# Comparing Compute Engine, GKE, Cloud Run, and App Engine

When bringing a Java/Spring application to Google Cloud, the first question is not necessarily “which deploy command should I run?”. The more important question is: **how much infrastructure control does the application need, what scaling model does it require, how much operational work is the team ready to handle, and what are the reliability, security, and cost requirements?** A simple REST API may fit Cloud Run, a multi-workload system needing Kubernetes may fit Google Kubernetes Engine (GKE), legacy software with OS dependencies may need Compute Engine, while a web app tightly coupled to the App Engine model may continue leveraging that service's strengths.

This lesson belongs to the **GCP Architecture Design** chapter of the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability alongside cost. In this lesson, we compare the four application runtime platforms from an architectural perspective, without treating any single platform as best in all cases.

> **Scope:** The comparison focuses primarily on web/API applications, Java/Spring Boot services, workers, and certain background workloads. Features, limits, and pricing may change over time, by region, and by configuration; always check official documentation and pricing sheets before finalizing a production plan.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between virtual machine, Kubernetes, serverless container, and managed application platform models.
- Evaluate Compute Engine, GKE, Cloud Run, and App Engine in terms of control, operations, scaling, deployment, networking, cost, and portability.
- Understand the differences between GKE Autopilot and Standard, as well as App Engine Standard and Flexible.
- Select a platform based on Java/Spring Boot requirements, background jobs, stateful services, and infrastructure dependencies.
- Estimate the components of total cost of ownership rather than comparing CPU or memory unit prices alone.
- Design a sample deployment and define boundaries for IAM, storage, logging, and rollback.
- Propose a single-platform or multi-platform architecture with testable reasoning and assumptions.

## 1. Four Options Across the Control Spectrum

Google Cloud provides multiple levels of abstraction:

1. **Compute Engine:** provisions virtual machines (VMs). The team has control over the guest OS, runtime, processes, and most host-level VM configurations.
2. **GKE:** provides managed Kubernetes. The team defines Pods, Deployments, Services, networking, and Kubernetes policies; the degree of node management differs between Standard and Autopilot.
3. **Cloud Run:** deploys containers or source code into serverless workloads without managing clusters. Cloud Run has multiple resource types, where services fit request-driven APIs, jobs fit finite tasks, and worker pools fit pull-based/always-on background processing.
4. **App Engine:** an application deployment platform organized by service/version, with **Standard** and **Flexible** environments that have distinct operational characteristics.

~~~mermaid
flowchart LR
    A["Compute Engine<br/>VM and guest OS"]
    B["GKE<br/>Kubernetes"]
    C["Cloud Run<br/>serverless workloads"]
    D["App Engine<br/>app-centric platform"]
    A --- B --- C --- D
~~~

This diagram illustrates the deployment models; it is **not** a strict ordering of cost, performance, or suitability. GKE Autopilot significantly reduces node management compared to GKE Standard; App Engine Flexible still runs on managed VMs; Cloud Run is no longer limited to serving HTTP requests. When making decisions, compare based on the specific workload type.

### Shared responsibility: what does Google manage and what does the team manage?

| Responsibility Layer | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Hardware, Google infrastructure | Google | Google | Google | Google |
| Workload guest OS | Ops team is responsible for configuring/patching the guest OS | Node OS is managed by GKE depending on mode; team still manages workloads | Google manages infrastructure; app manages dependencies in image/source | Google manages the environment per Standard/Flexible |
| Orchestration | Team builds it or uses MIGs | Kubernetes/GKE | Cloud Run | App Engine |
| Runtime/application | Team | Team | Team | Team, within runtime boundaries |
| IAM, data, secrets, network policy | Team configures | Team configures; some defaults supported by GKE | Team configures ingress/egress/identity | Team configures service IAM, identity, and permissions |
| Scaling policy, SLO, observability | Team | Team | Team, though platform handles provisioning | Team, though platform handles provisioning |

**Managed does not mean zero operational work.** Across every platform, the team remains responsible for designing permissions, protecting data, managing dependencies, handling application errors, setting SLOs, and observing user impact.

## 2. Quick Comparison in One Table

| Criterion | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Deployment unit | VM image, startup script, package, container on VM | Container in Pod/Deployment/Job | Container, source build; service/job/worker pool | App service and version; source/runtime or container depending on environment |
| OS control | High, including guest OS and kernel | Higher in Standard; more restricted in Autopilot | Cannot modify host OS/kernel | Standard is restricted; Flexible is customizable via container/Dockerfile |
| Self-managed nodes | Yes | Standard: yes; Autopilot: managed by GKE | No | Not under a conventional node administration model |
| Scaling model | Custom-designed or MIG autoscaling | HPA/VPA, node autoscaling, depending on mode | By workload type: requests, tasks, CPU/backlog, or configuration | Automatic/basic/manual depending on Standard/Flexible |
| Scale to zero | VMs do not scale to zero by default | Workloads can scale to 0 replicas, though cluster/node costs remain depending on mode | Services can usually scale to 0; jobs run when invoked; worker pools have specific rules | Standard automatic can scale to 0; Flexible typically requires at least 1 instance |
| Operational effort | High | Medium to high; Autopilot reduces node work | Lower for fitting workloads | Relatively low, but subject to platform constraints |
| Stateful workloads | Can run with self-designed disks and HA | StatefulSet + persistent volumes | Persistent state should be externalized to other services | Persistent state should be externalized to other services |
| Typical fit | Legacy, custom OS, specialized agents/drivers | Many microservices, Kubernetes-native, needing networking/operators | APIs, webhooks, event processing, fitting batch tasks | Web apps already using App Engine or needing the service/version model |
| Costs to evaluate | VM, disk, IP, network, OS/licenses, HA | Cluster, node or workload resources, network, storage | CPU/memory/resources per billing mode, requests, min instances, and network | Instances/resources per Standard/Flexible, storage/network, and supporting services |
| Portability | VM images/scripts, requires OS management | Kubernetes manifests, still includes GCP-specific configs | OCI images portable at code level, but Cloud Run-specific API/deploy config | App.yaml and runtime/deploy model have platform coupling |

This is a directional guide. For example, GKE Autopilot has higher automation than GKE Standard, Cloud Run offers background workload types beyond HTTP services, and Compute Engine Managed Instance Groups (MIG) support autoscaling/autohealing. Therefore, do not decide based on a single “Yes/No” cell.

## 3. Compute Engine: VM Control and Flexibility

