# Requests, Limits, and Workload Scheduling on GKE

> **Chapter:** GKE Fundamentals  
> **Lesson:** Requests, Limits, and Workload Scheduling on GKE  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, storage services, and databases. Through practical deployment scenarios, learners learn how to select services, secure resources, automate releases, monitor reliability, and optimize cost. For **GKE**, those goals connect directly to three questions: **how many resources does a Pod need, which node does Kubernetes place the Pod on, and what happens when the application consumes more than expected?**

Kubernetes uses **resource requests** to make scheduling decisions, **resource limits** to cap runtime usage, and **scheduling constraints** to place Pods on nodes with matching attributes. In GKE Standard, you manage node pools and autoscaler configs. In GKE Autopilot, Google Cloud manages much of the node infrastructure while enforcing dedicated rules for CPU, memory, ephemeral storage, and selected hardware types.

**Key point upfront:** raising `limits.cpu` does not unstick a `Pending` Pod if **`requests.cpu`** cannot be satisfied. Adding nodes cannot fix a broken `nodeSelector`. And a `Running` Pod does not mean a Java API has enough RAM, avoids CPU throttling, or meets its SLO.

All project names, namespaces, clusters, images, and metrics in this lesson are illustrative. Manifests/commands can create workloads and incur charges if applied to real clusters; execute them only in authorized environments. The guide progresses from observation to design, followed by controlled experimentation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `resources.requests` and `resources.limits` for **CPU, memory, and ephemeral-storage**.
2. Distinguish **Node Capacity**, **Node Allocatable**, and remaining schedulable resources available for Pods.
3. Predict why Pods remain `Pending` due to `Insufficient cpu`, `Insufficient memory`, `Too many pods`, or unmatched constraints.
4. Describe **CPU throttling**, **`OOMKilled`**, **eviction**, and the QoS classes **Guaranteed, Burstable, and BestEffort**.
5. Use `nodeSelector`, node affinity, Pod affinity/anti-affinity, taints/tolerations, and topology spread constraints appropriately.
6. Distinguish resource management and control boundaries between **GKE Standard** and **GKE Autopilot**.
7. Combine **Horizontal Pod Autoscaler (HPA)**, **Vertical Pod Autoscaler (VPA)**, and **Cluster Autoscaler** without confusing their scopes.
8. Design a Deployment for a **Java Orders API** with requests, limits, probes, multiple replicas, and zonal spread.
9. Use `kubectl`, Google Cloud Console, and Cloud Monitoring to investigate scheduling, throttling, and memory pressure incidents.
10. Choose resource settings aligned with reliability, quotas, scalability, and cost.

## 2. Kubernetes Scheduling Flow on GKE

~~~mermaid
flowchart TD
    Commit["CI/CD applies Deployment<br/>Orders API"] --> API["Kubernetes API server"]
    API --> RS["Deployment / ReplicaSet<br/>creates Pods"]
    RS --> Pod["Unscheduled Pod"]
    Pod --> Scheduler["kube-scheduler"]
    Scheduler --> Filter["Filter nodes<br/>requests + constraints"]
    Filter --> Score["Score feasible nodes"]
    Score --> Bind["Bind Pod to node"]
    Bind --> Kubelet["kubelet + container runtime"]
    Kubelet --> Run["Java container runs<br/>cgroups + probes"]
    HPA["HPA: replica count"] -. "updates Deployment" .-> RS
    CA["Cluster Autoscaler / Autopilot<br/>node capacity"] -. "scales nodes" .-> Filter
~~~

Each component has a single job:

- **Deployment/ReplicaSet** maintains the desired Pod count per template.
- **Scheduler** picks a node for unscheduled Pods by inspecting **requested** resources, eligible nodes, and placement rules.
- **Kubelet** on each node launches containers, tracks status, and coordinates with the runtime/kernel to enforce resource limits.
- **HPA** adjusts Pod count based on metrics when configured.
- **Cluster Autoscaler** in GKE Standard adds/removes nodes per resource demand and bounds; **Autopilot** manages node capacity natively.

**The scheduler does not wait for actual CPU utilization to hit 90% before blocking placement.** It primarily evaluates *declared requests* against node allocatable capacity and scheduling rules. Thus, a cluster with low actual CPU usage can still fail to schedule new Pods if existing Pods have already requested most of the allocatable CPU.

## 3. Requests and Limits: Meaning and Syntax

### 3.1. A Container Has Two Sets of Values

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
    ephemeral-storage: "1Gi"
  limits:
    cpu: "1000m"
    memory: "1536Mi"
    ephemeral-storage: "2Gi"
~~~

| Property | Primary Role | Typical Consequence |
|---|---|---|
| `requests.cpu` | Reserves CPU for scheduler placement; CPU share weight during contention | Pod stays `Pending` if no node has enough free CPU request capacity |
| `limits.cpu` | CPU time ceiling for the container | Reaching the cap causes **CPU throttling**, not automatic termination |
| `requests.memory` | Reserves memory for scheduling and influences protection under memory pressure | Pod may be evicted if exceeding request while the node lacks RAM |
| `limits.memory` | Hard RAM cap enforced via kernel/cgroups | Exceeding it can trigger **`OOMKilled`**, restarting per policy |
| `requests.ephemeral-storage` | Local ephemeral storage accounted for during scheduling | Insufficient local ephemeral storage blocks scheduling |
| `limits.ephemeral-storage` | Monitored cap on ephemeral storage usage | Exceeding the cap can trigger Pod **eviction** |

**`requests` is not a guarantee that "the container always gets an isolated chunk of physical RAM and CPU" in an absolute sense.** Kubernetes uses requests for placement planning and kernel mechanisms for prioritization/protection; actual runtime behavior also depends on resource type, QoS, cgroups, kernel features, and node health.

### 3.2. Common Units

| YAML Notation | Interpretation |
|---|---|
| `cpu: "1"` | One Kubernetes CPU; equivalent to one vCPU/logical core on the node |
| `cpu: "500m"` | 500 millicores = 0.5 CPU |
| `cpu: "100m"` | 0.1 CPU |
| `memory: "512Mi"` | 512 mebibytes (MiB), base 1024 |
| `memory: "1Gi"` | 1 gibibyte = 1024 MiB |
| `memory: "1000M"` | 1000 megabytes, **different from** `1000Mi` |
| `ephemeral-storage: "2Gi"` | 2 GiB ephemeral local storage |

**Memory unit warning:** lowercase `m` means milli, **not MB**. For example, `memory: "400m"` is a tiny fraction of a byte, not 400 MiB. Always use explicit `Mi`/`Gi` for RAM to prevent mistakes.

### 3.3. What If They Are Omitted?

In Kubernetes generally:

- If **`limits` is set while `requests` is omitted** for a resource, the request defaults to the limit at admission unless another default policy applies.
- A namespace **`LimitRange`** can inject default, min, max, and ratio constraints.
- Omitting CPU/memory requests/limits does not protect the app when the node experiences contention.
- Behavior can vary across resource quotas, admission controllers, namespace policies, and Kubernetes versions.

With **GKE Autopilot**, the platform actively injects or adjusts requests and limits based on **ComputeClass, hardware, minimums/maximums, ratios, and bursting support**. Never apply GKE Standard assumptions to Autopilot without inspecting the Pod **post-admission**.

## 4. CPU and Memory Are Enforced Differently

### 4.1. CPU Is a Compressible, Time-Shared Resource

Linux container runtimes typically use **cgroups** to manage CPU. When a CPU limit is configured, a container gets **throttled** if it consumes its quota within the scheduling period.

Example:

- Request: `500m`.
- Limit: `1000m`.
- When the node has spare CPU, the container can burst above its request up to its limit.
- When CPU demand exceeds `1000m` within the period, the kernel delays thread execution rather than killing the process.

Java symptoms: rising p95/p99 latency, thread pools waiting on CPU, longer GC pauses, and request timeouts even while "average CPU" dashboards look moderate. Correlate **CPU throttling metrics**, CPU usage vs. limit, JVM/GC stats, and latency.

**Do not raise CPU limits blindly** when the bottleneck is the database, lock contention, or networking. On GKE Standard, teams sometimes **omit CPU limits** while keeping accurate CPU requests to eliminate throttling; weigh multi-tenant safety and organizational policy first. Autopilot has its own limit and bursting behavior.

### 4.2. Memory Has No Soft "Throttle" Equivalent to CPU

Suppose a container declares:

~~~yaml
requests:
  memory: "768Mi"
limits:
  memory: "1536Mi"
~~~

It can use more than 768 MiB if the node has free RAM, yet once it hits 1536 MiB and the kernel cannot reclaim or allocate more, the process can be killed for **out of memory (OOM)**. Kubernetes typically shows `OOMKilled` and exit code `137` (`SIGKILL`), though exit code `137` **is not exclusively** caused by OOM; always verify `Last State`, events, and logs.

For Java, memory footprint is far more than **`-Xmx`**:

~~~text
Approximate container memory:
  Java heap
+ metaspace, code cache
+ thread stacks
+ direct / native buffers
+ JNI / native libraries
+ runtime / OS allocations
+ memory-backed volumes (if any)
~~~

If the container limit is 1.5 GiB and `-Xmx` is set to 1.5 GiB, the process will quickly OOM before the heap even reaches its cap because non-heap regions still require RAM. Configure headroom, heap percentages, measure GC, and run load tests.

### 4.3. Ephemeral Storage Differs from PersistentVolume

**Ephemeral storage** covers local node disk space tracked by Kubernetes per feature/filesystem layout—such as the container writable layer, container logs, and disk-backed `emptyDir`. It is **not** a PersistentVolume for durable data.

- Unbounded logging or temporary file downloads can exhaust ephemeral storage.
- Exceeding a Pod's `ephemeral-storage` limit triggers kubelet **eviction**.
- `emptyDir.medium: Memory` consumes **RAM**, counting toward container memory usage rather than disk-backed ephemeral storage.
- A PVC backed by Persistent Disk/Hyperdisk is a separate storage resource with its own topology, storage class, and lifecycle.

Never store orders or invoices needing to survive Pod replacement in ephemeral storage; use Cloud SQL, Cloud Storage, or an appropriate PersistentVolume.

## 5. Node Capacity, Allocatable, and Calculating Pod Requests

### 5.1. Why Can't a 4 vCPU Node Give All 4 CPUs to Pods?

Nodes expose two numbers:

- **Capacity:** total CPU/RAM/Pod slots advertised by the machine.
- **Allocatable:** resources remaining for Pods after subtracting OS, kubelet, system daemon, and eviction reservations.

~~~text
Capacity (example):   4 CPU, 16 GiB RAM
Reserved/system:      CPU/RAM reserved for kubelet, OS, system daemons
Allocatable:          smaller than Capacity
Already requested:    system Pods + scheduled workloads
Available for new Pod = Allocatable - sum(Requests of Pods on the node)
~~~

Suppose a node has **3500m allocatable CPU**, and running Pods already request **3000m**. A new Pod requesting **750m** cannot schedule onto that node, even if real-time CPU usage at that instant is only 10%. The scheduler never ignores reservations based on an instantaneous usage metric.

### 5.2. Multi-Container Pods: Summing Requests

~~~yaml
containers:
- name: orders-api
  resources:
    requests:
      cpu: "500m"
      memory: "768Mi"
- name: telemetry-sidecar
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
~~~

Total requests for these **two application containers** are:

~~~text
CPU:    500m + 100m = 600m
Memory: 768Mi + 128Mi = 896Mi
~~~

Pods with **init containers** follow a specific *effective request* calculation: because standard init containers run sequentially, the scheduler takes the **maximum across init containers** versus the **sum of application containers**, plus **Pod overhead** if a RuntimeClass applies. For native sidecar init containers using `restartPolicy: Always`, resource calculation accounts for overlapping lifetimes; check the exact Kubernetes spec/version.

**Never naively add every init container to every application container**, nor look only at the main container's resource block. Across many Pods, sidecars, and DaemonSets, small miscalculations produce major cluster sizing errors.

### 5.3. Inspecting Capacity and Allocatable with kubectl

~~~bash
# List nodes in an authorized cluster.
kubectl get nodes -o wide

# Inspect capacity, allocatable, and currently allocated requests.
kubectl describe node NODE_NAME

# Extract details as YAML if needed.
kubectl get node NODE_NAME -o yaml
~~~

In `kubectl describe node`, examine two sections:

- **Capacity / Allocatable**.
- **Allocated resources**: sum of Requests/Limits across Pods currently bound to that node.

The `Allocated resources` table shows **declared requests**, not actual live CPU/RAM usage. Compare it with `kubectl top node` or Cloud Monitoring to spot overprovisioning and resource pressure.

## 6. QoS Classes: Guaranteed, Burstable, BestEffort

Kubernetes assigns each Pod a **Quality of Service** class to manage risk when a node runs short on resources.

| QoS | Typical CPU/Memory Condition | Behavior Under Node Pressure |
|---|---|---|
| **Guaranteed** | Every container sets CPU and memory **`request == limit`**, greater than 0 | Prioritized to stay alive ahead of lower classes |
| **Burstable** | At least one container has a CPU/memory request or limit, without meeting Guaranteed | Eligible for eviction depending on usage above request and pressure |
| **BestEffort** | No container specifies any CPU/memory request or limit | First in line for eviction under node resource pressure |

Examples:

~~~yaml
# Guaranteed for CPU/memory:
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "500m"
    memory: "1Gi"
