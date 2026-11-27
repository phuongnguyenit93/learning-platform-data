# Decision Matrix for Read Concern, Write Concern, and Read Preference in MongoDB

## 1. Three Configuration Knobs — Three Different Questions

In MongoDB, a read or write operation on a replica set or sharded cluster is governed by three concepts:

1. **Read concern**: what guarantees does the returned data have regarding durability, snapshot consistency, and observation order?
2. **Write concern**: how many members must acknowledge a write, and is journal flushing required, before MongoDB returns success?
3. **Read preference**: which **member** does the driver select to execute a read — primary or a secondary?

They address **three orthogonal dimensions**. For example:

```text
                     Java / mongosh client
                              |
                              v
                    Read preference
                (selects server to read)
                              |
                +-------------+-------------+
                |                           |
             PRIMARY                    SECONDARY
                |                           |
                +-------------+-------------+
                              |
                              v
                       Read concern
                  (data state observed)

Client -- write operation --> PRIMARY
                               |
                               v
                          Apply write
                               |
                               v
                         Write concern
                 (write acknowledgment level)
                               |
                        Acknowledgment
```

**Common misconception:** `readPreference=secondary` does not mean `readConcern=majority`. Reading from a secondary does not automatically return the latest data. Conversely, `readConcern=majority` does not force reading from a secondary; it can be used on the primary.

### 1.1. Running Context

An account management system on a three-data-bearing-member replica set:

```text
              Replica set rsOrders

          +---------- PRIMARY P ----------+
          |  receives writes              |
          |  emits oplog                  |
          +-------------------------------+
                       |        |
                 replicate   replicate
                       v        v
                SECONDARY S1  SECONDARY S2

               Java service / mongosh
```

The application has varying requirements:

- Reading the product listing page: wants low latency and tolerates slightly stale data.
- Displaying the balance immediately after a transfer: cannot accept showing an outdated balance.
- Recording a payment: needs results durable across failovers.
- Analytical reporting: wants a consistent snapshot without mixing multiple points in time.
- Health dashboard: can accept approximate data to offload the primary.

Do not apply a single read concern / write concern / read preference setting across all cases without considering business semantics.

### 1.2. Learning Objectives

After this lesson, you will be able to:

1. Identify the meaning and limits of each read concern level.
2. Explain `w:0`, `w:1`, `w:"majority"`, `w:n`, custom tag write concerns, and `j`.
3. Select `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, or `nearest` read preference.
4. Distinguish **majority-committed** from **latest**, **read-your-writes**, **causal consistency**, **linearizability**, and **snapshot consistency**.
5. Design appropriate configurations for CRUD, reporting, audit, payments, background jobs, and consumers.
6. Use the Java Sync Driver and `mongosh` to set concerns/preferences at client, database, collection, and transaction levels.
7. Understand the impact of replication lag, elections, network partitions, journaling, timeouts, and sharded clusters.
8. Create a test matrix, metrics/runbooks, and trade-off decisions across latency, availability, and durability.

**Scope:** focuses on MongoDB replica sets and sharded clusters in modern versions. Supported features and concern levels vary by version, storage engine, and command type; always verify the specific command and target deployment. Write/delete examples must only run in an owned test database.

## 2. Quick Reference Table: Read Concern

| Read concern | Runs on | Core meaning | Can observe rolled-back data? | Guaranteed latest? | Common use cases |
|---|---|---|---|---|---|
| `local` | Eligible primary/secondary | Returns current data on the targeted member without waiting for majority commit | **Possible** | **Not guaranteed** | Standard queries prioritizing latency |
| `available` | Certain contexts, notably sharded | Prioritizes availability, no majority guarantee; on sharded clusters has orphaned data caveats | **Possible** | **No** | Specialized cases with well-understood trade-offs |
| `majority` | Supported primary/secondary | Returns data that is majority-committed per corresponding semantics | Not under normal rollback of majority-committed data | **No** | Data that must avoid seeing easily rolled-back writes |
| `linearizable` | **Primary** | Reads a single document with linearizability under MongoDB-supported conditions | No, under linearizable conditions | Strongest for real-time single-document reads, but may wait/fail | Reading lock state or ultra-sensitive business decisions |
| `snapshot` | Transactions, and certain non-transaction reads on supported servers | Consistent snapshot at a single logical point in time | Per applicable snapshot/commit semantics | **Not guaranteed to be absolute current** | Transactions, reconciliation/reports needing consistent snapshots |

**Reading the table properly:** "cannot observe rolled-back data" does not mean "sees the latest write." A secondary may lag behind the primary even when reading with `majority`. And a `snapshot` may be completely consistent **at a past point in time**.

### 2.1. Opening Questions

- Must reads avoid seeing data from a write that is later rolled back?
- Must a read reflect the result of the exact request just written?
- Must a read reflect **every** write that completed before the read began?
- Must multiple commands in a transaction observe the same snapshot?
- Can the operation tolerate waiting or failing during failover or network partitions?

## 3. Quick Reference Table: Write Concern

| Write concern | Condition to return acknowledgment | What it does not guarantee | Trade-off |
|---|---|---|---|
| `w:0` | Does not request write acknowledgment | Whether command succeeded, validation errors, durability | Minimal wait for response, high risk |
| `w:1` | Primary confirms command was applied | Does not guarantee replication or majority commit | Lower latency, rollback risk after failover |
| `w:"majority"` | Required number of voting/data-bearing members acknowledge per majority semantics | Not synchronous on all members, not exactly-once business outcome | More durable across failovers, latency/availability cost |
| `w:2` or `w:n` | Specified number of eligible members acknowledge | Does not automatically equal majority in all topologies | Coupled to topology and member count |
| Custom tag write concern | Meets custom write concern mode per replica set tag configuration | Invalid if mode or replica set config is incompatible | For specialized placement/policy needs |
| `j:true` | Requires acknowledgment per supported journal option | Does not replicate to multiple nodes when `w:1` | Durability/disk I/O cost |
| `wtimeout` | Caps time spent waiting for write concern conditions | Does **not** cancel an already applied write | Produces an uncertain state requiring handling |

**Remember:** `wtimeout` (or URI `wtimeoutMS`) only limits **how long to wait for the write concern condition**; on timeout, the operation may already have been applied on the primary. Never blindly retry a **non-idempotent** business action such as transferring money twice.

## 4. Quick Reference Table: Read Preference

| Read preference | Server selected | Fallback | When to consider | Pitfalls |
|---|---|---|---|---|
| `primary` | Primary only | No secondary fallback | Writes, simple read-after-write, transactions | Reads fail if primary is overloaded or unavailable |
| `primaryPreferred` | Primary if eligible | Secondary when no primary exists | Controlled read availability | During failover, reads can suddenly jump back to stale data |
| `secondary` | Eligible secondaries only | **No** primary fallback | Offloading reporting/batch reads | Fails if no eligible secondary exists |
| `secondaryPreferred` | Secondary if available | Primary when no eligible secondary exists | Offloading with fallback | Tests may assume secondary reads while silently hitting primary |
| `nearest` | Eligible member with lowest measured latency per driver selection | No strict primary/secondary distinction | Stale-tolerant, latency-optimized workloads | Does not mean "latest," nor necessarily same region |

Read preference also supports:

- **Tag sets** to filter/prefer members with labels such as region or workload.
- **`maxStalenessSeconds`** to cap estimated relative secondary lag (not an absolute freshness guarantee).
- **`localThresholdMS`** to pick among servers within a latency window, per driver settings.

## 5. Reading All Three Tables in One Target Matrix

| Business Goal | Read Concern | Read Preference | Related Write Concern | Notes |
|---|---|---|---|---|
| Product catalog less sensitive to freshness | `local` or `majority` depending on rollback risk | `secondaryPreferred` if stale is acceptable | `w:1`/`majority` per required durability | Fallback may switch servers |
| Read order by ID, preferring latest on primary | `local`/`majority` per policy | `primary` | `majority` if surviving failover matters | Primary alone does not give linearizable guarantees |
| Read-your-writes in the same causal session | `majority` | `primary` or causally eligible secondary | `majority` | Requires client session and ordered operations |
| Payment/audit record must avoid acknowledged rollback | `majority` for sensitive reads | `primary` | `majority`, journaling per deployment | Requires business idempotency |
| Single document holding lock/decision state needing linearizability | `linearizable` | `primary` | Related writes use `majority` | May be slow/fail in partitions; single-document semantics only |
| Multi-read report needing one consistent snapshot | `snapshot` in transaction / supported snapshot reads | `primary` in transaction | Transaction commit `majority` | Mind transaction lifetime/age limits |
| Auxiliary report tolerant of lag | `majority` to avoid rollbacks, or `local` if tolerated | `secondary`/`nearest` with tags | `majority` for critical source writes | Monitor lag and `maxStaleness` |
| Change stream consumer | MongoDB stream semantics, not regular `find` table | Per stream/server support | Source writes `majority` if durable ack needed | Resume tokens, oplog window, idempotency |
| Protect source data against primary failover | Per read requirement | Usually `primary` for critical reads | `majority` | Majority does not mean every secondary has seen it |

This table is a **starting point**, not a one-size-fits-all config. Always verify command version/feature constraints and business SLAs before applying.

## 6. Defaults: Never Guess From Code Without Explicit Options

### 6.1. Common Defaults

- Typical driver default read preference is **`primary`**.
- Typical default read concern for most operations is **`local`** unless overridden at the appropriate level.
- Default write concern **is not always `w:1`**. Modern MongoDB servers apply implicit default write concern rules that depend on topology (especially setups with arbiters), and clusters can configure admin-level default read/write concerns.

### 6.2. Danger Sign

```java
MongoClient client = MongoClients.create(uri);
collection.insertOne(doc);
```

You cannot deduce exact write durability from those two lines alone. Check the URI, client/database/collection settings, transaction options, server default RW concern, and server version/topology.

### 6.3. Configuration Inheritance and Overrides

```text
MongoDB deployment defaults
            |
MongoClientSettings / connection string
            |
MongoDatabase overrides
            |
MongoCollection overrides
            |
Operation / session / transaction-specific options
```

Not every operation supports overrides the same way; transactions have their own scope. Driver and server documentation for the specific operation is the final authority.

### 6.4. Default Write Concern Can Shift When Topology Changes

Moving from a three-data-bearing-member replica set to a primary-secondary-arbiter (PSA) changes the implicit default write concern and majority availability. For sensitive workflows, **specify requirements explicitly** and verify that the deployment satisfies them.

## 7. Read Concern `local`: Fast Reads, Not Yet Majority-Committed

`local` reads the current data on the selected server without requiring majority acknowledgment.

Example:

```text
T0: primary P applies order.status="PAID"
T1: client reads P with readConcern local -> sees "PAID"
T2: P loses majority before write replicates sufficiently
T3: a secondary becomes primary; old write may roll back
```

The client observed a state that never became part of the replica set's committed history.

### 7.1. Effect on Secondaries

`readPreference=secondary` + `readConcern=local` can read data applied on a secondary that is not yet majority-committed, and typically lags behind the primary.

### 7.2. When Is It Reasonable?

- Lookup UIs insensitive to a non-majority-committed change.
- Temporary telemetry/reports that tolerate non-final results.
- Workloads with existing reconciliation or eventual consistency.
- When speed is prioritized and the business accepts rollback/stale views.

### 7.3. Never Use `local` as Proof That a Write Is Durable

Reading a value on the primary does not mean that write has replicated far enough to survive a failover.

### 7.4. Compared With `w:1`

`w:1` describes **write acknowledgment**; `local` describes **what data a read can observe**. They often align in latency expectations, yet remain two independent settings.

## 8. Read Concern `available`: Use Deliberately

`available` does not wait for majority-committed data and prioritizes availability. In **sharded clusters**, MongoDB carries an important caveat: `available` queries can return **orphaned documents** during certain chunk migration scenarios.

### 8.1. What Is an Orphaned Document?

When a chunk migrates between shards, old copies may temporarily remain on the source shard prior to cleanup. Standard routing excludes those leftover source copies as non-authoritative.

### 8.2. Why Is This Dangerous for Reports?

If a query observes both the old copy and the migrated copy during an awkward window, reports can double-count or reflect unexpected records.

### 8.3. Usage Scope

Use `available` only when you **clearly understand** why behavior different from `local` is needed, the deployment supports it, and orphaned results are acceptable. Never pick `available` simply because its name sounds "always up."

### 8.4. On Replica Sets

In many ordinary replica set operations, `available` behaves similarly to `local` regarding visible data; still verify version support and semantics.

## 9. Read Concern `majority`: Committed, Yet Not Necessarily Latest

`majority` returns data that has been **majority-committed** according to the deployment's replication and commit-point rules.

### 9.1. Illustrative Timeline

```text
P  : v1 ---- v2 ---- v3
S1 : v1 ---- v2
S2 : v1