Compute Engine is an Infrastructure as a Service (IaaS) offering: create VMs with the appropriate machine type, operating system, disks, network interfaces, firewalls, and service accounts. The team can install a JDK, Nginx, monitoring agents, native libraries, or software requiring guest OS admin privileges.

### When Compute Engine is a good choice

- Legacy applications requiring OS configuration, custom TCP ports, daemons, or native libraries.
- Requirements for kernel/guest OS control, drivers, process managers, or specific patching schedules.
- Workloads needing attached disks, GPU/hardware profiles, or software requirements incompatible with PaaS limits.
- Organizations already operating VMs effectively with image baking, patching, backup, and monitoring tooling.
- Need for a fast lift-and-shift path from VMs/on-premises prior to application modernization.

### What the team must operate

- OS configuration, security updates/patches, hardening, and CVE remediation.
- Code deployment, systemd/service configuration, automatic restarts, and health checks.
- Load balancing, autoscaling, capacity planning, and multi-zone HA.
- Monitoring agents, log shipping, backups, recovery, and disk lifecycle.
- Firewalls, service accounts, network ingress/egress, and SSH protection.

A single VM running Spring Boot may suffice for a demo, but it is a single point of failure. For production applications requiring availability, consider multiple VMs across different zones, a load balancer, and a controlled update/rollback model.

### Managed Instance Groups

Compute Engine **Managed Instance Groups (MIG)** allow managing multiple identical VMs via an instance template, supporting autoscaling, autohealing, rolling updates, and multi-zone deployment with regional MIGs. This reduces some effort compared to managing individual VMs manually, but the team must still manage images, the OS, application configuration, and release strategies.

Do not confuse MIG autoscaling with full serverless capabilities: VMs in a group still have lifecycles, boot times, and costs based on provisioned resources.

### Example: deploying Spring Boot on VMs

A simple architecture:

~~~text
HTTPS Load Balancer
      |
Managed Instance Group
  +--- VM A (Spring Boot, systemd, Ops Agent)
  +--- VM B (Spring Boot, systemd, Ops Agent)
      |
Cloud SQL / Memorystore / Cloud Storage
~~~

VMs use a least-privilege service account and download tested artifacts from a trusted repository. Persistent state is separated from each VM's local filesystem when instance replacement is required.

**Core limitation:** greater freedom comes with greater operational overhead. If you only need to run a stateless HTTP API, Compute Engine may add work without proportional benefit.

## 4. GKE: Kubernetes for Multi-Workload Systems

Google Kubernetes Engine provides managed Kubernetes. You declare your application's desired state using Deployments, StatefulSets, DaemonSets, Jobs, Services, ConfigMaps, Secrets, Ingress, or Gateway. Kubernetes orchestrates Pods, executes rolling updates, brings new Pods into service after readiness probes pass, and replaces failed Pods via controllers.

### When to choose GKE

- The team already has Kubernetes experience or needs a shared platform for multiple teams/microservices.
- Workloads require custom Kubernetes controllers, operators, sidecars, service mesh, advanced networking, or policies.
- Orchestration is needed across multiple workload types: web/API, workers, Jobs, cron, StatefulSets.
- Control is needed over deployment configuration, placement, affinity, taints/tolerations, quotas, and namespaces.
- You want to standardize GitOps/Helm/Kustomize workflows and multi-cluster deployments.

GKE does not eliminate the need to understand Kubernetes. The team still designs manifests, requests/limits, probes, security contexts, RBAC, rollouts, and application incident recovery.

### GKE Standard vs. Autopilot

| Question | GKE Standard | GKE Autopilot |
|---|---|---|
| Who manages node pools? | Team chooses/controls them, with autoscaler tooling support | Google manages node infrastructure for Autopilot workloads |
| Node customization | Many options, suited for specialized drivers/agents | Restricted by Autopilot policies and configurations |
| Autoscaling | Combines HPA and cluster/node autoscaler, configured by the team | GKE automatically provisions node capacity for Pod demand; team still designs workload scaling |
| Default security | Team must configure and maintain corresponding policies | Built-in security defaults and restrictions |
| Pricing | Typically considers cluster + node resources and related services | Typically considers cluster + workload resources per applicable model |
| Best fit | Need infrastructure control or features restricted by Autopilot | Most standard Kubernetes workloads aiming to reduce node operations |

**Current note:** GKE can run Autopilot workloads inside a Standard cluster using ComputeClass when properly configured. Therefore, do not view this model as strictly two mutually exclusive options. For new organizations, Autopilot is usually the option to evaluate first unless specialized node requirements exist.

### Example Kubernetes Deployment for a Java API

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/example-project/apps/orders-api:release-12
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
~~~

The manifest assumes Spring Boot has readiness and liveness endpoints enabled and appropriately secured. A complete deployment also requires a namespace, a Kubernetes Service/Gateway or Ingress, Workload Identity Federation for GKE, Artifact Registry access, network configuration, and necessary policies.

### The price of flexibility

Everything from Pod scheduling to resource quotas, autoscaling, and upgrade windows needs an owner. When running only two small APIs, a dedicated cluster can create unnecessary operational overhead. However, when multiple teams and workloads share a cluster, orchestration capabilities and standardization can deliver significant value.

## 5. Cloud Run: Serverless Workloads Without Cluster Management

Cloud Run runs containerized applications or source builds turned into containers on Google-managed infrastructure. For web/API applications, **Cloud Run services** are often a sensible starting point because the team mainly provides the image, configures CPU/memory, concurrency, min/max instances, ingress, identity, and required connections.

Cloud Run now offers multiple resource types:

| Resource Type | Primary Goal | Usage Pattern |
|---|---|---|
| Services | Receive HTTP/gRPC requests or events delivered as requests | REST APIs, webhooks, web frontends/backends |
| Jobs | Run tasks with a start and end, splittable into multiple tasks | ETL, migrations, batch reports, scheduled runs via Scheduler/Workflows |
| Worker pools | Continuous/pull-based background processing instead of waiting for HTTP requests | Queue consumers or long-lived event streams |
| Instances | Cases requiring an independently managed instance | Specialized workloads, not the mainstream API choice |

### Key advantages

- No need to create or manage Kubernetes clusters or VMs.
- Deployment from container images, with revisions for inspection/rollback and traffic splitting.
- Can scale with traffic for request-driven services; services can scale to 0 when warm instances are not required.
- Easy integration with runtime service accounts, Secret Manager, and Cloud Logging/Monitoring/Trace.
- Well-suited for stateless Java/Spring Boot APIs, webhooks, and event-driven integrations.

### Operational limits to understand

