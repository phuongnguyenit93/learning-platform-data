# Choosing Between Managed Container Platforms and Kubernetes

> **Chapter:** Container Architecture  
> **Scope:** Designing cloud application architectures from business requirements to networking, compute, data, and deployment models. This lesson focuses on trade-offs in reliability, security, scalability, cost, and operations using a Well-Architected mindset.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between application-level managed container platforms, managed Kubernetes, and self-managed Kubernetes.
2. Analyze workloads to determine the required level of control over compute, networking, storage, scheduling, and runtime.
3. Compare options based on operational responsibility, customizability, reliability, security, scalability, and TCO.
4. Design container workloads with appropriate resource configuration, health probes, autoscaling, network policies, secrets, observability, and rollout strategies.
5. Build a decision matrix with mandatory criteria, weights, and testing evidence.
6. Plan deployment, migration, and periodic reviews when requirements or team capabilities change.

## 1. Start with Workloads, Not Platform Names

Containers package an application together with the dependencies it needs to run, helping reduce differences between development, testing, and production environments. However, where to run those containers remains a critical architectural decision.

A cloud booking application might consist of three workload groups:

- User-facing HTTP APIs requiring traffic-based autoscaling and frequent releases.
- Queue-processing workers that run continuously and require concurrency control and graceful shutdown.
- Periodic jobs that generate reports, synchronize data, or clean up resources.

The same image can run across multiple platforms. Before choosing, answer the following:

- Which layers does the team need to control: nodes, networking, scheduling, ingress, storage, service discovery, or runtime policies?
- Do any workloads require GPUs, kernel capabilities, daemons, sidecars, or specialized volumes?
- What is the service count, load variability, concurrency, and execution duration?
- Who is responsible for node patching, control plane upgrades, cluster networking, capacity, and production incidents?
- Which security, data residency, audit, SLO, RTO/RPO, and budget requirements are non-negotiable?

A good platform helps the organization meet requirements with an appropriate level of control and operational responsibility.

## 2. Common Types of Container Platforms

### 2.1. Application-Level Managed Container Platforms

Users typically provide an image, CPU/RAM settings, environment variables, ports, health checks, and scaling rules. The platform handles most of the compute placement and runtime management.

Common characteristics:

- Deploy containers without directly managing a Kubernetes cluster.
- High level of abstraction with built-in integration for load balancers, logging, identity, and autoscaling in the provider's native way.
- Well-suited for web services, APIs, workers, and containerized tasks with standard runtime requirements.
- Less customization for the scheduler, node OS, CNI/CSI, admission policies, or service mesh compared to Kubernetes.
- May impose limits on execution duration, workload types, concurrency, networking modes, or volume mounting.

Examples include AWS App Runner, Google Cloud Run, Azure Container Apps, and similar services. Names and features vary by product, version, and deployment region; always check current documentation before deciding.

### 2.2. Managed Kubernetes

The provider manages part or most of the control plane; customers still declare workloads via the Kubernetes API and remain responsible for many cluster configurations, node pools, networking, security policies, and applications.

Common examples include Amazon EKS, Google Kubernetes Engine (GKE), and Azure Kubernetes Service (AKS). The scope of management varies depending on the operational mode, node model, version, and enabled features.

Managed Kubernetes does not mean the provider takes full responsibility for cluster configuration or applications.

### 2.3. Self-Managed Kubernetes

The organization installs and manages the control plane, nodes, upgrades, networking, storage, backup/restore, security, and observability on its own. This provides extensive control but creates significantly more infrastructure responsibility.

This option should only be chosen for clear reasons, such as specialized environments, control requirements that managed services cannot meet, or a sufficiently strong platform team. Self-managing purely for full control can lead to the team spending most of its time maintaining the platform instead of building products.

### 2.4. Concepts Not to Confuse

| Concept | Role |
| --- | --- |
| Container runtime | Runs container images and manages process/container lifecycles |
| Orchestrator | Schedules, maintains desired state, scales, and manages multiple workloads |
| Kubernetes control plane | API, scheduler, controllers, and cluster control components |
| Worker node | Machine/compute running container workloads in a node-based Kubernetes model |
| Managed platform | A service that abstracts away a portion of infrastructure and operational responsibilities |
| Container registry | Stores and distributes images/artifacts |
| Service mesh | A layer supporting service-to-service communication, telemetry, and traffic policies |

Kubernetes is a container orchestration platform, not a standalone container runtime. It provides flexible APIs and control mechanisms, but does not automatically solve business design, data architecture, application security, or cost optimization.

