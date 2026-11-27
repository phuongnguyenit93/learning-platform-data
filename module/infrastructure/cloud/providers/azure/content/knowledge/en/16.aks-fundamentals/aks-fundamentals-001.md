# AKS Architecture and Cluster Model Selection

## 1. Architectural problem: when do you need Kubernetes on Azure?

An application on Microsoft Azure can start on a single virtual machine, then move to containers for runtime packaging and consistent deployment. As the system grows into multiple APIs, workers, background jobs, and data components, the operations team must solve problems such as deploying dozens of containers, routing traffic, monitoring health, scaling with load, performing rolling updates, and securing service-to-service connections.

**Azure Kubernetes Service (AKS)** is a managed Kubernetes service on Azure. AKS simplifies deploying and operating Kubernetes by letting Azure manage most of the **control plane** infrastructure, while your team focuses on designing the cluster, node pools, networking, access permissions, applications, and system lifecycle.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter of the Microsoft Azure ecosystem module. AKS connects knowledge of subscriptions, resource groups, Microsoft Entra ID, virtual networks, VMs, registries, storage, data, monitoring, security, and cost control into a containerized application architecture.

**The core question is not "how do I create AKS as fast as possible?" but "do we really need AKS, and which cluster model should we choose to meet requirements while remaining operable?"**

For example: an enterprise has three Java APIs, an email-sending service, an image-processing worker, and an admin portal. It can deploy on AKS, but if the team is small and does not need advanced Kubernetes orchestration capabilities, Azure Container Apps or App Service is also worth considering. The right choice must consider features, team capability, cost, isolation level, and operational requirements.

## 2. Learning objectives

After this lesson, you can:

1. Describe AKS architecture including the **control plane**, **node pools**, **nodes**, **pods**, **services**, and system components.
2. Distinguish Azure's responsibilities from those of the AKS operator.
3. Compare **AKS Standard** and **AKS Automatic** experiences when those options are supported.
4. Decide between a dedicated or shared cluster, public or private cluster, and single-region or multi-region architecture.
5. Design system node pools, user node pools, VM sizes, Availability Zones, and Spot nodes when appropriate.
6. Plan VNet, subnets, Pod IP, Service CIDR, ingress, egress, and Network Policy.
7. Combine Microsoft Entra ID, Azure RBAC, Kubernetes RBAC, managed identity, workload identity, and ACR.
8. Understand Deployment, Service, probes, requests/limits, HPA, cluster autoscaler, KEDA, and persistent storage.
9. Plan Kubernetes upgrades, security, observability, backup/DR, and cost control.
10. Practice inspecting a cluster and deploying a test workload without exposing it to the Internet.

## 3. Big picture of AKS architecture

~~~mermaid
flowchart TB
    ADMIN[Administrator / CI-CD] --> API[Kubernetes API Server]
    subgraph CP[Azure-managed control plane]
        API --> SCHED[Scheduler]
        API --> CTRL[Controllers]
        API --> ETCD[(etcd - cluster state)]
    end
    subgraph NODES[Node pools in Azure]
        N1[Node 1 - kubelet / container runtime]
        N2[Node 2 - kubelet / container runtime]
        N3[Node 3 - kubelet / container runtime]
        N1 --> P1[API Pods]
        N2 --> P2[API Pods]
        N3 --> P3[Worker Pods]
    end
    API --> N1
    API --> N2
    API --> N3
    CLIENT[Users] --> ING[Ingress / Load Balancer]
    ING --> P1
    ING --> P2
    P1 --> DB[(Database)]
    P2 --> DB
    P3 --> STORE[(Queue / Blob Storage)]
    ID[Microsoft Entra ID / Workload Identity] --> P1
    REG[Azure Container Registry] --> NODES
~~~

This is a conceptual diagram. The API server access path, how ingress is deployed, and the image-pull mechanism depend on the actual configuration. The control plane does not run as a set of VMs that users can SSH into and modify arbitrarily.

Three layers to remember:

- **Control plane:** stores desired state, handles Kubernetes API requests, and orchestrates objects.
- **Worker nodes:** actual VMs providing CPU/RAM to run pods; typically organized into node pools.
- **Workloads:** Deployment, StatefulSet, DaemonSet, Job, CronJob, Service, and other application objects.

**Managed AKS does not mean every component is automatically operated for you by Azure.** Your team is still responsible for configuring permissions, networking, images, upgrades, quotas, container security, data backups, and application resiliency.

## 4. What does the control plane do?

The Kubernetes control plane consists of these core components:

| Component | Function | Design implication |
|---|---|---|
| **kube-apiserver** | Exposes the Kubernetes API to kubectl, controllers, and automation | Must protect the endpoint, permissions, and network path |
| **etcd** | Stores cluster configuration state | Do not use it as an application business database |
| **kube-scheduler** | Decides which suitable Node a Pod is placed on | Depends on resources, affinity, taints, and topology |
| **kube-controller-manager** | Runs controllers that maintain desired state | Enables Kubernetes to recreate pods and reconcile objects |
| **Cloud integration** | Connects Kubernetes with supported Azure resources | Load Balancer, disk, identity, and networking |

For example, if you declare **replicas: 3** for a Deployment, the controller tries to maintain three corresponding pods. When one pod dies, the system can create a replacement pod, but if the entire node pool has no space left, the pod will stay **Pending** until suitable capacity becomes available.

### 4.1. "Managed control plane" does not mean ignoring SLA

Azure manages the deployment and maintenance of the control plane according to the selected tier/service. However, users still need to:

- Choose an appropriate service tier/SLA if the application requires availability commitments.
- Secure Kubernetes API access.
- Plan version upgrades and compatibility.
- Monitor cluster status and control plane events.
- Design applications to keep serving while the Kubernetes API is temporarily unavailable, within the scope of currently running pods.

**Control plane availability is different from application availability.** The control plane can remain healthy while application pods are crash-looping or the database is failing.

## 5. Nodes, node pools, and underlying Azure resources

A **Node** is a machine running kubelet and a container runtime to execute pods. In AKS, nodes are typically Azure VMs managed through cluster infrastructure resources. A **node pool** is a group of nodes sharing key configurations such as VM SKU, OS, image, scaling, and scheduling attributes.

Inside a Kubernetes node:

- **kubelet** watches PodSpecs and coordinates with the runtime.
- **Container runtime** such as containerd launches containers from images.
- **CNI/networking components** configure network connectivity for pods.
- **CSI drivers** enable attaching volumes from storage services.
- **DaemonSets** can run one pod on each matching node to collect logs or run agents.

### 5.1. AKS involves two Azure resource groups you must distinguish

An AKS deployment typically involves:

1. **The resource group containing the AKS resource** that you create/select, for example **rg-aks-app**.
2. **The node resource group** created/managed by AKS, usually named with the pattern **MC_...**, containing underlying infrastructure resources such as VM Scale Sets, NICs, disks, and load balancers.

Do not manually modify AKS-managed resources in the node resource group while bypassing the Kubernetes/AKS API, except for operations explicitly supported by Microsoft. Manual changes may be overwritten by controllers or leave the cluster in a hard-to-maintain state.

