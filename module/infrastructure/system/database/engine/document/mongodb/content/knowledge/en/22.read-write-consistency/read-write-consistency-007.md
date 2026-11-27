# Conditions for guaranteeing read-your-writes in MongoDB

An API just successfully wrote an order to MongoDB and immediately queries it back to return the result. In a single-node test environment, **read-your-writes** often seems obvious. However, when the application connects to a **replica set**, reads from secondaries, spans multiple services, performs retries, or experiences failovers, the subsequent read may fail to see the new record, observe an older version, or return an error.

To reason accurately, you must distinguish several mechanisms often lumped together into the single question "Is MongoDB consistent?":

- **Read-your-writes (RYW)**: within a causally related sequence of operations, subsequent reads observe the effects of earlier completed writes under the chosen consistency conditions.
- **Write concern**: what acknowledgments MongoDB must receive before reporting a write command as successful.
- **Read concern**: the level of guarantee applied to data a read command is permitted to observe.
- **Read preference**: whether the application reads from the primary, secondaries, or selects nodes according to another policy.
- **Causally consistent session**: the MongoDB Driver carries causal timestamp metadata across operations within the same session, helping preserve orderings such as "write then read" when paired with proper read/write concerns.
- **Transaction**: a group of operations executed with dedicated commit and visibility rules.

The goal of this lesson is to **identify the required conditions**, rather than memorizing an isolated setting. We will walk through concrete scenarios, examine how replication behaves, practice with `mongosh` and the MongoDB Java Sync Driver, and handle secondary reads, failovers, network errors, and multi-step APIs.

## 1. What does "read-your-writes" mean precisely?

Suppose a user creates a profile:

~~~text
Time t1:  POST /profiles
          MongoDB writes profile P-100
          Server acknowledges success

Time t2:  GET /profiles/P-100
          Application expects to see P-100
~~~

**Read-your-writes** requires a causally subsequent read operation after a write to observe the effect of that write, subject to the corresponding guarantees. If the write operation is:

~~~javascript
db.profiles.insertOne({
  _id: "P-100",
  displayName: "An",
  version: 1
});
~~~

then the follow-up read question is:

~~~javascript
db.profiles.findOne({ _id: "P-100" });
~~~

However, note three distinctions:

1. **Write succeeded** differs from **client definitely received acknowledgment**. A timeout can leave the write outcome ambiguous.
2. **Observing the write's effect** differs from **seeing the exact unmodified values**: if another client updates the document afterward, a valid read may observe a newer version.
3. **Reading later in wall-clock time at the application layer** is insufficient to guarantee MongoDB knows the two operations are causally related, especially when sent across two separate sessions or nodes.

### 1.1. Why is reading an old version a business problem?

Real-world examples:

- **Order creation:** POST succeeds, yet the order history screen returns a list missing the new order.
- **Address update:** user saves a new address, and the next page still displays the old address.
- **Password or permission change:** the security change was written, yet a request reading a secondary sees the prior state.
- **Balance or payment status update:** an API confirms the update, another service immediately reads the stale value and makes the wrong decision.
- **Inventory sync:** a worker updates a reservation, then another worker queries from a node that has not received enough oplog entries yet.

Depending on business needs, a system may **tolerate reading data delayed by a few seconds** or must strictly enforce **read-your-writes**. Thus, configuration choices must stem from consistency, latency, and fault-tolerance requirements.

### 1.2. Four concepts not to equate

| Term | Question it answers |
|---|---|
| Read-your-writes | Once a client wrote X, do causally subsequent reads observe the effect of X? |
| Monotonic reads | Having observed state at point T, can a causally subsequent read revert to an older state? |
| Majority durability | Is a write acknowledged by a configured majority of members protected from standard rollbacks during failover? |
| Linearizable read | Does a single-document read reflect majority writes completed before the read began in real-time order? |

Read-your-writes belongs to causal guarantees. Linearizability is a stronger consistency model for operations within its supported scope, carrying extra conditions and costs. Reading from the primary can facilitate read-your-writes without automatically making every read in every situation linearizable.

## 2. Replica sets: the source of reads lagging behind writes

In a standard replica set, the application writes to the **primary**. The primary records the operation, and secondaries replicate changes via the **oplog** and apply them through replication.

~~~text
                         Application
                           |
                       insert X
                           |
                           v
                        PRIMARY
                           |
                   writes X / oplog
                           |
           +---------------+---------------+
           |                               |
           v                               v
       SECONDARY A                     SECONDARY B
    applies X after lag Δ1          applies X after lag Δ2
           |                               |
       sees X?                          sees X?
    depends on timing               depends on timing
~~~

Secondaries do not necessarily apply the same operation **instantaneously**. The gap between primary acknowledgment and secondary application fluctuates with load, network, configuration, and incidents.

### 2.1. Timeline: write to primary then read from secondary too early

~~~text
Time advancing ------------------------------------------------------->

Primary:     write X --> ack write ---> ...

Secondary:   (does not have X) ----------> apply X ---> ...

Client:      POST X --> 200/201
                           |
                           +-- GET from secondary
                               Can it see X yet?
                               Not guaranteed if node lags.
~~~

Even when the GET request is sent **after** the POST response, if GET goes to a secondary that has not caught up, the result may miss record X.

### 2.2. Primary and secondaries have distinct roles

In a normal replica set:

- The **primary** accepts normal writes.
- **Secondaries** replicate and apply changes to serve reads per the configured read preference.
- When the primary fails, the replica set can elect a new primary; during that process, some requests may fail or require retries.

Reading from secondaries can help distribute load for certain workloads, but **you cannot treat load distribution as proof that data is always the freshest**.

### 2.3. Majority acknowledgment does not mean all secondaries have updated

Suppose a replica set has three nodes: primary P, secondaries S1 and S2. With **majority** write concern, an operation can be acknowledged once the configured majority is reached; **it does not wait for every secondary**.

~~~text
P:  has X            |
S1: has X            | => majority met, can acknowledge
S2: does not have X  | => still lagging
~~~

An immediate read from S2 afterward may still miss X unless a mechanism enforces reading at the right causal point. This is why **`w: "majority"` does not automatically keep every secondary caught up at all times**.

## 3. Three configuration knobs affecting read-after-write

Separate **write concern**, **read concern**, and **read preference** into three distinct decisions.

### 3.1. Write concern: when is a write operation acknowledged?

Write concern specifies the acknowledgment level a write command requests.

| Setting | General meaning | Impact on read-back |
|---|---|---|
| w: 1 | Primary acknowledges per applicable write policy | Immediately reading from the same primary usually sees the completed write, but carries rollback risk across failover |
| w: "majority" | Write satisfies majority acknowledgment per replica set config | Aligns with durability/causal consistency guarantees when paired with majority read concern |
| w: 0 | Does not wait for write acknowledgment at this level | Cannot assume the operation succeeded merely because the client sent it |
| wtimeout | Limits wait time for write concern | On timeout, must distinguish actual write state; never assume rollback |

Example:

~~~javascript
db.profiles.insertOne(
  {
    _id: "P-101",
    displayName: "Bình",
    version: 1
  },
  {
    writeConcern: { w: "majority", wtimeout: 10000 }
  }
);
~~~

The command requests majority acknowledgment with a corresponding wait limit. **If a `writeConcernError` or network disconnect occurs, the write effect may already have happened.** The application must reconcile by business key rather than treating failure as "not written."

**`w: "majority"` does not mean data can never be lost in catastrophic failures outside the assumed model.** Review replica set configuration, default write levels, storage, backups, and operational procedures.

### 3.2. Read concern: which version level of data can be read?

| Read concern | Core characteristics | Key point for RYW |
|---|---|---|
| local | Reads data present on the serving node, potentially including non-majority-committed changes | Primary reads usually see just-applied writes, but provide no rollback protection |
| majority | Reads data majority-committed per server rules | May still trail the causal point of an earlier write without a causal session |
| linearizable | Supports real-time properties for qualifying single-document reads on primary | Requires specific conditions, may wait; does not replace multi-document transactions |
| snapshot | Reads from a consistent snapshot within supported feature/transaction scope | Suits consistent multi-record views; does not automatically see external non-transactional changes |
| available | Suitable for specific supported cases; may read non-majority-committed data | Not a choice for guaranteeing durable RYW |

**Read concern `"majority"` does not automatically turn every read into "the absolute latest data."** It governs the majority-committed state a node can serve. If reading from a lagging secondary, you need a mechanism carrying the causal milestone from write to read so the read does not precede that write.

