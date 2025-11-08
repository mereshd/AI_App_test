# PubNub Job Processor

A Python service that listens to PubNub messages, processes job-related queries using OpenAI and Supabase, and publishes responses back to PubNub.

## Features

- **Real-time PubNub Integration**: Listens to job request messages on a configured channel
- **Intelligent Job Matching**: Queries job context from Supabase using embeddings and semantic search
- **AI-Powered Responses**: Processes queries using OpenAI's GPT-4 model
- **Persistent Storage**: Stores all responses in Supabase for future reference
- **Response Publishing**: Automatically publishes response references back to PubNub

## Architecture

```
PubNub (job-requests)
    ↓
Job Processor
    ↓
1. Query Job Context (Supabase + Embeddings)
    ↓
2. Process with OpenAI (GPT-4)
    ↓
3. Store Response (Supabase job_responses table)
    ↓
4. Publish Reference (PubNub job-responses)
```

## Setup

### 1. Install Dependencies

Ensure all required packages are installed:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Add the following to your `.env` file:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_api_key
PUBNUB_PUBLISH_KEY=your_pubnub_publish_key
PUBNUB_SUBSCRIBE_KEY=your_pubnub_subscribe_key
PUBNUB_JOB_CHANNEL=job-requests
PUBNUB_RESPONSE_CHANNEL=job-responses
```

### 3. Set Up Supabase

Run the migration to create the `job_responses` table:

```bash
# If using Supabase CLI
supabase db push

# Or manually run the migration file
# supabase/migrations/create_job_responses_table.sql
```

This creates:
- `job_responses` table with proper schema
- Indexes for optimal query performance
- RLS (Row Level Security) policies
- Auto-updating `updated_at` timestamp

### 4. Ensure Required Supabase Functions

The script requires the `match_documents_by_document_type` RPC function to exist in Supabase for semantic search. This should already be set up from existing migrations.

## Usage

### Running the Service

Start the PubNub job processor:

```bash
python pubnub_job_processor.py
```

The service will:
1. Connect to PubNub
2. Subscribe to the job requests channel
3. Listen for incoming messages
4. Process each message and publish responses

### Message Format

#### Input Message (Published to `job-requests` channel)

```json
{
  "request_id": "unique-request-id",
  "job_id": "job-123",
  "job_description": "Senior Data Engineer position...",
  "query": "What are the key responsibilities for this role?"
}
```

Fields:
- `request_id` (optional): Unique identifier for tracking the request
- `job_id` (optional): Direct job ID to query from Supabase
- `job_description` (optional): Job description for semantic search if job_id not provided
- `query` (required): The user's question about the job

#### Output Message (Published to `job-responses` channel)

```json
{
  "status": "success",
  "response_id": "uuid-of-stored-response",
  "job_id": "job-123",
  "request_id": "unique-request-id",
  "response": "The key responsibilities include...",
  "timestamp": "2025-10-30T12:34:56.789Z"
}
```

Or in case of error:

```json
{
  "status": "error",
  "error": "Error message",
  "request_id": "unique-request-id"
}
```

## Database Schema

### job_responses Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| job_id | TEXT | Job identifier |
| user_query | TEXT | Original user question |
| ai_response | TEXT | OpenAI generated response |
| metadata | JSONB | Additional metadata (similarity score, request_id, etc.) |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Record last update time |

## Testing

### Send a Test Message

You can test the service using the PubNub console or programmatically:

```python
from pubnub.pubnub import PubNub
from pubnub.pnconfiguration import PNConfiguration

pnconfig = PNConfiguration()
pnconfig.publish_key = "your-publish-key"
pnconfig.subscribe_key = "your-subscribe-key"
pnconfig.user_id = "test-client"

pubnub = PubNub(pnconfig)

# Send a test message
pubnub.publish()\
    .channel("job-requests")\
    .message({
        "request_id": "test-123",
        "job_id": "some-job-id",
        "query": "Tell me about this job"
    })\
    .sync()
```

### Monitor Responses

Subscribe to the response channel to see processed results:

```python
def response_callback(message):
    print(f"Response received: {message.message}")

pubnub.subscribe().channels("job-responses").execute()
```

## Logging

The service uses Python's built-in logging module. Logs include:
- Connection status
- Message processing events
- Errors and warnings
- Response publication confirmations

## Error Handling

The service handles various error scenarios:
- Missing environment variables
- Supabase connection errors
- OpenAI API errors
- PubNub connection issues
- Invalid message formats

All errors are logged and error responses are published to the response channel.

## Production Considerations

1. **Scaling**: Run multiple instances of the script for higher throughput
2. **Monitoring**: Set up logging aggregation and alerting
3. **Rate Limiting**: Implement rate limiting for OpenAI API calls
4. **Message Queuing**: Consider using PubNub's persistence features
5. **Security**: Use environment-specific keys and proper RLS policies

## Troubleshooting

### Service not receiving messages
- Check PubNub credentials
- Verify channel names match
- Ensure network connectivity

### OpenAI errors
- Verify API key is valid
- Check OpenAI account has credits
- Review rate limits

### Supabase errors
- Confirm database migrations are applied
- Check RLS policies allow the operations
- Verify service role key has proper permissions

## Contributing

When modifying the script:
1. Test with sample messages first
2. Update this documentation
3. Add appropriate error handling
4. Update logging statements

## License

See main project LICENSE file.
