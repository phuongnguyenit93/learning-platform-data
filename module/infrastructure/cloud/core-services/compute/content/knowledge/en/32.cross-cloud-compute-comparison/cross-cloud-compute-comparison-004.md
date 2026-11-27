# Comparing Container Runtime Models and Server Management Responsibilities

Containers package an application and its dependencies into an image that runs consistently across environments. However, packaging as a container does not automatically eliminate server management responsibilities. If containers run directly on VMs managed by the operations team, that team still has to update the OS, runtime, networking, and capacity. If using managed Kubernetes or serverless containers, the provider manages more of the control plane, nodes, or execution infrastructure; the customer remains responsible for the image, application, data, access permissions, and workload configuration.

A **container runtime model** describes how containers are deployed, scheduled, networked, scaled, and replaced. **Server management responsibility** defines who operates the hardware, hypervisor, host OS, worker nodes, container runtime, control plane, and application layers.

In **CLOUD_CORE_SERVICES_COMPUTE**, it is necessary to distinguish between self-managed containers on VMs, managed container orchestration, managed Kubernetes with customer-managed nodes, Kubernetes with provider-managed compute, and serverless containers. Higher degrees of management usually reduce node and cluster administration work, but they do not shift all security, data, availability, and application operations responsibilities onto the provider.

## 1. Containers Do Not Equal Managed Compute

A container is an OS-level process packaging and isolation mechanism. An image can run on:

- VMs created and managed by your own team.
- VMs inside a managed Kubernetes cluster.
- A container orchestration service managed by a cloud provider.
- A serverless platform that takes an image and provisions compute automatically.

Therefore, the critical question is not simply "does the application run in containers?", but "who is responsible for each layer from the server up to the application?"

### 1.1. Layers in a Container Platform

| Layer | Components | Example Responsibilities |
| --- | --- | --- |
| Physical infrastructure | Datacenter, servers, network fabric, storage | Providing hardware and power |
| Virtualization | Hypervisor or isolation boundary | Creating and isolating compute |
| Host/guest OS | Kernel, packages, security patches | Updating the OS running containers |
| Container runtime | containerd, CRI-O, or equivalent runtime | Pulling images, creating containers, managing lifecycle |
| Orchestration/control plane | Scheduler, API server, controllers, service scheduler | Scheduling, maintaining desired state, managing services |
| Worker/node | CPU, RAM, disk, network, and agents | Providing execution capacity |
| Container image | Base image, runtime, dependencies | Building, scanning, versioning, and publishing |
| Application | Code, API, configuration, health endpoints | Executing business logic and handling requests |
| Data/dependencies | Databases, caches, queues, object storage | Storing data, backups, and consistency |
| Operations | Monitoring, alerts, incidents, DR, cost | Ensuring SLOs and continuous operations |

A provider may manage certain layers without implicitly managing all remaining layers. The exact boundary depends on the service, deployment mode, contract, and chosen configuration.

### 1.2. Shared Responsibility

Shared responsibility is the model dividing obligations between the cloud provider and the customer. The provider is responsible for securing and operating the infrastructure underlying its services; the customer is responsible for configuring and using those services securely.

For example, the provider may patch the Kubernetes control plane, while the customer must still:

- Choose secure images and update dependencies.
- Configure RBAC and workload identity.
- Restrict network access.
- Protect secrets and data.
- Configure replicas, autoscaling, readiness, and disruption policies.
- Monitor application errors and handle incidents.

Never interpret the word "managed" to mean the provider will design your architecture, recover your data, or guarantee that every workload meets your SLOs.

## 2. Common Container Runtime Models

Models can be categorized by their level of abstraction and how much server infrastructure the customer manages.

### 2.1. Self-Managed Containers on VMs

The team provisions VMs, installs a container runtime, configures networking and storage, and deploys containers using Docker, Podman, or similar tools. Container scheduling and replacement may be handled by scripts, systemd, or a self-built platform.

