# Distributing Members Across Failure Domains and Testing Member Loss in a MongoDB Replica Set

A MongoDB Replica Set stores multiple copies of data and uses a **primary election** mechanism to preserve write capability when a member becomes unavailable. Yet having three members does not automatically mean the system will survive losing a server, Availability Zone (AZ), or Region. If all sit in one failure domain, a single shared incident can knock out the entire replica set.

Proper design and testing require distinguishing:

1. **Failure domain:** which members can fail simultaneously from the same root cause?
2. **Election quorum:** after an incident, does a voting majority remain to elect or maintain a valid primary?
3. **Data copies and applications:** do enough data-bearing members remain to satisfy write concern, and does the application recover properly after failover?

This lesson explains how to distribute a replica set across hosts/racks/AZs/Regions, calculate majority, choose 3- or 5-member topologies, understand arbiter and non-voting member limits, and build runbooks to test **secondary loss, primary loss, full AZ loss, and network partitions**. Examples use **mongosh** and the **MongoDB Java Sync Driver**.

**Safety scope:** Never run node-stopping, network-isolating, or primary-switching commands on a real system without authorization. Fault-injection steps are strictly for lab/staging or approved production game days with telemetry, abort thresholds, and rollback plans.

## 1. Fault Tolerance Must Be Defined by Failure Domain

A three-member replica set can be deployed in three ways:

**Case A – three processes on one host:**

~~~text
Host-01
├── mongod-1
├── mongod-2
└── mongod-3
~~~

Losing one process leaves the others, yet losing Host-01 takes all three down.

**Case B – three hosts in one AZ:**

~~~text
AZ-A
├── Host-01: mongod-1
├── Host-02: mongod-2
└── Host-03: mongod-3
~~~

Tolerates independent host failures, yet an AZ-A-wide outage takes all three down.

**Case C – three independent AZs:**

~~~text
Region R1
├── AZ-A: mongod-1
├── AZ-B: mongod-2
└── AZ-C: mongod-3
~~~

With three voting data members, losing one AZ leaves two votes; mathematically majority still holds. You additionally need the two remaining nodes to reach one another and include a valid primary candidate.

### 1.1. Failure Domains Are Not Just Geographic Locations

Failure domains can be:

| Failure Domain | Examples |
| --- | --- |
| Process | `mongod` crash or OOM |
| Host / VM | kernel panic, disk failure, hypervisor error |
| Rack | power loss, top-of-rack switch failure |
| Storage domain | backing volume failure or shared storage service outage |
| Availability Zone | relatively independent infrastructure cluster |
| Region | regional outage or inter-region link failure |
| Network | routing, firewall, DNS, certificates |
| Control plane | simultaneous faulty rollout or secret rotation |

Three VMs across three AZs can still suffer a correlated config outage if a policy is rolled out simultaneously everywhere. **Multi-AZ reduces correlated risk; it does not eliminate all correlated risk.**

### 1.2. RTO and RPO

- **RTO:** maximum service disruption time acceptable to the business.
- **RPO:** maximum data loss acceptable under business objectives.

A replica set can elect a new primary, yet election and client discovery are not instantaneous. Therefore measure how long until the application **actually resumes writing**, rather than checking only that the server side has a PRIMARY.

A replica set also does not automatically guarantee every write survives failover. You must evaluate **write concern** and replication state.

## 2. Member Roles

| Member | Holds Data? | Contributes Vote? | Can Become Primary? |
| --- | --- | --- | --- |
| Primary | Yes | Per config | Currently primary |
| Normal secondary | Yes | Per config | Possible, if eligible |
| Arbiter | No | Yes | No |
| Hidden secondary | Yes | Can | Usually no due to priority = 0 |
| Delayed secondary | Yes, applied with delay | Depends on config | Not treated as normal candidate |
| Non-voting secondary | Yes | No | No |
| Priority-0 secondary | Yes | Can | No |

Three attributes to keep distinct:

- **votes:** contributes to primary election quorum.
- **priority:** relative preference and eligibility to become primary.
- **data-bearing:** actually stores collections and oplog.

A **priority: 0, votes: 1** secondary still casts a vote yet cannot be elected primary. A non-voting secondary still stores data yet does not increase voting majority. An arbiter holds a vote yet stores no data copy.