Current commit point may be at v2 (depending on acknowledgments).

Read majority on S2:
  may still return v1 because S2 has not yet applied v2.
```

Key property to remember: **majority does not mean newest**. A secondary can return majority-committed data older than the newest state on the primary.

### 9.2. When to Prefer It?

- Reports must not depend on writes that could roll back under normal replication mechanics.
- Audit or critical reads require stronger assurance of committed history than `local`.
- Causal consistency within a session when paired with `w:"majority"`.
- Pre-decision reads must rely on stable, committed state without requiring real-time linearizability.

### 9.3. Insufficient for Read-Your-Writes Across Members

A client writing with `w:majority` and then reading from a secondary with `readConcern=majority` **without** a causal session/`afterClusterTime` can observe stale values if that secondary is lagging.

### 9.4. Does Not Prove Every Secondary Has Applied the Write

In a three-data-bearing-member replica set, majority is 2. The third member may still be behind.

### 9.5. Errors and Latency

`majority` reads may wait for the commit point, especially under replication lag or loss of majority. Configure clear timeouts/deadlines and matching SLOs.

## 10. Read Concern `linearizable`: Single-Document Real-Time Ordering

Linearizable reads aim to ensure that for supported **single-document read operations** on the primary, a read starting after a related majority-acknowledged write completes will not return pre-write history in a way that violates real-time order.

### 10.1. Visual Comparison

```text
Client A: write lock.owner="A" with majority
             |---------- completed ----------|

Client B:                                  |--- read begins ---|

Linearizable read:
  must be consistent with completed majority write
  or may wait/fail if guarantee cannot be met.
```

### 10.2. How Does It Differ From `majority`?

- `majority` focuses on majority-committed history.
- `linearizable` adds **real-time ordering** guarantees for a single-document read relative to majority writes.

### 10.3. Essential Prerequisites

- Must execute on the **primary**.
- Applies only to supported **single-document read** shapes.
- Writes participating in the guarantee must use `w:"majority"`.
- Do not treat linearizable reads as a multi-document transaction snapshot.
- Requires `maxTimeMS` to avoid waiting indefinitely when majority is unavailable.

### 10.4. Example

An application checks a document:

```javascript
{
  _id: "leader-lock:billing",
  owner: "worker-17",
  leaseEpoch: NumberLong("42")
}
```

When decisions are sensitive to a majority-acknowledged lock, a linearizable read fits well. However, to prevent stale workers, **lease fencing and compare-and-set on writes** remain mandatory: a linearizable read alone does not turn read-then-write into an atomic transaction.

### 10.5. Do Not Use for General UIs

Linearizable reads increase latency and reduce availability during partitions. Using them by default on a 100,000-item catalog listing adds needless cost.

## 11. Read Concern `snapshot`: Multiple Operations Observing One Logical Time

`snapshot` enables reading a consistent snapshot per MongoDB capabilities.

### 11.1. Inside a Transaction

```text
T0 transaction starts
T1 reads account A
T2 concurrent writer changes account B
T3 transaction reads account B

Snapshot semantics:
  transaction sees a consistent snapshot,
  not an arbitrary mixture of unrelated times.
```

### 11.2. Outside a Transaction

In supported MongoDB server versions (e.g., 5.0+ for listed operations), read concern `snapshot` also works on **selected non-transaction read commands** like `find`/`aggregate`/`distinct` per server semantics. Do not assume every command or version supports it.

### 11.3. AtClusterTime and Snapshot Time

When reading at a specific point in time on supported versions/operations, `atClusterTime` specifies a logical timestamp within the server's retained snapshot/history window; do not pick an arbitrarily old timestamp expecting the server to retain every version forever.

### 11.4. Snapshot Is Not Newest

An exact snapshot at `T0` excludes writes committed at `T1`. It solves **cross-read consistency**, not "must be latest."

### 11.5. Transaction Lifetime Limits

Long-lived transactions retain historical data, pressure WiredTiger cache, and abort once exceeding configured lifetime limits. Never open a multi-hour transaction to scan the entire database just to keep a report static.

### 11.6. Snapshot Read Concern and Commit Write Concern

Inside a transaction, durability and majority semantics depend on the **commit write concern**. Do not assume a `readConcern:"snapshot"` transaction committed with `w:1` offers the same guarantees as a majority-committed transaction.

## 12. Choosing Read Concern by Data Requirement

| Question | Answer | Selection Guidance |
|---|---|---|
| Can you tolerate reading a write that is later rolled back? | Yes | `local` may fit |
| Must reads only see majority-committed data? | Yes | `majority` |
| Do you require real-time single-document ordering? | Yes | `linearizable` + majority writes + primary |
| Do multiple reads need the same logical snapshot? | Yes | `snapshot` with transaction/supported operation |
| Simply want lowest latency under any condition? | Yes, accepting risk | Consider `local`/`available` per deployment |
| Must a secondary read always return the latest write? | Yes | Cannot be guaranteed by `secondary` alone |

**Separate your goals:** **freshness**, **durability**, and **consistency** are not solved by a single configuration switch.

## 13. Write Concern `w:0`: No Acknowledgment Does Not Mean Success

`w:0` is an unacknowledged write. The client does not wait for server confirmation the way acknowledged writes do.

```text
Client sends write
      |
      +--> does not wait for normal write acknowledgment
      |
      v
Client continues
```

### 13.1. Risks

- No certainty the server received or applied the write.
- No reliable write result to distinguish duplicate keys or validation failures via normal acknowledgments.
- Unsuitable for orders, payments, or audits needing confirmed outcomes.
- Complicates recovery because the application proceeds blindly.

### 13.2. Not Equivalent to Safe Fire-and-Forget

Low-criticality telemetry or logs might accept weak durability by design, yet if the data actually needs to be stored reliably, a proper queue or telemetry pipeline is safer than silently using `w:0`.

### 13.3. Compatibility

Commands, sessions, and retryable writes have specific support rules. Do not assume `w:0` operations participate in transactions or retry semantics like acknowledged writes.

## 14. Write Concern `w:1`: Accepted by Primary, Not Safe From Rollback

`w:1` requires the primary to acknowledge applying the write, without waiting for a majority of replica set members.

### 14.1. Timeline

```text
T0 client sends write to P
T1 P applies write
T2 P returns w:1 success
T3 P fails before S1/S2 replicate
T4 election chooses new P
T5 old unreplicated write may be rolled back
```

The application received success at `T2` yet can still lose the write after an election.

### 14.2. When Is It Acceptable?

- Reconstructible or reconcilable data.
- Workloads with lower durability SLAs.
- Another protected event log/source of truth exists.
- Latency is top priority and the business explicitly accepts the risk.

### 14.3. `j:true` With `w:1`

Requiring journal acknowledgment per storage engine semantics **does not** force replication to a majority. It helps against certain local crashes, yet failing over to another secondary can still roll back an uncommitted-to-majority write.

### 14.4. Do Not Lump Every Ack Under "Durable"

"Durable" must specify against which failure: process crash, power loss, primary election, regional outage, human error, or logical corruption? Write concern addresses **part** of the picture; topology, backups, app idempotency, and disaster recovery remain essential.

## 15. Write Concern `w:"majority"`: Majority Commitment

In a three-data-bearing-member replica set, two members are required for majority.

```text
P  applied + acknowledged  ---> 1
S1 applied + acknowledged  ---> 2
S2 still behind            ---> not needed for majority

writeConcern w:majority satisfied
```

### 15.1. What Does It Guarantee?

A majority-acknowledged write is designed not to roll back under normal election and replication rules, subject to durability assumptions, journal/storage-engine configuration, and system behavior.

### 15.2. Does Not Mean Every Secondary Has Seen It

Secondary `S2` may still lag. Reading `S2` right after the write can return stale state; `w:"majority"` does not imply "every read immediately sees the new value."

### 15.3. Does Not Mean Application-Level Exactly-Once

If the server wrote the record yet the response was lost, the caller may retry the business request. Issuing another `$inc` under a new transaction ID still duplicates the business effect. You still need idempotency keys, unique constraints, or transaction protocols.

### 15.4. Latency

Acknowledgment latency includes waiting for enough replica set members across topology, network, journal, and current load. When secondaries lag or majority is lost, commands wait, time out, or fail.

### 15.5. Default Majority Is Not Fixed at 2

With 5 voting members, majority is 3. When arbiters exist, data-bearing votes and acknowledgment eligibility require careful analysis—never compute majority just by "counting containers."

## 16. Write Concern `w:n`, Tag Modes, and Topology

MongoDB supports member-count write concerns (such as `w:2`) and custom write concern modes backed by replica set tags under supported conditions.

### 16.1. Counting Members Does Not Always Equal Majority

| Voting members | Majority votes | Is `w:2` a majority? |
|---:|---:|---|
| 3 | 2 | Matches numerically, still verify semantics/config |
| 5 | 3 | **No** |
| 7 | 4 | **No** |

Choose `w:"majority"` when you truly want majority semantics rather than hardcoding `w:2` for a current topology.

### 16.2. Tag-Aware Write Concern

For instance, nodes tagged `region=apac`, `region=eu`, `region=us`. A custom write concern mode can require acknowledgment across a desired tag distribution as defined in the replica set configuration.

### 16.3. Does Not Automatically Promise Multi-Region Durability

Tag policies must be tested against replica set votes, data-bearing member counts, config, and network partitions. Satisfying a tag write concern does not by itself deliver full application DR and regional failover.

### 16.4. Unrelated to Indexing

Write concern is not an index option; it is configured at client, operation, transaction, or server-default level. Enforcing business uniqueness with a unique index is a **separate** mechanism.

## 17. Journal Option `j` and What "Durable" Means

In MongoDB with WiredTiger, the journal records changes to support recovery under specific crash or power-loss conditions.

### 17.1. Combining `w` and `j`

| Setting | What You Request | What You Should Not Infer |
|---|---|---|
| `{w:1}` | Primary acknowledges apply | No guarantee of journal flush or replica copies as desired |
| `{w:1,j:true}` | Primary acknowledges per journal semantics | No majority replication |
| `{w:"majority"}` | Majority acknowledgment per server config | Does not mean every node or region retains data |
| `{w:"majority",j:true}` | Majority acknowledgment plus journal request where supported | Does not replace backups or provide business exactly-once |

### 17.2. `writeConcernMajorityJournalDefault`

Durability tied to majority journaling also depends on server and storage-engine configuration. Some deployments carry exceptions or options altering journal behavior. When designing SLAs, check **effective server values**, not just the connection string.

### 17.3. `j:true` Can Increase Latency

Journal I/O has a cost; benchmark write-heavy workloads on real storage, replication, network, and disks.

### 17.4. Do Not Treat `j:true` as RAID or Backups

Journaling does not protect against accidental collection drops, ransomware, buggy deployments, or catastrophic multi-node/regional loss. Use backups/PITR, versioning, guardrails, and restore tests.

## 18. `wtimeout` and Ambiguous Write Outcomes

Command example:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "W471-01",
      status: "CREATED"
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
});
```

Inside a command's `writeConcern`, `wtimeout` is in **milliseconds**.

### 18.1. What Is a Write Concern Timeout?

The primary may have applied the write, yet failed to gather the required write concern acknowledgments within the timeout budget. The result may include a `writeConcernError`, or the driver throws the corresponding exception.

### 18.2. Does Not Mean the Write Rolled Back

```text
T0 primary applies insert
T1 no majority confirmation within budget
T2 write concern timeout returned
T3 secondaries catch up later

Final state:
  record may exist.
```

### 18.3. Business Retries

For an "order creation" action, use a deterministic request ID:

```javascript
{
  _id: "order:client-request-471",
  requestId: "client-request-471",
  status: "CREATED"
}
```

Backed by a unique index on business request identity, retries can look up the prior operation before deciding. Never generate a new `ObjectId` and insert a second time without checking.

### 18.4. Distinguishing Timeout Types

| Timeout | Scope | Implication |
|---|---|---|
| `wtimeout`/`wtimeoutMS` | Waiting for write concern satisfaction | Write may already be applied |
| Server selection timeout | Driver locating primary/eligible member | Command may never have been sent; check attempt details |
| Socket timeout | Network wait/I/O | Outcome unknown once request was sent |
| `maxTimeMS` | Server-side operation time limit where supported | Check command semantics; do not assume auto-rollback of all side effects |
| Transaction timeout | Transaction lifetime/behavior limit | Commit outcome must be checked separately |

### 18.5. Do Not Blindly Retry Every Exception

Classify error labels, error codes, and business invariants. A duplicate key error might indicate an earlier idempotent request succeeded—or a genuine conflict; never blindly treat it as success unless payloads match.

