# Deployment Requirements for Transactions on Replica Sets and Sharded Clusters in MongoDB

## 1. What Problem Do Multi-Document Transactions Solve?

MongoDB guarantees **single-document atomicity** for an individual write operation. If information can live in the same document, updating with `$set`, `$inc`, `$push`, or an update pipeline is usually enough to keep related fields consistent.

However, some business workflows must modify **multiple documents, collections, databases, or shards** on an **all-or-nothing** basis:

- Money transfers: debit account A, credit account B, record transfer history.
- Order placement: create order, reserve inventory, store an internal payment status record.
- Ownership transfer: update two entities and an audit record.
- Modifying multiple coupled aggregates that cannot be left in a half-completed state.

A **multi-document transaction** lets you group eligible operations into a single ACID unit. If the commit succeeds, the transaction's changes are accepted as a set; if it aborts, none of the transaction's changes are retained.

```text
Before transaction
  Account A: 1000
  Account B:  500

Transfer 200 transaction
  1. A -= 200
  2. B += 200
  3. Insert transfer log

Commit succeeds:
  A = 800, B = 700, log present

Abort:
  A = 1000, B = 500, no log
```

Yet you cannot simply write `session.startTransaction()` and expect transactions to work on every MongoDB server. **Deployment type**, version and feature compatibility, topology, sessions, read/write concern, allowed operations, and runtime limits all govern deployability.

> **Key takeaway:** MongoDB multi-document transactions run on a **properly configured replica set or sharded cluster**, not on a standalone `mongod`. On sharded clusters, transactions can span multiple shards, but at higher cost and with tighter constraints.

This lesson focuses on **deployment prerequisites** and how to verify those prerequisites in real systems, rather than merely showing start/commit syntax.

---

## 2. Support Matrix by Architecture

| Environment | Multi-Document Transactions | Things to Note |
| --- | --- | --- |
| Standalone `mongod` | **Not supported** | Even if all collections reside on the same server, it is not a replica set. |
| **Single-node replica set** for development | **Usable for testing** | No high availability; does not represent production failover behavior. |
| Multi-node replica set | **Supported** | Must have proper topology, session, read/write concern, and runtime settings. |
| Sharded cluster with valid shards | **Supported** | Accessed through `mongos`; can run across one or multiple shards. |
| A shard replica set within a sharded cluster | Eligible to participate in transactions | Application clients must use the proper sharded router/topology. |
| Replica set with an arbiter | Certain transactions can run | Special restrictions apply to multi-shard writes or shard key updates. |
| Sharded cluster with a shard having `writeConcernMajorityJournalDefault: false` | **Transactions not supported** | The shard's durability/majority configuration does not meet prerequisites. |
| MongoDB Atlas or managed MongoDB | Depends on cluster/tier type and server | Check service docs, topology, version, and permissions instead of calling `rs.initiate()`. |

A **single-node replica set** is useful for local development with transactions, but do not treat it as a “production equivalent of a three-node replica set”. It lacks an independent majority, real failover, and distributed commit behavior across multiple shards.

### 2.1. Historical Support Milestones

| Form | MongoDB Version Introduced | Documented Minimum FCV |
| --- | --- | --- |
| Multi-document transactions on replica sets | **4.0** | **4.0** |
| Multi-document transactions on sharded clusters | **4.2** | **4.2** |

FCV stands for **featureCompatibilityVersion**. It controls whether deployment compatibility behaviors/features are enabled, which is especially relevant during rolling upgrades.

On currently supported MongoDB versions, transactions are a standard feature, yet **the actual environment must still be properly configured**. Never just check `mongod --version` while ignoring FCV and topology.

---

## 3. Checking Server Version and FCV

Before configuring application transactions, verify:

```javascript
db.version();
```

To check FCV if your account has privileges:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

On a replica set or sharded cluster undergoing a staged upgrade, confirm that **the entire deployment** is compatible, not just whichever single node you happen to be connected to.

### 3.1. Why Does FCV Matter?

For example, a replica set may have upgraded binaries while FCV remains at the older level to preserve upgrade rollback capability. If the application relies on a feature requiring a higher FCV, errors can occur even though the server binary appears new enough.

In transaction documentation, the historical minimum thresholds are:

```text
Replica set     : FCV >= 4.0
Sharded cluster : FCV >= 4.2
```

When operating modern MongoDB, check the **compatibility matrix for your specific server release**; never manually pin FCV down to 4.0/4.2. The goal of this table is to understand historical minimums, not to recommend downgrading.

### 3.2. FCV Is Not the Only Prerequisite

Even when version/FCV is satisfied:

- The server might still be **standalone**.
- A sharded cluster might contain a shard with unsupported journaling/majority settings.
- The client might be connecting **directly to a shard** instead of `mongos`.
- The application might misuse sessions or read preferences.
- Transactions might abort due to lifetime limits, locks, DDL, or write conflicts.

That is why a comprehensive deployment checklist is necessary.

---

## 4. Why Doesn't a Standalone `mongod` Run Multi-Document Transactions?

A server started without a replica set topology is standalone:

```text
Application
    |
    v
standalone mongod
    |
    +-- collection A
    +-- collection B
```

It can execute multiple write operations, but **does not accept session-based multi-document transactions like a replica set**. The error typically seen when running driver transactions against standalone relates to `Transaction numbers are only allowed on a replica set member or mongos`.

**Do not confuse two concepts:**

1. `updateOne` on a single document in standalone has document-level atomicity.
2. `startTransaction` followed by modifying multiple documents is a multi-document transaction and requires a supported deployment.

### 4.1. Detecting a Standalone Environment

Connect with `mongosh`:

```javascript
db.hello();
```

On a replica set, the response includes set name and member role details. On standalone, there is no corresponding replica set topology.

You can inspect replica set configuration in a managed/self-hosted setup:

```javascript
rs.status();
rs.conf();
```

On standalone, these replica set commands do not work as they do on a replica set member; this signals that the deployment must be reconfigured.

### 4.2. Local Development: Using a Single-Node Replica Set

Conceptual example with a local **non-production** `mongod`:

```shell
mongod --replSet rsDev --dbpath /data/mongodb/rsDev --port 27017 --bind_ip 127.0.0.1
```

Once the server is running, connect via `mongosh` and initiate:

```javascript
rs.initiate({
  _id: "rsDev",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Wait for the member to become primary:

```javascript
db.hello();
rs.status();
```

Application:

```text
mongodb://localhost:27017/?replicaSet=rsDev
```

If using Docker or multi-namespace networks, hostnames in `rs.initiate()` must be **resolvable from both clients and peer members**. `localhost` inside one container does not automatically point to MongoDB in another container.

**The example above omits production security configuration.** Real environments require authentication, authorization, TLS, internal authentication, proper hostnames, and secrets management. Never spin up an unsecured public-facing replica set just to bypass transaction errors.

---

## 5. What Components Does a Production Replica Set Need?

A basic topology has three data-bearing members:

```text
             Replica set rsOrders

            +---------------------+
            | PRIMARY   db1       |
            | SECONDARY db2       |
            | SECONDARY db3       |
            +---------------------+
                      ^
                      |
              MongoDB Driver
                      |
                Application
