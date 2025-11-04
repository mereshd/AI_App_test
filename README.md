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

### 1. Private Fork Setup

#### Step 1: Create a bare clone
```bash

git clone --bare git@github.com:DataExpert-io/ai-application-october-2025.git
cd ai-application-october-2025/

```

#### Step 2: Create a new private repository on GitHub
Go to [github.com/new](https://github.com/new), name it `ai-application-october-2025-app`, select **Private**, and create it.

#### Step 3: Mirror-push to your private repo
```bash
cd ai-application-october-2025.git
git push --mirror git@github.com:<your_username>/ai-application-october-2025-app.git
cd ..
rm -rf ai-application-october-2025.git
```

#### Step 4: Clone your private repo
```bash
git clone git@github.com:<your_username>/ai-application-october-2025-app.git
cd ai-application-october-2025-app
```

#### Step 5: Add upstream for updates
```bash
git remote add upstream git@github.com:DataExpert-io/ai-application-october-2025.git
git remote set-url --push upstream DISABLE
```

**Update from upstream**: `git fetch upstream && git rebase upstream/main`

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
Final refresh trigger
