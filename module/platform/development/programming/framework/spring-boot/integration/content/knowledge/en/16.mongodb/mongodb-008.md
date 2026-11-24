# Replica Sets, Read Preference, and Write Concern

## 1. Why Do Integration Applications Need to Understand These Three Concepts?

A Spring Boot service receives HTTP requests, persists processing state in MongoDB, and then publishes events to a broker or calls a partner API. If the MongoDB primary goes down or a secondary has not yet caught up on replication, an unintentional configuration can cause the service to:

- Report a successful write, yet after failover no longer see the record it just confirmed.
- Read from a secondary, observe stale state, and re-emit an event or return wrong API results.
- Wait too long for acknowledgment, time out, and not know whether MongoDB applied the write.
- Assume that having a replica set automatically guarantees **exactly-once**, **read-your-writes**, and **zero downtime**.

A **replica set** handles data replication, primary elections, and availability recovery. **Read preference** governs which node the client chooses for reads. **Write concern** governs how many acknowledgments MongoDB must collect before reporting a write succeeded. Additionally, **read concern** governs what data state is eligible to be returned by a read; designing a sound integration flow requires considering all four factors.

| Concept | Question It Answers | What It Does Not Guarantee on Its Own |
| --- | --- | --- |
| Replica set | How is data replicated and how is a primary elected? | Zero interruption during primary elections |
| Read preference | Read from primary, secondary, or nearest node? | Whether the record has been durably committed |
| Write concern | When is a write acknowledged at the requested level? | Duplicate prevention when a client retries a request |
| Read concern | Which data visibility state may a read return? | Forcing primary reads or providing read-your-writes across arbitrary sessions |

### Running scenario

Suppose an integration service persists an `IntegrationRequest` keyed by `requestId`. The `POST /imports` API inserts a document with state `RECEIVED`; another worker reads it and calls an external API; afterward, the worker updates the state to `COMPLETED`. System requirements:

1. An acknowledged request must be durable enough to continue processing if the primary changes.
2. Workers must not rely on stale state when deciding whether to issue the external call again.
3. Retries from HTTP clients or brokers must not produce duplicate side effects.
4. Reporting reads can tolerate brief lag, whereas transaction-status checks must match the promised consistency level.

We will use this scenario to drive configuration choices rather than memorizing parameter names.

## 2. Replica Set: Primary, Secondary, Election, and Oplog

A replica set is a group of `mongod` processes maintaining the same logical dataset. Typically there is **one primary** accepting standard writes, and **multiple secondaries** replicating operations from the primary. Secondaries apply changes via the **oplog** (operation log), and because replication is asynchronous, they can trail behind the primary.

~~~mermaid
flowchart LR
    A[Spring Boot MongoDB Driver] -->|Write and primary read| P[(Primary A)]
    P -->|Oplog replication| S1[(Secondary B)]
    P -->|Oplog replication| S2[(Secondary C)]
    A -.->|Read if read preference permits| S1
    A -.->|Read if read preference permits| S2
~~~

### How does a failover occur?

1. The driver monitors topology and routes writes to the current primary.
2. If the primary fails or becomes unreachable, voting members hold an election under replica set rules.
3. An eligible secondary is elected as the new primary once it secures enough votes.
4. During failure detection and election, writes or reads requiring the primary may fail, wait, or be retried by the driver if eligible.
5. The driver updates its topology view and routes subsequent operations to the new primary; the application must handle timeouts, transient errors, and uncertain write outcomes.

Not every member can receive writes simultaneously. In standard replica sets, only the primary accepts normal writes. An **arbiter** holds a vote but **stores no data**, cannot serve reads, and contributes nothing to durable data acknowledgments. A three-node **Primary–Secondary–Secondary (P-S-S)** topology is generally preferable to **Primary–Secondary–Arbiter (P-S-A)** when you need to survive losing one data-bearing node while keeping `w: "majority"` writes working.

**Quorum and durability are different things:** having enough votes to elect a primary does not mean having enough **data-bearing** copies to acknowledge `w: "majority"` writes. In P-S-A, if the sole secondary goes down, the primary and arbiter can still form a voting majority, yet `w: "majority"` writes lack enough data-bearing copies to acknowledge.

### Oplog and replication lag

