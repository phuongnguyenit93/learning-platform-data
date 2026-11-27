# Immediate Consistency, Eventual Consistency, and Update Costs

## Learning Objectives

After this lesson, you will be able to:

- Explain **immediate consistency within a transaction boundary** and **eventual consistency** without conflating them with "fast" or "slow" queries.
- Analyze how duplicating counters, totals, or display attributes impacts **the write path**, locks, write amplification, resources, and recoverability.
- Choose a consistency boundary based on **business invariants**, allowed freshness lag, and the authoritative data source.
- Design synchronous updates in PostgreSQL or asynchronous event propagation using a **transactional outbox**, while handling retries, double counting, and out-of-order events.
- Build reconciliation queries, lag metrics, and benchmark suites to verify real costs before denormalizing.
- Compare the same trade-offs across relational, document, graph, and analytical models.

This topic belongs to the **Denormalization** chapter of **DATABASE_DATA_MODELING**. Turning business requirements into entities, relationships, constraints, and physical schemas is complete only when you specify **which data must be accurate at which moment, where authority lives, and what it costs to uphold that commitment**.

## 1. One Counter, Two Different Contracts

Suppose an application has a **Like** button for posts. The source data is the relationship set:

~~~text
post_likes(post_id, user_id)
~~~

Each **(post_id, user_id)** pair has at most one row. The current total likes is the row count per **post_id**.

The post listing page may display **like_count** thousands of times per minute. Rather than running COUNT repeatedly, the design team proposes a pre-stored **post_like_counts(post_id, like_count)** table.

Two feature areas may want two different contracts:

- **The acting user's own flow:** after the API reports "Liked," that user's like must genuinely exist; if the UI returns an updated count, it must not contradict the API's acknowledgment.
- **Public post listings:** can tolerate the counter reflecting changes a few seconds later, provided the number is informational and lag stays bounded.

One implementation updates the relationship and counter **in the same transaction**. Another writes the relationship at the source, emits an event, and **updates the counter later** in a read model. Both can be valid choices, yet their guarantees and costs differ.

Crucially: **post_likes** defines who currently likes a post; **post_like_counts** is derived data. Whenever the copy differs from the source, rules must clarify whether that represents acceptable transient sync lag or a bug needing repair.

## 2. Understanding Both Consistency Models Precisely

### 2.1. Immediate Consistency: Accurate Beyond a Defined Boundary

In this lesson, **immediate consistency** carries the practical meaning:

> Once a write operation **commits successfully** on the database owning both the source and the counter, subsequent queries against **that same database** within an appropriate read scope observe both the relationship and counter reflecting that operation.

For example: a transaction inserts the like relationship and increments the counter. If it commits, both changes become visible together; if it rolls back, neither is published.

This is a **transaction-scoped** guarantee. It **does not automatically mean**:

- A stale cache, a lagging read replica, or another database also sees new data immediately.
- A previously opened snapshot-isolation transaction suddenly changes results mid-flight.
- Every user globally observes identical state at the exact same microsecond.
- Arbitrary pairs of complex reads/writes achieve **linearizability** simply because one table uses transactions.

**Atomicity** (all-or-nothing commit), **isolation** (how concurrent transactions observe one another), and **linearizability** (a strong total-order guarantee across concurrent operations) are distinct concepts. When requirements demand strong guarantees, specify the exact API, read target, isolation level, and time boundary—never substitute the generic word "real-time" for a measurable contract.

In PostgreSQL, fresh queries against the primary under **READ COMMITTED** typically observe committed writes on their next statement snapshot, whereas higher isolation levels, replicas, and caches behave differently. Reason about consistency against your actual read architecture.

### 2.2. Eventual Consistency: Temporarily Divergent, Yet Must Converge

**Eventual consistency** means that if source writes stop and propagation/application keeps operating under design assumptions, replicas **eventually converge** to reflect the source.

Example:

~~~text
T0    User likes post; source commits successfully
T0+1s Event enters queue; counter is still stale
T0+3s Consumer applies delta to counter table
T0+4s Listing page returns the updated count
~~~

