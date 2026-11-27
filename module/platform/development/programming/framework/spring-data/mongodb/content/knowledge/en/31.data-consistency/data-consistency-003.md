# Write concern, majority, journal, and write acknowledgment

> **Chapter:** Data Consistency  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; practicing query design, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objective:** Explain accurately when MongoDB acknowledges a write operation; compare `w:0`, `w:1`, `w:"majority"`, and `j:true`; understand journaling, replication, rollbacks, `wtimeout`, and write concern errors; configure via the MongoDB Java Driver, `MongoTemplate`/repositories/reactive; choose policies suited to data durability and verify behavior through tests.

## 1. Core question: does a successful `insert` mean data is safe?

Suppose an application accepts a payment and inserts a document:

~~~javascript
{
  _id: "pay301",
  tenant_id: "t01",
  order_id: "o301",
  state: "PAID",
  amount_vnd: NumberLong(850000)
}
~~~

MongoDB returns a success result. But **what does "success" mean here**?

- Did the primary process the write command?
- Was the journal on the primary synced to disk?
- Did one or more secondaries receive and acknowledge the oplog?
- Will the data survive if the primary loses power or steps down in an election?
- Will a reader on a secondary immediately see the new document?

These questions **are not synonymous**. MongoDB uses **write concern** to control the level of **write acknowledgment** a client requires before completing an operation. That acknowledgment level affects durability across failover, response latency, and write availability when the cluster experiences faults.

> **Important rule:** `acknowledged` does not automatically mean "cannot roll back," `j:true` does not automatically mean "replicated to a majority," and `wtimeout` does not automatically mean "the write did not happen."

### 1.1. Terms to distinguish

| Term | Meaning |
| --- | --- |
| **Write acknowledged** | The server confirms the operation satisfied the client-requested write concern |
| **Applied on primary** | The primary accepted/applied the change at the data level |
| **Replicated** | Other replica set members received the write/oplog progress per rules |
| **Journaled** | The write was synced to the on-disk journal on the required members |
| **Majority committed** | The write reached the majority confirmation mark, per MongoDB version mechanics |
| **Durable** | Has a level of data-loss protection based on chosen replication/journaling, not absolute immunity to every catastrophe |
| **Visible to reader** | A specific query sees the value, depending on read concern, read preference, and when a secondary applies it |
| **Atomic** | One or a set of changes with all-or-nothing semantics at the level MongoDB supports; distinct from write concern |

**Do not use write concern as a substitute for a business transaction.** For instance, writing to both `payments` and `orders` with `majority` **does not automatically make them an atomic transaction**. To guarantee all-or-nothing across multiple documents, design a transaction or equivalent business model.

## 2. Structure of a write concern

MongoDB represents write concern as a document:

~~~javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
~~~

| Option | Meaning | Examples |
| --- | --- | --- |
| `w` | Number of members that must acknowledge, or majority/custom concern | `0`, `1`, `2`, `"majority"` |
| `j` | Requests acknowledgment related to on-disk journaling | `true`, `false`, unspecified |
| `wtimeout` | Time limit to wait for `w` level, in milliseconds | `5000` |

In Java Driver URIs, the timeout option is typically written as `wTimeoutMS`; in a MongoDB command/`mongosh` write concern document, it is `wtimeout`. Distinguish **time units** and **API property names**—never rename them arbitrarily across layers.

### 2.1. Three independent axes

~~~mermaid
flowchart LR
    A["Client sends insert/update"] --> B["Primary processes write"]
    B --> C["Replication to other members"]
    B --> D["On-disk journal"]
    C --> E["Satisfies w condition"]
    D --> F["Satisfies j requirement"]
    E --> G["Sends acknowledgment to client"]
    F --> G
~~~

This diagram is a conceptual model. Execution order, details, and journal/commit timing vary by MongoDB version, storage engine, replica set config, and write concern type. Do not infer that replication and journaling always happen in one strict linear sequence.

### 2.2. What write concern does not control

Write concern **does not** govern:

- Which documents are updated: that is the query predicate's job.
- Business validity checks: that belongs to validation and data constraints.
- Choosing primary or secondary for **reads**: that is `readPreference`.
- Consistency/stability level for **reads**: that is `readConcern`.
- Whether writes across multiple documents roll back together: that belongs to transaction semantics.
- Whether a timed-out request can be retried infinitely safely: that belongs to retry/idempotency design.

## 3. Replica sets and how majority is calculated

Suppose a replica set has **three data-bearing, voting members**:

~~~text
               Replica set (3 data-bearing voting members)

           Primary P
         (handles write)
               |
      +--------+--------+
      |                 |
  Secondary S1      Secondary S2

w:1             -> P acknowledging is enough.
w:"majority"    -> P and at least one of S1/S2 reach majority mark.
w:3             -> P, S1, and S2 all acknowledge.
~~~

With three voting members, **majority is 2**. With five voting members, majority is **3**. Tag sets and custom write concerns follow separate rules outside basic examples.

### 3.1. `w:1`

~~~javascript
{ w: 1 }
~~~

The primary can return acknowledgment right after applying the change locally. It **does not wait for secondaries** to satisfy write concern. If the primary fails before the write replicates to a member later elected as the new primary, an acknowledged `w:1` write **can be rolled back**.

For regenerable data and low-criticality tasks, this option may be considered after accepting the risk. For payments, ledgers, or order states with financial impact, evaluate carefully instead of optimizing solely for latency.

### 3.2. `w:"majority"`

~~~javascript
{ w: "majority" }
~~~

MongoDB waits for acknowledgment from a **majority of eligible data-bearing voting members** under replica set rules. This substantially reduces the risk of an acknowledged write being rolled back during an election/failover.

**What it is not:** "all secondaries have seen the data." Reaching majority in a three-node set requires only two members; the third node may still lag.

### 3.3. `w:2` is not always equivalent to majority

In a three-voting-member data-bearing replica set, `w:2` happens to match a majority of 2. Yet in a five-voting-member replica set:

~~~text
w:2        -> 2 data-bearing members acknowledge
w:majority -> at least 3 voting members per majority threshold
~~~

`w:2` does not permanently mean majority. When topology changes, the majority threshold changes; moreover, numeric `w` can be satisfied by **non-voting** members, whereas majority follows voting rules.

### 3.4. Arbiters do not store data

A **P-S-A** replica set (primary, secondary, arbiter):

~~~text
P: Primary, data-bearing, voting
S: Secondary, data-bearing, voting
A: Arbiter, voting but stores NO data

Voting majority = 2.
An arbiter cannot contribute a data copy to acknowledge a majority write.
~~~

In this topology, `w:"majority"` reaching 2 requires participation from **both P and S**. If S is unavailable, writes cannot achieve majority even though the arbiter still votes in elections.

This is one reason **never to treat P-S-A as equivalent to P-S-S** for majority write availability.

## 4. `w:0`, `w:1`, `w:"majority"`, and `w:n`

| Write concern | Acknowledgment level | Risks / notes |
| --- | --- | --- |
| `w:0` | Does not request server write acknowledgment | Cannot reliably detect duplicate keys, validation failures, or write outcomes |
| `w:1` | One member, usually the primary | Can roll back if primary loses role before majority replication |
| `w:2` | Two eligible members | May not equal majority; depends on topology |
| `w:"majority"` | Majority of voting data-bearing members per rules | Better rollback protection under standard conditions; increases wait / lowers availability when quorum is lost |
| `w:3` | Three eligible members | Unsuitable if deployment lacks enough data-bearing members or a member lags |

