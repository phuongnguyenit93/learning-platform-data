# Rolling Deployments, Concurrency Limits, and Stop Conditions in Apache Cassandra

> **Chapter:** Operations Automation  
> **Scope:** Controlled change orchestration on Apache Cassandra: rolling restarts, configuration/version changes, Java Driver application rollouts, schema migrations, and maintenance tasks such as repair/streaming. This lesson focuses on **rollout order**, **concurrency budgets**, **inter-wave health gates**, and **pause/emergency-stop conditions**. Examples are educational designs; never execute restart/repair/replace actions in production without authorization, plans, and rollback procedures.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why Cassandra requires **wave-by-wave rollouts** instead of updating every node simultaneously.
2. Distinguish rolling restarts, rolling binary upgrades, rolling config changes, schema migrations, rolling app deployments, and node replacements.
3. Derive concurrency limits from **replication factor (RF)**, **consistency level (CL)**, **natural replica sets**, current node states, and datacenter/rack scopes.
4. Design an execution order that avoids taking two replicas of the same hot partition offline simultaneously.
5. Define **GO/HOLD/ABORT/ROLLBACK** conditions rather than relying on fixed sleep intervals.
6. Author a rollout manifest containing topology, change fingerprint, canary, batch size, health gates, deadlines, guardrails, and approvers.
7. Separate milestones: **process started**, **gossip UP/Normal**, **native transport ready**, **driver routing healthy**, **data/CL ready**, and **performance recovered**.
8. Set distinct concurrency limits for restarts, repair/streaming, compaction-heavy maintenance, schema DDL, and Java applications.
9. Use `nodetool status`, `describecluster`, `netstats`, `tpstats`, `compactionstats`, and CQL probes to construct preflight and post-change gates.
10. Design an automated **fail-closed** controller with locks/leases, idempotency, checkpoints, deadlines, bounded retries, and safe crash recovery.
11. Understand why `PodDisruptionBudget`/StatefulSet readiness or an operator "Task Completed" status is **insufficient** to prove CL and business data health.
12. Write a Java Driver 4.x readiness probe at the target CL and distinguish schema, connection, replica/CL, timeout, and data mismatch errors.
13. Model RF3/`LOCAL_QUORUM`, multi-DC, quorum headroom, an already-DOWN node, and scenarios requiring concurrency reduced to 0.
14. Report rollouts with timestamps, attempt IDs, before/after observations, gate results, node coverage, and unresolved risks.

**In the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module**, tokens and partition keys determine natural replicas, keyspaces define replication strategy and RF, and CL determines how many responses reads/writes require. Therefore, Cassandra operations automation must **protect serving capability across replica sets**, not just make each machine look "green" on a dashboard. CQL and Java examples are used to verify exact **data and application behavior** after changes.

## 2. What is a "rolling deployment"?

A rolling deployment applies a change to **one small unit or a bounded wave**, checks the results, and only then expands to the next unit:

~~~text
                 Approved change request
                           |
                      PREFLIGHT
                           |
                      CANARY NODE
                           |
                Health + data + SLO gates
                   /            \\
                PASS           FAIL
                 |               |
             WAVE 1             HOLD
                 |               |
           Re-check gates   rollback/escalate
                 |
             WAVE 2
                 |
                ...
                 |
          POST-ROLLOUT SOAK
                 |
              REPORT
~~~

In Cassandra, a wave may be **one Cassandra node**, **one rack/zone with an approved tiny node count**, **a batch of application pods**, or **one partitioned maintenance task**. They do not share identical concurrency or safety rules. Never assume "batch size 2" is safe for every operation type.

### 2.1. Why not restart all of RF3 at once?

Suppose a keyspace has RF3, natural replicas for a partition are A, B, C, and reads/writes at `LOCAL_QUORUM` require **2/3 replicas** to respond in the same DC.

~~~text
Before:
  A UP    B UP    C UP
  quorum 2/3 possible

Restart A only:
  A DOWN  B UP    C UP
  quorum 2/3 still possible (but zero headroom left)

Restart B while A not recovered:
  A DOWN  B DOWN  C UP
  quorum 2/3 NOT possible
~~~

This implies: if **one replica is already unavailable**, the next wave must not take down another replica of that same key. Having 100 nodes in a cluster does not make restarting any 10 nodes safe: a hot partition still has only three natural replicas, and two of them could sit inside those 10 chosen nodes.

### 2.2. State change on a node vs. topology change

| Activity | Primary change | Why a separate wave design is needed |
|---|---|---|
| Rolling restart Cassandra process | One node briefly stops serving; token/host ID usually retained | Preserves quorum, cache warm-up/commitlog replay |
| Rolling binary upgrade | Version-specific binary/feature compatibility | Mixed-version constraints, SSTable/protocol/storage format |
| Rolling config change | JVM/Cassandra/driver parameters, may require restart | Restart-safe vs. runtime-dynamic, rollback |
| Schema migration | DDL propagates to many nodes; not tied to one replica | Single DDL owner, schema agreement, app compatibility |
| Rolling Java application | Changes code/driver config, not necessarily restarting Cassandra | Client pools/routing, queries/CL, traffic shift |
| Bootstrap/replace/decommission | Token ownership / natural replicas change | Streaming, hints/repair; unlike a restart |
| Repair/streaming task | Heavy disk/network/CPU, does not necessarily mark node DOWN | Resource contention, data coverage, overlapping token ranges |

**Avoid confusion:** `nodetool decommission`/`removenode`/node replacement **are not** ways to rolling-restart a routine node. Those commands alter topology and data ownership and require dedicated runbooks.

### 2.3. "One node at a time" is a safe default, not an absolute theorem

Even one node at a time can still cause an outage when:

- Another replica is already DOWN/sluggish, breaking quorum as soon as the node restarts.
- The app uses `ALL`/`EACH_QUORUM` or a CL lacking headroom for one node down.
- The keyspace has RF1 or RF2 while the contract needs quorum or full replicas.
- The restarting node coordinates/serves hot partitions near saturation with no capacity left to absorb failover.
- A cross-DC network partition exists or drivers connect to only one endpoint.
- Compaction/repair/streaming from a prior wave still occupies disk/network.

**Rule:** Before *every* wave, evaluate **current observed state**; never treat initial preflight results as a permanent guarantee.

## 3. Three budgets that must be enforced concurrently

Every automation step is governed by three independent budget groups:

1. **Replica availability budget:** How many natural replicas can go down per token range while still meeting CL/contracts?
2. **Resource budget:** How much concurrent work can run before disk, network, CPU, GC, or streaming/repair/compaction bottlenecks?
3. **Business error budget:** How much can a wave degrade SLO p95/p99, error rates, timeouts, unknown outcomes, or backlogs before stopping?

~~~text
                      Proposed wave W
                             |
            +----------------+----------------+
            |                |                |
          REPLICA          RESOURCE          BUSINESS
          BUDGET           BUDGET            BUDGET
            |                |                |
         PASS?             PASS?             PASS?
            \\                |               /
             \\               |              /
              +--------------+-------------+
                             |
                        ALL PASS?
                       /         \\
                    YES           NO
                     |             |
                  EXECUTE         HOLD/ABORT
~~~

**Never combine these budgets into an average score.** A wave using minimal CPU that breaks quorum must still be blocked; a wave preserving quorum that fills the commitlog disk must also be blocked.

### 3.1. Budget does not equal maximum node count

For example, RF3 + `LOCAL_QUORUM` allows **one unavailable replica per natural replica set** if all remaining replicas are healthy. A cluster spans hundreds of token ranges and multiple keyspaces; each node owns many token ranges. Two nodes in different racks **can still be co-replicas** for some partitions depending on token placement, vnodes, racks, DCs, and routing.

Thus "one node per rack concurrently" **does not prove safety by itself**. Concurrency must be constrained by replica-set intersection alongside load and failure domains.

### 3.2. Multiple keyspaces with different RF/CL

~~~text
Keyspace orders:     RF3 in dc1, LOCAL_QUORUM
Keyspace telemetry:  RF2 in dc1, LOCAL_ONE
Keyspace audit:      RF3 in dc1, ALL

Wave candidate: restart node A
~~~

If `audit` uses `ALL` and node A sits in the natural replica set of active partitions, taking one node down breaks that CL. Even though `orders` keeps quorum, the wave must **HOLD** if the audit contract requires continuous availability. Accepting planned downtime for `audit` requires explicit **approval and traffic quiescence**, never silently lowering CL.

### 3.3. Actual state can be weaker than RF on paper

`RF=3` specifies the replication target, not proof every replica holds complete data and responds within deadlines. A `DN` node, bootstrapping/rebuilding node, overloaded disk, unapplied hints/repair, or driver routing gap all reduce the effective budget.

**Execute the plan only when observed capacity and data/probe evidence prove it is safe.**

## 4. State model for a node/wave

### 4.1. Do not treat `UN` as the sole criterion

~~~text
PENDING
   |
PREFLIGHT_OK
   |
INTENT_RECORDED / LEASED
   |
DRAINING (if runbook requires)
   |
PROCESS_RESTARTING
   |
PROCESS_STARTED
   |
GOSSIP_UP_NORMAL
   |
NATIVE_TRANSPORT_READY
   |
SCHEMA_AND_DRIVER_READY
   |
DATA_CL_PROBES_PASS
   |
PERFORMANCE_AND_BACKGROUND_WORK_STABLE
   |
WAVE_VERIFIED
   |
COMMITTED -> NEXT WAVE
~~~

A wave advances to `COMMITTED` only when **every gate applicable to that change type** passes. If a gate lacks telemetry, treat it as **UNKNOWN/HOLD**, never PASS due to missing numbers.

### 4.2. Five readiness types commonly conflated

| State | Verifiable via | Does not guarantee |
|---|---|---|
| Process started | PID/container/pod RUNNING, JVM boot logs | CQL works, schema/data are intact |
| Gossip `UN` | `nodetool status` from multiple vantage points | Driver routes to it, bootstrap/streaming/repair finished |
| Native transport ready | CQL handshake / `system.local` | RF/CL and business data are intact |
| Metadata/driver ready | `CqlSession.getMetadata()`, query prepare | All data replicas have caught up |
| Business + performance ready | Sentinel read/write at CL, latency/error/queue windows | Full token/tenant coverage if probing only 1 key |

**A single successful `SELECT` on `system.local` is insufficient** to declare an app using `LOCAL_QUORUM` or `EACH_QUORUM` ready. Probe representative keyspaces/tokens/queries while avoiding unauthorized production mutations.

### 4.3. Persist state durably

Automation must persist at least `run_id`, `change_hash`, wave index, node host IDs, timestamps, gate outcomes, failed actions/attempts, operator overrides, and rollback status. When a controller crashes, it must **reconcile observed state** against checkpoints before retrying—never replay a side-effecting action simply because an HTTP/JMX response was lost.

### 4.4. Rollback does not mean immediately restarting the old binary

If a new binary changed on-disk formats or enabled new config/protocol features, binary rollback may be **unsupported**. If a node is DOWN or half-upgraded, check release-specific compatibility, snapshots/backups, and cluster state before rolling back. That is why **canaries + early stop gates** beat assuming "reverting the image tag is always safe."

## 5. Computing concurrency budgets from RF, CL, and natural replicas

### 5.1. Foundational formula per replica set

Let `S(k, d)` be the set of **natural full replicas** serving partition key `k` in DC `d`. Let `A(k, d)` be the set of replicas currently healthy enough to answer CQL within deadlines, and `B` be the set of nodes rendered unavailable by a wave. For `LOCAL_QUORUM` in a DC with RF=`r`:

\[
q_{\mathrm{local}} = \left\lfloor \frac{r}{2}\right\rfloor + 1.
\]

**Necessary condition** for the wave not to lose local quorum on the partition:

\[
\left|(A(k,d)\setminus B)\cap S(k,d)\right|
\geq q_{\mathrm{local}}.
\]

For a wave to be permissible across the workload, this inequality must hold for **every replica set/token range, keyspace, and DC** whose CL contract must remain served—not just one lucky test key.

This is only a **necessary counting check**; it ignores replica lag, disk saturation, network partitions, client routing, and latency. Automation must pair it with resource and SLO gates. With transient replicas, topology changes, or CLs other than `LOCAL_QUORUM`, apply the **actual consistency rules of your version/replica type** rather than blindly applying the full-RF formula above.

### 5.2. Intuition table for a single DC, full replicas

| Full RF (one DC) | CL | Logically required replies | Max unavailable replicas where CL *may* still succeed | Recommended default rollout policy |
|---:|---|---:|---:|---|
| 1 | `ONE`/`LOCAL_ONE` | 1 | 0 | No zero-downtime rolling restart; planned downtime or HA redesign needed |
| 2 | `LOCAL_QUORUM` | 2 | 0 | Do not restart nodes when continuous CL availability is required |
| 3 | `LOCAL_QUORUM` | 2 | 1 | **One node at a time** when all remaining replicas are healthy |
| 3 | `ALL` | 3 | 0 | Planned downtime or CL contract review required |
| 5 | `LOCAL_QUORUM` | 3 | 2 | Still start at concurrency=1; scale only with replica-set proof and headroom |
| 3 | `LOCAL_ONE` | 1 | 2 by count | Never assume two nodes down is safe for durability or latency |

The "may still succeed" columns are **not** SLAs or durability guarantees. At `ONE`, one surviving replica does not guarantee latest data or healthy disks. Operations plans keep **extra safety margin** rather than pushing right against the quorum edge for speed.

### 5.3. Why cluster node count cannot replace `S(k,d)`

~~~text
Cluster dc1 has 12 Cassandra nodes
Keyspace orders RF3

Token range X: natural replicas A, E, J
Token range Y: natural replicas B, F, K
Token range Z: natural replicas A, B, C

Wave {A, B}:
  X loses A -> 2 of 3 remain (possible quorum)
  Y loses B -> 2 of 3 remain (possible quorum)
  Z loses A,B -> 1 of 3 remains (NO quorum)
