# Roles of Clusters, Nodes, Workloads, and Services in a Container Platform

## 1. Viewing a Container Platform as a Multi-Layered System

Containers help package an application along with the components required to run in a consistent environment. However, when bringing an application to the cloud, simply running a container is only the starting point. The platform must also decide which machine the container runs on, who monitors its lifecycle, how workloads discover one another, how data persists across restarts, and how the system recovers when a node or availability zone experiences an outage.

A container platform typically has multiple layers of responsibility:

- **Cluster:** an administration and workload scheduling domain that provides APIs and shared resources.
- **Control plane:** manages the desired state, stores configuration, and makes scheduling decisions.
- **Node:** a machine participating in the cluster that provides CPU, RAM, storage, and networking to run workloads.
- **Workload:** an application unit declared for the platform to create, replace, and maintain, such as a Deployment, StatefulSet, Job, or DaemonSet in Kubernetes.
- **Container / Pod:** the execution environment; in Kubernetes, a Pod is the smallest unit placed onto a node by the scheduler.
- **Service:** an abstraction that provides a stable access address for a group of backends or exposes an application outside the cluster.

These components are related, but they are not synonymous. **A cluster is not one large server; a node is not an application; a Pod is not a Service; and a Service is not a process running containers.** Assigning roles properly helps architects choose compute, networking, storage, scaling, and deployment models on the cloud with clear responsibilities.

In the **CLOUD_ARCHITECTURE** module, the goal is to design cloud applications from business requirements down to networking, compute, data, and deployment models. When choosing a container platform, you need to balance **reliability, security, scalability, cost, and operability**, while evaluating trade-offs through a Well-Architected mindset.

After this lesson, you will be able to:

- Describe the roles and boundaries between a cluster, control plane, node, workload, Pod, container, and Service.
- Trace the path from workload declaration to the point where a container is scheduled and receives traffic.
- Understand the scheduler, kubelet, container runtime, service discovery, storage, and networking at an architectural level.
- Choose the appropriate workload type for stateless, stateful, batch, or node-wide tasks.
- Design security boundaries, quotas, autoscaling, health checks, deployments, and recovery.
- Determine how to observe and validate the platform under high load or node failures.

## 2. Component and Responsibility Map

~~~mermaid
flowchart TB
    User["User / calling system"] --> Entry["Ingress / Gateway / Load Balancer"]
    Entry --> Svc["Service: stable address"]
    Svc --> Pods["Workload Pods"]
    subgraph Cluster["Container cluster"]
        subgraph CP["Control plane"]
            API["API server"]
            Sched["Scheduler"]
            CM["Controllers"]
            Store[("State store")]
        end
        subgraph Nodes["Worker nodes"]
            N1["Node A: kubelet + runtime"]
            N2["Node B: kubelet + runtime"]
            N1 --> P1["Pod A"]
            N2 --> P2["Pod B"]
        end
        API <--> Store
        Sched --> API
        CM --> API
        API --> N1
        API --> N2
    end
    Pods --> P1
    Pods --> P2
~~~

The diagram is a conceptual model based on Kubernetes. Managed container platforms may hide or replace some control plane, state store, and node management components. Logical boundaries remain useful for knowing who is responsible during deployment, scheduling, networking provisioning, or incident troubleshooting.

| Component | Primary Responsibility | Architectural Question |
| --- | --- | --- |
| Cluster | Administration domain for workloads, configuration, and shared resources | Does one cluster serve a single environment or multiple application teams? |
| Control plane | Orchestrates state, APIs, scheduling, and controllers | Who operates, backs up, upgrades, and protects the control plane? |
| Node | Provides resources to execute workloads | Which node pool matches CPU, RAM, GPU, and reliability requirements? |
| Workload controller | Maintains Pod count and state according to declarations | Does the application need rollouts, scaling, state, or scheduled runs? |
| Pod | Scheduling unit consisting of one or more containers | Which containers need to share a network namespace, volumes, and lifecycle? |
| Container | Executes the application image or helper | Is the image secure, reproducible, and scanned? |
| Service | Provides a stable endpoint for selected backends | Who is allowed to call it, over which port, and how is traffic distributed? |
| Namespace | Resource grouping and policy scope | How should ownership, quotas, RBAC, and network policies be structured? |
| Persistent Volume | Provides durable storage for workloads | How is data persisted, backed up, restored, and migrated? |

## 3. Cluster: Governance and Scheduling Domain

A **cluster** is a collection of a control plane and nodes managed as a unified platform. With Kubernetes, the cluster provides an API to declare resources and maintain the desired state. Applications generally do not need to know which node a Pod resides on; they declare resources, policies, and scheduling requirements, and the platform handles placement.

### 3.1. What Is the Cluster Responsible For?

