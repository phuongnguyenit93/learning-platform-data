# Setting Up a Replica Set When Lessons Require Transactions or Change Streams

## 1. Objectives and Context

In the **SPRING_DATA_MONGODB** module, Spring applications use Spring Data MongoDB to connect to MongoDB, map Java documents, query via repositories or `MongoTemplate`, run aggregations, build indexes, manage transactions, perform reactive access, and diagnose performance. Several lessons only require MongoDB running in standalone mode, whereas two categories of hands-on exercises require a supporting topology:

- **Multi-document / multi-collection transactions:** for example, creating an order and writing an outbox record within the same MongoDB transaction.
- **Change streams:** having the application subscribe to insert, update, replace, and delete events on a collection and react as data changes.

MongoDB supports both capabilities on a **replica set** (or an appropriate sharded cluster deployment). A plain standalone `mongod` is not enough to practice those features.

This lesson guides you through setting up a **single-node replica set** named `rs0` on a development machine, verifying it has a `PRIMARY`, configuring the Spring application connection, testing transactions and change streams, and troubleshooting common connection errors.

> **Scope:** a single-node replica set is sufficient for learning transactions and change streams, yet it provides **no high availability** and does not simulate multi-node elections or failover. Real production deployments require multi-node replica set design, security, backups, monitoring, and dedicated upgrade workflows.

## 2. What Is a Replica Set and Why Do These Two Features Require It?

A **replica set** is a group of `mongod` processes maintaining the same dataset through replication. In a standard topology:

- **PRIMARY:** receives normal write operations and records entries in the operation log (*oplog*).
- **SECONDARY:** replicates changes from the oplog; eligible to become PRIMARY via an election when qualified.
- **Election and majority mechanics:** govern PRIMARY selection and write-acknowledgment guarantees across multi-node setups.

The **oplog** is an ordered history of operations used for replication. **Change streams** rely on this infrastructure to emit change events to clients; consequently, running `$changeStream` on a standalone server is rejected.

**Multi-document transactions** rely on client sessions and MongoDB's transaction coordination machinery. MongoDB does not support this type of transaction on a standalone `mongod`. On an initialized replica set, transactions can span multiple documents and collections, subject to server version, configuration, and system limits.

A **single-node** replica set still has a `PRIMARY` and an oplog once `rs.initiate()` succeeds. However, with only one node, losing that node means losing availability; `w: "majority"` on a single-node topology also does not create an independent copy of data.

| Configuration | Document Writes | Multi-Document Transactions | Change Streams | Survives Single-Node Loss |
| --- | --- | --- | --- | --- |
| Standalone `mongod` | Yes | No | No | No |
| Single-node replica set | Yes | Yes | Yes | No |
| Multi-node replica set with quorum | Yes | Yes | Yes | Depends on node count, quorum, and config |
| Appropriate sharded cluster | Yes | Yes | Yes | Depends on architecture and config |

Do not confuse **transactions**, **change streams**, and **replication**: transactions provide atomicity/consistency across a group of operations; change streams deliver an event feed; replication copies data and serves as the underlying infrastructure enabling those features.

## 3. Prerequisites

The examples below assume:

- Your development machine has **Docker Engine/Docker Desktop** capable of running Linux containers, or has `mongod` and `mongosh` installed natively.
- TCP port **27017** on the development machine is not occupied by another service.
- Java/Spring Boot and Spring Data MongoDB are set up in your application. For configuration examples, YAML snippets use **Spring Boot 3.x** property names; if using another Spring Boot version, check the corresponding property names and starters.
- The lab runs **on a development machine** without MongoDB authentication enabled. The port is published strictly on loopback (`127.0.0.1`), never exposed directly to the Internet.

Naming conventions used in this lesson:

| Value | Meaning |
| --- | --- |
| `rs0` | Replica set name |
| `mongodb-rs0` | Docker container name |
| `127.0.0.1:27017` | MongoDB address as seen from an app running on the host |
| `spring_mongo_lab` | Database used for practice |
| `orders`, `outbox` | Two collections illustrating transactions |
| `mongo-rs0-data` | Docker volume preserving data across container stops/restarts |

> **Environment note:** the Docker instructions in Section 4 assume the **Spring application runs on the host machine**, outside Docker. If the app runs in another container, see Section 8 on DNS and replica set member addresses, since `localhost` inside any container points only to that container.

