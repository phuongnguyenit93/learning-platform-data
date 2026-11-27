# Majority Commit Point and Rollback Risk After Incidents in a MongoDB Replica Set

## 1. Does a Successful Write Command Mean Data Will Survive Failover?

Suppose an order application writes to MongoDB:

~~~javascript
db.orders.insertOne({
  _id: "order-1001",
  tenantId: "t001",
  status: "created",
  amount: NumberDecimal("200.00")
});
~~~

The command returns success. One second later, the **replica set** primary disconnects; the secondaries elect a new primary. When the application reads again, the newly created order **no longer exists**.

This can happen if the write was acknowledged only by the primary without becoming part of the **majority-committed** history. When another primary is elected, writes lying on an unselected history branch may have to **roll back**.

This lesson distinguishes four easily confused concepts:

1. **Primary received/applied the write**: the operation exists on the primary at that point in time.
2. **Client received acknowledgment**: depending on **write concern**, this may only be acknowledgment from the primary.
3. **Majority commit point has advanced past the write**: the operation belongs to the oplog history confirmed by a majority of eligible copies.
4. **Application observes the data after failover**: depends on commit status, replication progress, read concern, and where reads are routed.

**Key message:** an acknowledged result with **w:1** does not guarantee majority-committed status. A write successfully acknowledged with **w:"majority"** is protected against rollback in normal replica set failover scenarios, assuming proper deployment and storage conditions.

### Learning Objectives

After this lesson, you will be able to:

- Explain **oplog**, **optime**, **majority commit point**, and the election process.
- Diagram two scenarios: a write **not yet majority-committed being rolled back** and a write **already majority-committed surviving** normal failover.
- Distinguish **w:1**, **w:"majority"**, **j:true**, and **wtimeout**.
- Understand why **writeConcernError** does not mean "the write definitely did not happen."
- Distinguish **readConcern "local"**, **"majority"**, **"snapshot"**, and result freshness.
- Observe **lastCommittedOpTime**, member states, and replication lag using read-only commands.
- Design retry/idempotency handling and transactions suited to rollback prevention requirements.
- Recognize the limits of majority in quorum-loss situations, misconfigurations, and severe incidents beyond normal failover.

> Examples illustrate only on a **practice replica set**; never intentionally shut down nodes, sever networks, or run configuration-changing commands in shared environments. Rollback is explained via timelines and analysis; ordinary lab exercises do not actively induce failures.

## 2. Replica Set Structure and Replication

### 2.1. Primary, Secondaries, and Oplog

A **replica set** is a group of MongoDB processes jointly maintaining copies of a logical dataset. In a typical three data-bearing member model:

~~~text
                  Application Client
                        |
                writes to Primary P
                        |
                 +------+------+
                 |             |
                 v             v
           Secondary S1   Secondary S2
             replicates     replicates
             oplog          oplog
~~~

The **primary** normally accepts application write operations. Changes are recorded in the **oplog** (operation log) in order; **secondaries** read and apply entries to maintain their data copies.

The oplog is not an infinite business audit log. It is a replication structure with bounded storage and its own lifecycle. When nodes diverge due to failover, the oplog is a key component for identifying shared history and operations that must be synced or rolled back.

### 2.2. Three Distinct States

Suppose a write operation generates oplog entry **E101**. It can pass through conceptual stages:

~~~text
Time A:
  Primary P   : ... E100 E101
  Secondary S1: ... E100
  Secondary S2: ... E100

Time B:
  Primary P   : ... E100 E101
  Secondary S1: ... E100 E101
  Secondary S2: ... E100

Time C:
  Primary P   : ... E100 E101
  Secondary S1: ... E100 E101
  Secondary S2: ... E100 E101
~~~

At **A**, only the primary has E101. With three data-bearing voting members, the operation has not yet reached majority.

At **B**, P and S1 both have E101; that is **2/3** of members. When corresponding replication/durability conditions are met, the entry can become **majority-committed** even though S2 has not received it yet.

At **C**, all three have it. Replication to every member **is not a mandatory prerequisite** for majority write concern in this three-member configuration.

**Replication is asynchronous.** Software cannot assume secondaries have received data merely because the primary returned acknowledgment with w:1.

### 2.3. Optime and Oplog History

MongoDB tracks operation positions in replication history using **OpTime** metadata, typically comprising:

- **timestamp (ts)**: logical position/timestamp in the oplog.
- **term (t)**: election epoch associated with the write history.

Fields like **appliedOpTime**, **durableOpTime**, and **lastCommittedOpTime** help observe corresponding milestones; exact semantics and structure depend on MongoDB version.

**Optime is not simply the server's wall-clock time.** Do not take two timestamps of different kinds, subtract milliseconds, and conclude "lag is exactly N ms" without understanding what they represent.

## 3. What Is the Majority Commit Point?

### 3.1. Intuitive Definition

The **majority commit point** is the latest oplog point MongoDB considers replicated to a majority of required voting data-bearing members under the replica set's replication/durability rules.

In a replica set with three data-bearing voting members:

~~~text
Primary P       : ... E100 E101 E102 E103
Secondary S1    : ... E100 E101 E102
Secondary S2    : ... E100 E101
                               ^
                             E101
~~~

At this hypothetical point:

- **E101** is present on P, S1, S2.
- **E102** is present on P and S1, reaching **2/3**.
- **E103** is only on P.

Assuming required durability conditions are satisfied, the **majority commit point can be at E102**. E103 remains an **uncommitted (non-majority-committed)** operation.

~~~text
Oplog on Primary:

... E100 -- E101 -- E102 || E103
                   ^
           majority commit point

Left of and at the mark: majority-committed history.
Right side: newer writes that may lack enough copies.
~~~

**Note:** the majority commit point is a **marker in oplog history**, not a document count in a collection, not "the latest command the client saw succeed," and does not necessarily match the primary's latest oplog entry.

### 3.2. The Commit Point Can Advance Even When Using w:1

Suppose a client sends E102 with write concern **w:1**. MongoDB may return acknowledgment right after the primary applies the operation per w:1 semantics. Afterward, secondaries continue replicating E102; once a majority holds it, the commit point advances past E102.

Therefore:

- **w:1 acknowledged** does not prove E102 was already majority-committed at response time.
- Yet **w:1 does not mean E102 will definitely roll back**. If E102 reaches majority before an election, it can still survive.
- **w:"majority" acknowledged** carries a stronger guarantee: acknowledgment waits for majority conditions to be met under the actual configuration.