- **API and state:** Deployments, Services, ConfigMaps, Secrets, policies, and status.
- **Scheduling:** where workloads can be placed based on resources and node conditions.
- **Networking:** Pod addressing, service discovery, network policies, and external connectivity.
- **Identity and policy:** user identities, service accounts, RBAC, admission policies, and permissions.
- **Capacity and isolation:** CPU/RAM, quotas, node pools, limits, and sharing levels.
- **Operations:** upgrades, backups of necessary data, monitoring, and incident response.

A cluster is not an absolute security boundary. Namespaces, RBAC, and NetworkPolicy help divide permissions, but they do not replace the isolation of cloud accounts/projects, VPCs/VNets, nodes, workload identity, and runtime security.

### 3.2. Single Cluster or Multiple Clusters?

Deciding the number of clusters requires evaluating environments, reliability levels, compliance requirements, deployment regions, blast radius, administrative permissions, and operational capacity.

| Model | Benefits | Costs / Risks |
| --- | --- | --- |
| Single shared cluster | High compute utilization, shared platform tooling, lower control plane overhead | Resource contention, cross-impact, complex policies, large blast radius |
| Dedicated cluster per environment | Separates dev/staging/prod, independent permissions and changes | Multiple clusters to upgrade, observe, configure, and size for capacity |
| Dedicated cluster per trust domain | Reduces blast radius, customizes policies and maintenance schedules | Higher resource overhead, increased governance and connectivity complexity |
| Multiple clusters across regions | Meets geography, latency, and DR requirements | Config synchronization, failover, data replication, DNS, and drills |

**A cluster is a useful governance boundary, not the default unit of subdivision for every microservice.** A small application does not need its own cluster just because it is a separate service; workloads with distinct compliance requirements or criticality levels may need stronger boundaries than namespaces.

### 3.3. Namespaces and Shared Boundaries

In Kubernetes, namespaces group named resources such as Deployments, Pods, Services, Secrets, and quotas:

~~~text
cluster-prod
  namespace: commerce
    deployment: checkout
    service: checkout
    deployment: catalog
  namespace: platform
    deployment: metrics-agent
  namespace: batch
    job: nightly-reconciliation
~~~

Namespaces support scoped RBAC, ResourceQuota, LimitRange, and certain policies. However, they do not create a separate kernel for each group, do not automatically isolate network traffic, and do not guarantee that workloads in other namespaces cannot access Secrets. They must be combined with RBAC, Pod Security controls, NetworkPolicy, admission policies, node isolation when needed, cloud IAM, and encryption.

## 4. Control Plane: The Orchestration Brain

In Kubernetes, the control plane provides the API and components that govern the cluster. On managed platforms, the provider typically operates most or all of the control plane; customers still manage many aspects of nodes, workloads, identity, networking, storage, and configuration.

| Component | Role | What to Understand |
| --- | --- | --- |
| kube-apiserver | API gateway; authentication, authorization, and request handling | Admin tools and controllers interact through the API |
| etcd | Key-value store holding state in self-managed deployments | Availability, backup, encryption, and restore are critical |
| kube-scheduler | Selects nodes for unassigned Pods | Evaluates resource requests, constraints, affinity, and taints/tolerations |
| kube-controller-manager | Runs controllers that reconcile actual state to desired state | Controllers continuously observe and adjust |
| cloud-controller-manager | Integrates certain functions with the cloud provider | May manage nodes, routes, and load balancers depending on the provider |

Managed Kubernetes may hide etcd and controllers inside the service; some responsibilities are handled by the provider. When drawing diagrams, it is still good practice to depict the control plane as the orchestration layer to distinguish it from workload execution capacity on nodes.

### 4.1. When a Declaration Is Applied

Suppose a team declares a Deployment with three replicas:

1. CI/CD sends the manifest to the API server.
2. The API server performs authentication, authorization, admission control, and object validation.
3. The desired state is written to the state store.
4. The Deployment controller creates or updates a ReplicaSet.
5. The ReplicaSet controller creates Pods until the desired count is reached.
6. The scheduler finds suitable nodes and assigns the Pods.
7. The kubelet receives the Pod specification, instructs the runtime to pull the image, and runs the containers.
8. Probes, container statuses, endpoints, and controllers update based on the actual state.

~~~mermaid
sequenceDiagram
    participant Dev as CI/CD
    participant API as API server
    participant State as State store
    participant Ctrl as Controllers
    participant Sch as Scheduler
    participant K as Kubelet
    participant CR as Container runtime
    Dev->>API: Apply Deployment replicas=3
    API->>State: Validate and store desired state
    Ctrl->>API: Create ReplicaSet and Pods
    Sch->>API: Select node for Pod
    K->>API: Watch assigned Pods
    K->>CR: Create sandbox and run container
    CR-->>K: Container status
    K-->>API: Update Pod status
~~~

Controllers operate via an observe-and-adjust loop (*reconciliation loop*). Therefore, applying a declaration successfully does not mean the application is ready; you must observe Pending, ContainerCreating, Running, Ready states, and related events.

### 4.2. Does the Control Plane Manage Traffic?

