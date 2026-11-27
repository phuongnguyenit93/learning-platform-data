# Configuring Security, Monitoring, and Resource Limits

A Neo4j capstone is not finished just because the app can create nodes, connect relationships, and run Cypher. Once deployed to multi-user environments, the system must also **protect data**, **detect anomalies early**, and **bound CPU, memory, connection, and transaction time consumption**. If these three pillars are not designed together, an overly wide traversal can stall other transactions; an over-privileged app account can expose sensitive data; or an outage is noticed only when users report the API has stopped responding.

The lesson **“Configuring Security, Monitoring, and Resource Limits”** belongs to the **Capstone Project** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. You will apply property graph modeling, Cypher, indexes/constraints, query tuning, Java Driver, Spring Data Neo4j, and Neo4j operations into **a verifiable deployment package** rather than studying settings in isolation.

**Final capstone deliverable:** a Neo4j environment for a project-membership management app, complete with access policies, resource budgets, monitoring signals, integration test suite, incident drills, and an evidence-backed acceptance report.

> **Version scope:** baseline examples use Neo4j **5.26** in Docker and Java Driver 5/6 with `executeRead`/`executeWrite`. They illustrate a **single self-managed lab instance**, not an HA cluster. Fine-grained graph RBAC, server-side Prometheus metrics, certain query logging modes, and enterprise backup tooling depend on **Neo4j Enterprise Edition** or managed service tiers. Neo4j AuraDB has its own management plane and configurable surface. Never assume an Enterprise feature works on Community.

## 1. Objectives, Deliverables, and Completion Criteria

After this lesson, you will be able to:

1. Stand up a Neo4j test instance with **authentication**, ports bound only where intended, and secrets kept out of source code.
2. Distinguish **authentication**, **Neo4j authorization**, **application-layer business permissions**, and **transport encryption**.
3. Design a least-privilege reader role, verifying allowed vs. denied operations on supported editions.
4. Configure reasoned limits for **CPU/container memory**, **JVM heap**, **page cache**, **transaction timeouts**, **driver connection pools**, and **retry budgets**.
5. Collect **latency, throughput, query/transaction errors, lock waits, and resource health** across application and database layers.
6. Verify behavior with fixture data, negative tests, a small load test, and an incident drill inside an isolated environment.
7. Produce **runbooks**, a risk table, dashboards/SLOs, and an evidence-backed acceptance report.

### Required Deliverables

| ID | Artifact | Minimum evidence |
|---|---|---|
| D1 | Architecture and connection-flow diagram | App → Driver → Neo4j, network boundaries, and identities |
| D2 | Test database configuration | Verified config with zero exposed passwords |
| D3 | Security policy | Identity–permission matrix, allowed/denied tests |
| D4 | Resource budget | CPU, heap, page cache, pool, timeout values, and rationale |
| D5 | Monitoring setup | Dashboards/logs/metrics populated with real data |
| D6 | Test suite | Cypher correctness, security, limits, and recovery tests |
| D7 | Runbooks and report | Slow/error remediation, measurements, residual risks, conclusion |

**Acceptance criteria are not** “the config file exists,” but “the configuration actually takes effect, tests produce expected results, and evidence is attached.” If a feature is unavailable in your edition, mark it **NOT APPLICABLE / NOT AVAILABLE** and propose compensating controls—**never record a fake PASS**.

## 2. Capstone Business Context

Suppose an internal service manages users and projects:

~~~text
(:CapUser {uid: 'U01', name: 'An', email: 'an@example.test'})
   -[:MEMBER_OF]->
(:CapProject {code: 'P01', name: 'Graph Platform'})

(:CapSecret {key: 'S01', note: 'private-demo'})
~~~

The application has three workflows:

- **Read:** look up a user's projects by `uid`.
- **Write:** create or update project memberships upon authorized requests.
- **Admin:** manage constraints/indexes, provision accounts and roles, monitor/recover the system.

These three workflows **should never share the same privileges**. The project-listing service needs `CapUser.uid`, `CapUser.name`, `CapProject.code`, and `CapProject.name`, yet never needs `CapUser.email` or `CapSecret.note`.

### Trust Boundary Diagram

~~~mermaid
flowchart LR
    USER["Users / API"] --> APP["Spring Boot / Java service"]
    SEC["Secret manager<br/>or secure env vars"] -.-> APP
    APP -->|"Bolt + TLS in production"| DRIVER["Neo4j Java Driver"]
    DRIVER --> DB["Neo4j database"]
    DB --> OBS["Internal metrics / logs"]
    MON["Monitoring service"] --> OBS
    ADM["Dedicated admin account"] --> DB
~~~

**Boundaries to state explicitly:** who may reach the Bolt port, who can read logs/metrics, where the app fetches credentials, which account runs migrations, and who holds backup-restore privileges.

## 3. Scoping by Edition

To keep the capstone portable across environments, split implementation into **two tiers**:

| Capability | Self-managed Neo4j Community baseline | Neo4j Enterprise / compatible managed extension |
|---|---|---|
| Password authentication | Yes | Yes or tier-supported auth mechanism |
| Keep Bolt off public Internet | Yes, network config | Yes, plus private networking where applicable |
| Parameterized Cypher, validation, constraints | Yes | Yes |
| Self-managed heap/page cache/CPU caps | Yes | Managed: governed by tier and exposed settings |
| Driver pool, retry, and tx timeout limits | Yes within supported API/config | Yes |
| Application metrics/logs/traces | Yes | Yes |
| Fine-grained label/property graph RBAC | **Not complete** like Enterprise | Enterprise and supported tiers |
| Detailed server-side Prometheus metrics | Do not assume available | Enterprise self-managed and export-capable tiers |
| Deep query/audit logging | Edition/version dependent | Per edition/tier/privileges |
| Custom plugins, host access, config files | Available self-managed within edition limits | Enterprise self-managed flexible; managed typically restricted |

**Rule:** proving “a reader cannot view email even when running Cypher directly” requires a database with **true fine-grained RBAC**. On Community, hiding email in an API DTO is a **different control**, not proof that Neo4j denied property reads.

## 4. Preparing the Practice Environment

### 4.1. Prerequisites

- Modern Docker Engine and Docker Compose.
- Sufficient host RAM/disk to run the container with the limits below; never force a 4 GiB config onto an under-provisioned host.
- A dedicated project directory **isolated from production data**.
- A test Neo4j password supplied via environment variable; **never commit to Git**.
- JDK 17+ and a Java/Spring Boot project if implementing the integration layer.