- You cannot customize the host OS/kernel the way you can on a VM.
- Design containers to start up and serve traffic according to the Cloud Run runtime contract.
- The instance's local filesystem must not be treated as durable state storage; use Cloud Storage, Cloud SQL, Spanner, Firestore, or an appropriate service.
- For Cloud Run services, requests have a deadline; the default timeout is 5 minutes and can be increased up to 60 minutes under current configurations. Do not use a single HTTP request for unbounded tasks.
- If a workload must continuously listen or poll external sources without incoming requests, evaluate worker pools, min instances, instance-based billing, or queue/event architectures rather than assuming a service scaled to 0 will restart itself without requests.
- Scale-to-zero saves costs in many patterns, but can cause cold starts. Configuring minimum instances can reduce latency at an added cost.

**Do not conclude that Cloud Run lacks GPUs or cannot run background tasks.** GPU capabilities and workload types have expanded; specific decisions still depend on resource types, quotas, regions, hardware requirements, and published limits.

### Example: deploying a Java container to Cloud Run

After building the Spring Boot image and pushing it to Artifact Registry:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/example-project/apps/orders-api:release-12" \
  --region="asia-southeast1" \
  --project="example-project" \
  --service-account="orders-runtime@example-project.iam.gserviceaccount.com" \
  --memory="1Gi" \
  --cpu="1" \
  --concurrency="40" \
  --min="0" \
  --max="20"
~~~

This is an illustrative example, not an optimal configuration for every API. Depending on CLI version and autoscaling mode, verify the corresponding min/max flags. A service should receive public traffic only when granted appropriate invoker/ingress permissions; **never** open it publicly just for testing.

After deployment, verify revision Ready status, run authenticated smoke tests if needed, and check error rates, P95 latency, and database connection counts. For databases with connection limits, factor in the impact of max instances multiplied by connections per instance.

### Billing is not just request count

Cloud Run offers request-based or instance-based billing options depending on workload type and configuration. Costs also depend on CPU, memory, active duration, minimum instances, GPUs if used, networking, and supporting services. Do not equate “scale to zero” with “free”; high request volume, high memory, or min instances can add up to substantial costs.

## 6. App Engine: Version-Based Application Deployment Platform

App Engine is a managed application platform built around services, versions, and traffic splitting. App Engine's two environments behave noticeably differently:

- **Standard environment:** uses Google-provided runtimes, configured via `app.yaml`; scales automatically according to the selected scaling mode, supporting scale-to-zero under suitable automatic scaling configurations.
- **Flexible environment:** runs applications inside containers on managed VMs; supports custom runtimes, background processes, and SSH debugging; active versions require at least one instance, and startup/deployment typically takes longer than Standard.

### Comparing Standard and Flexible

| Criterion | App Engine Standard | App Engine Flexible |
|---|---|---|
| Runtime | Supported runtimes per lifecycle schedule | Built-in runtimes or custom runtime/container |
| Environment customization | More restricted | Customizable via Dockerfile |
| Background tasks | Restricted depending on runtime | More flexible with background processes |
| Local filesystem | Not durable storage; `/tmp` has scoped limits | VM filesystem exists, but durable state still needs externalization |
| Startup | Generally faster | May need time to initialize VM/container |
| Scale to zero | Possible with automatic scaling | No, minimum 1 instance for a serving version |
| Direct SSH debugging | No | Yes |
| Deployment unit | Service/version via `app.yaml` | Service/version via `app.yaml` |

### Is App Engine suitable for Java/Spring?

Yes. New-generation App Engine Standard runtimes support modern Java (for example Java 21 or Java 25 within supported runtime scopes) and frameworks producing executable JARs like Spring Boot. Specific support must be confirmed against the runtime lifecycle schedule and application version.

Minimal **`app.yaml`** example for Java 21 on Standard:

~~~yaml
runtime: java21
instance_class: F2
automatic_scaling:
  min_instances: 0
  max_instances: 10
~~~

The application must adhere to the chosen runtime's contract, including startup behavior, port listening, and state management. Do not copy this `app.yaml` directly into Flexible because machine resource/runtime and scaling configurations differ.

Deploying a version:

~~~bash
gcloud app deploy app.yaml \
  --project=example-project \
  --quiet
~~~

App Engine supports splitting traffic between versions and rolling back by shifting traffic, though database migrations and side effects must still be evaluated when reverting to a previous version.

### When to keep or choose App Engine

- The project already runs stably on App Engine, using its service/version model and built-in integrations.
- The web application fits within Standard's runtimes and limits.
- The team prefers a platform-centric model with minimal cluster/VM management.
- Flexible may fit when an application needs a custom runtime while retaining the App Engine workflow.

For **new applications**, evaluate Cloud Run first because container workflows are typically more flexible for CI/CD and cover diverse workload types. However, there is no rule requiring every App Engine app to migrate immediately. Migration cost, legacy integrations, SLOs, and operational risk can make staying on App Engine a reasonable decision.

## 7. Decision Process Instead of Picking by Service Name

Before choosing a platform, the architecture team should document the actual constraints:

1. Does the application serve HTTP/gRPC, run scheduled tasks, consume messages continuously, or require long-lived processes?
2. Does it need guest OS admin rights, kernel modules, drivers, or specialized agents?
3. Can the application be containerized? Does it need Kubernetes operators, StatefulSets, DaemonSets, or a service mesh?
4. Is traffic steady or highly variable? Are fast startups or warm instances required?
5. Where does persistent state live? Can managed databases/storage be used, or are directly attached disks mandatory?
6. Can the team operate VMs/Kubernetes 24/7? Is there an existing shared platform team?
7. Do security/compliance requirements mandate specific OS, network, image, or data residency controls?
8. What are the SLOs for latency, availability, RTO, RPO, and recovery time after a bad deploy?
9. Is the annualized cost—including operational staffing and supporting services—acceptable?
10. Is there a need for multi-cloud portability, retaining Kubernetes configs, or legacy runtime compatibility?

A guiding workflow:

~~~mermaid
flowchart TD
    A["Identify workload type and SLOs"]
    B{"Need guest OS, kernel, specialized drivers?"}
    C["Prefer Compute Engine"]
    D{"Need Kubernetes API, operators,<br/>sidecars, or complex scheduling?"}
    E["Evaluate GKE Autopilot/Standard"]
    F{"Web/API app or job<br/>running in containers?"}
    G["Evaluate Cloud Run"]
    H{"Already coupled to<br/>App Engine / app.yaml model?"}
    I["Evaluate App Engine Standard/Flexible"]
    J["Compare cost, security, SLOs,<br/>complexity, and migration effort"]
    A --> B
    B -->|"Yes"| C
    B -->|"No"| D
    D -->|"Yes"| E
    D -->|"No"| F
    F -->|"Yes"| G
    F -->|"No"| H
    H -->|"Yes"| I
    H -->|"No"| C
    C --> J
    E --> J
    G --> J
    I --> J
