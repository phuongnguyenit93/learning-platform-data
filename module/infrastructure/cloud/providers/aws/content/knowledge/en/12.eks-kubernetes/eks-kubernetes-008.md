# EBS CSI, EFS CSI, and Storage for Kubernetes Workloads on Amazon EKS

## Learning Objectives

After this lesson, you will be able to:

- Explain how **Kubernetes Pods** consume storage through **Volumes, PersistentVolumes (PV), PersistentVolumeClaims (PVC), StorageClasses, and the Container Storage Interface (CSI)**.
- Clearly distinguish the **Amazon EBS CSI driver** and the **Amazon EFS CSI driver** in attachment capabilities, data sharing, Availability Zone scope, performance, durability, and cost.
- Configure a **StorageClass and PVC** to provision gp3 EBS volumes for stateful workloads on **EKS EC2 nodes**, using `WaitForFirstConsumer` to prevent AZ mismatch errors.
- Configure **EFS dynamic provisioning with access points** or **static provisioning** so multiple Pods share a filesystem; understand limitations related to **EKS Fargate**.
- Understand the difference between **standard EBS CSI (`ebs.csi.aws.com`)** and **EKS Auto Mode block storage (`ebs.csi.eks.amazonaws.com`)**.
- Design **IAM Pod Identity or IRSA** permissions, AWS KMS, security groups, mount targets, DNS, POSIX permissions, snapshots, and backups.
- Diagnose PVC `Pending`, Pod `ContainerCreating`, `FailedAttachVolume`/`FailedMount` errors, unwritable volumes, mount timeouts, and wrong `accessModes`.
- Make storage choices for Java applications, databases, web uploads, analytics, and batch jobs based on **security, observability, recoverability, and cost efficiency**.

**Module context:** This lesson belongs to the **Kubernetes with EKS** chapter of the **CLOUD_PROVIDERS_AWS** module. EKS provides an AWS-managed Kubernetes control plane, while workloads run on EC2 nodes, EKS Auto Mode nodes, or EKS Fargate depending on configuration. You must properly combine **Region/AZ, IAM, VPC, EBS/EFS/S3, load balancing, databases, serverless, monitoring, recovery, and cost** knowledge so Pod data is not lost when containers are replaced.

> **Example scope:** The manifests below target primarily **Linux Pods on EKS with EC2 nodes**, using standard StorageClasses and AWS CSI drivers. EKS Auto Mode and Fargate have distinct conditions noted separately. IDs like `fs-...`, `vol-...`, cluster names, Regions, and buckets are illustrative; replace and verify them in your lab cluster before running.

## 1. Why Do Containers Need a Dedicated Storage Layer?

Containers provide a filesystem during execution, yet **writing to the container's writable layer is not a durable storage strategy**. When a Pod is deleted, rescheduled, rolled out, or a node fails, data in that ephemeral layer can disappear.

Examples:

- A Java API writes a PDF report to `/tmp/report.pdf` and the container is replaced: the temporary file can be lost.
- PostgreSQL running in a Pod needs data at `/var/lib/postgresql/data` to outlive a single container run.
- Two replicas of a web app need to read uploaded files together: they need a **shared** file store or object storage as required.
- A worker decoding large files needs scratch space: it may **not need** a persistent volume.

Kubernetes distinguishes:

| Need | Typically Suitable Solution | Notes |
|---|---|---|
| Cache/scratch within Pod lifecycle | `emptyDir` or appropriate ephemeral storage | Lost when Pod is deleted; still constrained by node capacity |
| Durable filesystem for **one node-attached workload** | **EBS CSI + PVC** | Block volume in a single AZ; node placement matters |
| Shared POSIX files across **multiple Pods/AZs** | **EFS CSI + PVC** | NFS; requires mount targets, networking, POSIX permissions |
| Large objects, images, invoices, backups | **S3 API** | Not a default POSIX filesystem; design app for object storage |
| Business databases needing managed HA/DR | **RDS/Aurora/DynamoDB** or replicated self-managed DB | Provisioning a PV alone does not create database HA |
| Specialized/HPC filesystems | **Amazon FSx** per protocol/performance needs | Must check drivers, topology, and supporting resources |

**Key message:** EBS/EFS solve provisioning block/file storage for Pods. **Kubernetes does not automatically turn every PV into multi-AZ storage or recoverable application backups.**

## 2. Five Kubernetes Concepts You Must Know

### 2.1. Volume in a Pod

A **volume** in a Pod is how containers see storage at a mount path, such as `/app/data`. Containers declare `volumeMounts`, while the Pod declares `volumes`.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: scratch-example
spec:
  containers:
    - name: worker
      image: busybox:1.36
      command: ["sh", "-c", "echo hello > /scratch/output.txt; sleep 3600"]
      volumeMounts:
        - name: work
          mountPath: /scratch
  volumes:
    - name: work
      emptyDir: {}
~~~

**`emptyDir` is not a PersistentVolume.** If the Pod is recreated on another node, that data is not automatically restored. It suits temporary scratch data, not order records.

### 2.2. PersistentVolume (PV)

A **PV** is a cluster-scoped resource representing provisioned storage, either created **statically** by an administrator or **dynamically** by a CSI provisioner.

A PV contains details such as:

- capacity and `accessModes`;
- `storageClassName`;
- reclaim policy;
- driver/volume handle details;
- `nodeAffinity` or topology constraints if applicable.

For example, a CSI-created EBS PV references `volumeHandle: vol-...`; an EFS PV references a file system or access point. A PV is a Kubernetes API object, **not the physical disk itself**.

### 2.3. PersistentVolumeClaim (PVC)

A **PVC** is a namespace-scoped request for storage: “I need 10 GiB, `ReadWriteOnce`, using StorageClass `ebs-gp3`.” When compatible, the controller **binds** the PVC to a PV.

~~~text
Namespace team-a
  └── PVC orders-data (10Gi, RWO)
        └── PV pvc-123... (bound)
              └── EBS volume vol-123... in AZ A
~~~

Pods only reference the **PVC name** and do not need to know the AWS EBS volume ID in application manifests. This decouples application teams from infrastructure teams.

### 2.4. StorageClass

A **StorageClass** configures a **provisioner** to dynamically provision PVs for matching PVCs. On EKS, a StorageClass can specify:

- CSI provisioner `ebs.csi.aws.com` or `efs.csi.aws.com`;
- EBS parameters such as `type: gp3`, encryption, IOPS/throughput;
- EFS parameters such as `fileSystemId`, `provisioningMode: efs-ap`;
- `volumeBindingMode`, `allowVolumeExpansion`, `reclaimPolicy`.

**A cluster is not limited to a single StorageClass.** You can define a `gp3` class for databases, `efs-ap` for shared files, and a dedicated class for EKS Auto Mode.

### 2.5. CSI driver

**Container Storage Interface (CSI)** is the standard for integrating storage with Kubernetes. A CSI driver connects Kubernetes requests to infrastructure create, attach, mount, and detach operations.

~~~mermaid
flowchart LR
    App[Pod with volumeMount] --> PVC[PersistentVolumeClaim]
    PVC --> PV[PersistentVolume]
    PV --> SC[StorageClass / CSI driver]
    SC --> AWS{AWS storage}
    AWS --> EBS[Amazon EBS block]
    AWS --> EFS[Amazon EFS NFS]
    PV -. Metadata / volume handle .-> App
~~~

This diagram illustrates configuration relationships; in practice, during dynamic provisioning, the StorageClass is used to **create a PV from a PVC**, and CSI controller/node components perform provisioning, attachment, and mounting. Application I/O requests do not traverse the Kubernetes API.

## 3. EBS CSI vs. EFS CSI: Core Comparison

| Criterion | **EBS CSI** | **EFS CSI** |
|---|---|---|
| AWS service | Amazon Elastic Block Store | Amazon Elastic File System |
| Storage type | Block device; filesystem on block | Shared file system, NFS |
| Standard CSI provisioner | `ebs.csi.aws.com` | `efs.csi.aws.com` |
| Location scope | **One EBS volume belongs to one AZ** | **Regional** EFS file system mountable from multiple AZs via mount targets |
| Common access mode | **RWO** (ReadWriteOnce); RWOP where driver/K8s support it | **RWX** (ReadWriteMany) |
| Concurrent multi-Pod use | RWO limits writes to **one node** semantically; not a cluster filesystem | Multiple nodes/Pods read-write concurrently if network/permissions allow |
| Performance | gp3/io2, configurable IOPS and throughput per volume type, low block latency | NFS network filesystem, throughput/IO patterns, metadata and network latency |
| Capacity | Pre-provisioned per PVC/StorageClass, expandable within limits | Elastic file system; PVC `storage` is not a hard quota |
| EKS Fargate support | **Cannot mount EBS onto Fargate Pods** | Supports **static PVs**, no dynamic provisioning on Fargate |
| EKS Auto Mode support | **Separate** driver `ebs.csi.eks.amazonaws.com` | Check driver/runtime configuration, networking, and workload type |
| Data recovery | CSI VolumeSnapshots/EBS snapshots; DB-aware backups | Backups/AWS Backup, EFS Replication per design, file data protection |
| Primary costs | Provisioned GiB, provisioned IOPS/throughput, snapshots | Stored capacity, throughput/requests by mode/tier, backups, data transfer |

