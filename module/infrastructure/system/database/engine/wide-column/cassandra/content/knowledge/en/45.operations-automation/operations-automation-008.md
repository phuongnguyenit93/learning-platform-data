# Orchestrating Bootstrap and Decommission Without Repeating Dangerous Operations in Apache Cassandra

## 1. Objectives and safety boundaries

In Cassandra, **bootstrap** brings a new node into the topology and distributes data/tokens to it; **decommission** removes a participating node from the ring via a version-supported mechanism, typically streaming data to remaining replicas. These are **stateful topology mutations**, not idempotent HTTP APIs that clients can blindly retry on timeout.

This lesson belongs to the **Operations Automation** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. Module objectives include distributed wide-column architecture, partition keys, replication, consistency, compaction, repair, and Java/CQL. These exact mechanics determine whether a node can safely enter or leave a cluster and when automation is permitted to advance to the next step.

After this lesson, you will be able to:

1. Distinguish bootstrap, decommission, replacement, restart, join/leave, `removenode`, and `cleanup` at the **operational semantics** level.
2. Explain why **blindly retrying a topology command** can create duplicate nodes, misplace tokens, lose data, or break consistency levels.
3. Design an **operation ID**, expected target state, immutable change manifest, durable journal, leader lease, and single-operation ownership.
4. Apply **fencing/epochs** to stop old and new controllers from orchestrating concurrently, while understanding the limits when Cassandra does not accept fencing tokens in admin commands.
5. Use read-only reconciliation to determine progress after a crash, timeout, or lost response **without re-issuing commands**.
6. Verify **DC/rack, RF/CL, replica availability, token ownership, streaming, disk/GC/network**, schema agreement, and CQL queries.
7. Build stop/rollback/escalation policies with **PASS/FAIL/UNKNOWN** states instead of inferring success from a `UN` line.
8. Write state-machine pseudocode, Java Driver probes, incident runbooks, test matrices, and change-control checklists.

**Version scope:** bootstrap/decommission behavior, `nodetool` commands, startup options, seed discovery, vnodes/tokens, host IDs, `system.peers_v2`, metadata, and compatibility can differ across Cassandra 3.x/4.x/5.x and distributions. This lesson covers general safety principles; all real operations must be checked against your **release, cluster topology, and approved SOPs**.

**Authoring-step boundary:** no Cassandra commands, topology changes, Java/Gradle runs, or external repo reads are executed here. All commands in this lesson are templates for understanding workflows.

## 2. Why aren't bootstrap and decommission freely retryable?

### 2.1. Two commands with the same name do not mean one safe repeated action

Suppose automation orchestrates removing node `A`:

~~~text
10:00  Controller-1 confirms PRECHECK PASS.
10:01  Controller-1 sends decommission to node A.
10:02  Controller network times out.
10:03  Cassandra node A keeps streaming data and leaves the ring.
10:04  Controller-2 restarts.
10:05  Controller-2 sees "request timeout" and sends decommission a second time.
~~~

Controller-2 **does not know** whether the first command was received. Depending on Cassandra state and release, repeating the command may be rejected, cause conflicts, or mask real errors. Worse, if automation **re-resolves the target by a reused IP**, the second attempt could even hit **a different node**.

**Rule:** timeout means **unknown outcome**, not that the operation never started or rolled back.

### 2.2. Distinguish command retries from observation retries

| Activity | Characteristics | Auto-retry on timeout? |
|---|---|---|
| Reading `nodetool status` | Observes state; risk of stale/partial view | Bounded, with freshness checks |
| Reading `nodetool netstats` | Observes streaming | Bounded |
| Reading GC/disk/CQL metrics | Observes health | Bounded |
| Bounded read-only CQL query | Verifies data/CL | Bounded, with timeout budget |
| Initial node bootstrap | Mutates membership/ownership on startup | **Never auto-replay** before reconciling |
| Node decommission | Mutates ring and replica data | **Never blind-retry** |
| `removenode`/replace | High-risk membership mutation | Human/SOP control |
| `cleanup`/repair/compaction | Heavy I/O/resource/data tasks | Never run as a health check |
| Reimage/recreate VM/PVC | Can wipe identity/commitlog/data | Never repeat without identity verification |

**State-reading calls** can be retried, yet a single node or single snapshot is not conclusive; cross-check multiple sources and expected topology.

### 2.3. You cannot promise "exactly-once" with try/catch

A controller writing `started=true` **before** dispatching may crash before sending; writing **after** sending may crash before persisting. There is no shared atomic transaction spanning the controller's journal and Cassandra's ring mutation.

Therefore, practical design uses:

- **At-most-one in-flight intent** controlled by a single active controller.
- An **immutable operation ID** bound to each topology change.
- Durable persistence **before** dispatching: target identity, operation type, checkpoint, and authority.
- After disconnect, **read-only reconciliation** followed by manual resume/continuation per state.
- Never claim an exactly-once guarantee if Cassandra offers no true idempotency key for that command.

## 3. Bootstrap, decommission, and commonly confused operations

### 3.1. Terminology and purpose

| Operation | Purpose | Risk if mischosen |
|---|---|---|
| Bootstrap | **New** node joins cluster, receives tokens/data | Duplicate identity, streaming pressure |
| Restart | Existing node stops/starts, **keeping identity/data** | Accidental re-bootstrap, availability loss |
| Replace | Replaces failed node via release-supported mechanism | Duplicate host ID/tokens or data loss if wrong |
| Decommission | **Live capable** node leaves cluster cleanly | Unsafe RF/CL, unfinished streaming |
| Removenode | Removes metadata of an unavailable node per SOP/version | Loss of replica metadata/data if misused |
| Cleanup | Purges SSTables no longer owned after topology changes | Premature data removal / I/O spikes |
| Rebuild | Resyncs data from sources via release tooling | Network/disk saturation |
| Repair | Synchronizes/heals divergent replica ranges | I/O/disk/CPU cost and dedicated schedule |

**Never use `decommission` as a substitute for `removenode`** on a dead node where your version does not support it. Likewise, never initialize an old node holding existing data under a new identity and call it a restart.

### 3.2. Bootstrap is not a universal `nodetool bootstrap` command

In most Cassandra releases, bootstrap happens when **a new node starts with join configuration**, contacts seeds/peers, and selects tokens per policy (`auto_bootstrap`/replace/initial_token/vnodes by version).

Thus a controller must never write:

~~~text
Run a made-up universal command:
  nodetool bootstrap

Assume every Cassandra release supports that action.
~~~

Instead, the controller invokes the version-supported **cluster management operator/SOP**, governs approved node creation/startup, and **observes `Joining` → `Normal` plus streaming**. Never invent hazardous shortcuts by editing token metadata directly.

### 3.3. Decommissioning a live node differs from removing a dead node

Decommissioning normally requires the node to be alive enough to hand off ownership and stream data. For dead nodes, the workflow differs and carries data-loss risks for missing replicas. Automation must classify:

~~~text
Target is Up, Normal, healthy:
    Consider approved decommission preflight.

Target is Down/unreachable:
    STOP; invoke node-failure/removal/replace SOP.

Target is already Leaving or absent:
    DO NOT send decommission again.
    Reconcile history and ring views.

Target identity changed:
    STOP; investigate recycled IP/PVC/host ID.
~~~

Never let a script see `DN` and issue `decommission` as a "remediation."

## 4. Identity model: an IP address is not a safe identifier

### 4.1. Fields required in an operation manifest

~~~yaml
# Input manifest example: NOT a Cassandra config file.
change_id: CHG-2026-1121-008
operation_id: "f25be1dc-58ba-4d11-af04-0c7c80080008"
operation_type: DECOMMISSION
cluster_id: "cassandra-telemetry-production"
expected_cluster_version: "approved-release"
target:
  host_id: "11111111-2222-3333-4444-555555555555"
  node_address: "cassandra-a.example.invalid"
  datacenter: "dc1"
  rack: "rack2"
  persistent_volume_identity: "approved-storage-identity"
expected_before:
  membership: NORMAL
  target_up: true
expected_after:
  membership: ABSENT
guardrails:
  no_parallel_topology_change: true
  require_operator_approval: true
  require_healthy_quorum: true
  require_sufficient_disk: true
  observation_window_seconds: 900
~~~

This is an illustrative manifest. `operation_id` must stay immutable across **controller retries**, never minting a fresh UUID every time a worker restarts.

**Distinguish by action:** the manifest above illustrates **DECOMMISSION**, where the existing node's host ID is already known. For **BOOTSTRAPPING a brand-new node**, Cassandra may only generate the host ID on first boot. Before dispatching, lock **cluster, instance/PVC identity, DC/rack, and generation**; when the host ID first appears, persist it via journal CAS and verify it does not collide with any existing member. Never invent a fixed host ID pre-startup or swap in a different node during reconciliation.

### 4.2. Multi-layer identity verification

- **Cluster ID/name** of the managed connection, preventing staging/production mix-ups.
- Target **host ID** from Cassandra metadata, not IP/DNS alone.
- **DC/rack placement** and failure domain.
- **Current membership state** (Normal/Joining/Leaving/Down/absent).
- **Persistent data/volume identity**, especially with Kubernetes StatefulSets/PVCs or VM replacements.
- **Token/vnode assignment** and Cassandra-version policy.
- **Version/config baseline** for joining or leaving nodes.
- Signed/approved **change manifest revision**.

An IP or pod name can be recycled after a replacement. If the live cluster's host ID mismatches the manifest, **never "auto-adjust the target"**; emit `UNKNOWN/FAIL` and require operator investigation.

### 4.3. Never let a mutable selector pick a new target node

Anti-pattern:

~~~text
for every node with hostname prefix cassandra-a:
    if node unhealthy:
        run decommission
~~~

Target selection must **resolve once before approval**: for **decommission**, pin host ID/cluster; for **new bootstrap**, pin instance/PVC/cluster and record the host ID observed post-startup. Every subsequent reconcile verifies "this is still the exact same entity." If the node was replaced, the old operation **must never transfer to another node**.

## 5. Hard gates before topology changes

### 5.1. Preflight PASSes only with complete facts

| Gate | Bootstrap | Decommission |
|---|---|---|
| Approved change, unique operation ID | Mandatory | Mandatory |
| No other operation in same scope | Mandatory | Mandatory |
| Consistent cluster/DC/rack inventory | Mandatory | Mandatory |
| Right target identity and lifecycle | New node, not yet in ring | Existing node, Up/Normal per SOP |
| Post-change RF/CL feasible | Check disk/replica distribution | Check no lost replica/quorum |
| No unrelated unexpected DOWN nodes | Mandatory | Mandatory |
| Stable schema/token metadata | Mandatory | Mandatory |
| Conflicting streaming/repair/backup? | Must verify | Must verify |
| Disk/network/GC/CPU headroom | Inbound/outbound streaming | Outbound streaming and receiving peers |
| Reliable app CQL & SLO baseline | Mandatory | Mandatory |
| Clear rollback/abort strategy | Required | Required, without promising rollback always works |
| Observation and recovery owner | Mandatory | Mandatory |

