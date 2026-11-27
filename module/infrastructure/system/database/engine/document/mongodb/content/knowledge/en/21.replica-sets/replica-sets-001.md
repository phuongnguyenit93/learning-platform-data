# Replication Goals and Primary, Secondary Structure in a MongoDB Replica Set

## Lesson Objectives

A database running on a single server easily becomes a **single point of failure**: when the machine fails, a disk malfunctions, the network is interrupted, or the `mongod` process stops for maintenance, the application may lose the ability to read/write. A **MongoDB Replica Set** is a group of MongoDB processes that coordinate to maintain copies of the same dataset and elect a **primary** member to serve writes. Other members that store data are typically **secondaries**, which replicate changes from the oplog and can become primary when election conditions allow.

This lesson belongs to the **Database Engine Document MongoDB** topic, **Replica set** chapter, and focuses directly on **replication goals, primary and secondary structure** along with their important implications for application design.

After this lesson, learners will be able to:

1. Explain how replication differs from sharding, backup, disaster recovery, and journaling.
2. State the goals of high availability, data redundancy, durability, failover, maintenance, and secondary reads.
3. Diagram an architecture with one primary and multiple secondaries, distinguishing the role of each member.
4. Explain how the primary handles writes, how secondaries follow the oplog, and why replication has lag.
5. Understand majority voting principles, primary elections, and temporary disruptions during failover.
6. Compare a three data-bearing member replica set **P-S-S** with **P-S-Arbiter**.
7. Know priority, votes, hidden, delayed, and non-voting member options at an architectural level.
8. Distinguish read preference, read concern, and write concern, especially `w:1` vs. `w:"majority"`.
9. Understand when writes can be rolled back and why replication does not replace backups.
10. Practice with `rs.initiate()`, `rs.status()`, `rs.conf()`, `db.hello()`, connection strings, and the Java Driver.
11. Propose topologies suited to failure domains, control replication lag, and operate safely.

> **Remember:** Having multiple copies does not mean the copies update instantaneously. Having enough **votes** to elect a primary does not mean having enough **data copies** to acknowledge majority writes. A replica set increases fault tolerance, but it does not replace an independently restorable backup.

---

## 1. What is a Replica Set?

A **replica set** is a group of `mongod` instances that maintain the same **logical dataset**. In a typical structure, one member holds the **PRIMARY** role, while the other data-bearing members hold the **SECONDARY** role.

~~~text
                         REPLICA SET rs0

                   +-----------------------+
Client writes ----->| PRIMARY mongo1:27017  |
                    | Data + indexes        |
                    | Oplog                 |
                    +-----------+-----------+
                                |
                    Asynchronous replication
                         /            \
                        v              v
          +--------------------+  +--------------------+
          | SECONDARY mongo2   |  | SECONDARY mongo3   |
          | Data + indexes     |  | Data + indexes     |
          | Oplog              |  | Oplog              |
          +--------------------+  +--------------------+
~~~

The goal of the members is to maintain the same dataset once caught up. The application does not have to separately write the same order to three machines. The driver is aware of the replica set configuration, routes writes to the primary, and depending on policy can read from the primary or a secondary.

### 1.1. Basic Terminology

| Term | Meaning |
|---|---|
| `mongod` | MongoDB database server process |
| Replica set | Group of MongoDB members storing copies and participating in primary management |
| Primary | Member elected to accept normal writes |
| Secondary | Data-bearing member that replicates and applies data from a replication source |
| Data-bearing member | Member containing user data and indexes |
| Arbiter | Member that votes but **does not store user data** |
| Oplog | Ordered log of operations used for replication |
| Election | Process of electing a primary |
| Majority | Majority of votes, applied in elections and applicable acknowledgment rules |
| Replication lag | Replication progress gap between members |
| Write concern | Level of write acknowledgment requested by the client |
| Read preference | Rule for selecting a member to read from |
| Read concern | Level of guarantee regarding the data read |
| Failover | Transitioning to a new primary when the current primary becomes unavailable |
| Rollback | Removing/reconciling operations not part of the accepted history when a member rejoins |

### 1.2. A Replica Set is Not a Way to Split Data into Three Parts

If:

~~~text
Server A holds Northern region customers
Server B holds Southern region customers
Server C holds Central region customers
~~~

then each machine holds a **different** group of data. That is not the replication model of the same dataset.

With a replica set:

~~~text
Mongo1: orders + users + inventory (copy 1)
Mongo2: orders + users + inventory (copy 2)
Mongo3: orders + users + inventory (copy 3)
~~~

The copies may differ temporarily due to replication lag, but the goal is to synchronize the same accepted history.

If you need to **distribute data** across multiple shards to scale capacity and throughput, MongoDB uses **sharding**. Each shard typically has its own replica set for redundancy. The two mechanisms complement each other, but they are not synonymous.

---

## 2. First Goal: High Availability

### 2.1. A Single Server Creates a Single Point of Failure

~~~text
App -> Single MongoDB -> machine failure -> application loses access path
~~~

With a replica set of three voting data-bearing members:

~~~text
App -> rs0
         |
         +-- Primary fails
         |
         +-- Two secondaries remain active, having enough majority votes
         |
         +-- Election: one secondary becomes the new primary
         |
         +-- Official driver detects the topology and routes writes
~~~

This is the **automatic failover** mechanism under appropriate election conditions.

### 2.2. High Availability Does Not Mean Zero Downtime

During the time the primary fails and a new primary has not yet been elected:

- Writes may wait or temporarily fail.
- Some reads that depend on the primary may also be interrupted.
- In-flight operations may receive network or not-primary errors.
- The driver needs to discover the new topology.
- The application needs an appropriate timeout/retry policy.

Do not promise a fixed RTO value simply because you created a replica set. Failover duration depends on failure type, heartbeat/election settings, network, member state, data freshness, and the application.

### 2.3. Per-Node Maintainability

A replica set helps organize maintenance member by member:

- Replacing a disk/VM for a secondary.
- Performing rolling upgrades following version guidelines.
- Verifying backups from an appropriate member.
- Performing a controlled primary step-down/switch if needed.
- Recovering a member via initial sync.

However, this does **not** mean you can arbitrarily stop two out of three voting nodes and continue writing. You must account for majority and data safety before operating.

---

## 3. Second Goal: Data Redundancy and Durability

### 3.1. Having Multiple Physical Copies

When members reside on independent machines and failure domains, a disk/host failure of one member does not by itself cause loss of all data.

A better example than a single machine:

~~~text
Availability Zone A         Zone B             Zone C
     mongo1                  mongo2             mongo3
     data                    data               data
     vote 1                  vote 1             vote 1
~~~

If one zone has an issue, the remaining two zones can continue forming a quorum and retaining two data copies in a standard P-S-S setup.

