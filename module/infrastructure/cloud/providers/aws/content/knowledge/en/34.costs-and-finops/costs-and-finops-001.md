# Pricing Models and Common Cost Sources

AWS offers many services under a pay-as-you-go model. This pricing approach enables engineering teams to start small and scale resources as demand changes, but bills can become unpredictable without understanding the billing units of each service. An EC2 instance typically incurs charges based on running time and configuration type; Amazon S3 charges for storage capacity, requests, and certain data operations; NAT Gateway charges for provisioned hours and the amount of data processed; CloudWatch can incur costs from log ingestion, storage, metrics, and queries.

Therefore, estimating AWS costs is not simply multiplying the number of servers by a unit price. You need to understand how much compute, storage, requests, network traffic, logs, backups, and management operations a workload generates. You must distinguish time-based fixed costs from usage-based variable costs, while identifying the account, Region, environment, and team responsible for each charge.

In the CLOUD_PROVIDERS_AWS ecosystem, architects must select appropriate services, operate securely with observability and recovery capabilities, and control costs. This lesson covers common pricing models, typical cost sources, and how to build a FinOps process that turns billing data into engineering and business decisions.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the pay-as-you-go model and the factors that affect AWS pricing.
- Differentiate between On-Demand, Savings Plans, Reserved Instances, Spot, and tenancy options.
- Identify cost sources across compute, storage, networking, databases, serverless, observability, security, and backup.
- Estimate costs based on billing units, usage volume, and operating duration.
- Break down costs by account, Region, service, usage type, and cost allocation tag.
- Use AWS Pricing Calculator, Cost Explorer, AWS Budgets, Cost and Usage Reports/Data Exports, and Cost Anomaly Detection.
- Propose cost optimization approaches while still meeting performance, security, availability, and RPO/RTO requirements.
- Establish a FinOps loop consisting of observing, allocating, optimizing, and continuously operating.

## 2. Foundations of the AWS Pricing Model

### 2.1. Pay-as-you-go

Pay-as-you-go is a model where you pay for the actual amount of resources or activity consumed. Instead of purchasing a data center with fixed capacity upfront, organizations can provision resources on demand and pay according to how each service meters usage.

Benefits:

- Reduces upfront capital expenditure on hardware.
- Scales capacity up or down with load.
- Enables experimenting with new services without purchasing equipment.
- Allows allocating costs by workload, account, or environment.

This model does not mean every resource automatically stops billing when idle. An EC2 instance continues to incur charges while running even if the application receives no requests; an EBS volume continues to incur storage charges when the instance is stopped; a NAT Gateway and load balancer can still charge based on how long they exist. Organizations must define resource lifecycles and automatically clean up what is no longer needed.

### 2.2. Billing Units

Each service meters usage using its own units. A bill may include:

| Unit Group | Examples | Questions to Answer |
|---|---|---|
| Time | Instance-hour, vCPU-hour, GB-month | How long did the resource exist or run? |
| Capacity | GB-month, TB-month | How much data was stored and for how long? |
| Requests | API request, read/write request | How many operations were invoked? |
| Data Processed | GB processed, GB scanned | How much data did the service process or query? |
| Data Transferred | GB transferred | How did data move across AZs, Regions, the Internet, or edge? |
| Provisioned Capacity | Provisioned IOPS, throughput, capacity unit | What performance level did the organization reserve in advance? |
| Managed Objects/Units | Secret-month, metric, rule, resource item | How many objects are being managed? |

A single service can combine multiple units. For example, a database may charge for compute by time, storage by GB-month, I/O by configuration or usage, backups by capacity, and data transfer by traffic flow.

### 2.3. Basic Estimation Formula

A general model:

\[
\text{Cost} \approx \sum_i (\text{Usage}_i \times \text{Unit Price}_i) + \text{Fixed Fees} - \text{Discounts}
\]

In practice, you also need to add factors such as data transfer, requests, licenses, taxes, and billing adjustments. Unit prices depend on the Region, service type, configuration, operating system, tenancy, purchase option, usage tier, and effective date.

For example, an application running on EC2 may incur:

1. Compute for the instance per hour or per second depending on the operating system and the service's billing rules.
2. EBS volumes and snapshots.
3. Elastic IPs or public IPv4 addresses under current pricing policies.
4. Data transfer out to the Internet or across AZs/Regions.
5. Load balancers and NAT Gateways.
6. CloudWatch Logs, metrics, alarms, and tracing.
7. Backups and related security services.

Consequently, looking only at the EC2 line item in Billing will not reflect the total cost of running the application.

### 2.4. Factors That Change Unit Pricing

When comparing two configurations, check:

- **Region:** compute, storage, network, and managed service prices can differ across Regions.
- **Availability Zone:** certain inter-AZ data flows incur data transfer fees.
- **Resource type:** CPU, memory, storage type, throughput, IOPS, network performance, and size.
- **Operating system and license:** Windows, SQL Server, or bundled licensed software can change pricing.
- **Tenancy:** shared tenancy, Dedicated Instances, or Dedicated Hosts have different pricing models.
- **Purchase option:** On-Demand, Spot, Savings Plans, or Reserved Instances.
- **Usage level:** tiers, free allowances, or volume discounts can affect the effective unit price.
- **Term and commitment:** some discounts require a term or spend commitment.