The control plane orchestrates objects and state, while application traffic generally flows through the data plane: the Pod network, Service dataplane, ingress/gateway, load balancer, or proxies. Losing access to the API server can impact new changes and orchestration, but running workloads can continue serving depending on the design. You should not assume that losing API server connectivity immediately stops all containers.

## 5. Node: Where Workloads Actually Run

A **node** is a machine participating in the cluster. In the cloud, nodes are typically VMs or bare-metal servers provisioned by the provider; some platforms use serverless/container instances to abstract away node management. A node has hardware characteristics: CPU architecture, RAM, disk, GPU, network bandwidth, and local ephemeral storage.

| Node Component | Responsibility |
| --- | --- |
| kubelet | Agent that receives Pod specifications, coordinates with the runtime, and reports status |
| Container runtime | Pulls images, creates containers, and manages lifecycle; for example, containerd |
| CNI plugin | Provisions and manages networking for Pods |
| kube-proxy or equivalent dataplane | Supports Service networking; some CNIs replace this role |
| CSI node plugin | Attaches, detaches, and mounts volumes for Pods |
| Node OS / kernel | Provides process isolation, network stack, and filesystem |

The dataplane may use eBPF instead of kube-proxy; CSI/CNI plugins are installed as add-ons or managed services. You should not assume every cluster runs the exact same list of daemons.

### 5.1. Node Pool Classification

A node pool is a group of nodes with similar configuration and scaling policies:

| Node Pool | Suitable Workloads | Risks to Control |
| --- | --- | --- |
| General purpose | APIs, lightweight workers, stateless services | Shared resources, noisy neighbor |
| Memory optimized | Caches, data analytics, memory-intensive applications | RAM cost, eviction limits |
| Compute optimized | CPU-heavy processing, encoding, rendering | CPU saturation and execution time |
| GPU / accelerator | ML inference, image processing, specialized compute | Cost, quotas, plugins, and GPU scheduling |
| System / platform | DNS, metrics, ingress, cluster add-ons | Insufficient system capacity degrades multiple functions |
| Spot / preemptible | Retryable batch jobs and interruption-tolerant workloads | Nodes may be reclaimed; not the default for critical tasks |

Node pools do not replace resource requests/limits, affinity, topology spread, and taints/tolerations. They group capacity; the scheduler still needs matching workload requirements to place Pods on the right nodes.

### 5.2. A Node Is Not a Single Failure Domain

Multiple nodes may reside in the same Availability Zone, depend on a single storage backend, or share a network path. If high availability is required, you must consider distributing nodes across zones, replica counts, topology spread, PodDisruptionBudgets, spare capacity, and application fault tolerance.

## 6. Containers, Pods, and Workloads

### 6.1. Container as the Unit of Execution

A container image is an immutable package describing the filesystem and metadata needed to run an application. Common containers on Linux share the host kernel, using namespaces/cgroups or equivalent mechanisms to isolate processes, networking, and resources. A container is not a full VM with its own kernel in all cases.

Images should be built through a controlled pipeline, scanned for vulnerabilities, pinned by digest when needed, run as a non-root user with restricted capabilities, and avoid embedded secrets. Data that must persist should not be stored solely in the container's writable layer.

### 6.2. Pod as the Unit of Scheduling

A Pod contains one or more containers designed to coexist and work closely together. Containers inside a Pod share a network namespace (same IP and port space) and can share volumes. The scheduler places **Pods**, not individual containers within a Pod onto different nodes.

Containers should be placed in the same Pod when they require nearly identical lifecycles and locality, such as a sidecar proxy, a log/metrics helper, or an init container preparing resources before the main container starts. Do not bundle multiple independent applications into a single Pod just to reduce object count, as they will scale, roll out, and fail together.

~~~mermaid
flowchart TB
    subgraph Pod["One Pod: one network namespace"]
        App["Application container"]
        Sidecar["Sidecar proxy"]
        Shared[("Shared volume if needed")]
        App --- Shared
        Sidecar --- Shared
        App <-->|"localhost"| Sidecar
    end
~~~

### 6.3. Choosing a Workload Controller by Lifecycle

| Workload | Purpose | Typical Use Cases |
| --- | --- | --- |
| Deployment | Maintains stateless Pod replicas, rollout/rollback | REST APIs, frontends, stateless workers |
| StatefulSet | Pods with stable identity and typically attached persistent storage | Stateful applications, databases/operator-managed services |
| DaemonSet | Ensures a Pod runs on every matching node | Log agents, network/security agents, node monitoring |
| Job | Runs a task until completion | Batch imports, one-time migrations, reports |
| CronJob | Creates Jobs on a schedule | Report aggregation, cleanup, periodic reconciliation |
| ReplicaSet | Maintains Pod replica count; usually managed by Deployment | Typically does not need to be created directly |

A StatefulSet does not automatically give a stateful application high availability, backups, or consistency. A database in a StatefulSet still requires replication, quorum, appropriate storage, backup/restore, and an upgrade plan.

## 7. Service: A Stable Address for Changing Backends

