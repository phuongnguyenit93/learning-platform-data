# Read preference and choosing primary or secondary

> **Chapter:** Data Consistency  
> **Module:** `SPRING_DATA_MONGODB`

When running MongoDB as a **replica set**, data is replicated from a **primary** node to **secondary** nodes. The primary receives ordinary write operations; secondaries replicate changes through the replication mechanism and can serve certain read queries. When a Spring Data MongoDB application uses a repository or `MongoTemplate`, the question "read from primary or secondary?" directly affects **data freshness, latency, server load, and behavior when a replica set undergoes failover**.

**Read preference** is the policy that guides the driver in choosing a replica set member for supported read operations. It is **not** a guarantee that data is always the latest, nor does it replace `readConcern`, `writeConcern`, transactions, or business logic. A report running on a secondary may tolerate replication lag; however, an operation like "just placed an order, reopen it to confirm the order was saved" requires a different consistency contract.

This lesson belongs to `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories, practicing queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics. The focus is on **how to choose primary/secondary and make the right decision for each read path**.

## 1. Learning objectives

After this lesson, you can:

1. Describe primary, secondary, replication lag, and failover in a replica set.
2. Distinguish the five modes `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, and `nearest`.
3. Choose a read preference for freshness-sensitive operations, dashboards/reports, read-heavy APIs, and primary/secondary loss scenarios.
4. Explain why `readPreference`, `readConcern`, and `writeConcern` address different concerns; apply causal consistency when needed.
5. Configure MongoDB connection strings, the MongoDB Java driver, and Spring Data `MongoTemplate` as needed; know when to use two read clients.
6. Control secondary selection using tag sets and `maxStalenessSeconds`, without treating `nearest` as a "secondary closest to the user" choice.
7. Test multi-node replica sets, observe replication lag, handle timeouts/failover, and review data consistency pitfalls.

## 2. Replica set: how does data flow from primary to secondary?

Consider a three-member replica set example:

```text
                         MongoDB driver
                               |
                     Replica-set discovery
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
        [PRIMARY P]       [SECONDARY S1]    [SECONDARY S2]
        accepts writes     replicates data    replicates data
             |                 ^                 ^
             |     replication |     replication |
             +-----------------+-----------------+

  Data at time T:
    P:  includes write W10
    S1: includes write W9, W10 not yet applied
    S2: includes write W8, W9 and W10 not yet applied
```

A replica set provides fault tolerance and distributes certain read queries. Secondary nodes copy operations from the primary's replication log (*oplog*) and apply them at their own pace. Replication **must not be assumed to be instantaneously synchronous across all secondaries**.

### 2.1. Timeline for an order update

```text
Time  | Primary (P)                     | Secondary (S)
------+---------------------------------+-----------------------------
t0    | order.status = "NEW"            | order.status = "NEW"
t1    | update status = "PAID"          | change not yet visible
t2    | acknowledged write              | may still see "NEW"
t3    |                                 | applies update: "PAID"

READ at t2:
  readPreference=primary    => reads "PAID" if reading after a successful write
  readPreference=secondary  => may read "NEW"
```

This is the model explaining the **stale read** phenomenon. Actual timing depends on write concern, replica set state, replication load, network, and read timing. `writeConcern:"majority"` requires the necessary members to acknowledge according to the majority rule, but **does not mean every secondary has already applied the write**.

### 2.2. Primary does not mean "always available"

When the primary loses connectivity or an election occurs, the system may experience a window where **no primary has been elected and observed by the driver**. Reading with `primary` may wait during server selection and then time out. Replacing `primary` with `secondaryPreferred` does not guarantee every query will always succeed: secondaries may also be unavailable, fail tag/staleness criteria, or lack the needed data.

### 2.3. A replica set is not data sharding

Secondaries typically replicate **the same dataset** from the primary. They are not shards holding separate slices of data. Using secondaries to serve reports only **distributes read load across replica-set members**; it does not automatically replace sharding, indexing, or query optimization.

## 3. What is read preference, and what does it not do?

`readPreference` instructs the driver on **which server to select** to handle a read operation. The MongoDB driver's default for ordinary read operations is `primary` unless configured otherwise.

It does **not**:

- Make data replicate to secondaries faster.
- Guarantee that a secondary always has the latest write.
- Guarantee that a single request always reads from **the same** secondary across multiple queries.
- Replace transactions or optimistic locking to prevent lost updates.
- Automatically create indexes, optimize aggregations, or route writes to secondaries.
- Automatically modify tenant filters, authorization checks, or soft-delete filters.

### 3.1. Table of the five modes

| Mode | Preferred/selected node | When no suitable node exists | Short takeaway |
| --- | --- | --- | --- |
| `primary` | **Primary only** | Waits or errors when no primary can be selected | Prioritize reading from the write-accepting node |
| `primaryPreferred` | Primary; if no primary is available, look for a secondary | Errors if no suitable member exists | Normally reads primary, falls back to secondary |
| `secondary` | **Secondary only** | Waits or errors when no eligible secondary can be selected | Intentionally dedicate reads to secondaries |
| `secondaryPreferred` | Secondary; if no eligible secondary exists, may fall back to primary | Errors if no suitable member exists | Prefer secondary, with a primary fallback path |
| `nearest` | Eligible member within the **latency window**, which may be primary or secondary | Errors if no suitable member exists | Prioritize network latency to the server, not member role |

**Note:** "no suitable server" can stem from topology, tag sets, `maxStalenessSeconds`, connectivity, or server selection. The driver applies server selection rules rather than simply sending requests sequentially to hostnames listed in the URI.

## 4. primary: the default and usually suitable for transactional read paths

`primary` restricts ordinary read commands to the primary member:

```javascript
// In mongosh connected to a replica set:
db.getMongo().setReadPref("primary")

db.orders.findOne({ _id: "ORD-101" })
```

**Advantages:**

- Avoids selecting a secondary that **has not yet received a recent write**.
- Often the easiest choice to reason about for "write then read back" behavior.
- Suitable for many read paths that inform an immediate update decision, provided the application also handles versioning/transactions as required.

**Limitations to understand:**

- The primary can face heavy read load when many APIs/dashboards access it concurrently.
- During an election or when there is no primary, operations may wait and then fail.
- `primary` **does not automatically guarantee linearizability for every configuration**. Consistency level also depends on `readConcern`, `writeConcern`, sessions, and failover history.
- A `find` on the primary followed by an `update` are **two separate operations**, not automatically a single transaction. A race condition can occur without checking an expected version or using an atomic conditional update.

### 4.1. Business example where primary should be preferred

A user just paid for order `ORD-101`; the detail API needs to reflect the updated status before returning the confirmation page. Reading from a secondary without a causal consistency mechanism may return the old status `NEW` and cause the user to pay again. For this read path, prefer `primary` or design a properly constrained causal session, and **do not try to offload the primary by trading away the consistency guarantee the UI requires**.

## 5. primaryPreferred: prefer primary but accept fallback

`primaryPreferred` behaves as follows:

1. If an eligible primary is available and visible to the driver, use the primary for reads.
2. If no primary is available, it may read from a secondary according to server selection rules.
3. Once a primary is elected again, the driver normally returns to selecting the primary on subsequent reads.

```javascript
db.getMongo().setReadPref("primaryPreferred")
db.products.find({ active: true })
```

**Suitable use cases:** product catalog APIs, public information, and data where during periods without a primary you still want to attempt serving reads **while accepting that data may be stale**.

