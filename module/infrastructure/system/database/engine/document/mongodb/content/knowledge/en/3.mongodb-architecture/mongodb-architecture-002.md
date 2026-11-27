# Path of a Read or Write Request in MongoDB

## 1. From an Application Command to Actual Data

When an application calls `find()`, `insertOne()`, or `updateOne()`, MongoDB does not simply perform a basic operation on a data file. The request passes through multiple layers: **application-side driver → network connection → server selection → command processing → query/storage engine → replication mechanism → response**. In a sharded cluster, there is also the `mongos` routing layer.

Understanding this path helps explain real-world situations:

- Why do two queries with the same filter condition have different latencies?
- Why is a write request already acknowledged on the primary server but not yet visible on a secondary server?
- Why can creating an index reduce the number of documents read without completely eliminating wait time?
- Why does a network error occurring after sending a write command **not prove** that the write failed?
- Why are `writeConcern`, `readConcern`, and `readPreference` three distinct choices?

Let's follow the `orders` collection in the `shop` database:

```javascript
// Example document stored in BSON format.
{
  _id: "ORD-001",
  customerId: "C01",
  status: "PAID",
  total: NumberDecimal("240000"),
  createdAt: ISODate("2026-10-20T09:00:00Z")
}
```

An application might request the 10 newest orders for a customer or insert a new order. Although the syntax used is very short, the processing behind it depends on the **MongoDB deployment model**, **query plan**, **consistency/durability configuration**, and **cluster state at execution time**.

## 2. Participating Components

| Component | Role in the Path |
|---|---|
| **Application + MongoDB driver** | Constructs commands, encodes/decodes BSON, manages sessions, connections, and server selection |
| **Connection pool** | Reuses TCP/TLS connections; avoids opening a new connection for every operation |
| **`mongod`** | Server process that executes commands, checks permissions, plans queries, and manages data |
| **Primary in a replica set** | Main server that normally receives write operations and generates change entries for replication |
| **Secondary in a replica set** | Receives and applies change entries from the primary; can serve reads depending on configuration |
| **`mongos`** | Router that receives commands from applications in a sharded cluster and sends them to the appropriate shards |
| **Config server** | Stores sharded cluster metadata: which collections are sharded, data range distribution, etc. |
| **WiredTiger** | MongoDB's default storage engine, responsible for cache, storage structures, and supporting data durability mechanisms |
| **Index** | Structure supporting searching/sorting for certain query patterns, complementing document data |
| **Oplog** | Ordered operations log in a replica set used by secondaries to replay changes |

**Distinguishing two common topologies:**

- **Unsharded replica set:** the application connects to member `mongod` instances; the driver selects an eligible member to execute the command.
- **Sharded cluster:** the application connects through one or more `mongos` instances; each shard is typically a replica set and data is split across multiple shards.

The server behind the driver can be either a `mongod` or a `mongos`. This is the most important branching point when tracing a request's path.

### 2.1. Replica Set Diagram

```text
  Application
      |
  MongoDB driver ── Connection pool, topology discovery
      |
      | Write command (default)
      v
  mongod PRIMARY  ────── WiredTiger read/write
      |                         |
      |                         +-- Cache, data, indexes
      |                         +-- Journal / checkpoint
      |
      +---- oplog / replication ----> mongod SECONDARY 1
      |
      +---- oplog / replication ----> mongod SECONDARY 2

  Read command:
    readPreference=primary   -> primary
    readPreference=secondary -> eligible secondary
```

The diagram shows the **logical path**, not claiming that network steps, journal writes, checkpoints, or replication always occur in a rigid linear order. MongoDB handles many tasks concurrently and optimizes according to version, topology, and system load.

## 3. Before Reading or Writing: The Driver Chooses Where to Send the Command

### 3.1. Opening Connections and Discovering Topology

Example replica set URI:

```text
mongodb://mongo-a.example:27017,mongo-b.example:27017,mongo-c.example:27017/shop?replicaSet=rs0
```

