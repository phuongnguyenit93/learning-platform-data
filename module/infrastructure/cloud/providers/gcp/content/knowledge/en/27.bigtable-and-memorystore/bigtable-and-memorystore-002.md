# Bigtable Instances, Clusters, and App Profiles

> **Chapter:** Bigtable and Memorystore  
> **Module:** CLOUD_PROVIDERS_GCP

An IoT platform ingests hundreds of thousands of sensor events per second. An API needs to read the latest value per device with low latency; an analytics job scans historical data; and the system must continue serving when a zone experiences an outage. **Google Cloud Bigtable** fits large-scale wide-column data accessed by row key and row-key ranges. However, deploying Bigtable does not stop at creating a table: you must understand **instances**, **clusters**, and **app profiles** to allocate capacity and control how every request is routed.

In the **CLOUD_PROVIDERS_GCP** module, this lesson connects concepts across projects/IAM, deployment zones, Cloud Run/GKE, databases, reliability, and cost. The focus is configuring Bigtable capacity; **Memorystore** is referenced in comparisons to avoid treating a cache as a durable data store. Examples use Bigtable **Enterprise edition** in a lab project; features dependent on **Enterprise Plus** are explicitly noted.

**After this lesson, you will be able to:**

1. Distinguish between an instance (data scope), cluster (zonal compute capacity), node (compute), and app profile (routing path and workload settings).
2. Explain why adding a cluster does **not** create a new table, but creates a data replica and replication work.
3. Choose **single-cluster** or **multi-cluster routing**, and reason about consistency, failover, and single-row transactions.
4. Design separate app profiles for online APIs, batch analytics, and workloads requiring read-your-writes.
5. Create/inspect instances, clusters, and app profiles with `gcloud`; select an app profile in a Java client.
6. Configure autoscaling, request priorities, Data Boost, and alerts for CPU/storage/replication.
7. Plan costs, IAM, backups, and failover, and validate SLO compliance through a lab exercise.

## 1. Component Diagram: Data Belongs to the Instance, Resources Belong to the Cluster

~~~mermaid
flowchart TB
  AP["Application: realtime API"] -->|"app profile: api-ha"| ROUTER["Bigtable app profile\nmulti-cluster routing"]
  ETL["Application: batch history"] -->|"app profile: batch-asia"| FIX["App profile\nsingle-cluster routing"]
  ROUTER --> A["Cluster events-asia\nZone asia-southeast1-b"]
  ROUTER --> B["Cluster events-dr\nZone asia-southeast1-c"]
  FIX --> A
  subgraph INST["Instance: bt-events-lab"]
    DATA["Tables: telemetry, device_metadata\nRow keys, column families, cells"]
    A <-->|"Replication, eventual consistency"| B
  end
  DATA -. "Data belongs to instance;\neach cluster holds a replica" .-> A
  DATA -.-> B
  A --> N1["Nodes / autoscaling"]
  B --> N2["Nodes / autoscaling"]
~~~

The diagram illustrates two clusters in the same region across different zones. To withstand a **full-region outage**, you need a cluster in **another region** along with separate networking/latency/residency planning; two zones within one region do not replace regional DR.

| Object | Scope | Characteristics | Example |
| --- | --- | --- | --- |
| **Project** | Google Cloud | IAM, billing, API enablement | `LAB_PROJECT_ID` |
| **Bigtable instance** | Data container | Holds tables, clusters, app profiles; has edition/storage type | `bt-events-lab` |
| **Table** | Inside an instance | Row key, column families, cells/versions | `telemetry` |
| **Cluster** | Belongs to an instance, in **one zone** | Serves reads/writes and replication, has node count and storage | `events-asia` |
| **Node** | Inside a cluster | Compute/read/write capacity, management/compaction | 3 nodes (illustrative) |
| **App profile** | Belongs to an instance | Routing, request priority, compute/isolation; selected by client | `api-ha` |
| **Bigtable client** | Inside the app | Sends RPCs with project, instance, and app profile ID | Java Cloud Run |

**Foundational rule:** Tables belong to the **instance**, not to an individual cluster. When there are multiple clusters, **every cluster stores a replica of every table in the instance**; you cannot use cluster A solely to hold table X and cluster B solely to hold table Y. <https://docs.cloud.google.com/bigtable/docs/instances-clusters-nodes>

### 1.1. Do Not Confuse Bigtable with Memorystore

| Need | Bigtable | Memorystore (Redis/Valkey) |
| --- | --- | --- |
| Large-volume, long-lived data | Good fit | Not the primary choice for storing all historical data |
| Row-key lookup, organized key-range scans | Core strength | Primarily key-value/in-memory data structures |
| Hot-key cache, sessions, short-lived rate-limit state | Can serve, but less optimal than a dedicated cache | Usually a better fit |
| Replication/HA | Multiple clusters via app profiles | Depends on product, tier/topology |
| Multi-table SQL transactions and JOINs | Not the primary model | Not a SQL database |

Do not choose Bigtable for a small CRUD app just because you need high availability; evaluate Firestore, Cloud SQL/AlloyDB, or a cache based on access patterns and total cost.

## 2. Instance: Administrative Scope and Hard-to-Change Decisions

An instance defines the **scope of tables, app profiles, and clusters**. The instance ID is the stable identifier used by clients. An instance can have one or more clusters in permitted locations. Several initial decisions have long-term impact:

| Decision | Considerations |
| --- | --- |
| **Edition** | Enterprise / Enterprise Plus, features, corresponding SLA/pricing; edition changes follow policy rules |
| **Storage type** | SSD vs. HDD, workload latency/throughput and pricing; **cannot switch SSD ↔ HDD on an existing instance** |
| **Cluster locations** | Latency to applications, failure domains, data residency, egress |
| **Node/autoscaling policy** | Peak capacity, headroom for replication/failover, cost |
| **Table/GC policy** | Retention per column family; applies uniformly across clusters |
| **CMEK when needed** | Encryption key, location, KMS permissions, and recoverability |

