# Building a Replica Set, Stepping Down the Primary, and Observing Consistency

A **MongoDB Replica Set** is a group of `mongod` processes maintaining copies of the same logical dataset. One member serves as the **primary**, receiving normal write operations, while **secondaries** replicate and apply operations written on the primary. When the primary becomes unavailable, eligible members hold an election to choose a new primary.

Understanding the definition is only the first step. When operating MongoDB, developers and engineers need to **see firsthand** member roles, replication lag, driver reactions during primary changes, and the differences between:

- A write acknowledged by the primary;
- A write acknowledged by a majority of members;
- A specific secondary having applied the change;
- A client being able to read data from the node it just connected to;
- Whether a write outcome is actually safe to retry.

The practice lesson **"Building a Replica Set, Stepping Down the Primary, and Observing Consistency"** in the **Integrated Practice** chapter walks through setting up a three-member replica set with Docker Compose, using `mongosh`, creating test data, executing a **controlled stepdown**, observing the election, testing `writeConcern`, `readConcern`, `readPreference`, and running a Java application with the MongoDB Driver. It also explains the limits of testing on a single machine and how to interpret results without claiming guarantees MongoDB does not actually make.

> **Safety scope:** All topology-changing commands, member shutdowns, and failover tests in this lesson are strictly for an **isolated lab environment** owned by the learner. Never run `rs.stepDown`, `rs.reconfig`, stop a primary, or disable authentication on production/Atlas without formal procedures, approval, and a recovery plan. A MongoDB replica set **does not replace backups**.

---

## 1. Learning Outcomes

Upon completion, you will be able to:

1. Explain the roles of primary, secondary, election, term, oplog, and majority quorum.
2. Spin up three `mongod` processes on a Docker network without exposing ports externally.
3. Initialize `rs0` via `rs.initiate()` and verify a primary exists.
4. Use `rs.status()`, `rs.conf()`, and the `hello` command to inspect cluster state.
5. Write data with `w:1` or `w:"majority"` and recognize the differences.
6. Read data from primary/secondaries using `readPreference` and `readConcern`.
7. Transfer primary leadership using `rs.stepDown()` in the lab.
8. Retry reads/writes across primary changes; distinguish transient errors from corrupt data.
9. Stop a member and evaluate remaining quorum capability.
10. Observe replication lag and explain why on a single machine you may **observe zero lag**.
11. Write a Java Driver client using a replica set URI, retryable writes, and sessions.
12. Design sound consistency tests without generalizing from a single lucky outcome.
13. Identify scenarios needing `majority`, causal consistency, transactions, or linearizable reads.
14. Collect evidence, build an experiment table, and restore the environment cleanly.

## 2. Replica Set Architecture

A three-member replica set:

```text
                    MongoDB Client
                          │
                          ▼
               Replica set discovery
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
        mongo1:27017  mongo2:27017  mongo3:27017
            │             │             │
         PRIMARY       SECONDARY     SECONDARY
            │             ▲             ▲
            └────── Oplog replication ───┘
```

Roles can shift:

```text
Before election:
  mongo1 = PRIMARY
  mongo2 = SECONDARY
  mongo3 = SECONDARY

After mongo1 steps down:
  mongo1 = SECONDARY
  mongo2 = PRIMARY    (example, not guaranteed)
  mongo3 = SECONDARY
```

Never hardcode application logic assuming `mongo1` is always primary. The MongoDB Driver discovers members from the replica set URI and server responses; applications should rely on these mechanisms rather than hardcoding a single write host.

### 2.1. Primary

- Receives normal writes for the replica set.
- Records operations in the oplog.
- Participates in write concern acknowledgments.
- Can lose its role due to stepdown, network issues, elections, or configuration changes.

### 2.2. Secondary

- Copies and applies changes via the replication mechanism.
- Can serve reads when `readPreference` permits.
- Can become primary if eligible and elected.
- Not every secondary catches up with the primary instantaneously.

### 2.3. Oplog

The oplog is the operations log driving replication. Secondaries tail the oplog and apply matching operations. The oplog also governs change streams and resume windows; if a secondary or consumer falls too far behind, a resync or appropriate recovery method may be needed.

### 2.4. Heartbeats and Elections

Members monitor each other's health and elect a primary when required. Elections depend on votes, priority, term, sync state, and majority. Never rely on a fixed number of seconds or assume a specific node will always win.

## 3. Majority Quorum for Three Members

With three voting members:

\[
\text{majority votes} = \left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

This yields:

| Scenario | Reachable Voting Members | Can Maintain/Elect Primary? |
|---|---:|---|
| All three healthy | 3 | Yes |
| One voting member down | 2 | Usually yes, if eligible |
| Two voting members down | 1 | No majority |
| Partition of two members vs. one member | 2 and 1 | Side with two can elect/hold; side with one cannot |
| All three online, none eligible for primary | Votes sufficient | Not guaranteed to have a primary |

**Quorum for elections and write acknowledgment does not automatically mean every member has received the data.** Study voting members, data-bearing voting members, and write concern majority semantics for your server version and configuration.

### 3.1. Why Not Use Two Members Expecting Full HA?

A replica set with two voting data-bearing members needs both for a majority. If one node goes down, the remaining node lacks enough votes to elect a primary. Three voting members can tolerate losing one voting member under a proper topology.

### 3.2. Arbiters Hold No Data

An arbiter votes in elections but stores no copy of the data. It **does not** substitute for a data-bearing secondary for durability, and arbiter topologies introduce trade-offs for majority write concerns and transactions. This lab uses **three data-bearing members** to observe full replication.

## 4. Preparing the Environment

Requirements:

- A machine with Docker Engine / Docker Desktop and the Docker Compose plugin.
- A terminal supporting `docker compose` (Windows PowerShell, macOS/Linux shell).
- Sufficient CPU, RAM, and disk for three MongoDB processes.
- No local policy blocking these containers on your machine.
- Permissions to create a project directory and Docker volumes.
- Ability to run `mongosh` **inside containers**; host installation is optional.
- Internet/registry access to pull the image initially.

This lesson uses the **`mongo:8.0`** image to demonstrate standard MongoDB 8.0 syntax. This is a **pinned example version**, not a claim that it is the latest or right for your current production stack. If changing image tags, check compatibility and upgrade paths—never jump major versions arbitrarily over existing volumes.

### 4.1. Connection Targets

Containers communicate over internal DNS:

```text
mongo1:27017
mongo2:27017
mongo3:27017
```

Do not publish `ports:` to the host in the Compose file. This limits access from outside the Docker network, though it is **not a complete security boundary**.

### 4.2. Lab Security Limitations

To focus on replication, this example omits internal authentication and TLS. **Use only in an isolated Docker lab**; never deploy this configuration on a public network or in production. Real deployments require internal authentication (keyfile or x.509 per design), TLS, RBAC, secret management, network restrictions, monitoring, and backups.

## 5. Creating `compose.yaml` for Three `mongod` Instances

In a new lab directory, create:

```yaml
services:
  mongo1:
    image: mongo:8.0
    hostname: mongo1
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo1_data:/data/db
    networks:
      - rs_lab

  mongo2:
    image: mongo:8.0
    hostname: mongo2
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo2_data:/data/db
    networks:
      - rs_lab

  mongo3:
    image: mongo:8.0
    hostname: mongo3
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
      - --port
      - "27017"
    volumes:
      - mongo3_data:/data/db
    networks:
      - rs_lab

networks:
  rs_lab:
    driver: bridge

volumes:
  mongo1_data:
  mongo2_data:
  mongo3_data:
```

Key details:

- Every service runs `mongod` with the same replica set name `rs0`.
- Each member has its **own volume** for data persistence.
- Hostnames `mongo1`, `mongo2`, `mongo3` must resolve among members on the network.
- Port `27017` is not mapped out to the host.
- Compose **only starts processes**; it has not initialized the replica set yet.
- `--bind_ip_all` listens on container network interfaces; since auth is disabled, keep the lab strictly isolated.

### 5.1. Never Share One Volume

Wrong:

```yaml
volumes:
  - same_data:/data/db
```

across all three members. Each `mongod` requires its own data directory. Sharing storage files across processes is not replication and corrupts data.

### 5.2. Stable Hostnames

The replica set config stores `host` for each member. Changing hostnames or networks without a proper reconfiguration procedure can prevent members and clients from connecting.

### 5.3. Why Not Map Ports?

If you map all three ports:

```text
localhost:27017
localhost:27018
localhost:27019
```

while the replica set advertises `mongo1:27017`, `mongo2:27017`, ..., a Java client running **on the host** will fail to resolve `mongo1`, `mongo2`, `mongo3`, causing server selection errors.

This lesson runs clients inside the Docker network via `docker compose exec`. To run a Java client on the host, configure DNS/host mappings/tunnels so every advertised member address is reachable from the client.

## 6. Starting the Containers

In the directory containing `compose.yaml`:

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

Ping MongoDB on each member:

```bash
docker compose exec mongo1 mongosh --quiet --eval "db.adminCommand({ping: 1})"
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({ping: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({ping: 1})"
```

Expected once processes are ready:

```javascript
{ ok: 1 }
```

If run too early before containers finish starting, connection refused may occur; retry after checking `docker compose ps` and logs. Never alter security settings or wipe volumes to troubleshoot an uninvestigated connection error.

### 6.1. Reading Logs

```bash
docker compose logs --tail=80 mongo1
docker compose logs --tail=80 mongo2
docker compose logs --tail=80 mongo3
```

Warnings about authentication being disabled will appear in the lab. This **must never be considered a safe production configuration**.

### 6.2. Before `rs.initiate()`

A process launched with `--replSet rs0` before initialization has no primary yet. Querying replica set status reports not yet initialized. This is expected initially, not data loss.

## 7. Initializing the Replica Set with `rs.initiate`

Open `mongosh` directly on the first node:

```bash
docker compose exec mongo1 mongosh
```

In `mongosh`:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo1:27017",
      priority: 2,
      votes: 1
    },
    {
      _id: 1,
      host: "mongo2:27017",
      priority: 1,
      votes: 1
    },
    {
      _id: 2,
      host: "mongo3:27017",
      priority: 1,
      votes: 1
    }
  ]
});
```

Success typically returns `ok: 1`. The initial election takes a moment; do not declare failure just because `hello` does not show a primary immediately.

### 7.1. Initialize Only Once

Do not run `rs.initiate()` on every member. A replica set is initialized once with the specified config; the other members join from that configuration.

### 7.2. Why Set `priority:2` on mongo1?

To demonstrate one member having higher election priority than the others. Priority influences election preference, yet **does not guarantee `mongo1` is primary at every moment**, such as right after a stepdown or when ineligible.

### 7.3. `_id` and `host`

Here `_id` is the **member index in the replica set config**, not a collection document ID. Every member must have a valid, unique `host` entry in the config.

### 7.4. DNS Inside the Replica Set

Every member must be able to reach the hostnames in the config. After connecting to a seed host, drivers discover that exact hostname list. Using temporary IPs or hostnames resolvable on only one machine causes half-working replica sets.

## 8. Confirming a Primary Exists

In `mongosh`:

```javascript
rs.status();
```

Observe:

- `set`: `rs0`;
- `members`: the three configured members;
- `stateStr`: `PRIMARY` or `SECONDARY`;
- `health`;
- `term`;
- `optime`/`optimeDate`;
- Election and replication details;
- Metadata fields may vary by server version.

A compact summary:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
}));
```

