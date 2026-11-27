# Initializing a Replica Set for Practicing Transactions and Change Streams

MongoDB can run as a **standalone** server, but two essential features for learning how to build stateful applications—**multi-document transactions** and **change streams**—require a **replica set** or **sharded cluster** deployment. This lesson sets up a replica set environment on a development machine, checks member states, then executes a transaction and observes data changes in real time.

## 1. Objectives and Background Knowledge

After this practice, you will be able to:

1. Distinguish a standalone server from a replica set and understand the roles of **primary**, **secondary**, **oplog**, and the election mechanism.
2. Initialize a single-member replica set using Docker to quickly run transactions and change streams.
3. Confirm that the node has become primary, use the proper replica set connection string, and persist data across restarts.
4. Execute a balance transfer transaction between two documents while observing insert/update/delete events via a change stream.
5. Expand to a three-member replica set to explore replication and failover when needed.

A **replica set** is a group of `mongod` processes maintaining the same logical dataset. Normally, applications write to the **primary**; **secondaries** replicate operations via the **oplog** (operation log) and can be elected as the new primary when the current one becomes unavailable. In a three-member voting replica set, a majority is two members.

For **transactions**, a replica set provides the session infrastructure and commit coordination required to update multiple documents as an atomic unit. For **change streams**, MongoDB reads the change sequence from the oplog and emits events for majority-committed operations. Operations on a single document are already atomic even without a transaction; transactions matter when multiple operations must succeed or fail together.

| Environment | Multi-Document Transactions | Change Streams | Replication and Failover |
| --- | --- | --- | --- |
| Standalone | No | No | No |
| Single-member replica set | Yes | Yes | No standby node |
| Three-member replica set | Yes | Yes | Can practice replication, election, and failover |

**Practice choice:** start with a **single-member** replica set to focus on transactions and change streams. You only need the three-member setup in Section 6 when you want to practice high availability. A single member satisfies feature requirements but **provides no data redundancy or failover**.

## 2. Environment Preparation

You need Docker Engine or Docker Desktop running, host port **27017** available, and a terminal window (PowerShell, Bash, or equivalent). The examples use the **mongo:8.0** Docker image so steps follow the same version line; other MongoDB Server versions may display slightly different status output.

Verify Docker:

~~~bash
docker version
docker ps
~~~

The official MongoDB image already includes **mongosh**, so you do not have to install MongoDB Shell on the host machine. In the single-member section, the port is published only to the host's loopback address **127.0.0.1** to avoid exposing an unauthenticated server to external networks. This is a learning configuration; real deployments must use authentication, authorization, network security, and proper replica set configurations.

## 3. Creating a Single-Member Replica Set

### 3.1. Starting the MongoDB Process

Run the following commands sequentially in the host terminal:

~~~bash
docker volume create mongo-rs-lab-data

docker run -d --name mongo-rs-lab --hostname mongo-rs-lab -p 127.0.0.1:27017:27017 -v mongo-rs-lab-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all

docker ps
~~~

Meaning of the flags:

- **--replSet rs0**: enables replica set mode with the logical name `rs0`; this name must match the initiation configuration and connection string.
- **--bind_ip_all**: allows the `mongod` process to listen on container interfaces; the published port remains restricted to the host's loopback via `-p`.
- **-v mongo-rs-lab-data:/data/db**: stores replica set data, oplog, and configuration in a Docker named volume so nothing is lost when replacing the container.
- **--name mongo-rs-lab**: names the container for convenient use with `docker exec`, `docker logs`, `docker stop`, and `docker start`.

If the container just started and the shell cannot connect yet, inspect logs while waiting for MongoDB to initialize:

~~~bash
docker logs mongo-rs-lab
~~~

### 3.2. Initializing the Replica Set Configuration

Open the shell directly inside the container:

~~~bash
docker exec -it mongo-rs-lab mongosh
~~~

Inside the `mongosh` prompt, run this JavaScript:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
})
~~~

A successful result includes **ok: 1**. The address `localhost:27017` is chosen deliberately for a **single-node** setup: the MongoDB process inside the container sees itself at this address, and a client running directly on the host accesses the same address because Docker forwards port 27017.

**Run `rs.initiate()` only once for a fresh dataset.** If the volume already contains a replica set configuration from an earlier run, inspect existing state with `rs.status()` instead of re-initiating. Restarting the container with the same volume does not require re-initiation.