### 4.1. `w:0` — unacknowledged write

~~~javascript
{ w: 0 }
~~~

This does not mean "faster write that still definitely succeeds." The client **receives no guarantee that the server executed it successfully**. Drivers generally cannot provide reliable `matchedCount`/`modifiedCount` results from an unacknowledged write.

`w:0` is unsuitable for operations that tell users "registration succeeded," "payment received," or "status updated." It also provides no reliable signal for duplicate key or schema errors.

### 4.2. `w:1` — acknowledged by primary, not guaranteed durable across failover

~~~javascript
{ w: 1 }
~~~

This **does not mean data stays in RAM forever**; journaling and replication can still happen afterward. It only states that the client **does not wait** for those steps before receiving acknowledgment, unless `j` requires otherwise.

### 4.3. `w:"majority"` — prioritizing replica set durability

~~~javascript
{ w: "majority", wtimeout: 5000 }
~~~

The client waits for enough members and receives a write concern error if not met within the wait limit. **This wait error does not automatically undo a write** already applied on the primary.

### 4.4. `w:n` — do not pick a number without checking topology

A high numeric `w` can become unachievable when a secondary lags, disconnects, or there are not enough data-bearing members. Without a proper timeout, an unachievable write concern can wait a very long time.

Separate two operational metrics: **acknowledgment latency** and **availability when a member fails**. No single `w` fits every workload.

## 5. Journal: what does `j:true` mean?

MongoDB uses **write-ahead logging/journaling** on journaled storage engines such as WiredTiger to support crash recovery after process or host failures.

### 5.1. `j` unspecified

~~~javascript
{ w: 1 }
~~~

With numeric write concern and `j` unspecified, MongoDB generally **does not need to wait** for journal sync before returning acknowledgment. The journal can still be flushed later under normal operation.

### 5.2. `j:true`

~~~javascript
{ w: 1, j: true }
~~~

The client requests acknowledgment tied to **syncing the journal to disk** before considering the write to satisfy write concern. This improves crash recovery on **the requested members**, however:

> **`w:1,j:true` is still not `w:"majority"`.**

Even if the primary has journaled the write, if it was not replicated to a majority and the primary is excluded from the elected history after failover, the write can still roll back under replica set rules. **Journaling protects against one failure mode, while majority protects against another.**

### 5.3. `w:"majority"` and default journaling

On replica sets with journaling enabled, `w:"majority"` with `j` unspecified is governed by server parameter `writeConcernMajorityJournalDefault`:

- **`true` (typical default):** majority acknowledgment waits for writes to be durably journaled per majority rules.
- **`false`:** majority acknowledgment may return based on in-memory state without waiting for the journal; if multiple nodes crash/restart simultaneously, data loss/rollback risk is higher.

Instead of assuming `majority` "always implies `j:true`" or "is unrelated to the journal," **inspect your deployment configuration**.

### 5.4. Do not oversimplify `j:false` as disabling all journal waits

MongoDB documentation distinguishes explicit `j`, the majority journaling default, and storage engine behavior. On a default replica set with `writeConcernMajorityJournalDefault:true`, `w:"majority"` still involves journal/majority-snapshot mechanics affecting acknowledgment timing even if a write specifies `j:false`.

Operational policy should take **desired durability** as input, rather than treating `j:false` as a guaranteed "skip all disk syncs" switch in every topology.

### 5.5. Running without a journal

Some storage engines/configurations have no journal in the WiredTiger sense. Requesting `j:true` may be unavailable or handled differently depending on the engine; MongoDB defines specific rules for the in-memory storage engine. When infrastructure does not use WiredTiger/standard journaling, check support and version-specific docs.

## 6. `w` × `j` decision table

This is a **practical model for typical WiredTiger replica sets**; it does not replace version-specific documentation or special server options.

| Configuration | What does the client wait for? | Crash / failover resilience |
| --- | --- | --- |
| `{w:0}` | Does not wait for write acknowledgment | No confirmation guarantee from server |
| `{w:1}` | Primary processes the write | Rollback risk after election |
| `{w:1,j:true}` | Primary writes journal before acknowledgment | More resilient to primary crash, **still subject to rollback** if not majority-replicated |
| `{w:"majority"}` | Majority acknowledges write; journaling depends on `writeConcernMajorityJournalDefault` | Reduces rollback risk when majority is durable |
| `{w:"majority",j:true}` | Majority meets write and journal conditions per server mechanics | Suitable for sensitive writes needing both majority and journaling |
| `{w:3,j:true}` | Required member count and journaling | May wait long / become unachievable if topology lacks members |

### 6.1. Example: `w:1,j:true` is not majority

~~~text
Timeline:

t0  P writes order o301, flushes journal.
t1  Client receives ACK with w:1,j:true.
t2  S1/S2 have NOT received the write yet.
t3  P becomes isolated; S1 is elected as the new primary.
t4  P's write history is not in the majority history.

Possible outcome: order o301 is rolled back when P rejoins the replica set.
~~~

### 6.2. Example: `w:"majority"` improves safety

~~~text
t0  P processes order o301.
t1  S1 reaches the majority acknowledgment point along with P.
t2  Client receives w:"majority" ACK.
t3  P loses connectivity; replica set elects a new primary.

The write was majority-committed under replica set rules, unlike a write
recorded locally on P alone; even if S2 has not applied it yet,
the write has stronger protection against failover.
~~~

This illustrative model assumes a healthy replica set and properly configured majority journaling; it is not an absolute guarantee against simultaneous loss of multiple storage replicas.

## 7. Default write concern: do not guess from driver version

### 7.1. MongoDB 5.0 and later

For **most MongoDB 5.0+ deployments**, the implicit default write concern is `{w:"majority"}`. **There is a notable exception for replica sets containing an arbiter**: in certain topologies, the effective default is `{w:1}`.

For example, a P-S-A set has voting majority 2 but only two data-bearing voting members plus an arbiter—that is precisely a topology where you must verify the default value carefully.

In addition to implicit defaults, administrators can configure **cluster-wide default read/write concern** via a dedicated command. Drivers/clients/applications can also set explicit write concerns. Therefore:

> Never conclude effective write concern simply by reading "MongoDB version >= 5" or "Java Driver defaults to acknowledged."

### 7.2. Checking defaults on the server

In `mongosh` with appropriate administrative privileges:

~~~javascript
db.adminCommand({ getDefaultRWConcern: 1 });
~~~

This command inspects configured default read/write concerns and related default source metadata depending on version. An application may still use a **write concern override**, so this command **does not prove** which level a specific Spring Data method uses.

### 7.3. Checking the configuration path

~~~text
Application policy / MongoTemplate WriteConcernResolver
                   |
          MongoTemplate default
                   |
           Driver MongoClient/DB/Collection
                   |
       Cluster-wide / implicit server default
~~~

This diagram serves as a **configuration source** checklist, not an absolute precedence chain for every API. When a write concern is explicit at the operation/collection level, server defaults no longer dictate the chosen level. In production, verify the **actual `writeConcern` sent** using safe command monitoring/logs and configuration metadata.

### 7.4. Separating server version and driver version

