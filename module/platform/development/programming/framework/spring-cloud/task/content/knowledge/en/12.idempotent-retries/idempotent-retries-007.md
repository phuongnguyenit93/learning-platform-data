# Connection Drops or JVM Termination Mid-Update

In the **Idempotent Retries** chapter of the **SPRING_CLOUD_TASK** module, the key problem is not only "how to rerun after a failure," but **how to determine what already happened before the failure occurred**. A finite-running Spring Cloud Task application may write business data to a database, update metadata in `TaskRepository`, and exit. If the network drops or the JVM is killed right between those steps, business outcomes and execution state can diverge.

For example: a task generating the Nov 24 report wrote the report row to PostgreSQL. Right as the database completed `COMMIT`, the connection dropped; the program never received the acknowledgment. The scheduler sees a failed run and triggers a relaunch. If the second run blindly inserts a new report or adds an amount again, the system can create duplicate data even though the original fault was only in the network response.

This lesson explains **ambiguous commit outcomes**, distinguishes business transactions from Spring Cloud Task metadata, and builds a retry solution grounded in **idempotency keys, unique constraints, post-reconnect status checks, and bounded retry policies**.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish failures before `COMMIT`, failures while sending/receiving the `COMMIT` response, and failures after the database already succeeded.
- Explain why an exception or non-`0` exit code **is not sufficient proof** that business data rolled back.
- Distinguish `TaskExecution` in Spring Cloud Task from the business data source that determines whether a job finished.
- Design idempotency keys that remain stable across multiple runs, including when schedulers launch runs concurrently.
- Use transactions and `UNIQUE` or `PRIMARY KEY` constraints in PostgreSQL to prevent duplicate writes.
- Apply reconciliation procedures after connection drops, timeouts, JVM crashes, and runs that failed to update `TaskRepository`.
- Understand the limits of database transactions when combined with APIs, emails, message brokers, or file/object storage.
- Establish retry/backoff policies, coordinate with Spring Batch, and test failures at critical boundaries.

## 2. Core scenario: the database committed, but the application does not know

Suppose the task is invoked with:

~~~bash
java -jar daily-report-task.jar --tenant=shop-01 --businessDate=2026-11-24
~~~

The application intends to write **one** report for `(shop-01, 2026-11-24)`. During an execution, events may unfold as follows:

1. Spring Cloud Task records run startup in `TaskRepository`, if infrastructure is ready.
2. `ApplicationRunner` calls the report-generation service.
3. The service runs `BEGIN`, computes, and writes the business data row.
4. The application sends `COMMIT` to PostgreSQL.
5. PostgreSQL may have committed, yet the network drops before the response reaches the application.
6. The application or JVM fails; the scheduler receives no proof of completion.
7. The scheduler relaunches the same request.

**By step 5, the application cannot infer from the connection error alone whether the transaction committed.** Actual reality could be:

- **Committed:** data genuinely exists in the database.
- **Uncommitted / rolled back:** changes were not saved.
- **Unverified:** the database remains unreachable, or observations are not yet trustworthy.

An "unknown" state differs from a confirmed failure. A connection-closed exception around commit **does not automatically mean PostgreSQL rolled back**.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant T as Spring Cloud Task
    participant DB as PostgreSQL
    S->>T: Run report with business key K
    T->>DB: BEGIN; write report for K
    T->>DB: COMMIT
    DB--xT: COMMIT response lost
    Note over T,DB: App does not know commit outcome
    T--xS: Task fails / terminated
    S->>DB: Query by business key K once connected
    alt Matching K and matching fingerprint found
        DB-->>S: Already completed earlier
    else No confirmed data found
        DB-->>S: No result found
        S->>T: Retry idempotent operation
    end
~~~

In practice, the scheduler may delegate reconciliation to a separate application rather than querying the database directly. The diagram highlights the sequence of **verifying state before deciding to replay business effects**.

## 3. Analysis table of failure windows

