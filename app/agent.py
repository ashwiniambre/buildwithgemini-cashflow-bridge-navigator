# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional
import urllib.request
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

MODEL = "gemini-3.6-flash"
GCP_PROJECT_ID = "qwiklabs-gcp-04-6cd340013265"
GCS_BUCKET_NAME = "cashflow-bridge-assets-6cd340013265"
SANDBOX_RESOURCE_NAME = "projects/356017740640/locations/us-east1/reasoningEngines/627185621739241472/sandboxEnvironments/3211752629570895872"

_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    return _firestore_client


def list_pending_bills(category: str = "") -> List[Dict[str, Any]]:
    """Retrieves pending bills, credit card balances, and expenses from the Firestore database.

    Args:
        category: Optional category filter, such as 'credit_card', 'medical', or 'utility'. If empty, returns all bills.

    Returns:
        A list of dictionaries with bill details: id, name, category, balance, minimum_due, due_date, apr, hardship_status, and notes.
    """
    db = get_firestore_client()
    collection_ref = db.collection("pending_bills")
    docs = collection_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if category:
            if data.get("category", "").lower() == category.lower():
                results.append(data)
        else:
            results.append(data)

    results.sort(key=lambda x: str(x.get("due_date", "")))
    return results


def add_pending_bill(
    name: str,
    category: str,
    balance: float,
    minimum_due: float,
    due_date: str,
    apr: float = 0.0,
    notes: str = "",
) -> Dict[str, Any]:
    """Adds a new pending bill, credit card balance, or expense to Firestore.

    Args:
        name: Creditor or bill name (e.g., 'Chase Freedom', 'City Hospital').
        category: Category of bill ('credit_card', 'medical', 'utility', 'other').
        balance: Total outstanding balance owed.
        minimum_due: Minimum payment amount due.
        due_date: Payment due date in 'YYYY-MM-DD' format.
        apr: Annual Percentage Rate interest rate (e.g., 24.99). Defaults to 0.0.
        notes: Any details regarding hardship eligibility, late fees, or arrangements.

    Returns:
        A dictionary confirming the newly added bill with its ID.
    """
    db = get_firestore_client()
    doc_id = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    collection_ref = db.collection("pending_bills")

    record = {
        "id": doc_id,
        "name": name,
        "category": category,
        "balance": float(balance),
        "minimum_due": float(minimum_due),
        "due_date": due_date,
        "apr": float(apr),
        "hardship_status": "none",
        "notes": notes,
    }
    collection_ref.document(doc_id).set(record)
    return {
        "status": "success",
        "message": f"Added bill '{name}'",
        "bill": record,
    }


def update_bill_hardship_status(
    bill_id: str,
    hardship_status: str,
    notes: str = "",
) -> Dict[str, Any]:
    """Updates payment arrangement or hardship status and notes for a specific bill in Firestore.

    Args:
        bill_id: The document ID of the bill (e.g., 'chase-freedom', 'citi-double-cash').
        hardship_status: New hardship status ('none', 'eligible', 'requested', 'deferred', 'enrolled').
        notes: Additional notes or extension details (e.g., 'Approved 30-day grace period').

    Returns:
        A dictionary confirming the update status.
    """
    db = get_firestore_client()
    doc_ref = db.collection("pending_bills").document(bill_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"status": "error", "message": f"Bill with id '{bill_id}' not found"}

    updates: Dict[str, Any] = {"hardship_status": hardship_status}
    if notes:
        existing_notes = doc.to_dict().get("notes", "")
        updates["notes"] = f"{existing_notes} | {notes}" if existing_notes else notes

    doc_ref.update(updates)
    return {
        "status": "success",
        "message": f"Updated bill '{bill_id}' hardship status to '{hardship_status}'",
    }


def calculate_cashflow_runway(
    current_cash: float,
    expected_income_date: str,
    expected_income_amount: float = 0.0,
) -> Dict[str, Any]:
    """Analyzes cashflow runway, calculates deficits until expected income arrives, and prioritizes pending bills.

    Args:
        current_cash: The user's available liquid cash on hand (e.g. checking account balance).
        expected_income_date: Date when next income or benefit deposit is expected in 'YYYY-MM-DD' format.
        expected_income_amount: Expected deposit amount in dollars (e.g. EDD disability payment). Defaults to 0.0.

    Returns:
        A dictionary summarizing days until income, total minimum payments due before income arrival,
        cash deficit/surplus, and categorized payment recommendations.
    """
    db = get_firestore_client()
    docs = db.collection("pending_bills").stream()
    all_bills = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        all_bills.append(data)

    try:
        target_date = datetime.date.fromisoformat(expected_income_date)
        today = datetime.date.today()
        days_until = (target_date - today).days
    except Exception:
        days_until = 0

    due_before = []
    due_after = []

    for bill in all_bills:
        due_str = bill.get("due_date", "")
        try:
            b_date = datetime.date.fromisoformat(due_str)
            if b_date <= target_date:
                due_before.append(bill)
            else:
                due_after.append(bill)
        except Exception:
            due_before.append(bill)

    total_min_due_before = sum(float(b.get("minimum_due", 0.0)) for b in due_before)
    cash_gap = float(current_cash) - total_min_due_before

    must_pay_now = [b for b in due_before if b.get("category") == "utility"]
    hardship_candidates = [
        b for b in due_before
        if b.get("category") != "utility" or b.get("hardship_status") == "eligible"
    ]

    return {
        "current_cash": float(current_cash),
        "expected_income_date": expected_income_date,
        "expected_income_amount": float(expected_income_amount),
        "days_until_income": max(days_until, 0),
        "bills_due_before_income_count": len(due_before),
        "total_minimum_due_before_income": round(total_min_due_before, 2),
        "cashflow_gap": round(cash_gap, 2),
        "has_shortfall": cash_gap < 0,
        "shortfall_amount": round(abs(cash_gap), 2) if cash_gap < 0 else 0.0,
        "must_pay_now": [
            {
                "id": b.get("id"),
                "name": b["name"],
                "minimum_due": b.get("minimum_due"),
                "due_date": b.get("due_date"),
                "category": b.get("category"),
            }
            for b in must_pay_now
        ],
        "hardship_deferral_candidates": [
            {
                "id": b.get("id"),
                "name": b["name"],
                "minimum_due": b.get("minimum_due"),
                "due_date": b.get("due_date"),
                "category": b.get("category"),
                "hardship_status": b.get("hardship_status"),
                "potential_savings": b.get("minimum_due"),
            }
            for b in hardship_candidates
        ],
        "bills_due_after_income": [
            {
                "id": b.get("id"),
                "name": b["name"],
                "due_date": b.get("due_date"),
                "minimum_due": b.get("minimum_due"),
            }
            for b in due_after
        ],
    }