## 4. Option A — Creating a Single-Node Replica Set with Docker

This is a convenient way to start without installing `mongod` directly on the host machine.

### Step 1: Run MongoDB in Replica Set Mode

In a terminal (PowerShell, Bash, or equivalent), run:

```bash
docker run -d --name mongodb-rs0 -p 127.0.0.1:27017:27017 -v mongo-rs0-data:/data/db mongo:8.0 --replSet rs0 --bind_ip_all
```

Meaning of key flags:

- `mongo:8.0`: example MongoDB 8.0 image. You can use another version compatible with your lessons; pinning a version line keeps the lab environment stable.
- `--replSet rs0`: starts `mongod` as a member of replica set `rs0`.
- `--bind_ip_all`: allows `mongod` to listen on interfaces inside the container. `-p 127.0.0.1:27017:27017` restricts host port publishing to loopback.
- `-v mongo-rs0-data:/data/db`: preserves data when the container is stopped/removed and recreated with the same volume.

Inspect the container:

```bash
docker ps --filter name=mongodb-rs0
docker logs mongodb-rs0
```

Simply launching `mongod` with `--replSet` is **not enough**: you must initialize the replica set configuration in the next step.

### Step 2: Open `mongosh` Inside the Container

```bash
docker exec -it mongodb-rs0 mongosh
```

From here on, enter the `javascript` blocks **directly at the `mongosh` prompt**, not in PowerShell. Interactive input also avoids quote-escaping issues when nesting JavaScript inside `docker exec` on Windows.

Initialize the single-node replica set:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Set `host: "localhost:27017"` because both MongoDB and the application follow the topology of **one MongoDB container + application running directly on the host**. A client on the host can connect over the published port and reach the advertised `localhost:27017` member address during replica set discovery.

If `rs.initiate()` returns `ok: 1`, the configuration was accepted. Once the node is elected `PRIMARY`, writes can proceed.

**Do not rerun `rs.initiate()` on every startup.** Replica set configuration is persisted in the data volume. Once initialized, calling it again fails because the replica set is already configured.

### Step 3: Verify PRIMARY Status

Continue in `mongosh`:

```javascript
rs.status().set;
rs.status().members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health
}));
db.adminCommand({ hello: 1 }).isWritablePrimary;
```

Expected results:

- `rs.status().set` is `rs0`.
- `members` contains one entry with `stateStr: "PRIMARY"` and `health: 1`.
- `isWritablePrimary` equals `true`.

Immediately after initialization, the node may take a moment to transition to `PRIMARY`. If `PRIMARY` has not appeared yet, re-check `rs.status()` and `docker logs mongodb-rs0` to inspect why.

You can also verify the oplog exists:

```javascript
db.getSiblingDB("local").getCollection("oplog.rs").stats().count;
```

The oplog entry count changes with activity; the purpose is to confirm the replica set oplog collection exists, not to assert a fixed number.

### Step 4: Connect from the Host Machine

Exit `mongosh` with `exit`. If `mongosh` is also installed on the host, test connecting:

```bash
mongosh "mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0"
```

This command is optional if your application connects directly through the Java driver. The URI for an app on the host is:

```text
mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
```

`replicaSet=rs0` tells the driver to verify the replica set name; it **does not turn a standalone server into a replica set**. The name `rs0` must match the initialized configuration.

### Step 5: Stop and Restart the Environment

```bash
docker stop mongodb-rs0
docker start mongodb-rs0
```

The data volume preserves both data and replica set configuration. If recreating the container against the same volume, ensure the name, port, and startup arguments match; avoid deleting data unintentionally.

## 5. Option B — Using `mongod` Installed Natively on the Host

If MongoDB Server and `mongosh` are installed on the host machine, you can start a dedicated `mongod` for this lesson. The example command assumes the data directory already exists and uses OS-appropriate paths:

```bash
mongod --dbpath ./mongo-rs0-data --port 27017 --bind_ip 127.0.0.1 --replSet rs0
```

Open another terminal:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

In `mongosh`, run once:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Once `PRIMARY` is ready, verify as in Section 4. Create the `mongo-rs0-data` directory before starting `mongod`, ensure write permissions on it, and avoid port conflicts with any other MongoDB instance.

