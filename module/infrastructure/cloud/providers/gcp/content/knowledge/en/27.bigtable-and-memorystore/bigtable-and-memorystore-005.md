# Replication, Consistency, and Access Routing in Bigtable

A retail system collects product views from **Cloud Run** and device events from **GKE**, storing time-series data in **Bigtable**. Customers in two regions want to read data near where they connect, yet operations must also answer: *if an event is written to cluster A and immediately read from cluster B, is it guaranteed to show the new data? If cluster A stops serving, which cluster does the application fail over to, and what consistency guarantees are lost?*

**Replication** increases availability and places data replicas closer to applications, but does not automatically provide global transactions like **Spanner**. In Bigtable, selecting an **application profile (app profile)** determines which cluster receives requests, directly affecting **consistency, failover, latency, and cost**.

This lesson belongs to the **Bigtable and Memorystore** chapter, **CLOUD_PROVIDERS_GCP** module. It focuses on **Bigtable replication, consistency, and access routing**, connecting with IAM, VPC, Compute Engine, GKE, Cloud Run, reliability monitoring, and cost. *Memorystore is a separate caching/in-memory service; it does not synchronize or guarantee consistency for Bigtable data.*

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe replication between **clusters within the same Bigtable instance** and why a replica can lag behind the source.
2. Distinguish **eventual consistency**, **read-your-writes**, and scenarios that can achieve **strong consistency**.
3. Choose **single-cluster**, **multi-cluster/any-cluster**, **cluster group**, or **row-affinity** app profiles.
4. Explain why **single-row transactions** require dedicated routing and cannot be combined with multi-cluster routing.
5. Configure app profiles, verify settings, and plan manual/automatic failovers with `gcloud`.
6. Monitor **replication latency, max delay, CPU, errors, and automatic failovers**, evaluating RPO/RTO against system targets.
7. Design tests and runbooks for multi-region applications while avoiding conflicting writes and surprise costs.

## 2. How Does Bigtable Replication Work?

### 2.1. Instances, Clusters, Tables, and Replicas

A **Bigtable instance** contains one or more **clusters** located in supported zones/regions. Clusters within a replicated instance hold **replicas of the same tables**, while each cluster has independent serving capacity. All clusters can serve **both reads and writes**; there is no single default primary like in some relational databases.

~~~mermaid
flowchart LR
    A["Cloud Run / GKE region A"] --> P["App profile"]
    P --> CA["Cluster A"]
    P --> CB["Cluster B"]
    CA <-->|"Asynchronous replication"| CB
    CA --> DA["Table replicas"]
    CB --> DB["Table replicas"]
~~~

A write operation is served by the chosen cluster and then propagated to other clusters. **There is no guarantee that every cluster has received the record at the moment the write succeeds on the first cluster.** Replication can lag due to network distance, write volume, CPU load, or transient issues on a cluster.

| Property | Design consequence |
| --- | --- |
| Each cluster holds a copy of the data. | Storage/cost of a replicated instance scales with the number of clusters and regions. |
| Each cluster serves requests. | Can lower read latency when clients are close to a cluster. |
| Replication is asynchronous. | Reading from another cluster right after a write can return stale data. |
| Clusters accept both reads and writes. | Conflicting writes must be controlled, especially for single-row transactions. |
| App profiles determine routing. | Two apps hitting the same database with different profiles experience different semantics. |

**Replication is not an immutable backup.** Accidental deletions or bad writes replicate to other clusters. To recover from mistakes, use **Bigtable backups** under a separate policy; a backup taken on one cluster may also miss writes from another cluster still pending replication.

### 2.2. Does Replication Increase Throughput?