Pods have a dynamic lifecycle: they are created, deleted, rescheduled, scaled, and assigned different IPs. A **Service** provides a stable abstraction so clients can access a group of matching backends without tracking individual Pod IPs.

| Service Type | Access Mechanism | When to Use |
| --- | --- | --- |
| ClusterIP | Internal cluster virtual IP address | Service-to-service communication |
| NodePort | Opens a port on node addresses | Certain environments/labs or as part of a load balancer path |
| LoadBalancer | Requests cloud provider load balancer integration | Exposing services via a public or private load balancer |
| ExternalName | DNS CNAME to an external hostname | Name mapping; does not create a proxy data path |

Ingress/gateways provide L7 routing such as host/path/TLS depending on the implementation. **A Service does not inherently provide WAF, authentication, or API authorization** unless additional components are present.

### 7.1. Service Discovery Inside the Cluster

Clients typically call the DNS name of a Service, such as `catalog.commerce.svc.cluster.local` under default cluster DNS conventions. DNS service discovery returns the name/ClusterIP; the dataplane forwards traffic to eligible backend endpoints.

~~~mermaid
flowchart LR
    Client["Pod checkout"] --> DNS["Cluster DNS"]
    DNS -->|"catalog.commerce.svc"| VIP["Service ClusterIP"]
    VIP --> DP["Service dataplane"]
    DP --> P1["Catalog Pod 1"]
    DP --> P2["Catalog Pod 2"]
    DP --> P3["Catalog Pod 3"]
~~~

When a Pod is not yet Ready, its endpoint may be excluded from the serving pool depending on configuration. If a Service has no endpoints, check the selector, labels, readiness, and EndpointSlice.

## 8. Scheduling and Resource Management

The scheduler selects nodes based on multiple criteria. Applications must declare resources rather than letting workloads run unbounded and contend for resources.

### 8.1. Requests and Limits

- **CPU request:** the amount of CPU the scheduler uses when evaluating Pod placement and typically serves as a relative baseline guarantee for scheduling.
- **CPU limit:** the cap on CPU time a container is allowed to consume; exceeding it can result in throttling.
- **Memory request:** used for scheduling and evaluating allocation capacity.
- **Memory limit:** exceeding this threshold can cause the process/container to be OOM killed.

Requests are not actual usage, and limits are not free spare capacity. Setting them too low causes throttling, OOM kills, or node pressure; setting them too high prevents the scheduler from utilizing capacity efficiently and increases costs.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: commerce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      containers:
        - name: app
          image: registry.example.com/checkout:1.4.2
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

The values above are illustrative; you must measure heap, working set, CPU profile, peak load, and startup time. Probes must accurately reflect application state; do not call slow dependencies on every liveness check and trigger cascading restarts.

### 8.2. What Conditions Does the Scheduler Evaluate?

- Resource requests against available capacity.
- Node selectors and node affinity/anti-affinity.
- Taints on nodes and tolerations on Pods.
- Topology spread constraints to distribute replicas across zones/nodes or failure domains.
- Volume topology, GPUs, or specialized devices.
- Other policies and scoring rules depending on version/cluster.

The scheduler does not inherently understand business semantics such as "two replicas of the same tenant must not be in the same zone." Architects must express these constraints as labels, affinity rules, or topology constraints.

### 8.3. Spreading Replicas Across Zones

A Deployment with three replicas needs to avoid concentrating all three in the same zone. You can use topology spread constraints with the zone label provided by the node/provider. Parameters such as `maxSkew` and `whenUnsatisfiable` must be chosen alongside actual capacity; overly strict configurations can leave Pods Pending when a zone lacks nodes.

## 9. Health Checks and Workload Lifecycle

The platform needs to know when a container has finished starting, when it can receive traffic, and when it needs to be restarted. Kubernetes provides three types of probes:

| Probe | Question | On Failure |
| --- | --- | --- |
| **Startup probe** | Has the application finished starting up? | Kubelet keeps retrying within the configured threshold; exceeding it restarts the container |
| **Readiness probe** | Can the Pod receive traffic right now? | Pod is marked unready and typically removed from serving endpoints |
| **Liveness probe** | Is the process still in a healthy state to keep running? | Kubelet restarts the container according to its policy |

Readiness and liveness are not interchangeable. An application may be unready due to cache warming or a temporarily unavailable dependency, while the process is still healthy and does not need a restart. If a process deadlocks, liveness can help detect and recover it.

### 9.1. Avoiding Cascading Health Check Failures

- Readiness endpoints should measure request-handling readiness by application criteria, avoiding synchronous calls to all dependencies every few seconds.
- Liveness should not depend on databases, queues, or external services if a dependency outage could cause all replicas to restart themselves.
- For slow-starting applications, use a startup probe to protect the initialization phase.
- Choose initial delay, period, timeout, and failure threshold based on startup metrics and recovery characteristics.
- Monitor restart counts, probe failures, and time from start to Ready.

### 9.2. Rolling Updates and Rollbacks

