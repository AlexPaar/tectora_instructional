#!/usr/bin/env python3
"""Load the thesis artifacts of a given directory into a MongoDB vector store."""

import json
import logging
import os
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

import gridfs
import tiktoken
import typer
from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc.document import DoclingDocument
from dotenv import load_dotenv
from langchain_core.language_models import LanguageModelInput
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field, model_validator
from pymongo import MongoClient
from rapidfuzz import fuzz
from rich.console import Console

app = typer.Typer()

console = Console()

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.getLogger("pypdf").setLevel(logging.ERROR)

PYTHON_ENV = os.getenv("PYTHON_ENV", "production").lower()

MODEL_ENV = os.getenv("MODEL_ENV", "litellm").lower()

HF_TOKEN = os.getenv("HF_TOKEN")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27020/?directConnection=true")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tectora")
MONGO_DOCUMENTS_COLLECTION = os.getenv("MONGO_DOCUMENTS_COLLECTION", "documents")
MONGO_DOCUMENT_CHUNKS_COLLECTION = os.getenv("MONGO_DOCUMENT_CHUNKS_COLLECTION", "document_chunks")
MONGO_ACADEMICS_COLLECTION = os.getenv("MONGO_ACADEMICS_COLLECTION", "academics")

MODEL_STRUCTURED_OUTPUT = os.getenv("MODEL_STRUCTURED_OUTPUT", "openai:gpt-4o-mini")
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "openai:text-embedding-3-small")

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000/v1")

EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))

MAXIMUM_TEXT_LENGTH = int(os.getenv("MAXIMUM_TEXT_LENGTH", "20480"))
TEXT_LENGTH_FOR_DOCUMENT_CATEGORY = int(os.getenv("TEXT_LENGTH_FOR_DOCUMENT_CATEGORY", "4000"))
TEXT_LENGTH_FOR_STAKEHOLDER_INFO = int(os.getenv("TEXT_LENGTH_FOR_STAKEHOLDER_INFO", "4000"))
TEXT_LENGTH_FOR_THESIS_TITLE = int(os.getenv("TEXT_LENGTH_FOR_THESIS_TITLE", "2000"))
TEXT_LENGTH_FOR_SUBMISSION_DATE = int(os.getenv("TEXT_LENGTH_FOR_SUBMISSION_DATE", "4000"))

MAXIMUM_TEXT_LENGTH_FOR_THESIS_SUMMARY = int(os.getenv("MAXIMUM_TEXT_LENGTH_FOR_THESIS_SUMMARY", "20480"))
MAXIMUM_TEXT_LENGTH_FOR_THESIS_TITLE = int(os.getenv("MAXIMUM_TEXT_LENGTH_FOR_THESIS_TITLE", "2000"))
MAXIMUM_TEXT_LENGTH_FOR_SUBMISSION_DATE = int(os.getenv("MAXIMUM_TEXT_LENGTH_FOR_SUBMISSION_DATE", "4000"))
MAXIMUM_TEXT_LENGTH_FOR_ACADEMICS = int(os.getenv("MAXIMUM_TEXT_LENGTH_FOR_ACADEMICS", "4000"))

INPUT_DIR = os.getenv("INPUT_DIR")
OUTPUT_DIR = os.getenv("OUTPUT_DIR")

MIRRORED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}

DOCLING_EXTENSIONS = {
    "JSON": ".docling.json",
    "DCLG": ".dclg",
}


class DoclingDocumentCategory(BaseModel):
    """Schema for categorizing Docling documents into specific categories."""

    category: Literal["thesis", "thesis_proposal", "company_statement", "assessment", "notes"] = Field(
        description="""Classify the document into exactly one of these categories based on strict rules:
        - 'thesis': The final academic paper (Bachelor/Master thesis). Characterized by high page counts, an abstract, table of contents, extensive bibliography, and a 'Declaration of Authorship' ('Eigenständigkeitserklärung'). MUST have more than 8000 words and contain final results/conclusions.
        - 'thesis_proposal': A preliminary research proposal or outline written before the thesis. Outlines the research question, planned methodology, and literature overview. Typically 3-10 pages (less pages than the final thesis) and lacks final conclusions/results.
        - 'company_statement': Official letters or forms from the corporate partner/internship company ('Praxispartner'). Mentions company details and how the content of the Bachelor/Master thesis relates to the company's needs.
        - 'assessment': Official grading reports or evaluation forms ('Gutachten') written by the professor/supervisor. Contains explicit evaluative feedback, grading scales, or a final grade.
        - 'notes': Informal documentation, personal drafts, bulleted meeting minutes, to-do lists, or raw feedback transcripts gathered during supervision sessions.
        """
    )
    confidence_score: float = Field(
        description="A confidence score between 0.0 (completely unsure) and 1.0 (absolutely certain)."
    )
    key_indicators: list[str] = Field(
        description="Extract 2-3 short phrases or structural elements from the text that heavily justified this classification choice."
    )


