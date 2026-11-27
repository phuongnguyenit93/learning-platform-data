# Consistency, latency, and availability trade-offs during network partitions

A MongoDB system can run smoothly for months and then suddenly encounter scenarios where: **the primary is still running on one machine**, yet the application gets write errors; a **secondary still responds to queries**, yet data a user just updated has not appeared; or an `insertOne()` command reports a timeout even though the document was actually written on the primary.

These situations do not necessarily mean MongoDB "lost data" or "has a consistency bug." They reflect **deliberate trade-offs** in distributed systems, especially when nodes lose communication or replication lags.

This lesson in the **Read and Write Consistency** chapter focuses on three related yet distinct goals:

1. **Consistency:** at what guarantee level is a read allowed to see data, in what order are operations observed, and does the system protect acknowledged writes?
2. **Latency:** how long must the application wait for a read or write operation to complete at the chosen guarantee level?
3. **Availability:** when nodes fail or the network partitions, which operations can the application still perform, in which regions, and with what guarantees?

MongoDB lets you design trade-offs through **replica set quorum, write concern, read concern, read preference, sessions, transactions, and client error handling**. No single configuration allows every isolated partition to always succeed writes, guarantees every read always sees the latest state, and gives every operation minimal latency across all network conditions.

> **Principle:** During a network partition, a side lacking a majority of votes cannot maintain valid primary write authority. That may reduce availability for certain requests, but protects the single-valid-primary model and committed write ordering. Allowing secondary reads can improve read availability, subject to read concern and data freshness.

## 1. Context: a three-member replica set

Consider replica set `rs0`:

```text
                 Application
                     |
               MongoDB driver
                     |
          ┌──────────┴───────────┐
          |                      |
       node-a                  node-b               node-c
       PRIMARY                 SECONDARY            SECONDARY
       vote=1                  vote=1               vote=1
       data=yes                data=yes             data=yes
          |                       ^                    ^
          +------ replication ----+--------------------+
```

Under normal conditions:

- Clients write to the **primary**.
- Secondaries receive and apply writes via replication.
- Voting members coordinate to elect a primary.
- Each node may apply data at a different speed.
- Clients use **read preference** to pick where to read and **read concern** to pick read data guarantees.
- Clients use **write concern** to choose the required acknowledgment before treating a write as complete per their contract.

If `node-a` loses connectivity to `node-b` and `node-c`, the replica set no longer has a fully connected network. Two groups may form:

```text
Partition A                       Partition B
───────────                       ───────────
node-a                            node-b   node-c
  1 vote                            1       1
                                     └── 2 votes ──┘
```

The replica set has three voting members, so quorum is **two votes**. Partition B has quorum and can elect a new primary if an eligible candidate exists. Partition A has only one vote and cannot keep valid primary status once it detects loss of majority.

This does not mean every read request in Partition A fails immediately. Some reads from reachable nodes can still occur depending on role, node state, read preference, and read concern. **Read availability and write availability are not the same thing.**

## 2. Clearly defining each goal

### 2.1. Consistency has more than one level

In applications, the word "consistency" can refer to multiple requirements:

- **Read-your-writes:** after a user changes their address, their own next read must see the new address.
- **Monotonic reads:** the same session must not see an older data version after already seeing a newer one.
- **Causal consistency:** causally related operations are observed in proper order within the same session.
- **Majority-committed visibility:** reads only see data meeting MongoDB's majority commit guarantee.
- **Linearizability:** an operation appears to take effect at a single point between its start and completion, respecting the real-time order of completed operations.
- **Snapshot consistency:** multiple reads observe one logical data snapshot at a single milestone, rather than each seeing a different state.

These requirements **are not identical**. An application might need causal consistency for a profile page, linearizable reads for a critical state lock, and consistent snapshots for a multi-collection financial report.

### 2.2. Latency has multiple components

Command completion time is more than index speed:

```text
Application-side latency
  = server selection / connect time
  + network RTT to node
  + resource wait and query execution
  + waiting for replication / write concern (if any)
  + waiting for read concern conditions (if any)
  + response transmission and client processing
```

When a replica set spans multiple regions, a write requiring multiple replica acknowledgments typically takes longer than one waiting only on the primary, especially when required replicas are distant or lagging. Actual differences must be **measured on real topology and load**.

### 2.3. Availability for which operation?

A node may:

- Still answer TCP;
- Still respond to `hello`;
- Still hold readable data;
- Yet not be primary;
- Lack election quorum;
- Or fail to satisfy the desired write concern.

Thus, **"mongod is running" does not mean "the application can still safely write orders."**

When designing SLAs, define separately:

| Capability | Question to answer |
|---|---|
| Read availability | Which nodes can be read when the primary is lost? |
| Fresh-read availability | Can the latest state be read at the required level? |
| `w: 1` write availability | Is there a valid primary capable of accepting writes? |
| Majority-write availability | Are enough data-bearing acknowledgments available to complete writes? |
| Transaction availability | Can transactions commit with the required guarantees? |
| Business availability | Does the endpoint return results **conforming to business contract** or merely HTTP 200? |

## 3. CAP theorem: understanding C, A, and P accurately

CAP is often summarized as: *during a network partition, a system cannot simultaneously provide full consistency and availability as defined by the theorem*.

The three letters:

- **C — Consistency:** in CAP, a strong consistency form typically expressed as **linearizability**, not merely "valid schema" or "error-free data."
- **A — Availability:** every request to a non-failing node eventually receives a **non-error response**, rather than always retrying, timing out, or rejecting.
- **P — Partition tolerance:** the system continues operating in a defined manner when network failures prevent normal inter-node communication.

When a true partition exists, a system cannot simultaneously:

1. Allow **every partitioned side to accept and confirm all operations**;
2. Guarantee those operations obey **one strong real-time consistent order**;

if the sides cannot exchange required coordination.

### 3.1. Why can MongoDB reject writes on the minority side?

Suppose:

```text
         NETWORK PARTITION
      ┌─────────────────────┐
      │                     │
  node-a                 node-b + node-c
  1 vote                   2 votes
      │                     │
  lacks quorum           can elect primary
```

If both sides independently let primaries accept writes, the same document could evolve along two conflicting histories. To maintain a single-valid-primary model and uphold write commitments, MongoDB requires election quorum.

Consequence: the one-vote side **does not retain primary authority**. Clients on that side cannot write. This is a **write availability trade-off** protecting replica set consistency guarantees.

### 3.2. Should MongoDB be labeled CP or AP?

Do not slap a label like "MongoDB is always CP" or "MongoDB is always AP" and ignore configuration. Application behavior depends on:

- Replica set topology and quorum;
- Read preference;
- Read concern;
- Write concern;
- Primary/secondary state;
- Retry rules;
- Whether the application allows returning stale data.

