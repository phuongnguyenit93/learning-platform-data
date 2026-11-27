# Quorum, Voting Members, and Conditions for Having a Primary in a MongoDB Replica Set

A **replica set** is a group of `mongod` processes that jointly maintain copies of a dataset. In normal operation, a replica set has **one primary** that receives write operations, while **secondaries** replicate changes from the primary and can become primary when an incident occurs. To prevent the system from arbitrarily creating two independent primaries during a network split, MongoDB uses **majority-vote-based elections**.

The three core questions of this lesson are:

1. **What is the quorum?** How many votes are required to elect a primary?
2. **Who has a vote?** What roles do data-bearing members, non-voting secondaries, and arbiters play?
3. **When is there a primary?** Majority is a necessary condition, yet why can a replica set still fail to elect a primary even when enough nodes remain?

Understanding these three questions helps explain familiar scenarios: a two-node replica set loses its primary when one node fails; a three-node replica set typically tolerates one node failure; a topology with two data nodes and one arbiter still has limitations with `w: "majority"` writes; a `priority: 0` node can vote but cannot become primary.

## 1. Primary, Secondary, Arbiter, and Votes

Members in a replica set do not necessarily share the same voting rights and eligibility to become primary.

| Member Type | Stores Data? | Can Vote? | Can Become Primary? |
| --- | --- | --- | --- |
| Regular data-bearing member, `votes: 1, priority > 0` | Yes | Yes | Yes, if eligible and wins election |
| Data-bearing member `votes: 1, priority: 0` | Yes | Yes | No |
| Non-voting secondary `votes: 0, priority: 0` | Yes | No | No |
| Arbiter `arbiterOnly: true` | Does not store application data copy | Yes, in standard configurations | No |

The **primary** itself is also a data-bearing voting member currently holding the leadership role; it can lose this role when it no longer has a majority, encounters a process failure, is reconfigured, or when a new election occurs.

A **secondary** replicates the oplog and maintains data. A secondary can be designated ineligible to become primary while still remaining useful for reads, backups, or data processing according to system design.

An **arbiter** participates in voting but holds no data and cannot receive data to acknowledge writes like a secondary. Therefore, adding an arbiter is not equivalent to adding a safe data copy.

### Two Attributes to Distinguish: `votes` and `priority`

In a replica set configuration, a data-bearing member can have:

```javascript
{
  _id: 1,
  host: "mongo-b.example.net:27017",
  votes: 1,
  priority: 0
}
```

This is a **voting secondary** that cannot run for primary. Conversely:

```javascript
{
  _id: 2,
  host: "mongo-c.example.net:27017",
  votes: 0,
  priority: 0
}
```

the member can still store and replicate data, but has **no vote** and **cannot become primary**. In MongoDB configuration, a member with `votes: 0` must have `priority: 0`; you cannot set `votes: 0, priority: 1` and expect it to become primary.

`priority` indicates the relative preference to become primary among eligible members. **Priority does not turn one vote into two votes**, does not change the quorum formula, and does not allow a minority side to win an election.

## 2. Election Quorum Is a Majority of Configured Votes

Suppose a replica set has `V` **voting members**, each having either one vote or zero votes. The minimum number of votes required for a majority is:

```text
majorityVotes = floor(V / 2) + 1
```

This is a **strict majority**, meaning **greater than half**, not "equal to half".

| Voting members `V` | Minimum quorum | Maximum voting members that can be lost while retaining enough votes? |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

The table assumes the remaining members **can communicate with each other** and there is **at least one eligible data-bearing voting member**. The number of running nodes alone does not guarantee a primary if the nodes are partitioned into unreachable groups or all candidates have `priority: 0`.

### Key Point: The Denominator Does Not Shrink Automatically When a Node Fails

With a three-voting-member configuration, quorum is **2**. If one node fails, the required vote count remains **2**; it does not drop to one just because only two nodes are currently alive. With a five-voting-member configuration, quorum remains **3** when two nodes fail.

The quorum condition is based on the **effective voting configuration**, not the number of `mongod` processes you happen to see online. Changing the voting members configuration is an explicit administrative operation, not an automatic adjustment after every network failure.

### Why Majority Prevents Two Factions from Simultaneously Claiming Authority

An important property of any two majority sets is that **they always share at least one vote in common**.

```text
Replica set has 5 votes, quorum = 3

Faction A has 3 votes: A, B, C
Faction B has 3 votes: C, D, E

The two majority sets intersect at C.
```

In the election protocol, members regulate voting by term and current state. The intersection property of quorums combined with the term/vote mechanism helps the replica set avoid maintaining two valid primaries for the same election term under typical network partition scenarios.

**Do not interpret this as "there is never a period where an old primary has not yet realized it lost majority."** When the network fluctuates, a node may briefly retain stale state before detecting the failure and stepping down. Applications must handle errors/retries and use appropriate write concerns; the majority mechanism is the foundation for consistency, not a guarantee that every client sees role transitions instantaneously.

