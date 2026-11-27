# Evaluating Kubernetes and Storage Before Stateful Deployment

Kubernetes excels at managing applications that can be recreated on any node. However, **Neo4j is a stateful database management system**: nodes, relationships, properties, indexes, and transaction logs must stay consistent even if a container, node, or Kubernetes cluster fails. A pod restarting cleanly does not prove data is intact, indexes are online, or transactions recovered properly.

This lesson belongs to the **Deployment** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j uses a **property graph** to store connected data, queries with Cypher, optimizes via indexes/constraints, and integrates with the Java Driver or Spring Data Neo4j. When placing this system on Kubernetes, decisions around **StatefulSets, PersistentVolumes, StorageClasses, CSI, topology, backups, resources, monitoring, and recovery** directly affect transaction durability and application availability.

The goal is not to claim "Neo4j can run on Kubernetes," but to evaluate **whether a specific infrastructure meets the database's requirements**. After this lesson, you will be able to:

- Compare Kubernetes against VMs/bare metal and managed Neo4j services like Aura based on business needs.
- Explain why StatefulSets, PVCs/PVs, and the rule that **each Neo4j server has its own isolated data volume** form the foundation of safe deployment.
- Evaluate StorageClasses/CSI for durability, `fsync`, latency, topology, access modes, resizing, and volume reclaim behavior.
- Distinguish **multiple pods** from a **real Neo4j cluster** with discovery, routing, consensus, and quorum.
- Plan resources, probes, backup/restore, upgrades, security, and failure testing.
- Build a go/no-go acceptance checklist grounded in RPO/RTO and operational evidence.

> **Version scope:** Neo4j setting names, Helm charts, clustering capabilities, backups, and service configs depend on version/edition/deployment tier. All illustrative YAML must be adapted to the organization-verified chart/operator, image, and CSI. Do not treat the single-pod example below as a high-availability production configuration.

## 1. The First Question: Should You Use Kubernetes?

**Kubernetes does not inherently make a database more durable.** It deploys, schedules, monitors pods, and replaces failed processes. Yet whether data survives a machine failure is still determined by **Neo4j, the storage layer, and recovery procedures**.

| Option | Advantages | Trade-offs | Best Fit When |
| --- | --- | --- | --- |
| **Neo4j on VM/bare metal** | Clear control over I/O paths, filesystems, backups, and resources; fewer orchestration layers. | Ops team must manage VMs, deployment, failover, patching, monitoring. | You have a DBA/SRE team needing granular storage control. |
| **Self-managed Neo4j on Kubernetes** | Integrates with GitOps, resources, secrets, monitoring, scheduling, and platform workflows. | Adds CSI/PVC, scheduler, networking, probes, rescheduling events, RBAC, and operator/chart risk. | You already run a mature Kubernetes platform experienced with stateful workloads. |
| **Managed Neo4j service** | Provider handles much of infra, backups/HA per service tier. | Constraints on regions, tiers, configuration surface, pricing, and infra access. | You want to focus on the app and accept service features/SLAs. |

Questions to answer **before** writing manifests:

1. How much data loss (**RPO**) and downtime (**RTO**) can the system tolerate?
2. Does recovery scope cover losing one pod, one node, one availability zone, or the entire Kubernetes cluster?
3. Are Neo4j Enterprise/clustering, online backups, role management, or other features required?
4. Can the ops team benchmark CSI performance, restore backups, handle PV/PVCs, and upgrade Neo4j?
5. What are the data residency, encryption, private networking, audit, tenant isolation, and budget constraints?
6. Is Kubernetes operational overhead justified by deployment standardization benefits?

Without answers for **RPO, RTO, and storage recovery**, writing a StatefulSet should be treated as a technical spike, not production approval.

## 2. Defining Clear State Boundaries

A Neo4j system on Kubernetes typically spans these layers:

~~~text
Java Driver / Spring Data Neo4j Client
              |
           Service
              |
          Neo4j Pod
              |
      +-------+-------+
      |               |
   Data store       Neo4j process
   indexes          heap/page cache
   metadata         transactions
      |
   /data mount
      |
 PersistentVolumeClaim (PVC)
      |
 PersistentVolume (PV)
      |
 StorageClass / CSI / physical volume
~~~

| Layer | What Kubernetes Guarantees | What It Does NOT Automatically Guarantee |
| --- | --- | --- |
| Pod/container | Recreates processes per controller and policy. | Data in ephemeral filesystems is not preserved. |
| StatefulSet | Stable identity/ordinals and per-template pod/volume claims. | Does not turn multiple processes into a Neo4j cluster. |
| PVC/PV | Binds claims to volumes via StorageClass/CSI. | Does not prove database consistency or durable `fsync`. |
| CSI/storage backend | Provisions, attaches, and detaches volumes per driver. | Not all backends share the same latency, semantics, or failure domains. |
| Neo4j | Manages transactions, store, indexes, and engine recovery. | Cannot protect data if storage fails or is misused. |
| Independent backup | Provides a recovery path when primary data is corrupted/lost. | Worthless without restore testing and consistency checks. |

### 2.1. Data Must Not Live on Ephemeral Volumes

`emptyDir`, container writable layers, or pod-scoped volumes are **not durable storage for production Neo4j**. When a pod is replaced, data vanishes. Use ephemeral storage only for temporary files safe to lose and rebuild.

Neo4j typically uses `/data` in official container images to hold database data. In real manifests, mount the PVC to the data directory matching your actual image and version. Never assume `/logs` or `/import` mounts substitute for transactional data.

### 2.2. One Data Volume Is Not for Multiple Concurrent Writers

**Never mount the same Neo4j store directory for two independent pods to write concurrently**, even if a StorageClass allows `ReadWriteMany`. A shared filesystem does not make the store multi-process safe; it causes lock conflicts and data corruption.

In a real Neo4j cluster, **each server owns its own local store on its own PVC**, while Neo4j handles replication and consensus over cluster protocols. Kubernetes merely provides scheduling, networking, and persistent volumes for each server to maintain state.

## 3. Analyzing Storage Requirements from Business Workloads

