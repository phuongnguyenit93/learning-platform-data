# Elections, Stepdown, and Handling Connections During Primary Transitions in a MongoDB Replica Set

## 1. Context and Objectives

A MongoDB replica set is a group of `mongod` processes that jointly maintain copies of a dataset. During normal operation, a replica set has **one primary** that accepts normal write operations; **secondary** members replicate operations from the primary to maintain availability and support recovery.

However, the primary is not a permanent server address. It can:

- Encounter an OS, hardware, or network failure.
- Lose connectivity with enough voting members.
- Be proactively asked by an administrator to **step down** for maintenance.
- Be replaced following a configuration change or an election.
- Restart after maintenance and become a secondary.

Applications usually do not need to know *which machine* will be primary forever. Applications need to know **how to find the current primary**, **how to cope with the window when no primary exists**, and **how not to lose or duplicate business operations when retrying**.

This lesson belongs to the **Replica set** chapter of the **Database Engine Document MongoDB** module, focusing on three topics:

1. **Elections:** which members can be elected, how many votes are required, and why network partitions affect writability.
2. **Stepdown:** the primary proactively relinquishing its role, how to perform safe maintenance, and impacts on in-flight requests.
3. **Handling connections during primary transitions:** seed lists, topology discovery, retryable reads/writes, write concern, transactions, idempotency, and monitoring.

After this lesson, you will be able to analyze a failover event without confusing **an open TCP connection**, **having a new primary**, **an operation having been executed**, and **an operation having been acknowledged as successful to the client**.

> **Key point:** Failover does not guarantee every request succeeds uninterrupted. MongoDB and drivers help automatically discover the new primary, yet applications still need retry policies, timeouts, outcome verification, and business operations safe to execute under transient failures.

## 2. From a Single Node to a Replica Set

A standalone deployment:

~~~text
Application
     |
     v
  mongod
  (one node)
~~~

When that node stops operating, the application has no replacement node within the same deployment.

A typical three-member replica set:

~~~text
                       Replica set rsDemo
                 +-----------------------------+
                 |                             |
Application ---->|  node-a:27017  PRIMARY      |
                 |      |                      |
                 |      | oplog replication    |
                 |      +-------------------+  |
                 |      |                   |  |
                 |      v                   v  |
                 |  node-b:27017       node-c:27017
                 |  SECONDARY          SECONDARY
                 |                             |
                 +-----------------------------+
~~~

Secondaries receive data by replicating and applying changes from the oplog via the replication mechanism. Hostnames in the diagram are illustrative; in real deployments, they must be resolvable and reachable addresses among members and from applications.

### 2.1. Dynamic Roles vs. Fixed Configuration

| Term | Meaning |
|---|---|
| `PRIMARY` | Member currently holding primary authority; accepts normal writes |
| `SECONDARY` | Member syncing data from the replica set; can run as candidate if eligible |
| `ARBITER` | Member participating in voting without storing data |
| `STARTUP`, `RECOVERING`, `ROLLBACK` and other states | Node lifecycle states; not writable by default |
| `priority` | Relative preference when a member is eligible to run as candidate |
| `votes` | Ability to cast votes in elections |
| `term` | Election epoch used in election/replication mechanisms |

The `PRIMARY` role is dynamic state. Node-a might be primary in the morning and secondary after an election. Applications should not hard-code "node-a is the write machine."

### 2.2. Data Replication and Write Path

Normal writes must be sent to the primary:

~~~text
Client
  |
  v
PRIMARY ---- oplog ---> SECONDARY 1
    |
    +-------- oplog ---> SECONDARY 2
~~~

When a client requests write concern `w: "majority"`, successful acknowledgment requires the necessary number of data-bearing members to have recorded the operation per the topology's majority rules. That differs from the primary merely accepting the operation with `w:1`.

**Do not assume secondaries are always instantaneously up to date with the primary.** Replication can lag, and read preference/read concern choices affect how applications observe data after failover.

## 3. Primary Election Mechanism

An election can take place when:

- The current primary stops responding to heartbeats or loses the ability to maintain its role.
- The primary proactively steps down.
- Configuration or priorities allow an eligible member to become primary.
- A recovery/restart triggers a topology change.

An **eligible** secondary can become a candidate and request votes from members configured to vote. MongoDB requires a **majority of votes from configured voting members** to elect a new primary.

### 3.1. Majority/Quorum

In a configuration with `V` voting members, the majority vote count is:

\[
\text{majorityVotes}=\left\lfloor\frac{V}{2}\right\rfloor+1
\]

| Voting members | Majority votes required |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 7 | 4 |

Example with three members having one vote each:

~~~text
node-a: 1 vote
node-b: 1 vote
node-c: 1 vote

Total: 3 votes
Majority: 2 votes
~~~

When node-a fails, node-b and node-c can still reach two votes and elect a new primary if they satisfy candidacy, state, and data freshness conditions.

If only node-b remains running and cannot reach the other two nodes, **one vote is insufficient to elect a primary** in a three-voter configuration. This is an intentional constraint to protect role consistency during network partitions.

### 3.2. Why Are Odd Voter Counts Commonly Chosen?

In common setups, three or five voting members generally provide useful fault-tolerance ratios:

- With 3 voters, 2 votes are needed; losing 1 voter still leaves majority.
- With 5 voters, 3 votes are needed; losing 2 voters still leaves majority.
- With 4 voters, 3 votes are needed; it also tolerates losing only 1 voter just like a 3-voter setup in terms of majority votes.

Therefore, adding a fourth voter to three voters **does not automatically increase** the number of members that can be lost while preserving majority. However, actual failover capability also depends on network topology, data-bearing member count, data freshness, and voting config.

MongoDB allows at most **7 voting members** in a replica set; total member limits and extra constraints must be checked against the exact server version. Do not increase voting member count merely to "switch primaries faster."

### 3.3. Elections Depend on More Than Votes

A candidate must also meet conditions such as:

- Being a member capable of becoming primary, not an arbiter.
- Having a suitable `priority` setting (non-zero).
- Having eligible replication state/data freshness under election rules.
- Not being in initial sync, recovering, or an ineligible state.
- Meeting replica set term and configuration rules.

Thus, **having enough votes without an eligible secondary** can still result in a period with no primary.

### 3.4. Terms and Preventing the Old Primary from Continuing Writes

MongoDB uses election terms and replication mechanisms to coordinate leadership transitions. When a node detects it cannot maintain the primary role, it must relinquish that role per system rules.

A client holding an open TCP connection to the old primary **does not mean that node still has authority to accept writes**. The driver must refresh topology; new operations may fail with a not-primary error and then be rerouted or retried per supported policy.

Do not rely on a host "still responding to ping" to conclude it is a valid primary.

## 4. Three Network Scenarios Clarifying Majority Rules

### 4.1. Primary Loses Connectivity, Two Secondaries Still See Each Other

~~~text
Before:
A (PRIMARY) ---- B (SECONDARY)
      \          /
       \        /
        C (SECONDARY)

After incident:
A  X      B <----> C
(isolated)   has 2/3 votes
~~~

B and C can elect a new primary if eligible. A cannot keep holding a valid primary role indefinitely once it loses majority reachability.

### 4.2. Two Nodes Unreachable, Only One Node Alive

~~~text
A  X       B  X       C
                       |
                  1/3 vote
                  no majority
~~~

C does not elect itself primary merely because it is the sole running node. Applications must handle periods with no primary rather than trying to write directly to C.

### 4.3. Network Partition into Two Groups

~~~text
Group 1: A + B            Group 2: C
          2 votes                 1 vote

   Capable of electing          Lacks majority
   a valid primary              to elect primary
~~~

Majority and terms prevent both sides from maintaining two valid primaries in the same consistent configuration. During transition windows, however, a client may briefly see stale state or errors; let the driver update topology instead of treating stale heartbeat results as write authority.