## 19. Write Concern in a Replica Set With an Arbiter

A **P–S–A** replica set:

```text
P  = primary, stores data
S  = secondary, stores data
A  = arbiter, votes but stores no data

Votes: 3; election majority: 2
Data-bearing members: P, S
```

### 19.1. Why Cannot an Arbiter Replace a Data Copy?

An arbiter neither receives nor stores replicated data like a secondary. When `S` goes offline, `P + A` may supply enough votes for certain election situations, yet it **does not** allow new writes on `P` to achieve the majority data acknowledgment required by MongoDB semantics.

### 19.2. The Surprise

A PSA cluster may continue accepting `w:1` writes during certain partitions while blocking or timing out `w:"majority"` writes whenever data-bearing `S` is unavailable.

### 19.3. Default Write Concern Changes With Topology

In modern MongoDB versions, the implicit default write concern depends on the count of arbiters and data-bearing voting members; on certain arbiter topologies, the default becomes `w:1` instead of `majority`. Never rely on implicit defaults as an SLA.

### 19.4. Production Design

A replica set with three **data-bearing** members generally offers better majority data availability and failover resilience than P–S–A when infrastructure permits. Always evaluate sizing, voting, regions, and write concern for the target deployment.

## 20. Read Preference `primary`: Default Primary Read Path

`primary` reads exclusively from the primary. This is typically the default and is appropriate when:

- Read-after-write must avoid secondary lag, where the contract does not demand linearizability beyond that.
- Transactions or sessions require primary selection.
- Administrative operations require the primary.
- Data is critical and silent fallback to secondaries is unwanted.

### 20.1. Primary Does Not Mean Linearizable Read

Reading with `local` on the primary can observe an un-majority-committed write that later rolls back. Reading with `majority` on the primary lacks the real-time ordering guarantee of `linearizable`.

### 20.2. Failover

When the driver sees no primary, `primary` reads wait during server selection and eventually fail. Do not blindly "fix" this by switching to `secondaryPreferred` if the business rejects stale views.

### 20.3. Load

Routing all heavy reporting reads to the primary creates contention with writes. Split analytical read paths under separate SLAs when needed.

## 21. Read Preference `primaryPreferred`: Prefer Primary With Fallback

`primaryPreferred` selects the primary when available and falls back to an eligible secondary when no primary exists.

### 21.1. Benefits

Applications can continue reading certain data during an election or network disruption if a secondary is reachable.

### 21.2. Risks

A request right before failover reads a newer primary, while the next request falls back to an older secondary; without causal coordination, the application can observe data "going backward."

### 21.3. Avoid for Sensitive Authorization Decisions

If the app authorizes actions or disburses funds based on state where a secondary may lag, silent fallback is hazardous.

### 21.4. Observability

Command monitoring and SDAM metrics should report which actual host and role executed each command, rather than assuming based on configured preference.

## 22. Read Preference `secondary`: Offload Without Fallback

Selects only secondaries matching topology, tag, and staleness rules. If no matching server is found within timeout, the read fails.

### 22.1. Use Cases

- Reports or exports tolerant of replication lag.
- Read-heavy workloads isolating the primary.
- Analytical batches equipped with retries, backoff, and freshness policies.

### 22.2. Does Not Force Returning the Latest Version

`readConcern=majority` on a secondary avoids un-majority-committed data per semantics, yet does not force that secondary to catch up to the latest majority-acknowledged write.

### 22.3. Max Staleness and Tags

You can filter secondaries by estimated staleness and tags, yet setting a tiny number does not guarantee "never older than 2 seconds." Drivers and servers enforce minimum thresholds and estimation windows.

### 22.4. Testing Real Secondary Reads

A test calling `secondary()` against a single-node replica set **has no secondary** and fails; that is not a read concern bug. Testing secondary reads requires a multi-data-bearing-member replica set.

## 23. Read Preference `secondaryPreferred`: Offload With Primary Fallback

Tries eligible secondaries first; if none are available, falls back to the primary.

### 23.1. Good Fit

- Dashboards or reports prioritizing offload.
- Willing to fall back to primary to reduce read errors.
- No strict requirement to keep reads off the primary at all times.

### 23.2. Poor Fit

- SLAs requiring that heavy reports **never** run on the primary.
- Tests asserting queries must execute on a secondary.
- Correctness requirements needing an explicit freshness policy rather than implicit fallback.

### 23.3. Tags Can Affect Fallback

When configuring tag sets alongside server selection, inspect driver/read-preference rules carefully; the primary does not carry secondary tag selection rules identically across all modes. Never assume configured tags apply identically to a fallback primary.

## 24. Read Preference `nearest`: Network Latency, Not Write Time

`nearest` picks an eligible member whose measured network latency falls within the fastest window per driver selection—not necessarily primary, geographically closest, or most up-to-date.

### 24.1. Example

```text
P  RTT 20 ms
S1 RTT 7 ms
S2 RTT 8 ms

nearest may pick S1/S2
depending on tags/local threshold/selection state.
```

### 24.2. Freshness

`nearest` pays no attention to recent writes unless paired with causal/consistency mechanisms. A low-RTT member can lag significantly in replication.

### 24.3. Local Threshold

The driver selects among servers whose latency is sufficiently close to the fastest server. Tuning `localThresholdMS` does not change consistency guarantees.

### 24.4. When Is It Reasonable?

Reading freshness-insensitive event history or metadata across distributed regions after validating tag, freshness, and tier policies; avoid it for payment states.

## 25. Max Staleness: A Secondary Selection Filter, Not a Consistency Level

`maxStalenessSeconds` caps how far behind a secondary is estimated to be relative to driver-tracked benchmarks, excluding overly lagging secondaries from candidate selection.

### 25.1. Not a Read Concern

`readConcern=majority` governs majority-committed data. `maxStalenessSeconds` governs **server selection**. Neither replaces the other.

### 25.2. Not an Absolute Freshness SLA

If all servers lag behind an external event source, relative max staleness does not prove returned values are "no older than N wall-clock seconds."

### 25.3. Minimum Supported Threshold

MongoDB drivers enforce a lower bound on `maxStalenessSeconds` (in modern drivers/versions, typically around **90 seconds** unless disabled). Do not set `maxStalenessSeconds=2` assuming the driver will enforce 2-second freshness.

### 25.4. Monitoring

Measure actual replication lag and end-to-end read freshness. If an application requires read-your-writes at a tight bound, use sessions/primary/causal protocols rather than max staleness alone.

## 26. Read Preference Tag Sets and Topology Placement

Replica set members carry tags (for example `region=apac`, `workload=reporting`) in configuration.

```text
P:  region=apac, workload=oltp
S1: region=apac, workload=reporting
S2: region=eu,   workload=reporting
```

### 26.1. Use Cases

- Preferring secondaries in regions close to the application.
- Isolating dedicated reporting nodes.
- Avoiding specific data centers for read traffic.

### 26.2. Tag Sets Are an Ordered Priority List

Drivers accept an ordered list of tag sets per read preference specification. If the first tag set yields no eligible member, the driver evaluates subsequent sets depending on mode and rules.

### 26.3. Tags Do Not Enforce Data Residency by Themselves

Data residency and compliance require verifying storage placement, backups, logs, exports, failover behavior, access control, and legal rules. Tag-based read routing alone does not form a complete compliance boundary.

### 26.4. Never Select Tags From Raw User Input

API clients must never supply arbitrary replica set tags to steer data sources. Select tags via verified service policy.

## 27. Causal Consistency: Ordering Guarantees Within a Session

Causal consistency helps related operations within a session preserve guarantees such as:

- **Read-your-writes**: after a write, subsequent reads in the causal session see its effect when conditions are met.
- **Monotonic reads**: reads do not move backward in time across a causal sequence.
- **Monotonic writes**: related write order is preserved per semantics.
- **Writes-follow-reads**: writes following a read reflect the corresponding causal relationship.

### 27.1. Typical Requirements for Full Causal Guarantees

Use **causally consistent sessions** with **`readConcern:"majority"`** and **`writeConcern:"majority"`**, and execute operations in proper **sequence** within the session.

### 27.2. Timeline

```text
Session S:
  1) write order.status="PAID" with w:majority
  2) read order from eligible member with readConcern majority
     and causal time tracking

Driver/server coordinate causal position:
  read should not silently return state prior to own
  successful majority write.
```

### 27.3. Why Is Plain Secondary Reading Not Enough?

Without session causal timing, the driver only knows the secondary can return majority data, without tying the read point to the cluster time of the client's prior write.

### 27.4. Do Not Treat Everything Sharing a User Token as One MongoDB Session

An HTTP session or JWT is not a MongoDB `ClientSession`. Request 1 hitting pod A and Request 2 hitting pod B may use different `MongoClient`/`ClientSession` instances. If causal continuation across HTTP requests is required, design a protocol passing causal tokens/operation times as supported by your driver and architecture—never serialize raw client session objects into JWTs.

### 27.5. Do Not Share a Session Concurrently Without Care

A Java `ClientSession` must not be shared concurrently across multiple threads unless explicitly supported by the driver. Keep session operations sequential or allocate one session per transaction/task per API rules.

## 28. Snapshot vs Causal: Two Distinct Purposes

### 28.1. Snapshot

Ensure multiple reads see the exact same logical point in time:

```text
Report:
  totalAssets at snapshot T
  totalLiabilities at same snapshot T
```

### 28.2. Causal

Ensure a subsequent read reflects a prior completed write in the same causal chain:

```text
User changes address
Then checks profile
Read must not go backwards before own update
```

### 28.3. Different From Linearizable

Linearizable is a strong real-time ordering guarantee for eligible single-document reads/writes. Causal consistency tracks causal dependencies along an operation chain; it does not force all independent clients to agree on global real-time ordering for every write.

### 28.4. You Cannot "Upgrade" Consistency by Choosing `nearest`

`nearest` or low secondary latency adds neither snapshot nor causal guarantees. Configure each layer explicitly.

## 29. Transactions: Different Concern/Preference Behavior Than Outside Transactions

Inside multi-document transactions, concerns and preferences are typically set via **TransactionOptions** / session transaction configuration.

### 29.1. Read Concern

`snapshot` is commonly used when business logic needs the transaction to see a consistent snapshot. `local` and `majority` carry distinct semantics; never apply non-transaction defaults blindly to transactions without checking.

### 29.2. Write Concern

Write concern applies at **transaction commit**, not per individual write inside the transaction the way outside-transaction writes behave. Configure an appropriate write concern at the transaction/session level.

### 29.3. Read Preference

Transactions require routing reads/writes through the primary under supported configurations. Do not configure `readPreference.secondary()` on a transaction expecting MongoDB to run the whole transaction on a secondary.

### 29.4. Callback Retry Risks

Driver transaction callbacks can be re-executed on certain transient errors. Never send emails or charge cards directly inside the callback unless guarded by an outbox or idempotency.

### 29.5. Long-Running Transactions

Snapshot history and locks/resources carry cost. Never wrap a 12-hour batch report inside a single giant transaction.

## 30. Read/Write Concern Mechanics on Sharded Clusters

```text
Java driver
     |
     v
   mongos
   /   \
  v     v
Shard A RS      Shard B RS
```

### 30.1. mongos Routing

Shard keys and query shapes govern targeted vs scatter-gather routing. Read preferences and read concerns affect server selection and data visibility, but cannot fix queries missing the shard key.

### 30.2. Read Concern `available`

Always remember the orphaned documents / chunk migration caveat. Never enable it merely thinking "it must be faster."

### 30.3. Majority and Snapshots Across Shards

An aggregation spanning multiple shards has distinct time-consistency considerations; `readConcern:"majority"` does not automatically make the entire output a **single point-in-time snapshot**. When a consistent snapshot is needed, use supported `snapshot` / transaction mechanisms.

### 30.4. Sharded Transactions

Commit and write concern coordination differ from single shards and add latency when touching multiple shards. Measure performance and verify transaction retry behavior.

### 30.5. Read Preference Does Not Force Identical Member Roles Across Shards

During a scatter query, each shard can independently select a member per preference and tags. Never assume the entire query "read from a single consistent secondary" on one server.

### 30.6. Per-Shard Failover

One shard losing its primary does not bring down `mongos` completely; operations touching that shard may stall or fail while operations targeting other shards continue.

## 31. Configuring Concerns/Preferences in the Connection String

Illustrative URI:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsOrders
  &readPreference=primary
  &readConcernLevel=majority
  &w=majority
  &journal=true
  &wtimeoutMS=5000