Examples assume the database is named `neo4j`. On AuraDB or multi-database servers, verify the actual database name rather than relying blindly on defaults.

### 4.2. Docker Compose for the Lab

A minimal self-managed setup:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    restart: unless-stopped
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set_NEO4J_PASSWORD}"
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "1G"
      NEO4J_server_memory_pagecache_size: "1G"
      NEO4J_db_transaction_timeout: "30s"
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    mem_limit: 4g
    cpus: "2.0"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
~~~

**Key points to recognize:**

- `NEO4J_AUTH` enables authentication for the default `neo4j` user. Password comes from the host environment when Compose runs.
- Rule for mapping Neo4j setting names to Docker env vars: `.` → `_`; literal `_` in setting names → `__`. For example, `server.memory.heap.max_size` becomes `NEO4J_server_memory_heap_max__size`.
- `127.0.0.1:7687:7687` binds Bolt strictly to loopback. This is **single-host lab isolation**, not a substitute for TLS across untrusted networks.
- `mem_limit: 4g` and `cpus: "2.0"` are **practice caps**; Neo4j memory spans heap, page cache, plus native/off-heap memory.
- `/data` and `/logs` use persistent volumes. **Volumes are not backups** and do not replace restore drills.
- `db.transaction.timeout` sets a default transaction ceiling. Large batch jobs need dedicated timeout plans—never raise it indefinitely just to let bad jobs finish.

**Credential warning:** container environment variables are visible to Docker admins and diagnostic tools. This fits an isolated lab; production should use proper secret managers or platform credential injection rather than treating Compose env vars as tamper-proof secret storage. Avoid printing interpolated `docker compose config` output into public logs.

### 4.3. Starting and Verifying Beyond “Container Up”

Illustrative commands to **run in your isolated lab environment**:

~~~bash
# Export NEO4J_PASSWORD securely in your shell environment.
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Once ready, open Neo4j Browser at `http://127.0.0.1:7474`, sign in with the test credentials, and run:

~~~cypher
RETURN 1 AS ready;
~~~

~~~cypher
SHOW DATABASE neo4j
YIELD name, currentStatus
RETURN name, currentStatus;
~~~

`RETURN 1` proves the server accepts a trivial query; it **does not prove** the user holds required privileges, data is intact, backups exist, or business queries run fast enough.

## 5. Creating Verifiable Constraints and Fixture Data

To run security, monitoring, and resource tests against identical inputs, create the fixture **strictly on the practice database**.

### 5.1. Creating Constraints

~~~cypher
CREATE CONSTRAINT cap_user_uid_unique IF NOT EXISTS
FOR (u:CapUser)
REQUIRE u.uid IS UNIQUE;

CREATE CONSTRAINT cap_project_code_unique IF NOT EXISTS
FOR (p:CapProject)
REQUIRE p.code IS UNIQUE;
~~~

Constraints accelerate key lookups and block duplicate business keys. **Uniqueness does not enforce property presence**; existence or node-key constraints require a compatible edition if mandated by policy.

### 5.2. Seeding Sample Data

~~~cypher
MERGE (u1:CapUser {uid: 'U01'})
SET u1.name = 'An',
    u1.email = 'an@example.test',
    u1.isActive = true
MERGE (u2:CapUser {uid: 'U02'})
SET u2.name = 'Bình',
    u2.email = 'binh@example.test',
    u2.isActive = true
MERGE (p1:CapProject {code: 'P01'})
SET p1.name = 'Graph Platform'
MERGE (p2:CapProject {code: 'P02'})
SET p2.name = 'Monitoring'
MERGE (u1)-[:MEMBER_OF]->(p1)
MERGE (u1)-[:MEMBER_OF]->(p2)
MERGE (u2)-[:MEMBER_OF]->(p2)
MERGE (s:CapSecret {key: 'S01'})
SET s.note = 'private-demo';
~~~

Independent checks:

~~~cypher
MATCH (u:CapUser)
RETURN count(u) AS users;
// Sample data: 2
~~~

~~~cypher
MATCH (:CapUser)-[r:MEMBER_OF]->(:CapProject)
RETURN count(r) AS membershipEdges;
// Sample data: 3
~~~

~~~cypher
MATCH (u:CapUser {uid: 'U01'})-[:MEMBER_OF]->(p:CapProject)
RETURN p.code AS projectCode, p.name AS projectName
ORDER BY projectCode;
// P01 / Graph Platform; P02 / Monitoring
~~~

**Assumption:** this assumes a clean database or no pre-existing `CapUser`/`CapProject`/`CapSecret` data. If another test suite shares those labels and IDs, isolate the database or fixture before trusting `count`.

## 6. Designing a Least-Privilege Access Model

### 6.1. Separating Identities by Role

| Identity | Purpose | Needed privileges | Must not hold |
|---|---|---|---|
| `cap_reader` | Display user's projects | ACCESS, traverse `MEMBER_OF`, read needed IDs/names | Read `email`/`CapSecret`, write, admin |
| `cap_writer` | Manage memberships | Read keys and write scoped targets only | User admin, schema DDL, backup |
| `cap_migrator` | Deploy indexes/constraints | Authorized schema/migration privileges | Used as runtime API identity |
| `cap_observer` | Monitor operations | System monitoring/log/metric read access | Mutate business data |
| `cap_admin` | Approved provision/restore | Scoped administrative privileges | Used as default service credential |

**Separate HTTP users from Neo4j users:** even if the API connects as `cap_reader`, the app still must authorize which projects the HTTP caller may view. Neo4j RBAC cannot know the end-user HTTP identity when all requests share one DB account.

### 6.2. Authentication in the Community Baseline

In the Docker Compose lab, `NEO4J_AUTH` enforces login authentication. Baseline tests:

1. Log in with the right password and run `RETURN 1` successfully.
2. Log in with the wrong password; verify connection rejection.
3. Verify Bolt/Browser ports listen only on loopback as configured.
4. Verify API logs never contain passwords, tokens, or credentialed URIs.
5. Verify queries always use parameters rather than concatenating user input into Cypher.

**This verifies authentication and network exposure only**, not fine-grained label/property authorization. Never run a production app under a shared admin account merely because a Community lab lacks Enterprise RBAC.