```

Typically, the application connects with a URI listing the hosts and set name:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/
  ?replicaSet=rsOrders
```

The URI is wrapped across lines for readability; an actual URI must be a single continuous string. Add TLS/auth according to your environment.

### 5.1. Operational Conditions to Verify

1. The replica set is initialized and has a valid **primary**.
2. Members have connectivity, healthy replication, and consistent configuration.
3. Version/FCV supports transactions.
4. Servers support sessions and required storage engine/replication behavior.
5. Selected write concern can be acknowledged within the topology.
6. The database user has necessary CRUD privileges on collections involved in the transaction.
7. The application uses a MongoDB driver supporting sessions/transactions.
8. Transaction duration, resources, locking, and the oplog window are monitored.
9. Collections/indexes are pre-created to avoid DDL inside transactions.
10. The team has a strategy for handling failover and safe retries.

### 5.2. Replica Sets Do Not Make Transactions Free

Every transaction generally incurs more overhead than a single-document atomic update:

- The server maintains snapshots and transaction state.
- Multiple documents may require appropriate locks or produce write conflicts.
- Commits must satisfy write concern conditions.
- Long-running transactions pin snapshots and increase cache/history pressure.
- During primary stepdowns or connection resets, the application must handle transient errors.

The goal is not “enable transactions for every write”, but to protect **cross-document invariants that genuinely require atomicity**.

---

## 6. Sharded Cluster Architecture and Where Transactions Run

A sharded cluster typically consists of:

- **`mongos`:** router receiving commands from applications and routing them to shards.
- **Config server replica set (CSRS):** stores sharded cluster metadata.
- **Shards:** each shard is typically a **replica set** storing a subset of a collection's data.
- **Shard key:** determines how documents are distributed/routed across shards.

```text
                         Application
                              |
                              v
                            mongos
                         /    |    \
                        /     |     \
              Shard 1 RS   Shard 2 RS   Shard 3 RS
               P + S + S    P + S + S    P + S + S
                        \      |      /
                         Config Server RS
```

**Applications connect to `mongos`, never directly to a shard's `mongod`, when running cluster-wide transactions.** The router holds distribution metadata and coordinates operations across participating shards.

### 6.1. Single-Shard Transactions

A transaction touching data on **only one shard**:

```text
Client -> mongos -> Shard 1 RS
                       |
                     Commit
```

Overhead is typically close to a replica-set transaction, plus routing through `mongos`.

For example, an `orders` collection sharded by `tenantId`. If all operations in a transaction filter on the same `tenantId` and all touched data resides on the same shard, the transaction may involve only one shard.

This **does not happen automatically** just because you use the same database. You must know each collection's shard key and how data is distributed.

### 6.2. Multi-Shard Transactions

A transaction touching data across **multiple shards**:

```text
                    mongos
                   /     \
                  v       v
             Shard 1   Shard 2
                 \       /
                  \     /
          Transaction coordination
                  |
                  v
          Consistent commit/abort
```

Multi-shard transactions add a **distributed commit coordination** phase using a **two-phase commit** protocol to ensure all participating shards reach the same commit/abort decision.

Consequences:

- Additional network round trips between router, coordinator, and shards.
- Commits can be slower than single-shard transactions.
- Commit latency is affected by slow shards or network issues.
- Retries and unknown commit results must be handled properly.
- You cannot treat shards as independent standalone MongoDB instances and commit sequentially from the client.

According to MongoDB documentation, **transactions targeting a single shard can achieve performance comparable to replica-set transactions**, whereas multi-shard transactions incur higher overhead.

---

## 7. Special Conditions for Sharded Clusters

To deploy multi-document transactions on a sharded cluster, verify at least the following conditions:

| Condition | Why It Is Needed |
| --- | --- |
| MongoDB/FCV supports sharded transactions | Historical support began in MongoDB/FCV 4.2. |
| Applications connect through `mongos` | The router holds metadata and coordinates cross-shard transactions. |
| Shards are valid replica sets | Writes, replication, and commits rely on capable members. |
| `writeConcernMajorityJournalDefault` is not `false` on any shard | The cluster cannot run transactions if a shard fails this condition. |
| Multi-shard transactions do not touch shards with an arbiter | Write transactions spanning multiple shards error/abort if an operation touches a shard replica set containing an arbiter. |
| Shard keys/indexes satisfy CRUD and uniqueness | Targeting and global uniqueness have specific constraints in sharding. |
| Target write collections are pre-created | New collections cannot be created inside cross-shard write transactions. |
| Appropriate monitoring and retry/timeout handling | Chunk migrations, DDL, lock conflicts, and failovers can abort transactions. |

### 7.1. `writeConcernMajorityJournalDefault`

A specific restriction: MongoDB **does not allow transactions on a sharded cluster if any shard has `writeConcernMajorityJournalDefault` set to `false`**.

For instance, documentation cites cases where a shard has a voting member using the **in-memory storage engine**, causing this setting not to meet the requirement.

Do not conclude “every replica set must have every member on WiredTiger” solely from this rule. What matters is the **actual deployment configuration**, particularly journaling and majority commit behavior on each shard.

Certain parts of a sharded transaction commit use `{w: "majority", j: true}` even when the transaction-level write concern is configured differently. That is why lowering write concern to `w: 1` **does not eliminate all durability requirements during cross-shard commits**.

### 7.2. Arbiters Impose Special Constraints

An arbiter only votes and holds no data. Per MongoDB rules:

- Transactions that update a **shard key** cannot be used if the replica set has an arbiter.
- **Multi-shard write transactions** will error and abort if any operation in the transaction reads from or writes to a shard that contains an arbiter.

Never design a multi-shard transaction expecting an arbiter to “acknowledge part of the data”, because an arbiter holds no data copy.

### 7.3. Individual Shard Resources Still Matter

Even with valid configuration, a slow shard, insufficient disk IOPS, or heavy replication lag can cause transactions to take too long, time out, or abort. Monitor both the router and the actual shards participating in transactions.

---

## 8. Sessions Are Mandatory

A MongoDB multi-document transaction is bound to a **logical session**. The driver manages session and transaction metadata, such as `lsid` and transaction numbers at the protocol level.

In Java:

```java
try (ClientSession session = mongoClient.startSession()) {
    session.startTransaction();

    collectionA.insertOne(session, documentA);
    collectionB.updateOne(
        session,
        Filters.eq("_id", someId),
        Updates.set("status", "PAID")
    );

    session.commitTransaction();
}
```

This is only an illustrative skeleton; error handling, aborts, and timeouts are covered in detail in later sections.

### 8.1. Every Operation Must Receive the Right Session

Wrong:

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(
    Filters.eq("_id", sku),
    Updates.inc("available", -1)
); // Session omitted: runs outside the transaction.

session.commitTransaction();
```

Right:

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(
    session,
    Filters.eq("_id", sku),
    Updates.inc("available", -1)
);

session.commitTransaction();
```

If an operation omits the matching session, it **does not belong to the transaction**. The result can be an inconsistent state even though `commitTransaction()` reports success.

### 8.2. Only One Active Transaction per Session

Never open two concurrent transactions on the same `ClientSession`. Furthermore, a driver session is tied to the exact `MongoClient` that created it; never pass a session from client A to a collection obtained from client B.