### 3.2. Three `mongod` Processes on the Same Host Is Only a Lab

~~~text
One VM:
  mongod :27101
  mongod :27102
  mongod :27103
~~~

This configuration is useful for learning replication/elections, but **if the VM fails, all three stop**. It provides no high availability against host, power, or shared storage failures.

### 3.3. Durability Requires Combining with Write Concern

Replication provides copies, while **write concern** defines how far the client waits for acknowledgment.

Writing with `w:1`:

~~~javascript
db.orders.insertOne(
  { _id: "O-101", status: "PAID" },
  {
    writeConcern: {
      w: 1
    }
  }
);
~~~

Writing with `w:"majority"`:

~~~javascript
db.orders.insertOne(
  { _id: "O-102", status: "PAID" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

`w:1` requests acknowledgment from the primary, which does not prove the operation has reached any secondary. `w:"majority"` requires majority acknowledgment according to replica set rules, raising protection against certain rollback/failover scenarios.

That does **not** mean every member has received the operation, nor does it guarantee every kind of disaster cannot cause data loss.

### 3.4. Replication Does Not Replace Backups

An erroneous operation:

~~~javascript
db.orders.deleteMany({});
~~~

if accepted by the primary, can be replicated to the secondaries. All copies can suffer the consequence.

Therefore, **backup/PITR** with point-in-time recovery capabilities, access controls, isolated copy storage, and restore testing are required. Replica sets help tolerate node failures; backups serve to recover when data is deleted/overwritten/corrupted or when a broader disaster occurs.

---

## 4. Third Goal: Read Scalability When Appropriate

Secondaries can be used for some read workloads when the application accepts reading slightly stale data.

Examples:

- Daily historical reports.
- Near-real-time dashboards with acceptable latency.
- Analytical queries that can run on a dedicated member if configuration allows.

However, the limitations include:

1. Replication is asynchronous; a secondary may not have applied recent writes yet.
2. Heavy reads can contend for CPU/RAM/disk with applying the oplog.
3. Not every secondary is selected by the driver (hidden members are an example).
4. A read preference does not by itself create a consistency guarantee.
5. Certain business flows such as payments, balances, and inventory decisions require fresher data.
6. Reading on a secondary may offload the primary, but increases total resource usage across the cluster.

**Conclusion:** A replica set is primarily for **redundancy and availability**; secondary reads are a conditional capability, not a guarantee of unlimited scale-out.

---

## 5. What is PRIMARY?

The primary is the data-bearing member elected to hold the writable role. In a standard configuration, a replica set has **one current primary**.

### 5.1. Responsibilities of the Primary

- Accepts normal insert/update/delete operations.
- Applies changes to its own data and indexes.
- Records change information into the oplog for the replica set to replicate.
- Serves read operations according to read preference.
- Provides replication progress state for the replication mechanism.
- Participates in heartbeats, elections, and coordination with other members.

Write example:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $set: {
      available: 20
    }
  }
);
~~~

An application writing via a replica set URI will be routed by the driver to the discovered primary, rather than manually calling every secondary.

### 5.2. The Primary Also Stores Data

The primary is not a stateless router without storage. It has collections, indexes, a journal/storage engine, and an oplog as a data-bearing member.

~~~text
Application writes
     |
     v
   PRIMARY
     |
     +--> Primary's own data/indexes
     |
     +--> Oplog for replication
     |
     +--> Write concern progress info
                 |
        Secondaries continue catching up
~~~

This is a conceptual model, not an absolute I/O ordering diagram for every version.

### 5.3. Do Not Hard-Code the Primary

Do not assume:

~~~text
mongo1 is always primary because it was primary at initialization.
~~~

An election can cause mongo2 or mongo3 to become primary. `priority` only affects election preference, not a "permanent lock" on the role.

Applications should use a multi-host URI:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

The driver will handle topology discovery/monitoring.

---

## 6. What is SECONDARY?

A secondary is a data-bearing member that holds a copy of the same dataset and continuously applies replicated operations.

### 6.1. What Does a Secondary Do?

- Receives change information from a sync source.
- Reads and applies the necessary oplog entries.
- Maintains corresponding collections and indexes.
- Publishes replication progress.
- Can serve reads depending on read preference and configuration.
- Can be a candidate in primary elections if eligible.
- Serves specialized backup/reporting purposes within safe boundaries.

### 6.2. A Secondary Is Not an Instantaneous Copy

Example:

~~~text
12:00:00.100
PRIMARY:   order O-101.status = PAID
SECONDARY: order O-101.status = NEW

12:00:00.700
SECONDARY applied the change:
  order O-101.status = PAID
~~~

During the gap, reads on the secondary may return stale data. This is **replication lag**, not necessarily an error.

### 6.3. A Secondary Can Become the New Primary

For a secondary to become primary, it must meet election criteria, such as:

- Having voting rights and an appropriate priority.
- Having data state/progress that satisfies the rules.
- Receiving enough majority votes.
- Satisfying election term, network, and configuration conditions.

A member with `priority:0` is still a normal data-bearing secondary, but is **ineligible to be elected primary**.

### 6.4. A Secondary Can Receive Oplog Entries from Another Secondary

Basic diagrams often draw the primary streaming directly to every secondary. In practice, a secondary can choose another suitable **sync source**, including another secondary according to replication rules. The replication topology is not required to be a fixed star.

---

## 7. Oplog: The Mechanism Connecting Primary and Secondaries

### 7.1. What is the Oplog?

The **oplog** (operations log) is an ordered log of replicated operations. In a replica set, it is stored at:

~~~text
local.oplog.rs
~~~

This is a special internal collection with rolling/capped behavior per MongoDB's mechanism, with storage and history limits.

Conceptual flow:

~~~text
1. Client sends write to primary.
2. Primary processes write per MongoDB semantics.
3. Operation is recorded in oplog history.
4. Secondary pulls oplog entries from sync source.
5. Secondary applies changes in the appropriate order.
6. Secondary updates optime/progress.
7. Majority confirmation depends on progress of eligible members.
~~~

Do not interpret steps 3 through 7 as an immediate cluster-wide transaction: **replication is asynchronous**.

### 7.2. The Oplog Is Not the Journal

| Component | Purpose |
|---|---|
| Oplog | Replicates changes between replica set members |
| Journal | Supports durability and recovery of the local storage engine |
| Backup | Keeps independently restorable data according to policy |
| Change streams | Application-facing change tracking API built on MongoDB's mechanism |
| Application audit log | Records user/business activities per separate policy |

### 7.3. Reading the Oplog in a Lab

~~~javascript
db.getSiblingDB("local")
  .getCollection("oplog.rs")
  .find({})
  .sort({ $natural: -1 })
  .limit(5);
