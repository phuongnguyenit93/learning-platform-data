# AWS Well-Architected Framework and the Six Pillars

When designing a workload on AWS, choosing the right services is only part of the job. The architecture must also meet business objectives, protect data, withstand failures, maintain performance, control costs, and use resources responsibly. A decision that optimizes for one goal can create issues for another: adding replicas increases resilience but increases cost; encryption and deep inspection protect data but can increase latency; using self-managed services allows granular control but increases operational overhead.

The AWS Well-Architected Framework provides a structured approach to evaluating those decisions. The Framework presents questions and best practices that help architecture teams identify risks, document trade-offs, and plan improvements throughout the workload lifecycle. The Framework is not a mandatory list of services, a single reference architecture for every system, or a compliance certification.

This lesson focuses on the six pillars of Cloud Workloads: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability. It also introduces Cloud Foundations, the organizational foundation section added by AWS in the Framework update on November 16, 2026, along with how to use the AWS Well-Architected Tool to conduct reviews and track improvements.

## Learning Objectives

After this lesson, learners can:

- Explain the purpose of the AWS Well-Architected Framework and the role of the six pillars.
- Distinguish Cloud Foundations from Cloud Workloads in the current Framework structure.
- Translate business requirements into measurable architectural criteria.
- Identify design decisions to evaluate in each pillar.
- Analyze trade-offs between security, reliability, performance, cost, operations, and sustainability.
- Conduct a Well-Architected review with clear scope, evidence, owners, and an improvement plan.
- Use the AWS Well-Architected Tool, lenses, profiles, milestones, and workload reports to track progress.
- Apply the Framework to an e-commerce workload deployed on AWS.

## 1. What Is the AWS Well-Architected Framework?

The AWS Well-Architected Framework is a collection of design principles, evaluation questions, and best practices that help teams build, deploy, and operate workloads on AWS. The Framework creates a common language for product owners, architects, developers, security engineers, SREs, operations, and finance to discuss architecture quality together.

The Framework helps answer questions such as:

- Can the workload continue serving functionality when an Availability Zone or component fails?
- Who and which services are allowed to access data, and how are those permissions controlled?
- Can the team detect issues before users are impacted?
- Does performance meet demand during peak hours and when load changes?
- Is the cost of the workload commensurate with business value?
- Are provisioned resources used efficiently throughout their lifecycle?

A review under the Framework is a constructive conversation about architectural decisions. It is not an audit or an automated mechanism to certify that a workload complies with every standard. The review helps uncover gaps, understand the rationale behind decisions, and identify improvement actions.

### 1.1. What Is a Workload?

A workload is the collection of AWS resources, application code, data, configurations, and related components that make up an application or service serving a business objective. For example:

- An e-commerce system comprising a website, APIs, order service, payment, databases, queues, and deployment pipelines.
- A data processing platform comprising ingestion, storage, batch/stream processing, catalog, analytics, and dashboards.
- An internal service comprising an application, identity, enterprise network integration, logging, and support mechanisms.

The workload scope should be clear enough to identify owners, users, data boundaries, dependencies, environments, business objectives, and operational criteria. If the scope is too broad, the review struggles to go deep into specific decisions. If it is too narrow, critical dependencies may be missed.

### 1.2. Framework Structure Updated on November 16, 2026

In the November 16, 2026 update, AWS consolidated the content of the six pillar whitepapers into a unified Framework source, updated many best practices, added Cloud Foundations, and expanded guidance on AI adoption, AI-driven operations, and architecture reviews.

The Framework is now presented in two parts:

| Part | Scope | Core Question |
|---|---|---|
| Cloud Foundations | Foundational capabilities at the organization, account, and shared services levels. | Has the organization created an AWS environment with consistent governance, identity, observability, security, networking, and cost management? |
| Cloud Workloads | Designing, building, and operating individual workloads. | Does a specific workload satisfy the six pillars? |

Cloud Foundations is typically managed by the cloud platform, foundation engineering, or cloud engineering team. Cloud Workloads is typically designed, built, and operated by product teams and workload owners. The two parts complement each other: a solid foundation helps workloads inherit guardrails and shared services; workload reviews help uncover new requirements that the platform needs to support.

### 1.3. Seven Capabilities of Cloud Foundations

| Capability | Description |
|---|---|
| Multi-account environment | Organizing AWS accounts and organizational units to create isolation boundaries, separate environments, and apply policies consistently. |
| Identity and access management | Centralizing identity management, protecting privileged accounts, and applying least privilege. |
| Central observability management | Standardizing logs, metrics, and traces, and aggregating telemetry for a unified view across the organization. |
| Resource and inventory management | Standardizing tags, inventory, dependencies, shared patterns, and automating patching. |
| Security and compliance | Establishing emergency access, audit logging, threat detection, vulnerability management, and forensic readiness. |
| Cloud financial management | Cost allocation, budgets, licensing, cost visibility, and commitment strategies. |
| Networking and connectivity | Managing network topology, DNS, protection controls, and connectivity between accounts, Regions, workloads, and on-premises. |