## 3. Conditions for a Replica Set to Have a Primary

A majority of votes is a **necessary condition**, but not the only condition. For an election to succeed, the following are required:

1. **An eligible data-bearing member to run as candidate**: a member permitted to become primary, typically with `votes: 1`, `priority > 0`, in an appropriate state, and eligible under the election protocol.
2. **The candidate communicates with and receives a majority of votes** from the voting members under the effective configuration.
3. **The candidate satisfies election rules on state and data freshness**; a secondary that is too far behind, not in an appropriate state, or undergoing initial sync cannot arbitrarily become primary merely because it receives network signals.
4. **No corresponding election barriers exist**, such as invalid configuration/term, members restricted from running, or members holding enough votes being unable to communicate.

During normal operation, the primary must maintain connectivity with a **majority of voting members**. If the primary is isolated from quorum within the failure detection window, it cannot validly remain primary and will step down.

```text
Replica set with 3 voting data members

      A (primary)
      /           \
 B (secondary)  C (secondary)

Quorum = 2:
  A + B: sufficient
  A + C: sufficient
  B + C: sufficient to elect a new primary if an eligible candidate exists
  A alone: insufficient
```

**A node having a TCP connection to a client does not mean the replica set currently has a writable primary.** In an application, writability is determined by the replica set protocol and the driver's server selection result, not simply by pinging a network port.

### Eligibility to Run Differs from the Right to Vote

Suppose the configuration is:

```text
A: votes=1, priority=2
B: votes=1, priority=0
C: votes=1, priority=0
```

Quorum is still **2**. However, **only A** is eligible to become primary because B and C have `priority: 0`. If A stops operating, B and C still have two votes, meaning **they still have quorum arithmetically**, but **there is no eligible candidate**. As a result, the replica set cannot automatically elect a new primary.

This is a concrete illustration of the statement: **"Having quorum" does not always mean "there will be a primary."**

## 4. Practicing Quorum Calculation for Common Topologies

### 4.1. One Voting Data Member

```text
A (voting, electable)

V = 1, quorum = 1
```

A can elect itself primary in an appropriate configuration. However, this is **not high availability**: when A fails, there is no replacement that can become primary. Adding a `votes: 0` secondary does not solve election failover either if A is the sole voting member.

### 4.2. Two Data-Bearing Voting Members

```text
A (primary) <----> B (secondary)

V = 2, quorum = 2
```

If both A and B can communicate, a primary can be maintained. If A fails, B has only **one out of two votes** and cannot elect itself primary. If B fails, A no longer sees a majority of votes and cannot continue holding primary stably either.

This is why **a two-voting-member replica set cannot tolerate the loss of one voting member in terms of quorum**. This setup easily creates a false sense of "already having replication so it is highly available," yet data replication and election capability are two distinct properties.

### 4.3. Three Data-Bearing Voting Members: P–S–S

```text
               A (primary)
               /         \
    B (secondary) --- C (secondary)

V = 3, quorum = 2
```

One node fails or is isolated from the remaining two:

- If **C fails**, A and B have two votes; primary A can continue operating as long as other conditions are met.
- If **A fails**, B and C have two votes; one of them can be elected primary **if an eligible candidate exists with suitable data/state**.
- If **only A remains**, A lacks majority and cannot remain a valid primary.

P–S–S is a foundational topology for understanding high availability: three data-bearing voting members provide both majority election capability when one node is lost and additional data copies.

### 4.4. Four Voting Members

```text
A, B, C, D
V = 4, quorum = 3
```

If two members fail simultaneously or the network splits 2–2, **neither side reaches quorum 3**. Adding a fourth member to a three-voter topology increases node cost, yet **does not increase the number of tolerable voting-member failures** from 1 to 2. Therefore, an odd number of voting members is usually preferred when designing quorum, provided other requirements align.

### 4.5. Five Voting Members

```text
A, B, C, D, E
V = 5, quorum = 3
```

The replica set can still achieve quorum when **two voting members lose connectivity** with the rest, provided the remaining three members can communicate and include a suitable candidate. This is an example of a topology that tolerates more voting member failures than a three-node setup, though it does not mean every five-node placement tolerates two failures **in any failure domain**.

If three voting members are placed in the same infrastructure zone and that zone fails, leaving only two votes in other zones means quorum is lost. The member count and their placement across failure domains must be considered together.

## 5. Network Partition: Majority Side and Minority Side

Suppose a five-voting-member replica set splits into two sides:

```text
Region 1: A --- B --- C      (3 votes)

         DISCONNECTED

Region 2: D --- E            (2 votes)
```

With quorum = 3:

- Side A–B–C **has quorum** and can maintain/elect a primary if an eligible candidate exists.
- Side D–E **lacks quorum**, so it must not elect a primary even though both members are running normally.
- If the old primary is on side D–E, it must step down upon realizing it lost majority; the three-node side can proceed with an election once conditions are satisfied.