Write concern is the **acknowledgment condition requested by the client**, whereas majority commit point is a **replication state of the replica set**.

### 3.3. Why Does Majority Prevent Rollback in Normal Failover?

Any two majority sets within the same voting configuration must intersect in at least one member. With three nodes P/S1/S2, any two 2/3 subsets share at least one member.

If E102 is majority-committed, any valid new primary must be elected under election and oplog-freshness rules. In normal failover, those rules protect majority-committed history from being discarded when electing a new primary.

~~~text
P : E100 E101 E102  (then fails)
S1: E100 E101 E102  (can become the new primary)
S2: E100 E101       (does not yet have E102)

E102 was majority-committed on P + S1.

After a valid election, the new history must continue from
majority-committed operations; S2 catches up rather than losing E102.
~~~

**This is a guarantee under normal system conditions**; do not interpret it as "data can never be lost in any disaster." Physical data loss on a majority of nodes, restoring wrong snapshots, configuration tampering, or failures outside normal assumptions still require backups and recovery procedures.

## 4. How Can a Write Be Rolled Back?

### 4.1. Scenario: E201 Exists Only on the Primary

Suppose a three-member replica set P, S1, S2 initially all share history up to E200:

~~~text
Before incident:

P  (PRIMARY)    : E198 E199 E200 E201
S1 (SECONDARY)  : E198 E199 E200
S2 (SECONDARY)  : E198 E199 E200

E201 is only on P; not yet majority-committed.
~~~

Sequence:

1. Client writes E201 to P with **w:1** and receives acknowledgment.
2. P becomes isolated or unavailable before S1/S2 replicate E201.
3. S1 and S2 form a majority and elect a new primary per election rules.
4. The new primary continues history without E201, potentially generating new entries under a new term.
5. When P returns, MongoDB must resolve the diverging history branch. E201 may be **rolled back** from P to align with the valid new primary's history.

~~~text
          Client receives ACK from P under w:1
                         |
                         v
P :  ... E200 -- E201     X  (P loses contact)
S1:  ... E200 -------------- E202 -- E203 (new history)
S2:  ... E200 -------------- E202 -- E203

When P returns:
          E201 lies on a diverging branch
          -> may be rolled back
          -> P syncs to the new history
~~~

**Key point:** the application may have received a success response and even read E201 back from P **before** the incident occurred, yet that response only reflected the requested write concern level.

### 4.2. What Is Rollback at the Data Level?

Rollback is the process by which MongoDB reverts the effects of operations on a history branch outside the valid new primary's oplog sequence, within MongoDB's supported scope and limits.

An operation can:

- **Insert** a document, and then that document vanishes after rollback.
- **Update** a document, and the old value is restored to match the shared history.
- **Delete** a document, yet the document reappears per the valid history.

In an application, this symptom can look like "a created order disappeared," "a recently updated status reverted," or "a deleted document came back." It is not necessarily an application cache bug; it can result from non-majority-committed replication history prior to failover.

Do not assume every rollback case can easily be recovered manually from a file. Some versions/configs save rollback data for investigation in a dedicated directory, yet that is **not a reliable backup** and does not replace proper write concern, business logs, or PITR.

### 4.3. Why Do Not All w:1 Writes Roll Back?

Suppose E201 is acknowledged with w:1, and then both P and S1 record E201 before P loses connectivity. Once E201 passes the majority commit point, it can survive across an election. **How the client requested acknowledgment does not permanently freeze the entry's replication state.**

The following two statements differ:

1. "The application **lacks a rollback-prevention guarantee** at the moment it receives a w:1 acknowledgment."
2. "Data acknowledged with w:1 **will definitely be rolled back**."

Only the first statement holds in general.

## 5. Scenario: Majority-Committed Write Survives Failover

### 5.1. E301 Confirmed by P and S1

Suppose:

~~~text
P  (PRIMARY)    : ... E300 E301
S1 (SECONDARY)  : ... E300 E301
S2 (SECONDARY)  : ... E300

E301 is replicated to 2/3 data-bearing voting nodes.
Durability conditions are satisfied.
Client receives success for w:"majority".
~~~

When P fails and S1/S2 remain active, S1 holds sufficiently fresh history to participate in the election and can become primary. S2 catches up on E301. Under valid election rules, the majority-committed history containing E301 is preserved.

Comparison:

| Criterion | E201 only on P, w:1 ACK | E301 majority-committed, w:"majority" ACK |
| --- | --- | --- |
| Applied on primary? | Yes | Yes |
| Client received ACK? | Yes | Yes |
| Reached majority in example? | **No** | **Yes** |
| Rollback risk if P fails and S1/S2 elect new primary | Yes | No in normal valid replica set failover |
| Can skip backups? | No | **No** |
| Means every secondary updated? | No | No |

### 5.2. Majority Does Not Require Every Secondary to Catch Up

If S2 lags by seconds, P + S1 can still satisfy majority for E301. A direct read hitting S2 may not yet see E301 **at the exact moment the client receives the ACK**, depending on read preference/read concern and replication apply progress.

**Majority write concern does not mean all copies updated simultaneously.** Rollback protection and read freshness from a specific secondary are two separate issues.

### 5.3. Do Not Treat "Majority ACK" as Protection Against All Disasters

Within a properly operating replica set, majority protects against **normal failover/elections**. However, it does not replace:

- Backups capable of restoring to required points in time.
- Verifying journaling and storage durability configurations.
- Procedures for simultaneous data loss across multiple members.
- Cross-region/cluster disaster recovery plans.
- Administrative controls when restoring snapshots or reconfiguring replica sets.

If every copy holding relevant data is physically lost or restored from an old backup, you cannot rely on the phrase "majority-committed" alone to recreate lost data.

## 6. Write Concern: What Does the Acknowledgment Level Determine?

### 6.1. w:1

Example:

~~~javascript
db.events.insertOne(
  {
    _id: "event-1",
    type: "order-created"
  },
  {
    writeConcern: { w: 1 }
  }
);
~~~

With **w:1**, the client asks the primary to acknowledge the operation per w:1 semantics. It does not wait for a majority of the replica set.

**Advantage:** can provide lower acknowledgment latency in many situations.

**Trade-off:** an acknowledged write may still lie beyond the majority commit point if failover strikes, risking rollback.

Do not write that "w:1 means the write is only in RAM." Where the write resides on storage/journal depends on the storage engine, **j**, and apply timing. The core point is that **w:1 does not require majority copy acknowledgment**.

