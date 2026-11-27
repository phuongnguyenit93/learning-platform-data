# Nodes, Pods, and the Separation of Responsibilities Between Control Plane and Workers

Kubernetes manages container workloads by describing the desired state of an application and continuously reconciling the cluster to achieve that state. In this model, the **control plane** makes decisions and maintains the control state; **worker nodes** provide CPU, memory, networking, and storage to run workloads; and a **Pod** is the smallest deployable unit that Kubernetes schedules onto a node.

Understanding these three concepts helps design compute capacity properly. A cluster with many nodes may still fail to run more workloads if Pods request resources exceeding the capacity of individual nodes, are constrained by topology, or lack networking/storage. Similarly, even if worker nodes have free CPU and RAM, an application may still fail to be scheduled if the control plane cannot reach the API, the scheduler encounters an error, or a policy disallows placement.

In the CLOUD_CORE_SERVICES_COMPUTE module, this lesson connects virtual machine, CPU, memory, networking, and storage fundamentals with how Kubernetes allocates compute. You will see how the control plane decides where a Pod runs, how a worker node turns that decision into running containers, and why a Pod has a different lifecycle from a node.

After this lesson, you will be able to:

- Distinguish between a cluster, control plane, worker node, Pod, and container.
- Describe the roles of the API server, etcd, scheduler, and controller manager.
- Explain kubelet, container runtime, CNI, kube-proxy, and CSI on a worker node.
- Walk through the flow from declaring a Deployment to when a Pod runs and serves traffic.
- Read node Capacity/Allocatable and understand how requests/limits affect scheduling.
- Identify Pending, Running, Ready, and Failed states along with common reasons a Pod cannot be scheduled.
- Choose appropriate workload controllers and Pod distribution strategies aligned with compute capacity and availability.

## 1. The Big Picture of a Kubernetes Cluster

A Kubernetes cluster consists of a control plane and a set of nodes. In small clusters, the control plane and workers can co-exist on the same machine with an appropriate configuration; in production, the control plane is typically separated and may be managed by a cloud provider.

- **Control plane:** exposes the Kubernetes API, stores cluster state, schedules Pods, and runs controllers.
- **Worker node:** the compute machine that executes Pods. A node can be a VM or a physical machine, depending on how the cluster is deployed.
- **Pod:** the deployment unit containing one or more containers that share certain resources such as a network namespace and volumes.
- **Container:** an application process run by the container runtime on a node.
- **Kubernetes API objects:** objects such as Pod, Deployment, Service, Node, ConfigMap, Secret, and PersistentVolume that describe desired or observed state.

~~~mermaid
flowchart TB
    subgraph CP["Control plane"]
      API["kube-apiserver"]
      ETCD[("etcd")]
      SCH["kube-scheduler"]
      CM["kube-controller-manager"]
      CCM["cloud-controller-manager (if present)"]
      API <--> ETCD
      SCH --> API
      CM --> API
      CCM --> API
    end
    subgraph W1["Worker node A"]
      K1["kubelet"]
      CR1["Container runtime"]
      P1["Pod A"]
      K1 --> CR1 --> P1
    end
    subgraph W2["Worker node B"]
      K2["kubelet"]
      CR2["Container runtime"]
      P2["Pod B"]
      K2 --> CR2 --> P2
    end
    API <--> K1
    API <--> K2
    SCH -. bind Pod to node .-> API
~~~

The control plane and workers communicate via the Kubernetes API and related protocols. The scheduler does not run containers directly; it selects a node and writes the decision to the API. The kubelet on the node watches for Pods assigned to it and instructs the container runtime to create the corresponding containers.

### A Cluster Is Not Equivalent to One Large Machine

A cluster may consist of multiple VMs of different sizes, multiple node pools, and multiple failure domains. Kubernetes views nodes as allocatable pools of resources, yet each individual Pod must still fit within the capacity and policies of the chosen node.

For example, a cluster might have 64 vCPUs in total, while one Pod requests 20 CPUs. If no single node has enough remaining allocatable CPU to satisfy that request, the Pod can remain Pending even though the sum of free CPU across all nodes exceeds 20. The scheduler does not automatically split a single Pod across multiple nodes.

## 2. What Does the Control Plane Do?

The control plane maintains desired state and orchestrates components across the cluster. Its core components typically include:

| Component | Primary Responsibility | What It Does Not Directly Do |
|---|---|---|
| kube-apiserver | API gateway; handles authentication, authorization, admission, and provides the interface for clients/components | Does not select nodes for Pods itself |
| etcd | Consistent key-value store persisting cluster state and critical configuration | Does not run application containers |
| kube-scheduler | Selects an appropriate node for unassigned Pods | Does not create containers on nodes |
| kube-controller-manager | Runs controllers to compare actual state with desired state and make adjustments | Does not replace kubelet in running containers |
| cloud-controller-manager | Integrates with a cloud provider for functions such as nodes, routes, and load balancers | Not required in every cluster or environment |

