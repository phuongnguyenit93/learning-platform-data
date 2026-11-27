# Choosing Local Environment, Docker, and Neo4j Aura Service

## 1. Objectives and Context

Neo4j is a graph database management system based on the **property graph** model. Data is represented using **nodes** (vertices), **relationships** (directed and typed edges), and **properties** (attributes). You query nodes, relationships, and paths using **Cypher**. Before learning modeling, indexes, constraints, query tuning, data import, or connecting via the Java Driver and Spring Data Neo4j, you need to choose an appropriate runtime environment.

After this lesson, you will be able to:

- Distinguish between local Neo4j installation, running via Docker, and using the managed **Neo4j AuraDB** service.
- Choose an environment based on learning goals, offline capability, level of control, and deployment requirements.
- Initialize a Neo4j DBMS, determine the access address, set up an account, and run a Cypher verification query.
- Understand how data is persisted, how passwords are managed, and how to troubleshoot common connection errors.
- Prepare connection parameters to reuse in Java or Spring Boot applications.

> **Scope:** This lesson focuses on choosing and setting up an initial environment. Cluster deployment, production hardening, backup planning, memory tuning, and Enterprise edition features require separate dedicated operations documentation.

## 2. What Needs Do the Three Options Address?

All three ways of running Neo4j allow you to learn Cypher and work with property graphs, but they differ in where the DBMS runs and who is responsible for operations.

| Criterion | Local: Neo4j Desktop / server | Docker on development machine | Neo4j AuraDB |
| --- | --- | --- | --- |
| Where does the DBMS run? | On your personal machine's operating system | In a container on a machine/host you manage | On cloud infrastructure managed by Neo4j |
| Initial setup | Via the Desktop UI or server package installation | Install Docker Engine/Desktop, declare image and volume | Create an account, create an instance in Aura Console |
| Working without Internet | Yes, after downloading and installing all components | Yes, if the image is already downloaded | No; requires connectivity to the service |
| System configuration permissions | Depends on edition, generally quite flexible | Explicit, easy to describe via Compose file | Limited to options provided by the service |
| Reproducibility across team/CI | Depends on manual steps and installed version | High if image, Compose, and configuration are pinned | High at the application level, but depends on service state/tier |
| Data storage | Local DBMS directory | Volume or bind mount | Managed service; backup capabilities depend on tier |
| Resources and cost | Your CPU/RAM/disk and administration time | CPU/RAM/disk, Docker resources | Free for learning needs; paid tiers per current terms |
| Typical scenarios | Personal learning, trying Cypher, debugging | Application development, sharing team config, integration testing | Multi-machine demos, cloud POCs, managed service |

**Quick selection by goal:**

1. **Just starting out and want to see data immediately:** choose Neo4j Desktop if your machine has sufficient resources.
2. **Building a Java/Spring Boot backend and need a reproducible environment:** choose Docker Compose.
3. **Don't want to manage the DBMS yourself and need Internet access:** choose AuraDB Free for learning or choose a paid tier suited to your deployment goal.
4. **Need deep configuration changes, plugins, on-disk data access, or operational testing:** prefer a self-managed environment; check permissions by edition.
5. **Aiming for production:** evaluate SLA, security, backup/restore, monitoring, scalability, and cost; practicing on a single instance does not represent a production architecture.

~~~mermaid
flowchart TD
    A["You need to run Neo4j"] --> B{"Need offline operation<br/>or DBMS control?"}
    B -- "No" --> C["AuraDB: managed service"]
    B -- "Yes" --> D{"Need repeatable environment<br/>via config and CI?"}
    D -- "Yes" --> E["Docker + Compose"]
    D -- "No" --> F["Neo4j Desktop / local server"]
~~~

## 3. Common Connection Concepts to Remember

A minimal Neo4j environment consists of a **running DBMS**, a **database**, **authentication credentials**, and a **connection address**. Do not confuse the DBMS (which manages one or more databases, depending on edition) with each individual database containing nodes/relationships.