### 3.3. Read preference: which node does the read connection route to?

| Read preference | Meaning | Impact on read-back |
|---|---|---|
| primary | Reads from primary | Fits many flows needing immediate visibility of writes accepted by the primary |
| primaryPreferred | Prefers primary, can read secondary if primary unavailable | Must account for switching to a secondary |
| secondary | Reads from secondary | Can encounter replication lag; needs causal session for durable RYW |
| secondaryPreferred | Prefers secondary, can fall back to primary | Data freshness depends on serving node and read policy |
| nearest | Selects node by latency per driver selection rules | Nearest node is not necessarily the freshest node |

**Read preference only decides read routing**; it does not make secondaries sync instantaneously, does not alter write concern, and does not create causal ordering by itself.

### 3.4. Distinguishing "written" from "majority-committed"

`w: 1` example:

~~~text
Primary:   writes X --> ACK
Secondary: has not replicated X
Primary:   fails before X is majority-committed
Election:  new node without X becomes primary
~~~

Under conditions permitting rollback, X may disappear after failover. A read from the old primary before failure might have observed X, yet that **does not prove X survived across a primary change**.

If the application needs "write, read back, and remain intact after failover," evaluate **majority write concern** and appropriate read requirements rather than relying on a single successful `local` read.

## 4. Which conditions actually guarantee read-your-writes?

You cannot answer with a blanket "always enable majority" or "just use primary." You must define **where reads go**, **how writes are acknowledged**, **whether causality is preserved**, and **how far business guarantees must extend**.

### 4.1. Simple case: same primary, read after successful write

In a normally operating replica set:

~~~text
Write to primary
  -> primary acknowledges success
  -> read back from the same primary afterward
  -> normally observes the write effect
~~~

Example:

~~~javascript
db.orders.insertOne(
  { _id: "O-001", state: "CREATED" },
  { writeConcern: { w: 1 } }
);

db.orders.findOne({ _id: "O-001" });
~~~

If the insert succeeds and the subsequent read executes on the **same unchanged primary**, with no competing delete/update prior to the read, a `local` read normally observes the newly written document.

However, this configuration **is not a durable end-to-end guarantee across all failovers**. `w: 1` can be acknowledged before the write replicates to a majority. If the primary changes and the write rolls back, post-failover results can differ.

Moreover, if the read is routed to a secondary via middleware or a different read preference, you cannot apply "the primary had the write" directly to the reading node.

### 4.2. Case requiring secondary reads while preserving causality

MongoDB supports **causally consistent client sessions**. When a client executes operations **sequentially within the same session**, the session carries the causal timestamp milestone from write to read.

To achieve causal guarantees such as read-your-writes per MongoDB documentation, combine:

1. **Causally consistent session** enabled.
2. Related operations executed **within the same session** or validly forwarding causal metadata.
3. **Write commands using write concern `"majority"`**.
4. **Read commands using read concern `"majority"`**.
5. Operations executed **in causal order**, never concurrently executing multiple operations on the same session.
6. Replica set/sharded deployment, driver, and server versions **supporting the corresponding session mechanism**.

When these conditions are met, the subsequent read carries the requirement not to read from a point prior to the acknowledged write in that session.

### 4.3. Comparison table of scenarios

| Scenario | Read-back expectation | Limitations to remember |
|---|---|---|
| w:1, local read from same primary after ACK | Usually sees newly applied write | May roll back on failover; does not apply if reading secondary |
| w:majority, primary read after ACK | Suits flows needing to see majority-committed writes | Must still handle failover, network errors, concurrent updates |
| w:majority, secondary local read without session | May not see write immediately | Secondary may lag |
| w:majority, secondary majority read without causal session | Does not guarantee seeing the exact just-acknowledged write point | Majority snapshot on secondary may still lag behind |
| w:majority + readConcern majority + causal session, secondary read | Guarantees RYW within session semantics when sequential | Read may have to wait for secondary to catch up or time out |
| w:1 + readConcern majority + causal session | Does not fully satisfy majority write premise for causal guarantees | Write risks rollback; not fixed by session alone |
| Write inside transaction not yet committed, read outside transaction | Not permitted to see uncommitted writes | External reads do not observe uncommitted writes |
| Write and read inside the same transaction | Can read changes made by that same transaction within transaction semantics | Does not mean transaction committed or is visible to other clients |
| Linearizable read from primary paired with proper majority write | Strong real-time guarantee for supported operations | May wait/fail during quorum issues; does not apply uniformly to all operations |

This table is a map of choices; **not every read carries the same guarantee**, and "enabling majority on one side" does not solve everything automatically.

### 4.4. A quick decision flowchart

~~~text
Application just wrote a document and must read it back
                      |
                      v
           Tolerates delayed reads?
                 /          \
               Yes           No
               |              |
      Can use eventual         v
      secondary reads      Read from primary?
      + retry/polling         /         \
                            Yes          No
                            |             |
                  Consider w majority      v
                  + primary read      Read from secondary
                            |             |
                            |        Causal session
                            |        + majority write
                            |        + majority read
                            |             |
                            +------+------+
                                   |
                                   v
                            Handle failover,
                            timeout, retry,
                            concurrent mutations
~~~

If the requirement goes beyond RYW to **real-time ordering consistently observed across multiple clients** on a single document, study read concern **linearizable** and its specific conditions/costs. If multiple documents must be seen simultaneously under one snapshot, study transactions and read concern **snapshot**.

## 5. How does a causally consistent session work?

A session supporting causal consistency lets the MongoDB Driver attach logical progress metadata to operations. Markers such as **`operationTime`** and **`clusterTime`** support causal ordering; the server can use **`afterClusterTime`** in read concern to avoid returning a snapshot earlier than the known milestone.

Visualize it:

~~~text
Client session S

1. INSERT X on primary, w:majority
               |
               v
        Server acknowledges success
               |
               v
        Session S records milestone T
               |
               v
2. FIND X on secondary, readConcern:majority
   + requires causal milestone >= T
               |
        +------+------+
        |             |
 Secondary has     Secondary has not
 reached T         reached T
        |             |
        v             v
    Return result   Wait to catch up or
                    timeout/error
~~~

The key point is that **the session propagates causal information**, not that the session forces secondary replication to happen instantaneously.

### 5.1. Reads may wait, not "guaranteed to return immediately"

If the selected secondary lags, a causal read needs a snapshot reaching the requested logical time. It may:

- Wait for the node to apply necessary changes.
- Succeed once the node catches up.
- Fail with an error due to timeout, disconnect, unavailable node, or other operational limits.

Therefore, a consistency guarantee is a **guarantee on data version when a read succeeds**, not a promise to always finish within one millisecond.

Configure appropriate timeouts and retry policies; avoid unbounded waits when the system is degraded.

### 5.2. Same `MongoClient` does not mean same causal session

Example:

~~~text
POST request -> MongoClient A, session S1 -> writes X
GET request  -> MongoClient A, session S2 -> reads X
~~~

Two requests sharing one **`MongoClient`** or connection pool do not automatically belong to **the same causally consistent session**. A session is a distinct logical context with its own lifecycle and logical timestamps.

If the backend creates a new session per HTTP request, causality **does not automatically transfer between requests** merely because they share a process or user.

### 5.3. Never use one session concurrently across multiple threads

A session in the MongoDB Driver is not considered safe for arbitrary parallel execution of multiple operations. In a causal flow, execute operations sequentially:

~~~text
write -> await success -> read -> await result
~~~

Do not turn it into:

~~~text
start write
start read before write has returned a result
~~~

when write-before-read causality is desired. If two operations run concurrently, there is no basis to require the read to observe a write not yet acknowledged and whose causal milestone is not yet recorded.

### 5.4. Why must majority read and majority write go together?

Read concern majority enforces reading only majority-committed data, while write concern majority enforces write acknowledgment durability. Causal sessions link operation order within supported guarantee boundaries.

If you change only read concern to majority while writing with `w:1`, writes may lack quorum durability. If you write with majority but read secondary majority without a causal milestone, the reading node may not have reached the write's point yet. If you enable a session while commands omit required concerns, you cannot assume **the full causal consistency guarantees stated**.

## 6. Scope of guarantees: session, request, and multiple services

In a single program keeping one session alive across write and read, design is straightforward. In web/microservice architectures, two calls may hit two different instances:

~~~text
Client
   |
   +-- POST /orders ---> service A ---> MongoDB primary
   |
   +-- GET /orders  ---> service B ---> MongoDB secondary
~~~

Here, service B may not know **service A's causal timestamp milestone**. Common solutions based on requirements include:

1. **Route immediate post-write reads to the primary**, paired with write concern matching desired durability.
2. **Keep the workflow inside one service/session** for parts needing read-your-writes.
3. **Propagate causal metadata** across services/sessions via supported APIs and security policies, when secondary reads with preserved causality are genuinely needed.
4. **Return the written data in the POST response** so the UI need not immediately issue a GET when a fresh database read is unnecessary.
5. **Intentionally accept eventual consistency**: client polls by `requestId`/version with suitable timeout/backoff if business logic permits.

### 6.1. Returning the POST result is not an automatic "read"

If an API inserts an order and returns the exact object it just submitted:

~~~json
{
  "orderId": "O-100",
  "state": "CREATED"
}
~~~

the client can **display the new data immediately** without waiting for secondaries. However, this does not prove an independent GET reading from a secondary already sees the order. Distinguish **UI displaying command results** from **database read-your-writes**.

### 6.2. Causal tokens across different sessions

At the driver layer, APIs exist for **`clusterTime`/`operationTime`** and advancing a new session to a known milestone, depending on the driver. This technique requires understanding security models and metadata formats; never invent an application timestamp and expect MongoDB to treat it as a valid causal milestone.

When forwarding milestones across services, verify:

- The milestone comes from **an actual server-acknowledged operation**, not client `Date.now()`.
- The new session **advances** causal info using supported APIs.
- Read concern, write concern, and permissions are properly configured.
- Internal sensitive metadata is never leaked, nor are external clients allowed to supply arbitrary milestones.
- Timeout/retry handling exists if reading nodes lag behind.

In many systems, **primary reads after majority writes** or **keeping write-read logic in one service** is simpler than forwarding causal metadata across layers. Add complexity only when load distribution benefits and consistency needs justify it.

### 6.3. Do not confuse read-your-writes with "read-your-transaction"

Inside a transaction, operations within the same transaction see changes written by that transaction before external commit. That is **transaction visibility rules**. Read-your-writes **after commit across sessions/nodes** depends on commit behavior, read concern, and causal order.

Do not observe a `find` inside a transaction seeing a document and conclude every secondary read outside the transaction immediately sees that document.

## 7. Practicing on a replica set with `mongosh`

Guarantees involving **primary/secondary, majority, and causal sessions** require a deployment supporting replication. A standalone MongoDB instance does not allow observing secondary lag or replica set failover.

Connect to a **test replica set** or eligible MongoDB cluster using `mongosh`. Never shut down a primary, block replication, or modify production read/write concerns for exercises.

### 7.1. Checking the environment

In `mongosh`:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

For a replica set, the response may include fields like **`setName`**, **`isWritablePrimary`**, **`secondary`**, and the host list, depending on node and settings. Never paste full outputs containing internal addresses into public shared documents.

With appropriate privileges:

~~~javascript
rs.status();
~~~

This command helps inspect members and replication status. In managed services or unprivileged accounts, it may be restricted. In that case, verify topology via authorized management tools rather than escalating permissions just for exercises.

### 7.2. Creating a test collection and unique key

~~~javascript
use ryw_lab

db.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_ryw_requestId" }
);
~~~

Suppose each exercise order creation uses a distinct `requestId`, e.g., **R-240-001**.

~~~javascript
db.orders.insertOne(
  {
    _id: "O-240-001",
    requestId: "R-240-001",
    state: "CREATED",
    version: 1,
    updatedAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

After the insert is acknowledged, read from primary:

~~~javascript
db.orders.findOne({ _id: "O-240-001" });
~~~

If the same connection routes reads to the primary with no competing writes, the result contains the newly created document. This is an easily observable example of read-after-write on the primary under normal conditions.

### 7.3. Observing read concern majority in a command

You can run `find` as a database command with explicit `readConcern`:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-240-001" },
  readConcern: { level: "majority" }
});
~~~

The output typically contains **`cursor.firstBatch`** and corresponding metadata. This lets you observe a read with read concern majority **on whichever node the command is routed to**. It is **not an experiment proving secondaries caught up** if the command still ran on the primary.

### 7.4. Creating an explicit causal session

In `mongosh`, a session can be obtained from the Mongo connection:

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

const sdb = session.getDatabase("ryw_lab");

try {
  const writeResult = sdb.runCommand({
    insert: "orders",
    documents: [
      {
        _id: "O-240-SESSION",
        requestId: "R-240-SESSION",
        state: "CREATED",
        version: 1,
        updatedAt: new Date()
      }
    ],
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  });

  printjson(writeResult);

  if (writeResult.ok !== 1 || writeResult.n !== 1) {
    throw new Error("Write was not confirmed; do not assume success");
  }

  const readResult = sdb.runCommand({
    find: "orders",
    filter: { _id: "O-240-SESSION" },
    readConcern: { level: "majority" }
  });

  printjson(readResult.cursor.firstBatch);
} finally {
  session.endSession();
}
~~~

This example illustrates **write → read ordering on the same explicit session**, with majority write and majority read. In application code, also handle `writeConcern` errors, exceptions, timeouts, and rollback conditions rather than checking only the `ok` field in a command result.

The read in this snippet **did not yet request a secondary**: to test reading from secondaries within a client session, use the driver API configuring **`readPreference: secondary`**, as in the Java example next. Do not assume adding read concern majority automatically shifts read routing to secondaries.

**If re-running**, the existing `_id`/`requestId` pair will fail the insert due to the unique key. Use a fresh test ID instead of unintentionally deleting data.

### 7.5. An intentional eventual consistency test

To see the impact of secondary lag, you can use two differently configured connections:

- Write connection: routed to primary.
- Read connection: read preference `secondary`.

Right after a newly acknowledged write, try reading via the secondary connection **without a causal milestone**. Depending on environment and timing, the read may see the document immediately or miss it. **You cannot guarantee reproducing staleness with a few documents** if secondaries sync quickly.

Never induce lag by disrupting replication on a shared cluster. To test enforced causal reads, use explicit sessions and driver configuration as in the Java section.

## 8. Java Sync Driver: guaranteeing read-after-write on secondaries

For code that needs to **write on the primary then read from a secondary with causal ordering**, the MongoDB Java Sync Driver allows:

1. Creating a **`ClientSession`** with **`causallyConsistent(true)`**.
2. Writing via a collection with **`WriteConcern.MAJORITY`**.
3. Reading via a collection with **`ReadConcern.MAJORITY`**.
4. Selecting **`ReadPreference.secondary()`** if intentionally targeting a secondary.
5. Passing the **same `ClientSession`** to both `insertOne` and `find`.
6. Waiting for the write result before starting the read.

### 8.1. Complete Java example

Example for a project with a compatible **`mongodb-driver-sync`** dependency, **`MONGODB_URI`** environment variable pointing to a replica set with readable secondaries, and appropriate permissions:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.Date;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class ReadYourWritesDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        String id = "O-" + UUID.randomUUID();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession(
                     ClientSessionOptions.builder()
                             .causallyConsistent(true)
                             .build())) {

            MongoDatabase database = client.getDatabase("ryw_lab");
            MongoCollection<Document> orders =
                    database.getCollection("orders");

            MongoCollection<Document> writer = orders
                    .withWriteConcern(WriteConcern.MAJORITY);

            MongoCollection<Document> secondaryReader = orders
                    .withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.secondary());

            Document order = new Document("_id", id)
                    .append("requestId", id)
                    .append("state", "CREATED")
                    .append("version", 1)
                    .append("updatedAt", new Date());

            // Write on primary, wait for majority acknowledgment.
            writer.insertOne(session, order);

            // Same session propagates causal dependency to the read.
            // If secondary has not caught up, read may wait/fail.
            Document seen = secondaryReader
                    .find(session, Filters.eq("_id", id))
                    .maxTime(10, TimeUnit.SECONDS)
                    .first();

            if (seen == null) {
                throw new IllegalStateException(
                        "Order not found after acknowledged write: " + id);
            }

            System.out.println(seen.toJson());
        }
    }
}
~~~

**Important points in the code:**

