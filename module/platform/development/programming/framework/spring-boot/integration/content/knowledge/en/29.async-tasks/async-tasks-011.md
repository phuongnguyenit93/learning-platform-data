# Limitations of Local Scheduling Across Multiple Application Replicas

## 1. The problem: one schedule, multiple JVMs executing together

In a **Spring Boot Integration** service, scheduled jobs might call partner HTTP APIs for reconciliation, sweep outbox records to Kafka, refresh caches, or sync data from a database. On a single laptop, `@Scheduled` is straightforward. Yet once deployed across three replicas behind a load balancer, each JVM runs its own **local scheduler** unaware of whether another replica already ran the task.

For example, the same build runs across three pods, each hosting this bean:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationTimer {
    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    public void reconcile() {
        // Sync order reconciliation with external system.
    }
}
~~~

At 02:00 UTC, **all three pods can call `reconcile()`**. Spring does not elect a leader pod or grant distributed locks for `@Scheduled` by default. If the job updates balances, emits messages, or calls a rate-limited partner, running three times creates duplicates, inflates cost, and corrupts business state.

~~~mermaid
flowchart TB
    Cron["02:00 UTC: same schedule"] --> A["Replica A: @Scheduled"]
    Cron --> B["Replica B: @Scheduled"]
    Cron --> C["Replica C: @Scheduled"]
    A --> API["Partner HTTP / DB / Kafka"]
    B --> API
    C --> API
    DB[("Shared state store")] -. "No coordination yet" .-> Cron
~~~

**Lesson objective:** understand the scope of local scheduling, duplicate and missed-run scenarios across scaling or restarts, and choose cluster-level coordination. The goal is not merely **firing once**, but ensuring data consistency, retries, idempotency, failure testing, and integration observability.

## 2. What does `@Scheduled` actually guarantee?

Spring scans managed beans for `@Scheduled` and invokes callbacks per configuration **within the same application context/JVM**. Apps normally enable this via `@EnableScheduling`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Common scheduling modes:

| Mechanism | Principle | Multi-replica risk |
|---|---|---|
| `@Scheduled(fixedRate = ...)` | Periodic cadence relative to prior start time, per scheduler and execution capacity | Each replica runs its own cadence; total runs scale with replicas |
| `@Scheduled(fixedDelay = ...)` | Waits an interval after the previous run on that scheduler finishes | Serializes invocations only locally |
| `@Scheduled(cron = "...")` | Fires whenever wall-clock matches the cron expression | Every replica matches the same instant simultaneously |
| `initialDelay` | Delays first run after startup | Does not elect a leader or store cluster schedule state |

Key details to understand:

- **Schedules run per instance.** Scaling from one to five replicas can trigger five parallel executions of the same schedule.
- **Scheduler pools are local.** Increasing `spring.task.scheduling.pool.size` manages tasks inside one JVM, never stopping duplicates across JVMs. If callbacks can overlap or multiple triggers target one task, guard local contention too.
- **`@Async` does not replace distributed scheduling.** `@Async` dispatches to a JVM executor; it neither restricts a schedule to one replica nor preserves tasks if the process exits.
- **No durable history store by default.** If no instance is alive at cron time, the run is skipped; adding replicas does not replay missed schedules.
- **Cron uses time zones.** Declare `zone` explicitly instead of relying on OS defaults; when using local business zones, account for daylight saving time (DST) where applicable.

Therefore, `@Scheduled` is a **per-instance clock signal**, not a mechanism guaranteeing cluster-wide once-only pickup or completion.

## 3. Common failures in multi-replica deployments

### 3.1. Duplicate scheduled runs

Suppose a scheduler sends `POST /partner/settlements` at 02:00. If all three replicas fire and the partner API lacks idempotency keys, three settlement batches can be created. `synchronized`, `ReentrantLock`, and `AtomicBoolean` lock only inside one JVM; sibling replicas still run independently.

### 3.2. Missed runs when no instance is alive

During an upgrade right at cron time, all replicas briefly stop. When new pods boot at 02:05, standard `@Scheduled` **does not automatically backfill** the missed 02:00 slot. For daily reconciliation, persist schedules/slots in a database, implement catch-up logic, or use a scheduler with persistent history and misfire policies.

### 3.3. Old and new versions coexisting during rolling deployments

Old version A pods remain alive while new version B pods start up. Both can catch the same cron tick and even process data under different contracts. Infrastructure rolling updates create no transactional boundary for business jobs.

