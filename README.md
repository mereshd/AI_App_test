# Hello World App - htmx + FastAPI + Supabase

A full-stack application boilerplate with htmx frontend, FastAPI backend, Supabase database, and Render deployment configuration.

## Project Structure

```
base-app/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   ├── templates/
│   │   └── index.html      # Main htmx template
│   └── .env.example        # Environment variables template
├── frontend/
│   └── README.md           # Frontend documentation
├── render.yaml             # Render deployment config
└── README.md
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

### Backend (.env)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

## Deployment to Render

### Deploy Web Service

1. Push your code to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click "New" > "Web Service"
4. Connect your repository
5. Configure:
   - Name: `htmx-fastapi-app`
   - Runtime: `Python 3`
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`

The entire application (frontend + backend) is now served from a single web service!

## API Endpoints

- `GET /` - Main application page (HTML)
- `GET /api/health` - Health check (JSON)
- `GET /api/message` - Backend message (HTML fragment)
- `GET /api/data` - Fetch data from Supabase (HTML fragment)

## Features

- htmx for dynamic content without full page reloads
- FastAPI backend serving HTML templates with Jinja2
- Supabase integration for database
- No build process required - simple deployment
- Single service deployment (no separate frontend/backend)
- Much smaller footprint than React (htmx is ~14KB vs React ~140KB)

## Benefits of htmx over React

- **Simpler**: No complex build tooling, bundlers, or transpilers
- **Smaller**: Dramatically reduced bundle size
- **Faster**: Server-rendered HTML loads instantly
- **Easier to deploy**: Single service instead of two
- **Lower cost**: One Render service instead of two
- **More maintainable**: Less JavaScript, more HTML

## Next Steps

- Add authentication with Supabase Auth
- Implement CRUD operations with htmx forms
- Add proper error handling
- Add CSS framework (Tailwind, etc.)
- Add tests
- Configure CI/CD

## License

MIT
