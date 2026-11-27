# Read preference: primary, secondary, and preference modes in MongoDB

## 1. Context and objectives

MongoDB supports **replica sets** to provide fault tolerance and data replication. In a typical replica set, the **primary** receives write operations, while **secondaries** replicate those operations and can serve read queries. When an application has multiple candidate nodes for reads, a policy is needed to decide where to route queries.

**Read preference** is the policy for selecting which member serves a read operation. MongoDB has five primary modes:

- `primary`
- `primaryPreferred`
- `secondary`
- `secondaryPreferred`
- `nearest`

This lesson helps you:

1. Understand the node selection mechanism and differences among the five modes.
2. Analyze when data from a secondary may be stale (*stale read*).
3. Use **read preference tags**, `maxStalenessSeconds`, and `localThresholdMS`.
4. Configure read preference in connection URIs, `mongosh`, Node.js, and the Java Driver.
5. Distinguish read preference from **read concern**, **write concern**, **causal consistency**, and transactions.
6. Design appropriate modes for transactional screens, reports, multi-region lookups, and failover handling.

**Key takeaway:** Read preference answers the question **"Which node does MongoDB read from?"** It **does not guarantee** "data is always the freshest," "reading your just-executed write," or "an entire sequence of operations shares a consistent snapshot."

## 2. Replica sets: primary, secondary, and replication lag

Simple diagram:

~~~text
                Application / MongoDB Driver
                            |
                            v
                   Replica set rs0
                     /     |      \
                    v      v       v
              +--------+ +--------+ +--------+
              | PRIMARY| |SECONDARY| |SECONDARY|
              |  A     | |   B     | |   C     |
              +--------+ +--------+ +--------+
                  |           ^          ^
                  +-----------+----------+
                    Asynchronous replication
~~~

The primary handles normal writes. Secondaries apply written operations via the replication stream. Why is read preference needed?

- If all reads hit the primary, the primary handles both reads and writes and can become overloaded.
- Offloading some reads to secondaries distributes load, at the cost of accepting replication lag.
- If the cluster spans multiple regions, network latency between the application and each member differs.
- During a primary election, some modes can read from secondaries, while others intentionally do not fall back.

### 2.1. How does a stale read happen?

~~~text
T0   Client writes order O-100 to primary A.
T1   A acknowledges the write according to the chosen write concern.
T2   Client reads O-100 from secondary B.
T3   B finishes applying the O-100 record.
~~~

At T2, secondary B may **not yet have** O-100. The query at that moment may return `null`, even though the prior write request was accepted by the primary. This is the gap between **the latest state on the primary** and **the state already applied by the secondary**.

Do not confuse these terms:

| Term | Meaning |
| --- | --- |
| Read preference | Selects which member serves reads |
| Replication lag | Delay for a secondary to receive/apply writes |
| Read concern | Rules governing which versions of data can be read |
| Write concern | Level of write acknowledgment under the replication mechanism |
| Causal consistency | Guarantees causal order among operations within an eligible session |
| Transaction | Group of operations with transactional semantics within supported scope |

## 3. Comparison table of the five modes

| Mode | When cluster is healthy | No primary available | No eligible secondary | Can it be stale? |
| --- | --- | --- | --- | --- |
| `primary` | Reads primary only | No read node available; may time out/fail | Still reads primary | No from secondary replication lag, though still depends on read concern |
| `primaryPreferred` | Prefers primary | Falls back to secondary if available | Uses primary if available | Yes, when falling back to secondary |
| `secondary` | Reads secondary only | Can still read secondaries | Server selection error/timeout; does not fall back to primary | Yes |
| `secondaryPreferred` | Prefers secondary | Can read secondaries | Falls back to primary if available | Yes, when using secondaries |
| `nearest` | Selects primary or secondary within latency window | Can read secondaries | Can select primary | Yes, if a secondary is selected |

**The default mode is `primary`.**

You can remember them as:

~~~text
primary            -> PRIMARY only
primaryPreferred   -> PRIMARY first, SECONDARY fallback
secondary          -> SECONDARY only
secondaryPreferred -> SECONDARY first, PRIMARY fallback
nearest            -> eligible primary or secondary by latency
~~~

The word **Preferred** indicates **preference and fallback**, not a guarantee that every operation reaches the preferred node type. Even after a member is selected, an operation can still fail due to network issues, load, or server state transitions.

## 4. `primary` mode: default for transactional applications

`primary` allows reads only from the primary:

~~~javascript
// Illustrative driver option:
{ readPreference: "primary" }
~~~

While the primary is healthy, the driver sends reads to the primary. If the primary is unavailable during an election, the client waits up to the server selection timeout and then reports an error.