class ThesisSummary(BaseModel):
    summary: str = Field(description="A concise thesis summary.")


class ThesisTitle(BaseModel):
    title: str = Field(description="The title of the thesis, extracted from the cover page.")


class SubmissionDate(BaseModel):
    submitted: date | None = Field(
        None,
        description="The submission or publication date of the thesis, extracted from the cover page. Return null if not found.",
    )


class Academic(BaseModel):
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Academic ID, auto-generated if not provided.",
    )
    name: Annotated[str, Field(description="The full name of the individual (e.g., 'John Doe' or 'Prof. Dr. Smith').")]
    roles: list[Literal["author", "supervisor", "advisor"]] = Field(
        default_factory=list,
        description="The role(s) of this person in the context of the thesis/supervision. Empty if unknown.",
    )
    affiliation: str | None = Field(
        None,
        description="The university department, institute, or company name they belong to.",
    )
    email: str | None = Field(
        None,
        description="The extracted email address. Enforce standard email format if found.",
    )
    phone_number: str | None = Field(
        None,
        description="The extracted telephone or mobile number, including country codes if present.",
    )

    @model_validator(mode="after")
    def ensure_uuid_id(self) -> "Academic":
        try:
            uuid.UUID(self.id)
        except (ValueError, AttributeError):
            self.id = str(uuid.uuid4())
        return self


class Academics(BaseModel):
    academics: list[Academic] = Field(
        default_factory=list,
        description="A list of all academics, contact persons, or authors identified in the text.",
    )


docling_document_category_extractor: Runnable[LanguageModelInput, DoclingDocumentCategory]

thesis_summary_extractor: Runnable[LanguageModelInput, ThesisSummary]

thesis_title_extractor: Runnable[LanguageModelInput, ThesisTitle]

submission_date_extractor: Runnable[LanguageModelInput, SubmissionDate]

academics_extractor: Runnable[LanguageModelInput, Academics]

embeddings: OpenAIEmbeddings

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
documents_collection = db[MONGO_DOCUMENTS_COLLECTION]
document_chunks_collection = db[MONGO_DOCUMENT_CHUNKS_COLLECTION]
academics_collection = db[MONGO_ACADEMICS_COLLECTION]

# GridFS bucket for docling JSON exports, which can exceed MongoDB's 16 MB document limit
docling_files = gridfs.GridFS(db, collection="docling_files")


# Chunker for DoclingDocuments, tokenized against the embedding model's own token limit
hybrid_chunker = HybridChunker(
    tokenizer=OpenAITokenizer(
        tokenizer=tiktoken.encoding_for_model(MODEL_EMBEDDING.rsplit(":", 1)[-1]), max_tokens=CHUNK_SIZE
    )
)


def _create_extractors_and_embeddings(litellm_virtual_key: str) -> None:
    """Initialize the extractors for document categorization, thesis summary, thesis title, submission date, and academics."""
    global docling_document_category_extractor
    global thesis_summary_extractor
    global thesis_title_extractor
    global submission_date_extractor
    global academics_extractor

    if MODEL_ENV == "direct":
        LLM = ChatOpenAI(model=MODEL_STRUCTURED_OUTPUT.rsplit(":", 1)[-1], temperature=0)
    else:
        LLM = ChatOpenAI(
            model=MODEL_STRUCTURED_OUTPUT.rsplit(":", 1)[-1],  # Must match a model allowed by your LiteLLM team
            base_url=LITELLM_BASE_URL,
            api_key=litellm_virtual_key,
            temperature=0,
        )

    docling_document_category_extractor = LLM.with_structured_output(DoclingDocumentCategory)
    thesis_summary_extractor = LLM.with_structured_output(ThesisSummary)
    thesis_title_extractor = LLM.with_structured_output(ThesisTitle)
    submission_date_extractor = LLM.with_structured_output(SubmissionDate)
    academics_extractor = LLM.with_structured_output(Academics)

    global embeddings

    if MODEL_ENV == "direct":
        embeddings = OpenAIEmbeddings(model=MODEL_EMBEDDING.rsplit(":", 1)[-1])
    else:
        embeddings = OpenAIEmbeddings(
            model=MODEL_EMBEDDING.rsplit(":", 1)[-1],
            base_url=LITELLM_BASE_URL,
            api_key=litellm_virtual_key,
        )