Not every mid-update failure carries the same meaning.

| Failure timing | Possible business data state | What to do on rerun |
| --- | --- | --- |
| Before opening transaction | No changes from this attempt | Safe to retry if input is stable |
| Inside transaction, before `COMMIT` | Operations in the same transaction normally roll back if uncommitted, though DB may need time to clean up the dead session | Never guess from logs; rely on business keys and proper transactions |
| Sending `COMMIT` or losing response after `COMMIT` | **Indeterminate**: committed or not | Read durable state and replay idempotent operation |
| After business `COMMIT`, before updating `TaskRepository` | Business data exists; `TaskExecution` may remain open | Confirm business outcome, reconcile metadata, avoid creating a duplicate |
| After calling external API, before receiving response | API may have executed the effect despite client timeout | Use target-side idempotency key or query transaction status |
| JVM killed between steps of a multi-transaction workflow | Some steps committed, others did not | Track progress by business key/checkpoint and handle compensation |
| Two schedulers run the same request concurrently | Both sessions may read "does not exist" | Enforce DB unique constraints/locks, not just `SELECT` before `INSERT` |

**Key takeaway:** a **single-database** transaction guarantees atomicity for operations inside its transaction boundary according to database settings and semantics. It **does not automatically turn** writes across two databases, external API calls, emails, and Task metadata updates into a single distributed transaction.

## 4. Three state layers that must be reconciled

A real execution has at least three state layers:

| Layer | Source of truth | Meaning |
| --- | --- | --- |
| **Process** | Scheduler, Kubernetes Job, container, JVM exit code | Was the process created, is it running, or has it terminated? |
| **Spring Cloud Task execution** | `TaskExecution` in `TaskRepository` | How did the framework record start/end, exit code, and errors? |
| **Business** | Report tables, transaction ledger, object storage, idempotency table | Was the expected outcome written accurately, completely, and once? |

These layers can diverge. For example:

- Task has `EXIT_CODE=1`, yet the report committed right before the network failed.
- `TaskExecution.END_TIME IS NULL` because the JVM was killed, yet the business transaction finished.
- Task has `EXIT_CODE=0`, yet the application swallowed an exception or skipped output verification.
- No `TaskExecution` exists because `ApplicationContext` failed very early, even though the scheduler tried launching the process.

Spring Cloud Task tracks **application lifecycle**, without automatically making every runner operation idempotent. Each rerun can generate a new `TASK_EXECUTION_ID`; this technical ID **should not be used as a business deduplication key**, because it changes across attempts of the same request.

Decision rule: **verify completion from durable business state; use `TaskRepository` and the scheduler to explain execution history**.

## 5. What is idempotency and how should keys be chosen?

An operation is **idempotent** if re-executing the same request produces no unintended extra side effects after the first successful execution. For example:

- Writing a report for a date and tenant with the same data version: the first run creates it; subsequent runs recognize it already exists.
- Setting an order status to `PAID`: the second time does not charge money again.
- Sending a debit command twice is **not** idempotent without a deduplication transaction key at the payment service.

### 5.1. Keys must bind to the unit of work, not the run

For daily reports, the business key might be:

~~~text
tenantId + businessDate + reportVersion
~~~

For example:

~~~text
shop-01|2026-11-24|v1
~~~

Every attempt doing the same work must carry the **same key**. Never use launch timestamp, retry count, a freshly generated runner UUID, or `TASK_EXECUTION_ID` as the key, because each rerun gets a new key and breaks deduplication.

When a request carries the same key but **different content or input version**, define an explicit policy: report a conflict, create a new work version, or allow controlled updates. Never silently treat differing data as a valid duplicate.

### 5.2. Input fingerprint

Alongside the key, you can store `payload_hash` (e.g., SHA-256 of a canonicalized input representation) to compare:

- Same key, same fingerprint -> operation already completed earlier; can return the prior outcome.
- Same key, different fingerprint -> **CONFLICT**; investigate why two requests share an identity but differ in data.
- Key absent -> insert only through an atomic mechanism backed by a unique constraint.

