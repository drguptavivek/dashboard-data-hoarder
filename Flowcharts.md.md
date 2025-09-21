# pg-sched — scheduled Postgres query runner + JSONB results API

pg-sched is a compact platform to **schedule SQL queries**, **store every run’s results**, and **serve them via a JSON API** for dashboards.

- Flask API (users/auth, data sources, queries CRUD, run browsing)
- Worker (APScheduler; cron/interval per query)
- Click CLI (keys, users, data sources, queries)
- RFC5424-style local logging with rotation, gzip, retention
- Passwords for external Postgres sources encrypted via **NaCl sealed boxes**

---

## Architecture (high level)

```mermaid
flowchart TD
  subgraph API["Flask API"]
    U[Users & Sessions]\n(bp_users.py)
    DS[Data Sources]\n(bp_conn.py)
    QCRUD[Queries CRUD]\n(bp_queries.py)
    RR[Runs & Results]\n(api.py)
  end

  subgraph Worker["Worker"]
    SCHED[APScheduler]
    EXEC[Query Executor]
  end

  subgraph AppDB["Postgres (App metadata)"]
    T1[(user_*)]
    T2[(data_source)]
    T3[(query_job)]
    T4[(query_run, query_run_blob)]
  end

  subgraph Src["External Postgres Sources"]
    PG1[(analytics)]
    PG2[(warehouse)]
  end

  API -->|SQLAlchemy| AppDB
  Worker -->|SQLAlchemy| AppDB
  EXEC -->|SELECT| Src
  QCRUD --> RR
  SCHED --> EXEC
```

---

## ER diagram

```mermaid
erDiagram
  data_source {
    int id PK
    string name
    string host
    int port
    string dbname
    string username
    bytes enc_password
    string enc_algo
    int key_version
    datetime created_at
    datetime updated_at
  }

  query_job {
    int id PK
    string name
    string title
    string description
    string sql_text
    int data_source_id FK
    string schedule_type
    string schedule_expr
    string timezone
    boolean enabled
    datetime created_at
    datetime updated_at
  }

  query_run {
    int id PK
    int query_id FK
    datetime scheduled_at
    string job_timezone
    datetime run_started_at
    datetime run_finished_at
    int duration_ms
    string status
    int rows_returned
    string error_message
  }

  query_run_blob {
    int run_id PK, FK
    string format
    json df_json
    int row_count
    int byte_size
  }

  user_account {
    int id PK
    string email
    string name
    string password_hash
    boolean is_active
    datetime created_at
    datetime updated_at
  }

  user_role {
    int user_id PK, FK
    string role PK
  }

  user_session {
    string id PK
    int user_id FK
    datetime created_at
    datetime last_seen_at
    datetime expires_at
    string ip
    string user_agent
    boolean is_revoked
  }

  %% Relationships
  data_source ||--o{ query_job : provides
  query_job ||--o{ query_run : has
  query_run ||--|| query_run_blob : has
  user_account ||--o{ user_role : has
  user_account ||--o{ user_session : has
```

---

## Flows

### 1) Login → Session → AuthZ

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant A as API (Flask)
  participant DB as App DB

  C->>A: POST /api/auth/login {email,password}
  A->>DB: SELECT user by email
  DB-->>A: user row + password_hash
  A-->>C: Set-Cookie: sid; {ok,user,roles}

  Note over C,A: Subsequent calls reuse sid cookie

  C->>A: GET /api/users/me
  A->>DB: validate session by sid
  DB-->>A: session + user + roles
  A-->>C: {authenticated:true,user,roles}

  C->>A: GET /api/admin/queries
  A->>DB: check role editor/admin
  DB-->>A: ok
  A-->>C: items...