Start from actual Cypher queries and write paths:

| Workload | Key Storage Requirements |
| --- | --- |
| Low-latency indexed node lookups | Random access, p95/p99 latency, page-cache hit rate, and IOPS. |
| High-degree/multi-hop relationship traversals | Large working set, page cache, I/O on cache misses. |
| Continuous small transaction writes | Synchronous write latency and durable flush behavior. |
| Bulk imports/batch updates across many nodes | Write throughput, transaction logs, temporary headroom, index update speed. |
| Index/full-text/vector index rebuilds | CPU, I/O, index size, and peak disk consumption. |
| Backup/restore | High read/write bandwidth, isolated copy storage, and restore duration. |
| GDS projections | Primarily RAM- and CPU-heavy; still affects the system when sharing nodes. |

The storage backend must provide database-grade semantics: **write, flush data durably to media, and acknowledge completion accurately**. Never treat a sequential throughput benchmark alone as proof of suitability. For durability, verify data preservation across process, node, or volume failures per vendor and driver commitments.

### 3.1. CSI Vendor Verification Criteria

| Criterion | Question to Verify | Required Evidence |
| --- | --- | --- |
| Durability and `fsync`/flush | Once sync succeeds, is data safely preserved if a node crashes? | Storage docs, vendor support, and controlled fault tests. |
| Latency | p50/p95/p99 random read/write and sync write latency under representative load? | Staging benchmarks and pilot production metrics. |
| IOPS/throughput | Is the volume throttled by disk tier, capacity, or node limits? | Infra specs and peak load measurements. |
| Access mode | Does CSI support `ReadWriteOnce` or `ReadWriteOncePod`? | StorageClass/CSI driver, mount test results. |
| Topology | Which zone does the volume belong to, and where can pods run? | PV node affinity and reschedule tests. |
| Attach/detach | When an old node disconnects, how long until the volume moves to a new node? | Chaos tests and CSI events. |
| Volume expansion | Are online/offline expansion and filesystem resize supported? | StorageClass + PVC test. |
| Snapshots | Are VolumeSnapshots supported with suitable semantics? | CSI capability and consistent restore tests. |
| Reclaim | Does deleting a PVC delete the underlying physical volume? | `reclaimPolicy`/PVC retention, deletion drill. |
| Encryption | Are encryption at rest/in transit and proper key management supported? | Vendor docs and operational verification. |

Never substitute a marketing claim of "fast SSD" for **crash recovery and post-commit durability** tests.

## 4. StorageClass, PVC, and Access Modes

### 4.1. Inspect Before Provisioning

Read-only Kubernetes commands (do not alter data):

~~~bash
kubectl get storageclass
kubectl describe storageclass fast-csi-rwo
kubectl get csidrivers
kubectl get nodes -L topology.kubernetes.io/zone
~~~

`fast-csi-rwo` is a **hypothetical name**. If your cluster lacks that StorageClass, substitute the name verified by your infrastructure team. For a StorageClass, check `provisioner`, `volumeBindingMode`, `allowVolumeExpansion`, `reclaimPolicy`, and driver topology/parameters. Never infer real quality from the name alone.

### 4.2. Choosing the Right Access Mode

| Access Mode | Meaning at PVC/Kubernetes Level | Notes for Neo4j |
| --- | --- | --- |
| `ReadWriteOnce` (RWO) | Volume can be mounted read/write limited at the **node** level. | Common for block volumes; does not itself stop multiple pods on the same node from sharing a volume. |
| `ReadWriteOncePod` (RWOP) | Only a single pod cluster-wide can mount read/write, where Kubernetes/driver supports it. | Helps enforce "one pod per PVC," but does not replace transaction safety or Neo4j clustering. |
| `ReadWriteMany` (RWX) | Multiple nodes/pods can mount read/write per driver capability. | **Must NOT** be used for two Neo4j servers writing to the same store. |
| `ReadOnlyMany` (ROX) | Multiple nodes can mount read-only. | Unsuitable for an active writable Neo4j data directory. |

Exact mode capabilities depend on the CSI driver and volume type. `RWOP` works only on supporting Kubernetes/CSI versions; verify in practice. Neither `RWO` nor `RWOP` guarantees fast failover if the volume is zone-pinned or stuck detaching from an unreachable node.

### 4.3. Reclaim Policy Is a Data-Loss Decision

With dynamically provisioned PVs, `reclaimPolicy: Delete` can **delete the physical volume when the PVC is deleted**. `Retain` keeps the PV after the claim is released, requiring controlled admin cleanup and reuse procedures.

Do not treat `Retain` as a backup; volumes can still corrupt or be deleted at the storage layer. Before applying manifests, verify:

- Whether the default StorageClass uses `Delete` or `Retain`.
- What PVC retention/cleanup policy the StatefulSet uses on scale-down or controller deletion.
- Whether independent backups exist and have passed restore tests.
- Whether namespace deletion, GitOps pruning, and teardown pipelines are guarded against deleting real data.

Never assume "deleting a StatefulSet never deletes PVCs" in every setup: Kubernetes versions and `persistentVolumeClaimRetentionPolicy` can change that behavior. Verify the policy on the exact resources you deploy.

## 5. Choosing Topology: Local PV, Zonal Block Volume, or Network Storage?

| Storage Type | Strengths | Risks to Evaluate | Assessment |
| --- | --- | --- | --- |
| **Local SSD/NVMe via local PV** | Often low latency/high IOPS, fewer network hops. | Volume is node-bound; node failure prevents reattaching data elsewhere. | Requires Neo4j replication/backups and node-replacement plan; not standalone HA. |
| **Zonal persistent block volume** | Can reattach to another node in the same zone; cloud snapshots/resizing. | Zone-bound, attach/detach delays, tier-capped IOPS. | Usually worth evaluating for stateful workloads if benchmarks pass. |
| **Network filesystem/RWX** | Convenient file sharing and flexible mounting. | Latency, locking, flush semantics, throughput, and partition behavior may violate DB needs. | Pick only when **explicitly supported/verified by Neo4j and the backend**; never share stores across servers. |
| **Managed storage/DB service** | Less manual node/volume management. | Depends on SLA, version, region, privileges, and pricing. | Compare by RPO/RTO and total operational cost. |

