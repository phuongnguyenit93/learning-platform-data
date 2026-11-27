# Simple and Composite Partition Keys

In Apache Cassandra, choosing the **partition key** is a critical decision when designing a table: this key determines the logical partition that Cassandra reads, writes, and replicates across nodes. A partition key can consist of **a single column** (*simple partition key*) or **multiple columns** (*composite partition key*). Both can be paired with *clustering columns* to store multiple rows within the same partition.

In a distributed wide-column model, choosing the right number and components of the partition key enables CQL queries to route directly to the required data, distribute load properly, and control partition sizes. This lesson focuses on comparing the two partition key choices; subsequent topics on replication, consistency levels, and connecting from Java will build upon that choice.

After this lesson, you will be able to:

- Distinguish single-column and multi-column partition keys via `PRIMARY KEY` syntax.
- Predict whether two rows belong to the same or different partitions by comparing the **entire** partition key value.
- Choose appropriate keys for queries by customer, device, time, and tenant.
- Recognize the risks of *hot partitions*, unbounded partition growth, and queries missing key components.
- Write CQL and queries from a Java application that align with the designed keys.

## 1. Simple partition key: one value identifies one partition

A **simple partition key** is a partition key consisting of only **one column**. For example, each customer has one profile:

```sql
CREATE TABLE customer_profile_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    email text
);

-- Equivalent: PRIMARY KEY (customer_id)
```

Each `customer_id` identifies one logical partition. Because the primary key contains no clustering columns, each `customer_id` value has at most one logical row in this table.

```sql
SELECT display_name, email
FROM customer_profile_by_id
WHERE customer_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Cassandra locates the partition from `customer_id` and reads the row in that partition. A simple key **does not mean** each partition can only contain one row. When clustering columns are added, a simple partition key can hold many rows:

```sql
CREATE TABLE readings_by_device (
    device_id uuid,
    recorded_at timeuuid,
    reading double,
    PRIMARY KEY (device_id, recorded_at)
) WITH CLUSTERING ORDER BY (recorded_at DESC);
```

In this table:

- Partition key: **`device_id`**.
- Clustering column: **`recorded_at`**.
- Full primary key: **`(device_id, recorded_at)`**.
- All records with the same `device_id` reside in the **same partition**, even when `recorded_at` differs.

Query to fetch the 10 most recent values of a device:

```sql
SELECT recorded_at, reading
FROM readings_by_device
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 10;
```

A simple key is easy to use when a single value is enough to identify the dataset to read. However, if a device continuously writes data over many years, that device's partition will grow very large. You should consider splitting by time or another criterion.

## 2. Composite partition key: multiple values combine to form one partition

A **composite partition key** consists of two or more columns. Cassandra treats the **combination of their values** as one complete partition key, then computes the token based on that combination.

For example, each device belongs to a tenant. The pair `(tenant_id, device_id)` identifies a device profile within a tenant's scope:

```sql
CREATE TABLE device_profile_by_tenant_and_id (
    tenant_id text,
    device_id uuid,
    device_name text,
    firmware_version text,
    PRIMARY KEY ((tenant_id, device_id))
);
```

The following two value pairs identify **two different logical partitions**:

```text
(tenant_id = 'acme', device_id = D1)  -> partition key ('acme', D1)
(tenant_id = 'beta', device_id = D1)  -> partition key ('beta', D1)
```

They share the same `device_id` but have different `tenant_id` values. Similarly, two different devices within the same tenant also have different partition keys.

The query must provide all components to identify the partition:

```sql
SELECT device_name, firmware_version
FROM device_profile_by_tenant_and_id
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

**A composite key cannot be treated as multiple independent keys.** A query with only `tenant_id` cannot derive the token of a key composed of `(tenant_id, device_id)`:

```sql
-- Cannot determine a complete partition key:
SELECT *
FROM device_profile_by_tenant_and_id
WHERE tenant_id = 'acme';
```

Under standard access patterns and without an appropriate index, Cassandra does not support this query without resorting to broad filtering. Adding `ALLOW FILTERING` may work in some cases, but it is generally not a good choice for large datasets.

### Combining a composite partition key with clustering columns

A composite partition key can still have multiple rows inside a partition. For example, fetching measurement history for **one device, belonging to one tenant, on one day**:

```sql
CREATE TABLE readings_by_tenant_device_day (
    tenant_id text,
    device_id uuid,
    event_day date,
    recorded_at timestamp,
    event_id timeuuid,
    reading double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        recorded_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (recorded_at DESC, event_id DESC);
```

Here, the three columns **`tenant_id`, `device_id`, and `event_day` together form one partition key**. The two columns `recorded_at` and `event_id` are clustering columns, distinguishing rows and determining their order within the same partition.

```text
Partition A = ('acme', D1, 2026-11-21)
  (08:45, E3) -> reading = 38.1
  (08:30, E2) -> reading = 37.9
  (08:00, E1) -> reading = 37.7

Partition B = ('acme', D1, 2026-11-22)
  (08:10, E4) -> reading = 38.0

Partition C = ('acme', D2, 2026-11-21)
  (09:00, E5) -> reading = 36.5
```

A, B, and C are **logical partitions**. They may happen to reside on the same node or share overlapping replica sets; different partition keys do not guarantee different servers.

## 3. Parentheses in `PRIMARY KEY` change the meaning

This is the most common mistake when transitioning from relational SQL to CQL:

| Declaration | Partition key | Clustering columns |
| --- | --- | --- |
| `PRIMARY KEY (tenant_id)` | `tenant_id` | None |
| `PRIMARY KEY (tenant_id, device_id)` | `tenant_id` | `device_id` |
| `PRIMARY KEY ((tenant_id, device_id))` | `(tenant_id, device_id)` | None |
| `PRIMARY KEY ((tenant_id, device_id), recorded_at)` | `(tenant_id, device_id)` | `recorded_at` |
| `PRIMARY KEY ((tenant_id, device_id, event_day), recorded_at, event_id)` | `(tenant_id, device_id, event_day)` | `recorded_at`, `event_id` |

In particular, the two lines below are **not equivalent**:

```sql
-- Only tenant_id is the partition key:
PRIMARY KEY (tenant_id, device_id, recorded_at)

-- tenant_id and device_id form a composite partition key:
PRIMARY KEY ((tenant_id, device_id), recorded_at)
```

In the first form, all devices belonging to the same tenant share **one partition**; `device_id` only helps order and distinguish rows within that partition. In the second form, each tenant–device pair gets **its own partition**, which helps distribute data when a tenant has many devices.

Terminology can also be confusing:

- **Composite partition key**: a partition key with multiple components inside the innermost pair of parentheses.
- **Compound primary key**: a primary key with a partition key and one or more clustering columns.
- A primary key can use a simple **or** composite partition key, with **or without** clustering columns.

To determine the key type, inspect the **parentheses syntax**, rather than just counting the columns listed after `PRIMARY KEY`.

## 4. How does Cassandra distribute both key types?

In principle, Cassandra encodes the partition key value and uses a *partitioner* (commonly `Murmur3Partitioner`) to compute a **token**. The token and replication strategy determine the nodes responsible for that partition.

```text
Simple key
    device_id = D1
       |
       v
    token(D1) -----------------------> Responsible replica set

Composite key
    (tenant_id, device_id, event_day)
    ('acme',   D1,        2026-11-21)
       |
       v
    token(combination of all 3) -----> Responsible replica set
```

Key points to grasp:

1. Cassandra computes the token from the **entire partition key**. With a composite key, there is no default rule to "hash the tenant token first and then sub-select by device."
2. Rows with the **same partition key** belong to the same logical partition. Rows in different logical partitions can have the same token (collision) or reside on the same replica set.
3. Changing one component of the partition key creates a **new partition key**, usually with a different token; old data does not automatically move to the new key via `UPDATE`.
4. Clustering columns **do not participate in token calculation**. They organize data within the partition.
5. `replication factor` governs the number of copies according to the replication strategy; increasing the number of replicas does not split an oversized partition into multiple partition keys.

For a composite key, the **column order in the key declaration** is part of the key definition and must be preserved when working with schemas/tokens. Conversely, the order of equality conditions in a `WHERE` clause does not have to match the declaration order, as long as the full key is provided.

## 5. Comparing against real-world query requirements

Key selection should start from the **questions the application needs to answer**:

| Requirement | Suggested partition key | Suggested clustering columns | Considerations |
| --- | --- | --- | --- |
| Fetch profile by `customer_id` | `customer_id` | None | One row per customer. |
| List devices of a tenant | `tenant_id` | `device_id` | A large tenant's partition can become too big. |
| Fetch info for one device within a tenant | `(tenant_id, device_id)` | None | Requires knowing both tenant and device. |
| Fetch events by device per day | `(tenant_id, device_id, event_day)` | `recorded_at`, `event_id` | Must bound daily buckets and handle multi-day queries. |
| Fetch latest event of every device in a tenant | Needs a separate query model | Depends on access order | Cannot assume a per-device history table efficiently solves all aggregate queries. |

### Query matching a daily composite key

```sql
SELECT recorded_at, event_id, reading
FROM readings_by_tenant_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Because the partition key is fully specified, Cassandra knows which partition to read. Since the schema declares `recorded_at DESC`, the newest records of the day appear first in clustering order.

Querying a time range within a day:

```sql
SELECT recorded_at, event_id, reading
FROM readings_by_tenant_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND recorded_at >= '2026-11-21T08:00:00+0700'
  AND recorded_at <  '2026-11-21T09:00:00+0700';
```

This range predicate applies to the **first clustering column** after binding all partition key components with equality. For a query spanning multiple days, the application must determine the day buckets to read and merge results, or use a dedicated data model for that query pattern.

### Queries not matching the composite key

```sql
-- Missing tenant_id and event_day:
SELECT *
FROM readings_by_tenant_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;

-- No partition key component at all:
SELECT *
FROM readings_by_tenant_device_day
WHERE recorded_at >= '2026-11-21T08:00:00+0700';
```

These queries cannot locate a partition using the primary key. If they need to be supported frequently, create a corresponding query table, or consider an indexing facility suited to your Cassandra version and data scale. `ALLOW FILTERING` does not automatically make a broad-scan query efficient.

## 6. When does a simple key become a bottleneck?

A **hot partition** occurs when one partition key receives too much read or write load; a **large partition** occurs when one partition key holds too much data. The two issues are related but not identical: a small partition can still be "hot" if accessed continuously.

Suppose a device generates **5 events/minute**, each event having an average payload of **1 KiB**, excluding metadata, compression, or tombstones. At a steady rate:

| Time span, per device | Estimated row count | Hypothetical data volume |
| --- | ---: | ---: |
| 1 day | 7,200 | Around 7.0 MiB |
| 30 days | 216,000 | Around 211 MiB |
| 365 days | 2,628,000 | Around 2.51 GiB |

If the key is only `device_id`, the device's data accumulates into one partition and grows continuously. If the key is only `tenant_id`, a tenant with 1,000 devices at the rate above can funnel around **7.0 GiB/day** into the same logical partition.

Adding an `event_day` bucket to the composite partition key bounds each partition per device to **a single day**. For example:

```sql
-- Device data accumulates unboundedly over days:
PRIMARY KEY (device_id, recorded_at)

