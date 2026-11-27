# COUNTER BATCH and Limits on Mixing with Regular Data

## Objectives and Context

In Apache Cassandra, data is distributed by **partition key**, stored under the **wide-column** model, and tables are typically designed around the queries they must serve. Alongside regular data columns, Cassandra provides the `counter` type for incrementing or decrementing tallies via CQL. These updates follow distinct rules, including a dedicated batch form: **`COUNTER BATCH`**.

This lesson falls within the scope of `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`: understanding distributed architecture, partition keys, query-driven table design, read/write consistency levels, and using Cassandra from Java. After this lesson, you should be able to:

- Design a valid counter table and explain why regular data must be separated into another table.
- Write counter `UPDATE`s, `BEGIN COUNTER BATCH ... APPLY BATCH`, and identify invalid batches.
- Distinguish **grouping updates** from an ACID transaction or a deduplication mechanism.
- Choose partition keys, consistency levels, and timeout/retry handling suited to count accuracy requirements.

## 1. Counter Is a Special Data Type

A counter is a signed integer column used for **adding/subtracting a delta**. Cassandra manages counter updates via a separate mechanism compared to regular value writes.

For example, an application tracks views and likes for each article by day and access channel:

~~~sql
CREATE TABLE article_counters_by_day (
    article_id text,
    day date,
    channel text,
    views counter,
    likes counter,
    PRIMARY KEY ((article_id, day), channel)
);
~~~

Here, `(article_id, day)` is the **composite partition key**, and `channel` is a **clustering column**. Rows for `channel = 'web'` and `channel = 'all'` for the same article/day reside in the same partition. This model fits queries reading metrics for an article on a given day:

~~~sql
SELECT channel, views, likes
FROM article_counters_by_day
WHERE article_id = 'post-42' AND day = '2026-11-21';
~~~

Counters are modified via addition or subtraction in an `UPDATE`:

~~~sql
UPDATE article_counters_by_day
SET views = views + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';

UPDATE article_counters_by_day
SET likes = likes - 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

If the counter row does not yet exist, the first update computes from an initial value of 0. However, before that update, a `SELECT` may return zero rows; the application should not assume a row with count 0 always exists.

Important rules:

| Topic | Rule |
| --- | --- |
| Increment/decrement | Use `UPDATE ... SET c = c + n` or `c = c - n`, where `n` is the delta. |
| Direct assignment | Do not use `SET views = 100` to initialize or reset a counter like a regular numeric column. |
| Primary key | A `counter` column cannot be part of the `PRIMARY KEY`. |
| Other columns in the table | Outside primary key columns, a table with counters may only contain counter columns; do not mix with regular `text`, `timestamp`, or `int` columns. |
| Expiration and write time | Do not use `USING TTL` or `USING TIMESTAMP` on counter updates. |
| Conditional writes | Counters do not support `IF` updates like lightweight transactions (LWT) to guarantee incrementing once. |
| Repeatability | `views = views + 1` is **not idempotent**: running it twice can increment by two units. |

## 2. COUNTER BATCH Syntax

When one event needs to update **multiple related counter rows**, Cassandra allows grouping them into a `COUNTER BATCH`:

~~~sql
BEGIN COUNTER BATCH
    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'web';

    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'all';
APPLY BATCH;
~~~

A single user viewing an article on the website increments both the `web` channel tally and the `all` aggregate tally. Both updates in this example belong to **the same partition**, thus avoiding the cost of distributing a batch across multiple partitions. You can read them back with the `SELECT` query from the previous section to observe the updated values.

Several points to distinguish:

1. `BEGIN COUNTER BATCH` is for **counter update statements**, not an alias for a standard `BEGIN BATCH`.
2. A batch is a **unit for dispatching and coordinating updates**. It does not turn counters into an ACID transaction across multiple rows/tables, does not create a consistent snapshot for readers, and does not provide an exactly-once guarantee.
3. A multi-partition batch can create coordination load, raise latency, and complicate error handling. Batching is not a default way to accelerate thousands of independent increments.
4. When counter columns of **the same row** must be incremented together, a single `UPDATE` is usually cleaner and more concise:

~~~sql
UPDATE article_counters_by_day
SET views = views + 1,
    likes = likes + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

