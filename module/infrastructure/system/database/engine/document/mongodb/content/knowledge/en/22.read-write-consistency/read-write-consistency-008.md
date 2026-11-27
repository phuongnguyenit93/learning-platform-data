# Snapshot reads and applicability outside or inside transactions in MongoDB

## 1. Lesson objectives

A live MongoDB system may simultaneously accept orders, transfer funds, update inventory, and run reports. While a report reads data, other transactions and write commands continue committing. Thus, two consecutive reads do not necessarily reflect the exact same database state.

For example, a pagination API reads the first 20 rows and then counts the total matching results. If a new order is created between the two queries, the list may reflect time T0 while the total reflects time T1. Both commands execute properly on their own, yet the **pair of results** is inconsistent across time.

MongoDB provides read concern `"snapshot"` to read data as it existed at **a specific logical timestamp**, within the scope and conditions supported by your server/driver version.

This lesson belongs to the **Read and Write Consistency** chapter of **Database Engine Document MongoDB**, focusing on **Snapshot reads and applicability outside or inside transactions**.

After this lesson, you will be able to:

1. Distinguish `local`, `majority`, `snapshot`, and `linearizable`.
2. Understand what snapshot reads guarantee and what properties they do not guarantee.
3. Use `snapshot` inside multi-document transactions with read concern set at the **transaction level**.
4. Know why starting in **MongoDB 5.0**, snapshot reads can run **outside transactions** for supported commands.
5. Use `find`, `aggregate`, `atClusterTime`, and `snapshot:true` sessions in `mongosh`.
6. Use snapshot sessions and transactions in the Java Sync Driver.
7. Handle history window limits, `SnapshotTooOld`, secondary lag, and sharded clusters.
8. Design consistent reporting and pagination without confusing snapshots with backups, transactions, or retries.

**Key message:** `readConcern:"snapshot"` is a request about **data view**. It does not make arbitrary writes atomic, does not retain historical data indefinitely, and does not guarantee the snapshot is the latest version when the application displays results.

## 2. How do snapshot reads work conceptually?

Suppose a system stores two e-wallets:

~~~javascript
{ _id: "A", balance: NumberDecimal("500.00") }
{ _id: "B", balance: NumberDecimal("300.00") }
~~~

A transaction transfers 50 from A to B and commits:

~~~text
T0: A=500, B=300; total 800
          |
          |  transaction transfers 50
          v
T1: A=450, B=350; total 800
~~~

A report reading A before T1 and B after T1 could observe:

~~~text
A=500 (pre-commit value)
B=350 (post-commit value)
Observed total = 850
~~~

The result 850 represents neither the state at T0 nor at T1. Snapshots let you fix a consistent view:

~~~text
Time --------------- T0 ------------ T1 ---------->

Snapshot S0:
  Read A after T1 -> still sees A=500 at T0
  Read B after T1 -> still sees B=300 at T0

Snapshot S1:
  Read A          -> A=450 at T1
  Read B          -> B=350 at T1
~~~

### 2.1. Snapshot time is not the application wall clock

The timestamp in MongoDB's snapshot mechanism is a **BSON Timestamp/cluster time** governed by replication and storage rules. It is not a document's `Date` field, not `createdAt`, and you cannot arbitrarily pick an `ISODate` far in the past.

### 2.2. A snapshot can be older yet still consistent

If a snapshot is pinned at T0, a write majority-committed at T1 will not appear inside snapshot T0. This is correct behavior: the snapshot reads the version at the selected point in time.

**Snapshot consistency** and **data freshness** are two different requirements. An application needing the latest data may need a different read concern/read path or a newer snapshot.

### 2.3. Snapshots do not make multiple non-transactional updates atomic

These two operations are two separate writes:

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: NumberDecimal("-50.00") } }
);

db.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberDecimal("50.00") } }
);
~~~

At the moment between the two writes, the true state may be A=450, B=300. A snapshot landing right at that intermediate point reflects that intermediate state; **it cannot turn two separate writes into a transaction**.

If business logic requires atomic multi-document transfers, use a transaction or another suitable atomic update model. If the requirement is simply *multiple reads sharing the same view*, snapshot reads are the direct mechanism.

## 3. Distinguishing read concern, write concern, and read preference

| Concept | Question it solves |
|---|---|
| `readConcern` | Which version of data may be read? |
| `writeConcern` | At what level must writes be acknowledged? |
| `readPreference` | Which node can execute the read? |
| `session` | Which operations share a logical context? |
| `transaction` | Which operations form a commit/abort unit? |

Example:

~~~text
readPreference=secondary
readConcern=snapshot
~~~

can permit snapshot reads on a secondary in supported versions. It does not turn a secondary into a primary and does not mean the data is the latest across the whole cluster.

### 3.1. Common read concern levels

| Level | General meaning | What to watch out for |
|---|---|---|
| `local` | Reads data currently on the node, without requiring majority commit | May observe data later rolled back |
| `majority` | Reads only majority-committed data per read concern guarantees | Two separate queries may read at different timestamps |
| `snapshot` | Reads a view of data at a chosen timestamp | Not automatically latest; requires supported scope/commands |
| `linearizable` | Strong real-time ordering guarantee for qualifying reads on primary | Not equivalent to a multi-collection/shard snapshot |

### 3.2. Why is majority not enough for multiple queries?

Suppose order 101 transitions from `NEW` to `PAID` at T1 and the write is majority-committed. Read #1 at T0 sees `NEW`; read #2 at T2 sees `PAID`. Both results are valid at `majority`, yet they belong to different timestamps.

A snapshot session anchors multiple reads to one timestamp, whereas isolated majority queries do not share that anchor.

### 3.3. Snapshot does not equal linearizable

A snapshot may reflect the recent past. Linearizable reads target ordering guarantees relative to operations completed in real time under supported conditions. Never call every snapshot "the latest data," and never use linearizable as a drop-in replacement for long multi-collection snapshot reports.

## 4. Support by version and scope

### 4.1. Snapshot inside transactions

MongoDB supports snapshot read concern in multi-document transactions within supported transaction scope:

- Replica sets support multi-document transactions since MongoDB **4.0**.
- Sharded clusters support transactions since MongoDB **4.2**.
- Transaction read concern is set at **`startTransaction`**, not per individual read command.
- To guarantee reading from a majority-committed snapshot per the MongoDB Manual, the transaction must **commit with write concern `"majority"`**.

### 4.2. Snapshot outside transactions