- The primary records operations in the oplog; secondaries tail and apply replicated changes sequentially.
- **Replication lag** is the delay between a secondary's state and the primary's; it depends on network, disk speed, read/write load, and node health.
- A lagging secondary can still return `RECEIVED` even after the primary updated the document to `COMPLETED`.
- During elections/failovers, writes not yet majority-committed risk being rolled back depending on topology and write concern.

Replica sets increase **availability and durability**, yet applications must still implement idempotency, transactions, retries, and observability.

### Quick topology inspection with `mongosh`

~~~javascript
rs.status();           // Roles and health of members
rs.conf();             // Replica set config, votes, and priorities
db.hello();            // Current node info and writable primary status
db.adminCommand({ getDefaultRWConcern: 1 }); // Default read/write concern
~~~

These commands require appropriate privileges and should run in authorized environments. `rs.status()` reflects a point-in-time snapshot and does not replace lag metrics, health checks, and election alerts. Never run `rs.initiate()` or `rs.reconfig()` on a production cluster while experimenting with this lesson.

## 3. Read Preference: Choosing Which Member Serves Reads

Read preference is a **server selection policy** in the MongoDB driver, configurable at client, database, collection, or per-read level depending on the API. By default, the driver reads from `primary`.

| Mode | Node Selection | When to Consider | Risks / Limitations |
| --- | --- | --- | --- |
| `primary` | Primary only | Checking newly updated business state; reads inside transactions | Cannot read when no primary is available |
| `primaryPreferred` | Prefers primary; falls back to eligible secondary if no primary exists | Queries preferring primary but tolerating stale fallback | During failover, reads can suddenly return older data |
| `secondary` | Eligible secondaries only | Reporting, analytics, and queries tolerating stale reads | Fails if no eligible secondary is available |
| `secondaryPreferred` | Prefers secondary; falls back to primary if no eligible secondary exists | Offloading reporting reads from the primary | Freshness can vary between consecutive reads |
| `nearest` | Picks any eligible node within the latency window regardless of role | Latency-sensitive queries tolerating variable freshness | Does not mean the node has the freshest data |

**Read preference is not read concern.** For example, `secondaryPreferred` with read concern `majority` guarantees returning only majority-committed data, **yet it may still lag behind the latest value on the primary** if the secondary has not caught up. Conversely, `primary` with read concern `local` can see writes not yet majority-committed that could still roll back on failover.

### Tags, latency windows, and `maxStalenessSeconds`

The driver can filter secondaries by member tags (e.g., `region`, `rack`), cap estimated staleness via `maxStalenessSeconds`, and choose among members within the **latency window**. Key options:

~~~text
readPreference=secondaryPreferred
maxStalenessSeconds=120
readPreferenceTags=region:ap-southeast-1
localThresholdMS=15
~~~

- `maxStalenessSeconds` must be **at least 90 seconds** when non-negative. It is an **estimated staleness bound for server selection**, not an SLA guaranteeing “data is always at most 120 seconds behind”.
- `readPreferenceTags` filters nodes matching the tag set; when supplying ordered tag sets, understand fallback order. Do not apply tags with `primary`.
- `localThresholdMS` is the allowable latency window relative to the fastest eligible node; `nearest` optimizes network latency, not data freshness.
- `primary` rejects `maxStalenessSeconds` and tag sets.

If business logic requires **reading your own write immediately after writing**, read from `primary` or use a properly configured causally consistent session. Switching read preference to `nearest` purely to “reduce latency” can break deduplication logic.

### Timeline example and stale reads

~~~text
T0   Primary A applies update: requestId=R9, state=COMPLETED
T1   A acknowledges write with w:majority; B has replicated the data
T2   Secondary C has not yet applied the update due to replication lag
T3   Worker reads with secondaryPreferred; driver selects C
T4   Worker observes stale state=RECEIVED, even though the write was majority-committed
~~~

At `T3`, neither writing with `w:majority` nor reading with read concern `majority` **forces** every secondary to reflect the newest value instantaneously. Workers must rely on idempotency keys/unique indexes and, when needed, primary reads or causal sessions.

### Transactions and read preference

**Transactions containing read operations must use read preference `primary`.** Never set `readPreference=secondaryPreferred` globally across the whole application assuming Spring Data MongoDB transactions will still work. A straightforward pattern is keeping the default URI on `primary` and applying secondary read preferences selectively to reporting queries. Inside a transaction, all operations must route to the same member.