Bigtable has no concept of "each cluster having an independent set of tables within the same instance." If you need true **data isolation** between production and sandbox, consider **separate instances/projects** rather than merely separating app profiles.

### 2.1. Editions and Storage

- **Enterprise** fits most traditional Bigtable workloads.
- **Enterprise Plus** extends certain features/capabilities, such as the **in-memory tier** which was in **Preview** at the time of documentation review. Do not make Preview features a production requirement by default.
- **SSD** is generally suited for low latency and read/write-heavy workloads. **HDD** offers cost/throughput trade-offs and is not optimal for all random reads.
- An instance uses the same storage type across all clusters; **the storage type is chosen at creation time and cannot be changed**.

Verify edition, quotas, supported regions, and the pricing calculator before creating billable clusters.

## 3. Clusters, Nodes, and Serving Capacity

A cluster is where Bigtable serves requests. Each cluster resides in **one zone** and has at least one node; capacity depends on node count, I/O, row-key distribution, storage, row sizes, read/write ratio, and replication work.

**Adding a node does not add a second copy of the data:** nodes expand processing and serving capacity **within one cluster**. **Adding a cluster** gives the instance an additional data replica and an additional failure domain.

| Action | Impact level |
| --- | --- |
| Increase node count to absorb QPS | Cluster |
| Change autoscaling min/max | Cluster |
| Add a cluster in another zone | Instance + replication, affects all tables |
| Create a table/column family | Instance; synchronized to all clusters |
| Change app profile `route-to` | App profile; changes request path for apps using that profile |
| Change row-key schema | Table + application; not solved merely by adding clusters |

### 3.1. One Cluster Does Not Mean One "Data Storage Machine"

Bigtable stores data on a distributed storage layer, while nodes serve requests and perform maintenance work. When a cluster lacks compute, latency/CPU, system errors, or slow scans can increase. Adding clusters to "increase write throughput" **does not guarantee** higher total write throughput: every write to one cluster must be **replicated to the remaining clusters**, creating extra work. <https://docs.cloud.google.com/bigtable/docs/replication-performance>

### 3.2. Sizing Before Choosing Nodes

| Workload metric | Impact |
| --- | --- |
| Read/write requests per second and bytes/s | Compute/network |
| P95/P99 read latency | Sizing, hot tablets, row-key distribution |
| Batch scans and bulk imports | Resource contention with online APIs |
| Total compressed storage | Storage capacity and node budget for **each** cluster |
| Replication input/output | CPU, network, freshness with multiple clusters |
| Number of regions and where data is allowed to reside | Compliance, latency, and egress |
| Failover peak QPS | Surviving clusters must absorb additional traffic |
| Garbage collection/change streams | Background CPU/storage cost |

Do not copy a node count from a demo into production. Use realistic load benchmarks along with **Monitoring/Key Visualizer**.

## 4. App Profiles as the Client's "Routing Contract"

An **application profile** is a resource within an instance. When connecting, the application provides an **app profile ID**, which Bigtable uses to determine cluster routing and workload attributes. An app profile is **not a Kubernetes profile**, **not a JDBC connection pool**, and **does not create an IAM security boundary**.

### 4.1. Standard App Profile

A standard app profile can specify:

- **Single-cluster routing:** sends requests exclusively to a designated cluster.
- **Multi-cluster routing:** selects an available cluster close to the client; supports automatic failover within the cluster set.
- **Cluster group routing:** restricts routing to a subset of clusters.
- **Row-affinity routing:** attempts to route single-row operations for a given row key to the same cluster.
- **Request priority:** `PRIORITY_HIGH`, `PRIORITY_MEDIUM`, or `PRIORITY_LOW`.
- **Single-row transactions:** permitted only with **single-cluster routing**, when read-modify-write/check-and-mutate is genuinely needed.

**Mandatory contract:** If an app needs to increment counters via `ReadModifyWriteRow` or perform conditional updates via `CheckAndMutateRow`, choose a **single-cluster app profile** and enable transactional writes. Using multi-cluster routing for these operations can cause conflicts/data loss; Bigtable does not allow enabling transactional writes on a multi-cluster profile.

### 4.2. The Default Profile and Custom Profiles

Bigtable creates the **`default`** app profile when an instance is created:

- If the instance initially has **one** cluster: `default` uses **single-cluster** routing with single-row transactions enabled.
- If the instance initially has **two or more clusters**: `default` uses multi-cluster routing without single-row transactions.
- **Adding or removing clusters later does not automatically change the routing policy of `default`.**

If a client does not specify a profile ID, it uses `default`. Therefore, do not assume "because we added a second cluster, the app will automatically fail over": inspect the profile actually in use. **Creating custom app profiles and passing explicit IDs** per workload makes behavior easier to observe and change safely. <https://docs.cloud.google.com/bigtable/docs/app-profiles>

### 4.3. Matrix of Routing Types

| Type | Consistency | Failover | Single-row transaction? | Example |
| --- | --- | --- | --- | --- |
| **Single cluster** | Read-your-writes within the same cluster; requires no conflicting writes on other clusters | **Manual** | **Yes**, when enabled | Counters/conditional writes |
| **Multi cluster / any** | **Eventual** across clusters | **Automatic** | **No** | Multi-zone read APIs |
| **Multi / group** | Eventual | Auto within cluster group | No | Isolating dedicated clusters |
| **Multi + row affinity** | Increases likelihood of read-your-writes for **single-row requests**, no guarantee | Auto; may switch clusters | No | Hot device state by row key |
| **Data Boost** | Read-only analytical jobs, product-specific snapshot/consistency semantics | Single cluster | Not for transactional writes | Historical scans |

Row-affinity **does not guarantee strong consistency**: failover, overload, or changes in cluster membership can shift a row key to another cluster. Do not rely on it to guarantee correctness for monetary or order transactions.