## 3. Calculating Majority

With **V voting members**, the required vote count is:

\[
Q = \left\lfloor\frac{V}{2}\right\rfloor + 1
\]

If a failure domain loses **L voters**, the condition to retain quorum is:

\[
V - L \ge Q
\]

| Voters V | Majority Q | Maximum voters lost while keeping majority? |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Replica sets are usually designed with an odd voter count such as **3 or 5**. MongoDB caps voting member count; when scaling topology, follow version-specific documentation rather than merely adding processes.

### 3.1. Majority Is Necessary, Not Sufficient

To have a writable primary after a failure, you need:

1. A remaining majority of reachable voters.
2. At least one **eligible data-bearing member** to elect primary.
3. Valid election conditions and replication freshness.
4. Clients able to connect to the new primary.

If only arbiters and `priority = 0` members remain, you cannot assume a primary will exist even if the vote count looks sufficient.

### 3.2. Election Majority Differs from Majority Acknowledgment

An arbiter can help reach majority **votes**, yet cannot confirm storing a write on disk because it holds no data copy. When evaluating **w: "majority"** capability, inspect data-bearing members and topology write concern rules.

## 4. Topology of Three Data-Bearing Voters Across Three AZs

~~~text
AZ-A: mongo-a  (data-bearing, voting, electable)
AZ-B: mongo-b  (data-bearing, voting, electable)
AZ-C: mongo-c  (data-bearing, voting, electable)

V = 3, Q = 2
~~~

| Incident | Remaining Voters | Quorum | Likely Behavior |
| --- | ---: | --- | --- |
| Loss of AZ-A | 2 | Yes | Two remaining members can elect primary |
| Loss of AZ-B | 2 | Yes | Retains majority |
| Loss of AZ-C | 2 | Yes | Retains majority |
| Loss of two AZs | 1 | No | Insufficient votes to elect primary |
| Loss of one independent host | 2 | Yes | Retains quorum if the two nodes communicate |

If mongo-a is PRIMARY and AZ-A fails, mongo-b/mongo-c can elect a new primary. During the election, application writes may time out or receive transient errors.

If an AZ holding only a secondary fails, the primary can continue serving, yet the cluster now sits at **exact majority**; one more failure can lose quorum.

## 5. Topology of Three Voters Placed 2–1 Across Two AZs

~~~text
AZ-A: mongo-a, mongo-b  (2 voters)
AZ-B: mongo-c           (1 voter)

V = 3, Q = 2
~~~

- Loss of AZ-B → two voters remain, quorum holds.
- Loss of AZ-A → one voter remains, **quorum is lost**.

This is an asymmetric fault-tolerance layout. It tolerates single-host failure yet **cannot tolerate losing any arbitrary AZ**.

Placing a high-priority primary in AZ-B does not fix this: one voter is still one voter. **Priority never changes majority vote counts.**

## 6. Topology of Five Voters Placed 2–2–1

~~~text
AZ-A: mongo-a1, mongo-a2
AZ-B: mongo-b1, mongo-b2
AZ-C: mongo-c1

V = 5, Q = 3
~~~

| Lost AZ | Lost Voters | Remaining Voters | Majority Met? |
| --- | ---: | ---: | --- |
| AZ-A | 2 | 3 | Yes |
| AZ-B | 2 | 3 | Yes |
| AZ-C | 1 | 4 | Yes |

A **2–2–1** layout satisfies quorum when losing any single AZ, provided no shared dependencies take out extra nodes.

### 6.1. A 3–1–1 Layout Is Not Equivalent

~~~text
AZ-A: 3 voters
AZ-B: 1 voter
AZ-C: 1 voter

V = 5, Q = 3
~~~

If AZ-A fails, only **2/5 voters** remain. Majority is lost.

Thus, **five nodes are not better than three nodes for surviving single-AZ loss if votes are poorly distributed**.

### 6.2. When Arbiters or Non-Voting Members Exist

Do not equate five processes with five data copies. Inventory **voters** and **data-bearing members** separately. Some topologies keep quorum yet lose all candidates or fail to satisfy majority writes as expected.

## 7. Trade-Offs of Multi-Region Distribution

Spreading across multiple Regions reduces single-Region outage risk while increasing:

- Inter-copy latency.
- Cross-Region replication data transfer costs.
- Latency for majority-acknowledged writes.
- Risk of inter-Region network partitions.
- Complexity of application routing, secrets, DNS, and service dependencies.

**Three Regions 1–1–1:** losing one Region leaves 2/3 voters, keeping quorum if the remaining two Regions connect.

**Two Regions 3–2:** losing the three-voter Region leaves 2/5, lacking quorum. This topology does not survive losing any Region.

**Three Regions 2–2–1:** with five voters, losing any Region leaves at least three voters. Yet quorum is only the math; latency and write acknowledgment behavior must be measured.

### 7.1. Preferring Primary Close to Writers

You can configure priority to prefer a primary near the main write-issuing application. Avoid aggressive priority configurations that trigger leader churn. If the preferred Region fails, eligible primary candidates must still exist in surviving Regions.

Never use priority as a substitute for quorum design.

### 7.2. Multi-Region Is Not Yet Complete Disaster Recovery

If MongoDB fails over successfully yet applications, DNS, payment services, or credentials live only in the lost Region, users still cannot operate.

DR must encompass backups, restores, service routing, dependencies, and system-wide procedures.

## 8. Arbiter: A Vote Without Data

**Primary–Secondary–Arbiter (PSA)** model:

~~~text
AZ-A: PRIMARY   (has data)
AZ-B: SECONDARY (has data)
AZ-C: ARBITER   (no data)

3 voters, 2 data-bearing
~~~

An arbiter can cast a vote in elections, yet:

- Stores no collections/oplog like a data-bearing member.
- Provides no third copy of data.
- Serves no data reads.
- Cannot be elected primary.
- Does not replace backups.

When the data-bearing secondary fails, the remaining primary plus arbiter may hold enough election votes, yet majority write concern faces limits due to lacking the required data copies.

For strong HA and durability, **three data-bearing members across three failure domains** are usually preferred over PSA when resources permit.

## 9. Hidden, Delayed, Priority-0, and Non-Voting Secondaries

**Hidden secondary** stores data yet is excluded from normal client read selection. Hidden normally must have priority = 0 and may still hold a vote.

**Delayed secondary** applies the oplog with intentional lag. It should not be treated as a current copy ready for immediate primary election. Check priority/votes constraints for your version and actual configuration.

**Non-voting secondary** holds data yet has votes = 0, so it does not increase election quorum.

**Priority-0 secondary** cannot become primary even if it contributes a vote. If only priority-0 nodes and arbiters survive a disaster, no valid writable primary candidate exists.

When designing, maintain a table:

~~~text
Member | Host | Rack | AZ | Region | Votes | Priority
Data-bearing | Hidden | Delayed | Role | Replication lag
~~~

## 10. Write Concern Majority and Data Loss Risk

Example write probe:

~~~javascript
db.haProbe.insertOne(
  {
    _id: "RUN-231-BASE-001",
    ts: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**w: "majority"** requests majority acknowledgment per write concern rules and active topology; **wtimeout** bounds how long to wait for acknowledgment.

### 10.1. Non-Majority-Acknowledged Writes Can Roll Back

If the primary accepts a write and returns a weaker acknowledgment before required secondaries receive it, and the primary fails, the new primary may not have that write. When the old primary returns, it may have to roll back non-majority-confirmed history.

In tests, separate:

~~~text
Write sent
Write applied on primary
Write acknowledged with w:1
Write acknowledged with w:majority
Write timed out or uncertain outcome
Write still present after failover
~~~

Never report RPO from a single "total successful requests" count if acknowledgment levels differ.

### 10.2. `wtimeout` Does Not Prove the Write Did Not Happen

When majority confirmation is not reached before timeout, the client may not know whether the primary applied the write. Never blindly retry arithmetic adjustments as a brand-new business command if it could duplicate effects.

### 10.3. Election Majority and Data Copies Must Be Evaluated Separately

An arbiter has a vote yet holds no data. A non-voting secondary holds data yet contributes no vote. Thus, designs must evaluate **quorum, election candidates, and write replication levels** as distinct conditions.

## 11. Read Preference During Failover

An application can read with:

| Read preference | General Behavior |
| --- | --- |
| **primary** | Read from primary only |
| **primaryPreferred** | Prefer primary |
| **secondary** | Read from secondary only |
| **secondaryPreferred** | Prefer secondary |
| **nearest** | Select member with suitable latency |

When no primary exists during an election, **primary** read preference may error or wait. When all eligible secondaries are lost, **secondary** read preference may error even while the primary runs.

Reading from secondaries can return stale data due to replication lag. For read-your-writes or stronger consistency, design read concern, sessions, and causal consistency properly.

## 12. Preflight Before a Member-Loss Test

In `mongosh`:

~~~javascript
rs.status();
~~~

Inspect configuration:

~~~javascript
rs.conf();
~~~

Inspect node status:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Optionally inspect replication info:

~~~javascript
rs.printSecondaryReplicationInfo();
~~~

Exact output fields vary by version. Information to verify includes:

- Current primary.
- Members and state/health.
- Votes/priority/hidden/delayed.
- Replication lag, oplog window.
- Which AZ/Region each member belongs to.
- Client read/write configurations.

### 12.1. Preflight Table

| Item | Pre-Test Condition |
| --- | --- |
| Primary | Stable, not oscillating through elections |
| Voting members | No pre-existing failures outside test scope |
| Secondaries | Acceptable replication lag |
| Oplog | Sufficient window for planned outage duration |
| Monitoring | Collecting both database and API metrics |
| Recoverability | Authorized to bring nodes/network back up |
| Backups | Recovery mechanisms ready per environment rules |
| Ongoing changes | No concurrent rollouts adding failure risk |
| Coordinator | Designated observer and abort criteria |

Never intentionally drop another voter if the cluster is already degraded down to **exact majority**.

## 13. Building a Workload Probe

A single successful ping does not prove the replica set has a primary and working majority writes. Maintain a dedicated probe collection:

~~~javascript
use ha_test_lab

db.probe.insertOne(
  {
    _id: "RUN231-PROBE-001",
    createdAt: new Date(),
    kind: "baseline"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

In prolonged tests, log:

- Fixed `requestId` for each business operation.
- Request send and response timestamps.
- Read/write type.
- Read concern, read preference, and write concern.
- Latency and error codes.
- Observed primary/client topology.
- Post-failover data verification outcomes.

### 13.1. Why Is a Continuous Probe Needed?

Running just one write before the incident and one write afterward tells nothing about how long the application was disrupted.

A probe at a controlled cadence, e.g., once per second, lets you estimate the duration from fault injection until new requests succeed again.

### 13.2. Distinguishing Unknown Outcomes from Confirmed Failures

If a network timeout occurs after sending a write, the client cannot know whether the server applied it. Reconcile by `requestId` before retrying at the business layer.

## 14. Scenario A: Losing a Secondary

Initial topology:

~~~text
AZ-A: mongo-a PRIMARY
AZ-B: mongo-b SECONDARY
AZ-C: mongo-c SECONDARY
~~~

Take **mongo-b** offline in lab/staging.

### 14.1. Expectations

- mongo-a and mongo-c retain 2/3 votes.
- Primary can keep its role.
- Majority writes can still acknowledge with enough data-bearing members.
- Clients connecting directly to mongo-b error; apps using appropriate read preferences can pick another source.
- When mongo-b returns, it must catch up on replication.

### 14.2. Runbook

1. Record `rs.status`, `rs.conf`, replication lag.
2. Start majority write and read probes.
3. Stop **only mongo-b** via authorized tooling.
4. Observe primary and errors/latency.
5. Restart mongo-b.
6. Wait until it returns to healthy secondary and catches up on the oplog.
7. Reconcile probes and close the test.

A restarted process **is not necessarily finished syncing data yet**.

## 15. Scenario B: Losing the Primary

~~~text
Before:
mongo-a PRIMARY
mongo-b SECONDARY
mongo-c SECONDARY

During failure:
mongo-a unavailable
mongo-b, mongo-c retain majority
~~~

An eligible secondary can be elected as the new primary.

### 15.1. Observation Timeline

~~~text
T0  primary loses connectivity
T1  remaining members detect change
T2  election finishes, new primary appears
T3  driver selects the new primary
T4  API majority writes succeed again
T5  old primary returns and finishes syncing
~~~

**Application RTO extends to T4, not just T2.** The driver still needs topology discovery, connection pool refresh, and retries.

### 15.2. Controlled Step-Down in Lab

To test role transfer while connected to the primary:

~~~javascript
rs.stepDown(60, 10);
~~~

This command can drop sessions and succeeds only when conditions permit. It tests **leader transition**, which is not identical to an actual host/AZ outage.

Never force step-down or force reconfig during tests without understanding quorum and data state.

### 15.3. Verify Outcomes

After election, verify:

- Only a valid primary exists per topology.
- API majority writes work again.
- Pre-failure majority-acknowledged data still exists.
- Timed-out requests caused no business duplicates.
- Returning old member syncs properly.

## 16. Scenario C: Losing an Entire AZ

If the goal is AZ fault tolerance, tests must cover **all voting members inside that AZ**, not just one process.

Example three voters across three AZs:

~~~text
AZ-A: mongo-a PRIMARY
AZ-B: mongo-b SECONDARY
AZ-C: mongo-c SECONDARY
~~~

Losing AZ-A → 2/3 votes remain. Losing AZ-B → primary in AZ-A retains quorum with AZ-C.

Yet if AZ-A holds **two voters** in a 2–1 layout, losing all of AZ-A leaves the other side without majority.

### 16.1. Client Routing Must Be Checked

The cluster having a new primary is not enough if:

- Clients are only allowed to reach hosts in the lost AZ.
- DNS/firewalls block traffic to surviving AZs.
- Needed secrets or certificates become unavailable.
- Applications depend on other services hosted inside the failed AZ.

Test from **the same network as the application**, not just from a DBA workstation.

### 16.2. Abort Conditions

Halt fault injection immediately if a second AZ becomes unhealthy, API errors exceed thresholds, replication lag spikes excessively, or rollback capability is endangered. Never push through a fault scenario at all costs.

## 17. Scenario D: Network Partition

A network partition can leave nodes running yet unable to reach a majority.

~~~text
Side A: mongo-a
Side B: mongo-b <-> mongo-c

V = 3, majority = 2
~~~

Side B has quorum. Side A cannot elect a new primary; the isolated old primary cannot sustain stable writability once it loses majority per election rules.

### 17.1. Measure from Both Sides

- Does the majority side have a primary and working majority writes?
- How does the minority side behave without quorum?
- Which server selection/network/write concern errors do minority-side clients hit?
- When the network heals, how do members converge onto one valid history?
- Did any non-majority-acknowledged writes have to roll back?

`rs.status` output from one node reflects **only that node's perspective**, not the whole partition. Collect logs and telemetry from multiple sides when possible.

### 17.2. Never Randomly Partition Production

Network partitioning can trigger mass timeouts, elections, and retry storms. Test only with reliable network-revert tooling, on-call staff, and strict abort thresholds.

## 18. Scenario E: Already-Degraded Cluster Loses Another Voter

~~~text
Initially: 3 voters
mongo-a healthy
mongo-b healthy
mongo-c offline

2/3 remain -> exact majority
~~~

If mongo-b also fails next:

~~~text
Only mongo-a remains
1/3 lacks majority
~~~

A cluster with a current primary may lack redundancy for another fault.

Standard operational rules:

- Pause maintenance that takes another voter offline.
- Recover the failed member first.
- Check oplog window so the offline node can still catch up.
- Monitor replication lag and network errors.
- Resume rollouts only after redundancy returns, per approved policy.

## 19. Measuring Failover Duration from the Application

A test report should record:

~~~text
T0: fault injection starts
T1: old primary becomes unusable
T2: new primary elected
T3: driver discovers new topology
T4: application majority write succeeds
T5: failed member returns and finishes syncing
~~~

Two metrics:

- **Server election duration:** measures primary election behavior.
- **Application recovery duration:** measured from failure onset until the API serves again per criteria.

### 19.1. Sample Report Table

| Metric | Baseline | During Failure | After Recovery |
| --- | --- | --- | --- |
| Reachable voters | 3/3 | 2/3 | 3/3 |
| Primary | mongo-a | Elected mongo-b | Stable |
| Majority write p95 | 20 ms | May time out | 22 ms |
| Driver errors | None | Transient | Resolved |
| Replication lag | Low | Failed node lagging | Shrinking |
| Majority acknowledged probes | Complete | Monitored | Reconciled |
| Duplicate business requests | None | None if idempotent | None |

**Latency figures are illustrative examples only**, not MongoDB performance guarantees.

### 19.2. Do Not Lump All Errors Into "MongoDB Down"

Distinguish no writable primary, server selection timeout, network timeout, write concern error, transient transaction errors, unknown commit result, and application HTTP timeouts. Recovery and retry behavior differ for each.

## 20. Connection String and Driver Discovery

Illustrative replica set URI:

~~~text
mongodb://mongo-a.example.net:27017,mongo-b.example.net:27017,mongo-c.example.net:27017/?replicaSet=rs0&retryWrites=true
~~~

Key conditions:

1. Every hostname advertised by MongoDB must resolve from the client.
2. Clients can reach nodes in surviving zones.
3. Exact `replicaSet` name.
4. Compatible TLS/auth/firewalls.
5. Driver is permitted to discover topology and the new primary.

If an application forces **`directConnection=true`** to the old primary, failover behavior will not match a full replica set connection.

### 20.1. Timeouts Are Part of Your SLO

Too short a server selection timeout fails requests before the cluster finishes elections. Too long a timeout causes requests to pile up.

Measure real failover to choose driver and HTTP API timeouts. No single set of numbers fits every application.

### 20.2. Retryable Writes Do Not Replace Idempotency

If the response drops after the server creates an order, retrying at the business layer with a new `orderId` creates a duplicate order, even though MongoDB drivers support retryable writes for eligible operations.

A business idempotency key helps distinguish a retried request from a brand-new request.

## 21. Java Sync Driver: Majority Write Probe

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Date;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public class ReplicaSetFailoverProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing replica set MONGODB_URI"
            );
        }

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToClusterSettings(builder ->
                        builder.serverSelectionTimeout(
                                15, TimeUnit.SECONDS
                        )
                )
                .writeConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                                10, TimeUnit.SECONDS
                        )
                )
                .readConcern(ReadConcern.MAJORITY)
                .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> probe = client
                    .getDatabase("ha_test_lab")
                    .getCollection("probe");

            String requestId = "HA-" + UUID.randomUUID();

            Document event = new Document("_id", requestId)
                    .append("createdAt", new Date())
                    .append("type", "majority-probe");

            long started = System.nanoTime();

            probe.insertOne(event);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started
            );

            System.out.println(
                    "requestId=" + requestId
                    + ", elapsedMs=" + elapsedMs
            );
        }
    }
}
~~~

