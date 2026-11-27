# Designing Idempotent Retries with Business Keys

## 1. Why does Spring Cloud Task need idempotency?

Spring Cloud Task helps build **short-lived** Spring Boot applications and records the lifecycle of each execution via `TaskExecution` in `TaskRepository`. A file import, day-close, reconciliation, or report export task may be triggered by a CronJob, API, CLI, or orchestrator. When failures happen, those systems often **rerun the same business operation**.

Common scenarios:

- The task committed data, but the JVM was killed before `TaskRepository` recorded the end time.
- The orchestrator did not receive a response and launched it again, even though the previous run may have already finished.
- An operator requests a backfill for a day suspected to have failed.
- Two instances simultaneously receive a request to process the same file or reconciliation period.
- A message broker redelivers a message after an acknowledgment timeout.
- An API client retries after a network disconnection.

For example, a revenue close task for `tenant-A` on `2026-11-23` already produced figures successfully. If rerunning adds the revenue again, the system may record **twice for one business intent**.

**Idempotency** means applying the same business intent again does not alter the effective outcome once that intent has already been applied successfully:

\[
apply(apply(S, K), K) = apply(S, K)
\]

Where `S` is the data state and `K` is the business key. This is a property of **business effects**, not a requirement that two runs share the same `TaskExecution` ID or identical logs. A retry can certainly create a new `TaskExecution`, but it must not produce unintended extra business outcomes.

## 2. Distinguishing TaskExecutionId from the business key

Common point of confusion: **`TaskExecutionId` only identifies a single application run**, not a unique business unit of work. Rerunning generates a new execution.

| Value | Example | Purpose | Stable across retries? |
|---|---|---|---|
| `TaskExecutionId` | `8191`, `8192` | Look up each run's history in TaskRepository | No |
| Pod or Job ID | `close-day-kx7kq` | Observe a scheduler execution | Usually no |
| UUID generated at runner startup | `a3bf...` | Technical tracing | No |
| **Business key** | `tenant-A / CLOSE_DAY / 2026-11-23 / revision-1` | Identify the intent that must take effect once | **Yes** |
| `eventId` from source system | `evt-1051` | Dedupe a specific event | Yes, if upstream reuses the event ID on redelivery |

For daily revenue closing, the key can be the tuple:

~~~text
(tenant_id, operation_type, business_date, revision)
= (tenant-A, CLOSE_DAY, 2026-11-23, 1)
~~~

For invoice ingestion, the key might be `tenantId + sourceSystem + externalInvoiceId`. For change-data synchronization, the key might be `source + entityId + sourceVersion`.

**The key must define precisely "when two requests are considered the same intent."** You often need tenant, source, task type, or processing version to prevent false collisions. However, adding `runAt`, current timestamp, a random UUID, or `TaskExecutionId` turns a retry into a **new key**, defeating duplicate prevention.

### Three scenarios to distinguish

| Scenario | Key to use |
|---|---|
| Retry due to timeout / transient failure | **Keep the same key** as the first attempt |
| Backfill an unfinished period | Use the key of the **period being backfilled**, not the current date |
| Recalculate because source data or rules changed | Use an **intentional new revision** if policy permits |

Never increment the revision merely to "dodge" a unique key error. A revision represents a new business action under explicit rules, such as replacing or adjusting an already published report.

## 3. Characteristics of a good business key

A useful idempotency key should satisfy these criteria:

1. **Deterministic:** the same business request produces the same key on every run, even across multiple JVMs.
2. **Properly scoped:** two different tenants do not accidentally block each other; two different task types do not share a key if they can run independently.
3. **Sufficiently granular:** two genuinely distinct intents are not collapsed into one.
4. **Runtime-independent:** do not use Pod ID, thread ID, `TaskExecutionId`, or newly generated timestamps.
5. **Persistently stored:** uniqueness is enforced in a database or an equivalent idempotency store.
6. **Retention policy:** do not purge deduplication state too early while messages/requests can still be replayed.
7. **No secret leakage:** you can log correlation IDs or selective hashes while avoiding unnecessary logging of sensitive identifying data.