### 4.4. Quorum Does Not Mean Every Request Succeeds

Even once group B+C has elected a new primary:

- Clients still holding connections to A can hit errors.
- The driver must discover and select the new server.
- An in-flight write can have an unknown outcome to the application.
- Transactions may be aborted or have unknown commit outcomes.
- Secondary reads may observe data at a different point in time.

The election mechanism resolves **who can be primary**; it does not directly resolve **retry semantics of every business API**.

## 5. `priority`, `votes`, and Member Roles

A member has two parameters that are easily confused:

- `votes`: whether the member participates in voting, typically 0 or 1.
- `priority`: preference level for becoming primary if the member is eligible to run.

Conceptual configuration example:

~~~javascript
{
  _id: "rsDemo",
  members: [
    {
      _id: 0,
      host: "node-a.example.test:27017",
      votes: 1,
      priority: 2
    },
    {
      _id: 1,
      host: "node-b.example.test:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "node-c.example.test:27017",
      votes: 1,
      priority: 0
    }
  ]
}
~~~

This is only an **illustrative configuration sample**, not a command to run directly. Node-c can still vote, yet with `priority:0` it cannot be elected primary.

### 5.1. Does High Priority Always Win?

No. Priority influences preference under suitable conditions; the high-priority node must also be online, eligible, synced, and electable. It cannot force an isolated or heavily lagging node to become primary immediately.

Use priority to express desired role placement across infrastructure; do not use priority to bypass majority rules.

### 5.2. Priority 0

A secondary with `priority:0` cannot be elected primary, yet can continue syncing and serving permitted reads per configuration. It can still be a voter if `votes:1`.

Use cases: a node in a remote region or a node dedicated to reads/reporting where you never want it to become primary.

### 5.3. Hidden Secondary

A hidden secondary is a type of secondary not selected by regular applications as a normal read member through standard discovery; it is configured ineligible to become primary and can serve dedicated workloads per design.

Do not confuse hidden with "not in the replica set." The node still participates in replication; voting configuration and availability must be checked specifically.

### 5.4. Arbiter

An arbiter votes but **stores no data** and cannot become primary. A configuration with an arbiter is commonly called PSA (Primary–Secondary–Arbiter).

Limited benefit: adding a voter when an extra data-bearing member cannot be added.

Trade-offs:

- An arbiter provides no extra data copy.
- PSA topology creates complex edge cases around majority write concern and write availability.
- It does not replace having three data-bearing members in a design requiring high durability/recoverability.

When possible, three data-bearing members are usually easier to reason about for elections and majority writes. Do not add an arbiter just to patch a quorum incident without analyzing topology.

## 6. Heartbeats, Election Timeout, and Primary Transition Time

Replica set members periodically exchange heartbeats to track each other's state. Common parameters:

- `heartbeatIntervalMillis`: heartbeat interval, commonly defaulting to 2 seconds.
- `electionTimeoutMillis`: timeout threshold for detecting election need, commonly defaulting to 10 seconds.

**These defaults are not a fixed failover SLA.** The time from primary failure until the application successfully writes again also depends on:

1. Other nodes detecting the change.
2. Election execution and candidate readiness.
3. Replication lag and catch-up requirements.
4. Network latency and CPU/I/O resources.
5. Time for the driver to update topology via SDAM.
6. `serverSelectionTimeoutMS` settings and retry mechanisms.
7. Application timeouts, queues, and load.

Do not promise "a new primary will always appear in exactly 10 seconds" merely because the default election timeout is 10 seconds.

### 6.1. Why Lowering Election Timeout Is Not Always Better

Lowering the timeout excessively in networks with latency, packet loss, or frequent GC/OS pauses can cause the replica set to hold elections too frequently, increasing disruption.

Adjusting election timeout is an operational decision requiring network quality measurement and cluster profiling; never tune it haphazardly for "instant failover."

### 6.2. When Can It Take Longer?

- Secondaries have not caught up with the oplog.
- Initial sync or recovering is in progress.
- Most voters are unreachable.
- Candidate nodes are resource-starved.
- Topology changes have not yet been discovered by the driver.
- Clients use a bad connection string pinned only to the old host.

What matters for applications is tolerating a period with **no primary** and responding appropriately, rather than relying on an imaginary fixed second count.

## 7. What Is Stepdown?

**Stepdown** is the action of the primary relinquishing the primary role. This process can be triggered proactively for maintenance or performed by MongoDB when the primary role is no longer valid.

For controlled maintenance, an administrator can ask the current primary to step down so an eligible secondary can be elected as the new primary.

Diagram:

~~~text
Before stepdown:
node-a = PRIMARY
node-b = SECONDARY
node-c = SECONDARY

           |
           | rs.stepDown(...)
           v

Transition:
node-a = SECONDARY / stepping down from PRIMARY
node-b = SECONDARY / running for election
node-c = SECONDARY
May briefly have no PRIMARY

           |
           | election completes
           v

After:
node-a = SECONDARY
node-b = PRIMARY
node-c = SECONDARY
~~~

**Stepdown does not guarantee node-b wins.** Which node becomes primary depends on configuration, votes, priority, data freshness, and cluster state.

### 7.1. Stepdown Is Not Shutdown

- `stepDown`: node leaves the primary role while the `mongod` process can keep running and continue operating as a secondary.
- `shutdown`: stops the process.
- `rs.remove()`: changes replica set membership.
- `rs.reconfig()`: changes replica set configuration.

These operations differ in risk. Never use `rs.remove()` or force reconfig merely to simulate a routine primary switch.

### 7.2. When to Proactively Step Down?

Examples:

- Maintaining the host currently serving as primary.
- Executing a rolling upgrade procedure following server version guidelines.
- Moving the role to an eligible node prior to infrastructure changes.
- Practicing failover in test/staging environments to confirm applications retry properly.

In production, stepdown causes brief write disruption and can interrupt in-flight operations. It requires approval, monitoring, and a recovery plan.

## 8. Inspecting Replica Set Status Before Acting

Suppose you have a replica set named `rsDemo` with three configured hosts. Example application URI:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/admin?replicaSet=rsDemo
~~~

The `example.test` domains are placeholders, not real MongoDB endpoints. Replace them with actual hostnames present in the config and reachable from the machine running `mongosh`.

Connect with `mongosh`:

~~~bash
mongosh "mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/admin?replicaSet=rsDemo"
~~~

Once connected:

~~~javascript
rs.status();
~~~

Commonly observed fields include set name, term, member states, health, and optime/heartbeat info depending on version.

### 8.1. Printing Member Status More Compactly

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  term: status.term,
  members: status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    lastHeartbeatMessage: m.lastHeartbeatMessage
  }))
});
~~~

**Illustrative** sample output, not fixed output:

~~~javascript
{
  set: "rsDemo",
  term: NumberLong("12"),
  members: [
    {
      name: "node-a.example.test:27017",
      state: "PRIMARY",
      health: 1
    },
    {
      name: "node-b.example.test:27017",
      state: "SECONDARY",
      health: 1
    },
    {
      name: "node-c.example.test:27017",
      state: "SECONDARY",
      health: 1
    }
  ]
}
~~~

Do not infer that `health:1` alone means a node is ready to replace the primary. Check candidacy eligibility, replication state, and majority.

### 8.2. `db.hello()`

~~~javascript
db.hello();
~~~

Useful fields when present in the output:

| Field | Meaning |
|---|---|
| `setName` | Replica set name |
| `isWritablePrimary` | Whether the responding node is currently considered writable primary |
| `secondary` | Whether the node is currently a secondary |
| `primary` | Host reported as current primary, if known |
| `hosts` | Member list published for discovery |
| `me` | Address of the responding node itself |
| `electionId`, `topologyVersion` | Topology change info when provided |

