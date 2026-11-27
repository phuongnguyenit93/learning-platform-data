# Choosing Between GKE Standard and GKE Autopilot

A Java development team wants to migrate an order service from Compute Engine to Kubernetes to run multiple replicas, perform zero-downtime updates, and autoscale as traffic grows. The administrator asks: **should we choose GKE Standard or GKE Autopilot?** Both options run Kubernetes on Google Cloud, but they differ in node control, operational responsibility, default security policies, resource management, and billing mechanisms.

**Google Kubernetes Engine (GKE)** provides managed Kubernetes with a control plane operated by Google Cloud. **Standard** is suitable when an organization needs to directly manage node pool configuration and capacity. **Autopilot** lets Google Cloud manage most of the node infrastructure, allocate resources based on workload requests, and enforce preconfigured guardrails. Current GKE documentation also allows running **Autopilot ComputeClasses inside a Standard cluster**, so the choice does not have to be "one workload type across the entire cluster."

This lesson belongs to the **GKE Fundamentals** chapter of the **CLOUD_PROVIDERS_GCP** module. Through practical deployment scenarios, learners will connect GKE with project organization, IAM, VPC, Compute Engine, Cloud Run, storage, databases, release automation, reliability monitoring, and cost optimization.

After this lesson, you will be able to:

- Distinguish **control plane**, **node**, **node pool**, **Pod**, **Deployment**, **Service**, and what Google Cloud manages in each mode.
- Choose Standard or Autopilot based on special privilege needs, hardware, operations, security, performance, and budget.
- Understand how **cluster mode** and **workload mode** differ, and know the role of **GKE ComputeClasses**.
- Create a lab cluster with `gcloud`, connect with `kubectl`, and deploy a containerized Java application.
- Plan `resources.requests`/`limits`, HPA, node autoscaling, Pod placement, and version updates.
- Explain **node-based** versus **Pod-based** billing, including cases where Autopilot uses specialized hardware.
- Prepare workload migration plans, review security/monitoring, and troubleshoot `Pending` or `Rejected` Pods.

> **Scope:** the cluster names, projects, and images below are examples. Do not run commands that create clusters, LoadBalancer Services, or storage resources in a production project without approval. GKE, VMs, IPs, PersistentVolumes, network egress, and related services may incur charges.

## 1. Which Kubernetes Components Does GKE Manage?

A Kubernetes cluster has a **control plane** and a set of **worker nodes**. The control plane receives API requests, stores desired state, schedules workloads, and reconciles state. Worker nodes run Pods; a Pod contains one or more containers sharing declared networking and storage.

~~~mermaid
flowchart TD
  A["Developer / GitOps / kubectl"] --> B["GKE Kubernetes API"]
  B --> C["Google-managed control plane"]
  C --> D{"Choose operational mode"}
  D --> E["Standard: node pools configured by you"]
  D --> F["Autopilot: GKE provisions and manages nodes"]
  E --> G["Kubernetes Pods"]
  F --> G
  G --> H["Service / Gateway / Ingress"]
  H --> I["Load Balancer / users"]
  G --> J["Cloud SQL / Cloud Storage / Pub/Sub"]
~~~

This diagram is conceptual; a cluster does not necessarily have an Internet-facing load balancer, and a Standard cluster can also run Autopilot workloads via ComputeClasses when supported prerequisites are met.

| Component | Role | Example |
|---|---|---|
| **Cluster** | Administrative boundary for the Kubernetes API, network/security configuration, and resources | `orders-prod` |
| **Control plane** | API server, scheduler, controllers, and Kubernetes state | Managed by GKE in both Standard and Autopilot |
| **Node** | VM/infrastructure running kubelet and Pods | Compute Engine node or Autopilot-managed node |
| **Node pool** | Group of nodes sharing configuration, machine type, and autoscaling | `general-pool` in Standard |
| **Pod** | Smallest schedulable workload unit | A Java API container |
| **Deployment** | Manages replica count and Pod rollouts | `orders-api`, 3 replicas |
| **Service** | Provides a stable address and distributes traffic to Pods | `ClusterIP` or `LoadBalancer` |
| **Ingress/Gateway** | Routes HTTP(S) traffic to services by host/path | API with TLS via a load balancer |
| **HPA** | Adjusts Pod replica count based on metrics | Scaling from 2 to 10 Pods |

**Key point:** GKE does not operate your Java code, tune your SQL queries, or back up your database for you. You remain responsible for images, container configuration, access control, workloads, releases, SLOs, and data dependencies in both modes.

## 2. GKE Standard: Control Over Node Pools and Infrastructure

With a **Standard cluster**, administrators actively choose and configure node pools: machine family, VM type, sizing, disks, GPUs, node zones, autoscaling strategy, and many Kubernetes/node-level settings. GKE still manages the control plane and can automatically repair/upgrade nodes when enabled, but **you manage node configuration and capacity utilization**.

~~~text
GKE Standard cluster
  ├── Control plane (Google-managed)
  ├── Node pool: web-pool
  │     ├── VM e2-standard-4
  │     └── VM e2-standard-4
  ├── Node pool: batch-pool
  │     └── Spot VM / suitable machine family
  └── Deployments, Services, HPA, Policies
~~~

Standard fits well when you:

- Need granular control over **machine types, images, node labels/taints, boot disks, and custom node settings**.
- Have **DaemonSets** or workloads requiring elevated privileges or host access incompatible with Autopilot restrictions.
- Need to optimize costs at the **node pool, reservation, committed use discount**, bin-packing, and baseline VM level.
- Have legacy applications, networking, or storage tied to specific node configurations.
- Have a platform/SRE team with cluster/node operating procedures that accepts capacity planning responsibility.

**Trade-off:** VMs provisioned for a Standard node pool still incur charges while running **even if Pods use little of their resources**. Oversized node pools, high min-nodes, or overly low Pod requests easily cause waste; conversely, insufficient nodes or quota leave Pods Pending.

### Standard Does Not Mean "Everything Is Manual"

GKE Standard still supports **node auto-upgrade, node auto-repair, cluster autoscaler, HPA, release channels, managed control plane**, and many other automated features. The core difference is **the ability and responsibility to configure more components**, not that GKE refuses to manage infrastructure.

## 3. GKE Autopilot: Focus on Declaring Workloads

With a **dedicated Autopilot cluster**, Google Cloud manages node infrastructure, node provisioning/scaling, bin packing, and applies recommended configurations for security, reliability, and updates. You declare **Pods, CPU/memory requests, volumes, policies, networking, and applications**; GKE decides how to provision appropriate nodes.