You also need to define the key's **validity window**. A dedupe key for a published event may need to outlive the orchestrator's TTL; a third-party API key may have a shorter retention limit. If the TTL expires while an old request is still retried, duplicate side effects can occur.

## 4. SELECT-then-INSERT is not enough

Error-prone pattern:

~~~java
if (!repository.existsByBusinessKey(key)) {
    repository.createResult(result);
}
~~~

Two concurrent runs can both observe "does not exist yet" before either writes.

~~~mermaid
sequenceDiagram
    participant A as TaskExecution 101
    participant B as TaskExecution 102
    participant DB as Business Database
    A->>DB: SELECT key -> not found
    B->>DB: SELECT key -> not found
    A->>DB: INSERT key
    B->>DB: INSERT key
    Note over A,DB: Without UNIQUE, duplicate writes can occur
~~~

**You must enforce protection at the commit boundary with `PRIMARY KEY` or `UNIQUE`**, instead of only checking beforehand in application code.

PostgreSQL example for a daily revenue close:

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE finance.daily_revenue_close (
    tenant_id            VARCHAR(64) NOT NULL,
    business_date        DATE NOT NULL,
    revision             INTEGER NOT NULL CHECK (revision > 0),
    request_fingerprint  CHAR(64) NOT NULL,
    total_amount         NUMERIC(19, 2) NOT NULL,
    completed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_daily_revenue_close
        PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

The primary key means: **each tenant, each date, and each revision has at most one effective result**. If the request generates multiple detail records, apply corresponding unique keys and design a consistent transaction covering both summary and detail tables.

The constraint does not prevent creating multiple `TaskExecution` records; it protects the **business outcome table**. `TaskExecution` records must still be stored independently so you know how many attempts occurred.

## 5. Adding a fingerprint so different data is not silently skipped

Some systems receive **the same business key with altered content**. If you only look at the key and return "already processed," modified data can be hidden.

| Request | Business key | Fingerprint | Correct behavior |
|---|---|---|---|
| First run | `tenant-A/date-23/rev-1` | `abc...` | Write result |
| Retry with same data | `tenant-A/date-23/rev-1` | `abc...` | Reuse existing result |
| Same key, source modified | `tenant-A/date-23/rev-1` | `def...` | Report **conflict** |
| Valid recalculation | `tenant-A/date-23/rev-2` | `def...` | Process under new revision policy |

A **fingerprint** can be a SHA-256 hash of a canonical representation of the input request/snapshot. Fix field ordering, timestamp normalization, monetary rounding, record sorting, and calculation rule version.

Do not include run timestamps or trace IDs in the fingerprint, because they change on every retry. Also do not treat a hash as a substitute for a unique constraint or tenant authorization checks.

If source data mutates continuously, define an explicit **snapshot/cutoff**. You cannot promise recalculated results will be "identical" if the first attempt and a later attempt read different points in time without a revision policy.

## 6. Atomic insert-or-reuse strategy

For tasks writing outcomes within the **same database**, you can use a single transaction to insert the result or read back the existing result:

~~~mermaid
flowchart TD
    A["Runner receives business key"] --> B["Canonicalize input, compute fingerprint"]
    B --> C["INSERT ... ON CONFLICT DO NOTHING"]
    C --> D{"Was one row inserted?"}
    D -- Yes --> E["Commit new result"]
    D -- No --> F["SELECT existing result"]
    F --> G{"Does fingerprint match?"}
    G -- Yes --> H["REUSED / ALREADY_APPLIED"]
    G -- No --> I["CONFLICT: stop and investigate"]
~~~

PostgreSQL allows:

~~~sql
INSERT INTO finance.daily_revenue_close (
    tenant_id, business_date, revision,
    request_fingerprint, total_amount
)
VALUES (
    :tenant_id, :business_date, :revision,
    :request_fingerprint, :total_amount
)
ON CONFLICT (tenant_id, business_date, revision)
DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` prevents duplicate writes from adding extra rows, **but it does not compare fingerprints automatically**. If logic also writes to detail tables, execute those writes **in the same transaction** or use a consistent checkpoint model.

In PostgreSQL `READ COMMITTED`, a concurrent insert may wait for the transaction holding the unique key; once the conflict resolves, a subsequent `SELECT` sees the committed row. Under other isolation levels or SQL dialects, account for serialization/deadlock errors and retry transactions appropriately.

## 7. Spring Boot example: service saving an outcome once

The following Java 17 and Spring JDBC example illustrates idempotency for **a revenue close result in PostgreSQL**. Production systems must implement the aggregation and fingerprint calculation from the input snapshot.

### Model and result

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record CloseDayCommand(
        String tenantId,
        LocalDate businessDate,
        int revision,
        String fingerprint,
        BigDecimal totalAmount) {
}

public record CloseDayResult(
        boolean newlyApplied,
        BigDecimal totalAmount) {
}

public class IdempotencyConflictException extends RuntimeException {
    public IdempotencyConflictException(String message) {
        super(message);
    }
}
~~~

### Persistence service

~~~java
import java.sql.Date;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CloseDayPersistenceService {

    private final JdbcTemplate jdbc;

    public CloseDayPersistenceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public CloseDayResult saveOnce(CloseDayCommand command) {
        int inserted = jdbc.update("""
            INSERT INTO finance.daily_revenue_close (
                tenant_id, business_date, revision,
                request_fingerprint, total_amount
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, revision)
            DO NOTHING
            """,
            command.tenantId(),
            Date.valueOf(command.businessDate()),
            command.revision(),
            command.fingerprint(),
            command.totalAmount()
        );

        if (inserted == 1) {
            return new CloseDayResult(true, command.totalAmount());
        }

        return jdbc.queryForObject("""
            SELECT request_fingerprint, total_amount
            FROM finance.daily_revenue_close
            WHERE tenant_id = ?
              AND business_date = ?
              AND revision = ?
            """,
            (rs, rowNum) -> {
                String savedHash =
                    rs.getString("request_fingerprint").trim();

                if (!Objects.equals(
                        savedHash, command.fingerprint())) {
                    throw new IdempotencyConflictException(
                        "Same business key with different input");
                }

                return new CloseDayResult(
                    false, rs.getBigDecimal("total_amount"));
            },
            command.tenantId(),
            Date.valueOf(command.businessDate()),
            command.revision()
        );
    }
}
~~~

**Significance:**

- `PRIMARY KEY` guarantees two transactions cannot commit two results for the same business key.
- The first attempt that inserts the row receives `newlyApplied=true`; a retry with the same fingerprint returns the persisted data.
- On the same key with a different fingerprint, the service throws an explicit exception instead of silently treating it as complete.
- `@Transactional` requires the transaction manager of the **matching DataSource**. Do not invoke the method via `this.saveOnce(...)` inside the same bean if relying on Spring proxies.
- The example only protects the **inserted row**. Any HTTP call, file write, or message publish performed afterward needs separate protection.

This assumes `fingerprint` has been validated as a 64-character hex string, the result comes from a defined source snapshot, and the transaction uses an appropriate isolation level. For MySQL/SQL Server/Oracle, adapt the upsert syntax to the dialect.

### Spring Cloud Task Runner

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayRunnerConfig {

    @Bean
    ApplicationRunner closeDayRunner(CloseDayJobService jobService) {
        return args -> {
            List<String> dates = args.getOptionValues("date");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Must pass --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            // Service computes a deterministic fingerprint and calls saveOnce.
            jobService.run("tenant-A", date, 1);
        };
    }
}
~~~

`CloseDayJobService` is a business service required in the application; it prepares the data, computes the fingerprint, and calls `CloseDayPersistenceService`. In real deployments, the tenant should be read from a trusted source and authorized; the code only illustrates the business entry point.

~~~bash
java -jar close-day-task.jar --date=2026-11-23
~~~

Rerunning with the same input does not create another result. If the first run committed successfully and the JVM died before `TaskRepository` updated `END_TIME`, the second run still recognizes that the business key is already complete.

## 8. Race condition between two JVMs and the role of transactions

Suppose two CronJobs run concurrently for `2026-11-23`:

~~~mermaid
sequenceDiagram
    participant A as Task A / JVM 1
    participant B as Task B / JVM 2
    participant DB as Business Database
    A->>DB: INSERT business key
    B->>DB: INSERT same key
    DB-->>A: inserted=1
    DB-->>B: inserted=0 after conflict handling
    B->>DB: SELECT fingerprint and result
    DB-->>B: Committed result
    Note over A,B: Both TaskExecutions are still tracked separately
~~~

Actual results depend on commit order: if A rolls back, B can become the winning insert. The unique constraint is the true data boundary. In-JVM `synchronized` or `ReentrantLock` **cannot protect** two separate containers.

Do not treat every SQL error as "duplicate already succeeded." Timeouts, connection drops, serialization failures, and deadlocks require different handling. When write status is uncertain, query by business key before deciding to retry.

## 9. Multi-step work: claim, lease, and fencing

If a task processes hundreds of thousands of records or runs for hours, holding a single transaction for the entire duration is a poor design. You can persist progress by **commit unit** and use a work-claim table with a business key:

~~~sql
CREATE SCHEMA IF NOT EXISTS workflow;

CREATE TABLE workflow.task_claim (
    tenant_id           VARCHAR(64) NOT NULL,
    business_key        VARCHAR(200) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    owner_token         UUID,
    lease_until         TIMESTAMPTZ,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tenant_id, business_key),
    CONSTRAINT ck_claim_status CHECK (
        status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED')
    )
);
~~~

Processing flow:

1. Create the claim via `INSERT ... ON CONFLICT` with the business key; if it already exists, check the fingerprint.
2. The worker **atomically claims** from `PENDING`/`FAILED` or from a `PROCESSING` claim whose lease has expired.
3. The worker processes each partition and saves a checkpoint after commit.
4. The worker renews its lease while alive; before completing, it verifies ownership.
5. On crash, the coordinator only lets a new worker take over according to timeout policy and state reconciliation.

Example of claiming an existing row (PostgreSQL):

~~~sql
UPDATE workflow.task_claim
SET status = 'PROCESSING',
    owner_token = :new_owner_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND business_key = :business_key
  AND status <> 'SUCCEEDED'
  AND (
       status IN ('PENDING', 'FAILED')
       OR (
           status = 'PROCESSING'
           AND lease_until < CURRENT_TIMESTAMP
       )
  )
RETURNING owner_token, attempt_count;
~~~

Returning zero rows means the worker **did not acquire ownership**. Do not execute business logic as if the claim succeeded. For `PROCESSING` with an active lease, observe/wait; for `SUCCEEDED` with a matching fingerprint, return the prior result.

The completion update must also verify the owner token and lease:

~~~sql
UPDATE workflow.task_claim
SET status = 'SUCCEEDED',
    owner_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND business_key = :business_key
  AND status = 'PROCESSING'
  AND owner_token = :owner_token
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Check the affected row count. If it is 0, the worker no longer holds completion rights.

**A lease alone does not prevent duplicate side effects:** worker A can pause, its lease expires, B takes over, and then A resumes. In systems with strict guarantees, use a **monotonically increasing fencing token** or `ownership_version` checked on every write operation. For external APIs, the receiver must also support idempotency/fencing or have a reconciliation mechanism.

## 10. External side effects: outbox and idempotency keys

A JDBC transaction does not encompass HTTP calls, object storage writes, emails, or message publishing.

For example, the system commits an order to the database and sends an invoice-creation request via API. If the API accepts the request but the JVM dies before recording the response, a retry may issue a second invoice.

A common solution is the **transactional outbox**:

~~~mermaid
flowchart LR
    A["Spring Cloud Task"] --> T["Local transaction"]
    T --> B["Write business data"]
    T --> O["Write outbox event"]
    B --> C["COMMIT"]
    O --> C
    C --> R["Outbox relay"]
    R --> M["Broker / external API"]
    M --> D["Receiver dedupes by eventId or business key"]
~~~

In the same transaction, persist both the business outcome and the outbox event. A relay may republish after a crash, so the receiver **must be idempotent**. An outbox table can be designed as:

~~~sql
CREATE TABLE workflow.outbox_event (
    event_id      UUID PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    business_key  VARCHAR(200) NOT NULL,
    event_type    VARCHAR(64) NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMPTZ
);
~~~

If two attempts for the same business operation would generate two different `event_id`s, add a unique key corresponding to the logical intent (such as `tenant_id, business_key, event_type`) or derive a deterministic event ID. The message `eventId` and third-party idempotency key must be reused across retries per the API contract.

**There is no system-wide exactly-once guarantee** from an outbox alone. A broker may deliver at least once, a relay may republish, and an API has a TTL on its idempotency key. You must specify which boundaries perform deduplication and for how long.

## 11. Spring Cloud Task, Spring Batch, and business data

| Component | Tracks | Automatically prevents duplicate business writes? |
|---|---|---|
| Spring Cloud Task `TaskRepository` | `TaskExecutionId`, start/end, exit code of **each application run** | No |
| Spring Batch `JobRepository` | `JobInstance`, `JobExecution`, `StepExecution`, checkpoints | Does not automatically protect all external side effects outside transactions |
| Business table with unique key | Final outcome per business key | Yes, within the scope of constraints and transactions |
| Claim/checkpoint table | Progress, ownership, and committed work | Yes, when properly designed |
| Outbox/idempotent consumer | Events and effects on external systems | Within the implemented boundary |

With Spring Batch, **identifying JobParameters** plus job name define the JobInstance and support Batch's restart mechanism. However, if every run adds a new `run.id` as an identifying parameter, the job instance changes too. Therefore, the business key must still be part of your data design even when Batch uses checkpoints.

Example of two runs:

~~~text
TaskExecution 8191 -> CLOSE_DAY tenant-A, date=2026-11-23, rev=1
TaskExecution 8192 -> CLOSE_DAY tenant-A, date=2026-11-23, rev=1

Business database:
  (tenant-A, 2026-11-23, revision=1) -> one effective result
~~~

When the JVM dies after commit but before `TaskRepository` updates status, the first `TaskExecution` may lack `END_TIME`. The retry must inspect **business state** before writing again; do not rely solely on `TaskRepository` status to decide whether the business operation succeeded.

## 12. Error classification and retry rules

Idempotency makes retries safer, but it does not turn every error into something worth retrying.

| Situation | Appropriate response |
|---|---|
| Connection timeout, transient DB error | Bounded retry with backoff/jitter, keeping the same key |
| Duplicate unique key, matching fingerprint | Return `ALREADY_APPLIED` and the existing result |
| Duplicate unique key, differing fingerprint | Report `CONFLICT`; do not overwrite |
| Invalid input or unauthorized | Fail-fast; do not retry identically forever |
| Claim in progress, lease still valid | Wait/observe; do not steal work |
| Lease expired | Verify and take over with fencing/checkpoint |
| Uncertain if external API processed request | Query status by idempotency key, reconcile, or use outbox |
| TaskExecution missing END_TIME | Cross-check process, logs, and business data before deciding |
| Retries exhausted | Record failed status, alert, and preserve diagnostic trail |

Retries need **max attempts**, backoff, jitter, timeouts, and diagnostic context. Do not change the business key or revision just to make a retry go through.

~~~text
Transient failure -> backoff -> retry SAME business key
Permanent failure -> stop, alert, preserve evidence
Duplicate + same fingerprint -> return old result
Duplicate + different fingerprint -> explicit conflict
Unknown external outcome -> reconcile before replay
~~~

## 13. Testing concurrent processes and crash scenarios

Testing a task running twice sequentially verifies only part of the requirements. You must test:

| Scenario | Expected outcome |
|---|---|
| First run | Exactly one result committed |
| Retry with same key/fingerprint | No extra write; returns existing result |
| Same key with different fingerprint | Reports conflict |
| Two JVMs processing same key simultaneously | Unique constraint yields only one effective row |
| Crash before commit | Transaction rolls back; retry can proceed |
| Crash after commit, before TaskRepository end | Retry detects the result already exists |
| Worker A lease expires, B takes over | A loses ownership; no duplicate result committed |
| Event published, ACK lost | Consumer deduplicates via eventId/business key |
| Two tenants on same date | No false blocking across tenants |
| Reprocess under new revision | New valid revision created per policy |

Example verification query:

~~~sql
SELECT tenant_id, business_date, revision, COUNT(*) AS row_count
FROM finance.daily_revenue_close
GROUP BY tenant_id, business_date, revision
HAVING COUNT(*) > 1;
~~~

With a properly enforced primary key, this query must return **zero rows**. Yet that alone does not prove external side effects did not duplicate; verify downstream receivers, the outbox, and business outcomes.

A hands-on exercise:

1. Create the schema/table via migration with a unique constraint on the business key.
2. Configure Spring Cloud Task with an `ApplicationRunner` accepting the processing date; use a persistent `TaskRepository`.
3. Call `saveOnce` and log the business key, `TaskExecutionId`, and `APPLIED/REUSED` status.
4. Run two processes concurrently for the same date, then query the results table.
5. Simulate killing the process right after commit; rerun with the same parameters.
6. Alter the input while keeping the revision and confirm the system reports a conflict.
7. Test the event publishing flow and duplicate handling in the consumer.

You do not need a massive test suite before real deployment requirements exist, but the scenarios above should be verified before enabling automatic retries in production.

## 14. Common design mistakes

### "TaskExecutionId is an idempotency key"

**Wrong.** It changes on every launch. It is suited for attempt auditing and correlation, not for defining a business intent.

### "SELECT EXISTS then INSERT is enough"

**Wrong under concurrency.** Two transactions can both see no data. Use unique constraints, upserts, and transactions.

### "ON CONFLICT DO NOTHING solves everything"

**Insufficient.** You must distinguish same key/same data from same key/different data. External API calls, files, and events need separate protection.

### "Having PROCESSING means it will never run twice"

**False.** A worker can die leaving the claim behind, or wake up after its lease expires. You need timeouts, ownership checks, fencing, and checkpoints.

### "Spring Batch restart guarantees exactly-once"

**Not automatically.** Batch manages job/step state and checkpoints, but out-of-transaction side effects and business rules still require idempotency.

### "Bump revision to avoid unique conflicts"

**Wrong.** A revision is an intentional business change; auto-incrementing it on retry creates unwanted duplicate outcomes.

## 15. Pre-production design checklist

| Question | Passing criteria |
|---|---|
| Is "same intent" clearly defined? | Stable business key properly scoped by tenant/type/period/version |
| Is the key enforced at the commit point? | `PRIMARY KEY` or `UNIQUE` |
| Are same-key different-data cases distinguished? | Fingerprint/snapshot and conflict policy |
| Are business tables consistent? | Transactions/constraints across summary, detail, and checkpoint tables |
| Is concurrent multi-JVM execution safe? | Race testing and proper DB retry handling |
| Are external systems affected? | Idempotency keys, outbox, consumer dedupe, or reconciliation |
| Are there long-running tasks? | Claim/lease, fencing, heartbeat, and checkpoints |
| Are retries controlled? | Backoff/jitter, timeouts, max attempts, and error classification |
| Is TaskRepository confused with business state? | Separate attempt metadata from business outcomes, linked via correlation ID |
| Are post-commit crashes handled? | Retry reads business key before creating new effects |
| Is there a rule for reprocessing fixed data? | Explicit revision and clear rules for which version is effective |

**Conclusion:** A Spring Cloud Task may be rerun multiple times due to errors, timeouts, or operational requests. To prevent business results from being duplicated, you need **a stable business key**, **a unique constraint at the commit boundary**, **a fingerprint to detect changed data**, and **clear retry/concurrency rules**. `TaskRepository` records each execution; business tables, checkpoints, and outboxes protect real-world effects. Combining these two layers allows scheduled or on-demand applications to recover safely after failures.
