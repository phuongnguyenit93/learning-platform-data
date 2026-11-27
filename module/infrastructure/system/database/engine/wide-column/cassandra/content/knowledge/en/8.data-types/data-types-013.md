# Key Data Types and Corresponding Constraints in Apache Cassandra

In **Apache Cassandra**, choosing a data type for a column in `PRIMARY KEY` is not merely a value representation decision. The **partition key** type affects how Cassandra generates tokens and distributes data to replicas; **clustering column** types affect how rows are **compared and sorted within a partition**. A CQL type completely valid for a regular data column is not necessarily valid—or suitable—inside a key.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module aims to cover distributed architecture and the wide-column model, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, error handling, and Java integration. Therefore, this lesson does not just list key syntax—it explains **identity semantics, ordering, uniqueness, queryability, retry control, and operations**. Details dependent on Cassandra version or distribution are called out explicitly to prevent mechanical misapplication.

## 1. Understanding PRIMARY KEY Before Choosing Types

Every Cassandra table must define a **`PRIMARY KEY`**. A primary key has two parts:

1. **Partition key** — always present; consists of **one or more columns**; Cassandra encodes and hashes it via the partitioner to determine the token and replicas.
2. **Clustering columns** — optional; columns listed **after** the partition key in the key declaration that determine row order **within the same partition**.

The following three declarations are **not equivalent**:

~~~cql
-- 1. Partition key only; each partition has at most one row.
CREATE TABLE accounts_by_id (
    account_id uuid PRIMARY KEY,
    display_name text
);

-- 2. account_id is the partition key;
--    event_id is the clustering column.
CREATE TABLE events_by_account (
    account_id uuid,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY (account_id, event_id)
);

-- 3. (account_id, event_day) is the composite partition key;
--    event_id is the clustering column.
CREATE TABLE events_by_account_day (
    account_id uuid,
    event_day date,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), event_id)
);
~~~

| Declaration | Partition Key | Clustering Columns | Consequence |
|---|---|---|---|
| `PRIMARY KEY (a)` | `a` | None | Each value of `a` identifies one row/partition |
| `PRIMARY KEY (a, b)` | `a` | `b` | Multiple rows can share `a`, sorted by `b` |
| `PRIMARY KEY ((a, b))` | `(a, b)` | None | `a` and `b` **jointly produce the partition's token** |
| `PRIMARY KEY ((a, b), c, d)` | `(a, b)` | `c`, `d` | Rows sharing `(a, b)` live in the same partition, sorted by `c, d` |

**Order and parentheses are part of the schema**, not decorative formatting. A very common mistake is writing `PRIMARY KEY (tenant_id, day, event_id)` assuming `(tenant_id, day)` is the partition key. In reality, in that syntax **only `tenant_id`** is the partition key, while `day` is a clustering column. To bucket by both tenant and day, write `PRIMARY KEY ((tenant_id, day), event_id)`.

### 1.1. "Ordered" Does Not Mean "Globally Sorted Across the Cluster"

Cassandra does not lay out partitions chronologically or numerically like a sequential B-tree index in SQL. The partitioner hashes **the entire partition key** into a token; two consecutive dates or two consecutive UUID v1s do not sit adjacent on the token ring.

Only clustering columns establish sort order within **a single partition**. Therefore:

- `timestamp` as a **single partition key** does not support querying "the 100 newest events cluster-wide."
- `timeuuid` as a **clustering key** within a chosen partition reads rows ordered by the time embedded in UUID v1.
- `date` inside a **composite partition key** is useful for bucketing, yet reading three days still requires querying the three daily partitions or building another access path.

## 2. Which CQL Types Are Allowed in Key Positions?

CQL documentation establishes two **strictly critical** restrictions:

- **`counter` cannot be a `PRIMARY KEY` column**. It is a counter column type with specialized increment/decrement semantics.
- **`duration` cannot be a `PRIMARY KEY` column** because it lacks a calendar-independent total ordering (`1mo` is not always larger or smaller than `30d`).

For other types, validity depends on nesting, **`frozen`**, version, and schema rules.

| CQL Type / Group | In `PRIMARY KEY` | Design Assessment |
|---|---|---|
| `uuid`, `timeuuid` | Typically ideal | `uuid` for IDs; `timeuuid` fits timeline clustering |
| `text`, `varchar`, `ascii` | Yes | Requires normalization, length caps, avoid arbitrary keys |
| `tinyint`, `smallint`, `int`, `bigint`, `varint` | Yes | Use for IDs/sequences/buckets with clear domains; avoid hotspots |
| `date`, `timestamp`, `time` | Yes | Distinguish bucket dates, absolute instants, and times of day |
| `inet`, `boolean`, `blob` | Allowed per type rules | Validity does not ensure good distribution; standalone `boolean` creates severe hotspots |
| `decimal`, `float`, `double` | Syntactically allowed in CQL | Usually **avoid** as business IDs due to canonicalization and floating-point arithmetic |
| `counter` | **No** | Regular counter column only with dedicated write rules |
| `duration` | **No** | Calendar intervals lack a fixed total ordering |
| **Non-frozen** `list<T>`, `set<T>`, `map<K,V>` | **No** | Multi-cell data, invalid as key columns |
| `frozen<list<T>>`, `frozen<set<T>>`, `frozen<map<K,V>>` | **Possible**, if inner types are valid | Legal does not mean advisable: keys become bulky and brittle |
| `tuple<...>` | Tuples are inherently **frozen**, allowed when component types are valid | Positional indices are error-prone; prefer simple scalar keys |
| `frozen<UDT>` | Possible depending on version and field types | Monolithic value; changing any field changes the whole key |
| Non-frozen UDT | **Invalid / avoid** in key positions | If testing a UDT key, use frozen and verify DDL |
| `vector<T,N>` (Cassandra 5.0+) | **Do not choose as a key**; verify deployment limits | Keep as data/vector-indexed column; use stable scalar IDs as keys |
| `STATIC` | **No** | `STATIC` applies strictly to **non-key** columns |

