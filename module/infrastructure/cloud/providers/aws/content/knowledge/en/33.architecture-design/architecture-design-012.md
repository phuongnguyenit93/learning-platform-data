# Architecture Review and Documenting Design Decisions

## Learning Objectives

An AWS architecture may run yet still be hard to operate, expensive, lacking resilience, or non-compliant with security requirements. An architecture review is a structured evaluation to inspect a design before and after deployment, uncover risks, clarify assumptions, and align on required actions. An Architecture Decision Record (ADR) captures why a choice was made so teams can understand, verify, and revisit that decision when context changes.

Within the `CLOUD_PROVIDERS_AWS` module, learners need to know how to select and combine AWS services in the context of Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless. This lesson ties that knowledge into a review process applicable to real-world workloads.

After this lesson, learners can:

- Prepare an architecture dossier with business goals, scope, assumptions, constraints, and non-functional requirements.
- Conduct an architecture review based on the AWS Well-Architected Framework and organizational requirements.
- Evaluate the reliability, security, performance, cost, operability, and sustainability of a workload.
- Analyze data flows, trust boundaries, dependencies, failure modes, and blast radius.
- Compare design alternatives using verifiable criteria and evidence.
- Record decisions, alternatives, consequences, and revisit conditions using ADRs.
- Track findings, action items, exceptions, and architectural changes post-review.
- Know when to re-review and how to use the AWS Well-Architected Tool in continuous improvement workflows.

## 1. What Problem Does an Architecture Review Solve?

An architecture review is a design evaluation with defined goals, scope, participants, criteria, and recorded outcomes. Reviews can take place prior to implementation, prior to production launch, after major changes, or on an operational cadence.

A solid review answers these questions:

- What business need is this workload solving?
- Are requirements for availability, latency, throughput, data retention, privacy, and recovery quantified?
- Which components can fail, and how are users or data affected when they do?
- Which identities are permitted to call which components? Which trust boundaries does data cross?
- Does the architecture meet RTO/RPO targets with tested restore procedures?
- Do projected costs align with budgets and growth models?
- Does the operations team have sufficient telemetry, runbooks, access permissions, and response procedures?
- Are service choices grounded in constraints, workload patterns, and documented trade-offs?

A review is not a diagram walkthrough looking for typos. It is a way to validate assumptions, risks, and system operability using data, scenarios, and evidence.

### 1.1. Reviews Do Not Replace Design Ownership

The design team still owns the architecture and technical decisions. Reviewers ask questions, challenge assumptions, identify gaps, and propose options. Workload owners decide how to address findings, accept risks within their authority, or escalate for approval.

A review cannot guarantee a bug-free system. It reduces the chance of blind spots through independent perspective, consistent criteria, and clear evidence.

### 1.2. Common Review Types

| Review Type | Timing | Focus |
|---|---|---|
| Concept review | At idea inception | Goals, scope, high-level options, feasibility |
| Architecture design review | Before finalizing design | Components, data flows, integrations, failure modes, and trade-offs |
| Security review | Before handling data or opening connectivity | Threat model, identity, trust boundaries, encryption, logging |
| Production readiness review | Prior to go-live | Monitoring, capacity, runbooks, backups, recovery, access |
| Change review | Before high-impact changes | Blast radius, compatibility, rollbacks, migrations |
| Periodic review | Scheduled cadence or post-incident | Drift, cost, capacity, reliability, and technical debt |
| Post-incident architecture review | After severe incidents | Systemic root causes, design weaknesses, and preventive controls |

Not every change needs a large review board. Review rigor should be proportional to the workload's risk, complexity, and impact.

## 2. Starting from the Workload and Requirements

Do not begin a review by asking "which AWS services should we use?". First understand what the workload must do, who uses it, what data is processed, and what success looks like.

### 2.1. Defining the Workload

A workload is the set of applications, data, infrastructure, operational procedures, and dependencies serving a business goal. It may deploy in one account or multiple accounts, one Region or multiple Regions, yet the review scope must be clearly bounded.

A minimal workload brief should include:

- Workload name, technical owner, business owner, and operational contact channels.
- Business objectives, user personas, and critical user journeys.
- Data created, read, modified, transmitted, and stored.
- Dev, test, staging, and production environments and associated accounts/Regions.
- Internal systems, partners, and external service dependencies.
- Criticality level, operating hours, peak schedules, and maintenance windows.
- Current lifecycle stage: concept, under construction, production, or migrating.

### 2.2. Functional Requirements and Non-Functional Requirements

Functional requirements describe product behavior—such as customers placing orders, looking up transactions, or staff approving requests. Non-functional requirements (NFRs) describe the qualities and constraints the system must meet.

| NFR | Question to Answer | Example Quantification |
|---|---|---|
| Availability | How available must the service be? | 99.9% monthly for transaction APIs |
| Latency | How quickly must requests complete? | p95 under 300 ms for read endpoints |
| Throughput | What are normal and peak loads? | 2,000 requests/second, 5,000 peak |
| Scalability | How does the system scale as load rises? | 3x increase within 10 minutes |
| Durability | What level of data loss is acceptable? | Zero loss of confirmed transactions |
| RTO | How fast must service recover? | 60 minutes |
| RPO | How stale can recovered data be at most? | 5 minutes |
| Security | How must identities and data be protected? | MFA for admin access, encryption at rest/in transit |
| Privacy | How is personal data handled? | Classification, restricted access, and retention |
| Operability | What must operations observe and act upon? | Alerts with owners, runbooks, and audit trails |
| Cost | What are the budget and unit-cost targets? | Cost per 1,000 transactions |
| Sustainability | Where can resource usage and waste be reduced? | Scale to load, reduce idle capacity |

Numbers in the table are illustrative examples. Each workload requires targets agreed upon by both business and technical owners. Avoid vague statements like "the system must be fast," "must be highly available," or "low cost."

### 2.3. Distinguishing Targets, Constraints, and Assumptions

- **Target:** desired, measurable outcome.
- **Constraint:** mandatory boundary limiting options, such as approved Regions, standardized tech stacks, budgets, or deadlines.
- **Assumption:** something temporarily taken as true to proceed with design, yet requiring verification.

For example: "p95 under 300 ms" is a target; "data must reside in organization-approved Regions" is a constraint; "the partner supports TLS 1.2" is an assumption. If an assumption proves false, the architecture may need to change.

## 3. Using the AWS Well-Architected Framework as a Review Structure

The AWS Well-Architected Framework provides structured questions to evaluate workloads across six pillars:

1. Operational Excellence.
2. Security.
3. Reliability.
4. Performance Efficiency.
5. Cost Optimization.
6. Sustainability.

The six pillars complement one another. A decision that lowers cost might lengthen recovery time; a security control might affect latency; adding redundancy might increase resource consumption. Reviews must inspect the whole picture and document trade-offs.

### 3.1. Operational Excellence

This pillar focuses on operational capability and continuous improvement:

- Are owners and responsibility models clearly defined?
- Are infrastructure and configurations managed as code?
- Are deployment, rollback, change management, and incident response processes defined?
- Are logs, metrics, traces, and events sufficient to detect and investigate incidents?
- Are runbooks executable and tested?
- Are post-incident reviews and continuous improvement mechanisms in place?

On AWS, components may include CloudWatch, CloudTrail, AWS Config, Systems Manager, EventBridge, deployment pipelines, and IaC. Simply having services enabled does not equal operational capability; check configurations, ownership, and operational usage.

### 3.2. Security

The Security pillar examines how the workload, identities, data, and infrastructure are protected:

- Are identities authenticated and authorized following least privilege?
- Are human permissions, workload roles, and administrative permissions separated?
- Are data classification, encryption, key lifecycles, and secret management clear?
- How are network boundaries, ingress/egress, and private connectivity controlled?
- Are logging, detection, incident response, and vulnerability management active?
- Are security controls continuously validated with evidence?

Services may include IAM, IAM Identity Center, Organizations, SCPs, KMS, Secrets Manager, ACM, VPC, Security Groups, Network Firewall, GuardDuty, Security Hub, and CloudTrail. Select services based on your threat model and control requirements.

### 3.3. Reliability

Reliability evaluates the workload's ability to perform correctly under failures, load changes, or dependency degradation:

- Are failure modes and blast radius identified?
- Are single points of failure eliminated?
- Are Multi-AZ or multi-Region topologies aligned with RTO/RPO?
- Are retries, timeouts, backoff, circuit breakers, and idempotency implemented?
- Are backups, restore tests, and failover/failback drills performed?
- Have service quotas, capacity, and dependency limits been verified?

Services such as Route 53, Elastic Load Balancing, Auto Scaling, RDS Multi-AZ, DynamoDB, S3, AWS Backup, SQS, and EventBridge support reliability. Yet picking managed services does not remove the need to design failure handling.

### 3.4. Performance Efficiency

Performance Efficiency examines using resources and technologies suited to the workload:

- Are benchmarks run using representative traffic?
- Do compute, storage, and databases match access patterns?
- Are caches, queues, or asynchronous processing used where appropriate?
- Does scaling track the right metrics and avoid oscillation?
- Have managed/serverless services been evaluated to reduce operational burden?
- Are p50/p95/p99 latency, throughput, saturation, and error rates measured?

EC2, ECS, EKS, Lambda, Fargate, Aurora, DynamoDB, ElastiCache, CloudFront, or OpenSearch can be used depending on patterns. Benchmarks and real profiling matter more than following technology trends.

### 3.5. Cost Optimization

Cost Optimization evaluates total cost of ownership and economic efficiency:

- Are costs tracked by workload, environment, and business unit?
- Are right-sizing, autoscaling, and non-production scheduling applied?
- Are storage classes, retention, and backups sized appropriately?
- Are data transfer, NAT Gateway, log ingestion, and cross-Region charges measured?
- Are managed services compared against self-managed operational costs?
- Are budgets, anomaly detection, owners, and periodic reviews in place?

Cost Explorer, AWS Budgets, Cost and Usage Reports, Compute Optimizer, and tagging strategies assist here. The lowest unit rate on one service line item is rarely the lowest total cost once operations and risk are factored in.

### 3.6. Sustainability

Sustainability examines resource efficiency and environmental impact:

- Do resources scale with actual demand?
- Are idle environments shut down or downsized?
- Are stored data, retention, and data transfers optimized?
- Are managed services and low-overhead architectures chosen where suitable?
- Are overprovisioning and unnecessary always-on workloads avoided?

Sustainability is not merely picking smaller instances. Resource efficiency must be balanced against reliability, security, latency, and user experience.

## 4. Preparing Documentation for the Review

A reviewer cannot assess an architecture accurately from a single high-level diagram. The design team must supply enough information to understand how the system works, how data moves, and how the system responds when a part fails.

### 4.1. Minimal Documentation Set

| Artifact | Contents |
|---|---|
| Workload brief | Business goals, owner, scope, criticality, users |
| Requirements matrix | Functional requirements, NFRs, targets, constraints, assumptions |
| Context diagram | Users, workload, external systems, and boundaries |
| Component/container diagram | Services, runtimes, databases, queues, caches, storage |
| Deployment diagram | Accounts, Regions, AZs, VPCs, subnets, routing, and endpoints |
| Data flow diagram | Data classification, protocols, direction, encryption, retention |
| Trust boundary / threat model | Identities, attackers, threats, controls, and residual risks |
| Failure-mode analysis | Dependencies, failures, detection, mitigation, and recovery |
| Capacity/performance model | Traffic, growth, concurrency, latency, and benchmarks |
| Cost estimate | Service assumptions, pricing dimensions, data transfer, environments |
| Operations model | Monitoring, alerts, runbooks, backups, restores, support ownership |
| Decision log / ADR | Decisions made, rationale, alternatives, and consequences |

Not every workload needs every artifact at the same depth. However, reviewers must know which artifacts are missing and how those gaps affect conclusions.

### 4.2. What Should Diagrams Show?

A useful diagram should tell readers:

- Who calls whom, over which protocol, and in which direction.
- Which component lives in which account, Region, AZ, VPC, or subnet.
- Where TLS terminates and where data is decrypted.
- Which data is sensitive, where it is stored, and how it is encrypted.
- Which identity/role calls services or accesses resources.
- Where queues, retries, DLQs, caches, and databases reside.
- Which components are managed services and which are self-operated by the team.
- Which dependencies fall outside the team's direct control.

Diagrams do not need every ARN or every security group rule. Those details belong in IaC, inventories, or appendices. Diagrams must be clear enough to review flows and boundaries.

### 4.3. Data Flows and Trust Boundaries

Mark where data is created, transmitted, transformed, stored, and deleted. For each flow, note:

- Data classification.
- Source and destination.
- Protocol/port.
- Authentication and authorization.
- Encryption in transit and at rest.
- Retention, backups, deletion, and residency.
- Logging, masking, and access controls.

A request traveling from the Internet through CloudFront, ALB, ECS, and RDS crosses multiple trust boundaries. If TLS terminates at the ALB and the backend uses HTTP, show that explicitly. Never draw a single "HTTPS" arrow end-to-end when TLS actually terminates mid-path.

## 5. Architecture Review Process

A simple yet disciplined process has six stages:

~~~mermaid
flowchart TD
    A[Intake: goals and scope] --> B[Preparation: dossier and reviewers]
    B --> C[Review: questions, evidence, trade-offs]
    C --> D[Findings: risk severity and owners]
    D --> E[Disposition: remediate or accept risk]
    E --> F[Follow-up: actions, deadlines, verify]
    F --> G[Periodic review / new trigger]
    G --> A
~~~

### 5.1. Intake

The review requester provides the workload brief, reason for the review, decision deadline, and scope. The coordinator checks that reviewers have the right expertise and appropriate independence.

Intake outputs:

- Workload and owners identified.
- Clear in-scope and out-of-scope boundaries.
- Review type and depth agreed upon.
- Decision deadline and decision authority recorded.

### 5.2. Preparation

The design team prepares the dossier. Reviewers read ahead and note questions per pillar. If critical documentation is missing, request it before the session or flag unverified assumptions.

Do not spend the review session discovering business goals for the first time or redrawing diagrams from scratch. Good preparation frees meeting time for real decisions and risks.

### 5.3. Review Session

A reference agenda:

1. Business context and success criteria.
2. Scope, assumptions, and constraints.
3. Architecture overview and data flows.
4. Reliability, security, performance, operations, cost, and sustainability.
5. Options and trade-offs requiring decisions.
6. Findings, owners, and next steps.

Reviewers should ask "what evidence demonstrates this target is met?" rather than merely "did you turn on service X?". For instance, asking "which restore drill proved the 60-minute RTO?" is far more useful than "do you have AWS Backup?".

### 5.4. Findings and Disposition

Findings must describe the issue, impact, evidence, priority, owner, and due date. The design team proposes remediations. Authorized stakeholders decide whether to fix, accept risk, escalate, or grant an exception.

Never mark a finding as "resolved" simply because a ticket was created. Evidence that the change was deployed and verified is required.

### 5.5. Follow-Up

Track action items until they are:

- Completed with verification evidence.
- Superseded by a new decision.
- Formally risk-accepted through governance.
- No longer applicable because scope or requirements changed.

Define an escalation path for overdue findings. Never leave high-severity findings sitting indefinitely in an unowned spreadsheet.

## 6. Reliability Review

A reliability review must trace from failure modes to system behavior. You cannot conclude "high availability" simply because two AZs or managed services are used.

### 6.1. Failure Domains and Blast Radius

Categorize potential failures:

- Process/container/instance.
- Availability Zone.
- Region.
- Network path, DNS, or certificates.
- Database/storage.
- Identity provider or KMS keys.
- Queues, event buses, or downstream services.
- Deployment/configuration errors.
- Operator mistakes or credential compromise.
- Provider/third-party dependencies.

For each failure, ask:

1. How can the failure occur?
2. Which signals detect it?
3. What do users experience?
4. Which components continue functioning?
5. Does it self-heal or require operator action?
6. Can data be lost or duplicated?
7. What are the recovery time and recovery point?

### 6.2. Multi-AZ and Multi-Region

Multi-AZ typically protects against single-AZ failures within a Region. Multi-Region can reduce the impact of Regional events, while increasing complexity across replication, data consistency, routing, IAM, key management, cost, and failback.

Do not pick multi-Region just because it sounds safer. Compare:

| Criterion | Multi-AZ | Multi-Region |
|---|---|---|
| Failure domain | AZ | Region |
| Data replication | Often service-managed within Region | Must specify mechanism per service |
| Latency | Usually lower across AZs in a Region | Can be higher across Regions |
| Complexity | Relatively lower | Higher; requires runbooks and testing |
| Cost | Increases via standbys/capacity | Usually higher due to replication, transfer, and capacity |
| Recovery objective | Fits many HA workloads | Reserved for Regional recovery or residency strategies |

Check each service's specific HA/replication features. Not every resource shares identical semantics or replication lag characteristics.

### 6.3. Retries, Timeouts, and Idempotency

Retries improve resilience against transient errors, yet unbounded retries easily cause retry storms. Reviews should verify:

- Do timeouts fit inside the latency budget?
- Do retries use exponential backoff and jitter?
- Are retry counts bounded?
- Are requests idempotent or carrying idempotency keys?
- Do queues/DLQs preserve failed messages for handling?
- Are circuit breakers or bulkheads necessary?

For SQS, inspect visibility timeouts, message retention, redrive policies, and dead-letter queues. For EventBridge, inspect retry policies, target DLQs, and duplicate handling. For Step Functions, inspect retry/catch blocks and state transitions. Never assume exactly-once delivery if the system can redeliver messages.

### 6.4. Backups, Restores, and Disaster Recovery

Reviews must inspect both backup policies and restore evidence:

- Are recovery points frequent enough to meet RPO?
- Does retention meet regulatory and operational needs?
- Are backup vaults, KMS keys, and restore permissions protected?
- Are copies sent to another account/Region if required by the threat model?
- Have restores been tested in an isolated environment?
- Were data and applications verified post-restore?
- Are runbooks, owners, and failover/failback criteria defined?

A successful backup job does not prove a successful restore. A completed restore job does not prove data integrity or application readiness. Reviews should demand validation evidence and end-to-end RTO/RPO measurements.

## 7. Security Review

Security reviews should be anchored in data flows and threat models. Every component, identity, and trust boundary must be assessed.

### 7.1. Identity and Least Privilege

- Does human access use federation/SSO and MFA?
- Do workloads use dedicated IAM roles instead of long-lived access keys?
- Do policies specify resource scopes, conditions, and permission boundaries?
- Is cross-account access designed explicitly?
- Are deploy, runtime, audit, and break-glass permissions separated?
- Are secrets stored in Secrets Manager/Parameter Store or an appropriate system?
- Are credentials rotated and audited?

With AWS Organizations, review account boundaries, OUs, SCPs, delegated administrators, and account vending. SCPs cap maximum permissions in member accounts; they never grant permissions on their own.

### 7.2. Networks and Trust Boundaries

Review VPC CIDRs, subnets, route tables, Internet/NAT paths, VPC endpoints, security groups, and network ACLs. Verify inbound/outbound rules specify exact sources, destinations, and ports. Assess private connectivity for AWS services and partners.

Do not cite "private subnet" as complete proof of security. A workload in a private subnet can still reach the Internet via NAT, service endpoints, or other routes. Inspect actual routing and policies.

### 7.3. Data Protection

For sensitive data, inspect:

- Encryption at rest and in transit.
- KMS key ownership, policies, rotation, and deletion protection.
- Certificate lifecycles and TLS policies.
- Data classification, masking, and tokenization where appropriate.
- Backup encryption and restore permissions.
- Data retention, deletion, and legal holds.
- Cross-Region/cross-account data transfers.

Specifically, misconfigured key policies or secret permissions can render data unreadable after a restore or failover. Security and reliability must be reviewed together.

### 7.4. Threat Modeling

STRIDE can guide threat identification:

| Category | Example Question |
|---|---|
| Spoofing | Can an attacker impersonate a workload or user? |
| Tampering | Can requests, messages, or objects be modified without authorization? |
| Repudiation | Is there an audit trail sufficient to trace actions? |
| Information Disclosure | Can data leak via logs, URLs, buckets, or networks? |
| Denial of Service | Can a client or dependency exhaust capacity? |
| Elevation of Privilege | Can IAM or application misconfigurations escalate privileges? |

Threat models must link threats to controls, owners, and residual risks. A filled-out STRIDE table without data flows or mitigations is not a complete threat model.

## 8. Performance and Scalability Review

Performance must be evaluated against realistic workload patterns, not just service settings.