`db.hello()` is a state observation **at the instant the command returns**. Because an election can occur right afterward, never use a single `hello` call to assume that host will accept writes indefinitely.

### 8.3. `rs.conf()`

~~~javascript
rs.conf();
~~~

View `members` configuration with `host`, `votes`, `priority`, `hidden`, `arbiterOnly`, and `settings` if present.

Do not treat `rs.conf()` output as a list of "nodes guaranteed to be healthy." Configuration states **who is defined as a member**; `rs.status()` and monitoring sources tell you **current operational state**.

### 8.4. Checking Replication Health

Before a proactive stepdown:

- Can enough voters communicate to form a majority?
- Is there a data-bearing secondary eligible to be elected primary?
- How caught up is the candidate secondary?
- Is any member undergoing initial sync/rollback/recovering?
- Is the workload currently running critical long-running writes or transactions?

Depending on version and privileges, inspect optime fields in `rs.status()` or use monitoring/replication lag tools from your provider.

## 9. `rs.stepDown()` Command and Parameters

In `mongosh` connected to the **primary**, you can request:

~~~javascript
rs.stepDown();
~~~

Or specify parameters explicitly:

~~~javascript
rs.stepDown(60, 15);
~~~

Typical arguments are:

| Parameter | Role |
|---|---|
| `stepDownSecs` | Duration in seconds during which the old primary is ineligible for re-election after stepdown |
| `secondaryCatchUpPeriodSecs` | Wait interval for eligible secondaries to catch up before completing stepdown per command mechanics |

For example, `rs.stepDown(60, 15)` asks the old primary to step down for 60 seconds per command semantics and allows up to 15 seconds for catch-up. It does **not** mean the cluster will definitely have no primary for 60 seconds. A new primary can be elected much sooner.

Common defaults are 60 seconds for the step-down period and 10 seconds for the catch-up period, though you should check documentation for your exact version.

### 9.1. Stepdown Can Return an Error or Drop Connections

During stepdown, the old node may close client connections and interrupt in-flight operations. `mongosh` may see a network error or not-primary error even when the request successfully caused the node to step down.

Therefore:

1. Do not rely solely on a shell exception to conclude stepdown failed.
2. Reconnect using a replica set URI containing multiple seed hosts.
3. Inspect `rs.status()`, `db.hello()`, and monitoring.
4. Confirm a new primary exists and application health returns.

### 9.2. An Eligible Secondary Is Required

A normal stepdown may refuse to execute if no eligible secondary is ready to take over under the required conditions, or if catch-up cannot complete appropriately.

This is a safety mechanism. Never force a stepdown when the cluster only has one data-bearing member available just to "test failover."

### 9.3. Never Use Force as Default Behavior

MongoDB's `replSetStepDown` administrative command supports a `force` parameter in administrative contexts. Forcing stepdown can prolong write disruption, raise risk if no eligible secondary exists, and alter catch-up guarantees.

For learning and routine maintenance procedures, **do not use `force:true`** unless under a dedicated runbook and an administrator understands the impact. Never try force on a production cluster just to see if an error goes away.

### 9.4. Do Not Run Stepdown on `mongos` or Standalone

`rs.stepDown()` is for a replica set primary, not a generic command to switch roles on a standalone `mongod` or directly control all shards through `mongos`.

In a sharded environment, each shard is its own replica set with its own shard primary; config servers also typically run as a replica set. Maintenance procedures must target the exact component per deployment guidelines.

## 10. Controlled Stepdown Procedure

Below is a **conceptual runbook** for a replica set in test/staging or under an approved operational procedure.

### Phase A — Before Switching Primary

1. Verify exact replica set name and hostnames.
2. Check `rs.status()`, `rs.conf()`, and replication lag.
3. Confirm enough voting members can form a majority.
4. Confirm at least one secondary is eligible and sufficiently caught up.
5. Ensure applications connect using a **replica set URI**, not pinned to the old primary.
6. Check for long-running operations/transactions or sensitive batch writes.
7. Watch dashboards for request errors, latency, server selection, and election events.
8. Confirm owner/team, maintenance window, and rollback/recovery plan.

### Phase B — Execution

On the primary in an authorized environment:

~~~javascript
rs.stepDown(60, 15);
~~~

`mongosh` may report a disconnect. That is an expected part of the process to verify, not a definitive failure signal on its own.

### Phase C — Observe the Election

Reconnect via the seed list and monitor:

~~~javascript
db.hello();
rs.status();
~~~

Wait for the replica set to announce a stable `PRIMARY` node. Never manually send writes to a secondary just because it is reachable.

### Phase D — Verify Application Health

- Did the driver locate the new primary?
- Do meaningful test writes succeed with appropriate write concern?
- Have error rates and server selection times returned to normal?
- Are there requests with unknown outcomes needing reconciliation?
- Is there any lingering data lag or incomplete long-running transaction?

For business verification, use idempotent keys and test data, never random writes/edits to production records.

### Phase E — Record Findings

Document stepdown timestamp, old/new primary, election term (if available), observed write-outage duration, client errors, retries, reconciliation outcomes, and any anomalies.

**Important point:** A runbook does not end at "`mongosh` printed ok." The real completion criterion is **a stable replica set and properly recovered application traffic**.

## 11. Automatic Primary Replacement When a Node Fails

Unlike planned stepdown, automatic failover can happen without prior notice.

~~~text
T0   node-a is PRIMARY
T1   node-a hits network / process failure
T2   secondaries detect primary state is no longer valid
T3   candidacy and voting
T4   node-b becomes PRIMARY if majority and eligibility are met
T5   driver updates topology and routes new writes to node-b
~~~

These milestones indicate ordering only, **not guaranteed second counts**.

### 11.1. Errors Observable from the Application

- Writes to the old primary are rejected.
- Connection reset/closed.
- No writable primary found within the server selection deadline.
- Transactions aborted.
- In-flight commands interrupted due to role change.
- Unknown write outcome due to disconnect before receiving ACK.

When seeing these errors, do not immediately assume every write failed to execute. Distinguish **not executed**, **executed yet client lost the response**, and **rolled back** in the context of write concern and replication.

### 11.2. The Old Primary Returns

When node-a restarts or reconnects to the network, it typically rejoins as a secondary and syncs to the replica set's chosen history.

In cases where old writes were not majority-committed, those writes may be rolled back as the node aligns with the new primary's history. This is a key reason to choose a write concern matching durability needs.

Do not assume the returning old primary immediately becomes primary again, or that every pre-failure write survives on the new primary.

## 12. Applications Must Connect to the Replica Set, Not Pin to the Old Primary

### 12.1. Mistake: Listing Only One Host

An incomplete URI for HA requirements:

~~~text
mongodb://node-a.example.test:27017/app
~~~

Depending on how the driver discovers topology and configuration, a single seed host can still lead to discovering the replica set. However, providing only one initial host reduces connection startup resilience if that host is down before the driver learns the member list.

A more dangerous case is **forcing direct connection**:

~~~text
mongodb://node-a.example.test:27017/app?directConnection=true
~~~

When pinned to a single host, the application is not configured to discover a new primary via standard replica set mechanisms. This URI is unsuitable for applications requiring automatic failover.

### 12.2. URI with Multiple Seed Hosts

An explicit replica set URI:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/app?replicaSet=rsDemo&retryWrites=true&retryReads=true&readPreference=primary&w=majority
~~~

Meaning:

| Component | Role |
|---|---|
| Multiple hosts in seed list | Driver has multiple starting points to discover the deployment |
| `replicaSet=rsDemo` | Verifies topology is a replica set with the expected name |
| `retryWrites=true` | Enables retryable writes for supported operations |
| `retryReads=true` | Enables retryable reads per driver/command capabilities |
| `readPreference=primary` | Reads via the primary per selected policy |
| `w=majority` | Requests majority write concern |
| `directConnection=false` (implicit in common configs) | Allows topology discovery rather than pinning one host |