**Starting in MongoDB 5.0**, supported read operations can use `readConcern:"snapshot"` **without opening a multi-document transaction**.

| Operation outside transaction | Snapshot supported? | Notes |
|---|---|---|
| `find` | Yes | Cursor can belong to a snapshot |
| `aggregate` | Yes | Read pipelines within permitted scope |
| `distinct` | Yes for **unsharded collections** | Does not arbitrarily extend to sharded collections |
| `count` command | No | Use aggregation `$count` if snapshot is needed |
| `insert`/`update`/`delete` outside transaction | No | Snapshot read concern does not make writes transactional |
| Other commands | Not by default | Check version support matrix |

Do not extrapolate "snapshot reads can run outside transactions" to mean every MongoDB read command supports it.

### 4.3. Primary, secondary, and sharding

Outside transactions, snapshot reads are supported on primaries and secondaries in eligible deployments; sharded clusters can coordinate snapshot reads across multiple shards at a unified logical point in time.

**Do not** infer that write transactions can run on secondaries simply because non-transactional snapshot reads can select secondaries. Standard multi-document transactions use `primary` read preference.

### 4.4. Capped collections vary by version

MongoDB 8.0 introduced support changes for `readConcern:"snapshot"` on capped collections. Earlier versions have restrictions. When using capped collections or mixed server versions, consult documentation for the exact version.

### 4.5. Do not use standalone to verify every feature

These transaction/snapshot examples should run on a properly configured replica set or sharded cluster. A standalone `mongod` or restricted managed tier may not support every operation described.

## 5. Preparing the practice dataset

Open `mongosh` connected to a test replica set, then select a dedicated database:

~~~javascript
use snapshot_read_lab
~~~

Create three accounts:

~~~javascript
const demoAccounts = [
  {
    _id: "A",
    tenantId: "tenant-1",
    owner: "Lan",
    balance: NumberDecimal("500.00"),
    version: NumberInt(1)
  },
  {
    _id: "B",
    tenantId: "tenant-1",
    owner: "Minh",
    balance: NumberDecimal("300.00"),
    version: NumberInt(1)
  },
  {
    _id: "C",
    tenantId: "tenant-2",
    owner: "An",
    balance: NumberDecimal("200.00"),
    version: NumberInt(1)
  }
];

demoAccounts.forEach(account => {
  db.accounts.replaceOne(
    { _id: account._id },
    account,
    { upsert: true, writeConcern: { w: "majority" } }
  );
});

db.accounts.find().sort({ _id: 1 });
~~~

Create six orders:

~~~javascript
const demoOrders = [
  {
    _id: 101,
    tenantId: "tenant-1",
    customerId: "A",
    status: "PAID",
    amount: NumberDecimal("40.00"),
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: 102,
    tenantId: "tenant-1",
    customerId: "B",
    status: "PAID",
    amount: NumberDecimal("15.00"),
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: 103,
    tenantId: "tenant-1",
    customerId: "A",
    status: "NEW",
    amount: NumberDecimal("20.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: 104,
    tenantId: "tenant-1",
    customerId: "B",
    status: "PAID",
    amount: NumberDecimal("30.00"),
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: 105,
    tenantId: "tenant-2",
    customerId: "C",
    status: "NEW",
    amount: NumberDecimal("12.00"),
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: 106,
    tenantId: "tenant-2",
    customerId: "C",
    status: "PAID",
    amount: NumberDecimal("55.00"),
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true, writeConcern: { w: "majority" } }
  );
});

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
);
~~~

On a fresh empty collection, you have:

- **6 orders**: `tenant-1` has four orders, `tenant-2` has two orders.
- `tenant-1` has **3 PAID**, 1 NEW; total PAID amount for `tenant-1` is **85.00**.
- Three accounts: A=500, B=300, and C=200.
- `amount`/`balance` use Decimal128.

`replaceOne(...,{upsert:true})` reloads those sample IDs, **but will overwrite modified test data** on those IDs. Never run on production collections. Expected results in this lesson assume no extra records or concurrent writes outside the described steps.

### 5.1. Why does seeding use majority write concern?

Snapshot reads outside transactions observe majority-committed data. If you just inserted documents with a weaker write concern, a new snapshot might not yet see all sample data at read time.

Writing with `w:"majority"` makes test results more predictable, provided the replica set has enough data-bearing members online to acknowledge.

### 5.2. Basic verification

~~~javascript
db.accounts.find(
  {},
  { _id: 1, balance: 1 }
).sort({ _id: 1 });

db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).sort({ createdAt: -1, _id: -1 });
~~~

PAID orders for `tenant-1` have IDs **104, 102, 101** in that order.

## 6. A non-transactional snapshot read with `find`

You can set read concern on a `mongosh` cursor:

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.readConcern("snapshot")
.toArray();
~~~

This read uses a snapshot of majority-committed data at a timestamp chosen by MongoDB under its supported mechanism.

### 6.1. Running one query does not pin the snapshot for subsequent queries

Run:

~~~javascript
db.orders.find({ tenantId: "tenant-1" })
  .readConcern("snapshot")
  .toArray();

db.orders.find({ tenantId: "tenant-1" })
  .readConcern("snapshot")
  .toArray();
~~~

If a write is majority-committed in between, the two separate commands may receive **two different timestamps**. Sharing the same read concern alone does not bind them to the same point in time.

### 6.2. Distinguish single-query stability from multi-query stability

- A snapshot `find` uses a view at **that query's** snapshot.
- Two separate `find` calls need not share the same timestamp.
- Multiple `find` calls in a **snapshot session** share the same timestamp.
- `find` calls inside a **snapshot transaction** also share the transaction's view.

### 6.3. Does a snapshot `find` lock out writers?

Do not treat a snapshot read as a write lock over all read documents. Other writers can still write new data. The snapshot read continues viewing the older version at its timestamp, provided history is retained.

## 7. A non-transactional snapshot read with `aggregate`

Example aggregating PAID orders:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "tenant-1",
        status: "PAID"
      }
    },
    {
      $group: {
        _id: null,
        count: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    }
  ],
  {
    readConcern: { level: "snapshot" },
    maxTimeMS: 5000
  }
);
~~~

With the sample data, `count = 3` and `totalAmount = 85.00`.

### 7.1. Why use `$count` in aggregation?

The `aggregate` command supports snapshots outside transactions. To count:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1" } },
    { $count: "total" }
  ],
  { readConcern: { level: "snapshot" } }
);
~~~