### 8.3. Do Not Run Parallel Operations in the Same Transaction

The Java driver does not support parallel operations within a single transaction. Do not pass the same session into two `CompletableFuture` tasks or multiple threads concurrently to “speed it up”.

```text
Correct:
  read -> update A -> update B -> insert audit -> commit

Inappropriate:
  session -> async update A
          -> async update B (simultaneously)
          -> commit without deterministic ordering
```

If you need parallel processing for workloads that do not require a shared transaction, design independent operations properly without sharing a single session.

---

## 9. Transaction Lifecycle

```text
startSession()
      |
      v
startTransaction()
      |
      v
CRUD operation 1
      |
      v
CRUD operation 2
      |
      v
Check invariants
      |
      +-----------------+
      |                 |
   Success           Error / timeout
      |                 |
      v                 v
commitTransaction()  abortTransaction()
      |                 |
      v                 v
   COMMITTED           ABORTED
      |
      v
close session
```

A transaction has three key practical outcomes:

1. **Confirmed commit success:** the caller is notified that the transaction committed per the write concern.
2. **Abort:** the transaction's changes do not take durable effect.
3. **Unknown commit result (`UnknownTransactionCommitResult`):** the client does not know for sure whether the commit succeeded. **Never assume the transaction aborted**.

The third state is especially critical when the network drops right during commit. The driver may need to retry **the commit operation**, rather than re-running the entire business workflow.

---

## 10. Read Preference Inside Transactions

MongoDB requires **transactions that contain read operations** to use read preference **`primary`**. Operations within a transaction must route to the appropriate replica set member.

Explicit configuration example:

```java
TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .build();
```

**Do not use `secondaryPreferred()` just because other read-only queries in the app read from secondaries.** Inside a transaction that reads data to make update decisions, the proper read preference is required.

### 10.1. Where Is Read Preference Configured?

MongoDB drivers can inherit read preference from:

1. Transaction options.
2. Session.
3. `MongoClient` settings.

To prevent a global client configured with `secondaryPreferred()` from accidentally passing an invalid setting into a transaction, **explicitly set `ReadPreference.primary()` on the transaction options**.

### 10.2. Do Not Use `readPreference=secondary` to “Offload the Primary”

Reading from secondaries inside a transaction is not a supported optimization for transactions containing read operations. If a report only needs eventual consistency, run the query outside a transaction on secondaries rather than forcing it into an ACID transaction.

---

## 11. Read Concern for Transactions

MongoDB supports three main read concern levels for transactions: `"local"`, `"majority"`, and `"snapshot"`.

| Read Concern | Key Semantics | Special Notes for Sharded Clusters |
| --- | --- | --- |
| `"local"` | Reads data from the local node's view, which may roll back if not majority-committed. | Does not guarantee a consistent snapshot across multiple shards. |
| `"majority"` | Returns majority-committed data when committed with majority under MongoDB rules. | Does not guarantee a single synchronized snapshot across shards. |
| `"snapshot"` | Reads from a consistent snapshot per contract, and with majority commit guarantees majority-committed data. | **Required level when a synchronized snapshot across multiple shards is needed.** |

### 11.1. Why Is `"snapshot"` Usually Chosen?

In a money transfer workflow, you do not want to read account A at one point in time and account B at an inconsistent point when data may span different shards.

Candidate configuration:

```java
TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

`ReadConcern.SNAPSHOT` in a sharded cluster transaction provides a data snapshot synchronized across shards. A `"majority"` read concern **is not equivalent** to such a synchronized snapshot.

### 11.2. Snapshot and Majority Write Concern Are Coupled

MongoDB documentation explicitly states that the guarantee of reading a snapshot of **majority-committed data** depends on the transaction **committing with write concern `"majority"`**.

If committed with `w: 1`, read concern `"snapshot"` **does not guarantee** that the read documents are majority-committed under those semantics.

Therefore, do not assume writing `readConcern: "snapshot"` alone provides full durability guarantees regardless of commit configuration.

### 11.3. Data Is Not Always the “Latest at the Exact Present Moment”

Snapshot isolation stabilizes the read view within a transaction, but a snapshot may **not reflect newer updates from outside**. Separate two concepts:

- **Snapshot consistency:** reads inside the transaction observe data from a mutually consistent point of view.
- **Freshness:** whether the view reflects the very latest commit at request time.

For business rules that must prevent concurrent updates from invalidating a decision, combine conditional writes, unique constraints, and write conflict handling; do not treat snapshot reads alone as a global lock.

---

## 12. Write Concern Must Be Set at the Transaction Level

Transactions use a **transaction-level write concern at commit time**. Individual write operations inside a transaction **must not specify their own write concern**.

Wrong:

```javascript
// Do not set per-operation write concern inside a transaction.
orders.insertOne(
  { _id: "O100", status: "NEW" },
  { writeConcern: { w: 1 } }
);
```

The shell snippet above merely illustrates an invalid configuration inside a transaction; depending on driver/shell APIs, you must also pass the session to attach the command to the transaction.

Conceptually correct:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: "primary"
});

// Execute CRUD operations using the session; do not specify
// individual write concerns per CRUD call.
```

### 12.1. Difference Between `w: 1` and `"majority"`

| Commit Write Concern | What Is Awaited | Things to Note |
| --- | --- | --- |
| `w: 1` | Primary acknowledgment per `w=1` semantics. | Transaction can be rolled back upon failover under documented MongoDB conditions. |
| `w: "majority"` | Majority acknowledgment from eligible voting data-bearing members. | Higher durability, potential latency increase, depends on replication health. |

**Never assume `commitTransaction()` returning success with `w: 1` means the data is already persisted on a majority of the replica set.**

### 12.2. Default Write Concern Depends on Version and Topology

In modern MongoDB, defaults are defined by server version, and topologies with arbiters can alter the implicit default. To eliminate ambiguity, financial or critical workloads should **explicitly set write concern** matching system requirements.

Never assume every cluster defaults to `"majority"` just because code omits `w`.

### 12.3. Sharded Cluster Commits Have Specific Majority/Journal Steps

For multi-shard transactions, certain commit coordination steps use `{w: "majority", j: true}` regardless of the transaction-level write concern. This explains why distributed commits cannot be reduced to the sum of two simple write commands.

---

## 13. Configuring Transaction Options in `mongosh`

The transfer example is demonstrated on an existing `accounts` collection where two accounts store balances in **minor currency units**:

```javascript
// Prepare data outside the transaction on a test database:
db.accounts.insertMany([
  { _id: "A", balanceMinor: NumberLong("100000") },
  { _id: "B", balanceMinor: NumberLong("50000") }
]);
```

Transaction:

```javascript
const session = db.getMongo().startSession();

try {
  const txnDb = session.getDatabase(db.getName());
  const accounts = txnDb.getCollection("accounts");
  const transfers = txnDb.getCollection("transfers");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const debit = accounts.updateOne(
    {
      _id: "A",
      balanceMinor: { $gte: NumberLong("20000") }
    },
    {
      $inc: { balanceMinor: NumberLong("-20000") }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Insufficient funds or missing account A");
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balanceMinor: NumberLong("20000") } }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Account B does not exist");
  }

  transfers.insertOne({
    _id: "TRANSFER-EXAMPLE-1",
    from: "A",
    to: "B",
    amountMinor: NumberLong("20000")
  });

  session.commitTransaction();
} catch (err) {
  if (session.inTransaction()) {
    session.abortTransaction();
  }
  throw err;
} finally {
  session.endSession();
}
```