### 3.4. Tasks running longer than the interval

A sweep takes 20 minutes while scheduled every 5 minutes. Across multiple replicas, overlapping work piles up fast. Even when a local scheduler serializes callbacks, each JVM runs its own cycle. Separate **no overlap** from **no duplicate business intent**.

### 3.5. Process dies between external effect and recording completion

If replica A succeeds over Kafka or HTTP and crashes before marking the job complete in the database, replica B may run it again. Distributed locks coordinate who starts, yet **never automatically make non-DB side effects run exactly once**.

| Failure point | Potential consequence | Required mechanism |
|---|---|---|
| All replicas down at cron tick | Missed slot | Persistent schedule/slots, catch-up logic |
| Multiple replicas awake at tick | Duplicate runs | Shared claim/lock, or single central scheduler |
| Long task outlives lock TTL | New worker starts while old worker still runs | Lease renewal, generation (*fencing*) tokens, idempotency |
| External API receives request then times out | Unknown if side effect happened | Idempotency keys, status reconciliation, bounded retries |
| DB commits yet Kafka never receives event | Missing downstream event | Transactional outbox and relay |
| Kafka receives event before worker marks done | Redelivered event | Stable `eventId`, idempotent consumer |

## 4. Clarify requirements before picking a solution

Three distinct goals are often conflated:

1. **Only one instance starts a scheduled slot** (*single trigger*): coordinating which instance gets permission to begin.
2. **Work eventually finishes despite errors** (*at-least-once execution*): requires persisted state, timeout detection, retries, and catch-up.
3. **Business side effects apply only once** (*effectively-once business effect*): requires idempotency, unique/conditional updates, and target-side deduplication.

Distributed locks usually solve only the first goal under normal conditions. If an older worker stalls, loses contact with the lock store, and keeps calling APIs after lock expiry, a second worker can run concurrently. Protecting business invariants demands the other two goals as well.

Choose the right unit of granularity:

- **By time slot:** `reconcile:2026-11-21` for reconciling a single day.
- **By entity:** `customer:42:report:2026-11` for per-customer reporting.
- **By event:** `eventId` or `orderId + eventType + version` to deduplicate message processing.

Locks that are too coarse (like `all-jobs`) bottleneck unrelated tasks; keys that are too narrow (random UUIDs per retry) fail to stop duplicate business intent.

## 5. Cluster-level coordination options

| Option | How it operates | Best when | Key limitation |
|---|---|---|---|
| `@Scheduled` on every replica | Each JVM triggers independently | Per-instance read/refresh work safe to duplicate | No coordination, no automatic catch-up |
| Schedule enabled on one dedicated instance | One process acts as scheduler; workers skip scheduling | Low job volume, simple ops, clear failover plan | Scheduler outage halts triggers until failover |
| Distributed lock/claim via DB or Redis | Replicas wake up; only lock winner runs | Keeping `@Scheduled` while guarding a shared slot or batch | Must handle TTL/leases, crashes, disconnects, retries, idempotency |
| Durable DB job queue | Scheduler inserts work; workers claim individual jobs | Need backfill, retries, and parallel job execution | Requires state machine, leases, backlog monitoring |
| Quartz with clustered JDBC JobStore | Scheduler persists triggers/state in shared JDBC tables; nodes coordinate | Many triggers, dynamic schedules, misfire policies, history | Extra config, Quartz schema, operational overhead |
| Kubernetes CronJob / platform scheduler | Infra launches a Job Pod on schedule that exits when done | Isolating batch tasks from HTTP API replicas | Jobs can still miss or double-launch; needs idempotency and schedule guards |
| Broker / task queue | Producer enqueues work; consumer group distributes/processes | Heavy workloads needing retries and worker scaling | Broker doesn't supply schedule origin, dedup, or external atomicity |

**Practical choice:** no single tool fits all cases. To simply keep two replicas from running concurrently, a DB claim may suffice. To know whether every slot completed, persist **durable jobs or slot history**. For long jobs needing retries and horizontal workers, scheduler-enqueues + worker-consumes scales cleaner than running heavy work inside cron callbacks.

## 6. Baseline example: PostgreSQL unique keys for daily slot claiming

Suppose an integration service reconciles orders at 02:00 UTC daily, and only **one replica may claim the run** per day.

### 6.1. Slot tracking table

