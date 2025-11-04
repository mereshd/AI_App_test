BEGIN;
-- WE need more memory to actually create this index!
SET LOCAL maintenance_work_mem = '128MB';
CREATE INDEX ivff_index
  ON rag_content USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
COMMIT;
