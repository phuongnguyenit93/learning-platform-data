# Static Columns and Shared Data Within a Partition

In Apache Cassandra, a **partition** can contain multiple rows, distinguished by **clustering columns**. When multiple rows belonging to the same partition need to share a piece of information, Cassandra allows declaring a **static column** using the CQL `STATIC` keyword. The value of this column exists at the **partition level**, rather than being stored separately for each row with a different clustering key.

This concept is especially useful in the distributed wide-column model: the partition key identifies the group of rows and responsible replica set; clustering columns distinguish and sort rows within the group; and static columns describe information applying to the **entire group**. However, "shared" only has meaning **within a single logical partition of one table**; it does not turn Cassandra into a relational database with JOINs or data shared across all partitions.

After this lesson, you will be able to:

- Identify `STATIC` columns and distinguish them from partition keys, clustering columns, and regular columns.
- Create tables with static columns; write partition metadata even before any event rows exist.
- Read, update, and delete static columns within the proper scope using CQL.
- Understand why static data may repeat in `SELECT` results while belonging to only one partition.
- Evaluate the benefits, limits, TTL, replication, and modeling mistakes when using static data.
- Use the Java Driver to read/write metadata at the partition level.

## 1. What is a static column?

Suppose an application stores events within an access session. Each session has **multiple events**, while `user_id`, session start time, and access source are **shared information for the whole session**.

If these attributes were placed as regular columns, every event row would have to carry its own copy of the values. With `STATIC`, we declare the metadata **once per partition key** and event rows in the partition see that same value.

| Column type | Key / Example | Purpose |
| --- | --- | --- |
| Partition key | `(tenant_id, session_id)` | Selects the partition and determines data distribution placement. |
| Clustering columns | `event_time`, `event_id` | Distinguish events and determine order within the session. |
| Static columns | `user_id STATIC`, `started_at STATIC`, `source_app STATIC` | Store shared metadata for the partition/session. |
| Regular columns | `event_type`, `payload` | Store values specific to each event row. |

One way to visualize it:

```text
Partition key = ('acme', session-01)
│
├── Partition static data:
│     user_id    = user-77
│     started_at = 2026-11-21 08:00:00 UTC
│     source_app = web
│
├── Row (08:00:05, event-A) -> page_view, /home
├── Row (08:00:10, event-B) -> button_click, buy
└── Row (08:00:15, event-C) -> page_view, /checkout
```

Rows in the same partition share the **same current static value**. Changing `source_app` at the partition level will be reflected when reading those rows, subject to write time and the read/write consistency level in use.

> **Point of distinction:** a static column is not part of the primary key. It does **not** change the token, does not identify rows, and does not affect clustering order.

## 2. Declaring static columns in CQL

Design a table serving two primary queries:

1. Reading the list of latest events for a session.
2. Reading metadata that applies to the entire session without accessing individual events.

```sql
CREATE TABLE session_events_by_id (
    tenant_id  text,
    session_id uuid,
    event_time timestamp,
    event_id   timeuuid,
    user_id    uuid STATIC,
    started_at timestamp STATIC,
    source_app text STATIC,
    event_type text,
    payload    text,
    PRIMARY KEY (
        (tenant_id, session_id),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Read this schema as follows:

- **Composite partition key:** `(tenant_id, session_id)`. Each tenant–session pair is one logical partition.
- **Clustering columns:** `event_time` and `event_id`. They distinguish and order events within the session.
- **Static columns:** `user_id`, `started_at`, and `source_app`. These three values are shared within the same partition.
- **Regular columns:** `event_type` and `payload`, varying per event.

### Declaration rules

Static columns are only supported in tables that have **at least one clustering column**. They cannot be part of the primary key.

Invalid example:

```sql
-- No clustering column: cannot declare STATIC.
CREATE TABLE invalid_session_metadata (
    session_id uuid PRIMARY KEY,
    source_app text STATIC
);
```

In cases where there is strictly one row per partition key and no clustering columns, use **regular columns**, without `STATIC`.

On the other hand, the partition key **does not have to be composite** to use static columns. A table with `PRIMARY KEY (session_id, event_time)` can still contain `source_app text STATIC`, because `event_time` is a clustering column.

## 3. Writing static metadata and writing events

### Writing metadata when a session starts

Static columns can be written by providing the **full partition key**, even without providing clustering columns:

```sql
INSERT INTO session_events_by_id (
    tenant_id, session_id, user_id, started_at, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    8817a208-1858-4144-86e9-b24d9083e478,
    '2026-11-21T08:00:00Z',
    'web'
);
```

The statement above creates/updates the **partition's static data**. It does not create a regular event row with `event_time` and `event_id`. This differs from writing regular columns: regular columns belong to a specific row, so writing them requires specifying the row's full clustering key.

### Writing events into the same session

```sql
INSERT INTO session_events_by_id (
    tenant_id, session_id, event_time, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:05Z',
    now(),
    'page_view',
    '/home'
);