**Use only one of Option A or Option B on port 27017**, unless you intentionally choose a different port. Running both simultaneously will cause one process to fail binding to the port.

## 6. Testing Transactions Directly in `mongosh`

Once the replica set has a `PRIMARY`, test a transaction writing to two collections: `orders` and `outbox`. Both inserts must commit together or abort together if the transaction does not complete.

Open `mongosh`:

```bash
docker exec -it mongodb-rs0 mongosh
```

Create a session and execute the transaction:

```javascript
const session = db.getMongo().startSession();
const lab = session.getDatabase("spring_mongo_lab");

try {
  session.startTransaction();

  lab.orders.insertOne({
    _id: "tx-order-001",
    status: "PLACED",
    total: NumberDecimal("2500000")
  });

  lab.outbox.insertOne({
    _id: "tx-event-001",
    orderId: "tx-order-001",
    type: "ORDER_PLACED"
  });

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
```

Inspect both documents after commit:

```javascript
const checkDb = db.getSiblingDB("spring_mongo_lab");
checkDb.orders.findOne({ _id: "tx-order-001" });
checkDb.outbox.findOne({ _id: "tx-event-001" });
```

Both must exist. Rerunning the snippet unchanged will hit a duplicate key error on the existing IDs; use fresh IDs per run or manage test data cleanup deliberately.

Test **rollback** using a different ID:

```javascript
const rollbackSession = db.getMongo().startSession();
const rollbackDb = rollbackSession.getDatabase("spring_mongo_lab");

try {
  rollbackSession.startTransaction();
  rollbackDb.orders.insertOne({
    _id: "tx-order-rollback",
    status: "PLACED"
  });
  rollbackSession.abortTransaction();
} finally {
  rollbackSession.endSession();
}

db.getSiblingDB("spring_mongo_lab")
  .orders.findOne({ _id: "tx-order-rollback" });
```

Expected output is `null`: the inserted document was rolled back with the transaction.

**Notes:**

- Lab transactions use a MongoDB session; writes must be issued through database/collection handles bound to **the same session**. Writing via an unrelated connection or un-bound collection handle will not join the transaction.
- This demo transaction does not cover HTTP calls, external payment gateways, or operations in other databases. A MongoDB transaction does not turn independent external systems into a single distributed transaction.
- For systems requiring strong durability guarantees, configure appropriate `readConcern`, `writeConcern`, commit error handling, and retries. A single node with `majority` does not provide the fault tolerance of a multi-node replica set.

## 7. Testing Change Streams Directly in `mongosh`

To observe events live, you need **two terminals** connected to the replica set. When using Docker, open both with:

```bash
docker exec -it mongodb-rs0 mongosh
```

### Terminal A: Start Watching

Run in `mongosh`:

```javascript
const watchDb = db.getSiblingDB("spring_mongo_lab");
const stream = watchDb.orders.watch([
  { $match: { operationType: "insert" } }
]);

while (stream.hasNext()) {
  printjson(stream.next());
}
```

The loop blocks while waiting for events. This is expected because a change stream is a continuous watch cursor. When done testing, press `Ctrl+C` to stop the loop.

### Terminal B: Generate New Data

Run in Terminal B's `mongosh`:

```javascript
db.getSiblingDB("spring_mongo_lab").orders.insertOne({
  _id: "cs-order-001",
  status: "NEW",
  createdAt: new Date()
});
```

Terminal A receives an event with `operationType: "insert"`, `ns` showing the namespace, `documentKey._id` as the document ID, typically `fullDocument`, and event-level `_id` as the **resume token**.

Calling `watch()` observes changes occurring **after the stream starts** (unless configured with appropriate start/resume options). It does not replay previously existing orders automatically.

To see additional change types, remove `$match` or filter for `update`, `replace`, and `delete`. For updates, `fullDocument` does not always include the full updated document by default; understand the `fullDocument: "updateLookup"` option and the difference between update deltas and a point-in-time lookup of current state.

### Resume Tokens and Reliable Consumption

Change stream events include a resume token so clients can resume from a checkpoint after disconnects. Production applications should:

1. Process events **idempotently**, because reconnects/retries can redeliver events.
2. Persist the token durably **after** downstream processing succeeds using a consistent strategy.
3. Pass the resume option when recreating the stream.
4. Monitor oplog retention window: if historical entries needed for resume fall out of the oplog, an old token becomes invalid.

