# The AWS Service Catalog and How to Choose AWS Services

## Learning Objectives

After this lesson, you will be able to:

- Look at a business requirement and identify which AWS service categories to evaluate before picking a specific product.
- Distinguish commonly confused options: EC2, ECS/EKS, Fargate, Lambda; S3, EBS, EFS; RDS/Aurora, DynamoDB; SQS, SNS, EventBridge.
- Explain why Region, Availability Zone (AZ), IAM, VPC, monitoring, backups, and cost directly affect service selection decisions.
- Propose a well-reasoned minimal architecture, state trade-offs explicitly, and validate the choice with real metrics.

**Context:** AWS (Amazon Web Services) is a cloud service ecosystem spanning virtual machines, networking, storage, and databases to integration, data analytics, and serverless. Choosing an AWS service is not about finding the "most powerful" service, but matching the right capability to your requirements for performance, security, operations, resilience, and budget.

## 1. Mindset for Reading the AWS Service Catalog

The AWS catalog is vast and continuously evolving. An effective way to learn is **moving from requirements to capability groups**, rather than trying to memorize every service name. An application usually combines several groups:

| Question to answer | Service category typically evaluated | Examples |
| --- | --- | --- |
| Where will application code run? | Compute / Containers / Serverless | Amazon EC2, Amazon ECS, Amazon EKS, AWS Fargate, AWS Lambda |
| In what form is data stored? | Storage | Amazon S3, Amazon EBS, Amazon EFS |
| How does the application query data? | Database | Amazon RDS, Amazon Aurora, Amazon DynamoDB |
| Through which path do users access the application? | Networking / Content delivery | Amazon VPC, Elastic Load Balancing, Amazon Route 53, Amazon CloudFront, Amazon API Gateway |
| How do components exchange events? | Application integration | Amazon SQS, Amazon SNS, Amazon EventBridge, AWS Step Functions |
| Who is allowed to do what, and how is data protected? | Security / Identity | AWS IAM, AWS KMS, AWS Secrets Manager, AWS WAF |
| How do we know when the system fails, how it recovers, and what it costs? | Operations / Resilience / Cost | Amazon CloudWatch, AWS CloudTrail, AWS Backup, AWS Cost Explorer, AWS Budgets |

Another perspective is grouping services by **how much infrastructure AWS manages**:

- **IaaS / high control:** EC2 lets you choose the VM, OS, and software; the team maintains many components itself.
- **Managed services:** RDS, ECS, EKS, ElastiCache, or OpenSearch Service take over part of platform operations; users remain responsible for configuration and the application.
- **Serverless / on-demand managed:** Lambda, DynamoDB, or serverless options of individual services reduce server administration and support usage-based scaling.
- **Direct-use services:** S3, SQS, EventBridge, and CloudWatch are functional building blocks with dedicated APIs; there is no need to provision a VM just to provide those capabilities.

"Managed" and "serverless" **do not mean zero operations**. You must still configure access permissions, spending limits, redundancy, alarms, testing, and application error handling.

## 2. Service Catalog by Need

### 2.1. Compute: Running Applications and Processing Jobs

| Service | Key characteristics | Choose when | Points to consider |
| --- | --- | --- | --- |
| **Amazon EC2** | Virtual machines with OS and runtime control | Legacy software, specialized OS requirements, steady workloads, or deep control needed | Requires managing patches, machine images, autoscaling, availability, and capacity |
| **Amazon ECS** | AWS-integrated container orchestration | Running multiple container services, wanting a relatively streamlined operational model | Must understand tasks, services, images, networking, and deployments |
| **Amazon EKS** | Partially AWS-managed Kubernetes | Existing Kubernetes skills/ecosystem, requiring Kubernetes APIs and tooling | Higher operational complexity, cluster management, and cost in many cases |
| **AWS Fargate** | Serverless compute for containers without managing EC2; used with ECS or EKS | Service-based containers, wanting to focus on applications | Priced by provisioned resources/runtime duration; less host customization |
| **AWS Lambda** | Event-driven functions, auto-scaling within service limits | Short APIs, webhooks, file processing, automation, and intermittent tasks | Execution time limits, cold starts, quotas, statelessness |
| **AWS Elastic Beanstalk** | Application deployment platform orchestrating underlying resources | Wanting fast deployment of traditional web apps with a familiar model | Underlying resources still need monitoring; customization follows platform mechanisms |
| **Amazon Lightsail** | Simplified resource bundles with accessible setup and pricing | Websites, demos, small low-complexity services | Less flexible as networking and system demands grow |
| **AWS Batch** | Queuing and provisioning environments for batch jobs | Data processing/reporting/rendering across many finite jobs | Jobs must be designed independently and runtime/execution costs tracked |