This command returns the document count at that command's snapshot. The standalone `count` command is not on the list of non-transactional snapshot operations. Some `countDocuments()` helpers wrap aggregation internally, though support varies by API/driver; using `aggregate` here clearly illustrates the permitted command contract.

### 7.2. What does an empty `$count` return?

With a filter matching nothing, the pipeline:

~~~javascript
[
  { $match: { tenantId: "not-found" } },
  { $count: "total" }
]
~~~

returns an **empty array**, rather than synthesizing `{total:0}`. Application code should normalize this if an API expects zero.

### 7.3. `readConcern` does not alter filters or permissions

Snapshots do not automatically scope tenants. If you forget `tenantId` in `$match`, the query can still read other tenants' data per granted database privileges.

## 8. Snapshot sessions: multiple reads at the same point in time without transactions

Starting in MongoDB 5.0, a **snapshot session** can share a single timestamp across multiple supported read operations without starting a multi-document transaction.

In `mongosh`:

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const sdb = s.getDatabase("snapshot_read_lab");

try {
  const a = sdb.accounts.findOne({ _id: "A" });
  const b = sdb.accounts.findOne({ _id: "B" });

  printjson({
    balanceA: a.balance,
    balanceB: b.balance
  });
} finally {
  s.endSession();
}
~~~

Here there is no `startTransaction()`, `commitTransaction()`, or `abortTransaction()`. The session simply scopes reads to the same snapshot.

### 8.1. The first read picks the timestamp

~~~text
startSession({snapshot:true})
            |
            v
Read #1 ---> Server selects timestamp T and returns atClusterTime
            | Driver/shell retains T
            v
Read #2 ---> Reads at T
            |
            v
Read #3 ---> Reads at T
            |
            v
endSession()
~~~

The timestamp is not necessarily fixed at `startSession()`. It is established when the first supported operation acquires a snapshot.

### 8.2. Snapshot sessions can read across multiple collections

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const accounts = d.accounts.find({
    tenantId: "tenant-1"
  }).toArray();

  const paid = d.orders.find({
    tenantId: "tenant-1",
    status: "PAID"
  }).toArray();

  printjson({
    accountsRead: accounts.length,
    paidOrdersRead: paid.length
  });
} finally {
  s.endSession();
}
~~~

Two different collections, yet both reads belong to **one timestamp** because they share the snapshot session. This is a major difference from running two separate `majority` queries.

### 8.3. Snapshot sessions differ from transactions

| Non-transactional snapshot session | Snapshot transaction |
|---|---|
| Intended for supported read operations | Can include permitted CRUD operations, including writes |
| No atomic multi-write commit/abort | Has commit/abort |
| No transaction needed | Requires `startTransaction` |
| Shared timestamp across multiple reads | Transaction view fixed per transaction mechanics |
| Supports reading on secondaries per rules | Standard transactions use primary |
| May see `SnapshotTooOld` if held open too long | Has dedicated transaction lifetime and resource limits |
| Cannot be used for atomic transfers | Can execute atomic multi-document transfers |

### 8.4. `snapshot` and `causalConsistency` are mutually exclusive in a session

In `mongosh`, `snapshot:true` and `causalConsistency:true` cannot be combined.

~~~javascript
const good = db.getMongo().startSession({
  snapshot: true
});
good.endSession();
~~~

Do not write:

~~~javascript
// Invalid:
db.getMongo().startSession({
  snapshot: true,
  causalConsistency: true
});
~~~

Causal consistency and snapshot consistency solve different problems. Causal consistency tracks ordering relationships across operations; snapshots pin multiple reads to the exact same point in time.

## 9. Practice with an intervening write between two snapshot reads

Reload `accounts` from Section 5 so B=300, then run:

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const d = s.getDatabase("snapshot_read_lab");

try {
  // First read pins timestamp T.
  const aAtT = d.accounts.findOne({ _id: "A" });

  // This write does NOT belong to the snapshot session.
  db.accounts.updateOne(
    { _id: "B" },
    {
      $set: {
        balance: NumberDecimal("350.00")
      }
    },
    { writeConcern: { w: "majority" } }
  );

  // Subsequent read still uses timestamp T.
  const bAtT = d.accounts.findOne({ _id: "B" });

  // Normal read outside session observes the newer point in time.
  const bCurrent = db.accounts.findOne({ _id: "B" });

  printjson({
    aAtT: aAtT.balance,
    bAtT: bAtT.balance,
    bCurrent: bCurrent.balance
  });
} finally {
  s.endSession();
}
~~~

On sample data with no other writes:

~~~javascript
{
  aAtT: NumberDecimal("500.00"),
  bAtT: NumberDecimal("300.00"),
  bCurrent: NumberDecimal("350.00")
}
~~~

**Explanation:** Reading A first pinned the snapshot at a time when B was still 300. The external write updated B to 350. Reading B inside the session still sees the value at the old snapshot, whereas reading outside the session observes the new value.

Do not use two separate writes like this to implement real funds transfers. This is a **read consistency** test, not a funds-transfer guide.

Afterward, reload account B or all of `demoAccounts` before continuing.

## 10. `atClusterTime`: selecting a timestamp for non-transactional snapshot reads

Outside transactions, snapshot reads accept an optional `atClusterTime`.

~~~javascript
db.runCommand({
  find: "orders",
  filter: { tenantId: "tenant-1" },
  readConcern: {
    level: "snapshot",
    atClusterTime: Timestamp(1760000000, 1)
  }
});
~~~

The timestamp above **only illustrates syntax**. An arbitrary wall-clock timestamp is not guaranteed to have a retained snapshot. Applications must use a valid BSON Timestamp within the server's snapshot history.

### 10.1. Reading the timestamp from a response

Under the snapshot reads protocol, `find`/`aggregate` responses can include `cursor.atClusterTime`. Example:

~~~javascript
const first = db.runCommand({
  find: "orders",
  filter: { tenantId: "tenant-1" },
  projection: { _id: 1, status: 1 },
  batchSize: 20,
  readConcern: { level: "snapshot" }
});

const t = first.cursor.atClusterTime;

printjson({
  items: first.cursor.firstBatch,
  timestamp: t
});
~~~

`t` has type BSON Timestamp; it is not an order's `createdAt` field.

### 10.2. Reusing the timestamp for another aggregation

~~~javascript
const sameTime = db.runCommand({
  aggregate: "orders",
  pipeline: [
    { $match: { tenantId: "tenant-1" } },
    { $group: { _id: "$status", n: { $sum: 1 } } }
  ],
  cursor: {},
  readConcern: {
    level: "snapshot",
    atClusterTime: t
  },
  maxTimeMS: 5000
});

