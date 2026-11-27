# Priority, Votes, Arbiters, and Fault-Tolerance Trade-offs

A MongoDB **replica set** consists of multiple members jointly maintaining copies of data and coordinating to choose a **primary**. Applications typically write to the primary, while secondaries replicate data via replication. When the primary disconnects or fails, voting members can hold an **election** to choose a new primary.

However, "having many nodes" does not mean "tolerating arbitrary failures." MongoDB must distinguish **voting rights**, **eligibility to become primary**, **holding a data copy**, and **durability of a write operation**. Three commonly confused settings are:

- `priority`: a member's relative preference **when running for primary**;
- `votes`: whether the member **contributes a vote** toward election quorum;
- `arbiterOnly`: a member that only **votes**, without storing a data copy.

Misconfiguring these attributes can produce a system that **still elects a primary yet fails to satisfy desired write concerns**, or has multiple secondaries yet lacks enough votes to keep a primary active during a network partition.

This lesson explains how MongoDB computes majority, the meaning of `priority` and `votes`, the role of arbiters, differences between **PSS** and **PSA** models, availability vs. durability trade-offs, as well as safe monitoring and reconfiguration procedures.

> **Key idea:** *Election quorum* determines whether a primary can be elected and maintained. *Write concern majority* determines whether a write has been sufficiently confirmed by data-bearing members. **An arbiter participates in elections yet cannot acknowledge having stored data.**

## 1. Roles in a Replica Set

Suppose a three-machine deployment:

```text
                  Replica set rs0
             ┌──────────────────────────┐
Client write ──►  mongo-a:27017 PRIMARY │
             │       │       │          │
             │       │ oplog │          │
             │       ▼       ▼          │
             │  mongo-b     mongo-c     │
             │  SECONDARY   SECONDARY   │
             └──────────────────────────┘
```

In steady state:

- **Primary (P)** accepts normal client write operations.
- **Secondary (S)** maintains data via replication; depending on configuration, it can also serve read operations.
- **Arbiter (A)** is a special member that **holds no collection data**, does not replay the oplog like a secondary, and cannot become primary; it only participates in elections.
- **Voting member** is a member with `votes: 1`. A secondary with `priority: 0` can still be a voting member.
- **Non-voting member** has `votes: 0`, does not participate in quorum, cannot become primary, and must have `priority: 0`.

Topology notations:

| Notation | Meaning |
|---|---|
| **PSS** | One primary and two data-bearing secondaries |
| **PSA** | One primary, one secondary, one arbiter |
| **PS** | One primary, one secondary, no arbiter |
| **PSSS** | One primary, three secondaries |
| **PSSSS** | One primary, four secondaries |
| **P + S + A** | More explicit notation to avoid miscounting data-bearing members |

**The primary/secondary role is not permanently tied to a host.** During an election, an eligible secondary can become primary, and the old primary can return as a secondary.

## 2. Three Concepts to Keep Separate

Many design mistakes stem from treating `priority`, `votes`, and replication as the same thing.

| Concept | Question Answered | What It Does Not Guarantee on Its Own |
|---|---|---|
| `priority` | How strongly should this member be preferred for primary? | Does not add extra votes; does not create data copies |
| `votes` | Does this member participate in elections/quorum? | Does not imply holding data |
| `arbiterOnly` | Does this node only vote or also store data? | Arbiters do not acknowledge `w: "majority"` like secondaries |
| `writeConcern` | At what level must a write be confirmed before returning success? | Does not decide which node gets elected |
| `readConcern` | What commitment guarantees apply to data read? | Does not replace primary election mechanics |
| `replication lag` | How far behind the primary is a secondary? | A voting node does not necessarily hold every recent write |

For example, a secondary configured as:

```javascript
{
  host: "mongo-b:27017",
  priority: 0,
  votes: 1
}
```

**cannot become primary**, yet still **votes** and **stores data**; writes it confirms can contribute toward applicable write concerns.

Conversely, an arbiter:

```javascript
{
  host: "mongo-arb:27017",
  arbiterOnly: true,
  priority: 0,
  votes: 1
}
```

**holds a vote yet stores no data copy**. Thus, even though both have `priority: 0`, they differ completely in durability value.

## 3. Election Majority: How Quorum Is Calculated

To elect a primary, a replica set needs a **majority of votes among configured voting members**.

With `V` members having `votes: 1`, the minimum votes for a majority is:

\[
Q = \left\lfloor\frac{V}{2}\right\rfloor + 1
\]

Examples:

| Voting members `V` | Majority `Q` | Max absent votes while still retaining quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

A MongoDB replica set supports at most **seven voting members**. A replica set can include non-voting members, yet they **do not increase** the vote count used to calculate majority.

The table shows only the **mathematical vote-count condition**; having a working primary also requires an eligible candidate, sufficiently caught-up data per election rules, ability to communicate with quorum, and meeting MongoDB's criteria. You cannot simply count powered-on machines and conclude a usable primary exists.

### 3.1. Why Can Two Votes Not Tolerate Losing One Node?

Topology of two voting data-bearing nodes:

```text
mongo-a (P, votes=1) ─── mongo-b (S, votes=1)

V = 2, Q = 2
```

If `mongo-a` stops operating, `mongo-b` has **one vote**, short of `Q=2`, so it cannot elect itself primary. If the network link between the two nodes breaks, neither side seeing one vote can validly maintain primary capability.

Thus, there are **two data copies** yet no automatic failover upon losing one voting member. This is why a two-vote PS model fails to deliver the election availability many people assume by default.

### 3.2. Why Are Three Votes Commonly Used?

PSS topology:

```text
mongo-a (P, votes=1)
mongo-b (S, votes=1)
mongo-c (S, votes=1)

V = 3, Q = 2
```

If one voting member is lost, the remaining two still have enough votes. When the primary is lost, the two remaining secondaries can elect a new primary if other election conditions are satisfied.

In PSS, all three members **store data**. This provides a stronger foundation both to maintain election quorum and to satisfy write concerns requiring confirmation across multiple data copies.

### 3.3. Odd Numbers Are Not Magic

The rule of thumb "use an odd number of nodes" is a mnemonic, not a guarantee of arbitrary fault tolerance:

- Four voting members require `Q=3`, so they tolerate only **one** absent vote.
- Five voting members also require `Q=3`, yet tolerate **two** absent votes.
- Six voting members require `Q=4` and tolerate **two** absent votes.