~~~text
GKE Autopilot cluster
  ├── Control plane (Google-managed)
  ├── Managed node infrastructure (GKE-orchestrated)
  │     └── Nodes created per Pods and ComputeClasses
  ├── Deployment: orders-api replicas=3
  ├── requests: CPU / memory / ephemeral storage
  └── Services, HPA, Policies, Observability
~~~

Autopilot typically fits well when:

- Web APIs, microservices, background workers, and batch jobs run in **containers that do not require host privileges**.
- You want to reduce operational time spent on node pools, upgrades, scaling, and bin packing.
- Development teams want to focus on Kubernetes manifests, CI/CD, GitOps, and SLOs.
- You prefer a tightly controlled set of **default security guardrails**.
- Workload volume fluctuates and you want costs tied to the resources workloads actually request.

**Autopilot is not Cloud Run.** You still manage Kubernetes resources, namespaces, Services, HPAs, Deployments, and network policies. Cloud Run has a higher-level application deployment model; if you only have a simple HTTP service that does not need Kubernetes features, compare Cloud Run as well before creating a GKE cluster.

### Autopilot's Limits Do Not Mean "No GPUs"

Autopilot supports certain GPUs, TPUs, Arm, machine series, and ComputeClasses depending on documentation, region, and version. When **specific hardware** is required, GKE may provision dedicated nodes and apply **node-based billing** with an Autopilot management premium; not every Autopilot workload is billed solely by Pod requests. Verify feature support and quotas for the chosen hardware type.

## 4. Comparing Standard and Autopilot Across Technical Criteria

| Criterion | **Standard** | **Autopilot** |
|---|---|---|
| Control plane | Managed by Google Cloud | Managed by Google Cloud |
| Worker nodes | You define node pools and policies; GKE supports repair/upgrade/scaling | Google Cloud provisions and manages nodes per workload |
| Machine type / disk | Direct, flexible control | Declared via workload/ComputeClass and supported options |
| Node count | Node pool size and cluster autoscaler | GKE adjusts node infrastructure based on Pod demand |
| Kubernetes Pods / Services | Managed by developer/platform | Managed by developer/platform |
| Default security | Flexible settings; requires proactive hardening | Built-in guardrails and automatic restrictions |
| Privileged containers / host access | Available per cluster policies and permissions | Generally restricted; supported exceptions exist for approved partners/system |
| Cost optimization | Manage node utilization, packing, CUDs/Spot | Pod-based for general-purpose; node-based for specialized hardware |
| OS/node changes | More direct control | No unrestricted SSH/node administration like Standard |
| Pod autoscaling | Configure HPA/VPA or appropriate controllers yourself | Still must design HPA/VPA to scale Pod counts |
| Regional/HA | Can choose zonal or regional architecture | Autopilot clusters are designed on a managed regional model |
| Quotas and limits | Node/CPU, IP/Pod, API quotas, storage, LB | Pod requests, resource bounds, quotas, and scheduling limits |
| Operations | High control, higher platform effort | Less node control, reduced platform effort |

**Neither mode is universally cheaper or faster in every case.** A Standard cluster with well-utilized VMs and strong discounts can be very cost-competitive. An Autopilot cluster with high requests, many always-on replicas, or dedicated GPU requirements may cost more than anticipated.

## 5. Distinguishing Cluster Mode and Workload Mode in Modern GKE

Older documentation often presents GKE as two separate boxes: **Standard cluster** and **Autopilot cluster**. Current GKE documentation adds the concept of **Autopilot mode for workloads inside a Standard cluster** via **ComputeClasses**.

| Configuration | Which Workloads Run? | Who Manages the Nodes? |
|---|---|---|
| **Dedicated Autopilot cluster** | Only Autopilot workloads | GKE manages the nodes |
| **Traditional Standard cluster** | Standard workloads on node pools you create | Platform manages node pool settings |
| **Standard cluster with Autopilot ComputeClass** | Standard workloads + Pods selecting an Autopilot class | GKE manages nodes for Autopilot workloads; platform manages remaining node pools |
| **Standard cluster configured with Autopilot by default** | Most workloads use Autopilot per default config, with override capability | Depends on ComputeClasses and cluster configuration |

**Version requirements:** running Autopilot workloads in a Standard cluster requires a supported GKE version along with matching network/security prerequisites; documentation specifies a minimum of **GKE 1.34.1-gke.1829001** for Autopilot ComputeClasses, while newer features such as setting an Autopilot class as the cluster default require newer versions. Do not assume an older Standard cluster will support it immediately just by adding a label.

**Cluster mode is long-lived:** when creating a dedicated Autopilot cluster, mandatory Autopilot settings are **immutable**; you cannot simply convert it into a dedicated Standard cluster by toggling a flag. Changing cluster mode or immutable attributes typically requires creating a new cluster, deploying/migrating workloads, and shifting traffic in a controlled manner.

### What Is a ComputeClass?

A **GKE ComputeClass** is a custom Kubernetes resource declaring compute profiles (such as machine series, Spot, fallback behavior, accelerators, or the Autopilot container-optimized compute platform), allowing workloads to choose a profile rather than hardcoding node details.

Several **built-in Autopilot ComputeClasses** such as `autopilot` and `autopilot-spot` are provided by GKE on supported versions. Autopilot clusters use this mechanism for general-purpose workloads by default; Standard clusters can allow compatible Pods to select a ComputeClass so GKE manages dedicated nodes for them.

**Simply adding `cloud.google.com/compute-class: autopilot` is not enough**: the cluster must meet version, VPC-native networking, Shielded GKE Nodes, and related system prerequisites. You may also need at least one untainted Standard node pool for system Pods that do not run on Autopilot-managed nodes. Check the documentation before applying this in Standard production.

## 6. Division of Operational Responsibilities

| Operational Task | Standard | Autopilot |
|---|---|---|
| Kubernetes API/control plane availability | Google Cloud | Google Cloud |
| Node pool and machine type planning | Platform | Mostly GKE; platform chooses ComputeClass/hardware when needed |
| Node OS patching/upgrades | Platform configures auto-upgrade and owns policy | GKE automatically manages more steps |
| Node autoscaler | Platform enables/sets bounds and monitors | GKE adjusts per Pod demand |
| App image, Java runtime, dependencies | Application team | Application team |
| K8s Deployments/Services/HPA | Application/platform | Application/platform |
| IAM, Workload Identity, secrets | Application/platform | Application/platform |
| VPC, ingress/egress, DNS, LB, firewalls | Platform/network | Platform/network, except portions automatically provisioned by GKE |
| Backups, persistent data, migrations | Application/data platform | Application/data platform |
| SLOs, releases, runbooks, security incidents | Application/SRE | Application/SRE |
| Quotas, cost allocation, budgets | FinOps/platform | FinOps/platform |

