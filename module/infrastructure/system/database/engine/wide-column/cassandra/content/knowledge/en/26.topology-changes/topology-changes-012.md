# Coordinating Topology Changes While Java Driver Refreshes Metadata

> **Chapter:** Topology Changes  
> **Scope:** Distributed Apache Cassandra, especially bootstrap, decommission, removenode, and node replacement; impacts on gossip, token ranges, streaming, read/write consistency levels, and Java Driver 4.x. This lesson emphasizes **coordinating timing** between cluster changes and driver metadata refreshes, rather than treating a node-UP notification as a sign that data is completely ready.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **ring/topology**, **gossip and liveness**, **streaming progress**, and **driver metadata/token map**; explain why these four views can update at different times.
2. Describe how the Java Driver uses its **control connection**, add/remove/UP/DOWN events, **debouncing**, `session.getMetadata()` snapshots, and token-aware load balancing.
3. Build a safe operation sequence when **adding a node**, **retiring a healthy node**, **removing a dead node**, or **replacing a failed node**, with verification gates before advancing.
4. Know why **`NodeState.UP` does not prove bootstrap is complete**, and why a fresh metadata snapshot does not guarantee replicas have synchronized data.
5. Monitor the driver, Cassandra, and Java applications concurrently; evaluate CL, latency, timeout, reconnect, schema agreement, and retry risks during topology changes.
6. Practice inspecting token maps, node states, and query paths using CQL, `nodetool`, and the Java Driver.

This continues the **distributed wide-column** model: the partition key determines the token, the replication strategy determines natural replicas, and the consistency level (CL) determines how many replicas must respond. **The driver picks a suitable coordinator**; Cassandra itself executes and maintains replicas. When topology shifts, both sides must converge, yet they do not necessarily update at the exact same instant.

## 2. Four Distinct Views of a Topology Change

Suppose a keyspace has RF=3 in a datacenter. The cluster currently has three nodes A/B/C and is about to add node D to distribute token ranges and load better.

~~~text
              Event: preparing to bootstrap node D

    Cluster/server                        Java application
    ─────────────────────────────────────────────────────────
    Ring: token ranges                    Driver Metadata #1:
      A B C                               A B C
        │                                    │
        ▼                                    │
    D discovered via gossip                  │
    D begins streaming                       │
        │                                    ▼
        │                            topology event / refresh
        │                                    │
        ▼                                    ▼
    D received full data                 Driver Metadata #2:
    and enters NORMAL state             A B C D + updated token map
        │                                    │
        └───────── check convergence ────────┘
                 before opening next step
~~~

This diagram **does not enforce a strict chronological order**: the driver may learn about D while D is still joining, while another app updates later due to a dropped control connection or debouncing; metadata state can also change before/after streaming steps.

| View | Observation Source | What It Answers | What It Does Not Prove |
|---|---|---|---|
| **Token ring and node lifecycle** | `nodetool status`, `nodetool ring`, gossip info | Is the node JOINING/NORMAL/LEAVING? Who owns which tokens/ranges? | That all replicas are synced or apps know the new ring |
| **Streaming and data** | `nodetool netstats`, logs, repair, `tablestats` | How are bootstrap/decommission/replace transferring data? | That the driver updated query plans or all data matches business state |
| **Java Driver metadata** | `session.getMetadata()`, NodeStateListener, token map | Which nodes, host IDs, states, token ranges, and schema does the driver see? | That the server finished moving data |
| **Application experience** | CL, latency, timeouts, tracing, error rates, business checks | Are queries succeeding and accurate within tested scope? | That every node's ring or every app instance's metadata is identical |

**Critical mindset:** A topology change must never be declared complete simply because **one** of these four views shows the desired state.

### 2.1. Who Decides Where Data Is Stored?

- **The partitioner** computes a token from the partition key.
- **The replication strategy** such as `NetworkTopologyStrategy` and per-DC RF determine natural replicas for each token range.
- **The Cassandra coordinator** receives queries, determines target replicas, and executes reads/writes per CL; during transitions, the server handles ranges in flight.
- **Java Driver token-aware load balancing** prefers routing queries to a **coordinator** that is an appropriate replica when it knows the routing key and token map; it **does not** write replicas itself or dictate replication factor.

Thus an outdated driver token map can cause **suboptimal routing, extra network hops, or timeouts if a node is unreachable**. Never conclude a stale token map causes data to be stored in the wrong location: the server still enforces replication. However, never rely on this resilience to skip post-topology verification.

## 3. Topology Change Types and Their Metadata Impact

| Operation | Typical Server Progression | What Driver May Observe | Gate Criteria to Meet |
|---|---|---|---|
| **Bootstrap new node** | New node gets tokens, streams data, JOINING → NORMAL | Node added; state changes; token map recomputed | Node NORMAL, streaming done, steady reads/writes, app metadata converged |
| **Decommission live node** | Node exits ring gracefully, streams needed ranges | Node changes state/leaves list; updated token map | Streaming done, node left ring, RF still satisfied |
| **Removenode dead node** | Surviving replicas redistribute dead node's ranges | Node goes DOWN then is dropped from metadata | Old node gone from ring, streaming succeeded, enough healthy replicas |
| **Replace failed node** | Replacement takes over role/tokens, streams data | Host ID/address/state may change; new pool | Replace done, node NORMAL, data reconciled, conditional repair |
| **Move token** | Shifts ownership of token ranges; under version/topology conditions | Token map changes, possibly with node state events | New ranges balanced, cleanup/repair as needed, clients updated |
| **Change RF/DC** | Changes natural replicas even if node count stays fixed | Schema/keyspace replication metadata and new token map | Data migration/repair finished, valid CL, schema agreed |

**`nodetool decommission`** is for a live node; **`nodetool removenode`** is used when a node is dead/cannot decommission. Never treat them as equivalent ways to "drop an IP". Replacing a node typically uses the version-specific replace workflow, not just starting a new daemon with the same name.

### 3.1. Logical Ring Transition Example

~~~text
Before:
   A ───── B ───── C
   RF=3, three nodes in same DC

Add D:
   A ── D ── B ─── C
         ^    ^
       token ranges re-split;
       some data must stream to D

Applications:
   Driver instance 1: map A/B/C/D
   Driver instance 2: map A/B/C (not yet refreshed)
   Driver instance 3: sees D, but D lacks pooled connections yet
~~~

This is a **conceptual** example, not a diagram of exact tokens or real load. With virtual nodes (`num_tokens > 1`), one node can hold **many token ranges**, so a simple ring sketch does not fully capture data movement.

## 4. How Does Java Driver 4.x Learn Topology?

### 4.1. Control Connection

Java Driver 4.x maintains a **control connection** for administrative tasks:

1. Querying system tables for topology and schema.
2. Subscribing to server events reporting node-state and schema changes.
3. Checking schema agreement when needed.
4. Refreshing metadata objects that power load balancing and token-aware routing.

The control connection is **distinct** from pooled connections serving normal CQL queries. If the node hosting the control connection fails, the driver reconnects and picks another node per configuration. While disconnected or awaiting refresh, the app can still execute queries over surviving pools, yet metadata may lag behind true server state.

~~~text
Cassandra gossip / server topology events
                    |
                    v
         Driver control connection
                    |
        batch and throttle events
          (topology debounce)
                    |
                    v
         Refresh topology/schema
                    |
                    v
        New Metadata snapshot
             /           \
         Node list       Token map
             \           /
           Load balancing policy
                    |
          select coordinator for CQL
~~~

**Contact points are not a static list of all nodes**: they help the driver make initial connections, after which it discovers topology. Provide multiple stable contact points in the **local DC**, avoiding leaving a single about-to-be-decommissioned node as the sole contact point for newly starting processes.

### 4.2. Topology Events Do Not Arrive and Process Instantaneously

The driver uses **debouncing** to batch rapid UP/DOWN/ADD/REMOVE events. Reference configuration for Java Driver 4.17:

~~~hocon
datastax-java-driver {
  advanced.metadata {
    topology-event-debouncer {
      window = 1 second
      max-events = 20
    }
    schema.debouncer {
      window = 1 second
      max-events = 20
    }
  }
}
~~~

Implications:

- When node states flap rapidly, waiting through a debounce window avoids wasteful metadata refreshes per event.
- Once batched events hit the max count, the driver can process early rather than waiting indefinitely.
- **Increasing** the window lowers processing overhead yet **increases convergence lag**; **decreasing** it can trigger rapid refresh storms during node flapping.
- "Event received" does not equal "every session in every JVM has refreshed"; each instance owns its own control connection and lifecycle.

Never default to "optimizing" by setting `window=0`. Measure event frequency, real metadata lag, and driver CPU/admin thread impact first.

### 4.3. NodeStateListener: Knows About Events, Does Not Prove Data Readiness

Java Driver provides `NodeStateListener` with typical callbacks:

| Callback | Meaning from Driver Perspective | Must Never Be Used as Sole Signal For |
|---|---|---|
| `onAdd(Node)` | New node became known to driver | Successful bootstrap; note: node may **not yet be UP** |
| `onUp(Node)` | Driver considers node UP | Streaming/repair completed |
| `onDown(Node)` | Driver considers node DOWN or FORCED_DOWN | Node permanently left the ring |
| `onRemove(Node)` | Node vanished from driver's known topology list | All data cleaned up or other apps refreshed |

Callbacks may execute on **internal driver threads**. Only record metrics/logs or push events to a non-blocking queue; **never** invoke `nodetool`, blocking I/O, long queries, or node creation/deletion directly from a callback. Callbacks during session initialization can fire **before the session is ready**; nor should you assume `node.getHostId()` is populated on the very first event.

### 4.4. Metadata Snapshots Become Stale If Cached

~~~java
Metadata once = session.getMetadata();
// DO NOT cache "once" for routing/monitoring across hours.
~~~

`session.getMetadata()` returns a **point-in-time consistent metadata snapshot**, containing node list, token map, and schema (aside from a few mutable fields on `Node`, such as state). An old snapshot **never auto-adds newly bootstrapped nodes**. When observing current state:

~~~java
Metadata latest = session.getMetadata();
latest.getNodes().values().forEach(node ->
    System.out.printf("%s %s %s%n",
        node.getConnectAddress(), node.getState(), node.getDistance()));
~~~

`getNodes()` includes DOWN or IGNORED nodes. Appearing in the map **does not mean** the driver has active connections to that node; inspect `Node.getState()`, `getDistance()`, and open pool connections. Never use `Metadata#getNodes().size()` as the sole measure of real replica count or cluster safety.

## 5. Token-Aware Routing During the Metadata Refresh Window

Driver 4.x's default load-balancing policy prefers the **local DC** and **token-aware routing**. To compute preferred replicas, it needs:

- **Keyspace** and replication strategy info.
- The statement's routing key or routing token.
- An up-to-date token map.
- Eligible connected nodes not ignored by the load-balancing policy.

### 5.1. Prepared Statements Supply the Routing Key

Given table:

~~~sql
CREATE TABLE topology_lab.events_by_tenant (
    tenant_id text,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);
~~~

When using a `PreparedStatement` with partition-key bind markers:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT payload FROM topology_lab.events_by_tenant " +
    "WHERE tenant_id = ? AND event_id = ?");
BoundStatement query = ps.bind(
    "tenant-a", UUID.fromString("11111111-1111-1111-1111-111111111111"));
session.execute(query);
~~~

The driver receives partition-key bind-variable metadata from the prepared statement to compute the routing key. Conversely, for an unparameterized **simple statement**, the driver typically **cannot infer the routing key**, even when the query contains `WHERE tenant_id = 'tenant-a'`; token-aware routing for simple statements requires supplying routing info explicitly or switching to a prepared statement.

### 5.2. Before and After Token Ownership Shifts

~~~text
Before bootstrap:
  Driver token map: key tenant-a -> prefers A/B/C

During bootstrap:
  Server: D is receiving some ranges
  Driver app1: old token map, still tries A/B/C
  Driver app2: new token map, may consider D

After streaming + ring NORMAL + refresh:
  Driver computes updated preferred replicas for current ranges.
~~~

**Primary impact of lagging metadata:** queries hit suboptimal coordinators, adding round-trips, pressuring older nodes, and causing timeouts/retries while pools and streams fluctuate. **Do not** claim a stale token map itself loses data: Cassandra still handles replica selection and pending ranges server-side. Still, if quorum lacks replicas or streaming fails, reads/writes can fail; evaluate **both server and driver**.

### 5.3. Never Disable the Token Map to "Fix" a Slow Topology Refresh

~~~hocon
datastax-java-driver {
  advanced.metadata {
    schema.enabled = true
    token-map.enabled = true
  }
}
~~~

Disabling `token-map.enabled` strips the driver of optimal routing data. Disabling `schema.enabled` or filtering out keyspaces also strips replication metadata needed to compute the token map. That increases load and latency **without fixing** gossip/streaming issues.

> **Distinction to remember:** **Topology metadata** describes nodes/tokens; **schema metadata** describes keyspaces/tables and RF. Both must be accurate for effective token-aware routing, yet **schema agreement** does not mean data finished streaming, and **node UP** does not mean every node agrees on schema.

## 6. Transition Window: Avoid Treating One Event as a Safety Boundary

