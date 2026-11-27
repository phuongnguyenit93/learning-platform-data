# Aurora Clusters, Reader Endpoints, and Custom Endpoints

> **Chapter:** RDS and Aurora Databases  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; develop skills in service selection, secure application design, monitoring, recovery, and cost control.

## Learning Objectives

An online learning platform has an enrollment write API, high-volume course lookups, and long-running reporting jobs. If every query hits the same database instance, reporting queries can slow down critical transactions. **Amazon Aurora** provides a **DB cluster** model with one **writer** and multiple **Aurora Replicas (readers)** backed by shared distributed storage, along with **DNS endpoints** so applications connect to the right group of DB instances.

This lesson focuses on three core topics: **Aurora cluster** architecture, the **reader endpoint** for distributing read connections, and **custom endpoints** for routing a workload to selected instances. After studying this, you will be able to:

1. Distinguish Aurora DB cluster, DB instance, cluster volume, Availability Zone, and failover.
2. Choose between cluster/writer, reader, instance, and custom endpoints.
3. Explain why the reader endpoint **balances connections, not individual queries**, as well as writer fallback when readers are missing.
4. Configure custom endpoints of type **READER** or **ANY**, understanding `StaticMembers` and `ExcludedMembers`.
5. Analyze failover, promotion tiers, reader membership, DNS caching, and connection pools.
6. Apply read/write splitting, read-after-write handling, replica lag checks, and SQL permissions.
7. Leverage RDS Proxy, VPC/SGs, TLS, IAM, and Secrets Manager when needed.
8. Inspect configurations via **read-only** AWS CLI commands without creating or modifying RDS resources.
9. Propose monitoring, test cases, backup/restore, and costs suited to the workload.

## 1. Architecture of an Aurora DB cluster

### 1.1. An Aurora cluster is more than a single DB instance

A **DB cluster** is a logical unit containing a **distributed cluster volume**, a writer instance, Aurora Replicas, and endpoints for client connections.

~~~mermaid
flowchart TD
    APP[API / Workers] --> WEP[Writer endpoint]
    APP --> REP[Reader endpoint]
    APP --> CEP[Custom endpoint: reports]
    WEP --> W[Writer instance AZ A]
    REP --> R1[Reader 1 AZ B]
    REP --> R2[Reader 2 AZ C]
    CEP --> R2
    W --> S[(Shared Aurora cluster volume)]
    R1 --> S
    R2 --> S
    ST[Storage copies across 3 AZs] -. protects .-> S
~~~

| Component | Role | Key point to remember |
|---|---|---|
| DB cluster | Aurora management structure within a Region | Distinct from a standalone DB instance |
| Cluster volume | Shared, distributed logical storage | Compute is decoupled from storage |
| Writer/primary instance | Handles writes and reads | One writer in a standard cluster |
| Aurora Replica | Serves read queries and can be promoted | Can reside in another AZ; up to 15 replicas in supported models |
| Cluster endpoint | DNS pointing to the current writer | App uses this for SQL writes/DDL |
| Reader endpoint | DNS pointing to available readers | Distributes **new connections** |
| Instance endpoint | DNS of a specific instance | For testing/admin/diagnostics |
| Custom endpoint | DNS pointing to a selected set of instances | For specialized workloads |

Aurora is compatible with **MySQL or PostgreSQL** depending on engine/version. Query capabilities, SQL extensions, drivers, and specific features still depend on the engine family; do not assume all PostgreSQL/MySQL parameters behave identically.

### 1.2. Shared storage and Availability Zones

Aurora uses a distributed cluster volume with data replicated across **three Availability Zones**. Aurora documentation describes **six storage copies across three AZs**. The writer and readers share one logical cluster volume, avoiding a separate EBS copy per reader as in other replica models.

**Design implications:**

- Readers add compute capacity to process read queries; they do **not** give a single-writer cluster additional writers.
- Adding a reader in another AZ improves failover options.
- Storage replication provides durability, but **does not automatically guarantee application availability** if there is only one DB instance.
- Decoupling compute from storage lets Aurora promote a reader to writer without copying the entire dataset during role transition.
- Shared storage is also **not an independent backup**: accidental data deletion still applies to the cluster volume.

### 1.3. Writer and reader instances

The writer handles `INSERT`, `UPDATE`, `DELETE`, and schema changes like `CREATE TABLE`. Readers serve read workloads and act as failover candidates.

Suppose:

~~~text
Cluster: course-prod

Writer: course-prod-writer-1, AZ A
Reader: course-prod-reader-1, AZ B
Reader: course-prod-reader-2, AZ C

Data stored on one Aurora cluster volume.
~~~

A small application might start with only one writer and no readers. In that case, the **reader endpoint DNS still exists**, but there is no pool of read replicas to distribute across yet.

### 1.4. Aurora vs. traditional RDS Multi-AZ DB instance

| Criterion | Aurora cluster | Traditional RDS Multi-AZ DB instance |
|---|---|---|
| Compute | Writer + optional readers | Primary + standby for HA |
| Reading via replica | Aurora Replicas can serve queries | Standby in DB instance mode normally does not serve reads |
| Storage | Aurora shared distributed volume | Different storage/replication mechanism |
| Reader endpoint | Built-in reader endpoint | Do not treat standby as a reader endpoint |
| Failover | Promotes a reader or recovers primary | Switches to standby per RDS |
| Read scaling | Add reader instances | Depends on RDS engine/deployment/read replicas |

AWS also offers **RDS Multi-AZ DB cluster**, which is distinct from both RDS Multi-AZ DB instance and Aurora. This table compares only the traditional model to clarify the concepts.

## 2. Distinguishing Aurora endpoints

### 2.1. Decision table

| Endpoint | Illustrative hostname | When to use |
|---|---|---|
| **Cluster/writer** | `course.cluster-xxxx.ap-southeast-1.rds.amazonaws.com` | DML/DDL, write transactions, strict read-after-write |
| **Reader** | `course.cluster-ro-xxxx.ap-southeast-1.rds.amazonaws.com` | Large-scale reads tolerating replica lag |
| **Instance** | `course-reader-1.xxxx.ap-southeast-1.rds.amazonaws.com` | Debugging/query tuning against a specific instance |
| **Custom** | `course-reports.cluster-custom-xxxx.ap-southeast-1.rds.amazonaws.com` | Isolating a group of readers for reporting or ad-hoc queries |

Hostnames are **hypothetical** and do not point to real resources. Default ports are typically **3306** for Aurora MySQL and **5432** for Aurora PostgreSQL; check the actual cluster port rather than hard-coding.

### 2.2. Cluster/writer endpoint

Every standard Aurora cluster has a **writer endpoint**, maintained by AWS to connect to the current writer:

~~~text
jdbc:postgresql://course.cluster-xxxx.ap-southeast-1.rds.amazonaws.com:5432/appdb
~~~

Use for:

- `INSERT`, `UPDATE`, `DELETE`, DDL;
- Transactions that both read and write;
- Reads immediately after a commit that must see the new change;
- Locking/`SELECT FOR UPDATE`, migrations, and authorized administrative tasks.

**Do not think of the writer endpoint as a proxy that splits SQL automatically.** If you open a connection to the writer and send a `SELECT`, that query runs on the writer. During failover, the endpoint updates its target to the **new writer**, though existing connections may drop and the app must reconnect.

### 2.3. Built-in reader endpoint

Every Aurora cluster has a built-in reader endpoint. When eligible readers exist, the reader endpoint **distributes connection requests** across Aurora Replicas to offload read traffic from the writer.

~~~text
jdbc:postgresql://course.cluster-ro-xxxx.ap-southeast-1.rds.amazonaws.com:5432/appdb
~~~

**Four critical points:**

1. The reader endpoint **does not balance individual SQL queries**; each established connection stays bound to one instance.
2. Aurora readers can experience **replica lag**; do not use for strict read-your-writes operations without a proper consistency design.
3. If the cluster has **no available readers**, the built-in reader endpoint **can route connections to the writer**, and those connections can execute writes if the DB user is permitted.
4. You **cannot directly create, delete, or alter membership** of the built-in reader endpoint; for a specialized reader group, use a custom endpoint.