**Terminology note:** ECS and EKS are **orchestrators**; Fargate is a way to **provision compute** for containers. Thus, accurate comparisons are usually "ECS on Fargate" vs. "ECS on EC2," or "EKS on Fargate" vs. "EKS on EC2 nodes."

### 2.2. Storage: Object, Block, and File

| Service | Data model and access method | Use for | Avoid misunderstanding |
| --- | --- | --- | --- |
| **Amazon S3** | Objects in buckets, accessed via API/HTTP | Images, video, backups, static assets, data lakes | S3 is not an OS disk or a standard POSIX file system |
| **Amazon EBS** | Block volumes attached to compatible EC2 instances | Boot disks, filesystems, and local EC2 instance data | Volumes belong to one AZ; recovery requires snapshots/dedicated design |
| **Amazon EFS** | Shared NFS file system managed by AWS | Multiple instances/containers needing shared file-standard read/write access | Cost, latency, and access patterns differ from EBS or S3 |
| **Amazon FSx** | Managed file system families for specialized workloads | Windows file shares, Lustre/HPC, and supported file systems | Must choose the right FSx variant for the protocol/workload |
| **AWS Backup** | Centralized backup policies and recovery point management for supported services | Centralizing backup schedules, retention periods, and protection controls | Backups do not replace HA design or restore drills |

**Practical rule of thumb:** Uploaded objects like PDF invoices and product images typically go to S3; EC2 OS disks typically use EBS; directories that multiple instances must mount concurrently lead you to evaluate EFS. For S3, also evaluate S3 Storage Classes, lifecycle rules, versioning, and replication based on access, retention, and recovery needs.

### 2.3. Databases, Caching, Search, and Analytics

| Service | Data / workload type | Choose when | Watch out for |
| --- | --- | --- | --- |
| **Amazon RDS** | Managed relational DBs: PostgreSQL, MySQL, and supported engines | Transactions, SQL, JOINs, data constraints, business systems | Sizing, connections, backups, Multi-AZ, read replicas; app remains responsible for schema/queries |
| **Amazon Aurora** | MySQL/PostgreSQL-compatible relational DB with purpose-built storage | Wanting Aurora's scalability, performance, and HA characteristics | Evaluate cost and real compatibility with your workload |
| **Amazon DynamoDB** | Managed NoSQL key-value/document DB | Key-based access, highly variable load, low latency requirements, well-defined access patterns | Design partition keys, access patterns, indexes, and consistency from the start |
| **Amazon ElastiCache** | In-memory cache with supported engines | Reducing read latency, session/caching, offloading database load | Caches can expire/lose data; needs invalidation policies and cache-miss handling |
| **Amazon OpenSearch Service** | Indexing, full-text search, and log analytics | Text search, filtering, and analyzing indexed data | Typically does not replace the primary transactional data source |
| **Amazon Redshift** | Analytical data warehouse | BI/OLAP, aggregating and querying large data volumes | Data ingestion pipelines and compute/storage costs |
| **AWS Glue + Amazon Athena** | Data preparation/cataloging + querying data in S3 | Ad hoc analytics on a data lake without managing query servers | Data format quality, partitioning, and amount of data scanned |

**RDS and Aurora** both suit relational data; Aurora is a distinct database family, not simply a "faster toggle" for every RDS case. **DynamoDB** is not automatically better than RDS just for carrying the NoSQL label: if business logic involves complex relationships and multi-table transactions, a relational model may be easier to build and maintain.

### 2.4. Networking, Access, and Content Delivery