~~~

This is a **heuristic**, not a rigid decision tree. A long-running job might run on Cloud Run Jobs, GKE Jobs, a VM, or App Engine task architecture depending on limits and goals. A containerized workload can also run on a VM. After forming a preliminary option, verify quotas/features/regions, run a proof-of-concept, and measure real data before deciding.

### Weighted Evaluation Matrix

A team can score each option on a 1–5 scale (5 being best fit) against its constraints. Example for a **stateless** Spring Boot API with fluctuating traffic and no need for Kubernetes:

| Criterion | Suggested Weight | Compute Engine | GKE | Cloud Run | App Engine |
|---|---:|---:|---:|---:|---:|
| Low operational effort | 30% | 2 | 3 | 5 | 4 |
| Elasticity with load | 20% | 3 | 4 | 5 | 4 |
| Fit for existing containers | 20% | 4 | 5 | 5 | 3 |
| Minimal deploy configuration | 15% | 2 | 3 | 5 | 4 |
| Infrastructure control | 10% | 5 | 4 | 2 | 2 |
| Leverage team skills | 5% | 3 | 2 | 4 | 3 |

**These scores are illustrative only**, not objective benchmarks, and should not be copied directly to another project. Teams must re-score based on actual skills, network constraints, application state, SLOs, and pricing quotes. Eliminate options that violate mandatory constraints first, then compare weighted totals.

## 8. Comparing Scaling and High Availability

Scaling is more than “adding instances”. Consider autoscaling signals, warm-up times, downstream connection limits, load balancing capabilities, and recovery plans when a zone/region fails.

| Topic | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Common scaling unit | VM/MIG instance | Pod and node | Service instance, task, or worker depending on resource type | Instance/version |
| Scaling signal | CPU, load balancing, Monitoring metrics, schedules, etc. with MIG | HPA, custom metrics, node autoscaler, and controllers | Requests/concurrency/CPU/backlog depending on workload type and config | Automatic/basic/manual modes with corresponding signals |
| Warm-up responsibility | Startup script/process, health check | Image pull, startup/readiness probes | Image startup, concurrency, and min instances | Runtime/version startup, min instances per environment |
| Rolling updates | MIG updater or team-organized pipeline | Deployment controller, GitOps, progressive delivery | Revisions and traffic splitting for services | Versions and traffic splitting |
| HA | Regional MIG + LB, multi-zone and state design | Regional cluster/node/Pod topology, probes/PDBs | Platform manages provisioning; team still designs dependency availability | Platform manages instances; team still designs dependencies |

### Cold starts and request latency

Cloud Run services and App Engine Standard automatic scaling can scale down resources when idle. A new request may require spinning up an instance; with Spring Boot, JVM startup time, class loading, database connections, and bean initialization all contribute. You can:

- Optimize startup and avoid loading large datasets at boot time.
- Choose appropriate concurrency and avoid holding unnecessary connections.
- Use minimum instances when latency SLOs demand it while weighing cost.
- Use readiness/health checks and measure actual latency under load.

GKE or Compute Engine typically keep baseline capacity running for fast responses; however, they still incur scale-out latency when adding Pods/nodes/VMs, so not every sudden spike is served instantaneously.

### Downstream bottlenecks

An API with aggressive autoscaling can overwhelm Cloud SQL or a payment service. Estimate the maximum connection count:

~~~text
Total possible DB connections ≈ max instances/pods × max connections per instance
~~~

For example, 20 Cloud Run instances each with HikariCP `maximumPoolSize` of 10 can open up to roughly 200 database connections if every pool is fully utilized. Similarly, 40 Pods on GKE with a pool size of 10 can open up to 400 connections. This is a **theoretical configuration ceiling**, not the live connection count; measure metrics and account for other clients as well.

Never select a platform based solely on frontend autoscaling speed. Check database connection limits, queues, API quotas, and rate limiting across the entire architecture.

### Multi-zone and multi-region

- Compute Engine requires designing regional MIGs, load balancers, database HA, and appropriate backups.
- GKE requires choosing regional/zonal topology, Pod disruption budgets, topology spread, volume locations, and failover strategies.
- Cloud Run reduces instance management work, but overall availability still depends on region/service configuration and dependencies; multi-region requires separate routing/failover architecture.
- App Engine manages versions and instances within the application's region, but the application still needs a strategy for databases, external APIs, and disaster recovery.

**Platform availability does not replace data RTO/RPO.** A service may keep accepting requests yet fail to complete transactions if the database is down.

## 9. State, Storage, and Background Processing

An application designed as a stateless API generally has more runtime choices than one that persists data to local disk.

### Where should state live?

| Need | Commonly Suitable Architectural Choice |
|---|---|
| Relational SQL | Cloud SQL or another managed database service |
| Key-value/document | Firestore, Redis/Memorystore, or a fitting service |
| Durable objects/files | Cloud Storage |
| Events/messages | Pub/Sub or a suitable queue |
| Web sessions | External session store or secured cookies/session tokens |
| Local cache | Performance-only cache that tolerates data loss |
| Temporary working files | Ephemeral filesystem with clear size limits and cleanup |

Compute Engine and GKE can attach persistent disks and run stateful applications. However, **being able** to run a database on a VM/Pod does not mean **you should** self-manage a database if a managed service meets your needs. Factor in backups, replication, failover, patching, observability, and DBA skills.

### Background jobs and consumers

| Need | Compute Engine | GKE | Cloud Run | App Engine |
|---|---|---|---|---|
| Finite batch tasks | Process/VM/job scheduler | Kubernetes Job/CronJob | Cloud Run Jobs | Task architecture per environment |
| HTTP API | VM+LB | Deployment+Service/Gateway | Cloud Run Service | App Engine Service |
| Continuously running consumer | Daemon/process with supervisor | Deployment/StatefulSet | Worker pool or suitably configured service | Flexible supports background processes; Standard has restrictions |
| Scheduler | OS/systemd timer/cron | CronJob | Cloud Scheduler triggering Jobs/Workflows | Cloud Scheduler/cron service per app model |
| Custom kernel/driver needed | Possible | Standard with suitable nodes | No host kernel control | Not a primary choice |