A bootstrap or decommission can last minutes to hours depending on data volume, bandwidth, and compaction. Driver metadata may refresh during **only a fraction** of that window.

### 6.1. Illustrative Timeline for Bootstrap

~~~text
                   New node D joins

T0  A/B/C run steadily, app uses token map M0
    |
T1  Start D, ring recognizes D as JOINING
    |             \
    |              \-- Driver instance #1 receives onAdd(D)
    |                          (does not mean D can serve all ranges)
T2  D streams the ranges it will manage
    |             \
    |              \-- Driver #2 still holds metadata snapshot M0
    |                  due to debounce or unrefreshed control connection
T3  D receives full data, state turns NORMAL
    |             \
    |              \-- Driver #1/#2 sequentially see new state and token map
T4  Streaming/repair/checks stabilize; driver sessions converge to M1
    |
T5  Only now proceed to next step, e.g. cleanup
    or approved capacity/routing policy adjustment
~~~

**Do not assume T3, T4, and T5 happen at the exact same instant.** Even once a node is NORMAL, JVMs recovering a control connection may still hold stale metadata; token-routing shifts also cannot be verified by a single `onUp` callback.

### 6.2. Risks Across Transition Sub-Windows

| Window | What Can Happen | Coordination Action |
|---|---|---|
| D just discovered, not done streaming | `onAdd`/node list updates before bootstrap completes | Never scale traffic based on `onAdd`; check `nodetool netstats` and lifecycle |
| Driver holds stale token map | CQL may pick older coordinators, adding hops | Keep sufficient capacity on old nodes; watch driver topology refresh |
| Node D shows UP in driver | Pools may open while data/ranges are still moving | Check server NORMAL state, streaming, and real queries |
| Control connection migrates to another node | Metadata refresh lags; logs show reconnects | Configure multiple contact points, monitor control connection; never mass-restart JVMs |
| Old node LEAVING, app still holds address | Query plan may briefly try leaving or DOWN node | Ensure fallback nodes; bound connection errors/retries |
| New ring yet one app instance unrefreshed | Instances prefer different coordinators | Check metadata snapshots **across multiple JVMs**, not one pod |
| Keyspace RF changes concurrently | Replica placement/CL and schema metadata shift together | Avoid combining in one window; RF changes need dedicated runbook/repair |

A failed request during transition could be due to **an old coordinator leaving**, **insufficient replica ACKs**, **streaming resource contention**, **slow metadata refresh**, or another app bug. Classify via logs/traces instead of automatically blaming the driver.

### 6.3. The "Two Planes Ready" Rule

Before advancing to the next step, verify at minimum:

**Server/data plane:**

- Token ring and lifecycle match plan.
- Bootstrap/decommission/replace streaming completed with zero failed sessions.
- Healthy replicas suffice for CL and RF in the DC.
- Required repair/consistency actions are complete or have an explicit tracking plan.

**Client/driver plane:**

- Relevant Java services see the valid node set and local DC via a **fresh** `session.getMetadata()` snapshot.
- Token map is enabled with keyspaces intact; queries have routing keys.
- Pools and coordinators have enough UP nodes without reconnect storms or request timeouts.
- Latency, throughput, and CQL results across test keys are acceptable.

**No single flag** is set simultaneously by Cassandra and every JVM to confirm both planes. Runbooks must coordinate these signals.

## 7. Replication, Consistency, and Schema Agreement During Topology Changes

### 7.1. CL Does Not Vanish When the Ring Changes

Suppose a DC has RF=3 and the app uses `LOCAL_QUORUM`:

~~~text
RF dc1 = 3
LOCAL_QUORUM requires 2 responses from eligible full replicas.

Add D and shift tokens:
  Ranges may be reassigned.
  Cassandra handles replicas/pending ranges server-side.
  The driver only picks the preferred coordinator to send CQL.
~~~

**Quorum follows the keyspace's replication and placement**, not the count of addresses in `Metadata#getNodes()`. Adding a fourth node **does not raise RF from 3 to 4**, so seeing four nodes never alters the quorum formula. Conversely, concurrently running `ALTER KEYSPACE` to change RF **truly changes** responsible replicas and data sync procedures.

| Situation | Consequences to Consider |
|---|---|
| RF=3, add node D | D gets some ranges; each partition keeps configured RF |
| Old node decommissioned while other replicas healthy | Streaming preserves placement; apps must update token map |
| Dead node removed via removenode | Surviving replicas must rebuild ranges onto eligible nodes; heavy load possible |
| RF increased | New replicas need historical data; requires repair/range streaming per runbook |
| RF decreased | Fewer copies; verify data safety and run cleanup per procedure |
| Multi-DC using `LOCAL_QUORUM` | Quorum only in local DC; never assume remote DC is synced |

Never automatically "drop CL from `LOCAL_QUORUM` to `ONE`" just to get past bootstrap without evaluating consistency requirements. Lowering CL alters the application's read/write contract.

### 7.2. Schema Agreement Is a Separate State

During topology changes, DDL is usually **not needed**. However, changing RF, table schemas, or indexes forces the driver to refresh **schema metadata**. New nodes or nodes with unconverged schemas can trigger "unconfigured table" errors if DDL and requests are poorly coordinated.

- Java Driver includes a **schema agreement check** for schema changes.
- Schema agreement compares schema versions across checked nodes—it **does not** prove token ranges finished streaming.
- During certain **mixed-version server rolling upgrades**, differing schema-version calculations can prevent schema agreement; restrict DDL during upgrades per version guidance.
- Treat `checkSchemaAgreementAsync()` strictly as a **schema** signal, never an API to "wait for topology completion".

**Operational recommendation:** Execute major changes sequentially—topology, replication factor, schema, and binary upgrades—in separate verified maintenance windows. If forced to combine them, define an explicit dependency path and formal stop criteria.

### 7.3. Do Not Confuse Driver Routing with Data Writes

~~~text
Client knows old token map:
      |
      v
   Coordinator A
      |
      |  Server resolves replicas/pending ranges
      v
     B/C/D per server ring state

Client knows new token map:
      |
      v
   Coordinator D (if eligible)
      |
      v
   Replica set chosen by server
~~~

Sending a query straight to D **does not** let D unilaterally decide the result. When analyzing latency, record both **coordinator** and actual participating replicas. Token-aware routing reduces hops; it does not replace quorum or streaming protocols.

## 8. Runbook for Adding a Node While Java Driver Is Running

This is a preparation and verification framework; topology-changing commands should be executed only by authorized operators on verified versions and topologies. Never apply destructive or restart steps to production straight from an academic example.

### Phase A — Pre-Bootstrap Baseline

