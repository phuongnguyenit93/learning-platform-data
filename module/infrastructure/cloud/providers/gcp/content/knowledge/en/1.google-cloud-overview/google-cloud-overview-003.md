# Choosing IaaS, PaaS, Serverless, and Managed Services on Google Cloud

> **Chapter:** Google Cloud Overview  
> **Topic:** Choosing IaaS, PaaS, serverless, and managed services

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from organization hierarchy, projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, automated deployment, reliability, and cost. This lesson connects those services through a critical decision: **which parts of the system will the team manage themselves, and which parts will they delegate to Google Cloud?**

No single model is best for every application. A legacy application requiring OS customization may fit a virtual machine; a new containerized API may fit Cloud Run; a platform requiring Kubernetes may need GKE; and transactional data should usually live in a managed database rather than being self-installed on a VM.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **IaaS**, **PaaS**, **serverless**, and **managed services**, while recognizing how they can overlap.
- Compare Compute Engine, GKE, App Engine, Cloud Run, and Cloud Run functions in terms of control, scaling behavior, operations, and cost.
- Pair compute layer choices with Cloud Storage, Cloud SQL, Firestore, Spanner, BigQuery, and appropriate integration services.
- Explain trade-offs around IAM, networking, stateful data, reliability, portability, and total cost of ownership.
- Propose and defend a Google Cloud architecture for a real-world deployment requirement.

## 2. Understanding Service Models Accurately

### 2.1. IaaS: Renting Infrastructure, Self-Managing Many Software Layers

**Infrastructure as a Service (IaaS)** provides compute, disks, networking, and infrastructure resources. A classic example is **Compute Engine**: you choose the virtual machine (VM) type, operating system, machine image, disks, and network configuration; Google Cloud operates the underlying physical infrastructure.

With self-managed VMs, the team is typically responsible for OS updates, runtime installation, process security, application deployment, monitoring, and recovery design. IaaS is useful when an application requires specialized OS configurations, legacy software, a long-running process, or a level of control incompatible with more abstracted platforms.

**Note:** IaaS does not mean manual operations. You can still use instance templates, managed instance groups (MIGs), autoscaling, load balancers, and Infrastructure as Code tooling to automate.

### 2.2. PaaS: Focusing on the Application and Execution Environment

**Platform as a Service (PaaS)** provides a deployment platform with many operational tasks abstracted away. **App Engine** is a representative example: developers deploy applications using supported runtimes and configurations while the platform handles much of resource provisioning and deployment.

In return, the application must conform to the platform's runtime model, lifecycle, and configuration rules. Different App Engine environments have different flexibility and resource characteristics; verify actual requirements before choosing.

### 2.3. Serverless: No Need to Provision Servers Per Workload

**Serverless** means the platform handles provisioning and operating servers for workloads under a usage-based model. **Cloud Run** runs services/containers, jobs, and suitable workloads without forcing the team to manage VMs or Kubernetes nodes. **Cloud Run functions** are well suited for function logic triggered by events or HTTP.

Serverless **does not mean there are no servers**, **is not always free when idle**, and **does not guarantee every workload scales to zero resources**. For instance, configuring minimum instances, CPU allocation behavior, workload patterns, and billing models can generate costs even at low request volume. Applications still must handle timeouts, database connections, transient errors, idempotency, and scaling limits.

### 2.4. Managed Services: Another Classification Dimension

A **managed service** is one where the provider takes on a significant share of operational work for a specific component, such as infrastructure upgrades, backups, or configured high availability. Examples: **Cloud SQL** (relational database), **Cloud Storage** (object storage), **Firestore** (document database), **Pub/Sub** (event messaging), and **BigQuery** (data analytics).

The labels **managed**, **PaaS**, and **serverless** are not mutually exclusive. Cloud Run is both serverless and a managed platform; Cloud SQL is a managed database, yet you still must choose sizing, HA configuration, backups, connectivity, and cost controls. Do not slap a single label onto an entire architecture and assume all responsibilities have been handed off.

### 2.5. Shared Responsibility Shifts by Service Layer

| Responsibility Layer | Compute Engine (VM) | App Engine / Cloud Run | Managed Data Services |
|---|---|---|---|
| Physical infrastructure | Google Cloud | Google Cloud | Google Cloud |
| OS / workload nodes | Primarily the team for VMs | Primarily the platform | Primarily the platform |
| Runtime / application dependencies | Team | Team is responsible for code and dependencies; platform handles execution infrastructure | Not applicable to application code, except user-configured logic |
| Code, permissions, and data | Team | Team | Team decides access, data model, and data lifecycle |
| Backups, scaling, and recovery | Team designs, may use supporting services | Platform supports scaling per product capabilities; app must still handle failures | Google Cloud provides features; team must **enable, configure, and test** against targets |