**Do not keep an HTTP request open for hours to run background work** if it can be split into a queue + task worker. A producer → Pub/Sub → worker pattern isolates timeouts, retries, dead-lettering, idempotency, and scaling independently of the frontend. On Cloud Run, evaluate Jobs or worker pools depending on whether the task has a defined end or acts as a continuous consumer.

### Example hybrid e-commerce architecture

~~~mermaid
flowchart LR
    U["Web / mobile clients"] --> LB["HTTPS entry"]
    LB --> API["Cloud Run<br/>Orders API"]
    API --> DB["Cloud SQL"]
    API --> PS["Pub/Sub"]
    PS --> W["GKE or Cloud Run<br/>worker"]
    W --> ST["Cloud Storage"]
    W --> DB
    API --> SM["Secret Manager"]
    W --> SM
~~~

The HTTP API can use Cloud Run because it is stateless and traffic fluctuates. The worker can use a Cloud Run worker pool or GKE, depending on continuous processing needs, Kubernetes requirements, sidecars, and cost. Databases and storage hold durable state separately from instance lifecycles.

Do not use two platforms merely because a system has two components. If both the API and worker fit Cloud Run's requirements, using one platform reduces significant administrative overhead. Conversely, if the whole organization already has a standardized GKE platform, placing both components on GKE may also make sense.

## 10. Networking, IAM, and Security

Private accessibility of APIs or databases depends on VPC configuration, ingress/egress, identity, firewalls, and target services. You cannot generalize that “serverless services are always public” or “GKE/VMs are always more secure”.

### Compute Engine

- Use firewall rules, network tags, service accounts, and the principle of avoiding external IPs unless needed.
- Restrict SSH via IAM/OS Login/IAP where appropriate; never expose SSH to the entire Internet.
- Keep images/OS updated, install monitoring agents, and manage vulnerabilities.
- Scope service account permissions per policy and protect metadata credentials.

### GKE

- Configure Kubernetes RBAC, namespaces, NetworkPolicies, and workload security.
- Use Workload Identity Federation for GKE instead of service account JSON keys inside Pods.
- Scan container images, enforce admission/policy controls, and restrict service account privileges.
- Separate cluster-admin responsibilities from namespace application deployment permissions.
- Design private clusters/endpoints/egress when required.

### Cloud Run

- Attach a least-privilege runtime service account.
- Decide public/internal ingress, require IAM invoker permissions, and use identity tokens for service-to-service calls.
- Choose Direct VPC egress or an appropriate VPC connection option, verifying firewall/network routes.
- Use Secret Manager and avoid embedding secrets in images or source code.
- Cap max instances to prevent overloading downstream dependencies.

### App Engine

- Use a service account scoped appropriately to the application/version.
- Protect endpoints, configure access permissions, and verify VPC integration.
- Check Standard runtime restrictions or Flexible permissions/configurations.
- Manage secrets, dependencies, and error/log exposure just like on any other platform.

### Common permission patterns

| Principal | Required Permissions | Should Not Be Granted by Default |
|---|---|---|
| CI build identity | Read source, push to Artifact Registry, deploy to target | Modify production business data |
| Runtime identity | Read secrets and call required databases/APIs | Owner/Editor or deployment permissions |
| Operator | Read logs/metrics, execute runbooks per role | Full permissions across all projects |
| Security auditor | Read allowed audit logs/configurations | Modify runtime if unnecessary |

Every platform needs a secret rotation plan, software supply chain controls, administrative activity monitoring, and verified backup/recovery. The primary difference is whether the team enforces these controls at the VM layer, Kubernetes layer, or service configuration layer.

## 11. CI/CD, Rollout, and Rollback

A well-operated architecture does not just “deploy successfully”; it also **tracks which version is running, measures post-deploy impact, and rolls back when needed**.

| Platform | Primary Artifact | Deployment | Common Rollback Mechanism |
|---|---|---|---|
| Compute Engine | VM image, package, or container image | Startup scripts, automation, MIG rolling update | MIG rollback to a tested instance template or image update |
| GKE | Container image digest + manifests | kubectl, Helm, GitOps, Cloud Deploy | Rollout undo or revert Git/manifests/image, verify Pod Ready |
| Cloud Run | Container image digest + revision config | `gcloud run deploy` / Cloud Deploy | Route traffic back to a stable revision |
| App Engine | Source/runtime version or container per environment | `gcloud app deploy` | Route traffic back to the previous version |

### Build once, promote many

Build the artifact once in CI, scan and test it, then promote the exact same image digest across staging and production. Avoid rebuilding per environment unless necessary, because images can drift as dependencies or base images change.

Example Java container image reference:

~~~text
asia-southeast1-docker.pkg.dev/example-project/apps/orders-api@sha256:IMAGE_DIGEST
~~~

This is an illustrative path; replace `IMAGE_DIGEST` with the actual digest. Artifact Registry supports digest-based references to pin exact deployment contents. During rollout, record the mapping between commit SHA, Cloud Build ID, artifact digest, and revision/Deployment.

### Health checks and rollout gates

- **Compute Engine:** load balancer/MIG health checks and application smoke tests.
- **GKE:** startup/readiness/liveness probes, rollout status, and per-release SLIs.
- **Cloud Run:** revision Ready status, authenticated smoke tests, gradual traffic splitting.
- **App Engine:** health/traffic metrics, shifting traffic percentages between versions when appropriate.

A deployment returning exit code 0 is not enough to consider a release successful. Observe request latency, error rates, business flows, database metrics, and saturation over a representative window.

### Database migrations

Runtime rollback **does not** equal data/schema rollback. Apply the **expand-and-contract** strategy: add new structures in a backward-compatible way, deploy code capable of reading both old and new schemas, migrate data, and remove old fields only after no running instances or consumers depend on them. This matters on every platform, especially during Cloud Run traffic splitting or GKE rolling updates when two versions run concurrently.

## 12. Cost: Do Not Compare Machine Unit Prices Alone

A design that is cheap on CPU can be expensive in operations or networking; a design with higher resource charges can drastically cut administrative effort. Evaluate **Total Cost of Ownership (TCO)** instead of calculating only “1 vCPU/1 GB RAM”.

Components to estimate:

~~~text
TCO =
  compute / runtime charges
  + storage / persistent disks
  + network egress / load balancing / NAT
  + logs / metrics / tracing
  + databases / cache / messaging / secrets
  + CI/CD, artifacts, and security
  + operational labor / incidents / upgrades
~~~

