from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from temporalio.client import Client
from uuid import uuid4
import re
import asyncio
from fastapi.staticfiles import StaticFiles
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # go one level up
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

class PhoneRequest(BaseModel):
    workflow_id: str
    phone_number: str

class RegistrationRequest(BaseModel):
    workflow_id: str
    name: str
    gender: str
    age: str
    address: str

class DecisionRequest(BaseModel):
    workflow_id: str
    decision: str

# Store active workflows for decision making
active_workflows = {}
prescription_messages_sent = {}

@app.post("/chat")
async def chat(req: ChatRequest):
    doctor_name = req.message.strip()
    if not doctor_name:
        return {"response": "Please provide the doctor name."}

    try:
        client = await Client.connect("localhost:7233")
        workflow_id = f"reception-{uuid4()}"

        handle = await client.start_workflow(
            "ReceptionWorkflow",
            args=[doctor_name],
            id=workflow_id,
            task_queue="reception-task-queue"
        )

        active_workflows[workflow_id] = handle
        await asyncio.sleep(2)

        try:
            status = await handle.query("get_status")

            if not status.get("doctor_available"):
                result = await handle.result()
                return {"response": f"{result}"}

            if status.get("step") == "get_phone":
                return {
                    "response": f"Dr. {doctor_name} is available! Please provide your phone number to proceed.",
                    "workflow_id": workflow_id,
                    "requires_phone": True
                }

        except Exception as e:
            return {"response": f"Error checking doctor availability: {str(e)}"}

    except Exception as e:
        return {"response": f"System error: {str(e)}"}

@app.post("/phone")
async def provide_phone(req: PhoneRequest):
    workflow_id = req.workflow_id
    phone_number = req.phone_number.strip()

    if workflow_id not in active_workflows:
        return {"response": "Session expired. Please start over."}

    if not re.match(r'^\+?[\d\s\-\(\)]+$', phone_number):
        return {"response": "Invalid phone number format. Please enter a valid phone number."}

    try:
        handle = active_workflows[workflow_id]

        await handle.signal("provide_phone_number", phone_number)
        await asyncio.sleep(3)

        try:
            status = await handle.query("get_status")

            if status.get("step") == "register_patient":
                return {
                    "response": f"Phone number {phone_number} verified.\n This appears to be a new patient. Please provide your registration details to continue.",
                    "workflow_id": workflow_id,
                    "requires_registration": True
                }

            if status.get("step") == "make_decision" and status.get("wait_time") is not None:
                patient_name = status.get("patient_info", {}).get("name", "Patient")
                wait_time = status["wait_time"]
                return {
                    "response": f"Welcome, {patient_name}!\n No appointment found for today. Current wait time: {wait_time} minutes.\n\n Would you like to:\n• Continue (wait in queue)\n• Book for later",
                    "workflow_id": workflow_id,
                    "wait_time": wait_time,
                    "patient_name": patient_name,
                    "requires_decision": True
                }

            # Check if patient has appointment and prescription is being generated
            if status.get("step") == "generate_prescription":
                return {
                    "response": f"Welcome back, {status.get('patient_info', {}).get('name', 'Patient')}!\n Appointment confirmed for today.\n Generating your prescription slip...\n Please wait while we prepare your slip.",
                    "workflow_id": workflow_id,
                    "requires_prescription_check": True,
                    "status": "generating_prescription"
                }

            try:
                result = await asyncio.wait_for(handle.result(), timeout=0.1)
                del active_workflows[workflow_id]
                return {"response": f"{result}"}
            except asyncio.TimeoutError:
                pass

        except Exception as e:
            try:
                result = await handle.result()
                del active_workflows[workflow_id]
                return {"response": f"{result}"}
            except:
                return {"response": f"Error processing phone number: {str(e)}"}

    except Exception as e:
        return {"response": f"Error processing phone number: {str(e)}"}