A single successful probe is insufficient to evaluate failover. In real tests, run operations at a bounded cadence and log success/error/latency across the entire outage.

### 21.1. Preserve `requestId` When Retrying the Same Business Operation

The UUID in the example is generated **once per new probe**. When retrying **the same business request**, preserve the generated ID; never generate a fresh UUID on every retry and expect the database to deduplicate automatically.

### 21.2. Handling Unknown Outcome Errors

~~~java
try {
    probe.insertOne(event);
} catch (com.mongodb.MongoException e) {
    System.err.println("Mongo code: " + e.getCode());
    System.err.println("Message: " + e.getMessage());

    // Do not assume the write did not occur on timeout.
    // Check status by requestId.
    throw e;
}
~~~

With transactions, handle labels such as **TransientTransactionError** and **UnknownTransactionCommitResult** per driver guidelines.

## 22. Recovering Members After Testing

A recovery procedure:

1. Revert the faulted network/process condition.
2. Verify the member rejoins the replica set.
3. Check state and health.
4. Monitor replication lag and oplog catch-up.
5. Determine whether initial sync is needed.
6. Reconcile majority-acknowledged data.
7. Confirm application errors have stopped.
8. Close the test only once redundancy returns.

### 22.1. Online Node Does Not Mean Synced

If a node was offline longer than the usable oplog window, it may need initial sync. An open port and ping response do not mean it is a fully caught-up secondary.