The Java Driver offers constants such as `WriteConcern.ACKNOWLEDGED`, `MAJORITY`, and `JOURNALED`; they describe a client/driver policy. If the driver explicitly sends `w:1`, the fact that a MongoDB 5.0+ server has an implicit majority default **does not turn that write into majority**.

Inspect driver version, Spring Data version, connection string, bean configuration, and deployment to avoid faulty comparisons.

## 8. `wtimeout`: acknowledgment error does not mean rollback

### 8.1. Example write command with timeout

~~~javascript
use spring_data_mongodb_lab

db.payments_write_concern_demo_003.insertOne(
  {
    _id: "pay301",
    tenant_id: "t01",
    order_id: "o301",
    state: "PAID",
    amount_vnd: NumberLong(850000)
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Run this only in a **test database and a replica set supporting majority**, never using fixture IDs on real data. If the insert already succeeded, running it again with the same `_id` triggers a duplicate key error; that is not isolated proof of write concern behavior.

Suppose the write was **applied by the primary**, but secondaries lost connectivity and failed to reach majority within 5 seconds. MongoDB may return a **write concern error**.

What can happen next:

1. The document already exists on the primary.
2. After the command returns an error, secondaries may **continue replicating** and reach majority.
3. Or non-majority data might be rolled back if the old primary loses its role and its history is not chosen.

**Never infer "got a timeout so the insert did not happen."**

### 8.2. `wtimeout` vs. `maxTimeMS` and socket timeout

| Limit | What it controls |
| --- | --- |
| `wtimeout` | Wait time to satisfy write concern `w` after primary processing |
| `maxTimeMS` | Server-side execution time limit for operations supporting that option |
| Client socket/read timeout | Driver wait time for a network response |
| Application/request deadline | Total business time allowed, possibly spanning multiple steps |

`wtimeout` is only meaningful when `w > 1` or `w:"majority"`/equivalent concern. It is not a total end-to-end cap on every write and **does not guarantee the write is aborted upon expiration**.

### 8.3. `wtimeout:0` is not "immediate timeout"

In write concern, `wtimeout:0` means **no write concern wait limit**. If the `w` level remains unachievable for a long time, the request can wait indefinitely, bounded only by other timeouts and system state.

For real-time APIs, set deadlines based on SLOs and risk, rather than "fixing" timeouts by silently dropping `w` from majority to 1 for sensitive data.

### 8.4. Giving users the right answer when write outcome is uncertain

Wrong:

> "Payment failed, please click pay again" — even though the document may already have been written.

Handle it using a **stable idempotency key or business ID**, inspect state with an appropriate read, and then decide retry/reconciliation:

~~~text
Payment request (idempotencyKey = pay301)
       |
       +-- confirmed majority --> return success
       |
       +-- duplicate key / prior result --> compare payload, return prior result
       |
       +-- write concern/network unknown --> PENDING_CONFIRMATION state
                                       inspect/reconcile before retrying
~~~

Never treat a majority acknowledgment error as an automatic rollback.

## 9. Write errors and write concern errors: they are different

MongoDB reports errors at multiple layers:

| Category | Examples | Safe conclusion |
| --- | --- | --- |
| **Write error** | Duplicate key `E11000`, schema validation failure | Primary rejected that operation; fix data/command |
| **Write concern error** | Failed to reach majority within `wtimeout` | Write may have been applied on primary; requested durability was not confirmed |
| **Network/socket timeout** | Client disconnected before response | Operation outcome **cannot be determined** from the exception alone |
| **Server selection timeout** | Could not find a suitable server | Operation may not have been sent; diagnose topology/driver rather than guessing from exception name |
| **Transaction commit uncertainty** | Unknown whether commit succeeded | Use driver-supported commit retry / reconciliation |

### 9.1. `DuplicateKeyException` differs from `wtimeout`

Spring Data may translate duplicate key errors into `org.springframework.dao.DuplicateKeyException` when calling repositories/`MongoTemplate`. A failure to satisfy write concern can surface as a different exception type from the driver/Spring Data.

Do not write:

~~~java
// WRONG:
// catch (Exception ex) {
//     repository.insert(payment); // retry every error
// }
~~~

Because:

- Duplicate key is a data constraint violation; retrying the identical command rarely helps.
- `$inc` or `$push` can apply twice if retried manually after the first write succeeded.
- Network/write concern errors can leave the outcome **unknown**.
- Financial operations require an idempotency key/lock and an independent reconciliation state.

### 9.2. An error does not mean written data was deleted

Suppose `wtimeout` happens after the primary inserted `pay301`. The client receives an error, yet:

~~~javascript
db.payments_write_concern_demo_003.findOne({
  _id: "pay301"
});
~~~

may return the document. However, if this query runs on a stale primary or with a weak read concern, it also **does not prove** the write was majority-committed. Design appropriate read concern/causal sessions and reconciliation procedures.

## 10. Write concern and rollback on primary election

A replica set can suffer a network partition:

~~~text
Before fault:
P  -- S1 -- S2

P processes write W with w:1 -> returns ACK.
W has not reached S1, S2 yet.

After fault:
P is isolated.
S1 + S2 elect a new primary.

P's write W is not in majority history -> may roll back when P rejoins.
~~~

### 10.1. Why does majority reduce rollback risk?

Once a write reaches the majority commit point under replica set mechanics, valid majority elections cannot simply "forget" that committed history the way a write residing solely on an isolated primary can. That is why MongoDB recommends `w:"majority"` alongside proper journaling to prevent rollbacks of writes reported as successful.

**Exception to understand:** If `writeConcernMajorityJournalDefault:false` and multiple nodes crash/restart, a majority-acknowledged write only in memory can still be at risk. Avoid saying "absolute" when describing durability in distributed systems.

### 10.2. Rollback is not a business-level undo

Replica set rollback is a history-reconciliation event among members. It is not equivalent to an application-initiated `rollback transaction`.

A `w:1` write that returned HTTP 200 to a client and then rolled back after failover can leave a state where **the customer thinks it succeeded while the primary record is gone**. This is why high-value business data needs appropriate acknowledgment strategies, idempotency, and failover monitoring.

## 11. Write concern vs. read concern and read preference

| Concept | Question it answers |
| --- | --- |
| `writeConcern` | When does the server return ACK for a write? |
| `readConcern` | With what consistency/stability guarantee does a query read data? |
| `readPreference` | Which primary or secondary does the driver prefer for reads? |
| Causally consistent session | How is a causally linked sequence of reads/writes guaranteed? |

### 11.1. Do not infer "majority write ⇒ every secondary sees it immediately"

**Starting in MongoDB 8.0**, `{w:"majority"}` can be acknowledged once the **oplog entry** is durably written on a majority, while secondaries continue **applying** the change to their collections asynchronously.

Consequently, a direct query to a secondary right after a majority ACK may not yet read the new data from that secondary's collection. Prior to MongoDB 8.0, ACK timing differed because servers waited for operations to be applied under older mechanics.

When you need read-after-write on a secondary across a business flow, use a **causally consistent session** combining `readConcern:"majority"` and `writeConcern:"majority"` per MongoDB's contract.

### 11.2. Read concern `majority` is not write concern `majority`

~~~javascript
// Two independent settings:
{ readConcern: { level: "majority" } }
{ writeConcern: { w: "majority" } }
~~~

Setting `readConcern:"majority"` **does not make writes use majority**, and vice versa. When a service needs read-your-writes across secondaries within a session, configure both sides along with the session.

### 11.3. Read preference `secondary` can read lagging data

~~~text
write on primary -> replica writes oplog -> secondary applies -> secondary serves read
~~~

A secondary can lag due to network, I/O, apply queues, or partitions. `readPreference.secondary()` only tells the driver where to read; it does not guarantee fresh data. For flows needing the just-written state, clarify whether you need a causal session, primary read, or stronger isolation.

### 11.4. Majority write does not automatically create linearizability

"Reading the absolute latest state" is a stronger contract than `w:"majority"` alone. MongoDB also offers `readConcern:"linearizable"` for qualifying operations, with topology and write concern prerequisites. Do not conflate levels:

~~~text
majority ACK ≠ every reader on every node sees it immediately
majority ACK ≠ multi-document transaction
majority ACK ≠ linearizable read in all scenarios
~~~

## 12. Configuring via `mongosh` and connection string

### 12.1. A specific write

~~~javascript
db.payments_write_concern_demo_003.updateOne(
  {
    _id: "pay301",
    tenant_id: "t01",
    state: "PENDING"
  },
  {
    $set: { state: "PAID" }
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

**Note:** This example transitions from `PENDING` to `PAID`, so it only matches if the document is in the expected state. If you already ran the `pay301` fixture with `state:"PAID"` in Section 8, `matchedCount=0` is expected. Create a separate `PENDING` document when practicing state transitions.

### 12.2. Setting write concern for a `mongosh` connection

~~~javascript
db.getMongo().setWriteConcern({
  w: "majority",
  j: true,
  wtimeout: 5000
});

db.payments_write_concern_demo_003.insertOne({
  _id: "pay302",
  tenant_id: "t01",
  order_id: "o302",
  state: "PENDING",
  amount_vnd: NumberLong(250000)
});
~~~

This configures the **active shell connection**. It does not alter cluster-wide defaults or settings on a separate Java `MongoClient`.

### 12.3. MongoDB URI in Java/Spring Boot

Example:

~~~properties
# Configuration example; substitute actual hosts and credentials per environment.
spring.data.mongodb.uri=mongodb://mongo1:27017,mongo2:27017,mongo3:27017/payments_lab?replicaSet=rs0&w=majority&journal=true&wTimeoutMS=5000
~~~

In real replica set deployments, the URI must contain valid hosts/topology. Never hardcode passwords in code or commit secrets in properties files; use a secret manager or environment variables.

**Caution:** `w=majority` in the URI is the **driver/connection write concern** per driver application rules. A specific `MongoTemplate` or operation can override it with its own write concern. Do not assume from `spring.data.mongodb.uri` that every client bean in the app automatically shares the same policy.

### 12.4. Preserving timeout semantics

If an API enforces a 2-second request deadline while `wTimeoutMS=5000`, understand that **the client may stop waiting before the server finishes evaluating write concern**. Conversely, lowering `wtimeout` does not make the initial write safe to blindly retry. Policies must combine deadlines, idempotency, and handling for uncertain states.

## 13. MongoDB Java Driver: client- and collection-level configuration

### 13.1. Common `WriteConcern` constants

~~~java
import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;

WriteConcern unacknowledged = WriteConcern.UNACKNOWLEDGED; // w:0
WriteConcern primaryOnly   = WriteConcern.ACKNOWLEDGED;   // w:1
WriteConcern journaled     = WriteConcern.JOURNALED;      // w:1,j:true
WriteConcern majority      = WriteConcern.MAJORITY;       // w:"majority"

WriteConcern critical =
    WriteConcern.MAJORITY
        .withJournal(true)
        .withWTimeout(5, TimeUnit.SECONDS);
~~~

Note that `WriteConcern.JOURNALED` typically maps to `w:1,j:true` — **not majority**. The name `JOURNALED` expresses journal durability at that level; to require both majority and journaling, compose explicitly as in `critical`.

### 13.2. Collection-specific write concern

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.InsertOneResult;
import java.util.concurrent.TimeUnit;
import org.bson.Document;

// mongoClient is a pre-configured com.mongodb.client.MongoClient.
MongoDatabase database = mongoClient.getDatabase(
    "spring_data_mongodb_lab"
);

MongoCollection<Document> collection = database
    .getCollection("payments_write_concern_demo_003")
    .withWriteConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS)
    );

InsertOneResult result = collection.insertOne(
    new Document("_id", "pay303")
        .append("tenant_id", "t01")
        .append("state", "PENDING")
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Write was unacknowledged");
}
~~~

`withWriteConcern(...)` returns a **configured collection handle**. It does not permanently alter the MongoDB collection on the server or create a server-level policy; the setting applies to operations executed through that handle.

### 13.3. What does `wasAcknowledged()` mean precisely?

`result.wasAcknowledged() == true` means the operation received acknowledgment according to the write concern **that was used**. If the collection handle used `w:1`, `true` **does not prove majority**.

Therefore:

~~~java
// WRONG inference:
// if (result.wasAcknowledged()) { assertMajorityDurable(); }
~~~

Verify **effective write concern configuration** and topology in addition to the boolean result. Even a test on a single-node replica set with `MAJORITY` **does not prove** multi-member waiting, because majority of one voting member is one.

### 13.4. Update result counts differ from write concern

~~~java
var result = collection.updateOne(
    new Document("_id", "pay303"),
    new Document("$set", new Document("state", "PAID"))
);

if (result.wasAcknowledged()) {
    long matched = result.getMatchedCount();
    long modified = result.getModifiedCount();
}
~~~

`matchedCount` and `modifiedCount` answer "how many documents matched/changed," **not** "was it majority journaled." An operation can return `matched=1, modified=0` (setting the same value) and still be an acknowledged write. With `w:0`, most result accessors are meaningless and throw exceptions if accessed.

## 14. Spring Data `MongoTemplate`: setting write concern

Spring Data MongoDB allows configuring `com.mongodb.WriteConcern` on `MongoTemplate`. If unset on the template, it typically inherits the write concern from the corresponding database factory/driver/collection.

### 14.1. A `MongoTemplate` using majority + journal

~~~java
package com.example.consistency;

import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class ConsistencyMongoConfig {

    @Bean("criticalMongoTemplate")
    MongoTemplate criticalMongoTemplate(
            MongoDatabaseFactory factory) {

        MongoTemplate template = new MongoTemplate(factory);
        template.setWriteConcern(
            WriteConcern.MAJORITY
                .withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS)
        );
        return template;
    }
}
~~~

When a service injects this bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class PaymentWriteService {
    private final MongoTemplate criticalTemplate;

    public PaymentWriteService(
            @Qualifier("criticalMongoTemplate")
            MongoTemplate criticalTemplate) {
        this.criticalTemplate = criticalTemplate;
    }

    public PaymentDocument save(PaymentDocument payment) {
        return criticalTemplate.insert(payment);
    }
}
~~~

`PaymentDocument` is an illustrative domain entity defined in Section 16.1. This writes through **the selected template**; it does not imply all repositories in the application automatically switch to that template.

**Spring Boot integration warning:** Adding an extra `MongoTemplate` can affect auto-configuration and default template injection. With multiple beans, use `@Qualifier`, configure repository factories properly, and verify actual write paths before assuming repositories share the new policy.

### 14.2. `WriteConcernResolver`: selecting by operation/aggregate type

If an application needs different policies for critical entities vs. regenerable entities, use `WriteConcernResolver`:

~~~java
import com.mongodb.WriteConcern;
import org.springframework.data.mongodb.core.MongoTemplate;

// Configure before the template begins serving requests:
template.setWriteConcernResolver(action -> {
    Class<?> type = action.getEntityType();

    if (type != null
            && PaymentDocument.class.isAssignableFrom(type)) {
        return WriteConcern.MAJORITY.withJournal(true);
    }

    return action.getDefaultWriteConcern();
});
~~~

`MongoAction` exposes entity type, collection, operation type, and default concern so the resolver can decide. Never inspect sensitive document fields to log them, and avoid rules that give a single payment collection unexplained mixed durability levels.

**Limitation:** Operations executed via the raw driver or a different template bypass **this template's** resolver.

### 14.3. Which path do repositories use?

Standard `MongoRepository` beans use the configured Spring Data infrastructure (typically backed by `MongoOperations`) to perform CRUD. They **do not have a built-in per-method `@WriteConcern` annotation** analogous to `Query.collation(...)`.

For predictable configuration:

1. Set write concern at the `MongoClient`/URI level if it is the global policy.
2. Configure dedicated templates/repository factories if certain repositories require a distinct policy.
3. Use `MongoTemplate`/custom fragments for use cases needing explicit concern control.
4. Verify with command monitoring or configuration integration tests that real writes go through the expected path.

Never infer from `@Document` or a repository name that writes are majority-acknowledged.

### 14.4. `WriteResultChecking` differs from write concern

`MongoTemplate.setWriteResultChecking(WriteResultChecking.EXCEPTION)` controls how Spring Data checks/reports write errors in supported flows. It **does not set `w:"majority"`** and does not turn `w:0` into an acknowledged write.

~~~java
import org.springframework.data.mongodb.core.WriteResultChecking;

template.setWriteResultChecking(
    WriteResultChecking.EXCEPTION
);
~~~

This is a template-side error checking policy, **not** a durability setting replacing `setWriteConcern`.

## 15. Reactive Spring Data: a publisher is not an ACK

`ReactiveMongoTemplate` also supports setting write concern:

~~~java
import com.mongodb.WriteConcern;
import java.util.concurrent.TimeUnit;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

// reactiveTemplate was created with ReactiveMongoDatabaseFactory.
reactiveTemplate.setWriteConcern(
    WriteConcern.MAJORITY
        .withJournal(true)
        .withWTimeout(5, TimeUnit.SECONDS)
);
~~~

A reactive service:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public class ReactivePaymentWriteService {
    private final ReactiveMongoTemplate reactiveTemplate;

    public ReactivePaymentWriteService(
            ReactiveMongoTemplate reactiveTemplate) {
        this.reactiveTemplate = reactiveTemplate;
    }

    public Mono<PaymentDocument> insert(PaymentDocument payment) {
        return reactiveTemplate.insert(payment);
    }
}
~~~

**A `Mono<PaymentDocument>` emitting one item does not mean `w:1` or `w:"majority"`.** Publisher cardinality describes item count in the reactive API; write durability is determined by the effective write concern on the driver/template.

Publishers generally **do not execute** until subscribed. In WebFlux, compose results in the reactive chain; never call `block()` on an event loop to "wait for majority" in a blocking way.

### 15.1. Handling write concern errors in a reactive chain

~~~java
Mono<PaymentDocument> write = service.insert(payment)
    .doOnSuccess(saved -> {
        // Succeeded per the configured write concern.
        // Do not assume more without verifying the active policy.
    })
    .doOnError(error -> {
        // Classify the error. Do not blindly retry if outcome may be unknown.
    });
~~~

For retryable business operations, use idempotency keys and reconciliation queries rather than slapping `.retry(3)` onto every `MongoException`—especially with `$inc`/`$push` or flows with side effects outside MongoDB.

## 16. Domain example: recording payments with a stable ID

### 16.1. Entity and index

~~~java
// PaymentDocument.java
package com.example.consistency;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "payments_write_concern_demo_003")
public class PaymentDocument {
    @MongoId(FieldType.STRING)
    private String id; // stable idempotency key

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    private Instant createdAt;

