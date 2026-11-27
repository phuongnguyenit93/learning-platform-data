# Operating Containers/Kubernetes and Persistent Storage According to Environmental Conditions

> **Chapter:** Operations Automation  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database placing data by partition key/token, replication factor, and DC/rack. When running in containers or Kubernetes, you must align topology, persistent disks, consistency levels, compaction/repair, backups, and Java CQL applications properly.  
> **Focus:** Selecting deployment and operational patterns **based on environment** (laptop, CI, staging, production; VMs, local disks, cloud block storage, multi-zone), rather than assuming one Kubernetes manifest works in every cluster.

## 1. Scenario: pods self-heal, yet is the data truly safe?

A Java service writes tenant events to Cassandra. The cluster was migrated from VMs to Kubernetes. After a node pool upgrade:

- Cassandra pods were terminated and recreated, each receiving a new IP.
- One new pod mounted an empty volume because its PVC was not reused properly.
- The two surviving replicas kept satisfying **LOCAL_QUORUM**, so the API did not report errors immediately.
- Operators assumed Kubernetes had "self-healed" because every pod returned to Running.
- A day later, request timeouts appeared, repair/streaming spiked load, and missing data surfaced on another read path.

The root cause may not lie in CQL. It may lie in **node identity, persistent volume data, topology/replica placement, node-replacement procedures, or cluster-level automation**.

**Kubernetes manages container lifecycles; it does not automatically preserve Cassandra's distributed semantics.** A Running pod or a Bound PersistentVolume does not prove token ownership, SSTables, commitlogs, repair, CL, backups, and data correctness are intact.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **container filesystem**, **emptyDir**, **PersistentVolume/PersistentVolumeClaim**, and **off-fault-domain backups**.
2. Choose between **Docker/Compose for labs**, **self-managed StatefulSets**, **Cassandra operators**, and VM/bare-metal models.
3. Design **StorageClass/CSI, volume binding, and topology (zone/rack/DC)** matching hardware and RPO/RTO.
4. Keep **node identity, volume identity, seed/discovery, and RF/DC/rack** stable instead of replacing a Cassandra node like a stateless pod.
5. Configure **startup/readiness/liveness probes, PodDisruptionBudgets, termination grace, and rollouts** without causing restart storms or quorum loss.
6. Size **requests/limits, disk headroom, cgroup/JVM heap, off-heap, page cache, and I/O telemetry** properly.
7. Distinguish **pod restart**, **node replacement**, **rebuild/repair**, **snapshot**, and **backup restore**.
8. Connect from **Java Driver 4.x** using matching local DC, contact points, TLS/auth, and contracted CL.
9. Design runbooks for Pending PVCs, unmountable volumes, pod CrashLoops, zone failures, full disks, and upgrades.
10. Test safely in staging and make GO/PAUSE/STOP decisions backed by evidence.

> **Operational warning:** Lab examples illustrate configuration only. Never directly apply sample StatefulSets, delete PVCs/PVs, scale Cassandra, force-delete pods, alter StorageClass/volume topology, run repair/rebuild, or change RF in production. Those actions require a Cassandra operator/runbook, an owner, verified backups, and change approval.

## 2. Three persistence layers: Cassandra, Kubernetes, and storage

~~~mermaid
flowchart TD
    A["Java application\nCQL + CL + routing key"] --> B["Cassandra node\ncoordinator / replica"]
    B --> C["Memtable + Commitlog"]
    B --> D["SSTables + compaction"]
    C --> E["Container mount"]
    D --> E
    E --> F{"Persistent storage?"}
    F -->|ephemeral| G["emptyDir / container layer\ncan be lost when pod is replaced"]
    F -->|PVC/PV/CSI| H["Volume bound to node identity\ndepends on storage backend"]
    H --> I["Storage fault domain\nnode / rack / zone / region"]
    H --> J["Snapshots + off-domain backup\nmanifest + restore drill"]
~~~

### 2.1. Cassandra data model

Cassandra receives mutations via coordinators and distributes them to replicas owning token ranges by partition key. Under **NetworkTopologyStrategy**, RF is configured per DC; for instance, **RF=3 in `dc1`** with **LOCAL_QUORUM** typically requires replies from **two of three** local replicas.

Each replica maintains its own SSTables and commitlog. Placement/token info, schema, repaired SSTables, compaction, and replication state all affect recovery. **RF=3 tolerates certain replica failures, yet is not three independent backups.**

### 2.2. Kubernetes storage model

- **Container writable layer:** ephemeral; replacing containers or pods is not reliable persistence.
- **emptyDir:** tied to the **Pod** lifecycle; survives container restarts inside the same Pod, yet is wiped when the Pod is deleted or evicted.
- **PersistentVolume (PV):** provisioned or managed cluster storage volume resource.
- **PersistentVolumeClaim (PVC):** workload storage request bound to a PV via provisioning/binding.
- **StorageClass/CSI:** defines the driver, provisioning, binding, expansion, reclaim, and topology per backend.
- **VolumeSnapshot:** storage-layer snapshot when supported by CSI/snapshot controllers; **does not prove cluster-wide Cassandra consistency**.
- **Backup:** verified copy stored outside the relevant fault domain and restorable within measured RPO/RTO.

**A Bound PVC does not mean "data can never be lost."** Backends can suffer volume failures, zone outages, misprovisioning, security/mount issues, silent corruption, or accidental deletion. Design fault domains and off-cluster backups separately.

### 2.3. Datasets that must be preserved accurately

In a Cassandra container image, data/config paths depend on packaging. The **official Docker image** commonly uses **`/var/lib/cassandra`**; other builds or operators may use different paths and split data/commitlog/hints. Verify against the actual effective config:

| Data type | Role | Common mistake |
|---|---|---|
| **SSTables / data directories** | Flushed data | Mounting PVC on wrong path, leaving SSTables on container layer |
| **Commitlog** | Durability for recent mutations | Placing on ephemeral storage unaware of data loss on node crash |
| **Hints** | Stores missed mutations for later delivery | Confusing hints with full backup or repair |
| **Saved caches** | Regenerable cache state | Allocating excessive space or assuming caches protect source data |
| **Snapshots / incremental backups** | Snapshot-based recovery points | Treating local snapshots as off-domain backups |
| **Config, certificates, secrets** | Node identity, DC/rack, TLS/auth | Changing config on image/pod updates without change control |

Never apply "mounting one PVC is enough" if the image configures data, commitlog, and hints on separate paths. Conversely, never split into multiple volumes without verifying IOPS and operator mount/repair/restore support.

## 3. Environment dictates the solution, not the reverse

| Environment | Priority | Acceptable | Must not claim |
|---|---|---|---|
| **Laptop/dev** | Fast CQL/Java iteration, synthetic data | Single-node Docker/Compose, local or intentional ephemeral volume | Verified RF3/HA/multi-zone |
| **CI integration** | Reproducible tests, clean resets | Testcontainers / ephemeral data containers | Production-grade backup/repair |
| **Staging** | Resembles topology, disk/network, maintenance | Operator/StatefulSet, PVC/CSI, RF/DC, approved fault tests | Production guaranteed identical |
| **Production single-region** | Zone/rack HA, recovery | Version-supported operator, persistent disks, external backups | Kubernetes rescheduling fixes all data errors |
| **Production multi-DC** | Locality, WAN, data residency, DR | Per-DC NTS RF, DC/rack placement, controlled streaming/repair | Single-DC `LOCAL_QUORUM` guarantees all DCs synced |
| **VM / bare metal** | Optimal I/O, host/disk control | SSD/NVMe and appropriate manual/automated node lifecycles | Kubernetes is always better |

A single-machine small cluster can use **RF=1** for labs. Yet an RF1 test **never proves** quorum, unavailable handling, repair, or zone faults. Never extrapolate single-node results to distributed production.

### 3.1. Environment selection questions

1. What are the approved RPO, RTO, and data retention policies?
2. Are Cassandra, image, operator, CSI, and Kubernetes versions compatible?
3. How many **DCs and racks/zones**, what per-DC RF, and what fault tolerance are required?
4. What are current data size, growth rate, hot partitions, read/write p99, and compaction backlogs?
5. Is the storage backend **cloud block SSD**, local NVMe PV, SAN, or other? What are latency/IOPS and zone affinity?
6. During a fault, can a pod reschedule onto a new node/zone and still reattach its volume?
7. Are off-domain backups/restore drills and encryption/KMS operational?
8. What eviction limits, node drains, upgrade windows, PDBs, and change owners exist?
9. Does the Java Driver run in-cluster, outside Kubernetes, or via a managed proxy/service?
10. Who owns incidents when Pods are Running yet Cassandra is not JOIN/NORMAL or PVCs fail to mount?

## 4. Docker and Compose: great for learning, no substitute for production

### 4.1. Running a lab with explicit volumes

Single-node Docker Compose example using the official image's common data directory:

~~~yaml
services:
  cassandra:
    image: cassandra:5.0 # Lab; production pins digest and compatible version
    container_name: cassandra-lab
    environment:
      CASSANDRA_CLUSTER_NAME: cassandra-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
    ports:
      - "127.0.0.1:9042:9042"
    volumes:
      - cassandra_lab_data:/var/lib/cassandra
    restart: unless-stopped

volumes:
  cassandra_lab_data:
~~~

**Explanation:**

- A **named volume** preserves data across container recreation unless deleted; it still lives on the Docker host, not as an offsite backup.
- Bind ports to **127.0.0.1** for labs rather than exposing native transport across the network.
- Environment variables depend on the **image**. Never assume another image supports the same names or defaults.
- Authentication/TLS is omitted here for simplicity; **never use this config to expose CQL in untrusted environments**.
- Avoid `docker compose down -v` when preserving volumes; `-v` removes volumes and wipes lab data.
- Container health and Cassandra startup take time; Running does not mean the CQL listener is ready.

### 4.2. Container failure/recovery differs from distributed node loss

- **Container restart:** container reuses its volume; Cassandra replays commitlogs and resumes.
- **Container remove + recreate:** if mounted properly, data can survive; on ephemeral layers, data is lost.
- **Docker host disk loss:** named volumes on the same host do not protect against host hardware loss.
- **Multi-node Compose on one host:** can model basic protocol/quorum behavior, yet cannot simulate real rack/zone failures.
- **Docker Desktop / WSL filesystems:** I/O, memory cgroups, and networking differ significantly from production Linux.

Docker labs should use **test data and test tables** for small experiments. Repair, node replacement, disk faults, and HA require representative staging clusters.

## 5. Why does Cassandra need a StatefulSet or operator?

Stateless Deployments swap pod identities freely. Cassandra binds node identity and data directories to replica ownership, so Kubernetes deployments typically use **StatefulSets** or **Cassandra-aware operators**.

### 5.1. What does a StatefulSet provide?

