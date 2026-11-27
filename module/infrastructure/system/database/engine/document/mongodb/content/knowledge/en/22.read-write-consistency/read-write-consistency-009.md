# Combining read concern, write concern, and read preference by business workload in MongoDB

## 1. Real-world problem: write succeeded, yet read does not see it?

Suppose an e-commerce application runs on a MongoDB replica set. A user just placed an order, and the API returned "Order placed successfully." Immediately afterward, the order history screen calls another API and does not see the new order. In another scenario, the application reads the order on the primary, and after a failover, it disappears.

Both phenomena can involve **replication**, yet their causes and solutions differ:

1. **Secondary has not caught up to the primary:** the order was acknowledged with sufficient durability, but the node serving the read request is lagging and returns stale data.
2. **Write was not majority-committed:** the primary acknowledged at a weaker level, and after an incident, the oplog history containing the write may be rolled back.
3. **Application reads in a different context:** the write request and read request use different read preferences, sessions, or read concerns, failing to guarantee read-your-writes.

MongoDB provides three critical configuration groups answering **three distinct questions**:

| Mechanism | Question answered | Examples |
| --- | --- | --- |
| **write concern** | When is MongoDB considered to have acknowledged a write command? | **w: 1** or **w: "majority"** |
| **read concern** | Which type of data state is a read command permitted to observe? | **local**, **majority**, **snapshot**, **linearizable** |
| **read preference** | Which node type will the driver select to serve a read command? | **primary**, **secondaryPreferred**, **nearest** |

These three choices **cannot substitute for one another**. Using `readPreference: primary` does not automatically turn a `w: 1` write into majority-committed. Using `readConcern: majority` does not force queries to run on the primary. Using `w: majority` does not force every secondary to see the new write immediately.

This lesson focuses on **how to combine the three mechanisms by business requirement**, rather than explaining each option in isolation.

### After this lesson, you will be able to

- Distinguish **write durability**, **consistency guarantees of read data**, and **serving node placement**.
- Choose appropriate combinations for **orders, payments, inventory, user profiles, dashboards, reports, and audits**.
- Explain **stale reads**, **rollbacks**, **read-your-writes**, and **unknown write outcomes**.
- Use **causally consistent sessions** when recent writes must be read on secondaries.
- Understand **readConcern `snapshot`/`linearizable`**, transactions, and deployment limits.
- Write `mongosh` and Node.js driver queries with explicit settings.
- Build a consistency policy matrix aligned with **SLAs, data-loss risk, and latency**.
- Inspect a replica set without intentionally inducing failovers.

> Safety rule: consistency is a property of **the entire business process**. A strong database setting does not replace conditional inventory updates, unique indexes, idempotency, transactions, or tenant authorization checks.

## 2. System model to understand before choosing options

### 2.1. Primary, secondaries, and oplog

A replica set with three data-bearing voting members can be pictured as:

~~~text
                        Application
                     /              \
         write request               read request
               |                    /         \
               v                   v           v
         Primary P              Primary P    Secondary S1
               |
               | oplog, asynchronous replication
               +------------------------> Secondary S1
               |
               +------------------------> Secondary S2
~~~

The primary typically accepts write operations. Secondaries tail the oplog to apply changes. Because replication is asynchronous, at the same instant:

~~~text
Primary P:     ... E100 E101 E102 E103
Secondary S1:  ... E100 E101 E102
Secondary S2:  ... E100 E101
~~~

A query on S2 may not see E102/E103 yet; a query on P may see E103. However, seeing E103 **is insufficient to confirm E103 is majority-committed**.

### 2.2. Majority commit point

The **majority commit point** is the boundary in oplog history up to which MongoDB considers entries replicated to an eligible majority of members and satisfying corresponding durability rules.

In the diagram above, if P and S1 both hold E102, then E102 can reach majority in a three data-bearing voting-member configuration; E103, existing only on P, has not. Entries **not yet majority-committed** can roll back when another history becomes authoritative after an election.

~~~text
History on P:
  E100 -- E101 -- E102 || E103
                 ^
          majority commit point

E103: primary may have received it, yet it is not protected
      as majority-committed history.
~~~

**This does not mean `w:1` always loses data.** A write acknowledged at `w:1` may still replicate quickly enough to become majority-committed before a crash occurs. The issue is that **the client has no guarantee of that at the moment it receives a `w:1` acknowledgment**.

### 2.3. Two independent dimensions: safety and freshness

A write can be:

- **Safe against normal rollbacks** because it is majority-committed.
- Yet **not visible on S2** because S2 has not applied up to that point yet.

A read can be:

- **Very fresh** because it reads directly from the primary.
- Yet observing a write **not yet majority-committed**, carrying rollback risk.

Therefore, "reading the freshest data" and "reading rollback-resistant data" are two distinct properties. Choose read concern and read preference considering both.

## 3. Write concern: how far must a write go before returning success?

### 3.1. Common structure

`mongosh` example:

~~~javascript
db.orders.insertOne(
  {
    _id: "order-001",
    status: "created"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
~~~

Components:

| Component | Role |
| --- | --- |
| **w: 0** | Does not wait for standard write acknowledgment |
| **w: 1** | Primary acknowledges operation per `w:1` semantics |
| **w: "majority"** | Waits for replication to majority per replica set configuration |
| **j: true** | Requests journal durability per write concern and storage engine semantics |
| **wtimeout** | Wait timeout for write concern conditions, in milliseconds |

**`wtimeout` does not automatically roll back an operation already applied on the primary.** When a write concern error occurs, the application may not immediately know to what extent the write succeeded; handle the unknown state.

### 3.2. `w:1` and rollback risk

Suppose P has E201 while S1/S2 do not:

~~~text
P  : E200 E201  (client received w:1 ACK)
S1 : E200
S2 : E200
~~~

If P becomes isolated and S1/S2 elect a new primary, E201 may roll back when P rejoins. The user previously received "created," yet the document may be lost.

**`w:1`** may suit regenerable data or workloads accepting a narrow risk window. It is unsuitable if policy requires confirmed orders to be protected from normal failover rollbacks.

### 3.3. `w:"majority"`

With three data-bearing voting members:

~~~text
P  : E200 E201
S1 : E200 E201
S2 : E200

E201 is acknowledged by majority (P + S1),
assuming durability conditions are satisfied.
~~~

When the client receives a **successful `w:"majority"` acknowledgment**, the write satisfied the command's majority condition. This helps protect the write from rollback during normal valid failovers/elections.

**`w:"majority"` does not mean all secondaries are updated**, is not a backup, and does not make a business-invalid write valid.

### 3.4. `j:true` and `writeConcernMajorityJournalDefault`

**`j:true`** relates to journal durability. **Journaling does not replace replication majority**: a write journaled on the primary can still sit on an oplog branch rolled back after an election.

Many replica sets configure **`writeConcernMajorityJournalDefault: true`**, causing majority write concerns to wait for the corresponding journal requirement. Verify specific config and versions; never assume every environment behaves identically.

For financial transactions or hard-to-recreate state, design guarantees across **replication, durability, idempotency, and backups**, not a single parameter.

### 3.5. `wtimeout` and unknown outcomes

~~~javascript
db.orders.insertOne(
  { _id: "order-002", status: "created" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

If secondaries are too slow or too few nodes are available to satisfy majority, MongoDB may return a **write concern timeout/error**. Possible situations:

1. Primary wrote the document, not yet acknowledged by majority.
2. Write was applied and reached majority afterward, despite the client receiving a timeout.
3. Failover caused the non-majority-committed write to roll back.
4. Network response dropped, so the client does not know exactly what the server did.

**Never automatically resend an `$inc` command or create an order with a new ID just because of a timeout.** Use `requestId`/idempotency keys and reconciliation to determine outcomes.

## 4. Read concern: what guarantee level must read data meet?

Read concern is configured on read operations; it governs acceptable data states and consistency under MongoDB's model.

### 4.1. `readConcern: "local"`

**`local`** can return data applied by the serving node, even if that data is **not yet majority-committed**. It is useful for many routine needs, but offers no guarantee against observing data that might later roll back.

Example:

~~~text
Primary P:
  applied E103
  majority commit point currently at E102

readConcern local from P:
  can observe the effect of E103.

If E103 rolls back after failover:
  client previously saw data that no longer exists in the new history.
~~~

Reading `local` does not mean documents are corrupt or queries return wrong data for that node; it means **this read concern permits observing data past the majority commit point**.

### 4.2. `readConcern: "majority"`

**`majority`** returns only data that has reached majority-committed status per this read concern's semantics. It fits when applications must avoid reading writes that could later roll back during normal failovers.

`mongosh` example via database command:

~~~javascript
const lab = db.getSiblingDB("mongo_consistency_lab");

const response = lab.runCommand({
  find: "lab_orders",
  filter: { dataset: "consistency-v1", tenantId: "t001" },
  sort: { createdAt: -1, _id: 1 },
  limit: 10,
  readConcern: { level: "majority" }
});

if (response.ok !== 1) {
  throw new Error(tojson(response));
}

printjson(response.cursor.firstBatch);
~~~

**`readConcern: "majority"` does not mean reading the freshest state on every secondary.** If the reading node lags behind the primary, a majority read can return an older state while remaining completely valid under this guarantee.

### 4.3. `readConcern: "snapshot"`

**`snapshot`** is used when reading a consistent snapshot at an eligible milestone, crucial in multi-document transactions and supported snapshot-read contexts. Example:

~~~text
Transaction reads:
  Orders at snapshot T
  Payments at snapshot T
  Inventory at snapshot T

=> reads inside the transaction view one consistent
   snapshot per transaction semantics.
~~~

Inside transactions, set **`readConcern: {level:"snapshot"}`** and use **`writeConcern: "majority"` on commit** if corresponding durability is required.

**`snapshot` is not automatically the latest wall-clock state**, nor does it create transactions spanning external systems outside MongoDB.

### 4.4. `readConcern: "linearizable"`

**`linearizable`** targets a stronger real-time ordering guarantee for **single-document reads from the primary**, within MongoDB's supported scope and assuming writes were majority-acknowledged as required.

Suitable scenario: before making a critical decision, a service checks a contended single document's state and must not observe stale state caused by a primary transition.

Illustrative command example:

~~~javascript
const lab = db.getSiblingDB("mongo_consistency_lab");

const result = lab.runCommand({
  find: "lab_order_controls",
  filter: { _id: "control-001", dataset: "consistency-v1" },
  limit: 1,
  singleBatch: true,
  readConcern: { level: "linearizable" },
  maxTimeMS: 2000
});

printjson(result);
~~~

When using `linearizable`:

- Target **`primary`** and obey all constraints of this read level.
- Set **`maxTimeMS`/deadlines** to prevent requests from blocking indefinitely when quorum is lost.
- Account for latency cost; do not apply to every listing page just because it "sounds stronger."
- Do not replace **conditional updates** or transactions for preserving invariants under concurrent writes.

**A `linearizable` read followed by an unconditional update still has a race window between the two operations.** If stock must only decrement when enough inventory is available, put **`available >= quantity` inside the update itself**, rather than relying solely on a prior fresh read.

### 4.5. `readConcern: "available"`

MongoDB provides **`available`** in deployment contexts, particularly notable in sharded clusters. This read level favors availability, offering weaker guarantees against rollback-prone data and exhibiting differences such as orphaned document behavior in certain sharding situations.

Do not use `available` for decisions needing rollback avoidance or strong consistency. When using in sharded clusters, consult exact version documentation; never infer from the name that it is always "fastest and safe."

### 4.6. Read concern comparison table

| Level | Core goal/characteristic | What NOT to misunderstand |
| --- | --- | --- |
| **local** | Reads node's applied state | Does not guarantee avoiding non-majority-committed data |
| **majority** | Reads majority-committed data | Not automatically the freshest on secondaries |
| **snapshot** | Consistent snapshot at a supported point | Not synonymous with linearizable or "always latest" |
| **linearizable** | Strong real-time guarantee for single-document reads from primary | Different cost/availability; does not replace conditional writes |
| **available** | Prioritizes availability in supported contexts | Carries no majority guarantee; check sharding semantics |

## 5. Read preference: which node does the driver pick for reads?

### 5.1. Primary modes

| Read preference | Node selection | Considerations |
| --- | --- | --- |
| **primary** | Primary only for standard reads | Avoids secondary lag, though primary can overload |
| **primaryPreferred** | Prefers primary, falls back to secondary if primary unselectable | Fallback can return staler data |
| **secondary** | Eligible secondaries only | Can be stale, and no eligible node may exist |
| **secondaryPreferred** | Prefers secondary, falls back to primary if no secondary selectable | Freshness may vary across reads |
| **nearest** | Picks eligible node based on measured network latency, tags/staleness constraints, and selection rules | Does not mean "node with the freshest data" |

Read preference decides **where to read**, while read concern decides **what data state can be read**. Both mechanisms coexist in every query.

### 5.2. Reading from primary does not eliminate rollback risk on its own

If the primary applied a `w:1` write not yet majority-committed, a `local` read from the **primary** can see that write. After a failover, that write can still roll back.

~~~text
WRITE w:1 -> primary ACK
READ  local + primary -> sees write
FAILOVER before majority -> write can roll back
~~~

Therefore, "just read from primary" does not replace majority write concern when acknowledged data must be protected.

### 5.3. Secondary reads can be stale even with `majority`

~~~text
WRITE majority -> acknowledged by majority
READ  majority + secondary S2

S2 has not yet applied the write:
  can still return older majority-committed data.
~~~

Thus, **majority reads on secondaries do not automatically establish read-your-writes across two independent requests**. Design causally consistent sessions, or read from primary as required.

### 5.4. Tag sets, geography, and `maxStalenessSeconds`

Drivers allow configuring read preference with **tag sets** and, when eligible, **`maxStalenessSeconds`** to reduce the chance of selecting overly lagging secondaries.

Node.js driver example:

~~~javascript
import { ReadPreference } from "mongodb";

const preference = new ReadPreference(
  "secondaryPreferred",
  [{ region: "ap-southeast-1" }],
  { maxStalenessSeconds: 120 }
);
~~~

Configuration validity depends on topology and driver. In many deployments, **minimum `maxStalenessSeconds` is 90 seconds** (outside special/testing modes allowed by docs), and staleness is an **estimate used for node selection**.

**Do not advertise `maxStalenessSeconds = 120` as a hard SLA that "data is never older than 120 seconds."** It does not replace causal consistency and does not synchronize data when the replica set lags.

### 5.5. Secondaries are not just for "cheap reads"

Offloading reads to secondaries reduces some load on the primary, while simultaneously:

- Secondaries still must apply replication writes.
- Heavy queries can increase lag or contend for resources with replication.
- Nodes differ in cache warmup, disk I/O, and network latency.
- Fallback in **`secondaryPreferred`** sometimes sends queries back to the primary.
- Overly narrow tag sets may yield no eligible nodes.

Read preference choices must be benchmarked on **real topologies**; never treat secondaries as "free."

## 6. Combining all three axes: no single combination fits all workloads

Examine common goals:

| Workload | Desired write durability | Read freshness | Acceptable cost |
| --- | --- | --- | --- |
| Order confirmation | Very high | User must see newly created order | Accept majority wait and explicit retry policy |
| Payment processing | Very high | Must not read rollback-prone states | Accept transactions/sessions and reconciliation |
| Inventory reservation | High | Decisions based on current contended state | Requires conditional atomic updates, not just reads |
| User edits profile then opens view page | High or medium per SLA | **Read-your-writes** | Can use primary or causal session |
| Overview analytics dashboard | Follows source data | Tolerates seconds/minutes delay if clearly defined | Can read secondaries or read models |
| Daily/weekly reports | Depends on source data | Tolerates point-in-time snapshots | Can prefer secondaries/snapshots |
| Replayable telemetry | Tolerates minor loss | Immediate visibility not required | Lighter policy after risk evaluation |
| Controlling state of a single resource | High | Needs real-time-meaningful single-document read | Consider linearizable reads and guarded writes |

Do not pick settings by slapping "strongest read concern" on all requests. Exact requirements must be written as a **business contract**: after an API reports success, what must users see, acceptable latency, rollback risk, stale-data tolerance, and behavior when quorum is unavailable.

## 7. Pattern 1 — Ordering: never report success before durable writes

### 7.1. Business contract

The **`POST /orders`** API returns success only once the Order is written with a write concern satisfying failover protection rules, and duplicate requests do not create extra orders.

Initial proposal:

- **Write:** `w:"majority"`, with durability/journaling per appropriate config.
- **Post-write read:** `primary` + `majority` if avoiding rollback-prone data; or causal session if reading secondaries while needing read-your-writes.
- **Read preference for post-write check API:** `primary` is usually simpler.
- **Idempotency:** deterministic `requestId`/`orderId` and an appropriate unique index.
- **Errors:** write concern timeouts/network timeouts must be reconciled, never blindly recreating orders.

### 7.2. Two timelines

**Risky design:**

~~~text
Client             API            P              S1/S2
  | POST /orders    |             |               |
  |---------------->| insert w:1  |               |
  |                 |------------>| apply         |
  |                 |<------------| ACK w:1       |
  |<----------------| 201 Created |               |
  | GET /orders     |             |               |
  |---------------->| secondaryPreferred          |
  |                 |---------------------------->|
  |<----------------| may not see Order yet       |
~~~

**Better design when durability and read-your-writes are required:**

~~~text
POST /orders:
  writeConcern majority + idempotency key
         |
         v
  Server satisfies majority -> API confirms
         |
         v
GET /orders:
  Read primary, or use causally consistent session
  majority read if secondaries must be read.
~~~

**Note:** if POST and GET are two HTTP requests hitting two different API instances, causal sessions do not automatically propagate across requests. Design explicit context propagation/persistence, or use primary reads per freshness policy.

### 7.3. Consequences of `wtimeout`

If `POST /orders` hits `wtimeout`, the API must not assert "order was not created." It can return a state requiring verification/reconciliation, preserve `requestId`, and expose a lookup endpoint by `requestId`. The exact HTTP status code depends on the API contract, **but never turn an unknown outcome into a definitive failure confirmation**.

## 8. Pattern 2 — Read-your-writes right after a user updates their profile

### 8.1. Problem

A user changes `displayName` to "Minh". The update API succeeds, and the frontend calls `GET /profile`. If GET picks a lagging secondary, the user may see the old name.

**`readConcern: "majority"` alone does not reliably fix this** if the secondary has not yet applied the new write.

### 8.2. Causal consistency

MongoDB supports **causally consistent sessions**, under eligible conditions, to preserve causal relationships among operations in the same session. Under the documented recommended model, combine:

- **Write concern `"majority"`** for writes in the session.
- **Read concern `"majority"`** for reads in the session.
- Operations executed sequentially in order, **never arbitrarily in parallel on the same session**.
- Pass the session/context across operations requiring causal ordering.

Properties can include **read-your-writes**, **monotonic reads**, **monotonic writes**, and **writes-follow-reads** within causal consistency bounds.

~~~text
Within the same causally consistent session:
    UPDATE profile (w: majority)
           |
           | causal ordering / operation time
           v
    READ profile (readConcern: majority)
    from node eligible under readPreference

=> read is constrained by the session's causal history.
~~~

When reading from a secondary that has not caught up to the needed point, driver/server may wait until the point is reached or hit a timeout/error within limits. Causal consistency **does not make replication instantaneous**.

### 8.3. Node.js driver code

~~~javascript
import { MongoClient } from "mongodb";

async function updateThenReadProfile(uri) {
  const client = new MongoClient(uri, {
    retryWrites: true
  });
  await client.connect();

  const session = client.startSession({
    causalConsistency: true
  });

  try {
    const profiles = client
      .db("mongo_consistency_lab")
      .collection("lab_profiles");

    const filter = {
      _id: "profile-001",
      dataset: "consistency-v1",
      tenantId: "t001"
    };

    const update = await profiles.updateOne(
      filter,
      { $set: { displayName: "Minh" } },
      {
        session,
        writeConcern: {
          w: "majority",
          wtimeoutMS: 10000
        }
      }
    );

    if (update.matchedCount !== 1) {
      throw new Error("Valid profile not found");
    }

    const readBack = await profiles.findOne(
      filter,
      {
        session,
        readConcern: { level: "majority" },
        readPreference: "secondaryPreferred",
        maxTimeMS: 5000
      }
    );

    return readBack;
  } finally {
    await session.endSession();
    await client.close();
  }
}

// await updateThenReadProfile(process.env.MONGODB_URI);
~~~

Key points:

1. The **same session** is passed to `updateOne` and `findOne`.
2. Update uses **`w:"majority"`**; read uses **`readConcern: majority`**.
3. The read may select `secondaryPreferred` while still respecting the session's causal ordering.
4. If the deadline cannot be met, the application must handle the timeout; never fall back to stale data while still claiming "read-your-writes guaranteed."
5. This snippet assumes a lab replica set already seeded with the profile; seed scripts are provided in Section 14.

### 8.4. Sessions do not automatically persist across multiple HTTP requests

If update runs on API instance A and read runs on API instance B with a new session, **causality is not automatically inherited**. Design paths:

- Read primary after write for flows needing simplicity and freshness.
- Keep a workflow within the same backend session when possible.
- Propagate causal context/`clusterTime` per driver docs when architecture truly requires it; strictly validate metadata source and usage.
- Design controlled optimistic/self-refreshing UIs if business logic accepts eventual visibility.

Never treat one MongoDB `ClientSession` as a global object for concurrent requests. `ClientSession` is not designed for arbitrary parallel operations sharing causal/transaction state.

## 9. Pattern 3 — Inventory: correctness comes from conditional writes

### 9.1. Strong read concerns alone do not prevent overselling

Suppose **`available = 1`**:

~~~text
Request A: reads available=1
Request B: reads available=1

A: decrements 1
B: decrements 1

If both rely only on read results and write unconditionally,
available can go negative or one update overwrites the other.
~~~

Even if A and B both use scoped **`linearizable` reads**, a race window still exists between read and update. **Read concern does not replace atomic conditional updates.**

### 9.2. Updating safely with a conditional filter

~~~javascript
const stock = db.getSiblingDB("mongo_consistency_lab")
  .getCollection("lab_stock");

const result = stock.updateOne(
  {
    _id: "sku-001",
    dataset: "consistency-v1",
    tenantId: "t001",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1,
      version: 1
    }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);

printjson(result);
~~~

A single-document update is atomic, including its filter condition. Once stock reaches 0, subsequent attempts fail to match the filter. **`w:"majority"`** protects the write result from normal failover rollback after acknowledgment; the **filter** enforces the non-negative `available` invariant.

To prevent **the same request from re-executing**, also add `reservationId`/idempotency. If reservation and stock span **multiple documents**, use a transaction or an event/ledger model.

### 9.3. Inventory read policies

- On product pages, displaying stock counts a few seconds behind (per SLA) is often acceptable as informational data.
- At **reservation/checkout time**, issue a **conditional write to the primary** rather than trusting displayed stock.
- When verifying a newly created reservation, use primary or a causal session to avoid stale state.
- For confirmed orders, ensure durability and reconcile on timeouts.

One workflow can use **two different read policies for the exact same field** for different purposes.

## 10. Pattern 4 — Dashboards and reports: tolerating intentional lag

### 10.1. Overview pages

A dashboard showing today's order totals can tolerate a small, disclosed delay. In that case:

- Order data is still written with its proper durability policy.
- Reporting queries can use **`secondaryPreferred`** or run against a read model.
- Use **`readConcern: majority`** if avoiding rollback-prone data in totals.
- Measure replication lag and define response freshness.
- APIs can return **`asOf`** or computation timestamp instead of implying "strict real-time."

**Never lower Order write concern to `w:1` just because dashboards tolerate lag.** Source data durability and screen freshness are two separate decisions.

### 10.2. Reports needing cross-collection consistency

If a report sums `Orders` and `Payments` to compare them, reading two collections at unsynchronized times can produce temporarily skewed ratios. When a **consistent logical snapshot** is required, use a **`snapshot`** transaction or an appropriate snapshot/read-model mechanism.

Do not run two independent majority queries and assume they share one snapshot:

~~~text
READ Orders with readConcern majority at T1
          ...
WRITE Payment commits between the two reads
          ...
READ Payments with readConcern majority at T2

=> T1 and T2 may differ.
~~~

Read concern `majority` protects read data from rollback, **without synchronizing independent calls to the same snapshot milestone**.

### 10.3. Do not dump every heavy workload onto secondaries

Heavy aggregations on secondaries can:

- Compete for I/O with replication.
- Cause higher replication lag.
- Evict secondary cache pages needed for routine reads.
- Slow down during topology changes.

For heavy reports, consider **materialized summaries**, batch jobs, properly sized read replicas, and explicit staleness/timeout policies.

## 11. Pattern 5 — Payments and auditing: cross-document integrity

### 11.1. Requirements

Payment APIs typically require:

- Never recording the same payment twice.
- Updating Order status to paid alongside recording Payment/Audit entries consistently.
- Ensuring a "confirmed" outcome survives normal failovers.
- Allowing services to determine whether payment committed after a disconnect.

A combination to evaluate:

| Stage | Tools |
| --- | --- |
| Request/payment validation | Business validation, unique idempotency key |
| Update Order + Payment + Outbox | Multi-document **transaction** |
| Reads inside transaction | **`readConcern: snapshot`** when appropriate |
| Commit transaction | **`writeConcern: "majority"`** |
| Post-commit reads | Primary + majority, or causal session when needed |
| Lost commit response | Driver transaction retry/reconciliation by `requestId` |
| Calling external payment gateway/email | Outbox/saga and idempotency; **do not** treat as part of MongoDB transaction |

**`readPreference`** for transactions is typically **`primary`**. Never try routing transactional writes to secondaries.

### 11.2. Node.js transaction example

~~~javascript
import { MongoClient } from "mongodb";

async function markPaid(uri, orderId, paymentId) {
  const client = new MongoClient(uri, { retryWrites: true });
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_consistency_lab");
  const orders = lab.collection("lab_orders");
  const payments = lab.collection("lab_payments");

  try {
    await session.withTransaction(async () => {
      // Payment _id serves as the idempotency key for this lab.
      const already = await payments.findOne(
        { _id: paymentId, dataset: "consistency-v1" },
        { session }
      );

      if (already) {
        if (already.orderId !== orderId) {
          throw new Error("paymentId is already bound to another Order");
        }
        return;
      }

      const updated = await orders.updateOne(
        {
          _id: orderId,
          dataset: "consistency-v1",
          tenantId: "t001",
          status: "created"
        },
        {
          $set: { status: "paid" },
          $currentDate: { paidAt: true }
        },
        { session }
      );

      if (updated.matchedCount !== 1) {
        throw new Error("Order is not in a valid state");
      }

      await payments.insertOne(
        {
          _id: paymentId,
          dataset: "consistency-v1",
          tenantId: "t001",
          orderId,
          status: "recorded",
          createdAt: new Date()
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Run only on the lab replica set after seeding in Section 14.
// await markPaid(process.env.MONGODB_URI, "order-001", "pay-001");
~~~

This snippet simulates only recording Payment state **inside MongoDB**, without calling or executing real payments. For concurrent requests using the same `paymentId`, handle duplicate keys/write conflicts and verify commit outcomes rather than relying solely on `findOne` before insert. A unique `_id` provides partial database-level idempotency.

**`withTransaction` may retry the callback.** Never invoke non-idempotent payment gateways or email sends inside the callback.

### 11.3. Majority does not automatically guarantee business correctness

If an operation writes a wrong amount and commits with majority, majority protects **that wrong value** from normal rollback. To prevent mistakes:

- Unique indexes and idempotency.
- State conditions in filters.
- Proper transaction boundaries.
- Validation and currency handling.
- Reconciliation and auditing.

Choosing concerns is necessary, not sufficient.

## 12. Causal consistency, snapshot, and linearizable: distinct choices

All three terms may loosely be called "consistent reads," yet they solve separate problems.

### 12.1. Causal consistency

Goal: preserve causal ordering across operations within a session, such as **writing a profile then reading it back**.

Key characteristics:

- Bound to **session context** and operation sequence.
- Can allow reading from secondaries with appropriate `readPreference`.
- Relies on majority reads/writes for causal guarantees as documented.
- Does not make secondaries catch up instantly; may wait or time out.

### 12.2. Snapshot consistency

Goal: multiple reads observe **one consistent logical snapshot** for analytics/transactions, avoiding mixing data from different timestamps.

Key characteristics:

- Very useful with multi-document transactions.
- Does not automatically return the latest real-time data.
- Carries resource costs, transaction lifetime limits, and write conflict handling.
- Does not replace idempotency or commit write concern.

### 12.3. Linearizable read

Goal: strong real-time ordering guarantee for a single-document read within supported scope, with primary routing and appropriate write conditions.

Key characteristics:

- Suits critical state decisions.
- May wait during quorum loss; set `maxTimeMS`.
- Does not turn read–modify–write into an atomic operation.
- Not a default choice for dashboards or multi-million-document pagination.

### 12.4. Selection table

| Goal | Primary tool | Insufficient if using only |
| --- | --- | --- |
| Must immediately read back the write just performed | **Causal session** or primary read per contract | Independent `readConcern: majority` on secondary |
| Report reading multiple collections at the same snapshot | **`snapshot`** in transactions/supported snapshot reads | Two independent majority reads |
| Single-document state read with strong real-time guarantee | **`linearizable`** from primary | `secondaryPreferred` |
| Decrement inventory without going negative | **Conditional atomic update** | `linearizable` read followed by unconditional update |
| Commit Order + Payment together | **Transaction + majority commit** | `w:majority` on two independent `updateOne` calls |
| Protect confirmed Orders from normal rollback loss | **`w:"majority"`** | Reading primary only |

## 13. Failure scenarios and root-cause analysis

### 13.1. "POST succeeded, yet GET returned empty"

Causes to check in order:

1. Did GET pass the right **`tenantId`**, `_id`, and filters?
2. Did POST use the right write concern and receive acknowledged success, or did it time out?
3. Did GET hit a secondary? What is the secondary lag?
4. Which `readConcern` did GET use?
5. Did POST and GET share a causal session?
6. Were there recent elections/failovers, rollbacks, or write conflicts?
7. Is there an application-layer cache, queue, or eventual read model?

Never conclude "MongoDB lost data" from one empty GET. A wrong tenant filter or stale secondary produces identical symptoms.

### 13.2. "Read saw it earlier, then it vanished"

If data was read with `readConcern: local` on primary before the write was majority-committed, rollback could explain it. However, a valid application delete/update could also explain it.

To investigate:

- Check the write concern of the creation operation.
- Check timestamps of elections/stepdowns.
- Inspect rollback logs or signals.
- Cross-check audit/transaction/outbox records.
- Verify permissions and query filters; never manually alter production data before knowing the root cause.

### 13.3. "Majority writes frequently time out"

Possible causes:

- Insufficient healthy data-bearing voting members.
- Secondary lag, disk I/O bottlenecks, or network congestion.
- Excessive write workload or costly index maintenance.
- Timeout set too short relative to real latency.
- Replica set configured with arbiters or special members altering write majority calculations unexpectedly.

**Never silently downgrade to `w:1`** if data requires rollback protection. Investigate quorum and replication before relaxing policies.

### 13.4. "Secondary reads are faster, yet numbers differ"

Secondary reads can be stale to varying degrees. With **`nearest`**, the driver may pick different nodes across calls; each node sits at different replication progress. If the application needs monotonic reads or read-your-writes, use causal sessions properly or choose primary rather than relying on node-selection luck.

### 13.5. "Set `maxStalenessSeconds`, yet still misses SLA"

`maxStalenessSeconds` is a **node selection** mechanism based on estimated lag, not a hard freshness guarantee per record. For strict freshness SLAs, measure/sync data milestones, track `asOf` timestamps, and design fallbacks when no fresh-enough source exists.

## 14. `mongosh` lab: fixed dataset and safe observation commands

Examples below strictly use a **dedicated practice replica set**. Never shut down nodes or induce elections/rollbacks. The goal is observing configuration behavior and seeing data once write concerns are satisfied.

### 14.1. Checking topology

~~~javascript
(() => {
  const hello = db.hello();

  printjson({
    setName: hello.setName,
    primary: hello.primary,
    isWritablePrimary: hello.isWritablePrimary,
    hosts: hello.hosts
  });

  if (!hello.setName) {
    throw new Error("Must connect to the lab replica set");
  }
})();
~~~

`db.hello()` changes no configuration. If `setName` is missing, the environment is not a replica set as required. On standalone instances, majority replication/elections cannot be observed like on three data-bearing nodes.

### 14.2. Seeding the practice collections

Database: **`mongo_consistency_lab`**.

Tag: **`consistency-v1`**.

Run as a block in `mongosh`:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const tag = "consistency-v1";
  const orders = lab.getCollection("lab_orders");
  const profiles = lab.getCollection("lab_profiles");
  const stock = lab.getCollection("lab_stock");
  const controls = lab.getCollection("lab_order_controls");
  const payments = lab.getCollection("lab_payments");

  // Lab data: clean up only documents matching the dataset label.
  const collections = [orders, profiles, stock, controls, payments];
  for (const collection of collections) {
    collection.deleteMany(
      { dataset: tag },
      { writeConcern: { w: "majority", wtimeout: 10000 } }
    );
  }

  orders.insertMany(
    [
      {
        _id: "order-001",
        dataset: tag,
        tenantId: "t001",
        status: "created",
        amount: NumberDecimal("100.00"),
        createdAt: ISODate("2026-01-01T08:00:00.000Z")
      },
      {
        _id: "order-002",
        dataset: tag,
        tenantId: "t001",
        status: "created",
        amount: NumberDecimal("200.00"),
        createdAt: ISODate("2026-01-02T08:00:00.000Z")
      },
      {
        _id: "order-003",
        dataset: tag,
        tenantId: "t002",
        status: "created",
        amount: NumberDecimal("300.00"),
        createdAt: ISODate("2026-01-03T08:00:00.000Z")
      }
    ],
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  profiles.insertOne(
    {
      _id: "profile-001",
      dataset: tag,
      tenantId: "t001",
      displayName: "Initial Name",
      version: NumberInt(0)
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  stock.insertOne(
    {
      _id: "sku-001",
      dataset: tag,
      tenantId: "t001",
      available: NumberInt(2),
      reserved: NumberInt(0),
      version: NumberInt(0)
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  controls.insertOne(
    {
      _id: "control-001",
      dataset: tag,
      tenantId: "t001",
      enabled: true
    },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: 1 },
    { name: "ix_consistency_lab_tenant_time" }
  );

  printjson({
    orders: orders.countDocuments({ dataset: tag }),
    profiles: profiles.countDocuments({ dataset: tag }),
    stock: stock.countDocuments({ dataset: tag }),
    controls: controls.countDocuments({ dataset: tag }),
    payments: payments.countDocuments({ dataset: tag })
  });
})();
~~~

**Expected result when replica set has majority:** 3 orders, 1 profile, 1 stock, 1 control, 0 payments.

The script does not drop collections or databases; however, `deleteMany`/inserts are separate operations, **not a single transaction**. Run only on the practice database and avoid running competing experiments concurrently on the same dataset label.

### 14.3. Writing with `majority` then reading `local`

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "consistency-v1";

  const result = orders.insertOne(
    {
      _id: "order-majority-004",
      dataset: tag,
      tenantId: "t001",
      status: "created",
      amount: NumberDecimal("50.00"),
      createdAt: ISODate("2026-01-04T08:00:00.000Z")
    },
    {
      writeConcern: { w: "majority", wtimeout: 10000 }
    }
  );

  printjson(result);
  printjson(orders.findOne({
    _id: "order-majority-004",
    dataset: tag
  }));
})();
~~~

Once majority-acknowledged, the document has satisfied the requested acknowledgment level. **Default `findOne` on a primary connection** sees the document; however, a default client-configured read does not verify all read concern levels.

Re-running with the same `_id` produces a duplicate key error; that is the intended effect of fixed IDs, not failure of the first write. To reset, re-run the seed script.

### 14.4. Reading a majority snapshot via command

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const result = lab.runCommand({
    find: "lab_orders",
    filter: {
      dataset: "consistency-v1",
      tenantId: "t001"
    },
    sort: { createdAt: -1, _id: 1 },
    limit: 10,
    singleBatch: true,
    readConcern: { level: "majority" }
  });

  if (result.ok !== 1) {
    throw new Error(tojson(result));
  }

  printjson(result.cursor.firstBatch);
})();
~~~

The result contains `t001` orders majority-committed at the read's serving milestone. If you just ran the majority insert step, `order-majority-004` is included. **Depending on `mongosh`/server version and topology**, specifying `readPreference` to read from secondaries should be done via connection/driver settings; the command above does not route to a secondary by itself.

### 14.5. Writing with `w:1`

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_consistency_lab");
  const orders = lab.getCollection("lab_orders");

  const result = orders.insertOne(
    {
      _id: "order-w1-005",
      dataset: "consistency-v1",
      tenantId: "t001",
      status: "created",
      amount: NumberDecimal("20.00"),
      createdAt: ISODate("2026-01-05T08:00:00.000Z")
    },
    { writeConcern: { w: 1 } }
  );

  printjson(result);
})();
~~~

On a healthy lab replica set, `order-w1-005` also quickly majority-commits and appears in subsequent majority reads. **That fact does not prove `w:1` carries equivalent guarantees to `w:"majority"`**. The difference lies in **the acknowledgment condition at response time**, not necessarily what is visible a few seconds later.

### 14.6. Reading replica set status

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  optimes: status.optimes
});

printjson(
  status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
);
~~~

If privileged, inspect fields such as **`lastCommittedOpTime`**, **`appliedOpTime`**, **`durableOpTime`**, plus PRIMARY/SECONDARY roles and lag. These are **point-in-time status snapshots**, not proof of how a specific request committed without timestamps/acknowledgment logs.

No need to run `rs.stepDown`, `rs.reconfig`, or shut down nodes. To learn rollbacks, use diagrams and thought exercises instead of breaking shared machines.

## 15. Node.js driver: configuring per operation and per workflow

### 15.1. Defaults on `MongoClient`

An application can set client-level defaults:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  readPreference: "primary",
  readConcern: { level: "majority" },
  writeConcern: {
    w: "majority",
    wtimeoutMS: 10000
  },
  retryWrites: true
});

await client.connect();

try {
  const orders = client
    .db("mongo_consistency_lab")
    .collection("lab_orders");

  const result = await orders.findOne({
    _id: "order-001",
    dataset: "consistency-v1"
  });

  console.log(result);
} finally {
  await client.close();
}
~~~

Setting defaults reduces the chance an API accidentally uses `w:1` or `local` when the product requires stronger policies. However, **not every operation needs the same read preference**: reports can specify `secondaryPreferred` at the operation/collection level while checkout keeps `primary`.

### 15.2. Dedicated policy for dashboards

~~~javascript
const dashboard = await orders.aggregate(
  [
    {
      $match: {
        dataset: "consistency-v1",
        tenantId: "t001"
      }
    },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    readPreference: "secondaryPreferred",
    readConcern: { level: "majority" },
    maxTimeMS: 3000
  }
).toArray();
~~~

This snippet assumes **`orders`** is a `MongoCollection` in a connected Node.js scope. For dashboards tolerating lag, `secondaryPreferred` can be sensible. **Do not promise the freshest values** just because `majority` is used.

### 15.3. Dedicated policy for write decisions

~~~javascript
const updated = await stock.updateOne(
  {
    _id: "sku-001",
    dataset: "consistency-v1",
    tenantId: "t001",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1, reserved: 1 }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeoutMS: 10000
    }
  }
);