Therefore, **the configured vote count and likelihood of losing votes simultaneously** are what must be analyzed. Adding a node merely to "make it odd" impacts quorum, write concerns, geographic placement, and operational cost.

## 4. Priority: Who Is Preferred to Become Primary?

In a replica set config, `priority` determines a member's relative preference **when electing a primary**.

Example:

```javascript
{
  _id: 0,
  host: "mongo-a:27017",
  priority: 3,
  votes: 1
}
```

Default priority for an electable data-bearing member is typically `1`. Higher values are used when preferring a specific node; `priority: 0` means the node is **ineligible to become primary**.

### 4.1. High Priority Does Not Add Votes

Suppose:

```text
mongo-a: priority=10, votes=1
mongo-b: priority=1,  votes=1
mongo-c: priority=1,  votes=1
```

Quorum is still computed over **three votes**, so **two votes** are required. `priority=10` **does not mean mongo-a has ten votes**. Node a may be preferred in elections or trigger priority takeover when appropriate, yet cannot unilaterally claim primary if isolated from the majority.

### 4.2. Priority Is Preference, Not a Rigid Assignment

Suppose node a has the highest priority, yet:

- a is powered off;
- a cannot reach quorum;
- a lags in replication and is ineligible to become primary;
- a is starting up/recovering;
- a has errors or fails election criteria;

then another eligible node can become primary. You cannot promise "the highest-priority node is always primary at all times."

Under appropriate conditions, MongoDB uses **priority takeover** so a higher-priority secondary can initiate an election once eligible. Yet takeovers can cause **stepdowns, connection drops, and brief disruptions**; do not use priority to continuously force primary onto an unstable or lagging node.

### 4.3. Priority 0: Store Data and Vote Only

Example:

```javascript
{
  _id: 2,
  host: "mongo-report:27017",
  priority: 0,
  votes: 1
}
```

This node:

- Replicates data as a secondary when in an appropriate state;
- Contributes **one vote** to election quorum;
- Cannot become primary;
- Can participate in write acknowledgments involving data-bearing voting members;
- Can serve reads under appropriate read preferences.

`priority: 0` is useful for dedicated read secondaries, nodes in locations where primary write traffic is unwanted, or members barred by operational policy from becoming primary.

**Important:** A replica set must never be configured so that every data-bearing voting member is ineligible for primary while expecting failover elections to work. Valid candidates must remain when failover is needed.

### 4.4. Priority in Multi-Region Environments

Suppose data center A has stable networking and low latency to the write API path:

```text
Region A:
  mongo-a1  priority=3, votes=1

Region B:
  mongo-b1  priority=1, votes=1

Region C:
  mongo-c1  priority=1, votes=1
```

The goal may be preferring primary in A while healthy, yet allowing B/C to fail over if A fails. This makes sense when latency from apps to primary in A is better.

However:

- If Region A is network-partitioned, it still cannot keep primary without quorum.
- Regions B/C must have sufficient latency and capacity to handle writes during failover.
- High priority on one host in A does not replace proper network, disk, and replication design.
- Excessive priority gaps or aggressive takeover setups can cause unnecessary role churn during instability.

## 5. Votes: Who Participates in Quorum?

Each member in the replica set config has a `votes` value per MongoDB-supported rules, typically `0` or `1`.

```javascript
{
  host: "mongo-b:27017",
  votes: 1,
  priority: 1
}
```

A member with `votes: 1` contributes one vote to the election mechanism.

```javascript
{
  host: "mongo-d:27017",
  votes: 0,
  priority: 0
}
```

A member with `votes: 0` does not participate in quorum and cannot become primary; `priority` must be 0.

### 5.1. A Non-Voting Secondary Still Holds Data

Setting `votes: 0` **does not stop replication**. A non-voting secondary still holds a data copy, usable for certain read/backup needs under MongoDB constraints.

However:

- It contributes no vote to keep a primary.
- It cannot become primary if voting members fail.
- Having a non-voting secondary must not be equated with strengthening quorum.
- It is not counted like a data-bearing **voting** secondary in majority write concern rules.

If the primary goal is improving failover resilience, adding `votes: 0` members will **not** solve it.

### 5.2. Example: Two Voting Members and Two Non-Voting Secondaries

```text
mongo-a  P   votes=1
mongo-b  S   votes=1
mongo-c  S   votes=0, priority=0
mongo-d  S   votes=0, priority=0
```

There are four machines storing data yet **only two votes**, so `Q=2`. If mongo-a stops, the remaining three secondaries hold only **one vote** from mongo-b. They do not form a three-voting-member quorum.

Many data copies do not substitute for a proper voting quorum configuration.

### 5.3. Increasing Votes Can Also Make Availability Harder

Suppose three healthy voting members (`V=3`, `Q=2`): the system tolerates one absent vote.

Adding a fourth voting member (`V=4`, `Q=3`) raises the new quorum to three. Four voting members still tolerate only one absent vote.

Thus, adding a voting member **does not automatically improve the number of simultaneous failures tolerated**. Recalculate majority **after the config changes**, rather than just looking at host count.

## 6. What Is an Arbiter?

An arbiter is a replica set member configured with `arbiterOnly: true`. Its primary role is **providing one vote** when quorum is needed, typically when deploying another data-bearing node is infeasible.

An arbiter:

- **Has a vote** under standard arbiter configuration;
- **Stores no copy of the application dataset**;
- **Does not replay data like a data-bearing secondary**;
- **Cannot become primary**;
- **Does not serve application data queries** like a secondary;
- **Does not acknowledge write concerns like a data-bearing node**;
- Still requires resources, networking, monitoring, and security protection.

Member configuration example:

```javascript
{
  _id: 2,
  host: "mongo-arb:27017",
  arbiterOnly: true,
  priority: 0,
  votes: 1
}
```

**An arbiter is not a third data copy.** If both primary and secondary lose data, the arbiter cannot recover data from a copy that does not exist.

### 6.1. Which Problem Does an Arbiter Solve?

Suppose budget allows running only two data-bearing nodes:

```text
mongo-a  Primary, data bearing
mongo-b  Secondary, data bearing
```

If both vote, `V=2`, `Q=2`; losing one node prevents elections from reaching majority.

An arbiter can be added:

```text
mongo-a  P   votes=1  data=yes
mongo-b  S   votes=1  data=yes
mongo-c  A   votes=1  data=no

V=3, Q=2
```