Some clusters also include additional components such as API aggregation, admission webhooks, scheduler profiles, or controllers installed by the platform provider or applications.

### kube-apiserver

The Kubernetes API is the central communication hub. Users, CI/CD pipelines, the scheduler, controllers, and kubelets all exchange information through the API server.

When running `kubectl apply`, the client sends the manifest to the API server. The API server authenticates the request, checks authorization, runs the admission chain, and persists valid objects to etcd. Other components watch or read the API to react to changes.

The API server can run multiple replicas behind a load balancer. In self-managed clusters, you need to protect the endpoint, certificates, authentication, authorization, and audit logs. In managed Kubernetes, the provider typically operates the control plane, but the customer remains responsible for API access permissions and workload configuration.

### etcd

etcd stores Kubernetes state data such as objects, metadata, and cluster configuration. It is a critical component of the control plane.

Operational principles:

- Maintain quorum according to cluster design; do not arbitrarily reduce the number of members.
- Protect data with backups/snapshots and test restores.
- Encrypt sensitive data according to the appropriate configuration.
- Monitor etcd latency, disk I/O, storage capacity, and health.
- Do not allow application workloads to access etcd directly.
- Avoid storing business application data in etcd; use an appropriate database or storage system.

Losing etcd quorum can prevent the cluster from writing new state, impacting scheduling and controllers. Already running Pods may continue processing for some time, but creating, updating, or newly orchestrating workloads can be disrupted.

### kube-scheduler

The scheduler watches for Pods without a `nodeName` and finds a suitable node. The general process consists of:

1. Filtering out nodes that do not meet the requirements (filtering).
2. Scoring the remaining nodes according to policy (scoring).
3. Selecting a node with an appropriate score.
4. Writing the binding/assignment via the API.
5. The kubelet on the node detects the assigned Pod and begins deployment.

The scheduler evaluates many factors: CPU/memory requests, node selectors, node affinity, taints/tolerations, topology spread, volume constraints, pod affinity/anti-affinity, and enabled policies/plugins.

The scheduler does not simply pick the node with the lowest CPU utilization. It primarily relies on requests and placement conditions; actual usage, resource limits, policies, and scoring can be handled according to specific plugins/configurations.

### kube-controller-manager

Controllers are reconciliation loops. Each controller observes the current state and makes adjustments to bring it closer to the desired state.

Examples:

- The Deployment controller manages ReplicaSets.
- The ReplicaSet controller creates or deletes Pods to achieve the desired replica count.
- The Node controller monitors node health/status.
- The Job controller orchestrates Pods performing finite tasks.
- The EndpointSlice controller updates backend endpoints for Services.

If a Deployment specifies 3 replicas but only 2 Pods are Ready, the controller will keep trying to create or restore the third replica when conditions permit. A controller does not guarantee reaching the desired state immediately if capacity is lacking or policies block placement.

## 3. Worker Nodes Provide Compute and Run Pods

Worker nodes are the actual compute machines. They can be cloud VMs, bare-metal servers, or nodes managed by a Kubernetes service. Nodes require resources and agents to join the cluster.

Common components:

- **kubelet:** the agent on each node that ensures Pods assigned to that node are running according to their PodSpec.
- **Container runtime:** pulls images and runs containers via the Container Runtime Interface (CRI), such as containerd or CRI-O.
- **CNI plugin:** configures network connectivity for Pods according to the cluster's network model.
- **kube-proxy or alternative dataplane:** implements part of Service networking; some clusters use eBPF or other solutions instead of kube-proxy.
- **CSI node plugin:** integrates volume attach/mount operations for workloads using storage via the Container Storage Interface.
- **Node-level agents:** telemetry, logging, security, device plugins, or platform-installed agents.

Not every node runs the exact same set of daemons. Configuration depends on the Kubernetes distribution, cloud provider, CNI, CSI, and operational policies.

### kubelet

The kubelet registers/maintains node status, watches Pods assigned to its node, and interacts with the container runtime. It:

- Reads the PodSpec provided by the API server.
- Instructs the runtime to create the sandbox and containers.
- Mounts volumes as configured.
- Executes startup, readiness, and liveness probes.
- Reports Pod/node status back to the API server.
- Coordinates with eviction mechanisms when the node experiences resource pressure.

The kubelet is not a scheduler. It does not decide which node a Pod should run on; it executes the Pods that have already been assigned to its node.

### Container Runtime and CRI

The container runtime is responsible for pulling images, creating containers, and managing process lifecycles. Kubernetes communicates with the runtime through CRI.

Images cached on a node can help Pods start faster. However, you should not rely on the local cache as the sole source; when a Pod moves to another node, the new node may need to pull the image again from the registry.

