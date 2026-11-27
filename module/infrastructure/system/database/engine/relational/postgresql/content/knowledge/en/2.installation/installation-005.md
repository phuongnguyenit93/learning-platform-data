# Setting Up a Practice Environment with Docker Compose and Persistent Volumes for PostgreSQL

When learning PostgreSQL, installing directly on your host machine can introduce several issues: a project's PostgreSQL version may differ from the one you are studying; the default port `5432` may already be occupied by another app; test configs and data can mix with real databases; or learners delete a container and assume the data is gone too. **Docker Compose** lets you describe a reproducible PostgreSQL environment in a single YAML file, while **Docker volumes** store data independently of the container lifecycle.

This lesson builds a dedicated practice PostgreSQL setup featuring:

- A `db` service using the official PostgreSQL image pinned to a major version.
- User, password, and database initialized from environment variables.
- Host access bound to `127.0.0.1` to avoid accidentally exposing the database to external networks.
- A **named volume** storing `PGDATA` so data persists after stopping or recreating the container.
- A healthcheck and a directory of SQL scripts that run only on first-time data initialization.
- Verification commands: creating a table, writing data, running `docker compose down`, `up`, and reading the data back.

Examples use the `postgres:16` image to keep the internal data path consistent. When using a different major version—especially PostgreSQL 18 or later—**do not blindly copy the mount path**, because `PGDATA` layout inside the official image can change.

## 1. How Do Docker, Images, Containers, Compose, and Volumes Differ?

| Concept | Meaning | Relation to This Lesson |
| --- | --- | --- |
| **Image** | Template containing minimal OS, PostgreSQL, and entrypoint scripts | `postgres:16` |
| **Container** | A running process/environment instantiated from an image | Container running PostgreSQL |
| **Docker Compose** | Tool defining multiple Docker resources in a YAML file | `compose.yaml` defines `db` and volume |
| **Named volume** | Storage area managed by Docker, surviving beyond container lifecycle | `pgdata` holds PostgreSQL data |
| **Bind mount** | Maps a host directory/file path into the container | `./init` holds initialization SQL |
| **PGDATA** | Data directory used by the PostgreSQL server | `/var/lib/postgresql/data` in the `postgres:16` image |

Visualizing the relationship:

~~~text
Host running Docker
│
├── Project directory postgres-lab/
│   ├── compose.yaml
│   ├── .env
│   └── init/
│       └── 01_schema.sql
│
├── Docker Compose project
│   └── Service db
│       └── Container running PostgreSQL 16
│           ├── port 5432 inside container
│           ├── /var/lib/postgresql/data     ← named volume pgdata
│           └── /docker-entrypoint-initdb.d  ← bind mount ./init
│
└── Docker volume pgdata
    └── Database files, WAL, catalogs, table data...
~~~

**Core principle:** a container can be deleted and recreated, yet the named volume remains until explicitly removed or lost to storage failure. When a new container mounts the **same volume**, PostgreSQL sees the existing data state instead of initializing a fresh cluster.

### Why Not Store Data Only in the Container Filesystem?

If data resides solely in the container's writable layer, replacing the container will not carry those files over. PostgreSQL is a stateful database engine, so its data path must be backed by storage with an independent lifecycle.

A Docker volume solves **persistence across container replacements**, but it **does not replace backups**. Accidentally dropping tables, disk corruption, host loss, or data corruption inside the volume can still cause data loss.

## 2. Prerequisites

You need:

1. Docker Engine or Docker Desktop installed and running.
2. The Docker Compose plugin supporting `docker compose` (with a space, not necessarily legacy `docker-compose`).
3. Permission to run Docker in your practice environment.
4. Port `5433` on the host unoccupied by another application.
5. Sufficient disk space for images, volumes, and test data.

Verify:

~~~bash
docker --version
docker compose version
docker info
~~~

`docker info` communicates with the Docker daemon. If Docker Desktop is not running or your account lacks Docker permissions, this command may fail even if the CLI binary is installed.

Commands can be executed in a Linux/macOS terminal, PowerShell, or an IDE's integrated terminal if Docker is properly configured. Examples using `docker compose` and `docker exec` do not depend specifically on Bash, though host path syntax and file management may vary across operating systems.

## 3. Creating the Project Structure

Create a dedicated directory, e.g., `postgres-lab`, containing:

~~~text
postgres-lab/
├── compose.yaml
├── .env
├── .gitignore
└── init/
    └── 01_schema.sql
~~~

`compose.yaml` declares Docker resources; `.env` stores configuration values for the learning environment; `init/01_schema.sql` contains SQL statements executed automatically when initializing the data cluster for the first time.

Your working directory matters: all `docker compose ...` commands below are run from **`postgres-lab/`**, where `compose.yaml` lives. If running from elsewhere, pass `-f` or switch to the project directory.

### The compose.yaml File

~~~yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped

    environment:
      POSTGRES_USER: "${POSTGRES_USER:-lab_user}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
      POSTGRES_DB: "${POSTGRES_DB:-lab_db}"
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"

    ports:
      - "127.0.0.1:5433:5432"

    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d:ro

    healthcheck:
      test:
        - CMD-SHELL
        - 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s

volumes:
  pgdata:
~~~

No `version:` key is required in the modern Compose format; Compose follows the current specification and some versions emit warnings when encountering a legacy `version` field.

### The .env File

~~~dotenv
POSTGRES_USER=lab_user
POSTGRES_PASSWORD=replace_with_a_long_random_local_secret
POSTGRES_DB=lab_db
~~~

**Always replace** `replace_with_a_long_random_local_secret` with a sufficiently strong practice password before running. Never use that placeholder as a password for a real system.

Compose uses `.env` for **variable interpolation** inside `compose.yaml`. `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` are then passed into the container via `environment`.

In Compose, `${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}` requires a non-empty value; if missing or empty, Compose aborts with an error message instead of initializing an account without a password.

Notes:

- `.env` is convenient for **local learning environments**, not a dedicated secret store. Anyone with permission to inspect Docker configs or containers can read environment variables.
- Shell environment variables can **override values interpolated from `.env`** depending on Compose precedence rules. If configuration differs from expected, check variables set in your terminal.
- Never commit real passwords to Git, and never share screenshots or outputs containing secrets publicly.

### The .gitignore File

~~~gitignore
.env
*.dump
*.backup
*.sql.gz
~~~

`.gitignore` prevents Git from tracking these files if untracked; it **does not protect secrets already committed in past commits**. For Git-tracked projects, provide a `.env.example` without real passwords to guide setup.

## 4. Understanding Each Section of compose.yaml

### 4.1. services.db and image

~~~yaml
services:
  db:
    image: postgres:16
~~~

`db` is the **service name** in Compose, not the PostgreSQL database name. Inside the shared private network of the same Compose project, other services can connect to hostname `db` on port `5432`.

`postgres:16` pins **major version 16** so subsequent image pulls do not jump automatically to PostgreSQL 17 or 18. However, this tag still receives newer patch releases on the 16 branch. For environments requiring byte-for-byte reproducibility, pin the image by digest and maintain a security update plan.

**Never simply change `postgres:16` to `postgres:17` or `postgres:18` and reuse PostgreSQL 16 PGDATA.** Physical PostgreSQL data files cannot be upgraded across major versions merely by swapping the image; a proper upgrade procedure such as `pg_upgrade` or dump/restore is required.

### 4.2. POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB

The official PostgreSQL image accepts initialization variables:

| Variable | Role When Initializing a New Cluster |
| --- | --- |
| `POSTGRES_USER` | Name of the initial PostgreSQL role with **superuser** privileges |
| `POSTGRES_PASSWORD` | Password for the initial role |
| `POSTGRES_DB` | Name of the database created at initialization |
| `POSTGRES_INITDB_ARGS` | Options passed to `initdb` during first initialization |

In this example, the image creates role `lab_user` and database `lab_db`. **`lab_user` is a superuser** because it is the image's bootstrap role, making this setup suitable strictly for learning. In real systems, create dedicated least-privilege application roles and never let applications connect as the bootstrap superuser.

`POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"` selects UTF-8 and the C locale when creating the cluster. The C locale uses simple byte-order sorting rather than Vietnamese linguistic rules; depending on your use case, choose another locale supported by the image.

**Initialization variables do not re-run when the volume already contains a PostgreSQL cluster.** If days later you change `POSTGRES_DB` from `lab_db` to `other_db`, the image will not automatically create the new database on an already initialized volume. To add another database to an existing cluster, run `CREATE DATABASE` inside PostgreSQL. Changing the password in `.env` also **does not update the password** of an existing role; use `ALTER ROLE` via an authorized account when needed.