## 3. Two Paths: Managed Platforms vs. Kubernetes

~~~mermaid
flowchart TB
    W["Workload and organizational requirements"] --> Q{"How much orchestration control is needed?"}
    Q -->|"Standard runtime, minimal platform ops"| M["Managed container platform"]
    Q -->|"Needs Kubernetes API, policies, and ecosystem"| K["Managed Kubernetes"]
    Q -->|"Needs deep control plane/infrastructure control"| S["Self-managed Kubernetes"]
    M --> MV["Focus on app config, images, IAM, integrated networking"]
    K --> KV["Manage cluster/nodes, namespaces, policies, workloads"]
    S --> SV["Manage control plane, nodes, upgrades, networking, storage"]
~~~

Managed platforms generally reduce the number of infrastructure decisions an application team must operate. Kubernetes establishes a shared control model and a rich ecosystem, but operators must understand additional abstractions, dependencies, and failure modes.

There is no single optimal choice for every organization. Some systems benefit from using both: standard APIs run on a managed platform, while workloads requiring specialized scheduling/policies run on Kubernetes. Combining them is only worthwhile when the differences are significant enough to offset the cost of operating two platforms.

### 3.1. Overview Comparison Table

| Criterion | Managed Platform | Managed Kubernetes | Self-Managed Kubernetes |
| --- | --- | --- | --- |
| Level of abstraction | High | Medium | Lower |
| Control plane | Managed by platform | Managed by provider within service scope | Organization is responsible |
| Node/compute | Often hidden or profile-configured | Typically selects node pools/compute models | Organization manages nodes and OS |
| Orchestration flexibility | Limited to platform features | High via Kubernetes API | High, but self-operated |
| Networking | Follows provider model | CNI, Service, Ingress/Gateway, network policies | Self-implements most of the networking stack |
| Storage | Limited to built-in integrations | CSI, PV/PVC, StorageClass | Self-manages storage integration |
| Autoscaling | By requests, CPU, concurrency, or supported metrics | HPA, KEDA, node autoscaling depending on setup | Self-operates scaling components |
| Portability | Dependent on provider APIs and integrated services | Relatively standard API, though storage/network/identity still differ | Greater control, though not free of all dependencies |
| Operational burden | Typically lower | Medium to high | High |
| Best suited for | Standard apps, product-focused teams | Diverse workloads needing flexible orchestration | Specialized environments and dedicated platform teams |

This table reflects general trends, not guarantees across every provider. You must compare exact service modes, regions, quotas, runtime limits, and billing models.

## 4. Building Measurable Selection Criteria

### 4.1. Mandatory Criteria Before Scoring

Some requirements disqualify an option right from the start:

- Regions/zones must be permitted for data processing and storage.
- The runtime must support required languages, CPU architectures, kernel/capabilities, filesystems, or GPUs.
- Required network connectivity, private endpoints, egress controls, and IAM policies must be achievable.
- Must support backup/restore and meet RTO/RPO requirements.
- Must support logging, auditing, vulnerability scanning, and patching mechanisms per policy.
- Must fit within approved quotas, budgets, and contracts.

If a managed platform does not support volumes with the semantics required by the application, that is an unmet mandatory criterion. You must either redesign the application or choose a different platform; do not simply assign a low score and move on.

### 4.2. Requirements Matrix

| Category | Questions | Recommended Evidence |
| --- | --- | --- |
| Workload | HTTP, background worker, batch, streaming, stateful, or GPU? | Workload profile, prototype |
| Scale | Peak load, growth rate, is scale-to-zero appropriate? | Load test, concurrency test |
| Availability | SLOs, deployment zones, failover, node drains? | Failure drills and reports |
| Security | IAM, image provenance, secrets, egress, runtime isolation? | Threat model, policy tests |
| Operations | Does the team have on-call capacity and platform troubleshooting skills? | Skills/capacity assessment |
| Deployment | Rolling update, canary, rollback, blue/green? | Release tests |
| Observability | Metrics, logs, traces, audits, and retention? | Dashboards and alert tests |
| Cost | Compute, requests, storage, networking, licenses, operations? | TCO under normal/peak loads |
| Portability | Is cloud migration or hybrid deployment required? | Dependency inventory, migration exercise |

### 4.3. Weighted Scoring After Passing Mandatory Criteria

You can agree on a 1–5 scale and weights for relative evaluation:

\[
Score=\sum_{i=1}^{n}w_i s_i,\qquad \sum_{i=1}^{n}w_i=1
\]