INSERT INTO session_events_by_id (
    tenant_id, session_id, event_time, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:10Z',
    now(),
    'button_click',
    'buy'
);
```

Both event rows share the partition key `('acme', 327a71e9-...)`, so both see the same `user_id`, `started_at`, and `source_app` in the partition.

**Note on `now()`:** this function generates a new `timeuuid` on every call. If the business logic requires idempotent writes on retry, use a stable event identifier generated and reused by the application to avoid creating multiple rows for the same event.

### Writing metadata after events already exist

Writing static data first is not required. If event rows already exist, an `UPDATE` on a static column by partition key still applies the new value to the entire partition.

```sql
UPDATE session_events_by_id
SET source_app = 'web-v2'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

You do not need to pass `event_time` or `event_id`, because `source_app` belongs to the partition, not to each individual event row.

## 4. How does static data appear in `SELECT`?

### Reading event rows along with metadata

```sql
SELECT event_time, event_id, event_type, payload,
       user_id, started_at, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

If the partition contains two event rows, the **result** might look like this (`event_id` shortened for readability):

| `event_time` | `event_id` | `event_type` | `source_app` | `user_id` |
| --- | --- | --- | --- | --- |
| 08:00:10 | B | button_click | web-v2 | user-77 |
| 08:00:05 | A | page_view | web-v2 | user-77 |

`source_app` and `user_id` **are displayed repeatedly on every result row**. That does not mean Cassandra stored a separate copy of these two columns for each event. They are shared partition values, projected onto each result row during reads.

### Reading partition metadata once

If you only need metadata, use `SELECT DISTINCT` on the **partition key and static columns**:

```sql
SELECT DISTINCT tenant_id, session_id, user_id, started_at, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

This expresses the intent of "one shared data row for the partition." With Cassandra's `SELECT DISTINCT`, you cannot arbitrarily add clustering columns or regular columns to the select list.

Merely running `SELECT source_app FROM ... WHERE ...` **is not guaranteed to always return a single row**, because static data can be projected onto every clustering row. If not using `DISTINCT` and only needing any single row carrying the metadata, you can use `LIMIT 1` in an appropriate query.

### A partition containing only static data

An important case: an `INSERT` only wrote static columns to create session metadata, with no events yet.

When selecting from this partition, Cassandra can still return **one row representing the static data**; the clustering and regular columns of that row have `null` values. Once event rows are written, the static columns appear alongside those rows in read results.

Example result before the first event:

| `tenant_id` | `session_id` | `event_time` | `event_id` | `source_app` |
| --- | --- | --- | --- | --- |
| acme | session-01 | `null` | `null` | web |

The illustrative table only represents data semantics; `session-01` is shorthand, not a CQL `uuid` literal.

Conversely, if the partition has event rows while static columns have not been written yet, the static values read back can be `null`.

## 5. Updating and deleting: partition scope vs. row scope

Static and regular columns have different update scopes:

| Operation | Required key condition in standard cases | Effect |
| --- | --- | --- |
| `UPDATE` static column | Full partition key | Shared value of the partition. |
| `UPDATE` regular column | Full partition key **and** row's clustering key | One specific row. |
| `DELETE static_column` | Full partition key | Deletes the partition's static value. |
| `DELETE` one clustering row | Row's full primary key | Deletes that event row; static data remains. |
| `DELETE` entire partition | Full partition key, without specifying clustering key | Deletes both clustering rows and static data of the partition. |

