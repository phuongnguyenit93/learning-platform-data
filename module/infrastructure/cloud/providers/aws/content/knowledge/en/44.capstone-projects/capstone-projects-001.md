# Designing Project Requirements, Architecture Diagrams, and Cost Estimates

A successful AWS project starts by understanding the problem and quantifying requirements before selecting services, drawing architectures, and estimating costs. Starting with a list of favorite services can lead a team to build a complex system that fails to solve the actual need. Having only a pretty diagram without workload numbers, security boundaries, assumptions, and traffic figures also makes the architecture difficult to implement and budget.

Cloud project design is the process of translating business requirements into a system that can be deployed, operated, and evolved. The designer must identify who uses the system, which features are mandatory, where data flows, what the expected load looks like, and what the security and recovery requirements are, while also explaining why each AWS service is chosen. Architecture diagrams must show components, data flows, network boundaries, and access permissions. A cost estimate must capture assumptions, pricing units, environments, growth, and the factors that can change total cost.

In the CLOUD_PROVIDERS_AWS module, learners explore Region/AZ infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless so they can choose services and design secure, observable, resilient, and cost-controlled applications. This lesson connects those concepts into a capstone workflow: clarifying requirements, building architecture diagrams, and creating a verifiable cost model.

## 1. Learning Objectives

After this lesson, you will be able to:

- Translate a business problem into goals, scope, and acceptance criteria.
- Write measurable functional requirements and non-functional requirements.
- Identify project assumptions, constraints, dependencies, and risks.
- Estimate workload from user counts, requests, data, retention, and traffic peaks.
- Choose AWS Regions, Availability Zones, and services that fit the requirements.
- Draw context, logical architecture, data flow, deployment, and security boundary diagrams.
- Justify choices for compute, database, storage, messaging, networking, and security.
- Design architectures with logging, metrics, tracing, backup, recovery, and deployment strategies.
- Use AWS Pricing Calculator to estimate costs per service.
- Build baseline, growth, and peak scenarios; perform sensitivity analysis and TCO analysis.
- Apply cost allocation tags, budgets, alarms, and cost review mechanisms.
- Present an architecture decision record and defend design choices.

## 2. AWS Project Design Workflow

There is no single fixed sequence for every project, but the workflow below helps a team move from a problem statement to a reviewable design.

~~~mermaid
flowchart TD
    A[Problem and business goals] --> B[Requirements and constraints]
    B --> C[Workload and data model]
    C --> D[Architecture options]
    D --> E[Select AWS services]
    E --> F[Architecture diagrams and decisions]
    F --> G[Security, reliability and operations review]
    G --> H[Cost model and scenarios]
    H --> I[Prototype and validate assumptions]
    I --> J[Delivery roadmap and acceptance]
    J -->|New evidence or changed requirements| B
~~~

Steps can iterate. For example, when the cost model shows that the database exceeds the budget, the team revisits the workload and access patterns to see whether data can be aggregated, cached, or stored differently. When a security review requires data to reside inside a private network, the team must update the network diagram and recalculate endpoint/NAT costs.

### 2.1. Understand the Problem Before Choosing Services

Describe the problem in the language of users and the business owner:

- Who is experiencing the pain point?
- How long does the current process take, or what errors occur?
- What outcome needs to be improved?
- Why move to AWS or build a new system?
- Are there legacy systems that must be integrated?
- What will count as project success?

For example, the statement "we need a serverless system on AWS" is not a goal. Saying "store staff can create and track orders across multiple branches, reducing processing time and continuing to accept orders even when a downstream worker temporarily fails" describes the problem and desired outcome much more clearly.

### 2.2. Identify Stakeholders

List end users, business owners, product owners, developers, platform teams, security, data teams, operations, and third parties. Each group may have different requirements:

| Stakeholder | Questions to Clarify |
|---|---|
| End users | Which tasks do they perform, and on which devices? |
| Business owner | What are the KPIs, budget, and timeline? |
| Developer | Which APIs, events, schemas, and workflows are needed? |
| Security | Which data is sensitive, and which permissions are restricted? |
| Operations | Who is on call, which alerts are needed, and what are the RTO/RPO? |
| Finance/FinOps | How are costs allocated and budgeted by team/project? |
| Partners | Which APIs, quotas, SLAs, and authentication mechanisms are provided? |

Record who approves each group of requirements. Without an owner, requirements can shift with no one responsible for confirming the impact.

### 2.3. Define Scope

Divide scope into:

- In scope: features and environments to be delivered.
- Out of scope: parts not implemented in the capstone.
- Future phase: capabilities that can be added later.

For example, the initial version of an Order Platform might include login, order creation, status viewing, asynchronous fulfillment processing, and an operations dashboard. Full ERP integration, predictive analytics, and multi-Region active-active deployment can remain outside the initial phase.

Clear scope prevents unbounded architecture expansion and gives the cost estimate a solid foundation.

## 3. Gathering and Writing Requirements

### 3.1. Functional Requirements

A functional requirement describes what the system must do. Write it in terms of verifiable actions and outcomes.

Examples:

1. Authenticated users can create an order with one or more products.
2. The system checks product availability before confirming the order.
3. Each order has a unique ID and a lifecycle status.
4. Users can only view orders belonging to their own account or tenant.
5. When an order is created, the system emits an event for asynchronous fulfillment processing.
6. Operations staff can search orders by ID and view status history.
7. The system stores an audit trail of status changes to support reconciliation.

Avoid vague requirements such as "the system must be fast," "data must be secure," or "it must be scalable." These statements must be turned into measurable criteria.

### 3.2. Non-Functional Requirements

Non-functional requirements (NFRs) describe quality attributes and operational limits. Common categories include:

| Category | Example Measurable Requirement |
|---|---|
| Performance | p95 API latency under 400 ms at target load, excluding async tasks |
| Availability | 99.9% availability target over a monthly window |
| Scalability | Support 100 requests/second during expected peak |
| Durability | Zero loss of confirmed orders |
| Recovery | RTO 2 hours, RPO 15 minutes |
| Security | MFA for operators, least privilege, encryption of sensitive data |
| Privacy | Do not store payment card details; personal data has defined retention |
| Operability | Dashboards, alerts, runbooks, and audit trail in place |
| Compatibility | Versioned APIs compatible with legacy clients during transition |
| Cost | Target cloud cost does not exceed the agreed monthly budget |

These numbers are examples, not default AWS guarantees. Business owners and operations must confirm realistic targets.

### 3.3. Writing Testable NFRs

A good requirement has four components:

- Condition: load, timeframe, data type, or scenario.
- Expected behavior.
- Measurable threshold.
- Testing method or evidence.

Example:

"During peak hours 10:00–11:00 at 100 requests/second, 95% of order status read requests complete within 400 ms, measured at API Gateway via p95 latency during a 15-minute load test."

This requirement is clearer than "the API must be fast" because it specifies workload, time window, percentile, threshold, and verification method.

### 3.4. Acceptance Criteria

Acceptance criteria are the conditions required for stakeholders to accept a feature. You can use Given/When/Then:

~~~text
Given a user is logged in and authorized to create orders
When the user submits a valid order with a new idempotency key
Then the system creates an order ID and returns status PENDING

Given a user does not belong to the tenant that owns an order
When the user requests to view that order ID
Then the API returns an authorization error and does not disclose order contents
~~~

Acceptance criteria must cover the happy path, validation, authorization, and failure paths.

### 3.5. Prioritizing Requirements

MoSCoW is one way to classify requirements:

- Must have: mandatory for the project to deliver value.
- Should have: important, though a temporary workaround exists.
- Could have: useful if time and budget allow.
- Won't have now: intentionally deferred to a later phase.

Prioritization helps the team choose an architecture that is right-sized. Do not build multi-Region, a data lake, or a streaming platform if the first version does not have the corresponding requirements and workload.

### 3.6. Requirements Traceability Matrix

Link requirements to components, tests, and acceptance evidence:

| Requirement ID | Requirement | Component | Verification Method |
|---|---|---|---|
| FR-01 | Create order | API Gateway, Lambda, DynamoDB | API integration/E2E test |
| FR-02 | Read only tenant-owned orders | Cognito authorizer, Lambda, data access layer | Negative authorization test |
| FR-03 | Async fulfillment processing | DynamoDB Streams, EventBridge, SQS, worker | Event flow integration test |
| NFR-01 | p95 under 400 ms | API, Lambda, DynamoDB | Load test and CloudWatch |
| NFR-02 | RPO 15 minutes | DynamoDB PITR/backup | Restore exercise |
| NFR-03 | Audit configuration changes | CloudTrail | Verify trail/event coverage |

This matrix helps reviewers see where each requirement is addressed in the design and verified.

## 4. Documenting Assumptions, Constraints, and Risks

### 4.1. Assumptions

An assumption is something temporarily treated as true so design work can proceed. Examples:

- 10,000 monthly active users.
- Most requests are status reads; order writes account for a smaller proportion.
- Payments are processed through an external provider.
- Users access the system primarily from Vietnam.
- Each order has a small payload, with attachments stored separately in S3.

Every assumption needs an owner and a verification method. If an assumption proves false, its impact on architecture and cost must be assessed.

### 4.2. Constraints

Constraints may include:

- Must use a specific Region due to data residency.
- Must integrate with the existing ERP system.
- Maximum monthly budget.
- Fixed deadline.
- Operations team only supports certain runtimes/languages.
- Data must be encrypted with a customer-managed KMS key.
- Certain services are disallowed by organizational policy.

Do not treat constraints as minor details. A network isolation requirement can change compute, endpoint, NAT, and cost choices.

### 4.3. Dependencies

List internal and external dependencies:

- Identity provider.
- Payment gateway.
- DNS/domain.
- ERP or CRM.
- Email/SMS provider.
- Data sources and migration tools.
- CI/CD platform.
- KMS keys and account baseline.

Document SLAs, quotas, timeouts, authentication, retries, and fallback behavior when a dependency is unavailable.

### 4.4. Risk Register

| Risk | Likelihood/Impact | Mitigation |
|---|---|---|
| Traffic peak higher than forecast | Medium/High | Load testing, quota review, autoscaling |
| Payment provider slow | High/High | Timeouts, queues, bounded retries, idempotency |
| Incorrect IAM policy | Medium/High | IaC policy tests, negative tests, CloudTrail |
| Test data contains PII | Low/High | Synthetic/masked data, account isolation |
| NAT or log costs exceed budget | Medium/Medium | Cost model, tags, budgets, reviews |
| Restore takes longer than RTO | Medium/High | Restore exercise and runbook |

Risk assessments must be tied to concrete actions and owners.

## 5. Modeling Workload Before Choosing Services

### 5.1. User and Request Profile

Estimate:

- Monthly active users (MAU).
- Daily active users (DAU).
- Sessions per user.
- Requests per session.
- Read/write ratio.
- Average and peak requests per second.
- Payload size.
- Error and retry rates.

Do not use registered user count as concurrent user count. You need to model user behavior and peak periods.

### 5.2. Calculating Request Volume

For example, with 10,000 MAU generating an average of 120 requests per month each:

\[
10,000 \times 120 = 1,200,000\ \text{requests/month}
\]

If there are 100,000 orders/month and each order produces three business events:

\[
100,000 \times 3 = 300,000\ \text{events/month}
\]

These figures should be validated through analytics or experiments. When forecasting peaks, hourly and daily request distribution matters more than dividing a monthly total evenly.

### 5.3. Estimating Concurrency

For request/response workloads, Little's Law can estimate average concurrency:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of in-flight requests.
- \(\lambda\): arrival rate in requests/second.
- \(W\): average processing duration in seconds.

If the system receives 50 requests/second and average processing time is 0.2 seconds:

\[
L = 50 \times 0.2 = 10
\]

Average concurrency is about 10 requests. Peak concurrency can be much higher during traffic bursts or latency spikes; use load testing to confirm.

### 5.4. Data Profile

Determine:

- Record size.
- New records per day.
- Data growth rate.
- Online and archive retention.
- Read/write ratio.
- Query patterns and access patterns.
- Data transfer across Regions/AZs or out to the Internet.
- Data requiring backup and restore time.

For example, 100,000 orders/month at an average of 3 KB per order record, excluding indexes and metadata:

\[
100,000 \times 3\ \text{KB} = 300\ \text{MB/month}
\]

When storing events, audit logs, indexes, and backup copies, actual storage is larger. Do not use logical record size as final storage capacity without accounting for overhead and copies.

### 5.5. Peak and Growth Factors

Define at least three levels:

| Scenario | Purpose |
|---|---|
| Baseline | Current average load |
| Peak | Daily or campaign peak load |
| Growth | User and data growth over 6–12 months |

For example, peak traffic may be 5x average for one hour. A growth scenario might triple requests after 12 months. Factors must be grounded in data or stakeholder-approved assumptions.

### 5.6. Workload Profile Worksheet

| Attribute | Example Value | Verification Method |
|---|---:|---|
| MAU | 10,000 | Product analytics |
| Requests/month | 1.2 million | API analytics |
| Orders/month | 100,000 | Business forecast |
| Peak RPS | 100 | Load test/traffic model |
| Average API payload | 8 KB | Request sampling |
| Order record | 3 KB | Schema estimate |
| Attachments | 200 GB/month storage | Product usage forecast |
| Online retention | 12 months | Business/legal requirement |
| RTO | 2 hours | Business impact analysis |
| RPO | 15 minutes | Data loss tolerance |

This is an illustrative workload for practice, not a standard benchmark for every project.

## 6. Choosing Region, Availability Zones, and Network

### 6.1. Choosing a Region

Evaluate:

- Where users are located and target latency.
- Data residency and regulatory requirements.
- Whether required services are available in the Region.
- Service pricing and data transfer pricing.
- Connectivity to on-premises systems or partners.
- DR strategy and operational capability.

Do not choose a Region simply because one individual service is cheaper. Consider the full picture across compute, database, storage, network, support, and inbound/outbound data transfer.