Example output:

```javascript
[
  {
    name: "mongo1:27017",
    state: "PRIMARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  },
  {
    name: "mongo2:27017",
    state: "SECONDARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  },
  {
    name: "mongo3:27017",
    state: "SECONDARY",
    health: 1,
    optimeDate: ISODate("2026-11-14T04:00:00Z")
  }
]
```

This is illustrative only: actual primary name and timestamps depend on runtime state.

### 8.1. Using `hello`

```javascript
db.adminCommand({ hello: 1 });
```

Useful fields:

```text
setName
isWritablePrimary
secondary
hosts
primary
me
electionId / topologyVersion (when present)
```

`isWritablePrimary:true` indicates that endpoint currently considers itself a writable primary. **That is a point-in-time snapshot** and can change immediately after the response.

### 8.2. Checking Each Member

From the terminal, run:

```bash
docker compose exec mongo1 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({hello: 1})"
```

Because `mongosh` here connects locally to each container by default, `hello` reveals each node's self-reported role.

### 8.3. `rs.conf()` vs. `rs.status()`

```javascript
rs.conf();
```

- `rs.conf()` describes the **desired configuration**: members, votes, priority, settings.
- `rs.status()` reflects **runtime state**: who is primary, who is secondary, health, lag, and election details.

Never use `priority` in `rs.conf()` as evidence of which node is currently primary.

## 9. Proper Client URI for a Replica Set

Inside the Docker network:

```text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0
```

Open a shell via a container:

```bash
docker compose exec mongo1 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

This URI supplies multiple **seed hosts** and the replica set name. The driver discovers the topology and routes writes to the current primary per semantics.

### 9.1. A Seed List Is Not a Fixed Primary List

A host in the seed list may be a secondary. The client still uses cluster discovery to locate the writable primary. Never assume the first host in the URI is primary.

### 9.2. `directConnection=true`

To **intentionally inspect a specific node**, use:

```text
mongodb://mongo2:27017/lab?directConnection=true&readPreference=secondary
```

This connects directly to the named member; never use it as the main URI for an application that needs automatic replica-set failover.

### 9.3. Do Not Confuse `localhost` Across Network Namespaces

Inside container `mongo1`, `localhost:27017` is that container itself, not the Windows/macOS host. Inside a separate Java container, `localhost:27017` is the Java container, not MongoDB. Use the Compose service DNS names.

## 10. Creating a Test Collection and Baseline Data

In a shell connected via the replica set URI:

```javascript
const labDb = db.getSiblingDB("lab");

labDb.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no"
  }
);

labDb.orders.insertOne({
  _id: "ORD-001",
  tenantId: "T-01",
  orderNo: "001",
  status: "CREATED",
  amountMinor: NumberLong("250000"),
  createdAt: new Date()
});
```

Verify:

```javascript
labDb.orders.findOne({ _id: "ORD-001" });
```

### 10.1. Why Use Fixed IDs?

In failover/retry tests, minting a new `_id` on every retry can silently create extra documents and blur duplicate business commands with replication issues. Fixed IDs make reconciliation straightforward.

### 10.2. Unique Constraint

The `(tenantId, orderNo)` index prevents duplicate business order numbers within a tenant. It does not make the whole workflow idempotent by itself; you still need request keys/identities and proper duplicate error handling.

## 11. Oplog and Data Propagation to Secondaries

Logical write flow:

```text
Client writes to PRIMARY
          │
          ▼
Primary applies change
          │
          ▼
Change recorded in oplog
          │
          ├── Secondary A fetches/applies
          └── Secondary B fetches/applies
          │
          ▼
Majority commit / read visibility according to settings
```

Secondaries apply changes faster or slower depending on network, disk, and CPU load. In a single-host lab, members usually exhibit very low latency.

### 11.1. Checking Whether Members Have Caught Up

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optime: m.optime,
  optimeDate: m.optimeDate
}));
```

Differences in `optimeDate` are an observable clue, not an exhaustive measure of all lag types. Members in `RECOVERING` or `STARTUP2` cannot serve normal reads.

### 11.2. `rs.printSecondaryReplicationInfo()`

In `mongosh` in an appropriate environment:

```javascript
rs.printSecondaryReplicationInfo();
```

This helper displays secondary lag details. Exact format and output vary by shell and server version.

### 11.3. Never Edit the Oplog Directly

The oplog is an internal replication structure. Never arbitrarily read/write `local.oplog.rs` to "sync" data. For learning, stick to supported inspection commands.

## 12. Write Concern: How Far Must a Write Propagate Before Acknowledgment?

MongoDB lets you specify acknowledgment requirements for writes.

Common levels:

| Write Concern | General Meaning | Trade-off |
|---|---|---|
| `w:0` | Do not wait for server ACK per semantics | Client never knows if the write succeeded |
| `w:1` | Primary acknowledges the operation | Lower ACK latency in many cases, yet write may lack majority confirmation |
| `w:2` | Two data-bearing members acknowledge under supported conditions | Topology-dependent; diverges from majority semantics if membership changes |
| `w:"majority"` | Waits for replica set majority per MongoDB rules | Better rollback safety; may wait longer |
| `j:true` | Requests journal acknowledgment per version semantics | Stronger durability requirement; verify config |

The difference matters most during primary failovers.

### 12.1. `w:1` Does Not Guarantee Data Loss Will Occur

Most writes replicate quickly and never roll back. However, there is **no guarantee** that any `w:1`-acknowledged write reached a majority.

### 12.2. `w:"majority"` Does Not Mean Every Secondary Has Applied the Write

With three voting data-bearing members, majority is two members; the third member may still lag behind. A secondary you read right afterward might not show the write yet.

### 12.3. Journaling and Durability Have Version and Config Conditions

Do not interpret a majority ACK as a guarantee surviving every hardware/configuration failure combination. Review `writeConcernMajorityJournalDefault`, journaling settings, and docs for your exact topology/version when strict durability is required.

## 13. Practicing Writes with `w:1`

In `mongosh` via the replica set URI:

```javascript
const wcOne = labDb.orders.withWriteConcern({
  w: 1,
  wtimeout: 5000
});

const r1 = wcOne.insertOne({
  _id: "WC-ONE-001",
  tenantId: "T-01",
  orderNo: "WC-ONE-001",
  amountMinor: NumberLong("100"),
  createdAt: new Date()
});

printjson(r1);
```

`wtimeout` bounds how long to wait for the write concern acknowledgment where supported. With `w:1`, normal writes on the primary return very quickly.

### 13.1. Observing After Write

```javascript
labDb.orders.findOne({ _id: "WC-ONE-001" });
```

Reading from the primary shows the written document. That **does not prove** the document was majority-acknowledged when the primary returned the `w:1` ACK.

### 13.2. Never Force Rollbacks on Important Data

To study `w:1` risks, use only synthetic records. Forcing network partitions or rollbacks can corrupt lab state; the core lab prioritizes controlled stepdowns to observe elections first.

## 14. Practicing Writes with `w:"majority"`

```javascript
const wcMajority = labDb.orders.withWriteConcern({
  w: "majority",
  wtimeout: 10000
});

const r2 = wcMajority.insertOne({
  _id: "WC-MAJ-001",
  tenantId: "T-01",
  orderNo: "WC-MAJ-001",
  amountMinor: NumberLong("200"),
  createdAt: new Date()
});

printjson(r2);
```