This is an illustrative URI. The driver does not treat the host list as a random list of addresses to try blindly. It uses **Server Discovery and Monitoring (SDAM)** to identify the topology, primary/secondary roles, server health, and capability to satisfy read/write options. During this process, the driver exchanges information such as the `hello` command, tracks topology changes, and maintains a set of connections in the pool.

When needing to execute a command, the driver typically:

1. Determines whether the request is a read or a write and checks accompanying options.
2. Selects a server satisfying `readPreference`, operation type, and topology state; in a sharded cluster, selects an appropriate `mongos`.
3. Acquires an available connection from the pool or establishes one when needed; performs authentication and TLS protection if configured.
4. Encodes the command and input data as BSON and sends it over the MongoDB network protocol.
5. Reads the BSON response and converts it into corresponding language objects or exceptions.

**Not every command requires a network handshake, login, or full topology re-discovery.** The driver continuously updates state and reuses connections. Waiting for an idle connection or server selection timeout can still add latency before the server starts executing the query.

### 3.2. Three Easily Confused Option Groups

| Option | Applies Primarily To | Question It Answers |
|---|---|---|
| `readPreference` | Reads | **Where to read from?** Primary, secondary, or another preferred configuration? |
| `readConcern` | Reads | **At what consistency level is data allowed to be seen?** |
| `writeConcern` | Writes | **What acknowledgments are required before reporting the write as successful?** |

These three options work together but do not replace one another. For example, reading from a secondary with `readConcern: "majority"` means reading majority-committed data available on that secondary; it **does not guarantee** that the secondary has caught up with the latest changes on the primary.

## 4. Detailed Path of a Read Request

Suppose the application needs the 10 newest orders for customer `C01`:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, _id: 0 }
).sort({ createdAt: -1 }).limit(10);
```

### Step 1 — Driver Packages and Sends the Command

The driver builds a BSON command with components equivalent to `find`, `filter`, `projection`, `sort`, and `limit`. `mongosh` provides the friendly `find()` syntax; what actually gets transmitted to the server is a MongoDB protocol command.

In a replica set with default configuration, the driver normally selects the primary for reads. If the application selects `secondaryPreferred`, the driver may select a suitable secondary; when no suitable secondary is available, it can fall back to the primary. With other read modes, selection rules differ.

### Step 2 — Server Validates the Command and Permissions

`mongod` receives the command on an established connection, checks syntax, database/collection context, access permissions, and command options. An invalid or unauthorized command can be rejected here before reading any documents.

If `readConcern` is specified, MongoDB must also provide a view of the data consistent with the requested isolation/consistency level. Some requests may have to wait until data state satisfies the read condition.

### Step 3 — Query Planner Selects How to Retrieve Documents

The server analyzes filter conditions, sort order, and projection. The planner may consider execution strategies such as:

- **Collection scan (`COLLSCAN`):** sequentially reads relevant documents in the collection.
- **Index scan (`IXSCAN`):** uses an index to narrow the search range or leverage key ordering.
- **Index scan then fetch:** locates index keys first, then reads the document BSON to verify/complete the result.
- **Covered query:** when appropriate conditions are met, uses only information inside the index without reading the base document.

If the query above runs frequently, consider:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

With two equality conditions preceding `createdAt`, this index has a good chance of helping filter and retrieve data in newest-first order. However, **having an index does not mean the planner is guaranteed to choose it**; the plan depends on data, selectivity, statistics, and many other factors.

### Step 4 — Storage Engine Retrieves Keys and BSON Documents

When the execution engine needs index keys or documents, the storage engine fetches data through WiredTiger's storage structures. Data may already reside in **cache** or need to be read from disk. A query backed by an index may still have to read many documents if the projection or filter is not fully contained in the index.

WiredTiger uses concurrency control mechanisms and versioned data views so reads and writes can proceed concurrently. Do not imagine that every read command locks the entire collection until completion.

### Step 5 — Filtering, Sorting, Projecting, and Returning Results

The server applies the remaining parts of the query: additional filtering, sorting if the index could not satisfy the sort order, projecting fields, and limiting result count. For large results, the server may return **a first batch and a cursor ID**. The driver then sends `getMore` to fetch subsequent batches; this is still one logical read operation on the application side, though it may involve multiple network round-trips.

```text
find() in application
      |
      v