For example, an organization can use AWS Organizations and service control policies for account governance; IAM Identity Center for workforce access management; a centralized logging account to collect CloudTrail; Amazon CloudWatch and Amazon OpenSearch Service for observability; AWS Config and Security Hub to detect drift; AWS Cost Explorer and Cost and Usage Reports for cost management; and Transit Gateway and Route 53 Resolver for connectivity management.

Cloud Foundations does not replace individual workload reviews. A well-configured landing zone can still contain an application that is poorly designed in terms of data, resilience, or performance.

## 2. General Design Principles on AWS

In addition to the six pillars, the Framework provides general principles to guide architectural decisions:

1. **Stop guessing capacity:** measure load, set thresholds, and use appropriate scaling instead of fixed provisioning based on data-poor predictions.
2. **Test systems at production scale:** create representative test environments to evaluate behavior under high load or failures.
3. **Automate to make architectural experimentation easier:** use Infrastructure as Code, pipelines, and reproducible environments to compare options and reduce manual effort.
4. **Allow for evolutionary architectures:** favor reversible decisions, deploy incrementally, and reduce the cost of reversing changes when requirements evolve.
5. **Drive architectures using data:** base decisions on latency, throughput, error rate, utilization, availability, cost, and business outcomes.
6. **Improve through game days:** simulate incidents and rehearse operational procedures to uncover gaps before real incidents happen.

These principles are interconnected. For example, autoscaling requires reliable telemetry; testing at production scale requires environments that can be automatically created and torn down; game days require runbooks, designated owners, and success criteria.

## 3. Six Pillars of the AWS Well-Architected Framework

| Pillar | Goal | Architectural Question |
|---|---|---|
| Operational Excellence | Operate efficiently, gain workload observability, and continuously improve processes. | Can the team deploy changes, detect issues, respond, and learn from incidents? |
| Security | Protect data, systems, and assets; control access, detect, and respond to events. | Do the right identities access the right resources under the right conditions with auditability? |
| Reliability | Workload performs its intended function correctly and consistently, and recovers from failures. | Can the workload withstand failures, handle load changes, and recover within business objectives? |
| Performance Efficiency | Use resources efficiently to meet performance requirements as demand and technology evolve. | Does the architecture meet latency, throughput, and capacity targets with appropriate resource choices? |
| Cost Optimization | Deliver business value at an appropriate cost and eliminate waste. | Does the team know where costs come from and select the right services, sizing, and pricing models? |
| Sustainability | Reduce energy consumption, resource usage, and environmental impact of workloads. | Is each unit of work completed with the necessary and efficient level of resources? |

You should not maximize a single pillar in isolation and assume the entire architecture is sound. A system running many replicas across multiple Regions may have high availability but be expensive and difficult to operate. A system choosing the cheapest resources may fail to meet latency or availability targets. Business goals, mandatory constraints, and risk tolerance must be defined before making decisions.

## 4. Operational Excellence

Operational Excellence focuses on building software properly, operating workloads effectively, understanding system health, and continuously improving to deliver value to users.

AWS organizes guidance for this pillar into four areas: Organization, Prepare, Operate, and Evolve.

### 4.1. Organize Teams Around Business Outcomes

Development and operations teams need to understand the goals the workload serves, such as order success rate, transaction processing time, number of users served, or recovery time. Responsibilities must be clear among the product owner, application team, platform team, security, and on-call team.

Practices to adopt:

- Define owners for each workload and critical dependency.
- Define technical KPIs tied to business outcomes.
- Establish change management processes and decision-making authority during incidents.
- Use managed services when they reduce operational burden and meet requirements.
- Document operational knowledge to reduce reliance on any single individual.

### 4.2. Prepare – Preparing Before Production

Before putting a workload into production, risks must be identified, change procedures tested, and the team ensured to have the capability to support the system.

Examples:

- Use AWS CodePipeline, CodeBuild, or GitHub Actions to automate build/test/deploy.
- Use CloudFormation, AWS CDK, or Terraform to manage infrastructure as code.
- Apply quality gates: unit tests, integration tests, security scans, policy validation, and appropriate approvals.
- Use canary or blue/green deployments to reduce blast radius.
- Prepare runbooks, escalation paths, dashboards, and on-call rotations.
- Verify service quotas, dependencies, backups, and rollback procedures before release.

### 4.3. Operate – Operating and Observing