```

In real application configs, place the URI on **one line** and URL-encode credentials/tags properly.

### 31.1. Parameter Meanings

| Parameter | Category | Meaning |
|---|---|---|
| `replicaSet` | Topology/SDAM | Specifies replica set name |
| `readPreference` | Server selection | Selects member role for reads |
| `readConcernLevel` | Read concern | Read guarantee level |
| `w` | Write concern | Acknowledgment count/mode |
| `journal` | Write concern | Journal requirement |
| `wtimeoutMS` | Write concern | Timeout waiting for acknowledgment |
| `maxStalenessSeconds` | Read preference | Filters secondaries by staleness estimate |
| `readPreferenceTags` | Read preference | Server tags where supported |

### 31.2. Never Log Raw URIs

URIs may embed usernames, passwords, and infrastructure details. Redact credentials and never log full connection strings in production.

### 31.3. Do Not Mismatch Advertised Hostnames

In a replica set, the driver discovers members via `hello`; if hostnames in the replica set config are unreachable from the application, a seemingly valid seed URI still fails server selection. That is separate from concerns/preferences.

### 31.4. Option Precedence

`MongoClientSettings` and URI options interact via the builder/config pipeline. Centralize configuration and avoid setting conflicting values in multiple places and guessing precedence.

## 32. Java Sync Driver: Client-Level Defaults

Illustrative example for a modern driver:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class ConcernClient471 {

    public static MongoClient create(String uri) {
        WriteConcern acknowledgedMajority =
            WriteConcern.MAJORITY
                .withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS);

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .readPreference(ReadPreference.primary())
            .readConcern(ReadConcern.MAJORITY)
            .writeConcern(acknowledgedMajority)
            .build();

        return MongoClients.create(settings);
    }
}
```

### 32.1. Client Settings Have Broad Blast Radius

Databases and collections derived from the client inherit its defaults unless overridden at the appropriate level. Never set `linearizable` client-wide just because one lock-check endpoint needs it.

### 32.2. Long-Lived `MongoClient`

Normally create one `MongoClient` per cluster configuration and share its connection pools; never instantiate a fresh `MongoClient` just to run one `secondary` query.

### 32.3. Choose Majority Write Concern for Business Meaning

`w:"majority"` fits orders and payments well, yet if the cluster lacks a data-bearing majority or the workload cannot tolerate the latency, fix the topology/SLA alignment rather than silently downgrading durability.

### 32.4. Documentation and Versions

Imports and class names above follow Java Sync Driver 5.x. Projects on other versions must check their exact API and dependencies rather than assuming identical imports across driver generations.

## 33. Java Sync Driver: Database/Collection Overrides

You can create handles with distinct settings:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

MongoDatabase db = client.getDatabase("consistency_lab_471");

MongoCollection<Document> criticalOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.primary())
      .withReadConcern(ReadConcern.MAJORITY)
      .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> reportingOrders =
    db.getCollection("orders")
      .withReadPreference(ReadPreference.secondaryPreferred())
      .withReadConcern(ReadConcern.MAJORITY);
```

### 33.1. Two Handles, One Namespace

Both variables target the same `orders` collection, differing only in driver-side options. Calling `withReadPreference` does not create duplicate data.

### 33.2. Reading Reports

```java
import static com.mongodb.client.model.Filters.eq;

var reports = reportingOrders
    .find(eq("status", "PAID"))
    .maxTime(5, java.util.concurrent.TimeUnit.SECONDS)
    .limit(100);

for (Document order : reports) {
    System.out.println(order.getString("status"));
}
```

With `secondaryPreferred`, the driver can fall back to the primary. Never treat `reportingOrders` as proof that every read hit a secondary.

### 33.3. Never Send Non-Idempotent Raw Business Updates

`withWriteConcern(MAJORITY)` does not stop an API from accidentally applying `$inc` twice. Applications still need request IDs, transaction/business policies, and unique indexes.

## 34. Java Sync Driver: Using `linearizable` for a Single Document

Example fetching a system state key:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;

MongoCollection<Document> lockState =
    client.getDatabase("consistency_lab_471")
        .getCollection("locks")
        .withReadConcern(ReadConcern.LINEARIZABLE)
        .withReadPreference(ReadPreference.primary());

Document lock = lockState
    .find(eq("_id", "leader-lock:billing"))
    .maxTime(3, java.util.concurrent.TimeUnit.SECONDS)
    .first();
```

### 34.1. Single-Document Semantics

Filtering by `_id` is a supported single-document lookup per this example's design. Never apply `linearizable` broadly to aggregations or paginated lists.

### 34.2. Write Side

If a linearizable read must observe completed transitions, the corresponding writes must use `w:"majority"` alongside a clear synchronization protocol.

### 34.3. Timeout Is Essential

If the primary cannot confirm majority/leadership, a linearizable read can block. `maxTime` prevents hanging indefinitely so the client can handle the failure per policy.

### 34.4. Read-Check-Write Race

Even after a successful linearizable read, another writer can modify the lock immediately afterward. Updates still require `findOneAndUpdate`/conditional updates/transactions and fencing tokens to prevent races.

## 35. Java Sync Driver: Causal Sessions

Test snippet inserting and reading a document inside **the same causally consistent session**:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

import static com.mongodb.client.model.Filters.eq;

MongoCollection<Document> orders =
    client.getDatabase("consistency_lab_471")
        .getCollection("orders")
        .withReadConcern(ReadConcern.MAJORITY)
        .withWriteConcern(WriteConcern.MAJORITY)
        .withReadPreference(ReadPreference.secondaryPreferred());

ObjectId id = new ObjectId();

ClientSessionOptions options = ClientSessionOptions.builder()
    .causallyConsistent(true)
    .build();

try (ClientSession session = client.startSession(options)) {
    orders.insertOne(session,
        new Document("_id", id)
            .append("status", "CREATED")
            .append("amountMinor", 100000L));

    Document found = orders
        .find(session, eq("_id", id))
        .maxTime(5, java.util.concurrent.TimeUnit.SECONDS)
        .first();

    if (found == null) {
        throw new IllegalStateException("Expected own write");
    }
}
```

### 35.1. Sessions Carry Causal Metadata

The driver tracks cluster/operation times and coordinates with the server so subsequent reads do not observe state older than known operations in the causal chain. That is why an explicit session is needed.

### 35.2. `secondaryPreferred` Does Not Guarantee a Secondary Was Used

On a single-node replica set or when no eligible secondary exists, the driver reads from the primary. To verify real read-your-writes **via a secondary**, run a multi-node replica set and instrument server selection.

### 35.3. Majority Must Be Configured on Both Sides

For full official causal guarantees, operations must use both majority read concern and majority write concern per rules; merely setting `causallyConsistent(true)` while leaving writes at `w:1` is insufficient.

### 35.4. Never Run Concurrent Operations on One Session

The code above is sequential. Never pass the same session to 20 concurrent tasks when the API is not thread-safe.

## 36. Java Sync Driver: Transactions With Snapshot

Example reading and updating two account documents in a transaction:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.inc;

MongoCollection<Document> accounts =
    client.getDatabase("consistency_lab_471")
        .getCollection("accounts");

TransactionOptions txOptions = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);
    try {
        accounts.updateOne(session,
            eq("_id", "A"),
            inc("balanceMinor", -30000L));
        accounts.updateOne(session,
            eq("_id", "B"),
            inc("balanceMinor", 30000L));

        // Production: validate matchedCount and funds constraints.
        session.commitTransaction();
    } catch (RuntimeException ex) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            ex.addSuppressed(abortError);
        }
        throw ex;
    }
}
```

### 36.1. This Example Is Not a Full Payment Engine

It demonstrates transaction concerns and preferences, without handling overdrafts, idempotency, unknown commit results, transient transaction errors, business ledgers, or audit/outbox workflows.

### 36.2. Do Not Set `w` on Individual Operations Inside a Transaction

MongoDB transaction write concern is enforced at transaction commit. If a service holds collection handles with custom write concerns, understand transaction option overrides and semantics—never assume each `updateOne` inside the transaction receives independent majority acknowledgment.

### 36.3. Do Not Retry Transaction Bodies Arbitrarily

A transaction body can be re-executed on transient errors using the driver's label-based retry API; prevent duplicate external side effects and enforce a retry budget.

### 36.4. Snapshot Does Not Prevent Write Skew Without Guards

Transactions provide snapshot isolation semantics, not automatic serialization of arbitrary multi-document invariants. If two transactions read a shared condition and modify disjoint documents, evaluate write skew and constraint design.

## 37. mongosh: Running Reads With Explicit Read Concern

In the lab database:

```javascript
use consistency_lab_471;

db.runCommand({
  find: "orders",
  filter: {
    status: "PAID"
  },
  limit: 10,
  readConcern: {
    level: "majority"
  },
  maxTimeMS: 5000
});
```

### 37.1. Read Concern Attached to Read Command

The example above does not select a secondary; read preference is a separate client/server-selection policy.

### 37.2. Use the Test Database

Never run risky writes in production just for illustration. Even for `find`, keep proper query scoping, indexes, and result limits to prevent large scans.

### 37.3. Returns a Cursor

The raw `find` command returns a cursor document/result structure; `getMore` follows corresponding cursor lifecycle rules. Avoid printing sensitive payloads in full to terminals.

## 38. mongosh: Writing With Explicit Write Concern

```javascript
use consistency_lab_471;

db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "req-471-001",
      status: "CREATED",
      amountMinor: NumberLong("350000")
    }
  ],
  ordered: true,
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 5000
  }
});
```

### 38.1. Fields

- `w`: acknowledgment mode.
- `j`: journal acknowledgment option if supported by the deployment.
- `wtimeout`: milliseconds to wait for write concern (does not cancel the write).

### 38.2. Upsert/Retry

Repeating an insert with the same `_id` triggers a duplicate key error. That is not necessarily a production failure if the original request ID already succeeded, yet the application must verify payload equivalence and ownership before treating it as an idempotent success.

### 38.3. Result Can Include writeConcernError

Do not inspect only the inserted count: inspect the command result and error path, and reconcile via business policy whenever outcomes are uncertain.

## 39. mongosh: Setting Read Preference

In an interactive shell, read preference can be configured on the connection per shell API:

```javascript
db.getMongo().setReadPref("secondary");

// This query follows the connection's read preference:
db.orders.find({ status: "PAID" }).limit(10).toArray();

// To switch back to primary:
db.getMongo().setReadPref("primary");
```

### 39.1. Not Equivalent to readConcern

`setReadPref("secondary")` only controls member selection; without setting a read concern, the query has no majority guarantee.

### 39.2. Test on Multi-Member Topologies

On a single-node replica set, `secondary` finds no eligible server. Do not treat that as a misconfigured read preference.

### 39.3. Permissions and Commands

Certain admin commands or transaction operations mandate primary selection regardless of general read preference; drivers or servers reject `secondary` readPreference for those commands.

### 39.4. Shell APIs Evolve

`mongosh` and the legacy `mongo` shell differ. For production scripts, check official shell version options and avoid legacy `rs.slaveOk()` or `slaveOk()`.

## 40. Comparison Table: "Majority" on Both Sides

| Case | Effect | What It Is Still Insufficient For |
|---|---|---|
| `writeConcern:majority` | Write is majority-acknowledged per topology | Guaranteeing every secondary reads it immediately |
| `readConcern:majority` | Reads only majority-committed data | Guaranteeing it is the absolute latest write |
| Both, **without** causal session | Stronger durability and stable reads | Read-your-writes across all secondaries |
| Both, **with** causally consistent session | Adds causal ordering when used properly | Global real-time linearizability across all clients |
| `readConcern:linearizable` + majority writes | Conditional single-document real-time semantics | Multi-document snapshots or atomicity |
| `readConcern:snapshot` in transaction + majority commit | Consistent transaction snapshot and commit durability | Real-time ordering of arbitrary independent commands |

### 40.1. Test Question

> Write an order with `w:majority`, then in another sessionless request read a secondary with `readConcern:majority`. Is the newly written order guaranteed to appear?

**No.** The secondary may lag, and the read lacks causal context tying it to the write's operation time.

### 40.2. Want Simplicity and Freshness?

Within the same service needing immediate read-after-write, reading from the primary is often pragmatic; if strong guarantees across failovers or clients are required, explicitly decide whether a causal session or linearizable read (with its prerequisites) is needed.

## 41. Matrix: "Can Roll Back", "Can Be Stale", "Can Time Out"

| Configuration | Can Observe Non-Majority Write? | Can Be Stale Due to Secondary? | Can Wait for Majority? |
|---|---|---|---|
| `local + primary` | Yes | Not due to secondary, though races/failover apply | Not due to majority-read rules |
| `local + secondary` | Yes | Yes | Not due to majority-read rules |
| `majority + primary` | No under majority semantics | May not be newest depending on commit point/lag | Yes |
| `majority + secondary` | No under majority semantics | **Yes** | Yes |
| `linearizable + primary` | No under supported conditions | Real-time single-doc guarantee with majority writes | **Potentially significant** |
| `snapshot + transaction primary` | Per snapshot/commit semantics | Snapshot is not automatically current | Potentially |

