# Persisting Data, Backing Up Configuration, and Reproducing an Oracle Environment

An Oracle environment used to study SQL, JDBC, or Java application development typically goes through repeated stops, restarts, code updates, and even deleting and recreating containers. Without designing storage up front, learners can lose all their tables and data from a single misexecuted Docker command. Conversely, keeping data without recording the Oracle version, connection configuration, and schema-creation steps still makes rebuilding the environment on another machine prone to failure.

This lesson guides you through organizing **an Oracle practice environment with persistent storage**, **backing up both configuration and data**, and **controlled environment reproduction**. The examples use Oracle Database Free in Docker Compose, though the principles of consistency, backups, versioning, and recovery apply equally to Oracle running directly on a host or inside a virtual machine.

## 1. Distinguishing Four Activities Often Lumped Together as "Saving Data"

| Activity | Goal | Example | Limitation |
|---|---|---|---|
| **Data persistence** | Retain data after the app/container stops or is recreated | Mounting a Docker named volume to Oracle's data directory | A volume can still be corrupted or deleted; **it is not a backup** |
| **Data backup** | Have an independent copy of data to recover from failure | Oracle RMAN, Data Pump, or a volume archive *taken after a clean database shutdown* | Some backup types restore only a schema, not the entire database |
| **Configuration backup** | Record exactly how the environment is built and connected | `compose.yaml`, image version, init SQL, JDBC config, operational docs | Cannot recover runtime business data without a data backup |
| **Reproducibility** | Rebuild a working, verifiable system from saved configuration | Compose + pinned image version + SQL migrations/seed + restore guide | Does not automatically include the latest live data |

Three scenarios must be distinguished:

1. **Restart:** stop and restart the same environment; committed data must remain.
2. **Recreate:** remove the container and start a new one using the **same volume**; prior data must still remain if the volume was not deleted.
3. **Disaster recovery:** the original volume is lost or corrupted; an **independent backup** is required for restoration beyond simply recreating the container.

> **Principle:** Containers are disposable and recreatable, but database data needs its own lifecycle. A volume preserves state across container lifecycles; a backup stored outside that volume provides recoverability when the volume is lost.

## 2. How Does Oracle Write Data Persistently?

Oracle processes queries through an **instance** (memory and processes), while data is organized inside a **database** consisting of required files on storage:

- **Datafiles:** store segments holding tables, indexes, and other objects.
- **Control files:** record database structure and state, datafile inventory, and redo metadata.
- **Online redo logs:** record changes to support crash recovery.
- **Archived redo logs:** saved copies of filled redo logs when `ARCHIVELOG` is enabled; crucial for backup strategies and point-in-time recovery.

When a transaction executes `COMMIT`, Oracle uses the redo mechanism to guarantee transaction durability under standard configuration. Changes are not necessarily flushed immediately into datafiles at `COMMIT` time: redo is essential if the instance stops abruptly. Never try to replace this mechanism by manually copying open Oracle files.

Example:

~~~sql
INSERT INTO lab_notes (note_id, note_text)
VALUES (99, 'Note must survive after restart');

COMMIT;
~~~

After a clean restart, the committed row must remain, provided the database and storage are intact and no delete/overwrite restore occurred. Conversely, an **uncommitted** transaction can be rolled back when a session disconnects or the instance performs recovery.

In multitenant architecture, application data typically resides inside a **PDB** (e.g., `FREEPDB1`) belonging to a **CDB**. Having a PDB does not mean you mount a separate Docker volume per PDB. In the example below, the volume holds the database file set created by Oracle Free; PDBs inside it are served from that storage.

## 3. Why Storing Data Inside the Container Layer Is Not Enough

Containers have an **ephemeral writable layer**. Changes stored only in that writable layer can be lost when the container is removed and recreated from the image. Docker provides **volumes** or **bind mounts** to store data outside the container lifecycle.

~~~text
Learner's machine
│
├── compose.yaml, .env, sql/       Configuration and scripts
│
└── Docker Engine
    │
    ├── Oracle container          Can stop / remove / recreate
    │   ├── Oracle instance        Running memory + processes
    │   └── /opt/oracle/oradata ───────────┐
    │                                     │ mount volume
    └── Docker named volume               ▼
        oracle_lab_data             Database files
                                     persist outside container