Now, if one data-bearing member disconnects while the survivor still reaches the arbiter, **two votes** remain, satisfying election quorum. That is where an arbiter helps.

**Yet the arbiter adds no data copy.** The severe trade-off with `w: "majority"` is analyzed next.

### 6.2. Do Not Treat an Arbiter as a "Cheaper Secondary" in Every Aspect

An arbiter typically has lower storage needs than a data-bearing secondary, yet:

- It remains a critical quorum component;
- Network failure or arbiter shutdown changes election capability;
- Arbiter placement can bias which side wins during network partitions;
- It improves neither read scaling, backup distribution, nor durability;
- It still requires security design, monitoring, hardening, and upgrades.

An arbiter placed on an unstable host can push a replica set into unpredictable election behavior.

## 7. Two Types of Majority Commonly Confused

The most important part of replica set design is **never equating election majority with data acknowledgment majority**.

### 7.1. Election Majority

Election quorum is determined by the number of **voting members**:

```text
P + S + A:
V = 3
Election majority Q = 2
```

Because the arbiter holds one vote, the `P + A` combination has two votes and can maintain quorum under suitable conditions.

### 7.2. Write Concern Majority

In MongoDB, `writeConcern: { w: "majority" }` requires the write to be confirmed by a **majority of data-bearing voting members** per replica set rules. An arbiter **holds no data**, so it cannot confirm writing to a data copy of its own.

In a **PSA** topology with two data-bearing voting members, satisfying `w: "majority"` requires confirmation from **both eligible data copies**, per majority write concern rules.

This creates a confusing scenario:

```text
Primary P alive        ✓ has data
Secondary S lost       ✗ cannot confirm
Arbiter A alive        ✓ votes, holds no data

Election quorum: P + A = 2/3           SUFFICIENT
w: "majority" from data-bearing nodes: INSUFFICIENT
```

**A primary can still exist and election quorum remain intact, yet writes requiring majority can block and time out** because only one data copy remains.

### 7.3. Explicit Write Concern Command Example

```javascript
db.orders.insertOne(
  {
    orderNo: "O-229",
    createdAt: new Date(),
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

In PSA, if the data secondary is unavailable, majority requirements may **fail to complete within `wtimeout`** even though primary and arbiter still communicate.

**Do not infer that a timeout means the write definitely does not exist on the primary.** In some cases the primary applied the operation, yet **failed to reach the requested write concern level**. Clients must handle errors/uncertain outcomes using retryable writes, idempotency, or reconciliation per application contract.

### 7.4. How Does `w: 1` Differ?

```javascript
db.orders.insertOne(
  {
    orderNo: "O-230",
    createdAt: new Date()
  },
  {
    writeConcern: { w: 1 }
  }
);
```

`w: 1` asks the primary to acknowledge the operation per corresponding write concern rules, **without waiting** for confirmation from other data-bearing secondaries.

In PSA when the secondary is down, `w: 1` can still succeed on the primary if the primary holds election quorum and is writable. Yet a record residing on only one data-bearing node carries higher risk if the primary fails before replication occurs.

You cannot treat an acknowledged `w: 1` write as equivalent to a `w: "majority"` write in surviving failover.

### 7.5. Journal and Write Concern

`w` specifies **the number of confirming members**; `j` relates to waiting for the journal on nodes per corresponding write concern semantics. Durability also depends on journaling and storage/deployment configuration.

Example:

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
}
```

Never describe `j: true` as replacing replication, or replication as completely replacing all persistent storage mechanisms. Explaining durability requires examining **copy count, acknowledgment level, journaling, topology, and failover**.

## 8. PSA vs. PSS: Identical Three Nodes on the Surface, Fundamentally Different

Both topologies have **three voting members** and require a two-vote majority, yet differ in **data copies**.

### 8.1. PSS Model: Three Data-Bearing Nodes

```text
          PSS
   ┌───────────────┐
   │ P: data + vote│
   │ S: data + vote│
   │ S: data + vote│
   └───────────────┘

Voting members = 3
Election quorum = 2
Data-bearing voting members = 3
```

If one data-bearing node is lost:

- **Two votes** remain.
- Both remaining nodes **hold data**.
- `w: "majority"` can generally still be satisfied by the remaining data copies if replication and write concern conditions are healthy.
- If the primary is lost, the two secondaries can elect a new primary when eligible.

### 8.2. PSA Model: Two Data-Bearing Nodes and One Arbiter

```text
          PSA
   ┌───────────────┐
   │ P: data + vote│
   │ S: data + vote│
   │ A:      vote  │
   └───────────────┘

Voting members = 3
Election quorum = 2
Data-bearing voting members = 2
```

If the secondary is lost:

- Primary and arbiter still hold **two votes**.
- Only **one** data-bearing member remains.
- The system may keep accepting `w: 1` writes depending on primary state.
- **There are no longer enough data-bearing acknowledgments to complete majority writes** as when both data-bearing members were healthy.

If the arbiter is lost, P and S still hold two votes as well as two data copies, so PSA can typically retain a primary and satisfy majority writes when replication is healthy.

### 8.3. Quick Decision Table

| Scenario | PSS (3 data) | PSA (2 data + A) |
|---|---|---|
| Vote count | 3 | 3 |
| Election quorum | 2 | 2 |
| Data copies | 3 | 2 |
| Loss of one secondary | Two data-bearing nodes remain; majority writes possible | Only one data-bearing node left; majority writes impacted |
| Loss of primary | Two secondaries elect new one; two copies remain | Secondary and arbiter can elect; only one active data copy remains |
| Loss of arbiter | No arbiter | P + S remain, typically enough quorum |
| Arbiter helps acknowledge writes? | N/A | **No** |
| Data storage cost | Higher | Lower |
| Suitable when continuous majority writes needed after single node loss | **Preferred choice** | **Not equivalent to PSS** |

The table assumes remaining nodes are healthy, connected, and satisfy election/replication rules; it is not an absolute uptime guarantee.

## 9. Failure Matrix for PSA

Consider three members:

```text
P = mongo-a, data-bearing, vote=1
S = mongo-b, data-bearing, vote=1
A = mongo-c, arbiter, vote=1
```

Common scenarios:

| Connected/Healthy Nodes | Election Quorum | Can Primary Operate? | `w: "majority"` for New Writes? |
|---|---|---|---|
| P + S + A | 3/3 | Yes | Yes, when P/S replication is healthy |
| P + S | 2/3 | Yes | Yes, when P/S replication is healthy |
| P + A | 2/3 | Yes, under suitable conditions | **Insufficient data copies** |
| S + A, P lost | 2/3 | S can be elected if eligible | **Insufficient two data-bearing nodes** |
| P alone | 1/3 | Cannot maintain valid primary without quorum | No |
| S alone | 1/3 | Cannot elect itself primary | No |
| A alone | 1/3 | Cannot act as primary | No |

If only `S + A` remain, the secondary can become the new primary, yet remains the **sole active data copy**. Distinguish "still having a new primary" from "satisfying all write concerns."

### 9.1. Risk of Data Existing on Only One Copy

In the `P + A` state, if the application lowers write concern to `w: 1` to keep writing, new writes exist **only on P** until S returns and syncs.

If P subsequently loses data or cannot recover before S receives those writes, the arbiter holds no data to rescue them. Therefore, allowing `w: 1` in a degraded state must be paired with **accepted RPO**, recovery planning, and business controls.

"The arbiter keeps quorum for the primary" never means "the arbiter protects written records."

## 10. PSA and Implicit Default Write Concern

There is a critical operational point: **never assume drivers always use `w: "majority"`** merely because MongoDB supports majority write concern.

Depending on server version and cluster-wide default read/write concern settings, the **implicit default write concern** can differ by topology. In some deployments with an arbiter, rules involving voting members and non-arbiter data-bearing members can cause the inferred default to be `w: 1`.

Therefore:

1. Check the actual **default read/write concern** of your deployment.
2. For critical business operations, declare write concern **explicitly** per durability needs.
3. Never change cluster-wide default write concern just to make a benchmark pass.
4. When adding/removing an arbiter or voting member, re-evaluate default rules and any clients relying on defaults.

Example check in an environment with appropriate admin privileges:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

Exact command and output fields depend on version/permissions. If you need to alter default RW concern, follow a deployment plan, understand impacts, and use operations supported by your server version's docs.

**Practical rule:** a financial/order system should never rely on guessing "MongoDB always defaults to majority writes"; measure/inspect the real configuration.

## 11. Changing `priority` Is Not Changing `votes`

Two operations have different purposes:

### 11.1. Lowering Priority While Keeping Vote

```javascript
{
  host: "mongo-c:27017",
  priority: 0,
  votes: 1
}
```

The node still stores data, still votes, and does not run for primary.

This choice is useful if a secondary sits in a location undesirable for primary yet still needs to contribute to quorum/durability under supported conditions.

### 11.2. Disabling Voting Rights

```javascript
{
  host: "mongo-c:27017",
  priority: 0,
  votes: 0
}
```

The node can still act as a data-syncing secondary, yet contributes no vote and cannot become primary.

If a replica set originally had three voting data members and you set one secondary to `votes: 0`, voting members drop to **two** and election majority becomes **two votes**. Losing either of the two voting members loses quorum, even though the non-voting secondary remains healthy with a data copy.

**Never change `votes: 1` to `votes: 0` just to "reduce influence of a remote node" without recalculating fault tolerance.**

## 12. Priority Takeover and Unnecessary Election Risks

An illustrative setup:

```text
mongo-a priority=5, votes=1
mongo-b priority=2, votes=1
mongo-c priority=1, votes=1
```

Suppose mongo-a fails, and mongo-b is elected primary. Once mongo-a recovers, reaches healthy/caught-up state, and has proper connectivity, the system can trigger a **priority takeover** to prefer primary on mongo-a.

Benefits:

- Primary tends to return to the node/region optimized for applications;
- Can lower write-traffic latency in steady state.

Trade-offs:

- Every primary switch can cause a brief write interruption;
- In-flight transactions may be affected;
- Drivers/clients must handle retryable errors;
- If the high-priority node repeatedly flaps, it can cause unnecessary role churn.

For most applications, **primary stability** is highly valuable. Do not create excessive priority differentials without clear business/operational justification.

### 12.1. Priority Is Not an Advanced Health Check

Priority does not evaluate CPU, IOPS, replication lag, client connections, and regional latency for you. A high-priority node with a slow disk does not "upgrade its performance" via config.

When choosing priorities, consider:

- Host resources and stability;
- Ability to handle write throughput;
- Location of write-issuing applications;
- Network RTT to secondaries and quorum;
- Recovery behavior after failover.

## 13. Network Partitions: Why Does Quorum Matter?

A three-voting-member replica set can split into two sides:

```text
Partition 1: mongo-a + mongo-b (2 votes)
Partition 2: mongo-c           (1 vote)

V = 3
Q = 2
```

The two-vote side can maintain or elect a primary if eligible. The one-vote side cannot validly elect a primary on its own.

The goal is preventing two independent partitions from both believing they hold majority write authority, thereby reducing **sustained split-brain primary** risk.

However, this is not a guarantee of "zero transient errors." During a partition/failover:

- The old primary may take time to realize it lost quorum and step down;
- Drivers may briefly connect to a node with stale status;
- Some operations may return "not primary", timeouts, or transient transaction errors;
- Pre-failover `w: 1` writes may roll back under applicable scenarios;
- Clients must handle retries/idempotency properly.

**Quorum reduces the risk of two valid primaries operating concurrently over time; applications must still design for state-transition errors.**

### 13.1. Which Partition Holds the Arbiter Can Decide Which Side Has a Primary

In PSA:

```text
Region A: P (data)
Region B: S (data)
Region C: A (arbiter)
```

If the network splits into:

```text
Partition 1: P
Partition 2: S + A
```

the `S + A` side has two votes, meeting election criteria even with only **one active data-bearing node** on that side. P alone cannot maintain a valid primary.

If the partition shifts to:

```text
Partition 1: P + A
Partition 2: S
```

then P + A holds quorum, while S alone does not.

Arbiter placement is not just a hosting cost question; it can decide **which region retains write authority during a network split**. You must consider network topology and where applications reside.

## 14. Geographic Vote Quorum Does Not Equal Geographic Data Durability

Suppose a replica set has three members:

```text
DC Hanoi:        P (data, vote)
DC Da Nang:      S (data, vote)
DC Ho Chi Minh:  A (vote only)
```

From an election viewpoint, three sites hold three votes. Yet actual data resides in only **two places**.

