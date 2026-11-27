# Launching with Docker Compose Using Persistent Storage and Custom Configuration

## 1. Objectives and Outcomes

In Neo4j, data is stored as a **property graph**: **nodes** represent entities, **relationships** represent directed associations, and **properties** store attributes of nodes/relationships. To practice **Cypher**, indexes, constraints, path queries, data import, or connecting via the **Java Driver** and **Spring Data Neo4j**, learners need a Neo4j DBMS running reliably with a reproducible configuration that **does not lose data when recreating containers**.

**Docker Compose** lets you describe the Neo4j image, network ports, environment variables, volumes, and secrets in configuration files. The same Compose definition can be reused across developer machines or in integration test pipelines.

After this lesson, you will:

1. Write a `compose.yaml` that runs Neo4j with a **pinned image version**, without relying on the `latest` tag.
2. Use **named volumes** for `/data` and `/logs` so data persists after a container is replaced.
3. Separate environment-specific parameters into `.env` or `--env-file`; use **Docker Compose secrets** for initial credentials.
4. Check status, log in, run Cypher, and read data back after `docker compose down` and `docker compose up -d`.
5. Distinguish configuration on the host, inside the container, and in Java/Spring Boot apps; troubleshoot common errors systematically.

> **Scope:** This is a configuration for **a single Neo4j Community Edition instance for local learning/development**. Examples use the official `neo4j:2026.10.2` image. For production deployment, you must separately design TLS, monitoring, backup/restore, secret policies, upgrades, resource sizing, and high availability.

## 2. How It Works: Service, Container, Volume, and Configuration

Compose does not create a database by itself; it instructs Docker to run a **service** named `neo4j` from the selected image. Neo4j creates the database inside the internal `/data` directory when the DBMS starts for the first time. A **volume** maps this directory to storage outside the container's writable layer, so replacing the container does not delete the graph.

~~~mermaid
flowchart LR
    U["Neo4j Browser / Java Driver on host"] -->|"HTTP :7474 / Bolt :7687"| C["Service neo4j<br/>Container from pinned image"]
    C -->|"writes DB"| D[("Named volume neo4j_data<br/>mounted at /data")]
    C -->|"writes logs"| L[("Named volume neo4j_logs<br/>mounted at /logs")]
    E[".env / --env-file<br/>version, ports, memory"] --> C
    S["Compose secret<br/>initial credentials"] --> C
~~~

### 2.1. Different Configuration Layers

| Component | Purpose | Read by whom? | Commit to Git? |
| --- | --- | --- | --- |
| `compose.yaml` | Describes services, image, ports, volumes, and secrets | Docker Compose | Yes, after removing secrets |
| `.env` or `.env.dev` | Values interpolated into Compose: image tag, host ports, memory, secret path | **Compose CLI** | Usually no; publish `.env.example` |
| `environment` in Compose | Variables passed into the container; Neo4j reads `NEO4J_*` variables | Container/Neo4j | Yes if containing no secrets |
| `secrets/neo4j_auth.txt` | Initialization string `neo4j/<password>` | Docker secret → Neo4j | **No** |
| `neo4j_data` | Database, metadata, and critical data | Neo4j inside container | Not part of Git source |
| `neo4j_logs` | Application logs for diagnostics | Neo4j inside container | Not part of Git source |

**Common pitfall:** putting `NEO4J_PASSWORD=...` in `.env` only makes that variable available for Compose interpolation. Variables in `.env` **do not automatically enter the container** unless referenced in `environment`, `env_file`, or an appropriate Compose attribute. In this lesson, the password is supplied via a **secret file**, not through `.env`.

### 2.2. How Do Named Volumes and Bind Mounts Differ?

| Type | Example in Compose | Advantages | Things to watch |
| --- | --- | --- | --- |
| **Named volume** | `neo4j_data:/data` | Docker manages location and lifecycle; fewer host path permission issues | Actual volume name usually has a **Compose project prefix** |
| **Bind mount** | `./data:/data` | Files visible directly in host folder, convenient for external tools | Prone to permission errors, OS path differences, accidental folder deletion |
| No mount | No mapping for `/data` | Very quick for testing an image | **Data lost when container is removed/replaced** |

> Stopping and restarting the same container does not delete its writable layer. The main risk of an **unmounted** configuration is when the container is **removed/recreated**. Therefore, attach `/data` to a volume from the start.

## 3. Prerequisites