printjson(sameTime.cursor.firstBatch);
~~~

Both operations request the exact same timestamp T.

**Note:** Never pass `atClusterTime` alongside `afterClusterTime`, and do not use this in a causally consistent session with conflicting options. Unless you specifically need manual timestamp control, letting the driver manage a snapshot session is simpler and less error-prone.

### 10.3. Secondary has not caught up to T

If a read goes to a secondary that has only applied the oplog up to T1 while you request `atClusterTime: T2`, the server may wait until the node has data at T2. `maxTimeMS` bounds waiting/computation time.

### 10.4. Timestamp is too old

If T falls outside WiredTiger's retained history, MongoDB may report `SnapshotTooOld`. Retrying the exact command with the same expired timestamp usually will not help; you need a new snapshot or a different historical storage design.

## 11. Snapshot inside transactions: configuring at `startTransaction`

A multi-document transaction provides a commit/abort unit. For transaction operations to read from a snapshot, set read concern when **starting the transaction**:

~~~javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const txdb = session.getDatabase("snapshot_read_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const a = txdb.accounts.findOne({ _id: "A" });
  const b = txdb.accounts.findOne({ _id: "B" });

  printjson({
    balanceA: a.balance,
    balanceB: b.balance
  });

  session.commitTransaction();
} catch (e) {
  try { session.abortTransaction(); } catch (_) {}
  throw e;
} finally {
  session.endSession();
}
~~~

### 11.1. Do not attach individual read concerns to reads inside a transaction

Incorrect usage:

~~~javascript
session.startTransaction();

// Do not use cursor-level readConcern instead of transaction options:
txdb.accounts.find({ _id: "A" })
  .readConcern("snapshot");
~~~

Correct:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});
~~~

Transaction read concern applies to all operations in the transaction, rather than ad-hoc per-query settings. If a collection/database has its own read concern, transaction-level options take precedence per driver/server rules.

### 11.2. Reading multiple collections in one transaction

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

const accounts = txdb.accounts.find({
  tenantId: "tenant-1"
}).toArray();

const orders = txdb.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).toArray();

session.commitTransaction();
~~~

Both reads share the transaction's snapshot view, suitable for reports needing computation alongside writes in the same transactional unit if required.

### 11.3. `startTransaction` does not fix the timestamp immediately

In `mongosh`, `startTransaction()` initializes context; the transaction actually starts on the server when the first operation is sent. Never assume the snapshot timestamp equals wall-clock time at the `startTransaction` call before the first read/write runs.

### 11.4. Only one open transaction per session

Never open two concurrent transactions on the same `ClientSession`. For parallel work, organize separate sessions/transactions following driver concurrency rules and business requirements.

## 12. Majority write concern and snapshot transaction guarantees

Per the MongoDB Manual, read concern `snapshot` in a transaction guarantees reading from a majority-committed snapshot when the transaction **commits with write concern `majority`**.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});
~~~

Compare:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
});
~~~

The second configuration lacks the equivalent full majority-committed snapshot guarantee of a majority commit.

### 12.1. Do not attach write concern to individual updates inside a transaction

Example to avoid:

~~~javascript
txdb.accounts.updateOne(
  { _id: "A" },
  { $set: { owner: "Lan" } },
  { writeConcern: { w: "majority" } }
);
~~~

When an operation is inside a transaction, the transaction's write concern is applied at **commit**. Specifying `writeConcern` on individual writes may be rejected.

### 12.2. Commit can have an unknown outcome

If the network drops after the client sends commit, the application may not know for sure whether the transaction committed. Handle error labels such as `UnknownTransactionCommitResult`, `TransientTransactionError`, and driver retry mechanisms.

Never treat a timeout as proof the transaction did not execute; and never re-issue another payment business operation without idempotency.

## 13. Does a transaction see its own writes?

**Yes.** A snapshot transaction isolates its view from external mutations, while writes made by **the transaction itself** are visible to subsequent reads within the same transaction.

Example transferring 50 from A to B in the practice database:

~~~javascript
const s = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const d = s.getDatabase("snapshot_read_lab");

try {
  s.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  d.accounts.updateOne(
    { _id: "A" },
    { $inc: { balance: NumberDecimal("-50.00") } }
  );

  d.accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: NumberDecimal("50.00") } }
  );

  const a = d.accounts.findOne({ _id: "A" });
  const b = d.accounts.findOne({ _id: "B" });

  printjson({
    inTxA: a.balance,
    inTxB: b.balance
  });

  s.commitTransaction();
} catch (e) {
  try { s.abortTransaction(); } catch (_) {}
  throw e;
} finally {
  s.endSession();
}
~~~

Starting from A=500, B=300, reads inside the transaction after the two updates observe A=450, B=350.

**Important:** This snippet **writes real data in the practice database**. Reload `demoAccounts` before subsequent exercises. In production, add authorization checks, balance validation, idempotency, and full transaction retry handling.

### 13.1. Snapshots do not pull external new writes into the transaction

If another transaction updates A after the snapshot timestamp, reads inside the current transaction still see old A. Do not use a snapshot transaction when the requirement is reading "the absolute latest value" without an appropriate coordination strategy.

### 13.2. Write conflicts

When a transaction operates on an old snapshot and attempts to modify a document already updated by another transaction or write, MongoDB may return `WriteConflict` and abort the transaction.

The application must retry per the transaction protocol and **re-evaluate business conditions**, rather than blindly overwriting conflicts.

## 14. Snapshot isolation does not guarantee serializability for all invariants

Consider a rule that at least one staff member must always remain on call:

~~~text
T0:
  Alice.onCall = true
  Bob.onCall   = true

Transaction T1 reads the same snapshot T0:
  sees Bob is on call
  -> updates Alice.onCall = false

Transaction T2 reads the same snapshot T0:
  sees Alice is on call
  -> updates Bob.onCall = false

If the two writes on two documents do not directly conflict,
both transactions can produce state:
  Alice.onCall = false
  Bob.onCall   = false
~~~

This is commonly known as *write skew*. Snapshot isolation ensures multiple reads are point-in-time consistent, but does not automatically enforce arbitrary cross-document rules like a serializable schedule.

Design options:

- Use a single coordination document holding the protected condition, updated atomically.
- Use unique indexes/schema constraints where invariants can be encoded.
- Inside transactions, perform a conditional write forcing competing transactions to conflict directly.
- Use optimistic concurrency and version fields.
- Re-check conditions upon retry against fresh data.