| Component | Common value | Purpose |
| --- | --- | --- |
| HTTP / Neo4j Browser | `http://localhost:7474` | Use the UI to run queries on the local machine |
| Bolt | `bolt://localhost:7687` | Direct connection from a Driver to a standalone Neo4j instance, commonly used in local development |
| Routing scheme | `neo4j://...` | Allows the Driver to use routing information returned by the DBMS when applicable |
| AuraDB over Bolt with TLS | `neo4j+s://<instance-id>.databases.neo4j.io` | Encrypted and certificate-verified connection to AuraDB |
| Initial username | `neo4j` | Common default account |
| Database | Usually `neo4j` | Target database selected for Cypher execution; confirm the actual name in the instance |

**Distinguishing UI and protocol:** the address `http://localhost:7474` opens the web interface; the Java Driver connects via an appropriate Bolt/Neo4j URI—do not use the web UI address to initialize a Bolt Driver. Ports `7474` and `7687` are only defaults for local installations and can be reconfigured.

In examples, passwords and instance IDs are **illustrative values only**. Never commit passwords, downloaded Aura credentials, or `.env` files containing secrets into Git.

## 4. Option A — Running Neo4j on a Local Machine

### 4.1. Neo4j Desktop: convenient for beginners

Neo4j Desktop provides a UI to create and manage DBMSs on a personal machine, start/stop servers, manage connections, and open query tools. Desktop 2.x can also connect to remote DBMSs. The Developer Edition license included with Desktop is intended for **development**, and does not by default permit use as a production Enterprise edition.

Steps:

1. Download and install **Neo4j Desktop** from the official website; choose the build compatible with your operating system and CPU architecture.
2. In Desktop, create a local DBMS; choose a DBMS version compatible with your course/project.
3. Set a sufficiently strong password for the `neo4j` user and store it in a personal secret manager.
4. Start the DBMS; wait for the status indicating the server is ready.
5. Open the Query/Browser tool from Desktop, log in with the DBMS account, and run:

~~~cypher
RETURN 'Neo4j local ready' AS message, 1 + 1 AS result;
~~~

The expected result has one row with `message = "Neo4j local ready"` and `result = 2`. Depending on the Desktop version, button names or screens may vary; look for the DBMS management section and the Query tool.

**Advantages:** fewer commands to memorize, easy to inspect logs and configuration, useful when learning Cypher syntax and visualizing graphs. **Limitations:** manual DBMS creation does not guarantee every team member uses the same version/configuration; the DBMS consumes machine resources and requires manual data management.

### 4.2. Installing Neo4j server directly: when OS control is needed

Beyond Desktop, you can install the Neo4j Server package compatible with your operating system. General sequence:

1. Choose the edition/version and check Java/runtime requirements in the documentation for **that exact version**.
2. Install the server, configure settings in `neo4j.conf`, and set the initial password according to the release instructions.
3. Start via the service manager or the `neo4j console` command from the distribution's `bin` directory (exact syntax/path depends on installation method).
4. Check logs and access Browser/Driver through the configured endpoints.

This option is suitable when you need to learn OS administration, file permissions, services, storage configuration, and logging. In return, upgrades, backups, security updates, and process management are the operator's responsibility.

## 5. Option B — Running Neo4j with Docker Compose

Docker packages Neo4j into an image. Compose describes how to run the container, ports, environment variables, and volumes in a single file that can be shared among project members.

### 5.1. Prerequisites

- Docker Engine or Docker Desktop is running.
- Docker Compose v2 is available (`docker compose` command).
- The machine has sufficient RAM, CPU, and disk space for the DBMS and Docker.
- No other service on the host occupies the ports to be published.

Check:

~~~bash
docker --version
docker compose version
~~~

If it reports that it cannot connect to the Docker daemon, start Docker Desktop/Engine before continuing.

### 5.2. Creating a configuration for the development environment

In a dedicated practice directory, create `compose.yaml`:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
    volumes:
      - neo4j_data:/data
    restart: unless-stopped

volumes:
  neo4j_data:
~~~

Create an `.env` file **in the same directory**:

~~~dotenv
NEO4J_PASSWORD=CHANGE_ME_to_a_unique_strong_password
~~~

Replace the sample string with your own password, avoiding spaces or characters that complicate variable interpolation if you are not yet familiar with how Compose parses `.env`. Add `.env` to `.gitignore` and use an approved secret management method for real deployments. The `.env` file in the example avoids putting the password directly in `compose.yaml`, but it is **not a secure secret store**: anyone who can read the file or inspect container configuration can access the credentials. Production requires a proper secret mechanism.