Do not compare the price of two services based solely on the first unit price you see. Compare total cost for the same workload, the same performance requirements, and the same operating duration.

## 3. Compute Purchase and Commitment Models

### 3.1. On-Demand

On-Demand lets you use compute without long-term commitments. Organizations pay based on resource usage.

Best suited when:

- Workloads are new and lack reliable load history.
- Development, testing, or demo environments do not run continuously.
- Demand fluctuates sharply and is hard to forecast.
- Flexibility is needed to change instance families or Regions.

The advantage is ease of starting with no commitment lock-in. The drawback is that the unit cost is typically higher than committed options for steady, long-running workloads.

### 3.2. Savings Plans

Savings Plans are a compute spend commitment measured in USD per hour over a typical one- or three-year term. In return, eligible usage is billed at discounted rates. If eligible usage falls below the commitment, the organization still pays the committed amount per the plan's terms.

Main categories:

- **Compute Savings Plans:** more flexible across eligible compute types, applicable to EC2, AWS Fargate, and AWS Lambda according to program rules.
- **EC2 Instance Savings Plans:** discount rates tied to an instance family within a single Region, in exchange for lower flexibility.

Savings Plans fit predictable baseline compute. Before purchasing, analyze usage history, minimum load levels, architectural change plans, and commitment duration. Do not commit to peak capacity if that load only occurs for short periods.

### 3.3. Reserved Instances

Reserved Instances (RI) are a commitment-based pricing option for supported services and resource types. RIs are commonly used with EC2, RDS, and several other services. Depending on the RI type, Standard or Convertible options, different terms, and different payment options may be available.

For EC2:

- Regional RIs generally provide a pricing discount for matching usage within a Region without automatically reserving capacity.
- Zonal RIs can provide a capacity reservation in a selected Availability Zone and apply discounts according to eligibility conditions.
- Convertible RIs allow exchanging certain attributes according to program rules.

Do not confuse an RI discount with guaranteed server availability. If you need capacity assurance, check reservation attributes and your dedicated capacity strategy.

### 3.4. Spot Instances

Spot allows you to use spare AWS EC2 capacity at variable prices that are often significantly lower than On-Demand. AWS can reclaim Spot capacity when needed. Workloads must tolerate interruptions and be able to restart or continue on other resources.

Best suited for:

- Batch processing.
- CI/CD workers.
- Rendering or distributed data processing.
- Checkpointed and retryable tasks.
- Fleets that can combine Spot with On-Demand to maintain a baseline.

Do not use Spot alone for stateful workloads that cannot recover or require continuous availability without a fallback design. You can use EC2 Auto Scaling or ECS capacity providers to combine multiple capacity types.

### 3.5. Dedicated Instances and Dedicated Hosts

Dedicated Instances run on hardware dedicated to a single customer at the instance level under the supported model. Dedicated Hosts provide dedicated physical servers and give greater control over instance placement, sockets/cores, and certain licensing requirements.

These options are suitable when hardware isolation, socket/core-based licensing, or specific compliance rules apply. Costs are typically higher than shared tenancy; verify legal and licensing requirements before choosing them.

### 3.6. Quick Comparison

| Model | Commitment | Flexibility | Best Use Cases |
|---|---|---|---|
| On-Demand | None | High | New, spiky, or short-lived workloads |
| Savings Plans | Hourly spend commitment | Depends on plan type | Steady compute baseline |
| Reserved Instances | Commitment by supported service/configuration | Depends on RI type | Steady, predictable workloads |
| Spot | No continuous capacity guarantee | Can be reclaimed | Batch, interruption-tolerant workers |
| Dedicated | Dedicated resource model | Depends on option chosen | Licensing or isolation requirements |

An architecture often combines multiple models: baseline on Savings Plans or RIs, burst load on On-Demand, and interruption-tolerant batch jobs on Spot.

## 4. Compute Cost Sources

### 4.1. Amazon EC2

EC2 costs depend on instance type, Region, operating system, tenancy, purchase option, and running time. A larger instance may increase the hourly rate, but it can also finish work faster and reduce total runtime hours.

When estimating:

1. Determine the number of instances per environment and Availability Zone.
2. Select the appropriate family, size, CPU, memory, and networking.
3. Identify the operating system and licensing.
4. Estimate monthly running hours, including buffer and maintenance windows.
5. Choose On-Demand, Savings Plans, RIs, or Spot based on load stability.
6. Add EBS, snapshots, networking, load balancers, NAT, and monitoring.

Stopping an instance generally stops the instance's compute billing under EC2 rules, but EBS volumes, snapshots, Elastic IPs, or related resources may still incur charges. Terminating an instance also does not automatically delete every volume or snapshot; check delete-on-termination settings and retention policies.

### 4.2. Auto Scaling and Schedules

Auto Scaling adjusts the number of instances based on metrics or schedules. This mechanism can reduce costs during low-load periods, provided minimum, desired, and maximum capacities are set appropriately.

Examples:

- Production APIs keep at least two instances to maintain service availability.
- Batch workers scale out based on queue depth.
- Development environments automatically stop outside business hours.
- Scheduled jobs provision capacity only during the processing window.