**Short selection rule:** If a database Pod needs block storage with random I/O and low latency, **EBS** is worth evaluating. If multiple Pods across nodes/AZs need a shared NFS/POSIX directory, **EFS** fits better. If the app stores images/videos without needing a POSIX filesystem, evaluate **S3**, since NFS is not mandatory.

### Access modes do not grant security permissions by themselves

Kubernetes access modes describe **how a volume can be mounted/claimed**, not file-level access permissions:

- **ReadWriteOnce (RWO):** mounted read-write by **one node** at a time; multiple Pods **on that same node** may share access depending on setup.
- **ReadWriteOncePod (RWOP):** restricted to **a single Pod** cluster-wide where supported by CSI/Kubernetes; useful when strict single-Pod writer semantics are needed.
- **ReadWriteMany (RWX):** multiple nodes can mount read-write concurrently, suited for EFS.
- **ReadOnlyMany (ROX):** multiple nodes mount read-only where supported by the backend.

**Do not assume RWO means “only one single Pod can ever read or write.”** That is a common misconception. With EFS RWX, two Pods can still overwrite the same file or trigger race conditions; application-level locking/transactions and POSIX permissions remain necessary.

## 4. EKS Architecture with EBS and EFS Across Multiple AZs

Suppose an EKS cluster in Region `ap-southeast-1` has EC2 nodes across AZs A/B and a multi-replica API deployment:

~~~mermaid
flowchart TB
    LB[ALB / Ingress] --> API[Java API Deployment]
    API --> P1[API Pod AZ A]
    API --> P2[API Pod AZ B]

    subgraph AZA["AZ A"]
      P1 --> EA[(EBS volume: app cache/data A)]
      N1[EC2 Node A]
    end
    subgraph AZB["AZ B"]
      P2 --> EB[(EBS volume: app cache/data B)]
      N2[EC2 Node B]
    end

    P1 --> EFS[(Regional EFS: shared/uploads)]
    P2 --> EFS
    P1 --> DB[(RDS Multi-AZ / DynamoDB)]
    P2 --> DB
    Backup[Snapshots / AWS Backup] -. Protects data .-> EA
    Backup -. Protects data .-> EB
    Backup -. Protects data .-> EFS
~~~

This model shows **each replica with its own EBS volume**, alongside **EFS as a shared filesystem**. Key takeaways:

- **Two independent EBS volumes do not automatically sync data.** If the app needs shared files, use EFS or external replication.
- **An EBS volume only attaches to an EC2 node in the same AZ.** When a Pod moves to another AZ, the scheduler cannot simply carry the volume across AZs.
- **Regional EFS** can serve Pods across multiple AZs, though each AZ needs mount paths/networking; network latency and throughput must be measured.
- **Multi-AZ database** is the DB's own HA setup, not something achieved simply by setting Kubernetes replica count = 2.
- **Snapshots and backups** do not replace instant failover when RTO is very tight.

## 5. How Does the EBS CSI Driver Work?

With standard EBS CSI:

1. An administrator installs the **Amazon EBS CSI driver** into the cluster, usually as the **`aws-ebs-csi-driver` EKS add-on** on EC2-backed clusters.
2. The CSI controller receives **IAM permissions** to call EC2/EBS APIs to provision/modify/delete/attach/snapshot volumes within supported scope.
3. The administrator creates a StorageClass with `provisioner: ebs.csi.aws.com`.
4. An application creates a PVC using that StorageClass and a Pod referencing the PVC.
5. The CSI controller provisions the EBS volume; the node plugin attaches, formats/mounts the volume per lifecycle.
6. When the Pod is deleted/recreated, the PVC can reattach to the **existing volume**, provided scheduling/AZ and retention policies allow.

~~~mermaid
sequenceDiagram
    participant Dev as kubectl / app owner
    participant API as Kubernetes API
    participant CSI as EBS CSI controller
    participant EC2 as AWS EC2/EBS API
    participant Node as Worker node / kubelet

    Dev->>API: Create StorageClass + PVC + Pod
    API->>CSI: PVC requires volume per StorageClass
    CSI->>EC2: CreateVolume (AZ, type, encryption)
    EC2-->>CSI: EBS volume ID
    CSI->>API: Create/bind PV
    API->>Node: Schedule Pod on node in matching AZ
    Node->>CSI: Request attach/mount via CSI node plugin
    CSI->>EC2: Attach volume (as appropriate)
    Node-->>Dev: Pod has mount path, workload runs
~~~

The order changes when using `WaitForFirstConsumer`: Kubernetes resolves Pod/node/topology first before the driver provisions the volume. This diagram illustrates component responsibilities rather than a rigid API sequence for every deployment.

### Controller and node plugin differ

| Component | Primary Function |
|---|---|
| **CSI controller** | Creates/deletes volumes via AWS APIs, orchestrates attachments and management tasks |
| **CSI node plugin** | Coordinates with kubelet to stage/format/mount/unmount volumes on the node |
| **Kubernetes scheduler** | Picks a node with resources, labels/taints, and topology matching the PVC |
| **Kubernetes attach/detach controller and sidecars** | Reconcile volume attachment metadata/state per CSI mechanics |

Proper operation requires **IAM for both the controller and node plugins on eligible nodes**. On EKS EC2 nodes, the add-on runs node components as a DaemonSet. While the controller can run on compatible compute, **the EBS node plugin cannot mount EBS onto EKS Fargate Pods**.

## 6. StorageClass EBS gp3: Foundational Configuration

Example deploying the **standard EBS CSI driver** on EC2 nodes. File `ebs-gp3-storageclass.yaml`:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
  csi.storage.k8s.io/fstype: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
~~~

**Meaning:**

- `provisioner`: standard EBS CSI driver, not Auto Mode.
- `type: gp3`: general-purpose SSD; current baseline for gp3 is **3,000 IOPS and 125 MiB/s** unless higher performance is provisioned.
- `encrypted: "true"`: provisions encrypted EBS volumes; if using a customer-managed KMS key, specify `kmsKeyId` and matching KMS permissions.
- `reclaimPolicy: Retain`: when the PVC is deleted, the PV and underlying EBS volume are not automatically deleted; admins must handle recovery/cleanup manually.
- `allowVolumeExpansion: true`: permits PVCs to request capacity increases when supported by driver/Kubernetes/filesystem.
- `WaitForFirstConsumer`: waits to identify the first consuming Pod and its node topology before provisioning the EBS volume.

**Caution:** avoid adding the `is-default-class` annotation just for a lab in a cluster with multiple StorageClasses; setting `storageClassName` explicitly in PVCs prevents accidentally provisioning the wrong volume type or cost tier.

### Why is WaitForFirstConsumer nearly mandatory by design?

An EBS volume is created in **one specific AZ**. If a PVC provisions a volume in AZ A before scheduling info is known, yet the Pod can only run in AZ B due to nodeSelector, affinity, or capacity shortages, the PVC/Pod gets stuck.

~~~text
Immediate:
  PVC → volume created early in AZ A
  Pod → scheduler requires node in AZ B
  Result: topology/AZ conflict, Pod Pending or FailedAttach

WaitForFirstConsumer:
  PVC delays volume provisioning
  Pod → scheduler selects node with valid topology in AZ B
  CSI provisions volume in AZ B
  Result: avoids initial cross-AZ volume mismatch
~~~

**Do not try to “fix” this by relaxing all node affinities** if the workload genuinely needs a node in another AZ. Evaluate data needs, storage topology, and scheduler constraints first.

### Advanced gp3 parameters

Add to StorageClass per driver/API and current limits:

~~~yaml
parameters:
  type: gp3
  encrypted: "true"
  iops: "6000"
  throughput: "250"
~~~