## 7. Enterprise Extension: Label- and Property-Scoped Read Access

This section runs **only on a test Neo4j Enterprise instance** supporting RBAC, or a managed tier offering the same capability. User/role creation and grants are executed by an admin on the **system database**.

### 7.1. Provisioning Role and User

~~~cypher
// SYSTEM database — admin; supply $readerPassword from a secure store.
CREATE ROLE cap_reader_role IF NOT EXISTS;
~~~

~~~cypher
CREATE USER cap_reader IF NOT EXISTS
SET PASSWORD $readerPassword
CHANGE NOT REQUIRED;
~~~

~~~cypher
GRANT ROLE cap_reader_role TO cap_reader;
~~~

Never hardcode real passwords as literals in docs, query histories, or tickets. Some tools log query parameters if configured; enforce log hygiene when provisioning credentials.

### 7.2. Granting Required Privileges

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO cap_reader_role;

GRANT MATCH {uid, name}
ON GRAPH neo4j NODES CapUser
TO cap_reader_role;

GRANT MATCH {code, name}
ON GRAPH neo4j NODES CapProject
TO cap_reader_role;

GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS MEMBER_OF
TO cap_reader_role;
~~~

Never grant `MATCH {*} ON GRAPH *`, `WRITE`, or admin privileges just to let an API read one screen. When more properties are genuinely required, update the permission matrix and tests before expanding grants.

**Important:** a user can hold multiple roles, including privileges inherited via `PUBLIC`; another `GRANT` can widen effective access unexpectedly. Never treat the minimal grant script alone as final proof.

### 7.3. Inspecting Effective Privileges

~~~cypher
// SYSTEM database — account with privilege-inspection rights.
SHOW USER cap_reader PRIVILEGES AS COMMANDS;
~~~

~~~cypher
SHOW USERS
YIELD user, roles, suspended
WHERE user = 'cap_reader'
RETURN user, roles, suspended;
~~~

Verify exact database names, labels, properties, relationship types, and all roles assigned to `cap_reader`. If another role exposes `email` or `CapSecret`, mark the security test **FAIL**—never weaken assertions.

## 8. Controlled Security Test Suite

**Always seed fixtures with an authorized account and COMMIT before running reader tests.** If a reader queries before the seed transaction commits, empty results reflect isolation rather than RBAC.

### 8.1. Positive Control: Reader Reads Public Data

Connect as `cap_reader` to database `neo4j`:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})-[:MEMBER_OF]->(p:CapProject)
RETURN u.uid AS uid, u.name AS userName,
       p.code AS projectCode, p.name AS projectName
ORDER BY projectCode;
~~~

**Expected:** exactly 2 rows, `P01` and `P02`. Positive tests catch **overly restrictive grants** that would break the API.

### 8.2. Negative Read: Sensitive Properties Hidden

Reader:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})
RETURN u.uid AS uid, u.email AS email;
~~~

With only the grants from section 7, the reader sees `uid` while `email` is hidden (typically `null` under fine-grained READ semantics). With admin:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})
RETURN u.email AS email;
// Admin sees an@example.test.
~~~

A valid PASS requires **both proofs**: the real property exists when read by an authorized identity, yet stays hidden from the reader.

### 8.3. Negative Traversal: Out-of-Scope Nodes

Reader:

~~~cypher
MATCH (s:CapSecret)
RETURN count(s) AS visibleSecrets;
// Typically 0 when reader lacks TRAVERSE on this label.
~~~

Admin:

~~~cypher
MATCH (s:CapSecret)
RETURN count(s) AS totalSecrets;
// Sample data: 1.
~~~

Missing `TRAVERSE` privileges can make nodes **disappear from results** rather than throwing an exception. Tests must distinguish hidden data from truly absent data.

### 8.4. Negative Write: Cannot Modify Resources

Reader attempts to rename a project:

~~~cypher
MATCH (p:CapProject {code: 'P01'})
SET p.name = 'Tampered'
RETURN p.name;
~~~

**Expected:** write rejected; assert the version-appropriate authorization error code, then verify as admin:

~~~cypher
MATCH (p:CapProject {code: 'P01'})
RETURN p.name AS name;
// Must still be Graph Platform.
~~~

`assertThrows(...)` alone without re-reading the database **is insufficient** for negative write tests. For multi-step transactions, also verify clean rollback boundaries.

### 8.5. Security Test Matrix

| Test | Community baseline | Enterprise fine-grained |
|---|---|---|
| Valid / invalid password | Execute | Execute |
| Ports bound strictly to loopback/private network | Execute | Execute |
| Cypher parameterization, zero secrets in logs | Execute | Execute |
| Reader reads `uid`/`name` | Verify API behavior | Verify RBAC and raw Cypher |
| Reader cannot read `email` via direct Cypher | Never equate API masking to DB RBAC | **Mandatory test** when policy requires |
| Reader cannot traverse `CapSecret` | Lacks fine-grained proof | **Mandatory test** |
| Reader cannot `SET`/`DELETE` | Per edition's actual permissions | **Mandatory test** |
| App user holds no admin/schema rights | Verify within edition capabilities | Verify effective privileges |

## 9. Security in Cypher, Java Driver, and Connections

### 9.1. Never Concatenate Input into Cypher Strings

**Wrong:**

~~~java
String cypher =
    "MATCH (u:CapUser {uid: '" + inputUserId + "'}) RETURN u";
~~~

**Right:**

~~~java
var result = tx.run("""
    MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->(p:CapProject)
    RETURN p.code AS code, p.name AS name
    ORDER BY code
    """, Map.of("uid", inputUserId));
~~~

Parameterization keeps input values separate from Cypher syntax. When a user selects labels or relationship types dynamically, never interpolate raw text—use a strict **allowlist** for structural elements that cannot be parameterized directly.

### 9.2. TLS and Network Boundaries

- **Lab loopback:** Compose binds ports strictly to `127.0.0.1` for single-machine testing; **never** send credentials over public networks without TLS.
- **Self-managed production:** enforce valid TLS on Bolt, verifying certificates, DNS, firewalls, and advertised hostnames. Use `neo4j+s://` or `bolt+s://` per topology.
- **Cluster:** with routing URIs, every address returned in the routing table must be reachable by the app over the designed network and TLS configuration.
- **Managed AuraDB:** use the URI and security settings provided by the instance; do not try editing `neo4j.conf` on managed infrastructure without server access.
- **Secrets:** load from a secret manager or deployment vault; never log `AuthTokens.basic(...)`, passwords, or credentialed URIs.