### 4.3. ports and Connecting from the Host

~~~yaml
ports:
  - "127.0.0.1:5433:5432"
~~~

The syntax breaks down as:

~~~text
127.0.0.1 : 5433 : 5432
   │         │       │
   │         │       └── PostgreSQL port inside the container
   │         └────────── port published on the host
   └──────────────────── host network interface address
~~~

As a result:

- Tools on the **host machine** can connect to `127.0.0.1:5433`.
- PostgreSQL inside the container still listens on port `5432`.
- Specifying `127.0.0.1` binds the published port strictly to loopback, preventing accidental exposure on all network interfaces.

Do not confuse `127.0.0.1` inside an application container with `127.0.0.1` on the host: inside a container, `localhost` refers to that container itself. If an application service runs in the **same Compose network**, it typically connects to `db:5432` rather than `127.0.0.1:5433`.

### 4.4. volumes: Named Volume for Data

~~~yaml
volumes:
  - pgdata:/var/lib/postgresql/data
~~~

In the official PostgreSQL 16 image, `/var/lib/postgresql/data` is the default data path configured by the image. `pgdata` on the left is the **Docker-managed named volume**; the right side is the path inside the container.

At the bottom of the file:

~~~yaml
volumes:
  pgdata:
~~~

Compose declares a volume resource named `pgdata`. Its actual name in Docker is usually prefixed with the **Compose project name**, such as `postgres-lab_pgdata`. The project name normally derives from the directory name unless explicitly overridden.

**Consequence:** if you copy the folder elsewhere and run it under a different project name, Compose may create a **new volume**; your old data is not deleted—it sits in the volume belonging to the old project. This is a common reason learners think data was lost after renaming a directory.

### 4.5. Bind Mount for Initialization Scripts

~~~yaml
volumes:
  - ./init:/docker-entrypoint-initdb.d:ro
~~~

`./init` is a host directory mounted into `/docker-entrypoint-initdb.d` inside the container. The `:ro` suffix mounts it read-only for the container.

The official PostgreSQL image entrypoint automatically executes matching initialization files in this directory **when the cluster is created for the first time**. Typically this includes `.sql`, `.sql.gz`, and `.sh` shell scripts following the image's conventions.

If PGDATA already contains data, these scripts **do not re-run** when you run `docker compose restart` or `up --force-recreate`. Therefore, `init` is suitable for **bootstrapping lab data**, not as an automated migration tool for running databases.

### 4.6. Healthcheck

~~~yaml
healthcheck:
  test:
    - CMD-SHELL
    - 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
  interval: 5s
  timeout: 3s
  retries: 10
  start_period: 10s
~~~

`pg_isready` checks whether PostgreSQL is accepting connections. `$$POSTGRES_USER` and `$$POSTGRES_DB` in Compose use **double dollar signs** to prevent Compose from interpolating them on the host, so the shell inside the container expands the actual environment variables.

Healthchecks help distinguish between:

- The container having been created/started.
- PostgreSQL inside being ready to accept connections.

However, **`healthy` does not prove passwords are correct, schema migrations are complete, or application queries will succeed**. `pg_isready` checks connection readiness, not full functional health.

## 5. Creating a First-Time Initialization SQL Script

The `init/01_schema.sql` file:

~~~sql
CREATE TABLE lab_entries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lab_entries (note)
VALUES ('Data from first-time init script');
~~~

This is a simple table to prove the initialization script ran. When the volume is empty, the entrypoint initializes the cluster, creates the `lab_db` database, and executes the SQL script inside that newly created database. Initially there will be one row.

In exercise environments, init scripts help everyone start from the same baseline. In long-lived projects, evolving schemas across versions requires a migration tool such as Flyway, Liquibase, or an equivalent controlled workflow, because init scripts run only once on initial cluster creation.

**Note on initialization errors:** if a script fails after the cluster was already initialized, the volume may retain partial data. Subsequent starts will not necessarily re-run the entire script because PGDATA is no longer empty. In a lab, you can create **a fresh volume** once you confirm old data is unneeded; in real systems, investigate the error and plan recovery rather than reflexively deleting the volume.

## 6. Starting PostgreSQL with Docker Compose