**Common misconception:** `primaryPreferred` does not create an "always read fresh" guarantee: right during failover, a request may route through a lagging secondary. Therefore, if the product **cannot tolerate** stale reads, do not use a preferred mode hoping it behaves identically to `primary` in every situation.

## 6. secondary: read only on secondaries

`secondary` selects only secondaries. If no eligible secondary is available, it **does not automatically fall back to the primary**:

```javascript
db.getMongo().setReadPref("secondary")

db.audit_events.find({
  tenantId: "TENANT-A",
  eventType: "LOGIN"
}).limit(100)
```

**Suitable when:**

- An analytics job can tolerate replication lag.
- You want to avoid extra read load on the primary to protect the transactional write path.
- There is a secondary provisioned with resources/indexes/monitoring for reporting workloads.

**Risks:**

- If there is no secondary (e.g., a single-member replica set), the query will fail after the server selection timeout.
- A secondary may lag behind the primary, causing the latest report to miss recent data.
- Heavy reports still consume CPU/RAM/I/O on the secondary, which can **increase replication lag** and affect recovery capability.
- `secondary` should not be treated as appropriate for read-modify-write operations that need to see the latest data.

## 7. secondaryPreferred: offload reads with a fallback path

`secondaryPreferred` prefers an eligible secondary and can fall back to the primary when no suitable secondary is available:

```javascript
db.getMongo().setReadPref("secondaryPreferred")

db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $group: { _id: "$channel", count: { $sum: 1 } } }
])
```

**Good use cases:** statistics screens or reports that do not require updates up to the very latest write, while still wanting higher availability if secondaries are temporarily unavailable.

**Downside of fallback:** During periods when only the primary is eligible, a heavy report may **run on the primary**, defeating the load isolation goal. If the operational requirement is "never let heavy reports run on the primary," choose `secondary` and accept returning an error/pausing when no secondary is available.

### 7.1. There is no single "secondaryPreferred right for every API"

Classification examples:

| Read path | Freshness expectation | Initial choice to consider |
| --- | --- | --- |
| Confirming payment immediately after write | High | `primary`; check read/write concern |
| Fetching newly created order list for next navigation | High or needs read-your-writes | `primary` or verified causal session |
| Order count dashboard from 5 minutes ago | Lag acceptable | `secondaryPreferred` if primary fallback is acceptable |
| High-cost analytical report | Lag acceptable | `secondary` to avoid primary fallback |
| Rarely changing product catalog | Short lag acceptable | `primaryPreferred` or `secondaryPreferred` per SLA |
| Multi-document operations inside a transaction | Needs transaction guarantees | Use appropriate transaction config, typically reading from primary |

Do not choose based solely on whether an API is GET/POST. A GET checking balance or access permissions may be stricter than a scheduled report.

## 8. nearest: latency-based selection, not synonymous with secondary

`nearest` selects an **eligible** member whose network latency falls within the driver's acceptable window relative to the fastest node. The selected node can be either a primary or a secondary:

```javascript
db.getMongo().setReadPref("nearest")
db.catalog.find({ category: "BOOK" }).limit(20)
```

**Two misconceptions to avoid:**

1. "nearest" does not automatically determine geographic distance from the end user to the data; the driver measures **network latency from the client to the replica set member**. A proxy, data center, or network topology can make the selection differ from geographic intuition.
2. "nearest" does not mean "nearest secondary"; **the primary can still be selected**.

Latency-based selection can help some geographically distributed read workloads, but consistency still depends on replication lag and read concern. If the business requires stale-free reads after a write, do not rely on `nearest` alone as a guarantee.

## 9. Read preference vs. read concern and write concern

These three terms often appear together, yet they solve **three independent questions**:

| Mechanism | Question | Examples |
| --- | --- | --- |
| **Read preference** | **Which member to read from?** | `primary`, `secondaryPreferred` |
| **Read concern** | **What visibility/durability level does the read require?** | `local`, `majority`, `snapshot`, `linearizable` under supported conditions |
| **Write concern** | **Under what conditions is a write acknowledged?** | `w:1`, `w:"majority"`, `j:true`, timeout |

Do not infer:

- `readPreference=primary` ⇒ automatically uses `readConcern=majority`. **False.**
- `readPreference=secondary` + `readConcern=majority` ⇒ always gets the latest write on the primary. **False.**
- `writeConcern=majority` ⇒ every secondary has caught up to the write by the time the client receives ACK. **False.**
- `readPreference=nearest` ⇒ application latency is always lowest. **Insufficient basis** without examining replication lag, server load, queries/indexes, and network.

### 9.1. Read concern local

`local` allows reading data that the server already has at the moment it serves the query, without requiring that data to be majority-committed. On the primary, a change that is not yet majority-committed risks being rolled back upon failover. On a secondary, `local` can still read data **lagging in replication** behind the primary.

Therefore, "I read from the primary" does not fully specify the durability of write history; and "I read from a secondary" does not specify whether the data is majority-committed.

### 9.2. Read concern majority

`majority` restricts returned data to versions considered recorded by a majority of voting members under replica set rules. It provides stronger **survival across failover** guarantees than `local` under supported conditions, but it does not mean a secondary immediately has the latest result present on the primary.

For example, write `W10` may be majority-acknowledged by the primary and one secondary, while another secondary is still at `W9`. A `majority` read sent directly to the slower secondary might still not observe `W10` without an appropriate causal/snapshot requirement.

### 9.3. Read concern snapshot and linearizable

`snapshot` is used in supported contexts/operation types to view data at a consistent snapshot, which is often important in transactions. However, a consistent snapshot **does not automatically mean the latest point in time at the instant of the query**.

`linearizable` is a stricter level for supported reads on the **primary**, with associated conditions and costs. It is not an option you can arbitrarily attach to a secondary to force the secondary to behave like a primary. When such a strong guarantee is needed, verify read/write concern, session, topology, and timeout requirements against the documentation for the server/driver version in operation.

### 9.4. Write concern majority and replication lag

`w:"majority"` requires acknowledgment from a majority under MongoDB rules; it does not mean all secondaries have caught up. This is why a post-write read on **an arbitrary secondary** must not be treated as read-your-writes merely because the prior write received a majority ACK.

`mongosh` example:

```javascript
// Example with a replica set and the orders collection.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { status: "PAID" } },
  { writeConcern: { w: "majority", wtimeout: 10000 } }
)
```

The write command is still sent to the primary. If the result returns a write concern timeout, **do not automatically infer that the write definitely did not happen**. Check state or use appropriate idempotency/CAS before retrying.

## 10. Read-your-writes and causal consistency

"Read-your-writes" means that after a client/session successfully writes a value, a subsequent read in the same causal chain does not observe a state **older** than the written result.

### 10.1. Why a secondary alone is usually not enough

```text
Client                    Primary                 Secondary
  |                         |                        |
  |--- update ORD-101 ----->|                        |
  |<-- acknowledged --------|                        |
  |                         |--- replication pending |
  |--- find ORD-101 -------------------------------->|
  |<-- status = "NEW" --------------------------------|
```

If a user has just updated a status, routing the next read to a secondary **without coordination** may return a stale result. The simplest approach is to read from the primary. If you want to use a secondary while maintaining ordering constraints, you need to design a **causally consistent session** and read/write concerns that satisfy MongoDB's requirements.

### 10.2. What does a causal session do?