Characteristics:

- High control over OS, kernel, runtime, and networking.
- Leverages existing VM operational expertise.
- The team must patch the guest OS and container runtime.
- Must build or operate mechanisms for deployment, restarts, health checks, scaling, and service discovery.
- Each VM can become a single point of failure or bottleneck without fleet management.

This model suits small workloads, specialized software, or teams needing host-level control. As service and VM counts grow, operational overhead can escalate rapidly.

### 2.2. Managed Container Orchestration on VMs

An orchestration service manages desired state, task/service placement, health, and container replacement. Compute can run on customer-managed VMs or provider-allocated capacity.

Examples:

- Amazon ECS with EC2 capacity providers: AWS manages the ECS control plane; the customer still manages EC2 capacity and the node OS per configuration.
- Amazon ECS with AWS Fargate: the provider manages server infrastructure for tasks; the customer declares tasks, images, IAM, networking, and resources.
- Similar managed container services can offer service schedulers, rollouts, and load balancer integration.

Orchestration removes the burden of managing individual containers, yet node responsibilities may still belong to the customer if a VM-backed model is chosen.

### 2.3. Managed Kubernetes with Customer-Managed Nodes

The provider operates the Kubernetes control plane—such as the API server, scheduler, and controller manager. The customer creates or configures worker nodes/node pools, selects instance types, and manages workloads and much of cluster operations.

Common examples:

- Amazon EKS with managed node groups or self-managed nodes.
- Azure Kubernetes Service (AKS) with node pools.
- Google Kubernetes Engine (GKE) Standard with node pools.

A "managed control plane" does not mean all nodes are provider-operated. Depending on the product, the provider may supply node images, node auto-upgrades, or automation tools, yet the customer must still select policies, validate rollouts, and manage workload compatibility.

### 2.4. Managed Kubernetes with Higher-Managed Compute

Some modes reduce worker node management responsibilities:

- GKE Autopilot manages much of node configuration and operations while enforcing workload policies and constraints.
- Amazon EKS Fargate runs pods on AWS-managed compute within supported profiles and workload types.
- Certain managed Kubernetes services offer modes that automate node provisioning, upgrades, or scaling.

Customers still manage Kubernetes workloads, images, resource requests, identities, network policies, data, and application behavior. Host customization or privileged daemon capabilities may be restricted.

### 2.5. Serverless Container/Application Platforms

The customer provides a container image or source artifact and configures CPU/RAM, concurrency, networking, and scaling. The provider manages most of the server infrastructure, runtime platform, and capacity provisioning.

Examples:

- Google Cloud Run.
- Azure Container Apps.
- AWS App Runner.
- AWS ECS on Fargate for container tasks/services without managing EC2 nodes.

Some platforms support scale-to-zero, request-based scaling, or event-driven scaling. In exchange, customers must account for cold starts, execution/request timeouts, concurrency, networking, persistent storage, and runtime constraints.

## 3. Quick Model Comparison

| Model | Who Manages Servers/OS? | Who Manages Orchestration? | Host Control | Customer Operational Tasks |
| --- | --- | --- | --- | --- |
| Self-managed containers on VMs | Customer manages guest OS and runtime | Customer operates or builds | High | VMs, patching, runtime, deployments, health, scaling, networking |
| ECS on EC2 or equivalent model | Customer manages nodes/VMs; provider manages service control plane | Provider manages scheduler/service | Medium to high | EC2 capacity, node patching, tasks, images, IAM, networking |
| Managed Kubernetes Standard | Provider manages control plane; node responsibility depends on config | Provider manages control plane; customer manages workloads and many policies | High on workload/node config | Node pools, upgrade policies, cluster add-ons, workloads, security |
| Managed Kubernetes with serverless/Autopilot compute | Provider manages much of nodes/capacity | Provider manages control plane; customer declares workloads | Lower | Workloads, resource requests, policies, data, IAM, networking |
| Serverless container platform | Provider manages hosts and capacity | Provider manages runtime/service orchestration | Low | Images, app, config, identity, data, SLOs, and service limits |