### 22.2. Old Primary May Remain a Secondary

After failover, the new primary may keep its role when the old primary returns. Avoid forcing another primary switch merely to restore initial appearances, as that adds unnecessary disruption.

### 22.3. Force Reconfig Carries Risk

When majority is lost, do not arbitrarily alter votes, force reconfigure, or wipe a node's data to force the cluster up. Know member states, partition causes, and version-appropriate DR procedures with backups and proper approval.

## 23. Replica Sets Do Not Replace Backups

A valid yet business-wrong deletion:

~~~javascript
db.orders.deleteMany({
  status: "PAID"
});
~~~

can replicate to every secondary. All three AZs remain healthy, yet the documents are deleted across all copies.

Backup/PITR provides point-in-time recovery, not a capability fully replaced by replica sets.

Check:

- Are backups stored in an independent failure domain?
- Are restores tested periodically?
- Are encryption keys and credentials available if a Region fails?
- Are retention and accidental-delete protections enabled?
- Do backup RTO/RPO meet business needs?

## 24. Local Labs vs. Real Failure Domain Testing

A three-container replica set on one machine lets you learn elections yet cannot prove host-loss tolerance:

~~~text
One host
├── mongo-a
├── mongo-b
└── mongo-c
~~~

Illustrative lab config:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    {
      _id: 0,
      host: "mongo-a.lab.example:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 1,
      host: "mongo-b.lab.example:27017",
      votes: 1,
      priority: 1
    },
    {
      _id: 2,
      host: "mongo-c.lab.example:27017",
      votes: 1,
      priority: 1
    }
  ]
});
~~~

