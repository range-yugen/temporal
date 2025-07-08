from temporalio import workflow
import asyncio
from datetime import timedelta
from activities import (
    check_doctor_availability,
    get_patient_by_phone,
    confirm_patient_appointment,
    estimate_wait_time_for_walkin,
    book_later_appointment,
    add_to_walkin_queue,
    register_patient,
    generate_prescription_slip,
    prescription_with_diagnosis,
    get_random_diagnosis_and_medicines
)

@workflow.defn
class ReceptionWorkflow:
    def __init__(self):
        self.wait_time = None
        self.decision = None
        self.phone_number = None
        self.patient_info = None
        self.doctor_available = None
        self.step = "check_doctor"
        self.prescription_slip = None
        self.diagnosis = None
        self.medicines = None
        self.doctor_id = None
        self.doctor_name = None

    @workflow.signal
    async def provide_phone_number(self, phone_number: str):
        self.phone_number = phone_number

    @workflow.signal
    async def provide_patient_info(self, info: dict):
        self.patient_info = {
            "name": info["name"],
            "gender": info["gender"],
            "age": info["age"],
            "address": info["address"],
            "phone_number": self.phone_number
        }

    @workflow.signal
    async def make_decision(self, decision: str):
        self.decision = decision

    @workflow.query
    def get_status(self) -> dict:
        return {
            "step": self.step,
            "wait_time": self.wait_time,
            "decision": self.decision,
            "phone_number": self.phone_number,
            "patient_info": self.patient_info,
            "doctor_available": self.doctor_available,
            "prescription_slip": self.prescription_slip,
            "diagnosis": self.diagnosis,
            "medicines": self.medicines,
            "doctor_name": self.doctor_name,
        }

    @workflow.run
    async def run(self, doctor_name: str) -> str:
        self.doctor_name = doctor_name
        self.step = "check_doctor"

        # Step 1: Check doctor availability
        result = await workflow.execute_activity(
            check_doctor_availability,
            args=[doctor_name],
            start_to_close_timeout=timedelta(seconds=10)
        )

        if result["available"]:
            self.doctor_id = result["doctor_id"]
            self.doctor_available = True
        else:
            self.doctor_available = False
            return f"Dr. {doctor_name} is not available at this time. Please try again later or choose another doctor."

        # Step 2: Wait for phone number
        self.step = "get_phone"
        await workflow.wait_condition(lambda: self.phone_number is not None)

        # Step 3: Look up patient by phone        
        self.patient_info = await workflow.execute_activity(
            get_patient_by_phone,
            args=[self.phone_number],
            start_to_close_timeout=timedelta(seconds=10)
        )

        if not self.patient_info:
            # Patient not found - need registration
            self.step = "register_patient"
            await workflow.wait_condition(lambda: self.patient_info is not None)

            # Register the patient
            await workflow.execute_activity(
                register_patient,
                args=[
                    self.patient_info["name"], 
                    self.phone_number, 
                    self.patient_info["gender"], 
                    self.patient_info["age"], 
                    self.patient_info["address"]
                ],
                start_to_close_timeout=timedelta(seconds=10)
            )

            # Fetch the newly registered patient
            self.patient_info = await workflow.execute_activity(
                get_patient_by_phone,
                args=[self.phone_number],
                start_to_close_timeout=timedelta(seconds=10)
            )

            if not self.patient_info:
                return f"Registration failed for phone number {self.phone_number}. Please try again."

        patient_id = self.patient_info["patient_id"]
        patient_name = self.patient_info["name"]

        # Step 4: Check for existing appointment
        self.step = "check_appointment"
        
        has_appointment = await workflow.execute_activity(
            confirm_patient_appointment,
            args=[patient_id, self.doctor_id],
            start_to_close_timeout=timedelta(seconds=10)
        )

        if has_appointment:
            # Patient has appointment - direct to consultation
            self.step = "generate_prescription"
            
            # Generate initial prescription slip
            slip_result = await workflow.execute_activity(
                generate_prescription_slip,
                args=[{
                    "name": self.patient_info["name"],
                    "phone": self.patient_info["phone_number"],
                    "age": self.patient_info["age"],
                    "gender": self.patient_info["gender"],
                    "address": self.patient_info["address"],
                }],
                start_to_close_timeout=timedelta(seconds=20)
            )

            self.prescription_slip = slip_result
            
            # Wait 8 seconds before proceeding to diagnosis
            await asyncio.sleep(8)
            
            # Add diagnosis generation step
            self.step = "diagnosis_generation"
            
            # Get diagnosis and medicines (simulate doctor consultation)
            diagnosis_data = await workflow.execute_activity(
                get_random_diagnosis_and_medicines,
                start_to_close_timeout=timedelta(seconds=10)
            )
            self.diagnosis = diagnosis_data["diagnosis"]
            self.medicines = diagnosis_data["medicines"]

            self.step = "finalize_prescription"
            
            # Generate final prescription with diagnosis and medicines
            final_pdf_url = await workflow.execute_activity(
                prescription_with_diagnosis,
                args=[self.prescription_slip["unique_id"], self.diagnosis, self.medicines],
                start_to_close_timeout=timedelta(seconds=20)
            )
                          
            return f"Consultation completed for {patient_name}!\n Final prescription with diagnosis: {final_pdf_url}\n Diagnosis: {self.diagnosis}"

        # No appointment - calculate wait time
        self.step = "calculate_wait"
        
        self.wait_time = await workflow.execute_activity(
            estimate_wait_time_for_walkin,
            args=[self.doctor_id],
            start_to_close_timeout=timedelta(seconds=10)
        )

        # Wait for patient decision
        self.step = "make_decision"
        await workflow.wait_condition(lambda: self.decision is not None)

        # Process decision
        if self.decision == "continue":
            # Add to walk-in queue
            self.step = "add_to_queue"
            
            await workflow.execute_activity(
                add_to_walkin_queue,
                args=[patient_id, self.doctor_id],
                start_to_close_timeout=timedelta(seconds=10)
            )

            await asyncio.sleep(1)

            # Generate prescription slip
            self.step = "generate_prescription"
            
            slip_result = await workflow.execute_activity(
                generate_prescription_slip,
                args=[{
                    "name": self.patient_info["name"],
                    "phone": self.patient_info["phone_number"],
                    "age": self.patient_info["age"],
                    "gender": self.patient_info["gender"],
                    "address": self.patient_info["address"],
                }],
                start_to_close_timeout=timedelta(seconds=20)
            )

            self.prescription_slip = slip_result
            
            # Wait 8 seconds before proceeding to diagnosis
            await asyncio.sleep(8)
            
            # Add diagnosis generation step
            self.step = "diagnosis_generation"
            
            # Get diagnosis and medicines (simulate doctor consultation)
            diagnosis_data = await workflow.execute_activity(
                get_random_diagnosis_and_medicines,
                start_to_close_timeout=timedelta(seconds=10)
            )
            self.diagnosis = diagnosis_data["diagnosis"]
            self.medicines = diagnosis_data["medicines"]
            
            self.step = "finalize_prescription"
            
            # Generate final prescription
            final_pdf_url = await workflow.execute_activity(
                prescription_with_diagnosis,
                args=[self.prescription_slip["unique_id"], self.diagnosis, self.medicines],
                start_to_close_timeout=timedelta(seconds=20)
            )

            return f"Consultation completed for {patient_name}!\n Final prescription with diagnosis: {final_pdf_url}\n Diagnosis: {self.diagnosis}"

        # Book later appointment
        self.step = "book_appointment"
        
        result = await workflow.execute_activity(
            book_later_appointment,
            args=[patient_id, self.doctor_id],
            start_to_close_timeout=timedelta(seconds=20)
        )

        if isinstance(result, str):
            return f"Booking failed: {result}"

        patient_id, doctor_id, appointment_time = result
        return f"Appointment scheduled successfully!\n Patient: {patient_name}\n Doctor: Dr. {doctor_name}\n Appointment time: {appointment_time}\n Please arrive 15 minutes early."