MongoDB supports causal sessions for a sequence of related operations. When used under the proper conditions — including `majority` read concern and `majority` write concern for appropriate causal durability guarantees — the driver/server can use logical time metadata such as `operationTime`/`afterClusterTime` to require subsequent reads **not to go backward before known operations**.

This may cause a secondary read to **wait for replication to catch up** before returning a result, rather than immediately reading an older version. However:

- It does not happen automatically just by enabling `readPreference=secondaryPreferred`.
- The session must be **maintained consistently** across the operation chain; you cannot independently create a new session in each service and expect them to share causal history.
- Latency may increase or requests may time out when a secondary cannot catch up quickly enough.
- Strong guarantees do not hold if the application uses unsuitable read/write concerns, mixes sessions arbitrarily, or fails to preserve operation ordering.
- Causal consistency does not replace transactions for multi-document invariants.

### 10.3. Java driver example: causal session with a secondary

The snippet below illustrates an intentional configuration; it assumes `client` is connected to a replica set with primary/secondaries, MongoDB supports sessions, and the caller keeps the same session:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public void writeThenCausallyRead(MongoClient client) {
    MongoCollection<Document> collection = client
        .getDatabase("shop")
        .getCollection("orders");

    MongoCollection<Document> writer = collection
        .withWriteConcern(WriteConcern.MAJORITY);

    MongoCollection<Document> reader = collection
        .withReadPreference(ReadPreference.secondary())
        .withReadConcern(ReadConcern.MAJORITY);

    ClientSessionOptions options = ClientSessionOptions.builder()
        .causallyConsistent(true)
        .build();

    try (ClientSession session = client.startSession(options)) {
        writer.updateOne(
            session,
            new Document("_id", "ORD-101"),
            new Document("$set",
                new Document("status", "PAID")));

        Document observed = reader.find(
                session, new Document("_id", "ORD-101"))
            .first();

        if (observed == null) {
            throw new IllegalStateException("Order not found");
        }
        System.out.println(observed.getString("status"));
    }
}
```

This example should only be run against a test database and an existing document. `ClientSession` must not be used concurrently by multiple uncontrolled threads; operations in the causal chain must execute sequentially per the contract. If no valid secondary exists, `ReadPreference.secondary()` may fail; if the secondary is lagging, the read may block waiting. Appropriate timeouts and error handling must be configured for your SLA.

**Important:** this code demonstrates the causal consistency mechanism; it **does not prove every read from a secondary is up-to-date relative to all other clients**. It applies only to causal relationships tracked within the session under supported conditions.

### 10.4. Read-after-write across multiple HTTP requests

If a frontend sends a POST in request 1 and a GET in request 2, the two requests may reach different application instances using different sessions. In that case, you must not assume a `ClientSession` held in request 1 is automatically reused for request 2.

Design options:

- Read from the primary for the confirmation endpoint immediately following a write.
- Return the confirmed information directly in the write response, if the contract allows.
- Propagate session/causal tokens across requests **only when security, token lifecycle, and driver support are clearly designed**.
- Accept eventual consistency and show UX/status such as "syncing" with bounded polling if the business truly tolerates it.

Do not solve this by pinning an arbitrary `ThreadLocal` and assuming all server instances share the same session.

## 11. Consistency states to classify before choosing a mode

| Business requirement | What is actually needed | Suggested read preference |
| --- | --- | --- |
| View an order just successfully written | Read-your-writes or just-confirmed data | `primary` is usually a simple first step |
| Check balance to decide a payment | Avoid deciding on stale state; protect concurrent updates | `primary` + appropriate atomic update/transaction/CAS |
| Hourly order count dashboard | Eventual consistency with a lag SLA | `secondaryPreferred` or `secondary` per load policy |
| Export a large analytical report | Usually tolerates bounded lag | `secondary` + lag monitoring and chosen read concern |
| Rarely changing catalog | Can tolerate stale data | `primaryPreferred` or `nearest` if evaluated |
| Check access permissions or soft delete | Leakage risk if reading a stale snapshot | Prefer a read path ensuring current policy and authorization design |
| Multi-step transaction | Transaction/session per DB contract | Do not arbitrarily choose secondary if the transaction requires primary |

**A single default configuration is rarely sufficient for every query type.** Separating workloads with different consistency constraints and costs helps you choose read preferences intentionally.

## 12. Replica set failover and fallback behavior

Suppose P is primary and S1/S2 are secondaries:

```text
Before failover:
  P = PRIMARY
  S1, S2 = SECONDARY

During election:
  P loses role or connectivity
  No PRIMARY visible to the client yet
  S1/S2 may still be readable (depending on state/topology)

After election:
  S1 = new PRIMARY
  S2 = SECONDARY
```

During the window without a primary:

- `primary`: no suitable server; reads may wait until timeout or until a new primary is elected.
- `primaryPreferred`: may read from a currently eligible secondary; data may lag.
- `secondary`: continues reading from a secondary while an eligible secondary exists.
- `secondaryPreferred`: continues preferring a secondary; when no eligible secondary remains, may fall back to primary if one is available.
- `nearest`: picks an eligible member by latency, without guaranteeing role or freshness.

**Do not promise that read preference automatically completes every request during failover.** Topology state changes, the driver must discover the election, and networks can flap; some in-flight reads may fail, conditionally retry, or time out.

### 12.1. Retryable reads are not unlimited retries

The MongoDB driver can retry certain supported read types upon transient errors. This does not mean:

- Every command is retryable.
- A read automatically turns into a transaction or becomes more consistent.
- Aggregations with write stages (`$out`/`$merge`) are treated as pure reads.
- You should keep retrying a request when no secondary is eligible.

Choose appropriate timeouts, retry limits, idempotency for operations with side effects, and degradation policies. When server selection cannot find a node, returning a clear service error is usually better than waiting indefinitely.

## 13. Configuring read preference via connection string

A connection string connects to the **replica set**, not a single secondary hostname:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=primary
```

Example switching to secondary-preferred reads:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondaryPreferred
```

`db1/db2/db3` are **illustrative hostnames**, not servers you can connect to immediately. Use your environment's actual DNS/credentials/TLS/replica-set name, and manage URIs containing passwords with a secret manager rather than committing them to Git.

| URI option | Meaning |
| --- | --- |
| `replicaSet=rs0` | Identifies the replica set the client expects to connect to |
| `readPreference=primary` | Read only from primary |
| `readPreference=secondary` | Read only from secondary |
| `readPreference=secondaryPreferred` | Prefer secondary, fall back to primary per rules |
| `readPreference=primaryPreferred` | Prefer primary, fall back to secondary |
| `readPreference=nearest` | Select an eligible member based on network latency |
| `readPreferenceTags=...` | Prioritize/select members by tag sets when the mode permits |
| `maxStalenessSeconds=...` | Exclude secondaries estimated to be too stale per policy |
| `serverSelectionTimeoutMS=...` | Limit how long the driver waits for an eligible server |

### 13.1. Spring Boot application configuration

In many Spring Boot 3.x projects, the default URI is configured via:

```properties
spring.data.mongodb.uri=mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=primary
```

Across framework major versions, **MongoDB configuration property names may differ**; verify against the Spring Boot version your project actually uses. This example shows that **MongoDB driver URI parameters** are what determine read preference.

If you change this URI to `secondaryPreferred` for an application sharing a single `MongoTemplate`, many repository reads and template reads may be affected. This is why you should not change the default read preference of **the entire application** just to optimize one report.

### 13.2. Do not use directConnection to simulate replica-set routing

In some `directConnection=true` configurations, the client connects directly to one member instead of performing normal topology discovery/routing. This differs semantically from connecting to a replica set and letting the driver select members according to read preference.

When you want to shift reads from primary to secondary in a replica set, let the driver **discover topology** properly; do not hardcode a hostname that happens to be a secondary and hope it keeps that role after failover. With MongoDB Atlas/SRV, use the provider-supplied URI and add options according to the corresponding documentation.

## 14. Java driver: client-level configuration

The MongoDB Java driver provides `com.mongodb.ReadPreference`. The code below creates clients with a global read preference for reads using that client.

File `MongoReadClientFactory.java`:

```java
package com.example.shop.config;