### 5.2. Do not confuse node pool with namespace

- **Node pool:** groups **compute capacity** and machine characteristics.
- **Namespace:** groups **Kubernetes objects**, useful for organization and policies.
- **Resource group:** an Azure resource management boundary, not a Kubernetes namespace.

A namespace can have pods running across multiple node pools; a node pool can serve pods from multiple namespaces unless restricted by scheduling rules.

## 6. System node pool and user node pool

An AKS design typically separates **system node pools** and **user node pools**.

| Type | Purpose | Typical workloads |
|---|---|---|
| **System node pool** | Provides capacity for critical Kubernetes system components | DNS, networking/monitoring agents, and system pods |
| **User node pool** | Runs organization applications and jobs | Java APIs, background workers, batch jobs |

A production cluster should consider dedicating sufficient capacity and redundancy for system components, rather than letting them starve when application pods spike unexpectedly.

### 6.1. Sample design

~~~text
AKS cluster
├── systempool: multiple stable nodes, appropriate VM size
├── apipool: runs HTTP APIs, HPA and autoscale
└── workerpool: processes Queue/Batch, can use a different VM SKU
~~~

This is a logical model, not a mandatory requirement that every cluster must have three pools. For small systems, you can start simple and split pools when operational reasons arise.

### 6.2. Labels, taints, and tolerations

Kubernetes supports controlling where pods run:

- **Node labels:** describe node characteristics.
- **nodeSelector/affinity:** require or prefer pods to run on matching nodes.
- **Taints and tolerations:** restrict disallowed pods from being scheduled onto a node pool.
- **Topology spread constraints:** distribute replicas across zones/nodes as required.

For example, a GPU worker should not accidentally be scheduled onto a CPU-only node. A GPU user pool can be configured with a label/taint, and the AI application configured with a matching toleration and resource request.

**A taint is not an absolute security boundary.** It is a scheduling mechanism; when strong isolation is needed, combine it with permissions, admission policies, network isolation, and sometimes separate clusters.

## 7. AKS Standard and AKS Automatic: choosing the management level

Azure offers AKS deployment experiences such as **AKS Standard** and **AKS Automatic**, depending on time, region, and availability. Naming, defaults, and features can evolve; verify the actual supported capabilities in your subscription before finalizing an architecture.

### 7.1. AKS Standard

The Standard model focuses on letting the platform team actively make most configuration decisions:

- Choose networking, node pools, scaling, and VM SKUs.
- Configure controls for security, ingress, upgrades, and monitoring.
- Tune configurations to fit enterprise topologies.
- Take more responsibility for designing and operating cluster components.

Best suited when the team needs deep control over Kubernetes infrastructure, has complex networking requirements, or wants to enforce specific internal standards.

### 7.2. AKS Automatic

The Automatic experience aims to reduce cluster configuration/operational overhead by providing more default decisions and managed/automated capabilities.

Best suited when the team prioritizes deployment speed and accepts the choices/constraints supported by this experience. However, you remain responsible for applications, permissions, data, cost, and security policies.

### 7.3. Decision comparison

| Question | Leans toward Standard | Leans toward Automatic |
|---|---|---|
| Need deep control over node pools/networking? | Usually a better fit | Check customization limits |
| Want to reduce infrastructure choices to operate? | Requires extra configuration | Usually a better fit |
| Have a specialized enterprise topology? | Advantageous for granular config | Verify feature support first |
| Team is new to Kubernetes? | Requires more training and operations | Can reduce platform toil |
| Compliance requires custom configurations? | Often more flexible | Must verify whether requirements are met |

**Automatic and Standard do not mean a Kubernetes cluster with or without a control plane.** Both belong to AKS; they differ in automation level and configuration control for each experience. Likewise, the **control plane service tier/SLA** is a separate decision dimension and should not be conflated with the Automatic/Standard experience names.

## 8. Do you really need AKS?

Do not choose AKS solely because your application is containerized.

| Platform | Best suited when | Considerations |
|---|---|---|
| **Azure App Service** | Web/API with simple deployment flows and supported runtimes | Limited Kubernetes control |
| **Azure Container Apps** | Microservices, jobs, containers needing autoscale with minimal cluster ops | Platform limits and model differ from AKS |
| **AKS** | Multiple Kubernetes apps needing CRDs/operators, policies, node pools, topology, and specific K8s workflows | Requires operational expertise and platform cost |
| **VM/VMSS** | Workloads needing OS/VM control, not yet ready for K8s | Self-manage more deployment and lifecycle tasks |

### 8.1. Signs that AKS is a good fit

- The organization already has Kubernetes deployment standards, Helm/GitOps, and skilled platform engineers.
- You need operators, CRDs, a service mesh, or specific Kubernetes primitives.
- Multiple workloads require scheduling across distinct node pools and resource profiles.
- You need control over Kubernetes networking, namespace policies, ingress, and deployment lifecycles.
- You want consistent deployment of a complex suite of applications following the Kubernetes model.

### 8.2. When should you choose a simpler service?

If you only have one Java API and one background worker without needing deep Kubernetes capabilities, evaluate App Service or Container Apps first. Forcing a small, simple service onto AKS adds the overhead of nodes, networking, monitoring, Kubernetes upgrades, and on-call operations without proportional value.

**The selection criteria should be actual application requirements and team capability, not technology popularity.**

## 9. Single cluster or multiple clusters?

This choice directly affects cost, blast radius, and governance.

### 9.1. One shared cluster for multiple applications

Example:

~~~text
AKS shared cluster
├── namespace team-orders
├── namespace team-customers
└── namespace team-analytics
~~~

Pros:

- Shares node capacity and platform services.
- Can reduce the number of control planes, node pools, and operational effort.
- Convenient when multiple teams share similar security standards.

Cons:

- Cluster-level upgrade failures, networking changes, or permission errors affect multiple teams.
- Applications compete for CPU, memory, IPs, quotas, and shared limits.
- A namespace is not a strong security isolation boundary equivalent to a separate cluster.

### 9.2. Dedicated clusters per environment or high-risk group

Example:

~~~text
aks-dev-shared
aks-staging
aks-prod-orders
aks-prod-finance
~~~

Pros:

- Separates permissions, network configuration, maintenance windows, and operational fault domains.
- Reduces the risk of experimental changes impacting production.
- Suitable when teams have different compliance requirements or lifecycles.

Cons:

- Increases resource count, management overhead, and update work.
- Requires operating multiple pipelines, policies, monitoring setups, and identity integrations.
- Fragments capacity if each cluster keeps idle buffer nodes.

### 9.3. Recommended rule of thumb

**Separating production from development/test** is usually worth considering when high safety and stability are required. For multiple teams with the same trust level, a shared production cluster can be cost-effective but requires clear quotas, RBAC, Network Policy, admission controls, and monitoring. For sensitive workloads or strict isolation needs, dedicated clusters may be more appropriate.

Do not mechanically create one cluster per microservice; equally, do not lump every workload into one cluster without assessing blast radius.

## 10. Public cluster or private cluster?

The Kubernetes API endpoint is a sensitive management target. The public/private choice relates to the **API server access path**, not merely whether the application has a public IP.