**Conditions for this example to run properly:**

- Connected to a replica set or `mongos`, not standalone.
- Both `accounts` and `transfers` collections are pre-created, especially if the transaction can touch multiple shards.
- All operations use collection handles obtained from `session.getDatabase()`.
- Accounts A and B already exist with compatible balance types.
- No prior run inserted the same transfer `_id`; duplicate `_id` causes an error.
- Do not use this illustrative script as a production payment gateway; it lacks API idempotency, input validation, audit policies, and caller handling for unknown commit results.

In real applications, use the **callback API** or a controlled retry loop instead of assuming a single start/commit always succeeds. The Java section below shows driver-supported transaction management.

### 13.1. Verifying After Commit

```javascript
db.accounts.find(
  { _id: { $in: ["A", "B"] } }
).sort({ _id: 1 });

db.transfers.findOne({
  _id: "TRANSFER-EXAMPLE-1"
});
```

Never try to “test atomicity” by killing connections or dropping databases on production. Use a dedicated integration test suite covering aborts, conflicts, and failovers.

---

## 14. Preparing Collections and Indexes: DDL Restrictions in Transactions

MongoDB permits certain collection/index creation operations **inside transactions** under limited conditions, but this does not mean all DDL is supported.

### 14.1. Conditionally Permitted Operations

Creating collections or indexes inside a transaction is allowed if it is **not a cross-shard write transaction**.

For index creation:

- Only allowed on a **non-existent collection** (created within the transaction) or a **new, empty collection created earlier in the same transaction**.
- Creating an already-existing index may succeed as a no-op existence check per API rules.
- **Explicit collection/index creation requires transaction read concern `"local"`**.

That is incompatible with choosing `"snapshot"` everywhere if the transaction also performs explicit DDL.

### 14.2. New Collections Cannot Be Created in Cross-Shard Write Transactions

Example:

```text
Shard A:
  write to existing collection orders.

Shard B:
  insert into non-existent collection auditLogs,
  causing implicit collection creation.

Both occur inside the same transaction.
```

MongoDB **disallows** creating collections like this inside a cross-shard write transaction. The transaction will fail.

**Deployment recommendation:** run **schema migrations/index creation before the application starts transactions**, confirming collections/indexes exist and sharding metadata is ready.

### 14.3. Concurrent DDL Can Abort Transactions

While a transaction holds collection resources, an operator runs `createIndex`/`renameCollection`/`drop` concurrently. DDL may wait on the transaction, and new transactions may block behind the pending DDL and hit lock timeouts.

In sharded clusters, chunk migrations and DDL also have critical sections. Depending on interleaving, a transaction can **abort on commit** because partitioning metadata changed.

Do not catch all DDL/migration errors and retry indefinitely. Plan change windows, retry budgets, and monitor lock waits.

---

## 15. Restricted or Disallowed Operations

Not every MongoDB command can run inside a transaction.

| Operation / Category | Condition or Restriction |
| --- | --- |
| Standard CRUD on supported collections | Allowed with proper session/privileges/concerns. |
| `createCollection`, `createIndex` | Only in supported collection/index creation scenarios, and explicit DDL requires `readConcern: "local"`. |
| Creating collections in cross-shard write transactions | **Disallowed**. |
| `listCollections`, `listIndexes` | Not allowed in transactions. |
| `getParameter`, `createUser`, and many administrative commands | Not allowed in transactions. |
| `explain()` | Cannot be run as an operation inside a transaction. |
| `$out`, `$merge` in aggregation | Not allowed in transactions. |
| Writes to **capped collections** | Disallowed. |
| Reading capped collections with snapshot read concern | Version-restricted; unsupported in MongoDB 5.0+. |
| Reads/writes to collections in `config`, `admin`, `local` databases | Not allowed in transactions. |
| Writes to `system.*` collections | Not allowed in transactions. |
| `getMore` on a cursor created outside a transaction, or vice versa | Cannot mix transaction boundaries. |
| `$graphLookup` targeting a sharded collection | Restricted inside transactions. |
| Parallel operations sharing one session/transaction | Unsupported by drivers. |

### 15.1. `count` and `distinct` Commands