Driver selects server and sends BSON command
      |
      v
mongod: checks permissions + readConcern
      |
      v
Query planner / execution engine
      |
      +--> index scan ---------+
      |                        |
      +--> collection scan     v
                           WiredTiger
                         cache / disk
                              |
                              v
                     Filter / sort / projection
                              |
                              v
                     BSON batch + cursor
                              |
                              v
                    Driver returns to application
                         (getMore if needed)
```

Key takeaway: the read process involves **two distinct costs**: reaching the right server (connection, server selection, routing) and retrieving/processing the right data (indexes, cache, disk, sorting, cursors).

### 4.1. Reading from Primary, Secondary, and Consistency Levels

| Option | Basic Meaning | Limitations to Remember |
|---|---|---|
| `readPreference: primary` | Reads from primary, default in a replica set | Does not automatically turn `readConcern: local` into majority-committed data |
| `readPreference: secondary` | Reads from a suitable secondary | May see stale data relative to the primary |
| `readPreference: secondaryPreferred` | Prefers secondary, can fall back to primary | Actual read target depends on topology at selection time |
| `readConcern: local` | Reads data currently available on the selected member | May include writes not yet majority-committed and subject to rollback |
| `readConcern: majority` | Reads data acknowledged as majority-committed | Not necessarily the newest state across the entire cluster |
| `readConcern: snapshot` | Reads from a consistent data snapshot at a supported point in time | Depends on operation/transaction context and deployment requirements |
| `readConcern: linearizable` | Applies to eligible reads on the primary, providing strong real-time ordering guarantees | Has its own constraints and waiting overhead; not a universal default |

Read concern levels have varying support conditions depending on version and operation type. In particular, configuring `secondary` does not by itself guarantee immediately reading a write that just completed. For flows requiring **read-your-writes** across multiple nodes, applications should understand causal consistency sessions along with appropriate `readConcern` and `writeConcern` settings, rather than assuming all members synchronize instantaneously.

## 5. Detailed Path of a Write Request

Consider an order insert command:

```javascript
db.runCommand({
  insert: "orders",
  documents: [{
    _id: "ORD-002",
    customerId: "C01",
    status: "PAID",
    total: NumberDecimal("480000"),
    createdAt: ISODate("2026-10-21T09:00:00Z")
  }],
  writeConcern: { w: "majority", wtimeout: 5000 }
});
```

This example uses a database-level command to make `writeConcern` explicit. In an application, the driver provides equivalent APIs like `insertOne()` with write options.

### Step 1 — Selecting the Server to Receive the Write

In a standard replica set, write operations are directed to the **primary**. The driver may already know the primary through topology monitoring; when the primary changes after a failure, the driver must update its information and re-select the target.

In a sharded cluster, the command first goes to `mongos`; the router determines the relevant shard, and then the shard primary processes the write.

### Step 2 — Validating the Command and Constraints

The server verifies authentication/permissions, BSON structure, document size, schema validation rules if configured, and index-related constraints. For example, `_id` must be unique within a collection; writing a duplicate unique key returns a **duplicate key** error.

For `updateOne()`, the server must also locate the document matching the filter condition before modifying it. Therefore, indexes can strongly impact **conditional write** performance, even though indexes themselves must also be updated after modifying the data.

### Step 3 — Storage Engine Applies the Change

The primary uses WiredTiger to apply changes to the document and related indexes. MongoDB provides **single-document atomicity**: an update to a single document is applied as a single unit, even when modifying multiple fields within that document.

Concurrent execution capability does not mean two commands contending for the same document always run without friction; the system may wait, resolve conflicts, or require retries depending on the operation type. Commands modifying **multiple documents** do not automatically form an atomic transaction over the whole set unless an appropriate transaction is used.

WiredTiger manages data in cache and provides durability through the **journal** and periodic **checkpoints**. Do not imagine that every `insertOne()` waits for an entire document to be flushed into the final data files before replying; response timing depends on the requested write guarantees.

### Step 4 — Recording the Change in Replication History

In a replica set, the primary generates change entries for the **oplog**. Secondaries pull and apply the oplog sequentially to update their copies. This activity is not strictly synchronous with the moment the application sends the command; at any instant, a secondary may still be lagging behind the primary.

During replication:

1. The primary performs the change and records the change information according to the replica set mechanism.
2. Secondaries receive unapplied oplog entries.
3. Secondaries replay the changes on data and indexes on their own nodes.
4. Member acknowledgment status determines when the operation satisfies `writeConcern`.

This describes **logical causal relationships**. Exact timing of journal writes, commits, and change synchronization is coordinated internally by MongoDB, not a rigid per-command network broadcast schedule.

### Step 5 — Acknowledging the Write per Write Concern

MongoDB returns a result once the requested write conditions are met, or returns an error/timeout message accordingly. Three commonly seen configurations:

| Illustrative Configuration | When Considered Satisfied | What to Understand |
|---|---|---|
| `{ w: 1 }` | Primary has acknowledged the write | Does not require majority acknowledgment; write can be rolled back upon failover |
| `{ w: "majority" }` | Write has been acknowledged according to the majority rule of data-bearing voting members in the replica set | Increases survival guarantee across failovers compared to `w: 1`; wait time may be higher |
| `{ w: "majority", j: true }` | In addition to majority acknowledgment, requires journal durability guarantees as configured | `j` controls journal durability requirements, does not replace `w` |

In a replica set with a primary and two voting secondaries, `w: "majority"` normally requires **two out of three members** to acknowledge. An **arbiter** member does not store data and therefore does not substitute for a data-bearing copy in protecting records.

Distinguish clearly:

- **Journal:** supports local state recovery after a process/machine crash.
- **Checkpoint:** periodically advances storage state to a durable milestone; not every write ACK waits for a new checkpoint.
- **Oplog/replication:** replicates changes across nodes to maintain multiple copies of data.
- **Write concern:** condition that must be met before the client receives acknowledgment.

The combination of journal and majority guarantees depends on the storage engine, version, and replica set configuration. You cannot infer from `w: "majority"` alone that all nodes have flushed every data file to the latest checkpoint.

### 5.1. Timeout Does Not Mean Data Was Not Written

In the `wtimeout: 5000` example, the primary may have already applied the command while secondaries acknowledged slowly. When the write concern timeout expires, the client receives a write concern error even though **the write effect may have already occurred**. Similarly, if the network drops after the primary processed the command but before the client received the ACK, the final state from the client's perspective may be ambiguous.

Therefore, do not automatically re-issue the same write command with a new ID after every error. You can:

- Check the outcome using a business key or stable `_id`.
- Use the driver's **retryable writes** feature when the operation/topology meets support conditions.
- Design operations to be safely repeatable (idempotent) when needed, especially for payments, order creation, and event processing.

Retryable writes also do not mean every type of write or every error is automatically retried. You must distinguish data errors (e.g., duplicate unique key), connection drops, failovers, and write concern errors.

### 5.2. Two Write Acknowledgment Cases on the Same Replica Set

```text
                   Replica set: P, S1, S2