Deployments allow version changes through rollout strategies. Two important parameters are:

- **maxSurge:** maximum number of extra Pods allowed during an update relative to the desired replica count.
- **maxUnavailable:** maximum number of Pods that can be unavailable during the rollout.

These values must match capacity, startup time, and version compatibility. If a new version requires a different database schema, rolling back the binary does not automatically roll back the migration. Migrations should be designed using an expand-and-contract pattern so old and new versions can coexist during the transition period.

## 10. Storage: Where Does Workload Data Live?

Containers have short lifecycles. If critical data is only written to a container's writable layer, it can be lost when the Pod is deleted or recreated. You must distinguish between:

- **Ephemeral storage:** temporary data on the node/container, suitable for transient caches, scratch space, and regenerable intermediate files.
- **Persistent Volume (PV):** durable storage resource provisioned for workloads.
- **Persistent Volume Claim (PVC):** a workload's request for storage capacity and access mode.
- **StorageClass:** describes the storage tier and how volumes are provisioned via drivers/policies.
- **CSI (Container Storage Interface):** the interface for integrating storage systems into the cluster.

~~~mermaid
flowchart TB
    Pod["Pod / Stateful workload"] --> PVC["PersistentVolumeClaim"]
    PVC --> SC["StorageClass"]
    SC --> CSI["CSI provisioner / driver"]
    CSI --> PV["Persistent Volume"]
    PV --> Backend["Managed disk / file / block storage"]
~~~

A successfully bound PVC does not mean data is backed up or recoverable within RPO. You must verify performance class, IOPS/throughput, latency, encryption, snapshots, retention, zone affinity, access modes, and restore tests.

### 10.1. Access Modes and Topology

Some storage providers offer block volumes that can only be attached to one node at a time; some file storage systems support concurrent sharing. The semantics of ReadWriteOnce, ReadOnlyMany, ReadWriteMany, or ReadWriteOncePod depend on driver capabilities and platform behavior. **Do not assume multiple Pods can safely read/write concurrently just by declaring a PVC.**

Volumes can be bound to a specific zone. If a StatefulSet Pod is rescheduled to a node in another zone, attaching the volume may fail or require replication mechanisms. Storage design must be evaluated alongside node topology and DR.

### 10.2. Stateless and Stateful

| Characteristic | Stateless Workload | Stateful Workload |
| --- | --- | --- |
| State | Stored outside the container or can be regenerated | Preserves data/identity across restarts |
| Scaling | Typically scales replicas independently | Depends on replication, partitioning, quorum, and access patterns |
| Common controller | Deployment | StatefulSet or specialized operator |
| Storage | Usually does not require persistent volumes on the Pod | PVC or external data services |
| Recovery | Creates a new Pod from image/config | Must restore consistent data and state |

A StatefulSet does not automatically turn a database into an HA service. Containerized databases still require replication, backups, restores, failover, encryption, and data administration. Using a managed database outside the cluster decouples compute lifecycle from data, at the trade-off of accounting for latency, networking, cost, and dependencies.

## 11. Networking: From Pods to Services

When selecting a container platform, you need to define three communication layers:

1. **Pod-to-Pod:** workloads exchanging data between Pods on the same node or across different nodes.
2. **Pod-to-Service:** clients calling a stable address while the dataplane distributes traffic to endpoints.
3. **North-South traffic:** users or external systems accessing the cluster through load balancers, ingress, or gateways.

### 11.1. CNI and Pod Networking Models

Container Network Interface (CNI) is the interface/plugin responsible for configuring network connectivity for workloads. CNI plugins can assign Pod IPs, create interfaces/routes, enforce policies, or integrate with cloud SDN.

Some platforms assign Pod IPs from the VPC/VNet CIDR; others use an overlay network and encapsulation:

| Model | Advantages | Points to Verify |
| --- | --- | --- |
| Pod IP from cloud network | Direct VPC/VNet routing and policy integration in some models | Subnet IP count, interface/secondary IP limits, node scaling |
| Overlay network | Decouples Pod CIDR from physical subnet addresses, flexible in certain topologies | Encapsulation, MTU, routing, observability, and performance |

Do not assume all Pod IPs are directly reachable from on-premises or the Internet. You must verify routes, network policies, firewalls, NAT, security groups, and load balancers.

### 11.2. Service, EndpointSlice, and Load Balancing

A Service uses a selector to match Pods by label, or can use manual endpoints in certain scenarios. Kubernetes maintains EndpointSlices reflecting backends and readiness conditions. A dataplane such as kube-proxy or an eBPF-based implementation forwards traffic accordingly.

If a Service is not receiving traffic, check:

1. Does the Service selector match the Pod labels?
2. Is the Pod Ready, or is the readiness probe failing?
3. Does the EndpointSlice contain backend addresses?
4. Are targetPort, port, and protocol configured correctly?
5. Are NetworkPolicy, security groups, CNI, or the dataplane blocking traffic?
6. Is the application listening on the right interface and port?

### 11.3. North-South Traffic