**Compose explanation:**

- `image: neo4j:2026.10.2` pins a specific version as an example at the time of writing, helping avoid unexpected changes on re-pull. For other projects, choose a supported version and upgrade proactively; avoid blindly relying on the `latest` tag.
- The two `ports` lines map HTTP `7474` and Bolt `7687` from the container to **loopback 127.0.0.1** on the host, which is sufficient for local practice.
- `NEO4J_AUTH` supplies the **initial password** for the `neo4j` account when the database has no credentials yet.
- The named volume `neo4j_data` persists data beyond the container lifecycle; replacing the container does not mean losing the database.
- `restart: unless-stopped` lets Docker restart the container automatically unless explicitly stopped.

### 5.3. Starting, checking, and stopping

Open a terminal in the directory containing `compose.yaml`:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Wait until the logs show that Neo4j is ready, then open **http://localhost:7474**, log in as user `neo4j` with the password from `.env`, and try:

~~~cypher
RETURN 'Docker ready' AS environment;
~~~

Common operational commands:

~~~bash
# Stop the container while keeping the container and volume
docker compose stop

# Restart a stopped container
docker compose start

# Remove the container and Compose network, keeping the named volume
docker compose down

# Recreate the container when needed (data remains in the named volume)
docker compose up -d
~~~

**Be careful:** the `docker compose down -v` command **also deletes named volumes** managed by Compose. In this example, graph data stored in the volume would be deleted; only use it when you intentionally want to reset the environment and already have necessary backups.

**Common pitfall:** if the `neo4j_data` volume already contains an initialized database, changing `NEO4J_PASSWORD` in `.env` and restarting the container **does not reset the existing password**. You need to change the password through Neo4j's administrative mechanism appropriate for the DBMS state, or use a new volume when you truly want to initialize a clean practice environment.

### 5.4. Connecting a backend running on the host or in another container

| Where does the application call Neo4j from? | Common URI | Explanation |
| --- | --- | --- |
| Java/Spring Boot running on laptop | `bolt://localhost:7687` | Goes through the port published to the host |
| Java/Spring Boot in the **same Compose network** | `bolt://neo4j:7687` | `neo4j` is the internal DNS name of the service |
| Another machine on the network or Internet | Do not use the loopback config in the example | Requires designing public/private networking, TLS, and separate access control |

Inside an application container, `localhost` typically points to **the application container itself**, not to the Neo4j container. This is a common cause of `Connection refused` errors in Docker environments.

### 5.5. Extending when learning data import and operations

The example only mounts `/data` to persist the database. When learning `LOAD CSV` from local files, you may need to grant access to the appropriate import directory or bind-mount the path containing CSV files. When learning logs, configuration, or plugins, design additional volumes and check the documentation for your Neo4j version. Do not expose database ports to the Internet just for convenient CSV import; if data needs to be shared, choose appropriate data transfer and authentication mechanisms.

## 6. Option C — Neo4j AuraDB in the Cloud

**Neo4j AuraDB** is a graph database service managed by Neo4j. You focus on the data model, Cypher, and application integration; many infrastructure tasks such as instance provisioning and system updates are handled by the service.

### 6.1. When to use AuraDB Free or a paid tier?

**AuraDB Free** is suitable for learning, demos, model prototyping, and small applications without provisioning CPU/RAM on your laptop. The Free service has resource limits, feature restrictions, and auto-pause policies when inactive. According to current product documentation, Free does not include automated backups like paid tiers and may auto-pause after a period of inactivity; verify the latest policies before designing workflows. Free should not be treated as a production service with an SLA.

Paid tiers are appropriate when higher capacity, availability, monitoring, recovery, and commercial requirements are needed. Confirm specific limits and features in Aura pricing and documentation at selection time.

### 6.2. Creating an AuraDB instance