Where \(w_i\) is the criterion weight agreed upon by stakeholders, and \(s_i\) is the option's score on that criterion. Scores are a discussion tool, not an objective measurement if the input data is merely guesswork.

Hypothetical example for standard HTTP APIs and background workers:

| Criterion | Weight | Managed Platform | Managed Kubernetes |
| --- | ---: | ---: | ---: |
| Operational simplicity | 25% | 5 | 3 |
| Orchestration flexibility | 20% | 2 | 5 |
| Standard workload scaling | 15% | 4 | 4 |
| Network/policy control | 15% | 3 | 5 |
| Onboarding speed | 10% | 5 | 3 |
| TCO at assumed scale | 15% | 4 | 3 |
| **Weighted total** | **100%** | **3.85** | **3.80** |

These scores only illustrate the method. A system with hundreds of workloads, custom controllers, or complex policies may yield different results; a system with two standard APIs and a small team may lean clearly toward a managed platform.

Do not score security highly simply because a platform offers many features. Security also depends on configuration, identity, networking, pipelines, runtime, and operational capability.

## 5. When Is a Managed Container Platform Suitable?

Consider a managed platform when:

- Workloads are primarily HTTP APIs, web services, workers, and scheduled jobs using standard runtimes.
- The team wants to focus on business logic, delivery, and application operations.
- There is no need for custom schedulers, node daemons, CRDs/operators, or specialized network plugins.
- Traffic fluctuates and needs request/concurrency-based scaling or scale-to-zero.
- You want to minimize responsibilities for patching, control plane/node upgrades, and capacity planning.
- You want a straightforward deployment path to adopt containers that is easy to train on.

### Limits to Verify

- Execution model: request-triggered services or long-running background workloads?
- Concurrency: maximum requests per instance, queue semantics, and parallel processing limits.
- Startup/shutdown: startup timeout, graceful termination, scale-to-zero, and cold starts.
- Storage: ephemeral or persistent filesystem; access modes and behavior when instances change.
- Networking: private ingress, static outbound IPs, VPC integration, service identity, private DNS.
- Runtime: root privileges, kernel capabilities, host access, sidecars, init processes, CPU architectures.
- Job/scheduler: periodic runs, retries, timeouts, and duplicate job prevention.
- Quotas: max instances, request size, execution duration, image size, and regional capacity.

Serverless container platforms can be convenient, yet still carry limitations for stateful workloads, daemons, or long-running processing. Do not assume there are no cold starts, quotas, or operational responsibilities just because of the "serverless" label.

## 6. When Does Kubernetes Provide Value?

Kubernetes is a better fit when requirements demand a rich orchestration layer:

- Dozens or hundreds of workloads spanning Deployments, StatefulSets, DaemonSets, Jobs, and CronJobs.
- Scheduling, affinity/anti-affinity, topology spread, resource quotas, and priorities.
- Consistent service discovery and traffic routing across multiple teams.
- Custom resources/controllers or an ecosystem supporting platform operations.
- Network policies, admission policies, and workload controls per namespace/cluster.
- Diverse workloads with distinct resource profiles requiring dedicated node pools.
- A platform team capable of standardizing clusters, policies, upgrades, observability, and developer support.

Distinguish between *needing* Kubernetes and *liking* Kubernetes. If workloads only need to run a standard HTTP image, managing clusters, node pools, ingress, policies, and operators may not deliver proportional value.

### 6.1. Components to Understand

| Component | Function | Design Questions |
| --- | --- | --- |
| Cluster | Control and resource boundary | Single or multiple clusters? Split by environment, region, trust boundary? |
| Control plane | API server, scheduler, controllers | Which parts does the provider manage? Upgrade policies? |
| Node pool | Group of nodes with similar compute configuration | Do workloads need different CPU, memory, GPU, or architectures? |
| Namespace | Logical partitioning | Are quotas, RBAC, and network policies sufficient for isolation? |
| Deployment | Manages stateless application replicas | Rolling updates, readiness, rollout strategy? |
| StatefulSet | Stateful workloads needing stable identity/volumes | Should databases run inside the cluster? How do backup/restore work? |
| Service | Stable address to access workloads | Internal/external access? |
| Ingress/Gateway | HTTP(S) entry point | TLS, routing, WAF, and ownership? |
| ConfigMap/Secret | Configuration and secret references | Encryption at rest, secret stores, rotation? |
| HPA | Scales workload replicas | Metrics, min/max, and stabilization? |
| PodDisruptionBudget | Limits voluntary disruptions | Are there sufficient replicas and topology spread? |
| Network Policy | Controls Pod/namespace network flows | Does the CNI enforce policies? |
| Operator/CRD | Extends APIs/automation | Who owns lifecycle, upgrades, and incidents? |

