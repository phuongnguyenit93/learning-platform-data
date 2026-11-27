# Choosing Virtual Machines, Containers, Serverless, and Application Platforms

When deploying applications in the cloud, compute choices determine **who manages the servers, operating system, and runtime; how workloads are packaged and scaled; how the application recovers when an instance fails; and how many infrastructure layers the team must operate**. Virtual machines (VMs), containers, serverless, and managed application platforms can all run a web application, API, or background task, but they provide different levels of control and responsibility.

In the **CLOUD_ARCHITECTURE** module, compute decisions must stem from business requirements and system constraints. Reliability, security, scalability, performance, cost, and operational capability must be evaluated together through a Well-Architected mindset. No technology is automatically better in every situation; the right model is the one that meets workload and service objectives at a level of complexity the team can sustain.

## 1. Four Compute Models and Levels of Responsibility

| Model | How It Works | What Users Typically Manage | What Providers Typically Manage |
| --- | --- | --- | --- |
| **Virtual Machine (VM)** | A virtual computer with its own CPU, RAM, disk, and operating system | OS, patches, runtime, application, agents, scaling, and HA by design | Physical host, hypervisor, datacenter infrastructure |
| **Container** | Packages application and dependencies into an image, run by a container runtime/orchestrator | Image, configuration, resource requests/limits, orchestration policies, application, and workload security | Node/runtime infrastructure or control plane depending on managed/self-managed model |
| **Serverless compute** | Runs code or containers per request/event/job with server infrastructure abstracted away | Handler/image, configuration, permissions, concurrency, timeout, data, and observability | Provisioning and most host management; limits vary by service |
| **Managed application platform** | Deploys applications to an environment with pre-provided runtime, routing, scaling, and health management | Code/artifact, configuration, supported runtime version, and deployment policies | Many parts of OS, platform runtime, ingress, and lifecycle |

Responsibility boundaries vary by product. **Using VMs does not mean managing physical hardware**, using containers does not automatically mean Kubernetes, serverless does not mean there are no servers, and a managed platform does not guarantee every patch or application dependency is automatically handled.

### A Spectrum of Control and Responsibility

~~~mermaid
flowchart LR
    VM["VM"] --> CON["Container platform"]
    CON --> F["Serverless container / function"]
    F --> PAAS["Managed application platform"]
    subgraph CONTROL["Abstraction trend"]
      A["More OS / network / runtime control"]
      B["Less host management and patching"]
      A --> B
    end
~~~

The diagram only illustrates a general trend, not an absolute scale. Managed containers can still offer very deep networking control; some serverless containers still require selecting CPU/RAM, VPC, image, concurrency, and scaling policies. Always read the specific service's responsibility model and limits before designing.

## 2. Virtual Machines: Deep Control for Workloads Needing Dedicated Environments

A VM provides a guest operating system (guest OS) with its own CPU, RAM, volumes, network interfaces, and administrative mechanisms. Application teams can install arbitrary runtimes, run long-lived processes, system agents, or legacy software. This is a useful choice when a workload needs OS-level access, special system libraries, or specific network/disk configurations.

~~~mermaid
flowchart TB
    subgraph PHYSICAL["Cloud infrastructure"]
      H["Physical host / hypervisor"]
      subgraph VM1["Virtual machine"]
        OS["Guest OS"]
        RT["Runtime + libraries"]
        APP["Application"]
        OS --> RT --> APP
      end
      subgraph VM2["Another virtual machine"]
        OS2["Guest OS"]
        APP2["Another application"]
        OS2 --> APP2
      end
      H --> VM1
      H --> VM2
    end
~~~

### Advantages

- **Freedom to configure the environment:** choose the OS, runtime version, packages, and agents as required.
- **Legacy software compatibility:** suitable for applications requiring daemons, drivers, native libraries, or traditional installation procedures.
- **Long-lived resources:** suited for continuously running workloads or those needing predictable performance when properly sized and placed.
- **Familiar operational boundaries:** teams can leverage existing OS, monitoring, hardening, and automation expertise.

### Costs and Responsibilities

- Operations teams are typically responsible for **OS patching, SSH/RDP configuration, endpoint protection, secrets, host firewalls, logging, and backups**.
- Requires processes for golden image creation, vulnerability scanning, package inventory, license management, and key rotation.
- Must design load balancing, auto scaling, health checks, rolling replacement, and recovery when a VM or zone fails.
- A VM with configuration drift or left unpatched for a long time can become a risk point; increasing the number of VMs also increases patching and monitoring overhead.

### When Should You Choose VMs?

VMs are appropriate when applications require deep OS access, legacy workloads are hard to containerize, long-running processes need a specialized environment, licenses are tied to the OS, or commercial software requires a specific configuration. They are also a practical transition step when migrating legacy applications to the cloud before refactoring.

