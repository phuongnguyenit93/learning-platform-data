# Region Selection Criteria and Data Residency Requirements

In AWS, choosing a **Region** is an architectural decision with long-term impact on user experience, incident recovery capability, operating costs, and compliance with data regulations. A Region close to users may reduce latency, yet it might not provide all required services or meet an organization's data requirements. Therefore, Regions should be evaluated thoroughly before deploying infrastructure.

This lesson belongs to the **AWS Overview** chapter of the **CLOUD_PROVIDERS_AWS** module. It applies knowledge of Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless to help learners select, design, and deploy secure, observable applications with recovery plans and cost controls.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between Regions, Availability Zones (AZs), and edge locations; explain the scope of impact of each infrastructure layer.
2. Build a Region selection criteria set considering latency, services, availability, cost, operations, and sustainability.
3. Distinguish **data residency** (where data is stored or processed), **data localization** (requirements to store/process data within a specific territory), and **data sovereignty** (jurisdiction and legal control over data) from security requirements.
4. List easily overlooked data copies: backups, snapshots, logs, caches, analytics data, and disaster recovery (DR) replicas.
5. Propose a single-Region Multi-AZ or Multi-Region architecture based on RTO/RPO targets and permitted geographic scope.
6. Plan how to verify resource placement and implement guardrails preventing deployment in the wrong Region.

## 2. Understanding AWS Infrastructure Placement Properly

A **Region** is a geographic area where AWS provides resources and services, identified by codes such as **ap-southeast-1** (Singapore), **ap-northeast-1** (Tokyo), or **eu-central-1** (Frankfurt). Each Region typically has multiple **Availability Zones** separated in physical infrastructure. AZs are used to build fault tolerance against localized incidents within a Region.

**Edge locations** serve delivery or routing services close to users, such as Amazon CloudFront. An edge location is not equivalent to the Region housing your database or application servers. An application can keep its database in one Region while still caching content at many locations outside that Region if the content delivery configuration permits it.

| Concept | Primary scope | Architectural role | Key reminder |
|---|---|---|---|
| Region | Geographic area | Service deployment location, data scope, and Region-level recovery | Selecting a Region does not automatically control every data copy across every service |
| Availability Zone | Independent fault domain within a Region | Deploying applications and redundant data across multiple AZs | Multi-AZ protects against AZ-level failures, not Region-wide outages |
| Edge location | Point of presence near users | CDN, accelerated access, handling part of traffic at the edge | Cached content and some logs may be generated outside the origin Region |

For example, an e-commerce website can run Amazon ECS or EC2 across two AZs in one Region, place Amazon RDS in Multi-AZ mode, use Amazon S3 for product images, and use CloudFront for image delivery. Users can receive images from a nearby edge location, while shopping cart queries still reach the system in the primary Region.

~~~mermaid
flowchart TB
    U["Users"] --> EDGE["CloudFront / edge location"]
    EDGE --> ALB["Application Load Balancer\nPrimary Region"]
    subgraph R["Primary Region: deployment scope"]
        subgraph A["AZ A"]
            APP1["Application"]
        end
        subgraph B["AZ B"]
            APP2["Application"]
        end
        ALB --> APP1
        ALB --> APP2
        DB["Multi-AZ Database"]
        S3["S3 bucket in same Region"]
        APP1 --> DB
        APP2 --> DB
        APP1 --> S3
        APP2 --> S3
    end
    R -. "Replicate only when permitted and configured" .-> DR["Standby Region"]
~~~

This diagram illustrates the processing flow; storage locations for caches, logs, operational data, and actual behavior must be verified per AWS service.

## 3. Region Decision Criteria

Do not pick a Region based solely on distance on a map. Separate **mandatory requirements** (a Region must meet them to be shortlisted) from **optimization criteria** (used to compare eligible candidates).

