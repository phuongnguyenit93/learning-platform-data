# Comparing Equivalent Services Across AWS, Azure, and Google Cloud

## 1. Purpose and How to Read This Comparison

In cloud application architecture, the question "What is the Azure or Google Cloud equivalent of AWS service X?" routinely comes up when designing new systems, evaluating multi-cloud options, or planning migrations. A product lookup table helps provide quick orientation, yet **services with similar names or functions do not necessarily share identical operational contracts, scaling limits, consistency guarantees, or pricing**.

This lesson belongs to the **Reference Architecture Patterns** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to learn how to select and map components from business requirements to networking, compute, data, and deployment models, while clearly seeing trade-offs in reliability, security, scalability, cost, and operations under Well-Architected thinking.

After this lesson, learners can:

- Map architectural capabilities across **Amazon Web Services (AWS)**, **Microsoft Azure**, and **Google Cloud** without confusing product names with underlying capabilities.
- Recognize categories with close equivalents (such as object storage) versus categories requiring redesign (such as NoSQL, queues, and serverless).
- Translate a **provider-neutral reference architecture** into three comparable implementation proposals.
- Build service selection criteria grounded in SLOs, data models, consistency levels, network/security rules, operability, and total cost of ownership (TCO).
- Plan measurable validation and migration steps instead of merely swapping product icons on a diagram.

> **Scope:** Service names and capability groupings below are technical guideposts; features, SKUs, quotas, pricing, SLAs, regional availability, and integrations evolve. Before committing to a deployment, verify current documentation and terms in your target **region**.

## 2. Map by Capability, Not by Name

The same capability—"running containers"—can be solved via Kubernetes, a managed container service, or a serverless platform. Therefore, compare across four layers:

| Comparison layer | Questions to answer | Examples |
| --- | --- | --- |
| **Functional contract** | What workloads, protocols, or data shapes does the service accept? | HTTP requests, background jobs, queues, SQL, key-value, objects. |
| **Non-functional properties** | What are scaling limits, latency, consistency, HA, DR, and SLOs? | RPO/RTO, throughput, cold start duration, event ordering. |
| **Operations and security** | Who manages OS, patches, backups, IAM, private networking, logs, and encryption keys? | Self-managed VMs vs. managed database services. |
| **Cost and constraints** | Billed by time, requests, storage, or transfer? Egress, licensing, or lock-in? | Paying per VM-hour vs. paying per request. |

Equivalence can be graded at three levels:

1. **Close equivalent:** same resource category and core consumption model, though SLAs, quotas, configs, and pricing still need checking.
2. **Equivalent in purpose:** solves the same general need, yet APIs, behaviors, operability, or programming models differ.
3. **No one-to-one equivalent:** requires combining multiple services or redesigning parts of the application and data model.

For instance, **Amazon S3 ↔ Azure Blob Storage ↔ Google Cloud Storage** are all object stores with fairly close purpose equivalence. By contrast, **Amazon SQS ↔ Azure Service Bus ↔ Google Cloud Pub/Sub** is only a starting comparison: SQS is a work queue, Service Bus offers queues/topics and broker features, and Pub/Sub centers on topic–subscriptions. Dispatching targeted HTTP tasks on Google Cloud may instead call for **Cloud Tasks**.

## 3. Accounts, Organizations, Networking, and Traffic Delivery

The table below focuses on architectural roles. A cell listing multiple names indicates **multiple services collaborating** to deliver the corresponding capability.