- **LoadBalancer Service:** provisions a load balancer via cloud integration, which can be public or internal depending on the provider.
- **Ingress controller:** provides HTTP(S) routing by host/path and TLS depending on the implementation.
- **Gateway API / API gateway:** provides richer routing and policies depending on the deployed controller/gateway.
- **Service mesh:** can manage east-west traffic, service identity, mTLS, and telemetry, but adds control plane/data plane complexity and operational overhead.

Not every cluster comes with an Ingress controller installed by default; creating an Ingress resource does not enable routing capabilities without a corresponding controller.

## 12. Workload Security and Tenant Boundaries

Container platforms run multiple applications on shared compute, so security must be addressed across images, identity, control plane, nodes, networking, and data.

### 12.1. Protecting Images and the Supply Chain

- Use only managed registries; restrict who can push/pull images.
- Scan for vulnerabilities and malware in CI/CD pipelines; define policies for handling critical findings.
- Pin image digests for production when immutability is required; do not rely solely on mutable tags like `latest`.
- Build minimal images, removing compilers and packages unnecessary at runtime.
- Sign images/attestations and verify provenance when risk levels require it.
- Never bake credentials, tokens, or secret files into image layers.

### 12.2. Identity and Permissions

- Distinguish between cluster operator permissions (human identity/RBAC) and workload permissions to call cloud APIs (workload identity).
- Each workload should have only the permissions it needs; avoid attaching a broad cloud role shared by all Pods on a node.
- Use provider-integrated identities or workload identity federation where appropriate to avoid long-lived access keys.
- Manage Secrets with encryption at rest, rotation, and auditing. Kubernetes Secrets do not automatically mean data is encrypted at every layer.
- Protect kubeconfig files, API endpoints, and CI/CD credentials; control permissions to create privileged Pods or access host namespaces.

### 12.3. Container Security Context

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-example
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/app@sha256:REPLACE_WITH_DIGEST
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
~~~

This manifest illustrates the principles; the UID must match the image, the application may need dedicated writable directories mounted, and cluster policies must allow the configuration. Avoid privileged mode or broad `hostPath` mounts unless there is an approved requirement.

### 12.4. Network Policies and Segmentation

Some CNIs allow unrestricted Pod communication in the absence of NetworkPolicies. A baseline should define ingress/egress per workload—only allowing checkout to call catalog/payment adapters on required ports, and restricting egress to the Internet or metadata endpoints. You must verify that the plugin actually enforces policies; simply creating a NetworkPolicy object does not guarantee enforcement on every platform if the CNI does not support it.

### 12.5. Isolation Between Tenants

Namespaces are an organizational tool, not a strong sandbox for untrusted workloads. For tenants with differing trust levels, consider dedicated node pools, taints/tolerations, strict admission policies, runtime sandboxes, or separate clusters. Evaluate the blast radius if a tenant exhausts resources, exploits a kernel vulnerability, or accesses shared credentials.

## 13. Scaling and Capacity Balancing

### 13.1. Horizontal Pod Autoscaler

HPA adjusts workload replica counts based on metrics such as CPU, memory, or custom/external metrics. When scaling on CPU utilization, requests are essential for calculating utilization ratios; missing requests leave scaling behavior without a proper baseline.

HPA only adds Pods, so **node capacity** must be able to accommodate them. If resources run out, Pods will stay Pending; a cluster autoscaler or node autoscaling can add nodes if configured and if cloud quotas/capacity permit.

### 13.2. Three Different Scaling Layers

| Layer | What Changes? | Component / Mechanism |
| --- | --- | --- |
| Application replica | Number of workload Pods | HPA or KEDA/custom controller |
| Node capacity | Number or size of nodes | Cluster autoscaler / node pool autoscaling |
| Service/platform capacity | Throughput of databases, queues, load balancers, DNS, control plane | Managed service scaling, partitioning, or upgrading limits |

Scaling HPA from 3 to 30 Pods does not mean the system can handle 10x the load. Database connection pools, payment API rate limits, queue throughput, and network limits can become bottlenecks before compute does.

### 13.3. Scale to Zero and Interruptible Workloads

Scaling to zero can save costs for workloads that do not require immediate responses, but increases cold start and latency. Spot/preemptible nodes can lower costs for batch jobs, provided the application handles eviction, checkpointing, or retries. Payment processing or critical data writes should not run on preemptible resources without strong guarantees and recovery mechanisms.

## 14. Deployment, Updates, and Configuration Management

### 14.1. Separating Images and Configuration

Images should contain the packaged program and dependencies; environment-specific configuration should be passed via ConfigMaps, Secrets, or appropriate mechanisms. Do not build separate images for dev, staging, and production solely because database endpoints differ.

Do not put secrets in plain ConfigMaps or environment variables that might be accidentally logged. For sensitive data, use protected Secrets or an external secret manager with rotation and clear access controls.

### 14.2. Declarative Deployment and GitOps

