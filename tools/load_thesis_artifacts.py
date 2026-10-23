import os
import sys
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

sys.path.append(str(Path(__file__).resolve().parent.parent))

INPUT_DIR = os.getenv("INPUT_DIR")
OUTPUT_DIR = os.getenv("OUTPUT_DIR")


class ThesisArtifactsLoadingResult(BaseModel):
    files_touched: int = Field(
        description="The number of files in the input folder that were touched during the loading process."
    )
    files_mirrored: int = Field(
        description="The number of files that were mirrored to the output folder during the loading process."
    )
    files_deleted: int = Field(
        description="The number of files that were deleted from the input folder during the loading process."
    )
    files_converted: int = Field(
        description="The number of files that were converted to Docling format during the loading process."
    )
    files_loaded: int = Field(
        description="The number of files that were successfully loaded into the MongoDBvector store during the loading process."
    )
    academics_count: int = Field(
        description="The number of academics that were stored in the MongoDB vector store during the loading process."
    )


@tool(
    description=("Load the thesis artifacts of a given directory into a MongoDB vector store."),
)
def load_thesis_artifacts(
    config: RunnableConfig,
) -> dict:
    """
    Load the thesis artifacts of a given directory into a MongoDB vector store.

    Args:
        config (RunnableConfig): The configuration object containing the necessary parameters for the loading process.
    Returns:
        dict: A dictionary containing the results of the loading process, including counts of files touched, mirrored, deleted, converted, loaded, and academics stored.
    """
    thesis_artifacts_loading_result_schema = ThesisArtifactsLoadingResult.model_json_schema()["properties"]

    litellm_virtual_key = config.get("configurable", {}).get("litellm_virtual_key")

    if not isinstance(litellm_virtual_key, str) or not litellm_virtual_key:
        raise ValueError("Missing LiteLLM virtual key in RunnableConfig")

    from scripts.load_thesis_artifacts import load_thesis_artifacts

    thesis_artifacts = load_thesis_artifacts(
        input_folder=INPUT_DIR, output_folder=OUTPUT_DIR, litellm_virtual_key=litellm_virtual_key
    )

    thesis_artifacts_loading_result = ThesisArtifactsLoadingResult(**thesis_artifacts)

    self_documenting_payload = {
        "data": thesis_artifacts_loading_result.model_dump(),
        "field_semantics_reference": thesis_artifacts_loading_result_schema,
    }

    return self_documenting_payload