A workload must emit telemetry so the team understands what is happening. Metrics should be tied to user behavior and service objectives.

Examples:

- Amazon CloudWatch metrics, logs, alarms, and dashboards.
- AWS X-Ray or OpenTelemetry to trace requests across multiple services.
- CloudTrail to audit AWS administrative activities.
- SLOs, error budgets, latency percentiles, throughput, error rates, and queue age.
- EventBridge, SNS, SQS, or Systems Manager Automation to orchestrate responses.

Avoid creating excessive alerts without clear actions. A useful alert must indicate impact, owner, trigger condition, and next remediation steps.

### 4.4. Evolve – Learning and Improving

After each incident, failed deployment, or game day, the team should look for systemic root causes rather than assigning individual blame.

Activities include:

- Conducting post-incident reviews and documenting lessons learned.
- Measuring change failure rate, MTTR, and the volume of repetitive manual tasks.
- Automating procedures with clear outcomes and conditions.
- Updating runbooks, architecture, dashboards, and decision records.
- Adding improvement items to the backlog with an owner and deadline.

For example, if the team frequently intervenes manually when queue backlog grows, evaluate consumer autoscaling, visibility timeout, a dead-letter queue, and alarms based on the age of the oldest message.

## 5. Security

Security focuses on protecting data, systems, and assets; ensuring the right human and workload identities have appropriate access; and maintaining the ability to observe, protect, and respond when incidents occur. Security must be integrated into design, development, deployment, and operations.

AWS organizes this pillar into four primary practice areas.

### 5.1. Security Governance and Operations

The organization must define control objectives, policies, responsibilities, and response procedures. It must have the capability to detect events, investigate, and recover.

Examples:

- AWS Organizations, service control policies, and account separation.
- AWS CloudTrail, AWS Config, and Security Hub.
- Amazon GuardDuty to detect suspicious behavior.
- Amazon Inspector to detect vulnerabilities.
- AWS Security Incident Response or internal incident response procedures.
- Procedures for preserving evidence and running tabletop exercises/game days.

### 5.2. Identity and Access Management

Every access must be tied to an identity and a set of permissions scoped to the task.

Practices:

- Use IAM roles and temporary credentials for workloads instead of long-lived access keys.
- Use IAM Identity Center or federation for the workforce.
- Apply least privilege, permission boundaries, and separation of duties.
- Protect the root user and privileged accounts with MFA.
- Use IAM Access Analyzer to review policies and trust relationships.
- Periodically review permissions and remove unused credentials.

An ECS task that needs to read objects from S3 should use a task role scoped to the required bucket/prefix. Never embed administrative account access keys in environment variables or source code.

### 5.3. Data Protection

Data must be classified and protected throughout its entire lifecycle: creation, transit, storage, access, backup, sharing, and deletion.

Examples:

- AWS KMS to manage encryption keys.
- TLS to protect data in transit over the network.
- S3 Block Public Access, bucket policies, and access points.
- Amazon Macie to discover sensitive data in S3.
- Backups, retention, lifecycle, and access controls on backup copies.
- Tokenization or masking when applications do not need the raw data.

Do not simply enable encryption and consider it done. You must manage key policies, rotation, decrypt permissions, backups, and recovery procedures.

### 5.4. Infrastructure and Application Protection

Protection must be applied across multiple layers: account, network, compute, application, and data.

Examples:

- Security groups, network ACLs, AWS Network Firewall, and AWS WAF.
- Patch management using Systems Manager.
- Hardening AMIs/container images and scanning dependencies.
- Secure coding, code review, secret scanning, and SAST/DAST.
- Securing deployment pipelines and CI/CD role permissions.
- Separating public subnets, private subnets, and data subnets according to appropriate trust boundaries.

### 5.5. Shared Responsibility Model

AWS is responsible for protecting the cloud infrastructure that AWS operates, including physical facilities, hardware, networking, and the virtualization layer. Customers are responsible for security in the cloud depending on the selected services: data, identities, resource configurations, applications, and the guest operating system when using EC2.

With EC2, customers manage the operating system, patches, application software, and security groups. With managed services like S3 or DynamoDB, AWS manages more of the infrastructure components, while customers still manage data, IAM permissions, encryption options, backups, and replication strategies.

The level of responsibility varies by service and deployment model. Architects must review the specific responsibilities of each service before designing controls.

## 6. Reliability

Reliability is the ability of a workload to perform its intended function correctly and consistently when expected, throughout its lifecycle. This pillar focuses on resilience: the ability to recover from disruptions, handle load changes, and reduce the impact of failures or misconfigurations.

AWS groups best practices into four areas.

### 6.1. Foundations

The foundation must support the workload's reliability goals:

- Check service quotas and API limits.
- Design network topology and dependencies.
- Choose Regions/AZs suited to business continuity requirements.
- Identify dependencies on external services and fallback capabilities.
- Validate permissions, DNS, certificates, and connectivity before production.

### 6.2. Workload Architecture

Design the system so that a failure in one component does not bring down the entire workload.

Techniques:

- Distribute the workload across multiple Availability Zones when availability requirements demand it.
- Use Elastic Load Balancing and Auto Scaling to distribute load and replace failed instances.
- Decouple components using SQS, EventBridge, or streaming services.
- Use retries with exponential backoff and jitter, timeouts, circuit breakers, and idempotency.
- Limit blast radius using cell-based architecture or fault isolation.
- Avoid single points of failure on critical paths.

Multi-AZ and multi-Region serve different goals. Multi-AZ typically provides fault tolerance within a single Region; multi-Region can serve disaster recovery, data residency, or global latency requirements, but increases complexity and cost. Do not deploy multi-Region unless RTO/RPO and business impact require it.

### 6.3. Change Management

Changes are also a source of failures. Resources must be monitored, capacity adjusted, and deployments controlled.

Examples:

- Monitor workload resources and dependencies.
- Use autoscaling based on appropriate metrics.
- Roll out changes in stages.
- Verify compatibility and migration plans for schemas/databases.
- Automatically roll back when health checks or SLOs breach thresholds.

### 6.4. Failure Management

Failures will occur; the architecture must be prepared to detect, isolate, recover, and learn.

Practices:

- Back up data and test restore capability.
- Use fault isolation to contain incident scope.
- Design to withstand component/AZ failures.
- Test failure scenarios and recovery procedures.
- Plan disaster recovery based on RTO and RPO.

RTO (Recovery Time Objective) is the target time to restore the service. RPO (Recovery Point Objective) is the maximum acceptable data loss measured in time that the business can tolerate. Having backups exist is not enough; restores must be tested and actual recovery times measured.

## 7. Performance Efficiency

Performance Efficiency focuses on using resources efficiently to meet performance requirements and maintaining that efficiency as demand or technology changes.

### 7.1. Define Performance Requirements

Start with measurable business requirements:

- p95/p99 latency for critical APIs.
- Throughput or transactions per second.
- Number of concurrent users.
- Batch processing duration.
- Error rate and stability under traffic spikes.
- Data freshness or query completion time.

Do not optimize a technical metric if it does not reflect user experience or product goals.

### 7.2. Select and Configure Resources

Select services based on access patterns and workload characteristics:

| Need | Selection Direction |
|---|---|
| General-purpose compute | EC2, ECS, EKS, or AWS Lambda depending on operational model and load. |
| Containers without managing servers | AWS Fargate. |
| High-scale key-value/document access | Amazon DynamoDB. |
| Relational data and SQL transactions | Amazon RDS or Amazon Aurora. |
| Object/file storage | Amazon S3 or an appropriate storage service. |
| Read-heavy caching | Amazon ElastiCache or edge caching. |
| Global content distribution | Amazon CloudFront. |
| Event and message processing | Amazon SQS, SNS, EventBridge, or streaming services. |

Beyond service type, choose the right instance family, storage class, IOPS, network throughput, cache strategy, and database indexes.

### 7.3. Monitor, Test, and Improve

- Use CloudWatch metrics and dashboards to track latency, utilization, and saturation.
- Load test with a traffic profile close to production.
- Profile to identify CPU, memory, query, or network bottlenecks.
- Check cache hit ratios and data access patterns.
- Compare configurations using reproducible experiments.
- Re-evaluate when workloads, traffic, or AWS services change.

For example, if product page p99 latency increases due to database read load, check query plans, indexes, cache hit ratio, and connection pools before blindly scaling up the database size.

## 8. Cost Optimization

Cost Optimization is the continual process of achieving business outcomes at an appropriate cost. The goal is not always choosing the cheapest service, but achieving business value at the right cost while still meeting functional, security, reliability, performance, and sustainability requirements.

AWS groups this pillar into four areas.

### 8.1. Effective Cloud Financial Management

The organization needs to know who is responsible for costs and what cost targets the workload should meet.

Practices:

- Define owners and cost allocation tags.
- Build budgets and forecasts.
- Align finance, engineering, and product teams.
- Set cost targets by workload or business unit.
- Evaluate business value per unit of cost.

### 8.2. Expenditure and Usage Awareness

You cannot optimize spending that is not observed and allocated.

Tools and practices:

- AWS Cost Explorer to analyze usage/cost.
- AWS Budgets to alert on thresholds.
- Cost and Usage Reports for granular analysis.
- Cost allocation tags and cost categories for accountability.
- Track data transfer, NAT Gateway, idle resources, storage, and log ingestion.

