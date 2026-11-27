# How to Read Documentation, Reference Architectures, and the GCP Service Catalog

> **Chapter:** Google Cloud Overview  
> **Module:** CLOUD_PROVIDERS_GCP

Google Cloud has many products and many types of documentation: getting started guides, configuration docs, API references, reference architectures, operational recommendations, and pricing tables. When starting out, the challenge is usually not finding a service that can run an application, but **finding the right source of information, reading the applicable conditions, and comparing design options**.

In the **CLOUD_PROVIDERS_GCP** module, learners study how to organize organizations, projects, IAM, and VPCs; choose Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, storage, and databases; and then deploy, secure, automate releases, observe reliability, and control costs. This lesson provides a lookup map to use across all of those topics.

After studying this lesson, you will be able to:

- Choose the right type of Google Cloud documentation for the question you are trying to solve.
- Read a reference architecture, identifying data flows, security boundaries, failure points, and design assumptions.
- Group GCP services by need and explain why an option is chosen or ruled out.
- Write an architecture decision record backed by cited sources, verification conditions, and alternatives.

## 1. Map of Official Documentation Sources

No single page answers every question. Distinguish **product overview pages** from **specific technical documentation** and **reference architectures**.

| Source | When to Read? | What to Look For |
| --- | --- | --- |
| [Google Cloud Documentation](https://docs.cloud.google.com/docs) | Starting out or looking up a specific service | Overview, concepts, guides, prerequisites, troubleshooting |
| [Get started with Google Cloud](https://docs.cloud.google.com/docs/get-started) | No environment yet or unfamiliar with tools | Setting up organizations, projects, authentication, command-line tools |
| [Product Catalog](https://cloud.google.com/products) and [Products at a glance](https://docs.cloud.google.com/docs/product-list) | Wanting to know which Google Cloud services fit a need | Current product names, primary purpose, functional category |
| [Cloud Architecture Center](https://docs.cloud.google.com/architecture) | Designing, evaluating, or migrating a system | Reference architectures, topology choices, design guidance |
| [Well-Architected Framework](https://docs.cloud.google.com/architecture/framework) | Reviewing design quality | Operations, security, reliability, cost, performance, sustainability |
| Service-specific administration guides | Preparing for real-world deployment and operations | IAM, networking, configuration, limits, backups, monitoring |
| API/CLI reference and code samples | Integrating applications or automating | Parameters, data types, API versions, responses, and error codes |
| Pricing, quotas, locations, release notes, SLA | Preparing for production or evaluating changes | Unit prices, limits, supported regions, feature changes, service commitments |

**Principle for choosing sources:** Product pages explain *what* a service is for; overviews explain *how the service works*; guides show *how to implement*; API references define *exact syntax*; architecture docs explain *when and why to combine services*. When pages differ in level of abstraction, rely on technical documentation and the service's specific terms for deployment decisions.

### 1.1. Search Documentation by Question, Not Just Product Name

For example, with the requirement "transactional API, small operations team, peak traffic spikes," break it down into questions:

1. **Compute:** Do you need virtual machines, a Kubernetes container platform, or a managed application runtime? See [Choose a compute option](https://docs.cloud.google.com/docs/compute-area/choose-compute-options).
2. **Data:** What level of SQL support and consistency do transactions require? Review the overviews of Cloud SQL, AlloyDB, or Spanner before comparing features.
3. **Connectivity:** Does the app need public HTTPS, private access, or integration with internal systems?
4. **Security:** Who can invoke the API? What identity does the application use to access databases and Secret Manager?
5. **Operations and cost:** Are there concurrency limits, quotas, failure points, alerts, redundancy mechanisms, or baseline maintenance costs?

The right questions lead to the right pages much faster than searching "best Google Cloud service."

### 1.2. Workflow for Reading a Product Documentation Set

For each new service, read in this order:

1. **Overview and concepts:** understand core resources, management model, and global/regional/zonal scope.
2. **When to use / use cases:** identify suitable scenarios and design boundaries.
3. **Before you begin / quickstart:** note required APIs to enable, project, billing, IAM roles, and tools.
4. **How-to guides:** review configurations for networking, identity, data, and deployment.
5. **Security and operations:** check least privilege, backups, observability, error handling, and upgrades.
6. **Quotas, pricing, SLA, release notes:** check scalability, cost, regional availability, and recent features.
7. **API/CLI reference:** only when building automation or verifying exact parameters.

Read documentation warnings carefully: **Preview** features may have different operational terms than generally available features; quickstart examples typically optimize for running fast rather than meeting production security and operational standards.

### 1.3. Documenting Applicability Conditions and Doc Freshness

An architectural choice may be valid in one deployment region and unsuitable in another. When taking notes, always record:

- Source page URL and date checked; note the last updated/reviewed date if displayed on the page.
- API version, deployment mode, and feature release stage.
- Supported regions/zones, quotas, and limits affecting the system.
- IAM permission scope, authentication method, network connectivity, and encryption requirements.
- Load assumptions, RTO/RPO, SLA, request volume, and data transfer volume.
- Values that must be empirically measured via testing—never turn documentation example numbers into commitments.

**Short note-taking example:**

| Attribute | Example Entry for an Application |
| --- | --- |
| Requirement | HTTPS API, relational data, variable load |
| Option under evaluation | Cloud Run + Cloud SQL |
| Questions to verify | Startup time, database connection limits, private access capability |
| Conditions | Shared region between app and data; proper connection permissions; suitable backup mechanism |
| Sources to read | Cloud Run overview, Cloud SQL connections, IAM, pricing, quotas |
| Validation method | Load test, measure p95 latency, inspect logs, and estimate cost |

## 2. Understanding the "Google Cloud Context" Before Reading Diagrams

A technical diagram may omit governance details. However, resource organization, permissions, and networking determine whether a system can be deployed safely.

### 2.1. Resource Hierarchy

A common model:

~~~text
Organization (represents the enterprise/entity)
└── Folder (optional: department, environment, or team)
    ├── Project: app-dev
    │   ├── Cloud Run service
    │   └── Cloud Storage bucket
    └── Project: app-prod
        ├── Cloud Run service
        └── Cloud SQL instance
~~~

- **Organization** is the enterprise governance root if a Google Cloud organization exists; not every lab account has an organization.
- **Folder** groups resources by unit, application, or environment and can only exist beneath an organization.
- **Project** is the foundational unit owning and managing most service resources, APIs, permissions, and cost tracking.
- **Billing account** links to projects for payment, but it is a separate management concept, not a folder tier beneath a project.

IAM policies and certain organization policies can be inherited down the hierarchy. Overly broad permissions granted at the organization or folder level can affect many projects. See [Resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy).

### 2.2. Distinguishing Resource Scopes

| Concept | Accurate Understanding | Design Consequence |
| --- | --- | --- |
| **Global** | Managed globally in scope, depending on resource type | Does not automatically mean data is replicated globally |
| **Region** | Geographic area composed of zones | Choose based on latency, data residency, available services, and cost |
| **Zone** | A deployment location within a region | Running in a single zone can suffer an outage if that zone fails |
| **VPC network** | A virtual network with global scope in Google Cloud | VPC subnets have regional scope; routes, firewalls, and IP ranges must be checked |
| **Service account** | Identity used by a workload | Grant least-privilege roles per task, avoiding unnecessary long-lived credentials |

**Example:** An API in one region connecting to a database in another region can incur cross-region latency and data transfer charges. When reviewing a diagram, do not just write "Cloud Run → Cloud SQL"; ask where each resides, which connection method is used, and whether it meets disaster recovery targets.

## 3. How to Read a Reference Architecture

A **reference architecture** is a sample blueprint for learning structure and design decisions within a defined context. It may include diagrams, processing flow descriptions, service components, reference configurations, deployment guides, and trade-offs. Do not treat a sample diagram as a turnkey production deployment for every system.

The Cloud Architecture Center gathers several types of content:

- **Architecture fundamentals:** foundations such as Well-Architected, zonal/regional/multi-regional deployment patterns, and landing zones.
- **Reference architectures:** how services combine to solve a specific problem.
- **Blueprints or implementation guides:** reusable setup details and policies.
- **Architecture decision guidance:** frameworks for choosing among models, platforms, and alternatives.

### 3.1. Six Questions You Must Answer When Looking at a Diagram

1. **What are the problem and assumptions?** User count, latency, traffic, data state, regulatory requirements, team skills.
2. **Where do requests and data flow?** Who calls whom, synchronous vs. asynchronous communication, where data is stored.
3. **Where are the trust boundaries?** Public/private components, input authentication, inter-service IAM, secret handling.
4. **What is the failure domain?** Single instance, zone, region, or provider? Is there redundancy, backup, recovery?
5. **Who operates which parts?** Does the customer manage the OS, cluster, application, database, or only configuration?
6. **What limits and cost drivers scale with growth?** Requests, vCPU/RAM, uptime, storage, connections, egress.

If a question cannot be answered yet, log it as an **assumption to verify**. That becomes input for the next design phase.

### 3.2. Example: Web Application Architecture with Event Processing

The diagram below is for **educational illustration** and does not replace a concrete networking/IAM design:

~~~mermaid
flowchart TD
    U[Users] --> LB[HTTPS Load Balancer]
    LB --> API[Cloud Run: API]
    API --> DB[(Cloud SQL: transactional data)]
    API --> OBJ[(Cloud Storage: files)]
    API --> MQ[Pub/Sub: events]
    MQ --> WORKER[Cloud Run: worker]
    WORKER --> DB
    API -. logs and metrics .-> OBS[Cloud Logging / Monitoring]
    WORKER -. logs and metrics .-> OBS
~~~

Read the diagram step by step:

- **Synchronous path:** Users call the API through an HTTPS load balancer to Cloud Run; the API accesses Cloud SQL and Cloud Storage. Placing a load balancer in front of Cloud Run is an explicit configuration (for example via a serverless NEG), not something that exists automatically.
- **Asynchronous path:** The API publishes events to Pub/Sub; the worker receives and processes them. You must design for safe duplicate handling (idempotency), retries, and unprocessable messages. Delivery from Pub/Sub to the worker requires configuring an appropriate integration/subscription.
- **Data:** Cloud SQL handles relational and transactional data; Cloud Storage handles objects like images/files; they are not interchangeable.
- **Security:** Define who can call the API, service accounts for the API/worker, bucket permissions, database connectivity, and secret management.
- **Reliability:** Check backup policies, database high availability, timeouts/retries, concurrency limits, and alerting.
- **Cost:** Check database uptime or utilization, Cloud Run resources, message counts, stored data, and network egress.

**What cannot be deduced from the drawing alone:** whether Cloud SQL HA is enabled, bucket lifecycle policies, whether Cloud Run access is private or public, WAF/TLS settings, resource regions, secret mechanisms, alert thresholds, and SLO targets. You must read the accompanying narrative and configuration details.

### 3.3. Common Architectural Patterns

| Pattern | Characteristics | Questions Worth Checking |
| --- | --- | --- |
| Multi-tier Web/API | Entry point, compute, database, cache | Is the API stateless? Need connection pooling? How is cache consistency handled? |
| Event-driven | Producer, broker, consumer processing asynchronously | Delivery semantics, retries, idempotency, event ordering |
| Analytical data | Data sources, ingestion, processing, analytical warehouse | Batch or streaming, data quality, retention, and security |
| Container platform | Multiple services on Kubernetes | Who manages clusters, policies, autoscaling, upgrades, and networking? |
| Hybrid/migration | Connecting existing systems to the cloud | Bandwidth, routing, identity, synchronization, rollback capability |
| Multi-region / DR | Standby region or distributed request routing | RTO/RPO, data synchronization, failover, operational cost |

A pattern is only useful when its goals and conditions match the system you are designing. For instance, multi-region addresses certain reliability or latency requirements, but increases data synchronization complexity, recovery testing effort, and cost.

## 4. GCP Service Catalog by Need

Google Cloud offers many services, and product names can evolve over time. The table below is an **orientation map**, not an exhaustive product list or a substitute for the latest feature documentation.

| Need | Representative Services | When to Investigate? |
| --- | --- | --- |
| Virtual machines and OS control | **Compute Engine** | Apps needing VMs, OS configuration control, or lift-and-shift workloads |
| Containers and orchestration | **Google Kubernetes Engine (GKE)** | Multiple workloads needing Kubernetes, policies/orchestration, and the Kubernetes ecosystem |
| Apps/containers without managing clusters | **Cloud Run** | HTTP services, workers, jobs, or workloads suited to a managed runtime |
| File/object storage | **Cloud Storage** | Images, files, object backups, raw data, static assets |
| VM-attached storage / file systems | **Persistent Disk/Hyperdisk**, **Filestore** | Block devices for VMs or shared file systems per application needs |
| Relational databases | **Cloud SQL**, **AlloyDB**, **Spanner** | SQL/transactions with differing compatibility, performance, and scaling needs |
| NoSQL and caching | **Firestore**, **Bigtable**, **Memorystore** | Documents, large-scale key-based data access, in-memory caching |
| Analytics and pipelines | **BigQuery**, **Dataflow**, **Pub/Sub** | Analytical warehousing, batch/stream processing, event delivery |
| Networking and delivery | **VPC**, **Cloud Load Balancing**, **Cloud DNS**, **Cloud CDN**, **Cloud NAT**, **Cloud VPN**, **Cloud Interconnect** | Connectivity, routing, DNS, content delivery, hybrid networking |
| Identity and security | **IAM**, **Organization Policy**, **Secret Manager**, **Cloud KMS**, **Security Command Center** | Access control, centralized policies, secrets, keys, risk monitoring |
| CI/CD and infrastructure | **Cloud Build**, **Artifact Registry**, **Cloud Deploy**, **Infrastructure Manager/Terraform** | Building, storing artifacts, release delivery, Infrastructure as Code |
| Operations and cost | **Cloud Logging**, **Cloud Monitoring**, **Cloud Trace**, **Cloud Billing** | Collecting logs/metrics/traces, creating alerts, viewing costs, and setting budgets |

### 4.1. Choosing Compute: Compute Engine, GKE, or Cloud Run?

| Criterion | Compute Engine | GKE | Cloud Run |
| --- | --- | --- | --- |
| Primary unit | VM | Kubernetes cluster and workloads | Services, jobs, and supported workloads |
| Infrastructure control | High, self-managing many OS components | Manage Kubernetes workloads; node management differs between Standard and Autopilot | Primarily manage code/containers, configuration, and permissions |
| Scaling up/down | Configure instance groups/autoscaling as needed | Pod/node autoscaling per configuration | Platform scaling mechanics per workload characteristics |
| Typical fit | Apps needing a specific OS/VM | Many apps needing Kubernetes | Web APIs, backends, background processing with minimal infra admin |
| Things to verify | Patching, images, firewall, HA | Cluster operations, policies, networking, cost | Timeouts, concurrency, cold starts, networking, scaling, limits |

**How to decide:** If the workload does not require Kubernetes orchestration or OS administration, evaluate Cloud Run first to reduce operational effort. If Kubernetes and its capabilities are required, evaluate GKE Autopilot/Standard. If VM-level control is required, investigate Compute Engine. This is a starting point; the final decision must rest on technical constraints and testing.

### 4.2. Choosing Data Services: Start from Access Patterns

- **Cloud SQL:** managed relational database suitable for applications needing MySQL, PostgreSQL, or SQL Server within its scaling envelope.
- **AlloyDB:** PostgreSQL-compatible database worth evaluating when performance and scale requirements go beyond standard Cloud SQL options.
- **Spanner:** horizontally scalable relational database suited when distributed semantics and specialized scaling are required.
- **Firestore:** document database suited to document access models and applications needing service-managed sync.
- **Bigtable:** key-based NoSQL database for massive volumes and high throughput; not used as a standard transactional SQL database.
- **BigQuery:** analytical data warehouse; never select it for online transaction processing merely because it supports SQL queries.
- **Cloud Storage:** object storage for files and data; does not share the transactional model of a relational database.

Key questions include: data structure, transactional constraints, query patterns, latency, storage growth rate, backup needs, compatibility with existing apps, and pricing model.

### 4.3. Distinguishing Integration Components

**Pub/Sub** delivers messages/events between components; **Eventarc** routes certain event types to supported destinations; **Workflows** orchestrates multi-step tasks/API calls; **Cloud Scheduler** triggers jobs on a schedule. Do not lump these services into a single generic “job queue” concept. Choose based on trigger source, delivery/processing model, retry requirements, and observability.

### 4.4. Networking, Identity, and Operations Accompany Every Product

Compute and database choices cannot be separated from foundational layers:

- **Project, IAM, and Organization Policy**: who can configure, who can invoke, and what constraints apply.
- **VPC, subnets, firewalls, routes, load balancing**: paths traffic traverses and where access is allowed from.
- **Secret Manager/KMS**: how secrets are stored and keys managed instead of embedding credentials in source code.
- **Logging, Monitoring, and alerting**: how you know the system is healthy, overloaded, or experiencing abnormal cost spikes.
- **Cloud Billing**: costs depend on compute, databases, storage, data transfer, and traffic volume.

## 5. From Service Catalog to Verifiable Decisions

Never start from a list of “most popular services.” Start from workload attributes:

| Question | Leads to Decision |
| --- | --- |
| Is the application stateless or stateful? | Independent compute or state persistence and session strategy |
| Synchronous requests or background processing? | API/service or message-based worker, scheduler, workflow |
| Need VM/OS or Kubernetes? | Compute Engine, GKE, or Cloud Run |
| Is data relational and transactional? | SQL family rather than object store/warehouse |
| How must data be protected? | IAM, secret management, encryption, networking, retention, and backups |
| What are the SLO, RTO, RPO targets? | HA policies, backups, recovery, multi-region, and testing |
| What are the load and cost forecasts? | Scaling caps, storage tiers, egress, estimates, alerts |
| How much can the team operate? | Managed service level vs. self-managed scope |

A concise **Architecture Decision Record (ADR)** can include:

~~~text
Decision: Choose Cloud Run for the booking API
Context: HTTPS API, variable load, small operations team
Options considered: Compute Engine, GKE, Cloud Run
Rationale: Fits a managed service model; no Kubernetes required
Conditions: Verify timeouts, concurrency, Cloud SQL connectivity, and IAM
Trade-offs: Subject to platform limits; must test cold starts and load
Reliability: Verify HA/backups for data; define SLOs and alerts
Cost: Compare estimates against realistic traffic, database, logs, and egress
Sources: Documentation URL + date checked
Test results: To be added after load testing and security review
~~~

The value of an ADR lies in its **rationale and applicability conditions**, not just the final service name.

## 6. End-to-End Scenario: Designing a Scheduling Service

A development team needs to build a customer scheduling application:

- HTTPS API storing bookings and payment status; requires consistent transactions.
- Low baseline traffic with sharp bursts; the team does not specialize in Kubernetes operations.
- Users upload illustrative images; confirmation notifications can be processed asynchronously.
- Separate test and production environments; must monitor errors, latency, and cost.

**Step 1 — Summarize requirements:** Define latency targets (e.g., p95), expected request volume, data scale, sensitive data, budget, and RTO/RPO. These numbers must be agreed upon by product and operations—not guessed from a sample architecture.

**Step 2 — Choose the application platform:** Cloud Run is the first candidate because the workload is an API and the team wants to minimize infrastructure management. GKE can be considered later if specific Kubernetes needs arise; Compute Engine fits when custom VM or OS requirements exist.

**Step 3 — Choose storage:** Cloud SQL is the candidate for relational transactional data; Cloud Storage handles images/files. Check database connection counts as Cloud Run scales, timeouts, backup mechanics, and recovery plans. For higher demands, compare AlloyDB/Spanner against the specific workload.

**Step 4 — Decouple background tasks:** The API publishes events to Pub/Sub and a worker handles notifications. Design idempotency using event/transaction IDs because tasks can be redelivered; define retries, dead-letter queues, or exception handling if needed.

**Step 5 — Protect resources:** Use separate service accounts for the API and worker, grant least privilege, keep secrets outside source code, restrict network paths, and address user authentication and input validation. Separating dev/prod projects clarifies resources, permissions, and costs.

**Step 6 — Deploy and operate:** Use Artifact Registry to store images, Cloud Build/Cloud Deploy or an appropriate pipeline to release, Cloud Logging/Monitoring to observe, and establish dashboards and alerts for errors, latency, success rates, and costs.

**Step 7 — Evaluate the architecture:** Test load spikes, database disconnections, event retries, backup restores, permissions, and cost estimates against realistic usage. Every reference architecture must pass through this step before production.

### 6.1. Illustrating Existing Resource Discovery with gcloud

The following commands are **read-only** against a project your account can access, helping cross-check a drawn architecture against real resources. Replace uppercase placeholders with your environment's ID/region and authenticate the Google Cloud CLI before running.

~~~bash
# View project details
gcloud projects describe PROJECT_ID

# View currently enabled APIs
gcloud services list --enabled --project=PROJECT_ID

# View Cloud Run services in a region
gcloud run services list --region=REGION --project=PROJECT_ID

# View VPC networks
gcloud compute networks list --project=PROJECT_ID

# View buckets the account is permitted to list
gcloud storage buckets list --project=PROJECT_ID
~~~

If a command returns a permission error, verify IAM first; never grant yourself broad roles just to make a command succeed. An empty list can also result from specifying the wrong project/region or resources belonging to a different service.

### 6.2. Signals to Monitor After Deployment

| Signal | Meaning | Action on Anomaly |
| --- | --- | --- |
| HTTP error rate / business errors | User experience and service health | Trace logs, dependencies, recent release changes |
| p50/p95/p99 latency | User responsiveness | Inspect cold starts, database, network, and traffic |
| Instance count, concurrent requests, DB connections | Scaling pressure | Check scaling caps and connection pools |
| Retry count, event backlog | Background processing health | Inspect workers, idempotency, input errors |
| Storage size and growth rate | Storage and backup forecasting | Configure data lifecycle policies, plan budget |
| Cost by project/service | Efficiency and budget overrun risk | Compare against baseline, forecast, and cost drivers |

**Cost note:** Budget alerts notify when thresholds are reached; do not assume every budget alert automatically stops all services. Cloud Billing documentation distinguishes between budget types and scopes, so read the exact terms before relying on budgets as a spend-control mechanism.

## 7. Using the Well-Architected Framework to Critique a Design

The Google Cloud Well-Architected Framework organizes guidance into six pillars. Apply each pillar as a set of review questions:

| Pillar | Critique Questions for the Scheduling App |
| --- | --- |
| **Operational excellence** | Who receives alerts? Are there runbooks, rollbacks, observability, and a backup testing schedule? |
| **Security, privacy and compliance** | Is IAM least privilege? Where does personal data live? How are secrets and audit logs managed? |
| **Reliability** | What are the SLO/RTO/RPO? Does the database dependency have a single point of failure? Have restores been tested? |
| **Cost optimization** | Which components run continuously? Are there forecasts, resource labels, and data transfer optimizations? |
| **Performance optimization** | Has p95 been measured during peak hours? Can the database/concurrency handle the load? |
| **Sustainability** | Are resources right-sized? Are unnecessary workloads and stale data cleaned up? |

These six pillars are not six services. They are a structured way of questioning a technical design to uncover weaknesses. When specialized industry or technical requirements exist, also consult the relevant **perspectives** in the framework.

## 8. Common Mistakes When Reading GCP Docs and Architectures

1. **Seeing a reference architecture and deploying it verbatim.** Samples carry different assumptions about load, region, security, or objectives. Re-analyze for your workload.
2. **Picking services by product name alone.** Compare data models, access patterns, limits, operational models, and pricing.
3. **Confusing transactional SQL with a data warehouse.** Cloud SQL/AlloyDB/Spanner solve different problems from BigQuery; SQL is a query language, not a sufficient definition of system goals.
4. **Assuming managed services require zero operations.** You still have to configure IAM, networking, backups, limits, observability, error handling, and cost controls.
5. **Ignoring regions, zones, and data transfer.** This can heavily impact latency, outage exposure, data residency requirements, and cost.
6. **Copying quickstart commands straight into production.** Re-check permissions, service accounts, public access, redundancy, and secret handling.
7. **Overlooking versions and feature maturity.** Check release notes, regional support, limits, and page update dates.
8. **Equating estimated unit pricing with real-world cost.** You must also account for traffic, storage, logs, egress, baseline charges, and growth.

## 9. Self-Check Practice Exercise

**Problem:** A company needs to ingest order data from an API, store transactions, generate daily reports, and send emails after new orders arrive. The operations team is small; data must be backed up and costs must be monitored.

Follow these steps in order:

1. Find relevant Documentation and Architecture Center pages; record at least three URLs with reasons for choosing them.
2. Draw a diagram covering ingress, compute, database, event channel, report processing, and observability.
3. Choose between Cloud Run/GKE/Compute Engine; explain at least two trade-offs.
4. Distinguish the transactional store from the analytical store; decide whether BigQuery is needed from day one.
5. List at least five unknown questions to verify before production.
6. Write a short ADR covering the decision, assumptions, risks, validation plan, and alternatives.

**Reference check:** A viable option could be Cloud Run receiving the API, Cloud SQL storing orders, Pub/Sub distributing events, a worker sending emails, Cloud Scheduler/Workflows for periodic reports, and BigQuery if analytical needs justify it. Consistency, processing triggers, access permissions, backups, retries, and pricing must be verified. This is only one approach, not a mandatory answer.

### Pre-Finalization Checklist for a GCP Choice

- [ ] I can describe the workload and measurable non-functional requirements.
- [ ] I have identified the overview docs, how-to guides, APIs, quotas, pricing, and release notes.
- [ ] I understand the relevant organization/project scope, IAM, networking, and regions/zones.
- [ ] I can explain how data flows across components.
- [ ] I have compared at least one alternative and documented the trade-offs.
- [ ] I have reviewed security, backup, recovery, observability, and cost requirements.
- [ ] I have a testing plan and will update the ADR when actual results differ from assumptions.

## 10. Official References for Further Learning

All sources below are official Google Cloud pages; when using them for a real project, verify feature status, limits, and pricing at deployment time.

- [Google Cloud Documentation](https://docs.cloud.google.com/docs) — main documentation portal.
- [Get started with Google Cloud](https://docs.cloud.google.com/docs/get-started) — environment and tooling setup.
- [Products and Services](https://cloud.google.com/products) and [Products at a glance](https://docs.cloud.google.com/docs/product-list) — product map.
- [Cloud Architecture Center](https://docs.cloud.google.com/architecture) and [Architecture fundamentals](https://docs.cloud.google.com/architecture/fundamentals) — architecture documentation.
- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework) — design review framework.
- [Choose a compute option](https://docs.cloud.google.com/docs/compute-area/choose-compute-options) — guidance for choosing a compute platform.
- [About resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — resource organization.
- [Create and manage budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — tracking and controlling costs.
- [Google Cloud pricing](https://cloud.google.com/pricing) — pricing tables and estimation tools.

**Takeaway to keep:** Read documentation driven by technical questions, read diagrams driven by data flow and operational boundaries, and select services based on verifiable requirements. A sound decision has cited sources, explicit assumptions, documented trade-offs, and test evidence to back it up.