~~~

~~~yaml
# Burstable:
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "1Gi"
~~~

**Important:** QoS is only one input to eviction decisions. **Pod Priority**, how much a Pod exceeds its requests, the type of node pressure, and other factors also influence which Pod gets evicted. `Guaranteed` **does not promise "the Pod can never be killed"**: hitting a container memory limit (`OOMKilled`), node crashes, or other events still terminate Pods.

Recent Kubernetes versions introduce **Pod-level resource specifications** via feature gates/versions, yet this foundational guide uses **container-level resources** for broad compatibility and clarity. When adopting newer features, verify GKE version and enablement status.

## 7. From Resources to Pod Scheduling

The scheduler evaluates placement in two phases:

1. **Filter:** eliminates nodes lacking resources or failing mandatory constraints.
2. **Score:** ranks surviving feasible nodes to select the best placement.

~~~mermaid
flowchart TD
    P["Pod Orders API<br/>requests 750m CPU, 1Gi RAM"]
    N1["Node A<br/>500m allocatable CPU left for requests"]
    N2["Node B<br/>1000m CPU, 2Gi RAM left<br/>matches nodeSelector"]
    N3["Node C<br/>1500m CPU left<br/>has untolerated taint"]
    F["Scheduler filter"]
    B["Bind Pod to Node B"]
    P --> F
    N1 -. "Insufficient cpu" .-> F
    N2 --> F
    N3 -. "Untolerated taint" .-> F
    F --> B
~~~

Scheduling failures stem from both resources and **unmatched constraints**:

| Typical Event / Message | Meaning |
|---|---|
| `Insufficient cpu` | No node has enough unrequested allocatable CPU |
| `Insufficient memory` | No node has enough unrequested allocatable RAM |
| `Insufficient ephemeral-storage` | Not enough local ephemeral storage for the request |
| `Too many pods` / `OutOfPods` | Node hit its maximum Pod slot limit |
| `node(s) didn't match Pod's node affinity/selector` | Node labels or affinity rules did not match |
| `had untolerated taint` | Pod lacks a matching toleration |
| `didn't match pod affinity/anti-affinity` | Co-location or anti-co-location rule unsatisfied |
| `volume node affinity conflict` | PVC/PV topology points to a different zone |
| `didn't match topology spread constraints` | Spread rule is too strict for available domains |
| `Insufficient nvidia.com/gpu` | Node lacks the requested GPU extended resource |

Exact messages vary by scheduler and GKE version. A single Pod can fail on multiple nodes for different reasons at once; **read all Events** rather than latching onto the first line.

## 8. `nodeSelector` and Node Affinity

### 8.1. `nodeSelector`: Simple Label Constraint

~~~yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
      - name: orders-api
        image: IMAGE_URI
~~~

The Pod schedules only onto nodes labeled `kubernetes.io/arch=amd64`. If the cluster only has `arm64` nodes, the Pod stays **`Pending`** regardless of abundant CPU/RAM.

Use only built-in or contractually managed labels. On GKE Standard with node pools, you can rely on node-pool labels; **do not manually edit labels on Autopilot-managed nodes as you might in Standard**.

### 8.2. Required vs. Preferred Node Affinity

- `requiredDuringSchedulingIgnoredDuringExecution`: **hard** constraint at scheduling time.
- `preferredDuringSchedulingIgnoredDuringExecution`: **soft** preference; the scheduler picks another node if needed.
- `IgnoredDuringExecution`: changing node labels after a Pod is already running will not evict it under this rule.

Example preferring a specific zone while allowing fallback when needed:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 80
      preference:
        matchExpressions:
        - key: topology.kubernetes.io/zone
          operator: In
          values:
          - asia-southeast1-a
~~~

When a workload **strictly requires** zonal storage or specific hardware, a preferred rule is not enough; use required affinity/topology rules. When the goal is simply latency optimization, preferred rules avoid leaving Pods stuck `Pending`.

### 8.3. Picking a Zone Does Not Equal HA

Pinning all API replicas to zone A might simplify zonal disk access, yet **increases outage blast radius**. For stateless APIs behind a load balancer, spread across multiple zones in a regional GKE cluster. For stateful Pods with zone-bound PVCs, align scheduler constraints with storage topology and failover—never try forcing a zonal PVC into another zone by changing `nodeSelector`.

## 9. Taints and Tolerations: Reserving Nodes for Matching Workloads

### 9.1. Taint Differs from Toleration

A node can carry a taint:

~~~text
dedicated=batch:NoSchedule
~~~

Pods lacking a matching toleration will not schedule onto that node. Illustrative toleration:

~~~yaml
tolerations:
- key: dedicated
  operator: Equal
  value: batch
  effect: NoSchedule
~~~

However, **a toleration only permits a Pod to be considered for a tainted node**; it **does not force the Pod onto that node**. To ensure batch workloads land exclusively on the batch node pool, pair the toleration with **node affinity/`nodeSelector`**.

### 9.2. Three Common Effects

| Taint Effect | Impact |
|---|---|
| `NoSchedule` | Blocks new Pods without a matching toleration from scheduling |
| `PreferNoSchedule` | Scheduler tries to avoid the node if viable alternatives exist |
| `NoExecute` | Blocks scheduling and can **evict already-running Pods** without a toleration (subject to `tolerationSeconds` if set) |

On GKE Standard, define node-pool taints in the **node pool configuration** so newly autoscaled nodes inherit them automatically. Tainting an individual node manually will not persist across scale events or upgrades.

**Security note:** taints and tolerations are practical scheduling and isolation tools, not security boundaries replacing IAM, network policies, or container sandboxing.

## 10. Pod Affinity, Anti-Affinity, and Topology Spread

### 10.1. Packing Pods Together or Spreading Them Apart?

- **Pod affinity:** co-locates Pods in the same topology domain as matching labeled Pods.
- **Pod anti-affinity:** keeps Pods off the same node/zone as matching Pods for fault isolation.
- **Topology spread constraints:** bounds replica count skew across domains such as zones or hostnames.

Example of a Java app needing replicas spread across zones in a regional cluster with multi-zone nodes:

~~~yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: ScheduleAnyway
  labelSelector:
    matchLabels:
      app: orders-api
~~~

**`ScheduleAnyway`** means the scheduler prefers even spread yet still schedules Pods when ideal balance isn't possible. With `DoNotSchedule`, Pods stay `Pending` if the constraint cannot be met—use that when strict fault isolation is required and node capacity is well provisioned.

### 10.2. Node-Level Anti-Affinity

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchLabels:
            app: orders-api
        topologyKey: kubernetes.io/hostname
~~~

Meaning: avoid placing two `orders-api` Pods on the same node when possible. This is a **soft** rule, so it does not guarantee strict separation. Hard anti-affinity can leave Deployments `Pending` when node pools are small or the autoscaler cannot add nodes.