This table shows responsibility trends and does not replace specific product documentation or service commitments.

## 3. Compute Service Map on Google Cloud

| Service | Best-Fit Model | Control and Operational Effort | Typical Suitable Workloads | Points to Consider |
|---|---|---|---|---|
| **Compute Engine** | IaaS | High VM/OS control; team manages many layers | Legacy apps, software needing a specific OS, specialized processes | Patching, images, scaling, OS security, HA |
| **GKE Standard** | Managed Kubernetes | High cluster/node config control; must operate Kubernetes and node pools | Multi-service platforms needing Kubernetes APIs, operators, deep policies | Cluster/node complexity, upgrades, and baseline cost |
| **GKE Autopilot** | Managed Kubernetes with higher infrastructure automation | Reduced node burden; still manage Kubernetes workloads and resources | Need Kubernetes while wanting less node administration | Configuration/compatibility limits and resource-request-based billing |
| **App Engine** | PaaS | Deploy using supported runtimes and environments | Web apps/APIs aligned with the App Engine model | Runtime constraints, configuration, portability |
| **Cloud Run** | Serverless containers | Supply an image and service/job config; no server management | HTTP APIs, web apps, event handlers, batch jobs | Timeouts, concurrency, cold starts, ephemeral storage, DB connections |
| **Cloud Run functions** | Serverless functions | Write functions and configure triggers | Webhooks/small logic, event processing with clear scope | Triggers, retries, idempotency, execution limits |

**GKE is not automatically better just because you have multiple microservices.** If each service only needs standard HTTP/container execution, Cloud Run can still be simpler. Choose GKE when you genuinely need the Kubernetes ecosystem, APIs, controllers, or operational model.

## 4. Compute Layer Selection Process

Before selecting a product, document requirements using these questions:

1. **Do you need control over the OS, drivers, kernel, or special background daemons?** If yes, evaluate Compute Engine.
2. **Do you depend on Kubernetes APIs, Helm/operators, a service mesh, custom schedulers, or cluster structure?** If yes, evaluate GKE Standard and Autopilot.
3. **Can the application be packaged as a container, handle HTTP/events, or run bounded jobs?** If yes, try Cloud Run first.
4. **Does the application match App Engine's runtime model and deployment workflow?** If yes, App Engine is a reasonable PaaS option.
5. **Is the logic just a small HTTP/event-triggered function?** Cloud Run functions can streamline deployment.
6. **Is there state that must be persisted durably?** Choose dedicated storage/databases; never rely on instance memory or ephemeral filesystems to persist business data.

