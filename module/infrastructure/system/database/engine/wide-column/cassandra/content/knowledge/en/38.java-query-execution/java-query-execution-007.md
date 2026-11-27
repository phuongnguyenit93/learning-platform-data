# Statement Consistency Level, Serial Consistency, and Execution Profiles

> **Chapter:** Query Execution from Java  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. When a Java application executes CQL, choosing a consistency level requires accounting for partition keys, replication, datacenter topology, read/write paths, compaction, repair, timeout handling, and business correctness requirements.

## 1. Problem: one query mechanism, multiple execution policies

Suppose a Java service performs three kinds of operations:

- Displaying a page of recent customer events, prioritizing low latency and tolerating slightly stale data.
- Reading a payment status that was just written, requiring a stronger consistency policy in the local datacenter.
- Creating an order **only if the order ID does not already exist**, requiring a conditional compare-and-set operation (*lightweight transaction — LWT*).

If every request uses a single consistency setting, the system falls into one of two traps: **overpaying for reads** beyond what is needed, or **violating business guarantees** when replicas lag or fail. Moreover, LWT introduces a separate consensus phase, so setting only a regular consistency level does not fully describe the policy.

In Java Driver 4.x, three concepts must be kept distinct:

1. **Consistency level (CL):** replica response requirement for regular CQL read/write operations.
2. **Serial consistency level (serial CL):** consensus scope of the Paxos phase used for conditional statements such as **IF NOT EXISTS** or **IF status = ?**.
3. **Execution profile:** a named group of execution settings (default consistency, timeout, page size, and other driver options) that can be attached to statements to avoid repeating configuration.

An execution profile **is not a type of consistency level**: it is a container defining defaults and driver policies for a group of requests. Individual statements can still set CL explicitly to override the profile's setting.

After this lesson, you will be able to configure CL at the session/profile/statement layers, apply serial CL accurately in LWTs, handle conditional outcomes, select consistency levels based on topology, and verify behavior via Java/CQL when timeouts or replica failures occur.

## 2. Request path from Java to replicas

Upon receiving CQL, the Java driver picks a coordinator using cluster metadata and its routing policy. When the full partition key is bound, **token-aware routing** can help select a coordinator close to the replicas owning that partition; the coordinator then coordinates replicas per the replication strategy and CL.

~~~mermaid
flowchart LR
    A["Java service"] --> B["Statement: query + bind + CL + profile"]
    B --> C["Java driver: routing and execution"]
    C --> D["Cassandra coordinator"]
    D --> R1["Replica 1"]
    D --> R2["Replica 2"]
    D --> R3["Replica 3"]
    R1 --> K["Commitlog / memtable / SSTable"]
    R2 --> K
    R3 --> K
~~~

**Cassandra model notes:**

- **Partition keys** locate partitions; **clustering columns** order rows within a partition.
- **Replication factor (RF)** is the configured replica count per datacenter/keyspace, not the count of healthy replicas at every instant.
- **Consistency level** chooses the success condition for a request; it does not control where data is placed and cannot rescue a query missing its partition key.
- **Compaction** merges SSTables and processes data/tombstones under LSM mechanics; **repair** reconciles replicas. Both affect latency, availability, and observed data quality, yet neither replaces choosing the right CL.
- **Retries** and **timeouts** from Java do not mean a request definitely was not applied. This is especially critical for LWTs and non-idempotent operations.

## 3. Read/write consistency levels: thinking in replica counts and DC scope

### 3.1. Common levels

| CL | High-level meaning | When to consider |
|---|---|---|
| **ONE** | Requires one replica response; replica selection depends on coordinator/topology | Reads/writes prioritizing latency or availability and accepting the trade-offs |
| **LOCAL_ONE** | Requires one replica response in the local datacenter | Applications operating primarily against a local DC |
| **QUORUM** | Quorum computed over total replicas in the defined scope | Seeking overlap across replica sets while weighing multi-DC latency |
| **LOCAL_QUORUM** | Majority of replicas in the local DC | Applications needing stronger consistency within the local DC |
| **EACH_QUORUM** | For writes, requires quorum in every participating DC | Writes needing multi-DC acknowledgment; higher cost and availability impact |
| **ALL** | Requires every replica counted for the operation | Broad confirmation; fails whenever any replica is unavailable |
| **SERIAL / LOCAL_SERIAL** | **Serial** level for the LWT consensus phase; also has special semantics for serial reads depending on usage | Never use as an arbitrary replacement for regular read/write CLs |

This table is not an exhaustive list of every Cassandra CL. **ANY** is a level for certain writes, not a read option; **TWO/THREE** also exist in certain versions. Java Driver 4.x provides the **DefaultConsistencyLevel** enum for standard levels.