### 6.2. w:"majority"

~~~javascript
db.events.insertOne(
  {
    _id: "event-2",
    type: "payment-confirmed"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**w:"majority"** requires the write condition to be met by a majority of eligible members before the client receives a successful acknowledgment. In a 3 data-bearing voting member replica set, this typically corresponds to **at least 2 members**.

**Advantage:** protects writes from rollback during normal failover/elections.

**Trade-off:** latency can increase if secondaries take longer to replicate/acknowledge; if insufficient required members are available, the request may fail to receive majority acknowledgment within the desired time.

### 6.3. w:0

**w:0** is an unacknowledged write concern: the client does not wait for the server to confirm the write outcome in the normal way. Never use this level for business operations that need to know whether orders, money, inventory, or audits were actually written.

Unacknowledged does not mean "fast and guaranteed to persist"; precisely because it skips waiting for confirmation, the application has less knowledge of the outcome.

### 6.4. Comparison

| Write concern | Acknowledgment condition | Rollback risk if not majority-committed | Use when |
| --- | --- | --- | --- |
| **w:0** | Does not wait for normal write confirmation | No majority guarantee | Only when risk is acceptable and outcome need not be known |
| **w:1** | Primary confirms per w:1 mechanics | **Yes** if failover happens before majority commit | Reproducible data, with assessed risk |
| **w:"majority"** | Majority of eligible copies confirm | Protected in normal failover after successful ACK | Orders, financial transactions, critical state |
| **w:N** | Configured number of members | Depends on N, topology, and ack rules | Special operational requirements |

No single write concern fits all systems. Choose based on **acceptable data loss**, latency requirements, topology, and recovery procedures.

## 7. Journaling: How Does On-Disk Durability Differ from Majority?

### 7.1. What Role Does j:true Play?

The **j: true** option enforces conditions relating to writing to the journal on participating members per write concern and storage engine rules. It emphasizes **durability on storage media**, distinct from merely counting how many members received the data.

Example:

~~~javascript
db.events.insertOne(
  { _id: "event-3", type: "important-state" },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
~~~

Depending on configuration, **w:"majority"** by default already relates to journal durability. The replica set setting **writeConcernMajorityJournalDefault** is an important configuration: normally it is **true**, yet you must verify it on the actual cluster rather than assuming mentally.

### 7.2. Majority and Journaling Are Two Orthogonal Axes

~~~text
Copy count axis:
    Primary only  -----------------  Majority

Local durability axis:
    Applied in memory only ---------  Journal/durable
~~~

A write can be acknowledged by the primary without waiting for majority. A write can reach multiple members while deployment journal policy governs when durability is confirmed. When stating "majority commit point protects against rollback," state **valid replication and durability assumptions**.

Do not shorthand "j:true = no rollback." **A journal on a single primary does not prevent that primary's history branch from being discarded if a new primary is elected.** Conversely, majority replication and journaling address different failure modes.

### 7.3. Distinguishing Rollback and Crash Recovery

| Incident | Primary Issue |
| --- | --- |
| Primary loses power, restarts, and continues same history | Recovering durable writes on storage |
| Primary isolated from quorum, new primary elected | May have to roll back diverging oplog |
| Multiple machines/disks lose physical data | Requires backups or recovery outside lost copies |
| Application sends same request twice | Requires idempotency; not a journaling problem |

Do not use a vague blanket term "durable" to gloss over differences between these scenarios.

## 8. wtimeout: A Timeout Does Not Mean the Write Was Undone

### 8.1. Waiting for Majority Without Enough Time

Example:

~~~javascript
db.events.insertOne(
  {
    _id: "event-4",
    type: "order-accepted"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

**wtimeout: 5000** sets a wait limit for the write concern condition, in milliseconds. If replication is slow or required members are unavailable, the command can return a **write concern timeout/error**.

Crucial point:

**A write concern timeout does not automatically roll back a write already applied by the primary.**

When a timeout occurs, it is possible that:

1. The primary applied the write, yet it is **not yet majority-committed**.
2. The write subsequently reaches majority and becomes durable per policy.
3. The primary fails over before majority commit, leaving the write outside the chosen history and rolled back.
4. The client does not know the exact final state if the response was lost/network failed.

Therefore, never read a write concern error and immediately conclude "no data exists" or re-send a non-idempotent operation blindly.

### 8.2. Distinguishing Three Outcome Types

| Condition Observed by Client | Valid Inference | Invalid Inference |
| --- | --- | --- |
| Success ACK with w:"majority" | Met the command's majority condition per config | Every secondary updated; no backups needed |
| Success ACK with w:1 | Primary confirmed at w:1 level | Definitely majority-committed |
| Write concern error/timeout | Desired ack condition was not confirmed within timeout | Command definitely did not apply, or definitely rolled back |
| Network timeout/disconnect | Client received no reliable outcome | Server never saw the request |
| Duplicate key on retry | Matching document/key already exists | Previous request definitely committed exact payload |

**Unknown outcome** is a normal state to design for in distributed systems. A reliable API must provide **reconciliation** and **duplicate request handling**.

### 8.3. maxTimeMS, Socket Timeout, and wtimeout

Time limits are not equivalent:

- **wtimeout:** wait time for the write concern condition.
- **maxTimeMS:** server execution time limit for operations supporting this parameter, with specific semantics.
- **Socket timeout:** I/O wait timeout between client and server.
- **Overall request deadline:** total budget for all API logic, including connection, processing, database, and response.

A socket timeout shorter than wtimeout can cause the client to give up before seeing the majority response. Align timeouts with business requirements and unknown-outcome handling.

## 9. Majority Commit Point and Read Concern

### 9.1. Read Concern "local"

With **readConcern: "local"**, MongoDB can return data that the serving node has applied, even if not yet majority-committed. Reading from the primary in the E201 example prior to failover can return E201; yet E201 can still roll back.

~~~text
Primary P:
  last applied: E201
  majority commit point: E200

Read concern local:
  can see E201 on P.

Read concern majority:
  does not return non-majority-committed data per this read level's rules.
~~~

**Warning:** readConcern local does not mean "data is definitely lost"; it means this read level **gives no guarantee that data is already majority-committed**.

### 9.2. Read Concern "majority"

**readConcern: "majority"** returns only data reflecting majority-committed state that the node can serve in the given context. It helps prevent applications from observing an uncommitted write that is later rolled back.

Command example:

~~~javascript
const lab = db.getSiblingDB("mongo_commit_lab");

const result = lab.runCommand({
  find: "lab_commit_events",
  filter: { dataset: "majority-commit-v1" },
  sort: { createdAt: 1, _id: 1 },
  batchSize: 20,
  readConcern: { level: "majority" }
});

printjson(result.cursor.firstBatch);
~~~

**readConcern majority does not automatically guarantee reading the absolute latest data as of right now.** A secondary can lag behind replication; a majority read can still observe older state than the primary.

### 9.3. Majority Read Does Not Automatically Provide Read-Your-Writes Across All Requests

Suppose:

1. Client writes a document with w:"majority" to the primary.
2. Client switches to reading from a routed secondary.
3. That secondary has not yet applied the newest document.

A readConcern majority on a secondary does not guarantee seeing the client's write immediately in all configs/read preferences. If the application needs **causal consistency/read-your-writes** across related calls, use a **causally consistent session** combined with corresponding write/read concerns per driver documentation.

When needing to check status immediately after a write, reading by **_id** from the primary within the same flow can be a pragmatic choice; yet workflow-wide consistency properties must still be explicitly designed rather than assuming "once inserted, every node sees it."

### 9.4. Read Concern "snapshot" and "linearizable"

**snapshot** provides a consistent snapshot read at an appropriate point, especially meaningful inside transactions. However, snapshot does not replace **majority write concern** when committing a transaction.

**linearizable** (within supported scope, especially single-document reads from the primary) has a different goal: guaranteeing stronger real-time ordering consistency, with related write concern and latency conditions. Do not swap read concern names interchangeably without establishing API requirements.

### 9.5. Comparison Table

| Mechanism | Problem It Solves | What It Does Not Guarantee on Its Own |
| --- | --- | --- |
| **w:"majority"** | Waits for write confirmation by majority | Every secondary immediately sees the data |
| **readConcern "majority"** | Avoids reading non-majority-committed data per read semantics | Reading the latest state on every secondary |
| **readConcern "local"** | Reads the node's current state | Data is protected from rollback |
| **readConcern "snapshot"** | Reads a consistent snapshot in supported contexts | Guarantees external write commit durability |
| **Causally consistent session** | Preserves causal ordering between session ops when configured properly | Automatically synchronizes external systems outside the session |
| **Transaction + majority write concern at commit** | Groups multi-op commit/abort and protects commit via majority | External side effects roll back automatically |

## 10. Elections, Quorum, and Member Counts

### 10.1. Three Data-Bearing Voting Members

A simple replica set:

~~~text
P (1 vote, data-bearing)
S1 (1 vote, data-bearing)
S2 (1 vote, data-bearing)

Voting majority: 2/3
~~~

If P is lost, S1 and S2 can still achieve voting majority to elect a new primary, subject to quorum and other election rules. A write previously on P+S1 can achieve majority; a write only on P has not.

### 10.2. An Arbiter Is Not a Data Copy

Another configuration:

~~~text
P  (PRIMARY, data-bearing, vote)
S  (SECONDARY, data-bearing, vote)
A  (ARBITER, vote, DOES NOT store data)
~~~

**An arbiter participates in elections but does not replicate user data/oplog like a data-bearing member.** Therefore, never think "P + Arbiter = two nodes storing the write, so majority write concern is met."

Specifically in a **Primary–Secondary–Arbiter (PSA)** topology, when the sole secondary is unavailable, the primary may still have enough votes with the arbiter for certain election purposes, yet **cannot rely on the arbiter to satisfy data replication requirements for majority write concern**.

Thus, comparing write concern and fault tolerance requires examining:

- Number of **voting members**.
- Number of **data-bearing members**.
- Priority/votes configuration, hidden/delayed members if any.
- Actual replication capacity and durability.

Do not merely divide **total `mongod` processes** by two to deduce required data copies.

### 10.3. When Quorum Is Lost

If a replica set loses the quorum needed to elect/maintain a primary, normal writes cannot be accepted or cannot be majority-acknowledged.

**This is a trade-off between data safety and availability.** MongoDB cannot simultaneously provide a consistent majority commit history and keep acknowledging arbitrary majority writes without enough required copies.

Applications must decide how to return errors, perform bounded retries, queue requests, or enter read-only/maintenance mode; **never automatically downgrade write concern to w:1** merely to "make dashboards green" if the data cannot tolerate rollback.

## 11. Common Pitfall: "Seen on a Secondary" Yet Still Unsafe

### 11.1. Do Not Confuse One Secondary with Majority

In a three-member replica set P/S1/S2, if a write appears on **P and S1**, that can be a majority. However, in a replica set with **five data-bearing voting members**, **P plus one secondary** is only **2/5**, not a majority.

Hence, claiming "once replicated to one secondary it will definitely never roll back" is false in general configurations.

### 11.2. A Secondary Can See a Record and Then Lose It During Resync

A secondary can apply an entry belonging to an invalid branch when an election changes history. Upon resyncing with the new primary, that non-majority-committed entry can be rolled back.

An application **reading data on a secondary with readConcern local** does not prove the entry passed the majority commit point. To ensure majority guarantees, combine **write concern, read concern**, and proper operational scope.

### 11.3. Replication Lag and Rollback Risk

Rising replication lag can lengthen the window where a new write exists only on the primary or lacks majority confirmation. Yet replication lag and majority commit point **are not the same metric**.

For instance, with P/S1/S2, S2 lags 30 seconds while S1 keeps up nearly instantaneously; P + S1 can still majority-commit quickly. Conversely, if both S1 and S2 fall behind, the commit point can stall.

Therefore, monitor lag alongside **lastCommittedOpTime**, node states, and available member count, not merely an average "secondary lag" number.

## 12. Safe `mongosh` Practice on a Private Replica Set

This lab section **does not induce failover**. Its purpose is inspecting replica set structure, comparing write concern syntax, and reading commit point metadata.

### 12.1. Environment Prerequisites

- A **practice MongoDB replica set** with properly configured data-bearing members; never use a production database.
- `mongosh` connection string targeting the **replica set**, not standalone.
- Account with read/write privileges on the lab database. Viewing **rs.status()** may require appropriate operational/monitoring privileges.
- Do not run **rs.stepDown()**, **rs.reconfig()**, stop `mongod`, block networking, or delete storage files.
- No need to trigger a real failover to learn rollback semantics; that was modeled via timelines.

Using a standalone `mongod` means majority replication/election experiments **do not represent** a replica set; do not try forcing errors using the wrong topology.

### 12.2. Confirm Connection to Primary

~~~javascript
(() => {
  const info = db.hello();

  printjson({
    replicaSetName: info.setName,
    isWritablePrimary: info.isWritablePrimary,
    primary: info.primary,
    hosts: info.hosts
  });

  if (!info.setName) {
    throw new Error(
      "Current connection is not a replica set. Please use a lab replica set."
    );
  }

  if (!info.isWritablePrimary) {
    print(
      "Current node is not primary; reconnect via a replica set URI."
    );
  }
})();
~~~

**setName** identifies the replica set. **isWritablePrimary** indicates whether the current node holds the writable primary role in the context of the hello command. With `mongosh` using a replica set URI, the driver selects the primary for writes automatically; no system config edits are needed to create a new primary.

### 12.3. Create a Scoped Test Dataset

Run on the primary of the lab replica set:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");
  const coll = lab.getCollection("lab_commit_events");
  const tag = "majority-commit-v1";

  // Delete only lab documents, with appropriate write concern.
  const cleanup = coll.deleteMany(
    { dataset: tag },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 10000
      }
    }
  );

  printjson({ cleaned: cleanup.deletedCount });

  const seed = coll.insertMany(
    [
      {
        _id: "commit-seed-001",
        dataset: tag,
        kind: "seed",
        createdAt: ISODate("2026-01-01T00:00:00.000Z")
      },
      {
        _id: "commit-seed-002",
        dataset: tag,
        kind: "seed",
        createdAt: ISODate("2026-01-02T00:00:00.000Z")
      }
    ],
    {
      writeConcern: {
        w: "majority",
        wtimeout: 10000
      }
    }
  );

  printjson({
    acknowledged: seed.acknowledged,
    insertedCount: seed.insertedCount,
    count: coll.countDocuments({ dataset: tag })
  });
})();
~~~

**Expected result when the replica set is healthy with majority:** two seed documents are inserted. If `writeConcern` times out, **do not proceed assuming the seed committed**. Inspect the error and verify state before retrying.

Using fixed `_id` values and `dataset` ensures examples never touch unrelated data. **Note:** `deleteMany` and `insertMany` are separate commands; the block is not a transaction and is unsafe to run concurrently with another writer sharing the same dataset tag.

## 13. Inspecting `lastCommittedOpTime` and Node States

### 13.1. `rs.status()`

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  optimes: status.optimes
});
~~~