    protected PaymentDocument() { }

    public PaymentDocument(
            String id,
            String tenantId,
            String orderId,
            long amountVnd,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.amountVnd = amountVnd;
        this.state = "PENDING";
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderId() { return orderId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
}
~~~

`_id` has a default unique index in MongoDB, preventing the same `idempotency key` from creating two separate documents. **Never** treat a unique `_id` alone as an automatic "charge only once" guarantee with an external payment gateway—you still need a state machine, request fingerprint validation, and side-effect reconciliation.

### 16.2. Repository

~~~java
// PaymentRepository.java
package com.example.consistency;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface PaymentRepository
        extends MongoRepository<PaymentDocument, String> {
}
~~~

### 16.3. Service with majority write concern

~~~java
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class PaymentCreationService {
    private final MongoTemplate criticalTemplate;

    public PaymentCreationService(
            @Qualifier("criticalMongoTemplate")
            MongoTemplate criticalTemplate) {
        this.criticalTemplate = criticalTemplate;
    }

    public PaymentDocument register(
            String requestId,
            String tenantId,
            String orderId,
            long amountVnd) {
        PaymentDocument next = new PaymentDocument(
            requestId,
            tenantId,
            orderId,
            amountVnd,
            Instant.now()
        );

        try {
            return criticalTemplate.insert(next);
        } catch (DuplicateKeyException duplicate) {
            PaymentDocument prior = criticalTemplate.findById(
                requestId, PaymentDocument.class
            );
            if (prior == null) {
                // Duplicate occurred, yet the read did not confirm it yet.
                throw duplicate;
            }
            if (!tenantId.equals(prior.getTenantId())
                    || !orderId.equals(prior.getOrderId())
                    || amountVnd != prior.getAmountVnd()) {
                throw new IllegalStateException(
                    "Idempotency key reused with different request");
            }
            return prior; // Return the prior record matching the same request.
        }
    }
}
~~~

This code illustrates the **happy-path idempotency flow** and duplicate handling. It is **not yet complete for a production payment service**:

- When write concern/network outcome is unknown, the exception is not necessarily `DuplicateKeyException`; an independent reconciliation job/API is needed.
- `findById` has its own read concern/read preference; it may not prove majority commit in every situation.
- Tenant must be bound from the security context, never trusting spoofable input.
- `_id` collisions could stem from another error; never mask every duplicate by returning an existing record without comparing fingerprints.
- Third-party payment status updates and outbox/transaction integration are not shown here.

### 16.4. Why `save` does not replace idempotency

`repository.save(entity)` has insert/replace semantics depending on identifier state; if a request is re-sent with the same ID and a different payload, `save` can overwrite old data inappropriately. For **"create exactly one payment per requestId,"** `insert` + unique ID + fingerprint verification is much clearer.

Never apply `$inc` to account balances relying solely on "we waited for majority" without guards/idempotency: majority solves **ACK durability**, not **duplicate business execution**.

## 17. Retryable writes and uncertain outcomes

The MongoDB Java Driver supports **retryable writes** for eligible operations on supported topologies and versions. Yet driver retries are **not** a license for applications to blindly retry every write command.

### 17.1. Three layers to separate

| Layer | Role |
| --- | --- |
| **Driver retry** | Can retry certain eligible writes after transient errors, preserving operation/session identity per driver protocol |
| **Application retry** | Can re-invoke a workflow when a request times out or a dependency fails |
| **Business idempotency** | Ensures a business request does not execute side effects twice, even when requests repeat |

### 17.2. Avoid blindly retrying `$inc`

~~~javascript
db.wallets_write_concern_demo_003.updateOne(
  { _id: "wallet301" },
  { $inc: { balance_vnd: -100000 } },
  { writeConcern: { w: "majority", wtimeout: 2000 } }
);
~~~

If a request hits a network timeout after the server already deducted the balance, an application retry issued **as a new command** can deduct another 100,000. Majority write concern does not make `$inc` idempotent.

**Safer pattern:** record a transaction/ledger entry using a unique request ID, inspect the entry's state, conditionally deduct balance or use an appropriate transaction, and return results based on persisted state. Never just increase timeouts to hide double-charge bugs.

### 17.3. Is `$set` always idempotent?

~~~javascript
{ $set: { state: "PAID" } }
~~~

Assigning a field to the same value may be idempotent **at the field-value level**, yet if the same operation also updates `updatedAt`, version, counters, audit events, or external side effects, it is **no longer workflow-idempotent**.

Retry design must evaluate **the entire business operation**, not just a single MongoDB operator.

### 17.4. Uncertain outcomes require dedicated API states

An API response might define statuses like:

~~~text
CONFIRMED         : write satisfied the durability policy.
PENDING_CONFIRM   : uncertain; checking/reconciling.
REJECTED          : rejected by business validation or unique constraint.
FAILED_RETRYABLE  : confirmed transient error, safe to retry.
~~~

This is an **illustrative state machine**, not a MongoDB-provided enum. State transitions must be evidence-based—never map every exception to `FAILED` and tell the user to resubmit payment.

## 18. Transactions: write concern is set at commit

MongoDB transactions can execute multiple writes atomically within supported bounds. **For multi-document transactions, write concern must be specified at the transaction level—do not attach separate write concerns to individual operations inside the transaction.**

### 18.1. Why `w:1` at commit still carries risk

Even after a transaction commits with `w:1`, data can be rolled back after failover if the commit was not majority-replicated. MongoDB explicitly documents transaction rollback risk when using write concern `w:1`.

If a transaction writes both order + payment and the API requires high durability, configure an appropriate **commit** write concern—typically considering majority and journaling.

### 18.2. Spring Data transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentWorkflowService {
    private final MongoTemplate template;

    public PaymentWorkflowService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager",
        label = {
            "mongo:readConcern=SNAPSHOT",
            "mongo:writeConcern=MAJORITY"
        }
    )
    public void transitionOrderAndRecordPayment(
            OrderDocument order,
            PaymentDocument payment) {
        // Illustrates two writes within one transaction only.
        // Real implementations require full validation and state checks.
        template.save(order);
        template.insert(payment);
    }
}
~~~