import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoReadClientFactory {

    private MongoReadClientFactory() {}

    public static MongoClient primaryClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.primary())
            .build();

        return MongoClients.create(settings);
    }

    public static MongoClient reportingClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.secondaryPreferred())
            .build();

        return MongoClients.create(settings);
    }
}
```

`applyConnectionString` reads the URI options. The subsequent `readPreference(...)` call sets the read preference explicitly chosen by the code; if the URI contains a different value, define a clear configuration rule to avoid hard-to-spot conflicts.

A client is an object normally **reused** long-term with its connection pool, not created per HTTP request. Manage the lifecycle of `MongoClient`, close it on application shutdown, and do not share credentials with broader privileges than required.

### 14.1. Setting read preference on a MongoCollection

When only a reporting task needs a secondary, the Java driver can set read preference directly on a collection handle:

```java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> reportingOrders = client
    .getDatabase("shop")
    .getCollection("orders")
    .withReadPreference(ReadPreference.secondary());

Document row = reportingOrders
    .find(new Document("_id", "ORD-101"))
    .first();
```

This snippet lives inside a method with an injected `MongoClient client`. `MongoCollection.withReadPreference(...)` creates a collection handle with that option; it does not change the read preference of other collections on the same client.

**Note on Spring Data mapping:** this is the **MongoDB driver API**, returning `org.bson.Document` rather than automatically mapping into entities via `MongoTemplate` converters. For business logic relying on `@Field`, custom converters, or callbacks, use a properly configured `MongoTemplate` or carefully manage output mapping yourself.

### 14.2. Read preference does not route writes to secondaries

Setting `ReadPreference.secondary()` does not cause `insertOne` or `updateOne` to execute directly on a secondary. In a replica set, ordinary writes are still sent to the primary; writes on a secondary that does not accept writes will not be accepted as on the primary.

This is crucial when naming `reportingClient` or `reportingTemplate`: the name **is not a read-only authorization mechanism**. If you need read-only enforcement, use a MongoDB user/role with read-only permissions, API controls, and dedicated reporting job configuration.

## 15. Spring Data MongoDB: keep the write path accurate, separate the reporting path

In an application handling both transactions and reporting, an understandable structure is:

```text
Application Service
    |
    +-- OrderRepository (default primary MongoTemplate)
    |       |
    |       +-- create/update/delete; read-after-write
    |
    +-- ReportingService (reportingMongoTemplate)
            |
            +-- aggregate/read accepting eventual consistency
                    |
                    +-- MongoClient readPreference=secondaryPreferred
```

**Separating templates separates read configuration**, not logical databases: both clients can still point to the same replica set and collection. MongoDB authorization and data state rules must be enforced consistently across both paths.

### 15.1. Example with two MongoTemplate beans

The example below intentionally configures clients/templates explicitly to control routing. File `MongoRoutingConfiguration.java`:

```java
package com.example.shop.config;

import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration(proxyBeanMethods = false)
public class MongoRoutingConfiguration {

    private static MongoClient client(
            String uri, ReadPreference readPreference) {

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(readPreference)
            .build();

        return MongoClients.create(settings);
    }

    @Bean(name = "primaryMongoClient", destroyMethod = "close")
    @Primary
    public MongoClient primaryMongoClient(Environment env) {
        return client(
            env.getRequiredProperty("app.mongo.uri"),
            ReadPreference.primary());
    }

    @Bean(name = "reportingMongoClient", destroyMethod = "close")
    public MongoClient reportingMongoClient(Environment env) {
        return client(
            env.getRequiredProperty("app.mongo.uri"),
            ReadPreference.secondaryPreferred());
    }

    @Bean(name = "mongoTemplate")
    @Primary
    public MongoTemplate mongoTemplate(
            @Qualifier("primaryMongoClient") MongoClient client) {

        return new MongoTemplate(
            new SimpleMongoClientDatabaseFactory(client, "shop"));
    }

    @Bean(name = "reportingMongoTemplate")
    public MongoTemplate reportingMongoTemplate(
            @Qualifier("reportingMongoClient") MongoClient client) {

        return new MongoTemplate(
            new SimpleMongoClientDatabaseFactory(client, "shop"));
    }
}
```

The example makes `app.mongo.uri` a **project property** (not a mandatory built-in Spring Boot property) and selects database `shop` for both templates. With multiple `MongoClient`/template beans, **check autoconfiguration/repository scanning** in your actual Spring Boot version to avoid duplicate or miswired beans. If using custom `@EnableMongoRepositories`, you can specify `mongoTemplateRef = "mongoTemplate"` to explicitly bind standard repositories to the primary template.

Do not copy this configuration verbatim into an application that already has its own MongoDB routing and end up creating two duplicate sets of beans. This is an **architectural pattern** that must be integrated with existing security, TLS, sessions, metrics, and transaction managers.

### 15.2. Reporting service using a dedicated reportingMongoTemplate

File `OrderReportingService.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderReportingService {

    private final MongoTemplate reportingTemplate;

    public OrderReportingService(
            @Qualifier("reportingMongoTemplate")
            MongoTemplate reportingTemplate) {
        this.reportingTemplate = reportingTemplate;
    }

    public List<Document> countPaidOrdersByChannel(
            String permittedTenantId) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant");
        }

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
                    .and("status").is("PAID")),
            Aggregation.group("channel")
                .count().as("orders"),
            Aggregation.project("orders")
                .and("_id").as("channel")
                .andExclude("_id")
        );

        return reportingTemplate.aggregate(
                pipeline, "orders", Document.class)
            .getMappedResults();
    }
}
```

This report counts `PAID` orders by sales channel based on data currently present on the selected node. **If an order was just paid, the total may not have incremented yet on the secondary.** The report's SLA should explicitly state that lag is tolerated; never use this figure as the source of truth for payment decisions or immediate ledger posting.

### 15.3. Default repositories and @Aggregation

If `OrderRepository` is backed by the primary `mongoTemplate`, derived queries and `@Aggregation` on that repository normally use the primary configuration path. Switching reads to a secondary via an annotation **does not always have a single universal annotation available across all Spring Data versions**. Do not assume every repository method supports declaring per-method read preference identically across major versions.

For a reporting pipeline needing clear routing, a repository fragment or query service using an explicitly injected `reportingMongoTemplate` is usually easier to understand and integration-test. If your running version supports an API to override read preference per operation, still verify it takes effect for the specific aggregation command type.

### 15.4. Reactive path

If the application uses `ReactiveMongoTemplate`, choosing read preference happens via the corresponding reactive MongoDB client/factory. The nature of a replica set does not change:

- Choosing a secondary still carries stale read risk.
- A `Flux` does not automatically provide read-your-writes.
- Do not use blocking `MongoTemplate` inside the reactive event loop.
- Sessions/causal consistency require the reactive session API and actually supported read/write concerns.

Do not assume switching to reactive reduces replication lag or makes data fresher.

## 16. Tag sets: selecting the right kind of secondary for the workload

Replica set members can be tagged with metadata by administrators, for example:

```javascript
// Illustration of tags configured by a replica set administrator:
{
  "db1.example.net:27017": { region: "north", workload: "primary" },
  "db2.example.net:27017": { region: "south", workload: "reporting" },
  "db3.example.net:27017": { region: "north", workload: "general" }
}
```

This is an **illustrative tag diagram**, not a replica set configuration command. Actual tagging must be deployed and verified on members by administrators. A tag does not change primary/secondary roles, does not create the ability to read the latest data, and does not replace security.

### 16.1. URI filtering secondaries by tag

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting
```