### 6.2. Availability Zones

A production architecture typically distributes workloads across multiple Availability Zones to reduce the risk of a single-AZ failure. Determine:

- Public/private subnets per AZ.
- Load balancer or managed service placement.
- Database replication/failover.
- NAT Gateway or VPC endpoint placement per the design.
- Cross-AZ data transfer and its cost impact.

Multi-AZ increases availability but can increase compute, storage, replication, and network costs. Tie the choice to your availability target.

### 6.3. VPC and Subnets

A VPC can be segmented into:

- Public subnets for load balancers or NAT Gateways depending on the architecture.
- Private application subnets for compute that needs access to internal resources.
- Isolated/database subnets for RDS/Aurora or resources that do not need direct Internet routes.

Never place a database in a public subnet just for connection convenience. Use security groups scoped to required sources and ports, NACLs per organizational policy, and minimal route tables.

### 6.4. NAT Gateway and VPC Endpoints

If workloads in private subnets need outbound Internet access, a NAT Gateway is one option. However, NAT Gateways incur hourly charges and per-GB data processing fees; traffic crossing multiple AZs or taking unintended routes can drive up costs.

For AWS services, consider VPC endpoints:

- Gateway endpoints for S3 and DynamoDB.
- Interface endpoints for services supporting PrivateLink.

Compare endpoint costs per AZ, number of services, NAT processing, and data transfer. Do not assume VPC endpoints are always cheaper; model the actual traffic.

### 6.5. Network Diagram

A network diagram should show:

- VPC CIDR.
- Availability Zones.
- Public/private/isolated subnets.
- Internet Gateway, NAT Gateway, VPC endpoints.
- Security group boundaries.
- Load balancers and compute.
- Databases and connection paths.
- VPN/Direct Connect if applicable.

A diagram that only writes "VPC" without showing subnets, routes, and trust boundaries is usually insufficient for a security review.

## 7. Selecting AWS Services Based on Requirements

### 7.1. Compute

| Need | Candidate Service | Decision Questions |
|---|---|---|
| Short events/APIs, automatic scaling | AWS Lambda | Execution duration, runtime, concurrency, dependencies |
| Containers without managing servers | Amazon ECS with Fargate | Continuous workload, task size, networking |
| Containers needing EC2 control | Amazon ECS on EC2 | Need node optimization, GPUs, or daemons? |
| Kubernetes ecosystem | Amazon EKS | Are Kubernetes and operational expertise required? |
| VMs/legacy software | Amazon EC2 | OS, licensing, instance family, and patching |

Choose compute based on execution model, latency, workload duration, scaling, portability, and operations. Do not use Lambda just for the serverless buzzword if the workload is long-running or has unsuitable runtime requirements.

### 7.2. Storage

| Data Type | Service | Considerations |
|---|---|---|
| Objects, file uploads, archives | Amazon S3 | Storage class, requests, lifecycle, retrieval, replication |
| Shared POSIX file system | Amazon EFS | Throughput, storage mode, mount targets per AZ |
| Block storage for EC2 | Amazon EBS | Volume type, IOPS, throughput, snapshots |
| Cache/in-memory | ElastiCache | Memory size, node count, replication, backups |

Separate metadata in the database from large file payloads. Use S3 for objects instead of storing large blobs in the database when the access pattern fits.

### 7.3. Database

| Access Pattern | Service | When It Fits |
|---|---|---|
| Key-value/document, well-defined access patterns | DynamoDB | High scale, low latency, managed |
| Relational, SQL, transactions, and joins | RDS/Aurora | Relational data and SQL queries |
| Cache/session | ElastiCache | Hot data, offloading database reads |
| Search/full-text | OpenSearch Service | Search and matching analytics |
| Time-series | Timestream or appropriate time-series option | Time-ordered telemetry |

Do not choose a database based on hype. Write out query patterns first: which keys are queried, how sorting/filtering works, transaction boundaries, and required consistency levels.

### 7.4. Integration and Messaging

| Need | Service |
|---|---|
| Queuing and decoupling | Amazon SQS |
| Pub/sub and event routing | Amazon EventBridge |
| High-throughput streaming | Amazon Kinesis Data Streams |
| Simple notification fan-out | Amazon SNS |
| Workflow orchestration | AWS Step Functions |
| Data delivery to S3/analytics | Amazon Data Firehose |

Choose based on semantics: queues, event buses, streams, and workflows solve different problems. Define delivery guarantees, ordering, retries, DLQs, replay, and idempotency.

### 7.5. Identity and Security

Common components:

- IAM roles for workloads and operators.
- Amazon Cognito or an appropriate identity provider for user authentication.
- AWS KMS for encryption keys.
- AWS Secrets Manager or Systems Manager Parameter Store for secrets/configuration.
- AWS WAF and Shield according to endpoint protection needs.
- Security groups, VPC endpoints, and network controls.
- CloudTrail, Config, GuardDuty, and Security Hub based on governance requirements.

Separate authentication from authorization. Successful login does not mean a user can access every record; enforce permissions at each resource and tenant boundary.

### 7.6. Observability and Operations

Design from the start:

- CloudWatch Logs, Metrics, Alarms, and Dashboards.
- AWS X-Ray or OpenTelemetry.
- CloudTrail and AWS Config.
- Runbooks, on-call ownership, and alert routing.
- Backup, restore, and DR testing.
- CI/CD and IaC.

Observability is part of the architecture, not an afterthought added after deployment.

## 8. How to Draw Architecture Diagrams

### 8.1. Context Diagram

A context diagram shows who interacts with the system and which external systems connect to it:

- Users and roles.
- The system being designed.
- Identity provider.
- Payment/ERP/CRM.
- Data sources.
- Operators or admins.

The context diagram should be simple, helping stakeholders understand project boundaries without needing service-level details.

### 8.2. Logical Architecture

Logical architecture shows capabilities:

- Presentation/API.
- Business services.
- Data stores.
- Messaging/eventing.
- Identity/security.
- Observability.

At this step, you can use capability names before locking in specific services.

### 8.3. AWS Deployment Architecture

A deployment diagram maps capabilities to AWS services and networking:

- CloudFront, API Gateway, Lambda, ECS.
- S3, DynamoDB, RDS.
- SQS, EventBridge.
- VPC, subnets, security groups, endpoints.
- IAM, KMS, Secrets Manager.
- CloudWatch, X-Ray, CloudTrail.

This is the diagram reviewers use to verify placement, network paths, and service integrations.

### 8.4. Data Flow Diagram

Show:

- Data sources.
- Protocols or APIs.
- Processing components.
- Data stores.
- Consumers.
- Encryption boundaries.
- Sensitive data flows.
- Points where data is validated, masked, or deleted.

For personal or payment data, clearly mark where data travels and where it must never be stored.

### 8.5. Sequence Diagram

A sequence diagram illustrates a use case over time. For example, order creation:

~~~mermaid
sequenceDiagram
    actor User
    participant API as API Gateway
    participant Auth as Cognito Authorizer
    participant Fn as Order Lambda
    participant DB as DynamoDB
    participant Stream as DynamoDB Streams
    participant Relay as Event Relay Lambda
    participant Bus as EventBridge
    participant Queue as SQS

    User->>API: POST /orders + token + idempotency key
    API->>Auth: Validate identity
    Auth-->>API: Claims
    API->>Fn: Invoke with request context
    Fn->>DB: Transaction write order + outbox
    DB-->>Fn: Commit
    Fn-->>API: 202 Accepted + orderId
    API-->>User: Order accepted
    DB->>Stream: New outbox record
    Stream->>Relay: Invoke relay
    Relay->>Bus: Publish OrderCreated
    Bus->>Queue: Route event
~~~

The diagram shows that a synchronous response can return before fulfillment finishes. The system needs order statuses and a query API so users can see the outcome of asynchronous processing.

### 8.6. Diagram Conventions

A review-ready diagram needs:

- Component names and roles.
- Directional arrows.
- Protocol or message-type labels.
- Account, Region, VPC, and trust-zone boundaries.
- Clear distinction between synchronous and asynchronous calls.
- Encryption or authentication annotations on critical flows.
- Callouts for optional components.
- A legend when colors or symbols are used.

Never include real secrets, account credentials, or real personal data in diagrams. For large architectures, create multiple views instead of cramming every component into one image.

## 9. Capstone Example: Order Management Platform

### 9.1. Project Context

A multi-store retail business wants to build an order management platform. Staff create orders at the counter or on the web; customers check order status; the system sends orders to fulfillment and updates payment results from an external provider.

Goals:

- Create and query orders via API.
- Authenticate users and authorize access by tenant/store.
- Process fulfillment asynchronously.
- Store attachments and invoices.
- Track status and history.
- Provide auditing, dashboards, and alerting.
- Scale with traffic and recover within the chosen RPO/RTO.

### 9.2. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Authenticated users can create an order |
| FR-02 | The system generates a unique order ID and supports idempotency |
| FR-03 | Users can only access data belonging to their assigned tenant |
| FR-04 | New orders emit events for fulfillment processing |
| FR-05 | Workers update status and record failures |
| FR-06 | Users can view order status |
| FR-07 | Users can download invoices/files from authorized links |
| FR-08 | Operators can look up orders and inspect the audit trail |

### 9.3. Illustrative Non-Functional Requirements

| Attribute | Target |
|---|---|
| MAU | 10,000 |
| API requests | 1.2 million/month |
| Peak traffic | 100 requests/second during campaigns |
| API p95 | Under 400 ms for reads/create acknowledgements |
| Availability | 99.9% target |
| RPO | 15 minutes |
| RTO | 2 hours |
| Data retention | 12 months online, archived per policy |
| Security | TLS, encryption at rest, least privilege, tenant isolation |
| Operations | Dashboards, alerts, traces, audit, and runbooks |

These targets must be validated through load tests, security tests, and restore exercises before being treated as commitments.

### 9.4. Reference Architecture Diagram

~~~mermaid
flowchart TB
    U[Web / Mobile users] --> R53[Route 53]
    R53 --> CF[CloudFront]
    WAF[AWS WAF] -. protect edge .-> CF
    CF --> WEB[S3 static web]
    CF --> API[API Gateway HTTP API]
    API --> AUTH[Cognito authorizer]
    API --> L[Order Lambda]
    L --> DB[(DynamoDB Orders + Outbox)]
    DB --> STR[DynamoDB Streams]
    STR --> RELAY[Outbox Relay Lambda]
    RELAY --> EB[EventBridge custom bus]
    EB --> Q1[SQS Fulfillment]
    EB --> Q2[SQS Notifications]
    Q1 --> WORKER[Fulfillment Worker]
    Q2 --> NOTIFY[Notification Worker]
    WORKER --> DB
    NOTIFY --> EXT[Email/SMS provider]
    L --> S3[S3 invoices and attachments]
    L --> SEC[Secrets Manager]
    SEC --> EXT
    L -. logs metrics traces .-> OBS[CloudWatch / X-Ray]
    WORKER -. logs metrics traces .-> OBS
    AUD[CloudTrail] --> OBS
    KMS[AWS KMS] -. encryption keys .-> DB
    KMS -.-> S3
~~~

This is a reference logical architecture. In the deployment design, add account boundaries, Region/AZ details, VPC placement if private resources exist, IAM roles, KMS key policies, endpoints, and network paths. Not every Lambda function needs to run inside a VPC; attach a VPC only when accessing private resources or meeting specific network control requirements.

### 9.5. Why Were These Services Selected?

| Component | Selection Rationale | When to Consider Alternatives |
|---|---|---|
| CloudFront + S3 | Serve static web assets and cache close to users | SSR web apps or dynamic content may need compute origins |
| AWS WAF | Filter requests using managed/custom rules | Depends on threat model, traffic, and policy |
| API Gateway HTTP API | Managed API with Lambda and authorizer integration | REST API if features exclusive to REST API are needed |
| Cognito | Manage user authentication and tokens | Use an enterprise IdP if the organization already has an identity platform |
| Lambda | Short, event-driven request processing | ECS/Fargate for long-running workloads or continuous runtimes |
| DynamoDB | Access patterns by order ID/tenant, managed scaling | Aurora/RDS if complex joins, SQL, and relational modeling are required |
| DynamoDB Streams | Detect changes to relay the outbox | Direct event bus/queue if different delivery semantics are acceptable |
| EventBridge | Route domain events to multiple consumers | SNS or Kinesis if their semantics fit better |
| SQS | Buffer and decouple workers | Kinesis if high-throughput ordered streams are needed |
| S3 | Store invoices, attachments, and objects | EFS if a shared file system is needed |
| Secrets Manager | Manage credentials for external providers | Parameter Store for non-sensitive config or suitable use cases |
| CloudWatch/X-Ray | Logs, metrics, alarms, and traces | Integrate with another observability platform if mandated by org standards |

Service selection is driven by access patterns and requirements, not by which service has the longest feature list.

### 9.6. Data Model and Access Patterns

Before designing DynamoDB, define the queries:

- Get an order by order ID.
- List orders by tenant and timestamp.
- Query orders by status.
- Look up the event history of an order.
- Idempotency lookup by tenant and key.

A simple table can use a partition key by tenant/order and a sort key for record type or timestamp. If there are multiple access patterns, choose single-table or multi-table design based on the workload; do not copy a relational schema directly into DynamoDB without analyzing queries.

The outbox record can be written alongside the order inside a single DynamoDB transaction. The relay reads the stream and publishes events, while consumers process idempotently because streams/consumers can retry or replay records according to service semantics. Monitor relay lag, errors, and unpublished records.

### 9.7. Security Design

- Users sign in via Cognito or the selected identity provider.
- The API authorizer validates tokens.
- Lambda checks the tenant claim and resource ownership.
- Execution roles grant access only to the required tables, queues, buses, and buckets.
- KMS encrypts data and objects as required.
- External provider secrets are stored in Secrets Manager.
- S3 Block Public Access is enabled; files are served via time-limited presigned URLs.
- CloudTrail logs control-plane activity and data events requiring audit.
- WAF protects public endpoints per the threat model.
- Logs exclude tokens, payment credentials, and unnecessary PII.