~~~

For the illustrative image `gvenzl/oracle-free:23-slim`, the database storage directory is mounted at `/opt/oracle/oradata`. **This path is image-dependent**: when using a different Oracle image, consult that image's documentation before mounting a volume. Mounting the wrong path can cause a fresh database to be initialized every time the container is recreated.

### Named volumes vs. bind mounts

| Mechanism | Used for | Key traits to remember |
|---|---|---|
| **Named volume** | Datafiles, redo, control files of the lab environment | Docker manages path and permissions; usually convenient for Oracle data in containers |
| **Bind mount** | Scripts, configs, output directories for backups/exports | Files are immediately visible on the host; pay attention to permissions and I/O performance |
| **Container writable layer** | Temporary contents that do not need to persist | Lost when container is removed; never store database data you want to keep here |

When running Docker Desktop on Windows/macOS, named volumes usually avoid permission and I/O performance issues common when placing database files directly on host-shared folders. However, **volumes do not automatically sync to Git or the cloud**.

## 4. Setting Up a Practice Oracle Environment with Docker Compose

This example uses Docker Compose v2 and the community image `gvenzl/oracle-free` for lab practice. You need Docker Engine / Docker Desktop, sufficient RAM, and disk space for Oracle. In long-lived environments, **pin a specific version or verified image digest** instead of letting a floating tag change unexpectedly.

### 4.1. Project layout

~~~text
oracle-lab/
├── compose.yaml
├── .env.example
├── .env                      Do not commit; contains real passwords
├── .gitignore
├── sql/
│   └── 001_schema_and_seed.sql
├── backups/                  Backups stored outside the database volume
└── README.md                 How to run, connect, back up, restore
~~~

The `backups/` folder is only a local destination on your machine; to protect against losing the machine or disk, copy backups to independent, secured storage and test restoration.

### 4.2. The `compose.yaml` file

~~~yaml
name: oracle-lab

services:
  db:
    image: gvenzl/oracle-free:23-slim
    ports:
      - "127.0.0.1:1521:1521"
    environment:
      ORACLE_PASSWORD: "${ORACLE_PASSWORD:?Set ORACLE_PASSWORD in .env}"
      APP_USER: LAB_APP
      APP_USER_PASSWORD: "${APP_USER_PASSWORD:?Set APP_USER_PASSWORD in .env}"
    volumes:
      - oracle_data:/opt/oracle/oradata
    stop_grace_period: 3m

volumes:
  oracle_data:
    name: oracle_lab_data
~~~

Explanation:

- `db` is the Compose service name. Inside Compose's internal network, apps in other containers can use hostname `db`.
- Port `1521` is published on the host's `127.0.0.1` so the lab is reachable from the machine running Docker; by default it is not exposed on all network interfaces.
- `ORACLE_PASSWORD` is supplied during database initialization per this image's convention; `APP_USER` and `APP_USER_PASSWORD` set up a test user during first initialization.
- `oracle_data` maps to the named volume **`oracle_lab_data`**, an explicit fixed name that is easy to identify and back up.
- `stop_grace_period` gives Oracle extra time to shut down before Docker forces container termination. For cold-copy backups, you must still verify the database shut down cleanly.

The keys in `environment` are **specific to this illustrative image**; they do not automatically apply to every Oracle image. Once data has been initialized inside the volume, editing password variables in `.env` **does not automatically change the user password stored inside the database**.

### 4.3. `.env.example` and `.gitignore`

~~~dotenv
# .env.example - template only, contains no real passwords
ORACLE_PASSWORD=replace-with-a-strong-admin-password
APP_USER_PASSWORD=replace-with-a-strong-app-password
~~~

~~~gitignore
# Do not store secrets or backups in the source code repository
.env
backups/
*.dmp
*.bak
~~~

Create `.env` from the template and replace both values with passwords dedicated to your lab environment. In PowerShell:

~~~powershell
Copy-Item .env.example .env
# Open .env in a text editor and replace the sample values
docker compose up -d
docker compose ps
docker compose logs -f db
~~~

First-time Oracle initialization can take a while. Connect only after the image's logs/health indicate the database is ready. To exit log tailing, press `Ctrl+C`; this does not delete the volume.