### 6.2. Stateless API Deployment Example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api:1.8.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            failureThreshold: 30
            periodSeconds: 5
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
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
~~~

This example must be tailored to the application and cluster:

- Requests help the scheduler calculate resource allocation; declaring less than actual demand can overload nodes.
- Limits cap usage according to runtime semantics. CPU limits can cause throttling; exceeding memory limits typically results in the container being OOMKilled.
- Startup probes allow time for application initialization; readiness determines whether to receive traffic; liveness determines whether the process needs restarting.
- Do not use a single endpoint checking all dependencies for all three probe types.
- A read-only filesystem requires valid writable paths for temporary directories via appropriate volumes.
- Do not use the `latest` tag in production; use versioned artifacts or image digests that can be traced and rolled back.

## 7. Resources, Autoscaling, and Capacity Planning

### 7.1. CPU/Memory Requests and Limits

In Kubernetes:

- Request is the resource amount the scheduler uses to place a Pod.
- Limit is the cap enforced at runtime per resource type.
- Overcommitment can improve node utilization but reduces safety margins for critical workloads.
- QoS classes are influenced by requests/limits and can affect Pod selection during node pressure.

Do not copy local machine settings directly into production. Profile under realistic loads or benchmarks with production-like datasets, concurrency, and conditions.

### 7.2. Scaling Workloads

Horizontal Pod Autoscaler (HPA) adjusts replica counts based on metrics like CPU, memory, or custom/external metrics if supported. HPA does not create additional node capacity if the cluster lacks free compute; a node autoscaler or compute provider must supply additional capacity.

~~~mermaid
flowchart TD
    MET["Metrics: CPU / request rate / queue age"] --> HPA["HPA / autoscaling policy"]
    HPA --> REPL["Pod replica count"]
    REPL --> SCHED["Scheduler"]
    SCHED -->|"Nodes have capacity"| NODES["Worker nodes"]
    SCHED -->|"Insufficient capacity"| CA["Cluster/node autoscaler"]
    CA --> NODES
    NODES --> APP["Running workload"]
    APP --> MET
~~~

You must determine:

- Which metrics reflect real demand? High CPU does not always correlate with request volume.
- Min/max replicas, scale-up speed, scale-down stabilization, and resource headroom.
- Node startup delay, regional quotas, and cloud API limits.
- Pod startup time, image pulls, readiness, and warm-up duration.
- Can downstream databases/brokers handle the new concurrency?

### 7.3. Scale-to-Zero and Cold Starts

Scale-to-zero lowers costs when there are no requests, but the first request after an idle period can be slow due to container initialization, image loading, runtime startup, and establishing dependency connections. For checkout flows or APIs with strict p95 SLOs, load test after idle periods.

Queue-based workers need a clear strategy: scale-to-zero can fit sparse tasks, but you must measure time to receive the first message, visibility timeouts, duplicate deliveries, and draining behavior during scale-down.

## 8. Networking, Ingress, and Service-to-Service

The container platform shapes how workloads receive requests and call dependencies:

- Ingress traffic may traverse load balancers, API gateways, WAFs, or ingress controllers.
- Pods/services communicate over internal DNS, virtual networks, and policies.
- Outbound traffic must be controlled via NAT, egress gateways, private endpoints, or firewalls.
- TLS/mTLS, service identity, and authorization are essential layers of defense; network reachability does not imply business-level authorization.
- Service discovery must remain stable across rollouts, scaling, and node failures.
- Observability must capture requests/traces across gateways, services, and workers.

Do not treat the cluster as a flat network. If every Pod can call every other Pod and every database is open to all namespaces, a compromised container can move laterally. Define trust boundaries, default-deny policies where appropriate, least-privilege RBAC and service accounts, and test network reachability.

Application-level managed container platforms may provide private networking or service identity through their own abstractions. Evaluate actual behavior rather than forcing Kubernetes configuration models onto a service that does not expose those primitives.

## 9. Supply Chain and Runtime Security

Container images carry code, libraries, OS packages, and startup configuration. Risks emerge across source code, dependencies, build pipelines, registries, and production runtimes.

Controls to consider:

1. **Base images:** use minimal images from trusted sources with a clear update schedule.
2. **Build reproducibility:** lock dependency versions, generate SBOMs and provenance where feasible.
3. **Image scanning:** scan for CVEs, enforce severity policies, and track exceptions with owners and expiration dates.
4. **Registry access:** private registries, least-privilege IAM, and pull/push auditing.
5. **Image signing/verification:** verify artifacts reaching production come from trusted pipelines if supported.
6. **Runtime security:** non-root execution, read-only filesystems, dropped capabilities, seccomp/AppArmor or equivalents, restricted host access and privileges.
7. **Secrets:** retrieve from secret managers or secure mechanisms; never bake into images or logs.
8. **Patch lifecycle:** rebuild and redeploy images when base images or dependencies require updates; containers do not self-patch internal libraries while running.

### 9.1. Multi-Stage Dockerfile Example

~~~dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine AS runtime
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
~~~

This example only illustrates a multi-stage build. Before going to production, verify that base image versions are pinned per policy, user 101 has appropriate read/write permissions, the nginx configuration supports non-root/unprivileged ports, and health checks and logging are configured. Never copy environment files, private keys, or local caches into the final image.

## 10. Deployment Strategies and Availability

Even a strong container platform can suffer downtime if rollouts, probes, and shutdowns are misconfigured.

### 10.1. Rolling Updates

Gradually replaces old Pods with new Pods within `maxSurge`/`maxUnavailable` limits. Suitable when applications and schemas are compatible across versions. Requires accurate readiness probes, appropriate termination grace periods, and enough capacity while two versions run concurrently.

### 10.2. Blue/Green and Canary

- **Blue/green:** maintains two environments and switches traffic after testing. Enables fast traffic rollback, but can increase costs and requires handling schema/data migrations.
- **Canary:** shifts a portion of traffic to the new version, monitors error rates/latency, and gradually increases it. Requires traffic splitting and reliable metrics.

### 10.3. Readiness and Graceful Shutdown

When a Pod receives SIGTERM, the application should stop accepting new requests, finish or reject in-flight work according to its semantics, close connections, and exit within the grace period. Terminating the process immediately can drop in-flight requests or cause messages to be redelivered.

For queue workers, ack/nack handling, visibility timeouts, idempotency, and draining must align with the container lifecycle. `PreStop` hooks can assist, but do not replace safe shutdown logic inside the application.

### 10.4. Availability Zones and Disruptions

Having multiple replicas does not guarantee HA if all Pods land on the same node or zone. Use topology spread, anti-affinity, PodDisruptionBudgets, and appropriate node pools. PDBs limit certain voluntary disruptions; they do not protect against all node/zone failures or every form of forced deletion.

Managed platforms may hide node placement; verify multi-zone commitments, instance distribution behavior, and failover capabilities for your selected mode.

## 11. Stateful Workloads and Storage

A container having a writable temporary filesystem does not mean data is durable. When a container is replaced, local data can be lost.

For stateful workloads, clarify:

- **Ephemeral storage:** regenerable caches/temp files; requires capacity management and cleanup.
- **Persistent volumes:** volumes with independent lifecycles, access modes, zone affinity, snapshots, and backups.
- **Managed databases/object storage:** consider managed data services instead of self-hosting databases in the cluster unless there is a specific reason.
- **StatefulSet:** provides stable identity/ordinals and volume claim templates; does not automatically solve replication, backups, or database consistency.
- **Restore:** practice data restoration drills rather than merely checking that snapshots exist.

On managed application platforms, volumes may be unsupported or limited to specific persistence forms. If a workload requires a shared filesystem or specialized storage semantics, verify support before choosing the platform.

### When Should You Run Databases in Kubernetes?

It can be reasonable when the team has deep expertise operating database operators, replication, backups, restores, upgrades, storage classes, and data incidents—or when environmental constraints make it beneficial.

Do not put a database inside a cluster simply to containerize everything. Managed databases often provide better backups, patching, failover, and cloud IAM integration at a lower operational cost. Compare TCO and the ability to meet RPO/RTO under realistic conditions.

## 12. Observability and Operational Responsibilities

Managed platforms offload part of the infrastructure work, yet still require application observability. Kubernetes adds more layers to monitor: the control plane within your access scope, nodes, scheduler, CNI, CSI, ingress, operators, quotas, and cluster autoscaler.