- **Ordinal-pinned pod names:** e.g., `cassandra-0`, `cassandra-1`.
- **Dedicated PVC per pod** via `volumeClaimTemplates`.
- **Stable network identity** when paired with a headless Service.
- Ordered rollout/update semantics and PVC retention policies depending on config/version.
- Still, Kubernetes does not natively understand **token rings, seed membership, RF, repair, rebuild, or safe node replacement**.

### 5.2. What does an operator add?

A supported Cassandra-aware operator can coordinate bootstrap, topology, rack placement, rolling upgrades, scaling, backup integration, restore/replacement, and repair hooks within its product capabilities. However, **having an operator does not replace runbooks and verification**.

| Layer | Kubernetes / StatefulSet | Cassandra operator / runbook |
|---|---|---|
| Pod scheduling / PVC binding | Standard Kubernetes primitives | Can enforce zone/rack policies |
| Token ring, seeds/discovery | Lacks full distributed semantics | Requires Cassandra-specific operator/config |
| RF, DC/rack, and CL | Never chosen automatically | Must be designed and verified |
| Node bootstrap/replace | Creates container/PVC | Version-aware Cassandra coordination |
| Readiness/downtime | Probes and Pod status | Needs gossip/native-protocol/topology checks |
| Safe scaling/upgrades | Rollout primitives | Needs safe ordering, streaming, repair, rollback |
| Backup/restore | Volume/storage primitives | Needs snapshots/manifests/commitlogs and restore plans |
| Repair/tombstone coverage | No built-in anti-entropy | Dedicated operator/service mechanism, must verify |

**Design recommendation:** For multi-node production, prefer an organization-supported Cassandra operator tested across the **Kubernetes + CSI + Cassandra + JDK + Java Driver** matrix. Use self-managed StatefulSets only if the team has strong Cassandra operations capability, runbooks, and HA/backup/repair sign-off.

## 6. Kubernetes lab: Headless Service and single-node StatefulSet

The following manifest **illustrates a single-node lab only**. It does not build a production-safe Cassandra cluster: it lacks auth/TLS, multi-rack topology, backups, an operator, HA, and repair policies, and has not been validated against a real CSI/image matrix. Never bump `replicas` to 3 and claim you have a production cluster.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: cassandra-headless
  namespace: cassandra-lab
spec:
  clusterIP: None
  publishNotReadyAddresses: true
  selector:
    app: cassandra-lab
  ports:
    - name: cql
      port: 9042
      targetPort: 9042
    - name: internode
      port: 7000
      targetPort: 7000
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
  namespace: cassandra-lab
spec:
  serviceName: cassandra-headless
  replicas: 1
  selector:
    matchLabels:
      app: cassandra-lab
  template:
    metadata:
      labels:
        app: cassandra-lab
    spec:
      terminationGracePeriodSeconds: 180
      containers:
        - name: cassandra
          image: cassandra:5.0 # Lab only; pin/verify exact version
          env:
            - name: CASSANDRA_CLUSTER_NAME
              value: cassandra-k8s-lab
            - name: CASSANDRA_DC
              value: dc1
            - name: CASSANDRA_RACK
              value: rack1
          ports:
            - containerPort: 9042
              name: cql
            - containerPort: 7000
              name: internode
          resources:
            requests:
              cpu: "1"
              memory: 3Gi
            limits:
              memory: 5Gi
          startupProbe:
            tcpSocket:
              port: cql
            periodSeconds: 10
            failureThreshold: 60
          readinessProbe:
            tcpSocket:
              port: cql
            periodSeconds: 10
            failureThreshold: 3
          volumeMounts:
            - name: data
              mountPath: /var/lib/cassandra
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: cassandra-lab-ssd
        resources:
          requests:
            storage: 50Gi
~~~

**Points to understand before using:**

1. Namespace `cassandra-lab` and StorageClass `cassandra-lab-ssd` must be created by authorized admins matching your CSI/backend; these are **example names**, not assumed to exist.
2. A single-pod StatefulSet creates a PVC named `data-cassandra-0` (from template/pod names). Never rename the StatefulSet, ordinals, or volume templates expecting to reuse data without a migration plan.
3. `publishNotReadyAddresses` aids pre-ready discovery yet does not make a cluster healthy. Understand DNS, broadcast/listen addresses, and Service behavior.
4. `tcpSocket 9042` proves only that a port accepts TCP, **not CQL auth, schema agreement, `NORMAL` status, or data correctness**.
5. This sample intentionally **omits `livenessProbe`** because CQL-latency-based liveness probes can trigger restart storms during GC/repair spikes. Production must design probes per verified operator guidance.
6. Memory/CPU/storage values here are **lab placeholders**, not production Cassandra sizing. Account for JVM heap, off-heap, page cache, disk growth, and OOMKilled risks.
7. Image env vars and data paths assume the reference image; verify the **entrypoint and effective `cassandra.yaml`**.
8. Single-node fits learning StatefulSets/PVCs yet should use **RF=1** and matching CL in the lab. Never test RF3 `LOCAL_QUORUM` on one node.
9. This manifest omits full cluster networking, auth/TLS, NetworkPolicies, security contexts, backups, operator hooks, and cross-zone behavior.

### 6.1. When to use an operator CR instead of a raw StatefulSet?

Cassandra operators typically define custom CRDs (such as the `CassandraDatacenter` family in some ecosystems), with schemas and options varying by operator/version. **Never invent an imaginary CRD manifest for production.** Always read the installed CRD schema and official docs for your chosen operator, verifying:

- Node counts, racks/DCs, and seed discovery.
- Storage mount paths, PVC templates, and reclaim behavior.
- Resource requests/limits and JVM tuning.
- Rolling upgrades, node replacement, and scaling policies.
- TLS/auth secrets, bootstrap health, and probes.
- Backups/restores, repair, monitoring, and maintenance windows.

If an option is unsupported by the operator, **never patch operator-managed StatefulSets directly**; reconciliation can overwrite changes or break controller invariants.

## 7. PersistentVolume, PVC, and StorageClass: choosing storage carefully

### 7.1. Properties to review

| Component | Question | Risk if wrong |
|---|---|---|
| **StorageClass provisioner** | Which CSI driver provisions volumes, and is its version tested? | Mount failures, broken snapshots/resizes |
| **volumeBindingMode** | `Immediate` or `WaitForFirstConsumer`? | PV provisioned in wrong zone; pod stuck Pending |
| **reclaimPolicy** | `Delete` or `Retain`? | Deleting PVC wipes volume or leaves orphaned PVs |
| **allowVolumeExpansion** | Does backend support online/offline expansion? | Disk nears full while PVC cannot expand as assumed |
| **accessModes** | What do RWO/RWOP/RWX actually support? | Mount conflicts / multi-pod attachment issues |
| **Topology constraints** | Which zones/nodes can access the volume? | Pod cannot reschedule to another zone despite spare CPU |
| **Performance profile** | IOPS, throughput, p99 I/O, queues, burst credits? | CQL p99 spikes despite low CPU |
| **Snapshot/backup** | What consistency level does CSI VolumeSnapshot offer? | Snapshot exists yet Cassandra cannot restore cleanly |
| **Encryption** | Encryption at rest, key rotation, KMS governance? | Policy breach or unmountable volumes on key issues |

### 7.2. WaitForFirstConsumer and topology

A StorageClass can set `volumeBindingMode: WaitForFirstConsumer` so volume provisioning aligns with the zone chosen by Pod scheduling. Conceptual example:

~~~yaml
# SCHEMA ILLUSTRATION ONLY; provisioner must be a real CSI driver name.
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cassandra-lab-ssd
provisioner: example.csi.driver.invalid
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: true
parameters:
  storageTier: ssd
~~~

**Do not apply** this snippet: provisioner and parameters are **fictitious**. It illustrates fields to inspect. Real StorageClasses vary by CSI driver and cloud provider.

**Immediate binding** can provision a volume before the scheduler picks a Pod location. With zone-bound storage, if pod affinity/rack mismatches the volume's zone, the pod stays Pending. **WaitForFirstConsumer** defers binding until scheduling, yet **still does not let a zone-A volume magically move to zone-B** once created.

### 7.3. Access modes: RWO is neither backup nor fencing

- **ReadWriteOnce (RWO):** permits read/write mount per storage/Kubernetes semantics, usually scoped to a node; **not a distributed lock protecting Cassandra node identity**. Multiple pods on the same node might still share RWO in certain setups.
- **ReadWriteOncePod (RWOP):** restricts a PVC to a single pod at a time where supported by Kubernetes/CSI versions; detach/attach and node replacement still require control.
- **ReadWriteMany (RWX):** even if supported by the backend, **never share one data directory across multiple Cassandra pods**.
- **ReadOnlyMany:** unusable for writing SSTables or commitlogs.

**Every Cassandra node must own its own dedicated data directory.** Two Cassandra processes writing to the same data directory risk corruption; RWX does not turn Cassandra into a shared-disk database.

### 7.4. ReclaimPolicy and PVC retention

Deleting a StatefulSet may retain PVCs depending on defaults and configuration/version. Deleting a **PVC** backed by a PV with `reclaimPolicy: Delete` can delete the underlying storage volume. With `Retain`, volumes require explicit cleanup/mapping and risk becoming orphaned.

Some Kubernetes versions support StatefulSet `persistentVolumeClaimRetentionPolicy` to control PVC retention on scale-down or deletion. **Never assume defaults or feature support are identical across clusters.**

Dangerous command:

~~~text
kubectl delete pvc data-cassandra-0
# DO NOT RUN in production just to "reset a pod."
# Can permanently delete the data volume depending on reclaim policy.
~~~

**Deleting a Pod** differs from **deleting a PVC**; **scaling down** differs from **decommissioning a Cassandra node**; **deleting a StatefulSet** differs from **wiping cluster data**. Verify retention and recovery policies for each case.

### 7.5. Local PV vs. cloud block disks

| Type | Pros | Trade-offs |
|---|---|---|
| **Local NVMe/PV** | Great IOPS/latency, direct hardware control | Node-bound PV; losing physical host can lose local data, requiring replace/rebuild |
| **Cloud zonal block** | Reattaches within zone, supports CSI snapshots | Zone-bound, attach latency, provisioned IOPS/throughput limits, cost |
| **Network block / SAN** | Backend replication per product, centralized abstraction | Tail latency/availability tied to network/storage service |
| **Object storage** | Ideal for backups, manifests, archives | Never mount object buckets directly as Cassandra data dirs |
| **Container layer / emptyDir** | Fast for labs, auto-cleaned | Unsuitable for durable SSTables/commitlogs |

**Storage volume replication** and **Cassandra RF** are separate layers; if both rely on the same backend or zone, they suffer **correlated failures**. Design zones/racks around real fault domains, not copy counts alone.

## 8. Topology: DC, rack, zone, and placement