For example, when a busy database needs more IOPS/throughput than baseline. Both extra allocations **incur additional charges**; throughput/IOPS ceilings also depend on volume size, instance limits, and account quotas. Do not assume `iops: "6000"` will be achieved in every Pod if the node hits an EBS bandwidth bottleneck.

## 7. PVC and Pod Using EBS on an EC2 Node

File `ebs-pvc.yaml`:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ebs-gp3
  resources:
    requests:
      storage: 20Gi
~~~

File `ebs-demo-pod.yaml`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: ebs-writer
  namespace: default
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          while true; do
            date -u >> /data/timestamps.txt
            sleep 15
          done
      volumeMounts:
        - name: persistent
          mountPath: /data
  volumes:
    - name: persistent
      persistentVolumeClaim:
        claimName: postgres-data
~~~

**This is only a storage example**, not an actual PostgreSQL deployment; the PVC is named `postgres-data` to represent the workload pattern. In production, databases require StatefulSet deployments, backup/logging/consistency configurations, and proper data protection.

Apply in a lab cluster with the EBS CSI driver installed:

~~~bash
kubectl apply -f ebs-gp3-storageclass.yaml
kubectl apply -f ebs-pvc.yaml
kubectl apply -f ebs-demo-pod.yaml

kubectl get sc
kubectl get pvc,pv
kubectl get pod ebs-writer -o wide
kubectl describe pvc postgres-data
kubectl describe pod ebs-writer
~~~

Because of `WaitForFirstConsumer`, the PVC stays `Pending` while **no Pod** consumes it; that is normal if only the PVC has been applied. Once the Pod is scheduled and the volume is provisioned, the PVC transitions to `Bound`.

### Verify data persists across the Pod lifecycle

~~~bash
kubectl exec ebs-writer -- sh -c 'tail -n 3 /data/timestamps.txt'

kubectl delete pod ebs-writer
kubectl apply -f ebs-demo-pod.yaml

kubectl exec ebs-writer -- sh -c 'tail -n 3 /data/timestamps.txt'
~~~

The new Pod can be scheduled onto a **different node in the same AZ** as the volume and re-mount data from the existing PVC. If no eligible node remains in that AZ, the Pod cannot start until capacity returns in that AZ or data is **restored/migrated** to a new volume in another AZ.

**Important:** for real workloads needing consistency, abruptly killing a Pod does not guarantee in-flight files/database pages are consistent. This lab solely verifies **EBS PV lifecycle**, not database backup integrity.

## 8. StatefulSet and volumeClaimTemplates for Stateful Applications

**Deployments** generally fit stateless apps with interchangeable replicas. For stateful workloads requiring stable identities and a dedicated volume per replica, **StatefulSet + volumeClaimTemplates** is the essential Kubernetes pattern.

Condensed example running BusyBox writing data to each replica's own volume:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: writer-headless
spec:
  clusterIP: None
  selector:
    app: stateful-writer
  ports:
    - port: 80
      name: placeholder
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: stateful-writer
spec:
  serviceName: writer-headless
  replicas: 2
  selector:
    matchLabels:
      app: stateful-writer
  template:
    metadata:
      labels:
        app: stateful-writer
    spec:
      containers:
        - name: writer
          image: busybox:1.36
          command: ["sh", "-c", "while true; do date -u >> /data/log.txt; sleep 30; done"]
          volumeMounts:
            - name: data
              mountPath: /data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: ebs-gp3
        resources:
          requests:
            storage: 10Gi
~~~

After creation, PVCs are typically named:

~~~text
data-stateful-writer-0 → EBS volume for replica 0
data-stateful-writer-1 → EBS volume for replica 1
~~~

**Each Pod gets its own volume; the two replicas do not share data.** If this were a PostgreSQL cluster, replication between replicas must be handled by the database/operator; a StatefulSet **does not automatically replicate DB data**.

When deleting or scaling down a StatefulSet, PVCs typically have their own retention policies; never assume deleting a StatefulSet wipes all data. Kubernetes provides StatefulSet PVC retention policies by version/config, and the PV's `reclaimPolicy` also governs backend resources. Check both before running deletions.

### When is EBS a good fit for a StatefulSet?

- Each replica has its **own dataset**, such as nodes of a distributed database or queue cluster.
- Random I/O workloads requiring low block latency.
- The application handles replication, quorum, failover, and backups **independently** of CSI.
- A plan exists for Pod rescheduling when an EBS volume cannot directly switch AZs.

If all replicas must access shared files at one POSIX path, evaluate **EFS** or an appropriate file service instead.

## 9. EBS CSI, EKS Auto Mode, and EKS Fargate: Three Distinct Models

### 9.1. Standard EBS CSI driver

- Provisioner: `ebs.csi.aws.com`.
- Used with compatible EC2 nodes; the node plugin mounts EBS onto nodes.
- Installed via the **`aws-ebs-csi-driver` Amazon EKS add-on** or self-managed driver when justified and compatible.
- Controller IAM: typically uses **EKS Pod Identity or IRSA** per AWS guidance.
- EBS volumes attach to **EC2 nodes in the same AZ**.

### 9.2. EKS Auto Mode block storage

**EKS Auto Mode** includes built-in block storage management; you do not have to install the standard EBS CSI controller to use it. Your StorageClass must specify a **different provisioner**:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: auto-ebs-gp3
provisioner: ebs.csi.eks.amazonaws.com
parameters:
  type: gp3
  encrypted: "true"
volumeBindingMode: WaitForFirstConsumer
allowedTopologies:
  - matchLabelExpressions:
      - key: eks.amazonaws.com/compute-type
        values:
          - auto
reclaimPolicy: Retain
allowVolumeExpansion: true
~~~

The `allowedTopologies` condition in the example restricts volumes/workloads to Auto Mode nodes in **mixed node-type** clusters. Auto Mode **does not automatically create a StorageClass** just because Auto Mode is enabled; you must define an appropriate class.

**Never directly change `ebs.csi.aws.com` to `ebs.csi.eks.amazonaws.com` on a StorageClass with existing PVCs and call that a migration.** These are two separate volume provisioners; migrating existing workloads requires snapshot/restore or a supported migration workflow with data verification and downtime planning.

With EKS Auto Mode using a **customer-managed KMS key**, KMS permissions involve the **EKS cluster role** per Auto Mode docs; **do not copy the standard EBS CSI controller Pod Identity/IRSA model** onto Auto Mode-managed capabilities.

**Note on modifying performance after volume creation:** on sufficiently new EKS Auto Mode/Kubernetes versions, changing EBS type, IOPS, and throughput can use **VolumeAttributesClass**; AWS docs explicitly note moving away from the annotation-based `volume-modifier-for-k8s` project. Before modifying live volumes, verify your Kubernetes version and supported APIs rather than relying on older annotations.

### 9.3. EKS Fargate

With **EKS Fargate Pods**, **you cannot mount EBS volumes** as on EC2 nodes. Fargate provides its own ephemeral storage, while shared persistent files can integrate with **Amazon EFS**.

**EFS on EKS Fargate supports static provisioning, not dynamic provisioning for PersistentVolumes.** Fargate includes built-in EFS mounting; do not install the EFS CSI node DaemonSet on Fargate nodes. Properly configure the file system, mount targets, and static PV/PVC. Never create a dynamic `efs-ap` PVC expecting Fargate to dynamically provision an EFS access point.

| Capability | EC2 nodes + standard CSI | EKS Auto Mode nodes | EKS Fargate |
|---|---|---|---|
| EBS persistent PV | Yes, via EBS CSI | Yes, via Auto Mode provisioner | **No** |
| EFS persistent PV | Yes, via EFS CSI | Per driver/runtime config | Yes, **static provisioning** |
| Self-managed EBS CSI controller | Installed via add-on/self-managed | Not needed for Auto Mode block storage | Controller can run on compatible compute, but no EBS node mounts |
| Shared RWX files | Appropriate EFS/FSx | EFS/FSx per specific support | Static EFS |
| Ephemeral scratch | Node/Pod ephemeral volumes | Depends on node/workload | Fargate ephemeral storage |

## 10. EFS CSI: Providing a Shared Filesystem for Multiple Pods

**Amazon EFS** is a shared **NFS** network filesystem. On EKS, the **Amazon EFS CSI driver** creates PVs or mounts file systems/access points into Pods.

A Regional EFS file system can be accessed by multiple Pods across different nodes when:

- The EFS file system has **mount targets** in matching VPC/AZs;
- Nodes/tasks have network routes, DNS, and security groups reaching mount targets on **TCP 2049**;
- IAM/file system policies and POSIX permissions allow the operations;
- The CSI node plugin/mount helper operates properly in the target environment.