If acknowledged cleanly, the operation satisfied the requested write concern.

### 14.1. Comparing Timing

You can measure approximate elapsed time using `Date.now()` in the shell:

```javascript
let started = Date.now();

wcMajority.updateOne(
  { _id: "WC-MAJ-001" },
  { $set: { marker: "majority-check" } }
);

print("Elapsed ms: " + (Date.now() - started));
```

Repeat across write concern levels with adequate sample sizes. On single-host Docker, differences can be tiny or masked by scheduler/cache/network jitter—**never treat a single command as a performance benchmark**.

### 14.2. When Majority Is Unavailable

If two members cannot acknowledge as required, `w:"majority"` waits until `wtimeout` or returns an error per runtime conditions. **A write concern error does not necessarily mean the change never happened on the primary.** Verify state by ID/idempotency before retrying.

## 15. Read Preference: Which Member Serves Reads?

`readPreference` controls node selection for reads.

| Mode | Meaning | Usage Guidance |
|---|---|---|
| `primary` | Read from primary | Common default when current state is required |
| `primaryPreferred` | Prefer primary, fall back when unavailable per semantics | Must tolerate staleness |
| `secondary` | Read from a secondary | Offload reads/analytics when lag is acceptable |
| `secondaryPreferred` | Prefer secondary, fall back to primary | Trades off availability vs. freshness |
| `nearest` | Pick node within latency window | **Does not guarantee freshest data** |

### 15.1. `nearest` Does Not Mean "Most Up-to-Date"

A secondary closer in network latency can reply faster while lagging behind the primary. Network speed does not dictate data recency.

### 15.2. Read Preference vs. Read Concern

- `readPreference` asks **which node to read from**.
- `readConcern` asks **what consistency guarantee applies to the data read**.

Specifying `readConcern:"majority"` on a secondary does not force that secondary to catch up to the latest real-time write.

## 16. Reading Directly from a Secondary

From the terminal:

```bash
docker compose exec mongo2 mongosh "mongodb://mongo2:27017/lab?directConnection=true&readPreference=secondary"
```

In the shell:

```javascript
db.adminCommand({ hello: 1 });
db.getSiblingDB("lab").orders.findOne({
  _id: "WC-MAJ-001"
});
```

If `mongo2` is currently `SECONDARY`, `readPreference=secondary` lets you execute reads against it.

### 16.1. What If mongo2 Became Primary?

After a stepdown, roles can flip. Direct-connecting to a node with `readPreference=secondary` when it is currently primary will fail server selection for reads. Check `hello` and target an actual `SECONDARY` instead of altering data.

### 16.2. Do Not Treat "Saw the Data" as a Law About Zero Lag

Reading a just-written document on a secondary only proves **that node caught up in time for this test**. It does not prove secondaries are always instantaneously synchronized.

### 16.3. Reading via the Full Replica Set URI

In a multi-host URI shell:

```javascript
db.getMongo().setReadPref("secondary");
db.getSiblingDB("lab").orders.findOne({
  _id: "WC-MAJ-001"
});
```

To switch back:

```javascript
db.getMongo().setReadPref("primary");
```

To see exactly which node served a read, use command monitoring/client logging or direct-connect to a member in the lab. Never guess the serving node from the document returned.

## 17. Read Concern: local, majority, snapshot, linearizable

Common levels:

| Read Concern | Primary Meaning | Notes |
|---|---|---|
| `local` | Reads node's current local data per server semantics | Can observe uncommitted-to-majority data in some cases |
| `majority` | Reads data majority-committed per MongoDB semantics | Does not guarantee read-your-writes across arbitrary nodes |
| `snapshot` | Reads from a consistent snapshot under supported conditions/scope | Used with transactions or appropriate snapshot read APIs |
| `linearizable` | Strong guarantee for single-document primary reads under constraints | Carries latency/availability cost; primary only |
| `available` | Availability-first reads in supported contexts | Consistency trade-offs, especially in sharded clusters |

Never confuse **write concern**, **read concern**, and **read preference**.

### 17.1. Majority Read Does Not Mean Current Latest

Suppose a majority write was acknowledged by `mongo1` and `mongo2`, while `mongo3` has not caught up yet. A majority read on `mongo3` still returns the older majority-committed snapshot `mongo3` has applied, not necessarily the brand-new write.

### 17.2. Snapshots Do Not Automatically Span an Entire Job

Transactions/snapshot reads have specific scopes, lifetimes, and prerequisites. Running multiple separate `find()` queries with `readConcern: "majority"` does not automatically give a multi-hour job a single frozen snapshot.

### 17.3. Linearizable Is Not Recommended as a Blanket Default

Understand its latency, availability impact, and single-document/primary restrictions. For most web applications, combining `majority`, causal sessions, CAS, and transactions when needed works better than applying `linearizable` to every read.

## 18. Testing Majority Reads on a Secondary

In a direct secondary shell, if the command/`mongosh` API supports it:

```javascript
const secondaryLab = db.getSiblingDB("lab");
secondaryLab.getCollection("orders")
  .find({ _id: "WC-MAJ-001" })
  .readConcern("majority");
```

The snippet above shows the intent; `mongosh` cursor fluent methods vary by version. A more reliable approach is **configuring read concern in the URI or driver/collection API**, e.g., in Java:

```java
MongoCollection<Document> secondaryOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.secondary())
      .withReadConcern(ReadConcern.MAJORITY);
```

Then read through that collection using the matching Java Driver version.

### 18.1. Do Not Force Lag to Appear

If results show zero difference on a single host, record `NOT OBSERVED` rather than concluding "MongoDB has no replication lag." A rigorous lab recognizes **what it cannot demonstrate**.

## 19. Causal Consistency: Reading Your Own Writes

A causally consistent session maintains ordering relationships such as **read-your-writes** under MongoDB-documented prerequisites, including using `writeConcern: "majority"` and `readConcern: "majority"` on participating operations.

Concept:

```text
Client session S
     │
     ├── Write order = PAID (majority)
     │
     └── Read order from secondary
                │
                ▼
         Wait/coordinate causal point
         before returning suitable result
```

### 19.1. Causal Sessions Do Not Force Other Clients to See Writes Immediately

A session enforces causal ordering for operations within **that session** under prerequisites, not a global real-time view across every secondary and every independent application.

### 19.2. Causal Consistency Does Not Fix Broken Producer Logic

If another service overwrites an order without CAS, your session cannot prevent business races. Use optimistic concurrency or transactions for invariants.

### 19.3. Sessions Must Be Used Sequentially

A MongoDB Java Driver `ClientSession` must never be used concurrently across multiple threads. Scope one session to a sequential workflow and close it when done.

## 20. Testing Concurrent Writes to Understand Atomicity

A document:

```javascript
{
  _id: "COUNTER-1",
  count: NumberLong("0"),
  revision: NumberLong("0")
}
```

Insert:

```javascript
labDb.counters.insertOne({
  _id: "COUNTER-1",
  count: NumberLong("0"),
  revision: NumberLong("0")
});
```

Atomic update:

```javascript
labDb.counters.updateOne(
  { _id: "COUNTER-1" },
  {
    $inc: {
      count: NumberLong("1"),
      revision: NumberLong("1")
    }
  }
);
```

When multiple workers issue valid `$inc` updates, each successful update on a single document executes atomically per MongoDB semantics.

### 20.1. Read-Then-`$set` Can Lose Updates

Wrong:

```text
Worker A read count = 10
Worker B read count = 10
Worker A set count = 11
Worker B set count = 11
```

Even though each `$set` is atomic, the final count is 11 instead of 12. Use `$inc` or CAS with `revision` depending on business semantics.

### 20.2. A Replica Set Does Not Fix Races in Application Logic

Replicas maintain copies of data; they never turn two separate read-modify-write commands into an atomic operation.

## 21. Atomic Updates and Multi-Document Consistency

Consider checkout:

```text
orders.insertOne(order)
inventory.updateOne(decrement)
payment_requests.insertOne(request)
```

If all three commands run separately, partial success can occur.

### 21.1. When to Use a Transaction?

When business requires all three MongoDB documents to commit or abort together and topology supports it:

```text
MongoDB transaction
   ├── Insert order
   ├── Reserve stock
   └── Insert outbox payment request
      COMMIT or ABORT
```

### 21.2. A Replica Set Is the Foundation for Transactions

Multi-document transactions operate on replica sets meeting version/topology requirements. A three-node data-bearing lab replica set provides the baseline to test transaction behavior.

### 21.3. Never Call External Payment APIs Inside a Transaction

A MongoDB transaction cannot make an HTTP call to a payment provider atomic with database writes. Use sagas, outboxes, idempotency, and reconciliation.

## 22. Short Transaction in `mongosh`

In a replica-set URI shell:

```javascript
const session = db.getMongo().startSession();

try {
  const sdb = session.getDatabase("lab");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  sdb.tx_demo.insertOne({
    _id: "TX-001",
    value: "first"
  });

  sdb.tx_demo.insertOne({
    _id: "TX-002",
    value: "second"
  });

  session.commitTransaction();
} catch (e) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Do not mask original error; log per policy.
  }
  throw e;
} finally {
  session.endSession();
}
```

