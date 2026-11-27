# AWS Pricing Calculator and Architecture Cost Estimation

AWS Pricing Calculator helps estimate the cost of a workload before deployment or when changing an architecture on AWS. The tool takes assumptions about services, Regions, resource configurations, and usage levels, and then calculates projected costs under the corresponding pricing model. The results support comparing alternatives, budgeting, aligning with product owners, and evaluating the financial impact of engineering decisions.

An architecture can only be estimated well when both the technical model and the usage model are clearly defined. Selecting the right EC2 instances while forgetting EBS, data transfer, NAT Gateways, load balancers, log ingestion, or backups will significantly understate total cost. Similarly, entering average request counts while ignoring peaks, retries, cache misses, or inter-AZ traffic can make an estimate much lower than reality.

In the AWS ecosystem, Pricing Calculator helps model costs across compute, storage, database, networking, integration, serverless, monitoring, and other components. The tool is a planning step; once the system is running, estimates must be reconciled against actual costs via AWS Billing, Cost Explorer, Cost and Usage Reports, and FinOps processes.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Distinguish the public AWS Pricing Calculator from the in-console Pricing Calculator experience in the AWS Billing and Cost Management console.
- Gather technical requirements and translate them into priceable usage units.
- Build estimates by service, Region, workload, and architectural group.
- Estimate compute, storage, database, networking, data transfer, integration, serverless, and observability components.
- Compare On-Demand, Spot, Reserved Instances, and Savings Plans when the usage pattern fits.
- Build baseline, optimized, and growth scenarios; clearly explain assumptions and limitations.
- Export, save, and share estimates, and integrate results into architecture/FinOps review workflows.
- Reconcile estimates against actual costs after deployment to calibrate assumptions.

## 2. What Is AWS Pricing Calculator?

AWS Pricing Calculator is an estimation tool based on usage inputs provided by the architect. Learners can access the public calculator at https://calculator.aws/ without creating an AWS account. The tool lets you add services, select Regions, configure workload parameters, organize by groups, and review total upfront, monthly, and 12-month costs. The public calculator is not a metering system for a running account.

AWS currently provides two experiences that should be distinguished:

| Criterion | Public AWS Pricing Calculator | In-console AWS Pricing Calculator |
|---|---|---|
| Access point | Website calculator.aws | AWS Billing and Cost Management console |
| AWS account | Not required | Required |
| Purpose | Estimate new workloads or proposed architectures using public rates | Model workloads and their impact on an account/Organization bill |
| Historical data | User manually enters assumptions | Can import historical usage; requires Cost Explorer enabled for usage import |
| Discounts/commitments | Public calculator focuses on public rates and options supported in the service configurator | Can use after-discount rates and model existing or planned Savings Plans/Reserved Instances based on permissions and rate preferences |
| Output | Estimate by service and group; supports PDF/CSV export and public share links | Workload estimate or bill estimate; managed inside the account with API/SDK support per in-console documentation |
| Audience | Learners, architects, project teams, users without an account | FinOps, billing owners, management accounts, and authorized member accounts |

### 2.1 Public Calculator

The public calculator is suitable when you need to quickly estimate a new workload, compare Regions, or prepare options before an account exists. A common workflow is:

1. Create an estimate.
2. Add services to the estimate.
3. Select a Region and enter configuration/usage parameters.
4. Save the service to the estimate.
5. Organize services into groups.
6. Review total upfront, monthly, and 12-month costs.
7. Export CSV/PDF or generate a share link.

The public calculator does not require signing in. Estimate share links are stored on AWS public servers; anyone with the link can view the estimate. Do not put secrets, sensitive internal identifiers, or restricted architectural details in an estimate's name or description.

Per the public calculator documentation, there is currently no API for the public website. If you need to integrate estimates into automated workflows, check the in-console Pricing Calculator API and appropriate pricing data APIs; do not assume the public calculator has undocumented endpoints.

### 2.2 In-console Calculator

The in-console Pricing Calculator provides two types of estimates:

- **Workload estimate:** estimates the cost of a specific workload, application, set of resources, or architectural change. It can use public rates or effective rates permitted by the management account, including after-discount and after-discount-plus-commitment rates.
- **Bill estimate:** estimates the impact of modeled usage/commitments on the Organization's entire consolidated bill. A bill estimate automatically pulls in usage from the most recent billing period and existing commitments such as Savings Plans/Reserved Instances; this estimate type is intended for a management account or standalone account.

A workload estimate is useful for answering "if we deploy Architecture A, how much will this workload cost?". A bill estimate is useful for answering "if we change usage or commitments, how will the Organization's total bill change?". The two questions have different scopes; do not use a workload estimate to replace a consolidated bill analysis when commitments have not been accounted for.

The in-console calculator can use historical data and discounts depending on permissions. The management account configures rate preferences for member accounts; if permission to use after-discount rates has not been granted, member estimates may use public rates. Importing historical usage requires Cost Explorer to be enabled per AWS documentation.

Workload estimates are provided free of charge. For bill estimates, each account gets five free estimates per month; starting from the sixth estimate in the same calendar month, each estimate costs $2 USD according to current AWS documentation. If an estimate fails, it does not count toward the free quota and is not billed. Always verify the current pricing page before budgeting for recurring analysis activities.

## 3. An Estimate Is an Assumption-Driven Model, Not a Quote

Pricing Calculator produces approximate figures based on the parameters entered. Results are not a binding quote, do not guarantee the actual bill, and do not replace contracts or formal quotes from AWS or partners. Actual costs depend on real usage, Region, timing of usage, price changes, tiers, discounts, commitments, additional services, and how the workload operates.

Estimate quality is bounded by input quality. If an architect enters one EC2 instance running 730 hours per month, but production actually runs more instances, keeps a staging environment on, or triggers autoscaling, the bill will differ. If the architecture includes data transfer, NAT Gateways, snapshots, logs, support, or Marketplace licenses that the estimate omits, total cost will also be understated.

Explicitly document three categories of data in every estimate:

| Data Category | Examples | How to Manage |
|---|---|---|
| Known | Current node count, DB size, chosen Region | Cite inventory, design docs, or measured telemetry |
| Assumed | 2,000,000 requests/day, 30% cache hit, 500 GB egress/month | Record approver, date, and rationale |
| Unknown | Post-launch growth, retry rate, peak log volume | Build low/base/high scenarios and define post-launch measurement |

A useful estimate explains why costs arise, what drives them up, and which assumptions need validation. Presenting only a single total figure without structure or assumptions is hard to use for decision-making.

## 4. Preparing Data Before Opening the Calculator

Before adding services, describe the workload using technical questions. Do not start from a list of services and leave the tool's default numbers untouched.

### 4.1 Architectural Scope

