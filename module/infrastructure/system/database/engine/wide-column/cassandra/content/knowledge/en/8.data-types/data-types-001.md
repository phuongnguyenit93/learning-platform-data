# Choosing Apache Cassandra Data Types by Value Domain, Precision, and Access Pattern

Apache Cassandra is a distributed database built on the **wide-column** model. Data is distributed by the **partition key**, sorted within a partition by **clustering columns**, stored as cells, and synchronized across replicas according to replication and consistency settings. Therefore, a CQL data type does not merely determine which values can be stored: it also affects record size, key comparison, update operations, query capabilities, and long-term storage cost.

This lesson belongs to the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The focus is on choosing data types for query-driven tables, clarifying numeric and temporal precision, and connecting those choices to CQL and Java. Concepts such as compaction, repair, and consistency levels remain important for Cassandra operations, but they cannot replace choosing the right value domain and key model from the start.

## 1. Three Questions to Answer Before Choosing a Type

1. **What is the value domain?** Is the value an identifier, a measurement, money, a point in time, an IP address, a set of labels, or a nested entity? Are there leading zeros, Unicode characters, negative numbers, very large values, or nested structures?
2. **How much precision is required?** Is floating-point approximation acceptable? Does temporal data require day, millisecond, or nanosecond resolution? Do you need to preserve the original time zone or distinguish when an event occurred from when it was written to Cassandra?
3. **What are the read and write access patterns?** Will queries look up by identifier, filter by a time range within a partition, look up collection elements, or update individual attributes? Will the data grow unboundedly? Will write operations be retried?

Only after answering these should you choose a type. For example, a string `"001234"` representing a customer code requires **text**; only if it is a quantity subject to arithmetic should you consider a numeric type. A sensor reading can use **double**, whereas a payment amount requires **decimal** or minor units stored as **bigint**.

## 2. Quick Selection Map of CQL Types

| Data Domain / Requirement | Typically Suitable Type | Things to Check Before Finalizing |
|---|---|---|
| Unicode text, Vietnamese names, business codes | **text** (or **varchar**, equivalent alias) | Preserving leading zeros in codes; string length and normalization |
| Strings containing only ASCII characters | **ascii** | Do not use for accented characters or Unicode content |
| True/false | **boolean** | Distinguish unknown values from false in business logic |
| Small integers | **tinyint**, **smallint**, **int** | Value bounds and risk of future growth exceeding the range |
| Counters/large integers, money in minor units | **bigint** | Unit convention required; check for 64-bit overflow |
| Arbitrarily large integers | **varint** | Representation/computation overhead and Java mapping |
| Exact decimal numbers | **decimal** | Scale, rounding mode, and display formatting conventions |
| Measurements where approximation is acceptable | **float**, **double** | IEEE 754 precision error and actual precision needed |
| Technical identifiers | **uuid** | Generate once and keep stable across retries |
| Time-ordered identifiers | **timeuuid** | Compatibility with UUID version 1 and ID generation strategy |
| Absolute points in time | **timestamp** | Stores milliseconds since epoch; manage time zones in the application |
| Date only / time of day only | **date** / **time** | Do not use as a full point in time |
| Calendar durations | **duration** | Months/days/nanoseconds do not map to a fixed number of seconds |
| IPv4/IPv6 addresses | **inet** | Does not replace hostnames or CIDR ranges |
| Small binary data | **blob** | Consider storing large payloads outside Cassandra |
| Ordered lists / unique sets / key-value mappings | **list**, **set**, **map** | Use only for small, bounded collections |
| Structured attribute groups | **UDT**, **tuple** | Need to update individual fields or the entire value? |
| Fixed-dimension embeddings, Cassandra 5.0+ | **vector<float, n>** | Cluster version, vector queries, and float precision |

These are starting choices. There is no rule that "smaller types are always better": data domains can expand, code must align cleanly with the Java driver, and query constraints usually matter far more than saving a few bytes per value.

## 3. Value Domains and Precision

### 3.1. Identifiers vs. Quantities