def _mirror_directory(input_dir: str, output_dir: str) -> tuple[int, int, int]:
    """Mirror input_dir into output_dir: copy new/changed files and delete stale ones.

    Returns the number of touched, mirrored, and deleted files.
    """
    input_relative_paths: set[str] = set()
    touched_count = 0
    mirrored_count = 0

    for root, _, files in os.walk(input_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() not in MIRRORED_EXTENSIONS:
                continue

            input_path = os.path.join(root, file)
            relative_path = os.path.relpath(input_path, input_dir)
            input_relative_paths.add(relative_path)
            touched_count += 1
            output_path = os.path.join(output_dir, relative_path)

            # Only copy if the output file is missing or older than the input file
            if not os.path.exists(output_path) or os.path.getmtime(input_path) > os.path.getmtime(output_path):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copy2(input_path, output_path)
                mirrored_count += 1

    if not os.path.isdir(output_dir):
        return touched_count, mirrored_count, 0

    # Remove output files/directories that no longer exist in the input
    deleted_count = 0
    for root, dirs, files in os.walk(output_dir, topdown=False):
        for file in files:
            output_path = os.path.join(root, file)
            if any(file.lower().endswith(extension.lower()) for extension in DOCLING_EXTENSIONS.values()):
                continue
            relative_path = os.path.relpath(output_path, output_dir)
            if relative_path not in input_relative_paths:
                os.remove(output_path)
                for extension in DOCLING_EXTENSIONS.values():
                    docling_path = output_path + extension
                    if os.path.exists(docling_path):
                        os.remove(docling_path)
                deleted_count += 1

        for directory in dirs:
            dir_path = os.path.join(root, directory)
            if not os.listdir(dir_path):
                os.rmdir(dir_path)

    return touched_count, mirrored_count, deleted_count


def _create_doclings(dir: str) -> int:
    """Convert every file with a MIRRORED_EXTENSIONS suffix in dir into a lossless Docling JSON document.

    Returns the number of Docling files created.
    """
    converter = DocumentConverter()
    created_count = 0

    for root, _, files in os.walk(dir):
        for filename in files:
            if os.path.splitext(filename)[1].lower() not in MIRRORED_EXTENSIONS:
                continue

            source_path = os.path.join(root, filename)
            docling_path_json = Path(source_path + ".docling.json")
            docling_path_dclg = Path(source_path + ".dclg")

            source_mtime = os.path.getmtime(source_path)
            json_needs_update = not docling_path_json.exists() or source_mtime > docling_path_json.stat().st_mtime
            dclg_needs_update = not docling_path_dclg.exists() or source_mtime > docling_path_dclg.stat().st_mtime

            if not json_needs_update and not dclg_needs_update:
                continue

            conversion_result = converter.convert(source_path)
            if json_needs_update:
                conversion_result.document.save_as_json(docling_path_json)
            if dclg_needs_update:
                conversion_result.document.save_as_doclang(docling_path_dclg)

            created_count += 1

    return created_count


def _extract_academics(document: DoclingDocument) -> Academics:
    """
    Parses document text to extract structured academics contact details.
    """
    prompt = f"""
    You are a data extraction assistant. Carefully analyze the following text snippet from a university 
    thesis supervision file. Extract the names, roles, affiliations, emails, and phone numbers of all 
    relevant academics (authors, primary supervisors, secondary reviewers, or company contacts).
    
    Do not invent or assume information. If a specific field (like a phone number) is missing for a person, 
    leave it as null.
    
    Document Text:
    \"\"\"{document.export_to_text()[:MAXIMUM_TEXT_LENGTH_FOR_ACADEMICS]}\"\"\"
    """

    academics = academics_extractor.invoke(prompt)

    return academics


def _extract_submission_date(document: DoclingDocument) -> SubmissionDate:
    """
    Extract the submission date from the thesis cover page.
    """
    prompt = f"""
    You are a data extraction assistant. Carefully analyze the following text snippet from a thesis document's cover page.
    Extract the submission or publication date of the thesis (typically stated on the title page or cover).
    
    Common date formats following German conventions include: "15.06.2024", "7.6.2024", and "15. Juni 2024"

    Often, the date is preceded by a location like "Dresden, den 15.06.2024" or "Dresden, 7.6.2024".
    
    Do not invent or assume information. If the date is not found, return null.
    
    Document Text:
    \"\"\"{document.export_to_text()[:MAXIMUM_TEXT_LENGTH_FOR_SUBMISSION_DATE]}\"\"\"
    """

    submission_date = submission_date_extractor.invoke(prompt)

    return submission_date


def _extract_thesis_title(document: DoclingDocument) -> ThesisTitle:
    """
    Extract the thesis title from the cover page.
    """
    prompt = f"""
    You are a data extraction assistant. Carefully analyze the following text snippet from a thesis document's cover page.
    Extract the title of the thesis (typically stated prominently on the title page or cover).
    
    Document Text:
    \"\"\"{document.export_to_text()[:MAXIMUM_TEXT_LENGTH_FOR_THESIS_TITLE]}\"\"\"
    """

    thesis_title = thesis_title_extractor.invoke(prompt)

    return thesis_title


def _generate_thesis_summary_embedding(thesis_summary: ThesisSummary | None) -> list[float] | None:
    """Generate a single embedding vector for the given thesis summary."""
    if not thesis_summary or not thesis_summary.summary:
        return None
    return embeddings.embed_query(thesis_summary.summary)


def _generate_thesis_summary(document: DoclingDocument) -> ThesisSummary:
    """Generate a concise summary for files categorized as thesis."""
    prompt = f"""
    You are an expert academic reviewer and scientific communicator. Your task is to analyze the provided thesis text and synthesize it into a comprehensive, high-density academic summary targeting approximately 2,000 words. 

    To achieve this length and maintain rigorous academic quality, you must strictly follow this structural breakdown and word budget:

    1. Introduction & Research Question (~300 words)
      - Outline the primary research problem, scope, and objectives.
      - State the core research questions or hypotheses explicitly.

    2. Theoretical Framework & Literature Review (~300 words)
      - Summarize the foundational theories, models, or literature the thesis builds upon.
      - Highlight the gap in existing research that this thesis aims to fill.

    3. Methodology & Research Design (~400 words)
     - Detail the exact research design, data collection methods, tools, and analytical frameworks used.
     - Explain the justification for choosing this specific methodology.

    4. Empirical Findings & Data Analysis (~600 words)
     - Provide an extensive, detailed breakdown of the main results, data points, or qualitative findings.
     - Use structured sub-sections if necessary to cover distinct experiments, case studies, or thematic patterns found in the text.

    5. Discussion, Limitations & Conclusion (~400 words)
      - Synthesize what the results mean in the broader context of the field.
      - Highlight the limitations noted by the author and the stated avenues for future research.

    CRITICAL INSTRUCTIONS:
      - Do not compress or over-summarize. Maintain a professional, academic tone.
      - Retain key terminology, academic citations (if present in the text), and specific data metrics.
      - Ensure the output spans the requested depth; do not truncate sections early.

    File: {document.origin.filename}
    Thesis Text:
    \"\"\"{document.export_to_text()[:MAXIMUM_TEXT_LENGTH_FOR_THESIS_SUMMARY]}\"\"\"
    """
    thesis_summary = thesis_summary_extractor.invoke(prompt)

    return thesis_summary


def _categorize_document(document: DoclingDocument) -> DoclingDocumentCategory:
    """Classify the document text into one of the predefined categories using a LLM."""

    # Pass just a snippet of the text to save tokens
    snippet = document.export_to_text()[:TEXT_LENGTH_FOR_DOCUMENT_CATEGORY]

    prompt = f"Analyze this document snippet of file {document.origin.filename} and categorize it into the correct category:\n\n{snippet}"

    result = docling_document_category_extractor.invoke(prompt)

    return result


def _complete_filepath_normalization(input_path: str) -> str:
    """
    Performs absolute canonical normalization on any file path.
    Handles environment variables, user shortcuts, symlinks, relative fragments,
    and platform-specific casing irregularities.
    """
    if not input_path:
        return ""

    # 1. Expand Environment Variables (e.g., converting '$PROJECTS/thesis' or '%VAR%')
    expanded_vars = os.path.expandvars(str(input_path))

    # 2. Convert to Path Object & Expand User Tilde (e.g., '~')
    path_obj = Path(expanded_vars).expanduser()

    # 3. Resolve to absolute path (eliminates '.', '..', extra slashes, and resolves symlinks)
    # strict=False avoids throwing an error if the target file doesn't exist yet
    canonical_path = path_obj.resolve(strict=False)

    # 4. Normalize Case (Crucial for Windows/macOS string comparisons)
    # e.g., converts 'C:\Users\Admin' and 'c:\users\admin' to an identical casing format
    fully_normalized_str = os.path.normcase(str(canonical_path))

    return fully_normalized_str


def _load_docling_documents(dir: str) -> tuple[int, list[Academic], dict[str, list[str]]]:
    """Load every Docling JSON file in dir, chunk its text, embed the chunks, and upsert into MongoDB.

    Returns the number of files loaded and the academics extracted from each file.
    """
    docling_extension = DOCLING_EXTENSIONS["JSON"]
    loaded_count = 0
    academics: list[Academic] = []
    document_academic_ids: dict[str, list[str]] = {}

    for root, _, files in os.walk(dir):
        for filename in files:
            if not filename.lower().endswith(docling_extension):
                continue

            filepath = _complete_filepath_normalization(os.path.join(root, filename))
            original_filename = filename[: -len(docling_extension)]

            docling_document = DoclingDocument.load_from_json(filepath)
            docling_json = docling_document.export_to_dict()

            category = _categorize_document(docling_document)

            thesis_summary = _generate_thesis_summary(docling_document) if category.category == "thesis" else None

            thesis_summary_embedding = _generate_thesis_summary_embedding(thesis_summary)

            thesis_title = _extract_thesis_title(docling_document) if category.category == "thesis" else None

            submission_date = _extract_submission_date(docling_document) if category.category == "thesis" else None

            academics_in_document = _extract_academics(docling_document)
            academics += academics_in_document.academics
            document_academic_ids[filepath] = [academic.id for academic in academics_in_document.academics]

            # Store the (potentially large) docling JSON in GridFS to stay under the 16 MB BSON document limit
            for stale_file in docling_files.find({"filename": filepath}):
                docling_files.delete(stale_file._id)
            docling_file_id = docling_files.put(
                json.dumps(docling_json).encode("utf-8"), filename=filepath, content_type="application/json"
            )

            documents_collection.update_one(
                {"filepath": filepath},
                {
                    "$set": {
                        "filepath": filepath,
                        "filename": original_filename,
                        "docling_file_id": docling_file_id,
                        "category": category.category,
                        **({"text_summary": thesis_summary.summary} if thesis_summary else {}),
                        **({"text_summary_embedding": thesis_summary_embedding} if thesis_summary_embedding else {}),
                        **(
                            {"thesis_title": thesis_title.title}
                            if thesis_title and thesis_title.title is not None
                            else {}
                        ),
                        **(
                            {"submitted": datetime.combine(submission_date.submitted, datetime.min.time())}
                            if submission_date and submission_date.submitted is not None
                            else {}
                        ),
                    }
                },
                upsert=True,
            )

            # Delete stale chunks for this file before inserting fresh ones (idempotency)
            document_chunks_collection.delete_many({"filepath": filepath})

            chunks = [hybrid_chunker.contextualize(chunk) for chunk in hybrid_chunker.chunk(docling_document)]

            if chunks:
                vectors = embeddings.embed_documents(chunks, chunk_size=CHUNK_SIZE)

                docs = [
                    {
                        "filepath": filepath,
                        "filename": original_filename,
                        "chunk_index": i,
                        "chunk_text": chunk,
                        "embedding": vector,
                    }
                    for i, (chunk, vector) in enumerate(zip(chunks, vectors))
                ]
                document_chunks_collection.insert_many(docs)

            loaded_count += 1

    return loaded_count, academics, document_academic_ids


def _merge_academics(base: Academic, incoming: Academic) -> Academic:
    """Combines two records of the same person, retaining the most complete fields."""
    merged_roles = list(dict.fromkeys(base.roles + incoming.roles))  # union, preserving order
    return Academic(
        id=base.id,  # Preserve the canonical ID of the already-tracked record
        # Keep the longer/more complete name format (usually includes titles)
        name=(incoming.name if len(incoming.name or "") > len(base.name or "") else base.name),
        roles=merged_roles,
        # Merge optional fields by selecting the populated version
        affiliation=incoming.affiliation or base.affiliation,
        email=incoming.email or base.email,
        phone_number=incoming.phone_number or base.phone_number,
    )


def _title_preprocessor(s: str) -> str:
    """Removes common titles before fuzz matching."""
    if not s:
        return ""
    titles = [
        "mr.",
        "mrs.",
        "ms.",
        "dr.",
        "prof.",
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "hr.",
        "herr",
        "fr.",
        "frau",
    ]
    lowered = s.lower()
    for title in titles:
        # Pad with spaces to prevent accidental partial-word clipping
        lowered = f" {lowered} ".replace(f" {title} ", " ")
    return lowered.strip()


def _advanced_name_match(name1: str, name2: str, threshold: float = 90.0) -> bool:
    """
    Uses Token Set Ratio to calculate a similarity percentage out of 100.
    """
    # token_set_ratio is perfect for matching subsets like "Doe" vs "John Doe"
    score = fuzz.token_set_ratio(name1, name2, processor=_title_preprocessor)
    return score >= threshold


def _normalize_string(val: str | None) -> str | None:
    """Helper to clean string metadata for safer comparison."""
    return val.strip().lower() if val else None


def _store_academics(academics: list[Academic]) -> tuple[list[Academic], dict[str, str]]:
    """Merge incoming academics with academics already stored in MongoDB (to avoid duplicates),
    upsert only the new/changed records, and return just the incoming academcis in their
    consolidated forms."""
    existing_academics = [
        Academic(
            id=doc["id"],
            name=doc.get("name") or "",
            roles=doc.get("role") or [],
            affiliation=doc.get("affiliation"),
            email=doc.get("email"),
            phone_number=doc.get("phone_number"),
        )
        for doc in academics_collection.find({})
    ]

    stored: dict[str, Academic] = {a.id: a for a in existing_academics}
    touched_ids: list[str] = []
    touched_set: set[str] = set()
    academic_id_map: dict[str, str] = {}

    for incoming in academics:
        if not incoming.name:
            continue

        matched_id = None
        inc_email = _normalize_string(incoming.email)
        inc_phone = _normalize_string(incoming.phone_number)

        for existing_id, base in stored.items():
            base_email = _normalize_string(base.email)
            base_phone = _normalize_string(base.phone_number)

            if (
                (inc_email and base_email and inc_email == base_email)
                or (inc_phone and base_phone and inc_phone == base_phone)
                or (_advanced_name_match(base.name, incoming.name))
            ):
                matched_id = existing_id
                break

        if matched_id:
            stored[matched_id] = _merge_academics(stored[matched_id], incoming)
        else:
            matched_id = incoming.id
            stored[matched_id] = incoming

        academic_id_map[incoming.id] = matched_id

        if matched_id not in touched_set:
            touched_ids.append(matched_id)
            touched_set.add(matched_id)

    for academic_id in touched_ids:
        academic = stored[academic_id]
        academics_collection.update_one(
            {"id": academic.id},
            {
                "$set": {
                    "name": academic.name,
                    "role": academic.roles,
                    "affiliation": academic.affiliation,
                    "email": academic.email,
                    "phone_number": academic.phone_number,
                }
            },
            upsert=True,
        )

    return [stored[academic_id] for academic_id in touched_ids], academic_id_map


def _consolidate_academics(academics: list[Academic]) -> tuple[list[Academic], dict[str, str]]:
    """Deduplicate academics and map each incoming ID to its consolidated ID."""
    unique_academics: dict[str, Academic] = {}
    academic_id_map: dict[str, str] = {}

    for incoming in academics:
        if not incoming.name:
            continue

        matched = False
        matched_id = incoming.id
        inc_email = _normalize_string(incoming.email)
        inc_phone = _normalize_string(incoming.phone_number)

        for base_id, base in unique_academics.items():
            base_email = _normalize_string(base.email)
            base_phone = _normalize_string(base.phone_number)

            if (
                (inc_email and base_email and inc_email == base_email)
                or (inc_phone and base_phone and inc_phone == base_phone)
                or (_advanced_name_match(base.name, incoming.name))
            ):
                unique_academics[base_id] = _merge_academics(base, incoming)
                matched_id = base_id
                matched = True
                break

        if not matched:
            unique_academics[incoming.id] = incoming
        academic_id_map[incoming.id] = matched_id

    return list(unique_academics.values()), academic_id_map


def _persist_document_academic_ids(
    document_academic_ids: dict[str, list[str]],
    consolidated_academic_ids: dict[str, str],
    stored_academic_ids: dict[str, str],
) -> None:
    """Write canonical academic IDs back to the documents they were extracted from."""
    for filepath, extracted_ids in document_academic_ids.items():
        canonical_ids = list(
            dict.fromkeys(
                stored_academic_ids[consolidated_academic_ids[academic_id]]
                for academic_id in extracted_ids
                if academic_id in consolidated_academic_ids
                and consolidated_academic_ids[academic_id] in stored_academic_ids
            )
        )
        documents_collection.update_one({"filepath": filepath}, {"$set": {"academic_ids": canonical_ids}})


def load_thesis_artifacts(input_folder: str, output_folder: str, litellm_virtual_key: str) -> dict:
    """
    Load the thesis artifacts of a given directory into a MongoDB vector store.

    Args:
        input_folder (str): The path to the folder containing the thesis artifacts to be loaded into the vector store.
        output_folder (str): The path to the folder where the vector store will be saved after loading the thesis artifacts.

    Returns:
        dict: A dictionary containing the results of the loading process, including counts of files touched, mirrored, deleted, converted, loaded, and academics stored.
    """

    _create_extractors_and_embeddings(litellm_virtual_key)

    touched_count, mirrored_count, deleted_count = _mirror_directory(input_folder, output_folder)

    created_count = _create_doclings(output_folder)

    loaded_count, academics, document_academic_ids = _load_docling_documents(output_folder)

    academics, consolidated_academic_ids = _consolidate_academics(academics)

    academics, stored_academic_ids = _store_academics(academics)

    _persist_document_academic_ids(document_academic_ids, consolidated_academic_ids, stored_academic_ids)

    return {
        "files_touched": touched_count,
        "files_mirrored": mirrored_count,
        "files_deleted": deleted_count,
        "files_converted": created_count,
        "files_loaded": loaded_count,
        "academics_count": len(academics),
    }


@app.command()
def main() -> None:
    """Load the thesis artifacts of a given directory into a MongoDB vector store."""
    console.print("[dim]Initializing extractors...[/dim]", highlight=False)

    litellm_virtual_key = (
        os.getenv("SK_DEVELOPMENT", "sk-development-pb") if PYTHON_ENV == "development" else os.getenv("SK_LITELLM")
    )

    _create_extractors_and_embeddings(litellm_virtual_key)

    console.print("[dim]Mirroring input directory to output directory...[/dim]", highlight=False)

    touched_count, mirrored_count, deleted_count = _mirror_directory(INPUT_DIR, OUTPUT_DIR)

    console.print(
        f"[bold green]✓ Done. {touched_count} file{'' if touched_count == 1 else 's'} touched, "
        f"{mirrored_count} file{'' if mirrored_count == 1 else 's'} mirrored, and {deleted_count} file{'' if deleted_count == 1 else 's'} deleted.[/bold green]"
    )

    console.print("[dim]Creating Docling JSON files...[/dim]", highlight=False)

    created_count = _create_doclings(OUTPUT_DIR)

    console.print(
        f"[bold green]✓ Done. {created_count} file{'' if created_count == 1 else 's'} converted to Docling format.[/bold green]"
    )

    console.print("[dim]Loading Docling JSON files into MongoDB...[/dim]", highlight=False)

    loaded_count, academics, document_academic_ids = _load_docling_documents(OUTPUT_DIR)

    console.print(
        f"[bold green]✓ Done. {loaded_count} file{'' if loaded_count == 1 else 's'} loaded into MongoDB with chunks and embeddings.[/bold green]"
    )

    academics, consolidated_academic_ids = _consolidate_academics(academics)

    # for academic in academics:
    #     console.print(f"[dim]ACADEMIC[/dim]: {academic.model_dump()}")

    academics, stored_academic_ids = _store_academics(academics)

    _persist_document_academic_ids(document_academic_ids, consolidated_academic_ids, stored_academic_ids)

    console.print(
        f"[bold green]✓ Done. {len(academics)} unique academic{'' if len(academics) == 1 else 's'} stored in MongoDB.[/bold green]"
    )


if __name__ == "__main__":
    main()
