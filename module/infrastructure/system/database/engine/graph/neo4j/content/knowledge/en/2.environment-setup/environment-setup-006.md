# Directory Structure for Configuration, Data, Logs, and Extensions

## 1. Lesson Objectives

Neo4j is a graph database management system based on the **property graph** model. Information is modeled with **nodes**, directed **relationships**, and **properties**; the **Cypher** language lets you query relationships and paths between nodes. To work effectively with Neo4j in Java applications, Spring Data Neo4j, CSV imports, creating indexes/constraints, or operating the database, you must know **what each file and directory does**.

Within the **Environment Setup** chapter, this lesson explains the directory layout when installing Neo4j directly on a machine, via OS packages, in Neo4j Desktop, and in Docker. You will use that layout to locate configuration, databases, transaction logs, operational logs, import files, and plugins accurately.

After this lesson, you will be able to:

1. Identify the roles of `bin`, `conf`, `data`, `logs`, `import`, `plugins`, `labs`, `products`, and `lib`.
2. Distinguish **transaction logs** inside the data area from **diagnostic logs** in `logs`.
3. Find configuration paths by installation method and verify the actual paths Neo4j is using.
4. Run a Neo4j instance with Docker Compose using **persistent volumes for data/logs**, a **read-only bind mount for CSVs**, and an optional plugin directory.
5. Troubleshoot permission errors, incompatible plugins, unreadable CSVs, disk exhaustion, or data loss after container replacement.

> **Scope:** Path names and settings follow the Neo4j 5.x/2026.x line; Docker examples use `neo4j:2026.10.2`. Older releases, editions, or installation methods may have their own layouts. **Do not manually edit internal files of a running database**; interact with data through Cypher or version-matched Neo4j administration tools.

## 2. Directory Map: Understanding by Purpose

For ZIP/TAR Neo4j Server distributions, `<NEO4J_HOME>` is the extracted root directory. General layout:

~~~text
<NEO4J_HOME>/
├── bin/                   # neo4j, neo4j-admin, cypher-shell
├── conf/                  # neo4j.conf, neo4j-admin.conf, *-logs.xml
├── data/                  # databases, system database, transaction logs, dumps...
│   ├── databases/         # Internal database files; do not edit manually
│   └── transactions/      # Transaction logs per database (default)
├── import/                # CSV files used by LOAD CSV from file:///
├── logs/                  # Operational, debug, and query logs if enabled
├── plugins/               # Custom plugin JARs, procedures/functions
├── labs/                  # Bundled plugins such as APOC Core
├── products/              # Bundled add-on products/features, depending on edition
├── lib/                   # Core JAR libraries Neo4j requires to run
├── licenses/              # License files when required
├── metrics/               # Metric files, depending on edition/config
└── run/                   # Process/PID state
~~~

The diagram above is a **conceptual map**, not a guarantee that every directory or file exists in every edition and version. Neo4j may create additional directories such as `web` or `ssl`, or change internal layout across releases.

| Directory | Primary purpose | Minimum permissions usually needed | Should you modify it directly? |
| --- | --- | --- | --- |
| `bin` | Starting the DBMS and admin tools | Read, execute | Run tools; do not edit binaries |
| `conf` | DBMS/Log4j configuration | Read; admin write access | **Yes**, after understanding settings and restart flow |
| `data` | Data store and system metadata | Read, write for the Neo4j process | **Do not edit internal files manually** |
| `logs` | Operational/diagnostic logs | Read, write | May read/collect logs; manage via rotation config |
| `import` | Source import files | Neo4j needs read access | **Yes**, place CSVs here as needed |
| `plugins` | Custom plugin JARs | Neo4j read access | Yes, but only add version-matched plugins from trusted sources |
| `labs`, `products` | Bundled add-on packages | Read | Only copy/install per plugin documentation |
| `lib` | Core server runtime libraries | Read | Do not drop arbitrary JARs here |
| `licenses` | Required license files (if any) | Read | Manage only through official licensing mechanisms |
| `metrics`, `run` | Operational metrics/process files | Per function | Do not edit or delete arbitrarily |

**Two principles to remember:**

- **Configuration, data, and logs have different lifecycles.** When upgrading an image/server, you typically keep data and backups; configuration must be reconciled with the new version; logs follow their own retention policy.
- **Host paths do not necessarily match container paths.** Docker can mount a named volume at `/data`; a Java app folder on the host cannot infer the physical host path of that volume.

