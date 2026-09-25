"""Seed script for Firestore collection 'pending_bills'."""

from google.cloud import firestore

GCP_PROJECT_ID = "qwiklabs-gcp-04-6cd340013265"


def seed_data():
    db = firestore.Client(project=GCP_PROJECT_ID)
    collection_ref = db.collection("pending_bills")

    bills = [
        {
            "id": "chase-freedom",
            "name": "Chase Freedom Unlimited",
            "category": "credit_card",
            "balance": 1450.00,
            "minimum_due": 45.00,
            "due_date": "2026-10-02",
            "apr": 24.99,
            "hardship_status": "eligible",
            "notes": "Hardship program available: can reduce APR to 9.99% or defer payment 30 days upon hardship verification.",
        },
        {
            "id": "citi-double-cash",
            "name": "Citi Double Cash",
            "category": "credit_card",
            "balance": 820.00,
            "minimum_due": 30.00,
            "due_date": "2026-10-08",
            "apr": 26.24,
            "hardship_status": "none",
            "notes": "Late fee $41. Requires phone call to customer retention for temporary waiver.",
        },
        {
            "id": "sutter-health",
            "name": "Sutter Health Urgent Care",
            "category": "medical",
            "balance": 350.00,
            "minimum_due": 50.00,
            "due_date": "2026-10-15",
            "apr": 0.0,
            "hardship_status": "eligible",
            "notes": "Zero interest medical bill. Financial assistance / charity care application pending; offers interest-free 6-month installment plan.",
        },
        {
            "id": "pge-electric",
            "name": "Pacific Gas & Electric (PG&E)",
            "category": "utility",
            "balance": 185.50,
            "minimum_due": 185.50,
            "due_date": "2026-09-30",
            "apr": 0.0,
            "hardship_status": "none",
            "notes": "Essential utility. Medical Baseline allowance or REACH program provides immediate 60-day shutoff moratorium.",
        },
    ]

    print(f"Seeding bills into Firestore project '{GCP_PROJECT_ID}'...")
    for item in bills:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"  ✓ Seeded {item['name']} ({item['category']}) - Due: {item['due_date']}, Balance: ${item['balance']}")

    print("Seeding completed successfully!")


if __name__ == "__main__":
    seed_data()