**Never use the reader endpoint as a security control to block writes.** A read-only DB account must be granted **SELECT-only** privileges in the database.

### 2.4. Instance endpoint

An instance endpoint points to a **specific DB instance**, handy for inspecting slow queries, CPU/memory, connection counts, replica lag, or query plans.

~~~text
course-reader-1.xxxx.ap-southeast-1.rds.amazonaws.com:5432
~~~

**Caution:** an instance can change roles after failover. The endpoint follows the **instance name**, not the role; an instance that is a reader today could be the writer tomorrow. Never hard-code a writer's instance endpoint in an app that needs automatic failover recovery.

### 2.5. Custom endpoint

A custom endpoint represents a **subset of instances** you define, used to isolate reporting groups or instances with different hardware sizes:

~~~text
Built-in reader endpoint -> reader-small, reader-medium, reader-report

Custom interactive -> reader-small, reader-medium
Custom reporting -> reader-report
~~~

Aurora distributes **new connections** across eligible instances rather than scheduling individual queries. AWS currently supports up to **5 custom endpoints per cluster** per documentation for provisioned and Aurora Serverless clusters.

### 2.6. Choosing an endpoint by workload

~~~mermaid
flowchart TD
    Q[DB Workload] --> D{Writes / DDL / read-your-writes?}
    D -->|Yes| W[Writer endpoint]
    D -->|No| R{Need isolation by capacity group?}
    R -->|No| RE[Built-in Reader endpoint]
    R -->|Yes| CE[Custom READER endpoint]
    Q -->|Debug specific instance| IE[Instance endpoint]
    Q -->|High pooled connections / failover| PR[RDS Proxy writer / reader endpoints]
~~~

## 3. The reader endpoint is a connection balancer

### 3.1. Not a query router

~~~mermaid
flowchart LR
    POOL[Java HikariCP pool] -->|New session 1| DNS[Reader endpoint DNS]
    POOL -->|New session 2| DNS
    POOL -->|New session 3| DNS
    DNS --> R1[Reader A]
    DNS --> R2[Reader B]
    DNS --> R3[Reader C]
~~~

A connection already established to reader A may run 200 `SELECT` statements on reader A. It does not automatically shift individual `SELECT`s to reader B or C. Consequently, if a connection pool creates all connections at once and holds them long-term, load distribution can become uneven.

### 3.2. Why is one reader at 80% CPU while another sits at 10%?

Common causes:

- JVM/OS/JDBC clients cache DNS for too long and keep connecting to the same IP;
- The connection pool holds sessions long-term without opening new connections;
- Heavy reporting queries run on one reader, even with few sessions;
- One reader is unhealthy or recently went through maintenance/failover;
- The app mistakenly uses an instance endpoint or a single-member custom endpoint;
- Auto Scaling added a reader, yet the app did not recycle connections.

**Do not immediately add more readers when you see skewed load**; first determine which DB instances the pool is connected to, actual session counts, and the query profile.

### 3.3. DNS TTL and HikariCP

Per Aurora best practices, if a client caches DNS, set a **TTL under 30 seconds** to pick up new IPs quickly after failover. This is an operational guideline, not a fixed-time DNS switch SLA.

Example Java security properties:

~~~properties
networkaddress.cache.ttl=10
networkaddress.cache.negative.ttl=1
~~~

These properties are normally set in **JVM security settings** or via `java.security.Security.setProperty(...)` early at startup; putting them in `application.properties` does not automatically apply them.

In HikariCP, `maximumPoolSize`, `minimumIdle`, `idleTimeout`, `maxLifetime`, `connectionTimeout`, and connection validation govern how connections are created and reused. Do not set `maxLifetime` to just a few seconds to force per-query load balancing; that causes connection churn and raises CPU.

### 3.4. The reader endpoint does not guarantee fair CPU distribution

A reader running a 15-minute reporting query can consume massive CPU/RAM even with a single pooled connection. The reader endpoint does not inspect SQL cost to move queries to another reader. For heterogeneous workloads, **custom endpoints** + query timeouts + DB grants + capacity planning are a cleaner solution.

### 3.5. Reader endpoint vs. RDS Proxy reader endpoint

| Criterion | Aurora reader endpoint | RDS Proxy read-only endpoint |
|---|---|---|
| Service | Aurora DB cluster | RDS Proxy fronting the cluster |
| Connection balancing | DNS at connection creation | Proxy manages target connections |
| Pooling | Handled by application | Pooling/multiplexing where eligible |
| DNS cache/failover | Client must re-resolve/reconnect | Proxy can reduce disruption |
| When no readers exist | **Can fall back to writer** | **Read-only proxy endpoint may error/wait**, not equivalent to writer fallback |
| Cost | No separate proxy service fee | Incurs RDS Proxy cost |

**An Aurora custom endpoint is not an RDS Proxy endpoint.** RDS Proxy also has its own networking, authentication, secrets, and quotas. The proxy does not replace business transactions or idempotency.

## 4. Custom endpoints: READER, ANY, and membership

### 4.1. Why group readers?

Suppose:

~~~text
writer:            db.r7g.large
reader-api-1:      db.r7g.large
reader-api-2:      db.r7g.large
reader-report:     db.r7g.2xlarge

Lookup API   -> reader-api-1 and reader-api-2
BI reporting -> reader-report
~~~

If both API and BI use the built-in reader endpoint, BI can still land on a small API reader and the API can land on the large reporting reader. Custom endpoints let you **assign instance groups** to match workloads.

### 4.2. CustomEndpointType=READER vs. ANY

| Type | Eligible instances | Best suited for | Caution |
|---|---|---|---|
| **READER** | Only reader roles in membership | BI, reporting, read-only APIs | If no eligible reader remains, connections may fail |
| **ANY** | Both writer and readers if in membership | Apps aware of topology that accept either role | Writes may hit a reader and error; heavy queries may hit the writer |

**The AWS Console currently creates custom endpoints as type ANY**, without offering a type selector in the creation screen. If you need type **READER**, use supported AWS CLI/API/IaC and verify `CustomEndpointType` after creation. Some API schemas list extra enum values, while Aurora custom endpoint guides focus on **READER/ANY**; verify actual engine/version support.

**Never use ANY as a second writer endpoint**, and never trust ANY to remain read-only. If a workload must be read-only, use type READER with a SELECT-only DB user.

### 4.3. StaticMembers — fixed list

~~~text
Custom reporting (READER):
  StaticMembers:
    - course-reader-report-1
    - course-reader-report-2
~~~

The endpoint includes only the listed instances that **hold an eligible role**. If Aurora Auto Scaling creates a new reader, **it is not automatically added** to static membership. Suitable when reporting should use only two approved high-memory readers.

### 4.4. ExcludedMembers — exclusion list

~~~text
Custom interactive (READER):
  ExcludedMembers:
    - course-reader-report-1

Eligible:
  all current/future readers
  except course-reader-report-1
~~~

When a new reader is added, an **exclusion-list** endpoint automatically includes the eligible new reader as long as its name is not in `ExcludedMembers`. This pairs well with Aurora Replica Auto Scaling.

**Only one list type** applies to a given endpoint: static inclusion **or** exclusion. You cannot combine both lists as simultaneous expressions. An instance can belong to multiple custom endpoints; monitor total load on each instance.

### 4.5. Membership dynamics during failover

Before failover:

~~~text
writer: course-primary
reader: course-reader-a
reader: course-reader-b

Custom READER static=[course-reader-a, course-reader-b]
~~~

After `course-reader-a` is promoted to writer:

~~~text
writer: course-reader-a
reader: course-reader-b

Custom READER eligible -> course-reader-b
~~~

With type **READER**, Aurora removes the newly promoted writer from the eligible set. With type **ANY**, that instance can remain in the endpoint as long as it stays in the membership list.

**Important:** membership updates do not automatically terminate all already-open database sessions. Sessions on the failed instance drop due to failover; other sessions remain open. Applications must handle stale connections and re-resolve DNS.

### 4.6. Choosing static vs. excluded