If any required metric is missing, return **UNKNOWN** and halt—never report "0 errors" when monitoring connectivity failed.

### 5.2. Cluster health is more than `UN`

A cluster with all nodes `UN` can still suffer:

- Nearly full disks and rising pending compactions.
- Repair/hints/streaming saturating I/O.
- JVM GC pauses pushing CQL p99 past SLO.
- Broken native CQL TLS/auth for Java clients.
- Schema disagreement or prepared-query incompatibilities.
- A DC/rack lacking redundancy for RF/CL.
- Hot partitions overloading specific replicas.

Health gates require **status from multiple observers**, hottest-node metrics, and representative CQL probes at target CL.

### 5.3. Do not count `UN` instead of checking inventory

Suppose 8 nodes are expected while `nodetool status` prints 7 lines, all `UN`. A script grepping for `DN` and finding none wrongly PASSes: **one node vanished from output**.

Compare **expected host IDs, DC/rack, and states** against manifest expectations. During bootstrap, expected count **increases in phases**; during decommission, expected count **decreases upon completion**. Never force pre- and post-node lists to match when the operation intentionally mutates topology.

## 6. RF/CL, token ownership, and safety when removing a node

### 6.1. Local quorum example

Assume `NetworkTopologyStrategy` with `RF(dc1)=3` and the app uses `LOCAL_QUORUM`. Normally a write/read needs **2 replica replies in `dc1`** for the target partition.

If one node in `dc1` is DOWN, requests may still succeed if remaining replica sets answer, yet **you cannot safely decommission another node**. A degraded cluster that still serves traffic is not safe for topology changes.

### 6.2. Do not evaluate mechanically by "3 nodes in DC"

Cassandra uses a token ring and replica placement; RF=3 does not mean every partition in every topology sits on the same three arbitrary nodes. Verify:

- Configured RF per DC.
- Node count, rack placement, and replica counts in each token range's **replica set**.
- Whether existing nodes hold necessary data before the target leaves.
- Repair history and out-of-sync replica status.
- Any node showing UP whose native transport or streaming is impaired.
- Transient replication or version-specific behaviors if enabled.

One `nodetool status` check cannot prove consistency when token ownership shifts.

### 6.3. Post-decommission capacity

A node leaving means data and traffic redistribute across remaining nodes. Hypothetical example:

~~~text
dc1: 6 nodes, each holding roughly 2 TiB of SSTables
decommission 1 node
=> total logical/replica data must fit across 5 nodes;
   even distribution is only a rough estimate.

Never assume:
  "each node grows by exactly 20% and will definitely fit on disk"
because token ownership, RF, SSTable sizes, compaction/streaming,
skew, and temporary files can differ.
~~~

Capacity budgets must include **peak streaming and compaction temporary space**, disk/volume limits, bytes per token range, hotspots, and failover headroom. Never wait until a disk hits full to fail preflight.

### 6.4. Capacity during bootstrap

Bootstrapping a new node causes source peers to stream data, shifts ownership, and affects caches, disk, and network. A new node showing `UN` may not have finished cache warm-up, while peers may not yet have run cleanup or fully settled. Check **streaming completion, expected token/rack/host IDs, and traffic p99** before advancing.

### 6.5. Never lower consistency to "make maintenance pass"

If production uses `LOCAL_QUORUM` while probes use `ONE`, a cluster losing quorum can still report CQL PASS. Verification CL must match application SLO/correctness contracts. Never lower production CL just to get past preflight failures.

## 7. State machine separating intent from observed outcome

### 7.1. Minimum states

~~~mermaid
flowchart TD
    A["NEW"] --> B["APPROVED"]
    B --> C["PREFLIGHT"]
    C -->|PASS| D["RESERVED"]
    C -->|FAIL/UNKNOWN| H["HOLD"]
    D --> E["COMMAND_INTENT_RECORDED"]
    E --> F["COMMAND_DISPATCH_UNCERTAIN"]
    F --> G["RECONCILING_READ_ONLY"]
    G -->|Active| I["IN_PROGRESS"]
    G -->|Not resolved| H
    G -->|Expected target reached| J["VERIFYING"]
    I --> G
    J -->|PASS| K["COMPLETED"]
    J -->|FAIL/UNKNOWN| H
    H --> L["HUMAN_REVIEW / RECOVERY"]
~~~

`COMMAND_DISPATCH_UNCERTAIN` **does not mean the request failed**: it reflects that the controller cannot commit atomically with Cassandra. Even when transport returns an ACK, ring state and data movement must still be observed and verified afterward.

### 7.2. Explicit outputs per state

| State | Meaning | May dispatch topology command? |
|---|---|---|
| NEW | Manifest unapproved | No |
| APPROVED | Scope/owner/change ID locked | No |
| PREFLIGHT | Reading state and checking safety gates | No |
| RESERVED | Holds exclusive scope right | Not yet; must record intent |
| COMMAND_INTENT_RECORDED | Durable checkpoint prior to side effect | Once, under control |
| COMMAND_DISPATCH_UNCERTAIN | May have been accepted/started | **Never replay** |
| IN_PROGRESS | Cassandra observed joining/leaving/streaming | No |
| RECONCILING_READ_ONLY | Gathering live evidence vs. expected state | No |
| VERIFYING | Target state observed; checking CQL/metrics | No |
| HOLD | Gate failed or missing evidence | No |
| HUMAN_REVIEW | Operator decides per SOP | Never automatically |
| COMPLETED | Postconditions passed, audit committed | No |

Record `COMPLETED` only with full evidence, never from `nodetool` exit code 0 or a fixed sleep timer.

### 7.3. Transitions require invariants

Practical invariants:

- Within one cluster/topology scope, **at most one potentially conflicting mutation** is orchestrated at a time.
- An operation past `COMMAND_INTENT_RECORDED` must never dispatch a second command on recovery merely because the journal lacks "completed."
- Every observation includes source node, UTC timestamp, and freshness.
- Target cluster, host ID, DC, and rack **never change** from the approved manifest.
- Each change phase has distinct expected topology; never share identical invariants across bootstrap and decommission.
- `FAIL` or `UNKNOWN` blocks progression under fail-closed policy.
- The controller owns orchestration only; it never invents ad-hoc repairs/recoveries outside SOPs.

## 8. Locks, leases, and fencing: necessary, yet never over-promise

### 8.1. Choosing where to store the operation journal

The journal must be:

- **Durable**, with appropriate read-after-write consistency and transaction guarantees.
- Storing `operation_id`, manifest revision, target identity, state, command intent, and evidence references.
- Supporting **compare-and-swap (CAS)** or optimistic versioning so two controllers cannot advance state together.
- Resilient to worker process crashes.
- Governed by clear permissions, auditing, and retention.

Use a dedicated control-plane store such as Kubernetes Lease/etcd plus a transactional DB or equivalent semantics. **Never rely solely on the very Cassandra cluster under maintenance to store its own lock**: if Cassandra becomes unreachable, the controller loses visibility into lock ownership.

### 8.2. Lease expiration does not stop an in-flight topology command

~~~text
Controller A owns lease epoch=41.
A launches decommission; command continues running on Cassandra.
A loses network, lease expires.
Controller B acquires lease epoch=42.

Wrong:
  B dispatches decommission again.

Right:
  B sees durable command intent with no verified outcome,
  RECONCILES read-only, then HOLD/HUMAN_REVIEW if uncertain.
~~~

A fencing token/epoch works only against targets that inspect and validate it. **Cassandra `nodetool decommission` has no universal guaranteed fencing token at its command interface.** Incrementing a control-plane epoch **does not cancel** an already-running command.

### 8.3. Preventing split-brain controllers

1. **Leader election** scoped by cluster/topology (not just per pod).
2. **CAS on journal revision** for all state writes.
3. **Single dispatch authority** tied to an active lease/epoch.
4. Block stale workers from side effects unless epoch and scope validate immediately before dispatch.
5. **Durable dispatch intent** persists even if the lease expires.
6. A new owner only reconciles, never re-dispatches topology commands.
7. Restrict direct admin channels: manual terminal/script actions must go through change control.
8. Whenever unsure who executed a command, **HOLD and escalate**.

If an engineer can invoke operational commands outside the controller from a terminal, controller-internal locks **are no longer exclusive**. Combine RBAC, auditing, and change freezes.

### 8.4. "Retry-safe" differs from "idempotent"

An operation is retry-safe only when backed by a **target-verified idempotency contract**, not merely a Java method annotated `@Retryable`.

Use bounded backoff retries for **read-only reconciliation** with deadlines; topology commands follow *at-most-once per approved intent*, and any uncertain state must be proven safe before an operator permits continuation.

## 9. Classifying observation vs. state-mutating commands

### 9.1. Never treat command exit code as the sole source of truth

| Tool / illustrative command | Purpose | Category | Automation policy |
|---|---|---|---|
| `nodetool status` | Membership/ring view | Observation | Bounded retry, compare inventory |
| `nodetool info` | Node memory/load/uptime | Observation | Check freshness and source |
| `nodetool gossipinfo` | Gossip peer states | Observation | Interpret per version |
| `nodetool netstats` | SSTable streaming | Observation | Compare progress across samples |
| `nodetool tpstats` | Pending/active/dropped stages | Observation | Watch for counter resets |
| `nodetool compactionstats` | Compaction tasks/backlog | Observation | Do not require absolute pending=0 |
| `nodetool describecluster` | Metadata/schema views | Observation | Does not prove CQL app health |
| `nodetool tablestats` | Table-level SSTables/memtables | Observation | Carries I/O and permission costs |
| `nodetool decommission` | Controlled ring departure | **Topology mutation** | Single approved dispatch, no blind retry |
| First node startup with bootstrap config | Join ring / stream data | **Topology mutation** | Single lifecycle intent, never spawn a second node |
| Node replacement per SOP | Replace identity/token ownership | **Topology mutation** | Separate approval, exact node/volume |
| `nodetool removenode` | Remove metadata of dead node per SOP/version | **Topology mutation** | Never substitute casually for decommission |
| `nodetool cleanup` | Purge unowned data | Storage mutation | Never auto-run in health loops |
| `nodetool repair` | Repair replica ranges | Resource-heavy / data op | Dedicated schedule; never run on UNKNOWN |
| Restart/recreate PVC | Change process or storage identity | Side-effecting | Dedicated SOP; verify persistent data |

Verify exact outputs, command names, and flags on your running release. Listing a command here **is not** an instruction to run it on a live cluster.

### 9.2. Read-only command examples

~~~bash
# Only authorized personnel, from a valid operations environment.
nodetool status
nodetool info
nodetool gossipinfo
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool describecluster
~~~

`nodetool` typically communicates over JMX; a succeeding command does not prove Java app native CQL TLS/auth works. Releases may vary in flags, outputs, permissions, and subcommands.

### 9.3. Never wrap topology commands in a retry loop

~~~text
# ANTI-PATTERN — pseudocode, not an authorized shell command.
retry(5, operation = decommission(target))

# CONCEPTUALLY RIGHT
record intent once
dispatch once under exclusive authorization
on timeout:
    mark outcome UNKNOWN
    read cluster state/streaming evidence
    hold until reconciled or human decision