`OrderDocument` is an illustrative order aggregate not fully defined in this lesson. When adapting this into a runnable project example, declare the order entity/mapping, ensure `template` uses **the same `MongoDatabaseFactory`** as the transaction manager, and run on a replica set/sharded deployment supporting transactions.

Labels like `mongo:writeConcern=MAJORITY` and `mongo:readConcern=SNAPSHOT` are supported in recent Spring Data MongoDB versions via the transaction option resolver. On older versions, configure transaction options through the transaction manager/API; do not assume every version parses annotation labels.

### 18.3. Notes on commit and retries

When `commitTransaction` hits a network error, do not immediately conclude the transaction rolled back. MongoDB/drivers use error labels such as `UnknownTransactionCommitResult` and `TransientTransactionError` to guide proper retry logic in specific scenarios.

If there are side effects **outside** MongoDB (sending email, calling a payment gateway), a MongoDB transaction cannot roll them back. For multi-system workflows, consider **outbox**, saga, idempotency, and delivery controls.

### 18.4. Transactions do not upgrade APIs without a manager

Putting `@Transactional` on a Spring method **does not guarantee** a MongoDB multi-document transaction unless the project configures `MongoTransactionManager`/`ReactiveMongoTransactionManager` and a supporting topology.

Spring Data also has requirements around sessions, pre-existing collections, and driver config; verify in integration tests.