~~~

This command may require appropriate privileges. **Do not directly edit or delete `local.oplog.rs`.** It is critical system data.

### 7.4. Oplog Window

Suppose the current workload allows the oplog to retain replication history for roughly 10 hours. A secondary offline for 24 hours might not find enough oplog entries to catch up. It may have to perform an **initial sync** again or another recovery procedure.

The oplog window depends on:

- Oplog size.
- Write volume and write rate.
- Size/types of operations.
- Retention configuration and version.
- Network health/replication lag.

Do not monitor only "is the node online?"; monitor **lag relative to oplog history retention capacity**.

---

## 8. Initial Sync and Steady-State Replication

### 8.1. Initial Sync

A new secondary, without suitable data yet, requires **initial synchronization**. Conceptually:

1. Select an appropriate sync source.
2. Copy the necessary data/indexes.
3. Collect changes occurring during the copy.
4. Apply oplog entries to catch up.
5. Transition to SECONDARY when complete and eligible.

Implementation details and states depend on the server version.

### 8.2. Steady State

After initial sync, the secondary continues replicating from the oplog to keep its copy up to date.

~~~text
Initial sync:
  Create initial data copy + catch up on change history.

Steady state:
  Continuously maintain the copy as the primary receives new writes.
~~~

### 8.3. Why a Successful Ping Is Not Enough

A member may have an open TCP port while in STARTUP2, RECOVERING, or rollback. Do not infer that an open port means the secondary is ready to serve normal reads.

Check `rs.status()` and driver topology; monitor initial sync progress, lag, and health.

---

## 9. Primary Elections via Majority Voting

### 9.1. Majority Formula

If a replica set has `V` voting members, the majority vote count is:

\[
\mathrm{majorityVotes}=\left\lfloor\frac{V}{2}\right\rfloor+1
\]

| Voting members | Majority needed |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 6 | 4 |
| 7 | 4 |

A MongoDB replica set has limits on total members and voting members (typically a maximum of 7 voting members, even though total members can be larger). Exact limits should be checked against version documentation when designing large topologies.

### 9.2. Conceptual Election Flow

~~~text
PRIMARY becomes unavailable / ineligible to be primary
                     |
                     v
Members observe via heartbeats/topology
                     |
                     v
Eligible secondary initiates an election
                     |
                     v
          Enough majority votes?
                   /       \
                 Yes        No
                  |          |
                  v          v
           New PRIMARY     Cannot elect
                  |        a valid primary
                  v
       Driver detects and redirects writes
~~~

Many other technical conditions apply: term, data freshness, priority, node state, network, and replica set protocol. This diagram illustrates the purpose of quorum, not a full simulation of the algorithm.

### 9.3. Why 3 Voting Nodes Are Better Than 2

- With **2 voters**, majority = 2. Losing one node leaves insufficient votes.
- With **3 voters**, majority = 2. Losing one node still leaves enough votes.
- With **4 voters**, majority = 3. Losing two nodes leaves insufficient votes.
- With **5 voters**, majority = 3. Losing two nodes still leaves enough votes.

Therefore, deploying an odd number of votes such as 3 or 5 usually avoids adding an even voter without a corresponding gain in fault tolerance. Final choices also depend on placement, costs, read/write concerns, and failure domains.

### 9.4. A Member with Data Still Might Not Be Writable

If a three-vote P-S-S loses two members, the surviving node has only 1/3 of the votes. It may hold a valid copy of the data but **lacks quorum to become primary**. This is a trade-off to preserve the consistency of election history.

Do not arbitrarily force a reconfig during a network incident to create an extra primary without understanding the consequences of data divergence.

---

## 10. P-S-S Structure: Three Data Copies Model

### 10.1. Diagram

~~~text
                  P-S-S — rs0

                PRIMARY P
                data + oplog
                votes = 1
                  /    \
                 v      v
        SECONDARY S1    SECONDARY S2
        data + oplog    data + oplog
        votes = 1       votes = 1
~~~

There are three data-bearing members and, if all three have votes=1, three voting members. Election majority = 2/3.

### 10.2. When the Primary Fails

Suppose P goes down, and S1 + S2 remain healthy:

- The two secondaries have 2 votes.
- An eligible candidate can become the new primary.
- The application may temporarily lose the write path during the election.
- Data still exists on S1 and S2.
- As long as both data-bearing members keep up, majority writes can be acknowledged.

### 10.3. When One Secondary Fails

P + S1 remain:

- Two votes remain online, meeting majority.
- The primary can continue serving.
- Two active data copies still remain.
- `w:"majority"` can be acknowledged if both data-bearing members meet progress requirements.
- The system is in a degraded redundancy state; one more voting node failure could lose quorum.

### 10.4. When Two Voting Nodes Fail

Only one member remains:

- No 2/3 majority.
- Cannot elect a valid new primary under the current config.
- The write path may be unavailable.
- Having one data copy does not mean having the authority to accept writes.

### 10.5. Advantages and Costs

**Advantages:** stronger redundancy than P-S-A, easier rolling maintenance, tolerance for one voting node failure, and two data copies remaining after one node fails.

**Costs:** three times the dataset/index storage, replication network traffic, replication CPU/disk I/O, monitoring and security across all three, and write concern latency per topology.

---

## 11. P-S-Arbiter Structure: Votes Differ from Data Copies

### 11.1. What Does an Arbiter Do?

An **arbiter** is a member that can vote in elections but **does not store user data** and cannot serve application data reads/writes.

~~~text
            P-S-A

        PRIMARY P         SECONDARY S
        data + oplog  --> data + oplog
        1 vote            1 vote

                  ARBITER A
                  no user data
                  1 vote
~~~

Three voting members → election majority = 2, but there are only **two data-bearing members**.

### 11.2. An Arbiter Cannot Replace a Secondary

An arbiter:

- Can contribute an election vote.
- Does not apply the oplog to hold a copy of user data.
- Does not serve secondary reads.
- Cannot be elected primary.
- Cannot recover data from a copy that does not exist.
- Cannot acknowledge data replication in place of a data-bearing member.

### 11.3. Secondary Fails, Primary + Arbiter Remain

~~~text
S down
P has data + 1 vote
A has 1 vote
=> P + A have 2/3 votes.
=> A valid primary can still exist.

But only P stores data.
=> A cannot count as a copy to satisfy
   w:"majority" for written data.
~~~

In P-S-A, when only one data-bearing member is active, writes requiring `w:"majority"` can wait and return a write concern timeout. This is an important example of **having enough election quorum but not enough data replication acknowledgments**.

### 11.4. Primary Fails, Secondary + Arbiter Remain

- S + A have 2/3 votes.
- S can be elected primary if eligible.
- Only one data-bearing member remains active.
- The same issue with majority write concern still applies.