| Capability | AWS | Azure | Google Cloud | Architectural notes |
| --- | --- | --- | --- | --- |
| Org hierarchy & governance | AWS Organizations, Control Tower | Management groups, subscriptions, Azure Policy, landing zones | Organization, folders, projects, Organization Policy | Billing, resource, permission, and quota boundaries differ. |
| Identity & access management | IAM, IAM Identity Center | Microsoft Entra ID, Azure RBAC | Cloud IAM, Cloud Identity | Distinguish users, workload identities, roles, policies, and federation. |
| Virtual private network | Amazon VPC | Azure Virtual Network (VNet) | Virtual Private Cloud (VPC) | AWS VPC and Azure VNet are regional; Google Cloud VPC is global with regional subnets. |
| Subnets | VPC subnets | VNet subnets | VPC subnets | Subnet/zone boundaries differ; never copy CIDR layouts mechanically. |
| Traffic filtering | Security Groups, Network ACLs | Network Security Groups, Azure Firewall | VPC firewall rules, Cloud NGFW | Stateful/stateless semantics, rule priorities, and attachment points differ. |
| Private service access | VPC endpoints, AWS PrivateLink | Private Endpoint, Azure Private Link | Private Service Connect | Check private DNS, connection direction, endpoint types, and supported services. |
| Outbound NAT | NAT Gateway | Azure NAT Gateway | Cloud NAT | Check IP/port limits, logging, and egress charges. |
| VPN & dedicated links | Site-to-Site VPN, Direct Connect | VPN Gateway, ExpressRoute | Cloud VPN, Cloud Interconnect | Differ in BGP routing, availability SLAs, bandwidth, and peering locations. |
| DNS resolution | Route 53 | Azure DNS, Azure Private DNS | Cloud DNS | Public and private DNS require separate designs. |
| Content delivery | CloudFront | Azure Front Door/CDN | Cloud CDN | Differ in WAF integration, caching, origin types, and global capabilities. |
| HTTP(S) load balancer | Application Load Balancer | Application Gateway, Azure Front Door | Application Load Balancer | Pick regional vs. global scope and backend integration model. |
| L4 load balancer | Network Load Balancer | Azure Load Balancer | Network Load Balancer | Protocols, passthrough/proxy behavior, and health checks differ. |
| WAF / app protection | AWS WAF | Web Application Firewall (Application Gateway/Front Door) | Cloud Armor | Policy attachment points, protection scope, rule limits, and pricing need individual review. |

### Networking Differences Easily Overlooked

**AWS:** a VPC lives inside one region; subnets bind to a single Availability Zone (AZ). **Azure:** a VNet is regional, and a subnet can span resources across zones depending on service type. **Google Cloud:** a VPC is global, while subnets are regional resources. This directly impacts routing topologies, IP allocation, failure isolation, and IaC automation.

When migrating from AWS to Google Cloud, decide whether to consolidate or split VPCs based on isolation, organization, connectivity, firewalls, and quotas—rather than mechanically creating "one VPC per region" out of AWS habit. When moving to Azure, pay close attention to NSGs, private endpoints, and private DNS zones. Every design must clearly define **north–south** paths (users entering the app) and **east–west** paths (traffic among internal components).

## 4. Compute, Containers, Serverless, and Application Tier

| Need | AWS | Azure | Google Cloud | Equivalence and risks |
| --- | --- | --- | --- | --- |
| Virtual machines | EC2 | Azure Virtual Machines | Compute Engine | Close VM-level equivalence; machine families, disks, images, quotas, and pricing differ. |
| VM autoscaling | EC2 Auto Scaling groups | Virtual Machine Scale Sets | Managed Instance Groups | Verify health checks, autoscaling signals, and rollout strategies. |
| Managed Kubernetes | EKS | AKS | GKE | All run Kubernetes yet differ in versions, IAM, networking, node/pod models, and managed features. |
| Container orchestration without managing Kubernetes | ECS | Azure Container Apps | Cloud Run | Same broad need, but task models, requests, networking, and scaling differ noticeably. |
| Serverless container compute | Fargate (with ECS/EKS) | Azure Container Apps, Azure Container Instances | Cloud Run | No 1:1 mapping: Fargate supplies task/pod compute capacity, while Cloud Run is a service/job platform. |
| Event-driven functions | Lambda | Azure Functions | Cloud Run functions (formerly Cloud Functions) | Runtime limits, triggers, concurrency, cold starts, and timeouts differ. |
| Web app PaaS | Elastic Beanstalk, App Runner | Azure App Service | App Engine, Cloud Run | Runtime control, deployment flows, and private networking differ. |
| API management | API Gateway | API Management | API Gateway, Apigee | Basic API gateways and enterprise API management platforms are two distinct tiers. |
| Workflow orchestration | Step Functions | Durable Functions, Logic Apps | Workflows | Compare state models, retries, timeouts, integrations, and pricing limits. |
| Build & deployment | CodeBuild/CodePipeline, CodeDeploy | Azure DevOps Pipelines, GitHub Actions | Cloud Build, Cloud Deploy | Shared CI/CD tools can work, though credentialing and release integrations differ. |
| Image registry | Elastic Container Registry (ECR) | Azure Container Registry (ACR) | Artifact Registry | Verify replication, vulnerability scanning, pull permissions, and retention. |