### 4.4. Creating an App Profile Does Not Grant Permissions

Google Cloud IAM controls who can read/write Bigtable tables; profiles primarily control routing, isolation, and telemetry. For a read-only client, use `roles/bigtable.reader` or appropriate permissions on a table/authorized view; writing data requires `roles/bigtable.user` or custom permissions. **Do not treat a LOW-priority app profile as a data protection layer.**

## 5. Replication and Consistency

With a single cluster, Bigtable provides strong consistency for operations against that cluster. With multiple clusters, Bigtable replicates data **asynchronously** across clusters. **Every cluster is primary** for reads and writes; there is no default read-only cluster.

~~~mermaid
sequenceDiagram
    participant A as API write via cluster A
    participant BA as Bigtable cluster A
    participant BB as Bigtable cluster B
    participant R as Reader via cluster B
    A->>BA: MutateRow(device-42, value=18)
    BA-->>A: Write OK
    R->>BB: Read device-42 immediately
    BB-->>R: May see stale value
    BA-->>BB: Async replication
    R->>BB: Read after sync
    BB-->>R: Sees new value
~~~

**Key takeaway:** A successful write at A **does not prove B has received the data**. Replication latency has no hard time bound like "just sleep 1 second"; it can increase during cluster overload, cross-region links, or network issues. <https://docs.cloud.google.com/bigtable/docs/replication-overview>

### 5.1. Read-Your-Writes and Single-Cluster Routing

If both reads and writes for a workload go to the **same cluster** through a single-cluster app profile, the workload can preserve read-your-writes. If **all** applications use the same cluster and produce no concurrent writes on other clusters, some multi-cluster instance designs can still provide strong consistency for that workload. However, during manual failover to cluster B while replication is incomplete, reads can be **stale**.

### 5.2. Multi-Cluster Write Conflicts

Bigtable identifies each cell by `row key / column family / column qualifier / timestamp`. When two clusters write the same cell with the exact same timestamp, Bigtable uses an **internal last-write-wins** conflict resolution mechanism. Transactional operations (read-modify-write, conditional writes) executed **independently** on two clusters can break business semantics.

For example, a counter increments from 7 to 8 on A and also increments from 7 to 8 on B. Replication does not automatically infer the intent "increment twice to get 9." Where suitable for the data type, consider **aggregate cells/AddToCell** per supported capabilities for explicit merge semantics; otherwise, route all transactional writes for the same row to **one** cluster.

### 5.3. Choosing Consistency Based on Requirements

| Requirement | Preferred design | Trade-off |
| --- | --- | --- |
| Latest device value must be immediately visible after write in one region | Single-cluster profile | No automatic failover |
| Read replicated data near customers, tolerating a few seconds of lag | Multi-cluster routing | Eventual consistency |
| Automatic HA failover when a cluster fails | Multi-cluster (any/group) | Possible stale reads after failover |
| Increments and conditional writes | Single-cluster + transactional writes | Avoid conflicting writes across multiple clusters |
| Batch analytics without causing CPU spikes on online APIs | Data Boost profile or dedicated cluster | Compute/storage cost and freshness constraints |

### 5.4. Failover Does Not Replace Backups

Replication maintains **multiple live copies of active data**, not immutable backups: logic bugs, table deletions, bad writes, or misconfigured GC policies can all be replicated. Use **Bigtable backup/restore**, retention policies, and separate recovery drills. Depending on configuration, regional replication may also carry residency/egress constraints that must be approved upfront.

## 6. Lab Topology and Preflight

Shared example parameters in this lesson:

| Field | Illustrative value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Bigtable instance | `bt-events-lab` |
| Edition / storage | `ENTERPRISE` / `ssd` |
| Cluster A | `events-asia`, zone `asia-southeast1-b` |
| Cluster B | `events-dr`, zone `asia-southeast1-c` |
| Table | `telemetry` |
| Online app profile | `api-ha` (multi-cluster) |
| Transaction app profile | `counter-single` (single-cluster A) |
| Batch app profile | `batch-asia` (single-cluster A, low priority) |

**Cost reminder:** Bigtable nodes and data in each cluster incur charges **even during testing**, and replication consumes resources and may incur network charges. Prefer an admin-provisioned lab environment; if studying theory only, use **simulated exercises** and do not spin up two billable clusters just to follow along.

**Prerequisites:** valid project/billing and Bigtable APIs enabled, up-to-date `gcloud`, `roles/bigtable.admin` or a custom role for administrative actions; runtime apps use narrower permissions. Check zonal quotas and edition/node-scale limits. Do not grant Project Owner/Editor to a service account that only reads data.

### 6.1. Read-Only Preflight Commands

~~~bash
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud bigtable instances list --project=LAB_PROJECT_ID

# If the lab instance already exists:
gcloud bigtable instances describe bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable clusters list \
  --instances=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles list \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

If the instance does not exist yet, commands referencing `bt-events-lab` may return `NOT_FOUND`; that indicates a missing lab resource, not a reason to create one in a production project.

## 7. Creating an Instance/Cluster — Approved Sandbox Only

### 7.1. Creating a Single-Cluster Instance (Billable)

~~~bash
# MODIFIES RESOURCES, INCURS CHARGES
# Run only if LAB project, quota, zone, and budget are approved.
gcloud bigtable instances create bt-events-lab \
  --display-name="Bigtable events lab" \
  --edition=ENTERPRISE \
  --cluster-storage-type=ssd \
  --cluster-config=id=events-asia,zone=asia-southeast1-b,nodes=3 \
  --project=LAB_PROJECT_ID
~~~

This example uses `--cluster-config`, recommended over deprecated cluster creation flags. The count **3 nodes is illustrative**, not a universal default/minimum across all editions. Check exact regions/quotas/pricing before running. If the instance ID already exists, **do not overwrite or delete it**.