An order code `"00007342"` has no arithmetic meaning for addition or subtraction. If stored as an **int**, leading zeros are lost; if the code later includes letters, the schema will have to change. Store business codes as **text** and enforce formatting at the application layer.

Use **uuid** when you want a 128-bit binary identifier that can be generated independently across nodes. Use **timeuuid** when you need a UUID version 1 carrying temporal information, often used as a clustering key for event streams. **timeuuid** is not equivalent to **timestamp**: timestamp represents a point in time, whereas timeuuid is an identifier that embeds time information. If you must preserve event ordering by the timestamp provided by the originating device, store an additional business **timestamp**; a timeuuid generated upon ingestion cannot replace the time the event actually occurred.

Phone numbers, postal codes, SKUs, and card numbers containing special characters are all **text**, even if they appear to consist only of digits. For Vietnamese text, choose **text**, not **ascii**.

### 3.2. Integers: Choosing for Future Bounds

Common signed integer types:

| Type | Size / Value Range |
|---|---|
| **tinyint** | 8-bit: −128 to 127 |
| **smallint** | 16-bit: −32,768 to 32,767 |
| **int** | 32-bit: −2,147,483,648 to 2,147,483,647 |
| **bigint** | 64-bit: −2^63 to 2^63 − 1 |
| **varint** | Variable-length integer, can exceed 64 bits |

For example: **smallint** may suffice for scores in the range −100 to 100; **bigint** is more reasonable for total bytes transferred or monetary amounts in minor units (such as VND or cents) where long-term values can grow large. Do not pick **tinyint** just because there are currently only 30 statuses if the catalog could expand to several hundred values.

**varint** is intended for integer domains that genuinely do not fit in 64 bits, not as the default choice for all integers. Java typically reads and writes varint as **BigInteger** and bigint as **long**. Changing a column or key type once in production may require creating a new table and migrating data.

### 3.3. Money and Measurements: decimal vs. float/double

**float** (32-bit) and **double** (64-bit) use IEEE 754 binary floating-point representation. They fit temperatures, probabilities, scientific quantities, or embeddings where approximate error is acceptable. **double** is generally more precise than float, but neither can represent every decimal fraction exactly.

~~~java
double observed = 0.1 + 0.2;
// observed is typically 0.30000000000000004

BigDecimal exact = new BigDecimal("0.1")
    .add(new BigDecimal("0.2"));
// exact is 0.3
~~~

For money, there are two common strategies:

- **decimal** stores exact decimal values, such as 19.90; Java uses **BigDecimal**. Define the scale, rounding mode, and rounding rules at business boundaries.
- **bigint** stores the number of **minor units**, such as 1,990 cents for 19.90 USD. You must store or know the currency and unit because currencies have different numbers of decimal places; check for 64-bit overflow when summing.

~~~cql
CREATE TABLE invoice_amounts_by_id (
    invoice_id uuid PRIMARY KEY,
    currency text,
    amount_exact decimal,
    amount_minor bigint
);

INSERT INTO invoice_amounts_by_id
    (invoice_id, currency, amount_exact, amount_minor)
VALUES
    (11111111-1111-4111-8111-111111111111, 'USD', 19.90, 1990);
~~~

The two columns in the example are for comparing strategies; in real designs, you typically choose **one monetary representation as the source of truth**, avoiding parallel writes of two values that could drift apart. Do not use **double** for monetary calculations, product prices, or balances requiring exact reconciliation.

### 3.4. Time: Distinguishing date, time, timestamp, timeuuid, and duration

- **date**: a calendar date without time of day or time zone; suitable for birth dates, billing cycle cutoff dates, and **bucket_day**.
- **time**: time of day with nanosecond resolution, without date or time zone; suitable for business hours.
- **timestamp**: an absolute point in time, represented at millisecond resolution since the Unix epoch. Cassandra does not preserve the original time zone name; when ingesting or displaying, the application must apply time zone conventions.
- **timeuuid**: an identifier with a time component (UUID version 1) that can serve as a time-ordered clustering key.
- **duration**: a span consisting of months, days, and nanoseconds. A month is not always 30 days; this type does not replace fixed-length duration measurements in milliseconds or nanoseconds.

