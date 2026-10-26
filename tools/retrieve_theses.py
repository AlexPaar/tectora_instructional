"""Deep Agent Research Assistant Tools."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_mongodb.vectorstores import MongoDBAtlasVectorSearch
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field, RootModel
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27020/?directConnection=true")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tectora")
MONGO_DOCUMENTS_COLLECTION = os.getenv("MONGO_DOCUMENTS_COLLECTION", "documents")
MONGO_DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX = os.getenv(
    "MONGO_DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX", "document_text_summaries_vector_index"
)
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "openai:text-embedding-3-small")
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "2"))


class ThesesRetrievalParams(BaseModel):
    query_terms: str = Field(
        description="The search query terms for retrieving theses from the database. This can include keywords, phrases, or specific topics of interest. Do NOT include file extensions."
    )
    top_k_results: int = Field(default=TOP_K_RESULTS, description="The maximum number of matching theses to retrieve.")


class ThesisRetrievalOutput(BaseModel):
    filepath: str = Field(description="The original path of the file on disk.")
    filename: str = Field(description="The original name of the file on disk.")
    docling_file_id: str | None = Field(description="The unique identifier of the corresponding Docling file.")
    text_summary: str = Field(description="Generated summary of the thesis content.")
    thesis_title: str | None = Field(
        None,
        description="The title of the thesis, extracted from the cover page.",
    )
    submitted: date | None = Field(
        None, description="The submission date of the thesis document; null for non-thesis files."
    )
    academic_ids: set[str] = Field(
        default=set(),
        description="A unique set of IDs of academics mentioned in the thesis.",
    )


def _initialize_vector_store() -> MongoDBAtlasVectorSearch:
    """Initialize MongoDB Atlas Vector Search store for document queries."""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    collection = db[MONGO_DOCUMENTS_COLLECTION]

    embeddings = OpenAIEmbeddings(model=MODEL_EMBEDDING.rsplit(":", 1)[-1])

    vector_store = MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name=MONGO_DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX,
        text_key="text_summary",
        embedding_key="text_summary_embedding",
    )

    return vector_store


@tool(args_schema=ThesesRetrievalParams, description="Retrieve theses from the database based on query terms")
def retrieve_theses(query_terms: str, top_k_results: int = TOP_K_RESULTS) -> dict:
    """Retrieve theses from the database based on query terms."""
    thesis_list_schema = RootModel[list[ThesisRetrievalOutput]].model_json_schema()

    try:
        vector_store = _initialize_vector_store()
        docs = vector_store.similarity_search(query_terms, k=top_k_results)

        results = []

        for doc in docs:
            metadata = doc.metadata
            result = ThesisRetrievalOutput(
                filepath=metadata.get("filepath"),
                filename=metadata.get("filename"),
                docling_file_id=metadata.get("docling_file_id"),
                text_summary=doc.page_content,
                thesis_title=metadata.get("thesis_title"),
                submitted=metadata.get("submitted"),
                academic_ids=set(metadata.get("academic_ids", [])),
            )
            results.append(result)

        thesis_list_model = RootModel[list[ThesisRetrievalOutput]](results)

        self_documenting_payload = {
            "data": thesis_list_model.model_dump(),
            "field_semantics_reference": thesis_list_schema if results else None,
        }
    except Exception as error:  # noqa: BLE001
        self_documenting_payload = {
            "data": [],
            "error": str(error),
            "field_semantics_reference": thesis_list_schema,
        }

    return self_documenting_payload