| Layer | Metrics / Logs to Monitor |
| --- | --- |
| Application | Request rate, p95/p99 latency, error rate, business success rate |
| Container | CPU, memory, throttling, restarts, OOMKilled, startup time |
| Kubernetes workload | Desired vs. available replicas, rollouts, pending Pods, probe failures |
| Node/cluster | Capacity, pressure, node readiness, scheduling, upgrade status |
| Networking | Connection errors, DNS, ingress latency, policy drops |
| Storage | Volume capacity, latency, attach/mount failures, snapshot/restore |
| Autoscaling | Replica changes, scaling lag, quotas, pending workloads |
| Cost | Idle vCPU/RAM, request pricing, node utilization, egress, log ingestion |

Do not monitor only whether Pods are Running. An API with three Running replicas where every request is slow due to the database is still an unhealthy system. SLIs/SLOs should reflect user experience: search success rate, p95 checkout latency, on-time job completion rate, and recovery capability.

SREs need runbooks for Pod crash loops/OOMs, node/zone unavailability, HPA missing metrics/quotas, image pull failures, broken secrets/configs post-deploy, overly restrictive network policies, storage mount/restore failures, and control plane/API quota issues.

## 13. Cost: Calculate TCO Instead of Compute Price Alone

Managed platforms typically charge by running instances/resources, requests, compute time, or a combination depending on the product. Kubernetes incurs control plane/management fees depending on provider/mode, plus nodes/compute, storage, load balancers, networking, logs, registries, licenses, and operational staffing.

\[
TCO = C_{\text{compute}} + C_{\text{control}} + C_{\text{network}}
+ C_{\text{storage}} + C_{\text{observability}}
+ C_{\text{security}} + C_{\text{operations}}
\]

Here, operational cost includes platform engineering effort, on-call support, upgrades, vulnerability remediation, DR testing, and maintaining automation.

### Hypothetical Comparison Example

Suppose an API service and two workers have moderate traffic:

| Monthly Line Item | Managed Platform | Managed Kubernetes |
| --- | ---: | ---: |
| Workload compute | 700 USD | 500 USD |
| Platform/control/cluster | Bundled or usage-based | 150 USD |
| Load balancer/network | 80 USD | 120 USD |
| Logging/metrics/security | 100 USD | 120 USD |
| Allocated operational effort | 100 USD | 450 USD |
| **Illustrative total** | **980 USD** | **1,340 USD** |

These figures are strictly illustrative, not provider quotes. With many workloads, node sharing can make Kubernetes more cost-efficient; with a small number of workloads, a managed platform can avoid baseline cluster costs and operational overhead.

Model at least six scenarios: steady state, peak, idle, failure/DR, growth, and engineering cost. Do not choose Kubernetes solely expecting compute savings, and do not choose a managed platform assuming zero operational overhead.

## 14. Real-World Scenario: A Growing Booking Platform

### 14.1. Context

An enterprise has three stateless APIs needing autoscaling, two workers consuming messages from a queue, one scheduled reporting job, and one image processing component requiring specialized native libraries. The Platform team has two engineers; the development team wants frequent releases. User growth is projected from 10,000 to 100,000 active users within one year.

This is a hypothetical scenario. There is not yet enough data to finalize the platform choice; throughput, job durations, dependencies, security, and costs must be measured first.

### 14.2. Two Options

**Option A — Managed container platform for all workloads**

Pros: minimal cluster burden, fast API onboarding, integrated cloud services, and usage-based autoscaling if supported by the platform.

Needs verification: continuous worker execution/queue semantics, job scheduling, native libraries, storage, concurrency, outbound networking, and keeping instances warm to meet SLOs.

**Option B — Managed Kubernetes**

Pros: manages diverse workloads via a unified API and ecosystem; customizable scheduler, node pools, policies, sidecars/operators, and networking as needed.

Trade-offs: the Platform team must handle cluster upgrades, node capacity, CNI/CSI, ingress, policies, observability, and developer support. Two engineers must assess on-call capacity and automation maturity before scaling up.

### 14.3. Hybrid Option to Consider

| Workload | Initial Recommendation | Conditions |
| --- | --- | --- |
| Standard APIs | Managed platform | p95, concurrency, private networking, and autoscaling pass |
| Queue workers | Managed platform or Kubernetes | Graceful shutdown, queue metrics, retries, and long-running processes |
| Scheduled reports | Managed job/scheduler or Kubernetes CronJob | Retries, timeouts, duplicate job prevention, and permission controls |
| Native image processing | Prototype on both if needed | CPU/GPU, libraries, memory, and throughput |
| Workloads needing custom policies/scheduling | Managed Kubernetes once proven necessary | Platform team has capacity and provides guardrails |

