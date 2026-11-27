# Mutation Timestamp Precision vs. the Timestamp Data Type in Data

## 1. Two Types of Timestamps, Two Purposes in Cassandra

In **Apache Cassandra** (a distributed **wide-column** database), the word *timestamp* appears in two contexts that are frequently confused:

- **Mutation timestamp** (also called *write timestamp*) is metadata attached to a cell write. Cassandra uses it to arbitrate versions during conflicting writes via the **last-write-wins** mechanism.
- **The CQL `timestamp` data type** is a column data type defined by the table designer, used to store an application-level point in time, such as when an order was created or when a device emitted an event.

Two values can represent the same point in time, yet **they do not have the same resolution, are not automatically synchronized with each other, and do not serve the same role**.

| Property | Mutation timestamp | CQL `timestamp` column |
|---|---|---|
| Purpose | Choose the winning version in a cell write conflict | Store an application timestamp for display, persistence, or querying |
| Core storage/representation unit | **Microseconds (µs)** since Unix epoch | **Milliseconds (ms)** since Unix epoch |
| Fractional second digits representable | Up to 6 digits: `.123456` | Up to 3 digits: `.123` |
| How it is assigned | `USING TIMESTAMP`, driver timestamp generator, or coordinator | Value in `INSERT`, `UPDATE`, or query parameters |
| How it is read via CQL | `writetime(column_name)` for supported columns | `SELECT column_name` |
| Can it be used as a partition/clustering key? | No, because it is cell metadata | A CQL `timestamp` column can be used in a key if it fits the table design |
| Directly affects last-write-wins? | **Yes** | **No**; unless the application explicitly converts the value into a mutation timestamp on write |

> **Key point:** "Microseconds" and "milliseconds" here refer to **representation resolution**. Using microsecond units does not mean real-world machine clocks are accurate to the exact microsecond, nor that every write receives a distinct timestamp.

## 2. Unix Epoch and Unit Conversion

Both representations can be based on the **Unix epoch**, i.e., `1970-01-01T00:00:00Z`. For the same point in time:

```text
2026-01-01T00:00:00.123456Z
                       └── 123456 microseconds within the first second

Epoch seconds:        1767225600
Epoch milliseconds:   1767225600123
Epoch microseconds:   1767225600123456
                                    ^^^
                            456 µs remaining after converting to ms
```

Arithmetic relationship for non-negative epochs:

```text
microseconds = milliseconds * 1_000 + microseconds_remainder
milliseconds = floor(microseconds / 1_000)

1767225600123456 µs
  = 1767225600123 ms * 1000 + 456 µs
```

If you store the event above in a **CQL `timestamp` column**, only millisecond precision is retained, e.g., `2026-01-01T00:00:00.123Z`. The sub-millisecond `456 µs` portion is not preserved by that column. Meanwhile, the mutation timestamp can carry the number `1767225600123456` as metadata.

If you convert back from epoch milliseconds to epoch microseconds by multiplying by `1000`, the lost sub-millisecond portion **cannot be recovered**:

```text
1767225600123 ms × 1000 = 1767225600123000 µs
1767225600123456 µs - 1767225600123000 µs = 456 µs lost
```

These numbers also illustrate a common mistake: passing a 13-digit **epoch milliseconds** value directly into `USING TIMESTAMP`, where Cassandra expects a ~16-digit **epoch microseconds** value. That mutation is interpreted as a point far in the past compared to current writes and easily keeps losing under last-write-wins.

## 3. CQL Example: One Column, Two Different Timestamps

The following experiment is intended for a **test keyspace** already selected with `USE`. Use an unused UUID so data and tombstones from previous runs do not skew the results.

### Create the Table

```sql
CREATE TABLE IF NOT EXISTS event_records (
    event_id uuid PRIMARY KEY,
    event_at timestamp,
    processing_state text
);
```

`event_at` is a column holding the event's timestamp; `processing_state` is a state the application can update. Each cell is still tagged by Cassandra with its own **write timestamp**.

### Write with an Explicit Mutation Timestamp