### 11.5. Why P-S-S Is Usually Preferred

If infrastructure allows, P-S-S with three data-bearing voting members is usually the better choice for production workloads needing data redundancy and durability. P-S-A may appear under resource constraints, but it is **not equivalent** in safety merely because it also has three voting nodes.

| Criterion | P-S-S | P-S-A |
|---|---|---|
| Total members | 3 | 3 |
| Data-bearing members | **3** | **2** |
| Voting members | 3 | 3 |
| Election majority | 2 | 2 |
| Has arbiter | No | Yes |
| Data copies after losing one data node | 2 | 1 |
| Majority write with one data-bearing member left | Does not happen after a single data node failure in 3-data-node P-S-S | May fail to satisfy even though P+A have enough votes |
| Reading from secondary | Can have two candidates | Only one secondary normally |
| Storage cost | Higher | Lower |
| Data protection level | Better in this comparison | Significant trade-offs |

Not every failure produces the exact same outcome, but the table highlights why you must design around **actual data copies**, not just member counts.

---

## 12. Specially Configured Members

### 12.1. `priority`

Member example:

~~~javascript
{
  _id: 2,
  host: "mongo3:27017",
  priority: 0
}
~~~

`priority: 0`: the member **cannot be elected primary**, though it can still be a normal data-replicating secondary.

Priority 2 does not equal two votes. Priority only influences election preference; it does not guarantee that node will always become primary.

### 12.2. `votes`

~~~javascript
{
  _id: 3,
  host: "mongo4:27017",
  votes: 0,
  priority: 0
}
~~~

`votes: 0`: the member contributes no election votes and cannot become primary. It can still store data as a normal secondary. It is not counted as a voting member when determining election majority.

### 12.3. Hidden Secondary

~~~javascript
{
  _id: 2,
  host: "mongo3:27017",
  hidden: true,
  priority: 0
}
~~~

Hidden secondary:

- Holds data and replicates.
- Does not become primary.
- Is not selected as a normal secondary by driver server selection.
- May hold voting rights depending on configuration.
- Can be suitable for specialized admin/backup tasks with proper direct connection.

**Hidden does not mean free of storage/index maintenance costs.**

### 12.4. Delayed Secondary

A secondary can intentionally delay applying operations via `secondaryDelaySecs` in supported versions. The purpose can be creating a window to detect accidental operations before they appear on the delayed copy.

However:

- After the delay, the bad change can still be replicated.
- It is not an immutable backup or PITR.
- Oplog window and delay interval must be accounted for.
- A properly configured delayed secondary cannot become primary and should be configured with appropriate hidden/votes settings as recommended.
- Intentional delay must be distinguished from abnormal lag.

### 12.5. Comparison Table

| Type | Stores user data? | Can be primary? | Can vote? | Normal read via driver? |
|---|---|---|---|---|
| Primary | Yes | Currently primary | Usually yes | Yes |
| Normal secondary | Yes | If eligible | Can | Yes with appropriate readPreference |
| Priority 0 secondary | Yes | **No** | Can | Yes if not hidden and selected |
| Hidden secondary | Yes | **No** | Can | Not as a normal secondary |
| Delayed secondary | Yes | No when configured properly | Depends on config | Not suitable for reads needing fresh data |
| Non-voting secondary | Yes | **No** | **No** | Possible depending on config |
| Arbiter | **No** | **No** | **Yes** | **No** |

Attributes have specific constraints when combined. Do not invent arbitrary combinations directly from the table.

---

## 13. Member States and How to Recognize Them

In `rs.status()`, you may see states such as:

| State | Brief Meaning |
|---|---|
| `STARTUP` | Just started |
| `STARTUP2` | Initialization/initial sync phase where applicable |
| `RECOVERING` | Recovering or not yet able to serve as a normal secondary |
| `PRIMARY` | Currently elected primary |
| `SECONDARY` | Serving in the secondary role |
| `ARBITER` | Voting member with no user data |
| `DOWN` | Observed as unreachable |
| `UNKNOWN` | State unknown |
| `ROLLBACK` | Processing a rollback |
| `REMOVED` | Not part of the current replica set configuration |

**State differs from config.** A node with `priority: 2` can still show state SECONDARY; a node in state SECONDARY does not mean it is configured with priority 0.

Do not rely solely on TCP ping/`health:1` to conclude replication lag is 0.

---

## 14. Reading Data: Read Preference and Read Concern

### 14.1. Read Preference Answers "Where to Read?"

| Mode | General Rule |
|---|---|
| `primary` | Read from primary only; common default |
| `primaryPreferred` | Prefer primary, can fall back to secondary |
| `secondary` | Read from eligible secondary only |
| `secondaryPreferred` | Prefer secondary, can fall back to primary |
| `nearest` | Choose a member based on latency; may be primary or secondary |

URI example:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn&readPreference=secondaryPreferred
~~~

This does not mean every read will be served by a secondary: `secondaryPreferred` can fall back to the primary.

### 14.2. Read Concern Answers "Read with What Guarantee?"

| Read concern | Idea |
|---|---|
| `local` | Data on the queried member, without requiring majority commit |
| `majority` | Data at the majority-committed level per server semantics |
| `linearizable` | Strong guarantee for certain reads on the primary under specific conditions |
| `snapshot` | Consistent snapshot in supported contexts |

Read preference and read concern are two **independent** choices.

For example:

~~~text
readPreference: secondary
readConcern: majority
~~~

can read majority-committed data from a secondary, but **the secondary can still lag behind the primary**. A majority read on a secondary does not automatically guarantee reading the exact latest operation at the moment of the query.

### 14.3. When Is It Acceptable to Read from a Secondary?

Acceptable examples:

- Yesterday's revenue dashboard.
- Looking up historical data for statistical purposes.
- Internal reports whose SLA tolerates a few seconds of staleness.

Examples requiring careful consistency consideration:

- Account balance immediately after a transaction.
- Checking payment status right after paying.
- Warehouse dispatch decisions after an inventory update.
- Flows requiring read-your-writes or causal consistency.

**Read preference does not replace consistency design.** Official drivers provide sessions and other mechanisms to support stronger guarantees when configured properly.

### 14.4. maxStalenessSeconds

Some drivers allow configuring `maxStalenessSeconds` to exclude secondaries estimated to be too stale from the read candidate list. However, this is not an exact "data is always newer than N seconds" contract, and it is subject to driver server selection limits and algorithms.

Do not use this parameter as a substitute for an appropriate read concern.

---

## 15. Write Concern: w:1, majority, and Timeout

### 15.1. `w:1` Only Waits for the Primary

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-W1", amount: 500 },
  {
    writeConcern: {
      w: 1
    }
  }
);
~~~