### 7.2. Adding Cluster B to Enable Replication

~~~bash
# MODIFIES INSTANCE, incurs compute/storage and replication charges
gcloud bigtable clusters create events-dr \
  --instance=bt-events-lab \
  --zone=asia-southeast1-c \
  --num-nodes=3 \
  --project=LAB_PROJECT_ID
~~~

Adding cluster B replicates **all tables** from the instance to B. **It does not automatically switch the routing policy of the `default` profile** when the instance was originally created with one cluster. Wait for replication/health to stabilize before sending production traffic to B.

**Two clusters in two zones of the same region do not protect against a full-region outage.** For regional DR, select a second region per data governance rules and account for cost/latency.

### 7.3. Verifying After Changes

~~~bash
gcloud bigtable instances describe bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable clusters list \
  --instances=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

Inspect **Console → Bigtable → Instances → Clusters** to verify zone, node count, autoscaling, status, and storage. **Cluster READY does not guarantee zero replication lag or sufficient failover capacity.**

## 8. Creating Three Standard App Profiles for Three Workloads

### 8.1. Online API: Multi-Cluster and Auto Failover

~~~bash
# MODIFIES RESOURCE: create profile so online requests can route to A/B
gcloud bigtable app-profiles create api-ha \
  --instance=bt-events-lab \
  --route-any \
  --priority=PRIORITY_HIGH \
  --description="Online API; multi-cluster auto failover" \
  --project=LAB_PROJECT_ID
~~~

**Effect:** Requests can route to the cluster nearest the client and automatically fail over when that cluster is unavailable. **Trade-off:** consistency across clusters is eventual, and single-row transactional writes cannot be used on this profile.

To restrict failover strictly to A/B if a cluster C is added later:

~~~bash
# Example creating another profile; specify group eligible for auto failover
gcloud bigtable app-profiles create api-ab-only \
  --instance=bt-events-lab \
  --route-any \
  --restrict-to=events-asia,events-dr \
  --priority=PRIORITY_HIGH \
  --project=LAB_PROJECT_ID
~~~

With `--restrict-to`, adding a new cluster **does not automatically** include it in the routing group. This helps keep analytics/DR clusters isolated, though it can prevent apps from using a newly added cluster during an outage if operators forget to update the group.

### 8.2. Single-Row Transactions: Single-Cluster

~~~bash
# MODIFIES RESOURCE: allow CheckAndMutateRow / ReadModifyWriteRow
gcloud bigtable app-profiles create counter-single \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --transactional-writes \
  --priority=PRIORITY_HIGH \
  --project=LAB_PROJECT_ID
~~~

**Do not** add `--route-any`/`--restrict-to` to this command. If other writers still send conflicting transactional writes for the same row to cluster B, consistency can break even when profile A is configured properly.

### 8.3. Batch Analytics: Single-Cluster and Low Priority

~~~bash
# MODIFIES RESOURCE: route batch scans through A, reducing contention with high-priority API
gcloud bigtable app-profiles create batch-asia \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --priority=PRIORITY_LOW \
  --project=LAB_PROJECT_ID
~~~

Priority is a Bigtable **scheduler** hint within a cluster; it does **not** provide strict compute isolation and does not restrict read permissions. For large scans, consider **Data Boost** for stronger compute isolation.

### 8.4. Verifying Profiles

~~~bash
gcloud bigtable app-profiles list \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles describe api-ha \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles describe counter-single \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

Verify both the *actual routing policy* and that *the client selects the right profile ID*. A successful profile creation command does not guarantee the application has stopped using the `default` profile.

## 9. Java Client: Selecting the App Profile at Client Creation

The Google Cloud Bigtable Java Data Client retrieves credentials using **Application Default Credentials (ADC)**. Applications running on Cloud Run/GKE/Compute Engine should use a runtime service account with appropriate IAM rather than storing JSON keys in images/Git.

### 9.1. Reading a Row with a Specified Profile

Example using `com.google.cloud:google-cloud-bigtable`, assuming table `telemetry` exists with row key `device#0042#20261119T0900Z`:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;

public final class ReadTelemetry {
    public static void main(String[] args) throws Exception {
        String project = "LAB_PROJECT_ID";
        String instance = "bt-events-lab";
        String appProfile = "api-ha";

        BigtableDataSettings settings = BigtableDataSettings.newBuilder()
            .setProjectId(project)
            .setInstanceId(instance)
            .setAppProfileId(appProfile)
            .build();

        try (BigtableDataClient client = BigtableDataClient.create(settings)) {
            Row row = client.readRow(
                "telemetry", "device#0042#20261119T0900Z");
            if (row == null) {
                System.out.println("Row not found");
            } else {
                System.out.println("Row key: " + row.getKey().toStringUtf8());
            }
        }
    }
}
~~~

**Explanation:**

- `setProjectId` identifies the project containing the instance.
- `setInstanceId` identifies the **instance**, not a cluster ID.
- `setAppProfileId("api-ha")` routes requests according to the multi-cluster/HA policy created earlier.
- `client.readRow` returns data for **one row** or `null` if it does not exist.
- The example prints only the row key to avoid writing cell values/PII into logs.

This snippet is a minimal program illustrating the API; it requires dependencies/versions compatible with your JDK and a table containing real data. **Do not run this demo to prove immediate read-your-writes on `api-ha`**; a multi-cluster profile has eventual consistency.

### 9.2. Why Not Create BigtableDataClient Per Request?

Repeatedly creating clients/channels increases TLS/network setup, thread counts, and latency. On Cloud Run/GKE, create one reusable client tied to the process lifecycle and close it on shutdown. If two routing policies are required, create **separate** clients/settings for `api-ha` and `counter-single`, and dispatch each operation to the appropriate client.

**Do not** pass a cluster ID into `setInstanceId` to switch zones; routing is the responsibility of the app profile.