## 3. Default Locations by Installation Method

### 3.1. Path comparison table

| Component | Linux/macOS ZIP/TAR | Windows ZIP | Debian/RPM package | Docker |
| --- | --- | --- | --- | --- |
| Executables | `<NEO4J_HOME>/bin` | `<NEO4J_HOME>\bin` | `/usr/bin` | Inside image, invoked via `docker exec` |
| Configuration | `<NEO4J_HOME>/conf` | `<NEO4J_HOME>\conf` | `/etc/neo4j` | `/conf` inside container |
| Data | `<NEO4J_HOME>/data` | `<NEO4J_HOME>\data` | `/var/lib/neo4j/data` | `/data` |
| Logs | `<NEO4J_HOME>/logs` | `<NEO4J_HOME>\logs` | `/var/log/neo4j`, `journalctl` for service logs | `/logs` and `docker logs` |
| CSV import | `<NEO4J_HOME>/import` | `<NEO4J_HOME>\import` | `/var/lib/neo4j/import` | `/import` |
| Plugin JARs | `<NEO4J_HOME>/plugins` | `<NEO4J_HOME>\plugins` | `/var/lib/neo4j/plugins` | `/plugins` |
| Bundled APOC | `<NEO4J_HOME>/labs` | `<NEO4J_HOME>\labs` | `/var/lib/neo4j/labs` | `labs` directory inside image |

**Neo4j Desktop:** instead of guessing folders under `AppData`, `Library`, or your home directory, select the active **DBMS instance**, open **Open → Terminal** (menu labels vary by Desktop version), and access `conf`, `data`, `logs`, or `plugins` from that instance's own terminal. One machine can hold multiple Desktop-managed DBMSs, each in its own location.

**Neo4j AuraDB:** the system runs on service-managed infrastructure, so **you cannot directly open `data`, `conf`, or `plugins` on the server** as in self-hosted setups. Use Aura Console, service settings, query tools, and APIs provided for your tier.

> **Version note:** In Neo4j Community Edition starting from 2026.02.3, a `web` directory may hold the Neo4j Browser bundle; Browser packaging differs between Community and Enterprise. This is UI distribution packaging, not a directory holding nodes/relationships.

### 3.2. Querying paths from the DBMS instead of guessing

If you have permission to view settings, run in Neo4j Browser or Cypher Shell:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'server.directories.'
RETURN name, value
ORDER BY name;
~~~

This query confirms the directory settings Neo4j sees. Certain settings and `SHOW SETTINGS` privileges depend on version and edition; if the command is not permitted, ask an administrator or inspect readable config files. Never modify internal database files just to locate storage paths.

On Linux installed via package, you can inspect config paths with **read-only** commands:

~~~bash
# If granted read permission
ls -l /etc/neo4j
ls -ld /var/lib/neo4j/data /var/log/neo4j
~~~

With Docker, check mounted paths:

~~~bash
docker compose ps
docker compose exec neo4j sh -c 'ls -ld /conf /data /logs /import /plugins'
~~~

Run these commands on a **lab environment** you control; some images/permissions may restrict listing all directories. To inspect container mounts from the host, use `docker inspect` instead of poking into hidden volume paths under Docker Engine's directory.

## 4. The `conf` Directory: Managing Configuration Properly

### 4.1. Key files

| File | Function |
| --- | --- |
| `neo4j.conf` | Main configuration file: networking, memory, directories, security, and other settings |
| `neo4j-admin.conf` | Configuration for supported administrative commands |
| `user-logs.xml` | Log4j configuration for user logs such as `neo4j.log` |
| `server-logs.xml` | Log4j configuration for `debug.log` and query/security/HTTP logs per edition/settings |

Configuration files may hold paths, hostnames, security settings, resource limits, and logging rules. **Do not put passwords/tokens directly into committed files.** Only change settings verified in Neo4j documentation for your exact version.

### 4.2. Example directory settings

In native Neo4j Server, some available settings:

~~~properties
# Illustrative directory settings for Neo4j 5.x/2026.x
server.directories.data=data
server.directories.logs=logs
server.directories.import=import
server.directories.plugins=plugins
server.directories.transaction.logs.root=data/transactions
server.directories.dumps.root=data/dumps
~~~