## 19. Operations: choosing concern from SLOs and criticality

Do not pick `w:1` for every write solely for low latency, and do not hardcode `w:3,j:true` for every workload without checking how many data-bearing members the cluster has.

| Workload | Data-loss risk | Policy to evaluate |
| --- | --- | --- |
| Payments, ledgers, finalized order states | High | `w:"majority"` with properly configured journaling, idempotency, audit/outbox |
| Non-regenerable event history | High | Majority + recovery guarantees, backups, and reconciliation workflows |
| Critical business configuration | Medium–high | Consider majority, version guards, and post-write verification |
| Rebuildable caches | Lower | Weaker acknowledgment may be considered if rollback is acceptable |
| High-frequency counters/telemetry | Depends on use case | Batching, criticality tiering; avoid unacknowledged when exact counts are required |
| Job queues/claims | Medium–high | Atomic updates/`findAndModify` with state predicates and suitable durability policy |

**This is a decision framework, not a mandatory default configuration.** Evaluate write volume, replication lag, quorum, disk cost, deadlines, timeout rates, and recoverability.

### 19.1. Operational signals to monitor

- Write latency by p50/p95/p99 and write concern.
- Rate of write concern errors, timeouts, and retries.
- Replication lag, majority commit point, member states.
- Election/stepdown and rollback events.
- Journal/storage latency and I/O bottlenecks.
- Count of requests with unknown outcomes and reconciliation time.
- Rate of duplicate key/idempotency conflicts.
- Driver command durations and connection pool health.

If majority writes suddenly slow down, do not immediately downgrade write concern. Inspect inter-member networking, secondary lag, storage/journal I/O, elections, and write load.

### 19.2. When majority cannot be reached

Example P-S-S replica set where only P is reachable because both secondaries disconnected:

~~~text
w:1           -> primary can continue acknowledging certain writes.
w:"majority"  -> threshold cannot be met; may time out or error.
~~~

This drop in availability is an **intentional trade-off** when requiring majority-acknowledged writes. For sensitive data, never "fail open" to `w:1` just to keep returning HTTP 200—doing so increases the risk of losing writes after failover.

### 19.3. Backups are still essential

Majority + journaling **do not replace backups**. They do not fully protect against accidental majority-committed deletes, application bugs, code-driven data corruption, full infrastructure zone loss, or point-in-time recovery needs.

## 20. Integration tests: what do they prove and not prove?

### 20.1. Testing against a real replica set

To test most Spring Data APIs and write concerns, use a MongoDB **test replica set** (e.g., Testcontainers configured as a replica set). Standalone MongoDB can test basic inserts, but **cannot simulate multi-member replica set majorities**.