### 9.8. Reliability and Recovery

- The API writes the order and outbox record within a transaction.
- The relay and workers implement retries and idempotency.
- SQS uses visibility timeouts, redrive policies, and DLQs.
- Consumers enforce timeouts and bounded retries.
- DynamoDB uses backups/PITR aligned with the RPO.
- S3 enables versioning/lifecycle policies where needed.
- Multi-AZ resilience is provided by managed services per each service's architecture; cross-Region DR is a separate decision.
- Runbooks include procedures for event replay and DLQ handling.
- Restore tests measure actual RTO/RPO.

## 10. Security and Access Control Design

### 10.1. Identity and Trust Boundaries

Distinguish between:

- Human identity: end users, developers, operators.
- Workload identity: Lambda execution roles, ECS task roles, EC2 instance profiles.
- Service principal: AWS services assuming a role or accessing resources via policy.
- External identity: partners, IdPs, or workloads outside AWS.

Every identity has only the permissions it needs. Never embed long-term access keys in code or container images.

### 10.2. Authentication and Authorization

Authentication verifies who the caller is; authorization determines what that identity can do on which resource. For example, Cognito authenticates the user, but Lambda must still verify the tenant ID and order ownership.

Test all of the following:

- Valid user, matching tenant.
- Valid user, wrong tenant.
- Expired token or wrong audience.
- Operator with read-only access attempting modification.
- Workload role attempting to access an out-of-scope table or bucket.

### 10.3. Encryption

Define:

- TLS for client-to-service and service-to-service traffic where applicable.
- Encryption at rest for databases, objects, queues, and logs.
- KMS key ownership, rotation, and key policies.
- Backup/snapshot encryption.
- Secret rotation and access auditing.

If using customer-managed keys, account for key and request charges in the cost model, and specify which principals are allowed to encrypt/decrypt.

### 10.4. Network Security

- Do not expose databases directly to the Internet.
- Security groups allow only required sources and ports.
- Use private subnets for workloads accessing private databases.
- Use VPC endpoints when beneficial for security or cost.
- Inspect outbound egress and DNS behavior.
- Isolate accounts/environments based on risk level.

### 10.5. Audit and Compliance

CloudTrail, AWS Config, and security services support auditing. Define which events must be logged, where they are stored, retention periods, access controls, and incident response workflows. Never claim a system is "compliant" solely because a service is enabled; compliance requires mapping controls to requirements and gathering actual evidence.

## 11. Reliability, Availability, and Disaster Recovery

### 11.1. Failure Mode Design

List dependencies and what happens when each dependency fails:

| Dependency | Failure Mode | Mitigation |
|---|---|---|
| Identity provider | Unable to validate tokens | Graceful error handling, monitoring, provider fallback if required |
| Database | Timeout/throttling | Bounded retries, backoff, circuit breaker |
| Queue consumer | Worker stops processing | Queue buffering, DLQ, alarms |
| Payment provider | Slow API / 5xx responses | Timeouts, idempotency, reconciliation |
| Notification provider | Delivery failure | Retries, DLQ, delivery status tracking |
| Region | Unavailable | DR strategy, backup/replication, failover runbook |

### 11.2. Retries and Idempotency

Retries help recover from transient failures but can introduce duplicates. Every operation with side effects must define an idempotency boundary. Use exponential backoff with jitter, cap retry attempts, and route failures to a DLQ or failure destination.

Do not retry permanent errors such as validation or authorization failures. Retries must respect an overall timeout and stay within what the caller tolerates.

### 11.3. Availability Zones

Use multiple AZs for components requiring high availability. Identify what replication and failover a managed service already handles and what the application must do when endpoints change or connections reset.

Multi-AZ within a single Region does not protect against a Region-wide outage, logical data corruption, or accidental deletion. Appropriate backups and DR are still required.

### 11.4. Backup and Restore

Design:

- Backup frequency.
- Retention.
- Encryption.
- Destination account/Region.
- Access control.
- Restore procedure.
- Post-restore validation.

Backups are only valuable if they can be restored. Put restore exercises on the operations calendar and record actual RTO/RPO.

### 11.5. Choosing a DR Strategy

| Strategy | Description | Cost / Complexity |
|---|---|---|
| Backup and restore | Restore from backups when an incident occurs | Lower, typically longer RTO |
| Pilot light | Keep minimal core infrastructure running in a standby Region | Medium |
| Warm standby | Standby environment running at scaled-down capacity | Higher, shorter RTO |
| Multi-site active/active | Multiple Regions serving traffic simultaneously | Highest cost and complexity |

Choose based on business impact, RTO/RPO, data replication, consistency, and budget. Do not implement active-active just to have a "resilient" diagram if the business does not need it.

## 12. Observability and Operations

### 12.1. Logs, Metrics, and Traces

Every request/event should include:

- Request ID or message ID.
- Correlation ID.
- Trace context.
- Service/environment.
- Deployment version.
- Outcome/error code.
- Duration.

CloudWatch Logs supports search and querying; CloudWatch Metrics/Alarms detect trends; X-Ray/OpenTelemetry supports dependency analysis. CloudTrail adds audit events.

### 12.2. Dashboards and Alarms

Minimum dashboard panels:

- API traffic, 4xx/5xx, p95 latency.
- Lambda errors, duration, throttles, concurrency.
- DynamoDB throttling and consumed capacity.
- SQS queue depth, oldest message age, and DLQ count.
- Business success/failure counts.
- Cost trend and budget status.

Every alarm needs an owner, threshold, runbook, and action. Never create alarms that nobody responds to.

### 12.3. Deployment and Rollback

Infrastructure as Code enables consistent environment recreation. CI/CD pipelines should run unit tests, integration tests, IaC security checks, deployments, and smoke tests.

Choose rolling, canary, or blue/green deployments depending on the workload. Database migrations must maintain backward compatibility; rolling back application code does not automatically roll back data changes. Use expand-and-contract migrations whenever possible.

### 12.4. Runbooks

A runbook documents:

- Symptoms and triggering alarms.
- How to determine impact scope.
- Dashboard, log query, and trace links.
- Diagnostic steps.
- Rollback or failover procedures.
- DLQ handling and event replay steps.
- Responsible owner and escalation path.

Runbooks should be tested during game days or incident simulations.

## 13. Estimating AWS Project Costs

### 13.1. Cost Estimation Principles

Cost estimation is not just summing rough prices of selected services. You must translate workloads into billing dimensions for each service, select the Region, specify configurations, calculate usage duration, and model growth.

A reviewable estimate must state:

- Region and currency.
- Estimation period, typically monthly and annual.
- Workload assumptions.
- Services and configurations.
- Pricing units and quantities.
- Unit prices looked up from AWS Pricing Calculator.
- Data transfer and supporting requests.
- Dev/test/staging/prod environments.
- Backups, log retention, and support.
- Unresolved items and confidence level.