Manifests declare the desired state, get reviewed, and are applied via pipelines or GitOps controllers. This enables diff reviews, auditing, and reproducible environments. However, direct cluster modification permissions must be restricted; if operators make manual changes, configuration can drift from Git and be overwritten by controllers.

### 14.3. Deployment Strategies

| Strategy | How It Works | When Suitable |
| --- | --- | --- |
| Rolling update | Replaces replicas incrementally within surge/unavailable limits | Simultaneously compatible versions, frequent deployments |
| Blue/Green | Maintains two environments/version groups, switches traffic when ready | Needs fast traffic cutover and capacity for two versions |
| Canary | Routes a portion of traffic to the new version and increases gradually based on results | Reliable metrics, routing, and rollback are in place |
| Recreate | Stops the old version before starting the new version | Application cannot run side-by-side or has data constraints |

Rollbacks must account for database migrations, message schemas, external API side effects, and written data—not just reverting an image tag.

## 15. Operations, Observability, and Recovery

### 15.1. Layers to Observe

| Layer | Key Metrics and Events |
| --- | --- |
| Control plane | API availability/latency, admission errors, scheduler backlog, controller errors |
| Node | CPU/memory/disk pressure, inodes, network errors, kubelet/runtime health |
| Pod/container | Pending state, restart count, OOMKilled, probe failures, image pull errors |
| Workload | Desired/available replicas, rollout duration, queue depth, request rate, and error rate |
| Service/network | EndpointSlice, DNS failures, connection resets, latency, dropped packets |
| Storage | Volume attach/mount errors, latency, IOPS, capacity, backup/restore status |
| Security | Image findings, policy violations, RBAC changes, privileged workloads, secret access |

Metrics reveal trends, logs show events, and traces connect requests across services. Apply labels and retain logs at a level sufficient for investigation without creating excessive cardinality or storing unnecessary sensitive data.

### 15.2. Runbooks for Common Scenarios

| Symptom | Check First | Investigation Path |
| --- | --- | --- |
| Pod Pending | Events, requests, node capacity, taints, PVC | Scheduler constraints, quotas, insufficient nodes, or storage topology |
| ImagePullBackOff | Image name/tag/digest, registry access | Pull secrets, IAM, networking, rate limits, and registry availability |
| CrashLoopBackOff | Container logs, exit code, probes | Config/secrets, startup, dependencies, permissions, memory |
| OOMKilled | Memory usage, limit, node pressure | Heap leak, requests/limits, batch size, memory profile |
| Service has no backends | Selector, labels, EndpointSlice, readiness | Port mismatch, CNI, policies, application not listening |
| Rollout stuck | Replica availability, events, quotas | Probes, image pull, PodDisruptionBudget, capacity, or migrations |
| PVC Pending / attach failure | PVC, PV, StorageClass, CSI events | Quotas, access mode, zone mismatch, driver, cloud volume API |
| Node NotReady | Node conditions, kubelet, runtime, network | Disk pressure, certificates, control plane connectivity, host failure |

Do not treat every incident simply by deleting the Pod. Controllers may recreate the Pod and repeat the exact same error while wiping diagnostic evidence. Gather events/logs and check root causes before taking mutating actions.

### 15.3. Cluster and Node Upgrades

Upgrading the control plane, node OS, kubelet, runtime, CNI/CSI, and add-ons requires a compatibility matrix. Execute during change windows, check API deprecations, drain nodes properly, ensure sufficient capacity for displaced workloads, and have a recovery plan. Managed services reduce control plane operational overhead, but do not automatically resolve application or add-on compatibility issues.

## 16. Well-Architected and Container Trade-Offs

| Perspective | Decisions to Consider | Benefits / Trade-Offs |
| --- | --- | --- |
| **Operational Excellence** | Managed cluster vs. self-managed; GitOps; standardized node pools and telemetry | Managed reduces control plane burden, but workloads, nodes, policies, and add-ons still require management |
| **Security** | Cluster isolation, RBAC, workload identity, image signing, network policies | Stricter isolation reduces blast radius but adds process, policy, and cost overhead |
| **Reliability** | Replicas, zone spread, PDBs, storage, probes, and DR | More replicas require capacity, stateless design, and fault-tolerant backends |
| **Performance Efficiency** | Requests/limits, node families, CNI, sidecars, autoscaling | Resource optimization reduces cost, but misconfiguration causes throttling and latency |
| **Cost Optimization** | Bin packing, spot nodes, scale-to-zero, right-sizing | Saves compute cost, but increases interruption risk or cold start latency |
| **Sustainability** | Reducing idle resources, right-sized images and node pools | Less waste, while still maintaining headroom and redundancy |

### 16.1. Mindset for Choosing Managed vs. Self-Managed

Managed Kubernetes is suitable when an organization wants to use Kubernetes APIs and its ecosystem without operating the entire control plane. However, the team must still understand node pools, version skew, workload security, CNI/CSI, quotas, networking, backups, and DR. Serverless container platforms can hide node management as well, but limits on runtime, networking, storage, startup, or workload duration must be evaluated.