1. **Record cluster state:** Cassandra version, DC/rack, seeds, `num_tokens`, RF, gossip health, `UN` node count, load, and token distribution.
2. **Check data and repair:** never bootstrap right amid severe replica loss, prolonged repair failures, or unresolved tombstones.
3. **Estimate data to stream:** verify disk headroom on new and source nodes, network capacity, and compaction headroom.
4. **Record SLOs:** p95/p99 latency, error rate, throughput, and timeouts for critical queries.
5. **Record client view:** Java Driver version, local datacenter, contact points, metadata enabled, token-aware enabled, app instance count, and driver snapshot timestamp.
6. **Set change concurrency:** avoid bootstrapping multiple nodes together without measuring cluster streaming capacity.

Non-mutating observation commands:

~~~bash
nodetool status
nodetool ring
nodetool describecluster
nodetool tablestats topology_lab
nodetool compactionstats
~~~

Save output with UTC timestamps and the target node address; `nodetool status` from one node does not guarantee all nodes share the same gossip view during cluster issues.

### Phase B — Bootstrap per Official Configuration

1. Prepare node D with exact **cluster name, compatible version, snitch, datacenter, rack, seeds, network/security, data directories, and token allocation**.
2. Start bootstrap following Apache Cassandra docs for the running version. **Do not** set `auto_bootstrap: false` to "go faster" when adding a normal data node; doing so can skip loading required ranges.
3. As D joins, watch D's lifecycle (e.g., `UJ`/JOINING) and `nodetool netstats` during streaming.
4. Preserve capacity on A/B/C. Never jump to cleanup or decommission source nodes simply because the driver fired `onAdd(D)`.
5. If bootstrap fails, halt and follow the **resume/restart/rebuild** runbook for your exact Cassandra version. Never delete active files or force the node into the ring with unloaded data.

~~~bash
# Observe bootstrap; run on authorized nodes.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

**Edge case:** In some Cassandra releases, consistent bootstrap can fail if a source replica is unavailable. Flags bypassing that guarantee (e.g., JVM flags related to consistent range movement) risk missing data; never disable safety just to "make bootstrap succeed".

### Phase C — Confirm D Readiness on the Server Side

Set explicit conditions:

- D enters **UP/NORMAL (`UN`)** state from the cluster's viewpoint.
- `nodetool netstats` shows no active bootstrap streaming or unexplained errors.
- Disk, SSTables, compaction, and logs on the new node show no missing/corrupt data signs.
- New ranges have enough replicas to serve CL; evaluate hints/repair if downtime occurred during bootstrap.
- Selected partitions **across affected token ranges** can be read/written, not just one generic query.

**Never treat `UN` alone as "all data reconciled".** If replicas are suspected of missing mutations, run properly scoped repair or appropriate data verification procedures.

### Phase D — Confirm Driver Convergence

Across **each Java service group**, capture a **fresh** `session.getMetadata()` snapshot to verify:

- D appears with the right host ID/address/local DC.
- Driver can connect to eligible local nodes and pools are active.
- Token map/keyspace metadata are enabled; prepared statements still compute routing keys.
- Control connection events/logs are free of infinite reconnect loops.
- Query share hitting appropriate coordinators and latency/timeouts show no abnormal spikes.

If one pod still misses D, check its control connection, network, gossip, topology event debouncer, and driver version. **Never mass-restart all pods simultaneously** if the issue is only slow refresh, as that triggers a connection storm overloading the cluster.

### Phase E — Run Cleanup Only After Convergence

Apache docs recommend running `nodetool cleanup` on nodes **that lost ownership of some ranges** after confirming the new node is active and data streamed completely. Cleanup purges SSTables holding data no longer owned by the node; it is I/O- and disk-intensive and can impact SLAs.

~~~bash
# Run ONLY under an approved production runbook,
# on nodes identified as needing cleanup:
nodetool cleanup topology_lab
~~~

**Never run cleanup early while bootstrap or the ring is unsettled.** Nor should successful cleanup be treated as replacing repair or verifying all Java services updated metadata.

## 9. Decommission, Removenode, and Replacing Dead Nodes Runbooks

### 9.1. Decommissioning a Healthy Node

**Goal:** Active node A gracefully leaves the ring, transferring its range data to appropriate replicas.

1. Check RF, healthy nodes, disk headroom, and streaming paths on remaining nodes.
2. Confirm the driver has **multiple contact points** and enough LOCAL nodes to sustain pooling; never leave A as the sole live contact point for new instances.
3. Issue decommission only from an approved maintenance session:

~~~bash
# Syntax illustration; this is a topology-changing operation.
nodetool decommission
~~~

4. Monitor `nodetool netstats`, LEAVING state, and streaming until A exits the ring.
5. Verify on Java sessions that `onRemove`/updated node lists appeared, query plans no longer depend on A, and connection errors returned to baseline.
6. Run data/CL checks and appropriate cleanup once the ring stabilizes.

**Never confuse "A is DOWN" with "A is decommissioned".** Merely stopping the daemon keeps natural replicas and token ranges on the old topology.

### 9.2. Removenode When a Node Is Dead

When node A fails and cannot run decommission, `nodetool removenode` may be used **from another healthy node** per official procedure. Verify the dead node's exact **host ID**, and ensure surviving copies hold sufficient data and disk to redistribute.

~~~bash
# Check host ID and ring state first.
nodetool status

# Parameter illustration; NEVER run with a guessed ID.
nodetool removenode <dead-node-host-id>

# Monitor during redistribution.
nodetool netstats
~~~

After removenode finishes, verify both **ring/data** and **driver metadata**. `onRemove` only confirms the driver noticed the node departure, not that surviving replicas hold valid data. If every copy of a range was lost, removenode/repair cannot recreate lost data.

### 9.3. Replacing a Failed Node

Replacing a dead node differs from bootstrapping a brand-new node: it may use **`-Dcassandra.replace_address_first_boot=<dead_node_ip>`** per Apache Cassandra, along with matching IP/host ID and version configs. While replacement streams, status seen from other nodes vs. the replacing node's own view may differ.

Apache docs note repair must run to guarantee data on a replacement when:

- The old node was down **longer than `max_hint_window`** before replacement.
- Or replacing with the **same IP** and replacement lasted **beyond `max_hint_window`**.

This is a critical operational condition: replacement may finish bootstrapping yet **have missed writes occurring before or during the transition window**. Java Driver receiving `onUp` for the replacement node does not prove missed mutations were repaired.

Never set `max_hint_window` to "infinite" to dodge repair; hints are not backup copies and do not replace scoped anti-entropy repair.

### 9.4. Avoid Mixing Multiple Major Events

A common dangerous sequence:

~~~text
Bootstrap D still streaming
      |
Stop A (source node)
      |
Concurrently ALTER KEYSPACE to change RF
      |
Multiple driver instances hit bursts of ADD/DOWN/SCHEMA events
      |