**Hostnames are illustrative.** In production, configure real hostnames, TLS, authentication, and private networking per organizational policy.

### 12.3. Which Host List Does the Server Advertise?

The driver does not rely only on the seed list string. It queries topology state via `hello`/SDAM and discovers hostnames from the replica set config.

If MongoDB advertises hostnames that cannot be resolved from the application network, failover can still fail even if an initial seed host was reachable.

Check all of:

- DNS, routing, and firewalls between clients and all members.
- Hostnames in `rs.conf()`.
- TLS certificate hostname validation.
- Kubernetes, Docker, NAT, or multi-network environments.
- Ability for clients to reach **every host eligible to become primary**.

### 12.4. `mongodb+srv` URI

With deployments supporting SRV, a `mongodb+srv://...` URI can discover endpoints via DNS SRV/TXT records and corresponding driver mechanisms.

What remains essential is using the right URI for the deployment, right replica set/cluster name, TLS security, and avoiding pinning writes to the old primary. Do not switch a standard URI to SRV unless DNS infrastructure actually provides the required records.

## 13. How Does the Driver Detect Primary Changes? (SDAM)

**SDAM** stands for **Server Discovery and Monitoring**. The MongoDB driver monitors topology to know:

- Which nodes are currently reachable.
- Which node is primary.
- Which nodes are secondaries.
- Whether topology or term has changed.
- Which address is valid to receive commands given the chosen read preference and write capability.

~~~text
                   MongoDB Driver
                +-------------------+
App operation ->| Server selection  |
                | + monitoring      |
                +---------+---------+
                          |
          +---------------+---------------+
          |               |               |
        node-a          node-b          node-c
        SECONDARY       PRIMARY         SECONDARY
                          |
                          v
                        Write
~~~

When the old primary steps down, the driver updates its topology view and finds the new primary. This takes time; requests during a no-primary interval wait or fail depending on the server-selection deadline and connection state.

### 13.1. Do Not Cache a `primaryHost` Variable in Application Code

Conceptually wrong:

~~~javascript
// Application pseudocode: never hard-assume a fixed primary.
const primaryHost = "node-a.example.test";
sendEveryWriteTo(primaryHost);
~~~

Better: create a `MongoClient` using the replica set URI and reuse the client/connection pool, letting the driver manage discovery and server selection.

### 13.2. One Long-Lived `MongoClient` Is Better Than Creating One Per Request

MongoDB drivers typically manage connection pools and background topology monitoring. Creating a new `MongoClient` on every HTTP request:

- Increases connection and authentication overhead.
- Fragments topology monitoring.
- Increases CPU/socket usage.
- Can worsen overload during failover.

In server applications, manage client lifecycle alongside application lifetime or via framework dependency injection.

### 13.3. An Open Socket Can Still Point to a Secondary

Immediately after an election, the old node-a may still listen on the network and respond to eligible commands while no longer being primary. A successful TCP connection does not mean a write will be accepted.

This explains why applications must handle both **not writable primary** errors and ordinary network errors.

## 14. Timeouts vs. Retries

Common timeouts:

| Parameter/Concept | General Meaning |
|---|---|
| `serverSelectionTimeoutMS` | Maximum time the driver waits to find a suitable server for an operation |
| `connectTimeoutMS` | Network connection timeout to a host |
| `socketTimeoutMS` or driver-appropriate read timeout | I/O wait timeout for a socket/operation |
| `maxTimeMS` | Server-side execution time limit applied to supported commands |
| HTTP/gRPC Deadline | Application request service deadline, independent of MongoDB |

URI example:

~~~text
mongodb://node-a.example.test:27017,node-b.example.test:27017,node-c.example.test:27017/app?replicaSet=rsDemo&serverSelectionTimeoutMS=20000&retryWrites=true
~~~

If no new primary exists yet, the driver can keep waiting within the server selection bound. When it times out, an exception does not mean the cluster will never recover; it means that specific request could not find a suitable server within its deadline.

### 14.1. Short Timeouts Do Not Speed Up Elections

Lowering `serverSelectionTimeoutMS` from 30 seconds to 500 ms does not make MongoDB elect a primary faster. It causes more requests to **fail earlier** during failover.

Conversely, an overly long deadline can leave HTTP requests hanging and exhaust worker threads or queues. Balance deadlines against SLAs, concurrency, retry budgets, and user experience.

### 14.2. Retries Must Have a Budget

An application-layer retry policy should specify:

- Which operations/errors are retryable.
- Maximum retry count and total duration.
- Backoff and jitter to prevent all clients from retrying in lockstep.
- Overall request deadline.
- Which states require reconciliation instead of blind retry.
- How to log request IDs/idempotency keys.

Do not create infinite retry loops when the replica set lacks majority, as that can immediately overwhelm a newly recovering cluster.

## 15. Retryable Reads

Drivers support **retryable reads** for eligible read operations when enabled and supported by server/driver.

URI example:

~~~text
...?retryReads=true
~~~

If a read encounters a transient error due to networking or primary change, the driver can retry per supported rules.

Points to understand:

1. Not every command/configuration shares identical retry semantics.
2. Retrying a read may observe data from a newer point in time.
3. Pagination, sorting/filtering, and consistency still require dedicated design.
4. An aggregation pipeline with `$out`/`$merge` write stages should not be treated as pure read-only merely because `aggregate()` was called.
5. Secondary read preference never lets a secondary accept writes.

### 15.1. Read Preference Primary

~~~text
readPreference=primary
~~~

The driver selects the primary for reads. During an election gap, primary reads must wait or fail if no primary is available.

### 15.2. Read Preference Secondary or SecondaryPreferred

Secondary read policies can allow certain reads to continue while no primary exists, depending on topology and server selection. However:

- Secondaries can lag in replication.
- Not every read/operation type is suitable.
- Reading from a secondary does not enable writes when no primary exists.
- Flows requiring "read-your-own-writes immediately" need read concern, causal consistency/sessions, and node selection evaluation.

Do not blindly switch all reads to secondaries during failover if the application has strict freshness requirements.

## 16. Retryable Writes: How Far Can the Driver Handle Them?

**Retryable writes** allow the driver to retry **certain write operations** upon transient errors such as connection loss or primary transitions, per server/driver semantics.

Example:

~~~text
...?retryWrites=true
~~~

Operations typically in scope include single-document operations such as `insertOne`, `updateOne`, `replaceOne`, `deleteOne`, and certain `findOneAnd...` variants when prerequisites are met. Bulk writes are retryable only when every operation in the batch is of a supported retryable type; multi-document operations such as `updateMany`/`deleteMany` do not automatically carry the same guarantee.

Never assume a simplistic rule that "every write is automatically retried exactly once by the driver regardless of the error."

### 16.1. Why Do Retryable Writes Need Session/Transaction Metadata?

In the retryable write protocol, the driver and server use logical operation identifiers, sessions, and transaction numbers to recognize retries of the same operation under supported conditions.

The goal is preventing the server from executing **the exact same retryable write** twice simply because the initial response was lost. Yet this feature does not replace end-to-end business workflow idempotency and does not guarantee handling every combination of errors, timeouts, or non-retryable operations.

### 16.2. Example of a Write and Lost ACK

~~~text
Client                            Old Primary
   |                                   |
   | INSERT order-101 ---------------->|
   |                                   | Write may have executed
   |             X connection lost     |
   |                                   |
   |      Election takes place         |
   |                                   |
   | Driver selects new primary        |
   | Retryable write if supported      |
   |---------------------------------->|
   |                                   |
   | Acknowledged or returns error     |
~~~

If the client receives no ACK, the application **cannot conclude solely from a timeout that the write did not execute**. Driver retryable writes help cover many cases, yet if the application still receives a final error, the outcome may require reconciliation.

