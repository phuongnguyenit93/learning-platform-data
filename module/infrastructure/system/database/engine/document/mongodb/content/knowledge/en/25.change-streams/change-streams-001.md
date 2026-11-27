# Change Tracking Goals and Deployment Prerequisites for Change Streams in MongoDB

## 1. Why Does an Application Need to Know When Data Has Just Changed?

In many applications, a MongoDB write operation is not the end of the business workflow. When an order is updated, other components may need to know in order to perform follow-up work:

- Send a notification when the order status changes to **SHIPPED**.
- Refresh the cache when product information changes.
- Synchronize a subset of data to a search system.
- Update summary tables or materialized views.
- Push changes to reporting, monitoring, or ETL services.
- Display a near-real-time change feed for collaborative applications.

For example, in the **orders** collection:

~~~javascript
{
  _id: "ORD-100",
  tenantId: "SHOP-A",
  customerId: "CUS-01",
  status: "PENDING",
  totalCents: NumberLong(350000)
}
~~~

When the application runs:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100", tenantId: "SHOP-A" },
  { $set: { status: "PAID" } }
);
~~~

another service wants to receive a signal:

~~~text
Order ORD-100 was updated
Field status: "PAID"
Collection: orders
Operation: update
~~~

Without a change-tracking mechanism, the consuming service must continuously query the database:

~~~text
Every few seconds:
  QUERY orders WHERE updatedAt > lastCheck
  -> process results
  -> sleep
  -> repeat
~~~

This **polling** approach both generates periodic query load and easily leads to incorrect handling if timestamps collide, indexes are missing, changes happen between reads, or documents are deleted.

**MongoDB Change Streams** allow applications to **subscribe to data change events** on a collection, a database, or an entire deployment without having to directly read and decode the oplog themselves. This is a built-in **change data capture (CDC)** mechanism in MongoDB.

The goal of this lesson is to understand **what it is used for, what infrastructure requirements it has, how to verify eligibility, and what limitations to prepare for before deploying**.

## 2. Goals of Change Streams

Change Streams solve the problem of **detecting changes that have occurred in MongoDB and delivering that information to consumers** in near real time.

Key capabilities:

1. **Track write events** such as insert, update, replace, and delete.
2. **Limit the watch scope** from a single collection to a database or an entire deployment.
3. **Filter events** using compatible aggregation pipeline stages.
4. **Receive metadata**: operation type, document identifier, namespace, logical timestamp, and descriptions of changed fields.
5. **Resume after connection interruptions** using a resume token as long as the oplog history remains available.
6. **Integrate with event-driven architectures** to trigger synchronization, indexing, notifications, and reporting.

Change Streams are a stream of events about **operations written to MongoDB**, not automatic callbacks for every business event.

~~~text
User confirms payment
          |
          v
Backend verifies with payment provider
          |
          v
MongoDB updates order.status = PAID
          |
          v
Change Stream emits update event
          |
          v
Consumer receives event and updates cache/reports
~~~

The consumer knows there was an update event on the `status` field, but looking only at the database change **does not by itself prove that the provider actually collected the money**. The business service must still enforce payment rules, security, and idempotency.

### 2.1. Appropriate Use Cases

| Need | How Change Streams Help |
|---|---|
| Search synchronization | When a product changes, the consumer updates an index outside MongoDB. |
| Cache invalidation | When a relevant field changes, delete or update the cache key. |
| Realtime UI | The backend pushes events over WebSocket/SSE to authorized users. |
| Operational audit support | Record change metadata for observability systems. |
| Materialized view | Update aggregated data based on source writes. |
| ETL/CDC | Forward deltas to another data pipeline. |
| Microservices integration | React to durable changes in the database. |

### 2.2. Things Change Streams Do Not Guarantee on Their Own

Change Streams are **not**:

- A multi-source message broker replacing Kafka/RabbitMQ in every scenario.
- A permanent audit history with infinite replay capability.
- An end-to-end exactly-once mechanism for email, cache, Elasticsearch, or HTTP APIs.
- A full snapshot of all documents existing prior to opening the stream.
- A transaction spanning MongoDB and external systems.
- A replacement for authorization, schema validation, or business rules.
- A tool for predicting changes **before a write is committed**.

A sound architecture typically combines Change Streams with **idempotent consumers, checkpoints, monitoring, reconciliation**, and sometimes a **transactional outbox**.

## 3. How Do Change Streams Differ from Polling and Tailing the Oplog Directly?

### 3.1. Polling by updatedAt

~~~javascript
db.orders.find({
  updatedAt: { $gt: lastCheckedAt }
});
~~~

Advantages: simple when the collection has an appropriate index; works on standalone MongoDB; the application controls the interval. Limitations: repeated queries even when there are no writes; interval-based latency; deletes leave no document to read; every write path must update the timestamp; requires pagination and handling duplicate timestamps.

### 3.2. Tailing the Oplog Directly

The oplog is the replica set's operation log. Reading the oplog directly requires understanding internal formats, topology, transaction semantics, and resume/failover handling; those internal details can change across versions.

Change Streams provide a higher-level API:

~~~javascript
const stream = db.orders.watch();
~~~

Instead of forcing consumers to decode raw oplog entries, MongoDB returns **change event documents** following the Change Streams schema.

### 3.3. Comparison

| Criterion | Polling | Direct Oplog Tailing | Change Streams |
|---|---|---|---|
| Requires replica set/sharded cluster | Not strictly required. | Requires an oplog. | **Yes**, standalone is not supported. |
| Delete detection | Requires soft delete/tombstone. | Possible, but complex. | Provides delete events. |
| Near real-time | Interval-based. | Yes. | Yes, once event emission conditions are met. |
| Dedicated API | Standard queries. | Oplog-dependent. | **watch() / ChangeStream**. |
| Resume after disconnect | Manage checkpoints manually. | Manage extensive logic manually. | Resume token provided. |
| History retention | Depends on design. | Oplog window. | **Oplog window**. |
| Downstream exactly-once | Must design yourself. | Must design yourself. | **Still must design yourself**. |

**Change Streams are suitable** when the source of changes is MongoDB, delta-based processing is needed, the deployment is a replica set or sharded cluster, and downtime fits within the resumable window.

**Polling** may be suitable when only simple batch processing is needed or on standalone instances.

A **message broker/outbox** is often suitable when clear domain event contracts, long retention, multiple consumer groups, or events originating from multiple systems are required.

## 4. How Change Streams Work Conceptually

A simplified flow with a replica set:

~~~text
                  MongoDB Replica Set
  +----------------------------------------------+
  |  Primary                                     |
  |    |                                         |
  |    +-- writes to data                        |
  |    +-- replication log (oplog)               |
  |                |                             |
  |                +----> Secondary A            |
  |                +----> Secondary B            |
  |                                              |
  |      majority-committed change               |
  |                |                             |
  +----------------|-----------------------------+
                   |
                   v
        Change Stream watch() cursor
                   |
                   v
         Change event {operationType,...}
                   |
                   v
            Application consumer
~~~

MongoDB emits a notification once a change is **majority-committed across data-bearing members**. It does not immediately emit every operation applied locally on the primary that is not yet majority-committed.

### 4.1. Majority-Committed Does Not Mean Every Consumer Receives It Instantly

Events must traverse replication, cursor/getMore, the network, and the consumer. There is **end-to-end latency**:

~~~text
Write
  -> majority commit
  -> server constructs change event
  -> cursor/getMore
  -> application processing
  -> downstream acknowledgement
~~~

Change Streams are **near-real-time**, not hard real-time with a fixed deadline.

### 4.2. Distinguish Write Acknowledgement from Event Arrival Time

A write with **w:1** can receive a response before majority commit. The Change Stream will not necessarily emit the event at that moment.

A write with **w:"majority"** is acknowledged after achieving majority write concern, but the event still must be delivered via the cursor to the consumer. Do not use event arrival time to infer the exact moment the client received the write result.

### 4.3. Change Streams Do Not Automatically Synchronize External Data

~~~text
MongoDB change event
        |
        v
Consumer processEvent()
        |
        +-- update cache
        +-- index search
        +-- publish message
~~~

This is application behavior written by developers. If the consumer fails, the Change Stream does not automatically roll back the source document.

## 5. Three Change-Watching Scopes

### 5.1. Collection-level: db.collection.watch()

~~~javascript
const stream = db.orders.watch();
~~~

Receives only events related to the `orders` collection. Ideal when a service only cares about orders, needs tight permission boundaries, and wants to reduce complexity.

### 5.2. Database-level: db.watch()

~~~javascript
const stream = db.watch();
~~~

Receives events from **non-system collections in the current database**. The **ns.db** and **ns.coll** fields allow routing events by source.

### 5.3. Deployment-level: Mongo.watch()

In mongosh:

~~~javascript
const stream = db.getMongo().watch();
~~~

Watches **non-system collections across the deployment** subject to MongoDB limitations. This scope requires broad privileges and can generate more load.

### 5.4. Scope Selection Table

| Scope | mongosh Command | Considerations |
|---|---|---|
| Collection | **db.orders.watch()** | Fewer events, narrow permissions. |
| Database | **db.watch()** | Multiple schemas, requires database-wide permissions. |
| Deployment | **db.getMongo().watch()** | Broad permissions, requires governance and routing. |

**Choose the smallest scope that satisfies requirements**; do not watch the entire deployment by default for a service that only needs `orders`.

### 5.5. Namespace Limitations

MongoDB documentation excludes **system collections** and collections in system databases such as **admin, local, config** from standard Change Streams scopes. Do not treat a database watch as a tool to receive every internal MongoDB change.

## 6. Topology Prerequisites

### 6.1. Replica Set or Sharded Cluster Required

**Standalone MongoDB does not support Change Streams** because the feature relies on the **replica set oplog** to generate and resume events.

~~~text
✅ Single-node replica set for local development
✅ Multi-member replica set
✅ Sharded cluster with replica set shards
✅ Managed MongoDB deployment supporting change streams

❌ Pure standalone MongoDB
❌ A mongod process without replica set configuration
~~~

A single-node replica set is **sufficient for testing syntax and local consumers**, but **does not fully simulate** majority durability, failover, or secondary lag.

### 6.2. WiredTiger and Replica Set Protocol

MongoDB requires replica sets/sharded clusters to use the **WiredTiger storage engine** and **replica set protocol version 1 (pv1)** for Change Streams.

In modern MongoDB, WiredTiger and pv1 are standard, but you should still verify the actual server/topology before deployment.

### 6.3. Do You Need to Enable Read Concern Majority Separately?

According to MongoDB documentation, **Change Streams are available whether deployment-level read concern majority support is enabled or disabled**, though events are still only emitted once changes are majority-committed.

Therefore, do not rely on outdated advice such as "you must enable readConcern majority configuration for Change Streams to run" as a blanket rule across all versions.

### 6.4. Sharded Clusters Must Connect Through mongos

For a replica set, open a Change Stream from a **data-bearing member** according to read preference/driver behavior.

For a sharded cluster, open the stream through **mongos** so MongoDB merges and handles events from the shards.

~~~text
Client/Consumer
      |
      v
    mongos
     / \
    v   v
 Shard A  Shard B
    |       |
    +-- MongoDB sorts/filters events --+
                                       |
                                       v
                                    Consumer
~~~

Do not manually tail each shard and merge them using a naive timestamp if you need the semantics of a sharded Change Stream.

### 6.5. Checking Topology

In mongosh:

~~~javascript
db.hello();
~~~

Hints:

- The **setName** field typically indicates the replica set name.
- The **msg:"isdbgrid"** field indicates `mongos`.
- Standalone has no replica set name and is not `mongos`.

Do not infer topology solely from hostnames or the number of hosts in a URI.

### 6.6. Local Development: Single-Node Replica Set

Example **only on a test machine with no real data**:

~~~bash
# The dbpath must point to an existing data directory.
mongod --dbpath ./mongo-data --replSet rs0 --bind_ip 127.0.0.1 --port 27017
~~~

Open mongosh in another terminal:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "127.0.0.1:27017" }
  ]
});

rs.status();
~~~

Wait for the node to become PRIMARY, then connect using the corresponding local URI:

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0
~~~

**Do not run these topology-conversion commands directly on a live production MongoDB instance.** Configuring a real replica set requires backups, security/authentication, proper hostnames/networking, an appropriate rolling deployment, and driver URI configuration.

### 6.7. MongoDB Atlas and Managed Deployments

When using a managed cluster, verify that the deployment type/tier supports Change Streams, along with URI, TLS, network allowlists, RBAC, oplog retention, and connection pools. Do not assume every managed tier or serverless option behaves identically; check the provider's documentation and your active version.

## 7. MongoDB Server and Driver Version Requirements

Change Streams were introduced in **MongoDB 3.6** for replica sets and extended to sharded deployments. Several additional features require newer server versions:

| Capability | Version Milestone | Notes |
|---|---|---|
| Change Streams on replica set | **MongoDB 3.6** | Initial change-tracking API. |
| Sharded/deployment scope support | **MongoDB 4.0** | Must connect through mongos. |
| Reject pipelines altering event _id | **MongoDB 4.2+** | Event `_id` is the resume token. |
| Performance improvements for certain stages | **MongoDB 5.1+** | Does not eliminate cursor/getMore overhead. |
| Document pre- and post-images | **MongoDB 6.0+** | Must be enabled at the collection level when used. |
| Split large change stream events | **MongoDB 7.0+** | For exceptionally large events. |

These milestones serve as a guide; **do not copy APIs from newer version documentation into an older server without checking compatibility**. The Java Driver, Spring Data MongoDB, MongoDB server, and Stable API settings all need matching compatible versions.

### 7.1. Time Series Collections

According to current MongoDB Change Streams documentation, **time series collections do not support Change Streams** because their specialized storage format does not track document-level changes directly like standard collections.

If you need to emit events when time-series data is written, you can use domain events/outbox in a regular collection or design a separate ingestion pipeline.

### 7.2. Views and System Collections

Views do not have an independent oplog of writes like a physical collection. Do not assume watching a view works like watching its underlying source collection. System collections and the `admin`/`local`/`config` databases have API restrictions.

### 7.3. Stable API

Change Streams are part of MongoDB **Stable API V1**; certain extended options such as **showExpandedEvents** are not part of Stable API V1. When using **apiStrict**, check the specific feature against your chosen API version.

## 8. Access Control and Security

In a deployment with authorization enabled, MongoDB requires two actions:

- **find**
- **changeStream**

Their resource scope must match the scope being watched.

### 8.1. Collection-level Privilege

To watch **appdb.orders**:

~~~javascript
{
  resource: {
    db: "appdb",
    collection: "orders"
  },
  actions: [
    "find",
    "changeStream"
  ]
}
~~~

Example creating a custom role if you have administrative privileges:

~~~javascript
use appdb

db.createRole({
  role: "ordersChangeReader",
  privileges: [
    {
      resource: {
        db: "appdb",
        collection: "orders"
      },
      actions: ["find", "changeStream"]
    }
  ],
  roles: []
});
~~~

An administrator can then assign this role to the appropriate service account. Never embed passwords in source code.

### 8.2. Database-level Privilege

Watching a database requires **find + changeStream** on the non-system collections of that database:

~~~javascript
{
  resource: {
    db: "appdb",
    collection: ""
  },
  actions: ["find", "changeStream"]
}
~~~

### 8.3. Deployment-level Privilege

Watching the entire deployment requires privileges covering non-system collections across all databases:

~~~javascript
{
  resource: {
    db: "",
    collection: ""
  },
  actions: ["find", "changeStream"]
}
~~~

This is a very broad privilege; grant it only to necessary CDC infrastructure with appropriate governance.

### 8.4. Protecting Data After Receiving Events

Change events can contain customer identifiers, addresses, business payloads, or entire documents when `fullDocument`/pre-images are enabled. You should:

1. Authenticate service identities and grant only the minimal namespace privileges.
2. Use TLS, a secret manager, and rotate credentials.
3. Avoid logging entire documents containing sensitive data.
4. Enforce tenant/authorization checks **before pushing events over WebSocket/SSE to end users**.
5. Apply retention policies for checkpoints, logs, pre-images, and downstream stores.
6. Monitor authorization errors explicitly instead of retrying infinitely.

**Change Streams do not automatically enforce end-user access permissions when a backend forwards data.**

## 9. Hands-On: Your First Change Stream in mongosh

Prerequisite: connected to a **replica set or sharded cluster that supports Change Streams**, with the required permissions. Use a test database:

~~~javascript
use change_stream_lab
db.createCollection("orders");
~~~

Run **db.createCollection** only once; if the collection already exists, skip the creation step.

### 9.1. Terminal A: Open the Stream First

~~~javascript
use change_stream_lab

const stream = db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: [
            "insert",
            "update",
            "replace",
            "delete"
          ]
        }
      }
    }
  ],
  {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

while (stream.hasNext()) {
  const event = stream.next();
  printjson(event);
}
~~~

**The `hasNext`/`next` calls block waiting for events**, so Terminal A may look idle. This is normal behavior for a long-lived cursor. Stop it by interrupting the loop/closing the cursor appropriately; in applications, call **close()** during shutdown.

### 9.2. Terminal B: Generate Changes to Test

Open a mongosh session **connected to the same MongoDB deployment/database**:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "ORD-001",
  tenantId: "SHOP-A",
  status: "PENDING",
  totalCents: NumberLong(250000)
});