def get_federal_interest_rates(security_desc: str = "") -> Dict[str, Any]:
    """Fetches benchmark interest rates from the U.S. Department of the Treasury Fiscal Data API.

    These rates represent current federal borrowing and yield benchmarks (e.g. Treasury Bills, Notes, Bonds)
    which directly influence prime lending rates and consumer credit card APRs.

    Args:
        security_desc: Optional filter for security type (e.g., 'Bills', 'Notes', 'Bonds', or leave empty for all).

    Returns:
        A dictionary containing the latest average interest rates by security type, source attribution, and record date.
    """
    api_key = os.getenv("FISCAL_DATA_API_KEY", "")
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=10"
    headers = {"User-Agent": "CashflowBridge/1.0"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        raw_items = payload.get("data", [])
        rates = []
        seen = set()
        for row in raw_items:
            desc = row.get("security_desc", "")
            if security_desc and security_desc.lower() not in desc.lower():
                continue
            if desc not in seen:
                seen.add(desc)
                rates.append({
                    "security": desc,
                    "security_type": row.get("security_type_desc"),
                    "average_rate_percent": float(row.get("avg_interest_rate_amt", 0.0)),
                    "effective_date": row.get("record_date"),
                })

        return {
            "status": "success",
            "source": "U.S. Department of the Treasury Fiscal Data API",
            "rates": rates,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to fetch treasury data: {e}",
        }


async def generate_item_image(
    prompt: str,
    filename: str = "financial_roadmap.jpg",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Generates a visual illustration, roadmap card, or milestone badge for an item in the cashflow and hardship domain using gemini-3.1-flash-lite-image in the global region.

    Saves the generated image as an artifact via tool_context.save_artifact for the Playground's Artifacts panel,
    and uploads the image bytes to the public Cloud Storage bucket, returning its public https URL. Does not write to a local file.

    Args:
        prompt: Detailed visual prompt describing the financial roadmap, bill relief badge, or cashflow bridge diagram to generate.
        filename: Name of the artifact and Cloud Storage object (e.g. 'financial_roadmap.jpg').
        tool_context: Injected by the ADK runtime to interact with artifacts.

    Returns:
        A dictionary containing the public Cloud Storage HTTPS URL, status, and filename.
    """
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location="global",
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    image_bytes: Optional[bytes] = None
    mime_type = "image/jpeg"

    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

    if not image_bytes:
        return {
            "status": "error",
            "message": "No image bytes were returned by gemini-3.1-flash-lite-image.",
        }

    # (1) Save artifact for Playground's Artifacts panel
    artifact_saved = False
    if tool_context is not None:
        try:
            artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            artifact_saved = True
        except Exception:
            artifact_saved = False

    # (2) Upload same image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket("cashflow-bridge-assets-6cd340013265")
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)
    public_url = f"https://storage.googleapis.com/cashflow-bridge-assets-6cd340013265/{filename}"

    return {
        "status": "success",
        "public_url": public_url,
        "filename": filename,
        "artifact_saved": artifact_saved,
        "mime_type": mime_type,
        "message": f"Image successfully generated and uploaded to public Cloud Storage: {public_url}",
    }


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Cashflow Bridge Navigator — a personal financial crisis, cashflow, and hardship advisor. "
        "You help individuals navigate temporary income gaps and disruptions (such as layoffs, medical or disability leave, "
        "unemployment, freelance invoice delays, or emergency expenses) by prioritizing essential living expenses and protecting "
        "their credit.\n\n"
        "Key capabilities and guidelines:\n"
        "1. Inspect and track bills, credit cards, utilities, and medical expenses using your Firestore tools.\n"
        "2. Calculate cashflow runway, timelines, and shortfalls until the next income arrival using calculate_cashflow_runway.\n"
        "3. Prioritize essential survival expenses (preventing utility shutoffs and eviction) over unsecured debt.\n"
        "4. Identify hardship programs, payment deferrals, and late-fee waivers to bridge cash gaps safely.\n"
        "5. Reference federal benchmark interest rates from the U.S. Treasury to explain why carrying high credit card balances is costly and why hardship APR freezes save money.\n"
        "6. Generate visual roadmap cards, debt payoff badges, or cashflow bridge milestone illustrations using generate_item_image when helpful.\n"
        "7. When running custom financial math, compound interest projections, or simulation scripts, safely execute Python code in your Agent Engine Sandbox environment.\n"
        "8. Communicate empathetically, clearly, and concisely, suitable for both visual reading and spoken voice playback."
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        list_pending_bills,
        add_pending_bill,
        update_bill_hardship_status,
        calculate_cashflow_runway,
        get_federal_interest_rates,
        generate_item_image,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