| Test | What it verifies |
| --- | --- |
| Driver collection handle `withWriteConcern(MAJORITY)` | Driver handle retains expected policy |
| `insertOne` with majority on single-node replica set | Operation ACKs per majority of **one** member; does not verify replication to secondaries |
| `MongoTemplate` with majority policy | Write path through template works |
| `InsertOneResult.wasAcknowledged()` | Write ACK per applied concern; does not prove specific topology |
| Duplicate `_id` | Database rejects duplicates; Spring Data translates exception properly |
| Write timeout under fault-simulated topology | Requires multiple data-bearing members and controllable test environment |
| Primary stepdown before/after majority | Requires dedicated chaos/integration test; never induce faults on shared clusters |
| Secondary read after majority ACK on MongoDB 8+ | Tests causal session/lag behavior per version |
| Transaction commit write concern | Uses transaction manager; tests both result and resilience |

### 20.2. Testing configuration and acknowledged writes

~~~java
package com.example.consistency;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.WriteConcern;
import com.mongodb.client.result.InsertOneResult;
import java.util.concurrent.TimeUnit;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class WriteConcernAcknowledgmentTest {
    @Autowired MongoTemplate template;

    @Test
    void majorityWriteHasAcknowledgedResult() {
        String id = "fixture-wc003";
        var base = template.getDb().getCollection(
            "payments_write_concern_it_003"
        );

        var majority = WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS);

        var collection = base.withWriteConcern(majority);

        // Test data belongs to an isolated test database.
        base.deleteOne(new Document("_id", id));
        try {
            InsertOneResult result = collection.insertOne(
                new Document("_id", id)
                    .append("tenant_id", "test-tenant")
                    .append("state", "PENDING")
            );

            assertThat(collection.getWriteConcern())
                .isEqualTo(majority);
            assertThat(result.wasAcknowledged()).isTrue();
            assertThat(base.countDocuments(
                new Document("_id", id)
            )).isEqualTo(1L);
        } finally {
            base.deleteOne(new Document("_id", id));
        }
    }
}
~~~

**Test limitations:** this **does not** simulate secondary failover or prove two out of three members actually journaled. On a single-node replica set, majority requires only one node; on standalone, semantics differ from a multi-node replica set. Separate chaos tests on a suitable topology are still needed.

### 20.3. Testing Spring Data `DuplicateKeyException`

Add inside a test class with `template`:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.dao.DuplicateKeyException;

@Test
void duplicateIdIsRejected() {
    String id = "fixture-wc003-dup";
    var collection = template.getDb().getCollection(
        "payments_write_concern_it_003"
    );

    collection.deleteOne(new Document("_id", id));
    try {
        template.insert(
            new org.bson.Document("_id", id)
                .append("state", "PENDING"),
            "payments_write_concern_it_003"
        );

        assertThatThrownBy(() -> template.insert(
            new org.bson.Document("_id", id)
                .append("state", "PAID"),
            "payments_write_concern_it_003"
        )).isInstanceOf(DuplicateKeyException.class);
    } finally {
        collection.deleteOne(new Document("_id", id));
    }
}
~~~

This test must run while the driver/template uses **acknowledged writes**; if forced to `w:0`, expecting `DuplicateKeyException` on the client is no longer reliable. This test verifies `_id` constraints and exception translation, not majority journaling.

### 20.4. Chaos testing timeouts — only on a cluster you are allowed to disrupt

In a **test-owned three-node replica set**, you can:

1. Issue a write with `w:"majority"` and a finite `wtimeout`.
2. In a controlled manner, make secondaries temporarily unable to acknowledge.
3. Send the write to primary and observe the write concern error.
4. Verify the primary may already have saved the document despite the client error.
5. Restore secondaries and reconcile the write using an appropriate read concern.
6. Repeat an election scenario to verify rollback risk of `w:1`.

**Never drop replicas or trigger stepdowns on production or shared test MongoDB clusters.** No lesson justifies causing disruption simply to experiment. You can start by unit/service-testing simulated exceptions and isolate real failover tests in a dedicated chaos environment.

### 20.5. Checking configuration consistency

An application may simultaneously contain:

- Default `MongoRepository` beans.
- A dedicated `MongoTemplate` for payments.
- `ReactiveMongoTemplate` for WebFlux.
- Direct Java Driver `MongoCollection` usage.

Audit each write path and its **effective write concern**. Testing one template **does not prove** another repository or reactive template uses the same policy.

## 21. Common mistakes

| Assumption or symptom | Why it is wrong | How to handle it |
| --- | --- | --- |
| "Once ACKed, data cannot be lost" | `w:1` can roll back after an election | Choose concern per durability needs; verify journaling |
| "`j:true` equals majority" | Primary journaling does not prove replica majority | Use `w:"majority"` when preventing failover rollbacks |
| "`w:"majority"` means all secondaries applied it" | Majority needs a subset; MongoDB 8+ can ACK oplog before secondary apply | Use causal sessions with majority read/write for read-after-write |
| "`w:2` is always majority" | A 5-voting-member topology needs majority 3 | Specify `w:"majority"` per business requirement |
| "Arbiters help ACK majority writes" | Arbiters hold no data | Check data-bearing voting members and default concerns |
| "MongoDB 5+ always defaults to majority" | Arbiter topologies and explicit client/cluster defaults exist | Check `getDefaultRWConcern` and actual commands |
| "`wtimeout` means the server did not write" | Primary may have applied it and secondaries may catch up later | Reconcile/use idempotency; never blindly retry |
| "`wtimeout:0` means instant timeout" | `0` means no write concern timeout limit | Configure timeouts matching SLOs |
| "Socket timeout means insert failed" | Outcome may be unknown | Verify by key/idempotency; classify errors |
| "`wasAcknowledged()==true` proves majority" | Could just be a `w:1` ACK | Verify applied write concern, topology, and driver |
| "`matchedCount=0` is a durability error" | It is a predicate result; document may not match | Distinguish matched/modified counts from ACKs |
| "`@Transactional` always creates a MongoDB transaction" | Missing manager/topology or session config | Configure the transaction manager properly and test |
| "Inside a transaction, set `w` per write" | MongoDB requires write concern at the transaction level | Set transaction write concern at commit |
| "Driver retries let apps retry any `$inc`" | Manual retries as new operations can increment twice | Use idempotency and classified retry policies |
| "Read concern majority raises write concern" | They are two separate settings | Configure both reads and writes appropriately |
| "Reactive `Mono` of one item means `w:1`" | Publisher cardinality is unrelated to write concern | Inspect template/driver config |
| "Majority writes are slow because of Java mapping" | They may be waiting on replication/journal/topology | Monitor secondary lag and journal I/O |
| "Majority + journal replace backups" | They do not protect against accidental committed deletes or bugs | Keep backups, PITR, and recovery plans |

## 22. Pre-release checklist for write workflows

1. **Classify data** by write-loss tolerance: payments, orders, audit logs, caches, or telemetry.
2. **Inspect topology**: P-S-S vs. P-S-A, number of voting data-bearing members, replica lag, journaling.
3. **Never assume defaults**: confirm write concern on `MongoClient`/URI, templates, resolvers, and server.
4. **Pick `w` explicitly**: `w:1`, `w:"majority"`, or numeric per real requirements.
5. **Evaluate `j` together with `writeConcernMajorityJournalDefault`** instead of separating journaling from durability.
6. **Set appropriate `wtimeout`** and distinguish it from overall/request/socket deadlines.
7. **Design for unknown outcomes**: never map timeouts directly to definite failure.
8. **Use idempotency keys** and reconciliation states for operations that must not repeat.
9. **Separate ACK from result counts**: `matchedCount`/`modifiedCount` are not durability proofs.
10. **Define read-after-write**: read primary, or use read concern/causal session when reading secondaries.
11. **Set write concern at commit** when using multi-document transactions.
12. **Audit every write path**: repositories, templates, reactive, and raw driver calls.
13. **Test exception translation** and business errors like duplicate keys.
14. **Run isolated chaos tests** for failover, replication lag, and write concern timeouts.
15. **Track metrics**: errors, majority lag, journal latency, rollback events.
16. **Maintain backup/restore** and an operational runbook when majority is unreachable.