### Updating a static column

```sql
UPDATE session_events_by_id
SET source_app = 'android'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Subsequent reads can show `android` on **every row** in the partition, depending on timing and consistency level. Cassandra processes writes via cell timestamp semantics; concurrent updates can resolve according to conflict-resolution rules rather than an exclusive partition-wide lock assignment.

### Deleting only one static column

```sql
DELETE source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

After successful deletion and reading at an appropriate consistency level, `source_app` no longer has a current value, while events and other static columns can still exist.

### Deleting one event while keeping metadata

```sql
-- Assume the event_id below is the real ID of the event to delete:
DELETE FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_time = '2026-11-21T08:00:05Z'
  AND event_id = 199dd010-a94c-11e5-bf7f-feff819cdc9f;
```

This statement affects the row with the given clustering key; static columns still belong to the partition.

### Deleting the entire partition

```sql
DELETE FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

When deleting a **partition** this way, Cassandra deletes both the static part and the clustering rows of the partition using tombstones. In Cassandra, deleting does not mean data disappears immediately from all physical SSTables; compaction and tombstone handling govern the storage lifecycle.

> **Common mistake:** wanting to change shared metadata, but writing it as a regular column on one specific row. Reading other rows will not automatically show that value. Declare `STATIC` at design time if the semantics truly belong to the partition.

## 6. TTL, write timestamps, and replication of static columns

Static columns are **normal Cassandra cells with respect to TTL, write timestamps, and replication**, differing only in their partition-level scope.

### TTL can apply to a static column

For example, setting a one-hour expiration on a static value:

```sql
UPDATE session_events_by_id
USING TTL 3600
SET source_app = 'temporary-web'
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

TTL attaches to the **cell value written by the operation**, and does not automatically set a one-hour expiration on all event rows in the partition. When the static value's TTL expires, the other events can continue to exist.

You can inspect the TTL and write timestamp of a cell in an appropriate query context:

```sql
SELECT DISTINCT tenant_id, session_id, source_app
FROM session_events_by_id
WHERE tenant_id = 'acme'
  AND session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

If you want to view `TTL(source_app)` or `WRITETIME(source_app)`, you can query those functions in a regular `SELECT` statement; the returned value reflects the metadata of the surviving cell and depends on read timing.

### Static data is still subject to replication and consistency

- Static values belong to the **same partition** as event rows, distributed by the **same partition key**, with no separate token.
- Replicas are determined by the **keyspace replication strategy and replication factor**. Static columns do not create a "sub-table" with different replication.
- Reading/writing static columns uses the same **consistency level** semantics and **last-write-wins by timestamp** as corresponding Cassandra data. That does not guarantee every replica sees updates instantaneously.
- `STATIC` does not automatically provide multi-partition transactions, system-wide uniqueness, or guarantees that metadata fields update atomically for every business rule.

For example: if an application writes metadata at consistency level `ONE` and immediately reads from a replica that has not yet received the update, it may observe the old value. Choosing consistency levels for reads/writes is a system-wide decision, not a special feature of static columns.

### How does changing a static value take effect?

A new static value is written **once per partition key**. The application does not need to issue `UPDATE` statements for each clustering row. However, if you **duplicate the same business information across many partitions** (for example, the same `user_id` across thousands of daily partitions), updating the static column in one partition does **not** automatically update the other partitions.

## 7. When should and shouldn't you use `STATIC`?

Static columns are well-suited for data that:

1. **Has true partition-level meaning**: the whole session shares the logged-in user, start time, or originating channel.
2. **Is frequently read alongside clustering rows**: event queries want to display session info as well.
3. **Is managed by partition key**: the application knows the exact session to read/update.
4. **Does not require automatic synchronization across multiple partitions**.

Suitable examples:

| Partition key | Clustering keys | Meaningful static data |
| --- | --- | --- |
| `session_id` | `event_time, event_id` | Session start time, client that created the session. |
| `(tenant_id, device_id, event_day)` | `measured_at, measurement_id` | Notes or configuration applying **specifically to that day bucket**. |
| `order_id` | `line_number` | Status or currency of the **order**; each line item holds its own values. |
| `(account_id, month_bucket)` | `transaction_time, transaction_id` | Metadata defined specifically for the transaction month. |

**Unsuitable** cases:

- **Global user information:** display name or email address that must stay consistent across thousands of partitions by tenant, day, and session. A static cell in session A will not automatically update in session B. Consider a profile table keyed by `user_id` or an explicit multi-table synchronization model.
- **Per-row varying data:** temperature of each measurement, status of each line item, or event timestamp. These values must be regular columns.
- **Aggregate values requiring exact updates under concurrent writes:** `total_events STATIC` followed by read-add-write can lose updates when multiple producers write in parallel. Design proper aggregation, counters, or coordination mechanisms; `STATIC` does not solve addition atomicity.
- **Data needing queries across all static values:** e.g., "find all sessions with `source_app = 'web'`." Defining a static column **does not automatically create a table-wide index** on `source_app`.
- **Oversized partitions:** `STATIC` only saves repeated information; it does not split a large partition into smaller partitions.

### Static column vs. a separate metadata table

Two common modeling approaches:

| Criterion | Metadata as `STATIC` | Metadata in a separate table |
| --- | --- | --- |
| Scope | One partition of a table with clustering rows. | By the metadata table's partition key. |
| Reading alongside events | Can receive metadata in the same partition query. | Application usually needs an additional metadata query. |
| Updating | One partition key of the event table. | One partition key of the metadata table. |
| Reuse across multiple tables/partitions | Not automatically synchronized. | Can share reading a single independent metadata record. |
| Data lifecycle | Easily tied to the event partition, though TTL/deletion must be considered. | Metadata lifecycle can be managed independently. |

If the data is genuinely **session** metadata, static columns make sense. If it is a **user attribute existing independently of sessions**, a separate profile table is usually clearer.

## 8. Reading and updating static columns from Java

The Java Driver 4.x example below assumes `CqlSession` is connected and the `session_events_by_id` table resides in the current keyspace. `PreparedStatement` objects are prepared once and reused.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.UUID;

public final class SessionMetadataRepository {
    private final CqlSession session;
    private final PreparedStatement readMetadata;
    private final PreparedStatement writeSourceApp;

    public SessionMetadataRepository(CqlSession session) {
        this.session = session;
        this.readMetadata = session.prepare(
            "SELECT DISTINCT tenant_id, session_id, user_id, " +
            "started_at, source_app " +
            "FROM session_events_by_id " +
            "WHERE tenant_id = ? AND session_id = ?"
        );
        this.writeSourceApp = session.prepare(
            "UPDATE session_events_by_id SET source_app = ? " +
            "WHERE tenant_id = ? AND session_id = ?"
        );
    }

    public SessionMetadata findMetadata(String tenantId, UUID sessionId) {
        Row row = session.execute(readMetadata.bind(tenantId, sessionId)).one();
        if (row == null) {
            return null; // No data for the queried partition
        }
        return new SessionMetadata(
            row.getUuid("user_id"),
            row.getInstant("started_at"),
            row.getString("source_app")
        );
    }

    public void updateSourceApp(String tenantId, UUID sessionId, String sourceApp) {
        session.execute(writeSourceApp.bind(sourceApp, tenantId, sessionId));
    }

    public record SessionMetadata(
        UUID userId, Instant startedAt, String sourceApp
    ) {}
}
```

Key points to note:

- Java binds **all partition key components**: `tenantId` and `sessionId`.
- `SELECT DISTINCT` retrieves only the partition key and static columns, fitting the goal of reading a session's metadata.
- `UPDATE` of a static column **does not need `event_time`/`event_id`**.
- Static values can be `null` if not yet written or after TTL expiration; the application must handle that case.
- If business requirements demand read-after-write with a specific consistency level, configure the consistency level on the driver/statement according to system policy.