If the primary acknowledges before secondaries receive it, and then the primary becomes unavailable, the operation may fall outside the majority-accepted history and risk being rolled back.

### 15.2. `w:"majority"` Waits for Greater Acknowledgment

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-WMAJ", amount: 800 },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

In a normal three-voting-data-member P-S-S set, a write can reach majority when **two eligible data-bearing voting members** have reached the required progress. All three do not need to have caught up by default.

### 15.3. Journaling and `j:true`

~~~javascript
db.orders.insertOne(
  { _id: "ORDER-JOURNAL" },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Journaling is the storage engine's local durability mechanism, distinct from replication. The exact relationship between majority acknowledgment, journaling, and durability depends on MongoDB version and settings such as `writeConcernMajorityJournalDefault`. Do not treat every acknowledgment as "fsynced to all disks on all nodes".

### 15.4. `wtimeout` Does Not Mean the Write Did Not Happen

If the wait for majority times out:

- The write may already have been applied on the primary.
- One or more secondaries may already have replicated it.
- The requested acknowledgment level was not met by the timeout.
- The client may receive a write concern error.
- Blindly retrying can cause duplicate writes.

Example with `$inc`:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-101" },
  {
    $inc: {
      points: 10
    }
  }
);
~~~

If it was already applied and the response was lost, uncontrolled retries could increment by 20 instead of 10. Idempotent request IDs or business reconciliation mechanisms are needed.

### 15.5. Defaults Are Not Immutable

The default write concern can vary by MongoDB version and topology, especially in deployments with an arbiter. Do not teach "every replica set defaults to w:1" or "everywhere defaults to majority" without checking the environment.

---

## 16. Replication Lag: How Can a Secondary Fall Behind?

### 16.1. Concept

~~~text
PRIMARY   lastApplied = 12:00:10
SECONDARY lastApplied = 12:00:07

Progress gap: e.g. ~3 seconds.
~~~

This is an illustration. In real operations, you must read optime/replication metrics with proper semantics; clock skew, lastApplied vs. lastDurable, and sync source progress can affect interpretation.

### 16.2. Common Causes

- High write rate on the primary.
- Secondary lacking CPU, RAM, or disk I/O.
- Latency or packet loss between members.
- Secondary handling heavy reporting workloads.
- Index builds, backups, or maintenance causing I/O pressure.
- Secondary recently restarted.
- Poor sync source.
- Large write operations or workloads involving many indexes.
- Intentional delayed secondary.

### 16.3. Consequences

- Secondary reads may be stale.
- Majority writes may slow down in topologies with few up-to-date copies.
- A member may be ineligible to become primary at a given time.
- If offline beyond the oplog window, initial sync may be required.
- Failover may take longer or lead to rollbacks for writes not yet majority-committed.

### 16.4. Remediation

Measure metrics, check network/disk, reduce read-heavy workloads on secondaries, control index builds, and verify the oplog window. Do not merely increase timeouts or lower write concern while ignoring durability risks.

---

## 17. Failover, Network Partition, and Rollback

### 17.1. An Illustrative Failover Incident

~~~text
T0: mongo1 = PRIMARY, mongo2/mongo3 = SECONDARY
T1: App writes W to mongo1, w:1 returns success.
T2: mongo1 is network-partitioned before W replicates sufficiently.
T3: mongo2 + mongo3 have 2/3 votes.
T4: mongo2 is elected PRIMARY.
T5: mongo1 returns.
T6: MongoDB reconciles to the accepted history;
    W may be rolled back if not yet majority committed.
~~~

Not every w:1 operation will roll back, but this is a risk that must be accounted for.

### 17.2. Majority Ack and Rollback

Majority-acknowledged writes provide stronger protection against rollback in typical failover scenarios. However, real-world safety also depends on storage durability, journaling configuration, simultaneous multi-node failures, and operational conditions.

Do not phrase it as "never lose data in any disaster" simply by configuring majority.

### 17.3. 2–1 Network Partition

~~~text
Group A: mongo1 + mongo2 = 2 votes -> has majority
Group B: mongo3          = 1 vote  -> no majority
~~~

Quorum prevents a side with only 1/3 of the votes from electing a valid primary on its own. An old primary may take time to detect the loss of majority; applications must rely on official driver discovery and appropriate write concerns rather than judging by host availability.

### 17.4. Do Not Arbitrarily Force Reconfig

During a partition, forcing a config change so a side lacking quorum can elect a primary can create diverging histories or rollback risks. This is an exceptional recovery procedure, executed only according to a verified runbook and with data/backup assessment.

---

## 18. Maintenance, Topology Selection, and Failure Domains

### 18.1. Three Data-Bearing Members Across Three Zones

In infrastructure with independent failure domains, a P-S-S spread across three zones generally allows continuing to elect a primary when one zone fails.

However, cross-zone networking increases:

- Replication latency.
- `w:"majority"` latency when a remote node is needed.
- Network costs.
- Partition risk.
- Operational complexity.

No single topology formula fits every environment. You must measure latency and define RTO/RPO.

### 18.2. Quorum Differs from Backup

A P-S-S across three zones can survive the loss of one zone, yet still cannot save data accidentally deleted and replicated. Backups must be stored and protected independently.

### 18.3. Backup/Restore and RPO/RTO

- **RPO:** maximum amount of data loss acceptable during an incident.
- **RTO:** maximum acceptable service interruption duration.

Replica sets help reduce recovery time when a node fails, but actual RPO still depends on write concern and failure type. Backup/PITR addresses other incidents, with its own RPO/RTO that must be tested.

---

## 19. Hands-On: Creating a Replica Set in Docker Compose

This section is for an **isolated lab only**; do not use it as-is for production. The sample Docker image `mongo:8.0` does not enable authentication/TLS in the example. Do not expose the Docker network to untrusted networks.

### 19.1. Create `compose.yml`

~~~yaml
services:
  mongo1:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo1_data:/data/db

  mongo2:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo2_data:/data/db

  mongo3:
    image: mongo:8.0
    command: ["mongod", "--replSet", "rsLearn", "--bind_ip_all"]
    volumes:
      - mongo3_data:/data/db

volumes:
  mongo1_data:
  mongo2_data:
  mongo3_data:
~~~

The three containers have Docker-internal service DNS names and separate volumes. Do not publish host ports. For production, you need auth, TLS/member auth, backups, resource limits, and version management.

Start it:

~~~bash
docker compose up -d
~~~

### 19.2. Initialize the Replica Set

In a terminal in the directory containing `compose.yml`:

~~~bash
docker compose exec mongo1 mongosh --quiet --eval 'rs.initiate({_id:"rsLearn",members:[{_id:0,host:"mongo1:27017",priority:2},{_id:1,host:"mongo2:27017",priority:1},{_id:2,host:"mongo3:27017",priority:1}]})'
~~~