if (updated.matchedCount !== 1) {
  throw new Error("Insufficient stock or invalid data");
}
~~~

Variable **`stock`** must be a valid `MongoCollection`. This is an atomic single-document update with a filter enforcing the invariant; it does not use read preference because **writes route to primary**. If constraints span multiple documents, design a transaction separately.

### 15.4. Defining policies at the right layer

MongoDB drivers support option inheritance/overrides across client, database, collection, and operation levels. When an API group applies specific options:

- Know which effective settings apply to each operation.
- Avoid conflicts between URI parameters and code.
- Test failover and timeouts on staging.
- Emit telemetry showing which `w`/`readConcern`/`readPreference` operations actually use.
- Never trust a code comment claiming "strong consistency" when runtime options are overridden.

Structure code with **business-named** helpers like `confirmedOrderWrite` or `staleTolerantDashboardRead`, rather than vague `"strong"`/`"weak"` enums that obscure exact guarantees.

## 16. Designing a policy matrix for a real system

Suppose an application has five critical flows. An initial policy matrix could be:

| Flow | Write concern | Read concern | Read preference | Notes |
| --- | --- | --- | --- | --- |
| Create confirmed Order | majority | majority when checking status | primary | `requestId`/idempotency; handle unknown outcome |
| Payment and Outbox commit | majority at transaction commit | snapshot in transaction | primary | Multi-document atomic; check status/unique |
| User just updated profile | majority if avoiding rollback | majority | primary or secondaryPreferred **in causal session** | Ensures read-your-writes within workflow scope |
| Total orders dashboard | Order source follows its own policy | majority if needing rollback-free data | secondaryPreferred | Allows stale data, attach `asOf`/lag |
| Display reference inventory | Reservation writes majority | local/majority per page needs | secondaryPreferred if lag tolerated | Checkout must use conditional write |
| Admin inspects critical control doc | majority when writing control | consider linearizable | primary | Strong current read, `maxTimeMS`, does not replace conditional update |
| Multi-collection reconciliation report | majority on source | appropriate snapshot | primary for transaction | Needs shared snapshot point, not two majority reads |