Navigate to `postgres-lab` and validate the configuration:

~~~bash
docker compose config --quiet
docker compose config --services
docker compose config --volumes
~~~

`docker compose config --quiet` validates syntax and variable interpolation without printing the full configuration. This is good practice when using passwords from `.env`, because `docker compose config` **without `--quiet` can print interpolated passwords**. Never share sensitive output.

Start:

~~~bash
docker compose up -d
~~~

On the first run, Docker may pull the PostgreSQL image, create the Compose network, create the named volume, and start the container. Per the image's entrypoint logic, it runs `initdb` to initialize the cluster, creates the role/database, and executes `01_schema.sql`.

Monitor:

~~~bash
docker compose ps
docker compose logs --tail=100 db
~~~

`docker compose ps` displays the container and service status; once initialization finishes, the healthcheck should transition to `healthy`. `docker compose logs --tail=100 db` reveals initialization messages, connections, errors, and PostgreSQL startup details.

In real containerized environments, logs may contain sensitive application data or initialization SQL; always review logs before sharing them publicly.

### If PostgreSQL Is Not Healthy Yet

Inspect logs:

~~~bash
docker compose ps
docker compose logs --tail=150 db
~~~

Common causes include a missing initialization password, SQL script errors, an occupied host port, incompatible bind mount permissions, a volume containing data from a different PostgreSQL major version, or insufficient host resources.

If port `5433` is already occupied, change the **host side** of the port mapping—for example, `127.0.0.1:55432:5432`. Do not change the internal container port unless the exercise specifically requires it.

## 7. Connecting and Querying Inside the Container

Once the service is ready, use `docker compose exec` to launch `psql` inside the container:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db
~~~

Inside `psql`:

~~~sql
SELECT version();
SELECT current_database(), current_user;
SELECT id, note, created_at
FROM lab_entries
ORDER BY id;
~~~

Per the init script, you should see one row:

~~~text
id | note
---+-----------------------------------
 1 | Data from first-time init script
~~~

Handy `psql` commands:

~~~text
\l          -- list databases
\dt         -- list tables in search path
\d lab_entries
\q          -- quit psql
~~~

These are **`psql` meta-commands**, not standard SQL. To run a single query directly from the terminal:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT COUNT(*) AS total FROM lab_entries;"
~~~

Note: local connections inside the container may match different authentication rules than TCP connections from the host. The fact that `docker compose exec db psql ...` works **does not automatically prove** external connection passwords are valid.

### Connecting from an Application on the Host

Using the port published by Compose:

~~~text
Host:       127.0.0.1
Port:       5433
Database:   lab_db
Username:   lab_user
Password:   value configured in .env
~~~

If `psql` is installed on the host:

~~~bash
psql -h 127.0.0.1 -p 5433 -U lab_user -d lab_db
~~~

The tool will prompt for a password if authentication requires it. Avoid typing passwords directly into commands or shell history.

Example JDBC URL for a Java application running **on the host**:

~~~properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5433/lab_db
spring.datasource.username=lab_user
spring.datasource.password=YOUR_LOCAL_SECRET
~~~

Use `YOUR_LOCAL_SECRET` solely as a placeholder; never commit real passwords to source control. A Java application running in **another container on the same Compose network** connects via `jdbc:postgresql://db:5432/lab_db` instead of the host's loopback address.

## 8. Experiment: Data Persists After Replacing the Container

This is the most important part for understanding **persistent volumes**. We will insert a row manually, stop/remove the container, start it again, and verify the row remains.

### Step 1. Write a Row After Initialization

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "INSERT INTO lab_entries (note) VALUES ('Data written after startup');"
~~~

Inspect the data:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

At this point there should be **two rows**: one from the init script and one just inserted.

### Step 2. Stop Compose and Remove the Container Normally

~~~bash
docker compose down
~~~

By default, `docker compose down` stops and removes containers and networks created by Compose for the project, **without removing the named volume `pgdata`**. PostgreSQL data remains safely inside the Docker volume.

List volumes:

~~~bash
docker volume ls
~~~

You should see a volume named something like `postgres-lab_pgdata`. The actual name depends on the Compose project name; never guess a name and run delete commands based on an example string.

### Step 3. Start Again

~~~bash
docker compose up -d
docker compose ps
~~~

