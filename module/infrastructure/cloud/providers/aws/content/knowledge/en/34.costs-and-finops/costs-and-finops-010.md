# Compute Optimizer and Resource Rightsizing

An AWS workload can run smoothly while still costing far more than necessary. An EC2 instance provisions 16 vCPUs while the application uses only a small fraction; an EBS volume provisions higher IOPS than needed; a Lambda function allocates excessive memory; or an ECS service on Fargate keeps large task sizes despite low actual load. Conversely, downsizing too aggressively can increase latency, timeouts, errors, and operational costs.

**Rightsizing** is the process of matching resource types and sizes to actual workload demand at a reasonable cost. It is not simply picking the smallest configuration. A sound configuration maintains enough headroom for peaks, growth, traffic spikes, and latency and availability requirements.

**AWS Compute Optimizer** analyzes resource configurations and utilization data to generate optimization recommendations. The service identifies resources that may be over-provisioned, under-provisioned, optimized, or lacking sufficient data to conclude. Operators can review options, performance risk levels, utilization graphs, and estimated savings before deciding on changes.

In the **CLOUD_PROVIDERS_AWS** ecosystem, Compute Optimizer supports FinOps practices with measured telemetry rather than guesswork. This module aims to help learners select services and design and deploy applications safely with observability, resilience, and cost control. Therefore, recommendations must be combined with business context, SLOs, load schedules, architecture, actual purchase pricing, and controlled change management.

## 1. What Problem Does Rightsizing Solve?

Oversized resources waste fixed or hourly spend. Undersized resources bottleneck CPU, memory, IOPS, throughput, or networking. Both hurt business outcomes:

- Over-provisioning forces organizations to pay for unused capacity.
- Under-provisioning raises latency, errors, queue backlogs, processing durations, and SLO breach risk.
- Choosing the wrong resource family can create bottlenecks even when vCPU counts or total capacity look adequate.
- Idle resources continue incurring charges without delivering value.

For example, a database server averages 8% CPU while memory remains nearly full and swap climbs. Downsizing solely on CPU could starve the database of memory. A `gp2` volume with low average IOPS might regularly exhaust its burst balance; shrinking the volume could worsen performance. Rightsizing must inspect all relevant resource dimensions, not just one metric.

### Principles

1. Use an observation window long enough to capture normal load and peaks.
2. Inspect averages, maximums, percentiles, and trends over time.
3. Preserve headroom aligned with SLOs and growth rates.
4. Verify dependencies, quotas, licenses, CPU architecture, and storage characteristics.
5. Test changes via canary or small batches first.
6. Measure cost and performance post-change, then update the baseline.

## 2. How Does AWS Compute Optimizer Work?

Compute Optimizer is a managed analytical service. Once an account opts in, it evaluates configuration metadata and utilization metrics for supported resource types, producing findings and one or more recommendation options.

General workflow:

~~~mermaid
flowchart TD
    A[Opt in to Compute Optimizer] --> B[Read resource configurations]
    B --> C[Analyze CloudWatch and supported telemetry]
    C --> D[Evaluate workload over lookback period]
    D --> E[Findings and recommendation options]
    E --> F[Assess performance risk and savings]
    F --> G[Owner validates context]
    G --> H[Test and apply controlled changes]
    H --> I[Monitor metrics and cost post-change]
~~~

Compute Optimizer does not predict every future traffic shift with certainty. Recommendations primarily reflect historical configurations and usage during the analysis window. Operators must layer in product launches, peak seasons, batch jobs, growth, special events, and recovery requirements.

### A Recommendation Is Not a Change Order

Recommendations are decision-support inputs. Operations teams must verify compatibility, evaluate risk, pick deployment windows, and prepare rollbacks. Some accounts/Regions can enable Compute Optimizer Automation to apply supported recommended actions, though automated actions do not cover all rightsizing recommendation types.

## 3. Enabling Compute Optimizer and Managing Multiple Accounts

Compute Optimizer requires opting in. It can be enabled per standalone account or managed at the AWS Organizations level through the management account and a delegated administrator under the supported model.

A multi-account organization should:

1. Designate a dedicated FinOps or Security/Platform account as delegated administrator where appropriate.
2. Opt in to Compute Optimizer in the Regions to be analyzed.
3. Enroll member accounts and verify enrollment status.
4. Grant required read permissions for resource configurations and CloudWatch metrics.
5. Enable Cost Explorer so Compute Optimizer has billing data for pricing and savings estimates.
6. Consider opting in to Cost Optimization Hub to view rightsizing recommendations alongside active Savings Plans and Reserved Instances.
7. Build dashboards or export recommendations to track progress by account, Region, application, and owner.

Compute Optimizer is Regional for its recommendations. Enabling one Region does not cover other Regions. Verify enrollment and coverage in every Region across the organization.

### Access Permissions

Separate recommendation read access from resource modification permissions. FinOps analysts may need read access to recommendations and billing; workload owners need visibility into their team's resources; deployment roles hold actual rights to modify instance types, volumes, or memory settings. Never grant broad administrative permissions just to view reports.

## 4. Supported Resource Types

Compute Optimizer's scope extends beyond EC2. However, each resource type has distinct recommendation types and eligibility requirements. Distinguish **rightsizing recommendations** from **idle resource recommendations**.

| Resource | Typical Recommendations | Optimization Scope |
|---|---|---|
| EC2 instances | Rightsizing and idle | Instance family/type, vCPU, memory, architecture, and performance |
| EC2 Auto Scaling groups | Rightsizing and idle | Instance types aligned with group config and scaling policies |
| EBS volumes | Rightsizing and idle/unattached | Volume type, size, IOPS, throughput, or idle volume detection |
| Lambda functions | Memory rightsizing | Memory sizing balanced against duration and workload |
| ECS services on Fargate | Task/container CPU and memory | Task size and container resource settings |
| RDS DB instances and Aurora | Instance and storage recommendations | Compute, storage, IOPS, and throughput by database type |
| Commercial software licenses | License recommendations | Microsoft SQL Server on EC2 under supported conditions |
| NAT Gateway | Idle | Detects low-utilization gateways per service criteria |
| DynamoDB provisioned tables | Idle | Provisioned tables showing inactivity signals |
| ElastiCache, MemoryDB, DocumentDB | Idle | Low- or unused clusters/databases per supported criteria |
| WorkSpaces and SageMaker endpoints | Idle | Underutilized or idle resources |

The list of supported resources and recommendation types evolves over time. Some resources in the table receive only idle recommendations; do not assume Compute Optimizer generates configuration-change recommendations for every one of them.

## 5. Lookback Periods and Data Quality

By default, Compute Optimizer analyzes utilization over the last 14 days. With Enhanced Infrastructure Metrics enabled for eligible resource types, the lookback window extends up to 93 days. Enhanced Infrastructure Metrics is a paid feature; weigh the value of longer history against budget.

Recommendations typically refresh daily. After opting in or when insufficient data exists, generating recommendations can take roughly 24 hours or longer depending on the resource and telemetry conditions.

For many resource types such as EC2, Auto Scaling, EBS, and Lambda, Compute Optimizer evaluates the maximum utilization data point in each 5-minute interval of the lookback period. For ECS services on Fargate, it uses the maximum utilization point in each 1-minute interval. This helps capture short load spikes, though operators should still inspect percentiles and raw metrics in CloudWatch.

### Example Data Requirements

| Resource | Typical Requirement to Generate Recommendations |
|---|---|
| EC2 and Auto Scaling groups | At least 30 hours of CloudWatch metric data in the last 14 days; Enhanced Infrastructure Metrics extends lookback up to 93 days for eligible resources |
| EBS volumes | Volume must be attached to a running EC2 instance for at least 30 consecutive hours; CloudWatch data exists only while attached to a running instance |
| Lambda | For memory recommendations, function needs at least 50 invocations in 14 days and configured memory not exceeding 1,792 MB; Lambda does not rely on EC2-style CloudWatch metrics |
| ECS services on Fargate | Needs at least 24 hours of CloudWatch/ECS utilization metrics in 14 days; step scaling or simultaneous CPU and memory target tracking can restrict recommendations |
| RDS/Aurora | DB instance needs at least 30 hours of CloudWatch metrics in 14 days; some recommendations require Performance Insights or Aurora cluster-specific criteria |