These are **illustrative values for understanding setting names**, not a snippet to paste verbatim into every `neo4j.conf`. Debian/RPM packages already establish their own path layout. Changing `server.directories.data` to a new folder without properly migrating data can make Neo4j start with a different database or fail.

**Transaction logs** are separated via `server.directories.transaction.logs.root`; by default they reside under `data/transactions`. **Dumps** (when created via admin tools) have their own root; never treat `data` as a folder you can freely rename while the database is running.

### 4.3. Environment variables in Docker

Neo4j Docker supports converting setting names into environment variables. Standard conversion rules:

- Prefix `NEO4J_`.
- Each dot `.` in the setting name → single underscore `_`.
- Each underscore `_` in the setting name → double underscore `__`.

Example:

~~~yaml
environment:
  NEO4J_server_memory_heap_initial__size: "512m"
  NEO4J_server_memory_heap_max__size: "512m"
  NEO4J_server_memory_pagecache_size: "512m"
~~~

These map to `server.memory.heap.initial_size`, `server.memory.heap.max_size`, and `server.memory.pagecache.size`. These values are only starting points for a **small lab**, not production sizing. Per Neo4j Docker docs, settings provided via environment variables take precedence over corresponding values in `/conf`.

### 4.4. Be careful when bind-mounting `/conf`

Adding a mount like:

~~~yaml
volumes:
  - ./conf:/conf:ro
~~~

causes your supplied `/conf` directory to **replace** the image's built-in configuration files. An empty directory or missing `neo4j.conf`/Log4j files can prevent the container from starting properly. To use a custom `/conf`, provide a **complete, version-matched configuration set**; Neo4j docs explain using the image's `dump-config` command to export baseline configs before editing. When supplying custom Docker network configs, check `server.default_listen_address=0.0.0.0` so the service listens inside the container.

In labs, when changing only a few settings, using **environment variables** is clearer and easier to control. In production, configuration should be version-controlled, diffed on upgrades, and separated from credentials.

## 5. The `data` Directory: Storing the Graph and Consistency

### 5.1. What lives inside `data`?

By default, `data` holds **database stores**, related metadata, user/auth data (in the system database), transaction logs, and internal files/directories required by Neo4j. When you run:

~~~cypher
MERGE (person:Person {personId: 'directory-lab-001'})
  ON CREATE SET person.name = 'An'
RETURN person;
~~~

Neo4j writes nodes, labels, properties, and related structures into **store files** under `data`; they are not separate `.json` or `.csv` files per node. Creating relationships, indexes, or constraints updates the corresponding internal structures and metadata.

**Never manually edit, move, or delete database files while the DBMS is running.** The internal layout under `data/databases` can change between versions. To modify graph contents, use Cypher and transactions; to move or restore a database, use `neo4j-admin`, backup/restore, or version-appropriate migration procedures.

### 5.2. How do transaction logs differ from `debug.log`?

| Characteristic | **Transaction logs** | **Operational logs (`logs`)** |
| --- | --- | --- |
| Default location | `data/transactions/<database>` | `logs` |
| Purpose | Record transactional changes, supporting consistency and recovery | Help monitor startup, errors, activity, and performance |
| Critical to database recovery? | **Yes**; part of the database engine | Cannot be used alone to reconstruct graph data |
| Arbitrarily readable in a text editor? | Not standard human-readable text logs | Readable with appropriate log viewers |
| Safe to delete to free disk space? | **Never delete manually** | Manage via log rotation/retention, do not delete indiscriminately |

Transactions creating nodes/relationships, indexes, or constraints are tracked by Neo4j to maintain consistency. If `data` is lost or transaction logs are tampered with, keeping `neo4j.log` alone **cannot** rebuild the database.

### 5.3. Volumes are not backups

Attaching `/data` to a Docker named volume preserves data across container replacements. It does **not** protect against volume deletion, disk failure, application bugs, or accidental Cypher delete queries.

- **Persistence:** keeps the data store outside the container's writable layer.
- **Backup:** creates a consistent copy using tools supported for your Neo4j edition.
- **Restore:** tests restoring a backup in an isolated environment.
- **Migration/upgrade:** verifies store and version compatibility before swapping images.

**Never copy `data` files while the server is actively writing and assume it is a valid backup.** For critical systems, follow official Neo4j backup/restore procedures matching Community/Enterprise capabilities and verify restores.