| Use case | Choice |
|---|---|
| Dedicate two powerful readers strictly to BI | READER + StaticMembers |
| Include all readers except one ETL instance | READER + ExcludedMembers |
| Have new auto-scaled readers join the API read group | ExcludedMembers |
| No need to separate readers by workload | Built-in reader endpoint |
| Both writer and readers eligible for a special task | ANY, after evaluating risks |
| Restricted to reading sensitive data only | READER + SELECT-only DB role + authorization |

### 4.7. Do not treat a custom endpoint as a security control

A custom endpoint only selects DB instances at **connection time**; it does not grant or revoke SQL privileges. If a DB role has `INSERT` permission, an ANY endpoint routing to the writer can still write; and a READER endpoint cannot replace SQL GRANTs. Combine:

- Separate DB credentials for readers;
- DB grants, schema/table/RLS permissions;
- VPC SGs and resource isolation;
- Query timeouts / resource governors where supported;
- Auditing and clear ownership for every endpoint.

## 5. Failover, role changes, and high availability

### 5.1. When the writer fails

Aurora can promote an Aurora Replica to become the new writer:

~~~mermaid
sequenceDiagram
    participant APP as Java application
    participant EP as Cluster writer endpoint
    participant W as Old writer AZ A
    participant R as Reader AZ B
    APP->>EP: SQL write connection
    EP->>W: Current writer
    Note over W: Failure
    Note over R: Aurora promotes reader
    APP->>W: Old JDBC session fails
    APP->>EP: Reconnect and resolve DNS
    EP->>R: New writer
    APP->>R: Safe retry / reconciliation
~~~

The DNS endpoint still represents the writer role, but **existing TCP/JDBC sessions do not migrate automatically**. The app must reconnect, invalidate broken pool connections, and retry safely.

### 5.2. Promotion tiers

Aurora supports **failover promotion tiers from 0 to 15**:

- Tier **0** is highest priority;
- Tier **15** is lowest;
- Within the same tier, Aurora weighs instance capacity/availability per service logic;
- Do not assume the instance with the lowest CPU is always promoted.

If a cluster has only a writer and no readers, Aurora must recover the primary host instead of promoting an existing reader, which can extend downtime. For stronger HA, place readers in **a different AZ from the writer**.

With Aurora Serverless v2, promotion tiers 0/1 can also affect minimum ACUs on serverless readers kept ready to replace the writer. Factor in cost rather than setting every reader to Tier 0 blindly.

### 5.3. Endpoints after a role change

| Endpoint | Post-failover behavior |
|---|---|
| Writer | DNS updates target to the new writer; app reconnects |
| Reader | Reader pool may change; if no readers remain available, may fall back to writer |
| Instance | Still points to the specific instance, though its role may have changed |
| Custom READER | Eligible instances adjust to exclude the new writer |
| Custom ANY | May continue including the promoted writer |
| RDS Proxy | Manages DB targets/connection pooling per its own semantics |

Existing connections may drop; in-flight queries may roll back or error. **A stable endpoint name does not mean transactions continue uninterrupted.**

### 5.4. Failover-aware transaction recovery

Balance deduction example:

~~~sql
BEGIN;
UPDATE wallet
SET balance = balance - 100
WHERE account_id = 'account-123';
COMMIT;
~~~

If the connection breaks **right after COMMIT but before the app receives acknowledgment**, the app does not know whether the operation succeeded. A blind retry could deduct twice. You need a **business operation ID**, unique constraints/idempotency, outcome reconciliation, bounded retry backoff, and transaction auditing.

Never run live failover tests on production just to verify a lesson. Failover causes disruption and potential cost.

### 5.5. Writer-only cluster

In a cluster with no readers:

- The reader endpoint still exists and can point to the writer;
- Read traffic competes with writes for CPU/RAM;
- Custom type READER has no eligible targets;
- An RDS Proxy read-only endpoint behaves differently from built-in reader writer-fallback;
- Failover has no pre-existing reader to promote.

**Always check `DBClusterMembers[].IsClusterWriter` and instance statuses**; never assume read scaling exists just because a reader endpoint hostname exists.

## 6. Read consistency and read/write splitting

### 6.1. Replica lag and stale reads

Aurora Replicas see the same shared cluster volume, yet **visibility of changes** can lag behind the writer. AWS notes Aurora Replica lag is typically very low under normal conditions, but it is **not guaranteed to be zero**, especially as write load or long-running queries rise.

Example:

~~~text
T0: Writer COMMIT enrollment.status = PAID
T0 + 5 ms: App SELECT status via reader A -> still PENDING
T0 + 40 ms: App SELECT again -> sees PAID
~~~

This is a **stale read**. Acceptable for a public course feed; for payment confirmation, financial authorization checks, update-after-read, or **read-your-writes**, you generally must read from the writer or use an explicitly designed and tested consistency mechanism.

### 6.2. Connection routing matrix

| Business flow | Requirement | Endpoint |
|---|---|---|
| Create course/enrollment | Write transaction | Writer |
| Read status right after payment | Read-your-writes | Writer |
| Course catalog search | Tolerates slight staleness | Reader |
| End-of-day summary reports | Tolerates replica lag, heavy queries | Dedicated reporting Custom READER |
| Check stock then deduct | Transaction/locking | Writer within same transaction |
| General statistics view | Eventual consistency valid | Reader or custom |
| Run DDL/migrations | Schema changes | Writer under change-control |
| Profile one DB instance | Exact target instance | Instance endpoint |

### 6.3. Do not split a read-then-write transaction

A transaction that reads and then writes, when locking/consistency is required, must run through the writer:

~~~sql
BEGIN;
SELECT seats_remaining
FROM course_capacity
WHERE course_id = 'course-123'
FOR UPDATE;

UPDATE course_capacity
SET seats_remaining = seats_remaining - 1
WHERE course_id = 'course-123' AND seats_remaining > 0;

COMMIT;
~~~

Sending `SELECT FOR UPDATE` to a reader conflicts with read-only roles and locking semantics. **Never route SQL solely by checking whether a string starts with `SELECT`**, because stored functions, CTEs, or transactions can mutate data or require session state.

### 6.4. Spring `@Transactional(readOnly=true)` does not auto-route

In Spring, `@Transactional(readOnly=true)` is primarily a **hint/semantics for the transaction manager/JPA/driver**; it does not mean the framework automatically connects to an Aurora reader endpoint. You need a **routing datasource** or two explicit DataSources/JdbcTemplates.

If using `AbstractRoutingDataSource`, the routing decision must occur **before acquiring the JDBC connection**, while also accounting for propagation, nested transactions, and async threads. For foundational needs, **two explicit connection pools** are easier to reason about than dynamic SQL routing.

### 6.5. Read-only DB roles protect the right layer

Suppose the app uses:

~~~text
app_writer:
  INSERT/UPDATE/DELETE privileges on required tables

app_reader:
  SELECT privileges on permitted schemas/tables
  no DML/DDL
~~~

Even if the reader endpoint unexpectedly points to the writer because no replicas remain, **the `app_reader` DB user still cannot write**. Endpoints are for routing, **not a security boundary**.

Illustrative PostgreSQL sandbox example:

~~~sql
-- Execute as an authorized DB admin in a test environment.
-- Never store plaintext passwords in source code or migration logs.
CREATE ROLE app_reader LOGIN;
GRANT CONNECT ON DATABASE appdb TO app_reader;
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO app_reader;
~~~

Actual SQL GRANTs depend on schema ownership, role inheritance, RLS, extensions, and engine version. `ALTER DEFAULT PRIVILEGES` applies only to **objects created by the corresponding role** unless another role is specified. Verify with permission tests and use Secrets Manager/IAM DB auth for logins as designed.

## 7. Java/Spring Boot example: two connection pools

### 7.1. Environment variables

Aurora PostgreSQL example:

~~~properties
db.writer.jdbc-url=jdbc:postgresql://${DB_WRITER_HOST}:5432/appdb?sslmode=verify-full
db.reader.jdbc-url=jdbc:postgresql://${DB_READER_HOST}:5432/appdb?sslmode=verify-full