### 3.3. Waiting for Primary Election and Verifying

Continue running in `mongosh`:

~~~javascript
rs.status()
db.hello()
db.adminCommand({ ping: 1 })
~~~

After election completes, the key indicators are:

- In `rs.status()`, **set** is `rs0`, **myState** is `1`, and the current member has **stateStr** equal to `PRIMARY`.
- In `db.hello()`, **setName** is `rs0` and **isWritablePrimary** is `true`.
- `ping` returns **ok: 1**, confirming the server responds.

If you initially see `STARTUP2`, `RECOVERING`, or no primary yet, wait for election to finish and query status again. With a single-node replica set, it usually takes only a brief moment for the node to become primary.

From a host machine with `mongosh` installed, connect via URI:

~~~bash
mongosh "mongodb://localhost:27017/?replicaSet=rs0"
~~~

Or continue using the shell inside the container:

~~~bash
docker exec -it mongo-rs-lab mongosh "mongodb://localhost:27017/?replicaSet=rs0"
~~~

Sample connection string for an application running **directly on the host**:

~~~text
mongodb://localhost:27017/replica_lab?replicaSet=rs0
~~~

For Spring Boot, an example learning configuration is:

~~~properties
spring.data.mongodb.uri=mongodb://localhost:27017/replica_lab?replicaSet=rs0
~~~

Only add `directConnection=true` when you clearly understand the intent of connecting directly to a single node. With multi-node replica sets, applications normally need **topology discovery** so the driver locates the primary and switches nodes after failover; do not use that option as a default workaround for hostname resolution errors.

## 4. Verifying Transactions on the Replica Set

Example: transfer **200 units** from account A to B. Business invariant: we must never debit A without crediting B. To avoid stale data affecting results, prepare a deterministic set of documents.

Open `mongosh` connected to the replica set and run:

~~~javascript
const lab = db.getSiblingDB("replica_lab");

lab.accounts.deleteMany({});
lab.accounts.insertMany([
  { _id: "A", balance: 1000 },
  { _id: "B", balance: 500 }
]);

lab.accounts.find().sort({ _id: 1 }).toArray();
~~~

Start a **session**, open a transaction, and execute both updates through the database handle tied to that session:

~~~javascript
const session = db.getMongo().startSession();

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const accounts = session.getDatabase("replica_lab").accounts;

  const debit = accounts.updateOne(
    { _id: "A", balance: { $gte: 200 } },
    { $inc: { balance: -200 } }
  );
  if (debit.modifiedCount !== 1) {
    throw new Error("Insufficient balance or account A not found");
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: 200 } }
  );
  if (credit.modifiedCount !== 1) {
    throw new Error("Account B not found");
  }

  session.commitTransaction();
  print("Transaction committed");
} catch (error) {
  if (session.inTransaction()) {
    session.abortTransaction();
  }
  print("Transaction error: " + error.message);
} finally {
  session.endSession();
}

db.getSiblingDB("replica_lab").accounts.find().sort({ _id: 1 }).toArray();
~~~

After a successful commit, account A has **800**, B has **700**, and the total balance remains **1,500**. If any step throws an error before commit, the transaction aborts; uncommitted updates do not become part of the final database state.

To observe rollback behavior on its own, create a new session, modify A, and explicitly abort:

~~~javascript
const rollbackSession = db.getMongo().startSession();
rollbackSession.startTransaction();

rollbackSession.getDatabase("replica_lab").accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -50 } }
);

rollbackSession.abortTransaction();
rollbackSession.endSession();

db.getSiblingDB("replica_lab").accounts.find().sort({ _id: 1 }).toArray();
~~~

Balances must still be A = 800 and B = 700 because the **-50** change was never committed. In real applications, use the **withTransaction** API or driver-recommended retry mechanisms to handle transient transaction errors as well as unknown commit outcomes on network drops. Never automatically retry a transaction that produces external side effects outside the database without designing idempotency.

**Note:** do not set separate write concerns on individual operations inside a transaction; configure write concern at the transaction/commit level. Snapshot read concern provides a consistent view; majority write concern requires commits to be acknowledged by a majority of members.

## 5. Observing a Live Change Stream