### 10.1. API server with a public endpoint

A cluster with a public API endpoint allows management tools to reach the endpoint over the Internet as configured. Authentication and authorization are still required; source access can be restricted with **authorized IP ranges** or other supported mechanisms.

**A public endpoint does not mean anyone has admin access to the cluster.** Risk depends on authentication, RBAC, network restrictions, client security, and cluster configuration.

### 10.2. Private AKS cluster

With a private cluster, API server access is designed over private connectivity and DNS according to the supported AKS model. Tools like kubectl, CI runners, and operators must have a valid network path, such as an internal network connected via VPN/ExpressRoute, a jump host, or an appropriate management environment.

Pros:

- Reduces exposure of the API server directly over the Internet.
- Aligns with enterprise policies requiring a private management plane.

Cons:

- Requires designing DNS, routing, firewalls, and management connectivity.
- Hosted CI/CD runners without VNet access may be unable to manage the cluster.
- Troubleshooting and access provisioning must be prepared in advance.

### 10.3. Do not confuse a private API with a private application

A cluster with a private API server can still expose a **public LoadBalancer/Ingress** for customer applications. Conversely, a cluster with a public API can run purely internal workloads not exposed to the Internet.

Make separate decisions for:

1. Access to the **Kubernetes API**.
2. Access to **applications**.
3. **Egress** paths from nodes/pods to external services.

## 11. Designing regions, Availability Zones, and HA

A production AKS cluster typically needs multiple nodes and replicas to withstand infrastructure failures.

### 11.1. Availability Zones

If the region and VM SKU support them, consider spreading nodes of critical pools across multiple **Availability Zones**. However, selecting zones on a node pool alone is not enough: workloads must have multiple replicas, proper scheduling rules, and dependencies with their own redundancy plans.

Example:

~~~text
Zone-supported region
  Zone 1: system node(s), API pod(s)
  Zone 2: system node(s), API pod(s)
  Zone 3: system node(s), API pod(s)
~~~

This is an architectural goal; actual node counts and pod distribution must be verified.

### 11.2. Replicas and PodDisruptionBudget

**Deployment replicas** help maintain multiple instances of an application. **PodDisruptionBudget (PDB)** limits how many pods can be voluntarily disrupted during operations such as drains or upgrades.

However, a PDB does not prevent involuntary node/zone outages, and an overly strict configuration can block upgrades. You must evaluate PDBs alongside total replicas and spare capacity.

### 11.3. Multi-region is more than multiple AKS clusters

If recovering from an entire region outage is required, you can design **two AKS clusters across two regions** combined with Front Door/Traffic Manager or an appropriate routing mechanism. But you also need:

- Data and database replication matching RPO.
- Container images available in the standby region.
- Consistent permissions, secrets, and configuration.
- Prepared networking, DNS, TLS, and storage.
- Rehearsed failover and failback procedures.

**Availability Zones protect against certain intra-region failures; they do not replace multi-region disaster recovery.**

## 12. System pool and user pools in production

A commonly used design:

| Pool | Role | Guidance |
|---|---|---|
| **systempool** | Kubernetes system components | Stable VMs, adequate spare capacity |
| **apipool** | Stateless APIs | Replicas and autoscaling based on traffic |
| **workerpool** | Batch/Queue workers | Can use separate SKUs or scaling rules |
| **gpupool** | GPU processing if needed | Enable only when demand, quota, and plugins exist |

Not every application needs four pools. Multiple pools isolate resources and optimize scheduling, but increase management overhead, fixed cost, and compute fragmentation risk.

### 12.1. System nodes should not be filled up

System components need CPU, RAM, and disk. If you allow batch workloads to consume all capacity on the system pool, DNS, network agents, and platform components can become unstable.

### 12.2. Node pools tailored to workload profiles

Examples:

- Java APIs needing large RAM for the JVM → choose a memory-appropriate pool.
- CPU-intensive image-processing workers → compute-oriented pool.
- Windows workloads require a compatible Windows node pool.
- Eviction-tolerant jobs can use a Spot pool if supported by the AKS/mode configuration.

Do not schedule Windows/Linux pods onto the wrong OS pool; use node selectors, labels, and matching image architectures.

## 13. Designing IP addressing before creating the cluster

Kubernetes uses multiple address layers:

- **VNet/subnet CIDR:** addresses for nodes and Azure components.
- **Pod CIDR or Pod subnet:** addresses for pods depending on the CNI model.
- **Service CIDR:** virtual IP space for Kubernetes Services.
- **DNS service IP:** IP of the in-cluster DNS service.
- **On-prem/peered VNet networks:** prefixes connected via VPN/ExpressRoute.
- **Private endpoints:** VNet addresses for Azure services.

Illustrative address plan example:

| Type | CIDR |
|---|---|
| VNet | 10.40.0.0/16 |
| Node subnet | 10.40.10.0/24 |
| Pod overlay CIDR | 10.244.0.0/16 |
| Service CIDR | 10.96.0.0/16 |
| DNS service IP | 10.96.0.10 |
| On-prem | 172.20.0.0/16 |

**None of these ranges may overlap with each other or with connected networks**, subject to the networking mode's rules. The ranges above only illustrate the principle of subnet separation; in real deployments, also check reserved ranges, AKS limits, and growth plans.

Bad IP addressing designs are hard to fix once a cluster holds data or many workloads. Some CIDR changes require creating a new cluster or complex migration procedures.

## 14. Azure CNI and how IPs are allocated to Pods

**Container Network Interface (CNI)** is the networking layer for pods. AKS supports different Azure CNI models depending on version, SKU, and configuration.

### 14.1. Azure CNI Overlay

In the **overlay** model, pods receive addresses from a Pod CIDR separate from the nodes' VNet subnet. The network layer handles pod-to-pod and pod-to-external traffic via the model's overlay/NAT mechanisms.

Common benefits:

- Reduces direct consumption of VNet IPs per pod.
- Useful when VNet IP space is constrained and pod counts are high.
- Decouples pod IP planning from the node subnet where supported.

You must verify routing behavior, network policies, outbound connectivity, service compatibility, and scenarios requiring direct pod reachability.

### 14.2. Azure CNI with addresses from VNet/pod subnet

Some Azure CNI models assign pods addresses routable within the Azure network as supported, such as allocating from the node subnet or a dedicated pod subnet.

This helps in certain architectures, but **consumes VNet/pod subnet IPs** based on pod counts and allocation configuration, so scalability must be calculated upfront.

### 14.3. Network dataplane and policy

AKS may support dataplane/network policy options such as **Azure CNI powered by Cilium** or other mechanisms depending on configuration. Policy features, observability, and integration capabilities must be verified on the target AKS/networking version.

**Network Policy does not replace NSGs/Azure Firewall**, nor do NSGs automatically enforce pod-to-pod policies in the same way. Designs often require defense in depth across multiple layers.

### 14.4. Do not pick networking from a random sample command

When choosing a CNI, ask:

1. What is the maximum number of pods per node?
2. What is the maximum number of nodes per node pool?
3. Does the VNet have enough IP addresses?
4. Are there on-prem/peered VNets or private endpoints?
5. Do we need to control east-west traffic between namespaces?
6. Is overlay/NAT acceptable, or must pod IPs be routable in the VNet?
7. Are our monitoring, security, and policy tools supported?

This is a foundational cluster decision; avoid choosing randomly and trying to change it after workloads are deployed.

## 15. Service, Ingress, and traffic paths

Kubernetes provides objects for application communication:

| Component | Function | Example |
|---|---|---|
| **ClusterIP Service** | Internal service identity and load balancing inside the cluster | Backend API calling service orders-api |
| **NodePort** | Opens a port on nodes using the supported mechanism | Often a technical building block or lab tool |
| **LoadBalancer Service** | Requests Azure to provision/integrate a load balancer per configuration | Public or private TCP/HTTP endpoint |
| **Ingress / Gateway API** | L7 routing rules when backed by a corresponding controller/implementation | HTTP host/path, TLS, routing to Services |

**An Ingress resource does not process traffic on its own without a suitable controller.** For instance, you need an ingress controller or an AKS-supported integration service; deploying only Ingress YAML without a controller creates no actual proxy.

### 15.1. Public ingress

Used when Internet users need to call APIs. Requires TLS, WAF if appropriate, application/API protection policies, and health checks.

### 15.2. Internal ingress

Used when APIs only serve internal networks, private endpoints, or other workloads. Can be configured with an internal Load Balancer or matching ingress without exposing a public IP.

### 15.3. Outbound/egress

Nodes/pods may need to pull images from ACR, call external APIs, access Azure services, and send telemetry. Design egress explicitly via NAT Gateway, Azure Firewall, or an AKS-supported option, rather than relying on uncontrolled default outbound access.

**A private AKS cluster still needs paths to required endpoints for the cluster and workloads to operate.** Overly restrictive egress policies can break image pulls, node bootstrapping, or updates.

## 16. DNS and service discovery

Inside the cluster, Kubernetes DNS normally allows a pod to call a Service by name:

~~~text
orders-api.apps.svc.cluster.local
~~~

Assuming:

- Service name: **orders-api**
- Namespace: **apps**
- Cluster domain: **cluster.local** (common example)

A pod in another namespace can use this FQDN to reach the Service. If the service is in the **apps** namespace and the pod is in the same namespace, the short name **orders-api** is usually sufficient.

Distinguish between:

- **CoreDNS/Kubernetes service discovery:** Service names inside the cluster.
- **Azure Private DNS:** names of private endpoints or Azure resources inside the VNet.
- **Public DNS:** Internet domain names of the application.

An AKS workload using Azure SQL via a private endpoint may require the proper private DNS zone, VNet link, and routing. Working Kubernetes DNS does not mean Azure private DNS is configured properly.

## 17. Identity and access control in AKS

A complete design covers at least three distinct permission groups:

1. **Azure resource management:** who can modify the AKS cluster, node pools, networking, or IAM via Azure Resource Manager.
2. **Kubernetes API access:** who can list, create, update, or delete Kubernetes objects.
3. **Workload permissions to Azure services:** whether a pod can read Blob storage, fetch secrets from Key Vault, or call other APIs.

### 17.1. Microsoft Entra ID and Kubernetes RBAC

AKS can integrate with Microsoft Entra ID to authenticate users accessing the cluster. After authentication, authorization can be handled by **Kubernetes RBAC** or **Azure RBAC for Kubernetes Authorization**, depending on the chosen model.

Do not confuse **Azure Contributor on a resource group** with permission to edit all Deployments inside the cluster. These permissions belong to different layers; kubeconfig retrieval and action scopes must be configured explicitly.

### 17.2. Cluster and kubelet managed identities

AKS uses identities to interact with required Azure resources. There can be a **cluster identity** and a **kubelet identity** for different tasks. For example, kubelet/node ACR pull permission must be granted to the right principal and scope according to the ACR authorization mode.

### 17.3. Workload Identity

**Microsoft Entra Workload ID** enables Kubernetes workloads to obtain tokens by federating a Kubernetes ServiceAccount with Microsoft Entra ID, in supported AKS configurations.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant P as Pod
    participant SA as Kubernetes ServiceAccount
    participant EN as Microsoft Entra ID
    participant ST as Azure Storage
    P->>SA: Uses configured identity
    SA-->>P: Projected service account token
    P->>EN: Exchanges token via federated identity
    EN-->>P: Token for Azure resource
    P->>ST: Calls API with granted permissions
~~~

You must properly configure the OIDC issuer, federated credential, ServiceAccount, Azure identity, and data-plane RBAC. Enabling a single cluster flag does not automatically grant every pod permission to read Storage.

### 17.4. Secret management

Never embed passwords, account keys, or private keys in container images or Git. Use managed identities, Key Vault with the Secrets Store CSI Driver, or another approved secrets management solution. A Kubernetes Secret can be part of configuration management, but still requires access controls and encryption according to design.

## 18. Azure Container Registry in AKS architecture

Applications need container images before pods can be created. A common flow:

~~~text
Source code -> CI build/test -> Azure Container Registry
                                  |
                                  v
                         AKS node pulls image
                                  |
                                  v
                             Kubernetes Pod
~~~

Workflow:

1. Build and test the image.
2. Push to an ACR repository with an explicit tag.
3. Record the manifest digest.
4. Grant the appropriate identity pull permissions under the ACR RBAC/repository authorization model.
5. Configure the Deployment to use the verified image.
6. Inspect pod events if pulling fails.

**ImagePullBackOff** can stem from a wrong tag/digest, missing permissions, private endpoint DNS issues, firewalls, or an image built for the wrong CPU architecture. Do not enable the ACR admin user as a blanket workaround for every error.

Production should pin images by digest or enforce immutable tag controls. The **latest** tag provides no guarantee of being the newest version and can cause drift between environments.

## 19. Requests, limits, and Kubernetes scheduling

When multiple workloads share a cluster, **resources.requests** and **resources.limits** affect placement and how containers consume CPU/memory.

- **CPU request:** CPU amount used by the scheduler when deciding if a pod fits on a node.
- **Memory request:** RAM amount reserved by the scheduler for placement.
- **CPU limit:** upper CPU cap enforced by the runtime, which can cause throttling.
- **Memory limit:** exceeding this limit can result in the container being OOMKilled.

Example:

~~~yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
~~~

Here **100m CPU** equals 0.1 CPU core in Kubernetes units. Do not set requests to 0 and expect the cluster autoscaler to infer actual demand.

### 19.1. Why do requests matter?

Suppose a node has 1 GiB of allocatable RAM left according to the scheduler, while a pod requests 2 GiB: the pod cannot be placed on that node even if CPU is idle. If no suitable node remains, the pod stays **Pending**.

### 19.2. Why must limits be measured?

A memory limit set too low causes Java JVMs or Node.js processes to get OOMKilled. A CPU limit set too tight can trigger throttling and increase latency. Measure load, Heap/GC, startup, and real RAM consumption before finalizing values.

### 19.3. Namespace quotas