### 4.4. Connecting to the right PDB

With the illustrative image and configuration, the default PDB service is `FREEPDB1`; check the actual service if using a different version or image.

| Where the app runs | Host | Port | Service | JDBC Thin example |
|---|---|---|---|---|
| Java on the **host** | `localhost` | `1521` | `FREEPDB1` | `jdbc:oracle:thin:@//localhost:1521/FREEPDB1` |
| Java in the **same Compose network** | `db` | `1521` | `FREEPDB1` | `jdbc:oracle:thin:@//db:1521/FREEPDB1` |

The application user is `LAB_APP`, and the password is the `APP_USER_PASSWORD` used during initialization. For Java / Spring Boot apps, read the password from an environment variable or secret manager:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//localhost:1521/FREEPDB1
spring.datasource.username=LAB_APP
spring.datasource.password=${DB_APP_PASSWORD}
~~~

Here `DB_APP_PASSWORD` is the **Java application's** environment variable; supply a value matching user `LAB_APP`'s password, as there is no automatic sync between Java's variable and Compose's `.env`.

## 5. Repeatable Schema and Sample Data Initialization

To reproduce an environment, besides containers and volumes, you need the **database schema**: tables, indexes, constraints, seed data, and migration order. For a small lab, SQL files can live in `sql/`. For real applications, manage versioned migrations with a tool like Flyway or Liquibase.

The `sql/001_schema_and_seed.sql` file below can be re-run without creating duplicate tables or sample records:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE

-- Log in as LAB_APP on PDB FREEPDB1 before running.
DECLARE
    v_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM user_tables
    WHERE table_name = 'LAB_NOTES';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE lab_notes (
                note_id    NUMBER(10) PRIMARY KEY,
                note_text  VARCHAR2(200) NOT NULL,
                created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )';
    END IF;
END;
/

MERGE INTO lab_notes t
USING (
    SELECT 1 AS note_id,
           'Initial seed record' AS note_text
    FROM dual
) s
ON (t.note_id = s.note_id)
WHEN NOT MATCHED THEN
    INSERT (note_id, note_text)
    VALUES (s.note_id, s.note_text);

COMMIT;

SELECT note_id, note_text, created_at
FROM lab_notes
ORDER BY note_id;
~~~

Run inside the container (PowerShell from the project directory):

~~~powershell
docker cp .\sql\001_schema_and_seed.sql "$(docker compose ps -q db):/tmp/001_schema_and_seed.sql"
docker compose exec db sqlplus -L lab_app@//localhost:1521/FREEPDB1
~~~

SQL*Plus will prompt for `LAB_APP`'s password. At the `SQL>` prompt, enter:

~~~sql
@/tmp/001_schema_and_seed.sql
~~~

If using SQL Developer or SQLcl on your machine, you can also connect directly to `localhost:1521/FREEPDB1` as `LAB_APP` and run the SQL contents without `docker cp`.

**Note on repeatability:** `MERGE` prevents duplicate seed rows and `CREATE TABLE` runs only when the table does not exist yet. For schemas evolving across versions, do not rely solely on "create if not exists" tricks in place of a migration tool; you need ordering, versioning, and structured handling for complex column/index changes.

## 6. Testing Data Persistence Across Restart and Recreate

Connect as `LAB_APP` and insert a row **not present in the seed file**:

~~~sql
INSERT INTO lab_notes (note_id, note_text)
VALUES (99, 'Row created during practice');

COMMIT;

SELECT note_id, note_text
FROM lab_notes
WHERE note_id = 99;
~~~

Then exit SQL*Plus and run:

~~~powershell
# Case 1: stop and restart the existing service
docker compose stop db
docker compose start db

# Case 2: tear down the container and Compose network, then recreate the container
# (do not pass -v)
docker compose down
docker compose up -d
~~~

Wait for Oracle to open and log back in; the query `WHERE note_id = 99` must still return the row. This proves the datafiles in the named volume survive the container lifecycle.

Inspect the volume name and state:

~~~powershell
docker volume inspect oracle_lab_data
~~~

Comparison of operations:

| Command | Container | Typical named volume |
|---|---|---|
| `docker compose stop` | Stopped; container/metadata preserved | Retained |
| `docker compose start` | Starts existing container again | Reused |
| `docker compose down` | Removes container and Compose network | **Retained**, unless `-v` is passed |
| `docker compose up -d` | Uses/creates container per config | Reattaches declared volume |
| `docker compose down -v` | Removes container and Compose-managed volumes | **Can permanently delete lab data** |
| `docker volume rm oracle_lab_data` | Does not necessarily affect removed containers | **Deletes volume** when Docker permits |

Never run `down -v` or delete the volume just to "refresh the container" if you still need the data. Before intentionally resetting an environment, confirm whether you want a **brand-new empty database** or to **restore an existing database**.

## 7. Data Backups: Choosing the Right Scope and Consistency Level

Three common backup methods serve different needs:

| Backup method | What does it capture? | When to use? | Notes |
|---|---|---|---|
| **Cold backup** after clean Oracle shutdown | Database file set within the copied scope | Personal labs, snapshots before major changes, moving as-is to a compatible environment | Must shut down database cleanly and capture all related files; never hot-copy ad hoc |
| **Data Pump** (`expdp`/`impdp`) | Logical data and metadata at schema/table/PDB scope | Moving exercise data, saving a single schema, importing into another database | Does not replace a full physical backup of CDB, redo, control files, or instance config |
| **RMAN** | Oracle-aware physical backups supporting advanced recovery workflows | Environments needing online backups, retention, and rigorous recovery | Must plan backup storage, archivelog, privileges, retention, and restore testing |

### 7.1. Cold backup for a lab using a named volume

In this example, **do not** tar the volume while Oracle is actively writing data. Shut down Oracle cleanly first, stop the container, then copy the volume into an archive file outside the database volume.

**Step 1 — perform a controlled database shutdown.** Ensure no exercise or application has pending transactions to finish. Connect with OS admin rights inside the container and instruct Oracle to shut down:

~~~powershell
docker compose exec -u oracle db bash -lc 'printf "shutdown immediate;\nexit;\n" | sqlplus -s "/ as sysdba"'
~~~

Proceed only if the shutdown command completes cleanly. If your image or OS permissions differ, use the shutdown method supported by that image. A Docker force-stop due to timeout or process kill **does not count as a clean shutdown**.

**Step 2 — stop the container and create the host backup directory.**

~~~powershell
docker compose stop -t 180 db
New-Item -ItemType Directory -Force .\backups\cold | Out-Null
~~~

**Step 3 — archive the volume using a helper container.**

~~~powershell
docker run --rm --mount "type=volume,src=oracle_lab_data,dst=/source,readonly" --mount "type=bind,src=$((Resolve-Path .\backups\cold).Path),dst=/backup" alpine:3.20 tar -czf /backup/oracle_lab_data.tar.gz -C /source .
~~~

This mounts the volume read-only and writes `backups/cold/oracle_lab_data.tar.gz` on the host. On Linux/macOS, replace the PowerShell path expression `$((Resolve-Path ...).Path)` with the absolute path of the host backup directory.

**Step 4 — generate a checksum and bring Oracle back online.**

~~~powershell
(Get-FileHash .\backups\cold\oracle_lab_data.tar.gz -Algorithm SHA256).Hash | Set-Content .\backups\cold\oracle_lab_data.tar.gz.sha256
docker compose up -d db
~~~

Record alongside the backup: timestamp, image/tag **and digest** used, CDB/PDB names, backup type, shutdown status, archive size, SHA-256 checksum, and restore instructions. Keep the archive outside the original volume; a copy sitting on the exact same physical disk as the volume can still be lost if that disk fails.

> **Example limitation:** This is a file-level backup taken after closing the database and works best for a single-container lab where one volume holds all required Oracle files. If the system spans multiple volumes, places files outside the mounted folder, or uses ASM, RAC, or other storage layouts, archiving a single volume may be **incomplete**. When hot backups or point-in-time recovery are needed, use an Oracle-supported method such as RMAN.

### 7.2. Data Pump: logical backup of a single schema

When you only need to move `LAB_APP`'s tables, data, and metadata to another environment, **Oracle Data Pump** is an option. A conceptual export command:

~~~text
expdp lab_app@//localhost:1521/FREEPDB1 \
  schemas=LAB_APP \
  directory=LAB_DUMP_DIR \
  dumpfile=lab_app_01.dmp \
  logfile=lab_app_01.log
~~~

Before running, a DBA must create an **Oracle DIRECTORY object** (e.g., `LAB_DUMP_DIR`) pointing to an OS directory writable by the Oracle process and grant `READ`/`WRITE` privileges on it to the exporting user. `directory=LAB_DUMP_DIR` is a **database object name**, not an arbitrary path passed from the client machine. The `.dmp` file is written **on the Oracle server side**; after exporting, copy it to independent backup storage along with the log, version, and export parameters. In some configurations, the export/import scope requires higher privileges than an application user.

When importing with `impdp`, consider target user/schema, tablespaces, privileges, version compatibility, and pre-existing objects. **Never** treat a single-schema Data Pump export as a substitute for a full CDB backup.

### 7.3. RMAN: when structured recovery is required

**Recovery Manager (RMAN)** is Oracle's physical backup and restore tool. It manages database and archivelog backups, supporting verification and engineered recovery procedures. A common RMAN command in an archivelog strategy is:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

This is a semantic example, **not** a complete backup configuration. Before running in a real environment, verify the database mode, backup destination, capacity, privileges, retention policy, archivelog state, and tested restore procedures. In simple labs, cold backups may be easier to grasp; in systems that must stay online continuously, evaluate RMAN.

## 8. Configuration Backup: What Belongs in the "Reproduction Kit"

A backup containing only database files without instructions on how the environment was built can force whoever restores it to spend hours hunting down versions, accounts, and endpoints. Maintain a version-controlled configuration kit:

~~~text
oracle-lab/
├── compose.yaml                  Services, volumes, ports, image
├── .env.example                  List of required variables
├── sql/
│   ├── 001_schema_and_seed.sql
│   └── ...                       Subsequent migrations/seeds
├── app-config.example            JDBC URL and env var names
├── README.md                     Setup, run, reset, backup, restore
└── backup-manifest.txt           Version, timestamp, and backup checksum
~~~

Document the following clearly:

- **Software versions:** exact Oracle image and digest; Docker/Compose versions; if using a Java app, record Java version, JDBC driver, and schema migrations.
- **Service configuration:** service name/PDB, ports, Docker networks, volume mounts, resource limits, and any customized listener/Oracle Net options.
- **Data configuration:** SQL creating tables, constraints, indexes, required users/privileges, and seed data; if using migrations, record applied versions.
- **Secrets:** the *names* of required variables (`ORACLE_PASSWORD`, `APP_USER_PASSWORD`, etc.), where secrets are securely stored, and how they are injected. Never push real values into repositories, logs, or screenshots.
- **Operational runbook:** start/stop commands, readiness checks, backup steps, checksum validation, restore steps, data verification, and warnings before volume deletion.

**Pinning images by digest** makes the specification far more reproducible since tags like `23-slim` can be updated. The exact digest depends on the image your team actually pulled and tested; record it with the backup and use the compatible image when restoring. Never attempt to upgrade a database version merely by swapping the image and attaching an old version's data volume unless following an Oracle/image-supported upgrade path.

`.env.example` can be committed because it holds only placeholders. The **real `.env`** must be protected; if backed up for recovery, encrypt it and restrict access so admin passwords never enter Git.

## 9. Reproducing the Environment: Two Distinct Paths

Two different operational goals lead to two different workflows:

~~~text
                    Saved compose + SQL + image version?
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
        Create a fresh, clean environment      Restore existing data
                    │                                   │
          Start DB on a new volume            Retrieve independent backup
                    │                                   │
         Run migrations + seed data           Restore into target volume/DB
                    │                                   │
         Schema and sample data ready         Data state as of backup time
                    └─────────────────┬─────────────────┘
                                      ▼
                        Connect and verify schema,
                        data, and application flow
~~~

### 9.1. Fresh rebuild from configuration

Workflow:

1. Clone/fetch the configuration repository, read `README.md`, and install/pull the specified image version.
2. Supply secret variables from a secure source—never pull real passwords from the repository.
3. Create a **new empty volume** and run `docker compose up -d`.
4. Wait for Oracle readiness, confirm PDB `FREEPDB1`, and log into the application user.
5. Run migrations / SQL seeds in order.
6. Verify table structure, sample row counts, JDBC connection URL, and an application read/write flow.