| Service | Role | Common use cases |
| --- | --- | --- |
| **Amazon VPC** | Private logical network within a Region, divided into subnets, routes, and security groups | Workload isolation, public/private segmentation, path control |
| **Elastic Load Balancing: ALB/NLB** | ALB routes Layer 7 HTTP(S); NLB handles Layer 4 connections like TCP/UDP | Multiple instances/containers needing an entry point and load distribution |
| **Amazon Route 53** | DNS and domain routing | Mapping domains to apps/entry points; applying appropriate routing policies |
| **Amazon CloudFront** | CDN delivering content close to users, integrated with edge security/compute | Static content, websites, APIs needing caching or global latency reduction |
| **Amazon API Gateway** | Managed API entry point with routing, auth, and throttling features | Lambda backends or HTTP services needing API management |
| **NAT Gateway** | Enables resources in private subnets to make outbound connections per routing | Private workloads requiring outbound Internet access; monitor cost |
| **VPC Endpoints / AWS PrivateLink** | Private connectivity to supported services without traversing the public Internet | Accessing S3 or service APIs from private networks, reducing exposure |
| **AWS Transit Gateway / Site-to-Site VPN / Direct Connect** | Connecting multiple VPCs and/or on-premises infrastructure | Multi-network topologies, hybrid cloud, or dedicated private link needs |

A **public subnet** has a route to an Internet Gateway; a **private subnet** has no direct route to an Internet Gateway. Placing an EC2 instance inside a private subnet does not automatically guarantee data security: you must still check security groups, IAM, NACLs, routing, endpoints, and application ports.

### 2.5. Application Integration and Event Processing

| Service | Pattern | Choose when | Example |
| --- | --- | --- | --- |
| **Amazon SQS** | Message queue; consumers pull and process | Decoupling producers/workers, load buffering, async retries | After payment, enqueue PDF generation |
| **Amazon SNS** | Pub/sub pushing notifications to multiple subscribers | One event needs to fan out to multiple destinations | New order notifies multiple downstream systems |
| **Amazon EventBridge** | Event bus and rules routing events | Routing by event attributes across apps/SaaS/AWS services | OrderPlaced triggers related business flows |
| **AWS Step Functions** | Workflow orchestration with steps, branches, retries, and state | Long workflows with multiple conditional tasks | Verify order → reserve inventory → record → notify |
| **Amazon Kinesis / Amazon MSK** | Data stream ingestion/processing, or managed Kafka | Event streaming, telemetry, multi-consumer data pipelines | Clickstreams, sensor telemetry |
| **Amazon MQ** | Managed message broker for supported protocols/engines | Compatibility needed with apps using traditional brokers | Migrating systems tied to AMQP/JMS and related protocols |

SQS, SNS, EventBridge, and Step Functions **do not fully replace one another**. Ask whether you need **queuing work for workers**, **broadcasting one notification**, **rule-based event routing**, or **stateful workflow orchestration**. One system can use EventBridge to route events into SQS so workers process them from the queue.

For message processing, design **idempotency** (processing the same event twice does not corrupt state), backoff retries, and dead-letter queues (DLQs) where supported. Never assume every system delivers exactly-once or strictly ordered messages without verifying configurations and real conditions.

### 2.6. Security, Governance, Monitoring, and Cost

| Service | Problem addressed |
| --- | --- |
| **AWS IAM** | User permissions, roles, policies, and least privilege |
| **AWS IAM Identity Center** | Centralized workforce access and SSO, especially in multi-account environments |
| **AWS Organizations / Service Control Policies (SCP)** | Multi-account structure and organization-level permission guardrails; SCPs do not grant permissions themselves |
| **AWS KMS** | Managing and using encryption keys across integrated services |
| **AWS Secrets Manager / Systems Manager Parameter Store** | Managing secrets or config parameters; access control by sensitivity |
| **Amazon GuardDuty / AWS Security Hub** | Threat detection and aggregating security posture/findings |
| **AWS WAF / AWS Shield** | Rule-based web request filtering and DDoS protection support per service scope |
| **Amazon CloudWatch** | Metrics, logs, alarms, dashboards; monitoring operations and errors |
| **AWS CloudTrail** | Recording API activity and administrative actions for auditing/investigation |
| **AWS Config** | Tracking resource configurations and evaluating rule compliance |
| **AWS CloudFormation / AWS CDK** | Infrastructure as Code, testable and repeatable deployments |
| **AWS Backup** | Centralized backup policies and recovery points |
| **AWS Cost Explorer / AWS Budgets** | Analyzing usage costs and setting budget alert thresholds |
| **AWS Pricing Calculator / Compute Optimizer** | Estimating deployment options and reviewing resource right-sizing recommendations |

