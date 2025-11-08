CREATE TABLE resumes (
  resume_id BIGSERIAL PRIMARY KEY,
  resume JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  -- Handy generated columns (optional but great for filtering)
  name TEXT GENERATED ALWAYS AS (resume->>'name') STORED,
  location TEXT GENERATED ALWAYS AS (resume->'contact_information'->>'location') STORED,
  
  -- Minimal structural checks (tune to your tolerance)
  CONSTRAINT resume_has_name CHECK (
    resume ? 'name' AND jsonb_typeof(resume->'name') = 'string'
  ),
  CONSTRAINT resume_has_prof_summary CHECK (
    resume ? 'professional_summary' AND jsonb_typeof(resume->'professional_summary') = 'string'
  ),
  CONSTRAINT resume_arrays_types_ok CHECK (
    (NOT (resume ? 'work_experience') OR jsonb_typeof(resume->'work_experience') = 'array') AND
    (NOT (resume ? 'education') OR jsonb_typeof(resume->'education') = 'array') AND
    (NOT (resume ? 'skills') OR jsonb_typeof(resume->'skills') = 'array') AND
    (NOT (resume ? 'certifications') OR jsonb_typeof(resume->'certifications') = 'array') AND
    (NOT (resume ? 'projects') OR jsonb_typeof(resume->'projects') = 'array')
  )
);