~~~

Never call `nodetool decommission` inside a polling loop, re-run it after a controller `SIGTERM`, or "switch hosts" to try another command.

## 10. Bootstrap workflow: from uninitialized node to Normal member

### 10.1. Stage A — pre-startup preparation for the new node

**Preflight must verify:**

1. Change manifest specifies approved target DC/rack, capacity, version/config, volume, and networking.
2. No other topology mutation is active in the affected scope.
3. No unexpected DOWN nodes or streaming/repair overload.
4. Existing RF/CL and capacity suffice while the node bootstraps.
5. New node **carries no data/system tables from another node** unless executing an **approved replacement plan**.
6. Persistent disk/volume identity matches target; never reuse a PVC holding another host ID's Cassandra state.
7. Seed list and internode/TLS/config match the real cluster; seeds are discovery contacts, **not the complete cluster list**.
8. Gossip/broadcast/listen/native transport addresses and DNS/SANs align.
9. JVM/memory/disk/network/FD/CPU headroom, rack/DC placement, and release compatibility verified.
10. Telemetry and read permissions exist to observe joining, streaming, and recovery.

**Never start multiple bootstrapping nodes concurrently** unless cluster SOP permits; parallel streams can saturate source nodes and networks.

### 10.2. Stage B — persist intent, then create/start the node exactly once

~~~text
Journal:
  operation_id = op-2026-008
  operation_type = BOOTSTRAP
  target_node_instance = immutable cloud/PVC identity
  target_cluster = cassandra-prod-example
  state = COMMAND_INTENT_RECORDED
  generation = 27
  approved_manifest_hash = ...
  command_dispatch_count = 0

Controller:
  CAS state -> COMMAND_DISPATCH_UNCERTAIN
  provision/start approved node once
  record dispatch metadata best effort
  begin read-only reconcile
~~~

This diagram illustrates the concept. In the crash window after CAS and before provisioning, the controller cannot know whether creation ran. On resume, never spawn a new instance automatically; check infrastructure APIs, PVC/VM identities, node logs, and ring membership to establish whether the action occurred.

### 10.3. Stage C — monitor Joining/Streaming conditionally

~~~mermaid
flowchart TD
    A["Approved node start intent"] --> B["New process discovered"]
    B --> C["Gossip membership Joining or equivalent phase"]
    C --> D["Streaming/token range movement"]
    D --> E["Normal membership + expected host ID/DC/rack"]
    E --> F["Native CQL + schema + data/latency probes"]
    F --> G{"All postconditions satisfied?"}
    G -->|Yes| H["COMPLETED"]
    G -->|No/Unknown| I["HOLD; diagnose/recover"]
~~~

State transitions vary across releases; never treat the flowchart as an exact internal-step promise. Poll `status`/`netstats` alongside logs/metrics with deadlines and backoff.

A newly `UN` node may still need cache warm-up, driver peer discovery, compaction/repair scheduling, and metric stabilization. `UN` is a **necessary condition**, not sufficient to PASS.

### 10.4. Stage D — post-bootstrap verification

| Check | Acceptance condition |
|---|---|
| Membership | Expected new host ID present and Up/Normal |
| Address/DC/rack | Matches manifest; no wrong peer IP advertised |
| Token ownership | Metadata matches plan; no duplicate tokens or host IDs |
| Source peers | No unexpected `DN` or lost RF/CL |
| Streaming | Bootstrap transfers finished per release/state evidence |
| Data | Expected replica ranges serve representative CQL queries |
| Schema | App prepares/executes CQL across required nodes |
| Workload | p95/p99/errors stay within SLO; retries do not storm |
| Resources | Source/destination disk, GC, network, and compaction stable |
| Maintenance | No conflicting operations; observer evidence fresh |

Never run `cleanup` across all source nodes as an automatic "mandatory sweep" before verifying topology, ownership, and version guidance. Cleanup deletes unowned data and consumes I/O; it requires its own gate and plan.

### 10.5. When bootstrap stalls

Before retrying node startup:

1. Check whether the new node is still running or merely restarted its process.
2. Check Joining/Normal state and streaming activity across multiple samples.
3. Compare host ID, tokens, and volume identity against the operation manifest.
4. Inspect logs for data-directory or identity conflicts.
5. Check disk, network, TLS, gossip, seeds, DC/rack, and compatibility.
6. Set state to `UNKNOWN`/`IN_PROGRESS`/`HOLD` per evidence.
7. Only an operator following SOP decides resume/restart/replace; **never spawn a second node** to "try faster."

## 11. Decommission workflow: leave the ring only when safe

### 11.1. Stage A — verify the target can be decommissioned

For a live node scheduled to leave:

- Exact host ID, Up/Normal, not already undergoing replacement.
- DC/rack/cluster topology matches approved manifest.
- Per-DC RF and **remaining node count** satisfy post-change replication/availability policy.
- Replica ranges have viable streaming/recovery targets.
- Receiving peers have adequate disk/network capacity.
- No conflicting repair, streaming, or topology operations active.
- App CQL at production CL and baseline SLO are healthy.
- Plan exists if decommission fails or the node goes DOWN mid-way.
- Backups/snapshots/retention and rollback constraints are clear.
- Approvers understand **decommission is not a liveness test**.

### 11.2. Stage B — single audited dispatch

~~~text
1. Validate target host ID and cluster in real time.
2. Verify no active/journaled conflicting operation.
3. Obtain exclusive authority and persist command intent.
4. Cross-check approval revision and safety gate freshness.
5. Dispatch supported decommission action ONCE.
6. Record transport response or lack thereof.
7. Enter read-only observe/reconcile loop.
8. Never send command again merely because controller timed out.
~~~

If using `nodetool decommission`, run it **on the exact live target** per release tooling/SOP. A request can continue mutating the ring after the control client disconnects; CLI state does not capture the entire operation.

### 11.3. Stage C — observe Leaving and data handoff

~~~text
Target A: Normal -> Leaving -> absent from membership
Others:   continue serving clients + receive streams
Control:  observe ring, netstats, status, logs, CQL, resources
Decision: continue waiting / HOLD / escalate
~~~

Exact sequencing and representation vary by release. **Never infer streaming completion % from a single field**; a node may still be replaying hints, compacting, or waiting on conditions beyond visible streams.

### 11.4. Stage D — verify the node truly left

After decommission:

- Target host ID is **absent from membership** across multiple observers (allowing reasonable propagation time).
- Node count, DC, and rack match the post-change manifest.
- No unplanned replacement node appeared.
- Token metadata and ownership match expected state.
- Remaining nodes are healthy with required RF/CL intact.
- Streaming transfers completed per supported evidence.
- Representative CQL reads/writes (where authorized) succeed accurately.
- Application native connections and driver metadata drop departed endpoints within policy windows.
- Disk, compaction, hints, retries, p95/p99, and error budgets remain within SLO.
- Audit record preserves command outcome, source evidence, and human approvals if any.

**Never treat `node absent` from one observer as sole proof**; the node could be temporarily unreachable. Combine multi-node membership views with dispatch history.

### 11.5. Never "fill the gap" with unplanned auto-bootstrap

After a clean decommission, adding a new node is a **separate operation** with its own ID, target identity, and approval. Never auto-provision a replacement simply because inventory count dropped—decommission intentionally lowers node count.

If the workload requires replacing a node, follow the **replacement SOP** and migration plan; never assume "decommission old then bootstrap new" has identical consistency/capacity semantics to replace.

## 12. Traps when combining add/remove to preserve cluster size

### 12.1. Never let the controller mutate both sides of topology at once

For a change adding B and removing A, ordering depends on RF, rack placement, and resource capacity. A safe pattern is:

~~~text
Step 1: Bootstrap B with operation ID op-B
  -> verify B Normal, streaming, tokens, CQL, resources
  -> close bootstrap scope.

Step 2: Re-evaluate cluster and replica layout.
  -> only if approved change demands and gates pass:

Step 3: Decommission A with NEW operation ID op-A
  -> verify A absent, RF/CL, data, app SLO.
~~~

This is **one example of an SOP-approved expand-then-shrink sequence**, not the only method and not a substitute for Cassandra's native node-replace mechanism. Order can vary by distribution, version, and capacity; verify your specific recipe.

### 12.2. "Node replacement" has distinct semantics

When A is dead, running decommission as if A were alive may be impossible. Some Cassandra versions/distributions support replace-address / node-replace via startup/config. Risks include:

- Two processes advertising the same tokens/identity.
- Incorrect data dir / PVC reuse or accidental new host ID creation.
- Unreconciled counters, commitlogs, hints, or convergence.
- Stale seed/gossip state continuing to advertise the dead node.
- Controller running `cleanup` before replica ownership settles.

**Never** stitch together an automated `removenode` → `bootstrap` → `cleanup` replacement flow without a version-specific SOP and explicit approval.

### 12.3. Scaling in below RF requirements

If a DC has 3 nodes with RF=3, scaling down to 2 nodes while keeping RF=3 violates **capacity/replication policy**. Never silently lower RF from 3 to 2 just to "let decommission pass." Changing RF requires evaluating consistency, fault tolerance, data movement/repair, and a separate change request.

### 12.4. Multi-DC is more than total cluster node count

RF is configured per DC under `NetworkTopologyStrategy`. One DC having enough replicas does not prove another DC does. If an operation targets `dc1`, health checks must verify local-DC availability, inter-DC streaming/networking, app failover, and `LOCAL_QUORUM` independently per region.

## 13. Measuring streaming and progress: preventing false conclusions

### 13.1. Read-only measurements

~~~bash
# Illustrative; check tool docs per release.
nodetool status
nodetool netstats
nodetool tpstats
nodetool compactionstats
nodetool info
~~~

Capture samples with timestamps, node identity, and observation windows. `netstats` primarily reflects **SSTable streaming**; never use it to conclude all CQL replication, repair, or commitlog activity finished.

### 13.2. Progress is not elapsed time

A job may:

- Increase streamed bytes while pending tasks remain high.
- Pause streaming briefly due to disk backpressure.
- Switch source peers if a node errors.
- Finish streaming while compaction and cache warm-up continue.
- Display `UN` while application p99 remains elevated.

Therefore never set a rule like "after 10 minutes mark COMPLETE." Use **condition-based deadlines** with `IN_PROGRESS`, `STALL_SUSPECTED`, `UNKNOWN`, and escalation.

### 13.3. A "stall" must be judged in context

Hypothetical example:

| UTC | Streamed GiB | Pending tasks | Disk await | App p99 | Interpretation |
|---|---:|---:|---:|---:|---|
| 10:00 | 100 | 12 | 5 ms | 120 ms | Progressing |
| 10:05 | 118 | 8 | 7 ms | 130 ms | Progressing |
| 10:10 | 118 | 8 | 100 ms | 900 ms | Suspected disk stall |
| 10:15 | 118 | 8 | 110 ms | 1,300 ms | HOLD/escalate per policy |

Figures are illustrative. Never treat a zero gauge or two identical readings in one snapshot as proof of **data loss** or **command never ran**.

### 13.4. Other critical metrics