Exact thresholds and conditions vary by resource type. When recommendations do not appear, check resource requirements, metric coverage, instance types, Region, and enrollment status before concluding a resource has no optimization opportunities.

For ECS Fargate, if a service uses target tracking solely on CPU, Compute Optimizer may recommend only memory; if solely on memory, it may recommend only CPU. If scaling policies target both dimensions or use step scaling, rightsizing recommendations may not be generated. For Aurora DB cluster storage, additional requirements apply such as sufficient cost history and absence of certain cluster configurations.

### Historical Data Is Not a Forecast

A 14-day lookback may miss monthly, quarterly, or seasonal cycles. An invoicing system that peaks heavily at month-end can be dangerously downsized if the analysis window misses that peak. For variable workloads, use longer lookback windows where appropriate and cross-check business calendars.

## 6. Understanding Findings, Recommendations, and Performance Risk

Compute Optimizer may classify findings as:

- **Over-provisioned:** resource capacity exceeds observed demand; downsizing can cut costs.
- **Under-provisioned:** resource risks failing to meet demand; scaling up or changing configuration may improve performance.
- **Optimized:** current configuration matches requirements and observed telemetry.
- **Not optimized / Unavailable:** some resource types or cases use specific statuses when data is insufficient or reliable recommendations cannot be generated.

Exact labels and statuses vary by resource type. Never apply a single uniform classification scheme blindly across EC2, Lambda, ECS, EBS, and RDS.

### Performance Risk

Performance risk indicates the likelihood that a recommended configuration fails to meet workload demand under the evaluation model. Depending on page and resource type, risk levels range from Very low to High.

Do not pick a recommendation solely for highest savings. Compare:

| Criterion | Question |
|---|---|
| Estimated monthly savings | How much is estimated to be saved, and on what pricing basis? |
| Performance risk | Could the new configuration run short on CPU, memory, IOPS, or throughput? |
| Utilization graph | Does the recommendation preserve adequate headroom during peak intervals? |
| Compatibility | Is the application compatible with the CPU architecture, OS, drivers, licenses, and storage? |
| Operational impact | Does the change require a restart, redeploy, failover, or downtime? |
| Future demand | Will upcoming load differ from the lookback window? |

## 7. Optimizing EC2 Instances

Compute Optimizer analyzes EC2 configurations and utilization to suggest better-fitting instance types. Depending on workload and available metrics, dimensions include CPU, memory, networking, EBS throughput, GPUs, and related performance telemetry.

### CPU Is Not the Only Metric

An instance with low average CPU may still need to keep or increase its size if:

- Memory utilization is high or swapping occurs frequently.
- Network throughput nears limits.
- EBS throughput or IOPS is saturated.
- GPU utilization or GPU memory is high.
- The application requires short CPU bursts.
- The workload enforces strict latency or tail-latency targets.

Compute Optimizer does not automatically receive memory metrics for every EC2 instance. To analyze memory, install and configure the CloudWatch Agent to emit appropriate metrics. On Linux, metrics such as `mem_used_percent` in the `CWAgent` namespace can be used; on Windows, configure appropriate memory metrics such as `Available MBytes`. Check documentation for your OS and agent version.

For example, Linux can collect `mem_used_percent` under `CWAgent` or legacy `MemoryUtilization` under `System/Linux`. On Windows, Compute Optimizer can use `Available MBytes` under `CWAgent`; configure the agent to match how each OS reports memory.

### Choosing Instance Families

Do not compare only vCPU and RAM counts. Instance families differ across:

- CPU architecture and instruction sets.
- Network bandwidth and packet-per-second performance.
- EBS bandwidth.
- Local NVMe/instance store.
- GPUs, accelerators, and memory bandwidth.
- Architecture-dependent licensing and software support.

Compute Optimizer does not generate EC2 rightsizing recommendations for Spot Instances and supports only published instance types. If an instance shows no recommendation, check its instance type and eligibility before troubleshooting metrics.

If Compute Optimizer recommends Graviton, verify binaries, container images, runtimes, native dependencies, and multi-architecture build pipelines. For Windows or commercial software workloads, verify licensing and vendor support before switching families.