Commonly inspected fields inside **optimes** include:

- **lastCommittedOpTime**: majority-committed replication point reported by the node.
- **appliedOpTime**: operation point applied by the node.
- **durableOpTime**: operation point tied to durable storage state.

Depending on version, output also includes **WallTime** timestamps or read concern fields. Do not assume every server returns the exact same structure/full set of fields. When `rs.status` lacks privileges, use proper monitoring tools rather than escalating permissions casually.

### 13.2. Listing Members and Freshness

~~~javascript
const status = rs.status();

printjson(
  status.members.map(member => ({
    name: member.name,
    state: member.stateStr,
    health: member.health,
    optime: member.optime,
    optimeDate: member.optimeDate,
    syncSourceHost: member.syncSourceHost
  }))
);
~~~

Meaning:

- **PRIMARY/SECONDARY/ARBITER**: current role.
- **health**: availability indicator as observed by the queried node.
- **optime/optimeDate**: replication progress of each member per reported fields.
- **syncSourceHost**: sync source used by the secondary where applicable.

Values are **point-in-time snapshots at invocation** and can change immediately afterward. A node reporting SECONDARY and caught up at one instant is not guaranteed to stay caught up forever.

### 13.3. Comparing Before and After a Majority Write

To observe:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");
  const coll = lab.getCollection("lab_commit_events");

  print("Optimes before write:");
  printjson(rs.status().optimes);

  const result = coll.insertOne(
    {
      _id: "commit-majority-001",
      dataset: "majority-commit-v1",
      kind: "ack-majority",
      createdAt: ISODate("2026-01-03T00:00:00.000Z")
    },
    {
      writeConcern: {
        w: "majority",
        j: true,
        wtimeout: 10000
      }
    }
  );

  printjson(result);
  print("Optimes after write:");
  printjson(rs.status().optimes);
})();
~~~