~~~mermaid
flowchart TB
    subgraph A["AZ A"]
      P1[Web Pod A] --> MT1[EFS mount target A]
      N1[EC2 Node A]
    end
    subgraph B["AZ B"]
      P2[Web Pod B] --> MT2[EFS mount target B]
      N2[EC2 Node B]
    end
    MT1 --> FS[(Regional EFS file system)]
    MT2 --> FS
    FS --> AP1[EFS Access Point /team-a]
    FS --> AP2[EFS Access Point /team-b]
~~~

**EFS access points** map a root directory and POSIX user/group identity for an application or dataset. Access points **do not create separate physical file systems**; data still resides in the same EFS file system unless you intentionally separate file systems.

### Is EFS suitable for transactional databases?

EFS delivers NFS file semantics, not EBS-equivalent block latency. Database engines have strict filesystem/locking/fsync and latency requirements; never move a database from EBS to EFS merely “so multiple Pods can mount it.” For relational databases, consider **RDS/Aurora** or a database operator/cluster proven compatible with storage, durability, and HA requirements.

## 11. EFS Dynamic Provisioning with Access Points

On **EKS EC2 nodes** running a supported EFS CSI driver version, dynamic provisioning can create a new **EFS access point** when a PVC requests storage. The EFS file system must **already exist**.

### Preparation steps

1. Create a Regional EFS file system in the right VPC and select performance/throughput modes per workload.
2. Create **mount targets** in AZs hosting EKS worker nodes; attach an EFS SG allowing inbound **TCP/2049 from the node SG**.
3. Ensure VPC DNS resolvers and routes resolve/reach mount targets.
4. Install the **Amazon EFS CSI driver** as the `aws-efs-csi-driver` EKS add-on for EC2 nodes and grant the controller EFS API permissions via Pod Identity/IRSA.
5. Review EFS file system policy, encryption at rest, TLS in transit, access points, and POSIX permissions.

### StorageClass that dynamically creates access points

File `efs-ap-sc.yaml`:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: efs-ap
provisioner: efs.csi.aws.com
parameters:
  provisioningMode: efs-ap
  fileSystemId: fs-0123456789abcdef0
  directoryPerms: "750"
  basePath: "/k8s-dynamic"
reclaimPolicy: Retain
volumeBindingMode: Immediate
mountOptions:
  - tls
~~~

Explanation:

- `fileSystemId` points to an **existing EFS**; it does not create an EFS file system.
- `provisioningMode: efs-ap` tells the driver to create an **access point** per PVC.
- `directoryPerms` governs permissions when the driver creates directories in supported scenarios; **POSIX UID/GID and access point identity** still need verification.
- `mountOptions: [tls]` enforces NFS encryption in transit via the supported helper/driver.
- `reclaimPolicy: Retain` keeps the PV/backend reference on PVC deletion to avoid accidental data loss; requires manual cleanup when no longer needed.

With `reclaimPolicy: Delete`, the dynamic provisioner normally removes the **access point** upon PV reclamation; **do not assume all underlying files/directories are automatically purged from the EFS file system**. Verify storage cleanup and permissions to avoid leaving sensitive data or orphaned charges behind.

### RWX PVC

File `efs-pvc.yaml`:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-upload
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-ap
  resources:
    requests:
      storage: 5Gi
~~~

**`5Gi` on an EFS PVC does not enforce a 5 GiB quota on the file system.** EFS scales elastically with stored data; per-team quotas require separate design or application/tooling controls.

### Two Pods sharing one PVC

File `efs-two-pods.yaml`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: efs-writer-a
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "writer A started" >> /shared/notes.txt
          sleep 3600
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: shared-upload
---
apiVersion: v1
kind: Pod
metadata:
  name: efs-reader-b
spec:
  containers:
    - name: reader
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: shared-upload
~~~

Once both Pods are `Running`, test:

~~~bash
kubectl exec efs-writer-a -- cat /shared/notes.txt
kubectl exec efs-reader-b -- cat /shared/notes.txt
kubectl exec efs-reader-b -- sh -c 'echo writer-B >> /shared/notes.txt'
kubectl exec efs-writer-a -- cat /shared/notes.txt
~~~

If `Permission denied` occurs, do not conclude EFS lacks RWX support. Check access point POSIX UID/GID, `directoryPerms`, `runAsUser`, `fsGroup`, file system policy, and mount status. **RWX is a mount mode**, not blanket permission to write every file.

## 12. EFS Static Provisioning: Solution for Existing Resources and Fargate

With static provisioning, an admin **creates a PV pointing to an existing EFS file system or access point**. The PVC binds to that PV.

Template with a **pre-created EFS access point**:

~~~yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: efs-static-pv
spec:
  capacity:
    storage: 5Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  csi:
    driver: efs.csi.aws.com
    volumeHandle: "fs-0123456789abcdef0::fsap-0123456789abcdef0"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: efs-static-claim
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  volumeName: efs-static-pv
  resources:
    requests:
      storage: 5Gi
~~~

**`volumeHandle` in the example uses the `EFS file system ID :: EFS access point ID` format.** A real access point must exist before applying, with matching file system and IAM/POSIX settings. `storageClassName: ""` indicates no default dynamic StorageClass is used; `volumeName` binds the PVC to the static PV.

Example Pod mounting the claim:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: efs-static-reader
spec:
  containers:
    - name: reader
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: efs-static-claim
~~~

For **EKS Fargate**, ensure the Pod is matched by a **Fargate profile**, the file system has mount targets reachable from the Pod's network, and policies/permissions match. Fargate mounts EFS using built-in mechanics—**never manually install the EFS CSI node DaemonSet onto Fargate**. Verify EKS version support and workload limits before deploying.

**Data caution:** PV/PVC capacity `5Gi` does not cap the EFS access point at 5 GiB. EFS quotas/billing operate at the file system layer per service behavior.

## 13. Storage Topology, Scheduling, and Cross-AZ Errors

An EBS volume created in **AZ A** while the Pod's node runs in **AZ B** is a common cause of `Pending` or `ContainerCreating` Pods.

### 13.1. When a PVC is already bound to an existing EBS volume

Suppose a PVC points to `vol-aaaa` in AZ A. A new nodeSelector requires AZ B:

~~~text
PVC → PV (vol-aaaa, AZ A)
Pod → nodeSelector / affinity requires AZ B
Scheduler → no node satisfies both PVC topology and node rules
Pod → Pending
~~~

**You cannot change the AZ of an existing EBS volume** by editing `nodeAffinity` on the PV. Creating a new volume in the target AZ typically requires **snapshot/restore or application-level replication/migration**. Altering metadata to bypass validation while the underlying volume stays in AZ A is unsafe and does not resolve the physical constraint.

### 13.2. Pod rescheduling and node autoscaling

When Karpenter/Cluster Autoscaler provisions nodes, account for:

- Nodes must reside in an AZ compatible with **bound PVs**;
- Capacity type/instance type must support EBS/ENI/attachment limits;
- Taints/tolerations, node affinity, and topology spread constraints;
- Time for new nodes to become Ready, plus EBS detach from the old node and attach to the new node;
- Rollouts/PodDisruptionBudgets and StatefulSet HA requirements.

**PodDisruptionBudgets** help limit voluntary disruptions, yet cannot stop infrastructure outages or all operational actions; PDBs **do not protect EBS data from an AZ loss**.

### 13.3. EFS is less AZ-bound, but not topology-free

With **EFS Regional**, two Pods in different AZs can access the same namespace via mount targets; however, if one AZ lacks an EFS mount target, clients may route cross-AZ, raising latency, transfer cost, and failure coupling. Standard practice is placing **mount targets in every AZ running workloads**, measuring latency and mount helper address selection.

With **EFS One Zone**, data lives in a single AZ; never assume it provides the same AZ fault tolerance as EFS Regional. Choose based on RTO/RPO and acceptable data loss.

## 14. IAM: CSI Controller Permissions Are Not Application Permissions

When the EBS CSI driver provisions volumes, the controller requires API permissions like `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:DeleteVolume`, `ec2:CreateTags`, volume/snapshot descriptions, and related actions. For dynamic EFS, the controller needs permissions like `elasticfilesystem:CreateAccessPoint`, `DeleteAccessPoint`, and `DescribeFileSystems` per AWS-documented IAM policies.

**Do not grant all these permissions to a Java application Pod just so the app can write files to its mount.** Keep two boundaries clear:

| Principal | Permissions Needed | Example |
|---|---|---|
| **EBS CSI controller** | EBS/EC2 APIs within PV management scope | CreateVolume, AttachVolume, snapshot, modify per capability |
| **EFS CSI controller** | EFS access point/file system metadata APIs for dynamic mode | Conditional CreateAccessPoint, DeleteAccessPoint |
| **Application Pod** | File operations on mounted volumes; separate AWS APIs if called | `s3:GetObject`, `sqs:SendMessage` on the app role |
| **Kubernetes user/admin** | K8s RBAC to create StorageClass, PVC, PV, Pod, snapshots | Does not imply AWS IAM API permissions |
| **EKS node / Fargate role** | Runtime infrastructure actions per compute type | Should not substitute for CSI/app roles |

### IAM Pod Identity and IRSA

AWS supports **EKS Pod Identity** and **IAM Roles for Service Accounts (IRSA)** so workload/controller Pods obtain temporary AWS credentials per ServiceAccount identity.

- **Pod Identity** uses EKS Pod Identity associations and trusts service principal `pods.eks.amazonaws.com` in supported setups.
- **IRSA** uses the EKS OIDC provider, Kubernetes ServiceAccount tokens, and `sts:AssumeRoleWithWebIdentity` trust policies.
- Driver IAM roles must be **bound to the exact CSI controller ServiceAccount**, typically in `kube-system`.
- On EKS Auto Mode, the block storage capability uses a different permission model from the traditional driver; consult EKS Auto Mode and KMS cluster role guidance.

Example checking EKS add-ons:

~~~bash
aws eks describe-addon \
  --cluster-name storage-lab \
  --addon-name aws-ebs-csi-driver \
  --region ap-southeast-1

aws eks describe-addon \
  --cluster-name storage-lab \
  --addon-name aws-efs-csi-driver \
  --region ap-southeast-1
~~~

These commands only check **EKS managed add-ons**. If drivers are installed via self-managed Helm or you use Auto Mode, add-ons may not appear here, which does not prove storage is broken.

### Choose managed IAM policies carefully

AWS provides managed policies for CSI drivers (names/versions may evolve), such as **AmazonEBSCSIDriverPolicyV2** or appropriate scoped alternatives, and **AmazonEFSCSIDriverPolicy**. Inspect official policies, resource tag conditions, and account scope instead of writing `ec2:*`/`elasticfilesystem:*` on `*`.

When using a **customer-managed KMS key** for EBS, verify IAM + key policies/grants, `kms:CreateGrant` within required scope, and key Region. KMS errors can surface during PVC provisioning or attach even when Kubernetes RBAC is completely valid.

## 15. VPC, DNS, Mount Targets, and POSIX: Securing EFS

### 15.1. NFS flow over TCP/2049

An EFS mount requires a network path:

~~~mermaid
flowchart LR
    P[Pod] --> Node[EC2 Node or Fargate networking]
    Node --> DNS[VPC DNS resolver / EFS DNS]
    DNS --> MT[EFS mount target IP]
    Node -->|TCP 2049 / TLS when configured| MT
    MT --> EFS[(EFS filesystem)]
~~~

**Typical security groups:**

- **EFS mount target SG**: inbound **TCP/2049** from the **node SG** or actual Pod network SG.
- Node/Pod SG: outbound TCP/2049 to the EFS mount target SG/IP per organizational policy.
- NACLs (if restrictive) allow **bidirectional** traffic, including stateless return traffic.
- Routes/DNS between the Pod subnet and mount target work; VPC DNS can resolve the EFS hostname.

**Never open NFS 2049 to the Internet** or `0.0.0.0/0` just because a Pod reports a mount timeout. Verify destination IPs, which ENIs carry which SGs, and Pod VPC networking.

### 15.2. Encryption at rest, in transit, and KMS

- **EBS:** configure EBS volume encryption on the StorageClass/volume; customer-managed KMS keys need appropriate key usage permissions. Individual file reads/writes inside a Pod do not call KMS on every I/O.
- **EFS at rest:** select encryption when creating the file system; manage KMS keys and permissions properly. Changing encryption on an existing file system has constraints; migration differs from simply editing YAML.
- **EFS in transit:** use TLS mounts via CSI/driver options; if IAM authorization for EFS clients is required, configure mount option `iam`, access point/file system policies, and runtime IAM per EFS docs.
- **POSIX:** `runAsUser`, `runAsGroup`, `fsGroup`, access point POSIX identity, file ownership, and mode determine whether files can be read/written; encryption does not replace POSIX permissions.

**Avoid a common confusion:** IAM for the CSI controller to **create access points** and IAM for a **client to mount/access EFS** (if enforced by a file system policy) are two separate concerns. NFS file access is still governed by POSIX ACLs/modes rather than simple `s3:GetObject` style calls.

### 15.3. Access points to isolate paths and users

One EFS file system can serve multiple teams. You can create:

~~~text
File system fs-example:
  Access Point A → /teams/team-a → POSIX uid/gid A
  Access Point B → /teams/team-b → POSIX uid/gid B
~~~

Each PV/PVC maps to a dedicated access point. This helps govern namespaces/permissions, yet **is not a complete isolation boundary like separate accounts or separate file systems**. Verify AWS/EFS file system policies and access paths to prevent unintended access point bypasses.

## 16. Snapshots and Restoring EBS CSI Volumes

Kubernetes provides **VolumeSnapshot**, **VolumeSnapshotClass**, and **VolumeSnapshotContent** through CSI snapshot APIs when required CRDs/controllers are installed. With EBS CSI, backend snapshots correspond to **EBS snapshots**.

### Prerequisites

1. EKS cluster has a compatible EBS CSI driver.
2. **CSI external snapshot controller** and VolumeSnapshot CRDs are installed (via EKS add-on or compatible setup).
3. EBS CSI controller has snapshot IAM permissions and KMS grants/permissions for encrypted volumes.
4. Source PVC exists, and the workload has a data consistency strategy when taking snapshots.

**Installing only the EBS CSI add-on without the snapshot controller/CRDs will not make VolumeSnapshots work automatically.**

### VolumeSnapshotClass

File `ebs-snapshot-class.yaml`:

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: ebs-snapshot-retain
driver: ebs.csi.aws.com
deletionPolicy: Retain
~~~

### Create a snapshot from a PVC

File `ebs-snapshot.yaml`:

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-data-snap
  namespace: default
spec:
  volumeSnapshotClassName: ebs-snapshot-retain
  source:
    persistentVolumeClaimName: postgres-data
~~~

Apply and check status:

~~~bash
kubectl apply -f ebs-snapshot-class.yaml
kubectl apply -f ebs-snapshot.yaml

kubectl get volumesnapshot -n default
kubectl describe volumesnapshot postgres-data-snap -n default
kubectl get volumesnapshotcontent
~~~

Wait for `readyToUse: true` in API status before relying on a snapshot for recovery. **`deletionPolicy: Retain`** on VolumeSnapshotClass governs backend snapshot deletion, distinct from StorageClass/PV `reclaimPolicy`.

### Create a new PVC from a snapshot

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: restored-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ebs-gp3
  resources:
    requests:
      storage: 20Gi
  dataSource:
    name: postgres-data-snap
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
~~~

The restored PVC needs a **minimum capacity compatible** with the snapshot. With `WaitForFirstConsumer`, provisioning the new EBS volume waits for the first Pod, picking the right AZ. Restoring into another AZ in the same Region is typically done by **provisioning a new volume from a snapshot**, rather than “moving” the old EBS volume across AZs.

### Crash consistency differs from application consistency

EBS snapshots capture block state; for actively writing databases, without quiescing or using database-native backup mechanisms, snapshots may only be **crash-consistent**. For reliable PostgreSQL/MySQL recovery:

- Use database-aware backups, transaction/WAL/binlog archiving, and consistency verification;
- If data spans multiple PVCs, coordinate snapshot/application synchronization;
- **Test restores** in an isolated lab workload, checking data/queries and app startup;
- Measure time from incident to service restoration for **RTO**, and the last recoverable point in time for **RPO**.

**VolumeSnapshots do not automatically provide multi-Region DR:** EBS snapshots are Regional; cross-Region recovery requires copying snapshots and separate procedures. For strict recovery targets, pair with AWS Backup or an appropriate snapshot/replication strategy.

## 17. Backups for EFS: Separating EBS Snapshots from File Protection

**EFS is not EBS.** Never apply an EBS VolumeSnapshotClass to an EFS PVC expecting EBS snapshots for NFS data.