Some legacy commands/helpers are restricted inside transactions. When counting with conditions, you can use aggregation such as:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
```

To retrieve distinct values, you can use `$group` + `$addToSet` with appropriate semantics. Always attach the session and avoid unsupported stages inside transactions.

### 15.2. Run Migrations Before Transactions

If a unique index is needed to protect `transferId` or a business key, create it **before handling production transactions**. Do not wait until the first request and run DDL inside a transaction, as that invites lock contention, read concern incompatibilities, and cross-shard restrictions.

---

## 16. Shard Keys and How to Avoid Multi-Shard Transactions

Transactions spanning multiple shards can be necessary, but should be avoided when a sound data model allows grouping related operations onto the **same shard**.

For example, a collection sharded by:

```javascript
sh.shardCollection(
  "shop.orders",
  { tenantId: 1, orderId: 1 }
);
```

This configuration example illustrates the key. Choosing an actual shard key requires analyzing cardinality, data distribution, targeting, and indexes. Never run `sh.shardCollection` without preparing the collection, indexes, and topology.

### 16.1. Queries Including the Shard Key Target Better

```javascript
db.orders.findOne({
  tenantId: "T100",
  orderId: "O900"
});
```

When an appropriate shard key is present, `mongos` can route the operation directly to the relevant shard instead of broadcasting widely.

If a filter only specifies:

```javascript
db.orders.findOne({
  status: "PENDING"
});
```

the router may have to send the operation to multiple shards, increasing participant count and transaction cost.

### 16.2. Shard Key Is Only Part of Transaction Design

If collection A is sharded by `tenantId` and collection B is sharded by `customerId`, a workflow updating both A and B is **not guaranteed** to land on the same shard. To achieve a single-shard transaction, verify data placement across all touched collections, not just whether one filter includes `tenantId`.

### 16.3. Unique Indexes in Sharded Collections

MongoDB has cross-shard uniqueness limitations. Generally, a unique index on a sharded collection must include the **full shard key as a prefix** under supported rules.

Example:

```javascript
// If the collection is sharded by tenantId:
db.transfers.createIndex(
  { tenantId: 1, transferId: 1 },
  { unique: true }
);
```

This constraint enforces uniqueness on the `(tenantId, transferId)` pair per the model. It **does not guarantee global `transferId` uniqueness** if different tenants use the same `transferId`.

Before placing an idempotency key in a sharded collection, define the required uniqueness scope: system-wide, per-tenant, per-customer, or per-API request. Transactions **do not automatically add a global unique constraint** on fields outside the shard key.

---

## 17. Can Transactions Change a Shard Key?

On supported MongoDB versions, updating a shard key has specific prerequisites and is typically done via appropriate document-identifying operations inside a transaction or retryable write depending on the case.

Key distinctions:

- **Updating regular fields** of a sharded document is not the same as **changing a shard key**, which may move the document to another shard.
- Changing a shard key has specific routing, filter, and atomicity requirements.
- **Changing a shard key inside a transaction is disallowed if an involved replica set has an arbiter**, per MongoDB restrictions.
- If the mutation moves the document across shards, cost and retry/error likelihood can increase.

Do not treat modifying a shard key as an ordinary `$set` update. For workflows that change tenants/partitions or relocate data, redesign routing and verify documentation for your exact version first.

---

## 18. Transaction Lifetime

Per MongoDB documentation, **by default a transaction must complete in under one minute**. The server parameter:

```text
transactionLifetimeLimitSeconds
```

controls this time limit. Transactions exceeding the limit are considered expired and can be aborted by periodic cleanup.

### 18.1. Why Are Long Transactions Harmful?

The longer a transaction pins snapshots and associated state, the more it can:

- Increase memory/cache pressure.
- Pin historical data needed for snapshots.
- Hold locks/resources for extended periods.
- Increase conflicts with concurrent writes or DDL.
- Slow down chunk migrations in sharded clusters.
- Increase timeout/abort risk during failovers.

Never place external HTTP service calls, waiting for user confirmation, sending emails, or processing large files **in the middle** of a transaction if they keep the transaction open for long.

### 18.2. Adjusting Lifetime in a Sharded Cluster

If you must adjust `transactionLifetimeLimitSeconds` in a sharded cluster, MongoDB requires setting it on **all members of the shard replica sets** per documentation guidelines.

Raising timeouts does not make transactions faster or safer. Prioritize narrowing transaction scope, optimizing indexes, eliminating network calls, and splitting separable business steps.

### 18.3. `maxTimeMS`, `wtimeout`, and Transaction Lifetime Differ

- **Transaction lifetime:** limits how long a transaction can stay alive; expiration can abort it.
- **`maxTimeMS` on `commitTransaction`:** bounds commit execution time per server behavior; on sharded clusters, transaction lifetime still applies.
- **Write concern timeout (`wtimeout`):** bounds waiting for write concern acknowledgment; **a timeout does not prove data rolled back**.

Never assume every timeout error means “nothing was written”. Especially at commit time, state may be unknown and must be handled by error label.

---

## 19. Lock Waits, Write Conflicts, and Transaction Resources

### 19.1. Default Lock Request Timeout

Per MongoDB documentation, transactions wait **approximately 5 ms** by default to acquire needed locks. If locks cannot be acquired within that threshold, the transaction can abort.

Related parameter:

```text
maxTransactionLockRequestTimeoutMillis
```

Do not arbitrarily raise this threshold to several minutes to “make errors go away”. Doing so may convert fast aborts into queued waiting requests, making contention harder to diagnose.

### 19.2. Write Conflicts

Two transactions modifying the same document, or a transaction encountering a concurrent outside write, can trigger a **write conflict**. MongoDB may abort one transaction to preserve consistency.

```text
Transaction T1: reads account A
Transaction T2: updates account A and commits
Transaction T1: attempts to write account A
        |
        +--> May hit write conflict / abort
```

The application needs a mechanism to **retry the entire transaction on eligible transient errors**; do not retry only the final command after the transaction has aborted.

### 19.3. Oversized Transactions and Cache Pressure

A transaction modifying vast numbers of documents, returning huge cursors, or accumulating excessive intermediate state increases cache/history pressure and triggers resource errors.

Do not assume a 16 MiB cap applies to **the entire transaction** just because individual BSON documents have that limit. BSON document limits and transaction/oplog/cache limits are distinct rules that can also change across MongoDB versions.

Specifically, starting in MongoDB 6.2, `TransactionTooLargeForCache` is not retried by the server as a normal transient error. You must **shrink the transaction scope** instead of looping endlessly on an oversized operation.

### 19.4. DDL and Chunk Migrations

DDL can wait for active transactions to finish; new transactions can wait behind pending DDL and expire. In sharded clusters, chunk migrations enter a critical section; if a migration alters placement during a transaction, the transaction may fail at commit.

These errors typically require proper retries, coordinated deployments, and shorter transaction durations. Never disable the balancer cluster-wide indefinitely just to avoid conflicts.

---

## 20. Two-Phase Commit in Multi-Shard Transactions

When a transaction writes across multiple shards, MongoDB uses a distributed coordination mechanism to bring participants to a consistent commit/abort decision.

Conceptual diagram:

```text
App
 |
 v
mongos / coordinator
 |
 +--> Shard A: modify document A
 |
 +--> Shard B: modify document B
 |
 +--> Prepare commit decision
 |          |
 |          +--> participant A
 |          +--> participant B
 |
 +--> Commit decision recorded/coordinated
 |
 +--> Shards complete commit
 |
 v
Result to client
```

Never treat this as a set of independent transactions that the application commits sequentially:

```text
commit Shard A succeeds
commit Shard B fails
```

Doing that client-side loses multi-shard atomicity. The MongoDB coordinator executes the commit as a distributed transaction.

### 20.1. When the Client Loses Connection During Commit

Suppose the coordinator records the commit decision, then the network between client and router drops. The client may receive `UnknownTransactionCommitResult`.

**Never immediately re-run the entire transfer assuming the prior transaction failed.** If the prior transaction already committed, re-running can execute the business transfer a second time.

The driver callback API includes commit retry logic based on appropriate labels; the business layer still needs an idempotency key and reconciliation for ambiguous outcomes.

### 20.2. Visibility from Other Operations During Commit

MongoDB defines visibility rules during cross-shard commits:

- Some external reads using `"snapshot"` or `"linearizable"` read concern may **wait** to observe a consistent committed state.
- External reads with other concern levels may observe **pre-transaction state** during the commit window.
- Never assume every read at every concern level observes all shards at the exact same instant unconditionally.

If the application requires reading a consistent cross-shard snapshot, choose the appropriate read concern and verify exact transaction semantics.

---

## 21. Java Sync Driver: A Complete Transaction Example

Internal transfer example using the `MongoDB Java Sync Driver`. All balances are stored in **minor units** (e.g., cents) as Int64 so integer addition/subtraction is exact.

Data is seeded **outside the transaction** in a pre-created collection:

```javascript
db.accounts.insertMany([
  {
    _id: "ACC-A",
    balanceMinor: NumberLong("150000")
  },
  {
    _id: "ACC-B",
    balanceMinor: NumberLong("75000")
  }
]);
```

The `transfers` collection must also exist beforehand, especially when running on a sharded cluster that could produce cross-shard write transactions.

### 21.1. Code Using `withTransaction()`

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.bson.Document;

public final class TransferService {

    private final MongoClient client;
    private final MongoCollection<Document> accounts;
    private final MongoCollection<Document> transfers;

    public TransferService(MongoClient client) {
        this.client = client;

        MongoDatabase database =
            client.getDatabase("bank_demo");

        this.accounts = database.getCollection("accounts");
        this.transfers = database.getCollection("transfers");
    }

    public void transfer(
            String transferId,
            String fromAccount,
            String toAccount,
            long amountMinor
    ) {
        if (amountMinor <= 0 || fromAccount.equals(toAccount)) {
            throw new IllegalArgumentException(
                "Invalid transfer arguments"
            );
        }

        TransactionOptions options =
            TransactionOptions.builder()
                .readPreference(ReadPreference.primary())
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {

                UpdateResult debited = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", fromAccount),
                        Filters.gte("balanceMinor", amountMinor)
                    ),
                    Updates.inc("balanceMinor", -amountMinor)
                );

                if (debited.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Account not found or insufficient funds"
                    );
                }

                UpdateResult credited = accounts.updateOne(
                    session,
                    Filters.eq("_id", toAccount),
                    Updates.inc("balanceMinor", amountMinor)
                );

                if (credited.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Destination account not found"
                    );
                }

                transfers.insertOne(
                    session,
                    new Document("_id", transferId)
                        .append("from", fromAccount)
                        .append("to", toAccount)
                        .append("amountMinor", amountMinor)
                );

                return null;
            }, options);
        }
    }
}
```