### Burstable Instances

For the T family, CPU credits and baseline performance directly affect behavior. A configuration with low average CPU that bursts regularly can exhaust CPU credits after downsizing. Inspect `CPUCreditBalance`, `CPUCreditUsage`, Unlimited mode settings, and surplus credit charges before resizing.

### Evaluating Peaks and Headroom

Inspect maximum and percentile charts, not just averages. A system averaging 15% CPU while spiking to 95% during batch windows may need to retain capacity or reschedule batches. Recommendations must handle business-acceptable peaks, not merely average load.

## 8. Optimizing EC2 Auto Scaling Groups

For Auto Scaling groups, Compute Optimizer can suggest instance types and certain idle opportunities based on group configuration. Recommendations may depend on whether the group uses a single instance type, mixed instances, CPU-based scaling policies, or scheduled scaling.

Key points:

- An instance type recommendation does not automatically adjust `min`/`max`/`desired` capacity or scaling policies.
- Mixed instances policies carry constraints on families, architectures, platforms, and allocation strategies.
- Certain combinations of Spot, instance families, or workloads may not qualify for rightsizing recommendations.
- Groups backing ECS/EKS may have different constraints than standalone EC2 groups.

When applying instance type changes, you can use EC2 Auto Scaling instance refresh with an appropriate rolling strategy. Tune minimum healthy percentage, warm-up, health checks, and checkpoints; preserve rollback readiness by retaining prior configurations.

## 9. Optimizing EBS Volumes

Compute Optimizer can recommend changes to volume type, size, IOPS, or throughput for supported EBS volumes. For example, `gp2` volumes may be candidates for `gp3`; `io1`/`io2` volumes may have over-provisioned IOPS; low-throughput volumes may suit different settings.

Metrics to inspect:

- Read/write operations and IOPS.
- Read/write throughput.
- Burst balance for burstable volume types.
- IOPS exceeded checks and throughput exceeded checks where supported.
- Attachment status and usage duration.

### Example: Choosing Between gp2 and gp3

`gp2` ties IOPS to volume size and relies on burst buckets. `gp3` decouples storage capacity from provisioned IOPS/throughput, allowing independent tuning within service limits. Moving from `gp2` to `gp3` can lower costs or improve tunability, provided you verify whether the workload requires IOPS/throughput above `gp3` defaults.

Do not shrink volume sizes merely because most space is unused. Account for growth rate, log retention, temporary files, backup staging, database expansion, and future headroom.

### Idle or Unattached Volumes

Unattached volumes or volumes with minimal activity may generate idle recommendations. Before deleting:

1. Identify owner, tags, and former workload.
2. Check attachment history and idle duration.
3. Confirm data is not a recovery copy, forensic evidence, or standby volume.
4. Take a snapshot if policy requires.
5. Verify snapshot completion and KMS decryption key availability.
6. Delete the volume via change management and track ongoing snapshot storage costs.

Never delete a volume based solely on an idle finding. It may be retained for DR, audit, or periodic recovery procedures.

## 10. Optimizing AWS Lambda

Compute Optimizer generates memory size recommendations for eligible Lambda functions. In Lambda, memory settings scale CPU power and other execution resources. Increasing memory can make functions finish faster; even with a higher per-millisecond rate, shorter duration can reduce or equalize total invocation cost.

Evaluate:

- Current configured memory.
- Duration p50/p95/p99.
- Error and timeout rates.
- Invocation counts and concurrency.
- Cold starts and deployment package size.
- Cost across invocations and GB-seconds.

Memory recommendations do not mean every function should run at minimum memory. Image processing, encryption, or compute-heavy functions may benefit from higher CPU/memory; network-bound functions may see minimal speedup from extra memory.

Under current Compute Optimizer rules, functions configured above 1,792 MB may receive `Unavailable`/`Inconclusive` findings and omit recommendations. Therefore, seeing no recommendation does not prove a function is already optimized.

After changing memory, test with realistic payloads and concurrency. Monitor duration, errors, throttling, and cost per successful invocation. For sensitive functions, deploy via versions/aliases and traffic shifting to roll back if latency or errors spike.