~~~

Because token assignments/vnodes rarely map cleanly to "one replica per rack" in all setups, two nodes can still overlap on replica ranges. Never choose waves purely by hostname order or Kubernetes `maxUnavailable` arithmetic.

### 5.4. Per-DC and failure-domain limits

With `NetworkTopologyStrategy`:

~~~text
dc1: RF3, A/B/C
dc2: RF3, D/E/F
App dc1: LOCAL_QUORUM -> needs 2 local replicas
App dc2: LOCAL_QUORUM -> needs 2 local replicas
~~~

Restarting one node in dc1 and one in dc2 **can** preserve local quorum when all full replicas are healthy, yet running in parallel is not automatically safe. Any operation using `QUORUM` across 6 replicas needs 4 replies; losing one per DC leaves exactly 4—**zero headroom** against tail latency or network blips. `EACH_QUORUM` also requires quorum in **every DC**. A conservative policy may keep **cluster-wide concurrent node restarts <= 1** initially even when theory allows more.

### 5.5. "One node already DOWN" changes the budget immediately

~~~text
Before:
  RF3, LOCAL_QUORUM, replicas A/B/C all healthy
  Planned restart A is conditionally safe.

At pre-wave gate:
  C is already DOWN or failing reads.

If restart A:
  A and C unavailable -> only B left.
  Do not start wave.
~~~

**Account for existing unavailability, not only nodes the automation intends to restart.** If a node is already `DN` in an RF3/LQ keyspace, automation must **HOLD/ABORT** any wave taking down a second replica of the same partitions, even if pre-approved earlier.

### 5.6. Guards for Java connections

Cassandra node availability is insufficient if the Java Driver:

- Uses the wrong `localDatacenter` and discovers only remote-DC nodes.
- Has misconfigured contact points/routing, leaving too few coordinators in its pool.
- Triggers a thundering herd of reconnects when a node returns.
- Retries/speculates excessively, diverging physical attempts from logical QPS.
- Prepares new CQL before schema agreement/metadata settle.

A sound rollout verifies **app-side success/errors/in-flight** in addition to server-side replica counts.

## 6. Rollout order: canary, single-wave, rack/DC spread, and anti-affinity

### 6.1. Canaries must be chosen deliberately

Do not blindly pick the first node alphabetically. Choose a canary that:

- Shares the target hardware, storage, JDK, and Cassandra version.
- Carries representative traffic while **not** being the last healthy replica of a critical range.
- Has no active bootstrap, replace, repair, or abnormal compaction backlog.
- Has full log/metric collection and rollback readiness with on-call staffing.
- Has sufficient disk/CPU/GC headroom for cold caches and commitlog replay.
- For multi-DC changes, includes a canary per **DC/role/zone** gated by that DC's applications.

A zero-traffic canary will not catch hot-partition bugs; after the canary, run **representative token/DC/query-family probes**.

### 6.2. Wave ordering is more than a list of IPs

~~~text
Plan:
  wave-0: canary node A (dc1/rack-1)
  wave-1: node E (dc1/rack-2)
  wave-2: node J (dc1/rack-3)
  wave-3: nodes in dc2, each gated

Before each wave:
  recompute replica intersection
  check current available nodes
  evaluate critical-keyspace CL
  check disk/streaming/repair/latency
~~~

This is an **illustrative ordering diagram**, lacking token maps proving A/E/J never share natural replicas. A real plan pulls topology metadata from the cluster and workload registry/known token ranges to evaluate safety predicates. When evidence is missing, set `concurrency=1` or **HOLD**—never assume safety.

### 6.3. Cassandra anti-affinity differs from scheduler anti-affinity

A rack or availability zone usually marks a physical failure domain. Cassandra `GossipingPropertyFileSnitch`/`NetworkTopologyStrategy` uses DC/rack info to place replicas. Kubernetes `podAntiAffinity`/`topologySpreadConstraints` spreads pods across hosts/zones. Yet the two can diverge if labels, snitches, rack maps, or topologies drift.

**Only after verifying live topology** can rack constraints inform concurrency. A ConfigMap saying `rack=r1` does not guarantee Cassandra actually registered that rack.

### 6.4. Waves track host IDs/tokens, not just pod names

A pod can be recreated with the same name yet a different host ID, tokens, or storage mount. If automation tracks only `cassandra-2`, an operator could apply a rollout onto a replacement node instead of a routine restart. Record:

~~~text
planned_node:
  logical_name: cassandra-dc1-rack2-2
  host_id: "expected stable UUID"
  datacenter: "dc1"
  rack: "rack2"
  token_digest: "expected tokens fingerprint"
  storage_identity: "expected PVC/volume identity"
  intended_action: "restart_process"
~~~

This is an **example manifest**, not standard `cass-operator` config; never fabricate random IDs as expected host IDs in production. Before acting, compare expected vs. observed; mismatch → **STOP**.

### 6.5. Never advance automatically after a watchdog timeout

A node restart can take longer due to commitlog replay, JVM warm-up, or hints/caches. If automation waits 5 minutes and hits its deadline, **never automatically restart the next node**. Exhausting the time budget means **HOLD/ABORT and inspect**, not "assume the old node finished."

## 7. Distinguishing concurrency types across the system

| Concurrency type | Unit | Example guard | Impact if exceeded |
|---|---|---|---|
| Node restart | Unavailable nodes | 1 cluster-wide or proven by replica set | Loss of CL/quorum |
| JVM/config rollout | Nodes on new config | One canary, then gated waves | Mixed config/format/routing bugs |
| Schema migration | DDL writer | **One migration owner** | Schema disagreement / DDL races |
| Full repair | Repair sessions/token ranges | Resource-budgeted tasks only | Disk/network/compaction overload |
| Streaming/replace | Bootstrap/replacement job | Very low limit, per DC/rack/range | Token/data migration risk |
| Major compaction | SSTable rewrite | Per node / I/O headroom | Full disk / read p99 spikes |
| App pods | Traffic-serving instances | `maxUnavailable`/`maxSurge` + SLO | Client reconnect storms / query errors |
| Reconciliation workers | Unknown business ops | Bounded concurrency/rate | Retry storms / duplicate side effects |

Never share a single `MAX_PARALLEL=5` across all tasks. One repair can consume far more I/O than an app pod rollout; two node restarts might pass replica counts yet **fail dangerously** if they saturate shared storage or network.

### 7.1. A single wave contains sequential, non-concurrent steps

~~~text
Within one node wave:
  Acquire lease
     -> Preflight
     -> Drain (if planned)
     -> Stop process
     -> Replace binary/config
     -> Start process
     -> Wait readiness
     -> Verify data/CL
     -> Soak + release lease
~~~

This is a **strict sequence**. Parallelizing `drain` and `stop` defeats graceful shutdown. Running backup/snapshot/repair concurrently with a restart also requires explicit owner and I/O-budget approval, never assumed safe.

### 7.2. Token-range concurrency budgets

A controller can construct a conflict graph:

~~~text
node A ---- shares critical replica set ---- node B
node A ---- independent enough -----------> node E
node B ---- shares critical replica set ---- node F

Conflict edge A-B:
  must never be offline together under this CL.
~~~

Pick wave nodes from an **independent set** of the graph, then enforce resource and business budgets. Across multiple keyspaces and token ranges, computing this accurately is non-trivial; without authoritative metadata proving the graph, never approximate from rack names.

### 7.3. A node that is not DOWN can still lose capacity

Unthrottled compaction or repair may keep a node `UN` while spiking read p99, timeouts, and hinted handoff. Resource budgets must therefore track **busy nodes**, not merely `inFlightRestarts`. Restarting A while B runs full repair and C sits at 95% disk can break quorum latency even though B and C are nominally "UP."

### 7.4. Start conservative, expand only with evidence

Practical rule of thumb: without full replica-set intersection analysis, start with **one node at a time for downtime actions** and **zero concurrent heavy repairs**. Still, never claim "one node at a time guarantees zero downtime": under RF1/2 or `ALL`, even a single node can cause an outage.

## 8. Preflight: is there enough evidence to begin?

### 8.1. Verifying cluster identity and change scope

Before running, record:

- Cluster ID/name, cloud/region, DC/rack, and allowlisted CQL/JMX endpoints.
- Current and target Cassandra/JDK/driver/operator versions.
- Exact **host IDs, token ownership, network addresses, and storage identities**.
- Critical keyspaces, per-DC RF, read/write/LWT CLs, and hot token ranges/tenants.
- Operation type: binary/config restart vs. topology/data-ownership change.
- Package SHA/checksum, container image digest, config diff, and target state.
- Change owner/approver, maintenance window, on-call contact, and rollback authority.
- Latest backup/snapshot/restore-test timestamp and restorability.

**Never** rely solely on the cluster name returned by `nodetool describecluster`; two environments can share the same cluster name. Verify independent inventory, identities, credentials, and network allowlists.

### 8.2. Read-only commands for preflight

~~~bash
# Only on authorized Cassandra clusters.
# Each command requires appropriate JMX/host permissions.
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
~~~

Notes:

- `nodetool status` relies on gossip and can vary across nodes; query multiple nodes if a network partition is suspected.
- `describecluster` displays schema versions; agreement does not prove data is repaired.
- `tpstats` reports pending/dropped tasks in thread pools.
- `netstats` reports streaming; active streaming is not automatically a failure yet competes for disk/network.
- `compactionstats` shows active/pending compactions; `pending=0` is not required under steady writes.
- `gcstats` gives a GC snapshot; combine with continuous metrics and GC logs.

### 8.3. CQL checks for topology and keyspace contracts

~~~sql
SELECT cluster_name, data_center, host_id,
       release_version, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='orders';
~~~

In labs, substitute `orders` with an authorized keyspace; never edit system schemas. `system.local` reflects the **local view of the connected coordinator**, so connect directly to each authorized node to compare versions across nodes.

### 8.4. Difference between status, availability, and readiness

| Signal | Reliable to confirm | Insufficient to confirm |
|---|---|---|
| `UN` in ring | Node viewed Up/Normal by gossip | All app requests satisfy CL |
| JMX responds | JVM exposes management endpoint | Native CQL transport serves normally |
| Port 9042 open | Socket listener active | CQL auth, schema, and queries work |
| `SELECT system.local` | Basic internal query works | User keyspace natural replicas satisfy CL |
| `SELECT by primary key` at `ONE` | One replica can return data | Local/global quorum and data completeness |
| Driver ready / pool connected | Can dispatch requests | New schema/metadata synced and p99 healthy |
| K8s Pod Ready | Defined probe passed | Cassandra business readiness if probe checks only port |

A trustworthy rollout gate is the **intersection of multiple independent signals**. If Cassandra/JVM/driver telemetry drops out, never assume "zero errors"—treat it as **loss of visibility** → HOLD.

### 8.5. Precondition invariants

~~~text
Before wave N:
  no unapproved schema migration running
  no unexpected UN->DN transition
  no conflicting backup/restore/repair/bootstrap
  enough replica/CL headroom for chosen wave
  free disk and CPU/network headroom
  app-level baseline SLO within bounds
  controller lease is sole owner
  rollback/recovery path is documented
~~~

These preconditions must be **re-evaluated after every wave**. Invariants holding before wave 1 are not guaranteed if hardware fails during wave 2.

## 9. Reproducible rollout manifest

### 9.1. Tool-agnostic declarative template

~~~yaml
# PSEUDOCODE/YAML DATA MODEL — not a cass-operator manifest
run:
  run_id: cassandra-rolling-config-2026-11-21-01
  environment: isolated-staging
  cluster_identity: expected-host-id-set-and-cert-fingerprint
  change_type: cassandra_process_config_restart
  source_version: "4.1.x"
  target_version: "4.1.x"
  change_digest: "sha256-of-reviewed-config-package"
  approved_by: "cassandra-ops-owner"
  start_window_utc: "2026-11-21T01:00:00Z"
  end_window_utc: "2026-11-21T03:00:00Z"
  dry_run_first: true

topology:
  datacenters:
    dc1:
      racks: [rack1, rack2, rack3]
      nodes: 3
      critical_keyspaces:
        - name: orders
          full_rf: 3
          normal_read_cl: LOCAL_QUORUM
          normal_write_cl: LOCAL_QUORUM
  known_degraded_nodes: []

rollout:
  batch_size_initial: 1
  max_global_unavailable_nodes: 1
  max_per_dc_unavailable_nodes: 1
  forbid_replica_set_quorum_loss: true
  forbid_restarts_on_joining_or_replacing_nodes: true
  canary_count: 1
  max_inflight_waves: 1
  cooldown_between_waves_seconds: 120
  max_wave_duration_seconds: 1800

gates:
  require_expected_node_identity: true
  require_cassandra_up_normal: true
  require_native_transport: true
  require_schema_agreement_among_up_nodes: true
  require_expected_token_set: true
  require_cl_data_probes: true
  require_driver_query_probes: true
  error_rate_max_percent_example: 0.5
  p99_latency_ms_max_example: 150
  disk_free_min_percent_example: 25
  steady_windows_required: 5
  window_seconds: 60
  abort_on_new_down_node: true

recovery:
  on_gate_timeout: HOLD
  on_data_mismatch: ABORT
  on_unknown_action_outcome: HOLD_AND_RECONCILE
  rollback_requires_approval: true
~~~

This is an **illustrative data model**. Field names like `forbid_replica_set_quorum_loss` or `steady_windows_required` are **not** built-in Cassandra YAML, Kubernetes PDB, or `cass-operator` options. Real execution requires implementing/testing controller logic and telemetry collection. Thresholds such as 0.5%, 150ms, and 25% are hypothetical; real SLOs/guardrails depend on workload, storage, RF/CL, and baseline.

### 9.2. Manifests must never contain secrets

Never embed Cassandra passwords, JMX tokens, private keys, or raw customer IDs into rollout YAML. Use references to least-privilege secret managers/identities; audit logs record only change hashes/IDs. **Never share** manifests exposing sensitive hostnames and topology outside authorized operations scope.