For EFS, options to evaluate include:

- **AWS Backup** with appropriate schedules, retention, and vaults, supporting EFS backup/restore workflows.
- **EFS replication** to maintain replicas where supported, paired with failover, writeability, and restore testing.
- **Application-level versioning or backup logic** for critical files, with integrity checks.
- **S3** if the data is truly object-oriented; S3 versioning/lifecycle/replication follow a different model from EFS.

**High-availability Regional EFS does not protect against accidental deletion or ransomware.** A file deleted by a Pod with write access disappears for all Pods sharing that mount. Backups isolated from runtime permissions, with proper IAM and retention, are essential.

### Recovery options table

| Incident | With EBS PVC | With EFS PVC |
|---|---|---|
| Pod/container crashes | Service/StatefulSet recreates Pod, reattaches EBS in same AZ | New Pod remounts EFS over network |
| EC2 node fails | Reschedules to healthy node **in the EBS AZ** | Reschedules to node/AZ with a mount target |
| AZ outage | Restore new volume from snapshot or app-replicate to another AZ | Regional EFS remains accessible via other AZs; One Zone does not |
| Accidental file deletion | App snapshots/backups, file-level restore | AWS Backup or appropriate file/version backups |
| DB corruption | DB-aware backups, point-in-time recovery if designed | Using EFS does not prevent corruption |
| Region outage | Cross-Region snapshot copy/DB replication | EFS replication/cross-Region backups per design |

## 18. Volume Expansion and Performance

### 18.1. Expanding EBS PVC capacity

With a StorageClass setting `allowVolumeExpansion: true`, you can **increase** a PVC's storage request:

~~~bash
kubectl patch pvc postgres-data \
  -p '{"spec":{"resources":{"requests":{"storage":"30Gi"}}}}'

kubectl get pvc postgres-data
kubectl describe pvc postgres-data
~~~

Kubernetes and the CSI driver orchestrate resizing the EBS volume and filesystem where supported. Some filesystems/versions/runtimes require Pod/node involvement to complete; monitor `FileSystemResizePending`, status/conditions, and `df -h` inside the container. Do not assume resizing is finished merely because the AWS EBS size grew.

**You cannot shrink an EBS volume directly** by patching a PVC from 30Gi down to 10Gi. Shrinking requires creating a new smaller PVC/volume large enough for the data, migrating/restoring, and switching the application over.

### 18.2. Tuning IOPS/throughput differs from resizing capacity

For gp3, provisioning extra IOPS/throughput is separate from size. It can be set at StorageClass creation or via supported volume modification features depending on driver/version. **Do not edit a StorageClass expecting all previously provisioned volumes to automatically change performance.**

In sufficiently recent EKS Auto Mode, **VolumeAttributesClass** supports adjusting performance/type per policy and Kubernetes version. Illustrative example only:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: VolumeAttributesClass
metadata:
  name: auto-gp3-6000-250
driverName: ebs.csi.eks.amazonaws.com
parameters:
  type: gp3
  iops: "6000"
  throughput: "250"
~~~

Per AWS Auto Mode docs, on supported Kubernetes versions (e.g., 1.34+), PVCs can reference a VolumeAttributesClass to request volume attribute changes. **APIs and support can evolve**; verify before applying, especially on clusters using standard EBS CSI or self-managed drivers.

### 18.3. EBS, EFS, and real-world limits

| Aspect | EBS | EFS |
|---|---|---|
| How capacity grows | Expand EBS volume/PVC per supported conditions | Filesystem grows elastically with data; PVC request is not a hard quota |
| Bottlenecks | Volume IOPS, throughput/latency, and EC2 EBS bandwidth | Network, NFS ops, throughput mode, client count, metadata |
| What to benchmark? | I/O size, random/sequential, queue depth, p95/p99 latency | NFS read/write, concurrent clients, metadata ops, throughput, latency |
| Cost of performance | gp3 provisioned IOPS/throughput above baseline, io2 | EFS throughput/storage classes/IO per active mode |
| Failure recovery | Reattach in same AZ, snapshots, app replication | Remount, multi-AZ mount targets, backups/replication |

**Never optimize by raising EBS IOPS if the Pod is bottlenecked on CPU or database locks.** Likewise, never raise EFS throughput when the real failure is POSIX `Permission denied` or blocked TCP 2049.

## 19. Troubleshooting by Symptom

| Symptom | Possible Cause | Priority Checks |
|---|---|---|
| EBS PVC `Pending`, no Pod yet | `WaitForFirstConsumer` waiting for consumer | Check StorageClass; create Pod so scheduler picks topology |
| EBS PVC stuck `Pending` despite Pod | CSI driver not running, IAM `UnauthorizedOperation`, EBS quota, no eligible node | `kubectl describe pvc/pod`, CSI controller logs, IAM role, AZs |
| EBS Pod `Pending` with nodeSelector in another AZ | PV already bound in old AZ, topology conflict | PV `nodeAffinity`, node AZ labels, plan snapshot/restore |
| Pod `ContainerCreating` and `FailedAttachVolume` | EBS still attached elsewhere, detach/attach error, missing IAM, volume state | `VolumeAttachment`, node events, EBS `describe-volumes` |
| EBS PVC `Bound` but mount fails | CSI node plugin, filesystem/permissions, device/format/mount | kubelet/CSI node logs, Pod events, filesystem mode |
| Cannot mount EBS on Fargate | EKS Fargate does not support EBS mounts | Use EC2/Auto Mode nodes or evaluate EFS/S3 |
| EBS StorageClass on Auto Mode fails to provision | Wrong provisioner `ebs.csi.aws.com` for Auto Mode capability | Use `ebs.csi.eks.amazonaws.com`, topology, cluster role perms |
| Dynamic EFS PVC `Pending` | Wrong fileSystemId, missing `CreateAccessPoint`, IAM, AP quota, driver error | EFS CSI controller logs, PV events, filesystem/account/Region |
| EFS Pod `FailedMount` timeout | TCP 2049 blocked by SG/NACL/route, missing mount target, DNS error | Mount targets per AZ, source/dest SGs, resolver, network test |
| EFS mounts yet cannot write | Access point POSIX identity, directoryPerms, wrong fsGroup/runAsUser, or EFS policy | `id`, `ls -ln`, `iam` mount option, access point |
| One Pod sees file, another does not | Different PVCs/access points, different mount paths, or app caching | PV `volumeHandle`, AP ID, namespace, paths, consistency |
| EFS PVC writes past 5Gi despite 5Gi request | PVC capacity is not an EFS filesystem quota | Design quotas/monitoring at service/app layer |
| HPA scales Pods yet EBS fails to attach | One RWO PVC is not shared RWX; nodes span AZs | Per-replica StatefulSet volumes, EFS RWX, or object storage |
| Deleting PVC wiped EBS volume | StorageClass `reclaimPolicy: Delete` | Check PV/PVC before deleting; use backups/Retain |
| Snapshot creation fails | Missing CSI snapshot controller/CRDs, IAM, or wrong snapshot class driver | `kubectl get volumesnapshotclass`, logs, EC2 permissions |
| Volume expanded yet filesystem size unchanged | Node filesystem resize incomplete | PVC conditions, `df -h`, CSI logs, Pod restart if required |
| High EFS latency across AZs | Missing mount target in AZ, networking/throughput/caching | AZ placement, EFS CloudWatch metrics, NFS client load |
| Rising EBS/EFS costs | Uncleaned PVs/volumes, stale EFS data, snapshot retention/IOPS | Billing, tags, PV reclaim policy, EFS lifecycle, Budgets |

### Layered incident reading order

~~~text
1. kubectl get pod,pvc,pv -A (identify exact namespace and objects)
2. kubectl describe pod <pod> -n <ns>
3. kubectl describe pvc <claim> -n <ns>
4. kubectl get sc; kubectl get csidrivers
5. For EBS: check driver, StorageClass provisioner, IAM, PV nodeAffinity,
   node AZ, VolumeAttachment, EBS volume state/KMS.
6. For EFS: check access point/PV volumeHandle, mount targets, DNS, TCP 2049,
   SGs/NACLs, POSIX UID/GID, EFS filesystem policy.
7. Cross-check AWS CloudTrail + controller/node logs + application logs.
8. Fix minimal root cause, test real mount/write/read, and rehearse recovery.
~~~

Never run `chmod -R 777`, open SGs to `0.0.0.0/0`, grant `AdministratorAccess` to controllers, or delete PVs/PVCs holding critical data just to silence an immediate error. Those shortcuts increase data loss risk or open unintended access.