In Cassandra, **DC/rack** governs placement and replication; in Kubernetes, **nodes, labels, zones, affinity, and topology spread** govern scheduling. Both layers must align cleanly.

~~~mermaid
flowchart LR
    A["Cassandra keyspace\nNTS dc1 RF3"] --> B["Replica A\nrack/zone-a"]
    A --> C["Replica B\nrack/zone-b"]
    A --> D["Replica C\nrack/zone-c"]
    B --> E["PVC/PV A\nstorage zone-a"]
    C --> F["PVC/PV B\nstorage zone-b"]
    D --> G["PVC/PV C\nstorage zone-c"]
~~~

### 8.1. Do not rely on `podAntiAffinity` alone

Pod anti-affinity keeps pods off the same host, yet does not automatically align Cassandra rack mappings, replica placement, and storage topology. Placing three pods on three separate worker nodes **inside the same zone** still leaves the cluster vulnerable to a single zone outage.

Verify:

- Node labels such as `topology.kubernetes.io/zone` / `region` and real scheduling policies.
- Cassandra DC/rack settings matching chosen topology failure domains.
- Enough **zones/nodes** for the policy; hard anti-affinity leaves pods Pending if capacity falls short.
- StorageClass/PV `nodeAffinity` does not conflict with pod placement.
- How the operator enforces rack placement and handles node replacements.

### 8.2. Example scheduling constraints

~~~yaml
# Illustrative FRAGMENT; not a complete production config.
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cassandra-lab
          topologyKey: kubernetes.io/hostname
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        app: cassandra-lab
~~~

**Preferred/`ScheduleAnyway`** does not guarantee zone separation when resources are tight. Using **required/`DoNotSchedule`** can leave pods Pending if a zone lacks capacity. Production policies must balance **hard fault-domain rules, PVC availability, and scheduler feasibility**.

### 8.3. A zone outage does not mean Kubernetes heals data automatically

With zonal PVs, a Pod bound to a zone-A PV cannot simply reschedule to zone-B if the volume cannot attach there. If the node/volume is truly lost, creating a fresh volume triggers **Cassandra node replacement/rebuild**—streaming and altering data on affected token ranges—never a routine pod restart.

**RF3/`LOCAL_QUORUM`** tolerates some replica loss if remaining replicas are healthy, yet poor rack/zone placement means one zone outage can break quorum. Run staging fault tests matching real RF/DC and measure p99/errors rather than checking Pod Ready alone.

## 9. Networking: stable names, discovery, and CQL routing

Cassandra uses distinct addresses and ports for CQL clients, internode traffic, and management. Common ports—**depending on version/config**—include:

| Connection | Common port | Notes |
|---|---:|---|
| **CQL native transport** | 9042 | Java Driver, TLS/auth, service discovery |
| **Internode communication** | 7000 | Do not assume internode TLS is enabled automatically |
| **Internode TLS** | 7001 | Configuration syntax can vary by version |
| **JMX management** | 7199 | Strictly restrict access; remote auth/TLS optional by version |
| **Metrics / sidecars** | Varies | Never expose publicly on the Internet |

**Never expose internode or JMX over a public LoadBalancer.** NetworkPolicies/firewalls must mirror exact Pod–Pod, app–CQL, operator–management, and backup/monitoring flows. If internode traffic fails, local `nodetool`/CQL health on one node does not prove the ring is healthy.

### 9.1. Headless Services do not replace seed configuration

A Headless Service provides stable Pod/Service DNS names aiding discovery, yet Cassandra still requires valid seed providers, broadcast/listen addresses, and network topology matching your image/operator.

- Never pick seed nodes casually from ephemeral Pod IPs.
- Never treat headless DNS as the authoritative list of ring replicas.
- Never set **localhost** as the broadcast address in a multi-node cluster.
- Never let two pods share a node identity/host ID or data directory via copied YAML.
- Verify DNS propagation, TTLs, and address translation for out-of-cluster clients.
- When a Pod IP changes while identity/volume persist, verify node join/gossip via supported procedures.

### 9.2. Kubernetes Service types

- **Headless Service:** commonly backs stable per-pod DNS and internal discovery.
- **ClusterIP Service:** can provide an internal entrypoint, yet token-aware drivers still need reachable node addresses discovered from cluster metadata for optimal routing.
- **LoadBalancer / Ingress:** does not naturally fit Cassandra's native protocol. TCP proxies/LBs and managed Cassandra offerings vary in discovery and TLS models; use supported solutions rather than putting HTTP Ingress in front of port 9042.
- **External clients:** need private networking, TLS/auth, and supported address translation/proxies if Pod IPs are non-routable. Never assume a single LB contact point makes all discovered nodes reachable.

### 9.3. Designing NetworkPolicies

Separate at minimum:

1. Java clients allowed to reach intended CQL endpoints.
2. Cassandra nodes allowed internode traffic in both directions on required ports.
3. Operators/monitoring granted scoped management/JMX access.
4. Backups granted egress to storage/KMS and DNS.
5. Kubernetes DNS / headless lookups unblocked.
6. Zero direct database exposure to public networks.

If a new deployment triggers `AllNodesFailedException`, inspect per-node errors (DNS/TCP/TLS/auth) and local DC instead of immediately raising Java Driver timeouts or running repair.

## 10. CPU, heap, off-heap, page cache, and cgroup memory

Cassandra consumes **JVM heap**, **off-heap/native memory**, filesystem page cache, and kernel buffers. Container memory limits cannot simply equal `-Xmx` ("4 GiB container so 4 GiB heap").

### 10.1. Memory has multiple consumers

| Component | Role | Risk |
|---|---|---|
| **Java heap** | Objects, memtables/metadata, JVM workload | Too large causes long GC pauses; too small causes pressure |
| **Off-heap / native** | Buffers, mmap/direct allocations, threads, native libs | RSS exceeds heap, causing OOMKilled |
| **Page cache** | Caches SSTable file pages | Insufficient RAM outside heap increases disk reads |
| **Filesystem / kernel / cgroup** | I/O buffers, networking, slab/cache accounting | OOM even before JVM heap fills |
| **Monitoring / sidecars** | Exporters, backup agents, proxies | Extra CPU/RAM usage and I/O contention |

A hypothetical **16 GiB** budget might allocate 6 GiB heap, 2 GiB native/off-heap, 5 GiB page cache, and 3 GiB headroom. This is not a universal formula across versions. In many environments page cache counts toward the container cgroup limit—**never treat it as free outside memory limits**. Monitor RSS, `memory.current`, GC pauses, OOM events, page-cache hits, and read p99.

### 10.2. CPU limits and throttling

- `requests.cpu` drives scheduling/capacity; `limits.cpu` can trigger CFS throttling even while the physical host has idle CPU.
- CPU-throttled JVMs suffer longer GC pauses, slower compactions, and higher CQL p99.
- Omitting CPU limits does not grant infinite CPU: quotas, host capacity, and noisy neighbors still apply.
- Monitor CPU throttled time, user/system CPU, GC, node pressure, and disk I/O.
- Raising requests/limits requires checking node/zone capacity so rack and volume placement stays intact.

### 10.3. QoS and eviction

Kubernetes enforces QoS classes and pressure-based evictions. **Guaranteed QoS does not prevent all evictions or OOMs.** Node-level disk pressure on container filesystems/`ephemeral-storage` can evict pods even while data PVCs have free space. PodDisruptionBudgets do not stop all evictions or node failures; once evicted, PV zone/node affinity may prevent immediate rescheduling.

## 11. Disk I/O and capacity: more than SSTables

~~~text
Commitlog writes
Memtable flush -> SSTables
Compaction -> read SSTables + write new SSTables
Repair validation & streaming
Bootstrap/rebuild streaming
Snapshots pinned SSTables + backup copy
Hints, temporary files, and container logs
~~~

A node storing **700 GiB of data** cannot run on a 710 GiB volume expecting compaction, repair, and snapshots to fit. Growth, SSTable rewrites, and retention all demand headroom.

### 11.1. Hypothetical capacity example

Usable volume 1 TiB, live data 650 GiB, growth before maintenance 100 GiB, compaction/streaming peak 180 GiB, snapshots pinning roughly 80 GiB of old SSTables:

~~~text
Peak demand    = 650 + 100 + 180 + 80 = 1010 GiB.
Usable ceiling = 1024 GiB.
Margin ~14 GiB, before filesystem metadata or incidents.
=> NO-GO for this maintenance profile until headroom improves.
~~~

With snapshot hard links, **do not add entire snapshot sizes as independent file copies**; 80 GiB here represents extra space pinned by uncompacted/old SSTables retained past compaction. Measure actual filesystem accounting, snapshot retention, and off-domain backup progress.

### 11.2. IOPS differs from bandwidth

SSDs with high MiB/s throughput can still bottleneck on random IOPS, queue depth, or p99 await. Monitor:

- Per-device read/write IOPS, throughput, await/latency, queue depth, and free bytes.
- Cloud storage provisioned IOPS, burst credits, and node-level attach throughput caps.
- SSTable counts, pending compactions, and flush/commitlog latencies.
- Cache misses, GC pauses, and node/pod cgroup throttling.
- Hot partitions/token ranges concentrating traffic on a specific node.

Never rely on cluster-wide average CPU to claim there is no disk bottleneck.

### 11.3. Should commitlog and data directories be separated?

Separating volumes can reduce I/O contention when backed by **genuinely independent devices/backends**, provided image/operator configs and backup/recovery workflows support it. Verify:

1. Do both volumes retain matching identities and reattach together on Pod restart?
2. Is the commitlog protected against pre-flush data loss?
3. Is there a clear recovery plan if either volume fails?
4. Does CSI support expansion and snapshots/restores for all volumes?
5. Do throughput, IOPS, and cost genuinely improve?

**Never move commitlog onto `emptyDir`** to save money when durability is required. Evaluate commitlog durability, CL, and workload RPO.

## 12. Startup, readiness, and liveness probes

### 12.1. Three distinct probes

| Probe | Question | Dangerous mistake |
|---|---|---|
| **`startupProbe`** | Has startup/replay finished enough to begin health checks? | Killing a node mid-bootstrap or commitlog replay |
| **`readinessProbe`** | Should the Pod receive traffic via Kubernetes Service? | Treating open TCP as healthy CQL/CL/schema |
| **`livenessProbe`** | Is the process truly dead/hung and needing restart? | Quorum timeouts triggering a restart storm |
| **Operator / Cassandra health** | Token/ring, `NORMAL` status, schema, and CQL health | Checking Pod Ready instead of node status |

**Open TCP 9042 proves only a listening socket**, not TLS/auth, schema agreement, `NORMAL` state, or latency. A `LOCAL_QUORUM` CQL check wired into `livenessProbe` can fail because *another* replica is slow, causing kubelet to repeatedly restart a healthy process.

Principles:

- Keep liveness conservative, tied to process liveliness/hangs rather than distributed SLOs.
- Align readiness with Cassandra-aware operator readiness; avoid heavy queries every second.
- Give `startupProbe` enough budget for realistic startup, commitlog replay, disk speed, and GC.
- On `CrashLoopBackOff`, `OOMKilled`, `ProbeFailed`, or `Evicted`, diagnose the exact cause instead of endlessly bumping timeouts.
- Never let probes trigger repair, rebuild, or topology mutations.

### 12.2. Termination and draining

Kubernetes runs `preStop` hooks, sends termination signals, and enforces `terminationGracePeriodSeconds`. Cassandra drain/shutdown/flush behavior depends on version and operator.

- Give termination grace enough room for clean shutdown, without assuming it always completes in time.
- `preStop` consumes part of the grace period; overly long hooks still get killed by Kubernetes.
- `nodetool drain` has real side effects—do not inject it blindly into YAML without understanding image/operator shutdown hooks.
- Node maintenance differs from node replacement; not every Pod termination should trigger decommission.
- After forced terminations, Cassandra replays commitlogs; inspect ring state, disk, CL, and data correctness.

Never use `terminationGracePeriodSeconds=0`, force-delete, or `kill -9` as routine upgrade steps.

## 13. PodDisruptionBudgets, node drains, and rolling upgrades

### 13.1. PodDisruptionBudgets do not understand Cassandra quorum

A PodDisruptionBudget (PDB) limits certain voluntary disruptions via the **Kubernetes Eviction API**. Staging 3-pod example:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-staging-pdb
  namespace: cassandra-staging
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: cassandra-staging
~~~

**Do not apply directly to production.** `minAvailable=2` does not guarantee every partition in every DC/rack retains enough replicas for `LOCAL_QUORUM`. PDBs do not prevent all Pod deletions, node failures, OOMs, zone outages, or operator actions.

### 13.2. Kubernetes node drain runbook

1. Identify Cassandra pods, PVC/PV handles, node/zone affinity, and operator ownership.
2. Verify replica availability, RF/DC/CL, and application error budgets.
3. Check PDBs, eviction policies, and maintenance windows.
4. Let the Cassandra-aware operator coordinate shutdown/relocation using tested procedures.
5. Monitor PV detach/attach, Pod restarts, gossip, and token ownership.
6. Track Java client successful RPS, p95/p99, timeouts, and `Unavailable` counts.
7. Move to the next worker node only after health gates pass.

**Node drain differs from Cassandra decommission.** A Pod may migrate keeping its existing PVC and identity; leaving the Cassandra ring permanently requires decommission or replace/rebuild with streaming and verification per runbook.

### 13.3. Version-aware rolling upgrades

- Review compatibility matrices and release notes across Cassandra, JDK, Java Driver, operator, CSI, and Kubernetes.
- Hold verified backup manifests/checksums, restore drills, and realistic rollback plans; downgrades after SSTable/commitlog format changes **are not automatically safe**.
- Validate CQL prepared statements, TLS/auth, RF/CL, LWTs, and disk/GC in staging/canary.
- Update **one Cassandra failure domain at a time** per runbook; never run blind rolling updates that break quorum.
- Verify UP/NORMAL status, schema agreement, token placement, disk, compaction, and application SLO before advancing.
- Avoid unapproved overlap with heavy repair/backup/bootstrap; enforce clear GO/PAUSE/STOP gates.

StatefulSet `RollingUpdate` is only a Kubernetes primitive; it **lacks awareness** of Cassandra node identity, SSTable versions, and ring safety.

### 13.4. Cassandra does not autoscale like a Java API

HPA scaling out Java pods can suddenly spike Cassandra in-flight requests. Raising StatefulSet `replicas` does not guarantee safe bootstrap/token/streaming/rack placement; lowering `replicas` does not safely decommission nodes. Scaling Cassandra requires an **operator/DBA capacity plan** covering PVCs/zones, RF/DC, streaming, repair, and rollback.

## 14. Node identity: Pod restart, node replacement, and PVCs

| Scenario | Assessment | Procedure |
|---|---|---|
| **Pod restarts with same PVC and node identity** | Can resume as same node if data intact | Startup/replay, verify ring/CQL |
| **Pod IP changes while PVC/host ID preserved** | Valid depending on discovery/broadcast config | Verify gossip and token ownership |
| **PVC mounted to wrong ordinal** | Risk of identity/data corruption | STOP, preserve evidence, involve DBA |
| **PVC lost/corrupt, empty volume attached** | Needs node replacement/rebuild, not plain restart | Follow operator/version runbook |
| **Zonal PV cannot attach** | Disk cannot jump zones automatically | Storage recovery or node replacement |
| **Scaling down Cassandra** | Never just delete Pod/PVC | Decommission with data handoff |
| **Restoring SSTables from old snapshot** | Risks losing newer writes or resurrecting deletes | DR and reconciliation |
| **Two pods writing to same data dir** | Corruption risk | Block immediately; enforce single writer/identity |

### 14.1. Capture evidence before acting

~~~text
Kubernetes: namespace, Pod UID/name, StatefulSet ordinal
Scheduler : worker node, zone, taints, and affinity
Storage   : PVC UID, PV name, CSI volume handle, mount path
Cassandra : host ID, tokens, DC/rack, node status
Recovery  : snapshot/backup manifest, operator run ID
~~~

Never manually edit host IDs, modify system tables, rename data directories, or delete PVCs experimentally. Node C's volume does not become a valid replica D just because a new pod shows Ready.

### 14.2. Three health layers must agree

~~~text
Kubernetes:
  Pod Running / Ready; PVC Bound / Mounted

Cassandra:
  Node UP/NORMAL; schema agreement; token ownership
  Streaming/repair/compaction; DC/rack

Java Application:
  CQL successful throughput; p95/p99; timeout/error rate
  Data correctness by partition key and CL
~~~

One green layer does not prove the whole system is safe. Automation must cross-check all three before opening traffic, advancing waves, or deleting recovery points.

## 15. CQL: verifying RF, partition-keyed tables, and consistency

A **multi-node lab** cluster with RF=3 in `dc1` can use:

~~~sql
-- Only for labs with enough replicas in dc1.
CREATE KEYSPACE IF NOT EXISTS k8s_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS k8s_lab.events_by_tenant_day (
  tenant_id uuid,
  event_day date,
  happened_at timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (
  happened_at DESC, event_id ASC
);

INSERT INTO k8s_lab.events_by_tenant_day (
  tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21',
  '2026-11-21T08:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'LAB_WRITE',
  'synthetic'
);

SELECT happened_at, event_id, event_type
FROM k8s_lab.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

**Table design:** Partition key `(tenant_id, event_day)` collocates data by tenant and day; clustering columns sort newest events first. If one tenant/day gets too hot, shard/bucket per query pattern. Never run `ALLOW FILTERING` or cluster-wide table scans as routine health checks.

**Important:** the single-node lab YAML in Section 6 cannot satisfy an RF3 keyspace. On a 1-node lab, use RF1 and matching CL; an RF1 test proves basic CQL only, never HA or multi-node quorum. Never alter production RF just to make tests pass.

### 15.1. Read schema options instead of guessing

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'k8s_lab';

SELECT keyspace_name, table_name, gc_grace_seconds,
       default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'k8s_lab';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'k8s_lab'
  AND table_name = 'events_by_tenant_day';
~~~

One coordinator's metadata snapshot does not prove cluster-wide **schema agreement**. During topology changes or upgrades, inspect nodes/ring, pending migrations, and effective keyspace settings.

### 15.2. RF/CL and availability under node churn

| Condition (RF3 single DC) | `LOCAL_ONE` | `LOCAL_QUORUM` |
|---|---|---|
| 3 healthy replicas | Can succeed | Normally needs 2/3 local replicas |
| 1 replica DOWN | Can succeed | Can succeed if other two respond fast enough |
| 2 replicas DOWN | Some requests may still succeed on surviving replica | Likely `Unavailable`/timeout |
| Nodes UP yet disk/GC saturated | May still time out | May still time out |

This simplified illustration of CL replica satisfaction is not a guarantee every request succeeds. Local quorum in `dc1` **does not prove data synchronized to other DCs**.

### 15.3. TTLs, tombstones, and post-restart healing

Cassandra may run commitlog replay, compaction, or streaming after restarts/replacements. **TTL expiration**, tombstone grace, and repair coverage still apply; never run major compaction "just to be sure data is right." Compaction is not anti-entropy repair, and repair does not replace backups.

## 16. Java Driver 4.x: matching local DC without masking cluster errors

Java services may run in the same Kubernetes namespace, a different namespace, an external VPC, or behind a managed Cassandra endpoint. Connection paths and address discovery must reflect reality.

### 16.1. Using a single `CqlSession` with an explicit lifecycle

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CassandraK8sReadProbe {
    public static void main(String[] args) {
        // LAB ONLY: configure TLS/auth/secrets for real deployments.
        // Contact point and DC must match environment and routing.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress(
                        "cassandra-headless.cassandra-lab.svc", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM k8s_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement query = select.bind(
                    UUID.fromString(
                        "11111111-1111-4111-8111-111111111111"),
                    LocalDate.parse("2026-11-21"),
                    20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            Row first = session.execute(query).one();
            System.out.println(
                first == null ? "no row in this read" : "row observed");
        }
    }
}
~~~

**Critical warning:** on a 1-node lab, never run `LOCAL_QUORUM` assuming RF3 quorum tolerance. This example targets a **multi-node RF3 lab**. For out-of-cluster clients, headless DNS/pod IPs may be non-routable; use supported contact points and driver address translation/proxies.

### 16.2. Java Driver settings to review

| Setting | Risk |
|---|---|
| **Contact points** | Unroutable service DNS/IP, wrong cluster, or wrong port |
| **Local datacenter** | Mismatches Cassandra DC, yielding zero eligible nodes |
| **TLS/mTLS** | Invalid truststore, hostname verification, or client certs |
| **Authentication** | Secret rotation mismatch or wrong role/permissions |
| **Execution profiles** | CL, request timeout, or serial consistency/LWT diverges from contract |
| **Connection pools** | In-flight requests surge after Java API scale-out |
| **Retry policy / speculation** | Retries amplify load when disks/repairs run slow |
| **Routing key / prepared statements** | Queries missing partition key lose token-awareness |
| **Session lifecycle** | Creating a `CqlSession` per HTTP call causes connection churn |

Java Driver 4.x classes live under `com.datastax.oss.driver.api`. Pin versions and compile against real dependencies; never deploy plaintext non-TLS examples into untrusted environments.

### 16.3. Classify errors instead of turning failures into "no data"

- **`AllNodesFailedException`:** inspect tried nodes and causes via `getAllErrors()`; may indicate DNS, TLS, auth, or port blocks rather than all Cassandra replicas being DOWN.
- **`DriverTimeoutException`:** driver missed its deadline; does not prove a mutation failed to apply.
- **`ReadTimeout`/`WriteTimeout`/`Unavailable`:** check coordinators/replicas, RF/CL, node health, disk/GC, and topology.
- **`OverloadedException`:** shed load; never retry infinitely immediately.
- **Connection reset after write:** outcome may be UNKNOWN; reconcile idempotently by business key.

**Never catch every exception and return an empty result.** A timed-out query differs completely from a successful read returning zero rows. During migration/restore tests, swallowing errors creates false "missing data" alarms.

### 16.4. Measure before and after maintenance

Compare **offered requests, successful RPS, p50/p95/p99, timeout/error rates, in-flight/retries, and correctness** from the Java service. Do not look solely at Pod Ready or Cassandra throughput. Tag every PV/topology/repair change with a run ID and timestamps for metric correlation.

## 17. Backup, snapshot, and restore: persistent PVCs are not enough

### 17.1. Concepts not to conflate

| Mechanism | Protects against | Does not protect against |
|---|---|---|
| **Cassandra RF** | Certain replica/node failures per topology/CL | Accidental DELETEs, full fault-domain loss, logical corruption |
| **PVC/PV** | Container filesystem loss on pod replacement, per backend | PVC/PV deletion, backend outages, zone/region loss |
| **Cassandra snapshot** | SSTable recovery point per snapshot method | Automatic offsite copies or full PITR |
| **CSI VolumeSnapshot** | Volume-level snapshot if driver supports | Cluster-wide Cassandra logical consistency |
| **Remote backup + manifest/restore drill** | Off-fault-domain recovery per tested policy | Measured RPO/RTO until actually drilled and verified |

Backing up Cassandra involves **SSTable snapshots, schema/topology, commitlog archiving if PITR, incremental backups, checksums/manifests, and encryption/KMS**. Local snapshots rely on hard links and keep old SSTables from being reclaimed by compaction, raising disk usage over time.

### 17.2. CSI VolumeSnapshots are block-level snapshots

A VolumeSnapshot captures a point-in-time copy of one PVC. Yet Cassandra writes SSTables and commitlogs concurrently across multiple replicas and volumes. Snapshotting a single volume offers at most backend **crash consistency**, not cluster-wide CL consistency.

If DR requires snapshot consistency, use Cassandra-aware tooling or workflows coordinating version-compatible data/commitlog/manifests, paired with **isolated restore drills**.

### 17.3. Separate backups from the same fault domain

- Backups residing on the pod's PVC → still vulnerable to volume/node/zone loss.
- Backups uploaded over private networking to object storage with IAM/KMS/retention → stronger fault isolation, still requiring checksums and restore verification.
- Snapshot metadata lacking schema/manifests → hard to restore cleanly across topologies/versions.
- Restoring old snapshots can reintroduce deleted data or miss post-cutoff writes; plan **reconciliation**, especially for privacy-mandated deletions.

### 17.4. RPO and RTO must be measured

- **RPO:** maximum data age tolerable in an outage.
- **RTO:** elapsed time to restore compliant serving capability.

Measure RPO/RTO through **recovery drills**, not snapshot speed estimates. Include Kubernetes/CSI provisioning, SSTable download, schema restore, node startup, repair/rebuild if needed, CQL verification, Java API checks, and post-cutoff deletion reconciliation.

### 17.5. Never delete PVCs before backups are verified

During an incident where a volume sticks in Pending or mount fails, operators may be tempted to "delete and recreate the PVC." That can trigger `reclaimPolicy: Delete` and destroy recovery points. Verify the PVC→PV→CSI volume mapping, storage health, backup manifests, and DBA runbooks before any destructive action.

## 18. Container and Kubernetes operational security

Cassandra stores sensitive data and metadata; Pods, PVCs, and backups can themselves leak data. Security design must cover **identity, network, images, storage, and logs**.

### 18.1. Images and supply chain

- Pin approved image versions/digests; scan CVEs and update against compatibility matrices.
- Never deploy unpinned `latest` tags in production; tags can change bytes between rollouts.
- Use private registries and `imagePullSecrets` where needed, separating pull rights from cluster-mutation rights.
- Check entrypoints, UID/GID, mount paths, JVM version, and native libraries on image updates.
- Never let containers fetch unverified config or certificates over the network at startup.
- Test rolling upgrades in staging with real SSTables/commitlogs, not just successful image pulls.

### 18.2. Runtime users and filesystem permissions

A fresh volume may have ownership/mode differing from Cassandra's UID/GID. Typical symptom: Pod `CrashLoopBackOff` complaining it cannot write data/commitlog.

- Know which UID runs inside the image and what filesystem permissions it needs.
- Configure `securityContext.runAsUser`/`fsGroup` only with full understanding of image UID/GID, CSI driver behavior, and `fsGroup` recursive behavior.
- Never blindly `chown` multi-terabyte SSTable trees on every Pod restart: it causes huge startup delays or wrong ownership.
- Never make containers `privileged` just to bypass mount errors; fix CSI, security policies, and init permissions properly.
- Root filesystems can be read-only if logging/temp paths are prepared; never flip it blindly and break Cassandra runtime writes.
- Verify read/write mount modes and confirm data directories actually land on the PVC.

### 18.3. TLS and secrets

| Channel | Requirements to evaluate |
|---|---|
| **Java client ↔ Cassandra** | TLS/mTLS, hostnames/cert chains, auth roles, keyspace/table grants |
| **Internode** | Encryption, trust/rotation, matching seed/broadcast addresses |
| **JMX / management** | Network isolation, auth/TLS per version, zero public exposure |
| **Backup / KMS / Object store** | Least-privilege IAM, encryption, retention, and auditing |
| **Kubernetes Secrets** | Namespace RBAC, encryption at rest, zero secret logging, rotation |
| **Operator service account** | Scoped strictly to Cassandra CR/PVC/Pods; audit changes |

Base64-encoded Kubernetes Secrets **do not constitute encryption**. Enforce etcd encryption, external secret stores/KMS, and strict Secret RBAC. Never hardcode usernames, passwords, or keystore private keys in ConfigMaps, Git YAML, or lab manifests reused in real environments.

### 18.4. NetworkPolicies and security boundaries

NetworkPolicies must allow Cassandra internode traffic, app CQL, operator/JMX, monitoring, backups, and DNS while blocking unneeded workloads. Overly strict policies leave Pods Running while CQL fails; overly broad policies expose unauthorized access.

If `AllNodesFailedException` hits Java right after adding a NetworkPolicy, inspect per-node causes (DNS, TCP, TLS, auth) instead of assuming data corruption and running repair.

## 19. Observability: correlate Kubernetes and Cassandra on the same timeline

### 19.1. Read-only Kubernetes commands

The following are **read-only** examples on the lab namespace requiring view permissions:

~~~bash
# Check pods, nodes, and scheduling placement.
kubectl -n cassandra-lab get pods -o wide

# StatefulSet replica status and rollout info.
kubectl -n cassandra-lab get statefulset cassandra -o wide

# PVC bound/pending state and storage class.
kubectl -n cassandra-lab get pvc -o wide

# Volume/PVC events and attach/mount errors.
kubectl -n cassandra-lab describe pvc data-cassandra-0

# Pod scheduling, probes, restarts, and OOM/eviction events.
kubectl -n cassandra-lab describe pod cassandra-0

# Pod logs; requires permission and must not leak secrets.
kubectl -n cassandra-lab logs cassandra-0 -c cassandra --tail=100

# Inspect voluntary disruption budget configuration.
kubectl -n cassandra-lab get pdb
~~~

**Note:** Pod/PVC names match the Section 6 manifest; operators may name objects differently. Never copy commands assuming production namespaces match. Avoid mutating commands (`delete`, `patch`, `scale`, `rollout restart`) during observation.

### 19.2. Cassandra health inspection commands

Per your running version's syntax and permissions:

~~~bash
# Cassandra gossip/ring, DC/rack, and node states.
nodetool status

# Node/resource information.
nodetool info

# Pending/dropped thread pool tasks.
nodetool tpstats

# Active compactions.
nodetool compactionstats

# Streaming/network sessions.
nodetool netstats

# Table statistics.
nodetool tablestats k8s_lab.events_by_tenant_day

# Partition/row size distribution if supported by version.
nodetool tablehistograms k8s_lab events_by_tenant_day

# Snapshot retention.
nodetool listsnapshots
~~~

**`nodetool status` `UN` does not imply healthy CQL latency or complete repair.** Operators may also expose custom metrics/JMX/Prometheus endpoints whose names vary by version/exporter. Never invent metric names assuming they exist on the cluster.

### 19.3. Metric matrix

| Layer | Signals | Question |
|---|---|---|
| **Kubernetes scheduling** | Pending, node affinity, zone spread, taints, events | Does the Pod have a valid place to run? |
| **CSI storage** | PVC/PV status, attach/detach, mount errors, volume latency | Is the volume durable and attached cleanly? |
| **Pod / container** | Restart counts, OOMKilled, CPU throttling, memory RSS, ephemeral disk | Is the container throttled or killed? |
| **Cassandra node** | Gossip status, host ID, token/DC/rack, CQL readiness | Are identity and topology valid? |
| **Cassandra storage** | SSTables, commitlogs, compaction, disk free/await | Are reads/writes/repairs I/O-bottlenecked? |
| **Repair / streaming** | Active sessions, progress, failed ranges, bytes | Is synchronization covering the scope? |
| **Java application** | Offered/successful RPS, p95/p99, retries, failures | What SLO do users experience? |
| **Correctness / DR** | Fixture reads/writes, backup manifests, restore RPO/RTO | Is data intact and recoverable? |

### 19.4. Timeline from change to impact

~~~text
T0: Baseline CQL p99, successful RPS, and node health stable
T1: Change window opens; Pod rollout or volume operation starts
T2: PVC attach/mount, Pod startup
T3: Cassandra node UP/NORMAL, token/rack verified
T4: Streaming/repair/compaction activity if triggered
T5: Java application p99/errors return within bounds
T6: Backup/checksum and correctness verification complete
~~~

**Never declare completion at T2** merely because the Pod is Ready; verify data correctness and recovery windows whenever storage or topology changed.

## 20. Diagnostic runbooks by Kubernetes/storage symptom

### 20.1. Pod Pending, PVC Pending

**Symptom:** Pod cannot schedule, PVC stays Pending, or volume provisioning is rejected.

Check:

1. `kubectl describe pod/pvc`: provisioning, zone, quota, missing StorageClass, or permission events.
2. Whether the StorageClass provisioner/CSI driver exists and is healthy.
3. Whether `volumeBindingMode` and zone/node affinity match scheduler constraints.
4. Capacity/IOPS quotas, volume count limits, and account permissions.
5. Any stale PVC or retained PV needing mapping cleanup after an earlier incident.

**Never delete a PVC** just to retry without checking reclaim policies and attached data. If an old PV holds real data, provisioning a fresh volume turns a node restart into a node replacement.

### 20.2. Pod Pending due to PV zone affinity

**Symptom:** PVC is Bound yet the Pod cannot schedule in a zone.

- Inspect PV `nodeAffinity`/topology labels, worker node availability, and pod affinity/anti-affinity.
- Verify whether the PV is zonal/local and can reattach within the same zone.
- Never "strip affinity" to force-mount a volume across zones if the backend forbids it.
- If a zone is permanently lost, execute storage recovery or DBA node replacement/rebuild—not a stateless pod move.

### 20.3. `CrashLoopBackOff` after mount

**Symptom:** Container restarts repeatedly; logs report permission denied or corrupt startup files.

- Read full startup logs and last termination reason rather than just the final line.
- Verify actual mount paths, UID/GID/`fsGroup`, filesystem permissions, and free disk.
- Confirm which node identity's SSTables/commitlogs reside on the volume.
- Separate JVM heap/off-heap/`OOMKilled` from permission errors.
- Never alter UIDs, `chown` whole data trees, or manually delete system keyspaces without DBA approval.

### 20.4. Disk full despite recently expanding PVC

**Symptom:** PVC size increased yet filesystem available bytes did not; or snapshots/compaction pin lots of files.

- Confirm CSI/backend supports expansion and filesystem resizing completed.
- Check whether the Pod/filesystem sees new capacity or resize is pending remount.
- Check snapshot-pinned SSTables, compaction backlogs, commitlogs, and logs on separate filesystems.
- Never delete snapshots before external backups are verified.
- Never force compaction on a nearly full disk because compaction needs temporary space.

### 20.5. `AllNodesFailed`/`DriverTimeout` after Service or NetworkPolicy change

**Symptom:** Java service fails CQL connections or times out after Pod IPs change.

- Check contact points, DNS/headless service records, local DC, and address discovery.
- Inspect per-node causes in `AllNodesFailedException.getAllErrors()`: `ConnectException`, TLS/PKIX, auth, init timeouts.
- Check Cassandra CQL listeners, internode networking, query plans, and replica availability.
- Compare request timeouts against pools, admission, GC, and server read/write latencies.
- Never lower CL or raise retries infinitely to hide connectivity failures.

### 20.6. Node UP, yet Java read p99 spikes after replacement

- Check active streaming, repair, compaction, disk queues, networking, and GC.
- Inspect the new node's token/rack ownership, partition key distribution, and hot partitions.
- Measure offered vs. successful RPS and retry/speculative-execution amplification.
- Throttle maintenance per operator runbooks and admission controls while protecting SLO gates.
- Never assume "adding a node immediately speeds up APIs," since bootstrap temporarily increases I/O.

### 20.7. Suspected stale data when an old volume returns

If a node/volume was disconnected longer than tombstone grace and returns with old SSTables, missed deletes whose tombstones may have purged risk zombie resurrection.

- **PAUSE** returning the stale node to service when required by runbook.
- Inspect `gc_grace_seconds`, repair coverage, outage duration, compaction, and mutation audits.
- Never assume a single repair run restores lost deletions.
- Let the DBA decide quarantine, rebuild, replace, or reconciliation from business sources of truth.
- Preserve backups and incident evidence; avoid hasty actions that wipe valid newer data.

## 21. Environment-specific test scenarios

### 21.1. Layer tests across tiers

| Test tier | Goal | Does not prove |
|---|---|---|
| **Docker single-node** | Named volume persistence, prepared CQL, container restarts | RF3, quorum, zone failures |
| **Kubernetes single-node lab** | PVC binding/mounting, Pod recreation, Startup/Readiness | Node replacement and multi-replica repair |
| **Same-zone multi-node staging** | Token-aware routing, RF/CL, operator bootstrap/repair | Full-zone outage tolerance |
| **Multi-zone staging** | Scheduling/PV topology, zone outage, quorum, operator failover | Multi-region WAN/DR if single-region |
| **Multi-DC DR lab** | DC placement, local consistency, backup/restore/reconciliation | Production has identical latency/capacity |
| **Java end-to-end load** | HTTP/CQL p95/p99, retries, errors, correctness | Data restorability without restore drills |

**Rule:** Lower-tier tests are necessary, never sufficient for HA/DR. Results depend on exact image, operator, CSI, Kubernetes, and Cassandra versions, DC/rack, RF/CL, data size, and live load.

### 21.2. Test A — Recreate Pod while preserving PVC

On a **single-node lab** with a PVC and synthetic data:

1. Preflight schema, PVC/PV names, Pod ordinal, and volume handle.
2. Write a deterministic primary-key CQL row and read it back.
3. Restart the Pod using a **lab-approved mechanism** without deleting the PVC.
4. Wait for startup; verify it mounted the **exact same PVC**, inspect logs, and check the effective Cassandra data directory.
5. Read back the row by PK; record result and recovery duration.
6. Compare node identity/host ID before and after if supported by tooling.
7. Confirm no other Pod mounts the same data directory.

**PASS scope:** proves data survives Pod recreation on that storage backend. Does not prove host/zone failures or corruption recovery.

### 21.3. Test B — Zonal PVC/PV behavior

In multi-zone staging:

1. Record zone labels for each worker, StorageClass, and PV `nodeAffinity`.
2. Verify Pod distribution and Cassandra rack placement.
3. Simulate a worker drain or zone outage per runbook with a rollback plan.
4. Observe whether the Pod keeps its PVC in the original zone or undergoes valid operator replacement.
5. Measure quorum/CL, CQL errors, network/streaming, and disk.
6. Never manually edit PV `nodeAffinity` just to "make the Pod run" during a fault.
7. Mark **FAIL/NO-GO** if prolonged Pod Pending breaks quorum or SLO targets.

### 21.4. Test C — One replica lost under RF3/`LOCAL_QUORUM`

On a **real RF3** staging cluster, simulate losing one replica per approved fault-injection plan:

- Issue partition-key CQL `SELECT`/`INSERT` at target CL.
- Measure successful RPS, p99, and errors.
- Confirm the other two replicas are genuinely live in that DC.
- Restore the replica; observe streaming/repair and data.
- Run repair via the operator if required by runbook, never unlimited ad-hoc full repairs.
- Avoid creating counter/list-append side effects on retries.

**Conditional PASS:** app met SLO and correctness under the tested fault profile. Does not prove arbitrary topologies or two simultaneous down replicas are safe.

### 21.5. Test D — CSI VolumeSnapshots and restore drills

1. Create a backup via supported workflows, capturing manifest/schema/commitlog policies.
2. Verify snapshots, uploads, checksums, and KMS access.
3. Restore into an **isolated** cluster matching version, schema, and RF plan.
4. Run sample partition-key queries checking for duplicate or missing rows.
5. Measure real RPO/RTO including volume provisioning, data copy, node startup, and service readiness.
6. Verify **valid DELETEs after the backup cutoff** will be reconciled if restoring into production workflows.
7. Never restore an old snapshot over a live serving cluster just to test.

### 21.6. Test E — Controlled PVC expansion

- On a lab volume, review StorageClass `allowVolumeExpansion` and CSI docs.
- Increase size through the approved workflow and watch PV/PVC conditions.
- Confirm the filesystem and Pod recognize the expanded capacity.
- Check I/O performance before/after, backup snapshots, and free disk.
- Never assume larger PVCs automatically multiply IOPS unless the backend guarantees it.
- Document rollback constraints; shrinking PVCs is rarely a simple supported operation.

### 21.7. Test F — Probes under maintenance load

Run a bounded-concurrency Java load generator alongside repair/backup in staging:

~~~text
Baseline:
  success RPS, p95/p99, errors, disk await, and GC

Maintenance:
  repair/streaming or backup copy per runbook

Probe checks:
  startup does not kill a node still replaying
  readiness does not return false positives
  liveness does not restart a node merely due to slow quorum
  app error budget and disk headroom stay within bounds

Recovery:
  Node NORMAL, repair/compaction backlogs settle
  CQL correctness and p99 return to baseline
~~~

If **liveness** triggers a restart storm, mark FAIL and fix probe policies with the operator before continuing. Never relax SLO thresholds mid-test just to report green.

## 22. Environment-driven decision scenarios

### 22.1. StorageClass has capacity, yet not enough zones

**Context:** Design calls for RF3 across three distinct racks/zones, yet the Kubernetes cluster spans only two zones.

**Risk:** Hard spreading leaves Pods unschedulable; soft spreading packs two replicas into one zone, where losing that zone breaks quorum.

**Action:** **NO-GO** for unmet fault-domain requirements; add zones/capacity or redesign with approval. Never strip anti-affinity just to get "all Pods Running" and call it HA.

### 22.2. Local NVMe is fast, yet a worker node fails

**Context:** Cassandra uses local NVMe PVs and a physical host dies permanently; the Pod stays Pending due to PV `nodeAffinity`.

**Risk:** Local disks cannot reattach to another worker like zonal network volumes; on-node data is gone.

**Action:** RF/quorum and backups must supply recovery. DBA/operator executes version-appropriate node replacement/rebuild—never attach an empty PVC and treat it as a Pod restart. Measure streaming cost, data correctness, and recovery time.

### 22.3. Cloud block volume is healthy, yet the pod cannot attach

**Context:** Worker replaced, PVC Bound, zonal volume intact, yet attach hangs.

**Risk:** Multi-attach conflict, finalizer/CSI controller bug, wrong-zone scheduling, or stale attachment.

**Action:** Gather PVC/PV/CSI events, node/zone, volume handle, and operator logs. Coordinate safe detach/attach with the storage owner. Never force-detach while a writer still holds the volume, and never delete the PVC/volume.

### 22.4. Low CPU, yet reads are very slow

**Context:** Pod CPU sits at 30%, app p99 tripled, disk await is high, and compaction backlog is large.

**Analysis:** I/O is the bottleneck; raising Java heap or scaling API Pods can worsen it. Inspect StorageClass IOPS/throughput, tombstones, partition skew, compaction/repair, and page cache.

**Action:** Throttle background jobs per runbook, tune I/O capacity and data models, and re-measure with unchanged load and CL.

### 22.5. Same PVC, yet host ID changed unexpectedly

**Context:** After a container image update, the Pod mounts its old PVC, yet Cassandra joins as a brand-new node in the ring.

**Risk:** The new image changed data directory paths, an init script created fresh system keyspaces in the container layer, or identity mapping broke.

**Action:** STOP further rollout; check effective directories, PVC mounts, host ID/tokens, startup logs, and backups. Never delete the old node in gossip or manually edit system tables on a hunch.

### 22.6. Local snapshots are fast, yet disk is filling up

**Context:** Daily cron snapshots write to the same PVC, remote uploads occasionally fail, and compactions pile up.

**Analysis:** Snapshot hard links pin old SSTables so disk space is never reclaimed, while offsite backups remain unverified.

**Action:** Verify remote manifests/checksums, fix upload jobs, enforce retention, and alert on free disk. Clean local snapshots only when policy/owners permit; never delete the last recovery point.

### 22.7. Java pod scale-out drives Cassandra `Overloaded`

**Context:** HPA scales an API service from 10 to 50 replicas; every Pod opens pools and fires requests at Cassandra.

**Risk:** Traffic spikes, pools/in-flight requests and retries climb, and `Overloaded`/`DriverTimeout` errors appear even though Cassandra did not change.

**Action:** Enforce admission control, bounded per-tenant concurrency/rates, driver session reuse, retry budgets, and capacity planning—do not blindly 5x Cassandra immediately, since bootstrapping also consumes disk and network.

### 22.8. Pods Ready, yet queries in one DC fail with `Unavailable`

**Context:** Kubernetes dashboard is green, Java runs in `dc2`, while `dc2` lacks sufficient RF or uses the wrong local DC.

**Analysis:** Kubernetes readiness differs from CL/replica availability. Check NTS replication, per-DC Cassandra node states, driver local DC, gossip, and repair/streaming.

**Action:** Fix topology/config through change control while preserving the consistency contract; never lower `LOCAL_QUORUM` just to clear dashboard errors.

## 23. GO / PAUSE / STOP / ESCALATE rules

### 23.1. Gate table for rollouts and maintenance

| Gate | GO when | PAUSE / STOP when |
|---|---|---|
| **Backup** | Recent verified/restored backup per policy | No recovery point for a risky change |
| **Topology** | DC/rack/replica health satisfies approved criteria | Quorum lost, conflicting token placement |
| **Storage** | PVC identity matches, disk/headroom/IOPS sufficient | Wrong mount, disk full, CSI attach error |
| **Client SLO** | Successful RPS, p95/p99, errors within bounds | Error budget or timeouts breached |
| **Repair/streaming** | No unresolved failed ranges/sessions | Stale replicas, unexplained partial repair |
| **Image/version** | Compatibility matrix and staging pass | No feasible downgrade/rollback plan when needed |
| **Security** | TLS/auth/RBAC/secret rotation valid | TLS disabled or secrets exposed |
| **Correctness** | Fixture data and invariants verified | Missing/duplicate data, suspected corruption |
| **Fault domain** | Volumes/Pods/racks/zones align with policy | Co-located replicas violate policy |

### 23.2. Illustrative threshold profile

~~~yaml
example_policy_not_production_defaults:
  api_read_p99_max_ms: 250
  logical_error_rate_max_percent: 1
  min_successful_rps: 900
  min_disk_free_percent: 20
  required_backup_restore_drill_passed: true
  no_unresolved_volume_identity_mismatch: true
  no_unverified_repair_failures: true
  rolling_max_nodes_per_failure_domain: 1
  require_topology_and_schema_agreement: true
~~~

Thresholds **250 ms, 900 RPS, 20%** are examples only. Real numbers must come from SLOs, data/disk growth forecasts, RF/CL, and your storage backend. A free-disk percentage threshold never replaces **absolute gigabytes** needed for compaction and streaming.

### 23.3. Never destroy evidence on STOP

- Stop new dispatches/rollouts; never kill Cassandra or delete PVCs/PVs impulsively.
- Preserve logs, PV mappings, host ID/token/replica states, backup manifests, and metrics.
- When intervening on active jobs, follow operator/version-approved procedures.
- Separate **config/image rollback** from **data recovery**: rolling back code never undoes written SSTables.
- Resume only after an owner approves a recovery plan and verification criteria.

## 24. Case exercises and suggested answers

### Exercise 1 — Three Docker containers equal HA?

A developer runs three Cassandra containers on one laptop; RF3 and `LOCAL_QUORUM` both return results.

**Question:** Does this prove tolerance for a real zone failure?

**Answer:** No. Three containers sharing one host, disk, and network share one fault domain. Proving zone fault tolerance requires genuinely independent worker nodes, volumes, zones, and staging fault drills.

### Exercise 2 — `emptyDir` across container restarts

A Pod uses `emptyDir` for SSTables. The container crashes and kubelet restarts it inside the **same Pod**; data remains.

**Question:** Can `emptyDir` serve as production persistent storage?

**Answer:** No. `emptyDir` survives container restarts inside one Pod, yet is destroyed when the Pod is deleted or evicted. Use proper PVCs/PVs and backups.

### Exercise 3 — StatefulSet Pod Ready, yet volume is empty

`cassandra-1` is recreated after an upgrade. The PVC did not mount onto `/var/lib/cassandra` as before, and the app sees missing data.

**Question:** What should be checked?

**Answer:** STOP the rollout; inspect effective data directories, `volumeMounts`, PVC UID, PV handle, host ID, startup logs, and token placement. Never create a new table or wipe system keyspaces to "fill in data." This is likely an identity or data-path bug.

### Exercise 4 — Same data directory shared by two pods

An RWX volume is mounted into two Cassandra pods, both writing to the same data directory.

**Question:** Why is this wrong even though RWX permits mounting?

**Answer:** Cassandra is a shared-nothing replica system; two processes writing to the same SSTable/commitlog/system files risk corruption. Every node needs its own data directory and identity; RWX is not distributed database locking.

### Exercise 5 — `Immediate` StorageClass and wrong-zone PV

A PVC provisions in zone-a while the Pod scheduler only has eligible workers in zone-b. The Pod stays Pending.

**Question:** How do you prevent this?

**Answer:** Review `volumeBindingMode`/`WaitForFirstConsumer` if supported by CSI, PV `nodeAffinity`, and pod topology; align zone placement from the start. Never edit PV zone affinity arbitrarily.

### Exercise 6 — PVC `reclaimPolicy: Delete`

A Pod fails, and an operator plans to delete the PVC so the StatefulSet recreates it. The StorageClass/PV uses `reclaimPolicy: Delete`.

**Question:** What is the risk?

**Answer:** Deleting the PVC can delete the underlying backend volume, losing SSTables and commitlogs. Check PV/PVC mapping, backups, retention policies, and recovery runbooks before any destructive action.

### Exercise 7 — Scaling StatefulSet from 3 down to 2

A team cuts costs by reducing StatefulSet `replicas` without running Cassandra decommission.

**Question:** Why is this wrong?

**Answer:** Cassandra replica/token ownership and data movement require explicit handling. Deleting Pods/PVCs does not transfer ranges or rebalance RF, risking `Unavailable` errors and data loss. Use approved operator/decommission workflows.

### Exercise 8 — PDB `minAvailable: 2`

Cassandra runs RF3 with PDB `minAvailable=2`; one node went DOWN with disk failure, and the team drains another node because the PDB allows it.

**Question:** Does the PDB guarantee `LOCAL_QUORUM` stays intact?

**Answer:** No. PDBs know nothing about partition placement or Cassandra liveness, and Pod Ready states can mislead. DBAs must check replica/quorum state for affected token ranges before draining.

### Exercise 9 — Low CPU, very slow queries

Pod CPU is only 40%, yet read p99 hits 700ms, disk await is high, and pending compactions climb.

**Question:** Should we raise CPU limits first?

**Answer:** Insufficient evidence. Disk/compaction may be the bottleneck; inspect IOPS/throughput/queues, caches, tombstones, and hot partitions. Test storage or maintenance throttling in staging while holding query mix and CL constant.

### Exercise 10 — Heap equals memory limit

Pod limit is 8 GiB, JVM `-Xmx` is 8 GiB. The Pod gets `OOMKilled` even before heap-used fills.

**Question:** Why?

**Answer:** Off-heap/direct buffers, thread stacks, native memory, page cache, and kernel/cgroup accounting push RSS above the total limit. Budget memory explicitly and monitor RSS/GC/page cache; never set heap equal to the full container limit.

### Exercise 11 — Liveness running `SELECT` at `LOCAL_QUORUM`

`livenessProbe` executes a `LOCAL_QUORUM` `SELECT` every 5 seconds. One slow replica causes probes to fail, and kubelet restarts healthy Pods.

**Question:** What is the risk?

**Answer:** A restart storm stripping additional replicas and breaking availability. Liveness should check process dead/hung states with adequate startup time, while readiness/operator health checks use distinct semantics—never use quorum queries blindly for liveness.

### Exercise 12 — Pod IP changes

Pod `cassandra-0` reschedules with a new Pod IP while keeping the exact PVC and host ID.

**Question:** Is a rebuild mandatory?

**Answer:** Not automatically. Verify seeds/discovery, broadcast addresses, gossip/token ownership, and CQL. When identity and data match, it can be a valid restart; if host ID changed or the volume mismatched, STOP.

### Exercise 13 — Java Driver fails connecting to Headless Service

A Java service outside Kubernetes uses internal Pod DNS as its contact point, which is non-routable; `AllNodesFailed` wraps `ConnectTimeout`.

**Question:** Will raising the request timeout fix it?

**Answer:** No. You need reachable endpoints, supported address translation/proxies/network routes, TLS/auth, and matching local DC. Per-node errors show a transport issue—do not run Cassandra repair to fix it.

### Exercise 14 — Losing one zone with RF3 across two zones

Three replicas of a partition sit 2 in zone-a and 1 in zone-b. Zone-a goes down.

**Question:** Does `LOCAL_QUORUM` stay available?

**Answer:** With only one replica surviving in zone-b, **2/3 quorum in `dc1` is lost**. Having 3 total nodes does not ensure HA if placement and fault domains fall short.

### Exercise 15 — Is a PVC snapshot a sufficient backup?

A CSI `VolumeSnapshot` was taken for one PVC, with no schema manifest, remote copy, commitlog policy, or restore drill.

**Question:** Does this satisfy RPO/RTO?

**Answer:** Cannot be concluded. Block snapshots do not guarantee cluster-wide Cassandra consistency or business recoverability. You need Cassandra-aware backups, manifests/checksums/restore tests, and measured RPO/RTO.

### Exercise 16 — Deleting snapshots when disk nears full

Node disk is nearly full, snapshot SSTables are huge, remote uploads are failing, and no verified recent backup exists.

**Question:** Should snapshots be deleted immediately?

**Answer:** Never arbitrarily. You risk losing the only recovery point. The DBA and backup owner must assess prior backups, disk headroom, retention, upload recovery, or capacity expansion per incident runbook.

### Exercise 17 — Commitlog on `emptyDir`

The data directory sits on a PVC while the commitlog sits on `emptyDir`. A Pod is deleted before memtables flush.

**Question:** What is the risk?

**Answer:** Unflushed mutations in the commitlog are wiped with `emptyDir`, breaking durability and RPO. Evaluate commitlog/CL semantics and split volumes only deliberately—never purely to cut storage bills.

### Exercise 18 — Cassandra repair raises Java p99

Repair streams heavy SSTables, pushing API read p99 from 150 to 400 ms against a 250 ms SLO.

**Question:** Does launching more repair jobs to finish sooner make sense?

**Answer:** No, especially when SLO is already breached. Enforce health/capacity gates, throttle maintenance via the operator, monitor disk/network/compaction and recovery windows, and track repair coverage/deadlines.

### Exercise 19 — Wrong Local DC configured

The Cassandra cluster runs in `dc-east`, while the Java Driver sets `withLocalDatacenter("dc1")`; all Cassandra Pods are UP.

**Question:** Why can the app still fail?

**Answer:** Load balancing finds zero eligible nodes matching the configured local DC. Fix the effective config to match real topology rather than routing to another DC if data-residency or CL constraints apply.

### Exercise 20 — Restoring PVCs from an old snapshot

Restoring from last week brings back an order deleted this week, even though the fresh cluster booted cleanly.

**Question:** What went wrong?

**Answer:** An older snapshot cutoff omits newer deletes. DR must replay/reconcile post-cutoff writes and deletions, checking business truth and privacy retention before opening traffic—Pod Ready does not prove data correctness.

### Exercise 21 — Kubernetes CronJob driving repair

A CronJob triggers periodic repair without tracking token/DC scopes, repair modes, or failed ranges. The Job Pod reports `Completed`.

**Question:** Can we conclude every replica was repaired before `gc_grace_seconds`?

**Answer:** No. Maintain a **coverage ledger** by keyspace/table/range/replica/DC, last verified success, evidence, and near-deadline alerts. A cron trigger never substitutes for a repair verifier.

### Exercise 22 — Growing a PVC expecting double IOPS

A PVC expands from 500 GiB to 1 TiB; the backend provisions IOPS independently, so p99 barely moves.

**Question:** Why?

**Answer:** Capacity does not automatically scale throughput or IOPS. Inspect StorageClass/backend performance policies, disk queues, node attach limits, compaction, and query shapes; load-test to pick the right storage tier.

### Exercise 23 — Force-deleting Pods to speed up node drain

A Cassandra Pod takes long to terminate while flushing/replaying. The team force-deletes Pods repeatedly to finish the rollout faster.

**Question:** What are the risks?

**Answer:** Abrupt termination disrupts clean shutdowns, lengthens commitlog recovery, risks losing quorum, and triggers cascading node replacements. Inspect Pod/Cassandra state, `terminationGracePeriodSeconds`, and operator runbooks—never treat force-delete as routine.

### Exercise 24 — Users see missing data while `SELECT` errors

Java code catches every exception and returns an empty list. After an upgrade/network change, the app reports zero events.

**Question:** Can we treat this as confirmed data loss?

**Answer:** Not yet. `ReadTimeout`, `Unavailable`, and `AllNodesFailed` are **unknown read outcomes**, not successful zero-row reads. Fix error handling, inspect per-node causes/CL/partition keys, and verify the source Cassandra cluster.

## 25. Environment-based operations checklist

### 25.1. Data and storage

- [ ] SSTable, commitlog, hints, and snapshot paths verified per image/operator.
- [ ] Durable data lives on proper PVCs/PVs; never rely on container layers or `emptyDir` for persistent production data.
- [ ] Each node's PVC maps to the right Pod ordinal and host ID; never share data directories.
- [ ] StorageClass/CSI driver, access modes, topology binding, reclaim policy, and expansion tested.
- [ ] Local PV / zonal PV deployments have explicit node-replacement / zone-recovery runbooks.
- [ ] Disk headroom covers compaction, bootstrap, repair, snapshots, and growth.
- [ ] Off-fault-domain backups, manifests/checksums, encryption/KMS, and restore drills active.
- [ ] Never delete PVCs/PVs/snapshots or alter reclaim policies mid-incident without approval.

### 25.2. Topology, lifecycle, and HA

- [ ] Cassandra DC/rack mappings align with Kubernetes zones/node topology.
- [ ] Per-DC RF and Java client CLs documented and tested for quorum under node/zone loss.
- [ ] Seed discovery, broadcast addresses, and internode networking follow operator/version guidance.
- [ ] Startup, readiness, and liveness probes tested under GC, repair, and bootstrap with zero restart storms.
- [ ] `terminationGracePeriodSeconds`/`preStop` match version shutdown behavior without abusing force-delete.
- [ ] PDB scope understood properly; never treat a PDB as a Cassandra quorum guarantee.
- [ ] Rolling upgrades, scaling, and replacements orchestrated by operator/runbook with stop gates.
- [ ] HPA never scales Cassandra autonomously like a stateless API.
- [ ] Repair coverage, `gc_grace_seconds`, and node downtime actively monitored.

### 25.3. Java application and security

- [ ] Java Driver version pinned and compatible with Cassandra and JDK.
- [ ] Contact points routable, local DC accurate, and topology/token discovery working.
- [ ] TLS/mTLS, auth, NetworkPolicies, JMX/management access, and secrets tightly scoped.
- [ ] `CqlSession` and prepared statements reused cleanly; never allocate a session per request.
- [ ] Queries use partition keys; never use `ALLOW FILTERING` as a health check.
- [ ] Client p95/p99, successful RPS, retries, errors, and in-flight counts monitored.
- [ ] Post-write timeouts handled via idempotency/reconciliation; never assume an error means unapplied mutation.
- [ ] No sensitive configs, secrets, or payloads in public logs or Git YAML.

### 25.4. Change acceptance

- [ ] Baselines and approvals recorded for environment, version, and storage backend.
- [ ] Staging tests cover Pod restarts, PVC reattachment, and zone faults matching real fault domains.
- [ ] Fault/recovery tests run at real RF/CL; single-node tests are never mislabeled as HA proof.
- [ ] Kubernetes Pod Ready / PVC Bound reconciled against Cassandra `NORMAL`, repair, and streaming.
- [ ] CQL fixture reads/writes and business data correctness verified post-change.
- [ ] Resource headroom, error budgets, and post-maintenance recovery windows measured.
- [ ] RPO/RTO measured via restore drills, not snapshots alone.
- [ ] GO/PAUSE/STOP/ESCALATE report records owner, evidence, and unverified gaps.

## 26. Sample report for a storage/topology change

After every change window, archive a traceable report. The example below contains **sample data only**, not a Kubernetes/Cassandra manifest or real measurements:

~~~yaml
change:
  id: "cassandra-k8s-staging-storage-2026-11"
  environment: "staging-isolated"
  owner: "cassandra-platform"
  operation: "pod-restart-with-existing-pvc"
  approval: "<change-record>"
versions:
  kubernetes: "<exact-version>"
  csi_driver: "<exact-driver-version>"
  operator: "<name-and-version-or-none>"
  cassandra: "<exact-version>"
  jdk: "<exact-version>"
  java_driver: "<exact-version>"
topology:
  cluster: "staging-cassandra"
  dc: "dc1"
  racks_or_zones: ["zone-a", "zone-b", "zone-c"]
  rf_in_dc: 3
storage:
  storage_class: "<actual-class>"
  volume_binding_mode: "<observed>"
  access_mode: "<observed>"
  reclaim_policy: "<observed>"
  pvc_before: "<uid-and-volume-handle>"
  pvc_after: "<uid-and-volume-handle>"
  data_directory_verified: true
  same_node_identity_verified: true
baseline:
  cql_successful_rps: "<measured>"
  read_p99_ms: "<measured>"
  logical_error_percent: "<measured>"
maintenance:
  pod_restart_count: "<measured>"
  volume_attach_seconds: "<measured>"
  cassandra_startup_seconds: "<measured>"
  streaming_bytes: "<measured-if-applicable>"
  compaction_backlog_peak: "<measured>"
after_change:
  ring_and_token_placement_verified: true
  read_write_by_partition_key_verified: true
  repair_status: "<verified-coverage-or-not-applicable>"
  cql_successful_rps: "<measured>"
  read_p99_ms: "<measured>"
  recovery_window_minutes: "<measured>"
dr:
  off_domain_backup_verified: true
  restore_drill_reference: "<controlled-evidence>"
  rpo_measured: "<value-or-not-measured>"
  rto_measured: "<value-or-not-measured>"
decision:
  status: "GO | PAUSE | STOP | ESCALATE"
  unresolved_issues: []
  next_owner_action: "<approved-action>"
~~~

If a metric was not measured, record `NOT_MEASURED`. Never infer identity or replication state from Pod Ready. Reports/logs should store **node aliases, run IDs, and controlled volume handles** rather than credentials, certificate private keys, or real tenant IDs/payloads.

### 26.1. Acceptance questions not to miss

1. Did the Pod restart with the **exact same PVC** and Cassandra host ID/tokens?
2. Was data on that PVC actually read back via **partition key and target CL**?
3. Do Cassandra placement and DC/racks match real fault domains rather than merely counting 3 pods?
4. Did the Java service's p99 and error budget stay within bounds during and after maintenance?
5. Have compaction, repair/streaming, and disk headroom returned to stable levels?
6. Are backups independent of node/zone failures and **actually restore-tested**?
7. If a node/PV was lost, was **proper replacement/rebuild** run rather than just spawning a new Pod?
8. Are there post-cutoff deletions requiring reconciliation upon restore?
9. Is an owner assigned to remaining risks with an explicit stop gate?
10. Is every conclusion backed by evidence for your exact versions, operator, CSI, and environment?

## 27. Summary

**Operating Apache Cassandra in containers/Kubernetes is a problem of preserving identity, data, and distributed topology**, not merely putting a Java process inside a Pod. Kubernetes recreates Pods, binds PVCs, and schedules workloads, yet **does not natively understand token ownership, replication factors, consistency levels, compaction/repair, tombstones, or business data correctness**.

Sound design starts with **environmental conditions**: dev/CI can use single-node Docker and ephemeral data; staging must mirror storage, zones, and traffic; production requires **PVs/PVCs/CSIs with verified performance, fault domains, and retention**, a capable Cassandra-aware operator or runbook, aligned DC/rack topology, graceful lifecycles/probes free of restart storms, resource headroom, and end-to-end security.

**Persistent volumes do not replace replication, replication does not replace backups, CSI snapshots do not prove Cassandra-consistent restores, and Pod Ready does not prove data correctness.** After every restart, rollout, zone fault, or node replacement, reconcile **Cassandra ring/host ID/tokens, PVC identity, RF/CL, partition-key CQL, Java API p99/errors, repair/compaction/streaming, and backup recoverability**.

The final operational rule is **assess the environment → deploy under control → observe both Kubernetes and Cassandra → verify data and SLOs → archive evidence → GO/PAUSE/STOP per runbook**. Only when all of these layers are verified does automation help Cassandra recover dependably rather than merely recreating healthy-looking containers.