Compose creates a new container and reattaches the existing named volume. Because `PGDATA` inside the volume already holds a valid PostgreSQL cluster, the entrypoint **does not re-run `initdb` and does not re-run `01_schema.sql`**.

Verify:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_db \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

The output should **still have two rows**. This proves data persists **outside the container's lifecycle**.

### Step 4. Recreate the Container While Keeping the Volume

You can test:

~~~bash
docker compose up -d --force-recreate
~~~

This forces recreation of the container while reusing the declared volume. Data continues to persist as long as the old volume is mounted properly and the cluster is intact.

**Key differences to remember:**

| Action | Container | Declared Named Volume |
| --- | --- | --- |
| `docker compose stop` | Stopped, not removed | Preserved |
| `docker compose start` | Starts existing container | Preserved |
| `docker compose restart` | Restarts container | Preserved |
| `docker compose down` | Removes project containers and networks | **Preserved** |
| `docker compose up -d --force-recreate` | Recreates container | **Preserved** |
| `docker compose down -v` | Removes containers and networks | **Deletes named volumes declared by Compose** |

This final point is critical: **`docker compose down -v` destroys your practice data** if the volume holds the only copy. Use it only when intentionally resetting the lab and certain no needed data remains.

## 9. Named Volume vs. Bind Mount: Which Should You Choose?

Both persist data outside the container, but they are managed differently:

| Criterion | Named Volume | Bind Mount |
| --- | --- | --- |
| Storage path | Managed by Docker | Host path specified by user |
| Compose example | `pgdata:/var/lib/postgresql/data` | `./pg-data:/var/lib/postgresql/data` |
| Access permissions | Managed with Docker resource handling | Depends on host owner, permissions, and file sharing |
| Ease of use on Docker Desktop | Usually convenient | May suffer host file-sharing overhead/performance limits |
| Inspecting on host | Via Docker and volume tools | Directory visible directly on host |
| Risks | Still removable via volume commands | Can be accidentally edited/deleted from host, wrong permissions, or slow I/O |

For practicing PostgreSQL, a **named volume is usually the simplest option**: it avoids complex data directory permission issues on Windows/macOS and keeps PGDATA out of synced project folders.

Bind mounts remain ideal for config files, init scripts, or Linux hosts requiring explicit control over storage layout. However, when bind-mounting PGDATA itself, pay close attention to ownership, filesystem type, I/O performance, and PostgreSQL compatibility.

### Never Back Up PostgreSQL by Arbitrarily Copying Live Files

Copying a PGDATA directory while PostgreSQL is writing **is not a reliable, consistent backup method**. PostgreSQL relies on WAL, checkpoints, and strict consistency guarantees. For backups, use `pg_dump`/`pg_restore` for logical backups or a supported physical backup tool with proper procedures.

## 10. Distinguishing Container Removal, Volume Removal, and Project Renames

Several situations commonly cause confusion:

**Scenario A: running `down` then `up` in the same directory.** The volume should be preserved, and data remains intact.

**Scenario B: renaming the project directory.** Compose may derive a **different project name**, creating a new, empty volume. Old data likely still resides in the old project's volume.

**Scenario C: renaming the `pgdata` resource in YAML.** Compose may create a new volume because the resource name changed, making PostgreSQL look like a brand-new cluster.

**Scenario D: running `down -v`.** Compose-managed volumes are actually deleted; data is lost if no backup exists.

**Scenario E: changing `postgres:16` to `postgres:17`.** The volume remains intact, yet PostgreSQL 17 may refuse to start against a PostgreSQL 16 data directory due to version mismatch. This is a **data upgrade issue**, not a lost volume.

### Identifying Which Volume Compose Uses

~~~bash
docker compose config --volumes
docker compose ps -q db
docker volume ls
~~~

To inspect actual mounts, run:

~~~bash
docker inspect "$(docker compose ps -q db)"
~~~

`docker inspect` outputs a large JSON document that may include **environment variables and passwords**. Inspect it locally only and never share raw output. Under mounts, verify type `volume`, the volume name, and destination `/var/lib/postgresql/data`.

If data "disappears" after renaming a directory or editing the Compose file, **do not rush to run `down -v`**; check the project name and attached volume first.

## 11. Initialization Data Runs Only Once

This behavior frequently surprises learners in labs. Distinguish three cases.

### 11.1. Editing 01_schema.sql After the First Run