### 9.3. An Example of Choosing the Wrong Profile

Code snippet:

~~~java
BigtableDataSettings wrongSettings = BigtableDataSettings.newBuilder()
    .setProjectId("LAB_PROJECT_ID")
    .setInstanceId("bt-events-lab")
    .setAppProfileId("api-ha")
    .build();

// Do not use the api-ha configuration with read-modify-write/check-and-mutate
// while this profile uses multi-cluster routing.
~~~

You do not even need to inspect the mutate call: the bug is in the **routing decision**, not the mutation syntax. Switch to `counter-single` for transactional operations while ensuring no competing transactional writes hit another cluster.

## 10. Autoscaling and Capacity Planning

Bigtable supports **manual node allocation** or **autoscaling** per cluster. Autoscaling adjusts nodes based on CPU/storage targets, not solely on HTTP request counts.

| Parameter | Meaning | Warning |
| --- | --- | --- |
| `autoscaling-min-nodes` | Minimum nodes retained | Must be enough for baseline, replication, and storage |
| `autoscaling-max-nodes` | Scaling ceiling | Must provide enough headroom during traffic/failover spikes |
| `autoscaling-cpu-target` | Target CPU utilization, **10–80%** | Setting too high reduces headroom for spikes |
| `autoscaling-storage-target` | Target capacity in GiB/node | Depends on SSD/HDD and edition limits |
| `num-nodes` | Manual node count | Mutually exclusive with autoscaling mode |

The Bigtable autoscaler adds nodes quickly when CPU exceeds target, but **does not guarantee zero latency impact during failover** if a cluster receives a sudden surge of traffic. On Enterprise Plus, **2× node scaling** increments may require an even minimum node count; verify edition constraints before setting values. <https://docs.cloud.google.com/bigtable/docs/autoscaling>

### 10.1. Enabling Autoscaling on Cluster A

~~~bash
# MODIFIES cluster, affects cost/capacity.
# Run only in a lab project with an explicit budget.
gcloud bigtable clusters update events-asia \
  --instance=bt-events-lab \
  --autoscaling-min-nodes=2 \
  --autoscaling-max-nodes=8 \
  --autoscaling-cpu-target=60 \
  --project=LAB_PROJECT_ID
~~~

The 2–8 nodes and 60% CPU configuration is only illustrative for Enterprise; if your edition/zone/feature specifies different rules, use valid values per the CLI and documentation. Under high storage pressure, the autoscaler also keeps enough nodes; never drop min nodes to a point that risks exceeding storage hard limits.

### 10.2. Sizing for Failover Scenarios

Suppose:

| Cluster | Normal load | Provisioned capacity | When A goes down |
| --- | --- | --- | --- |
| A | 60% of total traffic | 6 nodes | 0 traffic |
| B | 40% of total traffic | 4 nodes | Receives an extra 60% traffic |
| B after failover | 100% | Needs higher capacity, workload-dependent | May need to scale up and see elevated p95 |

This is a **capacity planning problem**, not a simple "6 + 4 nodes = always handles 100%" formula: row-key distribution, read/write mix, replication overhead, and storage also determine throughput. For failovers requiring a very short RTO, **provision headroom upfront** rather than relying solely on the autoscaler to add nodes in time.

### 10.3. Replication Increases Both Compute and Storage

An instance with two clusters maintains **two copies of the data**. Each cluster must handle background replication/compaction in addition to application traffic. Therefore:

- Adding a cluster can improve **read latency/HA**, but increases storage and compute costs.
- Adding a cluster **does not automatically increase total write throughput**.
- Every cluster must have enough nodes to store and replicate data, even a cluster not targeted as primary by any app profile.
- Low **average CPU** does not rule out hotspots; inspect **hottest node** CPU and Key Visualizer.

## 11. Request Priority, Data Boost, and Workload Isolation

### 11.1. Request Priorities

A standard app profile has `PRIORITY_HIGH` / `PRIORITY_MEDIUM` / `PRIORITY_LOW` levels. On a cluster serving both API and batch workloads, you can prioritize API requests. Priority helps the scheduler differentiate work types; it is **not a hard rate limit, dedicated node pool, or IAM control**.

Example setting batch to low priority:

~~~bash
# MODIFIES profile, affects workloads currently using it
gcloud bigtable app-profiles update batch-asia \
  --instance=bt-events-lab \
  --priority=PRIORITY_LOW \
  --project=LAB_PROJECT_ID
~~~

Measure CPU, latency, and throughput before and after. If API and batch workloads still contend heavily, route batch to another cluster or use Data Boost.

### 11.2. Data Boost for Big Scans

**Data Boost** provides serverless compute for **high-throughput read jobs**, instead of using cluster nodes to serve large scans. It uses a **Data Boost app profile** with **single-cluster routing**, isolating analytical workloads from serving CPU. Do not use a Data Boost profile for transactional writes or standard online API read/write traffic.

~~~bash
# MODIFIES RESOURCE: create Data Boost app profile per edition support rules
gcloud bigtable app-profiles create history-boost \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --data-boost \
  --data-boost-compute-billing-owner=HOST_PAYS \
  --project=LAB_PROJECT_ID
~~~

**Verify feature availability, workload eligibility, and Data Boost pricing** before running. Data Boost has its own freshness/snapshot semantics and should not be used to check "just-written" values. This command only creates the profile; the client/job must **specify the profile ID** to actually use separate compute.

### 11.3. In-Memory Tier Differs from Memorystore

In certain **Enterprise Plus (Preview)** configurations, an app profile can use an **in-memory tier** to accelerate eligible point reads. This is a **Bigtable** feature, not Memorystore Redis/Valkey; it has different feature, routing, and cost constraints and is **single-cluster only**. Do not treat Preview features as mandatory prerequisites for labs or production.

## 12. Failover: Automatic and Manual