This is an **initial proposal**, not a mandatory preset for every organization. Final policies depend on:

- Acceptable data loss after the API reports success.
- Read/write latency SLAs.
- How much staleness is tolerable.
- Whether a session must read back its own just-created writes.
- Whether multiple documents must be mutually consistent.
- Topology, voting/data-bearing member counts, journaling, and sharding.
- Fault/quorum-loss tolerance and behavior when requested consistency cannot be met.

### 16.1. Classifying along two decision axes

~~~text
                        READ freshness
                   Can lag           Needs fresh/causal
WRITE       +------------------+------------------------+
durability  | Dashboard on     | Ordering; payments;    |
  high      | durable Orders   | just-updated profiles  |
            +------------------+------------------------+
  lower     | Replayable       | Temporary state within |
            | telemetry        | a session, but assess  |
            |                  | rollback risk          |
            +------------------+------------------------+
~~~

A common design mistake is collapsing both axes into a single "strong consistency" toggle. A dashboard may require **highly durable source writes** alongside **lag-tolerant reads**. An internal screen might read the ultra-fresh primary yet view `w:1` data still exposed to rollback.

## 17. Failures, timeouts, and handling uncertainty

### 17.1. Three states of a write

Applications should distinguish at least:

1. **Successful ACK at requested write concern**.
2. **Definitive failure before the write was applied**, if provable by driver/server.
3. **Unknown final outcome**: network error, write concern timeout, or unknown commit result.