- Which product, environment, and cost center does the workload serve?
- Is it deployed in a single Region or multiple Regions?
- Does it require Multi-AZ, read replicas, standby nodes, disaster recovery, or active-active?
- Which components run continuously, and which run only on a schedule or per request?
- Which development, test, staging, production, and sandbox environments must be included?
- Which services does data traverse, and is there inter-AZ, inter-Region, or Internet traffic?
- Are there third-party services, AWS Marketplace items, OS/database licenses, or support plans?

### 4.2 Usage Levels

Gather both averages and peaks:

- Number of instances/containers/tasks/pods and running hours.
- vCPU, RAM, CPU architecture, OS, tenancy, and licensing.
- Requests/second, requests/day, processing duration, concurrency, retries, and cache hit ratio.
- Average stored capacity, monthly incremental growth, IOPS, throughput, and request counts.
- Data inbound/outbound over the Internet, across Availability Zones, across Regions, and between services.
- Log/metric/trace volume, retention duration, queries, and exports.
- Backups, snapshots, replication, data retrieval, and restore frequency.
- Number of users, API calls, messages, events, and batch jobs.

### 4.3 Consistent Measurement Units

| Category | Common Units | Example |
|---|---|---|
| Compute | instance-hour, vCPU-hour, GB-hour, task-hour | 2 instances running 730 hours/month |
| Requests | request, invocation, message, API call | 30 million invocations/month |
| Storage | GB-month or TB-month | Average capacity 2 TB/month |
| I/O | IOPS, I/O request, throughput | 5,000 IOPS and 100 MB/s |
| Data transfer | GB/TB by direction and destination | 800 GB Internet egress/month |
| Logging | GB ingested, GB scanned, metric-month | 40 GB log ingestion/month |
| Database | instance-hour, ACU-hour, vCPU/RAM-hour, storage, I/O | Multi-AZ DB running continuously |
| Backup | GB-month, snapshot storage, copy, restore | 2 TB recovery points retained |

Do not mix GB with GiB, MB/s with Mbps, or requests/day with requests/month without converting. If a telemetry source reports bytes and the calculator uses GB, document the conversion explicitly. Unit mismatches can create huge discrepancies even when formulas are right.

### 4.4 Determining Usage Hours

A service may run 24/7, only during business hours, or scale with events. The public calculator commonly uses a 730-hour month assumption for monthly cost calculations. If a workload runs 8 hours/day, 22 days/month, expected hours are 176 hours, though you should add extra hours for deployments, retries, maintenance, and environments left running.

For autoscaling, sum the hours of each capacity tier instead of multiplying maximum instances by 730. For example, 2 baseline instances running all month plus 2 additional instances running 4 hours/day for 30 days yields 1,700 instance-hours in the assumed month:

    Baseline = 2 × 730 = 1,460 instance-hours
    Burst    = 2 × 4 × 30 = 240 instance-hours
    Total    = 1,460 + 240 = 1,700 instance-hours

If burst instances use a different instance type or Spot, separate their usage to price them accurately.

## 5. Step-by-Step Workflow with the Public Calculator

### Step 1: Decide How to Organize the Estimate

Before opening the tool, choose an appropriate grouping scheme:

- By product/workload: website, order service, data platform, mobile backend.
- By architectural layer: edge, application, database, analytics, observability.
- By environment: production, staging, development.
- By cost center/team/client.
- By Region: primary, disaster recovery, or Regions being compared.

AWS recommends deciding how to structure the estimate upfront so Groups are meaningful. An estimate can hold multiple services and groups; summing groups reveals the full workload picture.

### Step 2: Create an Estimate and Add Services

Open https://calculator.aws/ and choose Create estimate. On the Add service page, search for a service by name or filter by location/service category. Choose Configure to open the configuration screen. Each service has its own set of inputs; not every service shares the same unit model.

### Step 3: Select Location and Region

Choose the Region where resources will actually run—do not pick a Region out of habit or solely for the lowest price. Pricing, instance availability, features, quotas, data residency, latency, DR capabilities, and connectivity to existing systems can vary across Regions.

If the architecture spans multiple Regions, create separate groups or service estimates for each Region. Also include data copy costs, inter-Region transfer, replication, backups, and cross-Region traffic. Do not apply a single Region's pricing to all services when some components reside elsewhere.

### Step 4: Enter Service Parameters

For each service:

1. Provide a meaningful description, such as "API production – application tier".
2. Select the Region/location type.
3. Choose resource configurations aligned with technical requirements.
4. Enter quantities and usage hours.
5. Enter associated storage, requests, I/O, throughput, or data transfer.
6. Select a pricing model if the configurator supports it and it fits the workload.
7. Review add-ons, monitoring, backups, data transfer, and licensing.
8. Use Show calculation to inspect how the cost is derived.
9. Save and add the service to the estimate.

Do not leave default values untouched just because the tool pre-filled them. Some screens default to one instance or a tiny starting storage size as a placeholder; replace them with gathered usage numbers.

### Step 5: Add Dependent Services

After adding compute or databases, check supporting components:

- EBS or block storage for EC2.
- Load balancers, NAT Gateways, public IPv4 addresses, data transfer, and Route 53.
- Snapshots, backups, replication, and storage retrievals.
- CloudWatch logs, metrics, alarms, dashboards, and tracing.
- KMS requests, Secrets Manager secrets/API calls, and certificates.
- SQS, SNS, EventBridge, API Gateway, Step Functions, or inter-service data transfer.
- AWS Support, Marketplace software, licenses, and external non-AWS costs if within TCO scope.

The calculator only prices what has been added or what the configurator explicitly includes. Walk through the architecture end-to-end so no dependencies are missed.

### Step 6: Organize Groups and Review Totals

Create groups per layer, workload, Region, or cost center. Move services into the appropriate groups for ownership-based review. The My estimate page displays total upfront, monthly, and 12-month costs along with service/group breakdowns. Inspect the detailed line items, not just the grand total.

### Step 7: Save and Export

Generate a share link if collaborating via the public calculator; record the link alongside the description, creation date, assumption version, and owner. Export CSV for data analysis or PDF for stakeholder review. A public calculator PDF includes the estimate's share link.

If you modify an estimate, generate a new link after saving. The public calculator does not overwrite old links in place; public links created on or after May 31, 2023 remain valid for one year per current documentation. For sensitive estimates or IAM-governed access, consider the in-console calculator.

## 6. Parameters to Enter by Service Group

### 6.1 Compute: EC2, ECS, EKS, and Lambda

| Component | Key Inputs | Frequently Missed Costs |
|---|---|---|
| EC2 | Region, instance type, OS, tenancy, instance count, workload pattern, running hours, pricing model | EBS, snapshots, data transfer, detailed monitoring, Elastic IP/public IPv4, licenses, load balancer |
| ECS on EC2 | EC2 capacity, node count, CPU/RAM utilization, scaling | Idle EC2 headroom, EBS, networking, load balancer, logs |
| ECS/Fargate | vCPU, memory, ephemeral storage, task count, duration, platform | NAT/data transfer, load balancer, logs, image pulls, idle service minimum |
| EKS | Cluster/control-plane fee, node group or Fargate profile, pod capacity | EC2/EBS, load balancer, NAT, inter-AZ, observability, add-ons |
| Lambda | Invocations, memory, duration, architecture, provisioned concurrency, ephemeral storage | API Gateway, EventBridge/SQS, retries, logs, data transfer, provisioned concurrency |