### When to Choose VMs, Kubernetes, PaaS, or Serverless?

- **VMs** fit when you need OS control, specific system dependencies, or hard-to-repackage software. The trade-off is owning patching, scaling, hardening, and operations.
- **Managed Kubernetes** helps when many services share one orchestration model, workload placement policies, and the Kubernetes ecosystem. You still govern configs, cluster upgrades, networking, permissions, capacity, and cost.
- **PaaS/serverless containers** fit web APIs or jobs with compatible interfaces when minimizing server management. Verify startup times, request limits, sessions, concurrency, database connectivity, and scale-to-zero behavior.
- **Functions** excel at small, short, independent event handlers. Never force a long-running or locally stateful process into a function just because all three clouds offer a "functions" product.

**Example:** A Java order-processing API with long-lived sessions accessing PostgreSQL can run on ECS/EKS, Azure App Service/AKS, or Cloud Run/GKE. The right choice depends on concurrency patterns, max DB connections, private connectivity, session handling, and load-test results—not merely the Java runtime or container image.

## 5. Storage, Databases, and Data Analytics

| Data capability | AWS | Azure | Google Cloud | Verify before choosing |
| --- | --- | --- | --- | --- |
| Object storage | S3 | Blob Storage | Cloud Storage | APIs, tiers, lifecycles, versioning, events, IAM, egress, and metadata differ. |
| VM block storage | EBS | Managed Disks | Persistent Disk, Hyperdisk | IOPS/throughput, snapshots, attachment rules, and multi-attach mechanics. |
| Managed file shares | EFS, FSx (by protocol) | Azure Files, Azure NetApp Files | Filestore, Google Cloud NetApp Volumes | NFS/SMB, ACLs, performance, HA, and regional availability. |
| Managed PostgreSQL | RDS for PostgreSQL | Azure Database for PostgreSQL – Flexible Server | Cloud SQL for PostgreSQL | Confirm extensions, versions, HA, read replicas, backups, networking, and limits. |
| Managed MySQL | RDS for MySQL | Azure Database for MySQL – Flexible Server | Cloud SQL for MySQL | Replication, PITR, and failover are not identical by default. |
| Managed SQL Server | RDS for SQL Server | Azure SQL Managed Instance/SQL Database (feature-dependent) | Cloud SQL for SQL Server | Evaluate engine compatibility, SQL Server features, and licensing. |
| Cloud-optimized relational | Aurora | No identical counterpart; pick Azure SQL/PostgreSQL by workload | AlloyDB for PostgreSQL (for matching needs) | Aurora, Azure SQL, and AlloyDB differ in storage architecture and features. |
| NoSQL document/key-value | DynamoDB | Azure Cosmos DB for NoSQL | Firestore; Bigtable for certain other access patterns | **Not 1:1** in partition keys, queries, transactions, consistency, APIs, or billing. |
| Distributed cache | ElastiCache | Azure Managed Redis | Memorystore | Verify engine/versions, Redis compatibility, topology, failover, and pricing. |
| Data warehouse | Redshift | Azure Synapse Analytics, Microsoft Fabric Warehouse | BigQuery | Compute/storage separation, SQL dialects, concurrency, and query billing differ. |
| Stream/event processing | Kinesis Data Streams, Managed Service for Apache Flink | Event Hubs, Stream Analytics | Pub/Sub, Dataflow | Match ingestion, stream processing, and retention cleanly. |
| ETL / data orchestration | Glue | Azure Data Factory | Dataflow, Cloud Data Fusion, Workflows (problem-dependent) | Pipeline orchestrators differ from distributed processing engines. |
| Centralized backup / DR | AWS Backup, Elastic Disaster Recovery | Azure Backup, Site Recovery | Backup and DR Service | Per-workload support, recovery regions, and restore-testing capabilities differ. |
| Database migration | AWS Database Migration Service | Azure Database Migration Service | Database Migration Service | Engine support, CDC, DDL handling, targets, and conversion limits must be verified. |