- **`ClientSessionOptions.causallyConsistent(true)`** explicitly expresses intent to preserve causal ordering.
- **`writer.insertOne(session, order)`** and **`secondaryReader.find(session, ...)`** share the same session.
- **`WriteConcern.MAJORITY`** and **`ReadConcern.MAJORITY`** provide the required concern levels for causal guarantees.
- **`ReadPreference.secondary()`** forces reading from a secondary; if no eligible secondary exists, the operation fails rather than silently switching to primary.
- **`maxTime(10, TimeUnit.SECONDS)`** caps server execution time per MongoDB rules; it is not a guarantee that total network time never exceeds 10 seconds.
- **`ClientSession`** and **`MongoClient`** are closed upon completion in this CLI program.

In multi-request web applications, **`MongoClient` is typically reused long-term**, not created/closed per HTTP request. Meanwhile, sessions should be created, used sequentially, and closed along appropriate **business boundaries**.

### 8.2. If you want to prefer secondaries while allowing primary fallback

Replace:

~~~java
ReadPreference.secondary()
~~~

with:

~~~java
ReadPreference.secondaryPreferred()
~~~

When an eligible secondary exists, the driver reads from a secondary; if none exists, it can fall back to the primary per read preference. Therefore, never assert a request definitely went to a secondary solely because code specifies **`secondaryPreferred`**. To verify which node was picked, use command monitoring or appropriate observability tools.

### 8.3. If reading only from the primary

You can configure:

~~~java
MongoCollection<Document> primaryReader = orders
        .withReadPreference(ReadPreference.primary())
        .withReadConcern(ReadConcern.MAJORITY);
~~~

After a majority-acknowledged write on the primary, this is often a simpler design for immediate read-after-write APIs. Depending on contract, you can still retain a causal session so ordering remains explicit and consistent in the processing flow.

### 8.4. If a write encounters a timeout or `writeConcernError`

Never jump straight to:

~~~java
// Flawed logic assumption example:
// If insertOne throws a network error -> generate a new id and re-insert.
~~~

Because the outcome of the first write may be indeterminate. For resource-creation operations, use a **stable `requestId`/idempotency key**, unique indexes, and bounded reconciliation or retry procedures. Otherwise, the client may create duplicate resources simply because the first write succeeded while its response dropped.

Re-reading with a causal session after a **write not yet acknowledged as successful** does not create proof that the write reached majority. First verify write status or execute safe retries per business contract.

## 9. Spring Data MongoDB: passing sessions through the data access layer

In a Spring Boot application using Spring Data MongoDB, **`MongoTemplate`** or repositories handle CRUD operations. However, simply injecting the same `MongoTemplate` bean does not ensure two independent requests share a causal session.

### 9.1. A pattern for accessing data within the same session

Spring Data MongoDB offers an API creating a **`MongoOperations`** context bound to a `ClientSession`:

~~~java
import com.mongodb.client.ClientSession;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderService {
    private final MongoTemplate mongoTemplate;

    public OrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document insertThenRead(
            ClientSession session,
            Document order) {

        MongoOperations operations =
                mongoTemplate.withSession(session);

        operations.insert(order, "orders");

        return operations.findById(
                order.getString("_id"),
                Document.class,
                "orders"
        );
    }
}
~~~

In this example:

- **`withSession(session)`** binds operations on the `MongoOperations` context to the passed session.
- The caller must ensure the session remains valid and operations execute sequentially.
- **No majority concerns are configured in this snippet**: achieving causal guarantees requires configuring majority write/read concerns for the actual operations, suited to your environment and Spring Data version.
- **`findById`** on primary is typically the simple case; to read secondaries within the same session, configure the proper read preference and verify actual operations use the intended concerns.

Do not treat this snippet as guaranteeing durable RYW automatically if `MongoTemplate` or the driver is using unsuitable default concerns.

### 9.2. Who creates and closes `ClientSession`?

Typically a session is scoped to **a single unit of work**, not held permanently in a singleton Spring bean:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

public class SessionBoundary {
    private final MongoClient client;
    private final OrderService orderService;

    public SessionBoundary(
            MongoClient client,
            OrderService orderService) {
        this.client = client;
        this.orderService = orderService;
    }

    public void processOrder() {
        ClientSessionOptions options = ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

        try (ClientSession session = client.startSession(options)) {
            // Ensure majority read/write concerns are configured
            // on actual operations here when causal RYW is needed.
            orderService.insertThenRead(
                    session,
                    new org.bson.Document("_id", "O-SPRING-240")
                            .append("state", "CREATED")
            );
        }
    }
}
~~~

The code illustrates session boundaries. Re-running with the same `_id` using `insert` triggers a duplicate key error on the second run; real APIs should use stable business request keys and appropriate idempotency workflows.

### 9.3. Repositories do not carry sessions across HTTP automatically

Suppose:

~~~text
POST /orders -> OrderRepository.save(...)
GET /orders  -> OrderRepository.findById(...)
~~~

Two repository calls may execute in two different HTTP requests, threads, and application instances. Never assume end-to-end causal consistency simply because they call the same repository interface.

For critical flows, explicitly choose one of these paths:

- **`primary` read preference** for queries needing visibility of recent writes.
- **Transactions or explicitly managed sessions** for a single unit of work.
- **Validly propagated causal tokens** when connecting two requests across services.
- **Polling/reconciliation by version or `requestId`** when delayed synchronization is acceptable.

Solution selection depends on Spring Data configuration, MongoDB Driver, and topology—not just repository method names.

## 10. Read-your-writes inside MongoDB transactions

MongoDB supports **multi-document transactions** in qualifying deployments. When a transaction writes a document and then reads that same document **inside the same transaction**, the read observes the transaction's own uncommitted writes.

Java Sync Driver example:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class TransactionReadOwnWrite {
    public static void createAndRead(
            ClientSession session,
            MongoCollection<Document> orders,
            String orderId) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        session.startTransaction(options);
        try {
            orders.insertOne(session,
                    new Document("_id", orderId)
                            .append("state", "CREATED"));

            Document ownWrite = orders.find(
                    session, Filters.eq("_id", orderId)).first();

            if (ownWrite == null) {
                throw new IllegalStateException(
                        "Missing own write inside transaction");
            }

            session.commitTransaction();
        } catch (RuntimeException ex) {
            if (session.hasActiveTransaction()) {
                session.abortTransaction();
            }
            throw ex;
        }
    }
}
~~~

This example demonstrates **reading the transaction's own writes**; pass an initialized `ClientSession` and `MongoCollection`. In real applications, transactions can encounter **`TransientTransactionError`** or **`UnknownTransactionCommitResult`** and require retries per error-label policies. Never place external HTTP side effects inside a retryable transaction callback.

### 10.1. Do other clients see the document before commit?

No. Another transaction or a read outside the transaction does not see uncommitted writes of this transaction.

~~~text
Transaction A                      Client B
   |
   +-- insert X
   +-- find X -> sees X
   |                                  find X -> does not have X yet
   +-- commit
                                      |
                                      +-- after commit:
                                          visibility depends on
                                          which node is read,
                                          read concern, causal order
~~~

A seeing X inside its transaction **does not allow B to read it before A commits**. And right after commit, a secondary read without causal ordering may still miss the change if that node has not caught up.

### 10.2. Read concern `snapshot` differs from `linearizable`

Read concern **`snapshot`** enables reading a consistent snapshot within a transaction or supported contexts. It does not make every query linearizable in real time. Within a snapshot transaction, changes committed by other clients after the snapshot timestamp may not appear in that transaction's reads.

If the goal is "write multiple documents and read all of them consistently," transactions fit well. If the goal is "one client just wrote a single document and another client must read the newest result immediately in real time," examine read concern `linearizable` or primary routing and related conditions.

### 10.3. Where does commit majority matter?

Writing multiple documents inside a transaction does not mean all documents are majority-committed merely because `insert` executed. Distinguish **operations inside the transaction**, **commit**, and **the commit's write concern**.

Once a transaction commits successfully with majority write concern, the application has a stronger foundation for subsequent steps reading committed changes. If commit returns a network error with unknown outcome, never blindly re-run the whole workflow with a new ID; retry commit/reconcile per driver mechanics and business keys.

## 11. Linearizable read: when is a stronger level required?

Sometimes the requirement is not merely **a client seeing its own writes**, but **any client reading a document must respect the completion order of previously majority-acknowledged writes**.

Read concern **`linearizable`** can support that requirement for **qualifying read operations on the primary**, under MongoDB-supported conditions. It is typically paired with **majority write concern** to achieve the desired real-time guarantee.