Autopilot reduces **node-related** toil; it does not remove application backend design responsibilities. If Cloud SQL is a single non-HA instance or an API lacks a readiness probe, running on Autopilot will not make the application fault-tolerant on its own.

## 7. Choosing Based on Five Practical Questions

1. **Does the workload require special host privileges?** If it strictly requires privileged containers, host namespaces, unsafe sysctls, kernel tuning, or security agents unsupported by Autopilot, favor Standard or an alternative design. Verify policy support for Autopilot-approved partner DaemonSets.
2. **Do you need specific machines, reservations, or GPUs/TPUs?** Standard provides direct node pool control; Autopilot also supports specialized hardware through supported capabilities, though pricing mechanics may differ.
3. **Do you have a platform team capable of operating Kubernetes?** If staffing is lean and workloads are compatible, Autopilot reduces operational overhead significantly.
4. **Is resource demand predictable?** High steady baseline with good utilization and CUDs: Standard is worth calculating. Many small Pods with spiky load: compare Autopilot Pod-based billing.
5. **What do organizational policies require?** Review IAM, networking, compliance, version/release channel, private access, quotas, and data residency before locking in a mode.

### Quick Selection Matrix

| Scenario | Initial Choice | Why |
|---|---|---|
| Stateless Java API, fast rollout, lean node operations | **Autopilot** | Focus on the app and minimize node operations |
| Platform team requires privileged DaemonSets or specialized host access | **Standard** | Requires deeper node and Pod configuration |
| Many small web services autoscaling by hour | **Autopilot** | Pod-request billing for general-purpose workloads |
| Cluster running legacy systems tightly coupled to kernel/node type | **Standard** | Infrastructure compatibility and node control |
| Existing Standard cluster with a few services not needing special nodes | **Autopilot ComputeClass in Standard**, when eligible | Combine both modes per workload |
| GPU training/batch | **Evaluate both** | Check availability, accelerator types, quotas, and node-based billing |
| Short-lived dev lab | **Depends on cost model and lab** | Cluster fees and node/Pod usage still apply |
| Requirement for zero nodes when idle | **Evaluate cluster/version and Autopilot** | Does not imply total cost is zero |

**Avoid rigid slogans:** "production always needs Standard" is false; GKE recommends Autopilot for most compatible production workloads. "Autopilot cannot use GPUs/DaemonSets" is also inaccurate as an absolute claim; check current hardware support and exceptions.

## 8. Preparing the Project and Lab Cluster Configuration

A lab cluster requires:

- A Google Cloud project with billing enabled and the **Kubernetes Engine API** (`container.googleapis.com`) enabled.
- Appropriate IAM permissions for the cluster creator, such as `roles/container.clusterAdmin` at the appropriate scope, plus network/service account permissions if configured separately.
- A region/zone with GKE availability and quota; examples below use `asia-southeast1` and `asia-southeast1-a`, but verify actual machine availability and region.
- VPC/subnet and Secondary IP ranges for Pods/Services if using custom networking; consider a **VPC-native cluster**.
- Cloud SDK with `gcloud`, `kubectl`, **gke-gcloud-auth-plugin**, and connectivity to the control plane.
- Cost estimation: cluster management fee, Standard nodes or Autopilot Pods/nodes, disks, load balancers, IPs, egress, and logging.

### Creating a Sample Autopilot Cluster

~~~bash
PROJECT_ID="my-gke-lab-project"
REGION="asia-southeast1"
AUTO_CLUSTER="orders-autopilot-lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com

# Create a dedicated Autopilot cluster.
gcloud container clusters create-auto "$AUTO_CLUSTER" \
  --location="$REGION" \
  --release-channel=regular

gcloud container clusters describe "$AUTO_CLUSTER" \
  --location="$REGION" \
  --format="yaml(name,location,autopilot,releaseChannel,status)"

gcloud container clusters get-credentials "$AUTO_CLUSTER" \
  --location="$REGION"
kubectl get nodes
kubectl get namespaces
~~~

An Autopilot cluster with no user workloads yet may have no application worker nodes; once you create a Deployment, GKE provisions the needed capacity automatically. **Do not interpret having few or no nodes before deploying as a broken cluster.** Also, `create-auto` defaults may evolve by release channel; verify the resulting cluster config before production use.

### Creating a Sample Standard Cluster

~~~bash
PROJECT_ID="my-gke-lab-project"
ZONE="asia-southeast1-a"
STD_CLUSTER="orders-standard-lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com

# A zonal Standard cluster with an initial node pool you choose.
gcloud container clusters create "$STD_CLUSTER" \
  --location="$ZONE" \
  --num-nodes=2 \
  --machine-type=e2-standard-2 \
  --release-channel=regular

gcloud container clusters describe "$STD_CLUSTER" \
  --location="$ZONE" \
  --format="yaml(name,location,nodePools,releaseChannel,status)"

gcloud container clusters get-credentials "$STD_CLUSTER" \
  --location="$ZONE"
kubectl get nodes -o wide
~~~

The zonal cluster in this example uses **a single zone**, so it is not a zone-fault-tolerant production design. Standard **can also create regional clusters** when HA is required. Do not compare "zonal Standard" against "regional Autopilot" and assume every HA difference comes from the mode itself.

**Two independent CLI snippets:** creating both clusters will incur charges for both. In a lab, run one cluster at a time or use separate projects if comparing side by side, then clean up resources safely.

## 9. Deploying the Same Java API on Both Modes

Mode is an infrastructure decision; an application's Kubernetes Deployment can often use the same manifest as long as it complies with Autopilot and Standard cluster requirements.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
              ephemeral-storage: "1Gi"
            limits:
              cpu: "1000m"
              memory: "2Gi"
              ephemeral-storage: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - port: 80
      targetPort: 8080
~~~

This is a **reference manifest**, not a complete Java application: you must have a real image in Artifact Registry, grant read access to the runtime image-pull identity, and implement the `/ready` and `/health` endpoints. `ClusterIP` provides internal cluster access only; external Internet access requires an Ingress/Gateway or an appropriate LoadBalancer Service.

**One key difference:** Autopilot may **adjust requests** based on the ComputeClass's minimums, maximums, and CPU:memory ratios, and may also inject defaults when fields are omitted. Values of 500m CPU and 1Gi memory in this example may be accepted on compatible configurations, but check how admission modified the Pod rather than assuming values remain unchanged across every architecture and version.

### Apply and Observe

~~~bash
# Assumes orders-api.yaml has been prepared outside this lesson.
kubectl apply -f orders-api.yaml

kubectl get deployments,pods,services -l app=orders-api
kubectl rollout status deployment/orders-api
kubectl describe deployment orders-api
kubectl get pods -l app=orders-api -o wide
kubectl get events --sort-by=.lastTimestamp
~~~