### 9.3. Why is `change_digest` needed?

When a controller crashes and resumes, it must verify that target artifacts/configs **remain the exact approved revision**. If a mutable `latest` image tag changes mid-rollout, wave N could run a different binary than wave N+1. Pin:

- Container image digests or binary package checksums.
- Rendered `cassandra.yaml` diff/checksum, not just a Git branch.
- JVM arguments and JDK version.
- App/driver/sidecar/operator versions.
- Compatibility feature modes required by the upgrade guide.

### 9.4. Separate `run_id`, `action_id`, and `node_id`

~~~text
run_id    = one rollout campaign
wave_id   = one bounded group of changes
action_id = one intended side-effect on a specific node
attempt_id= one network/API attempt to perform that action
node_id   = stable Cassandra host ID + expected token/volume identity
~~~

An HTTP request to an operator timing out does not prove the action never started. **Never issue a fresh `restart node` with a new `action_id`** until reconciliation confirms the node's state and whether the previous action is still in flight.

### 9.5. Never treat an approved batch size as permission to bypass gates

`batch_size=1` is an **upper cap**, not a mandatory execution target. If cluster health degrades, permitted concurrency drops to **0**. Controllers should compute `effective_batch_size = min(configured_cap, safety_budget, resource_budget)` and **HOLD** when it equals 0.

## 10. Time-window gates: observe trends, not a single snapshot

### 10.1. Difference between startup, recovery, and steady state

~~~text
T0  node process restarted
T1  JVM/Cassandra system tables load
T2  gossip UP / native transport ready
T3  driver reconnect and metadata refresh
T4  CQL at required CL succeeds
T5  cache warms, hints/streaming/repair backlog drains
T6  p99/error/GC/disk trend returns to accepted range
T7  wave declared healthy
~~~

Timings T0..T7 depend on dataset size, commitlog replay, JVM warm-up, disk, repair, workload, and cluster size; **no fixed 60-second sleep** guarantees Cassandra readiness. During bootstrap/replace, T5 can also include streaming/repair per topology runbook.

### 10.2. Rolling-window gate example

Suppose a business SLO for a query family specifies p99 <= 150ms, error rate < 0.5%, target QPS 2,000/s (**illustrative** figures):

| Gate | Example condition | Evidence |
|---|---|---|
| Availability | No new `UN→DN` transitions outside expected node | `nodetool status` from multiple peers |
| Data correctness | Known-key sentinel at `LOCAL_QUORUM` returns expected revision/value | CQL/Java business probe |
| App success rate | Error rate < 0.5% across 5 consecutive windows | End-to-end app metrics |
| Latency | p99 <= 150ms for every critical query family | Histogram with sufficient samples |
| Throughput | Completed QPS stays near offered QPS without retry/throttle drops | Client/generator |
| Background tasks | Repair/streaming/compaction queues not accumulating | `netstats`/`compactionstats`/JMX |
| Resources | Disk free/GC/network/CPU/await maintain headroom | Host + Cassandra metrics |
| Driver | Pool connected; in-flight/retries stable | Java Driver metrics |

If a query family receives only 50 requests per minute, a 60s window p99 is far less reliable than 100,000 samples; widen the window or report raw results/upper bounds. **Never report percentiles without sample counts.**

### 10.3. Minimal inter-wave gate

~~~text
For each of 5 consecutive windows:
  available replica sets pass CL contract
  data oracle probes pass
  no new unexpected DOWN node
  app p99 within SLO (with enough samples)
  error/timeouts/retries within budget
  disk/GC/queue/streaming trends acceptable

Only THEN release wave lease and proceed.
~~~

If metrics disappear or the query oracle lacks reference data, return **UNKNOWN**—never default to pass. If windows fail while recovery is visibly progressing, HOLD up to a deadline; past deadline → ABORT/escalation.

### 10.4. Compaction can always be running

Do not enforce `PendingCompactions=0` strictly under write-heavy workloads; Cassandra routinely compacts continuously in steady state. What matters is whether backlogs, bytes, active tasks, and I/O remain **bounded** rather than growing endlessly. Conversely, `PendingCompactions=0` at one instant does not prove disk, tombstones, or p99 are healthy.

### 10.5. Latency looking "artificially good" because slow requests time out

A rollout can appear to lower p99 of successful requests simply because the slowest requests **fail and drop out of the success histogram**. Gates must report **timeouts, cancelled requests, unknown write outcomes, and retries/speculative attempts** alongside latency. Never call lower success p99 a PASS if error rates climbed.

## 11. Phasing a rolling change: from canary to post-soak

### 11.1. P0 — Preparation

1. Lock down keyspaces + read/write CLs + natural replica sets/critical queries.
2. Verify version/compatibility of target binaries and configs.
3. Capture baseline node/gossip/schema/data probes, app SLOs, and resource headroom.
4. Confirm backups/snapshots/rollback plans per change type without assuming snapshots restore instantly.
5. Acquire cluster lease/lock and block competing maintenance windows.
6. Select the canary and wave sequence; dry-run candidate evaluations.
7. Obtain approvals/owners, stop thresholds, and maintenance deadlines.

### 11.2. P1 — Canary

1. Re-run preflight immediately before acting.
2. Drain/remove candidate node from traffic per runbook (if required) without altering metadata/token ownership.
3. Execute one action with a stable `action_id` and event logging.
4. Observe startup/health/CL/schema/driver probes.
5. Hold a soak window; check data oracles and latency on representative keys.
6. If PASS, checkpoint `CANARY_VERIFIED`. If FAIL, **stop advancing**.

### 11.3. P2 — Subsequent waves

~~~text
for each wave:
  refresh topology and client observed health
  recompute safety budget
  verify no outstanding unknown action
  execute <= effective_batch_size
  observe all applicable gates
  checkpoint verified results
  proceed only on explicit GO
~~~

This is **pseudocode**; do not run against production without atomic leases and consistent APIs/policies. Never loop blindly across hostnames while an earlier node has not recovered.

### 11.4. P3 — Post-rollout

After the last node:

- Confirm every expected host ID, token, rack, DC, and state with zero unplanned replacements.
- Verify application releases, driver metadata, and schema compatibility.
- Run read/write business probes at contracted CL across representative token ranges.
- Monitor cache warm-up, GC, flush/compaction/repair/streaming, and disk as load returns.
- Collect errors/timeouts/p95/p99 over a post-rollout soak window.
- Confirm uniform package/config digests per the **planned compatibility stage**.
- Mark `COMPLETED` only when all post-rollout gates PASS.

### 11.5. P4 — Audit and postmortem if needed

Archive node/wave timestamps, input manifest checksums, observed per-gate health, operator actions/manual overrides, rollback/recovery steps, durations, and unresolved risks. If halted mid-way, preserve a **resume plan** recording per-node state rather than restarting blindly from wave 0.

## 12. Runbook: rolling restart of the Cassandra process

### 12.1. Distinguish routine restart from node replacement

**Routine restart:** Same logical Cassandra node, host ID, token ownership, and data directory/volume. May change JVM options/config or restart the service, without creating a new node or shifting token ownership.

**Replacement:** A dead node or lost volume replaced by another node; can introduce a new host ID, bootstrap/streaming, hints/repair, and altered data placement. This is a **distinct topology-change procedure**, never folded into a rolling restart script.

Whenever automation detects an unexpected host ID or token digest after pod recreation, **STOP**. Never treat matching pod names as a "successful restart."

### 12.2. Pre-drain checks

~~~text
Candidate node A:
  - planned host ID/tokens match observed
  - no unexpected DN/UJ/UL/UM nodes elsewhere
  - per-keyspace/token replica budget PASS if A unavailable
  - app QPS/error/p99 baseline acceptable
  - disk free/commitlog/GC/compaction headroom adequate
  - no conflicting repair/replace/backup operations
  - controller holds exclusive lease
  - operator approved the exact config/image digest
~~~

If another replica just went DOWN or `netstats` shows ongoing streaming, never proceed merely because the maintenance window is shrinking.

### 12.3. `nodetool drain` is a state-mutating operation

Per Cassandra documentation, `nodetool drain` **stops accepting writes and flushes all tables** in preparation for node shutdown. It is **not an observation command** and must never be run to test node health.

~~~bash
# PSEUDOCODE RUNBOOK — only on authorized nodes
# 1. Quiesce/redirect traffic if required by deployment design.
# 2. Check topology and all gates first:
nodetool status
nodetool tpstats
nodetool compactionstats

# 3. Immediately before approved graceful shutdown:
nodetool drain

# 4. Stop/start using approved service manager or operator.
#    The exact systemctl/Kubernetes/API action is environment-specific.
~~~

After draining, the node must not be treated as serving writes normally until properly restarted. If `drain` succeeds yet the stop/restart API times out, the controller must **reconcile actual process state** rather than advancing to another node or looping `drain`.

### 12.4. Never assume every platform requires manual `drain`

A `cass-operator`, management layer, or service shutdown hook may already sequence graceful stop/`drain`. Calling `drain` manually beforehand when the operator expects another flow can desynchronize state machines or prolong downtime. Follow your **deployment's runbook**: one actor owns each lifecycle transition.

### 12.5. Multi-gate post-restart verification

~~~text
Process JVM started
     |
JMX/management API available
     |
Gossip reports node Up/Normal
     |
Native transport CQL + authentication works
     |
Schema metadata and driver route recognize node
     |
Known-key CL reads/writes (where authorized) PASS
     |
No unexpected streaming/repair failures
     |
App SLO / driver retries / GC / disk stabilize
     |
Wave VERIFIED
~~~

`nodetool status` showing `UN` is necessary yet **insufficient**. If the node remains `UJ` (joining), `UL` (leaving), or `UM` (moving), this is not a completed routine restart; block the next wave and investigate topology.

### 12.6. Warning about cold caches after restart

JVM caches and driver connections cool down; OS page caches may stay warm on process/container restarts depending on host/volumes. Hints catch-up, commitlog replay, and compaction can consume I/O post-startup. Never use `sleep 30` or a single `system.local` query p99 as the recovery gate.

### 12.7. What to do if a restart fails?

| State | Action |
|---|---|
| Process has not stopped, action response lost | Reconcile process/host ID; do not blindly issue a second stop |
| Drained, yet restart has not run | HOLD; owner handles drained node |
| Process started, yet gossip `DN` | Check logs/internode/JVM/disk; do not restart other nodes |
| Gossip `UN`, yet CQL auth/schema fails | HOLD; investigate CQL transport/config/DDL |
| CQL PASS, yet CL data probe fails | HOLD; inspect replicas/ownership/data |
| CL PASS, yet p99/GC/disk poor | HOLD/evaluate rollback; do not declare recovered |
| Storage identity/tokens changed | **ABORT + topology incident** |

### 12.8. Never use `removenode`/`decommission` for routine restarts

`nodetool decommission`/`removenode` alter ownership and trigger streaming/data redistribution; they are **not** "pull node from load balancer to restart." Misuse causes unintended topology shifts and costly repair/cleanup. For real node replacements, use a dedicated replacement plan and version-matched topology docs.

## 13. Rolling binary upgrades and configuration

### 13.1. Binary changes carry version constraints

Rolling Cassandra 4.1.x → 4.1.y within a minor line, 4.1 → 5.0, or changing JDK/compaction strategy/feature flags **do not share the same rules**. Major upgrades require:

- Verifying upgrade paths and compatibility across Cassandra + JDK + driver.
- Verifying mixed-version cluster compatibility during the rolling phase.
- Ensuring no CQL/feature/index/compaction option understood only by new nodes is enabled while old nodes remain in service.
- Checking rollback restrictions once on-disk/data formats change.
- Confirming repair, schema migration, and SSTable upgrade strategies separately.

Never automatically run `nodetool upgradesstables` or push new features cluster-wide as soon as the canary comes up; doing so triggers heavy disk I/O and alters rollback options.

### 13.2. Compatibility modes in Cassandra 5.x

Cassandra 5.0 configuration docs describe `storage_compatibility_mode` with compatibility stages transitioning `CASSANDRA_4` → `UPGRADING` → `NONE` along supported upgrade paths. These steps can require **multiple rolling restart passes**; never combine all three modes into one wave or enable `NONE` while incompatible older nodes remain.

This is a **version-specific example**, not a universal recipe for every upgrade; check Cassandra 5.x documentation and your exact supported source version before running. Source: [cassandra.yaml reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html).

### 13.3. Canaries check both version and behavior

~~~text
Before canary:
  source binary hash, JDK, config hash captured
  schema/data/driver baseline captured

After canary:
  expected release_version on node
  same expected host_id and token ownership
  native transport and app CQL probe PASS
  p99, GC, disk, compaction in range
  driver handles mixed-version cluster
  no new warnings/errors from upgraded binary
~~~

If a new feature works only once the entire cluster finishes upgrading, **never** enable it on the canary and claim older nodes are compatible.

### 13.4. Dynamic vs. restart-required configuration

Some Cassandra settings update via `nodetool`/JMX/runtime APIs (if supported by version); others require process restarts; still others carry **data/topology impacts**. Classify upfront:

| Change | Appropriate rollout method | Additional gates |
|---|---|---|
| Runtime log level | Authorized runtime API | Log volume, disk/CPU |
| Compaction throughput | Runtime/config per version | Pending compaction bytes, disk I/O |
| Heap/JVM flags | Rolling process restart | GC pauses, OOM risk, startup time |
| Snitch/DC/rack mapping | **Topology-sensitive** | Replica placement/ring; separate runbook |
| Storage compatibility mode | Version-controlled rolling phases | Binary compatibility and data format |
| RF/keyspace | Schema change + data distribution | Repair/streaming and CL probes |
| Table compaction strategy | DDL + background SSTable rewrite | Disk headroom, read/write p99 |