Requirements to prepare:

- An image registry reachable from every node that needs to run the workload.
- Explicit image versions/digests.
- Appropriate image pull secrets or workload identities.
- Sufficient disk space for image layers and writable layers.
- Runtime versions compatible with Kubernetes and the node OS.

### CNI, kube-proxy, and CSI

| Component | Role | Scope |
|---|---|---|
| CNI | Assigns IP addresses and network connectivity to Pods; may enforce policies | Pod network |
| kube-proxy or equivalent dataplane | Forwards traffic to Service endpoints according to the implementation | Service networking |
| CSI | Integrates storage drivers to attach/mount volumes | Persistent/ephemeral volumes |

CNI, kube-proxy, and CSI are not identical mandatory core control plane components across all clusters. Some capabilities may be provided by the cloud provider or a different dataplane.

## 4. How Are Nodes, Pods, and Containers Different?

| Object | What Is It? | Lifecycle | Resources |
|---|---|---|---|
| Node | Compute machine participating in the cluster | Can be added, cordoned, drained, upgraded, or deleted | CPU, RAM, disk, network, devices |
| Pod | Scheduling unit containing one or more containers | Typically shorter-lived than a node; can be recreated on another node | Sum of container requests/limits and related overhead |
| Container | Application process run by the runtime | Can restart within the same Pod | Bounded by container/Pod resource configuration and the runtime |
| Deployment | Controller describing replicas and rollouts for stateless apps | Managed across multiple Pods and revisions | Does not provide CPU/RAM itself; its Pod template declares resources |
| Service | Stable endpoint for accessing a group of Pods | Exists independently of individual Pod IPs | Not a compute instance |

### Pod Is the Scheduling Unit

The scheduler assigns a Pod to a single node. Containers within the same Pod are always placed on the same node and share certain namespaces/resources.

Containers in a Pod typically:

- Share a network namespace and the same Pod IP.
- Can call each other via `localhost` if using different ports.
- Can share volumes declared at the Pod level.
- Can follow sidecar, init container, or application container patterns.
- Are managed as a single unit with respect to placement and Pod lifecycle.

Do not bundle multiple independent applications into a single Pod just to save nodes. When independent scaling or releasing is needed, split them into separate Pods and connect them via Services.

### A Pod Is Not a Mini VM

A Pod does not have its own kernel like a VM. Containers in a Pod share the node's kernel and are isolated using OS mechanisms such as namespaces and cgroups. Therefore:

- Kernel/OS compatibility pertains to the node.
- A failing Pod does not mean the node has failed.
- A failing node can affect multiple Pods simultaneously.
- The security boundary of a container differs from a VM boundary.
- Pod IP and container IDs can change when a Pod is recreated.

### Pod IP and Service

A Pod typically receives its own IP address within the cluster network, but that Pod IP can change when the Pod is recreated. Clients should not hardcode Pod IPs. A Service provides a stable endpoint and distributes traffic to eligible backend Pods.

## 5. Flow from Manifest to Running Pod on a Worker Node

Suppose a user creates a Deployment with 3 replicas:

1. `kubectl apply` sends the manifest to the API server.
2. The API server authenticates, authorizes, runs admission, and stores the Deployment in etcd.
3. The Deployment controller observes the Deployment and creates a ReplicaSet.
4. The ReplicaSet controller creates 3 Pod objects.
5. The scheduler detects Pods that have not been assigned a node.
6. The scheduler filters and scores nodes based on resource requests and policies.
7. The scheduler writes a binding for each Pod.
8. The kubelet on the corresponding worker node receives the PodSpec.
9. The kubelet calls the runtime via CRI to create the Pod sandbox and containers.
10. CNI sets up networking for the Pod.
11. CSI or kubelet mounts volumes if the Pod requires storage.
12. Containers start; startup/readiness/liveness probes are executed.
13. The Pod transitions to Ready when readiness conditions succeed.
14. Service/EndpointSlice places eligible endpoints into the traffic path.

~~~mermaid
sequenceDiagram
    participant U as User/kubectl
    participant API as API server
    participant E as etcd
    participant C as Controllers
    participant S as Scheduler
    participant K as kubelet
    participant R as Runtime/CNI/CSI
    U->>API: Apply Deployment
    API->>E: Persist desired state
    API-->>U: Accepted
    C->>API: Watch Deployment
    C->>API: Create ReplicaSet and Pods
    S->>API: Watch unscheduled Pods
    S->>API: Bind Pod to selected Node
    K->>API: Observe assigned Pod
    K->>R: Create sandbox, containers and mounts
    R-->>K: Runtime/network/storage ready
    K->>API: Report Pod status and probes
~~~

If a Pod is not running, identify which step it is stuck at: unscheduled, image pull failure, volume mount error, container crash, or readiness not yet passing. Each state requires a different investigation path.