### 8.3. Cost-Efficient Resources

Choose the right services, resource types, sizes, and pricing models.

Examples:

- Right-size EC2/RDS based on utilization.
- Use Graviton if compatible and more efficient for the workload.
- Use Spot Instances for interruption-tolerant workloads.
- Use Savings Plans or Reserved Instances for steady-state usage after analysis.
- Use S3 Lifecycle to transition infrequently accessed data to appropriate storage classes.
- Stop or schedule dev/test environments when not in use.

Do not purchase commitments just for discounts if actual demand is not yet stable.

### 8.4. Continuous Optimization

Costs change with load, architecture, and service pricing. A review cadence and automation are required.

- Use AWS Compute Optimizer to find right-sizing opportunities.
- Autoscale based on demand.
- Remove unused snapshots, volumes, IPs, and resources through a safe process.
- Review data transfer and cross-Region traffic.
- Re-evaluate service choices when AWS introduces new managed capabilities.
- Track cost per request, cost per order, or cost per transaction.

A cost-optimized architecture must account for operational costs, licensing, data transfer, backups, observability, and engineering effort, not just compute pricing.

## 9. Sustainability

The Sustainability pillar focuses on the environmental impact of workloads, particularly energy and resource efficiency. The goal is to accomplish useful work with fewer required resources across the entire workload lifecycle.

AWS organizes content into six practice areas.

### 9.1. Region Selection

Choose Regions based on regulatory requirements, data residency, latency, cost, availability, and sustainability goals. Regions closer to users can reduce latency and network transfer; energy and environmental goals should also be factored in.

### 9.2. Alignment to Demand

Align resources with actual demand:

- Autoscale with load.
- Shut down workloads that do not need to run continuously.
- Delete unused resources.
- Reduce excess capacity.
- Use queues or batch processing to utilize resources efficiently where appropriate.

### 9.3. Software and Architecture

- Choose efficient algorithms and data structures.
- Reduce redundant computation.
- Use caching to avoid unnecessary queries or data transfers.
- Design services to scale independently.
- Reduce payload sizes and unnecessary data processing.
- Avoid overprovisioning solely for rare traffic peaks.

### 9.4. Data

- Define appropriate retention periods.
- Use lifecycle policies to move data to suitable storage tiers.
- Delete duplicates and data that no longer has value according to policy.
- Compress, partition, and optimize data formats where appropriate.
- Avoid unnecessary repeated data movement across the network.

### 9.5. Hardware and Services

Choose compute, storage, and managed services suited to the job. Keep track of more efficient hardware options, such as Graviton when applications are compatible. Managed services can share and utilize infrastructure at scale while reducing the operational work teams must perform themselves.

### 9.6. Process and Culture

Set sustainability goals and measure impact per unit of work, such as energy or resources per transaction. Incorporate resource efficiency criteria into architecture reviews, procurement, development, and operations. Track improvements over time rather than doing a one-off exercise.

Sustainability does not mean cutting resources at all costs. An under-provisioned workload can run longer, retry more often, and cause greater overall impact. Both output and resource consumption must be measured together.

## 10. Trade-offs Across the Six Pillars

A single architectural decision often affects multiple pillars. Document the goals, alternatives, impacts, and when the decision will be reviewed.

| Decision | Primary Benefit | Cost or Risk to Consider |
|---|---|---|
| Multi-AZ database | Increases AZ-level fault tolerance. | Increases cost, replication traffic, and failover testing requirements. |
| Multi-Region active-active | Can reduce downtime and latency for global users. | Increases complexity, data synchronization, conflict handling, and cost. |
| Synchronous replication | Reduces risk of data loss during failover. | Can increase write latency and network dependency. |
| Using managed services | Reduces patching, scaling, and platform operations work. | Reduces fine-grained control and may hit service constraints. |
| Detailed logging | Improves investigation and auditability. | Increases ingestion/storage costs and noise if poorly filtered. |
| Aggressive caching | Reduces latency and database load. | Requires handling cache invalidation, stale data, and consistency. |
| Spare capacity | Can absorb traffic spikes or component failures. | Increases idle capacity cost and sustainability impact. |
| Serverless | Reduces server management and suits variable loads. | Requires considering cold starts, concurrency quotas, timeouts, and per-request cost. |

### 10.1. Documenting Architectural Decisions

An Architecture Decision Record (ADR) can include:

1. Context and business requirements.
2. Options evaluated.
3. Selected decision and rationale.
4. Pillars improved.
5. Impact on remaining pillars.
6. Metrics to verify success.
7. Accepted residual risks and mitigations.
8. Owner and review date.