Do not reduce capacity below what availability requires. A system running fewer instances that frequently overloads, times out, or requires manual intervention can result in higher total costs.

### 4.3. AWS Fargate

Fargate charges based on the compute resources allocated to a task or pod and the duration of usage, along with other service-specific components. For ECS on Fargate, estimate vCPU, memory, and task runtime. For EKS on Fargate, calculate pod configuration and runtime under the supported model.

Over-provisioning CPU and memory increases costs even when the application does not utilize them. Under-provisioning can cause throttling, OOM errors, or prolonged processing times. Use CPU, memory, task duration, and throughput metrics to rightsize.

### 4.4. Amazon ECS and Amazon EKS

The ECS control plane is not billed in the way an EC2 instance is billed, though the underlying resources running tasks still incur costs. ECS on EC2 incurs instance, EBS, and network costs; ECS on Fargate incurs costs based on task configuration and duration.

EKS has a time-based cluster management fee plus compute charges for EC2 or Fargate nodes, along with storage, load balancer, network, and add-on costs. For small clusters, the cluster management fee can represent a significant share. When running many separate clusters, factor in the cluster fee alongside node and operational tooling costs.

### 4.5. AWS Lambda

Lambda typically has the following billing components:

- Number of invocations.
- Execution duration and allocated memory.
- Provisioned Concurrency if enabled.
- Ephemeral storage beyond the included amount or separately billed features.
- Data transfer and downstream services invoked by Lambda.

Execution duration increases when code runs slowly, makes repeated dependency calls, or has poorly tuned memory settings. Increasing memory may raise the cost per unit of time while reducing runtime; benchmark to compare total cost per request or per completed task.

### 4.6. Compute Calculation Example

Suppose a worker runs continuously for 30 days on a fixed configuration. The theoretical hours in a 30-day month are:

\[
30 \times 24 = 720\ \text{hours}
\]

If you run two workers of the same configuration, total compute usage is 1,440 instance-hours before applying discounts, actual runtime variations, and associated resources.

This is only the compute portion. You must add volumes, snapshots, data transfer, load balancing, logs, and backups to obtain total operating cost.

## 5. Storage Cost Sources

### 5.1. Amazon EBS

EBS generally incurs charges based on the provisioned capacity of a volume for as long as the volume exists. Some volume types also charge separately for provisioned IOPS or throughput beyond the included baseline.

Factors:

- Volume type such as gp3, io2, or another suitable type.
- Provisioned capacity, not just actual written data.
- IOPS and throughput.
- Snapshots and snapshot copies.
- Data transfer or related operations where applicable.

gp3 lets you configure capacity, IOPS, and throughput independently within the volume type's limits. For workloads that do not need high performance, over-provisioning IOPS/throughput causes waste. For critical databases, under-provisioning can increase latency and prolong processing times.

### 5.2. EBS Snapshots

EBS snapshots store data incrementally after the initial snapshot. Cost depends on the stored snapshot capacity and the storage features/tiers used. Deleting a snapshot does not necessarily release all blocks if those blocks are still referenced by another snapshot.

Best practices:

- Set snapshot schedules aligned with RPO.
- Use lifecycle policies to delete expired snapshots.
- Audit orphaned snapshots and snapshots belonging to deleted volumes.
- Distinguish source snapshots, cross-Region copies, and archived snapshots.
- Test restore capabilities and volume initialization time.

### 5.3. Amazon S3

S3 costs may include:

- Stored capacity by storage class and duration.
- PUT, GET, LIST, and other requests.
- Data retrieval and retrieval requests in certain classes.
- Outbound or cross-Region data transfer.
- Replication, inventory, analytics, and additional management features.

Common storage classes:

| Storage Class | Usage Characteristics | Cost Considerations |
|---|---|---|
| S3 Standard | Frequently accessed data | Storage and requests |
| S3 Intelligent-Tiering | Data with unpredictable access patterns | Monitoring/automation fees; retrieval across tiers has specific conditions |
| S3 Standard-IA | Infrequently accessed data needing fast retrieval | Lower storage fee, with retrieval fees and minimum storage duration |
| S3 One Zone-IA | Infrequently accessed data acceptable in a single AZ | Cost and availability risk differ from Standard-IA |
| S3 Glacier Instant Retrieval | Archive data requiring fast retrieval | Storage, request, and retrieval fees; minimum storage duration applies |
| S3 Glacier Flexible Retrieval | Archive where restore time is acceptable | Cost depends on retrieval method and capacity |
| S3 Glacier Deep Archive | Very long-term retention, rarely accessed | Lowest storage rate, but restore time and fees must be factored in |

Choose a storage class based on access frequency, acceptable latency, retention duration, and retrieval costs. Moving data to a cheaper class may not save money if it is frequently retrieved or deleted before the minimum duration.

### 5.4. Lifecycle and Intelligent-Tiering

S3 Lifecycle can transition objects to other storage classes or expire objects based on rules. Check:

- Whether prefixes or tags target the intended scope.
- Whether object versioning retains older versions.
- Whether delete markers and noncurrent versions are handled.
- Whether incomplete multipart uploads are cleaned up.
- Whether minimum storage class durations affect charges.