On a Standard cluster, Pods are placed on nodes with enough free CPU/memory. On Autopilot, GKE may provision new nodes, taking additional time before Pods become `Running`, especially on the first deploy. **A Pod staying Pending for a few minutes is not necessarily an error**, but check events to distinguish normal provisioning from quota, constraint, or image pull failures.

## 10. Requests, Limits, and Pod Scaling

In Kubernetes:

- **`requests.cpu` / `requests.memory`** govern placement and serve as the sizing/billing basis in Pod-based Autopilot.
- **`limits.cpu` / `limits.memory`** define CPU throttling thresholds and memory caps; exceeding the memory limit can trigger `OOMKilled`.
- **`ephemeral-storage`** is temporary container storage (writable layer, logs, etc.) and does not replace PersistentVolumes or Cloud Storage.
- **HPA** adjusts workload replica counts based on CPU/memory or integrated metrics.
- **Node autoscaling** scales node capacity up/down so Pods have room to run; in Standard you manage node pool autoscaling, while in Autopilot GKE manages node provisioning.

| Scenario | Standard | Autopilot |
|---|---|---|
| Deployment scales 3 → 8 Pods | HPA creates Pods; cluster autoscaler adds VMs if needed and configured on the node pool | HPA creates Pods; GKE automatically provisions additional node capacity |
| CPU request too small | May ease scheduling initially, but increases contention/OOM risk if memory is mis-sized | Requests may be bumped up to valid minimums/ratios, affecting billing |
| No HPA configured | Replicas remain at the Deployment spec count | Replicas also remain at the Deployment spec count |
| Only node autoscaler enabled | Does not automatically increase Pod replicas without an active HPA | Google scales nodes to match Pod demand, but does not increase replicas on traffic spikes |

### Sample HPA

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

An HPA CPU utilization target of 65% is measured relative to **CPU requests**, not 65% of total cluster cores. For example, for a Pod requesting `500m`, the target is roughly `325m` per metric collection rules; HPA aggregates across eligible Pods using its stabilization algorithms. This is **not a guarantee of holding exactly 65% instantaneously**.

~~~bash
kubectl apply -f orders-api-hpa.yaml
kubectl get hpa orders-api-hpa
kubectl describe hpa orders-api-hpa
kubectl top pods
~~~

If HPA shows `unknown` for the CPU metric, inspect the metrics server/pipeline, container requests, permissions, and how long the Pods have been running. Do not raise `maxReplicas` indefinitely to work around a database bottleneck.

## 11. Billing: Pod-Based and Node-Based Are Not the Same

A common mistake when comparing modes is saying **"Autopilot only charges by Pods"** without considering hardware, or **"Standard is always cheaper because you manage nodes yourself"** without factoring in idle capacity and operational effort.

### Standard: Primarily Node-Based

In Standard node pools, compute charges are based on **Compute Engine VMs**, boot disks, networking, and related infrastructure components. A node running 24 hours where Pods use only 20% CPU is still billed for the provisioned VM capacity; committed use discounts or Spot VMs may apply per policy.

~~~text
Total Standard cost, approximate model
  = cluster management fee
  + sum(node VM-hours × VM price)
  + boot disks / PersistentVolumes / networking / LB
  + logging / monitoring / dependent services
~~~

The **node autoscaler** can scale down VMs within node pool bounds; however, node pool min size, system Pods, PodDisruptionBudgets, Pod requests, and zonal constraints can keep a baseline level of capacity running. In Standard, cost control requires tracking **node utilization** and allocated-but-unused CPU/memory.

### Autopilot General-Purpose: Pod-Based

For **general-purpose** workloads on the Autopilot container-optimized compute platform or corresponding built-in ComputeClasses such as Balanced/Scale-Out in Autopilot clusters, GKE uses **Pod-based billing**: charges are primarily based on the **requested** CPU, memory, and ephemeral storage of Pods scheduled onto nodes.

~~~text
Total Autopilot general-purpose cost, approximate model
  = cluster management fee
  + sum(Pod requested CPU/memory/ephemeral-storage × billable duration)
  + PersistentVolumes / networking / LB
  + logging / monitoring / dependent services
~~~

In this model, node size and unallocated node capacity are not the primary billing unit for workloads; certain system Pods and node overhead are not billed the same way as user Pods. However, **a scheduled Pod in `CrashLoopBackOff` or `ImagePullBackOff` may still be billed**, whereas an unscheduled Pod is not billed under this model.

**Watch minimum/default requests:** if `resources.requests` is omitted, Autopilot supplies defaults; if CPU/memory falls outside ComputeClass bounds or ratios, GKE may bump requests to valid levels. Billing is based on **post-admission requests**, not the numbers a developer initially assumed. For example, an app that only needs 200m CPU but omits requests may receive higher default requests. Do not try to optimize by setting `0` expecting free compute.

### Autopilot Specialized Hardware: Node-Based

When workloads select **GPUs, TPUs, or specific machine series/accelerators** via selectors or ComputeClasses, Autopilot may provision dedicated VMs and bill for the **entire node's Compute Engine resources + Autopilot management premium**. If a workload only uses part of a GPU node, you can still pay for the whole node; plan packing, quotas, scheduling, and node lifetime carefully.

| Workload | Mode / Resource | Estimation Approach |
|---|---|---|
| Standard web API on an e2 node pool | Node-based | VM-hours × node count; Pod utilization determines waste |
| Autopilot API without specialized hardware | Pod-based | Pod requests × scheduled Pod duration |
| Autopilot batch selecting a specific GPU/machine series | Node-based + premium | VM/accelerator hours and ability to pack onto nodes |
| Autopilot ComputeClass in a Standard cluster | Per Autopilot workload type | General-purpose Pod-based; hardware-specific node-based |
| Standard GPU pool | Compute Engine nodes + GPUs | Node count, GPU type, disks, and applicable discounts |

### Cluster Management Fees and Easily Forgotten Items

Both Standard and Autopilot may incur a **cluster management fee** per the GKE pricing schedule; certain monthly free-tier credits apply to eligible cluster types and Billing accounts. Never treat the "GKE free tier" as free VMs, Pods, load balancers, networking, or Cloud SQL.

Beyond compute, budget for:

- Persistent Disks, Filestore, Cloud Storage FUSE, and operations.
- External/Internal Load Balancers, public IPs, Cloud NAT, and network egress.
- Artifact Registry, Secret Manager, Cloud Logging/Monitoring, and security products.
- Buffer quota/capacity for rolling updates, HPA bursts, and Pod disruptions.
- SRE/platform engineering time: not a line item on the Google Cloud invoice, but a real business cost.