This mode requires a secondary matching the `workload:reporting` tag. If no eligible secondary exists, the driver **does not automatically fall back to primary** because the mode is `secondary`; the read may fail after the server-selection timeout.

### 16.2. Multiple tag sets in priority order

Some URIs allow declaring multiple `readPreferenceTags` in order:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting&readPreferenceTags=region:north&readPreferenceTags=
```

The intent is to prefer a secondary with `workload:reporting`, if unavailable consider the next tag set, and finally allow any secondary via an empty tag set. Verify URL encoding syntax and selection results against the MongoDB driver version in use.

**Note:** `readPreferenceTags` is not used with ordinary `primary` mode. With `primaryPreferred`, the primary is chosen first and tags mainly apply to the secondary fallback path. Do not configure tags expecting them to "filter" the primary the same way as secondaries in all modes.

### 16.3. Tags do not guarantee the same server

Tags identify a pool of eligible members. If multiple secondaries match and have similar latency, the driver may pick different members across queries. When a secondary changes role to primary after an election, member selection continues to depend on **mode + topology**, not just tags remaining on the host.

If a workload requires **pinning one exact server** for investigation or backup, that is a different operational concern; do not use `readPreferenceTags` as a sticky session lock for application requests.

## 17. maxStalenessSeconds: filtering out overly lagging secondaries

`maxStalenessSeconds` lets the driver exclude secondaries **estimated to be too far behind** replica set progress according to the server selection algorithm.

Example:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&maxStalenessSeconds=120
```

Meaning: exclude secondaries whose **estimated** staleness exceeds roughly two minutes under server selection rules.

### 17.1. Not a hard SLA of "data <= 120 seconds old"

This is a **server selection** constraint, not a command forcing the server to wait until a specific write arrives. The MongoDB driver calculates staleness from topology/replication information that itself has collection lag. The result is approximate and does not guarantee:

- Every most recent write is present in the query.
- The snapshot point is never older than exactly `120` seconds under all conditions.
- Queries always return results even when no eligible secondary remains.
- The client gets read-your-writes like a causal session.

If the requirement is "users must see the operation they just completed," do not use `maxStalenessSeconds` instead of primary reads or causal consistency.

### 17.2. Value limits

The MongoDB driver requires a minimum `maxStalenessSeconds` under server selection rules; in common replica set configurations, **the minimum is 90 seconds** and also depends on heartbeat interval plus a safety margin. Do not set `maxStalenessSeconds=3` expecting secondaries to lag by at most three seconds: the driver/server may reject the configuration.

If a report's SLA allows at most **5 seconds** of lag, `maxStalenessSeconds` alone cannot meet that SLA. You need a different read model, lag metrics, and a way to check result freshness.

### 17.3. Combining tags and staleness

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:reporting&maxStalenessSeconds=120
```

The driver picks a secondary matching the tag and meeting the staleness criterion. If the reporting machine lags past the threshold, **no suitable server may remain** and requests will error. This may be **desired** behavior to avoid returning overly stale data, but it must be accounted for in the product's SLA and fallback handling.

### 17.4. secondaryPreferred may fall back to primary

With `secondaryPreferred`, when no eligible secondary remains due to tags/staleness/topology, the driver may select the primary. If the goal of `maxStalenessSeconds` is **never to put reporting load on the primary**, reconsider: `secondaryPreferred` does not promise load isolation. For strict isolation, `secondary` is clearer.

## 18. Latency window, server selection timeout, and throughput limits

In `nearest` read preference, the driver selects from eligible servers falling within a latency range (*latency window*) of the fastest responding server. The default is typically **15 ms**, though configurable; check your current driver to avoid guessing.

### 18.1. Fast network does not guarantee a fast query

A secondary with low ping but high CPU or missing indexes for the query can still respond slowly. Server selection does not replace:

- Designing compound/multikey indexes.
- Bounding page size, batch size, and response payload.
- Optimizing aggregations (early `$match`, avoiding unnecessary `$unwind`/`$group`).
- Monitoring memory, I/O, and replication lag on each member.

### 18.2. Server selection timeout

URI example:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0&readPreference=secondary&serverSelectionTimeoutMS=5000
```

If no secondary can be selected within the configured duration, the driver may raise a server-selection timeout. Increasing the timeout can help ride out short elections, but **also prolongs user wait time**. Define SLAs and timeouts at the driver, service layer, load balancer/gateway, and ensure errors are mapped cleanly back to the API.

### 18.3. Do not create too many MongoClient instances needlessly

Two clients with different read preferences create corresponding connection pools. Across many service instances, this multiplies total connections to the replica set. Only create separate clients/templates when SLA and routing differences justify it; monitor pool size, connection churn, and request counts per node.

## 19. Read preference with aggregations and special operations

Not every "read-like" command is a plain `find`:

| Operation | What to watch out for |
| --- | --- |
| `find`, `countDocuments` on a collection | Can usually be served per read preference when topology allows |
| Aggregation with only `$match/$group/$project` | Can use a secondary if the command/server supports it |
| Aggregation containing `$lookup` | Can read multiple collections; watch read concern and replication lag on joined data |
| Aggregation with `$out` or `$merge` | Has **write side effects**; do not treat as a read-only query or assume read preference applies like a normal aggregate |
| Multi-document transaction | Requires session/transaction options; **primary read preference** is generally required by transactions |
| `findAndModify` / find-and-update | Is a **write** operation; do not route to secondary just because it returns a document |
| Change streams | Have their own change-tracking mechanisms and requirements; do not use `readPreference` alone to promise instant sync |

A `$lookup` pipeline on a secondary may observe replicated states across collections that are out of sync with business intent unless an appropriate snapshot/consistency mechanism is used. If a financial report needs figures consistent at a point in time, define snapshot/read concern rather than just picking `secondary` for speed.

### 19.1. Transactions: keep primary and clear scope

In MongoDB, multi-document transactions use sessions and impose specific requirements on read preference; **primary** is required in transaction scenarios supported by the MongoDB protocol. Do not start a transaction on a `reportingMongoTemplate` configured with `secondaryPreferred` expecting reads inside the transaction to run on secondaries.

With Spring Data, `MongoTransactionManager`/reactive transaction manager must be bound to the proper database factory and session. If multiple clients/templates exist, a transaction does not automatically span across another client/factory. This matters when a repository acts on primary while a service simultaneously invokes a reporting template using secondaries.

### 19.2. Reading from a secondary does not make financial reports accurate

Even after replication catches up, a report can still be wrong due to:

- Using `Double` for money instead of `Decimal128`/integer minor units.
- Aggregations missing status/tenant predicates.
- Soft-deleted records not filtered out by the report.
- Summing across orders after an `$unwind` multiplies rows.
- Reading pages at different points in time while totals are changing.