db.orders.updateOne(
  { _id: "ORD-001" },
  {
    $set: {
      status: "PAID"
    }
  }
);

db.orders.replaceOne(
  { _id: "ORD-001" },
  {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PACKING",
    totalCents: NumberLong(250000)
  }
);

db.orders.deleteOne({ _id: "ORD-001" });
~~~

Terminal A will receive the corresponding events if the stream is running and connectivity/replication are healthy.

**Testing note:** if you run this snippet again against data in a different state, results may differ. You must open the stream **before performing writes** if you want to observe new writes under default watching behavior.

### 9.3. Without Terminal B, What Does Terminal A Do?

The Change Stream cursor waits and sends `getMore` requests to fetch events. **Having no new documents** is not an error condition. A production client should have proper shutdown, timeout, and heartbeat/monitoring mechanisms.

### 9.4. Read Operations Do Not Emit Change Stream Events

~~~javascript
db.orders.find({ status: "PAID" });
~~~

A **find** query does not generate an insert/update/delete event. Change Streams track **data changes**, not user read operations.

### 9.5. Watch Is Not a Snapshot Query of Existing Data

If the collection already contains 100,000 orders before opening the stream, calling **watch()** does not automatically emit 100,000 insert events. To obtain **initial state + subsequent changes**, you must design a bootstrap and delta-sync workflow with checkpointing to avoid gaps or duplicates.

## 10. Structure of a Change Stream Event

An abridged **insert event** example (token/timestamp values are illustrative):

~~~javascript
{
  _id: {
    _data: "<opaque-resume-token>"
  },
  operationType: "insert",
  clusterTime: Timestamp(1, 1),
  ns: {
    db: "change_stream_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-001"
  },
  fullDocument: {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PENDING",
    totalCents: NumberLong(250000)
  }
}
~~~

**This is not a real token for resuming**; tokens are generated by MongoDB and use an internal format. Do not fabricate tokens by concatenating timestamps or document `_id`s.

### 10.1. Key Fields

| Field | Meaning |
|---|---|
| **_id** | **Resume token of the change event**, not the order's `_id`. |
| **operationType** | Operation type: insert, update, replace, delete, etc. |
| **ns.db / ns.coll** | Database and collection of the event. |
| **documentKey** | Identifier of the changed document; in a sharded collection, may include shard key fields. |
| **clusterTime** | Logical timestamp of the change; not synonymous with an exact wall-clock timestamp for business SLAs. |
| **fullDocument** | The full document for certain events/options. |
| **updateDescription** | Describes fields updated/removed in an update event. |
| **lsid / txnNumber** | May appear for operations associated with a transaction. |

### 10.2. Update Event

Example:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  ns: {
    db: "change_stream_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

**By default, update events are delta-oriented** and do not always carry the entire post-update document. If a consumer needs other fields, it must choose a `fullDocument` strategy or query the document itself.

### 10.3. Replace Event

~~~javascript
{
  operationType: "replace",
  documentKey: { _id: "ORD-001" },
  fullDocument: {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PACKING",
    totalCents: NumberLong(250000)
  }
}
~~~

A **replace** differs from an **update**: it replaces the matched document (subject to `_id` rules), so the event payload can include `fullDocument` rather than a field-by-field delta.

### 10.4. Delete Event

~~~javascript
{
  operationType: "delete",
  documentKey: {
    _id: "ORD-001"
  }
}
~~~

After a delete, the document is no longer in the collection. **There is no post-delete `fullDocument` to look up**. If you need the pre-delete content, consider pre-images or a soft-delete/audit design.

### 10.5. Do Not Confuse the Two _id Fields

~~~text
changeEvent._id
  -> Resume token
  -> Used to resume the stream

changeEvent.documentKey._id
  -> Source document identifier
  -> Used to update cache/search projections
~~~

A very common mistake is saving `documentKey._id` and passing it as `resumeAfter`. That is **invalid** because `resumeAfter` requires a **server-generated token**.

## 11. Operation Types and Lifecycle Events

Typically, consumers care about:

| Operation | Meaning |
|---|---|
| **insert** | A document was inserted. |
| **update** | Fields of a document were modified. |
| **replace** | A document was replaced. |
| **delete** | A document was deleted. |
| **invalidate** | The stream was invalidated in lifecycle situations such as collection drop/rename. |
| **drop / rename / dropDatabase** | Certain DDL/lifecycle changes depending on scope. |

Other event types may appear on specific server versions or options, especially when **showExpandedEvents** is enabled. Do not hardcode a rigid enum assuming the database will never emit new event types.

### 11.1. Invalidation Requires Separate Recovery Handling

If a collection is dropped or renamed, the stream may receive **invalidate** and close. This is not simply a transient network disconnect.

**resumeAfter** cannot be used to resume **after an invalidate event**. MongoDB provides **startAfter** to open a new stream after an invalidate event when supported conditions are met.

If the consumer still needs to watch a recreated collection, it may need to reinitialize state/namespaces and check schemas. Do not swallow `invalidate` and keep looping with the old cursor.

### 11.2. No-op Writes and Events

Do not assume every `updateOne` request from the application produces a separate event if no data actually changed. Change Streams focus on changes recorded by MongoDB; an update that produces no actual modification may not emit the expected event.

If requirements demand one event **per business command**, use domain events/outbox rather than relying solely on document change events.

## 12. fullDocument, updateLookup, and Pre-/Post-Images

### 12.1. updateLookup

For update events, you can request:

~~~javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

MongoDB can look up and return the **current majority-committed version of the document at the time the lookup runs**.

**Common pitfall:** `updateLookup` is not an exact point-in-time snapshot from when the event was created. If another update occurs between the original operation and the lookup, `fullDocument` may reflect the newer state.

Example:

~~~text
T1: status -> PAID      (Event E1)
T2: status -> PACKING   (Event E2)
T3: Consumer processes E1 with updateLookup

E1.updateDescription.status = "PAID"
E1.fullDocument may reflect "PACKING"
~~~

If you need the exact document state **immediately before/after the event**, you must understand pre-/post-image semantics and their version requirements.

### 12.2. Pre- and Post-Images (MongoDB 6.0+)

Starting in MongoDB 6.0, you can enable the collection-level option:

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

Then you can request:

~~~javascript
const stream = db.orders.watch([], {
  fullDocumentBeforeChange: "whenAvailable",
  fullDocument: "whenAvailable"
});
~~~

Available modes:

- **whenAvailable:** returns the image if available; does not fail by default if the image is missing.
- **required:** requires the image; if unavailable under server conditions, returns an error.
- **updateLookup:** looks up the current document for updates; not equivalent to the exact post-image at the time of the change.

A **pre-image** is the document before update/replace/delete. A **post-image** is the document after insert/update/replace where supported; deletes have no post-image.

### 12.3. Cost of Pre-/Post-Images

Enabling pre-/post-images:

- Increases storage and processing overhead.
- Involves retention and cleanup processes.
- Does not provide infinite history.
- Can cause large events to exceed the BSON size limit.

Enable them only when genuinely needed and with proper sizing/retention planning.

### 12.4. The 16 MiB Limit and Large Events

MongoDB has a standard **16 MiB** BSON document size limit. If an event includes `fullDocument`, pre-image, and a large `updateDescription`, the event itself may exceed this limit.

Starting in MongoDB 7.0, **$changeStreamSplitLargeEvent** can be used in special cases to split large events, though it requires version/driver support and consumers must handle fragments. Do not enable it by default if your data does not require it.

## 13. Filtering Events Directly in the Change Stream

Change Streams are built on the aggregation framework. When calling **watch(pipeline, options)**, the application can supply a pipeline to receive only needed events.

### 13.1. Watch Only Insert and Update

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
~~~

This is a **filter on the event envelope**, not a direct query on the source document.

### 13.2. Care Only About Status Changes

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": {
        $exists: true
      }
    }
  }
]);
~~~

This pipeline selects **update events** where the `status` field appears in `updatedFields`.

**Limitation:** it does not catch every status change performed via **replace** or another event shape. If the goal is "every time effective status changes", decide explicitly how to handle **replace**, pre-/post-images, and source data.

### 13.3. Filtering Namespaces in a Database Watch

~~~javascript
const stream = db.watch([
  {
    $match: {
      "ns.coll": {
        $in: ["orders", "products"]
      }
    }
  }
]);
~~~

Not every lifecycle event has the exact same fields; pipeline filters must account for the schema of the selected event types.

### 13.4. Avoid Transformations That Strip the Resume Token

Event **_id** is the resume token. Never use a pipeline that removes, replaces, or recomputes **event._id**:

~~~javascript
// Do not do this:
db.orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      documentKey: 1
    }
  }
]);
~~~