## 6. Node Capacity and Allocatable

A node has total hardware resources (Capacity), but not all of them are available for workload Pods.

- **Capacity:** total resources advertised by the node, such as CPU, memory, ephemeral storage, and maximum Pod count.
- **Allocatable:** the amount of node resources available for Pods after subtracting reservations for the OS, kubelet, and configured system reservations.
- **Requested:** total requests accounted for by the scheduler for Pods already assigned to the node.
- **Actual usage:** the actual CPU/memory being consumed by workloads at the time of measurement.

For example, a node has 8 vCPUs and 32 GiB of RAM. If the OS and system daemons reserve 1 CPU and 3 GiB, allocatable might be around 7 CPUs and 29 GiB. These are illustrative numbers; actual values must be read from the Node object and node configuration.

~~~text
Node Capacity
  CPU:       8 vCPU
  Memory:    32 GiB
       |
       | minus system/kube reservations
       v
Node Allocatable
  CPU:       7 vCPU
  Memory:    29 GiB
       |
       | minus total scheduled Pod requests
       v
Remaining allocatable capacity for new Pods
~~~

The scheduler primarily uses requests to evaluate whether a Pod can fit. If total requests exceed allocatable, a new Pod may not be scheduled even if current actual usage is low. This protects capacity against the committed consumption of workloads.

### Inspecting Node Capacity with kubectl

~~~bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu,MEMORY:.status.capacity.memory,MEMORY_ALLOC:.status.allocatable.memory
~~~

In `kubectl describe node`, review the Capacity, Allocatable, Conditions, Addresses, Taints, and Non-terminated Pods sections. The listed Pod requests/limits help reveal how much resource capacity has been allocated by requests.

## 7. Pod Requests and Limits

Containers can declare CPU/memory requests and limits. This is an essential mechanism for scheduler placement and node resource management.

- **Request:** the amount of resource used for scheduling and as the basis for certain resource management decisions.
- **Limit:** the maximum resource usage permitted for a container according to the resource's semantics.
- CPU limits are typically enforced via throttling when a container exceeds its quota within a measurement interval.
- Memory limits are typically enforced via OOM kill when usage exceeds the threshold, depending on node and kernel state.

Example:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: compute-example
spec:
  containers:
    - name: app
      image: registry.example/compute-app:1.0.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "1"
          memory: "1Gi"
~~~

This Pod asks the scheduler to reserve 0.5 CPU and 512 MiB of memory based on requests. The container can use up to 1 CPU and 1 GiB of memory based on limits. `500m` CPU equals half a CPU core in Kubernetes units; `1` equals one Kubernetes-defined CPU unit.

### Total Requests of Multi-Container Pods

A Pod may contain multiple application containers, sidecars, and init containers. The scheduler computes a Pod's resource request using Kubernetes aggregation rules; init containers can alter the effective request of the Pod compared to merely summing concurrently running containers. For Pods with sidecar injection or init containers, inspect the actual effective resource requests after admission.

### QoS Classes

Kubernetes classifies Pods into QoS classes based on container requests/limits:

- **Guaranteed:** CPU and memory requests and limits for every container meet Kubernetes rules and are equal.
- **Burstable:** has at least one request or limit but does not meet Guaranteed criteria.
- **BestEffort:** declares no CPU or memory requests/limits for any container.

QoS class influences eviction/handling order when a node runs low on resources, but it is not an absolute guarantee that Guaranteed Pods will never be affected. Node pressure, system failures, and other conditions can still disrupt Pods.

### Avoid Arbitrary Resource Declarations

- Requests too low: the scheduler may pack too many Pods onto a node, causing contention under load.
- Requests too high: capacity is reserved on paper, Pods become hard to schedule, and autoscalers may provision unnecessary nodes.
- CPU limits too low: throttling can increase latency even when the node has spare CPU.
- Memory limits too low: containers may be OOMKilled.
- No requests declared: the scheduler cannot easily predict demand and the QoS class may become BestEffort.

Measure representative load, set requests based on steady-state demand, and set limits according to appropriate protection policies. Monitor actual usage and saturation to tune over time.

## 8. Scheduler Placement: Why Was a Pod Placed on This Node?

The scheduler selects a node based on constraints and scoring. Common factors include:

- Sufficient remaining CPU/memory/ephemeral-storage requests.
- `nodeSelector` or node affinity.
- Node taints and Pod tolerations.
- Pod affinity/anti-affinity.
- Topology spread constraints.
- Volume zone/node constraints.
- Node conditions and schedulability.
- Extended resources such as GPUs or devices advertised by device plugins.
- Scheduler policies/plugins configured on the cluster.

### Node Selector

Uses labels to require a Pod to run on nodes with specific attributes, such as a GPU group or CPU architecture.

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: amd64
    workload-pool: batch
~~~

