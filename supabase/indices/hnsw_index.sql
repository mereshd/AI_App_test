CREATE INDEX hnsw_index ON rag_content USING hnsw (embedding vector_cosine_ops);