Consult [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) and the [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator) before deciding. **Do not compare solely on raw per-vCPU unit prices** when the two options differ in availability, performance, and operational responsibilities.

### Conditional Comparison Exercise

Suppose 10 APIs each run 3 steady Pods, and each Pod declares `500m` CPU and `1Gi` memory. Total application requests are:

~~~text
Pod count       = 10 × 3 = 30
CPU requests    = 30 × 0.5 = 15 vCPU
Memory requests = 30 × 1 GiB = 30 GiB
~~~

With **Autopilot general-purpose**, the 30 Pods contribute to billable requests over their scheduled duration plus any admission adjustments, on top of cluster, storage, and network fees. With **Standard**, you must select enough nodes to fit 15 vCPU and 30 GiB **plus system overhead**, while budgeting headroom for zone failure tolerance and rollout surge. Picking oversized VMs with only a few Pods easily causes waste in Standard; well-packed node pools with discounts can yield different economics.

This is not an exact cost comparison because regional pricing, availability tiers, load profiles, CUDs, CPU architectures, and runtime hours are not included. Measure actual requests, SLOs, and costs in a test environment before optimizing.

## 12. Security: Autopilot Guardrails vs. Standard Control

In an Autopilot cluster, GKE enforces preconfigured policies to restrict Pod configurations that increase host access risk:

- **Privileged containers** are blocked by default, except for certain verified and supported system/partner cases.
- **Host namespaces, HostProcess, unsafe sysctls**, and many forms of host access are restricted.
- **`hostPath` volumes** are restricted, with limited read-only exceptions for logs per documentation.
- Linux capabilities are controlled; certain capabilities or networking modes have opt-in mechanisms by version/feature.
- Some Pod settings are automatically mutated or rejected by **admission controllers** when violating guardrails.

Standard is more flexible: administrators can permit privileged Pods or host-level agents when required. **Flexibility does not mean secure by default**; organizations must proactively enforce Pod Security Standards, policy engines, container image scanning, least privilege, auditing, and node patching.

### IAM and Kubernetes RBAC

There are two authorization layers:

1. **Google Cloud IAM:** who can create/modify clusters, manage networks, and call Google APIs.
2. **Kubernetes RBAC:** who can read, create, modify, or delete namespaces, Deployments, Secrets, and other K8s resources once connected to the control plane.

| Actor | Action | Scoping Approach |
|---|---|---|
| Platform cluster admin | Create/modify clusters, node pools, and cluster policies | `roles/container.clusterAdmin` on the required project |
| Developer | Deploy into an application namespace | Appropriate IAM + namespace-scoped Kubernetes Role/RoleBinding |
| CI/CD release identity | Apply approved manifests | Minimal Kubernetes permissions; separate prod and dev |
| Java runtime Pod | Access Cloud SQL/Storage/Pub/Sub | Workload Identity Federation for GKE and resource-level IAM roles |
| Auditor/SRE | Read logs, metrics, and cluster state | Read-only permissions, not `cluster-admin` by default |

**Workload Identity Federation for GKE** allows workloads inside Pods to use a Kubernetes ServiceAccount tied to a Google Cloud IAM principal via supported mechanisms, avoiding long-lived JSON service account keys in container images or Secrets. Exact setup depends on the cluster and workload, but the **least privilege** principle applies equally to Standard and Autopilot.

### Inspecting Manifests Before Choosing a Mode

If an application requires:

~~~yaml
securityContext:
  privileged: true
  runAsUser: 0
volumes:
  - name: host
    hostPath:
      path: /var/lib
~~~

**Do not deploy this manifest unchanged onto Autopilot and expect it to be accepted.** Both `privileged` and `hostPath` can violate guardrails. `runAsUser: 0` is **not always blocked** in Autopilot, as policies may allow root inside a container under certain conditions. Always inspect the exact field rejected by policy rather than generalizing "Autopilot bans all root containers."

The security team can replace host-level agents with observability/scanning options that do not require privileged DaemonSets, or run specialized components in a Standard node pool/cluster.

## 13. Networking, IP Addressing, and Application Access

GKE uses VPC networking so Pods and nodes can reach other services. A production design must account for:

- **VPC-native IP addressing:** subnets and secondary ranges for Pods/Services, avoiding IP exhaustion when HPA scales replicas up.
- **Private nodes / control plane access:** restricting external IPs and Kubernetes API access, configuring Cloud NAT/Private Google Access as needed.
- **Ingress:** Service type LoadBalancer, GKE Ingress, or Gateway API for inbound requests; Cloud DNS/TLS/Cloud Armor for public endpoints where appropriate.
- **Egress:** VPC firewalls, routing, Cloud NAT, Secure Web Proxy, or organizational policies controlling outbound Internet traffic.
- **NetworkPolicy and GKE Dataplane V2:** restricting unnecessary pod-to-pod traffic.
- **Service-to-service authentication:** never treat "inside the same cluster" as permission to call every API.

### Illustrative Diagram for a Java API

~~~mermaid
flowchart TD
  A["Internet client"] --> B["Cloud DNS"]
  B --> C["External Application Load Balancer + TLS"]
  C --> D["GKE Service / Gateway"]
  D --> E["Java API Pods: Standard or Autopilot"]
  E --> F["Cloud SQL private IP"]
  E --> G["Cloud Storage API"]
  E --> H["Pub/Sub"]
  I["IAM / Workload Identity"] --> E
  J["NetworkPolicy / VPC firewall"] --> E
~~~

**Choosing a mode does not automatically create network security:** if you declare a Kubernetes Service of type `LoadBalancer`, Google Cloud may provision LB and IP resources per configuration. If access should be VPC-internal only, select the proper internal LB type or networking policy rather than simply switching from Standard to Autopilot.

### GKE and Cloud Run in the Same Architecture

An organization can run batch jobs or Kubernetes-dependent services on GKE while running simple APIs that need minimal cluster-level controls on Cloud Run. What matters is managing networking, identity, CI/CD, logs, and cost **per service**, rather than forcing every application onto one platform.

## 14. Persistent Storage and High Availability

Pods are **ephemeral, replaceable** instances; files written to a container's writable layer are not durable storage for business data. Regardless of Standard or Autopilot, choose storage based on the access pattern:

| Requirement | Reference Solution | Notes |
|---|---|---|
| Single Pod needs a persistent block filesystem | PersistentVolume/PVC via Persistent Disk CSI driver | Zone-dependent, access mode, attach/detach |
| Multiple Pods/VMs need shared POSIX files | Filestore CSI driver | NFS networking, permissions, tier, and cost |
| Images and object artifacts | Cloud Storage API or Cloud Storage FUSE CSI driver | Object semantics are not identical to POSIX disks |
| Transactional database | Cloud SQL/AlloyDB or an appropriate DB service | HA, backups, connection pools, and quotas independent of GKE |
| Temporary cache | Ephemeral storage or Redis/Memorystore | Never treat ephemeral data as the sole copy |