### 16.3. Never Blindly Retry `$inc` Operations

Business example:

~~~javascript
db.accounts.updateOne(
  { _id: "account-101" },
  { $inc: { balance: 100 } }
);
~~~

If an application hits a timeout without knowing whether the write applied, re-issuing the same `$inc` as a **new business request** can increment the balance twice. That risk differs from the driver retrying **the same retryable write** under protocol semantics.

Safer design uses transaction identifiers, ledger entries, or atomic conditional updates to guarantee each business action executes only the allowed number of times.

## 17. Idempotency: Protection at the Business Layer

An **idempotent** operation can be executed repeatedly without causing unintended side effects beyond executing it once, within its defined context.

### 17.1. Creating Orders with Application-Chosen `_id`

Example:

~~~javascript
db.getSiblingDB("replica_failover_lab").orders.insertOne({
  _id: "order-request-2026-001",
  customerId: "C01",
  status: "NEW",
  amount: NumberDecimal("42.00"),
  createdAt: new Date()
});
~~~

If the ACK is lost, the client sending a new `insertOne` with the same `_id` may hit a duplicate key error. That error suggests a document exists, yet **you should not treat every duplicate key error as unconditional success**. Read the record back and verify request ID/payload and ownership to confirm it truly resulted from the original request.

### 17.2. Upsert by Unique Business Key

Conceptual example:

~~~javascript
db.getSiblingDB("replica_failover_lab").requestLog.updateOne(
  { _id: "req-001" },
  {
    $setOnInsert: {
      type: "CREATE_ORDER",
      payloadHash: "expected-hash",
      status: "RECEIVED"
    }
  },
  { upsert: true }
);
~~~

Using a unique key per request helps the application recognize whether a request was already processed. Yet creating a log entry alone does not guarantee full business exactly-once behavior when external side effects exist, such as sending emails, charging payments, or publishing messages.

When multiple collections or side effects are involved, use transactions, outbox/inbox patterns, reconciliation, or appropriate business consistency mechanisms.

### 17.3. Distinguishing 3 Layers of Retry

| Layer | Responsibility |
|---|---|
| **Driver retry** | Retries a single command under supported protocol and session metadata |
| **Application retry** | Decides to re-run logic after failure, with timeouts/backoff and conditions |
| **Business idempotency** | Prevents duplicating business effects when a request is resubmitted |

If an HTTP client resends a request after timeout, that is typically a **new application request**, not automatically a protocol-level retryable write of the prior command. Thus, business-layer idempotency remains necessary.

## 18. Write Concern and Data After Failover

### 18.1. `w:1` vs. `w:majority`

With `w:1`, the primary acknowledges once one node satisfies the configured write concern. If the primary becomes isolated/fails before changes replicate and commit appropriately, writes not yet majority-committed may roll back.

With `w:"majority"`, acknowledgment requires the necessary number of data-bearing voting members per replica set calculation to satisfy majority write concern.

~~~javascript
db.getSiblingDB("replica_failover_lab")
  .orders
  .insertOne(
    {
      _id: "majority-test-001",
      createdAt: new Date(),
      status: "NEW"
    },
    { writeConcern: { w: "majority", wtimeout: 5000 } }
  );
~~~

Meaning:

- `w:"majority"` strengthens durability guarantees against election/rollback per server semantics.
- `wtimeout` limits how long to wait for the write concern to be satisfied.
- If a write concern times out, the write **may already have been applied** without yet being acknowledged at the requested level. Never treat a timeout as proof it "definitely wasn't written."

### 18.2. Arbiters Do Not Store Data

In a topology with an arbiter, it can vote to elect a primary yet cannot record data like a secondary. Election majority and majority write concern must not be simplified to "two votes means two data copies saved."

Evaluate `writeMajorityCount`, data-bearing members, and write concern configuration of your actual topology, especially PSA.

### 18.3. Read Concern Majority

When business logic requires reading only majority-committed data, consider `readConcern: "majority"` paired with appropriate read preference and session semantics.

Write concern and read concern address different problems:

- **Write concern:** acknowledgment level of a write operation.
- **Read concern:** consistency/commitment level of data a read is allowed to observe.
- **Read preference:** which node may be chosen to execute a read.

Do not assume merely setting `readPreference=secondaryPreferred` guarantees reading the latest version or eliminates all post-failover issues.

## 19. Rollback: What Happens to Insufficiently Protected Writes?

Suppose three members A, B, C:

~~~text
T0: A PRIMARY, B/C SECONDARY

T1: Client writes X to A, receives ACK with w:1
T2: X has not reached enough nodes to be majority-committed
T3: A becomes isolated

T4: B and C elect B as PRIMARY
T5: A returns, follows B's history
    X may roll back if not in the chosen history
~~~

This example illustrates the risk of acknowledging solely from the old primary. It does not mean **every `w:1` write rolls back**; it can happen under specific failure sequences.

### 19.1. Do Not Treat `w:1` ACK as a "Never Lose Data" Guarantee

If business requirements involve financial transactions, order creation, or critical event logging, choose write concerns and replication architectures matching the required data durability.

### 19.2. Majority Does Not Solve Every Application Problem

Even when a write is majority-committed, a client can still miss the ACK due to network failure. Identify and reconcile the request rather than blindly re-executing the business effect as a brand-new transaction.

### 19.3. Rolled-Back Operations and External Side Effects

If an application sends an email or calls a payment service immediately after an insufficiently protected write, external state may change while the MongoDB record rolls back.

When side effects matter, use transactions, outbox patterns, idempotent event delivery, and reconciliation. Failover never automatically rolls back emails, HTTP calls, or external systems.

## 20. Transactions When the Primary Changes

MongoDB supports multi-document transactions in appropriate topologies and versions. A running transaction can fail when a primary stepdown or election occurs.

Important error labels:

| Label | General Handling Meaning |
|---|---|
| `TransientTransactionError` | Transient error inside a transaction where the entire transaction may need retrying per driver pattern |
| `UnknownTransactionCommitResult` | Unclear whether commit succeeded; retry commit via appropriate mechanism |
| `RetryableWriteError` | Info supporting retryable write error handling per protocol/driver |
| `NoWritesPerformed` | Label in supported versions indicating no writes were performed after described write retries |

Do not treat these labels as plain text strings to match via exception message regexes. Drivers provide APIs/methods to inspect error labels.

### 20.1. Pre-Commit Errors Differ from Unknown Commit Results

Case A: The transaction hits a transient error before commit succeeds; the driver/helper may need to rerun the entire transaction.

Case B: The client sends commit, yet connectivity drops before receiving the response. The transaction **may already have committed**. Retry the commit per protocol or reconcile—do not immediately issue a new business transaction.

### 20.2. `withTransaction` and Callbacks with Side Effects

Many drivers offer `withTransaction` helpers or callback APIs that automatically retry transactions/commits per supported semantics.

Because the callback **may execute more than once**, never place non-idempotent external side effects—like sending emails, charging cards, or publishing messages—directly inside the callback without safeguards.

Instead, consider writing an outbox record inside the same transaction and having a worker deliver it externally with deduplication. That is application design, not an automatic feature of replica set elections.

### 20.3. `readConcern`/`writeConcern` in Transactions

Transaction design requires read concerns, write concerns, and read preferences compatible with driver/server rules. High consistency modes, especially snapshot reads, carry specific constraints and costs.

Do not arbitrarily switch transactions to secondary reads while handling primary failover.

## 21. Java Driver Example: Automatic Primary Discovery

Assume the system uses a MongoDB Java Sync Driver version compatible with the server. The Java Driver provides `MongoClient`, connection pooling, and SDAM.

The example below uses illustrative hostnames; replace them with names from your deployment.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