Specify input normalization, timezone, field ordering, encoding, and algorithm version so the fingerprint never shifts across runs. If source data mutates continuously, freeze an input snapshot/version or design a versioned recalculation mechanism.

## 6. Why SELECT before INSERT is still not enough

An unsafe implementation:

~~~text
If SELECT finds no report for date D
    INSERT new report
~~~

Two concurrent tasks can **both see no record**, then both run `INSERT`. Pre-checking with `SELECT` only reads current visibility; it **does not replace database unique constraints**.

A more solid approach:

1. Enforce `PRIMARY KEY`/`UNIQUE` on the business key.
2. Attempt the write atomically inside a transaction.
3. If the key already exists, read the **committed** result and verify the fingerprint.
4. If same key but different data, raise a conflict; do not overwrite automatically.
5. If the database is unreachable, keep state as **UNKNOWN** rather than guessing outcomes.

With PostgreSQL, you can use `INSERT ... ON CONFLICT DO NOTHING`; in other databases use equivalent syntax and rules. Under stricter isolation levels such as `REPEATABLE READ` or `SERIALIZABLE`, handle serialization errors by retrying **the entire transaction** per an appropriate policy.

## 7. PostgreSQL hands-on: protecting a report from duplicate creation

The example below builds a Spring Cloud Task that creates an immutable report. "Created" state is defined by the **committed business record** in PostgreSQL, while `TaskExecution` metadata is recorded separately by Spring Cloud Task infrastructure.

### 7.1. Business schema

Use migrations to create the table in PostgreSQL:

~~~sql
CREATE TABLE daily_report (
    tenant_id       VARCHAR(64)  NOT NULL,
    business_date   DATE         NOT NULL,
    report_version  VARCHAR(32)  NOT NULL,
    payload_sha256  CHAR(64)     NOT NULL,
    report_body     TEXT         NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

The three-column primary key prevents the database from storing two rows for the **same tenant, same date, and same report version**. The example intentionally treats reports as immutable: to publish a new version, increment `report_version` per business rules instead of overwriting the old row.

Alongside this table, the Spring Cloud Task metadata database requires its **own schema defined by your framework version**. Do not create `TASK_EXECUTION` manually using business example DDL.

### 7.2. Dependencies and Spring Boot configuration

The Maven project needs **compatible versions** of Spring Boot and Spring Cloud Task. Typical dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Use the Spring Boot parent/BOM, import a compatible Spring Cloud BOM, and configure `spring-boot-maven-plugin` to build an executable JAR.

Example `application.yml`:

~~~yaml
spring:
  application:
    name: safe-daily-report
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: safe-daily-report
      initialize-enabled: false
~~~

Environment variables must point to a database already migrated with both the Spring Cloud Task schema and the `daily_report` table. `initialize-enabled: false` assumes the metadata schema already exists; avoid giving the runtime account unnecessary schema-altering privileges.

To keep things simple, the example shares one `DataSource`. **Even within the same database**, do not treat `TaskRepository` updates and the business transaction below as one atomic commit; they run at different stages of the application lifecycle.

### 7.3. ApplicationRunner with deterministic inputs

Create `src/main/java/com/example/task/SafeDailyReportApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class SafeDailyReportApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(SafeDailyReportApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner reportRunner(DailyReportWriter writer) {
        return args -> {
            String tenant = requiredOption(args, "tenant");
            LocalDate date = LocalDate.parse(
                    requiredOption(args, "businessDate"));
            String version = "v1";

            // Demo: deterministic content for identical inputs.
            // In production: read from a frozen snapshot/version.
            String body = "Report for " + tenant + " / " + date;

            String result = writer.saveOnce(
                    tenant, date, version, body);
            System.out.println("Report result: " + result);
        };
    }

    private static String requiredOption(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one --" + name + "=... is required");
        }
        return values.get(0).trim();
    }
}
~~~

This snippet generates fixed report content to **demonstrate idempotency**. For real reports, derive content from a versioned data snapshot rather than querying live "current data" each time and accidentally producing inconsistent fingerprints.

### 7.4. Service writing once via transaction and unique key

Create `src/main/java/com/example/task/DailyReportWriter.java`:

~~~java
package com.example.task;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDate;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyReportWriter {

    private final JdbcTemplate jdbc;

    public DailyReportWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public String saveOnce(
            String tenantId,
            LocalDate businessDate,
            String reportVersion,
            String body) {

        String hash = sha256(body);

        int inserted = jdbc.update("""
            INSERT INTO daily_report
                (tenant_id, business_date, report_version,
                 payload_sha256, report_body)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, report_version)
            DO NOTHING
            """,
            tenantId, businessDate, reportVersion, hash, body);

        if (inserted == 1) {
            return "CREATED";
        }

        String previousHash = jdbc.queryForObject("""
            SELECT payload_sha256
            FROM daily_report
            WHERE tenant_id = ?
              AND business_date = ?
              AND report_version = ?
            """,
            String.class, tenantId, businessDate, reportVersion);

        if (!hash.equals(previousHash)) {
            throw new IllegalStateException(
                    "IDEMPOTENCY_CONFLICT: same key, different content");
        }

        return "ALREADY_APPLIED";
    }

    private static String sha256(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

How it works:

1. `@Transactional` wraps the entire write-and-check decision. `saveOnce` is invoked **through the Spring bean** from the runner so the Spring transaction interceptor applies; do not self-invoke it from another method in the same class.
2. First run: PostgreSQL inserts one row. After `COMMIT`, the report exists durably.
3. Second run with same key and same content: `ON CONFLICT DO NOTHING` inserts nothing; the service reads the hash and returns `ALREADY_APPLIED`.
4. Same key with different content: the service throws `IDEMPOTENCY_CONFLICT`. This enforces "the same request must yield the same result."
5. If two processes run concurrently, the **primary key constraint** is the ultimate safeguard. PostgreSQL arbitrates lock contention; a standalone pre-`SELECT` would not suffice.
6. When the connection drops around `COMMIT`, the caller may receive an exception even though the true outcome is unknown. The scheduler may safely retry the **same idempotent operation** once connectivity returns, instead of using the connection error to infer a rollback.

The example assumes PostgreSQL's default **READ COMMITTED** isolation and a JDBC driver supporting `LocalDate`. Under higher isolation levels, concurrent races may throw serialization errors that must be classified and retried within bounds.

**Example caveat:** `CREATED` is returned from the method body before the transaction interceptor commits. The caller receives the normal return value only after the proxy commits successfully; if commit throws an exception, the runner must not treat an unconfirmed `CREATED` return as proof of commit.

## 8. First run, second run, and conflicting inputs

Suppose the artifact is `target/safe-daily-report-0.0.1-SNAPSHOT.jar`. With JDBC URL and credentials in environment variables, run the first time:

~~~bash
java -jar target/safe-daily-report-0.0.1-SNAPSHOT.jar \
  --tenant=shop-01 --businessDate=2026-11-24
~~~

Expected business output:

~~~text
Report result: CREATED
~~~

Run **a second time with the same parameters**:

~~~bash
java -jar target/safe-daily-report-0.0.1-SNAPSHOT.jar \
  --tenant=shop-01 --businessDate=2026-11-24
~~~

Expected output:

~~~text
Report result: ALREADY_APPLIED
~~~

The commands above use POSIX line continuation; in PowerShell, run on one line or use PowerShell line-continuation syntax. Running a third time with a different date creates a new record because the **business key differs**.

Verify in the database:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       payload_sha256,
       created_at
FROM daily_report
WHERE tenant_id = 'shop-01'
ORDER BY business_date, report_version;
~~~

After two runs with the same key, expect **one** row for `(shop-01, 2026-11-24, v1)`:

~~~sql
SELECT COUNT(*) AS report_count
FROM daily_report
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND report_version = 'v1';
~~~

`report_count` must equal `1` if database/schema are configured properly and runs finished as designed. To test conflicts, keep the same key while changing the business content in a **test environment**; the service must reject rather than overwrite.

Meanwhile, `TASK_EXECUTION` may contain **multiple rows** because each Spring Cloud Task launch is a distinct execution:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

**Multiple `TaskExecution` records paired with a single business outcome is the right behavior** for a retried idempotent task.

## 9. Decision workflow after losing connection

Avoid a rule of "immediately rerun on every exception." A safer workflow:

~~~mermaid
flowchart TD
    A["Run fails / JVM terminated"] --> B["Obtain business key and run-id from orchestrator"]
    B --> C{"Primary data source reachable?"}
    C -->|"No"| D["UNKNOWN: alert, backoff, recheck later"]
    C -->|"Yes"| E["Read committed outcome by business key"]
    E --> F{"Record exists?"}
    F -->|"Yes"| G{"Hash and business rules match?"}
    G -->|"Yes"| H["Already completed: do not create new record"]
    G -->|"No"| I["CONFLICT: investigate, do not auto-overwrite"]
    F -->|"No"| J["Retry same key with idempotent operation"]
    J --> K{"Write succeeded?"}
    K -->|"Yes"| L["Confirm outcome"]
    K -->|"Timeout / connection drop"| D
~~~

Read status from a source with **sufficient consistency** to make decisions. If the database has lagging replicas or an async cache, "no record found" might reflect stale data. When needed, read from the primary database or use strongly consistent reads.

A post-failure `SELECT` only **classifies** the situation; duplicate prevention must still be enforced by `UNIQUE`/`PRIMARY KEY` or an equivalent atomic barrier. If the first transaction is still running, the retry must still pass through that uniqueness barrier.

While the database remains unreachable, keep the state as **UNKNOWN/PENDING_RECONCILIATION**. You cannot declare an unverified attempt successful, nor assume the previous transaction rolled back.

### When a run reports FAILED even though business work completed

The scheduler can record a separate business-request state such as `COMPLETED_AFTER_RECONCILIATION`, linked to `run-id`, record evidence, and verification timestamp. Do not directly update `TASK_EXECUTION.EXIT_CODE` to `0` to tidy up history: the execution record remains valuable when it accurately reflects the incident that happened.

## 10. What if the work involves multiple steps?

A single transaction can wrap writes to **the same database**, yet should not be stretched arbitrarily across minutes or over network calls. If a task has multiple steps:

1. Load source data.
2. Generate report rows by batch.
3. Upload file to object storage.
4. Send notification.
5. Record completion status.

The JVM may die between step 2 and step 3. No standard JDBC transaction can automatically roll back an uploaded file or a sent email. Separate the **business completion point** and design each step to be re-runnable.

One possible state model:

| Business state | Meaning | Action on rerun |
| --- | --- | --- |
| `PENDING` | Not started or request registered | Eligible to be picked up via safe claim |
| `PROCESSING` | A worker is actively processing | Check lease/heartbeat before taking over |
| `COMPLETED` | Primary outcome verified | Return existing outcome; perform no extra effects |
| `FAILED_RETRYABLE` | Transient recoverable error | Retry after backoff using the same key |
| `FAILED_FINAL` | Data error or invariant violation | Escalate for investigation/data fix; no auto-retry |
| `UNKNOWN` | Unverified after commit/network fault | Reconcile before deciding |

These state names are a **business design pattern**, not a built-in Spring Cloud Task enum. Production systems must define valid transitions, concurrency rules, and authorization for changing states.

### 10.1. Leases and handling dead workers

If using a `task_request` table with worker ownership, store `lease_until` and a generational token (*fencing token*). A new worker takes over only when the lease expires via an atomic update; if an old worker wakes up after stalling, it must not write outcomes past a newer token.

Never treat an unbounded `PROCESSING` state as proof a worker is still alive forever. Conversely, seeing an expired lease does not prove the prior session produced no effects: keep idempotency keys at the write target.

### 10.2. Application checkpoints

For thousands of data groups, commit by chunk and save a checkpoint in each group's transaction. On rerun, read committed groups to skip or process idempotently. This shrinks rework scope, but requires unique keys **per group/record**, not merely for the overall job.

## 11. Side effects outside the database: APIs, emails, brokers, and files

### 11.1. Calling a payment API

If a task calls `POST /charge` and times out, you cannot assume the charge was not created. When the target supports idempotency keys, pass the **same stable key** on every attempt and query transaction status before issuing a new command. If the API lacks keys or lookup support, design reconciliation/compensation; never promise "exactly once" from client retries alone.

### 11.2. Transactional outbox for messaging

If you must update a database and emit an event, write **business data and an outbox row inside the same database transaction**, with a stable `event_id` and unique constraint:

~~~sql
CREATE TABLE outbox_event (
    event_id         VARCHAR(128) PRIMARY KEY,
    event_type       VARCHAR(80) NOT NULL,
    event_payload    TEXT NOT NULL,
    published_at     TIMESTAMPTZ
);
~~~

After commit, a separate dispatcher reads unpublished events, sends them to the broker, and marks them published. If the broker accepted the message but the dispatcher died before marking, the event **may be published again**. Therefore, consumers still need an **inbox/deduplication** table or idempotent handling by `event_id`. An outbox prevents losing publish intent when crashing mid-flow; it **does not guarantee end-to-end exactly-once delivery on its own**.

### 11.3. Writing files and object storage

Name outputs from the business key, such as `reports/shop-01/2026-11-24/v1.csv`, write to a temporary object, and verify checksums before publishing. If object storage supports conditional writes or versioning, use them to prevent unintended overwrites. If the database records `COMPLETED` before the file actually exists, the system can report falsely. Define completion criteria based on **both the status record and verified output artifact**.

## 12. Spring Cloud Task and Spring Batch do not solve everything automatically

### 12.1. TaskRepository is execution history

In Spring Cloud Task's lifecycle, start metadata is created once infrastructure initializes before the runner; end metadata is updated on completion or failure under normal conditions. If the JVM is killed or the database is unreachable, the record may lack `END_TIME`.

Never use `TASK_EXECUTION_ID` as a business deduplication key; a single request can produce multiple runs and multiple IDs. `TaskExecution` helps **trace runs**, whereas business keys and database constraints **prevent duplicate effects**.

### 12.2. Spring Batch has checkpoints, yet still needs idempotency

Spring Batch provides `JobRepository`, `JobExecution`, `StepExecution`, and `ExecutionContext` to manage jobs, steps, restarts, and checkpoints. When chunk processing is properly configured, committing data alongside checkpoints can resume from already-processed work. However:

- Not every `ItemWriter` participates in the exact same transaction as Batch metadata.
- Calling external APIs or writing files can leave side effects even when a JDBC transaction rolls back.
- Job parameters determine `JobInstance` per configuration; rerunning with different identifying parameters creates a new job instance.
- If connectivity drops around `COMMIT`, you must still verify committed data and actual job restartability.

When combining Spring Cloud Task with Batch, distinguish **application run history** (Task) from **job/step processing history** (Batch), and both from **business outcomes**.

## 13. Bounded retry policy

Retries handle transient faults, not mask every root cause. A policy can follow this table:

| Error | Auto-retry? | Conditions |
| --- | --- | --- |
| Network timeout, connection reset | Possible | Same key; after reconnect, reconcile or replay idempotent operation |
| Deadlock / serialization failure | Possible | Retry **the entire transaction**, bounded attempts, backoff |
| HTTP 429/503 from upstream | Possible | Honor `Retry-After` if present, idempotency key, total time cap |
| Malformed input | No | Fix parameters/data |
| Same key, different fingerprint | No | Conflict needing investigation or a new business version |
| Bad schema or missing DB privileges | Usually no | Fix deployment/migrations/permissions first |
| Payment command with uncertain outcome | No blind retry | Query transaction or rely on target-side deduplication key |
| JVM killed mid-task | Conditionally | Verify business state and prevent concurrent execution |

Configure **max attempts**, exponential backoff with jitter, an overall timeout, and alerts when limits are exceeded. If the scheduler retries the whole process while the task's client retries individual calls, compute the **combined attempt count** to avoid request storms.

A workflow-level policy:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    try:
        execute idempotent operation with same businessKey
        verify business outcome
        return COMPLETED
    catch non-retryable error:
        return FAILED_FINAL
    catch transient error or ambiguous commit:
        if primary data source is reachable:
            read outcome by businessKey
            if outcome and fingerprint match:
                return COMPLETED_AFTER_RECONCILIATION
            if fingerprint differs:
                return CONFLICT
        if still unverified:
            bounded backoff then retry or transition to UNKNOWN
~~~

This is **policy pseudocode**, not directly usable Java code. The inner business operation must be idempotent; otherwise a retry loop can corrupt data faster.

## 14. Testing failures at commit and JVM boundaries

A test that merely succeeds twice in a row **is insufficient**. Actively test failure windows in a non-production environment:

| Scenario | How to simulate | Invariant to verify |
| --- | --- | --- |
| Run twice with same input | Invoke task twice sequentially | One business record per business key |
| Two concurrent runs | Launch two processes with same key | Unique constraint blocks duplicates without overwriting |
| Failure before transaction | Throw before calling writer | Zero business side effects |
| Failure inside transaction before commit | Throw mid-write | Same-transaction operations do not partially commit |
| Response lost after DB commit | In integration test, simulate response error **after commit**, then trigger retry | Retry with same key returns prior result without creating a new row |
| JVM killed after commit, before Task metadata update | Intentionally kill process in that window in test | Business still has exactly one outcome; `TaskExecution` may look incomplete |
| API call followed by client timeout | Use fake API supporting idempotency keys | Target service creates no second side effect |
| Outbox dispatcher replays event | Simulate crash after publish before marking | Consumer recognizes `event_id` and skips duplicate work |
| Prolonged DB disconnection | Cut connectivity in test environment | Result transitions to UNKNOWN/alert, never falsely declares success |

**Note on fault simulation:** throwing an exception after a service returns simulates a caller failing **after commit**, yet does not prove how a real network drop behaves mid-`COMMIT` wire protocol. Full validation requires testing against production-equivalent drivers, databases, transaction managers, and deployment setups.

Never force-crash processes or sever live databases serving real users to test these scenarios.

### SQL-verifiable acceptance criteria

After multiple attempts with the same key:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       COUNT(*) AS records
FROM daily_report
GROUP BY tenant_id, business_date, report_version
HAVING COUNT(*) > 1;
~~~

With a proper primary key, this query must return zero duplicate rows. Yet **zero duplicate rows is not enough**: also verify fingerprints, report contents, output state, and that external side effects (if any) were not duplicated.

## 15. Safe operations and post-incident recovery

A mature operational process should include:

1. **Traceable business keys:** keep keys identical across attempts; also store scheduler `run-id` to correlate logs and each `TaskExecution`.
2. **Clear primary source of truth:** where business completion is confirmed; never rely on exit codes alone.
3. **Defensive schema:** appropriate `UNIQUE`/`PRIMARY KEY`, short transactions, and controlled migrations.
4. **Input data strategy:** freeze business date, timezone, and snapshot/version so the same key never sees shifting data.
5. **Reconcilability:** queries/states to detect `UNKNOWN`, overdue `PROCESSING`, `TaskExecution.END_TIME IS NULL`, and missing outputs.
6. **Safe retries:** error classification, bounded attempts, backoff, and no blind retries when external APIs have uncertain outcomes.
7. **Concurrency protection:** unique keys, locks/leases, or fencing tokens where needed; never non-atomic check-then-insert.
8. **Logs and alerts:** include correlation IDs; log commit/network errors without leaking passwords, tokens, or sensitive payloads.
9. **Recovery runbook:** operators can inspect attempt history, verify outputs, and decide to retry, compensate, or flag for intervention.
10. **Periodic testing:** exercise crash/timeout scenarios on staging before upgrading Spring Cloud Task, Spring Batch, or JDBC driver versions.

For audited systems, preserve technical execution history verbatim and record **reconciliation outcomes** in a separate table or orchestration system. Never erase initial failure evidence by directly updating execution metadata to "success."

## 16. Self-check exercises

**Question 1.** A task runs `COMMIT`, hits a "connection reset" error, and exits with code `1`. Can you conclude the transaction rolled back? Why or why not?

**Question 2.** Why can two runs `TASK_EXECUTION_ID=901` and `902` still represent **the same business request**? Which key should be used to prevent generating the report twice?

**Question 3.** Two instances both `SELECT` and see no report, then both `INSERT`. Does adding another `SELECT` before writing solve the problem completely? What must the database guarantee?

**Question 4.** A report record already exists for the business key, yet its SHA-256 differs from the new attempt. Should you return `ALREADY_APPLIED`, overwrite, or report a conflict? Explain the impact of each choice.

**Question 5.** An outbox event was published, yet the dispatcher died before updating `published_at`. When the dispatcher restarts, what additional mechanism is needed on the consumer side?

**Exercise A — Idempotent report:** run the PostgreSQL example with identical input at least three times; compare `CREATED` vs `ALREADY_APPLIED`, `TaskExecution` count, and `daily_report` row count.

**Exercise B — Race condition:** launch two processes with the same business key. Verify exactly one row exists with no overwrite. Capture the logs and how PostgreSQL resolved the conflict.

**Exercise C — Ambiguous commit:** in an integration test, simulate data committing while the caller receives an exception. Write a key/hash reconciliation step, then prove a rerun creates no second row.

**Exercise D — From database to API:** replace report writing with an external API transaction command. Design the idempotency key, status-lookup API, retry conditions, and manual investigation triggers.

## 17. Key takeaways

- **Network failures around `COMMIT` or JVM crashes do not prove a transaction rolled back.** The outcome may be indeterminate and must be reconciled.
- **`TaskExecution` records application lifecycle**, whereas **business keys and committed data** confirm whether work actually executed.
- **Idempotency keys must stay stable** across all attempts for the same request; `TASK_EXECUTION_ID`, timestamps, or attempt numbers are unsuitable as deduplication keys.
- **Database transactions and unique constraints** are a primary line of defense against retries and concurrent runs. `SELECT` before `INSERT` is not enough.
- For **APIs, brokers, or files**, JDBC transactions do not cover all side effects. Use target-side idempotency, outbox/inbox, reconciliation, or appropriate compensation.
- Retries require **error classification, bounds, backoff, and external state inspection**. When unverified, keep state **UNKNOWN** rather than falsely reporting success.
- Spring Batch supports job/step checkpoints and restarts, yet you must still protect external side effects and test crash points.

## References

- [Spring Cloud Task Reference — Task lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskExecution` lifecycle recording and limits during metadata initialization/writes.
- [Spring Batch Reference 5.1 — Batch Processing and Transactions](https://docs.spring.io/spring-batch/reference/5.1/transaction-appendix.html): transactions, retries, chunk processing, and boundaries for side-effecting operations.
- [PostgreSQL — COMMIT](https://www.postgresql.org/docs/current/sql-commit.html): semantics of a database-accepted commit.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): conflict handling and unique constraints.

When practicing, consult documentation, schema scripts, and versions matching your project's Spring Boot, Spring Cloud Task, Spring Batch, and JDBC driver stack.