**A `ReadWriteOnce` PVC backed by Persistent Disk does not support concurrent writes from Pods across multiple nodes.** When RWX/shared-filesystem semantics are needed, evaluate Filestore or another appropriate solution. Autopilot also supports many CSI/storage integrations, though access modes, node privileges, filesystems, and driver support may differ by version.

### High Availability Does Not Depend on Mode Alone

Autopilot clusters use a **regional** architecture; Standard can be **zonal** or **regional**. However, **a regional cluster alone is not enough for application HA**:

1. Run multiple replicas across zones as supported by scheduling/ComputeClasses.
2. Configure readiness/liveness/startup probes tailored to JVM startup times.
3. Set PodDisruptionBudgets and topology spread constraints where appropriate, understanding scheduling limits.
4. Ensure storage/databases have no single point of failure.
5. Size spare capacity for zone failures, rolling updates, and cluster maintenance.
6. Implement graceful termination, timeouts, and controlled retries while avoiding retry storms.

For example, a Deployment with `replicas: 3` **does not guarantee one Pod per zone**. When zonal spread is required, use topology spread constraints or affinity rules, then verify actual placement via `kubectl get pods -o wide`.

## 15. Deployment, Updates, and GitOps

Both modes use Kubernetes manifests, `kubectl`, Helm, Kustomize, Argo CD/Flux, or compatible pipelines.

Recommended release flow:

~~~text
Git commit
  → CI tests + image scanning
  → Build Java container image
  → Push to Artifact Registry
  → Review manifests (CPU/memory, probes, policy)
  → Apply via GitOps/CD identity
  → Deployment rolling update
  → Readiness / SLO checks / canary if applicable
  → Monitor and roll back when needed
~~~

**Versioned images:** avoid uncontrolled `:latest` tags; use digests or immutable image tags so you know the exact version serving traffic. Decouple application deployment from node management; upgrading the GKE version does not rebuild your Java image.

### Rolling Update and Rollback

~~~bash
# Use an actual image pushed by CI; PROJECT_ID must be replaced.
kubectl set image deployment/orders-api \
  api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v2

kubectl rollout status deployment/orders-api
kubectl rollout history deployment/orders-api

# If the new version fails the defined checks.
kubectl rollout undo deployment/orders-api
~~~

A Pod rollout can stall if `maxUnavailable`, `maxSurge`, quotas, readiness probes, or node resources are misaligned. In Standard, check node pool capacity/autoscaler as well; in Autopilot, check admission, scheduling, and resource provisioning. Rolling back a Deployment's image **does not automatically roll back database schemas** or written data.

### Maintenance and Upgrades

GKE provides **release channels** and upgrade/maintenance controls. Autopilot manages node updates according to Google-defined settings; Standard gives platform teams more control over node pool settings, auto-upgrade windows, and rollouts. In both modes:

- Test image and client compatibility with target Kubernetes versions.
- Track API deprecations before upgrading.
- Configure maintenance windows/exclusions where eligible.
- Use readiness probes and PodDisruptionBudgets to minimize SLO impact.
- Never treat Google-managed nodes as a zero-downtime guarantee for a single-replica app.

## 16. Quotas, Scheduling, and Startup Latency

A Pod can stay `Pending` even when its manifest is valid. Key causes include:

| Issue | Symptom | Standard | Autopilot |
|---|---|---|---|
| Insufficient CPU/memory | `Insufficient cpu/memory` | Resize or autoscale node pool; check requests | GKE provisions nodes; check quotas/compute bounds |
| Invalid resource requests | Admission rejection or mutated requests | Check LimitRange/ResourceQuota | Check Autopilot min/max and CPU:memory ratio |
| Overly strict node affinity | No nodes match selector/taints | Adjust node pools/taints | Adjust ComputeClass/constraints |
| Insufficient quota or capacity | Node provisioning fails or stalls | Check CPU/GPU quotas and zones | Check quotas, region/accelerator availability |
| Private registry unreachable | `ImagePullBackOff` | Image pull identity, networking | Same; nodes are Google-managed |
| Incompatible Pod security | Admission rejection | Review cluster policies | Review Autopilot guardrails |
| Storage zone mismatch | PVC Pending, mount failure | Check node/volume zones | Check topology/driver/support |
| Rollout too aggressive | 5xx or readiness errors | Review surge/capacity | Review node provisioning and resource requests |

**Autopilot provisioning also has startup latency:** during a sudden scale-out, GKE must provision new node capacity, pull the image, and wait for the application to become ready. An API with a 90-second JVM warmup does not deliver full throughput the instant HPA adds replicas. Design HPA metrics, pre-warming/replica floors, and load shedding to match SLOs.

### Quick Investigation Commands

~~~bash
kubectl get pods -A -o wide
kubectl describe pod POD_NAME -n NAMESPACE
kubectl get events -A --sort-by=.lastTimestamp
kubectl get nodes -o wide
kubectl get deployments,hpa -A
kubectl get pvc -A

# When Pods are running but the application is failing.
kubectl logs deployment/orders-api --tail=100
kubectl describe deployment/orders-api
~~~

Even if `kubectl get nodes` shows nodes in Autopilot, that does not grant SSH or OS customization access as in Standard. When a Pod is rejected by an Admission webhook, read the **exact reason/message** in events instead of raising CPU or blindly disabling guardrails.

## 17. Workload Migration and Hybrid Architecture Choices

Suppose an organization runs a Standard cluster with many applications; some Pods would run well on Autopilot, while others need privileged agents. There are at least two paths:

**Path A — Create a new dedicated Autopilot cluster.** Use this when most workloads are compatible and you want to reduce long-term node-level operational overhead.

1. Inventory Deployments, StatefulSets, DaemonSets, PVCs, NetworkPolicies, Ingresses, HPAs, CRDs, and cluster add-ons.
2. Audit privileged containers, `hostPath`, machine types/GPUs, CSI drivers, CPU/memory/ephemeral requests, and CPU:memory ratios.
3. Create the Autopilot cluster in an approved VPC/region; configure IAM, Workload Identity, Artifact Registry, Secret Manager, logging, and networking.
4. Deploy compatible namespaces, CRDs, and workloads via GitOps.
5. Migrate persistent data using proper snapshots/backups/replication; never copy an actively written PVC and assume consistency.
6. Run functional, performance, and security tests; measure actual requests and cost.
7. Shift traffic via load balancing/DNS using a canary plan, keeping the old endpoint ready for rollback.
8. Once stable, review costs and decommission old Standard resources properly.