| Platform | Commonly Overlooked Cost Items |
|---|---|
| Compute Engine | VMs running continuously even at low traffic, boot disks, snapshots, OS licenses, LBs, and patching time |
| GKE Standard | Unused cluster and node capacity, overprovisioned requests, network/ingress/storage, and operators |
| GKE Autopilot | Workload-requested resources, cluster charges, Pod-type features and limits, network/storage |
| Cloud Run | Min instances, CPU/memory configs, concurrency, request counts, instance-based billing, network/VPC, and downstream |
| App Engine Standard | Instance classes and scaling, versions retaining traffic, supporting services, and networking |
| App Engine Flexible | Minimum VM resources/instances, startup overhead, storage/network, and version management |

### Qualitative comparison examples

**Workload A:** 10 requests/minute at night, 1,000 requests/minute for 15 minutes midday, stateless Spring API, no custom OS needed. Cloud Run can leverage autoscaling, including scaling down during low load; always-on VMs or clusters can be inefficient if not shared with other workloads.

**Workload B:** 100 continuously running microservices with steady traffic across multiple teams that already have platform engineering and shared Kubernetes. GKE Standard or Autopilot may benefit from platform sharing, orchestration, and resource packing; Cloud Run should still be evaluated across the entire workload rather than assumed more expensive by default.

**Workload C:** Legacy Java with custom TCP services, native agent systems, and specific kernel requirements. Compute Engine can reduce upfront refactoring costs despite higher VM ops effort. Choosing Cloud Run solely for a lower bill, only to spend months rewriting the app, may worsen TCO.

Do not put made-up currency numbers into formal estimates. Use current pricing sheets, the Google Cloud Pricing Calculator, or organizational quotes, grounded in concrete assumptions for requests, runtime, memory/CPU, egress, deploy frequency, and SLOs.

### Measurements that inform decisions

1. Measure hourly requests/second, latency percentiles, CPU/memory, and idle frequency.
2. Estimate replicas/instances needed for peak load.
3. Test cold starts, database connections, and autoscaling under load.
4. Include storage/network/LB/NAT/observability costs, not just runtime.
5. Account for recurring operational hours: security patches, cluster upgrades, troubleshooting.
6. Run a pilot in a test environment to measure real metrics before committing long-term.

## 13. Portability and Platform Lock-in Risk

**Application portability** exists at multiple levels:

- **Java/Spring Boot source code** can run across many platforms if business logic avoids coupling to runtime APIs.
- **OCI container images** are generally reusable across Cloud Run, GKE, or container-running VMs, though service configurations differ.
- **Kubernetes manifests** are standardized, yet StorageClasses, LoadBalancers, Ingress, Workload Identity, or custom controllers can remain provider-specific.
- **VM images** allow moving parts of a workload, but kernels, networking, disks, bootstrapping, and operations differ.
- **App Engine `app.yaml`** and the service/version workflow have platform coupling; moving to Cloud Run/GKE may require reconfiguring deployments.

Portability does not mean zero migration cost. Databases, service accounts, Cloud Logging/Monitoring, event contracts, and networking typically require redesign during a move.

### Decoupling business logic from infrastructure

For instance, Spring Boot code should call interfaces like `OrderRepository`, `PaymentGateway`, and `EventPublisher`, with underlying implementations using Cloud SQL, Pub/Sub, or another backend. Pull configuration from environment variables or Secret Manager instead of hardcoding project IDs or service URLs.

When migrating from Cloud Run to GKE:

1. Keep the same tested image if the container contract aligns.
2. Move service/secret configurations to ConfigMaps, Secrets, or appropriate Secret Manager integrations.
3. Configure KSAs and Workload Identity Federation for GKE.
4. Declare Kubernetes Deployments/Services/Gateways, probes, and requests/limits.
5. Design autoscaling and networking.
6. Verify logs, traces, metrics, and graceful shutdown behavior.
7. Shift traffic in phases and prepare a rollback plan.

Conversely, moving from GKE to Cloud Run requires removing dependencies on clusters, nodes, or specialized sidecars that Cloud Run does not support; stateful data must be moved to durable external services.

## 14. Six Platform Selection Scenarios

### Scenario 1 — New Spring Boot API with highly variable load

The app serves HTTPS, is stateless, stores data in Cloud SQL, and has a small team without platform engineering.

**Top candidate:** Cloud Run Service. Why: no VM/cluster management, image deployment, request-driven autoscaling, and revisions/traffic splitting. Must verify cold starts, concurrency, timeouts, and database connections.

**When to change choice:** use GKE if the company already operates a standardized cluster/platform with good policies and operational cost, or when specialized service mesh/operators are required.

### Scenario 2 — 30-microservice system with GitOps and custom sidecars

The team needs multiple namespaces, custom resources, shared ingress, network policies, sidecars, and GitOps.

**Top candidate:** GKE. Evaluate Autopilot first if workloads fit its constraints; choose Standard when node control or features disallowed by Autopilot are required. Establish platform ownership, cluster upgrades, quotas, and incident response.

**When to change choice:** if most services are actually simple and the team does not want to maintain Kubernetes, consider Cloud Run for suitable services.

### Scenario 3 — Legacy accounting system with OS dependencies

An older Java app requires OS packages, specialized TCP access, vendor agents, and fixed maintenance windows.

**Top candidate:** Compute Engine, potentially combined with MIGs or HA VMs depending on statefulness. Start with a controlled lift-and-shift, then gradually externalize state and upgrade the runtime.

**When to change choice:** once OS dependencies are removed and containerization is stable, evaluate GKE or Cloud Run to reduce ops work.

### Scenario 4 — Web app currently running on App Engine Standard

The app has stable versions/traffic splits, adheres to supported runtimes, ops teams know `app.yaml`, and there are no new requirements outside the platform.

**Top candidate:** stay on App Engine if SLOs, security, lifecycle, and cost remain suitable. Schedule runtime upgrades along the support timeline while building a Cloud Run prototype to understand migration costs.

**When to change choice:** requirements for more flexible runtimes/containers, artifact unification strategies, or App Engine limitations impede development.

### Scenario 5 — End-of-day batch report generation

The task starts on a schedule, chunks data, completes in a finite duration, and does not need to serve HTTP.

**Top candidate:** Cloud Run Jobs combined with Scheduler/Workflows if runtime limits, quotas, and connectivity fit; or Kubernetes Jobs if the organization already runs GKE and needs specialized scheduling/policies.

**When to change choice:** use Compute Engine/Batch or corresponding GKE workloads if hardware, job duration, dependencies, or orchestration exceed Cloud Run Jobs limits.

### Scenario 6 — Continuously running message consumer

A worker continuously polls a data source and may receive no HTTP requests for long stretches.