## 4. Write Concern: When May MongoDB Reply “Written”?

Write concern defines the **acknowledgment level** requested by the application for write commands. Typical components include `w`, `j`, and `wtimeout` (expressed as `wTimeoutMS` in URIs).

| Setting | Acknowledgment Condition | Trade-offs and Use Cases |
| --- | --- | --- |
| `w: 0` | No write acknowledgment requested | Unsuitable for persisting critical integration state |
| `w: 1` | Primary acknowledges the operation | Lower latency, yet writes can roll back on failover before replicating |
| `w: 2` or `w: 3` | Specified count of data-bearing members acknowledge | Tightly coupled to topology size/state; not identical to majority |
| `w: "majority"` | Calculated majority of data-bearing voting members acknowledge | Fits critical data needing durability across typical failovers; trades latency and availability when quorum is lost |
| `j: true` | Requires journal flush per write concern semantics | Increases durability guarantees before ACK; depends on cluster journaling configuration |
| `wtimeout` | Bounds wait time for write concern acknowledgment | Timing out **does not roll back** an already applied write |

**Important:** `w: 1` does not mean durable across a majority of nodes; `w: "majority"` does not mean “any voting majority including an arbiter suffices”. MongoDB calculates write concern majority over eligible data-bearing members. Under common configurations, majority acknowledgment pairs with journaling; exact behavior depends on `writeConcernMajorityJournalDefault` and `j`.

### Defaults can vary by topology

Never claim unconditionally that MongoDB **always defaults** to `w: "majority"`. Many modern replica sets default implicitly to majority, yet topologies with arbiters have exceptions—for instance, P-S-A may implicitly default to `w: 1`. Inspect `getDefaultRWConcern` or configure explicitly for critical flows. When durability is part of your data contract, specify `w=majority` explicitly in the connection string or on relevant operations.

### Write concern timeout does not prove the operation failed

Suppose the primary wrote request R9, yet secondaries are too slow to acknowledge majority within the timeout. The application receives a `write concern timeout`. Three possibilities exist:

1. The write was applied on the primary and may still replicate.
2. The write had not yet reached the requested durability when the timeout fired.
3. After a network error or election, the client does not know the final outcome.

Therefore, **never treat a timeout as “definitely not written”** and reissue a new transaction with a fresh request ID. Use an idempotency key, look up existing state, and retry within limits. The driver's `retryWrites=true` helps certain eligible writes, yet does not replace end-to-end idempotency across HTTP → MongoDB → broker.

### Mongo shell: explicit write concern per operation

~~~javascript
db.integrationRequests.insertOne(
  {
    _id: "partnerA:req-1001",
    state: "RECEIVED",
    createdAt: new Date()
  },
  { writeConcern: { w: "majority", j: true, wtimeout: 10000 } }
);
~~~

This requires majority acknowledgment plus journaling with a 10-second wait limit. Under latency-sensitive workloads, benchmark with realistic load and monitor `writeConcernErrors` before rolling out broadly.

A version-specific note: starting in MongoDB **8.0**, `w:majority` acknowledgment is based on a majority of data-bearing members durably recording the **oplog entry**; secondaries may apply changes to collections **after** acknowledgment returns. Thus, reading immediately from a secondary can still miss the newly written document, reinforcing the need for explicit read preferences or causal sessions. Earlier versions acknowledged at different points in the apply lifecycle; verify documentation for your deployed server version.

## 5. Read Concern and Causal Consistency: The Missing Piece

Read concern is often discussed alongside read/write preferences because they interact, yet **they do not replace one another**.

| Read Concern | Primary Meaning | Integration Considerations |
| --- | --- | --- |
| `local` | Returns the node's local data, even if not yet majority-committed | Can expose data that later rolls back |
| `available` | Favors availability/low latency in applicable topologies | No majority guarantee; in sharded clusters may return orphaned chunks |
| `majority` | Returns data from the node's latest majority-committed snapshot | More durable, yet **does not** guarantee the newest cluster-wide state |
| `linearizable` | For eligible primary reads, reflects all majority writes completed before the read began | Strong guarantee, can wait longer; set reasonable `maxTimeMS` and check eligibility |
| `snapshot` | Reads from a consistent snapshot in supported operations/transactions | Requires `w:majority` commit in multi-document transactions to maintain guarantees |