If no node has all required labels, the Pod stays Pending. Verify actual node labels and avoid hardcoding custom labels without a management process.

### Taints and Tolerations

A taint marks a node to repel Pods without a matching toleration. A toleration allows a Pod to be considered for a tainted node; it does not guarantee the Pod will be scheduled onto that node.

For example, a GPU node has a taint reserved for GPU workloads. Only Pods with the matching toleration can run there; the Pod still needs to declare the extended resource and satisfy other placement conditions.

### Affinity and Topology Spread

Pod anti-affinity or topology spread can distribute replicas across nodes/zones to reduce correlated failures. However, if the cluster lacks enough nodes or topology domains, overly strict constraints can leave Pods Pending.

Balance availability, utilization, and schedulability. For example, requiring three replicas across three different zones requires at least three valid domains and corresponding capacity.

## 9. Pod Lifecycle and Status

Pods are ephemeral objects. When a Pod is deleted or a node is lost, Kubernetes can create a new Pod via its controller, but the new Pod typically receives a different UID and IP.

Common phases:

| Phase | Meaning | What to Check |
|---|---|---|
| Pending | Accepted by the cluster but setup is incomplete; may be waiting for scheduling or container preparation | Events, scheduler, image pull, volumes |
| Running | Pod has been assigned to a node and at least one container is running or starting | Container state, logs, probes |
| Succeeded | All containers terminated successfully | Job completion and output |
| Failed | Containers terminated with error or Pod could not complete | Exit codes, logs, events |
| Unknown | State cannot be determined, often due to node communication issues | Node health and kubelet connectivity |

Ready is not a Pod phase; it is a condition indicating whether the Pod is ready to receive traffic based on its readiness probe and related conditions.

### Probes

- **Startup probe:** gives the application time to start up; liveness/readiness checks can be delayed until the startup probe succeeds.
- **Readiness probe:** determines whether a Pod should receive traffic through a Service.
- **Liveness probe:** determines whether a container needs to be restarted.

Probes must check the right conditions. An overly sensitive liveness probe can trigger a restart loop when a dependency is slow; an overly broad readiness probe can remove all Pods from traffic because of a non-essential secondary dependency.

### Pod Restarts and Replacement

Containers can restart inside the same Pod; a Pod object can also be replaced with a new Pod by its controller. Distinguish `restartCount`, Pod UID, and owner references when investigating. Do not use a Pod's local filesystem as the sole storage location for data if the Pod can be recreated.

## 10. Workload Controllers and How They Use Nodes

Workload controllers define how Pods are created and maintained:

| Controller | Purpose | Example |
|---|---|---|
| Deployment | Manages stateless applications, rollouts, and replicas | Web API, frontend |
| ReplicaSet | Maintains a specified number of Pods from a template | Usually managed by a Deployment |
| StatefulSet | Workloads requiring stable ordinal-based identity/network/storage | Suitable databases or stateful systems |
| DaemonSet | Runs one Pod per node or selected set of nodes | Log agents, network/security agents |
| Job | Runs finite work until completion | Batch jobs, migrations |
| CronJob | Creates Jobs on a schedule | Nightly reports, cleanup |
| ReplicationController | Legacy mechanism; Deployment/ReplicaSet are normally used now | Legacy workloads |

### Deployment Example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: compute-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: compute-api
  template:
    metadata:
      labels:
        app: compute-api
    spec:
      containers:
        - name: api
          image: registry.example/compute-api:1.4.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
~~~

The Deployment requests three replicas. The controller creates Pods and replaces them when needed to maintain the desired count. The scheduler decides the node for each Pod; the kubelet on that node runs the containers.

### DaemonSets and Node-Level Compute

DaemonSets are commonly used for agents that must be present on every node, such as log collectors or security agents. These Pods also consume node CPU/RAM and must be accounted for in capacity planning. If an agent's memory usage grows, application workloads may run short of allocatable capacity even if application requests remain unchanged.

## 11. Networking: Pod Network and Services

Each Pod typically has its own IP address in the cluster network. Containers in the same Pod share a network namespace, so they can communicate over `localhost`. Different Pods communicate via Pod IP or Service.

Components:

- CNI plugin creates interfaces and connects Pods to the cluster network.
- Network policy plugins can control traffic between Pods, namespaces, and endpoints.
- Services provide stable addresses/DNS for a group of Pods.
- EndpointSlices reflect eligible backend endpoints.
- Ingress or Gateway API can manage incoming HTTP/TLS traffic to the cluster.
- kube-proxy or an alternative dataplane handles Service routing according to the implementation.

### Pod IPs Are Not Durable Endpoints

When a Pod is replaced, its IP can change. Applications should use Service DNS such as `compute-api.namespace.svc` instead of hardcoding Pod IPs.

Service example:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: compute-api
spec:
  selector:
    app: compute-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