### 11.1. Example reading a single document with a known `_id`

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-240-001" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 10000
});
~~~

This is a single-document query on the primary using linearizable read concern appropriately. **Never select `readPreference: secondary` for linearizable reads**. Verify server version, supported operation types, and permissions in your actual deployment.

### 11.2. Why can linearizable reads be slow or fail?

To verify it is not reading from a stale primary that lost its ability to commit per replica set rules, MongoDB may need to communicate with other members during execution. When quorum is lost, networks partition, or elections occur, linearizable reads can wait up to their time limit or return an error.

**Consistency can trade off latency and availability.** If the application only needs to read its own writes within a session, causal majority or primary reads are simpler and cheaper than forcing linearizable on all reads.

### 11.3. Do not apply linearizable to arbitrary complex queries

This level is not a universal switch turning arbitrary aggregations, multi-document queries, and transactions into a global real-time snapshot. It has a specific supported scope, typically tied to reads identifying a single document. When needing multi-document consistency, use transactions/snapshots; when needing causal ordering, use causal sessions.

### 11.4. Comparing three typical options

| Need | Commonly considered approach |
|---|---|
POST a document then GET immediately from primary | Write with appropriate concern; read primary after ACK |
Write then read from secondary in the same business flow | Causal session, majority write + majority read, sequential |
Read a single document reflecting prior majority writes in real time | Linearizable read on primary under supported conditions |
Write and read multiple documents in a transaction | Transaction with read concern snapshot and proper commit concern |
Analytics screens tolerating staleness | Secondary read/eventual consistency with lag monitoring |

Key point: do not blindly use stronger consistency than needed, yet never trade business correctness for read speed when data drives critical decisions.

## 12. Failover, retries, and unknown write outcomes

In distributed systems, failures occur at multiple points. Read-back guarantees depend on **whether the write actually completed** and **whether the client holds a reliable causal milestone**.

### 12.1. Write succeeds, but response is lost

~~~text
Client                     Primary                     Secondary
  |                           |                            |
  |--- insert order O-900 --->|                            |
  |                           |---- replicate ----------->|
  |                           |<---- majority ack ---------|
  |<----------- X ------------|                            |
       Response lost
~~~

The client does not know the write succeeded, even though the server may have committed it to a majority. If the client generates **a new random `orderId`** and resends, the system may create a second order.

**Read-your-writes assumes you already have an acknowledged write under required conditions.** When a write yields an ambiguous outcome, the first step is **safely verifying or re-executing the business intent**, never assuming the write does not exist.

A protective pattern:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

If the client sends a stable `clientRequestId`, the backend can read by key to reconcile. Even if data is missing on a secondary, do not conclude the request was never processed; read from a source with appropriate consistency guarantees or retry under a safe policy.

### 12.2. Retryable writes differ from causal consistency

MongoDB Drivers support **retryable writes** for certain operations on eligible deployments. This mechanism helps re-execute write commands upon transient errors within driver context.

**Causal consistency** solves a different problem: once a write is acknowledged and its causal milestone is recorded, subsequent reads in the session must not revert prior to that milestone under the majority conditions described.

| Mechanism | Solves |
|---|---|
| Retryable writes | Automatically retrying eligible write commands on network/failover errors |
| Causal session | Causal ordering of linked operations |
| Majority write concern | Durable acknowledgment level for writes |
| Majority read concern | Visibility of majority-committed data |
| Unique `requestId`/idempotency | Preventing duplicate business effects when HTTP/messages repeat |

They complement each other; they are not different names for the same feature.

### 12.3. When `wtimeout` occurs

With:

~~~javascript
{
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
}
~~~

If waiting for majority exceeds the limit, the client may receive a **write concern timeout/error**. This does not mean the write was definitely canceled on the primary or never applied. Nor does it prove the write reached majority at the moment the client received the error.

To recover:

1. Keep the same **`requestId`** or business key.
2. Classify network errors, write concern errors, and business errors.
3. Retry **idempotently** or query state from an appropriate read source.
4. If state remains ambiguous, record **UNKNOWN/NEEDS_RECONCILIATION** instead of declaring success or generating a new operation.

Never write **`catch any exception → insert with a new _id`**.

### 12.4. Failover between write and read

If a write was acknowledged with **`w: 1`**, the primary may fail before the write is durably replicated. A new primary lacking that effect may be elected under rollback-eligible conditions.

If the write was majority-acknowledged under normal replica set conditions, rollback risk for committed writes is greatly reduced per replication guarantees. Yet applications must still handle **elections, retries, session timeouts, and read routing**.

Do not confuse **durability** with **availability**: durable data does not mean every read during failover returns instantaneously without error.

### 12.5. The new primary is not necessarily ready instantaneously

During an election, drivers may encounter server selection errors or fail to locate a primary under read preference for a brief window. A failed read is not proof that the document vanished. Retry with bounded backoff, time limits, and proper error classification.

If a read cannot be served at the required consistency level, the system should **return an error or bounded wait per policy** rather than silently falling back to a stale secondary when business rules forbid it.

## 13. A GET can read from a cache outside MongoDB

Even when MongoDB is properly configured, an application may still display old data if GET never queries MongoDB directly:

~~~text
POST /profile
   |
   v
MongoDB: displayName = "B"

GET /profile
   |
   v
Redis / in-memory cache / HTTP CDN
   |
   v
displayName = "A"
~~~

MongoDB causal consistency **does not control data in Redis, HTTP caches, CDNs, or browser caches**. To achieve end-to-end API read-your-writes, you must also govern read paths outside MongoDB.

### 13.1. Common strategies

- **Cache invalidation on write:** delete or update the related entry upon contract-compliant write success.
- **Write-through or write-behind with clear rules:** understand when cache and database align, especially during failures.
- **Versioned cache:** attach versions to documents and only serve cache entries meeting the version milestone the client already saw.
- **Read-after-write bypass:** route requests right after writes directly to the authoritative source for a window or until the new version appears.
- **Optimistic UI:** render the confirmed write result and sync afterward; if GET may be stale, handle it gracefully in the UI.

No strategy is free. Cache invalidation can race; write-behind adds delay; bypass increases primary load. Choose according to product consistency needs.

### 13.2. Cache invalidation can race too

Example:

~~~text
Worker A: GET old version from DB
Worker B: UPDATE new version, invalidate cache
Worker A: stores old version into cache after invalidation
~~~

As a result, the cache again holds stale data. Simply issuing a cache delete after an update is not always sufficient under heavy concurrency.

Solutions can include **versioning, compare-and-set, appropriate TTLs, or cache sync mechanisms**; evaluate the semantics of each cache/store. Do not claim MongoDB violated RYW when GET actually served an outdated entry from an application cache.

### 13.3. Critical diagnostic question

When updating and then seeing stale data on GET, determine **where GET actually fetched from**:

1. MongoDB primary?
2. MongoDB secondary?
3. Service cache?
4. CDN/HTTP cache?
5. Unupdated browser or frontend state?
6. An asynchronously synced search index or read model?

Remediation differs completely depending on the answer.

## 14. Is reading secondaries with `maxStalenessSeconds` enough?

MongoDB Drivers provide **`maxStalenessSeconds`** in certain read preferences to exclude secondaries estimated to lag behind an upper bound.

Usage model:

~~~text
Read preference: secondary/secondaryPreferred
Max staleness: limits selected node lag per driver criteria
~~~

**Max staleness does not guarantee read-your-writes.** Even if a node is considered only a few seconds behind, a write from one millisecond ago may not yet be applied on that node.

### 14.1. Comparing the two mechanisms

| Mechanism | Question it answers |
|---|---|
| maxStalenessSeconds | Should this secondary be chosen if it appears too far behind reference nodes? |
| Causal session with afterClusterTime | Is this read permitted to return a snapshot prior to the known write milestone in this session? |

Max staleness is a **node selection policy**, not proof that a node has applied the exact write a client just executed. Use it to avoid excessively lagging secondaries for eventual-consistency workloads, never as a substitute for causal consistency.

### 14.2. Reading near users does not mean reading the freshest data

Read preference **`nearest`** selects nodes based on network latency and driver selection rules. A node in a region close to the application may replicate slower than a distant node.

If the goal is **fast responses that tolerate slight staleness**, `nearest`/`secondary` are candidates to evaluate. If the goal is **immediate visibility after writing**, add data-timestamp guarantees rather than merely optimizing network latency.