**Note on composite types:** `frozen` lets a collection/UDT be stored and compared as a single value, yet **does not legitimize illegal inner types**. For example, embedding `duration` or restricted nested structures still causes key declarations to be rejected. **Test `CREATE TABLE` directly on your target Cassandra version** when using composite types; never infer from `frozen` that "anything can be a key."

In practice, most production tables use keys made of `uuid`, `timeuuid`, `text`, `int`, `bigint`, `timestamp`, `date`, or a few other simple scalars. Frozen composite keys are a **language capability**, not a default recommendation.

## 3. Partition Keys: Three Rules on Identity, Presence, and Distribution

### 3.1. Requires a Present, Stable Value

A partition key must hold a **valid value**, never `NULL` or `UNSET`. In prepared statements, never leave a partition-key bind marker unset expecting Cassandra to pick a row.

~~~cql
-- Invalid: NULL cannot form a partition key.
-- INSERT INTO accounts_by_id (account_id, display_name)
-- VALUES (null, 'Customer A');

-- Valid: supply an appropriate UUID.
INSERT INTO accounts_by_id (account_id, display_name)
VALUES (11111111-1111-4111-8111-111111111111, 'Customer A');
~~~

In an `INSERT`, every `PRIMARY KEY` component must be specified. In `DELETE`/`SELECT`, certain syntax lets you target a **partition** or **clustering range** rather than one row, yet never confuse **omitting clustering predicates to affect multiple rows** with **binding NULL to a key**.

**`0`, `false`, or `1970-01-01` are not NULL.** They are valid CQL values when legitimate in your domain. However, using a sentinel like `0` to mean "unknown ID" funnels unrelated requests into a single partition and overwrites the same key. Handle missing IDs at the ingest or staging layer with a valid controlled key.

### 3.2. Primary Key Values Cannot Be Updated Directly

Writing with the **exact same full primary key** performs an **upsert** in Cassandra (cells are written/overwritten) rather than creating a second row. CQL does not let you turn `account_id = A` into `account_id = B` via `UPDATE SET account_id = B`.

To change a key in business terms, **insert a new row under the new key** and handle the old row plus any related query tables:

~~~cql
-- Assuming the new ID represents the migrated account.
INSERT INTO accounts_by_id (account_id, display_name)
VALUES (22222222-2222-4222-8222-222222222222, 'Customer A');

-- Delete the old row only after verifying the migration.
DELETE FROM accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

These two statements are **not an atomic multi-partition ACID transaction**. Applications need state tracking, reconciliation, rollback/compensation, or LWT as required. Notably, changing a partition key can move data to **different tokens and replicas**.

### 3.3. A Valid Type Can Still Cause Hotspots

Suppose a table uses:

~~~cql
-- Poor distribution if the table will hold millions of events:
-- CREATE TABLE all_events_by_success (
--     succeeded boolean,
--     occurred_at timestamp,
--     event_id uuid,
--     PRIMARY KEY (succeeded, occurred_at, event_id)
-- );
~~~

`boolean` is a valid CQL key type, yet the partition key has **only two common values**: `true` and `false`. All events pile into two massive partitions, causing hotspots, read amplification, and compaction strain.

Even a standalone `tenant_id` can run hot if one tenant emits millions of events per hour. **High cardinality is not the only metric**; evaluate traffic skew and **per-partition size**.

Rule: choose partition keys based on **query patterns + load distribution + expected partition size**, never just because the parser accepts the type.

## 4. Composite Partition Keys: Every Component Type Is a Contract

A composite partition key is built by encoding **all key components** in declaration order.

~~~cql
CREATE TABLE api_events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    response_code smallint,
    service_name text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Explanation:

- `tenant_id uuid` stably identifies the tenant.
- `event_day date` creates a **daily bucket** so a tenant's events do not grow into one unbounded partition.
- `occurred_at timestamp` orders rows chronologically (to the millisecond).
- `event_id uuid` acts as a **tie-breaker**, keeping events with identical `occurred_at` distinct.
- `response_code smallint` and `service_name text` are data columns; they do **not** participate in row identity or token placement.

Query fetching the 50 latest events for a tenant on a given day:

~~~cql
SELECT occurred_at, event_id, response_code, service_name
FROM api_events_by_tenant_day
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Querying the 08:00–09:00 UTC window:

~~~cql
SELECT occurred_at, event_id, response_code
FROM api_events_by_tenant_day
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

This query executes efficiently by design because it supplies the **full partition key** and bounds the first clustering column. Using a half-open `[start, end)` interval prevents double-reading boundary events across adjacent windows.