This example requires a clean environment or unused IDs. Production code must handle retries for transient transaction errors and unknown commit outcomes per driver/shell docs.

### 22.1. Inspecting After Commit

```javascript
labDb.tx_demo.find({
  _id: { $in: ["TX-001", "TX-002"] }
});
```

In a committed transaction, both inserts commit together per transaction semantics; there is no final state containing only `TX-001` if `TX-002` failed and the transaction aborted properly.

### 22.2. Transactions and Replication Lag

A majority commit does not force every secondary to catch up immediately. If reading from an arbitrary secondary right after commit misses the result, check read preference, read concern, and causal sessions rather than concluding the transaction "half-committed."

## 23. Measuring Replication Lag in Practice

First generate many small writes:

```javascript
const batch = [];

for (let i = 0; i < 1000; i++) {
  batch.push({
    insertOne: {
      document: {
        _id: "LAG-" + i,
        tenantId: "T-LAB",
        n: i,
        createdAt: new Date()
      }
    }
  });
}

labDb.events.bulkWrite(batch, { ordered: false });
```

Then inspect:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate
}));
```

### 23.1. Lag Is Not Always Observable

With all three instances on one host, minimal network latency, tiny documents, and idle CPU, secondaries may apply writes almost instantaneously. That does not invalidate consistency test design.

### 23.2. Never Overload the Server Just to "Prove" Lag

Do not insert tens of millions of documents or generate uncontrolled CPU stress on shared hosts. Stop at 1,000 records and document the environment's observation limits.

### 23.3. Comparing Timestamps Is Approximate

`optimeDate`/replication info is not the sole measure of read freshness, and timestamps have specific granularity and semantics. In sharded or event-driven systems, use appropriate watermarks/cluster times.

## 24. Preparing for Primary Stepdown Testing

Before failover:

1. Confirm all three members are in valid `PRIMARY` or `SECONDARY` states.
2. Confirm there is exactly one primary.
3. Verify secondaries are not severely lagging.
4. Record `rs.status()`, `rs.conf()`, and `hello`.
5. Prepare a client using a **replica set URI**.
6. Record `w`/`readConcern` values for the writes being observed.
7. Never trigger failovers while non-lab data operations are running.
8. Ensure you know how to bring any stopped member back online.

### 24.1. Never Assume mongo1 Is Still Primary

In the initial config, `mongo1` had higher priority, yet after uptime or earlier failover tests, always **inspect runtime state** to locate the current primary.

### 24.2. Stepdown vs. Killing a Process

`rs.stepDown()` asks the primary to yield leadership via an administrative command with configurable wait periods. `docker compose stop` halts the process/container. Both trigger elections, yet their symptoms, timing, and impacts differ.

## 25. Stepping Down the Primary with `rs.stepDown()`

**Lab only.** Connect with a shell using the replica set URI (routing to the primary for eligible commands), then verify:

```javascript
db.adminCommand({ hello: 1 });
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr
}));
```

If the shell is connected to the actual primary, run:

```javascript
rs.stepDown(60, 10);
```

Parameters per `mongosh` helper:

- `60`: seconds the current node avoids holding primary after stepping down.
- `10`: seconds to wait for a secondary to catch up per supported stepdown logic.

Verify the exact `rs.stepDown()` signature for your MongoDB/`mongosh` version. If no eligible secondary exists, a **non-forced stepdown** may decline; never pass `force:true` casually just to watch the primary flip.

### 25.1. The Command May Drop the Connection

As the primary steps down, the shell command may throw a connection error or `NotWritablePrimary` because the node just relinquished primary status. This is expected during failover—inspect **cluster status afterward** rather than judging from a single shell line.

### 25.2. You May Need to Open a New Shell

From the terminal:

```bash
docker compose exec mongo2 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

Or run the client from the `mongo1` container; **which container launches the shell does not dictate which node is cluster primary**.

### 25.3. Verifying the New Primary

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health
}));

db.adminCommand({ hello: 1 });
```

Expected: a **new eligible primary** exists if the election succeeded. The new primary may be `mongo2` or `mongo3`; never assert that `mongo2` must always be chosen.

## 26. Primary Transition Timeline

Fill into your lab log:

| Time | Observation | Meaning |
|---|---|---|
| T0 | `mongo1` is primary (example) | Initial state |
| T1 | Send `rs.stepDown(60,10)` | Request leadership yield |
| T2 | Client sees errors or reconnects | Failover window |
| T3 | `rs.status()` shows new primary | Election complete |
| T4 | New write via replica set URI succeeds | Driver routes to new primary |
| T5 | Verify prior majority writes | Data reconciliation |
| T6 | Old node settles as secondary | Topology stabilized |

Record UTC timestamps, status values, and error labels. **The interval T1→T3 is not an absolute measure of election time** if client polling, shell startup, and monitoring intervals contribute to the delta.

### 26.1. Why Might the Primary Switch Back Later?

A higher-priority member may reclaim leadership under eligible conditions once its stepdown cooldown expires and state stabilizes. Do not treat topology right after T3 as permanent.

### 26.2. `electionId` and Term

Replica sets track terms and election metadata to order leadership per protocol. Inspecting them confirms an election occurred, but never use them as business order IDs or edit metadata manually.

## 27. Testing Reads/Writes After Election

Once the shell connects via the replica set URI:

```javascript
const after = db.getSiblingDB("lab");

after.orders.insertOne({
  _id: "AFTER-FAILOVER-001",
  tenantId: "T-01",
  orderNo: "AFTER-FAILOVER-001",
  amountMinor: NumberLong("300"),
  createdAt: new Date()
});

after.orders.findOne({
  _id: "AFTER-FAILOVER-001"
});
```

If no primary exists at the instant the client writes, the driver waits up to server selection timeout or throws an error. Once the cluster stabilizes, normal operations succeed via the standard URI.

### 27.1. Never Manually Update URIs to the New Primary's Hostname

Applications must discover topology dynamically; if code hardcodes `mongodb://mongo1:27017/?directConnection=true` for writes, it breaks after stepdown.

### 27.2. Verifying Pre-Failover Writes

```javascript
after.orders.find({
  _id: {
    $in: [
      "WC-MAJ-001",
      "WC-ONE-001",
      "AFTER-FAILOVER-001"
    ]
  }
});
```

Seeing those documents is useful observation, yet **does not generally prove every `w:1` write survives failover**.

## 28. Retryable Writes Across Failover

MongoDB drivers support retryable writes for **eligible operations** on supported deployments/versions, typically via:

```text
retryWrites=true
```

Key points:

- Driver retries do not guarantee every write operation is retryable.
- Retryable writes assign protocol-level session/transaction statement identities.
- `updateMany`/`deleteMany` and bulk operations with ineligible commands follow different semantics.
- An API-layer timeout spawning a brand-new request does not preserve the prior write identity.
- Infinitely retrying a business command containing `$inc` can increment twice.

### 28.1. Example Failure at the Failover Window

```text
T1 Client sends updateOne to old primary
T2 Primary applies write
T3 Primary steps down
T4 ACK never reaches client
T5 Client receives error / unknown outcome
```

An **unknown outcome** does not mean the write never happened. If the app mints a new order ID or calls payment a second time, duplicate business effects occur.

### 28.2. Business Idempotency

Use stable operation IDs, unique indexes, conditional state transitions, provider idempotency keys, and reconciliation. This business layer complements driver retryable writes.

## 29. Testing Failover by Stopping a Container

**Advanced test, lab only.**

After identifying the current primary with `rs.status()`, stop that exact service. For instance, if `mongo1` is primary:

```bash
docker compose stop mongo1
```

Watch the remaining members:

```bash
docker compose exec mongo2 mongosh --quiet --eval "db.adminCommand({hello: 1})"
docker compose exec mongo3 mongosh --quiet --eval "db.adminCommand({hello: 1})"
```

If the two remaining members hold a voting majority and are eligible, they elect a new primary.

### 29.1. How It Differs from Stepdown

- Stepdown: primary yields voluntarily on command.
- Stop container: member vanishes; peers detect loss via heartbeats and trigger an election.
- Failover speed may differ.
- Driver errors and retry behavior may differ.

### 29.2. Restarting the Member

```bash
docker compose start mongo1
```

The restarted node needs time to catch up. Never assume it immediately reclaims primary or is caught up.

### 29.3. Never Stop by Default Name If Primary Changed

If `mongo2` is currently primary, stopping `mongo1` (a secondary) only tests losing a secondary, not losing the primary. Always pick the target member from **runtime state**.

## 30. Testing a Secondary Disconnecting

Another test: if `mongo3` is currently `SECONDARY`, stop it:

```bash
docker compose stop mongo3
```

In a three-member data-bearing voting set, the two remaining members still form a majority while reachable.

Observe:

```javascript
rs.status();
```

And test a majority write:

```javascript
db.getSiblingDB("lab").orders
  .withWriteConcern({ w: "majority", wtimeout: 5000 })
  .insertOne({
    _id: "TWO-OF-THREE-001",
    tenantId: "T-01",
    orderNo: "TWO-OF-THREE-001"
  });
```

### 30.1. Recovering the Member

```bash
docker compose start mongo3
```

Once healthy, check status and replication progress. Never wipe the member's volume just because it was stopped during the lab.

### 30.2. When Proving Single-Fault Tolerance