**Advantages:**

- Avoids reading from secondaries that have not yet applied recent writes.
- Suitable for APIs needing responses closely aligned with recently updated state.
- Straightforward when operating transactional workflows.
- Aligns with rules for transactions containing reads.

**Trade-offs:**

- The primary bears the read workload.
- No secondary fallback during primary unavailability windows.
- If the application is far from the primary, RTT may be higher than to a nearby secondary.

### 4.1. Primary does not mean every read is linearizable

`readPreference: "primary"` **does not automatically turn read concern into `majority` or `linearizable`**. It only selects the member serving the read. Consistency, rollback exposure, and snapshots depend on read concern/write concern and topology.

### 4.2. Primary is incompatible with tag sets and max staleness

Do not use:

~~~text
readPreference=primary&readPreferenceTags=region:vn
readPreference=primary&maxStalenessSeconds=120
~~~

Read preference tags and `maxStalenessSeconds` are incompatible with `primary` mode; drivers may reject the configuration.

## 5. `primaryPreferred` mode: primary first, secondary when needed

`primaryPreferred` selects the primary when it is available. When the primary is unavailable, the driver evaluates eligible secondaries according to tags, staleness, and latency:

~~~javascript
{ readPreference: "primaryPreferred" }
~~~

Flow diagram:

~~~text
Is primary available?
  |
  +-- YES --> select primary
  |
  +-- NO  --> find eligible secondary
                   |
                   +-- found --> select secondary
                   +-- none  --> selection timeout / error
~~~

**Use case:** applications prioritizing primary-fresh state, while tolerating **stale reads during failover** to improve query availability.

An easily overlooked detail: when a request switches to a secondary while no primary exists, results can be **older than what the user already saw** in an earlier primary read. Do not pick this mode if business rules strictly forbid backward state reads.

### 5.1. Tags only take effect during fallback

For example, wanting to fall back to a secondary in the Vietnam region:

~~~javascript
{
  readPreference: "primaryPreferred",
  readPreferenceTags: [
    { region: "vn" }
  ]
}
~~~

While the primary in Singapore is healthy, the driver still prefers that primary; the `region: "vn"` tag **does not force the primary to match the tag**. Tags are only applied when secondaries are candidates.

## 6. `secondary` mode: read from secondaries only

`secondary` selects an eligible **secondary** and **never falls back to the primary** if no secondary is available:

~~~javascript
{ readPreference: "secondary" }
~~~

Suitable for:

- Dashboards that tolerate data delayed by some interval.
- Reports/analytics or batch queries that do not require read-your-writes.
- Read workloads that can be isolated from the primary.
- Export tasks with well-defined resource limits.

If a replica set has only a primary and no eligible secondaries, `secondary` will find no matching server. Wait duration depends on `serverSelectionTimeoutMS` and driver mechanics.

**Do not choose `secondary`** to make a critical write decision based on a just-read value—such as deducting inventory or verifying recently revoked permissions—without designing appropriate consistency/atomicity mechanisms.

### 6.1. Secondary reads also have costs

Reading from secondaries can reduce query CPU on the primary, but still consumes CPU, I/O, and cache on the secondary. Heavy reporting queries can slow down oplog application on a secondary, increasing lag. Do not assume "offloading more reads to secondaries is always better."

## 7. `secondaryPreferred` mode: secondary first, primary when needed

`secondaryPreferred` selects a secondary when available, but **falls back to the primary** if no eligible secondary exists:

~~~javascript
{ readPreference: "secondaryPreferred" }
~~~

~~~text
Eligible secondary available?
  |
  +-- YES --> select secondary
  |
  +-- NO  --> primary available?
                   |
                   +-- yes --> read primary
                   +-- no  --> error
~~~

Advantage: distributes reads to secondaries under normal conditions while retaining read capability when secondaries are unavailable.

Disadvantage: when secondaries fail, query traffic can **surge onto the primary right when the system is degraded**. Measure read load and design rate limiting/circuit breakers if needed.

If the requirement is to **never** let reporting jobs read from the primary, use `secondary`, not `secondaryPreferred`.

### 7.1. Why tags may fail to enforce load isolation

With `secondaryPreferred` + tag `workload: "analytics"`, the client prefers matching secondaries. When no eligible secondary exists, the policy can still fall back to the primary. Tags are not used to exclude the primary in the fallback branch of this mode.

## 8. `nearest` mode: latency window priority, role-agnostic

`nearest` treats primary and secondaries as equal candidates, filters by criteria, and selects a node within the **latency window**:

~~~javascript
{ readPreference: "nearest" }
~~~