For example: an order workload runs across three Availability Zones to meet availability targets. The team accepts higher compute/database costs and sets a defined failover time target. The decision is reviewed quarterly using availability, RTO, cost per order, and game day results.

There is no single availability, RTO, or RPO target that fits every workload. Values must be derived from the business impact of downtime and data loss.

## 11. Process for Conducting a Well-Architected Review

Reviews should be conducted at key milestones such as before production, after a major architecture change, after a severe incident, or when business requirements change.

### Step 1: Define Workload Scope

Document:

- Workload name, owner, environment, and AWS accounts.
- Users and business outcomes.
- Data classification and regulatory constraints.
- Internal/external dependencies.
- Region/AZ, network boundaries, and data flows.
- SLOs, availability, latency, throughput, RTO, and RPO.

### Step 2: Gather Evidence

Prepare architecture diagrams, data flows, IAM models, deployment pipelines, dashboards, incident history, cost reports, backup/restore tests, and security findings. Evidence ensures the review is based on how the workload actually operates rather than assumptions in documentation.

### Step 3: Evaluate the Six Pillars

For each question, identify:

- Best practices currently applied.
- Supporting evidence.
- Practices not applied or not applicable.
- Rationale if marked as not applicable.
- Risks and impact if not improved.

Do not mark a practice as applied just because an AWS service is enabled. For instance, having CloudWatch does not mean good observability if SLOs, dashboards, and actionable alerts are missing.

### Step 4: Identify and Prioritize Risks

Classify risks by impact, likelihood, resource scope, exploitability, and business requirements. Identify items that must be addressed before production or before the next release.

### Step 5: Create an Improvement Plan

Each improvement item needs:

- Description of the issue and impact.
- Specific action.
- Owner and collaborating teams.
- Priority and deadline.
- Effort, dependencies, and change window.
- Definition of done and verification evidence.

### Step 6: Implement and Verify

Deploy changes via IaC/pipelines or the appropriate change process. Re-verify using metrics, security checks, load tests, restore tests, or game days. Update architecture diagrams and ADRs to reflect the new state.

### Step 7: Save a Milestone and Review Again

Save a milestone to snapshot the workload state at a point in time. Compare milestones across reviews to measure the number of risks reduced, remaining risks, and newly emerged issues.

## 12. AWS Well-Architected Tool and Lenses

The AWS Well-Architected Tool (AWS WA Tool) helps document architectures, evaluate workloads against best practices, and track improvements. The tool helps standardize the review process and generate improvement plans.

### 12.1. Workloads and Lenses

When creating a workload in the WA Tool, the team enters information about the workload, environment, owner, architecture, and the lenses to evaluate.

A lens is a set of questions and best practices for a specific architectural scope:

- The AWS Well-Architected Framework lens evaluates the six pillars.
- AWS-provided lenses focus on industries or technologies such as serverless, SaaS, generative AI, analytics, or migration.
- Custom lenses allow organizations to bring internal requirements, policies, or custom technical criteria into reviews.

A workload can apply multiple lenses to examine different dimensions. Choose lenses based on the workload type and risks to evaluate; avoid adding irrelevant lenses just to increase the question count.

### 12.2. Profiles and Review Templates

Profiles allow defining business goals and prioritizing questions/risks aligned with the workload's objectives. For example, a payment workload may prioritize security, reliability, and compliance; an internal analytics workload may focus on cost, performance, and data governance.

Review templates help standardize answers and reduce repetitive work when multiple workloads share the same characteristics or platform standards.

### 12.3. Improvement Plans and Milestones

After a review, the WA Tool aggregates risks and recommends improvement items by lens. The team can:

1. Open the improvement plan.
2. View questions and best practices with risks.
3. Select actions to implement.
4. Assign owners and add items to the backlog.
5. Update answers/notes after making improvements.
6. Save a new milestone to measure progress.

A milestone records the review state at the time it is saved and supports comparisons across evaluations. A workload report can share status, answers, risks, and improvement recommendations with stakeholders.

### 12.4. Integrations and New Capabilities

The WA Tool can integrate with services such as AWS Trusted Advisor and AWS Service Catalog AppRegistry to help gather workload information. The tool also provides APIs and sharing features to embed reviews into governance workflows.

AWS Well-Architected Agent is a separate AI capability currently in public preview that helps analyze environments and recommend improvements; it does not replace the AWS WA Tool or human owner decisions. The November 16, 2026 Agent update added organizational profiles, AWS Organizations integration, profile/recommendation sharing, and basic profile onboarding. Access to the Agent depends on support plan and AWS-published eligibility terms.

## 13. Practical Scenario: Designing an E-Commerce Website