| Criterion | Questions to answer | How to verify / metrics |
|---|---|---|
| **Data residency and compliance** | Which data must remain in which country/region? Can replicas, logs, or backups leave? | Data inventory, legal and contractual obligations, security assessments, per-service documentation |
| **Latency** | Where are users, partner systems, and supporting services located? | Measure actual response times, p95/p99, load tests from representative locations |
| **Services and features** | Does the Region offer the required services, versions, instance types, and AI/serverless/database features? | Regional service list, quotas, available resource types |
| **Availability and recovery** | Must it survive one AZ failure or an entire Region outage? What are RTO/RPO targets? | Multi-AZ design, DR architecture, restore and traffic-failover tests |
| **Total cost** | How do compute, storage, data transfer, backup, and operational costs compare? | AWS Pricing Calculator, Region-specific pricing, load forecasts, egress and cross-AZ/cross-Region transfer |
| **Connectivity and integration** | Are there links to offices, on-premises systems, SaaS, partners, or other Regions? | Network testing, VPC plan, VPN/Direct Connect, link and bandwidth checks |
| **Operational and security readiness** | Can the team monitor, handle on-call incidents, manage access, and handle encryption in that Region? | Runbooks, IAM, KMS, CloudWatch, CloudTrail, AWS Config, and drill results |
| **Other organizational requirements** | Are there sustainability, contracting, procurement, or support requirements? | Internal policies, official documentation, and organization-approved criteria |

### 3.1. Latency Must Be Measured, Not Inferred from Geography

Physical distance is only an initial signal. Real latency also depends on ISP network routing, DNS, the number of API hops, database query latency, and external systems outside AWS.

- Gather user and partner locations; separate real-time interactive requests from background jobs.
- Test from multiple networks and times of day; use **p95/p99** and end-to-end response times rather than average ping alone.
- Measure application → database, application → partner paths, and content loading from CloudFront if using a CDN.
- Define acceptable experience thresholds—such as p95 for critical APIs based on business needs—and re-test after caching and architectural optimizations.

### 3.2. Availability: Multi-AZ and Multi-Region Solve Different Risks

**Multi-AZ** is suited to reducing the impact of a failure in one AZ: stateless components deployed across multiple AZs, data tiers using service-supported HA mechanisms, paired with backups and drills. **Multi-Region** can mitigate Region-level risk, but requires data synchronization, routing, failover testing, key management, and a larger budget.

Two DR metrics to define upfront:

- **RTO (Recovery Time Objective):** the target maximum time to restore service after an incident.
- **RPO (Recovery Point Objective):** the maximum acceptable data loss, measured in time between the last recoverable record and the time of the incident.

Simply creating a copy in another Region does not automatically produce a working DR system. You must verify replication lag, consistency, access permissions, DNS/routing, standby infrastructure, and run recovery drills.

### 3.3. Evaluating Full-Lifecycle Cost

Do not compare only hourly EC2 or database rates. Total cost typically includes:

**Compute + database + storage + requests + data transfer + backup/replication + observability + operations/DR.**

Rates, billing units, and availability vary by Region, service, and time. In particular, outbound Internet traffic, cross-AZ traffic, and cross-Region traffic can incur charges depending on the path, service, and configuration. Use the AWS Pricing Calculator with realistic traffic forecasts; compare across candidates under the exact same load scenario and availability requirements.

## 4. Data Residency Requirements: Pinpointing What Must Stay Where

**Data residency** answers *in which geographic location data is stored or processed*. **Data localization** is a stricter requirement that may mandate a category of data be stored or processed within a specific territory. **Data sovereignty** relates to legal jurisdiction and statutory control over data. These concepts are related, not interchangeable.

For example, a company aiming to improve latency for customers in Vietnam might evaluate several candidate Regions. However, if an applicable contract or regulation requires a certain class of data to be stored within Vietnamese territory, you cannot assume a Region in a neighboring country is compliant. Check specific obligations against service locations, deployment methods, and input from legal/compliance teams.

**Encryption, IAM, and Region selection are distinct controls.** Encryption protects confidentiality; it does not turn data stored outside a territory into data stored inside that territory. Access permissions restrict who can act on data; they do not by themselves guarantee the physical location of every data replica.