For EC2, pick the exact OS because Windows, Linux, and certain licenses have different billing rules. Check tenancy (Shared/Dedicated/Host), instance family, size, instance count, and usage pattern. The calculator can model constant, daily spike, weekly spike, or monthly spike workloads in the EC2 configurator. Workload patterns help better estimate On-Demand versus reservation-eligible usage.

For burstable instances, check Unlimited mode and CPU credit surplus if average load can exceed the baseline. Do not pick instances based solely on vCPU/RAM; network performance, EBS bandwidth, CPU architecture, memory pressure, and licensing also affect selection.

For containers, do not assume pod count is the direct billing unit in every scenario. ECS on EC2 pays for EC2 capacity and storage/networking; Fargate charges by configured vCPU/memory/time; EKS has a cluster/control plane fee plus node or Fargate costs. Include spare capacity headroom for autoscaling and rolling deployments.

For Lambda, request count alone is insufficient. You need duration, memory, architecture, provisioned concurrency, ephemeral storage, and retry rate. A rarely invoked function with long duration or high provisioned concurrency can still carry substantial costs. Do not forget log ingestion and triggering services.

### 6.2 Storage: EBS, S3, EFS, and FSx

| Service | Inputs | Items to Verify |
|---|---|---|
| EBS | Volume type, GB-month, IOPS, throughput, volume count | Differences across gp3/io2/gp2; provisioned IOPS/throughput; snapshots |
| S3 | Average capacity per storage class, PUT/GET/LIST, retrievals, lifecycle, replication | Versioning, object count, minimum storage duration, retrieval fees, request fees, data transfer |
| EFS | Storage class, average storage, throughput mode, provisioned throughput, requests | Regional/One Zone, lifecycle, IA/archive access, backups |
| FSx | File system type, capacity, throughput, deployment type, backups | Multi-AZ, SSD/HDD, throughput capacity, backup storage, data transfer |

Do not use end-of-month storage size in place of average storage when storage grows steadily. If 1 TB of data grows linearly from 0 to 1 TB over 30 days, average storage is roughly 0.5 TB-month under a linear model, though actuals depend on ingest timing and retention.

For S3, separate Standard, Intelligent-Tiering, Standard-IA, One Zone-IA, and Glacier Instant/Flexible/Deep Archive by access pattern. Estimate object counts, request classes, retrievals, transitions, minimum storage durations, restores, and replication. Cheaper storage tiers can introduce higher retrieval charges or longer restore wait times.

For EBS, account for both capacity and provisioned IOPS/throughput. Snapshots are typically incremental, but cost depends on changed blocks and retention duration. If snapshots are copied to another Region, include destination copy/storage fees and data transfer per service rules.

### 6.3 Database: RDS, Aurora, DynamoDB, and ElastiCache

| Service | Inputs | Items to Model |
|---|---|---|
| RDS | Engine, instance class, instance count, Multi-AZ, storage, IOPS, backups, data transfer | Primary/standby/read replicas, storage, I/O, backups exceeding free allocation, engine licenses |
| Aurora | Engine, provisioned or Serverless v2, instances/ACUs, storage, I/O, backups | Readers, Multi-AZ storage, I/O requests, backups, data transfer |
| DynamoDB | Read/write request units, on-demand/provisioned, table/index storage, backups, streams, global tables | GSI/LSI, transactional requests, PITR, export/import, replication |
| ElastiCache | Engine, node type, node count, replicas, shard count, data tiering | Multi-AZ/replicas, backups, snapshots, data transfer |

For RDS Multi-AZ, select the Multi-AZ configuration in the calculator if the configurator provides it. Do not both choose Multi-AZ and manually add another standby instance if the price already includes the standby. Read replicas are an additional component serving a different purpose; model them separately according to the actual topology.

Aurora provisioned and Aurora Serverless v2 use different capacity units. For Serverless v2, estimate average ACU, min/max ACU, active duration, and scaling patterns. For DynamoDB, distinguish on-demand from provisioned capacity, tables/indexes, reads/writes, transactional operations, backups/PITR, streams, and global table replication.

### 6.4 Networking and Content Delivery

| Component | Units/Inputs | Notes |
|---|---|---|
| Application/Network Load Balancer | Load balancer-hours, LCU/NLCU-hours | LCU is based on usage dimensions; takes the highest dimension per service rules |
| NAT Gateway | Gateway-hours, GB processed | Count AZs with NAT and traffic flowing through each gateway |
| Data transfer | GB by source/destination/Region/AZ | Separate Internet egress, inter-AZ, inter-Region, cross-account, and service-specific transfer |
| CloudFront | Data transfer out by edge region, requests, invalidations, and features | Cache hit ratio changes origin traffic; pricing varies by location |
| Route 53 | Hosted zones, queries, health checks, resolver endpoints/queries | Include private hosted zones and health checks if used |
| Public IPv4 | Address-hours or corresponding usage type | Check address type and duration attached to resources |
| VPC endpoints | Endpoint-hours, data processing | Interface endpoints and Gateway endpoints have different pricing models |

Networking is the category most often omitted from estimates. A workload may have reasonably priced EC2 instances while incurring high NAT, inter-AZ transfer, load balancer, and Internet egress costs. Diagram the data flow and calculate bytes crossing each network boundary.

### 6.5 Integration, Serverless, and Application Services

- API Gateway: request count, API type, caching, data transfer, private integrations.
- SQS: request count, batch size, payload size, long polling, FIFO, and dead-letter queues.
- SNS: publishes/deliveries, protocol, and endpoint count.
- EventBridge: event ingestion, archive/replay, cross-account/Region event buses.
- Step Functions: state transitions, Standard/Express workflows, retries, and execution duration.
- Kinesis: shard-hours or throughput/on-demand data, retention, and enhanced fan-out.
- AppSync: requests, connections, data transfer, and resolver usage.
- Secrets Manager: secret count, API calls, rotation Lambdas, and cross-Region replication.

A single user request can trigger multiple services. For instance, API Gateway receives one request, Lambda runs twice due to a retry, writes a message to SQS, emits an event, reads a secret, and writes logs. An estimate that only counts API requests while omitting invocations and downstream requests will undercount costs.

### 6.6 Observability and Security

Operational and security costs are also part of the architecture:

- CloudWatch Logs: GB ingested, storage/retention, Logs Insights scans, subscriptions/filters, and exports.
- CloudWatch Metrics: custom metrics, dimensions/cardinality, high-resolution metrics, alarms, and dashboards.
- X-Ray/Application Signals: trace ingestion, sampling, retention, and service maps.
- KMS: API requests, key types, rotation, and multi-Region keys if used.
- AWS Config: configuration item recording, rule evaluations, and conformance packs.
- CloudTrail: management/data events, Lake ingestion/retention, and S3 storage.
- GuardDuty/Security Hub/Inspector: resource coverage, finding volume, scan or ingestion model per pricing page.
- AWS Backup: protected storage, warm/cold tiers, copies, and restores.

