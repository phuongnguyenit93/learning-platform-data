# Backfilling Large Datasets Without Overloading the Main Service

In **SPRING_BOOT_INTEGRATION**, Spring Boot commonly links HTTP clients, databases, caches, message brokers, and Spring Integration adapters into a continuous data pipeline. When you need to **backfill** millions of missing records or rebuild a query projection table, the recovery flow must run while users still call APIs and consumers still process live data. Without controls, a seemingly simple scan-and-update loop can exhaust connection pools, build broker backlogs, spike p99 latency, cause replication lag, and render the main service unresponsive.

This lesson focuses on **controlled, large-scale backfill operations**: defining exact scope, budgeting resources, chunking work, rate limiting, checkpointing, deduplicating, coordinating with live traffic, monitoring, and pausing automatically under load. Examples use **Spring Boot + PostgreSQL** as the foundation, extending to HTTP clients, caches, RabbitMQ/Kafka, and Spring Batch.

## 1. Context: Rebuilding an Order Lookup Table

Suppose the system has an **orders** table with 30 million orders. The API queries **order_projection** to return order statuses quickly. A deployment bug skipped projection updates for three days. To repair it, operations must re-scan roughly **8 million orders** and restore the projection.

Meanwhile:

- The API serves real users under latency and error-rate SLAs.
- The **live** flow keeps receiving `OrderCreated`, `OrderPaid`, and `OrderShipped` from the broker.
- The PostgreSQL primary serves active order creation and update transactions.
- Read replicas, brokers, Redis, and HTTP partners each have their own limits.
- Underlying data keeps changing; the backfill may read an older version after live traffic already wrote a newer one.

A naive **"SELECT everything then UPDATE every row as fast as possible"** job might finish the backfill sooner while destabilizing production. The right goal is **completing recovery within an allowed load budget**, with pause, resume, retry, and reconciliation support.

~~~mermaid
flowchart LR
    SOURCE[("Orders source / read replica")] --> READER["Small-page backfill reader"]
    READER --> LIMIT["Rate limit + concurrency limit"]
    LIMIT --> APPLY["Idempotent projection writer"]
    LIVE["Live events"] --> APPLY
    APPLY --> TARGET[("Order projection DB")]
    CTRL[("Backfill run + task + checkpoint")] <--> READER
    METRICS["DB p95, pool wait, replica lag, API errors"] --> ADAPT["Controller: scale up / throttle / pause"]
    ADAPT --> LIMIT
    TARGET --> API["Production API"]
~~~

**Key takeaway:** a backfill is usually **deferrable workload**, whereas user transactions and live event processing hold higher priority. Throttling mechanisms must protect **the actual resources shared** between both flows.

## 2. How Backfill Differs from Replay and Live Processing

| Flow | Data Read | Purpose | Operational Characteristics |
| --- | --- | --- | --- |
| **Live ingestion** | New events, live requests | Maintain near-real-time state | Prioritizes latency and stability |
| **Retry/redelivery** | Unconfirmed message or operation | Resolve uncertain outcomes | Preserves identity/idempotency keys |
| **Replay** | Historical events stored in log/archive | Re-run logic or rebuild projection | Requires retention, offsets, duplicate-effect protection |
| **Backfill** | Missing data or a historical range from DB/API/files | Fill gaps or regenerate data | High volume; requires load limits and reconciliation |
| **Reconciliation** | Two states treated as source and target | Detect/fix discrepancies | Determines whether recovery is truly complete |

A backfill can **use replay techniques** if the source is an event archive, though not every broker keeps enough history. Standard RabbitMQ queues cannot re-read acked/deleted messages; Kafka supports re-reading within log retention; RabbitMQ Streams offer their own offset/retention controls. Never assume you can backfill from every queue without an actual historical store.

A missing row in the projection does not become a brand-new order when backfilled. **`eventTime`/`sourceVersion`** reflects source-system timing and sequence; **`ingestedAt`/`backfillRunId`** reflects recovery timing. Keep them separate so revenue reports or customer notifications do not fire for past periods.

## 3. First Define Data Boundaries and Completeness Proof

Before computing throughput, know exactly **what to read**. A backfill lacking stable scope easily loops indefinitely or misses records at boundaries.

### 3.1. Identify the Source of Truth

For a projection table, the source of truth may be:

1. **The current orders table:** sufficient if only final state is needed and the source table retains every field required to reconstruct it.
2. **An event archive / CDC log:** required when projections accumulate across historical transitions, such as ledgers or event-derived totals.
3. **A partner API with snapshot/cursor support:** used when you do not own the source database.
4. **Immutable snapshot files:** helpful for offline backfills or versioned reloads.

If business logic needs cumulative history, a **latest-state snapshot** usually cannot recover intermediate transactions. Never apply a latest-state upsert rule to financial ledgers, reward points, or payment commands.

### 3.2. Lock Scope and Cutoff

For **append-only** tables with monotonically increasing numeric keys, capture a **high-watermark ID** (e.g., **id <= H**) and scan via keyset pagination. Newer rows with ID > H belong to live traffic or a later run. However, **H bounds inserted rows only**; it does not freeze updates or deletes on older rows.

For **mutable tables**, pick one of these strategies:

- Consistent snapshot at watermark W, then apply CDC/log changes **after W**.
- Source API supporting a **snapshot token/cursor** guaranteeing a stable view throughout reading.
- Records carrying **`sourceVersion`/revision** paired with conditional updates, reconciliation, and tombstones.
- Without those guarantees, document limitations explicitly, scan with overlap windows, and reconcile deltas afterward.

Using `updatedAt <= now()` or offset pagination on a continuously mutating table does not yield a consistent snapshot. Rows updated mid-scan can jump pages, get skipped, or be read twice.

### 3.3. Design Completion Criteria Up Front

Never define completion simply as "workers read every page." For example, a backfill meets acceptance criteria when:

- Source keys within the cutoff range have full representation at the target.
- Target records match source versions/states at the chosen watermark.
- Zero unexplained gaps, data conflicts, or quarantined records remain above allowed thresholds.
- The backfill caused zero production SLA breaches, duplicate side effects, or resource-limit failures.
- Reconciliation results, timings, and run configurations are saved for audit.

## 4. Budget Resources Before Starting the Job

A large backfill simultaneously touches CPU, RAM, network, disk I/O, DB connections, HTTP connections, broker partitions, Redis ops, and data locks. Capping **worker thread count** alone is useless if each thread sends huge SQL batches.

### 4.1. Prioritize the Live Flow's Budget

Measure baselines during peak and low-traffic windows:

| Resource | Baseline to Watch | Sign Backfill Is Causing Harm |
| --- | --- | --- |
| API/service | RPS, error rate, p95/p99 latency, request queues | p95/p99 climbs, timeouts, 429/503 |
| PostgreSQL primary | CPU, IOPS, WAL, lock waits, active sessions, replication lag | Live transactions slow, checkpoints/WAL spike |
| Read replica | CPU/I/O, replica lag, query duration | Replica serves stale reads or falls behind primary |
| Connection pool | active, idle, pending acquire, timeouts | Threads wait on pool; live requests fail |
| Broker | queue depth, oldest message age, lag, redelivery | Live consumers starved of resources |
| Partner HTTP | quota, 429/5xx, p95 latency | Rate limits hit, circuit breakers open |
| Redis/cache | latency, CPU, evictions, throughput | Hot keys evicted, API falls back to DB |

Define **stop thresholds** from production SLOs. Illustrative example: run only while API p95 < 250 ms, DB CPU < 70%, connection pool pending ≈ 0, and replica lag < 5 seconds. These **are not** universal defaults; determine real numbers from load testing and service targets.

### 4.2. Translate Downstream Quota into Backfill Rate

Suppose a partner API has a quota of **120 HTTP requests/second**, peak live traffic uses 85 requests/second, and 15 requests/second are reserved for bursts. Maximum backfill budget:

\[
Q_{\mathrm{backfill}} \le 120 - 85 - 15 = 20\ \text{requests/second}
\]

Start **well below the calculated limit**—such as 5 requests/second—and ramp up from observed telemetry. API quota is only **one** bottleneck. If I/O pressure limits the DB to 10 records/second extra, then **10 records/second** (normalized to work units) is the governing limit.

Never assume a fixed "1 item = 1 SQL statement." One item may trigger 1 read + multiple updates + cache invalidations + outbox writes. Measure **resource cost per thousand items** at various throughputs and recalculate whenever schemas or indexes change.

### 4.3. Duration Estimates Are Not Promises

With **8 million records** at a sustained **40 records/second**, pure processing time is:

\[
\frac{8,000,000}{40} = 200,000\ \text{seconds} \approx 55.6\ \text{hours}
\]

This is a **hypothetical baseline** before pauses, retries, reconciliation, and live traffic shifts. If meeting a deadline requires exceeding safe headroom, change the architecture: export snapshots to object storage, optimize SQL, build a new table in batches, or schedule maintenance windows. Never crank up concurrency unboundedly to force speed.

## 5. Isolate Resources So Backfill Cannot Starve Production

### 5.1. Separate Backfill Workers from the API

Prefer a dedicated backfill process/deployment—such as a Spring Boot worker profile—instead of running an 8-million-row scan loop inside HTTP request threads. A separate deployment lets you:

- Set explicit **CPU/memory requests and limits**.
- Use **separate connection pools** for read replicas and target DBs.
- Cap **worker replica count**, never autoscaling solely on backlog without checking DB headroom.
- Isolate thread pools, queues, and retry policies.
- Pause/stop the entire backfill without restarting the API.

Even in separate processes, **primary databases, networks, and brokers remain shared resources**. Deployment isolation works only when paired with quotas, pool bounds, and rate limits.

### 5.2. Read from Replicas or Snapshots Where Appropriate

For heavy read workloads, a **read replica** or analytical snapshot offloads scanning from the primary. Remember:

- Replicas still share storage/network I/O in some topologies and can add load.
- Replicas carry **lag**, so reads may trail already-processed live events.
- Long queries on replicas can conflict with WAL replay or vacuum depending on DB settings.
- Backfill reads must align with the chosen watermark/snapshot.
- Projection writes may still hit the primary; moving reads to a replica **does not relieve write load**.

For massive rebuilds, exporting partitioned snapshots to object storage or building the projection on a separate database/cluster before a **controlled cutover** often beats issuing millions of production upserts.