A Service selects Pods with matching labels that qualify as endpoints. If a readiness probe fails, the Pod is normally excluded from regular serving endpoints. Check selectors, labels, ports, and EndpointSlices when a Service fails to route traffic.

### Network Performance

For compute workloads, networking can become a bottleneck:

- Cross-node or cross-zone Pod-to-Pod traffic.
- Overlay/encapsulation overhead depending on the CNI.
- Bandwidth/packet rate limits of the node VM.
- MTU mismatches.
- Network policy and dataplane processing overhead.
- Egress/NAT or cloud load balancer quotas.

Monitor throughput, packet drops, retransmissions, latency, and connection counts at both the node and application levels.

## 12. Storage: Ephemeral and Persistent Volumes

Container filesystems usually include a writable layer tied to the container/Pod lifecycle. When a Pod is recreated, data in that layer can be lost.

### Ephemeral Storage

Nodes provide ephemeral storage for image layers, writable layers, and temporary volumes such as `emptyDir`. This is a finite resource; excessive usage can cause node disk pressure and lead to eviction.

You can declare requests/limits for ephemeral storage so Kubernetes manages it according to configuration:

~~~yaml
resources:
  requests:
    ephemeral-storage: "1Gi"
  limits:
    ephemeral-storage: "2Gi"
~~~

### Persistent Volumes

For data that must survive Pod replacement, use a PersistentVolumeClaim and an appropriate storage provisioner/CSI. A volume's lifecycle can be independent of the Pod, though it still depends on access mode, storage class, zone, and driver.

Not all volumes can be mounted simultaneously on multiple nodes. When a Pod is scheduled to a different zone, the volume may fail to attach if storage topology is restricted. The scheduler and CSI topology must coordinate to place the Pod where the volume can be used.

## 13. Node Health, Cordon, Drain, and Node Replacement

A node can transition to `NotReady` when kubelet loses connectivity, the runtime fails, networking breaks down, or the host encounters an issue. Kubernetes can update node conditions and handle Pods according to policy.

Operational concepts:

- **cordon:** marks a node so the scheduler will not place new Pods on it.
- **drain:** evicts eligible Pods to prepare for node maintenance/deletion; behavior depends on DaemonSets, PodDisruptionBudgets, and command flags.
- **uncordon:** allows the scheduler to consider the node again.
- **Node replacement:** provisions a new node, lets workloads reschedule, and then removes the old node.

Examples:

~~~bash
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets
kubectl get pods -A -o wide
kubectl uncordon <node-name>
~~~

`drain` can be blocked by a PodDisruptionBudget or by Pods not managed by a controller. Do not use `--force` or `--delete-emptydir-data` without understanding the impact on workloads and data.

### PodDisruptionBudget

A PodDisruptionBudget (PDB) limits voluntary disruptions for a group of Pods—for instance, the minimum number of Pods that must remain available during a drain. A PDB does not protect against node crashes, power loss, or region outages; it primarily coordinates with evictions caused by voluntary disruptions.

To drain safely, ensure sufficient replicas, accurate readiness probes, capacity on other nodes, and an appropriate PDB. An overly strict PDB can block maintenance; an overly loose PDB can reduce availability.

### Node Pressure and Eviction

When a node runs short of memory, disk, or inodes, kubelet can trigger eviction based on thresholds and priority. BestEffort Pods or Pods whose usage exceeds requests may be affected earlier depending on conditions. Monitor Node Conditions such as `MemoryPressure`, `DiskPressure`, and `PIDPressure`, along with eviction events.

## 14. Compute Capacity Planning for Kubernetes

Capacity planning must account for both workloads and system overhead on nodes.

### Calculating Total Requests

Suppose each API Pod requests `500m` CPU and `512Mi` memory. With 6 replicas:

- Total CPU requests: 6 × 0.5 = 3 CPUs.
- Total memory requests: 6 × 512Mi = 3,072Mi (about 3 GiB).

If a node has 7 CPUs and 29 GiB allocatable remaining, it can theoretically hold these Pods alongside other workloads within request limits. However, you must also consider DaemonSets, Pod overhead, topology, anti-affinity, volume zones, and headroom.

Do not plan based solely on total requests. Observe actual usage, bursts, node system overhead, and fault tolerance when a node or zone is lost.

### Headroom and N+1

If workloads must continue serving when a node is lost, the cluster needs enough remaining capacity to run replicas on the surviving nodes. With N+1, calculate capacity not only for steady state, but also for the state after one node or failure domain is removed.

### Node Pools

Node pools can be separated by workload characteristics:

- General-purpose for standard APIs and services.
- Compute-optimized for CPU-bound tasks.
- Memory-optimized for caches or high-RAM workloads.
- GPU/accelerator pools for ML or specialized processing.
- Spot/interruptible pools for retryable batch jobs.
- System pools dedicated to platform components.