Do not choose VMs simply because they feel "easy to understand." If you have hundreds of small services requiring independent builds/deployments, managing individual OSes can increase operational overhead and slow down releases. Automated image pipelines, configuration management, and autoscaling can reduce the burden, but OS maintenance effort must still be accounted for.

## 3. Containers: Packaging Applications and Standardizing Execution

A container image packages application code along with the required runtime and libraries. Containers run as processes isolated at the OS kernel level via namespaces, cgroups, and other mechanisms; multiple containers typically share the host kernel. This difference matters when comparing containers with VMs: containers **do not have a separate guest OS kernel** in the way traditional VMs do.

~~~mermaid
flowchart TB
    subgraph HOST["A node / VM host"]
      K["Host OS + container runtime"]
      subgraph C1["Container A"]
        A1["App A + runtime/libs"]
      end
      subgraph C2["Container B"]
        B1["App B + runtime/libs"]
      end
      K --> C1
      K --> C2
    end
~~~

Containers keep artifacts close to the execution environment across laptops, CI, and production; image versions can be controlled and deployed reproducibly. However, containers do not inherently provide orchestration, service discovery, routing, scaling, or HA. Those capabilities come from the container platform and operational configuration.

### Container Orchestration

When there are many containers requiring scheduling, self-healing, rollouts, service discovery, and autoscaling, organizations can use an orchestration platform like Kubernetes or a managed container service. A cluster typically consists of a control plane coordinating desired state and worker nodes running workloads; with managed services, shared responsibilities depend on the specific service.

Key concepts to understand:

| Concept | Role |
| --- | --- |
| **Image** | Immutable artifact identified by tag/digest, containing the application and runtime components |
| **Registry** | Stores, controls access to, and distributes images |
| **Container** | A running instance of an image with specific configuration |
| **Pod/task** | Scheduling unit depending on the orchestrator; can hold one or more related containers |
| **Node/worker** | Compute machine providing CPU, RAM, network, and storage for workloads |
| **Deployment/service** | Defines replica counts, update strategies, and access endpoints per platform |
| **Autoscaler** | Adjusts replica or node counts based on metrics and policies |
| **Resource request/limit** | Declares requested resources and usage limits for a workload |

### Advantages

- **Consistent packaging:** reduces drift between build and runtime environments when images are properly built and controlled.
- **Higher resource density:** multiple workloads can co-exist on a node when properly limited and allocated.
- **Versioned deployment and rollback:** uses immutable images, replica-based rollouts, and health tracking.
- **Artifact-level portability:** the same image can run across compatible platforms, though networking and storage still differ.
- **Supports modularity:** APIs, workers, and jobs can be packaged separately, sharing a codebase while deploying independently.

### Operational Risks

- Orchestrators, networking, ingress, service meshes, storage, and observability introduce a significant operational surface.
- Overly permissive or privileged containers can weaken security boundaries.
- Stale images, vulnerable base images, secrets baked into images, and overly open registries are common risks.
- Misconfigured requests/limits can cause throttling, OOMKilled events, or resource contention.
- Persistent state in a container filesystem can be lost when the container is replaced; data must reside in appropriate volumes or storage services.

### When Should You Choose Containers?

Containers fit well when standardized packaging is needed, there are many services/workloads, deployments are frequent, runtime environments can be managed as code, and the team has platform capabilities. You can start with a managed container service to avoid operating the entire orchestrator yourself.

Kubernetes is not mandatory for a small API. A simpler container platform or managed app platform can eliminate significant configuration and operational work. Choose an orchestrator only when its scheduling, networking, policy, workload mix, or ecosystem capabilities are genuinely needed.

## 4. Serverless: Focusing on Code, Events, and Execution Units

Serverless is a cloud model in which the provider manages most of the provisioning and operation of the execution infrastructure. Developers deploy functions, containers, or jobs; the platform allocates resources based on configuration and load, scaling with events/requests and scaling down to low levels when idle. Some services charge per request, execution duration, or provisioned resources; exact billing varies by product.

**Serverless does not mean there are no servers.** Servers still exist, but users do not directly manage the host/OS. Users remain responsible for code, dependencies, IAM, data, concurrency limits, timeouts, observability, and failure design.

### Common Serverless Forms

| Form | Deployment/Trigger Unit | Example Workloads |
| --- | --- | --- |
| **Function-as-a-Service (FaaS)** | Function triggered by a request or event | Webhooks, file processing, event handlers |
| **Serverless container** | Container image run per request, job, or schedule | APIs, workers, batch tasks |
| **Serverless job/batch** | Single run with a defined start and end | Data imports, reporting, file conversion |
| **Managed event/workflow service** | Event or workflow step triggering tasks | Orchestrating async workflows, system integration |

### Advantages