~~~mermaid
flowchart TD
  E["Cluster A fails"] --> PROFILE{"App profile type?"}
  PROFILE -- "multi-cluster"| AUTO["Bigtable can auto reroute\nto B in group"]
  PROFILE -- "single-cluster"| MAN["Operator evaluates lag/capacity\nthen updates profile route-to=B"]
  AUTO --> CHECK["Test request success, p95,\nreplication freshness, data correctness"]
  MAN --> CHECK
  CHECK --> Q{"Meets SLO/consistency?"}
  Q -- "No" --> FIX["Adjust capacity, route,\nblock risky writes, runbook"]
  Q -- "Yes" --> HOLD["Monitor and log incident"]
~~~

### 12.1. Multi-Cluster Automatic Failover

With `api-ha`, when a cluster cannot process requests, Bigtable can reroute to an available cluster according to policy. Failover speed **depends on request deadlines and current conditions**. Do not assume **zero errors/zero stale reads**; applications still need idempotent retries, timeouts, and monitoring.

### 12.2. Single-Cluster Manual Failover

With `batch-asia`, an operator can change `route-to` after verifying cluster B is healthy and serving sufficiently fresh data:

~~~bash
# CHANGES TRAFFIC PATH, execute only on lab app profile.
# Verify replication lag and data correctness first.
gcloud bigtable app-profiles update batch-asia \
  --instance=bt-events-lab \
  --route-to=events-dr \
  --project=LAB_PROJECT_ID
~~~

The routing update **does not copy data instantaneously**; it only shifts requests to the existing replica in B. It affects **all clients using `batch-asia`**. For profiles allowing single-row transactions, failover must also ensure no conflicting writes remain on the old cluster and handle unreplicated writes.

**Do not use `--force` to bypass consistency warnings just because an incident is urgent.** Your runbook must define acceptable staleness bounds, whether writes should be paused, and how to fail back.

### 12.3. Do Not Overlook Stale Reads

If replication lag is 40 seconds when A fails, a client immediately reading B can observe state **missing writes already acknowledged on A**. The application must decide:

- Is **eventual consistency** acceptable, such as for historical telemetry?
- Is immediate accuracy mandatory, such as for quotas or financial ordering?
- Should the app enter read-only/degraded mode until data is verified?
- When to fail back, and how to prevent dual-cluster conflicting writes?

## 13. Security and Operational Responsibilities

### 13.1. Google Cloud IAM Permissions

| Role | Typical permissions | Intended use |
| --- | --- | --- |
| `roles/bigtable.admin` | Manage instances, clusters, profiles, tables | Infrastructure team, only when needed |
| `roles/bigtable.user` | Read/write data within granted scope | Runtime ingestion/API |
| `roles/bigtable.reader` | Read-only data access | Reporting/sandbox readers |
| Custom roles/Authorized Views | Narrow permissions and data scope | Multi-app/multi-tenant isolation where appropriate |

Grant permissions at the narrowest supported resource scope; do not use `roles/editor` or long-lived service account JSON keys in Cloud Run/GKE. **App profiles do not restrict who can view table rows**; data access continues to be governed by IAM and dedicated protection mechanisms.

### 13.2. Networking and Data Residency

- Bigtable uses Google APIs endpoints (TLS); verify DNS/egress/firewalls and **Private Google Access/Private Service Connect** when private network architectures require them.
- Accessing Bigtable via API is not equivalent to a database running directly inside your subnet; instances/clusters have their own locations.
- With multi-region clusters, table data is replicated to those locations; evaluate **data residency** before adding clusters.
- **CMEK** can be used where supported, making KMS key/IAM/rotation management part of DR.
- Audit Logs, service account impersonation, and change approvals should track changes to app profile routing and cluster placement.

### 13.3. Data Protection Approach

Replication mitigates cluster/region outages appropriately, **but does not replace backups**. For accidental table deletion, application-level corruption, or bad GC rules, rely on Bigtable backups, retention, and restore drills. Also maintain a source of truth for IAM, profiles, autoscaling configs, and table/column family definitions.

**Do not** delete a production cluster or table just to "verify failover." Use lab resources, simulated route switches, or approved fault-injection environments.

## 14. Observability, Troubleshooting, and Cost

### 14.1. Key Metrics by Cluster and App Profile

| Metric | Operational question |
| --- | --- |
| CPU average / **hottest node** | Does the cluster have hotspots or uneven CPU distribution? |
| Node count and autoscaling recommendations | Is it hitting max nodes during traffic spikes? |
| Storage utilization (%/bytes) per cluster | Is there enough headroom to store/replicate data? |
| Read/write latency p95/p99 | Did SLOs improve after changing routing or sizing? |
| Rows read/written, read/write throughput | Which cluster is actually receiving the load? |
| System error rate | Are errors coming from Bigtable backend or client retries? |
| Replication latency **input/output** | How stale can cross-cluster reads become? |
| Automatic failover events | Are there unexpected routing shifts between clusters? |
| CPU/latency by **app profile** | How much capacity are API vs. batch profiles consuming? |
| Data Boost SPU-seconds (if used) | What is the cost/efficiency of batch compute? |

In **Bigtable → System insights**, inspect views by Instance, Tables, Application Profiles, and Replication; for hotspots, use **Key Visualizer**. Storage metrics can lag due to compression/compaction calculations; do not mistake a slight reporting delay for data loss.

