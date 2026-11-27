# Write concern: `w`, `j`, `wtimeout` and write acknowledgment levels in MongoDB

When an application calls `insertOne()`, `updateOne()`, or `deleteOne()`, what is guaranteed at the moment MongoDB replies "success"? Has the data been received by the primary? Has a secondary replicated it? Has it been written to the on-disk journal? Or was it just sent over the connection without the client waiting for a response?

In MongoDB, the answer depends significantly on the **write concern**. This configuration specifies **the level of acknowledgment requested by the application before considering a write operation acknowledged**. A write concern is typically expressed as:

```javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
```

The three components have distinct meanings:

- **`w`**: requests acknowledgment from a specified number of replica set members that have propagated the data, or a majority using `"majority"`.
- **`j`**: whether to request acknowledgment that the write has been written to the **on-disk journal**, in configurations/storage engines that support journaling.
- **`wtimeout`**: limits the **time to wait for the write concern to be satisfied**, in milliseconds.

Write concern belongs to the topic of **Read and Write Consistency**. It relates to data durability and the meaning of write responses, but **is not the same as read concern, read preference, transactions, or primary election quorum**. This lesson progresses from replica set architecture to failure scenarios, followed by hands-on practice in `mongosh` and the MongoDB Java Sync Driver.

## 1. Stages of a write operation

Suppose a replica set has one primary P and two secondaries S1 and S2. An application sends a document insert command:

```text
                  APPLICATION
                     |
                     | insertOne(document)
                     v
                  PRIMARY P
                     |
           Applies change on P
                     |
          +----------+----------+
          |                     |
          v                     v
     Secondary S1          Secondary S2
     replicates oplog      replicates oplog
          |                     |
          v                     v
     Applies entry         Applies entry

          ----> Primary decides when to
                send acknowledgment based on write concern
```

A write operation can go through non-simultaneous stages:

1. The client sends the request to a server identified as a writable primary.
2. The primary validates the command, applies the change, and records the change for replication.
3. The secondaries replicate and apply the corresponding changes.
4. Depending on journaling and the write concern, the involved members may need to write the change to the journal.
5. Once the acknowledgment conditions are met, the server responds to the client; if they are not met within the wait timeout, the result may contain a **write concern error/timeout**.

**Key point:** "The primary has applied the write", "enough replicas have acknowledged", and "the journal has been durably written" are three distinct concepts. Write concern lets the application choose **when to receive an acknowledgment response strong enough for its needs**.

### Write responses do not make all work instantaneous

Even when using `w: "majority"`, there may still be a secondary that is lagging or has not yet received the update. `majority` does not mean **every** node in the replica set has finished syncing. Conversely, an operation acknowledged by the primary with `w: 1` does not guarantee that secondaries already have a copy.

## 2. Write concern syntax

In `mongosh`, you can specify a write concern per operation:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1001",
    customerId: "C001",
    total: 250,
    status: "pending"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
```

In the example above, `wtimeout: 5000` means **5,000 milliseconds**, not 5 seconds written directly in the syntax. Depending on the environment, the command will succeed when the write concern condition is met or return an error when the requested acknowledgment level is not achieved.

| Parameter | Common values | Meaning |
| --- | --- | --- |
| `w` | `0`, `1`, `2`, `3`, `"majority"` | Number of members required to acknowledge, or majority per configuration |
| `j` | `true`, `false` | Whether to request journal acknowledgment |
| `wtimeout` | `0`, positive integer in milliseconds | Time limit to wait for write concern satisfaction |

It is not necessary to specify all three fields in every command. When an option is omitted, behavior relies on the **effective default write concern** and the corresponding server/driver rules. Because defaults can vary by topology and configuration, you should not infer the durability level solely from the absence of `writeConcern` in code.

### Syntax in a database command

A write operation can be expressed using the `insert` command directly:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "ord-1002",
      customerId: "C002",
      total: 100,
      status: "pending"
    }
  ],
  writeConcern: {
    w: 2,
    j: true,
    wtimeout: 3000
  }
})
```

In this command, `writeConcern` is part of the `insert` command, not a field of the inserted document. This is the difference between **write operation configuration** and **business data**.

## 3. `w: 0` — writing without waiting for server acknowledgment

`w: 0` is the **unacknowledged write concern** level. The application does not require the server to return a write result acknowledgment under the standard write concern mechanism:

```javascript
db.events.insertOne(
  { _id: "evt-01", kind: "page-view" },
  { writeConcern: { w: 0 } }
)
```

With `w: 0`, you should not infer from the absence of a client-side call error that the server has definitely saved the document. Data constraint errors, duplicate keys, or server-side errors may not be reported in the way acknowledged writes provide.

**Does not mean zero client-side errors.** An error constructing the command, closing the connection, or sending data can still occur depending on the driver and timing. What `w: 0` eliminates is the requirement to **wait for a write acknowledgment from the server**.

### When should `w: 0` not be used?

For orders, payments, balance adjustments, access permission records, or auditable events, `w: 0` is generally inappropriate. The application needs to know whether the operation was received and acknowledged by the server at the desired durability level.

