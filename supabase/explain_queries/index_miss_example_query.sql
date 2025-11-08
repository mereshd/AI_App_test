EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM rag_content
WHERE embedding <=> (SELECT embedding FROM rag_content LIMIT 1) >= 0.5 -- or <-> / <#> depending on your metric
LIMIT 10;