`STATIC` helps reduce multi-row updates, yet you still need to manage metadata versioning, retry mechanisms, and concurrent writes in the Java application just like with other Cassandra data.

## 9. Common errors and diagnostics

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| `CREATE TABLE` errors when declaring `STATIC` | Table has no clustering column, or tried to mark a key column `STATIC`. | Check primary key structure; only mark non-key columns. |
| `SELECT *` shows static data "duplicated" | Static values appear on **every result row** in the partition. | Understand this is result projection; use `SELECT DISTINCT` if only metadata is needed. |
| Wrote static metadata but see no events yet | Writing only partition key and static columns does not create clustering rows. | This is a valid state; write events with the full clustering key when needed. |
| Updated `source_app` of one session but another session still keeps the old value | Static data is scoped to a single partition key. | Distinguish session metadata from global metadata; use a separate table or intentional updates. |
| Static column suddenly becomes `null` | Never written, deleted, TTL expired, or read discrepancy due to consistency. | Check update flow, TTL, consistency, and write timestamps. |
| Deleted all events but metadata still remains | Deleting individual clustering rows does not delete static values. | Clarify lifecycle requirements; when deleting an entire session, delete the whole partition. |
| Updating event count via `total + 1` then `UPDATE` static | Concurrent writes cause lost updates. | Use a proper aggregation/sync model; do not treat a static cell as an atomic counter. |
| Query `WHERE source_app = 'web'` is not served efficiently | Static column is neither partition key nor clustering key. | Design a table serving that query pattern or evaluate a version-compatible index. |

## 10. Knowledge self-check

Consider a table storing line items by order:

```sql
CREATE TABLE order_items_by_order (
    order_id      uuid,
    line_number   int,
    product_id    uuid,
    quantity      int,
    unit_price    decimal,
    currency      text STATIC,
    customer_note text STATIC,
    PRIMARY KEY (order_id, line_number)
);
```

Answer before viewing the explanations:

1. What are the table's partition key, clustering key, and static columns?
2. Can two line items with the same `order_id` have two separate `currency` values?
3. Can `customer_note` be written before the first `line_number` exists?
4. Does deleting a row with `line_number = 3` remove the order's `currency`?
5. To change the `currency` of **one order**, which columns must be specified in `WHERE`?
6. Does `SELECT currency, customer_note FROM order_items_by_order WHERE order_id = ...` always return a single row?
7. Does `currency STATIC` automatically enable finding all orders using `'VND'` currency?

**Answers:**

1. Partition key: `order_id`; clustering key: `line_number`; static columns: `currency` and `customer_note`.
2. **No within the same partition**: every line item of the same order sees the same current static `currency` value.
3. **Yes**: write the static columns with `order_id`, without needing `line_number`.
4. **No**: deleting one clustering row does not delete the partition's static metadata.
5. `WHERE order_id = ...` is sufficient to update `currency`.
6. **Do not assume so**: when multiple clustering rows exist, static data can appear repeated in the results; use `SELECT DISTINCT order_id, currency, customer_note ...` if only metadata is needed.
7. **No**: `STATIC` does not automatically provide an index or table-wide search by column value.

## 11. Summary and design principles

- `STATIC` declares **one shared value per partition key**; the table must have at least one clustering column.
- Static columns are not in the primary key and do not participate in token hashing or clustering order.
- Reading data alongside multiple clustering rows can **display static data repeatedly**; that is result representation, not multiple separate stored values.
- You can **write or update static columns using only the partition key**; deleting individual clustering rows does not automatically delete static data.
- Static cells remain subject to **TTL, write timestamps, replication, and consistency** like regular Cassandra data; consistency is not strengthened merely because a column is static.
- Only use `STATIC` when data **truly has the same meaning across a single partition**. Independent metadata or data that must stay synchronized across many partitions usually requires another table or strategy.

Understanding static columns accurately lets you combine shared and per-row data in Cassandra's wide-column model, control record lifecycles, and write appropriate CQL/Java queries. This lays the groundwork for exploring replication, consistency levels, compaction, repair, and operational scenarios when data is updated or deleted.