Suppose you add:

~~~sql
CREATE TABLE another_table (
    id integer PRIMARY KEY
);
~~~

to `init/01_schema.sql`, and run:

~~~bash
docker compose restart db
~~~

**`another_table` will not magically appear** just because you edited the init script. The volume already holds an initialized cluster, so the entrypoint skips init scripts.

To apply changes to the existing database, run explicit SQL or a migration:

~~~bash
docker compose exec -T db \
  psql -U lab_user -d lab_db \
  < init/02_add_table.sql
~~~

In this example, `init/02_add_table.sql` is a SQL file created by the learner. `-T` disables pseudo-TTY allocation, useful when piping a file over stdin. Only run scripts you have read and trust; if a script is not idempotent, re-running it may fail or duplicate data.

### 11.2. Wanting a Completely Clean Lab

If you do not need to preserve any data:

~~~bash
# WARNING: deletes the volume and all associated lab data.
docker compose down -v
docker compose up -d
~~~

This procedure **intentionally wipes data** to rebuild the learning environment from scratch. Run it only after confirming the target Compose project and volume are not holding real service data. Fresh data will be created from the current `init` scripts.

### 11.3. Keeping Data While Evolving the Schema

Do not delete the volume. Instead of relying on init scripts, use versioned migrations, such as:

~~~text
V1__create_lab_entries.sql
V2__add_category_column.sql
V3__create_indexes.sql
~~~

Execute migrations using an appropriate tool or workflow, track schema versions, and prepare rollback steps for failed changes. Compose handles the **container lifecycle**, while migration tools manage **database schema change history**.

## 12. Backing Up and Restoring Lab Data

Named volumes protect data across container replacements, but not against accidental deletion, disk corruption, or `down -v`. Even in a practice environment, you should know how to take logical backups.

### 12.1. Backing Up with pg_dump

This example runs `pg_dump` **inside the container**, writing a custom-format file to `/tmp` inside the container:

~~~bash
docker compose exec db \
  pg_dump -U lab_user -d lab_db \
  -F c -f /tmp/lab_db.dump
~~~

Then copy the backup file from the container to your working directory on the host:

~~~bash
docker cp "$(docker compose ps -q db):/tmp/lab_db.dump" ./lab_db.dump
~~~

Using these two commands avoids piping the **binary stream** of `pg_dump -Fc` through host shell redirection, which can alter bytes differently across shells (especially in older PowerShell environments).

`lab_db.dump` on the host is a logical backup of `lab_db`. Store it safely if the data matters; never treat `/tmp` inside a container as durable storage.

### 12.2. Testing Restore into Another Lab Database

In a practice environment, you can verify a backup by restoring it into a **new** database rather than overwriting the active one:

~~~bash
docker compose exec db \
  createdb -U lab_user lab_restore

docker cp ./lab_db.dump "$(docker compose ps -q db):/tmp/lab_db.dump"

docker compose exec db \
  pg_restore -U lab_user -d lab_restore \
  /tmp/lab_db.dump
~~~

Then verify:

~~~bash
docker compose exec db \
  psql -U lab_user -d lab_restore \
  -c "SELECT id, note FROM lab_entries ORDER BY id;"
~~~

The `lab_entries` table and backed-up rows should appear in `lab_restore`. This practices the **restore test** mindset: a backup is only trustworthy once you can restore and query it.

**Scope note:** `pg_dump -d lab_db` backs up **a single database**; it does not automatically include cluster-wide roles, other databases, or instance configs. In real systems, design backup plans covering every resource needed for recovery. Furthermore, logical `pg_dump` backups do not replace WAL-based PITR when point-in-time recovery is required.

### 12.3. Why Not Back Up Only by Copying Docker Volumes?

A Docker volume is simply file storage; it does not create historical recovery points. Copying a volume while the database is running may yield inconsistent files unless proper PostgreSQL physical backup procedures are followed. For labs, `pg_dump` is clear and easy to start with. For larger systems, consider `pg_basebackup`, WAL archiving, and tested backup tools.

## 13. Upgrading the PostgreSQL Image Without Losing Data

Distinguish three kinds of updates:

1. **Restarting with the same image:** volume data remains intact.
2. **Patch updates within the same major version:** PGDATA can usually be reused, though you should still take a backup and review release notes before updating.
3. **Major version upgrades**, e.g., PostgreSQL 16 → 17: **never just swap the image tag**. Follow an upgrade workflow compatible with PostgreSQL's mechanisms.