A change stream lets a client subscribe to notifications when documents change. This example uses **two concurrent `mongosh` sessions**. Events fire after the watch is opened, because change streams do not automatically replay all pre-existing data.

### 5.1. Terminal A: Open the Watch Stream

In Terminal A, connect to the replica set and prepare the collection (create only if missing):

~~~javascript
const eventDb = db.getSiblingDB("replica_lab");
if (!eventDb.getCollectionNames().includes("events")) {
  eventDb.createCollection("events");
}

const stream = eventDb.events.watch(
  [
    {
      $match: {
        operationType: { $in: ["insert", "update", "delete"] }
      }
    }
  ],
  { fullDocument: "updateLookup" }
);

print("Waiting for 3 events...");
for (let i = 0; i < 3; i++) {
  const change = stream.next();
  printjson({
    type: change.operationType,
    key: change.documentKey,
    fullDocument: change.fullDocument,
    resumeToken: change._id
  });
}
stream.close();
~~~

The loop will **block** until three events arrive. Keep Terminal A running and perform the next step in Terminal B.

### 5.2. Terminal B: Generate Changes

In Terminal B, open another `mongosh` session to the same replica set. Run:

~~~javascript
const eventDb = db.getSiblingDB("replica_lab");

eventDb.events.insertOne({
  _id: "evt-1",
  kind: "lab",
  value: 1,
  createdAt: new Date()
});

eventDb.events.updateOne(
  { _id: "evt-1" },
  { $set: { value: 2 } }
);

eventDb.events.deleteOne({ _id: "evt-1" });
~~~

Terminal A sequentially receives events with **operationType** values `insert`, `update`, and `delete`. Each event typically contains:

| Field | Meaning |
| --- | --- |
| `_id` | Resume token used to continue watching after a processed event |
| `operationType` | Change type: `insert`, `update`, `delete`, `replace`, etc. |
| `ns` | Database and collection where the event originated |
| `documentKey` | Identifier of the modified document, typically containing `_id` |
| `fullDocument` | Full document when available; with `updateLookup`, MongoDB queries the current version for updates |
| `updateDescription` | Updated or removed fields for update events |

The **fullDocument** value on an update is not necessarily a point-in-time snapshot at the exact moment of the update: subsequent operations may occur before the lookup completes. If the document has already been deleted, the lookup may return `null`. Delete events do not include the deleted document in `fullDocument` as a full copy.

### 5.3. Resume Tokens and Watch Scope

After reading an event, the application can save `change._id` to reopen the change stream with the **resumeAfter** option:

~~~javascript
// Illustrative example assuming savedToken is _id from an already processed event.
const resumedStream = db.getSiblingDB("replica_lab").events.watch(
  [],
  { resumeAfter: savedToken }
);
~~~

The snippet above illustrates API usage; **savedToken must be an actual token** stored by the application from a prior event. In production code, update the saved token only after successfully processing the corresponding event, avoiding dropped work if the application restarts.

Change streams can be opened at the collection, database, or deployment level depending on the API and permissions. They rely on the **oplog**, so resumability is guaranteed only while the needed history remains within the oplog window. If the history is too old, the application may receive **ChangeStreamHistoryLost** and require an appropriate resynchronization workflow. Change streams do not replace durable message queues or application-level deduplication/idempotency handling.

## 6. Extension: Three-Member Replica Set

A single node enables features but does not demonstrate replication or elections. When you want to observe **primary → secondary** behavior, you can use Docker Compose with three MongoDB containers sharing a Docker network.

Create **compose.mongo-rs.yml** in a separate practice directory with:

~~~yaml
services:
  mongo1:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo1-data:/data/db

  mongo2:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo2-data:/data/db

  mongo3:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rs0", "--bind_ip_all"]
    volumes:
      - mongo3-data:/data/db

volumes:
  mongo1-data:
  mongo2-data:
  mongo3-data:
~~~

Start all three processes:

~~~bash
docker compose -f compose.mongo-rs.yml up -d
docker compose -f compose.mongo-rs.yml ps
docker compose -f compose.mongo-rs.yml exec mongo1 mongosh
~~~

Inside **mongo1**'s shell, initialize the replica set:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1:27017" },
    { _id: 1, host: "mongo2:27017" },
    { _id: 2, host: "mongo3:27017" }
  ]
})
~~~