Separate node pools help manage instance families, autoscaling, taints/labels, and cost. However, workloads must have matching tolerations/affinity, and the pool must have available capacity.

### Cluster Autoscaler and Workload Autoscalers

- Horizontal Pod Autoscaler (HPA) adjusts replica counts based on metrics such as CPU, memory, or custom metrics.
- Vertical Pod Autoscaler (VPA) can recommend or adjust requests depending on its mode/configuration.
- Cluster Autoscaler or node autoscalers add/remove nodes when Pods cannot be scheduled or nodes have excess capacity, depending on the implementation.

HPA can increase replicas, but if the node pool runs out of capacity, Pods will remain Pending. A node autoscaler can provision new nodes, but booting, pulling images, and reaching readiness take time. Plan adequate headroom and appropriate scaling signals.

## 15. Troubleshooting: From Pending Pods to NotReady Nodes

When a Pod is not running, do not start by blindly adding nodes. Identify the failure point in the chain: API → scheduler → kubelet → runtime/network/storage.

### Pod Pending

~~~bash
kubectl get pods -A
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp
~~~

Common causes:

- `Insufficient cpu` or `Insufficient memory`: requests do not fit node allocatable capacity.
- `node(s) didn't match Pod's node affinity/selector`: labels or affinity rules do not match.
- `untolerated taint`: the Pod lacks a required toleration.
- `volume node affinity conflict`: volume and node reside in different topologies.
- `pod has unbound immediate PersistentVolumeClaims`: the PVC is not yet bound.
- Overly strict topology spread/anti-affinity.
- No nodes available with required extended resources such as GPUs.

### ImagePullBackOff or ErrImagePull

Check image name/tag/digest, registry connectivity, credentials, image pull secrets, and CPU architecture. An `amd64` image will not run directly on an `arm64` node without a multi-arch manifest or matching build.

### CrashLoopBackOff

Check logs before/after restart, exit codes, command/args, configs, secrets, volume mounts, OOMKilled status, and probes. `CrashLoopBackOff` is the backoff state between restarts, not the root cause itself.

### Node NotReady

~~~bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get pods -A -o wide
~~~

Check kubelet heartbeats, container runtime, CNI, disk/memory pressure, node networking, certificates, and cloud VM health. In managed Kubernetes, the provider may offer additional node diagnostics; still inspect cluster-side events and workload impact.

### Service Has No Endpoints

~~~bash
kubectl get svc -n <namespace>
kubectl get endpointslices -n <namespace>
kubectl describe svc <service-name> -n <namespace>
~~~

Verify whether the selector matches Pod labels, whether Pods are Ready, whether `targetPort` is correct, and whether network policies are blocking traffic.

## 16. Security and Shared Responsibility

Kubernetes does not automatically guarantee that every Pod is secure simply because it runs inside a cluster. Responsibilities are divided between the cloud provider/platform team and the application team.

### Control Plane

- Protect API endpoints and certificates.
- Configure authentication, RBAC, and admission policies.
- Encrypt secrets at rest according to platform capabilities.
- Back up/restore etcd or use a managed control plane service per provider guidance.
- Audit API requests and restrict `cluster-admin` privileges.
- Update Kubernetes versions and verify compatibility.

### Worker Nodes

- Patch the OS/kernel and container runtime.
- Restrict SSH/remote access; use identity and access gateways.
- Protect kubelet endpoints and node credentials.
- Configure disk encryption and secure boot where available.
- Manage image provenance, vulnerability scanning, and registry access.
- Monitor runtime, node agents, and network policies.

### Pods/Workloads

- Run as non-root whenever possible.
- Use `securityContext`, seccomp, and minimal capabilities.
- Do not run `privileged` containers without a clear reason.
- Restrict service account tokens and follow least-privilege RBAC.
- Set CPU/memory/ephemeral-storage requests and limits.
- Use `NetworkPolicy` when supported by the CNI.
- Inject secrets via a secrets manager/CSI or protected Kubernetes Secrets.
- Never bake credentials into images, public manifests, or logs.

### Shared Responsibility in Managed Kubernetes

The provider may operate the control plane, etcd, API availability, and parts of upgrades. Customers typically remain responsible for worker configuration, Pod security, RBAC, network policies, images, data, workload availability, and capacity. Exact boundaries depend on the managed service.

## 17. Practical Example: Deploying an API Across Three Worker Nodes

An API application needs three replicas to serve users. The cluster has three worker nodes, each with 4 vCPUs and 16 GiB of RAM. After subtracting system reservations, assume each node has 3.5 CPUs and 14 GiB allocatable.

Each API Pod declares requests of `500m` CPU and `512Mi` memory. Three Pods require a total of 1.5 CPUs and 1.5 GiB based on requests. The scheduler can spread one Pod per node if topology spread or anti-affinity is configured. Without constraints, the scheduler may place multiple Pods on the same node based on scoring.

