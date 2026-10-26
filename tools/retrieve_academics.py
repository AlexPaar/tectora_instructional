import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field, RootModel
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27020/?directConnection=true")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tectora")
MONGO_ACADEMICS_COLLECTION = os.getenv("MONGO_ACADEMICS_COLLECTION", "academics")


class AcademicsFromIDsParams(BaseModel):
    academic_ids: set[str] = Field(description="The academic IDs.")


class AcademicsFromIDsOutput(BaseModel):
    name: str = Field(description="The name of the academic.")
    affiliation: str | None = Field(description="The affiliation of the academic.")
    email: str | None = Field(description="The email address of the academic.")
    phone_number: str | None = Field(description="The phone number of the academic.")
    role: list[str] = Field(description="The roles of the academic.")


class AcademicByNameParams(BaseModel):
    name: Annotated[str, Field(description="The full name of the individual (e.g., 'John Doe' or 'Prof. Dr. Smith').")]


class AcademicByNameOutput(BaseModel):
    name: str = Field(description="The name of the academic.")
    affiliation: str | None = Field(description="The affiliation of the academic.")
    email: str | None = Field(description="The email address of the academic.")
    phone_number: str | None = Field(description="The phone number of the academic.")
    role: list[str] = Field(description="The roles of the academic.")


@tool(args_schema=AcademicsFromIDsParams, description="Retrieve academics from the database based on their IDs")
def retrieve_academics_from_ids(academic_ids: set[str]) -> dict:
    """Retrieve academics from the database based on their IDs."""
    academic_list_schema = RootModel[list[AcademicsFromIDsOutput]].model_json_schema()

    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
        collection = db[MONGO_ACADEMICS_COLLECTION]

        results = collection.find({"id": {"$in": list(academic_ids)}})

        academics = [
            AcademicsFromIDsOutput(
                name=academic.get("name"),
                affiliation=academic.get("affiliation"),
                email=academic.get("email"),
                phone_number=academic.get("phone_number"),
                role=academic.get("role"),
            )
            for academic in results
        ]

        academic_list_model = RootModel[list[AcademicsFromIDsOutput]](academics)
        self_documenting_payload = {
            "data": academic_list_model.model_dump(),
            "field_semantics_reference": academic_list_schema if academics else None,
        }
    except Exception as error:  # noqa: BLE001
        self_documenting_payload = {
            "data": [],
            "error": str(error),
            "field_semantics_reference": academic_list_schema,
        }

    return self_documenting_payload


@tool(args_schema=AcademicByNameParams, description="Retrieve an academic from the database based on their name")
def retrieve_academic_by_name(name: str) -> dict:
    """Retrieve an academic from the database based on their name."""
    academic_schema = AcademicByNameOutput.model_json_schema()["properties"]

    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
        collection = db[MONGO_ACADEMICS_COLLECTION]

        result = collection.find_one({"name": name})

        if result:
            academic = AcademicByNameOutput(
                name=result.get("name"),
                affiliation=result.get("affiliation"),
                email=result.get("email"),
                phone_number=result.get("phone_number"),
                role=result.get("role"),
            )

            self_documenting_payload = {
                "data": academic.model_dump(),
                "field_semantics_reference": academic_schema,
            }
        else:
            self_documenting_payload = {"data": None, "field_semantics_reference": None}
    except Exception as error:  # noqa: BLE001
        self_documenting_payload = {
            "data": [],
            "error": str(error),
            "field_semantics_reference": academic_schema,
        }

    return self_documenting_payload
