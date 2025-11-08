EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM rag_content
ORDER BY embedding <-> (SELECT embedding FROM rag_content LIMIT 1) -- or <-> / <#> depending on your metric
LIMIT 10;