Client ---- insert ----> P (primary)
                         |
                         +-- apply change
                         +-- write oplog
                         |
                         +-------------> S1 (receive/apply oplog)
                         |
                         +-------------> S2 (receive/apply oplog)

  w:1       -> ACK can arrive after acknowledgment from P
  w:majority-> waits for majority acknowledgment condition (e.g. P + S1)

  ACK does not say that all secondaries have caught up.
```

This example is not meant to prescribe a physical ordering among cache/journal/oplog writes or the exact ACK arrival order across nodes, but simply to explain the **acknowledgment threshold**.

## 6. With Sharding: Adding the Routing Layer

MongoDB can split a collection across multiple **shards** based on a **shard key**. Normal applications do not need to know on their own which shard holds a document: they connect to `mongos`.

```text
                         APPLICATION
                              |
                            Driver
                              |
                         mongos router
                              |
                   Routing metadata (cache)
                      from config servers
                       /             \
                      v               v
                  SHARD A           SHARD B
                replica set       replica set
               P / S1 / S2       P / S1 / S2
                    |                  |
                 WiredTiger         WiredTiger
```

### 6.1. Reads in a Sharded Cluster

Suppose the collection is sharded by `customerId`. With the query:

```javascript
db.orders.find({ customerId: "C01" });
```

If the router has enough shard key information to determine where `C01` is stored, it can perform a **targeted query** to the relevant shard. If the query only specifies `status: "PAID"` and lacks sufficient information to select a shard, `mongos` may have to send it to **multiple shards (scatter-gather)** and merge the results.

When `sort`, `limit`, or aggregation is involved, the router and shards may divide the work. Merging results can introduce additional network, CPU, and memory overhead; the response time of a multi-shard query can also be affected by the slowest shard.

### 6.2. Writes in a Sharded Cluster

For an insert command, `mongos` relies on the shard key and metadata to determine the target shard. That shard's primary executes the write and replicates it within the shard's replica set. For certain write forms lacking enough information to select a single shard, MongoDB has different rules and limitations depending on the operation, shard key choice, and version; do not assume a write command will automatically update across all shards.

If metadata changes due to data range migrations, the router may need to refresh its information and re-route. Data migration is an additional operational layer, but it **does not replace** storage or replication mechanisms within each shard.

### 6.3. Multi-Document, Multi-Shard Transactions

Operations on a **single document** still have single-document atomicity guarantees. When business logic requires updating multiple documents or collections simultaneously as one unit, a **multi-document transaction** can be used if the topology supports it. In a sharded cluster, multi-shard transactions require commit coordination across participants; latency overhead and failure modes are more complex than a single write command.

Do not default to running every application command inside a transaction. Most simple operations are processed by the server as standalone commands.

## 7. Comparing the Read Path and Write Path

| Stage | Read Request | Write Request |
|---|---|---|
| Starting point | Driver sends `find`/`aggregate` | Driver sends `insert`/`update`/`delete` |
| Server selection | Per `readPreference` and topology | Normally directed to replica set primary or `mongos` |
| Consistency rules | `readConcern` determines visible data level | `writeConcern` determines acknowledgment threshold |
| Data access | Query planner selects index or scans documents | May use index to find records to modify; must update affected indexes |
| Storage engine | Reads from cache/disk, applies appropriate data view | Modifies documents/indexes, uses journal/checkpoint mechanisms |
| Replica set | Secondaries can serve reads but may lag | Primary generates changes and secondaries replicate |
| Returned result | Documents or batches/cursors | Write result or error; post-network-error state may be uncertain |
| Common bottlenecks | Scanning many documents, sort, I/O, getMore, routing | Write contention, number of indexes to update, journal, replication, and write concern |

A **read** command must answer "which data to fetch, from which replica, at what consistency level?". A **write** command must answer "what to modify, where to write, how many acknowledgments are enough?".

## 8. Observing the Path with MongoDB Tools

You do not need to guess whether a slow query is caused by the network, indexes, or the replica set. Inspect the relevant layer directly.

### 8.1. Inspecting Read Plans

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Commonly useful fields/indicators:

| Indicator | Interpretation |
|---|---|
| `COLLSCAN` | A collection scan occurred |
| `IXSCAN` | An index scan occurred |
| `FETCH` | A document fetch step occurred after reading index keys |
| `SORT` | Shows whether a separate sort stage outside index order occurred |
| `totalKeysExamined` | How many index keys were examined |
| `totalDocsExamined` | How many documents were examined |
| `nReturned` | How many results were returned |

Plan structure and some stage names may vary across MongoDB versions and execution engines. `explain()` helps analyze **server-side execution**, but does not capture server selection wait time, connection pool queuing, network transit between application and server, or the application's full cursor consumption time.

### 8.2. Identifying the Connected Topology

```javascript
// Returns information about the server/router receiving commands.
db.adminCommand({ hello: 1 });