Reads can be distributed across clusters, reducing latency and increasing regional read capacity. However, **adding a cluster does not automatically increase write throughput**: every cluster must still receive and apply replicated writes, consuming CPU, storage, and network. When capacity planning, include **background replication load**, not just direct client QPS. See [Replication and performance](https://cloud.google.com/bigtable/docs/replication-performance).

## 3. Three Consistency Levels to Distinguish

### 3.1. Eventual Consistency

If an application sends a write to cluster A and reads from B before replication catches up, B may return the previous version. Once replication finishes and no conflicting writes occur, replicas converge to the same state.

~~~text
09:00:00.000  Write row k, status=READY to cluster A → succeeds
09:00:00.010  Read row k via cluster B → may still see status=PENDING
09:00:00.xxx  Replication completes
09:00:00.yyy  Read via B → sees READY
~~~

Timings and latencies above are purely illustrative; **there is no fixed few-millisecond SLA for every write or network path**. For dashboards, clickstreams, IoT telemetry, or analytics tolerating slight staleness, eventual consistency is usually acceptable.

### 3.2. Read-Your-Writes

An application needing to read back its own writes can use **single-cluster routing** and ensure **all related writes and reads for that workload target the same cluster**. Note:

- This guarantee applies to the consistently routed path; **another profile reading from a different cluster can still see stale data**.
- If the system switches clusters during failover, unreplicated data may not yet appear at the target.
- If multiple applications must **observe the same strongly consistent state**, all related workloads must read/write through **the same cluster** without other clusters serving independent operations.

### 3.3. Conditional Strong Consistency

Per Bigtable documentation, achieving **strong consistency on a replicated instance** for a set of workloads requires single-cluster routing across all participating app profiles and **serving reads/writes from a single shared cluster**. Remaining clusters can act as failover standbys or serve unrelated tasks, but if they also serve direct reads/writes, system-wide strong consistency cannot be assumed.

**Failover temporarily breaks this assumption:** failing over to a lagging cluster can return stale reads until replication catches up. Therefore, **HA and strong consistency across failover are not simultaneously guaranteed automatically**. <https://cloud.google.com/bigtable/docs/replication-overview>

| Business requirement | Recommended design | Limitation |
| --- | --- | --- |
| Analytics/telemetry events where staleness is acceptable. | Multi-cluster routing, clusters close to clients. | Eventual consistency. |
| Single app must read back its own just-written values. | Single-cluster routing, read/write same cluster. | Requires manual failover and accepting semantic shifts during failover. |
| Multiple apps must observe the exact same current state. | All app profiles pinned to the same serving cluster. | No other app may write to a second cluster. |
| Automatic HA while trying to reduce single-row stale reads. | Multi-cluster + row-affinity. | **Improves probability**, does not guarantee strict read-your-writes. |

## 4. Conflicting Writes, Atomicity, and Single-Row Transactions

### 4.1. Bigtable's Consistency Unit

A **mutation on a single row** is atomic, even when updating multiple cells in that row within one operation. Bigtable **does not provide ACID transactions updating multiple rows atomically** like Spanner. Business flows requiring multi-table/multi-row transactions or global uniqueness should be designed on an appropriate datastore.

Operations such as **read-modify-write** (increment/append) and **check-and-mutate** are **single-row transactions**. They can produce wrong results if two clusters independently modify the same row/cell before syncing.

### 4.2. Why Multi-Cluster Disallows Transactional Writes

Suppose row `ticket#123` holds `sold=5` on two clusters:

~~~text
Cluster A: increment sold → 6
Cluster B: increment sold → 6   (has not received write from A yet)
Subsequent replication cannot infer the result should be 7.
~~~

To prevent this class of conflicts, Bigtable **only allows single-row transactional writes on app profiles using single-cluster routing**. You can have multiple single-cluster profiles, but **never enable transactional writes on multiple profiles pointing to different clusters if they can make conflicting updates to the same row**. For additive counters, evaluate **aggregate cells** where suitable or enforce a single write path.

### 4.3. Conflict Resolution Is Not "Latest Write on the Client Clock"

A Bigtable cell version is identified by the tuple `(row key, column family, column qualifier, timestamp)`. If **two writes with the exact same tuple** arrive at different clusters, Bigtable uses an **internal server-time last-write-wins** mechanism to resolve conflicts consistently after replication. That is **not** a business-intent transaction merge and does not necessarily pick what the app considers the "newer event." If timestamps differ, both versions can coexist according to retention/GC policies rather than simply overwriting one value. See [Writes and conflict resolution](https://cloud.google.com/bigtable/docs/writes).

For a row receiving concurrent mutations:

- Avoid letting two independent regions decide updates to the same critical state.
- Assign **writer ownership** by row key/tenant when needed; design event IDs, versions, or idempotency.
- Do not rely on clocks across disparate clients to resolve business conflicts.
- If the system requires multi-row transactions or strict invariants, evaluate **Spanner/Cloud SQL**; Bigtable is built for key/row access and high throughput rather than replacing relational transactional systems.

## 5. App Profiles and Four Access Routing Modes

An **app profile** configures how a specific application/workload accesses a Bigtable instance. Clients pass an **app profile ID** when connecting, and Bigtable applies the corresponding **routing policy** and options. You do not need a separate instance just to give analytics workloads different routing from online workloads.

| Routing policy | How it works | Consistency and failover |
| --- | --- | --- |
| **Single-cluster** | Sends all profile requests to one designated cluster. | Read-your-writes when reads/writes share the cluster; **manual failover**. Can enable single-row transactions. |
| **Multi-cluster: any** | Routes to a nearby/available cluster per Bigtable routing. | **Automatic failover**, eventual consistency; single-row transactions cannot be enabled. |
| **Multi-cluster: cluster group** | Restricts routing/failover to a chosen subset of clusters. | Similar to multi-cluster, but never routes to clusters outside the group. |
| **Multi-cluster: row-affinity** | Routes requests for **the exact same row key** more consistently to one cluster. | Improves read-your-writes under normal conditions, **no guarantee** under failover, overload, or cluster topology changes. |

### 5.1. Row-Affinity Is Not Sticky Sessions

Row-affinity keys off the **row key**, not a user's HTTP session, client IP, or fixed region. It fits APIs primarily issuing **single-row reads/mutations**, but:

- Does not apply to **row-range scans** or multi-row requests.
- **Does not apply to Bigtable SQL `ExecuteQuery`**, even when SQL filters a single row.
- Routing can change on failover, network errors, cluster overload, or cluster list changes.
- Using a **cluster group** prevents adding a new cluster from unexpectedly reshuffling row-key assignments.

Therefore, never design payments or inventory requiring strict consistency based solely on row-affinity. Read [Routing options](https://cloud.google.com/bigtable/docs/routing).

### 5.2. Do Not Blindly Trust the `default` App Profile

The `default` app profile is created automatically, yet its default routing depends on **how many clusters existed when the instance was created**:

- Instance **created with one cluster**: `default` typically uses **single-cluster** routing and allows single-row transactions.
- Instance **created with two or more clusters**: `default` uses **multi-cluster** routing and disallows single-row transactions.
- **Adding clusters later does not automatically change the routing of `default`**.

To avoid unintended behavior changes, create **workload-named app profiles** (`orders-consistent`, `telemetry-ha`, `analytics-low-priority`) instead of relying indefinitely on `default`. Separate profiles also let you track CPU/latency per workload.

## 6. Choosing a Topology for Availability and Consistency Goals

### 6.1. Active–Passive: Prioritizing Consistency

~~~mermaid
flowchart LR
    APP["Transactional app"] --> PROFILE["Single-cluster app profile"]
    PROFILE --> A["Cluster A: serving"]
    A <-->|"Replication"| B["Cluster B: standby"]
    PROFILE -. "Switch route-to when needed" .-> B
~~~

All consistency-sensitive requests go to **A**, while B receives replicated copies on standby. If A suffers an outage, operations actively switch the app profile to B after assessing **replication lag and stale-read risk**. This mode supports single-row transactions on the primary cluster, though it does not automatically yield zero RPO.

### 6.2. Active–Active: Prioritizing Availability and Latency

~~~mermaid
flowchart LR
    APP_A["Region A app"] --> PA["HA app profile"]
    APP_B["Region B app"] --> PA
    PA --> A["Cluster A"]
    PA --> B["Cluster B"]
    A <-->|"Replication"| B
~~~

Multi-cluster routing directs applications to an appropriate cluster and **automatically shifts to another cluster** if one becomes unavailable. This is a strong fit for event data and read-heavy workloads tolerating eventual consistency. If **the region hosting the application** itself goes down, simply having a second Bigtable cluster in another region **is not enough**: you must deploy applications/clients in at least one other location with traffic steering, health checks, quotas, and IAM.

### 6.3. Quick Selection Table

| Need | First configuration to evaluate | Trade-off |
| --- | --- | --- |
| API must always read back just-written values, single source of truth. | Single-cluster, aligning all related app profiles to the same cluster. | Manual failover and higher latency for distant clients. |
| Multi-region telemetry where a few seconds of staleness is acceptable. | Multi-cluster any. | Eventual consistency, replication cost. |
| Want standby redundancy without uncontrolled automatic failover. | Single-cluster + standby replication. | Requires runbooks, monitoring, and explicit switchover decisions. |
| Analytics workload must not consume online cluster CPU. | Multi-cluster cluster-group or dedicated single-cluster. | Manage load, placement, cost; no automatic consistency boost. |
| Mostly single-row operations wanting fewer stale reads with auto HA. | Multi-cluster + row-affinity. | No read-your-writes guarantee when routing shifts. |
| Globally accurate counters with concurrent multi-region updates. | Single-writer ownership or an appropriate transactional DB. | Do not use multi-cluster Bigtable RMW on the same cell. |

## 7. Hands-On `gcloud`: Creating and Inspecting App Profiles

Example commands use **Bash** and assume an instance already has **two existing clusters**. Replace IDs with your lab project's resources. `create/update` commands **write configuration and can affect live traffic**; never run them in production without change approval. App profiles **do not create replication**: having multiple clusters requires configuring instance clusters separately per official docs.

### 7.1. Read-Only Preflight

~~~bash
PROJECT_ID="retail-lab"
INSTANCE="events-bt"
CLUSTER_A="events-a"
CLUSTER_B="events-b"

# READ-ONLY: confirm active principal and project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: verify instance, clusters, and app profiles.
gcloud bigtable instances describe "$INSTANCE" --project="$PROJECT_ID"
gcloud bigtable clusters list --instances="$INSTANCE" --project="$PROJECT_ID"
gcloud bigtable app-profiles list --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

Check each cluster's zone/region, CPU/capacity, inter-site latency, and existing profiles. Never guess a cluster ID solely from a region name, because clusters have admin-assigned IDs.

### 7.2. Creating Profiles for Each Scenario

~~~bash
# WRITE: single-cluster for workloads requiring read-your-writes.
gcloud bigtable app-profiles create orders-consistent \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-to="$CLUSTER_A" \
  --description="Read/write on cluster A"

# WRITE: automatic HA, can route to any cluster in the instance.
gcloud bigtable app-profiles create telemetry-ha \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-any \
  --description="Automatic failover; eventual consistency"

# WRITE: restrict to A/B, enable row-affinity for single-row operations.
gcloud bigtable app-profiles create telemetry-sticky \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-any \
  --restrict-to="$CLUSTER_A,$CLUSTER_B" \
  --row-affinity \
  --description="Single-row routing with affinity"

# READ-ONLY: verify actual routing policy.
gcloud bigtable app-profiles describe telemetry-sticky \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

**Enabling transactional writes** applies strictly to single-cluster profiles when business logic requires `ReadModifyWriteRow` or `CheckAndMutateRow`, e.g., creating a profile with `--route-to="$CLUSTER_A" --transactional-writes`. Never combine `--transactional-writes` with `--route-any` or `--row-affinity`, and verify no other profiles write the same row on cluster B. Note that `orders-consistent` in the example **does not enable** transactional writes yet.

### 7.3. Java Client Specifying an App Profile

Example using `com.google.cloud:google-cloud-bigtable` with **Application Default Credentials (ADC)** and no embedded JSON keys. Code reading a row via the Bigtable Java API:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;

public class ReadEvent {
    public static void main(String[] args) throws Exception {
        BigtableDataSettings settings = BigtableDataSettings.newBuilder()
                .setProjectId("retail-lab")
                .setInstanceId("events-bt")
                .setAppProfileId("telemetry-ha")
                .build();

        try (BigtableDataClient client = BigtableDataClient.create(settings)) {
            Row row = client.readRow("events", "device#001#20261119");
            System.out.println(row == null ? "Not found" : "Found");
        }
    }
}
~~~

This assumes the table/row exists and the identity has read permissions. In **production Cloud Run/GKE**, create **one shared `BigtableDataClient` per process lifecycle** instead of creating one per HTTP request; call `close()` on shutdown and configure appropriate deadlines/retries. Switching from `telemetry-ha` to `orders-consistent` changes routing/consistency behavior **even when SQL/row keys stay identical**.

## 8. Controlled Failover and Failback

### 8.1. Automatic or Manual?

- **Multi-cluster routing:** Bigtable can automatically switch clusters when the closest cluster is unavailable. Failover speed depends on **request deadlines** and cluster health; zero errors across all requests are not guaranteed.
- **Single-cluster routing:** **does not switch clusters automatically**; operators must update `route-to` when deciding to fail over.
- Both modes can incur **stale reads** right after switching clusters if replication has not caught up. If the source continues accepting writes during a split/failover, data conflicts must be handled carefully.

### 8.2. Manual Failover Runbook

1. **Assess the incident:** compare 5xx/timeouts, latency, CPU/hottest node, networking, and cluster A status. Do not assume every p99 spike warrants switching clusters.
2. **Assess data:** check replication latency/max delay and staleness risk on cluster B; confirm whether the business tolerates the temporary RPO.
3. **Verify target capacity:** cluster B must handle both redirected traffic and background replication.
4. **Decide on writes:** for transactional/conditional mutations, stop or tightly control writes on A to avoid conflicting writes across both clusters.
5. **Switch profile inside a change window:**

   ~~~bash
   # WRITE: run ONLY after failover approval and confirming cluster B is healthy.
   gcloud bigtable app-profiles update orders-consistent \
     --instance="$INSTANCE" --project="$PROJECT_ID" \
     --route-to="$CLUSTER_B"
   ~~~

6. **Verify:** inspect the app profile, application success rate, p95/p99, errors, data freshness, automatic failovers (if other profiles exist), latency, and cost.
7. **Planned failback:** once A recovers, verify replication has caught up, consider consistency tokens/canaries, and only then route the profile back to A; avoid rapid routing ping-pong.

`--force` bypasses important CLI safety warnings; **never pass it by default**. For multi-cluster profiles, automatic failover is never a reason to turn off monitoring. Read [Manage failovers](https://cloud.google.com/bigtable/docs/managing-failovers).

## 9. Verifying Replication Catch-Up

### 9.1. Using Consistency Tokens for Checkpoint Guarantees

If a batch of writes must replicate to every cluster before downstream analytics or a backup runs:

1. Send and confirm the batch writes to Bigtable.
2. Call **`GenerateConsistencyToken`** for the **table** after the batch.
3. Poll **`CheckConsistency`** with the token and appropriate mode (e.g., `StandardReadRemoteWrites`).
4. If `consistent=false`, wait/retry with timeout and backoff; proceed only once satisfied or fail clearly.

The token verifies that **writes completed before token creation** have met replication conditions; **it makes no claim about writes sent afterward**. The first check may take time to confirm across all clusters. This is a **batch/table-level barrier mechanism**—do not generate/poll a new token for **every HTTP request** just to replace read-your-writes routing. See [GenerateConsistencyToken](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/generateConsistencyToken) and [CheckConsistency](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/checkConsistency).

### 9.2. Replication and Backups

A table backup taken in one cluster reflects that cluster's data at snapshot time and may **omit writes from another cluster that had not replicated yet**. To back up consistently after critical batch writes, use consistency tokens/conditions supported by Bigtable docs and practice restores. Replication **does not replace backups for accidental table deletion, application bugs, or misconfigured garbage collection**. See [Bigtable backups](https://cloud.google.com/bigtable/docs/backups).

## 10. Monitoring: Measuring Consistency, Latency, and Failover

### 10.1. Signals to Inspect Together

| Signal in Bigtable/Cloud Monitoring | What does it show? | When to pay attention? |
| --- | --- | --- |
| `bigtable.googleapis.com/table/replication/latency` | Distribution of **replication latency** between source and destination, in ms. | Rising p50/p95/p99, especially before failover or backups. |
| `bigtable.googleapis.com/table/replication/max_delay` | **Upper bound** on replication delay per the provided metric, in seconds. | Assessing windows where consistency/latency info may be incomplete. |
| Read/write latency by cluster/app profile | Server-side request latency at Bigtable. | Spotting distant regions, heavy scans, load imbalance. |
| CPU utilization, **hottest node CPU** | Cluster/tablet capacity and hotspots. | Certain row-key ranges running hot despite low average CPU. |
| Automatic failovers | Requests automatically rerouted by Bigtable across clusters. | Understanding routing shifts and p99 variance on multi-cluster. |
| System error rate, timeouts, request counts | Whether the service is processing steadily. | Diagnosing network/capacity issues before altering app profiles. |
| Client-side p95/p99, retries, Google Cloud audit logs | User experience and who changed routing. | Investigating incidents, misconfigurations, or rollouts. |

**Key distinction:** `replication/latency` measures **the latency of replicated mutations**, not a guarantee that "every row in the table is at most p95 old." Similarly, `replication/max_delay` is not a fixed numeric RPO SLA at all times. Monitoring metrics involve sampling/reporting lag; evaluate over sufficiently wide windows. Docs: [Bigtable metrics](https://cloud.google.com/bigtable/docs/metrics), [Monitor Bigtable](https://cloud.google.com/bigtable/docs/monitoring-instance).

### 10.2. Alert on SLOs, Not One Threshold for Every Table

Illustrative hypothetical policy for a telemetry app:

~~~text
SLO: 99.9% reads succeed, p99 < 200 ms.
Reporting consistency budget: tolerate up to 30 seconds of staleness.

Warning:
  replication p99 elevated for several minutes, read p99 exceeds target.
Incident:
  replication delay keeps climbing + client errors rising / cluster unstable.
Failover readiness:
  measure replication lag, CPU headroom, capacity, and client placement.
~~~

These numbers are illustrative only, **not Bigtable limits or SLAs**. For order state or counters requiring immediate accuracy, avoid assuming "30 seconds is fine" without a business decision. Read/write SLOs must be measured end-to-end with **the application**, since clients in an affected region may fail to reach Bigtable even when another cluster is healthy.

## 11. Load, IAM, Networking, and Cost

### 11.1. Capacity Allocation Per Cluster

When Bigtable has multiple clusters:

- Each cluster requires **replica storage**, node/compute capacity, and CPU for **background replication**.
- **Write throughput does not multiply by cluster count**; writes hitting one cluster must still replicate to all others.
- During failover, the target cluster absorbs extra **client traffic** while replication and system overhead continue consuming resources.
- Multi-region routing can lower user-facing latency, yet incurs **inter-region replication/network transfer charges** per data path and pricing; adding a new cluster also incurs initial data copy costs.
- **Dropping row ranges** on replicated instances can be slow and CPU-intensive; avoid bulk drops near peak hours.

If a cluster already runs low on headroom before an outage, HA on paper may fail SLOs during failover. Load-test **N-1 capacity** (one cluster lost) and monitor node counts, storage, and autoscaling behavior under your edition/configuration.

### 11.2. Separating Identities and Permissions

| Principal | Needed actions | Principle |
| --- | --- | --- |
| Cloud Run runtime SA | Read/write rows via app profile. | `roles/bigtable.user` or least-privilege data role at appropriate scope; never Admin by default. |
| GKE workload SA | Process Bigtable events. | Workload Identity Federation for GKE and Data API permissions per workload. |
| SRE/DBA | Create/edit app profiles, clusters, failovers. | Separate admin permissions, approvals, and auditing; **never grant route-change rights** to every app runtime. |
| CI/deployer | Manage configs via IaC/releases. | Deploy/`iam.serviceAccounts.actAs` permissions as needed, separate from reading sensitive data. |
| Auditor | Inspect configs/metrics. | Monitoring/Bigtable Viewer on resources. |

**App profiles are a routing mechanism, not a data authorization boundary**. IAM/authorized views and application-level authorization must still be designed independently. For private workloads, verify **paths to Google APIs**, DNS, Private Google Access/PSC, and VPC Service Controls per topology; Bigtable is not a PostgreSQL server accessed over a single private DB IP.

### 11.3. Cost Should Be Calculated for the Full Architecture

~~~text
Estimated cost ≈
  compute/nodes of each Bigtable cluster
  + replica storage in each cluster
  + inter-zone/region network transfer/replication by path and volume
  + backups and initial copy when adding a cluster
  + Cloud Run/GKE client compute + logging/monitoring
~~~

Do not oversimplify to "Bigtable doubles in price" merely for having two clusters: compute, storage, transfer, backups, and regions each have distinct rates and scopes. Measure **cost per million events processed within SLO**, and check [Bigtable pricing](https://cloud.google.com/bigtable/pricing).

## 12. Case Study: Multi-Region Reads/Writes and Failover Scenario

### 12.1. Context

- `events-bt`: Bigtable instance with clusters A and B in two different regions.
- Cloud Run in A emits `product.viewed`; GKE in B aggregates clickstreams.
- The website needs near-realtime telemetry; the promotions app maintains a **critical state counter**.
- Telemetry SLO allows eventual consistency, whereas the business counter cannot tolerate lost increments.

**Design:**

| Stream | App profile | Explanation |
| --- | --- | --- |
| `product.viewed` ingestion & dashboard | `telemetry-ha`: multi-cluster any | Automatic HA, lower regional latency, stale reads acceptable. |
| Lookup of a just-written telemetry row | `telemetry-sticky`: multi-cluster row-affinity | Reduces stale reads, while still handling staleness during failover. |
| Promotion counter needing single-row read-modify-write | `orders-consistent`: single-cluster A, transactional writes enabled if needed | Never scatter conditional mutations across two clusters. |
| Reporting running strictly in B | Dedicated single-cluster B profile or appropriate cluster group | Isolates load/visibility, accepting incomplete replication per internal SLA. |

**Warning:** if the counter requires multi-row transactions or exact concurrent updates across both A and B, evaluate Spanner/Cloud SQL or a proper aggregate/writer-ownership design; never rely on replication to merge increments automatically.

### 12.2. A Hypothetical Outage

When region A experiences an outage:

1. `telemetry-ha` automatically shifts traffic to B; some reads may briefly observe stale data.
2. `orders-consistent` still points to A and **fails/times out**, because single-cluster does not auto fail over.
3. SRE inspects replication lag and conflict risk, then decides to switch the transactional profile to B per runbook criteria.
4. App team ensures client A has fallback endpoints/compute; dashboards continue tracking p99, errors, and replication delay.
5. When A recovers, **do not** immediately push all writes back to A until data consistency is verified and dual-writer contention is eliminated.

**Lesson:** Automatic HA for telemetry and tight consistency for a transactional stream can **coexist on one instance via different app profiles**, creating distinct runbooks and RPOs. Never confuse "readable from B" with "zero risk of missing latest writes" after an outage.

## 13. Troubleshooting: Looking at the Right Layer

| Symptom | Possible cause | What to check first |
| --- | --- | --- |
| Write on A succeeds, read on B sees old value | Asynchronous replication has not caught up. | App profile routing, replication latency/max delay, read path. |
| Read after write in same app is occasionally stale | Multi-cluster profile, row-affinity inapplicable, or failover occurred. | Request type, app profile, routing, and automatic failover metrics. |
| `CheckAndMutateRow` rejected | Multi-cluster profile or transactional writes not enabled. | `route-to`/`transactional-writes`; never enable blindly across multiple clusters. |
| Counter drops increments | Conflicting conditional/RMW writes across clusters. | Writer ownership, multiple profiles, transaction safety. |
| High latency only in region B | Distant network path, hot CPU on B, hotspot, or heavy replication load. | Client/server latency, hottest node CPU, read/write QPS. |
| Adding clusters does not raise write throughput | Every cluster still has to replicate writes. | Replication CPU, node count, client QPS. |
| Automatic failover does not occur | Single-cluster profile or cluster group lacks a healthy target. | Routing policy, allowed clusters, system errors. |
| Stale reads right after automatic failover | New cluster has not received all source writes yet. | Replication lag, traffic direction, freshness SLO. |
| SQL query over row-affinity hits another cluster | Row-affinity **does not apply to `ExecuteQuery`**. | API method, routing docs, app profile. |
| Sticky routing shifts after adding a cluster | Row-key-to-cluster assignment changed. | Cluster membership; use `--restrict-to` when needed. |
| Cannot update app profile | Lacks admin permissions or policy conflict warning. | IAM, CLI warnings, approval; do not blindly add `--force`. |
| Post-failover backup misses very recent writes | Backup cluster replica lacked unreplicated writes. | Consistency token, backup timing, restore drills. |

**Short workflow:** confirm project/instance/cluster/app profile → trace read/write paths → verify freshness and transaction types → inspect replication/server/client metrics → check failover, IAM/capacity → validate via canary/consistency token where appropriate → alter routing only after approval.

## 14. Exercises

### Exercise 1 — Eventual Consistency

A row is written on A and read from B 20 ms later, still showing the old value. Is this definitely a replication failure? Which metrics should you inspect before declaring an incident?

### Exercise 2 — Choosing App Profiles

Select profiles for: (a) a telemetry dashboard tolerating staleness; (b) an API always reading back its writes immediately on the same cluster; (c) reporting scans confined to cluster B; (d) a single-row counter using check-and-mutate. State routing type and failover policy.

### Exercise 3 — Why Adding a Cluster Does Not Multiply Write Throughput

A single-cluster instance has 4 nodes; after adding a second cluster, writes/sec did not double as expected. Explain replication CPU cost and how to measure where the bottleneck lies.

### Exercise 4 — Row-Affinity and SQL

A `--route-any --row-affinity` profile is used with SQL `ExecuteQuery` filtering `WHERE row_key = ...`, yet read-your-writes remains inconsistent. Why? If you switch to `ReadRows` with a single exact row key, is read-your-writes guaranteed unconditionally?

### Exercise 5 — Single-Row Transactions

Two regions concurrently increment `sold=5` via read-modify-write. Each produces `6`. Why cannot replication deduce `7` from those two writes? Which configuration does Bigtable prohibit, and what safer design would you use?

### Exercise 6 — Manual Failover

Cluster A fails while `orders-consistent` points to A; cluster B is lagging. Write a failover decision checklist, the required `gcloud` change, and post-change verification steps. Why can you not claim RPO = 0?

### Exercise 7 — The Default Profile

An instance starts with one cluster, and cluster B is added later. Does `default` automatically switch to multi-cluster routing? How does an instance initially created with two clusters behave differently? How do you avoid depending on this historical difference?

### Exercise 8 — Consistency Tokens and Backups

You need to take a backup after a batch of writes on A and ensure B has received all writes up to that point. Describe the sequence for generating/checking a consistency token, handling timeouts, and why the token does not cover writes arriving **after** token generation.

### Exercise 9 — Architecture and Cost

Design an IoT system with 100,000 devices sending events across two regions, needing low read latency and a standby replica. Specify routing, freshness SLO, metrics, N-1 failover capacity, and cost items to budget. If multi-row payment transactions are added, should they go into Bigtable?

## 15. Production Checklist and Official Documentation

| Item | Verification criterion |
| --- | --- |
| **Replication** | Right number of clusters/regions, per-cluster capacity, and inter-cluster latency monitored. |
| **Consistency** | Each read/write stream explicitly defines eventual, read-your-writes, or strong requirements. |
| **Routing** | Workload-named profiles; never rely unintentionally on `default`. |
| **Transactions** | Single-row transactional writes only on single-cluster profiles; no cross-cluster conflicting writes. |
| **Row-affinity** | Used only for single-row operations; never treated as a strict guarantee or applied to SQL. |
| **Failover** | Clear distinction between auto-failover and manual-runbook profiles; failback rehearsed. |
| **Monitoring** | Replication p95/p99/max delay, CPU/hottest node, auto failovers, errors, latency tracked. |
| **Backups** | Backup/restore drills performed, accounting for replication lag and consistency tokens when needed. |
| **IAM/networking** | Least-privilege runtime SA, separate routing admin rights, valid Google APIs egress. |
| **SLO/cost** | Realistic RTO/RPO/freshness; N-1 capacity, storage, transfer, and client costs measured. |

Official reference sources:

- [Bigtable — Replication overview](https://cloud.google.com/bigtable/docs/replication-overview)
- [Bigtable — Routing options](https://cloud.google.com/bigtable/docs/routing)
- [Bigtable — App profiles overview](https://cloud.google.com/bigtable/docs/app-profiles)
- [Bigtable — Configure app profiles](https://cloud.google.com/bigtable/docs/configuring-app-profiles)
- [Bigtable — Replication settings examples](https://cloud.google.com/bigtable/docs/replication-settings)
- [Bigtable — Replication and performance](https://cloud.google.com/bigtable/docs/replication-performance)
- [Bigtable — Writes and conflict resolution](https://cloud.google.com/bigtable/docs/writes)
- [Bigtable — Failovers](https://cloud.google.com/bigtable/docs/failovers)
- [Bigtable — Manage failovers](https://cloud.google.com/bigtable/docs/managing-failovers)
- [Bigtable — Metrics and monitoring](https://cloud.google.com/bigtable/docs/metrics)
- [Bigtable — Consistency token API](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/generateConsistencyToken)
- [Bigtable — Backups](https://cloud.google.com/bigtable/docs/backups)
- [Bigtable Java client settings](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.BigtableDataSettings)
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing)

**Key takeaway:** Bigtable replication maintains multiple replicas and improves failover capability, but **replicates asynchronously**, meaning reads from another cluster can observe stale data. **App profiles** determine consistency and failover: single-cluster prioritizes read-your-writes and enables single-row transactions, whereas multi-cluster prioritizes automatic cluster failover and accepts eventual consistency. Row-affinity only **reduces the probability** of stale reads for single-row operations. Sound operations mean matching routing to business requirements, controlling conflicting writes, measuring replication lag, rehearsing failovers, and budgeting full per-cluster costs.