The key point of **quorum** is not "as long as fewer than half the nodes fail everything works," but rather **there must be a group with a majority that can still communicate and conduct elections**.

### A Network Partition Is Not Like a Node Shutdown

A `mongod` node is still running, yet:

- Does not receive heartbeats from certain other members.
- Does not exchange election information on time.
- May be unable to reach the data-bearing members needed for write concern.

Looking at a dashboard showing only that the process is alive is insufficient to conclude the replica set is healthy. You must check **inter-member connectivity**, not just process status or port `27017`.

### Role Transition Does Not Happen at a Single Global Instant

Failure detection, heartbeat timeouts, elections, and topology updates all take time. Some write requests may temporarily fail with primary/replication-related errors; the driver may need to rediscover the primary and retry according to configuration.

Do not claim that losing one node means a new primary will appear **immediately** or always in a fixed number of seconds. Actual time depends on topology, network conditions, replication lag, `electionTimeoutMillis`, and candidate selection mechanisms.

## 6. Majority Does Not Mean Every Member Must Be Online

The following two conditions are different:

```text
All members online:
    5/5 online

Enough quorum to elect primary:
    3/5 voting members can exchange votes
```

A replica set does not require every secondary to be online to have a primary. A three-voting-member replica set can operate with two members; a five-voting-member replica set can operate with three members, within election constraints.

However, quorum is not a way to "ignore all risk": if only the minimum required votes remain, one more failure can cause the system to lose its primary. When in a degraded state, prioritize restoring connectivity/replication and avoid maintenance operations that risk losing votes.

### Voting Is Not Equivalent to Data Synchronization

A node with `votes: 1` has the right to participate in deciding who becomes primary. That alone does not say:

- That the node has the latest data.
- That the node can accept client writes.
- That the node stores a copy of the data.
- That a write operation has been durably acknowledged on a majority of data-bearing members.

These properties must be analyzed separately, especially when the configuration includes an arbiter or a lagging secondary.

## 7. Role of `priority` in Elections

MongoDB allows setting a higher priority for a member generally preferred to be primary:

```javascript
{
  _id: 0,
  host: "mongo-a.example.net:27017",
  votes: 1,
  priority: 2
}
```

Compared to:

```javascript
{
  _id: 1,
  host: "mongo-b.example.net:27017",
  votes: 1,
  priority: 1
}
```

In appropriate circumstances, the replica set can prefer member A over B as primary. However:

- A still needs a **majority of votes**; priority 2 does not equal two votes.
- A must be **eligible for election**; it cannot be undergoing initial sync and still become primary.
- B can still be elected when A is unavailable and B meets the requirements.
- Priority settings can trigger unintended primary transitions if configured without considering network quality and node placement.

### `priority: 0` Can Still Vote

Example:

```text
A: votes=1, priority=2    eligible candidate
B: votes=1, priority=1    eligible candidate
C: votes=1, priority=0    votes only, non-candidate
```

Quorum = 2. If A fails, B and C can vote for B to become primary, even though C can never become primary. This differs from configuring `B: votes=0`, in which case B cannot contribute election votes.

When designing a member solely for reads or backups, consider whether it should vote, rather than just setting `priority: 0` and assuming it has been excluded from quorum calculations.

## 8. `votes: 0`: A Data Copy That Does Not Help Reach Quorum

Suppose there are three data-bearing members:

```text
A: votes=1, priority=1
B: votes=1, priority=1
C: votes=0, priority=0

Total voting members V = 2
Quorum = 2
```

Although there are **three data copies**, the replica set still has only **two votes**. If A is lost, B and C remain as two data-bearing nodes yet hold only **one vote** (B), so a primary cannot be elected.

This illustrates two independent axes:

| Axis | Question |
| --- | --- |
| **Data replication** | How many data-bearing members are storing and syncing data? |
| **Voting rights** | How many voting members exist, and how many votes remain reachable? |

A non-voting secondary can be very useful for read, analytics, or backup needs by design, but **does not fix the lack of quorum** in a configuration with only two voting members.

### Maximum Number of Voting Members

MongoDB enforces a limit on voting members in a replica set: **at most seven voting members**; a replica set can include additional non-voting members within the total member limit supported by the version. Distinguish the total number of members in `rs.conf().members` from the number of members with `votes: 1`.

Do not turn every secondary read node into a voting member just to "increase safety." More voters alter the quorum, election complexity, and failure domain distribution requirements; choose voting members based on actual availability design.

## 9. Arbiter: Adding a Vote Without Adding a Copy

An arbiter is commonly discussed in the **P–S–A** topology:

```text
        P (primary, data)
        /                \
S (secondary, data) --- A (arbiter)

P: votes=1
S: votes=1
A: votes=1

V = 3, quorum = 2
```

An arbiter participates in elections, stores no user data, and cannot become primary. When you do not want or cannot yet add a third data-bearing member, an arbiter allows a three-vote group to achieve quorum with two connected members.