There is no universal truth like "network storage is always slow" or "local SSD is always best": workloads, caching, IOPS, regions, and provisioner layers differ. However, tail latency and durable write semantics are **mandatory to measure**, never guessed from storage labels.

### 5.1. VolumeBindingMode and Zone Constraints

`WaitForFirstConsumer` delays volume binding/provisioning until a pod is scheduled in supporting setups. This reduces cases where a PVC gets provisioned in a zone where the pod cannot run. Yet once provisioned in a zone, **the pod and data cannot automatically move across zones**.

When a node fails:

1. StatefulSet tries to reschedule the pod via the scheduler.
2. The scheduler must find a node matching **PV topology and affinity**.
3. CSI must safely complete detach/attach.
4. Neo4j opens the store, runs any needed recovery, and then becomes ready.

If no eligible node exists in that zone, the pod stays `Pending` even when the rest of the Kubernetes cluster has spare CPU/RAM. **Cluster-wide Kubernetes capacity does not mean volumes can cross zones.**

## 6. Capacity and I/O Budgeting Before Launch Day

Do not equate source data size (CSVs, JSON, RDBMS tables) with Neo4j disk usage. The same source data can expand into vastly different counts of nodes, relationships, properties, and indexes.

Sample capacity budget:

| Component | Why Reserve Space? | Estimation Source |
| --- | --- | --- |
| Node/relationship/property store | Persistent data and Neo4j metadata. | Trial import on representative dataset. |
| Indexes and constraint-backed indexes | Property/lookup/full-text/vector queries. | Measure after building on schema-accurate test data. |
| Transaction logs | Writes, imports, checkpoint/recovery per policy. | Write rate and configured retention/catch-up. |
| Peak during migrations/index rebuilds | Temporary tasks require extra working space. | Upgrade/index population rehearsals. |
| Other logs and temp files | App/server logs, imports, staging files. | Actual mount points and retention. |
| Backups/snapshots | Independent recovery and copy storage. | Backup tool and object store; avoid sharing the data volume. |
| Headroom | Incidents, volume expansion, maintenance, unexpected growth. | RPO/RTO, growth rate, and response lead time. |

### 6.1. Example Budget Calculation

Suppose a representative trial import yields:

- Store: **220 GiB**.
- Indexes: **55 GiB**, assuming **not already included in the store measurement**.
- Transaction logs at peak bulk import: **80 GiB**.
- Other operational files: **15 GiB**.
- Approved headroom: **30%** on top of pre-headroom total.

When measurements **do not overlap**, pre-headroom demand is `220 + 55 + 80 + 15 = 370 GiB`; adding 30% headroom gives `481 GiB`. This is an **illustrative example**, not a universal Neo4j sizing recommendation.

If the "store size" metric already included indexes, adding 55 GiB would **double-count**. If data and transaction logs live on **two separate PVCs**, budget headroom per volume; 481 GiB total does not guarantee each individual volume has enough room.

### 6.2. Measuring I/O and `fsync` on the Exact StorageClass

Recommended staging tests on an isolated production-like volume:

1. Measure random read/write and p50/p95/p99 latency under mixed read/write load.
2. Measure Neo4j commit latency under concurrent transactions, not just raw file throughput.
3. Run trial imports, property updates, and index builds to observe peak store/log sizes.
4. Inject controlled pod/node failures **in the test environment** and verify committed data survives.
5. Measure volume attach, restart, store recovery, and read/write resumption times.
6. Repeat when the volume is nearly full, as performance often degrades compared to an empty volume.

Never run destructive write benchmarks like `fio --filename=<Neo4j store path>` on a live production volume; benchmark on a separate staging volume. Prefer **application → Neo4j** benchmarks to validate drivers, transactions, and indexes end to end.

## 7. Single-Node Manifest: Read to Understand Structure, Not as HA

This YAML illustrates a **StatefulSet with a single Neo4j server** and one PVC mounted at `/data`. It is useful for understanding structure and testing in an isolated environment once secrets, namespace, and StorageClass exist.

~~~yaml
# Requires namespace graph-demo, Secret neo4j-demo-auth,
# and StorageClass fast-csi-rwo to already exist.
# Image neo4j:5.26.0 is only an example pinned version;
# select an image and patch level tested/supported by your team.
apiVersion: v1
kind: Service
metadata:
  name: neo4j-demo-headless
  namespace: graph-demo
spec:
  clusterIP: None
  selector:
    app: neo4j-demo
  ports:
    - name: bolt
      port: 7687
      targetPort: 7687
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j-demo
  namespace: graph-demo
spec:
  serviceName: neo4j-demo-headless
  replicas: 1
  selector:
    matchLabels:
      app: neo4j-demo
  template:
    metadata:
      labels:
        app: neo4j-demo
    spec:
      terminationGracePeriodSeconds: 180
      containers:
        - name: neo4j
          image: neo4j:5.26.0
          ports:
            - name: bolt
              containerPort: 7687
          env:
            - name: NEO4J_AUTH
              valueFrom:
                secretKeyRef:
                  name: neo4j-demo-auth
                  key: neo4jAuth
            - name: NEO4J_server_memory_heap_initial__size
              value: "2G"
            - name: NEO4J_server_memory_heap_max__size
              value: "2G"
            - name: NEO4J_server_memory_pagecache_size
              value: "3G"
          resources:
            requests:
              cpu: "2"
              memory: "8Gi"
            limits:
              memory: "8Gi"
          volumeMounts:
            - name: data
              mountPath: /data
          startupProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 10
            failureThreshold: 60
          readinessProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 20
            failureThreshold: 6
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: fast-csi-rwo
        resources:
          requests:
            storage: 100Gi
~~~

**Limitations you must understand before applying:**