### 14.2. Common Diagnostics

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `NOT_FOUND` for instance/table | Wrong project/instance/table ID or resource does not exist | `instances list`, table metadata, client settings |
| App errors on read-modify-write | Multi-cluster profile disallows single-row transactions | Switch to `counter-single`, check profile config |
| API returns stale data after write | Reading from another cluster before replication catches up | Routing, lag, same-cluster reads |
| Added cluster but app does not auto fail over | `default` is still single-cluster | Actual app profile used by the client |
| Latency spikes during failover | B lacks capacity or data is cold | Node headroom, autoscaling, p95/CPU |
| Resource exhausted errors | CPU/quota/storage exhaustion or hotspot | Metrics, Key Visualizer, quotas, and retries |
| Low average CPU, some slow requests | Hot row-key range | Hottest node/Key Visualizer, schema |
| Batch scan raises API p99 | Contending for the same cluster resources | LOW priority, Data Boost, or separate cluster |
| Storage does not drop right after GC | Compaction/metrics lag | Check GC policy, storage trend, do not delete blindly |
| `PERMISSION_DENIED` | Runtime SA lacks IAM | Bigtable role on exact resource, ADC |
| Profile changed but app behavior unchanged | Client still uses `default` or cached config | `setAppProfileId`, restart/client lifecycle |
| Cost rises after adding a cluster | Each cluster carries compute/storage copies | Per-cluster billing, replication/egress |

**Investigation workflow:** verify project/instance → actual app profile → routing/cluster health → IAM/network → CPU/hottest node/storage → replication lag → row-key access pattern → cost.

### 14.3. Cost Components to Budget For

Bigtable billing components depend on configuration and edition:

- **Cluster nodes** (or compute capacity by edition) over time.
- **Storage bytes** for each cluster replica.
- **Network/data transfer**, especially across multi-region clusters and distant clients.
- Backups/change streams, Data Boost SPUs, and advanced features if used.
- Cloud Monitoring/Logging and read/write workloads on Cloud Run/GKE/Dataflow.

Illustrative estimate: scaling an instance from 1 cluster of 3 nodes to **2 clusters of 3 nodes each** **doubles provisioned compute** before autoscaling optimization; storage also requires an extra replica. This is **not** an exact bill forecast, as edition, pricing, duration, and region vary. Use Cloud Billing Reports/Budgets/Calculator and real metrics.

## 15. Practice Lab: Routing Decisions for an IoT Platform

**Goal:** Design app profiles, justify consistency/failover choices, and validate via configs/metrics. Prefer **simulating with data/read-only commands** to avoid incurring charges if no sandbox is provisioned.

### 15.1. Part A — Initial Model

Assume the system has:

- **Realtime API**: needs lookup by device ID, tolerates a few seconds of stale reads during failover; p95 SLO is defined separately.
- **Quota counter**: requires safe increments/conditional mutations on a single row.
- **Batch analytics**: nightly data scans that must not raise API p95.
- **HA**: survive a single-zone failure within the same region; regional DR is a future requirement.
- **Security:** Cloud Run runtime SA may only read/write required tables; reporting is read-only.

**Task:** Determine cluster count, locations, app profiles, routing policies, and IAM. Use this table:

| Workload | App profile | Route | Transactions | Reason |
| --- | --- | --- | --- | --- |
| Realtime API | `api-ha` | Multi / any A,B | No | HA/nearest cluster, eventual consistency acceptable |
| Counter | `counter-single` | Single A | Yes | Safe read-modify-write when no concurrent writes hit B |
| Batch | `batch-asia` or Data Boost | Single A, LOW / read-only Data Boost | No | Controls impact on online API |

### 15.2. Part B — Preflight and Design

1. Verify gcloud project, Bigtable instance, cluster zones, and current `default` profile configuration.
2. If given a **lab with an existing instance**, inspect current profiles via `gcloud bigtable app-profiles list`.
3. Diagram the data paths for the API and counter. Highlight where stale reads can occur during failover.
4. Explain why the `telemetry` table exists on both clusters A and B without creating the table a second time.
5. Estimate preliminary node capacity if A fails: assuming B absorbs an extra 60% traffic, how much headroom is required?
6. Design autoscaling min/max/CPU targets **based on assumed metrics**, not merely user count.
7. Write a change plan to create profiles using Section 8 commands and apply only after owner approval.
8. Record verification that the runtime SA has appropriately scoped IAM and the client sets `setAppProfileId` properly.

### 15.3. Part C — Failure Scenarios

- **Scenario 1:** Write succeeds on cluster A, immediate read on B does not see the value. **Answer:** eventual replication; use single-cluster for read-your-writes or design to tolerate stale reads.
- **Scenario 2:** A team enables counter transactions on a multi-cluster profile. **Answer:** not allowed; switch to single-cluster and prohibit conflicting writes from other profiles.
- **Scenario 3:** Cluster A fails; `api-ha` fails over automatically while `counter-single` errors out. **Answer:** multi-cluster routes automatically; single-cluster requires a manual runbook, evaluating lag/capacity and transactional write risks.
- **Scenario 4:** Four profiles all scan against the same cluster; API p99 spikes. **Answer:** measure CPU by app profile, then apply LOW priority, Data Boost, or separate workloads.
- **Scenario 5:** Every cluster has high disk utilization, and an operator reduces nodes to cut costs. **Answer:** must check storage hard limits; lowering nodes could cause writes to fail across the instance.

### 15.4. Deliverables

| Evidence | Passing criteria |
| --- | --- |
| Diagram of instances/clusters/profiles | Accurate ownership and replication |
| Per-workload routing policies | Explicitly states auto/manual failover and consistency |
| Client configuration | Explicitly specifies `appProfileId` |
| Transaction behavior | Never routes `ReadModifyWriteRow` through multi-cluster |
| Autoscaling plan | CPU/storage targets, failover headroom |
| Metrics | Includes CPU/hottest node, replication lag, p95, system errors |
| Security | Least-privilege IAM, never confuses profiles with access control |
| Cost | Per-cluster compute/storage accounted for; budget alerts configured |
| DR | Backup/restore drills, data residency, and manual/auto failover |

## 16. Review Questions and Model Answers