### Scenarios in P–S–A

| Scenario | Reachable votes | Election quorum? | Key takeaway |
| --- | --- | --- | --- |
| P, S, A all healthy | 3 | Yes | Two data copies and one arbiter |
| A fails; P and S remain | 2 | Yes | P and S still have enough votes |
| S fails; P and A remain | 2 | Yes | Can maintain primary, though only P holds active data |
| P fails; S and A remain | 2 | Yes | S can be elected if eligible |
| Only P remains | 1 | No | Cannot maintain a valid primary |
| Only S remains | 1 | No | Cannot elect a primary |

**The P + A scenario is very prone to confusion:** two votes suffice for elections, so a primary can exist, **yet there are not enough data copies to acknowledge writes with `w: "majority"`** in a standard P–S–A topology. The arbiter has no data to receive and record changes.

When only one data-bearing node remains active, `w: 1` writes can be acknowledged by the primary but face data loss/rollback risk if that node fails before other copies sync. With `w: "majority"`, write operations may have to wait or fail with a timeout when insufficient data-bearing members satisfy the requirement.

### P–S–A Is Not Equivalent to P–S–S

| Property | P–S–S | P–S–A |
| --- | --- | --- |
| Total voting members | 3 | 3 |
| Election quorum | 2 | 2 |
| Data-bearing members | 3 | 2 |
| Has a member storing no data | No | Yes, arbiter |
| When one data-bearing secondary is lost | P and the other S remain to replicate/ack majority | Only P and A may remain, insufficient data-bearing nodes to ack majority |
| Tolerates losing one voting member for quorum | Yes | Yes |
| Data redundancy level | Higher in this configuration | Lower |

An arbiter is not a default equivalent to a real secondary. For high data durability requirements, consider **three data-bearing voting members** when infrastructure permits.

### Do Not Infer Default Write Concern Solely from Node Count

MongoDB has **implicit default write concern** rules depending on version and configuration, especially when a replica set has an arbiter. Therefore, never assume every P–S–A system always uses `w: "majority"` if the client does not specify it.

Critical applications must **explicitly declare write concern**, verify the actual configuration, and understand the impact when a secondary or arbiter becomes unavailable.

## 10. Election Majority Differs from Write Concern `majority`

The word `majority` appears in two distinct contexts:

**A. Election majority (quorum):**

> Are there enough votes from voting members to maintain or elect a primary?

**B. Write concern `w: "majority"`:**

> Has a write operation been acknowledged as replicated to the required number of data-bearing voting members?

The difference is that **an arbiter has a vote but does not replicate data**. In topologies with only data-bearing voting members, these two kinds of majority can easily be conflated as the same thing. In P–S–A, the distinction is critical.

```text
P - S - A

P online, S disconnected, A online

Votes:
  P + A = 2/3      -> still has quorum

Copies able to acknowledge writes:
  P has data
  A holds no data
  S is disconnected
                    -> w:"majority" cannot complete normally
```

### Example Write Request with Majority

In `mongosh` on an appropriate replica set:

```javascript
db.orders.insertOne(
  {
    orderCode: "ORD-1001",
    status: "paid",
    total: 150
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

`wtimeout: 5000` instructs not to wait indefinitely if the write acknowledgment condition is not met within that duration. **A write concern timeout does not prove the operation was not written on the primary.** It may already have been applied on some nodes without meeting the requested acknowledgment level; the application needs appropriate response handling, retries, and business idempotency.

This example is suitable only for an `orders` collection and a lab environment with a primary. In production, do not run illustrative insert code carelessly and do not change application write concern merely to test failover.

### Comparing `w: 1` and `w: "majority"`

| Property | `w: 1` | `w: "majority"` |
| --- | --- | --- |
| Primary acknowledgment level | Primary acknowledges per write concern | Required data-bearing voting members acknowledge |
| Depends on secondary to ack | Does not require ack from secondary | Typically yes, depending on topology and majority conditions |
| When primary finishes writing but secondary is lost | Can still ack | Can wait or time out |
| Protection against rollback during failover | Weaker | Stronger for writes that achieved majority |
| Cost/latency | Can be lower | Can be higher due to waiting for replication |

`w: "majority"` **does not guarantee writes occur instantaneously across the entire replica set**, and does not replace transactions when multiple documents must change as a single unit. Additional journaling policies, timeouts, and client-side error handling are needed for real durability requirements.

### Read Concern Is Not an Election Condition

`readConcern: "majority"` relates to the properties of readable data and the majority commit level; it **does not grant extra votes** and does not turn a secondary into a primary. Likewise, `readPreference: "secondary"` is merely a choice of where to read when the application permits, and does not resolve a lack of quorum for writes.

## 11. What Happens When the Primary Loses Contact with the Majority?

Suppose a three-voting-member replica set `A, B, C`, with A initially primary. The network splits:

```text
A (old primary)      |       B --- C
 1 vote              |       2 votes
                     |
               disconnected