**Do not treat `readConcern: "snapshot"` as a default cure-all for every global invariant or race condition.**

## 15. How does causal consistency differ from snapshot sessions?

Causal consistency focuses on causal ordering between operations such as "reading your own prior write." Snapshot sessions focus on reading **the exact same timestamp**, even as external writes continue arriving.

Example:

~~~text
Causal session:
  write X finishes
  read Y after X -> preserves causal order under supported conditions

Snapshot session:
  read X at T
  read Y at T
  new writes outside session after T do not appear
~~~

The two concepts do not replace each other.

### 15.1. Do not pass conflicting `atClusterTime` and `afterClusterTime`

`afterClusterTime` relates to causal consistency, while `atClusterTime` requests reading a specific snapshot timestamp. Do not combine them in violation of command rules.

To use `atClusterTime` explicitly, use an appropriate session/command setup rather than enabling causal consistency in the same snapshot session and adding `atClusterTime`.

### 15.2. When is causal consistency more suitable?

If an application only needs to see the effects of writes previously executed in the same flow, causal consistency/majority concern may fit better than pinning an old snapshot.

If an application needs a report across multiple collections at a unified point in time, a snapshot session is clearer.

## 16. Consistent pagination: `total` and `items`

Suppose an API:

~~~text
GET /orders?tenantId=tenant-1&status=PAID&page=1&pageSize=2
~~~

Needs:

- `items`: top 2 orders chronologically.
- `total`: total orders matching the filter.
- `totalPages`: page count based on `total`.

Two ordinary operations:

~~~javascript
const filter = {
  tenantId: "tenant-1",
  status: "PAID"
};

const total = db.orders.countDocuments(filter);

const items = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(2)
  .toArray();
~~~

do not automatically share a timestamp. An insert/update between the two commands can make `total` and `items` reflect different points in time.

### 16.1. Using a snapshot session for `items` and `count`

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const filter = {
    tenantId: "tenant-1",
    status: "PAID"
  };

  const items = d.orders.find(filter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(2)
    .toArray();

  const counted = d.orders.aggregate([
    { $match: filter },
    { $count: "total" }
  ]).toArray();

  const total = counted.length === 0
    ? 0
    : counted[0].total;

  printjson({
    ids: items.map(x => x._id),
    total: total,
    totalPages: Math.ceil(total / 2)
  });
} finally {
  s.endSession();
}
~~~

On sample data, IDs are 104, 102 and `total=3`.

**Key point:** Both `find` and `aggregate` run through `d` of the **same snapshot session**. If one operation accidentally uses plain `db.orders`, it will not share the snapshot session.

### 16.2. Why is `$facet` also an option?

A single aggregation can return both data and count:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "tenant-1",
        status: "PAID"
      }
    },
    {
      $facet: {
        data: [
          { $sort: { createdAt: -1, _id: -1 } },
          { $limit: 2 }
        ],
        metadata: [
          { $count: "total" }
        ]
      }
    }
  ],
  {
    readConcern: { level: "snapshot" }
  }
);
~~~

This uses **one command** with snapshot read concern, though the count branch still scans all matching items. `$facet` has its own memory and 16 MiB BSON output limits. Do not treat it as a free count.

### 16.3. Paginating across multiple HTTP requests

When a user loads page 1 and returns for page 2 several minutes later, a snapshot session should never be held open indefinitely on the server just for UI paging.

You can use a snapshot timestamp `atClusterTime` over a short window while history remains retained, provided tokens have expiration policies. If an exact fixed total is unnecessary, keyset pagination with stable sorting and `hasNext` is usually simpler.

## 17. Snapshot time, keyset, and offset pagination

With filter/sort:

~~~javascript
const filter = {
  tenantId: "tenant-1",
  status: "PAID"
};

const sort = { createdAt: -1, _id: -1 };
~~~

To keep pagination deterministic when multiple documents share the same `createdAt`, include a tie-breaker like `_id`.

### 17.1. Offset does not solve mutating data

~~~javascript
db.orders.find(filter)
  .sort(sort)
  .skip(20)
  .limit(10);
~~~

`skip` becomes expensive on deep pages and positions shift as records are inserted/deleted. A snapshot freezes the dataset at one timestamp, but does not turn deep `skip` into an O(1) jump.

### 17.2. Keyset also does not pin a snapshot by itself

Keyset pagination uses the last key from the previous page:

~~~javascript
{
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

which avoids deep skips, yet pages queried at different times can still see changing data. If pages must reflect the exact same fixed set, combine keyset with snapshot management or product rules.

### 17.3. Designing a token with a timestamp

A token might contain or reference:

~~~json
{
  "after": {
    "createdAt": "2026-10-02T08:00:00Z",
    "_id": 102
  },
  "snapshot": "<opaque-reference>",
  "pageSize": 20
}
~~~

This is an illustrative API-layer structure, **not** a pre-encoded BSON Timestamp. Tokens must be signed/verified and bound to tenant, filter, sort, and expiration. Once snapshot history expires, the old timestamp can no longer be used.

## 18. Snapshot history limits: `minSnapshotHistoryWindowInSeconds`

The storage engine must retain older versions to serve snapshot timestamps. The parameter:

~~~text
minSnapshotHistoryWindowInSeconds
~~~

governs the minimum snapshot history window retained.

MongoDB documentation on long-running snapshot queries cites a default value of **300 seconds** for the WiredTiger history window in that context. However, actual settings may vary by version, topology, and managed service.

### 18.1. When does `SnapshotTooOld` happen?

~~~text
T0: first read pins snapshot T0
    |
    | many new writes + time passes
    |
T1: versions needed for T0 are no longer retained
    |
    v
    SnapshotTooOld
~~~

A snapshot query/session extending past the available snapshot window can fail.

### 18.2. There is no guarantee of "runs for exactly 300 seconds"

Do not interpret the default setting as a hard deadline guaranteeing every read runs exactly 300 seconds before failing. The chosen timestamp, actual retained history, resource pressure, server version, and configuration all matter.

### 18.3. Handling an expired timestamp

1. Do not endlessly retry with the same expired timestamp.
2. Classify it as snapshot expired rather than an empty result.
3. If UX permits, acquire a new snapshot and restart the report.
4. If long-term history is required, use materialized reports, audit/versioning, or appropriate backups/PITR.
5. Measure query latency and optimize to shorten snapshot hold time.

### 18.4. Should you increase the history window?

Increasing history retention increases multi-version storage overhead, I/O, and disk usage. It is an operational decision requiring DBA evaluation against workload, not a simple fix for every slow report.

## 19. Snapshots on secondaries and lagging data

Non-transactional snapshot reads can run on eligible secondaries. The benefit is offloading read work from the primary, though freshness must be understood.

~~~text
Primary:   majority-committed up to T2
Secondary: applied only up to T1

Snapshot without forced time:
  may select a majority-committed snapshot older than T2

Snapshot requesting atClusterTime=T2:
  secondary must wait to catch up to T2
  or query times out if deadline expires
~~~

### 19.1. Stale data does not mean an inconsistent snapshot

If a snapshot is taken at T1 and data is consistent at T1, it is still consistent. However, the API must know whether users accept lag relative to the primary.

### 19.2. Write transactions cannot be routed to secondaries

Using `secondary` read preference for non-transactional snapshots is not a way to send updates/transaction commits to secondaries while the primary is absent.

### 19.3. Long reads still consume secondary resources

A heavy report creates CPU/RAM/disk pressure on a secondary, impacting replication. Never treat "secondary reads" as free or incapable of affecting write workloads.

## 20. Snapshots in sharded clusters

In a sharded cluster, data is distributed across multiple shards. A report reading both shard A and shard B must decide whether they need to reflect **the exact same timestamp**.

### 20.1. Cross-shard consistency

`readConcern:"snapshot"` enables reading majority-committed data from a synchronized view across shards where supported.

### 20.2. Transaction `majority` differs from `snapshot`

In a transaction on a sharded cluster, `readConcern:"majority"` **does not guarantee** all shards are observed at the same snapshot timestamp. When business logic requires a synchronized point in time across all shards, use `readConcern:"snapshot"` in the transaction.

### 20.3. `distinct` on sharded collections

Outside transactions, `distinct` with `snapshot` is restricted to **unsharded collections**. Inside transactions, the `distinct` command on sharded collections also has limitations.

To retrieve distinct values via aggregation:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $sort: { _id: 1 } }
]);
~~~

When running on a real sharded cluster, verify permissions, data, indexes, and stage rules accordingly.

### 20.4. Waiting for shards to catch up to a timestamp

A snapshot query spanning multiple shards may wait for shards to satisfy the timestamp, so latency does not depend solely on returned document count.

## 21. Read concern `snapshot` is not a backup or infinite time travel

| Goal | Primary solution |
|---|---|
| One long query needs a unified view | Snapshot read outside transaction |
| Multiple short reads need the same point in time | Snapshot session |
| Multiple writes must commit/abort atomically | Transaction |
| Multiple collections/shards need a snapshot transaction | Transaction with `readConcern: "snapshot"` |
| Recovering data after accidental deletion | Supported backup/restore or PITR |
| Retaining last month's data history | Event logs, versioned documents, materialized snapshots |
| API needs to reopen results hours later | Persist reports or result sets per contract; do not rely on history window |
| Re-runnable periodic reports | Can materialize output into a dedicated collection |

The BSON Timestamp of `atClusterTime` is meaningful only while version history at that point remains available. It is not a portal back to arbitrary database states from months ago.

## 22. Performance and operational cost

### 22.1. Read concern does not replace indexes

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).readConcern("snapshot");
~~~

still needs proper indexes/filters to run efficiently on large collections. Snapshots do not magically turn collection scans into index scans.

### 22.2. Match and project tightly

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1", status: "PAID" } },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 20 },
    { $project: { _id: 1, status: 1, amount: 1 } }
  ],
  {
    readConcern: { level: "snapshot" },
    maxTimeMS: 5000
  }
);
~~~

A small result set does not guarantee low cost, though selective filters and proper indexes usually reduce how long snapshots are held.

### 22.3. Other limits still apply

- Maximum 16 MiB BSON document output.
- Certain blocking stages require RAM/disk spill.
- Transactions have lifetime limits and write-conflict constraints.
- Cursors return data in batches.
- Secondaries can lag.
- Snapshot timestamps are bounded by history-window limits.

Enabling `snapshot` does not disable any of these limits.

### 22.4. Measure and monitor

Track query latency, `totalDocsExamined`/`totalKeysExamined`, replication lag, `SnapshotTooOld`, transaction aborts, memory/I/O, and end-to-end API latency.

Do not benchmark a single command on a few sample documents and extrapolate to millions of records.

## 23. MongoDB Java Sync Driver: snapshot sessions outside transactions

The Java Driver supports `ClientSessionOptions.builder().snapshot(true)` in driver versions compatible with MongoDB 5.0+.

Example assuming `client` (`MongoClient`) is connected to a valid replica set:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

MongoDatabase database =
    client.getDatabase("snapshot_read_lab");

MongoCollection<Document> orders =
    database.getCollection("orders");

ClientSessionOptions sessionOptions =
    ClientSessionOptions.builder()
        .snapshot(true)
        .build();

try (ClientSession session =
         client.startSession(sessionOptions)) {

    List<Document> items = orders.find(
            session,
            Filters.and(
                Filters.eq("tenantId", "tenant-1"),
                Filters.eq("status", "PAID")
            )
        )
        .limit(2)
        .into(new ArrayList<>());

    List<Document> countRows = orders.aggregate(
            session,
            List.of(
                Aggregates.match(
                    Filters.and(
                        Filters.eq("tenantId", "tenant-1"),
                        Filters.eq("status", "PAID")
                    )
                ),
                Aggregates.count("total")
            )
        )
        .into(new ArrayList<>());

    long total = countRows.isEmpty()
        ? 0
        : ((Number) countRows.get(0).get("total")).longValue();

    System.out.println("items=" + items.size());
    System.out.println("total=" + total);
}
~~~

**Important:** Pass `session` to **every** read, such as `orders.find(session, ...)` and `orders.aggregate(session, ...)`. Any query accidentally omitting `session` does not share the snapshot.

### 23.1. Sequential reads on the same session

`ClientSession` must not be used concurrently across multiple threads. For multiple queries in a snapshot session, execute reads sequentially or design another pattern per driver specifications.

### 23.2. Do not call `startTransaction` on a snapshot session

A Java session created with `snapshot(true)` is exclusively for non-transactional snapshot reads. The driver forbids using it as a transaction session via `startTransaction()`. Create a standard session when a multi-document transaction is needed.

## 24. Java Sync Driver: snapshot transactions