More detailed telemetry helps operations but also carries a price. Estimate log volume from request count × log bytes/request; estimate traces after sampling; control metric cardinality and retention. Do not pick an arbitrary GB figure for logs without log samples or benchmarks.

## 7. Pricing Models to Understand Before Comparing

### 7.1 On-Demand

On-Demand fits when usage is not yet stable, workloads are new, or capacity must remain flexible. Costs generally depend on usage units such as instance-hours, GB-months, requests, or I/O. Rates vary by Region, service, OS, instance type, and time.

The advantage is no long-term commitment; the disadvantage is higher unit pricing when usage remains steady long term. Use On-Demand as the baseline before modeling discounts/commitments.

### 7.2 Savings Plans

Savings Plans are a spend commitment in USD/hour over a typical one- or three-year term in exchange for discounted rates on eligible usage. Two main categories:

- Compute Savings Plans offer broader flexibility across EC2, Fargate, and Lambda under program terms.
- EC2 Instance Savings Plans are tied to a specific instance family/Region and typically provide higher savings when workloads remain stable within that scope.

Commitments are measured in hourly spend, not reserved instance counts. Eligible usage receives the discounted rate; usage exceeding the commitment or outside eligible scope continues at standard rates. Unused commitment still incurs the committed charge.

### 7.3 Reserved Instances

Reserved Instances (RIs) are a pricing model for supported services and resource types. For EC2, RIs provide a discount on usage matching reservation attributes; Standard RIs offer higher discounts with less flexibility than Convertible RIs. RIs do not automatically reserve capacity unless an appropriate capacity reservation option is selected. RDS and several other services have their own reservation models.

Common terms are one or three years. Payment options include No Upfront, Partial Upfront, and All Upfront. All Upfront can lower total cost but requires upfront cash; No Upfront reduces initial cash outlay while remaining a term commitment.

### 7.4 Spot

Spot uses spare EC2 capacity at discounted rates and can be reclaimed by AWS when capacity is needed. Spot fits interruption-tolerant workloads such as batch jobs, stateless workers, CI jobs, or checkpointed distributed processing. Do not use Spot as the sole capacity for non-interruptible components.

The public EC2 configurator can show historical Spot discounts and accept a discount assumption to generate an estimate. Actual Spot prices vary by pool, Region, and time; historical figures do not guarantee future savings. For workloads requiring more accurate Spot modeling, create separate scenarios and verify against pricing/Spot data.

### 7.5 Dedicated Tenancy, Hosts, and Licensing

Dedicated Instances, Dedicated Hosts, or licensing models can significantly alter costs. When Windows Server, SQL Server, Oracle, or BYOL licenses are required, determine whether licensing is included in the hourly rate, charged per core/socket, per host, or under a separate agreement. AWS Pricing Calculator does not automatically include all third-party or Marketplace license fees.

### 7.6 Choosing a Model by Workload Stability

| Workload Characteristics | Appropriate Starting Point | Items to Verify |
|---|---|---|
| Unknown traffic, newly launched | On-Demand | Collect actual usage after launch |
| Continuous baseline, variable peaks | Commitment for baseline + On-Demand for burst | Commitment level sustainable reliably |
| Interruption-tolerant batch | Spot combined with fallback capacity | Checkpointing, retries, completion time |
| Stable EC2 family/Region | Compare EC2 Instance Savings Plans and RIs | Family, Region, OS, and term flexibility |
| Multiple changing compute services | Compute Savings Plan | Eligible service scope and utilization |
| Stable RDS workload | RDS Reserved DB Instances if suitable | Engine, Region, class, Multi-AZ, and term |

Do not buy a commitment just because an estimate shows large savings. First verify baseline usage, commitment term, migration plans, growth expectations, and your ability to utilize the commitment if the workload shifts.

## 8. Analyzing Network and Data Transfer Costs

Data transfer costs typically depend on transfer direction, Region, Availability Zone, service type, and connection point. Separate at least these flows:

1. Internet ingress: data from users into AWS.
2. Internet egress: data from AWS out to users.
3. Inter-AZ: data between Availability Zones in the same Region.
4. Inter-Region: data between Regions.
5. Cross-account: data/backups shared across accounts, depending on service pricing.
6. Service-to-service: data among EC2, S3, CloudFront, NAT, VPC endpoints, and other services.

Do not apply one flat data transfer rate to every flow. Some services have allowances or special rules; certain paths within the same Region can incur per-service or per-AZ fees. Always check pricing pages for both source and destination.

### 8.1 NAT Gateway

NAT Gateways can incur charges per gateway-hour and per GB processed. In a Multi-AZ architecture, if each AZ has its own NAT Gateway to avoid cross-AZ dependencies, count the actual number of gateways and distribute traffic across each gateway. If you model only one NAT while deploying across three AZs, the estimate will miss both gateway-hours and potentially data processing/inter-AZ transfer.

Some traffic to AWS services can bypass NAT using Gateway endpoints or Interface endpoints. However, Interface endpoints have endpoint-hour and data processing charges; Gateway endpoints for S3/DynamoDB have a different pricing model. Compare based on traffic and security requirements rather than assuming endpoints are always cheaper than NAT.

### 8.2 Load Balancers

Application Load Balancers and Network Load Balancers charge per hour and per processing unit (LCU/NLCU) across dimensions defined by the service. Estimate new connections, active connections, processed bytes, and rule evaluations according to the load balancer type. Use the highest-utilized dimension per the service's calculation rules—avoid summing all dimensions as independent charges if the calculator already picks the maximum.

### 8.3 CloudFront and Caching

CloudFront can reduce origin requests and improve user experience, though costs depend on edge location, data transfer, requests, invalidations, and enabled features. A high cache hit ratio reduces origin traffic and backend load; cache misses, dynamic content, invalidations, or overly short TTLs can drive origin costs up.

When comparing with versus without CloudFront, calculate CloudFront costs alongside the resulting reductions in EC2/ALB/S3/Data Transfer. Do not compare CDN rates solely against origin egress rates.

### 8.4 Inter-AZ and Topology

Applications distributed across multiple AZs can incur data transfer when nodes in AZ A call databases or services in AZ B. Adding replicas or sharding can improve HA and throughput while increasing inter-AZ traffic. Map actual traffic flows and estimate GB/month rather than simply writing "Multi-AZ".

## 9. Estimation Formulas and Unit Sanity Checks

A few simple sanity-check models help validate Calculator results:

    Monthly compute ≈ units × usage hours × price per unit-hour
    Monthly storage ≈ average capacity (GB-month) × price per GB-month
    Request cost ≈ requests / pricing unit × price per unit
    Data transfer cost ≈ billable GB per path × path rate
    Monthly total ≈ compute + storage + I/O + network + requests + operations + support + licenses