### 10.3. Pairing Spread Rules with Autoscaling

When combining topology spread constraints with cluster autoscaling, check `nodeTaintsPolicy` and eligible domain behavior. GKE guidance recommends considering `nodeTaintsPolicy: Honor` for workloads using topology spread with Cluster Autoscaler to avoid scale-down/scale-up thrashing caused by differing views of eligible nodes.

**Never assume `replicas: 3` automatically means "one Pod per zone."** If nodes exist in only one zone, the scheduler cannot invent new zones. You need matching multi-zone node pools, ComputeClasses, or cluster topology across enough eligible domains.

## 11. How GKE Standard and GKE Autopilot Differ in Resource Management

| Topic | GKE Standard | GKE Autopilot |
|---|---|---|
| Node pools | Operators manage configuration, sizing, and autoscaling | GKE manages most underlying node infrastructure for workloads |
| Resource requests | Determined by manifest, `LimitRange`/admission | GKE enforces defaults/mins/maxes and adjusts requests per ComputeClass/hardware |
| CPU/memory ratio | Depends on machine type and cluster policies | Enforces **valid CPU:RAM ratios** per ComputeClass |
| CPU limits | Standard Kubernetes/cgroups; operators set policy | Adjusts limits based on cluster **bursting support** |
| Ephemeral storage | Per Kubernetes, node capacity, and cluster policy | Has defaults and bounds; **limits equal requests** for ephemeral storage |
| Hardware | Selected via machine types / node pools | Selected via supported ComputeClasses / hardware requests |
| Scheduler constraints | Self-managed labels, taints, and node pools | Certain constraints or hard affinities carry specific rules/limits |
| Pricing | Typically billed for node VMs and related services | Depends on **Pod-based or node-based billing** and workload config |
| Troubleshooting | Inspect node pools/autoscaler too | Inspect Pod post-admission, ComputeClass, Autopilot config, and capacity |

### 11.1. Autopilot May Inject Default Requests

Per current documentation, several built-in Autopilot ComputeClasses have default resource requests such as:

| ComputeClass | Default CPU | Default RAM |
|---|---:|---:|
| General-purpose | 0.5 vCPU | 2 GiB |
| Balanced | 0.5 vCPU | 2 GiB |
| Scale-Out | 0.5 vCPU | 2 GiB |

These are **illustrative reference defaults from docs**, not rules for every GPU/Performance workload or version. For non-DaemonSet containers, Autopilot also sets a default ephemeral storage request—for example, **1 GiB** in current docs. Always verify min/max, compute class, and bursting tables in official docs before relying on absolute numbers.

### 11.2. CPU:Memory Ratios and Adjusted Values

Suppose you request `1 vCPU` and `16Gi` in the **Scale-Out ComputeClass**. If the maximum allowed ratio is **1 vCPU : 4 GiB**, Autopilot may **bump the CPU request up to 4 vCPU** to satisfy the ratio. You wrote 1 vCPU in YAML, yet billing and scheduling reflect the GKE-adjusted request.

Autopilot may also:

- Raise requests below the minimum.
- Apply defaults when requests are omitted.
- Reject workloads exceeding hardware/ComputeClass maximums.
- Adjust limits when bursting is unsupported.
- Adjust init-container requests under dedicated policies.

Therefore, after `kubectl apply`, **inspect the created Pod** rather than reading only Git YAML to see effective requests and limits.

### 11.3. Bursting and CPU Limits in Autopilot

| Configuration | Cluster **with bursting** | Cluster **without bursting** |
|---|---|---|
| Request lower than CPU limit | Pod can burst up to limit when capacity is free | Autopilot may set limit equal to request |
| Request set, CPU limit omitted | Can burst subject to available capacity | Autopilot may add a limit equal to request |
| CPU limit set only | Request defaults to limit at admission | Same, subject to Autopilot policies |
| Request/limit outside min/max/ratio | May be mutated or rejected | May be mutated or rejected |

For ephemeral storage in Autopilot, **requests and limits must be equal**; GKE may mutate the spec to enforce this. Do not deploy a manifest with `ephemeral-storage` request `1Gi` and limit `5Gi` expecting identical behavior to Standard.

### 11.4. Is Autopilot Always Cheaper Than Standard?

You cannot tell from the mode name alone. **Requests** drive sizing, scheduling, and many Autopilot billing models. Standard bills for node pools/machine types and associated charges; Autopilot bills by workload resource requests or node-based models depending on hardware/class.

An over-requested Pod that sits mostly idle wastes capacity and increases cost; an under-requested Pod suffers poor performance or gets bumped by Autopilot. Base decisions on **cost per request/transaction meeting SLOs**, not a single Pod or VM line item.

## 12. Hands-On A — Java Orders API Deployment on GKE Standard

This lab assumes namespace `orders-lab` and an OCI image **already built, pushed to a Docker repository, and pullable by the cluster**. Example image:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
~~~

**Never use a Maven JAR path as an image URI.** An Artifact Registry Docker repository holds OCI images; Maven artifacts are build inputs used to create the image.

### 12.1. Deployment Manifest with Requests, Limits, and Topology Spread

Save `orders-deployment.yaml` in an authorized lab environment. Notice `topologySpreadConstraints` sits at the **Pod `spec` level**, alongside `containers`, not inside an individual container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-lab
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
      terminationGracePeriodSeconds: 30
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: orders-api
      containers:
      - name: orders-api
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
        ports:
        - containerPort: 8080
          name: http
        resources:
          requests:
            cpu: "500m"
            memory: "768Mi"
            ephemeral-storage: "1Gi"
          limits:
            cpu: "1000m"
            memory: "1536Mi"
            ephemeral-storage: "2Gi"
        env:
        - name: JAVA_TOOL_OPTIONS
          value: "-XX:MaxRAMPercentage=65.0"
        startupProbe:
          httpGet:
            path: /healthz
            port: http
          periodSeconds: 5
          failureThreshold: 24
        readinessProbe:
          httpGet:
            path: /ready
            port: http
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /healthz
            port: http
          periodSeconds: 10
~~~

Explanation:

- Each replica requests **0.5 vCPU**, **768 MiB** RAM, and **1 GiB** ephemeral storage.
- Three replicas request **1.5 vCPU**, **2304 MiB** RAM, and **3 GiB** ephemeral storage total, **excluding** extra containers, init containers, Pod overhead, or node system Pods.
- CPU can burst up to 1 vCPU when capacity permits in Standard under applicable policies.
- Memory limit is **1536Mi**; ensure heap + native footprint stay below this cap.
- `topologySpreadConstraints` sits at **`spec.template.spec`**, sibling to `containers`.
- `PROJECT_ID` in the image is a placeholder; replace it with a real image URI that nodes/kubelet have IAM permission to pull.
- Never create a public LoadBalancer Service without a real access requirement.