String uri =
    "mongodb://node-a.example.test:27017," +
    "node-b.example.test:27017," +
    "node-c.example.test:27017/app" +
    "?replicaSet=rsDemo" +
    "&retryWrites=true" +
    "&retryReads=true";

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.MAJORITY)
    .writeConcern(WriteConcern.MAJORITY)
    .retryWrites(true)
    .retryReads(true)
    .applyToClusterSettings(builder ->
        builder.serverSelectionTimeout(
            20, TimeUnit.SECONDS
        )
    )
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase db = client.getDatabase("app");
    MongoCollection<Document> orders =
        db.getCollection("orders");

    Document order = new Document("_id", "req-001")
        .append("status", "NEW")
        .append("amount", 42);

    orders.insertOne(order);

    Document saved = orders.find(
        new Document("_id", "req-001")
    ).first();

    System.out.println(saved);
}
~~~

**Note:** This program illustrates connection and read/write logic without credentials, TLS, or a real server environment. In production, configure authentication and secret management per policy.

### 21.1. What Happens During Stepdown in Java?

If node-a was primary and transitions to secondary:

- The driver detects node-a is no longer writable primary.
- The driver continues discovery via the remaining replica set nodes.
- For new write operations, the driver selects a node meeting the primary requirement.
- For supported transient errors, retryable writes/reads can complete the operation.
- If the server selection deadline expires or the error is non-retryable, the Java API can still throw an exception.

This does not require the application to close and recreate `MongoClient` after every election. Reusing a long-lived client is usually the right design.

### 21.2. Do Not Open a Client to a Host Read from a One-Off `hello`

Conceptually wrong:

~~~java
// Never cache "primary = node-a" and create a host-pinned
// MongoClient for all future writes.
~~~

Correct: the URI describes the replica set topology, while the driver manages member discovery and connection pooling.

### 21.3. Create One Client for the Application Lifecycle

In Spring Boot or Java servers, create `MongoClient` via configuration/DI; avoid creating and closing it on every request.

Benefits:

- SDAM maintains continuous topology state.
- Connection pools are reused.
- Connection and authentication overhead drops.
- Centralized timeout/retry management.

## 22. Java Driver: Handling Unknown Write Outcomes

Below is a **conceptual** pattern for creating an order with an application-assigned `_id`:

~~~java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

String requestId = "order-request-001";

Document desired = new Document("_id", requestId)
    .append("status", "NEW")
    .append("amount", 42);

try {
    orders.insertOne(desired);
    System.out.println("Write acknowledged");
} catch (MongoException ex) {
    // When ACK is unclear, do not conclude the write did not happen.
    // Classify error, request deadline, and reconciliation path.
    Document existing = orders.find(
        new Document("_id", requestId)
    ).first();

    if (existing != null) {
        // Compare actual contents/owner/payloadHash before
        // treating this as the same business request.
        System.out.println("Need to verify existing order");
    } else {
        // Observing no record still does not cover every
        // eventual failover/timeout edge case.
        System.out.println("Needs controlled recovery");
    }
}
~~~

This example is not a complete retry engine: the verification read itself can fail if failover has not finished yet. Real applications must protect the verification branch with timeouts and a resumable pending state.

### 22.1. Why Not Loop `insertOne` Infinitely?

A client might resend a new request after timeout, yet timeouts do not reveal server outcome. Retrying without a deadline will:

- Amplify request load while the system is degraded.
- Risk business duplicates if no unique key exists.
- Force users to wait indefinitely.
- Contend for resources with recovery.

Combine bounded retries, backoff/jitter, idempotency keys, and reconciliation.

### 22.2. Do Not Classify Errors Solely by Text Messages

Messages like `not primary`, `connection reset`, or `timed out` do not all carry identical semantics.

In the Java Driver, inspect exception types, error codes/labels when available, and write acknowledgment results. For transactions, error labels like `TransientTransactionError`/`UnknownTransactionCommitResult` are more reliable than message strings.

## 23. Read-After-Write When Primary Changes

A common requirement:

~~~text
POST /orders
  -> create order
GET /orders/{id}
  -> expect to see newly created order
~~~

If after writing on the primary the application reads from a secondary with replication lag, it may temporarily **not see** the new order.

Even when the URI enables `retryReads` and the driver picks a healthy secondary, that does **not** guarantee the secondary has applied the latest write.

### 23.1. Choose Mechanisms According to Need

| Need | What to Consider |
|---|---|
| Immediate read after write in business flow | Read primary, with session/causal consistency when appropriate |
| Reporting not needing latest state | Secondary reads may be appropriate |
| Read only majority-committed data | Read concern majority, paired with suitable read design |
| Consistent snapshot across multiple ops | Sessions/transactions/read concern as appropriate; watch cost |
| Infinite scroll UI | Stable sort, cursor tokens, data mutations, not just elections |

### 23.2. Read Preference Does Not Change Write Routing

`readPreference=secondaryPreferred` lets the driver pick a secondary for reads when suitable, **never letting the application write to a secondary** when no primary exists.

When majority is lost and there is no primary, write operations must wait or fail; no read preference setting bypasses this requirement.

## 24. Observing Failover from `mongosh` Without Altering Production Data

Assume you have an authorized practice replica set.

### 24.1. Watch the Current Primary

~~~javascript
const hello = db.hello();

printjson({
  setName: hello.setName,
  isWritablePrimary: hello.isWritablePrimary,
  primary: hello.primary,
  hosts: hello.hosts
});
~~~

If you run this command from `mongosh` connected via a replica set URI, the driver/shell picks an appropriate server per its mechanics. When inspecting **a specific member**, use the proper operational connection/tool with authorized privileges; never assume an arbitrary `hello()` represents all members at the same moment.

### 24.2. Watch Member States

~~~javascript
const s = rs.status();