| Group | Signals | Risk |
|---|---|---|
| Topology | Node states, host IDs, DC/rack | Wrong membership |
| Streaming | Active sessions, bytes, progress | Incomplete data transfer |
| Storage | Free disk, SSTables, pending compactions | Source/destination full |
| JVM | GC pauses, heap/off-heap, thread counts | Coordinator/replica stalls |
| OS | CPU quota, disk await, network retransmits | Slow streams / high latency |
| CQL | Read/write timeouts, unavailable, p99 | Effective RF/CL degraded |
| Driver | Pool connections, retries, stale peer addresses | App not recovered |
| Hints/repair | Backlogs, jobs, errors | Data convergence incomplete |
| Schema | Version agreement, prepared CQL | Client incompatibility |

Do not look solely at cluster averages; the worst node can exhaust all headroom when a peer shifts load onto it.

## 14. Verifying CQL with Java: scoped evidence

### 14.1. Why is `nodetool status` insufficient?

`nodetool` normally uses JMX, whereas the Java Driver uses native CQL over TLS, auth, and connection pools. A `UN` node can still:

- Reject connections from the application namespace.
- Have incompatible certificate SANs or truststores.
- Lack `SELECT`/`MODIFY` permissions on the app role.
- Fail schema/prepared CQL compatibility after changes.
- Experience `LOCAL_QUORUM` read/write timeouts.
- Suffer poor p99 from streaming, GC, or disk load.

Run a **new-connection canary** from the application network using the exact role and CL with bounded full-partition-key queries.

### 14.2. Pre-created lab/approved probe schema

~~~cql
-- Run DDL only in authorized environments, prior to maintenance.
-- dc1 must match the real datacenter name per release/config.
CREATE KEYSPACE IF NOT EXISTS topology_probe
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
} AND durable_writes = true;

CREATE TABLE IF NOT EXISTS topology_probe.probes_by_run (
    run_id uuid,
    check_id text,
    expected_value text,
    PRIMARY KEY ((run_id), check_id)
);
~~~

**Never create a new keyspace/table mid-decommission**; DDL can alter schema agreement and add risk. In multi-DC setups, declare per-DC RF per policy. On a 1-node lab cluster, RF/CL must fit that lab—never copy `dc1:3`.

### 14.3. Value-idempotent CQL read/write probe

~~~cql
-- run_id/check_id/value remain fixed across a single check run.
INSERT INTO topology_probe.probes_by_run
  (run_id, check_id, expected_value)
VALUES (?, ?, ?)
USING TTL 3600;

SELECT expected_value
FROM topology_probe.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Never use counter increments or LWT side effects for smoke checks. Retries can refresh TTL, so `idempotent` applies to **health-probe semantics** rather than promising byte-for-byte identical timestamps or expiration.

### 14.4. Java Driver 4.x example with read-back check

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

public final class TopologyHealthProbe {
    private final CqlSession session;
    private final PreparedStatement put;
    private final PreparedStatement get;

    public TopologyHealthProbe(CqlSession session) {
        this.session = session;
        this.put = session.prepare(
            "INSERT INTO topology_probe.probes_by_run " +
            "(run_id, check_id, expected_value) " +
            "VALUES (?, ?, ?) USING TTL ?");
        this.get = session.prepare(
            "SELECT expected_value FROM topology_probe.probes_by_run " +
            "WHERE run_id = ? AND check_id = ?");
    }

    public boolean check(UUID runId, String checkId, String expected) {
        if (runId == null || checkId == null || expected == null)
            throw new IllegalArgumentException("Required probe values");

        BoundStatement write = put.bind(
                runId, checkId, expected, 3600)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        session.execute(write);

        BoundStatement read = get.bind(runId, checkId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        Row row = session.execute(read).one();
        return row != null
            && expected.equals(row.getString("expected_value"));
    }
}
~~~

This code illustrates common Java Driver 4.x APIs; check exact signatures and JDK compatibility for your artifact. Pass `CqlSession` from the application with the right local DC, contact points, and TLS/auth; **reuse the session** rather than creating one per probe.

A write timeout has an uncertain outcome; without enough read-back/replica-health evidence, mark `UNKNOWN/FAIL` instead of retrying indefinitely. Operators must enforce a **combined retry budget** across app, driver, and controller.

### 14.5. What this probe does not prove

- One `run_id` hits one replica set, not the entire token ring.
- `LOCAL_QUORUM` in `dc1` does not prove `dc2` converged.
- One small row does not represent tables with wide partitions or tombstones.
- Matching read-back after write does not rule out duplicate side effects in other tables.
- One successful connection does not prove all peer addresses updated cleanly post-bootstrap.
- Never replaces inventory, token metadata, or streaming gates.

To expand coverage, probe multiple intentional partition keys and representative business reads while capping QPS/bytes and avoiding full-table scans.

## 15. Independently verifiable postconditions

### 15.1. Bootstrap and decommission have different exit criteria

| Criterion | Bootstrap PASS | Decommission PASS |
|---|---|---|
| Target host ID | Present and matches new node | No longer a ring member |
| Expected node count | Increased per manifest | Decreased per manifest |
| Target membership | Up/Normal | Absent across multiple views |
| DC/rack placement | Matches target | Remaining peers accurate |
| Token ownership | Added/rebalanced per policy | Ownership transferred per policy |
| Streaming | Bootstrap complete | Decommission transfers complete |
| Unplanned nodes DOWN | None | None |
| RF/CL and CQL | Business CL/probes PASS | Business CL/probes PASS |
| Application peer discovery | Discovers compatible new node | Stops routing to departed node within window |
| Resources/SLO | Stable / within envelope | Stable / within envelope |
| Hints/repair/compaction | Clear follow-up plan | Clear follow-up plan |
| Operation journal | COMPLETED with evidence | COMPLETED with evidence |

Never replace these postconditions with a "process exited" or "`nodetool` command completed" event.

### 15.2. Expected topology evolves by phase

~~~text
Bootstrap:
  before:  6 known members
  joining: 6 normal + 1 joining (observer/version dependent)
  after:   7 normal, new node host ID confirmed

Decommission:
  before:  7 normal
  leaving: 6 normal + 1 leaving (observer/version dependent)
  after:   6 normal, target host ID absent
~~~

Numbers and phases are illustrative. Never hardcode `expected_nodes=6` across all phases. For replacements, node counts do not simply grow or shrink this way.

### 15.3. "Absent" requires multiple sources and history

If the target node fails to show up once in status output:

- It may simply be unreachable over gossip.
- The observer's topology view may be stale.
- Automation may be querying the wrong cluster.
- The node address may have changed while the host ID persists.
- Or decommission genuinely finished.

Require **host ID + expected changes + multiple observer views + operation journal + streaming evidence**, never treating an empty row as proof.

## 16. When the controller crashes: reconcile first, never re-dispatch

### 16.1. Recovery decision tree

~~~mermaid
flowchart TD
    A["Controller restart; journal has command intent"] --> B["Acquire exclusive control lease"]
    B --> C["Verify cluster, target identity, manifest revision"]
    C --> D{"Target already at expected AFTER state?"}
    D -->|Yes| E["VERIFYING: CQL, RF/CL, metrics, evidence"]
    D -->|No| F{"Joining/Leaving/streaming observed?"}
    F -->|Yes| G["IN_PROGRESS; poll read-only"]
    F -->|No| H{"Confident command never dispatched?"}
    H -->|No/Unknown| I["HOLD; human review"]
    H -->|Yes| J["Only approved operator can decide re-dispatch"]
    E --> K{"All gates PASS?"}
    K -->|Yes| L["COMPLETED"]
    K -->|No| I
    G --> D
~~~

**Important:** even when joining/leaving is not yet observed, a pending command or stale observer view can exist. Never conclude "never ran" from a single missing indicator.

### 16.2. Cases requiring mandatory HOLD

- Journal shows an intent while the cluster is unreachable.
- Target's expected host ID/metadata cannot be read.
- Two controllers simultaneously claim ownership of the same operation.
- Node identity/IP/PVC changed while the manifest stayed unchanged.
- Some observers report Leaving while others report Normal indefinitely without reconciliation.
- Streaming stalls while disk/network metrics are missing.
- An unplanned topology operation appears outside the change plan.
- CQL quorum/`Unavailable` or data correctness fails.
- Post-change token/replica layout violates RF/CL.
- Release/tooling behaves differently from the runbook without operator confirmation.

Returning `UNKNOWN` protects data; it is not a reporting bug.

### 16.3. Difference between retrying admin commands and retrying checks

After a controller crash, **read-only status fetches** may retry with backoff. Never replay:

~~~text
decommission target A
bootstrap replacement B
removenode target A
cleanup all nodes
repair all ranges
~~~

merely because an old log lacks `COMPLETED`. Each action above has distinct preconditions, side effects, and recovery SOPs.

## 17. Controller pseudocode: separating dispatcher from observer

### 17.1. Two distinct privilege boundaries

A safe controller separates **two components**:

- **Observer:** reads status, metadata, stream progress, metrics, and CQL only; uses bounded retries.
- **Dispatcher:** holds topology-mutation rights, executes at most once when operation state, approvals, and leader epoch are valid; never invoked from post-crash reconciliation loops.

Side-effecting code paths must stand out clearly for independent code review.

### 17.2. Java-style interfaces for the operation journal

~~~java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

enum Action { BOOTSTRAP, DECOMMISSION }
enum State {
    NEW, APPROVED, PREFLIGHT, RESERVED,
    COMMAND_INTENT_RECORDED, COMMAND_DISPATCH_UNCERTAIN,
    IN_PROGRESS, VERIFYING, HOLD, HUMAN_REVIEW, COMPLETED
}
enum Gate { PASS, FAIL, UNKNOWN }

record NodeIdentity(
    UUID hostId,
    String datacenter,
    String rack,
    String instanceId) {}

record Operation(
    UUID operationId,
    String clusterId,
    Action action,
    NodeIdentity target,
    State state,
    long revision,
    long leaderEpoch,
    Instant updatedAt) {}

interface OperationStore {
    Optional<Operation> load(UUID id);