**Never pick a CL based purely on the word “QUORUM”** while ignoring replica counts and datacenters. In particular, **QUORUM** and **LOCAL_QUORUM** compute over different scopes in a multi-DC cluster.

### 3.2. Example: RF = 3 in one local datacenter

Suppose a keyspace has **RF = 3** in **dc1** and all three replicas for a partition are placed and available:

| CL | Required responses under typical semantics |
|---|---:|
| ONE / LOCAL_ONE (within matching scope) | 1 |
| LOCAL_QUORUM in dc1 | 2 |
| ALL (three participating replicas) | 3 |

For example, a `LOCAL_QUORUM` write is acknowledged by the coordinator once **2/3 replicas** in the local DC respond per operation rules. This **does not mean** the third replica has already received and persisted the write by the time the client gets the response.

If one replica fails, **LOCAL_QUORUM** can still succeed while the remaining two replicas stay healthy. Yet if a second replica suffers a GC pause or saturated disk I/O, requests can time out even though RF is configured as 3.

### 3.3. Reads and writes: replica intersection

With a simple replica set of RF = 3, choosing write CL = 2 and read CL = 2 yields:

~~~text
R = replicas participating in read response = 2
W = replicas acknowledging write            = 2
RF = 3

R + W = 4 > RF = 3
~~~

The **R + W > RF** condition ensures the read and write response sets overlap when evaluated over the same replica set. This is an essential mental tool, **not proof that Cassandra provides transaction isolation or linearizability for all operations**.

You must also weigh:

- Which **datacenter** and replica set? `LOCAL_QUORUM` in different DCs does not automatically overlap across local sets.
- Clocks/timestamps, concurrent writes, and Cassandra's conflict resolution rules affect the winning value.
- Failed replicas, incomplete repairs, stale tombstones, and operational incidents can affect observed correctness.
- An application-level **read-modify-write**, even with `LOCAL_QUORUM` for both read and write, **is not an atomic compare-and-set** without LWT or another synchronization mechanism.

**Conclusion:** `LOCAL_QUORUM` is often well-suited for reads/writes needing strong consistency within a local DC, yet a business rule such as “create an order only once” requires an explicit conditional mechanism, not just `R + W` arithmetic.

## 4. Setting consistency level at the Java statement layer

Java Driver 4.x lets you set CL per statement, such as on a **BoundStatement** for prepared CQL. This fits services sharing one session across queries with varying requirements.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

// Assumes session has prepared a SELECT with 2 bind markers:
// WHERE tenant_id = ? AND event_day = ?
PreparedStatement preparedRead = session.prepare(
    "SELECT happened_at, event_id, event_type " +
    "FROM shop.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 50");

BoundStatement read = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);

var result = session.execute(read);
~~~

This snippet assumes **session**, **tenantId**, **eventDay**, and the keyspace/table already exist; the schema is shown in Section 7. **LOCAL_QUORUM** is only meaningful when actual topology and RF satisfy it.

**BoundStatement in Driver 4.x is immutable.** Setters return a new statement. If you write:

~~~java
BoundStatement original = preparedRead.bind(tenantId, eventDay);
original.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

// Broken intent: original still lacks the updated CL.
session.execute(original);
~~~

you must fix it to:

~~~java
BoundStatement corrected = original
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
session.execute(corrected);
~~~

Or chain setters right when constructing the statement.

### 4.1. Per-request CL, not a cluster-wide change

**setConsistencyLevel** does not alter keyspace RF or server configuration. It sets the consistency requirement for **that single request**. Two statements sharing the same `CqlSession` can use different CLs:

~~~java
BoundStatement fastRead = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

BoundStatement importantRead = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

Choices must match application SLAs and consistency contracts; never flip CL arbitrarily in response to errors. In particular, silently downgrading CL after a timeout can cause the API to **return stale data** without the caller knowing.

### 4.2. Reading by the full partition key remains foundational

On a table with key **((tenant_id, event_day), happened_at, event_id)**, reads must bind **both `tenant_id` and `event_day`** to address a single partition. A query missing a key component or scanning many partitions burns I/O and causes fan-out; raising CL will never fix that query pattern.

## 5. Serial consistency: LWT's separate consensus phase

### 5.1. Why does LWT differ from regular INSERT/UPDATE?

Regular Cassandra writes follow **last-write-wins** semantics based on timestamps and tombstones. If two clients both read “order does not exist” and both run `INSERT`, reading at `LOCAL_QUORUM` beforehand **does not turn two separate statements into an atomic check-and-write**.

CQL supports **lightweight transactions (LWT)** via conditions such as:

~~~sql
INSERT INTO shop.order_state_by_id (
    tenant_id, order_id, status, created_at
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Or:

~~~sql
UPDATE shop.order_state_by_id
SET status = ?
WHERE tenant_id = ? AND order_id = ?
IF status = ?;
~~~

LWT uses **Paxos** to coordinate condition evaluation and writes within the target partition, instead of stitching a SELECT and an INSERT together in Java.

### 5.2. Two CLs involved in LWT

When executing an **IF** statement, distinguish two layers:

| Option | Controls | Example |
|---|---|---|
| **Regular consistency level** | Normal read/write confirmation level, including the LWT commit phase per server mechanics | `LOCAL_QUORUM` |
| **Serial consistency level** | Serial consensus / Paxos scope for evaluating and coordinating the LWT condition | `SERIAL` or `LOCAL_SERIAL` |

Typically, an LWT performs multiple phases and network round trips compared to a normal write, raising **latency, CPU, and network cost**. Never use LWT on every INSERT just to feel “safer” when business logic does not need an atomic condition.

### 5.3. SERIAL and LOCAL_SERIAL

| Serial CL | General scope | Considerations |
|---|---|---|
| **SERIAL** | Serial consensus phase across LWT replicas spanning multiple DCs when multi-DC is configured | Appropriate when global multi-DC coordination is required; latency and availability are exposed to cross-DC links |
| **LOCAL_SERIAL** | Serial consensus phase within the coordinator's local datacenter | Reduces cross-DC dependency, yet must be evaluated carefully if invariants span all DCs |

**Critical point for multi-DC apps:** never pick `LOCAL_SERIAL` merely because it is faster if business invariants require global conditional ordering across DCs. Avoid **mixing `SERIAL` and `LOCAL_SERIAL`** for the same set of business invariants without fully understanding their coordination scope; verify your exact version's documentation and test concurrent cross-DC writes.

Serial consistency **is not a “make every SELECT stronger” button**. It is primarily for conditional LWT operations; Cassandra also defines special semantics for serial reads, yet you should not apply serial CL blindly to ordinary queries.

### 5.4. What is LWT's atomic scope?

CQL conditions apply within the operation scope supported by Cassandra and the target **partition**. An **INSERT IF NOT EXISTS** guards creating a row by primary key. It **does not turn multiple distinct partitions into a multi-table ACID transaction with rollback**.

When business workflows must create an order and update several query-driven tables, design idempotency, outbox/event processing, or reconciliation. **Consistency level** and **serial CL** do not replace application-level multi-entity transaction handling.

## 6. LWT results and the `[applied]` column

Cassandra typically returns a row containing **`[applied]`** for conditional writes:

| Value | Meaning when the request returns successfully |
|---|---|
| **true** | Condition passed and the conditional write was applied per server result |
| **false** | Condition failed; the requested mutation was not applied |
| **Timeout / exception** | **Insufficient information** to know whether it was applied or not |

For instance, if an order with `order_id` already exists, **INSERT ... IF NOT EXISTS** returns **`[applied] = false`** along with current column values (depending on statement/version). That is a **business conflict**, not automatically an infrastructure error to retry.

Conversely, an LWT timeout may occur after several Paxos phases—or even after commit—before the client receives the reply. **Never assume “timeout = not written”.** This shapes API idempotency, request IDs, and retry logic.

### 6.1. Do not mistake false after a retry for an initial failure

Suppose the first **INSERT IF NOT EXISTS** actually succeeded, yet the response was lost. The client retries the exact same condition and gets **`[applied] = false`** because the row now exists. If the API interprets `false` as “someone else created the order” without checking identity/values, it returns the wrong business outcome.

Safer approach:

1. Use a **deterministic `order_id`** from the request; never generate a fresh UUID per retry.
2. Persist an **idempotency key** or request identifier per design.
3. When the outcome is unknown, read/reconcile the row by partition key at an appropriate CL.
4. Distinguish “already created by this same prior request” from “conflicted with different content”.
5. Enable automatic retries only under policies explicitly tested with LWT and specific error types.

LWT provides atomic conditional writes within a partition scope; it **does not automatically deliver system-wide exactly-once semantics**.

## 7. CQL data model for practice

Two tables serving two distinct access patterns:

1. **events_by_tenant_day:** reads events by tenant/day, potentially accepting different CLs per endpoint.
2. **order_state_by_id:** looks up/updates an order's state by key, using **IF** for compare-and-set.

~~~sql
-- dc1 and RF = 3 must match your real topology or lab setup.
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS shop.order_state_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    created_at timestamp,
    version int,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

**Partitioning notes:**

- The events table uses an **event_day** bucket so a single tenant's partition does not grow unboundedly. For ultra-hot tenants, size partitions and traffic to pick smaller buckets if needed.
- The order-state table uses composite partition key **(tenant_id, order_id)**. Each order gets its own small partition, ideal for per-order LWTs without contention on a shared tenant partition.
- **PRIMARY KEY** governs routing. CL controls required replica responses, not partition sizing.
- Two query-driven tables may represent views of the same business entity; Cassandra provides no automatic cross-table atomicity. Design synchronization or reconciliation if required.

### 7.1. Sample test data

~~~sql
INSERT INTO shop.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'CHECKOUT_STARTED'
);