- **Reduced host administration:** no need to maintain OSes and node pools in the traditional way (within the managed service's scope).
- **On-demand scaling:** automatically spins up execution instances as requests/events increase; some services scale to zero.
- **Usage-based pricing:** advantageous for sparse, bursty workloads or non-continuous jobs.
- **Event integration:** well suited for processing events from object storage, queues, schedulers, webhooks, and cloud platforms.
- **Faster time-to-market:** small teams can ship functionality without building a dedicated compute platform.

### Constraints to Plan For

- **Cold starts:** initializing an environment or waking from idle can add latency; impact depends on runtime, package size, configuration, and platform.
- **Time limits:** some functions have maximum timeouts; long jobs or continuous processes may require containers, jobs, or VMs.
- **Concurrency and quotas:** rapid scaling can open large numbers of database connections or exceed external service limits.
- **State and filesystem:** do not rely on memory or ephemeral filesystems to persist state across invocations.
- **Observability and debugging:** execution is distributed across requests/events, requiring correlation IDs, tracing, and structured logging.
- **Vendor coupling:** event schemas, runtimes, IAM, triggers, and workflows can tie into provider-specific APIs; evaluate portability and switching costs.
- **Cost under continuous load:** serverless is not automatically cheaper than containers/VMs if load is high, steady, and long-running.

### Event Processing Pattern

~~~mermaid
flowchart LR
    UPLOAD["Object upload"] --> EVENT["Storage event"]
    EVENT --> QUEUE["Queue"]
    QUEUE --> FN["Serverless handler"]
    FN --> OUT["Output object"]
    FN --> DB["Metadata database"]
    QUEUE --> DLQ["Dead-letter queue"]
~~~

In this example, an uploaded file emits an event, a queue absorbs bursts, and a handler processes the file and writes metadata. The design must account for **at-least-once** delivery, duplicate events, retries, DLQs, file size limits, timeouts, concurrency, and job replay mechanisms. Never assume an event arrives only once or a handler runs only once.

### When Should You Choose Serverless?

Serverless generally fits webhooks, event handlers, short tasks, irregular workloads, file processing, automation, and stateless APIs, provided timeout, latency, networking, and concurrency constraints align.

Do not force a multi-hour workflow into a time-limited function; split it into idempotent steps orchestrated by a workflow or job engine. For APIs requiring very consistent latency, always-warm workloads, large memory footprints, or long processing times, containers or VMs may be better suited after benchmarking.

## 5. Managed Application Platforms: Reducing Infrastructure Operations

A managed application platform provides a standardized path to deploy applications. Development teams typically push source/artifacts or container images to the platform and configure the runtime, environment variables, domains, TLS, scaling, and health checks; the platform handles part of the lifecycle, routing, and underlying servers.

These products are often called **Platform-as-a-Service (PaaS)** or managed app services, though their scope varies. Some support specific language runtimes while others accept containers; some automatically manage ingress and autoscaling while others require configuring networking, compute plans, or dedicated workers.

~~~mermaid
flowchart TB
    DEV["Source / image / artifact"]
    PLATFORM["Managed application platform"]
    ROUTE["Ingress / TLS / routing"]
    APP["Application instances"]
    SCALE["Health / autoscaling / rollout"]
    OBS["Logs / metrics"]
    DATA["Managed data services"]
    DEV --> PLATFORM
    PLATFORM --> ROUTE
    PLATFORM --> APP
    PLATFORM --> SCALE
    PLATFORM --> OBS
    APP --> DATA
~~~

### Advantages

- **Less infrastructure management:** teams focus more on the application, domain logic, and releases.
- **Simplified deployment path:** integrates source repositories/build pipelines, runtime configuration, and health checks per product.
- **Built-in capabilities:** domains, TLS, logging, autoscaling, staging slots, or deployment mechanisms depending on the platform.
- **Small teams can run production:** no need to build full container orchestration or OS automation from scratch.

### Trade-offs

- **Less environment control:** only supports specific runtimes, versions, OSes, and networking models.
- **Workload limitations:** long-running jobs, custom daemons, kernel modules, special protocols, or OS-level requirements may not fit.
- **Quotas and pricing models:** compute plans, workers, instances, network integration, and storage may be billed in different ways.
- **Portability:** depends on platform-specific configuration, APIs, deployment slots, runtimes, and integrated services.
- **Responsibility boundaries:** the provider manages the platform, but users must still patch application dependencies, protect secrets, manage IAM and data, configure ingress, and enforce access controls.

### When Should You Choose a Managed App Platform?

Suitable when web/API applications use a supported runtime, the team wants to minimize operations, production requires structured deploy/rollback workflows, and workloads do not require deep OS privileges. It is often a strong starting point for standard business applications, especially when there is no reason to operate a cluster yet.

If you need custom system agents, deep network customization, diverse workload scheduling, or dozens of services under unified policies, a container platform can offer better control. Decisions must be grounded in actual requirements—not biases that PaaS is "too simple" or Kubernetes is "more professional."

## 6. Comparison Across Architectural Criteria

| Criterion | VM | Container / Orchestrator | Serverless | Managed Application Platform |
| --- | --- | --- | --- | --- |
| **OS management** | Usually customer-managed guest OS | Depends on node model; managed services reduce node management | Provider manages most host/OS | Provider manages most platform/OS |
| **Runtime control** | Very high | High inside the image, constrained by host runtime/orchestrator | Limited to runtimes or images supported by the service | Limited to runtimes/versions offered by the platform |
| **Scaling** | VM/instance groups, may incur boot time | Replica/pod and node autoscaling | Per request/event/concurrency within quotas | Per instance/plan/autoscale features |
| **Long-running workloads** | Very well suited | Well suited | Depends on service limits; serverless jobs/containers may support | Depends on allowed durations and process types |
| **Bursty workloads** | Can scale but needs forecasting and warm capacity | Autoscaling, though constrained by node capacity | Often well suited if quotas/cold starts are acceptable | Depends on autoscale speed and minimum floors |
| **Operational complexity** | Significant OS and fleet management | Can be high if self-managing clusters | Low host management, but requires event/limit control | Usually lower for standard applications |
| **Portability** | OS/images depend on configuration but fairly flexible | Container images are relatively portable | Can depend on proprietary triggers, IAM, workflows, and runtimes | Depends on platform runtimes and APIs |
| **Cost model** | By instance, storage, network, and licenses | Nodes/clusters, workloads, storage, network | Requests, duration, provisioned capacity, network, and auxiliary services | Plans/instances, workers, storage, network, and integrations |
| **Typical use cases** | Legacy, OS-specific, specialized processes | Microservices, diverse APIs and workers | Event handlers, short jobs, bursty traffic | Standard web/APIs seeking low ops |

There is no absolute score for each cell. You must inspect actual provider capabilities: for instance, a managed container service can eliminate most cluster operations, while serverless containers can run longer jobs than traditional functions. Marketing names are not enough to determine technical limits.

## 7. Selecting Compute from Workload Characteristics

An informed decision starts by classifying the workload:

| Characteristic | Questions to Answer | Direction to Consider |
| --- | --- | --- |
| Execution time | Requests of a few hundred ms, jobs of several minutes, or continuous processes? | Functions for short tasks; containers/jobs or VMs for long processes |
| Load profile | Steady, time-of-day, seasonal, or seconds-long spikes? | Managed scaling, queues, scheduled capacity, or serverless |
| Resources | How much CPU, RAM, GPU, I/O, and network are needed? | Appropriate VM instance family or container resource profile |
| Environment | Which OS/runtime/version/native libraries are required? | VMs for deep OS needs; containers when images can be standardized |
| State | Are there local sessions, persistent files, transactions, or locks? | Externalize state to databases/caches/object storage/queues |
| Latency | Are p95/p99 targets strict? Do cold starts matter? | Benchmark warm/cold, keep minimum capacity, or choose always-on processes |
| Connectivity | Which VPC/private endpoints and inbound/outbound protocols are needed? | Verify platform network integration and quotas |
| Operations | Can the team manage OS/clusters/on-call? | Managed platforms reduce burden when they fit |
| Security | What are host permissions, workload identity, secrets, image, and patch needs? | Choose a control level matching threat model and compliance |
| Cost | Is load steady, are there idle periods, licenses, and egress? | Calculate TCO from the load profile, not a single hourly rate |

### Example Candidate Matrix

| Workload | Characteristics | Possible Starting Choice |
| --- | --- | --- |
| Stateless booking API | Steady load, low latency needed, frequent rollouts | Managed app platform or managed containers |
| Legacy system with special OS agent | Custom runtime/OS and long-running process | VM first, then evaluate containerization |
| Event-driven image resizing | Bursty load, independent jobs, retryable | Queue + serverless handler or container workers |
| Nightly reporting batch | Long job, clear schedule, checkpointing needed | Managed job/batch or containers/VMs depending on duration |
| Memory-intensive search service | Continuous workload, large index | Containers/VMs or managed search platform |
| Low-traffic webhook | Short requests, occasional spikes | Serverless function/container if latency fits |
| Multi-team Kubernetes platform | Many workloads, shared policy and scheduling requirements | Managed Kubernetes when benefits outweigh operational cost |

These are **candidates**, not conclusions; benchmarks, quotas, data, product features, and team skills determine the final choice.

## 8. Compute Sizing: From Measurements to Reserve Capacity

Choosing compute types before knowing the workload easily leads to over- or under-provisioning. Measure or estimate:

- **Throughput:** requests/sec, jobs/min, messages/sec, concurrent sessions.
- **CPU:** CPU-seconds/request or job; utilization at steady state and peak.
- **Memory:** working set, heap, native memory, caches, and peak allocation.
- **I/O:** IOPS, throughput, and latency for block/object storage and databases.
- **Network:** connection counts, bandwidth, packet rate, egress, and NAT limits.
- **Tail latency:** p95/p99, queue wait time, cold starts, and job completion time.
- **Availability headroom:** remaining capacity when losing an instance, node, or AZ.

### Preliminary CPU Calculation

For a workload with relatively steady CPU cost:

\[
\text{Required CPU cores}
\approx\frac{\lambda\times c}{u}
\]

Where \(\lambda\) is requests/second, \(c\) is CPU-seconds/request, and \(u\) is target CPU utilization (e.g., 0.60). This is a directional estimate for CPU capacity and excludes overhead, bursts, heavy/light request variance, memory pressure, and other limits.

**Example:** an API receives 240 RPS, each request using an average of 0.02 CPU-seconds. Target average CPU is under 60%:

\[
\frac{240\times0.02}{0.60}=8\text{ cores}.
\]

If the system must survive losing one of two AZs while maintaining peak load, each AZ must hold enough capacity for the target load or have an acceptable degradation plan. Placing 4 cores in each AZ leaves only 4 cores when one AZ is lost, failing the 8-core requirement unless other capacity is ready. Calculations must also be verified via load testing at SLO.

### Capacity Planning for Workers

For a queue:

\[
\text{Backlog growth/sec}\approx
\max(0,\lambda_{\text{arrival}}-\mu_{\text{processing}})
\]

If producers generate 80 jobs/s while workers complete 65 jobs/s, the backlog grows by 15 jobs/s, or 900 jobs/min. You must calculate drain time after a burst, maximum acceptable job age, scale-out time, and downstream quotas. Autoscaling solely on CPU can miss queue lag; autoscaling solely on queue depth can push workers past what the database or downstream providers can handle.

### Do Not Size on a Single Average

A system averaging 100 RPS but spiking to 1,000 RPS for 10 seconds may need warm capacity, admission control, or queues. P99 for heavy requests can diverge sharply from average CPU. Load test with representative data/payloads, warm/cold caches, read/write ratios, retries, dependency failures, and replica/AZ loss scenarios. Measure at the SLO threshold; high throughput that violates latency commitments is not usable capacity.

## 9. Scalability and Availability in Each Model

### VM

VMs typically scale by resizing or adding instances in a group behind a load balancer. Scale-out depends on boot time, configuration provisioning, image pulling, and warm-up. Use immutable images, health checks, multi-AZ placement, and graceful draining so instances can be replaced safely. One large standalone VM may be simple, but it creates a large failure domain; evaluate RTO if the host fails.

### Container

Orchestrators can scale replicas/pods based on CPU, memory, request metrics, or queues. However, distinguish between:

- **Horizontal scaling:** adding replicas.
- **Vertical scaling:** increasing CPU/RAM per replica or node.
- **Node scaling:** adding worker nodes when cluster capacity runs out.
- **Pod/task placement:** spreading workloads across nodes/AZs via topology constraints/anti-affinity as supported by the platform.

Liveness, readiness, and startup probes serve distinct semantics; overly aggressive probes can trigger restart storms when a dependency slows down. Resource requests/limits, disruption budgets, rollout strategies, and node quotas also impact availability. Even when the cluster control plane is managed, you must still ensure nodes, networking, storage, and applications are fault-tolerant.

### Serverless

Serverless can automatically spawn concurrency under load, but limits must be set to protect downstream systems. If a function scales to 1,000 concurrent invocations and each opens a DB connection, the database can exhaust its pool. Configure reserved/max concurrency, batching, queues, connection reuse, or suitable data access patterns. Check cold starts, throttling, retries, and DLQs when the platform cannot absorb an entire burst.

### Managed Application Platform

Platforms may manage health checks, instance replacement, routing, and autoscaling; understand the exact semantics: whether autoscale triggers on CPU, requests, queues, or schedules; how long capacity changes take; whether apps restart during scaling/maintenance; and whether deployment slots or rolling releases preserve connections. Do not assume multi-AZ HA is guaranteed if the configuration/plan has not enabled it or the product does not support it.

### Journey-Level Recovery Objectives

Availability is not just the count of healthy instances. When an instance is lost, open connections can reset; users may see errors even after the load balancer shifts traffic. Define **SLIs/SLOs** and error budgets, along with RTO/RPO per user journey, and test end-to-end failover. Transactions must not be lost or duplicated on client retries; data and sessions must be stored outside ephemeral local filesystems.

## 10. Security and Compute Responsibility Models

Compute choices alter the attack surface and what the team must protect.

| Layer | VM | Container | Serverless / Managed Platform |
| --- | --- | --- | --- |
| OS/host patching | Customer usually patches guest OS; cloud manages host/hypervisor | Managed nodes may be patched by provider; self-managed requires managing nodes; customer updates base images | Provider manages most host/OS within service scope; customer still patches dependencies/runtime packages in artifacts |
| Artifact | VM image, packages, and scripts | Container image, base image, registry | Function package or container image |
| Identity | VM role/managed identity and OS permissions | Workload identity/service account and container permissions | Execution role/function identity/platform identity |
| Secrets | Secret manager, file/memory injection, rotation | Secret manager or orchestrator secrets; never bake into images | Platform secret/config store and permission mechanisms |
| Network | Security groups/firewalls, subnets, host firewalls | Network policies, service ingress/egress, node boundaries | VPC integration, endpoints, ingress/egress within service limits |
| Runtime protection | EDR/agents, hardening, OS auditing | Image scanning, admission policies, runtime security | Dependency scanning, identity policies, platform controls |
| Logging | OS + application logs | Container stdout/stderr, node and orchestration events | Application logs, invocation/request metrics, and platform logs |

Key principles:

1. **Least privilege:** VM roles, workload identities, or function roles may only access required resources; never use default admin permissions.
2. **Trusted artifacts:** build from controlled sources, scan dependencies/images, sign artifacts when required by policy, and deploy by traceable digest/version.
3. **Keep secrets out of images and source:** use secret managers, short-lived identities, and rotation; avoid logging secrets.
4. **Clear patching and lifecycle ownership:** define who patches the OS, runtime, base images, and dependencies, along with vulnerability remediation SLAs.
5. **Minimal networking:** open only required ingress; control egress; encrypt connections to databases, queues, and external services.
6. **Workload isolation:** do not run privileged containers or mount unnecessary host paths; isolate sensitive workloads via separate nodes/plans/accounts when the threat model demands it.
7. **Durable data and backups:** never treat local ephemeral disks as the sole store for business data; restrict backup/restore permissions and test recovery.

Shared responsibility varies by service and management tier. A provider may patch the host without assuming responsibility for vulnerable libraries inside your application image. Read the service's compliance scope and operational responsibilities carefully before running sensitive data workloads.

## 11. Compute Cost and Total Cost of Ownership (TCO)

Comparing a VM's hourly price to a serverless per-request price is not enough. TCO must include:

- **Direct compute:** vCPU, RAM, instance hours, function invocations, duration, provisioned concurrency, or plans.
- **Storage and artifacts:** disks, image registries, object storage, snapshots, and backups.
- **Networking:** load balancers, NAT, internet egress, cross-AZ/region transfer, private endpoints.
- **Supporting platform:** cluster control planes, message brokers, monitoring/logging, secrets, registries, orchestration.
- **Redundancy:** minimum instances, standby capacity, fault-tolerance headroom, and capacity warm-up.
- **Operational staffing:** OS patching, cluster upgrades, on-call rotation, quota management, security response, and pipelines.
- **Licensing and support:** commercial software, runtimes, operating systems, and support plans.

### Comparison Example by Load Profile

Suppose the same API has two profiles:

| Profile | Behavior | Models to Consider |
| --- | --- | --- |
| A — bursty | 2,000 requests/day, mostly concentrated in 20 minutes, short tasks | Serverless or managed app with low autoscale floor |
| B — continuous | 500 RPS nearly all day, low and steady latency | Containers/VMs or compute with always-ready capacity |

Profile A has long idle periods so pay-per-use can be advantageous, though API gateway, logging, queues, cold starts, and egress must be added. Profile B has high utilization and needs always-warm capacity; tuned containers/VMs or serverless with provisioned capacity may be more economical depending on pricing. **You cannot conclude from a profile alone without unit prices, region, CPU/RAM configuration, request duration, and actual usage patterns.**

### Scenario-Based TCO Calculation

You can build a table:

| Line Item | Basis | Low | Base | High |
| --- | --- | ---: | ---: | ---: |
| Compute | vCPU/RAM × time or invocations × duration | … | … | … |
| Storage/images | GB-month, image pulls/cache | … | … | … |
| Network | GB egress, inter-AZ/region, NAT | … | … | … |
| HA/DR | Replica/standby count and backups | … | … | … |
| Observability | Metrics, logs, traces, retention | … | … | … |
| License/support | Per instance/user/plan | … | … | … |
| Operations | Engineering hours for patching, upgrades, on-call | … | … | … |
| **Total** |  | … | … | … |

Evaluate by **cost per transaction/job**, not just the total cloud bill. If containers cut compute spend by 15% but require an extra 24/7 platform on-call rotation, total cost can rise. Conversely, a managed platform with a higher unit price that drastically reduces patching incidents and deployment time can yield a better TCO.

## 12. Design Example: A Cloud Booking Application

Suppose a booking platform has the following workloads:

| Capability | Load Profile and Requirements |
| --- | --- |
| Booking API | Relatively steady load, requires low latency, must not create duplicate bookings |
| Catalog API | Read-heavy, stateless, cacheable content |
| Search | Variable CPU/RAM, large index, frequently updated algorithms |
| Image processing | Bursty around upload waves, each job can run tens of seconds |
| Notification | Can run asynchronously, needs retries and duplicate prevention |
| Report batch | Long scheduled job, needs checkpointing and durable output storage |

### Well-Grounded Candidate Architecture

- **Booking and Catalog APIs:** start on managed containers or a managed application platform if runtime, networking, and autoscaling meet SLOs. Keep modules separate; store state in managed databases/caches.
- **Search:** dedicated search service or platform with isolated resources. Benchmark memory/index/query performance and p99; do not let search compete with booking APIs for RAM by default.
- **Image processing:** queue + autoscaling container workers or serverless handlers. Limit concurrency, handle duplicates, and write objects under deterministic keys.
- **Notification:** separate queue/workers, idempotency/dedup, backoff, and DLQ; never block booking requests waiting on email delivery.
- **Report batch:** managed batch/jobs or container jobs depending on runtime, checkpointing, quotas, and deadlines.

Logical diagram:

~~~mermaid
flowchart TB
    USER["Client"] --> EDGE["WAF / API ingress"]
    EDGE --> API["Booking + Catalog API"]
    EDGE --> SEARCH["Search service"]
    API --> DB["Managed database"]
    API --> Q["Message queue / outbox"]
    Q --> IMG["Image workers"]
    Q --> NOTI["Notification workers"]
    Q --> REPORT["Batch/report jobs"]
    IMG --> OBJ["Object storage"]
    SEARCH --> INDEX["Search index"]
    REPORT --> OBJ
~~~

This is an illustrative layout; workloads can run together on a single container platform or managed app platform if resource isolation, lifecycles, and scaling can be separated. Not every box needs to be an independent compute product.

### Decisions Requiring Verification

1. Do the Booking API's p95/p99 latency and error rate meet targets at peak load, including when losing a replica/AZ?
2. Does Search still consume shared resources in a way that impacts Booking?
3. Can worker scale-up exhaust DB connections, object storage quotas, or email rate limits?
4. Do handler cold starts violate image processing deadlines or client experience?
5. Can batch jobs checkpoint and resume after a container replacement?
6. Do new image rollouts include safe health checks, canaries, and rollbacks?
7. Are backups/restores and data access preserved when a compute node or region fails?

## 13. Compute Selection Process in an Architecture Review

**Step 1 — Identify workloads:** API, worker, batch, stream, stateful service, or legacy process; runtime duration, triggers, and load profile.

**Step 2 — Record SLOs and constraints:** p95/p99 latency, throughput, availability, RTO/RPO, data, compliance, residency, and networking.

**Step 3 — Determine required control:** OS, kernel, runtime, libraries, GPU, filesystem, protocols, and administrative access.

**Step 4 — Shortlist two or three candidates:** VM, managed container, serverless, or managed app platform; avoid defaulting to a single option.

**Step 5 — Benchmark and failure-test:** use realistic payloads/data, test cold/warm starts, burst/steady load, scale-out, dependency failures, zone failures, and deployment rollbacks.

**Step 6 — Calculate TCO:** compute, network, storage, HA/DR, observability, support, and operational effort across growth scenarios.

**Step 7 — Review responsibilities and team capability:** who patches, who is on-call, and who manages pipelines, quotas, identity, secrets, backups, and platform upgrades?

**Step 8 — Document decision and review triggers:** state rationale, alternatives, risks, metrics, owners, and triggers for re-evaluation.

~~~mermaid
flowchart TD
    W["Describe workload + user journeys"] --> N["SLOs, data, network, compliance"]
    N --> C["OS/runtime control requirements"]
    C --> O["Select VM / container / serverless / managed platform"]
    O --> B["Benchmark + failure test + sizing"]
    B --> T["TCO + operational capability"]
    T --> D{"Meets goals?"}
    D -->|No| O
    D -->|Yes| ADR["Record architecture decision and review triggers"]
~~~

## 14. Common Mistakes When Selecting Compute

1. **Chasing trends:** using Kubernetes or serverless for simple workloads, inflating operational surface area.
2. **Treating containers as an absolute portability guarantee:** a runnable image does not mean networking, storage, IAM, and secrets behave identically across platforms.
3. **Ignoring OS and runtime patching:** providers manage hosts, yet application dependencies and images still become outdated.
4. **Omitting requests/limits/concurrency caps:** one unbounded workload can exhaust nodes, databases, or external services.
5. **Scaling solely on CPU:** ignoring queue lag, memory, connection pools, latency, and quotas.
6. **Using local filesystems for persistent state:** data vanishes when instances, functions, or containers are replaced.
7. **Overlooking cold starts and timeouts:** jobs or APIs breach latency limits when scaling from zero.
8. **Assuming autoscaling replaces HA:** autoscalers take time, quotas, and node capacity; they do not guarantee instant capacity when an AZ fails.
9. **Missing health checks and graceful shutdown:** rollouts or scale-ins drop in-flight requests.
10. **Budgeting only by compute price:** ignoring networking, logging, storage, backups, replicas, licenses, and operations.
11. **Ignoring team readiness:** adopting a platform requiring 24/7 cluster on-call with no dedicated owner.
12. **Skipping dependency testing:** compute instances look healthy while databases, NAT gateways, or external APIs are overloaded.

## 15. Practice Exercises and Guided Answers

A company is preparing to deploy four workloads:

| Workload | Characteristics |
| --- | --- |
| A — Transaction API | 300 RPS at peak hours, short requests, p99 latency under 250 ms |
| B — Video conversion | 8–15 minute jobs, heavy CPU/GPU usage, periodic batch load |
| C — Event webhook | 1,000 requests/day, occasional 20× bursts, each handled in under 2 seconds |
| D — Legacy application | Requires a licensed OS agent and specialized system configuration |

**Question 1: Propose a compute model for each workload.**

**Guided answer:** For A, consider managed containers or a managed app platform with sufficient always-on capacity and load-based scaling; p99 must be benchmarked at peak load. For B, consider container jobs/batch on appropriate CPU/GPU nodes or a managed batch platform; verify timeouts, checkpointing, GPU quotas, and node spin-up times. For C, consider serverless functions/containers if cold starts, concurrency, and retries fit. D likely needs VMs due to OS/agent/licensing requirements; automate image builds and patching.

**Question 2: Why should all four workloads not be placed onto one large VM?**

**Guided answer:** Their resource needs, runtimes, burst profiles, security postures, and lifecycles differ. Video conversion can saturate CPU/GPU and degrade the API; the low-traffic webhook would waste money on idle capacity; the legacy app needs its own OS. Separating scaling units provides isolation, though communication, networking, and total cost still require management.

**Question 3: API A handles 300 RPS, averaging 0.01 CPU-seconds/request with a 50% CPU target. Estimate preliminary CPU demand.**

**Solution:** \(300\times0.01/0.5=6\) effective cores. This excludes headroom, burst load, memory/I/O bottlenecks, and HA for AZ loss; it must be validated via benchmarks.

**Question 4: Webhook C scales to 500 concurrent invocations, each opening a database connection. What is the risk?**

**Guided answer:** It can open 500 simultaneous connections exceeding DB capacity, causing connection exhaustion and cascading failures. Cap concurrency, use connection pooling/proxies where appropriate, batch/queue when possible, control retries, and monitor DB connections and latency.

**Question 5: Why might workload B be unsuitable for short-timeout functions?**

**Guided answer:** An 8–15 minute job can exceed function time limits and requires GPU or checkpoint/resume support. Container jobs/batch or long-running VMs/workers may fit better. Verify the actual limits of the chosen serverless service, as some serverless containers/jobs support longer durations than standard functions.

**Question 6: When choosing a managed app platform, which security responsibilities stay with the application team?**

**Guided answer:** Code and dependencies, secrets, IAM/identity, data permissions, ingress/egress configuration, logs, backup/restore per shared responsibility, vulnerability remediation, and incident response procedures. Provider management of platform infrastructure does not automatically protect application logic or data.

## 16. Decision Checklist

- Are the workloads, average/peak loads, execution durations, and CPU/RAM/I/O profiles clear?
- Are SLOs, p95/p99 targets, availability, RTO/RPO, and failure domains defined?
- Is deep OS/runtime control genuinely required, or is a managed platform sufficient?
- Who manages images, dependencies, patches, secrets, IAM, and networking?
- Does scale-out fit within quotas and protect downstream services?
- Is persistent data separated from ephemeral compute?
- Have rolling deployments, health checks, graceful shutdown, canaries, and rollbacks been tested?
- Does the cost estimate include HA/DR, networking, logging, storage, licenses, and operations?
- Have load tests and failover tests been executed at realistic workload levels?
- Are there defined owners, dashboards, runbooks, and triggers to revisit the decision?

When concluding the review, present **workload characteristics, compute candidates, benchmark evidence, responsibility models, risks, and TCO**. A sound decision explains why a VM, container, serverless, or managed app platform fits current requirements while identifying what signals will trigger a re-evaluation of the architecture.