You need a Windows, macOS, or Linux machine running **Docker Engine/Docker Desktop** and **Docker Compose v2**. For the lab-level memory settings in the examples, reserve enough RAM for the OS, Docker, and Neo4j; having roughly **4 GB or more of RAM available to Docker** makes practice smoother. Disk capacity must cover the image, graph, logs, and generated data. Do not treat these levels as production sizing.

Verify the environment:

~~~bash
docker --version
docker compose version
docker info
~~~

- `docker --version` confirms Docker CLI is installed.
- `docker compose version` confirms the Compose v2 plugin.
- `docker info` confirms the CLI can reach the Docker daemon/Engine.

If `docker info` fails because it cannot connect to the daemon, start Docker Desktop or the Docker service and re-check. If another local Neo4j instance is on the machine, check ports `7474` (HTTP) and `7687` (Bolt) before running an additional instance.

**No host Java installation is required just to run Neo4j with Docker:** the Neo4j image already bundles the appropriate server runtime. If you also write a Spring Boot application on the host, that application needs its own compatible JDK and Java Driver.

## 4. Preparing the Project Directory Structure

Create a dedicated directory, such as `neo4j-compose-lab`:

~~~text
neo4j-compose-lab/
├── compose.yaml
├── .env
├── .env.example
├── .gitignore
└── secrets/
    └── neo4j_auth.txt
~~~

All `docker compose` examples below are run from the **directory containing `compose.yaml`**. In this article, these are files **the learner creates in the lab**, not new files to add to the documentation module source.

### 4.1. `compose.yaml` — service configuration

~~~yaml
services:
  neo4j:
    image: "${NEO4J_IMAGE:-neo4j:2026.10.2}"

    ports:
      - "127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474"
      - "127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687"

    environment:
      NEO4J_AUTH_FILE: /run/secrets/neo4j_auth
      NEO4J_server_memory_heap_initial__size: "${NEO4J_HEAP:-512m}"
      NEO4J_server_memory_heap_max__size: "${NEO4J_HEAP:-512m}"
      NEO4J_server_memory_pagecache_size: "${NEO4J_PAGECACHE:-512m}"

    secrets:
      - neo4j_auth

    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

    restart: unless-stopped
    stop_grace_period: 2m

secrets:
  neo4j_auth:
    file: "${NEO4J_AUTH_SOURCE:-./secrets/neo4j_auth.txt}"

volumes:
  neo4j_data:
  neo4j_logs:
~~~

**Explanation of key choices:**

- `image` reads from `NEO4J_IMAGE`, defaulting to `neo4j:2026.10.2` — an official Community Edition tag published by Neo4j. Pin the version so lab results are repeatable across machines; when upgrading, perform a data compatibility check procedure.
- `127.0.0.1:7474:7474` and `127.0.0.1:7687:7687` publish HTTP and Bolt only to **host loopback**. Access from other machines requires dedicated network design and TLS; do not casually switch to `0.0.0.0`.
- `NEO4J_AUTH_FILE` points to the **file mounted by the Compose secret** inside the container, not to a host path.
- The three `NEO4J_server_memory_*` variables use the Neo4j setting-to-environment-variable conversion rule: **dot `.` → `_`, underscore `_` → `__`**. For example, `server.memory.heap.max_size` becomes `NEO4J_server_memory_heap_max__size`.
- `neo4j_data:/data` preserves the database across container replacements; `neo4j_logs:/logs` keeps logs for troubleshooting.
- `stop_grace_period: 2m` gives Neo4j extra time for a clean shutdown before Docker may forcefully terminate it. Adjust according to actual workload.
- `restart: unless-stopped` lets Docker restart the container if the service/daemon restarts, unless stopped manually.

This is a configuration for **a single development instance**; it does not enforce production-grade TLS, backups, or resource isolation.

### 4.2. `.env` — machine-specific configuration

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/neo4j_auth.txt
~~~

You can share **`.env.example`** with **non-secret sample values** so teammates know which variables to fill in. Each person creates their own `.env`. On machines running multiple instances, change the host ports in `NEO4J_HTTP_PORT` and `NEO4J_BOLT_PORT`; **container ports remain 7474/7687** unless you change Neo4j's listen settings.

For example, setting `NEO4J_HTTP_PORT=7475` and `NEO4J_BOLT_PORT=7688` makes the **host** URLs `http://localhost:7475` and `bolt://localhost:7688`. Inside the Compose network, another app still calls the Neo4j service at `neo4j:7687`.