If the DC holding the secondary disconnects, primary and arbiter still retain quorum; the system can accept `w: 1` writes yet gains no extra data copy of new writes on the arbiter. There are not "three data-storing regions."

A properly distributed three-data-bearing topology can better preserve writes confirmed by a majority of data-bearing members across certain failures, at corresponding storage/replication cost and network latency.

### 14.1. Never Place an Arbiter on the Same Failure Domain Without Accounting for It

If an arbiter sits on the same host, rack, power domain, or network segment as a data-bearing member, a single failure can knock out **two votes at once**.

Example:

```text
Failure domain X: P + A
Failure domain Y: S
```

When X loses power, S has one vote and cannot elect a primary. Thus, the arbiter fails its goal of increasing election availability against that failure mode.

Do not merely count "three `mongod` processes"; count **independent failure domains** and surviving votes under each failure scenario.

### 14.2. WAN Latency Impacts Replication and Failover

Spreading data-bearing members across regions helps geographic fault tolerance with trade-offs:

- Higher WAN RTT;
- Majority writes may have to wait for acknowledgments across the network;
- Secondaries may lag when bandwidth is insufficient;
- Elections/heartbeats become more sensitive to network partitions;
- Backups and resyncs can take longer;
- Higher storage/egress costs.

No topology is universally optimal: design must balance **RTO, RPO, latency, cost, and fault domains**.

## 15. Priority 0 and Practical Failover Capability

Suppose three data-bearing voting members:

```text
mongo-a: priority=2, votes=1
mongo-b: priority=0, votes=1
mongo-c: priority=0, votes=1
```

There are three votes and `Q=2`, yet **only mongo-a is eligible to become primary**. If mongo-a fails, the two remaining secondaries hold a majority of votes yet **have no valid candidate** because both have priority 0.

Conclusion:

> **Having quorum is not enough**: at least one valid candidate must exist within the quorum partition.

This is an easily overlooked design mistake when ops teams set priority 0 on every secondary to "pin primary" to one host.

### 15.1. A More Failover-Friendly Configuration

```text
mongo-a: priority=2, votes=1
mongo-b: priority=1, votes=1
mongo-c: priority=0, votes=1
```

If a is lost, b can stand as primary candidate backed by c's vote under appropriate conditions.

Still, if both a and b are lost, only c remains with one vote, lacking quorum. Do not infer from b having priority=1 that c alone can rescue the cluster if only one node survives.

### 15.2. Do Not Confuse "Non-Voting" with "Priority-Zero"

`votes: 0` implies `priority: 0`, whereas `priority: 0` **does not** necessarily imply `votes: 0`.

Example:

```javascript
// Secondary can still vote:
{ priority: 0, votes: 1 }

// Secondary neither votes nor becomes primary:
{ priority: 0, votes: 0 }
```

The two configurations affect quorum, write concern, and fault tolerance differently.

## 16. Post-Failover Capacity Problem

Increasing data copies does not guarantee applications run well after losing a node.

Suppose:

```text
mongo-a: 16 CPU, 64 GB RAM, NVMe; priority=5
mongo-b: 2 CPU, 8 GB RAM, HDD; priority=1
mongo-c: arbiter; priority=0
```

When a is lost, b can be elected primary with the arbiter's vote. Yet b may **fail to handle the write load** previously served by a.

A new primary must have:

- Sufficient CPU/RAM/IOPS for peak write workload;
- Adequate disk space and oplog;
- Network connectivity to clients;
- Capacity to sustain replication;
- Compatible configuration and version;
- Monitoring and alerting on role changes.

Therefore, `priority` must match **a node's real serving capacity**, not just desired role.

### 16.1. RTO and RPO Must Be Defined

- **RTO (Recovery Time Objective):** maximum acceptable outage before appropriate read/write capability returns.
- **RPO (Recovery Point Objective):** amount of data loss acceptable when an incident occurs.

A PSA set can let **an election succeed** when primary is lost, yet with one data-bearing node left, `w: "majority"` still cannot be satisfied. Thus, RTO for **"having a primary"** differs from RTO for **"succeeding majority writes."**

If lowering to `w: 1` during degradation, RPO risk profile changes. Document this trade-off in operational procedures rather than treating it as a harmless workaround.

## 17. Interaction with `writeConcern` and `readConcern`

### 17.1. Write Concern

Examples:

```javascript
// Primary acknowledgment under w=1.
db.orders.insertOne(
  { orderNo: "A-001" },
  { writeConcern: { w: 1 } }
);

// Require majority acknowledgment.
db.orders.insertOne(
  { orderNo: "A-002" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

`w: 1` generally exhibits lower latency under certain conditions, yet its durability across failover is not equivalent to majority. `w: "majority"` requires enough data copies to confirm; this can raise latency when secondaries lag or disconnect.

`wtimeout` limits how long to wait for write concern, **not acting as an overall timeout for every stage of write processing**; understand error outcomes and uncertain states when using it.

### 17.2. Read Concern Majority

A read with `readConcern: { level: "majority" }` provides guarantees regarding majority-committed data per MongoDB rules.

Conceptual example:

```javascript
db.orders.find(
  { status: "PAID" }
).readConcern("majority");
```

Syntax for setting read concern on cursors/APIs varies by shell/driver and version; with drivers, it is commonly set on collection/database/client or supported operation options. **Do not treat majority read concern as a fixed snapshot across multiple requests**: reads at different moments can still see newly majority-committed data.

An arbiter holds no application data to serve a majority query. It is not a fallback read source.

### 17.3. Majority Commit Point

The **majority commit point** concept clarifies which writes have been confirmed across a majority of data-bearing voting members under replication mechanics. If only one active data copy remains in PSA, the commit point may stop advancing for new writes because no eligible data-bearing secondary exists to confirm them.

This can impact majority read concern and operations relying on majority-committed state. Do not infer from "primary is running and `w:1` writes succeed" that all majority read/write operations remain fully functional.

## 18. Arbiters and Transactions

MongoDB supports multi-document transactions in certain environments/versions. However, deploying a replica set with an arbiter does not mean every transaction behaves identically to an all-data-bearing replica set.

**Especially in PSA**, transactions can face restrictions when certain operations require majority commit or when transactions involve sharding/DDL under server version constraints. In sharded clusters, a shard with an arbiter carries specific limitations for cross-shard transactions.

Key design points:

- Transactions do not turn an arbiter into a data copy;
- A system can have election quorum while lacking data-bearing acknowledgments;
- When cross-shard transactions or majority durability are required, verify topology and exact docs for your MongoDB version;
- Never add an arbiter to solve missing quorum without checking its impact on transaction workloads.

If an application handles payments, inventory deductions, or multi-document order creation, prefer a **proper data-bearing architecture** rather than assuming an arbiter is a cheaper equivalent.

## 19. Inspecting Current Configuration

In `mongosh`, inspect the replica set config:

```javascript
rs.conf();
```

An illustrative config:

```javascript
{
  _id: "rs0",
  version: 7,
  members: [
    {
      _id: 0,
      host: "mongo-a:27017",
      priority: 2,
      votes: 1
    },
    {
      _id: 1,
      host: "mongo-b:27017",
      priority: 1,
      votes: 1
    },
    {
      _id: 2,
      host: "mongo-c:27017",
      priority: 0,
      votes: 1
    }
  ]
}
```

This merely **illustrates relevant fields**, not the full `rs.conf()` output. Real configs contain many other properties, such as settings, horizons, tags, buildIndexes, or version metadata.

Inspect member status:

```javascript
rs.status();
```

Commonly useful details:

| Field/Status | What to Observe |
|---|---|
| `set` | Replica set name |
| `members[].name` | Host/member |
| `members[].stateStr` | `PRIMARY`, `SECONDARY`, `ARBITER`, `RECOVERING`, ... |
| `members[].health` | Health level as observed by the queried node |
| `members[].optime` | Replication progress |
| `members[].lastHeartbeatMessage` | Connectivity/heartbeat incident info |
| `election*` metadata | Election info depending on version |
| `syncSourceHost` / equivalent field | Sync source of a secondary |

Combine status, replication lag, networking, operation latency, and logs. `health: 1` tells only part of the story—insufficient to prove a node can become primary or majority writes will always succeed.

### 19.1. Reading Configuration in a Clear Table

```javascript
const config = rs.conf();