### 5.3. Priority Controls and Emergency Stop Switches

Jobs need a periodically checked **pause flag / kill switch**, along with **max concurrency**, **max rows/requests per second**, timeouts, and error thresholds. When a guardrail trips, stop **claiming new tasks**, finish or roll back the active chunk per policy, and persist checkpoints. Avoid killing processes mid-large-transaction whenever possible.

## 6. Reading Large Datasets via Keyset Pagination and Small Chunks

### 6.1. Avoid Large `OFFSET` Queries

Queries like this degrade severely at high offsets:

~~~sql
SELECT id, state, source_version
FROM orders
ORDER BY id
LIMIT 500 OFFSET 7000000;
~~~

The database scans and discards millions of rows before returning the page; under concurrent inserts/deletes, offset pages also shift, skipping or duplicating rows.

When **id** is an indexed monotonically increasing integer, use **keyset pagination**:

~~~sql
-- :lastId starts right before the range's first key.
-- :rangeEnd is the FIXED upper bound of the task.
SELECT id, state, source_version, updated_at
FROM orders
WHERE id > :lastId
  AND id <= :rangeEnd
ORDER BY id
LIMIT :pageSize;
~~~

Once a page is durably processed, advance **`lastId` = last row's id**. This serves as a **read cursor**—not proof every side effect succeeded if target writes and checkpoints use separate transaction managers.

**Keyset limitation:** an indexed `id` solves pagination cost, not snapshot isolation. If the source permits updates/deletes on IDs below the cursor, handle those via `sourceVersion`, CDC, or reconciliation. For composite keys, define a complete, immutable sort key.

### 6.2. Partition Work into Bounded-Range Tasks

Instead of one worker scanning the whole table, split the keyspace into **tasks**:

~~~text
Run R-20261121 / high-watermark H = 30,000,000
  Task 001: id 1         ..  100,000
  Task 002: id 100,001   ..  200,000
  ...
  Task 300: id 29,900,001 .. 30,000,000

Each task uses pageSize=300, commits per page/chunk,
tracks lastId, and holds a lease to resume if a worker dies.
~~~

100,000 IDs/task and 300 items/page are illustrative only; sparse IDs mean some ranges hold fewer rows. Dividing strictly by **ID range** does not equalize row counts across tasks. For partitioned or skewed multi-tenant tables, shard by **partition/date/tenant** using histograms to balance work. Always cap reading at the run's high-watermark.

### 6.3. Indexes and Query Plans Matter More Than Worker Count

Build or select indexes matching filters, sort keys, and partitions. Example:

~~~sql
-- If backfill scans rows filtered by source_system and id:
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_source_id_idx
    ON orders (source_system, id);

-- Illustrative query using this index:
SELECT id, state, source_version, updated_at
FROM orders
WHERE source_system = :source
  AND id > :lastId
  AND id <= :rangeEnd
ORDER BY id
LIMIT :pageSize;
~~~

**`CREATE INDEX CONCURRENTLY`** is PostgreSQL syntax requiring careful planning for disk space and I/O; never add production primary indexes casually for one-off jobs. Evaluate existing indexes first and inspect query plans on representative data. Run **`EXPLAIN ANALYZE`** cautiously since it executes the query.

## 7. Persisting Runs, Tasks, Leases, and Checkpoints for Pause/Resume

A well-operated backfill stores **durable coordination state** instead of relying on in-RAM counters.

### 7.1. Illustrative Coordination Tables on PostgreSQL

~~~sql
CREATE TABLE backfill_run (
    id                  uuid PRIMARY KEY,
    kind                varchar(80) NOT NULL,
    source_system       varchar(80) NOT NULL,
    scope_description   text NOT NULL,
    high_watermark      bigint,
    state               varchar(16) NOT NULL,
    page_size           integer NOT NULL,
    requested_rate      integer NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    finished_at         timestamptz,
    CHECK (state IN ('PLANNED', 'RUNNING', 'PAUSED', 'FAILED', 'COMPLETED')),
    CHECK (page_size > 0 AND requested_rate > 0)
);

CREATE TABLE backfill_task (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          uuid NOT NULL REFERENCES backfill_run(id),
    range_start     bigint NOT NULL,
    range_end       bigint NOT NULL,
    last_id         bigint NOT NULL,  -- initialized to range_start - 1
    state           varchar(16) NOT NULL DEFAULT 'PENDING',
    lease_token     uuid,
    lease_until     timestamptz,
    attempts        integer NOT NULL DEFAULT 0,
    available_at    timestamptz NOT NULL DEFAULT now(),
    last_error_code varchar(80),
    CHECK (range_start > 0 AND range_end >= range_start),
    CHECK (last_id >= range_start - 1 AND last_id <= range_end),
    CHECK (state IN ('PENDING', 'RUNNING', 'DONE', 'FAILED'))
);

CREATE INDEX backfill_task_ready_idx
    ON backfill_task (available_at, id)
    WHERE state = 'PENDING';
~~~

Never treat **`backfill_run`** as the business source of truth; it tracks only operational coordination. Task tables can sit in a separate coordination schema/DB, though committing checkpoints **atomically with projection writes** requires both to share one transaction. Otherwise, accept at-least-once semantics and build an idempotent writer.