The third category is critical. Never treat a timeout as "command did not run."

### 17.2. Retryable writes and idempotency

Drivers support **retryable writes** on replica sets/sharded clusters for eligible operations, retrying the same statement on transient errors within mechanism limits. However:

- Not every operation is retryable.
- A new HTTP request will not reuse the same statement identity.
- An `$inc` command re-sent as a new business action can deduct twice.
- Bulk workflows and external side effects require dedicated design.

For Orders/Payments, use **idempotency keys** and verify matching payloads. If multiple MongoDB steps must commit atomically, use transactions; for external side effects, use outbox/saga patterns.

### 17.3. When majority is unreachable

When quorum is lost or secondaries lag too far, the API can:

- Wait within its designed latency budget.
- Return a temporarily unconfirmed status allowing later reconciliation.
- Write to a durable queue (if an eligible system exists).
- Reject critical operations rather than silently lowering durability.

**Never silently downgrade from `majority` to `w:1` for financial transactions** just for faster responses, unless a formal business decision accepted the risk with explicit compensation logic.

### 17.4. Timeouts on linearizable/causal reads

Reads with strong requirements may wait for nodes to reach required state. Configure **`maxTimeMS`** or corresponding client deadlines; when unsatisfied, return an appropriate error rather than switching to a stale read while still labeling it strongly consistent.