Only increment both `views` and `likes` in the same statement if **the business event genuinely produces both actions**. A counter batch also does not impose an execution order across statements inside the batch.

## 3. Why Must Counters Not Be Mixed with Regular Data?

Suppose the system also stores article title, author, and last updated timestamp. That is regular data, so place it in an independent table:

~~~sql
CREATE TABLE article_metadata (
    article_id text PRIMARY KEY,
    title text,
    author text,
    updated_at timestamp
);
~~~

An **invalid design** puts `title` in a table with a counter:

~~~sql
-- INVALID: a counter table cannot contain non-primary-key regular columns.
CREATE TABLE invalid_article (
    article_id text PRIMARY KEY,
    views counter,
    title text
);
~~~

**The batch below is also invalid**, even though the statements write to two different tables:

~~~sql
-- INVALID: COUNTER BATCH does not accept regular data write statements.
BEGIN COUNTER BATCH
    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'web';

    UPDATE article_metadata
    SET title = 'Cassandra Fundamentals'
    WHERE article_id = 'post-42';
APPLY BATCH;
~~~

The reverse is also invalid: placing a counter increment inside a standard `BEGIN BATCH` or `BEGIN UNLOGGED BATCH` to try to mix the two update types. Cassandra separates counter batches from batches for regular write operations.

**The right solution** is separating the two write paths:

~~~sql
-- Regular data write path:
UPDATE article_metadata
SET title = 'Cassandra Fundamentals',
    updated_at = toTimestamp(now())
WHERE article_id = 'post-42';

-- Counter write path:
UPDATE article_counters_by_day
SET views = views + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

The two statements above are **two independent operations**. If the business requires both the metadata update and the counter increment to succeed or fail together, Cassandra does not provide an ACID transaction across two tables by wrapping them in a `COUNTER BATCH`. The application needs error-handling workflows, event recording, reconciliation, or an alternative data model depending on the required accuracy.

## 4. Timeouts, Retries, and Consistency Limits

The most error-prone scenario is when **the client does not know whether the increment was applied**:

| Time | Event | Possible Consequence |
| --- | --- | --- |
| T0 | Counter is currently 100. | This is the pre-event value. |
| T1 | Application sends `views = views + 1`. | One or more replicas may have processed the request. |
| T2 | Client receives a timeout. | A timeout does not prove the increment failed. |
| T3 | Application resends `+1` without business verification. | If the first attempt actually succeeded, the counter can reach 102 for a single view. |

Therefore:

- **Do not automatically retry a counter increment as if it were idempotent.** Inspect the client/driver retry policy and define how to handle indeterminate write outcomes.
- `LOCAL_QUORUM` or `QUORUM` can be chosen to achieve read/write acknowledgment levels suited to your replication and datacenters; they do **not** turn `+1` into an exactly-once write, nor do they fix duplicate submissions.
- `COUNTER BATCH` does not eliminate this risk. If a batch times out and is resent, one or more counts may be incremented again.
- Repair resolves data divergence across replicas under Cassandra's mechanisms; repair cannot recognize that two `+1` increments actually came from the same business event to reduce them back to one.

If counts are only used as **approximate metrics**, such as dashboard view counts, counters can be a good fit. If counts affect **money, quotas, inventory, entitlements, or strict exactness requirements**, consider modeling individual events with unique `event_id` values and a recoverable aggregation/reconciliation pipeline. Storing an `event_id` and then updating a counter in two separate tables still **does not automatically create an atomic transaction**; processing states and recovery paths must be explicitly designed.

## 5. Choosing Partition Keys, Replication, and Performance

Cassandra distributes data by partition key. In the example, `(article_id, day)` groups channels for the same article/day to serve related queries and updates. This is convenient when one event increments both `web` and `all` rows in the same partition, yet it can create a **hotspot** if one article receives massive traffic.

Under high load, one approach is splitting the counter across **shards residing in multiple partition keys**:

~~~sql
CREATE TABLE article_views_by_day_shard (
    article_id text,
    day date,
    shard smallint,
    views counter,
    PRIMARY KEY ((article_id, day, shard))
);
~~~