General algorithm:

1. Find members in eligible states.
2. Filter secondaries by `maxStalenessSeconds` if configured.
3. Filter by read preference tag sets if configured.
4. Determine the minimum RTT and add `localThresholdMS` to form the window.
5. Select a member among eligible candidates inside the window.

The default `localThresholdMS` is typically **15 ms**.

Example:

| Member | Role | RTT |
| --- | --- | ---: |
| A | primary | 11 ms |
| B | secondary | 17 ms |
| C | secondary | 43 ms |

With a 15 ms threshold, the maximum window RTT is **26 ms**. A and B are candidates; C is excluded. The driver may pick **A or B**, not strictly A.

**`nearest` does not mean:**

- The geographically closest member.
- The member with the freshest data.
- The member guaranteed to respond fastest to every query.
- Always avoiding the primary.

`nearest` is suitable when network latency matters more than fixing primary/secondary roles and the application can handle stale reads.

## 9. Server selection mechanism and timeouts

Read preference is evaluated **per operation**, rather than pinning the entire application lifecycle to a single member. Factors involved:

- Current replica set topology: primary, secondary, unreachable/recovering.
- Selected read mode.
- Tag set lists.
- `maxStalenessSeconds`.
- `localThresholdMS` or corresponding router threshold.
- Server selection timeout and connection health.

### 9.1. Selection timeout is not query timeout

Example connection URI:

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary&serverSelectionTimeoutMS=5000
~~~

`serverSelectionTimeoutMS=5000` limits the process of **finding an eligible member**, not how long a query already running on a selected member may execute.

If no secondary exists, `secondary` mode can trigger a server selection error when the timeout expires. Increasing this timeout does not magically create a new secondary.

### 9.2. Reading from secondaries does not redirect writes to secondaries

Read preference does not alter standard replica set write rules. `insert`/`update`/`delete` commands still require an eligible primary. When no primary exists during an election, `secondaryPreferred` may continue serving reads, **but does not make writes available on secondaries**.

## 10. Read preference tags: grouping servers by metadata

Administrators can attach tags to replica set members, for example:

~~~javascript
// Conceptual configuration example, not a live command
// modifying an actual replica set.
{
  host: "db-secondary-vn.example.net:27017",
  priority: 0,
  tags: {
    region: "vn",
    workload: "analytics"
  }
}
~~~

Tags `region` and `workload` are system-defined conventions, not attributes automatically populated by MongoDB.

Read policy:

~~~javascript
{
  readPreference: "secondary",
  readPreferenceTags: [
    { region: "vn", workload: "analytics" }
  ]
}
~~~

Only secondaries matching the tag set and other criteria are eligible.

### 10.1. Tag set lists are priority lists

Example:

~~~javascript
[
  { region: "vn", workload: "analytics" },
  { region: "sg" },
  {}
]
~~~

The driver evaluates tag sets in order:

1. Find eligible members matching the first tag set.
2. If none match, try the second tag set.
3. If still none match, `{}` permits any member passing the remaining mode/staleness criteria.

A member does not have to match all three tag sets simultaneously.

### 10.2. Tags applied by mode

| Mode | Tag rules |
| --- | --- |
| `primary` | Incompatible |
| `primaryPreferred` | Only when selecting a secondary |
| `secondary` | Always when selecting a secondary |
| `secondaryPreferred` | When selecting a secondary; does not force fallback primary to match tags |
| `nearest` | Filters both primary and secondaries |

If no member matches the tags and the mode is `secondary`, the client does not automatically ignore tags. If broad fallback is desired, include an empty tag set `{}` in the list per agreed policy.

**Tags do not guarantee freshness.** The tag `region: "vn"` says nothing about how far behind that secondary is lagging.

## 11. `maxStalenessSeconds`: filtering overly lagging secondaries

`maxStalenessSeconds` lets you exclude secondaries whose **estimated replication staleness** exceeds a threshold.

Example:

~~~text
readPreference=secondaryPreferred
maxStalenessSeconds=120
~~~

Secondary candidates with estimated lag greater than 120 seconds are excluded by server selection.

### 11.1. Minimum threshold of 90 seconds