1. Visit **[Aura Console](https://console.neo4j.io/)** and log in or create an account.
2. Choose to create an **AuraDB** instance and select an appropriate tier (you can start with Free if quota is available).
3. Name the instance, choose available options for the tier, and create the database.
4. **Save/download the credentials immediately when provided**; the initially generated password cannot be viewed in plain text again once lost.
5. Copy the **Connection URI**, **username**, and **database name** (if applicable), and store the password in a secret vault. Example URI:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

`example123` is a placeholder, not a real instance. When an organization uses a custom endpoint/private networking, take the **exact URI** provided by Aura Console; do not guess the hostname.

### 6.3. Testing from the UI and from an application

- In Aura Console, open **Query** or the provided query tool, select the right instance, and connect using your credentials.
- Run `RETURN 'Aura ready' AS environment;` to confirm the database returns a result.
- When integrating the Java Driver or Spring Data Neo4j, use the `neo4j+s://...` URI provided by Aura along with the username/password. The `+s` suffix enforces TLS with certificate verification; **do not switch to `bolt://` or disable certificate verification to work around connection errors**.
- When an instance has multiple databases, select the exact database name. If omitted, the driver may use the default database for the account/instance.

Query path diagram:

~~~mermaid
flowchart LR
    A["Java / Spring Boot Application"] -->|"Bolt / TLS over Internet"| B["AuraDB instance"]
    C["Aura Query"] --> B
    B --> D["Node + Relationship + Property"]
~~~

**Special note for AuraDB Free:** if the URI cannot resolve the hostname or connections suddenly fail after a period of inactivity, check for **Paused** status in Aura Console and resume if needed before troubleshooting firewall/DNS.

## 7. Verifying with the Same Property Graph Test

To compare the three environments fairly, perform the same operations in a **test database**. First verify connectivity:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Next, create a student, a course, and an enrollment relationship using Cypher:

~~~cypher
MERGE (student:Student {studentId: 'ST-001'})
  ON CREATE SET student.name = 'An'
MERGE (course:Course {courseId: 'NEO4J-101'})
  ON CREATE SET course.title = 'Introduction to Neo4j'
MERGE (student)-[:ENROLLED_IN]->(course)
RETURN student.name AS studentName, course.title AS courseTitle;
~~~

Read back the path:

~~~cypher
MATCH p = (:Student {studentId: 'ST-001'})
          -[:ENROLLED_IN]->
          (:Course {courseId: 'NEO4J-101'})
RETURN p;
~~~

**Explanation of results:**

- `Student` and `Course` are node labels; `studentId`, `courseId`, `name`, and `title` are properties.
- `ENROLLED_IN` is the relationship type from student to course.
- `MERGE` matches or creates the corresponding pattern, making re-runs of the example less likely to create duplicates compared to `CREATE` in this test dataset. For real data and concurrent access, you still need to design appropriate **uniqueness constraints**.
- `MATCH p = ... RETURN p` retrieves a path so Neo4j Browser/Query can render it as a graph.

To verify **data persistence**, stop and restart the DBMS/container, or close the session and reconnect to Aura; then re-run the `MATCH` query. If it returns the same path, you have confirmed that the data resides in the database rather than only in the browser session. In Docker, this test is especially useful for verifying volume configuration.

## 8. Preparing Connections for Java Driver and Spring Data Neo4j

A Java application does not need to know whether you use Desktop, Docker, or AuraDB; it needs the right **URI, username, password, and database name**. You can externalize these into environment variables to switch configurations without modifying source code.

| Scenario | `NEO4J_URI` | Notes |
| --- | --- | --- |
| Local Neo4j on host | `bolt://localhost:7687` | Local account and DBMS |
| Spring Boot container in the same Compose network | `bolt://neo4j:7687` | Ensure both services share the Docker network |
| AuraDB | `neo4j+s://<id>.databases.neo4j.io` | Use the exact URI and credentials from Aura Console |

Example `application.properties` for Spring Boot using Spring Data Neo4j:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Set the `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD` environment variables on the host running the application or via a secret manager. For example, an application running on the host against the Docker setup in Section 5 uses `NEO4J_URI=bolt://localhost:7687` and `NEO4J_USERNAME=neo4j`; an AuraDB URI follows the TLS pattern above. If the application targets a specific database, also check the database name selection mechanism for your Driver/Spring Data Neo4j version.

**Do not log passwords**, do not hardcode credentials in source code, and do not include real credentials in commits. Cloud connections over the Internet require reviewing network policies, TLS, and account privileges.

## 9. Common Errors and Verification Steps

| Symptom | Common cause | Verification step |
| --- | --- | --- |
| Browser cannot open `localhost:7474` | DBMS/container not running, port in use, different configured port | Check Desktop status or `docker compose ps` and `docker compose logs neo4j` |
| Java Driver reports `Connection refused` | Wrong host/port or DBMS not ready | Verify URI, Neo4j process, and actual reachable address from where the app runs |
| Connection to `localhost:7687` fails inside container | `localhost` refers to the app container itself | If on the same Compose network, switch to the service name `neo4j:7687` |
| `Authentication failed` | Wrong password, wrong instance, or volume holds old credentials | Match username/password to the right instance; remember `NEO4J_AUTH` only initializes once |
| Container keeps restarting / out of memory | Insufficient Docker resources, memory config too high | Check logs, resource limits, and RAM/disk requirements of the Neo4j version |
| AuraDB cannot resolve hostname | Wrong URI, paused instance, blocked DNS/network | Check Aura Console status first; verify hostname and network policy |
| AuraDB TLS / certificate error | Wrong scheme, endpoint, or network policy | Use the exact `neo4j+s://` URI provided by Aura and verify the certificate chain |
| Data lost after stopping container | `/data` volume not attached or volume deleted accidentally | Check volume configuration; avoid `docker compose down -v` when preserving data |
| Restarted Compose but new password has no effect | Volume already has initial account | Use Neo4j's password change mechanism; do not expect `NEO4J_AUTH` to overwrite it |

With AuraDB, you do not have direct access to the disk or DBMS process as in a self-hosted setup. Conversely, with local/Docker setups you are responsible for updates, access control, storage, and recovery. The two models require different operational procedures.

## 10. Environment Selection Exercises

**Scenario 1 — Learning Cypher on a personal laptop:** A learner wants to build a friends graph, create nodes/relationships manually, and sometimes works offline. **Suitable choice:** Neo4j Desktop; Docker is also reasonable if already comfortable with the terminal and wanting reproducible environments.

**Scenario 2 — Java/Spring Boot team:** Four members need the same DBMS version when running integration tests, with each person having separate test data. **Suitable choice:** Docker Compose with a pinned image and separate volumes per environment; sync configuration in source control while keeping credentials out of Git.

**Scenario 3 — Demoing an app from multiple locations:** The team wants to run a POC without keeping a laptop on 24/7 or configuring a public network server themselves. **Suitable choice:** AuraDB for demo purposes; select a tier based on limits, pause behavior, and required availability.

**Scenario 4 — Critical production service:** A company requires role-based access control, backup schedules, monitoring, disaster recovery, and SLA targets. **Choice:** evaluate an AuraDB tier that supports these requirements or a corresponding self-managed Neo4j architecture; do not conclude readiness merely from `RETURN 1` succeeding.

### Lesson Completion Checklist

- [ ] Can explain the differences between local DBMS, container, and managed service.
- [ ] Selected an environment and listed at least three reasons matching your needs.
- [ ] Know the URI for Browser UI and the URI for Driver connections.
- [ ] Started the DBMS, logged in successfully, and ran `RETURN 1 AS ok`.
- [ ] Created and read back the `Student-[:ENROLLED_IN]->Course` pattern.
- [ ] Verified data persists after reconnecting / restarting.
- [ ] Know where credentials and data are stored and how not to accidentally delete volumes.

## 11. Official References

- [Neo4j Desktop](https://neo4j.com/docs/desktop/current/) — creating and managing local DBMSs.
- [Neo4j Operations Manual: Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — container initialization, authentication, and data persistence.
- [Neo4j Operations Manual: Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — Compose configuration and credential management.
- [Neo4j Aura: Create an instance](https://neo4j.com/docs/aura/getting-started/create-instance/) — creating a cloud instance.
- [Neo4j Aura: Connect to an instance](https://neo4j.com/docs/aura/getting-started/connect-instance/) — obtaining the URI and connecting applications.
- [Neo4j Aura: Pricing](https://neo4j.com/pricing/) — comparing Free and paid tier capabilities at deployment time.

> **Version note:** The Docker tag in the example is a version used in Neo4j documentation at the time of writing; when practicing later, check the support lifecycle and upgrade instructions on the official site.