## 6. The `logs` Directory: Reading the Right Log Type

Neo4j uses a logging framework to record service status and operational events. Individual files may or may not exist depending on edition and configuration.

| File / tool | Typical contents | When to inspect |
| --- | --- | --- |
| `neo4j.log` | General startup/shutdown and server status info | DBMS fails to start or keeps restarting |
| `debug.log` | Deep technical diagnostics, errors, and stack traces | Startup failures, incidents needing deeper diagnosis |
| `query.log` | Query records per query logging policy; depends on edition/settings | Investigating slow queries, tuning |
| `security.log` | Security/authentication events; depends on edition | Auditing logins and privileges |
| `http.log` | HTTP requests if enabled | Debugging HTTP endpoint issues |
| `gc.log` | JVM garbage collection events if enabled | Analyzing memory pressure |
| `docker compose logs neo4j` | Container/service STDOUT/STDERR | Docker startup, config errors, and process output |
| `journalctl -u neo4j` | `systemd` service logs, common for Debian/RPM packages | Service fails to start on Linux |

**Do not assume `query.log` or `security.log` always exist on Community Edition.** They may be Enterprise features or disabled in configuration. On Neo4j 2025.x/2026.x, `debug.log` uses JSON format by default; log viewers should support parsing JSON records when filtering by fields.

Docker check examples:

~~~bash
docker compose logs --tail=100 neo4j
docker compose exec neo4j sh -c 'ls -lah /logs'
~~~

Example reading a log file (if present and permitted):

~~~bash
docker compose exec neo4j sh -c 'tail -n 50 /logs/debug.log'
~~~

When reading logs to investigate queries, **do not include passwords, tokens, or parameters containing personal data in reports**. Issue analyses should record timestamp, DBMS version, database, error type, and request/transaction ID if available. To control disk growth, configure **log rotation and retention** via version-matched Log4j settings; avoid deleting log files currently held open by the process.

## 7. The `import` Directory: Where `LOAD CSV` Actually Looks

For security reasons, Neo4j typically restricts local files read by `LOAD CSV` to the `import` directory. Suppose you have `students.csv`:

~~~csv
studentId,name
S-001,An
S-002,Binh
~~~

When placed at **`<NEO4J_HOME>/import/students.csv`** (native) or **`/import/students.csv`** (Docker), run in Browser:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///students.csv' AS row
RETURN row.studentId AS studentId, row.name AS name;
~~~

Expected output returns two student rows. Crucial point: the `file:///students.csv` URI is read by Neo4j **from the server's filesystem**, not from the Browser user's laptop. Therefore:

- For containerized Neo4j, the CSV file must be visible **inside the container** at `/import/students.csv`; a CSV in your host's Downloads folder does not automatically appear inside the container.
- For Neo4j on a remote server, `file:///...` resolves on the **server side**; Java Driver/Bolt does not transfer local client files alongside a query.
- With AuraDB, you do not have direct OS-level upload access to `/import`; use service-supported import methods such as an accessible HTTPS URL or Aura import tools.
- For large imports, learn about `neo4j-admin database import` and version-appropriate workflows; **never** run admin import commands casually against a live database.

After verifying the import file works:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///students.csv' AS row
MERGE (s:Student {studentId: row.studentId})
SET s.name = row.name
RETURN count(s) AS processedRows;
~~~

In this lab, `processedRows = 2`. For real datasets, create a **uniqueness constraint** on `Student.studentId`, validate source data, and batch appropriately. This section introduces the import path and does not replace dedicated data-import lessons.

## 8. The `plugins`, `labs`, `products`, and `lib` Directories

Neo4j can be extended with custom **procedures/functions** and specialized libraries. Plugins are typically distributed as **JAR** files:

- **`plugins`:** where plugin JARs to be loaded at Neo4j startup are placed.
- **`labs`:** may contain bundled APOC Core; must be installed/enabled per instructions.
- **`products`:** add-on products/plugins included in the distribution, varying by edition/version.
- **`lib`:** server runtime libraries; **do not use it as a drop folder for arbitrary plugins**.

### 8.1. Installing a plugin properly

1. Identify the running **Neo4j DBMS version and edition**. For example:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