A MongoDB replica set **does not allow two disconnected sides to both keep valid primaries** under quorum rules. Yet applications can read from secondaries with weaker guarantees, tolerate stale data, or pause writes when majority is lost. Different endpoints can behave differently.

**CAP is not a one-time two-checkbox menu.** It defines boundaries during partitions; real designs must specify **which requests continue and with what semantics**.

### 3.3. CAP Consistency differs from ACID's C

ACID describes transaction properties, where *Consistency* typically refers to transactions preserving business validity rules/constraints. CAP consistency focuses on observing a strong operation order in a distributed system.

A collection with schema validation and valid business transactions **does not automatically make all secondary reads linearizable**. Conversely, having a linearizable read does not replace business validation.

## 4. PACELC: latency remains a trade-off even without partitions

CAP emphasizes network partitions. However, distributed systems must trade off latency versus consistency guarantees **even when nodes communicate normally**.

One framing is PACELC:

```text
If there is a Partition (P):
    trade off Availability (A) versus Consistency (C)

Else (E) when the system operates normally:
    trade off Latency (L) versus Consistency (C)
```

This is a **mental framework**, not a single rigid label applied to all MongoDB operations.

For example:

- Writing with `w: 1` can return ACK once the primary accepts it per write concern rules, without waiting for secondaries to acknowledge.
- Writing with `w: "majority"` must wait for sufficient acknowledgments per majority write concern rules, potentially raising latency.
- Reading from a geographically close secondary lowers RTT to the read node while returning data **trailing behind the primary**.
- Reading with `readConcern: "linearizable"` requires coordination to verify recency, adding latency or failing if quorum conditions are unmet.
- Multi-document snapshot reads provide a consistent reporting state, but require managing snapshot age, resources, and transaction limits.

Therefore, a better question than "Does MongoDB favor consistency or latency?" is:

> For this specific operation, what guarantee do we require, which nodes must we wait for, and what happens when that condition cannot be met?

## 5. Election quorum and data replica counts

MongoDB replica sets use votes from voting members to establish a valid primary.

With `V` voting members:

\[
\text{Election majority} = \left\lfloor \frac{V}{2} \right\rfloor + 1
\]

Examples:

| Voting members | Votes needed for election majority | Votes that can be lost while retaining quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

The table covers **vote counts only**; it does not guarantee a valid primary candidate exists or enough data-bearing replicas exist to satisfy writes.

### 5.1. Three data-bearing nodes (PSS)

```text
P: primary   vote=1   data=yes
S: secondary vote=1   data=yes
S: secondary vote=1   data=yes

V=3; Q=2
```

If one secondary is lost, the primary and remaining secondary remain:

- Two voting ballots remain;
- Two data copies remain;
- `w: "majority"` can generally still complete while both remaining members are healthy and replication keeps up.

If the primary fails, the two remaining secondaries can elect a new primary if election criteria are met. Role transition creates a brief window where **writes are unavailable**.

### 5.2. Two data-bearing nodes (PS)

```text
P: vote=1, data=yes
S: vote=1, data=yes

V=2; Q=2
```

Losing one node leaves the remaining node without quorum. Two data copies do not provide automatic failover without quorum. Adding a non-voting secondary also does not solve missing votes.

### 5.3. Primary–Secondary–Arbiter (PSA)

```text
P: vote=1, data=yes
S: vote=1, data=yes
A: vote=1, data=no

V=3; Q=2
```

If S fails, P and A still hold **two votes**, so P can stay a valid primary. However, only **one data copy** remains.

Critical points:

- **Arbiters vote**, and do not store documents/oplogs like secondaries.
- Arbiters **never confirm that a write replicated to a data copy**.
- A PSA set can retain **election quorum** while **unable to satisfy writes requiring `w: "majority"`** when the data-bearing secondary is unavailable.

This is why counting three members is insufficient to evaluate durability. Count **data-bearing voting members** and check topology majority write concern rules.

### 5.4. Same three votes, different majority write capability

| Single member failure | PSS (three data-bearing) | PSA (two data-bearing + arbiter) |
|---|---|---|
| Secondary lost | Two data-bearing remain; majority writes possible | Only primary and arbiter remain; majority writes cannot be adequately acknowledged |
| Primary lost | Remaining two data-bearing can elect new primary | Secondary + arbiter can elect new primary, but only one data copy remains |
| Arbiter lost | Not applicable | P + S retain quorum and two data copies |

**Having a primary** and **being able to commit majority** are two separate states requiring independent monitoring.

## 6. Write concern: ACK at which level?

Write concern specifies the acknowledgment level an application requests for a write operation.

### 6.1. `w: 0`, `w: 1`, `w: "majority"`

| Write concern | Practical meaning | Trade-offs |
|---|---|---|
| `w: 0` | Does not wait for standard write acknowledgment | Minimal outcome visibility; hard to handle errors/durability |
| `w: 1` | Waits for primary acknowledgment at configured level | Potentially faster, yet unreplicated writes may roll back on failover |
| `w: "majority"` | Waits for enough data-bearing acknowledgments per majority write concern | Increases durability against failures; may slow down or fail when replication/quorum degrades |
| `w: <number>` | Waits for specified number of members | Must understand data-bearing count and topology; exceeding capacity times out |

Do not use `w: 0` for operations like order creation or payments just to shave a few milliseconds; the application needs to know success/failure and handle retries semantically.

### 6.2. `w: 1` write example

```javascript
db.orders.insertOne(
  {
    _id: "ORDER-101",
    status: "NEW",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: 1
    }
  }
);
```

Upon receiving ACK, the client knows the primary accepted the operation under that write concern. However, ACK **does not mean** secondaries have received the record.

If the primary fails before a `w: 1` write replicates to the required set of members, that write may roll back in certain failover scenarios. That risk must be evaluated against your **RPO** (Recovery Point Objective).

### 6.3. `w: "majority"` write example

```javascript
db.orders.insertOne(
  {
    _id: "ORDER-102",
    status: "NEW",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

`wtimeout` is in milliseconds and limits waiting time to **satisfy the write concern** per operation rules; it does not mean every phase from client to server is strictly capped at 5 seconds.

If a required secondary lags or loses connectivity, the write may:

- Already be applied on the primary;
- Not yet be acknowledged by enough members;
- Return a write concern timeout error.

**Never infer from `wtimeout` that the document definitely does not exist.** The operation may have been applied without satisfying acknowledgment requirements. Applications need stable request identifiers and retry/reconciliation strategies to avoid duplicate transactions.

### 6.4. Journaling does not replace replication

A configuration:

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
}
```

`j: true` involves waiting for the journal per applicable write concern/replica set rules. It creates no extra data replicas, and a majority acknowledgment does not mean the application has an independent backup.

When evaluating durability, examine:

- Number of data-bearing members;
- Write acknowledgment level;
- Journaling/storage engine;
- Rollback exposure;
- Fault domains;
- Backups and disaster recovery.

### 6.5. Never guess the default write concern

Drivers/clusters have default write concerns depending on configuration and server version. In topologies with arbiters, implicit defaults may differ from expectations.

Inspect defaults in eligible deployments:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

For critical data, explicitly specify write concern in architecture/drivers or cluster-wide policy, and verify the **actual effective value**. Never state "MongoDB always writes with majority by default" across every topology.

## 7. Read concern: read at which consistency level?

**Read concern** describes guarantees on data a read can observe. It differs from read preference—which chooses the target node.

| Read concern | Characteristics | Important notes |
|---|---|---|
| `"local"` | Can read local data present on the node | Non-majority-committed data may roll back |
| `"available"` | Suitable for certain availability-first scenarios, especially sharded reads | Specific limits; in sharded clusters may see orphaned documents |
| `"majority"` | Only reads majority-committed data per supported mechanism | **Not** automatically latest on every secondary or linearizable |
| `"linearizable"` | Reads with linearizable guarantees within supported scope | Requires primary; carries cost and failure risk when quorum degrades |
| `"snapshot"` | Reads from a consistent snapshot within supported scope | Does not mean snapshot is latest; has time/resource limits |

### 7.1. `readConcern: "local"`

A secondary may have applied a new record that has not yet reached majority commit. A `local` read can see this record. If a rollback occurs later, the record may vanish.

Therefore, `local` reads are **insufficient** when the application requires "once data is observed, it belongs to majority-committed history." For feeds or analytics tolerating mutable results, `local` is sometimes sensible; for payments, stricter guarantees are required.

### 7.2. `readConcern: "majority"`

Majority reads rely on majority-committed data guarantees, avoiding reads of insufficiently committed writes that could roll back under normal replication mechanics.

However, notice a crucial distinction:

```text
T1: P accepts and majority-commits version=10.
T2: Secondary S1 applies version=10.
T3: Secondary S2 has applied only up to version=9.
T4: Client reads S2 with readConcern="majority".
```

If S2 holds a valid majority-committed view at version 9, it can return a **version older** than the primary's latest value. `"majority"` does not force a lagging secondary to immediately serve the real-time latest state at request time.

Conclusion:

> **Majority reads protect the durability property of read data, not that the data is the latest across the cluster.**

### 7.3. `readConcern: "linearizable"`

For critical single-document problems, MongoDB supports `"linearizable"` read concern within documented scope and conditions. It targets the **primary** paired with sufficiently strong writes to achieve linearizable single-document semantics.

Example of a state flag:

```javascript
{
  _id: "payment-gate",
  enabled: false
}
```

Once a majority-acknowledged update completes, a valid linearizable read starting **after** that command is designed to observe state consistent with real-time order.

This does not mean every `find()` on a secondary becomes linearizable. Linearizable reads require:

- Reading from the primary;
- Scope primarily limited to **single-document reads**;
- Ability to verify majority-related conditions;
- Potential slowness or long waits during quorum/partition anomalies;
- Reasonable timeouts such as `maxTimeMS`.

An explicit read command example:

```javascript
db.runCommand({
  find: "systemFlags",
  filter: { _id: "payment-gate" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 3000
});
```

This example requires running on a primary/supported topology. Do not use linearizable reads for large analytical queries simply because the name sounds "safer"; it is built for specific strong-consistency single-document cases.

### 7.4. `readConcern: "snapshot"`

Snapshot reads serve scenarios where multiple documents or multiple reads must see **one consistent logical state** at a single point in time.

For example, a report needing order counts and revenue totals over the exact same dataset, rather than counting at T1 and summing at T2 after thousands of orders changed state.

Snapshot reads can be used inside transactions or via supported non-transactional snapshot reads in compatible versions/topologies. Choosing between them requires checking runtime duration, transaction limits, snapshot age, and history retention.

**A snapshot consistent at one milestone is not necessarily the latest state when the client receives the response.** Never substitute `linearizable` for `snapshot`, nor `snapshot` for `linearizable` in all cases.

## 8. Read preference: which node to read from?

Read preference determines the **preferred target node**:

| Read preference | General meaning |
|---|---|
| `primary` | Read only from primary |
| `primaryPreferred` | Prefer primary, may select secondary when conditions allow |
| `secondary` | Select eligible secondaries only |
| `secondaryPreferred` | Prefer secondary, may fall back per server selection rules |
| `nearest` | Select node with eligible network latency; does not mean latest data |

Read preference does not turn a secondary into an instantaneously synchronous replica.

Example:

```javascript
const orders = db.getCollection("orders");

orders.find(
  { customerId: "C-101" }
)
.readPref("secondaryPreferred");
```

This is `mongosh`-style syntax; read preference APIs in Java/Spring Data/Node.js can be configured on client, database, collection, or per operation depending on the driver.

### 8.1. A closer secondary is not always suitable

A user near a secondary may receive responses quickly due to low network RTT, yet:

- The secondary may lag on the oplog;
- Read concern may not guarantee fresh state;
- Missing indexes/slow queries stay slow even on a nearby node;
- If the node holds an older snapshot, returned data can be stale.

If an endpoint displays view counts tolerating a few seconds of lag, secondary reads can make sense. If an endpoint checks "is this account locked?" requiring latest state and real-time order, node/concern selection must be stronger.

### 8.2. `maxStalenessSeconds` does not prove data is the latest

Some drivers allow filtering secondaries by estimated staleness. This is a **server selection policy** with its own conditions/limits, not a linearizability protocol or proof every read is at most N seconds behind the primary under all failure modes.

To commit to exact freshness, monitor replication lag, align sessions/consistency, and define application behavior when sufficiently fresh data is unavailable.

## 9. Majority does not mean linearizable

A very common misconception:

> "Just write with `w: "majority"` and read with `readConcern: "majority"`, and the system linearizes all operations."

That conclusion is **too strong**.

### 9.1. What does majority write protect?

Suppose PSS:

```text
P   wrote version=11
S1  wrote version=11
S2  is at version=10
```

If P and S1 acknowledged per majority rules, writing version 11 can be majority-acknowledged. The system can tolerate node failures without losing majority-committed state under replica set guarantees.

However, S2 has not caught up. A read from S2 with `readConcern: "majority"` does not automatically know the client wants P's latest state **at that exact moment**.

### 9.2. When is a linearizable read needed?

Suppose a service decides whether to keep a "payment gateway" open. Once an administrator **completes** locking the gateway via a majority write, any read starting afterward must observe the locked state.

This approaches a **real-time ordering** requirement. On an eligible single document, you can use:

- Majority write for the state transition;
- Linearizable read from primary to verify state under supported guarantees;
- Read timeouts and error handling when quorum is lost.