If not ready yet, check the containers and run it after startup completes. Do not repeat `rs.initiate()` after the replica set has already been successfully initialized.

### 19.3. View Status

~~~bash
docker compose exec mongo1 mongosh --quiet --eval 'rs.status()'
~~~

In mongosh:

~~~javascript
rs.status();
rs.conf();
db.hello();
~~~

Wait for the members to finish initial sync and for one member to reach PRIMARY.

### 19.4. Create a Document

Connect to the current primary using mongosh or an appropriate replica set URI:

~~~javascript
use replica_lab

db.orders.insertOne({
  _id: "ORDER-001",
  status: "NEW",
  createdAt: new Date()
});
~~~

If you connect directly to a secondary and receive a not-primary error, identify the current primary or use a replica set URI; do not fix the application by hard-coding the primary's IP.

### 19.5. Observe Member Roles

In mongosh on each member:

~~~javascript
db.hello().isWritablePrimary;
db.hello().secondary;
~~~

Try inspecting `rs.status()` to look for `stateStr` and `optimeDate`. A secondary may not show the new document yet if replication has not finished applying it.

### 19.6. Simulate Primary Failure

If mongo1 is currently primary:

~~~bash
docker compose stop mongo1
~~~

On mongo2 or mongo3:

~~~bash
docker compose exec mongo2 mongosh --quiet --eval 'rs.status()'
~~~

After the election, check which member is the new primary; do not assume it is always mongo2. Restart the old member:

~~~bash
docker compose start mongo1
~~~

Observe it rejoin and catch up. With differing priorities, the primary may change later depending on actual conditions.

### 19.7. Clean Up the Lab

~~~bash
docker compose down
~~~

This command preserves named volumes under normal behavior. If you **intentionally want to delete lab data** and are sure you are in the right Compose project:

~~~bash
docker compose down -v
~~~

`-v` deletes the project's volumes; do not run this in environments with important data.

### 19.8. DNS Note When Running from the Host

The hosts `mongo1`, `mongo2`, `mongo3` resolve inside the Docker network but may not resolve from the host machine. If mongosh/Java runs from the host, design networking/hostnames properly; do not simply replace all member hosts with `localhost`, because members need to reach one another using their configured names.

---

## 20. Administrative Commands for Reading Status

### 20.1. `rs.status()`

~~~javascript
rs.status();
~~~

Read:

- `set`: replica set name.
- `members[]`: list of members.
- `stateStr`: PRIMARY, SECONDARY, ARBITER...
- `health`: observed reachability/health status.
- `optime` or `optimeDate`: replication progress.
- Sync source and version-appropriate election/heartbeat fields.

Illustrative shape example:

~~~javascript
{
  set: "rsLearn",
  members: [
    { name: "mongo1:27017", health: 1, stateStr: "PRIMARY" },
    { name: "mongo2:27017", health: 1, stateStr: "SECONDARY" },
    { name: "mongo3:27017", health: 1, stateStr: "SECONDARY" }
  ]
}
~~~

This is only an example of fields to watch, **not the full real output**.

### 20.2. `rs.conf()`

~~~javascript
rs.conf();
~~~

Inspect hostnames, votes, priority, hidden, and configuration attributes. **`rs.conf()` is the configuration; `rs.status()` is the actual state.** A member in the configuration could currently be DOWN.

### 20.3. `db.hello()`

~~~javascript
db.hello();
~~~

`isWritablePrimary` helps identify whether a member holds the writable role. However, this indicator **does not guarantee** every write concern can be satisfied: in P-S-A with only P+A remaining, the node can be primary, yet `w:"majority"` lacks enough data-bearing confirmations.

### 20.4. Print Brief Status

~~~javascript
const result = rs.status();

printjson(
  result.members.map((member) => ({
    name: member.name,
    state: member.stateStr,
    health: member.health,
    optimeDate: member.optimeDate
  }))
);
~~~

`health:1` does not prove lag is 0. You need to inspect optime and replication monitoring.

### 20.5. Oplog/Replication Helpers

In supported mongosh/server environments:

~~~javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
~~~

Output and support level may vary by version. In production, also use metrics from monitoring tools and official admin commands.

---

## 21. Java Sync Driver: Connecting Correctly to a Replica Set

### 21.1. Multi-Host Connection String

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

The driver can discover the primary and route operations to the appropriate node. This is a lab network example without username/TLS. Production requires corresponding security.

### 21.2. Java Example

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

public class ReplicaSetExample {

    public static void main(String[] args) {

        String uri =
            "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/"
            + "?replicaSet=rsLearn";

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .build();

        try (MongoClient client = MongoClients.create(settings)) {

            MongoDatabase database =
                client.getDatabase("replica_lab");

            MongoCollection<Document> orders =
                database.getCollection("orders")
                    .withWriteConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                            5, TimeUnit.SECONDS
                        )
                    )
                    .withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.primary());

            orders.insertOne(
                new Document("_id", "ORDER-JAVA-001")
                    .append("status", "NEW")
            );

            Document saved = orders.find(
                new Document("_id", "ORDER-JAVA-001")
            ).first();

            System.out.println(saved);
        }
    }
}
~~~

This illustrates common Java Sync Driver usage and assumes valid connectivity. Re-running with the same `_id` may raise a duplicate key error; manage lab data accordingly.

### 21.3. Reading for Reports

~~~java
MongoCollection<Document> reportingOrders =
    database.getCollection("orders")
        .withReadPreference(
            ReadPreference.secondaryPreferred()
        )
        .withReadConcern(ReadConcern.MAJORITY);

Document item = reportingOrders.find(
    new Document("status", "PAID")
).first();
~~~

ReadPreference secondaryPreferred can fall back to the primary and does not guarantee the newest data. Use it only when the report tolerates staleness.

### 21.4. Do Not Pin Connection to the Primary Host

A URI pointing only to mongo1 with `directConnection=true` can be useful for member administration, but is unsuitable as a default for applications needing automatic failover because mongo1 can become a secondary after an election.

### 21.5. Retries Need Understanding of Unknown Outcome States

Official drivers support server discovery/monitoring and retryable operations under certain conditions. However, network timeouts, write concern failures, and transaction retries still require application policies. Do not infinitely retry non-idempotent commands when it is uncertain whether the previous write occurred.

---

## 22. Replication Is Not Backup: Assessing RPO/RTO

| Aspect | Replica set | Backup or PITR |
|---|---|---|
| Maintains multiple online copies | Yes | Per schedule/retention |
| Elects primary on single node failure | Yes if quorum/conditions met | Not its responsibility |
| Recovers replicated accidental deletion | Does not auto-recover | Possible with suitable copy |
| Restores to a historical point in time | Not primary mechanism | Possible with PITR |
| Protects against ransomware with same credentials | Insufficient | Needs isolated/immutable backups |
| Recovery objective | Faster failover | Restore per RPO/RTO |