@app.post("/register")
async def register_patient(req: RegistrationRequest):
    workflow_id = req.workflow_id

    if workflow_id not in active_workflows:
        return {"response": "Session expired. Please start over."}

    if not all([req.name.strip(), req.gender.strip(), req.age.strip(), req.address.strip()]):
        return {"response": "All registration fields are required. Please fill in all details."}

    try:
        handle = active_workflows[workflow_id]

        await handle.signal("provide_patient_info", {
            "name": req.name.strip(),
            "gender": req.gender.strip(),
            "age": req.age.strip(),
            "address": req.address.strip()
        })

        await asyncio.sleep(4)

        try:
            status = await handle.query("get_status")

            if status.get("step") == "make_decision" and status.get("wait_time") is not None:
                patient_name = status.get("patient_info", {}).get("name", "Patient")
                wait_time = status["wait_time"]
                return {
                    "response": f"Registration successful!\n Welcome, {patient_name}!\n No appointment found for today. Current wait time: {wait_time} minutes.\n\n Would you like to:\n• Continue (wait in queue)\n• Book for later",
                    "workflow_id": workflow_id,
                    "wait_time": wait_time,
                    "patient_name": patient_name,
                    "requires_decision": True
                }

            try:
                result = await asyncio.wait_for(handle.result(), timeout=0.1)
                del active_workflows[workflow_id]
                return {"response": f"Registration successful!\n {result}"}
            except asyncio.TimeoutError:
                pass

        except Exception as e:
            try:
                result = await handle.result()
                del active_workflows[workflow_id]
                return {"response": f"Registration successful!\n {result}"}
            except:
                return {"response": f"Error processing registration: {str(e)}"}

    except Exception as e:
        return {"response": f"Error processing registration: {str(e)}"}

@app.post("/decision")
async def make_decision(req: DecisionRequest):
    workflow_id = req.workflow_id
    decision = req.decision.lower()

    if workflow_id not in active_workflows:
        return {"response": "Session expired. Please start over."}

    if decision not in ["continue", "book_later"]:
        return {"response": "Invalid choice. Please select 'continue' or 'book_later'."}

    try:
        handle = active_workflows[workflow_id]

        if decision == "continue":
            await handle.signal("make_decision", decision)
            await asyncio.sleep(1)

            try:
                status = await handle.query("get_status")
                if status.get("step") == "add_to_queue":
                    await asyncio.sleep(2)
                    status = await handle.query("get_status")
                    if status.get("step") == "generate_prescription":
                        return {
                            "response": "Added to queue successfully!\n Generating your prescription slip...\n Please wait while we prepare your slip.",
                            "workflow_id": workflow_id,
                            "requires_prescription_check": True,
                            "status": "generating_prescription"
                        }
        
            except Exception:
                return {
                    "response": "Processing your request...\n We'll notify you when your prescription is ready.",
                    "workflow_id": workflow_id,
                    "requires_prescription_check": True,
                    "status": "processing"
                }

        else:
            await handle.signal("make_decision", decision)
            await asyncio.sleep(3)

            try:
                result = await handle.result()
                del active_workflows[workflow_id]
                return {"response": f"Appointment scheduled!\n {result}"}
            except Exception as e:
                return {"response": f"Error booking appointment: {str(e)}"}

    except Exception as e:
        return {"response": f"Error processing decision: {str(e)}"}

@app.get("/check_prescription/{workflow_id}")
async def check_prescription_status(workflow_id: str):
    if workflow_id not in active_workflows:
        return {"response": "Workflow not found or completed."}

    try:
        handle = active_workflows[workflow_id]

        try:
            result = await asyncio.wait_for(handle.result(), timeout=0.1)
            del active_workflows[workflow_id]
            # Clean up the tracking when workflow completes
            if workflow_id in prescription_messages_sent:
                del prescription_messages_sent[workflow_id]
            return {
                "status": "completed",
                "response": f"{result}"
            }
        except asyncio.TimeoutError:
            pass

        status = await handle.query("get_status")
        current_step = status.get("step")

        if current_step == "add_to_queue":
            return {
                "status": "adding_to_queue",
                "response": "Adding you to the queue...\n Please take a seat and wait for your turn."
            }

        elif current_step == "generate_prescription":
            prescription_slip = status.get("prescription_slip")
            if prescription_slip and prescription_slip.get("pdf_url"):
                # Check if we've already sent the prescription ready message
                if workflow_id not in prescription_messages_sent:
                    prescription_messages_sent[workflow_id] = True
                    return {
                        "status": "prescription_ready",
                        "response": f"Your initial prescription slip is ready!\n Download: {prescription_slip['pdf_url']}\n",
                        "prescription_url": prescription_slip["pdf_url"]
                    }
                else:
                    # Already sent the message, just show ongoing consultation
                    return {
                        "status": "consultation_in_progress",
                        "response": "Doctor consultation in progress...\n Generating diagnosis and finalizing prescription..."
                    }


        else:
            return {
                "status": "processing",
                "response": f"Processing step: {current_step or 'unknown'}\n Please wait..."
            }

    except Exception as e:
        return {
            "status": "error",
            "response": f"Error checking prescription status: {str(e)}"
        }