### 7.2. Claiming a Task via Lease

With multiple worker replicas, use a short transaction with **`FOR UPDATE SKIP LOCKED`** so two workers never claim the same task simultaneously:

~~~sql
-- Run inside a SHORT transaction on the coordination DB.
-- :leaseToken is a fresh UUID generated per claim.
WITH picked AS (
    SELECT t.id
    FROM backfill_task AS t
    JOIN backfill_run AS r ON r.id = t.run_id
    WHERE r.state = 'RUNNING'
      AND (
        (t.state = 'PENDING' AND t.available_at <= now())
        OR (t.state = 'RUNNING' AND t.lease_until < now())
      )
    ORDER BY t.id
    FOR UPDATE OF t SKIP LOCKED
    LIMIT 1
)
UPDATE backfill_task AS t
SET state = 'RUNNING',
    lease_token = :leaseToken,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE t.id = picked.id
RETURNING t.id, t.run_id, t.range_start, t.range_end,
          t.last_id, t.lease_token;
~~~

**Commit the claim transaction** before reading sources or calling HTTP. Never hold DB row locks while waiting on hundreds of HTTP responses or scanning millions of rows. Keep leases long enough—or **renew conditionally by `lease_token`**—so expired `RUNNING` tasks reclaim cleanly if a worker dies.

**Leases reduce concurrent contention; they do not guarantee exactly-once.** An old worker may resume executing after its lease expires and another worker reclaims the task. Every checkpoint update and target write must validate **`lease_token`** and keep writers idempotent. Across separate source/target transactions, crash retries can reprocess a page.

## 8. Idempotent Writers and Commit-Boundary Checkpoints

### 8.1. Version-Guarded Projections

Suppose each source order carries a monotonically increasing **`source_version`** per `orderId`, and the projection stores the **latest state**:

~~~sql
CREATE TABLE order_projection (
    source_system         varchar(80) NOT NULL,
    order_id              bigint NOT NULL,
    source_version        bigint NOT NULL,
    state                 varchar(40) NOT NULL,
    state_updated_at      timestamptz NOT NULL,
    rebuilt_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, order_id)
);