```sql
INSERT INTO event_records (
    event_id,
    event_at,
    processing_state
)
VALUES (
    22222222-2222-2222-2222-222222222222,
    '2026-01-01T00:00:00.123Z',
    'queued'
)
USING TIMESTAMP 1767225600123456;

SELECT event_at,
       writetime(event_at),
       processing_state,
       writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Expected semantic result:

| Expression | Expected value | Interpretation |
|---|---|---|
| `event_at` | `2026-01-01 00:00:00.123` depending on client display formatting | CQL `timestamp` column, **millisecond** precision |
| `writetime(event_at)` | `1767225600123456` | Write timestamp of the `event_at` cell, **microsecond** precision |
| `processing_state` | `queued` | Text column data |
| `writetime(processing_state)` | `1767225600123456` | Write timestamp of the `processing_state` cell |

**Observation:** `event_at` and `writetime(event_at)` are both time-related, yet one is a **user value** and the other is **metadata Cassandra uses to reconcile writes**. Here they are nearly equal because we **deliberately** chose the same instant. Cassandra does not automatically derive the mutation timestamp from `event_at`.

### A Difference of a Few Microseconds Can Change the LWW Outcome

Try updating `processing_state` with a timestamp **56 µs older** than the initial timestamp:

```sql
UPDATE event_records
USING TIMESTAMP 1767225600123400
SET processing_state = 'stale'
WHERE event_id = 22222222-2222-2222-2222-222222222222;

SELECT processing_state, writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

The result stays `queued` with write timestamp `1767225600123456` because mutation `...3400` is less than `...3456`. Even though the `UPDATE` ran after the `INSERT`, it still loses under LWW.

Next, write with a timestamp **one microsecond newer**:

```sql
UPDATE event_records
USING TIMESTAMP 1767225600123457
SET processing_state = 'processed'
WHERE event_id = 22222222-2222-2222-2222-222222222222;

SELECT event_at, writetime(event_at),
       processing_state, writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Now `processing_state = 'processed'` with write timestamp `...3457`; `event_at` still carries write timestamp `...3456`, because only the status cell was updated. The `event_at` column itself **does not gain extra precision** just because the mutation is 1 µs newer.

**Limitations of `writetime()`:** the function reads the write timestamp of supported regular columns; do not use it to read timestamps of **primary-key columns** or **counters**. For deleted cells, `writetime()` is not a tool for directly inspecting tombstone timestamps. Depending on data state and column type, the result may be `null` or the query may be rejected.

## 4. Differences Between Resolution, Accuracy, and Write Ordering

Separate three concepts:

1. **Resolution:** the smallest unit the representation can distinguish. Mutation timestamps use µs; CQL `timestamp` uses ms.
2. **Accuracy:** how close the recorded time is to actual real-world time. Clock skew, network latency, the timestamp generator, or sampling time all introduce error.
3. **Ordering guarantees:** whether two timestamp numbers reflect actual business ordering. Cassandra only compares **timestamp values**; it does not inherently know which event truly occurred first.

For example, a machine whose clock is 5 minutes fast can assign a future mutation timestamp to `status = 'approved'`. Another machine receives `status = 'cancelled'` later in real time but assigns a smaller timestamp. Cassandra may keep choosing `approved` due to LWW. Having **microseconds** does not fix this discrepancy.

Similarly, two requests from two services can receive the **same mutation timestamp** even though the time structure supports microseconds. Cassandra has a tie-breaking rule when timestamps are equal; never assume "the command sent later wins." When a tombstone conflicts with a live value at the same timestamp, the tombstone takes precedence. When an application requires conditional updates, it may need **lightweight transactions (LWT)** or a purpose-built data/event model.

## 5. Where Do Default Timestamps Come From?

When a CQL statement omits `USING TIMESTAMP`, Cassandra/the driver still must determine a mutation timestamp for regular writes. Depending on version and configuration:

- **The driver** can generate the timestamp client-side using a **timestamp generator** and send it with the request.
- **The coordinator** can generate the timestamp when the client does not supply one.
- **`USING TIMESTAMP <number>`** lets the CQL author specify a timestamp in **microseconds**, overriding the auto-generation policy for that write statement.

Some client-side timestamp generators attempt to maintain monotonically increasing values within the same process when many mutations are issued rapidly. This **does not guarantee** global ordering across multiple applications or absolute physical clock accuracy.

To reduce unwanted conflicts, synchronize system clocks, monitor **clock skew**, standardize timestamp generation policies across services, and avoid setting timestamps manually unless the problem genuinely requires it. For retries of the same event, consider reusing a stable timestamp so a late retry does not accidentally become a newer record.

## 6. Java Applications: `Instant`, Milliseconds, and Microseconds

Java applications connecting to Cassandra with the **DataStax/Apache Cassandra Java Driver** (4.x API) typically handle business instants using `java.time.Instant`.

Java's `Instant` supports nanoseconds, but when bound to a CQL `timestamp` column, Cassandra stores it at **millisecond resolution**. If you want to manually assign a mutation timestamp, you must convert `Instant` to **epoch microseconds** in the exact unit.

```java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class EventRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO event_records " +
            "(event_id, event_at, processing_state) " +
            "VALUES (?, ?, ?) USING TIMESTAMP ?"
        );
    }

    public void save(UUID eventId, Instant eventTime) {
        // Example: 2026-01-01T00:00:00.123456Z
        long epochMillis = eventTime.toEpochMilli(); // 1767225600123

        // Convert properly to epoch microseconds, preserving the µs part from Instant.
        long epochMicros = Math.addExact(
            Math.multiplyExact(eventTime.getEpochSecond(), 1_000_000L),
            eventTime.getNano() / 1_000L
        ); // 1767225600123456

        // event_at only stores down to ms; the mutation timestamp receives epochMicros.
        session.execute(insert.bind(eventId, eventTime, "queued", epochMicros));
    }
}
```

With `Instant.parse("2026-01-01T00:00:00.123456Z")`, the calculation produces the exact two values from Section 2. Using `Math.multiplyExact` and `Math.addExact` also helps detect overflow if the time range is abnormal.

### Common Java Mistakes

| Wrong code or assumption | Problem | How to handle |
|---|---|---|
| `USING TIMESTAMP = System.currentTimeMillis()` | Passes **ms** into a field requiring **µs** | Convert to the right unit; if true microseconds are needed, obtain a time source with sub-millisecond precision |
| `eventTime.toEpochMilli() * 1000` while assuming 1 µs precision | Unit is right, but the sub-**1 ms** part of `Instant` is lost | Use `getEpochSecond()` and `getNano()/1000` if existing microseconds must be preserved |
| Using `eventTime.getNano()` as Unix microseconds | `getNano()` is only the fraction within the second, missing seconds since epoch | Add epoch seconds × 1 million to the converted nanosecond fraction |
| Using `Instant.now()` on every client and trusting global ordering | Clocks across machines can drift; resolution does not imply accuracy | Synchronize clocks and design explicit business ordering rules |
| Expecting to read back full `.123456` from a `timestamp` column | CQL `timestamp` only keeps ms precision | Store an additional `bigint` epoch-microseconds column when preservation is required |

Note: you do not necessarily have to use `eventTime` itself as the mutation timestamp. For example, business logic may require **event occurrence time** and **status update time** to be two independent timelines. Choose the same timestamp only when the system's conflict policy genuinely requires it.

## 7. When Business Logic Needs to Preserve Microseconds in Data

Telemetry, financial, or stream-processing systems may receive data with microsecond-accurate timestamps. In that case, a single CQL `timestamp` column is **not enough to preserve the full input resolution**.

A clear option is to store **epoch microseconds** in a `bigint` column and optionally also store a `timestamp` column for display convenience:

```sql
CREATE TABLE sensor_events_by_device_day (
    device_id text,
    event_day date,
    event_time_us bigint,
    event_id uuid,
    event_at timestamp,
    measurement double,
    PRIMARY KEY (
        (device_id, event_day),
        event_time_us,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time_us DESC,
    event_id ASC
);
```

This model fits queries for **the newest events of a device on a given day**, filtering by `device_id`, `event_day`, and an `event_time_us` range (following the clustering key order). `event_id` distinguishes multiple events occurring within the same microsecond. `event_at` is only used as a millisecond-precision timestamp convenient for presentation. Limit the number of rows per partition using a bucketing strategy suited to actual traffic.

Query example:

```sql
SELECT event_time_us, event_id, event_at, measurement
FROM sensor_events_by_device_day
WHERE device_id = 'sensor-07'
  AND event_day = '2026-01-01'
  AND event_time_us >= 1767225600000000
  AND event_time_us < 1767312000000000
LIMIT 100;
```

Here, **row read order** is produced by the **clustering key `event_time_us`**; Cassandra **does not sort rows by `writetime()`**. That is a fundamental principle of query-driven table design in wide-column systems.

Storing microseconds as a `bigint` still only reflects the accuracy of the source data. If a sensor only measures down to milliseconds, multiplying milliseconds by `1000` does not create new time information.

## 8. Relationship to TTL, Replication, Consistency, and Repair

The **Timestamps and TTL** chapter also involves another time unit to distinguish: **TTL (time to live) in CQL is measured in seconds**.

```sql
UPDATE event_records
USING TTL 3600
SET processing_state = 'temporary'
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

In this statement:

- `TTL 3600` sets the lifetime of the state cell to roughly **3,600 seconds**.
- The cell's mutation still has a **write timestamp in microseconds** (using the auto-generation policy if `USING TIMESTAMP` is omitted).
- If you read `ttl(processing_state)` immediately after writing, you observe the number of **seconds remaining** for the cell, not microseconds.
- The `event_at timestamp` column in the table remains application data with **millisecond** resolution.

In a multi-replica cluster, writes do not necessarily arrive at nodes in the same order. **Replication factor** determines the number of copies; **consistency level** such as `ONE`, `QUORUM`, or `ALL` determines response requirements on read/write; and **mutation timestamp** determines which cell version wins during reconciliation. Raising the consistency level cannot fix a mutation carrying a wrong-unit timestamp or originating from a skewed clock.

When a cell's TTL expires or it is deleted, Cassandra uses an expiration/tombstone mechanism to prevent stale copies from reappearing before safe cleanup. **Compaction**, **repair**, and tombstone policies must be accounted for in operations; you cannot rely on timestamp resolution alone to infer that replicas are fully synchronized.

## 9. Checklist When Diagnosing Timestamp Bugs

| Symptom | What to check |
|---|---|
| `UPDATE` reports success, yet `SELECT` keeps the previous value | `writetime()` of the cell, `USING TIMESTAMP`, and the possibility of a tombstone with a higher timestamp |
| Two services write "at the same time", yet one service's writes always lose | **ms/µs** units, timestamp generator, clock skew between machines |
| API receives `.123456`, yet reading the time column only returns `.123` | CQL `timestamp` type has **ms** resolution; use `bigint` if full µs must be stored |
| Data appears different across replicas | Consistency level, replicas participating in the read, repair status, and write timestamp conflicts |
| Displayed results are shifted by several hours | Client timezone formatting and offsets in CQL strings; use `Z` or an explicit offset |
| Query cannot `ORDER BY writetime(...)` | To order events, design the clustering key according to the query |

For diagnostics, log the **unit and generation source of timestamps** in application logs rather than printing a bare integer. When passing times in JSON or APIs, use clear names such as `eventTimeEpochMicros`, `eventTimeEpochMillis`, or ISO-8601 with an offset like `2026-01-01T00:00:00.123Z`.

## 10. Self-Check Exercises

**Question 1.** An application stores `event_at` = `2026-01-01T00:00:00.123Z` and `writetime(event_at)` = `1767225600123456`. Do these two values contradict each other?

**Answer:** No. `event_at` is millisecond-level data; `writetime(event_at)` is microsecond-level metadata. They are not required to be equal, even though the example picks nearly the same instant.

**Question 2.** If two mutations on the same cell have timestamps `1767225600123456` and `1767225600123457` respectively, which mutation wins after reconciliation?

**Answer:** The mutation with `...3457`, because it is 1 µs larger. Do not infer that this mutation definitely arrived later in physical time.

**Question 3.** Can `Instant.toEpochMilli() * 1000` be used to produce a microsecond count?

**Answer:** It can produce an **epoch microseconds value**, but **it does not preserve the sub-millisecond µs portion** of `Instant`. If the inherent microsecond resolution is needed, use `getEpochSecond() * 1_000_000 + getNano() / 1_000`.

**Question 4.** To list a device's events from newest to oldest at microsecond resolution, is storing only the mutation timestamp enough?

**Answer:** No. Cassandra does not use mutation timestamps as a query sort key. Store the business timestamp at the required resolution and design the **clustering key** according to the query.

**Question 5.** Does `USING TTL 3600` correspond to 3,600 microseconds, milliseconds, or seconds?

**Answer:** **Seconds**. TTL, CQL `timestamp`, and mutation timestamps are three time concepts with three different roles and units.

**Key takeaway:** Cassandra mutation timestamps represent **microseconds** and serve **last-write-wins**; the CQL `timestamp` column type stores business timestamps at **millisecond** resolution; TTL is measured in **seconds**. Converting units properly is a necessary condition, yet clock accuracy and business ordering still must be designed and controlled separately.