## 20. Diagnostic Practice via kubectl and AWS CLI

### 20.1. Verify cluster identity and add-ons

~~~bash
aws sts get-caller-identity
aws eks describe-cluster \
  --name storage-lab \
  --region ap-southeast-1 \
  --query 'cluster.{Name:name,Status:status,Version:version}'

kubectl get nodes -L topology.kubernetes.io/zone
kubectl get storageclass
kubectl get csidrivers
kubectl get pods -n kube-system
~~~

**Note:** if kubeconfig points to the wrong cluster/account, every diagnostic observation will mislead you. Confirm `kubectl config current-context`, namespace, and AWS role before acting.

### 20.2. Inspect permissions and EBS volume from a PV

~~~bash
kubectl get pvc -A
kubectl get pv -o wide
kubectl describe pv <actual-pv-name>
kubectl get volumeattachments
~~~

Example inspecting a known EBS volume:

~~~bash
aws ec2 describe-volumes \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1 \
  --query 'Volumes[0].{AZ:AvailabilityZone,Type:VolumeType,Size:Size,State:State,Encrypted:Encrypted,Attachments:Attachments}'
~~~

For cross-AZ errors, compare the volume's `AvailabilityZone` against `topology.kubernetes.io/zone` on the scheduled node, plus PV nodeAffinity/constraints.

### 20.3. Inspect EFS mount targets

~~~bash
aws efs describe-mount-targets \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1

aws efs describe-file-systems \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Record mount target subnets/AZs and IPs. Verify inbound SG TCP/2049 from the exact node/Pod SG. Without a reachable mount target, `kubectl get pvc Bound` alone does not prove a Pod can mount it.

### 20.4. Inspect CSI logs

For EKS add-ons running in `kube-system`, exact deployment/daemonset names vary by driver version:

~~~bash
kubectl get deploy,ds,pods -n kube-system | grep -E 'ebs|efs|csi'

kubectl logs -n kube-system deployment/ebs-csi-controller \
  --all-containers=true --tail=100
~~~

The EBS controller command above only works if the deployment matches that exact name; check `kubectl get` first. For EFS, inspect the actual deployment/controller and CSI node pods. **Do not look for secrets/access keys in logs and never publish logs containing sensitive information.**

### 20.5. Test real data and permissions

~~~bash
kubectl exec efs-writer-a -- sh -c 'id; ls -ln /shared'
kubectl exec efs-writer-a -- sh -c 'echo ok >> /shared/probe.txt'
kubectl exec efs-reader-b -- sh -c 'cat /shared/probe.txt'
~~~

If a Pod has broader write access than intended, audit POSIX/access points and Kubernetes RBAC/ServiceAccounts to ensure isolation. If only one component should write while others read, consider read-only mounts or dedicated access points/policies.

### Note on placeholder values

In sample commands, strings like `<actual-pv-name>` are **placeholders**—never run them verbatim in a shell because `<` can be interpreted as input redirection. Replace with real resource names. `fs-0123456789abcdef0` and `vol-0123456789abcdef0` are illustrative IDs, not live storage resources.

## 21. Monitoring EKS Storage via CloudWatch and Applications

### Signals to monitor

| Layer | Metrics / Events | When to Alert |
|---|---|---|
| **Kubernetes** | PVC/PV phase, Pod Pending, FailedAttachVolume/FailedMount, VolumeAttachment | PVC stays unbound or Pod mount stalls beyond threshold |
| **CSI controller** | CreateVolume/CreateAccessPoint errors, IAM Deny, rate limits, throttling | Repeated provision/attach/resize/snapshot failures |
| **EBS** | Read/Write IOPS, throughput, queue length, latency/supported metrics | Approaching limits, rising p95/p99 latency, high queue depth |
| **EFS** | PercentIOLimit, throughput, client connections, burst/IO metrics by throughput mode | Rising NFS latency/load, hitting performance caps |
| **EC2 nodes** | EBS bandwidth, ENI/volume attachment limits, CPU/memory, disk inodes | Node overloaded, capacity/attachment exhaustion |
| **Application** | File read/write latency, error codes, DB checkpoint/fsync, job retries | User SLOs degrade despite Bound PVCs |
| **AWS CloudTrail** | EBS/EFS create/delete APIs, key policy changes, IAM | Unexpected config changes or resource deletions |
| **AWS Budgets/Cost Explorer** | Provisioned EBS, snapshots, EFS storage/throughput/backups | Spending exceeds team/service thresholds |

**A `Bound` PVC does not prove the application is healthy.** An EFS mount can suffer high latency, hit app-level quotas, or have wrong permissions; an EBS volume can hit its IOPS cap. Measure inside Pods alongside CloudWatch and traces/logs.

### Cost management by storage class

- **EBS gp3:** billed for **provisioned capacity** even if Pods write very little; extra IOPS/throughput above baseline and snapshots incur separate charges. PVs kept under `Retain` can leave billable EBS volumes behind.
- **EFS:** capacity billed by stored data, with throughput/storage classes/tiers per configuration and API; heavy small-file/metadata workloads have different performance/cost profiles from large streaming workloads.
- **Cross-AZ traffic:** EBS is co-located in the node's AZ; EFS uses NFS over the network, requiring attention to mount target placement and transfer pricing.
- **Data lifecycle:** deleting a PVC does not necessarily erase underlying data; audit **orphaned volumes, access points, snapshots**, and backup retention before cleanup.
- **KMS:** customer-managed keys have separate fees/permissions; encryption does not replace backups.

Estimate totals using **AWS Pricing Calculator**, **AWS Cost Explorer**, and **AWS Budgets** per Region, propagating consistent tags/K8s labels to AWS resources where supported by CSI drivers/capabilities.

## 22. Four Storage Selection Scenarios

### Scenario A — Self-managed PostgreSQL on EKS

**Requirements:** Transactional data, random I/O, low latency, Pods can restart; needs backups and cross-AZ availability.

**Assessment:**

- Start with **EBS gp3/io2** on EC2 nodes sized by IOPS/latency benchmarks; each replica/stateful Pod gets its own PVC.
- Use a **StatefulSet/database operator** for identity/replication/quorum; never mount one RWO PVC into multiple DB primary replicas.
- Design **WAL/backups/point-in-time recovery**, crash-consistent snapshots, and failure drills.
- When AZ A fails, AZ A EBS volumes cannot attach to AZ B nodes; **fail over to a replica with its own volume in AZ B** or restore a new volume from snapshot.
- If the team prefers less DB operations overhead, evaluate **Amazon RDS/Aurora Multi-AZ** for managed HA and backups.

**Never choose EFS merely for RWX** to run multiple PostgreSQL primaries on the same directory; that risks data corruption.

### Scenario B — Java web app with shared file uploads

**Requirements:** 4 replicas across multiple AZs; each replica must read files written by other replicas.

**Assessment:**

- If the app requires a **POSIX filesystem** with file/path operations, choose **Regional EFS + RWX PVC** with proper access points and POSIX permissions.
- Provision mount targets across multiple AZs, TCP/2049, TLS, and EFS backups.
- If uploads are static images/documents/objects, reconsider the API/storage design and prefer **S3** to avoid shared NFS and simplify scaling.

### Scenario C — Retryable large-scale data batch jobs

**Requirements:** Many Pods process inputs from S3, write temporary files, and push outputs back to S3.

**Assessment:**

- Use `emptyDir`/ephemeral storage if intermediate files can be regenerated; no need to pay for persistent EBS/EFS.
- If Pods need heavy block I/O, use gp3 EBS with dedicated PVCs, measuring attach/provision latency and cleaning up storage afterward.
- Avoid RWX EFS for high-frequency scratch writes unless true cross-Pod file sharing is required.

### Scenario D — EKS Fargate service needing shared config/files

**Requirements:** Team chose Fargate to minimize node operations; the service needs to read/write shared files.

**Assessment:**

- **Cannot use EBS PVs directly on Fargate Pods.**
- Use **static EFS PV/PVC** when NFS is needed, with accurate access points, mount targets, and SGs.
- If dynamic per-PVC EFS access points are needed on Fargate, design **pre-provisioning outside Fargate** or switch compute to eligible EC2 nodes; do not assume dynamic EFS CSI provisioning works on Fargate.
- Verify POSIX, TLS, IAM, latency, and total filesystem cost.

## 23. Production Deployment Checklist

