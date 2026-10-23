// Setup script for the tectora database.
// Run with: mongosh "mongodb://localhost:27020/?directConnection=true" setup.js

use("tectora");

const DOCUMENTS_COLLECTION = "documents";
const DOCUMENT_CHUNKS_COLLECTION = "document_chunks";
const ACADEMICS_COLLECTION = "academics";
const DOCLING_FILES_BUCKET = "docling_files";

const DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX =
  "document_text_summaries_vector_index";
const DOCUMENT_CHUNKS_VECTOR_INDEX = "document_chunks_vector_index";

const EMBEDDING_DIMENSIONS = 1536;

// ── Collections ───────────────────────────────────────────────────────────────

db.createCollection(DOCUMENTS_COLLECTION);
db.createCollection(DOCUMENT_CHUNKS_COLLECTION);
db.createCollection(ACADEMICS_COLLECTION);

// GridFS bucket for docling JSON exports, which can exceed MongoDB's 16 MB document limit.
db.createCollection(`${DOCLING_FILES_BUCKET}.files`);
db.createCollection(`${DOCLING_FILES_BUCKET}.chunks`);

print("Collections created.");

// ── Regular indexes ───────────────────────────────────────────────────────────

// Unique index on filepath so upserts are always idempotent.
db.documents.createIndex(
  { filepath: 1 },
  { unique: true, name: "documents_filepath_unique" },
);

// Non-unique index on filepath for fast delete_many() before chunk re-insertion.
db.document_chunks.createIndex(
  { filepath: 1 },
  { name: "document_chunks_filepath" },
);

// Supports filtering $vectorSearch results by category.
db.document_chunks.createIndex(
  { category: 1 },
  { name: "document_chunks_category" },
);

// Unique academics id index for deterministic upserts.
db.academics.createIndex(
  { id: 1 },
  { unique: true, name: "academics_id_unique" },
);

// Non-unique index on filename for fast lookup/delete before re-inserting a docling JSON GridFS file.
db.getCollection(`${DOCLING_FILES_BUCKET}.files`).createIndex(
  { filename: 1 },
  { name: "docling_files_filename" },
);

print("Regular indexes created.");

// ── Vector Search indexes ─────────────────────────────────────────────────────

db.documents.createSearchIndex({
  name: DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX,
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "text_summary_embedding",
        numDimensions: EMBEDDING_DIMENSIONS,
        similarity: "cosine",
      },
    ],
  },
});

db.document_chunks.createSearchIndex({
  name: DOCUMENT_CHUNKS_VECTOR_INDEX,
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: EMBEDDING_DIMENSIONS,
        similarity: "cosine",
      },
    ],
  },
});

print("Vector Search index submitted.");

/*
Check status with:
  print(
    `db.documents.getSearchIndexes("${DOCUMENT_TEXT_SUMMARIES_VECTOR_INDEX}")`,
  );
  print(`db.document_chunks.getSearchIndexes(${DOCUMENT_CHUNKS_VECTOR_INDEX})`);
*/

print('Wait until status is "READY" before running vector queries.');