    // Control-plane atomic compare-and-swap.
    boolean compareAndSet(
        UUID id, long expectedRevision, Operation next);
}

interface ReadOnlyTopologyObserver {
    ClusterSnapshot observe(String clusterId);
}

interface ClusterSnapshot {
    boolean hasFreshObservers();
    boolean targetIdentityMatches(NodeIdentity expected);
    boolean targetJoiningOrLeaving(NodeIdentity expected);
    boolean targetAtExpectedAfterState(Operation op);
    Gate healthAndCqlPostconditions(Operation op);
}
~~~

This is an **architectural sketch** without a production implementation. Verify `OperationStore` is genuinely atomic and durable; declaring a CAS interface **does not grant** those guarantees. `NodeIdentity` illustrates decommission where host ID is known; real bootstrap implementations must represent an **unassigned** host ID explicitly (e.g., `Optional`) and pin it immutably once observed rather than treating `null` as a verified identity.

### 17.3. Post-crash decision function must have zero side effects

~~~java
final class SafeReconciler {
    static State nextOnRecovery(
            Operation op, ClusterSnapshot snap) {

        if (!snap.hasFreshObservers())
            return State.HOLD;

        if (!snap.targetIdentityMatches(op.target()))
            return State.HOLD;

        if (snap.targetAtExpectedAfterState(op)) {
            Gate post = snap.healthAndCqlPostconditions(op);
            if (post == Gate.PASS) return State.COMPLETED;
            if (post == Gate.FAIL) return State.HOLD;
            return State.VERIFYING;
        }

        if (snap.targetJoiningOrLeaving(op.target()))
            return State.IN_PROGRESS;

        // Cannot prove the command was never dispatched.
        return State.HUMAN_REVIEW;
    }
}
~~~

Zero lines in `nextOnRecovery` invoke bootstrap or decommission. It is strictly an **observation classifier**; when uncertain, it returns `HUMAN_REVIEW` instead of issuing a new command.

### 17.4. Dispatcher must verify authority before side effects

~~~text
function dispatchOnce(approvedOperation):
    assert target == immutableManifestTarget
    assert preflight == PASS with fresh evidence
    assert maintenance lease is owned at current epoch
    assert no conflicting topology operation intent
    CAS operation from RESERVED to COMMAND_INTENT_RECORDED
    CAS operation to COMMAND_DISPATCH_UNCERTAIN
    invoke approved version-specific topology operation ONCE
    record response best effort
    return to READ-ONLY reconciliation

on timeout or crash:
    DO NOT invoke again
    acquire authority and inspect journal + live cluster
    OBSERVE / VERIFY / HOLD / HUMAN_REVIEW
~~~

There is a **crash gap** between CAS and invoke. If the controller dies right there, it cannot tell autonomously whether the command fired. Require human review and evidence from infrastructure and Cassandra, never treating `dispatch_count=0` as license to re-send.

### 17.5. Control every retry layer

- CI pipelines may auto-retry jobs on non-zero exit codes.
- Kubernetes Jobs/Controllers may restart containers while side effects still run.
- HTTP SDKs or proxies may auto-retry management calls.
- An on-call engineer may click re-run when no response arrives.
- Two workflows may run concurrently on one cluster if lock scopes are wrong.

Do not merely disable a retry loop in one Java method. **The topology dispatcher must use retry-disabled adapters + durable dedupe + exclusive authority**, while observers use bounded retries.

## 18. Phase-based gates and fail-closed behavior

### 18.1. Preflight for BOOTSTRAP

~~~text
[ ] Cluster ID, manifest hash, and change approval match.
[ ] New node and volume identity are not already in the ring.
[ ] Does not carry system.local data/identity from another node.
[ ] DC/rack/token/seed/TLS/network configs are valid.
[ ] All expected existing members are present and healthy.
[ ] RF/CL and user CQL SLOs pass.
[ ] No conflicting JOIN/LEAVE/REPLACE or repairs active.
[ ] Disk/network/GC/CPU headroom adequate on source and destination.
[ ] Journal, lease, and revision mechanics operate safely.
[ ] Operator and recovery runbooks are explicit.
~~~

If the target already appears `UJ` while the journal says NEW, **HOLD**: another runner may have started it or the journal is out of sync. Never start a second node.

### 18.2. Preflight for DECOMMISSION

~~~text
[ ] Exact host ID is Up/Normal in the right DC/rack.
[ ] Not already Leaving, decommissioning, or absent.
[ ] No unexpected DOWN nodes exist.
[ ] Remaining DC/rack nodes satisfy RF/CL/fault tolerance.
[ ] Streaming recipient peers have disk/network headroom.
[ ] Repair, hints, and compaction workloads accounted for.
[ ] App CQL at production CL meets SLO.
[ ] No conflicting topology operations active.
[ ] Approval and target identity locked.
[ ] Contingency plan exists if node dies mid-decommission.
~~~

### 18.3. During execution

~~~text
if observation source stale:
    HOLD next mutation; request fresh evidence
if target identity/topology changed unexpectedly:
    HOLD, human review
if replica availability or app CQL hard gate FAIL:
    stop next step and invoke recovery SOP
if streaming still advancing and resources safe:
    continue read-only observation
if target expected end-state and health checks PASS:
    verify stable observation window, then COMPLETE
~~~

HOLD typically means **stop dispatching new mutations**, not killing the Cassandra process mid-transfer. Cancellation/abort safety depends on release and SOP; never assume it is harmless.

### 18.4. Postflight

| Gate | BOOTSTRAP | DECOMMISSION |
|---|---|---|
| Identity | New host ID Up/Normal | Exact host ID absent |
| Node count | Increased as expected | Decreased as expected |
| Placement | New DC/rack/tokens match | Remaining peers placement matches |
| Streaming | Completed/accepted | Completed/accepted |
| RF/CL | No regression | Remaining replicas satisfy policy |
| CQL | Read/write probes and business queries | Read/write probes and business queries |
| Resource/SLO | Source and destination stable | Remaining nodes stable |
| Journal | Audited completed evidence | Audited completed evidence |

## 19. Timeouts, backoff, and observation windows

### 19.1. Distinguishing deadlines

| Milestone | Meaning | Must not infer |
|---|---|---|
| CLI/transport timeout | Caller received no response | Topology command never started |
| Lease expiry | Owner failed to renew lease | Cassandra stopped the operation |
| Read-only poll timeout | Observer missed one sample | Node is definitely down |
| Operation deadline | Time budget exceeded | Safe to auto-cancel command |
| Observation window | Enough samples to confirm stability | Whole cluster is guaranteed flawless |

Exceeding a deadline → `HOLD`, alert, and human review per policy; **never issue a second dispatch**.

### 19.2. Polling observations with backoff

~~~text
initialDelay = policy-controlled interval
nextDelay = min(maxDelay, exponentialBackoff * jitter)
overallDeadline = change-specific
maxConcurrentObservers = bounded per DC
allObservations = timestamped, source-identified
~~~

Never mark PASS after waiting a fixed number of minutes; never hammer JMX hundreds of times per second. If observations go stale, return `UNKNOWN`.

### 19.3. Hysteresis vs. safety conditions

You may require multiple matching samples and observers before marking PASS. However, **hard FAILs**—such as an unexpected missing host ID, lost RF/CL quorum, or suspected data corruption—must halt immediately without waiting for a histogram window to fill.

## 20. Audit trail sufficient to reconcile after restarts

### 20.1. Audit events with source and revision

~~~yaml
# Sample report record, not a production config/file.
event_id: "audit-043"
operation_id: "f25be1dc-58ba-4d11-af04-0c7c80080008"
change_id: "CHG-2026-1121-008"
timestamp_utc: "2026-11-21T10:10:00Z"
controller_epoch: 42
journal_revision: 9
cluster_id: "cassandra-telemetry-production"
operation_type: DECOMMISSION
target_host_id: "11111111-2222-3333-4444-555555555555"
target_datacenter: dc1
target_rack: rack2
event_kind: OBSERVATION
state_before: COMMAND_DISPATCH_UNCERTAIN
state_after: IN_PROGRESS
evidence:
  sources: ["approved-observer-A", "approved-observer-B"]
  detail: "Leaving observed, streaming active"
decision: WAIT_AND_RECONCILE
actor: "authorized-controller"
~~~

Audits must record **intent before side effects**, identity/cluster/scope, transport outcome or UNKNOWN, observations, human approvals, and final postconditions. Never log JMX passwords, tokens, private keys, or customer data.

### 20.2. Durable storage must truly be durable

An `audit.log` inside an ephemeral container disappears on pod reschedule. The journal needs durable external storage with proven transactions/CAS, backups, ACLs, and retention. Attach `journal_revision` and `controller_epoch` to disambiguate competing workers.

Model both crash windows explicitly:

1. **After persisting intent, before dispatch:** side effect may not have fired, yet the journal marks "uncertain."
2. **After dispatch, before persisting response:** Cassandra may already be mutating the ring while the journal lacks confirmation.

When exact outcomes cannot be proven, transition to **HUMAN_REVIEW** rather than clearing "uncertain" by deleting journal entries.

### 20.3. Evidence vs. inference

| Observation | Permitted conclusion |
|---|---|
| `nodetool status` on observer A shows `UL` | Observer A saw target Leaving at that timestamp |
| CLI timeout | Controller lacks a trustworthy response |
| Streamed bytes climb across samples | Streaming progress on that metric |
| Target absent from one status output | Insufficient to declare decommission complete |
| Node Up/Normal + CQL read PASS | Only partial liveness/query correctness |
| Low p99 across 10 requests | Insufficient sample size for production SLO |
| Journal `state=COMPLETED` while cluster state differs | **Inconsistency: HOLD**; inspect audit and live state |

### 20.4. Closure report template

~~~text
Change and operation IDs
Action: BOOTSTRAP / DECOMMISSION
Cluster ID, target host ID, DC/rack, volume/instance identity
Manifest hash/revision, approver, controller epoch
Dispatch intent count, request response (ACK/TIMEOUT/UNKNOWN)
Observed phase timeline with node/source/time
Before vs after expected membership/token ownership
Streaming/repair/hints/compaction observations
CQL probes with CL, local DC and representative query results
Resource/SLO p95/p99, retries, error/timeout rate
Final: COMPLETED or HOLD/HUMAN_REVIEW, limitations, owner
~~~

Never emit a blanket `SUCCESS` when source/UTC timestamps are missing or an `UNKNOWN` was overwritten by a stale sample.

## 21. Kubernetes, VMs, and service discovery do not replace topology gates

### 21.1. Kubernetes StatefulSets/PVCs and operators

Kubernetes `StatefulSet`s, pod ordinals, PV/PVCs, and readiness probes manage processes and storage, yet do not guarantee Cassandra safely joined or left the ring.

Guard against:

- Reused pod ordinals and DNS names.
- PVCs containing another node's data/system tables.
- Readiness probes checking only a TCP port instead of RF/CL.
- New nodes marked `UN` while streaming/compaction has not settled.
- Two controllers scaling a StatefulSet or competing with the operator.
- Operators restarting while Cassandra remains Joining/Leaving.

If the cluster uses a **Cassandra operator supporting bootstrap/decommission**, defer to the operator's API, state machine, and official SOP—**never run external scripts racing it for topology control**. Custom resource names and fields depend on your operator and distribution.

### 21.2. Service discovery and gossip do not share identical state

Cassandra gossip may mark a node `UN` while Java Driver/clients have not discovered the peer, network policies block native ports, TLS SANs mismatch DNS, or Kubernetes Service endpoints lag.

Post-decommission, drivers may briefly retain stale peer connections to the departed node; that does not mean decommission failed, yet postflight must verify **new connections and key CQL paths** recover within policy windows.

### 21.3. VM/bare-metal provisioning

A cloud API timeout after a VM-creation request does not prove the VM was not created. Query instance IDs and resource state via read-only APIs, matching volume/host IDs and the journal. Never spin up a second VM merely because the create call timed out.

In particular, automation must never select disks or hosts using a `first available` selector after a crash. Target storage identities must stay pinned to the approved manifest.

## 22. Operational permissions and secret safety

### 22.1. Least privilege

| Principal | Required permissions | Avoid by default |
|---|---|---|
| Read-only observer | JMX/metrics/metadata reads per policy | Decommission/`removenode` |
| Operation journal writer | CAS state/audit | SSH/root on Cassandra nodes |
| Dispatcher | Single approved action on exact cluster/target | Wildcard admin access |
| Human approver | Approve changes and exceptions | Self-signing and self-executing without dual control |
| CQL probe role | `SELECT`/`MODIFY` on probe table | Cassandra superuser |
| Report viewer | Redacted logs/metrics | Raw secrets / heap dumps |

`nodetool` normally uses JMX with separate auth/TLS; a CQL role with `SELECT` does not imply JMX admin access. Never grant admin privileges to the whole controller just so health probes can read data.

### 22.2. Command injection and target substitution

~~~text
# ANTI-PATTERN pseudocode - DO NOT use in practice.
shell("nodetool -h " + userSuppliedHost + " decommission")
~~~

Use typed arguments in supported tooling, host ID/cluster allowlists, and approved manifest revisions, rejecting arbitrary flags or shell fragments from user input. Verify identity immediately **before dispatch**, not just when opening the change ticket.

### 22.3. Losing visibility due to mid-flight secret rotation

If JMX/TLS/auth credentials rotate while decommission runs, the controller may lose connectivity while Cassandra keeps streaming.

Safe response:

1. Record `UNKNOWN` for observations.
2. Do not retry topology commands.
3. Restore trust/secrets via a separate runbook.
4. Re-read the journal and verify target host ID.
5. Resume read-only reconciliation; never assume "command failed."
6. If control-plane split-brain occurs, HOLD for human review.

### 22.4. Keep the cluster running even if the controller fails

When a controller loses authority, halt **new mutations**. Never kill production JVMs/nodes just to "release a lock": in-flight Cassandra side effects do not stop cleanly that way. Revoking admin access or locks to **block further dispatches** must be planned without disrupting ongoing streaming.

## 23. Runbook A — Bootstrap timeout where the controller wants to spawn a second node

**Situation:** Cloud API times out after requesting provision/start of node B. The controller lacks `created=true`, yet node B may already be running and streaming.

1. **HOLD dispatch**: never create a new node, VM, pod, or PVC.
2. Read the durable operation ID, approved manifest, instance/volume identity, and command intent.
3. Query infrastructure APIs **read-only**: does B exist or is it pending?
4. Collect `nodetool status`, gossip, and streaming evidence from multiple observers.
5. Compare host ID, DC, rack, and tokens against the manifest—not DNS/IP alone.
6. If B is Joining/streaming, mark `IN_PROGRESS` and poll read-only.
7. If B is Up/Normal, transition to `VERIFYING` to test CQL, RF/CL, p99, and resources.
8. If B is unobserved yet intent may have fired, mark `HUMAN_REVIEW`.
9. Only an owner following SOP decides recovery with evidence; never provision a duplicate node.
10. RCA: provider idempotency request IDs, durable journaling, and crash-window tests.

**Never use a different hostname/IP as a "bootstrap retry"**: that risks creating an unplanned node.

## 24. Runbook B — Lease expires mid-decommission

**Situation:** Controller A dispatches decommission and loses network while streaming; B acquires the lease with a new epoch.

1. B reads the journal and sees `COMMAND_INTENT_RECORDED`/`COMMAND_DISPATCH_UNCERTAIN`.
2. B **does not** dispatch decommission a second time.
3. B verifies cluster, host ID, manifest revision, and owner epoch.
4. B observes `status`/`netstats`, JMX, logs, and metrics via approved observers.
5. Target Leaving/streaming → `IN_PROGRESS`, continue observing.
6. Target absent → verify all postconditions, then `COMPLETED`.
7. Target Normal while uncertain if command arrived → `HUMAN_REVIEW`.
8. Prevent stale worker A from gaining new dispatch authority; remember epochs do not cancel active Cassandra side effects.
9. Verify no unplanned topology mutation intervened.
10. Re-test lease expiry/reconciliation post-incident and archive audit chronology.

**Leases pick the coordinator; they do not cancel a decommission already inside Cassandra.**

## 25. Runbook C — Host ID, PVC, or IP mismatches manifest

**Situation:** Live host ID at the target address differs from the approved host ID, or a bootstrapping node mounted a volume holding another node's data.

1. Stop dispatch; preserve journal, approvals, and evidence.
2. Compare cluster ID, host ID, DC/rack, VM/pod/PVC, and node address.
3. Check for unplanned replacements, reimages, reschedules, or manual edits.
4. Never use IP, DNS, or ordinal as justification to auto-update the target.
5. Read metadata read-only; never manually edit `system.local`/`system.peers_v2`.
6. Never wipe data directories or `system` keyspaces to force bootstrap.
7. Preserve logs and disk identities for the replacement SOP.
8. Operators must approve a new manifest/change if the target entity changed.
9. Re-run RF/CL/topology/CQL gates after resolving identity.
10. Add host ID/PVC mismatch alerts to preflight.

**Identity mismatch = hard STOP**—never bypass it just to reach a target node count.

## 26. Runbook D — Bootstrap/decommission streaming stalls

**Situation:** Streamed bytes flatten across multiple samples while disk await/GC climbs and app p99 degrades.

1. Identify action, node, token ranges, and source/destination.
2. Compare multi-sample streaming progress; one flat sample does not prove a stall.
3. Inspect disk free/await, network RTT/retransmits, internode TLS/gossip, and logs.
4. Check `tpstats`, `compactionstats`, GC, hints, and repair contention.
5. Check whether any unexpected node went DOWN or RF/CL became unavailable.
6. Never launch extra topology changes, major compaction, repair, or cleanup to "nudge progress."
7. Shed non-essential background load per SOP while protecting business traffic SLOs.
8. Track progress/metrics against deadlines; classify `IN_PROGRESS`/`HOLD`.
9. If abort/recovery is required, run release-specific approved commands—never assume `kill -9` is rollback.
10. RCA capacity, networking, retry storms, and streaming thresholds.

**CLI acceptance does not mean data movement finished.**

## 27. Runbook E — Decommission target is already DOWN or absent

**Situation:** Node A turns `DN` prior to dispatch, or status lacks a matching row.

1. Halt the controller; never send decommission to an arbitrary IP.
2. Distinguish DOWN, unreachable, Leaving, already absent, and stale observer views.
3. Match exact host ID, cluster/DC/rack, and journal history.
4. Check RF/CL, replica health, and CQL errors on remaining nodes.
5. Determine whether the node can recover with its original identity and data.
6. If decommission already completed, run full postflight without re-issuing.
7. If it died prior to the operation, switch to the **node-failure/replace/removal SOP**.
8. Never reflexively run `removenode` merely because decommission cannot run.
9. Never lower RF/CL just to make the pipeline green.
10. Audit the new action scope and human approvals if needed.

**Clean decommission of a live node differs from removing a dead node.**

## 28. Runbook F — An unplanned second operation appears

**Situation:** While B bootstraps, another workflow decommissions A or an engineer runs a manual topology command.

1. Halt all **new dispatches** within cluster scope.
2. Identify which operations already triggered side effects via journals, logs, and ring state.
3. Never issue an opposing command to "undo" it automatically.
4. Inspect token/replica sets, DC/rack, and RF/CL of all involved changes.
5. Monitor p99, CPU, GC, disk, and network, throttling non-essential loads if needed.
6. Audit leases/epochs, approvals, RBAC, and external admin access.
7. For active transfers, observe read-only without launching another operation.
8. Let the human incident commander decide recovery sequencing per SOP.
9. Once stable, re-run preflight with fresh operation IDs and approvals.
10. RCA scope locking, CI retries, operator contention, and access controls.

**Two independent coordinators cannot both mutate the ring and still be called serialized maintenance.**

## 29. Runbook G — Topology looks right, yet `LOCAL_QUORUM`/p99 fails

**Situation:** Node B is `UN` or A is absent, yet Java Driver `LOCAL_QUORUM` times out, data mismatches, or p99 spikes.

1. Hold in `VERIFYING`/`HOLD`; do not mark `COMPLETED`.
2. Inspect RF/CL/DC/rack and replica placement for failing workloads.
3. Check client local DC, peer discovery, and native TLS/auth/ports.
4. Run CQL read/write probes in the dedicated probe table and bounded representative business queries.
5. Separate `Unavailable`, timeouts, schema/codec errors, and auth failures—never lump them as "node down."
6. Inspect worst-node resources, compaction/streaming/hints, and retry rates.
7. Never lower CL or raise timeouts indefinitely to fake a PASS.
8. On data mismatches, inspect TTLs, day buckets, replicas, and repair policies.
9. If postflight fails, the human owner invokes recovery/rollback SOPs if feasible.
10. Close only once CQL correctness, errors, p99, capacity, and remaining replicas pass.

**One passing canary key does not check every token range or every DC.**

## 30. Runbook H — Autoscaler/CI re-triggers a topology step

**Situation:** A Jenkins job retries or a Kubernetes autoscaler deletes pods while the controller mutates the ring.

1. Pause competing autoscale/maintenance pipelines per operational authority.
2. Correlate `operation_id`, retries, CI attempt IDs, and leadership epochs.
3. Compare orchestrator desired count with actual Cassandra membership and host IDs.
4. Never adjust counts merely because pod/node counts look low.
5. If an operation is active or uncertain, reconcile read-only and HOLD.
6. Audit startup hooks, job restart policies, and HTTP/JMX SDK auto-retries.
7. Enforce a single dispatcher authority and cluster/topology lock per SOP.
8. Job re-runs must reuse the same `operation_id` without minting new intents.
9. Rehearse crashes, API timeouts, lease expiries, duplicate workflows, and stale workers in a lab.
10. Re-enable automation only after zero concurrent actors remain and cluster postconditions pass.

**Pod scaling does not safely migrate Cassandra token ownership on its own.**

## 31. Test matrix for controllers and topology gates

Use unit tests with mocked observers/journals for state logic, integration labs for CQL, and a **dedicated fault lab** for node membership/streaming. Never induce node failures or production decommissions just to test.

| ID | Scenario | Safe outcome |
|---|---|---|
| T01 | NEW without approval | Do not dispatch |
| T02 | APPROVED while preflight UNKNOWN | HOLD |
| T03 | Unplanned node `DN` | FAIL/HOLD |
| T04 | Status lists 5/6 nodes, all `UN` | Inventory mismatch |
| T05 | Bootstrap target already exists in infra | Reconcile; do not create a new instance |
| T06 | New node host ID collides with old member | Hard STOP |
| T07 | New node joins wrong DC/rack | FAIL/HOLD |
| T08 | B already Joining before intent dispatch | Do not dispatch again |
| T09 | B `UN`, streaming unverified | VERIFY/HOLD |
| T10 | Provision API times out | `COMMAND_DISPATCH_UNCERTAIN` |
| T11 | Crash after journal intent, before command | Human review unless outcome proven |
| T12 | Crash after command, before persisting response | Read-only reconcile |
| T13 | Lease expires while streaming runs | New owner does not dispatch |
| T14 | Stale-epoch worker tries writing state | Rejected by CAS/epoch |
| T15 | Two controllers reserve the same scope | Only one wins authority |
| T16 | CI retries the same `operation_id` | No new intent created |
| T17 | Different `operation_id` while cluster is active | Block conflict |
| T18 | Admin runs manual command bypassing journal | HOLD/escalate |
| T19 | Decommission target not Up/Normal | Do not dispatch |
| T20 | Target already Leaving | Observe; do not dispatch |
| T21 | Target absent from only one observer | Not COMPLETE |
| T22 | Target absent, yet CQL FAILS | HOLD |
| T23 | IP reused / host ID changed | Identity hard STOP |
| T24 | PVC holds another Cassandra identity | Do not provision/start |
| T25 | RF=3, yet DC would drop to 2 nodes | Reject / separate plan |
| T26 | Replica DOWN before decommission | HOLD per fault budget |
| T27 | CQL `ONE` PASS, `LOCAL_QUORUM` FAIL | CQL hard gate FAIL |
| T28 | TLS/new connection fails post-bootstrap | Postflight FAIL |
| T29 | Write/read canary PASS, business query times out | Not COMPLETE |
| T30 | p99 exceeds absolute SLO despite target `UN` | HOLD |
| T31 | Low free disk prior to streaming | Preflight FAIL |
| T32 | Streamed bytes flat in one sample | Needs more evidence |
| T33 | Prolonged streaming stall + high disk await | HOLD/escalate |
| T34 | `netstats` empty while target still Leaving | Do not auto-COMPLETE |
| T35 | Schema agreement fails | HOLD |
| T36 | Java prepared query errors post-upgrade | Compatibility FAIL |
| T37 | Metrics/JMX missing | UNKNOWN, not zero |
| T38 | Observer samples stale | UNKNOWN |
| T39 | Unparseable `nodetool` output format | UNKNOWN |
| T40 | Job/SDK auto-retries decommission step | Blocked by dispatcher |
| T41 | Provider API auto-retries VM creation | Idempotency ID or block |
| T42 | Repair/compaction exceeds resource budget | HOLD |
| T43 | Unplanned replacement operation appears | Human review |
| T44 | Journal CAS/persist fails | Do not dispatch |
| T45 | CLI exits 0 while target stays Leaving | `IN_PROGRESS`/HOLD |
| T46 | Overall deadline expires mid-transfer | Escalate; do not retry |
| T47 | Counters reset after restart | Do not miscalculate progress |
| T48 | Bootstrap reaches target state + CQL/resources PASS | COMPLETE |
| T49 | Decommission reaches target state + CQL/resources PASS | COMPLETE |
| T50 | Missing postflight hard gate | UNKNOWN/HOLD, not COMPLETE |

### 31.1. Test layers and boundaries

- **Unit:** immutable manifest validation, CAS/lease/epoch conflicts, state machine, no-dispatch recovery, inventory equality, stale-observer handling.
- **Integration:** durable journal, mocked infra APIs, CQL probes, metric parsers, controller cancellation.
- **Cluster lab:** Joining/Leaving/streaming, quorum under node faults, multi-DC local routing, disk pressure, node replacement.
- **Failure-injection controller:** crash windows before/after dispatcher, timeouts, network drops, dual leaders, duplicate CI jobs, forced observer failures.

A single-node RF=1 Cassandra lab cannot validate RF=3/`LOCAL_QUORUM` in multi-rack/multi-DC topologies. Never treat "no exception" as enough; assert the exact invocation count of topology commands.

### 31.2. Stop conditions for fault tests

~~~text
[ ] Unexpected node down or membership diverges from plan.
[ ] RF/CL no longer satisfied in the lab.
[ ] Disk/memory/GC/IO pressure crosses guardrails.
[ ] Journal/lease consistency indeterminate.
[ ] Two actors potentially able to dispatch concurrently.
[ ] Observations stale, missing, or parser broken.
[ ] Data correctness probe fails.
[ ] Recovery plan infeasible within lab bounds.
~~~

**Stopping a test due to a guardrail is a valid outcome.**

## 32. JUnit: verifying reconciliation never re-dispatches

### 32.1. Key test cases

This JUnit 5 example assumes the `Operation`, `ClusterSnapshot`, and `SafeReconciler` records/interfaces defined in Section 17; requires a JDK supporting Java records and is not intended directly as production code.

~~~java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeReconcilerTest {
    private Operation operation() {
        return new Operation(
            UUID.randomUUID(), "cluster-lab",
            Action.DECOMMISSION,
            new NodeIdentity(
                UUID.randomUUID(), "dc1", "rack1", "vm-A"),
            State.COMMAND_DISPATCH_UNCERTAIN,
            5L, 42L, Instant.EPOCH);
    }

    private ClusterSnapshot observed(
            boolean fresh, boolean sameIdentity,
            boolean moving, boolean after, Gate post) {

        return new ClusterSnapshot() {
            public boolean hasFreshObservers() {
                return fresh;
            }
            public boolean targetIdentityMatches(
                    NodeIdentity id) {
                return sameIdentity;
            }
            public boolean targetJoiningOrLeaving(
                    NodeIdentity id) {
                return moving;
            }
            public boolean targetAtExpectedAfterState(
                    Operation op) {
                return after;
            }
            public Gate healthAndCqlPostconditions(
                    Operation op) {
                return post;
            }
        };
    }

    @Test void staleEvidenceHolds() {
        assertEquals(State.HOLD, SafeReconciler.nextOnRecovery(
            operation(), observed(false, true, false, false,
                                   Gate.UNKNOWN)));
    }

    @Test void activeStreamDoesNotRetrigger() {
        assertEquals(State.IN_PROGRESS,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, true, false,
                                      Gate.UNKNOWN)));
    }

    @Test void uncertainDispatchGoesToHuman() {
        assertEquals(State.HUMAN_REVIEW,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, false, false,
                                      Gate.UNKNOWN)));
    }

    @Test void afterStateRequiresCqlAndHealth() {
        assertEquals(State.HOLD, SafeReconciler.nextOnRecovery(
            operation(), observed(true, true, false, true,
                                  Gate.FAIL)));
    }

    @Test void verifiedAfterStateCompletes() {
        assertEquals(State.COMPLETED,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, false, true,
                                      Gate.PASS)));
    }
}
~~~