### Three Comparisons Worth Examining Deeply

**1. Relational (RDBMS):** Comparing RDS for PostgreSQL ↔ Azure Database for PostgreSQL ↔ Cloud SQL for PostgreSQL makes sense at the engine level. Yet RPO, HA mechanics, read replicas, connection limits, extension versions, logical replication, superuser privileges, backups, and point-in-time recovery can differ. **Amazon Aurora PostgreSQL-compatible** is not a strict mirror of managed PostgreSQL on the other two clouds.

**2. NoSQL:** DynamoDB centers on partition keys, sort keys, and secondary indexes; Cosmos DB for NoSQL has its own partitioning, query/indexing engine, and consistency choices; Firestore is a document database with distinct query rules, transactions, indexes, and limits. Bigtable is a wide-column store suited for high-throughput key-range workloads exceeding some DynamoDB patterns, yet is not API-compatible. Start from **real access patterns**, not the generic label "NoSQL."

**3. Cache:** Redis/Valkey powers caches, sessions, rate limiters, and fast data structures. When switching services, verify command compatibility, clustering, eviction, TTLs, persistence, failover, subnet placement, auth, and pricing. A cache is not an authoritative data store by default; define how lost data is rebuilt.

## 6. Messaging, Events, and Asynchronous Tasks

| Need | AWS | Azure | Google Cloud | Notes |
| --- | --- | --- | --- | --- |
| Consumer work queue | SQS | Service Bus queues | Cloud Tasks (especially HTTP tasks), Pub/Sub for subscription processing | Receipt, ACK, retry, and consumer-scaling models differ. |
| Event pub/sub | SNS, EventBridge | Service Bus topics, Event Grid | Pub/Sub, Eventarc | Distinguish durable messaging, event routing, and SaaS/cloud integrations. |
| Event bus / routing | EventBridge | Event Grid | Eventarc | Sources/targets, filters, schemas, and delivery behaviors differ. |
| High-volume event streaming | Kinesis Data Streams, MSK | Event Hubs | Pub/Sub or Managed Service for Apache Kafka (as needed) | Differ in retention, partitions, ordering, consumers, and protocols. |
| Job orchestration | Step Functions | Durable Functions, Logic Apps | Workflows | Retries, compensation, callbacks, and timeouts are key differentiators. |

### Why Queues Are Not Automatically Equivalent

Suppose a system creates an order, emits an event, and updates inventory:

~~~text
Order created
    ↓
Outbox in same transaction as order write
    ↓
Publisher reads outbox → Broker
    ↓
Consumer updates inventory
    ↓
Acknowledge / retry / dead-letter
~~~

Whether using SQS, Service Bus, or Pub/Sub, the architecture must answer:

- **Delivery guarantees:** generally design for duplicate delivery; consumers need an **idempotency key** or deduplication safeguard. Never assume exactly-once execution for external side effects.
- **Ordering:** is per-order ordering required, or only eventual correctness? FIFO queues, sessions, and ordering keys carry distinct limits and behaviors.
- **Retries and poison messages:** cap retry counts, configure dead-letter queues/subscriptions, build replay tooling, and alert on backlogs.
- **Retention:** retention duration, TTLs, visibility lock/ACK deadlines, and slow-consumer handling.
- **Data flow:** must one command go to one worker, or must one event fan out to multiple subscribers? That is an architectural choice between a work queue and pub/sub, not a mere SDK swap.
- **Private access and security:** service identities, keys, encryption, queue/topic permissions, networking, and auditing.