2. Check the **plugin's compatibility matrix** and any permission/license requirements. A JAR valid for Neo4j 5.26 may **not** be compatible with Neo4j 2026.10.
3. Obtain the JAR from an **official source**, verifying checksums/signatures when provided by the publisher.
4. Place the JAR into `plugins` with **read permissions for the Neo4j process**, or use the official plugin mechanism of Desktop/Docker.
5. Allowlist only the required procedures when genuinely needed, then **restart Neo4j** to load the JAR.
6. Check startup logs and verify procedures/functions exist using version-appropriate commands.

Example query to find procedures starting with `apoc` (if the plugin is installed):

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name
LIMIT 20;
~~~

If the result is empty, the plugin may not be loaded, may be incompatible, may not be allowlisted, or the procedure may not exist in the installed version. **Never** "fix" this in real environments by setting `dbms.security.procedures.unrestricted` to a wildcard.

### 8.2. The APOC case

**APOC Core** is a popular procedure/function library. For servers shipping the JAR in `labs`, Neo4j docs instruct copying the **version-matched** JAR into `plugins` and restarting; Neo4j Desktop has a plugin manager UI; Docker offers the `NEO4J_PLUGINS` convenience variable for development environments.

Example when **APOC is genuinely needed** in Docker dev:

~~~yaml
environment:
  NEO4J_PLUGINS: '["apoc"]'
~~~

This utility downloads/installs plugins at container startup, convenient for learning and testing; **it is not recommended as a production plugin management method**. In production, control plugin JARs, versions, and privileges like audited dependencies. Note that if Docker mounts `/plugins` **read-only**, `NEO4J_PLUGINS` may need write access to copy/download JARs; pick one consistent strategy rather than conflicting mounts.

**APOC Extended**, **Graph Data Science**, and other plugins carry their own version/edition/license requirements. Do not assume every JAR under `products` is enabled automatically.

## 9. Docker Compose Lab: Separating Data, Logs, and CSV Imports

### 9.1. Host directory structure

Create a standalone lab directory, for example:

~~~text
neo4j-paths-lab/
├── compose.yaml
├── .env                      # Lab password, do not commit
├── .gitignore
└── import/
    └── students.csv          # Illustrative CSV from Section 7
~~~

`.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
secrets/
~~~

Do not create a `data` directory in the source tree if using a **named volume**; Docker manages the actual storage location. The lab `import` folder holds only **shareable source files**, which may be tracked in Git if free of personal data or secrets.

### 9.2. `compose.yaml`

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set NEO4J_PASSWORD in .env}"
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "512m"
      NEO4J_server_memory_pagecache_size: "512m"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./import:/import:ro
    restart: unless-stopped
    stop_grace_period: 2m

volumes:
  neo4j_data:
  neo4j_logs:
~~~

Create `.env` **for lab use only**:

~~~dotenv
NEO4J_PASSWORD=REPLACE_WITH_UNIQUE_STRONG_PASSWORD
~~~

Replace the placeholder with your own password before starting. `.env` is not a secret manager; never commit it to Git. In real deployments, use **Compose secrets / `NEO4J_AUTH_FILE`** or a proper secret manager to deliver credentials. In this learning example, `NEO4J_AUTH` only **initializes the password** when the database volume has no users yet.

**Role of each mount:**

| Declaration | Meaning | After replacing the container |
| --- | --- | --- |
| `neo4j_data:/data` | Graph and critical database files | Preserved unless volume is deleted |
| `neo4j_logs:/logs` | Logs outside the container's writable layer | Preserved unless volume is deleted |
| `./import:/import:ro` | Host `./import` folder readable by the server | Intact on host; Neo4j cannot write here |

This example intentionally **does not mount `/conf`** to avoid replacing the image's full config set; the base config stays intact while we override a few settings via environment variables.

### 9.3. Starting and inspecting files

From the lab directory:

~~~bash
docker compose config --quiet
docker compose pull neo4j
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Once the DBMS is ready, open `http://localhost:7474/browser/` and connect with `bolt://localhost:7687`, user `neo4j`, and the password from `.env`. Run:

~~~cypher
RETURN 'Neo4j file structure lab ready' AS message;
~~~

From a terminal on the host (Linux/macOS Bash; Windows PowerShell can run the same `docker compose exec` commands):