An enterprise wants to build an e-commerce website on AWS. The system includes a website, catalog, login, shopping cart, order service, payment integration, and inventory management. Traffic surges heavily during promotional campaigns. Order data must be protected, and the service must recover from infrastructure failures.

### 13.1. Reference Architecture

~~~mermaid
flowchart TB
    U["Shopper"] --> CF["Amazon CloudFront"]
    CF --> WAF["AWS WAF"]
    WAF --> ALB["Application Load Balancer"]
    ALB --> APP["ECS services across multiple AZs"]
    APP --> CACHE["ElastiCache"]
    APP --> DB["Aurora / RDS Multi-AZ"]
    APP --> Q["Amazon SQS"]
    Q --> WORKER["Order / Inventory workers"]
    WORKER --> DB
    APP --> S3["Amazon S3"]
    APP --> ID["Amazon Cognito / IAM integration"]
    APP --> PAY["Payment provider"]
    APP --> OBS["CloudWatch / X-Ray"]
    DB --> BACKUP["AWS Backup / snapshots"]
~~~

This is a conceptual diagram. Choices for database, identity, payment integration, queues, and AZ deployment must be validated against data requirements, workload profile, Region availability, and business constraints.

### 13.2. Evaluation Across the Six Pillars

| Pillar | Design Decision | Verification Method |
|---|---|---|
| Operational Excellence | Use IaC, CI/CD, CloudWatch dashboards, tracing, and runbooks. | Check deployments, alert response, change failure rate, and MTTR. |
| Security | Use IAM roles, KMS encryption, WAF, TLS, secret management, and audit logging. | Check permissions, policies, security findings, and traceability. |
| Reliability | Run services/database across multiple AZs, use SQS to decouple order processing, retries, and backups. | Test single-AZ loss, queue backlog, database restore, and failover. |
| Performance Efficiency | Use CloudFront, caching, autoscaling, and database/indexes aligned with access patterns. | Load test, track p95/p99 latency, throughput, and cache hit ratio. |
| Cost Optimization | Right-size compute, autoscale, use S3 lifecycle, and measure cost per order. | Review Cost Explorer, budgets, utilization, and data transfer. |
| Sustainability | Shut down unused environments, scale to demand, reduce redundant processing, and store data with proper lifecycle policies. | Measure resource consumption per order and idle capacity ratio. |

### 13.3. Analyzing a Trade-off

Suppose the business wants to keep processing orders even if one AZ experiences an outage. The team chooses to deploy services and the database Multi-AZ, while using SQS to decouple order intake from inventory processing.

Benefits:

- Requests can continue to be accepted when some workers fail.
- The queue buffers work while consumers recover.
- The database has availability mechanisms matching the chosen configuration.

Costs and limitations:

- Multi-AZ increases resource costs.
- Queues require handling duplicate delivery via idempotency.
- Failover can disrupt connections for a period of time.
- Backups must still be restore-tested; Multi-AZ does not replace backups.
- Consistency across orders, payments, and inventory must be designed at the application layer.

The team needs to define SLOs, RTO/RPO, retry rules, and transaction reconciliation criteria before deciding on the level of redundancy.

## 14. Common Misconceptions

1. **The Framework is an AWS service checklist.** The Framework evaluates decisions and best practices; it does not require every workload to use the same set of services.
2. **A review is an audit or compliance certification.** A review is a conversation to identify risks and improve the architecture.
3. **You only need to check the six pillars during initial design.** Workloads change with business needs, traffic, dependencies, and AWS services; reviews must happen periodically and on key events.
4. **Multi-AZ means zero downtime.** Failover, application dependencies, deployments, and logic bugs can still cause disruptions.
5. **Multi-Region is always better than Multi-AZ.** Multi-Region increases complexity and cost; it should be driven by RTO/RPO, latency, and business continuity.
6. **Security is just IAM and encryption.** Security also includes governance, detection, infrastructure/application protection, and incident response.
7. **Having CloudWatch means observability is good.** You need KPIs/SLOs, telemetry with sufficient context, dashboards, and actionable alerts.
8. **Cost Optimization means picking the cheapest service.** You must balance price with business value, reliability, security, and performance.
9. **Sustainability is only about choosing a Region.** You must optimize software, architecture, data, hardware, demand alignment, and processes.
10. **One review is enough.** Best practices, workloads, and AWS services evolve; milestones and follow-up reviews are necessary.

## 15. Self-Check Questions

**1. What problem does the AWS Well-Architected Framework solve?**

The Framework provides questions and best practices to evaluate architectural decisions, identify risks, and plan workload improvements.

**2. What are the six pillars of the Framework?**

Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability.

**3. How does Cloud Foundations differ from Cloud Workloads?**

Cloud Foundations establishes capabilities and guardrails at the organization/account level; Cloud Workloads evaluates the design and operation of individual workloads.