-- Test the conditional statement in cqlsh; if the row already exists,
-- [applied] will no longer be true on a repeat insert with the same key.
INSERT INTO shop.order_state_by_id (
    tenant_id, order_id, status, created_at, version
) VALUES (
    11111111-1111-4111-8111-111111111111,
    33333333-3333-4333-8333-333333333333,
    'NEW',
    '2026-11-21T08:05:00Z',
    0
) IF NOT EXISTS;
~~~

These UUIDs are fixtures only. When running on a lab with **fewer than three replicas** in `dc1`, never assume **LOCAL_QUORUM with RF 3** exhibits production behavior. Align topology/RF with your environment and document any differences in test notes.

## 8. Java Driver 4.x example: regular CL at the statement level

Java Driver 4.x uses **DefaultConsistencyLevel** and immutable statement APIs. This example opens a `CqlSession` to the lab and reads by partition key.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class ReadWithConsistency {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Adjust contact point, DC, and security settings for your lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement statement = prepared
                .bind(tenantId, day, 50)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(statement);
            int count = 0;
            for (Row row : result) {
                if (row.getUuid("event_id") == null) {
                    throw new IllegalStateException(
                        "Event missing identifier key");
                }
                count++;
            }
            System.out.println("Rows: " + count);
        }
    }
}
~~~

**Explanation:**

- **PreparedStatement** is prepared once; values are bound with exact **uuid, date, int** types and reused.
- The statement sets **LOCAL_QUORUM**; the same prepared CQL can produce another statement with a different CL.
- **LIMIT ?** caps returned rows for one partition; it does not turn an oversized partition into a sound data model.
- TLS/auth are omitted here purely to focus on CL. Real environments require proper auth and TLS; never disable security to work around connection errors.
- In long-lived services, reuse **CqlSession** and `PreparedStatement`; never open a new session per HTTP request.
- A query returning without errors is not enough to prove correctness: verify against expected fixtures, event IDs, and values.

## 9. Java example: LWT with regular CL and serial CL

For “create order only if absent”, use **INSERT ... IF NOT EXISTS** and configure **both CLs explicitly**.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public class CreateOrderIfAbsent {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID orderId = UUID.fromString(
            "33333333-3333-4333-8333-333333333333");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO shop.order_state_by_id " +
                "(tenant_id, order_id, status, created_at, version) " +
                "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");

            BoundStatement conditional = insert.bind(
                    tenantId, orderId, "NEW",
                    Instant.parse("2026-11-21T08:05:00Z"), 0)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_SERIAL);

            Row row = session.execute(conditional).one();
            if (row == null) {
                throw new IllegalStateException(
                    "No LWT result row returned");
            }

            if (row.getBoolean("[applied]")) {
                System.out.println("Order created");
            } else {
                System.out.println(
                    "Order already exists; compare business details");
            }
        }
    }
}
~~~

**Analyzing the two attributes:**

- **setConsistencyLevel(LOCAL_QUORUM):** regular CL for the conditional write/commit phase of the request.
- **setSerialConsistencyLevel(LOCAL_SERIAL):** serial CL for the LWT consensus phase within the local DC.
- **`[applied]`** indicates whether the condition succeeded in the returned result. `false` must not be treated as an infrastructure failure and retried endlessly.
- **Deterministic `orderId`** is vital for idempotency. If a timeout occurs before learning the outcome, check the persisted state rather than generating a new order ID.
- When invariants span **multiple datacenters**, analyze consensus scope and choose **SERIAL** rather than defaulting to `LOCAL_SERIAL` out of habit. Keep serial policies consistent across all competing writers.

### 9.1. Conditional state update

Suppose you want to transition state from `NEW` to `PAID`:

~~~sql
UPDATE shop.order_state_by_id
SET status = 'PAID', version = 1
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND order_id = 33333333-3333-4333-8333-333333333333
IF status = 'NEW' AND version = 0;
~~~

This is **compare-and-set** for one order, not a cross-table transaction. If another request already updated the order, the condition fails and returns **`[applied] = false`**. The application must decide whether to re-read and retry against the new state, report a conflict, or trigger workflow handling.

If multiple query-driven tables also mirror order status, never infer from an LWT on `order_state_by_id` that “every other table updated atomically”. Design events, idempotent projections, and reconciliation.

## 10. What is an execution profile?

In Java Driver 4.x, an **execution profile** is a named configuration grouping commonly used execution options—for instance, one profile for lightweight reads, one for `LOCAL_QUORUM` reads, and one for conditional writes.