For advisory screens, you may intentionally fall back to stale data **if contract permits** and the response indicates it. For decisions like debiting funds, never silently fall back.

## 18. Topology impacts: arbiters, hidden/delayed secondaries, and sharding

### 18.1. Arbiters

In a **Primary–Secondary–Arbiter (PSA)** replica set:

~~~text
P: data-bearing, votes
S: data-bearing, votes
A: arbiter, votes, HOLDS NO DATA COPY
~~~

Arbiters participate in elections but **do not replicate documents/oplogs like data-bearing members**. Never count an arbiter as a data copy when evaluating majority write concern. If S goes down, P cannot satisfy majority replication with only an arbiter, even though vote counts have specific nuances.

### 18.2. Hidden/delayed secondaries

A secondary may be excluded from normal reads or configured with a replication delay. This affects read preference eligibility, freshness, and recovery policies.

Do not assume every secondary is suited for reporting reads. When configuring tag sets/`secondaryPreferred`, verify members are read-eligible and understand delayed/hidden/priority roles.

### 18.3. Sharded clusters

With sharded MongoDB, a query may pass through `mongos` and multiple shards. Read concern, write concern, and read preference still apply, however:

- One operation may touch multiple shards at different replication progress points.
- Snapshots/cross-shard transactions carry extra overhead and operational rules.
- Read preference selects replica set members within each shard per policy.
- Check shard key/targeting to avoid unnecessary scatter-gather queries.
- A global freshness SLA cannot be inferred from a local `maxStalenessSeconds`.