### 41.1. Use This Table Carefully

"No" in the table means **not via the mechanism named in that column**, not a guarantee against concurrent updates, application bugs, or cluster-wide power failures.

### 41.2. Stale Data Can Still Be Acceptable

An end-of-day report may only need data through 23:59 yesterday. Using a snapshot or secondary can be far better than forcing real-time latest state on every query.

## 42. Separating Read Preference From the Consistency Contract

Two APIs:

```text
GET /catalog/products
GET /wallet/balance
```

### 42.1. Product Catalog

Optimizes throughput and latency, tolerating a few seconds of replication lag on price updates per business policy. Can use `secondaryPreferred` with `local` or `majority` read concern based on rollback risk and UI expectations.

**However:** when displaying price for checkout, checkout backend must validate the authoritative current price; never trust a catalog cache as the payment authority.

### 42.2. Wallet Balance

Reading a balance before authorizing a payment requires transaction/invariant design, not just `readConcern`. Use `primary` + majority writes alongside atomic conditional updates or a ledger.

### 42.3. Do Not Copy Settings Across Every Collection

One MongoDB cluster may host both catalogs and ledgers; separate repository handles and service policies instead of applying a single strong or weak global read preference everywhere.

## 43. Decision Flow: Business Correctness Before Performance

```text
Is this a WRITE?
    |
    +-- Yes --> Must the write survive normal failover?
    |              |
    |              +-- Yes --> w:majority (plus journaling policy)
    |              |
    |              +-- No  --> w:1 may be acceptable
    |                         (document risk/compensation)
    |
    +-- No --> This is a READ
                  |
                  +-- Must observe real-time completed
                  |   single-doc majority write?
                  |         -> linearizable + primary
                  |
                  +-- Must observe a consistent snapshot?
                  |         -> snapshot transaction / supported read
                  |
                  +-- Must avoid uncommitted-to-majority state?
                  |         -> majority
                  |
                  +-- Can tolerate rollback/stale reads?
                            -> local where suitable

For every READ:
  Select preference separately:
    primary (freshness/consistency path)
    secondary/nearest (offload/lag accepted)
  If causal ordering is needed:
    session + majority read/write
```

**This flow is a baseline guide.** No read concern option by itself replaces unique constraints, transactions, idempotency, or business reconciliation.

## 44. Scenario A — Create an Order and Read It Immediately

### 44.1. Requirement

Client sends:

```text
POST /orders requestId=req-471-a
GET  /orders/order-471-a
```

Once POST succeeds, the user expects to see the order.

### 44.2. Choices

- POST: `writeConcern=majority` if business rules forbid losing acknowledged writes in normal failovers.
- Immediate GET: `readPreference=primary` is simpler than reading a secondary.
- If GET may hit a secondary or route across services/requests: design causal continuation / causal sessions where supported.
- Data layer uses unique `requestId`/`_id` for safe retries.

### 44.3. What If `secondaryPreferred` Is Used?

Depending on topology, GET may hit a lagging secondary. The user just created an order yet the UI returns 404. That is a **stale read**, not necessarily a failed write.

### 44.4. Do Not Paper Over With Infinite Retries

If the API requires read-your-writes, enforce the primary route or causal rule upfront. Wrapping GET in endless polling loops hides consistency contract flaws and worsens latency.

## 45. Scenario B — Money Transfer Between Two Accounts

### 45.1. Requirement

```text
Before:
  A.balance = 100000
  B.balance = 40000

Transfer:
  A -> B: 30000

After:
  A.balance = 70000
  B.balance = 70000
```

### 45.2. Baseline Configuration

- Multi-document transaction if both account documents must change atomically.
- `readConcern=snapshot` on the transaction for a consistent view.
- `writeConcern=majority` at **transaction commit** to meet durability policy.
- `readPreference=primary` inside the transaction.
- Unique business transaction ID and ledger/audit/outbox so retries never double-transfer.

### 45.3. Why Is `majority` Alone Insufficient?

Two separate `updateOne` calls with `w:majority` can still leave a half-completed transfer if the process crashes between calls. `majority` does not merge them into an atomic unit.

### 45.4. Why Is `snapshot` Alone Insufficient?

Snapshot gives consistent reads inside the transaction; you must still enforce balance checks, concurrency conflicts, commit handling, idempotency, and unknown outcome resolution.

## 46. Scenario C — Reading a Leader Coordination Lock

### 46.1. Requirement

A scheduler must determine the current lock holder and prevent two workers from executing a critical job simultaneously.

### 46.2. Choices

- Single-document state storing `owner`, `leaseEpoch`, `leaseUntil`.
- Majority-acknowledged updates on the lock.
- Primary + linearizable read when decisions depend on real-time completed writes.
- Atomic conditional update / `findOneAndUpdate` to claim/renew.
- Fencing token `leaseEpoch` to block stale workers from emitting side effects.

### 46.3. Why Read Concern Does Not Replace CAS

```text
Worker A reads: lock free
Worker B reads: lock free
Worker A tries claim
Worker B tries claim
```

If both operations simply read and then blind-write, even linearizable reads do not prevent both workers from claiming. **Atomic conditional writes** stop the race.

### 46.4. Timeouts

Linearizable reads must carry `maxTimeMS` and matching operation timeouts; when state cannot be confirmed, workers should fail closed / stand by rather than seizing the lock due to a slow read.

## 47. Scenario D — Product Catalog and Reporting

### 47.1. Business Difference

Catalog pages can tolerate a few seconds of replication lag per SLA. End-of-month revenue reports need data reflecting a consistent point in time.

### 47.2. Catalog

Candidate: `readPreference=secondaryPreferred`, `readConcern=local` or `majority` depending on rollback tolerance. Cache TTLs and invalidation still govern end-user freshness.

### 47.3. Report

If a report is a single aggregation that does not reconcile across multiple separate reads, `majority` may suffice to exclude un-majority-committed state, though it does not guarantee a cross-operation snapshot.

If multiple reads or collections must share one logical snapshot, use `snapshot` via supported APIs within bounded duration and resource limits.

### 47.4. Never Dump Heavy Reports Onto Primary Without Assessment

Setting primary read preference for every report increases p99 write latency through contention. Balance SLOs, indexes/aggregations, secondary capacity, and consistency requirements.

## 48. Scenario E — Audit Logs and Regulatory Reporting

### 48.1. Questions to Answer

Is the audit log the source of truth? Can an event ever be lost after failover? Are hash chains or tamper-evident storage required? What are retention and backup periods?

### 48.2. Recommendations

- Writes: majority acknowledgment, journaling policy, and idempotent event IDs.
- Sensitive reads: `majority` or `snapshot` depending on report type.
- Append-only / restricted application permissions.
- Backups/PITR, retention, access auditing, and reconciliation against external systems.

### 48.3. Write Concern Does Not Create Immutability

Any principal with delete privileges can still delete audit documents. Protection requires RBAC, write authorization, storage retention, and separate operational controls.

### 48.4. Change Streams Are Not an Infinite Archival Audit Log

Resume tokens require sufficient oplog history; if a consumer stays offline past the oplog window, resumability breaks. Use a durable outbox or event store when business rules require it.

## 49. Scenario F — API While Primary Is Lost

### 49.1. Timeline

```text
T0 P healthy, S1/S2 healthy
T1 P unavailable
T2 election in progress: no primary
T3 S1 elected new P
T4 driver detects new topology
```

### 49.2. With `readPreference=primary`

Reads block during server selection or return errors while no primary exists, recovering after election completes.

### 49.3. With `primaryPreferred`

Reads may fall back to secondaries while primary is absent, accepting staleness. Avoid for decisions requiring the latest state.

### 49.4. With `w:majority` Writes

Without a primary or data-bearing majority, writes wait or fail. Post-election retry logic must handle uncertain outcomes.

### 49.5. Do Not Auto-"Fix" by Switching to `w:1`

Lowering write concern during an outage causes the system to acknowledge writes vulnerable to rollback. That alters the business durability SLA, not a harmless toggle.

## 50. Scenario G — 30-Second Secondary Lag

Suppose:

```text
P  latest order revision = 18
S1 latest order revision = 17 (lag 30s)
S2 latest order revision = 18
```

### 50.1. `readPreference=secondary`

The driver may pick `S1` or `S2` based on eligibility, tags, and latency. If `S1` is chosen, the read returns rev 17.

### 50.2. Adding `readConcern=majority`

Does not force `S1` to return rev 18 just because rev 18 is majority-committed on `P`/`S2`. If `S1` has not applied it yet, it cannot serve that state immediately.

### 50.3. Adding `maxStalenessSeconds`

The driver can exclude overly lagging secondaries based on staleness estimates and version rules. This is not an exact freshness guarantee.

### 50.4. Causal Session

If the client just wrote rev 18 and must read it within the same causal chain, use majority writes/reads with a causal session. The read will either wait for `S1` to catch up or select an eligible member.

### 50.5. Business Fallback

If mandatory freshness SLAs are tighter than staleness filtering allows, prefer `primary` or a materialized view/CDC pipeline with an explicit lag gate instead of setting `maxStalenessSeconds=1`.

## 51. Scenario H — BI Dashboard Using `nearest`

### 51.1. Requirement

Users across regions view aggregated charts. The dashboard tolerates delayed data.

### 51.2. Candidate Settings

- `readPreference=nearest` with intentional tags.
- `readConcern=majority` if only committed values should appear.
- Caching and indexed/materialized reports.
- Display `dataAsOf` or a lag indicator where helpful.

### 51.3. Do Not Use `nearest` to Hide Freshness Lag

A "per-minute sales" chart driving real-time decisions should expose staleness and refresh budgets explicitly. Low network RTT never proves data freshness.

### 51.4. Never Assume `nearest` Means Same Region

Driver selection relies on measured latency and tags; network routing can differ from physical geography. If data residency matters, enforce dedicated storage/placement policies.

## 52. Scenario I — Change Stream Events and Committed Writes

### 52.1. Goal

A consumer watches `orders` and sends an email once status changes to `PAID`.

### 52.2. Key Behavior

Change streams run on supported replica set/sharded topologies; stream events reflect changes satisfying majority-commit/oplog semantics. Not every `w:1` write acknowledged by the primary becomes an unlosable durable event.

### 52.3. Do Not Rely Solely on Read Concern

Consumers require:

- Durable resume tokens.
- Idempotent processing.
- Never checkpointing a token before executing an external side effect without atomicity.
- Sufficient oplog window or recovery plans if oplog history expires.
- An outbox if external email/event delivery guarantees are required.

### 52.4. When Write Ack Is Unknown

A client may hit a write timeout yet the event still appears later because the write eventually committed. Idempotent consumers and request identities are mandatory to avoid sending two emails.

## 53. Scenario J — Reading T0 State for Reconciliation

### 53.1. Goal

Reconcile the balance ledger against account snapshots at one exact point in time, avoiding reading the ledger after Transaction A alongside an account before Transaction A.

### 53.2. Why Is `majority` Alone Insufficient?

Two independent `majority` reads can execute against **two different majority-committed points in time**.

### 53.3. Choosing the Right Snapshot

A transaction with `readConcern:"snapshot"` captures a consistent snapshot across reads within supported bounds. For massive datasets, consider non-transaction snapshot reads or pagination/CDC architectures to avoid long transactions.

### 53.4. Watch Snapshot Timestamps

Clearly define whether "as-of" means cluster logical time, business cutoff time, or application wall-clock time. They are not always identical.

### 53.5. Never Scan 500 Million Documents Inside One Transaction

For huge reports, holding a transaction open stresses snapshot history. Design batch consistent snapshots, historical materialization, or dedicated analytical pipelines with verified trade-offs.

## 54. Scenario K — Search and Cache

### 54.1. MongoDB Read Concern Does Not Bind Caches

If a service reads from a Redis cache or Atlas Search index, MongoDB document consistency does not propagate automatically to the cache or search index. A `linearizable` MongoDB read won't even be called on a cache hit.

### 54.2. End-to-End Consistency Contract Needed

- Business-critical reads: bypass or validate cache, or enforce version guards.
- Secondary search: tolerate indexing lag alongside `dataAsOf`/version metadata.
- Checkout: validate authoritative current state before committing.

### 54.3. Never Promise Read-Your-Writes Based Only on `w:majority`

If the read path hits an un-invalidated cache or an un-refreshed search index, users still see stale data. Contracts must account for data sinks outside MongoDB.

## 55. Scenario L — Config / Feature Flags