**Path B — Keep the Standard cluster and select Autopilot ComputeClasses for eligible workloads.** Use this when hybrid controls are needed in the same cluster and the cluster meets version/network/security prerequisites. Keep in mind that Autopilot workloads carry their own guardrails and pricing even inside a Standard cluster.

### Illustrating a Workload Selecting an Autopilot ComputeClass in a Standard Cluster

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      nodeSelector:
        cloud.google.com/compute-class: autopilot
      containers:
        - name: worker
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-worker:v1
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
~~~

This is an **illustration** for a Standard cluster that supports the built-in `autopilot` ComputeClass. If the cluster lacks the required version or prerequisites, Pods may remain Pending. Verify that the ComputeClass exists and how the scheduler selects nodes; do not copy this manifest regardless of cluster version. On a dedicated Autopilot cluster, GKE already applies Autopilot to workloads and typically **does not need** this selector.

**Not an in-place migration:** you cannot simply add a few node pools and convert an entire dedicated Autopilot cluster into an unrestricted Standard cluster. Building a hybrid architecture requires supported **Standard + Autopilot ComputeClasses** or deploying across two clusters.

## 18. Enterprise Scenario: Choosing a Mode per System

Suppose an e-commerce enterprise operates four systems on Google Cloud:

1. **Java Orders API:** 8 stateless microservices using Cloud SQL and Pub/Sub, with hourly traffic peaks.
2. **Search indexing:** batch data-processing workers using GPUs in periodic stages.
3. **Legacy fraud engine:** agents requiring host-level privileges, DaemonSets, and specialized kernel settings.
4. **Web frontend:** simple HTTP container with a few services and no Kubernetes-specific API dependencies.

### Evaluate by Workload, Not by Slogans

| System | Key Requirement | Initial Choice |
|---|---|---|
| Java Orders API | Minimal node-level customization, multiple replicas, HPA, and rollouts | **GKE Autopilot** if network/storage needs are compatible |
| GPU Search indexing | Specialized hardware, periodic batch runs | **Compare Autopilot hardware-specific vs. Standard GPU pools** |
| Legacy fraud engine | Mandatory privileged agents/host access | **GKE Standard** or refactor agents for compatibility |
| Minimalist web frontend | No cluster needed; want minimal Kubernetes ops | **Compare Cloud Run** before choosing GKE |

### Architecture Option A: Separation by Responsibility

~~~text
                     Google Cloud Organization
                       ├── ecommerce-prod project
                       │    ├── GKE Autopilot: Orders APIs
                       │    ├── Cloud SQL: transactional data
                       │    ├── Pub/Sub: event bus
                       │    └── External Application Load Balancer
                       ├── fraud-prod project
                       │    └── GKE Standard: privileged agents
                       └── web-prod project
                            └── Cloud Run: HTTP frontend
~~~

Pros: separates IAM, security posture, release processes, and billing by team. Trade-off: more projects/clusters, requiring cross-project management of networking, observability, service-to-service authentication, and CI/CD.

### Architecture Option B: Hybrid Standard Cluster

If the organization already operates a regional Standard cluster meeting modern ComputeClass prerequisites, it can keep a Standard node pool for the Fraud engine while letting eligible Orders workers use an Autopilot ComputeClass. The upside is fewer network/API changes; the trade-off is that the platform team **must still operate the Standard cluster** and govern policies where both workload modes coexist.

### Evidence-Based Selection Process

Before finalizing, run a pilot:

1. **Inventory requirements:** Pod manifests, DaemonSets, CRDs, storage, host privileges, data residency, and release windows.
2. **Run admission tests:** apply the same deployments in Standard and Autopilot environments; record any rejections or adjusted requests.
3. **Load test:** measure startup latency, P95/P99 HTTP latency, database connections, HPA lag, Pod scale-out, and quota failures.
4. **Compare costs:** for equal throughput/SLO, calculate cluster fees, vCPU/memory requests, VM/node-hours, networking, LB, disks, logging, and operational staffing.
5. **Test outages:** simulate Pod crashes, node drains, and zone-level failures in an authorized environment.
6. **Security review:** IAM, Workload Identity, RBAC, network policies, privileged workloads, and image supply chain.
7. **Finalize the operating model:** owners for nodes, apps, scaling, patching, incidents, and rollbacks.

**Scenario conclusion:** Orders APIs will likely fit Autopilot well; Fraud requires Standard unless privileges can be removed; Search needs real hardware/price benchmarking; Web frontend may not need GKE at all. Choose the platform based on business goals and application architecture rather than forcing every workload into one mode.

## 19. Common Misconceptions When Choosing a GKE Mode

| Misconception | Reality to Verify |
|---|---|
| "Autopilot has no VMs/nodes." | Node infrastructure exists, but GKE manages and provisions it per workload |
| "Standard means you manage the control plane too." | GKE manages the Kubernetes control plane in both modes |
| "Autopilot means no HPA is needed." | HPA is still required to scale replica counts based on traffic/metrics |
| "Autopilot always bills by Pod." | General-purpose is Pod-based; specialized hardware can be node-based + premium |
| "Without requests, Pods only pay for actual CPU used." | Autopilot injects default requests and may adjust them to bounds |
| "Standard is always cheaper." | Must factor in VM utilization, discounts, node overhead, and operational costs |
| "Autopilot does not support GPUs." | GPU/accelerator support exists depending on class, region, version, and quota |
| "Autopilot bans all root containers." | Certain host/privileged capabilities are blocked; root user is not universally banned |
| "Standard and Autopilot cannot coexist." | Standard clusters can run Autopilot workloads via ComputeClasses when eligible |
| "Regional GKE alone equals HA." | Also need multiple Pods, topology spread, storage/database HA, and spare capacity |
| "Pending Pods mean the cluster is broken." | Nodes may be provisioning, or quotas, policies, PVCs, or resources may constrain scheduling |
| "Deleting a Deployment stops all costs." | Cluster, Standard nodes, PVs, LBs, IPs, and dependent resources may still remain |

## 20. Selection and Deployment Checklist

### Before Choosing Standard or Autopilot

- [ ] Inventoried all workloads, DaemonSets, CRDs, CSI drivers, agents, and host privileges.
- [ ] Identified Pod security requirements, privileged mode, `hostPath`, and sysctls.
- [ ] Checked GPU/TPU, Arm, memory, disk, network, and ComputeClass support by region/version.
- [ ] Distinguished cluster mode from workload mode in Standard clusters with Autopilot ComputeClasses.
- [ ] Confirmed HA requirements at the VM/zone/region level along with database/storage dependencies.
- [ ] Selected VPC-native networking, Pod/Service IP ranges, and ingress/egress paths.
- [ ] Decided ownership for node pools, patching/upgrades, capacity, Pod security, and incident response.
- [ ] Compared costs by throughput/SLO, node utilization, Pod requests, GPU premiums, networking/LB/PV/Logging.