The names **mongo1**, **mongo2**, and **mongo3** are Docker Compose internal DNS service names. They resolve from containers on the same network; they do not automatically resolve from a terminal or JVM running directly on the host.

Verify inside the container:

~~~javascript
rs.status()
rs.conf()
db.hello()
~~~

Wait until there is one `PRIMARY` node and two `SECONDARY` nodes. You can use the following connection string **from a container on the same Docker network**:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/replica_lab?replicaSet=rs0
~~~

If you need to run a Java application on the host against the three-container replica set, you must design hostnames/ports that resolve and remain reachable **consistently** from both the replica set members and the Java driver. Simply publishing ports 27017/27018/27019 while keeping internal hostnames like `mongo1` in `rs.conf()` typically causes discovery failures from the host; that is a network addressing issue rather than a transaction bug. For basic lessons on the host, using the single-member replica set from Section 3 is simpler.

To practice failover, identify the current primary in `rs.status()`, stop **that exact primary container**, and watch a new primary get elected between the remaining two nodes. The election window can cause writes to fail temporarily; a properly configured driver discovers the new primary. Next, restart the stopped node and confirm it rejoins the replica set. A three-node replica set tolerates one unavailable member as long as the remaining two members can communicate and form a majority.

## 7. Common Errors and Root-Cause Diagnosis

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | MongoDB is still running standalone or client connected to the wrong instance | Check `--replSet`, `rs.status()`, `db.hello()`, and URI |
| `The $changeStream stage is only supported on replica sets` | Not connected to a replica set/sharded cluster | Run `rs.initiate()`, wait for a primary, and connect to the right node |
| `ReplicaSetNoPrimary` / server selection timeout | Election incomplete, node stopped, or configured hostname/port unreachable from client | Inspect `rs.status()`, Docker logs, and each hostname in `rs.conf()` |
| `getaddrinfo ENOTFOUND mongo1` from host | Docker Compose DNS names only exist inside container networks | Run client in the same network or configure replica set addresses reachable from host |
| `not primary` or `NotWritablePrimary` | Node is currently secondary or mid-failover | Wait for election, use a replica set URI so the driver discovers the primary |
| `ChangeStreamHistoryLost` / cannot resume | Oplog no longer retains events for the resume token | Build a recovery/resync path and persist tokens regularly |
| `Unauthorized` | MongoDB has auth enabled, but client lacks credentials/permissions | Provide proper credentials and roles; never disable security in real environments |
| Port 27017 already in use | Another MongoDB instance or container occupies the port | Stop conflicting instance or adjust port mapping and URI for the lab |

A systematic diagnostic order is: confirm the container is running, MongoDB responds to `ping`, the replica set has a primary, the replica set name in the URI matches, and finally verify that member hostnames are reachable from the **client's actual runtime location**.

## 8. Maintaining and Cleaning Up the Lab Environment

For the single-member replica set:

~~~bash
docker stop mongo-rs-lab
docker start mongo-rs-lab
docker exec -it mongo-rs-lab mongosh
~~~

On restart, inspect `rs.status()` and data in `replica_lab`. The named volume helps MongoDB preserve the replica set configuration and data across restarts. When the container is no longer needed, you can run `docker rm -f mongo-rs-lab`; this **does not automatically delete the named volume**. Only remove the volume once you accept losing all practice data.

For the three-member setup:

~~~bash
docker compose -f compose.mongo-rs.yml stop
docker compose -f compose.mongo-rs.yml start
docker compose -f compose.mongo-rs.yml ps
~~~

Do not pass volume-deletion options to Docker Compose if you want to keep data. After each restart, the replica set may take a brief moment to elect a primary before accepting writes.

## 9. Expected Outcomes After This Practice

You now have a MongoDB deployment with `rs0` initialized, can verify primary status, and can use a URI with `replicaSet=rs0`. The transfer transaction atomically updates both accounts or rolls back cleanly; the change stream receives data events after subscribing. If you also ran the three-member setup, you explored how secondaries synchronize and how a replica set continues operating when the primary becomes unavailable.

For real-world services, a replica set requires much stronger design than a lab: at least three appropriately placed members, replication lag and oplog monitoring, backups/restores, transport and auth security, upgrade procedures, failover testing, and driver retry strategies. Those requirements go beyond initializing a practice environment here.