### 55.1. Goal

An application reads feature flags enabling/disabling money transfers or emergency kill switches.

### 55.2. Classification

- Ordinary flags may tolerate propagation delay.
- Emergency kill switches may need strong reads and centralized policy.
- If a flag controls authorization, treat it as security-sensitive data.

### 55.3. Choices

Use primary reads and majority writes, or a linearizable read on a single-document state if real-time ordering is mandatory. Local caching and refresh intervals must honor the exact same contract.

### 55.4. Availability Trade-Off

During a partition, failing closed (temporarily rejecting the action) may be safer than serving a stale "enabled" state and incurring risk. This belongs to business and security policy.

## 56. Common Fallacy: "Stronger" Is Always Better

Trade-off pairs:

```text
Higher consistency:
  may require waiting, lower availability in partitions

Stronger write acknowledgment:
  may increase latency or fail when majority unavailable

Read offloading to secondary:
  may increase apparent data staleness

Long snapshots:
  may retain history and consume resources
```

### 56.1. Do Not Optimize on Paper

Benchmark against real topology, network, journal/storage engine, and workloads; majority latency and read preference behavior depend on many variables.

### 56.2. Contracts Can Vary by Endpoint

`POST /payments` differs from `GET /catalog`. Never force one global toggle across endpoints with different business rules.

### 56.3. Never Pick `local` Just to "Stop Timeouts"

If timeouts stem from primary failover or degraded majority health, lowering read concern rarely fixes server selection and risks returning rolled-back data.

### 56.4. Changing Write Concern Requires Change Review

Switching `w:majority` to `w:1` changes the durability guarantee. It requires owner/business sign-off—not a casual performance tweak.

## 57. Verifying Actual Runtime Configuration

### 57.1. In the Application

Log a secret-free config snapshot:

```text
service=orders-api
clusterAlias=mongo-orders-prod
driverVersion=...
readPreference=primary
readConcern=majority
writeConcern=majority
journal=true
writeConcernTimeoutMs=5000
```

### 57.2. In MongoDB

With appropriate administrative privileges, inspect replica set topology/status and cluster default concerns:

```javascript
rs.status();
rs.conf();
db.adminCommand({ getDefaultRWConcern: 1 });
```

Certain commands require matching deployment, version, and privileges. Never run `rs.reconfig`, `setDefaultRWConcern`, or modify votes merely to inspect state.

### 57.3. Never Rely on the URI Alone

Applications may override settings at collection or transaction scope. Server-side default concerns may also differ. To verify what an operation actually uses, inspect both client configuration paths and command instrumentation.

### 57.4. Actual Read Preference

Command monitoring combined with SDAM topology events reveals which host and role handled a read command; avoid logging full BSON payloads containing PII.

## 58. Metrics When Tuning Concerns and Preferences

| Metric | Why Needed |
|---|---|
| MongoDB command p50/p95/p99 latency | Measures real read/write latency |
| Server selection timeouts | Missing eligible server, primary election, wrong tags |
| Pool checkout wait | Connection pool saturation |
| Primary and secondary CPU/IO | Verifies offload goals |
| Replication lag per secondary | Read staleness and majority write latency |
| Majority commit point progress | Majority read/write health |
| Journal latency/I/O | `j:true` and durability overhead |
| Write concern errors/timeouts | Majority unsatisfied within budget |
| Retryable write / transaction retry counts | Network or election pressure |
| Change stream consumer lag | Oplog/history dependency and processing rate |
| Oplog window | Resumability and catch-up margin |
| Read routing role/host distribution | Confirms preference matches actual selection |
| Business stale-read incidents | Actual outcomes matter more than config labels |

### 58.1. Histograms

Measure `p99` latency at both application endpoints and MongoDB commands. A majority read concern may raise command latency during failover, while retries or caches alter user-facing latency.

### 58.2. Safe Labels

Attach service, command, read preference, read concern, write concern class, error family, and cluster alias. Avoid raw connection URIs, user IDs, document IDs, high-cardinality `tenantId` labels, or query payloads.

### 58.3. Never Equate 100% HTTP Success With Data Correctness

A service reading a secondary and returning HTTP 200 can still serve stale data. Measure domain-specific freshness and invariants, not just HTTP status codes.

## 59. Preflight Checklist Before Changing Read/Write Policy

Before rolling out a change, document:

1. **Business invariant**: latest reads? no rollback? snapshot? availability priority?
2. **Endpoint scope**: which APIs, jobs, or tenants are affected?
3. **Server topology**: votes, arbiters, secondaries, replication lag, regions.
4. **Current defaults**: explicit client/database/collection/transaction settings and server default RW concerns.
5. **Version support**: valid `readConcern` levels for the commands and storage engine.
6. **Timeouts**: server selection, `maxTimeMS`, socket, write concern timeouts, retry budgets.
7. **Latency baseline**: p95/p99 read/write per workload.
8. **Failure model**: primary election, loss of majority, single-secondary lag.
9. **Rollback plan**: understand policy impacts before reverting configs.
10. **Monitoring**: commands, journal, commit point, business stale reads.

### 59.1. Every Policy Needs an Owner

If the Platform team modifies cluster defaults while the Payments service expects `w:majority`, business guarantees silently break. Set explicit write concerns on critical paths, maintain a config registry/owner, and verify at runtime.

### 59.2. Run a Canary

Apply changes to an approved subset of services or tenants, comparing p99 latency, error rates, replication pressure, and business invariants before expanding.

### 59.3. Do Not Downgrade Silently

If enforcing a new SLA triggers timeouts, investigate root causes and make an explicit business decision; never silently fall back to `w:1` or `local` inside an error retry handler.

## 60. Runbook 1 — Write Returns Write Concern Timeout

### Symptoms

```text
insertOne/updateOne reached MongoDB
writeConcern: majority
error: write concern could not be satisfied within timeout
```

### What to Know Immediately

**The write may already have applied.** This is not proof that the write rolled back or never ran.

### Remediation Steps

1. Log `requestId`/business identity safely.
2. Inspect primary/majority status, replication lag, and write concern metrics.
3. Never resend a non-idempotent operation under a new ID.
4. Query state by business-controlled key using an appropriate read concern.
5. If status remains unclear, retry with the exact same identity/idempotent protocol or trigger reconciliation.
6. Investigate infrastructure: majority members, replication lag, journaling, network.
7. Record incident evidence and add failover/retry regression tests.

### What Not to Do

Never assume `wtimeout` made the server cancel the write. Never drop `w:"majority"` down to `w:1` just to silence errors without business approval.

## 61. Runbook 2 — Secondary Read Misses Newly Created Order

### Symptoms

```text
POST /orders -> 201
GET  /orders/{id} -> 404
readPreference: secondaryPreferred
```

### Possible Causes

- Secondary replication lag.
- Client/session lacks causal context.
- GET hit a stale cache.
- Query missing or wrong tenant filter.
- Order rolled back because write ack was weak and failover occurred.

### Remediation Steps

1. Confirm POST's write concern and exact outcome.
2. Check which server/role executed GET—did it hit a secondary?
3. Query the primary per policy to separate stale secondary reads from genuinely missing data.
4. Inspect session/causal requirements.
5. Inspect cache invalidation and search/materialized views.
6. Fix the endpoint contract: primary read or causal session whenever read-your-writes is required.

### What Not to Do

Do not declare "MongoDB lost data" just because a secondary returned 404; equally, do not dismiss it as "just lag" without ruling out write rollback, authorization, or cache issues.

## 62. Runbook 3 — `linearizable` Read Stalls During Partition

### Symptoms

A single-document read with `readConcern:linearizable` slows down and eventually times out, while `local` reads continue returning data.

### Explanation

Linearizable reads require strong real-time confirmation against primary/majority. When those conditions cannot be verified, the read must wait or fail rather than return an unverified value.

### Remediation Steps

1. Check cluster health, quorum, and primary election status.
2. Ensure bounded `maxTimeMS` and client timeouts.
3. Maintain fail-closed behavior for security- or coordination-critical paths.
4. Evaluate whether the endpoint truly requires `linearizable` or if `majority`/causal suffices.
5. If downgrading, execute an approved policy change—never automate silently.

### What Not to Do

Never disable read concern on a leader-lock authorization path merely to keep the endpoint returning HTTP 200.

## 63. Runbook 4 — Primary Failover After `w:1` Success

### Symptoms

The application received success from a `w:1` write, yet after an election the document is gone and rollback logs show the write was never majority-committed.

### Remediation Steps

1. Confirm write acknowledgment level and timeline.
2. Inspect replica set topology, rollback indicators, and new primary state.
3. Reconcile using durable business request IDs, outbox records, or sources of truth.
4. For critical data, upgrade write requirements via change management and ensure a true data-bearing majority.
5. Add chaos/failover integration tests asserting business outcomes.

### What Not to Do

Do not change `readConcern` to `majority` and claim write durability is fixed; read concern never alters past write acknowledgments.

## 64. Runbook 5 — Driver Cannot Find an Eligible Secondary

### Symptoms

```text
readPreference=secondary
server selection timeout
secondary nodes exist but none eligible
```

### Possible Causes

- Secondary lag exceeds `maxStalenessSeconds`.
- Tag sets do not match actual member tags.
- Secondaries are unreachable, recovering, or down.
- Replica set only has one member.
- Advertised hostnames/DNS are unreachable.

### Remediation Steps

1. Inspect `rs.status()` and `hello` outputs on members.
2. Check tags, max staleness, latency policies, and driver logs.
3. Verify application network connectivity to advertised hosts.
4. Reduce load or restore secondary health.
5. If primary fallback is acceptable to the business, consider `secondaryPreferred` via change review; otherwise keep explicit failures.

### What Not to Do

Never switch `secondary` to `nearest` while assuming reads still strictly hit secondaries.

## 65. Runbook 6 — Majority Writes Stall on PSA Topology

### Symptoms

A primary-secondary-arbiter replica set loses its secondary; `w:majority` writes time out even though the primary still accepts `w:1` writes.

### Explanation

An arbiter votes but stores no data; it cannot substitute for data replication to a data-bearing node to satisfy majority write concerns.

### Remediation Steps

1. Inspect voting vs data-bearing member topology.
2. Restore secondary health and connectivity.
3. Evaluate adding an appropriate data-bearing member.
4. Check the implicit default write concern on this topology.
5. Uphold business durability SLAs; any policy change requires formal approval.

### What Not to Do

Never treat an arbiter as a "second secondary," and never unconditionally downgrade `w:majority` just to keep writes flowing.

## 66. Runbook 7 — Report Returns Differing Totals Across Two Reads

### Symptoms

A report runs two aggregations:

```text
read A at T1
read B at T2
```

If writes occur between `T1` and `T2`, results may not reflect the same snapshot even though both reads used `readConcern:"majority"`.

### Remediation Steps

1. Determine whether the report requires a logical snapshot or eventually consistent metrics.
2. If a snapshot is needed, use a transaction or supported snapshot reads within duration bounds.
3. For long reports, consider materialized reports tied to a cut-off/as-of timestamp.
4. Ensure proper indexes and performance to keep transactions short.
5. Test with concurrent writers while the report runs.

### What Not to Do

Never simply set read preference to `primary` and claim both reads observed the same snapshot.

## 67. Runbook 8 — `nearest` Read Is Fast Yet Serves Stale Data

### Symptoms

A client using `nearest` sees low response times yet receives an old document version.

### Remediation Steps

1. Identify the actual host/role, replication lag, and latency-selection details.
2. Confirm the active read concern.
3. If the business requires latest/causal state, switch the read path to primary or causal sessions.
4. If eventual consistency is allowed, surface freshness/`dataAsOf` and set a lag SLO.
5. Check caches and search indexes, as staleness may originate outside MongoDB secondaries.

### What Not to Do

Never assume `nearest` means "the nearest primary" or "the freshest document."

## 68. Runbook 9 — Transaction Commit Returns Uncertain Outcome

### Symptoms

Transaction commit ends with an error labeled `UnknownTransactionCommitResult` or a network/socket exception after commit was sent.

### Explanation

The client does not know whether commit succeeded; you **must not** blindly rerun the entire business workflow and risk duplicating side effects.

### Remediation Steps

1. Distinguish transient transaction-body retries from unknown commit results.
2. Apply driver commit-retry patterns tailored to the error label within a retry budget.
3. Inspect the business transaction ID or ledger state when uncertain.
4. Never send emails or charge payments directly inside a retryable callback without an outbox/idempotency.
5. Inspect majority/journal health, election timelines, and timeout configs.

### What Not to Do

Never treat `UnknownTransactionCommitResult` as equivalent to `abortTransaction` or "definitely did not commit."

## 69. Runbook 10 — Default RW Concern Changed Unexpectedly