Two common approaches for major upgrades:

- **Dump/restore:** export data from the old PostgreSQL instance, initialize a new cluster with the target image version, and import the data.
- **pg_upgrade:** upgrade the cluster using a procedure compatible with both PostgreSQL versions and required data/library paths.

With Docker Compose, creating a new volume for the target version and **keeping the old volume until verification completes** is generally safer than modifying live data in place.

Additionally, PostgreSQL 18 introduced significant changes to data directory layout in the official Docker image; never assume the `/var/lib/postgresql/data` mount path from this `postgres:16` example applies unchanged to newer tags.

## 14. Common Errors When Setting Up Labs with Compose

### 14.1. Missing or Empty POSTGRES_PASSWORD

**Symptom:** Compose reports a missing variable, or container initialization fails with password errors.

**Resolution:** verify `.env` sits where Compose reads it, `POSTGRES_PASSWORD` has a non-empty value, and no shell environment variable overrides it to an empty string.

Never work around this by enabling `trust` authentication for all hosts in a networked environment, as that weakens authentication controls.

### 14.2. Port 5433 Already in Use

**Symptom:** Docker cannot publish the port because the address/port is already allocated.

**Resolution:** change the **host** port in `ports`, e.g., `127.0.0.1:55432:5432`. There is no need to change PostgreSQL's internal container port without a specific requirement.

### 14.3. Changing POSTGRES_DB Does Not Create a New Database

**Cause:** the volume already contains PGDATA, so the entrypoint skips bootstrap steps.

**Resolution:** run `CREATE DATABASE` inside the existing cluster, or intentionally initialize a fresh lab on a new volume.

### 14.4. Editing the Init Script Does Not Show New Tables

**Cause:** scripts in `/docker-entrypoint-initdb.d` run only during initial cluster creation.

**Resolution:** run a SQL migration or rebuild a clean lab environment once you confirm old data is unneeded.

### 14.5. Using localhost from Another Application Container

**Cause:** `127.0.0.1` inside an application container resolves to that container itself.

**Resolution:** if on the same Compose network, use service name `db` and internal port `5432`. Use `127.0.0.1:5433` only for applications running directly on the host.

### 14.6. Compose Creates a New Volume After Renaming the Directory

**Cause:** the Compose project name changed, changing the actual derived volume name.

**Resolution:** inspect existing volumes with `docker volume ls`, check project naming, and verify mounts. Never rush to run `down -v` before identifying which volume holds your data.

### 14.7. Container Reports "database files are incompatible with server"

**Possible cause:** the image major version differs from the version that created PGDATA.

**Resolution:** switch back to the original major version image to access and back up data, then plan a controlled upgrade; never delete PGDATA just to make the error disappear.

### 14.8. Healthcheck Passes but the Application Still Errors

`pg_isready` primarily indicates the server accepts connections; it does not fully verify passwords, privileges, or schemas. Test an actual connection with the target user/database/host/port and check application logs.

### 14.9. Container Restarts Repeatedly

Check:

~~~bash
docker compose ps
docker compose logs --tail=150 db
~~~

Look for init SQL errors, mount permission issues, config errors, data directory version mismatches, or RAM/disk exhaustion. `restart: unless-stopped` retries container startup after failures, **but it cannot fix the underlying error**.

## 15. Basic Security for Practice Environments

Even when an environment is solely for learning, adopt good habits:

- **Do not publish the database port to all interfaces** unnecessarily. `127.0.0.1:5433:5432` fits a single-host lab.
- **Do not reuse example passwords**, commit secrets to Git, or treat `.env` as a production-grade secret vault.
- **Do not let real applications use the `POSTGRES_USER` bootstrap superuser.** When building real systems, create dedicated application roles with appropriate schema/table privileges.
- **Do not delete volumes by guessing names.** Always verify the exact project and data first.
- **Do not use a lab PostgreSQL container to store production data** without full backup, monitoring, hardening, and operational policies.
- **Do not mount the Docker socket or grant unnecessary container privileges** merely to access a database.

If another machine must connect to PostgreSQL, redesign network scope, firewalls, authentication, transport encryption, and per-role privileges; **never just swap `127.0.0.1` for `0.0.0.0` and assume it is safe**.