- `neo4j:5.26.0` is an illustrative tag, not a recommendation of the newest release. Production should pin tested versions, verify server/driver/edition compatibility, maintain vulnerability patching, and consider image digests per supply-chain policy.
- Secret `neo4j-demo-auth` holds key `neo4jAuth` formatted per the image's `NEO4J_AUTH` convention (e.g., `neo4j/<password>` on fresh init). **Never embed real passwords in manifests/Git.** On an already-initialized store, changing this env var does not automatically change the stored password.
- Heap/page cache settings must be verified on the **exact image/version**; the 8 GiB memory request/limit is illustrative only. Beyond heap and page cache, account for off-heap/native memory, transaction/query memory, and OS overhead.
- A TCP probe only verifies the port accepts connections; **it does not prove Cypher transactions work, the database is fully online, or the node is ready for cluster participation**. Real systems need health/readiness matching driver/version capabilities.
- A 100 GiB PVC may be insufficient if store, indexes, and transaction logs share it; do not reuse this number blindly for large workloads.
- A headless Service provides internal StatefulSet DNS identities; **it does not configure routing/advertised addresses or external TLS**.
- `replicas: 1` means zero Neo4j HA. Changing it to `replicas: 3` **does not** create a Neo4j cluster—it would spawn three independent standalone instances with divergent data.

### 7.1. Observing Pods and PVCs After Staging Deployment

~~~bash
kubectl -n graph-demo get statefulsets
kubectl -n graph-demo get pods -o wide
kubectl -n graph-demo get pvc
kubectl get pv
kubectl -n graph-demo describe pod neo4j-demo-0
kubectl -n graph-demo get events --sort-by=.lastTimestamp
~~~

These are read-only inspection commands requiring appropriate Kubernetes RBAC. Check `PVC Bound`, PV/zone, CSI events, container restarts, and pod readiness. Do not hastily delete a `Pending` PVC to "retry" if it already holds data or is bound to a volume you need to keep.

## 8. StatefulSet Provides Stable Identity, Not Database Clustering

StatefulSet manages ordinal-named pods and templated volume claims:

~~~text
neo4j-demo-0
   |
   +--> data-neo4j-demo-0 (PVC)
              |
              +--> PV / storage backend
~~~

When a pod is replaced, Kubernetes tries to reattach the bound PVC and preserve identity; this still depends on **attach/detach behavior, topology, scheduling rules, and ensuring the old process stopped writing**.

In a genuine Neo4j cluster:

~~~text
       Neo4j cluster
     (quorum/consensus)

neo4j-server-A   neo4j-server-B   neo4j-server-C
      |                 |                 |
     PVC-A             PVC-B             PVC-C
      |                 |                 |
    PV-A              PV-B              PV-C
~~~

Each server maintains an **independent store** and compatible cluster configuration. Kubernetes provides networking/volumes/processes; Neo4j handles replication, leader/primary roles, consensus, and query serving per edition/version capabilities.

### 8.1. Requirements for a Neo4j Cluster

For an architecture needing single-server fault tolerance, evaluate:

- Whether the Neo4j edition and version support required clustering/backup features.
- Primary/secondary counts and **majority/quorum** per that version's cluster mechanics; typically at least three primaries across independent failure domains are needed to keep quorum after losing one primary.
- Stable discovery and *advertised addresses* resolvable across pods and by relevant clients.
- Internal networking, TLS, certificates/DNS, required ports, and network policies.
- Dedicated PVC per server with sufficient capacity and performance—never shared stores.
- Scheduling spread across nodes/zones, never packing all primaries onto one machine.
- Rolling upgrade, backup, scale-up/down, and server replacement procedures per exact version docs.

**Do not equate Kubernetes replicas with consistent data copies.** Scaling pods is only a controller action; adding/removing database members must follow supported Neo4j cluster procedures.

### 8.2. Different Layers of High Availability

| Failure | What Kubernetes Can Handle | What Neo4j/Storage Must Still Handle |
| --- | --- | --- |
| Container crash | Restart container or replace pod. | Store recovery and query readiness. |
| Worker node dies | Reschedule pod if an eligible node exists. | Safe volume reattach or database failover to another server. |
| Loss of one zone | Scheduler can place workloads in another zone if resources allow. | Zonal volumes may not move; requires proper clustering/backups. |
| One Neo4j server unresponsive | Pod/readiness may detect it to some degree. | Quorum, leader election/routing, and transaction semantics. |
| Physical store/volume corruption | Kubernetes cannot regenerate lost data. | Valid replication, backup/restore, and rebuild procedures. |
| Accidental database/PVC deletion | Controller follows policy but cannot "undo" logical drops. | Backups, retention, audits, and destructive-action guards. |
| Entire Kubernetes cluster lost | No scheduler/config remains in that cluster. | Independent data copies and rehearsed disaster recovery. |

In some failover scenarios, **clients must retry eligible transactions** and use the right URI/routing mode, driver version, and advertised addresses. Using `neo4j://` will not fix broken DNS, TLS, network policies, or misconfigured routing topologies.

## 9. Scheduling, Anti-Affinity, and PodDisruptionBudgets

A three-server Neo4j cluster scheduled onto a single Kubernetes worker cannot survive losing that worker. When designing HA:

1. Use `podAntiAffinity` or `topologySpreadConstraints` to spread pods across hostnames and available zones.
2. Check **PV node affinity** so volumes can attach wherever the scheduler places pods.
3. Use a `PodDisruptionBudget` (PDB) to reduce the chance of simultaneous **voluntary evictions** breaking quorum.
4. Configure `priorityClassName`, guaranteed resources, and spare capacity to prevent critical pods from being evicted under node pressure.
5. Verify autoscaler and node-drain behavior: PVCs may take time to detach/attach, and Neo4j may take time to recover.

**A PDB cannot stop sudden node crashes**, zone outages, or network partitions; it only governs voluntary evictions through the Kubernetes eviction API. Do not make PDBs so strict that node maintenance stalls indefinitely, yet never let one drain take down enough primaries to lose quorum.

If fewer zones exist than pods to spread, an overly strict `DoNotSchedule` rule can leave pods stuck `Pending`. Match constraints to your SLA and actual cluster topology, then rehearse pod restarts, node drains, and zone failures.

## 10. Readiness, Startup, and Liveness Must Not Trigger Cascading Failures