1. **Does a table belong to a cluster or an instance?** It belongs to the **instance**; every cluster in the instance holds a replica of all tables.
2. **How does a node differ from a cluster?** Nodes scale compute within a cluster; a cluster is a separate zonal failure domain.
3. **Does adding a second cluster create a new table?** No; Bigtable replicates all tables.
4. **Can every replicated cluster accept writes?** Yes, all clusters are primary clusters.
5. **What consistency does a multi-cluster profile provide?** Eventual consistency across clusters, with automatic failover.
6. **Does a single-cluster profile have automatic failover?** No; operators must perform manual failover.
7. **Is read-your-writes guaranteed with row-affinity?** No; it only increases the probability under normal conditions.
8. **What does a read-modify-write counter require?** Single-cluster routing with transactional writes enabled; avoid conflicting writes on other clusters.
9. **Does the `default` app profile automatically switch to multi-cluster when adding a cluster?** No.
10. **Can `--route-any` be combined with `--transactional-writes`?** No.
11. **What is `--restrict-to=A,B` used for?** Restricts automatic routing/failover strictly to clusters A and B.
12. **Does `PRIORITY_LOW` block an app from reading sensitive tables?** No; IAM controls data access permissions.
13. **Why isn't adding a cluster guaranteed to increase write throughput?** Replication generates extra CPU/network work on every cluster.
14. **What workloads should use Data Boost?** High-throughput read analytics needing isolated compute; not for transactional writes.
15. **Is the newest write on A always immediately visible on B?** No, you must wait for replication to complete.
16. **What are the risks of adding a cluster in another region?** Increased latency, data residency concerns, and higher network egress/cost.
17. **What happens if `autoscaling-max-nodes` is too low during failover?** The receiving cluster lacks capacity, raising p95 latency and error rates.
18. **What does low average CPU with a high hottest node indicate?** A hot key range/tablet; inspect Key Visualizer.
19. **Does replication replace backups?** No; accidental deletions, schema changes, or GC rules replicate to every cluster.
20. **How does the Java client select routing?** `BigtableDataSettings.setAppProfileId(...)`.

## 17. Production Checklist and References

- [ ] Chose Bigtable based on access patterns/scale, not as a cache or default SQL JOIN engine.
- [ ] Instance edition, SSD/HDD, locations, and CMEK approved with budget.
- [ ] Clusters provide sufficient failure domains and capacity for all tables and replication.
- [ ] App profiles tailored per workload; `default` is not altered carelessly.
- [ ] Workloads requiring consistency use single-cluster routing where needed.
- [ ] Multi-cluster automatic failover tested and eventual consistency accepted.
- [ ] Single-row transactions enabled only on single-cluster profiles with no conflicting writers.
- [ ] Row affinity is not relied upon as a strong consistency guarantee.
- [ ] Clients explicitly call `setAppProfileId`; cluster IDs are never confused with instance IDs.
- [ ] Batch workloads have proper priority/compute isolation; Data Boost used only when suitable.
- [ ] Autoscaling min/max CPU/storage targets and failover headroom load-tested.
- [ ] Alerts configured for CPU/hottest node, storage, p95/p99, replication latency, and app profile usage.
- [ ] Least-privilege IAM/runtime identities, encryption/auditing, and data residency verified.
- [ ] Backup/restore drills and failover/failback runbooks in place.
- [ ] Multi-cluster node/storage/network/backup/Data Boost costs monitored.
- [ ] Do not delete shared instances/clusters/tables simply because a test has finished.

**Official Google Cloud Documentation:**

- [Bigtable overview](https://docs.cloud.google.com/bigtable/docs/overview) — workloads, consistency, and data protection.
- [Instances, clusters and nodes](https://docs.cloud.google.com/bigtable/docs/instances-clusters-nodes) — instance/cluster/node hierarchy, SSD/HDD.
- [Create an instance](https://docs.cloud.google.com/bigtable/docs/creating-instance) — instance, cluster, location/edition.
- [Modify an instance](https://docs.cloud.google.com/bigtable/docs/modifying-instance) — adding clusters, adjusting nodes/autoscaling.
- [Application profiles](https://docs.cloud.google.com/bigtable/docs/app-profiles) — default/custom, Standard, Data Boost.
- [Create and configure app profiles](https://docs.cloud.google.com/bigtable/docs/configuring-app-profiles) — routing, flags, and priority.
- [Routing options](https://docs.cloud.google.com/bigtable/docs/routing) — single/multi/group/row-affinity, transactions.
- [Replication overview](https://docs.cloud.google.com/bigtable/docs/replication-overview) — eventual consistency, conflict resolution.
- [Replication configurations](https://docs.cloud.google.com/bigtable/docs/replication-settings) — HA, workload separation.
- [Managing failovers](https://docs.cloud.google.com/bigtable/docs/managing-failovers) — manual vs. automatic.
- [Autoscaling](https://docs.cloud.google.com/bigtable/docs/autoscaling) — node targets and capacity.
- [Bigtable monitoring](https://docs.cloud.google.com/bigtable/docs/monitoring-instance) — cluster/app profile/replication metrics.
- [Data Boost overview](https://docs.cloud.google.com/bigtable/docs/data-boost-overview) — serverless compute for analytics.
- [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries) — ADC/Java `BigtableDataClient`.
- [gcloud app profiles create](https://docs.cloud.google.com/sdk/gcloud/reference/bigtable/app-profiles/create) — `--route-any`, `--route-to`.
- [gcloud instance create](https://docs.cloud.google.com/sdk/gcloud/reference/bigtable/instances/create) — `--cluster-config`.
- [Bigtable IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/bigtable) — Reader/User/Admin.
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing) — editions, nodes, storage, and Data Boost.

**Key takeaway:** **The instance owns the data; the cluster provides zonal compute and a data replica; the app profile determines how requests are routed.** A multi-cluster profile improves availability while requiring acceptance of eventual consistency; a single-cluster profile preserves read-your-writes and supports single-row transactions while requiring manual failover. Combine profiles, autoscaling, capacity headroom, IAM, and backups to achieve reliability without losing cost control.