Change streams do not provide "exactly once" semantics for external side effects out of the box. When building job queues or external sync pipelines, design explicit retries, deduplication, and recovery workflows.

## 8. Connection Strings and Replica Set Hostname Resolution

After connecting to a seed host, the MongoDB driver discovers replica set members using the addresses **advertised** by the server in `rs.conf()`. Because of this, networking and DNS are frequent stumbling blocks during labs.

### 8.1. Spring App Running on the Host

Using the topology from Section 4:

```text
Spring App (host)
    |
    | mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
    v
Published Docker port 127.0.0.1:27017
    |
    v
MongoDB container (rs0 / PRIMARY)
  rs.conf(): member host = localhost:27017
```

The host resolves `localhost`, so the driver finds the advertised member. Both the `127.0.0.1` seed and `localhost` member point to the same host machine here.

### 8.2. Spring App Running in Another Container

If the app runs on the same Docker network as a MongoDB service named `mongo`, the replica set member should advertise a DNS address that **the app container can resolve and reach**, such as `mongo:27017`. The app container's URI looks like:

```text
mongodb://mongo:27017/spring_mongo_lab?replicaSet=rs0
```

Corresponding member configuration when initializing a **fresh container-only environment**:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo:27017" }
  ]
});
```

`mongo` in this example must actually be MongoDB's DNS name on the Docker network, and `mongod` must be able to resolve that name during initialization.

**Do not casually swap `localhost` for `mongo` inside an already-running replica set just because you moved the app.** Inspect topology and DNS from both sides and update configuration systematically. An address valid inside containers may not resolve from the host, and vice versa.

### 8.3. Does `directConnection=true` Solve Everything?

`directConnection=true` can help in certain single-node Docker experiments where the advertised member address is unreachable externally, as it instructs the driver to talk directly to the seed host. However, it is **not a substitute for reachable member hostnames in real topologies**, nor is it a catch-all fix for transaction, change stream, or multi-node replica set issues.

Before adding that option, inspect:

```javascript
rs.conf()._id;
rs.conf().members.map(m => m.host);
rs.status().members.map(m => m.stateStr);
```

If the client sees an unresolvable hostname or no `PRIMARY`, fix the underlying configuration/connectivity issue. For the host-based single-node lab in Section 4, a URI with `replicaSet=rs0` is the clean choice.

## 9. Connecting Spring Boot to the Replica Set

### 9.1. Dependencies and URI Configuration

Example for a **Spring Boot 3.x** application using synchronous access:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

Configuration in `application.yml`:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/spring_mongo_lab?replicaSet=rs0
```

If using Gradle, declare the equivalent dependency. For reactive applications, use the reactive MongoDB starter matching your framework version:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Only include both synchronous and reactive starters when the app genuinely needs both access paths. **Do not guess property or starter names across Spring Boot versions:** these examples target Boot 3.x; for Boot 4.x or customized setups, verify against your version's configuration documentation.

To avoid committing credentials when authentication is enabled in other environments, inject the URI and secrets via environment variables or a secret manager rather than hardcoding them in the repository.

### 9.2. Registering `MongoTransactionManager` for Synchronous Access

Spring Data MongoDB provides `MongoTransactionManager` to bind `@Transactional` to MongoDB client sessions. Example configuration class:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
```

A service can then perform both inserts within one transaction:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LabOrderService {
    private final MongoTemplate mongoTemplate;

    public LabOrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void createOrderAndOutbox(String orderId) {
        mongoTemplate.insert(
            new Document("_id", orderId)
                .append("status", "PLACED"),
            "orders"
        );

        mongoTemplate.insert(
            new Document("_id", "event-" + orderId)
                .append("orderId", orderId)
                .append("type", "ORDER_PLACED"),
            "outbox"
        );
    }
}
```

This example illustrates only the **MongoDB transaction boundary**. Production code must also address idempotency, duplicate IDs, validation, and error-appropriate retries. `@Transactional` applies when the method is invoked through a Spring proxy; internal *self-invocation* within the same object generally bypasses default proxy-based transactions.

**Testing rollback:** induce a failure on the second insert (such as an intentional duplicate `_id` in the `outbox` collection) and confirm the first insert does not persist once the transaction aborts. Run this check on isolated test data to avoid confusing it with previous runs.