config.members.forEach((m) => {
  printjson({
    host: m.host,
    priority: m.priority,
    votes: m.votes,
    arbiterOnly: m.arbiterOnly === true,
    hidden: m.hidden === true
  });
});
```

If a member omits certain attributes explicitly, understand **MongoDB defaults** when interpreting; do not treat `undefined` blindly as 0. For arbiters, check `arbiterOnly` and actual role in `rs.status()`.

## 20. Controlled Priority Change Example

`rs.reconfig()` commands can trigger an election or force the primary to step down. Therefore, **execute them only with admin privileges, a change plan, and a rollback path**. The commands below illustrate operations in a test environment, not a script to run blindly in production.

Suppose you want to raise mongo-b from priority 1 to 2:

```javascript
const cfg = rs.conf();

const member = cfg.members.find(
  (m) => m.host === "mongo-b:27017"
);

if (!member) {
  throw new Error("Member mongo-b not found");
}

member.priority = 2;

// Caution: may trigger an election or primary switch.
rs.reconfig(cfg);
```

Afterward:

```javascript
rs.conf();
rs.status();
```

Verify:

- MongoDB accepted the configuration;
- Members returned to healthy states;
- Primary role matches policy;
- No significant replication lag exists;
- Writes with the desired write concern still succeed;
- Drivers/clients work after any election.

### 20.1. Changing `votes` Requires Recalculating Quorum

Suppose you want to set a member to `votes: 0`; you must know:

1. How many voting members remain after the change;
2. What the new majority quorum is;
3. Which partitions/failures would lose quorum;
4. Which data-bearing voting members remain to satisfy write majority;
5. Whether enough candidates with priority > 0 remain.

MongoDB restricts how voting members can be added/removed in a single reconfiguration; typically **you must not arbitrarily change multiple voting members in one reconfig command**. For critical topology changes, follow the steps documented for your MongoDB version, verifying after each step.

### 20.2. Never Use `force` to Solve Every Quorum Incident

Some reconfiguration operations support a `force` option for special scenarios. This is an emergency tool carrying configuration/data-loss risks, **not** a routine operational shortcut to "manually appoint a primary" while partitioned.

If a replica set lacks quorum, diagnose failure domains and data first; avoid forcing multiple independent sides into hard-to-recover states.

## 21. Adding an Arbiter: Procedure and Warnings

In a test environment with a running replica set, command example:

```javascript
rs.addArb("mongo-arb:27017");
```

This command adds an arbiter to the replica set (when topology and privileges permit). Yet **adding an arbiter changes the voting quorum mechanism**, not merely adding a process.

Before executing:

1. Confirm the replica set is configured, has a valid primary, and has current quorum.
2. Check the voting member limit.
3. Calculate majority before/after the change.
4. Evaluate constraints regarding `w: "majority"` and implicit default write concern.
5. Check impacts on transaction/sharded workloads.
6. Choose an appropriate failure domain for the arbiter.
7. Provision connectivity, minimum resources, monitoring, and security.
8. Prepare a rollback plan to the old topology if needed.

**Never add an arbiter merely to have "three nodes on a diagram"** when the real need is increasing data copies or continuing majority writes after a data-bearing node fails.

### 21.1. Why Prefer a Real Secondary If Resources Allow?

Instead of:

```text
P + S + A
```

if you can deploy:

```text
P + S + S
```

then the third member both votes and stores data, participating in failover and majority replication under proper conditions. This usually delivers much higher value for applications prioritizing durability and write availability.

Costs of a real secondary include storage, backup/replication bandwidth, CPU/RAM, and operations; base the decision on RPO/RTO requirements and budget.

## 22. Design Examples by Fault-Tolerance Level

### 22.1. Case A: Resource-Constrained Learning Environment

Only two data-bearing machines available, needing to understand elections and practice failover:

```text
P + S + A
```

PSA can be a useful learning model to observe an arbiter's role. Yet state clearly:

- Only two data copies exist;
- When one data-bearing member is lost, majority writes are impacted;
- Does not by default meet production durability SLAs;
- Do not use PSA to replace DR/backup requirements.

### 22.2. Case B: Transactional App Needing Single-Node Loss Tolerance

```text
P + S + S
```

With three data-bearing voting members, losing one member leaves two data-storing nodes and two votes. Under healthy replication, the system can both retain election quorum and satisfy majority writes.

Spread members across sufficiently independent failure domains, verify latency, and ensure secondaries can carry primary load.

### 22.3. Case C: Three Data-Bearing Nodes, Yet One Secondary Cannot Become Primary

```text
P:  priority=2, votes=1
S1: priority=1, votes=1
S2: priority=0, votes=1
```

S2 still provides a data copy and a vote, yet never becomes a candidate. If P is lost, S1 can become primary backed by S2's vote, when eligible.

This design is far sounder than setting both S1 and S2 to priority 0 if automatic failover is required.

### 22.4. Case D: Four Data-Bearing Voting Members

```text
P + S + S + S
V = 4
Q = 3
```

Increasing from three to four votes **does not increase simultaneous vote losses tolerated while keeping quorum**: both tolerate only one absent vote. However, it adds another data copy depending on backup/read-load needs and topology.

Tolerating two voting member losses for election quorum typically requires **at least five** voting members (`V=5`, `Q=3`), while ensuring valid candidates and sufficient data-bearing replicas for the target write concern.

### 22.5. Case E: Multiple Non-Voting Secondaries for Reads

Some systems need extra copies for reporting, analytics, or backups:

```text
P + S + S    (3 voting)
    +