### Symptoms

After changing replica set membership or cluster configuration, latency or rollback exposure shifts even though application code did not change.

### Possible Causes

- Server implicit write concern shifted with topology.
- An admin modified `setDefaultRWConcern`.
- A newer service overrides client/database settings.
- A different URI/environment profile was deployed.
- Transactions carry separate options.

### Remediation Steps

1. Inspect the service's effective configuration path (without exposing secrets).
2. Inspect `getDefaultRWConcern` and `rs.conf()` with proper privileges.
3. Correlate timestamps of config or version changes.
4. Compare p95/p99 latency, write concern errors, and business outcomes.
5. Pin explicit options on critical paths as needed.
6. Enforce config change reviews and regression tests.

### What Not to Do

Never assert "MongoDB always defaults to `w:1`" or "always defaults to `majority`" across every topology and version.

## 70. Test Matrix for Concerns and Preferences

| Test | Topology | Options | What to Verify |
|---|---|---|---|
| Local read basic | Single-node RS | `local+primary` | Read succeeds |
| Majority write/read | Multi-node RS | `w:majority,rc:majority` | Write ack / stable read |
| Secondary stale | Three-node RS | `rc:majority,rp:secondary` | Can lag; never assume latest |
| PrimaryPreference | Multi-node RS | `rp:primary` | Server selection targets primary only |
| SecondaryPreferred fallback | Multi-node RS | `rp:secondaryPreferred` | Picks secondary or falls back per health |
| Secondary unavailable | Single-node RS | `rp:secondary` | Server selection times out per budget |
| Election | Three-node RS | `w:majority,rp:primary` | No-primary window, retries/recovery |
| `w:1` rollback exposure | Multi-node with controlled fault | `w:1` | Never promise write survives failover |
| `wtimeout` | Multi-node with controlled lag | `w:majority,wtimeout` | Outcome can be unknown |
| Linearizable | Multi-node RS | `rc:linearizable,rp:primary` | Real-time ordering / timeouts |
| Causal session | Multi-node RS | Majority read/write + session | Read-your-writes |
| Snapshot transaction | Supported topology | `rc:snapshot,commit w:majority` | Coherent view |
| PSA outage | P–S–A test setup | `w:majority` | Loss of S blocks majority ack |
| Sharded read | Sharded cluster | `majority/available` | Routing and orphan caveats |
| Tags/max staleness | Multi-node tagged RS | `rp:secondary,tags` | Eligible server filtering |

### 70.1. Why Is a Single-Node Replica Set Insufficient?

It can verify basic transaction and `readConcern:majority` syntax, yet lacks secondaries to reproduce replication lag, elections, or secondary selection. Never mark a failover test "passed" simply because a container restarted after stopping.

### 70.2. Use Disposable Test Infrastructure

Perform fault injection against disposable Testcontainers or multi-node test clusters; never stop a production primary to test theory.

### 70.3. Never Assert Fixed Election Durations

Poll state against deadlines and SLO windows. CI and local machines schedule differently—never use `Thread.sleep(2000)` as proof an election finished.

## 71. JUnit 5 + Testcontainers: Basic Configuration Testing

An integration test can run against a real MongoDB container rather than mocking the driver:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static com.mongodb.client.model.Filters.eq;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ConcernSmoke471IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void majorityWriteThenMajorityPrimaryRead() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {

            var collection = client
                .getDatabase("consistency_lab_471")
                .getCollection("orders")
                .withWriteConcern(WriteConcern.MAJORITY)
                .withReadConcern(ReadConcern.MAJORITY)
                .withReadPreference(ReadPreference.primary());

            collection.insertOne(new Document("_id", "T471")
                .append("status", "PAID"));

            Document result = collection
                .find(eq("_id", "T471"))
                .first();

            assertNotNull(result);
            assertEquals("PAID", result.getString("status"));
        }
    }
}
```

### 71.1. What Does This Prove?

The integration test exercises a real MongoDB instance and confirms both concerns execute on a supported topology.

### 71.2. What Does It **Not** Prove?

A single-node replica set satisfies majority with one member; this test **does not** prove replication to a second machine or durability when losing the primary and electing a secondary. Testing those requires multiple data-bearing members.

### 71.3. Testing Secondary Read Preference Requires a Different Topology

Adding `withReadPreference(ReadPreference.secondary())` to the single-node sample leaves zero eligible secondaries. Spin up a multi-node RS with reachable hostnames and verify the actual selected host.

### 71.4. Fault Injection

To test failover properly:

1. Start a three-node RS with majority.
2. Wait for one primary and two secondaries.
3. Perform a majority write.
4. Stop the current primary (do not assume node A).
5. Wait for election completion.
6. Read/write once the driver discovers the new primary.
7. Assert majority-acknowledged data remains intact and business identities did not double-apply.

### 71.5. Timing and Isolation

Never run primary failure tests against production. Avoid hardcoding host port 27017 since Testcontainers binds dynamic mapped ports. Keep test timeouts generous enough for CI yet bounded.

## 72. Operation Consistency vs End-to-End Workflow Consistency

An order creation endpoint typically performs:

```text
1. Authorize user
2. Validate stock and price
3. Insert order
4. Reserve inventory
5. Publish event
6. Read order back
7. Respond HTTP 201
```

### 72.1. Each Step Has a Different Consistency Source

| Step | Primary Mechanism |
|---|---|
| Authorize | Identity, roles, tenant policy, policy freshness |
| Validate stock | Domain invariants, conditional write/transaction |
| Insert order | Unique keys, write concern, idempotency |
| Reserve inventory | Atomic filter/transaction, concurrency control |
| Publish event | Outbox / event delivery semantics |
| Read back | Read concern, preference, causal/session/cache |
| HTTP response | Deadlines, unknown outcomes, retry contract |

### 72.2. There Is No "One Setting to Rule Them All"

`w:"majority"` does not replace transactions; `readConcern:"linearizable"` does not replace authorization or atomic conditional updates; `readPreference:"primary"` does not invalidate Redis caches.

### 72.3. End-to-End SLAs

Questions to codify into the contract:

- Does HTTP 201 guarantee the order is majority-acknowledged?
- If the client times out after POST, can it safely POST again with the same `requestId`?
- Must a GET immediately after POST hit the primary or carry a causal token?
- How much lag is permitted on external search or emails?
- When majority is unavailable, does the system return an error or accept reduced durability?

### 72.4. Avoid Vague Claims Like "Strong Consistency"

State instead: "Order writes are majority-acknowledged; GETs in the same interaction chain use primary + majority; asynchronous search has a 30-second SLA; payments enforce idempotency keys." That is a testable requirement.

## 73. Anti-Patterns and Replacements

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Treating read concern = read preference | Confuses data guarantees with server selection | Choose each independently |
| Treating `majority` = latest | Secondaries lag even on majority data | Primary/causal/linearizable per need |
| Treating `w:majority` = applied on all nodes | Third secondary can still lag | Monitor replication / causal reads |
| Treating `w:2` as always majority | With 5 voters, majority is 3 | Use `w:"majority"` |
| Treating `w:1` as rollback-proof | Unreplicated writes can roll back | Use majority for critical writes |
| Treating `j:true,w:1` = multi-node durability | Journal is not replica confirmation | Pick appropriate write concern |
| Treating `wtimeout` as write cancelled | Write may already be applied | Idempotent recovery |
| Retrying transfer with a new request ID | Double business effect | Stable idempotency key |
| `readPreference=secondary` on one-node RS | No eligible secondary exists | Multi-node RS or `primary` |
| `secondaryPreferred` to mandate offload | Falls back to primary | `secondary` if primary must be avoided |
| `primaryPreferred` for security decisions | Silent fallback to stale data | Strong path / fail closed |
| `nearest` = newest | Latency is not data version | Define freshness separately |
| `maxStalenessSeconds=1` for 1s SLA | Driver lower bounds, estimate only | Primary/causal/lag gate |
| Changing read concern to fix cache lag | Has no effect on cache | Invalidate or version cache |
| Changing preference to fix write rollbacks | Read routing does not change write ack | Set proper write concern |
| Picking `snapshot` alone to fix lost updates | Snapshot does not replace domain guards | CAS/transaction constraints |
| `linearizable` on all lists/reports | High cost, narrow scope | Target strong reads selectively |
| Two `majority` queries = same snapshot | Reads observe different times | Snapshot/transaction |
| Omitting `maxTimeMS` with `linearizable` | Can block indefinitely | Bounded deadline and fail-closed policy |
| Transaction reading secondaries | Role restrictions/conflicts | `ReadPreference.primary()` per API |
| Per-operation `w` inside a transaction | Misunderstands commit semantics | Configure `TransactionOptions` |
| Retrying whole txn body on unknown commit | Duplicate side effects | Proper commit retry + outbox |
| Enabling causal session with `w:1`/`rc:local` | Missing expected guarantees | Majority read and write |
| Sharing one session across threads | Unsafe per driver API | Sequential session operations |
| Treating HTTP cookie as MongoDB session | Carries no automatic causal time | Explicit causal protocol |
| Auto-lowering `w` during outages | Alters durability SLA silently | Approved fallback or fail |
| Counting PSA arbiter as data secondary | Insufficient majority write ack | Data-bearing topology |
| Assuming fixed implicit defaults | Varies by server/topology/overrides | Inspect and set critical options explicitly |
| Fixing slow missing-shard-key query via concern | Does not solve scatter-gather | Shard-aware query/index |
| Using `available` on sharded without orphan check | Possible duplicate/inconsistent reads | Choose appropriate concern |
| Treating `readConcern:majority` as "backup" | Does not protect accidental deletes | Backups/PITR/RBAC |
| Measuring only command p99, ignoring staleness | HTTP 200 can still be stale | Domain freshness metrics |
| Not tracking actual read server | Preference differs from actual role | SDAM/command monitoring |
| Logging full URIs | Leaks credentials | Redact secrets |
| Running failover tests in production | Outage risk | Disposable test clusters |
| Changing server defaults without service review | Silent policy drift | Config ownership and canary |

## 74. Configuration Worksheet per API

A simple design artifact before writing code:

| Endpoint/Job | Freshness Contract | Durability Contract | Read Concern | Write Concern | Read Preference | Session/Transaction | Fallback |
|---|---|---|---|---|---|---|---|
| GET catalog | Can be stale per SLA | Read-only | `local`/`majority` | — | `secondaryPreferred` | None unless required | Show cached timestamp |
| GET newly created order | Read-your-writes | Order majority-committed | `majority` | — | `primary`/causal | Yes if cross-secondary causal | Bounded retry / primary read |
| POST order | Response confirms durable ack | Majority | — | `majority` | — | Idempotency + optional txn | Reconcile unknown outcome |
| POST transfer | Atomic business transaction | Majority commit | `snapshot` | `majority` | `primary` | Transaction + request ID | Retry protocol |
| GET leader lock | Real-time single doc | Lock majority-acknowledged | `linearizable` | — | `primary` | CAS/fencing for write | Fail closed |
| Generate finance report | Consistent as-of view | Source committed | `snapshot` | — | Per txn/API | Snapshot mechanism | Delay report |
| Dashboard telemetry | Eventual | N/A | `local` | — | `nearest`/`secondary` | None | Show as-of timestamp |
| Analytics export | Snapshot/timestamp if needed | N/A | `snapshot`/`majority` | — | Per scope | Bounded jobs | Defer |

**Fill the worksheet per system:** do not leave "A/B" placeholders in final configs without choosing one option and stating exact conditions.

### 74.1. Write One Concrete "Acceptance Criterion"

Example:

> When the order-creation API returns 201, data has been majority-acknowledged and a GET in the same interaction flow observes the order via the designated read path. If the response is lost, a client retry with the same `requestId` does not create a second order.

This is a testable criterion; "use strong consistency" is not.

### 74.2. Update When Topology Changes

`w:majority` and read preference columns require re-evaluation if the replica set changes member count, adds an arbiter, moves regions, or shards. Never treat a one-time choice as permanent.

## 75. Practice Exercises

### Exercise 1 — Classify Concern vs Preference

Distinguish `readConcern`, `writeConcern`, and `readPreference` via three distinct questions. Give an example where `readPreference` is right yet `readConcern` is inappropriate.

### Exercise 2 — Majority Does Not Mean Latest

Replica set `P`, `S1`, `S2`. `P` and `S1` have applied `revision=9`; `S2` has applied `revision=8`. Which revision can `readConcern=majority` on `S2` return? Explain.

### Exercise 3 — Read Concern `local`

A client reads `"PAID"` from the primary with `local`, then the primary fails over and that write rolls back. Why did the client see `"PAID"`?

### Exercise 4 — `available` on Sharded Clusters

A chunk moves from shard A to shard B, leaving temporary orphaned documents. What caveat affects `available` reads? Should it be used for financial aggregates?

### Exercise 5 — `linearizable`

A lock record was majority-acknowledged before a GET begins. Select read concern and preference for real-time ordering; explain why `maxTimeMS` is required.

### Exercise 6 — `snapshot`

A report reads `accounts` and `ledger` in two separate queries amid concurrent writes. Why is `majority` on both insufficient to guarantee the same snapshot?

### Exercise 7 — Single-Node vs Multi-Node

A single-node replica set satisfies `w:majority` with one member. What durability and replication behaviors remain untested if integration tests only run one container?

### Exercise 8 — `w:0`

A service writes audit events with `w:0`. What errors or outcomes can go unobserved? Propose a better approach if audit integrity is required.

### Exercise 9 — `w:1` Failover

A `w:1` write returns success, then the primary dies before replicating. Outline the rollback timeline and business recovery strategy.

### Exercise 10 — `w:majority`

A five-voter replica set has three data-bearing members and two arbiters. Why must majority/data acknowledgment distinguish arbiters from secondaries?

### Exercise 11 — `w:n`

A replica set has five voting data-bearing members. Does `w:2` equal `w:"majority"`? How many does majority require?

### Exercise 12 — Journal

Compare `{w:1,j:true}` and `{w:"majority"}` under two failures: primary process crash and primary election. State the limits of each case.

### Exercise 13 — Timeout

`wtimeout=5000` after an insert; the application receives an error. Can you assert the document does not exist? What query/identity protocol enables safe retries?

### Exercise 14 — Error Classification

Distinguish MongoDB server selection timeout, socket timeout, and write concern timeout regarding whether the command was sent or executed.

### Exercise 15 — Read Preference `primary`

During an election window with no primary, what happens with `readPreference=primary`? Why shouldn't a payment API auto-switch to a secondary?

### Exercise 16 — `primaryPreferred`

Describe a scenario where `primaryPreferred` reads `revision=20` from `P`, then `revision=19` from a secondary during failover. How is causal monotonicity violated?

### Exercise 17 — `secondary`

A test uses `ReadPreference.secondary()` against a single-node replica set. What happens? Adjust the test topology to genuinely test secondary reads.

### Exercise 18 — `secondaryPreferred`

A system wants to *strictly never* run heavy reports on the primary, yet configures `secondaryPreferred`. Where is the flaw?

### Exercise 19 — `nearest`

Primary RTT = 18 ms; secondary RTT = 5 ms with 40 seconds of lag. What can `nearest` return? When is this configuration suitable?

### Exercise 20 — Max Staleness

Why does setting `maxStalenessSeconds=2` fail to provide a 2-second freshness SLA? Explain server-selection estimates, minimum/version constraints, and alternative read paths.

### Exercise 21 — Tag Sets

A replica set spans APAC and EU. Design preferences/tags for APAC reporting, noting fallback behavior and limits of tags for data residency.

### Exercise 22 — Causal Session

Write Java pseudocode using `ClientSessionOptions.causallyConsistent(true)` with majority writes/reads to read your own write.

### Exercise 23 — HTTP vs MongoDB Session

A user authenticates via JWT; Request A writes through Pod 1, and Request B reads through Pod 2. Why does a JWT not carry MongoDB causal metadata automatically?

### Exercise 24 — Transaction

Write `TransactionOptions` with snapshot read concern, majority commit, and primary read preference. Explain why per-operation `w` is not set inside a transaction.

### Exercise 25 — `UnknownTransactionCommitResult`

Commit returns an unknown result. Distinguish retrying commit vs retrying the transaction body; design idempotency/outbox for a money transfer.

### Exercise 26 — Sharded Majority

A report reads across multiple shards with `readConcern=majority`. Why does this not guarantee a single point-in-time snapshot?

### Exercise 27 — Sharding and `available`

Evaluate `readConcern:available` during chunk migration; explain the risk of orphaned documents.

### Exercise 28 — URI

Write a MongoDB connection string with `readPreference=primary`, `readConcernLevel=majority`, `w=majority`, `journal=true`, and `wtimeoutMS=5000`.

### Exercise 29 — Client vs Collection Overrides

`MongoClient` specifies majority/primary, while a reporting collection sets `secondaryPreferred`. How do you verify which server an operation actually read from?

### Exercise 30 — Java `linearizable`

Write a `find` by `_id` using `ReadConcern.LINEARIZABLE`, `ReadPreference.primary()`, and bounded `maxTime`.

### Exercise 31 — mongosh Command

Write a `db.runCommand` insert with `majority`/`j:true`/`wtimeout`; explain what the result or error may contain.

### Exercise 32 — Read-Your-Writes

POST order uses `w:majority`; GET reads `majority` on a secondary without a session. Is the order guaranteed to be visible? Propose two solutions.

### Exercise 33 — Cache/Search

An endpoint checks Redis cache, then Atlas Search, then MongoDB. Why does setting `readConcern:majority` in MongoDB alone not make the endpoint consistent?

### Exercise 34 — Defaults

A service omits explicit write concern and the cluster moves to a topology with an arbiter. List steps to inspect implicit/explicit defaults and associated risks.

### Exercise 35 — PSA

A P–S–A replica set loses `S`; `P` and `A` stay connected. Why can majority write concerns stall? Does the arbiter store data?

### Exercise 36 — Monitoring

Design a dashboard tracking command latency p99, write concern errors, replication lag, secondary read routing, server selection timeouts, and domain stale-read rates.

### Exercise 37 — Chaos Test

Design a multi-node replica set test: majority write, stop the actual primary, elect a new primary, verify committed data; identify unsafe assumptions.

### Exercise 38 — Incident

After a deployment, `w:majority` timeouts spike and API p99 degrades. Write a runbook that does **not** automatically downgrade `w`.

### Exercise 39 — Business SLA Matrix

Choose concerns, preferences, and sessions for four endpoints: `GET /catalog`, `POST /orders`, `POST /transfer`, `GET /leader-lock`. State exact trade-offs.

### Exercise 40 — Capstone

A B2B SaaS MongoDB deployment features:

1. Three-data-bearing-member replica set across two regions.
2. 10,000 catalog writes/sec, 1,000 order writes/sec.
3. Payments must never double-charge.
4. Heavy reports and lag-tolerant dashboards.
5. Several failovers per year.
6. Java Sync Driver and Spring Data clients.
7. Atlas Search with indexing delay.
8. Requirement to track uncertain write incidents.

Design:

- Per-endpoint read/write consistency contracts.
- Concerns, preferences, and timeout budgets.
- Causal sessions/transactions where required.
- Unique business keys, idempotency, and outbox.
- Separate reporting handles and safety guardrails.
- Replica set topology and majority/journal policies.
- Metrics, alerts, and test matrix.
- Canary rollout, failure recovery, and runbooks.

## 76. Quick Checklist Before Choosing Configuration

When reviewing a new requirement, follow this sequence:

```text
1) Operation:
   read / write / transaction / stream?