For example, an image-processing service receiving scheduled/retryable HTTP commands fits SQS + workers on AWS, Service Bus queues + workers on Azure, or Cloud Tasks + Cloud Run on Google Cloud. If that same "image uploaded" event must feed three independent consumers, SNS/EventBridge, Event Grid/Service Bus topics, or Pub/Sub/Eventarc are better matches.

## 7. Observability, Security, and Infrastructure as Code

| Capability | AWS | Azure | Google Cloud | Comparison principle |
| --- | --- | --- | --- | --- |
| Metrics/logs/alerts | CloudWatch | Azure Monitor, Log Analytics | Cloud Monitoring, Cloud Logging | Check ingestion limits, cardinality, retention, and observability pricing. |
| Application performance tracing | X-Ray / OpenTelemetry integration | Application Insights | Cloud Trace | Standardize on OpenTelemetry trace context for portability and correlation. |
| Admin audit logs | CloudTrail | Azure Activity Log | Cloud Audit Logs | Separate control-plane auditing from data-plane access logs. |
| Secrets management | Secrets Manager, Systems Manager Parameter Store | Key Vault | Secret Manager | Secret lifecycles, rotation, identities, and access boundaries. |
| Encryption key management | KMS, CloudHSM | Key Vault Keys, Managed HSM | Cloud KMS, Cloud HSM | BYOK/HYOK, key residency, and issuance controls differ. |
| Security posture | Security Hub, GuardDuty | Microsoft Defender for Cloud | Security Command Center | Signal coverage, enablement models, and billing differ. |
| Governance policy | AWS Config, Organizations policies | Azure Policy | Organization Policy, policy tooling | Preventive, detective, and remediation mechanisms differ. |
| IaC & declarative config | CloudFormation, CDK | ARM templates, Bicep | Infrastructure Manager (Terraform), Config Connector | Terraform spans clouds, yet providers and modules remain cloud-specific. |

**OpenTelemetry, Kubernetes, and Terraform** reduce switching friction at specific layers, yet never erase platform differences. A Kubernetes Deployment YAML looks similar across clouds, but ingress, load balancers, CSI storage, workload identity, network policies, and autoscalers must still be re-engineered. A Terraform module written for an AWS VPC cannot turn into an equivalent Azure VNet simply by replacing "aws" with "azurerm."

The **shared responsibility model** must also be remapped when switching services: the provider operates underlying infrastructure layers, while your organization remains responsible for permissions, configuration, data, application security, compliance, and recovery plans within each service's boundary.

## 8. Reference Architecture Pattern: Web/API and Order Processing

### Hypothetical Requirements

An e-commerce platform needs:

- A public API behind HTTPS, WAF, and rate limiting; the backend accepts no traffic bypassing approved ingress.
- An autoscaling stateless application targeting **99.9% monthly availability** as an illustrative goal, not an SLA guarantee.
- PostgreSQL storing orders; object storage holding files; a cache accelerating frequent reads.
- When an order commits successfully, an event triggers email notifications and inventory updates; consumers tolerate duplicate delivery.
- Private connectivity to data stores, least-privilege secrets, centralized metrics/logs/traces, plus backups and tested restores.
- Initial deployment in **one region spanning multiple zones where services support it**. Full-region failure requires an explicit DR design, not an inference from multi-zone deployment.

### Platform-Neutral Logical Diagram

~~~mermaid
flowchart TD
    U[Users / partner apps] --> D[DNS + CDN + WAF]
    D --> G[HTTPS ingress / API gateway]
    G --> A[Stateless app / autoscaling]
    A --> DB[(Managed PostgreSQL / HA)]
    A --> C[(Managed cache)]
    A --> O[(Object storage)]
    A --> OB[(Transactional outbox)]
    OB --> P[Publisher]
    P --> Q[(Queue / event broker)]
    Q --> W[Background workers]
    W --> X[Email / warehouse / partners]
    A -. telemetry .-> M[Metrics / logs / traces]
    W -. telemetry .-> M
    DB -. backup/restore .-> R[Backups and DR plan]
~~~