**Expected result with majority:** insert is acknowledged; oplog markers may advance. However, other admin/write entries may interleave, and `rs.status` updates do not promise seeing exactly a single timestamp increment per call. Do not treat the difference between these values as an exact write latency measurement.

**Re-running the example with the same `_id`** will raise a duplicate key error if the document still exists. This helps detect prior runs rather than auto-cleaning data after tests.

### 13.4. Comparing Syntax with `w:1`

~~~javascript
(() => {
  const coll = db.getSiblingDB("mongo_commit_lab")
    .getCollection("lab_commit_events");

  const result = coll.insertOne(
    {
      _id: "commit-w1-001",
      dataset: "majority-commit-v1",
      kind: "ack-primary-only",
      createdAt: ISODate("2026-01-04T00:00:00.000Z")
    },
    {
      writeConcern: { w: 1 }
    }
  );

  printjson(result);
})();
~~~

If the write is acknowledged, the document typically exists when read back immediately on the primary. **That does not prove the document is not yet majority-committed**, because replication can happen very fast. Likewise, it **does not prove the document was protected from rollback** at response time. The difference lies in **acknowledgment semantics**, not necessarily seeing two different data states on a healthy lab.

### 13.5. Reading with `readConcern` Majority

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");

  const result = lab.runCommand({
    find: "lab_commit_events",
    filter: {
      dataset: "majority-commit-v1"
    },
    sort: { createdAt: 1, _id: 1 },
    limit: 20,
    singleBatch: true,
    readConcern: { level: "majority" }
  });

  if (result.ok !== 1) {
    throw new Error(
      "find majority command failed: " + tojson(result)
    );
  }

  printjson(result.cursor.firstBatch);
})();
~~~

Once the replica set has majority-committed all writes in the exercise, you will see them in the output. A majority read returning data does not prove they were originally written with w:majority: **a w:1 write can become majority-committed once replication finishes**.

## 14. One Experiment Not to Do: Inducing Rollback on a Shared Machine

To observe an actual rollback, an operator must create diverging oplogs across a failover prior to majority commit. This can require network isolation, altering process state or topology, and risks disrupting multiple clients.