Intelligent-Tiering automatically moves objects between access tiers based on access patterns, but charges a monitoring/automation fee for eligible objects. Compare this fee against manual lifecycle rules when access patterns are well understood.

### 5.5. Storage Estimation Example

Suppose a bucket holds an average of 2 TB of data during the month. Base storage cost can be estimated as:

\[
\text{Billable Capacity} \times \text{GB-month Unit Price of Storage Class}
\]

However, you must add requests, retrievals, replication, versioning, and data transfer. If data is downloaded repeatedly, request and retrieval charges can be substantial relative to storage fees.

## 6. Networking and Data Transfer Cost Sources

### 6.1. Data Transfer

Network costs are frequently overlooked because they do not appear under a single workload name. Flows to examine:

- Data transfer out to the Internet.
- Data transfer between Availability Zones.
- Data transfer between Regions.
- Traffic through NAT Gateways.
- Traffic through load balancers.
- Traffic through VPC endpoints or edge services.
- Cross-account or cross-Region replication.

An application may have minimal compute while transferring large volumes of data—for example, media processing, analytics, or file-serving APIs. In such cases, data transfer can become one of the largest cost items.

### 6.2. NAT Gateway

NAT Gateways typically charge per provisioned hour and per GB of data processed. If many private subnets send Internet traffic through a NAT Gateway, total data volume can drive costs up rapidly.

Ways to control this:

- Use VPC endpoints for supported AWS services to avoid routing internal traffic through NAT.
- Verify route tables to ensure traffic flows through the intended endpoint.
- Place NAT Gateways according to an appropriate AZ architecture to balance cost, availability, and cross-AZ charges.
- Monitor bytes processed and provisioned hours.
- Avoid creating NAT Gateways in test environments that do not need Internet access.

Do not remove NAT solely to cut costs if the workload still requires outbound connectivity. Evaluate security, patching, external APIs, and operational requirements.

### 6.3. VPC Endpoints

Gateway endpoints for services like S3 and DynamoDB have a different cost model than interface endpoints. Interface endpoints typically charge per provisioned endpoint-hour and per GB of data processed. Compare total endpoint fees against NAT Gateway charges and actual traffic volume.

VPC endpoints can reduce traffic over the Internet/NAT and improve network control, but not all endpoints are free. The number of AZs, number of endpoints, hours, and data volume all affect total cost.

### 6.4. Load Balancers

Application Load Balancers and Network Load Balancers can charge by operating hours and corresponding capacity/processed traffic units. For ALB, examine Load Balancer Capacity Units (LCUs) and dimensions such as new connections, active connections, bytes processed, and rule evaluations as metered by the service.

An idle load balancer that remains provisioned continues to incur hourly charges. Audit unused load balancers, target groups, listeners, and decommissioned environments.

### 6.5. CloudFront and Edge Delivery

CloudFront incurs charges related to data transfer, requests, and additional features by region/plan. Using a CDN can reduce origin load and improve latency, but compare:

- Amount of data distributed by edge location.
- Request count and request types.
- Cache hit ratio.
- Origin fetches and data transfer from the origin.
- Invalidations or additional features if billed.

Optimizing cache policies, TTLs, compression, and object sizes can reduce origin requests and total data transferred. Do not assume a CDN is always cheaper than direct delivery; model it based on actual traffic.

## 7. Database and Cache Cost Sources

### 7.1. Amazon RDS and Aurora

RDS/Aurora can incur costs from:

- DB instances or serverless capacity.
- Storage and IOPS.
- Multi-AZ deployments or read replicas.
- Backups and snapshots beyond included retention/allowance.
- Data transfer.
- Proxies, monitoring, or optional features if enabled.

Multi-AZ increases availability and can increase compute/storage costs compared to single-AZ deployments. This is an architectural choice driven by reliability requirements and should not be disabled solely to lower the bill if the workload requires fault tolerance.

Read replicas can add cost while offloading read traffic from the writer. Before adding a replica, inspect query patterns, caching, indexing, and existing scaling headroom.

### 7.2. Aurora Serverless

Aurora Serverless bills based on provisioned or consumed capacity under the corresponding serverless model, along with storage, I/O, and other components. Minimum and maximum capacity settings affect baseline cost and burst responsiveness.

If minimum capacity is set too high, low-traffic workloads can still incur significant costs. If minimum capacity is too low or scaling lags behind traffic spikes, applications may experience latency. Measure usage across daily/weekly cycles and test peak hours.

### 7.3. Amazon DynamoDB

DynamoDB offers two capacity models:

- **On-Demand:** charges per read/write request unit consumed, suitable for unpredictable or newly launched workloads.
- **Provisioned:** allocates read/write capacity; can use auto scaling to adjust with load.

Beyond request capacity, account for storage, backups/PITR, global tables, streams, exports/imports, and additional features. Poor partition key design can create hot partitions and force higher capacity or degrade performance.

Choosing On-Demand does not mean all costs are purely request-based; storage, backups, replication, and data transfer still apply.

### 7.4. Caching

Amazon ElastiCache can charge by node or serverless capacity and usage duration, depending on the option chosen. Caching reduces database load and latency, but adds compute, memory, backup, and data transfer costs.