### 4.3. Creating the authentication secret — never commit passwords

Create `secrets/neo4j_auth.txt` (UTF-8 text) with **a single line**:

~~~text
neo4j/REPLACE_WITH_YOUR_OWN_LONG_RANDOM_PASSWORD
~~~

Replace the placeholder with a unique, strong password; do not use the sample string in actual runs. This file is only used by Neo4j when **initializing authentication for a database that does not exist yet**. Changing the file contents after the database has been initialized **does not automatically change the existing account's password**.

In `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
secrets/
~~~

If you use a separate config file containing secrets, add that file to the exclusion list as well. **A Compose secret on a dev machine is a host file mounted into the container**; do not assume it is automatically encrypted or protected like a secret manager. Protect directory permissions and use your infrastructure's secret mechanism for real deployments.

### 4.4. Validating Compose before launching

~~~bash
docker compose config --quiet
docker compose config --images
~~~

`config --quiet` checks syntax and config interpolation; `config --images` shows the actual image Compose will use. If `NEO4J_AUTH_SOURCE` points to the wrong path or the secret file does not exist yet, fix the path and create the file before starting. **Do not** paste config output containing sensitive credentials into tickets or chat.

## 5. Starting Neo4j and Confirming the DBMS Is Ready

In the project directory:

~~~bash
docker compose pull neo4j
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Explanation:

1. `pull` downloads the image for the pinned tag; the first run may require Internet access.
2. `up -d` creates the volumes, secret mount, network, and container, then starts the service in the background.
3. `ps` shows whether the service is `running`; **running does not yet mean the server is accepting queries**.
4. `logs` helps check initial authentication errors, secret read permissions, memory, ports, or the Neo4j startup sequence.

Wait until the logs report Neo4j is ready, then open **http://localhost:7474** and log in with:

- **Username:** `neo4j`.
- **Password:** the part after `/` in `secrets/neo4j_auth.txt`.
- **Database:** typically `neo4j` for a fresh lab; verify the actual value in the DBMS.

Neo4j Browser uses the HTTP UI; Java/Spring Data Neo4j applications use **Bolt** via `bolt://localhost:7687` (when running on the host). Do not use the HTTP URL to initialize the Neo4j Java Driver.

### 5.1. Verifying with Cypher

Run in Browser:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Expected result: one row with `ok = 1`. Next, verify the exact version/edition:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

`versions` should contain the actual DBMS version, e.g., `2026.10.2`, and `edition` indicates Community/Enterprise. Having the right image name alone is not enough to prove you are connected to the intended DBMS if multiple containers or published ports exist on the machine.

If your terminal supports interactivity, you can open Cypher Shell inside the container:

~~~bash
docker compose exec neo4j cypher-shell -u neo4j -d neo4j
~~~

Cypher Shell will prompt for the password if not supplied via flags. This avoids putting plaintext passwords into command history; if the shell environment is non-interactive, prefer Browser or an appropriate secure credential-passing mechanism.

## 6. Critical Test: Data Persists After Container Recreation

### 6.1. Creating a small property graph

Example modeling a student enrolling in a course:

~~~cypher
MERGE (s:Student {studentId: 'docker-lab-001'})
  ON CREATE SET s.name = 'An'
MERGE (c:Course {courseId: 'neo4j-compose'})
  ON CREATE SET c.title = 'Neo4j with Docker Compose'
MERGE (s)-[:ENROLLED_IN]->(c)
RETURN s.name AS student, c.title AS course;
~~~

Read the relationship and path:

~~~cypher
MATCH p = (:Student {studentId: 'docker-lab-001'})
          -[:ENROLLED_IN]->
          (:Course {courseId: 'neo4j-compose'})
RETURN p;
~~~

Neo4j returns a path containing the `Student` node, the `Course` node, and the `ENROLLED_IN` relationship. `MERGE` is convenient for repeatable labs; with concurrent workloads and production data, you still need a **uniqueness constraint** on business keys and proper transaction handling.

### 6.2. Stopping, removing, and restarting the container

Run in the **exact same Compose directory/project** used earlier:

~~~bash
# Stop and remove Compose container/network, BUT keep named volumes
docker compose down

# Create a new container from the same image and volumes
docker compose up -d
docker compose ps
~~~