Management level is not a binary scale. One service may manage the control plane while leaving nodes to the customer; another may manage nodes while still requiring the customer to update images and dependencies. Always review the responsibility matrix for the exact mode chosen.

## 4. Layer-by-Layer Responsibility Matrix

The table below illustrates general patterns. "Provider" means the cloud provider operates that service infrastructure layer; "Customer" means the customer must configure, monitor, or update that part. Some layers are shared responsibilities.

| Layer | VM + Self-Managed Containers | Managed Kubernetes with Node Pools | Serverless Containers |
| --- | --- | --- | --- |
| Datacenter and hardware | Provider | Provider | Provider |
| Hypervisor/host virtualization | Provider | Provider | Provider |
| Guest/worker OS | Customer | Shared per node mode and upgrade policy | Provider |
| Container runtime on nodes | Customer | Provider or shared per service/node mode | Provider |
| Kubernetes/control plane | Customer if self-installed | Provider | Provider does not expose Kubernetes to users |
| Worker capacity | Customer creates and scales VMs | Shared: customer configures node pools, provider may assist management | Provider allocates per service |
| Container image | Customer | Customer | Customer |
| Application code/runtime dependencies | Customer | Customer | Customer |
| Application configuration | Customer | Customer | Customer |
| IAM/workload identity | Shared | Shared | Shared |
| Networking and firewalls | Shared | Shared | Shared |
| Data and databases | Customer or separate data services | Customer or separate data services | Customer or separate data services |
| Data backup/restore | Customer configures | Customer configures | Customer configures |
| Application observability | Customer | Customer | Customer |
| Workload availability | Customer designs | Customer designs | Customer designs within platform limits |
| Patching dependencies in images | Customer | Customer | Customer |
| Patching nodes/control plane | Customer | Shared per service | Provider for underlying host/runtime |

The provider operating a layer does not mean the customer can ignore it. For example, the provider may replace a failed node, but the application still needs readiness probes, graceful shutdown, sufficient replicas, and externalized data.

## 5. Cross-Provider Comparison

### 5.1. AWS

| Model | Provider Manages | Customer Manages |
| --- | --- | --- |
| EC2 + Docker/Podman | Datacenter, servers, and hypervisor | Guest OS, runtime, deployments, scaling, health, networking, and data |
| ECS on EC2 | ECS control plane and service scheduler | EC2 instances/capacity, node OS, task definitions, images, IAM, networking |
| ECS on Fargate | Server infrastructure and runtime capacity for tasks | Task definitions, images, CPU/RAM, IAM, networking, scaling, and application |
| EKS on EC2 | Kubernetes control plane | Node pools/EC2, node upgrade policies, add-ons, workloads, policies, and data |
| EKS Fargate | Control plane and compute hosts for supported pods | Pod specs, images, profiles, IAM, networking, workloads, and data |

ECS is AWS's container orchestration service, not Kubernetes. EKS provides a managed Kubernetes control plane. Fargate is a compute option that runs tasks/pods without requiring customers to manage EC2 hosts for eligible workloads.

With EKS, managed node groups assist with node lifecycle management, yet customers still choose configurations, upgrade schedules, capacity, and verify compatibility. Fargate carries constraints compared to EC2 nodes, such as host customization options and supported workload types.

### 5.2. Microsoft Azure

| Model | Provider Manages | Customer Manages |
| --- | --- | --- |
| VM + container runtime | Datacenter and hypervisor | Guest OS, runtime, orchestration, scaling, images, and apps |
| AKS | Kubernetes control plane and selected managed features | Node pool policies, workloads, images, identity, networking, data, and upgrade config |
| AKS Automatic or equivalent automated modes | More of cluster/node lifecycle depending on mode | Workloads, images, app security, data, SLOs, and remaining policies |
| Azure Container Apps | Underlying cluster/container runtime infrastructure and scaling | Container images, app config, identity, ingress, scaling rules, and data |