**RPO** is the acceptable level of data loss; **RTO** is the desired recovery time. A replica set can improve both metrics during ordinary node failures, but does not promise RPO=0 and RTO=0 in every incident.

---

## 23. Monitoring and Production Operations

At a minimum, monitor:

1. **Current primary** and election count.
2. **Member states/health**, heartbeat failures.
3. **Replication lag**, optime/applied/durable progress.
4. **Oplog window** and oplog data growth rate.
5. **Write concern errors/timeouts**.
6. Disk usage, disk latency, free space.
7. CPU, RAM, cache pressure, network.
8. Read/write p95/p99 latency and slow queries.
9. Backup age, PITR window, and restore test results.
10. TLS certificates, authentication/authorization events, changes to replica set config.

A cluster with all three members in SECONDARY/PRIMARY state can still suffer heavy lag, near-full storage, or unrestorable backups.

### 23.1. When Secondary Lag Is High

Investigation procedure:

- Identify which member is lagging and by how much.
- Check recent writes, disk I/O, and network.
- Review reporting workloads on the secondary.
- Check the oplog window.
- Monitor initial sync/recovering activity.
- Consider capacity/index/query optimizations.
- Recover the member per official documentation if it can no longer catch up.

Do not reflexively lower write concern or increase oplog size while ignoring the root cause.

### 23.2. When Primary Elections Happen Frequently

Check:

- Network instability.
- Host reboots/CPU stalls.
- Storage latency.
- Replica set priority/config changes.
- Heartbeat failures.
- Software version compatibility.
- Recent maintenance operations.

Repeated elections can disrupt writes and increase application retry load.

### 23.3. Security

Production requires TLS, authentication, member-to-member authentication, least privilege, secret management, network isolation, and protected backups. Do not copy an unauthenticated Compose lab into production.

---

## 24. Common Misconceptions

**"Replica set = sharding."** False. A replica set replicates the same dataset; sharding partitions the dataset.

**"Running three processes on one VM is full HA."** False. A VM failure stops all three.

**"Secondaries immediately receive every write."** False. Replication is asynchronous; secondaries can lag.

**"A secondary never becomes primary."** False. An eligible secondary can be elected.

**"Priority 2 gives two votes."** False. Priority is distinct from votes.

**"Priority 0 does not replicate data."** False. It can still be a normal data-bearing secondary.

**"An arbiter is a data copy."** False. An arbiter holds no user data.

**"Having a primary guarantees w:majority succeeds."** False. P-S-A with only primary+arbiter is a counterexample.

**"One surviving data copy can always accept writes."** Not necessarily; quorum is required for a valid primary.

**"w:1 already confirms on every secondary."** False; w:1 does not require that.

**"w:majority = all members wrote it."** False; majority is not all.

**"wtimeout definitely means the write did not happen."** False; the write may already have been applied on the primary.

**"ReadPreference secondary always reads the latest value."** False; it can be stale.

**"ReadConcern majority + secondary means read latest."** Does not guarantee the secondary has caught up to the primary.

**"The oplog is a backup."** False; the oplog is rolling/capped and used for replication.

**"A replica set saves accidental deletion."** Not automatically; accidental deletions can replicate.

**"The driver must know a hard-coded primary IP."** No; use replica set discovery and multiple seed hosts.

**"health:1 proves replication lag = 0."** No; health and progress are separate matters.

**"You can force reconfig immediately upon losing majority."** Risks divergence/rollback; requires an official runbook.

**"Heavy reads on secondaries do not affect replication."** They can contend for resources and increase lag.

---

## 25. Process for Designing a Replica Set to System Needs

### Step 1 — Define Clear Requirements

- Target RPO/RTO?
- Tolerate failure of one node, one zone, or an entire region?
- How many writes/second, reads/second?
- Which APIs require read-your-writes?
- Any compliance/region requirements?
- How much replication lag is acceptable?
- Acceptable storage/network cost?
- Are backup/PITR already in place?

### Step 2 — Choose Data-Bearing Members

Common starting point: three voting data-bearing members across independent failure domains. Only choose an arbiter when you clearly understand the safety and majority write limitations.

### Step 3 — Calculate Election Quorum

With V voting members, majority = floor(V/2)+1. Evaluate every node/zone down scenario. Do not just count surviving servers.

### Step 4 — Evaluate Write Acknowledgment

For each scenario:

~~~text
Is there a primary?
How many data-bearing members remain?
Is there a quorum?
Can w:majority still be acked?
Is there a risk of w:1 rollback?
~~~

### Step 5 — Design Reads

Choose primary/secondary preference and read concern per API. Do not replace read consistency with a single indiscriminate application-wide config.

### Step 6 — Plan Deployment

Ensure DNS/hostnames, disks, zones, TLS, member authentication, write concern, oplog, monitoring, backups, and capacity.

### Step 7 — Failure Testing

- Stop a secondary.
- Stop the primary.
- Recover a node.
- Simulate secondary lag.
- Test read staleness.
- Test majority write timeout.
- Test backup restore.
- Measure real failover RTO under realistic workload.

### Step 8 — Write a Runbook

Document inspection commands, alert thresholds, procedures for node replacement, upgrades, quorum recovery, and rollback/backup handling.

---

## 26. Analysis Scenarios

### A. P-S-S Loses Primary

Two secondaries remain reachable: 2/3 votes, able to elect a new primary. Writes may pause briefly during the election, then resume once a primary exists and write concern is satisfied.

### B. P-S-S Loses Two Nodes

One member holds data but has only 1/3 votes, failing to reach majority. Do not create a primary via force reconfig without an official recovery plan.

### C. P-S-A Loses Secondary

Primary+arbiter have 2/3 votes, yet only one data-bearing member remains. Majority writes may time out because the arbiter does not acknowledge data.

### D. Primary Acks w:1 Then Crashes

If the write was not majority committed, it may be rolled back when another primary is elected and the old node rejoins.

### E. Reading from a Secondary Right After Payment

The secondary may still see status NEW even though the primary accepted PAID. Read preference alone does not provide read-your-writes.

### F. Secondary Offline Too Long

The oplog window no longer contains the operations needed to catch up. A fresh initial sync may be required.

### G. Three Nodes Share Storage

When shared storage fails, all three can stop. Voting quorum does not solve correlated infrastructure failures.

### H. Accidental Deletion on Primary

Secondaries also apply the deletion; only an independent backup/PITR per policy enables recovering historical data.

### I. Hidden Secondary Used for Reporting