**Top candidate:** Cloud Run worker pool or GKE Deployment depending on scaling mechanics, reliability, and platform requirements. If event processing can be converted into push requests to a Cloud Run Service, consider that pattern to reduce background infrastructure work.

**When to change choice:** Compute Engine may fit specialized agents/drivers, while App Engine Flexible should be examined if a legacy system already follows the App Engine model.

### Scenario 7 — A service with sensitive data processing requirements

The application requires private connectivity, workload identity, regional data residency, and controlled Internet egress.

**Candidates:** all four platforms can meet part or all of these needs depending on specific requirements. Before choosing, build a compliance matrix: ingress, egress, VPC, DNS, secret access, encryption, organization policies, logging, and auditing. If host OS control is mandatory, Compute Engine or GKE Standard has an advantage; if properly configured IAM and network protections suffice, Cloud Run/App Engine can still fit.

**Lesson:** never infer compliance purely from a platform's name. Verify actual controls against regulations and permitted configurations.

## 15. Common Architectural Thinking Pitfalls

| Hasty Assumption | Why It Goes Wrong | Better Way to Evaluate |
|---|---|---|
| Serverless is always cheapest | Min instances, request density, networking, and downstream usage can add major costs | Calculate TCO with actual workloads and billing modes |
| Kubernetes is always more professional | Managing clusters, YAML, RBAC, and debugging carries cost | Choose GKE when you genuinely need orchestration, policies, or its ecosystem |
| VMs are always slow to innovate | MIGs, image baking, IaC, and automation enable strong CI/CD | Assess automation maturity and organizational constraints |
| Cloud Run only runs HTTP APIs | It offers Jobs, worker pools, and other resource types | Classify workloads first, then check current capabilities |
| GKE Autopilot is the same as Cloud Run | Autopilot still uses Kubernetes APIs/semantics and Kubernetes constraints | Compare orchestration needs, Pod policies, and node control |
| App Engine is too old and must be deleted | Stable apps can carry heavy migration costs | Measure SLOs, runtime lifecycle, security, and opportunity cost |
| A successful deploy means the app is healthy | DBs, queues, external APIs, and user journeys can still fail | Run smoke tests, SLI/alerts, and canaries after deploy |
| VM/container has a disk so data is durable | Local disks and instance lifecycles do not guarantee business continuity | Design backups, replication, RPO/RTO, and managed storage |
| Autoscaling eliminates capacity planning | Downstream quotas or connection pools still have limits | Load-test the system end-to-end and apply rate limits |
| Running one container in two places means full portability | IAM, ingress, storage, secrets, and logging differ | Use adapter/config layers and test migrations |

### Rule: minimize ops without sacrificing requirements

A useful strategy is to **pick the highest abstraction level that still satisfies mandatory constraints**. If Cloud Run can run the application, do not spin up Kubernetes by default. If Kubernetes is needed, evaluate Autopilot before self-managing nodes. If OS/kernel customization is required, Compute Engine or GKE Standard may be justified. For stable App Engine apps, switching platforms should be driven by clear benefits rather than trends.

However, platform team availability and organizational standards are also constraints. A company with a shared GKE platform complete with dashboards, security policies, GitOps, and on-call SREs can launch a new service on GKE very quickly with little marginal cost. Conversely, a small startup will not have that same advantage.

## 16. Recording Decisions with an Architecture Decision Record

Before production deployment, write a concise **Architecture Decision Record (ADR)** that can be revisited when assumptions change.

Template:

~~~markdown
# ADR: Choose Runtime Platform for Orders API

## Context
- Workload: Spring Boot REST API, stateless
- Traffic: average / peak / idle
- Latency and availability SLOs:
- Data: Cloud SQL, Pub/Sub, Cloud Storage
- Ops team, skills, and on-call:
- IAM / network / compliance constraints:

## Options
1. Cloud Run
2. GKE Autopilot
3. GKE Standard
4. Compute Engine MIG
5. App Engine Standard/Flexible

## Mandatory Constraints
- ...

## Evaluation
| Criterion | Weight | Cloud Run | GKE | VM | App Engine |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

## Decision
- Selected platform:
- Why:
- Rejected options and reasons:

## Risks and Mitigations
- Cold starts:
- Database connections:
- Security / IAM:
- Cost uncertainty:
- Rollback / DR:

## Verification Method
- Load test:
- Smoke test:
- Measured cost:
- SLI/SLO during pilot phase:

## Revisit Trigger
- After 3 months or when technical needs change significantly
~~~

An ADR should state **assumptions and conditions for reversing the decision**. For example: “Choose Cloud Run if P95 latency stays under 300 ms with min instances ≤ 2 and monthly cost stays within budget.” When traffic grows or requirements change, the team has an objective basis to re-evaluate rather than debating on gut feel.

## 17. Practice Exercise: Choosing Platforms for Three Applications

Suppose an organization has three services:

| Application | Characteristics | Constraints |
|---|---|---|
| Orders API | Spring Boot, HTTP, stateless, fluctuating load | Needs multiple deploys/week, latency SLO |
| Billing worker | Asynchronous message processing, variable duration | Retries, DLQ, may need continuous execution |
| Legacy reporting | Older Java app, native libraries and custom OS processes | Cannot refactor immediately, requires guest OS privileges |

Carry out the following steps:

1. Document business goals and SLIs/SLOs for each application.
2. Classify workloads (request-driven, task-driven, continuously running, stateful/legacy).
3. List dependencies: Cloud SQL, Pub/Sub, external APIs, filesystems, secrets, networks.
4. Identify mandatory constraints such as custom kernel/drivers or Kubernetes-specific operators.
5. Shortlist among Compute Engine, GKE Autopilot/Standard, Cloud Run, and App Engine.
6. Build a weighted matrix of at least six criteria with explained scores.
7. For Orders API, deploy a test Spring Boot container to Cloud Run staging; record revision, image digest, startup time, and request latency.
8. For a suitable workload, build a sample Deployment/Job on a test GKE cluster (if authorized), comparing YAML, startup/rollout, and operational work.
9. For Legacy reporting, draft a VM/MIG plan including OS patching, health checks, backups, and deployment automation.
10. Use the Pricing Calculator or current price sheets to estimate costs by traffic/CPU/memory/network for each option.
11. Design security boundaries: build identity, runtime identity, IAM, VPC, secrets, and database access.
12. Write an ADR stating the initial choice, risks, unknowns, and revisit triggers.

### Expected Outcomes