## 11. Optimizing ECS Services on Fargate

Compute Optimizer generates task-size and container-size recommendations for ECS services on Fargate. Primary metrics are CPU utilization and memory utilization.

Findings can flag over-provisioned or under-provisioned CPU or memory. Task-level and container-level recommendations must align: total container resource reservations must fit within task size.

Some scaling policies restrict recommendation types. For instance, services using target tracking on both CPU and memory or step scaling may have limited recommendation scope. Review ECS service requirements before assuming no optimization exists.

When applying changes:

1. Compare current vs. recommended task CPU/memory.
2. Check container CPU shares, memory reservations, and memory limits.
3. Inspect peak utilization and minimum task counts.
4. Verify service autoscaling, deployment configuration, and health checks.
5. Roll out the new task definition via rolling deployment.
6. Monitor task restarts, OOM events, latency, and desired/running counts.

Never trim task memory right down to average utilization. Brief load bursts or memory spikes can trigger OOM kills and continuous task restart loops.

## 12. Optimizing Amazon RDS and Aurora

Compute Optimizer supports selected Amazon RDS and Aurora resources, including recommendations for DB instances, RDS DB instance storage, and Aurora DB cluster storage under supported engines and conditions.

Analyzed metrics can include:

- CPU utilization.
- Database connections.
- Network receive throughput.
- Read/write IOPS and throughput.
- Free storage space.
- Database load and OS metrics when Performance Insights or equivalent observability is enabled.
- Aurora cluster I/O usage and storage spend.

For certain RDS DB instances, Performance Insights must be enabled for Compute Optimizer to recommend vCPU reductions. Requirements and database observability feature names vary by engine and service version; verify current RDS/Aurora documentation.

### Do Not Look Only at CPU

A database with low CPU but high DB load may be bottlenecked by locks, I/O, connections, or poor query plans. Shrinking the DB instance class can worsen symptoms. Before changing a DB instance class:

1. Inspect Database Insights/Performance Insights, DB load, and wait events.
2. Inspect connection pools, query latency, and slow queries.
3. Inspect memory, cache hit ratio, IOPS, throughput, and free storage.
4. Verify read replicas, Multi-AZ, and failover behavior.
5. Verify engine/version compatibility for target instance classes.
6. Plan maintenance windows, snapshots, and rollbacks.

For Aurora, separate instance compute from cluster storage. Storage recommendations relate to I/O and cluster storage costs; resizing instance classes and optimizing storage are two distinct decisions.

## 13. Recommendation Preferences and Headroom

Compute Optimizer lets you customize certain recommendation preferences, such as:

- CPU utilization headroom and thresholds.
- Memory utilization headroom.
- Lookback periods.
- Instance family preferences.
- CPU architecture choices or recommendation scope across organization/account/Region.

Headroom represents the safety buffer an organization chooses to retain. Workloads with strict latency or sharp bursts need higher headroom. Deferrable, easily scaled batch workloads can tolerate higher utilization.

Never set headroom artificially low just to inflate estimated savings. Base settings on SLOs, peaks, scale-out times, cold starts, quotas, and ramp rates. Recommendation preferences adjust how the model evaluates options; they never replace real testing.

## 14. Savings Estimates and FinOps Integration

Compute Optimizer displays estimated monthly savings and price comparisons across many recommendations. These are estimates grounded in usage assumptions, list/contracted rates, and available billing data—not guaranteed savings.

To interpret savings estimates properly:

1. Check the account/Region and purchasing option used.
2. Confirm Cost Explorer is enabled and billing data is populated.
3. Account for active Savings Plans or Reserved Instances.
4. Check Cost Optimization Hub to compare recommendations alongside existing discounts/commitments.
5. Factor in migration effort, downtime, testing, and licensing costs.
6. Measure actual billing post-change.

### On-Demand vs. Discounts

A recommendation may quote savings at On-Demand rates while actual cash savings are smaller if the resource is already covered by a Savings Plan or Reserved Instance. Conversely, rightsizing can free up commitment capacity to cover other workloads. Never decide solely from the hourly rate difference between two instance types.