For a real API, `/ready` and `/healthz` must **genuinely exist** in the image. If the app only exposes `/healthz`, update the probes and verify logic before deploying. `startupProbe` prevents premature liveness kills during JVM warm-up; liveness should never fail solely because an external dependency hiccups.

### 12.2. Readback and Apply in the Right Environment

Connection inspection commands:

~~~bash
gcloud container clusters list --project=PROJECT_ID
gcloud container clusters get-credentials CLUSTER_NAME \
  --project=PROJECT_ID \
  --location=CLUSTER_LOCATION

kubectl config current-context
kubectl get namespace orders-lab
~~~

`get-credentials` updates **your CLI kubeconfig**, not the cluster. Verify you point to the right cluster. If the namespace doesn't exist and you are authorized to create it:

~~~bash
kubectl create namespace orders-lab
~~~

**The following commands create/update real workloads:**

~~~bash
kubectl apply --dry-run=server -f orders-deployment.yaml
kubectl apply -f orders-deployment.yaml

kubectl get deployment orders-api -n orders-lab
kubectl get pods -n orders-lab -o wide
kubectl rollout status deployment/orders-api -n orders-lab
~~~

**`--dry-run=server`** still sends the manifest to the API server for validation/admission without persisting the resource; it depends on permissions and configured webhooks. Review its output before applying for real. If the cluster uses GitOps/Helm, never manually edit controller-managed workloads outside process.

## 13. Hands-On B — Autopilot-Compatible Requests/Limits Manifest

Example for **General-purpose Autopilot** with a stable Java API container and illustrative resources:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-lab
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
      - name: orders-api
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
        resources:
          requests:
            cpu: "500m"
            memory: "2Gi"
            ephemeral-storage: "1Gi"
          limits:
            cpu: "500m"
            memory: "2Gi"
            ephemeral-storage: "1Gi"
        ports:
        - containerPort: 8080
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          periodSeconds: 5
~~~

This configuration sets requests equal to limits across CPU, RAM, and ephemeral storage, avoiding reliance on bursting and offering a predictable starting point. It is **not a universal optimal preset for every Java workload**—always benchmark p95 latency, GC, and memory footprint.

To use CPU bursting in Autopilot, first confirm whether the cluster **supports bursting**, the matching ComputeClass, and billing/scheduling effects; set request lower than limit only when supported.

Inspect the created Pod:

~~~bash
kubectl get pods -n orders-lab
kubectl get pod POD_NAME -n orders-lab -o yaml
kubectl describe pod POD_NAME -n orders-lab
~~~

Specifically check `spec.containers[].resources` **on the running Pod**, not just the Deployment manifest—Autopilot admission may have mutated the values.

## 14. HPA, VPA, and Cluster Autoscaler Solve Different Layers

### 14.1. Three Tools, Three Questions

| Tool | What Changes? | Driven By What? |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | **Workload replica count** | CPU/memory utilization or custom/external metrics via adapters |
| **Vertical Pod Autoscaler (VPA)** | **Recommended or updated Pod resource requests/limits** | Historical usage analysis and VPA policy |
| **Cluster Autoscaler (Standard)** | **Node count** in configured node pools | Unschedulable Pods, requests, constraints, and scaling policies |
| **Autopilot node management** | Underlying node capacity for workloads | Managed by GKE per Pod requirements and ComputeClasses |

~~~mermaid
flowchart TD
    Traffic["Traffic rises"] --> Metrics["Metrics: CPU / RPS"]
    Metrics --> HPA["HPA increases Pod count"]
    HPA --> Pending["Some Pods lack matching nodes"]
    Pending --> CA["Cluster Autoscaler<br/>or Autopilot provisions capacity"]
    CA --> Nodes["Matching nodes added"]
    Nodes --> Pods["Pods scheduled"]
    VPA["VPA from usage history"] -. "Recommends/adjusts per-Pod requests" .-> HPA
~~~

**Do not confuse them:** HPA never raises a Pod's RAM limit; Cluster Autoscaler never raises a container's CPU limit; VPA never scales replica count just because QPS spikes.

### 14.2. HPA Computes CPU Utilization Relative to Request

Suppose a Pod requests `500m CPU` and measures `400m` CPU usage:

~~~text
CPU utilization per HPA = CPU usage / CPU request
                        = 400m / 500m
                        = 80%
~~~

If the HPA target is 60%, it sees a scale-out signal (subject to multi-Pod averaging, tolerance, stabilization windows, and rules). **This is not "80% of the `1000m` CPU limit."** Raising the request from `500m` to `1000m` with unchanged usage drops utilization from 80% to 40%, altering HPA behavior.

If a container omits the CPU request needed for utilization math, HPA may fail to compute the metric or skip Pods depending on configuration. **Accurate requests are therefore the foundation of CPU-based HPA.**

### 14.3. Sample HPA Manifest

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
  namespace: orders-lab
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 12
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
~~~

When using HPA, avoid having another pipeline/operator overwrite a fixed `spec.replicas` onto the same Deployment. Set `minReplicas`/`maxReplicas` aligned with SLOs, quotas, and budgets. HPA requires a working metrics pipeline; beyond CPU, it can use custom/external metrics where supported.

### 14.4. VPA Is Not a Second HPA

VPA can recommend resource sizing without immediately mutating Pods. Example **recommendation-only** configuration:

~~~yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: orders-api-vpa
  namespace: orders-lab
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  updatePolicy:
    updateMode: "Off"
~~~

VPA must be **supported/enabled** in the target GKE cluster. `Off` generates recommendations without automatically altering requests. Inspect via:

~~~bash
kubectl get vpa -n orders-lab
kubectl describe vpa orders-api-vpa -n orders-lab
~~~

Never let VPA automatically mutate the same resources HPA uses for utilization scaling without careful coordination: changing requests changes HPA's denominator, creating unpredictable oscillation. A safe pattern is **VPA in recommendation-only mode to tune baselines**, HPA scaling replicas on traffic/resources, and Cluster Autoscaler supplying node capacity.

### 14.5. When Can't Cluster Autoscaler Rescue a Pending Pod?

- A Pod's request **exceeds what any eligible machine type/node pool can offer**.
- `nodeSelector`/affinity targets labels absent from node pool templates.
- Taints/tolerations, topology spread, or PVC node affinity create unsatisfiable constraints.
- Max node count, regional quotas, IP exhaustion, or zonal capacity blocks scaling.
- `ResourceQuota`/`LimitRange`/admission blocks Pod creation or mutation.
- Requested GPU hardware is unavailable or out of quota.
- Policy rules or scale-up timing delays apply.