If conditions cannot be verified during a partition, the read **times out** instead of returning an old answer masquerading as the latest.

### 9.3. Never use linearizable reads instead of multi-document transactions

A critical query on **one document** differs from transferring funds between two accounts stored in two documents.

For multi-document invariants, design transactions, unique constraints, data models, write concerns, and retry logic appropriately. A linearizable read on one document does not guarantee two other documents were read from the same snapshot.

## 10. Causal consistency: preserving causal order within a session

Some scenarios do not require every global client to see updates instantaneously, yet a user **must see the effects of their own prior operation**.

Example:

```text
T1: User updates display name to "Minh".
T2: Server acknowledges the write operation.
T3: User reopens their profile from a secondary.
```

If T3 reads a lagging secondary, the profile may display the old name, creating a "just updated, yet my change disappeared" experience.

MongoDB supports **causally consistent sessions** to protect causal relationships among operations in the same session when related read/write conditions are satisfied.

### 10.1. Commonly cited guarantees

Inside a causally consistent session with proper settings, you can achieve:

- **Read-your-writes:** reads after writes observe prior writes in the session;
- **Monotonic reads:** never seeing an older version after observing a newer one;
- **Monotonic writes:** writes in the session preserve causal order;
- **Writes-follow-reads:** writes following a read relate causally to the observed state.

A crucial requirement for strong causal guarantees is using **majority read concern and majority write concern** on related operations, within the same session, per driver guidelines.

### 10.2. Causal consistency can increase latency

Suppose a session wrote `version=12` on primary and got majority acknowledgment. On a subsequent read from secondary S2:

```text
S2 has only applied up to version=11.
Session requires reading at or after the causal milestone of version=12.
```

The read may have to **wait for S2 to catch up** or fail within the configured deadline. This is a latency trade-off to prevent "read-your-writes going backward."

Causal consistency **is not equivalent** to cluster-wide linearizability across unrelated clients.

### 10.3. Never share one session arbitrarily across independent threads

Operations in a session must follow driver concurrency rules. Never share one session arbitrarily across parallel requests or independent users expecting causal ordering to sort itself out.

Sessions also tie to lifecycle, auth context, and resource management. In web APIs, explicitly decide which flows need causal continuity and how to pass/advance context if spanning requests.

## 11. Snapshots and transactions: multi-operation consistency

Suppose business logic updates:

```text
orders.status = "PAID"
payments.status = "CAPTURED"
```

Writing two collections with two separate non-transactional commands risks clients observing "order paid while payment not yet updated" in between.

MongoDB supports **multi-document transactions** on eligible deployments. A transaction with snapshot read concern and proper commit write concern provides a more consistent logical unit of work.

### 11.1. `mongosh` example in a suitable environment

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  sessionDb.orders.updateOne(
    { _id: "ORDER-201", status: "PENDING" },
    { $set: { status: "PAID" } }
  );

  sessionDb.payments.updateOne(
    { _id: "PAY-201", status: "AUTHORIZED" },
    { $set: { status: "CAPTURED" } }
  );

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Actual transaction state must be handled based on the received error.
  }
  throw error;
} finally {
  session.endSession();
}
```

This illustrates transaction scoping, **not complete retry logic**. Production code must verify `matchedCount`, business preconditions, transient error retries, unknown commit results, and idempotency.

### 11.2. Transactions do not eliminate all trade-offs

Transactions may require:

- Waiting for coordination and commit steps;
- Holding snapshot/cache resources throughout the transaction;
- Resolving write conflicts;
- Retrying on primary stepdowns/partitions;
- For sharded transactions, extra cross-shard coordination overhead.

A very long transaction is not an unconditional solution for multi-hour reports. Controlled snapshot reads, materialized data, or periodic reporting designs may fit better.

### 11.3. Snapshot does not replace commit policy

Setting `readConcern: "snapshot"` on a read/write transaction without understanding write concern at **commit** can misalign durability expectations. For strong guarantees, evaluate **snapshot read concern, majority write concern at commit**, and driver/server rules together.

Do not treat the phrase "ACID transaction" as a substitute for full failover and timeout design.

## 12. Timeline: same network failure, three different outcomes

Consider PSS and chronological events:

```text
T0: P, S1, S2 are all healthy.
T1: P receives update: flag = true.
T2: S1 acknowledges update; S2 has not applied yet.
T3: Update is majority-acknowledged.
T4: Network partition isolates P.
T5: S1 + S2 hold an election; one node becomes primary.
T6: Clients attempt reads/writes from each side.
```

### 12.1. Write at T1 with `w: 1`

If the write gets ACK right after P applies it, and then P is isolated **before enough replicas receive the write**, the record may not yet belong to majority-committed history. It can roll back if the quorum-holding side elects a history without that write.

**A `w: 1` acknowledgment is not a certificate of majority durability.**

### 12.2. Write at T3 with `w: "majority"`

If the operation was majority-acknowledged prior to the partition, a new primary validly elected from data-bearing voting members per replication/election rules preserves majority-committed commitments within MongoDB's guarantees.

This does not eliminate risks from beyond-model disasters: losing all required replicas, storage corruption, operator error, accidental deletion, or lacking backups can still lose data.

### 12.3. Read at T6 from a lagging secondary

Even once `flag=true` is majority-committed, a secondary that has not yet applied up to that point may return an older majority snapshot unless appropriate causal/linearizable requirements are enforced.

For endpoints tolerating eventual freshness, that may be acceptable. For endpoints checking access permissions or security locks, design rejection/waiting rather than returning stale decisions.

## 13. Network partition matrix by topology

### 13.1. PSS: three data-bearing members

| Scenario | Election | `w: 1` writes | `w: "majority"` writes | Reading from secondary |
|---|---|---|---|---|
| P, S1, S2 all healthy | Has primary | Yes when primary ready | Yes when replication healthy | Possible, depending on preference/concern |
| One secondary lost | P + remaining secondary hold quorum | Yes | Usually yes | Yes from remaining secondary, depending on state |
| Primary lost, S1 + S2 remain | Can elect new primary | Interrupted until new primary | Interrupted then can resume | May serve some reads before election finishes |
| P isolated, S1 + S2 connected | Minority P must step down; two-vote side can elect | P side cannot validly write after losing quorum; majority side can write post-election | Majority side can write post-election if two data copies healthy | Can read within selected constraints |
| All three isolated into 1 + 1 + 1 | No side has two votes | No valid primary once quorum loss detected | No | Some nodes may serve weaker reads depending on role/state |

The words "possible" and "may" are intentional: primary state, freshness, candidate eligibility, heartbeat timeouts, replication lag, and server selection all shape real outcomes.

### 13.2. PSA: two data-bearing members and one arbiter

| Live/connected nodes | Election quorum | Available data copies | New majority writes |
|---|---|---|---|
| P + S + A | 3/3 | 2 | Can satisfy |
| P + S | 2/3 | 2 | Can satisfy |
| P + A | 2/3 | 1 | **Insufficient data acknowledgments** |
| S + A, P lost | 2/3 | 1 | **Insufficient data acknowledgments**, though S can be elected |
| Only P or only S | 1/3 | 1 | No valid primary quorum |
| Only A | 1/3 | 0 | Cannot accept writes |

The pain point of PSA is that **election availability and majority-write availability can diverge**. The system has a primary, yet APIs requiring `w: "majority"` still time out.

### 13.3. Five voting data-bearing members

```text
P + S + S + S + S
V = 5
Q = 3
```

In terms of votes, the system tolerates losing two voting members while retaining three votes. However:

- An eligible candidate must remain;
- Enough data-bearing members must remain to acknowledge majority writes;
- The network must form a connected partition;
- Remaining nodes must have enough capacity for the workload.

Five members do not mean "any arbitrary two failures are safe" if two failures hit correlated failure domains or remaining members are unhealthy.

## 14. Trade-offs in multi-region systems

Suppose an application serves users in Hanoi, Singapore, and Frankfurt. Goals:

- Order writes survive normal failovers;
- Catalog reads stay fast near users;
- Survive losing an entire region while retaining service;
- Minimize end-to-end latency.

One PSS placement:

```text
Region A: Primary + main writer app
Region B: Secondary
Region C: Secondary
```

### 14.1. Majority writes may depend on cross-region RTT

For majority writes in PSS, the primary needs acknowledgments from **at least one secondary** besides itself per majority rules. If secondaries are distant, write latency can depend on RTT to the nearest qualifying region.

A PSS majority write does not wait for **all** secondaries, only enough copies. If the nearest secondary slows down/fails, the distant secondary becomes necessary, raising latency.

Illustrative example, **not real benchmarks**:

```text
Primary apply/journal:        3 ms
Nearby secondary ACK:         8 ms
Distant secondary ACK:       70 ms