The diagram depicts **roles**, not vendor lock-in. In production, the outbox is typically a **table inside the same database/transaction as the order** (drawn separately here for clarity), from which a publisher relays events to the broker. This mitigates "order committed without emitting event," while still requiring consumer deduplication when the publisher retries.

### Reference Configuration Per Cloud

| Logical component | AWS option | Azure option | Google Cloud option |
| --- | --- | --- | --- |
| DNS, edge, WAF | Route 53 + CloudFront + AWS WAF | Azure DNS + Front Door + WAF | Cloud DNS + External Application Load Balancer/Cloud CDN + Cloud Armor |
| HTTPS ingress | ALB or API Gateway as needed | Application Gateway or API Management as needed | External Application Load Balancer or API Gateway as needed |
| Backend containers | ECS/Fargate, or EKS | Container Apps, or AKS | Cloud Run, or GKE |
| PostgreSQL HA | RDS for PostgreSQL Multi-AZ | Azure Database for PostgreSQL Flexible Server with matching HA | Cloud SQL for PostgreSQL with matching HA config |
| Cache | ElastiCache | Azure Managed Redis | Memorystore |
| Object storage | S3 | Blob Storage | Cloud Storage |
| Background work | SQS + workers | Service Bus queue + workers | Cloud Tasks or Pub/Sub + workers by semantics |
| Secrets & workload identity | Secrets Manager + IAM role | Key Vault + Managed Identity/RBAC | Secret Manager + service account/IAM |
| Telemetry | CloudWatch and tracing | Azure Monitor + Application Insights | Cloud Monitoring + Logging + Trace |
| Backup & recovery | Backups/snapshots and RDS recovery | Service-native backups/PITR | Service-native backups/PITR |

**Distinguish options inside the same cell:** ALB and API Gateway do not fully replace each other; App Gateway and API Management solve different layers of responsibility. Cloud Tasks fits directed task execution, whereas Pub/Sub fits publish–subscribe fan-out. Pick one concrete stack only after locking down application boundaries and protocols.

### Non-Negotiable Design Points

**Reliability:** Multiple zones mitigate zone failures, not region outages. Design health checks, failover, timeout/retry rules, event durability, backups, restores, and real RTO/RPO validation. Treating the cache as optional versus mandatory dictates fallback behavior.

**Security:** Keep databases on private networks, separate read/write permissions, use workload identities over static keys wherever possible, and encrypt in transit and at rest. Verify ingress, egress, private connectivity, and secret rotation on each provider.

**Performance:** Backend autoscaling can trigger PostgreSQL connection storms; enforce concurrency caps, connection pooling, and load testing. Worker scaling must respect downstream capacity and partner API rate limits.

**Cost:** Compare requests, vCPU/RAM hours, DB instances/storage/IOPS, load balancers, NAT, network egress, logging, backups, and standby environments. Never assume "serverless is always cheaper"; under steady high load or minimum-instance configs, results can flip.

**Operations:** Assign owners, SLI/SLO dashboards, actionable alerts, runbooks, restore-drill schedules, and log retention windows. Switching cloud providers never eliminates operational toil.

## 9. Comparison Pattern When Migrating an Application

Suppose an existing system runs **EKS + RDS for PostgreSQL + SQS + S3**. Two targets are under evaluation:

| Current component | To Azure | To Google Cloud | Must verify / redesign |
| --- | --- | --- | --- |
| EKS | AKS | GKE | Kubernetes version, CNI/IP planning, ingress, autoscalers, service account/workload identity, storage classes. |
| RDS for PostgreSQL | Azure Database for PostgreSQL Flexible Server | Cloud SQL for PostgreSQL | Extensions, PITR, HA, CDC, connection limits, versions, permissions, schemas, and cutover duration. |
| SQS Standard queue | Service Bus queue | Pub/Sub subscription or Cloud Tasks by processing mode | Visibility timeout/locks, ACKs, retries, delivery semantics, DLQs, idempotency, and ordering. |
| S3 | Blob Storage | Cloud Storage | SDK/API, signed URLs, metadata, lifecycles, checksums, events, encryption, transfer, and egress. |
| IAM roles for workloads | Managed Identity/Workload Identity | Workload Identity Federation/service accounts | Trust rules, least privilege, token issuance, rotation, and revocation. |
| CloudWatch/CloudTrail | Azure Monitor/Activity Log | Cloud Monitoring/Cloud Audit Logs | Log normalization, trace IDs, metric labels, retention, alerts, and cost. |