### 4.1. Day Buckets Require One Consistent Time-Zone Rule

Java can compute:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate eventDayUtc =
    occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
~~~

If writers compute `event_day` in UTC while readers query using a local date (e.g., UTC+07), queries look in a different partition from where the event was written. **`date` has no time zone**; document the bucketing rule explicitly.

Being part of the partition key, `date` **does not subdivide data further** if one tenant sends massive traffic in a single day. When needed, adopt hourly buckets or deterministic sharding and update queries to target the right shards.

### 4.2. Never Add Sharding Blindly

A table with `PRIMARY KEY ((tenant_id, event_day, shard), occurred_at, event_id)` spreads write load for a tenant/day across multiple partitions. Yet to read "all events today ordered newest first," the application must query all relevant shards and **merge results**; Cassandra does not merge and sort across partitions automatically.

Compute `shard` deterministically from the event ID or a defined routing policy. If a retry sends the same event to a different shard, it creates a duplicate row. Sharding **trades read complexity for write scalability**—it is never a free optimization.

## 5. Clustering Keys: Types Must Have Consistent Ordering

Clustering columns sort rows **by each CQL type's comparator** in declaration order. This differs from user-expected UI sorting or locale-specific string collation.

Example:

~~~cql
CREATE TABLE messages_by_room_day (
    room_id uuid,
    message_day date,
    sent_at timestamp,
    message_id uuid,
    sender_id uuid,
    body text,
    PRIMARY KEY ((room_id, message_day), sent_at, message_id)
) WITH CLUSTERING ORDER BY (sent_at DESC, message_id ASC);
~~~

Cassandra can read "newest first" within a partition without sorting thousands of rows in Java:

~~~cql
SELECT sent_at, message_id, sender_id, body
FROM messages_by_room_day
WHERE room_id = 33333333-3333-4333-8333-333333333333
  AND message_day = '2026-11-21'
LIMIT 50;
~~~

### 5.1. Why Is a Tie-Breaker Needed?

Cassandra's `timestamp` stores points in time to the **millisecond**. Two messages can be sent within the same millisecond; if the primary key were only `((room_id, message_day), sent_at)`, two writes could share the **exact same row key**, overwriting one message.

Adding `message_id uuid` ensures two messages with different IDs coexist side by side. Ordering between two messages sharing the **same `sent_at`** then depends on the **UUID comparator**, which does not prove which message occurred first physically.

If the domain requires strict higher-resolution ordering, a **stable source sequence**, `event_epoch_ns bigint`, or a dedicated sequencing design may fit better. You must then define who assigns sequences and how concurrent writers coordinate.

### 5.2. timeuuid vs. UUID v4

- `uuid` is typically used for **stable identifiers**, e.g., `UUID.randomUUID()` (UUID v4 in Java). Never rely on UUID v4 to sort events chronologically.
- `timeuuid` represents UUID **version 1**, carrying a timestamp that Cassandra compares chronologically. It fits clustering keys for timelines ordered **by ID generation time**.
- `timeuuid` does not prove system clocks are accurate, does not establish causal ordering across hosts, and does not replace `occurred_at` when source events arrive late.

An alternative design:

~~~cql
CREATE TABLE events_by_device_day_timeuuid (
    device_id uuid,
    event_day date,
    event_id timeuuid,
    source_time timestamp,
    event_type text,
    PRIMARY KEY ((device_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

In this table, rows sort by the timestamp inside `event_id`, **not** by `source_time` if data arrives late. Choose based on the business question, not merely because `timeuuid` contains the word "time."

### 5.3. text Has Ordering, Not Linguistic Collation

If `city text` is a clustering column, sort order follows CQL's byte-level comparator, **not** Vietnamese or French locale dictionary rules. Diacritics, casing, NFC/NFD, and case folding can produce unexpected ordering.

To look up users by `email`, store an application-**canonicalized** `email_key text`. For locale-sorted lists, build explicit sort keys or sort bounded result sets in the application rather than expecting Cassandra to apply locale collation.

### 5.4. CLUSTERING ORDER BY Does Not Apply to Partition Keys

`WITH CLUSTERING ORDER BY (...)` accepts **clustering columns only**, never partition key columns. Valid example:

~~~cql
WITH CLUSTERING ORDER BY (sent_at DESC, message_id ASC)
~~~

Never try `WITH CLUSTERING ORDER BY (room_id DESC)` hoping to turn token distribution into global ordering across rooms. **Clustering order applies strictly within each partition**.

## 6. Query Rules Directly Govern Key Ordering

Choosing a key's type must go hand in hand with the **`WHERE` patterns** the application executes.

Our example table `messages_by_room_day` has keys:

~~~text
Partition:  room_id + message_day
Clustering: sent_at DESC, message_id ASC
~~~

| Query | Matches Primary Access Path? | Reason |
|---|---|---|
| Room + day, LIMIT 50 | **Yes** | Full partition key provided |
| Room + day + `sent_at` range | **Yes** | Range on first clustering column |
| Room + day + `sent_at` + specific `message_id` | **Yes** | Further refines along clustering key order |
| Only `room_id` | **Incomplete partition key** | Date is part of the partition key |
| Only `day` | **Incomplete partition key** | Missing `room_id` |
| Only `message_id` | **No** | `message_id` is a trailing clustering column after `sent_at` and lacks partition key |
| All rooms by newest `sent_at` | **No** via this table | No global cluster-wide sort order |

In Cassandra, conditions on clustering columns generally follow **key prefix order**; you cannot skip `sent_at` arbitrarily and expect `WHERE message_id = ...` to run efficiently. Certain `IN` clauses, indexes, or filter features vary by version, yet should never serve as shortcuts replacing query-driven modeling.

When you need "look up one message by `message_id` alone," add a dedicated lookup table:

~~~cql
CREATE TABLE message_locator_by_id (
    message_id uuid PRIMARY KEY,
    room_id uuid,
    message_day date,
    sent_at timestamp
);
~~~

The application queries the locator and uses `(room_id, message_day, sent_at, message_id)` to fetch the full message from the timeline table—or maintains a `messages_by_id` table per read pattern. **Writing multiple tables requires synchronization, idempotency, and reconciliation**, because Cassandra does not update denormalized tables atomically like a multi-partition ACID transaction.

## 7. NULL, UNSET, and Non-Missing Keys

Regular columns can be unwritten, deleted with NULL/DELETE, or skipped via UNSET. **Keys are different**: Cassandra requires valid keys to identify a row/partition.

~~~cql
-- Do not insert a row without account_id.
-- INSERT INTO accounts_by_id (display_name) VALUES ('No ID');

-- Do not bind NULL for account_id.
-- INSERT INTO accounts_by_id (account_id, display_name)
-- VALUES (null, 'Invalid');
~~~

Java-layer rules:

| Request State | Key Column | Regular Data Column |
|---|---|---|
| Absent | **Reject or obtain ID from valid flow** | Can be **UNSET/omitted** in PATCH |
| Explicit NULL | **Rejected** | Can mean **delete** and create a tombstone |
| Valid value | Bind accurately, keep stable | Bind/update |
| Synthetic default value | Only when it is a true business ID | Allowed as default if contract permits |

If a user lacks a `tenant_id`, never assign a hardcoded `"unknown tenant"` UUID across requests. That breaks tenant isolation and funnels traffic into one hotspot partition. Handle missing keys at the **API boundary** or staging pipeline with a valid, controlled identifier.

**Exception to understand properly:** `DELETE FROM table WHERE partition_key = ?` can delete an entire partition without naming clustering columns. That is a **different mutation scope**, not permission for `INSERT` key components to be NULL.

## 8. Never Use counter, duration, or Non-Frozen Collections in PRIMARY KEY

### 8.1. Counter

`counter` is for **incrementing/decrementing** integer counts under counter semantics, not for identifying rows.

~~~cql
CREATE TABLE requests_count_by_tenant_day (
    tenant_id uuid,
    request_day date,
    total counter,
    PRIMARY KEY ((tenant_id, request_day))
);
~~~

Here `total` is a **non-key** counter column. Counter tables impose strict rules: **all non-PRIMARY-KEY columns must be counters**—you cannot mix in regular columns like `updated_at timestamp`. Counters do not support TTL like regular columns, and retrying an increment after a timeout can **over-count**.

~~~cql
UPDATE requests_count_by_tenant_day
SET total = total + 1
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND request_day = '2026-11-21';
~~~

To query by day and tenant, put date and ID in the key; never put `total` in the partition key just to read counts.

### 8.2. Duration

`duration` stores **months, days, and nanoseconds**; it has no unique ordering independent of a calendar anchor. That is why Cassandra **forbids `duration` in PRIMARY KEY**.

~~~cql
-- Invalid schema:
-- CREATE TABLE billing_tasks_wrong (
--     interval duration PRIMARY KEY,
--     task_name text
-- );
~~~

Instead, compute the **due timestamp**:

~~~cql
CREATE TABLE billing_tasks_by_day (
    due_day date,
    due_at timestamp,
    task_id uuid,
    billing_interval duration,
    plan_code text,
    PRIMARY KEY ((due_day), due_at, task_id)
) WITH CLUSTERING ORDER BY (due_at ASC, task_id ASC);
~~~

`billing_interval duration` is **policy data**, while `due_day/date`, `due_at/timestamp`, and `task_id/uuid` form the **access path and identity**. If a single day holds too many tasks, add sharding or hourly buckets rather than stuffing unbounded tasks into one partition.

### 8.3. Non-Frozen vs. Frozen Collections

Regular `list`, `set`, and `map` are **multi-cell collections** supporting per-element/entry mutations in CQL. They are **not** valid key components.

Conversely, Cassandra's `CREATE TABLE` documentation notes that **primary keys may include frozen collections**:

~~~cql
-- CQL capability, NOT a production recommendation:
CREATE TABLE features_by_frozen_tagset (
    tagset frozen<set<text>> PRIMARY KEY,
    description text
);
~~~

Such a key introduces several problems:

- Adding or removing one tag **changes the entire key value**; you cannot mutate the key via UPDATE.
- Large sets make keys bulky, inflating network transfer and comparison costs.
- Uncanonicalized text representations create different keys for the same logical set.
- Querying "all rows containing tag X" is not enabled by making `tagset` the partition key; you still need the **exact whole set** to locate a partition.

Therefore, prefer `feature_set_id uuid` or a stable canonicalized key, keeping `tags set<text>` as a data column. To search by tag, build a tag lookup table or evaluate an appropriate index.

## 9. Tuple, UDT, and vector: Type Capability Does Not Dictate Key Design

### 9.1. Tuples Are Always Frozen

A `tuple<int, text>` has fixed positions and is **always frozen**; Cassandra treats it as a monolithic value. Tuple types can satisfy key constraints when all component types are valid, yet using **two separate scalar columns** usually makes schema validation, evolution, and partial-component queries much clearer.

Example:

~~~cql
-- Better than a tuple when filtering clearly by country and city:
CREATE TABLE offices_by_country_city (
    country_code ascii,
    city_code text,
    office_id uuid,
    office_name text,
    PRIMARY KEY ((country_code, city_code), office_id)
);
~~~

Packing `country_code, city_code` into a `tuple<ascii,text>` partition key loses per-column schema representation and makes validation and migrations harder to follow.

### 9.2. Frozen UDTs

A UDT with named fields can be marked **frozen**, treating it as a single value permitted in key positions where supported by the version. Still, an address makes a poor identifier:

- Updating a postal code or diacritics alters the key.
- Two customers can share the same address.
- UDT schema changes require tight control over codecs, field order, and migrations.
- Queries like `city = ?` are not automatically optimized when `city` is buried inside a frozen UDT key.

Instead, use `customer_id uuid` as the key and keep `shipping_address frozen<address>` as a **data snapshot**. A **non-frozen UDT** supports field-level mutations and is not meant for partition/clustering keys.

### 9.3. Vectors by Cassandra Version

`vector<T, N>` arrived in Apache Cassandra **5.0** to store fixed-dimension sequences. With `vector<float,N>` and SAI, clusters support **ANN similarity search**.

Nearest-vector search is completely separate from partition-key lookups:

~~~cql
-- Example with clear separation of roles:
CREATE TABLE embeddings_by_chunk_id (
    chunk_id uuid PRIMARY KEY,
    model_version text,
    embedding vector<float, 3>
);
~~~

`chunk_id` provides stable identity; `embedding` is the indexed/matched payload. **Never use an embedding as a business identifier or expect clustering by similarity**; ANN ordering is not `CLUSTERING ORDER BY`. Check exact vector/key restrictions for your version/distribution, though the reliable standard pattern is **scalar key + vector column/index**.

On Cassandra 4.x clusters, `vector<float,3>` is unsupported; never copy Cassandra 5.0 schemas without checking `release_version` and driver support.

## 10. Canonicalizing Key Data: Identical Bytes Equal Identical Intent

### 10.1. text/varchar and Unicode

Cassandra stores `text`/`varchar` as UTF-8 Unicode; it **does not normalize automatically**:

- `"Alice"` and `"alice"` are distinct keys under standard comparison.
- NFC `"café"` and NFD `"café"` render identically yet have different bytes.
- Emails have local-part and domain rules; never blindly call `toLowerCase()` on every email without an explicit business policy.
- `ascii` suits strictly ASCII domains (country codes, protocol codes), not accented full names.

If queries need "find user by case-insensitive username," store a **canonical username key** generated identically across every service:

~~~cql
CREATE TABLE users_by_username_key (
    username_key text PRIMARY KEY,
    user_id uuid,
    display_username text,
    created_at timestamp
);
~~~

`username_key` serves lookups, while `display_username` preserves original formatting for display. Define normalization, case folding, allowed characters, length limits, and confusable handling. If usernames must be **unique**, use conditional writes/coordination rather than relying on UUID generation alone.

### 10.2. Numbers and Times in Keys

- **Money**: use minor-unit `bigint` or `decimal` for exact calculations, yet **never use a monetary amount as a transaction ID**; prices change and collide.
- **`float`/`double`**: precision error, `NaN`/infinity, `-0.0`, and comparison edge cases make keys brittle; avoid in business keys.
- **`timestamp`**: stops at **milliseconds**, requiring a secondary UUID/sequence in clustering keys for high-frequency events.
- **`date`**: calendar date without time zone; derive daily buckets consistently in UTC or one business time zone.
- **`inet`**: represents one IP, not a hostname, CIDR subnet, or client identity; many users share IPs behind NAT/proxies.

Even allowed key types require **domain validation** and cross-client serialization/deserialization testing.

## 11. PRIMARY KEY, Uniqueness, and Conditional Writes

Cassandra guarantees **one `PRIMARY KEY` tuple identifies a unique row location within a table**. However, regular CQL `INSERT` has **upsert** semantics—it does not reject existing keys like an SQL `UNIQUE` constraint.

Example:

~~~cql
INSERT INTO users_by_username_key (
    username_key, user_id, display_username, created_at
) VALUES (
    'nguyenha',
    44444444-4444-4444-8444-444444444444,
    'NguyenHa',
    '2026-11-21T08:00:00Z'
) IF NOT EXISTS;
~~~

`IF NOT EXISTS` is a **lightweight transaction (LWT)** conditional write supported by Cassandra. It helps **claim an unclaimed `username_key`**. Applications must inspect the **`[applied]`** flag in the result and handle `false`, timeouts, and racing writes.

**LWT does not enforce cluster-wide uniqueness on regular columns.** For example, if `users_by_id` has a regular column `email text`, `IF NOT EXISTS` on `user_id` will not stop another user from claiming the same email. You need a **canonical-email lookup/reservation table** plus cross-table write/reconciliation logic.

Moreover, Cassandra `PRIMARY KEY` does not provide:

- `FOREIGN KEY` constraints across tables;
- `UNIQUE` constraints on arbitrary non-key columns;
- General relational SQL joins;
- Global auto-incrementing sequences;
- Cross-partition / multi-table ACID transactions.

Other business invariants must be enforced via **table design, application validation, targeted LWTs, and data synchronization workflows**.

## 12. Java Driver 4.x: Bind the Right Types and Keep Keys Stable on Retries

Common key type mappings in Java Driver 4.x:

| CQL | Java | Bind Setter | Read Getter |
|---|---|---|---|
| `uuid`, `timeuuid` | `UUID` | `setUuid` | `getUuid` |
| `text`, `varchar`, `ascii` | `String` | `setString` | `getString` |
| `int`, `smallint`, `tinyint` | `int`, `short`, `byte` | `setInt`, `setShort`, `setByte` | `getInt`, `getShort`, `getByte` |
| `bigint` | `long` | `setLong` | `getLong` |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` |
| `timestamp` | `Instant` | `setInstant` | `getInstant` |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` |

### 12.1. Writing to a Tenant/Day Table

Assume `session` is a `CqlSession` configured with cluster and keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Initialized and managed outside this example.

UUID tenantId = UUID.fromString("99999999-9999-4999-8999-999999999999");
UUID eventId = UUID.randomUUID(); // Generated once per event.
Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate eventDay = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

PreparedStatement insert = session.prepare(
    "INSERT INTO api_events_by_tenant_day "
  + "(tenant_id, event_day, occurred_at, event_id, "
  + " response_code, service_name) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, eventDay)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setShort(4, (short) 200)
    .setString(5, "checkout")
    .build();

session.execute(bound);

// On retry after timeout, reuse the exact same tenantId,
// eventDay, occurredAt, and eventId.
~~~

If the application **generates a fresh UUID on every retry**, one event becomes two rows because the **primary key changed**. If the application recomputes the day bucket from `Instant.now()` on each retry, the same event can land in a new partition after midnight. Keep the entire **event envelope**—both keys and source data—immutable across retries.

### 12.2. Exact-Key Read

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement find = session.prepare(
    "SELECT occurred_at, event_id, response_code "
  + "FROM api_events_by_tenant_day "
  + "WHERE tenant_id = ? AND event_day = ? "
  + "AND occurred_at = ? AND event_id = ?");

Row row = session.execute(
    find.bind(tenantId, eventDay, occurredAt, eventId)
).one();

if (row != null) {
    UUID storedEventId = row.getUuid("event_id");
    int status = row.getShort("response_code");
}
~~~

The table is partitioned by `tenant_id + event_day` and clustered by `occurred_at + event_id`. Because the query supplies every component, it hits the exact row. If only `eventId` is known, maintain a **separate locator/lookup table** built for that access path.

### 12.3. Validating Keys Before Binding

Principle example:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

static void validateEventKey(
    UUID tenantId, LocalDate eventDay,
    Instant occurredAt, UUID eventId
) {
    Objects.requireNonNull(tenantId, "tenantId");
    Objects.requireNonNull(eventDay, "eventDay");
    Objects.requireNonNull(occurredAt, "occurredAt");
    Objects.requireNonNull(eventId, "eventId");
}
~~~

Never use `UNSET` to "skip" `tenant_id` or `event_id` in a mutation. For regular non-key columns, PATCH may use UNSET to preserve or NULL to delete; **key requirements do not vanish just because the driver exposes `unset()`**.

### 12.4. Keys Must Be Encoded Identically Across All Clients

If Java, Go, and Python share a keyspace:

- Align CQL types and codecs against the schema.
- Align `text`/email/username normalization rules.
- Align UTC conventions and `Instant`-to-bucket derivation.
- Keep monetary units, IDs, and code formats within identical value domains.
- For `blob` or frozen types, control exact byte layout/canonicalization.
- Test key duplicates and retries across driver versions.

Two keys "looking alike" in logs do not guarantee identical serialized bytes if clients differ in normalization or data formatting.

## 13. Replication, Consistency, Compaction, and Repair: Consequences of Key Type Choices

### 13.1. Tokens and Replication

The partition key is **encoded and hashed** to yield a token; the replication strategy places replicas accordingly. Key types and value distributions therefore directly shape **partition counts** and token-range load.

- **Well-distributed UUIDs** spread writes evenly, though they do not prevent one heavy tenant from saturating its partition.
- **Standalone boolean keys** yield only two values, creating tiny partition counts and severe hotspots.
- **Huge text keys** bloat requests, caches, and comparisons unnecessarily.
- **Frozen collection keys** turn bulky structures into IDs, creating oversized keys.
- **Daily buckets** bound partitions over time, yet extreme daily volume still requires hourly buckets or sharding.

### 13.2. Clustering, Tombstones, and Compaction

Clustering keys organize rows inside a partition so Cassandra can slice ranges via `WHERE` and `LIMIT`. Still, a single partition can grow huge, and deletes/TTLs create tombstones scanned during reads.

**Compaction** merges SSTables and clears eligible tombstones; it **never fixes a broken key design**. If `partition_key = succeeded boolean` creates two giant partitions, compaction will not split them into thousands of small partitions.

Changing a primary key usually means **migrating to a new table** with planned read/write cutover and backfills, not an ad-hoc `ALTER TABLE`.

### 13.3. Repair and Business Data Divergence

**Repair** converges replica state for written cells/mutations. It does **not**:

- Merge two rows with **different `event_id` values** created by a non-idempotent retry.
- Move a mis-bucketed event from yesterday's partition to today's partition.
- Normalize Unicode emails written as two distinct keys.
- Automatically synchronize unique identifiers across **two tables**.

Consistency levels like `LOCAL_QUORUM` strengthen read/write quorum guarantees under specific failure assumptions, yet they **never replace idempotency or business key constraints**.

### 13.4. Security and Access Control

A partition key like `tenant_id uuid` is a **query key**, not an automatic security boundary. Services must verify the caller is authorized for that tenant rather than blindly passing any client-supplied UUID into `WHERE`.

When using emails, phone numbers, or IP addresses as keys, weigh **PII exposure** in logs, metrics, URLs, and traces. Consider surrogate IDs with access-controlled lookup tables; design encryption/hashing carefully so lookups and privacy deletions still work.

## 14. Migrating When Key Types or Components Must Change

A populated table usually **cannot simply be altered** from `PRIMARY KEY (tenant_id, event_id)` to `PRIMARY KEY ((tenant_id, event_day), event_id)`. Both data placement and row layout change. Likewise, changing `event_id text` to `uuid` in a primary key changes binary encoding and semantics.

A safe migration workflow:

1. **Audit actual queries**: which queries must be served, and which columns appear in `WHERE`/`ORDER BY`?
2. **Design the new key**: pick types, canonicalization, partition buckets, and clustering order.
3. **Create the new table** with a clean schema; never mutate keys in place on the old table.
4. **Add compatible writes**, such as dual-writing with stable IDs and reconciliation checks.
5. **Backfill by known keys** using rate-limited, checkpointed, retryable jobs instead of unthrottled cluster scans/writes.
6. **Verify row counts, content hashes, and query cases**, including Unicode, time zones, duplicate timestamps, nulls, and late arrivals.
7. **Cut over reads gradually**, tracking latency, errors, partition fullness, and missing records.
8. **Stop old writes and decommission** per retention, backup, and rollback plans once verified.

**Never treat changing a key type as trivial formatting.** Switching `text` to `uuid` or float to `bigint` can affect IDs across every row and referencing table. With concurrent writers, coordinate backfill windows and dual-writes carefully.

## 15. Typical Design Mistakes Table

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing `PRIMARY KEY (a,b)` with `PRIMARY KEY ((a,b))` | Completely different token placement and query paths | Specify partition vs. clustering parentheses explicitly |
| Using a standalone `boolean` partition key for large logs | Only a couple of giant partitions | Bucket by tenant/time/shard |
| Using `timestamp` alone as clustering key for high-rate events | Same-millisecond events overwrite one row | Add a stable ID tie-breaker |
| Using UUID v4 in clustering expecting time order | No chronological ordering | Use `timeuuid` v1 or `timestamp + uuid` |
| Putting `counter` in PRIMARY KEY | DDL rejected | Keep counters as regular columns; use scalars in keys |
| Putting `duration` in PRIMARY KEY | Lacks total ordering; DDL rejected | Store duration as policy, `due_at timestamp` as key |
| Using non-frozen `map/list/set` as key | Invalid key structure | Use frozen only if truly needed; prefer scalar IDs |
| Using large frozen UDT/collection as key | Brittle, bulky keys | Use surrogate IDs; keep UDT/collections as values |
| Putting `STATIC` in primary key | Invalid DDL | `STATIC` is strictly for non-key columns |
| Binding `NULL`/`UNSET` to a partition key | No key to locate row | Validate keys before executing |
| Regenerating `uuid()` or `now()` on every INSERT retry | Creates duplicate business rows | Generate ID once and reuse it |
| Using text keys without Unicode canonicalization | Visually identical values create separate keys | Enforce consistent NFC/case policy |
| Using `float` for money/IDs | Rounding error and brittle equality | Use `bigint`/`UUID`/`decimal` with clear contracts |
| Querying only `event_id` on a tenant/day partitioned table | Missing partition key | Add a lookup/locator table by ID |
| Assuming `LOCAL_QUORUM` enforces cross-table uniqueness | Denormalized tables can still diverge | Use targeted LWTs, idempotency, and reconciliation |
| Trying to change key types with direct `ALTER TABLE` | Incompatible with storage/token layout | New table + backfill + cutover |

## 16. Practice Exercises

### Exercise 1 — Reading PRIMARY KEY Correctly

Given:

~~~cql
CREATE TABLE clicks (
    tenant_id uuid,
    click_day date,
    clicked_at timestamp,
    click_id uuid,
    PRIMARY KEY (tenant_id, click_day, clicked_at, click_id)
);
~~~

**Question:** what is the partition key? Are tenant and day bucketed together in the partition key?

**Answer:** only **`tenant_id`** is the partition key; `click_day`, `clicked_at`, and `click_id` are clustering columns. To bucket by tenant and day, change it to `PRIMARY KEY ((tenant_id, click_day), clicked_at, click_id)`.

### Exercise 2 — Which Key Types Are Invalid?

Review the abbreviated declarations:

~~~cql
-- A: Invalid
-- CREATE TABLE a (k duration PRIMARY KEY, value text);

-- B: Invalid
-- CREATE TABLE b (k counter PRIMARY KEY);

-- C: Valid CQL syntax, questionable design
-- CREATE TABLE c (k frozen<set<text>> PRIMARY KEY, value text);

-- D: Common and well suited for ID lookups
CREATE TABLE d (
    k uuid PRIMARY KEY,
    value text
);
~~~

**Answer:** A and B are forbidden by type rules; C is syntactically accepted as a frozen collection yet generally poor as a business identifier; D is a standard, sound choice.

### Exercise 3 — Duplicate Timestamps

A table has `PRIMARY KEY ((device_id, day), occurred_at)`, and two events on the same device/day share the exact same `occurred_at` to the millisecond.

**Question:** will Cassandra store two separate rows?

**Answer:** no, because they share the entire primary key; mutations overwrite/upsert the same row. Add `event_id uuid` as a secondary clustering key, or use an appropriate source-ordering design.

### Exercise 4 — Querying the Wrong Access Path

`api_events_by_tenant_day` has `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)`.

**Question:** is `SELECT * FROM ... WHERE event_id = ?` optimal?

**Answer:** no. It lacks the **entire partition key**, and `event_id` is a clustering column after `occurred_at`. You need a lookup/table keyed by `event_id`, or must supply the full keys.

### Exercise 5 — Cardinality and Hotspots

An app uses `client_ip inet` as a single partition key storing all requests. Most users sit behind one shared reverse proxy.

**Question:** why does `inet` still produce poor distribution?

**Answer:** a valid type does not create distinct partition-key values; a shared proxy/NAT IP concentrates massive request volume into one partition. Key by tenant/service/bucket and/or sharding matching queries, and extract source IPs only from trusted proxy chains.

### Exercise 6 — Day Bucket Shift Across Retries

A worker writes an event at `2026-11-20T18:30:00Z` using UTC `event_day`, then retries after midnight Vietnam time using `LocalDate.now()`.

**Question:** what can happen?

**Answer:** the same event can land in two different daily partitions, creating duplicates or missing query results. Compute the bucket once from the **chosen source instant** and agreed time zone; keep IDs and keys constant across retries.

### Exercise 7 — Unique Username Design

Does `users_by_id(user_id uuid PRIMARY KEY, username text)` guarantee no two users share the same `username`?

**Answer:** no. The unique key is `user_id`. To claim unique usernames, use a canonical `username_key` in a username lookup table with conditional writes/coordination to reserve it, then synchronize with the ID-keyed table.

## 17. Checklist for Reviewing Key Data Types

- [ ] Have **partition key** and **clustering columns** been clearly separated, especially parentheses in composite partition keys?
- [ ] Is every key component type supported by your **actual Cassandra version**?
- [ ] Are **counter**, **duration**, non-frozen collections, and `STATIC` excluded from PRIMARY KEY?
- [ ] If using a frozen collection/UDT/tuple, have all inner types, sizes, and justification for a composite key been verified?
- [ ] Are all key components guaranteed non-NULL/non-UNSET on write, avoiding arbitrary `"unknown"` sentinel values?
- [ ] Are key values generated/canonicalized **once and kept stable** across retries?
- [ ] Does the partition key have healthy **cardinality and load distribution**, free of boolean/status/proxy-IP hotspots?
- [ ] Have rows/bytes per partition, throughput, and retention been measured to size buckets/shards?
- [ ] Do critical queries supply the full partition key and valid clustering prefixes/ranges?
- [ ] Do clustering columns sort by the right semantics: source time, `timeuuid`, or sequence?
- [ ] Is there a tie-breaker when timestamps cannot distinguish same-millisecond events?
- [ ] Do `text`, emails, usernames, Unicode, and IP addresses enforce consistent **canonicalization**?
- [ ] Are `float`/`double` avoided for identifiers and money, with explicit unit contracts?
- [ ] When uniqueness is required on regular columns, are lookup tables, LWTs, and reconciliation designed rather than misusing another table's PRIMARY KEY?
- [ ] Does the Java Driver bind exact types and validate keys before execution?
- [ ] Is there a migration plan (new table, backfill, dual-write, cutover) if keys or key types must change?
- [ ] Have replication, consistency, tombstones, compaction, repair, and PII controls been addressed?

## References

- [Apache Cassandra — Data Definition: Primary key, partition and clustering columns](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — CREATE TABLE: PRIMARY KEY constraints and frozen collections](https://cassandra.apache.org/doc/latest/cassandra/reference/cql-commands/create-table.html).
- [Apache Cassandra — CQL Data Types: counter, duration, collections, UDT, tuple](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra — Vector data type (Cassandra 5.0)](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html).
- [Apache Cassandra Java Driver 4.x — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

**Remember:** a "valid" CQL type **is not automatically a good key type**. `PRIMARY KEY` defines **row identity**, **partition key** governs **token and replica placement**, and **clustering columns** govern **ordering within a partition**. `counter` and `duration` cannot serve as keys; non-frozen collections are unsuitable as keys, and frozen collections/UDTs are possible yet require careful trade-offs. Resilient design picks **small, stable, canonicalizable, query-aligned keys**, enforces retry control, and benchmarks real workloads on distributed Cassandra.