~~~cql
CREATE TABLE events_by_user (
    user_id uuid,
    event_id timeuuid,
    occurred_at timestamp,
    action text,
    PRIMARY KEY ((user_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

INSERT INTO events_by_user (user_id, event_id, occurred_at, action)
VALUES (
    22222222-2222-4222-8222-222222222222,
    now(),
    '2026-11-21T01:15:00Z',
    'login'
);
~~~

The **now()** function generates a new timeuuid at execution time. If the same event is rewritten with another statement generating a new **now()**, the key may differ and create duplicate rows. For idempotent ingestion, generate the event ID once before retrying and reuse that ID. When events can arrive late or with clock skew, explicitly decide whether display order is based on the source's **occurred_at** or on the ingestion time.

**Important note:** a business column's CQL **timestamp** value is not the *write timestamp* Cassandra uses for last-write-wins conflict resolution. Values written with **USING TIMESTAMP** and returned by **WRITETIME()** pertain to write metadata in microseconds, whereas CQL **timestamp** stores points in time to the millisecond. Confusing these two concepts can lead to incorrect update logic.

## 4. Data Types Tied to the Query Model

Cassandra is optimized for queries with a known partition key and, when needed, conditions on clustering columns in the appropriate order. Choosing good types cannot save a table whose partition key does not match the query.

Suppose a payment system needs: "Fetch the 50 most recent payments for a customer on a given day, optionally filtered by a time range." A suitable table:

~~~cql
CREATE TABLE payments_by_customer_day (
    customer_id uuid,
    bucket_day date,
    occurred_at timestamp,
    payment_id uuid,
    amount_minor bigint,
    currency text,
    state text,
    PRIMARY KEY ((customer_id, bucket_day), occurred_at, payment_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, payment_id ASC);
~~~

Rationale for each choice:

- **customer_id uuid** forms the first part of the partition key because queries specify a customer; **bucket_day date** bounds partition growth by day. The partition definition consists of both columns together, not two separate partitions.
- **occurred_at timestamp** is a clustering column, supporting range queries and returning results from newest to oldest within a day. **payment_id uuid** disambiguates transactions occurring within the same millisecond.
- **amount_minor bigint** provides exact integer amounts in minor units; **currency text** carries the unit convention; **state text** is suitable when statuses are business codes that may expand over time.
- The primary key defines row uniqueness within a partition; to prevent duplicate writes, reuse the exact same key tuple on retries.

~~~cql
SELECT occurred_at, payment_id, amount_minor, currency, state
FROM payments_by_customer_day
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND bucket_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T01:00:00Z'
  AND occurred_at <  '2026-11-21T02:00:00Z'
LIMIT 50;
~~~

This query provides the **full partition key** and constrains a **clustering column**. If the business requires "finding all payments by state across all customers," you need to design an appropriate access path (such as another query-driven table, or an index evaluated against the Cassandra version and actual workload); changing **state** from text to another type will not make a cluster-wide query efficient.

**Partition size and width:** bucketing by day is only an example. Customers with millions of events per day may need hourly buckets or additional sharding, while low-traffic workloads can use weekly or monthly buckets. Choose based on row count and size per partition, throughput, retention, and query patterns. The **date** type of the bucket does not by itself limit partition size.

**Keys and ordering:** the partition key is hashed to determine data placement; clustering columns determine sort order within a partition. Choosing **uuid** vs. **text** for IDs must follow the value domain and integration contract, rather than assuming that lexicographical string order will sort partitions chronologically. Do not use **float/double** as keys for values requiring exact equality comparison, because precision differences can turn seemingly identical values into distinct keys.

## 5. Collections, UDTs, and Tuples: Flexible but Must Be Bounded

### 5.1. List, Set, and Map Have Different Characteristics

| Type | Use When | Risks If Misused |
|---|---|---|
| **list<T>** | A few ordered elements that may contain duplicates | Positional updates / frequent mutations, unbounded list growth |
| **set<T>** | A few unique labels where insertion order is not needed | Unsuitable for storing event history or occurrence counts |
| **map<K,V>** | Small set of attributes with known or bounded keys | Unsuitable as a sub-table with millions of keys |

~~~cql
CREATE TYPE customer_address (
    line1 text,
    city text,
    postal_code text
);

CREATE TABLE profiles_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    labels set<text>,
    preferences map<text, text>,
    shipping_address frozen<customer_address>
);
~~~

**set** does not preserve the insertion order of labels; **map** is not equivalent to an indexed table for fast filtering on arbitrary values. CQL supports mutating elements/entries of non-frozen collections, but continuous additions/deletions and growing values can increase cells, tombstones, compaction overhead, and read amplification. **list** requires particular caution with index-based operations and state-dependent updates.

If the requirement is "all customer actions in the last 90 days," store **each action as a separate row with a clustering key**, rather than placing all actions into a **list** in a single row. If you need to find customers by label, design a dedicated access/lookup path rather than defaulting to cluster-wide **set CONTAINS** queries.

### 5.2. UDT, Tuple, and Frozen

A **UDT (user-defined type)** names a structure with business meaning, such as an address composed of line1/city/postal_code. A **tuple** suits a fixed-position group of values where each position has a well-defined type, though it is harder to read and evolve than a UDT with named fields.

**frozen<customer_address>** serializes the entire UDT as a single value; updates must replace the whole value rather than updating individual fields inside it. Use frozen when the substructure is read and written as a single unit, relatively small, and infrequently modified; a non-frozen UDT may be more appropriate when individual fields need separate updates (subject to CQL version and nesting rules).

**Rule of thumb:** collections and UDTs represent a *structured value* inside a row, not a replacement for an unbounded one-to-many relationship. Consider element counts, update frequency, deletion patterns, and total cell/partition size after compaction.

### 5.3. Counter, Blob, Inet, and Vector: Special Cases

**counter** supports distributed increment/decrement counters with dedicated table rules: non-primary-key columns in a counter table must all be counters, cannot be mixed with regular columns, and cannot use TTL like normal data. Incrementing a counter and retrying after a timeout can increment it again; do not use counters as an exact ledger that must guarantee every event is counted exactly once.

**blob** is suitable for small binary payloads. For large images, videos, or files, it is usually more efficient to store the object in dedicated object storage and keep the URI/metadata in Cassandra. **inet** accepts IPv4 or IPv6 addresses; storing hostnames, IP/CIDR ranges, or network metadata requires different types or models.

Starting in Cassandra **5.0**, **vector<float, n>** supports fixed-dimension vectors for use cases like embeddings and approximate search when backed by an appropriate index/infrastructure. Because it is float-based, it is not meant for data requiring exact decimal precision. Before adopting it, verify that both your cluster and Java driver support this type; do not add vectors to the schema of an older cluster.

## 6. CQL-to-Java Mapping and Safe Operations

When connecting with the Apache Cassandra Java Driver 4.x, common mappings include:

| CQL | Typical Java Type |
|---|---|
| **text**, **ascii** | **String** |
| **boolean** | **boolean/Boolean** |
| **int**, **bigint** | **int/Integer**, **long/Long** |
| **varint**, **decimal** | **BigInteger**, **BigDecimal** |
| **float**, **double** | **float/Float**, **double/Double** |
| **uuid**, **timeuuid** | **UUID** |
| **date**, **time**, **timestamp** | **LocalDate**, **LocalTime**, **Instant** |
| **inet**, **blob** | **InetAddress**, **ByteBuffer** |
| **list**, **set**, **map** | **List**, **Set**, **Map** with compatible element types |
| **UDT**, **tuple** | **UdtValue**, **TupleValue** (or configured codecs) |

Example using the **payments_by_customer_day** table created above. Assume **session** is a **CqlSession** already configured with appropriate contact points, local datacenter, and credentials:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// session is already initialized; IDs must be persisted and reused on retry.
UUID customerId = UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID paymentId = UUID.fromString("33333333-3333-4333-8333-333333333333");
Instant occurredAt = Instant.parse("2026-11-21T01:15:00Z");
LocalDate bucketDay = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
long amountMinor = 1990L; // 19.90 USD = 1990 cents

PreparedStatement ps = session.prepare(
    "INSERT INTO payments_by_customer_day "
  + "(customer_id, bucket_day, occurred_at, payment_id, "
  + " amount_minor, currency, state) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement statement = ps.boundStatementBuilder()
    .setUuid(0, customerId)
    .setLocalDate(1, bucketDay)
    .setInstant(2, occurredAt)
    .setUuid(3, paymentId)
    .setLong(4, amountMinor)
    .setString(5, "USD")
    .setString(6, "CAPTURED")
    .build();

session.execute(statement);
~~~

**Prepared statements** ensure proper type binding and avoid concatenating input values into CQL strings. The **bucketDay** variable is computed in UTC so all services bucket consistently; if business logic requires "day in the store's time zone," define it explicitly and apply the exact same rule on both writes and reads.

For **decimal**, Java should construct **BigDecimal** from strings or equivalently exact sources; avoid initializing from a binary-rounded **double**. For **timestamp**, use **Instant** to represent points in time; do not pass an offset-less **LocalDateTime** into a distributed system without an explicit time zone policy.

A Cassandra write operation can return a timeout even though some replicas have already received the data. Rewriting with the same key and same values is idempotent and far safer than generating a new ID on every attempt. However, updating the same cell with different write timestamps still follows last-write-wins semantics; **business correctness is not automatically guaranteed by data types or consistency levels alone**.

## 7. Four Design Scenarios to Distinguish

**Scenario A — Listed prices and payment totals.** Requires exact reconciliation down to the smallest monetary unit. Use **decimal** if working with decimals under defined scale rules, or **bigint** with minor units and an explicit currency. Do not choose **double**, even if initial test additions appear accurate.

**Scenario B — Telemetry at 50,000 records/second.** Sensor values can use **double**, measurement timestamps **timestamp**, and device identifiers **uuid/text** depending on the domain. Reading by device and time requires partition bucketing and clustering columns; do not store all samples in an unbounded **list<double>**.

**Scenario C — User profiles with a few labels.** Use **set<text>** if the labels are few, bounded, and order does not matter. If you need to find all users with the `"vip"` label at large scale, design a lookup table by label or an evaluated indexing strategy, because a set type by itself does not provide efficient global queries.

**Scenario D — View counts.** **counter** can fit a near-real-time increment/decrement metric where counter retry characteristics are acceptable. If view counts are used for billing, record events with stable IDs, deduplicate, and aggregate through a controlled pipeline; a standalone counter cannot prove that every event was counted exactly once.

## 8. Cassandra Schema Review Checklist

- Does the value represent an **identifier** or a **quantity**? Does a code string require Unicode or preserving leading zeros?
- Do numeric columns have sufficient range for future growth and overflow-handling rules? Is money using **decimal** or **minor units**, not float/double?
- Do temporal fields distinguish **date**, **time of day**, **point in time**, and **duration**? Are time zone and resolution defined?
- Do critical queries provide the full **partition key** and filter on valid **clustering columns**? Do sort order and range conditions follow the key order?
- Are partitions and collections bounded under real-world data growth? Is there a risk of excessive tombstones from updates/deletes?
- Do retry operations reuse IDs/keys? Are there **counter** increments, list appends, or new **now()** calls that break idempotency?
- Do the chosen types map stably in the Java driver, match the running Cassandra version, and allow planned schema evolution?

**Key takeaway:** in Cassandra, data types, key design, and queries are three tightly coupled decisions. The right value domain prevents data from losing meaning; the right precision prevents calculation errors; and the right access pattern keeps reads and writes focused on predictable partitions.