Work can be structured in five steps:

1. **Inventory:** catalog every service, runtime version, dependency, ingress/egress traffic, connection counts, data volumes, legal mandates, network layout, and identities.
2. **Contract mapping:** map functional and non-functional requirements per component; mark close equivalents versus items forcing SDK changes, storage shifts, or new event-handling behavior.
3. **Proof of concept:** stand up an end-to-end vertical slice with ingress, API, DB, queue, IAM, and telemetry; run basic fault injection, load tests, and data checks.
4. **Data/cutover planning:** pick snapshot/CDC or replication tooling, define consistency cutoffs, enforce single-writer rules, reconcile data, prepare rollback/roll-forward, and validate RPO/RTO.
5. **Deploy and verify:** monitor SLOs, business correctness, cost variance, and operational readiness; decommission old resources only after clearing acceptance gates.

Notably, **keeping the same RDBMS engine does not make migration a pure lift-and-shift**. Provider-coupled pieces like IAM, networking, metrics, backups, secrets, object-storage events, and message brokers still require redesign or reconfiguration.

## 10. Verifiable Decision Matrix

An architecture team should score **concrete implementation options**, not generic cloud brand names. Illustrative criteria:

| Criterion | Example weight | Evidence |
| --- | ---: | --- |
| Functional fit & data compatibility | 25% | API contract tests, queries, queue behavior, business outcomes. |
| Reliability & recoverability | 20% | SLOs, fault tests, backup restores, rehearsed RPO/RTO. |
| Security & compliance | 20% | Threat model, IAM, data residency, auditing, private connectivity. |
| Performance & scalability | 15% | Load-test p95/p99, concurrency, backlogs, quotas. |
| Total cost of ownership | 10% | Estimates for compute, data, egress, logs, licenses, ops staffing. |
| Team capability & operability | 10% | CI/CD workflows, runbooks, skills, support, incident recovery time. |

Score each criterion from **0 to 5** against transparent standards, then compute:

~~~text
Option score = Σ (criterion score / 5 × criterion weight)
~~~

The maximum score is 100%. **Never let a high weighted score mask a hard mandatory failure.** If an option violates data sovereignty or drops transactions beyond acceptable RPO, it **fails** regardless of how cheap or easy it is to operate.

Example: Both Cloud Run and AKS can run containers; a POC shows Cloud Run deploys faster, yet its connection and concurrency model overwhelms database connection limits without adding pooling. In that case, redesign connection pooling and re-run load tests instead of simply awarding extra points for operational simplicity.

## 11. Verification Checklist Before Approving a Mapping

Every row in a service mapping should have concrete evidence answering:

1. **API/protocol:** Are HTTP, TCP, SQL, event schemas, and client SDKs compatible?
2. **Deployment region:** Are the services/SKUs available in the required region; where do primary data and backups reside?
3. **HA/DR topology:** To what degree does it self-recover across instance, zone, and region failures? Are RPO/RTO provable?
4. **Consistency:** After a write, where is data readable, after what delay, and in what order?
5. **Limits:** What are account/project/subscription quotas, connection caps, payload limits, timeouts, backlog caps, and throughput limits?
6. **Networking:** Public/private endpoints, DNS, NAT, firewalls, egress, hybrid links, and private routing?
7. **Identity:** How do workloads authenticate, how is access audited, and are any static secrets left?
8. **Recovery:** Are backups, PITR, exports, restores, restore drills, and data rollback plans in place?
9. **Observability:** Can you trace requests, correlate logs/metrics, and reconcile business outcomes?
10. **Pricing:** Does modeling cover real/peak traffic, regional fees, networking, read/write ops, ops labor, logs, and standby environments?
11. **Operations:** Who is on call, who upgrades platforms, who grants access, and what are change/incident processes?
12. **Vendor lock-in:** Does the service rely on proprietary APIs/features, and what are future switching costs and risks?