AWS prices vary by Region, time, service tier, and options. Use AWS Pricing Calculator with the target Region for current pricing; never use outdated figures from slides or blog posts as a quote.

### 13.2. Cost Categories

| Category | Example Cost Items |
|---|---|
| Compute | Lambda requests/GB-seconds, ECS task hours, EC2 instance hours |
| API/Edge | API Gateway requests, CloudFront requests/data transfer, WAF |
| Database | Read/write capacity, storage, backups, I/O, instance hours |
| Storage | S3 storage classes, requests, retrieval, replication |
| Messaging | SQS requests, EventBridge events, Kinesis capacity |
| Network | NAT Gateway hours/GB, VPC endpoints, data transfer, load balancers |
| Security | KMS keys/requests, Secrets Manager secrets/API calls, WAF |
| Observability | Log ingestion/storage/queries, metrics, alarms, traces |
| Backup/DR | Snapshots, backup storage, cross-Region replication, standby capacity |
| Support/Operations | AWS Support plan, third-party tools, staff effort |

### 13.3. Workflow for Using AWS Pricing Calculator

1. Open AWS Pricing Calculator and create a new estimate.
2. Select the workload's Region.
3. Add each AWS service in the architecture.
4. Select the appropriate pricing model: On-Demand, Savings Plans, Reserved Instances, or other options if the workload is steady enough.
5. Enter configurations and usage quantities from the workload profile.
6. Include data transfer, requests, backups, storage, and monitoring.
7. Group estimates by environment or business unit if needed.
8. Save assumptions, export the estimate, and review with owners.
9. Update the estimate whenever workloads or architectures change.

The calculator assists with planning; actual bills may differ due to traffic, retries, bursts, Free Tier eligibility, discounts, taxes, support, and unexpected usage.

### 13.4. Identifying Billing Dimensions per Service

| Service | Inputs to Model |
|---|---|
| API Gateway | Request count, API type, data transfer, caching if enabled |
| Lambda | Invocations, memory, duration, architecture, provisioned concurrency |
| DynamoDB | Read/write request units or capacity, item size, storage, backups, streams |
| SQS | Request units, payload size, send/receive/delete, long polling, batching |
| EventBridge | Event count, event size, bus/rules, and features used |
| S3 | GB-month by storage class, PUT/GET/LIST, retrieval, lifecycle, replication |
| CloudFront | Data transfer out, request count, cache hit ratio, origin traffic |
| WAF | Web ACLs, rules/rule groups, inspected requests |
| CloudWatch | Log ingestion, storage, query scans, custom metrics, alarms |
| X-Ray | Trace/segment volume and retrieval per pricing model |
| KMS | Key type/count and API requests |
| Secrets Manager | Secret count, API calls, and rotation depending on configuration |
| NAT Gateway | Gateway-hours and GB processed |
| VPC Endpoints | Endpoint-hours, AZ count, and data processing by endpoint type |

Read each service's pricing dimensions carefully. For example, SQS bills by request unit, where a large message can consume multiple request units; do not use message count directly without accounting for payload size and batching.

### 13.5. Calculating Lambda

Lambda typically has two primary inputs:

- Invocation count.
- Compute duration based on memory allocation and execution time.

For example, a workload with 1.5 million invocations/month, 512 MB memory, and 200 ms average duration:

\[
1,500,000 \times 0.2\ \text{s} \times 0.5\ \text{GB}
= 150,000\ \text{GB-seconds}
\]

This is compute usage before applying pricing, Free Tier, or applicable discounts. Add request charges and specific features like provisioned concurrency if used. For Lambda functions running in a VPC, add NAT or VPC endpoint costs if required by the architecture.

### 13.6. Calculating Storage

For S3:

\[
\text{Storage GB-month}
= \text{Average monthly stored volume}
\]

For example, storing an average of 200 GB over a month is roughly 200 GB-month, excluding versioning, replication, backups, and intra-month object growth. Calculate PUT/GET/LIST requests, retrieval, lifecycle transitions, and data transfer separately.

For databases, separate:

- Table/database storage.
- Indexes or replicas.
- Backups/snapshots.
- Read/write requests or instance hours.
- I/O and data transfer if included in the pricing model.

### 13.7. Calculating Network

Networking is the category most easily overlooked:

- Data transfer out to the Internet.
- Cross-AZ data transfer.
- Cross-Region data transfer.
- NAT Gateway processing.
- VPC endpoint processing.
- Load balancer hours and processed bytes.
- CloudFront origin fetches and cache hit ratio.

Estimate data flows on the diagram: how many GB enter from clients, move between services, cross between AZs, and leave the Region to the Internet. Never assume all internal traffic is free.

### 13.8. Calculating Observability

Estimate:

- GB of log ingestion per day.
- Retention days.
- Verbose logging ratio.
- Custom metrics and dimensions.
- Alarm count.
- Trace sampling rate.
- Logs Insights query frequency and scanned data volume.
- CloudTrail data event volume and retention.

For example, if an application produces 10 GB of logs/month retained for 30 days, ingestion and storage costs must be calculated separately. Enabling debug logs that increase volume 5x will change the estimate significantly.

## 14. Worked Example: Cost Model for the Order Platform

### 14.1. Workload Assumptions

This example uses the same workload profile from the architecture section:

- 10,000 MAU.
- 1.2 million API requests/month.
- 100,000 orders/month.
- 300,000 domain events/month.
- 1.5 million Lambda invocations/month, average 512 MB memory, 200 ms duration.
- DynamoDB estimated at 0.6 million write request units and 2.5 million read request units/month after analyzing item sizes and access patterns.
- S3 holding an average of 200 GB, with 500,000 PUTs and 2 million GETs/month.
- CloudFront delivering 150 GB/month and 1.2 million requests.
- CloudWatch ingesting 10 GB of logs/month with 30-day retention.
- X-Ray/OTel trace sampling at 5% of successful requests plus 100% of error traces per sampling policy.

These are illustrative assumptions. DynamoDB request units must be derived from item size, consistency, transactions, and access patterns; never use business record counts directly.

### 14.2. Cost Worksheet Table

| Component | Workload Input | Billable Units | Notes |
|---|---|---|---|
| API Gateway HTTP API | 1.2 million requests/month | Request count, data transfer | Choose the right API type |
| Lambda | 1.5 million invocations; 150,000 GB-s | Requests and GB-seconds | Add provisioned concurrency if used |
| DynamoDB | 0.6M WRU; 2.5M RRU; storage | Request units, GB-month, backup | Check item size and indexes |
| DynamoDB Streams | Outbox change records | Read requests/stream usage per model | Relay must keep up with stream |
| EventBridge | 300,000 events/month | Event ingestion and features | Account for event size and bus |
| SQS | Events × send/receive/delete | Request units | Batching and payload affect unit count |
| S3 | 200 GB-month; 500k PUT; 2M GET | Storage, requests, retrieval | Choose storage class |
| CloudFront | 150 GB out; 1.2M requests | Data transfer, requests | Cache hit ratio affects origin traffic |
| WAF | 1 Web ACL, rule set, 1.2M requests | ACL/rules/requests | Select required managed rules |
| CloudWatch | 10 GB logs, 30-day retention | Ingestion, storage, queries, metrics | Avoid log noise |
| X-Ray/ADOT | 5% baseline traces + error traces | Trace/segment volume | Sampling must be tested |
| KMS | Key count and API calls | Key-months, requests | Customer-managed keys if needed |
| Secrets Manager | 2 secrets, scheduled rotation | Secret-months, API calls | Avoid storing unnecessary secrets |
| Network | Egress, cross-AZ, NAT or endpoints | GB, gateway-hours, endpoint-hours | Calculate from data flows |