**Never treat every edit to `cassandra.yaml` as a "pure config change."** Some alter distributed behavior, restarts, or on-disk data layout.

### 13.5. Rollbacks need a feasibility matrix

~~~text
Change A: logging config -> restore previous value
Change B: JVM heap setting -> revert and restart, preserving quorum
Change C: binary major upgrade -> rollback MAY be unsupported
Change D: schema DROP COLUMN -> rollback may lose data
Change E: node replacement -> data/topology procedure, not simple revert
~~~

Approvers must know **what is reversible** prior to rollout. Never write a generic `rollback: restart_old_binary` for major-version upgrades without verifying release compatibility.

## 14. Rolling application deployments and Java Driver metadata

### 14.1. Why can changing the Java app also cause a Cassandra outage?

A new app version might:

- Reference new CQL/keyspaces/tables/indexes before migrations finish.
- Change `withLocalDatacenter` or connection pooling so the driver loses coordinators.
- Raise request concurrency, retries, or speculative executions, multiplying physical load.
- Issue LWTs at `SERIAL` instead of `LOCAL_SERIAL`, altering WAN/latency behavior.
- Use a different CL, causing `Unavailable` errors or stale reads if lowered.
- Run DDL on every pod startup, creating schema races.
- Prepare statements against tables not yet propagated to all nodes.

Therefore, roll out apps **separately** with canaries/metrics/rollbacks, rather than concurrently with Cassandra rolling restarts unless governed by a joint change plan.

### 14.2. Gates before app deployment

~~~text
Versioned DDL migration completed by ONE runner
       |
Schema agreement among relevant UP nodes
       |
Expected table/columns/PK verified
       |
Application vN+1 can PREPARE representative CQL
       |
Driver local DC, auth/TLS, pool/routing validated
       |
Canary app pods serving small traffic percentage
       |
Data/CL + p99/error/retry gates
       |
Expand traffic with bounded maxUnavailable/maxSurge
~~~

`IF NOT EXISTS` in DDL does not confirm **existing table definitions** match expected schema. When old and new binaries share a table during rolling app deploys, prefer expand–migrate–contract: add compatible columns, backfill, switch code, and drop old dependencies only after verification.

### 14.3. Application concurrency differs from node concurrency

Setting `maxUnavailable=1` or `maxSurge=1` on an app Deployment/StatefulSet bounds pod transitions, yet **does not** cap concurrent Cassandra requests if new pods open excess connections or retries. Enforce driver/request throttling, backpressure, and warm-up gates.

### 14.4. Retries are not readiness

If the driver retries 20 times before an HTTP call "succeeds," business p99 can blow up while Cassandra absorbs 20 physical attempts. Track **logical requests vs. node messages/attempts**, timeouts, LWT unknown outcomes, JMX ClientRequest latency, and pools/in-flight counts. Never treat "5xx dropped" as the sole criterion if retries multiplied.

### 14.5. Diagnosing `unconfigured table` after an app rollout

~~~text
Old app CQL: orders_by_id (status, revision)
New app CQL: orders_by_id (status, revision, new_field)
Schema migration ADD new_field not yet applied
                         |
                PREPARE/SELECT fails
~~~

**STOP/HOLD** the app rollout; inspect `system_schema.columns`, schema agreement, and query strings/driver metadata. Never `DROP TABLE` or unconditionally restart Cassandra to "refresh."

## 15. Coordinating repair, streaming, backups, and compaction

### 15.1. Tasks that do not mark a node DOWN can still cause risk

Repair, streaming, compaction, and backups keep nodes `UN` while saturating disk, network, or CPU. Restarting node A while B runs repair and C carries a heavy compaction backlog keeps B+C count at 2, yet **latency/ACKs may breach SLO**.

~~~text
RF3 replicas: A, B, C

A: planned restart (unavailable)
B: full repair / streaming at high disk I/O
C: compaction + client writes saturating disk

Logical quorum: B + C = 2
Practical quorum before timeout: maybe not.
~~~

Enforce **maintenance mutual exclusion / I/O budgets** across natural replica sets, not just `maxUnavailable`.

### 15.2. Repairs require coverage and ownership

Per Apache Cassandra docs, repair synchronizes data ranges via anti-entropy/streaming; hinted handoff is strictly **best effort**, never a replacement for repair. Repair is resource-intensive and must be scheduled. On versions supporting `nodetool repair -pr` (primary ranges), schedule thoughtfully to cover cluster-wide ranges without duplicating work on the same token ranges due to misunderstood flags.

~~~text
Maintenance plan:
  identify keyspace + token ranges
  identify involved replicas + DC
  choose one bounded repair task
  monitor streaming/anticompaction/IO
  verify coverage and backlog
  then start next task
~~~

**Never** run `nodetool repair -pr` on every node simultaneously just to finish faster; overlapping resource domains can take the cluster offline. Because full/incremental repairs, pending sessions, and compaction states differ by Cassandra version, follow version-specific runbooks.

### 15.3. Backups/snapshots do not prove data recovery readiness

`nodetool snapshot` or a backup orchestrator copies SSTables, yet "snapshot job succeeded" does not prove **restores work**, commitlog/PITR coverage exists, or schema manifests are complete. Before risky config/binary rollouts, verify the latest snapshot/backup and restore test; avoid running concurrent snapshots that fill disks.

### 15.4. Streaming after bootstrap/replace

`nodetool netstats` reports streaming progress from a node's viewpoint. After topology changes:

- Never use `UN` alone to skip streaming/data verification.
- Verify token ownership, RF/DC, and new natural replicas.
- Run repairs if required by outage duration, hints, and replacement mechanics of your **exact Cassandra version**.
- Run `cleanup` on nodes that shed token ownership only once topology and streaming stabilize and the runbook permits.

`cleanup`, `decommission`, `rebuild`, and `replace` are data/topology operations **never to be tucked automatically into a rolling restart job**.

### 15.5. Classifying maintenance before scheduling

| Task | Run concurrently with node restart? | Decision basis |
|---|---|---|
| Read-only metrics scrape | Usually yes, rate-limited | Negligible load |
| Snapshot/backup | Only after resource/space review | Disk headroom and consistent backup manifest |
| Incremental repair | Needs overlap/range/I/O proof | Replicas, streaming, compaction pressure |
| Full repair | Strictly restricted | Disk/network, data amplification, duration |
| Major compaction | Avoid overlapping node restarts | SSTable rewrites and free space |
| Bootstrap/replacement | **Separate change plan** | Token ownership/streaming/natural replicas |
| Schema migration | Serial owner, coordinated with app | Schema agreement and backward compatibility |

This is **risk guidance**, not a Cassandra command forbidding concurrency. Certain tasks can overlap when evidence, headroom, and expert approval exist; automation defaults conservatively.

## 16. Kubernetes, StatefulSets, and cass-operator: automation must not bypass the controller

### 16.1. PDBs protect only partially

A Kubernetes `PodDisruptionBudget` limits **voluntary evictions** for selector-matched pods; it does not guarantee:

- Cassandra holds enough natural replicas at the required CL.
- All token ranges retain quorum.
- The node completed graceful shutdown/drain/streaming safely.
- Java Driver apps routed onto healthy replicas.
- Remaining pods have disk/GC/network headroom.

With `maxUnavailable: 1`, a PodDisruptionBudget is a **supplemental guardrail**, not a replacement for Cassandra-aware rollout gates.

### 16.2. StatefulSet readiness/ordering

Kubernetes StatefulSets provide ordered rollout semantics driven by policy and readiness probes. If a readiness probe checks only port `9042` or container RUNNING, the scheduler marks pods READY far earlier than Cassandra CL/data/performance readiness. Align readiness definitions with the operator and monitor Cassandra-native metrics.

### 16.3. `cass-operator` has its own lifecycle controller

In K8ssandra/`cass-operator`, the Management API and operator manage node lifecycles; newer versions provide `CassandraTask` for operational jobs including rolling restarts. Some CRDs expose `fast`/`force` and other release-specific controls. **Check your exact CRD/operator version**:

- Never enable `fast` merely for speed: some modes restart multiple nodes/racks concurrently.
- `force` can bypass operator safety checks; never enable it to "push past gates" on a degraded cluster.
- Legacy fields like `rollingRestartRequested` are deprecated in newer CRDs; use current APIs.
- Never run `kubectl delete pod --all` or directly edit StatefulSets while the operator is reconciling another plan.