When healthy:
  majority write can complete after nearby secondary's ACK.

When nearby secondary is down:
  majority write must wait for distant secondary.
```

Actual timings depend on network RTT, storage, replication scheduling, transactions, traffic, and journaling; never sum a few theoretical numbers while ignoring parallel execution.

### 14.2. Secondary reads near users

Reading from a secondary close to users reduces network latency and primary load. However, if the secondary lags, users may see:

```text
Primary:   order.status = "PAID"
Secondary: order.status = "PENDING"
```

Appropriate UX choices include:

- List/history pages allowing refresh and showing sync timestamps;
- Transaction confirmation screens reading from primary/causal sessions when needed;
- Final state-decision operations reading from a strong authoritative source;
- Returning "Syncing" rather than making false assertions when freshness cannot be met.

### 14.3. Failure domains matter more than host counts

Three `mongod` processes in one rack do not provide the power/rack fault tolerance of three `mongod` processes across three independent failure domains.

However, spreading nodes across three regions increases network RTT and operational complexity. Balance **RPO, RTO, p95 latency, replication lag, data-transfer cost, and failover resilience**.

## 15. Latency budgets for an operation

For SLA design, break down time by work phase rather than looking only at total latency.

Order example:

```text
Client request timeout:        3000 ms
  ├─ Server selection / connect
  ├─ Primary write
  ├─ Wait for majority replication
  └─ Response transmission
```

Under healthy conditions, the operation meets its SLA. When required secondaries lag:

```text
Application requests w:majority
        ↓
Primary applied
        ↓
Secondary fails to ACK in time
        ↓
wtimeout or client timeout
```

Distinguish two timeout categories:

- **`wtimeout`:** waiting for write concern;
- **Driver/client/network timeouts:** can happen during server selection, connection, socket read/write, or other stages.

Adding `wtimeout` **does not make a partition available**. It merely stops one processing stage from blocking indefinitely so the application can react appropriately.

### 15.1. Short timeouts do not create stronger consistency

Setting `wtimeout: 100` ms instead of 5000 ms does not make data safer. It increases timeout errors across cross-region links. Setting timeouts too high can exceed HTTP request SLAs, causing clients to abort while the server continues processing.

Allocate budgets across:

1. Server selection;
2. Query execution/primary write;
3. Replication acknowledgment;
4. Retries if permitted;
5. Overall request deadline.

Verify alignment across timeouts in drivers, API gateways, load balancers, and upstream services.

### 15.2. Never use average latency to represent failure behavior

An environment with p50 write latency of 12 ms yet p99 of 900 ms during network jitter can severely impact checkout. Report:

- p50, p95, p99;
- Timeout rate;
- Retry rate;
- Election frequency;
- Secondary replication lag;
- Count of requests failing desired concern levels;
- Time without a primary;
- Behavior when a region fails.

## 16. Distinguishing "returning stale data" from "non-durable writes"

Two risks often lumped together as "eventual consistency":

### 16.1. Stale read

Read returns an older version:

```text
Primary:   version 12
Secondary: version 11

Secondary read → version 11
```

If version 12 was majority-committed, reading from the secondary is just **lagging behind**, not losing version 12.

Applications can handle this with causal sessions, reading primary, waiting for secondaries per causal milestone, or showing a "updating" status.

### 16.2. Rollback of non-majority-committed writes

A `w: 1` write ACKed on the primary without sufficient replication is followed by primary loss and a new history excluding the write. The write can roll back. This is a **durability/commit** issue, not merely a secondary not updating the UI yet.

You cannot fix a rollback by "refreshing the page" if the data genuinely no longer exists in the elected history; the application must handle it per business policy.

### 16.3. Data conflicts in external multi-writer models

A MongoDB replica set uses one quorum-validated primary under standard operation. If an application builds two independent databases across two regions allowing each region to write independently during partitions, that is an **application-designed multi-writer architecture**, not a native capability of a single MongoDB replica set.

In that case, you must define conflict resolution, event ordering, merging, duplicate handling, and business rules. You cannot use `w: 1` on two independent clusters and expect MongoDB to automatically merge all transactions cleanly.

## 17. Designing by per-workload guarantee levels

Not all data needs linearizable reads.

| Workload | Commonly considered guarantee | Trade-offs |
|---|---|---|
| Product view counts | Tolerates delayed reads and deferred updates | Prioritizes latency/throughput; can be stale |
| Public article listings | Secondary reads or caches with suitable TTL | Items may appear slightly delayed |
| Profile just edited by the same user | Causal session or primary read per contract | May wait or increase latency |
| Critical feature flag lock state | Majority writes; linearizable single-doc read when truly required | Can fail/time out during partitions |
| Order placement needing deduplication | Majority write + unique business key + retry/idempotency | Write latency, more complex error handling |
| Conditional inventory deduction | Atomic single-document update with predicate and proper write concern | Can reject when condition is no longer met |
| Multi-document funds transfer | Transactions and proper commit/retry strategy | Coordination overhead, lower availability on failure |
| Period-end financial reports | Snapshots/immutable materialized datasets | Report generation delay and snapshot storage cost |
| Near real-time summary dashboards | Caches, materialized summaries, or event processing | Disclosed synchronization lag |

This table offers design suggestions. Final decisions depend on regulatory constraints, data sensitivity, failover models, and product accuracy needs.

### 17.1. Prioritize per-endpoint contracts

Two endpoints querying the same `orders` collection can have distinct requirements:

```text
GET /orders?status=PAID
  Allows listing updates delayed by a few seconds.