Neo4j startup can take considerable time due to:

- Slow volume attach or throttled I/O.
- Store recovery after a crash or transaction log replay.
- Index population/rebuilds after maintenance or restore.
- Cluster quorum/discovery stabilizing.
- Page cache warming and query services reaching SLO.

| Probe | Goal | Common Mistake |
| --- | --- | --- |
| **startupProbe** | Allows a long startup window before liveness can kill the container. | Timeout set too low, causing endless restart loops during recovery. |
| **readinessProbe** | Controls whether the pod receives Service traffic. | Checking TCP only and assuming DB handles queries/transactions normally. |
| **livenessProbe** | Detects stuck processes needing restart. | Running heavy Cypher that occasionally times out and restarts a busy DB. |

Probes must be **lightweight, safe, least-privilege, and never leak credentials**. Never pass passwords inline in probe command lines where logs, `describe`, or process lists can expose them. Evaluate health procedures or endpoints supported by your image/chart version.

If a liveness probe restarts a pod while Neo4j is performing lengthy recovery, it can extend downtime indefinitely. Measure real startup/recovery times to set failure thresholds and termination grace periods.

### 10.1. Graceful Shutdown

When Kubernetes replaces a pod, it sends shutdown signals per container lifecycle; Neo4j needs time to flush and stop cleanly. Setting `terminationGracePeriodSeconds` too short can kill the process mid-work and lengthen recovery on the next boot.

Size the grace period for real workloads/transactions. Kubernetes can still lose a node abruptly without graceful shutdown, so **crash-recovery paths** must be tested—not just happy-path rolling restarts.

## 11. CPU, RAM, Page Cache, and Cgroup Resources

Neo4j uses more than just the Java heap. A pod's RAM budget must account for:

| Memory Area | Role |
| --- | --- |
| Java heap | Java objects and runtime/GC memory. |
| Neo4j page cache | Caches frequently accessed store/index pages. |
| Native/off-heap memory | Transactions/queries, driver/native structures, and internal allocations. |
| OS/container memory | Thread stacks, buffers, and system overhead. |
| GDS if enabled | Projections/algorithms can require large RAM outside normal query budgets. |

If a pod has `memory limit: 8Gi` yet configures 6 GiB heap and 4 GiB page cache, reservations already exceed the limit before adding anything else. Kubernetes can OOM-kill the pod, forcing restarts and recovery. **Do not treat `requests.memory` as a consumption cap**: `limits` govern cgroup OOM kills.

CPU:

- Set appropriate requests so the scheduler guarantees steady compute.
- Evaluate CPU limits carefully: throttling can spike tail latency; measure per infra policy.
- Budget CPU for index population, backups, GC, GDS, and failovers—not just average queries.

I/O:

- Measure disk latency and queue depth at the infrastructure layer.
- Inspect Neo4j page cache hit/miss rates, transaction latency, and log flush times where metrics exist.
- On volumes whose IOPS scale with capacity, resizing storage can impact throughput and cost together.

Never use a single memory graph to conclude "Neo4j has plenty of page cache left" if that metric only tracks JVM heap. Observability must separate memory sources.

## 12. Backups and Restores: Non-Negotiable Requirements

**A persistent PVC is not a backup. A Neo4j cluster is not a backup. A CSI snapshot is not automatically a consistent backup of a live writing database.**

Events like accidental Cypher deletions, buggy bulk updates, or compromised credentials replicate the **exact same bad data across every cluster member**. You need independent point-in-time copies and verified restore procedures.

### 12.1. Choose Backup Mechanisms by Edition and Version

For self-managed Neo4j, check **online/offline backup and restore** tools supported on your exact edition/version. In some versions, backups require dedicated service endpoints/ports and specific database/cluster conditions. For Aura, use the snapshot/backup policy provided by your service tier.

A backup plan must specify:

- **RPO:** how many minutes/hours of data loss are tolerable on recovery?
- **RTO:** total time for detection, provisioning, restore, recovery, index building, data validation, and reopening traffic?
- **Retention:** how many recovery points are kept, where/under which keys, and are copies stored outside the primary failure domain?
- **Integrity:** are checksums/file verification and decryption tested?
- **Restore drills:** are restores tested into a separate environment checking nodes/relationships/constraints/Cypher?
- **Re-provisioning procedures:** how are secrets, certificates, cluster addresses, and DNS handled post-restore?

### 12.2. CSI VolumeSnapshots: Useful, Not Application-Consistent by Default

A volume-level snapshot typically captures storage state at a point in time. For an actively writing database, it may be **crash-consistent** rather than **application-consistent**. When Neo4j splits store and transaction logs across multiple volumes, separate snapshots do not guarantee both volumes were captured at the exact same consistent point.

Therefore:

1. Verify whether Neo4j and the storage vendor document a **supported consistent snapshot procedure**.
2. If required, quiesce/back up strictly per official guidelines, respecting transaction boundaries; never freeze filesystems arbitrarily.
3. Protect snapshots from deletion alongside the namespace/cluster and test isolated restores.
4. Verify recoverability with matching **transaction logs/metadata** and validate the exact recovered data point.

Never treat `kubectl get volumesnapshots` showing `ReadyToUse` as proof that Neo4j can restore the database and meet RPO/RTO.

### 12.3. Running Criteria-Driven Restore Drills

A passing restore drill must prove:

| Check | Evidence |
| --- | --- |
| Backup decrypts/reads cleanly | Backup/restore tool succeeds with verified logs. |
| Database starts | Neo4j reports ONLINE and accepts test client connections. |
| Data is accurate | Key fixtures, node/relationship counts, constraints, and Cypher queries match. |
| New writes are safe | Can commit, restart, and read back newly written transactions. |
| Privileges are intact | Read/write accounts and tenant boundaries are properly restored. |
| RPO/RTO met | Recorded latest recovered timestamp and actual end-to-end restore time. |
| Independent of failed source | Restored environment uses copies and secrets from a valid failure domain. |

If any step remains unverified, its status must be **backup exists, restore unproven**, not "DR ready."

## 13. Upgrades, Scaling, and Storage Changes