The hostnames above are placeholders and must be replaced with addresses resolvable by all members and clients, with appropriate TLS/auth/network/storage.

To validate AZ loss, nodes must reside in independent AZs or an environment faithfully simulating those dependencies.

## 25. End-to-End Game Day Runbook

### Phase A – Preparation

- Define secondary/primary/AZ/partition loss scenario.
- Lock down topology and votes/priority/data-bearing table.
- Calculate post-incident quorum.
- Verify backups and oplog window.
- Collect baseline metrics.
- Define probe workload.
- Document abort thresholds and on-call owners.
- Ensure ability to revert faults from an outside failure domain.

### Phase B – Controlled Fault Injection

- Record T0 and target node/failure domain ID.
- Inject only the approved fault.
- Watch `rs.status`, election logs, and replication.
- Log client success/error/latency.
- Abort immediately if blast radius or safety thresholds are exceeded.

### Phase C – Recovery

- Revert network/process fault.
- Confirm member returns to appropriate state.
- Monitor replication catch-up/initial sync.
- Verify majority-acknowledged writes and check for duplicates.
- Confirm API stabilizes and redundancy is restored.

### Phase D – Report

~~~text
Scenario:
Replica set:
Members per AZ/Region:
Voting majority:
Fault injected at:
Primary elected at:
API write restored at:
RTO measured:
Write concern errors:
Replication recovery:
Data reconciliation:
Unexpected duplicates/rollbacks:
Pass / Fail:
Actions:
~~~

Never mark a test **PASS** simply because a new primary exists while applications still time out or redundancy has not recovered.

## 26. Common Mistakes

| Mistake | Explanation |
| --- | --- |
| Having 3 `mongod`s means surviving AZ loss | Must verify whether they share AZ/rack/host |
| Using process count to compute majority | Must use voting members |
| Preferring primary via priority instead of vote placement | Priority does not increase quorum |
| Treating an arbiter as a data copy | Arbiters store no data |
| Assuming priority-0 means non-voting | Priority differs from votes |
| Thinking non-voting secondaries raise election majority | `votes: 0` does not participate in quorum |
| Assuming 5 voters in 2 Regions survive any Region loss | 3–2 fails if the 3-voter Region goes down |
| Equating election majority with majority writes | Must evaluate data copies and write concern |
| Thinking `wtimeout` proves the write did not run | Outcome may still be uncertain |
| Assuming new primary equals recovered API | Drivers still must discover and connect |
| Pinging one `mongod` proves cluster health | Ping checks neither quorum nor majority writes |
| `stepDown` simulates full AZ loss | Tests primary transfer only |
| Three containers on one host equal three failure domains | Still share one host |
| Online node means caught up on oplog | Must monitor replication |
| Retrying after timeout is always safe | Requires idempotency |
| Treating replica set as backup | Erroneous deletes replicate too |
| Force reconfig is normal quorum repair | Carries data risks if misused |

## 27. Hands-On Exercises

### Exercise 1 – Three Voters Across Three AZs

~~~text
AZ-A: 1 voter
AZ-B: 1 voter
AZ-C: 1 voter
~~~

