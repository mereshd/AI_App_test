# App Supabase + Pubnub + Render

An application boilerplate with Pubnub, Supabase database, and Render deployment configuration.

## Project Structure

```
ai-application-october-2025/
├── .env.example
├── .gitignore
├── README.md
├── data/
│   └── synthetic_profiles.json
├── main.py
├── render.yaml
├── requirements.txt
└── templates/
    ├── chat.html
    ├── index.html
    ├── pingpong.html
    └── resume.html
```

## Prerequisites

- Python 3.11+
- A Supabase account and project
- A Render account (for deployment)

## Local Development Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd base-app
```

### 2. Set up Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Create a table called `items` in your Supabase database:
   ```sql
   CREATE TABLE items (
     id SERIAL PRIMARY KEY,
     name TEXT,
     created_at TIMESTAMP DEFAULT NOW()
   );
   ```
3. Insert some test data:
   ```sql
   INSERT INTO items (name) VALUES ('Test Item 1'), ('Test Item 2');
   ```
4. Get your Supabase URL and anon key from Project Settings > API

### 3. Backend Setup

```bash
# Create and activate virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your Supabase credentials

# Run the application
uvicorn main:app --reload --port 8000
```

The application will be available at http://localhost:8000

## Environment Variables
```
SUPABASE_URL=https://example.supabase.co
SUPABASE_KEY=
OPENAI_API_KEY=
PUBNUB_PUBLISH_KEY=demo
PUBNUB_SUBSCRIBE_KEY=demo
```

## Deployment to Render

### Deploy Web Service

1. Push your code to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click "New" > "Web Service"
4. Connect your repository
5. Configure:
   - Name: `ai-application-october-2025`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `OPENAI_API_KEY`
   - `PUBNUB_PUBLISH_KEY`
   - `PUBNUB_SUBSCRIBE_KEY`

The entire application is now served from a single web service!

## API Endpoints

- `/chat` - For chatbot
- `/pingpong` - For Pubnub testing

## License

MIT