// In a replica set, when the account has appropriate privileges:
rs.status();
```

`hello` can provide information to identify primary/secondary roles and replica set members. In a sharded cluster, the response from `mongos` differs from that of a replica set `mongod`. `rs.status()` must be run in an appropriate context and may require corresponding monitoring privileges.

When analyzing production, combine metrics on replication lag, connection counts, read/write latency, cache/I/O, and driver wait times. These metrics complement `explain`, rather than being replaced by it.

## 9. Illustrative Scenarios

### Scenario A — Index Exists, Yet Reads Remain Slow

A query filters `status: "PAID"` in a collection where most orders are `PAID`. An index on `status` may not narrow the input dataset much. If the application also sorts on a field not aligned with the index or returns many megabytes, document fetch time and transferring multiple batches remain significant.

**How to reason:** check filter selectivity, proportion of matching documents, chosen index, sort stage, actual documents read, and result size. Do not look only at whether an index "exists."

### Scenario B — Write Is ACKed, Yet Secondary Does Not Show It

The application writes to the primary with `w: 1` and immediately reads from a secondary. The read may hit a secondary that has not yet applied the corresponding oplog entry. A read missing the new order is a symptom of replication lag, not sufficient grounds to conclude the earlier write never executed.

**How to reason:** review `readPreference`, `readConcern`, `writeConcern`, replication status, and session-based consistency needs.

### Scenario C — Write Returns Write Concern Timeout

The primary accepts the operation, but secondaries experience high lag; the command requested `w: "majority"` with a short timeout. The application may receive a write concern timeout error even though the primary has already modified the data.

**How to reason:** distinguish command execution failure from failing to satisfy the acknowledgment threshold. Re-check using a stable key or use safe retry mechanisms before creating another business transaction.

### Scenario D — A Query Becomes Slower After Sharding

Before sharding, the query scanned one collection on a single replica set; after sharding, the same expression lacking the shard key causes `mongos` to broadcast to multiple shards. Total routing, distributed processing, and result-merging overhead can increase even if each shard processes less data.

**How to reason:** determine whether the query is targeted or scatter-gather, check whether the shard key appears in the filter, and check where sort/aggregation executes.

## 10. Practicing Along the Real Request Path

You can perform the steps below in a test MongoDB environment without modifying production configurations:

1. Create an `orders` collection with fields `customerId`, `status`, `createdAt`, and at least several distinct documents.
2. Run a `find` with filter, sort, and `explain("executionStats")`; observe index scan/collection scan **before** creating a compound index.
3. Create index `{ customerId: 1, status: 1, createdAt: -1 }` and re-check the plan. On a very small dataset, the planner might still choose a collection scan.
4. If you have a test replica set, inspect `hello` and primary/secondary status; verify the current connection session's read preference before testing secondary reads.
5. Send a write command with a `writeConcern` appropriate for the test environment. Distinguish the returned write result from the observed replication state.
6. If you have a test sharded cluster, compare queries with and without the shard key in terms of shards targeted and result-merging cost.

### Self-Check Questions

1. Why can `find()` generate multiple network round-trips even though the application calls it once?
2. Why do `readPreference: secondary` and `readConcern: majority` not equate to "always reading the newest data"?
3. When running `updateOne()` with a filter condition, which parts of the write process can indexes affect?
4. What is the difference between the journal, checkpoints, and the oplog?
5. With `w: 1`, if the primary loses its role immediately after ACK, what risk can the application face?
6. Why is `wtimeout` or losing the connection after sending a write insufficient to conclude that the operation was not applied?
7. How does a query missing the shard key affect routing at `mongos`?

**Connecting the main idea:** MongoDB is a multi-layered system. **The driver decides where to send commands; `mongod` or `mongos` routes and processes; the query planner and WiredTiger decide how to read/write; the replica set and read/write concern decide data visibility and acknowledgment thresholds.** When an operation is slow or returns unexpected results, tracing the exact request path helps isolate the problem more accurately.