S + S        (2 non-voting, priority=0)
```

Non-voting nodes can isolate read workloads when read preferences and replication lag permit, yet **election quorum still rests on the three voting members**. Avoid mistaking five data copies for five election votes.

## 23. Risks of Zone-Imbalanced Arbiter Configurations

Suppose:

```text
DC-A: Primary + Arbiter
DC-B: Secondary
```

Losing DC-A wipes out both primary and arbiter, leaving DC-B with one vote and unable to elect a new primary. If the main goal is **surviving total loss of DC-A**, this topology fails.

Moving the arbiter to DC-C:

```text
DC-A: Primary
DC-B: Secondary
DC-C: Arbiter
```

improves **zone-distributed quorum**, yet when DC-A or DC-B fails only one data-bearing node remains, and majority writes cannot work as when both were healthy.

To survive losing a zone while still satisfying majority writes, evaluate placing **three data-bearing voting members** across suitable failure domains. However, three data-bearing zones introduce WAN replication latency; measure it before deciding.

### 23.1. Build a Failure Matrix Before Deciding

Build a table:

| Hypothetical Incident | Remaining Voting Members? | Candidate Exists? | Remaining Data-Bearing Members? | `w: "majority"` Satisfied? |
|---|---|---|---|---|
| Primary lost | Depends on topology | Yes/no | How many? | Yes/no |
| Secondary lost | Depends on topology | Does primary remain? | How many? | Yes/no |
| Arbiter lost | Depends on topology | Does primary remain? | How many? | Yes/no |
| Entire rack lost | Votes in that rack disappear | Calculate | Copies in that rack lost | Calculate |
| Entire zone lost | Votes in that zone disappear | Calculate | Copies in that zone lost | Calculate |
| 2/1 network partition | Which side has majority? | On which side? | How many copies per side? | Depends on side and write concern |

Analyzing **by failure domain** is far more valuable than the rule "an odd node count is fine" whenever a rack/region can knock out multiple hosts together.

## 24. Failover Testing Must Measure Real Operations

A failover drill should cover at least three parts:

1. **Election:** which member was elected primary? How long did it take?
2. **Write availability:** how did `w: 1` and `w: "majority"` writes behave during degradation?
3. **Data durability:** were any ACKed records missing after failover? Did outcomes match the write concern level?

Example staging test skeleton:

```javascript
// Read topology before test.
rs.status();