Three tools are often needed together: **CloudWatch** answers "how is the system behaving?", **CloudTrail** answers "who/what called an AWS API?", and **AWS Config** answers "did resource configurations change and do they comply with rules?".

## 3. Mandatory Foundations Before Selecting Services

### 3.1. Regions and Availability Zones

- **Region** is a geographic area where services are deployed. Choose based on user location, data residency requirements, service availability, latency, and pricing.
- **Availability Zone (AZ)** is an isolated infrastructure zone within a Region; multiple AZs support fault-tolerant designs for individual components.
- **Multi-AZ** helps an application keep running when one AZ fails, **if** components are properly deployed and configured. Running two EC2 instances in a single AZ does not create AZ-level fault tolerance.
- **Multi-Region** serves Region-scale disaster recovery or geographic distribution needs, at the cost of higher complexity, data synchronization, and expense.
- Resource scopes differ: VPC belongs to a Region, subnets belong to an AZ; EBS volumes attach to an AZ; S3 buckets are created in a Region; IAM has global scope for the account. You must verify each service's specific behavior.

Example: an e-commerce system needing single-AZ fault tolerance can use an ALB, ECS tasks across at least two AZs, and RDS configured in Multi-AZ mode. You still must verify routing, quotas, health checks, DB connectivity, and incident recovery.

### 3.2. IAM, Networking, and the Shared Responsibility Model

Under the **Shared Responsibility Model**, AWS is responsible for security *of* the cloud infrastructure; the customer is responsible for security *in* their deployed configurations and workloads. What AWS manages varies by service type, yet responsibility for permissions, data, and application configuration always remains critical.

Minimum practices:

1. Use roles and temporary credentials for EC2, ECS tasks, and Lambda; avoid embedding long-lived access keys in source code.
2. Restrict IAM permissions to genuinely required actions/resources, control administrative access, and enforce MFA on appropriate accounts.
3. Place databases and internal workloads in private subnets when appropriate; open only required ports and paths via security groups, routes, and endpoints.
4. Use TLS in transit and encrypt data at rest as needed; manage keys and secrets with proper access control.
5. Enable logging, configure monitoring, and ensure an incident response plan exists for compromised credentials.

**Distinguishing application users from IAM:** Customers logging into a website typically use an application identity solution such as Amazon Cognito or an equivalent identity provider. IAM is primarily for access to AWS resources and APIs.

## 4. Evidence-Based Service Selection Process

Start with measurable requirements, then compare services. You can follow these six steps.

### Step 1 — Describe the Workload

Document core functionality, request patterns, data, growth rate, and operating hours:

- **Traffic:** average and peak requests/second? Event-driven spikes?
- **Compute:** how long does each request take? Continuous execution or scheduled/event-driven? Any GPU, OS, or specialized protocol needs?
- **Data:** tightly relational/SQL, key-value, files/objects, or analytics logs? What transactions and consistency levels are required?
- **Reliability:** target availability, RTO (acceptable recovery time), and RPO (maximum acceptable data loss)?
- **Security:** what sensitive data, who has access, where must data stay, how long must logs be retained?
- **People:** does the team have Kubernetes, database, or 24/7 operations expertise, or is it primarily focused on app development?
- **Budget:** normal monthly cost, peak cost, and desired alert thresholds?

When details are missing, state **assumptions to validate**. Avoid vague phrases like "needs good scalability" in place of SLOs, load figures, or budget targets.

### Step 2 — Choose the Compute Operating Model

Use these guiding questions:

~~~text
Does the app need OS/kernel control or specialized agents?
  ├─ Yes → Consider EC2
  └─ No
      ├─ Is it a short, independent function/task triggered by events?
      │    └─ Yes → Consider Lambda
      └─ Is it a long-running app/container handling many HTTP requests or workers?
           ├─ Does the team need Kubernetes? → EKS (choose EC2 or Fargate accordingly)
           └─ No Kubernetes needed → ECS (prefer comparing Fargate vs. EC2)