References: [K8ssandra cass-operator](https://docs.k8ssandra.io/components/cass-operator/) and [CRD reference](https://docs.k8ssandra.io/reference/crd/cass-operator-crds-latest/index.html).

### 16.4. Illustrative PDB, not a safety proof

~~~yaml
# Illustrative Kubernetes PDB; do not deploy directly.
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-example-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: cassandra-lab
~~~

A PDB matches only if its selector covers the right pods; in operator-managed clusters, the operator typically creates/manages the PDB and operators should avoid creating duplicates. Never assume a PDB prevents pod crashes, node failures, force deletes, or all forms of rolling updates.

### 16.5. Do not confuse `minReadySeconds` with data recovery

`minReadySeconds` (if supported by the controller/version) requires a pod to remain Ready for a minimum interval. It helps dampen quick "ready flaps," yet still depends on the **Ready probe definition**; 30 seconds of Pod Ready does not prove data repair, hints, compaction, and p99 have settled.

### 16.6. Operator status and external controllers must align

If a cluster uses `cass-operator` alongside external automation, enforce a **single owner** per lifecycle action rather than issuing direct commands that the operator might undo. Inspect `CassandraTask`/`K8ssandraTask` statuses and node states **after** actions; if a Task reports Completed while CQL/CL data probes FAIL, the application-side controller must **HOLD**.

### 16.7. Four scenarios to block immediately

~~~text
K8s Pod Ready = true, Cassandra node DN   -> HOLD
Operator Task Completed, app LOCAL_QUORUM fails -> HOLD
PDB maxUnavailable=1, another replica already failed -> HOLD
Operator rolling restart in progress, external job requests decommission -> STOP
~~~

Never raise PDB `maxUnavailable: 100%` or toggle operator `force` just to push through a stalled rollout. Diagnose why the gate failed, collect logs/state, and follow incident procedures.

## 17. Controller design: idempotency, fencing, locking, and recovery

### 17.1. Auditable state machine

~~~text
PLANNED
  |
VALIDATING -----> BLOCKED (preflight fails)
  |
LEASED
  |
ACTION_SUBMITTED
  |
OBSERVING
  |           \\
  |            +----> UNKNOWN_ACTION_OUTCOME
  |                         |
  |                       RECONCILE
  |                         |
  |           +-------------+
  v           v
GATES_PASS  GATES_FAIL ----> HOLD/ABORT
  |
WAVE_COMMITTED
  |
NEXT_WAVE / DONE
~~~

**Never** ignore `UNKNOWN_ACTION_OUTCOME` just because a call to Kubernetes/JMX/operator APIs timed out. The action may already have executed; query actual node state and action ID before retrying.

### 17.2. Cluster- or maintenance-domain-scoped lock/lease

Controllers need mutual exclusion:

~~~text
Lease key = cluster-id + maintenance-domain
Lease owner = rollout-run-id
Fencing epoch = monotonically increasing number
TTL/renewal = bounded and observed
~~~

If a controller loses its lease, it must **stop issuing new actions**; if another controller acquires the lease, the stale actor must never "wake up" and act on stale state. Leases must be enforced **at the execution boundary** via fencing tokens; in-memory locks alone cannot prevent split-brain.

### 17.3. Checkpointing before and after side effects

~~~text
Persist ACTION_INTENT(node=A, config_hash=X)
  |
Call restart via owner API
  |
API call times out?
  |
Read observed process/pod/node status
  |
Match expected action outcome and identity?
  |
Persist ACTION_VERIFIED or UNKNOWN/HOLD
~~~

If checkpoints are written only after restarts finish, a mid-action controller crash cannot tell whether A restarted. Blind retries could restart A a second time right as it recovers.

### 17.4. Retries must distinguish transient from permanent errors

| Error | Retry? | Before retrying |
|---|---|---|
| Metrics API timeout | Bounded | Check another source; never treat as PASS |
| Operator action submission timeout | **Do not replay blindly** | Query action ID, controller state, and node state |
| Cassandra node down after restart | Only with owner diagnosis | Check logs, data, and host ID before restarting again |
| Wrong node identity / config digest | **No** | STOP and inspect inventory |
| `InvalidQuery` due to unapplied schema migration | **No** | Fix DDL/order of operations |
| `Unavailable` at required CL | Never mask by lowering CL | Restore replicas/availability |
| Repair task failure | Dedicated runbook | Inspect tokens, partial streaming, resources, disk |
| Host disk full | **No** | STOP and recover |

Use backoff/jitter for transient read/poll APIs; side-effect retries require explicit **idempotency/fencing semantics** and observed-state evidence.

### 17.5. Deadlines and cancellation

Every wave defines:

- `action_deadline`: time limit for the control action to start/finish.
- `node_ready_deadline`: time limit for the node to enter serving state.
- `data_cl_deadline`: time limit for CQL at required CL and correctness probes to pass.
- `performance_deadline`: time limit for SLO, queues, and resources to return within bounds.
- `maintenance_window_deadline`: latest timestamp allowed to start a new wave.

Breaching any deadline → **HOLD/ABORT**, never assume success or rush the next node. Cancellation may only halt **scheduling new waves**; an already-running restart or repair may need to finish cleanly rather than being safely aborted mid-flight.

### 17.6. Do not abuse optimistic controller retries

A reconcile loop running every 2 seconds could trigger restart 30 times if it fails to track `action_id` and observed transitions. Design:

~~~text
Desired state: target config installed on node A
Observed state: node A is restarting
Action record: action-17 already submitted

Controller decision:
  WAIT / OBSERVE,
  not SUBMIT new action.
~~~

**Goal:** Automation should act like a careful operator keeping a logbook, not a loop clicking "if not green yet, press the button again."

## 18. Lab A — CQL: creating a sentinel and verifying the data gate

### 18.1. Objective and constraints

This lab illustrates how to stage a **reference value verifiable post-rollout** using full primary keys and CL. It does **not** restart nodes or inject real faults.

Requirements:

- Cassandra 4.1/5.0 **single-node lab** with `cqlsh` allowed to create a dedicated namespace.
- Never use production keyspaces or delete/truncate others' data.
- RF1/`ONE` teaches CQL/gate mechanics only and **does not** support zero-downtime rolling restarts.
- Verify the real node DC via `system.local`.
- Do not confuse one sentinel record with proof that all partitions are healthy; this is a **scoped probe**.

### 18.2. Create keyspace and partition-keyed table

~~~sql
CREATE KEYSPACE IF NOT EXISTS rollout_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS rollout_lab.probe_by_tenant (
  tenant_id text,
  probe_id uuid,
  state text,
  revision int,
  updated_at timestamp,
  PRIMARY KEY ((tenant_id), probe_id)
);

CONSISTENCY ONE;
~~~

In this lab, `tenant_id` is the partition key and `probe_id` is the clustering key. All queries supply the full primary key with zero `ALLOW FILTERING` or table-wide `COUNT(*)`. In multi-DC production, keyspaces should use `NetworkTopologyStrategy` with appropriate RF; **never** use `SimpleStrategy` RF1 where HA is needed.

### 18.3. Seed a known row

~~~sql
INSERT INTO rollout_lab.probe_by_tenant
  (tenant_id, probe_id, state, revision, updated_at)
VALUES (
  'tenant-lab',
  11111111-1111-1111-1111-111111111111,
  'READY',
  7,
  '2026-11-21T00:00:00Z'
);
~~~

**Expected:** One row with `state=READY` and `revision=7`. Never run this `INSERT` in production automation as it mutates state; in production use a team-owned sentinel with dedicated value checks, or read-only known keys with strong consistency validation.

### 18.4. Read-only data gate

~~~sql
SELECT state, revision, updated_at
FROM rollout_lab.probe_by_tenant
WHERE tenant_id='tenant-lab'
  AND probe_id=11111111-1111-1111-1111-111111111111;
~~~

A real gate asserts **values**, not merely "SELECT threw no exception." For example:

~~~text
query executed               = true
row exists                   = true
state                        = READY
revision                     = 7
consistency level            = ONE  (RF1 lab)
latency / timeout            = within budget
~~~

If the query succeeds yet returns empty or `revision=6`, **the data oracle FAILS**. Do not continue to the next wave hoping "maybe the next node fixes it."

### 18.5. Check schema and keyspace replication

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='rollout_lab';

SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name='rollout_lab';

SELECT cluster_name, data_center, host_id,
       release_version, schema_version
FROM system.local;
~~~

These are read-only probes. `system.local` reports only **the current coordinator node**; to verify per-node schema versions in a multi-node cluster, query multiple nodes or run `nodetool describecluster`.

### 18.6. Why can't an RF1 lab test "safe one-node restart"?

RF1 needs one live replica for `ONE` reads/writes. When the sole node restarts, **0 replicas** remain. No quiesce trick turns RF1 into automatic HA. This lab only demonstrates authoring CQL/readiness probes. Fault-tolerant rolling restart testing requires a real cluster with RF/CL headroom and proper data manifests.

### 18.7. Canaries on RF3 must check multiple sentinel keys

In an NTS RF3 cluster:

~~~text
Probe P1 -> natural replica set {A,B,C}
Probe P2 -> natural replica set {B,D,E}
Probe P3 -> natural replica set {A,E,F}
~~~

Passing sentinel P1 at `LOCAL_QUORUM` **does not prove P2/P3** remain healthy if B restarts. Runbooks need probe coverage across representative token ranges, critical tenants, and driver routing—not just `SELECT system.local`.

## 19. Lab B — Java Driver 4.x: data-verifying readiness probe

### 19.1. Objective

This Java 17 program reads a sentinel at the **specified normal CL**, checks schema agreement across UP nodes (as visible to the driver), verifies expected metadata, and asserts row values. It does **not** restart nodes, execute DDL, write production data, or alter rollout status. Metrics, compaction, and topology signals must still be supplied by the controller.

Example Gradle Kotlin DSL dependency:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

For driver 4.17.x, use the corresponding supported group/version; never mix driver artifacts across major versions.

### 19.2. Complete Java 17 program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;

public final class CassandraRolloutProbe {
    private CassandraRolloutProbe() {}

    private static final String KEYSPACE = "rollout_lab";
    private static final String TABLE = "probe_by_tenant";
    private static final UUID PROBE_ID = UUID.fromString(
        "11111111-1111-1111-1111-111111111111");

    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                "Usage: CassandraRolloutProbe " +
                "<contact-host> <local-dc> <ONE|LOCAL_QUORUM>");
            System.exit(2);
        }

        String contactHost = args[0];
        String localDc = args[1];
        DefaultConsistencyLevel consistency =
            DefaultConsistencyLevel.valueOf(args[2]);

        // For RF1 lab: ONE.
        // For RF3 production-like staging: LOCAL_QUORUM.
        // NEVER lower real application CL just to turn a gate green.
        if (consistency != DefaultConsistencyLevel.ONE
                && consistency != DefaultConsistencyLevel.LOCAL_QUORUM) {
            throw new IllegalArgumentException(
                "Unsupported CL in this example");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress(contactHost, 9042))
                .withLocalDatacenter(localDc)
                .build()) {

            boolean schemaAgreement =
                session.checkSchemaAgreement();
            if (!schemaAgreement) {
                throw new IllegalStateException(
                    "Schema disagreement among currently UP nodes");
            }

            boolean tableKnown = session.getMetadata()
                .getKeyspace(CqlIdentifier.fromCql(KEYSPACE))
                .flatMap(ks -> ks.getTable(
                    CqlIdentifier.fromCql(TABLE)))
                .isPresent();

            if (!tableKnown) {
                throw new IllegalStateException(
                    "Expected table missing from driver metadata");
            }

            PreparedStatement read = session.prepare(
                "SELECT state, revision " +
                "FROM rollout_lab.probe_by_tenant " +
                "WHERE tenant_id = ? AND probe_id = ?");

            BoundStatement request = read.bind(
                    "tenant-lab", PROBE_ID)
                .setConsistencyLevel(consistency)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));

            long started = System.nanoTime();
            ResultSet result = session.execute(request);
            Row row = result.one();
            double elapsedMs =
                (System.nanoTime() - started) / 1_000_000.0;

            if (row == null
                    || !"READY".equals(row.getString("state"))
                    || row.getInt("revision") != 7) {
                throw new IllegalStateException(
                    "Sentinel data oracle mismatch");
            }

            System.out.printf(
                "READINESS_PASS dc=%s cl=%s elapsed_ms=%.3f%n",
                localDc, consistency, elapsedMs);
        }
    }
}
~~~

### 19.3. Running in the lab

~~~bash
# Check actual DC with SELECT data_center FROM system.local
# Example invocation once the Java class is compiled/tested:
java example.CassandraRolloutProbe 127.0.0.1 datacenter1 ONE
~~~

Expected output:

~~~text
READINESS_PASS dc=datacenter1 cl=ONE elapsed_ms=<measured>
~~~

`elapsed_ms` reflects actual runtime measurement, not a fixed constant. If the node is unreachable, metadata/table is missing, CL cannot be satisfied, row is empty, or revision differs, the program must **fail** with an exception. Never check merely that a result row exists while ignoring `revision`.

### 19.4. Changes needed before using against RF3 staging

1. Create the keyspace/sentinel at true RF3 in a dedicated multi-node cluster.
2. Keep known keys and expected values isolated from overwriting production rows.
3. Pass `LOCAL_QUORUM` when required by the application contract.
4. Run from every application DC across multiple token/partition probes.
5. Combine with ring, driver pool, host metrics, streaming, GC, and SLO for a complete gate.
6. Use a least-privilege role/account and environment-appropriate TLS/auth.

**Never deploy this program as-is as a production readiness daemon**: it opens a fresh `CqlSession` per invocation, incurring connection/auth/metadata overhead. In real systems, reuse long-lived service sessions or a rate-limited diagnostic controller so hundreds of pods do not open CQL sessions every second.

### 19.5. Why not rely on `ExecutionInfo.isSchemaInAgreement()` from a SELECT?

In the Java Driver, `isSchemaInAgreement()` applies to schema-changing DDL; a regular `SELECT` may return true by default. It is not an independent schema gate. Call `session.checkSchemaAgreement()`, inspect driver/server metadata properly, and verify the data oracle at the target CL.

## 20. Lab C — Java 17 batch-size verification from simulated replica sets

### 20.1. Objective

This is a **pure Java simulation** that makes no Cassandra connections and restarts no nodes. It demonstrates a necessary-condition check: given a candidate wave, do all declared natural replica sets retain enough live replicas to satisfy quorum?

### 20.2. Complete program

~~~java
package example;

import java.util.List;
import java.util.Set;

public final class ReplicaBudgetLab {
    private ReplicaBudgetLab() {}

    record ReplicaSet(
        String name, Set<String> replicas, int requiredAcks) {}