printjson(
  s.members.map(m => ({
    host: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
);
~~~

No need to run tight continuous polling loops in this lesson; use monitoring or deliberate spot checks.

### 24.3. Testable Write Pattern

In a dedicated practice database:

~~~javascript
use replica_failover_lab

db.orders.updateOne(
  { _id: "health-check-order" },
  {
    $set: {
      status: "READY",
      checkedAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

If the primary transitions right during the write:

- It may succeed.
- It may hit a retryable error handled by the driver.
- It may exceed the deadline.
- It may be unclear whether the ACK met the requested write concern.

Do not treat `matchedCount:0` on an upsert as a failover error itself; when an upsert inserts a new document, `matchedCount` can be 0 while `upsertedId` is set.

## 25. Hands-On Failover Exercise in Staging

**Perform this section only if you have admin rights on a test replica set.** Never run stepdown in production for a routine learning exercise.

### Exercise 1 — Check Preconditions Before Stepdown

Record:

~~~javascript
rs.status();
rs.conf();
db.hello();
~~~

Answer:

1. How many voters exist?
2. How many votes are needed for majority?
3. Which members are secondaries?
4. Do any secondaries have `priority:0`?
5. Is there an eligible, sufficiently caught-up secondary?
6. Does the application host use a replica set URI or a single host?

### Exercise 2 — Start a Test Write Operation

In a client session:

~~~javascript
use replica_failover_lab

db.orders.updateOne(
  { _id: "failover-demo" },
  {
    $set: {
      status: "BEFORE_STEPDOWN",
      updatedAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: { w: "majority" }
  }
);
~~~

Read back the document and confirm success before administrative actions.

### Exercise 3 — Planned Stepdown

From `mongosh` authorized on the primary after confirming safe conditions:

~~~javascript
rs.stepDown(60, 15);
~~~

If the shell shows a network or not-primary error, reconnect via the replica set URI and verify topology. Do not keep calling `rs.stepDown()` repeatedly on the new primary just to see the command "succeed."

### Exercise 4 — Verify the New Primary

~~~javascript
db.hello();
rs.status();
~~~

Record:

- Which host holds the new primary role.
- States of the secondaries.
- Term if available.
- Timestamp when applications resumed writing.
- Any client exceptions observed.

### Exercise 5 — Test Write After Election

~~~javascript
db.getSiblingDB("replica_failover_lab")
  .orders
  .updateOne(
    { _id: "failover-demo" },
    {
      $set: {
        status: "AFTER_STEPDOWN",
        updatedAt: new Date()
      }
    },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );
~~~

Verify the document once the cluster stabilizes. Note this operation is strictly for practice; never touch real application records.

### Exercise 6 — Test Driver Reconnect

Build a Java app with `MongoClient` using multiple seed hosts and the `replicaSet` name. Keep `MongoClient` running across the stepdown, then observe:

- Does the driver automatically pick the new primary?
- How long do writes fail/wait during the election gap?
- Are retryable writes enabled?
- Did any request time out and require reconciliation?
- After the election, did the client need to recreate `MongoClient`?

**Goal:** Understand behavior, not overload the system with errors.

### Exercise 7 — Compare `w:1` and `majority`

No need to force data rollback. Explain on paper:

- With `w:1`, what does the first ACK confirm?
- With `w:"majority"`, what does the ACK wait for?
- If no ACK arrives due to network failure, is it certain the write did not execute?
- Why are unique request IDs/idempotency still needed?

### Exercise 8 — Reconciling an Uncertain Outcome Operation

Suppose an order-creation POST carrying `requestId:"req-123"` times out right after a primary change.

Design the steps:

1. Keep `requestId` fixed; do not generate a new ID for retries.
2. Reconnect through the replica set driver.
3. Check the record by `requestId`/unique key.
4. Compare `payloadHash` and tenant/owner.
5. If the matching record already exists, respond per API contract.
6. If absent, decide on bounded retry or return a pending-reconciliation status.
7. If a different record holds the same key, classify as a conflict; never treat every duplicate key as success.

## 26. Common Error Scenarios and Interpretations

| Symptom | Possible Cause | Resolution Direction |
|---|---|---|
| Driver reports no primary found | Election in progress, missing majority, DNS/network or wrong URI | Check topology, voters, server selection, connectivity |
| Write to old host returns not-primary | Node just stepped down | Use replica set URI/driver discovery; handle valid retries |
| Ping to old node succeeds yet insert fails | Old node is still online, now a secondary | Do not confuse TCP reachability with writable primary |
| `rs.stepDown` reports disconnect | Command may have triggered role change | Reconnect and check status; do not conclude from exception alone |
| Stepdown rejected | No eligible/caught-up secondary or other condition | Check lag, priority, quorum; do not force |
| Node with priority 0 is never elected | Configured ineligible | May be intended behavior; inspect `rs.conf` |
| Arbiter exists yet few data copies remain | Arbiters only vote | Evaluate topology, replication, and write concern separately |
| Secondary read misses recent write | Replication lag/consistency | Check read preference, read concern/sessions |
| Write times out yet document exists | ACK lost or write concern timeout | Reconcile by request ID; do not blindly retry |
| `$inc` applied twice | Application re-sent a new business op after ambiguous outcome | Use proper ledger/idempotency/transactions |
| `w:1` write lost after failover | Non-majority-committed write can roll back | Choose write concern matching required durability |
| Transaction fails mid-way | Primary change, transient transaction error | Use driver transaction retry pattern; check side effects |
| Commit result unknown | Disconnect at commit step | Retry commit per semantics; do not create new business op |
| URI lists only the dead old host | Discovery failed/no other seed | Provide multiple reachable seeds and `replicaSet` name |
| URI has `directConnection=true` | Driver pinned to one host | Use topology-aware replica set connection |
| Overly aggressive retries after failover | Many clients retrying simultaneously | Backoff+jitter, retry budgets, rate limiting |
| Continuous elections | Unstable network, timeout/priority/config, or resources | Inspect logs, heartbeats, lag, election terms |
| No primary despite one live node | Insufficient majority votes | Restore quorum; do not force writes |
| New primary stable yet API still fails | Connection pool/advertised hostnames/TLS/timeouts | Check advertised hosts and driver SDAM |
| Primary changed and app required restart | App pinned host or mismanaged `MongoClient` | Use long-lived `MongoClient` + proper topology URI |

## 27. Distinguishing Elections, Retries, Rollback, and Consistency

Four concepts often placed side by side solve different problems:

| Mechanism | Question Addressed |
|---|---|
| **Election/quorum** | Which node is permitted to act as primary? |
| **Driver SDAM + retry** | Can the client find the new primary and retry eligible commands? |
| **Write concern/rollback** | At what durability level was the write acknowledged, and could uncommitted history be reverted? |
| **Read concern/session/transaction** | At what consistency level is a read or group of operations allowed to view data? |

Examples:

- A successful election does **not** automatically guarantee a payment API executed exactly once.
- Retryable writes succeeding does **not** mean every new HTTP retry of the same business request is safe.
- `w:"majority"` helps protect acknowledged writes, yet clients can still lose the ACK.
- Secondary reads may continue during a no-primary gap without necessarily reflecting the latest data.
- A transaction commit with an unknown result must be handled differently from a transaction aborted before commit.

Resilient systems require combining these mechanisms rather than expecting elections alone to solve every business layer.

## 28. Monitoring Elections and Failover in Real Environments

Useful metrics/events:

### 28.1. Replica Set State

- Primary identity changes.
- Election term changes.
- Member health and state.
- `LastHeartbeatMessage`.
- Replication lag and optimes.
- Number of reachable members and ability to achieve majority.

### 28.2. Driver and Application

- Server selection timeout counts.
- Server selection time before and after failover.
- Insert/update/transaction error rates.
- Retryable errors and successful retries if recorded.
- API p50/p95/p99 latency.
- Connection pool checkout time and new connections.
- Requests with unknown outcomes needing reconciliation.
- Queue depth and concurrent retry volume.

### 28.3. Alerting Workflow

An alert saying merely "primary changed" is insufficient to understand impact. Correlate:

~~~text
Election event
     |
     +--> Who is the new primary?
     |
     +--> How long was there no primary?
     |
     +--> How much did app errors/latency spike?
     |
     +--> Are there transactions with unknown outcomes?
     |
     +--> What is replication lag post-failover?
     |
     +--> Did retries and idempotency work properly?
~~~

If election counts spike abnormally over a short window, investigate infrastructure/networking, disk stalls, CPU, and configuration rather than endlessly raising application timeouts.

## 29. MongoDB Compass and Primary Transition Scenarios

MongoDB Compass is a GUI tool for inspecting collections and certain connection states. Interfaces vary by version.

Sensible practice:

1. Connect to a test replica set using a connection string with proper seed list/cluster endpoint.
2. View database and collection lists while topology is stable.
3. In an authorized `mongosh` window, read `rs.status()` and `db.hello()`.
4. If authorized and in test/staging, perform a controlled stepdown.
5. Observe whether Compass continues querying after the election.
6. If Compass shows transient errors, wait for topology stabilization and re-check.
7. Cross-check with `mongosh` and driver logs; do not treat the UI showing documents as proof the connected node is currently primary.

Never intentionally step down a production cluster merely to demonstrate Compass; the UI is for observation, never a substitute for authorization and operational runbooks.

## 30. Misconceptions to Avoid

**Misconception 1: "A three-node replica set means there is always a primary."**

False. When majority is lost or no secondary is eligible, there can be no primary.

**Misconception 2: "Stepdown stops `mongod`."**

False. Stepdown changes role; the process normally continues running as a secondary.

**Misconception 3: "A 60-second stepdown means 60 seconds of downtime."**

False. That parameter governs how long the old primary avoids re-election; a new primary can be elected well before 60 seconds elapse.

**Misconception 4: "Enabling `retryWrites` makes every HTTP request run exactly once."**

False. The retryable write protocol applies only to eligible writes; HTTP retries are a separate layer requiring business idempotency.

**Misconception 5: "A lost ACK means the write definitely did not run."**

False. The write may already have executed or been majority-committed before the response was lost.

**Misconception 6: "Reading from secondaries solves all failover errors."**

False. It does not enable writes without a primary and can serve stale data.

**Misconception 7: "Having an arbiter provides an extra data copy."**

False. An arbiter votes but stores no data.

**Misconception 8: "Lowering `electionTimeout` always gives better HA."**

Not necessarily. Too low a timeout can trigger unnecessary elections on jittery networks.

**Misconception 9: "After an election, the old primary automatically becomes primary again."**

Not guaranteed. The old node may remain a secondary.

**Misconception 10: "An exception after stepdown proves the command failed."**

Insufficient. Connections may close as part of role transition. Verify cluster state.

## 31. Knowledge Check Exercises

### Question 1. What is the majority of a three-voter replica set?

**Answer:** 2 votes. If only one voter can communicate with itself, it fails to achieve majority.

### Question 2. Can a secondary with priority 0 and votes 1 become primary?

**Answer:** No. It can vote per configuration, yet priority 0 prevents it from being elected primary.

### Question 3. How do stepdown and shutdown differ?

**Answer:** Stepdown changes the primary role within the replica set; shutdown stops the process.

### Question 4. Why can a client connected directly to node-a alone run into trouble after stepdown?

**Answer:** Node-a is no longer writable primary. If the application pins the connection, it will not automatically select the new primary like a topology-aware replica set driver.

### Question 5. When a user POST to create an order times out, can you immediately resend the POST with a new ID?

**Answer:** Unsafe. The previous write may already have executed. Keep the request ID, retry per policy, and reconcile/enforce idempotency.

### Question 6. What is the significance of majority write concern in a failover context?

**Answer:** It requires acknowledgment from the necessary number of data-bearing members per majority write concern, reducing the risk of losing acknowledged writes during elections/rollbacks.

### Question 7. Does `readPreference=secondaryPreferred` let the server allow writes to a secondary when no primary exists?

**Answer:** No. It is solely a **read** node selection policy.

### Question 8. Why can `rs.stepDown` disconnect `mongosh`?

**Answer:** When the primary leaves its role, certain connections/operations are interrupted. Reconnect and inspect status rather than concluding from a single error.

### Question 9. How does `TransientTransactionError` differ from `UnknownTransactionCommitResult`?

**Answer:** One indicates retrying the entire transaction per appropriate helper/protocol; the other indicates uncertain commit outcome and requires retrying commit/reconciling per corresponding semantics.

### Question 10. Why can a node respond to ping yet refuse inserts?

**Answer:** It may be a secondary, recovering, or no longer writable primary; network reachability is not write authority.

## 32. Scenario Design Exercises

### Scenario A — Primary Loses Power

A replica set has A, B, and C all as data-bearing voters, with A as primary. A loses power while B and C remain connected.

Present:

1. How many votes are needed for majority?
2. What can B/C do?
3. During the election gap, what errors might the write application observe?
4. What characteristics must the connection string have?
5. Why should you examine the write concern of transactions issued right before A lost power?

### Scenario B — 1–2 Network Split

A is in a one-node group; B+C are in a two-node group. Nodes cannot communicate across groups.

Explain why the two-voter group has a chance to elect a valid primary while A alone should not keep holding write authority. Could there be a brief period where the driver still thinks A is primary? How should the application react?

### Scenario C — Processing a Payment

An application receives a request with idempotency key `payment-777`. After sending a status update write, the connection to the primary resets.

Design:

- "Committed," "not committed," and "unknown" states.
- Key-based reconciliation operation.
- Retry limits.
- How to avoid calling the payment gateway a second time.
- Role of transactions/outbox when multiple collections or external side effects are involved.

### Scenario D — Automatic Failover Succeeds, Yet API Errors Persist for 30 Seconds

In monitoring, the election finished early, yet the API keeps reporting server selection timeouts.

Propose checks:

1. Is the application using `directConnection=true`?
2. Are the seed list and `replicaSet` name accurate?
3. Do advertised hosts in `rs.conf()` resolve from the app host?
4. Do firewalls/TLS on the new primary permit client access?
5. Is `MongoClient` being recreated too frequently?
6. Is connection pool/network load abnormal?
7. Is the application deadline shorter than discovery time?

### Scenario E — Rolling Maintenance

A DBA wants to upgrade software on a three-node replica set. Explain why replication health, member eligibility, majority, maintenance ordering, and client reconnection must be verified **before** stepping down the primary.

Do not propose shutting down all nodes simultaneously. Ordering and compatibility for rolling upgrades must follow the runbook for the specific MongoDB version.

## 33. Pre-Production Checklist

### Replica Set

- [ ] Sufficient data-bearing members/voters for fault tolerance targets.
- [ ] Majority and network topology clearly understood.
- [ ] Candidate secondaries have suitable priorities/votes.
- [ ] Replication lag and health monitored.
- [ ] Not relying on an arbiter as a data copy.
- [ ] Stepdown runbook and new-primary verification steps documented.
- [ ] Procedure exists for loss of majority.

### Client and Connections

- [ ] URI describes the replica set with multiple seed hosts or appropriate discovery endpoint.
- [ ] Write application is not pinned to the old primary host.
- [ ] All advertised hosts are reachable from the application network.
- [ ] Long-lived `MongoClient`/connection pool lifecycle.
- [ ] Server selection timeout, connect timeout, and request deadline defined.
- [ ] Read/write retries enabled where appropriate for driver/server.
- [ ] Read preference and read concern chosen per business requirements.

### Business Safety

- [ ] Critical writes use appropriate write concerns.
- [ ] Create/modify requests carry idempotency keys or deduplication guards.
- [ ] Unknown write outcomes are reconciled rather than assumed failed.
- [ ] Transactions handle transient errors and unknown commit outcomes per semantics.
- [ ] External side effects are not duplicated when transaction callbacks retry.
- [ ] Backoff, jitter, and retry budgets implemented.
- [ ] HTTP statuses and pending/reconciliation states have clear contracts.

### Monitoring

- [ ] Track primary changes/election terms.
- [ ] Track replica lag and member health.
- [ ] Track server selection timeouts, not-primary, and network errors.
- [ ] Track p95/p99 request latency during failover.
- [ ] Log request IDs to reconcile ambiguous outcomes.
- [ ] Failover drills run in staging under representative workloads.

## 34. Summary

A MongoDB replica set can automatically elect a new primary when the current primary is no longer viable. However, a successful election is only **one part** of application resilience.

- **Elections:** require a majority of voting member votes and an eligible candidate; lacking majority can leave no primary.
- **Priority/votes:** govern election participation and preference, not replacing state/freshness checks.
- **Stepdown:** proactively yields the primary role for maintenance; does not mean shutdown or downtime equal to the passed seconds.
- **Replica set URI + SDAM:** lets drivers locate the current primary and reroute writes when topology changes.
- **Retryable reads/writes:** recover from many transient errors, strictly within supported operations and conditions.
- **Majority write concern:** strengthens durability for acknowledged writes; cannot replace idempotency design when clients lose ACKs.
- **Transactions:** distinguish transient failures from unknown commit outcomes; avoid non-idempotent side effects inside retryable callbacks.
- **Monitoring/runbooks:** observe from server state through client errors, measure write-outage duration, and reconcile requests with unknown outcomes.

A highly available MongoDB system needs not only **fast primary elections**, but also **applications wired to the right topology, reacting safely during failover, and preserving business semantics on retries**.

## Official Reference Documentation

- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set Primary](https://www.mongodb.com/docs/manual/core/replica-set-primary/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — rs.stepDown](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — replSetStepDown command](https://www.mongodb.com/docs/manual/reference/command/replSetStepDown/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Production Notes for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