Read preference is only **one** factor in data quality assurance.

## 20. Integration testing: requires a multi-member replica set

A `@DataMongoTest` connecting to a standalone MongoDB can verify repository mapping, but **cannot prove** read preference routes to primary or secondary properly. Even a Testcontainers MongoDB configured as a **single-member replica set** still **has no secondary** to test.

This topic requires a test replica set environment with:

- An elected primary and at least one active secondary.
- A test account with read/write privileges on a **dedicated test database**.
- `majority` write concern supported and reasonable timeouts.
- Hostnames/network properly discoverable and reachable by the driver (not just an unreachable container internal address).
- No assumption that "a secondary is always stale for N seconds": replication can be fast enough that an immediate test read already sees the new data.

### 20.1. Testing eventual convergence with the Java driver

JUnit 5 example (runs **only when** `TEST_MONGODB_REPLICA_URI` points to a real test replica set):

```java
package com.example.shop.consistency;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import java.time.Duration;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ReplicaReadPreferenceIntegrationTest {

    @Test
    void primaryWriteEventuallyAppearsOnSecondary()
            throws InterruptedException {

        String uri = System.getenv("TEST_MONGODB_REPLICA_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Requires a test replica set with primary and secondary");

        try (MongoClient client = MongoClients.create(uri)) {
            // Use a TEST database only, never share with production.
            MongoCollection<Document> base = client
                .getDatabase("read_pref_it")
                .getCollection("orders");

            MongoCollection<Document> primary = base
                .withReadPreference(ReadPreference.primary())
                .withWriteConcern(WriteConcern.MAJORITY);

            MongoCollection<Document> secondary = base
                .withReadPreference(ReadPreference.secondary())
                .withReadConcern(ReadConcern.MAJORITY);

            String id = "RP-" + UUID.randomUUID();

            try {
                primary.insertOne(
                    new Document("_id", id)
                        .append("status", "NEW")
                        .append("tenantId", "TENANT-TEST"));

                primary.updateOne(
                    new Document("_id", id),
                    new Document("$set",
                        new Document("status", "PAID")));

                // Primary already acknowledged the new status.
                Document onPrimary = primary.find(
                    new Document("_id", id)).first();

                assertThat(onPrimary).isNotNull();
                assertThat(onPrimary.getString("status"))
                    .isEqualTo("PAID");

                // Do not assert that secondary MUST be stale right after write.
                // Wait with a bounded timeout for the secondary to catch up.
                long deadline = System.nanoTime()
                    + Duration.ofSeconds(30).toNanos();

                Document onSecondary = null;
                while (System.nanoTime() < deadline) {
                    onSecondary = secondary.find(
                        new Document("_id", id)).first();

                    if (onSecondary != null
                            && "PAID".equals(
                                onSecondary.getString("status"))) {
                        break;
                    }
                    Thread.sleep(250);
                }

                assertThat(onSecondary).isNotNull();
                assertThat(onSecondary.getString("status"))
                    .isEqualTo("PAID");
            } finally {
                primary.deleteOne(new Document("_id", id));
            }
        }
    }
}
```

**Test limitations:**

1. Checking eventual convergence **cannot prove the secondary will lag**: the server may replicate almost instantaneously.
2. If the secondary is unavailable or unreachable by the driver, `secondary.find(...)` may throw a server-selection timeout; this indicates a test setup or availability issue to investigate.
3. Each `find` call inside the loop has its own timeout. Set server-selection timeout/maxTime appropriately for the environment so a single read does not exceed the whole test's budget.
4. Majority write concern provides better acknowledgment guarantees but does not let you conclude **all** secondaries have already updated.
5. Cleanup uses `deleteOne` by random ID on a test database; do not use `dropDatabase`/`deleteMany({})` on a shared test environment.
6. In parallel CI runs, random IDs avoid collisions, though they do not replace credential/database isolation.

This test is **illustrative example code to implement and run in a suitable replica set environment**, not executed during document authoring.

### 20.2. Testing when no secondary is available

A separate test can run against a single-member replica set:

```java
MongoCollection<Document> onlySecondary = client
    .getDatabase("read_pref_it")
    .getCollection("orders")
    .withReadPreference(ReadPreference.secondary());

// In a replica set with no SECONDARY, the read has no eligible
// node and may time out; do not expect automatic fallback to PRIMARY.
onlySecondary.find(new Document("_id", "RP-DEMO")).first();
```

This snippet illustrates an **expected-failure case**, not a complete test assertion. In a real test, configure a short but reliable `serverSelectionTimeoutMS`, use `assertThatThrownBy`/`assertThrows` for the exception thrown by that driver version, and inspect the cause details.

Contrast with `secondaryPreferred`: if the replica set has a primary but no eligible secondary, preferred mode can read from the primary. With a healthy primary, this experiment clarifies the difference between **isolation** (`secondary`) and **availability fallback** (`secondaryPreferred`).

### 20.3. Never run tests that kill the primary in production

Testing failover/election requires a dedicated environment and infrastructure coordination rights:

```text
Phase 1: P is primary; S1/S2 are secondaries.
Phase 2: simulate P losing its role in a test cluster.
Phase 3: verify the app detects election, timeouts/retries work properly.
Phase 4: after a new primary emerges, reads/writes recover.
Phase 5: verify data and ensure retries caused no unintended side effects.
```

Do not provide an `rs.stepDown(...)` command to run casually in a shared system. How failover is triggered depends on topology and operational policy; perform it only on an authorized test cluster.

### 20.4. Test matrix by read preference

| Scenario | primary | primaryPreferred | secondary | secondaryPreferred | nearest |
| --- | --- | --- | --- | --- | --- |
| Primary and secondaries healthy | Primary | Primary | Secondary | Secondary | Eligible node by latency |
| No eligible secondary, primary available | Primary | Primary | None selectable | Falls back to primary | Primary if eligible |
| Temporarily no primary, eligible secondary | None selectable | Secondary | Secondary | Secondary | Secondary if eligible |
| Secondary lag exceeds max staleness | Does not affect primary selection | May pick primary or eligible secondary | May have none selectable | May fall back to primary | Considers eligible members only |
| Secondary catches up immediately | Reads fresh value from primary | Usually primary | May already see fresh | May already see fresh | Depends on node |
| Secondary has not caught up | Reads from primary | Usually primary | May be stale | May be stale | May be stale if secondary chosen |

This matrix is a **model by topology state**, not a promise that requests succeed at every moment. Auth, network, server selection, read concern, timeouts, and operations that do not support secondary reads also apply.

## 21. Observing replication lag and server selection

To safely leverage secondaries, monitor how well they keep up with the primary. **Do not just monitor primary CPU dropping after turning on `secondaryPreferred`.**

### 21.1. Checking replica set status

In `mongosh` with appropriate administrative privileges:

```javascript
rs.status()
```

When permitted, you can inspect diagnostic fields such as:

```javascript
const status = rs.status();

status.members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost
}));
```

Present fields and display details vary by version/topology; this is administrative observation, not a business API. Use cluster/cloud provider monitoring for reliable replication lag metrics and historical charts.

### 21.2. Also inspect client/server selection logs

Indicators:

- Driver reports no suitable secondary found.
- Newly configured tags match no member.
- `maxStalenessSeconds` excludes all secondaries.
- A replica set member address is only reachable from another network.
- Frequent elections occur, or the client connects with the wrong replica-set name.
- Reports still run on the primary because `secondaryPreferred` fell back.