### 4.1. Classifying Data and Data Flows

Before selecting a Region, build an inventory:

| Data category | Examples | Placement verification questions |
|---|---|---|
| Core business data | Customer profiles, orders, transactions, uploaded files | Which Region stores the primary copy? Does the service replicate elsewhere? |
| Operational data | Application logs, access logs, traces, metrics, security events | Which CloudWatch, S3, SIEM, or centralized account receives the logs? |
| Replicas and long-term retention | Backups, snapshots, S3 replication, data exported to analytics warehouses | Are there cross-Region replication policies, data exports, or external archives? |
| Transient and delivery data | Caches, CDNs, queues, temporary files, processing results | Can caching or delivery mechanisms place data outside permitted boundaries? |
| Metadata and control data | Identifiers, account configurations, service events, support details | Is the service Regional or global; what does service documentation say about metadata location? |
| Human-created copies | Downloaded CSVs, support extracts, test exports | Are there rules for laptop locations, analytics tools, sub-processors, and test environments? |

Classify by sensitivity level (e.g., public, internal, personal data, specially regulated data), data subjects, retention period, processing purpose, and permitted countries/territories. Then map data flows from ingestion through storage, processing, backup, monitoring, and deletion.

### 4.2. Common False Assumptions When Using AWS

1. **"Creating resources in Region A means all data always stays in Region A."** There is insufficient basis for that conclusion. Examine each service's behavior, especially global services, edge services, replication features, and support/operational channels.
2. **"RDS Multi-AZ replicates to another Region."** RDS Multi-AZ operates within the same Region; cross-Region DR architecture is a separate decision.
3. **"S3 automatically replicates to another Region for safety."** S3 cross-Region replication is a feature you must explicitly configure; do not assume a replica exists or does not exist from a bucket name. Check replication, copy jobs, and backups.
4. **"Using CloudFront keeps data only in the origin Region."** A CDN can cache content at edge locations; evaluate which content is cached and which locations are permitted for distribution.
5. **"Using AWS KMS satisfies data residency."** KMS keys and encrypted data have separate lifecycles and locations to control. KMS multi-Region keys must also be evaluated if enabled.
6. **"Blocking Regions is sufficient for compliance."** Region-based policies do not automatically control all global service calls or actions that move data across Regions.

### 4.3. Primary Data, Logs, Backups, and DR Must Share One Policy

A requirement like "customer information must only be stored in region X" must be translated into verifiable technical rules:

- Primary system: EC2/ECS/Lambda, databases, S3, EBS, EFS, and integration services are placed in permitted Regions; verify **actual service availability** for each service.
- Supporting data: define destinations for CloudTrail, CloudWatch Logs, VPC Flow Logs, load balancer access logs, query results, queues, and analytics stores.
- Backups: review AWS Backup, snapshots, S3 replication, database replicas, and export jobs; never configure destinations outside permitted boundaries.
- Delivery: classify which content may go to CloudFront or edge caches; review features, processing locations, contracts, and cache controls.
- Keys and security: choose appropriate Regions and AWS KMS policies; protect access with IAM and encryption in transit and at rest.
- Operations: control manual exports, test environments, support systems, analytics accounts, and sub-processors.

Decisions regarding jurisdiction and compliance must rely on applicable regulations, contracts, and the latest AWS service documentation; an architecture document does not replace legal review.

## 5. Deployment Options Under Geographic Constraints

| Option | When to consider | Advantages | Limitations and checks needed |
|---|---|---|---|
| **Single Region, Multi-AZ** | AZ-level HA is required; data is restricted to one Region/area | Lower complexity, typically shorter data paths | Does not eliminate Region-wide outage risk; requires tested backups and recovery |
| **Two Regions within permitted scope** | Region-level DR is needed and data replication between those Regions is permitted | Can recover if the primary Region goes down | Higher cost; must manage replicas, keys, synchronization, failover, and RTO/RPO |
| **One Region plus DR in another approved location** | Geographic constraints limit AWS Region options | Enables design aligned with specific residency rules | Must verify suitability of on-premises/hybrid models, service dependencies, and feasibility |