    static boolean safeToRestart(
            Set<String> candidates,
            Set<String> healthyNodes,
            List<ReplicaSet> criticalRanges) {

        if (candidates.isEmpty() || criticalRanges.isEmpty()) {
            return false; // Missing plan/coverage -> fail closed
        }
        if (!healthyNodes.containsAll(candidates)) {
            return false; // Candidate already degraded: reconcile
        }

        for (ReplicaSet range : criticalRanges) {
            if (range.replicas().isEmpty()
                    || range.requiredAcks() <= 0
                    || range.requiredAcks() >
                       range.replicas().size()) {
                return false;
            }

            long liveAfterWave = range.replicas().stream()
                .filter(healthyNodes::contains)
                .filter(node -> !candidates.contains(node))
                .count();

            if (liveAfterWave < range.requiredAcks()) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Set<String> healthy =
            Set.of("A", "B", "C", "D", "E", "F");

        List<ReplicaSet> ranges = List.of(
            new ReplicaSet(
                "range-X", Set.of("A", "B", "C"), 2),
            new ReplicaSet(
                "range-Y", Set.of("B", "D", "E"), 2),
            new ReplicaSet(
                "range-Z", Set.of("A", "B", "F"), 2)
        );

        System.out.println(
            "Restart A only: " +
            safeToRestart(Set.of("A"), healthy, ranges));

        System.out.println(
            "Restart A+B: " +
            safeToRestart(Set.of("A", "B"), healthy, ranges));

        Set<String> degraded =
            Set.of("A", "B", "D", "E", "F"); // C is DOWN

        System.out.println(
            "Restart A while C down: " +
            safeToRestart(Set.of("A"), degraded, ranges));
    }
}
~~~

Expected output:

~~~text
Restart A only: true
Restart A+B: false
Restart A while C down: false
~~~

Because:

- Wave `{A}` leaves at least 2 replicas across all ranges in the example.
- Wave `{A,B}` leaves only F on `range-Z`, below quorum=2.
- While C is DOWN, restarting A leaves only B on `range-X`.

### 20.3. Critical limitations of the simulation

This is **not a production scheduler**. It:

- Assumes `criticalRanges` is exhaustive and the replica map is accurate.
- Assumes nodes in `healthyNodes` actually satisfy CQL within deadlines.
- Ignores multiple DCs, `EACH_QUORUM`/`SERIAL`/transient replicas, and per-query-family CLs.
- Ignores disk/GC/streaming/compaction/backpressure.
- Lacks leases, checkpoints, replay protection, and health windows.
- Does not observe errors, data oracles, or driver routing.

A handful of logical lab ranges **do not** prove the whole cluster is safe. Real controllers must pull authoritative metadata, inspect current token/replica placements for all SLO keyspaces, and evaluate all three budgets. **Returning `true` in this Java simulation means only "passed the simulated count check."**

## 21. Testing controllers with dry-runs and fault simulation

### 21.1. Three distinct test layers

| Layer | Objective | Where it runs |
|---|---|---|
| Unit / pure simulation | Wave selection, replica budgets, state transitions | CI, no Cassandra connection |
| Integration with fake operator/JMX | Checkpoints, retries, leases, action timeouts | Isolated test harness, no real restarts |
| Multi-node Cassandra staging | Quorum, driver, data, performance after restart/fault | Dedicated approved RF3/multi-DC cluster |

You do not need **production chaos** to prove logic like "if node C is already DOWN, do not restart A." Most safety predicates belong in deterministic fixture tests; real fault injection validates distributed interactions that cannot be fully mocked.

### 21.2. Test-case matrix per transition

| Case | Preflight / event | Expected controller decision |
|---|---|---|
| T01 | All 3 replicas UP, RF3/LQ, batch={A} | `GO` if resource/business gates PASS |
| T02 | C already DN, batch={A}, A/B/C share natural set | `HOLD` |
| T03 | Batch={A,B}, RF3/LQ same set | `HOLD` |
| T04 | RF1/ONE, restart sole replica | `HOLD` or explicit approved downtime path |
| T05 | RF3/ALL, restart one replica | `HOLD` if outage not allowed |
| T06 | Node unexpectedly UJ/UM/UL | `HOLD`, investigate topology |
| T07 | Expected host ID != observed host ID | `ABORT` and open identity incident |
| T08 | Action API times out after restart submitted | `UNKNOWN_ACTION_OUTCOME` → reconcile |
| T09 | Process UP, CQL at required CL fails | `HOLD` |
| T10 | CQL PASS, yet p99 exceeds SLO for 5 windows | `HOLD/ABORT` per deadline |
| T11 | Metrics collector unavailable | `HOLD`, never PASS |
| T12 | Repair starts on natural replica during node restart | `HOLD` competing maintenance |
| T13 | Controller loses lease / fencing epoch | Stop issuing actions; `HOLD` |
| T14 | Canary package hash differs from approved hash | `ABORT` |
| T15 | DC2 app uses wrong local DC | `HOLD` DC2 rollout |
| T16 | Operator Task Completed, yet data oracle wrong | `HOLD` |
| T17 | Wave returns UN, yet streaming unsettled | `HOLD` until scoped gate passes |
| T18 | App error rate rises despite lower success p99 | `HOLD/ABORT` |
| T19 | Controller restarts after checkpoint before action | Reconcile intent; no duplicate restart |
| T20 | Wave finished, yet manual change altered RF | Recompute/abort stale plan |

**Testing goal:** Cover **PASS, FAIL, and UNKNOWN** for every gate, not just happy paths. In real life many outages stem from UNKNOWN branches: a command ran yet the API never returned its response.

### 21.3. Fake operator: lost response after action started

~~~text
Controller persists action-17: restart A
       |
Fake operator receives action-17
       |
Fake operator sets node A = RESTARTING
       |
Response is deliberately dropped
       |
Controller receives timeout
       |
Expected:
  do NOT submit action-18 restart A
  query operator state by action_id
  observe node/process/host_id
  mark ACTION_OBSERVED or HOLD_UNKNOWN
~~~

This is a **unit/integration simulation**, not a real network drop command. If the action API supports idempotency keys, reuse the **same `action_id`** when checking/retrying per API contract; if not, reconcile state first and involve an owner decision.

### 21.4. Fake metrics: dashboard drops out mid-canary

~~~text
At T0: p99=60ms, error=0.1%
At T1: Cassandra restart finishes, node UN
At T2: metrics scrape fails (no data)

Expected:
  Gate=UNKNOWN
  Do NOT assume p99=0ms or errors=0
  HOLD next wave until evidence returns or escalate
~~~

Never convert null metrics into 0 when evaluating SLOs. When exporters restart, counters reset; handle gaps, resets, and sample-count thresholds properly.

### 21.5. Fault simulation after a node returns

A sound multi-node test covers:

1. Critical keyspaces at RF3, `LOCAL_QUORUM`, and known sentinel keys across multiple replica sets.
2. Restarting a canary node in dedicated staging.
3. While the canary is down, running probes at required CL; tolerating documented SLO degradation without changing CL.
4. Waiting for node UN, native transport, and driver readiness.
5. Running CL probes and oracles; measuring p99, retries, hints, streaming, and GC.
6. **Only after steady windows pass**, allowing the next wave.
7. Intentionally taking another node DOWN (in an approved lab) to verify the controller clamps concurrency=0.

If fault injection corrupts data, fills disks, or prevents recovery per runbook, stop the test and preserve evidence rather than pushing through remaining waves just for coverage.

### 21.6. Testing with multiple keyspaces

Test at least one keyspace of each type:

- RF1/ONE or RF2/LQ → zero spare replicas for non-disruptive restarts.
- RF3/LQ → at most one absent natural replica when healthy.
- RF3/ALL → zero replicas can be lost if availability must hold.
- RF5/LQ → larger theoretical headroom, yet resource/SLO budgets may be tighter.
- NTS multi-DC → verify local/each/global quorum and application local DC separately.

Never let a scheduler optimize for the **easiest keyspace** while overlooking an audit/ledger keyspace with stricter CL.

## 22. Observability and rollout decision telemetry

### 22.1. Dashboards need a unified timeline

~~~text
Panel 1  Rollout markers: wave start/drain/stop/start/UN/GO/HOLD
Panel 2  Node states by DC/rack/host ID, unexpected DOWN
Panel 3  CQL client errors, timeouts, unavailables by query family/CL
Panel 4  Client p50/p95/p99, completed QPS, request counts
Panel 5  Driver connections/in-flight/retries/speculation
Panel 6  Cassandra read/write/coordinator latency and thread-pool drops
Panel 7  Disk read/write IOPS, await, throughput, free space
Panel 8  JVM heap, GC pauses, CPU, network RTT/errors
Panel 9  Repair/streaming, compaction pending/active/bytes
Panel 10 Sentinel data oracle and schema/metadata readiness
Panel 11 Unknown action outcomes, reconcile age and maintenance lease
~~~

Never infer causation across misaligned panel time windows. For instance, high p99 at T2 while disk I/O panels show T4 obscures compaction contention.

### 22.2. Metric sources

| Layer | Source | Used to measure |
|---|---|---|
| Controller | Action/checkpoint/lease logs | Wave order, last passing gate, unknown attempts |
| Cassandra JMX | ClientRequest, Table, Compaction, ThreadPools, Storage | Latency, queues, errors, SSTables, compaction |
| `nodetool` | `status`, `tpstats`, `netstats`, `compactionstats` | Node/task state snapshots |
| Java Driver 4.x | Session/node metrics | Pool state, retries, per-node responses |
| Application/API | Traces/business metrics | End-to-end SLO, data oracle, unknown business outcomes |
| Host/kernel | CPU, disk/FS, network, GC logs | Resource contention |
| Kubernetes/operator | Pod statuses, tasks, events | Controller lifecycle and orchestration attempts |

Never subtract server p99 from client p99 to "compute network latency": percentiles from two different sample sets **do not add or subtract** like means. Use distributed tracing on the same request to break down latency.

### 22.3. Counters, gauges, and histograms

| Type | Examples | Handling |
|---|---|---|
| Counter | Total request timeouts, bytes compacted | `rate`/`increase`, handle resets after node restarts |
| Gauge | Pending compaction, free disk, in-flight | Current level and slope |
| Histogram/timer | Read latency, GC pauses | Percentiles + sample counts/precision |
| Boolean/state | Node UN, gate pass | Timestamped with observer viewpoint |
| Derived ratio | Error rate, retry amplification | Counts with clear denominators and aligned windows |

Restarting a node resets many counters; never compare raw pre/post counters and declare "timeouts dropped 90%." Compute time-windowed rates, per-query-family error counts, and aligned timestamps.

### 22.4. Leading vs. lagging indicators

**Leading indicators:** rising pending compaction/flush queues, rising disk await, rising driver in-flight/backpressure, rising retries, longer GC pauses, schema disagreement, shrinking replica liveness margin.

**Lagging indicators:** p99 breaching SLO, client timeouts, unavailable errors, stale/data oracle mismatches, business processing backlogs.

Waiting until lagging indicators explode means the next wave may already be running and worsening the outage. Controllers should enforce **early HOLD** on deteriorating leading trends even if p99 temporarily remains inside SLO.

### 22.5. Do not expand when numbers look "good" on only one node

A freshly restarted node may report lower CPU or cleaner stats while remaining natural replicas carry the load and experience rising GC/throttling. Gates must inspect **the whole cluster and all nodes serving the canary's token ranges**, not just the canary. Likewise, aggregate app p99 can mask a "checkout" query family timing out.

### 22.6. Illustrative telemetry table

~~~text
Window  QPS  p99(ms) errors(%) pendingCompaction unexpectedDN  Action
  1    2000     85       0.1        12                0       HOLD
  2    1990     90       0.2        15                0       HOLD
  3    1980    105       0.3        30                0       HOLD
  4    1920    128       0.5        70                0       HOLD
  5    1800    165       1.1       130                0       ABORT
~~~

**Hypothetical** numbers. Even with zero unexpected DOWN nodes, falling throughput alongside climbing p99/errors/backlog means **no steady state achieved**. Never advance waves just to "finish on time."

### 22.7. Safety signals must carry provenance and freshness

A cached `nodetool status` snapshot from 15 minutes ago is invalid for a current pre-wave gate. Each observation should carry:

~~~text
metric_name, source_node, scope, timestamp_utc,
last_successful_scrape, sample_count, freshness_limit,
value, threshold, evaluation_result
~~~

If data is stale or comes from the wrong cluster, the gate returns `UNKNOWN`. Never treat missing telemetry as PASS.

## 23. Twenty-four common scenarios in rollout automation

### Case 1 — Restarting two nodes in the same natural replica set

**Symptom:** RF3/`LOCAL_QUORUM`; controller picks A and B in one wave; partition P has replicas A/B/C.  
**Cause:** Limiting by total node count instead of replica sets.  
**Fix:** **HOLD**; permit waves only when quorum survives across all affected ranges; keep concurrency=1 until graph safety is proven.

### Case 2 — One node already DN, batch still keeps `maxUnavailable=1`

**Symptom:** C is already DN; plan restarts A; A/C co-serve a hot partition.  
**Cause:** Controller counts only nodes it intentionally stops, ignoring existing failures.  
**Fix:** Remaining budget for affected candidates is 0 → **HOLD/ABORT**; restore the failed replica first.

### Case 3 — An RF1 keyspace turns every rolling restart into an outage

**Symptom:** Cluster's main keyspace is RF3, yet an audit keyspace is RF1.  
**Cause:** Safety check inspects only the primary keyspace.  
**Fix:** Check **all critical keyspaces/CLs**; never promise zero-downtime rollouts; schedule planned downtime or fix replication design first.

### Case 4 — Node comes up `UN`, yet CQL at `LOCAL_QUORUM` times out

**Symptom:** `nodetool status` looks clean while app reads/writes time out.  
**Likely cause:** Slow replica, insufficient CL headroom, driver routing, or streaming/hints/GC/compaction pressure.  
**Fix:** **HOLD**; run representative CQL/data oracles and resource diagnostics rather than advancing waves.

### Case 5 — Native port 9042 open, yet new table cannot be read

**Symptom:** Kubernetes readiness PASSes while Java `PREPARE` throws `unconfigured table`.  
**Cause:** App rolled out ahead of schema migration, stale metadata, or a node lacks schema agreement.  
**Fix:** Pause app release; enforce single migration owner, schema agreement, expected definitions, and Java probes.

### Case 6 — PDB blocks one eviction while an admin force-deletes another pod

**Symptom:** One node is restarting while another pod is force-deleted or its host crashes.  
**Cause:** PDBs do not stop all disruption types and know nothing of Cassandra replica budgets.  
**Fix:** **ABORT** new waves; re-evaluate gossip/natural replicas; never treat a PDB as proof of CL.

### Case 7 — Operator Task Completed, yet node host ID changed

**Symptom:** Pod recreated; controller reports restart succeeded, yet host ID/tokens/volume mismatch.  
**Cause:** Unintended replacement, missing PVC, or identity drift.  
**Fix:** **STOP** as a topology incident; verify token placement/streaming; do not start the next wave.

### Case 8 — `nodetool drain` run as a health check

**Symptom:** A cron job calls `drain` every time it tests node readiness.  
**Cause:** Confusing a state-mutating command with a read-only observation command.  
**Fix:** Remove `drain` from probes; run it only immediately before owner-approved graceful shutdowns.

### Case 9 — Drain finished, operator restart API times out

**Symptom:** Node is drained, orchestration call returns no response, controller moves on.  
**Cause:** Missing `UNKNOWN_ACTION_OUTCOME` and reconciliation.  
**Fix:** **HOLD**; inspect process/pod/operator action state, recover the drained node, and only then consider the next wave.

### Case 10 — Two automation systems managing the same node

**Symptom:** `cass-operator` runs a rolling restart while an external script calls `service stop`.  
**Cause:** No single lifecycle owner or lease.  
**Fix:** Assign one controller as action owner and make the other read-only; enforce maintenance locks and fencing.

### Case 11 — New Cassandra version uses config unsupported on older nodes

**Symptom:** New canary node PASSes, yet a schema/feature option is enabled while the cluster is still mixed-version.  
**Cause:** Compatibility phase checks skipped.  
**Fix:** HOLD upgrade; stay on a compatible feature set per release plan; never blindly trigger irreversible on-disk formats.

### Case 12 — Enabling `fast` to shorten `cass-operator` rolling restarts

**Symptom:** Multiple nodes/racks restart concurrently, exhausting CL/latency headroom.  
**Cause:** `fast`/`force` flags or operator settings bypassing safety assumptions.  
**Fix:** Stop and lower concurrency per operator version runbook; never enable `force` on a degraded cluster.

### Case 13 — Heavy repair runs concurrently with restarting another natural replica

**Symptom:** Remaining nodes stay UP, yet p99 spikes and CL responses time out.  
**Cause:** Disk/GC/streaming capacity lower than theoretical quorum count.  
**Fix:** HOLD restarts; coordinate resource budgets and repair windows so both do not overlap without headroom.

### Case 14 — Success p99 looks better while HTTP 504s climb

**Symptom:** Success-histogram p99 drops as timeout count rises.  
**Cause:** Slow requests dropped out of success samples, creating a false positive.  
**Fix:** HOLD/ABORT per error budget; report p99, request counts, timeouts, and retries together.

### Case 15 — Controller receives null metrics and treats them as 0

**Symptom:** Scrape failed, dashboard displays 0 errors, wave auto-advances.  
**Cause:** Failing to separate `NO_DATA` from `0`.  
**Fix:** Status `UNKNOWN` → HOLD; enforce telemetry source and freshness predicates.

### Case 16 — Post-restart node is still replaying commitlogs / cold GC

**Symptom:** Quick `UN`, yet app p99 stays high and GC/disk await fluctuate.  
**Cause:** Process-up time differs from performance recovery.  
**Fix:** Soak across multiple rolling windows and check resource/backlog trends before the next wave.

### Case 17 — Controller loses lock yet keeps acting from cached plan

**Symptom:** Lease expired, another actor took control, old actor keeps issuing restarts.  
**Cause:** Lease not fenced at the execution boundary.  
**Fix:** Every action requires a valid fencing epoch/owner; lease loss → STOP new actions.

### Case 18 — Retrying restarter after API 504 restarts a node twice

**Symptom:** First action executed, response lost; script submits a new action.  
**Cause:** Missing persistent `action_id` and observed-state reconciliation.  
**Fix:** Reconcile pod/process/node/action status before retrying, keeping the same intent identity.

### Case 19 — Increasing wave size to beat a deadline

**Symptom:** Drain/repair slowed the rollout, so the operator raises `maxUnavailable` near the end of the window.  
**Cause:** Treating deadlines as reasons to relax safety budgets.  
**Fix:** Window expires → **HOLD and reschedule**; never breach CL, replica, or resource gates.

### Case 20 — Java app deployment ramps up speculative retries

**Symptom:** Cassandra sees physical requests triple despite flat HTTP logical QPS.  
**Cause:** Driver retry/speculative config in the new release.  
**Fix:** Roll back/tune canary app config; measure pools, in-flight requests, retries, and CL rather than success rate alone.

### Case 21 — Two DCs have different schemas while gate checks only dc1

**Symptom:** dc1 service PASSes while dc2 `PREPARE`/`SELECT` fails post-rollout.  
**Cause:** Checking only one `system.local`/driver vantage point.  
**Fix:** Enforce per-DC schema agreement, metadata, and CQL checks; keep dc2 traffic closed until its gates pass.

### Case 22 — Node replacement treated as a routine restart

**Symptom:** New node gets different tokens/host ID and starts streaming; script continues rolling waves.  
**Cause:** Not comparing inventory, volumes, or token identities.  
**Fix:** STOP; switch to the replace/bootstrap/repair runbook and verify ownership and data coverage.

### Case 23 — Full repair auto-triggered to "fix latency"

**Symptom:** p99 degrades, controller runs full repair, further saturating disk and network.  
**Cause:** Treating every Cassandra issue as missing data needing repair.  
**Fix:** Diagnose read paths, compaction, GC, and driver behavior first; run repair only with a data-sync plan and resource budget.

### Case 24 — Rollout paused after wave 2, restarted from wave 0 next day

**Symptom:** Nodes A/B already run the target binary; controller lacked checkpoints and restarts them needlessly.  
**Cause:** Missing durable run/wave/action state and config hashes.  
**Fix:** Resume via reconciliation: verify current versions, configs, host IDs, and gates, executing only unverified steps while respecting mixed-version constraints.

## 24. Runbook: GO / HOLD / ABORT / ROLLBACK

### 24.1. Four distinct decision states

| Decision | Meaning | Permitted actions |
|---|---|---|
| **GO** | Sufficient evidence to execute **selected wave** | Only actions in that wave, within concurrency budget |
| **HOLD** | Recoverable issue or insufficient gate evidence | Stop new waves; keep observing within deadline |
| **ABORT** | Guardrail breached or unsafe to proceed | Halt new rollout; hand off to incident/recovery owner |
| **ROLLBACK** | Revert to prior approved state **if compatible** | Only after assessing reversibility per change type |

**HOLD** does not mean aborting already-dispatched side effects; restarts or streaming may need to finish safely. **ABORT** does not mean immediately killing Cassandra. **ROLLBACK** is not always safe; major-version, data-format, or destructive schema changes may be irreversible.

### 24.2. P0 — Pre-run decision gate

- Approvals and authorized access to the target cluster exist.
- Node inventory, host IDs, tokens, and storage IDs are locked down.
- Keyspaces, CL, SCL, and critical query families are listed.
- RF/DC/rack/replica-set safety verified on current observed topology.
- No unexpected `DN`/`UJ`/`UL`/`UM` nodes; degraded clusters require explicit exception policies.
- Resource headroom, backup/restore tests, and version-appropriate rollback strategy exist.
- Single maintenance owner/lease and immutable `change_digest` recorded.
- Fresh telemetry, known-key CQL probes, and business error budgets ready.
- Canary, wave plan, and hard-stop rules defined.

**If any mandatory criterion cannot be answered**, the state is HOLD—never choose GO by "trying once to see."

### 24.3. P1 — Pre-wave safe-to-act

~~~text
function safe_to_act(candidate_wave):
  assert approved run_id and immutable change_digest
  assert valid, exclusive lease/fencing epoch
  assert observed host IDs/tokens match manifest
  assert current topology snapshot fresh
  assert no unknown previous action remains
  assert every critical replica set will retain required CL
  assert no conflicting repair/streaming/maintenance
  assert per-node/per-DC resource headroom
  assert app error/latency/QPS baseline within policy
  assert before-window deadline and rollback owner valid
  return GO if all true; else HOLD/ABORT according to guardrail
~~~

This is **pseudocode**, not runnable commands. A `GO` decision is valid only for **one candidate wave at one snapshot**; if a node unexpectedly goes DOWN 30 seconds later, the executor must re-check and/or cancel unstarted actions.

### 24.4. P2 — Checkpointed execution

~~~text
persist INTENT(action_id, node_ids, expected_state, digest)
    |
submit action to single lifecycle owner
    |
observe action state and Cassandra node health
    |
ACTION COMPLETE? -- no --> HOLD/RECONCILE with deadline
    |
yes
    |
run post-wave CL/data/driver/resource gates
    |
ALL PASS? -- no --> HOLD / ABORT / rollback assessment
    |
yes
    |
persist WAVE_VERIFIED and release maintenance slot
~~~

Persist the outcome before releasing the slot. If the controller crashes between action submission and checkpointing, the reconciler must **read actual state**, never blindly re-issue the side effect.

### 24.5. P3 — HOLD conditions

HOLD when:

- A node is not yet `UN`/native-ready while still within its recovery deadline.
- Driver metadata has not converged or schema agreement is still propagating after valid DDL.
- Repair/compaction backlogs rise without crossing hard stops and require observation.
- App p99/errors have not yet passed the required **consecutive windows**.
- Scrapers/JMX/metric stores are unavailable, causing missing evidence.
- Another node unexpectedly goes `DN`; controller must recompute replica budgets.
- Operator action status is unknown after a timeout.

During HOLD, **never open a new wave**; notify the owner and continue bounded observation. Past deadline or on further degradation → ABORT/escalation.

### 24.6. P4 — Immediate ABORT conditions

ABORT when:

- Quorum at contracted CL is lost on critical replica sets.
- Host ID, token, or storage identity diverges from expected.
- Data oracle returns wrong values/versions, data corruption appears, or unexpected keyspace/table drops occur.
- Full disk, read-only filesystem, commitlog failures, repeated OOMs, or severe compaction failures occur.
- Errors/timeouts/p99 breach hard SLOs/error budgets with customer impact.
- Controller lease/fencing is lost or a competing actor mutates the lifecycle.
- Runbook targets the wrong cluster or environment.
- An unknown action outcome caused unrecoverable duplicate execution.
- Recovery/rollback risks breaking compatibility or losing data without owner sign-off.

**Never "push another wave faster" as a remedy for ABORT.** Preserve evidence and transfer incident ownership clearly.

### 24.7. P5 — Rollback decision tree

~~~text
Change failed / stop gate triggered
            |
Is original binary/config/schema/data state still compatible?
            /                           \\
          YES                            UNKNOWN/NO
           |                               |
  Rollback plan reviewed               HOLD + SME review
           |                               |
  Can we keep required CL through it?  Forward-fix or restore
           |                           under dedicated runbook
   YES ----+---- NO
    |            |
 Execute      Planned downtime/
 one-node     alternate recovery
 guarded      decision
 rollback
    |
 Verify CL/data/SLO again
~~~

Rolling back a node after a major binary upgrade may be **disallowed** once storage formats or feature flags change. For schema drops or data migrations, "rolling back DDL" does not restore rows. Every change type needs a *reversible?* assessment during preflight.

### 24.8. P6 — Rollout closure criteria

~~~text
All planned nodes:
  target artifact/config digest matches
  expected host ID/tokens/volume and DC/rack
  serving CQL native transport

All critical services:
  required consistency level probes PASS
  expected data/schema contract PASS
  app p95/p99/errors/retries within SLO
  repair/streaming/compaction resource stable

Controller:
  no unknown action/outstanding restart
  all waves checkpointed
  lease released correctly
  report and audit trail stored
~~~

Never close a rollout while `UNKNOWN_ACTION_OUTCOME` remains or a `DN` node is waved away as "we will fix it tomorrow" without an owner, ticket, and explicit service-risk acknowledgment. Reporting a rollout as **partially completed/held** is a valid, honest outcome.

### 24.9. Sample incident/handoff report

~~~text
RUN_ID:
CHANGE_ID / APPROVER / WINDOW_UTC:
CLUSTER_ID / ENVIRONMENT:
SOURCE_VERSION / TARGET_VERSION / ARTIFACT_DIGEST:
KEYSPACE_REPLICATION_AND_CL_CONTRACT:
APP_DRIVER_VERSIONS_AND_LOCAL_DCS:
NODE_INVENTORY_HOST_IDS_TOKENS_RACKS:
CONTROLLER_LEASE_AND_FENCING_EPOCH:
CANARY_NODE / RESULT:
WAVES_PLANNED / WAVES_VERIFIED / WAVE_IN_PROGRESS:
LAST_NODE_ACTION_ID / OBSERVED_STATE:
UNEXPECTED_DOWN_NODES / JOINING / STREAMING:
SCHEMA_AGREEMENT_BY_DC:
KNOWN_KEY_DATA_ORACLE_BY_QUERY_FAMILY:
CLIENT_P99_ERROR_TIMEOUT_RETRY:
GC_DISK_NETWORK_COMPACTION_BACKLOG:
STOP_REASON / ROLLBACK_DECISION:
UNKNOWN_ACTION_OUTCOMES / RECONCILIATION:
GO/HOLD/ABORT/ROLLBACK_FINAL_STATE:
NEXT_OWNER / NEXT_REVIEW_UTC:
~~~

Never log passwords, TLS private keys, raw tenant/order IDs, or unredacted query bindings. Use host IDs and opaque correlation IDs inside access-controlled internal systems.

## 25. Execution and code-review checklist

### 25.1. Identification and scope

- [ ] Target cluster/environment and maintenance authorization verified.
- [ ] Manifest pins binary/config/image checksums; no mutable `latest` tags.
- [ ] Node host IDs, tokens, DCs, racks, and storage identities reconciled.
- [ ] Distinguished restarts, replacements, bootstraps, schema migrations, and repairs.
- [ ] Upgrade compatibility matrix verified, including rollback feasibility.
- [ ] Keyspaces, RF, CL, and `SERIAL`/`LOCAL_SERIAL` (if using LWTs) listed.
- [ ] No overlooked RF1/`ALL` keyspaces with strict availability requirements.
- [ ] Never inferred quorum guarantees from a Kubernetes PDB or StatefulSet policy alone.
- [ ] Canaries represent hardware, DCs, drivers, and query workloads.
- [ ] Snapshots/backup verification and recovery owners assigned per change type.

### 25.2. Concurrency and ordering

- [ ] Wave size is strictly an **upper cap**, dropping to 0 when degraded.
- [ ] Every natural replica set/token range keeps required CL if candidate nodes go unavailable.
- [ ] Existing `DN`/slow/streaming nodes factored into the observed budget.
- [ ] Resource budget covers CPU/GC, disk/commitlog, network, and repair/compaction.
- [ ] SLO error/p99 and data oracles act as independent hard gates.
- [ ] Never select waves solely by hostname order or rack labels.
- [ ] No concurrent lifecycle owners mutating the same node/cluster.
- [ ] Never start a wave while an earlier wave has an `UNKNOWN` action.
- [ ] Never raise concurrency merely to beat a maintenance deadline.
- [ ] Cooldown/soak windows driven by metrics, not fixed `sleep` timers.

### 25.3. Node lifecycle

- [ ] `nodetool drain` called only right before planned graceful shutdowns, never as a health check.
- [ ] Operator/service manager has a single owner for stop/start.
- [ ] Process startup, gossip `UN`, native transport, and driver routing all verified.
- [ ] Expected host ID, tokens, and volumes stay unchanged for routine restarts.
- [ ] Data gate verified at required CL, not just `system.local`.
- [ ] Schema agreement, driver metadata, and queries checked after DDL/app rollouts.
- [ ] Streaming, repair, compaction, GC, and disk queues observed post-startup.
- [ ] Never use `decommission`/`removenode`/`replace` for routine restarts.
- [ ] Never treat `UJ`/`UL`/`UM` or `DN` nodes as `READY` simply because pods are Running.
- [ ] Never advance to the next node before the current node is verified.

### 25.4. Controller durability

- [ ] Exclusive lease with renewal and fencing epoch enforced.
- [ ] Separate stable `run_id`, `wave_id`, `action_id`, and `attempt_id`.
- [ ] Intent persisted before side effects; checkpoints persisted after verification.
- [ ] Control API timeouts yield UNKNOWN + reconciliation, never blind retries.
- [ ] Controller crashes/restarts do not replay already-submitted actions.
- [ ] Metric freshness and source identity verified before marking PASS.
- [ ] Max action/wave/recovery durations and maintenance deadlines enforced.
- [ ] Explicit HOLD/ABORT rules and manual owners defined.
- [ ] Operator tasks/statuses matched to exact API version; never blindly toggle `force`/`fast`.
- [ ] Error paths, missing telemetry, and UNKNOWN action outcomes all tested.

### 25.5. Java application/data readiness

- [ ] Driver `localDatacenter`, TLS, auth, and contact points match the real cluster.
- [ ] Keyspace/table/column/PK contracts verified against live metadata/CQL.
- [ ] Single migration owner enforced, avoiding DDL on every app pod startup.
- [ ] Read/write CL matches production; never lowered to `ONE` just to pass.
- [ ] Known-key sentinel oracle asserts row values/revisions, not just absence of exceptions.
- [ ] Probes cover planned critical token ranges, query families, and DCs.
- [ ] p95/p99 paired with sample counts, errors, timeouts, and retries on dashboards.
- [ ] Driver retries, speculation, and pool in-flight metrics show no abnormal spikes.
- [ ] LWT unknown outcomes handled if the app uses conditional writes.
- [ ] Never open full traffic while caches/GC/compaction remain unsettled.

### 25.6. Security, safety, and reporting

- [ ] Runtime actors have least-privilege access without exposing JMX/CQL passwords.
- [ ] Never manually edit `system_schema`, token ownership, or Paxos internals.
- [ ] Never trigger destructive repairs/compactions/drops/truncates blindly to fix rollout errors.
- [ ] Never inject faults or restarts in production outside approved windows.
- [ ] Hard stops configured for full disks, wrong data oracles, lost quorum, or identity drift.
- [ ] UTC timestamps, decision evidence, and source freshness recorded.
- [ ] Capability to report **PARTIAL/HOLD** honestly instead of forcing `COMPLETED`.
- [ ] Handover owner assigned for unresolved nodes or unknown actions.
- [ ] Rollback runbooks verified per version without assuming binary downgrades work.
- [ ] Java/CQL labs are illustrative only; production controllers require QA and staging validation.

## 26. Self-assessment questions and suggested answers

**Question 1.** Why is deploying to all Cassandra nodes simultaneously dangerous?  
**Hint:** It can break required CL/quorum, overload streaming/repair/GC concurrently, and eliminates canary isolation.

**Question 2.** Does "rolling deployment" require every wave to contain exactly one node?  
**Hint:** No; wave size depends on change type, replica sets, resources, and business budgets, though one node is the conservative baseline.

**Question 3.** Why can even one node at a time cause an outage?  
**Hint:** RF1, RF2/LQ, RF3/ALL, or another replica already DOWN/saturating.

**Question 4.** How many full replicas must reply in the same DC for RF3 `LOCAL_QUORUM`?  
**Hint:** Two of three in the full-replica model.

**Question 5.** With RF3/`ALL`, can you restart a natural replica and still satisfy `ALL` on that partition?  
**Hint:** No, unless planned downtime or a contract change is approved.

**Question 6.** How many ACKs does RF5/`LOCAL_QUORUM` require?  
**Hint:** Three full replicas in that DC.

**Question 7.** Why can't concurrency be calculated purely from a 100-node cluster total?  
**Hint:** Each partition maps to a small natural replica set; any two nodes may overlap inside one replica set.

**Question 8.** What mathematical condition keeps `LOCAL_QUORUM` intact across a wave?  
**Hint:** Remaining live natural replicas for **every** partition/DC must be at least `floor(RF/2) + 1`.

**Question 9.** How must a node already DOWN before a rollout be accounted for?  
**Hint:** Subtract it from the observed availability budget before selecting waves.

**Question 10.** Does `maxUnavailable: 1` in Kubernetes automatically guarantee Cassandra quorum?  
**Hint:** No; a PDB guards voluntary disruptions without knowing natural replica sets or CL.

**Question 11.** Why doesn't rack anti-affinity replace replica-set analysis?  
**Hint:** Scheduler labels, snitches, and token assignments can diverge, and vnodes create overlaps.

**Question 12.** Can a wave overlap with full repair on another natural replica?  
**Hint:** Only when resource/replica/SLO proofs permit; default to avoiding overlapping heavy maintenance.

**Question 13.** What does "Node `UN`" prove?  
**Hint:** Gossip views the node Up/Normal; it does not prove native CQL, CL/data oracles, or p99.

**Question 14.** Which readiness layers must be checked after a restart?  
**Hint:** JVM/process, JMX, gossip, native transport, schema/driver, CL/data oracle, and performance/backlogs.

**Question 15.** Is `nodetool drain` a read-only health diagnostic command?  
**Hint:** No; it stops accepting writes and flushes tables to prepare for graceful shutdown.

**Question 16.** Drain succeeds yet the restart API times out—what must the controller do?  
**Hint:** HOLD/`UNKNOWN_ACTION_OUTCOME`; inspect actual process/operator state rather than advancing waves.

**Question 17.** Can `nodetool decommission` pull a node from traffic before a restart?  
**Hint:** No; decommission alters topology and ownership, unlike a graceful restart.

**Question 18.** Why verify expected host IDs and token digests after a restart?  
**Hint:** Catches unintended replacements or PVC identity drift instead of assuming the same logical node restarted.

**Question 19.** If a pod is Running while Cassandra reports `UJ`, is the wave complete?  
**Hint:** No; joining/bootstrapping means topology and data streaming are unfinished.

**Question 20.** Does schema agreement prove all historical data is repaired?  
**Hint:** No; schema metadata and replica data synchronization are separate layers.

**Question 21.** Which operation must have a single owner?  
**Hint:** DDL/schema migrations, preventing concurrent pods from racing schema changes.

**Question 22.** Why is `CREATE TABLE IF NOT EXISTS` insufficient as a contract gate?  
**Hint:** An existing table may have different PKs/types/columns while the statement still succeeds as a no-op.

**Question 23.** Why avoid rolling out the Java app concurrently with binary/schema changes unless a joint plan exists?  
**Hint:** Introduces confounders, schema/driver incompatibilities, and retry/routing storms.

**Question 24.** What errors stem from a misconfigured Java Driver `localDatacenter`?  
**Hint:** Routing, connection, and availability failures even while Cassandra nodes in another DC are UP.

**Question 25.** Why is `SELECT system.local` not a business readiness oracle?  
**Hint:** It skips user keyspaces, partitions, required CLs, and expected business data checks.

**Question 26.** What must a sentinel query assert beyond "no exception thrown"?  
**Hint:** Expected key, row existence, value/version, CL, deadlines, scope, and token-key distribution.

**Question 27.** Does an RF1/`ONE` lab prove zero-downtime restarts?  
**Hint:** No; when the single node restarts, zero replicas remain to satisfy `ONE`.

**Question 28.** Why doesn't a driver readiness probe at `ONE` prove a `LOCAL_QUORUM` service is healthy?  
**Hint:** `ONE` needs fewer replies and can read stale data; it tests a weaker contract.

**Question 29.** Success p99 drops while timeouts climb—what should the controller do?  
**Hint:** HOLD/ABORT and inspect censored slow requests; never treat lower success p99 as a win.

**Question 30.** Do we need p99 sample counts?  
**Hint:** Yes; low-QPS percentiles are statistically unstable.

**Question 31.** Why isn't `PendingCompactions=0` the sole steady-state gate?  
**Hint:** Reads/writes/GC/disk/streaming/replicas can still bottleneck, and continuous compaction can be normal.

**Question 32.** What happens if metrics disappear mid-wave?  
**Hint:** Gate becomes UNKNOWN → HOLD; never turn null into 0.

**Question 33.** Why can't a 15-minute-old metric snapshot authorize a pre-wave gate?  
**Hint:** Topology and availability may have changed; enforce freshness bounds.

**Question 34.** Are `run_id`, `action_id`, and `attempt_id` identical?  
**Hint:** No; rollout campaign, intended side effect, and individual network/API attempts are distinct.

**Question 35.** Does a restart API timeout prove the node has not restarted?  
**Hint:** No; the side effect may already have occurred, requiring reconciliation.

**Question 36.** Why must controllers persist intent before side effects?  
**Hint:** Crash recovery needs to know which actions were already submitted to avoid blind replays.

**Question 37.** Is an in-memory maintenance lock sufficient against split-brain?  
**Hint:** No; use durable leases with renewals and fencing enforced at the action boundary.

**Question 38.** A controller loses its lease yet still remembers the old plan—may it continue?  
**Hint:** No; stop issuing new actions and let the new leaseholder reconcile.

**Question 39.** Does `batch_size=1` mean always restarting a node every 60 seconds?  
**Hint:** No; it is an upper bound—effective batch can drop to 0, and readiness requires evidence.

**Question 40.** Should concurrency be raised to finish before the maintenance deadline?  
**Hint:** No; stop and reschedule rather than violating safety budgets.

**Question 41.** Does running `repair -pr` on one node fix all data ranges cluster-wide?  
**Hint:** No; repair is scoped to that node's ranges and requires a cluster-wide coverage plan.

**Question 42.** Does hint delivery replace repair completely?  
**Hint:** No; hinted handoff is best effort, and missed writes still need repair and verification.

**Question 43.** Why does node replacement differ from a rolling restart?  
**Hint:** Token/data ownership, bootstrap/streaming/repair, and host ID/volume identities can all change.

**Question 44.** Can `storage_compatibility_mode` be set to `NONE` immediately on a Cassandra 5.x canary?  
**Hint:** Not arbitrarily; follow the supported staged upgrade sequence and compatibility rules.

**Question 45.** When is binary rollback permitted?  
**Hint:** Only when release, on-disk format, config, and schema states remain compatible and the runbook has approval.

**Question 46.** Why doesn't an operator "Task Completed" equal GO?  
**Hint:** The operator confirms task lifecycle completion, not app CL, data correctness, or SLOs.

**Question 47.** What is the safety rule when a node goes DOWN unexpectedly after a wave?  
**Hint:** Recompute headroom; HOLD/ABORT subsequent waves rather than blindly following the old plan.

**Question 48.** When can a rollout be marked COMPLETED?  
**Hint:** All planned waves verified, expected versions/identities match, required CL/data oracles and SLOs PASS, background work stable, zero unknown actions remaining, and audit report archived.

## 27. Summary: every wave is a fresh safety decision

~~~text
              CASSANDRA OPERATIONS AUTOMATION
                            |
                   CHANGE CONTRACT
           approved target/config/version + rollback
                            |
                      PREFLIGHT
    topology/RF/CL/token sets + resources + business SLO
                            |
                 COMPUTE SAFE CONCURRENCY
             min(replica, resource, business)
                            |
                +-----------+-----------+
                |                       |
             UNSAFE                   SAFE
                |                       |
           HOLD/ABORT                  CANARY
                                        |
                              Lifecycle action + checkpoint
                                        |
                              Node/process/CQL readiness
                                        |
                               CL + data oracle PASS?
                                /             \\
                              NO              YES
                               |               |
                              HOLD       Resource/SLO windows
                                                |
                                          PASS or FAIL?
                                        /          \\
                                      PASS          FAIL
                                       |             |
                                WAVE_VERIFIED     HOLD/ABORT
                                       |
                             Re-check next wave budget
                                       |
                               ALL WAVES VERIFIED
                                       |
                            POST-SOAK + AUDIT REPORT
~~~

### 27.1. Seven mandatory principles to remember

1. **Replica sets before batch size:** Restart counts cannot prove safety without knowing natural replicas and CLs for critical keyspaces.
2. **One node at a time is a baseline, not a theorem:** RF1/2/LQ/ALL or an already-DOWN node can make even a single restart unsafe.
3. **All three budgets must PASS:** replica availability, disk/CPU/network maintenance capacity, and business SLO/error budgets.
4. **Look beyond `UN`:** Verify native CQL, schema/driver readiness, CL data oracles, p99/retries/errors, and background task trends.
5. **Never multiply side effects on lost ACKs:** Action API timeout → UNKNOWN + reconcile by ID/state, never blind restarts.
6. **Each change type has its own lifecycle:** Restarts, upgrades, schema migrations, repairs, replacements, and app rollouts do not share one concurrency/recovery rule.
7. **HOLD is a safe outcome:** When telemetry is missing, node identities mismatch, quorum margins shrink, or rollback is unclear, halt new waves and hand off rather than forcing COMPLETED.

**Core message:** Apache Cassandra operations automation is not a "for-loop over a node list." A trustworthy rollout is **an evidence-driven chain of decisions**: knowing replica ownership and RF/CL, re-evaluating live state before every wave, capping concurrency by data availability, resources, and SLOs alike, advancing only after data/driver/performance gates pass, and **halting safely** whenever UNKNOWNs or changed conditions appear.

### 27.2. Content/lab boundaries

The RF1 CQL lab teaches only sentinel and CL syntax; the Java Driver probe checks only one table/key until coverage expands; and the Java replica-budget simulation computes solely over declared sets. No script in this lesson executes real restarts or fault injection on a live cluster. Production adoption requires verifying versioned Cassandra/K8ssandra operator APIs, real topology, RBAC/TLS, on-call approvals, staging validation, and rollback compatibility. Per the curriculum authoring workflow, **STEP 4 writes Markdown only**, without running Gradle/Python or the STEP 6 Content QA pass.

## References

- [Apache Cassandra — Use nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — `status`, `tpstats`, `netstats`, `compactionstats`, and limitations of a single-node view.
- [Apache Cassandra — Nodetool drain](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/drain.html) — preparing graceful shutdown: stopping writes and flushing tables.
- [Apache Cassandra — Nodetool status](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/status.html) — Up/Down, Normal/Joining/Leaving/Moving states, and host IDs/racks.
- [Apache Cassandra — Nodetool netstats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/netstats.html) — observing streaming and transfer state.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — best-effort hinted handoff, repair/ranges, incremental/full repair, and resource cost.
- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html) — topology changes, streaming, replacement, and cleanup vs. restarts.
- [Apache Cassandra — Cassandra configuration reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — storage compatibility modes and upgrade configuration settings.
- [Apache Cassandra — Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — request latency/errors, thread pools, compaction/repair, and system metrics.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — SSTable rewrites, resource contention, and maintenance.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — partitions/tokens, natural replicas, replication, and consistency levels.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — primary key/partition modeling and query-driven CQL design.
- [Apache Java Driver 4.18 — Metadata](https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/) — node/schema/metadata snapshots and driver view.
- [Apache Java Driver 4.18 — Pooling](https://apache.github.io/cassandra-java-driver/4.18.1/core/pooling/) — connections, in-flight streams, and multiplexing.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — retries, idempotency, and physical request amplification.
- [Apache Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) — driver session/node metrics and latency timers.
- [K8ssandra — Cass Operator](https://docs.k8ssandra.io/components/cass-operator/) — Kubernetes Cassandra lifecycle/management API and operator responsibilities.
- [K8ssandra — Cass Operator CRDs](https://docs.k8ssandra.io/reference/crd/cass-operator-crds-latest/index.html) — version-specific operator tasks and configuration.
- [Kubernetes — PodDisruptionBudgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruptions, PDB scope, and limitations.
- [Kubernetes — StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) — ordered rollout, readiness, and identity semantics.