Starting in MongoDB 4.2, Change Streams return an error if the pipeline modifies event **_id**. If you want a compact DTO for downstream systems, construct it **inside the consumer after extracting/persisting the resume token**.

### 13.5. Not Every Aggregation Stage Belongs in a Stream

A Change Stream pipeline is not an ordinary reporting aggregation where any stage can be used. For example, write stages like **$out** or **$merge** are not suitable in a change stream pipeline, and the **$changeStream** stage generated by `watch()` must follow proper placement/semantics.

Only use stages supported by MongoDB for Change Streams on your server version; check stage restrictions when transforming the event envelope.

### 13.6. Event Filtering Does Not Enforce Data Security

Having a backend watch an entire database and filter by `tenantId` is only an optimization/routing technique—it **does not replace access control** in MongoDB or at the API/WebSocket layer. Some delete events lack `fullDocument`, so you need `documentKey` or a safe mapping to determine the proper tenant.

## 14. Resume Tokens: Conditions for Resuming a Consumer

### 14.1. A Token Is Not an Ordinary Timestamp

Each change event has an **_id** field containing an **opaque resume token**:

~~~javascript
{
  _id: {
    _data: "..."
  },
  operationType: "update",
  documentKey: { _id: "ORD-001" }
}
~~~

Tokens are generated by the server to pinpoint a position in the change stream. **Do not convert a token into a timestamp string, reconstruct it from a document ID, or alter the BSON content of the token**.

### 14.2. resumeAfter

A consumer finishes processing event E1 and saves its token:

~~~javascript
const savedToken = event._id;
~~~

After restarting:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    resumeAfter: savedToken
  }
);
~~~

**resumeAfter** instructs the server to resume **after the event identified by the specified token**.

Note: **savedToken** in this example must be the real BSON object saved and restored accurately, not the literal string `"..."` or an order ID.

### 14.3. startAfter

If a change stream is **invalidated** due to collection drop/rename, you cannot use `resumeAfter` to continue past an invalidate token. **startAfter** allows opening a new stream after an invalidate event under MongoDB-supported semantics:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

The consumer may still need to reinitialize schemas/projections once the collection is recreated.

### 14.4. startAtOperationTime

You can start from a server **BSON Timestamp** within the retained oplog window:

~~~javascript
db.orders.watch(
  [],
  {
    startAtOperationTime: savedBsonTimestamp
  }
);
~~~

However, logical operation time is not a convenient substitute for a resume token when a token is available. If using timestamps, preserve the exact BSON type and understand boundary semantics and possible duplicates.

### 14.5. Only One Appropriate Starting Option

The **resumeAfter**, **startAfter**, and **startAtOperationTime** options are not three parameters to set arbitrarily at the same time. Choose the one mechanism matching your recovery state; do not cram every option into a single `watch` request.

### 14.6. Oplog Retention Is Mandatory for Resuming

A resume token is only useful while the server **still retains sufficient oplog history** to locate the corresponding event.

~~~text
Oplog history window
|-------------------------------------------|
T0                                          Tnow

Consumer checkpoint at Tc:

If Tc is within the window -> can resume

If Tc has fallen out of the window -> resume may fail
                                    -> must reinitialize
                                       state and bootstrap
~~~

This is a major operational risk with Change Streams. **Resuming after arbitrarily long downtime is never guaranteed**, even if the token was saved accurately.

### 14.7. Post-Batch Resume Token / Highwatermark

The server can also return a **postBatchResumeToken** when fetching a batch; this acts as a **highwatermark token** marking progress even when no new business events matched. Drivers manage tokens through the appropriate cursor APIs.

Production consumers must distinguish:

- The **event token** of an already processed change.
- The **highwatermark/post-batch token** indicating stream progress.
- The application's **durably persisted checkpoint**.

Do not persist a newer token before prior events have been successfully processed; doing so risks skipping unfinished work.

### 14.8. Resume with the Same Pipeline/Options

MongoDB recommends resuming with **the same pipeline and options used when the token was created**. Changing the pipeline can alter visible events or even make resuming fail.

If you upgrade a consumer version and change its schema/filter, plan a checkpoint/bootstrap migration instead of simply passing an old token to a completely new pipeline.

## 15. Checkpoints: Where and When to Save?

### 15.1. Simple Rule

A consumer reads an event, processes side effects, and then checkpoints the token:

~~~text
Read event E1
      |
      v
Process E1
      |
      v
Persist E1 resume token
      |
      v
Read E2
~~~

If you record the token **before processing E1**, and the process crashes:

~~~text
Checkpoint E1
     |
     X crash before Process E1

ResumeAfter(E1) -> E1 is skipped!
~~~

If you process **before checkpointing**, and the process crashes:

~~~text
Process E1 succeeds
     |
     X crash before Checkpoint E1

Resume from old token -> E1 may be processed again
~~~

The second scenario is generally preferable **provided the consumer is idempotent**.

### 15.2. At-Least-Once Application Processing

In real-world deployments, consumers should be designed assuming **events may be delivered or processed more than once** on connection errors, retries, or unpersisted checkpoints.

Change Streams provide a resume mechanism, but **do not automatically guarantee end-to-end exactly-once delivery** for downstream systems.

A practical strategy:

1. Process keyed by **event token/business entity ID**.
2. Upsert state instead of inserting duplicate records without unique keys.
3. Maintain **processed event IDs** or versions to ignore already applied events.
4. If both the effect and checkpoint reside in the same MongoDB deployment, consider atomic updates or transactions where appropriate.
5. For systems outside MongoDB, use sink idempotency, an outbox, or reconciliation.

### 15.3. Cache Update Example

Given an update event:

~~~javascript
{
  operationType: "update",
  documentKey: {
    _id: "ORD-001"
  }
}
~~~

The consumer can delete the cache key:

~~~text
DEL cache:order:ORD-001
~~~

Deleting a cache key is typically idempotent: running it twice leaves the key absent. However, the consumer must still ensure proper authorization, event ordering, and eventual refresh.

### 15.4. Search Index Update Example

For insert/replace/update, a consumer can query the current state and **upsert** into the index by document ID. For delete, remove the index entry by ID.

Key caveats:

- `updateLookup` may return a newer document than the event itself.
- Replayed events must not create duplicate search documents.
- A slow consumer might overwrite the index with an older version if ordering/versioning is not enforced.
- If the oplog window is lost, a full reindex may be required.

### 15.5. Multiple Consumer Instances

Change Streams **do not natively provide Kafka-style consumer group partitioning**. If two instances both open `watch` on the same scope, both receive the same events.

When scaling horizontally, establish a clear pattern:

- A single logical consumer has **one active owner** (leader election/lease).
- Or multiple consumers receive events and perform **idempotent/deduplicated** processing.
- Or forward events to a broker that supports consumer groups.

Never assume MongoDB automatically splits each event to only one of two service instances.

## 16. Bootstrap: Capturing Initial Data Before Tracking Changes

Change Streams observe **changes**; they do not automatically provide a full snapshot of the collection.

Suppose you need to build a search index from a `products` collection that already holds 1 million documents:

~~~text
MongoDB products
        |
        +-- Initial full scan  -> Search index baseline
        |
        +-- Change stream      -> incremental updates
~~~

### 16.1. Race Condition Between Snapshot and Watch

Dangerous pattern:

~~~text
T1: Scan all documents
T2: A document is deleted
T3: Open Change Stream

The delete at T2 is missed from the stream.
The search index may retain the deleted document.
~~~

**Do not simply run a full scan and open `watch` afterward** if writes can occur between the two steps.

### 16.2. A Safer Bootstrap Design

A conceptual strategy:

1. Open the Change Stream or capture a server-supported starting point.
2. Start the initial scan/snapshot using a consistent definition.
3. During the scan, **buffer or maintain a backlog** of incoming events.
4. Complete the baseline load.
5. **Replay events** from the recorded starting point with appropriate ordering/idempotency.
6. Transition to continuous consumption.
7. Checkpoint only once events have actually been applied.

Exact details depend on consistency requirements, sharding, snapshot support, and data size; do not treat this outline as a copy-paste production algorithm without handling races.

### 16.3. Losing the Oplog During Bootstrap

If the initial scan takes too long and the starting point falls out of the oplog window, you cannot guarantee replaying all deltas from the old token. You must **restart the bootstrap** with a fresh starting point or use a CDC mechanism with adequate retention.

## 17. Connection Pools, Cursors, and Resources

### 17.1. A Change Stream Is a Long-Lived Cursor

A Change Stream keeps a cursor open to await events. **getMore** calls waiting for events can occupy a connection from the pool.

MongoDB warns that if the number of active change streams exceeds the connection pool size, **notification latency** can occur. Therefore, size the pool based on the number of open streams plus regular query workload.

~~~text
MongoClient pool (maxPoolSize = N)
         |
         +-- stream 1: getMore
         +-- stream 2: getMore
         +-- stream 3: getMore
         +-- HTTP query A
         +-- HTTP query B