### 13.1. Upgrading Images Is Not an Ordinary Rolling Restart

Neo4j enforces compatibility across engine versions, store formats, cluster protocols, GDS/APOC plugins, and the Java Driver. Major/minor upgrades or store migrations may require specific sequencing and tooling.

Before changing the image:

1. Check the supported compatibility matrix for the target version and edition.
2. Back up, test restore, and run migrations in staging using representative data.
3. Check chart/operator values, deprecated settings, and image entrypoints.
4. Schedule cluster server updates in the supported sequence—never restart all members simultaneously.
5. Verify Cypher, indexes, constraints, Java Driver, Spring Data Neo4j, and plugins post-upgrade.
6. Define a realistic rollback: **restarting the older version on an upgraded store is often unsupported**; you may need to restore the pre-upgrade backup.

Never use the `latest` image tag for stateful deployments. GitOps/Helm can pull a newer image without an explicit reviewed change.

### 13.2. Scaling Up Storage

Check whether the StorageClass sets `allowVolumeExpansion`, whether CSI supports online/offline volume and filesystem expansion, and any restart requirements. If supported, expand the **PVC through Kubernetes**; never hack PV files/host paths directly or attempt to shrink volumes. Volume expansion can be hard to roll back.

The procedure should cover:

- Measuring current headroom and projected peaks.
- Confirming storage quotas/limits and availability zones.
- Backups and an abort plan if errors occur.
- Testing expansion on a staging environment/instance first, observing both Kubernetes and filesystem resize.
- Running verification queries/transactions after the volume reports the new size.

**Scaling down storage** is usually unsupported in place; to shrink physical footprint, plan a rebuild/restore onto a new volume via supported procedures. Deleting nodes in Neo4j does not guarantee underlying store files immediately shrink on disk.

### 13.3. Scaling Servers or Migrating Volumes

Adding a Neo4j cluster server requires planning discovery, privileges, roles, a new PVC, routing, and consensus. Removing a server must also follow cluster procedures; never simply run `kubectl scale --replicas 2` from 3 and assume it is safe.

Moving PVCs across storage tiers or zones requires planning for Neo4j downtime, data consistency, and rollback. Running `kubectl apply` to change StorageClass on an existing claim **does not** migrate data to the new backend; you generally must provision a new PVC and use supported migration/restore tools.

## 14. Securing Kubernetes and Neo4j Connection Paths

Neo4j holds sensitive data and relationships. Secure every layer from the Kubernetes control plane down to the database:

| Area | Requirement |
| --- | --- |
| Secrets | Never store passwords/tokens in Git, images, or logs; use Secrets/secret managers with RBAC, encryption at rest, and rotation policies. |
| Service accounts | Pods and CI/CD get only required Kubernetes permissions; disable auto-mounting Kubernetes tokens when unused. |
| NetworkPolicy | Restrict ingress to Bolt/HTTP/admin and cluster ports; separate clients, members, backups, and metrics. |
| TLS | Encrypt client–Neo4j and server–server links as required; verify certificates/hostnames. |
| Storage encryption | Encrypt volumes, snapshots, and backups with proper key management; assess PII exposure via relationships. |
| Container privileges | Run least-privilege with CSI-compatible UID/GID and `fsGroup`; avoid privileged containers without strict justification. |
| Image provenance | Pin versions/digests, scan images, restrict registries and loaded Neo4j plugins. |
| Neo4j privileges | Separate app read/write, backup, monitoring, and admin accounts; use granular RBAC per edition. |
| Exposure | Do not expose Bolt/HTTP to the public Internet unnecessarily; control ingress/load balancers and audit access. |

Kubernetes Secrets **are only a mechanism for managing sensitive config**, not absolute secrecy if etcd is unencrypted or RBAC grants broad secret reads. In the example manifest, `NEO4J_AUTH` inside the container environment can still be read by users with pod-debug privileges; production must evaluate privilege boundaries and real password rotation.

When using `neo4j://` with cluster routing, clients must resolve and reach Neo4j's advertised addresses. A stable Service IP is insufficient if the driver receives internal hostnames unreachable from outside the cluster.

## 15. Monitoring to Know If the Database Is Truly Healthy

An adequate dashboard needs **two measurement layers**:

**Kubernetes/storage:**

- Pod phase, restarts, OOMKilled, Ready/NotReady.
- PVC/PV status, VolumeAttachment errors, free disk bytes, volume growth.
- CSI latency, IOPS, throughput, attach/detach duration, and filesystem errors.
- Node conditions, CPU throttling, cgroup memory, and eviction events.
- Scheduler `Pending` states due to topology, quota, or resource shortages.

**Neo4j/application:**

- Database ONLINE/availability, cluster membership/quorum/catch-up where supported.
- Transaction commit/rollback rates, p95/p99 latency, and query errors.
- Store/index/transaction-log sizes, index states `ONLINE/POPULATING/FAILED`.
- Page cache, heap/GC, off-heap/transaction/query memory where metrics are exposed.
- Backup success/age, restore drills, import/CDC lag.
- Real Cypher latency in Java Driver/Spring Data Neo4j and retry rates.

Do not equate `Pod Ready` with `Neo4j healthy`. A pod may answer TCP while Cypher queries crawl, the cluster lacks quorum, or disk is nearly full. Conversely, an overly aggressive probe can kill a pod legitimately performing crash recovery.

**Alerting on missing metrics** is mandatory: zero data from a stopped collector does not mean 0% disk usage. Beyond percentages, disk alerts must check **remaining GiB and time-to-exhaustion forecasts**.

## 16. Pre-GO/NO-GO Testing

Build a staging environment matching production's **Kubernetes version, CSI/storage tier, topology, and Neo4j image**; use representative datasets, not just a handful of nodes.