Capture outcomes in an **Architecture Decision Record (ADR)**: context, mandatory requirements, options, POC evidence, decision, accepted risks, and review triggers. This spares the team from guessing why a service was chosen once the system is in production.

## 12. Common Misconceptions

| Misconception | Consequence | Right approach |
| --- | --- | --- |
| "Service A exists on all three clouds, so features match." | Missing network, IAM, retry, backup, or quota features during rollout. | Compare workload contracts and test every critical capability. |
| "SQS sounds like Pub/Sub, so just swap the SDK." | Duplicate processing, wrong ordering, mismatched task/event semantics. | Redesign publishing, ACKs, retries, DLQs, and idempotency. |
| "Moving DynamoDB to Cosmos DB/Firestore is just copying tables." | Wrong partitioning, indexes, queries, or consistency—raising cost and hurting latency. | Start from access patterns and data models before choosing products. |
| "Managed Kubernetes means zero cluster operations." | Accumulating security, networking, and upgrade debt. | Document a responsibility matrix between platform and app teams. |
| "Two availability zones stop every outage." | Zero recovery when an entire region goes down. | Design DR by failure domain and measure real RTO/RPO. |
| "Serverless bills per request, so it's always cheaper." | Overlooks steady traffic, minimum instances, databases, NAT, logs, and egress. | Model realistic traffic and compare full-system TCO. |
| "Terraform makes every cloud identical." | Network, IAM, LB, DB, and event differences remain. | Use IaC for reproducibility, but tailor modules and policies per provider. |
| "Swapping VPC for VNet finishes the network layer." | Broken subnets/zones, routes, DNS, firewalls, and private endpoints. | Redraw connectivity end-to-end and verify isolation. |

## 13. Practice: Comparing One Architecture Across Three Providers

A learning management platform runs a Java API, PostgreSQL, assignment file storage, background grading workers, 40,000 daily active users, and an 8x traffic spike during exams. Business requirements: data must stay strictly inside an approved region, submitted assignments must never be lost, the API must hit p95 under 400 ms at target load, and recovery must be testable within 60 minutes. These figures are **exercise assumptions**, not default SLAs.

Produce three designs—for AWS, Azure, and Google Cloud—each containing:

1. A diagram covering DNS/edge, ingress, compute, database, object storage, queue/workers, identity, observability, and backups.
2. A table of selected services, equivalence grade (close / equivalent in purpose / non-1:1), and rationale.
3. A walk-through of the "submit assignment" flow: saving metadata, saving files, writing outbox, emitting events, grading workers, retries, and deduplication.
4. A load-test plan for the 8x surge covering connection pools, queue backlogs, DB I/O, p95 latency, and autoscaling caps.
5. Single-zone failure and region-failure scenarios, clarifying when extra DR configuration is required and how replication impacts RPO.
6. A TCO estimate across major cost buckets stating assumptions for region, traffic, log retention, egress, and ops staffing.
7. An ADR selecting the best-fit option given mandatory constraints, POC outcomes, and residual risks.

**Completion criteria:** no service mapping relies on names alone; every component proves its functional contract, security, HA/DR, technical limits, and operations. An option that looks "close enough" yet breaks a mandatory constraint must be redesigned or rejected.

## 14. Official Documentation Suggestions

To verify current capabilities at implementation time, consult each provider's official product docs and architecture centers directly:

- **AWS:** AWS Architecture Center and AWS Well-Architected Framework on the official AWS documentation site.
- **Azure:** Azure Architecture Center and Azure Well-Architected Framework on Microsoft Learn.
- **Google Cloud:** Cloud Architecture Center and Google Cloud Well-Architected Framework in Google Cloud documentation.

When referencing them, always record the verification date, region, SKU/version, and link to the page describing the **specific capability** inside your ADR. A comparison table is only the starting point for a verifiable architectural decision.