```

General progression:

1. A may still consider itself primary for a brief period before detecting the loss of quorum.
2. A cannot validly maintain primary authority while disconnected from the majority; it will step down per the replica set mechanism.
3. B and C have a 2/3 quorum. An eligible member can win the election and become the new primary.
4. When the network reconnects, A must reconcile with the new state/term. Old writes **not yet majority committed** may need to be rolled back if they conflict with the chosen history.

Therefore, business requirements should not rely solely on a `w: 1` response and assume data is guaranteed to survive failover. For critical writes, choose an appropriate write concern and design retries/idempotency.

### Not Every Loss of Primary Has the Same Root Cause

Having no primary can result from:

- **Lack of quorum** due to lost or network-partitioned voting members.
- **Having quorum but no eligible candidate**: all remaining nodes have `priority: 0`, are undergoing initial sync, or fail election criteria.
- **Candidates failing freshness/state eligibility** per election rules.
- **Currently mid-election**, not yet finished choosing a new primary.
- **Unintended configuration**: voter count, priority, arbiter, or reconfiguration altering required conditions.

Thus, you must analyze **individual member states** and **voting member configuration**, not merely count how many `mongod` processes are still running.

## 12. Election Time, Heartbeats, and Terms

Replica set members exchange **heartbeats** to monitor state and reachability. When the primary is lost or unresponsive, eligible nodes can start an election according to timeouts and active protocol rules.

In the replica set configuration there is a `settings.electionTimeoutMillis` property, whose default value is typically **10,000 ms** if unchanged. However, **do not turn that number into a 10-second failover SLA**: failure detection, election attempts, data evaluation, and driver reconnection can all cause actual time to differ.

### Terms Distinguish Election Epochs

Replica sets use **terms** to represent election epochs. A new term helps members recognize new leadership state and prevents stale votes from being treated as still valid. During diagnostics, fields like `term`, `electionDate`, or state transition reasons may appear depending on the API and version.

You do not need to memorize every internal variable to answer "why is there no primary": first check quorum, candidate eligibility, and connectivity. Then dig deeper into heartbeats, terms, and election logs if the issue remains unclear.

### Replication Lag Also Matters

A secondary that just restarted or is lagging may not be immediately electable when the primary fails. Election safety requires candidates to meet data and state conditions set by MongoDB. Therefore, having enough voting members on paper is not enough; you must monitor **replication health** to know whether an eligible candidate will be available during failover.

## 13. Illustrative Replica Set Configurations

The examples in this section are **learning configurations**, not commands recommended to run directly on an active replica set. Hostnames must exist and resolve via DNS, `mongod` processes must be started with the same replica set name, inter-member connectivity must be open, and security must be properly configured.

### 13.1. Three Data-Bearing Voting Members

```javascript
// Only for a lab environment NOT yet initiated
rs.initiate({
  _id: "rsLearning",
  members: [
    {
      _id: 0,
      host: "mongo-a.example.net:27017",
      votes: 1,
      priority: 2
    },
    {
      _id: 1,
      host: "mongo-b.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-c.example.net:27017",
      votes: 1,
      priority: 1
    }
  ]
})
```

Meaning:

- **Three voting members** → quorum = 2.
- **All three hold data** → three data-bearing members.
- **All three have positive priority** → can run as candidates when conditions are met.
- A is preferred via `priority: 2`, but **does not have two votes**.

This configuration is an example of having at least two secondaries **eligible to run** when the primary is lost. In production, distribution across network regions/availability zones and latency policies determine real fault tolerance.

### 13.2. Two Data-Bearing Members and One Arbiter

```javascript
// Structural illustration only; do not re-initiate on the same cluster
{
  _id: "rsWithArbiter",
  members: [
    {
      _id: 0,
      host: "mongo-a.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 1,
      host: "mongo-b.example.net:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-arb.example.net:27017",
      arbiterOnly: true,
      votes: 1,
      priority: 0
    }
  ]
}
```

This is a P–S–A structure with three votes but only **two data copies**. If one data-bearing member is lost, the remainder may satisfy election quorum with the arbiter yet fail to guarantee `majority` write acknowledgment.

### 13.3. A Secondary That Votes but Cannot Become Primary

```javascript
{
  _id: 2,
  host: "mongo-report.example.net:27017",
  votes: 1,
  priority: 0
}
```

This member **can contribute a vote to elect another member**. If it needs to be excluded completely from voting quorum:

```javascript
{
  _id: 2,
  host: "mongo-report.example.net:27017",
  votes: 0,
  priority: 0
}
```

The two configurations result in **different numbers of voting members**, so you cannot simply change `votes` on a live replica set without planning quorum and reconfiguration impacts.

## 14. Checking Votes and Primary in `mongosh`

The following read-only config/status commands are useful during investigation, provided the account has appropriate privileges.

### 14.1. View Configuration and Voting Members

```javascript
rs.conf()
```

Extract only the key fields:

```javascript
const cfg = rs.conf();