Wait for Neo4j to finish starting, log in again, and re-run the `MATCH p = ... RETURN p` query from Section 6.1. If the old path is still there, data was preserved across the container lifecycle by the named volume.

**Why does it persist?** Compose manages the volumes declared under top-level `volumes`. When `down` is run without the `-v` flag, Docker preserves the volumes and re-attaches them at `/data` on `up`. Data, accounts, and metadata inside the volume are reused.

**Commands to clearly distinguish:**

| Command | Container and network | Named volume containing database |
| --- | --- | --- |
| `docker compose stop` | Stops, keeps container | Preserved |
| `docker compose start` | Starts stopped container | Preserved |
| `docker compose down` | Removes Compose container/network | **Preserved** by default |
| `docker compose up -d --force-recreate` | Recreates container | **Preserved** if volume/project config stays the same |
| `docker compose down -v` | Removes container/network **and Compose-managed volumes** | **Deletes data in the example volume** |
| `docker volume prune` | Not an operation specific to this project | May delete unreferenced volumes; do not run while data needs to be kept |

> **Important warning:** `docker compose down -v` or deleting a named volume is a **data-loss action**. Never run it just to "start clean" on a valuable database. Only perform it when intentionally destroying an environment and after verifying backups.

### 6.3. Identifying the actual volume name

~~~bash
docker compose ls
docker volume ls
docker compose ps
~~~

Compose typically names the actual volume as **`<project>_neo4j_data`**, where `project` defaults to the directory name or comes from `COMPOSE_PROJECT_NAME` / the `-p` flag. If you change the project name, Compose may create a **different volume**, giving the impression that "the database disappeared" even though the old volume still exists.

Therefore, **do not arbitrarily change the project name** between `down` and `up`. If you want a project-independent volume name, you can declare `name:` under the volume, but you must then guard against multiple projects sharing the same database. In labs, keeping the same project name is sufficient.

## 7. Using Separate Configurations per Environment

To avoid mixing data, ports, and credentials between **dev** and **test**, you can create two env files and two matching secrets without duplicating `compose.yaml`.

### 7.1. Two environment files

`.env.dev`:

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/dev_auth.txt
~~~

`.env.test`:

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7475
NEO4J_BOLT_PORT=7688
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/test_auth.txt
~~~

Create two separate secrets with different passwords in `neo4j/<password>` format. Exclude the value files from Git and share an `.env.example` template.

### 7.2. Running with `--env-file` and distinct project names

~~~bash
# Run for dev environment
docker compose --env-file .env.dev -p neo4j-dev up -d

# Run for test environment
docker compose --env-file .env.test -p neo4j-test up -d
~~~

Result:

- **Dev:** `http://localhost:7474`, `bolt://localhost:7687`, and volumes prefixed with `neo4j-dev`.
- **Test:** `http://localhost:7475`, `bolt://localhost:7688`, and volumes prefixed with `neo4j-test`.
- Both Neo4j services can run concurrently if host resources and ports permit; they do not share data volumes.

When reading logs or stopping, **use the exact matching env-file and project parameters**:

~~~bash
docker compose --env-file .env.dev -p neo4j-dev logs --tail=80 neo4j
docker compose --env-file .env.test -p neo4j-test ps
docker compose --env-file .env.test -p neo4j-test down
~~~

If you run `docker compose down` without `-p`, Compose may target a **different project** and fail to stop the intended instance. Standardize the commands and project names in your team documentation.

### 7.3. Customizing Neo4j via environment variables

Neo4j Docker translates variables starting with `NEO4J_` into settings in `neo4j.conf` using the rule in Section 4.1. Example additions under `environment`:

~~~yaml
NEO4J_server_memory_heap_initial__size: "512m"
NEO4J_server_memory_heap_max__size: "512m"
NEO4J_server_memory_pagecache_size: "512m"
~~~

These correspond to `server.memory.heap.initial_size`, `server.memory.heap.max_size`, and `server.memory.pagecache.size`. Choose values based on real resources, and avoid setting heap + page cache near the total RAM ceiling because the JVM and other processes also require off-heap memory.

If you want to configure Cypher, logging, or database path settings, **look up the exact setting names supported by your Neo4j version**. A setting name from Neo4j 4.x may have changed in Neo4j 5.x/2026.x; avoid carrying legacy configs directly into a new image.

### 7.4. When do you need a custom `neo4j.conf` file?