Hidden members are not selected via normal secondary readPreference; if using a direct connection for specialized tasks, you must manage consistency, network/auth, and load.

---

## 27. Hands-On Exercises

### Exercise 1 — P-S-S Diagram

Draw the primary, two secondaries, oplog, write path, and secondary read path. Annotate which members store data and which members vote.

### Exercise 2 — Calculate Majority

Calculate majority for V = 1, 2, 3, 4, 5, 7. Explain why two voting nodes cannot tolerate a single-node failure in terms of election quorum.

### Exercise 3 — Losing Primary in P-S-S

P dies, S1 and S2 remain. Determine quorum, data copies, failover steps, and achievable write concern level while both nodes keep up.

### Exercise 4 — Losing Secondary in P-S-A

P + A remain: are there enough votes? Are there enough data-bearing acknowledgments for `w:"majority"`? Why?

### Exercise 5 — Member Priority

Configuration:

~~~javascript
{
  _id: "rs0",
  members: [
    { _id: 0, host: "db1:27017", votes: 1, priority: 2 },
    { _id: 1, host: "db2:27017", votes: 1, priority: 1 },
    { _id: 2, host: "db3:27017", votes: 1, priority: 0 }
  ]
}
~~~

Can db3 become primary, does it hold data, and do db2+db3 have enough votes to elect a primary when db1 fails?

### Exercise 6 — Compare Write Concerns

Write `w:1` and `w:"majority"` insert commands; explain a scenario where w:1 acks before sufficient replication, and the consequence if the primary fails.

### Exercise 7 — Read Preference

Choose policies for a historical dashboard, viewing a newly created order, confirming payment, and analytics reporting. Explain staleness/consistency requirements.

### Exercise 8 — Inspect MongoDB

Use `rs.status()`, `rs.conf()`, and `db.hello()`. Record current primary, states, votes, priority, and optime. Explain why `health:1` does not guarantee lag = 0.

### Exercise 9 — Failover in Docker

Create a lab replica set, stop the primary, observe the election, issue a new write through the replica set URI, restart the old node, and observe catch-up. Do not hard-guess which node wins.

### Exercise 10 — Oplog Window

A secondary is offline for 20 hours while the oplog only holds about 8 hours at the current write rate. What can happen when it comes back?

### Exercise 11 — RPO/RTO

Draft a preliminary design for an application needing single-zone fault tolerance. State topology, backup, write concern, lag alerts, and how to measure real RTO.

### Exercise 12 — Java Driver

Write a Java connection using a three-host URI, primary reads, majority writes, then try secondaryPreferred reporting. Explain how the application must handle timeouts and idempotent retries.

### Exercise 13 — Counting Votes vs. Independent Copies

Create a comparison table for P-S-S, P-S-A, and two voting data-bearing nodes regarding majority, data copies, single-node loss tolerance, and majority writes.

### Exercise 14 — Disaster Recovery

If an admin drops an entire collection and the deletion replicates, describe the steps needed to recover from backup/PITR. Why is a delayed secondary also not an independent recovery guarantee?

### Exercise 15 — Monitoring Dashboard

Design panels for primary, states, election count, lag, oplog window, write concern timeouts, disk, CPU, and backup age. Define critical alerts.

---

## 28. Review Questions

1. What is a replica set?
2. What is the difference between replication and sharding?
3. What responsibilities does the primary have?
4. Can a secondary accept direct writes from an application like a primary?
5. Through what mechanism do secondaries obtain changes?
6. Where is the oplog stored?
7. How does the oplog differ from the journal/backup?
8. Is replication instantaneous synchronous or asynchronous?
9. What impacts does replication lag cause?
10. When does initial sync take place?
11. What is the election majority with three voters?
12. Why can losing one node in P-S-S still usually elect a primary?
13. Why can a single remaining voter not elect a primary in a three-vote replica set?
14. Does an arbiter store data?
15. Can an arbiter become primary?
16. How does P-S-A differ from P-S-S in the number of data-bearing members?
17. Why might P+A have enough votes yet still fail to ack `w:"majority"`?
18. What does priority 0 mean?
19. What does votes 0 mean?
20. What is the purpose of a hidden secondary?
21. Does a delayed secondary replace backups?
22. What question does read preference answer?
23. How does read concern differ from read preference?
24. Why can a majority read from a secondary still be stale?
25. What does `w:1` mean?
26. What does `w:"majority"` mean?
27. Does `wtimeout` prove the write did not occur?
28. Which types of writes can be affected by rollback?
29. Why should you not hard-code the primary host?
30. Why are three processes on one machine insufficient for HA across failure domains?
31. Which metrics should be monitored to detect lag?
32. What may a secondary offline beyond the oplog window need to do?
33. Does replication recover accidental deletions?
34. What are RPO and RTO?
35. Why must production topologies verify both votes and data copies?

---

## 29. Summary

A MongoDB Replica Set maintains multiple members to increase **availability** and **data redundancy**. In a typical setup, the **primary** accepts writes and records the oplog; **secondaries** replicate changes, maintain copies, and can participate in elections. Replication is asynchronous, so secondaries can lag.

Principles to remember:

- **Primary** is the elected writable member, not a fixed host.
- **Secondaries** store data, synchronize via the oplog, and can be elected primary if eligible.
- **Majority voting** protects elections, but does not mean having enough data copies.
- **P-S-S** normally has three data copies and is more suitable for redundancy than **P-S-A**.
- **Arbiters** hold a vote without data and cannot substitute for a secondary to ack `w:"majority"`.
- **Read preference** determines where to read; **read concern** determines visibility guarantees; **write concern** determines write acknowledgment guarantees.
- **Replication lag** causes stale data on secondaries; **w:1** carries a higher rollback risk than majority in applicable scenarios.
- **Backup/PITR** remains mandatory for recovering accidentally deleted data or disasters.
- **Production readiness** also requires failure domains, TLS/auth, monitoring, backups, runbooks, and failover tests.

The right question when designing a replica set is not merely **"how many machines are there?"**, but rather: **"are there enough votes to have a primary, how many actual data copies remain, and what read/write guarantees does the application need during an incident?"**

## Official MongoDB Reference Documentation

- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/)
- [MongoDB Manual — Replica Set Primary](https://www.mongodb.com/docs/manual/core/replica-set-primary/)
- [MongoDB Manual — Replica Set Secondary](https://www.mongodb.com/docs/manual/core/replica-set-secondary/)
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [MongoDB Manual — Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set Data Synchronization](https://www.mongodb.com/docs/manual/core/replica-set-sync/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Replica Set Write Concern](https://www.mongodb.com/docs/manual/core/replica-set-write-concern/)
- [MongoDB Manual — Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.conf()](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB Manual — db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Java Sync Driver — Connection Guide](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