const members = cfg.members.map(member => ({
  id: member._id,
  host: member.host,
  votes: member.votes,
  priority: member.priority,
  arbiterOnly: member.arbiterOnly === true
}));

printjson(members);
```

To calculate quorum from a standard configuration:

```javascript
const config = rs.conf();

const votingMembers = config.members.reduce(
  (count, member) => count + (member.votes === 1 ? 1 : 0),
  0
);

const electionQuorum = Math.floor(votingMembers / 2) + 1;

printjson({
  configuredMembers: config.members.length,
  votingMembers,
  electionQuorum
});
```

This snippet assumes members have explicit `votes` values in the configuration and inspects a normal steady-state config. If the server is currently in a **reconfiguration phase or has a newly added member**, also cross-check the majority/count fields reported by the server in the current state; do not treat a hand-written sum as the sole source of truth during every transition.

### 14.2. View Replica Set Status

```javascript
rs.status()
```

In many versions, `rs.status()` provides fields such as:

| Field | Interpretation |
| --- | --- |
| `set` | Replica set name |
| `myState` | State of the member where the command was run |
| `members[].name` | Host/port of the member |
| `members[].stateStr` | Role/state such as `PRIMARY`, `SECONDARY`, `ARBITER`, `RECOVERING` |
| `members[].health` | Health/connectivity indicator from the queried node's perspective |
| `members[].optime` | Replication progress info in the format reported by the server |
| `term` | Election term, when reported |
| `majorityVoteCount` | Majority vote count per server in versions that expose this field |
| `writeMajorityCount` | Server-reported write majority threshold, when present |
| `votingMembersCount` | Voting member count per server, when present |

JSON shape and field names can vary by version; do not rely on every field existing in every system.

For a compact table view:

```javascript
const state = rs.status();

printjson(state.members.map(member => ({
  name: member.name,
  state: member.stateStr,
  health: member.health,
  optimeDate: member.optimeDate
})));
```

`health` reflects the perspective of the queried node, not a cluster-wide network verification from every member. During a partition, nodes on opposite sides can have **different views of connectivity**.

### 14.3. Ask Whether a Node Is the Writable Primary

```javascript
db.adminCommand({ hello: 1 })
```

The response may include fields such as `setName`, `isWritablePrimary`, `secondary`, `primary`, and `hosts`. `isWritablePrimary: true` indicates the node reports itself as writable primary per its state.

When a driver connects to a replica set, selecting the primary normally relies on the driver's topology discovery/monitoring mechanism; do not implement it by pinging a random node yourself and hard-coding that it will remain primary forever.

### 14.4. Recognizing When There Is No Primary

If none of the members reachable by the client report `isWritablePrimary: true`, or the driver reports no writable primary found within the server selection window, possibilities to check include:

1. Loss of majority of voting members or network split.
2. No eligible candidate to become primary.
3. System is mid-election.
4. Connectivity between client and primary is blocked even though the replica set internally has a primary.
5. Incorrect URI/hostnames/replica set name causing the driver to discover topology wrongly.

Do not simply conclude "database down" just because a secondary answers `hello` queries while refusing writes. The issue may lie in primary authority/quorum rather than all MongoDB processes being stopped.

## 15. Designing Voting Topology Across Failure Domains

Suppose three voting members are placed across three availability zones:

```text
Zone A: mongo-a (1 vote)
Zone B: mongo-b (1 vote)
Zone C: mongo-c (1 vote)

Quorum = 2
```

Losing one zone still leaves two reachable votes, provided the network between the remaining two zones works and an eligible candidate exists.

Conversely:

```text
Zone A: mongo-a, mongo-b, mongo-c   (3 votes)
Zone B: mongo-d                      (1 vote)
Zone C: mongo-e                      (1 vote)