Verify **two voting data-bearing members are healthy and communicating** and that the majority write succeeds under configuration. If another member is lagging, down, or ineligible, the outcome changes.

## 31. What Happens When Majority Is Lost?

Suppose a 3-voting-member set drops to 1 remaining member.

Without a majority:

- A normal writable primary cannot be maintained or elected per protocol.
- Write clients cannot proceed as on a healthy cluster.
- `readPreference=secondary` may still read from reachable members under certain conditions, with staleness and configuration caveats.
- `w:"majority"` cannot be acknowledged normally.
- Forcing `force:true` or `rs.reconfig` to bypass quorum introduces serious data risks.

### 31.1. Never Force a Primary with Dangerous Commands

In real systems, forced reconfiguration is an emergency procedure with strict protocols, rollback/divergence risks, and DBA oversight. This lab **does not require** forced reconfiguration.

### 31.2. Losing Majority Blocks Subsequent Tests

If you intentionally stop two containers, restart them completely before continuing to later sections. Do not mistake `server selection timeout` for database corruption—the cluster simply lacks a primary/quorum.

### 31.3. Data Safety and Availability Are Distinct Goals

Replica sets enforce election/commit rules to prevent two valid writable primaries from splitting the cluster per protocol. This temporarily halts writes rather than letting an isolated minority member accept writes.

## 32. `w:1` and Rollbacks: Interpreting Accurately

Conceptual sequence:

```text
Primary P accepts write X
     │
     ├── Sends w:1 ACK to client
     │
     └── Has not replicated X to majority yet

P loses connectivity / loses leadership
     │
     ▼
Another secondary becomes primary
     │
     ▼
Write X is absent from the newly elected history
     │
     ▼
Rollback occurs on member holding X per MongoDB mechanics
```

This is why `w:1` should not be treated as maximum durability protection for critical data.

### 32.1. No Need to Force Rollbacks in the Core Lab

Orchestrating network partitions or forced elections to induce rollbacks can break lab state and encourage bad production habits. Here, simply:

- Explain the scenario;
- Observe failover;
- Distinguish `w:1` from majority ACKs;
- Document when a risk cannot be demonstrated safely without destructive tests.

### 32.2. A `w:1` Write Surviving One Failover Does Not Make It Majority

Seeing a record still present after a stepdown is only a single observation. Consistency guarantees rest on MongoDB's write/read concern contracts, not luck.

## 33. `wtimeout` and Unknown Write Outcomes

While secondaries are unresponsive, a majority write can:

- Be applied by the primary;
- Fail to reach majority acknowledgment within the deadline;
- Return a write concern timeout/error to the client.

This state requires investigation:

```text
Write sent
   │
   ▼
Primary may apply
   │
   ▼
Majority ACK not achieved before timeout
   │
   ▼
Client sees write concern error
   │
   ▼
Do not blindly retry non-idempotent command
```

### 33.1. Designing Idempotent Operations

Example state-guarded update:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paymentConfirmed: true
    }
  }
);
```

If invoked again, status is already `PAID`, so the filter matches nothing and applies no extra transition; the app reads back to distinguish "already processed" from "does not exist."

### 33.2. `$inc` Is Not Always Idempotent

```javascript
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { count: 1 } }
);
```

Re-running this as a fresh business request increments a second time if the first attempt succeeded while the client missed the ACK.

## 34. Majority and Secondary Read-After-Write

Suppose:

```text
Three members A, B, C

Write X acknowledged w:majority by A+B
C has not yet applied X
```

If a client reads from C immediately:

```text
Read C → may see state before X
```

This does not contradict majority writes. **Majority** does not mean "all replicas caught up."

### 34.1. Read Primary When Fresh Writes Are Needed

Reading from the primary with appropriate session/concern reduces stale-read risk. Still, exact guarantees under concurrent writes and failovers depend on driver, read concern, and session semantics—not node labels alone.

### 34.2. Causal Sessions When Secondary Reads Are Required

If a workflow must read its own writes from secondaries, use a causally consistent session with majority writes/reads per prerequisites; the driver coordinates causal points rather than returning data older than required.

### 34.3. Linearizable Reads for Real-Time Single-Document Requirements

`readConcern:"linearizable"` paired with `writeConcern:"majority"` on the primary under supported conditions fits invariants requiring visibility of all completed real-time writes. It adds cost and restrictions and does not replace multi-document transactions.

## 35. Time Models and Easily Confused Guarantees

| Concept | Question It Answers |
|---|---|
| Atomicity | Can an operation execute halfway? |
| Durability | After ACK, which failures can the data survive? |
| Consistency | Which histories can clients observe? |
| Isolation | How do concurrent transactions see each other? |
| Availability | During member/partition loss, what keeps working? |
| Causality | Does operation B observe operation A that happened before it? |
| Linearizability | Can single-document ops be ordered consistently with real time? |
| Eventual convergence | Do replicas catch up once the system stabilizes? |

### 35.1. `w:majority` Does Not Replace Business CAS

If two workers both transition an order from `PENDING` to different statuses using unguarded `$set`, both writes can earn majority ACK while silently overwriting the first worker's decision. Use status/revision guards.

### 35.2. `readConcern:majority` Does Not Turn Sequential Java Calls into a Transaction

Reading an account and inserting an order in two separate operations has a race condition. Use atomic conditional updates or multi-document transactions when invariants require it.

### 35.3. Replication Does Not Mean Backup

If someone accidentally drops or wipes a collection on the primary via a valid command, that deletion replicates to every secondary. Replication preserves the **current state**, including valid logical mistakes. Use backups/PITR to recover.

## 36. Java Sync Driver: Application URI

Suppose the Java client runs **inside the lab's Docker network**. URI:

```text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0&retryWrites=true
```

Code:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReplicaSetClientDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            System.out.println(orders.countDocuments());
        }
    }
}
```

Illustrative Maven dependency:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>${mongodb.driver.version}</version>
</dependency>
```

Set `${mongodb.driver.version}` to a driver version compatible with your server and Java runtime.

### 36.1. If Java Runs on the Host

Docker DNS names `mongo1`, `mongo2`, `mongo3` typically do not resolve on the host. Do not just pass `localhost:27017` expecting full discovery: the replica set advertises its configured addresses. Run Java inside the Docker network or configure DNS/networking so every advertised member is reachable.

### 36.2. Shared `MongoClient`

In web services, maintain one shared `MongoClient` per application lifecycle; it manages topology discovery and pooling. Never create a new client per request "to make sure it finds the new primary."

## 37. Java: Majority Write Concern

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

MongoCollection<Document> durableOrders =
    orders.withWriteConcern(
        WriteConcern.MAJORITY.withWTimeout(10, TimeUnit.SECONDS)
    );

InsertOneResult result = durableOrders.insertOne(
    new Document("_id", "JAVA-MAJ-001")
        .append("tenantId", "T-01")
        .append("orderNo", "JAVA-MAJ-001")
        .append("amountMinor", 500L)
);

System.out.println(result.wasAcknowledged());
```

This assumes `orders` is already initialized. If it throws, classify duplicate key, server selection, retryable labels, and write concern errors. Never assume every exception means "nothing was written."

### 37.1. Scope of `wasAcknowledged() == true`

`wasAcknowledged()` reflects acknowledgment under the requested write concern and successful API return; it does not verify external payment provider state.

### 37.2. Never Use `w:0` on Critical Orders Just for Throughput

For business data needing strong durability, choose write concern based on RPO and business risk, not latency benchmarks alone.

## 38. Java: Reading from a Secondary with Majority Read Concern

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> secondaryOrders = orders
    .withReadPreference(ReadPreference.secondary())
    .withReadConcern(ReadConcern.MAJORITY);

Document observed = secondaryOrders
    .find(new Document("_id", "JAVA-MAJ-001"))
    .first();

System.out.println(observed);
```

Prerequisites:

- An eligible secondary is reachable;
- Read preference allows selecting a secondary;
- Server supports the read concern;
- Without causal coordination, that node may still not reflect the latest commit point.

### 38.1. Do Not Read Secondaries When Latest State Is Mandatory

Right after completing checkout, if the UI must reflect the committed write immediately, use primary reads or a causal session. Arbitrary secondary reads can show stale state for seconds under certain conditions.

## 39. Java: Causally Consistent Session

Sequential flow example:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;

import org.bson.Document;

MongoCollection<Document> majorityWrites = orders
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> majoritySecondaryReads = orders
    .withReadPreference(ReadPreference.secondary())
    .withReadConcern(ReadConcern.MAJORITY);

ClientSessionOptions options =
    ClientSessionOptions.builder()
        .causallyConsistent(true)
        .build();

try (ClientSession session = client.startSession(options)) {
    majorityWrites.insertOne(
        session,
        new Document("_id", "CAUSAL-001")
            .append("tenantId", "T-01")
            .append("orderNo", "CAUSAL-001")
    );

    Document result = majoritySecondaryReads
        .find(session, new Document("_id", "CAUSAL-001"))
        .first();

    System.out.println(result);
}
```

This demonstrates **read-your-writes within the same causal session** using majority writes and majority reads. Never share a `ClientSession` across threads, and do not extrapolate this test to mean secondary reads outside the session see writes instantaneously.

### 39.1. If Server Selection Fails

Inspect:

- `rs.status()`;
- Whether an eligible primary/secondary exists;
- Hostname reachability from the client;
- Whether `replicaSet=rs0` matches;
- Whether enough time was allowed for election/replication;
- Server selection timeouts and pool metrics;
- Auth/TLS if security is enabled.

Never disable read concerns or set `directConnection=true` in production just to paper over broken topology discovery.

## 40. Java: Catching Errors When Primary Changes

A skeleton:

```java
import com.mongodb.MongoException;
import com.mongodb.MongoTimeoutException;

try {
    orders.insertOne(
        new Document("_id", "FAILOVER-CMD-001")
            .append("tenantId", "T-01")
            .append("orderNo", "FAILOVER-CMD-001")
    );
} catch (MongoTimeoutException ex) {
    // May have failed to select an eligible server within timeout.
    // Do not issue a new business request before verifying outcome.
    throw ex;
} catch (MongoException ex) {
    // Classify error labels/codes and apply proper retry policy.
    // Log traceId/operationId; never log PII or connection secrets.
    throw ex;
}
```

With driver retryable writes enabled, some transient errors are retried internally. Application-level retries must still be bounded with idempotency and reconciliation.

### 40.1. Never Map Every MongoException to HTTP 500

A duplicate key on an idempotency index may map to "order already created" or payload conflict. A server selection timeout indicates temporary unavailability. A validation error is bad input. Map errors by domain semantics.

### 40.2. Appropriate Log Fields

```text
traceId
businessOperationId
collection/namespace (per policy)
writeConcern level
readPreference
errorCode / errorLabel
duration
selectedServer (if permitted)
```

Never log raw MongoDB URIs with credentials or sensitive document fields.

## 41. Observing Driver Topology Changes

The MongoDB Java Driver offers event listeners for server, topology, and command monitoring per version API.

Key signals:

- Server description changed;
- Topology description changed;
- Primary unavailable;
- New primary discovered;
- Server selection latency;
- Connection pool checkout wait times;
- Retryable write errors;
- Request p95/p99;
- Command monitoring for `hello`, `find`, `insert`, `getMore`.

### 41.1. Never Log Raw Command Bodies

Commands can carry customer data, session metadata, or sensitive payloads. Normally log only command name, duration, error code, and trace correlation.

### 41.2. Measure Client Recovery, Not Just the Election

A new primary may exist at T3 while an application instance has not yet discovered it or is stuck waiting on connection pools. User SLOs depend on **time until reads/writes resume**, not merely `rs.status()` reporting `PRIMARY`.

## 42. Failover Tests Should Be Split into Two Layers

### 42.1. Database Layer

Verify:

- Replica set maintains quorum;
- Election succeeds;
- Former primary rejoins as `SECONDARY`;
- Majority-acknowledged data remains intact;
- Secondaries catch up;
- No abnormal replication errors occur.

### 42.2. Application Layer

Verify:

- Timeout/error rates on HTTP requests during the failover window;
- Driver discovers the new primary automatically;
- Idempotency keys prevent duplicate orders;
- Zero double charges;
- Session read-your-writes holds where required;
- Outbox/CDC consumers recover cleanly;
- User-facing SLOs remain within guardrails.

A clean `rs.status()` alone does not prove the application recovered.

## 43. Measuring Time Skew Across Multiple Workers

Suppose:

```text
Worker A: writes status = PAID
Worker B: reads from secondary
Worker C: reads from primary
```

Without a causal session or ordering contract, Worker B may read the older state while Worker C observes `PAID`. This is an expected consequence of replication lag.

### 43.1. Do Not Immediately Declare Secondary Data "Corrupt"

The secondary may simply be lagging and will converge. Decide whether the feature tolerates eventual visibility or mandates read-after-write consistency.

### 43.2. Use Message/Event IDs for Workflows

If Worker B reacts to `PAID`, emit an event carrying `orderId`/version and let the worker verify against the source of truth or causal ordering. Never poll `status` on an arbitrary secondary to trigger fulfillment.

## 44. `majority` and Session-Consistent Reads

A workflow:

```text
Session S:
  Write A with majority
       │
       ▼
  Read B with majority, causally ordered
```

Causal sessions maintain supported ordering relationships. However, opening a brand-new session on every independent HTTP request without propagating causal tokens/context provides no cross-request continuity.

### 44.1. Distinguish User Sessions from Driver Sessions

A MongoDB `ClientSession` is a driver/server construct for operations, transactions, and causality—not an HTTP session cookie or user login session.

### 44.2. Never Hold Sessions Open Indefinitely

Sessions have server lifetimes, timeouts, and connection implications. Create per workflow, close when finished, and never retain in unmanaged singletons for days.

## 45. Failover and Multi-Document Transaction Consistency

A transaction can:

- Commit with majority acknowledgment;
- Abort due to a transient error;
- Leave an unknown commit outcome for the client during failover.

Applications must rely on driver transaction retry patterns per error labels while protecting business requests with stable IDs.

### 45.1. Never Auto-Retry Transactions Containing External Side Effects

If a transaction callback calls an HTTP payment endpoint, a retry sends two payment calls. Keep external API calls out of transactions using outbox/saga patterns.

### 45.2. Transaction Commit Does Not Make Every Secondary Instantaneously Current

Even after a majority transaction commit, a lagging secondary may not have applied it yet. Choose read concerns and sessions matching workflow needs.

## 46. Do Not Confuse Replication Lag with Query Latency

| Metric | Interpretation |
|---|---|
| Replication lag | How far behind primary a secondary is in applying oplog |
| Write acknowledgment latency | Time client waits for ACK per write concern |
| Election duration | Time cluster takes to transfer leadership |
| Server selection latency | Time client spends finding a suitable node |
| Read query latency | Time taken to execute and return a query |
| Application recovery time | Time until API returns within SLO after failure |
| Oplog window | Amount of history retained for sync/resume |
| Change stream lag | How far behind log events a consumer sits |

An app can have low replication lag yet slow queries due to missing indexes. Conversely, a fast secondary read can return stale data. Measure the exact phenomenon you are diagnosing.

## 47. Useful Observation Commands

| Command / Helper | Purpose | Impact |
|---|---|---|
| `rs.status()` | Runtime health/members | Read-only |
| `rs.conf()` | Replica set config | Read-only |
| `db.adminCommand({hello:1})` | Node role and topology | Read-only |
| `rs.printSecondaryReplicationInfo()` | Inspect replication lag | Read-only |
| `db.serverStatus()` | Server metrics per privileges | Read-only |
| `db.currentOp()` | Active operations per privileges | Read-only |
| `rs.stepDown()` | Relinquish primary | **Topology-changing** |
| `rs.reconfig()` | Edit replica set config | **Topology-changing, risky** |
| `rs.freeze()` | Prevent a secondary from seeking election for a duration | **Topology-changing** |
| `docker compose stop` | Stop a member | **Disruptive** |
| `docker compose down -v` | Remove containers and volumes | **Wipes lab data** |

Never assume a command is read-only just because you run it in `mongosh`.

## 48. Responding When a Member Falls Behind

If `mongo3` stays `SECONDARY` with growing lag:

1. Read `rs.status()` and replication metrics.
2. Check network connectivity, disk, CPU, cache, and throttling.
3. Check whether the member is in initial sync / `RECOVERING`.
4. Check the oplog window and write volume.
5. Inspect recent workloads: batch writes, index builds, long queries.
6. Never wipe data volumes or force reconfig immediately.
7. If necessary, follow documented initial sync / resync procedures.

### 48.1. Distinguish Lag from Sync Source Issues

A secondary may be waiting on a sync source or unable to apply oplog entries fast enough. Do not rely solely on `optimeDate`; check logs and metrics.

### 48.2. Never Force a Lagging Member to Become Primary

A lagging or ineligible member must not be forced into primary just to "have a primary." Election rules protect data consistency and operations.

## 49. Primary Election Is Not Backup or DR

Suppose a client accidentally wipes data:

```javascript
db.orders.deleteMany({});
```

Because that valid write occurred on the primary, secondaries replicate and apply the deletion too. Replica sets mirror the **current logical state**, including valid human or application mistakes.

You need:

- Backup snapshots;
- Supported point-in-time recovery (PITR);
- Restore drills;
- Defined RPO/RTO;
- Access control;
- Auditing;
- Confirmations or soft deletes for destructive actions.

### 49.1. Never Run Wipe Commands Just to Test Replication

This lab does not require `deleteMany({})` on any non-test data. Keep cleanup strictly within the designated lab namespace.

## 50. Replica Set Security Outside the Lab

Production requires evaluating at minimum:

- Internal authentication between `mongod` members;
- TLS/mTLS per security architecture;
- SCRAM/x.509/OIDC/LDAP per environment;
- RBAC / least privilege;
- Network segmentation, firewalls, private endpoints;
- Secrets / keyfile protection;
- Audit logging;
- Encryption at rest / KMS;
- Backups / PITR;
- Hostname / DNS validity;
- Monitoring / alerts;
- Upgrade compatibility;
- Capacity and disaster recovery.

### 50.1. Disabling Auth Because Docker Is Easier Is Wrong in Production

The example config is intentionally simplified for learning replication locally. It is not a production-ready template.

### 50.2. Never Put Passwords in Command History

Production uses secret managers, workload identities, or certificates—never commit credentials to Compose files or repositories.

### 50.3. Governing Sensitive Commands