### Causal consistency

MongoDB provides client sessions with **causal consistency**. With **`readConcern=majority`** and **`writeConcern=majority`** inside a properly used causally consistent session, the application gains **read your writes**, **monotonic reads**, **monotonic writes**, and **writes follow reads**—even when reads route to secondaries. This is completely different from merely setting `readPreference=secondaryPreferred`.

Java Sync Driver example demonstrating writing and reading back the same document within one session:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.springframework.stereotype.Service;
import static com.mongodb.client.model.Filters.eq;

@Service
public class CausalReadExample {
    private final MongoClient mongoClient;

    public CausalReadExample(MongoClient mongoClient) {
        this.mongoClient = mongoClient;
    }

    public Document writeThenRead(String id) {
        try (ClientSession session = mongoClient.startSession(
                ClientSessionOptions.builder().causallyConsistent(true).build())) {

            MongoCollection<Document> requests =
                    mongoClient.getDatabase("integration")
                            .getCollection("integrationRequests")
                            .withReadConcern(ReadConcern.MAJORITY)
                            .withWriteConcern(WriteConcern.MAJORITY);

            requests.insertOne(session, new Document("_id", id)
                    .append("state", "RECEIVED"));

            return requests
                    .withReadPreference(ReadPreference.secondaryPreferred())
                    .find(session, eq("_id", id))
                    .first();
        }
    }
}
~~~

This applies **within the same session**, not automatically across two separate HTTP requests or two independent consumers. `id` must be a new key for this run; `insertOne` throws a duplicate key error if the same `_id` is inserted again. Sessions must not be shared concurrently across threads. When integrating with Spring Data's session/transaction management, use Spring's session/transaction APIs rather than opening disconnected sessions unaware of active transactions.

For workers deciding whether to emit broker events, causal consistency does not eliminate idempotency checks and atomic claim/status locks. Causal sessions clarify observation order; they do not fold external HTTP calls into a database transaction.

## 6. Configuring a MongoDB Replica Set in Spring Boot

### 6.1. Dependencies and connection string

For Spring MVC or synchronous REST projects using Spring Data MongoDB:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

For WebFlux and reactive pipelines, use `spring-boot-starter-data-mongodb-reactive`. The two models have distinct APIs; never call `block()` casually on the event loop to wait for MongoDB.

Example connection string for a three-node cluster:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/integration?replicaSet=rs0&readPreference=primary&w=majority&journal=true&wTimeoutMS=10000&retryWrites=true&serverSelectionTimeoutMS=5000&readConcernLevel=majority
~~~

Option breakdown:

| URI Option | Example Value | Role |
| --- | --- | --- |
| `mongo1,mongo2,mongo3` | Three hostnames/ports | Seed list for discovering the replica set and tracking primary changes |
| `replicaSet` | `rs0` | Verifies topology matches the expected replica set |
| `readPreference` | `primary` | Defaults all queries to read from the primary |
| `w` | `majority` | Requires majority write acknowledgment |
| `journal` | `true` | Requires journal durability per write concern |
| `wTimeoutMS` | `10000` | Waits up to 10 seconds for write concern; timeout does not delete applied writes |
| `retryWrites` | `true` | Driver can retry **certain** eligible writes on retryable-labeled errors |
| `serverSelectionTimeoutMS` | `5000` | Limits wait for an eligible server; can time out during elections |
| `readConcernLevel` | `majority` | Reads majority-committed snapshots by default |

This URI illustrates a policy for critical data. In production, enable TLS, authentication, inject secrets via a secret manager/env vars, and use hostnames reachable from every pod. Never commit passwords or credential-bearing URIs into repositories, and never log full connection strings with secrets.

**Recent version note:** MongoDB documentation now marks the `wtimeoutMS` URI option as **deprecated** and recommends `timeoutMS` where supported by the driver. Their scopes differ: `wtimeoutMS` bounds waiting for **write concern**, whereas `timeoutMS` bounds the **entire operation** (including server selection, connection checkout, and execution). If migrating to `timeoutMS`, re-evaluate related timeouts instead of treating them as identical. The example above retains `wTimeoutMS` to demonstrate write concern explicitly on systems still supporting it.

For **Spring Boot 3.x**:

~~~yaml
# application.yml (Spring Boot 3.x)
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