Do not extrapolate a 3-node replica set example to assert every sharded query shares identical freshness/latency.

## 19. Monitoring to verify whether policies are working

### 19.1. Core metrics

| Metric | Question |
| --- | --- |
| **Write concern majority latency p50/p95/p99** | How long does durable acknowledgment take? |
| **Write concern timeouts/errors** | Are we losing quorum or are secondaries too slow? |
| **Primary stepdown/election events** | Are failovers happening frequently? |
| **`lastCommittedOpTime`** | How is the majority commit point advancing? |
| **Applied/durable `optime`** | How far has each member caught up? |
| **Replication lag per secondary** | Which secondaries frequently lag? |
| **Read preference distribution** | Which primaries/secondaries are actually serving reads? |
| **Read concern distribution** | Are any APIs unexpectedly using `local`? |
| **Causal read waits/timeouts** | Are nodes failing to keep up with causal history? |
| **Transaction aborts/write conflicts** | Is contention forcing retries? |
| **Application stale-data reports** | On which screens are users seeing stale UIs? |
| **Unknown write outcomes/reconciliation** | How many requests require state reconciliation? |

Segment measurements by **endpoint, query shape, and workflow**, not just cluster-wide totals.

### 19.2. Inspecting `rs.status()`

~~~javascript
const s = rs.status();

printjson({
  set: s.set,
  optimes: s.optimes,
  members: s.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
});
~~~

Field layouts vary across versions, yet milestones like **`lastCommittedOpTime`**, **`appliedOpTime`**, **`durableOpTime`**, and member states are key concepts to watch. They are **point-in-time snapshots**; they do not prove the commit outcome of a specific request without logs or acknowledgment records.

### 19.3. Do not track only average replication lag

With P/S1/S2, S2 might lag 20 seconds while P+S1 still satisfy majority. Conversely, if S1 disconnects, P cannot immediately satisfy majority writes using the lagging S2.

Thus, monitor **commit point, member health, and topology**, not merely an average lag number.

### 19.4. Recording report freshness

For stale-tolerant dashboards, include metadata:

~~~javascript
{
  "data": {
    "paidOrders": 1432
  },
  "asOf": "2026-11-14T03:00:00.000Z",
  "consistencyPolicy": "majority-committed, stale-tolerant"
}
~~~

This is an **application-designed response shape**, not automatically generated by MongoDB. **`asOf`** must come from an authoritative aggregation or source timestamp; never populate `"now"` if the figures were computed from stale data.

## 20. Design checklist before deploying an API to production

### 20.1. For write operations

Answer:

1. Is the data regenerable?
2. Once the API reports success, is rollback after failover acceptable?
3. Must a single document or multiple documents be updated atomically?
4. Are uniqueness, idempotency, and conditional updates in place?
5. On `wtimeout`/network timeout, is there a reconciliation endpoint/workflow?
6. What is the replica set's actual journal/majority configuration?
7. Is write concern inherited/overridden from client or collection settings?

### 20.2. For read operations

Answer:

1. Is reading non-majority-committed values acceptable?
2. How old can stale data be?
3. Must a session read back changes it just wrote?
4. Do multiple collections need the exact same snapshot?
5. Does a control document require strong real-time read semantics?
6. Can read preference fall back to another node type?
7. When no eligible node exists, does the app fail or intentionally degrade?

### 20.3. For operations

Answer:

1. How many data-bearing voting members and arbiters are in the replica set?
2. Do dashboards display `lastCommittedOpTime`/replication lag?
3. Are alerts configured for majority write timeouts and frequent elections?
4. Are effective concern settings logged per endpoint?
5. Are backups/PITR and recovery drills independent of replication?
6. Are lost responses, delayed secondaries, and failovers tested on staging?

A sound policy must be **measurable and enforceable during incidents**, not just written in architecture docs.

## 21. Common misconceptions