~~~sql
CREATE TABLE scheduled_run (
    job_name VARCHAR(120) NOT NULL,
    slot_key VARCHAR(32) NOT NULL,
    state VARCHAR(16) NOT NULL
        CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    PRIMARY KEY (job_name, slot_key)
);
~~~

The primary key `(job_name, slot_key)` enforces synchronization inside PostgreSQL across **every replica sharing that database/schema**, independent of which JVM arrives first.

### 6.2. Spring Boot implementation

Using Spring JDBC for an atomic claim:

~~~java
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyReconciliationScheduler {

    private final JdbcTemplate jdbc;
    private final ReconciliationJob reconciliationJob;

    public DailyReconciliationScheduler(
            JdbcTemplate jdbc,
            ReconciliationJob reconciliationJob) {
        this.jdbc = jdbc;
        this.reconciliationJob = reconciliationJob;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    public void runDaily() {
        LocalDate todayUtc = LocalDate.now(ZoneOffset.UTC);
        String slot = todayUtc.toString();

        int claimed = jdbc.update("""
                INSERT INTO scheduled_run(job_name, slot_key, state)
                VALUES (?, ?, 'RUNNING')
                ON CONFLICT (job_name, slot_key) DO NOTHING
                """, "reconcile-orders", slot);

        if (claimed == 0) {
            return; // Another replica already claimed this slot.
        }

        try {
            reconciliationJob.runForDate(todayUtc.minusDays(1));
            jdbc.update("""
                    UPDATE scheduled_run
                       SET state = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP
                     WHERE job_name = ? AND slot_key = ?
                    """, "reconcile-orders", slot);
        } catch (RuntimeException ex) {
            jdbc.update("""
                    UPDATE scheduled_run
                       SET state = 'FAILED', finished_at = CURRENT_TIMESTAMP
                     WHERE job_name = ? AND slot_key = ?
                    """, "reconcile-orders", slot);
            throw ex;
        }
    }
}
~~~

`ReconciliationJob` is an application service exposing `void runForDate(LocalDate date)` with the reconciliation logic. This code runs `JdbcTemplate` on the **scheduler thread**—never call blocking JDBC from a reactive event loop. If using R2DBC, an R2DBC repository can run the same atomic insert, ensuring you subscribe/await completion cleanly within the job lifecycle rather than leaving an unexecuted publisher.

**Precondition for this example:** the `INSERT` must commit **before** `runForDate` emits side effects. Notice the method has no `@Transactional` wrapping the entire callback; with default JDBC, each `jdbc.update` auto-commits when no Spring transaction is active. Wrapping claiming and HTTP/Kafka calls in one long DB transaction blocks other replicas on row locks, hurts throughput, and complicates error handling.

### 6.3. Guarantees and limitations of this example

This pattern guarantees **at most one claim row is created per slot** while replicas share PostgreSQL and claim rows aren't deleted. It **does not** guarantee completion:

- Pod dies after insert: row stays `RUNNING` forever; subsequent cron ticks won't reclaim it.
- Job throws: row turns `FAILED`; no retry policy exists and the next run skips it.
- All pods down at 02:00: nobody inserts the slot; bare `@Scheduled` skips it.
- Partner API succeeds before pod dies prior to `SUCCEEDED` update: unsafe to retry unless the API supports idempotency keys or status lookup.
- PostgreSQL/network fails: claiming errors out—log/metric/alert instead of "falling back" to running unclaimed, which breaks mutual exclusion.

Hence this is a **single-claim illustration**, not a complete job engine. Production needs recovery for stale `RUNNING`/`FAILED` rows, deadlines, retries/backoff, and side-effect idempotency.

## 7. From simple claims to lease-based work queues

For jobs requiring retries or lasting several minutes, split into two parts:

1. **Scheduler** computes missing slots and inserts jobs into a table or queue with a unique business key.
2. **Workers** claim due batches, execute them, record success/failure, and schedule retries.

Every instance can run both roles when creation and claiming are atomic, or you can centralize scheduling and scale workers independently.

### 7.1. Claiming batches with `FOR UPDATE SKIP LOCKED`

In PostgreSQL, `FOR UPDATE SKIP LOCKED` lets multiple workers claim **disjoint rows** from a job table:

~~~sql
CREATE TABLE scheduled_work (
    id BIGSERIAL PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL UNIQUE,
    execute_after TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'READY'
        CHECK (state IN ('READY', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    claim_version BIGINT NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_scheduled_work_claim
    ON scheduled_work (execute_after, id)
    WHERE state IN ('READY', 'RUNNING');
~~~

Claiming up to 20 rows via `NamedParameterJdbcTemplate` (`:workerId` is a named parameter bound by Spring):

~~~sql
WITH candidates AS (
    SELECT id
      FROM scheduled_work
     WHERE execute_after <= CURRENT_TIMESTAMP
       AND (
            state = 'READY'
            OR (state = 'RUNNING' AND lease_until < CURRENT_TIMESTAMP)
       )
     ORDER BY execute_after, id
     FOR UPDATE SKIP LOCKED
     LIMIT 20
)
UPDATE scheduled_work AS w
   SET state = 'RUNNING',
       lease_owner = :workerId,
       lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
       claim_version = w.claim_version + 1,
       attempts = w.attempts + 1
  FROM candidates AS c
 WHERE w.id = c.id
RETURNING w.id, w.business_key, w.payload, w.claim_version;
~~~

Run this claim in a short transaction and **commit before calling external systems**. `SKIP LOCKED` keeps workers from stalling behind rows already locked by another worker; it does not replace global concurrency limits or priority rules. Because PostgreSQL executes `UPDATE ... RETURNING` atomically with row locks, two workers never claim the same row concurrently. Once `lease_until` expires, stale `RUNNING` jobs become reclaimable.

Upon completion, a worker may mark success only if it still owns the claim:

~~~sql
UPDATE scheduled_work
   SET state = 'SUCCEEDED',
       lease_owner = NULL,
       lease_until = NULL
 WHERE id = :id
   AND state = 'RUNNING'
   AND lease_owner = :workerId
   AND claim_version = :claimVersion
   AND lease_until > CURRENT_TIMESTAMP;
~~~

If **0** rows update, the lease expired or another worker claimed a newer generation; the stale worker must not overwrite job state. `claim_version` acts as an **in-database fencing token** for completion writes. It protects SQL writes only: if a stale worker calls an HTTP endpoint unaware of the token or idempotency key, the DB cannot undo that external call.

### 7.2. Leases, heartbeats, and retries

- Compute `lease_until` using the **database clock**, never pod clocks that can drift.
- For long jobs, renew leases periodically via `UPDATE ... WHERE id/owner/version` and abort if renewal fails. Never let an evicted worker keep writing shared state.
- On error, update `attempts`, `last_error` (if in schema), and `execute_after` for backoff retries. Past max attempts, transition to `FAILED` for operator handling.
- Add **reconciliation/catch-up** to generate missing slots (e.g., "dates lacking a report job") rather than waiting for the next cron and skipping past days.
- Enforce explicit state transitions: `READY → RUNNING → SUCCEEDED`, `RUNNING → READY` on retry, and `RUNNING → FAILED` past thresholds; guard every transition conditionally.

In production, add history tables/indexes, manage table bloat, and monitor lock contention. For heavy job volumes or rich calendars, prefer dedicated scheduler/queue platforms over hand-rolling a full state machine.

## 8. What distributed locks do—and do not—solve

With libraries like ShedLock or a shared DB/Redis lock, every replica still fires its `@Scheduled` callback, yet only the lock holder runs the guarded block.

~~~mermaid
sequenceDiagram
    participant A as Replica A
    participant B as Replica B
    participant L as Shared lock store
    participant E as External API
    A->>L: Try acquire job:reconcile
    B->>L: Try acquire job:reconcile
    L-->>A: Acquired
    L-->>B: Rejected
    A->>E: Run reconciliation
    A->>L: Release lock
~~~

Design decisions when using locks:

- **Lock store:** DB/Redis must be shared across all instances. In-memory locks do nothing across pods.
- **TTL/lease:** too short lets an active job lose its lock to another worker; too long delays recovery after a crash.
- **Ownership:** releasing or extending locks must verify the current owner/token so an old worker cannot delete another worker's newer lock. In Redis, check-and-delete must be atomic.
- **Missed runs:** locks only arbitrate among awake instances; they never recreate missed slots when zero instances were up.
- **Not exactly-once:** even with one active lock holder, HTTP/Kafka may succeed right before the worker crashes prior to recording completion; retries still require idempotency.

For per-slot once-only jobs, **unique business-key constraints + durable execution state** are usually easier to audit than ephemeral locks leaving no history. Conversely, for per-replica local cache refreshes, no distributed lock is needed—each replica refreshes its own cache.

## 9. When to move to Quartz, Kubernetes CronJob, or queues?

### Quartz with clustered JDBC JobStore

Quartz fits dynamic schedules requiring persistence, multiple triggers, misfire handling, and clustered execution across Quartz nodes. Scheduler instances must share **the same Quartz JDBC JobStore tables** with compatible cluster config and unique instance IDs. Separate tables mean zero clustering.

Even in clustered Quartz, monitor DB availability, cluster check-in intervals, misfire policies, and job idempotency. `@DisallowConcurrentExecution` on a Quartz `JobDetail` prevents overlapping runs of that job per Quartz rules, yet never makes external HTTP calls a distributed transaction.

### Kubernetes CronJob

A CronJob periodically spawns a **Kubernetes Job**, creating a Pod that runs and exits—isolating batch jobs from HTTP API replicas:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-order-reconciliation
spec:
  schedule: "0 2 * * *"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 300
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: reconciliation
              image: registry.example.com/integration-worker:1.0.0
              args: ["--job", "reconcile-orders"]
~~~

`concurrencyPolicy: Forbid` prevents overlapping **Jobs belonging to that CronJob**, yet does not coordinate separate CronJobs, stop all forms of duplicate starts, or guarantee every tick runs once. `startingDeadlineSeconds` governs whether late runs still start; tune it to catch-up and skip rules.

`timeZone` requires a supporting Kubernetes version. Also bound resources, job history limits, active deadlines, timeouts, and failed-Job alerts. Pass business slots deterministically or let workers detect missing slots from persistent state.

### Queues / brokers for async tasks

A scheduler can **persist work** in the DB and publish signals to Kafka/RabbitMQ for many consumers to process—useful when each tick spawns thousands of small tasks. Producers must assign exact **business keys** per item; consumers use idempotency keys to handle replays, crash retries, and rebalances.

Writing job state in a DB and publishing to a broker reintroduces the **dual-commit boundary**. Use a transactional outbox or reconciliation: save job/outbox in one DB transaction, then relay to the broker. Kafka transactions coordinate **within Kafka**, never across PostgreSQL commits, partner HTTP APIs, or caches.

## 10. Deduplication and integration data design

Schedule locks are only the first defense. At the business layer, make operations safe to repeat:

| Task | Appropriate idempotency | Key caveat |
|---|---|---|
| Daily report generation | Unique `(report_type, report_date)`, conditional upsert | Avoid generating duplicate files/emails on retries unless intended |
| HTTP data sync | Stable `requestId` or partner version/ETag | Timeouts do not prove partner didn't process |
| Payment / reconciliation | Transaction idempotency key + status inquiry API | Never mint a new key when retrying the same intent |
| Shared cache update | Conditional version/timestamp write + appropriate TTL | Repeated refreshes may be fine if pure and cheap |
| Kafka event emission | Constant `eventId`, outbox + consumer dedup | Marking sent after broker ACK still leaves a duplicate window |
| DB updates from messages | `processed_events` table with unique key in same DB tx | Commit offset only after business state commits |

Example PostgreSQL upsert:

~~~sql
INSERT INTO daily_reconciliation(day_key, outcome, updated_at)
VALUES (:dayKey, :outcome, CURRENT_TIMESTAMP)
ON CONFLICT (day_key) DO UPDATE
   SET outcome = EXCLUDED.outcome,
       updated_at = EXCLUDED.updated_at;
~~~

Upserts prevent **duplicate rows**, yet you must also guard **ordering and versions**: an old retry must never overwrite a newer result. For time-evolving data, guard updates with monotonic versions or source `updated_at` comparisons rather than unconditional upserts.

A `requestId` or `jobId` must remain constant across every retry of **the same logical task**. Generating a fresh UUID per retry provides zero real idempotency.

## 11. Which local tasks can safely run on every replica?

Not every local schedule is a bug:

- Refreshing **in-memory local caches** or per-instance read-only configuration.
- Purging local buffers, JVM-scoped stats, or per-JVM lifecycle objects.
- Periodic local health checks or snapshots intended per replica.

Conversely, bulk emails, inventory deductions, invoicing, outbox publishing, shared report generation, and shared DB mutations usually require cluster coordination, idempotency, and crash recovery.

Practical rule of thumb: **"If 10 replicas invoke this callback simultaneously, what mutates 10 times?"** If the answer is shared business state or a partner system, redesign the execution boundary.

## 12. Observing and operating schedules in production

For integration tasks, logging "Scheduler started" says nothing about outcomes. Track **planned slots**, **claimed slots**, and **completed side effects**.

Key signals:

- **Triggers:** `job_name`, `slot_key`, planned time, actual execution time, `instance_id`, `correlation_id`.
- **Coordination:** claim successes/failures, lock wait time, active leases, reclaimed jobs, owner/fencing rejections.
- **Execution:** duration, business errors, retries, HTTP timeouts, processed record counts, Kafka published/ACKed counts.
- **Backlogs:** `READY` counts, expired `RUNNING` counts, `FAILED` counts, oldest job age, uncreated downtime slots.
- **Dependencies:** DB connections, partner HTTP 429/5xx rates, broker latency, consumer lag, outbox backlog.

For example, alert if **yesterday's reconciliation slot is not `SUCCEEDED` by 03:00 UTC**, rather than alerting only on JVM exceptions. If metrics show expired `RUNNING` leases, verify whether workers died or merely stalled before bulk-retrying.

During rolling updates, use graceful shutdown: stop taking new work, let active tasks finish within limits, or leave retryable states. Align Kubernetes `terminationGracePeriodSeconds` and app timeouts with tasks that can exit cleanly; never assume HTTP/Kafka requests abort cleanly with zero side effects.

## 13. Testing multi-replica behavior

Run **at least two application contexts/processes** or two real workers against the same PostgreSQL instance (e.g., Testcontainers), rather than invoking a scheduler method directly in unit tests. Control clocks and slots so tests never depend on wall-clock time.

| Test | Setup | Expectation |
|---|---|---|
| Two replicas on same slot | Race to claim `(job_name, slot_key)` concurrently | Only one `INSERT` succeeds; never triggers twice from claim branch |
| Distinct business keys | Submit two different slots/dates | Valid independent jobs do not block each other |
| Crash after claim | Kill worker before updating outcome | `RUNNING`/expired lease exists; recovery kicks in per policy |
| Crash after side effect | Partner receives call; worker dies before ACK | Retry reuses same idempotency key with zero duplicate effect |
| Missed schedule during downtime | Stop all instances across cron hour | Catch-up creates/processes missed slots |
| Lease expires while A is slow | Worker B claims new generation | A cannot overwrite B's state; downstream handles duplicates safely |
| Rolling deployment | Run versions A and B concurrently | No conflicting duplicate results for the same slot; contract-compatible |
| HTTP/Kafka failures | Inject timeouts/429/5xx then recover | Bounded retry/backoff, accurate logs/metrics, zero lost work |
| Multiple queues/partitions | Multiple workers pull jobs | Idempotency prevents duplicates; throughput meets target |
| Time-zone schedules | Test midnight rollovers and DST | Slot business keys stay consistent in chosen time zone |

For the PostgreSQL sample in section 6, also test **stuck `RUNNING` rows**, since testing only "two replicas, one insert" creates a false sense of exactly-once safety. For section 7's lease pattern, test a stale worker completing after losing ownership.

## 14. Design checklist

Before shipping a `@Scheduled` task in a multi-replica Spring Boot app, decide:

1. Should the task run **per replica** or produce one shared cluster outcome?
2. What is the slot's business key, which time zone computes it, and does it stay constant across retries?
3. If every instance is down at cron time, what recreates the missed slot?
4. When two replicas trigger simultaneously, what claim mechanism grants execution rights?
5. If a worker dies after an external side effect, does the target have idempotency keys or status lookup?
6. How are TTL/leases, heartbeats, fencing, and retry/backoff designed?
7. Across DB + Kafka/HTTP, what prevents lost intents and handles duplicate deliveries?
8. Do metrics/alerts track **actually completed slots** rather than just scheduler wake-ups?
9. Have you tested multi-instance races, crashes, rolling updates, downtime, and timeouts?

**Conclusion:** `@Scheduled` provides a **per-JVM** clock, not a distributed scheduler. When Spring Boot Integration scales to multiple replicas, anchor schedules to durable work state, coordinate execution ownership, and enforce idempotency across database, HTTP, cache, and broker boundaries. Atomic claiming prevents duplicate starts in simple cases; reliable failure handling and completion also demand retries, catch-up, leases/fencing, or a dedicated scheduler/queue.

### References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, `@Async`, schedulers, and executors.
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): configuring task scheduling and thread pools.
- [Quartz Scheduler — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/): JDBC JobStore and clustering.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): schedules, time zones, `concurrencyPolicy`, deadlines, and scheduling limitations.
- [PostgreSQL — SELECT / Locking Clause](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` and row-locking behavior.