-- Each tenant-device-day is one partition:
PRIMARY KEY ((tenant_id, device_id, event_day), recorded_at, event_id)
```

These numbers are illustrative examples for reasoning, **not universal recommended capacity thresholds**. Actual size on SSTables varies by column types, update/delete counts, compression, and compaction; load also depends on node configuration, replicas, and query patterns. Measure both partition size distribution and actual workload traffic.

## 7. Choosing composite key components sensibly

A useful design workflow:

1. **List the primary queries.** For example: "Fetch the 20 latest records for device D, tenant T, day N."
2. **Identify the values the application definitely knows.** In the example above, `tenant_id`, `device_id`, and `event_day`.
3. **Put values that select the right data group into the partition key.** Evaluate whether a daily or hourly bucket is needed to bound size.
4. **Put columns needed for sorting/range filtering into the clustering key.** For example `recorded_at`, then add a stable `event_id` to distinguish events sharing the same timestamp.
5. **Estimate partition count, size, and per-partition traffic.** Avoid keys with very few distinct values (such as only `region` or only `status`) on large datasets.
6. **Check remaining queries.** If "all devices in a tenant" is queried very frequently, a table keyed by `(tenant_id, device_id, event_day)` does not directly serve it; another access path is needed.

Some common pitfalls:

| Design / Assumption | Problem | Remediation |
| --- | --- | --- |
| `PRIMARY KEY (tenant_id, device_id)` assumed to be a composite partition key | In reality only `tenant_id` is the partition key. | Write `PRIMARY KEY ((tenant_id, device_id))` if a composite key without clustering is intended. |
| Assuming composite key `(tenant_id, device_id)` allows prefix lookup of all devices by `tenant_id` | Token hash is computed over the entire key pair. | Use a tenant-scoped lookup table or an appropriate index. |
| Using only `event_day` as the partition key | All devices on that day share one giant partition. | Combine with entity identifiers such as tenant and device. |
| Putting high-cardinality `recorded_at` in the partition key when reading time series | Many tiny partitions, hard to retrieve historical ranges. | Move timestamp to the clustering key, use a time bucket in the partition key. |
| Using daily buckets when a single device still has massive throughput | Daily partition can still become too large or too hot. | Consider hourly buckets or controlled sharding, along with a matching query strategy. |
| `event_day` computed in different time zones by producer and reader | The same event may be written/queried in inconsistent buckets. | Standardize bucket calculation rules, e.g., UTC date, and apply consistently everywhere. |

**Note on cardinality:** adding a column to a composite key does not automatically guarantee even distribution. If that column only takes one or a few values for most rows, or one combination receives disproportionately high traffic, the system can still hit hotspots. Keys must be chosen based on actual data distribution and traffic.

## 8. Using a composite partition key from a Java application

The Java application should bind **all partition key components** in a prepared statement. The example below uses the DataStax/Apache Cassandra Java Driver 4.x API; assume `session` is already connected and the active keyspace contains the example table.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.LocalDate;
import java.util.UUID;

public class ReadingQueries {
    public static ResultSet latestForDay(
            CqlSession session, String tenantId, UUID deviceId, LocalDate eventDay) {

        PreparedStatement query = session.prepare(
            "SELECT recorded_at, event_id, reading " +
            "FROM readings_by_tenant_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "LIMIT 20"
        );

        return session.execute(query.bind(tenantId, deviceId, eventDay));
    }
}
```

The crucial point here is not the Java syntax, but the alignment between query and schema: **`tenantId` + `deviceId` + `eventDay`** uniquely identifies a partition key. In a real application, prepare the statement once and reuse the `PreparedStatement` instead of calling `prepare` on every invocation; avoid queries missing key components and patching them with `ALLOW FILTERING`.

## 9. Self-check

Consider the schema:

```sql
CREATE TABLE audit_by_tenant_user_month (
    tenant_id text,
    user_id uuid,
    event_month text,
    happened_at timestamp,
    audit_id uuid,
    action text,
    PRIMARY KEY ((tenant_id, user_id, event_month), happened_at, audit_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, audit_id ASC);
```

Answer these questions:

1. Is the partition key a simple or composite key? Which columns does it include?
2. Do two rows with the same tenant and user but different months reside in the same or different logical partitions?
3. To read one month of history for a user, is `WHERE tenant_id = ... AND user_id = ...` sufficient?
4. If the declaration is changed to `PRIMARY KEY (tenant_id, user_id, event_month, happened_at, audit_id)`, what remains as the partition key?
5. If a new requirement is "list all events of every user belonging to tenant T in month M", should this table be used directly as the primary query?

**Answers with explanations:**

1. It is a three-column composite partition key: `tenant_id`, `user_id`, `event_month`.
2. Different partitions, because `event_month` is part of the partition key.
3. Not sufficient: `event_month` is missing. You need to know the month, or read the relevant months.
4. Only `tenant_id` remains as the partition key; the other four columns become clustering columns.
5. Not suitable for direct querying by tenant and month because `user_id` is missing from the partition key. A separate table/access path tailored to that query is needed.

## 10. Key takeaways

- A **simple partition key** has one component, e.g., `PRIMARY KEY (device_id, recorded_at)` where `device_id` is the partition key.
- A **composite partition key** has two or more components, e.g., `PRIMARY KEY ((tenant_id, device_id), recorded_at)` where the pair `(tenant_id, device_id)` is the partition key.
- Cassandra computes the token from the **entire** partition key; all rows with the same key value belong to the same logical partition, while clustering columns organize rows within the partition.
- Cassandra table design starts from **query patterns + data scale + load distribution**, before deciding on a simple or composite partition key.
- Adding a time/bucket component to a composite key can bound a growing partition, but requires the application to manage reading across multiple buckets when needed.

Partition key selection is the bridge between the wide-column data model, distribution/replication mechanisms, and CQL query performance. Understanding simple and composite keys clearly equips you to proactively design Cassandra tables for multi-tenant systems, continuous event ingestion, and Java applications requiring predictable latency.