For customizing many settings, you can **bind mount** a `./conf` directory to `/conf` inside the container, but **this does not automatically append a few lines onto the base config**. Files in `/conf` **replace the configuration provided by the image**; you must ensure the config set is complete and matches the version. Mounting an empty directory may cause the DBMS to start misconfigured or fail to start. `NEO4J_*` environment variables take precedence over values in `/conf`.

According to Neo4j documentation, you can run the image with the `dump-config` command to export the default configuration into the mounted directory before editing. When mounting `/conf`, ensure `server.default_listen_address=0.0.0.0` so connectors listen on container interfaces as required by Docker port publishing.

For this lab, **prefer configuration via environment variables** to reduce risk from invalid config files. Only mount `/conf` when you genuinely need extensive configuration and have verified compatibility.

## 8. Connecting from Java Applications and Spring Data Neo4j

When the Neo4j service runs inside a container, the connection address depends on **where the application is running**:

| Application | Bolt URI | Reason |
| --- | --- | --- |
| Java/Spring Boot running on the **host** | `bolt://localhost:7687` (dev) or `bolt://localhost:7688` (test) | Uses the published **host port** |
| Java/Spring Boot in the **same Compose network** as Neo4j | `bolt://neo4j:7687` | Docker DNS resolves service name `neo4j`, using the **container port** |
| Another machine on the network | Do not use the lab's loopback config | Requires dedicated networking, authentication, and TLS design |

If Spring Boot runs in another container, `localhost` refers to the **Spring Boot** container, not Neo4j. Do not change the host port expecting the app container's `neo4j:7687` URI to change as well.

Example `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Environment variables for the Java app must be supplied via your app launcher or separate config. The Neo4j service's `neo4j_auth` secret **is not automatically shared with the Java container**; if sharing a secret, explicitly design permissions and how the app reads it.

**Distinguishing started vs. ready:** basic `depends_on` only enforces container creation/startup order. The Java app may open a connection before the DBMS is ready to accept queries; use bounded retry/reconnection logic or a proper healthcheck if your deployment flow requires readiness guarantees. Do not treat `docker compose ps` showing "running" as a substitute for a Cypher readiness check.

## 9. Persistence Does Not Replace Backups

A named volume solves **retaining data when a container is replaced**; it does not protect against hardware failure, volume deletion, store corruption, accidental delete queries, or failed upgrades.

- **Persistence:** keeps the database at `/data` outside the container's writable layer.
- **Backup:** creates a consistent copy usable for restoring elsewhere, using tools supported by your version/edition.
- **Restore:** procedure for returning a database to a state from a verified backup.
- **Upgrade/migration:** evaluating compatibility of DBMS, plugins, data, and Cypher before swapping the image.

For small labs, you can use **`neo4j-admin database dump/load`** mechanisms as documented for your edition and database state, or export model data as CSV/Cypher for easy recreation. Never raw-copy files while the database is actively writing and assume the copy is consistent. For critical systems, use online/offline backup procedures officially supported by Neo4j for that edition and **test restores**.

When changing `NEO4J_IMAGE` from `2026.10.2` to a newer version, **do not simply change the tag and run `up -d` on important data**: check release notes, the upgrade/migration guide, and rollback/recovery options. Having an existing volume does not mean the data store is backward-compatible with older versions.

## 10. Troubleshooting Common Issues

| Symptom | Common cause | Check or resolution |
| --- | --- | --- |
| `docker compose config` reports variable/secret error | Invalid YAML syntax, missing `.env` or secret file | Check project-relative paths, interpolation syntax, and `secrets:` entries |
| `Cannot connect to Docker daemon` | Docker Engine/Desktop is not running | Check `docker info`, start Docker |
| Port `7474` or `7687` already in use | Another Neo4j instance or program occupies the host port | Check listening ports, change host port values in `.env` |
| Container `running` but Browser fails | Neo4j still starting up, config error, or wrong host port | Run `docker compose logs --tail=100 neo4j` and check `ps` |
| `Authentication failed` | Wrong secret, hitting a different instance, or volume holds old password | Verify host port/project, initial secret, and use Neo4j's password-change procedure |
| Edited `NEO4J_AUTH_SOURCE` but password didn't change | Secret only initializes auth when the database does not exist yet | Do not delete volumes casually to reset; change password via appropriate admin command |
| Recreated container has empty graph | Different Compose project name/volume or `/data` was not mounted earlier | Check `docker volume ls` and `-p` flag; locate the old volume before modifying |
| `Permission denied` on `/data` | Host bind mount does not allow container UID/GID writes | Check owner/permissions per Neo4j docs; use named volumes for labs |
| JVM killed / OOM | Too little RAM allocated to Docker, heap/page cache too large | Inspect logs and host/engine RAM; adjust memory variables appropriately |
| `Connection refused` from app container | URI uses `localhost:7687` | If on the same Compose network, use `bolt://neo4j:7687` |
| Mounted `./conf:/conf` and Neo4j won't start | `conf` directory empty/missing key settings or invalid setting | Restore a version-matched config set, check logs; use env vars for small tweaks |
| Data exists but queries behave differently after upgrade | Cypher language version or DBMS features changed | Check `dbms.components()`, Cypher config, and release/upgrade notes |