AKS can automate node image upgrades and cluster upgrades by policy, though customers must still inspect disruptions, PDBs, compatibility, and workload readiness. Azure Container Apps abstracts the underlying Kubernetes cluster; customers focus more on container apps, revisions, ingress, and scaling.

### 5.3. Google Cloud

| Model | Provider Manages | Customer Manages |
| --- | --- | --- |
| Compute Engine VM + container runtime | Datacenter and hypervisor | Guest OS, runtime, orchestration, images, apps, and networking |
| GKE Standard | Kubernetes control plane and managed service | Node pools, workloads, images, policies, data, and many cluster settings |
| GKE Autopilot | Control plane and much of node provisioning/management | Workloads, images, resource requests, IAM, network policies, and data |
| Cloud Run | Host, runtime platform, and capacity provisioning | Images, apps, config, identity, ingress, concurrency, min/max instances, and data |

GKE Standard offers higher control over clusters and nodes. GKE Autopilot reduces node operational work while enforcing workload and resource policies/constraints. Cloud Run focuses on deploying containers as services/jobs at a higher abstraction than Kubernetes.

### 5.4. How to Read Comparison Tables

Do not compare solely by product names. Compare matching modes:

- Kubernetes Standard with self-managed nodes is not equivalent to Autopilot.
- ECS on EC2 is not equivalent to ECS on Fargate.
- AKS node pools are not equivalent to Azure Container Apps.
- GKE Standard is not equivalent to Cloud Run.

Each mode has different scopes for patching, scaling, networking, storage, observability, and quotas.

## 6. Who Is Responsible for Patching and Upgrades?

Patching is a major differentiator between VM-backed models and serverless containers.

### 6.1. VM + Self-Managed Containers

The customer is responsible for:

- Patching the guest OS and kernel.
- Updating the container runtime.
- Updating security and monitoring agents.
- Replacing base images and dependencies inside container images.
- Testing compatibility before release.
- Scheduling reboots or VM replacements.
- Tracking unpatched VMs.

A new application image does not automatically patch the host OS. Conversely, patching the host OS does not update dependencies packaged inside the image.

### 6.2. Managed Kubernetes

The provider usually manages the control plane as a service. Worker node responsibility depends on the node mode:

- Self-managed nodes: the customer owns most of the node lifecycle.
- Managed node groups: the provider supplies mechanisms to create/upgrade nodes; the customer configures and monitors them.
- Serverless/Autopilot compute: the provider manages most of the host/node layer; the customer manages workloads and images.

The customer must still:

- Upgrade API versions and add-ons per compatibility matrices.
- Update application images.
- Check for deprecated APIs.
- Test PDBs, topology spread, and rolling updates.
- Ensure workloads do not depend on specific hosts.

### 6.3. Serverless Containers

The provider manages the host OS and most of the runtime platform. The customer must still update:

- Base images.
- Runtimes and application libraries.
- Vulnerable dependencies.
- Certificates and secrets throughout their lifecycle.
- Code, configuration, and policies.

You cannot skip patching simply because nodes are hidden. An outdated image can still contain exploitable libraries.

## 7. Who Is Responsible for Scaling and Capacity?

### 7.1. Self-Managed Containers on VMs

The customer must coordinate:

- Scaling the number of VMs.
- Scaling the number of containers per VM.
- Load balancing and service discovery.
- CPU/RAM/disk/network capacity planning.
- Quotas and per-zone placement.
- Draining containers before terminating VMs.

If VMs lack capacity, containers cannot be scheduled simply by raising replica counts.

### 7.2. Managed Kubernetes

HPA adjusts pod counts; the node autoscaler or node provisioning controller adds nodes when needed. The customer must configure:

- CPU/memory requests and limits.
- Min/max replicas.
- Node pool min/max and instance types.
- Quotas, subnet IPs, and zone capacity.
- Pod topology, affinity, and disruption policies.
- Appropriate scaling metrics.

HPA does not create nodes directly and cannot guarantee the cloud provider has capacity. If node pools hit max or quotas run dry, pods can stay Pending.

### 7.3. Serverless Containers

The provider typically allocates compute automatically based on requests, events, or concurrency within service limits. The customer still configures:

- Min/max instances or task counts.
- Concurrency per instance.
- CPU/RAM.
- Request timeouts or execution limits.
- Queue/event triggers and scaling rules.
- Quotas and maximum scale.

Automatic scaling does not mean infinite capacity. Cold starts, concurrency limits, regional quotas, or downstream bottlenecks can still slow down or fail requests.

## 8. Networking and Service Discovery

The more managed the model, the fewer node-networking details are exposed, yet the customer must still configure traffic paths.

| Component | Self-Managed VM/Containers | Managed Kubernetes | Serverless Containers |
| --- | --- | --- | --- |
| Public entry point | Customer provisions LB/reverse proxy | Ingress/Gateway/LB per configuration | Service URL or managed ingress |
| Service discovery | Self-managed DNS/registry | Kubernetes Service/DNS | Service name or platform endpoint |
| Network isolation | VPC, subnets, firewalls, host rules | VPC, security groups, CNI, NetworkPolicy | VPC connector/private networking per service |
| Pod/container IP | Customer manages network plugin or host ports | Platform/CNI manages | Typically abstracted away |
| Egress control | Firewalls/NAT/routes | VPC, network policies, and egress gateways | Egress settings, VPC integration, and policies |
| TLS | Customer configures proxy/certificates | Ingress/Gateway/service mesh | Managed certificates or gateway depending on service |

Do not assign public IPs directly to individual containers unnecessarily. Use a gateway or load balancer as the entry point, enforcing TLS, authentication, rate limiting, and network segmentation.

## 9. Storage and Data

Containers typically have a writable layer tied to the container lifecycle. When a container is deleted, data in that layer can be lost. This is especially critical when migrating from traditional VMs to managed containers.

### 9.1. Ephemeral Storage

Suitable for:

- Temporary files.
- Regenerable caches.
- Job scratch space.
- Recomputable intermediate artifacts.

Do not use it for unique business data or sessions that must survive restarts.

### 9.2. Persistent Storage

Options include:

- Managed databases.
- Object storage.
- Shared file storage.
- Persistent volumes/block storage.

In Kubernetes, PersistentVolumes and StorageClasses provide volume abstractions. For serverless containers, volume mounting capabilities and storage semantics depend on the service; object storage or managed databases are usually easier to decouple from instance lifecycles.

### 9.3. Backup and Recovery

The provider may protect underlying storage infrastructure, yet the customer must still define:

- Which data requires backups.
- Retention and encryption.
- RPO/RTO.
- Point-in-time recovery.
- Restore testing.
- Backup access permissions and KMS keys.

Do not mistake provider service availability guarantees for backups against accidental deletion, corruption, or operator error.

## 10. Security and Identity

### 10.1. Host Security

With VM-backed containers, the customer bears greater responsibility for the guest OS, SSH access, host firewalls, runtime sockets, kernel patches, and security agents.

With serverless containers, the provider manages the host and base runtime, while the customer remains responsible for securing images, application processes, identities, secrets, and networking.

### 10.2. Workload Identity

Do not embed long-lived cloud access keys into images or static environment variables. Use workload identity, task roles, managed identities, or service accounts depending on the platform.

Each workload should follow least privilege:

- Read only the exact secrets required.
- Access only necessary databases/schemas or buckets.
- Publish/consume only designated queues.
- Separate production identities from test environments.
- Enforce proper auditing and rotation.

### 10.3. Container Image Security

The customer is responsible for:

- Using maintained base images.
- Scanning images and dependencies.
- Pinning versions/digests.
- Running as non-root whenever possible.
- Dropping capabilities and avoiding privileged mode.
- Never mounting host sockets or unnecessary hostPaths.
- Signing images or verifying provenance per organizational policy.

Managed platforms do not automatically fix vulnerable packages inside application images.

### 10.4. Cluster and Application Policies

With Kubernetes, customers must also configure RBAC, admission policies, NetworkPolicies, Pod Security, and secret access. With serverless containers, these policies may live in service IAM, VPC settings, ingress, and execution configuration.

Regardless of model, business authorization must still be enforced inside the application or a trusted gateway; private networking does not replace authentication.

## 11. Availability and Recovery Responsibilities

Managed services can raise control plane or compute infrastructure availability, yet applications must still be designed to keep serving when replicas or zones fail.

### 11.1. Replicas and Failure Domains

The customer must decide:

- Minimum replica count.
- Distribution across nodes/zones.
- Readiness and liveness probes.
- Graceful shutdown.
- PDBs or equivalent disruption policies.
- Autoscaling and capacity buffers.

If all replicas sit in a single zone, a managed control plane will not automatically make the workload survive a zone outage.

### 11.2. Dependency Availability

Check databases, caches, queues, DNS, identity providers, secret managers, KMS, and object storage. An API may have healthy containers yet fail requests if a key dependency is down.

### 11.3. DR and Failover

The customer must define:

- Backup/replication strategies.
- Recovery regions and networking.
- Image/artifact availability.
- Quotas and capacity.
- Secrets, certificates, and identities.
- Traffic cutover and DNS.
- Actual RPO/RTO verified through drills.

Providers supply multi-zone or multi-region building blocks, but customers must configure and validate recovery procedures.

## 12. Observability and Operations

Higher management reduces host visibility without eliminating the need for application observability.

| Signal | Self-Managed VM/Containers | Managed Kubernetes | Serverless Containers |
| --- | --- | --- | --- |
| Host metrics | Customer installs agents and collects | Integrated node metrics or agents | Host metrics are usually abstracted |
| Container metrics | Runtime/cAdvisor or agents | Metrics API, Prometheus, or managed services | Platform request, instance, and execution metrics |
| Application metrics | Customer instruments | Customer instruments | Customer instruments |
| Distributed tracing | Customer configures | Customer configures | Customer configures |
| Platform events | VM/system logs | Kubernetes events and audit logs | Service events and execution logs |
| Alerts/SLOs | Customer defines | Customer defines | Customer defines |

Track:

- Request rate, error rate, and p95/p99 latency.
- CPU, memory, throttling, and restarts.
- Queue depth and dependency latency.
- Desired/actual replicas and pending workloads.
- Startup times, cold starts, and scaling events.
- Cost per request/job and idle capacity.

## 13. Costs and Billing Models

### 13.1. VM-Backed Containers

Typically billed by VM/node runtime, disks, networking, and accompanying services. If containers are idle while VMs keep running, compute charges continue.

The advantage is optimizing utilization by packing multiple containers onto nodes. The drawback is provisioning headroom and managing nodes.

### 13.2. Managed Kubernetes

Costs can include:

- Worker nodes or serverless pod capacity.
- Managed control plane fees if charged by the service.
- Disks, load balancers, NAT, and egress.
- Registries, logging, monitoring, and add-ons.
- Platform engineering staffing.

Sharing a cluster across multiple workloads amortizes base costs better. A dedicated cluster for one small workload can introduce substantial overhead.

### 13.3. Serverless Containers

Can be billed by vCPU-seconds, GB-seconds, requests, task duration, minimum instances, or provisioned capacity. Idle costs can be low with scale-to-zero, though supporting services like databases, gateways, storage, and logging still incur charges.

### 13.4. Compare Costs Under Equal Conditions

Never compare raw VM price to serverless execution price while ignoring:

- Multi-zone and standby capacity.
- Databases, storage, and networking.
- Observability and security.
- Minimum instances/concurrency.
- Operational staffing costs.
- Migration and vendor-specific integration.

Calculate monthly/annual TCO and cost per successful request/job at the same SLO.

## 14. Needs-Based Selection Matrix

| Need | Typically Suitable Model | Rationale and Trade-Offs |
| --- | --- | --- |
| Need control over kernel, host, and specialized agents | Containers on VMs | High control, but self-operated OS/runtime |
| Many microservices needing Kubernetes APIs | Managed Kubernetes Standard | Rich orchestration features, requires platform skills |
| Want Kubernetes with less node management | Autopilot/serverless pod mode | Reduces node ops, fewer host customization options |
| Simple container services, HTTP/event-driven | Serverless container platform | Minimal cluster/node management, must accept service limits |
| Long-running batch requiring custom nodes/drivers | VM-backed or managed Kubernetes node pools | Better hardware and runtime control |
| Intermittent traffic that can scale to zero | Serverless containers | Low idle cost, requires evaluating cold starts |
| Steady 24/7 workloads sharing platform services | Managed Kubernetes or node-pool orchestration | Higher utilization potential, must factor platform overhead |
| Phased transition away from legacy VMs | Containers on VMs then managed orchestration | Enables staged migration |

These are directional guidelines, not rigid rules. Benchmarks, security mandates, quotas, regional availability, and team skills can shift the choice.

## 15. Example: The Same API Across Three Models

Suppose an Orders API needs at least 3 replicas, scales up to 20 replicas, accesses a managed database and object storage, and requires zero-downtime rolling deployments.

### 15.1. Option A: Containers on VMs

The team provisions a VM fleet, installs a runtime, deploys containers via automation, and places a load balancer in front.

Customer responsibilities:

- Guest OS, patches, and runtime.
- VM scaling, health monitoring, and replacement.
- Container deployment and restarts.
- Networking/firewalls and service discovery.
- Log/metric agents and configuration backups.

The team retains high control but must operate many layers.

### 15.2. Option B: Managed Kubernetes

The team creates a cluster, node pools, Deployment, Service, HPA, PDB, and ingress.

The provider manages the control plane; node responsibility depends on node pool type. Customer responsibilities:

- Node pool configuration and upgrade policies.
- Container images, Deployments, and rollouts.
- Resource requests/limits, HPA, and topology.
- RBAC, network policies, and workload identity.
- Database connection budgets and application SLOs.

The platform removes control plane administration but demands Kubernetes expertise.

### 15.3. Option C: Serverless Containers

The team deploys the image to the service and configures CPU/RAM, concurrency, min/max instances, ingress, and identity.

The provider manages hosts and capacity provisioning. Customer responsibilities remain:

- Stateless API and graceful request handling.
- Images, dependencies, and vulnerability patching.
- IAM, secrets, data, and network configuration.
- Concurrency, timeouts, scaling limits, and cold starts.
- SLOs, observability, and downstream capacity.

The team manages far fewer servers but must design around platform limits and semantics.

## 16. Workflow for Migrating from VMs to Managed Containers

1. **Build an inventory:** application, OS dependencies, ports, file paths, daemons, licenses, and data.
2. **Classify state:** which sessions, files, caches, and jobs are currently bound to VMs.
3. **Externalize state:** move durable data to databases, object storage, caches, or queues.
4. **Package images:** pin dependencies, set up build pipelines, scan, and version.
5. **Select a managed model:** Kubernetes, task orchestration, or serverless containers.
6. **Define a responsibility matrix:** assign who patches nodes, images, runtimes, networking, secrets, and backups.
7. **Design health/lifecycle:** readiness, startup, liveness, graceful shutdown, and draining.
8. **Design capacity:** resource requests/limits, concurrency, HPA, and quotas.
9. **Design security:** identity, RBAC, network policies, image policies, and auditing.
10. **Run a pilot deployment:** staging, canary, or traffic shadowing.
11. **Test failures:** terminate replicas, drain nodes, simulate dependency outages, and test zone failures within test scope.
12. **Measure TCO/SLOs:** latency, errors, availability, utilization, cost, and operational effort.
13. **Migrate in waves:** keep rollback plans and parallel run windows.
14. **Update runbooks:** transition operational ownership, alerts, escalation paths, and patch schedules.