Only authorized operators should run `rs.stepDown()` or `rs.reconfig()`, with change windows, communication, backups, and rollback plans.

## 51. Expectation Matrix When a Node Fails

With three data-bearing voting members, assuming no other faults:

| Event | Primary Available? | Majority Writes? | What to Observe |
|---|---|---|---|
| Healthy | Yes | Yes | Normal operation |
| Secondary 3 stops | Yes if other two are healthy | Usually yes | Lag / rejoin |
| Primary stops | Brief interruption until election | Resumes after election | Election and driver reconnect |
| Two members stop | No majority | No | Server selection / write errors |
| Primary steps down | Brief election | Resumes after election | State transition |
| One secondary lags | Usually yes | Depends on acknowledging members | Read freshness |
| 2–1 network partition | Majority side can elect | Majority side can write | Never two valid writable primaries |

These are **baseline expectations under assumptions**; real outcomes depend on votes, priority, member state, topology, elections, and server configuration.

## 52. Experiment Results Table

Fill in after running the lab:

| Test ID | Setup | Expected Result | Actual Observation | Conclusion |
|---|---|---|---|---|
| T01 | Init 3 nodes | 1 primary, 2 secondaries | ... | ... |
| T02 | Write `w:1` | Primary ACK per rules | ... | ... |
| T03 | Write majority | Majority ACK | ... | ... |
| T04 | Read secondary | May lag | ... | ... |
| T05 | Stepdown primary | New election | ... | ... |
| T06 | Write after election | Driver routes cleanly | ... | ... |
| T07 | Stop 1 secondary | Majority remains | ... | ... |
| T08 | Stop primary | New election if quorum | ... | ... |
| T09 | Causal session | Read-your-writes per rules | ... | ... |
| T10 | Transaction | Atomic commit/abort | ... | ... |
| T11 | Resume/cleanup | Cluster stable | ... | ... |

### 52.1. PASS Does Not Mean Lag Was Observed

For T04, if no lag appeared, record:

```text
Read secondary succeeded; lag NOT OBSERVED
under low-load single-host lab conditions.
```

Never write "secondaries are always instantaneously consistent."

### 52.2. Recording Timestamped Evidence

Record:

```text
UTC timestamp
Replica set status (redacted)
Current primary
Current term/election metadata
Member health
Client URI class (without credentials)
Read preference / concern
Write concern
Command outcome / error code
Driver/server versions
```

Never record raw secrets or customer documents.

## 53. Troubleshooting: `no primary` After Init

Symptoms:

```text
Replica set has no primary
Server selection timed out
```

Possible causes:

- Election has not finished yet;
- One or more members are unhealthy;
- Hostnames fail to resolve;
- Members cannot reach each other;
- Inconsistent `rs0` configuration;
- Data volumes contain stale config from an earlier lab;
- Votes/priorities leave no eligible candidate.

How to check:

```bash
docker compose ps
docker compose logs --tail=100 mongo1
docker compose logs --tail=100 mongo2
docker compose logs --tail=100 mongo3
```

In `mongosh`:

```javascript
rs.status();
rs.conf();
db.adminCommand({ hello: 1 });
```

Never delete volumes before verifying whether they hold data you need to keep.

## 54. Troubleshooting: Client Connects to One Host but Fails on Replica Set URI

Description:

```text
mongosh mongodb://localhost:27017 works
Java replicaSet URI times out
```

Common cause in Docker labs:

- Client runs on the host while the replica set advertises Docker DNS hostnames;
- Ports aren't published or DNS/hosts mappings are wrong;
- Client connects via an IP/hostname known to only one member;
- `replicaSet` name in URI mismatches `rs.conf()._id`.

### 54.1. Resolution

In the lab, run `mongosh`/Java inside the Docker network. In production, configure DNS and certificate SANs so clients can reach **every advertised member**, not only the first seed.

### 54.2. Never Fix HA Apps with `directConnection=true`

Direct mode connects to a single node and bypasses replica-set discovery/failover, causing writes to break whenever topology changes.

## 55. Troubleshooting: `NotWritablePrimary`

When a write hits a node that just lost primary status:

```text
NotWritablePrimary / not primary / node is recovering
```

Check:

- Whether client uses a replica set URI or direct member;
- Topology discovery state;
- `hello` on the current node;
- Driver version;
- Retryable writes setting;
- Server selection timeout;
- Election state.

If a client is pinned directly to the old node, retrying forever against that node will never turn it back into primary.

## 56. Troubleshooting: Majority Write Timeout

When majority ACK misses `wtimeout`:

```text
write concern timeout / write concern failed
```

Investigate:

1. Is there a primary?
2. Are enough voting/data-bearing members online for majority?
3. Which secondary is lagging or disconnected?
4. Are disk or network links saturated?
5. Was the write applied on the primary?
6. Is the operation idempotent?
7. Could the retry policy create duplicates?

Never lower `w:"majority"` to `w:1` in production just to silence timeouts without re-evaluating durability requirements.

## 57. Troubleshooting: Secondary Read Sees Stale Value

Example:

```text
Write status=PAID to primary, ACK majority
Read secondary C: status=PENDING
```

This reflects replication lag or read semantics, not necessarily data loss.

Remediation:

- Inspect `readPreference` and `readConcern`;
- If read-your-writes is required, use primary reads or causal sessions;
- Check member lag;
- Never trigger irreversible actions from a potentially stale read;
- Use event ordering or primary verification for critical workflows.

## 58. Troubleshooting: `rs.stepDown()` Rejected

Common causes:

- Not executed on the primary;
- No secondary is sufficiently caught up/eligible per helper checks;
- Majority is unavailable;
- Server is in an ineligible state;
- Missing admin privileges.

Steps:

1. Check `hello` to identify the current primary.
2. Inspect `rs.status()`.
3. Verify secondary health and lag.
4. Wait for stability and retry in the lab if appropriate.
5. Never blindly add the force option.

## 59. Troubleshooting: Primary Keeps Switching Back

Because the initial config gave `mongo1` higher priority, after a stepdown cooldown or node restart, the topology may re-elect the higher-priority member when eligible.

That is why you must:

- Never hardcode the primary node;
- Never assert failover permanently picks `mongo2`;
- Never treat an election test as failed simply because primary returns to `mongo1` minutes later;
- Inspect `rs.conf()` and election metrics.

To test deterministic long-term leadership, adjust priority/votes via controlled procedures—never reconfigure production just for a demo.

## 60. Rule: Never Run Dangerous Lab Commands Outside the Lab

These commands are **not** steps to run casually on production in this lesson:

```text
rs.stepDown(...)
rs.reconfig(...)
rs.freeze(...)
force reconfiguration
docker compose stop <primary>
docker compose down -v
db.dropDatabase()
```

Outside the lab, every topology-changing or destructive command needs a runbook, backups, proper authorization, change approval, and stop criteria.

### 60.1. Never Use `rs.reconfig` to Paper Over DNS Bugs

Changing member hostnames impacts the whole cluster and clients. Before reconfiguring, verify network/DNS/driver URIs, backups, and version-specific procedures.

### 60.2. Never Use `force:true` Just Because a Demo Feels Slow

Forced stepdowns/reconfigurations raise rollback and outage risks. The core lab uses standard stepdowns and observation.

## 61. Restoring to a Healthy State

After testing member shutdowns:

```bash
docker compose start mongo1
docker compose start mongo2
docker compose start mongo3
```

If already running, `start` confirms; use `docker compose ps` to verify.

Connect with the replica set shell:

```bash
docker compose exec mongo1 mongosh "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/lab?replicaSet=rs0"
```

Verify:

```javascript
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health
}));
```

Expected stable state:

```text
One PRIMARY
Two SECONDARY
All healthy
No member stuck in RECOVERING due to a lab issue
```

### 61.1. Do Not Expect Primary to Return to mongo1 Immediately

Priority takeovers happen after cooldowns and eligibility checks; what matters is a healthy cluster with a primary, synced replicas, and working clients.

### 61.2. Verify Data

```javascript
labDb.orders.find({
  _id: {
    $in: [
      "ORD-001",
      "WC-ONE-001",
      "WC-MAJ-001",
      "AFTER-FAILOVER-001"
    ]
  }
});
```

Record observations; never guess whether a failed write committed without evidence.

## 62. Stopping the Lab While Preserving Data

In the `compose.yaml` directory:

```bash
docker compose down
```

This stops and removes the project's containers and network while **preserving named volumes** (`mongo1_data`, `mongo2_data`, `mongo3_data`) by default.

When starting again:

```bash
docker compose up -d
```

Volumes retain data and replica set state. You typically do not rerun `rs.initiate()` if members keep their configuration.

### 62.1. Wiping the Lab When Certain Data Is No Longer Needed

**Command that deletes project volumes**—run only inside a confirmed lab:

```bash
docker compose down -v
```

This deletes all MongoDB data on the Compose project's named volumes. Never run it in a production directory or a folder holding other data without checking first.

### 62.2. Avoid Reusing Volumes Across Different Major Image Versions

If switching `mongo:8.0` to another major image, do not assume data files are compatible. Follow MongoDB's supported version upgrade path.

## 63. Summary of What Was Observed vs. What Remains Unproven