~~~bash
docker compose exec neo4j sh -c 'ls -ld /data /logs /import /plugins'
docker compose exec neo4j sh -c 'ls -lah /import'
docker compose exec neo4j sh -c 'ls -lah /logs'
~~~

Inside `/import`, you should see `students.csv`. Next, run the `LOAD CSV` query from Section 7 and a `MATCH` query to verify the graph:

~~~cypher
MATCH (s:Student)
WHERE s.studentId IN ['S-001', 'S-002']
RETURN s.studentId AS id, s.name AS name
ORDER BY id;
~~~

### 9.4. Verifying data persistence across container recreation

~~~bash
# Remove Compose container/network, BUT KEEP NAMED VOLUMES
docker compose down

# Recreate container from the same config and volumes
docker compose up -d
docker compose ps
~~~

Log back in using the **existing password stored in the database**, then re-run `MATCH` from Section 9.3. If both students remain, the `/data` mount worked as intended. Named volumes typically receive the Compose project prefix, e.g., `neo4j-paths-lab_neo4j_data`; changing the project name/`-p` creates a different volume.

**Do not run `docker compose down -v` on a database you want to keep:** the `-v` flag deletes this project's named volumes, wiping graphs, transaction logs, and users. Never delete a volume just to change a password or tweak configuration.

## 10. Managing Permissions and Directory Operations

### 10.1. Minimum file permissions

Neo4j needs **read** access to `conf`, `import`, and `plugins`; it needs **read and write** access to `data` and `logs`. If attaching host folders via bind mounts, ownership must allow the Neo4j user inside the container to access them.

In official Neo4j Docker images, the process typically runs as the `neo4j` user (commonly UID **7474**). Depending on startup configuration, the entrypoint may adjust mount ownership; setting arbitrary `--user` flags can prevent the server from reading or writing files.

- On Linux, apply least-privilege permissions and avoid `chmod 777` as a "quick fix"; use the service account and appropriate group.
- On Windows, restrict ACLs on data/config/log directories to the service account and required admin groups.
- For volumes holding real data, manage access through organizational controls and maintain backups.
- Never publicly share `data`, log directories, or secret files; they can expose internal structure or sensitive details.

### 10.2. Moving or upgrading directories

| Goal | Safer approach |
| --- | --- |
| Relocate logs | Configure `server.directories.logs` or mount `/logs` properly, verify permissions and rotation |
| Relocate database | Stop/isolate the DBMS, follow Neo4j migration/restore procedures; verify data consistency |
| Import more CSVs | Place files in the configured `import` directory, grant read access, run `LOAD CSV` |
| Add a plugin | Check compatibility, place JAR in `plugins`, configure allowlist/permissions, restart |
| Upgrade Docker image | Review release/migration guides and backup/restore before reusing volumes |
| Retain logs for investigation | Mount `/logs`, configure retention, avoid logging credentials |

**Note:** Persistent `/data` only prevents data loss caused by **container lifecycles**. It does not replace scheduled backups, restore testing, capacity management, or I/O monitoring.

## 11. Troubleshooting Common Issues

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| Neo4j fails to start after mounting `./conf:/conf` | Empty `/conf`, missing config files, invalid setting, or missing read permissions | Remove the mount in lab and use env vars; for custom configs generate a full set via `dump-config` from the matching image |
| `Permission denied` on `/data` or `/logs` | Neo4j user lacks write permission on bind mount | Check owner/ACLs and Docker user; use named volumes for labs |
| Graph disappears after container restart | `/data` not mounted, volume deleted, or Compose project name changed | Inspect `docker volume ls`, mounts, and `-p` flag; find the old volume before making changes |
| Rapid disk growth in `data` | Graph, indexes, or transaction logs growing | Inspect growth and configure retention per docs; **never delete transaction logs manually** |
| Cannot find `query.log` | Feature may be edition-specific or disabled | Check edition and logging config instead of assuming the file always exists |
| `LOAD CSV` reports file not found | CSV only on host, not mounted into `/import`, wrong filename/extension | Check `ls /import` **inside the container**, then use `file:///students.csv` |
| Cannot write output CSV into `/import` | Read-only `:ro` mount; user/DBMS lacks write permission | Keep import read-only in labs; use a separate export pipeline if genuinely needed |
| Plugin JAR copied but procedure does not appear | Not restarted, incompatible JAR, or missing config/privileges | Check startup logs, version, edition, and `SHOW PROCEDURES` |
| `NEO4J_PLUGINS` fails with `/plugins:ro` mount | Startup helper needs write access to copy/download JARs | Use a writable mount in dev or place version-matched JARs manually |
| `debug.log` looks hard to read as plain text | Current release may write JSON logs | Use a JSON log viewer; do not arbitrarily alter debug log format |
| Changed `data` path and Neo4j looks like an empty DB | DBMS points to an empty folder or no longer sees the original store | Stop making changes, inspect config and backups; never create/delete store files manually |