For **Spring Boot 4.x**, the connection URI property moved under `spring.mongodb.*`:

~~~yaml
# application.yml (Spring Boot 4.x)
spring:
  mongodb:
    uri: ${MONGODB_URI}
~~~

Spring Boot and driver releases can change property names and auto-configuration types across major versions. Check the metadata and migration guide for **your project's actual version** before copying examples. If declaring a custom `MongoClient` bean, manage all `MongoClientSettings` yourself rather than assuming Boot properties still apply automatically.

**Why isn't entering a single hostname enough?** The driver connects using the seed list and discovers all replica set members. If the hostnames MongoDB advertises internally do not resolve inside containers/Kubernetes, the app can still hit server selection errors even when the initial seed host is reachable. Verify DNS, network policies, TLS SAN hostnames, and advertised hosts across the whole cluster.

### 6.2. Reading reports from secondaries per query

Instead of setting `secondaryPreferred` globally, keep `primary` as the default for state handling and attach secondary read preference selectively to lag-tolerant reporting queries. Spring Data MongoDB (versions supporting `Query.withReadPreference`) allows:

~~~java
import java.util.List;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
class IntegrationReportService {

    private final MongoTemplate template;

    IntegrationReportService(MongoTemplate template) {
        this.template = template;
    }

    List<IntegrationRequest> recentlyCompleted() {
        Query query = Query.query(Criteria.where("state").is("COMPLETED"))
                .withReadPreference(ReadPreference.secondaryPreferred())
                .withReadConcern(ReadConcern.MAJORITY)
                .limit(100);
        return template.find(query, IntegrationRequest.class);
    }
}
~~~

Assuming `IntegrationRequest` is a `@Document`-mapped Spring Data entity with a matching index on `state`/timestamp so scheduled polls avoid full collection scans. `Query.withReadPreference(...)` applies **only to this query**, leaving state-checking services untouched. On older Spring Data MongoDB versions lacking this method, check `@ReadPreference` on repositories or template/collection settings per version.

For duplicate checks, work claiming, or API responses immediately following writes, read from `primary` and use atomic conditional updates. No read preference replaces indexes, unique keys, or transactions under concurrency.

## 7. Hands-On Example: Persisting Integration Request State Safely

Suppose the application receives messages carrying `sourceSystem`, `requestId`, and order payload from an HTTP API or broker. Redelivering the same message multiple times must yield **one** state record and **zero** duplicate business side effects.

### 7.1. Model and unique key

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "integrationRequests")
public record IntegrationRequest(
        @Id String id,
        String sourceSystem,
        String requestId,
        String payloadHash,
        String state,
        Instant createdAt,
        String workerId,
        Instant claimedAt) {
}
~~~

Here, `id = sourceSystem + ":" + requestId` is stored under MongoDB's unique `_id` key. If `sourceSystem` or `requestId` may contain the delimiter character, use length-prefix encoding or a canonical hash to avoid collisions. With multiple upstream systems, never assume `requestId` is globally unique on its own.

**Important:** Idempotency is not just “ignore if the ID already exists”. If the same key arrives with different content, reject with a contract error or quarantine it; compare `payloadHash` (computed over canonicalized input) against the stored record.

### 7.2. Upsert that writes only when the record does not exist

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class IntegrationRequestStore {

    private final MongoTemplate template;

    public IntegrationRequestStore(MongoTemplate template) {
        this.template = template;
    }

    public IntegrationRequest receive(
            String sourceSystem, String requestId, String payloadHash) {

        String id = sourceSystem + ":" + requestId;
        Query key = Query.query(Criteria.where("_id").is(id));
        Update onCreate = new Update()
                .setOnInsert("sourceSystem", sourceSystem)
                .setOnInsert("requestId", requestId)
                .setOnInsert("payloadHash", payloadHash)
                .setOnInsert("state", "RECEIVED")
                .setOnInsert("createdAt", Instant.now());

        // URI already requires majority writeConcern.
        template.upsert(key, onCreate, IntegrationRequest.class);

        // Lookup routes to primary by default.
        IntegrationRequest stored =
                template.findById(id, IntegrationRequest.class);

        if (stored == null ||
                !payloadHash.equals(stored.payloadHash())) {
            throw new IllegalStateException(
                    "requestId already exists with different payload or write not visible");
        }
        return stored;
    }
}
~~~