In Java, use `TransactionOptions` to configure read concern at the transaction level:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> accounts =
    client.getDatabase("snapshot_read_lab")
        .getCollection("accounts");

TransactionOptions txOptions =
    TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);

    try {
        Document a = accounts.find(
            session,
            new Document("_id", "A")
        ).first();

        Document b = accounts.find(
            session,
            new Document("_id", "B")
        ).first();

        System.out.println(a);
        System.out.println(b);

        session.commitTransaction();
    } catch (Exception e) {
        try {
            session.abortTransaction();
        } catch (Exception ignored) {
            // Transaction may have already ended.
        }
        throw e;
    }
}
~~~

This snippet illustrates syntax, not a standalone Java program with credentials or `MongoClient` initialization. Production code must implement transaction retries using driver error labels.

### 24.1. Distinguishing the two ways to create a session

| Creation method | Purpose |
|---|---|
| `client.startSession(ClientSessionOptions.builder().snapshot(true).build())` | Multiple snapshot reads **outside transactions** |
| `client.startSession()` then `session.startTransaction(txOptions)` | Transaction with `snapshot` read concern and `majority` write concern |

Never mix both patterns into one session.

### 24.2. Collection-level read concern does not replace transaction-level concern

Outside transactions you can configure:

~~~java
MongoCollection<Document> snapshotOrders =
    orders.withReadConcern(ReadConcern.SNAPSHOT);
~~~

However, inside a transaction, read concern is chosen from transaction options. To keep business requirements explicit, do not rely on a collection handle already having a read concern and omit transaction configuration.

## 25. `mongosh`: interactive read sessions and limitations

### 25.1. Sessions in `mongosh`

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const d = s.getDatabase("snapshot_read_lab");

try {
  const first = d.orders.find({
    status: "PAID"
  }).toArray();

  const second = d.accounts.find({
    tenantId: "tenant-1"
  }).toArray();

  printjson({
    firstCount: first.length,
    secondCount: second.length
  });
} finally {
  s.endSession();
}
~~~

### 25.2. Errors from missing `endSession`

Failing to close sessions when requests end can leak resources or prolong read contexts. Use `try/finally` to ensure `endSession()` is called.

### 25.3. Sessions are not objects to be shared arbitrarily

Never pass the same session to concurrent worker threads or store it in a global application cache shared across users. Sessions hold timestamp/transaction state and require strict boundaries.

## 26. MongoDB Compass

MongoDB Compass is useful for inspecting collections and running aggregations, though session, read concern, and `atClusterTime` options may not be exposed as completely as in `mongosh` or drivers across every version.

Practice workflow:

1. Connect Compass to a test replica set/sharded cluster.
2. Open `snapshot_read_lab.orders`.
3. In the **Aggregations** tab, test `$match` + `$count` to compute total PAID orders.
4. Observe results and compare with `mongosh` running `readConcern:"snapshot"`.
5. If Compass allows configuring read concern, verify the exact options sent.
6. Use `mongosh` to practice snapshot sessions, transactions, or `atClusterTime` when the UI lacks support.
7. Never treat two Compass refreshes returning the same data as proof they used the same snapshot.

Running a pipeline in Compass does not make it a multi-document transaction simply because it contains `$match` or `$group` stages.

## 27. Common errors and misconceptions

| Symptom | Cause | Resolution |
|---|---|---|
| Two majority reads return different results | Not at the same timestamp | Use snapshot session or same `atClusterTime` |
| Two `readConcern:snapshot` commands return different results | Executed independently; may pick different snapshots | Scope within a session/timestamp |
| Snapshot sees older value | Expected for timestamp T | Acquire a newer snapshot if freshness is needed |
| Need two atomic updates, only enabled snapshot | Confused read consistency with write atomicity | Use transaction or atomic data model |
| `count` command rejects snapshot outside transaction | Not on the permitted command list | Use aggregation `$count` |
| `distinct` on sharded collection fails | Command limitation | Consider `$group`/alternatives |
| MongoDB 4.4 rejects snapshot outside transaction | Feature introduced in 5.0 | Use transactions or plan an upgrade |
| Snapshot session paired with `causalConsistency:true` | Mutually exclusive modes | Pick the right session mode |
| Passing `ISODate` to `atClusterTime` | Wrong type and timestamp semantics | Use real BSON Timestamp |
| Secondary lags behind `atClusterTime` | Node has not caught up to T | Wait/timeout or choose primary appropriately |
| `SnapshotTooOld` | Timestamp fell outside retained history | Read fresh snapshot; do not retry expired T endlessly |
| Transaction reads stale document | Snapshot does not pull external concurrent writes | Re-evaluate after transaction; lock if needed |
| Transaction aborts due to write conflict | Incompatible concurrent updates | Retry per transaction protocol |
| Snapshot transaction commits with `w:1` | Lacks full majority-committed snapshot guarantees | Commit with `majority` |
| API `total` mismatches `items` | Different filter/tenant/session or different T | Share exact filter and snapshot |
| Transaction held open for minutes | Lifetime and history/resource pressure | Shorten it; design separate reporting |
| Snapshot on secondary is slow | Lag/I/O/query plan | Measure metrics, indexes, and node capacity |
| Snapshot enabled, yet business data shows intermediate state | Source writes were not atomic | Use transactions for write workflows |
| Snapshot isolation still permits write skew | Does not guarantee all invariants serializable | Use atomic constraints/versioning/coordination |
| Changing read concern to speed up queries | Read concern does not optimize filters/indexes | Optimize queries/indexes |
| Using `atClusterTime` to read last year's data | Older versions no longer in history | Use backups/PITR/materialized history |

## 28. Practice exercises

Exercises use the `snapshot_read_lab` database. Write exercises must run on a test environment and may require reloading Section 5 data.

### Exercise 1. Distinguishing read concern levels

Explain why two `majority` reads can reflect two different points in time, and when a snapshot session is needed instead of `majority`.

### Exercise 2. Snapshot for a single `find`

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
})
.readConcern("snapshot")
.sort({ createdAt: -1, _id: -1 });
~~~

**Initial expectation:** 104, 102, 101. Does this command automatically preserve its timestamp for a second run a few seconds later?

### Exercise 3. Counting with snapshot aggregation

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1", status: "PAID" } },
    { $count: "total" }
  ],
  { readConcern: { level: "snapshot" } }
);
~~~

**Expectation:** `total = 3`. Why not use the `count` command directly with snapshot read concern outside a transaction?