```

### 2) Admin creates Data Source and Query → Worker executes → Dashboard reads latest

```mermaid
flowchart TD
  A1[POST /api/datasources<br/>encrypt with public key] --> D1[(data_source.enc_password)]
  A2[POST /api/admin/queries] --> D2[(query_job)]
  subgraph Worker
    W0[load enabled query_job] --> W1[resolve data_source]
    W1 -->|decrypt with private key| W2[build DSN]
    W2 --> W3[run SELECT on source DB]
    W3 --> W4[(query_run)]
    W4 --> W5[(query_run_blob JSONB)]
  end
  A2 --> W0
  D1 --> W1
  D2 --> W0
  subgraph Read
    R1[GET /api/queries/:id/runs/latest] --> R2[(query_run + blob)]
  end
  W5 --> R2
```

### 3) Dry-run (no persistence)

```mermaid
sequenceDiagram
  autonumber
  participant E as Editor/Admin
  participant A as API
  participant DB as App DB
  participant S as Source PG

  E->>A: POST /api/admin/queries/:id/test {limit,timeout_ms}
  A->>DB: load query_job + data_source
  A->>DB: read enc_password
  A->>A: decrypt with private key
  A->>S: open connection (optional statement_timeout)
  A->>S: SELECT wrapped with LIMIT
  S-->>A: rows
  A-->>E: {ok:true,columns,row_count,rows,timing_ms}
```

### 4) APScheduler scheduling and execution

```mermaid
flowchart TD
  S0[start scheduler] --> S1[list enabled queries]
  S1 --> S2{schedule_type}
  S2 -- cron --> S3[CronTrigger]
  S2 -- interval --> S4[IntervalTrigger]
  S3 --> S5[add_job execute_job]
  S4 --> S5
  S5 --> S6[on trigger: execute_job]
  S6 --> S7[record run start]
  S7 --> S8[decrypt DSN]
  S8 --> S9[exec SELECT]
  S9 --> S10[save JSONB result]
  S10 --> S11[record success]
  S9 -- error --> S12[record error]
```

### 5) Key rotation via CLI

```mermaid
flowchart TD
  K0[cli keys rotate] --> K1[pg_dump metadata DB]
  K1 --> K2[load new public/private key]
  K2 --> K3[for each data_source]
  K3 --> K4[decrypt current enc_password]
  K4 --> K5[encrypt with new public key]
  K5 --> K6[update enc_password,key_version]
  K6 --> K7[test connections]
  K7 --> K8[done]
```

### 6) RFC-style logging with rotation/gzip/retention

```mermaid
flowchart TD
  L0[emit log record] --> L1[RFC5424 formatter]
  L1 --> L2[file handler: pgsched-*.log]
  L2 --> L3[daily rotation]
  L3 --> L4{age > GZIP_AFTER_DAYS?}
  L4 -- yes --> L5[gzip old files]
  L5 --> L6{age > KEEP_DAYS?}
  L4 -- no --> L6
  L6 -- yes --> L7[delete]
  L6 -- no --> L8[keep]
```

### 7) Run history navigation

```mermaid
sequenceDiagram
  autonumber
  participant U as Client
  participant A as API
  participant DB as App DB

  U->>A: GET /api/queries/:id/runs/latest
  A->>DB: select last run + blob
  DB-->>A: run + JSONB
  A-->>U: result

  U->>A: GET /api/queries/:id/runs/:rid/prev
  A->>DB: select id < rid order by id desc limit 1
  DB-->>A: prev_run_id
  A-->>U: {id,_link}

  U->>A: GET /api/runs/:run_id
  A->>DB: select run + blob
  DB-->>A: run + JSONB
  A-->>U: result
```

---

## Notes for GitHub Mermaid

- Use triple backticks with the word `mermaid` right after, like:
  \`\`\`mermaid
  ...diagram...
  \`\`\`
- Stick to simple types/keywords (e.g., `int`, `string`, `boolean`, `datetime`, `json`) in ERD.
- Avoid quotes or extra comments inside ER blocks.
- For flowcharts, use `flowchart TD` or `flowchart LR`. For sequences, use `sequenceDiagram`.