GET /orders/{id}/confirmation
  Displays "paid" only after confirmed state.
```

Using a single shared read preference/concern across all endpoints without analyzing business needs leaves some paths needlessly slow and critical paths too weak.

## 18. Atomic single-document updates and business consistency

Some invariants can be enforced directly with **atomic single-document updates** rather than multi-document transactions.

Example keeping inventory non-negative:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-001",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  },
  {
    writeConcern: { w: "majority", wtimeout: 5000 }
  }
);
```

Meaning:

1. Condition checks `available >= 2`;
2. If matched, decrements 2 in one atomic document operation;
3. Write concern enforces the required acknowledgment level.

This avoids the dangerous pattern:

```text
Read available = 2
Two clients both decide to buy 2
Both write subtract 2 in non-atomic steps
```

However:

- Document operation atomicity does not mean majority-committed if ACKed only with `w: 1`.
- `matchedCount = 0` may mean insufficient stock; do not retry endlessly.
- Write concern timeouts create **uncertain** outcomes; if the client resends `$inc` without idempotency, stock can be deducted twice.
- If inventory and orders across two documents must stay coordinated, design a suitable transaction or saga.

### 18.1. Idempotency keys help handle uncertainty

Example of an order-creation command with a fixed business ID:

```javascript
db.orders.updateOne(
  { _id: "ORDER-CLIENT-REQUEST-9931" },
  {
    $setOnInsert: {
      customerId: "C-101",
      status: "NEW",
      createdAt: new Date()
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
```

If the same request retries, a stable `_id` reduces the risk of creating two orders from one request. Still verify payload equivalence, authorization, update conflicts, and downstream duplicate actions; a fixed `_id` is only part of idempotency.

Never assume driver retryable writes completely replace **business-level idempotency** for multi-step workflows.

## 19. Never silently lower consistency during partitions

A knee-jerk reaction:

```text
When majority write times out:
  switch the whole system to w:1
  allow all transactions to proceed
```

This can restore partial write availability **if a valid primary still exists** and only data acknowledgments are lacking. However, it also:

- Weakens durability guarantees for new writes;
- Increases risk of rollbacks/lost acknowledged writes;
- Helps nothing when no quorum primary exists;
- Silently breaks write contracts without users knowing;
- Can compromise transactions and business invariants.

Therefore, never silently downgrade write concerns for critical transactions.

### 19.1. Degraded modes with explicit contracts

Some systems can support:

- **Read-only:** temporarily block mutations when required write guarantees cannot be met;
- **Cached reads:** show stale data with last-updated timestamps;
- **Accept requests without committing:** enqueue requests into an independent durable queue if architected for it, returning `PENDING` rather than "Paid";
- **Fail fast:** return service-unavailable/retryable errors to avoid holding HTTP connections indefinitely;
- **Feature degradation:** allow catalog browsing while pausing checkout.

An ingestion queue **requires its own durability and partition analysis**. You cannot switch to a non-durable queue and consider the problem solved.

### 19.2. When to fail closed?

For operations like locking/granting permissions, funds transfers, committed inventory deductions, or system-wide uniqueness checks, "unable to verify latest state" must lead to **rejection/waiting**, rather than returning an affirmative decision based on stale reads.

This is a business safety policy, not a single read concern toggle replacing all logic.

## 20. `mongosh` examples: comparing concerns via explicit commands

These commands can run on a test replica set with appropriate privileges and versions. They do not require inducing network partitions to understand configuration differences.

### 20.1. Reading topology and status

```javascript
rs.conf();
rs.status();
```

Inspect:

- Current primary;
- Healthy secondaries and replication lag;
- Voting members and arbiters if present;
- Election history and heartbeat messages;
- Whether enough primary candidates and quorum remain.