Self-managed clusters may be necessary when specific controls or custom environments are required, but they demand the capability to maintain the control plane, state store, certificates, upgrades, backups, patching, and on-call support. Choose the model based on total cost of ownership and required level of control, not compute pricing alone.

### 16.2. Metrics for Decision-Making

- **Utilization and saturation:** CPU/memory requests vs. usage, node pressure, throttling, OOMs, and queuing.
- **Availability:** Pod Ready ratio, request success rate, recovery time upon node/zone loss.
- **Delivery:** rollout duration, rollout failure rate, rollback time, and deployment frequency.
- **Performance:** p95/p99 latency, throughput, network drops, storage latency.
- **Cost:** cost per successful request/transaction, utilization per node pool, idle capacity cost, and logging cost.
- **Security:** scanned image ratio, critical vulnerabilities, privileged workloads, policy violations.

Thresholds should be tied to SLOs and business user journeys. Do not optimize CPU utilization so aggressively that there is no headroom left for bursts or node failures.

## 17. Lab: Designing a Container Platform for an Order Application

An enterprise is deploying an ordering application on the cloud. The system consists of checkout and catalog APIs, an order processing worker, a nightly reconciliation batch job, and a node metrics collection agent. Managed PostgreSQL runs outside the cluster; invoice files are stored in object storage. The team has three environments—dev, staging, and production—and needs to maintain availability when a node fails.

**Assignment Requirements:**

1. Draw a diagram of cluster/control plane/node/workload/Pod/Service, indicating which components are operated by the managed provider.
2. Choose controllers for the stateless APIs, worker, batch job, and node agent; explain when to use Deployment, Job/CronJob, and DaemonSet.
3. Propose namespaces, RBAC, ResourceQuotas, node pools, and network policies for the workload groups.
4. Write a Deployment manifest for checkout including resource requests/limits, readiness/liveness or startup probes, replicas, and a Service.
5. Propose appropriate topology spread/PDBs; explain how the system continues operating when a node is drained or a zone is lost.
6. Specify traffic paths from the Internet to the API, internal traffic between checkout and catalog, and connections to PostgreSQL and object storage.
7. Propose autoscaling for Pods and nodes; identify potential bottlenecks in the database, queue, or provider APIs.
8. Write short runbooks for Pod Pending, CrashLoopBackOff, and Service with no endpoints.
9. Provide three metrics covering reliability, performance, and cost, along with post-deployment verification steps.

### Evaluation Hints

A strong solution must distinguish between **administration units** and **application execution units**, select the right controller for each workload lifecycle, avoid storing critical state in ephemeral containers, provide stable endpoints, and enforce resource controls. It must also identify the limitations of namespaces, the practical role of probes, network/storage requirements, and operational responsibilities on the cloud.

A starting option might use a managed cluster for production, separate node pools for system and application workloads, Deployments for stateless APIs/workers, CronJob for batch processing, and DaemonSet for agents. This is only a candidate architecture; cluster count, zones, replicas, and policies must be validated against SLOs, cost, and operational capacity.

## 18. Checklist for Designing and Promoting Container Workloads to Production

- [ ] Cluster boundaries, environments, owners, and provider/customer responsibilities are clearly defined.
- [ ] Control plane/API endpoints and administrative permissions are protected.
- [ ] Node pools reflect CPU, memory, GPU, network, storage, and failure domains of workloads.
- [ ] Proper workload controllers are selected; Pods only group containers with matching lifecycles and locality.
- [ ] Resource requests/limits are measured and validated under load.
- [ ] Readiness, liveness, and startup probes have distinct purposes and do not cause cascading restarts.
- [ ] Service selectors, ports, endpoints, and application exposure paths are verified.
- [ ] CNI, routing, DNS, network policies, and firewalls accommodate permitted traffic flows.
- [ ] Persistent data uses appropriate storage; backups, restores, retention, and RPO/RTO have been rehearsed.
- [ ] Images are managed, scanned, least-privilege, secret-free, and have an update process.
- [ ] RBAC, workload identity, Pod security, admission control, and tenant isolation are approved.
- [ ] HPA/node autoscaling has quotas, headroom, and a strategy for capacity exhaustion.
- [ ] Rollouts, rollbacks, database migrations, and message schema compatibility are accounted for.
- [ ] Logs, metrics, traces, alerts, and runbooks cover control plane, nodes, Pods, Services, and storage.
- [ ] Cluster/node/add-on upgrades have a plan, testing, and rollback criteria.
- [ ] Costs for control plane, nodes, storage, networking, observability, and staffing are included in total cost of ownership.

**Key takeaway:** A cluster defines the governance domain; the control plane orchestrates state; nodes provide compute; workloads declare lifecycle; Pods group tightly coupled containers; Services provide stable addresses for changing backends. When roles are clearly separated, teams can purposefully design compute, networking, storage, scaling, and security on the cloud while evaluating impacts on reliability, cost, and operations under Well-Architected principles.