Measure cache hit ratio, memory utilization, evictions, and request patterns. An oversized cache or one with a low hit ratio may not be cost-effective. An undersized cache causes evictions and pushes load back onto the database.

## 8. Serverless and Integration Cost Sources

### 8.1. API Gateway

API Gateway can charge by request count, API type, data transfer, and related features. Estimates should be based on request counts, payload sizes, caching if used, and the number of stages/environments.

Unused test endpoints or old stages should be reviewed and removed. Verbose logging on every request can generate substantial CloudWatch Logs costs, especially with large payloads.

### 8.2. SQS, SNS, and EventBridge

Messaging/event services typically charge by requests, delivery/processing count, payload size, API type, or related features. Sending, receiving, visibility timeouts, retries, or redrives on a message can all increase request counts.

When designing:

- Avoid excessive polling on empty queues if the polling model generates high request volume.
- Use SQS long polling to reduce empty receives.
- Control retry loops and DLQ redrives.
- Limit message sizes and unnecessary fan-out.
- Monitor event counts, deliveries, errors, and consumer lag.

### 8.3. AWS Step Functions

Step Functions uses different pricing models depending on the workflow type. Standard workflows typically charge by state transition; Express workflows use a request and duration model. A workflow with many states, retries, or loops can generate far more transitions than expected.

Keep state machines concise, avoid tight polling loops, bound retries, and select the workflow type based on duration, execution history, and throughput requirements.

### 8.4. Lambda and Event-Driven Costs

An event-driven architecture can reduce continuously running compute, but event volume, invocations, retries, duration, and downstream requests can increase. Calculate the total cost of the entire chain:

Producer -> EventBridge/SNS/SQS -> Lambda -> Database/API -> Logs/Tracing

Do not compare Lambda fees solely against a single EC2 instance. Compare the cost to complete one unit of work, latency, scalability, and operational overhead.

## 9. Observability, Security, and Backup Are Also Cost Sources

### 9.1. Amazon CloudWatch

CloudWatch can charge for:

- Log ingestion and log storage.
- Custom metrics and metric resolution.
- Alarms.
- Dashboards or advanced observability features.
- Logs Insights queries and data scanned.
- Specific metric types, Contributor Insights, or add-on features.

Excessively verbose logs, overly long retention, or logging large payloads can produce high bills. Set retention based on purpose: short-term debugging, operations, security, and auditing. Do not reduce retention below investigation or compliance requirements.

### 9.2. Tracing and Auditing

AWS X-Ray and tracing solutions can incur charges based on traces or data collected/recorded. CloudTrail can incur costs for data events, CloudTrail Lake ingestion, and retention; AWS Config charges per configuration item or supported operation type.

Choose appropriate sampling rates to preserve diagnostic visibility without capturing every trace in full detail at high traffic volumes. For auditing, define which events must be recorded based on risk and compliance obligations.

### 9.3. Security Services

Services such as GuardDuty, Security Hub, Inspector, Macie, and KMS have their own pricing models based on data volume, resources, findings, requests, or features. Enabling multiple security services improves coverage, but their costs must be built into the design.

Do not disable security controls just to cut costs without a risk assessment. Instead, define scope, data sources, criticality, and appropriate configurations; monitor costs per account/Region to spot unexpected growth.

### 9.4. AWS Backup

AWS Backup can incur charges for storing recovery points, cross-Region/cross-account copies, restores, retrievals, or resource-specific protection features. Storing copies across multiple accounts improves resilience but adds storage volume.

To forecast:

- Estimate source data size and data change rate.
- Define copy count, Regions, and retention periods.
- Check storage tiers and lifecycle conditions.
- Estimate restore testing and temporary resources.
- Watch for recovery points retained longer than intended policy.

## 10. Pricing Tools and Pre-Deployment Estimation

### 10.1. AWS Pricing Calculator

AWS Pricing Calculator helps build estimates based on services, Regions, configurations, and projected usage. It can be used to:

1. List the services required for the workload.
2. Select the Region and configuration.
3. Enter runtime hours, storage capacity, requests, or data transfer.
4. Select appropriate purchase options.
5. Save the estimate and share it with stakeholders.

The Calculator is an estimation tool, not a billing guarantee. Results depend on inputs, assumptions, current unit prices, discounts, taxes, and unmodeled items. Document assumptions and update them as the workload evolves.

### 10.2. AWS Price List and Service Pricing Pages

Official service pricing pages are the authoritative source to verify billing units, tiers, Regions, and conditions. AWS Price List provides structured pricing data for internal systems to query or build estimation tools.

When reading pricing tables:

- Verify the exact Region.
- Read the usage type and operation carefully.
- Identify unit prices by tier and free/included allowances.
- Distinguish On-Demand unit rates from discounted rates.
- Check the effective date and currency.

Do not copy a price from an old article without verifying the current pricing page.

### 10.3. Workload-Based Modeling

A useful estimate must describe the workload, not just list services. Example for an e-commerce API:

| Component | Inputs to Estimate |
|---|---|
| Compute | Task/instance count, vCPU, memory, running hours, scaling levels |
| Database | Instance/capacity, storage, I/O, backups, replicas |
| Storage | GB-month, object count, requests, retrievals |
| Network | Egress, inter-AZ, NAT processed bytes, load balancers |
| API | Requests/month, payload size, caching, stages |
| Messaging | Message count, size, deliveries, retries |
| Observability | Log GB/day, retention, metrics, alarms, trace sampling |
| Security | Data events, findings, scan scope, KMS requests |
| Backup | Frequency, retention, copy count, restore tests |

The closer the inputs are to reality, the more useful the estimate. If actual figures are not yet available, create three scenarios—low, baseline, and high—and document the assumptions for each.

## 11. Reading Bills and Allocating Costs

### 11.1. Consolidated Billing

AWS Organizations can consolidate billing across member accounts via consolidated billing. This enables centralized cost visibility and can allow sharing certain pricing benefits across accounts under program rules.

Consolidated billing does not mean every team sees the same charges or that billing access is automatically granted to everyone. Design billing access, cost allocation, and reporting permissions by role.

### 11.2. Cost Analysis Perspectives

Costs can be analyzed by:

- Linked account or member account.
- Service.
- Region.
- Usage type.
- Operation.
- Purchase option.
- Tags and cost categories.
- Time, environment, or product group.

An EC2 line item can encompass many different usage types such as instance usage, EBS, data transfer, or licensing. Filtering by service name alone may not be enough to pinpoint the cause of a cost increase.

### 11.3. Cost Allocation Tags

Cost allocation tags are tags used to attribute costs by application, team, environment, or owner. Tags must be activated in Billing/Cost Management before they can be used in corresponding cost reports.

A reference tag set:

| Tag | Purpose | Example Values |
|---|---|---|
| Application | Application bearing the cost | commerce-api |
| Environment | Environment | production, staging, development |
| Team | Owning team | platform, payments |
| CostCenter | Cost center | CC-104 |
| Owner | Responsible person/team | team-payments |
| DataClass | Data classification | internal, confidential |

There is no need to attach every tag to every resource type if it adds no governance value. Standardize a tag dictionary, mandatory rules, and checks for untagged resources.

### 11.4. Cost Categories

Cost Categories help group costs using custom rules—for example, mapping multiple accounts or tags to a product, business unit, or cost center. This is useful when AWS account structure does not match the organizational chart.

Manage category rules with versioning, owners, and effective dates so prior months' reports can still be interpreted accurately when rules change.

### 11.5. Unblended, Blended, and Amortized Cost

AWS reports can present costs in several ways:

- **Unblended cost:** cost based on each account's/usage's rates and charges before blending.
- **Blended cost:** an averaged rate applied in certain consolidated billing contexts; not always suitable for internal cost allocation.
- **Amortized cost:** distributes upfront or commitment fees across the usage period to reflect economic cost within the period.

With Savings Plans or Reserved Instances, the unblended cash view and the amortized view can differ. When evaluating commitment effectiveness, examine payments, discounted usage, and amortized cost over time together.

## 12. Cost Management and Control Tools

### 12.1. AWS Cost Explorer

Cost Explorer helps analyze costs and usage over time by service, account, Region, tag, and supported dimensions. It can be used to:

- Compare month-over-month spend.
- Spot services or accounts with unusual increases.
- Analyze daily/monthly trends.
- View costs by purchase option.
- Evaluate Savings Plans/RI utilization and available optimization opportunities.

Filter the exact time range and cost metric before drawing conclusions. An increase may stem from workload growth, rate changes, expiring credits, billing adjustments, or allocation changes.

### 12.2. AWS Budgets

AWS Budgets lets you set budgets by cost, usage, Savings Plans, or Reserved Instances across supported budget types. You can configure alert thresholds and notify responsible stakeholders.

Examples:

- Monthly production budget.
- Budget per project or cost center.
- Alerts when actual or forecasted spend exceeds 80% or 100% of the budget.
- Tracking Savings Plans utilization and coverage.

A budget alert is a signal to investigate, not a root-cause explanation. It requires an owner and a response workflow.

### 12.3. Cost Anomaly Detection

AWS Cost Anomaly Detection identifies anomalies in spend and sends alerts via monitors/subscriptions. It can track all services, specific accounts, or configured scopes.

Anomaly detection is helpful for catching spikes early, but it does not replace budgets. Gradually rising spend may not trigger an anomaly alert yet still exceed the budget; conversely, a brief spike may warrant investigation even if the monthly total remains low.

### 12.4. Cost and Usage Reports and Data Exports

AWS Cost and Usage Report (CUR) and Data Exports capabilities provide granular cost and usage data for analysis in your own data systems. Organizations can store data in S3, query it with Athena, or ingest it into BI tools.

Granular data supports:

- Analyzing usage types and operations.
- Allocating costs by tags/cost categories.
- Reconciling invoices against application telemetry.
- Building dashboards and chargeback reports.
- Analyzing commitment costs and effective rates.

CUR/Data Exports can contain many columns and rows; design partitioning, retention, access controls, and the query/storage costs of the reporting system itself.

### 12.5. Optimization Support Tools

Additional tools include:

- **AWS Compute Optimizer:** recommends appropriate sizes or configurations based on utilization metrics for supported resources.
- **AWS Trusted Advisor:** provides checks for cost optimization, performance, security, and service quotas based on current support plan/permissions.
- **AWS Cost Optimization Hub:** aggregates optimization opportunities from supported sources.
- **S3 Storage Lens:** analyzes S3 usage patterns and data growth.
- **CloudWatch:** provides metrics and alarms to correlate spend with workload behavior.

Automated recommendations must be reviewed against workload and reliability requirements. Never apply instance size, retention, or network changes based solely on a single suggestion without checking the impact.

## 13. The FinOps Process

### 13.1. Inform, Optimize, and Operate

FinOps is a collaborative practice across engineering, finance, and business to maximize value from cloud spend.

A common iterative loop:

1. **Inform:** collect and allocate costs, clarify owners, build dashboards, and help teams understand usage.
2. **Optimize:** identify waste reduction opportunities, improve utilization, choose purchase models, and refine architecture.
3. **Operate:** set targets, budgets, review cadences, accountability, and continuously measure outcomes.

FinOps is not a one-time bill-cutting exercise. As a product grows, total spend may increase while cost per order or per customer decreases. Evaluate cost alongside business value.

### 13.2. Unit Economics

Unit economics ties cloud cost to a unit of output, for example:

- Cost per completed order.
- Cost per active user.
- Cost per GB of data processed.
- Cost per pipeline run.
- Cost per successful request.

Example:

\[
\text{Cost per order} = \frac{\text{Total system cloud cost in period}}{\text{Number of completed orders in period}}
\]

If total cost grows 15% while orders grow 40%, cost per order may decrease. Conversely, flat spend while traffic drops by half may indicate worsening utilization.

### 13.3. Showback and Chargeback

**Showback** provides reports so teams know how much cost they consume without necessarily transferring charges into their team budget.

**Chargeback** allocates costs directly into the responsible team's budget or financial statements.

Before implementing chargeback, agree on rules for shared costs such as NAT Gateways, transit gateways, logging accounts, security services, and shared databases. Allocation can follow measured usage, agreed ratios, or cost centers; document the methodology to avoid disputes.

### 13.4. Responsibilities and Review Cadence

A governance process may include:

- Engineering owners monitoring utilization and executing optimizations.
- Product owners understanding how cost changes affect user experience.
- Finance/FinOps analyzing bills, budgets, and commitments.
- Platform teams standardizing tags, accounts, dashboards, and guardrails.
- Security teams ensuring optimizations do not weaken controls.

Cost reviews should follow a regular cadence and also be triggered by major changes such as product launches, traffic surges, adding Regions, database changes, or purchasing long-term commitments.

## 14. Common Cost Optimization Approaches

### 14.1. Rightsizing

Rightsizing adjusts resource sizes to match actual load. Use CPU, memory, network, disk I/O, latency, and throughput over a representative time window. Check peaks, batch windows, and seasonal events before downsizing.

### 14.2. Scheduling Off-Hours Shutdowns

Development, test, and demo environments can run on a schedule. Use automation to stop/start instances or scale services down. Preserve required data resources and configurations; stopping EC2 does not remove EBS and other resource charges.

### 14.3. Storage Optimization

- Clean up unneeded snapshots, AMIs, volumes, and objects.
- Apply lifecycle policies aligned with data policies.
- Select storage classes based on access patterns.
- Reduce log retention when operational/audit requirements no longer apply.
- Avoid provisioning IOPS/throughput beyond actual demand.

### 14.4. Network Optimization

- Use caching/CDNs to reduce origin traffic where appropriate.
- Leverage VPC endpoints for supported AWS traffic.
- Inspect NAT Gateway and inter-AZ traffic.
- Co-locate workloads and data when architecture allows.
- Compress payloads and eliminate unnecessary responses.

### 14.5. Database and Application Optimization

- Optimize queries, indexes, and connection pooling.
- Use caching for repeated read data.
- Choose On-Demand or Provisioned capacity based on access patterns.
- Auto-scale on meaningful metrics.
- Reduce redundant requests and avoid aggressive polling.
- Optimize code to reduce Lambda duration and memory usage.

### 14.6. Choosing Purchase Options After Understanding the Baseline

First rightsize resources and eliminate waste. Only then evaluate Savings Plans or RIs on the steady load portion. Purchasing commitments before rightsizing can lock an organization into paying for ill-fitting configurations.

### 14.7. Never Trade Off Reliability Just to Cut Costs

Every optimization proposal should be evaluated against:

- Performance and latency.
- Availability and fault tolerance.
- RPO/RTO and restore capability.
- Security and compliance requirements.
- User experience.
- Operational cost and complexity.

For example, reducing AZ count, disabling Multi-AZ databases, or shortening retention can lower the bill while altering risk exposure. Document trade-offs and require owner sign-off.

## 15. Practical Walkthrough: Estimating an API Cost on AWS

### 15.1. Context

An e-commerce API includes these components:

- Application running on ECS Fargate.
- ALB receiving HTTP requests.
- RDS storing transactional data.
- S3 storing product images.
- SQS handling notification jobs.
- CloudWatch collecting logs and metrics.
- NAT Gateway handling part of the outbound traffic.

The team has no historical bill because this is a new system. Instead of guessing a lump sum, the team builds an input model:

| Component | Input Assumptions to Gather |
|---|---|
| API traffic | Requests/day, peak requests/second, average payload |
| ECS | Minimum tasks, scaling levels, vCPU/memory per task, running hours |
| ALB | Operating hours, new connections, concurrent connections, bytes processed |
| RDS | Instance/capacity, running hours, storage, backups, Multi-AZ |
| S3 | Stored GB, object count, PUT/GET, downloads, and lifecycle |
| SQS | Message count, message size, retries, and DLQ |
| CloudWatch | Log GB/day, retention, custom metrics, alarms |
| NAT | Gateway count, provisioned hours, GB processed |

### 15.2. Modeling Three Scenarios

The team builds three scenarios:

- **Low:** low average traffic, minimal peaks, slow data growth.
- **Baseline:** aligned with product forecasts and expected usage.
- **High:** marketing campaigns or peak seasons driving heavy traffic surges.

Each scenario uses the same architecture while varying the inputs. For ECS, estimate task counts over time; for RDS, verify peak headroom; for S3 and networking, calculate upload/download volumes; for logs, estimate from request volume and log size.

Next, enter the assumptions into AWS Pricing Calculator for the target Region and save the estimate. Document excluded items such as taxes, third-party licenses, support fees, or contractual discounts if the calculator does not model them completely.

### 15.3. Comparing Cost per Request

After a pilot deployment, take the cloud cost for the measurement period and divide by successful requests:

\[
\text{Cost per successful request} =
\frac{\text{Total cloud cost in period}}{\text{Successful requests in period}}
\]

If cost grows faster than traffic, inspect services with steep increases, failed requests, duplicate logs, cache hit ratio, NAT processed bytes, and database utilization. If cost drops while latency or error rate rises, review whether optimizations degraded service quality.

## 16. Common Mistakes When Reading and Managing Costs

| Mistake | Why It Misleads | How to Fix |
|---|---|---|
| Counting only EC2 | Omits EBS, networking, ALB, NAT, logs, and backups | Build a cost model across the entire workload flow |
| Assuming stopped instances cost nothing | Storage and dependent resources remain provisioned | Inventory EBS, IPs, snapshots, load balancers, and NAT |
| Using unit prices from another Region | Pricing and availability can differ | Select the exact Region in pricing tables and the calculator |
| Committing to peak capacity | Commitments may exceed actual usage | Analyze baseline load before purchasing |
| Using Spot for non-interruptible workloads | Can lose progress or cause service disruption | Add checkpoints, retries, capacity mix, and fallbacks |
| Moving all S3 data to Glacier | Retrieval fees and restore times may not fit | Classify access patterns and test retrievals |
| Not enabling cost allocation tags | Hard to identify the team or app owning costs | Standardize and activate tags in billing |
| Viewing only unblended costs | May not reflect amortized commitment costs per period | Compare cash view and amortized view |
| Cutting logs/backups without review | Loses investigation or recovery capability | Preserve security, compliance, and RPO/RTO requirements |
| Relying only on budget alerts | Does not explain root cause or ownership | Assign owners, dashboards, and response workflows |

## 17. AWS Cost Control Checklist

### Before Deployment

1. Identify workload, Region, environment, and business objectives.
2. List compute, storage, database, network, messaging, observability, security, and backup components.
3. Identify billing units for each service.
4. Estimate low/baseline/high scenarios and document assumptions.
5. Use AWS Pricing Calculator and verify official pricing pages.
6. Design tags, accounts, and cost categories for allocation.

### During Operations

1. Monitor Cost Explorer by account, service, Region, and tag.
2. Configure AWS Budgets and Cost Anomaly Detection.
3. Review utilization and rightsizing periodically.
4. Audit idle resources, old volumes/snapshots, and log retention.
5. Track data transfer, NAT Gateways, load balancers, and request volumes.
6. Check backups, restore tests, and cost-bearing security controls.
7. Reconcile unblended and amortized costs when commitments exist.

### When Optimizing

1. Identify cost increase drivers using usage types and granular data.
2. Measure impact on performance, availability, security, and RPO/RTO.
3. Prioritize waste elimination and rightsizing.
4. Purchase Savings Plans/RIs only after establishing a stable baseline.
5. Test changes at small scope and measure results.
6. Update estimates, budgets, owners, and runbooks.

## 18. Conclusion

AWS costs are shaped by multiple usage units: compute time, storage capacity, requests, data processed, data transfer, provisioned capacity, and management features. On-Demand provides flexibility; Savings Plans and Reserved Instances suit steady usage; Spot fits interruption-tolerant workloads. Services such as EC2, S3, RDS, Lambda, NAT Gateway, CloudWatch, and AWS Backup each have distinct billing components that belong in the cost model.

AWS Pricing Calculator supports pre-deployment estimation; Cost Explorer, Budgets, Cost Anomaly Detection, and CUR/Data Exports data support post-deployment tracking. Cost allocation tags and Cost Categories identify responsible teams, while FinOps connects cost data to engineering decisions and business goals.

A cost-efficient system is not simply one with a low bill. It delivers value at a reasonable cost while meeting performance, security, availability, and resilience requirements. By measuring cost per unit of output, optimizing per workload, and reviewing regularly, organizations can scale AWS in a controlled manner.