**4. Why is a single technical metric insufficient to evaluate an architecture?**

Architecture quality depends on multiple goals and trade-offs. You must look at business outcomes, risks, dependencies, evidence, and cross-pillar impacts.

**5. What do RTO and RPO describe?**

RTO is the target time to restore service; RPO is the maximum acceptable data loss measured in time.

**6. Why does Multi-AZ not replace backups?**

Multi-AZ provides fault tolerance for infrastructure/AZ failures according to service mechanics, but does not fully protect against accidental deletion, logic errors, corruption, or the need to restore data to an earlier point in time.

**7. When should you use managed services?**

When the service meets requirements and reducing operational burden is worth more than the granular control the team gives up.

**8. How does cost per transaction help?**

This metric links cost to business output, helping evaluate whether costs genuinely decrease when optimizing resources or improving efficiency.

**9. What does the AWS Well-Architected Tool support?**

Documenting workloads, conducting reviews using lenses, identifying risks, creating improvement plans, saving milestones, and generating workload reports.

**10. When should a Well-Architected review be conducted?**

Before production, at major milestones, after significant architecture changes, after incidents, and when business requirements change.

**11. What is the purpose of a game day?**

Simulating incidents to test detection, response, recovery capabilities, and runbook quality under controlled conditions.

**12. Why should trade-offs be recorded with ADRs?**

ADRs capture context, options, rationale, impacts, and review conditions, helping teams understand past decisions and avoid repeating debates.

## 16. Production Architecture Review Checklist

- [ ] Workload boundary, business owner, users, and business outcomes are clear.
- [ ] Architecture diagram, data flows, dependencies, and trust boundaries exist.
- [ ] SLOs/KPIs, availability targets, latency, throughput, RTO, and RPO are defined.
- [ ] Cloud Foundations provides the required account, identity, observability, networking, and security guardrails.
- [ ] Operational Excellence has runbooks, deployment controls, dashboards, and an incident process.
- [ ] Security has least privilege, data classification, encryption, detection, and incident response.
- [ ] Reliability has fault isolation, scaling, backups, restore tests, and a DR strategy.
- [ ] Performance Efficiency has load tests, profiling, a capacity strategy, and appropriate resource selection.
- [ ] Cost Optimization has cost attribution, budgets, lifecycle policies, and a review schedule.
- [ ] Sustainability has resource efficiency criteria and tracks impact relative to workload output.
- [ ] Key trade-offs are documented with owners and review dates.
- [ ] Improvement items have priorities, deadlines, and verification criteria.
- [ ] Milestones exist to compare before/after improvement states.
- [ ] Architecture diagrams, ADRs, and runbooks are updated after changes.
- [ ] A regular review schedule and triggers exist for when business or technology changes.

## References

- [AWS Well-Architected Framework – Current Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/framework.html)
- [AWS Well-Architected Framework – Release notes](https://docs.aws.amazon.com/wellarchitected/latest/framework/release-notes.html)
- [AWS Well-Architected Cloud Foundations](https://docs.aws.amazon.com/wellarchitected/latest/framework/cloud-foundations.html)
- [AWS Well-Architected Cloud Workloads](https://docs.aws.amazon.com/wellarchitected/latest/framework/workloads.html)
- [The six pillars of the Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html)
- [General design principles](https://docs.aws.amazon.com/wellarchitected/latest/framework/general-design-principles.html)
- [Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/framework/operational-excellence.html)
- [Security](https://docs.aws.amazon.com/wellarchitected/latest/framework/security.html)
- [Reliability](https://docs.aws.amazon.com/wellarchitected/latest/framework/reliability.html)
- [Performance Efficiency](https://docs.aws.amazon.com/wellarchitected/latest/framework/performance-efficiency.html)
- [Cost Optimization](https://docs.aws.amazon.com/wellarchitected/latest/framework/cost-optimization.html)
- [Sustainability](https://docs.aws.amazon.com/wellarchitected/latest/framework/sustainability.html)
- [Shared responsibility](https://docs.aws.amazon.com/wellarchitected/latest/framework/shared-responsibility.html)
- [Understanding architectural trade-offs](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel-understanding-tradeoffs.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/tool.html)
- [Tutorial: Document a workload with AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/tutorial.html)
- [Using lenses in AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/lenses.html)
- [Profiles in AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/profiles.html)
- [Generate a workload report](https://docs.aws.amazon.com/wellarchitected/latest/userguide/workloads-report.html)
- [AWS Well-Architected Tool user guide release notes](https://docs.aws.amazon.com/wellarchitected/latest/userguide/release-notes.html)
- [AWS Well-Architected documentation homepage](https://docs.aws.amazon.com/wellarchitected/)