| Evidence Gatherable in This Lab | What Cannot Be Inferred Automatically |
|---|---|
| Exactly 1 primary exists | Primary will always be `mongo1` |
| Secondary saw the write | Secondaries never lag |
| Majority write ACK returned | All nodes applied the write |
| `w:1` write survived stepdown | All `w:1` writes are rollback-proof |
| Driver found the new primary | Zero requests fail during failover |
| `rs.stepDown` succeeded | Production RTO is met |
| Transaction committed | External payment committed alongside |
| Replication is healthy | Backups are unnecessary |
| Secondary read succeeded once | All stale reads are eliminated |
| Java app connects in container | URI works from host/public networks |

### 63.1. A Scientific Conclusion States Assumptions

Write:

> "In a single-host Docker lab, three data-bearing members elected a new primary after stepdown and a pre-failover majority write remained readable. Large lag was not observed; results do not prove production RTO or instantaneous sync on all secondaries."

Do not write:

> "MongoDB replica sets always fail over instantly and never lose data."

## 64. Exercise 1 — Diagram Topology

Draw a three-node replica set showing primary/secondaries, oplog replication, and client discovery. Explain why client URIs need multiple seed hosts and `replicaSet`, and why primary hosts must not be hardcoded.

## 65. Exercise 2 — Calculate Quorum

For 3, 5, and 7 voting members, compute majority. In a 3-member set, analyze losing one vs. two voting members. Why doesn't adding an arbiter increase data-bearing copies?

## 66. Exercise 3 — Initialize and Inspect Config

Using Compose, initialize `rs0`, inspect `rs.conf()` and `rs.status()`. Distinguish `priority`, `votes`, `stateStr`, `health`, and `optimeDate`. Record the current primary.

## 67. Exercise 4 — Verify DNS

Simulate a Java client outside the Docker network unable to resolve `mongo2`. Explain why it may reach an initial seed host and then time out during discovery. Propose a safe lab fix without breaking production replica set configs.

## 68. Exercise 5 — Compare Write Concerns

Insert 100 documents with `w:1` and 100 with `w:"majority"` using synthetic data. Carefully measure p50/p95 and explain why single-host tests do not prove multi-region performance.

## 69. Exercise 6 — Read Preference

Read an order from primary and from a secondary. Test `primary`, `secondary`, and `secondaryPreferred` and explain the trade-offs. Never claim `nearest` guarantees the newest data.

## 70. Exercise 7 — Read Concern

Distinguish `local`, `majority`, `snapshot`, and `linearizable`. Match business requirements for: order history, post-checkout confirmation screen, lag-tolerant reporting, and updating a critical single document.

## 71. Exercise 8 — Causal Session

Write a Java client using one `ClientSession` to perform a majority write followed by a majority read from a secondary. Explain why session/causal ordering matters and why sessions must not be shared arbitrarily across threads.

## 72. Exercise 9 — Stepdown

Inspect `rs.status`, run `rs.stepDown(60,10)` on the lab's current primary, log the timeline, identify the new primary, and continue writing with the replica set URI.

## 73. Exercise 10 — Stop Primary

Stop the current primary container in the lab, confirm the remaining two hold quorum, and observe the election and driver reconnect. Restart the old member and verify catch-up.

## 74. Exercise 11 — Stop Secondary

Stop one secondary and test `w:"majority"` across the remaining two. Next, test leaving only one member in the lab if you have a clear recovery plan, and explain why no writable primary exists.

## 75. Exercise 12 — Unknown Write Outcome

An `$inc` command hits a network timeout right during a primary stepdown. Write three questions to verify before retrying. Propose a stable operation ID or CAS to avoid double increments at the application layer.

## 76. Exercise 13 — Atomic Update

Two workers read `revision=5` and both try to change order status. Write an `updateOne` filtering by revision and explain `matchedCount=0`. Does a replica set prevent lost updates if both run unguarded `$set`?

## 77. Exercise 14 — Transaction

Run a lab transaction inserting two documents. Inject an error before commit in a separate clean run and verify zero partial state. Discuss unknown commit outcomes and transaction retries.

## 78. Exercise 15 — Secondary Lag

Execute 1,000 writes and inspect `optimeDate`/replication info. If lag does not show up, document why single-host labs cannot prove zero lag. Propose metrics to track in real deployments.

## 79. Exercise 16 — Arbiters and Trade-offs

Compare 3 data-bearing members vs. 2 data-bearing + 1 arbiter on availability, durability, write concerns, and transaction eligibility. When might an arbiter be considered and why is it not a data copy?

## 80. Exercise 17 — Client Observability

Add driver topology/command monitoring for your version. During a stepdown test, record primary discovery, retry counts, server selection duration, API p95/p99, and errors—without logging command payloads or secrets.

## 81. Exercise 18 — Network Partition Scenario

A 3-member cluster splits into groups of 2 and 1. Analyze which side can elect a primary, impacts on writes, secondary reads, and stale results. Never rely on forced reconfig.

## 82. Exercise 19 — Restoring from Backup

Suppose an operator accidentally deletes a collection and it replicates. Why doesn't electing a new primary restore the collection? Design a backup/PITR restore drill with RPO/RTO validation.

## 83. Exercise 20 — Lab Report

Write a report covering topology, `rs.conf`, member states, write/read concerns, failover timeline, unobserved-lag notes, client recovery, error classification, limitations, and production recommendations.

## 84. Pre-Lab Checklist

- [ ] Docker Compose and compatible MongoDB image available.
- [ ] Dedicated project directory used; never mix production volumes.
- [ ] Unauthenticated ports are not published externally.
- [ ] Sufficient resources for three `mongod` instances.
- [ ] Docker DNS addresses and host connectivity limits understood.
- [ ] Three separate volumes configured.
- [ ] Familiar with `docker compose ps/logs/start/stop`.
- [ ] Operating only on an authorized environment.
- [ ] Goals and commands documented beforehand.
- [ ] Zero real user data in the lab.

## 85. Post-Initialization Checklist

- [ ] `rs.conf()._id` is `rs0`.
- [ ] All three hostnames match the Compose network.
- [ ] Three voting data-bearing members exist.
- [ ] Exactly one `PRIMARY` exists.
- [ ] Remaining members are healthy `SECONDARY` nodes.
- [ ] `rs.status` shows no abnormal errors.
- [ ] MongoDB client URI includes `replicaSet=rs0`.
- [ ] Test inserts and queries succeed.
- [ ] Member states and optimes inspected.
- [ ] Clear understanding that `priority` does not guarantee current role.

## 86. Post-Stepdown Checklist

- [ ] Pre-stepdown state recorded.
- [ ] Stepdown executed strictly on the lab primary.
- [ ] New primary elected if quorum suffices.
- [ ] Replica-set client rediscovered and routed automatically.
- [ ] `w:majority` writes reconciled.
- [ ] Never concluded `w:1` is rollback-safe from a single test.
- [ ] Former primary/secondaries returned to stable state.
- [ ] No long-running app workers stuck.
- [ ] Timeout/error metrics and recovery time recorded.
- [ ] Forced reconfig never used as a "quick fix."
- [ ] All lab members restarted cleanly.

## 87. Consistency Understanding Checklist

- [ ] Distinguish write concern from read concern.
- [ ] Distinguish read concern from read preference.
- [ ] Know secondaries can lag.
- [ ] Understand majority means a subset, not all nodes.
- [ ] Understand read-your-writes requires specific session/concern conditions.
- [ ] Know transaction scope differs from external side effects.
- [ ] Use CAS for business state races.
- [ ] Use idempotency to handle unknown outcomes.
- [ ] Never treat elections as backups.
- [ ] Never extrapolate single-host observations into production SLAs.

## 88. References

Check documentation for the **exact MongoDB Server, `mongosh`, and Java Driver versions** in use:

- [MongoDB Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [Deploy Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB `rs.initiate()`](https://www.mongodb.com/docs/manual/reference/method/rs.initiate/)
- [MongoDB `rs.status()`](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB `rs.conf()`](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB `rs.stepDown()`](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB `hello` Command](https://www.mongodb.com/docs/manual/reference/command/hello/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Driver Connection Strings](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/)

## Conclusion

Through this lab, you built a MongoDB **replica set of three data-bearing members**, inspected configurations and roles, wrote data, observed replicas on secondaries, stepped down the primary with `rs.stepDown()`, and observed client behavior across elections.

The key takeaway is not merely watching `mongo2` become `PRIMARY`. Replica sets provide **leader election and replication**, yet every guarantee must still be configured explicitly:

- **`w:1`** acknowledges on the primary per application rules; it does not mean a majority stored the write.
- **`w:"majority"`** provides stronger majority commit durability; it does not mean all secondaries have caught up.
- **`readPreference`** controls which node serves reads; it does not guarantee the newest data version.
- **`readConcern`** and **causal sessions** provide different guarantees over observed state.
- **Single-document atomicity**, **CAS**, and **multi-document transactions** enforce invariants distinct from replication.
- **Retries and idempotency** remain essential because a failover-window timeout can leave the client with an unknown outcome.

Furthermore, a three-container lab on a single machine cannot simulate real network faults, zone outages, disk corruption, or production latencies. Observing zero lag on a secondary in one run is a valid artifact of the test environment, **never proof that replication never lags**.

**A resilient MongoDB application does not need to predict which node is primary. It selects business-appropriate write and read concerns, lets the driver handle topology transitions, protects writes with idempotency, and validates consistency assumptions through repeatable tests.**