`$setOnInsert` populates fields only when the upsert actually inserts a new document; a retry with the same key will never revert `COMPLETED` back to `RECEIVED`. Still, depending on upsert races and index state, a call can raise duplicate-key or transient exceptions; callers must classify errors and look up by key before retrying per policy.

**Limitation of this snippet:** `receive` inserts or reads the state without claiming exclusive worker ownership. With multiple workers, use `findAndModify` conditioned on `state=RECEIVED` to transition atomically to `PROCESSING`, paired with worker tokens/leases and expiry recovery. Reading the state and calling a partner API directly without claiming still leaves a race across consumers.

### 7.3. Atomic state transition

Example claim succeeding only if state is still `RECEIVED`:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public IntegrationRequest tryClaim(String id, String workerId) {
    Query claimable = Query.query(
            Criteria.where("_id").is(id).and("state").is("RECEIVED"));

    Update update = new Update()
            .set("state", "PROCESSING")
            .set("workerId", workerId)
            .currentDate("claimedAt");

    return template.findAndModify(
            claimable,
            update,
            FindAndModifyOptions.options().returnNew(true),
            IntegrationRequest.class);
}
~~~

This is an additional method inside `IntegrationRequestStore` sharing `template`. If no record matches `state=RECEIVED`, it returns `null`: only the consumer receiving the updated document won the claim. `workerId` and `claimedAt` are already mapped in the record; in real deployments, also add lease expiration, timeouts, and token-checked completion so a stalled old worker cannot overwrite a newer worker's result.

Actual processing flow:

~~~mermaid
flowchart TD
    A[HTTP request or broker message] --> B[receive by idempotency key]
    B --> C{Payload hash valid?}
    C -- No --> X[Conflict or quarantine]
    C -- Yes --> D[Atomic claim RECEIVED → PROCESSING]
    D --> E{Claim succeeded?}
    E -- No --> F[Read state and return appropriate result]
    E -- Yes --> G[Call downstream with same idempotency key]
    G --> H{Downstream confirmed?}
    H -- Yes --> I[Record COMPLETED + event/outbox]
    H -- Timeout/unknown --> J[Query outcome + bounded retry]
    J --> G
~~~

In systems that actually emit events to Kafka/RabbitMQ after MongoDB commits, use a **transactional outbox** or a durable replay design. A MongoDB transaction cannot span an external HTTP call or an independent broker publish. Proper read preference and write concern ensure durability and visibility, not cross-system atomicity.

### 7.4. Should you use multi-document transactions?

