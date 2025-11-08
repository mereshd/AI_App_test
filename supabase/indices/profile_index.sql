CREATE INDEX profile_hnsw_index ON rag_content USING hnsw (embedding vector_cosine_ops)
WHERE document_type = 'profile';