| ID | Scenario | Passing Evidence |
| --- | --- | --- |
| K01 | Representative data import and index creation. | Measured store/index/log sizes fit with headroom. |
| K02 | Concurrent Cypher reads/writes under load. | p95/p99, IOPS/latency, and CPU/RAM meet SLO. |
| K03 | Controlled container restart. | Committed data intact; Neo4j recovers and becomes ready. |
| K04 | Delete pod so controller recreates it. | Same PVC reattaches; no fresh empty database created. |
| K05 | Planned node drain. | Detach/attach and recovery finish within RTO. |
| K06 | Sudden node loss in staging. | No two writers share a store; recovery/failover works per design. |
| K07 | Availability zone outage. | Cluster/backup architecture meets committed HA scope, or limits documented. |
| K08 | PVC stuck attaching / wrong zone. | Clear alerts; Pending pod not treated as healthy; recovery runbook exists. |
| K09 | Elevated CSI/storage latency. | Tail latency alerts fire; timeouts/throughput measured in Neo4j and infra. |
| K10 | Storage approaches headroom threshold. | Early alert fires; resolved without deleting database files. |
| K11 | Index `POPULATING`/`FAILED` during test. | State, query impact, and root cause clearly observable. |
| K12 | Backup and restore to another namespace/cluster. | Data, constraints, privileges, and Cypher match; RPO/RTO measured. |
| K13 | Java client disconnect/failover. | Routing and transaction retries behave cleanly without duplicate business side effects. |
| K14 | Supported version upgrade on test data. | Store/driver/plugins compatible, zero data loss, rollback path verified. |
| K15 | Privilege/network and secret restrictions. | Unauthorized pods cannot read data/secrets; TLS verified. |
| K16 | Accidental StatefulSet deletion in staging. | PVC/reclaim behavior matches policy; no unintended volume loss. |
| K17 | Metrics/collector outage. | Missing-telemetry alert fires; not misread as stable DB. |
| K18 | Quorum loss in test cluster. | System enforces write availability limits properly and recovers cleanly. |

### 16.1. Testing Committed Data Across a Restart

In a test database, create data with a stable key:

~~~cypher
CREATE CONSTRAINT deploy_demo_id IF NOT EXISTS
FOR (n:DeployDemoRecord)
REQUIRE n.recordId IS UNIQUE;
~~~

~~~cypher
MERGE (n:DeployDemoRecord {recordId: 'restart-test-001'})
SET n.expectedValue = 'persisted',
    n.updatedAt = datetime()
RETURN n.recordId AS recordId, n.expectedValue AS value;
~~~

Only after the write **commits successfully**, restart/kill the pod under controlled test conditions. After Neo4j recovers:

~~~cypher
MATCH (n:DeployDemoRecord {recordId: 'restart-test-001'})
RETURN n.expectedValue AS value;
~~~

Expected result: `value = 'persisted'`. This minimal test catches deployments accidentally storing data on ephemeral filesystems. It **does not** prove crash consistency for every write pattern or zero data loss across all storage failures; combine it with multi-transaction tests and backup verification.

### 16.2. Never Run Destructive Chaos Tests on Production Data

Run node/zone kills, network faults, volume detaches, or disk-full tests **only in isolated environments with synthetic data** and a recovery plan. Never use real data to trigger data-loss conditions just to "see if it works."

## 17. Common Incident Runbooks

### 17.1. Pod Pending, PVC Unbound

**Symptoms:** `StatefulSet` creates a pod stuck `Pending`, `PVC Pending`, or `FailedScheduling` events.

Procedure:

1. Inspect `kubectl describe pod`, `kubectl get pvc/pv`, and PVC events.
2. Verify StorageClass existence, quotas, access modes, `WaitForFirstConsumer`, and CSI provisioner.
3. Verify zone topology/node affinity and volume attachability where the pod can schedule.
4. Preserve existing PVCs/PVs containing data—never delete them and let the provisioner create empty volumes.
5. Adjust quotas/node capacity/topology per plan; verify the pod mounts the right data on recovery.

### 17.2. Pod CrashLoopBackOff or OOMKilled

**Symptoms:** continuous container restarts, failing queries, or flapping readiness.

Procedure:

1. Distinguish OOM, `/data` permission errors, invalid Neo4j config, mismatched image/plugin versions, and slow recovery.
2. Check authorized events/logs; protect secrets and sensitive details.
3. If probe-triggered, inspect `startupProbe`/liveness and actual recovery duration—never blindly disable all probes.
4. If memory-related, compare heap, page cache, and native memory against cgroup limits.
5. After fixing, verify committed data is intact and read/write queries succeed.

### 17.3. Volume Full or Rapid Transaction Log Growth

**Symptoms:** shrinking free disk, failing transaction commits, impacted indexes, abnormally large transaction logs.

Procedure:

1. Identify which PVC/volume is full and what grew: store, indexes, transaction logs, or other logs.
2. Inspect imports, huge transactions, retry loops, index builds, retention/pruning, and cluster/backup state.
3. Prioritize adding headroom or throttling non-essential write jobs per approved runbook.
4. **Never manually delete store/index/transaction log files.** Neo4j manages rotation/retention internally.
5. Once safe space is restored, verify consistency/availability, backups, and cluster progress.

### 17.4. Losing a Neo4j Cluster Member

**Symptoms:** clients report routing/leader errors, one server is NotReady, or topology is unstable.

Procedure:

1. Assess whether the database retains quorum and what level of read/write service remains—do not look only at pod count.
2. Check DNS/advertised addresses, certificates, cluster networking, and server status.
3. Verify the failed server's PVC is intact, safely attachable, and matches an eligible zonal node.
4. Following version-accurate Neo4j cluster procedures, recover/catch up the server or rebuild the member from a trusted source; never alter membership by deleting PVCs arbitrarily.
5. Verify Java Driver routing, transaction retries, writes around failover, and health/backups once stabilized.

## 18. GO / NO-GO Decision Table