**What is right from a transaction standpoint:**

- `ClientSession` comes from **the same `MongoClient`** that owns the collections.
- Both `updateOne` calls and `insertOne` receive the same `session`.
- Operations execute **sequentially**, not async in parallel.
- Transaction options specify `readPreference.primary`, `readConcern.snapshot`, and `writeConcern.majority`.
- The debit filter checks `balanceMinor >= amountMinor`, preventing negative balances under valid updates.
- `transferId` serves as the `_id` of the audit document, providing a uniqueness check when the collection is modeled appropriately.
- If any operation inside the callback fails, the driver aborts per `withTransaction()` behavior; commit only executes once the callback finishes.

### 21.2. Business Requirements Not Solved by This Example

This is a transaction illustration, **not a complete banking system**. Production still requires handling:

- Idempotency for retried HTTP transfer requests.
- Transfer limits, currency matching, and ownership/permission checks.
- Overflow checks when adding/subtracting `long` values.
- Auditing and reconciliation between ledger and balances.
- Blocking frozen accounts or invalid account statuses.
- Retry budgets and unknown commit scenarios.
- Uniqueness limitations of `_id`/business keys if `transfers` is sharded.
- Safe logging without exposing account numbers or PII.
- Cases where the transaction committed but the client never received the response.

If the application supports multiple currencies, `balanceMinor` must be paired with currency and formulas must never mix currencies.

### 21.3. Why Use the Callback API?

`ClientSession.withTransaction()` automates start/commit/abort lifecycle management and retries per MongoDB-defined error labels. It is the convenient choice for typical CRUD transactions.

However, **the callback can re-execute** on transient errors. Never place side effects external to the database inside the callback:

```java
// Avoid:
session.withTransaction(() -> {
    sendEmailToCustomer(); // Could send multiple times if callback retries.
    accounts.updateOne(session, filter, update);
    return null;
}, options);
```

If you need to send emails or events, consider a **transactional outbox**: write an outbox document in the same transaction, then have a post-commit worker deliver it externally with idempotency.

---

## 22. `UnknownTransactionCommitResult` and `TransientTransactionError`

These are two distinct error classes to separate clearly.

### 22.1. `TransientTransactionError`

During a transaction, transient failures such as write conflicts, stepdowns, or topology events can occur. If an error carries the label:

```text
TransientTransactionError
```

the standard handling is to **retry the entire transaction** from the beginning with a valid session/transaction, bounded by retry/backoff limits.

Do not merely rerun a single `updateOne` after the current transaction has already aborted.

### 22.2. `UnknownTransactionCommitResult`

If an error occurs during commit and carries the label:

```text
UnknownTransactionCommitResult
```

the application does not know for sure whether the server committed. Transaction-level handling is typically to **retry the commit operation** per driver semantics, rather than assuming the transaction failed.

A business request retried by a user after missing a response still needs an **idempotency key** to avoid creating duplicate transfers or orders.

### 22.3. Callback API vs. Core API

| Aspect | Callback API `withTransaction()` | Core API `startTransaction`/`commitTransaction` |
| --- | --- | --- |
| Start/commit/abort | Managed by driver | Coordinated by application. |
| Transient transaction retry | Built-in per driver spec | Must write custom logic. |
| Unknown commit result retry | Built-in per driver spec | Must write custom logic. |
| Flow control | Easy for sequential CRUD | More flexible but error-prone. |
| External side effects | Still must enforce idempotency manually | Still must enforce idempotency manually. |

Even though the callback handles retries, **do not claim it guarantees exactly-once execution for an entire HTTP request**. A durable business idempotency contract is still needed when clients resend requests.

---

## 23. Idempotency and Retries in Sharded Environments

Suppose an API looks like:

```text
POST /transfers
Idempotency-Key: 1d9f...
```

A transfer request executes and commits, but the network drops before the app returns a response. The client retries the request with the same key.

If the server processes the second call as a new transaction, the account can be debited a second time. MongoDB transactions protect **the atomicity of each execution**, not recognizing that two HTTP requests represent the same business intent.

A safer design:

1. Give each business request a stable `transferId`.
2. Persist `transferId` in the transaction alongside balance/ledger updates.
3. Place a unique constraint compatible with the shard key and business scope.
4. When a retry hits a duplicate, inspect the existing record and match amount/from/to/status before returning a result.
5. Never blindly treat every duplicate error as success: a duplicate could be a different request improperly reusing a key.
6. For `UnknownTransactionCommitResult`, combine driver commit retries with domain reconciliation.

### 23.1. Watch Out for Uniqueness in Sharded Collections

Suppose `transfers` is sharded by `tenantId`. A unique index on `transferId` alone may be invalid or lack the expected global guarantee.

Consider instead:

```javascript
db.transfers.createIndex(
  {
    tenantId: 1,
    transferId: 1
  },
  {
    unique: true
  }
);
```

This yields **per-tenant** uniqueness. If the business requires system-wide uniqueness, design keys/collections appropriately; never assume distributed transactions automatically create a global unique index.

---

## 24. Transactions Do Not Cover Systems Outside MongoDB

Example order placement flow:

```text
1. Create order in MongoDB.
2. Deduct inventory in MongoDB.
3. Call payment gateway.
4. Send confirmation email.
```

A MongoDB transaction makes **MongoDB writes attached to the same session** atomic. It **cannot roll back** a payment already captured by a payment gateway, nor “unsend” an email.

Avoid doing:

```text
startTransaction
  - update inventory
  - HTTP call to payment provider (waits 2 seconds)
  - insert order
commit
```

and treating the entire flow as one ACID transaction spanning MongoDB and the payment provider.

Better architectural patterns include:

- Sagas / compensating actions.
- Transactional outbox.
- Idempotent payment operations.
- Explicit state machines (`PENDING`, `AUTHORIZED`, `CONFIRMED`, `FAILED`).
- Periodic retries and reconciliation.

This also **shortens transaction duration**, avoiding timeouts and prolonged resource holds.

---

## 25. Designing Transactions to Usually Touch Only One Shard

A multi-tenant application has a collection:

```javascript
{
  tenantId: "T1",
  accountId: "A",
  balanceMinor: NumberLong("5000")
}
```

If an appropriate shard key co-locates a tenant's documents on the same shard, many intra-tenant transactions can reduce the number of participating shards.

However:

- Shard keys must not be chosen solely for transactions: load distribution, hot shards, and scalability also matter.
- A massive tenant may need to span multiple shards.
- Another collection sharded by a different key can still make transactions cross-shard.
- Changing a shard key or migrating chunks is a major architectural change.

### 25.1. Must Every Document Always Be Co-Located?

No. Some operations must transfer funds between two tenants or update two different shards. In those cases, cross-shard transactions are valid, provided you:

- Minimize the number of participating documents and shards.
- Target shards via the best possible filters.
- Index queries executed inside transactions.
- Avoid cluster-wide scans.
- Avoid DDL and external network calls.
- Configure timeout/retry budgets and measure p95/p99 commit latency.

**Never sacrifice correctness by splitting a distributed transaction into independent updates**, unless the domain accepts eventual consistency and has explicit sagas/recovery.

---

## 26. Monitoring Transactions on the Server

You can inspect transaction metrics depending on environment and privileges.

### 26.1. `serverStatus`

```javascript
db.serverStatus().transactions;
```

Fields may include active/inactive, committed, and aborted transaction counts along with other statistics depending on version/edition.

Do not hardcode dashboards to an assumed fixed metric set; inspect the output from your actual server version.

### 26.2. `$currentOp`

```javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  }
]);
```

Depending on privileges and version, `$currentOp` can expose active transactions, sessions holding resources, and distributed coordinator details.

These are **administrative diagnostic operations**, not operations to place inside business transactions.

### 26.3. Sharded Transaction Coordinator

For multi-shard write transactions, metrics and state for the two-phase commit coordinator are exposed via server tools such as `$currentOp` and `serverStatus`.

If p99 commit latency spikes, look beyond application logs. Inspect:

- Which shard participant is slow.
- Majority replication lag.
- Lock waits and write conflicts.
- Chunk migration / DDL critical sections.
- Network latency between router and shards.
- Active and aborted transaction counts.
- Transaction lifetime and cache pressure.

### 26.4. Driver-Side Telemetry

In Java, add command monitoring/tracing to observe `startTransaction` (wire-protocol metadata on commands), CRUD operations, `commitTransaction`, `abortTransaction`, command latency, and error labels.

Never log full documents or secrets just to debug transactions. Use properly scrubbed request IDs or business transaction IDs.

---

## 27. Verifying Transactions on Replica Sets and Sharded Clusters

### 27.1. Checking a Replica Set

In `mongosh`:

```javascript
rs.status();
db.hello();
db.version();
```

Check FCV if permitted:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Conditions to confirm:

- `db.hello()` confirms connection to a replica set member.
- An eligible primary exists.
- Key members are healthy.
- The replica set supports the required write concern.
- The application uses the right URI/set name without an invalid read preference.

### 27.2. Checking a Sharded Cluster

Connect through `mongos`:

```javascript
db.hello();
sh.status();
```

The `hello` response from a router includes `mongos`-specific indicators, such as `msg: "isdbgrid"` depending on version. `sh.status()` reports shards and data distribution.

Do not run `sh.status()` against a standalone `mongod` and conclude sharding is broken: connect to the router.

### 27.3. Safe Transaction Smoke Test

Use a test database with pre-created collections:

1. Insert two test documents.
2. Start a transaction.
3. Update both documents using the same session.
4. Explicitly abort and verify **both remain in their original state**.
5. Start another transaction.
6. Update both documents, commit with majority, and verify **both changed**.
7. Trigger a duplicate unique key error to verify the entire transaction aborts.
8. On a sharded cluster, test both **single-shard** and **multi-shard** paths with properly distributed data while observing metrics.

Never deliberately induce a primary failover or network partition during production hours just to check “whether transactions survive faults”. Run those tests in controlled staging/chaos environments.

---

## 28. Common Deployment Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | Connected to standalone. | Use a replica set or `mongos`; check URI. |
| Sharded cluster rejects transactions despite new server version | FCV, topology, or shard restrictions unmet. | Inspect all shards, FCV, arbiters, and majority journaling. |
| Transaction reports read preference error | Transaction reads while inheriting secondary read preference. | Set `ReadPreference.primary()` in transaction options. |
| Update A rolled back but update B persisted | Operation B omitted the session. | Ensure all CRUD operations receive the same `ClientSession`. |
| `NoSuchTransaction` or transaction state errors | Session/transaction aborted, expired, or misused lifecycle. | Inspect error labels, timeouts, and session usage. |
| `WriteConflict` | Multiple writers contending on the same document. | Retry transaction per transient label; reduce contention scope. |
| `LockTimeout` / abort during `createIndex` | Pending DDL blocking locks. | Coordinate migrations and transaction windows. |
| Transaction exceeds one minute and aborts | Default lifetime limit or excessive workload. | Reduce operation count, optimize queries, remove network calls. |
| `UnknownTransactionCommitResult` | Connection loss or timeout during commit. | Retry commit per driver and reconcile via idempotency; do not assume abort. |
| Multi-shard transactions slower than replica set | Distributed coordinator, network, and majority overhead. | Reduce participating shards; measure participant/commit times. |
| Creating new collection in multi-shard write txn fails | Unsupported DDL/implicit creation. | Pre-create collections/indexes before transactions. |
| `explain()` rejected in transaction | Unsupported operation. | Run explain outside the transaction with an equivalent query. |
| Transaction touching shard with arbiter fails | Multi-shard write restriction. | Redesign topology or transaction scope per guidelines. |
| Client retry creates two business operations | Missing idempotency. | Use business keys/unique constraints and reconcile. |
| High commit latency under majority | Replication lag or shard coordinator bottleneck. | Check shard health, network, and write concern. |
| `count`/`distinct` rejected | Unsupported command/helper inside txn. | Use equivalent aggregation where supported. |
| Transaction reads inconsistent data across shards | Read concern `"local"`/`"majority"` instead of `"snapshot"`. | Use `"snapshot"` when a synchronized cross-shard view is required. |

---

## 29. Practice Exercises

### Exercise 1 — Standalone vs. Replica Set

Local MongoDB runs with `mongod --dbpath ...`, without `--replSet`. Java calls `startTransaction()`, updates two collections, and throws an error.

**Question:** Why? How can you test transactions locally?

**Hint:** Standalone instances do not support multi-document transactions. Convert the local deployment into a **single-node replica set** or use a configured test MongoDB replica set.

### Exercise 2 — Version and FCV

Environment A: replica set with FCV 4.0. Environment B: sharded cluster with FCV 4.0.

**Question:** Do the historical minimum thresholds allow transactions?

**Hint:** Replica sets require at least 4.0; sharded clusters require at least 4.2. Always verify version/FCV across the entire deployment rather than relying on a single `mongos`.

### Exercise 3 — Operation Outside the Session

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(filter, update);