Some estimation modes incorporate account-specific discounts when enabled; otherwise, savings estimates may reflect On-Demand rates or the selected purchasing option. When building a business case, reconcile with Cost Explorer, Cost Optimization Hub, and actual workload bills.

### Cost Optimization Hub

Cost Optimization Hub consolidates optimization opportunities from multiple sources, including rightsizing, idle resources, Savings Plans, and Reserved Instances. Compute Optimizer focuses deeply on resource configuration and utilization; Cost Optimization Hub frames those opportunities within the broader spend picture. The two services complement each other.

## 15. Recommendation Evaluation and Implementation Workflow

A controlled seven-step FinOps workflow:

1. **Discover:** export recommendations by account, Region, resource type, tag, and owner.
2. **Validate data:** verify lookback window, metric coverage, peaks, seasonality, and resource state.
3. **Assess business impact:** evaluate criticality, SLOs, maintenance windows, DR tiers, and dependencies.
4. **Prioritize:** rank by savings, performance risk, effort, blast radius, and confidence.
5. **Test:** validate in development/staging or canary with load tests and synthetic transactions.
6. **Implement:** apply changes via IaC, deployment pipelines, or approved change management.
7. **Measure:** compare actual cost, latency, errors, utilization, and realized savings post-change.

### Example Prioritization Matrix

| Opportunity | Savings | Performance Risk | Effort | Reference Priority |
|---|---|---|---|---|
| Over-provisioned non-prod EC2 with steady metrics | High | Low | Low | High |
| Unattached EBS volume confirmed by owner | Medium | Low after snapshot | Low | High |
| Slightly oversized Lambda memory, easily testable | Medium | Low with good canary | Low | High |
| Production RDS with high DB load, vCPU reduction suggested | High | Medium/High | High | Needs deep investigation |
| ECS service with peak memory near limit | Low if downsized | High | Medium | Do not downsize |

Never prioritize solely by dollar savings. A risky production database tweak may warrant deferral, while an easy-to-revert dev improvement with moderate savings can ship immediately.

## 16. Applying Recommendations with Automation

AWS Compute Optimizer offers Automation to apply certain recommended actions directly or on recurring rules. Automation rules can be scoped by Region, resource tag, action type, and daily/weekly/monthly schedules, tracking automation events, execution steps, savings estimates, and supported rollback actions.

Currently documented automated actions focus on specific EBS operations, such as:

- Snapshotting and deleting eligible unattached EBS volumes.
- Upgrading certain older volume types to supported newer types.

Do not assume every EC2 instance type, Lambda memory, ECS task size, or RDS instance class recommendation can be auto-applied by Compute Optimizer Automation. Check the current supported action types in your Region/account.

### Guardrails Before Enabling Automation

- Enable only after owners understand service-linked role permissions and which resources can be modified.
- Scope rules tightly by tag, Region, lookback period, and specific action types.
- Use opt-out tags to exclude sensitive resources from automation.
- Exclude IaC-managed resources if automated edits cause drift, or establish workflows to sync the source of truth.
- Preview matching resources/actions before activating rules.
- Start in pilot accounts/Regions and off-peak maintenance windows.
- Monitor event status, step history, savings, and workload impact.
- Verify rollback mechanics for each action; never assume single-click rollback exists for everything.

Automation eliminates repetitive work, yet misconfigured rules can cause broad unintended changes. Rules lacking tight criteria can modify resources across unexpected Regions and accounts. Treat automation rules like production changes.

## 17. Querying Recommendations with AWS CLI

After opting in, use the AWS CLI to fetch recommendations. Example enabling enrollment for the active account/Region:

~~~bash
aws compute-optimizer update-enrollment-status \
  --status Active \
  --region ap-southeast-1
~~~

Fetch recommendations for an EC2 instance:

~~~bash
aws compute-optimizer get-ec2-instance-recommendations \
  --instance-arns "arn:aws:ec2:ap-southeast-1:111122223333:instance/i-0123456789abcdef0" \
  --region ap-southeast-1
~~~

Fetch recommendations for an EBS volume:

~~~bash
aws compute-optimizer get-ebs-volume-recommendations \
  --volume-arns "arn:aws:ec2:ap-southeast-1:111122223333:volume/vol-0123456789abcdef0" \
  --region ap-southeast-1