A hybrid setup adds extra deployment workflows, logging, IAM, release pipelines, and support overhead. Only adopt it when workload differences are substantial; if the APIs, workers, and jobs all run well on the same managed platform, a single platform is simpler.

### 14.4. Validation Plan

1. Package the same image for APIs and workers.
2. Deploy prototypes to both the managed platform and managed Kubernetes in comparable environments.
3. Run load tests at normal/peak traffic; measure p95/p99 latency, cold starts, concurrency, and error rates.
4. Test workers handling duplicate messages, shutdowns, scale-downs, retries, and dead-letter queues.
5. Test rollouts/rollbacks, secret rotation, network restrictions, and image vulnerability scanning.
6. Simulate instance/node failures and verify related data recovery.
7. Calculate TCO including compute, cluster/platform, networking, logging, security, and operational effort.
8. Review results with Product, SRE, Security, Finance, and technical owners; record an ADR and review triggers.

## 15. Implementation and Migration Roadmap

### Step 1 — Standardize Images

Ensure reproducible builds, pin dependencies and base images, run as non-root where feasible, externalize config/secrets, log to stdout/stderr, and implement health endpoints and graceful shutdown. Do not store critical state in the container's writable filesystem.

### Step 2 — Profile Workloads

Create workload profiles covering CPU, memory, startup, duration, concurrency, networking, and I/O. Define SLOs, capacity, bursts, dependencies, and traffic variability.

### Step 3 — Build a Standardized Deployment Foundation

Use Infrastructure as Code, a container registry, CI/CD, image scanning, identity, networking, logs, metrics, secrets, and runbooks. If choosing Kubernetes, standardize namespaces, quotas, RBAC, network policies, node pools, ingress, HPA, and upgrade policies.

### Step 4 — Migrate a Representative Workload

Pick a non-critical API or a reconcilable worker; deploy side-by-side, shift a portion of traffic, monitor SLIs, and verify rollback. Do not migrate all services at once.

### Step 5 — Expand Based on Evidence

Add workloads or clusters only when clearly justified. Optimize nodes/requests, quotas, autoscaling, and cost allocation; reassess after incidents and traffic shifts.

### Step 6 — Control Platform Debt

Platform debt can include un-upgraded clusters, unsupported operators, policy drift, missing dashboards, duplicated IaC modules, and manual deployments. Record owners, impact, and triggers for paying down the debt.

## 16. Sample Architecture Decision Record

~~~markdown
# ADR-041: Selecting a Container Platform for Booking APIs and Workers

Status: Conditionally Approved
Decision owner: Architecture lead + SRE + Product
Date: YYYY-MM-DD

Context:
- 3 stateless APIs, 2 queue workers, 1 scheduled report.
- Platform team consists of 2 engineers.
- Requires autoscaling, safe rollouts, and SLO-based observability.
- The native image of the image processor requires separate validation.

Constraints:
- Regions and networking must comply with data policies.
- RTO/RPO, IAM, and auditing per approved requirements.
- TCO within budget.

Options:
A. Managed container platform.
B. Managed Kubernetes.
C. Hybrid by workload type.

Decision:
- Pilot Option A for standard APIs and workers.
- Only adopt Option B for workloads with orchestration/policy requirements
  that A cannot satisfy, after reviewing Platform team capacity.

Trade-offs:
- A reduces cluster management effort but is constrained by platform abstractions.
- B offers greater flexibility, increasing node/network/upgrade responsibilities.
- C increases the number of platforms to observe and support.

Acceptance Evidence:
- Load, cold-start, graceful shutdown, and queue retry tests.
- Security, networking, image scanning, and rollback validation.
- Failure drills and TCO across steady/peak/DR scenarios.

Review Triggers:
- New workloads require GPUs/daemons/operators;
  workload count grows rapidly; SLOs/regions/costs change;
  or the Platform team builds capacity to operate a new cluster.
~~~

The ADR should attach workload profiles, test reports, cost models, remaining risks, and owners. Never approve solely based on a single successful demo.

## 17. Common Pitfalls