-- For the same order, write only if source version is HIGHER.
INSERT INTO order_projection AS p (
    source_system, order_id, source_version, state, state_updated_at
)
VALUES (:source, :orderId, :version, :state, :stateUpdatedAt)
ON CONFLICT (source_system, order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    state = EXCLUDED.state,
    state_updated_at = EXCLUDED.state_updated_at,
    rebuilt_at = now()
WHERE p.source_version < EXCLUDED.source_version;
~~~

With the version guard, a version=11 backfill record never regresses a projection already updated to version=13 by live traffic. If the same version carries differing payloads, run **conflict detection/quarantine** per source contract; version numbers alone do not catch all anomalies. For cumulative datasets like ledgers, use an **append-only ledger keyed by `eventId`/`transactionId`**, never latest-state upserts.

### 8.2. Spring Boot Chunk-Write Example

The example below assumes **`backfill_task`** and **`order_projection`** share the **same PostgreSQL DataSource/transaction manager**. Reading the page from the source completed outside this method's transaction; rows are validated and sorted by ascending `orderId`.

~~~java
public record SourceOrder(
        long id, long sourceVersion,
        String state, Instant stateUpdatedAt) {}

@Service
public class BackfillChunkWriter {
    private final JdbcTemplate jdbc;

    public BackfillChunkWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writePage(
            long taskId, UUID leaseToken,
            String sourceSystem, List<SourceOrder> rows) {

        if (rows.isEmpty()) {
            return; // Worker marks DONE via lease-checked update.
        }

        for (SourceOrder order : rows) {
            jdbc.update("""
                    INSERT INTO order_projection AS p
                        (source_system, order_id, source_version,
                         state, state_updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (source_system, order_id)
                    DO UPDATE SET
                        source_version = EXCLUDED.source_version,
                        state = EXCLUDED.state,
                        state_updated_at = EXCLUDED.state_updated_at,
                        rebuilt_at = now()
                    WHERE p.source_version < EXCLUDED.source_version
                    """,
                    sourceSystem, order.id(), order.sourceVersion(),
                    order.state(), Timestamp.from(order.stateUpdatedAt()));
        }

        long lastId = rows.get(rows.size() - 1).id();
        int checkpointUpdated = jdbc.update("""
                UPDATE backfill_task
                SET last_id = ?, lease_until = now() + interval '60 seconds'
                WHERE id = ?
                  AND lease_token = ?
                  AND state = 'RUNNING'
                  AND lease_until > now()
                  AND last_id < ?
                """, lastId, taskId, leaseToken, lastId);

        if (checkpointUpdated != 1) {
            // Rolls back the entire page, including projection upserts.
            throw new IllegalStateException("Lease or cursor is stale");
        }
    }
}
~~~

**Why update the checkpoint at the end of the transaction?** Committing projection writes and **`last_id`** together lets restarts know exactly what persisted durably. Advancing the checkpoint before writing risks **skipping** data on failure. Committing writes without the checkpoint in the same transaction leaves retries safe as long as writers are idempotent.

Here, **`@Transactional`** must be invoked through the Spring proxy, never via self-invocation inside the same bean. The 60-second lease is illustrative: chunks must finish within the lease or workers must renew cleanly. **Never turn a 60-second transaction into a wrapper around long HTTP calls**; keep chunks short. On lease expiry, throw to roll back—never keep writing with a stale token.

### 8.3. When Coordination and Target Live in Different Databases

When a single DB transaction cannot span both:

1. Read source pages and write to the target using **idempotent upserts / unique keys**.
2. Persist the cursor/checkpoint in the coordination DB only after target writes commit.
3. On crashes between steps, **re-read one page** upon resuming, accepting at-least-once behavior.
4. Reconcile target against source to catch gaps; never infer from a cursor alone that all side effects succeeded.

This is **at-least-once processing** with deduplication. Never expect `@Transactional` on one datasource to behave as a distributed transaction over another datasource, HTTP API, cache, or RabbitMQ.

## 9. Throttling Rate: Concurrency, Throughput, and Load-Adaptive Feedback

Backfills need at least **two independent limits**:

- **Concurrency limit:** max requests, chunks, or transactions running simultaneously.
- **Rate limit:** max work units per second—e.g., HTTP calls/second, rows/second, or bytes/second.

Low concurrency sending gigantic SQL batches still overloads the DB. A low average rate where calls hang for seconds still piles up huge in-flight work. Enforce **both**, plus bounded page/chunk sizes.

### 9.1. Illustrative Worker Configuration

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 2000

# CUSTOM application keys; Spring Boot does not enforce them automatically.
backfill:
  enabled: false
  page-size: 300
  max-in-flight-pages: 2
  max-rows-per-second: 40
  worker-poll-interval: 1000ms
  pause-on-primary-cpu-percent: 75
  pause-on-live-api-p95-ms: 350
  pause-on-replica-lag: 5s
~~~

**`backfill.*`** keys must be read and enforced by custom configuration, limiters, and controllers; YAML alone **does not throttle anything**. Pool size 4 illustrates a small worker, not a universal preset. With multiple worker instances, **total pools and total rates** must be bounded cluster-wide, not just per instance.

### 9.2. Token Buckets, Semaphores, and Cluster Limits

**Semaphores** cap simultaneous operations; **token buckets / rate limiters** pace permits over time. Across multiple replicas, per-pod in-memory limiters can let total traffic exceed shared quotas; partition budgets per replica or use a reliable distributed limiter.

Policy example:

~~~text
Global quota:        40 rows/s
Worker replicas:     2
Per-replica budget:  20 rows/s
Max in-flight pages: 1 per replica
Page size:           300

A 300-row page consumes ~15 seconds of replica budget
or splits into smaller chunks; never burst 300 updates instantly
and sleep 15 seconds if that burst spikes the primary.
~~~

To prevent micro-bursts, keep **chunk sizes small** and pace permits per **measured row/chunk cost**, rather than relying on one-minute averages. If the DB handles 50-row transactions smoothly, start with 50-row chunks paced evenly. For partner HTTP quotas, meter requests/second and cap concurrent pages separately.

### 9.3. Adaptive Throttling Based on Production Health

Static rates cannot adapt as live traffic fluctuates across the day. A simple controller can apply **additive increase, multiplicative decrease (AIMD)**:

~~~text
If all guardrails stay healthy across multiple windows:
    targetRate = min(maxRate, targetRate + 2 rows/s)

If API p95 breaches threshold or DB pool waits rise:
    targetRate = max(minRate, floor(targetRate * 0.5))

If live error rate, replica lag, or DB lock waits hit critical levels:
    PAUSE claiming new tasks

RESUME only after recovery stabilizes
and operators/automation authorize per policy.
~~~

This is an **illustrative algorithm**, not a built-in Spring Batch API. Add smoothing, hysteresis, and sensible evaluation windows to avoid rate oscillation. Measure signals close to the target resource; for instance, API p95 might rise for unrelated reasons, so diagnose carefully while still prioritizing production safety.

### 9.4. Retries Must Respect Quotas

HTTP 429, 503, DB deadlocks, or broker outages can be transient. Retries must:

- Have **bounded attempts**, **exponential backoff**, and **jitter**.
- Count retry traffic inside the rate quota—never retry "outside the limiter."
- Honor **`Retry-After`** when supplied by partners and permitted by contract.
- Route permanent failures (invalid schemas, malformed rows) to quarantine instead of retrying forever.
- Prevent one perpetually failing task from monopolizing all worker slots.

Adding threads or replicas to a failing backfill to "catch up" usually amplifies the outage.

## 10. Protecting Databases, HTTP Clients, Brokers, and Caches

### 10.1. PostgreSQL: Short Transactions and Indexed Queries

Best practices:

- Keep chunks small and transactions short; never hold row locks across HTTP calls.
- Use **bulk inserts/upserts** where appropriate, tuning batch size against actual latency, WAL volume, and lock waits.
- Ensure indexes support keyset queries and idempotency unique keys.
- Set **`statement_timeout`** and **`lock_timeout`** on worker connections so a stalled query cannot hold resources indefinitely.
- Monitor **autovacuum, WAL generation, replication lag, disk space, connection counts**, and primary query impact.
- Consider partitioning or building a fresh table before cutover when rewriting most of a production table.

Never wrap millions of rows in a single transaction. Holding long-lived snapshots blocks vacuum, worsens bloat, and complicates failure recovery.

### 10.2. HTTP: Balancing Partner Quotas and Connection Pools

When the backfill source is an HTTP API:

- Use partner cursors/keysets/snapshot tokens; persist cursors **only after durable page processing**.
- Configure dedicated connect/read/response timeouts, connection pools, and max concurrency for workers.
- Bound cluster-wide request rates; keep retries from spiking load.
- Verify pagination consistency, snapshot expiry, deletes/updates, and schema versions.
- If the partner offers bulk exports, consider downloading one archive to object storage and reading locally instead of firing millions of tiny API calls.

If live services and backfills share the same API quota, **reserve headroom for live traffic**. Even an isolated worker deployment can trigger 429s against customer requests.

### 10.3. RabbitMQ/Kafka: Do Not Crowd Out Live Queues

If the backfill emits messages:

- Consider **separate queues/topics** and dedicated consumer pools so backfills never flood high-priority queues.
- Cap publisher rates and **unconfirmed in-flight messages**; watch queue depth, oldest message age, and consumer lag.
- For RabbitMQ, configure publisher confirms, returns/mandatory flags, delivery modes, and queue limits; confirm timeouts do not prove publish failure, requiring idempotency.
- For Kafka, watch partition/consumer lag, backpressure, producer throughput, retention, and per-key ordering constraints.
- Preserve **source `eventId`s** during replay/backfill; never use new deliveryTags or new offsets as business identities.

When producers update DB and emit messages, use a **Transactional Outbox** to tie emission intent to business commits. On consumers, pair **inbox/idempotent processing with post-commit acks**. Backfills do not make DB and broker atomic under one `@Transactional`.

### 10.4. Redis/Cache: Prevent Stampedes During Mass Refreshes

Never invalidate millions of cache keys simultaneously if subsequent reads stampede the DB. Instead:

- Rebuild in the background and update keys at a rate-limited pace.
- Use versioned cache key namespaces per dataset to cut over atomically when ready.
- Invalidate incrementally, add TTL jitter, and watch hit rates and evictions.
- Never use a Redis dedup cache as sole proof "already processed" if cache eviction could trigger duplicate side effects.

Even seemingly cheap cache refreshes can spike load when miss rates surge across many keys at once.

## 11. What Roles Do Spring Batch and Spring Integration Play?

You do not need to build every coordination primitive from scratch. **Spring Batch** structures backfills cleanly into **Jobs/Steps**, **chunks**, **`JobParameters`**, **`ExecutionContext`**, restarts, and progress tracking. **Spring Integration** connects HTTP/DB/broker/file adapters. Both work well together, though load throttling remains your explicit configuration and operational responsibility.

### 11.1. Spring Batch: `chunk` Does Not Automatically Rate-Limit

Basic Spring Batch 5+ Step configuration example:

~~~java
@Bean
Step rebuildProjectionStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRecord> sourceReader,
        ItemProcessor<OrderRecord, ProjectionRecord> processor,
        ItemWriter<ProjectionRecord> targetWriter) {

    return new StepBuilder("rebuildProjectionStep", jobRepository)
            .<OrderRecord, ProjectionRecord>chunk(100, transactionManager)
            .reader(sourceReader)
            .processor(processor)
            .writer(targetWriter)
            .build();
}
~~~