Repeating chains of setters on every request duplicates code and makes policy changes hard to govern. Profiles centralize **timeouts, default consistency, page size**, and related options by workload group while still permitting explicit per-statement overrides.

### 10.1. Java Driver 4.x HOCON configuration example

Example configuration in an application's **application.conf**:

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = dc1

    request {
      consistency = LOCAL_ONE
      timeout = 2 seconds
      page-size = 500
    }
  }

  profiles {
    important-read {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
      basic.request.page-size = 100
    }

    conditional-write {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 5 seconds
    }
  }
}
~~~

This is an **illustrative configuration**, not a fixed production prescription. Option names and supported parameters depend on the **specific Driver 4.x release**; verify against driver references, RF, datacenters, SLOs, and workload.

**Three key points:**

1. **basic.request.consistency** in the base block establishes the default policy for requests without overrides.
2. The **important-read** profile sets `LOCAL_QUORUM`, a longer timeout, and a smaller page size for specific endpoints.
3. The **conditional-write** profile sets the **regular CL**, while the LWT's **serial CL** is specified explicitly on the statement below. Never assume setting regular CL = `LOCAL_QUORUM` automatically sets serial CL = `LOCAL_SERIAL`.

Across environments, supply contact points, DCs, credentials, and TLS settings via deployment config or secrets managers. Never embed passwords or private keys in committed config examples.

### 10.2. Attaching a profile to a statement

~~~java
BoundStatement important = preparedRead.bind(tenantId, eventDay)
    .setExecutionProfileName("important-read");

session.execute(important);
~~~

For conditional writes:

~~~java
BoundStatement lwt = preparedInsert.bind(
        tenantId, orderId, "NEW", createdAt, 0)
    .setExecutionProfileName("conditional-write")
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL);

Row result = session.execute(lwt).one();
~~~

In this example:

- **important** inherits regular CL and timeout from **important-read** unless overridden separately.
- **lwt** inherits regular CL from **conditional-write** and **sets serial CL explicitly**.
- The driver looks up profiles by name. Misspelling a name or omitting it from effective config causes configuration/statement errors; never assume missing profiles silently fall back to default.
- **setExecutionProfileName** returns a new statement because statements are immutable.

### 10.3. Profiles and statement overrides: effective precedence

Consider:

~~~java
BoundStatement request = preparedRead.bind(tenantId, eventDay)
    .setExecutionProfileName("important-read")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);
~~~

The profile configures **LOCAL_QUORUM**, yet the statement explicitly sets **LOCAL_ONE**. Therefore, **for this request's CL**, the explicit statement setting takes precedence over the profile default.

A practical rule of thumb:

~~~text
Explicit value on the statement
    takes precedence over the execution profile's corresponding setting.

If the statement does not override:
    use the selected execution profile.

If no named profile is selected:
    use the session/config default profile.
~~~

Exact inheritance between profiles, programmatic overrides, and defaults should be verified against your target driver version. Features may also have **both driver-side and server-side settings** that are not the same limit—for example, **driver `request.timeout`** is distinct from **server timeouts**.

### 10.4. Avoiding profile sprawl

- Name profiles by **business purpose / workload class** (**important-read**, **analytics-read**, **conditional-write**) rather than vague names like **profile1**.
- Use profiles for **groups of requests sharing a policy**; use statement overrides for approved exceptions.
- Never create hundreds of profiles just to vary CL per request ID.
- Never downgrade CL after errors just because “a profile is faster”; evaluate stale-read risk and API contracts first.
- Before modifying a profile, test affected endpoints and watch metrics; one config change can impact many requests simultaneously.
- Write **serial CL** explicitly for critical LWTs so policies are obvious in code review rather than relying on default assumptions.

## 11. Setting CL by layer: which choice fits where?

| Need | Where to set | Why |
|---|---|---|
| Most requests share one CL | **Default profile** | Eliminates repeated boilerplate across the app |
| Endpoint group has distinct SLA/timeout/page size | **Named execution profile** | Named, reviewable, measurable configuration |
| One specific statement needs a higher guarantee | **Per-statement `setConsistencyLevel`** | Local, explicit intent right in code |
| Conditional CQL needs Paxos | **Per-statement `setSerialConsistencyLevel`** + regular CL | Distinguishes both phases of LWT |
| Java app queries in another DC | Check **routing/local DC, topology, and replica policy** | CL does not route services to another DC automatically |
| Timeouts or unavailable errors spike | **Investigate root cause**; do not auto-lower CL | Prevents unapproved correctness trade-offs |

Using a profile does not make the driver “cache results” or inherently speed up queries; profiles merely select policies. If a query is slow due to large partitions, tombstones, compaction backlogs, or saturated disks, changing profiles only alters **when requests time out** rather than fixing the root cause.

