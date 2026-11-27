# Tag-Based Secondary Selection and Read-Scaling Purposes in a MongoDB Replica Set

In a retail system, a MongoDB Replica Set primary must handle order writes, inventory updates, and many critical queries. If an internal dashboard continuously scans data to build reports, the primary may have to share CPU, RAM, and I/O with heavy read jobs. Because a Replica Set has secondaries maintaining data copies, applications can **deliberately route certain read queries to secondaries** to offload the primary.

Yet "reading from secondaries" is not a complete design on its own. When multiple secondaries exist, you must answer:

- Which secondary is allowed to run reports, and which is dedicated to normal API reads?
- How do you configure preferring one region/zone while allowing fallback to another?
- If all reporting secondaries become unavailable, should the system **return an error** or **fall back to the primary**?
- How do you avoid reading data lagging too far behind the primary?
- Can tags select a secondary without altering write authority, elections, or consistency?

MongoDB provides two primary tools: **member tags** attached to the replica set config and **read preference with tag sets** on the client side. Combining them lets you describe each secondary's purpose and instruct the driver to choose from an **eligible group of members**, rather than manually targeting a single host. However, tags are not a strict load balancer, do not guarantee reading the latest data, and are not a security barrier.

This lesson belongs to the **Replica set** chapter of the *Database Engine Document MongoDB* module. Examples use **mongosh**, MongoDB Java Driver, and Node.js Driver. Specific fallback, staleness, latency window, and routing behaviors depend on driver/server versions, read preference mode, and topology; verify on your target environment before deploying. Commands modifying replica set configuration are **lab** examples only; never run them casually in production.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain primary, secondary, and replication lag roles in a replica set.
2. Attach **tags** to members and inspect config via `rs.conf()`.
3. Distinguish the five modes: `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, and `nearest`.
4. Use ordered **read preference tag sets** to prioritize secondary groups by purpose/region.
5. Distinguish **falling back to another secondary** from **falling back to the primary**.
6. Know when `maxStalenessSeconds` is needed and why it is not a guarantee that data is always within N seconds of fresh.
7. Understand the **latency window** and why `nearest` does not guarantee reading from a secondary.
8. Configure read preference at connection, database/collection, or per-operation level in Java/Node.js Drivers.
9. Distinguish read preference from **read concern**, causal consistency, write concern, and authorization.
10. Plan read scaling, monitor replication lag, server selection errors, and CPU/I/O load.
11. Recognize limitations involving hidden/delayed members, transactions, sharding, and failover.
12. Design tests verifying queries actually run on the intended node group.

## 2. Replica Set: Why Can Secondaries Serve Reads?

A replica set has multiple `mongod` processes maintaining the same dataset via replication. In a standard topology:

- **Primary** receives replica set write operations and serves default read queries.
- **Secondaries** replicate and apply operations from the oplog to synchronize over time.
- **Elections** can choose a new primary when the current primary is unavailable, depending on majority, priority, and member state.

~~~mermaid
flowchart TD
    App["Application"] --> W["Write"]
    App --> R["Read"]
    W --> P["Primary"]
    P --> O["Oplog / replication"]
    O --> S1["API Secondary"]
    O --> S2["Reporting Secondary"]
    R --> Q{"Read preference + tags"}
    Q -->|"Eligible candidates"| S1
    Q -->|"Eligible candidates"| S2
~~~

Core point: **replication is asynchronous**. A write succeeding on the primary may not appear immediately on a secondary. Thus:

~~~text
At time T:
Primary:   order-1001 already exists
Secondary: order-1001 may not yet be applied
~~~

If right after creating an order an API reads using read preference `secondary`, it may not yet see the new order. That is not necessarily a query bug or data loss; it can simply be **replication lag**.

### 2.1. A Secondary Is Not a "Free Read" Node

A secondary must:

- Receive and apply changes from the primary.
- Maintain its own indexes and data.
- Consume CPU, RAM/cache, disk, and network.
- Potentially participate in elections depending on configuration.

Sending thousands of heavy reports to a secondary can overload that secondary, increase replication lag, and impair recovery/failover capability. **Read scaling shifts and distributes cost; it does not eliminate cost.**

### 2.2. Read Offloading Differs from Write Scaling

Routing a read query from the primary to a secondary can reduce read load on the primary. Yet write operations still follow the replica set write path (normally to the primary). Adding secondaries **does not linearly scale write throughput**, because every member must maintain data and incurs replication overhead.

## 3. Member Tags: Describing Per-Node Attributes

MongoDB lets you configure a map of string `key: value` pairs on each replica set member. Example:

~~~javascript
{
  host: "mongo-report-1.example.internal:27017",
  tags: {
    purpose: "reporting",
    region: "hcm",
    zone: "az-b"
  }
}
~~~

Tags can describe:

| Tag | Illustrative Values | Convention Agreed by Ops Team |
|---|---|---|
| `purpose` | `app`, `reporting` | Dedicated to API reads or reporting |
| `region` | `hcm`, `hanoi` | Geographic region group of the node |
| `zone` | `az-a`, `az-b` | Availability zone |
| `tier` | `interactive`, `batch` | Suitable workload tier classification |
| `hardware` | `large-memory` | Machine spec description |

MongoDB does not inherently know that `purpose: "reporting"` means "only reporting may use this." It is an **application/operational convention**. Drivers merely match tags against the read preference you supply.

### 3.1. A Tag Is Neither a Hostname Nor an Access Control

When a node carries `purpose: "reporting"`:

- Drivers can select this node if read preference/tag sets match.
- The node **does not automatically block** other clients from reading if those clients hold privileges and use a different read preference.
- Tags do not cap connection count, CPU, or I/O.
- Tags do not encrypt or isolate data by tenant.
- Tags do not make a node a secondary; primary/secondary roles are governed by replica set/elections.

**Tags are metadata for server selection, not policy isolation.** True isolation requires access architecture, credentials, network controls, and additional workload management.

### 3.2. Key/Value Naming Must Be Consistent

Values like:

~~~text
purpose=reporting
purpose=Reporting
purpose=reports
~~~

must not be assumed equivalent. Drivers match exact tag pairs. Ops teams must standardize keys/values, document them, and check for drift when adding nodes.

## 4. Illustrative Topology for Practice

Suppose three data-bearing members:

| Member | Role at Illustration Time | Tags | Purpose |
|---|---|---|---|
| `mongo-a:27017` | Primary | `{region:"hcm",zone:"az-a",purpose:"app"}` | Writes and reads needing fresh data |
| `mongo-b:27017` | Secondary | `{region:"hcm",zone:"az-b",purpose:"app"}` | Lag-tolerant API reads |
| `mongo-c:27017` | Secondary | `{region:"hanoi",zone:"az-c",purpose:"reporting"}` | Reporting/batch |

This is a **point-in-time snapshot**, not an immutable role assignment: during an election, an eligible secondary can become primary. Tags are metadata bound to a member; **they do not migrate automatically with roles**.

~~~mermaid
flowchart LR
    API["Critical API"] -->|"primary"| A["mongo-a Primary"]
    Reader["Lag-tolerant read API"] -->|"secondary + purpose=app"| B["mongo-b Secondary"]
    BI["Reporting job"] -->|"secondary + purpose=reporting"| C["mongo-c Secondary"]
    A -.->|"Replication"| B
    A -.->|"Replication"| C
~~~

### 4.1. Why Account for Elections?

Suppose `mongo-c` is tagged `purpose: "reporting"` yet remains eligible for primary election. When an election shifts roles:

- Read preference `secondary` will **not** pick the new primary, even though its tags still match.
- If no secondary remains with `purpose: "reporting"`, strict reporting queries will fail to find a server.
- Queries using `nearest` with matching tags follow different rules because `nearest` considers the primary too.

To ensure a dedicated read-workload node **never becomes primary**, ops teams can consider `priority: 0` in the replica set design. Yet that affects electability and is not required to use tags; any priority/vote change must preserve election capability and topology availability.

## 5. Inspecting and Configuring Tags in `mongosh`

To view replica set configuration:

~~~javascript
rs.conf()
~~~

You may find:

~~~javascript
{
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo-a:27017",
      priority: 1,
      tags: { region: "hcm", zone: "az-a", purpose: "app" }
    },
    {
      _id: 1,
      host: "mongo-b:27017",
      priority: 1,
      tags: { region: "hcm", zone: "az-b", purpose: "app" }
    },
    {
      _id: 2,
      host: "mongo-c:27017",
      priority: 0,
      tags: { region: "hanoi", zone: "az-c", purpose: "reporting" }
    }
  ]
}
~~~

This illustrative snippet omits other config fields like version/votes/settings. Never copy this partial snippet and overwrite `rs.conf()` with an incomplete object.

### 5.1. Changing Tags in a Lab

On the primary of a **lab replica set**, with sufficient privileges:

~~~javascript
const cfg = rs.conf()

// Match by exact host to avoid editing the wrong member.
const member = cfg.members.find(
  m => m.host === "mongo-c:27017"
)

if (!member) {
  throw new Error("Member not found in configuration")
}

member.tags = {
  region: "hanoi",
  zone: "az-c",
  purpose: "reporting"
}

rs.reconfig(cfg)
~~~

Notes before applying:

- `rs.reconfig()` is a **configuration-changing operational action**; this example is for labs only.
- Use the real member's exact hostname/port, not a sample string.
- Verify config version, PRIMARY state, privileges, and replica set health.
- Do not simultaneously alter priorities/votes or add/remove members when the goal is solely updating tags.
- Config changes can affect server selection and in some cases trigger state changes/elections; follow production rollout/rollback procedures.

### 5.2. Verify After Changing

~~~javascript
const after = rs.conf()

after.members.forEach(m => {
  printjson({
    host: m.host,
    tags: m.tags,
    priority: m.priority,
    hidden: m.hidden
  })
})

rs.status()
~~~

`rs.conf()` confirms **configuration metadata**, while `rs.status()` inspects member/replication status. Seeing tags appear does not prove a query hit the right node; you must verify **client-side server selection**.

## 6. Read Preference: Who Is Permitted to Serve a Read Query?

MongoDB has five standard read preference modes:

| Mode | Selection Goal | Behavior to Note |
|---|---|---|
| `primary` | Primary only | Default for most clients; does not use tag sets to pick secondaries |
| `primaryPreferred` | Prefer primary | When primary is unavailable, can read a secondary under suitable conditions; risks stale data on fallback |
| `secondary` | Secondary only | Fits lag-tolerant reads; if no eligible secondary exists, waits/fails server selection rather than silently using primary |
| `secondaryPreferred` | Prefer secondary | Can fall back to primary if no usable secondary exists; easily shifts load onto primary unexpectedly |
| `nearest` | Member within driver latency window | Can select primary **or** secondary; not "nearest secondary" |

**There is no mode named "reporting."** Reporting is a tag you define; `secondary` is the secondary-reading mode; combine them to select the right node group.

### 6.1. `primary`

~~~javascript
// Conceptual client configuration:
readPreference = "primary"
~~~

Useful when:

- Immediately reading after a write to observe the freshest state visible via primary under chosen consistency.
- Operations depending on write order, orders, inventory, transaction confirmations.
- Transactions requiring primary read preference per MongoDB limits.

Read preference `primary` does not permit using tag sets to select secondaries. If a client config attempts to pair `primary` with read preference tags, the driver/config validator may reject it.

### 6.2. `secondary`

~~~javascript
readPreference = "secondary"
~~~

Considers only eligible secondaries matching tags, staleness, and latency. Ideal when you want to **protect the primary from auxiliary read workloads**, even if reports must temporarily fail when no secondary is available.

### 6.3. `secondaryPreferred`

~~~javascript
readPreference = "secondaryPreferred"
~~~

This favors availability, yet **provides no hard isolation**. When no eligible secondary exists, this mode falls back to reading from the primary. If heavy dashboards use this mode, a secondary outage can dump all reporting load onto the primary right when the system is resource-constrained.

### 6.4. `primaryPreferred`

Selects primary when a suitable primary exists; tag sets apply when falling back to a secondary. While primary is available, a "reporting" tag does not turn this mode into reading a reporting secondary.

### 6.5. `nearest`

The driver picks members based on eligibility, tag sets, and latency estimates. **`nearest` can include the primary**, so never use this mode if the requirement is "reports must never touch the primary." Physical geographic distance is not used directly by drivers like a GIS engine; drivers use network latency measured during topology monitoring.

## 7. Tag Sets: Selecting Member Groups with Ordered Conditions

A **tag set** is a collection of key/value pairs that must match **simultaneously** on a single member. Example:

~~~javascript
{ purpose: "reporting", region: "hanoi" }
~~~

means the member must carry **both** `purpose = reporting` **and** `region = hanoi`.

A **tag set list** specifies selection options in **priority order**:

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

The system checks the first tag set for eligible nodes; if no member satisfies that set, it tries the next set. **Do not** read these two objects as an AND across sets. AND applies **within one tag set**, whereas sets in the list are **ordered fallback tiers**.

~~~mermaid
flowchart TD
    R["Read with mode secondary"] --> First{"Any secondary with reporting + hanoi?"}
    First -->|"Yes"| A["Select from reporting/hanoi group"]
    First -->|"No"| Second{"Any secondary with reporting?"}
    Second -->|"Yes"| B["Select from reporting group in any region"]
    Second -->|"No"| E["No suitable server"]
~~~

### 7.1. Strict Priority for Reporting

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

With mode `secondary`, both tiers keep `purpose: "reporting"`. If no reporting secondary exists, the query will not silently fall back to an API secondary or primary. This acts as **fail-closed server selection** for reporting workloads.

### 7.2. Fallback to Any Secondary

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" },
  {}
]
~~~

An empty tag set `{}` means **no additional tag constraint** at the final fallback tier. It allows non-reporting secondaries to be selected if neither prior tier yields an eligible member.

**Do not add `{}` out of habit.** For heavy reporting, the final fallback can hit API secondaries and spike replication lag or latency on critical queries.

### 7.3. Single-Tag-Set List

~~~javascript
[{ purpose: "app" }]
~~~

restricts selection to members carrying the `app` tag. With `secondary`, it can select eligible `app` secondaries, and will **not** pick the primary just because the primary also carries `purpose: "app"`.

### 7.4. No Tags

If a read preference mode is set with **no tag constraint**, the driver considers all members allowed by that mode after applying health/staleness/latency filters. This differs from specifying a tag set containing a non-existent key.

### 7.5. Separate Mode Fallback from Tag Set Fallback

Two selection steps:

1. **Mode** governs which member roles may be considered and when primary/secondary fallback happens.
2. **Tag set list** prioritizes members matching metadata within that eligible group.

For instance, `secondaryPreferred` can fall back to primary when no matching secondary remains. Never assume `[{purpose:"reporting"}]` creates an absolute promise that queries in that mode **never hit the primary**. To isolate reporting load from the primary with explicit failure when capacity is missing, use mode `secondary` with strict tag sets plus proper timeout/error handling.

## 8. Designing Tag Taxonomy by Offloading Purpose

A system can classify reads:

| Workload | Data Requirement | Candidate Member Selection |
|---|---|---|
| Payment confirmation, balance, newly updated inventory | Needs high consistency | `primary` and appropriate read/write concern |
| Infrequently changing catalog pages | Tolerates small lag | `secondary` or `secondaryPreferred` with `app` tag |
| Hourly BI dashboards | Tolerates bounded lag | `secondary` + `reporting` tag |
| Scheduled large data exports | Can slow/pause if secondary busy | `secondary` + strict `batch`/`reporting` tag |
| Non-critical informational search | Optimize latency where consistency allows | `nearest` or other suitable mode; watch primary load |
| Reads inside multi-document transactions | Per transaction requirements | `primary` |

### 8.1. Tags by Role or by Region?

Two common patterns:

**By role:**

~~~javascript
{ purpose: "reporting" }
{ purpose: "app" }
~~~

**By role + location:**

~~~javascript
{ purpose: "reporting", region: "hanoi" }
{ purpose: "reporting", region: "hcm" }
~~~

`purpose` tags keep batch queries off application-facing nodes. `region` tags restrict selection by data center/region and affect latency/network egress. Yet never make region a hard constraint if node counts per region lack fault tolerance.

### 8.2. Pick Stable Tag Names

Avoid duplicate meanings:

~~~text
purpose=reports
role=reporting
workload=analytics
type=bi
~~~

If different app teams use different keys for the same node role, configuration changes and operations become painful. Maintain one standard convention table:

~~~text
purpose: app | reporting | batch
region: hcm | hanoi
zone: az-a | az-b | az-c
~~~

And document clearly:

- Which nodes serve which jobs.
- Which workloads are allowed to fall back.
- Which nodes can participate in elections.
- Who is authorized to edit tags.
- What to verify after `reconfig` to prevent config drift.

## 9. Example: Preferring Reports in One Region, Falling Back Within Reporting

Topology:

~~~text
mongo-a: PRIMARY             purpose=app, region=hcm
mongo-b: SECONDARY           purpose=app, region=hcm
mongo-c: SECONDARY           purpose=reporting, region=hanoi
mongo-d: SECONDARY           purpose=reporting, region=hcm
~~~

The analytics team prefers hanoi, yet can still read hcm if mongo-c fails:

~~~javascript
const reportingTagSets = [
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" }
]
~~~

If `mongo-c` is healthy and eligible, the first tier wins. If `mongo-c` is unavailable/stale per active filters, `mongo-d` can be chosen. Without a `{}` tier, it never spills onto secondary `mongo-b`.

### 9.1. Requirement: "Never Touch Primary"

Use:

~~~text
mode = secondary
tagSets = [
  {purpose:reporting, region:hanoi},
  {purpose:reporting}
]
~~~

If no suitable reporting secondary exists, the driver eventually raises a **server selection timeout** error. This can be the right behavior: auxiliary reporting pauses temporarily rather than pushing hundreds of heavy queries onto the transactional primary.

### 9.2. Requirement: "Prioritize Availability"

Using `secondaryPreferred` can fit if the API permits falling back to primary when secondaries are unavailable. In return, you must **know the load impact on primary upfront** and bound concurrency/query time. Never pick `secondaryPreferred` merely because it sounds "more redundant"; tie it to SLOs and overload policies.

### 9.3. Requirement: "Fall Back to App Secondary, Never Primary"

Combine `secondary` with:

~~~javascript
[
  { purpose: "reporting" },
  { purpose: "app" }
]
~~~

Allows failing over to `app` secondaries when reporting secondaries are missing. This can still degrade API read latency. If `app` secondaries must be protected, drop this fallback tier and have batch jobs retry with backoff when no reporting node exists.

## 10. `maxStalenessSeconds`: Excluding Excessively Lagging Secondaries

Read preference can set `maxStalenessSeconds` to **exclude secondaries estimated to be too stale** relative to reference replication progress. Example:

~~~text
mode: secondary
tags: purpose=reporting
maxStalenessSeconds: 120
~~~

Intent: select only eligible secondaries whose **estimated** staleness falls within tolerance. In modern MongoDB, the minimum supported value for `maxStalenessSeconds` is typically **90 seconds** (also constrained by heartbeat interval requirements); never set 5 or 10 seconds arbitrarily expecting MongoDB to accept it.

### 10.1. Staleness Is Not an Absolute Per-Read SLA

Do not interpret:

> "`maxStalenessSeconds = 120` means every result is always fresh within 120 seconds."

It is a **server selection** filter based on estimated replication lag, not a guarantee on each document's last-modified timestamp or a barrier waiting for all preceding writes.

Factors that can skew results:

- Heartbeat/monitoring latency.
- Timing of when the node fetches/applies the oplog.
- Write frequency and staleness estimation mechanics.
- Timing between query dispatch and server evaluation.
- I/O/CPU load on the secondary.

If business logic demands "must see data immediately after writing," **never rely on `maxStalenessSeconds` alone**. Consider reading from primary, or causal consistency with sessions and appropriate read/write concerns.

### 10.2. Secondary Staleness and Failover

If all reporting secondaries exceed the staleness threshold:

- Mode `secondary` finds no valid member and waits until server selection timeout.
- Mode `secondaryPreferred` falls back to primary per mode fallback rules.

Thus, with the exact same tag set, **different modes react very differently to lag**.

### 10.3. When Not to Set Too Tight a Threshold

An end-of-day reporting job may tolerate a few minutes of lag yet must finish before the delivery deadline. Too tight a threshold can fail queries while a replica is catching up even though the data is usable enough. Pick staleness by **business requirements**, not the smallest number thinking "smaller is better."

## 11. Latency Window: Why You Cannot Intuitively Pin "Nearest Node"

MongoDB drivers execute **server selection**:

1. Identify members per read preference mode.
2. Apply tags, max staleness, and eligibility criteria.
3. Use observed **round-trip time** to determine members inside the latency window.
4. Pick a member from the remaining candidate pool per driver mechanics.

The `localThresholdMS` parameter (commonly defaulting to **15 ms**) defines the latency window: servers whose RTT does not exceed the lowest RTT in the pool plus the threshold are all eligible candidates.

### 11.1. Example

~~~text
Reporting secondary A: RTT 12 ms
Reporting secondary B: RTT 20 ms
Reporting secondary C: RTT 35 ms

localThresholdMS = 15 ms
=> Latency window roughly 12..27 ms
=> A and B can be considered; C is normally excluded
~~~

Numbers are illustrative, not benchmark measurements. Drivers update measurements over time, and the candidate pool shifts as load or network conditions change.

### 11.2. Do Not Assume a 50/50 Load Split

A tag set matching two eligible secondaries **does not guarantee** each node receives 50% of queries. Selection is also influenced by:

- Each driver process's independent server selection.
- Available connections/pools and topology events.
- Latency window and server health.
- Number of client instances.
- Retries when a node becomes ineligible.
- Varying query duration/weight.

To distribute load with **exact ratios or quotas**, build workload routing, queues, dedicated client pools, or schedulers—not just tags.

### 11.3. `nearest` Does Not Mean Offloading Primary

`nearest` evaluates both primary and eligible secondaries where applicable. If the primary has good RTT, the driver can select the primary. To strictly read secondaries, use mode `secondary`.

## 12. Java Driver: Read Preference for Reporting

A Java application should scope read preference per **repository/collection or query**, rather than routing an entire service's queries to secondaries. Example illustrating the MongoDB Java Sync Driver API:

~~~java
import com.mongodb.ReadPreference;
import com.mongodb.Tag;
import com.mongodb.TagSet;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.List;

public class ReportingReadExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/" +
            "?replicaSet=rs0";

        // Each TagSet: all pairs must match on a single member.
        TagSet preferredRegion = new TagSet(List.of(
            new Tag("purpose", "reporting"),
            new Tag("region", "hanoi")
        ));
        TagSet anyReporting = new TagSet(List.of(
            new Tag("purpose", "reporting")
        ));

        ReadPreference reportingReadPreference =
            ReadPreference.secondary(
                List.of(preferredRegion, anyReporting)
            );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> collection =
                client.getDatabase("shop").getCollection("orders");

            // Only this collection view uses reporting secondaries.
            MongoCollection<Document> reportingOrders =
                collection.withReadPreference(reportingReadPreference);

            try (MongoCursor<Document> cursor = reportingOrders
                    .find(Filters.eq("status", "PAID"))
                    .limit(100)
                    .iterator()) {
                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

### 12.1. What the Java Example Demonstrates

- The client connects to a **replica set URI** with seed hosts; the driver discovers topology.
- `ReadPreference.secondary(...)` prevents reports from silently hitting the primary.
- `preferredRegion` prioritizes reporting secondaries in hanoi.
- If none exist, `anyReporting` allows reporting secondaries in other regions.
- `collection.withReadPreference(...)` returns a scoped view/config for reads without altering how other collections read.

If no eligible reporting secondary exists, the query waits up to server selection timeout and errors. Catch, classify, and apply bounded job retries at the application layer.

### 12.2. Do Not Apply This Pattern to Business Transactions

Example:

~~~java
// Principle illustration only: repositories handling inventory/new orders
// should use primary/read concern appropriate to business logic.
MongoCollection<Document> writeCriticalOrders =
    collection.withReadPreference(ReadPreference.primary());
~~~

Read preference controls **reads**; writes are never "pushed to a secondary" by setting `secondary`. Multi-document transactions must adhere to MongoDB's primary read preference requirements.

### 12.3. Companion Parameters to Design

Real services also need:

- Server selection timeout aligned with SLOs.
- Socket/connect timeouts and connection pools.
- `maxTimeMS` on heavy queries to prevent unbounded resource retention.
- Read concern matching required consistency.
- Tracing/logging showing which member served the read.
- Concurrency limits on reporting jobs.

Never turn these into a blanket default across all workloads without measuring impact.

## 13. Node.js Driver: Setting Read Preference Per Query

~~~javascript
import { MongoClient, ReadPreference } from "mongodb";

const uri =
  "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/" +
  "?replicaSet=rs0";

const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

try {
  const reportingPref = new ReadPreference(
    "secondary",
    [
      { purpose: "reporting", region: "hanoi" },
      { purpose: "reporting" }
    ],
    { maxStalenessSeconds: 120 }
  );

  const docs = await client
    .db("shop")
    .collection("orders")
    .find(
      { status: "PAID" },
      {
        readPreference: reportingPref,
        maxTimeMS: 3000
      }
    )
    .limit(100)
    .toArray();

  console.log("Reporting rows:", docs.length);
} finally {
  await client.close();
}
~~~

This illustrates a **freshness-tolerant read**. `maxStalenessSeconds: 120` is a member selection constraint, not a query execution time limit. `maxTimeMS: 3000` governs server-side execution budget; `serverSelectionTimeoutMS` is how long the driver waits to pick an eligible server.

### 13.1. Distinguish Three Timeouts

| Parameter | What It Bounds |
|---|---|
| `serverSelectionTimeoutMS` | Time driver waits to find an eligible member |
| `maxTimeMS` | Server-side query execution budget per supported semantics |
| `socketTimeoutMS` and network timeouts | Socket/operation I/O wait per driver |

Do not use `maxTimeMS` to "fix" missing suitable secondaries; the query may never even be dispatched to a server. Similarly, raising server selection timeout never makes a secondary missing the required tag eligible.

### 13.2. Observing the Executing Member

In the Node.js Driver, enable **command monitoring** on the client and listen to command events, capturing the server address from driver metadata. Use this in test environments to verify read commands truly run on `purpose=reporting` nodes.

Never log full command bodies if they contain PII/credentials; log only request ID, operation, server address, and timing after checking security policy.

## 14. MongoDB URI: Configuring Read Preference and Tag Sets

A connection string can specify mode and tag sets:

~~~text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rs0
  &readPreference=secondary
  &readPreferenceTags=purpose:reporting,region:hanoi
  &readPreferenceTags=purpose:reporting
  &maxStalenessSeconds=120
~~~

This is **wrapped across lines for readability**. In real configurations, use **one continuous URI** with no whitespace/line breaks; percent-encode special characters per URI rules. Repeating `readPreferenceTags` expresses **multiple ordered tag sets**, distinct from combining all pairs into one single tag set.

### 14.1. When to Use URI vs. Per-Operation?

**URI-level** fits a client/worker dedicated exclusively to reporting. For example, a batch service executing no write-critical reads can use a dedicated connection string with `readPreference=secondary`.

**Per-operation/per-collection** fits when one service houses both critical primary-reading APIs and secondary-capable dashboards.

Avoid a global `secondaryPreferred` connection string across all repositories: it can accidentally route reads needing latest state to secondaries when the application fails to specify consistency explicitly.

### 14.2. Empty Fallback Tag in URI

A `{}` fallback tier can be expressed as an empty tag set parameter per driver-supported URI syntax, yet **never add an empty fallback merely so queries "always run."** It widens eligibility to nodes outside the workload tag group, potentially defeating read isolation.

## 15. Hands-On `mongosh` with Read Preference

In a `mongosh` session connected to the replica set:

~~~javascript
// Inspect configuration first. Ensure a secondary carries purpose=reporting.
rs.conf()

// Set mode and tag sets for the shell session in the lab.
db.getMongo().setReadPref(
  "secondary",
  [
    { purpose: "reporting", region: "hanoi" },
    { purpose: "reporting" }
  ]
)

use shop

db.orders.find(
  { status: "PAID" },
  { _id: 1, createdAt: 1, amount: 1 }
).limit(10)

// Restore default read preference to primary after testing.
db.getMongo().setReadPref("primary")
~~~

Notes:

- `mongosh` syntax and options can vary across versions; use a URI to test consistently with driver behavior.
- If only one reporting secondary exists in hanoi, selection is clearer, yet still verify which node executed the read.
- A query can succeed without `find()` output showing **which node** served it. Driver/server observability is needed.
- Running the shell in direct-connection mode to one member defeats testing **driver server selection in replica set topology**; test read preference using a proper replica set connection.

### 15.1. Testing Unmatched Tag Sets

~~~javascript
db.getMongo().setReadPref(
  "secondary",
  [{ purpose: "nonexistent-workload" }]
)

db.orders.findOne({})
~~~

In a replica set where no secondary carries this tag, the query fails with a server selection timeout. This is a useful test proving **no automatic fallback to primary occurs** under mode `secondary`.

Afterward restore:

~~~javascript
db.getMongo().setReadPref("primary")
~~~

### 15.2. One Read Does Not Prove Load Distribution

If one test query happened to run on mongo-c, you cannot conclude the driver always selects mongo-c or distributes load evenly. Observe many requests across multiple client instances, longer periods, node failures, and latency changes.

## 16. Read Preference Differs from Read Concern

Two commonly confused concepts:

- **Read preference:** *which member to read from?*
- **Read concern:** *what commitment/consistency level of data may be observed?*

Example:

~~~text
readPreference = secondary
readConcern = majority
~~~

instructs selecting a secondary per mode/tags and reading data matching majority read concern semantics. It does **not** mean the secondary has applied all of the primary's latest writes.

### 16.1. Read Concern `local`

`local` reads data reflecting the member's local state, and under applicable conditions non-majority-committed data can roll back. It does not guarantee seeing a write just executed on the primary.

### 16.2. Read Concern `majority`

`majority` restricts reads to majority-acknowledged/committed data per MongoDB semantics, avoiding reads of data that could roll back. Yet a secondary may **lag behind**; results can be valid yet still stale.

### 16.3. `linearizable` Is Not a Secondary-Read Solution

Read concern `linearizable` is designed for primary reads under specific constraints, not a way to force secondaries to return the freshest data. If linearizable semantics are needed, never pair it to justify secondary read preference.

### 16.4. Summary Table

| Configuration | Which Node Is Selected? | Freshness / Consistency |
|---|---|---|
| `primary + local` | Primary | Sees primary state per local semantics; no default majority durability |
| `primary + majority` | Primary | Reads majority-committed data per read concern semantics; still inspect API consistency |
| `secondary + local` | Secondary | Can be stale; some data could roll back depending on commit state |
| `secondary + majority` | Secondary | Majority-committed yet **not guaranteed latest** |
| `secondary + causal session` | Eligible secondary | Can satisfy causal guarantees when session/read/write concerns are configured properly; may wait |

**No single configuration field** makes every secondary read as strong as a transactional read on the primary.

## 17. Causal Consistency and Read-Your-Writes

Scenario:

1. Client creates an order on the primary.
2. Immediately afterward, wants to display the order on a screen backed by a secondary.

With only `readPreference=secondary`, the follow-up query may **not yet see** the write. One option is a **causally consistent session** with appropriate write and read concerns (typically majority for the relevant guarantees), helping driver/server preserve causal ordering within the same session where supported.

### 17.1. Neither Infinite Nor Free

If the secondary has not yet reached the causal timestamp needed, the operation must **wait**. Under heavy lag, latency climbs or queries time out. Causal consistency never replaces capacity and replication health.

### 17.2. When Is Simply Reading Primary Better?

For the flow:

~~~text
POST /orders
GET /orders/{id} immediately
~~~

reading primary on the immediate post-write GET is usually simpler if the goal is **displaying the newly created record** with low latency and accuracy. Catalog screens, reports, or dashboards not needing read-after-write can use secondaries.

### 17.3. Sessions Do Not Automatically Propagate Across HTTP Requests

Do not assume a subsequent HTTP request automatically inherits the same logical session/causal context. If the application needs causal linkage, explicitly propagate context and manage sessions properly. For independent APIs, secondary read preference normally yields eventual consistency unless extra mechanisms are used.

## 18. Hidden and Delayed Members: Do Not Treat as Normal Reporting Secondaries

A replica set member can be:

- A normal secondary, selectable by drivers via read preference.
- A **hidden secondary**, invisible to normal application read selection.
- A **delayed secondary**, intentionally applying replication late and normally configured hidden.
- A `priority: 0` member, ineligible for primary yet **not automatically hidden**.

### 18.1. Never Use Tags to "Unlock" a Hidden Member

Even if a hidden member carries tags:

~~~javascript
tags: { purpose: "backup" }
~~~

drivers never pick a hidden member for normal read preferences merely because tags match. Hidden members normally receive reads only when clients **connect directly** to that member in authorized administrative contexts.

Thus, configuring:

~~~text
readPreference=secondary
tagSets=[{purpose:"backup"}]
~~~

does not turn a hidden backup node into a standard reporting secondary. If you want a node to serve automated topology-driven reporting, configure it as a **selectable secondary** (not hidden), and consider `priority:0` if you want to prevent it from becoming primary.

### 18.2. Delayed Secondaries Are Not for Real-Time Reporting

A delayed member intentionally holds data behind the primary. Routing queries there to "offload" returns stale results by design, corrupting business decisions. It serves data-protection/recovery purposes, not API read scaling.

### 18.3. `priority:0` Differs from `hidden:true`

| Option | Primary Effect |
|---|---|
| `priority: 0` | Member cannot be elected primary |
| `hidden: true` | Member is not chosen by drivers under normal topology read preference |
| Tags | Describe server selection criteria |

Do not conflate these three concepts. A secondary with `priority:0` and `hidden:false` can still be selected for reads under matching modes/tags.

## 19. Failover: What Happens When a Node Disappears?

Suppose reporting reads from `mongo-c` via:

~~~text
readPreference = secondary
tagSets = [{purpose:reporting}]
~~~

When `mongo-c` disconnects:

1. The driver updates topology based on heartbeats/monitoring.
2. If another eligible reporting secondary exists, it can switch to that node.
3. If none exists, queries wait until server selection timeout and fail.
4. It **never** falls back to primary because mode `secondary` forbids it.

### 19.1. The `secondaryPreferred` Case

With `secondaryPreferred`, when no eligible secondary remains, the mode falls back to primary. This raises availability yet risks **unexpected overload** if the lost node was a reporting node and the entire batch workload lands on the primary.

### 19.2. When the Primary Changes

If a reporting secondary is elected primary, it is no longer a candidate for `secondary`. Tags stay attached to the member, yet the `secondary` mode excludes the primary role. Never design around the assumption "tagged reporting means permanently a secondary."

To dedicate a member strictly to reporting, design election priority, electable member count, votes, majority, and failure domains upfront.

### 19.3. Bounded Retries

When no matching member exists, a batch/reporting job can:

- Retry with backoff + jitter.
- Cap concurrent jobs.
- Enforce deadlines aligned with reporting schedules.
- Alert when no reporting secondary is available or lag exceeds thresholds.
- Cancel/pause for operator intervention when strict isolation criteria can no longer be met.

Avoid self-healing hacks that **switch all batch read preferences to primary** unchecked: that can turn a reporting outage into a transactional incident.

## 20. Monitoring Replication Lag and Secondary Health

On a replica set, inspect:

~~~javascript
rs.status()
~~~

or the corresponding admin command, if authorized:

~~~javascript
db.adminCommand({ replSetGetStatus: 1 })
~~~

Fields such as state, optime/applied times, heartbeats, and member status help observe replication, though you must interpret them per server version and never look at a single timestamp difference assuming every query has that exact staleness.

### 20.1. Metrics to Monitor

| Metric | Why It Matters |
|---|---|
| Replication lag per secondary | High lag hurts freshness and `maxStaleness` eligibility |
| CPU, disk I/O, cache pressure | Reports can contend with replication apply |
| Network bandwidth/RTT | Affects server selection and latency |
| Query p95/p99 per node | Detects overloaded reporting secondaries |
| Connections/active operations | Finds long-running batches/queries hogging resources |
| Server selection timeouts | Missing eligible members or unstable topology |
| Tag drift/member config | Clients may mis-exclude nodes if tags drift |
| Election/primary changes | Can change reporting node eligibility |
| Oplog window/replication backlog | Slow secondaries risk losing catch-up capability |
| Read request rate by workload | Confirms read offloading off primary actually occurs |

### 20.2. "Routed to Secondary" Does Not Prove Improvement

Suppose primary CPU drops 20%, yet the reporting secondary's CPU spikes to 99% and replication lag jumps from seconds to minutes. You may simply have traded one bottleneck for another. Measure **end-to-end**: throughput, latency, staleness, lag, retries/errors, networking, and resilience.

### 20.3. Measure During Real Workload Windows

A secondary may sit idle in the morning yet saturate under ETL batches at night. Tags/latency express only **eligibility and selection**, never guaranteed spare capacity. Combine scheduling, concurrency limits, and query time budgets.

## 21. Indexes and Query Performance on Secondaries

Read preference never fixes missing indexes. If a report runs:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(100)
~~~

a matching compound index remains essential:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_tenant_status_created" }
)
~~~

In a replica set, index structures must be maintained across members. Adding indexes increases storage footprint and write/replication-apply cost; weigh this against reporting query gains.

### 21.1. Indexes Serve Queries; Tags Serve Routing

| Tool | Question It Solves |
|---|---|
| `readPreference=secondary` | Which member role may serve reads? |
| Tag sets | Which purpose/region group of secondaries? |
| `maxStalenessSeconds` | Is the member's estimated staleness within bounds? |
| `localThresholdMS` | Is the member inside the latency window? |
| Indexes | Can the query filter/sort efficiently on that member's data? |
| Read concern | What commit level of data may be observed? |

**Tags do not replace indexes**, and indexes do not route queries off the primary.

### 21.2. Explain Does Not Always Confirm Which Node Was Selected

`explain("executionStats")` is great for inspecting `IXSCAN`, `COLLSCAN`, `SORT`, `totalKeysExamined`, and `totalDocsExamined`. However, **explain is not complete proof of client-side server selection**. Pair it with driver command monitoring or node logs/metrics to confirm queries actually hit the intended member.

### 21.3. Reporting Reads Can Still Impact Oplog Apply Time

If a report triggers a huge collection scan, it contends for CPU/cache/disk with the replication applier. An overloaded secondary applies the oplog slowly, accumulates lag, and gets disqualified by `maxStalenessSeconds`. This creates a vicious cycle: the more reports pile onto one node, the more it lags and drops out of eligibility.

## 22. Read-Scaling Strategy by API Group

A practical implementation builds **separate client/query policies** rather than flipping a global read preference unconditionally:

~~~mermaid
flowchart LR
    UI["Users"] --> API["Backend"]
    API --> Critical["Order / inventory repository"]
    API --> Catalog["Catalog repository"]
    API --> Reports["Reporting service"]
    Critical -->|"primary"| P["Primary"]
    Catalog -->|"secondary / app tag"| S1["App Secondary"]
    Reports -->|"secondary / reporting tag"| S2["Reporting Secondary"]
    P -.->|"Replication"| S1
    P -.->|"Replication"| S2
~~~

### 22.1. Transactional Repositories

Set read preference `primary` to avoid surprises in read-after-write flows. For transactional workflows, use matching read/write concerns.

### 22.2. Catalog Repositories

If a few seconds of lag does not break business logic, use `secondary` or `secondaryPreferred` depending on availability contracts. Tag `purpose:app` avoids reporting nodes.

### 22.3. Reporting Services

Set `secondary` with `purpose:reporting` so it **never falls back to primary**, cap concurrent jobs, and enforce a retry budget. When stale data is acceptable for reports, choose a realistic max staleness; never pick a threshold tighter than replication can actually sustain.

### 22.4. Long-Running Exports/Batches

Use a dedicated reporting secondary with `maxTimeMS`, scheduling, batch size limits, and run windows. If a batch needs a consistent logical snapshot across time, design cutoff/snapshot logic or materialized datasets; read preference `secondary` **does not hold a frozen snapshot across a long-running job**.

### 22.5. Avoid Indirectly Queuing Load on Primary

An overloaded secondary causing `secondaryPreferred` batches to fall back onto primary can raise primary latency and trigger retries in critical APIs. Design clear **load budgets**: auxiliary jobs should fail cleanly rather than competing for resources with core transactions.

## 23. Tag-Based Selection Is Not Percentage Load Balancing

Given two reporting secondaries:

~~~text
mongo-c: purpose=reporting, RTT≈10ms, CPU=80%
mongo-d: purpose=reporting, RTT≈25ms, CPU=20%
~~~

If the latency window is narrow and mongo-c consistently has lower RTT, drivers may keep picking mongo-c despite its high CPU. Tags carry no signal saying "pick this node because CPU is lower."

If you need capacity-aware distribution:

- Partition batch queues explicitly across nodes/workloads.
- Use dedicated client pools or separate deployments for critical reports.
- Factor in latency windows, topology, client placement, and performance targets.
- Monitor lag/capacity and throttle concurrency under overload.
- Avoid embedding hostnames into business logic when MongoDB drivers manage topology better; reserve direct connections for special operational cases.

### 23.1. Distinguish Tag Preference from Data Locality

A `region:hanoi` tag is operator-assigned metadata. Drivers do not verify where hardware physically resides or legal data residency compliance. Data residency, compliance, or network isolation requirements need real infrastructure and deployment controls.

### 23.2. Tag Preference Does Not Make a Secondary Faster

If a secondary is slow due to missing indexes or networking, tag matching still merely answers "node is eligible." Lowering latency requires tuning queries, indexes, connection pools, caches, hardware, and client placement.

## 24. Sharded Clusters: Every Shard Has Its Own Replica Set

In a sharded cluster, each shard is typically a replica set. Read preferences/tag sets affect member selection on **every involved shard**. Things to verify:

- Which shards actually hold data for the query?
- Does every shard have a secondary carrying `purpose:reporting`?
- Does any shard only have `app` secondaries, leaving reporting queries without a match?
- Are staleness/latency uniform across shards?
- Does the query scatter-gather across many shards and merge results?
- Does load distribution create a hot shard?

### 24.1. Never Confuse Tags with Shard Keys

Tag-based read preference picks **which replica set member** serves reads. The shard key determines **how data is partitioned/routed across shards**. They solve two different problems. Giving every shard a reporting secondary does not turn a scatter-gather query lacking a shard key into a targeted query.

### 24.2. Cross-Shard Reads Observe Different Points in Time

With secondary read preferences across shards, each shard/member may sit at a slightly different replication timestamp. If a report demands a cross-shard consistent snapshot, review supported read concern/snapshot semantics and report design—do not rely solely on setting the same `maxStalenessSeconds`.

## 25. Failure Scenarios: What Does Each Policy Do?

| Scenario | `secondary` + strict reporting tag | `secondaryPreferred` + reporting tag | `nearest` untagged |
|---|---|---|---|
| Reporting secondary healthy | Selects eligible reporting secondary | Prefers reporting secondary | Can select any eligible member, including primary |
| Reporting secondary disconnects | No matching member → timeout/error if no other reporting node | Falls back to primary per fallback mode | Picks primary/other secondary by latency |
| Reporting secondary too stale | Excluded by `maxStaleness` if configured | Can fall back to primary | Depends on staleness config and eligibility |
| Primary overloaded | Never routes reporting to primary | Risks dumping reporting onto primary if secondaries missing | Primary can still be chosen |
| Expecting newly written data | No read-your-writes guarantee | No guarantee when reading secondaries | No guarantee because secondaries may be picked |
| Must strictly avoid primary | Suitable | Unsuitable | Unsuitable |

This table is a **policy guide**, not a substitute for testing driver/version behavior against your actual topology.

### 25.1. Scenario 1: "Reports Should Be Delayed Rather Than Slowing the Primary"

Choose mode `secondary`, tag sets restricted to reporting, with no `{}`. When secondaries are unavailable, jobs wait/retry cleanly and alert. This is **failure isolation via server selection policy**, not hard CPU/network isolation.

### 25.2. Scenario 2: "Feeds Must Stay Up Even If Secondaries Die"

Choose `secondaryPreferred` when the app **accepts** fallback load on the primary with safeguards. If the feed must show writes immediately after creation, read primary on that specific endpoint.

### 25.3. Scenario 3: "Read Closest to the Client"

`nearest` can fit when reading from either primary or secondary is acceptable, provided you understand latency windows; if the real requirement is secondary-only, use `secondary` with region tags rather than assuming `nearest` avoids the primary.

### 25.4. Scenario 4: "Zone B Secondaries Only"

Strict tag set:

~~~javascript
[{ zone: "az-b" }]
~~~

If zone B nodes are unhealthy or no secondary remains there, queries fail. To allow falling back to another zone, use multiple ordered tag sets.

## 26. A Test Lab Without Assuming an Existing Production Cluster

Prerequisites: a lab replica set with at least three healthy data-bearing members, including two secondaries. Replace sample hostnames with actual lab hostnames. Never try building a topology by running `rs.initiate()` on an already running production cluster.

### 26.1. Prepare Sample Schema and Index

On the lab primary:

~~~javascript
use read_scaling_lab

db.orders.insertMany([
  {
    _id: "o-001", tenantId: "t-01", status: "PAID",
    amount: NumberDecimal("150000"),
    createdAt: ISODate("2026-08-01T08:00:00Z")
  },
  {
    _id: "o-002", tenantId: "t-01", status: "CREATED",
    amount: NumberDecimal("300000"),
    createdAt: ISODate("2026-08-02T09:00:00Z")
  },
  {
    _id: "o-003", tenantId: "t-02", status: "PAID",
    amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-08-03T10:00:00Z")
  },
  {
    _id: "o-004", tenantId: "t-01", status: "PAID",
    amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-08-04T11:00:00Z")
  },
  {
    _id: "o-005", tenantId: "t-02", status: "PAID",
    amount: NumberDecimal("250000"),
    createdAt: ISODate("2026-08-05T12:00:00Z")
  }
])

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
)
~~~

Insert only into an empty lab database; re-running with the same `_id` raises duplicate key errors. To repeat the exercise, use a fresh lab database.

### 26.2. Tag the Two Secondaries

Example plan:

~~~text
Primary: mongo-a, purpose=app
Secondary 1: mongo-b, purpose=app, region=hcm
Secondary 2: mongo-c, purpose=reporting, region=hanoi
~~~

Use `rs.conf()` to verify exact member hostnames before running `rs.reconfig()` in the lab. Do not alter priority/votes unnecessarily.

### 26.3. Run a Reporting Workload

~~~javascript
db.getMongo().setReadPref(
  "secondary",
  [{ purpose: "reporting" }]
)

use read_scaling_lab

db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      totalRevenue: { $sum: "$amount" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalRevenue: -1 } }
])

db.getMongo().setReadPref("primary")
~~~

Because this dataset is tiny, the lab focuses on **server selection**, not throughput benchmarking. Use command monitoring/logs to confirm which member executed the query. Only compare CPU/latency using representative data volumes and sufficient iterations.

### 26.4. Test Losing the Reporting Secondary

Only in a lab with operational permissions and recovery steps:

1. Verify `mongo-c` is the sole reporting secondary.
2. Temporarily make the node unavailable **following a safe test script**.
3. Query with mode `secondary` + strict reporting tag.
4. Observe the server selection timeout/error message.
5. Restore the node and wait for replication catch-up.
6. Compare with `secondaryPreferred` to see how fallback can hit the primary.

Never shut down a production replica set node merely for demonstration. In small labs, any node-stopping action must consider majority and elections.

### 26.5. Test Unmatched Tags

Instead of stopping a node, change the `purpose=reporting` tag to another value **in the lab**, then run the strict query. This tests how the driver behaves when no member matches the tag without simulating a network outage. Still avoid reconfigs in production.

### 26.6. Observe Lag

In the lab, issue writes on the primary and watch secondary replication state. Never claim "secondaries always see writes immediately after insert"; record read timestamps per node and compare with/without `maxStalenessSeconds` within supported bounds. **Tiny datasets and local networking can keep lag near 0**, which does not prove absolute consistency.

## 27. Exercises from Basic to Advanced

### Exercise 1 — Distinguish Roles

Given three members: primary A, secondary B, secondary C. Explain why read preference `secondary` never chooses A, even if A carries tag `purpose:reporting`.

### Exercise 2 — AND Within a Tag Set

Given:

~~~javascript
{ purpose: "reporting", region: "hanoi" }
~~~

Does a member carrying only `purpose:reporting` in region `hcm` match? Why?

### Exercise 3 — Ordered Fallback Across Tag Sets

~~~javascript
[
  { purpose: "reporting", region: "hanoi" },
  { purpose: "reporting" },
  {}
]
~~~

Explain the three fallback tiers and the risk `{}` poses to API secondary load.

### Exercise 4 — Never Fall Back to Primary

Design read preference for a large export job requiring: **read only from reporting secondaries; if none exist, stop the job and retry later**. Which mode and tag sets?

### Exercise 5 — Availability

A catalog API accepts reading from the primary when no secondary is available. Name an appropriate mode, and warn about fallback load.

### Exercise 6 — Nearest

If primary RTT is 5ms, secondary A RTT is 12ms, and secondary B RTT is 20ms, why might `nearest` pick the primary even though the goal was secondary reads?

### Exercise 7 — Staleness

A job must avoid secondaries with excessive estimated staleness. What can `maxStalenessSeconds: 120` help with, and what does it **not guarantee**?

### Exercise 8 — Read Concern

Compare:

~~~text
secondary + local
secondary + majority
primary + majority
~~~

Which configurations can read majority-committed data? Which still risk missing a write that just succeeded on the primary?

### Exercise 9 — Hidden Member

A hidden secondary carries `tags:{purpose:"backup"}`. Can `secondary` + backup tag let drivers select it automatically? What is the right understanding of hidden vs. direct connection?

### Exercise 10 — Priority 0

Can a `priority:0, hidden:false` secondary serve tag-based reads? How does `priority:0` differ from `hidden:true`?

### Exercise 11 — Index Optimization

A report filters `tenantId`, `status`, and sorts descending by date. Why does setting read preference `secondary` alone fail to eliminate `COLLSCAN`? Propose a compound index.

### Exercise 12 — Causal Consistency

A user just placed an order and sees the order "missing" on a secondary-backed page. Explain the cause and two suitable solutions.

### Exercise 13 — Failover

A reporting secondary gets elected primary. What happens to strict `secondary` tag-reporting clients if no other reporting secondary exists?

### Exercise 14 — Sharded Cluster

A sharded cluster has three shards, yet only two shards have a reporting secondary. What problems can arise for scatter-gather reports using strict reporting tags?

### Exercise 15 — Measure Offloading

Build a before/after metrics table:

| Metric | Before | After | Notes |
|---|---|---|---|
| Primary CPU | … | … | … |
| Reporting secondary CPU | … | … | … |
| Replication lag p95 | … | … | … |
| Query latency p95 | … | … | … |
| Server selection timeouts | … | … | … |
| Read operations per member | … | … | … |

Never fabricate "measured" numbers without collecting them on a real environment. The goal is recognizing the trade-off between offloading primary and keeping secondaries healthy.

### Exercise 16 — Design a Tag Taxonomy

Define a convention for three workloads—transactions, catalog API, scheduled reporting—in a two-region system. Propose tag sets and explain which fallback tiers must be omitted to protect the primary.

## 28. Answer Hints

**Exercise 1:** Mode `secondary` considers only eligible secondaries. Tags on the primary do not turn it into a secondary.

**Exercise 2:** Does not match. Pairs within **the same tag set** are required simultaneously.

**Exercise 3:** Prefers reporting/hanoi; then reporting in any region; finally any eligible secondary. `{}` widens scope to `app` secondaries, risking resource contention.

**Exercise 4:** Mode `secondary` with `[{purpose:"reporting"}]`; do not use `secondaryPreferred` and do not add `{}` fallback.

**Exercise 5:** `secondaryPreferred` can fit if the API tolerates primary fallback; cap queries/concurrency to prevent overload.

**Exercise 6:** `nearest` considers both primary and eligible secondaries. Primary RTT 5ms sits within the best latency window and can be selected.

**Exercise 7:** Excludes members estimated stale past the threshold; does not guarantee absolute freshness of every result or read-your-writes.

**Exercise 8:** `majority` governs commit level; `secondary + majority` may still lack the latest write. `primary + majority` suits high-consistency reads better, though API consistency contracts still matter.

**Exercise 9:** No. Hidden members do not participate in normal driver read selection; only direct connections can be used in supported operational cases.

**Exercise 10:** Yes, if healthy/eligible. `priority:0` prevents primary election, while `hidden:true` hides from topology-based read selection.

**Exercise 11:** Read preference picks the node; indexes govern how data is found on that node. Candidate: `{tenantId:1,status:1,createdAt:-1}`.

**Exercise 12:** Secondary has not applied the write from primary yet. Read primary for immediate post-write flows, or design a causally consistent session with suitable read/write concerns while tolerating waits.

**Exercise 13:** The reporting node became primary and is no longer selected by mode `secondary`; if no other reporting secondary exists, clients hit server selection timeouts.

**Exercise 14:** Part of the query fails to find an eligible reporting member on the shard missing the tag; align shard topologies/tags and test full routing.

**Exercise 15:** Do not watch primary CPU alone; if replication lag and reporting secondary CPU climb too high, the solution may fail cluster-wide SLOs.

**Exercise 16:** Transactions read primary; catalog uses `app` secondaries if lag-tolerant; reports use strict `reporting` secondaries. Add fallbacks only when load/availability models allow.

## 29. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Thinking tags move queries off primary automatically | Tags have no effect under `primary` mode | Configure read preference explicitly |
| Using `secondaryPreferred` to "forbid" primary | Fallback can still hit primary | Use `secondary` mode for strict offload |
| Using `nearest` thinking it reads only secondaries | `nearest` can pick primary | Use `secondary` + tags |
| Putting all tags in one object when wanting fallback | All pairs become simultaneously required | Use an ordered list of multiple tag sets |
| Adding `{}` without understanding consequences | Can hit secondaries meant for other workloads | Add fallback only intentionally |
| Assuming secondary reads always see fresh data | Replication is asynchronous | Define freshness needs, read concern/sessions |
| Treating `maxStalenessSeconds` as a hard SLA | Can read data staler than business expects | Monitor lag and choose right consistency |
| Setting a 5-second threshold without checking limits | Driver/server may reject config | Respect minimum thresholds and version rules |
| Tagging a hidden node expecting drivers to pick it | Hidden nodes skip normal selection | Use a visible secondary instead |
| Confusing `priority: 0` with `hidden` | Misplanned election/read behavior | Separate electability from visibility |
| Offloading heavy reports while skipping indexes | Moves `COLLSCAN` from primary to secondary | Tune queries/indexes before and after offloading |
| Ignoring replication apply load | Secondary lag rises and loses eligibility | Monitor CPU/I/O/oplog/lag |
| Treating tags as a hard security boundary | Other clients can still access per privileges | Enforce network/AuthZ/workload policies |
| Assuming two tagged secondaries split traffic 50/50 | RTT/pools/topology skew ratios | Measure via server addresses/metrics |
| Testing tag routing via direct connection | Bypasses driver topology selection | Test properly with replica set URIs |
| Assuming reporting nodes can never become primary | Tags do not control elections | Configure priority/votes properly |
| Running `rs.reconfig` in production to experiment | Can disrupt availability/elections | Use labs, change review, rollback plans |
| Failing to test secondary loss | Unexpected server timeouts or primary fallback | Run controlled chaos/failover drills |
| Applying one `readPreference` to all repositories | Post-write flows read stale data | Tailor policies per use case |
| Using `majority` read assuming zero staleness | Majority does not mean latest on a secondary | Use causal consistency or primary reads |

## 30. Review Questions

**1. What are tags in a replica set?**

Key/value metadata pairs attached to members, helping drivers select server groups via read preference. Tags change neither data placement nor access control.

**2. Can a primary carry tags?**

Yes. Yet mode `secondary` still never picks the primary, regardless of matching tags.

**3. Inside a single tag set with two key/value pairs, is the logic AND or OR?**

AND: a member must match both pairs. A list of multiple tag sets represents ordered fallback tiers.

**4. What does the `{}` tag set signify?**

No additional tag constraint at that fallback tier; it widens selection to secondaries previously excluded by tags.

**5. Which mode ensures reads never hit the primary under normal read preference rules?**

`secondary`, since it considers only eligible secondaries. If none exist, queries fail rather than silently using the primary.

**6. Why is `secondaryPreferred` risky for heavy reporting?**

When secondaries are unavailable, it falls back to primary, piling reporting load onto the transactional node.

**7. Does `nearest` mean the secondary with the lowest RTT?**

No. It considers both primary and secondaries based on eligibility/latency windows; it is not restricted to a single lowest-RTT secondary.

**8. Does `maxStalenessSeconds` replace `readConcern` majority?**

No. One filters members by estimated staleness; the other governs commit/consistency guarantees of observable data.

**9. Does setting `maxStalenessSeconds=120` guarantee read-after-write visibility?**

No. A secondary may not have applied the write yet. For read-your-writes, read primary or use causal consistency.

**10. Can a hidden secondary be selected via tags?**

Not through normal topology read preference. Hidden members serve dedicated operational tasks and are accessed via direct connections where supported.

**11. Does `priority:0` stop a node from serving reads?**

No. Priority 0 governs elections; if not hidden and eligible, a secondary can still serve reads.

**12. Does secondary reading double write speed?**

No. It only offloads part of primary read traffic; replication, index maintenance, and writes still carry cost.

**13. When no node matches a reporting tag, what does `secondary` mode do?**

It does not fall back to primary; the driver waits up to server selection timeout and returns an error if no eligible secondary exists.

**14. Do tags isolate data access by tenant?**

No. Access isolation must be enforced via application queries, authentication, and proper security policies.

**15. Why monitor replication lag after offloading reports?**

Reports can consume secondary CPU/I/O, slowing replication apply and causing stale data, loss of eligibility, or operational risk.

**16. Are tag sets a tool for an exact 70/30 split across two nodes?**

No. They filter/prioritize eligible pools; actual query distribution depends on latency, connection pools, and server selection.

**17. What role do indexes play when queries already run on secondaries?**

They let secondaries filter/sort efficiently, cutting scans and resource drain. Read preference does not create indexes automatically.

**18. When an election promotes a reporting node to primary, are its reporting tags lost?**

No; tags belong to the member. However, `secondary` mode stops selecting that node while it holds the primary role.

**19. Does a shard key serve the same purpose as a replica set member tag?**

No. Shard keys govern data distribution/routing across shards; member tags guide node selection within a replica set per read preference.

**20. Why is command monitoring useful?**

It confirms the exact server address executing reads rather than guessing from query success alone that the driver hit the intended secondary.

## 31. Quick-Reference Configuration Table

| Need | Suggested Read Preference / Tags |
|---|---|
| Read primary | `primary` |
| Secondary only | `secondary` |
| Secondary, primary fallback allowed | `secondaryPreferred` |
| Primary first, secondary fallback allowed | `primaryPreferred` |
| Latency-oriented, primary or secondary okay | `nearest` |
| Reporting secondary, no fallback | `secondary` + `[{purpose:"reporting"}]` |
| Prefer reporting hanoi, then other reporting | `secondary` + `[{purpose:"reporting",region:"hanoi"},{purpose:"reporting"}]` |
| Reporting, then any secondary | `secondary` + `[{purpose:"reporting"},{}]` — weigh risk |
| App secondaries only | `secondary` + `[{purpose:"app"}]` |
| Exclude high-estimated-lag secondaries | `maxStalenessSeconds` per supported threshold |
| Tune latency window | `localThresholdMS` via client settings/URI |
| Inspect member tags | `rs.conf()` |
| Inspect replica set status | `rs.status()` |
| Verify which node a query actually picked | Driver command monitoring / server logs / metrics |

## 32. Production Deployment Checklist

- [ ] Classified which queries **require primary** vs. which tolerate lag?
- [ ] Standardized tag taxonomy for `purpose`, `region`, and `zone`?
- [ ] Drivers use `secondary` mode where avoiding primary is strictly required?
- [ ] Clear understanding of when `secondaryPreferred`/`primaryPreferred` fall back to another role?
- [ ] Tag set lists arranged in deliberate **priority order**?
- [ ] Avoided `{}` tier where spilling onto other workload secondaries is unwanted?
- [ ] Topology retains enough nodes/election majority when setting `priority:0` or hidden?
- [ ] Avoided treating hidden/delayed members as normal reporting secondaries?
- [ ] Chosen `maxStalenessSeconds` per business needs and version limits?
- [ ] Understood `maxStalenessSeconds` does not guarantee read-your-writes?
- [ ] Read concern/sessions/write concern satisfy consistency requirements?
- [ ] Driver connections use a replica set URI with proper topology discovery?
- [ ] Verified which member read queries **actually execute on**?
- [ ] Checked query plans/indexes rather than merely moving execution?
- [ ] Monitoring replication lag, oplog window, CPU/I/O, and network?
- [ ] Bounded concurrent reporting jobs, query time, and retry budgets?
- [ ] Tested losing eligible secondaries and verified fallback behavior?
- [ ] If sharded, configured matching read tags across all relevant shards?
- [ ] `rs.reconfig` changes executed only via reviewed operational procedures with rollback?
- [ ] All metrics measured under representative workloads, not tiny lab datasets?

## 33. Conclusion

**Replica set member tags** describe which nodes suit different read workloads. Combined with **ordered read preference tag sets**, applications can prioritize secondaries by region and purpose—such as `purpose:reporting` or `purpose:app`—while controlling fallback behavior. Yet choosing the **mode** sets a crucial boundary: `secondary` reads only secondaries and fails when none match, whereas `secondaryPreferred` can shift load back onto the primary.

Effective read scaling requires more than editing connection strings. Account for **replication lag**, consistency and read-your-writes, **latency windows**, indexes, secondary capacity, elections/failover, and workload throttling. For heavy reporting, a **clearly tagged visible reporting secondary, strict `secondary` read preference, monitoring, and bounded retries** is usually far more predictable than letting all queries roam across nearest nodes.

The ultimate proof is always **which member the system actually reads from, at what replication state, and at what cost and latency**—not merely a `tags` line inside `rs.conf()`.