### 32.2. Most critical invariant test

~~~text
Given:
  Stored journal state COMMAND_DISPATCH_UNCERTAIN;
  controller restarts, leader epoch changes;
  snapshot shows target Leaving.

When:
  reconcile called 100 times, including transient poll errors.

Then:
  topologyCommandAdapter.invocationCount == 0
  operation stays IN_PROGRESS / HOLD / VERIFYING
  no extra VM/pod/PVC instance is created.
~~~

Unit tests prove the controller's internal code paths; **they do not prove no external admin ran commands outside the controller**. Exclusivity requires RBAC, auditing, and control-plane process discipline.

## 33. Practice questions with answers

### Question 1 — Decommission command timeout

A controller sends `decommission` and times out. Does that prove Cassandra never received the command?

**Answer:** No. The command may already have placed the target into Leaving/streaming. Mark the outcome `UNKNOWN` and reconcile read-only; never re-dispatch.

### Question 2 — `nodetool bootstrap`

Can a script call a universal `nodetool bootstrap` across every Cassandra version?

**Answer:** No. Bootstrap normally occurs when a new node boots with join configuration; APIs/flags and operations depend on release and operator.

### Question 3 — Restarts and identity

An existing node restarts with a data directory already holding a host ID. Should a new host ID be assigned?