- **Orders API:** Cloud Run is typically the first candidate if no special constraints exist; verify cold starts, concurrency, and database connections.
- **Billing worker:** Cloud Run Jobs, worker pool, or GKE Job/Deployment depending on processing pattern, duration, and scaling needs.
- **Legacy reporting:** Compute Engine may require the least upfront refactoring, but needs a roadmap for operational optimization and runtime upgrades.

These are directional guidelines from the prompt, not the sole valid answer. A strong submission explains why the choice remains valid or shifts if traffic, cost, or organizational skills change.

### Evaluation Criteria

- Correctly distinguishes App Engine environments and GKE modes.
- Does not choose based on raw CPU unit prices alone.
- Covers SLOs, cost, IAM, networking, data state, and rollback strategy.
- Does not confuse Cloud Run resource types.
- Includes a test-based verification plan rather than unsubstantiated claims.
- Explicitly states mandatory constraints, assumptions, and trade-offs.

## 18. Architecture Checklist Before Finalizing a Platform

- [ ] Described workload type: HTTP, event, batch, continuous worker, or legacy.
- [ ] Documented SLIs, SLOs, RTO, RPO, and peak traffic requirements.
- [ ] Separated persistent state from ephemeral state.
- [ ] Confirmed requirements for kernel/OS/native drivers or Kubernetes APIs.
- [ ] Compared GKE Autopilot and Standard when considering GKE.
- [ ] Distinguished App Engine Standard from Flexible.
- [ ] Checked Cloud Run services/jobs/worker pools against actual needs.
- [ ] Verified regions, quotas, runtime support, and platform limits.
- [ ] Reviewed service accounts, ingress/egress, VPC, IAM, secrets, and auditing.
- [ ] Estimated cold starts, concurrency, and database connection limits.
- [ ] Designed deployment, health checks, gradual rollout, and rollback.
- [ ] Prepared observability: logs, metrics, traces, dashboards, and alerts.
- [ ] Included network, storage, load balancers, and supporting services in cost estimates.
- [ ] Accounted for operational effort of OS/cluster/patching/on-call.
- [ ] Evaluated portability of images, manifests, and configurations.
- [ ] Conducted load/availability tests with realistic data.
- [ ] Recorded an ADR and conditions for revisiting the decision.

## Self-Check Questions

**1. What is the main difference between Compute Engine and Cloud Run?**

Compute Engine provides VMs where the team manages the guest OS and running processes; Cloud Run accepts container/source workloads and manages infrastructure provisioning. In return, Cloud Run restricts host OS/kernel access while reducing VM operational work.

**2. Does GKE Autopilot remove Kubernetes from the application team's responsibilities?**

No. Autopilot manages most node infrastructure; the team still uses the Kubernetes API and defines Pods/Deployments, probes, scaling policies, security, and workload access permissions.

**3. Why can't we say all App Engine apps scale to zero?**

Because App Engine Standard and Flexible behave differently. Standard automatic scaling can scale to 0 under suitable conditions; Flexible requires at least one instance for an active version.

**4. Is a Cloud Run Service the only option for every background job?**

No. Cloud Run has Jobs for finite tasks and worker pools for consumer/pull workloads. There are also GKE Jobs/CronJobs and other models depending on requirements.

**5. Why can an HTTP API with aggressive autoscaling still fail?**

Databases, queues, or downstream APIs have quotas and connection limits. When scaling rapidly, total traffic or connections from all instances can exceed dependent capacity.

**6. When is Compute Engine a better fit than GKE/Cloud Run?**

When an application needs OS/kernel control, native libraries, drivers, or VM topologies not supported by higher-level platforms; or when refactoring costs outweigh benefits in the initial phase.

**7. What causes two identical container images to behave differently on Cloud Run and GKE?**

Factors such as IAM, ingress/egress, timeouts, concurrency, CPU allocation, storage, probes, autoscaling, and service configuration differ between the two platforms.

**8. How does TCO differ from runtime pricing?**

TCO includes not just compute, but also storage, networking, observability, CI/CD, security, backups, operational labor, and incident-handling costs.

**9. Why shouldn't every older App Engine app be automatically migrated to a new platform?**

You need to assess runtime support, current SLO status, migration effort, dependencies, cost, and risk. An application currently meeting requirements may continue running effectively on App Engine.

**10. When does a multi-platform architecture make sense?**

When workloads have clearly distinct needs and the benefits of using the right platform for each outweigh the integration, operational, security, and observability overhead between them.

## References

- [Google Cloud – Choose compute options](https://docs.cloud.google.com/docs/compute-area/choose-compute-options)
- [Compute Engine – Instance groups and Managed Instance Groups](https://docs.cloud.google.com/compute/docs/instance-groups)
- [GKE – GKE and Cloud Run](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run)
- [GKE – About modes of operation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode)
- [GKE – Autopilot and Standard feature comparison](https://docs.cloud.google.com/kubernetes-engine/docs/resources/autopilot-standard-feature-comparison)
- [GKE – Autopilot mode workloads in Standard clusters](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-autopilot-mode-standard-clusters)
- [Cloud Run – Deployment options and resource model](https://docs.cloud.google.com/run/docs/resource-model)
- [Cloud Run – Instance autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud Run – Request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Cloud Run – Minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [App Engine – Choose an environment](https://docs.cloud.google.com/appengine/docs/the-appengine-environments)
- [App Engine – Flexible versus Standard](https://docs.cloud.google.com/appengine/docs/flexible/flexible-for-standard-users)
- [App Engine Standard – Java runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime)
- [App Engine Standard – Runtime support schedule](https://docs.cloud.google.com/appengine/docs/standard/lifecycle/support-schedule)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
- [Google Cloud Architecture Framework](https://docs.cloud.google.com/architecture/framework)

## Conclusion

**Compute Engine, GKE, Cloud Run, and App Engine are not four linear upgrade tiers**, but four operational models with distinct trade-offs. Compute Engine provides VM and OS control; GKE offers Kubernetes orchestration with Autopilot or Standard options; Cloud Run runs APIs, jobs, and worker workloads without cluster management; App Engine provides a service/version application model with Standard and Flexible environments.

For a new, stateless Java/Spring Boot application without special requirements, Cloud Run is usually worth evaluating first. For Kubernetes-native systems or multiple workloads needing orchestration policies/features, GKE is a natural choice. For legacy applications requiring OS customization, Compute Engine can reduce migration costs; for stable App Engine applications, keeping the platform is sometimes wiser than a hasty migration. The final conclusion must rest on **SLOs, operations, IAM, data, measured costs, and recoverability**, and be documented in an ADR for re-evaluation when requirements change.