**ResourceQuota** and **LimitRange** can restrict total resources and set default bounds inside a namespace. They help mitigate noisy neighbors, but do not turn a namespace into a standalone security boundary.

## 20. Three autoscaling layers to distinguish

AKS often involves multiple scaling mechanisms operating at different layers.

| Mechanism | What does it change? | Typical signal |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | Number of replicas of a workload | CPU, memory, or supported metrics |
| **KEDA** | Number of replicas for event-driven workloads | Queue length, event source, or custom scalers |
| **Cluster Autoscaler** | Number of nodes in a configured node pool | Pending pods due to insufficient resources and scale-in conditions |
| **Node Auto Provisioning (if supported)** | Provisions/selects node capacity more flexibly | Scheduling demand and node provisioning policies |

### 20.1. HPA: adding pods

When API pod CPU rises, HPA can tell the Deployment to scale from 2 to 5 replicas. However, if the node pool lacks sufficient resources, the new pods will stay **Pending**.

### 20.2. Cluster Autoscaler: adding nodes

When pods are Pending due to insufficient capacity and the node pool has valid autoscaling configured, Cluster Autoscaler can request additional nodes. This takes time for VM provisioning.

### 20.3. KEDA: event-driven scaling

Queue-processing workers may need to scale based on message count or processing lag rather than CPU. KEDA is useful when installed/enabled and configured in the cluster.

### 20.4. Sequence of events

~~~mermaid
flowchart LR
    LOAD[Load or queue backlog increases] --> HPA[HPA / KEDA increases replicas]
    HPA --> SCHED{Enough node resources?}
    SCHED -->|Yes| PODS[Pods run]
    SCHED -->|No| PENDING[Pods Pending]
    PENDING --> CA[Cluster Autoscaler / node provisioning]
    CA --> NODES[New node boots]
    NODES --> PODS
~~~

**Increasing replicas does not mean serving capacity rises instantaneously.** You must account for scheduling time, image pulling, startup/readiness checks, and downstream dependency capacity.

## 21. Persistent data storage for workloads

The container filesystem is generally not suitable for persistent data. A pod can be replaced or rescheduled onto another node.

| Data type | Candidate solution | Notes |
|---|---|---|
| Disposable cache/scratch | emptyDir or suitable local ephemeral storage | Can be lost when the pod is deleted/moved |
| Database volume or durable files | PersistentVolume/PersistentVolumeClaim with Azure Disk CSI | Typically subject to zone, access mode, and detach/attach constraints |
| Shared files across pods | Azure Files CSI when appropriate | Consider protocol, latency, permissions, and cost |
| Object files | Azure Blob Storage SDK or suitable integration | Differs from standard block/file filesystems |
| Secrets | Key Vault/Workload Identity or approved mechanisms | Never store in images or public files |
| Retained logs | Azure Monitor/Log Analytics or centralized storage | Pods may vanish after upgrades |

### 21.1. PersistentVolume and PersistentVolumeClaim

A **PVC** describes a workload's capacity and access mode requirements. A **StorageClass** defines how dynamic provisioning works; the **CSI driver** connects Kubernetes to Azure storage.

For example, with Azure Disk: a disk is typically attached under specific access mode/node/zone constraints, so multiple pods across multiple nodes cannot simultaneously write to it by default like a shared file system.

### 21.2. StatefulSet

**StatefulSet** provides relatively stable pod identities and volume templates per replica, useful for certain stateful applications. However, it is not an automatic database replication or backup solution. Whenever possible, use managed data services to reduce the burden of self-operating stateful clusters.

### 21.3. Backup and restore

Backing up YAML/Helm charts does not mean backing up data inside PVs. You need a backup plan for cluster resources, persistent volumes, and databases aligned with RPO/RTO. You can consider Azure Backup for AKS or equivalent tools where supported, but always test actual restoration.

## 22. Probes, Deployments, and readiness

Kubernetes provides common probes:

- **Startup probe:** useful for slow-starting applications; prevents liveness from declaring failure too early.
- **Readiness probe:** determines whether a pod is ready to receive traffic through a Service.
- **Liveness probe:** helps detect when a container needs to be restarted.

For example, after starting the JVM, a Java API needs to load configuration and connect to the database. During this phase, readiness can return failure, returning success only once the app is ready.

**Readiness and liveness are not the same.** If a liveness check directly depends on an external service that is currently down, all pods could be restarted unnecessarily, worsening the outage.

### 22.1. Rolling updates

A Kubernetes Deployment can replace pods in batches using a rolling strategy. To minimize disruption:

1. Maintain enough replicas.
2. Configure readiness properly.
3. Set appropriate maxUnavailable/maxSurge values.
4. Handle SIGTERM and graceful shutdown.
5. Maintain spare capacity and an appropriate PDB.
6. Monitor error rates during rollout.

Rolling updates do not automatically fix incompatible database migrations. When two application versions run concurrently during a rollout, service protocols and schemas must remain compatible across the transition period.

## 23. AKS upgrades and cluster lifecycle

Kubernetes and node OS images must be upgraded regularly to stay supported and secure.

Types of changes:

- **Kubernetes control plane version:** updates the API/control plane version.
- **Node pool Kubernetes version:** updates nodes according to compatibility rules.
- **Node OS image:** applies OS image security patches to nodes.
- **Application/Helm releases:** updates workload images and manifests.
- **Add-ons/CSI/CNI:** upgrades integrated components that have their own lifecycles.

### 23.1. Safe upgrade process

1. Check the current Kubernetes version and AKS-supported target versions.
2. Review deprecations/API removals affecting manifests or controllers.
3. Verify add-ons, Helm charts, and workload compatibility.
4. Upgrade a staging environment mirroring production first.
5. Ensure system/user pools have spare capacity.
6. Review PDBs, requests, quotas, topology spread, and drain behavior.
7. Choose maintenance windows, upgrade channels, and surge settings as supported.
8. Monitor pods, node replacement, deployment health, and metrics.
9. Test actual application behavior after upgrading.
10. Have a recovery plan if an upgrade fails; you cannot arbitrarily downgrade a Kubernetes cluster.

### 23.2. Do not pin a cluster to an old version for too long

Leaving AKS on an unsupported Kubernetes version increases security risk, integration failures, and the difficulty of multi-hop upgrades. Establish a maintenance schedule and clear ownership for cluster lifecycle.

## 24. Layered cluster security

An AKS security model requires controls across multiple layers:

| Layer | Controls |
|---|---|
| **Subscription / ARM** | RBAC, Azure Policy, resource group governance |
| **API server** | Appropriate private/public access, Entra auth, authorized IPs if public, audit logs |
| **Kubernetes permissions** | Least-privilege Roles/RoleBindings or Azure RBAC for K8s |
| **Pods** | Non-root, restricted capabilities, no privileged unless required, resource limits |
| **Images** | ACR, scanning, digests, provenance, admission policies |
| **Network** | NSGs, Network Policy, firewall, private endpoints, TLS |
| **Secrets** | Managed identity, Key Vault, workload identity |
| **Node/OS** | Patching, security monitoring, disk encryption, runtime hardening |
| **Monitoring** | Audit logs, runtime alerts, incident response |
| **Data** | Backups, encryption, access controls, and DR |