### 8.1. Load Profile

Define:

- Average, peak, and burst request rates.
- Read/write ratios.
- Payload sizes and data volumes.
- Concurrent users, connections, and background jobs.
- Diurnal/seasonal patterns.
- Growth forecasts.
- Percentile latency targets.
- Workload mix and tenant skew.

A system handling 1,000 requests/second with 1 KB payloads differs dramatically from 1,000 requests/second with 5 MB payloads. Measure both data throughput and request rate.

### 8.2. Choosing Compute

| Option | Suitable When | Review Questions |
|---|---|---|
| EC2 | OS, runtime, or specialized configuration control is needed | Capacity, patching, scaling, instance families, and HA |
| ECS/Fargate | Container workloads wanting less host management | Task sizing, deployments, networking, task roles, and scaling |
| EKS | Kubernetes ecosystem or platform standardization is needed | Cluster ops, add-ons, node capacity, upgrades, and policies |
| Lambda | Event-driven or request workloads fitting its execution model | Timeouts, concurrency, cold starts, packaging, retries, and cost |

There is no universal "best" option. Compare operational burden, runtime constraints, scaling behavior, latency, portability, security, and total cost.

### 8.3. Data Tier and Caching

Review databases/storage against access patterns:

- Relational transactions, constraints, and joins.
- Key-value/document lookups by key.
- Object storage for blobs, files, backups, and data lakes.
- Shared file systems for workloads needing file semantics.
- Caching for read-heavy data with an invalidation strategy.
- Search engines for full-text or search analytics.

Check connection pools, hot partitions, indexes, cache hit ratios, evictions, consistency, and behavior when caches are unavailable. Caches must never accidentally become the authoritative source of truth.

### 8.4. Benchmarks and Load Tests

Reviews require reproducible benchmarks:

- Representative datasets excluding sensitive production data unless authorized.
- Recorded runtime, instance, database, and Region configurations.
- Explicit load profiles and warm-up periods.
- Measured latency percentiles, throughput, error rates, CPU, memory, I/O, and queue depth.
- Steady-state, burst, stress, and post-load recovery tests.
- Results tied to pass/fail thresholds and software versions.

A benchmark testing a single sequential request never proves a system can sustain peak load.

## 9. Cost and Economic Efficiency Review

Cost reviews should start from usage models and business unit economics, such as cost per order, cost per active user, or cost per GB processed.

### 9.1. Easily Overlooked Cost Components

- Continuously running compute and idle capacity.
- Database instances, storage, I/O, backups, and replicas.
- S3 storage classes, requests, retrievals, and lifecycle transitions.
- NAT Gateways, cross-AZ/cross-Region data transfer, and Internet egress.
- Load balancers, public IPv4 addresses, VPC endpoints, and IP consumption.
- CloudWatch log ingestion, retention, metrics, and tracing.
- KMS requests, secrets, queues/events, and API calls.
- DR standby capacity, replication, and restore drills.
- Support plans, operational labor, and third-party licenses.

### 9.2. Comparing Total Cost of Ownership

When comparing EC2 vs. Lambda or RDS vs. self-managed databases on EC2, do not compare compute sticker prices alone. Include:

- Provisioned/consumed capacity.
- Storage, backups, and networking.
- Licenses and support.
- Patching, upgrades, scaling, and incident handling.
- Engineering time and on-call burden.
- Cost of downtime and data loss.

Managed services may carry higher service rates while reducing operational labor. Self-managed setups may optimize at unique scales while requiring specialized expertise and carrying higher risk.

### 9.3. Cost Estimates Must Record Assumptions

An estimate must state Region, currency, usage profiles, commitments, discount assumptions, retention, data transfer, and growth. When using a pricing calculator, save the estimate or snapshot to compare against actual spend post-launch.

Never present an estimate as an exact invoice. Actual bills depend on real usage, current pricing, discounts, taxes, and workload behavior.

## 10. Operations, Observability, and Support Review

A production architecture must give teams visibility into system state and clear ways to intervene when behavior drifts from normal.

### 10.1. Observability

Check:

- Do metrics cover the golden signals: latency, traffic, errors, saturation?
- Do logs include structured fields, correlation IDs, and suitable retention?
- Do traces follow flows across service boundaries?
- Are alerts actionable with owners and runbooks?
- Do dashboards answer real operational questions?
- Are symptom alerts separated from cause alerts?
- Does telemetry control cardinality, PII, and cost?

CloudWatch, X-Ray, OpenTelemetry/ADOT, Managed Prometheus, or other observability tools can be used per requirements. You do not need every signal on every component; gather signals that serve SLOs and investigations.

### 10.2. Runbooks and Incident Response

Runbooks should specify:

- Trigger or symptom.
- Preconditions and required permissions.
- Ordered inspection steps.
- Safe actions vs. actions requiring approval.
- Rollback or escalation criteria.
- How to verify recovery.
- How to capture evidence.

Review a runbook by asking whether an on-call engineer can execute it under high stress. If steps rely on one person's memory, the runbook is incomplete.

### 10.3. Support and Service Limits

Verify support plans, escalation paths, service quotas, API rate limits, account limits, regional availability, and maintenance windows. An architecture may be logically sound yet impossible to deploy if quotas or features are unavailable in the chosen Region.

Include quotas in capacity models. If traffic can spike sharply, verify quotas ahead of time and establish limit-increase workflows.

## 11. Integration and Data Consistency Review

Integration boundaries create coupling and failure propagation. Review how the system reacts when downstream services slow down, fail, or deliver duplicates.

### 11.1. Synchronous vs. Asynchronous

Synchronous calls are easy to reason about and return immediate results, yet increase availability and latency coupling. Asynchronous messaging decouples processing timing, absorbs bursts, and supports retries, while introducing eventual consistency and message lifecycle management.

| Criterion | Synchronous API | Asynchronous Messaging |
|---|---|---|
| Response | Returned within the request | Processed later; feedback via events/status |
| Coupling | Tighter temporally | Looser |
| Failure handling | Timeouts, retries, circuit breakers | Retries, visibility timeouts, DLQs, replay |
| Consistency | Read-after-write possible by design | Typically eventual consistency |
| Burst scaling | Callers may block | Queues can absorb bursts |
| Complexity | Fewer moving parts | Must manage events/schemas/ordering/deduplication |

### 11.2. Event Schemas and Compatibility

For EventBridge, SNS, SQS, or streams, review:

- Do schemas have versions and owners?
- Can older consumers tolerate new fields?
- Are breaking vs. non-breaking changes distinguished?
- Are idempotency keys and deduplication strategies defined?
- Are ordering constraints identified?
- Are DLQs, replay, and retention configured appropriately?
- Can events be traced from producer to consumer?

Do not treat event payloads as a contractless shared database. Events should represent well-defined facts or commands.

### 11.3. Data Consistency and Migrations

If the system spans multiple databases, caches, search indexes, or data lakes, document the source of truth and synchronization mechanisms. Review migrations using expand/contract phases when multiple application versions must coexist.