## 12. Handling timeouts, retries, and uncertain outcomes

Cassandra surfaces distinct errors depending on failure mode:

| Signal | Meaning to distinguish | Handling direction |
|---|---|---|
| **Unavailable** | Coordinator knows insufficient replicas are available for CL | Check RF/DC/replica health; do not retry indefinitely |
| **ReadTimeout** | Insufficient read responses within server timeout | Check replicas, read path, partitions, tombstones, compaction, CL |
| **WriteTimeout** | Insufficient write ACKs within wait window | **Do not assume the write completely failed**; evaluate idempotency |
| **CAS / LWT timeout** | No definitive conclusion on the conditional phase | Re-check state by key/idempotency; never turn timeout into `applied=false` |
| **Driver-side request timeout** | Client waited past local deadline | Distinguish from server timeout; coordinator may still be processing |
| **Authentication / TLS / protocol** | Misconfigured or incompatible connection/security | Fix root cause; CL cannot fix these errors |

Exact exception names and classifications vary across driver/server versions. When real errors occur, log **exception class**, statement operation, CL/serial CL, profile name, timeout, datacenter, and a safe trace ID. Never log passwords, raw bind values, or customer PII.

### 12.1. Retries can amplify load

If nodes are slow due to compaction, repair, or network issues, simultaneous retries trigger a **retry storm**, piling more work onto already overloaded replicas.

- Bound concurrent requests and enforce backpressure.
- Separate **idempotent requests** from operations with side effects or newly generated IDs.
- For **counter increments**, never assume retries are safe when outcomes are uncertain.
- For **LWT `IF NOT EXISTS`**, a retry returning `false` may mean the first attempt succeeded; compare business state rather than blindly reporting a conflict.
- Never treat **lowering CL** as a cure-all for timeouts. If the business contract requires `LOCAL_QUORUM`, dropping to `LOCAL_ONE` can return out-of-contract data.

### 12.2. Execution profile timeouts vs server timeouts

The driver enforces a client-side **request timeout**. Cassandra also enforces server-side timeouts and guardrails. Whenever raising profile timeouts, measure:

- Service request p95/p99 and tail latency.
- Server-side `ReadTimeout`/`WriteTimeout` counts vs client-side timeouts.
- In-flight requests, driver queues, retry counts, and coordinator/replica load.
- Upstream HTTP/gRPC service deadlines calling Cassandra.

Never set client timeouts arbitrarily longer than business deadlines just to hide exception counts. Slow lingering requests still hold resources and get canceled by callers.

## 13. Policy design example for three endpoints

Suppose a service exposes three endpoints:

| Endpoint | Access pattern | Regular CL | Serial CL | Suggested profile |
|---|---|---|---|---|
| **GET /events/recent** | Single partition `(tenant_id, event_day)`, slightly stale data acceptable | `LOCAL_ONE` if business rules permit | Not needed | `default` / `fast-read` |
| **GET /orders/{id}** | Single partition `(tenant_id, order_id)`, critical state | `LOCAL_QUORUM` | Not needed | `important-read` |
| **POST /orders** | **INSERT ... IF NOT EXISTS** for one order | `LOCAL_QUORUM` | `LOCAL_SERIAL` or `SERIAL` per multi-DC needs | `conditional-write` |

This table illustrates one set of choices that **must be validated against topology, RF, and business SLAs**. For multi-DC order creation, `SERIAL` vs `LOCAL_SERIAL` must follow global invariants; **`LOCAL_SERIAL` is not automatically right** for every organization.

### 13.1. An easy-to-write broken design

An app defaults everything to **LOCAL_ONE**, then:

1. Reads “order does not exist” with `LOCAL_ONE`.
2. Executes an unconditional **INSERT** with `LOCAL_ONE`.
3. Assumes only one of two parallel requests can create the order.

This fails atomicity for read-modify-write. Upgrading both read and write to `LOCAL_QUORUM` **still does not make two steps into CAS**. To enforce “create only if absent”, use **LWT** or an appropriate uniqueness/idempotency mechanism.

### 13.2. An overly expensive design

An app uses **SERIAL** or LWT for every telemetry event just “to be safe”, even though each event has a unique ID and no condition check is needed. At high throughput, Paxos overhead inflates latency and resource usage. When business logic does not require a conditional write, use regular `INSERT` with proper primary keys and CL.

## 14. Observing and testing policies under cluster faults

### 14.1. Non-destructive testing in staging/lab

On a representative staging/lab topology:

1. Create keyspaces, tables, and partition-key fixtures.
2. Verify RF, DC/rack, snitch/topology, and which local DC the driver selects.
3. Run the same query with `LOCAL_ONE` and `LOCAL_QUORUM`; measure latency, not just exceptions.
4. Run LWT **IF NOT EXISTS** twice with the same key; verify `[applied]` on the first and second runs.
5. Run two competing conditional writes in a controlled test; confirm no two runs return **`true`** for creating the same record.
6. Simulate one slow or unavailable replica using approved operational methods; observe the effect on each CL.
7. Apply serial CL per policy and verify outcomes after simulated timeouts, especially idempotency.
8. Compare `default`, `important-read`, and `conditional-write` profiles, plus per-statement overrides to confirm precedence.
9. Run soak tests monitoring GC/heap/native memory, disk, compaction, repair/streaming, and retries.
10. Document limitations explicitly: a single-node lab cannot prove **RF = 3, multi-DC, or `LOCAL_QUORUM`** production behavior.

Never shut down production nodes, trigger ad-hoc repairs, or alter production RF for learning exercises. Use approved test environments.

### 14.2. Metrics to monitor

| Layer | Metric / event | Purpose |
|---|---|---|
| **Java app** | Per-endpoint p50/p95/p99, timeouts, error rate | Reflects user-facing impact |
| **Driver** | CL, profile name, retry count, coordinator/DC, in-flight requests | Separates policy settings from driver saturation |
| **Cassandra node** | Read/write latency, timeouts/unavailable, pending tasks | Spots overloaded coordinators or replicas |
| **LWT** | Conditional write latency, CAS contention/timeouts, applied true/false | Distinguishes business conflicts from infra failures |
| **Storage** | SSTable/partition size, tombstones, disk I/O, compaction backlog | Pinpoints slow read causes |
| **Cluster** | Node health, schema agreement, RF/DC/rack, repair status | Verifies cluster can satisfy chosen CL |

**`applied=false` is not a server error**, so never lump it with timeouts into an infrastructure failure rate. However, an unusual surge in `applied=false` can signal **business contention or idempotency collisions**.

### 14.3. Do not log sensitive data

Log **operation name, query shape, CL, serial CL, execution profile name, latency, exception class, retry count, and a PII-free request ID**. Avoid logging raw `BoundStatement` objects, passwords, tokens, customer IDs, or full column values from failed LWTs.

## 15. Common configuration mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Using **LOCAL_QUORUM** with too few local replicas | Unavailable / timeout | Verify RF/DC and node health; restore replicas or adjust lab to match goal |
| Setting **serial CL** assuming regular CL changed too | LWT commit phase behaves unexpectedly | Set and verify **both** regular and serial CL |
| Using `LOCAL_SERIAL` for invariants requiring multi-DC coordination | Business data violates global assumptions | Redesign consensus scope and writer policy |
| Writing manual SELECT + INSERT instead of CAS | Two racing requests both think the condition holds | Use `IF NOT EXISTS`/`IF ...` or proper uniqueness |
| Checking only **`[applied]`** after a retry | `false` misread as complete creation failure | Reconcile row/idempotency key when prior outcome was unknown |
| Calling `setConsistencyLevel` and discarding return value | Requests still run with the old `BoundStatement` | Reassign immutable statement |
| Misspelling profile name | Driver fails to resolve intended profile | Verify `application.conf`, profile name, and effective config |
| Assuming a profile sets serial CL because it sets regular CL | LWT runs with unreviewed serial policy | Set serial CL explicitly and test |
| Raising timeouts to mask slow queries | In-flight requests climb; SLO stays poor | Investigate partitions, tombstones, compaction, replicas |
| Downgrading CL automatically after timeouts | Reads/writes violate data contract | Maintain committed consistency; investigate availability |
| Using LWT for every event | CAS contention, high latency, and CPU load | Use regular writes for unconditional operations |
| Testing only on a single replica | Misses quorum and multi-DC bugs | Test on representative topology with fault scenarios |

## 16. Scenario exercises

### Exercise 1 — Reading/writing `LOCAL_QUORUM` with RF = 3

A keyspace has RF = 3 in `dc1`. The app uses `LOCAL_QUORUM` for reads and writes.

**Question:** How many replicas must normally respond? Does `R + W > RF` prove multi-statement transactions?

**Suggested answer:** A majority in `dc1`, i.e., **2/3** per request. `R + W = 4 > 3` establishes replica-set overlap in a single-set model, yet does not provide transaction isolation or compare-and-set across a SELECT-then-UPDATE sequence.

### Exercise 2 — Choosing regular vs serial CL

An endpoint creates orders with **INSERT ... IF NOT EXISTS**. A developer writes only:

~~~java
BoundStatement b = prepared.bind(tenantId, orderId, "NEW", createdAt, 0)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

**Question:** What policy setting is missing if the team wants explicit review of the consensus phase?

**Suggested answer:** Specify the appropriate **serial consistency**, such as **LOCAL_SERIAL** or **SERIAL** per multi-DC requirements, via **setSerialConsistencyLevel**. Regular CL alone does not specify the full LWT policy.