Retries and metadata refreshes amplify load
      |
Unclear if errors stem from topology, RF, data, or app
~~~

Instead, coordinate **one major change at a time**, with server/data/driver checkpoints and rollback/escalation criteria. Whenever truly independent operations are allowed concurrently, verify capacity and token scopes will not dangerously contend.

## 10. Java Driver 4.x: Observing Metadata Snapshots and Node Events

### 10.1. Creating a Session with Local DC, Contact Point, and Listener

Java Driver 4.x example showing how to collect node-change signals **without running heavy work inside callbacks**. Demo assumes lab Cassandra at `127.0.0.1:9042` and DC `dc1`; substitute real environment values.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.Metadata;
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.metadata.NodeStateListenerBase;
import java.net.InetSocketAddress;
import java.util.concurrent.atomic.AtomicInteger;

public final class TopologyObserver {
    public record Counters(
            AtomicInteger added,
            AtomicInteger up,
            AtomicInteger down,
            AtomicInteger removed) {
        public Counters() {
            this(new AtomicInteger(), new AtomicInteger(),
                 new AtomicInteger(), new AtomicInteger());
        }
    }

    public static CqlSession openLabSession(Counters counters) {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .addNodeStateListener(new NodeStateListenerBase() {
                @Override public void onAdd(Node node) {
                    counters.added().incrementAndGet();
                }
                @Override public void onUp(Node node) {
                    counters.up().incrementAndGet();
                }
                @Override public void onDown(Node node) {
                    counters.down().incrementAndGet();
                }
                @Override public void onRemove(Node node) {
                    counters.removed().incrementAndGet();
                }
            })
            .build();
    }

    public static void printSnapshot(CqlSession session) {
        // Fetch a fresh snapshot EACH TIME you observe.
        Metadata snapshot = session.getMetadata();
        System.out.println("knownNodes=" + snapshot.getNodes().size()
                + ", tokenMapPresent=" + snapshot.getTokenMap().isPresent());

        for (Node node : snapshot.getNodes().values()) {
            System.out.printf(
                "addr=%s hostId=%s state=%s distance=%s connections=%d%n",
                node.getConnectAddress(),
                node.getHostId(),
                node.getState(),
                node.getDistance(),
                node.getOpenConnections());
        }
    }
}
~~~

Usage inside a lab runner method:

~~~java
TopologyObserver.Counters counters = new TopologyObserver.Counters();
try (CqlSession session = TopologyObserver.openLabSession(counters)) {
    TopologyObserver.printSnapshot(session);
    // When topology changes: invoke printSnapshot again from an external
    // orchestration/observation path, NOT from the listener.
    System.out.println("onAdd=" + counters.added().get()
            + ", onUp=" + counters.up().get()
            + ", onDown=" + counters.down().get()
            + ", onRemove=" + counters.removed().get());
}
~~~

This snippet sits **inside a Java method**, not as a standalone runnable class. In real apps, create `CqlSession` **once** and reuse it; never create a new session per request or per metadata check. Multi-process apps must **collect metrics per process**, not from a single JVM's logs.

**Demo limitations:**

- The listener also receives events during session startup. Counters do not represent "post-bootstrap changes only".
- `Node.getHostId()` may temporarily be `null` on very early startup events; do not use it before ready.
- `getNodes()` lists nodes **known to the driver**, including DOWN/IGNORED; map size does not equal active connection pools.
- Callbacks run on driver threads. Atomic counters avoid blocking; for real event logs, use a **bounded** queue and a separate consumer.
- When multiple events are debounced/batched, **do not** assume callback counts equal every gossip state transition.

### 10.2. Prepared Queries Continue Working When Coordinators Shift

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

public final class EventReadService {
    private final CqlSession session;
    private final PreparedStatement findByKey;

    public EventReadService(CqlSession session) {
        this.session = session;
        this.findByKey = session.prepare(
            "SELECT payload FROM topology_lab.events_by_tenant " +
            "WHERE tenant_id = ? AND event_id = ?");
    }