## 15. Using version numbers to check "saw the new record" requirements

In some applications, rather than merely checking document existence, you need to ensure values reached **at least version N**.

Example:

~~~javascript
{
  _id: "PROFILE-1",
  displayName: "B",
  version: 12,
  updatedAt: ISODate("2026-11-14T10:30:00Z")
}
~~~

After successfully updating to version 12, a GET may return version 11 from a secondary/cache. If the client knows it observed version 12 in the POST response, it can recognize version 11 as **stale relative to its own progress**.

### 15.1. Conditional update to increment version

~~~javascript
db.profiles.updateOne(
  { _id: "PROFILE-1", version: 11 },
  {
    $set: {
      displayName: "B",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

If `matchedCount = 1`, the update matched the expected version and incremented it to 12. If `matchedCount = 0`, the document changed or does not exist; the application must handle **optimistic concurrency conflict** rather than blindly overwriting.

### 15.2. Versioning detects staleness, but does not fix it automatically

If GET returns version 11, the client can:

- Re-read from the primary.
- Retry secondary reads with bounded backoff.
- Wait for a read model/cache sync to finish.
- Display a "syncing" status if the product permits.

However, a version number **does not make secondaries apply the oplog faster**. When causal guarantees are required at the database tier, use properly configured causal sessions rather than passing a version number and hoping any node has the latest copy.

### 15.3. Versioning does not replace access control

If a response carries a version yet the client lacks permission to view the document, the backend must still enforce authentication/authorization. Never use a version number or `operationTime` as a guessable or arbitrarily transferable access token.

## 16. Guidance when an application has diverse query types

A single product often needs **multiple consistency levels** per workflow, not a single application-wide `readPreference`:

| Read type | Level to consider | Rationale |
|---|---|---|
GET immediately after order creation in checkout | Primary read and majority write; or proper causal session | Avoid showing "order not found" right after success |
Personal profile editing UI | User RYW, version verification or causal read | Users expect to see the field they just edited |
System-wide revenue stats refreshed per minute | Can read secondaries, tolerating defined lag | Prioritizes load distribution and throughput |
Authorization/security decisions on latest state | Consistency/controls matching risk level | Stale state reads can cause wrong decisions |
Ordered business job queues | Causal sequences and atomic conditional updates | Avoid triggering side effects before seeing required state |
Multi-collection reads in a reporting session | Snapshot/transaction per requirements | Avoid observing different collections at different times |
Activity history needing near real-time only | Secondary/eventual with sync indicators | Can trade freshness to offload primary |

### 16.1. Do not apply strong consistency to all analytics

If a dashboard refreshes every few minutes, demanding linearizable reads per document adds cost and lowers availability without commensurate value. For analytics, delays may also come from **data pipeline lag**, not just replication lag.

### 16.2. Do not rely on eventual consistency for irreversible decisions

If a process reads a balance/status from a secondary to decide **debiting funds, shipping goods, or granting access**, evaluate the risk of stale reads. Single-client RYW alone does not prevent races across multiple clients. You may need:

- Atomic conditional updates and unique business constraints.
- Transactions spanning related resources.
- Reads/writes with appropriate concerns and accurate routing.
- Idempotency keys when requests can be retried.

**RYW does not mean serializability of the entire workflow.** A seeing A's own write does not stop B from concurrently modifying the same document.

## 17. A successful read query can still miss the expected document

Before misdiagnosing consistency, inspect **query conditions and data**:

~~~javascript
db.orders.insertOne({
  _id: "O-CHECK",
  state: "CREATED",
  amountCents: NumberLong("100000")
});

db.orders.findOne({
  _id: "O-CHECK",
  state: "PAID"
});
~~~

Returning `null` is **correct per the filter**, because the document has state `CREATED` rather than `PAID`; it is not evidence of slow replication.

Similarly, if a field is **`ObjectId`** while the query passes a String, or reader and writer target different collections/databases, results will not match even when data sits on the exact same node.

### 17.1. First things to verify

- Do reader and writer target the **same cluster, database, and collection**?
- Do `_id` and compared fields share the exact **BSON type**?
- Does the query include extra filters like **`tenantId`, `isDeleted`, `state`** that exclude the document?
- Does a projection **omit fields**, misleading the application into thinking it was not updated?
- Is there an **uncommitted or aborted** transaction?
- Is GET reading from a cache/read model?
- Did another client modify/delete the document after the writer finished?
- Did an error occur **before or after majority write acknowledgment**?

Only after ruling out these possibilities should you conclude data was "stale read" due to replication or caching.

## 18. Diagnostic procedure for "POST succeeded, yet GET misses it"

An incident report should rely on evidence, not merely on a user seeing an un-updated UI.

### Step 1. Identify timestamps and operation identities

Collect a sample request with:

- **`requestId`/`traceId`** to correlate logs.
- **`_id` or business key** of the created document.
- **Start and end timestamps of the write command**.
- **Write outcome**: acknowledged, write concern, exceptions, error labels if any.
- **Start timestamp of the read** and query outcome.
- **Database/collection/tenant** and key BSON type.

Avoid logging sensitive full payloads unnecessarily. A `requestId` is only a trace identifier, not a replacement for access control.

### Step 2. Verify the write was actually acknowledged

Distinguish:

~~~text
ACK success, w:majority
ACK success, w:1
Write concern timeout
Network error, unknown whether server received command
Transaction commit result unknown
Validation error, document not written
Duplicate key, corresponding document may already exist
~~~

Each case requires a different response. Specifically, **timeout does not equal no data**.

### Step 3. Identify which node served the read

Check **read preference** at every level:

- Connection string.
- `MongoClient`/`MongoDatabase`/`MongoCollection`.
- Per-query overrides.
- Framework repositories/services.
- Proxies/routers and topology.

A configuration thought to be `primary` might be overridden to `secondaryPreferred` at the collection or another routing layer. When reading from a secondary, measure replication lag and check whether a causal session was active.

### Step 4. Verify concerns and sessions

| Question | Where to check |
|---|---|
Did the write use `w:1` or `majority`? | Operation/client/collection `WriteConcern` config |
Did the read use `local` or `majority`? | Operation/client/collection `ReadConcern` |
Did GET use primary or secondary? | `ReadPreference` and driver-selected node |
Did write and read share the same session? | Service session management / driver tracing |
Was `causalConsistency` enabled on the session? | `ClientSessionOptions` |
Was execution truly write-before-read? | Timeline and async/future handling |
Did GET hit a cache? | Cache hit/miss and data source |

Do not log entire raw session tokens in production just to diagnose. Prefer security-compliant metadata and authorized observability tools.

### Step 5. Check replication and topology

In an appropriately privileged environment:

~~~javascript
rs.status();
~~~

Compare node states and replication milestones against actual output. If a secondary is severely behind, read concern `majority` without causal ordering can still observe a snapshot older than the just-acknowledged write.

**Never intentionally induce lag in production** by blocking networks, stopping secondaries, or altering election configs. Fault-injection experiments belong on isolated test clusters.

### Step 6. Compare the exact document across read sources

If authorized, compare results using the exact same filter and BSON types:

~~~javascript
db.orders.findOne({
  _id: "O-240-001"
});
~~~

Across a dedicated primary connection and a dedicated secondary connection. If primary shows version 12 while secondary shows version 11, that is a useful indicator of lag or node/snapshot differences, though you should still verify effective read preferences and timing.

If both primary and secondary show version 12 while the API still returns 11, prioritize investigating **caches or read models outside MongoDB**.

### Step 7. Choose remediation based on root cause

| Observation | Remediation |
|---|---|
Read from lagging secondary, no causal session | Use primary for sensitive reads or configure causal majority session |
Majority read misses write from prior request | Check causal metadata and session boundaries |
`w:1` write rolled back after election | Review majority write concern and retry/idempotency strategy |
Write timed out, unknown outcome | Reconcile via business key; never unconditionally mint a new ID |
Client sends GET before write future finishes | Enforce `await`/sequencing in code |
Transaction not yet committed | Read outside transaction only after commit is confirmed |
Cache serves stale document | Invalidation, versioning, bypass, or fix cache strategy |
Query has wrong type/filter/collection | Fix query/mapping; do not blindly raise concerns |
Secondary takes too long to catch up | Set timeouts, backoff, metrics; consider primary reads |
Document modified concurrently by another client | Use optimistic concurrency/versioning or transactions |

### Step 8. Monitor after changes

Do not verify just one successful request. Track:

- **Rate of GET missing records immediately after ACKed POST**.
- **Rate of responses returning a version lower than the client's expected version**.
- **Replication lag** and count of causal reads waiting/timing out.
- **p95/p99 request latency** after read preference changes.
- **Failover/server selection durations** and related errors.
- **Cache hit rate serving stale versions** or cache bypass counts.
- **Count of `UNKNOWN`/reconciliation requests** from write errors.

These metrics must be instrumented/tracked in your observability system; they do not appear under these exact names natively in MongoDB.

## 19. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
|---|---|---|
"Once insert gets ACK, every secondary sees it immediately" | Secondary replication is asynchronous | Need causal milestone or primary read |
"`w:majority` means every node has the data" | Majority is not all members | Secondaries outside the acknowledging majority can still lag |
"`ReadConcern majority` always returns the newest version" | Majority snapshot is not necessarily the instant of the latest write | Needs causal ordering/`afterClusterTime` when reading secondaries |
"Just enabling `causalConsistency` is enough" | MongoDB causal guarantees require proper concerns and order | Majority writes + majority reads + same sequential causal session |
"Same `MongoClient` means same session" | A client can create many independent sessions | Explicitly pass the same `ClientSession` |
"Same user means two HTTP requests definitely share a causal session" | Requests may hit different services/threads | Needs explicit cross-request design choices |
"`ReadPreference secondaryPreferred` always reads secondaries" | Can fall back to primary | Inspect actual target nodes if needed |
"`ReadPreference nearest` means freshest" | `nearest` is a latency/topology policy | Offers no causal guarantee |
"`maxStalenessSeconds` replaces `afterClusterTime`" | Max staleness only filters relatively slow nodes | Does not replace causal sessions |
"Read concern `linearizable` applies to any aggregation" | Has a specific supported scope | Use eligible operations, primary, majority writes |
"`ReadConcern snapshot` always reads the newest data outside transactions" | Snapshots pin a read point in time | Use transactions/snapshots for their intended purpose |
"`find` inside a transaction sees writes, so other clients see them too" | Uncommitted writes are invisible externally | Must commit; external reads follow their own concerns |
"`w:1` on primary is durable enough across failovers" | Non-majority writes can roll back | Use majority per durability needs |
"Timeout means insert never occurred" | May have written and lost the response | Reconcile/retry idempotently |
"Once writes are majority, GET never times out" | Secondaries waiting to catch up, elections/networks can still error | Use timeouts/backoff and error handling |
"Once a read saw X, the next read must return identical X" | Another client can update the document afterward | RYW protects causal order, not permanent data freeze |
"Seeing stale data means replication bug" | Could be caching, mapping, or wrong filters | Identify the actual read source |
"Returning version in response automatically gives RYW" | Version only detects staleness | Must wait/route to proper source or use causal reads |
"Causal sessions prevent two clients from lost updates" | RYW is not atomic conflict prevention | Use compare-and-set, unique indexes, transactions |
"Enabling majority everywhere has zero cost" | Can impact latency/availability | Choose per required consistency level |

## 20. Complete application scenario

Suppose a system creates an order, and then the user's screen calls GET order. Business requirement:

> Once the API confirms the order was durably created, the user's next read must never report "order does not exist" merely because a secondary is lagging.

A pragmatic implementation:

### 20.1. Write with a stable business key

The client generates `clientRequestId` once per checkout intent, backed by a backend unique index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

The backend inserts the order with majority write concern and returns `orderId` and `version` after acknowledgment.

### 20.2. Choose a read path satisfying RYW

If GET runs in another service without forwarding a causal session:

- Configure **primary reads** for the order detail endpoint needing freshness.
- Or propagate causal metadata and configure appropriate majority read/write if secondaries must be read.
- Or return the created order directly from POST and only GET once read-model sync is signaled, if the contract allows.

Never treat an un-sessioned GET via `secondaryPreferred` as guaranteed to see the order immediately.

### 20.3. When only an eventual read model exists

An API may return:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "orderId": "O-900",
  "state": "INDEXING",
  "message": "Order created; read model is synchronizing"
}
~~~

This is an explicit choice to **accept delayed consistency and communicate it to the client**, not a MongoDB read-model RYW guarantee. An authoritative source of truth and reconciliation handling must exist if synchronization takes too long.

### 20.4. End goal: a contract-consistent API

Correctness is more than one successful `findOne`. The system needs:

- **No duplicate order records** when requests retry.
- **Write confirmation** matching committed durability levels.
- **GET read paths** not accidentally switching to stale nodes/caches when immediate visibility is promised.
- **Clients seeing the right version**, or receiving an explicit "synchronizing" state.
- **Controlled handling of network/failover errors**, never silently creating a second order.

## 21. Practice exercises and scenarios

Exercises use the **`ryw_lab`** database and **`orders`/`profiles`** collections introduced above. To test secondaries, causal sessions, or failovers, use a **test replica set**; on standalone MongoDB, restrict practice to CRUD and logical analysis. Never induce lag, delete data, stop nodes, or change concerns on a production cluster without operational approval.

### Exercise 1. Write then read from the same primary

Suppose `mongosh` connects to the primary and `orders` does not yet have `_id` `O-EX-1`:

~~~javascript
db.orders.insertOne(
  { _id: "O-EX-1", state: "CREATED" },
  { writeConcern: { w: 1 } }
);

db.orders.findOne({ _id: "O-EX-1" });
~~~

**Question:** Assuming the primary does not change, no competing writes occur, and the insert ACK succeeds, what does the read typically return? Can we conclude the write will definitely never roll back across any failover?

**Guidance:** Reading from the same primary typically finds the document. However, a `w:1` ACK does not equal majority replication; one successful read does not prove survival across all failovers.

### Exercise 2. Majority write but secondary read without a session

Replica set has P, S1, and S2. Insert X receives majority acknowledgment after P and S1 have X, while S2 has not applied X yet.

**Questions:**

1. Is an immediate read from S2 guaranteed to see X?
2. If read concern majority is set on S2 without a causal session, is that enough?
3. When can we expect to read X from S2?

**Guidance:** Not guaranteed; S2 may lag behind. Read concern majority does not carry the causal milestone from the write. Once S2 applies X and has an eligible majority snapshot, it can read X; to enforce write-read ordering, use a causal session and proper concerns.

### Exercise 3. Picking the right components of causal RYW

A developer claims:

> Just configure `secondaryPreferred` and `causalConsistency=true`, and by default every read will see the preceding write.

Fill in the missing conditions.

**Suggested answer:**

- Use the **same causal session** or forward valid causal metadata.
- **Majority-acknowledged writes** and majority read concern on reads.
- The write must complete before the read starts.
- Session operations execute sequentially.
- Deployment/driver must support sessions.
- If secondaries lag, reads may wait or time out.

`secondaryPreferred` is merely a node selection policy, not a replacement for these conditions.

### Exercise 4. Testing a session in `mongosh`

Using an unused `requestId`, create a session:

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

const sdb = session.getDatabase("ryw_lab");

try {
  printjson(sdb.runCommand({
    insert: "orders",
    documents: [
      {
        _id: "O-EX-SESSION-1",
        requestId: "R-EX-SESSION-1",
        state: "CREATED"
      }
    ],
    writeConcern: { w: "majority", wtimeout: 10000 }
  }));

  printjson(sdb.runCommand({
    find: "orders",
    filter: { _id: "O-EX-SESSION-1" },
    readConcern: { level: "majority" }
  }));
} finally {
  session.endSession();
}
~~~

**Question:** Which elements in this code are critical for causality? Can we assert the read in this exercise ran on a secondary just because `readConcern = majority`?

**Guidance:** Same session, majority write, majority read, and sequential execution. No, read concern is not read preference; configure secondary selection explicitly to test a secondary node.

### Exercise 5. New session in a second HTTP request

POST is handled by service A with session S1; GET is handled by service B with S2 and a secondary read. No causal metadata is forwarded.

**Question:** What can happen when GET arrives right after POST? Propose two remediation options.

**Guidance:** S2 does not know S1's causal milestone, and the secondary may be stale. You can route GET to primary per contract, or forward causal tokens/keep one session flow when appropriate. Returning the order from POST and syncing the UI is also viable for some products.

### Exercise 6. Lost write response and duplicate risk

A client submits an order creation request; MongoDB may have written successfully, yet the backend times out before receiving the response. The client retries with a new `orderId`.

**Question:** What risk arises? Which mechanism complements RYW?

**Guidance:** Duplicate orders may be created. Use a stable `requestId`/idempotency key, appropriate unique constraints, state reconciliation reads, and bounded retries. Causal consistency alone does not recognize two distinct business requests as one action.

### Exercise 7. Transactions before and after commit

Transaction T:

~~~text
T: insert document X
T: find X -> sees X
T: not committed yet
Other client: find X -> ?
T: commit
Other client: secondary read -> ?
~~~

**Question:** Can the other client see X before commit? After commit, is any arbitrary secondary guaranteed to see X immediately?

**Guidance:** Uncommitted writes are invisible externally. After commit, secondaries may take time to apply; for causal RYW, you need causal milestone linkage and proper concerns, or primary reads.

### Exercise 8. Linearizable and snapshot

Choose between two requirements:

1. Reading a single lock-state document requiring awareness of prior completed majority writes in real-time order.
2. Consistently reading balances and multiple transaction documents at a single suitable snapshot.

**Guidance:** (1) consider read concern `linearizable` on primary under applicable conditions; (2) consider transactions/`snapshot` per supported features. Never use `linearizable` as a toggle replacing multi-document transactions.

### Exercise 9. Majority write, yet GET still returns stale data

POST updates `displayName` from A to B; MongoDB primary acknowledges majority. GET returns A. Logs show GET was a Redis cache hit.

**Question:** Should raising MongoDB's read concern from `local` to `linearizable` be the first fix?

**Guidance:** No. GET is not reading MongoDB, so changing read concern will not fix stale data in Redis. Investigate cache invalidation/versioning or bypass per API contract.

### Exercise 10. `maxStalenessSeconds`

A service uses **`readPreference: secondaryPreferred`** and `maxStalenessSeconds = 120` in a supported setup.

**Question:** Can it guarantee every GET within 100 ms after POST will see the document?

**Answer:** No. Filtering out overly stale secondaries beyond a threshold is only a node selection criterion, not proof the node applied a write that just occurred. A causal session or primary read may be needed for RYW.

### Exercise 11. Optimistic concurrency and versioning

Existing document:

~~~javascript
{
  _id: "PROFILE-EX",
  displayName: "A",
  version: 7
}
~~~

Two clients both read version 7 and try to update. Write the update for client A:

~~~javascript
db.profiles.updateOne(
  {
    _id: "PROFILE-EX",
    version: 7
  },
  {
    $set: { displayName: "B" },
    $inc: { version: 1 }
  }
);
~~~

**Question:** If A updates successfully, and B executes the same `version: 7` filter, what will `matchedCount` be? How does this relate to RYW?

**Guidance:** With the document now at version 8 and no reverting update, B matches nothing (`matchedCount = 0`). This is **lost-update/concurrency protection**; it complements rather than replaces read-your-writes when reads route to secondaries.

### Exercise 12. Reading from primary, yet query returns `null`

Insert:

~~~javascript
db.orders.insertOne({
  _id: "O-EX-12",
  state: "CREATED",
  tenantId: "T-A"
});
~~~

Read:

~~~javascript
db.orders.findOne({
  _id: "O-EX-12",
  state: "PAID",
  tenantId: "T-A"
});
~~~

**Question:** Does returning `null` prove the primary is out of sync?

**Answer:** No. The filter requires `PAID` whereas the document has `CREATED`. Verify query criteria, BSON types, tenant, projection, and collection before inferring consistency issues.

### Exercise 13. Design reasoning for two workloads

Propose appropriate configs/architectures for:

- **Flow A:** just saved a new address; the user must see the new address on the very next GET.
- **Flow B:** order count dashboard refreshing every minute and tolerating a few seconds of lag.

**Guidance:** Flow A needs RYW—read from primary or use a causal majority session if secondary reads are needed. Flow B can use secondaries or an asynchronous read model with replication/pipeline lag metrics and freshness indicators. Two flows need not share the same consistency level when business needs differ.

### Exercise 14. When a secondary has not caught up yet

Java Sync Driver uses a causal session, writes with `w:majority`, and reads from a secondary with read concern `majority`. The secondary lags behind the write point, and the operation has a time limit.

**Question:** Does a read returning a timeout error mean the RYW mechanism "returned wrong data"? What should be done?

**Guidance:** No. The read did not return stale wrong data; it could not serve at the requested consistency milestone within the time limit. The application needs bounded backoff/retry, switching to primary if contract permits, or returning a clear error. Never fall back to stale data while still claiming RYW was satisfied.

## 22. Self-check table when building a read-after-write API

Before implementing, document the system's explicit decisions:

| Question | Example required answer |
|---|---|
At what level is a write considered successful? | `w:majority` or `w:1` per durability needs |
Where does the subsequent read go? | `primary`/`secondary`/`nearest`/cache |
Is read-your-writes required? | Yes for order details, possibly no for analytics |
Do write and read share a causal session? | Yes/no; if no, how are reads routed? |
Which read concern is used? | `local`, `majority`, `snapshot`, or `linearizable` per goal |
Is the write confirmed before reading? | Clear `await`/sequencing |
If secondaries lag, what does the app do? | Wait, retry, primary fallback, or error per contract |
What if write response is lost? | Reconcile by `requestId`, idempotent retry |
Is GET cached? | Invalidation/version/bypass per requirements |
What if another client updates the same document? | Version/CAS or transaction per business logic |
What if failover occurs between steps? | Timeout/retry strategy without false rollback assumptions |
What latency is acceptable? | p95/p99 targets, monitor replication lag |

Answering these clearly turns concern and session selection into a defensible engineering decision rather than copy-pasted configuration from another example.

## 23. Summary of principles

~~~text
                     WRITE X
                        |
                  Write concern
                        |
           +------------+-------------+
           |                          |
         w:1                      w:majority
           |                          |
     Primary ACK                Majority ACK
           |                          |
           v                          v
   Primary read usually        Need read-after-write?
   sees X, but rollback           /          \
   remains possible on          Yes          No
   failover                      |             |
                          Read primary or    Choose eventual
                          causal session     per workload
                                 |
                        +--------+---------+
                        |                  |
                 Primary read       Secondary read
                        |                  |
                proper concern       majority read
                                     + causal token
                                     + same session
                                     + sequential order
                        |                  |
                        +--------+---------+
                                 |
                                 v
                       Read succeeds at
                       exact required point
                       or waits/errors clearly
~~~

**Key points to remember:**

1. **Reading from the same primary after a successful write** is the simple case that usually observes the write effect, though **`w:1` does not guarantee survival across failover**.
2. **`w:majority` does not make all secondaries update instantaneously**. A secondary performing a majority read without knowing the prior write milestone can still lag behind.
3. To guarantee **read-your-writes on secondaries in a causal session**, you need **majority write, majority read, a causal session, and sequential operations**.
4. **Causal reads can wait or error** rather than returning an overly stale snapshot. Consistency is not a promise of instantaneous results.
5. **Transaction read-your-own-writes** and **post-commit reads from another session** are two different problems.
6. **Linearizable reads** serve stronger real-time guarantees within supported scope; **snapshot** serves consistent point-in-time views—do not use them interchangeably.
7. **Timeouts, caches, and wrong query filters** can also create the appearance of "missing just-written data." Investigate end-to-end paths rather than tweaking a single read concern.
8. **RYW does not replace idempotency, unique constraints, or atomic updates**. Those controls remain necessary whenever multiple clients/workers can issue duplicate or competing operations.

## 24. Conclusion

MongoDB has no single toggle guaranteeing "every reader anywhere immediately sees just-written data" regardless of node, session, concern, and failures. Proper design begins with **causal dependency scope**, selecting **write durability**, **read routing**, **read concern**, and handling when nodes fall behind.

For straightforward CRUD flows, reading from the **primary after write acknowledgment** usually meets immediate visibility needs; for durability, choose an appropriate write concern, typically majority. For **write then secondary read** flows, a **causally consistent session paired with majority write + majority read** is MongoDB's core mechanism protecting read-your-writes. For multi-document data or stronger real-time needs, evaluate transactions/`snapshot` or properly scoped `linearizable` reads.

More importantly, consider the whole system: **`requestId`, retries, failovers, caches, versions, and business logic**. When those pieces are aligned, an application can make a clear, enforceable promise: after a contract-compliant write succeeds, related reads will never silently revert to stale data, or will explicitly report that the requested consistency level cannot currently be served.