## 16. Practice Exercises

These exercises use the `postgres-lab` environment built above. Commands that destroy volumes are mentioned for contrast only; do not run them if you need to keep data.

### Exercise 1. Understanding the Compose File

For `compose.yaml` in Section 3, answer:

1. What is the PostgreSQL service name?
2. Which port is used from the host machine?
3. Which port does PostgreSQL use inside the container?
4. Which named volume stores PostgreSQL's physical data?

### Exercise 2. Testing Persistence

After adding a row to `lab_entries`, you run:

~~~bash
docker compose down
docker compose up -d
~~~

Questions: should the data remain? Why? Under what conditions might you see an empty database even though the old volume was not deleted?

### Exercise 3. Recognizing Data-Destructive Commands

Compare:

~~~bash
docker compose down
docker compose down -v
~~~

Which command preserves the named volume? Which command can delete PostgreSQL data?

### Exercise 4. Environment Variables Only Apply at Initialization

A user initializes `lab_db`, then changes `POSTGRES_DB=other_db` in `.env` and runs `docker compose restart`. Is `other_db` created automatically? What is the right approach to add a database while keeping `lab_db`?

### Exercise 5. Connecting from Another Container

A Java application running in an `api` service on the same Compose network uses `jdbc:postgresql://localhost:5433/lab_db` and fails. Suggest the correct URL and explain why.

### Exercise 6. Logical Backup

Show how to create `lab_db.dump` with `pg_dump` inside the container and copy it to the host. Why shouldn't you rely solely on a named volume as a backup?

### Exercise 7. Changing the Image to a New Major Version

Someone changes `postgres:16` to `postgres:17` while the `pgdata` volume still holds a PostgreSQL 16 cluster. Why may the server refuse to start? What should be done before upgrading?

### Exercise 8. Healthcheck and Passwords

The container shows `healthy`, yet the application fails to log in with a password newly edited in `.env`. Which two facts about the healthcheck and environment variable bootstrap mechanism should be checked?

### Reference Answers

| Exercise | Solution Direction |
| --- | --- |
| 1 | Service `db`, host port `5433`, container port `5432`, volume `pgdata` mounted at `/var/lib/postgresql/data` |
| 2 | Data remains because `down` preserves named volumes. An empty DB could result from a changed project name/volume, or connecting to the wrong database |
| 3 | `down` keeps the named volume; `down -v` deletes project-declared named volumes and can destroy data |
| 4 | No. `POSTGRES_DB` creates a database only during bootstrap. Run `CREATE DATABASE other_db;` or `createdb` on the existing cluster |
| 5 | Use `jdbc:postgresql://db:5432/lab_db` because sibling services connect via service name `db` and the container's internal port |
| 6 | Use `pg_dump -F c` to create a backup and `docker cp` to copy it to the host; volumes lack point-in-time history and can be corrupted/lost |
| 7 | PGDATA cannot be major-upgraded merely by swapping the image. Keep old data, back up, and perform dump/restore or `pg_upgrade` per compatible procedure |
| 8 | `pg_isready` does not verify full credentials; changing `POSTGRES_PASSWORD` post-bootstrap does not update the role password in existing PGDATA |

## 17. Quick Reference Command List

| Goal | Command |
| --- | --- |
| Validate configuration | `docker compose config --quiet` |
| Create and start container | `docker compose up -d` |
| Check status | `docker compose ps` |
| View logs | `docker compose logs --tail=100 db` |
| Open PostgreSQL CLI | `docker compose exec db psql -U lab_user -d lab_db` |
| Stop while keeping container | `docker compose stop` |
| Start stopped container | `docker compose start` |
| Restart container | `docker compose restart` |
| Remove containers/networks, keep named volume | `docker compose down` |
| Recreate container reusing old volume | `docker compose up -d --force-recreate` |
| List Docker volumes | `docker volume ls` |
| Delete lab **including data** | `docker compose down -v` — only when intentionally wiping data |

**Remember:** In a Docker Compose environment, the **image** holds PostgreSQL software, the **container** is the running process, and the **named volume** persists data across container recreations. Choosing the right mount path for your PostgreSQL version, understanding that bootstrap variables apply only at initial setup, and avoiding unintended volume deletion are the three most important principles for a safe, reusable PostgreSQL practice environment.