| Criterion | GO When | NO-GO or Redesign When |
| --- | --- | --- |
| RPO/RTO | Clear targets exist, architecture satisfies them, restore drills measured. | Relying solely on "Kubernetes auto-restarts." |
| Storage durability | CSI/backend and durable flush supported/verified. | Storage cannot guarantee required flush/durability. |
| PVC lifecycle | Clear reclaim/retention rules; accidental deletion guarded. | Deleting controller/namespace risks unbacked-up data loss. |
| Topology | Pods recover in valid zones/failure domains; cluster properly designed. | PVs are zone-locked while SLA requires surviving zone loss without a plan. |
| Database cluster | Edition, quorum, discovery, TLS, routing, and per-server PVCs tested. | Only increased StatefulSet `replicas` without Neo4j clustering config. |
| Capacity | Imports, indexes, tx logs, backups, and headroom sized from representative measurements. | Sized PVC by guessing from raw CSV size. |
| Performance | Measured p95/p99 query/commit latency and I/O on exact CSI tier. | No commit latency or peak load testing done. |
| Security | Secrets, RBAC, network, TLS, encryption at rest, and audits meet requirements. | Public DB, hard-coded secrets, or overly broad privileges. |
| Backup/DR | Independent copies, restore tests, data/constraint verification exist. | Only unverified CSI snapshots exist. |
| Operations | Monitoring, alerts, owners, on-call, and PVC/cluster runbooks ready. | Nobody has access/skills to handle volume attach or restore. |

A **GO decision can carry conditions**, such as accepting single-node Neo4j for dev or an internal app with a long RTO, but it must **never** be labeled zone-fault-tolerant or zero-downtime.

## 19. Hands-On Exercises

**Exercise 1 — Platform selection.** A team of two backend engineers with no SRE requires a max 5-minute RPO and 30-minute recovery from a zone outage. Compare Neo4j on VMs, self-managed Kubernetes, and managed services. Identify what evidence is needed before choosing.

**Exercise 2 — Reading StorageClasses.** Two StorageClasses exist: A is local NVMe with `WaitForFirstConsumer`, B is zonal block storage with `ReadWriteOnce` and resize support. Build a survivability table for pod restart, node loss, and zone loss. Do not assume B moves across zones just because it uses PVCs.

**Exercise 3 — Access modes.** A team proposes `ReadWriteMany` so three Neo4j pods share one `/data` directory, calling it a "simple cluster." Explain why this design is broken, and sketch three isolated PVCs for a three-server Neo4j cluster.

**Exercise 4 — Capacity math.** After a trial import, store is 300 GiB, indexes not in store are 60 GiB, peak tx logs are 90 GiB, and other files are 20 GiB. With 25% headroom, compute total demand. Adjust the math if indexes were already inside store; split into two budgets if transaction logs use a separate PVC.

**Exercise 5 — True readiness.** Kubernetes shows all three pods Ready via TCP probes, yet Neo4j lost quorum. Why is the pod-count dashboard misleading? Design additional health checks/metrics to detect write unavailability.

**Exercise 6 — Probes.** Neo4j needs 4 minutes to recover, yet liveness kills the container after 30 seconds without Bolt open. Identify the CrashLoop cause and redesign startup/readiness/liveness from real measurements.

**Exercise 7 — PVC lifecycle.** A GitOps job deletes a test namespace containing a StatefulSet and PVCs. Explain when namespace deletion destroys physical volumes, the difference between `Delete` and `Retain`, and why `Retain` never replaces backups.

**Exercise 8 — CSI snapshots.** Neo4j store and transaction logs live on two separate PVCs; snapshots are taken 30 seconds apart while the database is writing. Can those snapshots be treated as an application-consistent backup? Propose a workflow using Neo4j-supported backup/restore and test it.

**Exercise 9 — Pod Pending incident.** A Neo4j pod is replaced, yet its PVC only attaches in zone A while spare node capacity exists only in zone B. Explain PV topology, safe recovery options, and why you must not delete the PVC to create a new empty volume.

**Exercise 10 — GO decision test.** Define targets for p95 query latency, commit latency, RPO, RTO, capacity, and backup/restore time. Build an abbreviated K01–K18 test matrix for a concrete system, marking which failures trigger **NO-GO**.

## 20. Stateful Deployment Checklist

1. **Right operational model chosen:** self-managed Kubernetes, VM, or managed service based on real needs, not trends.
2. **Approved RPO/RTO:** failure scopes for pods, nodes, zones, and entire cluster clearly defined.
3. **CSI/storage verified:** `fsync`/durability, IOPS, latency, topology, attach/detach, resize, snapshots, and encryption tested.
4. **No ephemeral data:** Neo4j store resides on proper PVCs; each Neo4j server has isolated storage.
5. **StatefulSet understood:** stable pods/claims do not equal clustering; Neo4j replicas configured per database procedures.
6. **Accurate capacity budget:** nodes, relationships, properties, indexes, transaction logs, import peaks, and headroom counted without overlap.
7. **Maintenance plan:** pinned images/versions, driver/plugin compatibility, rolling upgrades, and rollbacks rehearsed.
8. **Sound probes:** slow startup/recovery not killed repeatedly by liveness; readiness reflects real serviceability.
9. **Failure-domain-aware HA:** placement, quorum, PV topology, PDBs, and client routing tested—not just pod count.
10. **Independent backups and real restores:** never equate PVCs, replicas, or VolumeSnapshots with guaranteed recovery.
11. **Defense-in-depth security:** Secrets/RBAC, NetworkPolicies, TLS, encryption at rest, image provenance, and Neo4j privileges.
12. **Full-stack observability:** Kubernetes + CSI/storage + Neo4j + Java Driver/Spring Data Neo4j, with missing-metric alerts.
13. **Owned runbooks:** handling Pending PVCs, CrashLoops, full disks, quorum loss, and restores with clear permissions.
14. **Controlled failure testing:** pod restarts, node failures, zone failures, backup restores, upgrades, volume expansion, and transaction checks.
15. **GO only with evidence:** a demo pod starting up never replaces load testing, restore drills, and data integrity verification.

**Conclusion:** Kubernetes is only suitable for stateful Neo4j when **storage is genuinely durable, topology and access controls are designed properly, each server has its own PVC, Neo4j clustering is configured correctly, and backup/restore workflows are tested**. StatefulSets preserve pod identity; StorageClasses/CSI govern where and how data persists; Neo4j governs transaction and cluster consistency. Approve deployments based on **SLOs, RPO/RTO, I/O metrics, and incident drill results**—never solely on `Running` status in Kubernetes.