**Selection principle:** Permitted geographic scope is an exclusionary filter first. Only afterward do you optimize latency, reliability, and cost. If no AWS Region satisfies mandatory legal requirements, change the design or choose an approved platform/location; never relax compliance conditions merely to pick the closest Region.

## 6. Region Selection Workflow for Projects

### Step 1 — Finalize Mandatory Requirements

Identify data types, permitted storage and processing countries/regions, contractual obligations, security standards, required services, connectivity needs, RTO/RPO, and budget. Separate negotiable preferences from mandatory requirements.

**Output:** a "pass/fail" checklist; any Region violating a mandatory condition is eliminated from the candidate list.

### Step 2 — Build the Eligible Region Shortlist

For each candidate, check supported services, instance types, service quotas, and specifically needed features. Note: a service being present in a Region does not mean every feature, engine version, or resource type is available there.

**Output:** a shortlist of Regions that passed data placement and service capability checks.

### Step 3 — Benchmark and Estimate Costs

Deploy a minimal test flow or use representative benchmarks to measure p95/p99 from user locations and partner systems; estimate pricing for identical load, storage volume, bandwidth, backups, and DR.

**Output:** a comparison table with measured evidence, load assumptions, and collection dates.

### Step 4 — Score Candidates and Document the Decision

**Hypothetical example to illustrate the methodology**, assuming two Regions already confirmed compliant for the project's data types. Scores run from 1 (poor fit) to 5 (strong fit) and do not reflect actual AWS measurements or pricing:

| Factor | Weight | Singapore — ap-southeast-1 | Tokyo — ap-northeast-1 |
|---|---:|---:|---:|
| Latency from target user group | 35% | 5 | 3 |
| Total cost under assumed load | 20% | 4 | 5 |
| Required services and features | 15% | 5 | 5 |
| HA and DR capability by design | 20% | 4 | 4 |
| Fit with operational capability | 10% | 5 | 3 |
| **Weighted score** | **100%** | **4.60/5** | **3.90/5** |

The score is calculated as the sum of **weight × factor score**. In this example, Singapore is chosen for pilot design due to its higher score. **If the project requires data to stay within Vietnam's territory and neither candidate Region meets that rule, both must be eliminated at Step 1, regardless of score.**

### Step 5 — Implement Guardrails and Monitoring

Configure:

- **IaC settings:** declare the Region explicitly in Terraform, AWS CloudFormation, or pipelines; lint/check code prior to deployment.
- **Account governance:** use AWS Organizations/SCPs to restrict actions in unapproved Regions, while designing exceptions for global services and verifying cross-Region operations.
- **Continuous inventory:** use AWS Config, CloudTrail, AWS Resource Explorer, or appropriate asset tools to detect resources, config changes, and activity in unapproved Regions.
- **Destination controls:** review S3 bucket policies, backup/log destinations, cross-Region replication permissions, and export pipelines.
- **Cost limits:** tag resources, configure AWS Budgets and cost alerts, and forecast cross-AZ/cross-Region data transfer.
- **Operational testing:** run failover, restore, access control, traceability, latency, and post-change data flow tests.

With AWS Organizations, the **aws:RequestedRegion** condition key is useful for restricting the Regional endpoint of many API calls, yet it does not guarantee an action cannot affect data in another Region. For instance, configuring replication can cause data to move outside the Region. Therefore, combine SCPs with service-specific behavior checks, resource policies, and monitoring.

### Step 6 — Periodic Review

Whenever adding new services, data sources, CDN capabilities, replication features, or new customer markets, update data-flow diagrams and Region decisions. Re-verify details when AWS updates its regional service catalog, pricing, or feature availability.

## 7. Verification Examples Using AWS CLI

The commands below **support inventory checks** and do not by themselves constitute full compliance evidence. Run them with appropriate read permissions, the right account/profile, and an initialized AWS CLI setup.