MongoDB requires `maxStalenessSeconds` to be **at least 90 seconds** (and satisfy requirements relative to the driver's heartbeat frequency).

~~~text
maxStalenessSeconds=5    -> invalid
maxStalenessSeconds=30   -> invalid
maxStalenessSeconds=90   -> meets minimum threshold
maxStalenessSeconds=120  -> meets minimum threshold
~~~

Staleness estimation relies on heartbeats and observed write timestamps, not millisecond-exact tracking. That is why a 5-second threshold cannot be enforced via this option alone.

### 11.2. Compatible modes

| Mode | `maxStalenessSeconds` |
| --- | --- |
| `primary` | **Cannot be used** |
| `primaryPreferred` | Yes, when falling back to secondary |
| `secondary` | Yes |
| `secondaryPreferred` | Yes |
| `nearest` | Yes, to filter secondaries |

If no primary exists, secondaries may be compared against the secondary with the most recent write time per the driver's algorithm, rather than against an unavailable primary.

### 11.3. Do not misunderstand the staleness bound

`maxStalenessSeconds=120` **does not guarantee** data is "at most exactly 120 seconds old" for every operation. It is a **coarse estimation node filter**. A secondary may start lagging further right after a heartbeat; a query may hit the primary under fallback modes; read concern and causal context also affect observed state.

For guaranteed read-your-writes, see causal consistency in a later section.

## 12. URI configuration

Examples assume a replica set named `rs0` with three endpoints. Production URIs must replace hostnames/credentials with real values and avoid storing secrets in source code.

**Default primary:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0
~~~

**Secondary only:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary
~~~

**PrimaryPreferred:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=primaryPreferred
~~~

**SecondaryPreferred with staleness:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondaryPreferred&maxStalenessSeconds=120
~~~

**Nearest with latency threshold:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=nearest&localThresholdMS=20
~~~

**Secondary with prioritized tag sets:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondary&readPreferenceTags=region:vn,workload:analytics&readPreferenceTags=region:sg
~~~

Repeating the `readPreferenceTags` parameter represents a **list of tag sets**, not two tags that must both match simultaneously.

When using Atlas with a `mongodb+srv://...` URI, read preference can also be configured via options supported by the driver and deployment; do not modify DNS/SRV/credentials just for testing.

## 13. `mongosh` practice on a replica set

### 13.1. Preparation

The following operations require an **active replica set**. On standalone instances, there are no eligible secondaries to test against.

~~~javascript
const lab = db.getSiblingDB("read_preference_lab");

lab.events.insertOne({
  _id: "e1",
  eventType: "created",
  createdAt: new Date()
});

lab.events.findOne({ _id: "e1" });
~~~

Writes are sent to the primary per replica set write rules. Reading from the primary immediately after an acknowledged write usually observes the new document; durability and rollback exposure depend on write/read concern.

### 13.2. Changing the `mongosh` connection's read preference

~~~javascript
db.getMongo().setReadPref("primary");

const lab = db.getSiblingDB("read_preference_lab");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("secondary");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("secondaryPreferred");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("primaryPreferred");
lab.events.find({}).limit(5).toArray();

db.getMongo().setReadPref("nearest");
lab.events.find({}).limit(5).toArray();
~~~

On a system with slow replication, a secondary read might not see `e1` yet even after the write completed. If no secondary exists, reading with `secondary` may time out.

After practicing, reset to default:

~~~javascript
db.getMongo().setReadPref("primary");
~~~

### 13.3. Inspecting topology

When connected directly to a replica set `mongod` with appropriate privileges:

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
~~~

Observe member states and replication timestamps. Output varies by version and may require operational privileges. On `mongos`, do not run these commands as if the router were a replica set member.

`db.hello()` reports server/topology information in that command's context, **not proof** that every subsequent `find()` goes to the same member. The driver can select a different node per operation.

## 14. MongoDB Node.js Driver: choosing mode per operation

Example running in a Node.js application, not `mongosh`:

~~~javascript
const { MongoClient } = require("mongodb");

const uri =
  "mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0";

async function main() {
  const client = new MongoClient(uri);

  try {
    await client.connect();

    const orders = client.db("app").collection("orders");

    await orders.insertOne({
      _id: "ORD-100",
      status: "PAID",
      createdAt: new Date()
    });

    // Freshness-sensitive read: primary.
    const detail = await orders.findOne(
      { _id: "ORD-100" },
      { readPreference: "primary" }
    );

    // Staleness-tolerant report: secondaryPreferred.
    const history = await orders.find(
      { status: "PAID" },
      { readPreference: "secondaryPreferred" }
    )
    .limit(20)
    .toArray();

    console.log({
      detail,
      reportCount: history.length
    });
  } finally {
    await client.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
~~~

Notes:

- The example assumes an existing replica set and write permissions.
- `detail` and `history` use **different read preferences** on the same collection handle.
- Do not assume `history` will always immediately include ORD-100.
- `toArray()` suits small result sets; large reports should stream through a cursor in batches.
- Production/tests should avoid reusing fixed `_id` values across runs to prevent duplicate key errors on re-execution.

### 14.1. Command monitoring to verify the serving node

The Node.js Driver supports command events on compatible versions:

~~~javascript
const { MongoClient } = require("mongodb");

const client = new MongoClient(process.env.MONGODB_URI, {
  monitorCommands: true,
  readPreference: "secondaryPreferred"
});

client.on("commandStarted", event => {
  if (["find", "aggregate"].includes(event.commandName)) {
    console.log({
      command: event.commandName,
      address: event.address
    });
  }
});
~~~

In a replica set, the address in the command event helps see which member received the command. In a sharded cluster, driver-side events may only show **`mongos`/router**, not confirming the final shard member. Do not log raw queries or sensitive data.

## 15. Java Sync Driver: scoping via collection handles

Java example:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ReadPreferenceExample {
    public static void main(String[] args) {
        ConnectionString uri = new ConnectionString(
            "mongodb://db1:27017,db2:27017,db3:27017/"
                + "?replicaSet=rs0"
        );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(uri)
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase database = client.getDatabase("app");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            // New handle dedicated to reporting.
            MongoCollection<Document> reportingOrders =
                orders.withReadPreference(
                    ReadPreference.secondaryPreferred()
                );

            Document detail = orders.find(
                new Document("_id", "ORD-100")
            ).first();

            reportingOrders.find(
                new Document("status", "PAID")
            ).limit(20).forEach(
                doc -> System.out.println(doc.toJson())
            );

            System.out.println(detail);
        }
    }
}
~~~

`withReadPreference()` returns a collection handle with the selected policy without changing the default for all queries across the application. If reports **must never fall back to the primary**, substitute `ReadPreference.secondary()`.

To configure advanced tags, max staleness, or custom server selection, use the `ReadPreference` API matching your **active driver version**, as overloads and builders may vary.

## 16. Read preference differs from read concern and write concern

| Setting | Question solved | Example values |
| --- | --- | --- |
| Read preference | Which member to read from? | `primary`, `secondaryPreferred` |
| Read concern | What commit/snapshot level of data can be read? | `local`, `majority`, `snapshot`, `linearizable` |
| Write concern | When is the client notified that a write is recorded/replicated? | `w:1`, `w:"majority"` |
| Causal consistency | Are causally related operations observed in proper order? | Session with majority read/write concerns |

### 16.1. Read concern `local`

With `local`, the query reads available data on the member per local read concern semantics. On a secondary, data may lag due to replication. Read data may include non-majority-committed writes, with corresponding rollback considerations.

### 16.2. Read concern `majority`

`majority` focuses on majority-committed data. However, reading from a secondary with `readConcern: "majority"` **does not mean** it already has every latest write acknowledged by the primary. The member still needs to apply writes or serve an eligible point in time.

### 16.3. Write concern `majority`

`w: "majority"` achieves write acknowledgment across a majority of eligible members. It **does not force** every secondary to serve subsequent queries immediately at the client's desired instant, nor does it turn an ordinary secondary read into read-your-writes.

### 16.4. Read concern `linearizable`

`linearizable` is supported under specific conditions tied to **reads on the primary**. You cannot set read preference secondary and expect that read path to have linearizable semantics like primary reads.

### 16.5. Transactions with reads

Per MongoDB rules, transactions containing read operations must use **`readPreference` `primary`**; transaction operations are routed according to transaction rules. Do not switch read preference to `secondaryPreferred` for transactions merely to offload traffic.

**Conclusion:** Selecting read preference is a first step, not a substitute for defining required freshness/durability/isolation.

## 17. Causal consistency: when read-your-writes across secondaries is needed

A familiar scenario:

~~~text
T1: User updates displayName on primary.
T2: GET profile API reads secondary.
T3: Secondary has not applied the write yet.
=> GET returns old displayName.
~~~

If the application needs to see the user's own writes, two approaches are commonly considered:

1. Read from the **primary** for freshness-sensitive steps.
2. Use a **causally consistent session** with appropriate read/write concerns if reading from secondaries while preserving causal ordering is required.

### 17.1. Session with majority write/read concern

Node.js example:

~~~javascript
const { MongoClient } = require("mongodb");

async function writeThenReadSecondary(client) {
  const orders = client.db("app").collection("orders");
  const session = client.startSession({
    causalConsistency: true
  });

  try {
    await orders.insertOne(
      {
        _id: "causal-order-001",
        status: "PAID"
      },
      {
        session,
        writeConcern: { w: "majority" }
      }
    );

    const document = await orders.findOne(
      { _id: "causal-order-001" },
      {
        session,
        readPreference: "secondary",
        readConcern: { level: "majority" }
      }
    );

    return document;
  } finally {
    await session.endSession();
  }
}
~~~

MongoDB provides **read your writes**, **monotonic reads**, and other causal guarantees for sessions when reads use `majority` read concern and writes use `majority` write concern per documentation rules.

**Trade-off:** If the chosen secondary cannot yet serve the required logical time, the read may wait or return an error/timeout. Causal consistency **does not make replication happen instantaneously**.

**Do not confuse:** A causally consistent session is not a multi-document transaction, does not block other writers from modifying data, and does not automatically propagate causal relationships between requests not sharing the same causal context.

### 17.2. Commonly cited guarantees

- **Read your writes:** a subsequent read reflects a prior causally related write.
- **Monotonic reads:** a subsequent read does not revert to a state earlier than a previously observed state.
- **Monotonic writes:** ordering among related writes is preserved.
- **Writes follow reads:** a write following a read respects the causal relationship of the read.

A single session must not be used concurrently without coordination across multiple threads if the driver requires sequential execution to maintain causal ordering.

## 18. Failover: what happens to the five modes?

Suppose:

~~~text
Initially:
  A = primary
  B = secondary
  C = secondary

When A is lost:
  A = unavailable
  B = secondary
  C = secondary

After election:
  B = new primary
  C = secondary
~~~

During the window with no primary:

| Mode | Possible outcome |
| --- | --- |
| `primary` | No primary; waits and fails if timeout expires |
| `primaryPreferred` | Falls back to an eligible secondary |
| `secondary` | Can still read from an eligible secondary |
| `secondaryPreferred` | Can still read from secondaries |
| `nearest` | Can select a secondary within latency window |

After the election, the driver updates topology and continues applying the mode. Read preference is re-evaluated across operations.

Conditions that can cause selection to fail even when nodes are running:

- Nodes are not in a state permitted to serve reads.
- No eligible node matches tags.
- Secondaries are too stale per `maxStalenessSeconds`.
- Network partition or timeout.
- A member changed roles mid-server-selection.

Choose modes based on your business contract:

- **Accept temporary errors rather than stale reads:** keep `primary`.
- **Prioritize availability over freshness during elections:** consider `primaryPreferred`.
- **Reports must never hit the primary:** choose `secondary`.

## 19. Read preference in sharded clusters

Applications typically send queries to `mongos` or a service-managed cluster router. The router routes reads to eligible members of each shard's replica set.

~~~text
Application
     |
   mongos
     |
     +---- Shard 1 replica set
     |      primary + secondaries
     |
     +---- Shard 2 replica set
            primary + secondaries
~~~

Read preference in multi-shard clusters introduces extra considerations:

- Queries not targeting the shard key can **scatter-gather** across multiple shards.
- Each shard may select a different member based on the policy.
- Latency to the router does not fully reflect latency to each shard member.
- Data across shards may be at different replication progress points.
- Queries missing indexes remain slow even when reading from `secondary` or `nearest`.

Thus, **read preference does not replace a good shard key, proper indexes, and query planning**.

### 19.1. Long-running secondary reads

MongoDB 8.2 and later introduced changes in handling certain long-running secondary reads in sharded clusters during orphaned document cleanup after chunk migrations. For long export/analytics jobs, check actual version documentation and implement appropriate resume/retry mechanisms.

## 20. Choosing mode by workload

| Workload | Commonly considered mode | Risks and notes |
| --- | --- | --- |
| User just created an order and opens details | `primary` | Prioritizes freshness |
| Login/access permissions just changed | `primary` | Needs appropriate consistency; do not rely solely on read preference |
| Periodic reports tolerating delay | `secondary` | Must handle timeouts if secondaries fail |
| High-read product listings | `secondaryPreferred` | Can be stale; fallback to primary adds load |
| Lookups tolerating staleness during election | `primaryPreferred` | Freshness may drop during fallback |
| Multi-region app prioritizing RTT | `nearest` + tags | No role or freshest-state guarantee |
| Reporting jobs never allowed on primary | `secondary` + tags | Fails if no eligible secondary exists |
| Transactions with reads | `primary` | Required by transaction rules |
| Counters/inventory used as write conditions | `primary` + atomic conditional update | Never just read then unconditionally write |

### 20.1. Avoid making write decisions from stale reads

Incorrect example:

~~~javascript
const product = await products.findOne(
  { _id: "SKU-1" },
  { readPreference: "secondary" }
);

if (product && product.stock > 0) {
  await products.updateOne(
    { _id: "SKU-1" },
    { $inc: { stock: -1 } }
  );
}
~~~

Secondaries can be stale; two requests can also both observe positive stock. Unconditional updates can then drive stock negative.

The safe approach is an **atomic conditional update**:

~~~javascript
const result = await products.updateOne(
  { _id: "SKU-1", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);

if (result.modifiedCount === 0) {
  // Out of stock or document did not match.
}
~~~

Condition and mutation are executed on **a single document in one write**, rather than relying on a stale value read from a secondary.

## 21. Monitoring replication lag and read routing

Causes of slow/stale secondary reads:

- Network congestion or high latency between members.
- Secondary applying oplog slowly due to CPU/disk bottlenecks.
- Reporting queries competing for resources with replication.
- Node undergoing initial sync/recovery or unavailable.
- Elections changing primary/secondary roles.
- Driver filtering out all eligible secondaries due to tags or max staleness.

In authorized environments, you can use:

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
~~~

These commands apply when connected directly to a replica set `mongod` with appropriate privileges; do not run them on `mongos` expecting cluster-wide stats.

On the driver side, monitor:

- Server Discovery and Monitoring (SDAM) events.
- Command monitoring and target member addresses receiving reads.
- Server selection timeouts.
- Read latency p50/p95/p99.
- Replication lag and count of eligible secondaries.
- Read/write load on primary and secondaries.
- Rate of missed read-after-write updates if business-critical.

**Do not look only at average replication lag.** A secondary may have low lag yet slow queries due to missing indexes or CPU saturation; `nearest` may reduce network RTT while still hitting slow backend queries.

## 22. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Secondary read misses a just-written update | Replication lag | Read primary or use causal session with majority |
| `secondary` mode times out | No eligible secondary | Check member state, tags, staleness, timeout |
| `secondaryPreferred` suddenly floods primary | Fallback when secondaries unavailable | Capacity/rate limit; choose `secondary` if isolation required |
| `primaryPreferred` returns old data during election | Secondary fallback | Avoid this mode for data that must stay fresh |
| `nearest` picks primary sometimes, secondary other times | RTT window and eligible member selection | Choose a role-specific mode if needed |
| `primary` with tag sets fails | Tags incompatible with `primary` | Remove tags or use another mode |
| `primary` with `maxStaleness` fails | Max staleness incompatible | Remove option |
| `maxStaleness` of 5 seconds rejected | Minimum is 90 seconds | Pick a valid value; measure actual lag |
| Tag `vn` finds no server | No eligible member matches | Check replica set config and fallback tags |
| Majority read concern still misses write | Secondary has not reached causal point | Use causal session with majority read/write |
| Slow query despite `nearest` | Bad query plan/index or scatter-gather | Run explain and check shard targeting |
| Transaction fails when using secondary read | Transaction reads require `primary` | Set `primary` for transactions |
| `mongosh` query on standalone has no secondary | Topology lacks replica selection | Test with a replica set |
| `rs.status()` fails via `mongos` | Router is not a replSet member | Use appropriate endpoint/privileges |
| Changing batch size does not fix staleness | Batch size differs from server selection | Use proper read preference and consistency settings |

## 23. Practice exercises

### Exercise 1 — Distinguishing the five modes

Explain in one sentence each: `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest`. In which mode is the primary **never** used for read queries?

**Answer:** `secondary` never reads primary; `primary` reads primary only; preferred modes fall back; `nearest` can choose either.

### Exercise 2 — No primary available

Primary A is lost, B/C remain secondaries, and the election has not completed yet. Predict reads for each mode. Which mode definitely will not fall back to a secondary?

**Answer:** `primary`; other modes can select eligible secondaries.

### Exercise 3 — No secondary available

A remains primary, while B/C are unavailable. Compare `secondary` and `secondaryPreferred`.

**Answer:** `secondary` has no target and can time out; `secondaryPreferred` falls back to primary.

### Exercise 4 — Latency window

A has RTT=11ms (primary), B=17ms (secondary), C=43ms (secondary). `localThresholdMS=15`. With `nearest`, which nodes fall inside the window?

**Answer:** A and B (max RTT 26ms), not C.

### Exercise 5 — Tag set list

You want to prefer secondaries with `{region:"vn",workload:"analytics"}`, else `{region:"sg"}`, else any eligible secondary. Write the tag set list.

**Answer:**

~~~javascript
[
  { region: "vn", workload: "analytics" },
  { region: "sg" },
  {}
]
~~~

### Exercise 6 — `primaryPreferred` with tags

Primary is in region `sg`, secondary in `vn`. Mode is `primaryPreferred` + tags `vn`. When the `sg` primary is healthy, where does the driver read from?

**Answer:** `sg` primary; tags apply only when falling back to secondaries.

### Exercise 7 — Max staleness threshold

Which values meet the minimum threshold: 10, 30, 90, 120 seconds? Can this be used with `primary`?

**Answer:** 90 and 120 meet the minimum threshold; incompatible with `primary`.

### Exercise 8 — URI

Write a URI for three members, replica set `rs0`, using `secondaryPreferred` and `maxStalenessSeconds` 120.

**Example:**

~~~text
mongodb://db1:27017,db2:27017,db3:27017/app?replicaSet=rs0&readPreference=secondaryPreferred&maxStalenessSeconds=120
~~~

### Exercise 9 — Read-your-writes

A user changes their name, immediately reads from a secondary, and sees the old name. Why? Name two ways to improve this.

**Answer:** Asynchronous replication; read from primary or use a causally consistent session with appropriate majority read/write concerns.

### Exercise 10 — Majority read concern

True or false: "`secondary` with `readConcern=majority` always sees a write just acknowledged by the primary."

**Answer:** False; majority read concern does not mean the secondary has caught up or shares causal context.

### Exercise 11 — Node.js overrides

Write code using `primary` for the newly-created-order screen and `secondaryPreferred` for reports. Why override per operation instead of changing the client-wide default?

### Exercise 12 — Java collection handles

Configure `ReadPreference.primary()` in `MongoClientSettings`, then create handle `orders.withReadPreference(ReadPreference.secondaryPreferred())`. Identify which queries use which policy.

### Exercise 13 — Secondary read to check stock

Why can reading stock from a secondary and then running an unconditional `$inc: -1` cause negative stock? Write the proper atomic conditional update.

**Answer:** Use filter `{_id, stock: {$gte:1}}` and `$inc: {stock:-1}` on primary; check `modifiedCount`.

### Exercise 14 — Handling failover

An application has heavy reports that tolerate staleness but **must never consume primary CPU**. Should it use `secondary` or `secondaryPreferred`?

**Answer:** `secondary`, because `secondaryPreferred` falls back to primary if no eligible secondary exists.

### Exercise 15 — Sharded clusters

A query without the shard key uses `readPreference: nearest`. Why can it still be slow?

**Answer:** Scatter-gather across shards, poor index/query plan, and backend load; `nearest` only affects member selection, not query routing.

### Exercise 16 — Designing policies by SLA

A product has three APIs:

- GET details of a newly created order, requiring immediate visibility.
- Analytics dashboard, tolerating several minutes of delay.
- Multi-region content search prioritizing RTT, tolerating stale data.

Propose read preference, tags/max staleness, and complementary consistency mechanisms. Explain the trade-off when secondaries become unavailable.

## 24. Summary

**Read preference** is the policy for selecting a MongoDB member for read operations:

1. `primary`: primary only, default.
2. `primaryPreferred`: primary first, secondary fallback.
3. `secondary`: secondary only, no primary fallback.
4. `secondaryPreferred`: secondary first, primary fallback.
5. `nearest`: primary/secondary within the latency window.

**Tag sets** select member groups; **`maxStalenessSeconds`** filters overly lagging secondaries using a coarse estimate (minimum 90 seconds); **`localThresholdMS`** defines the RTT window for server selection.

Read preference **is not** read concern, write concern, or transactions. For **read-your-writes** or **monotonic reads** via secondaries, understand causal consistency and majority read/write concern conditions. For multi-document transactions, follow the primary read preference rule. For data used to gate write decisions, prefer **atomic conditional updates** rather than trusting stale secondary snapshots.

### Official MongoDB documentation

- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — definitions and modes.
- [Read Preference Modes](https://www.mongodb.com/docs/manual/core/read-preference-modes/) — behavior of each mode.
- [Server Selection / Read Preference Mechanics](https://www.mongodb.com/docs/manual/core/read-preference-mechanics/) — member selection and latency thresholds.
- [Read Preference Tag Sets](https://www.mongodb.com/docs/manual/core/read-preference-tags/) — prioritized tag lists.
- [Read Preference maxStalenessSeconds](https://www.mongodb.com/docs/manual/core/read-preference-staleness/) — lag measurement and minimum threshold.
- [Read Preference Use Cases](https://www.mongodb.com/docs/manual/core/read-preference-use-cases/) — choosing modes by workload.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — stale reads and causal consistency.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — read concern levels.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — write acknowledgment levels.
- [Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — `readPreference`, staleness, tags, and timeouts.
- [MongoDB Node.js Driver Documentation](https://www.mongodb.com/docs/drivers/node/current/) — driver configuration and sessions.
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — `ReadPreference` and collection handles.