- [ ] Distinguished **emptyDir**, **PV/PVC**, **StorageClass**, **CSI driver**, and storage backends.
- [ ] Chose EBS/EFS/S3/managed DB based on access pattern, latency, RWX needs, durability, and total cost.
- [ ] Identified compute model (**EC2 nodes, EKS Auto Mode, or Fargate**) and matching provisioner/storage support.
- [ ] Standard EBS CSI uses `ebs.csi.aws.com`; EKS Auto Mode block uses `ebs.csi.eks.amazonaws.com` without swapping arbitrarily.
- [ ] For EBS, StorageClass sets `WaitForFirstConsumer`, proper volume type, encryption, expansion, and reclaim policy.
- [ ] For bound EBS PVCs, node/Pod placement matches AZ; migration/restore plan exists for AZ loss.
- [ ] For EFS, real file system/access points exist, mount targets span active AZs, and TCP/2049 is scoped to right SGs.
- [ ] EFS dynamic/static provisioning fits workload; **Fargate EFS uses static**, **Fargate does not attach EBS**.
- [ ] PVC access modes RWO/RWOP/RWX are properly understood, with application-level concurrency/locking controls.
- [ ] Controller IAM role via Pod Identity/IRSA or matching Auto Mode permissions and KMS key policies/grants verified.
- [ ] EBS at-rest and EFS at-rest/in-transit encryption configured properly, without confusing encryption with POSIX/app permissions.
- [ ] Snapshot controller/VolumeSnapshotClass installed where EBS CSI snapshots are needed, with snapshot/restore IAM.
- [ ] AWS Backup or EFS protection, DB-aware backups, replication, and RTO/RPO drills in place.
- [ ] Metrics/alerts active for PVC Pending, FailedMount, IOPS/throughput/latency, filesystem permissions, and cost.
- [ ] Plans exist for EBS PVC expansion (grow-only), driver-compatible performance updates, and rollbacks.
- [ ] Pod/StatefulSet/PVC/PV deletion scenarios reviewed; never wipe production data during lab cleanup.
- [ ] Tested app recovery across Pod/node/AZ failures, including data restore and backend/DB connectivity.
- [ ] Tags, quotas, snapshots, orphaned PVs/EBS/EFS access points, and AWS Budgets actively managed.

## 24. Exercises and Self-Check Questions

### Exercise 1 — EBS PVC across two AZs

**Prompt:** EKS has nodes in AZs A and B. The EBS StorageClass uses `volumeBindingMode: Immediate`; a PVC provisions an EBS volume in AZ A. The Pod has a `nodeSelector` for AZ B and hits `FailedAttachVolume`/Pending.

Tasks:

1. Explain why the EBS volume cannot attach to an EC2 node in AZ B.
2. Update the design **for new PVCs** to `WaitForFirstConsumer`.
3. For the PVC that already holds data, outline a snapshot/restore plan to a new volume in AZ B instead of editing PV nodeAffinity.
4. Design a recovery drill for an AZ A outage, including RTO/RPO.

### Exercise 2 — EFS RWX where one Pod cannot write

**Prompt:** Two Pods mount the same `ReadWriteMany` EFS PVC; Pod A writes successfully, yet Pod B fails with `Permission denied`.

Inspect: `kubectl describe`, access point IDs, `runAsUser`, `runAsGroup`, `fsGroup`, file owner/mode, `directoryPerms`, and EFS file system policy. Why does **RWX** not automatically mean every Pod's Linux user can write every file?

### Exercise 3 — CSI snapshots and database backups

**Prompt:** A PostgreSQL StatefulSet uses two EBS PVCs for data and WAL, targeting a 5-minute RPO and 30-minute RTO.

Describe:

- The snapshot CRDs/controllers that must be installed.
- How to obtain a consistent recovery point across database files and WAL.
- Why a snapshot every 12 hours fails a 5-minute RPO.
- How to automate backup/restore and verify startup in another AZ.
- When RDS/Aurora Multi-AZ is a lower-ops alternative.

### Exercise 4 — EKS Auto Mode migration

**Prompt:** A cluster has existing PVCs on `ebs.csi.aws.com` and wants to migrate to EKS Auto Mode `ebs.csi.eks.amazonaws.com`.

Explain why you cannot simply edit the provisioner on the existing StorageClass; design the workflow for PVC/PV inventory, snapshot/restore, verifying the Auto Mode StorageClass, `allowedTopologies`, KMS, application downtime, and post-migration data validation.

### Exercise 5 — Cost analysis

A workload uses:

- 20 gp3 EBS volumes, 100 GiB each, some needing extra IOPS/throughput.
- One Regional EFS file system holding 300 GiB of shared data.
- Periodic EBS snapshots and AWS Backup for EFS.

Build a Regional cost estimation table covering: provisioned capacity/IOPS/throughput, snapshots, EFS tier/throughput, backup retention, KMS, cross-AZ transfer, and logging. Propose tracking mechanisms to avoid paying for orphaned volumes and stale EFS data.

### Short-answer questions

1. **How does a PVC differ from a PV?** A PVC is the application's storage request; a PV represents the provisioned/bound storage resource.
2. **What provisioner does the standard EBS CSI driver use?** `ebs.csi.aws.com`; EKS Auto Mode uses `ebs.csi.eks.amazonaws.com`.
3. **Can one EBS volume attach directly to two nodes in two different AZs?** No; an EBS volume belongs to a single AZ. EBS Multi-Attach is a specialized single-AZ capability and does not turn EBS CSI into standard NFS.
4. **Does RWO strictly mean one single Pod?** Not necessarily; RWO restricts access to one node. RWOP enforces single-Pod exclusivity where supported.
5. **Does EFS RWX automatically prevent race conditions?** No. Applications need proper locking/consistency and POSIX permissions.
6. **Can an EKS Fargate Pod attach an EBS PV?** No.
7. **Can Fargate use dynamic EFS access point PVCs?** Not via dynamic EFS CSI provisioning on Fargate; use static PVs.
8. **Does changing a StorageClass's `reclaimPolicy` automatically update existing PVs?** Do not assume so; already provisioned PVs retain their own reclaim policy that must be inspected.
9. **Is an EBS VolumeSnapshot automatically an application-consistent backup?** No; DB-aware/quiesced backups and restore tests are needed.
10. **Does a 5Gi EFS PVC request block writing a 6th GiB file?** Not by default; EFS scales elastically and PVC capacity is not a hard quota.

## 25. Summary

In Kubernetes on EKS, **PV/PVC/StorageClass** let applications request storage via the Kubernetes API, while **CSI drivers** connect those requests to AWS storage backends.

- **EBS CSI** suits durable block storage, random I/O, and StatefulSets with per-replica volumes; requires managing **AZ topology**, IAM, snapshots, resizing, and node failures.
- **EFS CSI** suits shared NFS files across multiple Pods/nodes/AZs; requires managing **mount targets, TCP/2049, IAM/POSIX, TLS, access points**, and backups.
- **EKS Auto Mode and EKS Fargate** have their own support boundaries; **never swap provisioners blindly** or assume Fargate handles EBS like EC2 nodes.

Sound storage design integrates **Region/AZ, IAM/KMS, VPC, Java/database applications, resilience, monitoring, and budget**. A `Bound` PVC only proves Kubernetes-level binding; what matters more is **consistent data, reads/writes meeting SLOs, tested recoverability, and protection against leaks or loss from misconfigured policies/lifecycles**.

### Official Documentation for Reference

- [Amazon EKS – Use application data storage for your cluster](https://docs.aws.amazon.com/eks/latest/userguide/storage.html)
- [Use Kubernetes volume storage with Amazon EBS](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html)
- [Use elastic file system storage with Amazon EFS](https://docs.aws.amazon.com/eks/latest/userguide/efs-csi.html)
- [Amazon EKS Auto Mode – Create a storage class](https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html)
- [Amazon EKS Auto Mode – Sample stateful workload](https://docs.aws.amazon.com/eks/latest/userguide/sample-storage-workload.html)
- [Amazon EKS Fargate storage considerations](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html)
- [Enable snapshot functionality for CSI volumes](https://docs.aws.amazon.com/eks/latest/userguide/csi-snapshot-controller.html)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
- [Kubernetes Volume Snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [Amazon EFS User Guide](https://docs.aws.amazon.com/efs/latest/ug/)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/) and [Amazon EFS pricing](https://aws.amazon.com/efs/pricing/)

**Before deploying to production:** verify support for your **cluster Kubernetes version, EKS platform, node type, CSI driver version, Region, and IAM setup**, benchmark performance, test backup/restore, and validate cost models against your real account.