**Answer:** No. Restarts must preserve existing data and identity; changing identity creates a different member and belongs to a replacement SOP.

### Question 4 — IP reuse

Target A's IP was reused by pod B. Can we decommission based solely on the IP in an old ticket?

**Answer:** No. Verify the exact host ID, cluster, DC, rack, PVC, and instance from the approved manifest.

### Question 5 — Lease expiry

Controller A loses its lease while Cassandra is still decommissioning. Should B, upon winning the new epoch, re-send the command?

**Answer:** No. Leases transfer orchestration ownership; they do not cancel in-flight Cassandra side effects.

### Question 6 — Fencing

Does fencing epoch 42 in the journal halt a Cassandra command already sent by epoch 41?

**Answer:** No universal guarantee exists. Management commands do not necessarily inspect epochs; prevent new dispatches and reconcile read-only.

### Question 7 — Crash gap

Intent was persisted, yet the controller crashed right before dispatch. What must Controller B do?

**Answer:** Gather evidence from infrastructure APIs, the Cassandra ring, logs, and the journal. Whenever uncertain whether the command fired, HOLD/`HUMAN_REVIEW`.

### Question 8 — Exit code

Does `nodetool decommission` exit 0 prove the target left and the app is error-free?

**Answer:** Insufficient. Verify exact host ID absence across multiple observers, token/replica placement, streaming, RF/CL, CQL correctness, p99, and resources.

### Question 9 — Single observer

Node A does not appear in observer X's `nodetool status`. Can we mark COMPLETE?

**Answer:** No. Gossip views may be stale, a network partition may exist, or the observer hit the wrong cluster. Cross-check multiple sources and operation history.

### Question 10 — Node `DN`

The decommission target is already DOWN. Should we retry the command on another node?

**Answer:** No. Clean decommission differs from dead-node removal/replacement; switch to an approved SOP.

### Question 11 — RF and scaling in

A DC has 3 nodes with RF=3 and wants to scale down to 2 while keeping RF=3. Is that safe?

**Answer:** No. Redesign replication, fault tolerance, and capacity via a separate change rather than lowering CL/RF to bypass gates.

### Question 12 — Quorum

RF=3, app uses `LOCAL_QUORUM`, one replica is DOWN yet requests still succeed. Can we auto-restart another replica?

**Answer:** Not by default. Current request ACKs do not mean headroom remains to lose another node.

### Question 13 — Rack placement

A new node comes up `UN` in the wrong rack. Does bootstrap PASS?

**Answer:** No. Failure domains and replica placement may violate the manifest; HOLD and check token/rack/DC policies.

### Question 14 — Streaming flat in one sample

Streamed bytes did not increase in a single sample. Does that prove the operation hung?

**Answer:** No. Inspect a multi-sample window, disk/network/GC, logs, and phase-specific observations.

### Question 15 — `netstats`

Does an empty `nodetool netstats` mean all hints, repair, and replication traffic finished?

**Answer:** No. It reflects primarily SSTable streaming; monitor hints, repair, and CQL via dedicated metrics.

### Question 16 — Source resources

The new node has plenty of free disk, while source peers have full disks and compaction backlogs. Should bootstrap start?

**Answer:** Do not auto-PASS. Bootstrap streams from peers, requiring headroom on both source and destination.

### Question 17 — CQL probe CL

Nodes are `UN` and a `ONE` probe PASSes, while the app's `LOCAL_QUORUM` times out. Overall result?

**Answer:** FAIL/HOLD. The probe does not represent the business workload's CL.

### Question 18 — Single probe key

Does one `run_id` write/read-back PASS prove every token range is healthy?

**Answer:** No. One key covers one replica set; add topology/coverage checks, representative reads, and per-DC checks.