~~~

This tree is only a **starting point**, not an absolute rule. For instance, a low-traffic API might fit Lambda; a steady API with existing containers may fit ECS Fargate better. Validate decisions with benchmarks and cost estimates.

### Step 3 — Choose Storage and Databases from Data Characteristics

- Immutable objects/images/files or static assets → evaluate **S3**.
- VM disks → evaluate **EBS**; multiple instances needing a shared filesystem → **EFS/FSx**.
- SQL, JOINs, multi-entity transactions → start with **RDS/Aurora**.
- Key-based lookups with pre-designed access patterns → evaluate **DynamoDB**.
- Full-text search and indexed log/data analysis → add **OpenSearch**.
- Large-scale analytical queries → **S3 + Glue + Athena** or **Redshift**, depending on usage model.
- Accelerating repeated reads → evaluate **ElastiCache**, while designing cache invalidation.

Choosing a database is a major architectural decision: at minimum, test critical queries, transaction constraints, backup/restore plans, and cost forecasts before committing.

### Step 4 — Choose Synchronous vs. Asynchronous Communication

- User needs an immediate response → HTTP(S), typically pairing API Gateway or ALB with the backend.
- Work can finish later → send to **SQS**, letting independent workers process and update state.
- One event must notify multiple targets → evaluate **SNS** or **EventBridge** based on subscriber/routing needs.
- Multi-step workflows with state, retries, and conditional branches → **Step Functions**.
- Data streaming requiring independent stream consumers → **Kinesis/MSK** when genuinely needed.

### Step 5 — Check Cross-Cutting Constraints

**Security:** IAM, secrets, encryption, VPC, access control, auditing. **Reliability:** Multi-AZ, retries, backup/restore, failover. **Observability:** metrics, logs, tracing, alarms. **Operations:** CI/CD and Infrastructure as Code. **Cost:** compute, storage, data transfer, logs, requests, NAT, redundancy, and non-production environments.

If an option fails a mandatory constraint, disqualify it even if it is cheap or simple to configure.

### Step 6 — Compare, Prototype, and Record the Decision

Build a short decision table using only verified facts. Example for a long-running containerized HTTP API:

| Criterion | ECS on Fargate | ECS on EC2 | EKS |
| --- | --- | --- | --- |
| Server management effort | Low | Higher | Higher, including Kubernetes overhead |
| Reuse of existing containers | Good | Good | Good |
| Host customization | More limited | Broad | Depends on node types and configuration |
| Required platform skills | ECS/tasks/networking | ECS + EC2 operations | Kubernetes + operations |
| Good fit when | Small team wanting minimal ops | Steady load needing cost/host tuning | Organization standardized on Kubernetes |

**Sample decision record:** "Choose ECS on Fargate for the container API because the team is small, does not need Kubernetes, and wants to minimize EC2 management. Validate via peak-hour load tests, deployment time, CPU/RAM utilization, and monthly cost estimates. If sustained steady costs exceed the threshold, re-evaluate against ECS on EC2." This decision includes **assumptions, evidence to collect, and review triggers**, not just a service name.

## 5. Three Architectural Selection Examples

### 5.1. New E-Commerce Website and API with Spiky Traffic

**Assumed requirements:** small development team; web frontend, simple order API, product images, post-order notifications; campaign-driven traffic spikes. Whether transactional data has complex relations must be confirmed upfront.

~~~mermaid
flowchart LR
    U[Users] --> CF[CloudFront]
    CF --> FE[S3: frontend files]
    U --> APIGW[API Gateway]
    APIGW --> L[Lambda: API]
    L --> DB[(DynamoDB or RDS)]
    L --> Q[SQS: post-processing jobs]
    Q --> W[Lambda: worker]
    W --> S3[S3: files, invoices]
    L --> CW[CloudWatch: logs, metrics]
    W --> CW
~~~

**Selection rationale:** S3 + CloudFront for the static frontend; API Gateway + Lambda when each request is short-lived and traffic varies; SQS decouples post-processing so the API responds quickly; S3 stores objects; CloudWatch handles monitoring. **DynamoDB only fits if** the key model and access patterns satisfy business queries. If JOINs and complex relational transactions are needed, choose RDS/Aurora and handle connection pooling/scaling appropriately for Lambda.