2) Business meaning:
   stale allowed?
   rollback-ack allowed?
   read-your-writes required?
   real-time single-document?
   snapshot across documents?

3) Deployment:
   standalone / replica set / sharded?
   voting/data-bearing members?
   arbiter?
   secondary lag?
   region/network?

4) Correctness:
   read concern
   write concern
   read preference
   sessions/transactions/atomic filters

5) Reliability:
   timeout and retry budget
   idempotency key
   unknown outcomes
   backup and disaster recovery

6) Verification:
   functional tests
   failover tests
   actual server selection metrics
   business freshness checks
```

### 76.1. No Requirement for Latest Data?

Do not default to `linearizable`. Use `majority` or `local` with an appropriate read preference and document how stale data may be.

### 76.2. Must Avoid Rollbacks After Write Success?

Prioritize `w:"majority"` on an adequate topology, paired with durability/journal policies and idempotency. Do not merely raise read concern.

### 76.3. Must Observe Your Own Just-Completed Write?

Use primary reads or causal sessions with majority reads/writes where supported; verify caches and search indexes do not serve stale copies.

### 76.4. Must Read Multiple Documents Consistently?

Consider snapshot transactions or supported snapshot reads, avoiding long-running transactions over large datasets.

### 76.5. Must Survive Failovers?

Design retryability, primary discovery, and handling for uncertain outcomes; write concern alone cannot keep endpoints available without a primary or quorum.

## 77. Safe Operations Checklist

### Pre-Rollout

- [ ] Business owner has defined exact consistency and durability SLAs.
- [ ] Read concern, write concern, and read preference are distinct—no vague "strong" label.
- [ ] Replica set topology, votes, arbiters, and secondaries are documented.
- [ ] Implicit/server default RW concerns and explicit overrides are verified.
- [ ] Read concern is supported by target operations and server version.
- [ ] Critical writes specify explicit write concerns.
- [ ] Explicit timeouts exist for server selection, `linearizable`, writes, and transactions.
- [ ] Unique business keys, retries, and idempotency are implemented.
- [ ] Causal session/transaction policies exist where required.
- [ ] Dashboards track lag, commit point, command duration, and write concern errors.
- [ ] Canary and rollback plans are prepared.

### During Operations

- [ ] Never downgrade `w:majority` to `w:1` unconditionally during an outage.
- [ ] Never assume `majority` on a secondary means latest.
- [ ] Never treat `wtimeout` as "write did not happen."
- [ ] Never run long transactions for unbounded snapshots.
- [ ] Never print raw URIs or credentials in logs.
- [ ] Never disable business invariants as a performance fix.
- [ ] Monitor actual read server/role, not just configured `readPreference`.
- [ ] Monitor replication lag and staleness alongside p99 latency.
- [ ] Maintain reconciliation procedures for unknown outcomes.
- [ ] Run failover tests only on disposable environments.

## 78. Summary

**Read concern, write concern, and read preference are three independent dimensions that must be chosen together**:

- **Read concern** answers "what state of data is observed and under what guarantees?": `local` permits non-majority-committed state, `majority` restricts to majority-committed data, `linearizable` adds real-time ordering for single-document reads, `snapshot` preserves a consistent point-in-time view, and `available` carries special caveats in sharded deployments.
- **Write concern** answers "what acknowledgment level must the server reach before returning?": `w:1` risks rollback on failover, `w:majority` balances higher durability against latency/availability trade-offs, `j` governs journaling, and `wtimeout` never cancels an applied write.
- **Read preference** answers "where does the driver route reads?": `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, and `nearest` control server selection—not majority commits, causal semantics, or absolute freshness.

**Key takeaways:** `majority` does not mean "latest"; `nearest` does not mean "freshest secondary"; `secondaryPreferred` does not guarantee avoiding the primary; majority-acknowledged writes do not guarantee every secondary has applied them; snapshots do not create real-time freshness; and linearizable reads do not replace atomic conditional updates.

For every business flow, write **testable contracts** covering freshness, durability, atomicity, and availability, then align concerns/preferences, sessions/transactions, timeouts/retries, idempotency, and topology accordingly. Handle incidents with respect for outcome uncertainty—never by silently weakening guarantees or assuming an operation never executed.

## 79. References

- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): overview of levels and semantics.
- [MongoDB Manual — Read Concern "local"](https://www.mongodb.com/docs/manual/reference/read-concern-local/): local read behavior.
- [MongoDB Manual — Read Concern "available"](https://www.mongodb.com/docs/manual/reference/read-concern-available/): available reads and sharding caveats.
- [MongoDB Manual — Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/): majority-committed reads.
- [MongoDB Manual — Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/): linearizable single-document read semantics.
- [MongoDB Manual — Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/): transactions and snapshot reads.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): `w`, `j`, `wtimeout`, defaults.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary/nearest.
- [MongoDB Manual — Read Preference Tags](https://www.mongodb.com/docs/manual/core/read-preference-tags/): tags in server selection.
- [MongoDB Manual — Max Staleness](https://www.mongodb.com/docs/manual/core/read-preference-staleness/): staleness constraints.
- [MongoDB Manual — Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/): sessions and ordering guarantees.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction concern semantics.
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): primary elections and votes.
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/): arbiter restrictions.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): acknowledged retry semantics.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): `mongos` and consistency.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): oplog and resume tokens.
- [MongoDB Java Sync Driver — Read Concern](https://www.mongodb.com/docs/drivers/java/sync/current/read/read-concern/): driver configuration.
- [MongoDB Java Sync Driver — Write Concern](https://www.mongodb.com/docs/drivers/java/sync/current/write/write-concern/): driver write options.
- [MongoDB Java Sync Driver — Read Preference](https://www.mongodb.com/docs/drivers/java/sync/current/read/read-preference/): driver server selection.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): transaction options and retry examples.
- [Testcontainers Java — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/): integration test topology.