~~~

If multiple streams consume most connections, HTTP queries may block waiting for a connection. Consider a **dedicated MongoClient pool for CDC consumers** when an application runs many long-lived streams.

### 17.2. Never Open a New Watch per HTTP Request

Dangerous pattern:

~~~text
GET /orders
  -> create new MongoClient
  -> open db.orders.watch()
  -> wait for event

GET /orders
  -> create another MongoClient
  -> open another watch()
~~~

Each request increases connection/cursor counts and leaks resources.

Proper design:

- One or a few long-lived consumers managed by the service.
- Share a properly sized `MongoClient`/pool.
- Fan out notifications to internal WebSocket/SSE subscribers via an in-app router.
- Close cursors on service shutdown and handle cancellation/errors.

### 17.3. The Java Synchronous API Is Blocking

With the Java Sync Driver, iterating a Change Stream cursor typically **blocks waiting for events**. Never run an infinite wait loop on an HTTP request thread or event-loop thread.

Use a dedicated worker thread, managed executor, or appropriate reactive solution. Spring Data documentation recommends the reactive variant where suitable because a sync listener requires a long-running task.

### 17.4. maxAwaitTimeMS Is Not a Total Processing Deadline

**maxAwaitTimeMS** controls how long the server waits during a single `getMore`. It does not cause the stream to terminate after that duration; the cursor keeps awaiting across multiple rounds.

Applications need separate shutdown deadlines, connection timeouts, and processing timeouts.

### 17.5. Sharded Clusters Have Different Overhead

When opening a Change Stream on a sharded cluster, **mongos** opens corresponding streams on the shards and handles ordering/filtering, sometimes adding `fullDocument` lookups. Having many shards and many streams increases overhead.

Do not assume a collection-level scope only uses one connection or reads from a single shard in all sharded scenarios.

### 17.6. Oplog Window and Event Generation Rate

Oplog retention should not be assumed to be a fixed number of days. Depending on oplog size configuration, write rate, and retention settings, older entries can be evicted once capacity or time limits are reached.

Under heavy write throughput, **the oplog window can shrink**, causing a consumer disconnected for just a few hours to lose its ability to resume. Monitor this and provision capacity accordingly.

## 18. Java Sync Driver: Opening a Change Stream Properly

The MongoDB Java Sync Driver provides:

- **MongoClient.watch()** for deployment scope.
- **MongoDatabase.watch()** for database scope.
- **MongoCollection.watch()** for collection scope.

This returns a **ChangeStreamIterable**, from which you can obtain a **MongoChangeStreamCursor** to receive events.

### 18.1. Program Watching Orders

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;
import java.util.concurrent.TimeUnit;

public final class OrdersChangeStreamDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must point to a replica set or sharded cluster"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("change_stream_lab");
            MongoCollection<Document> orders =
                    database.getCollection("orders");

            List<Bson> pipeline = List.of(
                    Aggregates.match(
                            Filters.in(
                                    "operationType",
                                    List.of("insert", "update", "replace", "delete")
                            )
                    )
            );

            ChangeStreamIterable<Document> iterable = orders
                    .watch(pipeline)
                    .fullDocument(FullDocument.UPDATE_LOOKUP)
                    .maxAwaitTime(2, TimeUnit.SECONDS);

            try (
                    MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                            cursor = iterable.cursor()
            ) {
                while (!Thread.currentThread().isInterrupted()) {
                    ChangeStreamDocument<Document> event = cursor.tryNext();

                    if (event == null) {
                        continue;
                    }

                    System.out.println(
                            "Event type: " + event.getOperationType()
                    );
                    System.out.println(
                            "Document key: " + event.getDocumentKey()
                    );

                    Document fullDocument = event.getFullDocument();
                    if (fullDocument != null) {
                        System.out.println(fullDocument.toJson());
                    }

                    BsonDocument resumeToken = event.getResumeToken();

                    // In production:
                    // 1) Process the event using an idempotent operation.
                    // 2) Only after processing succeeds,
                    //    checkpoint resumeToken to durable storage.
                    System.out.println(
                            "Resume token: " + resumeToken.toJson()
                    );
                }
            }
        }
    }
}
~~~

The snippet above **only prints the token for illustration**; it lacks durable checkpoint persistence and production retry/recovery policies.

### 18.2. Why Is a Dedicated Worker Needed?

**MongoChangeStreamCursor.tryNext()** can wait while awaiting a batch from the server. Placing this loop inside an HTTP controller ties up request threads unnecessarily.

Production consumers should run under a **managed worker/service lifecycle** with shutdown signals, cancellation, and proper cursor closure.

### 18.3. Event API Methods to Note

~~~java
event.getResumeToken();   // BsonDocument token used for resuming.
event.getDocumentKey();   // BsonDocument identifying the source document.
event.getFullDocument();  // Document if present for the option/event.
event.getOperationType(); // Operation type.
event.getClusterTime();   // Logical BSON timestamp.
~~~

Do not confuse **getDocumentKey()** with **getResumeToken()**.

### 18.4. Resuming from a Saved Token

~~~java
// savedToken must be a real BSON token obtained from an event/cursor.
BsonDocument savedToken = loadResumeTokenFromCheckpoint();

ChangeStreamIterable<Document> iterable = orders
        .watch()
        .resumeAfter(savedToken)
        .fullDocument(FullDocument.UPDATE_LOOKUP);
~~~

**loadResumeTokenFromCheckpoint()** in this example is an application-implemented helper, not a built-in MongoDB driver API.

When implementing this function:

1. Store the token in BSON format preserving all data faithfully.
2. Use the same change stream pipeline/options as when the token was generated.
3. Handle the case where the token has fallen outside the oplog window.
4. Do not silently ignore resume errors and start from "now" if the business cannot tolerate missed deltas.

### 18.5. Connection URI and Client Lifecycle

A replica set URI might look like:

~~~text
mongodb://db1.example:27017,db2.example:27017,db3.example:27017/?replicaSet=rs0
~~~

Or using **mongodb+srv** when supported by the provider:

~~~text
mongodb+srv://<user>:<password>@cluster.example/?retryWrites=true
~~~

These are illustrative URIs, not reachable endpoints. Never hardcode credentials in source code, and never create a new `MongoClient` per event.

### 18.6. The Java Sync Driver Does Not Guarantee Exactly-Once

The driver can automatically resume after certain resumable errors according to its semantics, but **it has no visibility into whether downstream processing succeeded**.

If an event was sent to a search index before its token was checkpointed, the consumer may receive the event again after a restart. Design **idempotent upserts**, unique business IDs, or transactionally store both results and checkpoints in the same MongoDB deployment where appropriate.

## 19. Spring Data MongoDB: Change Streams with Reactive and Imperative APIs

Spring Data MongoDB supports Change Streams on both imperative and reactive drivers.

### 19.1. ReactiveMongoTemplate

With Spring Data MongoDB Reactive, you can write:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.core.Disposable;

public final class ReactiveOrdersListener {
    private final ReactiveMongoTemplate template;