## 23. Practice exercises and answers

These questions are independent scenarios. You do not need to disrupt a production replica set to answer them.

### Exercise 1 — Primary ACK

MongoDB receives `{w:1}`, and the primary acknowledges the insert. Can you state that the data is durable across failover?

**Answer:** No. The write may not have replicated yet; if the primary loses its role and its write history is not part of the majority, the acknowledged write can still roll back.

### Exercise 2 — `w:1,j:true`

If the primary already journaled the write, why can it still roll back?

**Answer:** Journaling helps recovery after a primary crash, yet does not ensure the history is accepted by a replica set majority. A new primary can be elected from members that never received that write.

### Exercise 3 — Majority in a three-node replica set

A P-S1-S2 replica set has all three voting and data-bearing. How many members does `w:"majority"` require?

**Answer:** Two of the three eligible voting data-bearing members, typically P and at least one secondary.

### Exercise 4 — Majority in a five-node replica set

Is `w:2` identical to `w:"majority"`?

**Answer:** No. Majority of five voting members is three, whereas `w:2` requires two eligible members.

### Exercise 5 — P-S-A

Can an arbiter substitute for a disconnected secondary to acknowledge a majority write?

**Answer:** No. An arbiter votes in elections but stores no data or oplog; it cannot contribute a data-bearing acknowledgment. In P-S-A, the data-bearing secondary is required to achieve a majority write.

### Exercise 6 — MongoDB 5+ defaults

Can you always assume that leaving write concern unconfigured yields `w:"majority"`?

**Answer:** No. Most 5+ deployments use majority as an implicit default, yet certain topologies with arbiters may default to `w:1`, and explicit client/cluster configurations can override it.

### Exercise 7 — Default journaling

`w:"majority"` is set while `j` is omitted. Does MongoDB always wait for the journal?

**Answer:** It depends on `writeConcernMajorityJournalDefault` and the storage engine/topology. Under the typical default `true`, majority acknowledgment includes journal durability; if `false`, it may ACK while data is only in memory.

### Exercise 8 — `wtimeout`

A majority write times out after 5 seconds. Can you assert the collection definitely does not contain the document?

**Answer:** No. The primary may have applied it, and secondaries may continue replicating after the error. Reconcile instead of retrying blindly.

### Exercise 9 — `wtimeout:0`

Does this mean "do not wait"?

**Answer:** No. It specifies no timeout limit for waiting on the write concern.

### Exercise 10 — `matchedCount=0`

`UpdateResult.wasAcknowledged()==true`, `matchedCount==0`. Did durability fail?

**Answer:** Not necessarily. ACK reflects write acknowledgment level, whereas matched count indicates the filter matched no documents; they are two independent axes.

### Exercise 11 — Java Driver

Write a configuration for majority + journal + 5-second timeout.

**Answer:**

~~~java
WriteConcern concern = WriteConcern.MAJORITY
    .withJournal(true)
    .withWTimeout(5, TimeUnit.SECONDS);
~~~

### Exercise 12 — Spring Data template

How do you set this policy on a `MongoTemplate`?

**Answer:**

~~~java
template.setWriteConcern(
    WriteConcern.MAJORITY.withJournal(true)
);
~~~

Verify that services/repositories **actually use that template**, rather than merely registering a bean in the application context.

### Exercise 13 — Secondary read

MongoDB 8+ ACKed `w:"majority"`, so is the document guaranteed to appear immediately on a secondary read?

**Answer:** Not guaranteed. The secondary may have durably written the oplog entry without having applied it to the collection yet. Use a causally consistent session pairing majority read and majority write when read-your-writes across secondaries is needed.

### Exercise 14 — Retrying `$inc`

A wallet deducts 100,000 via `$inc:-100000` and the client times out. Should you replay the exact same request as a fresh request?

**Answer:** No. The first attempt may already have deducted it. Design a ledger/idempotency key and inspect the outcome before retrying.

### Exercise 15 — Transaction commit

A transaction updates two collections. Should write concern be configured on each `updateOne` or at the transaction level?

**Answer:** **At the transaction/commit level**, per MongoDB rules. If commit only ACKs with `w:1`, rollback risk after failover remains.

### Exercise 16 — Performance

After switching from `w:1` to majority, p95 write latency rises. Should you immediately drop back to `w:1`?

**Answer:** Not automatically. Measure replication lag, disk/journal latency, topology, and workload; weigh durability/SLO requirements before changing policy.

### Exercise 17 — Testing

On a single-node replica set test, `WriteConcern.MAJORITY` succeeds. Does that prove two replicas ACKed?

**Answer:** No. Majority of a single node is one. Testing replication acknowledgment requires multiple data-bearing voting members and fault testing in a dedicated environment.

### Exercise 18 — Idempotency and duplicate keys

Resending `paymentId=pay301` returns a duplicate key error. Is this retry guaranteed harmless?

**Answer:** Not yet. Verify that tenant, order, amount, and request fingerprint **match the original request**; if they differ, report a conflict rather than returning success.

### Exercise 19 — Unacknowledged

Can `w:0` tell you an insert failed with E11000 so you can immediately return HTTP 409?

**Answer:** No. Without requesting server acknowledgment, the client gets no reliable duplicate-key signal. Use acknowledged writes whenever business flows need accurate responses.

### Exercise 20 — Backups

The application uses `w:"majority",j:true`. Are backups still needed?

**Answer:** Yes. Majority/journaling cannot recover accidental majority-committed deletes or many operational mistakes; keep backups and test restores.

## References

- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): `w`, `j`, `wtimeout`, acknowledgments, implicit defaults, majority journaling, and MongoDB 8+ differences.
- [MongoDB Manual — Write Concern for Replica Sets](https://www.mongodb.com/docs/manual/core/replica-set-write-concern/): majority, numeric write concerns, replica members, and timeouts.
- [MongoDB Manual — Rollbacks During Replica Set Failover](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/): `w:1` rollbacks, majority durability, and journaling.
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/): journal syncing and storage engine differences.
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): majority write/read concerns and causal guarantees.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary reads and stale data risks.
- [MongoDB Manual — Default Read and Write Concerns](https://www.mongodb.com/docs/manual/reference/mongodb-defaults/): topology-based defaults and arbiter cases.
- [MongoDB Java Sync Driver — Configure Client-level CRUD Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/configure-crud/): `w`, `journal`, `wTimeoutMS`, and URI/driver options.
- [MongoDB Java Sync Driver — Configure Replica Set Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/): `withWriteConcern`, `ReadConcern`, and `ReadPreference`.
- [Spring Data MongoDB — Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-config.html): `MongoTemplate.setWriteConcern`, `WriteConcernResolver`, and write result checking.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): transaction managers, commit write concern, transaction options, and error labels.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): write concern settings and write result handling.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): configuring write concern in the reactive template.
