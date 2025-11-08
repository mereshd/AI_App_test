-- Create a function to search for documents using cosine similarity
-- This function takes a query embedding and returns the top N most similar documents

create or replace function match_documents(
  query_embedding vector(1536),
  match_count int default 10
)
returns table (
  id text,
  context text,
  user_id int,
  document_type text,
  similarity float
)
language sql stable
as $$
  select
    id,
    context,
    user_id,
    document_type,
    1 - (embedding <=> query_embedding) as similarity
  from rag_content
  order by embedding <=> query_embedding
  limit match_count;
$$;