A safe migration typically includes:

1. Adding new structures compatible with older code.
2. Deploying producers/consumers supporting both old and new formats.
3. Running controlled backfills or dual-writes.
4. Verifying counts, checksums, and invariants.
5. Switching read paths.
6. Retiring old structures once zero consumers remain.

Dual-writes can cause inconsistency if one side succeeds while the other fails. Use reconciliation or the outbox pattern where appropriate.

## 12. Evaluating AWS Service Selections

An architecture review is not a contest to list services. Every choice must tie back to workload patterns, requirements, and trade-offs.

### 12.1. ALB, API Gateway, or CloudFront?

| Component | Typical Role | Pre-Selection Questions |
|---|---|---|
| CloudFront | CDN, edge caching, content delivery, and edge layer | Cacheability, origins, WAF, geography, and invalidation |
| ALB | Layer 7 routing to target groups | HTTP routing, target health, TLS termination, and compute integration |
| API Gateway | API management, throttling, auth integration, API lifecycle | API type, latency, payloads, auth, quotas, and pricing |

Multiple layers can be combined—for example, CloudFront in front of an ALB or API Gateway. Clarify where WAF, TLS, authentication, rate limiting, and logging are enforced to avoid security gaps or redundant controls.

### 12.2. RDS/Aurora or DynamoDB?

RDS/Aurora fits relational models, SQL, transactions, and entity relationships. DynamoDB fits key-driven access patterns, massive throughput, and query-driven data modeling.

Reviews must examine:

- Access patterns and query shapes.
- Transaction and consistency requirements.
- Data models, indexes, and partitioning strategies.
- Backups/PITR and recovery.
- Scaling, connection management, and operational skills.
- Costs across requests, storage, capacity, and traffic.

Do not pick DynamoDB just to be "serverless," and do not pick a relational database solely because the team knows SQL without analyzing access patterns.

### 12.3. ECS, EKS, or Lambda?

Compare execution models, packaging, runtimes, startup behavior, scaling, observability, security boundaries, upgrades, and team skills. A single workload can combine Lambda for event processing with ECS for API services. Avoid forcing everything onto one platform merely because the organization standardized on it if doing so adds unnecessary complexity or cost.

### 12.4. S3, EFS, or FSx?

- S3 is object storage, not a POSIX file system.
- EFS provides shared file system semantics for Linux workloads.
- FSx provides specialized file systems such as Windows File Server, Lustre, ONTAP, and OpenZFS.

Review protocols, access patterns, latency, throughput, locking, metadata, file semantics, data sharing, and backups. Application needs such as atomic renames or POSIX permissions can dictate the choice.

## 13. Documenting Decisions with Architecture Decision Records

An ADR is a concise record of an important architectural decision. ADRs preserve context and rationale so future readers understand why the system is built the way it is.

A good ADR is not a sales pitch for the chosen option. It states the problem, realistic alternatives, evaluation criteria, the decision, consequences, and conditions that would prompt revisiting it.

### 13.1. When Is an ADR Needed?

Create an ADR when a decision:

- Affects multiple components or multiple teams.
- Creates long-term coupling or is hard to reverse.
- Alters data models, API contracts, identity, or trust boundaries.
- Selects Regions, account structures, or DR strategies.
- Significantly affects cost, security, compliance, or availability.
- Chooses a platform or service with high migration cost.
- Grants an exception to organizational standards or guardrails.

Do not write ADRs for minor changes like renaming variables or tweaking a threshold with no architectural impact. Focus on decisions worth preserving.

### 13.2. ADR Structure

An ADR template can include:

~~~markdown
# ADR-0042: Select Database Model for Order Service

- Status: Proposed | Accepted | Rejected | Superseded
- Date: YYYY-MM-DD
- Decision owner: Team/role
- Reviewers: Names or roles
- Scope: Workload/component

## Context
Business goal, requirements, constraints, assumptions and current problem.

## Decision drivers
Latency, consistency, availability, security, operability, cost and skills.

## Options considered
Option A, Option B, Option C with evidence and trade-offs.

## Decision
The selected option and the reason it best satisfies the drivers.

## Consequences
Positive effects, negative effects, new risks, operational tasks and migration cost.

## Validation
Benchmark, proof of concept, security review, DR test or other evidence.

## Revisit conditions
The events or thresholds that should trigger a new review.

## References
Architecture diagrams, review findings, code, tickets and AWS documentation.
~~~

The template above is a reference structure. Organizations may add owners, risk acceptances, expiration dates, or approval links per their governance.

### 13.3. Status and Lifecycle

| Status | Meaning |
|---|---|
| Proposed | Under discussion; not yet an active decision |
| Accepted | Approved by authorized decision makers |
| Rejected | Evaluated and not chosen |
| Superseded | Replaced by a newer ADR |
| Deprecated | No longer recommended, though possibly still present in legacy workloads |

Never delete old ADRs when the architecture evolves. Mark the old ADR as `Superseded` and link it to the new ADR to preserve history.

## 14. ADR Example: Choosing a Database for Order Service

This example illustrates documenting trade-offs. Numbers and assumptions are synthetic practice data, not AWS benchmarks or service pricing.

### ADR-0042: Choose Database for Order Service

**Status:** Accepted

**Scope:** Order Service of an e-commerce application

**Decision owner:** Architecture owner and Order team

#### Context

Order Service stores orders, payment statuses, line items, and change history. The workload needs transactions for critical updates, queries by order ID, customer ID, and status, plus daily reporting. Data consistency must be preserved between orders and order items.

Assumed requirements:

- 1,500 requests/second at peak.
- p95 under 250 ms for core queries.
- 5-minute RPO and 60-minute RTO.
- SQL transactions and constraints required.
- Team already has operational experience with relational databases.

#### Options Considered

| Option | Strengths | Trade-offs |
|---|---|---|
| Amazon Aurora | Relational model, SQL, managed cluster, and configurable HA/read scaling | Cost, connection management, capacity planning, and engine limits |
| Amazon RDS for PostgreSQL | Managed PostgreSQL, relational semantics, and familiar ecosystem | HA/read scaling and capacity tied to instance configuration |
| DynamoDB | Managed key-value/document, scales by access pattern | Requires partition/index design; query flexibility and transaction model differ from SQL |

#### Decision

Select Aurora PostgreSQL for Order Service because transactions and relational integrity are primary requirements, queries require SQL, and the team has PostgreSQL expertise. Read scaling, Multi-AZ, backups, and PITR are configured to meet workload goals.

#### Consequences

Positive:

- Enables transactions, foreign keys, and SQL queries.
- Reduces database administration effort compared to self-managing on EC2.
- Supports offloading read workloads if benchmarks show it is needed.

Negative:

- Must manage connection pools and query performance.
- Cost may exceed key-value options for simple access patterns.
- Must test restores and failovers; never assume managed means zero disruption.

#### Validation