When node 2 becomes `NotReady`:

1. The Node controller detects that heartbeats have stopped.
2. Pods on the node may transition to `Unknown`/`Terminating` depending on timeouts and policies.
3. The Deployment/ReplicaSet continues maintaining the desired replica count.
4. The scheduler finds another node with sufficient capacity for a replacement Pod.
5. The kubelet on the new node pulls the image, creates the containers, and configures networking.
6. The readiness probe succeeds, and endpoints are updated.
7. The Service continues routing traffic to the remaining Ready Pods.

To tolerate a node failure without over-degrading capacity, the cluster must have enough headroom on nodes 1 and 3. If the remaining two nodes are already full on requests, the replacement Pod can remain Pending. Specifying three replicas in a manifest does not create physical capacity on its own.

### Example Observation Commands

~~~bash
kubectl get nodes -o wide
kubectl get pods -n production -o wide
kubectl top nodes
kubectl top pods -n production
kubectl describe node <node-name>
kubectl describe pod <pod-name> -n production
~~~

`kubectl top` requires Metrics Server or a compatible metrics source. Usage figures are point-in-time snapshots; use long-term monitoring to analyze trends and saturation.

## 18. Kubernetes Compute Design and Operations Checklist

### Cluster Architecture

- [ ] Determined whether the control plane is managed or self-managed.
- [ ] API server, etcd, scheduler, and controllers have appropriate health/availability.
- [ ] Worker nodes run compatible OS/runtime/CNI/CSI versions.
- [ ] Node pools are matched to CPU, memory, GPU, and workload classes.
- [ ] Spare capacity is reserved for node/zone failures.

### Pods and Resources

- [ ] Pods are designed with appropriate container boundaries.
- [ ] CPU/memory requests are measured and declared.
- [ ] Limits are set based on latency, stability, and policy.
- [ ] Ephemeral storage is budgeted and monitored.
- [ ] Readiness/liveness/startup probes accurately reflect application health.
- [ ] Pods do not store sole durable data in the writable layer.

### Scheduling and Availability

- [ ] Node selectors/affinity/taints/tolerations are applied intentionally.
- [ ] Topology spread/anti-affinity align with failure domains and capacity.
- [ ] PodDisruptionBudgets do not unintentionally block maintenance.
- [ ] Drain and node replacement workflows have been tested.
- [ ] HPA and node autoscalers have clear metrics, headroom, and limits.

### Networking and Storage

- [ ] CNI/Service dataplane operates properly and is monitored.
- [ ] Applications use Service DNS rather than hardcoding Pod IPs.
- [ ] NetworkPolicies match expected traffic flows.
- [ ] PVCs/storage classes use appropriate topology and access modes.
- [ ] CSI attach/mount and restore procedures have been tested.

### Operations and Security

- [ ] Runbooks exist for investigating Pending, CrashLoopBackOff, OOMKilled, and NotReady states.
- [ ] Centralized logging, metrics, events, and tracing are in place.
- [ ] RBAC, service accounts, and workload identities follow least privilege.
- [ ] Images are versioned and scanned for vulnerabilities.
- [ ] Node OS, runtime, and Kubernetes are patched on schedule.
- [ ] Control plane/data backups align with actual responsibilities and architecture.

## 19. Self-Check

1. How do a Node, a Pod, and a Container differ in role and lifecycle?
2. Why does the scheduler assign a Pod to a node without directly creating containers?
3. What responsibilities do `kube-apiserver`, `etcd`, `kube-scheduler`, and `kube-controller-manager` handle?
4. How does `kubelet` coordinate with the container runtime to run a Pod?
5. What types of resources do CNI, kube-proxy/dataplane, and CSI manage?
6. Why can a Pod requesting 20 CPUs stay Pending even when the cluster has more than 20 CPUs free in aggregate?
7. Distinguish between Capacity, Allocatable, Requests, Limits, and Actual Usage.
8. How can CPU limits and memory limits affect a container differently?
9. Why should a Pod IP not be used as a durable endpoint?
10. When a node becomes NotReady, how do Deployment and the scheduler coordinate to create a replacement Pod?
11. Which types of disruptions does a PDB protect against, and which incidents does it not protect against?
12. Analyze a Pod Pending due to `Insufficient memory` and propose how to verify the cause before scaling up a node pool.

Kubernetes separates orchestration decisions from where workloads execute. The control plane stores and reconciles desired state; the scheduler picks a node; worker nodes supply CPU, RAM, networking, and storage; and the kubelet together with the runtime turns a PodSpec into running containers. By understanding these boundaries and accurately measuring Capacity, Allocatable, requests, limits, and Pod/node states, teams can plan compute, scale, and recover workloads on a solid engineering footing.