    public String read(String tenantId, UUID eventId) {
        BoundStatement bound = findByKey.bind(tenantId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        Row row = session.execute(bound).one();
        return row == null ? null : row.getString("payload");
    }
}
~~~

**Advantage:** prepared statements supply partition-key bind metadata so the driver computes routing keys, provided schema/token metadata are enabled. When optimal coordinators shift due to an updated token map, the driver routes to another node without the app knowing individual replica IPs.

**Do not over-infer:** `LOCAL_QUORUM` only ensures appropriate responses per RF in the local DC; it does not replace repair, prove bootstrap streamed full data, or confirm remote-DC sync. On a `null` result, check whether the row never existed or encountered a read/CL issue rather than assuming "driver hasn't refreshed yet".

### 10.3. Measuring Metadata Convergence Lag Without Caching Snapshots

In an observation tool (not inside `NodeStateListener`), you can take two snapshots separated by an **operator-controlled interval**:

~~~java
Metadata before = session.getMetadata();
int beforeCount = before.getNodes().size();

// At a DIFFERENT point in time, after cluster events occurred and
// the operator explicitly queries again from monitoring:
Metadata after = session.getMetadata();
int afterCount = after.getNodes().size();

System.out.printf("knownNodes before=%d after=%d%n",
    beforeCount, afterCount);
~~~

Here `before` and `after` are useful only when genuinely collected at **two distinct times**. Reading two back-to-back snapshots does not force a driver refresh. There is no rule like "sleep two seconds and metadata is guaranteed fresh": dropped control connections, network partitions, debouncing, and driver version can prolong convergence.

To measure convergence, correlate timestamps from observability with **confirmed server events**, then track how many Java processes see the updated node/token map. A process missing an event must be investigated individually rather than raising application-wide timeouts.

## 11. Driver Configuration and Choices to Avoid

Verified HOCON snippet for Java Driver 4.17 series; adjust to your environment:

~~~hocon
datastax-java-driver {
  basic {
    load-balancing-policy.local-datacenter = dc1
  }

  advanced {
    metadata {
      schema.enabled = true
      token-map.enabled = true
      topology-event-debouncer {
        window = 1 second
        max-events = 20
      }
    }
  }
}
~~~

Java Driver 4.x config keys **differ** from Java Driver 3.x property names; never copy nested `DCAwareRoundRobinPolicy`/`TokenAwarePolicy` snippets from legacy samples into driver 4.x. Driver 4's default load-balancing policy is already local-DC and token-aware when metadata is available.

| Decision | Recommended Starting Choice | Counterproductive When Misused |
|---|---|---|
| Local DC | Specify the application's real DC name | Driver lacks local nodes, routes across wrong DCs |
| Contact points | Multiple stable addresses in local DC | Only leaving a soon-to-be-decommissioned IP → new sessions fail to start |
| Token metadata | Keep enabled and avoid filtering needed keyspaces | Loses token-aware routing, adds network hops |
| Schema metadata | Keep enabled for apps needing token/keyspace mapping | Lacks replication info to build token map |
| Debounce window | Keep default before benchmarking | Too small triggers refresh storms; too large delays reaction |
| Node listener | Very short, non-blocking callbacks | Stalls internal driver threads |
| Session lifecycle | Single reused session | Spawns multiple control connections, reconnect storms |
| Retry/speculative execution | Only policies matching idempotency and SLA | Retries non-idempotent writes or amplifies load during streaming |
| CL | Match business requirements and RF | Lowering CL to dodge timeouts risks stale reads / under-ACKed writes |

**Never use internal driver APIs to "force a node UP" or manually patch the token map** in routine operations. Doing so desynchronizes the load-balancing policy from the server; prioritize fixing connectivity, topology events, configuration, and the control connection.

### 11.1. Retries Are Not a Topology Synchronization Mechanism

A request timing out while coordinator D is entering the ring may **have already been partially applied** even though the client received no response. For INSERT/UPDATE/DELETE, retry decisions depend on idempotency and timestamps to avoid unwanted business side effects.

**Never** blindly enable infinite retries or speculative execution across the whole application when latency rises during streaming. That sends extra load to coordinators and replicas, prolonging range movement. Measure retry rates, timeouts, and in-flight counts, then address the root cause.

## 12. Lab: Observing Ring and Driver While Adding a Node

**Goal:** Zero production risk. Use a lab cluster with **at least three `dc1` nodes**, then add node D per your version's runbook. Sample data is tiny to observe metadata, **not** benchmark millions of partitions.

### Step 1 — Create Sample Schema and Data

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS topology_lab.events_by_tenant (
    tenant_id text,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);

CONSISTENCY LOCAL_QUORUM;

INSERT INTO topology_lab.events_by_tenant
    (tenant_id, event_id, payload)
VALUES ('tenant-a',
        11111111-1111-1111-1111-111111111111,
        'created');

INSERT INTO topology_lab.events_by_tenant
    (tenant_id, event_id, payload)
VALUES ('tenant-b',
        22222222-2222-2222-2222-222222222222,
        'paid');

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';
~~~

Substitute `dc1` if your actual DC name differs. In an RF=3 lab, `LOCAL_QUORUM` requires two responses in the local DC. If healthy replicas are insufficient, writes fail; never lower CL just to make the demo pass.

### Step 2 — Capture Baseline State

~~~bash
nodetool version
nodetool status
nodetool ring
nodetool describecluster
nodetool getendpoints topology_lab events_by_tenant tenant-a
~~~

Record:

- `UN` node count and addresses by DC/rack.
- Pre-change replica endpoints for `tenant-a`.
- Application latency/timeout metrics.
- `TopologyObserver.printSnapshot(session)` output **across observed Java processes**.

`getendpoints` returns expected **natural replicas** for a partition key per the queried node's ring, not proof that data on each replica has finished streaming.

### Step 3 — Start Java Observer and Track Events

Keep a `CqlSession` active in the lab; record:

~~~text
M0:
  session.getMetadata().getNodes() -> {A, B, C}
  tokenMapPresent               -> true
  Node states                   -> UP on healthy local nodes
  App read tenant-a             -> 'created'
~~~

Note that initial `onAdd`/`onUp` may record events right as the session opens. Do not mix them with events emitted by the subsequent bootstrap; establish a baseline timestamp after session initialization completes.

### Step 4 — Bootstrap D (Authorized Lab Only)

The lab operator prepares and starts D per Apache Cassandra topology changes docs. Meanwhile, observe:

~~~bash
# Run periodically when the operator checks progress.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

**Never** simulate a fake `onUp` in the driver to substitute for bootstrap. Observe in Java:

- Listener may receive `onAdd(D)` before the node is ready to serve CQL.
- Fresh metadata snapshots may include D in the node list and token map after a few events.
- Different app instances may observe transitions at different moments.
- Prepared queries for `tenant-a` must continue returning valid logical data even as preferred coordinators shift.

### Step 5 — Wait for D NORMAL and Metadata Convergence

~~~bash
nodetool status
nodetool netstats
nodetool getendpoints topology_lab events_by_tenant tenant-a
~~~

Compare `getendpoints` before/after: depending on token allocation, `tenant-a`'s replica set may change **or stay the same** based on token position. Check additional tenants/ranges if you want to prove the driver observed a specific token ownership shift.

From Java, call `printSnapshot(session)` again. Once D appears:

- Verify accurate **DC**, host ID, and state.
- Verify token map is present.
- Verify requests do not time out and the driver is not stuck in reconnect loops.
- Do not claim all JVMs converged after checking only one JVM.

### Step 6 — Test CQL Across Multiple Post-Change Checkpoints

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-b';

TRACING ON;

SELECT event_id, payload
FROM topology_lab.events_by_tenant
WHERE tenant_id = 'tenant-a';

TRACING OFF;
~~~

Tracing reveals the coordinator and participating replicas, yet adds overhead; use only in labs/short investigations. **Expected data:** `tenant-a` has payload `created`; `tenant-b` has `paid`. Updating the token map **must never** alter CQL results.

### Step 7 — Collect the Comparison Table

| Evidence | Before Bootstrap | After Bootstrap & Convergence | Passed? |
|---|---|---|---|
| Server ring | A/B/C `UN` | A/B/C/D `UN` | Compare outputs |
| Streaming | No bootstrap job | No failed/running jobs left | Check `netstats` |
| Driver metadata | List A/B/C | List A/B/C/D across targeted JVMs | Check fresh snapshots |
| Token metadata | Present for `topology_lab` | Present and matches new ring in tested scope | Do not infer from node count |
| CQL logic | `created`/`paid` | Still `created`/`paid` | Test both reads and writes |
| Driver errors | Baseline timeouts/reconnects | No abnormal spike | Metrics/logs |
| Server resources | Baseline disk/network/compaction | Steady post-stream | Metrics/logs |

If any gate fails, keep the change in **PARTIAL/INVESTIGATING** state. Never run cleanup early or start decommissioning the next node just because of a deadline.

## 13. Monitoring Server, Driver, and Application Concurrently

To know when metadata refreshes may impact traffic, use a **shared timeline** with synchronized clocks, event IDs, and node/DC/range context.

| Signal Group | Minimum Observation | Meaning and Limitations |
|---|---|---|
| Gossip/ring | `nodetool status`, `ring`, DC/rack, JOINING/LEAVING/NORMAL states | Shows ownership shifts; does not confirm clients refreshed |
| Streaming | `nodetool netstats`, session progress, source/destination errors | Reflects data movement; does not mean apps see new token map |
| Repair | Job IDs, range coverage, failed sessions, hints | Tracks missing-mutation risk; does not prove business correctness |
| Driver control connection | Host holding control connection, reconnect/error logs | Explains slow refresh when control node drops |
| Driver node metadata | Node map, `NodeState`, host ID, distance, connection count | A node in metadata may be DOWN/IGNORED |
| Driver token/schema map | Token map enabled, keyspace replication computable | Losing keyspace/schema metadata degrades token-aware routing |
| Node events | `onAdd`/`onUp`/`onDown`/`onRemove`, timestamps | Not a certificate of completed streaming |
| Pooled connections | Open connections, reconnects, unavailable hosts | Unready pools can trigger timeouts |
| CQL | Success/errors, p95/p99, timeouts, CL, retries | Measures real experience; does not replace ring checks |
| Capacity | Disk, compaction, network, CPU, GC | Streaming/refreshes/retries compete for resources |

### 13.1. Correlating Events on a Single Timeline

~~~text
UTC 09:00:00  Operation START bootstrap D
UTC 09:00:07  Server D = JOINING; netstats STREAMING
UTC 09:00:09  JVM-1 node event onAdd(D)
UTC 09:00:10  JVM-1 metadata includes D
UTC 09:00:11  JVM-2 control connection reconnecting
UTC 09:01:35  Server D = NORMAL; streaming complete
UTC 09:01:38  JVM-2 metadata includes D
UTC 09:02:10  App latency/retry returns to baseline
UTC 09:03:00  Operator verifies gates; change accepted
~~~

This is a **simulated timeline**, not a default driver or Cassandra SLA. Capture real timestamps via telemetry across every node/JVM, as streaming and refresh speeds vary widely between clusters.

**Recommended aggregate signals:** percentage of Java processes seeing the target node set; count of processes reconnecting; per-DC latency/timeout distributions; server streaming status; and remaining incomplete topology steps. Percentages must cover **the entire serving JVM fleet**, not just a couple newly redeployed instances.

### 13.2. Never Use NodeState Instead of Full Health Checks

A node may appear `UP` in the driver while:

- Still bootstrapping or streaming partial ranges.
- Lacking resources to meet SLAs.
- Reachable only over network paths from a subset of clients.
- Missing mutations skipped by prior replicas.
- Holding mismatched schema/replication compared to peers.

Conversely, a node temporarily `DOWN` in one JVM is not necessarily confirmed dead cluster-wide: that pod's network path alone might be broken. **Check both sides** before deciding to removenode or replace.

## 14. Troubleshooting Common Issues When Metadata Has Not Converged

### 14.1. "Node Is NORMAL Yet Java Service Does Not See It"

**Symptom:** `nodetool status` shows D as `UN`, yet `session.getMetadata().getNodes()` on a JVM omits D.

Checklist order:

1. Is the JVM using a **live session** and reading a fresh snapshot, or holding a stale startup `Metadata` reference?
2. Is the control connection pointed at a healthy node? Any timeout/reconnect, TLS, or authentication errors?
3. Did gossip/system tables on the control node already update with D?
4. Is the Java service using the right cluster, local datacenter, and broadcast/native transport addresses?
5. Is debouncing/refreshing processing a large event burst or slowed by continuous flapping?
6. Is a policy filtering D as `IGNORED`, or are token/schema metadata disabled?
7. Compare multiple JVMs to isolate local pod faults vs. workload-wide issues.

**Do not fix by:** hardcoding D's IP into CQL statements or mass-restarting all JVMs before finding root cause. If a control connection truly fails to recover, apply bounded rolling reconnects/redeploys.

### 14.2. "Driver Sees D Yet Does Not Use D as Coordinator"

Possible causes:

- D is not yet `UP`, lacks pooled connections, or was marked `IGNORED` by policy.
- D is outside the app's **local DC**, and default policy excludes remote DCs.
- For that specific partition key, D is **not** a natural replica per the token map—completely normal.
- Query uses a `SimpleStatement` without a routing key, or schema/token metadata were disabled/filtered.
- Load balancing still picks another node per policy and readiness; it need not hit D on every request.

To evaluate, pick **multiple partition keys** whose token ranges touch D, use prepared statements, and verify token map/keyspace replication. Never force every query onto D to "test load balancing".

### 14.3. "Decommission Finished Yet Java App Still Tries Old IP"

Possibilities:

- Metadata not yet refreshed or app caches an old snapshot.
- Driver process lost its control connection and missed the REMOVE event.
- App configured **only one contact point**—the departed IP—preventing **new sessions** from initializing.
- Load balancing/session still has a pool entry for the old node pending state update; timeouts may occur during pool reconnect.
- Server nodes did not reach ring agreement after a failed decommission.

Resolve by confirming server removal completed, updating contact points for **new session initialization**, and watching driver reconnects and fresh metadata; never hardcode all nodes into the request path.

### 14.4. "Read/Write Timeouts Surge Even Though Metadata Updated Properly"

Accurate metadata does not mean cluster capacity suffices for the change. During streaming:

- Source/destination disk I/O and network spike.
- Compaction, hints, and repair compete for resources.
- Surviving nodes absorb extra queries as one node leaves.
- CL may fail due to insufficient UP replicas.
- Driver retries/speculative executions amplify true request load.

The fix is **throttling topology changes, capacity, and concurrency**, not merely shrinking the debounce window. Observe all three layers—server, driver, app—to pinpoint the bottleneck.

### 14.5. "After Replace, All Nodes Are UP Yet Some Old Rows Are Missing"

Per Apache guidance, replacement may require repair if the old node was down longer than the hints window or used the same IP and replacement dragged out. `onUp` does not guarantee repair finished; reconcile data by range and inspect hints/repair/streaming.

Specifically, if the old replica was absent past `gc_grace_seconds` and missed DELETEs, **zombie data** risk must be assessed separately. Turning a node with old SSTables back on is not a safe "auto-repair" once tombstones are gone.

### 14.6. "Schema Agreement Reports Errors While Node List Looks Normal"

Distinguish:

- **Topology metadata:** nodes/token ranges and liveness.
- **Schema metadata:** tables, keyspaces, replication, UDTs, indexes.
- **Schema agreement:** whether checked nodes share compatible schema versions.

A clean node list does not equal synchronized schemas. Freeze new DDL, check schema versions and upgrade direction, and wait/fix propagation per runbook before letting Java services use new tables. Never "fix" an unconfigured-table error by altering CL or pinning queries to one IP.

## 15. Checklist Before Declaring a Change Complete

| Group | Verification Question | Expected Status |
|---|---|---|
| Approval | Correct change request, operation, and node/DC scope? | Yes |
| Ring | Joining/leaving/removed/replaced nodes in target state? | Yes |
| Streaming | No active or unexplained failed jobs remaining? | Yes |
| Replicas | Enough RF and healthy replicas for app CL in target scope? | Yes |
| Repair/hints | Post-replace/outage repair criteria met or safely scheduled? | Yes |
| Driver control | Sessions connected, control connections healthy? | Yes |
| Driver metadata | Majority/100% of serving JVMs see target topology per rollout criteria? | Per policy, clear metrics |
| Token/schema | Token map enabled, keyspace/schema valid? | Yes |
| Routing | Prepared partition-key queries show expected latency/coordinators? | Yes |
| Client config | Contact points/local DC independent of departed nodes? | Yes |
| SLA | Error rate, p95/p99, timeouts, retries, resource usage within limits? | Yes |
| Data | Before/after key sets match expected values, including DELETE/TTL if applicable? | Yes |
| Cleanup | Run only after cluster stability, if needed? | Planned |
| Rollback | Safe fallback exists if new node/metadata fail to converge? | Yes, verified |

**If the ring passes yet the driver has not:** do not accelerate the next step. **If the driver passes yet streaming has not:** do not declare completion either. Require a **joint gate** backed by evidence on both planes.

### 15.1. Decision Table When Hitting Blockers

| Situation | Initial Decision | What Not to Do |
|---|---|---|
| D is JOINING, `onAdd` fired | Hold window, monitor streaming | Immediately cleanup or retire source nodes |
| D is NORMAL, some JVMs unrefreshed | Inspect control connection/metadata per JVM | Uncontrolled mass restart of all services |
| Decommission failed, A stuck LEAVING | Halt next change and fix server side | Treat `onDown` as equivalent to `removenode` |
| RF short on healthy replicas | Prioritize restoring replicas/capacity | Mass-downgrade CL and declare complete |
| Replacement missed hints | Execute repair per runbook | Trust node UP equals full data |
| Schema disagreement | Pause DDL migrations, sync schemas | Pin queries to one fixed coordinator |
| Timeouts rise from streaming | Throttle streaming/compaction/load and analyze retries | Only raise timeouts infinitely |

## 16. Self-Assessment Questions

**Question 1.** Node D just triggered `onAdd` in Java Driver. Can you immediately decommission source node A?  
**Guidance:** No. `onAdd` means the driver discovered D; D may not be UP or finished streaming its ranges.

**Question 2.** Why is `Metadata once = session.getMetadata()` captured at startup unsuitable for tracking subsequent bootstrap?  
**Guidance:** `Metadata` is a snapshot; you must call `session.getMetadata()` again to observe changes.

**Question 3.** If a node is `UN` on the server yet only 20/30 JVMs see the new node, what is missing before completion?  
**Guidance:** Metadata has not converged across the full app fleet; check control connections, debounce, network, and rollout criteria.

**Question 4.** If the driver holds an old token map, does it force data to be stored on old replicas?  
**Guidance:** No; the driver picks preferred coordinators, while Cassandra enforces replication and pending ranges.

**Question 5.** At RF=3, does adding a fourth node automatically make `LOCAL_QUORUM` require three responses?  
**Guidance:** No; keyspace RF does not change automatically when adding nodes.

**Question 6.** Why do prepared statements generally perform better token-aware routing than simple statements?  
**Guidance:** The driver knows partition-key bind variables to compute the routing key.

**Question 7.** Does `onUp(D)` guarantee the replacement received all writes during the old node's downtime?  
**Guidance:** No. Repair may be required depending on `max_hint_window` and replacement state.

**Question 8.** Driver sees D in `getNodes()` with state DOWN. Can D be treated as a healthy coordinator?  
**Guidance:** No; the node map includes DOWN/IGNORED; inspect pools and distance.

**Question 9.** Does a successful `LOCAL_QUORUM` query in dc1 prove dc2 is synced after a topology change?  
**Guidance:** No. Local quorum only satisfies the local DC's requirement.

**Question 10.** After node A finishes decommission, new app instances fail to start because they list only contact point A. Should you hardcode every IP into every query?  
**Guidance:** No; update stable contact points for session initialization and let the driver discover nodes via its control connection.

**Question 11.** Is schema agreement a signal that D finished bootstrapping?  
**Guidance:** No; schema and streaming/token ring are independent state axes.

**Question 12.** If bootstrap drives up p99 and causes retry bursts, what should you adjust first?  
**Guidance:** Analyze disk/network/streaming and retries, and throttle the change; never default to shrinking debounce or lowering CL.

## 17. Summary

~~~text
                        TOPOLOGY CHANGE
                              |
                    +---------+----------+
                    |                    |
              SERVER / RING         JAVA DRIVER
                    |                    |
         gossip, token ranges       control connection
         JOINING / LEAVING          topology events
                    |                    |
         streaming / repair         debounce / refresh
                    |                    |
        NORMAL / range ownership    New Metadata snapshot
                    |                    |
                    +---------+----------+
                              |
                 Check CLIENT / DATA
            CL, CQL results, p95/p99, timeouts
                              |
                  Joint completion criteria
                              |
                   Advance to next step
~~~

**Core principle:** Cassandra stores data and moves token ranges on the **server plane**; Java Driver learns topology, maintains pools, and picks coordinators on the **client plane**. The two planes do not update atomically together. Therefore, during bootstrap/decommission/removenode/replace, **preserve capacity during transition, observe fresh metadata across multiple sessions, verify streaming/replicas and CQL before running cleanup or starting the next change**. This reduces timeouts, suboptimal routing, and unsynchronized data in distributed Cassandra systems serving Java applications.

## References

- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html) — bootstrap, decommission, removenode, replace, streaming, cleanup, and repair conditions.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — gossip, coordinators, replication, consistency levels, and recovery mechanisms.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, replica/range scope, and maintaining consistency.
- [DataStax Java Driver 4.17 — Control connection](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/control_connection/) — topology/schema discovery, events, and control connection recovery.
- [DataStax Java Driver 4.17 — Node metadata](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metadata/node/) — `getNodes()`, NodeState, and NodeStateListener.
- [DataStax Java Driver 4.17 — Token metadata](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metadata/token/) — token maps, replicas, and consequences of disabling.
- [DataStax Java Driver 4.17 — Performance](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/performance/) — topology-event debouncer, schema metadata, and refresh overhead.
- [DataStax Java Driver 4.17 — Load balancing](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/load_balancing/) — local DC, token-aware routing, and routing keys.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bind metadata and routing keys.
- [DataStax Java Driver 4.17 — Session API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/session/Session.html) — snapshot semantics of `getMetadata()` and schema agreement.