### 20.2. Writing with majority concern

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "O-243-A",
      customerId: "C-101",
      status: "CREATED",
      createdAt: new Date()
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 5000
  }
});
```

Under healthy conditions, the command succeeds once the write meets the requested concern. When replication is disrupted, inspect **write concern errors**, error labels, and command results; never assume a timeout means no write occurred.

### 20.3. Reading with `majority`

```javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-243-A" },
  limit: 1,
  readConcern: { level: "majority" },
  maxTimeMS: 5000
});
```

Read concern `majority` requests data that has reached majority commit per supported mechanics. It **does not create linearizability guarantees for all clients** simply because primary/secondaries are read.

### 20.4. Reading with `linearizable`

```javascript
db.runCommand({
  find: "orders",
  filter: { _id: "O-243-A" },
  limit: 1,
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
```

This command must route to the primary and suits eligible single-document reads. If quorum is unmet, it fails instead of returning stale data. Do not benchmark latency from a single execution, and never run heavy load tests on a production primary.

### 20.5. Checking default concerns

```javascript
db.adminCommand({ getDefaultRWConcern: 1 });
```

Identify deployment implicit/default settings alongside per-operation policies; pay special attention to topologies with arbiters.

## 21. Java MongoDB Driver: configuring by contract

Java Sync Driver example using collection views with explicit read/write levels:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

MongoDatabase database = mongoClient.getDatabase("app");

MongoCollection<Document> orders = database
    .getCollection("orders")
    .withReadPreference(ReadPreference.primary())
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(
        WriteConcern.MAJORITY.withWTimeout(5, TimeUnit.SECONDS)
    );

orders.insertOne(new Document("_id", "O-243-B")
    .append("status", "CREATED")
    .append("customerId", "C-102"));

Document order = orders.find(
    new Document("_id", "O-243-B")
).first();

System.out.println(order);
```

The goal is showing **per-collection and per-operation configuration**. Real applications must also manage `MongoClient` lifecycles, authentication, exception handling, retries, and DTO mapping; not every read needs the exact same concern.

### 21.1. Linearizable reads for a dedicated collection view

If an API checks a critical status document:

```java
MongoCollection<Document> flags = database
    .getCollection("systemFlags")
    .withReadPreference(ReadPreference.primary())
    .withReadConcern(ReadConcern.LINEARIZABLE);
```

The application still needs appropriate driver/request timeouts and exception handling when read concern cannot be met. Never apply `ReadConcern.LINEARIZABLE` globally to analytics queries or secondary reads.

### 21.2. Causal sessions in Java

Conceptual example:

```java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

ClientSessionOptions options = ClientSessionOptions.builder()
    .causallyConsistent(true)
    .build();

MongoCollection<Document> profiles = database
    .getCollection("profiles")
    .withReadPreference(ReadPreference.secondaryPreferred())
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(WriteConcern.MAJORITY);

try (ClientSession session = mongoClient.startSession(options)) {
    profiles.updateOne(
        session,
        new Document("_id", "USER-101"),
        new Document("$set",
            new Document("displayName", "Minh"))
    );

    Document profile = profiles.find(
        session,
        new Document("_id", "USER-101")
    ).first();

    System.out.println(profile);
}
```

This shows the same session used for update and read, with majority write/read concerns. When secondary reads lag behind the causal milestone, waiting or timing out is part of the trade-off.

Verify driver/server versions, cross-request context distribution, sequential execution, and real timeouts. Causal sessions are not objects to be shared concurrently across parallel HTTP requests without coordination.

## 22. Network partition experiments: only in controlled staging

A CAP/PACELC exercise is far more valuable when measuring application behavior **under intentional fault conditions**. However, never sever networks, stop `mongod`, or force elections in production.

### 22.1. Experiment setup

Environment:

```text
Test replica set: PSS
P:  mongo-a
S1: mongo-b
S2: mongo-c

Client 1: uses primary + w:majority
Client 2: uses secondaryPreferred + readConcern:majority
Client 3: uses primary + readConcern:linearizable
```

Before testing, create a document with an incrementing version:

```javascript
db.consistencyLab.updateOne(
  { _id: "counter-1" },
  {
    $setOnInsert: {
      version: 0,
      createdAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: { w: "majority", wtimeout: 5000 }
  }
);
```

Update step:

```javascript
db.consistencyLab.updateOne(
  { _id: "counter-1" },
  { $inc: { version: 1 } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

To verify written versions reliably, use a single writer or operation IDs; never manually retry `$inc` repeatedly after ambiguous outcomes because it can increment twice.

### 22.2. Phases to measure

1. **Healthy:** read and write across concerns; record p50/p95 latencies.
2. **One lagging secondary:** observe `replication lag`, majority write latency, and stale read behavior.
3. **Primary lost:** observe the primary-less window, election, and client-side errors.
4. **A 1/2 partition:** identify which side holds quorum and which node steps down.
5. **Connectivity restored:** observe secondary catch-up and application recovery.
6. **Compare read preferences:** test primary vs. secondary reads, noting selected consistency semantics.

### 22.3. Metrics to collect

| Metric | Reason |
|---|---|
| Primary election duration | Impacts write availability |
| Time without writable primary | Measures write RTO |
| Majority write p50/p95/p99 | Cost of waiting for replication |
| `wtimeout` rate | Frequency of unmet write concerns |
| Read error/timeout rate | Viability of strong-concern reads |
| Secondary replication lag | Exposure to stale reads |
| Retry counts | Overhead and duplicate risks |
| Data rollback events | Risk to non-majority-committed writes |
| Version observed by reader | Validates causal/freshness behavior |
| CPU/network/storage | Distinguishes resource exhaustion from partitions |

You cannot extrapolate one demo to assert all MongoDB versions and multi-region topologies share identical latencies. Record exact configs, versions, write/read concerns, fault-injection methods, and baseline load.

## 23. Hybrid patterns balancing performance and reliability

### 23.1. CQRS / separating read and write paths

A system may use:

```text
Command / Write API
   └── MongoDB primary, majority write

Query / Read API
   ├── MongoDB secondary
   ├── materialized view
   └── cache
```

Advantage: reads scale independently and return fast.

Trade-off: read models/caches **carry synchronization lag**; never present them as reflecting the immediate committed state of a transaction. Use versions, `lastUpdatedAt`, explicit refreshes, or primary queries for confirmation screens.

### 23.2. Outbox pattern

When creating an order must also emit a downstream event, write both the order and an outbox record inside an appropriate transaction, commit with required write concern, and have a worker read the outbox to dispatch events.

Properly designed, this reduces the risk of "order created yet message lost." However:

- Outbox still depends on MongoDB commit durability;
- Workers/consumers require idempotency;
- When the replica set loses quorum, transaction commits cannot complete;
- Having an outbox does not automatically yield exactly-once event delivery.

### 23.3. Caches and explicitly labeled stale data

If a partition occurs while users still need to browse a catalog, serve from cache:

```javascript
{
  items: [
    { sku: "SKU-101", name: "Keyboard" }
  ],
  dataTimestamp: "2026-11-14T08:00:00Z",
  freshness: "STALE",
  actionsAllowed: ["VIEW"]
}
```

This is an **application-designed response**, not automatic MongoDB metadata. It is far clearer than returning cached data as if it were live.

For operations with financial impact, the application may need to disable actions until authoritative state is reachable.

## 24. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| "Three `mongod` nodes guarantee surviving one failure and still majority-writing." | Must check whether all three store data; PSA differs from PSS. |
| "Arbiters help confirm data was replicated." | Arbiters only vote; they store no data copies. |
| "As long as primary is alive, any write works." | Losing quorum forces primary stepdown; strong write concerns can fail. |
| "`w: 1` and `w: "majority"` differ only in speed." | They differ in durability and rollback risk as well. |
| "`wtimeout` means the insert completely failed." | Primary may have applied it without reaching acknowledgment threshold. |
| "Writing with majority makes every secondary see data instantly." | Secondaries can still lag. |
| "Majority read is linearizable." | No; majority-committed visibility differs from real-time ordering. |
| "Linearizable reads can run on any secondary." | Must target primary within supported scope. |
| "Snapshots are always the latest." | Snapshots are consistent at a milestone, not necessarily latest. |
| "Causal sessions synchronize all global clients." | Guarantees causal order under session rules; does not create global linearizability. |
| "`nearest` read preference returns the newest copy." | `nearest` optimizes node selection by latency, not freshness. |
| "Switching to `secondaryPreferred` solves all partitions." | Helps some reads, but creates neither primary nor quorum for writes. |
| "Lowering all writes to `w: 1` carries no risk." | Increases rollback/lost acknowledged write risks and fails where primary is lost. |
| "Transactions eliminate write concern concerns." | Commit concern, retries, and failovers still matter. |
| "Good indexes guarantee low majority latency." | Indexes speed queries; replication/network still dominate latency. |
| "CAP means picking C, A, or P once for the whole database." | Contracts must be defined per operation, topology, and failure mode. |
| "Returning HTTP 200 means the system is still available." | Must verify responses meet business freshness/durability contracts. |

## 25. Checklist for designing a read/write API

Before deploying a critical endpoint, answer:

1. **How much data loss after a crash is tolerable?** Define RPO.
2. **How long can writes be unavailable?** Define RTO/SLO.
3. **Must clients see the latest version, or is staleness allowed?** Define freshness/consistency.
4. **Which write concern actually applies?** Per-operation, client, or cluster default.
5. **Which read concern and read preference apply?** Primary, secondary, majority, linearizable, or snapshot?
6. **When quorum is lost, what does the API do?** Timeout, retry, read-only, queue, or fail closed?
7. **On ambiguous timeouts, can retries create duplicates?** Idempotency keys, unique constraints, reconciliation.
8. **Are enough data-bearing replicas placed in independent failure domains?** Never just count votes.
9. **Are replication lag and elections monitored?** Set actionable alerts.
10. **Are total and component timeouts compatible with SLAs?** Never exceed upstream deadlines.
11. **Are rollback recovery and backups tested?** Replication does not replace backups.
12. **Are fault drills run on staging?** Never test only the happy path.

## 26. Practice exercises

### Exercise 1 — CAP in a 1/2 partition

A PSS set has primary A and secondaries B and C; A is isolated from B+C.

1. Which side holds election majority?
2. Why can A not keep valid primary authority once quorum is lost?
3. What must B+C do before accepting writes?
4. Under what conditions can a secondary on a minority side still return stale data?
5. What happens if a client demands a linearizable read when quorum is unreachable?

### Exercise 2 — Comparing write concerns

An application writes a document with:

```javascript
{ writeConcern: { w: 1 } }
```

versus:

```javascript
{ writeConcern: { w: "majority", wtimeout: 5000 } }
```

Explain differences in ACK, rollback risk, latency, and behavior when a required secondary does not respond. Why does `wtimeout` not allow concluding the record was definitely canceled?

### Exercise 3 — Can majority reads be stale?

PSS has P, S1, S2. `version=12` is majority-committed on P+S1, while S2 is only at `version=11`.

1. What can a `majority` read on S2 see?
2. Why is that answer not automatically linearizable?
3. When should a causal session be used?
4. If the absolute latest state of one document after a completed write is required, which read concern should be evaluated?

### Exercise 4 — PSS vs. PSA

Compare:

```text
PSS = P + S + S
PSA = P + S + A
```

When one secondary is lost:

- How many votes remain?
- How many data-bearing members remain?
- Can a primary be elected/maintained?
- Can `w: "majority"` complete?
- What is the risk of dropping down to `w: 1`?

### Exercise 5 — Priority and candidates

A replica set has three data-bearing voting members:

```text
A: priority=3, votes=1
B: priority=0, votes=1
C: priority=0, votes=1
```

If A fails, B+C hold enough votes. Why is there still no primary candidate? Propose a different priority setup that prefers A while still allowing failover.

### Exercise 6 — Designing read-after-write

A user successfully updates their avatar, then reads their profile from the nearest secondary and sees the old avatar.

1. Is this a stale read or a rollback?
2. Draft an API contract using a causal session or primary reads.
3. Describe the latency cost when the secondary lags behind the causal milestone.
4. Should linearizable reads be used for all profile pages? Why or why not?

### Exercise 7 — Order transaction timeout

An order-creation API receives a write concern timeout. The client resends `insertOne()` with a different random `_id`.

1. What is the business risk?
2. Why does the timeout not mean the first operation was canceled?
3. Design an appropriate idempotency key and unique constraint.
4. When should database state be checked after a retry?
5. Distinguish driver-level retryable writes from workflow-wide idempotency.

### Exercise 8 — Linearizable read or snapshot?

Two problems:

- A: checking a `paymentsEnabled` flag updated with majority, requiring every read after lock completion to see the new state.
- B: generating a revenue and order count report across multiple collections at one consistent point in time.

Which fits single-document linearizable reads? Which needs snapshot/transactions or materialized datasets? Why can one concern level not replace all others?

### Exercise 9 — Multi-region latency

PSS has primary in Region A, secondaries in B and C. B is closer to A than C.

1. While B is healthy, which node may govern majority write latency?
2. When B goes down, how can majority write latency change?
3. Reading from C near end users improves network RTT, yet introduces what risk?
4. List metrics to measure before declaring the topology meets its SLA.

### Exercise 10 — Designing degraded modes

A service supports catalog browsing and purchasing. When majority writes cannot be confirmed:

- Which endpoints can serve cached data?
- Which endpoints must return errors/wait or pending statuses?
- What fields should be added to responses to describe freshness?
- Why should you not lower write concerns for inventory deduction and payments?
- If using a queue for pending requests, how must queue durability be ensured?

### Exercise 11 — Controlled failover drill

On a PSS staging environment:

1. Write a document with `w: "majority"` and record ACK latency.
2. Observe status/lag in `rs.status()`.
3. Induce a controlled node failure per operations team runbooks.
4. Measure primary-less duration.
5. Retry majority write concern and majority reads.
6. Record application driver recovery time.
7. Compare latency, timeout rates, and data before/after.

Never perform fault-injection experiments on production without authorization and full preparation.

## 27. MongoDB references

- [Replication](https://www.mongodb.com/docs/manual/replication/)
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/)
- [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/)
- [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [Replica Set Arbiters](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/)
- [Default Read/Write Concern](https://www.mongodb.com/docs/manual/reference/command/getDefaultRWConcern/)
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)

## Conclusion

The trade-off among **consistency, latency, and availability** in MongoDB is more than asking "how many nodes are in the cluster?" During network partitions, **election vote majority** determines where a valid primary can persist; **actual data replica count** and write concern determine how strongly writes can be acknowledged. A PSA set may retain a primary via its arbiter, yet **cannot satisfy `w: "majority"` writes** when its data-bearing secondary is lost.

A **`w: 1`** write reduces wait time at the cost of higher rollback risk compared to a majority-acknowledged write within replica set guarantees. A **`majority`** read avoids uncommitted writes, yet **does not guarantee latest/linearizable reads** from a lagging secondary. **Causal consistency** preserves operation relationships within a session; **linearizable reads** suit real-time single-document decisions; **snapshots** serve multiple reads on a consistent logical state. Each choice carries its own costs and limits.

When failures strike, a reliable system never secretly rewrites its business contract. Define **RPO/RTO, required freshness, read/write concerns, failure domains, timeouts, retry/idempotency, and degraded modes** upfront during design. For data tolerating staleness, disclose how stale it is; for operations that must never be wrong, wait or reject when guarantees cannot be met. **True availability means returning responses faithful to the API's promise, not merely having some node respond.**