    public ReactiveOrdersListener(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Disposable start() {
        Flux<ChangeStreamEvent<Document>> changes = template
                .changeStream(Document.class)
                .watchCollection("orders")
                .listen();

        return changes.subscribe(
                event -> {
                    Document body = event.getBody();
                    System.out.println("Change: " + body);
                    System.out.println("Token: " + event.getResumeToken());
                    // Production: forward to an idempotent processing
                    // pipeline and checkpoint the token.
                },
                error -> {
                    System.err.println("Change stream failed: " + error);
                    // Production: classify resumable/non-resumable errors,
                    // restart from checkpoint with a backoff policy.
                }
        );
    }
}
~~~

**Disposable** is used to cancel the subscription during service shutdown. This is an illustrative reactive flow example, not a complete error-handling and checkpointing implementation.

### 19.2. Reactive Does Not Automatically Make Everything Faster

The reactive model is well suited for I/O-bound streams and managing non-blocking subscribers. However, if a consumer processes each event with long CPU-bound tasks or calls a blocking HTTP API directly inside the subscriber, bottlenecks still occur.

You need to structure:

- Proper backpressure/flow control.
- Appropriate schedulers or non-blocking clients.
- Downstream concurrency limits.
- Per-entity ordering if required by business logic.
- Retry/resume token handling and error routing.

### 19.3. Imperative MessageListenerContainer

Spring Data also supports **DefaultMessageListenerContainer** and **ChangeStreamRequest** for imperative applications. This mechanism spawns a task listening for events on the sync driver.

Key points to remember:

1. **A sync Change Stream blocks a thread** while waiting for data, so the listener container requires a dedicated thread/task.
2. Create and register subscription requests with the collection scope/options.
3. Register an **ErrorHandler** to handle stream errors rather than leaving exceptions solely in logs.
4. Stop the container during application shutdown.
5. When watching a database with diverse document types, use the **Document** type when events cannot all map to a single fixed entity.

### 19.4. Do Not Equate ChangeStreamEvent with an Entity

A change event is not merely a Product/Order entity; it includes metadata—**operationType, resumeToken, documentKey**—and may **not contain `fullDocument`** in operations like delete.

Spring Data mapping must properly handle the distinction between the event envelope and the domain document.

### 19.5. Spring Data Resume API

Spring Data `ChangeStreamOptions` supports resuming from a token or server time via its supported APIs. When resuming by time, pay attention to BSON timestamp precision. When an exact resume token is available, prefer the token.

Official documentation provides examples of **resumeAt** and reading **ChangeStreamEvent.getResumeToken()**; verify exact API signatures for your Spring Data version.

## 20. When to Use Change Streams, Outbox, or a Message Broker?

### 20.1. Change Streams for Data-Driven Projections

For example, when a product's name/price changes:

~~~text
MongoDB products
      |
      v
Change Stream
      |
      v
Search Index Consumer
      |
      v
Elasticsearch / OpenSearch
~~~

The consumer needs to know which document changed and update the projection. Change Streams fit well because the requirement is tied directly to persisted data changes.

### 20.2. Transactional Outbox for Domain Events

A money-transfer workflow may require an explicit event such as **TransferCompleted** rather than three separate raw changes across two account documents and a transfers collection.

~~~text
MongoDB transaction:
  update source account
  update target account
  insert transfer record
  insert outbox event
           |
           v
      COMMIT
           |
           v
Change Stream on outbox
           |
           v
Publisher -> Message Broker
~~~

In this pattern, the Change Stream **detects committed outbox events**, while the outbox document provides the **business event contract**.

### 20.3. Why Not Just Watch Orders and Send Email Immediately?

If an email sender processes an event and crashes before checkpointing:

~~~text
Send email succeeds
       |
       X crash
       |
Resume same event
       |
       v
Send email a second time
~~~

To prevent duplicate emails, you need an idempotency key or a durably updated delivery-status record. Change Streams cannot unsend an email.

### 20.4. Message Brokers for Fan-Out and Long-Term Replay

When dozens of independent consumer groups exist, or events must be retained for months and replayed by offset, a dedicated broker may be better suited for distribution.

A common architecture:

~~~text
MongoDB
  |
  +-- Change Stream Reader
         |
         +-- Normalize / Validate / Enrich
         |
         v
      Kafka topic
         |
         +-- Search projection consumer
         +-- Analytics consumer
         +-- Notification consumer
~~~

Architecture selection depends on throughput, retention, SLAs, failover, replay semantics, and operations. Do not assume Change Streams universally "lose" or "win" against a broker for every problem.

## 21. Data Changes in Transactions and Special Cases

### 21.1. Change Events from Multi-Document Transactions

MongoDB emits events for committed changes and may attach **lsid, txnNumber**. Events must be interpreted in the context of committed transactions; uncommitted operations are not emitted.

If a transaction aborts, uncommitted writes from that transaction are not emitted as durable changes.

### 21.2. Do Not Infer a Whole Business Transaction from One Event

A transaction might update `orders`, `payments`, and `inventory`. A consumer watching **orders** only sees changes within the `orders` scope, not a full summary of the transaction.

If downstream systems need a consolidated **OrderPlaced/PaymentSettled** event with a stable schema, use an **outbox/domain event**.

### 21.3. Deletes and TTL

Deletes emit corresponding events when recorded, but since the document is gone, there is no `fullDocument` to look up. If you need tenant information or old fields to clean up projections, maintain a mapping, use `documentKey`/shard key, or enable pre-images where supported.

Do not rely on **updatedAt polling** to detect all deletes; Change Streams handle this cleanly via delete events.

### 21.4. Sharded documentKey Does Not Always Contain Only _id

In a sharded collection, **documentKey** may contain shard key fields in addition to `_id`. When constructing cache keys or queries, understand the shard key, schema, and potentially missing fields.

Do not assume every `documentKey` has the exact structure **{_id:...}** across all sharded deployments and versions.

### 21.5. DDL Operations

Collection drop/rename can invalidate a stream; expanded events such as create or index-related events require corresponding options/versions. Consumers must distinguish:

- Document data changes.
- Schema/collection lifecycle changes.
- Internal MongoDB operations not emitted under standard scopes.

## 22. Questions to Answer Before Deploying to Production

### 22.1. What Is the Processing Goal?

State it clearly:

~~~text
When the orders collection has a status change,
the consumer refreshes the order projection in the search index.

Target latency: per application SLA.
Duplicate events tolerable: yes, with idempotent handling.
Resumable downtime: must remain within the oplog window.
On history loss: execute full reconciliation/rebuild.
~~~

Without defining the downstream action and acceptable latency, you lack enough information to choose scope, resources, and recovery.

### 22.2. Does the Deployment Meet Prerequisites?

Verify:

- It is a replica set or sharded cluster, not standalone.
- Compatible storage engine (WiredTiger) and protocol pv1.
- MongoDB server and driver versions support the intended options.
- URI matches the topology; sharded clusters connect via `mongos`.
- User/service account has **find + changeStream** on the required scope.
- Networking/TLS and authentication work reliably.

### 22.3. Do You Need fullDocument or Pre-/Post-Images?

Consider:

- Is **updateDescription** sufficient for the consumer?
- If the current document is needed, is it acceptable that **updateLookup may be newer than the event**?
- If exact before/after snapshots are needed, are pre-/post-images supported and enabled?
- Could document sizes cause events to exceed 16 MiB?
- Would sensitive data be exposed more broadly than necessary?

Do not enable `fullDocument`/pre-images just because they are "available," as they increase load and data exposure.

### 22.4. How Does the Consumer Handle Duplicates?

Define an **idempotency strategy**:

| Downstream Type | Example Strategy |
|---|---|
| Cache | Deleting/invalidating the same key multiple times remains safe. |
| Search index | Upsert by document ID/version without creating duplicate entries. |
| Analytics | Deduplicate by event token/business event ID or use versioned upserts. |
| Email | Unique notification key and persisted delivery state. |
| Payment provider | Provider idempotency key; never charge directly from raw change events. |

If a consumer cannot tolerate duplicate processing, it must not go to production with just a `while(hasNext())` loop.

### 22.5. Where Is the Token Stored?

Example **change_stream_checkpoints** collection:

~~~javascript
{
  _id: "orders-search-index-v1",
  consumerName: "orders-search-index",
  token: {
    _data: "<opaque-resume-token>"
  },
  pipelineVersion: 1,
  updatedAt: ISODate("2026-07-01T00:00:00Z")
}
~~~

This is an illustrative schema; real tokens are generated by MongoDB. **Preserve the token's BSON type**. If multiple instances could write to the same checkpoint, use leases/fencing/version CAS so a stale instance cannot overwrite a newer instance's checkpoint progress.

### 22.6. What If the Token Is Lost or the Oplog Evicted History?

Never silently start watching from "now" and claim the projection is accurate. Determine:

- What is the latest valid checkpoint?
- How large is the missed data gap?
- Can you rebuild completely from the MongoDB source?
- Are reconciliation jobs available to detect drift?
- Can downstream consumers be paused or data marked stale until rebuild completes?

### 22.7. How Many Active Streams Are Needed?

Each Change Stream uses a cursor/`getMore` and can hold a connection waiting for events. If 100 tenants open 100 streams on a shared 20-connection pool, expect latency and contention.

You may choose one database-level consumer routing by tenant instead of 100 collection-level streams, **balancing security, throughput, and blast radius**. There is no single universally right choice.

## 23. Deployment Selection Matrix by Scenario

| Scenario | Suggested Scope | Mandatory Preparation |
|---|---|---|
| Refresh orders cache | Collection | Idempotent invalidation, token, restart handling. |
| Products search index | Collection | Initial bootstrap, version/order handling, rebuild on oplog loss. |
| Analytics across multiple collections in one DB | Database | Namespace filtering, multi-schema mapping, checkpointing. |
| Central CDC across multiple databases | Deployment | Broad privileges, governance, routing, throughput, network/security. |
| Domain-event notifications | Outbox collection | Business event schema, idempotent publisher/consumer. |
| Watching operations on local standalone | Cannot watch yet | Switch to a test replica set or use polling. |
| Long-term audit retained for years | Not Change Streams alone | Persist durable audit records with retention/security controls. |
| Near-real-time UI updates | Collection/Database → app relay | User authorization, WebSocket/SSE, backpressure, reconnection. |

### 23.1. A Guiding Question

If the application only needs "when a document changes, invalidate the cache," Change Streams are usually sufficient as a notification source with a proper consumer.

If the business requires "once payment is confirmed, emit exactly one domain event to five systems and allow replay six months later," design an **outbox/broker/retention** layer alongside or downstream of Change Streams.

## 24. Testing and Monitoring

### 24.1. Basic Functional Testing

On a lab replica set:

1. Open a stream on the `orders` collection.
2. Insert a new order.
3. Update the order's status.
4. Replace the order.
5. Delete the order.
6. Observe **operationType, documentKey, updateDescription, fullDocument**.
7. Verify no events are emitted for pure read operations.

### 24.2. Disconnect and Resume Testing

1. Start the consumer, process E1, and save its token.
2. Stop the consumer.
3. Perform E2 and E3 while the consumer is down.
4. Restart with **resumeAfter(token E1)**.
5. Verify E2/E3 are consumed while oplog history remains available.
6. Simulate a crash after processing E2 but before checkpointing to verify idempotency.

### 24.3. Oplog Window Loss Testing

In a controlled test environment, create a condition where the checkpoint is older than oplog retention.

Expected outcome: the consumer must **detect the resume failure**, transition to a rebuild/reconciliation workflow or raise a critical alert; **never silently skip lost events**.

### 24.4. Invalidation Testing

On a test collection containing no real data:

~~~javascript
db.temp_watch_lab.insertOne({ _id: 1 });
~~~

Open a watch on `temp_watch_lab`, then in another terminal:

~~~javascript
db.temp_watch_lab.drop();
~~~

Observe the `drop`/`invalidate` event depending on stream scope. Verify the consumer does not mistake `invalidate` for a normal network error recoverable via `resumeAfter`.

**Never drop a real collection for testing.**

### 24.5. Scale and Connection Testing

Measure:

- Number of active streams.
- Connection pool occupancy, wait times, timeouts.
- Latency from `clusterTime`/event creation to consumer completion.
- Queue/backlog depth.
- Throughput in events/second.
- Downstream CPU/RAM and lag.

Do not benchmark latency solely on a lab collection with one document; benchmarks must reflect realistic load.

### 24.6. Operational Metrics

| Metric | Why It Matters |
|---|---|
| **change_stream_events_total** | Track event rate and `operationType` distribution. |
| **change_stream_processing_latency** | Spot slow consumers. |
| **change_stream_resume_total** | Detect unstable connections. |
| **change_stream_resume_failures_total** | Alert on history loss or invalid tokens. |
| **change_stream_checkpoint_age** | Compare checkpoint age against the oplog window. |
| **change_stream_active_cursors** | Track open streams and connection pressure. |
| **change_stream_duplicate_events_total** | Observe replays and idempotency triggers. |
| **change_stream_downstream_errors_total** | Separate MongoDB issues from sink failures. |
| **oplog_window_seconds** | Measure downtime tolerance before losing resume capability. |
| **change_stream_invalidation_total** | Detect collection drop/rename/lifecycle events. |

These names are **suggested application-level metrics**, not mandatory built-in MongoDB server metric names.

### 24.7. Business-Risk-Based Alerts

Example:

~~~text
Checkpoint age > 50% oplog window
   -> warning, investigate consumer lag.

Checkpoint age approaching oplog window
   -> critical, risk of losing resume capability.

Resume repeatedly failed
   -> do not restart infinitely without delay;
      escalate + initiate recovery plan.

Large backlog / downstream slow
   -> throttle, scale consumer, or increase sink capacity.
~~~

Percentage thresholds are illustrative; tune them based on actual retention, write rate, and SLOs.

## 25. Troubleshooting Common Deployment Errors

### 25.1. "The $changeStream stage is only supported on replica sets"

Common cause: the connection points to a **standalone mongod**.

Resolution:

1. Check **db.hello()**.
2. Confirm you are running a replica set or sharded cluster.
3. Locally, configure a single-node replica set.
4. In production, perform topology changes via formal administrative procedures—never ad-hoc hot fixes.

### 25.2. Unauthorized When Watching

Cause: missing **find** or **changeStream** privileges on the requested scope.

Resolution: verify the service account's role, watch scope, auth database, and connection credentials; grant **least privilege** rather than cluster-wide admin rights.

### 25.3. Stream Emits No Events Despite Writes

Check:

- Are the terminal/app connected to the exact same cluster/database/collection?
- Was the stream opened before the writes you expect to observe?
- Did the write actually modify data?
- Is a `$match` pipeline filtering out the `operationType` or namespace?
- Has the write been majority-committed?
- Is the cursor still active and not closed/canceled?
- Is the consumer waiting long enough and not misblocking threads?

### 25.4. Event Received but fullDocument Is Null

Not every event includes `fullDocument`:

- **delete** has no post-image.
- **update** defaults to delta-only.
- **updateLookup** may fail to find the current document if it was subsequently deleted or no longer matches at lookup time.
- **whenAvailable** may omit the image if the collection option is disabled or the image exceeded retention.

Choose the strategy matching your needs: delta, lookup, pre-/post-images, or domain events.

### 25.5. Resume Token Invalid / Oplog History Lost

Possible causes:

- Token was not stored intact.
- `documentKey._id` was used instead of `event._id`.
- Incompatible pipeline/options changes.
- The oplog window no longer contains the old event.
- Collection lifecycle invalidation requires `startAfter` instead of `resumeAfter`.

Do not silently ignore the error and restart from the current time if downstream completeness is required.

### 25.6. Event Processed Twice

This can happen if a consumer crashes **after side effects but before checkpointing**, or during resume/retry. The fix is **idempotent consumers**, deduplication, and disciplined checkpointing—not expecting global exactly-once effects from the stream itself.

### 25.7. Slow Notifications as Stream Count Grows

Inspect **maxPoolSize**, active cursors and `getMore` connections, consumer processing speed, and sharded cluster fan-out.

Do not just scale CPU if the bottleneck lies in the connection pool or downstream sink.

### 25.8. Every Service Instance Processes the Same Event

If multiple instances call `watch` on a collection, they **each register an independent stream**. There is no built-in consumer group splitting events across instances.

Implement a singleton consumer/lease, idempotent fan-out, or a broker with consumer group distribution.

### 25.9. Collection Dropped and Watch Stops

Distinguish an `invalidate` event from a network error. If you need to watch a recreated collection, review **startAfter** semantics, re-bootstrap, and update checkpoints/pipelines accordingly.

### 25.10. Works on Local Replica Set, Fails on Sharded Production

Check:

- Does the URI connect via **mongos**?
- Are auth scopes sufficient across databases/collections?
- Is shard key/`documentKey` handling appropriate?
- Do chunk migrations/shard removals affect cursor lifecycle?
- Are `fullDocument` lookups, pool sizing, and throughput sufficient for production load?

A local single-node replica set cannot replace testing on a sharded topology.

## 26. Change Streams Deployment Checklist

Before enabling a production consumer, confirm:

1. **Goal:** which events trigger what downstream actions?
2. **Topology:** replica set or sharded cluster, proper storage engine/protocol.
3. **Version:** server, driver, and Spring Data support the APIs/options used.
4. **URI:** proper replica set/`mongos` endpoints, TLS, and networking configured.
5. **RBAC:** `find` + `changeStream` with minimal required scope.
6. **Watch scope:** collection/database/deployment chosen deliberately.
7. **Pipeline:** filters desired events without altering resume token `_id`.
8. **Event contract:** distinguishes `documentKey`, resume token, update delta, and `fullDocument`.
9. **Pre-/post-images:** enabled only if needed, with retention and sizing planned.
10. **Initial state:** bootstrap plan avoids missing events.
11. **Checkpoint:** token persisted durably after successful/idempotent processing.
12. **Resume:** backoff, handling for `invalidate`, and oplog history loss.
13. **Idempotency:** downstream tolerates event replays or deduplicates.
14. **Concurrency:** multiple instances use leases/fencing or explicit fan-out design.
15. **Resources:** sized connection pools, `getMore` cursors, memory, and queues.
16. **Security:** prevents leaking sensitive data across tenants.
17. **Observability:** consumer lag, checkpoint age, resume failures, oplog window.
18. **Recovery:** able to rebuild/reconcile if oplog becomes too old.
19. **Testing:** insert/update/replace/delete, disconnects, restarts, failover, high load.
20. **Lifecycle:** close cursors, subscriptions, and `MongoClient` cleanly on shutdown.

## 27. Practice Exercises

### Exercise 1 — Goals of Change Streams

An e-commerce platform wants to update its search index whenever a product changes price or name. Describe the flow from `updateOne` through the change event, consumer, and search index. List where latency can arise.

### Exercise 2 — Polling vs. Change Streams

Explain at least three risks of relying solely on:

~~~javascript
db.products.find({
  updatedAt: { $gt: lastCheckpoint }
});
~~~

Why are delete operations difficult to detect with this polling pattern?

### Exercise 3 — Checking Topology

In mongosh:

~~~javascript
db.hello();
~~~

Determine whether it is standalone, a replica set, or `mongos`. Can a standalone instance run Change Streams?

### Exercise 4 — Local Replica Set

On a **dedicated test machine**, configure a single-node replica set, run `rs.initiate`, and open `db.orders.watch()`. Why is this test insufficient for evaluating production failover?

### Exercise 5 — Access Control

Write a custom role granting only **find** and **changeStream** on **appdb.orders**. Why should you not assign an admin role to a consumer that only watches `orders`?

### Exercise 6 — Collection vs. Database Scope

One service only needs `orders`, while another needs both `orders` and `products`. Choose a watch scope for each service and explain the trade-offs.

### Exercise 7 — Observing Events

Open a Change Stream in Terminal A. In Terminal B, run insert, update, replace, and delete on `ORD-001`. Record the `operationType`, `documentKey`, and `fullDocument`/`updateDescription` of each event.

### Exercise 8 — Resume Token

Explain the difference between:

~~~text
event._id
event.documentKey._id
~~~

Which field must be passed to `resumeAfter`?

### Exercise 9 — Resuming After Restart

A consumer checkpointed token E1. While it was offline, the server emitted E2 and E3. It restarts with `resumeAfter(E1)`. What condition on the oplog must hold?

### Exercise 10 — Invalidation

A collection is dropped after an event. Why is `resumeAfter(invalidateToken)` inappropriate? When should you consider `startAfter` and re-bootstrapping?

### Exercise 11 — fullDocument updateLookup

Event E1 changes status from `PENDING` to `PAID`, and then E2 changes `PAID` to `SHIPPED`. A consumer processes E1 late using `fullDocument: "updateLookup"`. Why might E1's `fullDocument` show `SHIPPED`?

### Exercise 12 — Pre-/Post-Images

Explain the prerequisites for obtaining a pre-image of an update on MongoDB 6.0+. Why might the image still be missing even when the consumer specifies `whenAvailable`?

### Exercise 13 — Pipeline Filtering

Write a `watch` pipeline that receives only `insert` and `update`. Then add a filter for `updateDescription.updatedFields.status`. Why must `replace` be handled separately if you want to capture every status change?

### Exercise 14 — Exactly-Once

A consumer updates the search index successfully and then crashes before checkpointing. After restart, the event is redelivered. Design an idempotent upsert keyed by document ID/version.

### Exercise 15 — Initial Bootstrap

From a collection of 500,000 documents, how do you build an initial projection without losing updates occurring between the full scan and opening the stream?

### Exercise 16 — Java Sync Driver

Write Java code that opens `collection.watch()`, uses `FullDocument.UPDATE_LOOKUP`, `tryNext()`, and `event.getResumeToken()`. Why must it run on a worker thread instead of an HTTP controller?

### Exercise 17 — Spring Data Reactive

Use `ReactiveMongoTemplate.changeStream(...).watchCollection("orders").listen()` to create a `Flux` of events. Explain how to cancel the subscription and handle errors on stream disconnect.

### Exercise 18 — Connection Pool

A service opens 150 streams with `maxPoolSize=50`. According to MongoDB documentation, what operational risk arises? What design approaches can reduce the number of streams?

### Exercise 19 — Multi-Instance

Three instances of a service all open `db.orders.watch()`. Is each event delivered to only one instance like a Kafka consumer group? Design an approach to avoid sending three emails.

### Exercise 20 — Transactional Outbox

An order-placement transaction updates `orders`, `inventory`, and inserts an outbox event. Why might watching the outbox represent the business event better than watching every update on `orders`?

### Exercise 21 — Oplog Loss Incident

A consumer stays offline long enough that its token falls out of the oplog. Write a short runbook to recover the search index without falsely claiming data is fully synchronized while gaps remain.

### Exercise 22 — Tenant Authorization

A database-level stream receives events for 100 tenants. The backend wants to push events over WebSocket per tenant. What security checks must run before relaying an event?

## 28. Review Questions

1. What problem do Change Streams solve?
2. Why are Change Streams not simply polling with a short interval?
3. How do MongoDB Change Streams differ from tailing the oplog directly?
4. Can Change Streams be used on a standalone `mongod`?
5. What is a single-node replica set sufficient to test, and what can it not test?
6. For a sharded cluster, through which component should a Change Stream be opened?
7. What role do WiredTiger and pv1 play in deployment prerequisites?
8. Which commit state must changes reach before MongoDB emits notifications?
9. How do collection-level, database-level, and deployment-level watches differ?
10. Why does watching an entire deployment carry greater access-control risk?
11. Which two actions does MongoDB require to watch a collection when authorization is enabled?
12. Is the event `_id` field the source document ID?
13. How do `documentKey` and the resume token differ in purpose?
14. Why does an update event normally contain only `updateDescription`?
15. Is `fullDocument` from `updateLookup` guaranteed to be the document state at the exact moment of the event?
16. When are pre-/post-images needed, and what version requirements apply?
17. For a delete, why is there no post-image to look up?
18. Why must you not `$project` away `event._id` in a change stream pipeline?
19. How do `resumeAfter` and `startAfter` differ on `invalidate`?
20. Why does the oplog window directly affect resume capability?
21. Does checkpointing before or after processing reduce the risk of losing events? What is the trade-off?
22. Do Change Streams guarantee end-to-end exactly-once delivery downstream?
23. Why can running an initial scan and opening `watch` afterward miss events?
24. Why can each active change stream affect the connection pool?
25. How do the Java Sync Driver and Spring Data Reactive differ in how they await events?
26. When multiple instances call `watch`, does MongoDB automatically partition events like a consumer group?
27. How do Change Streams differ from domain events in a transactional outbox?
28. Which metrics should be used to detect when a consumer is close to losing resume capability?
29. When `watch()` emits no events, what conditions should you check first?
30. If oplog history is lost, why should you not simply restart watching from the current time?

## 29. Summary

**Change Streams** are MongoDB's Change Data Capture API that lets applications react to **majority-committed data changes**, rather than tailing the oplog manually or polling continuously.

~~~text
MongoDB replica set / sharded cluster
        |
        v
Insert / Update / Replace / Delete
        |
        v
Majority-committed change
        |
        v
watch() -> Change Stream Event
        |
        v
Idempotent consumer processing
        |
        v
Checkpoint resume token
        |
        v
Downstream cache / search / analytics
~~~

**The most important mandatory deployment prerequisites:**

1. **Topology:** replica set or sharded cluster; standalone is unsupported.
2. **Infrastructure:** WiredTiger/pv1, compatible server/driver versions, connect through `mongos` when sharded.
3. **Privileges:** `find` + `changeStream` on the required scope.
4. **Scope:** select collection/database/deployment according to consumer responsibility.
5. **Event contract:** understand `operationType`, `updateDescription`, `fullDocument`, `documentKey`, and resume tokens.
6. **History:** oplog retention must cover resume downtime; there is no infinite replay.
7. **Reliability:** checkpoint after processing; accept replays, enforce idempotency, and plan recovery when history is lost.
8. **Resources:** long-lived cursors/`getMore`, connection pools, sharded fan-out, and downstream backpressure.
9. **Security:** protect tenants, sensitive data, and access controls outside the database.
10. **Operations:** monitor lag, checkpoint age, resume errors, restarts, and rebuilds.

Do not choose Change Streams simply because they carry the **real-time** label. The right question is: **"Which changes should the application react to, what freshness and durability guarantees are needed, and how will it recover when a consumer misses data?"**. Answering these questions determines whether Change Streams suffice on their own or should be paired with an outbox, broker, snapshots, and reconciliation.

### Official Documentation

- [MongoDB Change Streams — overview, availability, access control, and resumability](https://www.mongodb.com/docs/manual/changestreams/).
- [MongoDB db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/) — opening a stream, options, `fullDocument`, and pre-/post-images.
- [MongoDB db.watch()](https://www.mongodb.com/docs/manual/reference/method/db.watch/) — database-level watch.
- [MongoDB $changeStream aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/) — semantics of the change stream stage.
- [MongoDB Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — structure and operation types.
- [MongoDB Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog and replication history.
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — `MongoCollection.watch()`, `MongoChangeStreamCursor`, and `fullDocument`.
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — imperative `MessageListenerContainer`, `ReactiveMongoTemplate`, and resume options.
- [MongoDB Production Notes for Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — connection pool sizing and sharded cluster considerations.

Change Streams are most valuable when deployed as **one component inside a data-synchronization architecture with recovery**, rather than an endless event-reading loop lacking checkpoints and idempotency. Once topology, privileges, oplog retention, and downstream reliability are properly established, Change Streams provide a natural way to build systems that react to MongoDB changes in near real time.