`hello`/`isWritablePrimary` output from a separate connection helps investigate server roles, but **do not treat a manually issued hello command as proof that all application queries run on that server**. To verify actual routing, use command monitoring/driver logs, server-side metrics, and topology monitoring for your driver version.

### 21.3. Metrics to monitor

| Metric | What it reveals |
| --- | --- |
| Replication lag per secondary | Risk of stale reports, slow apply |
| Read ops/QPS per member | Whether reporting load truly left the primary |
| CPU, RAM, disk I/O on secondaries | Whether reports compete with replication resources |
| Server selection failures/timeouts | No eligible member or network errors |
| Query latency p50/p95/p99 per operation | Impact on user SLAs |
| Secondary rollback/election events | Topology changes, reliability |
| Number of connections/pools per client | Overhead from using multiple MongoClients |
| Keys/docs examined for report queries | Index fitness, whether queries scan broadly |

If a report requires data no older than 60 seconds, merely setting `maxStalenessSeconds=120` **does not directly satisfy** that requirement. You need a way to measure the freshness of returned data, or primary reads/causal consistency as required.

### 21.4. Document timestamps do not measure replication lag by themselves

An `updatedAt` field written by the application may come from an app server clock, not necessarily server commit time; different clocks can drift. When determining replication lag, prefer MongoDB's replication/optime metrics and monitoring systems rather than computing `now() - updatedAt` on an arbitrary document as lag evidence.

## 22. Production diagnostic scenarios

### 22.1. "Order placed, but the list page does not show the order"

**Possible cause:** write succeeded on primary, then the list API routed to a secondary that had not replicated yet.

**Checks:** read the same `_id` from primary; read from secondary; determine current read preference, lag, and write concern. Before concluding it is a stale read, also verify tenant filters, soft-delete, status, and pagination.

**Remediation:** route the immediate post-create confirmation endpoint through primary; or design a causal read with appropriate majority/session if secondary is needed. Do not blindly retry 100 times until it "looks right."

### 22.2. "SecondaryPreferred still overloads the primary"

**Possible cause:** no eligible secondary due to outage, tag mismatch, staleness, network, or too few members. The driver falls back to primary per policy.

**Checks:** topology, tag sets, max staleness, command/server metrics. Identify which reads are heavy reports.

**Remediation:** if strict isolation is required, use `secondary` with clear timeout/error bounds; scale secondary capacity as needed; optimize pipelines and indexes. Do not fix it by increasing timeouts indefinitely.

### 22.3. "Secondary read times out even though rs.status() shows SECONDARY"

**Possible cause:** server address unreachable from the app, server ineligible, tag mismatch, staleness, stale driver topology view, or overloaded server.

**Checks:** connection URI, replica-set member hostnames, TLS/auth, `serverSelectionTimeoutMS`, tags, maxStaleness, and metrics. A member appearing as SECONDARY from an admin environment does not prove the application can reach it.

### 22.4. "Already using read concern majority, yet still reading old status"

**Cause:** `majority` speaks to reading majority-committed state, and does not automatically ensure a secondary node has caught up to **a specific write from the current client**.

**Remediation:** distinguish majority durability from read-your-writes; use the same causal session and majority read/write concern when supported by design, or read from primary. Check timeouts when a secondary must wait causally.

### 22.5. "Reports occasionally show fluctuating totals"

**Possible causes:** consecutive requests hitting secondaries with different lag; data changing concurrently; paginated reports without a snapshot; queries with differing filters.

**Remediation:** define a consistent point-in-time/snapshot if required, cache/materialize reports, attach a meaningful business as-of timestamp, and verify stable pagination/sorting. Do not assume a single read preference setting solves all discrepancies.

## 23. Misconceptions to avoid

| Misconception | Correct understanding |
| --- | --- |
| `primary` means all reads are linearizable | Read preference only picks the server; suitable read/write concerns and conditions are still needed |
| `secondary` is always faster than primary | A secondary can lag, overload, or lack indexes; measure it |
| `secondaryPreferred` never increases primary load | When no eligible secondary exists, it can fall back to primary |
| `primaryPreferred` always returns fresh results | When the primary is absent, secondary fallback can return stale data |
| `nearest` always picks the closest secondary | It can pick the primary and uses network latency **from the client**, not end-user location |
| `writeConcern: majority` makes every secondary have the write | It only requires a majority per acknowledgment rules |
| `readConcern: majority` makes secondaries have the latest write | Majority-committed does not automatically give read-your-writes from an arbitrary secondary |
| `maxStalenessSeconds=120` guarantees data is fresh within 120 seconds | It is only an estimated server-selection limit, not a hard freshness SLA |
| `maxStalenessSeconds=5` forces at most 5 seconds of staleness | Violates the common minimum limit; another consistency design is needed |
| Three hosts in the URI means the driver round-robins reads across all three | Mode, topology, latency, tags, and staleness govern selection |
| Specifying a fixed secondary hostname always reads from a secondary | Members can change roles after an election |
| Setting read preference on a reporting template makes it read-only | Writes still go to primary; read-only is an RBAC/architectural requirement |
| Creating many MongoClients costs no resources | Each client has pools and monitoring/connection overhead |
| `@Aggregation` always runs on primary | Depends on the template/client and aggregate type; verify configuration |
| `findAndModify` is a read because it returns a document | It is a data-modifying operation needing write semantics |
| Streaming/reactive eliminates replication lag | Changing how results are consumed does not change replica apply speed |
| Any session guarantees causal consistency | You must maintain the same session/ordering and supported read/write concerns |
| Stale queries can be fixed with a unique index | Indexes support performance/uniqueness, not replication lag |
| Read preference protects tenant isolation | Tenant scoping and authorization are completely independent |

## 24. Application read preference design checklist

Before deploying a secondary read route, answer:

1. **What decision does the read path serve?** Transaction confirmation, display, reporting, or an action leading to a write?
2. **What freshness is desired?** Must newly written data appear immediately, or is 30 seconds / 5 minutes of lag acceptable?
3. **Is freshness a security requirement?** Could recently revoked permissions, soft deletes, or locked account states cause leaks if read stale?
4. **Is read-after-write needed across requests?** Within one session or across different application instances?
5. **Which write/read concerns are used?** Does majority meet durability, and does the session meet causal consistency?
6. **Does the fallback mode match the SLA?** `secondaryPreferred` can raise primary load; `secondary` can cause unavailability.
7. **Does the topology have enough members?** Real replica set or standalone/single-member test?
8. **Which members do tags and staleness exclude?** Verify enough secondaries remain eligible under real conditions.
9. **Are server-selection timeout, query timeout, and retries bounded?**
10. **Are you using one client or multiple clients?** Are bean naming, transaction/session wiring, and lifecycle clear?
11. **Do read workloads have indexes and `explain` plans?** Avoid heavy report loads causing secondary replication lag.
12. **Have you tested failover on a test cluster?** Observe routing, errors, availability, and data during elections.
13. **Are replication lag and read ops monitored per member?** Do not look only at aggregate API latency.
14. **Is there a degraded mode when no secondary remains?** Clear error, data-age-labeled cache, or approved fallback.
15. **Are there integration tests for read-only/causal sessions?** Avoid tests assuming fixed replication delay.
16. **Have you checked cloud/driver/server versions?** Some operations have specific routing restrictions.

## 25. Mode selection workflow by SLA