Even for telemetry where losing some events is acceptable, you still need to evaluate whether the client/driver, batch processing, and retry mechanisms support that mode of operation. You should not assume `w: 0` always makes the overall system faster or is safe as a replacement for an event queue.

### `w: 0` and `j: true` is not a sensible combination

`j: true` requires waiting for journal acknowledgment, whereas `w: 0` does not wait for acknowledgment. Because the two settings have conflicting goals, do not use this combination; versions/drivers may reject the invalid configuration. If the application needs to know that data was written to the journal, it must choose an acknowledged `w` level.

## 4. `w: 1` — primary acknowledges the operation

`w: 1` requests acknowledgment from the **primary** that it has accepted and applied the write operation according to server rules:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1101",
    status: "pending",
    total: 75
  },
  { writeConcern: { w: 1 } }
)
```

With a P–S–S replica set:

```text
Client ---> P applies write ---> ACK to client
               |
               +----> S1 may not have finished replicating
               |
               +----> S2 may not have finished replicating
```

When the application receives a `w: 1` acknowledgment, the operation has been acknowledged by the primary, **without waiting for secondaries**. However, if the primary fails before the change is replicated to the necessary members and a new primary is elected, uncommitted changes that have not been majority-committed may be **rolled back**.

### Is `w: 1` always durable on disk?

You should not make that claim without considering `j` and the journaling configuration. With `w: 1`, requesting confirmation that the data has been applied on the primary does not automatically equal requesting **written to the on-disk journal**.

If you need journal confirmation on the primary without waiting for secondaries yet, you can use `w: 1, j: true`; however, that level **still provides no majority replication guarantee**. Durability against a process crash/node restart and survival across a **failover to another primary** are two different issues.

## 5. `w: 2`, `w: 3`, and numeric values

When `w` is a positive integer `n`, MongoDB requires the write operation to be acknowledged by **`n` eligible data-bearing members**, including the primary, before returning that the write concern is satisfied.

For example, a replica set with P, S1, and S2:

```javascript
db.orders.updateOne(
  { _id: "ord-1101" },
  { $set: { status: "paid" } },
  { writeConcern: { w: 2, wtimeout: 5000 } }
)
```

The `w: 2` level typically requires the primary and **at least one secondary** to have received/applied the corresponding change. Both S1 and S2 do not need to finish.

```text
P + S1 + S2 (three data-bearing members)