**Never turn on autoscaling and assume every `Pending` Pod fixes itself.** Read `kubectl describe pod`, autoscaler logs/metrics, and node pool limits to fix the real cause.

## 15. `ResourceQuota`, `LimitRange`, and Namespace Governance

### 15.1. `LimitRange`: Per-Container/Pod Guardrails

A namespace can define default, min, and max resources. Example `LimitRange` for containers only:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: orders-limits
  namespace: orders-lab
spec:
  limits:
  - type: Container
    defaultRequest:
      cpu: "250m"
      memory: "512Mi"
    default:
      cpu: "1000m"
      memory: "1Gi"
    min:
      cpu: "100m"
      memory: "128Mi"
    max:
      cpu: "2000m"
      memory: "4Gi"
~~~

Defaults apply only when fields are omitted and policies align. On Autopilot, GKE admission defaults/minimums/ratios interact with `LimitRange`; always verify created Pods and never use `LimitRange` expecting to bypass Autopilot guardrails.

### 15.2. `ResourceQuota`: Namespace-Level Budget

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-lab
spec:
  hard:
    requests.cpu: "8"
    requests.memory: "16Gi"
    limits.cpu: "16"
    limits.memory: "32Gi"
    pods: "30"
~~~

Quotas cap aggregate requests/limits and Pod counts per namespace. They **do not add nodes**; exceeding a quota causes the API server to reject Pod creation outright—distinct from a created Pod sitting **`Pending` because the scheduler found no node**.

When a namespace enforces a `ResourceQuota` on requests/limits, explicit resource declarations are enforced at admission. Size quotas above expected HPA `maxReplicas` and batch workloads so autoscaling doesn't hit a wall unexpectedly.

## 16. Diagnosing: From `Pending` to `OOMKilled`

### 16.1. Observation Commands Before Changing Anything

~~~bash
# Check workload and placement status.
kubectl get deployment -n orders-lab
kubectl get pods -n orders-lab -o wide

# Inspect Pod details and Events, especially FailedScheduling.
kubectl describe pod POD_NAME -n orders-lab

# Inspect events ordered chronologically.
kubectl get events -n orders-lab --sort-by=.lastTimestamp

# Inspect nodes and currently allocated requests.
kubectl get nodes -o wide
kubectl describe node NODE_NAME

# Inspect actual CPU/memory usage if metrics pipeline is available.
kubectl top pods -n orders-lab --containers
kubectl top nodes

# Inspect configured resources, quotas, and limits.
kubectl get deployment orders-api -n orders-lab -o yaml
kubectl get resourcequota,limitrange -n orders-lab
~~~

**`kubectl top` requires `metrics-server` or a compatible metrics pipeline.** If data is unavailable, check Cloud Monitoring / GKE Observability and the metrics pipeline rather than assuming "CPU usage is 0."

### 16.2. Root Cause and Action Matrix

| Symptom | Observation | Action Path |
|---|---|---|
| Pod `Pending`, `Insufficient cpu` | Requests exceed allocatable on eligible nodes | Right-size requests; check node pools/autoscaler |
| Pod `Pending`, `Insufficient memory` | Total memory requests don't fit | Lower requests if backed by metrics, or use nodes with more RAM |
| Pod `Pending` despite plenty of CPU | Taint/affinity/topology/PVC/Pod slot limits | Read all Events and constraints |
| Pod `Pending` minutes after HPA scales | Autoscaler hit max/quota/capacity or provisioning delay | Inspect autoscaler logs, quotas, IP ranges |
| Pod creation rejected | `ResourceQuota`/`LimitRange`/Autopilot admission | Read the API error, not just scheduler |
| Pod `Running` yet latency spikes | CPU throttling, GC, DB, or network | Inspect CPU usage/limit/throttling, traces, and p95/p99 |
| Container `OOMKilled` | Exceeded memory limit; heap/native memory higher than expected | Inspect `Last State`, RAM, heap, and memory limit |
| Pod `Evicted` | Node memory/disk/PID pressure or ephemeral storage | Inspect reason/events and node conditions |
| `ImagePullBackOff` | Image URI / registry IAM / network | Check Artifact Registry pull permissions |
| Pod `CrashLoopBackOff` | App crash, bad config, probes, OOM | Container logs, last termination state, probes |
| Node `NotReady` | Node/network/kubelet failure | Node status, events, GKE operations |
| HPA doesn't scale up | Missing metrics, missing CPU requests, `maxReplicas`/policy | `kubectl describe hpa`, metrics/requests |
| Only one zone has Pods | Node availability / topology constraints | Check node pool across zones and spread policies |
| Autopilot Pod shows different requests than YAML | Admission defaults/min/max/ratios | Read Pod post-mutation; inspect ComputeClass |

### 16.3. `OOMKilled` and `137`

~~~bash
kubectl describe pod POD_NAME -n orders-lab
kubectl logs POD_NAME -n orders-lab --previous
kubectl get pod POD_NAME -n orders-lab -o yaml
~~~

Look for:

- `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`.
- Rising restart count and whether OOMs align with traffic bursts or startup.
- Memory working set, heap, and direct buffers from JVM telemetry.
- `emptyDir.medium: Memory` or sidecars inflating memory footprint.
- Whether `LimitRange` or Autopilot mutated resource values at admission.

If OOM occurs during startup peaks, tune requests/limits, heap settings, and startup behavior. If caused by a memory leak, raising RAM only delays failure—profile and fix the leak. Never disable memory limits in production without assessing multi-tenant safety.

### 16.4. CPU Throttling Is Not CPU OOM

CPU throttling manifests as **slowness or timeouts** while the container stays `Running`. If CPU usage constantly hugs the limit and JVM GC/profiling shows contention, consider:

- Raising the CPU limit if workload and policy allow.
- Raising the request so the scheduler guarantees a matching CPU share.
- Testing omitting CPU limits in GKE Standard where guardrails permit.
- Scaling via HPA on appropriate metrics, or optimizing CPU-heavy code paths.
- Inspecting node CPU contention and cgroup throttling metrics.

**Never "fix" a CPU bottleneck by raising the memory limit**, or vice versa.

## 17. Case Study: Java Orders API on a Regional GKE Cluster

### 17.1. Context and Metrics

A hypothetical enterprise deploys a Java Orders API on GKE Standard using Cloud SQL PostgreSQL and Artifact Registry. The API runs multiple replicas behind a load balancer with requirements:

- p95 latency below **200 ms** under representative load.
- No total outage if a single node or single zone fails.
- Scale up to 12 Pods during promotions.
- Never store order data in Pod local ephemeral storage.
- Observable CPU/RAM cost forecasting and node pool sizing.

Initial benchmark numbers:

| Metric | Measured (Hypothetical) |
|---|---|
| Average / peak request rate | 250 / 700 RPS |
| Average / peak CPU per Pod | 280m / 650m |
| Steady-state JVM RSS | 620–800 MiB |
| Warm-up peak memory | 1.1 GiB |
| p95 latency | 155 ms |
| CPU throttling | Rises at peak if limit is 500m |
| DB latency | Portion of requests depend on Cloud SQL |

### 17.2. Choosing a Baseline Instead of Guessing

A candidate spec of request `500m`, memory `768Mi`, CPU limit `1000m`, and memory limit `1536Mi` serves as a **benchmark baseline**. Notice the 1.1 GiB warm-up peak exceeds the `768Mi` memory request, increasing eviction risk under node memory pressure; for critical workloads, raise memory requests closer to steady/peak usage with headroom and re-test.

Never set memory limit equal to `-Xmx`; non-heap memory needs RAM too. With JVM heap percentage flags, measure actual RSS and GC. Consider setting memory request **`1Gi`** and limit **`1536Mi`** if load testing confirms stability and acceptable cost.

### 17.3. Why Requests Are Not "Nice Round Numbers"

Suppose three Pods each request `1000m` even though average CPU usage is 280m. The scheduler reserves **3 CPUs**, while actual combined usage averages ~0.84 CPU, and HPA scales slower against the inflated denominator. Conversely, setting requests to `100m` just to pack more Pods causes CPU contention and triggers overly twitchy HPA scaling.

The right workflow: collect metrics across **real traffic cycles**, test several request profiles, and compare latency, restarts/evictions, bin-packing, and invoices—never pick values from a single average chart.

### 17.4. Three-Layer Autoscaling

1. **HPA** maintains 3–12 replicas from CPU/traffic with stabilization and capacity headroom.
2. **Cluster Autoscaler** adds nodes to Standard node pools when new Pods don't fit.
3. **Topology spread** distributes Pods across zones; PDBs limit simultaneous voluntary disruptions.
4. **VPA recommendations** review baseline sizing over time without mutating requests in conflict with CPU-based HPA.
5. **Cloud Monitoring** tracks p95 latency, CPU throttling, memory pressure, HPA desired/actual replicas, Pending Pods, node autoscaling, and cost.

### 17.5. From Java Image to Production

~~~mermaid
flowchart LR
    Code["Git Orders API"] --> Build["CI build + unit tests"]
    Build --> Artifact["Artifact Registry<br/>OCI image"]
    Artifact --> Deploy["GKE Deployment + HPA"]
    Deploy --> Pods["Pods across multiple zones"]
    Pods --> SQL["Cloud SQL"]
    Pods --> Storage["Cloud Storage"]
    Monitor["Cloud Monitoring + Logs"] -. "Telemetry" .-> Pods
~~~

Additional checks:

- IAM / Workload Identity for Cloud SQL and Cloud Storage access.
- Readiness, liveness, and startup probes matching app lifecycle.
- Graceful shutdown, termination grace period, and `preStop` if needed.
- Connection pooling: scaling replicas must not exhaust DB connection limits.
- Artifact image digests and release rollout/rollback procedures.
- Network policies, Ingress, HTTPS, and durable storage independent of Pod local disks.

## 18. Safely Rolling Out Requests/Limits Changes

### 18.1. A Resource Change Is Still a Deployment Change

Even without code changes, editing `requests`/`limits` in a Pod template creates a new ReplicaSet and triggers a rollout. In GKE Standard, certain versions support in-place container resource resizing where enabled, yet **never assume every workload or cluster resizes without disruption**. Verify GKE version, policy, and actual rollout behavior.

Workflow:

1. Capture pre-change baseline (requests, limits, usage, latency, restarts, billing).
2. Analyze capacity and quotas if increasing requests.
3. Validate YAML, admission policies, and Autopilot mutations if applicable.
4. Test in staging under representative traffic.
5. Roll out via rolling update/canary, watching for `Pending` or OOMs.
6. Inspect HPA/VPA/Cluster Autoscaler after deployment.
7. Monitor p95/p99, error rates, CPU throttling, memory pressure, and cost.
8. Keep previous manifests/versions ready to roll back if SLOs degrade.

### 18.2. PodDisruptionBudget Cannot Replace Requests

Minimal example:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders-lab
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

A PDB governs **certain voluntary disruptions** via the eviction API to keep too many Pods from being drained simultaneously where supported. It **does not prevent node crashes, `OOMKilled`, or outages**, nor does it ensure smooth rollouts when capacity is missing. Combine **replica counts, topology, requests, and capacity**.

### 18.3. Cost vs. Responsiveness Trade-Offs

| Decision | Benefit | Risk |
|---|---|---|
| Requests close to usage with headroom | Better bin-packing, less over-allocation | Contention/eviction if set too low |
| CPU limit higher than request | Allows bursting where supported | One Pod's CPU spike can affect neighbors if unmanaged |
| Requests == limits | Predictable QoS/resources; eligible for Guaranteed | Less ability to use idle headroom; throttling if limit is tight |
| Generous memory limit | Fewer OOMs during spikes | Higher node memory pressure risk if request is low |
| High HPA max | Handles traffic spikes | Can exceed quotas, DB capacity, and budgets |
| Hard topology anti-affinity | Stronger fault-domain separation | Can leave Pods `Pending` when nodes/capacity are tight |
| Larger node pools | Fits larger Pods | Higher cost during low utilization |
| Autopilot | Reduces node operations | Request sizing and ComputeClass pricing/features still matter |

**Never optimize on a single metric.** Low compute spend with unacceptable p99 latency fails business objectives.

## 19. Practice Exercises and Self-Assessment

### Exercise 1 — Summing Requests

A Pod has a Java container requesting `500m CPU, 768Mi memory` and a sidecar requesting `100m CPU, 128Mi memory`. Ignore init containers and Pod overhead.

**Question:** What are the total CPU/memory requests? What minimum total resources must be declared for three replicas?

**Hint:** One Pod = `600m` CPU, `896Mi` memory; three Pods = `1800m` CPU, `2688Mi` memory, excluding other system/overhead needs.

### Exercise 2 — Node Has Idle CPU Yet Pod Stays Pending

A node has 3500m allocatable CPU; running Pods request 3000m total. A new Pod requests 750m. Dashboards show 10% CPU usage.

**Question:** Can the scheduler place the new Pod on this node? Why might Cluster Autoscaler add a node despite low CPU usage?

**Hint:** Only 500m of unrequested allocatable CPU remains, so 750m does not fit.

### Exercise 3 — CPU Throttling

A Java API has request `250m`, CPU limit `500m`, steady demand above `500m`, and rising p99 latency without container restarts.

**Question:** Is this OOM? Which metrics should you inspect, and what options reduce throttling?

**Hint:** CPU limit causes throttling, not memory OOM; inspect throttled time, CPU utilization, thread/GC stats, and latency.

### Exercise 4 — `OOMKilled`