When troubleshooting, verify in order: **DBMS version/edition → actual file paths → mounts/permissions → startup logs → configuration → query**. Separate path errors, data errors, and permission errors before attempting any data-modifying commands.

## 12. Hands-on Exercises

### Exercise 1 — Mapping directories for a real environment

Choose one installation type: **ZIP/TAR**, **Debian/RPM package**, or **Docker**. Record the actual paths for `conf`, `data`, `logs`, `import`, and `plugins`. Explain why you cannot assume they all live under one root folder when installed via APT/RPM.

**Expected deliverable:** a path table, verification commands, and notes on read/write permissions.

### Exercise 2 — Verifying persistence and CSV import

Using the Compose setup in Section 9, build the graph from `students.csv`. Run `docker compose down`, then `docker compose up -d`. Query the two `Student` nodes again, capture the output, and explain why the graph survives yet a volume should not be treated as a backup.

**Expected deliverable:** both students remain in the database; accurately identify the volume holding `/data`.

### Exercise 3 — Distinguishing operational logs from transaction logs

A team sees `data/transactions` consuming disk space and plans to delete it thinking it is `debug.log`. Explain the role of transaction logs, list at least two risks of deleting them manually, and propose proper disk-space management.

### Exercise 4 — Adding APOC properly

You want to use an APOC procedure in a lab. Describe how to check the Neo4j version, pick a compatible APOC release, use `NEO4J_PLUGINS` or place the JAR in `plugins`, restart, and verify via `SHOW PROCEDURES`. Explain why plugin files should not be placed in `lib`.

### Completion Checklist

- [ ] Can accurately explain the purpose of `conf`, `data`, `logs`, `import`, and `plugins`.
- [ ] Can state directory differences across ZIP/TAR, Debian/RPM, Docker, and Desktop.
- [ ] Distinguish transaction logs from debug/query/security logs.
- [ ] Know how to check settings/paths and mounts of the exact Neo4j instance.
- [ ] Ran Compose with `/data` and `/logs` as named volumes.
- [ ] Read `students.csv` from `/import` and created nodes via `LOAD CSV`.
- [ ] Verified the graph survives `docker compose down` and `up -d`.
- [ ] Can explain why `data`, transaction logs, or volumes must not be deleted while data is needed.
- [ ] Know how to verify plugin version compatibility and JAR placement.
- [ ] Know how to manage file permissions, log retention, and backups appropriately.

## 13. Official References

- [Neo4j Operations Manual — Default file locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/) — paths by installation method and file permissions.
- [Neo4j Operations Manual — Configuration](https://neo4j.com/docs/operations-manual/current/configuration/) — `neo4j.conf` and supported settings.
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/) — log types, Log4j, and retention policies.
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/) — purpose and location of transaction logs.
- [Neo4j Operations Manual — Persisting data with Docker volumes](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/) — `/data`, `/logs`, `/conf`, `/import`, `/plugins`.
- [Neo4j Operations Manual — Modify Docker configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/) — environment variables, `/conf`, and `dump-config`.
- [Neo4j Operations Manual — Configure plugins](https://neo4j.com/docs/operations-manual/current/configuration/plugins/) — plugin JARs, versions, and procedure privileges.
- [Neo4j Operations Manual — Docker plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/) — `NEO4J_PLUGINS` and `/plugins` mounts.
- [Neo4j Getting Started — CSV files](https://neo4j.com/docs/getting-started/data-import/csv-files/) — `LOAD CSV` and `file:///` paths.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — handling data across Neo4j version changes.

**Key takeaway:** `conf` controls DBMS behavior; `data` holds graph data and transaction logs; `logs` supports operations; `import` supplies source data; `plugins` extends functionality. Correct paths, file permissions, and storage policies are the foundation for learning Cypher, optimizing graphs, and operating Neo4j reliably.