Your diagnostic flow should go: **Compose config → Docker daemon → container/logs → ports → credentials → database → Cypher**. Never delete a volume before identifying the root cause.

## 11. Hands-on Exercises

### Exercise 1 — Proving Data Persistence

1. Run `docker compose up -d` with `neo4j_data:/data`.
2. Create the node/relationship using Cypher from Section 6.1 and capture the `MATCH` result.
3. Run `docker compose down`, then `docker compose up -d`.
4. Re-run `MATCH`, explain why the data still exists, and identify where it is stored.

**Expected outcome:** the `Student` node, `Course` node, and `ENROLLED_IN` relationship remain intact.

### Exercise 2 — Two Independent Environments

Create `.env.dev` and `.env.test` with different host ports; launch `-p neo4j-dev` and `-p neo4j-test` respectively. Create a node with the same `studentId` but different `name` values in each instance. Reconnect to each host port and verify data is not mixed. Then stop **only test** while keeping dev running.

**Expected outcome:** two volumes with distinct project prefixes; running `down` on test does not interrupt dev.

### Exercise 3 — Diagnosing a Java Connection Error

A Spring Boot application runs as another service in the same Compose network, uses `bolt://localhost:7687`, and gets connection refused. Explain what `localhost` points to, change the URI to `bolt://neo4j:7687`, and describe how to handle cases where the DBMS is not ready yet.

### Exercise 4 — Password Unchanged After Initialization

A teammate edits `secrets/neo4j_auth.txt` and runs `docker compose down` followed by `up -d`, yet logging in with the new password fails. Explain the **one-time initialization** role of `NEO4J_AUTH_FILE` and propose changing the password with Neo4j's admin tooling. Do not recommend deleting the volume if the database must be preserved.

### Environment Acceptance Checklist

- [ ] `docker compose config --quiet` succeeds with an explicit image tag.
- [ ] Compose starts cleanly; host Browser `localhost:7474` and host Bolt `localhost:7687` connect properly.
- [ ] `CALL dbms.components()` returns the expected Neo4j version/edition.
- [ ] Created and queried a graph with nodes, relationships, and properties.
- [ ] Data persists after `down` and `up -d` using the same project name.
- [ ] Know where named volumes, logs, and secrets are located.
- [ ] Secret files, passwords, and data volumes are excluded from Git.
- [ ] Can distinguish host URIs from internal Docker service URIs.
- [ ] Understand that `down -v` can cause data loss and volumes are not backups.

## 12. Official References

- [Neo4j Operations Manual — Deploy a standalone server using Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — Compose examples, authentication, and Docker secrets.
- [Neo4j Operations Manual — Persisting data with Docker volumes](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/) — `/data`, `/logs`, `/conf` mount points and file permissions.
- [Neo4j Operations Manual — Docker-specific configuration settings](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/) — rules for converting `neo4j.conf` keys to `NEO4J_*` variables.
- [Neo4j Operations Manual — Modify the default configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/) — `/conf`, `dump-config`, and configuration precedence.
- [Neo4j Operations Manual — Getting started with Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — images, editions, versions, and connectivity.
- [Docker Compose — Environment variables and interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/) — `.env`, `--env-file`, and Compose variables.
- [Docker Compose — Secrets](https://docs.docker.com/compose/how-tos/use-secrets/) — secret access via mounted files.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — review version changes before reusing data volumes.

**Practical takeaway:** A solid Neo4j Docker Compose setup for development needs a **pinned image version**, **`/data` mounted to a named volume**, **environment-specific configuration**, **credentials kept out of source code**, and **Cypher verification after container recreation**. This forms the foundation for learning Cypher, graph design, and Java integration reproducibly.