session.commitTransaction();
```

**Question:** Why does this transaction fail to make both operations atomic together?

**Hint:** `inventory.updateOne` lacks the `session` parameter, so it executes outside the transaction.

### Exercise 4 — Read Preference

`MongoClient` uses `ReadPreference.secondaryPreferred()`, while a transaction reads balances before writing.

**Question:** What needs to change?

**Hint:** Set `ReadPreference.primary()` on the transaction. Secondary reads are unsupported inside transactions that perform read operations.

### Exercise 5 — Cross-Shard Snapshot

A transaction reads account A on shard 1 and account B on shard 2. The team sets read concern `"majority"` and believes both come from the same snapshot.

**Question:** Is that conclusion correct?

**Hint:** `"majority"` does not guarantee a synchronized snapshot across shards. If needed, use `"snapshot"` with `"majority"` commit for the corresponding guarantees.

### Exercise 6 — Arbiter

A transaction writes across two shards, and one shard is a replica set with an arbiter.

**Question:** Is this supported?

**Answer:** MongoDB restricts this, and a multi-shard write transaction will error/abort if any operation touches a shard containing an arbiter.

### Exercise 7 — DDL

A transaction updates `orders` on shard A and inserts into a non-existent `auditLogs` collection on shard B.

**Question:** Can this run in one cross-shard write transaction?

**Answer:** No. Pre-create the collection outside the transaction.

### Exercise 8 — Transaction Lifetime

An application starts a transaction, calls a payment gateway taking 90 seconds, and then commits.

**Question:** What are the risks?

**Hint:** Exceeds the 60-second default lifetime, pins resources for too long, increases write conflicts, and commits may fail. Move external calls outside the transaction and use sagas/outbox.

### Exercise 9 — Retrying Commit

MongoDB committed, but the response was lost. The client receives `UnknownTransactionCommitResult`.

**Question:** Should this be treated as aborted and the money transfer re-run?

**Hint:** No. Retry the commit per the driver API and reconcile using a business idempotency key.

### Exercise 10 — Shard Key Design

`accounts` is sharded by `tenantId`, but the transaction query filters only by `accountId`.

**Question:** What is the risk?

**Hint:** The router may need to broadcast, increasing participant count and transaction cost. Review shard keys and filters to target shards whenever possible.

### Exercise 11 — Unique Indexes

Collection `transfers` is sharded by `tenantId`; the team creates a unique index solely on `transferId` to guarantee system-wide once-only execution.

**Question:** What remains unsolved?

**Hint:** Global uniqueness in sharded collections is constrained; unique keys must align with the shard key, and transactions do not enforce uniqueness across arbitrary fields on their own.

### Exercise 12 — Transactions and External Calls

A transaction updates two collections and sends an email inside the `withTransaction` callback.

**Question:** Why might two emails be sent even though MongoDB committed only once?

**Hint:** The callback can retry on transient errors. Use an outbox and idempotent event delivery.

---

## 30. Production Checklist for Replica Set Transactions

1. The replica set is initialized with a healthy primary and members.
2. Version/FCV supports transactions; deployment is not standalone.
3. The driver supports sessions, and every CRUD call uses the same session.
4. At most one active transaction exists per session; sessions are never shared across threads.
5. Read preference is appropriate; transactions with reads must use `primary`.
6. Read concern matches consistency needs, typically `snapshot` when required.
7. Write concern is set explicitly at the transaction level; consider `majority`.
8. Never set per-CRUD write concerns inside a transaction.
9. Protect invariants with conditional updates and unique indexes.
10. Pre-create collections and indexes via migrations.
11. Keep transactions short; avoid network calls, large data scans, and waiting on users.
12. Implement retries properly based on transient/unknown commit error labels.
13. Implement idempotency for business HTTP requests and side effects.
14. Monitor abort rates, duration, lock waits, cache pressure, and replication lag.
15. Test aborts, conflicts, failovers, and unknown commits in a controlled environment.

## 31. Additional Checklist for Sharded Clusters

In addition to the replica set checklist:

1. Application clients connect **through `mongos`**.
2. Cluster-wide version/FCV supports sharded transactions.
3. All shards have valid topologies and compliant majority journaling.
4. No shard has `writeConcernMajorityJournalDefault: false`.
5. Review arbiter restrictions before running cross-shard write transactions.
6. Collections to be written are pre-created and indexed, never created inside cross-shard write transactions.
7. Shard keys and filters target shards and minimize scatter-gather.
8. When a synchronized cross-shard snapshot is required, use read concern `"snapshot"`.
9. Account for two-phase commit and coordinator overhead.
10. Minimize participating shards when the domain allows.
11. Have a strategy for chunk migrations and DDL during active transaction windows.
12. Manage transaction lifetime across shard replica set members.
13. Evaluate uniqueness/idempotency alongside the shard key.
14. Monitor participant/coordinator metrics, network latency, and majority replication.
15. Benchmark single-shard vs. multi-shard workloads at p95/p99 under load.

Decision flowchart:

```text
Need to update multiple values
             |
             v
Can they fit into a single document?
        |            |
       Yes           No
        |            |
   Single-doc     Need all-or-nothing?
   atomic update        |             |
                       No            Yes
                        |             |
                  Intentional    Transaction
                  eventual/saga       |
                                      v
                               What is the deployment?
                                /      |       \
                          Standalone ReplicaSet Sharded
                             |        |        |
                           Not    Supported  Supported if
                         supported if valid  prerequisites met
                                               |
                                               v
                                   Single-shard or cross-shard?
                                     |               |
                                  Single          Cross
                                   shard           shard
                                     |               |
                                 Usually lower   2PC, arbiters,
                                   overhead      DDL, FCV, and
                                                 majority rules
```

---

## 32. Official MongoDB Documentation

- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/): ACID properties, sessions, concerns, read preferences, and general behavior.
- [Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): standalone/replica set support, FCV, lifetime, locks, DDL, and cache limits.
- [Production Considerations — Sharded Clusters](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/): overhead, shard restrictions, time limits, snapshots, and commits.
- [Transactions and Operations](https://www.mongodb.com/docs/manual/core/transactions-operations/): supported/disallowed operations and collection/index creation rules.
- [Handle Transactions in Applications with the Drivers API](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): callback/core APIs and retry label handling.
- [Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): `ClientSession`, `withTransaction`, transaction options, and Java examples.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): differences between `local`, `majority`, and `snapshot`.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgments and majority rules.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): read routing and primary requirement for transactions with reads.
- [Sharded Cluster Requirements](https://www.mongodb.com/docs/manual/core/sharded-cluster-requirements/): shard keys, unique indexes, and operational constraints.
- [Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/): role of `mongos` and targeted vs. broadcast routing.

In production operations, always cross-check your **MongoDB server version, FCV, driver, deployment type, and managed service**. Specific limits and metric collection mechanisms can vary across releases.

## 33. Conclusion

MongoDB multi-document transactions can only be deployed when the **server architecture** meets the requirements: **a valid replica set or sharded cluster**, not standalone. Version/FCV is the first prerequisite, but it is not enough on its own; **proper sessions, read preference, read concern, write concern, and supported operations** determine whether a transaction works correctly.

On a replica set, a transaction typically carries more overhead than a single-document update, yet it protects cross-document invariants. On a sharded cluster, applications must route through `mongos`; multi-shard transactions require distributed commit coordination and face added constraints around **arbiters, majority journaling, DDL, shard keys, and chunk migrations**.

In both topologies, **keep transactions short**, pre-create collections and indexes, avoid mixing network calls or external side effects into retryable callbacks, and design **idempotency + error handling** for unknown commit results. Measure both performance and correctness in a production-like environment.

**Technical prerequisites enable transactions to run; consistent design and proper retries make them safe in real systems.**