```text
Does the read require seeing the result of a just-acknowledged write?
    |
    +-- Yes --> primary is the simple starting choice
    |           or a designed/verified causal session.
    |
    +-- No  --> Can stale data be tolerated?
                 |
                 +-- No  --> determine required read concern/
                 |           snapshot and consistency.
                 |
                 +-- Yes --> Must it never run on primary?
                            |
                            +-- Yes --> secondary; manage unavailability,
                            |           tags, lag, timeouts, and capacity.
                            |
                            +-- No  --> secondaryPreferred or
                                        primaryPreferred/nearest
                                        depending on availability,
                                        latency, and freshness goals.
```

This is a **decision workflow**, not a substitute for measuring real data. Systems with strict financial/regulatory rules must design readConcern/transactions and snapshot recording separately before picking a mode.

### 25.1. One application configuration does not equal one SLA

E-commerce application example:

- **OrderCommandService:** writes and reads order confirmations using primary, version/CAS, or transactions as required.
- **OrderQueryService:** regularly reads orders from primary when users expect to see fresh changes.
- **CatalogReadService:** can use `secondaryPreferred` if product updates do not require real-time freshness.
- **RevenueReportingService:** reads from a dedicated secondary with workload tags and staleness policy, with clear error handling/load limits.
- **SecurityCheckService:** checks permissions and access policies from a designed consistent source; never blindly use a stale secondary just because the query is a `find`.

This organization separates **consistency classification by use case**, rather than forcing `secondaryPreferred` across the entire application and fixing resulting bugs afterward.

## 26. Hands-on exercises

An inventory management system runs a three-member replica set. `InventoryCommandService` writes stock updates on the primary, while `InventoryDashboardService` runs an aggregation every minute. Two user roles:

- **Warehouse clerk:** after deducting 5 items, must see the updated quantity to decide whether further dispatch is allowed.
- **Manager:** only needs a low-stock top SKU summary, tolerates 2–3 minutes of lag, and does not want heavy reports competing with primary I/O.

### Exercise 1: choosing read preference

Propose suitable modes for:

1. Reading right after an inventory deduction command.
2. Scheduled dashboard that can be stale.
3. Product catalog API during a primary election.
4. Queries served only when a reporting secondary is available, with no primary fallback.
5. Lowest network latency queries in a multi-region cluster.

Explain the specific freshness/fallback limitations of each proposal.

### Exercise 2: writing URIs

Create connection strings for:

```text
Replica set: rs0
Members: inv1.example.net:27017, inv2.example.net:27017, inv3.example.net:27017
Database: warehouse
```

Requirements:

1. Command client uses `primary`.
2. Reporting client uses `secondary`.
3. Reporting client selects only secondaries tagged `workload:analytics`.
4. Use `maxStalenessSeconds=120` to filter out secondaries estimated to be too slow.
5. Add `serverSelectionTimeoutMS=5000` and describe the impact when no secondary exists.

**Suggested configuration:**

```text
mongodb://inv1.example.net:27017,inv2.example.net:27017,inv3.example.net:27017/warehouse?replicaSet=rs0&readPreference=secondary&readPreferenceTags=workload:analytics&maxStalenessSeconds=120&serverSelectionTimeoutMS=5000
```

These hostnames are examples only. Verify that tags are configured by administrators, the replica set has eligible secondaries, the URI uses environment-appropriate auth/TLS, and credentials are never committed to the repository.

### Exercise 3: Java driver and Spring Data

1. Use `MongoClientSettings` to build two clients: one `primary`, one `secondaryPreferred`.
2. Create two `MongoTemplate` beans with `SimpleMongoClientDatabaseFactory`.
3. Use `@Qualifier` so reporting only calls the reporting template.
4. Show why default repositories remain bound to the primary template.
5. Explain why the reporting template **must not be called read-only** without write permission limits.
6. When transactions are used, identify which factory `MongoTransactionManager` uses and why templates cannot be mixed arbitrarily.

### Exercise 4: testing read-after-write

Seed document:

```javascript
{
  _id: "STOCK-101",
  tenantId: "TENANT-A",
  sku: "SKU-X",
  available: NumberLong(20),
  version: NumberLong(1)
}
```

On a test replica set environment:

1. Update stock from 20 to 15 on primary using `$inc` or a conditional update.
2. Use `writeConcern:majority` and read from primary.
3. Read using `secondary`, but **do not assert that a stale value must appear**.
4. Wait for the secondary to catch up with a clear timeout and verify the final value is 15.
5. Use the same causal session to verify read-your-writes across the secondary under supported conditions.
6. Simulate a missing secondary in a dedicated test setup; compare `secondary` failure vs. `secondaryPreferred` fallback.
7. Measure read latency and replication lag; do not use a single document's `updatedAt` delta as the sole metric.

### Exercise 5: real-world incident

During peak hours, a dashboard suddenly spikes primary CPU even though `secondaryPreferred` is configured. At the same time, users occasionally see old order statuses.

Propose checks for:

- Are any secondaries eligible? Tags, staleness, network, elections?
- Is the dashboard falling back to primary, or is a secondary serving it while overloaded?
- Were endpoints needing read-your-writes accidentally configured with `secondaryPreferred` on a shared client?
- Can primary/reporting templates and distinct RBAC roles be separated?
- Are indexes and aggregation limits in place before tuning read preference?
- If no secondary is eligible, should the product return a temporary error or force primary fallback?

### General answer guide

**Warehouse clerk:** read from primary and guard stock updates with atomic conditional updates/versioning; never rely on stale data to decide remaining availability. **Manager:** report on a dedicated secondary if eventual consistency is acceptable; use `secondary` mode if strictly avoiding the primary is required, with error handling or clearly age-labeled caching. Causal sessions fit when a single write-read chain on a secondary needs its own result, provided majority/sessions/timeouts are guaranteed and there is no illusion that all clients see the latest data simultaneously.

## 27. References

- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): principles of read routing and server selection modes.
- MongoDB Manual — [Read Preference Modes](https://www.mongodb.com/docs/manual/core/read-preference/#read-preference-modes): `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, and `nearest`.
- MongoDB Manual — [Maximum Staleness for Read Preference](https://www.mongodb.com/docs/manual/core/read-preference-staleness/): staleness algorithm and supported value limits.
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): `local`, `majority`, `snapshot`, `linearizable`, and guarantee scopes.
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): write acknowledgment and majority.
- MongoDB Manual — [Causal Consistency and Read and Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): session requirements and causal guarantees.
- MongoDB Manual — [Replication](https://www.mongodb.com/docs/manual/replication/): members, oplog, and replication lag.
- MongoDB Java Driver — [Read Preference](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/read-preference/): configuration via Java driver and connection options.
- Spring Data MongoDB — [Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, repositories, mapping, and sessions/transactions.
- Spring Data MongoDB — [Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): ClientSession, transaction manager, and session scope.

## Key takeaways

**Read preference answers "which node to read from," not "how fresh and consistent is the data."** `primary` is usually easiest to reason about for read-after-write; `secondary` isolates load but can be stale and does not fall back; `secondaryPreferred` prefers secondaries but can push reports back onto primary when needed; `primaryPreferred` prefers primary and only falls back when absent; `nearest` selects by network latency and can pick the primary too. Stronger guarantees require considering `readConcern`, `writeConcern`, sessions, transactions, latency/replication lag, and business conditions. With Spring Data MongoDB, separate reporting read paths from transactional paths when justified, test against a real replica set, monitor server selection and lag, and never trade correctness merely to reduce primary load.