### 9.3. Transactions in Reactive Applications

In a reactive stack, use `ReactiveMongoTransactionManager` instead of the synchronous manager:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new ReactiveMongoTransactionManager(mongoDatabaseFactory);
    }
}
```

In reactive flows, transaction context propagates via the Reactor context; you can annotate methods returning `Mono`/`Flux` with `@Transactional` or use `TransactionalOperator` for explicit transaction scopes. Never mix blocking operations into reactive flows, and avoid manually calling `subscribe()` inside a service while expecting subsequent steps to remain in the same transaction.

## 10. Watching Change Streams with Spring Data MongoDB

Beyond `mongosh`, Spring Data MongoDB provides change stream APIs in Java. In a reactive stack, you can expose a `Flux`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;

import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderChangeStreamService {
    private final ReactiveMongoTemplate template;

    public OrderChangeStreamService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Document>> watchOrders() {
        return template.changeStream(
            "orders",
            ChangeStreamOptions.builder().build(),
            Document.class
        );
    }
}
```

Consumers of the `Flux` must manage subscriptions, logging, error handling, reconnects, resume tokens, and backpressure/load limits. Simply declaring the `Flux` does not start listening; the stream starts only upon subscription. In production, side-effect handlers need idempotency and token checkpointing after work completes.

To filter events, pass an aggregation filter to `ChangeStreamOptions`. When you need the current document state after an update, check the `fullDocument` option; update events do not always carry the full document by default.

For imperative applications, Spring Data also offers change stream listeners via `MongoTemplate` and `MessageListenerContainer`; pick the API matching your threading model. A change stream does not replace an initial query if a screen or service needs to load documents that already existed before subscribing.

## 11. Indexes and Aggregations Once the Replica Set Is Ready

A replica set satisfies the **topology prerequisite** for transactions and change streams, yet it does not optimize queries by itself. As the module progresses to aggregation, indexes, and performance diagnostics, you still need to design indexes around real application query patterns.

For example, if you regularly fetch a customer's orders by time:

```javascript
use spring_mongo_lab
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "c-01" })
         .sort({ createdAt: -1 })
         .limit(20)
         .explain("executionStats");
```

Note that the sample documents from the transaction section lack `customerId` and `createdAt`; insert matching documents when practicing this query. `explain("executionStats")` lets you inspect the query plan, index keys/documents examined, and execution behavior on meaningful data; a tiny collection rarely reflects production workloads.

With change streams, avoid opening unnecessarily many clients or overly broad pipelines. Long-lived watch cursors carry connection and event-processing overhead. When scaling multiple consumers, monitor processing lag, oplog catch-up headroom, and stream recovery errors.

## 12. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check and Resolve |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | Connected to a standalone server | Check `--replSet` and `rs.status()`; initialize the replica set and reconnect |
| `$changeStream stage is only supported on replica sets` | Server topology does not support change streams | Confirm replica set is initialized; do not call `watch()` on standalone |
| `not primary` / `NotWritablePrimary` | No PRIMARY elected yet or client hit a non-writable node | Inspect `rs.status().members` and election state; retry once topology stabilizes |
| `ReplicaSetNoPrimary` / `ServerSelectionTimeoutException` | Driver cannot find a PRIMARY or cannot reach advertised member addresses | Check ports, container status, DNS, `rs.conf().members[*].host`, network, and URI |
| URI sets `replicaSet=rs0` but set name differs | Mismatched replica set name | Compare `rs.conf()._id` with the URI |
| App on host cannot reach `mongo:27017` | `mongo` only resolves inside the Docker network | Use a host-reachable hostname topology or adjust DNS/networking |
| App in container fails connecting to `localhost:27017` | `localhost` refers to the app container itself | Use the MongoDB service hostname on the Docker network and initialize member host accordingly |
| `rs.initiate()` reports already initialized | Already run earlier; config persisted in volume | Check `rs.status()`, do not re-initialize |
| Duplicate key error when rerunning transaction lab | Reused `_id` values from a previous run | Use fresh IDs or clean up test data intentionally |
| Change stream misses older documents | `watch()` starts listening from stream creation time | Insert new documents after starting the stream; query separately for historical data |
| Resume token expired / missing history | Event fell outside the retained oplog window | Build resync and checkpoint recovery workflows; monitor oplog window |
| Transaction aborted or conflicts occur | Write conflicts, network errors, commit errors, or transaction limits | Distinguish retryable errors; apply retries/idempotency per driver and business rules |
| Not authorized calling `watch()` when auth is enabled | User lacks required watch privileges | Inspect roles and collection/database permissions |