| Misconception | Reality | How to avoid |
| --- | --- | --- |
| Using primary guarantees reading rollback-free data | Primary + `local` can see non-majority-committed writes | Choose appropriate read/write concerns |
| Majority write means every secondary is updated | Only requires topology majority | Account for replication lag and read preference |
| Majority read on secondary is always latest | Secondary may be stale | Use causal session or primary read for read-your-writes |
| `w:1` guarantees data loss after failover | Write may reach majority after ACK | Distinguish unguaranteed from guaranteed rollback |
| `wtimeout` means write did not run | May have applied without meeting ACK threshold | Handle unknown outcomes and reconcile |
| `j:true` replaces `w:"majority"` | Local journal differs from replication majority | Address both durability and replication |
| Read concern `majority` creates a snapshot across two queries | Two queries can read at different points | Use transactions/snapshots when needed |
| Linearizable read prevents overselling | Read and update can still race | Use guarded atomic updates |
| `secondaryPreferred` always reads secondaries | Can fall back to primary | Know fallback semantics and observe node selection |
| `nearest` always picks the freshest data copy | `nearest` uses network latency/selection constraints | Never use it to promise freshness |
| `maxStalenessSeconds` is a hard freshness threshold | It is a node-selection estimate | Define explicit SLAs and `asOf` markers |
| Causal sessions span two HTTP requests automatically | Session/context does not auto-propagate across requests | Design workflow or read primary |
| Transactions automatically protect external side effects | Transactions cover only MongoDB ops in the session | Use outbox/saga for external systems |
| `snapshot` automatically equals `linearizable` | Snapshot is a view at one past/present milestone | Match semantics to problem |
| `majority` alone keeps balances non-negative | Replication does not enforce invariants | Use conditional updates/transactions |
| Having a replica set eliminates the need for backups | Replication replicates accidental deletes and logic bugs | Maintain independent backups/PITR |
| On quorum loss, just lower write concern for speed | Raises risk of acknowledged writes rolling back | Follow business fail/retry policy |
| All data needs the strongest read concern | Cost/availability penalties may be unnecessary | Use a matrix driven by SLA and risk |

## 22. Practice exercises and design scenarios

### Exercise 1 — Distinguishing the three mechanisms

An API configures **`writeConcern: majority`**, **`readConcern: local`**, and **`readPreference: secondaryPreferred`**. Explain what each option governs. When a user creates an Order with majority ACK yet a secondary GET misses it, why could that happen?

### Exercise 2 — Primary reads and rollbacks

Primary P has entry E103 (not yet majority-committed); S1/S2 are at E102. A client reads from primary with `readConcern: local` and sees E103. If P becomes isolated and S1/S2 elect a new primary, what can happen to E103? Does reading from primary prevent rollback?

### Exercise 3 — Majority does not mean latest

An Order write gets majority ACK on P+S1 while S2 lags. Is a GET using `readConcern: majority` from S2 guaranteed to see the Order? Compare with a GET on primary and a GET inside a causally consistent session.

### Exercise 4 — Checkout design

An API creates an Order and confirms to the user. Choose write concern, read concern, read preference, `requestId`/idempotency, and behavior on majority timeout. Why should you not return success with `w:1` if business policy forbids rollbacks?

### Exercise 5 — Recently updated profile

A user updates `displayName` and immediately opens their profile page. Write Node.js code using the **same session**, majority write concern, majority read concern, and `secondaryPreferred`. If the app splits these into two HTTP requests hitting two different instances, how must the architecture change?

### Exercise 6 — Inventory control

Two shoppers buy a SKU with exactly one item left. Explain why choosing `readConcern: linearizable` is **not enough**. Write an `updateOne` filtering `available >= 1` with matching `$inc` and `writeConcern: majority`. If reservation requests can be retried, what else is needed?

### Exercise 7 — Intentionally delayed dashboards

A dashboard accepts data delayed up to a product-defined SLA. Propose `secondaryPreferred`/`majority` reads and how to expose `asOf`. Why can you not claim `maxStalenessSeconds = 120` means figures are always accurate to the last 120 seconds?

### Exercise 8 — Multi-collection reporting

A report reads `Orders` at T1 and `Payments` at T2, both with `readConcern: majority`. Can temporary discrepancies appear? If a single shared snapshot is required, explain how to use transactions/snapshots and their trade-offs.

### Exercise 9 — Payment workflow

A payment updates Order, records Payment, and sends an email. Identify which operations belong inside the MongoDB transaction, commit write concern, transaction read concern, read preference, and how to handle email via an outbox.

### Exercise 10 — Write concern timeout

Primary wrote an Order; the client used `w:"majority"`, `wtimeout` 5 seconds, and received an error. List at least three possible subsequent outcome states. Design a status lookup endpoint by `requestId` to avoid creating duplicate Orders.

### Exercise 11 — Arbiters and quorum

A PSA replica set has one primary, one secondary, and one arbiter. The secondary fails. Can the arbiter help the primary satisfy majority write concern by holding data? Explain the difference between voting ballots and data copies.

### Exercise 12 — Causal consistency and monotonic reads

A user calls GET A then GET B, each hitting a different secondary. Can GET B return older data than GET A without a causal session? What does causal consistency guarantee, and which read/write concern conditions uphold causality per docs?

### Exercise 13 — Linearizable reads

An API inspects a single control document, needing strong real-time guarantees across primary transitions. Which read concern/read preference should it pick? Why is `maxTimeMS` needed, and why are guarded writes still required if the API later modifies the document?

### Exercise 14 — Read preference fallback

Compare **`primaryPreferred`** and **`secondaryPreferred`** when a node becomes unavailable. For an API rejecting stale data, why can falling back to a secondary violate its contract even though the read returns HTTP 200?

### Exercise 15 — Running the lab script

Run the seed script, then insert **`order-majority-004`** with `w:"majority"` and **`order-w1-005`** with `w:1`. Read back with `readConcern: majority` on a healthy replica set. If both appear, what does that prove—and what does it **not** prove—about rollback protection?

### Exercise 16 — Policy matrix

Build a policy matrix for three endpoints: **`POST /orders`**, **`GET /profile` after update**, and **`GET /analytics/daily`**. Pick options and explain latency, rollback exposure, stale reads, and error handling.

### Exercise 17 — Network failure after `$inc`

A balance-decrement command using `$inc` executes on the server, but the response drops. If the API sends a new request with a similar `$inc`, what is the risk? Distinguish driver-level retryable writes from business-layer idempotency keys.

### Exercise 18 — Production incident investigation

After an election, several customers report "I saw my Order earlier, and now it's gone." Outline a non-destructive investigation sequence: verifying filters/tenant, write concern ACKs, `readConcern`/`readPreference`, election/rollback logs, sessions, replication lag, audits, and reconciliation.

### Exercise 19 — Cost and availability

As secondary lag rises, compare the impact on `w:"majority"` writes, causal secondary reads, and dashboard reads. Which workflows should fail when guarantees cannot be met, and which can serve stale data if clearly badged?

### Exercise 20 — Custom policy design

A company has three data tiers: **Payments** (cannot tolerate normal rollbacks), **Product view counts** (can be re-aggregated), and **Admin feature flags** (require decisions consistent with fresh state). Choose a policy for each and explain why one preset cannot fit all three.

## 23. MongoDB references

- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/).
- MongoDB Manual — [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/).
- MongoDB Manual — [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/).
- MongoDB Manual — [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/).
- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Node.js Driver — [Read Preference](https://www.mongodb.com/docs/drivers/node/current/crud/configure/#read-preference).
- MongoDB Node.js Driver — [Client-Side Sessions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/).

**Conclusion:** Do not select read concern, write concern, and read preference by ranking them along a single "weak → strong" scale. **Write concern** governs acknowledgment conditions and write protection, **read concern** governs readable data properties, and **read preference** selects serving nodes. For critical confirmed data, use **`w:"majority"`**, timeout handling, and idempotency. For **read-your-writes**, use primary reads or **causally consistent sessions** with proper majority settings. For lag-tolerant reports, reading secondaries is fine when freshness is exposed. When invariants span multiple documents, use properly scoped **transactions/snapshots**, while contended single-document decisions require **conditional atomic updates**. A strong consistency policy aligns **business contracts, topology, and verifiable incident recovery**.