Between **T0** and when the copy updates, reading the source and reading the counter can return different results. That is considered **normal** only when within the declared consistency contract.

Eventual consistency **does not automatically guarantee a few-second max lag**. If events are dropped, workers halt permanently, or reconciliation is missing, the copy can stay wrong forever—failing convergence altogether. Concrete timing promises require **freshness SLOs**, replay mechanisms, and monitoring.

### 2.3. Guarantees Users Actually Observe

| User Expectation | What Must Be Designed? | Notes |
| --- | --- | --- |
| Once liking succeeds, "liked" state is accurate immediately | Write source relationship with commit confirmation; read source or derive state from write result | Does not necessarily wait on every public counter |
| Right after clicking Like, the user sees the count increment | Sync update, or optimistic UI with rollback handling, or wait for projection catch-up | Avoid presenting optimistic estimates as source-confirmed counts |
| Other users see updated like counts within tens of seconds | Eventual projection with measured freshness | State thresholds and recovery steps on lag |
| Never oversell committed inventory | Check/reserve/decrement inventory at source within proper consistency boundary | Never authorize decisions from potentially stale cached counters |
| Periodically refreshed revenue reports | Summary table or materialized view with refresh schedule | Needs watermarks, currency rules, and reporting periods |

A system can choose **strong consistency on business-critical write paths** and **eventual consistency on informational read paths**. You do not need one uniform consistency level across every module.

## 3. Define Business Invariants Before Choosing an Update Strategy

For likes, suppose:

- Each user likes a post at most once at any time.
- Unliking means the relationship no longer exists.
- When caught up, the counter equals the row count in **post_likes** for that post.
- Counters are non-negative.
- Retried operations do not increment or decrement a second time.

We can write the invariant:

~~~text
like_count(post_id)
  = COUNT(post_likes WHERE post_likes.post_id = post_id)
~~~

In synchronous mode, the invariant must hold after every committed transaction. In asynchronous mode, the invariant may temporarily lag at read time; instead, define a **maximum lag contract**, watermark tracking, and source-based recomputation.

For payment amounts, shipping addresses, account balances, or inventory stock, invariants are far more sensitive. Never extrapolate from an informational `like_count` to conclude **every counter suits eventual consistency**.

### 3.1. Authoritative Sources Differ by Semantics

- **post_likes** is the authoritative source for current like relationships.
- **post_like_counts** is a rebuildable derived counter.
- **order_items.unit_price_at_confirmation** is the authoritative source for the locked price of a past transaction.
- **catalog_products.current_price** is the authoritative source for current list prices; product-card copies must update when it changes.
- **daily_sales_summary** is derived from transactions under declared grain and formulas.

Locked-in prices must never "sync" to new list prices. The difference between a historical snapshot and a current projection is **semantic**, not merely two lag levels of the same copy.

## 4. Option A: Maintaining Counters Synchronously in PostgreSQL

Minimal schema:

~~~sql
CREATE TABLE posts (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE post_likes (
    post_id BIGINT NOT NULL REFERENCES posts(post_id),
    user_id BIGINT NOT NULL,
    liked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE post_like_counts (
    post_id BIGINT PRIMARY KEY REFERENCES posts(post_id),
    like_count BIGINT NOT NULL DEFAULT 0
        CHECK (like_count >= 0)
);
~~~

This assumes **user_id** is already authenticated and account validity constraints are managed elsewhere. **post_like_counts** may initially lack rows for posts with zero likes; readers must treat missing rows as **0**, or consistently initialize a **0** row for each post.

### 4.1. Increment Exactly Once When Actually Adding a Relationship

Use a single SQL statement with a CTE rather than reading the old count and writing it back:

~~~sql
WITH added AS (
    INSERT INTO post_likes (post_id, user_id)
    VALUES ($1, $2)
    ON CONFLICT (post_id, user_id) DO NOTHING
    RETURNING post_id
)
INSERT INTO post_like_counts AS counters (
    post_id, like_count
)
SELECT post_id, 1
FROM added
ON CONFLICT (post_id)
DO UPDATE SET
    like_count = counters.like_count + EXCLUDED.like_count;
~~~

Assuming the statement executes and commits in PostgreSQL:

1. A new like inserts into **post_likes**; the **added** CTE returns one row and increments the counter by 1.
2. If that user already liked the post, the primary key prevents duplicates; **added** returns zero rows and the counter does not increment.
3. If multiple users like the same post concurrently, **DO UPDATE** adds to the row-locked value rather than overwriting from a pre-read count.
4. If the statement fails and the transaction rolls back, both source and counter roll back together.

This guarantees **once-only effects when inserting the same (post_id, user_id) pair**. It does not cover every application concern: you must still handle transaction failures, permissions, post deletions, bulk imports, and pre-existing counter drift.

**Never write:**

~~~sql
-- Wrong under concurrency if the app read N earlier:
UPDATE post_like_counts
SET like_count = $old_count_plus_one
WHERE post_id = $post_id;
~~~

Two requests can read N simultaneously and both write N+1, losing one increment. Atomic row-level addition prevents **lost updates** in this pattern.

### 4.2. Decrementing on Unlike

Unliking must be symmetric: decrement only when **DELETE** actually removes a relationship.

~~~sql
BEGIN;

DELETE FROM post_likes
WHERE post_id = $1 AND user_id = $2
RETURNING post_id;

-- Execute ONLY when DELETE returned exactly one row:
UPDATE post_like_counts
SET like_count = like_count - 1
WHERE post_id = $1
  AND like_count > 0
RETURNING like_count;

-- If DELETE removed one row yet UPDATE returned zero rows:
-- ROLLBACK and investigate; never commit a divergent state.
COMMIT;
~~~

The SQL snippets above illustrate **the application protocol**, not a self-conditional script. Application code must inspect each statement's returned row count and decide **COMMIT/ROLLBACK** accordingly. When **DELETE** affects zero rows, skip the decrement and return "unliked" per API idempotency.

Test **like → unlike → like again** races for the same user/post, visibility states, lock ordering, and deadlock retries. If any write path bypasses updating the counter, primary keys and CHECK constraints cannot detect COUNT divergence against the source.

### 4.3. Benefits and Costs

**Benefits:** after commit, both tables in the same PostgreSQL instance can be read in transaction-consistent state. No queue or worker is needed to materialize counts.

**Costs:** every like/unlike writes not just one relationship row, but also updates a counter row. Updates generate WAL, touch indexes/row versions, hold locks, and raise write latency. For "viral" posts, massive concurrent updates hit the exact same **post_like_counts** row, creating a **hot row**.

Thus, immediate consistency has no fixed price. It can be cheap at moderate traffic yet fail high throughput when writes concentrate on a single row.

## 5. Option B: Write Source Immediately, Refresh Counter Asynchronously

An alternative architecture:

~~~text
Like API
   |
   v
[Source PostgreSQL]
  post_likes (authoritative source)
  like_event_outbox (written in same transaction)
   |
   | Publisher relays events; may redeliver
   v
[Queue / stream]
   |
   | Consumer with dedup, retry, and monitoring
   v
[Read store]
  post_like_counts (projection)
   |
   v
Listing pages may temporarily observe stale counts
~~~

In this approach, **the API returns success once the like relationship and outbox commit**, not after every counter updates. That is a major contract decision: "user has liked" is immediately true at the source, while the public counter may temporarily lag.

### 5.1. Outbox: Never Commit the Source and Merely Hope Event Sending Succeeds

In the source database:

~~~sql
CREATE TABLE like_event_outbox (
    event_id UUID PRIMARY KEY,
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('LikeAdded', 'LikeRemoved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

When a new like arrives:

~~~sql
WITH added AS (
    INSERT INTO post_likes (post_id, user_id)
    VALUES ($1, $2)
    ON CONFLICT (post_id, user_id) DO NOTHING
    RETURNING post_id, user_id
)
INSERT INTO like_event_outbox (
    event_id, post_id, user_id, event_type
)
SELECT
    $3::UUID,
    post_id,
    user_id,
    'LikeAdded'
FROM added;
~~~

If the pair already exists, **no bogus increment event is emitted**. If a new relationship is added, the event is recorded **atomically alongside the source change** inside one statement.

The publisher polls unpublished rows, dispatches messages, and marks them published. A crash right after sending but before marking **published_at** causes redelivery. That is why consumers must be **idempotent**; an outbox does not magically produce cross-component exactly-once effects.

The **unlike** path must likewise emit **LikeRemoved** only when a row is actually deleted, within the same transaction boundary. Bulk imports, post deletions, restores, or external scripts touching relationships must also emit events or trigger rebuilds.

### 5.2. Consumer Guarding Against Redelivered Events

Suppose the **read store** is also PostgreSQL and maintains:

If the read store is a **separate database**, its **post_like_counts** schema must match the read store's isolation; it cannot carry a direct foreign key referencing **posts** in the source database. The update examples below run inside the projection store, not as a cross-database transaction.

~~~sql
CREATE TABLE applied_like_events (
    event_id UUID PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

For a validated **LikeAdded** event, a single statement records deduplication state and increments the counter in the same read-store transaction:

~~~sql
WITH first_application AS (
    INSERT INTO applied_like_events (event_id)
    VALUES ($1::UUID)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
)
INSERT INTO post_like_counts AS counters (
    post_id, like_count
)
SELECT $2::BIGINT, 1
FROM first_application
ON CONFLICT (post_id)
DO UPDATE SET
    like_count = counters.like_count + EXCLUDED.like_count;
~~~

If the exact same **event_id** is redelivered, **first_application** returns zero rows and the counter is not incremented twice. Deduplication logging and counter increments must commit/roll back together; storing the marker in one store and incrementing in another without coordination still risks partial failure.

This snippet **only illustrates increment events**. When handling **LikeRemoved**, per-user/post ordering matters: if a decrement arrives before its corresponding increment while the counter sits at 0, the non-negative CHECK constraint can reject the update. Options include:

- Preserve processing order per **post_id** in the pipeline when using +/- deltas, alongside retry and late-event handling.
- Emit **absolute state or total count paired with a monotonically increasing source version**, accepting only newer versions.
- Recompute **COUNT** from the source relationship set to repair projections when cost and access allow.
- Shard counters or micro-batch events under a protocol preventing duplicates and gaps.

**Event IDs only prevent reapplying the exact same event; they do not fix lost events, out-of-order events, or two different event IDs representing one business action.** Those guarantees must be designed explicitly.

### 5.3. Eventual Consistency Requires Convergence Conditions and Recovery

If a worker crashes while events remain in the outbox/queue and the consumer restarts cleanly, the copy catches up. If events are lost silently, counters can stay wrong indefinitely.

A practical contract specifies:

- **Authoritative source** and recomputation formula.
- **Transport** supporting retries, replay, or source change capture.
- **Idempotency** and ordering rules.
- **Max freshness or percentile targets** per use case.
- **Periodic reconciliation** and compensating/rebuild procedures.
- **UI behavior** when sync falls behind: show stale data with a timestamp label, hide counts, fall back to source reads, or display an updating indicator.

You cannot claim eventual consistency "guarantees accuracy within 5 seconds" if you cannot measure it or sustain that bound under traffic spikes or component failures.

## 6. Update Costs: Read Benefits Come with Write Obligations

Denormalization typically **trades work at read time for work at write time**. Trade-off map:

~~~text
No stored total:
  READ:  SELECT ... COUNT/SUM/JOIN across many rows
  WRITE: write source relationship or event

Synchronous stored total:
  READ:  read single pre-aggregated row
  WRITE: source + total + index/WAL/locks in transaction

Asynchronous stored total:
  READ:  read projection, potentially stale
  WRITE: source + outbox; consumer updates projection later
  OPS:   queue, retries, lag, dedup, reconciliation, rebuild
~~~

### 6.1. Write Amplification and Fan-Out

**Write amplification** in data modeling is the increase in write work triggered when one source mutation forces updates across copies, indexes, or aggregates.

Examples:

- Adding a like: one relationship row + one counter row if synchronous.
- Renaming a category: potentially updating **hundreds of thousands of products** if copied onto product cards.
- Changing a transaction status: potentially adjusting multiple daily, currency, or status aggregate buckets.
- Changing visibility permissions: hiding or deleting copies across search indexes, caches, and analytics stores.

**Fan-out** measures how many target records are touched by one source change. Even a rare rename creates huge write bursts under high fan-out. Measure both updated row counts and completion time, not merely the byte length of the copied column.

### 6.2. Hot Rows, Lock Contention, and Write Latency

Storing a counter in a single row speeds up reads, yet concurrent transactions incrementing that row must serialize on its lock. Under heavy load, lock wait times spike quickly, and one slow transaction queues up others behind it.

Metrics to measure: **write p95/p99**, lock wait time, deadlocks, retries, throughput, CPU, WAL, I/O, and table/index bloat. Never assume cutting 20 ms off a read query makes the whole system "20 ms faster"—write load and background resource pressure may climb.

Mitigations only work under specific conditions:

- **Keep computing on read** if an indexed COUNT remains fast enough.
- **Batch updates** if the business tolerates lag.
- **Sharded counters** when a single row runs hot: spreads write contention while complicating reads and deduplication.
- **Dedicated projection** for heavy reads across separate stores when staleness is acceptable.
- **Offload aggregations to streaming/analytics** when multi-dimensional scale grows large.

Sharding does not fix double counting; batching does not guarantee freshness; queues do not reduce total compute work. Every option is a measurable trade-off.

### 6.3. Materialized Views and Summary Tables

A daily sales dashboard may choose among:

- **SUM/COUNT at read time:** accurate to the query snapshot, yet scans many rows.
- **Materialized view:** fast reads as of the last REFRESH, though refreshing may rescan large datasets.
- **Transactionally updated incremental summary table:** updates totals with every event, risking hot rows.
- **Event-driven async summary table:** relieves primary OLTP traffic at the cost of lag, late events, reconciliation, and rebuilds.

Summary tables must also define **grain** (e.g., day × currency), timezone, status filters, and refund rules. Without those definitions, updates may stay technically consistent while numbers stay semantically wrong.

## 7. Selection Matrix by Business Risk

| Use Case | Typical Freshness / Consistency Needed | Design Direction to Evaluate |
| --- | --- | --- |
| Decrementing stock to commit a sale | Cannot rely on stale counts causing overselling | Concurrency-controlled source check/reserve/decrement workflow |
| Available balance approving payouts | Must reflect confirmed transaction obligations | Ledger/authoritative transactions and consistent decision rules |
| "I have liked this post" right after API success | Must match the user's just-committed action | Read source relationship or write result |
| Public like count on listing feeds | May lag if documented and measured | Sync counter or eventual projection |
| Category name on search pages | Bounded lag acceptable if product permits | JOIN, cache, or versioned projection |
| Access permissions or takedown requests | Never assume lag is harmless | Enforce permissions at decision points; prioritize safe revocation |
| 5-minute operational dashboards | Lag acceptable per SLO | Materialized view, pre-aggregation, or streaming |
| Locked price/address on past orders | Must preserve point-in-time transaction truth | Historical snapshot; never overwrite from live profiles |

**There is no universal rule that "all financial data requires one single SQL transaction."** Distributed financial systems often use ledgers, compensating flows, and multi-step settlement. What never changes is that **decisions creating binding obligations must read verified authoritative state under proper invariants**, never a potentially stale read projection.

### 7.1. Boundaries in Document, Graph, and Analytical Stores

In **document databases**, embedding a counter inside a post document supports single-document atomic updates, yet does not automatically keep counts synchronized with relationships stored across other documents. Check transaction scopes and multi-document fan-out.

In **graph databases**, friend counts derive from relationship edges. Adding an edge and updating a vertex property counter may require transactions; if counters update asynchronously, edge traversals and vertex counters can diverge temporarily. Supernodes (high-degree vertices) become write hotspots.

In **analytical systems**, daily sales load via batches or streams; dashboards read fast yet depend on watermarks, late-arrival rules, and formula versioning. Multi-currency reports require currency dimensions and conversion rules before aggregating.

Primitives differ across engines. Never generalize single-document or single-row SQL transaction guarantees across multi-service copies.

## 8. Reconciliation: When Is a Divergent Counter a Bug?

Recompute likes from the source relationship table:

~~~sql
WITH actual AS (
    SELECT
        p.post_id,
        COUNT(l.user_id)::BIGINT AS exact_count
    FROM posts AS p
    LEFT JOIN post_likes AS l
        ON l.post_id = p.post_id
    GROUP BY p.post_id
)
SELECT
    COALESCE(a.post_id, c.post_id) AS post_id,
    a.exact_count,
    c.like_count AS stored_count
FROM actual AS a
FULL OUTER JOIN post_like_counts AS c
    ON c.post_id = a.post_id
WHERE a.post_id IS NULL
   OR c.post_id IS NULL
   OR a.exact_count IS DISTINCT FROM c.like_count
ORDER BY post_id;
~~~

Use **COUNT(l.user_id)** instead of **COUNT(*)** so a post with zero likes counts as 0 despite the **LEFT JOIN** row. **FULL OUTER JOIN** catches both missing and orphaned counter rows.

Interpret output in the proper context:

- **Synchronous in one PostgreSQL DB:** if writes committed, every path follows the contract, and the query reads a consistent snapshot, any mismatch signals a bug to investigate.
- **Asynchronous:** counters may legitimately lag. Never classify every instantaneous mismatch as an error; compare at matching **watermarks/versions** or evaluate only changes older than the allowed sync window.
- **Two separate databases:** you cannot assume direct SQL JOINs work or that two independent reads observed the exact same instant.
- **During migration/backfill:** classify in-flight records separately from steady-state sync errors.

When a projection is proven divergent, **repair from the authoritative source** or perform controlled replay. Never manually tweak numbers in the summary table without finding root cause; workers will reintroduce the drift.

### 8.1. Where Should Lag Metrics Start and End?

For a requirement like "public counters are at most 30 seconds stale":

~~~text
T0 = source commits like mutation
T1 = outbox publisher successfully dispatches event
T2 = consumer receives event
T3 = projection commits update
T4 = API reads updated value
~~~

**T0 to T4** reflects user-observed lag; measuring only **T2 to T3** captures consumer processing time while hiding publisher and queue delays.

Metrics worth tracking:

| Metric | Question Answered |
| --- | --- |
| End-to-end freshness lag | How long until a source commit appears on read APIs? |
| Outbox oldest pending age | Are committed events stuck unpublished too long? |
| Queue / consumer backlog | Are workers falling behind incoming write rates? |
| Applied event count and duplicate count | Are excessive retries or abnormal replays occurring? |
| Reconciliation mismatch | How many counters diverge past the allowed window? |
| Retry / dead-letter count | Are poison events failing repeatedly unhandled? |
| p95/p99 read/write latency | Does the architecture meet SLOs on both paths? |
| Rebuild time and recovery progress | After an outage, can projections catch up within budget? |

**p95 lag = 5 seconds does not prove max lag is under 30 seconds.** If an SLA promises "max 30 seconds," monitor tail/max observed lag and escalation procedures on breach. If using percentile targets, state exact percentages and measurement windows.

## 9. An Evidence-Based Selection Experiment

Suppose a like-counting service targets:

- **Listing read API:** p95 ≤ **120 ms**.
- **Like/unlike write API:** p95 ≤ **160 ms**.
- **Public counter:** allowed up to **30 seconds** lag.
- **"User liked this post" state:** must match source immediately on success.

The team benchmarks three options under **the exact same representative load**. Numbers below are **hypothetical for learning decision analysis, not a real benchmark**:

| Hypothetical Benchmark Result | Source COUNT | Same-DB Sync Counter | Eventual Counter via Events |
| --- | ---: | ---: | ---: |
| Listing API p95 | 155 ms | 78 ms | 73 ms |
| Like API p95 | 95 ms | 210 ms | 103 ms |
| Max observed counter lag | No projection | No separate projection | 46 seconds |
| Observed bottleneck | Repeated COUNT scans | Hot rows on viral posts | Peak-hour queue backlog |
| Additional overhead | Read CPU/I/O on source | WAL, locks, counter writes | Outbox, consumer, table, retries |
| Meets all criteria above? | **No**: reads too slow | **No**: writes too slow | **No**: counter lag breaches bound |

The right conclusion is **not** "pick eventual because read p95 is lowest." Every candidate currently misses one requirement. Next steps:

1. Optimize the source COUNT access pattern and indexes to test whether source reads can pass.
2. For sync counters, measure hot-row prevalence and test write sharding if needed.
3. For eventual counters, drain backlog, tune outbox polling, and re-measure max lag—or renegotiate lag bounds if the business truly tolerates 46 seconds.
4. Separate personal "I liked this" state (read from source) from the public total, never using eventual tables to verify user write commits.

**Never add or subtract p95s across separate tables to compute end-to-end p95.** Each percentile is measured directly on its request cohort; re-benchmark whenever read/write ratios, data skew, or concurrency shift.

## 10. Backfills and Safe Rollout When Changing Consistency Models

Suppose the system previously ran COUNT against the source and now introduces **post_like_counts**. Never create an empty table and immediately cut all APIs over to it.

A reference rollout sequence:

1. **Lock down source and invariant:** relationships in **post_likes**; `like_count` defined as COUNT of active rows.
2. **Select consistency contract:** same-transaction sync or eventual; assign write/projection owners and SLOs.
3. **Prepare schema and indexes:** unique keys, non-negative CHECKs, write permissions, and read indexes.
4. **Enable change tracking or event capture:** ensure zero mutations are missed while historical loading runs.
5. **Backfill from an anchored source snapshot:** throttle concurrency and scan volume.
6. **Catch up post-snapshot changes:** for eventual pipelines use checkpoints/replay with dedup and ordering; for sync updates prevent backfills from overwriting live increments.
7. **Reconcile numbers:** test zero-like posts, mega-popular posts, rapid like/unlike toggles, deleted posts, and retried events.
8. **Gradual read cutover:** shadow-compare source queries against derived counts, monitor latency and lag, and keep rollback to source reads ready.
9. **Test recovery:** halt workers, replay events, rebuild tables, and verify convergence.

If a backfill reads a count of 100 likes, the consumer applies a new event reaching 101, and the lagging backfill writes **100**, the projection regresses. Use version/checkpoint guards or parallel-table cutover. Running a raw "UPDATE everything" never proves safety against live writes.

### 10.1. Retiring a Copy

Denormalization must remain reversible. If source query tuning makes COUNT fast enough, or queue/hot-row maintenance outweighs benefits, revert to computing at read time. Before stopping updates or dropping the table, verify zero APIs, batch jobs, reports, or services still depend on it.

## 11. Practice: Writing a Contract for a Derived Field

Example compact contract for **post_like_counts.like_count**:

| Item | What Must Be Specified |
| --- | --- |
| Authoritative source | **post_likes**, keyed by **(post_id, user_id)** |
| Formula | COUNT of currently active like relationships per post_id |
| Consumer | Counter-builder service or same-DB sync transaction |
| Triggering operations | Like, unlike, post deletion, relevant imports/restores |
| Consistency | Same-DB post-commit sync, or eventual with explicit SLO |
| Event emission (if eventual) | Outbox written atomically with source mutation |
| Deduplication | Relationship PK + event ID / processing log |
| Ordering | Like/unlike sequencing rules, versions, or partitioning |
| Verification | Re-COUNT from source at matching snapshot/checkpoint |
| Resources | Read/write p95/p99, lock waits, backlog, WAL |
| Recoverability | Replay/backfill, table rebuild, convergence verification |
| Ownership | Source team owns relationships; read team owns projection and monitoring |

Any blank row in this contract represents an unresolved design risk before relying on derived data in production.

## 12. Practice Exercises

### Exercise 1 — Like Button and Listing Screen

A user clicks Like on a post. The API writes the relationship to the source and returns success, yet the public listing screen shows the old count for 4 more seconds. The UI contract permits public counts to lag up to 15 seconds.

**Question:** Is this necessarily a bug? Where should the "I have liked this" state come from?

### Exercise 2 — Counter Doubled After Retry

A consumer incremented the counter for **LikeAdded event-123**, then crashed before ACKing. The queue redelivered the exact same event and the consumer incremented by 1 again.

**Question:** What is missing in the design? If the same action were emitted under two different event IDs, where else must checks happen?

### Exercise 3 — Hot Row on New Viral Post

A popular post receives 25,000 likes per second. The counter updates in the same transaction as each relationship INSERT; Like API p99 spikes sharply while read APIs stay fast.

**Question:** Why is the system bottlenecked? Name two alternative trade-off approaches and their acceptance conditions.

### Exercise 4 — Dashboard Lag

A sales dashboard reads an eventual summary table with 8-second p95 lag, yet once lagged 90 seconds. Business rules mandate **no more than 60 seconds stale**.

**Question:** Does it meet the SLO? Which stages should be instrumented and alerted?

### Exercise 5 — Locked Price or Current Price?

Someone proposes updating **order_items.unit_price_at_confirmation** whenever **catalog_products.current_price** changes so "data stays consistent."

**Question:** Is that rule right or wrong? How does it differ from syncing **product_cards.current_price_display**?

### Exercise 6 — Reconciling 100 vs. 101

The source shows post P has 101 likes; the eventual counter shows 100. The consumer is processing new events, but lacks commit timestamps or checkpoint watermarks.

**Question:** Can you conclude a 30-second lag SLO breach? What metadata is needed?

### Suggested Solutions

1. **Not necessarily a bug** if a 4-second delay fits the 15-second contract and converges cleanly. Personal liked state should come from the authoritative relationship or committed write result; optimistic UI may be shown with rollback handling on failure.
2. Needs **deduplication/idempotency** by event ID, recording processed markers and updating totals inside the same consumer transaction. If two distinct IDs represent one business action, enforce a **business identifier and unique constraint** at the source or equivalent deduplication.
3. Every transaction contends on locking the single counter row, queuing writes behind one another. Try **sharded counters** (adds read/reconciliation complexity) or **eventual/batch aggregation** (requires accepting lag and event handling). Measure write p95/p99, freshness, correctness, and resource usage.
4. **Fails SLO** because observed 90 seconds exceeds the 60-second limit despite good p95. Track source commit → outbox → queue → consumer → projection → API, oldest pending event age, backlog, retries, and mismatches.
5. **Wrong** for confirmed prices: that is a historical fact that must be preserved or adjusted via audited workflows. **product_cards.current_price_display** projects current prices and therefore must refresh from the source.
6. **Cannot conclude a time-bound breach** from a count difference of 1 alone. You need committed event timestamps, projection applied watermarks, age of unapplied events, end-to-end pipeline lag, and exact SLA measurement rules. It may be normal in-flight sync or a dropped event.

## 13. Takeaways

**Immediate consistency** promises accuracy within a defined read/write boundary post-commit; **eventual consistency** permits temporary divergence provided the system converges within agreed freshness bounds. Neither concept decides which data matters most—business invariants do.

**Denormalization cuts read cost by shifting work onto writes, synchronization, and operations.** Copies introduce extra writes, hot rows, event retries, lag, stale reads, and rebuild duties. An approach pays off only when **read latency, write latency, correctness, and recovery cost** all fit your constraints.

Before storing another counter, total, or display field, ask: **"After which action must this value be exact? If staleness is allowed, for how long? What cost do we pay per source change, and how do we detect and fix drift?"**