Useful self-check commands:

```javascript
rs.conf()._id;
rs.conf().members.map(m => m.host);
rs.status().members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health
}));
db.adminCommand({ hello: 1 });
```

And on the host:

```bash
docker ps --filter name=mongodb-rs0
docker logs mongodb-rs0
```

If `rs.status()` fails in Docker, first confirm you ran the command inside `mongosh` connected to the right container. Several issues that look like transaction or change stream bugs are actually **connecting to the wrong standalone MongoDB instance** already listening on port 27017.

## 13. Verification Before Advancing to Deeper Transaction/Change Stream Lessons

To confirm your setup is ready, verify in order:

1. **Topology:** `rs.status()` reports set `rs0` with a `PRIMARY`; `hello.isWritablePrimary` is `true`.
2. **Connectivity:** Spring app connects with the right URI and writes/reads a document via repository or `MongoTemplate`.
3. **Transactions:** two inserts in the same session commit together; when explicitly aborted or when the second operation fails, the earlier insert rolls back.
4. **Change streams:** start `watch()` first, insert a new document in another terminal, and observe the emitted event.
5. **Reactive apps (if used):** start a real subscription and verify event handling, cancellation, and behavior across disconnects.
6. **Queries/indexes:** create a needed index, run queries over representative data, and inspect `explain("executionStats")`.
7. **Restart resilience:** run `docker stop`/`docker start`, confirm the replica set keeps its config, and verify connection recovery once `PRIMARY` is back.

These checks verify **technical environment readiness**; they do not prove full business transaction correctness, exactly-once delivery, cross-system consistency, or production cluster fault tolerance.

## 14. What Changes in Real Multi-Node Deployments

A single-node lab simplifies many realities. When operating a real replica set, plan additionally for:

- **Quorum and fault tolerance:** design appropriate voting members (for instance, three data-bearing nodes across distinct failure domains) so majority survives losing one node. Adding nodes without proper distribution or capacity does not automatically yield high availability.
- **Hostnames and networking:** each member must advertise a stable hostname resolvable by all topology-discovering clients and peer members; never configure all members as `localhost`.
- **Security:** enable client auth, internal member auth, TLS, and least-privilege roles; lock down networks and manage secrets properly.
- **Durability and consistency:** choose suitable write concern and read concern, and test failover, replication rollbacks, and retry logic.
- **Oplog and change streams:** monitor oplog retention window, write rate, consumer lag, and recovery when resume tokens expire.
- **Operations:** backups/restores, monitoring, version upgrades, incident runbooks, and controlled chaos testing.

Never copy the lab Docker flags `--bind_ip_all` combined with unauthenticated MongoDB onto a public server. In this lesson, publishing only on `127.0.0.1` is an essential safety guard for the example.

## 15. Summary and Readiness Checklist

Before moving on to Spring Data MongoDB lessons on transactions or change streams, confirm:

- [ ] MongoDB runs with `--replSet rs0`, `rs.initiate()` was run once, and a `PRIMARY` exists.
- [ ] The driver URI points to the right server, replica set name, and reachable member hostnames.
- [ ] Transactions succeed in `mongosh`, including the abort/rollback case.
- [ ] Starting `watch()` before inserting delivers the expected change event.
- [ ] Spring Boot includes the matching MongoDB starter and version-appropriate connection properties.
- [ ] The appropriate transaction manager (imperative or reactive) is registered when practicing `@Transactional`.
- [ ] You can distinguish replica set errors, DNS errors, auth errors, transaction errors, and resume token errors.
- [ ] You understand a **single-node replica set is for learning only** and provides no real failover.

With these steps complete, your environment has the foundation to practice repository and `MongoTemplate` queries, aggregations, indexes, multi-document transactions, change streams, reactive access, integration testing, and data performance diagnostics in **Spring Data MongoDB**. Above all, keep two concerns separate: **the replica set makes the features available**, while **business correctness and reliability** depend on proper session usage, transaction boundaries, query predicates, retry handling, and data modeling.