These are validation checks, not replacements for pricing pages. Some services use tiers, minimum charges, per-second billing, capacity, throughput, peak metrics, or multi-dimensional combinations. Use Show calculation to inspect which units the calculator is using.

### 9.1 Hour Conversions

    1 instance running continuously under calculator assumption = 730 instance-hours/month
    4 instances running 12 hours/day for 30 days = 4 × 12 × 30 = 1,440 instance-hours
    2 baseline instances + 2 instances running 4 extra hours/day:
      2 × 730 + 2 × 4 × 30 = 1,700 instance-hours

Do not treat 730 hours as the exact hour count of every calendar month. It is the calculator's standard convention for comparison. If systems run by calendar month, start mid-month, or use per-second billing, actual charges may differ.

### 9.2 Average Capacity

If data grows linearly from 100 GB to 400 GB over 30 days, average capacity is approximately:

    Average storage = (100 + 400) / 2 = 250 GB

If all data is loaded on day one, average capacity is close to 400 GB. If older data is deleted by lifecycle rules, model retained capacity rather than cumulative ingest alone.

### 9.3 Requests and Duration

For Lambda, calculate both request count and compute duration for the configured memory. For example, 10 million invocations with 200 ms average duration:

    Total execution time = 10,000,000 × 0.2 seconds
                         = 2,000,000 seconds

This is cumulative execution time for scale checking; exact cost also depends on memory, architecture, ephemeral storage, provisioned concurrency, free tier, and Region.

### 9.4 Data Transfer

Suppose 1,000,000 requests/day with an average response of 80 KB over 30 days:

    Monthly response bytes = 1,000,000 × 80 KB × 30
                           = 2,400,000,000 KB

This is raw response volume before accounting for compression, caching, protocol overhead, retries, and unit conversion. If CloudFront caches 70% of responses, origin egress may be considerably lower; however, CloudFront still delivers data to end users and incurs its own charges.

### 9.5 Avoiding Double-Counting

Common double-counting mistakes:

- Selecting RDS Multi-AZ in the calculator and manually adding a standby DB even though the configurator already includes it.
- Using an EC2 configurator with default EBS included and adding the same volume again separately.
- Entering data transfer inside EC2 and adding the exact same traffic again in a general network section.
- Counting all API-layer requests and recounting internal requests if the calculator already models them in service usage.
- Using discounted rates and subtracting the discount a second time.
- Counting snapshots/backups twice when the estimate already includes backup storage.

Every cost line item needs one measurement unit, one data source, and one owner. Flag items already included by a service configurator versus items that must be added manually.

## 10. Example: Estimating an E-Commerce Web Architecture

Suppose a project team designs an e-commerce application for customers in Vietnam. This is an example of how to build assumptions; fixed USD prices are omitted because unit rates, Regions, and service availability can change.

### 10.1 Assumed Architecture

    Users
       |
    Route 53 / CloudFront
       |
    Application Load Balancer
       |
    EC2 Auto Scaling (2 AZs)
       |                 \
    RDS Multi-AZ       S3 Invoices
       |
    ElastiCache

    Lambda + SQS for background tasks
    NAT / VPC endpoints for outbound traffic
    CloudWatch for logs, metrics, and alarms
    AWS Backup for snapshots and DR copies

### 10.2 Input Usage Table

| Component | Baseline Assumption | Estimate Unit |
|---|---|---|
| EC2 application | 2 baseline instances 730 hours; plus 2 instances 4 hours/day for 30 days | 1,700 instance-hours |
| EBS | 2 gp3 volumes, 100 GB each | 200 GB-month |
| ALB | 1 ALB running continuously, measured average and peak traffic | 730 ALB-hours + LCU-hours |
| RDS | 1 Multi-AZ database, benchmarked class, 500 GB storage | DB-hours + 500 GB-month + I/O |
| ElastiCache | 2 cache nodes running continuously | 1,460 node-hours |
| S3 | Average 500 GB stored; 5M GET and 200,000 PUT/month | GB-month + requests |
| CloudFront | 1 TB data served/month, 70% cache hit | GB transfer by edge + requests |
| NAT Gateway | 2 AZs, one NAT per AZ, 300 GB processed total | 1,460 gateway-hours + 300 GB |
| Lambda | 10M invocations, 256 MB, 200 ms average | Requests + GB-seconds |
| SQS | 20M requests/month, defined batch size | Request units |
| CloudWatch Logs | 40 GB ingested/month, 30-day retention | Ingest + storage + queries |
| Backup | 1 TB warm recovery points, copied to 1 DR Region | Storage + copy/transfer |

These numbers are sample inputs for practice. In a real project, replace them with data from benchmarks, analytics, access logs, CloudWatch, or comparable systems. RDS classes and EC2 types must be chosen from CPU/RAM/network requirements and load test results.

### 10.3 Organizing the Estimate by Group

Create the following groups:

| Group | Services Included |
|---|---|
| Edge and network | Route 53, CloudFront, ALB, NAT Gateway, VPC endpoints, data transfer |
| Application | EC2, EBS, Lambda, SQS |
| Data | RDS, ElastiCache, S3 |
| Operations and security | CloudWatch, KMS, Secrets Manager, AWS Backup |
| Disaster recovery | Cross-Region copies, backup storage, and DR resources if standby runs |

Inside each service, select the target Region and enter the corresponding usage dimensions. If the calculator lacks a needed dimension or service, log that item in an assumptions/adjustment register and document how to estimate it separately from the pricing page. Do not omit an item simply because the configurator does not display it.

### 10.4 Building Three Scenarios

| Scenario | Assumptions | Purpose |
|---|---|---|
| Low | Low traffic, high cache hit, low log volume, rare bursts | Check cost under slow adoption |
| Base | Expected usage from business plan and benchmarks | Used for initial budgeting |
| High | Higher traffic, lower cache hit, higher logs/egress, extended scale-out | Stress-test budget and load capacity |

The high scenario is not just increasing every line by 10%. Increase correlated drivers together: higher request volume can raise Lambda, SQS, logs, data transfer, and database I/O simultaneously. A campaign might create a peak lasting a few hours; do not multiply peak capacity across an entire month if the workload peaks only briefly.

### 10.5 Reading the Results

After calculation, inspect:

- Which component represents the largest share?
- Which fixed costs still appear during low traffic?
- Which components scale linearly with requests or data volume?
- Are there costs that scale with peak capacity or AZ count?
- Does DR cost cover storage/copies while omitting failover compute?
- Is anything double-counted or omitted?
- Does the high scenario exceed the budget or alter architectural choices?

If compute dominates, benchmark instance families, Graviton, autoscaling, and commitments. If networking dominates, inspect NAT, data transfer, caching, and topology. If storage/databases dominate, check retention, storage classes, IOPS, query patterns, and backups.