### 14.3. Total Cost Formula

For each service:

\[
C_i = \sum_j Q_{ij} \times P_{ij}
\]

Where:

- \(C_i\): cost of service i.
- \(Q_{ij}\): usage quantity for pricing dimension j.
- \(P_{ij}\): unit price for dimension j in the target Region at the time of estimation.

Total monthly cost:

\[
C_{\text{monthly}} =
\sum_i C_i + C_{\text{shared}} + C_{\text{support}}
\]

Shared costs may include networking, logging accounts, security services, and platform tooling. Avoid double-counting items already included in another service's estimate.

### 14.4. Splitting by Environment

Not every environment needs a production configuration:

| Environment | Suggested Configuration | Cost Control |
|---|---|---|
| Dev | Small resources, synthetic data | Shut down after hours, TTLs, and cleanup |
| Test | Provisioned per test run where possible | Ephemeral stacks, auto-delete |
| Staging | Production-like but lower load | Scheduled scaling, shorter retention |
| Production | Sized for SLA and peak workload | Autoscaling, budgets, alarms, tagging |

If dev/test runs continuously, total non-production cost can become significant. Include them in TCO rather than budgeting production alone.

### 14.5. Three Scenarios

Build at least:

| Scenario | Assumption | Question |
|---|---|---|
| Baseline | 1.2 million API requests/month | What is normal operating cost? |
| Growth | 3x requests and 2x storage | As users grow, which services scale linearly? |
| Peak | 5x requests over a short window | Is there throttling, provisioned capacity, or queue backlog? |

With serverless, costs usually scale with requests and compute; with continuously running resources such as NAT Gateways, database instances, or ECS services, costs have a fixed baseline even when traffic is low. Scenarios must separate fixed and variable costs.

### 14.6. Sensitivity Analysis

Vary one assumption at a time to identify cost drivers:

- Requests double.
- Average Lambda duration increases from 200 ms to 500 ms.
- Log volume increases 5x.
- Cache hit ratio drops.
- Storage retention increases from 12 to 24 months.
- Multi-AZ or cross-Region replication is enabled.
- NAT Gateway processes an extra 500 GB/month.

Identify which variable causes the steepest total cost increase. Prioritize optimizing large cost drivers instead of focusing on minor items with little impact.

### 14.7. TCO Beyond the AWS Bill

Total Cost of Ownership may include:

- AWS consumption.
- AWS Support plan.
- Third-party software, observability, and security tools.
- Operations and on-call staffing.
- Migration and training costs.
- DR testing and compliance costs.
- Development, upgrade, and decommissioning costs.

A capstone should distinguish monthly cloud run cost from project implementation cost and annualized TCO.

## 15. FinOps: Controlling Costs After Deployment

### 15.1. Cost Allocation Tags

Apply consistent tags across resources:

~~~text
Project=order-platform
Environment=production
Owner=commerce-team
CostCenter=CC-104
DataClass=confidential
ManagedBy=cdk
~~~

Tags support cost allocation and querying provided the service supports cost allocation tags. Not every resource or charge type can be allocated solely via tags; verify coverage.

### 15.2. AWS Budgets and Alerts

Configure:

- Overall monthly budget.
- Budgets per project/environment.
- Actual cost alerts.
- Forecasted cost alerts.
- Notifications to owners.

Budget alerts are a governance signal and do not automatically block spending. If automation is needed, design controlled actions and avoid automatically shutting down critical production resources.

### 15.3. Cost Explorer and Cost and Usage Report

Cost Explorer helps inspect trends by service, account, Region, and tag. The Cost and Usage Report (CUR) or equivalent billing exports can be used for deeper analysis in Athena/BI.

Review regularly:

- Actual vs. forecast.
- Cost by service and environment.
- Cost per order or cost per active user.
- Data transfer and NAT usage.
- Log/metric/trace volume.
- Idle resources and commitment utilization.

### 15.4. Optimizing After Collecting Real Data

Common optimization levers:

- Reduce unnecessary payloads and requests.
- Cache frequently read data.
- Use appropriate storage classes and lifecycle policies.
- Tune Lambda memory/duration after benchmarking.
- Batch messages when semantics allow.
- Shut down dev/test resources outside working hours.
- Adjust log retention.
- Evaluate VPC endpoints vs. NAT usage.
- Use Savings Plans/Reserved Instances once workloads are steady and usage data exists.

Do not purchase commitments solely based on unverified forecasts. Monitor actual usage and workload change risk before committing.

## 16. Architecture Decision Record

An architectural decision needs context and rationale, not just a service name.

ADR template:

~~~markdown
# ADR-001: Choose DynamoDB for Order Metadata

## Status
Proposed

## Context
The Order API needs lookups by tenant and order ID, frequent status writes,
variable traffic, and does not require complex joins in the initial phase.

## Decision
Use DynamoDB with pre-defined access patterns, on-demand capacity
initially, and backup/PITR aligned with the RPO.

## Alternatives
- Aurora PostgreSQL
- RDS PostgreSQL

## Consequences
- Must design partition/sort keys and indexes around query patterns.
- Cannot run ad-hoc queries like a relational database.
- Cost depends on read/write request units, storage, and backups.
- Re-evaluate if complex join/transaction requirements emerge.

## Validation
- Load test access patterns.
- Integration test conditional writes and transactions.
- Restore exercise.
- Cost estimate across baseline/growth scenarios.
~~~

An ADR can have status Proposed, Accepted, Superseded, or Rejected. When requirements change, record a new decision and link back to the previous ADR.

## 17. Capstone Delivery Plan

### 17.1. Milestones

| Phase | Deliverables | Exit Criteria |
|---|---|---|
| Discovery | Problem statement, stakeholders, scope | Confirmed by business owner |
| Requirements | FRs, NFRs, assumptions, risk register | Acceptance criteria defined |
| Workload | Capacity/data profile | Figures and assumptions have owners |
| Architecture | Context, deployment, data flow, sequence diagrams | Security/reliability review passed |
| Costing | Pricing Calculator estimate, scenarios | Reviewed by Finance/owner |
| Prototype | Vertical slice in an AWS test account | Core flow working |
| Validation | Unit/integration/E2E/load/security/restore tests | Evidence gathered for NFRs |
| Handover | Runbooks, dashboards, ADRs, backlog | Operations accepts handover |

### 17.2. Minimum Deliverables