### Before Deploying Applications

- [ ] Container images have explicit versions in an authorized registry.
- [ ] Deployments declare valid CPU/memory/ephemeral-storage requests and limits.
- [ ] Readiness, liveness, and startup probes reflect the application lifecycle.
- [ ] HPA has min/max replicas and reliable metrics; evaluated node provisioning and JVM boot times.
- [ ] Workload Identity Federation and IAM follow least privilege.
- [ ] Kubernetes RBAC, namespaces, and network policies have been reviewed.
- [ ] PVC/Filestore/Cloud Storage choices match data semantics; backup and restore plans exist.
- [ ] Application Load Balancer/TLS/Cloud Armor, DNS, and firewalls are verified if public.
- [ ] CI/CD, release channel, maintenance windows, and rollback have clear owners.
- [ ] Alerts for error rate, latency, saturation, Pending Pods, OOM, HPA, and cost are configured.

### When Concluding a Lab or Migration

- [ ] Backed up/migrated data before deleting clusters or PVCs.
- [ ] Checked for lingering LoadBalancer IPs, PersistentVolumes, Filestore, Cloud NAT, Artifact Registry, and logging resources.
- [ ] Deleted resources only in the right project/cluster after confirming owner and retention.
- [ ] Documented architectural decisions, rationale, cost assumptions, and review triggers.

## 21. Applied Exercises

**Exercise A — Choosing a Mode for Java APIs.** A team has 5 stateless microservices. Each service runs 3 replicas, with each Pod requesting `500m` CPU and `1Gi` memory on average. The team has no dedicated Kubernetes SRE, needs HPA during traffic spikes, and uses Cloud SQL private IP and Pub/Sub.

1. Choose Standard or Autopilot as the initial option; justify with at least four criteria.
2. Calculate total baseline **requested** CPU/memory and distinguish it from actual CPU usage.
3. List cost categories: cluster fees, Pod/node compute, LBs, Cloud SQL, networking, logging, and storage.
4. Write a Deployment manifest with probes, `resources.requests`/`limits`, and an HPA with min 3 and max 12 replicas.
5. Explain why HPA increasing replicas can still leave new Pods Pending temporarily.
6. Propose how to grant Pods access to Pub/Sub and Cloud SQL without embedding service account keys in the image.

**Exercise B — Autopilot Compatibility.** An existing cluster runs a security agent DaemonSet with `privileged: true` mounting hostPath `/var/lib`, a GPU service, and a CPU-only batch worker.

1. Flag which components must be tested or redesigned before moving to dedicated Autopilot.
2. Propose a hybrid architecture combining a Standard node pool with an Autopilot ComputeClass where version-supported.
3. Explain why the GPU workload in Autopilot may be billed **node-based** rather than by Pod requests.
4. State which metrics should be benchmarked before deciding to keep a Standard GPU pool.

**Exercise C — Cost and SLO Comparison.** A Standard node pool uses 4 VMs, each with 4 vCPU and 16 GiB RAM. Most of the time, total Pod requests are only 6 vCPU and 12 GiB RAM; for 2 hours each day, requests double.

1. Calculate provisioned VM capacity and the ratio of requested CPU/memory to nominal capacity (before deducting system overhead).
2. Propose a matching HPA + node autoscaler setup for Standard, including min/max bounds and quota checks.
3. Estimate Autopilot general-purpose usage from hourly Pod requests (without exact pricing if rate cards are unavailable), then compare relatively.
4. Explain why you cannot determine which mode is cheaper solely from total `kubectl top` CPU.
5. Describe how to measure P95 latency, 5xx, startup time, and rollout behavior before changing production.

**Exercise D — Production Incident.** After deploying a Java app onto an Autopilot cluster, Pods stay `Pending`, with logs/events indicating `resource request` out of bounds; the deployment previously ran on a Standard cluster.

1. Name at least three `kubectl` commands to investigate.
2. Explain how Autopilot applies default/min/max bounds and CPU:memory ratios.
3. State when to adjust requests, when another ComputeClass is needed, and when Standard is required for host privileges.
4. Propose how to roll out the fix without disrupting already-running services.
5. List CI guardrails/metrics to catch similar issues before production.

**Synthesis Question:** If the requirement is "just a Java REST API handling HTTP requests and a few background tasks," explain why **Cloud Run** should also be on the shortlist rather than defaulting to a GKE mode.

## Official Reference Documentation

- [About GKE modes of operation](https://cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode) — differences between Standard and Autopilot at the workload and cluster levels.
- [GKE Autopilot overview](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview) — node management, operations, and ComputeClasses.
- [Autopilot workloads in GKE Standard clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/about-autopilot-mode-standard-clusters) — running Autopilot workloads in Standard clusters.
- [Run Autopilot workloads in Standard clusters](https://cloud.google.com/kubernetes-engine/docs/how-to/autopilot-classes-standard-clusters) — version, networking, node pool, and ComputeClass prerequisites.
- [Configure Standard clusters to use Autopilot by default](https://cloud.google.com/kubernetes-engine/docs/how-to/standard-clusters-autopilot-mode) — configuring Autopilot-like settings for Standard clusters.
- [Create an Autopilot cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster) — Console, CLI, and Terraform.
- [Create a zonal Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-zonal-cluster) — CLI, zones, and node pools.
- [Create a regional Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-regional-cluster) — regional control plane, multi-zone node pools, and HA.
- [Autopilot resource requests](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests) — request defaults, minimums, ratios, and bursting.
- [Autopilot security measures](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-security) — privileged, capabilities, host access, and default policies.
- [GKE ComputeClasses](https://cloud.google.com/kubernetes-engine/docs/concepts/about-custom-compute-classes) — declaring compute profiles per workload.
- [Built-in GKE ComputeClasses](https://cloud.google.com/kubernetes-engine/docs/concepts/about-built-in-compute-classes) — autopilot, autopilot-spot, and other classes.
- [GKE cluster autoscaling](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler) — managing node capacity and how the autoscaler operates.
- [GKE storage overview](https://cloud.google.com/kubernetes-engine/docs/concepts/storage-overview) — Persistent Disk, Filestore, and Cloud Storage FUSE.
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — Pod identity and Google Cloud IAM.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — cluster fees, Pod-based/node-based billing, and limits.
- [GKE and Cloud Run](https://cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run) — choosing the right platform for containerized applications.