MongoDB supports multi-document transactions on eligible topologies, and Spring Data MongoDB provides `MongoTransactionManager` for `@Transactional`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {

    @Bean
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Open a transaction only when multiple documents/collections must commit or roll back together. Reads inside a transaction must use `primary`; **transaction commit** write concern should be set explicitly (such as `majority`) for desired durability, and transaction read concern `majority`/`snapshot` carries guarantees tied to commit write concern. Never wrap a slow HTTP call inside a transaction expecting MongoDB to roll back partner-side side effects.

## 8. Selecting Policies per Integration Flow

| Requirement | Read Preference | Write Concern | Read Concern / Safeguards |
| --- | --- | --- | --- |
| HTTP writes `RECEIVED` before returning `202 Accepted` | `primary` for conditional lookups | `majority`, consider journaling | Verify state with `majority` and idempotency key |
| Worker claims a request to call partner | `primary` | `majority` when claim state matters for recovery | Atomic `findAndModify`, token/lease, and retries |
| API writes then checks status immediately | `primary` | `majority` | `majority`, or causal session if spanning multiple steps/nodes |
| Dashboard report tolerating stale reads | `secondaryPreferred` | Per original write flow | `majority` as needed; monitor lag and accept stale views |
| Read-only offline analytics | `secondary` or `nearest` | Not applicable | Bound staleness and handle missing secondaries |
| Multi-document MongoDB transaction | `primary` | Configured on transaction commit, typically `majority` | `snapshot`/`majority` per transaction contract |
| Emitting broker event after DB write | Inspect state on `primary` | `majority` | Outbox/inbox and dedup keys; never rely on read preference |

No single URI fits every query. Setting a **safe business default** and applying specialized policies only to read-only reports is far easier to reason about than defaulting the client to `secondaryPreferred` and trying to patch critical paths later.

### Commonly overlooked trade-offs

**Durability vs. availability:** If a majority of data-bearing voting members are unreachable, `w:majority` writes cannot complete before timeout. Return clear errors, queue for retry, or shed load. Automatically downgrading to `w:1` without business sign-off silently alters the durability contract.

**Latency vs. freshness:** Offloading reports to secondaries relieves primary read load, yet replication lag can show older state on dashboards. Monitor lag, set staleness thresholds, and inform users if needed.

**Retries vs. duplicates:** After an election or write concern timeout, the request may have been partially or fully written. Safe retries reuse the same business key and conditional updates—never generate a new UUID on every retry of the same message.

**Replica set vs. multi-region:** Replication does not mean every region experiences identical latency or freshness. With tags/`nearest`, measure cross-region RTT and lag and enforce ordering per business key.

## 9. Testing Failover, Stale Reads, and Write Concern

To observe how these settings impact Spring Boot Integration flows, test against a **test replica set with at least three data-bearing nodes** and test fixtures—never step down a production cluster for this exercise.

### 9.1. Verify normal paths before fault injection

1. Start the replica set and wait for all members to become healthy.
2. Connect Spring Boot using a multi-host seed URI with the matching `replicaSet`.
3. Write an `IntegrationRequest` with `w:majority` and a stable ID.
4. Read back via `primary` to confirm matching state; then read via `secondaryPreferred` or `secondary` to observe behavior under replication lag.
5. Inspect server/driver metrics and logs to confirm selected nodes, response times, and write concern outcomes.

In `mongosh`:

~~~javascript
// Only in a controlled test environment:
rs.status();
db.adminCommand({ getDefaultRWConcern: 1 });
db.integrationRequests
  .find({ _id: "sourceA:req-101" })
  .readPref("secondaryPreferred");
~~~

Reading a document from a secondary right after writing may return the updated data, stale data, or nothing depending on replication timing. **Never write a test asserting a stale read must always occur**; that is timing-dependent. You can introduce controlled load or network delay in an isolated test environment to observe it, while asserting policy via read preference configuration and contract-valid outcomes.

### 9.2. Controlled primary re-election test

Procedure:

1. Identify the initial primary via `rs.status()` or `hello`.
2. Write request R1 with `w:majority` and confirm success acknowledgment.
3. On the **test cluster's** primary, intentionally run `rs.stepDown(60)` to trigger a realistic election.
4. During the election, issue a write with a stable ID; record server selection errors, retryable errors, timeouts, and recovery duration.
5. Once a new primary is elected, verify R1 and the final state of the mid-failover write rather than guessing from client exceptions.
6. Replay the request using **the exact same request ID** and verify no duplicate record or second side effect occurs.

If a write concern timeout occurs, never conclude the write rolled back; read back from the new primary or query state by idempotency key before deciding to retry. In Java, `MongoTimeoutException`, `MongoSocketException`, and `MongoWriteConcernException` carry distinct signals; log error labels and context when classifying. Through Spring Data, exceptions may translate into the `DataAccessException` hierarchy, so tests should not hard-bind to a single raw exception class.

### 9.3. Goal-oriented test matrix

| Test Case | Action | Expected Outcome |
| --- | --- | --- |
| Normal majority write | Write with healthy P-S-S | After ACK, read per selected policy and record latency |
| One secondary offline | Stop one secondary in P-S-S | With primary + one secondary forming majority, `w:majority` writes continue |
| Majority lost | Isolate enough nodes in test env | Majority writes cannot acknowledge; fail/time out per policy without silently downgrading durability |
| Election | Step down primary under load | Driver discovers new primary; app performs bounded idempotent retries |
| Secondary read | Set `secondaryPreferred` | Observe potential lag; never use for decisions requiring immediate freshness |
| Secondary unavailable | Set `secondary` | Read fails/waits on server selection; does not fall back to primary |
| Secondary unavailable | Set `secondaryPreferred` | Driver falls back to primary |
| Invalid staleness threshold | `maxStalenessSeconds=30` | Rejected as invalid because minimum is 90 seconds |
| Write concern timeout | Short timeout with insufficient ACK | Reports uncertain state; reconciles by same ID before retrying |
| Request retry | Send twice with same `(sourceSystem, requestId)` | Zero duplicate side effects; conflicting payload for same key rejected |
| Read inside transaction | Attempt `secondary` read preference in transaction | Rejected/unsupported; requires `primary` |

Good tests assert **final side effects** (documents, downstream call counts, outbox entries) and bounded duration, not merely that the driver threw an exception. When testing Spring Data integrations, use dedicated databases/collections, independent seeds, and cleanup by test keys—never reuse production business collection names.

## 10. Operational Observability and Troubleshooting

Signal groups to include on dashboards:

- **Replica set:** PRIMARY/SECONDARY roles, healthy node count, election/stepdown history, quorum status.
- **Replication:** oplog window, replication lag per secondary, lagging or recovering members.
- **Writes:** latency by `w`, `writeConcern` timeout counts, retryable writes, duplicate-key conflicts, uncertain outcomes.
- **Reads:** primary/secondary read ratios per query type, server selection latency, timeouts, stale results, and acceptable report lag.
- **Integration app:** message/outbox backlogs, `RECEIVED/PROCESSING/COMPLETED` counts, retry rates, HTTP/broker errors, processing duration, and blocked duplicate requests.

Exact metric names depend on your MongoDB Exporter version, driver Micrometer integration, and monitoring stack. Label by `service`, `operation`, `result`, and `cluster`; never use `requestId` as a high-cardinality label. Keep correlation IDs in logs/tracing to correlate a request across HTTP, MongoDB, and brokers.

### Symptoms and triage steps

| Symptom | Check First |
| --- | --- |
| App intermittently cannot find primary | Election ongoing? Do replica set hostnames resolve from pods? TLS/certs? Is server selection timeout too short? |
| Slow writes or `wtimeout` | Replication lag, healthy data-bearing member count, journaling, disk/network saturation, timeout settings |
| Reading `RECEIVED` even though worker wrote `COMPLETED` | Did query route to secondary? How large is lag? Are read concern/sessions appropriate? |
| Replayed records appear after restart | Did prior write use `w:1`? Rollback or message redelivery? Are idempotency keys/indexes enforced? |
| Transaction fails due to read preference | Do transaction queries use `primary`? Any client/repository/query override? |
| Driver connects to seed host yet misses other members | Advertised hosts in `rs.conf()`, DNS, firewall, NetworkPolicy, port mapping, TLS |
| Throughput rises with `nearest` yet data is stale | `nearest` optimizes network latency, not freshness; measure lag and choose the right read path |

**Never tune carelessly:** if an HTTP flow already acknowledged success to a user, changing `w=majority` to `w=1` merely to “stop timeouts” alters the durability guarantee of your contract. If switching `readPreference=primary` to `secondaryPreferred` to lower primary CPU, audit every code path assuming up-to-date reads.

## 11. Summary and Self-Check Questions

Three key distinctions to remember:

1. **Replica sets** replicate data and elect a new primary on failure, yet failover still causes brief interruptions and does not prevent applications from redelivering messages.
2. **Read preference** chooses which node serves a read; secondaries can lag. **Read concern** defines what commitment level a query may observe; `majority` does not guarantee cluster-wide newest state.
3. **Write concern** defines write acknowledgment; `w:majority` suits critical business writes, yet requires enough data-bearing members and timeouts still leave uncertain outcomes.

Self-check questions:

- Why can a write acknowledged with `w:majority` be followed immediately by a secondary query returning stale state?
- Why is P-S-A different from P-S-S for acknowledging `w:majority` writes when a secondary goes offline?
- If an HTTP client times out mid-election, what should the service check before reissuing the request?
- When is `secondaryPreferred` appropriate, and when is `primary` mandatory?
- To read your own write from a secondary across steps, how must sessions and read/write concerns be configured?
- Why cannot a MongoDB transaction guarantee atomicity across both DB writes and an external partner HTTP call?

In Spring Boot Integration, reliable designs combine **intentional MongoDB settings**, **idempotency keys**, **conditional updates**, **properly scoped transactions**, **error-aware retries**, and **end-to-end metrics, logs, and tracing**.

## References

- [MongoDB Manual — Replica Set](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Read Preference Staleness](https://www.mongodb.com/docs/manual/core/read-preference-staleness/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Default Read and Write Concerns](https://www.mongodb.com/docs/manual/reference/mongodb-defaults/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [Spring Boot Reference — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data MongoDB — Querying Documents and Read Preference](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