Never disable TLS certificate validation just to turn a connection test “green.” Separate network reachability, authentication, authorization, and functional correctness into independent tests.

## 10. Neo4j Resources: Splitting the Memory Budget Properly

Neo4j is a graph engine constantly traversing nodes, relationships, and indexes. Capping memory with `-Xmx` alone falls short because **not all Neo4j memory lives inside the JVM heap**.

### 10.1. Memory Regions

| Region | Purpose | Signs of undersizing or misconfiguration |
|---|---|---|
| **JVM heap** | Java objects, query execution state, metadata, transactions | Long GC pauses, heap errors, rising latency |
| **Page cache** | Caches graph/index storage pages | Rising page faults, heavy disk I/O, slow queries |
| **Native/off-heap & OS** | Bolt/network buffers, native allocations, thread stacks, runtime overhead | Container OOM-killed even while heap looks free |
| **Disk** | Store files, transaction logs, query/debug logs, backups | Out of disk, failed transactions, difficult recovery |

In the Compose sample:

~~~text
Container memory limit = 4 GiB
  Heap initial         = 512 MiB
  Heap maximum         = 1 GiB
  Page cache           = 1 GiB
  Remainder            = reserved for native/off-heap/OS/overhead

CPU quota              = 2 vCPU (illustrative value)
~~~

This is a **budget table**, not an exact RSS prediction. Beyond heap and page cache lie native/OS allocations; never set `heap + page_cache` equal to 100% of `mem_limit`. Host capacity and real workloads determine proper sizing.

### 10.2. Rules for Sizing Heap and Page Cache

- Never inflate heap blindly when queries are slow due to missing indexes or unbounded fan-out.
- Never size page cache so large that the container starves native/OS memory.
- Monitor **heap usage, GC pauses, page cache hits/faults, RSS, and container OOM events** where supported.
- Freshly started instances start with cold caches; compare configurations under matching cache warmth.
- Validate self-managed configs **against your Neo4j version** and benchmark on a representative dataset.
- In managed tiers, heap/page cache may be fixed by tier; tune via queries, indexes, and supported resource tiers.

### 10.3. Avoiding Misconceptions About Container Limits

Setting `cpus: "2.0"` does not cap each query to “at most 2 threads,” and `mem_limit: 4g` does not mean Neo4j stays safely at 4 GiB. These are **OS/runtime quotas**. Exceeding actual container memory triggers process kills by the OS or container runtime, so track OOM events and RSS—not just JVM heap.

## 11. Transaction, Query, and Connection Limits

### 11.1. Three Timeouts Not to Confuse

| Timeout | Meaning | When exceeded |
|---|---|---|
| **Connection acquisition timeout** | Driver waits to borrow a connection from the pool | Fails even before any query runs |
| **Transaction timeout** | Server/driver time limit for one transaction per config | Transaction is terminated and rolled back |
| **Max transaction retry time** | Driver budget for retrying managed transactions on transient errors | Driver stops retrying and surfaces the error |

Beyond these sit **HTTP/API timeouts**, socket connect timeouts, network timeouts, and idle-connection pruning. Setting one driver timeout **does not** mean every end-to-end HTTP call finishes within that exact bound.

### 11.2. Java Driver: Bounded Configuration

Java 17+ example:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