The outcome is **an environment with the exact same structure**, without prior runtime data. This reproduction path works well for onboarding or running automated labs from a clean baseline.

### 9.2. Restoring a cold backup into a **separate** volume to avoid touching original data

Testing a restore on a new volume is safer than overwriting an active volume directly. Assume `backups/cold/oracle_lab_data.tar.gz` exists from section 7, and the restore image is compatible with the image that created the backup.

**Step 1 — verify the saved archive and checksum:**

~~~powershell
$expected = (Get-Content .\backups\cold\oracle_lab_data.tar.gz.sha256).Trim()
$actual = (Get-FileHash .\backups\cold\oracle_lab_data.tar.gz -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "Backup checksum mismatch" }
~~~

**Step 2 — create a brand-new restore volume:**

~~~powershell
docker volume create oracle_lab_restore_data
~~~

**Step 3 — extract into the empty restore volume:**

~~~powershell
docker run --rm --mount "type=volume,src=oracle_lab_restore_data,dst=/target" --mount "type=bind,src=$((Resolve-Path .\backups\cold).Path),dst=/backup,readonly" alpine:3.20 sh -c 'test -z "$(ls -A /target)" && tar -xzf /backup/oracle_lab_data.tar.gz -C /target'
~~~

The `test -z "$(ls -A /target)"` guard requires an empty target volume, preventing accidental extraction over an existing database. Never use the original `oracle_lab_data` volume as a test target.

**Step 4 — run a separate Compose project for the restored instance:**

Create `compose.restore.yaml` (using the same compatible image/digest recorded in the manifest):

~~~yaml
name: oracle-lab-restore

services:
  db:
    image: gvenzl/oracle-free:23-slim
    ports:
      - "127.0.0.1:1522:1521"
    environment:
      ORACLE_PASSWORD: "${ORACLE_PASSWORD:?Set ORACLE_PASSWORD in .env}"
    volumes:
      - restored_data:/opt/oracle/oradata
    stop_grace_period: 3m

volumes:
  restored_data:
    external: true
    name: oracle_lab_restore_data
~~~

~~~powershell
docker compose -f compose.restore.yaml up -d
docker compose -f compose.restore.yaml ps
docker compose -f compose.restore.yaml logs -f db
~~~

In this example, host port `1522` forwards to port `1521` in the restored container, letting it run alongside the original lab on port `1521`. Log in with **the database's password as of backup time**: Compose's `ORACLE_PASSWORD` variable does not reset passwords already stored inside the volume.

From the host, use:

~~~text
jdbc:oracle:thin:@//localhost:1522/FREEPDB1
~~~

Then verify data committed prior to the backup:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS pdb_name
FROM dual;

SELECT note_id, note_text
FROM lab_notes
WHERE note_id = 99;
~~~

Row `99` depends on **when the backup was taken**: it exists in the restored database if committed before the snapshot; changes made after the snapshot will not appear upon restore. If you intend to promote the restored instance to become the primary database, plan the endpoint/service cutover, resolve data divergence, and halt writes on the old source under a controlled procedure.

## 10. Verifying That a Backup Is Actually Usable

A `.tar.gz` or `.dmp` file sitting on disk only proves a file exists; it does not prove recoverability. A lab can practice an independent restore against these criteria:

1. **Archive integrity:** size and SHA-256 match the manifest; file is readable from backup storage.
2. **Environment compatibility:** Oracle image, volume structure, PDB configuration, and required resources were recorded.
3. **Database startup:** instance and PDB open cleanly, and the listener/service serves connections.
4. **Data accuracy:** known sample rows, primary keys/indexes, schema owner, and basic queries work.
5. **Application connectivity:** JDBC connects with the right host, port, service, and user; a `SELECT` succeeds, and where appropriate, a write/rollback transaction succeeds.
6. **Secrets protected:** passwords were not leaked to Git/backup logs and can be retrieved via authorized procedures.

Record the date of the latest restore drill alongside the manifest. In real projects, schedule periodic restore tests and store backups independently of the database host. Keeping multiple historical backups also helps recover from issues that occurred before the most recent backup.

