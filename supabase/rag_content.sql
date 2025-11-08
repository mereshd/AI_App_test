CREATE TABLE rag_content (
   id TEXT PRIMARY KEY,
   embedding VECTOR(1536) NOT NULL,
   context TEXT NOT NULL,
   user_id INTEGER NOT NULL,
   document_type TEXT NOT NULL,
   document_id TEXT,
   username TEXT
)