A reviewable capstone should include:

1. Problem statement and business goals.
2. Stakeholder map and scope.
3. Functional/non-functional requirements.
4. Assumptions, constraints, dependencies, and risk register.
5. Workload/capacity model.
6. Architecture context diagram.
7. AWS deployment/network diagram.
8. Data flow or sequence diagrams for key use cases.
9. Security design and IAM boundaries.
10. Reliability/backup/DR strategy.
11. Observability plan and runbook outline.
12. Cost estimate by Region and scenario.
13. ADRs for major decisions.
14. Test strategy and acceptance evidence.
15. Implementation roadmap.

### 17.3. Review Gates

Before starting implementation:

- Business owner confirms goals and scope.
- Security reviews identity, data flows, and networking.
- Architecture review checks service choices and failure modes.
- Operations reviews RTO/RPO, monitoring, and runbooks.
- Finance/FinOps reviews assumptions and the cost model.

Reviews are not meant to be rubber stamps. Each gate must uncover a specific category of risk.

## 18. Common Mistakes in Project Design

| Mistake | Consequence | Fix |
|---|---|---|
| Picking services before understanding requirements | Architecture fails to solve the real problem | Start from business outcomes |
| Unmeasurable NFRs | Cannot verify acceptance | Define percentiles, workload, and thresholds |
| Unrecorded assumptions | Estimate cannot be audited | Record owners and verification methods |
| Not modeling peaks | Throttling or overprovisioning | Workload profile and load testing |
| Diagrams with only service icons | Missing data flows and trust boundaries | Draw context, deployment, and data flows |
| Ignoring network costs | Bill exceeds budget | Include NAT, endpoints, cross-AZ, and egress |
| Estimating production only | Missing dev/test/staging costs | Calculate multi-environment TCO |
| Choosing a database by preference | Hard-to-optimize queries, high cost | Start from access patterns |
| Missing idempotency design | Duplicate events cause side effects | Retry policies and idempotent consumers |
| Never testing restores | RPO/RTO exist only on paper | Run restore exercises |
| No observability | Hard to diagnose post-release issues | Logs, metrics, traces, audits, and runbooks |
| Using outdated prices | Cost estimate is inaccurate for the timeframe | Use AWS Pricing Calculator for the target Region |
| No post-deploy tracking | Cost drift goes unnoticed | Budgets, Cost Explorer, and regular reviews |

## 19. Practical Exercises

### Exercise 1: Write Requirements

Choose a problem domain such as order management, appointment booking, IoT monitoring, or document management. Write:

- One problem statement.
- Three business goals.
- Eight functional requirements.
- Six measurable non-functional requirements.
- Five assumptions and three constraints.
- One risk register with owners.

### Exercise 2: Model the Workload

Estimate:

- MAU/DAU.
- Monthly requests and peak RPS.
- Read/write ratio.
- Record and payload sizes.
- Storage growth and retention.
- Event/message volume.
- RTO/RPO.

Cite the source of each number or mark it as an assumption.

### Exercise 3: Draw Architecture Diagrams

Create:

- Context diagram.
- AWS deployment diagram.
- Data flow diagram.
- Sequence diagram for one use case.

Each diagram must include appropriate account/Region/VPC boundaries, protocols, and data directions.

### Exercise 4: Compare Services

Compare at least two options each for compute and database. Document:

- Access patterns.
- Availability/scaling.
- Operational overhead.
- Security.
- Cost drivers.
- Trade-offs.

Write an ADR for each major decision.

### Exercise 5: Estimate Costs

Create an estimate in AWS Pricing Calculator covering:

- Baseline.
- 3x Growth.
- 5x Peak.
- Production and non-production.
- Networking, logs, backups, and support.

Export the cost model table, clearly stating which Region and date the unit prices were taken from.

### Exercise 6: Architecture Review

Take the role of a reviewer and answer:

- Which requirements have no component addressing them yet?
- Which sensitive data flows lack protection?
- Which components are single points of failure?
- Where could retries create duplicates?
- Have RPO/RTO been verified?
- What is the largest cost driver?
- If traffic increases 3x, what needs to change?

## 20. Final Checklist

### Requirements

- [ ] Problem statement and business outcomes are clear.
- [ ] Stakeholders and owners are identified.
- [ ] Functional requirements have acceptance criteria.
- [ ] NFRs have metrics, thresholds, and test methods.
- [ ] Scope, assumptions, constraints, and dependencies are documented.

### Architecture

- [ ] Workload and data profiles are substantiated.
- [ ] Region/AZ choices are justified.
- [ ] Context, deployment, and data flow diagrams are complete.
- [ ] Compute/database/storage are chosen based on access patterns.
- [ ] Network and trust boundaries are illustrated.
- [ ] Least-privilege IAM and encryption are designed.
- [ ] Retries, idempotency, DLQs, and failure modes are defined.
- [ ] Backups, restores, RTO/RPO, and DR are described.
- [ ] Logs, metrics, traces, auditing, and runbooks are defined.

### Cost

- [ ] Estimate uses the target Region and current pricing.
- [ ] Compute, requests, storage, and databases are included.
- [ ] Networking, NAT, endpoints, and data transfer are included.
- [ ] Logs, metrics, traces, and CloudTrail are included.
- [ ] Backups, DR, and non-production are included.
- [ ] Baseline, growth, and peak scenarios exist.
- [ ] Cost allocation tags, budgets, and owners are defined.
- [ ] Assumptions and uncertainty are clearly noted.

### Delivery

- [ ] ADRs exist for key decisions.
- [ ] IaC and CI/CD strategies are defined.
- [ ] Unit, integration, E2E, and non-functional tests are planned.
- [ ] Smoke tests and rollback conditions are defined.
- [ ] Operations handover and restore exercises are planned.

## 21. Conclusion

Designing an AWS project begins with the business problem, stakeholders, scope, and measurable requirements. The workload model quantifies requests, concurrency, data, peaks, and growth. Only with those inputs in hand can you systematically select Regions, AZs, compute, databases, storage, messaging, networking, and security.

Architecture diagrams should show who the system interacts with, which components process data, where synchronous and asynchronous flows travel, and where security boundaries lie. A deployment diagram is valuable when reviewers can trace requests, verify access permissions, inspect failure modes, and locate where data is stored. ADRs capture decisions, alternatives, and trade-offs.

Cost estimates must be built from the workload and each service's pricing dimensions using AWS Pricing Calculator in the target Region. Include networking, observability, backups, DR, non-production environments, and support, then test baseline, growth, and peak scenarios. Combining requirements traceability, a defensible architecture, a transparent cost model, and an operations plan turns a capstone into an engineering proposal ready for review, implementation, and acceptance.

## 22. Official References

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Cloud Adoption Framework](https://aws.amazon.com/cloud-adoption-framework/)
- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Cost Management](https://aws.amazon.com/aws-cost-management/)
- [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html)
- [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/overview/welcome.html)
- [AWS IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Amazon VPC documentation](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html)
- [AWS Backup documentation](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)
- [AWS CloudFormation documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
