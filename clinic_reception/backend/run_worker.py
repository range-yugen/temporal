import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from workflows import ReceptionWorkflow
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

async def main():
    client = await Client.connect("localhost:7233", namespace="default")

    worker = Worker(
        client=client,
        task_queue="reception-task-queue",
        workflows=[ReceptionWorkflow],
        activities=[
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
        ]
    )

    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())