~~~

ARNs above are illustrative. Callers need appropriate IAM permissions and must query the exact Region. APIs return detailed recommendation options; use `--query`/`--output` to extract needed fields rather than dumping huge payloads into logs.

Use the corresponding APIs for Lambda, ECS, Auto Scaling, and RDS. When building reports, handle pagination and ineligible-resource errors; never treat an empty response as proof that a resource is already optimal.

## 18. Real-World Example: Rightsizing an Orders Platform

An e-commerce platform runs APIs on an EC2 Auto Scaling group, workers on ECS Fargate, invoice assets on EBS-backed EC2, databases on RDS, and image processing on Lambda. FinOps wants to reduce spend without impacting flash-sale peaks.

### Analysis

1. EC2 API instances show low average CPU but spike sharply during flash sales. The team enables memory metrics via CloudWatch Agent and uses a longer lookback to capture multiple cycles.
2. The Auto Scaling group uses a mixed instances policy. The team checks CPU architecture, platform, and allocation strategy before applying family recommendations.
3. ECS workers show low memory utilization, yet queue backlogs spike periodically. The team inspects queue age and concurrency to determine whether task size can shrink or headroom must stay.
4. RDS CPU is low, while DB load and connections are high. The team investigates wait events and queries before downsizing the DB class.
5. Image-processing Lambda runs at 1,024 MB with long duration. The team tests higher memory on a canary alias to measure duration and cost per image.
6. An unattached EBS volume is confirmed unneeded by its owner. The team snapshots it per policy before deletion.

### Change Plan

| Resource | Decision | Guardrails |
|---|---|---|
| EC2 API | Test new instance types on part of the ASG | Instance refresh, health checks, peak testing, rollback |
| ECS workers | Tune task size service by service | Monitor OOMs, queue age, task restarts |
| RDS | Hold off on downsizing; investigate DB load | Query analysis, snapshots, maintenance window |
| Lambda | Canary memory configuration | Compare duration, errors, and cost per image |
| Unattached EBS | Snapshot then delete after approval | Verify owner, retention, and KMS |

After each change, compare actual costs and performance under equivalent load. Comparing a quiet week against a flash-sale week produces misleading savings figures.

## 19. FinOps Governance and Measurement

To make rightsizing continuous, organizations need clear ownership and metrics.

### Ownership

- FinOps team owns the process, reporting, and prioritization.
- Platform team owns guardrails, IaC, deployment pipelines, and automation.
- Application owners validate traffic, SLOs, and change tolerance.
- Database owners evaluate queries, storage, and failover behavior.
- Security team reviews IAM, automation roles, auditing, and tagging.

### Metrics to Track

| Metric | Meaning |
|---|---|
| Recommendation coverage | Share of resources within analytical scope |
| Actionable recommendation rate | Share of recommendations with sufficient data and an assigned owner |
| Estimated savings | Total projected savings prior to implementation |
| Realized savings | Actual savings after normalizing for usage/discounts |
| Adoption rate | Share of recommendations acted upon |
| Reversal / rollback rate | Share of changes requiring rollback |
| Performance regression | Changes causing higher latency, errors, or lower throughput |
| Idle resource backlog | Unremediated idle resources |
| Time to action | Elapsed time from recommendation to decision and rollout |

Never incentivize teams purely on estimated savings. If downsizing causes outages or errors, business losses easily outweigh infrastructure savings. Evaluating cost per successful transaction, per customer, or per workload unit reflects true value much better.

## 20. Common Mistakes

### Looking Only at Average CPU

Memory, networking, EBS, GPUs, IOPS, and peaks may be the true bottleneck. Collect full metrics and inspect percentiles.

### Using Too Short a Lookback for Seasonal Workloads

Recommendations can miss month-end batches or peak sales. Use longer lookbacks and overlay business calendars.

### Treating Estimated Savings as Guaranteed Cash Savings

On-Demand pricing, Savings Plans, Reserved Instances, credits, and discounts alter outcomes. Measure actual billing after changes.

### Downsizing Databases Purely Due to Low CPU