~~~mermaid
flowchart TD
    A["Start: workload requirements"] --> B{"Need special OS/VM control?"}
    B -->|Yes| C["Compute Engine"]
    B -->|No| D{"Depend on Kubernetes APIs/operators?"}
    D -->|Yes| E["Evaluate GKE Standard / Autopilot"]
    D -->|No| F{"HTTP container, events, or job?"}
    F -->|Yes| G["Cloud Run"]
    F -->|No| H{"Fits App Engine runtime and model?"}
    H -->|Yes| I["App Engine"]
    H -->|No| J{"Simple HTTP/event function logic?"}
    J -->|Yes| K["Cloud Run functions"]
    J -->|No| L["Revisit requirements and deployment options"]
    C --> M["Select storage, database, IAM, network, SLO, and cost"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

This diagram is an **initial filter**, not an algorithm that replaces design. For example, a containerized API may still need GKE because of an operator requirement, or a VM because of software dependencies that cannot be containerized.

### 4.1. Criteria You Must Compare

| Criterion | Specific Question | Impact on Selection |
|---|---|---|
| Control | Need a custom OS, special agents, root privileges, or highly specialized networking? | Favor VMs/GKE when more abstracted services lack support |
| Workload pattern | Short requests, batch jobs, long-running processes, GPUs, or high concurrent connections? | Determines service type and execution limits to verify |
| Load variability | Steady traffic or spiky bursts by hour/event? | Autoscaling/serverless helps with variable traffic; VMs can suit steady loads |
| State | Need a persistent filesystem, SQL transactions, session data, or queues? | Offload state to appropriate Cloud Storage/DB/queue |
| Reliability | What are the SLO, RTO, RPO, and multi-zone/multi-region requirements? | Drives HA, replication, backups, failover, and app design |
| Security and connectivity | Must data travel over private links or meet compliance constraints? | Review IAM, VPC, ingress/egress, encryption, and auditing |
| Operational capability | Does the team have Linux/Kubernetes management experience? | May prefer managed services to reduce manual overhead |
| Total cost | Have you included idle compute, clusters, DB, storage, egress, and operational labor? | Compare realistic workloads, not just unit compute prices |
| Portability | Might the application need to run outside Google Cloud later? | Standard containers are generally more portable with fewer proprietary API dependencies |

## 5. Selecting Data and Integration Services Alongside Compute

Choosing compute only solves **where code runs**. Data, events, and background jobs need corresponding architectural choices.

| Need | Services to Consider | Selection Principle |
|---|---|---|
| Images, files, exports, object backups | **Cloud Storage** | Store objects in buckets; design access permissions, storage classes, lifecycle, and data location |
| SQL transactions with PostgreSQL/MySQL/SQL Server | **Cloud SQL** | Prefer when a familiar RDBMS is needed; configure HA, backups/PITR per engine capabilities and requirements |
| PostgreSQL-compatible, enterprise performance/features | **AlloyDB for PostgreSQL** | Evaluate based on performance, compatibility, and cost requirements |
| Relational data needing massive distributed scale | **Spanner** | Assess transactional requirements, geographic distribution, and data model; avoid picking just because it sounds "big" |
| Flexible document data for applications | **Firestore** | Fits document/index access patterns; design queries and operation costs carefully |
| Large-dataset analytics, SQL reporting/warehouse | **BigQuery** | Use for analytical workloads; do not treat as a direct OLTP replacement |
| Fast-access caching and ephemeral state | **Memorystore** | Accelerates access; critical source-of-truth data still needs durable storage |
| Asynchronous event distribution | **Pub/Sub** | Design idempotent consumers, retries, and duplicate message handling |
| HTTP task queues needing execution throttling | **Cloud Tasks** | Ideal for dispatching tasks to workers with rate/retry control |
| Recurring schedules | **Cloud Scheduler** | Trigger jobs on schedule; pair with Cloud Run jobs for batch completion workflows |

**Distinguish OLTP from OLAP:** Cloud SQL/Spanner handle application transactions per their characteristics; BigQuery is built for analytical queries. Do not push every individual order insert/update into BigQuery just because the dataset might grow large.

**Distinguish Pub/Sub from Cloud Tasks:** Pub/Sub fits publishing events to one or more consumers; Cloud Tasks fits queuing and throttling specific task invocations. With both, retries can cause repeated execution, so store idempotency keys or apply deduplication mechanisms when needed.

## 6. Scenario: Building an Online Ordering System

### 6.1. Initial Requirements

A development team is building an ordering API, a web UI, nightly product catalog imports, and order confirmation notifications. Traffic spikes sharply during campaigns, the team is small, and they do not need kernel tuning or Kubernetes APIs. Order data requires SQL transactions, and product images need durable storage.

A solid starting design:

- **Cloud Run service** runs the API/container, autoscales with traffic, and enforces authentication on protected endpoints.
- **Cloud SQL for PostgreSQL** stores orders and transactions; select HA, backups, and recovery based on business targets.
- **Cloud Storage** stores images and export files; the application only stores object references in the DB.
- **Pub/Sub** delivers `OrderCreated` events to a notification consumer; the consumer guards against duplicate processing.
- **Cloud Scheduler + Cloud Run jobs** execute scheduled data imports; the job must be safe to re-run.
- **Cloud Logging / Cloud Monitoring** provide logs, metrics, and alerts; **Cloud Billing budgets** provide budget alerts.

~~~mermaid
flowchart LR
    User["Users"] --> Api["Cloud Run: Orders API"]
    Api --> Db[("Cloud SQL PostgreSQL")]
    Api --> Obj[("Cloud Storage")]
    Api --> Topic["Pub/Sub: OrderCreated"]
    Topic --> Consumer["Cloud Run: Consumer"]
    Cron["Cloud Scheduler"] --> Job["Cloud Run Job: Data import"]
    Job --> Db
    Api -. "Log / metric" .-> Obs["Cloud Logging + Monitoring"]
    Consumer -. "Log / metric" .-> Obs
    Job -. "Log / metric" .-> Obs
~~~

**This is an illustrative architecture, not a production network diagram.** You still need to add region choices, ingress, load balancing/WAF if applicable, authentication methods, Cloud SQL connectivity, service account permissions, Secret Manager, backups, and recovery procedures.

### 6.2. Why Choose Cloud Run as a Starting Point?

The API can run in a container, does not need Kubernetes nodes, and experiences campaign-driven traffic swings. Cloud Run reduces VM/cluster administration and supports configured autoscaling. Cloud SQL handles relational transactions; Cloud Storage persists objects outside instance lifecycles.

However, **API scalability does not mean the database scales infinitely**. As instance counts and concurrency grow, you must manage connection pools, DB connection limits, expensive queries, and consumer concurrency. Run load tests, set sensible max-instance limits, and monitor p95/p99 latency alongside DB errors.

### 6.3. When to Switch Approaches?

- **Move to Compute Engine:** a software vendor requires a specialized OS/driver, or a service needs a long-lived VM model.
- **Move to GKE:** multiple teams have standardized on Kubernetes and need operators/controllers, workload policies, or cluster structures that Cloud Run cannot provide.
- **Evaluate App Engine:** the application aligns well with App Engine runtimes and version/traffic splitting, and the team wants that PaaS workflow.
- **Evaluate Spanner/AlloyDB:** when transactional, scale, distribution, or PostgreSQL feature demands exceed the current setup and metrics prove the need.

Platform migrations should only happen after observing real bottlenecks, technical constraints, and total migration costs.

## 7. Illustrative Deployment of an API to Cloud Run

Assume the container image `orders-api:1.0.0` already exists in **Artifact Registry**, the project and required APIs are configured, and a dedicated service account has been created for the service. You can deploy from Cloud Shell or an environment with `gcloud` configured:

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:1.0.0 \
  --region=asia-southeast1 \
  --service-account=orders-api@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=40 \
  --timeout=60s
~~~

Replace `PROJECT_ID` with the actual project ID. The image repository, service account, and required permissions must **exist beforehand**; if the API needs access to Cloud SQL, Cloud Storage, or Pub/Sub, grant least-privilege IAM permissions to the runtime service account and configure the corresponding connections. The command above protects access using Cloud Run's authentication mechanism; any client calling the service must have an identity with the appropriate invoker permission.

The numbers `10` instances, `40` concurrent requests/instance, and `60s` timeout are just **practice assumptions**, not optimal settings for every API. Realistic load testing must validate memory, CPU, connection limits, timeouts, response times, and retry counts. Be careful never to store order data in the container's ephemeral filesystem.

If the workload is a scheduled data import, look at **Cloud Run jobs** instead of trying to hold an HTTP request open for the entire batch. If the behavior reacts to small events, evaluate **Cloud Run functions** or a Cloud Run service triggered through an appropriate event mechanism.

## 8. Security, Networking, and Resource Organization

Choosing lower operational overhead **does not hand off responsibility for protecting application data**. A baseline design should include:

1. **Organization/project boundaries:** split projects by environment and governance scope; apply IAM at the appropriate level and avoid granting project-wide permissions to every service.
2. **Workload identity:** each service uses its own service account with only required permissions; prefer short-lived identities and IAM integrations over storing long-lived service account keys in code.
3. **Ingress and egress:** decide whether APIs are public or private, and review VPC access paths, DNS, firewall rules, and connections to private databases. Cloud Run needs appropriate VPC egress configuration when reaching private resources.
4. **Secrets and data:** manage credentials with **Secret Manager** or an equivalent mechanism; configure encryption, bucket permissions, retention, auditing, and backup policies.
5. **Delivery chain:** build images via pipelines, store them in Artifact Registry, scan/approve artifacts per policy, deploy in a controlled manner, and maintain a rollback plan.
6. **Observability and incidents:** tie together structured logs, metrics, traces, alerts, SLOs, and runbooks; practice data recovery drills.

For example, configuring a Cloud Run service as publicly accessible when the API is meant to be internal-only is an **access governance error**, even though Google operates the servers. Conversely, a fully patched VM can still be insecure if firewall rules or IAM grant overly broad access.

## 9. Reliability and Cost: System-Wide Comparison

### 9.1. Reliability

Define **SLO** (Service Level Objective), **RTO** (Recovery Time Objective), and **RPO** (Recovery Point Objective) before finalizing the architecture. Autoscaling only addresses part of load resilience; you must also examine:

- **Zone/region failures:** where workloads live, distribution capability, failover, and DB access paths.
- **State and transactions:** genuinely restorable backups, migration/schema rollbacks, and consistency verification.
- **Scaling latency:** cold starts on request-driven workloads, DB pool initialization, warm-up, and concurrency thresholds.
- **Asynchronous events:** retries, dead-letter handling where appropriate, idempotency, and message ordering if business logic requires it.
- **External dependencies:** timeouts, bounded exponential backoff, circuit breakers, and graceful degradation.

Never declare an architecture “high availability” solely because it uses managed services. Many HA, backup, and replication features depend on tier, region, and explicit configuration.

### 9.2. Cost

Total cost of ownership equals **compute + database + storage + network egress + logs/monitoring + backups + operational and incident labor**. For the same application:

| Option | Cost Drivers to Track | Risks Easy to Overlook |
|---|---|---|
| Compute Engine | Running VMs by machine type, disks, IPs/networking, load balancers | Idle VMs still incur charges; patching and HA require operational labor |
| GKE | Workload/node resources or mode-specific billing, cluster management, networking, and storage | Over-provisioned capacity, Kubernetes overhead, add-ons, and operations |
| App Engine | Resources/instances and environment-specific billing | Instance counts, scaling settings, and supporting services |
| Cloud Run | CPU, memory, requests, and billing/instance configuration by workload type | Min instances, suboptimal concurrency, egress, DB not scaling alongside API |
| Cloud SQL and data services | Instances/capacity, storage, backups, I/O, and networking depending on service | DBs and backups still cost money even when the API receives few requests |

Never assume serverless is always cheaper than VMs: steady-traffic workloads with consistent resource demand may yield different economics. Model **two to three options using measured traffic**, check current unit prices with Google Cloud's pricing calculator, label resources, set budgets/alerts, and review periodically.

## 10. Decision Patterns and Common Pitfalls

| Scenario | Sensible Starting Point | What to Verify |
|---|---|---|
| Legacy Java app requiring OS tweaks and custom agents | Compute Engine | Feasibility of repackaging and VM operational cost |
| Stateless REST API, variable traffic, containerized | Cloud Run | Timeouts, cold starts, connection pooling, and scaling limits |
| Multiple services needing Kubernetes operators, CRDs, custom policies | GKE Standard or Autopilot | Workload compatibility, Kubernetes skills, node requirements |
| Web app matching App Engine runtime, wanting built-in versions and traffic splitting | App Engine | Runtime and execution environment limits |
| Small function handling uploads or events | Cloud Run functions | Triggers, retries, access permissions, and idempotency |
| Large-scale data aggregation reports | BigQuery paired with ingestion pipelines | Query patterns, update latency, and processing costs |
| Transactional SQL orders | Cloud SQL, then evaluate alternatives once metrics exist | Load capacity, backups, HA, and access patterns |

**Anti-patterns** worth avoiding:

- Choosing GKE just because a project uses microservices, when Kubernetes features are not needed.
- Self-installing a database on a VM without evaluating the backup, patching, and HA features of managed services.
- Treating Cloud Run's local instance filesystem as durable storage.
- Allowing unbounded compute autoscaling while Cloud SQL has connection limits.
- Assuming every message is processed strictly once; skipping idempotency and retry handling.
- Enabling public access or broad IAM roles assuming the platform automatically secures the entire application.
- Comparing options solely by unit compute price while ignoring operations, networking, and data costs.

## 11. Design Exercise

**Problem:** A company needs to deploy a customer support system consisting of a Java API, a web UI, file attachments, relational ticket data, and a scheduled email-sending job. Traffic spikes during business hours. The team has three developers and no Kubernetes specialists; data loss must not exceed the business-defined RPO.

Propose:

1. The compute layer for the API/web tier plus one alternative, explained by control needs, traffic shape, and operational capacity.
2. Where tickets and attachments should be stored, along with the backup/recovery policy you will test.
3. How the scheduled job will run and handle retries safely.
4. How to structure projects/environments, IAM/service accounts, ingress, and database connectivity.
5. Three operational signals and three major cost drivers to monitor.
6. Conditions that would trigger migrating from the initial solution to GKE or Compute Engine.

**Self-check hint:** A well-founded solution can start with **Cloud Run + Cloud SQL + Cloud Storage + Cloud Scheduler/Cloud Run jobs**, supplemented with monitoring, backups, and least-privilege IAM. Moving to GKE/VMs must be justified by real constraints. There are no bonus points for picking more services.

## 12. Pre-Finalization Architecture Checklist

- [ ] Documented workload characteristics (HTTP, event, batch, stateful), OS/Kubernetes needs, and runtime limits.
- [ ] Separated compute from durable data, picking appropriate services for transactions, objects, analytics, and events.
- [ ] Defined team responsibilities for applications, IAM, secrets, networking, backups, and recovery.
- [ ] Defined SLO, RTO, RPO and tested scaling, failures, retries, and DB restores.
- [ ] Compared total cost under expected traffic and configured budget alerts.
- [ ] Documented assumptions, items to benchmark, and conditions for changing the architecture.

**Final principle:** Pick the **highest level of abstraction that satisfies real-world constraints** and that the team can operate reliably; validate with testing, load data, security reviews, and cost analysis. This forms the foundation for continuing into project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage/databases, and deployment automation on Google Cloud.