Each event picks a `shard` from a fixed range and increments that partition's counter. When reading the total, the application fetches data from **all shards** and sums them. Placing `shard` inside the **partition key** is essential; placing it only in the clustering key keeps all shards in the same partition and does not spread the hotspot. In return, read count and aggregation work grow with the number of shards.

Operational decisions should be grounded in queries and actual load:

| Scenario | Appropriate Approach |
| --- | --- |
| Incrementing one counter on one row | Single counter `UPDATE` statement. |
| Incrementing two counters on the same row | Single `UPDATE` with two addition/subtraction expressions. |
| Incrementing related counter rows in the same partition | Consider a small `COUNTER BATCH`; benchmark real performance. |
| Incrementing a large number of independent counters across many partitions | Separate `UPDATE`s, executed with bounded parallelism and backpressure; avoid giant batches. |
| Writing metadata and incrementing a counter | Two tables, two write paths; build business-driven error handling. |
| One partition receives very high increment traffic | Consider partition-key sharding and read-time aggregation. |
| Need to clear/reset periodic statistics | Design counters per new day/period/version; never treat `SET counter = 0` as a valid operation. |

With multi-datacenter replication, review replication factors, consistency levels, and read freshness requirements. Counts remain subject to distributed systems behavior: replicas may be temporarily out of sync, connection failures can leave write outcomes ambiguous, and higher consistency levels typically trade latency/availability under certain failure modes.

## 6. Using COUNTER BATCH from Java

Example with **Apache Cassandra Java Driver 4.x**, assuming `CqlSession session` is already configured and connected to the appropriate keyspace:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;

// session is created/configured in the application's connection management layer.
void recordWebView(CqlSession session, String articleId, LocalDate day) {
    PreparedStatement increment = session.prepare(
        "UPDATE article_counters_by_day " +
        "SET views = views + ? " +
        "WHERE article_id = ? AND day = ? AND channel = ?");

    BoundStatement web = increment.bind(1L, articleId, day, "web");
    BoundStatement total = increment.bind(1L, articleId, day, "all");

    BatchStatement batch = BatchStatement.builder(DefaultBatchType.COUNTER)
        .addStatement(web)
        .addStatement(total)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setIdempotence(false)
        .build();

    session.execute(batch);
}
~~~

The code represents a single view event incrementing two counter rows. The `?` placeholders use prepared statement parameters, avoiding direct concatenation of user input into CQL. `LOCAL_QUORUM` is only a **configuration example**; choose a consistency level matching your replication, datacenter layout, and latency targets.

In a real application, prepare the statement once and reuse it; configure timeouts, retries, error monitoring, and bounds on in-flight requests. Setting `setIdempotence(false)` clarifies that this batch is unsafe to replay arbitrarily. If `session.execute(batch)` throws a timeout, the application must handle the **indeterminate outcome** state rather than immediately incrementing again.

## 7. Practice and Verification

1. Create `article_counters_by_day` from section 1. Execute the `COUNTER BATCH` in section 2 once; read both the `web` and `all` rows. If the table is newly created with no other updates, each row will have `views = 1`.
2. Execute that exact batch one more time; observe the counts increment again. This is direct evidence of **non-idempotence**, not a Cassandra bug.
3. Create `article_metadata` and try the batch mixing a counter with a `title` update in section 3. Cassandra must reject the invalid batch; note the error message to identify the enforced rule.
4. Compare one `UPDATE` incrementing two columns on the same row against two separate `UPDATE`s. Choose the form that matches a single business event, avoiding coupling two unrelated metrics.
5. Simulate a scenario where a batch times out after dispatch: write down the business strategy for approximate counts versus strictly exact counts. Note that re-reading a counter after a timeout **is not always sufficient** to prove a specific event was applied exactly once when multiple clients increment concurrently.

When testing in a multi-replica environment, monitor timeout counts, retries, consistency levels, hot partition load, and latency. Do not treat a single `SELECT` returning the expected number as proof that the system guarantees exactly-once semantics.

## Key Takeaways

**`COUNTER BATCH` is strictly for counter updates; regular data must live in separate tables and write paths.** Design partition keys around queries, keep batches small, treat `+1` as non-idempotent, and handle timeouts according to your business accuracy requirements. Batches help group related operations, but they do not replace ACID transactions or event deduplication mechanisms.