### 24.1. Admission controls and policies

Azure Policy for Kubernetes, admission controllers, or equivalent policies can help block privileged containers, unapproved image registries, or missing security contexts. However, features and enforcement modes must be tested before enforcing in production.

### 24.2. Do not grant cluster-admin to every developer

The cluster-admin role can modify almost all Kubernetes objects. Separate roles clearly:

- Platform team: controlled cluster administration permissions.
- Application team: edit Deployments/Services only within assigned namespaces.
- CI identity: deployment permissions scoped appropriately.
- Runtime ServiceAccount: minimal permissions within Kubernetes and Azure.

### 24.3. Namespaces are not absolute sandboxes

A pod with host privileges or overly broad Kubernetes permissions can affect the entire cluster. When workloads come from untrusted groups or have vastly different compliance requirements, separate clusters or stronger isolation may be necessary.

## 25. Monitoring AKS with Azure Monitor and Kubernetes tools

To detect issues, observe across three levels (and key domains):

| Domain | What to monitor | Significance |
|---|---|---|
| Cluster/control plane | API availability, upgrade/operation status | Detect platform/management issues |
| Node pools/nodes | CPU, RAM, disk, node readiness, pressure | Identify compute bottlenecks |
| Pods/workloads | Restarts, OOMKilled, Pending, readiness, HTTP errors | Identify application faults |
| Autoscaling | HPA desired/actual replicas, Cluster Autoscaler events | Explain why scaling is not happening |
| Network | DNS, egress, ingress, policy drops | Troubleshoot connectivity issues |
| Data | Database latency, PVC, CSI attach/mount errors | Troubleshoot stateful failures |
| Security | Audit events, image scan findings, identity errors | Detect unauthorized changes |
| Cost | Node hours, disks, LB/NAT, logs, egress | Optimize operations |

Azure tooling may include Azure Monitor Container Insights, managed Prometheus/Azure Monitor metrics, Azure Managed Grafana, and Log Analytics depending on configuration/features. Regardless of the tool, define retention, sampling, label cardinality, and ingestion costs.

### 25.1. Useful Kubernetes diagnostic commands

~~~bash
kubectl get nodes -o wide
kubectl get pods --all-namespaces
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
~~~

The **--previous** flag helps when a container has restarted and logs from the prior run remain; those logs are not always preserved. Avoid exposing secrets or sensitive data from logs in public channels.

## 26. Decision patterns: choosing among cluster architectures

Suppose an enterprise has Java APIs, a Queue worker, a data layer, and an Azure operations team.

### Option A — Single AKS Standard cluster for production

~~~text
Production AKS
├── systempool (multiple stable nodes)
├── apipool (API pods, HPA)
└── workerpool (Queue workers, KEDA if appropriate)
    |
    +-- Azure Container Registry
    +-- Managed database
    +-- Azure Blob / Queue
    +-- Key Vault / Workload Identity
    +-- Azure Monitor
~~~

Suitable when the company has a clear Kubernetes platform, wants separate node pool profiles, and applications can share risk and policies.

### Option B — Separate AKS clusters for production and non-production

~~~text
aks-nonprod
  - development namespaces
  - test workloads

aks-prod
  - production API/worker
  - stricter RBAC and ingress
  - independent upgrade window
~~~

Suitable when experimental configuration risks must not affect production. In return, it requires higher cost and operational effort.

### Option C — Multi-region production AKS

~~~text
Region A: AKS + ingress + application
Region B: AKS + ingress + application
        \     /
     Global traffic routing
        |
  Replicated/recoverable data per architecture
~~~

Suitable when RTO/RPO requires surviving an entire region outage. Replicating Deployments alone is insufficient: you also need DNS, TLS, databases, ACR image distribution, secrets, backups, and autonomous operation in Region B.

### Option D — Do not use AKS

If the application consists of only a few containers needing autoscale without managing node pools, consider **Azure Container Apps**. If it is just a simple web/API app, consider **App Service**. If a specialized workload requires OS control, consider VMSS.

**Selection rule:** use the least complex model that still fully satisfies operational, security, growth, and resiliency requirements.

## 27. Architectural decision matrix

| Criterion | Shared cluster | Dedicated clusters | Multi-region |
|---|---|---|---|
| Platform cost | Usually lower | Higher due to multiple clusters/pools | Highest among these options |
| Change isolation | Lower | Better | Separates regional failure domains too |
| Upgrade autonomy | Multiple teams must coordinate | Teams can pick separate windows | Requires coordinating two regions |
| Strict compliance | Must prove isolation | Easier when strong separation is required | Still depends on data layer |
| Operational capacity | One platform team | Must operate multiple clusters | Requires DR and traffic routing |
| Regional outage resiliency | Insufficient | Not sufficient alone | Can meet needs if the whole system is designed |
| Node utilization | Easier to share | Can fragment capacity | Needs spare capacity in two locations |

Also evaluate: **Standard/Automatic**, **public/private API**, **system/user pools**, and **networking mode**. These choices are not mutually exclusive; an enterprise can run multiple dedicated clusters, each private, with multi-zone node pools.

### 27.1. Recording a decision with an ADR

For major architectural choices, write an **Architecture Decision Record (ADR)** covering:

- Context and requirements.
- Options considered.
- Decision and rationale.
- Trade-offs and unmet conditions.
- Owner and review date.
- Validation methods via load testing, security testing, and DR testing.

Example: "Separate production cluster for independent upgrades and RBAC policies; use Azure CNI Overlay to conserve VNet IPs; adopt a private API because CI runners already have private network connectivity; split user pools between API and worker due to differing load profiles."

## 28. Creating a test AKS cluster with Azure CLI

**Note:** this example is only for an authorized subscription and resource group with a lab budget. Region names, SKUs, networking features, and CLI flags must be verified against your current Azure CLI/AKS version before running. Do not blindly execute these commands from the article.

Sign in:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

Create a resource group:

~~~bash
az group create \
  --name rg-aks-architecture-lab \
  --location southeastasia
~~~

Example creating a test cluster with managed identity, 2 nodes, and Azure CNI Overlay networking:

~~~bash
az aks create \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab \
  --node-count 2 \
  --node-vm-size Standard_D2s_v5 \
  --enable-managed-identity \
  --network-plugin azure \
  --network-plugin-mode overlay \
  --generate-ssh-keys
~~~

Explanation:

- **--node-count 2:** initial node count, not application replica count.
- **--node-vm-size:** VM SKU must have quota/capacity and meet cluster requirements.
- **--enable-managed-identity:** uses managed identity for supported Azure integrations.
- **--network-plugin azure --network-plugin-mode overlay:** demonstrates one networking option for learning, not a default right choice for every enterprise.
- **--generate-ssh-keys:** intended for a lab environment per CLI behavior; production requires proper key management.

The minimal command above **does not fully configure** network security, private API, Availability Zones, additional node pools, workload identity, policies, or production monitoring. Do not use it verbatim as a production blueprint.

### 28.1. Connecting kubectl

~~~bash
az aks get-credentials \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab

kubectl get nodes -o wide
kubectl get namespaces
kubectl get pods -n kube-system
~~~