### Exercise 3 — Execution profile and overrides

Profile **important-read** sets `LOCAL_QUORUM`; a statement uses that profile yet calls **setConsistencyLevel(LOCAL_ONE)** afterward.

**Question:** What is the request's effective regular CL?

**Suggested answer:** **LOCAL_ONE**, because an explicit value on the statement overrides the corresponding profile setting. If `LOCAL_QUORUM` from the profile is intended, remove the conflicting override.

### Exercise 4 — `false` after an LWT timeout

The first `INSERT IF NOT EXISTS` times out. The client retries with the same `order_id` and gets **`[applied] = false`**.

**Question:** Can you conclude this request did not create the order?

**Suggested answer:** No. The first attempt may have applied before the response was lost. Read and reconcile the row by key, idempotency key, and business fields instead of generating a new `order_id` or blindly returning a conflict error.

### Exercise 5 — Multi-DC policy selection

An organization runs two datacenters and requires “only one global order ID can be created” while both DCs accept concurrent requests.

**Question:** Is `LOCAL_SERIAL` automatically sufficient? What must be verified?

**Suggested answer:** Not automatically. Evaluate Paxos serial scope, replication strategy, writers in each DC, and choose **SERIAL** when a global invariant is required; test concurrent conditional writes and DC disconnect scenarios.

### Exercise 6 — Profile raises timeout, yet p99 gets worse

After raising **basic.request.timeout** from 2 seconds to 8 seconds in a profile, client timeout errors fall, yet endpoint p99 and in-flight requests rise.

**Question:** Has the system been optimized?

**Suggested answer:** No. Raising timeouts only lets requests wait longer; measure disk latency, compaction, tombstones, partition sizes, replica health, retries, and app deadlines. Keep the change only if SLOs improve without overloading the system.

### Exercise 7 — Read missing a partition key

A table has `PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)`. An app passes only `tenant_id` and expects `LOCAL_QUORUM` to read “all days”.

**Question:** Does CL solve the missing `event_day`?

**Suggested answer:** No. CQL must satisfy primary key rules; design the API to query per day bucket or build another table matching the access pattern. CL only governs replica response rules.

### Exercise 8 — Correctness on retries

A counter increment times out and the driver considers retrying. A developer says “let's switch the profile to `LOCAL_QUORUM` so retries become safe”.

**Question:** What is wrong with that claim?

**Suggested answer:** CL does not make an increment idempotent. A timeout leaves an unknown outcome and retrying can double-increment. Use deduplication, an event model, or an idempotent business design.

## 17. Java Driver 4.x implementation checklist

- [ ] Identified **RF, local datacenter, and topology policy** for every relevant keyspace.
- [ ] Classified endpoints into **regular reads/writes** vs **conditional LWTs**.
- [ ] Regular CL chosen by SLO, availability, and correctness—not by whichever name sounds “strongest”.
- [ ] LWTs have **serial CL reviewed explicitly**, especially for multi-DC writers.
- [ ] Never confuse `SERIAL`/`LOCAL_SERIAL` with regular CL; avoid LWT when conditions are unnecessary.
- [ ] CQL tables follow query-driven design and statements bind full partition keys.
- [ ] `CqlSession` and `PreparedStatement` are reused; immutable `BoundStatement` return values are retained.
- [ ] Execution profiles have clear names, hold required defaults, and are tested with overrides.
- [ ] Verified **profile names, effective configuration, and precedence** between profiles and statements.
- [ ] Driver timeouts and server timeouts are distinguished; retry policies enforce limits and backpressure.
- [ ] Handled **`[applied] = false`**, timeout/unknown outcomes, and LWT idempotency keys.
- [ ] Tested concurrency, multi-DC invariants, replica outages, and retries on representative topology.
- [ ] Metrics track latency, CL/profile, LWT contention, errors, compaction/repair, and node health.
- [ ] Logs exclude credentials, raw bind values, customer IDs, and sensitive payloads.
- [ ] Verified TLS/auth, driver/server versions, and backup/recovery plans before rolling out config changes.

## 18. Summary

**Consistency level** specifies replica response requirements for regular Cassandra reads and writes; **serial consistency** is the separate policy for the consensus phase of **LWT**. In Java Driver 4.x, **execution profiles** bundle default settings such as CL, timeouts, and page size per request group, while individual statements can override specific attributes when explicit control is needed.

No single CL fits every query. Start from **partition keys, data modeling, replication/DCs, SLAs, and business invariants**. For conditional writes, inspect **`[applied]`**, handle unknown outcomes after timeouts, and preserve idempotency. For profiles, verify effective config and precedence so requests never silently run under unintended policies. Finally, measure latency, errors, correctness, and background **compaction/repair** load on representative topology before shipping configuration changes to production.