- Benchmark with representative datasets and workloads.
- Test p95/p99 latency, connection saturation, and failover.
- Run restore tests in an isolated environment.
- Verify transactions, schemas, constraints, and RPO markers.

#### Revisit Conditions

Re-evaluate if the workload shifts toward high-throughput key-based access, cross-table transactions are no longer required, costs exceed targets, or latency targets fail even after query tuning.

Crucially, the ADR records both the rationale and the conditions that trigger re-evaluation. Writing only "use Aurora because it fits" leaves future readers guessing which criteria mattered.

## 15. Comparing Options with a Decision Matrix

When multiple options exist, a decision matrix clarifies criteria and weights. It does not replace engineering judgment, yet reduces debates driven by gut feeling.

Synthetic example for two deployment options:

| Criterion | Weight | ECS/Fargate | EKS |
|---|---:|---:|---:|
| Operational simplicity | 25% | 5 | 2 |
| Kubernetes ecosystem | 15% | 1 | 5 |
| Workload portability | 10% | 2 | 5 |
| Team skill fit | 20% | 5 | 3 |
| Scaling/control needs | 15% | 4 | 5 |
| Cost at expected load | 15% | 4 | 3 |

Assuming a 1–5 scale, the weighted score sums each criterion score multiplied by its weight. Using the assumed numbers above:

[
Score_{Fargate}=0.25(5)+0.15(1)+0.10(2)+0.20(5)+0.15(4)+0.15(4)=3.80
]

[
Score_{EKS}=0.25(2)+0.15(5)+0.10(5)+0.20(3)+0.15(5)+0.15(3)=3.55
]

Fargate scores higher in this example, yet if the Kubernetes ecosystem is a hard constraint, EKS may still be the right choice. A decision matrix clarifies trade-offs; never use scores to obscure constraints, risks, or unverified data.

### 15.1. Selecting Criteria and Weights

- Criteria must tie directly to requirements.
- Weights must be agreed upon by owners before scoring.
- Scores must have justification or evidence.
- Do not double-count the same factor across multiple criteria to skew results.
- Clearly separate mandatory constraints from tradeable criteria.
- Perform sensitivity analysis if results hinge heavily on a single weight.

If two options score closely, build a proof of concept or run a benchmark instead of pretending there is an exact mathematical winner.

## 16. Managing Findings, Risks, and Exceptions

A finding must be specific enough for others to understand, prioritize, and verify.

### 16.1. Finding Template

~~~text
ID: AR-2026-014
Title: Restore process has not proven 5-minute RPO
Category: Reliability
Severity: High
Evidence: Backup schedule is 15 minutes; no restore validation exists yet
Impact: May lose more data than targeted during a database outage
Recommendation: Add PITR/recovery-point monitoring and run a restore drill
Owner: Database team
Due date: YYYY-MM-DD
Disposition: Open
Verification: Restore test + transaction marker comparison
~~~

### 16.2. Severity Classification

| Level | Description | Suggested Handling |
|---|---|---|
| Critical | Could cause severe compromise, major data loss, or outage of critical services | Escalate immediately, block go-live, or require interim mitigations |
| High | Major risk; fails to meet critical NFRs | Assign owner and deadline prior to agreed release milestone |
| Medium | Significant impact, though workarounds exist | Schedule with a deadline and track |
| Low | Improvement or bounded risk | Record in backlog and review periodically |

Severity must weigh impact, likelihood, exposure, detectability, and recoverability. Never assign severity purely by gut feel or comment volume.

### 16.3. Risk Acceptance

Risk acceptance is a deliberate decision. Records must include:

- Risk statement and evidence.
- Business impact and residual risk.
- Existing mitigations and alternatives considered.
- Authorized approver.
- Applicable workload, account, Region, or data scope.
- Expiration/review date.
- Triggers requiring the exception to be revisited.

Designers must not unilaterally accept risks beyond their authority. An exception lacking an owner or review date quickly becomes unmanaged technical debt.

## 17. AWS Well-Architected Tool

The AWS Well-Architected Tool helps document workloads, answer framework questions, create milestones, and track improvement plans. It standardizes reviews and preserves evaluation history.

### 17.1. Process-Level Usage

1. Identify the workload and owner.
2. Create the workload in the Well-Architected Tool with accurate scope details.
3. Select lenses or workload reviews suited to the workload type.
4. Answer questions based on evidence.
5. Record risks/high-risk issues and build an improvement plan.
6. Assign owners and due dates to actions.
7. Create a milestone to snapshot review status.
8. Re-review after major changes or on a regular cadence.

The tool does not automatically inspect all AWS configurations or prove answers are accurate. Output quality depends on the respondents and provided evidence.

### 17.2. Lenses and Scope

The Well-Architected Framework provides the baseline. AWS and the community may offer specialized lenses by workload or industry. Pick lenses based on actual need; do not attach every lens merely to inflate question counts.

When a question does not apply, record the rationale and scope. Never mark "Not applicable" to dodge a difficult requirement.

### 17.3. Improvement Plans

An improvement plan should document:

- Unmet risk or best practice.
- Action required.
- Owner and due date.
- Dependencies and effort.
- Expected outcome.
- Verification method once completed.

Never close an improvement plan item just because a PR or ticket was opened. Verify the control is deployed and achieves the expected outcome.

## 18. Managing Documentation and Decision Logs

Architecture diagrams, ADRs, review findings, and IaC must maintain clear links.

### 18.1. Where to Store

ADRs can live alongside source code in a repository, or in a documentation store with version history and proper access control. Key requirements:

- Searchable by workload and decision.
- Version history preserved.
- Clear owners and statuses.
- Linked to tickets, code, diagrams, and evidence.
- Appropriate retention and access controls.

### 18.2. Naming Conventions

Example:

~~~text
docs/
  architecture/
    diagrams/
      order-context.drawio
      order-deployment.drawio
    decisions/
      ADR-0001-order-database.md
      ADR-0002-event-delivery.md
    reviews/
      2026-11-production-readiness.md
    risks/
      architecture-risk-register.md
~~~

Name files with stable sequence numbers and topics. Never rename an ADR simply because the decision changed; create a new ADR and link back to the old one.

### 18.3. Keeping Documentation Synced with Production

Periodic reviews should compare diagrams against IaC, inventories, and telemetry. If documentation only captures the initial design, it quickly drifts from production.

You can add pull-request review gates for architecturally significant changes: requiring updates to diagrams, ADRs, or threat models when altering networking, data models, trust boundaries, or dependencies. Do not require documentation updates for trivial changes with no architectural impact.

## 19. Integrating Architecture Reviews into SDLC and IaC

Architecture reviews should be part of the software development lifecycle:

~~~mermaid
flowchart LR
    A[Discover requirements] --> B[Architecture options]
    B --> C[ADR proposed]
    C --> D[Design review]
    D --> E[Build with IaC]
    E --> F[Automated checks]
    F --> G[Deploy to test]
    G --> H[Performance / security / DR validation]
    H --> I[Production readiness review]
    I --> J[Operate and observe]
    J --> K[Periodic review]
    K --> B