~~~bash
# View Regions recognizable by the account and their opt-in status.
aws ec2 describe-regions --all-regions \
  --query 'Regions[].[RegionName,OptInStatus]' \
  --output table

# Check the Region of a specific S3 bucket.
aws s3api get-bucket-location \
  --bucket your-example-bucket

# Check RDS Multi-AZ configuration in the Region under evaluation.
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query 'DBInstances[].[DBInstanceIdentifier,AvailabilityZone,MultiAZ]' \
  --output table
~~~

**Interpreting results properly:**

- The Region listing command only returns Region/opt-in metadata; it does not prove every service is available or that the project is authorized to store data there.
- An S3 bucket's **LocationConstraint** has a special case: an empty/null value corresponds to **us-east-1** (US East – N. Virginia). Also inspect replication, backups, and export destinations.
- The RDS **MultiAZ** field indicates the DB instance's Multi-AZ option, not cross-Region DR status or verified restore success. For other database architectures, use their corresponding inventory APIs.
- For multi-Region accounts, iterate inventory checks across relevant Regions and aggregate results from every AWS account in governance scope.

## 8. Scenario Exercises

**Scenario A — E-Commerce Platform:** Customers primarily access from a group of Southeast Asian countries. The team uses APIs, a database, S3 for product images, CloudFront, and a daily analytics job. There is no statutory requirement to store data in a single country, but contracts restrict certain data flows outside approved countries.

**Question:** What should be checked before finalizing the Region and enabling CloudFront?

**Suggested approach:** Classify whether customer profiles and images contain sensitive data; confirm the list of approved countries/Regions; measure latency from users; verify service availability; inspect storage locations for logs, caches, analytics outputs, and backups; design Multi-AZ; forecast costs; document the decision and run operational checks. CloudFront must only be configured for approved data and distribution scopes.

**Scenario B — System with Territorially Restricted Data:** A records system has contractual clauses requiring primary records, snapshots, and logs containing sensitive data to reside inside country X. Region A offers the lowest latency but sits outside country X. Region B is closer from a legal standpoint but lacks a required database feature.

**Question:** Should you choose Region A for speed or Region B for location?

**Suggested approach:** Do not pick Region A if it violates a mandatory constraint. Region B is only a candidate if a technical solution satisfies all required features and data constraints; otherwise, find another approved architecture/service/location. Optimize performance and cost only after mandatory conditions are met.

## 9. Checklist Before Approving a Region

- [ ] Identified which data must be stored, processed, backed up, and deleted at which locations.
- [ ] Obtained legal/compliance sign-off on permitted Regions and data flows.
- [ ] Verified services, features, instance types, and quotas in each candidate Region.
- [ ] Measured or planned latency testing for users, APIs, databases, and partner systems.
- [ ] Selected a Multi-AZ architecture, defined RTO/RPO, and established restore drills.
- [ ] Verified storage locations for S3, databases, snapshots, backups, logs, caches, CDNs, and analytics outputs.
- [ ] Defined IAM/KMS protections, Region policies, and misconfiguration alerts.
- [ ] Estimated total costs, including data transfer, backups, and DR.
- [ ] Documented the Region decision, approvers, assumptions, and review schedule.

## 10. Takeaways

Region selection is a problem of **mandatory constraints first, optimization second**. Proper evaluation balances user experience with security, observability, recovery, and cost. A Region determines where most Regional resources live, but data residency requirements can only be confirmed after examining the **entire data lifecycle**, including caches, logs, backups, replication, management metadata, and global services.

### AWS Sources to Cross-Check During Implementation

- [AWS Global Infrastructure](https://aws.amazon.com/about-aws/global-infrastructure/) — map of Regions, AZs, and global infrastructure.
- [AWS Services by Region](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/) — services supported by Region.
- [AWS Data Privacy](https://aws.amazon.com/compliance/data-privacy/) — AWS documentation on data protection and customer choices.
- [AWS IAM: aws:RequestedRegion](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion) — semantics and limitations of the Region condition key in policies.
- [AWS Pricing Calculator](https://calculator.aws/) — create cost estimates before deployment.