**Verification points:** p95/p99 latency, cold starts, idempotent retries, worker errors/DLQ, per-function IAM permissions, and request/log cost estimates. Configure private S3 access for CloudFront using current mechanisms rather than making buckets public casually.

### 5.2. Continuously Running Containerized SQL Order System

**Assumed requirements:** 24/7 API with multiple services and SQL transactions; must survive one AZ failure; team knows Docker well but has not operated Kubernetes.

~~~mermaid
flowchart TB
    User[Customer] --> R53[Route 53]
    R53 --> CF[CloudFront / AWS WAF]
    CF --> ALB[Application Load Balancer]
    ALB --> A[ECS Fargate - AZ A]
    ALB --> B[ECS Fargate - AZ B]
    A --> DB[(RDS Multi-AZ)]
    B --> DB
    A --> Q[SQS]
    B --> Q
    Q --> Worker[ECS worker or Lambda]
    A --> S3[S3: objects]
    B --> S3
    A --> CW[CloudWatch]
    B --> CW
~~~

**Selection rationale:** ECS/Fargate runs containers without self-managing EC2 nodes; ALB handles health checks and load balancing; tasks span at least two AZs; RDS Multi-AZ improves relational data availability; SQS decouples email sending/report generation; S3 stores files; WAF and CloudWatch aid protection and monitoring.

**Note:** the diagram depicts logical components, not subnets and security groups. During deployment, the ALB is typically in public subnets while services and the database are in private subnets as required; verify the DB is not publicly accessible. RDS Multi-AZ provides high availability, **not read replicas for scaling read load**. Multi-AZ also does not replace backups.

### 5.3. Reporting from Logs and Event Data

**Assumed requirements:** collect order logs, periodically analyze trends, no need to run direct transactional queries on the log store.

1. Centralize raw data in **S3** (with access control and storage lifecycle policies).
2. Use **Glue Data Catalog** and, if needed, Glue jobs to define schemas and transform data.
3. Use **Athena** to query datasets in S3; optimize columnar formats and partitioning to reduce data scanned.
4. When BI workloads become steady with complex JOINs/analytics or dedicated warehouse requirements emerge, evaluate **Redshift**.
5. Add **Kinesis/MSK** only if near-real-time stream ingestion/processing is genuinely required.

**Lesson:** start with a simple pipeline that meets current goals, adding streaming and warehouse services when concrete demand metrics justify them.

## 6. Availability, Recovery, and Configuration Choices

A managed service does not automatically make **the entire application** highly reliable. Inspect every potential failure point: ingress, compute, queues, databases, DNS, access permissions, external dependencies, and human actions.

| Need | Controls to evaluate | What must be tested |
| --- | --- | --- |
| One instance/container stops | Health checks, multiple tasks/instances, self-healing | Terminate one instance/task and verify request serving |
| One AZ becomes unavailable | Distribute compute across multiple AZs, HA-configured DB | Simulate failover and measure RTO |
| Data deleted/corrupted | Backups, versioning, permissions, recovery points | Restore from backup; measure RPO |
| Dependent API call fails | Timeouts, bounded retries, circuit breakers, DLQs | Test cascading failures and duplicate messages |
| Entire Region outage | Cross-Region DR architecture per mandatory level | Drill region switchover, data sync, and DNS |

**RTO** (Recovery Time Objective) is the maximum acceptable time to recover. **RPO** (Recovery Point Objective) is the maximum interval of data loss acceptable upon recovery. For example, an RTO of 1 hour and RPO of 15 minutes must be proven through test restores—not assumed merely because backups or Multi-AZ are enabled.

## 7. Cost: Calculating Total Cost of a Usage Flow

AWS charges by service and resource type. Pricing varies by Region, configuration, usage level, and time; use the **AWS Pricing Calculator** and monitor actual bills/Cost Explorer. Even a "serverless" architecture can become expensive with high request counts, large data transfers, or long log retention.

Commonly forgotten items:

- Continuously running compute, provisioned capacity, number of AZs, autoscaling, and idle resources.
- Storage: volume size, request counts, replicas, backups/snapshots, retention duration.
- Data transfer out to the Internet, cross-Region, or cross-AZ per each service's pricing rules.
- NAT Gateways, public IPv4 addresses, load balancers, and network endpoints.
- CloudWatch log ingestion/retention, tracing, and custom metrics.
- Standby databases, replicas, I/O, and connection counts; sizing of development/staging environments.

**How to manage:** apply cost allocation tags by project/environment, configure AWS Budgets and alerts, analyze trends in Cost Explorer, set lifecycle policies for infrequently accessed data, set log retention limits, and right-size compute based on measurements. Commitment models like Savings Plans or Reserved Instances only fit when you understand baseline usage and eligibility terms; do not treat them as automatic discounts on every service.

To decide wisely, compare **total cost of ownership**, not compute rates alone. EC2 might appear cheaper for a 24/7 configuration yet demands operational labor, security patching, and autoscaling maintenance. Conversely, Fargate/Lambda reduce operations overhead while carrying pricing models and limits suited to different load shapes.

## 8. Common Misconceptions When Choosing AWS Services

| Misconception | More accurate understanding |
| --- | --- |
| "Serverless means no operational design needed." | You still need IAM, observability, concurrency/quotas, retries, security, and budgets. |
| "EKS is always more modern than ECS." | Kubernetes only pays off clearly when ecosystem requirements and skills outweigh its complexity. |
| "DynamoDB can replace every SQL database." | Query patterns, transactions, key design, and consistency determine suitability. |
| "S3 is like a disk attached to a VM." | S3 is object storage over API; EBS/EFS address block/file storage needs. |
| "Having two EC2 instances means Multi-AZ." | They must be placed in two AZs, and ingress, data, and networking must also tolerate AZ failure. |
| "Multi-AZ equals having backups." | HA, backups, and disaster recovery address different failure modes. |
| "Putting the database in a private subnet is secure enough." | You also need IAM, security groups, authentication, encryption, patching, and monitoring. |
| "CloudWatch alone covers all AWS auditing." | Distinguish app metrics/logs from CloudTrail API logs and AWS Config configuration state. |
| "Only server pricing matters." | Storage, networking, requests, logs, redundancy, and operational labor are all significant. |

## 9. Checklist for Evaluating an AWS Solution

Before finalizing a choice, you should have evidence answering:

- [ ] Business requirements, normal/peak traffic, and data sensitivity levels are documented.
- [ ] Region is selected based on latency, data residency requirements, service support, and cost.
- [ ] Clear rationale for choosing EC2, containers, or Lambda, with operational effort stated.
- [ ] S3/EBS/EFS chosen by storage model and database chosen by query/transaction patterns.
- [ ] Synchronous vs. asynchronous flows distinguished; timeouts, retries, and idempotency addressed as needed.
- [ ] IAM least privilege, secrets, encryption, VPC, and public/private boundaries reviewed.
- [ ] SLOs, RTO, and RPO defined; HA strategy, backups, and restore testing in place.
- [ ] CloudWatch metrics/logs/alarms and CloudTrail auditing configured as required.
- [ ] Compute, database, requests, storage, networking, and logs estimated; budget alerts configured.
- [ ] Repeatable deployment (IaC), load testing, and decision-review triggers established.

**Applied exercise:** For a service that receives user photos, generates thumbnails, and returns URLs for global display, write two designs: (A) event-driven processing with S3 + Lambda + CloudFront; (B) container workers with SQS + ECS/Fargate + S3 + CloudFront. Compare them across file size/frequency, latency, processing duration, access permissions, retries, and total cost. Neither design is universally superior in every scenario.

## 10. Conclusion

A sustainable way to choose AWS services is **define requirements → select capability groups → evaluate operating models → verify security/availability/cost → prototype and measure**. For beginners, start with the core building blocks: Regions/AZs, IAM, VPC, compute, storage, databases, integration, and CloudWatch/CloudTrail. Then expand as real needs dictate. A strong architecture does not necessarily use many services; it clearly meets current requirements and leaves a clean upgrade path when assumptions change.

**Reference material during deployment:** the AWS service catalog on AWS product pages, individual service documentation, the AWS Well-Architected Framework, the AWS Shared Responsibility Model, and the AWS Pricing Calculator. Service availability, quotas, integration support, and pricing must be verified per Region at deployment time.