DB load, memory, connections, I/O, and wait events may be constraining performance. Investigate thoroughly before changing DB classes.

### Ignoring CPU Architecture

Switching from x86 to Graviton requires checking binaries, runtimes, container images, and licenses.

### Changing Many Resources Simultaneously

Pinpointing root causes becomes difficult if latency or errors spike. Use canaries and phased rollouts.

### Auto-Applying Recommendations Organization-Wide

Broad automation rules can alter unintended resources or trigger IaC drift. Use tight criteria, previews, opt-out tags, and pilot accounts.

### Deleting Idle Volumes Without Owner Confirmation

Volumes may hold backups, forensic evidence, or DR data. Confirm ownership and snapshot per policy.

### Failing to Measure Post-Change Outcomes

FinOps impact cannot be proven merely by closing recommendation tickets. Compare cost, performance, and reliability before and after.

## 21. Compute Optimizer Implementation Checklist

- [ ] Compute Optimizer is opted in for target accounts and Regions.
- [ ] AWS Organizations and delegated administrator are configured for multi-account management.
- [ ] Cost Explorer is enabled for pricing context and savings estimates.
- [ ] Resources have sufficient metric data and meet eligibility criteria.
- [ ] Lookback periods match workload seasonality and cycles.
- [ ] EC2 instances report memory metrics where memory evaluation matters.
- [ ] Finding classifications, performance risks, and options have been reviewed.
- [ ] Resources have owners, tags, criticality ratings, and SLOs.
- [ ] CPU architecture, licenses, networking, EBS, and dependencies are verified.
- [ ] Savings Plans, Reserved Instances, and actual discounts are factored in.
- [ ] Changes are tested via canary or staging environments.
- [ ] Backups/snapshots and rollback plans are in place.
- [ ] Automation applies only supported actions under narrow criteria.
- [ ] IaC sources of truth are updated to prevent drift.
- [ ] CloudWatch alarms monitor latency, errors, utilization, and saturation post-change.
- [ ] Actual savings and cost per business unit are measured after rollout.

## 22. Key Takeaways

AWS Compute Optimizer analyzes configurations and utilization metrics to produce rightsizing and idle-resource recommendations across supported resource types. Recommendation quality depends on metric coverage, lookback duration, resource eligibility, and workload context.

Rightsizing must balance savings against performance risk. Inspect CPU, memory, networking, IOPS, throughput, queues, database load, and peaks; verify architecture compatibility, licensing, and dependencies; and roll out changes incrementally with canaries, monitoring, and rollback plans. Always reconcile estimated savings against purchasing options, Savings Plans, Reserved Instances, and actual billing.

Compute Optimizer Automation can apply certain supported actions, provided it is governed by narrow rules, least-privilege permissions, previews, and monitoring. FinOps creates lasting value only when cost savings preserve SLOs, reliability, and user experience.

## References

- [What is AWS Compute Optimizer?](https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html)
- [AWS Resources Supported by Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html)
- [Resource Requirements](https://docs.aws.amazon.com/compute-optimizer/latest/ug/requirements.html)
- [Metrics Analyzed by AWS Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/metrics.html)
- [Viewing EC2 Instance Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ec2-recommendations.html)
- [EC2 Instance Metrics Analyzed](https://docs.aws.amazon.com/compute-optimizer/latest/ug/ec2-metrics-analyzed.html)
- [Viewing EBS Volume Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ebs-recommendations.html)
- [Viewing Lambda Function Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-lambda-recommendations.html)
- [Viewing ECS Services on Fargate Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ecs-recommendations.html)
- [Viewing Aurora and RDS Database Recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-rds-recommendations.html)
- [Rightsizing Recommendation Preferences](https://docs.aws.amazon.com/compute-optimizer/latest/ug/rightsizing-preferences.html)
- [Apply Optimization Recommendations Using Automation](https://docs.aws.amazon.com/compute-optimizer/latest/ug/automation.html)
- [Automation Rules](https://docs.aws.amazon.com/compute-optimizer/latest/ug/automation-rules.html)
- [Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html)
- [AWS Compute Optimizer Pricing](https://aws.amazon.com/compute-optimizer/pricing/)