~~~

### 19.1. Review Early

Decisions like account structure, Regions, database models, data residency, and trust boundaries are expensive to change later. Reviewing early catches issues while remediation costs remain low.

### 19.2. Automated Guardrails

Tools to consider:

- CloudFormation Guard or policy-as-code to validate templates.
- `cfn-lint`, `terraform validate`, and static analysis.
- IAM Access Analyzer to detect unintended access.
- AWS Config rules and conformance packs to monitor configurations.
- Security Hub and security posture tools.
- CI policy gates for secrets, container images, dependencies, and IaC.

Automated checks only verify what rules are written to check. A passing template does not prove the architecture meets RTO/RPO or that the application can recover. Combine automated checks with design reviews and runtime testing.

### 19.3. Change Impact Analysis

Before applying changes, identify:

- Affected components and teams.
- API/schema compatibility.
- Data migrations and rollbacks.
- Security groups, IAM, KMS, and network routes.
- Capacity, quotas, and cost.
- Observability and alerts.
- Backups, restores, and DR.
- Deployment timing, maintenance windows, and communications.

A tiny security group edit can disrupt multiple services. A schema tweak can break older consumers. Reviews must evaluate real impact rather than judging by lines of code changed.

## 20. Architecture Review Anti-Patterns

1. **Reviewing too late:** hard-to-reverse decisions are already deployed before evaluation.
2. **Diagram-only reviews:** ignoring NFRs, data flows, IAM, failure modes, or costs.
3. **Service checklists:** checking off CloudWatch, Backup, or KMS without inspecting configurations and evidence.
4. **One-size-fits-all:** forcing every workload into one pattern despite differing requirements.
5. **Opinion-driven:** choosing technologies by preference or hype without criteria.
6. **No alternatives:** ADRs recording only the chosen option with no alternatives or trade-offs.
7. **False precision:** treating weighted scores or synthetic estimates as infallible proof.
8. **No owner:** findings lacking accountable owners and deadlines.
9. **Risk accepted forever:** exceptions without expiration dates or review triggers.
10. **Documentation drift:** diagrams and ADRs never updated after changes.
11. **Tool-driven reviews:** treating Well-Architected Tool output as automatic certification.
12. **Security-only reviews:** ignoring performance, cost, operability, and sustainability.
13. **No failure tests:** reviewing only the happy path without testing broken dependencies.
14. **No evidence:** relying on verbal assurances without benchmarks, logs, tests, or policies.
15. **Review as approval theater:** holding meetings without tracking findings or outcomes.

## 21. Case Study: Reviewing an Order Platform Architecture

An enterprise is deploying an order platform on AWS. Users access via web/mobile. The system includes Catalog, Checkout, Order, Payment, and Inventory. The design team proposes:

- CloudFront and WAF at the edge.
- ALB routing to ECS services.
- Aurora PostgreSQL for Orders.
- DynamoDB for Catalog cache/index per access patterns.
- SQS for background tasks.
- EventBridge for domain event routing.
- S3 for invoices and exported files.
- CloudWatch, CloudTrail, and AWS Backup for operations.

### 21.1. Review Questions

**Business and NFRs**

- Does peak traffic follow promotional campaign patterns?
- What is the checkout latency target?
- Does Payment require idempotency and auditing?
- How do Order RTO/RPO targets differ from Catalog?

**Reliability**

- If the Payment provider times out, does Checkout retry safely without double charging?
- If SQS backlogs grow, is there an alarm on age of oldest message?
- If Aurora fails over, do connection pools reconnect cleanly?
- Are restore tests executed for both databases and invoice files?

**Security**

- Is payment data stored, and if so, within what scope?
- Does the Payment task role have read permissions on the Catalog bucket?
- Do clients access only through the edge, or is the ALB still publicly reachable directly?
- Do S3 bucket policies and KMS keys restrict principals?

**Performance**

- How does Catalog cache invalidation work?
- Do Aurora connection counts align with ECS task scaling?
- Do queue workers scale on backlog depth or CPU?
- Have campaign peak benchmarks and slow-dependency tests been run?

**Cost**

- How many origin requests does CloudFront caching eliminate?
- Are NAT Gateway and cross-AZ data transfer costs significant?
- Can staging scale down outside working hours?
- Does log retention match audit requirements?

**Operations**

- Is a correlation ID propagated across Checkout, Order, and Payment?
- Is there a runbook for Payment provider outages?
- Who owns handling DLQ messages?
- Are restore, validation, and failback procedures ready?

### 21.2. Sample Findings

| ID | Finding | Severity | Action |
|---|---|---|---|
| AR-01 | Payment retries lack cross-request idempotency keys | High | Add contract and test duplicate charges |
| AR-02 | ECS task roles share broad policies across services | High | Split roles per service and narrow resource scopes |
| AR-03 | Queue age unmonitored when downstream slows | Medium | Add metrics, alarms, and runbooks |
| AR-04 | Database RTO relies solely on estimates | High | Run restore test and measure T0–T5 |
| AR-05 | NAT/data transfer omitted from cost estimate | Medium | Add traffic model and actual cost review |

### 21.3. Resulting Sample ADR

An ADR can record the decision to use SQS for retryable background work while using EventBridge to route domain events to multiple consumers. The ADR should explain why a single queue does not replace an event bus when multiple subscribers exist, and why an event bus does not replace queues when per-consumer buffering, visibility timeouts, or DLQs are needed.

Following the review, the design team updates IAM roles, idempotency, queue alarms, restore tests, and cost models. The review closes only after actions have verification evidence or approved risk acceptances.

## 22. Review Agenda and Minutes Template

~~~markdown
# Architecture Review Record

## Workload
- Name:
- Owner:
- Business objective:
- Environment / account / Region:
- Review type:
- Date:

## Scope
- In scope:
- Out of scope:
- Assumptions:
- Constraints:

## Requirements
- Availability:
- Latency / throughput:
- RTO / RPO:
- Security / privacy:
- Cost:
- Compliance:

## Participants
- Architect:
- Engineering:
- Security:
- Operations:
- Business owner:

## Review summary
- Architecture overview:
- Main decisions:
- Evidence reviewed:
- Open questions:

## Findings
| ID | Category | Severity | Finding | Owner | Due date | Status |

## Decisions
- ADR link:
- Accepted trade-offs:
- Risk acceptance:

## Outcome
- Ready:
- Ready with actions:
- Rework required:
- Decision owner:
- Next review date:
~~~

### 22.1. Review Outcomes

Three straightforward outcomes can be used:

- **Ready:** no blocking findings remain and required evidence is satisfied.
- **Ready with actions:** approved to proceed within agreed scope, with clear actions, owners, and deadlines.
- **Rework required:** unresolved risks or missing information prevent a go-ahead decision.

This is an internal governance convention, not an AWS-defined status. Organizations must define who holds approval authority and which exceptions require escalation.

## 23. When Should You Re-Review?

Architectures are not static. Re-review when:

- Workload traffic grows or traffic profiles shift significantly.
- New Regions, accounts, data stores, or third-party dependencies are added.
- Authentication, authorization, trust boundaries, or data classifications change.
- RTO/RPO, retention, compliance, or data residency requirements change.
- Incidents, outages, data corruption, or security findings occur.
- Major AWS service features, quotas, pricing, or support terms change.
- Costs diverge from forecasts across multiple periods.
- Teams, ownership, or operational models change.
- An ADR's revisit condition is triggered.

Periodic reviews should not run strictly by calendar. Combining scheduled cadences with event triggers ensures timely reviews when meaningful changes occur.

## 24. Self-Check Exercises

### Question 1

A team claims their workload is highly available because it runs two EC2 instances in the same AZ. What should the reviewer ask?

**Answer:** Are the instances in separate failure domains, how are load balancer health checks configured, how is an AZ outage handled, where does state live, and have RTO/RPO been tested? Two instances in the same AZ remain vulnerable to a single-AZ failure.

### Question 2

Is the requirement "the API must be fast" enough to choose compute and databases?

**Answer:** No. Latency percentiles, throughput, payloads, concurrency, access patterns, and growth must be quantified to benchmark and compare options.

### Question 3

An ADR only states "chose EKS for flexibility." What is missing?

**Answer:** Context, decision drivers, alternatives considered, trade-offs, operational burden, security, cost, validation evidence, consequences, and revisit conditions.

### Question 4

The AWS Well-Architected Tool marks a question as best practice achieved. Does that prove production is configured properly?

**Answer:** No. The tool records answers and evaluates based on inputs provided. Real configuration evidence, testing, and operational verification are still required.

### Question 5

A workload needs a 30-minute RTO and a 1-minute RPO. Can you immediately conclude multi-Region is required?

**Answer:** Not yet. Analyze failure domains, Multi-AZ/PITR capabilities, Regional outage requirements, replication semantics, consistency, cost, and failover/failback. Multi-Region is just one option.

### Question 6

Why should a finding not be considered resolved as soon as a ticket is created?

**Answer:** A ticket merely logs work to be done. Changes must be implemented, verified, and backed by evidence before closing the finding.

### Question 7

When is accepting a risk preferable to fixing it immediately?

**Answer:** When an authorized owner determines residual risk is acceptable within a defined scope and timeframe, backed by mitigations, an expiration/review date, and clear triggers. Risks exceeding authority must be escalated.

### Question 8

A request flows through CloudFront, ALB, and ECS. Why must the diagram mark TLS termination?

**Answer:** Because TLS may terminate at one hop while subsequent hops use HTTP or separate TLS. Marking decryption points accurately exposes data exposure and trust boundaries.

### Question 9

A decision matrix scores EKS higher than ECS, yet the organization lacks Kubernetes operational capability. Should EKS be chosen automatically?

**Answer:** No. Team skills and operational capability are constraints/drivers. Evaluate training, platform teams, managed add-ons, on-call burden, and cost before deciding.

### Question 10

After changing the database model, should the old ADR be reviewed?

**Answer:** Check the ADR's revisit conditions. If the new decision replaces the old one, write a new ADR and mark the old one `Superseded`, preserving historical links.

### Question 11

A service uses SQS without a DLQ or queue age metrics. What should the reviewer note?

**Answer:** This is a gap in failure handling and operability. Inspect retries/redrive, message retention, visibility timeouts, backlog/age alarms, and ownership for failed messages.

### Question 12

A cost estimate includes EC2 and RDS while omitting NAT Gateways, data transfer, and log ingestion. Is the estimate trustworthy?

**Answer:** Not yet. Add networking, observability, backups, requests, storage, support, and operations for a realistic total cost.

### Question 13

When should an ADR be created?

**Answer:** When a decision has long-term impact, spans multiple teams/components, is hard to reverse, or affects security, reliability, cost, data models, accounts/Regions, or platforms.

### Question 14

A workload passed a pre-production review. Does it need a review after an incident?

**Answer:** Yes, if the incident revealed flawed architectural assumptions or controls. A post-incident review updates failure models, runbooks, ADRs, and action plans.

### Question 15

Can the six Well-Architected pillars be optimized independently?

**Answer:** Not entirely. Pillars involve trade-offs and interact with one another. Optimize holistically around workload goals and accept intentional trade-offs.

## 25. Architecture Review Checklist

### Business and Scope

- [ ] Workload, owners, business objectives, and user journeys are clear.
- [ ] In-scope, out-of-scope, assumptions, and constraints are documented.
- [ ] Functional requirements and NFRs are quantified.
- [ ] Data classifications and dependencies are identified.

### Design and Decisions

- [ ] Context, component, deployment, and data flow diagrams have sufficient detail.
- [ ] Options and trade-offs have been compared.
- [ ] Failure modes and blast radius have been evaluated.
- [ ] ADRs exist for significant decisions.
- [ ] ADRs include status, owners, consequences, validation, and revisit conditions.

### Well-Architected

- [ ] Operational Excellence has telemetry, runbooks, ownership, and change processes.
- [ ] Security has least privilege, encryption, threat models, and auditing.
- [ ] Reliability has HA, quotas, retries, backups, restores, and DR tests.
- [ ] Performance has workload models and benchmarks.
- [ ] Cost has estimates, usage assumptions, and owners.
- [ ] Sustainability has plans to reduce idle capacity and waste.

### Review Outcome

- [ ] Findings include severity, evidence, owners, and deadlines.
- [ ] Risk acceptances specify authority, scope, and expiration/review dates.
- [ ] Action items specify verification methods.
- [ ] Diagrams, ADRs, and IaC stay synchronized.
- [ ] Outcomes and next review dates are recorded.

## 26. Official References

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
- [AWS Well-Architected Framework: Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/framework/operational-excellence.html)
- [AWS Well-Architected Framework: Security](https://docs.aws.amazon.com/wellarchitected/latest/framework/security.html)
- [AWS Well-Architected Framework: Reliability](https://docs.aws.amazon.com/wellarchitected/latest/framework/reliability.html)
- [AWS Well-Architected Framework: Performance Efficiency](https://docs.aws.amazon.com/wellarchitected/latest/framework/performance-efficiency.html)
- [AWS Well-Architected Framework: Cost Optimization](https://docs.aws.amazon.com/wellarchitected/latest/framework/cost-optimization.html)
- [AWS Well-Architected Framework: Sustainability](https://docs.aws.amazon.com/wellarchitected/latest/framework/sustainability.html)
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/welcome.html)
- [AWS Cloud Adoption Framework](https://docs.aws.amazon.com/whitepapers/latest/overview-aws-cloud-adoption-framework/welcome.html)
- [AWS CloudFormation Guard](https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html)
- [AWS IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html)
- [AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/WhatIsConfig.html)
- [AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html)

Feature names, lens questions, quotas, pricing, and service availability may change over time and by Region. When reviewing a specific workload, cross-check current documentation and live evidence in the target account/Region.