Calculate majority; how many voters remain if one AZ is lost? If remaining members are data-bearing eligible members and networking is healthy, can a primary be elected?

### Exercise 2 – Three Voters 2–1

~~~text
AZ-A: 2 voters
AZ-B: 1 voter
~~~

Compare losing AZ-A, losing AZ-B, and losing just one host in AZ-A. Why does this topology fail the requirement to survive losing any AZ?

### Exercise 3 – Five Voters 2–2–1 and 3–1–1

Calculate remaining voters when each AZ fails. Explain why 2–2–1 has better quorum properties than 3–1–1 for surviving single-AZ loss.

### Exercise 4 – PSA

An arbiter, a data primary, and a data secondary across three AZs. How many data copies exist? If the data secondary is lost, how do remaining votes and `w:majority` acknowledgment capability differ?

### Exercise 5 – Losing Primary in the Lab

1. Collect `rs.status`.
2. Run majority write probes.
3. Run controlled `stepDown` or take primary offline in an authorized environment.
4. Measure time until a new primary exists.
5. Measure time until the client writes successfully again.
6. Recover the node and inspect replication.

Explain why times in steps 4 and 5 can differ.

### Exercise 6 – 1–2 Network Partition

Three voters split into a one-node group and a two-node group. Which side holds quorum? Can the one-node side continue majority writes? When the network heals, what data and logs must be inspected?

### Exercise 7 – Already-Degraded Cluster

Three voters, one offline. Maintenance plans to restart a second voter. Calculate majority after the restart and decide whether to proceed.

### Exercise 8 – Duplicate Order Due to Retry

A client sends an order and times out right after the server writes it. The client retries with a new ID and creates a second order. Design a fixed business request ID, unique index, or upsert/idempotency check to avoid duplicates.

### Exercise 9 – Multi-Region

Compare 3 voters 1–1–1 with 5 voters 2–2–1 across three Regions. Analyze quorum, majority write latency, network partitions, and cost.

### Exercise 10 – Backups

An erroneous `deleteMany` replicates across all secondaries. Why can the replica set not restore the pre-delete version on its own? Design backup/PITR and restore testing.

### Exercise 11 – Inventory Table

Build a table with host, rack, AZ, Region, votes, priority, data-bearing, hidden, delayed, and replication lag. From the table, compute votes lost when each failure domain is isolated.

### Exercise 12 – Write a Runbook

Draft a test procedure for losing the AZ holding the primary: preflight, probe, injection, metrics, abort criteria, recovery, reconciliation, and measured RTO/RPO report.

## 28. Pre-Production Design Checklist

1. Identify all relevant failure domains.
2. Document placement of every voting and data-bearing member.
3. Calculate majority after losing each failure domain.
4. Confirm valid primary candidates remain.
5. Verify majority write capability with surviving copies.
6. Measure replication lag and cross-AZ/Region latency.
7. Verify driver URI, DNS, firewalls, TLS, and auth.
8. Define realistic SLO/RTO/RPO.
9. Design retries/idempotency.
10. Instrument server, client, and application monitoring.
11. Test secondary, primary, AZ, and partition loss.
12. Prepare network/process revert procedures.
13. Maintain independent backups/PITR and test restores.
14. Measure acknowledged data and duplicates post-failure.
15. Close tests only once members restore full redundancy.

## 29. Conclusion

A replica set is fault-tolerant when members are **properly distributed across failure domains** and after an incident the following remain:

- **Election majority** of voting members.
- An eligible **data-bearing candidate** to act as primary.
- Capability to **replicate and acknowledge writes** as required.
- Clients able to discover the new primary and retry safely.

With three data-bearing voters across three AZs, losing one AZ still leaves 2/3 votes. With five voters placed 2–2–1, losing one AZ leaves at least 3/5 votes. Conversely, 2–1 or 3–1–1 layouts concentrate too many votes in one failure domain.

Proper testing does not stop at **`rs.status` reporting a new primary**. Inject faults under control, measure recovery time at the application layer, protect majority-acknowledged writes, verify idempotency, recover members, and watch replication until redundancy returns. Finally, **a replica set never replaces backups or disaster recovery**.

## References

- [MongoDB Manual — Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/)
- [MongoDB Manual — Hidden Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-hidden-member/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.conf()](https://www.mongodb.com/docs/manual/reference/method/rs.conf/)
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