### Question 19 — Cleanup

Bootstrap just completed. Should automation immediately run cluster-wide cleanup to free disk?

**Answer:** No. Cleanup is a side-effecting storage operation requiring ownership, retention, version, and capacity gates under its own SOP.

### Question 20 — Repair

Decommission is running slowly. Should automation launch a cluster-wide repair to "push streaming along"?

**Answer:** No. Repair increases I/O pressure; diagnose the root cause first.

### Question 21 — CQL zero rows

A CQL canary query by event day returns 0 rows while nodes are healthy. Does that prove bootstrap lost data?

**Answer:** Not yet. It could be the wrong partition key or day bucket, TTL expiration, an unseeded fixture, or policy-expected consistency lag.

### Question 22 — Kubernetes

Does scaling a StatefulSet from 6 to 5 guarantee a clean Cassandra decommission?

**Answer:** No. Pod count differs from ring membership, token ownership, and streaming completion.

### Question 23 — Two controllers

Both CI and a Cassandra operator have topology privileges. Is locking only the CI pipeline enough?

**Answer:** No. Locks and processes must cover every actor with side-effect privileges; enforce single ownership and auditing.

### Question 24 — Stale snapshot

Preflight passed 30 minutes ago, yet metrics are now unreachable. Continue decommission?

**Answer:** No. Without fresh evidence, mark `UNKNOWN`/HOLD.

### Question 25 — Rollback

Mid-decommission, the controller wants to `kill -9` the JVM to "undo." Is that safe?

**Answer:** Not by default. Replicas may already have shifted data/tokens; follow release-specific abort/recovery SOPs with human approval.

### Question 26 — Schema

The new node is Up/Normal while Java prepared CQL queries fail. Is bootstrap complete at the app layer?

**Answer:** Not yet. Stay in `VERIFYING`/HOLD and inspect schema, codecs, native TLS/auth, and local DC.

### Question 27 — Ephemeral journal

The journal lives only inside a container and is lost on restart. Can single-dispatch still be guaranteed?

**Answer:** No. You need a durable CAS journal, audit trail, and read-only recovery.

### Question 28 — Lost JMX while Leaving

Can we conclude decommission failed and re-issue it because the observer's credentials expired?

**Answer:** No. Loss of observability is `UNKNOWN`; restore JMX/trust and reconcile.

### Question 29 — Unit tests

Are unit tests verifying `SafeReconciler` never dispatches enough to prove no other admin intervened?

**Answer:** No. They verify internal code paths; external actors require RBAC, locks, and audits.

### Question 30 — COMPLETE

What criteria close a topology operation successfully?

**Answer:** Exact target identity matches expected post-state, replica/token/streaming and RF/CL are safe, CQL/Java correctness and error/p99/resource budgets pass, and full observation windows plus audit evidence exist; missing any hard gate → HOLD.

## 34. Checklist before, during, and after bootstrap/decommission

### 34.1. Change preparation

~~~text
[ ] Change ID, operation ID, and approved manifest exist.
[ ] Cluster ID, target host ID, DC/rack, and node/PVC/instance identity pinned.
[ ] Cassandra release/operator/SOP compatibility verified.
[ ] Exact action classified: BOOTSTRAP, DECOMMISSION, REPLACE, or REMOVENODE.
[ ] No other topology operation active under cluster/scope lock.
[ ] Durable CAS journal and leader lease/fencing epoch verified.
[ ] SDK/CI/operator retry policies disabled on the topology dispatcher.
[ ] Approved operator and explicit rollback/forward-recovery plan ready.
[ ] No unintended DOWN nodes; schema/topology metadata consistent.
[ ] RF/CL, rack/DC fault tolerance, and app SLA confirmed.
[ ] Disk/network/GC/CPU and compaction/repair/streaming headroom sufficient.
[ ] Native CQL probes and baseline workload healthy.
[ ] All evidence carries UTC timestamps, sources, and freshness.
~~~

### 34.2. Bootstrap-specific gates

~~~text
[ ] New node has no identity/token collision with existing members.
[ ] Volume/data dir identity accurate; no improper PVC reuse.
[ ] Seed/gossip/internode/client TLS/native configs validated.
[ ] DC/rack placement and datacenter RF policy match plan.
[ ] Source peers have sufficient streaming capacity.
[ ] Controller persists intent before provisioning/starting.
[ ] Never spawn a second VM/pod/node after a timeout.
[ ] Monitor Joining/streaming from multiple sources.
[ ] Once Normal, check tokens, schema, CQL, and Java peer discovery.
[ ] No automated cleanup/repair without an SOP.
[ ] App errors/p99 and source/destination resources healthy.
~~~

### 34.3. Decommission-specific gates

~~~text
[ ] Exact target is Up/Normal, not already Leaving or absent.
[ ] Remaining nodes/DC/rack satisfy RF/CL/fault tolerance.
[ ] Receiving peers have disk/network/I/O headroom for streams.
[ ] No conflicting repair, replacement, or topology actions.
[ ] Intent durably persisted; action dispatched at most once.
[ ] Timeouts never cause command replay.
[ ] Leaving state and streaming/metrics tracked by read-only observers.
[ ] Target absent across multiple views, matched by exact host ID.
[ ] Token ownership, schema, and remaining nodes match plan.
[ ] App CQL at target CL and business read-back succeed.
[ ] Never restart/decommission the next node before completion.
~~~

### 34.4. Recovery on lost response

~~~text
[ ] Journal, intent, epoch, and revision re-read.
[ ] Two active topology dispatchers cannot exist.
[ ] Cluster and target identity match approved manifest.
[ ] Fresh observations gathered from multiple nodes/sources.
[ ] If target Joining/Leaving, observe read-only only.
[ ] If target absent or new Normal, run postflight without re-issuing.
[ ] If outcome cannot be proven, transition to HUMAN_REVIEW/HOLD.
[ ] Never edit system tables, wipe data dirs, or run removenode blindly.
[ ] Human actions/approvals audited; mint new operation ID if scope changes.
[ ] Never close a change from a CLI exit code alone.
~~~

### 34.5. Change closure

~~~text
[ ] Expected post-topology verified with exact matching identities.
[ ] RF/CL and app read/write CQL queries pass.
[ ] Schema, JDK, driver, and native TLS/auth compatibility verified.
[ ] Streaming/recovery state clear; pending jobs assigned owners.
[ ] Worst-node disk/GC/CPU/network headroom within policy.
[ ] CQL/app p95/p99, timeouts, errors, and retries within SLO.
[ ] Observation window sufficiently long; metrics fresh.
[ ] Durable audit report, limitations, and owner sign-off archived.
[ ] Controller retains no stale leases or elevated privileges.
[ ] Do not run STEP 6 subject-matter Content QA during this writing step.
~~~

## 35. Anti-patterns to block in code review

| Anti-pattern | Risk | Replacement rule |
|---|---|---|
| Retrying topology command after timeout | Side effect already started may repeat | Read-only reconcile |
| Minting a new `operation_id` on job restart | Breaks deduplication | Reuse durable ID |
| Locking only per pod, not cluster | Two controllers dispatch concurrently | Scope locks by topology |
| Treating lease expiry as command cancelled | False regarding Cassandra side effects | Fencing + journal + reconcile |
| Keying by IP instead of host ID | IP reuse hits a different node | Immutable identity |
| Reimaging + wiping system tables to bootstrap | Loss of data/identity metadata | Release-specific replacement SOP |
| Skipping expected node inventory | Missing node still PASSes | Compare host IDs/DC/rack |
| Node `UN` = operation complete | Streams/queries/resources may fail | Multi-layer postflight |
| CLI exit 0 = data safely moved | Never checks replicas/CL | Expected post-state + CQL |
| Polling every second forever | JMX/CPU/monitoring strain | Bounded backoff and deadlines |
| Auto-continuing on UNKNOWN | Hides missing evidence | Fail closed |
| Running repair/cleanup as health check | Side-effecting / heavy I/O | Separate scheduled operations |
| CQL probe `ONE` when app uses `QUORUM` | Masks replica failures | Match workload CL |
| One probe key representing the whole ring | Misses other replica sets | Topology coverage |
| Scaling StatefulSet as decommission | Pod lifecycle differs from ring lifecycle | Operator/SOP |
| Running add and remove in parallel | Token/data movement conflicts | Serialize steps |
| Disabling TLS for quick checks | Breaks security | Approved SSL/auth config |
| Granting superuser for probe controllers | Excessive blast radius | Least privilege |
| Lowering RF when cluster is degraded | Alters correctness/fault tolerance | Plan capacity/replication separately |
| Declaring stall from one sample | False alarms | Time-series + metrics |
| Ignoring source disk during bootstrap | Streaming overloads peers | Check capacity on both sides |
| Restarting next node before current stabilizes | Loses quorum and headroom | Per-node health gates |
| Storing journal in ephemeral pods | Loses dispatch history | Durable CAS store |
| Holding locks while external admins run CLI | Controller loses exclusivity | RBAC + audit + change freeze |
| Logging passwords or volume secrets | Data leakage | Redaction and ACLs |

## 36. Summary

Orchestrating **bootstrap and decommission without repeating dangerous operations** requires thinking like a distributed transaction system with **side effects lacking global idempotency keys**, not a retry loop in a script.

1. **Identify exact targets** via cluster ID, host ID, DC/rack, instance/PVC, and approved manifest—never IP or pod name alone.
2. **Distinguish bootstrap, decommission, replace, `removenode`, and restart**; each has unique preconditions and SOPs.
3. **Persist durable command intent before side effects**, using stable operation IDs and journal CAS/revisions.
4. **Allow at most one dispatcher per scope** to mutate the ring; leases and epochs coordinate controllers without stopping already-running Cassandra commands.
5. **Never retry topology commands after timeouts or crashes.** Bounded retries apply only to observations; uncertain outcomes → HOLD/`HUMAN_REVIEW`.
6. **Use phase-aware postconditions in the state machine**: Joining/Normal and transfers for bootstrap; Leaving/absent and transfers for decommission.
7. **Preflight checks RF/CL, replica/fault-domains, and storage/streaming/network headroom** before letting nodes enter or leave.
8. **Postflight verifies expected inventory/host IDs, token ownership, CQL correctness, and latency/resources**, beyond `UN` and CLI exit codes.
9. **Treat cross-DC and Java Driver verification as dedicated gates**, using read/write probes at workload CL with explicit scopes.
10. **Never auto-invoke repair/`cleanup`/`removenode` to "heal" incomplete operations**; those are separate risky procedures.
11. **Keep audits and observability fresh and provenance-tagged** so handover operators never have to guess.
12. **Enforce a fail-closed policy**: missing evidence or identity drift is a stop trigger, never permission to retry.

The final question before any step is not **"Did the previous command return success?"**, but rather **"Could the side effect already have started, did it target the right node and cluster, what phase is Cassandra in, are RF/CL and data safe, and do we have sufficient evidence to proceed without issuing a second ring-mutating command?"**

Whenever current evidence cannot answer that question, **halt dispatching, keep observing, and escalate to an operator under SOP**—that is always the safe choice.