The **get-credentials** command updates/modifies your local kubeconfig. Only run it on an authorized workstation/runner and verify the Kubernetes context before any mutating command:

~~~bash
kubectl config current-context
kubectl cluster-info
~~~

Do not run delete or deploy commands before confirming you are targeting the intended lab cluster.

### 28.2. Inspecting node pools and the cluster

~~~bash
az aks show \
  --resource-group rg-aks-architecture-lab \
  --name aks-architecture-lab \
  --query "{name:name,kubernetesVersion:kubernetesVersion,nodeResourceGroup:nodeResourceGroup}" \
  --output json

az aks nodepool list \
  --resource-group rg-aks-architecture-lab \
  --cluster-name aks-architecture-lab \
  --output table
~~~

Observe the node resource group and node pools. **Do not manually edit VMSS/NICs in the node resource group** to alter the cluster; use the corresponding AKS API/CLI.

## 29. Deploying a sample Deployment and Service

A lab should begin with a workload containing no sensitive data and requiring no public IP exposure.

Create a namespace:

~~~bash
kubectl create namespace aks-lab
~~~

Illustrative contents of **aks-demo.yaml**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-web
  namespace: aks-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: demo-web
  template:
    metadata:
      labels:
        app: demo-web
    spec:
      containers:
        - name: web
          image: nginx:stable
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "250m"
              memory: "128Mi"
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: demo-web
  namespace: aks-lab
spec:
  type: ClusterIP
  selector:
    app: demo-web
  ports:
    - port: 80
      targetPort: 80
~~~

**image: nginx:stable** is only for lab illustration. In production, pin digests or verified immutable tags and control image sources rather than relying on mutable tags.

Apply the manifest after creating the file in your lab environment:

~~~bash
kubectl apply -f aks-demo.yaml

kubectl get deployments -n aks-lab
kubectl get pods -n aks-lab -o wide
kubectl get service -n aks-lab
kubectl rollout status deployment/demo-web -n aks-lab
~~~

Verify without creating a Public Load Balancer by using port-forward:

~~~bash
kubectl port-forward -n aks-lab service/demo-web 8080:80
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8080/
~~~

This test path only opens a forwarding session from the machine running kubectl, not a production ingress. For a private cluster, the machine running kubectl must have network connectivity to the API server and related paths.

## 30. Testing replicas, HPA, and observing scheduling

Manually scale replicas:

~~~bash
kubectl scale deployment/demo-web \
  --replicas=3 \
  -n aks-lab

kubectl get pods -n aks-lab -o wide
~~~

If the cluster has available compute, three pods will be scheduled onto corresponding nodes; if capacity is lacking, some pods may remain Pending.

### 30.1. Basic HPA

If the cluster provides the metrics API/metrics-server properly:

~~~bash
kubectl autoscale deployment demo-web \
  --cpu-percent=60 \
  --min=2 \
  --max=5 \
  -n aks-lab

kubectl get hpa -n aks-lab
~~~

This example requires valid CPU requests and active metrics data. **HPA scales pods, not nodes**, unless the node pool has an appropriate autoscaler/node provisioning mechanism configured.

If you want to test cluster autoscaler, configure autoscaling on an AKS-supported node pool, set min/max bounds, and monitor costs. Do not enable large-scale scaling without quotas, budgets, and a cleanup plan.

### 30.2. Inspecting a Pending pod

~~~bash
kubectl get pods -n aks-lab
kubectl describe pod <pending-pod-name> -n aks-lab
kubectl get events -n aks-lab --sort-by=.metadata.creationTimestamp
~~~

Look for reasons such as **Insufficient cpu**, **Insufficient memory**, no matching nodes, mismatched taints/tolerations, or missing volumes. Do not conclude Azure "failed to create the pod" when the scheduler already explained the reason.

## 31. Architecture exercise: comparing three AKS models

**Scenario:** an enterprise has two Java APIs, a Queue worker, and data in Azure SQL/Blob. The team is considering migrating from Container Apps to AKS because they need stricter policies and more complex scheduling.

### Part A — Gather requirements

Build a table:

| Requirement | Questions |
|---|---|
| Number of apps | How many Deployments/Jobs/namespaces? |
| Load | Requests/s, jobs/s, peak traffic, and startup time? |
| Security | Private or public API? Which RBAC/Network Policies? |
| Data | Stateful services, PVCs, or managed databases? |
| HA | Tolerate node, zone, or region loss? |
| Operations | Does the team have Kubernetes experience, on-call coverage, and upgrade capability? |
| Cost | Budget for nodes/pools, egress, logs, and backups? |

### Part B — Choose a model

Propose three options:

1. **Container Apps** for simpler applications to reduce Kubernetes operational overhead.
2. **One AKS Standard or Automatic cluster** if features support it, with appropriate namespaces and node pools.
3. **Separate non-production/production AKS clusters** if risk and upgrade isolation are needed.

Score them on security, control level, cost, availability, and team capability. Do not pick "the option with the most components" by default.

### Part C — Preliminary AKS design

If AKS is chosen:

1. Select the region and Availability Zones requirements.
2. Choose a restricted public or private API endpoint.
3. Plan VNet, node subnet, Pod CIDR, Service CIDR, and DNS IP.
4. Select appropriate CNI and Network Policy.
5. Choose system/user pools, VM SKUs, and autoscaling rules.
6. Define managed identity, Entra integration, and workload identity.
7. Choose ingress, egress, ACR, and paths to databases/private endpoints.
8. Plan monitoring, backups, upgrade windows, and budgets.
9. Diagram failure domains and plans for handling node/zone loss.

### Part D — Lab implementation

1. Create a test AKS cluster per section 28, ensuring you do not use a production subscription.
2. Confirm the kubeconfig context and inspect nodes and system pods.
3. Deploy demo-web using a Deployment and ClusterIP Service.
4. Check readiness and port-forward.
5. Scale replicas from 2 to 3 and observe scheduling.
6. Try HPA if metrics are working; distinguish HPA from node autoscaler.
7. Simulate a pod crash by deleting **a pod belonging to the lab Deployment itself**, and observe the controller creating a replacement; do not delete system pods.
8. Inspect Events/Logs to observe the impact.
9. Clean up the namespace and lab resources according to approved procedures.

### Part E — Report

The report should include:

- Decision between AKS or Container Apps and rationale.
- Chosen cluster model: Automatic/Standard if supported, public/private, shared/dedicated.
- CNI, ingress, egress, node pools, Availability Zones.
- Authentication path and workload permissions.
- HPA/node autoscaling strategy.
- Fault tolerance, backup, and DR.
- Cost estimate.
- Results from the scaling/pod restart test.

**Completion criteria:** learners prove why the architecture meets requirements, rather than merely creating a cluster successfully.

## 32. AKS costs: more than just the cluster fee

Cost components to review:

| Category | Cost drivers |
|---|---|
| **Control plane / service tier** | Depends on the chosen service tier, SLA, and AKS model |
| **Compute** | Node count, VM size, operating system, and runtime hours |
| **Disk/storage** | OS disks, PV/PVC, snapshots, and backups |
| **Network** | Load Balancer, Public IP, NAT Gateway, Firewall, egress |
| **Registry** | ACR SKU, image storage, and image builds |
| **Monitoring** | Azure Monitor, Log Analytics, metrics, and retention |
| **Data services** | Azure SQL, Cosmos DB, Blob/Queue, cache, Key Vault |
| **HA/DR** | Redundant capacity across zones/regions, replication, and failover |

An idle cluster does not stop costing money: **node pools maintaining minimum nodes still incur compute charges**, alongside networking, storage, and monitoring services.

### 32.1. Cost optimization without breaking HA

- Base requests/limits on real metrics to avoid over-provisioning.
- Autoscale node pools for fluctuating workloads.
- Separate stable system pools from workload-specific user pools.
- Choose Spot nodes for retryable batch jobs; never rely solely on Spot for critical components.
- Reduce image sizes and unnecessary log ingestion.
- Avoid creating separate clusters without a matching isolation need.
- Control idle non-production hours if organizational policy permits.
- Set up Azure Cost Management budgets and cost alerts.

Never cut system nodes or replicas to levels that cause downtime just to lower the bill. Cost optimization must be evaluated alongside SLOs and risk.

## 33. Common AKS issues and classification

### 33.1. Cannot connect with kubectl

Check the Kubernetes context, credential retrieval permissions, Entra authentication, RBAC, and network path to the API server. For private clusters, check private DNS, VPN/ExpressRoute, or where kubectl is executed.

### 33.2. Pod Pending

Check **kubectl describe pod**, CPU/memory requests, quotas, taints/tolerations, node selectors, zone/volume constraints, and autoscaler events.

### 33.3. ImagePullBackOff

Check image registry, repository/tag/digest, ACR RBAC/ABAC, kubelet identity, DNS/firewall/private endpoint, and image platform architecture.

### 33.4. CrashLoopBackOff

Check startup logs, command/args, secrets, resource limits, OOMKilled status, health probes, and database connectivity.

### 33.5. Service unreachable

Check Service selectors, endpoints, pod readiness, targetPort, Network Policy, ingress controller, NSGs, and Azure Load Balancer. Do not assume a DNS issue solely because the browser times out.

### 33.6. Internal DNS failures

Check CoreDNS pods, Service DNS, Network Policy, custom DNS forwarders, VNet DNS, and connectivity to private endpoints.

### 33.7. Scaling does not trigger

Does HPA have metrics? Are requests configured? Is Cluster Autoscaler enabled with a high enough max node count? Does the subscription have quota and the subnet have free IPs? Is there node SKU/zone capacity?

### 33.8. Upgrade blocked

Check for overly strict PDBs, missing surge capacity, pods failing to drain, node pools unable to provision new nodes, or older workloads using removed Kubernetes APIs.

### 33.9. Data lost after pod recreation

The application may be writing data to the container filesystem/emptyDir instead of a PVC or external storage. Verify data persistence and backups.

### 33.10. Cluster is "healthy" but users still see errors

AKS status does not fully reflect API quality. Check error rates, latency, databases, ingress, DNS, TLS, external dependencies, and the data layer.

## 34. Pre-production checklist for AKS

- [ ] Verified AKS is truly needed compared to Container Apps/App Service/VMSS.
- [ ] Selected Standard/Automatic based on features and operational ownership.
- [ ] Decided on shared/dedicated and prod/non-prod separation based on risk.
- [ ] Chosen public/private API server and verified CI/CD access paths.
- [ ] Designed region, zones, fault domains, and HA targets.
- [ ] Provisioned a system pool with adequate capacity and workload-aligned user pools.
- [ ] Confirmed VNet, subnet, Pod CIDR, Service CIDR, and DNS do not overlap.
- [ ] Aligned CNI, Network Policy, ingress, and egress with Azure networking.
- [ ] Controlled Azure RBAC/Kubernetes RBAC/Entra integration.
- [ ] Properly configured workload identity, ACR pull, and Key Vault.
- [ ] Tested, scanned, and pinned images by digest or immutable tag.
- [ ] Configured sensible requests/limits, probes, replicas, and PDBs on workloads.
- [ ] Set min/max/quotas/budgets on HPA/KEDA and node autoscaling.
- [ ] Equipped stateful workloads with PV/PVC/CSI and recoverable backups.
- [ ] Established a Kubernetes/node OS upgrade schedule and checked API deprecations.
- [ ] Set up logging, metrics, alerts, and incident response runbooks.
- [ ] Rehearsed pod, node, and zone failures according to SLOs.
- [ ] Prepared a multi-region DR plan if required by RPO/RTO.
- [ ] Calculated compute, disk, network, logs, ACR, and backup costs.
- [ ] Managed infrastructure via IaC/GitOps or controlled deployment processes.

## 35. Self-check questions

1. How do the control plane and worker nodes differ in responsibility? Which part does Azure manage?
2. Are namespace, node pool, and resource group the same?
3. Why should you not manually edit VMSS or NICs in the AKS node resource group?
4. How do AKS Standard and Automatic differ in operational orientation?
5. When might Azure Container Apps be a better fit than AKS?
6. Why should you consider a dedicated production cluster instead of sharing one with development?
7. Are a public Kubernetes API and public application ingress the same decision?
8. When choosing Azure CNI Overlay, which address ranges and connectivity paths must you verify?
9. How do HPA and cluster autoscaler differ in what they scale?
10. Why is a Deployment with 5 replicas but only 3 Running pods not necessarily an HPA bug?
11. What purpose does the system node pool serve, and why shouldn't batch jobs consume all its capacity?
12. How does Workload Identity relate to a Kubernetes ServiceAccount and Microsoft Entra ID?
13. When an ACR image hits ImagePullBackOff, which layers should you inspect?
14. What problem does PersistentVolumeClaim solve that emptyDir does not?
15. How does a PDB help during a node drain, and what are its limitations?
16. Why does a rolling upgrade require readiness checks, spare capacity, and schema compatibility?
17. Does a multi-zone cluster guarantee application availability if the database loses an entire region?
18. Where do major AKS costs come from even when there is no user traffic?
19. When an application returns 5xx errors while all nodes are Ready, what should you investigate?
20. What requirements would lead you to choose dedicated clusters or multi-region over a shared cluster?

## 36. Summary

**Azure Kubernetes Service (AKS)** provides managed Kubernetes on Azure, with the control plane operated by the platform and node pools running your organization's workloads. Good design requires understanding **control plane – node – pod – service**, governance responsibilities, and the role of each layer.

When choosing a cluster model, start from real needs: **AKS or a simpler container service; Standard or Automatic; single cluster or multiple clusters; public or private API; single region or multiple regions**. Then design **node pools, Availability Zones, VNet/CNI, ingress/egress, identity/RBAC, storage, autoscaling, upgrades, monitoring, and backup/DR** into one cohesive system.

What determines architectural quality is not the count of Kubernetes components, but the ability to **deploy the right versions, protect data, scale with load, handle node/zone failures, recover from incidents, and control costs**. These decisions establish a solid foundation for upcoming AKS lessons on workload deployment and cluster operations on Azure.