**This lesson neither requires nor instructs inducing that failure on an environment serving others.** Instead, use the E201/E301 timelines in sections 4–5 to determine:

1. On how many data-bearing voting members does the entry appear?
2. Has the entry passed the majority commit point?
3. Under which write concern did the client receive acknowledgment?
4. Which history will a valid new primary choose?
5. Which data risks rollback when the old node resyncs?

If an organization genuinely needs chaos/failover drills, run them on an **isolated cluster with snapshots/backups, formal approval, and accountable operators**, measuring expected states rather than firing ad-hoc failover commands in production.

## 15. Majority and Transactions: Atomic Commit Does Not Automatically Equal Rollback Protection

### 15.1. A Multi-Document Transaction

Suppose transferring 100 units between wallets A and B while recording an audit entry:

~~~text
Inside transaction:
  A.balance -= 100
  B.balance += 100
  INSERT transferAudit
COMMIT
~~~

Transactions ensure changes within MongoDB commit/abort together under transactional semantics. Yet **write concern at commit time** still matters for determining whether the new commit history risks rollback during failover.

When a transaction commit is successfully majority-acknowledged, the commit outcome has stronger protection against normal failover than relying on a weaker acknowledgment level.

### 15.2. Node.js Driver Example: Majority at Commit

Implementation illustration (run only on a lab replica set supporting transactions):

~~~javascript
import { MongoClient } from "mongodb";