db.writer.username=${DB_WRITER_USER}
db.writer.password=${DB_WRITER_PASSWORD}
db.reader.username=${DB_READER_USER}
db.reader.password=${DB_READER_PASSWORD}
~~~

With `verify-full` enabled, install the proper **AWS RDS trust CA** and driver TLS configuration in the runtime. Never commit passwords to Git. Inject variables from your secret store/runtime per policy; `DB_READER_HOST` is a **DNS name**, not a static IP.

### 7.2. Spring Boot 3.x, HikariCP, and JdbcTemplate

Abbreviated wiring example with the key classes and imports:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class AuroraPoolsConfig {

    @Bean("writerDataSource")
    @Primary
    DataSource writerDataSource(
            @Value("${db.writer.jdbc-url}") String url,
            @Value("${db.writer.username}") String username,
            @Value("${db.writer.password}") String password) {
        HikariConfig config = new HikariConfig();
        config.setPoolName("aurora-writer");
        config.setJdbcUrl(url);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(12);
        config.setConnectionTimeout(3000);
        return new HikariDataSource(config);
    }

    @Bean("readerDataSource")
    DataSource readerDataSource(
            @Value("${db.reader.jdbc-url}") String url,
            @Value("${db.reader.username}") String username,
            @Value("${db.reader.password}") String password) {
        HikariConfig config = new HikariConfig();
        config.setPoolName("aurora-reader");
        config.setJdbcUrl(url);
        config.setUsername(username);
        config.setPassword(password);
        config.setReadOnly(true); // JDBC hint; DB GRANT is still required.
        config.setMaximumPoolSize(16);
        config.setConnectionTimeout(3000);
        return new HikariDataSource(config);
    }

    @Bean("writerJdbc")
    JdbcTemplate writerJdbc(@Qualifier("writerDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean("readerJdbc")
    JdbcTemplate readerJdbc(@Qualifier("readerDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }
}
~~~

**Example scope:** dedicated Spring Boot auto-configuration/`TransactionManager`/JPA wiring may be required if your app uses JPA, Spring Data, or multiple DataSources. Pool sizes are placeholders. Verify drivers, dependencies, SSL, SQL timeouts, connection validation, and retries in integration tests.

### 7.3. Choosing the right JdbcTemplate in a service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class EnrollmentService {
    private final JdbcTemplate writer;
    private final JdbcTemplate reader;

    public EnrollmentService(
            @Qualifier("writerJdbc") JdbcTemplate writer,
            @Qualifier("readerJdbc") JdbcTemplate reader) {
        this.writer = writer;
        this.reader = reader;
    }

    public int countPublishedCourses() {
        return reader.queryForObject(
            "SELECT COUNT(*) FROM courses WHERE published = true",
            Integer.class
        );
    }

    public int confirmEnrollment(String id) {
        return writer.update(
            "UPDATE enrollment SET status = ? WHERE id = ?",
            "PAID", id
        );
    }
}
~~~

**Risk:** calling `confirmEnrollment` and immediately calling a read method via `reader` may return stale state before the new status appears. In payment flows, if immediate confirmation is needed, read back via `writer` or return the committed state from the transaction.

### 7.4. Transaction management with two pools

When using JPA, explicitly separate or configure:

- Matching `EntityManagerFactory` and `PlatformTransactionManager`;
- `@Transactional(transactionManager="writerTxManager")` for write flows;
- Dedicated read datasource/transaction manager if genuinely needed;
- Do not assume two transaction managers form a **distributed atomic transaction**;
- Do not run a single logical write transaction across two instances expecting unified isolation/locking;
- If routing dynamically within the same business logic is unavoidable, define clear rules and test failover.

### 7.5. Calculating total connections

Suppose the app runs 6 concurrent EC2/ECS tasks:

~~~text
max writer pool: 12 connections per app task
max reader pool: 16 connections per app task

theoretical app writer connections: 6 × 12 = 72
theoretical app reader connections: 6 × 16 = 96
~~~

This excludes admin connections, other workers, background jobs, autoscaling, or retry spikes. If reader DNS skews distribution, a single reader could receive most of the 96 connections. Monitor `DatabaseConnections` per **`DBInstanceIdentifier`**, not just the cluster total.

**Do not raise `maximumPoolSize` on `too many connections` without analysis.** You may need to shorten long-running transactions, reduce connection churn, tune app scaling, or evaluate RDS Proxy.

### 7.6. Startup validation without leaking secrets

The app should fail fast if `DB_WRITER_HOST`/`DB_READER_HOST` are missing, without logging full JDBC URLs or credentials. Report errors by **key name** and endpoint role; redact passwords and sensitive URL query parameters. On health endpoints, separate **liveness** and **readiness** to avoid heavy probes or false positives when one reader is temporarily unavailable.

## 8. RDS Proxy, connection resilience, and proxy reader endpoints

### 8.1. Why use RDS Proxy?

RDS Proxy sits between the app and Aurora, managing DB connections and aiding failover:

~~~mermaid
flowchart LR
    APP[Lambda/ECS/EC2 app] --> PW[RDS Proxy read-write endpoint]
    APP --> PR[RDS Proxy read-only endpoint]
    PW --> W[Aurora writer]
    PR --> R1[Aurora reader A]
    PR --> R2[Aurora reader B]
~~~

The default RDS Proxy endpoint supports read/write and routes to the writer. You can create a **read-only proxy endpoint** to route connections across Aurora readers. The proxy can reduce direct open connections, multiplex compatible workloads, and speed up reconnection when a reader becomes unavailable.

### 8.2. When doesn't the proxy solve everything?

- Does not automatically split read/write SQL if clients use a single endpoint;
- Does not increase a reader's CPU or RAM;
- Does not guarantee exactly-once transaction commits;
- Does not replace DB grants, SGs, or Secrets Manager;
- Session pinning or long-running transactions can reduce multiplexing efficiency;
- A proxy read-only endpoint may wait and fail when **no readers are available**, unlike the built-in Aurora reader endpoint;
- The proxy incurs **costs** and has its own limits/configuration.

When an app sees bursts of short-lived Lambda invocations, evaluate a proxy to prevent connection storms. Benchmark cost/throughput and verify compatibility with your Aurora engine/Serverless version.

### 8.3. When is an Aurora custom endpoint better than a proxy?

| Requirement | Appropriate tool |
|---|---|
| Route BI strictly to high-RAM readers | Aurora custom READER endpoint |
| Send all new connections to an explicit subset | Custom Static/ExcludedMembers |
| Reduce DB connections from thousands of clients | RDS Proxy |
| Failover-aware reconnect and connection management | RDS Proxy / appropriate AWS JDBC Driver |
| Two reader groups with different capacities | Custom endpoints, optionally paired with proxy where supported |
| Distribute every SQL query across readers | No standard Aurora endpoint does this automatically |

Do not confuse RDS Proxy endpoints with Aurora custom endpoints. Proxy endpoints have a **proxy target role**, while custom endpoints have a **custom endpoint type/membership**, with distinct APIs and ownership.

## 9. VPC, IAM, TLS, and Secrets Manager

### 9.1. Secure network connectivity

~~~mermaid
flowchart LR
    USER[Client] --> ALB[ALB]
    ALB --> API[App SG, private subnet]
    API -->|TCP 5432 / 3306| SG[DB Security Group]
    SG --> DB[(Aurora DB cluster private)]
    API -->|AWS API| SEC[Secrets Manager / KMS]
~~~

For production:

- DB instances belong in **private subnets**, `PubliclyAccessible=false`.
- The DB subnet group should span multiple AZs matching Aurora's architecture.
- DB SG allows **inbound only from the App SG** on the exact DB port.
- App SG outbound, NACLs, and routing must allow TCP traffic to the DB.
- If the app is cross-VPC, configure DNS, routes, peering/Transit Gateway/private connectivity, and matching SGs.
- Private apps calling Secrets Manager/SSM/KMS may need NAT or VPC endpoints depending on the service.
- Never open port 3306/5432 to `0.0.0.0/0` just to fix a timeout.

### 9.2. IAM roles vs. database logins

**AWS IAM** governs control-plane reads and secret retrieval such as `rds:DescribeDBClusters`, `rds:DescribeDBClusterEndpoints`, `secretsmanager:GetSecretValue`, and `rds-db:connect` scoped to the DB resource/user when IAM DB auth is supported.

**Database SQL roles** govern `SELECT`/`INSERT`/`UPDATE` on tables. An app IAM role with `rds:DescribeDBClusters` **does not become** a database superuser. A SELECT-only `app_reader` DB user **has no** AWS CLI permission to modify endpoints.

### 9.3. TLS verification

- Enable TLS/SSL on clients and verify the DB server certificate and hostname against the RDS CA bundle.
- Aurora PostgreSQL with JDBC can use `sslmode=verify-full` with proper trust CA configuration.
- Aurora MySQL requires TLS identity verification mode configured in MySQL Connector/J or the AWS JDBC Driver.
- Test CA rotations, DNS-based endpoints, and JDBC driver upgrades.
- Never disable certificate hostname verification to bypass SSL errors in production.

### 9.4. Secret rotation

Manage credentials via **Secrets Manager** or your organization's secret store:

~~~text
Writer credential -> dedicated secret for write operations
Reader credential -> dedicated secret, SQL SELECT-only
DB host -> DNS endpoint, less sensitive than the secret password
~~~

When rotating passwords:

1. Ensure the app/pool can refresh credentials;
2. Rotate using an approved workflow with rollback;
3. Verify new DB connections authenticate successfully;
4. Drain/replace stale pooled sessions as needed;
5. Monitor authentication errors and latency;
6. Never paste passwords, tokens, or secret versions into tickets or chat.

For IAM DB auth, verify token lifetime, driver, proxy, and certificate support; do not assume identical behavior across all engines/versions.

## 10. Monitoring, HA, and cost optimization

### 10.1. Key CloudWatch metrics

| Metric | Target | Why monitor |
|---|---|---|
| `CPUUtilization` | Writer and each reader | Hot CPU, imbalance |
| `DatabaseConnections` | Each DB instance | Pool pressure, connection leaks |
| `FreeableMemory` | Each DB instance | Memory pressure from queries/reports |
| `AuroraReplicaLag` / lag variants | Reader/cluster per engine | Stale reads, read throughput pressure |
| `DBLoad` (Database Insights/PI where supported) | DB load | Wait events, top SQL |
| `VolumeBytesUsed` | Cluster | Actual consumed storage |
| `VolumeReadIOPs`/`VolumeWriteIOPs` | Cluster | Storage I/O workload and cost |
| `ServerlessDatabaseCapacity` / ACU metrics | Serverless v2 where supported | Capacity scaling, throttling/cost |
| `FreeLocalStorage` | Instance per engine/class | Local/temp storage pressure |
| RDS events | Cluster/instance | Failover, maintenance, scaling, errors |

Metric names and availability can differ by Aurora MySQL/PostgreSQL version, Serverless vs. provisioned, monitoring tier, and dimensions. Run CloudWatch `list-metrics` on your actual cluster before creating alarms. **Never treat an empty metric as proof that there are no errors.**

### 10.2. Workload-driven alerts

- Reader A at 90% CPU while B is at 15% → check DNS, pools, and queries.
- `ReplicaLag` spikes after bulk writes → ease read pressure or route critical reads to the writer.
- Writer `DatabaseConnections` jumps after deployment → inspect Hikari pools and app scaling.
- Failover event fires → measure app recovery time and uncertain transactions.
- Custom endpoint loses its last eligible reader → alert immediately so reporting pipelines do not fail silently.
- New reader added yet receives zero sessions → check `StaticMembers`/`ExcludedMembers` and DNS caching.

### 10.3. Aurora Auto Scaling vs. Serverless v2

| Mechanism | What changes | Impact on endpoints |
|---|---|---|
| Aurora Replica Auto Scaling | **Number of reader instances** | Built-in reader endpoint gains readers; custom static lists do not add them automatically |
| Aurora Serverless v2 | **ACU compute capacity** of an instance | Endpoints continue targeting that instance even as capacity scales |
| Manual resize | Writer/reader instance class | May cause reboot/disruption; requires a maintenance plan |
| RDS Proxy | Pooling/routing between clients and instances | Proxy endpoints have their own lifecycle/quotas |

Aurora Auto Scaling has provisioning lag and conditions; **it does not absorb sudden traffic spikes instantaneously**. Plan minimum readers/capacity and Aurora Serverless v2 limits by engine/version/Region.

### 10.4. Backups/PITR and HA are separate concerns

Aurora Replicas and three-AZ storage replication provide **availability and durability**, but **do not replace backups**. When an app accidentally deletes data, readers reflect that deletion too.

You need:

- Automated backups, retention, and appropriate PITR/snapshots;
- Restore tests into a separate cluster;
- Measured RPO/RTO and recovery procedures;
- Encryption/KMS, snapshot sharing restrictions, and auditing;
- Care not to delete production clusters/snapshots during lab cleanup.

### 10.5. Cost

| Component | What can raise cost | How to manage |
|---|---|---|
| Writer instance | Compute instance-hours or ACUs | Right-size, monitor CPU/`DBLoad` |
| Aurora Replicas | Additional reader compute | Provision only enough for read/HA needs |
| Aurora Standard / I/O-Optimized storage | Storage + I/O per tier and pricing | Measure workload and compare both options |
| RDS Proxy | Proxy capacity/usage pricing | Benchmark pooling/failover value |
| Data transfer | Cross-AZ/cross-Region and egress per pricing | Choose topology/networking carefully |
| Backups/snapshots | Additional retention/storage | Lifecycle rules; keep necessary backups |
| KMS/Secrets Manager | Keys, secrets, and API requests | Appropriate caching/rotation |
| CloudWatch/Insights | Logs, metrics, DB Insights | Retention, sampling, targeted alerts |
| RDS Data API or add-on features | Service API requests | Enable only when needed |

Adding **extra readers just to use a custom endpoint is not free**. An Aurora custom endpoint itself is just routing, while the underlying reader compute and related services are billed. Use AWS Pricing Calculator for your exact Region and engine before finalizing the architecture.

### 10.6. Backups, global databases, and DR

Aurora Global Database connects **Aurora clusters across multiple Regions**, unlike a single-Region multi-AZ Aurora cluster. Secondary clusters have distinct read/write semantics, and during global failover/switchover, the app must route to the **new primary Region**. Do not assume a cluster writer endpoint in a secondary Region accepts writes before role promotion.

If cross-Region DR is required, design DNS/routing, global replica lag handling, RPO/RTO, and runbooks rather than merely adding custom endpoints.

## 11. Lab 1 — Exploring an Aurora cluster with the AWS CLI (read-only)

> **This required lab section does not modify AWS resources.** Use AWS CLI v2 in CloudShell or a workstation with sandbox IAM credentials. Required read permissions include `rds:DescribeDBClusters`, `rds:DescribeDBInstances`, `rds:DescribeDBClusterEndpoints`, `rds:DescribeEvents`, and `cloudwatch:GetMetricStatistics` as applicable. Never call `Create`/`Modify`/`Failover` on production or read customer database records.

### 11.1. Verify identity and Region

Bash example:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1
aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If using AWS CloudShell with active session credentials and no `aws-lab-dev` profile, omit `AWS_PROFILE` and `--profile` as needed. Check Account/ARN to avoid querying the wrong account.

### 11.2. List Aurora DB clusters

~~~bash
aws rds describe-db-clusters \
  --region "$REGION" \
  --query "DBClusters[?Engine=='aurora-mysql' || Engine=='aurora-postgresql'].{Id:DBClusterIdentifier,Engine:Engine,Version:EngineVersion,Status:Status}" \
  --output table
~~~

Output may be empty if no sandbox cluster exists, the Region is wrong, or permissions are restricted. **Do not create an Aurora cluster just to pass a lab step**, as compute and storage incur charges even with zero traffic.

### 11.3. Inspect cluster topology

Specify an **authorized** cluster:

~~~bash
CLUSTER=course-aurora-sandbox

aws rds describe-db-clusters \
  --db-cluster-identifier "$CLUSTER" \
  --region "$REGION" \
  --query 'DBClusters[].{Cluster:DBClusterIdentifier,Engine:Engine,EngineVersion:EngineVersion,Status:Status,WriterEndpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Port:Port,Members:DBClusterMembers}' \
  --output json
~~~

In `DBClusterMembers`, inspect:

- `DBInstanceIdentifier`: name of each instance;
- `IsClusterWriter`: `true` for the current writer;
- `PromotionTier`: reader failover priority;
- Count actual readers rather than relying solely on `ReaderEndpoint` existing.

**Interpretation example:** a cluster with 3 members—one with `IsClusterWriter=true` and two with `false`—means one writer and two Aurora Replicas (when healthy). Check each instance's status before assuming both readers are serving traffic.

### 11.4. Inspect a DB instance

Pick a `DBInstanceIdentifier` from `DBClusterMembers`, e.g., `course-reader-a`:

~~~bash
INSTANCE=course-reader-a

aws rds describe-db-instances \
  --db-instance-identifier "$INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[].{Id:DBInstanceIdentifier,Cluster:DBClusterIdentifier,Status:DBInstanceStatus,Class:DBInstanceClass,AZ:AvailabilityZone,Endpoint:Endpoint.Address,Port:Endpoint.Port,PromotionTier:PromotionTier,PubliclyAccessible:PubliclyAccessible}' \
  --output json
~~~

`Endpoint.Address` here is the **instance endpoint**. `PromotionTier` alone does not tell you writer vs. reader role—cross-check `IsClusterWriter` on the cluster. Review `PubliclyAccessible=true` against your network/security architecture; do not alter settings unapproved.

### 11.5. Observe all endpoints

~~~bash
aws rds describe-db-cluster-endpoints \
  --db-cluster-identifier "$CLUSTER" \
  --region "$REGION" \
  --query 'DBClusterEndpoints[].{Id:DBClusterEndpointIdentifier,Endpoint:Endpoint,Type:EndpointType,CustomType:CustomEndpointType,Status:Status,StaticMembers:StaticMembers,ExcludedMembers:ExcludedMembers}' \
  --output json
~~~

This is the most important command in this lesson.

| Output field | How to read it |
|---|---|
| `EndpointType=WRITER` | Built-in cluster/writer endpoint |
| `EndpointType=READER` | Built-in reader endpoint |
| `EndpointType=CUSTOM` | User-created custom endpoint |
| `CustomEndpointType=READER` | Custom endpoint targeting eligible readers only |
| `CustomEndpointType=ANY` | Can include both writer and readers |
| `StaticMembers` non-empty | Targets listed instances only; does not auto-add new readers |
| `ExcludedMembers` non-empty | Excludes listed instances; new eligible readers join automatically |
| `Status=available` | Endpoint is ready, though target instance/network must still be checked |

**Caution:** `EndpointType=READER` on the built-in endpoint **differs** from `CustomEndpointType=READER` on a custom endpoint. Distinguish those two fields in JSON output.

### 11.6. Read RDS events for the cluster

~~~bash
aws rds describe-events \
  --source-type db-cluster \
  --source-identifier "$CLUSTER" \
  --duration 1440 \
  --region "$REGION" \
  --query 'Events[].{Time:Date,Category:EventCategories,Message:Message}' \
  --output table
~~~

RDS events reveal failovers, maintenance, or topology changes. `--duration 1440` illustrates pulling a 24-hour window per API limits; older events outside retention will not appear. Event messages can include resource metadata; never paste raw output into public channels.

### 11.7. Check CloudWatch ReplicaLag

If reader `course-reader-a` emits the corresponding metric:

~~~bash
READER_ID=course-reader-a
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name AuroraReplicaLag \
  --dimensions "Name=DBInstanceIdentifier,Value=$READER_ID" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Average Maximum \
  --region "$REGION" \
  --output json
~~~

Depending on engine/version and dimensions, `AuroraReplicaLag` may differ or be absent. Check `cloudwatch list-metrics --namespace AWS/RDS` before drawing conclusions. On PowerShell/Windows, `date -d` does not work; use PowerShell `Get-Date` to format ISO UTC timestamps instead.

### 11.8. Lab summary table

| Check item | Actual result | Meaning |
|---|---|---|
| Cluster engine/version | ... | Determines JDBC driver and SQL dialect |
| Writer identifier/AZ | ... | Where write transactions run |
| Number of readers and AZs | ... | Read capacity / HA |
| Reader endpoint hostname | ... | Target for new read connections |
| Custom endpoint type | ... | `READER` or `ANY`? |
| StaticMembers/ExcludedMembers | ... | Is autoscaling membership dynamic? |
| Reader `DatabaseConnections` | ... | Is the pool balanced evenly? |
| `ReplicaLag` | ... | Is there stale-read risk? |
| RDS events | ... | Recent maintenance or failover? |
| DB instance `PubliclyAccessible` | ... | Matches security policy? |

**Expected outcome:** you can identify the current writer, actual reader count, which endpoints are built-in vs. custom, which custom endpoints use static vs. exclusion lists, and explain the risks of running heavy reports through the shared reader endpoint.

## 12. Lab 2 — Checking SQL role from an endpoint (optional)

> Run only on your own sandbox database with valid credentials/SQL grants. Requires proper VPC/private network path and verified TLS; never use production data accounts. This is **read-only SQL introspection**—do not create or alter tables.

### 12.1. Aurora PostgreSQL

Using `psql` with the CA file properly configured:

~~~bash
# Sandbox database only. Never place passwords directly in the command.
psql "host=$DB_READER_HOST port=5432 dbname=appdb user=app_reader sslmode=verify-full sslrootcert=/path/to/rds-ca-bundle.pem" \
  -c "SHOW transaction_read_only;"
~~~

An `on` result typically indicates the session is in read-only mode. Check `current_user` or run a lightweight query without touching PII to confirm the database role, but **never execute DML** to “test permissions” on real data.

If connected to the writer with a read-only user, `SHOW transaction_read_only` may not reflect the user's SQL GRANTs. Do not interpret `off` as permission to write to any table.

### 12.2. Aurora MySQL

Inspect instance/read-only variables per engine/version:

~~~sql
SHOW VARIABLES LIKE 'innodb_read_only';
SELECT @@hostname;
~~~

This is a **non-mutating inspection example**. Results can vary across engine versions or Aurora features; never hard-code hostnames/IPs returned from queries into application connection strings.

### 12.3. Do not test failover on production

Some online guides suggest calling `aws rds failover-db-cluster` to watch DNS switch. That command **causes major impact** and can interrupt active transactions. This lesson **does not require** running a live failover. Fault-recovery testing must use an approved sandbox with backups, a maintenance window, monitoring, and stakeholder ownership.

## 13. Lab 3 — Controlled custom endpoint examples

> The commands in this section are **reference documentation only**; do not run by default. They **create/modify/delete RDS resources** and can affect live connections. Use only on an approved sandbox cluster with a rollback plan. Check engine, Region, membership, the 5-custom-endpoint quota, and IAM.

### 13.1. READER custom endpoint with static list

~~~bash
# MUTATING - SANDBOX ILLUSTRATION ONLY
aws rds create-db-cluster-endpoint \
  --db-cluster-identifier course-aurora-sandbox \
  --db-cluster-endpoint-identifier course-report-readers \
  --endpoint-type READER \
  --static-members course-reader-report-1 course-reader-report-2 \
  --region ap-southeast-1
~~~

After creation, run `describe-db-cluster-endpoints` and verify:

~~~text
EndpointType = CUSTOM
CustomEndpointType = READER
StaticMembers = [course-reader-report-1, course-reader-report-2]
Status = available once provisioning completes
~~~

**Do not assume an ANY endpoint created in the Console is equivalent** to READER. Always verify `CustomEndpointType` via the API.

### 13.2. READER custom endpoint with exclusion list

To let a custom group accept new auto-scaled readers while excluding the report reader:

~~~bash
# MUTATING - alternative to static-list, do not run both together.
aws rds create-db-cluster-endpoint \
  --db-cluster-identifier course-aurora-sandbox \
  --db-cluster-endpoint-identifier course-interactive-readers \
  --endpoint-type READER \
  --excluded-members course-reader-report-1 \
  --region ap-southeast-1
~~~

When AWS Auto Scaling adds a new reader, the exclusion-list endpoint automatically includes that eligible reader; a static-list endpoint does not. Monitor to ensure new instances match the workload profile.

### 13.3. Modify membership

~~~bash
# MUTATING - sandbox custom endpoint only
aws rds modify-db-cluster-endpoint \
  --db-cluster-endpoint-identifier course-report-readers \
  --static-members course-reader-report-1 course-reader-report-3 \
  --region ap-southeast-1
~~~

Open connections to a removed member **are not automatically dropped merely because membership changed**. New connections follow the updated membership once active; the app must manage pool lifecycles and avoid relying on stale DNS caches.

### 13.4. Delete a custom endpoint

~~~bash
# MUTATING - only after confirming no clients still use it
aws rds delete-db-cluster-endpoint \
  --db-cluster-endpoint-identifier course-report-readers \
  --region ap-southeast-1
~~~

**Never delete the built-in writer/reader endpoints**, and never delete a production custom endpoint before migrating all clients off it. Deleting an endpoint breaks new connection attempts; update connection strings first and allow drain time.

### 13.5. Minimal change review

~~~text
1. Verify account, Region, cluster, and endpoint identifier.
2. Check role + AZ + class + metrics of all members.
3. Confirm READER vs. ANY and static vs. excluded.
4. Compare new group capacity against expected workload.
5. Review migration of application connection strings.
6. Apply in sandbox; test read-only credentials and query latency.
7. Roll out in stages and observe DNS/pools.
8. Keep a rollback plan; do not delete the old endpoint too early.
~~~

## 14. Design scenario: course enrollment platform

### 14.1. Requirements

A Java/Spring Boot platform serving:

- 2,000 requests/second during registration peaks;
- Writes/updates to enrollments, payments, and audit logs;
- Heavily read course catalog tolerating 100–300 ms lag on some views;
- BI running 10–20 minute reports every hour;
- BI must not degrade write latency;
- Transactional read-your-writes required for payments;
- Multi-AZ HA, private database, and bounded budget;
- Read API should scale automatically, while report readers must use only dedicated powerful instances.

### 14.2. Proposed diagram

~~~mermaid
flowchart LR
    API[Spring Boot API] --> WR[Writer pool]
    API --> IR[Interactive reader pool]
    BI[BI/report workers] --> RP[Reporting reader pool]
    WR --> WEP[Cluster writer endpoint]
    IR --> C1[Custom READER endpoint interactive]
    RP --> C2[Custom READER endpoint reporting]
    WEP --> W[Writer - AZ A]
    C1 --> R1[Reader A - AZ B]
    C1 --> R2[Reader B - AZ C]
    C2 --> R3[High-memory reader - AZ C]
    W --> S[(Shared Aurora storage)]
    R1 --> S
    R2 --> S
    R3 --> S
~~~

| Workload | Endpoint | SQL user | Characteristics |
|---|---|---|---|
| Enrollment/payment writes | Cluster writer | App writer, limited DML | Transactions and read-after-write |
| Catalog reads | Custom interactive READER | App reader, SELECT-only | Exclusion list to accept auto-scaled readers |
| BI reports | Custom reporting READER | Reporting reader, SELECT-only | Static list of high-capacity readers |
| DB schema migrations | Writer | Explicit migration role | Change window / auditing |
| Reader diagnostics | Instance endpoint | Admin read-only | Inspect individual replicas |
| Bursts from many functions | RDS Proxy as needed | IAM/Secrets Manager + DB grants | Pooling and failover |

### 14.3. Why not just use the built-in reader endpoint?

The default reader endpoint balances new connections across **all eligible Aurora Replicas**. Heavy reporting queries could land on a small API reader, and API traffic could land on a dedicated reporting reader. Custom endpoints let you **segregate pools by purpose**. However, even an interactive custom reader endpoint does not auto-balance CPU/queries; app pooling and monitoring remain essential.

### 14.4. Handling read-your-writes

Payment flow:

~~~text
1. Receive payment callback and verify provider signature.
2. Write payment status + enrollment state via writer.
3. COMMIT transaction and record audit/idempotency key.
4. Return committed status or read back via writer.
5. Asynchronously update cache/search/reporting via events.
6. Other catalog UIs can use readers and tolerate lag.
~~~

Do not use the read-only `JdbcTemplate` to check whether a payment committed right after step 3 if the business flow requires immediate visibility.

### 14.5. Failover plan

- Writer in AZ A fails; Aurora promotes the reader in AZ B or AZ C by promotion tier/availability.
- The app writer pool discards stale connections and re-resolves the **cluster endpoint**.
- Interactive/reporting custom **READER** endpoints remove the newly promoted writer from their eligible sets.
- If the reporting group had only one reader and it got promoted, reporting loses its target: prepare an **explicit fallback** or scale an additional reader.
- Unknown transaction outcomes must be reconciled via idempotency keys, not retried blindly.
- Alert on RDS events, `DBConnections`, error rates, `ReplicaLag`, and recovery duration.

## 15. Common issues and how to handle them

| Symptom | Possible cause | What to check |
|---|---|---|
| App writes via reader endpoint hit `read-only` error | Real readers exist and write SQL used wrong URL | Use cluster writer endpoint for DML |
| Reader endpoint occasionally allows writes | Cluster has only a writer or no healthy readers; broad DB user | Check `DBClusterMembers`, DB roles; use SELECT-only account |
| Newly written data missing on screen | Replica lag / read-after-write | Read via writer on critical paths; measure lag |
| Reader A CPU high, Reader B low | DNS cache / pool stickiness / long queries | Connection targets, pool age, query profile |
| Added new reader but custom endpoint ignores it | `StaticMembers` does not auto-add | Switch to exclusion list or update static list |
| Custom READER fails to connect after failover | Only reader promoted; no eligible members left | Endpoint membership/cluster roles, availability |
| Custom ANY intermittently fails writes | Landed on a read-only replica | Use writer endpoint or custom READER for SELECTs |
| Console custom endpoint unexpectedly ANY | Console does not select READER type | Use supported CLI/API; verify `CustomEndpointType` |
| Connections still hit removed member | Existing open sessions or DNS/pool cache | Drain sessions, check lifecycle, TTL |
| Stale IP after failover | Long DNS cache, old pool connections | TTL <30 s per AWS guidance, reconnect |
| Writer endpoint unreachable | SG/NACL/DNS/port/engine status | SG source, network path, events |
| `too many connections` error | Sum of app pools too large | `DatabaseConnections`, `maxPoolSize`, RDS Proxy |
| RDS Proxy reader endpoint fails while built-in works | Proxy read-only has no available readers | Check available readers and proxy target health |
| `SSL certificate verify failed` | CA bundle/hostname/driver mismatch | RDS CA, TLS mode, certificate rotation |
| DB authentication fails after rotation | Pool holding old credentials | Secret refresh, new connections, key policy |
| Duplicate transactions after failover | Non-idempotent retries | Business operation ID, reconciliation |
| Reports slow down the writer | BI hitting writer or ANY custom endpoint | Read pool routing, role/SQL, `DBLoad` |
| Unexpected storage cost growth | Data/I/O/backup retention | Cost Explorer, metrics, I/O-Optimized comparison |
| Cluster has readers yet poor HA | Readers in same AZ or undersized | AZ placement, failover tiers, load testing |
| Read SQL gets permission denied | Reader DB user lacks GRANTs | SQL role/schema/table grants |
| Empty CloudWatch metric | Wrong engine/dimension/Region or no datapoints yet | `list-metrics`, RDS metrics docs |

### 15.1. 10-step runbook

~~~text
1. Confirm account, Region, cluster ID, and engine/version.
2. Inspect DBClusterMembers, IsClusterWriter, AZs, and status.
3. Inspect EndpointType/CustomEndpointType and StaticMembers/ExcludedMembers.
4. Verify app connection strings use the right writer/reader/custom endpoint.
5. Inspect events, CPU, DBLoad, DatabaseConnections, and ReplicaLag.
6. Check DNS TTL, JDBC pools, stale connections, and RDS Proxy.
7. Check SGs, ports, routing, TLS, and Secrets Manager.
8. For failed transactions, verify outcomes and idempotency.
9. Fix the exact fault layer; test sandbox/staging with negative cases.
10. Monitor, keep a rollback ready, and record audit/change logs.
~~~

## 16. Self-check questions

1. How does an Aurora DB cluster differ from a single DB instance?
2. What role does the shared cluster volume play in HA and reader scaling?
3. Can a standard Aurora cluster have multiple writers?
4. Does the reader endpoint distribute **queries** or **connections**?
5. If an Aurora cluster has no healthy readers, where can the built-in reader endpoint point?
6. Why shouldn't you rely on the reader endpoint to enforce SELECT-only permissions?
7. Does an instance endpoint still point to the same instance after failover? Can its role change?
8. What problem do custom endpoints solve compared to the built-in reader endpoint?
9. How does `CustomEndpointType=READER` differ from `ANY`?
10. Which type does creating a custom endpoint via the AWS Console usually produce?
11. How do `StaticMembers` and `ExcludedMembers` differ for auto-scaled readers?
12. With custom READER, when a member is promoted to writer, will new connections still pick that member?
13. Should you use an ANY custom endpoint as a writer endpoint?
14. Why might a Hikari pool send most load to a single reader?
15. What DNS TTL does AWS recommend if an app caches DNS?
16. What business bugs can replica lag cause in read-after-write flows?
17. Does Spring `@Transactional(readOnly=true)` automatically route JDBC to an Aurora reader?
18. Why must you separate writer and reader DB roles?
19. Is promotion tier 0 or 15 prioritized first during failover?
20. How does Aurora Auto Scaling differ from Aurora Serverless v2?
21. How does an RDS Proxy reader endpoint behave if the cluster has no readers left?
22. Why does having reader replicas not equate to having independent backups?
23. Which APIs inspect cluster topology and custom endpoints without modifying them?
24. During writer failover, why is idempotency needed in addition to reconnecting?
25. If BI queries are still too heavy despite a custom endpoint, what else is needed?

### 16.1. Answer hints

1. A cluster encompasses logical storage, instances, configuration, and endpoints; an instance is one compute node.
2. Storage is decoupled from compute and shared across the cluster; readers do not each copy an EBS dataset manually.
3. One writer in a standard single-writer cluster.
4. **New connections**, not individual queries.
5. **The writer**.
6. Endpoints handle routing; SQL `GRANT SELECT`-only is required for authorization.
7. The instance endpoint still points to the instance; the instance can switch between writer and reader roles.
8. Selecting a subset of instances per workload or capacity profile.
9. `READER` excludes the writer; `ANY` can include both writer and readers.
10. **ANY** per current Console behavior.
11. Static does not auto-add new readers; excluded automatically includes eligible new readers not on the exclusion list.
12. No, type `READER` updates eligibility based on role.
13. No; a connection could land on a read-only replica.
14. Long DNS caching, sticky connections, uneven query costs.
15. **Under 30 seconds** per Aurora best practices.
16. UI showing unpaid status after a committed payment; bad authorization or subsequent write decisions.
17. No; explicit datasource routing/config is required.
18. Defense-in-depth in case the reader endpoint falls back to the writer.
19. **0** is higher priority.
20. Auto Scaling adjusts the number of readers; Serverless v2 adjusts an instance's ACUs.
21. It may wait and fail, unlike Aurora's built-in reader fallback to writer.
22. Accidental deletes propagate on the shared cluster volume; snapshots/PITR are mandatory.
23. `describe-db-clusters`, `describe-db-instances`, `describe-db-cluster-endpoints`.
24. A transaction can commit before the ACK is lost; blind retries duplicate side effects.
25. SQL limits, sizing, query optimization, resource isolation, monitoring, and workload scheduling.

## 17. Pre-production checklist

### Clusters and endpoints

- [ ] Verified DB cluster, writer/reader instances, AZ distribution, and engine/version.
- [ ] Placed at least one reader in another AZ if HA requires it; promotion tiers match capacity.
- [ ] App writes/DDL use the **cluster writer endpoint**.
- [ ] Read workloads account for replica lag and read-after-write contracts.
- [ ] Reader endpoint is not used as a substitute for SELECT-only DB permissions.
- [ ] Custom endpoint type **READER/ANY** chosen intentionally for the use case.
- [ ] `StaticMembers`/`ExcludedMembers` have clear owners and align with Auto Scaling.
- [ ] Stayed within custom endpoint quotas and planned for zero-eligible-member scenarios.
- [ ] Instance endpoints used only when intentionally targeting a specific instance.

### Application and networking

- [ ] Separate writer/reader JDBC pools sized against total app replicas/instances.
- [ ] Tested DNS cache TTL, reconnect/validation, and failover recovery.
- [ ] Transactions implement idempotency/reconciliation with no blind retries.
- [ ] App SG → DB SG on the exact port, DB in private subnets, no arbitrary public access.
- [ ] TLS certificate/hostname verification working; driver and CA bundle up to date.
- [ ] DB credentials managed via Secrets Manager/roles with a rotation runbook.
- [ ] IAM control-plane permissions and SQL privileges governed independently.
- [ ] If using RDS Proxy, benchmarked both connection pooling and cost.

### Observability, DR, and cost

- [ ] Alerts set on CPU, `DatabaseConnections`, `ReplicaLag`, `DBLoad`, and failover events.
- [ ] Measured actual connection distribution across individual readers.
- [ ] Load-tested heavy reports, writer failover, and custom endpoint membership changes.
- [ ] Configured backups, PITR, and restore drills aligned with RPO/RTO.
- [ ] Dedicated Regional/global recovery plan in place if required by the business.
- [ ] Compared costs of reader instances, storage/I/O, RDS Proxy, Secrets Manager, KMS, and logs.
- [ ] Budgets, tagging, change-approval reviews, and sandbox cleanup ownership established.

**Expected outcome:** you can select the right Aurora endpoint for each workload, understand why the reader endpoint balances connections rather than queries and is not a security control, configure READER/ANY custom endpoints with proper membership, and plan read consistency, failover, security, monitoring, and cost.

## Official AWS documentation

- [Amazon Aurora overview](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_AuroraOverview.html)
- [Amazon Aurora endpoint connections](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Endpoints.html)
- [Aurora cluster/writer endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Cluster.html)
- [Aurora reader endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Reader.html)
- [Aurora instance endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Instance.html)
- [Aurora custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Custom.html)
- [Custom endpoint considerations, membership and type](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Custom.Considerations.html)
- [Creating Aurora custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-custom-endpoint-creating.html)
- [Editing custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-endpoint-editing.html)
- [Viewing Aurora endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-endpoint-viewing.html)
- [CLI tutorial for custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoint.Tutorial.html)
- [Aurora storage](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html)
- [Aurora replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html)
- [High availability and failover](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html)
- [Aurora failover procedure](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-failover.html)
- [Aurora Auto Scaling replicas](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Integrating.AutoScaling.html)
- [Amazon Aurora best practices including DNS TTL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.BestPractices.html)
- [RDS Proxy endpoints for Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy-endpoints.html)
- [Using RDS Proxy with Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy.html)
- [AWS CLI describe-db-cluster-endpoints](https://docs.aws.amazon.com/cli/latest/reference/rds/describe-db-cluster-endpoints.html)
- [Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Application note:** All DB cluster names, AWS account IDs, ARNs, hostnames, user names, SQL, and IAM examples in this lesson are **hypothetical training data**. Features, endpoint behavior, quotas, engine compatibility, and AWS pricing can vary by Region and engine version. Before deploying or modifying production, verify current AWS documentation, test in a sandbox, protect data, and follow change-approval processes.