**`chunk(100)`** defines the commit boundary per item count; it **does not guarantee** 100 items/second. A job can blaze through dozens of chunks per second when source and target respond fast. Add explicit throttling via executor bounds, reader/writer rate limiters, schedulers, or distributed coordinators.

**`JobRepository`/`ExecutionContext`** store technical progress metadata, not **business tables, unique/idempotency keys, or reconciliation state**. If a Step reads one DB and writes another, checkpoints and target writes are not atomic. On restarts, tolerate re-reading items safely.

### 11.2. Spring Integration: Isolating Flows and Throttling Channels

Spring Integration wires **HTTP inbound/outbound gateways, AMQP inbound/outbound adapters, JDBC polling, transformers, routers, filters, and aggregators**. For backfills:

- Separate channels/flows for **recovery traffic** and **live traffic** when load policies differ.
- **`ExecutorChannel`** decouples threads but must attach **bounded executors/queues**.
- **`QueueChannel`** provides buffering, yet unbounded queues hide overload and inflate latency; enforce capacity and overflow policies.
- Pollers need **`fixedDelay`/`fixedRate`, `maxMessagesPerPoll`, bounded task executors**, and health-driven pause controls.
- Across brokers, govern acks, retries, DLQs, and consumer idempotency.

Adding executors or raising **`maxMessagesPerPoll`** does not fix a slow database; it just shifts where backlog accumulates. Measure **per-stage queue depths and latencies** to locate true bottlenecks.

## 12. Handling Stale Backfill Data While Live Writes Continue

Large backfills run for hours or days while live events keep mutating the projection. Three common strategies exist:

| Strategy | Best For | Caveats |
| --- | --- | --- |
| **Live + backfill share writer with version guard** | Latest-state projections with reliable `sourceVersion` | Prevents backward overwrites; unsuitable for strict ordered ledgers/sagas |
| **Snapshot + CDC catch-up + cutover** | Rebuilding most of a table needing a consistent snapshot | Needs source log anchor and catch-up throughput |
| **Buffer live events by key, replay sequentially** | Workflows requiring every transition, e.g., sagas | Needs pending/gap state and backlog caps |

Crucial rules:

- **`eventTime`** is when the business event occurred; **`ingestedAt`** is when the backfill processed it. Never book last year's orders as today's revenue.
- **`sourceVersion`/sequence** governs ordering when upstream guarantees it; never treat **arrival time** as "newer."
- **Deletes/tombstones** need proper versioning so stale snapshots never "resurrect" deleted records.
- **Same version, different payload** must log conflicts and reconcile rather than silently ignoring them.
- For external side effects like payments or emails, never replay blindly; check idempotency keys and target side-effect state.

An **HTTP 200 when a backfill calls an endpoint** does not guarantee downstream systems committed properly. External side effects need dedicated retries, idempotency, verification, and audits.

## 13. Progress Tracking, Observability, and Operational Guardrails

### 13.1. Distinguish Scanning Progress from Actual Recovery

Track separate counters:

| Metric | Meaning |
| --- | --- |
| **scanned** | Candidate rows read by the reader |
| **validated** | Rows passing contract checks |
| **applied** | Mutations actually persisted to target |
| **duplicate/stale** | Rows already present or skipped due to older `sourceVersion` |
| **conflict/rejected** | Conflicting or invalid data requiring reconciliation |
| **retried** | Reprocessing attempts after failures |
| **pending/running/done tasks** | Coordination progress |
| **oldest incomplete task age** | Detects stalled tasks or missing workers |
| **watermark gap** | Verified gap remaining between source and target |

**`scanned = 8 million`** does not mean **`applied = 8 million`**, much less that every order is accurate. When repairing only missing rows or skipping stale/duplicate records validly, `applied` is naturally lower than `scanned`; reconcile by identity and state.

### 13.2. Metrics Protecting Live Traffic

Monitor simultaneously:

- API **RPS, p50/p95/p99**, error rates, saturation/queue waits.
- Primary DB CPU, active connections, pool pending, lock waits, deadlocks, WAL, replication lag.
- Read replica lag, query latency, CPU/I/O; verify data watermark.
- Broker **queue depth/consumer lag**, oldest message age, nacks/timeouts/DLQ.
- Backfill **rows/sec, pages/sec, retries/sec**, worker count, lease expiries, pause durations.
- Cache latency, hit rate, evictions, and DB fallback volume.

In logs/traces, attach **`backfillRunId`, `taskId`, `sourceSystem`, source range, cursor, and attempt**, correlating across HTTP/DB spans. Never place `runId`, `rowId`, or `eventId` in arbitrary Prometheus labels that cause extreme cardinality; keep granular IDs in logs/traces/audits.

### 13.3. An Operations Dashboard Should Answer

1. Is the backfill **reading the right range** without crossing its cutoff?
2. What is the **current rate**, and is it operator-set or throttled by an overload controller?
3. What is the impact on **live latency, errors, and DB lock waits**?
4. Which tasks are pending, retrying, expired on lease, or quarantined?
5. How much has been reconciled, and what gaps remain?
6. Where can we **safely pause/resume** without duplicating data?

## 14. Rollout Process from Dry-Run to Run Closure

### Phase 1: Planning and Dry-Run

Record **`runId`, source, ID/time range, high-watermark/snapshot token, `schemaVersion`, `pageSize`, rate budget, max concurrency, and pause triggers**. Check query plans and resource cost on representative data. Dry-runs can count/sample rows and estimate updates, but **never write business effects** or apply processed markers mistaken for real results.

### Phase 2: Bounded Canary

Run a tiny slice/tenant—say **0.1% of candidates**—at 5 rows/second on one worker. Watch live API p95/p99, connection pools, WAL, replica lag, and projection output. Verify **pause, same-run restart, and deduplication** before expanding.

### Phase 3: Controlled Ramp-Up

Increase rate or workers **one knob at a time** within observed thresholds. Enforce cluster-wide limiters, not just per-replica caps. If live metrics breach guardrails, auto-throttle or pause new claims and record timestamps and reasons.

### Phase 4: Continuous Recovery and Reconciliation

Execute paged tasks, checkpoint post-commit, retry with backoff, and audit failures. Compare target high-watermarks against source to catch gaps, stale rows, conflicts, and deletes. When using CDC catch-up, cut over only after lag meets targets and live behavior is verified.

### Phase 5: Closure—Do Not Rush Cleanup

Mark **`COMPLETED`** only after reconciliation meets criteria, not merely when every task says `DONE`. Retain run/task history, error logs, progress reports, and per-partition checksums/counts for the audit window. Schedule cleanup to keep coordination tables bounded without erasing auditability of past recoveries.

## 15. Failure and Recovery Matrix