async function transferInTransaction(uri) {
  const client = new MongoClient(uri);
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_commit_lab");
  const wallets = lab.collection("lab_wallets");
  const audit = lab.collection("lab_transfer_audit");

  try {
    await session.withTransaction(async () => {
      const debit = await wallets.updateOne(
        {
          _id: "wallet-a",
          dataset: "majority-commit-v1",
          balance: { $gte: 100 }
        },
        { $inc: { balance: -100 } },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("Insufficient balance");
      }

      const credit = await wallets.updateOne(
        {
          _id: "wallet-b",
          dataset: "majority-commit-v1"
        },
        { $inc: { balance: 100 } },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("Target wallet does not exist");
      }

      await audit.insertOne(
        {
          _id: "transfer-001",
          dataset: "majority-commit-v1",
          amount: 100
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Illustration only: create the two lab wallets separately before calling.
// await transferInTransaction(process.env.MONGODB_URI);
~~~

This snippet is separate from section 12's seed, which only created **lab_commit_events**. You must create the two lab wallets yourself if running it; do not run it expecting pre-seeded wallets. It illustrates placing **writeConcern: {w:"majority"} in transaction options**, not a test expected to pass on an unprepared database.

### 15.3. Warning on Transaction Retries

Transaction helpers can retry callbacks or commits upon transient errors. **Never send emails, charge external payment gateways, or execute non-idempotent side effects directly inside a transaction callback.**

If commit returns **UnknownTransactionCommitResult**, do not assume the transaction aborted. Use the driver's commit retry mechanism and idempotency keys to identify already-processed business transactions.

When external systems exist outside MongoDB, apply outbox/event-driven workflows or suitable distributed protocols; majority write concern does not create transactions across email or payment gateways.

## 16. Retrying After Failover: A Request May Have Executed Before the Client Knows

### 16.1. "No Response Received" Is a Distinct State

For example, the client sends:

~~~javascript
db.wallets.updateOne(
  { _id: "wallet-a" },
  { $inc: { balance: -100 } }
);
~~~

The connection drops before the client receives a response. Possibilities:

- The server never received the command.
- The server received and applied it, yet the write was not majority-committed.
- The write was majority-committed, and the response was lost on the network.
- The primary stepped down; final state must be reconciled.

If the client submits a brand-new request with **$inc -100**, it could deduct an extra **100** on top of a previously succeeded write.

### 16.2. Retryable Writes Have Scope Limits

MongoDB drivers support **retryable writes** for eligible operations under suitable topologies/sessions. This helps handle certain network/failover errors by avoiding duplicate execution of **the same statement** inside a supported retryable session context.

However:

- Not every operation is retryable.
- Commands like **updateMany** and multi-command workflows do not share the same guarantee as a retryable `updateOne`.
- **A new HTTP request** representing a new business call does not automatically reuse the same session/statement identity.
- Retryable writes do not replace business-level idempotency design for payments, transfers, or order creation.

### 16.3. Idempotency Key Pattern

Rather than inspecting balances after errors, each critical business operation carries a unique **requestId/transferId**. The application can:

1. Accept a `requestId` generated per trusted contract by server/client.
2. Record the `requestId` and business effect inside the same transaction or invariant-protected data structure.
3. Enforce a **unique index** on the business key.
4. On duplicate requests, check committed status with appropriate read/write concern.
5. Return the corresponding result, **never re-executing side effects** if the request already completed.

For deletions or payments, audit/outbox records and post-failover reconciliation may be required. Never treat "found a duplicate `_id` document" as proof the prior payload matched identically without comparing.

### 16.4. Look at Both Errors and Commit Outcomes

| Symptom | Handling Direction |
| --- | --- |
| NotPrimary/PrimarySteppedDown | Driver can pick the new primary and retry eligible operations |
| NetworkError after write | Treat outcome as uncertain; rely on retryable writes/idempotency |
| WriteConcernError or wtimeout | Do not conclude the write did not occur; reconcile majority-committed state |
| DuplicateKey after retry | Inspect idempotency key and payload; prior request may have created the record |
| UnknownTransactionCommitResult | Follow driver commit retry/reconciliation procedure |
| Inspecting data on a lagging secondary | Check read preference/read concern; do not rush to conclude the write rolled back |

## 17. Real-World Applications: Orders, Inventory, and Events

### 17.1. Customer-Confirmed Orders

Suppose an API returns "Order created" and sends a confirmation email. If inserting the Order was only acknowledged with **w:1**, and the Order later rolls back during failover, the customer may have a confirmation email while the database holds no order.

For critical data:

- Consider **w:"majority"** or equivalent durability policy per requirements.
- Write **Order and OutboxEvent** inside a transaction if multiple documents must commit atomically.
- Emit notifications only after outcomes are confirmed per system contract.
- Use **requestId** to avoid creating two orders when clients retry after timeouts.
- Maintain reconciliation procedures if external downstream steps fail.

**Majority reduces rollback risk**, yet delivering emails exactly once remains a separate application design problem.

### 17.2. Inventory

An inventory document can be updated atomically using filter **available >= quantity** and **$inc**. Yet if the stock write was acknowledged only at w:1 and later rolls back, the application may have reported "stock reserved" while the reservation vanished.

For critical stock reservations, combine **conditional updates, sufficiently strong write concern, business idempotency, and reservation reconciliation**.

Do not use majority as a substitute for inventory conditions: a majority-committed command can still write negative quantities if the filter permits it.

### 17.3. Reproducible Logs and Telemetry

Not every event requires the same durability as payments. For non-critical telemetry, majority write overhead may be unwarranted. Policy may accept losing a few events during failover, given:

- Defined acceptable data loss bounds.
- Sources capable of replaying or regenerating events.
- Metrics alerting on drops/overload.
- Never using that data as the sole source for financial audits.

Choose write concern by **data semantics**, avoiding blanket slogans like "majority everywhere" or "w:1 everywhere" that ignore domain needs.

## 18. Observing Replication and Recognizing Risks

### 18.1. Metrics to Monitor

| Metric / Observation | Meaning |
| --- | --- |
| **lastCommittedOpTime** | Majority commit point reported by the node |
| **appliedOpTime / durableOpTime** | Applied and durable milestones on the node |
| **Replication lag** | How far behind the replication source a secondary trails per measurement |
| **Member states** | PRIMARY/SECONDARY/ARBITER, health, sync source |
| **Election count and stepdown events** | Frequency of primary switches/failovers |
| **w:majority latency** | Wait time for acknowledgments affecting applications |
| **Write concern timeouts/errors** | Whether requested ack levels are struggling to succeed |
| **Rollback events/logs** | Evidence of diverging history and rolled-back operations |
| **Connections/retry rate** | Whether failover triggered a client retry storm |
| **Replication oplog window** | Whether a severely lagging secondary can still sync via oplog |

Monitor the **gap between applied and majority-committed points**, yet do not infer exact elapsed wall-clock time from two logical values without corresponding timestamp data.

### 18.2. `rs.printSecondaryReplicationInfo()`

In supported `mongosh` versions, you can run:

~~~javascript
rs.printSecondaryReplicationInfo();
~~~

This command shows secondary replication progress and estimated lag. It is an observational aid, not a direct measure of whether **a specific write has already been majority-committed**.

### 18.3. Observed Commit Point Shifts with Query Timing

Between two calls to:

~~~javascript
printjson(rs.status().optimes);
~~~

nodes can keep applying oplog entries, secondaries can catch up, elections can occur, and the commit point can advance. Therefore, conclusions about a specific failure must correlate **write timestamp**, **write concern**, **returned outcome**, and **server logs**, not just an `rs.status` snapshot taken minutes later.

### 18.4. Never "Fix" Incidents by Quietly Lowering Write Concern

If `w:"majority"` frequently times out:

1. Verify data-bearing voting member count and actual quorum.
2. Inspect secondary health, replication lag, and storage/network errors.
3. Measure resource pressure, journaling, and system limits.
4. Check workload characteristics: write volume, document size, index update cost.
5. Tune timeouts/budgets only with knowledge of normal latency.
6. Plan replica set recovery if a member cannot catch up.

Switching all operations to **w:1** just to eliminate timeout errors increases the **risk of losing acknowledged data**, especially for non-reproducible business workflows.

## 19. Limits and Cases Requiring Careful Reasoning

### 19.1. Majority Commit Point Does Not Mean All Writes on Primary Are Safe

The primary may hold oplog entries **newer** than the commit point. Reading a document on the primary does not by itself reveal which entries for that document have passed the majority commit point without examining read concern and operation history.

### 19.2. Majority Acknowledgment Does Not Mean "Never Need Backups"

Replica sets reduce risk when some members fail and provide automatic failover. Backups protect against other scenarios: majority-committed accidental deletions, corruption, cluster-wide data loss, restoring to a historical point in time, and long-term retention requirements.

**An accidental `deleteMany` executed with `w:"majority"` will be replicated very durably—yet it is still an accidental deletion.** Majority does not validate business logic correctness.

### 19.3. Majority Reads Do Not Fix Application Write Bugs

If two clients concurrently update a balance by reading the old value and issuing `$set`, a lost update can become majority-committed. Majority write concern only states **the write was replicated and confirmed**, not that the application's computed value was right.

Mechanisms like **$inc**, conditional filters, versioning/optimistic concurrency, and properly scoped transactions remain essential.

### 19.4. Rollback Is Not Transaction Abort

**Transaction abort** occurs when a transaction has not committed per transaction semantics and is cancelled, applying none of its changes to committed state.

**Replica set rollback** occurs when a node's oplog diverges from the history chosen after failover and non-majority-committed writes are removed from that node's history.

These two mechanisms differ in root cause, scope, and how applications must respond.

### 19.5. Simultaneous Failures Across Multiple Members

Majority guarantees rely on properly maintained oplog history and sufficient data across eligible members. When multiple nodes suffer storage loss, backups fail, or the cluster is mis-reconfigured, incidents outside the normal failure model can still occur.

**Never state "majority writes can absolutely never be lost" as an unconditional technical claim.** State clearly: it protects majority-committed writes against rollback during valid replica set failovers given proper storage and deployment conditions.

### 19.6. Changing Replica Set Config Affects Majority Calculation

Voting member count, arbiters, votes/priorities, and durability settings affect quorum and acknowledgment calculations. Especially during config changes, never apply a fixed three-node mental model blindly to every cluster.

All configuration changes must be executed by authorized operators under dedicated procedures. This lesson **does not instruct reconfiguring a replica set** and does not require actions that risk losing quorum.

## 20. Common Misconceptions

| Misconception | Reality | Design Consequence |
| --- | --- | --- |
| `insertOne` returning acknowledged means definitely majority-committed | ACK depends on write concern | Verify `w` before promising data survives failover |
| `w:1` means the write will definitely roll back | Write can reach majority after ACK | Do not make absolute claims from `w` alone |
| `w:"majority"` means all three nodes received it | Majority does not require all | A slow secondary may still lack the write |
| Primary writing to journal suffices against rollback | Local journal differs from majority history | Consider both `j` and `w` |
| An arbiter is a data copy | Arbiters only participate in elections, holding no dataset | Never count an arbiter as a replicating secondary |
| Seeing data via `readConcern local` means it is safe | Local can see uncommitted writes | Use majority read when needing to avoid rollback-prone data |
| Majority read is always the freshest | Secondaries can lag and majority reads can be stale | Use causal sessions/primary reads per requirements |
| `wtimeout` means not written | Write may have applied without full ACK | Never retry blindly |
| Network timeout means server never executed it | Response may drop after writing | Use retryable writes/idempotency |
| Having majority means no backups needed | Majority cannot rescue accidental deletes or cluster loss | Maintain appropriate PITR/backups |
| Atomic transaction automatically prevents rollback | Commit still has its own write concern | Specify majority at commit when needed |
| Rollback = transaction abort | One is diverging oplog, the other an uncommitted transaction | Handle distinct failure modes separately |
| One secondary lagging 30s means every write commits 30s late | Primary + another secondary can satisfy majority | Check commit point and topology |
| Downgrading to w:1 on majority timeout leaves risk unchanged | Rollback protection drops | Fix replication/quorum instead of silently lowering safety |
| Majority guarantees business invariants hold | Replication does not validate logic | Filters/transactions/validations are still required |
| Snapshot restore can ignore majority | Restoring wrong point in time can lose data | Recovery procedures must be controlled |

## 21. Reasoning and Hands-On Exercises

### Exercise 1 — Distinguish Acknowledged and Committed

With P/S1/S2:

~~~text
P : E100 E101 E102
S1: E100 E101
S2: E100
~~~

Assume entries satisfy storage requirements. Which entry can the majority commit point be at? Is E102 acknowledged with w:1 guaranteed safe against failover? If S1 catches up to E102, how does the answer change?

### Exercise 2 — Rolled-Back Write

Draw a timeline: P writes E201 with w:1, S1/S2 do not yet have E201, P becomes isolated, S1/S2 elect a new primary. Explain why E201 may be rolled back when P returns. Give an example consequence for a newly inserted Order.

### Exercise 3 — Majority-Committed Write

Suppose P and S1 have E301, client receives w:"majority" ACK, and S2 has not caught up yet. When P fails, what preserves E301 in the replica set's valid history? Why does S2 lacking E301 not mean the majority write failed?

### Exercise 4 — Difference Between `w:1` and `j:true`

Compare **w:1, j:true** with **w:"majority"** regarding rollback protection and local durability. Why is the primary's journal insufficient to protect a non-majority-committed entry when an election chooses another history?

### Exercise 5 — Timeout and Unknown Outcome

An insert with w:"majority" and 5-second wtimeout returns a WriteConcernError. List at least three possible states afterward. Propose how to reconcile using an idempotency key and suitable read concern instead of re-sending insert with a new `_id`.

### Exercise 6 — Reading on a Secondary

A client writes a document with w:"majority" and immediately reads from S2 using readConcern majority without seeing the document. Does this necessarily prove the write rolled back? Explain replication lag, read preference, and mechanisms required when read-your-writes is needed.

### Exercise 7 — Arbiter and Write Concern

A replica set has P, S, and an Arbiter. When S is down, P and the Arbiter can still reach a voting majority in some cases. Why does that not mean writes on P were replicated to a majority of data-bearing members?

### Exercise 8 — Describe `rs.status`

On a lab replica set, inspect members and optimes using **rs.status()**. Record `lastCommittedOpTime`, `appliedOpTime`, and `durableOpTime` if present. What question does each field answer, and why can you not deduce the exact full history of a specific request from one status snapshot?

### Exercise 9 — Compare Write Concern Results

Run the **commit-majority-001** and **commit-w1-001** examples on a lab without inducing failover. Both documents may subsequently be visible under `readConcern majority`. Explain why that outcome **does not prove w:1 is equivalent to majority**.

### Exercise 10 — Design Data Policies

Classify three data types: re-sendable telemetry events, customer-confirmed Orders, and Payment/Audit records. Specify write concern, read concern, idempotency, backup, and acceptable latency for each, along with reasons for the differences.

### Exercise 11 — Retry and Double-Charge

A **$inc -100** on a wallet may have majority-committed while the response dropped. If the client sends a new HTTP request, what risk occurs? Propose a unique `transferId` and a transaction updating the wallet + audit record to detect duplicate requests.

### Exercise 12 — Majority in Transactions

A transaction updating two documents and writing an audit entry commits with a write concern weaker than product durability requirements. Even though the transaction guarantees all-or-nothing atomicity at commit scope, what can happen if the commit is not majority-committed before failover? Show how to configure write concern at commit.

### Exercise 13 — Difference Between Election and Rollback

Explain why not **every election** causes a rollback. What condition creates a diverging history branch? How does a majority-committed entry differ from an entry applied only on the primary?

### Exercise 14 — Analyze Replication Lag

Replica set P/S1/S2: S1 keeps up with the primary nearly immediately, while S2 lags 20 seconds. Must a majority write wait for S2? If S1 subsequently disconnects too, what changes regarding `w:"majority"` acknowledgment capability?

### Exercise 15 — Restoring the Wrong Snapshot

An administrator restores the entire cluster from a day-old backup. Do yesterday's majority-committed entries automatically reappear? Distinguish replication guarantees from backup procedures, point-in-time restore, and external history retention.

### Exercise 16 — Upgrade API Policy

An API currently uses w:1 for order placement, returns success, and immediately sends an email. Propose an upgrade plan covering:

1. Writing the Order with appropriate durability guarantees.
2. Writing an outbox event in the same transaction if needed.
3. Designing `requestId`/idempotency.
4. Handling `wtimeout` and unknown outcomes.
5. Monitoring majority latency, error rates, and replication health.

State conditions under which the API should reject/defer writes rather than downgrading write concern automatically.

## 22. Official Reference Documentation

- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Replication](https://www.mongodb.com/docs/manual/replication/).
- MongoDB Manual — [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/).
- MongoDB Manual — [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/).
- MongoDB Manual — [db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/).
- MongoDB Manual — [replSetGetStatus / rs.status()](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).

**Takeaways to remember:** The **majority commit point** marks the portion of oplog history confirmed by a majority of eligible members. A write **acknowledged with w:1** that **has not yet passed the commit point** can still **roll back** if the primary loses its role before secondaries replicate sufficiently and another history is elected valid. A write **successfully acknowledged with w:"majority"** is protected against rollback caused by **normal replica set failover**, given proper replication and durability settings. Even so, **majority does not replace backups, idempotency, conditional updates, or transactions**. When handling network errors and `wtimeout`, accept the possibility of **not immediately knowing the final outcome**, reconcile by business identifier, and never blindly retry operations with side effects.