## 17. Common Misconceptions

- Assuming containers eliminate OS management altogether.
- Assuming managed Kubernetes means the provider manages all worker nodes.
- Assuming serverless containers never require image patching.
- Assuming the provider handles application data backups automatically.
- Assuming HPA can allocate capacity beyond quotas or when a zone runs out of resources.
- Assuming private networks replace authentication.
- Assuming a managed control plane guarantees multi-zone workload resilience.
- Assuming portable container images imply identical platform behavior everywhere.
- Comparing raw compute prices while ignoring control planes, logging, egress, and staffing.
- Failing to check runtime, concurrency, timeout, or storage limits of serverless platforms.

## 18. Pre-Production Responsibility Checklist

**Compute and Servers**

- [ ] Who manages VMs/worker nodes and node pools?
- [ ] Who updates the guest OS, kernel, and container runtime?
- [ ] Who configures autoscaling, quotas, and capacity?
- [ ] Who handles node draining, reboots, and replacement?

**Platform and Workloads**

- [ ] Who manages the control plane, cluster versions, and add-ons?
- [ ] Who builds, scans, signs, and updates container images?
- [ ] Who manages deployments, rollouts, rollbacks, and health probes?
- [ ] Who manages service discovery, ingress, and load balancing?

**Security and Data**

- [ ] Who provisions workload identities and reviews IAM?
- [ ] Who manages secrets, certificates, and rotation?
- [ ] Who configures network isolation and egress?
- [ ] Who handles data backups, restores, encryption, and retention?

**Operations**

- [ ] Who owns SLOs, alerts, and on-call?
- [ ] Who handles incidents across host, platform, and application layers?
- [ ] Who runs failover/DR drills and measures RPO/RTO?
- [ ] Who tracks costs, licenses, and shared platform overhead?
- [ ] Do runbooks clearly define escalation to the provider when issues lie in the managed service?

## 19. Operational Principles

1. **Read the service model accurately:** containers on VMs, managed Kubernetes, and serverless containers have distinct responsibility boundaries.
2. **Separate control plane from worker nodes:** provider control plane management does not eliminate customer node duties.
3. **Distinguish host patching from image patching:** providers may patch hosts while customers must still update application dependencies.
4. **Clarify shared responsibility:** IAM, networking, data, backups, SLOs, and observability still require customer configuration.
5. **Calculate capacity end-to-end:** autoscalers cannot bypass quotas or guarantee downstream dependency capacity.
6. **Design replaceable workloads:** statelessness, readiness, and graceful shutdown unlock managed orchestration benefits.
7. **Evaluate platform limits:** cold starts, concurrency, timeouts, storage, and runtime constraints shape architecture.
8. **Calculate full TCO:** nodes, control planes, networking, logging, security, licenses, and staffing.
9. **Test real-world responsibilities:** drill node upgrades, image updates, scale-outs, failovers, and restores.
10. **Maintain clear ownership:** every layer needs an owner, runbook, alerts, and escalation path.

Container runtime models differ primarily in their abstraction level and how much underlying infrastructure the provider operates. Self-managed containers on VMs offer maximum control but require managing servers, runtimes, and orchestration. Managed Kubernetes reduces control plane toil while nodes and workloads still demand configuration, updates, and monitoring. Serverless containers remove much of host and capacity provisioning work, while responsibility for images, applications, data, identity, networking, and SLOs remains with the customer. By mapping responsibilities layer by layer rather than looking only at service names, organizations can select the model that matches their operational capacity, control requirements, and workload costs.