### Introductory RPO and RTO

- **RPO (Recovery Point Objective):** the maximum acceptable time window of data loss. If you only take a cold backup Sunday night and lose the volume Tuesday night, you may lose all data generated since Sunday's backup.
- **RTO (Recovery Time Objective):** how quickly the system must be restored. A huge archive, slow download, or missing password/compatible image increases recovery time.

These metrics guide whether to back up daily or weekly, whether to use Data Pump or RMAN, and how many backups to retain. Even for personal practice labs, it helps to recognize that **persistence alone does not define RPO/RTO**.

## 11. Common Errors and How to Distinguish Them

| Symptom | Common likely cause | What to inspect |
|---|---|---|
| Recreated container and tables disappeared | Volume mounted to wrong path; accidentally ran `down -v`; different volume/project name | `compose.yaml`, container mounts, `docker volume ls` |
| Changed `APP_USER_PASSWORD` in `.env` but cannot log in | User was already created during first volume initialization | Password lives inside the database; change it with appropriate admin SQL |
| Oracle fails to open after restoring archive | Inconsistent/incomplete archive; incompatible image; file permissions or disk space | Shutdown method during backup, manifest, Oracle logs, restored file set |
| Restore succeeded but newly added row is missing | Row was added **after backup time** or never `COMMIT`ted | Backup timestamp vs. transaction timing; RPO |
| Connection to `localhost:1521` refused from another Java container | `localhost` inside the Java container refers to that container itself | Use Compose service hostname `db` and service `FREEPDB1` |
| Login succeeds but tables are missing | Connected to wrong PDB/service or user/schema; missing privileges | `SYS_CONTEXT('USERENV','CON_NAME')`, `CURRENT_SCHEMA`, table owner |
| Have `.dmp` file but cannot import | Missing DIRECTORY object/privileges, file in wrong location, or version mismatch | Server-side path, READ/WRITE privileges, expdp/impdp logs |
| Backed up `compose.yaml` yet cannot restore old data | Saved configuration only, no data backup | Datafile/RMAN/Data Pump backups and desired recovery point |

## 12. Practice Exercises

### Exercise 1 — Verify persistence

Create table `LAB_NOTES`, commit a row with `note_id = 99`, run `docker compose down`, then `docker compose up -d`. Reconnect and confirm row 99 still exists. Explain why datafiles were not lost even though the container was recreated.

**Hint:** compare the container lifecycle with the lifecycle of named volume `oracle_lab_data`; do not pass `down -v`.

### Exercise 2 — Point-in-time recovery concept

After writing row 99, take a cold backup. Once Oracle is running again, insert and commit `note_id = 100`. Restore the archive onto a new volume `oracle_lab_restore_data`. Query both rows in the restored database.

**Expected result:** row 99 is present in the restored instance; row 100 is absent if committed after the backup. This visually illustrates **RPO**.

### Exercise 3 — Moving to another machine

Suppose you can carry over only the configuration files, SQL scripts, archive file, and secrets via an authorized channel. Map out the sequence to rebuild Oracle on the new machine, change the host port if `1521` is already occupied by another app, then connect with JDBC and verify the data.

**Hint:** never assume container names or IPs match the old host. The connection target is determined by the new host's hostname/port and Oracle's service name; data comes from the backup, not from the Compose file.

### Exercise 4 — Choosing a backup method

You have three requirements: (a) move only the tables in schema `LAB_APP`; (b) recover the entire lab after losing a volume; (c) back up a system that must stay online for users and requires point-in-time recovery. Match each with Data Pump, cold backup, or RMAN, and state the preconditions needed for each method to be valid.

**Guidance:** (a) Data Pump; (b) a consistent, complete cold backup for the lab; (c) RMAN within a designed archive/retention/restore strategy. Each solves a different scope.

## Conclusion

A reliably reproducible Oracle practice environment requires **three parallel layers**: a volume to preserve data across container lifecycles, **independent and consistent backups** to recover from loss, and **versioned configuration plus SQL** to rebuild the environment accurately. Build the habit of documenting image versions, PDB/service names, volume paths, backup locations, secret handling, and restore verification procedures. Then restarting, switching machines, or resetting exercises becomes a controlled operation rather than a gamble with your data.