| Scenario | Risk if Handled Naively | Proper Handling |
| --- | --- | --- |
| Worker dies after write, before checkpoint | Page re-runs | Idempotent writer, checkpoint post-commit; share transaction if same DB |
| Worker loses lease mid-write | Two workers write same task | Lease token guard; rollback on lost ownership, idempotent upsert |
| Source API 429/503 | Retry storm hurting live traffic | Backoff + jitter, cluster-wide limiter, prioritize live traffic |
| Replica lag climbs | Backfill reads overly stale data | Pause/choose safe watermark; version guard and reconciliation |
| SQL full-table scan | DB CPU/I/O spikes, live latency surges | Keyset/indexes/query plans; shrink chunks and rate |
| WAL/disk fills up | Primary failure, downtime risk | Alert and pause on WAL/disk watermarks; plan storage capacity |
| Connection pool exhausted | Live API waits on connections | Dedicated small worker pool, max concurrency, pool-wait guardrails |
| Backfill v11 arrives after live v13 | Overwrites state backward | Conditional upsert on `sourceVersion` |
| Record deleted at source | Stale snapshot resurrects deleted data | Tombstones/versions/CDC catch-up |
| Historical data triggers emails or payments | Duplicate customer/financial side effects | Domain idempotency + side-effect policy and audits |
| One task fails schema repeatedly | Worker retries forever | Quarantine, max attempts, error codes, manual intervention |
| Broker backlog grows from recovery publishes | Live consumers lag | Separate queues/pools/rates, apply backpressure |
| Run scanned all rows yet projection has gaps | False success report | Independent reconciliation before `COMPLETED` |

## 16. Testing Under Load and Intentional Faults

A thorough test suite verifies both **data correctness** and **protection of production-like traffic**:

1. **Keyset/cursor:** with sparse IDs and large sources, every in-range ID is read accurately without `OFFSET` drift.
2. **Post-commit crash:** kill a worker between write and checkpoint; resume produces zero duplicate business effects.
3. **Lease expiry:** worker A's lease expires, worker B claims; A fails to commit with its stale token.
4. **Live race:** live traffic updates projection v13 while backfill pushes v11/v12; v13 remains intact.
5. **Mutating source:** updates/deletes during backfill; snapshot/CDC/reconciliation capture scope accurately.
6. **Database load:** run alongside peak-like HTTP traffic monitoring p95/p99, connection pools, lock waits, WAL, and replica lag.
7. **HTTP 429/503:** retries use backoff, obey quotas, and avoid storms.
8. **Broker backlog:** backfill emits heavy message volume while live consumers stay within lag bounds.
9. **Pause/resume:** pause mid-run, restart workers, confirm checkpoints/states remain intact.
10. **Multi-worker contention:** concurrent workers claim tasks from DB; each holds valid leases with consistent final data.
11. **Bad data:** quarantine schema errors and same-version payload conflicts rather than hiding behind total counts.
12. **Reconciliation:** intentionally drop a partition; verify system refuses to mark `COMPLETED` until the gap is resolved.

In Spring Boot, test databases with **Testcontainers PostgreSQL**, HTTP partners with **WireMock/MockWebServer**, brokers with matching containers, and load scenarios with dedicated load tools. Performance tests matter only with production-like data sizes, indexes, bandwidth, and connection caps; unit tests on a reader loop never prove production safety.

### Sample Acceptance Criteria

Suppose the goal is backfilling 8 million orders while live events keep flowing:

- Workers can **pause mid-run** and resume from durable checkpoints without skipping committed work.
- Production API stays within agreed error/latency thresholds; if breached, the controller throttles or pauses new tasks.
- Multiple concurrent workers never exceed combined **rate budgets** and allocated connection pools.
- Orders with newer `sourceVersion` are never overwritten backward; duplicate messages produce zero duplicate side effects.
- At run completion, reconciliation against source watermarks/partitions confirms completeness and reports remaining gaps/conflicts clearly.

## 17. Large Backfill Operations Checklist

- [ ] Define **source of truth, scope, cutoff/watermark**, and retention boundaries.
- [ ] Establish **baseline production SLOs**, rate budgets, throttle/pause thresholds, and kill switches.
- [ ] Isolate worker deployments/pools/queues from live traffic where appropriate; bound **both concurrency and throughput**.
- [ ] Use **keyset/partition/snapshot** reads rather than large `OFFSET`s or giant transactions.
- [ ] Verify indexes, small chunks/pages, timeouts, and WAL/replica-lag policies.
- [ ] Persist **runs/tasks/leases/cursors** durably; checkpoint post-commit with idempotent writers.
- [ ] Handle **event identities, `sourceVersion`, tombstones, stale data, and external side effects** cleanly.
- [ ] Implement **retry backoff, jitter, quarantine, and DLQs** without letting retries breach quotas.
- [ ] Monitor **live p95/p99, DB pool waits, broker lag, replica lag, rows/sec**, and pause/resume health.
- [ ] Execute **dry-run → canary → ramp-up → reconciliation → closure**, maintaining audit trails and discrepancy resolution.

**Principle to remember:** Large-scale backfilling is an **operational workload paced by remaining system headroom**, and simultaneously a **data-consistency problem**. Safety comes from **explicit sources and watermarks, controlled paged reads, idempotent writes, durable checkpoints, adaptive rate limits, and reconciliation**. Finishing fast or reporting `COMPLETED` is never enough; results must be accurate and primary user services must remain responsive throughout recovery.