// Write sample with majority.
db.failoverLab.insertOne(
  {
    _id: "before-failure",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);

// After inducing a controlled incident:
// 1. Check new primary/quorum.
// 2. Attempt writing with the same write concern.
// 3. Read back sample; log timings and errors.
```

**Never arbitrarily stop production nodes** just to test. Drills require a plan, operational approval, observers, monitoring tools, and a recovery plan.

### 24.1. Error Outcome Does Not Necessarily Mean Record Was Not Written

When a client receives a write concern timeout:

- The write may already have applied on the primary without reaching the needed ACK level;
- Retrying can create duplicates if the application lacks a fixed ID or idempotency mechanism;
- An operation may have majority-committed while the client lost the response due to network error;
- Transaction/retryable-write behavior depends on driver, server, and application usage.

Therefore, business logic needs an **operation ID**, suitable unique keys, retryable writes, and reconciliation. Never write code saying "on timeout, just insert a new record with a fresh ID" if it can create duplicate orders/payments.

## 25. Observing Key Operational Metrics

| Metric Group | What to Watch |
|---|---|
| Elections | Election count, primary stepdowns, reasons for primary switch |
| Quorum | Disconnected members, ping/heartbeats, no-primary duration |
| Replication | Secondary replication lag, oplog window, sync errors |
| Write concern | `wtimeout` rate, write latency by concern level |
| Durability | Majority commit lag, rollback events, journal/disk |
| Capacity | CPU, RAM, IOPS, network throughput, and connection counts |
| Arbiter | ARBITER state, heartbeats, network reachability |
| Application | Retry/error rate, p95/p99 latency, transaction aborts |
| Maintenance | Config changes, versions, member health, and backup schedule |

When an arbiter exists, alert whenever a **data-bearing secondary is lost**, even though the primary stays up and the arbiter preserves votes. That state easily creates the illusion "the cluster is healthy because there is a primary" while majority write capability has degraded.

### 25.1. Two Distinct Types of Alerts

**Alert A — Election quorum degradation**

> Replica set risks losing primary capability if one more voting member fails.

**Alert B — Majority write degradation**

> Insufficient healthy/synced data-bearing voting members remain to complete `w: "majority"` writes within SLA.

Both alerts must be distinguished because `P + A` in PSA might **not** fire Alert A in the sense of "quorum lost," yet must fire Alert B.

## 26. Configuration Changes and Upgrades: Safety Principles

When changing replica set topology or configuration:

1. **Record current configuration** and each member's status.
2. **Calculate quorum before and after** the change.
3. **Verify primary candidates**, especially nodes with priority > 0 and votes = 1.
4. **Assess durability**, including data-bearing voting member count and majority write availability.
5. **Assess failure domains**, avoiding losing multiple votes from one fault.
6. **Check default read/write concerns** and application commands/transactions.
7. **Execute step by step** per version docs; never alter multiple votes arbitrarily.
8. **Monitor replication catch-up** and avoid reconfig while unstable.
9. **Verify post-change** with `rs.conf()`, `rs.status()`, and valid test reads/writes.
10. **Have a rollback plan** and abort criteria if SLA degrades.

Be especially cautious with changes such as:

- Lowering a member's `votes` from 1 to 0;
- Setting too many candidates to priority 0;
- Adding an arbiter;
- Moving the highest priority to another network region;
- Removing the sole secondary contributing to majority acknowledgment;
- Changing multiple voting members within the same phase.

A setup that looks balanced on a diagram can still become less fault-tolerant after a quorum update.

## 27. Hands-On Exercises

### Exercise 1 — Calculate Election Quorum

For `V = 1, 2, 3, 4, 5, 6, 7`, calculate:

1. Majority `Q`.
2. Maximum voting members that can be absent while retaining quorum.
3. Why increasing voting members from 3 to 4 does not increase simultaneous vote losses tolerated.
4. Why non-voting secondaries do not change `Q`.

### Exercise 2 — Distinguish Priority and Votes

Suppose:

```text
A: priority=4, votes=1
B: priority=1, votes=1
C: priority=0, votes=1
```

Answer:

- Which nodes can become primary?
- Which nodes vote?
- If A stops, do B + C have enough quorum?
- If only C remains, can there be a primary?
- If `votes=0` is set on C, what is the impact?

### Exercise 3 — PSA and Write Majority

A PSA set has P, S, and A. S loses connectivity while P and A still communicate well.

1. Is there enough election quorum?
2. Can the primary stay active?
3. Can `w: 1` writes still succeed?
4. How are `w: "majority"` writes affected?
5. If P fails next before S receives the `w: 1` writes, what is the data risk?

### Exercise 4 — Compare PSS with PSA

Build a comparison table of PSS and PSA covering:

- Number of voting members;
- Number of data-bearing members;
- Election quorum;
- Impact of losing one secondary;
- Impact of losing primary;
- Ability to perform majority writes after one failure;
- Storage/replication cost;
- Ability to serve reads on secondaries.

Explain why **having the same three voting members does not mean having the same data durability**.

### Exercise 5 — Priority 0 Causing Failover Failure

Configuration:

```text
A: priority=3, votes=1
B: priority=0, votes=1
C: priority=0, votes=1
```

When A is lost, B and C hold two votes. Why can no primary still be elected? Propose a new configuration allowing B to fail over while still preferring A in steady state.

### Exercise 6 — Arbiter and Failure Domain

There are two data-bearing nodes in DC-A and DC-B, plus one arbiter in DC-A.

1. Losing DC-A leaves which votes?
2. Can DC-B elect a primary on its own?
3. If the arbiter moves to DC-C, how does election availability change?
4. Why is a three-DC setup with an arbiter still not equivalent to three data-bearing DCs?

### Exercise 7 — Compute RTO/RPO by Write Concern

An order application uses PSA. When the secondary is lost, ops proposes switching from `w: "majority"` to `w: 1` to keep writes flowing.

Describe:

- Impact on write latency and availability;
- Impact on rollback/data-loss risk;
- Approval conditions required before lowering write concern;
- How to design idempotency/retries for the order-creation endpoint;
- When the system must reject incoming transactions rather than accepting writes with insufficient copies.

### Exercise 8 — Analyze Network Partition

A PSS set has:

```text
A: P
B: S
C: S
```

The network splits A on one side, B and C on the other. Answer:

1. Which side retains quorum?
2. Which side can elect a primary?
3. What happens to old primary A once it realizes quorum is lost?
4. What errors might a client connected directly to A encounter?
5. Why is retry logic still needed even though elections prevent sustained split-brain?

### Exercise 9 — Inspect Config in `mongosh`

In an authorized environment, run:

```javascript
rs.conf();
rs.status();
```

Record for each member:

- Host;
- Role/state;
- `priority`;
- `votes`;
- `arbiterOnly`;
- Health and replication lag.

Calculate `V` and `Q`, and identify which data-bearing candidates can become primary. Do not modify production configuration in this exercise.

### Exercise 10 — Design a System Tolerating Single-Region Loss

An application spans two regions and requires:

- Never losing majority-acknowledged records during normal failover;
- Continuing majority writes when one data-bearing member is lost;
- Primary preferred close to write traffic;
- Data copies in independent failure domains.

Compare PSA with PSS and propose node placement across regions. Explain trade-offs in network latency, replication bandwidth, cost, and quorum.

## 28. MongoDB Reference Documentation

- [MongoDB Replication](https://www.mongodb.com/docs/manual/replication/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Replica Set Member Priority](https://www.mongodb.com/docs/manual/core/replica-set-priority-0-member/)
- [Replica Set Arbiters](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/)
- [Replica Set Member Votes](https://www.mongodb.com/docs/manual/core/replica-set-voting/)
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Set Default RW Concern](https://www.mongodb.com/docs/manual/reference/command/setDefaultRWConcern/)
- [Reconfigure Replica Set](https://www.mongodb.com/docs/manual/reference/method/rs.reconfig/)
- [Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/)

## Conclusion

In a MongoDB replica set, **`priority`**, **`votes`**, and **`arbiter`** solve **three distinct problems**.

- **`priority`** governs eligibility and relative preference to become primary; high priority **adds no extra votes**, while `priority: 0` bars a node from becoming primary.
- **`votes`** determines which members participate in election quorum; adding a non-voting secondary does not raise quorum, while changing votes directly alters fault tolerance.
- **Arbiter** supplies an election vote yet **stores no data**, so it cannot substitute for a secondary in satisfying majority write concern or recovering data.

Both **PSS** and **PSA** share three votes and an election quorum of two, yet differ fundamentally in **number of data copies**. In PSA, a **primary + arbiter** state can retain enough election votes while **lacking enough data-bearing members** to complete `w: "majority"` writes. That is why replica set design must never stop at asking "how many nodes are left?"—it must ask **how many votes remain, how many data copies remain, which primary candidates remain, and which write concerns can actually be satisfied**.

When a design must survive losing one node while continuing majority writes, **three data-bearing voting members** is usually a far sounder starting point than two data-bearing members plus an arbiter. Final decisions must account for RPO/RTO, network partitions, replication lag, standby primary capacity, failure domains, and failover drill results. **Quorum protects leadership; data copies and write concern protect the written data.**