### Exercise 4. Two reads in a snapshot session

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const a = d.accounts.findOne({ _id: "A" });
  const b = d.accounts.findOne({ _id: "B" });
  printjson({ a: a.balance, b: b.balance });
} finally {
  s.endSession();
}
~~~

Which timestamp do both reads use? Is the timestamp pinned at session creation or on the first read?

### Exercise 5. Intervening write

Using Section 9's example, read A in snapshot, modify B outside the session, then read B in snapshot.

**Expectation:** Snapshot read of B still sees 300; normal read after the write sees 350 under appropriate conditions. Explain why this is not a rollback.

### Exercise 6. Where is read concern set inside a transaction?

Rewrite the following correctly:

~~~javascript
session.startTransaction();
txdb.accounts.find({ _id: "A" }).readConcern("snapshot");
~~~

**Hint:** Put `readConcern:{level:"snapshot"}` inside `startTransaction({...})`.

### Exercise 7. Read-your-own-writes

Inside a snapshot transaction, decrement A by 50 and read A back. Why does the read inside the transaction see the new value written by the transaction itself?

### Exercise 8. Majority write concern

Explain why a snapshot transaction committing with `w:1` lacks the same majority-committed snapshot guarantee as committing with `w:"majority"`.

### Exercise 9. `atClusterTime`

Run a snapshot `find` command, capture `first.cursor.atClusterTime`, and pass it into a subsequent snapshot `aggregate` command.

**Question:** Why can you not pass an arbitrary `ISODate` to `atClusterTime`?

### Exercise 10. `SnapshotTooOld`

An API token holds a user's snapshot timestamp from hours ago, and the server no longer retains those older versions.

**Question:** How should the error be handled? Why does retrying endlessly with the same T fail to help?

### Exercise 11. Secondary lag

Primary has reached T2; secondary has only reached T1. When requesting a snapshot at T2 on the secondary, what might the server wait for? How does `maxTimeMS` affect this?

### Exercise 12. Sharded clusters

Why is `majority` read concern in a sharded transaction not equivalent to `snapshot` when a synchronized view across shards is required?

### Exercise 13. Pagination and count

Use a snapshot session to fetch the top 2 PAID orders and compute total via aggregation `$count`.

**Expectation:** `items` has 104/102; `total = 3`. Why must both commands use the same session object?

### Exercise 14. Long-running report

A report takes 10 minutes and repeatedly hits `SnapshotTooOld`.

**Requirement:** Propose optimizing filters/indexes, reducing data scanned, running smaller reports, or materializing results, rather than endlessly increasing the history window.

### Exercise 15. Write skew

Two transactions both read Alice/Bob as on-call, and each sets one person off-duty.

**Question:** Why is `snapshot` insufficient to preserve the invariant "at least one person remains on call"? Propose a versioned coordination document or conditional update.

### Exercise 16. Choosing the right tool

| Need | Choice |
|---|---|
| One long analytical query needing consistent data | Snapshot read outside transaction |
| Multiple related read-only queries, no writes | Snapshot session |
| Multiple updates that must commit together | Multi-document transaction |
| Reads + writes in a transaction across multiple shards | Transaction with `snapshot` read concern |
| Reading recently written data across a request sequence | Consider causal consistency/majority and suitable read preference |
| Saved report copy needing reopening a year later | Materialized report/backup/history, not snapshot window |
| Large list needing only a "Load more" button | Keyset pagination; exact snapshot count may be unnecessary |

## 29. Production deployment checklist

- [ ] Know exact MongoDB server/driver versions and cluster topology.
- [ ] Identify whether the need is **one command**, **multiple reads**, or **multiple writes**.
- [ ] Use non-transactional snapshots only for supported commands.
- [ ] If using a snapshot session, do not enable `causalConsistency` on the same session.
- [ ] Pass the same session to every read that must share the snapshot.
- [ ] If using `atClusterTime`, pass a valid BSON Timestamp and handle expiration.
- [ ] Inside transactions, set read concern at the transaction level.
- [ ] Transactions needing majority-committed snapshots must commit with `w:majority`.
- [ ] Do not set per-write `writeConcern` inside transactions.
- [ ] Understand snapshot transactions can read stale state relative to external commits.
- [ ] Do not expect snapshots alone to protect all invariants against write skew.
- [ ] Have indexes for filters/sorts and bound returned document counts.
- [ ] Set `maxTimeMS`/deadlines and handle errors separately from empty results.
- [ ] Monitor `SnapshotTooOld`, transaction aborts, and replication lag.
- [ ] Avoid keeping sessions/transactions open for extended periods.
- [ ] Do not treat secondary reads as latest data or write-capable.
- [ ] API `total`/`items` share identical filters, tenant, sort, and snapshot when required.
- [ ] Enforce snapshot expiration policies in pagination/reporting.
- [ ] Never treat snapshots as backups or infinite time travel.
- [ ] Critical business writes use appropriate idempotency/transactions.

## 30. Summary

Snapshot reads are a key MongoDB tool enabling a query or group of queries to observe **the same data version at a single logical point in time**.

- **Outside transactions, starting in MongoDB 5.0:** `find`, `aggregate`, and `distinct` on unsharded collections are supported; for multiple reads sharing one timestamp, use a `snapshot:true` session or controlled `atClusterTime`.
- **Inside transactions:** set `readConcern:{level:"snapshot"}` at `startTransaction`; commit with majority write concern when guaranteeing reads from a majority-committed snapshot.
- **Snapshot sessions are not transactions:** they do not make separate writes atomic, have no commit/abort, and cannot be used for transactional writes.
- **Snapshots are not the latest data:** a pinned view can be stale, especially when secondaries lag or data mutates after the timestamp.
- **Snapshots do not persist indefinitely:** history retention is finite and can raise `SnapshotTooOld`.
- **Applications still require solid design:** filters/authorization, indexes, pagination, transaction retries, anti-write-skew invariants, and long-term reporting remain independent concerns.

By clearly defining whether your scope is **a single command, a snapshot session, or a transaction**, you can select snapshot reads matching your exact consistency needs, eliminate time-skewed reports, and avoid unnecessary overhead from long-lived transactions.

## Official references

- [MongoDB Manual — Read Concern snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Perform Long-Running Snapshot Queries](https://www.mongodb.com/docs/manual/tutorial/long-running-queries/)
- [MongoDB Manual — Mongo.startSession](https://www.mongodb.com/docs/manual/reference/method/mongo.startsession/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Configure Operations on Replica Sets](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/)