## 11. Comparing Architectural Options with the Calculator

The calculator is most valuable when comparing options that deliver equivalent service quality. Do not select an architecture solely on monthly total if two designs differ in RPO, RTO, availability, latency, or security.

### 11.1 Single-AZ vs. Multi-AZ

Create two groups or two estimates:

- Option A: single AZ, fewer replicas, lower cost but different blast radius and availability.
- Option B: multiple AZs, with standby/replicas, load balancers, and corresponding network paths.

Account fully for compute, database standby, load balancers, inter-AZ traffic, per-AZ NATs, backups, and data transfer. Weigh the incremental cost against downtime risk reduction and SLA/SLO targets.

### 11.2 EC2 vs. Containers/Serverless

Compare EC2, ECS/Fargate, EKS, or Lambda at the same throughput, latency, and concurrency. Include:

- Headroom capacity and CPU/RAM utilization.
- Cluster/control plane fees if applicable.
- Load balancers, networking, logs, and image storage.
- Idle cost during low traffic.
- Operational time, patching, scaling, and complexity.

Serverless is not automatically cheaper for continuously running, high-throughput workloads; EC2 is not automatically cheaper when utilization is low. Benchmarks and usage patterns decide.

### 11.3 Region A vs. Region B

Create a group for each Region while keeping the same workload assumptions. Compare service availability, compute/storage/database pricing, data transfer, latency, compliance, support, and connectivity costs. If Region B requires copying data from Region A or serving distant users, include transfer/latency trade-offs.

### 11.4 On-Demand vs. Commitments

Set On-Demand as the baseline. Then model commitments for the steady baseline portion while keeping bursts on On-Demand. Compare total cost over the full term, upfront payments, monthly payments, unused commitment exposure, and workload contraction risk.

Do not compare standalone monthly prices if one option includes an upfront payment. Use total term cost, cash flow, and commitment utilization capacity.

### 11.5 Storage Classes and Retention

Compare S3 Standard against Intelligent-Tiering or other storage classes based on access frequency, retrievals, minimum duration, and lifecycle. For EBS, compare gp3 against io2 based on required IOPS/latency; for EFS/FSx, compare storage classes and throughput. Include backups, replication, restores, and retrievals.

## 12. Assumptions and Limitations to Disclose

The public calculator carries several important general assumptions per the AWS Pricing Assumptions page:

| Assumption | Impact on Estimate |
|---|---|
| 730 hours/month | Does not match exact hours of every month; does not reflect leap years |
| USD | Conversion to VND may fluctuate with exchange rates |
| Taxes excluded | Local taxes/VAT and statutory charges must be handled separately |
| Free Tier not automatically applied | Do not assume estimates are reduced by Free Tier or credits |
| Promotional credits/discounts not fully reflected in public calculator | Actual bill may be lower if the account has discounts |
| Tiered pricing | Existing usage outside the estimate may affect actual pricing tiers |
| Per-second billing | Some services bill per second; calculator assumptions may differ from actuals |
| Third-party licenses | Marketplace/software licenses may not be included in the estimate |
| Price changes | On-Demand prices and features/pricing models may be updated |
| Actual usage | Instance counts, data transfer, requests, retention, and traffic differing from assumptions will change the bill |

Some EC2-specific assumptions:

- Default tenancy may be Shared Instances; change it if the architecture requires Dedicated.
- Default OS may be Linux; select the exact OS/license.
- Default instance count may be one.
- Default EBS volumes may be pre-filled; replace them with actual counts and sizes.
- Detailed monitoring, data transfer, Elastic IPs, and additional costs must be reviewed.
- Burstable instances may incur CPU credit charges when configuration/usage exceeds baseline under service rules.

With the public calculator, do not assume Free Tier, promotional credits, or discounts will apply unless explicitly shown in the configurator. With the in-console calculator, inspect rate preferences, usage imports, and estimate type to see which historical data, discounts, or commitments are included.

## 13. Reviewing Estimates and Checking Reasonableness

A strong review process verifies architecture, quantities, and unit rates:

1. **Scope:** estimate covers the intended workload, environments, Regions, and timeframe.
2. **Completeness:** every component in the diagram has a cost line or an explicit note explaining why it is excluded.
3. **Quantity:** instance-hours, GB-months, requests, IOPS, GB transferred, and retention match the workload.
4. **Pricing model:** On-Demand, Spot, RIs, or Savings Plans align with stability and term.
5. **Architecture:** Multi-AZ, DR, replicas, NAT, endpoints, and load balancers are fully accounted for.
6. **Dependencies:** logs, metrics, backups, KMS, secrets, support, and licenses are included.
7. **Assumptions:** known facts, assumptions, and unknowns are clearly separated.
8. **Sensitivity:** low/base/high scenarios and key cost drivers are explained.
9. **Double-count:** items already included in a configurator are not counted twice.
10. **Owner:** every assumption has a confirming owner and a review date.

### 13.1 Sanity Check by Cost Share

If a small web workload shows NAT/data transfer costs many times higher than compute, inspect GB through NAT, NAT gateway count, and traffic paths. If databases represent a massive share, review instance class, Multi-AZ, storage, IOPS, and replicas. If CloudWatch accounts for an unusually large share, check log ingestion, retention, custom metric cardinality, and query scans.

There is no universal target percentage for all architectures. The goal is to catch line items inconsistent with the usage model and re-verify inputs.

### 13.2 Comparing Against an Actual Baseline

If a similar workload already exists, use Cost Explorer or Cost and Usage Reports to pull actual usage/cost as a baseline. Adjust for scale, Region, traffic, instance size, and operating hours. Compare actuals and estimates across each cost dimension, not just the total bill.

With the in-console calculator, you can import historical usage to build workload estimates and bill estimates. With the public calculator, collect historical metrics manually and enter them as usage assumptions.

## 14. Saving, Sharing, Exporting, and Updating Estimates

### 14.1 Public Share Links

The public calculator generates a unique public link for each estimate. Links can be shared with stakeholders or used to reopen the estimate. Estimates are stored on AWS public servers; anyone with the link can access them. Therefore:

- Do not put secrets, credentials, customer PII, or sensitive internal details into descriptions.
- Keep workload and group names appropriate for the sharing audience.
- Record the link in project documentation along with creation date, owner, and assumptions.
- After editing an estimate, generate a new link because edits do not overwrite old links.
- Check link expiration; links created on or after May 31, 2023 remain valid for one year per current AWS documentation.

### 14.2 Exporting CSV/PDF

In My estimate, choose Export and export CSV or PDF. CSV is ideal for aggregation, pivoting, comparing services/groups, or importing into review spreadsheets. PDF is suitable for stakeholder distribution and includes the estimate's share link.

An export is a point-in-time snapshot. If pricing or service configurators change later, downloaded files do not update automatically. Record the export date and calculator version/update status in the estimate record.

### 14.3 Updating Older Estimates

When opening a saved estimate, check its update status:

- **Required inputs:** the service configurator changed and new parameters must be entered.
- **Cost updated:** a pricing model or calculation change affected totals; the calculator may auto-update.
- **Read-only:** older estimates do not support direct updates; the service estimate may need to be recreated.
- **Check for updates:** the group contains services needing review.

After updating, inspect totals and altered assumptions. When saving changes, generate a new share link; the old link does not update automatically.

### 14.4 In-Console Sharing and Access Control

The in-console calculator uses IAM/role permissions and account-level estimate management. This is the better option when estimates contain workload or cost details requiring Organization governance. Verify discount visibility permissions, historical usage read permissions, Cost Explorer access, and account scope before asking member accounts to create estimates.

## 15. From Estimate to FinOps

An estimate delivers the most value when connected to the operational lifecycle:

    Product requirements
          |
    Architecture and usage assumptions
          |
    AWS Pricing Calculator
          |
    Technical + financial review
          |
    Budget / forecast / approval
          |
    Deploy and apply cost allocation tags
          |
    Cost Explorer / CUR / Billing
          |
    Compare estimate vs. actual
          |
    Adjust architecture and forecast

### 15.1 Estimate, Budget, and Forecast Differ

| Concept | Question | Primary Data |
|---|---|---|
| Estimate | How much is the architecture expected to cost under assumptions? | Projected configuration and usage |
| Budget | What is the approved spending limit? | Thresholds and owner |
| Forecast | Given current trends, how much will be spent by period end? | Actual usage, history, and trend |
| Actual cost | How much cost has actually been incurred? | Billing data, Cost Explorer, CUR |

Do not treat an estimate as an approved budget or a forecast measured from actuals. They serve distinct purposes but can be linked together.

### 15.2 Cost Allocation

Apply consistent tags such as Application, Environment, Owner, CostCenter, BusinessUnit, and DataClass. Use AWS Organizations, cost allocation tags, and cost categories to attribute costs to accountable owners. Without tagging from the start, attributing costs accurately after launch becomes difficult.

Estimate groups can mirror cost center or product stack structures for post-deployment reconciliation. However, calculator groups do not automatically become billing tags or cost categories; allocation mechanisms must be configured in Billing.

### 15.3 Comparing Estimate vs. Actual

After the first month:

1. Pull actual costs by service, Region, usage type, and tag.
2. Compare actual quantities against estimated quantities.
3. Classify variance into volume, rate, architecture, discount, timing, or missing service.
4. Update assumptions for the next month.
5. Create owner-assigned actions: rightsize, reduce log volume, adjust retention, change storage classes, optimize NAT/data transfer, or evaluate commitments.

If actuals exceed the estimate, identify the driver before cutting resources. Higher spend may reflect higher traffic and business success; the goal of FinOps is optimizing unit economics and value, not merely shrinking the total bill.

### 15.4 Unit Economics

Beyond total USD/month, calculate cost per business unit:

- Cost per order.
- Cost per active user.
- Cost per API request.
- Cost per GB processed.
- Cost per training job or inference request.
- Cost per tenant/customer.

Example:

    Cost per order = total workload cost / completed orders

If the bill rises 20% while orders grow 50%, cost per order drops. That provides a much better lens for scaling or capacity investment decisions.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Leaving default inputs untouched | Estimate does not reflect workload | Replace with inventory/benchmark figures |
| Selecting the wrong Region | Wrong unit rates, service availability, and transfer | Pick the actual Region; split groups for multi-Region |
| Multiplying max instances × 730 hours | Overestimates autoscaling workloads | Separate baseline and burst-hours |
| Counting only compute | Omits storage, networking, logs, backups | Walk through architecture diagram per dependency |
| Ignoring NAT Gateway | Misses gateway-hours and GB processed | Count NATs per AZ and traffic |
| Ignoring inter-AZ traffic | Misses network costs when scaling across AZs | Measure service-to-service flows |
| Selecting Multi-AZ then adding standby again | Double-counts database | Check what the configurator already includes |
| Entering end-of-month GB instead of average | Wrong GB-month | Model average storage and retention |
| Using request count without duration | Wrong Lambda/compute cost | Gather duration and memory/concurrency |
| Assuming discounts will apply | Estimate lower than actual | Verify rate preferences and eligibility |
| Treating Spot as guaranteed capacity | Risk of interruption and capacity shortage | Use for interruption-tolerant workloads |
| Omitting Marketplace/licenses | Incomplete TCO | Add custom costs or separate adjustment lines |
| Treating an estimate as a quote | Flawed financial decisions | Document assumptions, date, and limitations |
| Failing to save link or export | Estimate cannot be reproduced | Save link, CSV/PDF, owner, and version |
| Not updating older estimates | Prices/inputs may be stale | Check Required inputs/Cost updated/Read-only |

## 17. Lab Exercise: Estimating a Three-Tier Architecture

### Objective

Create an estimate for a web application with frontend, application, database, and storage tiers; model at least one HA option and one cost-optimized option; document assumptions for peer review.

### Preparation

- Choose the target deployment Region.
- Select a sample workload or a benchmarked lab workload.
- Prepare instance counts, running hours, storage, requests, data transfer, and retention.
- Define RPO/RTO, AZ count, and DR requirements.
- Prepare three scenarios: low/base/high.

### Execution

1. Open the public calculator at https://calculator.aws/ and create an estimate.
2. Create groups for Edge, Application, Data, and Operations.
3. Add ALB/CloudFront/Route 53 if used by the architecture.
4. Add EC2 or ECS/Fargate and enter instance/task counts, hours, OS, and storage.
5. Add RDS/Aurora or DynamoDB; select engine/capacity, Multi-AZ, storage, and I/O.
6. Add S3/EBS/EFS by average capacity, requests, retrievals, and retention.
7. Add NAT, data transfer, and appropriate VPC endpoints.
8. Add Lambda/SQS/API Gateway if request-driven processing exists.
9. Add CloudWatch/backups/security based on ingestion, retention, and protected storage.
10. Inspect Show calculation, audit default inputs, and check for double-counting.
11. Create separate groups/estimates for the HA option and the cost-optimized option.
12. Build low/base/high scenarios and compare monthly, upfront, and 12-month totals.
13. Export CSV/PDF, save the share link, and write an assumptions register.

### Deliverables

- Estimate link or exported files.
- Architecture diagram and usage assumptions table.
- Total cost breakdown table by group.
- Comparison of the three scenarios.
- At least the top three drivers impacting total cost.
- Explanation of trade-offs among cost, availability, performance, and security.

### Discussion Questions

1. If traffic doubles while cache hit ratio increases, which cost lines change?
2. When switching to Multi-AZ, which costs increase directly and which depend on traffic?
3. If the application runs continuously, when are commitments worth considering?
4. If the estimate lacks pricing for a component, how will you document and verify that item?
5. After one month in production, what data should be collected to calibrate the estimate?

## 18. Self-Check Questions

**Q1.** Is AWS Pricing Calculator an official quote?