| Pitfall | Consequence | Mitigation |
| --- | --- | --- |
| Choosing Kubernetes just because of microservices | Increases operational overhead without orchestration need | Evaluate workloads and team capacity |
| Assuming "managed" means the provider owns everything | Neglects security, apps, quotas, and configuration | Clarify shared responsibility and RACI |
| Comparing CPU/RAM prices alone | Omits control plane, egress, logging, backups, staffing | Calculate TCO and model failure/growth scenarios |
| Ignoring cold starts/scale lag | Breaches p95 SLOs during peak hours | Load test from idle and under surge |
| Setting requests/limits arbitrarily | Throttling, OOMs, pending Pods | Profile resources and tune accordingly |
| Using liveness to check all dependencies | Dependency outage triggers cascading restarts | Separate startup/readiness/liveness probes |
| Forgetting graceful shutdown | Lost or duplicated jobs/messages | Drain handling, idempotency, and termination tests |
| Multiple replicas in a single zone | Zone outage still disrupts the entire workload | Topology spread and failure drills |
| Putting databases in clusters just for uniformity | Increases storage/backup/upgrade risk | Compare managed DBs against operators |
| Enabling HPA without node capacity | Pods remain pending when traffic spikes | Combine workload and node autoscaling |
| Not standardizing images/registries | Broken deploys, vulnerabilities, poor traceability | Pin artifacts, scan, sign/verify, and audit |
| Adopting multiple platforms arbitrarily | Fragments IAM, logging, and skills | Use hybrid only when workload needs genuinely diverge |

## 18. Practice Exercise

A logistics system consists of 12 microservices, 4 queue workers, 2 nightly batch jobs, and an image processing service. The team has 4 backend engineers and 1 Platform engineer; they currently have CI/CD but no experience operating clusters. The business needs to scale 4x during peak season, meet Product-approved API p95 thresholds, and satisfy contractual DR requirements.

Complete the following:

1. Create workload profiles for the APIs, workers, batch jobs, and image processor; specify CPU/RAM, concurrency, startup, storage, networking, and execution duration.
2. Identify mandatory criteria: region, networking, IAM, auditing, RTO/RPO, SLOs, and quotas.
3. Compare a managed platform and managed Kubernetes; list specific features to verify.
4. Build a weighted decision matrix; justify the weights to Product, Security, SRE, and Finance.
5. Recommend a platform for each workload; if proposing a hybrid model, explain the cost of supporting multiple platforms.
6. Design API/worker rollouts, probes, graceful shutdown, autoscaling, queue backpressure, and rollbacks.
7. Write test scenarios for cold starts, peak load, node/instance failures, secret rotation, restores, and cost spikes.
8. Draft an ADR containing assumptions, alternatives, remaining risks, owners, and review triggers.

**Self-assessment criteria:** a strong solution must demonstrate that the platform satisfies workload and operational requirements, include SLO/cost data, support safe deployment and recovery, and avoid assuming that more technology automatically yields better outcomes.

## 19. Production Readiness Checklist

- [ ] Workload profiles and quality requirements are confirmed.
- [ ] Platform choice is backed by mandatory criteria and an evidence-based comparison matrix.
- [ ] Images come from trusted sources, have pinned versions/digests, are scanned, and have managed lifecycles.
- [ ] Containers run with least privilege, contain no secrets, and have properly designed filesystems.
- [ ] CPU/RAM requests/limits are grounded in measurements.
- [ ] Startup/readiness/liveness probes accurately reflect application state.
- [ ] Autoscaling defines metrics, min/max, headroom, quotas, and downstream dependency capacity.
- [ ] Networking, ingress, egress, service identity, and policies are tested.
- [ ] Deployments support appropriate rolling/canary/blue-green strategies, with rollbacks tested.
- [ ] Graceful shutdown, job draining, idempotency, and queue retries are verified.
- [ ] Volumes, backups, restores, RTO/RPO, and stateful data have clear owners.
- [ ] Metrics/logs/traces/dashboards/alerts/runbooks are in place.
- [ ] Nodes/clusters/platforms are patched and upgraded per policy.
- [ ] TCO includes compute, platform, storage, networking, observability, security, and operational effort.
- [ ] The ADR documents the chosen option, trade-offs, assumptions, risks, and review triggers.

## Key Takeaways

**Managed container platforms** help teams focus on applications by abstracting away much of the deployment and operational work; in return, customizability depends on product limits. **Kubernetes** offers a rich orchestration API suitable when workload, scheduling, policy, and ecosystem demands are substantial; in return, organizations must invest in platform, networking, storage, security, and lifecycle capabilities.

Follow the sequence: **workload requirements → mandatory criteria → required level of control → operational capacity → SLO/TCO testing → ADR with review triggers**. Choosing the right platform helps the system meet business needs safely, reliably, scalably, and at an acceptable operational cost.