A container has memory limit `1024Mi` and `-Xmx1024m`, alongside direct buffers, metaspace, and thread stacks. The Pod restarts with `OOMKilled`.

**Question:** Why can't the heap consume the entire memory limit? What steps should precede raising the limit?

**Hint:** the memory limit covers the entire process footprint; measure RSS, heap, and native memory, tune heap headroom, and load test.

### Exercise 5 — Label-Based Scheduling

A Pod sets `nodeSelector: kubernetes.io/arch: amd64`, yet the entire cluster runs only `arm64` nodes.

**Question:** Will adding CPU to existing nodes fix it? What is the right fix?

**Hint:** no; provide nodes with a matching architecture or build multi-arch images and update constraints deliberately.

### Exercise 6 — Taints and Tolerations

A batch node pool has taint `dedicated=batch:NoSchedule`. A Pod has a matching toleration but no `nodeSelector`.

**Question:** Is the Pod guaranteed to run only on batch nodes? What must be added to restrict it **strictly** to batch nodes?

**Hint:** a toleration only permits scheduling; add node affinity/`nodeSelector` matching the pool's label.

### Exercise 7 — HPA CPU Utilization Math

CPU request = `500m`, usage = `400m`, CPU limit = `1000m`, HPA target = `60%`.

**Question:** What utilization does HPA see? If you raise only the request to `1000m` with unchanged usage, what does the ratio become?

**Hint:** 80%; after raising the request, 40%. HPA divides by **request**, not limit.

### Exercise 8 — Autopilot Mutation

An Autopilot Scale-Out Pod requests `1 vCPU` and `16Gi memory`, exceeding the allowed ratio.

**Question:** Which request might GKE adjust, why must you inspect the Pod post-admission, and why does that affect cost?

**Hint:** GKE may raise CPU to 4 vCPU to satisfy a 1:4 ratio per ComputeClass rules/limits; billable requests change accordingly.

### Exercise 9 — Multiple Replicas in One Zone

A Deployment with `replicas: 3` uses soft topology spread, yet the cluster only has nodes in zone A.

**Question:** Do three replicas provide zone-failure tolerance? What must change in cluster topology and scheduling?

**Hint:** no; provision multi-zone nodes/capacity and verify actual spread placement.

### Exercise 10 — VPA and HPA Adjusting Together

A team enables CPU-based HPA and VPA auto-updating CPU requests on the same Deployment.

**Question:** What feedback loop can occur? What is a safer way to use VPA initially?

**Hint:** request is HPA's denominator, so VPA mutating requests shifts HPA decisions; start with VPA `Off` for recommendations first.

### Exercise 11 — Quota vs. Scheduling

A namespace has `ResourceQuota` `requests.cpu=2`. A Deployment wants four Pods requesting `750m` each.

**Question:** What is the total request? If it exceeds the quota, is this a scheduler node-shortage error or an API Pod-creation rejection?

**Hint:** 3 CPUs total; the quota rejects Pod creation at admission rather than leaving Pods `Pending` for lack of nodes.

### Exercise 12 — Designing a Java Orders API

A Java app sees 4× weekend traffic spikes, depends on Cloud SQL, and needs p95 under 200ms. Propose:

- Baseline resource requests/limits grounded in JVM RSS, CPU/GC, and benchmarks.
- HPA min/max and metrics.
- Node autoscaling / Autopilot behavior.
- Zonal spread/anti-affinity, readiness, and PDBs.
- Observability, database connection pooling, release rollbacks, and budget.

**Hint:** benchmark under representative load before locking numbers; never raise HPA max without sizing Cloud SQL capacity.

## 20. Checklist for Real GKE Environments

- [ ] Identified cluster mode (**Standard or Autopilot**), Kubernetes/GKE version, ComputeClasses, and workload architecture.
- [ ] Distinguished `requests` and `limits` for CPU, memory, and ephemeral storage.
- [ ] Verified CPU `m` and memory `Mi`/`Gi` units, avoiding mistakes like `memory: "400m"`.
- [ ] Summed requests across all containers, effective init-container requests, and Pod overhead.
- [ ] Inspected node **Allocatable** and allocated requests, not just live CPU usage.
- [ ] Verified namespace `ResourceQuota`, `LimitRange`, and admission policies.
- [ ] Inspected `FailedScheduling` events before increasing node counts.
- [ ] Distinguished `nodeSelector`, required/preferred affinity, taints/tolerations, and topology spread.
- [ ] Checked zone topology and PVC/volume node affinity for stateful apps.
- [ ] Understood Guaranteed/Burstable/BestEffort QoS and real eviction behavior.
- [ ] Checked for CPU throttling, memory `OOMKilled`, ephemeral storage evictions, and logs.
- [ ] Separated HPA, VPA, and Cluster Autoscaler; avoided conflicting request/replica loops.
- [ ] On Autopilot, inspected **post-admission** resource values alongside current min/max/ratio/bursting rules.
- [ ] Configured readiness, liveness, and startup probes suited to JVM warm-up.
- [ ] Used real Artifact Registry OCI images with proper IAM pull permissions.
- [ ] Measured p95/p99 SLOs, throughput, restarts, availability, quotas, and costs under peak load.
- [ ] Defined rollout/rollback strategies, PDBs, and multi-replica/multi-domain placement for HA.
- [ ] Reviewed security controls: IAM, Workload Identity Federation for GKE, network policies, and secrets.
- [ ] Assigned owners, obtained change approvals, and cleaned up unused sandbox workloads.

## 21. Official Google Cloud and Kubernetes Documentation

Autopilot defaults, bursting features, machine types, ComputeClasses, and feature gates can change across versions. Always check official documentation before deploying to production:

- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes — Pod Quality of Service Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
- [Kubernetes — Assign Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes — Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Kubernetes — Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
- [Kubernetes — Limit Ranges](https://kubernetes.io/docs/concepts/policy/limit-range/)
- [GKE — Resource requests in Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [GKE — Autopilot overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [GKE — About Cluster Autoscaler](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [GKE — Configure Horizontal Pod Autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/horizontal-pod-autoscaling)
- [GKE — Vertical Pod Autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler)
- [GKE — Troubleshoot deployed workloads](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads)
- [GKE — Pricing](https://cloud.google.com/kubernetes-engine/pricing)

**Key takeaway:** In GKE, **requests determine where Pods can schedule and reserve capacity**, while **limits cap container runtime usage**. The **scheduler** evaluates node allocatable capacity and constraints; **HPA** scales Pod counts, **VPA** assists with Pod sizing, and **Cluster Autoscaler/Autopilot** supplies node capacity. To run Java services safely, combine **data-driven sizing, multi-zone spread, probes, IAM, monitoring, and cost controls**, then validate against real application behavior—not just seeing Pods in the `Running` state.