w: 1  -> P
w: 2  -> P + at least one secondary
w: 3  -> P + S1 + S2
```

A few things to keep in mind:

- **`w: 2` does not always equal a majority.** In a replica set with five voters, the election majority is three votes, not two.
- **`w: 3` does not always mean writing to the entire replica set.** If there are five data-bearing members, two members may still be incomplete.
- **`w: n` does not pin specific secondaries** by hostname. MongoDB handles acknowledgment based on the availability and state of eligible members.
- **An arbiter is not a data-bearing member** and therefore cannot be counted as a node storing data to satisfy `w: 2` or `w: 3`.

### When `w` exceeds actual replication capacity

If a replica set has only two data-bearing members and the application requests `w: 3`, this write concern cannot be satisfied in the current topology. Depending on state and version, the operation may be rejected or wait and report a write concern error/timeout. Do not let such requests wait indefinitely; configure values suited to the topology and set a wait timeout when needed.

Do not use `w: 3` simply because "three is a larger number so it feels safer." The appropriate level must match the **member count and failure model** of the replica set.

## 6. `w: "majority"` — acknowledgment by the eligible majority

`w: "majority"` requires the write operation to be acknowledged by the **write majority** of the replica set. This is the level commonly used when an application wants to reduce the risk of losing acknowledged writes during a failover.

```javascript
db.orders.insertOne(
  {
    _id: "ord-1201",
    status: "paid",
    total: 300
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

In a replica set of three **data-bearing voting members** P–S1–S2, the typical majority requirement is achieved when the change has been acknowledged on **two out of three** eligible members. One slow secondary does not necessarily block `majority` operations, as long as enough remaining members respond.

```text
P -- S1 -- S2

Voters = 3, election majority = 2
Data-bearing voting members = 3

w: "majority" -> requires majority acknowledgment
                 typically corresponding to 2 data-bearing members
```

### Why does majority help protect during failover?

Majority sets always overlap. Once a write has achieved an appropriate majority commit and a new primary is elected according to the replica set protocol, the majority-committed history is preserved by the replication/election rules. This is stronger than an operation acknowledged only by the old primary with `w: 1`.

Nevertheless, distinguish between:

- **Applied by the primary:** the entry exists on the current primary.
- **Majority acknowledged/committed:** the state required by `w: "majority"` has been reached.
- **Journaled:** depends on `j` and journal configuration; majority replication is not a synonym for journaling in all modes.
- **Synced to all members:** a requirement stronger than majority and usually unnecessary for every operation.

Do not promise "majority guarantees data can never be lost in any disaster": simultaneous hardware failures, operational mistakes, loss of all failure domains, or improper recovery procedures remain risks requiring separate backups and system design.

## 7. How do election quorum and write majority differ?

In a replica set, the word "majority" can refer to **primary election** or **write acknowledgment**.

**Election quorum** answers: are there enough votes from voting members to maintain/elect a primary? If `V` is the number of voting members in the effective election configuration:

```text
electionMajority = floor(V / 2) + 1
```

**Write majority** answers: have the required number of **data-bearing voting members** acknowledged the write under the majority mechanism? An arbiter can help elect a primary but **holds no data to acknowledge writes**.

### Comparing topologies

| Topology | Voting members | Election quorum | Data-bearing members | Typical majority write requirement |
| --- | ---: | ---: | ---: | --- |
| P–S–S | 3 | 2 | 3 | Two data-bearing voting members |
| P–S–A (A = arbiter) | 3 | 2 | 2 | Two data-bearing voting members |
| P and one S, both voting | 2 | 2 | 2 | Both required |
| Three data voters and two non-voting secondaries | 3 | 2 | 5 | Majority is calculated from voting members, not simply 5 data nodes |

For configurations with arbiters, MongoDB's calculation of **write majority count** follows specific rules; inspect server information such as `writeMajorityCount` when provided, rather than guessing from the count of online processes or counting every secondary.

### P–S–A scenario when S is lost

```text
          P (primary, data)
          |
          A (arbiter, voting)

          S (secondary, data): disconnected
```

- **Electing/maintaining primary:** P + A have 2/3 votes, meeting the election quorum.
- **`w: 1`:** primary P can acknowledge if the command is processed successfully.
- **`w: "majority"`:** the arbiter stores no data; P alone does not provide enough data copies, so the command may wait or report a write concern timeout.

This is why a P–S–A topology is not fully equivalent to P–S–S in write durability. When majority durable writes are required, evaluate the number of reachable **data-bearing** members, not just vote counts.

## 8. `j: true` — on-disk journal write acknowledgment

MongoDB uses a **write-ahead journal** with supporting storage engines to enable recovery after certain types of process/machine crashes. Changes may be applied in memory and subsequently written to the journal according to the storage engine mechanism.

`j: true` is a request that acknowledgment must satisfy the journal condition before being considered complete:

```javascript
db.orders.insertOne(
  {
    _id: "ord-1301",
    status: "pending",
    total: 400
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
)
```

In the `w: 1, j: true` example, the application requests write acknowledgment on the primary **plus the journal condition**, without requiring a secondary to finish replicating.

### `j` does not replace `w`

| Configuration | What is requested | What is not guaranteed by this configuration alone |
| --- | --- | --- |
| `{w:1}` | Primary acknowledgment | Secondary replication, or journal if not requested |
| `{w:1,j:true}` | Primary acknowledgment with journal requirement | Enough majority replicas to prevent write loss on failover |
| `{w:2,j:false}` | Acknowledgment from two data-bearing members, no explicit journal request | Journal durability on the members |
| `{w:"majority",j:true}` | Majority write acknowledgment and journal per deployment semantics | That all secondaries are updated, or all infrastructure risks are eliminated |

A change that is **journaled on the primary** may still not be majority-replicated. If the primary fails and the new primary selects a different oplog history, writes that were not majority-committed can be rolled back by the replication mechanism. Thus, `j: true` and `w: "majority"` protect against **different classes of risk**.

### What does `j: false` mean?

`j: false` means the operation **does not request the journal condition** in its acknowledgment. It **does not disable journaling across all of MongoDB** and does not assert that the journal will not be written; the storage engine can still journal on its own schedule.

If `j` is omitted, actual behavior can depend on the write concern, `writeConcernMajorityJournalDefault`, and other server/version settings. You should not assume an omitted `j` always equals `j: false` in every situation.

### Majority and default journal configuration

On a replica set using a journaling storage engine, `writeConcernMajorityJournalDefault` affects whether `w: "majority"` waits for journal writes before acknowledging. Configuration values and related rules should be verified against the actual server.

When an application has clear durability requirements, **explicitly specify the write concern/journal level according to the architecture** and verify the version, rather than generically claiming "majority means it's on disk" without checking configuration.

### Limitations of the journal requirement

- Journal durability reduces data loss risk when a process or machine crashes under supported recovery mechanisms.
- It is not equivalent to periodic backups, replication to an independent site, or protection against all disk failures.
- Explicitly enabling journaling on write concerns can increase acknowledgment latency.
- Specific behavior depends on the storage engine, version, and how MongoDB writes/flushes the journal.

## 9. `wtimeout` — how long to wait at most for acknowledgment?

`wtimeout` sets a time limit for **waiting to satisfy the write concern**, measured in **milliseconds**:

```javascript
db.orders.updateOne(
  { _id: "ord-1301" },
  { $set: { status: "paid" } },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 4000
    }
  }
)
```

In this example, if MongoDB cannot satisfy the majority/journal acknowledgment conditions within the wait window, the application may receive a **write concern timeout/error**. This **does not mean MongoDB automatically rolls back the operation already applied on the primary**.

### A timeout does not mean the operation was not written

```text
Time 0 ms:
  Client sends update
         |
         v
  Primary applies update
         |
         v
  Secondaries do not acknowledge in time
         |
         v
  wtimeout expires
         |
         v
  Client receives write concern error/timeout

Actual state:
  The update may exist on the primary.
  Some secondaries may have received it.
  A secondary may receive it after the timeout.
```

A write concern error reflects that **the requested acknowledgment level was not satisfied under observed conditions**, not simply that "the update never happened." Therefore, blind retries can cause **duplicate effects**.

### Example of retry bugs with `$inc`

```javascript
db.wallets.updateOne(
  { _id: "wallet-01" },
  { $inc: { balance: 100 } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 2000
    }
  }
)
```

If the client receives a timeout and then issues **a new `$inc` operation** without a deduplication mechanism, `balance` can increase **twice** if the first operation was already applied. This is a business logic risk, regardless of whether the second request has identical content to the first.

For non-idempotent writes, design with **unique operation IDs, conditional updates, compatible retryable writes, or proper business transactions/ledgers**. Driver retryable writes have their own rules regarding sessions, retries, and eligibility; **do not assume** that any manual re-invocation is automatically safe.

### `wtimeout: 0`

`wtimeout: 0` typically signifies **no specific write concern timeout limit**. This does not guarantee a request will wait indefinitely in all circumstances: connections, server selection, command deadlines, or other limits can still interrupt the operation.

In production, set timeouts deliberately based on latency requirements, failover tolerance, and strategies for handling unknown write outcomes; do not pick an overly low number just to make an API respond faster.

## 10. Distinguishing `wtimeout`, connection timeout, and server selection timeout

A write request can encounter multiple types of timeouts at different layers:

| Timeout type | Where does it happen? | Approximate meaning |
| --- | --- | --- |
| `wtimeout` | MongoDB waiting to satisfy write concern | The write command may have been applied, but enough acknowledgments were not received |
| Server selection timeout | Driver locating an eligible server, e.g., writable primary | May have failed to select a primary to send the command to |
| Connect timeout | Establishing network connection | Failed to establish a connection within the deadline |
| Socket/read timeout | Waiting for response data on the connection | Execution state on the server may be unknown |
| `maxTimeMS` or other execution limits when supported | Server-side command execution deadline | Distinct from waiting for replication/journal |

You should not map all timeout types to a single internal message like "MongoDB did not write." Some errors occur **before sending the command**, while others occur **after the primary has already modified data**. Each type requires its own monitoring and retry policy.

### Responses can still contain write results alongside a write concern error

At the database command level, a response can report the number of documents successfully inserted/updated during the command application step, **while also** including a `writeConcernError` when the requested acknowledgment level was not met.

```javascript
// Illustrative structure diagram, not actual output
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    errmsg: "waiting for replication timed out"
  }
}
```

Do not check only `ok: 1` and conclude all write concern conditions were met. Conversely, do not treat `writeConcernError` as proof that the operation was reverted by the server.

In drivers, write concern errors may be surfaced as corresponding exceptions; the application must distinguish them from **write errors** such as duplicate keys or schema validation violations.

## 11. Write acknowledgment level decision table

| Business requirement | Write concern to consider | Points to evaluate |
| --- | --- | --- |
| Telemetry that can tolerate losing some events | `w:0` where appropriate | No certainty the server wrote; requires handling loss/drops and driver support |
| Routine operational writes, primary ack only | `w:1` | Rollback risk during failover |
| Primary ack and primary journal requirement | `w:1,j:true` | No majority replication yet |
| Need confirmation on two data-bearing members | `w:2` | Does not equal majority in all topologies |
| Critical business writes needing failover protection | `w:"majority"` | Replication latency, data-bearing majority, journal policy |
| Critical writes wanting explicit journal requirement | `w:"majority",j:true` | Evaluate latency, journaling, and infrastructure |
| Do not want to wait too long for write concern | Add appropriate `wtimeout` | Timeout does not auto-rollback; must handle unknown outcome |

There is no single "strongest and always best" configuration for every workload. Higher acknowledgment levels can increase latency or reduce write availability when the replica set is degraded. Levels that are too low increase the risk of losing data that the application already considered successful.

### An example contrasting latency and durability

Suppose the primary is in zone A, and secondaries are in zones B and C. When network latency from A to B/C increases:

- `w: 1` may still receive acknowledgment sooner because it does not wait for secondaries.
- `w: "majority"` must wait for one secondary in a three voting data-member topology, so responses are slower.
- If both B and C cannot replicate, the primary may lose election quorum depending on connectivity; if no writable primary remains, **no `w` level turns a secondary into a valid primary**.

High latency does not automatically prove the cluster is misconfigured. You must define latency and durability targets, then choose member placement, write concern, and timeouts accordingly.

## 12. Default write concern and configuration precedence

An operation without an explicit `writeConcern` still has an **effective write concern**. This value can come from server/replica set defaults, client/driver settings, database or collection settings, or an explicit option on the operation.

From the application perspective, keep in mind:

1. An **explicit write concern on an operation** is generally used for that operation.
2. When an operation omits it, it may inherit settings configured at the collection/database/client level or cluster default.
3. When the server has a cluster-level **default write concern** configured, account for that value instead of assuming a fixed default.
4. Different drivers/frameworks have their own option inheritance rules; check the active configuration and library version.

### Defaults may depend on arbiters and topology

Modern MongoDB versions support an **implicit default write concern**; it is typically `w: "majority"` in many replica sets, though in some cases `w: 1` is used when the topology includes an arbiter and a limited number of data-bearing voting members.

Therefore, do not state "MongoDB always defaults to `w: 1`" or "MongoDB always defaults to `w: "majority"`" without knowing the specific version and configuration.

On supported deployments and with appropriate privileges, you can inspect:

```javascript
db.adminCommand({ getDefaultRWConcern: 1 })
```

The output may display the default write concern along with the configuration source depending on version. This is a **configuration read command**, not one that modifies defaults. If the application has strict durability requirements, still specify the desired acknowledgment level clearly in design documents and deployment configuration.

### Do not confuse with read concern and read preference

- **Write concern:** to what extent a write command must be acknowledged.
- **Read concern:** the consistency/recency level guaranteed for data read under the corresponding conditions.
- **Read preference:** whether the driver prefers routing read operations to the primary or which secondary.

Selecting `readPreference: secondary` does not raise the write concern. Selecting `readConcern: "majority"` does not force the primary to wait for journaling on all writes. Each option addresses a different layer of requirements.

## 13. Safe practice dataset in `mongosh`

The examples below should only be run on a practice replica set with isolated data. If run on standalone MongoDB, options like `w: "majority"`, `w: 2`, or failover will not behave as they do in a replica set. Do not disconnect networks or stop members of a system serving real data for testing.

Select the database:

```javascript
use mongo_write_concern_lab
```

Create a document via insert with primary acknowledgment:

```javascript
db.orders.insertOne(
  {
    _id: "order-WC-01",
    customerId: "C01",
    status: "pending",
    total: 200,
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: 1,
      wtimeout: 5000
    }
  }
)
```

If this command succeeds and the server has a writable primary, the document is acknowledged at `w: 1`. This example does not prove that secondaries have replicated it.

### Updating with majority

```javascript
db.orders.updateOne(
  {
    _id: "order-WC-01",
    status: "pending"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
```

The command uses the `status: "pending"` filter to avoid accidentally transitioning a canceled order to `paid`. If the command is acknowledged with the requested write concern, the application gets a stronger acknowledgment than `w: 1`. If `matchedCount = 0`, inspect the business state; do not automatically conclude it is a replication error.

### Deleting with write concern

```javascript
db.orders.deleteOne(
  { _id: "order-WC-01", status: "paid" },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
)
```

Write concern applies to **write operations** such as insert/update/delete, not just inserts. A majority-acknowledged delete carries the corresponding acknowledgment semantics. Do not test deletion if you are using data you need to keep; this example is strictly for the lab.

### Do not run examples in random order

If you run `deleteOne()` first, subsequent update examples will not find the document. Re-running `insertOne()` with the same `_id` may cause MongoDB to return a duplicate key error. Those responses belong to **data operation semantics**, not evidence of a write concern failure.

## 14. Inspecting replication status before drawing conclusions about write concern

On a replica set, use read commands:

```javascript
rs.status()
```

```javascript
rs.conf()
```

```javascript
db.adminCommand({ hello: 1 })
```

In many MongoDB versions, `rs.status()` includes fields describing members, `PRIMARY`/`SECONDARY`/`ARBITER` states, replication progress, and several majority counters:

| Information to inspect | Why does it matter? |
| --- | --- |
| `members[].stateStr` | Is there a writable primary and can secondaries replicate? |
| `members[].health` | Can the primary see the other members? |
| `members[].optime` or equivalent | Are secondaries lagging behind the primary? |
| `votingMembersCount` | Size of the voting group per server, when present |
| `majorityVoteCount` | Election majority per server, when present |
| `writeMajorityCount` | Majority write acknowledgment threshold per server, when present |
| `members[].arbiterOnly` or `rs.conf().members` | Distinguish voting-only nodes from data-bearing nodes |

Not every version necessarily returns every field at the exact same path; this is a checklist of **information to look for**, not a mandatory JSON schema.

### Counting voters is not equivalent to calculating write majority

```javascript
const cfg = rs.conf();
const voters = cfg.members.filter(m => m.votes === 1);
const electionQuorum = Math.floor(voters.length / 2) + 1;

printjson({
  votingMembers: voters.length,
  electionQuorum,
  arbiters: cfg.members.filter(m => m.arbiterOnly === true)
                       .map(m => m.host)
});
```

This snippet illustrates **election quorum** for a typical stable configuration. It is **not** a replacement algorithm for how the server computes `writeMajorityCount` across all special configurations, reconfigurations, or newly added members.

### When `w: "majority"` is unusually slow

Check these categories of causes:

1. Secondaries are lagging or disconnected and have not acknowledged sufficiently.
2. Network/journal/I/O latency increases acknowledgment time.
3. Configuration has an arbiter and insufficient data-bearing voters remain to reach write majority.
4. The system is undergoing failover or has no writable primary.
5. `wtimeout` is set too low relative to latency targets and infrastructure conditions.

Do not "fix" this by automatically lowering `w` to 1 for all critical writes without evaluating rollback risk and durability goals.

## 15. Java MongoDB Sync Driver: declaring write concern

The MongoDB Java Sync Driver supports the `com.mongodb.WriteConcern` class. You can configure an acknowledgment level on a collection so that write operations through that handle use the selected setting.

```java
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class WriteConcernDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        WriteConcern durableMajority = WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5000, TimeUnit.MILLISECONDS);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_write_concern_lab");

            MongoCollection<Document> orders =
                db.getCollection("orders")
                  .withWriteConcern(durableMajority);

            orders.insertOne(
                new Document("_id", "order-java-WC-01")
                    .append("status", "pending")
                    .append("total", 350)
            );

            orders.updateOne(
                Filters.and(
                    Filters.eq("_id", "order-java-WC-01"),
                    Filters.eq("status", "pending")
                ),
                Updates.set("status", "paid")
            );

            System.out.println(
                "Completed commands with configured write concern"
            );
        } catch (MongoWriteConcernException e) {
            System.err.println(
                "Requested write acknowledgment level not met: " + e.getMessage()
            );
            System.err.println(
                "Do not treat this as proof that the write was rolled back"
            );
        } catch (MongoWriteException e) {
            System.err.println(
                "Write operation error (e.g., duplicate key): "
                + e.getMessage()
            );
        }
    }
}
```

This example requires the appropriate **MongoDB Java Sync Driver** dependency, a replica set with a primary, and the `MONGODB_URI` environment variable. `withWriteConcern()` returns a collection handle with the new configuration; it does not mutate every collection handle across the database.

`MongoWriteConcernException` and `MongoWriteException` are shown to distinguish the two main error categories; real applications also need to handle connection errors, server selection errors, timeouts, and other `MongoException` types according to their chosen strategy.

### Write concern options in Java

```java
// Primary acknowledgment
WriteConcern primaryAck = WriteConcern.ACKNOWLEDGED;

// No server acknowledgment requested (use with caution)
WriteConcern unacknowledged = WriteConcern.UNACKNOWLEDGED;

// Require a specific number of members
WriteConcern twoMembers = new WriteConcern(2);

// Majority and journal, with write concern timeout
WriteConcern strict = WriteConcern.MAJORITY
    .withJournal(true)
    .withWTimeout(5, TimeUnit.SECONDS);
```

Do not set `WriteConcern.UNACKNOWLEDGED` for transactions/tasks that require confirmed success; being able to configure `w: 0` does not mean it is suitable for all Java Driver operations.

### Inheritance order in the driver

In Java, write concern can be configured at multiple levels:

```java
MongoDatabase dbWithConcern = client
    .getDatabase("mongo_write_concern_lab")
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> orders = dbWithConcern
    .getCollection("orders")
    .withWriteConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(5, TimeUnit.SECONDS)
    );
```

The collection handle configuration applies to operations executed via that handle; do not assume it automatically alters every other collection access path in the application.

### With transactions

For multi-document transactions, write concern matters at **commit**, not as an arbitrary per-statement option inside the transaction. The application should configure **TransactionOptions** and ensure the acknowledgment level aligns with durability goals; do not attempt to use `w: 0` or work around transactional behavior with per-operation write concerns inside a transaction.

A transaction that called `commitTransaction()` but encounters a network error or timeout on the client may have an unknown commit state from the client's perspective; handle it using the driver's **error labels and transaction retry guidance**. Write concern does not replace commit retry mechanisms and idempotency handling.

## 16. Relationship between write concern, rollback, and retry

Consider three scenarios along a timeline:

### Scenario A: `w: 1`, primary fails before secondaries receive data

```text
Client -> P writes X -> P acks w:1 -> client reports success
                  |
                  +-- S1 does not have X yet
                  +-- S2 does not have X yet
                  |
                  v
                P fails
```

When S1 or S2 is elected as the new primary, the write X that was not majority-committed on the old primary **may be rolled back**. The fact that the client previously received `w: 1` does not prevent this possibility.

### Scenario B: `w: "majority"`, enough secondaries acknowledge

```text
Client -> P writes X
          |
          +--> S1 has replicated X
          |
          +--> majority met -> ACK
```

With the majority requirement and necessary journaling/commit conditions, write X has stronger protection against failover. S2 is not required to finish if majority is already met; S2 can continue syncing afterward.

### Scenario C: `w: "majority"` times out

```text
Client -> P writes X
          |
          +--> S1 slow / disconnected
          |
          +--> wtimeout -> write concern error
          |
          +--> later S1 may receive X
```

The application **cannot tell solely from a timeout** whether X reached majority shortly afterward. If it issues a new write operation identical to X, the outcome depends on the idempotency of the operation.

### Design patterns to reduce duplicate write risk

- Write documents with a unique `_id` or business operation ID, backed by an appropriate unique index.
- Use conditional updates based on state or version when possible.
- For `$inc`, debits, or transaction creation, use a **ledger/operation ID** mechanism to detect whether an operation has already been applied.
- Use retryable writes/transactions according to driver capabilities and server version, distinguishing a driver retry of the **same logical write** from a new write call.
- When the outcome is uncertain, check the business state before initiating a new operation; re-reading alone does not always resolve all races without explicit locks/idempotency.

Write concern defines the acknowledgment level, whereas **preventing duplicate processing is an independent business problem**.

## 17. When a write "succeeds" does not tell the whole story about read consistency

Suppose an application writes a document with `w: "majority"`, and then another screen reads from a secondary:

```text
          Majority write succeeds
                    |
        Client B reads secondary S2
                    |
          S2 may be lagging
```

A strong write concern does not automatically guarantee that **every read on every secondary immediately sees the new data**, because read preference and read concern also play a role. A secondary can serve older data depending on read settings and replication state.

Requirements such as:

- **Read-your-writes:** the same business flow must see changes it just wrote.
- **Monotonic reads:** subsequent reads must not see an older state than earlier reads.
- **Causal consistency:** multiple operations within the same session are observed in proper causal order.

require coordinating **write concern, read concern, sessions**, and topology conditions. Do not treat `w: "majority"` alone as a universal solution for all forms of read consistency.

In particular, `readConcern: "majority"` pertains to majority-committed data that a read operation is allowed to observe; it does not mean "reading from any secondary always returns the latest update" and does not replace `linearizable` reads when required.

## 18. Common mistakes and misconceptions

| Misconception | Why is it wrong? | Correct understanding |
| --- | --- | --- |
| "`w:1` guarantees data is already saved on secondaries" | Only requires primary acknowledgment | If replication acknowledgment is needed, use the corresponding `w` level |
| "`w:2` is always a majority" | Depends on voting member count and topology | Use `"majority"` when the goal is majority |
| "`w:3` means writing to all nodes" | A replica set may have more than three data-bearing members | Numeric `w` is an acknowledgment threshold, not total node count |
| "An arbiter counts as a data-bearing acknowledgment" | Arbiters store no data | Arbiters only assist in elections |
| "P–S–A with P+A remaining means majority writes will still succeed" | Only one data-bearing member remains | Election quorum differs from write majority |
| "`j:true` means all secondaries have received the data" | Journal and replication are two separate layers | Combine `w` and `j` based on your goals |
| "`j:false` disables server journaling" | Only omits requiring journal acknowledgment in the write concern | Storage engine journaling is configured separately |
| "`wtimeout` is the entire client connection deadline" | Only limits waiting for write concern | Distinguish socket/connect/server selection timeouts |
| "A timeout means MongoDB rolled back the write" | The write may already be applied on the primary | Handle unknown outcomes and idempotency |
| "Command returning `ok:1` means all write concern conditions were met" | The response may include `writeConcernError` | Inspect both the result and any errors |
| "Enabling retries makes every `$inc` immune to duplication" | Manual retries creating a new logical write can re-apply | Use operation IDs, conditional updates, and proper driver retries |
| "MongoDB always defaults to the same write concern" | Defaults depend on version, topology, and configuration | Check the effective write concern |
| "Writing with majority guarantees reading any secondary always sees the latest data" | Secondaries can lag; read policies differ | Design read concern/read preference/sessions |
| "`w:0` means the command was definitely accepted by the server" | Does not wait for acknowledgment | Do not infer server state from client-side success |
| "Having a primary means any `w:majority` write can be acknowledged" | May lack enough data-bearing members for majority | Check replication and write majority |
| "`wtimeout:0` guarantees the client will never time out" | Other limits still exist | Distinguish timeouts across layers |

## 19. Practice exercises

### Exercise 1. Comparing `w: 1` and `w: "majority"`

A P–S1–S2 replica set has three voting data-bearing members. Primary P has applied a write command, but S1 and S2 have not finished replicating it.

Can `w: 1` be acknowledged yet? Has `w: "majority"` been satisfied yet?

**Answer:** `w: 1` can be acknowledged by P under its configuration; `w: "majority"` is not yet satisfied if only P holds the change and insufficient data-bearing members have acknowledged. Once at least one eligible secondary acknowledges under the majority mechanism, this requirement can complete.

### Exercise 2. `j: true` does not replace replication

An application uses `{w: 1, j: true}` and receives success. Can we conclude the write exists on at least two nodes?

**Answer:** No. This level requests primary acknowledgment along with the journal condition, not confirmation from a secondary. Rollback risk for writes that are not majority-committed still exists during failover.

### Exercise 3. P–S–A when the secondary disconnects

A replica set has P (primary), S (secondary), and A (arbiter), all voting. S fails; P and A can communicate. Questions:

1. Can P still maintain election quorum?
2. Can `w: 1` be acknowledged by P?
3. Can `w: "majority"` be satisfied using only P and A?

**Answer:** (1) Yes, P+A hold 2/3 votes. (2) Yes, provided P remains a writable primary and the operation has no errors. (3) No, because A stores no data; majority write in this topology requires participation of the data-bearing secondary.

### Exercise 4. `wtimeout` and unknown outcome

Run:

```javascript
db.counters.updateOne(
  { _id: "visits" },
  { $inc: { count: 1 } },
  { writeConcern: { w: "majority", wtimeout: 1000 } }
)
```

The command reports a write concern timeout. Should you immediately send a new `$inc` to "make sure the write happened"?

**Answer:** Do not retry blindly. The primary may have already applied the first increment. If a different logical write is sent, `count` may increment twice. You need an operation tracking/idempotency mechanism or appropriate retryable writes, and proper handling for unknown outcomes.

### Exercise 5. Writing an `insertOne` command with majority and journal

Insert a document with `_id: "tx-001"` into `db.payments`, requiring majority acknowledgment, journal, and an 8-second wait limit.

**Answer:**

```javascript
db.payments.insertOne(
  {
    _id: "tx-001",
    amount: NumberDecimal("150.00"),
    status: "recorded"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 8000
    }
  }
)
```

If re-run with the same `_id` after the prior operation succeeded, a duplicate key error may occur. This should be treated as a signal to **reconcile the transaction's state**, rather than assuming duplicate key simply means a new successful operation.

### Exercise 6. Choosing `w` by topology

A replica set has five voting data-bearing members. The application specifies `w: 2`. Is this equivalent to `w: "majority"`?

**Answer:** No. The election majority for five voters is three; majority write in this topology requires a threshold corresponding to three data-bearing voting members. `w: 2` only requires two members to acknowledge, so it is weaker than `w: "majority"` in this example.

### Exercise 7. Interpreting a `writeConcernError`

A database command returns:

```javascript
{
  ok: 1,
  n: 1,
  writeConcernError: {
    errmsg: "waiting for replication timed out"
  }
}
```

Can we deduce that the document was definitely not created?

**Answer:** No. The response indicates the write command may have been applied, but the requested replication/journal acknowledgment level was not met. You must reconcile the data and apply business retry policies; do not rely on a write concern timeout to assume the operation was rolled back.

### Exercise 8. When is `w: "majority"` still not enough for read consistency?

An application writes a document with majority write concern, then reads from a lagging secondary and does not see the new document. Is this a contradiction?

**Answer:** Not necessarily. Majority write acknowledgment does not guarantee **all secondaries have immediately applied the change**. You need to consider read concern, read preference, and causal consistency/sessions as needed, rather than treating `w: "majority"` as a directive forcing every secondary to serve the latest data.

### Exercise 9. Reading the default write concern

A service does not specify `writeConcern` when calling `insertOne()`. Can we conclude for certain that it is `w: 1`?

**Answer:** No. The effective level depends on topology, version, cluster default write concern, and driver/collection settings. When a specific durability level is needed, configure it intentionally and verify the active defaults.

### Exercise 10. An error unrelated to write concern

A collection has a unique index on `orderCode`. An insert operation uses `{w: "majority", j: true}` but the `orderCode` value is a duplicate. Will increasing `wtimeout` fix it?

**Answer:** No. A duplicate key is a **write execution error due to a data constraint**, not an insufficient wait time for replication/journal. You must fix the data or handle duplicate key cases in business logic.

## 20. Process for choosing write concern in a project

When implementing a MongoDB data-writing service, answer these questions in order:

1. **Data criticality:** can some logs be lost, or are these orders/transactions whose acknowledgments must never be lost?
2. **Actual topology:** how many data-bearing voting members exist? Is there an arbiter? Which failure domains are members placed in?
3. **Post-failover goals:** do writes reported as successful to the application need protection from rollback during normal failovers?
4. **Journal durability:** does journaling need to be explicitly requested? What is the environment's default journaling behavior?
5. **Acceptable latency:** how long can you wait at most to achieve acknowledgment? Which timeouts belong to write concern versus network/driver?
6. **Error behavior:** how are write concern errors handled? Are there operation IDs or safe retry strategies for non-idempotent writes?
7. **Subsequent read policy:** does the application require read-your-writes or causal consistency? Does it read from secondaries?
8. **Operational observability:** are replication lag, primary availability, write concern errors, and retry counts monitored?

For critical workloads, a common design uses **`w: "majority"` with an appropriate journal policy**, a reasonable timeout for the infrastructure, and handling for unknown outcomes. However, the final choice must be grounded in actual data, durability requirements, latency tolerance, and replica set architecture.

## 21. Summary

Write concern describes **the acknowledgment level of a write operation**:

- **`w: 0`**: does not wait for server acknowledgment; do not infer the write succeeded.
- **`w: 1`**: primary acknowledges; secondaries may not have replicated yet and non-majority-committed writes may be rolled back.
- **`w: n`**: requires `n` data-bearing members to acknowledge; does not automatically equal majority.
- **`w: "majority"`**: requires acknowledgment at the replica set majority level, helping protect committed writes across normal protocol failovers.
- **`j: true`**: requests the journal condition; **journal durability does not replace replication majority**.
- **`wtimeout`**: limits the wait time for acknowledgment; **a timeout does not mean the operation was not applied or was rolled back**.

To apply these properly, distinguish **primary acknowledgment**, **replica acknowledgment**, **journal acknowledgment**, **election quorum**, and **read operation consistency**. Combining an appropriate write concern with topology, duplicate-write protection, replication monitoring, and read policies enables MongoDB applications to make reliable guarantees about write state and data durability.