**Answer:** No. It is an estimate based on usage assumptions, does not guarantee actual cost, and does not include all taxes/discounts/third-party licenses.

**Q2.** How do the public calculator and in-console calculator differ?

**Answer:** The public calculator requires no AWS account and focuses on public pricing assumptions. The in-console calculator can use historical usage, discounts, and commitments, and supports workload estimates and bill estimates.

**Q3.** How does a bill estimate differ from a workload estimate?

**Answer:** A workload estimate focuses on a single workload/application; a bill estimate models changes across the consolidated bill and incorporates historical usage and existing commitments, subject to appropriate account/permissions.

**Q4.** Why must you select the Region before configuring services?

**Answer:** Prices, service availability, instance availability, data transfer, and features can differ across Regions.

**Q5.** How many hours per month does the public calculator assume?

**Answer:** 730 hours/month per Pricing Assumptions. This is a convention of 365 days/year divided by 12 months, not the exact hour count of every calendar month.

**Q6.** Does an estimate automatically include taxes and promotional credits?

**Answer:** You should not assume so. The public calculator excludes taxes and does not automatically apply Free Tier/credits/discounts unless explicitly reflected in the configurator.

**Q7.** When estimating EC2, what inputs are needed beyond instance type?

**Answer:** Region, OS, tenancy, instance count, workload pattern, hours, pricing model, EBS, data transfer, monitoring, Elastic IPs, and relevant licenses/add-ons.

**Q8.** Why separate baseline hours and burst-hours?

**Answer:** Maximum instances do not run continuously all month. Separating usage avoids overestimating and supports commitment analysis for the baseline.

**Q9.** In what unit is a Savings Plans commitment expressed?

**Answer:** Spend in USD/hour over the commitment term; eligible usage receives the discounted rate.

**Q10.** Which workloads are suited for Spot?

**Answer:** Workloads that tolerate interruptions, support checkpointing/retries, and do not require continuously available capacity.

**Q11.** Why is NAT Gateway frequently missed?

**Answer:** Architects often calculate EC2 and general data transfer while forgetting gateway-hours and GB processed, especially when deploying NAT across multiple AZs.

**Q12.** Does a Multi-AZ RDS estimate need a separate standby instance added manually?

**Answer:** Only if the configurator does not already include it. Check the configuration and Show calculation to avoid double-counting.

**Q13.** Does end-of-month storage size always equal GB-month?

**Answer:** No. GB-month is based on stored volume over time during the month; use average capacity or time-based modeling.

**Q14.** Does an estimate automatically include Marketplace software licenses?

**Answer:** Not necessarily. Third-party licensing fees may be omitted; add or document them separately.

**Q15.** Does a public estimate link update automatically after edits?

**Answer:** No. After updating an estimate, save and generate a new link; the old link continues pointing to the previous version.

**Q16.** Why should you export CSV?

**Answer:** CSV supports pivoting, comparing services/groups, reviewing assumptions, and reconciling against actual costs.

**Q17.** How do an estimate and a forecast differ?

**Answer:** An estimate uses projected configurations/usage; a forecast uses actuals and trends to project end-of-period spend.

**Q18.** Why is unit economics more useful than total bill for some decisions?

**Answer:** It shows cost per order/user/request and helps distinguish healthy business growth from waste.

## 19. Pre-Submission Estimate Checklist

- [ ] Clearly identify workload, owner, environment, cost center, and Region.
- [ ] Record data sources and update dates for all usage assumptions.
- [ ] Separate known values, assumptions, and unknowns.
- [ ] Verify service availability and pricing models in the selected Region.
- [ ] Enter accurate instance types, OS, tenancy, counts, and hours.
- [ ] Include EBS, S3, EFS/FSx, database storage, I/O, and backups.
- [ ] Include NAT, load balancers, public IPv4, VPC endpoints, and data transfer per path.
- [ ] Include API/requests, Lambda duration, messages, events, and retries.
- [ ] Include log ingestion, metric cardinality, trace sampling, and retention.
- [ ] Check support, Marketplace, licenses, taxes, and non-Calculator items.
- [ ] Compare On-Demand, Spot, RIs/Savings Plans where the workload fits.
- [ ] Review upfront, monthly, and 12-month costs.
- [ ] Build low/base/high scenarios and highlight sensitive drivers.
- [ ] Audit Multi-AZ/DR, dependencies, and double-counting.
- [ ] Document calculator version/date, currency, and assumptions.
- [ ] Export CSV/PDF and save share links in accordance with sharing policies.
- [ ] Obtain technical and financial review before approval.
- [ ] Schedule post-deployment reconciliation of estimate vs. actuals.

## 20. Official References

1. [AWS Pricing Calculator – What is the calculator?](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/what-is-pricing-calculator.html) — capabilities, scope, and public calculator.
2. [Getting started](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/getting-started.html) — access, console structure, and Free Tier assumptions.
3. [Create and configure an estimate](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/create-configure-estimate.html) — workflow for adding and configuring services.
4. [Using groups to organize estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/estimate-groups.html) — grouping by cost center, product stack, and Region.
5. [AWS Pricing Assumptions](https://aws.amazon.com/calculator/calculator-assumptions/) — general assumptions, 730 hours/month, USD, taxes, tiered pricing, and limitations.
6. [Generating Amazon EC2 estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/ec2-estimates.html) — EC2, workload patterns, payment options, EBS, and data transfer.
7. [Sharing your estimate](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/save-share-estimate.html) — public links and updating estimates.
8. [Exporting your estimates](https://docs.aws.amazon.com/pricing-calculator/latest/userguide/export-estimate.html) — CSV/PDF export.
9. [Generating estimates with Pricing Calculator](https://docs.aws.amazon.com/cost-management/latest/userguide/pricing-calculator.html) — distinguishing public and in-console calculators, workload/bill estimates.
10. [AWS Pricing Calculator FAQs](https://aws.amazon.com/aws-cost-management/aws-pricing-calculator/faqs/) — assumptions, discounts, usage history, and commitments.
11. [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html) — pricing data and tracking price changes.
12. [AWS Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html) — commitment scope and mechanisms.
13. [Amazon EC2 pricing](https://aws.amazon.com/ec2/pricing/) — EC2, RI, and Spot pricing models.
14. [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/) — volumes, provisioned performance, and snapshots.
15. [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) — storage classes, requests, retrievals, and transfer.
16. [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/) — DB instances, storage, I/O, and deployment options.
17. [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) — NAT Gateway, endpoints, and data processing.
18. [AWS Data Transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer) — distinguishing transfer paths.
19. [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) — analyzing actual costs and usage.
20. [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html) — granular cost data for estimate reconciliation.

---

**Conclusion:** A reliable estimate starts from the workload model, not from the calculator's default values. Account for all services and dependencies, choose the right Region and pricing model, document assumptions, compare scenarios, and audit commonly missed items. After deployment, reconcile estimates against actual costs to turn initial estimation into a continuous FinOps loop.
