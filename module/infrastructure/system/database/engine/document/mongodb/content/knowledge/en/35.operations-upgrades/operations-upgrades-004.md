# Primary Switchover, Member Replacement, and Minimizing Connection Disruption in MongoDB

## 1. How Can Replica Set Maintenance Affect Users?

Suppose an order application uses a three-member MongoDB replica set:

```text
                  Java Order Service
                          |
                     MongoDB driver
                          |
             +------------+-------------+
             |            |             |
             v            v             v
         mongo-a        mongo-b       mongo-c
         PRIMARY        SECONDARY     SECONDARY
         votes=1        votes=1       votes=1
         priority=1     priority=1    priority=1
```

The operations team needs to replace host `mongo-a`. If they shut down the primary without checking the cluster first, the application may experience:

- No primary during the election window; some writes fail or block.
- The driver holding open connections to the old primary and needing to discover the new topology.
- An in-flight write whose response never arrives, leaving the application **uncertain whether the operation succeeded**.
- A secondary lagging too far behind to qualify safely for election.
- Removing a voting member causing loss of majority if another node simultaneously fails.
- Certificates, DNS, or replica set configuration not yet ready on the replacement machine.

A sound procedure does not promise "zero-disruption primary switchover". It **minimizes the window without a primary, bounds client-visible errors, and prevents data loss from operational mistakes**.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **planned switchover**, **automatic failover**, **stepdown**, **election**, and **rollback**.
2. Verify preconditions around majority/quorum, optime, replication lag, votes, priority, and primary eligibility.
3. Build a runbook to switch primary using `rs.stepDown()` or supported operational mechanisms.
4. Safely add, replace, and remove replica set members with `rs.add()`, `rs.remove()`, `rs.conf()`, and `rs.reconfig()`.
5. Manage initial sync, oplog window, member health, TLS, DNS, hostnames, and sharded cluster boundaries.
6. Configure the Java MongoDB driver to discover topology changes, use retryable operations appropriately, and prevent duplicate business side effects.
7. Coordinate rolling maintenance/rolling upgrades, monitor failovers, and run controlled resilience tests.
8. Distinguish connection-disruption mitigation from **durability/consistency** guarantees of write concerns and transactions.

**Safety scope:** `mongosh` examples are primarily for lab replica sets you administer. Commands such as `rs.stepDown()`, `rs.add()`, `rs.remove()`, `rs.reconfig()`, and member restarts **alter cluster state**; never run them in production without approval, backups, and a rollback plan.

## 2. Concepts to Distinguish

| Concept | Meaning | Intentional? |
|---|---|---|
| **Primary** | Member accepting standard replica set writes | Role decided by election |
| **Secondary** | Member syncing via oplog and optionally serving reads per config | Operational role |
| **Election** | Process by which voting members choose a primary per replica set rules | Automatic or triggered |
| **Automatic failover** | Primary is lost or disqualified; remaining members elect a new primary | Typically due to failure |
| **Planned switchover** | Deliberately shifting the primary for maintenance or operational balance | Yes |
| **Stepdown** | Primary yields leadership and is temporarily ineligible to re-run | Intentional or server-driven |
| **StepUp** | Requesting an eligible secondary to attempt to become primary | Intentional, subject to preconditions |
| **Initial sync** | New member receives a full initial data copy and catches up on the oplog | Can be time-consuming |
| **Rollback** | Reverting uncommitted changes diverging from the elected history after failover | Not a backup mechanism |

### 2.1. Switchover vs. Failover

**Switchover:** the operations team picks the timing, validates candidate secondaries, coordinates with applications, and steps down the primary.

**Failover:** the primary drops unexpectedly, and surviving members automatically elect a new primary if quorum and an eligible candidate exist.

Both use similar election machinery, but **switchover benefits from preparation**. When failover is caused by a network partition, unavailability of a primary can last longer than expected.

### 2.2. The New Primary Is Not Always the Desired Member

Priority, freshness, votes, connectivity, and election conditions shape the outcome. Never assume `rs.stepDown()` automatically promotes `mongo-b` specifically. Always **verify the result** after the election.

### 2.3. Having a Primary Does Not Mean Every Write Survived

A secondary may have replication lag; the new primary is elected under specific rules. For writes without majority acknowledgment, data can roll back after a failover. Looking solely at `stateStr: "PRIMARY"` is not enough to assess business data integrity.

## 3. Majority and Quorum: Non-Negotiable Boundaries

A replica set elects a primary via **voting members**. With $N$ voting members, a majority requires:

\[
\text{majority} = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

Examples:

| Voting members | Majority required | Max voting members lost while keeping majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

A MongoDB replica set can hold up to 50 members, yet at most **7 voting members**. Do not confuse "adding 10 secondaries" with "having 10 votes".

### 3.1. Three-Voter Example

```text
mongo-a PRIMARY   votes=1
mongo-b SECONDARY votes=1
mongo-c SECONDARY votes=1

Majority = 2
```

If `mongo-a` stops, `mongo-b` and `mongo-c` hold 2/3 votes and can elect a new primary **if** they are healthy, reachable, and eligible.

If `mongo-b` is under maintenance and `mongo-a` then fails unexpectedly:

```text
mongo-a DOWN
mongo-b DOWN
mongo-c SECONDARY

Only 1/3 votes remain => no majority.
```

Consequence: no valid primary can be elected, and write availability stops.

### 3.2. Quorum Is Not the Number of Data-Bearing Copies

An **arbiter** holds a vote without storing data. It can break election ties, but:

- It does not serve reads.
- It does not replicate the oplog like a secondary.
- It cannot become primary.
- It does not replace a data-bearing member for redundancy.

In a two data-bearing nodes + one arbiter topology, losing one data-bearing node impacts `majority` write concern and durability according to MongoDB version/topology rules. Never treat an arbiter as a "third data secondary".

### 3.3. Never Arbitrarily Alter Quorum During an Outage

Rushing to change votes or call `rs.reconfig(..., {force: true})` during a network partition complicates recovery and risks rollbacks. Determine each member's view, majority status, and committed history before changing configuration.

## 4. Election Eligibility: Who Can Become Primary?

A member is not eligible merely because its state is `SECONDARY`.

### 4.1. Conditions to Check

- `votes`: does the member have a vote?
- `priority`: is the member eligible to run and with what priority?
- `hidden`: usually paired with `priority: 0`.
- `secondaryDelaySecs`: delayed secondaries are configured not to run for primary.
- `SECONDARY` state and replication progress.
- Data freshness / optime relative to other members.
- Network reachability to a majority of voting members.
- Whether the member is `frozen` or in initial sync.

### 4.2. Example of a Non-Electable Member

```javascript
{
  _id: 2,
  host: "mongo-c.example.internal:27017",
  votes: 1,
  priority: 0,
  hidden: true
}
```

This member can vote in elections, but cannot become primary because `priority: 0`.

### 4.3. Do Not Conflate `votes` and `priority`

`votes` contributes to quorum/elections; `priority` governs whether a member can become primary and its preference order. A voting member with `priority: 0` can cast a vote yet never run for primary.

### 4.4. Higher Priority Does Not Guarantee Instant Promotion

Even when `mongo-b.priority=2` and `mongo-c.priority=1`, if `mongo-b` lags, is unreachable, or fails eligibility checks, the election outcome can differ from expectations.

**Never orchestrate a switchover relying solely on priority numbers while skipping freshness verification.**

## 5. Replication Lag and Oplog Window Before Switching Primary

### 5.1. Replication Lag

Replication lag is approximately the time difference between the latest oplog entry applied on the primary and on the secondary:

\[
\text{lag}_{secondary} \approx
\text{primaryLastApplied} - \text{secondaryLastApplied}
\]

Suppose:

```text
Primary last applied:    12:00:30
Secondary B applied:     12:00:29
Secondary C applied:     11:57:00

B lag ≈ 1 second
C lag ≈ 3 minutes 30 seconds
```

`mongo-b` looks like the better candidate, yet you must still check health, votes, priority, durable optime, network, and resources.

### 5.2. Oplog Window

The oplog window is the time span between the oldest and newest entries retained in `local.oplog.rs`. If a secondary stays down too long, the sync source may overwrite entries the secondary needs before it returns.

### 5.3. Headroom

An estimate:

\[
\text{headroom} \approx
\text{syncSourceOplogWindow} - \text{replicationLag}
\]

This is an **indicator**, not a strict deadline, because write rates can change.

### 5.4. Why Does This Matter When Replacing a Member?

Initial sync on a new node can take hours. During that window, primary changes must remain retained long enough for the new member to catch up.

If high write throughput shrinks the oplog window too quickly, initial sync can fail and require restarting.

### 5.5. Low-Write Clusters Can Show Misleading Lag

Do not subtract `secondary.optimeDate` from the current wall clock and call that lag. If the primary has had no writes for an hour and the secondary has applied the exact same optime, it may be **completely caught up**.

## 6. Read-Only Inspection Tools Before Every Operation

The following commands are read-only:

```javascript
rs.status();
rs.conf();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
db.getReplicationInfo();
```

### 6.1. `rs.status()`

```javascript
const status = rs.status();
printjson(status);
```

Illustrative output:

```javascript
{
  set: "rsShop",
  date: ISODate("2026-11-14T12:00:40Z"),
  term: NumberLong("12"),
  members: [
    {
      _id: 0,
      name: "mongo-a.example.internal:27017",
      stateStr: "PRIMARY",
      state: 1,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:30Z")
    },
    {
      _id: 1,
      name: "mongo-b.example.internal:27017",
      stateStr: "SECONDARY",
      state: 2,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:29Z")
    },
    {
      _id: 2,
      name: "mongo-c.example.internal:27017",
      stateStr: "SECONDARY",
      state: 2,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:25Z")
    }
  ],
  ok: 1
}
```

The fields above are a **condensed output for explanation**, not an immutable schema across every MongoDB version.

### 6.2. `rs.conf()`

```javascript
const cfg = rs.conf();
printjson(cfg.members.map(m => ({
  _id: m._id,
  host: m.host,
  votes: m.votes,
  priority: m.priority,
  hidden: m.hidden,
  secondaryDelaySecs: m.secondaryDelaySecs
})));
```

`rs.status()` shows **what members are currently doing**; `rs.conf()` shows **how members are configured**.

### 6.3. `rs.printSecondaryReplicationInfo()`

```javascript
rs.printSecondaryReplicationInfo();
```

Useful for human operators quickly reading lag from the primary, though it is text output. For scripts and exporters, use `rs.status()` or the `replSetGetStatus` command.

### 6.4. `rs.printReplicationInfo()`

```javascript
rs.printReplicationInfo();
```

Shows the oplog window **of the currently connected member**, not automatically all members.

### 6.5. `db.getReplicationInfo()`

```javascript
printjson(db.getReplicationInfo());
```

Typical fields include: `logSizeMB`, `usedMB`, `timeDiff`, `timeDiffHours`, `tFirst`, `tLast`.

### 6.6. Inspect from the Exact Target Member

If a MongoDB URI routes automatically to the primary, oplog inspection may run on the primary even when you meant to check a secondary.

When diagnosing a specific node, connect directly as appropriate:

```bash
mongosh "mongodb://mongo-b.example.internal:27017/admin?directConnection=true&tls=true" --tlsCAFile /secure/path/ca.pem --username monitor_user --password
```

`directConnection=true` is useful for diagnosing an individual node, **not** for application URIs needing automatic failover.

## 7. Checklist Before a Planned Switchover

### 7.1. Replica Set State

1. Confirm the current primary and at least one candidate secondary.
2. Confirm a majority of voting members are communicating.
3. Confirm the candidate has `health: 1` and `stateStr: "SECONDARY"`.
4. Confirm the candidate has `priority > 0` and `votes: 1`.
5. Verify replication lag is close to acceptable targets.
6. Verify the oplog window/headroom is ample.
7. Check for any initial sync, rollback, `RECOVERING`, or election storm.
8. Confirm the cluster has sufficient disk, CPU, and network capacity.

### 7.2. Application State

1. Java driver is on a supported version configured for replica set discovery.
2. Seed hosts/SRV and DNS/TLS are valid for the new primary.
3. Retryable reads/writes are configured appropriately.
4. Critical operations have application-level idempotency.
5. APIs handle server selection timeouts, write concern timeouts, and transaction retries.
6. Load balancers/health checks do not pin a single primary hostname.
7. Monitoring combines MongoDB and application dashboards on one timeline.
8. Maintenance window, owner, and rollback path are established.

### 7.3. Never Assume Any Condition Automatically Holds

For instance, `health: 1` does not prove a secondary is election-eligible; `lag: 0` does not prove the application uses the right read preference; `retryWrites=true` on the driver does not make every business command idempotent.

## 8. `rs.stepDown()`: Planned Primary Switchover

### 8.1. Syntax

In `mongosh` connected directly to the **current primary** on a **lab replica set**:

```javascript
rs.stepDown(60, 15);
```

Meaning:

- `60`: seconds during which the former primary cannot become primary again.
- `15`: maximum seconds to wait for a secondary to catch up before stepping down per command semantics.

This method invokes the `replSetStepDown` command. Exact arguments and behavior must be verified against your running MongoDB version.

### 8.2. Equivalent Command

```javascript
db.getSiblingDB("admin").runCommand({
  replSetStepDown: 60,
  secondaryCatchUpPeriodSecs: 15
});
```

**Do not test this casually** on production. It can briefly interrupt writes during the election.

### 8.3. Normal Stepdown Conditions

In non-forced mode, the server checks election and catch-up conditions so it does not step down unsafely without a suitable secondary.

If preconditions fail, the command rejects rather than stepping down. Investigate the cause before retrying.

### 8.4. Why Can the Command Return a Network Error?

When the server steps down, existing connections and in-flight operations to the old primary may be dropped. The shell may report a network error or "not primary" even though stepdown succeeded.

**Do not assume a network error means stepdown failed.**

Reconnect using the **replica set URI**, run `rs.status()`, and confirm the new primary.

### 8.5. Do Not Use `force` as a Shortcut

Calling the command with `force: true` bypasses safety checks and forces the primary to step down even without a caught-up secondary.

That endangers availability and uncommitted writes. Never use it simply to "push through a maintenance schedule".

## 9. Sequence to Minimize Switchover Disruption

```text
            PREPARE
          check quorum
          check lag
          electable candidate
          client retry/metrics
                |
                v
             EXECUTE
           rs.stepDown()
                |
                v
       Election / topology update
                |
                v
             VERIFY
       new primary identified
       majority writes succeed
       app operations recover
       old primary becomes SECONDARY
                |
                v
          CONTINUE MAINTENANCE
          on old primary host
                |
                v
          POST-CHECK / REPORT
```

### 9.1. Step 1: Capture Initial State Snapshot

```javascript
printjson({
  at: new Date(),
  status: rs.status(),
  config: rs.conf()
});
```

In real environments, this output contains sensitive topology/hostnames; store it securely with restricted access.

### 9.2. Step 2: Choose the Maintenance Window

Prefer:

- Low write volume.
- No large bulk imports or backfills running.
- No complex initial sync or resharding in progress.
- Applications configured for retries and observability.
- An operator actively watching with an abort/defer option.

### 9.3. Step 3: Validate the Candidate

The candidate needs:

```text
state=SECONDARY
health=1
votes=1
priority>0
acceptable replication lag
not in rollback/initial sync
stable network / disk
```

If no candidate qualifies, **never force stepdown** merely to finish the schedule.

### 9.4. Step 4: Execute

```javascript
// On the lab replica set primary, after passing preflight checks.
rs.stepDown(60, 15);
```

Do not put this in an infinite retry loop if the connection drops.

### 9.5. Step 5: Reconnect via Full Replica Set URI

```bash
mongosh "mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/?replicaSet=rsShop&tls=true" --tlsCAFile /secure/path/ca.pem --username monitor_user --authenticationDatabase admin --password
```

Applications should use seed lists/SRV and driver discovery; they do not need to know the new primary ahead of time.

### 9.6. Step 6: Verify

```javascript
const after = rs.status();
printjson(after.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

Also verify:

- Exactly one primary is active per the valid cluster view.
- A lab majority write succeeds.
- The old primary transitioned to secondary and resumes syncing.
- Replication lag stabilizes.
- Application error/retry rates return to baseline.
- No unexpected rollbacks or data inconsistencies occurred.

## 10. Absolute Zero Downtime Cannot Be Promised

Even with a healthy replica set and well-configured driver:

- Elections take time.
- Clients must discover the updated topology.
- In-flight operations may fail.
- Some operations **cannot be retried safely**.
- Active transactions may abort.
- Write concern timeouts can leave ambiguous outcomes.

Therefore, the realistic goal is **fast recovery plus accurate error and duplicate handling**.

### 10.1. "Application Still Serving" Differs from "Every Request Succeeds"

An API can keep accepting HTTP requests during an election while some writes transiently fail. With sensible frontend retries and backend idempotency, users may barely notice.

This must never hide failed requests or return fake successes. The system must still track error rates, latency, and user-visible failures.

### 10.2. Define SLOs Clearly

Internal example:

```text
Planned switchover:
  p95 database failover completion <= measured target
  user-visible write failure rate <= organizationally accepted threshold
  no acknowledged majority write loss
```

Never hardcode fixed numbers from examples; benchmark against your actual cluster, driver, and network.

## 11. Automatic Failover When the Primary Drops Unexpectedly

### 11.1. Illustrative Timeline

```text
T0       mongo-a PRIMARY stops
T0+...   members detect heartbeat failure
T0+...   election starts
T0+...   mongo-b elected PRIMARY
T0+...   driver updates topology
T0+...   write requests resume on mongo-b
```

No single fixed duration applies to every step; network partitions, election timeouts, topology/priorities, driver settings, and infrastructure load all affect timings.

### 11.2. No Majority: No Primary

Without enough votes to elect, MongoDB **will not** promote a new primary simply because one healthy secondary exists. This protects consistency.

### 11.3. The Old Primary May Return

Once networking recovers or the host boots back up, the former primary normally rejoins as a secondary and syncs the valid history; writes not majority-committed may roll back.

### 11.4. Do Not Confuse Failover with Backup Restore

Failover shifts service to another member. It cannot recover data deleted legitimately and replicated across members; backups/PITR handle accidental deletions.

## 12. Rollback, Write Concern, and Acknowledged Data

### 12.1. Write Concern `w:1`

With `w:1`, the primary can acknowledge before replicating the write to a majority. If the primary fails before the write reaches majority commit, that write may roll back after an election.

### 12.2. Write Concern `w:"majority"`

With `w:"majority"`, writes are acknowledged once majority criteria are satisfied per topology/version. This reduces rollback risk for majority-acknowledged writes.

However:

- It does not require every secondary to be updated.
- It does not replace backups.
- A write concern timeout does not prove the write **did not** apply.
- Journal/durability semantics and write concern must be evaluated per version and config.

### 12.3. mongosh Example

In `mongosh`:

```javascript
const orders = db.getSiblingDB("ops_lab_376").orders;

orders.insertOne(
  {
    _id: "ORDER-LAB-001",
    status: "CREATED",
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

Run only in a fresh lab; a fixed `_id` prevents duplicate inserts during test retries. Production requires comprehensive business idempotency.

### 12.4. `wtimeout` and Uncertainty

If the server returns a write concern timeout, the command may have already executed on the primary without reaching write concern within the timeout window.

**Never repeat a non-idempotent operation as a fresh request and assume it is safe.** Reconcile by operation ID or unique business key.

## 13. Retryable Writes: Benefits and Limits

### 13.1. Mechanism

MongoDB drivers support retryable writes on compatible replica sets and sharded clusters. Upon eligible network or availability errors, the driver automatically retries **supported write operations**, using session/transaction numbers to reduce duplicate write risk.

```text
App issues write
     |
     v
Driver sends to PRIMARY-A
     |
     v
Primary-A steps down / connection lost
     |
     v
Driver discovers PRIMARY-B
     |
     v
Driver retries if operation and error are eligible
```

### 13.2. What Retryable Writes Do Not Solve

- They do not make every MongoDB command retryable.
- They do not guarantee complex transactions succeed automatically.
- They do not deduplicate a business API request re-sent as a **new operation**.
- They cannot help if client timeouts expire before discovering the new primary.
- They do not replace majority durability or application idempotency.

### 13.3. Retryable Writes vs. Application-Level Retries

Example:

```text
Client POST /orders
  -> API creates new order O1
  -> DB insert succeeds
  -> response lost

Client POST /orders again
  -> API creates new order O2
```

Driver retryable writes protect **the same database operation under the same retry protocol**; they do not stop the backend from generating a second order when a client submits another HTTP request.

### 13.4. Idempotency Key

An API should carry a stable business key:

```javascript
{
  _id: "O1001",
  tenantId: "T01",
  requestId: "CHECKOUT-REQ-123",
  status: "CREATED"
}
```

With a scoped unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

When a request retries, the backend looks up the existing order for that `requestId` and returns the corresponding result. For sharded collections, unique-index constraints also depend on the shard key; design per topology.

## 14. Retryable Reads, Transactions, and Change Streams

### 14.1. Retryable Reads

Drivers can retry eligible read operations on transient failures. However:

- Not every aggregation/command is retryable.
- A retried read after failover may observe newer state if data is changing.
- Retrying a read does not guarantee the query shares the same point-in-time snapshot.

### 14.2. Transactions During Primary Switchover

A transaction can abort due to stepdown, election, or network error. Applications must handle error labels (`TransientTransactionError`, `UnknownTransactionCommitResult`) per driver API.

### 14.3. Transaction Callbacks and Side Effects

When driver helpers retry a transaction callback, callback code executes again. **Never send emails, charge payments externally, or invoke non-idempotent HTTP side effects inside the callback** without proper safeguards.

### 14.4. Change Streams

Change streams can resume across brief interruptions via resume tokens if sufficient oplog history remains. However:

- Save checkpoint tokens durably.
- Ensure the oplog window covers downtime.
- Keep event handlers idempotent.
- Resume tokens are not permanent data backups.

A solid switchover verifies CDC consumers as well as CRUD APIs.

## 15. Application URIs Must Describe a Replica Set, Not Pin a Primary

### 15.1. Purpose-Built Replica Set URI

```text
mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/shop?replicaSet=rsShop&retryWrites=true&retryReads=true&tls=true&w=majority
```

The application connects to the **replica set topology**, and the driver tracks which member is primary.

### 15.2. Why Not Use directConnection for Applications?

```text
mongodb://mongo-a.example.internal:27017/?directConnection=true
```

This URI targets a single host. If that host steps down or fails, the application lacks topology discovery to follow a new primary as in normal replica set usage.

`directConnection=true` belongs in single-node diagnostics, not default high-availability service configs.

### 15.3. MongoDB Atlas and SRV

Atlas typically uses `mongodb+srv://...`, resolving topology/seed hosts via DNS SRV records. This requires:

- DNS resolution from the application environment.
- Valid TLS certificate chains.
- Proper IP access lists or private endpoints.
- Compatible driver versions.
- No hardcoded secrets in source code or logs.

### 15.4. Hostnames Advertised by the Replica Set

Seed hosts are only the initial contact point. The driver subsequently reads hostnames from the replica set configuration.

Therefore, **every hostname in `rs.conf().members[].host` must be resolvable and reachable from clients**, not merely the first hostname listed in the URI.

## 16. DNS, TLS, and Certificates When Replacing a Member

### 16.1. One Hostname Change Can Break Discovery

Suppose a new member:

```text
mongo-d.example.internal:27017
```

is added to `rs.conf()`, while the application network only has DNS entries for `mongo-a/b/c`. The driver discovers `mongo-d` via `hello`, tries to connect, and fails.

### 16.2. Checks Before Adding

- DNS resolution from all members and client environments.
- Network routes and firewall/security groups.
- TLS SANs include the target hostname.
- Trusted certificate chain and CA.
- MongoDB authentication and internal cluster auth.
- Matching MongoDB `replSetName`.
- Valid data path and disk capacity.
- Clock synchronization and OS hardening.

### 16.3. Never Disable TLS Validation "Just to Make It Run"

Never enable options that bypass certificate or hostname verification in production simply because a new member has a SAN mismatch. Fix the certificate or DNS properly.

### 16.4. Reusing Hostnames Carries Risk

If replacing hardware while keeping the old DNS name, ensure the old node is completely stopped and **no two `mongod` processes advertise the same identity** or share incompatible data directories.

If introducing a new hostname, follow the proper add/sync/remove membership workflow instead of editing DNS while ignoring replica set membership.

## 17. Driver SDAM: Discovering the New Primary

MongoDB drivers implement **Server Discovery and Monitoring (SDAM)**. They monitor server descriptions, topology types, `hello` responses, and connection states to select servers for operations.

### 17.1. What Happens During an Election

```text
Primary A                     Driver
  |                             |
  +-- steps down --------------> connection error/not primary
                                |
                                v
                         topology marked unknown
                                |
                                v
                         hello / monitoring
                                |
                                v
                         Primary B discovered
                                |
                                v
                         eligible operations retried
```

Application recovery speed depends on multiple factors beyond election time: heartbeat/`hello` intervals, server selection timeout, connection establishment, and TLS handshakes.

### 17.2. Never Hardcode the Primary in Business Logic

Avoid:

```java
String primaryHost = "mongo-a.example.internal";
// Every write targets the old primaryHost.
```

Let the MongoDB driver manage replica set topology and maintain a long-lived `MongoClient` for the service.

### 17.3. One MongoClient per Pool

Do not instantiate a new `MongoClient` per HTTP request. Doing so creates redundant connection pools, repeated TLS handshakes, and higher latency during topology changes.

Use a singleton or application-managed bean tied to service lifecycle, closing it cleanly on shutdown.

## 18. Configuring the Java MongoDB Sync Driver

### 18.1. Basic Example

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory376 {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is missing");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .retryWrites(true)
            .retryReads(true)
            .applyToClusterSettings(builder ->
                builder.serverSelectionTimeout(
                    15, TimeUnit.SECONDS))
            .applyToConnectionPoolSettings(builder ->
                builder.maxSize(100))
            .build();

        return MongoClients.create(settings);
    }
}
```

This example requires Java 11+ for `String.isBlank()`. Pool sizes, timeouts, and retry settings are **not universal defaults for every workload**; measure and tune them to your SLOs.

### 18.2. Connection Strings via Secret Manager

`MONGODB_URI` from an environment variable is just an example. Production should retrieve credentials via a secret manager or workload identity and never log URIs containing credentials.

### 18.3. Timeouts to Distinguish

| Setting | Purpose | Risk If Too Low / Too High |
|---|---|---|
| `serverSelectionTimeoutMS` | How long the driver tries to pick a suitable server | Too low: fails requests during elections; too high: HTTP requests hang |
| `connectTimeoutMS` | Limit for establishing a TCP connection | Too low: slow networks fail; too high: prolonged waits |
| `socketTimeoutMS` | Driver socket I/O wait limit | Too low: aborts valid queries; too high: stalls requests |
| `maxPoolSize` | Maximum connections in pool | Too small: queuing; too large: server connection pressure |
| `waitQueueTimeoutMS` or equivalent | Waiting for a connection from the pool | Must align with overall request deadline |

Exact option names and builder APIs depend on driver version. Never adjust one timeout in isolation without considering total HTTP deadlines, retry budgets, and idempotency.

### 18.4. Timeouts Cannot Create a Majority

If the cluster loses quorum, raising `serverSelectionTimeoutMS` to a minute merely makes clients wait longer. It cannot make an ineligible secondary become primary.

## 19. Java: Checking Connectivity and Topology After Switchover

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReplicaHealth376 {
    public static void check(MongoClient client) {
        MongoDatabase admin = client.getDatabase("admin");

        try {
            Document hello = admin.runCommand(
                new Document("hello", 1));
            System.out.println(
                "isWritablePrimary=" +
                hello.getBoolean("isWritablePrimary"));
        } catch (MongoException e) {
            System.err.println(
                "MongoDB health check failed: " +
                e.getClass().getSimpleName());
            throw e;
        }
    }
}
```

### 19.1. A Single `hello` Does Not Prove Cluster-Wide Health

This reflects only the **server chosen by the driver** for that command. Comprehensive health monitoring also checks replica set status, application write probes, and per-member metrics under least-privilege roles.

### 19.2. Do Not Expose Topology Details on Public Endpoints

A public `/health` endpoint must never return raw `rs.status()`, internal hostnames, auth details, configs, or credentials.

Keep detailed diagnostics inside authenticated internal monitoring.

## 20. Handling Write Errors When the Primary Changes

### 20.1. Error Categories

- Network connection closed/reset.
- Server selection timeout while no primary exists.
- `NotWritablePrimary` or replica-state transition errors.
- Write concern timeouts.
- Transient transaction or unknown commit outcome errors.
- Duplicate key errors when retrying business requests with the same ID.

### 20.2. Never Catch All Exceptions and Retry Forever

Dangerous pattern:

```java
// DO NOT DO THIS:
while (true) {
    try {
        inventory.updateOne(filter, update);
        break;
    } catch (Exception ignored) {
        // Retry forever; can double-apply a business operation.
    }
}
```

### 20.3. Better Retry Rules

1. Determine whether the operation is eligible for driver retries.
2. Rely on driver retry semantics before writing custom wrappers.
3. For business retries, enforce an idempotency key or state machine.
4. Bound attempt count and duration to the request deadline.
5. Use backoff with jitter to avoid retry storms.
6. Separate permanent errors (validation, duplicate key) from transient ones.
7. Emit metrics for retries and unknown outcomes—not just successes.

### 20.4. A Timed-Out Write May Have Already Executed

If a client gets a network timeout after sending `$inc`, never assume it did not run. **Reconcile state via `requestId`** before issuing another business increment.

## 21. Keeping Business Operations Idempotent

### 21.1. Order Creation with a Request Key

```javascript
db.getSiblingDB("ops_lab_376").orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

API writes:

```javascript
{
  _id: "O1001",
  tenantId: "T01",
  requestId: "REQ-913",
  total: 890000,
  status: "CREATED"
}
```

On client retry, the backend queries by `tenantId/requestId` to check whether the request already completed and avoids creating a duplicate order.

### 21.2. Multi-Document Reservations

If an order reserves 3 SKUs, evaluate:

- Atomic conditional updates per SKU.
- Multi-document transactions or a reservation saga with compensation.
- Unique operation IDs.
- Pending/confirmed/released state transitions.
- Post-failover retries and uncertain outcomes.

An atomic `$inc` on one inventory document **does not** make an entire multi-SKU reservation atomic.

### 21.3. Coordinating with External Systems Outside MongoDB

If creating an order triggers an email or payment charge:

```text
MongoDB transaction commit
      |
      v
Outbox event
      |
      v
Worker processes with idempotency
      |
      v
Payment/notification service
```

Never assume retrying a MongoDB transaction synchronizes external side effects; use an outbox or saga pattern where required.

## 22. Read Preference During Elections

### 22.1. `primary`

By default, drivers route reads to the primary. During an election, reads requiring the primary may block briefly or fail transiently.

### 22.2. `secondary` or `secondaryPreferred`

Reads may continue from secondaries in certain scenarios, but:

- Secondaries can be stale.
- During maintenance on a member, read capacity shrinks.
- `secondaryPreferred` has specific fallback semantics; it does not guarantee every read hits a secondary.
- Reading from secondaries does not solve **writes needing a primary**.

### 22.3. Do Not Arbitrarily Flip Read Preference to Mask Errors

If the application needs read-your-writes or strong consistency, switching to secondaries can introduce stale-read bugs.

### 22.4. Causal Consistency

MongoDB causally consistent sessions paired with appropriate read/write concerns support causal guarantees like read-your-writes under documented conditions.

Do not assume a new request, a different session, and `secondary` read preference will always observe a write immediately.

## 23. Application Readiness and Liveness

### 23.1. Liveness

Answers: "Is the Java process alive and capable of functioning?" Never kill and restart an entire application fleet every time MongoDB undergoes a brief election.

### 23.2. Readiness

Answers: "Can this instance accept new traffic for its required capabilities?"

If the entire service depends on writes, readiness may check primary reachability within a reasonable window; however, avoid **dropping all Pods simultaneously** during a few-second election and triggering a cascade failure.

### 23.3. Guarding Against Retry Storms

```text
Election starts
  |
  +-> 100 service instances
       each with 1000 pending requests
          |
          v
       retry immediately at once
          |
          v
       new primary overloaded
```

Use bounded queues, backpressure, exponential backoff with jitter, and request deadlines.

### 23.4. Degrade Gracefully Where Appropriate

A UI might keep displaying cached catalog data during a brief write outage, while **clearly informing users** that checkout could not be confirmed—never returning a false success.

## 24. Replacing a Healthy Secondary: Risk-Reduction Pattern

Suppose:

```text
mongo-a PRIMARY
mongo-b SECONDARY (to be replaced)
mongo-c SECONDARY
```

### 24.1. Prefer Add-First, Remove-Later When Resources Allow

If a new host `mongo-d` is available and config permits, a safer sequence is:

```text
1. Prepare mongo-d (TLS, DNS, network, storage).
2. Add mongo-d as non-voting, priority=0.
3. Let mongo-d complete initial sync and catch up.
4. Transition voting/election eligibility per procedure.
5. Remove mongo-b after verifying quorum.
6. Verify replication and app connections.
```

Key principle: **never leave the cluster short of data-bearing members longer than necessary**.

### 24.2. When Add-First Is Not Possible

Hardware, licensing, or capacity limits may force removing the old node before adding the new one. That widens the risk window, requiring tighter evaluation of quorum, backups, and maintenance windows.

### 24.3. Do Not Treat "Adding a Node" as Harmless

Initial sync places network and disk load on the sync source. Reconfiguring membership affects elections and quorum. Measure carefully before and during the change.

## 25. `rs.add()`: Adding a New Secondary

### 25.1. Host Preparation

The new `mongod` must:

- Run a version compatible with the replica set.
- Match `replSetName`.
- Use proper internal authentication and TLS.
- Have valid data paths and permissions.
- Have bidirectional connectivity with required members.
- Have stable hostname/DNS resolution.
- Not collide with another host running the same identity.

### 25.2. Adding a Non-Voting Member in a Lab

Connected to the primary:

```javascript
rs.add({
  host: "mongo-d.example.internal:27017",
  priority: 0,
  votes: 0
});
```

Benefit: the new member does not alter voting majority while starting initial sync and cannot become primary before syncing completes.

### 25.3. Tracking Progress

```javascript
rs.status();
```

Observe:

- `STARTUP2` during initial sync.
- `initialSyncStatus` where available.
- `RECOVERING` during applicable phases.
- `SECONDARY` once complete.
- Replication lag and sync source.
- Disk, network, and oplog window.

### 25.4. Wait for Full Readiness Before Promotion

Never raise `votes`/`priority` merely because the process started or answers `ping`. Wait for initial sync completion, stability, catch-up, and an observation window.

## 26. Promoting a Non-Voting Member to Voting

Once `mongo-d` has caught up, update the config via `rs.reconfig()` within an **approved procedure**.

### 26.1. Illustrative Lab Example

```javascript
const cfg = rs.conf();
const newMember = cfg.members.find(
  m => m.host === "mongo-d.example.internal:27017"
);

if (!newMember) {
  throw new Error("New member not present in replica config");
}

newMember.votes = 1;
newMember.priority = 1;

rs.reconfig(cfg);
```

### 26.2. Why Not Modify by Hardcoded Array Index?

Avoid:

```javascript
// Contraindicated without verifying the exact member.
cfg.members[3].votes = 1;
```

Array positions can change over operational history. Match members by verified hostname or `_id`.

### 26.3. Check Quorum When Adding a Voter

Moving from 3 voters to 4 voters:

```text
Before: 3 voters -> majority 2
After:  4 voters -> majority 3
```

Adding a voter can **increase the votes required for majority**. If one node is already `DOWN`, adding a voter does not automatically improve availability.

### 26.4. Reconfiguration Restrictions

MongoDB enforces rules on membership/voting changes to safeguard quorum, including limits on adding/removing voting members per reconfiguration, config commitment, and concurrent reconfigs.

Never alter multiple voting fields at once in production without checking your version's exact rules; apply supported incremental steps.

## 27. `rs.remove()`: Removing the Old Member

Once the replacement member is stable and quorum is verified:

```javascript
// LAB / APPROVED CHANGE ONLY.
rs.remove("mongo-b.example.internal:27017");
```

### 27.1. Before Removing

1. Confirm the exact member to remove.
2. Confirm the member is not the active primary serving writes.
3. Confirm the replacement member has synced and caught up.
4. Calculate post-removal majority.
5. Check tolerance if another node fails simultaneously.
6. Verify monitoring, backups, or read preferences do not rely on the old member.
7. Maintain a rollback path and config backup.

### 27.2. Never Remove a Primary Directly Without Preparation

If the node being removed is still primary, perform a planned switchover first. Removing an active primary directly increases outage duration and config inconsistency risk.

### 27.3. After Removing

- Stop and decommission the old member's service per procedure.
- Revoke its certificates, keys, and infrastructure access.
- Update DNS, monitoring, and runbooks.
- Verify applications connect via the replica set URI.
- Check health of remaining members.

### 27.4. Never Use Remove to "Fix" Ambiguous Network Errors

If a secondary briefly loses heartbeats, diagnose the cause first. Removing it prematurely shifts majority and complicates rejoining.

## 28. Example Plan for Replacing a Secondary in a Three-Voter Set

Initially:

```text
A PRIMARY votes1
B SECONDARY votes1 (to be replaced)
C SECONDARY votes1
majority=2
```

### 28.1. When Four Data-Bearing Members Can Coexist Temporarily

```text
Phase 1:
A votes1, B votes1, C votes1, D votes0 priority0
majority=2
D runs initial sync

Phase 2:
D caught up; promote D votes1
A votes1, B votes1, C votes1, D votes1
majority=3

Phase 3:
Remove B
A votes1, C votes1, D votes1
majority=2
```

This is a **conceptual diagram**, not a mandatory order for every deployment. Each config change must verify cluster health and adhere to reconfiguration constraints.

### 28.2. Temporary Window with Majority = 3

If B goes `DOWN` right after D is promoted, all three remaining members A, C, and D must communicate to satisfy majority=3/4 until B is removed.

Thus, **change ordering must reflect real-time topology**, not blindly running "promote then remove" during another incident.

### 28.3. Replacing a Dead Member

If B has already failed, A and C still hold 2/3 majority. Adding D as non-voting and waiting for sync is one option; subsequent voter changes must preserve quorum across every step. If A or C fails before D finishes syncing, availability is impacted.

### 28.4. Never Use `force:true` for Speed

`rs.reconfig(cfg, { force: true })` bypasses safety checks and can create divergent history requiring rollback in edge cases. Consider it only within a verified recovery procedure with specialists and backups—never as a routine step.

## 29. Replacing the Primary with a New Host

Suppose `mongo-a`, currently primary, must be replaced:

```text
mongo-a PRIMARY (to be replaced)
mongo-b SECONDARY
mongo-c SECONDARY
mongo-d newly added
```

### 29.1. Safer Strategy

1. Prepare and add `mongo-d` as a non-voting secondary.
2. Let D complete initial sync and catch up; inspect logs and metrics.
3. Confirm B or C is a healthy primary candidate.
4. Perform planned `rs.stepDown()` on A during the change window.
5. Verify the new primary (B or C) and that writes resume.
6. Maintain/remove A following quorum-safe reconfig procedures.
7. Transition D's votes/priority per plan and monitor.
8. Verify applications, replication, backups, and monitoring.

### 29.2. Why Not "Shut Down A Then Add D"?

If A is primary and B/C have lag or network issues, shutting down A immediately can cause elections to fail or drag out. Adding D before shutting down A prepares capacity without halting writes.

### 29.3. What If the Primary Must Switch Before D Is Created?

Confirm B/C eligibility and majority. Switch A → B/C, then replace A while it is a secondary. This is an option depending on hardware constraints and risk tolerance.

### 29.4. Replacing Host vs. Replacing Disk

If reusing the hostname with a fresh data disk:

- Initial sync may be required.
- Never copy a data directory arbitrarily while the process runs.
- Confirm the old node is stopped and the old disk cannot start concurrently.
- Follow the MongoDB/automation/Operator procedure for your deployment.

If assigning a new hostname, update membership using supported operations.

## 30. Initial Sync and Performance Risk

### 30.1. High-Level Phases

```text
Member joins
   |
   v
STARTUP2 / initial sync
   |
   +-- copy database contents
   +-- build indexes
   +-- fetch/apply oplog while data is copied
   |
   v
RECOVERING / catch-up
   |
   v
SECONDARY
```

Exact details vary by MongoDB version and initial sync method.

### 30.2. Impact on the Sync Source

Initial sync increases:

- Network transfer.
- Disk read/write IOPS.
- WiredTiger cache pressure.
- Oplog fetching.
- CPU and index build load.

### 30.3. Avoid Concurrent Initial Syncs Unless Necessary

Replacing two secondaries simultaneously in a three-member replica set reduces redundancy while doubling sync load. Prefer replacing **one member at a time**, waiting for catch-up before starting the next.

### 30.4. When the Oplog Window Is Insufficient

A slow initial sync during heavy writes may demand more oplog history than retained. Monitor oplog window/headroom rather than simply increasing application timeouts.

### 30.5. Monitoring Completion

```javascript
const s = rs.status();
printjson(s.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

Do not treat `health: 1` as proof initial sync finished; verify `SECONDARY` state, lag, and logs/metrics.

## 31. Rolling Maintenance and Rolling Upgrades

### 31.1. Goal

Update OS, kernel, certificates, or MongoDB binaries node-by-node to **keep most of the replica set serving** instead of taking everything offline together.

### 31.2. General Principles

1. Check the compatibility matrix for MongoDB version, FCV, drivers, and tooling.
2. Verify backups/PITR, quorum, and replication lag.
3. Maintain **one secondary**.
4. Restart it, wait for `SECONDARY` state and catch-up.
5. Repeat for remaining secondaries.
6. Perform a planned primary stepdown if needed, then maintain the former primary.
7. Verify the new topology and application health.
8. Raise FCV only once all criteria in the version's upgrade procedure are met.

### 31.3. Primary-Last Order Has Prerequisites

Each MongoDB version defines specific rolling upgrade/maintenance rules, and Atlas/Operators automate steps differently. Never substitute a generic diagram for the official upgrade guide.

### 31.4. Do Not Move to the Next Secondary Too Soon

```text
B restarts -> B SECONDARY but 30 minutes behind
C restarts immediately -> only A holds the latest data
```

If A fails at that moment, election and availability carry severe risk.

Wait until B is healthy and caught up, and re-verify majority and headroom before touching C.

### 31.5. Practices That Increase Upgrade Risk

- Raising FCV before upgrading all binaries.
- Changing replica set config simultaneously during an upgrade.
- Deploying certificates with mismatched SANs or CAs.
- Restarting multiple voters at once.
- Skipping application compatibility tests.
- Ignoring deprecated features or removed settings.

## 32. Rotating TLS Certificates Without Taking Down the Cluster

### 32.1. Identities to Track

- MongoDB server certificates.
- CAs trusted by drivers.
- Internal member-to-member certificates or keyfiles.
- Credentials and role mappings if using X.509 authentication.

### 32.2. The CA Rotation Problem

If applications trust only the old CA while a new member presents a cert signed by the new CA, TLS handshakes fail even though the database is healthy.

### 32.3. Trust Overlap Plan

An infrastructure-dependent approach:

```text
1. Clients and members trust both old and new CAs during transition.
2. Rotate certificates member by member.
3. Verify TLS, replication, and app connectivity.
4. Migrate clients to the new CA.
5. Revoke the old CA only after all consumers have switched.
```

Exact mechanics depend on MongoDB and platform TLS handling; never apply blindly if your platform mandates a different sequence.

### 32.4. Never Work Around Errors with `tlsAllowInvalidCertificates`

Disabling certificate validation opens impersonation and MITM risks. Fix the chain, SANs, CA trust, and hostnames at the source.

## 33. Atlas: Managed Switchovers and Node Replacements

MongoDB Atlas manages most infrastructure operations, elections, and rolling restarts. Available actions such as Test Failover, restarts, scaling, or maintenance depend on cluster tier and current UI/API capabilities.

### 33.1. Differences from Self-Managed

- No direct OS/process control over hosts.
- Certain commands like `rs.reconfig()`/`rs.stepDown()` may be restricted.
- Node replacements, certificates, and rolling changes use managed mechanisms.
- Monitoring/alerts use Atlas metrics and activity logs.

### 33.2. Never Apply Self-Managed `rs.remove()` Runbooks to Atlas

Atlas uses its own control-plane automation; replace nodes through Atlas-supported controls instead of manually modifying replica set membership.

### 33.3. Brief Disruption Can Still Occur

Even on a managed cluster, applications still need proper URIs, compatible drivers, retries, idempotency, and SLO-aligned timeouts.

### 33.4. Controlled Use of Test Failover

Where supported by tier/environment, Test Failover helps validate:

- How fast applications discover the new primary.
- Server selection and retry behavior.
- Transaction error handling.
- Frontend behavior for in-flight requests.
- Alerts and dashboards.

Testing requires approval and expected-impact assessment—it is not a "zero-risk" button.

## 34. Sharded Clusters: `mongos`, Shard Replica Sets, and Config Servers

### 34.1. Architecture

```text
Java app
   |
   v
mongos routers
   |
   +-- Shard-A replica set
   |      A-P, A-S1, A-S2
   |
   +-- Shard-B replica set
   |      B-P, B-S1, B-S2
   |
   +-- Config-server replica set
          C-P, C-S1, C-S2
```

### 34.2. Switchover in One Shard

A primary change in Shard A does not make Shard B lose its primary. However, cross-shard queries or transactions can still be affected.

### 34.3. Do Not Bypass `mongos`

Sharded cluster applications normally connect to `mongos` routers rather than connecting directly to a shard member to route around a primary event.

### 34.4. Config Server Replica Sets Need Quorum Too

Config servers store critical sharding metadata. Maintain them under a dedicated runbook—never dismiss them as "data-less secondaries" or ignore their topology.

### 34.5. Each Replica Set Has Its Own Quorum

Never sum votes across Shard A, Shard B, and the config server into one pool. Each replica set maintains its own independent voting majority.

## 35. Scenario: Losing an Entire Region

Suppose three members are distributed as:

```text
Region A: PRIMARY + SECONDARY
Region B: SECONDARY
```

If Region A fails, only 1 vote remains in Region B ⇒ insufficient majority for a three-voter replica set.

### 35.1. Multi-Region Does Not Automatically Guarantee Region Failover

Availability depends on voter distribution across failure domains, network partitions, write concern, and topology.

### 35.2. Three-Region Design

```text
Region A: voter1
Region B: voter2
Region C: voter3
```

Losing one region leaves two votes, though inter-region latency, quorum behavior, and primary placement must also be evaluated.

### 35.3. Never Place an Arbiter in a Remote Region Just to "Reach Three"

An arbiter satisfies election vote counts without adding a data copy or backup resilience; architecture must align with RPO/RTO and data residency.

## 36. Designing Metrics and Alerts for Primary Transitions

| Metric/Alert | Question Answered |
|---|---|
| Primary availability | Is a writable primary available? |
| Election count/reasons | Are failovers happening too frequently? |
| Replica member state | Is any node `DOWN`/`RECOVERING`/`ROLLBACK`? |
| Replication lag | Has the candidate caught up? |
| Oplog window/headroom | Does an offline node still have enough history to rejoin? |
| Majority commit point | How far have majority-acknowledged writes progressed? |
| Driver server-selection errors | How long could clients not find a primary? |
| Driver connection pool | Is the pool exhausted or in a reconnect storm? |
| Retry count/error labels | Did retries spike during the election? |
| API HTTP 5xx/latency | Were users disrupted? |
| Transaction abort/retry | Do business operations need reconciliation? |
| Change stream resume failures | Is CDC keeping up? |
| Disk/network/CPU | Is a bottleneck slowing initial sync? |

### 36.1. Before/After Maintenance Dashboard

```text
T-10 min: baseline requests/sec, p95, write errors, lag
T0:      operator triggers planned switchover
T+...:   election, term changes, new primary observed
T+...:   driver topology updated; errors/retries settle
T+10m:   verify secondary health, lag, SLO
```

Plot **MongoDB events** and **application metrics** on the same timeline to separate database election time from client recovery time.

### 36.2. Never Coerce Missing Metrics to Zero

If monitoring cannot collect `rs.status()` from a disconnected node, do not record `lag = 0`. Mark it unknown/missing and fire a dedicated availability alert.

### 36.3. Measure Real Disruption Duration

A metric saying "election completed in 4 seconds" does not prove all services recovered at second 4. Measure **end-to-end time-to-success** for valid API writes.

## 37. Runbook A — Planned Primary Switchover for Maintenance

### Preconditions

- Change ticket, owner, maintenance window, and rollback plan.
- Valid backup/PITR or recovery strategy.
- Current primary identified.
- At least 1 healthy, electable, caught-up candidate.
- Majority remains intact even while the former primary pauses.
- Drivers/clients support topology discovery and retries.
- No open replication or network incidents.

### Execution

```text
1. Capture baseline metrics and config.
2. Notify API, CDC, and reporting owners.
3. Verify candidate lag and oplog headroom.
4. Trigger planned stepDown per procedure.
5. Reconnect via replica set URI.
6. Confirm the new primary.
7. Run majority write and application path tests.
8. Confirm the former primary transitions to SECONDARY.
9. Perform maintenance on the former primary.
10. Monitor and close the change once all SLOs stabilize.
```

### Stop Conditions

**Abort/defer** if:

- Candidate lags or loses electability.
- Quorum is at risk.
- Unexpected rollback, initial sync, or `RECOVERING` state appears.
- Network/TLS/DNS errors occur.
- Backups/checkpoints are missing or invalid.
- Application handling of uncertain writes is unverified.

## 38. Runbook B — Replacing a Secondary with a New Hostname

### Preconditions

- Prepare `mongo-d` with matching version, `replSetName`, networking, and certificates.
- Confirm disk capacity for full initial sync.
- Confirm primary and existing members are healthy.
- Check write throughput and oplog window.

### Execution

```text
1. Add D as non-voting, priority 0.
2. Monitor initial sync.
3. Confirm D reaches SECONDARY and catches up.
4. Plan voter/priority transition based on quorum.
5. Reconfig stepwise, verifying after each step.
6. Remove B once D is ready and quorum is safe.
7. Decommission B and revoke its secrets.
8. Verify all members and application discovery.
```

### Common Mistakes

- Hostname D not resolvable from apps.
- SAN certificate mismatch.
- Wrong `replSetName` on D.
- Insufficient disk on D.
- Promoting votes too early.
- Removing B while another member is still `DOWN`.
- Failing to check backup or read workloads pinned to B.

## 39. Runbook C — Unexpected Primary Failure

### Step 1: Do Not Intervene Arbitrarily

Observe automatic election within your SLO window before taking emergency action, unless a severe confirmed failure requires intervention.

### Step 2: Determine Quorum

Inspect:

- Which voting members remain reachable.
- Which members are eligible candidates.
- Whether a new primary has been elected.
- Whether a network partition exists across zones.

### Step 3: Application Impact

Measure:

- API write errors and server selection timeouts.
- Transaction failures.
- Unknown outcomes needing reconciliation.
- CDC consumers and read staleness.

### Step 4: When the Old Primary Returns

Verify it rejoins with the right role, check replication/rollback logs and disk health. Never force it back to primary just because it held that role previously.

### Step 5: Root-Cause Analysis

Node crash, disk, CPU, DNS/TLS, heartbeat timeout, network partition, operator change, or overload can all trigger failover.

## 40. Runbook D — No Primary Due to Lost Majority

```text
Replica set: 3 voters
Healthy reachable: 1
Primary: none
```

### What to Do

1. Determine whether the fault is network or host-level.
2. Restore connectivity to existing voting members.
3. Check disk, auth, TLS, OS, and logs.
4. Preserve data; never launch duplicate nodes with the same identity concurrently.
5. Gather evidence on optimes and majority commits before selecting a recovery path.
6. Follow a MongoDB-supported disaster recovery procedure if majority truly cannot be restored.

### What Not to Do

- Never run `rs.reconfig(..., {force: true})` just to get a primary immediately.
- Never remove all unavailable members in a loop.
- Never re-run `rs.initiate()` on existing data.
- Never delete data files to "reset the cluster".

These actions risk divergence, rollbacks, or corrupted recovery and require experienced specialists and a clear plan.

## 41. Runbook E — New Member Fails to Finish Initial Sync

### Primary Checks

```javascript
rs.status();
db.getReplicationInfo();
```

Plus:

- `initialSyncStatus` logs and errors.
- Network throughput and TLS.
- Disk capacity and I/O latency.
- Sync source load.
- Oplog window relative to clone duration.
- Index build errors.

### Remediation

Fix the underlying bottleneck, adjust capacity or timing, and follow the version's retry/resync procedure. Never blindly inflate oplog size or restart repeatedly without diagnosing why initial sync failed.

## 42. Runbook F — Application Still Errors After a New Primary Exists

### 42.1. Distinguish Database Issues from Driver Issues

If a new primary is active yet Java still throws `serverSelectionTimeout`, possible causes include:

- URI uses `directConnection=true` pointing to the old primary.
- DNS/SRV fails to resolve the new host.
- TLS CA/SAN mismatch.
- Network/firewall blocks traffic to the new member.
- Outdated driver version or unhealthy connection pool.
- Auth mechanism or credentials differ across nodes.
- Application instances have not refreshed or are in a retry storm.

### 42.2. Investigation Checklist

1. Verify `rs.status()` on the cluster.
2. Check `rs.conf().members[].host`.
3. Test DNS/TLS from application hosts.
4. Inspect redacted driver SDAM/server-selection logs.
5. Check pool size, waiting requests, and reconnect rate.
6. Compare traffic behavior across app instances.
7. Run an authorized test from a diagnostic/lab instance.
8. Never print raw passwords or URIs to logs during debugging.

### 42.3. Do Not Fix by Restarting All Services at Once

Mass restarts can trigger a connection storm that overwhelms the new primary. If an app rollout is needed, use batched/rolling restarts with capacity and connection backoff.

## 43. `rs.freeze()` and `rs.stepUp()`: Bounded Control Tools

### 43.1. Freezing a Secondary

In specific operational situations, `rs.freeze(seconds)` on a secondary prevents it from running for primary for the specified duration.

```javascript
// ONLY in an authorized lab, on an appropriate secondary.
rs.freeze(60);
```

`rs.freeze(0)` unfreezes according to supported semantics.

### 43.2. Freeze Does Not Guarantee Quorum

If you freeze all candidates and then step down the primary, no failover can occur. Never use freeze to "keep the cluster quiet" without accounting for votes, priority, and eligibility.

### 43.3. StepUp

Some MongoDB versions/tools provide `replSetStepUp` or an equivalent shell helper to ask a secondary to attempt promotion. It succeeds only when the member is eligible and quorum exists.

Forcing a specific member to become primary should **not** be routine; normally let elections and priorities decide after preflight checks.

### 43.4. Avoid Unnecessary Simultaneous Tweaks

A planned switchover rarely needs priority edits, freezes, stepUps, and stepDowns all at once. The more concurrent topology changes you make, the harder outcomes and rollbacks become to reason about.

## 44. Assessing Impact Before Changing Votes or Priority

### 44.1. Scenario Matrix

| Action | Can Quorum Change? | Can Primary Candidates Change? | Key Consideration |
|---|---|---|---|
| `rs.stepDown()` | Does not change voter count directly | Yes, via election | Brief write interruption |
| Add non-voting secondary | Does not change voter count | Not yet | Initial sync resource load |
| Promote non-voter to voter | Yes | Yes if `priority > 0` | Recalculate majority |
| Change priority | Does not change votes directly | Yes | May trigger election |
| Remove voting secondary | Yes | Possibly | Temporary redundancy reduction |
| Remove primary | Yes / shifts role | Yes | High risk; switchover first |
| Force reconfig | Possibly | Possibly | Emergency recovery only |

### 44.2. Configurations Must Commit

MongoDB enforces conditions for committing replica set reconfigurations. Never issue a subsequent reconfig before confirming the prior config has committed per version mechanics.

### 44.3. Do Not Create "Fake Quorum"

Placing multiple arbiters or voters on the same host or shared power infrastructure does not provide real resilience; evaluate **failure domains**, not just node counts.

## 45. Safe Lab Exercise: Observe Before Changing

### 45.1. Create Isolated Data

In a lab replica set, after verifying the namespace is empty:

```javascript
const lab = db.getSiblingDB("ops_lab_376");
const orders = lab.orders;

if (orders.countDocuments({}) !== 0) {
  throw new Error("Lab collection not empty; choose a new namespace");
}

orders.insertMany([
  {
    _id: "O376-1",
    tenantId: "T01",
    status: "CREATED",
    createdAt: new Date()
  },
  {
    _id: "O376-2",
    tenantId: "T01",
    status: "CREATED",
    createdAt: new Date()
  }
]);
```

Never run `drop()` or `deleteMany({})` on production to "clean a lab" without verifying what data lives in that namespace.

### 45.2. Capture Before-State

```javascript
const before = rs.status();
printjson(before.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

### 45.3. Inspect Voting Config

```javascript
const cfg = rs.conf();
printjson(cfg.members.map(m => ({
  host: m.host,
  votes: m.votes,
  priority: m.priority
})));
```

### 45.4. Simple Lag Calculation

```javascript
const s = rs.status();
const p = s.members.find(m => m.stateStr === "PRIMARY");

if (!p || !(p.optimeDate instanceof Date)) {
  print("PRIMARY_UNKNOWN");
} else {
  const lag = s.members.map(m => ({
    host: m.name,
    state: m.stateStr,
    lagSeconds:
      m.stateStr === "SECONDARY" &&
      m.optimeDate instanceof Date
        ? (p.optimeDate.getTime() -
           m.optimeDate.getTime()) / 1000
        : null
  }));

  printjson(lag);
}
```

Do not compute lag for an arbiter and never coerce `null` to `0`.

### 45.5. Check Oplog Window

```javascript
printjson(db.getReplicationInfo());
```

This reflects only the connected member's window, not necessarily the whole cluster.

### 45.6. Test Planned Switchover

Only after verifying quorum, candidates, and lab authorization:

```javascript
// Command changes the primary; never run arbitrarily in production.
rs.stepDown(60, 15);
```

Then reconnect using the replica set URI and verify the new primary and application behavior. If the command returns a connection error, do not blindly repeat it; inspect the actual cluster state.

## 46. Read-Only mongosh Script to Inspect Membership

```javascript
function replicaView376() {
  const status = rs.status();
  const conf = rs.conf();
  const configByHost = new Map(
    conf.members.map(m => [m.host, m])
  );

  const primary = status.members.find(
    m => m.stateStr === "PRIMARY");
  const primaryMs =
    primary?.optimeDate instanceof Date
      ? primary.optimeDate.getTime()
      : null;

  return {
    sampledAt: new Date(),
    replicaSet: status.set,
    term: status.term ?? null,
    members: status.members.map(m => {
      const c = configByHost.get(m.name);
      const appliedMs =
        m.optimeDate instanceof Date
          ? m.optimeDate.getTime()
          : null;

      return {
        host: m.name,
        state: m.stateStr,
        health: m.health,
        votes: c?.votes ?? null,
        priority: c?.priority ?? null,
        syncSourceHost: m.syncSourceHost ?? null,
        lagSeconds:
          m.stateStr === "SECONDARY" &&
          primaryMs !== null &&
          appliedMs !== null
            ? (primaryMs - appliedMs) / 1000
            : null
      };
    })
  };
}

printjson(replicaView376());
```

### 46.1. Limitations

- Represents a single snapshot from the queried member.
- Member states/optimes may not reflect the exact same instant.
- Missing fields can depend on version or member state.
- Never base election decisions solely on this summary.
- Does not replace continuous metrics or quorum verification.

## 47. Checklist for Minimizing Disruption in Java/Spring Boot

### 47.1. Connection Management

- Use one long-lived `MongoClient` with a configured pool.
- URI uses replica set seed hosts or Atlas SRV.
- Never use `directConnection=true` for primary-dependent apps.
- DNS/TLS can reach every advertised member.
- Never hardcode primary hostnames in business code.

### 47.2. Retries and Correctness

- Enable retryable writes/reads where appropriate.
- Enforce idempotency keys in API/order/payment flows.
- Bound retries and request deadlines.
- Handle transaction retries and unknown commit outcomes per driver guidelines.
- Never swallow exceptions and return a fake success.
- Reconcile uncertain outcomes.

### 47.3. Availability

- Ensure health probes do not cause restart storms.
- Size connection pools and apply backpressure.
- Provide graceful degradation for non-critical reads.
- Alert on user-visible failures, not solely database metrics.
- Rehearse failovers in staging.

### 47.4. Security

- Manage credentials and TLS CAs securely.
- Never log raw connection strings or queries containing PII.
- Use least-privilege MongoDB users.
- Do not expose topology on public diagnostic endpoints.

## 48. Simulated Incident: Primary Switches and Orders Are Duplicated

### 48.1. Timeline

```text
10:00:00  Client sends POST /orders with cart X
10:00:01  Backend inserts O1 successfully
10:00:01  Primary steps down; HTTP response lost
10:00:03  Client retries POST /orders
10:00:04  Backend creates O2 from the same cart X
```

### 48.2. Root Cause

The application failed to recognize the two HTTP requests as **the same business intent**.

### 48.3. Remediation

1. Client includes a stable idempotency key on checkout requests.
2. Backend enforces a unique index scoped by tenant/customer.
3. On duplicate requests, look up and return the original order state.
4. Payment/inventory reservation uses protocols preventing double side effects.
5. Return success only once business state is confirmed.

### 48.4. Why Isn't Driver `retryWrites` Enough?

Because the second insert originates from a brand-new HTTP request that may generate a new ID. The driver sees two distinct database operations and has no way to know they represent one checkout attempt.

## 49. Simulated Incident: New Member Is Healthy Yet Clients Cannot Connect

### 49.1. Timeline

```text
mongo-d:
  state=PRIMARY
  health=1

Java service:
  server selection timeout
  TLS hostname mismatch
```

### 49.2. Explanation

The MongoDB cluster elected the new primary, yet the application environment **does not trust its certificate or cannot reach its hostname**.

### 49.3. Action

- Check `rs.conf().members[].host`.
- Test DNS from application Pods/VMs.
- Verify TLS SANs and CA trust.
- Verify firewalls and private endpoints.
- Inspect redacted driver topology logs.
- Verify secrets/auth.

Never weaken TLS validation as a quick fix.

## 50. Simulated Incident: Secondary Becomes Too Stale After Maintenance

### 50.1. Situation

```text
Secondary B offline 6h.
Meanwhile write rate spikes.
Sync source oplog window shrinks to 3h.
```

When B returns, the oplog entries it needs have already been truncated.

### 50.2. Consequence

B reports too-stale / `RECOVERING` and cannot resume incremental replication. It requires an initial sync/resync per deployment procedure.

### 50.3. Operational Lesson

Every rolling maintenance must monitor oplog window/headroom **before, during, and after**. Never rely solely on scheduled calendar hours.

## 51. Simulated Incident: Quorum Lost During Node Replacement

### 51.1. Situation

```text
rsShop has 3 voters:
  A PRIMARY
  B SECONDARY (under maintenance)
  C SECONDARY

While B is offline, C loses network connectivity.
Only A remains reachable.
```

### 51.2. Result

Majority (2/3) is lost. The primary steps down because it no longer satisfies topology conditions for accepting writes.

### 51.3. Better Approach

- Maintain only one member at a time.
- Confirm the previous member is back and caught up before taking the next offline.
- Monitor quorum in real time with stop conditions.
- Spread voters across independent failure domains.
- Never rush to force reconfig on quorum loss.

## 52. Simulated Incident: Lowering Write Concern to "Keep Speed"

### 52.1. Situation

After a stepdown, the application sees higher latency with `w:"majority"` and lowers it to `w:1` without an RPO review.

### 52.2. Consequence

Writes are acknowledged earlier without majority replication. If the primary fails at an inopportune moment, rollback risk rises.

### 52.3. Decision Rule

Never trade away consistency/durability guarantees as an emergency performance tuning step without business sign-off. Analyze secondary apply speed, network, flow control, and workload first.

## 53. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Alternative |
|---|---|---|
| Shutting down primary before checking secondaries | Election may fail | Preflight, quorum, and candidate checks |
| Using `rs.stepDown(..., force)` unconditionally | Risk of unavailability or unsafe writes | Non-forced planned switchover |
| Hardcoding primary IP in Java | Outage after failover | Replica set / SRV URI |
| Using `directConnection=true` in APIs | Lacks full discovery | Driver topology mode |
| Single unreachable seed host | Poor bootstrap/recovery | Multiple seeds/SRV and valid DNS |
| Disabling TLS validation during host changes | Impersonation/MITM risk | Fix CA, SAN, and DNS |
| Treating `health=1` as caught-up data | Promotes stale node | Check optimes and lag |
| Adding a node as voting before initial sync | Election/quorum risk | Add as non-voter first |
| Replacing 2 secondaries simultaneously | Reduced redundancy/quorum | Roll one member at a time |
| Promoting a node without recalculating majority | Majority threshold can rise | Calculate votes before and after |
| Removing a member by array index | Removes the wrong member | Match by verified host/ID |
| Force reconfig to silence alerts | Divergence/rollback risk | Specialist-led recovery runbook |
| Treating an arbiter as a data copy | Misjudged redundancy | Data-bearing members |
| Ignoring delayed/hidden roles | Picks ineligible candidate | Check votes and priority |
| Raising timeouts indefinitely | Hung requests, backlogs | Bounded deadlines and backpressure |
| Retrying all exceptions forever | Retry storm / double writes | Driver eligibility + idempotency |
| Retrying `$inc` as a fresh business command | Double increment | Operation ID / protocol |
| Ignoring transaction retries | Errors / broken business flow | Driver transaction semantics |
| Putting external side effects in retryable callbacks | Duplicate emails/charges | Outbox / idempotency |
| Reading secondaries assuming latest data | Stale reads | Read preference / consistency |
| Treating election completion as app recovery | Clients still erroring | End-to-end SLO checks |
| Restarting all app instances on brief election | Connection storm | Proper health probes |
| Ignoring oplog window during maintenance | Too stale | Monitor headroom |
| Monitoring only average lag | Hides one severely lagging node | Per-member metrics |
| Overlooking config servers in sharding | Metadata outage | Dedicated runbook |
| Rotating certs across all nodes together | Cluster TLS outage | Staged rotation |
| Raising FCV before completing binary upgrades | Incompatibility | Version-specific rolling upgrade |
| Not checking for rollbacks after election | Overlooked data risk | Check write concern, optimes, logs |
| Treating a replica set as a backup | Accidental drops replicate | Backups/PITR and restore drills |

## 54. Hands-On Exercises

### Exercise 1 — Majority

For replica sets with 3, 4, 5, and 7 voting members, calculate the majority and maximum voting members that can be lost while preserving majority.

### Exercise 2 — Choosing a Candidate

Replica set:

```text
A PRIMARY votes1 priority1
B SECONDARY votes1 priority1 lag2s
C SECONDARY votes1 priority0 lag0s
```

If A steps down, can B or C run for primary? Why is lower lag alone insufficient?

### Exercise 3 — Estimating Disruption

An application uses `serverSelectionTimeout` of 2 seconds while elections in the lab often take longer. When will the app throw errors even though the replica set recovers? How should SLOs and retry budgets be designed?

### Exercise 4 — Reading `rs.status()`

Write a `mongosh` script returning host, `stateStr`, `health`, `optimeDate`, and `syncSourceHost`. Why should a `DOWN` member never be reported with `lag=0`?

### Exercise 5 — Optime

Primary and secondary both report last applied oplog time `10:00`, while current wall clock is `11:30`. Is replication lag 90 minutes?

### Exercise 6 — Planned Switchover

Write a pre- and post-checklist for calling `rs.stepDown(60, 15)`. Which steps are read-only and which alter the primary?

### Exercise 7 — Connection Error

After `rs.stepDown()`, `mongosh` reports connection reset. What must be verified before retrying the command?

### Exercise 8 — Force vs. Non-Force

An operator proposes `force:true` because a secondary is lagging by 10 minutes. Analyze durability/rollback risks and propose alternatives.

### Exercise 9 — Replacing a Secondary

Design the steps to replace `mongo-b` with `mongo-d`: add non-voter, initial sync, promote, remove, verify. At which step does majority change from 2/3 to 3/4?

### Exercise 10 — Voting Changes

A cluster has 4 voters with one node `DOWN`. What is the current majority? If a fifth voter is added, what is the new majority? Why must actual live state be included?

### Exercise 11 — Hidden Secondary

A hidden member has `priority: 0` and lag 0. Should you select it as primary during a planned switchover? List changes to consider and why this shouldn't be done mid-incident.

### Exercise 12 — Initial Sync

A new member has stayed in `STARTUP2` for three hours, and the oplog window dropped from 12 hours to 4 hours. Design alerts and investigate network, disk, and write throughput.

### Exercise 13 — Oplog Retention

A secondary is offline for 5 hours while the oplog window is only 2 hours. What can happen when it returns? Why won't increasing Java's server selection timeout solve it?

### Exercise 14 — DNS/TLS

A new primary has a hostname missing from the certificate SAN. The driver reports TLS hostname verification failure. List the proper remediation steps and explain why `tlsAllowInvalidHostnames` must not be used.

### Exercise 15 — Java SDAM

Explain how the driver discovers the primary via replica set membership/`hello`. Compare a replica set URI with `directConnection=true` when the primary changes.

### Exercise 16 — Retryable Writes

Compare the driver retrying a single write with an HTTP client re-sending `POST /orders`. Why does the latter require an idempotency key?

### Exercise 17 — Unknown Write Outcome

An `updateOne` incrementing `available` returns a network timeout. Can you assume it did not apply? Design reconciliation using an operation ID.

### Exercise 18 — Transactions

A transaction contains three updates and a callback sending an email. Why can the callback cause duplicate emails on retry? Propose an outbox pattern.

### Exercise 19 — Read Staleness

After a switchover, an application switches reads to secondaries to reduce errors. Explain read-your-writes risks and options around sessions, read preference, and read concern.

### Exercise 20 — Readiness Probes

A Kubernetes deployment restarts all 200 Pods whenever server selection fails for 3 seconds. Why can this worsen an outage? Propose sensible probes and backoff.

### Exercise 21 — Rolling Maintenance

Cluster has A primary and B/C secondaries. Write a runbook to restart B, wait for catch-up, restart C, and then execute a planned stepdown on A to maintain A.

### Exercise 22 — Certificate Rotation

Rotate the CA for a three-member replica set and Java clients. Draft an overlap trust plan, staged rollout, rollback, and TLS verification.

### Exercise 23 — Multi-Region

Three voting members span two regions: Region A holds two, Region B holds one. When Region A fails, will a new primary be elected in Region B? How would you redesign to survive a region failure?

### Exercise 24 — Sharded Cluster

Distinguish a primary switchover in one shard replica set from a `mongos` or config server replica set failure. Can votes across shards be combined for majority?

### Exercise 25 — Monitoring

Design a timeline dashboard tracking election events, primary availability, Java retry/error rates, p95 latency, replication lag, oplog headroom, and CDC resume errors.

### Exercise 26 — Atlas

An Atlas cluster supports Test Failover on its tier. List what to test on the application side along with stop conditions and approvers.

### Exercise 27 — Insufficient Majority

A three-voter replica set has only one reachable member. Write a safe incident response explaining why force reconfig is not the first step.

### Exercise 28 — Replacing a Live Primary

Suppose current primary A needs hardware decommissioning, B/C are healthy, and a new D is synced. Write the plan for switchover, stepwise promote/remove, rollback, and validation.

### Exercise 29 — Write Concern

Compare `w:1` and `w:"majority"` if the primary dies right after a write. Does a write concern timeout mean the write never happened?

### Exercise 30 — End-to-End Chaos Test

In an authorized staging environment, design a test plan:

1. Run a read/write workload with business request IDs.
2. Capture baseline SLOs.
3. Perform a planned switchover.
4. Measure errors, retries, and latency.
5. Verify no duplicate orders were created.
6. Verify replication and CDC recovery.
7. Document observation limits and lessons learned.

Never run primary-disruption tests in production without approval.

## 55. Decision Workflow for Maintenance Requests

### Step 1 — Define Objective

```text
Switch primary for OS maintenance?
Replace disk?
Upgrade MongoDB binary?
Replace a failed node?
Recover lost quorum?
Rotate certificates?
```

Each objective has a distinct runbook. **Do not treat `rs.reconfig()` as a universal answer for every scenario.**

### Step 2 — Capture True Topology

Collect `rs.status()`, `rs.conf()`, lag, oplog window, voting majority, primary location, candidates, and network status.

### Step 3 — Protect Data

Check majority write concerns, backup/PITR, rollback risks, and active business transactions.

### Step 4 — Protect Applications

Verify driver/SRV/seeds, TLS/DNS, retries, idempotency, application deadlines, and metrics.

### Step 5 — Select Sequence

- Primary switch only: preflight → stepdown → verify.
- Secondary replacement: add non-voter → initial sync → vote transition → remove old.
- Primary replacement: prepare member/candidate → switchover → maintain/remove old.
- Rolling upgrade: secondary by secondary → switchover → old primary, per version procedure.
- Lost quorum: prioritize restoring connectivity/data-bearing members; avoid arbitrary force reconfigs.

### Step 6 — Verify Between Every Step

Do not stop at verifying a command returned `ok: 1`. Inspect cluster state, quorum, lag, application errors, and data integrity.

### Step 7 — Close the Change

Record:

- Primary before/after.
- Membership, votes, and priorities after change.
- Election and client recovery durations.
- SLOs, errors, and retries.
- Backup/rollback evidence.
- Improvements for future operations.

## 56. Production Readiness Checklist

### 56.1. Replica Set

1. All voting members and quorum verified.
2. Healthy, electable primary candidate confirmed.
3. Replication lag and headroom satisfy the maintenance window.
4. No uninvestigated initial sync, `RECOVERING`, or `ROLLBACK`.
5. Backups/PITR and recovery procedures verified.
6. Member versions, FCV, and certificates are compatible.
7. Stop conditions defined before risking quorum.
8. Rollback accounts for ongoing application writes.

### 56.2. Application

1. Replica set/SRV URI used; primary never hardcoded.
2. Driver/monitoring supports topology discovery.
3. TLS/DNS verified for all members.
4. Retryable writes/reads properly enabled.
5. Business idempotency and transaction retries implemented.
6. Bounded connection pools and retry budgets.
7. Health checks do not trigger restart storms.
8. Alerts cover user-visible failures and CDC consumers.

### 56.3. Post-Change

1. Expected primary active via valid configuration/election.
2. Majority votes stable.
3. All expected members healthy.
4. Replication lag and headroom back to baseline.
5. No unexpected rollbacks or data divergence.
6. Application writes and reads succeed.
7. Duplicate or unknown business operations reconciled.
8. Configs, DNS, monitoring, and runbooks updated.

## 57. Summary

**A planned primary switchover is an operational workflow, not a single `rs.stepDown()` command.** Before switching, verify quorum, member states, replication lag, oplog window, and candidate eligibility. Afterward, confirm the election, new primary, return of the former primary, and application service health.

**Safe member replacement preserves redundancy across every step.** Where resources permit, add the new member as non-voting with `priority: 0`, wait for initial sync and catch-up, and transition votes/priorities within reconfiguration constraints before removing the old member. Recalculate majority after **every step**, not just the final state.

**Minimizing connection disruption relies heavily on the client side.** The Java MongoDB driver should connect with a replica set/SRV URI, validate DNS/TLS across all advertised hosts, maintain a stable connection pool, and retry eligible operations. For orders, payments, or inventory, **application idempotency** remains mandatory to avoid duplicating business actions when HTTP requests or transaction callbacks retry.

**Never trade consistency for the illusion that the system "is back up".** `w:"majority"`, election terms, optimes, rollback risk, transaction semantics, backups/PITR, and user-facing monitoring all matter. When quorum is lost, prioritize restoring connectivity and valid data—never force reconfig or drop members just to make commands return success.

A solid runbook helps operators answer: **do we have enough votes, how fresh is the new candidate, who will accept writes, how fast will apps recover, which requests had uncertain outcomes, and what is the next safe step?**

## 58. References

- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): primary election mechanics and eligibility.
- [MongoDB Manual — Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/): `PRIMARY`, `SECONDARY`, `RECOVERING`, and `ROLLBACK` states.
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepdown/): planned primary switchover.
- [MongoDB Manual — replSetStepDown](https://www.mongodb.com/docs/manual/reference/command/replsetstepdown/): stepdown parameters and rules.
- [MongoDB Manual — Add Members to a Replica Set](https://www.mongodb.com/docs/manual/tutorial/expand-replica-set/): adding members and initial sync.
- [MongoDB Manual — Remove Members from a Replica Set](https://www.mongodb.com/docs/manual/tutorial/remove-replica-set-member/): controlled member removal.
- [MongoDB Manual — rs.reconfig()](https://www.mongodb.com/docs/manual/reference/method/rs.reconfig/): configuration updates and voting/quorum caveats.
- [MongoDB Manual — Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/): votes, priority, hidden, and delayed members.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): retention, replication lag, and initial sync.
- [MongoDB Manual — Rollbacks During Replica Set Failover](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/): risks for non-majority-committed writes.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retry semantics.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary routing and stale read behavior.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority durability and timeouts.
- [MongoDB Manual — Upgrade a Replica Set](https://www.mongodb.com/docs/manual/release-notes/upgrade/): version-specific upgrade procedures.
- [MongoDB Atlas — Test Failover](https://www.mongodb.com/docs/atlas/tutorial/test-failover/): testing resilience on managed clusters.
- [MongoDB Java Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/): topology, timeouts, and retry options.