Quorum = 3
```

Although there are five voting members, if all of Zone A fails, only two votes remain in B and C, failing to reach quorum. Thus, "five nodes tolerate two node failures" **does not mean** "any single zone failure can be tolerated."

### Choosing Topology by Failure Domain

Several principles:

- Place voting members across independent failure domains whenever possible.
- Do not place a majority of votes on infrastructure sharing a single point of failure if you must tolerate that infrastructure failing.
- Evaluate **network latency and reliability** between members: a distant node can spread risk yet also increase timeout risk and replication lag.
- Verify whether the **surviving majority side** still has an **electable candidate** and enough data-bearing members for your target write concern.
- Do not equate an arbiter with a data-bearing vote when calculating data redundancy.

In practice, a sound design must satisfy **quorum, elections, data replication, and business goals**, not just the `floor(V/2)+1` formula.

## 16. Reconfiguration: Changing Votes Is a Sensitive Operation

When adding, removing, or modifying voting member attributes, MongoDB provides the replica set reconfiguration mechanism. These changes directly impact:

- The number of voting members and the majority threshold.
- Which nodes are eligible to be elected primary.
- Failover capability when a failure domain is lost.
- Write concern acknowledgment requirements and data state.
- The likelihood of elections or primary transitions during maintenance.

Do not modify `votes`, `priority`, or use **force reconfiguration** merely to force a node that has lost quorum into becoming primary without assessing data safety impacts. Forced or misconfigured changes can create rollback risks, loss of non-majority-committed writes, or unintended topology changes.

A change plan typically needs to:

1. Record the current configuration and status.
2. Determine voter count and quorum **before/after**.
3. Verify required nodes are synced and eligible.
4. Sequence changes in accordance with the MongoDB version's reconfiguration constraints.
5. Prepare rollback/recovery plans and a maintenance window if needed.
6. Monitor elections, replication lag, and write concerns after the change.

In this lesson, configuration examples are solely for understanding quorum. **Do not practice force reconfig, removing members, or stopping nodes on a replica set serving real production data.**

## 17. Status Reading Checklist When a Replica Set Loses Primary

When receiving a message like "no primary available," check these questions in order:

| Question | How to Check | Meaning |
| --- | --- | --- |
| How many members are configured? | `rs.conf().members` | Total node count is not identical to voter count |
| Who has votes? | `votes` in `rs.conf()` | Calculate quorum |
| What is the quorum? | `floor(V/2)+1` and check server status | Vote threshold that must be reached |
| Can voting members communicate with each other? | `rs.status()`, heartbeat/network logs | Online nodes are not necessarily in the same quorum |
| Is there an electable candidate? | `votes`, `priority`, replication state | Having quorum can still lack a candidate |
| Is there an arbiter? | `arbiterOnly` | A vote does not equate to a data copy |
| Has the old primary stepped down? | `rs.status()`, `hello`, logs, term | Detect role transition/ongoing election |
| Are secondaries lagging or in initial sync? | `rs.status()`, replication metrics | Affects candidates and ack capability |
| Can `w:"majority"` writes complete? | Write concern, `writeMajorityCount` if present, data-bearing status | Distinct from election quorum |
| Is the client discovering the right topology? | URI, replica set name, DNS, connectivity | Not every error stems from internal elections |

Prioritize **read-only inspection and observation** first. Changing election configuration or forcing a node to become primary should belong to an approved operational procedure, not a knee-jerk reaction when an error appears.

## 18. Common Misconceptions

| Misconception | Why It Is Incorrect | Correct Understanding |
| --- | --- | --- |
| "A two-node replica set tolerates one node failure because it has a copy" | Two voters require a 2/2 quorum | Separate data copy count from vote count |
| "Quorum is calculated from currently online nodes" | Dead members are not automatically removed from config | Majority is computed over voting members in the effective config |
| "Just need more than half of total nodes" | Non-voters have no votes, and nodes may not reach one another | Count voting members and reachable votes |
| "Having quorum guarantees a primary" | No eligible member may remain, or an election may be underway | Both quorum and an eligible candidate are needed |
| "`priority: 0` means non-voting" | Can still have `votes: 1` | `votes` and `priority` are two separate settings |
| "`priority: 2` gives two votes" | Priority is not votes | A normal voting member has one vote |
| "`votes: 0` with `priority: 1` can still be primary" | Non-voters are ineligible to run | `votes: 0` requires `priority: 0` |
| "An arbiter is a third data copy" | Arbiters store no data | It only contributes to elections |
| "P + arbiter has two votes so majority writes will succeed" | Arbiters do not replicate writes | Election majority differs from majority write acknowledgement |
| "Every added voting member increases fault tolerance" | Three voters have quorum 2, four voters have quorum 3; both tolerate 1 voter loss | Check the majority table by topology |
| "If primary is lost, secondary becomes primary instantly" | Requires election, heartbeats, eligibility | Failover has latency and may not immediately succeed |
| "You can arbitrarily edit votes to bring primary back" | Reconfig affects safety and data consistency | Follow a topology change procedure |
| "`rs.status()` from one node reflects all network sides identically" | Partitioned nodes have different perspectives | Cross-check nodes, logs, and actual topology |
| "If a `w: 1` write succeeds, it cannot be rolled back" | Non-majority-committed writes can be lost on failover | Choose write concern based on desired durability |

## 19. Hands-On Exercises and Answers

### Exercise 1. Basic Quorum Calculation

Calculate the minimum votes required when a replica set has 2, 3, 4, 5, and 7 voting members.

**Answer:**

```text
V = 2 -> quorum = 2
V = 3 -> quorum = 2
V = 4 -> quorum = 3
V = 5 -> quorum = 3
V = 7 -> quorum = 4
```

General rule: `floor(V/2)+1`.

### Exercise 2. Three Nodes Remaining, Yet No Quorum?

Topology:

```text
A: votes=1, priority=1
B: votes=1, priority=1
C: votes=0, priority=0
```

A completely loses connectivity. B and C remain active. Can B be elected primary with only C?

**Answer:** No. Only A and B have votes, so `V = 2`, quorum = 2. The B–C side has **one vote** from B; C does not vote. Even with two data-bearing members and B having positive priority, quorum is not met.

### Exercise 3. Quorum Met, Yet No Primary

Topology:

```text
A: votes=1, priority=1
B: votes=1, priority=0
C: votes=1, priority=0
```

A fails; B and C can communicate with each other. Can a new primary be elected?

**Answer:** B and C have two out of three votes (meeting quorum), but both have `priority: 0` and cannot become primary. **There is no electable candidate**, so no primary can be elected.

### Exercise 4. 3–2 Network Partition

A five-voting-member replica set splits into group X with three nodes and group Y with two nodes. Each group communicates internally, while the two groups cannot reach each other. Which side can have a primary?

**Answer:** Quorum = 3. Group X reaches majority and can maintain/elect a primary if an eligible candidate exists. Group Y lacks majority and cannot elect a primary. If the old primary belonged to group Y, it must step down upon losing quorum.

### Exercise 5. Arbiter and Majority Write

Replica set `P–S–A`: P is primary, S is secondary, A is arbiter, all three with one vote. S loses connectivity; P and A remain reachable.

1. Is there still an election quorum?
2. Can `w: "majority"` writes be guaranteed?

**Answer:** (1) Yes, P and A have 2/3 votes. (2) No; A stores no data, so only P can receive writes. Majority write requirements in a normal P–S–A cannot be fully acknowledged solely by P and A; writes may wait/time out.

### Exercise 6. A Node That Votes but Cannot Run

Given member:

```javascript
{
  host: "mongo-report.example.net:27017",
  votes: 1,
  priority: 0
}
```

Does this member contribute to quorum? Can it become primary?

**Answer:** It has a vote so it contributes to quorum; it cannot become primary because `priority: 0`.

### Exercise 7. Why Adding a Fourth Voter Does Not Increase Fault Tolerance

Compare a three-voter replica set and a four-voter replica set, all healthy. One arbitrary voting member loses connectivity in each set. Calculate quorum and remaining votes.

**Answer:**

| Topology | Quorum | Votes left after one failure | Still has quorum? |
| --- | ---: | ---: | --- |
| 3 voters | 2 | 2 | Yes |
| 4 voters | 3 | 3 | Yes |

Both tolerate only **one voting member failure** if no other conditions change. With four voters, losing two leaves two, short of quorum 3.

### Exercise 8. Placement Across Three Zones

A five-voting-member replica set is distributed `3–1–1` across three zones. The zone holding three members fails completely. Why does the topology still have no primary despite two zones remaining?

**Answer:** Quorum = 3, yet the two remaining zones have only two votes. Fault tolerance must be calculated by **votes lost within the same failure domain**, not simply zone count or total node count.

### Exercise 9. Reading Configuration

Given:

```javascript
members: [
  { _id: 0, votes: 1, priority: 2 },
  { _id: 1, votes: 1, priority: 1 },
  { _id: 2, votes: 1, priority: 0 },
  { _id: 3, votes: 0, priority: 0 }
]
```

Calculate total members, voters, quorum, and the number of members eligible to run per configuration.

**Answer:** Total members = 4, voters = 3, quorum = 2. Members `_id: 0` and `_id: 1` have `votes: 1, priority > 0`, making them two **candidates eligible to run per configuration**, provided their state/data freshness at election time are valid. `_id: 2` only votes; `_id: 3` does not vote.

### Exercise 10. Distinguishing Two Responses

An application can connect and read from a secondary, yet a write operation returns an error saying no primary was found. Is this contradictory?

**Answer:** No. A secondary can be online and serve appropriately configured read requests while the replica set lacks quorum or has not yet elected a primary. Reachability of one process does not mean writability through a primary. You need to inspect topology, voting configuration, network, election state, and driver server selection.

## 20. Summary

In a MongoDB replica set, **election quorum** is a majority of votes among voting members under the effective configuration:

```text
quorum = floor(numberOfVotingMembers / 2) + 1
```

To have a primary, a replica set needs not only **enough reachable votes**, but also **at least one eligible data-bearing voting member** and a valid election. `votes` determines quorum participation; `priority` determines candidacy eligibility and preference; `priority: 0` can still vote; `votes: 0` contributes no vote and cannot become primary. An arbiter contributes a vote without replicating data.

When designing high availability, you must evaluate **both election quorum and write concern `majority`**. A side with enough votes to have a primary may not have enough data-bearing members left to acknowledge writes at the required safety level. Likewise, distributing votes across independent failure domains and monitoring candidate replication health matter just as much as the quorum math. Understanding these distinctions helps predict the impact of node failures, explain why a replica set has no primary, and choose an appropriate topology for MongoDB applications.