public final class CapProjectGateway implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public CapProjectGateway(
            String uri, String username, String password,
            String database) {

        Config config = Config.builder()
                .withMaxConnectionPoolSize(40)
                .withConnectionAcquisitionTimeout(5, TimeUnit.SECONDS)
                .withMaxTransactionRetryTime(15, TimeUnit.SECONDS)
                .build();

        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public List<String> projectsOf(String uid) {
        TransactionConfig transactionConfig = TransactionConfig.builder()
                .withTimeout(5, TimeUnit.SECONDS)
                .build();

        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->
                          (p:CapProject)
                    RETURN p.code AS code
                    ORDER BY code
                    LIMIT 100
                    """, Map.of("uid", uid))
                    .list(record -> record.get("code").asString()),
                    transactionConfig);
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

**Checks to verify:**

1. Create one **long-lived Driver** per application, never a new Driver per HTTP request.
2. `Session` is short-lived per unit of work and never shared across threads.
3. `executeRead` signals a read transaction; with routing URIs in clusters, the driver routes to appropriate readers.
4. `.list(...)` consumes results inside the callback, so transaction timing covers streaming records back.
5. `LIMIT 100` bounds **returned rows**, yet cannot fix an unselective traversal before `LIMIT`.
6. `withMaxConnectionPoolSize(40)` does not cap system-wide connections at 40: multiple app instances and cluster members multiply total connections.
7. `withMaxTransactionRetryTime` does not make arbitrary errors safe to retry. Write callbacks must be idempotent and never trigger payments or emails inside retryable callbacks.

Numbers in the Java snippet are **for lab use**. Measure concurrency, processing latency, cluster size, and server connection budgets before deploying to production.

### 11.3. Spring Data Neo4j and Transaction Boundaries

With Spring Data Neo4j, URI and database settings usually live in Spring Boot config:

~~~yaml
spring:
  neo4j:
    uri: "${NEO4J_URI}"
    authentication:
      username: "${NEO4J_USERNAME}"
      password: "${NEO4J_PASSWORD}"
  data:
    neo4j:
      database: "${NEO4J_DATABASE:neo4j}"
~~~

In practice, use `@Transactional(readOnly = true)` for reads and `@Transactional` for writes along business boundaries. **Never treat annotations as hard resource caps or security controls**: timeouts, Neo4j roles, connection pools, query complexity, and service authorization still must be verified.

### 11.4. Do Not Raise Limits to Mask Bad Queries

Suppose an unbounded multi-hop traversal generates millions of intermediate rows. Raising heap from 1 to 8 GiB only **postpones the OOM**. Inspect the plan:

~~~cypher
EXPLAIN
MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->(p:CapProject)
RETURN p.code AS code
ORDER BY code
LIMIT 100;
~~~

In a test database, run `PROFILE` to inspect `Rows`, `DB Hits`, and operators. For write queries, **`PROFILE` executes and mutates data**, so never run it in production just for a plan. Tune queries, indexes, cardinality, and traversal depth before increasing resource quotas.

## 12. Monitoring: Observing Both Application and Neo4j

A useful dashboard answers: **where are users experiencing slowness?** Seeing `container running` or `CPU < 80%` does not prove the system is healthy.

~~~mermaid
flowchart TD
    A["HTTP / Application<br/>request latency, errors, throughput"] --> C["Correlation ID / tracing"]
    B["Java Driver<br/>pool, retries, exceptions"] --> C
    D["Neo4j Server<br/>queries, transactions, locks, cache"] --> C
    C --> O["Dashboard + alerts + runbook"]
~~~

### 12.1. Minimum Signals Table

| Group | Signal | Meaning |
|---|---|---|
| **Availability** | API readiness and DB connectivity | Can the service handle core business traffic? |
| **Latency** | p50/p95/p99 per endpoint and repository op | Typical speed and tail slowness |
| **Throughput** | Requests/s, successful queries/s, committed tx/s | Incoming load and completed work |
| **Errors** | API error ratio, Neo4j error codes, query failures | App, permission, query, or server faults |
| **Transactions** | Active, committed, rolled back, terminated | Transaction volume and failure modes |
| **Locks** | `waitTime`, `activeLockCount` where exposed | Potential write contention |
| **Memory/CPU** | Heap, GC, page cache, RSS, container OOM | Resource saturation |
| **Connections** | Pool wait, acquisition timeouts, Bolt connections | Connection bottlenecks |
| **Storage** | Free disk, store/log growth | Risk of running out of space |
| **Backups** | Backup success, backup age, restore test | Data recoverability |

**Keep units distinct:** requests/s ≠ queries/s ≠ transactions/s. One HTTP request can execute multiple Cypher statements, and one transaction can run multiple queries.

### 12.2. p95/p99 and Rates

Illustrative 60-second window (synthetic numbers):

~~~text
Query success counter: 10,000 → 10,300   = 300 queries
Query failure counter:    100 →    106   =   6 queries
Transaction rollbacks:     50 →     56   =   6 txs

Successful query rate = 300 / 60 = 5 queries/s
Query failure ratio   = 6 / 306 ≈ 1.96%
Rollback rate         = 6 / 60  = 0.1 tx/s
~~~

**Do not assume the 6 failed queries are the exact same 6 rolled-back transactions.** Counters have distinct definitions and one request can increment several events. When an exporter or DBMS restarts, counters can reset; use `rate`/`increase` functions suited to your metrics backend.

`p95` is a quantile of a **latency distribution**, not an average. Never compute `avg(p95_instance_1, p95_instance_2)` for cluster p95; aggregate histograms/distributions properly.

## 13. Baseline Monitoring: Logs and Application Instrumentation

Even when Community lacks full Enterprise server metrics, you can still establish solid application-layer observability.

### 13.1. Timing Repository Calls in Java

~~~java
long startNanos = System.nanoTime();
boolean success = false;
try {
    var codes = gateway.projectsOf("U01");
    success = true;
    return codes;
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    // Emit elapsedNanos, operation="projectsOf", success
    // to Micrometer/OTel; never use uid as a metric label.
}
~~~

This is a **snippet placed inside a method returning `List<String>`**, not a standalone Java file. The measurement spans everything inside `gateway.projectsOf`, including pool wait, query execution, and record retrieval.

In Spring Boot, use **Micrometer Timers** or OpenTelemetry histograms. Never attach `uid`, emails, full Cypher strings, or business parameters to metric labels: they leak sensitive data and cause **high cardinality**.

### 13.2. Structured Error Logging

The application should log:

- Stable operation names, e.g., `projectsOf` or `createMembership`.
- Java Driver exception class, Neo4j code, and GQLSTATUS when supported by your API/version.
- Non-sensitive request ID / trace ID.
- Database name, timestamp, duration, and retry count if instrumented.
- Error category: validation, authentication, authorization, transient, timeout, unavailable.

**Never log** passwords, tokens, emails, full parameter maps, or Cypher containing sensitive literals. Protect logs with access controls, retention limits, and searchability.

### 13.3. Inspecting Active Transactions

With monitoring privileges, in Neo4j Browser or cypher-shell:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount, currentQuery
RETURN database, transactionId, username, status,
       elapsedTime, waitTime, activeLockCount, currentQuery
ORDER BY waitTime DESC
LIMIT 20;
~~~

`waitTime` is **cumulative lock wait time**, not proof the transaction is **currently blocked**. `activeLockCount` shows locks currently held, not whether the transaction blocks others. Inspect `status`, capture multiple snapshots, and correlate with query logs and metrics.

Regular accounts may only see their own transactions; for system-wide visibility, use a dedicated **observer identity** with scoped monitoring privileges rather than granting admin to business apps.

## 14. Enterprise Extension: Query Logs and Prometheus

This section targets **self-managed Neo4j Enterprise** with server configuration access and supported metrics/logging features. Never paste these lines verbatim into Community or Aura assuming they take effect.

Example `neo4j.conf` for observability:

~~~properties
# Query logging: log queries taking longer than the lab threshold.
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false

# Prometheus endpoint: expose strictly on internal monitoring network.
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=0.0.0.0:2004
~~~

**Warning:** `0.0.0.0:2004` binds across container/host interfaces. Use it only behind strict **monitoring network policies and firewalls**; in Docker, never publish this port to the public Internet. If Prometheus runs on the same host, bind loopback and configure scraping locally rather than opening all interfaces.

**Query logs are not transaction logs.** Query logs diagnose Cypher execution, latency, and errors; transaction logs provide durability and recovery. Apply separate retention rules and never treat query logs as backups.

### 14.1. Selecting Real Neo4j Metrics

Logical metric names documented in Enterprise include:

~~~text
<prefix>.db.query.execution.success
<prefix>.db.query.execution.failure
<prefix>.db.query.execution.latency.millis
<prefix>.database.<db>.transaction.active
<prefix>.database.<db>.transaction.committed
<prefix>.database.<db>.transaction.rollbacks
~~~

`success`, `failure`, and transaction totals are **counters**; `active` is a **gauge**; `latency.millis` is a **histogram** or exporter-supported distribution. Exported Prometheus names vary in punctuation, suffixes, and labels.

Before writing PromQL, inspect the **actual `/metrics` payload** and `HELP`/`TYPE` headers to confirm database/member labels, version, and metric types. **Never build dashboards from guessed metric names and interpret empty charts as zero.**

### 14.2. Securing Metrics Endpoints and Query Logs

- Restrict who can read metrics and logs, since they reveal topology, traffic, users, and queries.
- Never enable `parameter_logging_enabled=true` on real user data just for convenient debugging.
- Use sampling or sensible slow-query thresholds; avoid logging every trivial query in production without assessing I/O overhead.
- Set retention windows and PII redaction/deletion rules per organizational policy.
- Never paste credentials or raw PII-bearing queries into support tickets.

## 15. Setting SLOs and Test Budgets

Without SLOs, “the database is fast” cannot be evaluated objectively. For the capstone, define **illustrative practice targets** (not Neo4j SLAs):

| SLO / Limit | Example lab target | How to measure |
|---|---|---|
| Project-read API p95 | Under 250 ms at defined test load | Micrometer/OTel or load test |
| Project-read API p99 | Under 750 ms under same workload | Proper histogram/distribution |
| API error ratio | Under 1% post warm-up on valid inputs | Final application responses |
| Query correctness | 100% of business test suite passes | Assertions against fixtures |
| Container memory | Stays within 4 GiB limit, zero OOM kills | Docker/host metrics |
| Pool acquisition | Zero acquisition timeouts at target load | Driver/app instrumentation |
| Authorization | Reader leaks zero sensitive properties/labels | Positive/negative tests |
| Recovery | Runbook and restore test within project scope | Drill report |

**Latency targets are meaningful only when accompanied by:** concurrent request rate, test duration, read/write ratio, graph size, hardware specs, warm-up state, and edition. A two-user graph never proves a production system meets SLOs across millions of nodes.

### Never Tune One Knob to Cure Every Symptom

| Symptom | Hypothesis to investigate | What NOT to do immediately |
|---|---|---|
| p99 climbs, server query latency normal | Pool wait, network, retries, mapping | Blindly enlarge page cache |
| High query `DB Hits`, wide fan-out | Missing index or suboptimal model/query | Only raise `-Xmx` |
| Heap/GC spikes sharply | Huge query state or poor heap sizing | Raise pool size indefinitely |
| Container OOM-killed while heap has headroom | Native/OS/page cache over-allocation | Claim “JVM had no error so DB is fine” |
| Write latency and `waitTime` climb | Hot-node contention / long transactions | Spawn unlimited writers |
| Query failures and rollbacks climb | Schema, permissions, timeouts, transient faults | Retry every exception blindly |

## 16. Controlled Load Experiments

### 16.1. Expanding Test Data Deterministically

On an isolated test database, create 5,000 `:CapLoadUser` nodes to test indexes and queries:

~~~cypher
CREATE CONSTRAINT cap_load_user_id_unique IF NOT EXISTS
FOR (u:CapLoadUser)
REQUIRE u.uid IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 5000) AS n
MERGE (u:CapLoadUser {uid: 'L' + toString(n)})
SET u.groupId = 'G' + toString(n % 25),
    u.score = n % 100;
~~~

Write a parameterized read query:

~~~cypher
MATCH (u:CapLoadUser)
WHERE u.groupId = $groupId
RETURN u.uid AS uid, u.score AS score
ORDER BY score DESC, uid ASC
LIMIT 50;
~~~

This is still a small practice dataset, not representative of multi-million-edge graphs. To compare query plans, add a range index:

~~~cypher
CREATE RANGE INDEX cap_load_group_score IF NOT EXISTS
FOR (u:CapLoadUser)
ON (u.groupId, u.score);
~~~

Wait until the index is `ONLINE`, then re-run the same query and parameters. Neo4j's planner may still choose a scan on tiny datasets; **never assert an index seek must appear in every trivial test**.

### 16.2. Stepped Load Testing

Suggested sample schedule:

| Phase | Suggested load | What to observe |
|---|---|---|
| Warm-up | A few req/s, data loaded | Connectivity, cache warming, config errors |
| Baseline | 10 req/s over measurement window | p50/p95/p99 and query correctness |
| Ramp | 20 then 40 req/s | Throughput, pool wait, CPU/RSS |
| Write probe | Targeted `MERGE` on distinct keys | Lock wait, rollbacks, duplicates |
| Cool-down | Return to baseline | Latency recovery and absence of resource leaks |

Rates in the table are **suggestions**—adjust to your machine's capacity. Never run unbounded concurrency benchmarks or unbounded `MATCH` traversals against production.

**Separate root causes:** if p95 climbs with concurrency, the culprit may be CPU, pool size, lock waits, or the query itself. Correlate signals rather than merely reporting “Neo4j handled 40 RPS.”

## 17. Failure Drills and Recovery Verification

Run the drills below **strictly in an authorized isolated environment**. The goal is practicing observability and safe recovery, not breaking live systems.

### Scenario A — Invalid Credentials

1. Attempt to connect using a wrong password.
2. Expect authentication rejection with zero Cypher executed.
3. Verify application logs never print the password.
4. Restore valid credentials and run `projectsOf("U01")`.

### Scenario B — Neo4j Temporarily Unavailable

1. In the lab, stop the Neo4j container in a controlled manner.
2. Send a test request; record exception types, timeouts, and API status.
3. Verify the app **does not retry infinitely** or hang.
4. Restart Neo4j, run readiness checks and verification queries.
5. Confirm data and constraints remain intact; persistent volumes still do not substitute for backups.

### Scenario C — Exhausted Connection Pool

1. In staging, temporarily set pool size smaller than expected concurrency.
2. Ramp concurrent requests **with a safe cap**.
3. Observe acquisition timeouts, waiting requests, and p95/p99.
4. Reduce load and verify the pool recovers cleanly.
5. Restore config and size pools using instance count, server limits, and measured load.

### Scenario D — Long Transactions / Lock Contention

1. In test Neo4j, create a dedicated `:CapTestAccount` node with a fixed ID.
2. Open two write sessions in **two separate transactions** updating that same node.
3. Keep the first transaction brief and controlled while observing the second transaction wait.
4. Query `SHOW TRANSACTIONS`, inspect `waitTime`, and compare app latency.
5. Commit/roll back and close both sessions—never leave dangling locks in the lab.

**You do not need to force deadlocks or OOM crashes** to pass the capstone. Controlled drills for auth, unavailability, timeouts, and lock contention suffice to prove monitoring and runbooks.

## 18. Backup and Recovery Verification

In production, **persistent volumes or clustering alone never guarantee data safety**. Backups need retention policies, access control, off-host storage, and verified restore drills.

### Recovery Checklist

1. Identify which backup tools your Neo4j version/edition supports; never run Enterprise backup commands on Community and blame data corruption.
2. Record backup timestamp, type (full/incremental if supported), storage location, and encryption status.
3. Test restoring into a **fresh test instance**, never overwriting an active primary.
4. Reconcile node/relationship counts per label/type, constraints/indexes, and core business queries.
5. Verify roles, credentials, and network rules on the restored instance.
6. Record observed data-loss window (RPO) and restoration duration (RTO).

**Managed services do not remove this responsibility:** providers may automate backups per tier, yet app teams still must verify restores actually satisfy recovery requirements. Never equate availability SLAs with RPO or RTO.

## 19. Capstone Integration Test Matrix

| ID | Scope | Test case | PASS condition |
|---|---|---|---|
| T01 | Connectivity | Valid / invalid credentials | Valid runs query; invalid is rejected |
| T02 | Network | Check Bolt/HTTP bindings | No ports exposed outside intended scope |
| T03 | Data | Seed fixture, run Java/SDN query | U01 returns exactly P01 and P02 |
| T04 | Schema | Create uniqueness constraints | Duplicate ID rejected; graph uncorrupted |
| T05 | Enterprise RBAC | Reader reads ID/name | Valid query returns expected rows |
| T06 | Enterprise RBAC | Reader reads email/CapSecret | Hides data admin confirms exists |
| T07 | Enterprise RBAC | Reader attempts `SET` | Rejected; property unchanged before/after |
| T08 | Resources | Verify heap/page cache/container caps | Limits active; zero OOM under design load |
| T09 | Driver pool | Check timeouts under bounded load | Zero timeouts at target load; errors carry codes/traces |
| T10 | Monitoring | Collect query latency and error metrics | Dashboard displays values with clear units |
| T11 | Transactions | Lock-wait drill | Wait observed and cleaned up cleanly |
| T12 | Failure | Stop/restart DB in lab | App fails boundedly and recovers cleanly |
| T13 | Backup | Restore rehearsal where supported | Post-restore data and schema reconciled |
| T14 | Security logging | Inspect logs and dashboards | Zero unnecessary secrets or PII |
| T15 | Regression | Re-test after config changes | Business results unchanged; SLOs still met |

Every test record should document **inputs, steps, expected output, actual output, evidence, and verdict**. For tests inapplicable to your edition, state the reason and residual risk instead of fabricating assumptions.

### Evidence Worth More Than UI Screenshots

- Parameterized Cypher queries with **non-sensitive** test parameters.
- Reproducible JUnit / Testcontainers assertions or test logs.
- Redacted query logs / exception codes with timestamps.
- Dashboards annotated with instance, database, and time window.
- Before/after config diffs alongside verified runtime setting outputs.
- Failover/restore rehearsal notes scoped to your environment.

## 20. Incident Runbooks

### 20.1. Slow API Responses

1. Check HTTP latency p95/p99 and request rate.
2. Compare against DB query latency to isolate whether the bottleneck is inside or outside Neo4j.
3. Inspect pool acquisition timeouts, retries, connection errors, and DNS/TLS.
4. Run `SHOW TRANSACTIONS` to spot lock-waiting or long-running transactions.
5. Check query logs (if supported) for real Cypher text and sanitized parameters.
6. Run `EXPLAIN`/`PROFILE` in a **safe environment** to inspect `Rows`, `DB Hits`, indexes, and fan-out.
7. Fix query shapes, indexes, or transaction boundaries before scaling resources if query logic is at fault.
8. Re-measure under the same workload and confirm business outputs remain unchanged.

### 20.2. Rising Transaction Failures

1. Classify by exception/code: auth, authorization, schema, deadlock/transient, timeout, unavailable.
2. Compare query failures vs. transaction rollbacks—never assume they are identical events.
3. Check recent role, constraint, index, or deployment changes.
4. For transient errors, use bounded managed-transaction retries and verify write idempotency.
5. For ambiguous commit errors, query by business key before re-creating records.
6. Document the incident timeline and update alerts/runbooks afterward.

### 20.3. Memory or Disk Approaching Limits

1. Inspect RSS/container memory, heap, page cache, GC, native memory, and free disk space.
2. Check for new queries, batch imports, heavy sorts/aggregations, or long-running transactions.
3. Check whether backup or log retention is consuming disk unexpectedly.
4. Shed load or pause background jobs per procedure if service outage is imminent.
5. Expand heap/page cache/disk only after confirming host capacity and recalculating the full budget.
6. Alert before OOM or disk exhaustion—never wait for the OS to kill the process.

## 21. Capstone Grading Rubric

Suggested 100-point rubric (illustrative self-check guide):

| Category | Points | Requirements for top marks |
|---|---|---:|
| **Architecture and threat model** | 15 | Clear trust boundaries, identities, network paths, sensitive data |
| **Security and negative tests** | 25 | Auth, edition-appropriate least privilege, zero data leaks, writes blocked |
| **Resource budgets and limits** | 20 | Sound heap/page cache/CPU/pool/timeout config tested under load |
| **Monitoring and alerting** | 20 | Latency/throughput/errors/locks/resources with sources, units, and baselines |
| **Testing, recovery, and runbooks** | 15 | Positive/negative tests, controlled drills, recovery and reconciliation |
| **Report and evidence** | 5 | Measured data and explicit limits without unverified claims |

**Production disqualifiers:** running long-lived services on admin credentials, exposing the database publicly without need, disabling auth/TLS over untrusted networks, failing to guard sensitive reads, or lacking backup/restore plans for critical data. A working demo can still fail production standards.

## 22. Common Mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Using admin `neo4j` user for all services | Excessive privileges; leaked creds jeopardize whole DB | Separate runtime, observer, and migration identities |
| Assuming Community includes Enterprise RBAC | Misunderstands edition capabilities | Document limits; choose edition/tier matching needs |
| Hiding email in DTOs while DB account reads all | Lacks defense in depth | Minimize DB grants where supported; test viewer auth |
| Committing passwords into Git | Leaks via history, backups, container images | Use secret managers, rotate, audit logs |
| Exposing `7474`/`7687` publicly on Internet | Expands attack surface | Bind loopback/private network, firewalls, and TLS |
| Setting `heap + page_cache = mem_limit` | Starves native/OS memory | Leave headroom; track RSS and OOM events |
| Enlarging pool to cure every slow request | Can overload the server further | Measure pool wait, query cost, and concurrency |
| Removing timeouts so imports “don't fail” | Long transactions hold locks and memory | Use bounded batches, checkpoints, job-specific timeouts |
| Tracking only average latency | Hides bad p95/p99 tail latency | Use histograms/SLOs per endpoint |
| Treating rollbacks = failed queries | Distinct metrics and causes | Track queries and transactions separately |
| Assuming high `waitTime` means currently blocked | It is cumulative wait duration | Combine with `status`, snapshots, and logs |
| Relying on `LIMIT` to stop wide traversals | Engine may expand millions of rows before `LIMIT` | Bound path patterns, add indexes, run `PROFILE` |
| Measuring Community and claiming Enterprise Prometheus | Ignores edition/metric availability | Verify real exporter payloads and capabilities |
| Assuming container “Up” means DB ready | Neo4j may still recover or business queries fail | Use readiness probes and integration queries |
| Treating Docker volumes as backups | Fails on volume loss or logical corruption | Implement backups and restore drills |
| Running fault injection on production | Risks real user outages | Drill strictly in isolated lab/staging |

## 23. Self-Check Exercises

### Exercise 1 — Memory Budget

A container has a **4 GiB** limit, max heap **2.5 GiB**, and page cache **2 GiB**. What is wrong with this design?

**Suggested answer:** Those two regions already exceed 4 GiB before native/off-heap/OS overhead, risking OOM kills. Shrink heap/page cache or raise the container budget on an adequately sized host, then measure RSS, page faults, and GC under realistic load.

### Exercise 2 — Which Layer Enforces Security?

A Community app strips `CapUser.email` from JSON responses, yet connects with credentials that can read every node and property. Can you claim “Neo4j enforces property-level least privilege”?

**Answer:** No. That is API-layer filtering. Database property restriction requires fine-grained RBAC in a supported edition/tier tested with a reader credential, while still enforcing HTTP user authorization in the app.

### Exercise 3 — Misinterpreted Latency

API p99 is 1,000 ms while server-side query latency is ~80 ms. What should you inspect before increasing Neo4j heap?

**Answer:** Connection pool wait, network/TLS overhead, driver retries, Spring entity mapping, application logic, HTTP queues, and external service calls. A single server query metric never captures the entire request path.

### Exercise 4 — Does Denied Access Always Throw an Exception?

Reader runs `MATCH (s:CapSecret) RETURN count(s)` and receives `0`. Does that mean the database has no `CapSecret` nodes?

**Answer:** Not necessarily. RBAC can hide nodes when `TRAVERSE` is absent. An admin must confirm the fixture actually contains nodes before citing the reader's `0` as authorization proof.

### Exercise 5 — Pool Sizing

A service runs 6 instances, each configured with max pool size 40. Can you claim the system opens at most 40 connections to Neo4j?

**Answer:** No. Each Driver/instance maintains its own pool, and clusters distribute connections across servers per topology. Calculate total connections across instances, server limits, replicas, and driver pool behavior.

### Exercise 6 — Retrying Writes

`CREATE (:Invoice)` drops connection right at commit. The app retries automatically, producing two invoices. What safeguards are missing?

**Answer:** Fixed business keys/request IDs backed by unique constraints, idempotent `MERGE` flows, status checks after ambiguous commit errors, and bounded retries. Transaction retries alone never guarantee system-wide exactly-once execution.

### Exercise 7 — Zero-Value Dashboards

A Prometheus dashboard shows no query latency data from a Community container. The student writes “0 ms because Neo4j is very fast.” Why is that wrong?

**Answer:** Missing metrics never equal zero. Check edition, exporter, and config, inspect raw metric payloads, and measure latency in the application. Document observability limits honestly instead of inventing numbers.

### Exercise 8 — Acceptance After Tuning

After increasing page cache, p95 drops, yet business tests report a missing project in the returned list. Should the update pass?

**Answer:** No. Resource tuning must never alter query correctness or drop permissions/data. Investigate why the result changed, inspect data/transactions/edges, and re-run both regression and load tests.

## 24. Sample Capstone Report Outline

A completed report should follow this structure:

~~~text
Project Name: Neo4j Capstone - Security, Observability, Resource Limits
Version / Edition / Environment:
Database / Topology:
Workload & Fixture Description:

1. Architecture Diagram and Connection Identities:
2. Security Configuration and Permission Matrix:
3. Heap, Page Cache, CPU, Memory, Pool, and Timeout Settings:
4. Dashboards and Real Measurement Sources:
5. Positive / Negative Test Results:
6. Load Test Results (RPS, p50/p95/p99, error ratio):
7. Failure Drill and Restore Rehearsal Results:
8. Residual Risks / N/A Due to Edition or Tier:
9. Production Go / No-Go Gates:
10. Runbooks and Component Owners:
~~~

If Neo4j Enterprise is unavailable, state explicitly **“fine-grained RBAC / server metrics: NOT TESTED on Community”** and explain how to verify them in a supported environment. A capstone honest about technical limits is far more valuable than an unsubstantiated “all PASS” report.

## 25. Official References

- [Neo4j Operations Manual — Configuration](https://neo4j.com/docs/operations-manual/current/configuration/)
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/)
- [Neo4j Operations Manual — Authentication & authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Query logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Transactions](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Neo4j Java Driver — Configuration](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

Docs at `current` URLs can evolve across releases. In real deployments, verify against your exact **Neo4j version, edition, Java Driver/SDN version, and managed service capabilities**; never copy Enterprise self-managed settings blindly into Aura or Community.

## 26. Key Takeaways

- **Security, monitoring, and resource limits are three complementary defense layers**, not interchangeable substitutes.
- **Successful authentication does not prove least privilege:** test effective privileges, hidden data, and denied writes where your edition supports them.
- **Heap, page cache, and native memory share the host/container budget:** combine database limits with query tuning and controlled timeouts.
- **Driver pools, timeouts, and retries must reflect measured workloads:** raising thresholds never fixes inefficient Cypher.
- **Track p95/p99, throughput, errors, rollbacks, locks, memory, and connections** from real sources—never turn missing metrics into zero.
- **A capstone passes only with empirical evidence:** accurate business queries, verified permissions, appropriate load tests, handled failures, and a tested recovery plan.
