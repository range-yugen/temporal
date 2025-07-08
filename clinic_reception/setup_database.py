import sqlite3
import pandas as pd

# Connect to SQLite database
conn = sqlite3.connect("clinic.db")

# Load and insert each CSV table
tables = ["doctor_schedule", "patients", "appointments", "doctor_queue", "diagnosis_medicines"]

for table in tables:
    df = pd.read_csv(f"data/{table}.csv")
    df.to_sql(table, conn, if_exists="append", index=False)
    print(f"Loaded {len(df)} records into {table} table")

conn.commit()
conn.close()
print("Database setup completed successfully!")