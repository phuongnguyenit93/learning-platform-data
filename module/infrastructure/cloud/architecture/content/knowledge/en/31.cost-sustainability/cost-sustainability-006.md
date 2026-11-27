# Comparing Managed Service Costs vs. Self-Managed Costs

## 1. Why You Cannot Compare Service Prices Alone

When designing a cloud architecture, teams often weigh using a managed service against self-managing software on VMs, containers, or Kubernetes. Managed services usually charge more per unit of resource or request, while the provider handles parts of provisioning, patching, backups, failover, and control plane operations. Self-managing may cut certain service fees, while shifting deployment, upgrades, security, monitoring, and incident response responsibilities onto the internal team.

Comparing the hourly price of a managed database against the VM price to run a database misses most of the cost. You must compare **Total Cost of Ownership (TCO)** across the exact same workload scope, service level, evaluation horizon, and operational obligations.

TCO should include:

- **Direct costs:** compute, storage, network, licenses, requests, backups, replication, and support.
- **Labor costs:** design, implementation, patching, on-call, incident response, upgrades, and capacity planning.
- **Tooling costs:** monitoring, security scanning, backup tooling, orchestration, automation, and observability.
- **Risk costs:** downtime, data loss, security incidents, SLA credits, and recovery.
- **Flexibility costs:** ability to scale up/down, switch regions, migrate, and avoid lock-in.
- **Opportunity costs:** engineering time spent running infrastructure instead of building product features and business value.

In the **CLOUD_ARCHITECTURE** module, the **Cost and Sustainability** chapter treats the managed vs. self-managed decision as a trade-off across cost, operational responsibility, reliability, security, scalability, and resource efficiency.

After this lesson, learners can:

1. Distinguish managed services, self-managed setups, and intermediate service models.
2. Build TCO comparisons across identical workloads, SLOs, capacity, and evaluation horizons.
3. Calculate direct, labor, tooling, reserve, and risk costs.
4. Estimate break-even points by usage scale and operational effort.
5. Compare responsibilities for security, patching, backups, HA, and compliance.
6. Evaluate elasticity, utilization, lock-in, and switching capability.
7. Select a model suited to workload, team skills, and business value.
8. Plan migrations, testing, and post-deployment cost reviews.

## 2. What Are Managed Services and Self-Managed Setups?

### 2.1. Managed Services

A managed service is a service where the provider operates part or most of the underlying platform. Customers configure and consume the service through an API, console, or control plane.

Examples:
- Managed relational databases.
- Managed Kubernetes control planes.
- Managed message brokers.
- Managed caches.
- Managed object storage.
- Managed search/analytics engines.
- Managed identity or observability platforms.

Depending on the service and tier, the provider may handle hardware, host OS, control plane, patching, or backups. Customers typically remain responsible for data, IAM, network access, configuration, applications, quotas, key policies, and how the service is used.

### 2.2. Self-Managed

Self-managed means the organization deploys and operates software on compute/storage/networking under its own control. This can run on VMs, bare metal, container platforms, or Kubernetes.

Examples:
- Installing PostgreSQL on VMs and managing replication/backups yourself.
- Running a Kafka cluster on Kubernetes.
- Operating a Redis cluster.
- Running an Elasticsearch/OpenSearch cluster.
- Managing ingress, certificates, monitoring, and upgrades yourself.

Self-managed does not mean building your own hardware. The cloud provider still operates the data center, physical network, and hypervisor; the organization takes on additional responsibility at the software/platform layer.

### 2.3. Intermediate Models

In practice, there is a spectrum of options:

| Model | Provider Handles | Internal Team Handles |
| --- | --- | --- |
| Fully managed | Infrastructure and most platform operations | Data, access, configuration, workloads |
| Managed control plane | Control plane/coordination | Worker nodes, add-ons, workloads |
| Hosted software | Host runtime or hardware per contract | App config, data, supported-level upgrades |
| Self-managed on cloud | Physical cloud infrastructure | OS, software, HA, backups, patches, monitoring |
| Self-hosted on-prem | Hardware potentially managed by the organization | Most of the stack from data center to application |

Labels alone are not enough to define responsibilities. Read the service boundary, SLA, maintenance policy, support plan, and shared responsibility model of the specific service.

## 3. Comparing Operational Responsibilities

| Activity | Managed Service | Self-Managed |
| --- | --- | --- |
| Data center/hardware | Provider | Cloud provider or internal infra team depending on environment |
| Host/hypervisor | Provider | Usually provider |
| OS patching | Usually provider at the managed service layer | Internal team |
| Software version/engine upgrades | Provider supports per policy; customer chooses schedule/tier per service | Internal team plans and executes |
| Control plane | Usually provider | Internal team if self-built |
| Data model/schema | Application team | Application team |
| IAM/network configuration | Shared responsibility | Primarily internal team |
| Backup policy | Service may provide mechanisms; customer configures/verifies | Internal team designs and operates |
| Restore validation | Customer must validate against business requirements | Internal team |
| Monitoring/SLO | Provider provides baseline telemetry; customer monitors workload | Internal team builds end-to-end |
| Incident response | Provider handles service side; customer handles workload/config | Internal team handles most of the stack |
| Capacity/quotas | Provider supplies capacity per quotas and service limits | Internal team sizes and scales workload |

Managed services offload part of the work, not customer accountability. For example, a provider may run automated database backups, yet the customer must still verify retention, access permissions, RPO/RTO, and independent restorability.

## 4. Defining a Fair Comparison Scope

Two options can only be compared when they satisfy the same objectives.

Before calculating TCO, specify:
- Workload: requests/s, transactions/s, data size, growth, and traffic mix.
- Availability/SLO: uptime, latency, error budget, and maintenance windows.
- RPO/RTO: acceptable data loss and recovery time.
- Security: encryption, identity, auditing, key management, and network isolation.
- Compliance: data residency, retention, evidence, and certification scope.
- Capacity: peaks, bursts, headroom, HA replicas, and DR.
- Environments: production, staging, development, and non-production.
- Time horizon: 1 year, 3 years, or expected lifecycle.
- Region, currency, pricing tier, and support level.

Never compare a multi-AZ managed database with backups, monitoring, and support against a single VM with no redundancy. Those are two different service levels.

### 4.1. Baseline Service Level

You can define a minimum requirements table:

| Requirement | Baseline to Meet |
| --- | --- |
| Throughput | Handles design peak and growth |
| Latency | Meets target p95/p99 |
| Availability | Meets agreed SLO |
| Recovery | Validated RPO/RTO |
| Security | Encryption, IAM, auditing, patching |
| Operations | Monitoring, on-call, runbooks |
| Compliance | Data location, retention, evidence |
| Capacity | Defined N+1 or failure scenarios |

If an option fails to meet the baseline, add the incremental cost required to reach the baseline or explicitly document residual risk. Never use a lower price to disguise a lower service level.

## 5. General TCO Model

TCO over a time horizon T:

```text
TCO(T) =
    Direct infrastructure cost
  + Managed service / license cost
  + Network and data transfer
  + Backup and disaster recovery
  + Observability and security tooling
  + Engineering and operations labor
  + Support and training
  + Migration and exit cost
  + Expected incident / risk cost
  - Discounts and reusable value
```

For self-managed, direct infrastructure may be lower while engineering/operations labor is higher. For managed services, the service premium may be higher while certain operational tasks shift to the provider.

### 5.1. Cost Categories

| Category | Examples | Easily Overlooked? |
| --- | --- | --- |
| Compute | VMs, CPU, memory, managed nodes | Yes |
| Storage | Capacity, IOPS, throughput, snapshots | Yes |
| Network | NAT, load balancers, egress, cross-zone transfer | Very easily |
| Licenses | Commercial engines, OS, add-ons | Yes |
| HA/DR | Replicas, standbys, cross-region copies | Yes |
| Backup | Retention, restores, archive retrieval | Very easily |
| Observability | Logs, metrics, traces, indexing | Very easily |
| Security | KMS, secrets, scanning, SIEM | Yes |
| Labor | SRE, DBRE, platform engineer, on-call | Very easily |
| Support | Provider plans, vendor support, training | Yes |
| Migration | Data transfer, refactoring, dual run, testing | Yes |
| Exit | Export, conversion, replatforming | Frequently ignored |

## 6. Direct Costs of Managed Services

Managed services may bill by:
- Instance size or vCPU/memory.
- Provisioned IOPS/throughput.
- Storage capacity and snapshots.
- Request/operation counts.
- Data processed or data scanned.
- Messages/partitions/throughput units.
- Data transfer and cross-region replication.
- License/edition/tier.
- Backup retention and restore operations.
- Minimum capacity or idle resources.
- Support plans and enterprise features.

Some services bill separately for control plane, workers, nodes, or data plane. Some bill hourly, others per request/GB or capacity reservation. Use the specific provider's pricing calculator and usage profile; there is no universal managed-service rate.

### 6.1. What Work Does the Premium Buy?

Do not treat the entire price difference as a "convenience fee." Itemize specifically what the service performs in place of the internal team:

| Managed Capability | Work Potentially Handled by Provider |
| --- | --- |
| Provisioning | Installation, platform configuration, endpoint creation |
| Patching | Host/engine updates within service scope |
| Backup | Creating recovery points and storing per policy |
| Failover | Health detection, promotion, or endpoint updates |
| Scaling | Capacity operations per tier/limits |
| Control plane | APIs, schedulers, orchestration, and service management |
| Baseline monitoring | Health signals and service-level telemetry |
| Support | Escalation to the service operations team |

Evaluate each item against the service description and SLA. If the provider does not handle a given task, include internal labor for it.

## 7. Direct Costs of Self-Managed Setups

Self-managed can use commodity compute and open-source software, yet must account for the entire stack:

- VMs/bare metal, disks, networking, and load balancing.
- OS licenses or subscriptions.
- Software licenses and commercial support if applicable.
- Orchestration/control plane.
- Database/broker/cache replicas.
- Backups, snapshots, log shipping, and archiving.
- Monitoring, metrics, logs, tracing, and alerting.
- Security scanning, vulnerability management, and secrets services.
- Build/deploy automation and configuration management.
- Staging/performance environments.
- DR capacity and failover environments.
- Data transfer, egress, and recovery traffic.

### 7.1. Reserve Capacity and Utilization

If a self-managed cluster is sized to survive losing a node or AZ, part of its capacity must always stay reserved to absorb failover load. Idle capacity still costs money.

If a managed service bakes HA into its tier or bills separately for standbys/replicas, compare equivalent total capacity. Do not add spare capacity to one option while forgetting it in the other.

### 7.2. Free Software Does Not Mean Free Operations

Open-source software may require no license fee, yet the team still has to install, upgrade, patch vulnerabilities, handle CVEs, back up, restore, benchmark, and cover on-call. Community support also carries different investigation and resolution timelines than contractual support.

Labor costs typically recur monthly and grow with complexity, cluster count, region count, version count, and customization depth.

## 8. Labor and Operational Costs

Labor is a major cost driver, especially for self-managed platforms. Estimate by concrete activities:

| Activity | Time to Account For |
| --- | --- |
| Initial architecture/build | Design, automation, and initial hardening |
| Provisioning/onboarding | Creating environments, granting access, configuration |
| Patching/upgrades | Scheduling, testing, deploying, rolling back |
| Backup/restore | Monitoring backups, restore drills, and remediation |
| Monitoring/on-call | Alert triage, incident response, postmortems |
| Capacity planning | Forecasting, benchmarking, scaling, and rebalancing |
| Security/compliance | Scanning, audit evidence, access reviews |
| Vendor/provider coordination | Case handling, escalation, maintenance |
| Documentation/training | Runbooks, handovers, knowledge transfer |

### 8.1. Labor Cost Formula

```text
Annual labor cost =
    Σ (hours per activity per year × fully loaded hourly cost)
```

Fully loaded hourly cost can include salary, benefits, overhead, and management costs per the organization's accounting model.

Hypothetical example:
- 30 hours/month for patching, upgrades, and maintenance.
- 20 hours/month for on-call and incident follow-up.
- 15 hours/month for backup, restore, and capacity tasks.
- Fully loaded labor cost of 50 USD/hour.

```text
Monthly hours = 30 + 20 + 15 = 65 hours
Monthly labor = 65 × 50 = 3,250 USD
Annual labor = 3,250 × 12 = 39,000 USD
```

This is a calculation example, not a salary benchmark or industry standard. Use your organization's actual staffing costs, workloads, and measured hours.

### 8.2. Avoid Double-Counting Labor Hours

If on-call hours are already embedded in fully loaded costs or team allocations, avoid adding them again on a separate line. Explicitly record FTEs, hours, and rates. For teams supporting multiple workloads, allocating by usage/effort is more realistic than charging the entire cost to a single service.

### 8.3. Opportunity Cost

A platform engineer spending 20% of their time operating a self-managed broker cannot spend that time improving the deployment platform or developer productivity. You can express opportunity cost via capacity/FTE and roadmap value, while avoiding false precision if no internal valuation method exists.

## 9. Security, Compliance, and Risk Costs

Managed services may provide patching, encryption integrations, audit hooks, or certification evidence, though customers must still configure and use them properly. Self-managed setups offer deep customization while placing full-stack control responsibility on the team.

Items to include:
- Vulnerability scanning and patch remediation.
- IAM reviews, secret rotation, and privileged access.
- Encryption/KMS key operations.
- Network segmentation and egress controls.
- Audit logging, retention, and SIEM ingestion.
- Backup immutability and restore validation.
- Compliance assessments and evidence collection.
- Incident response, forensics, and recovery.
- Contract/SLA reviews and provider risk assessments.

### 9.1. Shared Responsibility Model

For every control, state who is accountable:
- Provider: physical security, host infrastructure, or managed control plane per service.
- Customer: identity, data, access policies, application configuration, and much of network/security.
- Shared: patch windows, key management, backup policies, monitoring, and incident coordination.

Never assume "managed" means the provider assumes all compliance responsibility. Verify service scope, region, edition, contract, and audit reports.

### 9.2. Expected Risk Cost

You can use a simple model:

```text
Expected annual incident cost =
    Σ (scenario probability × business impact)

Risk-adjusted TCO =
    operating TCO + expected incident cost
```

Probabilities and impacts are usually uncertain. Evaluate scenarios such as region loss, unpatched vulnerabilities, failed restores, and operator errors; run sensitivity analysis rather than presenting a single deceptive point estimate.

## 10. Availability, Backups, and Disaster Recovery

A managed option may offer multi-AZ, automated backups, and failover, yet you must verify:
- Is HA included in the default tier or billed extra?
- How far do backup retention and PITR extend?
- Are replicas synchronous or asynchronous?
- Are RPO/RTO contractually committed or merely targets?
- Does restoring require provisioning new resources?
- Is failover automatic or manual?
- Is cross-region recovery supported?
- Are there quota limits or service dependencies?
- Can backups be deleted by the same account or security principal?

For self-managed setups, explicitly include standby compute, replicas, backup storage, transfer, monitoring, runbooks, and drill staffing.

Never compare managed multi-AZ against self-managed single-node. Compare identical failure scenarios and verified restore/failover evidence.

### 10.1. Value of Automation

A managed service can cut toil yet still require:
- Load testing.
- Backup restore testing.
- Failover game days.
- Application-level health checks.
- Data integrity validation.
- Post-incident reconciliation.

If these tasks remain on the customer side, do not omit them from TCO.

## 11. Elasticity and Utilization

Managed services typically allow scaling capacity up/down via API or autoscaling, though minimum tiers, scaling delays, quotas, and burst fees may apply. Self-managed setups can optimize utilization via bin packing and shared clusters, while requiring headroom and capacity planning.

Metrics:
- Average and peak utilization.
- Idle/reserved capacity.
- Scaling frequency and time-to-capacity.
- Resource fragmentation.
- Cost per request/transaction.
- Cost per GB stored/processed.
- Capacity headroom for failure scenarios.

### 11.1. Burst and Variable Workloads

For bursty workloads, managed serverless/elastic services can save money via usage-based billing. Still check request pricing, cold starts, burst quotas, minimum charges, and egress.

Self-managed can be cheaper when workloads are steady, utilization is high, and the team actively tunes resources. However, holding a large cluster for brief peaks can drive TCO up through idle capacity.

## 12. Cost Break-Even Between Managed and Self-Managed

Let:
- M be the monthly managed service fee for the workload.
- I be the monthly self-managed infrastructure/license/tooling cost.
- O be the monthly self-managed operations labor.
- G be the monthly managed-specific tooling/network/support cost not included in M.
- F be fixed setup/migration costs amortized over time if needed.

Then:

```text
Managed monthly TCO = M + G + Managed labor
Self-managed monthly TCO = I + O

Managed is cheaper when:
M + G + Managed labor < I + O
```

Because managed labor and self-managed labor are rarely identical, estimate each via the activity matrix rather than assuming managed labor is zero.

### 12.1. Illustrative Break-Even Point

Suppose:
- Managed service fee: 4,500 USD/month.
- Managed operations effort: 10 hours/month × 50 USD = 500 USD.
- Self-managed infrastructure, licenses, and tooling: 2,500 USD/month.
- Self-managed operations: 65 hours/month × 50 USD = 3,250 USD.

```text
Managed TCO = 4,500 + 500 = 5,000 USD/month
Self-managed TCO = 2,500 + 3,250 = 5,750 USD/month

Managed savings = 750 USD/month
Annual difference = 9,000 USD/year
```

In this example, managed has a higher service invoice yet a lower total TCO due to labor. The result would shift if the organization already runs shared operations teams and automation capabilities, lowering incremental labor.

### 12.2. Solving Backwards for Break-Even Scale

If managed fees scale with usage while self-managed infrastructure grows in capacity steps, break-even is not necessarily linear. Model it as:

```text
TCO_managed(x) = fixed_managed + unit_rate_managed × x
TCO_self(x) = fixed_self + tiered_infra(x) + ops(x)

Break-even occurs where:
TCO_managed(x) = TCO_self(x)
```

`x` can be transactions/month, GB processed, active connections, or throughput units. With tiered infrastructure, autoscaling, and step changes in labor, evaluate across multiple workload scenarios.

## 13. Scale, Stability, and Team Skills

Conditions that often favor managed:
- Small/medium workloads or uncertain growth.
- Variable traffic requiring elasticity.
- Small teams or lack of deep database/broker operations expertise.
- Time-to-market is critical.
- Need an HA/backup/patching baseline quickly.
- Product differentiation lies in business logic rather than platform software.

Conditions that can favor self-managed:
- Large, steady workloads with high utilization.
- Dedicated platform/SRE/DBRE expertise.
- Need for deep kernel, runtime, plugin, or topology customization.
- Portability requirements or hybrid/on-prem execution.
- Managed service limits or features do not fit.
- Provider/license pricing climbs steeply at large scale.

These are evaluation signals, not automatic rules. Large workloads can still be cheaper managed if the provider offers economies of scale; small workloads can still need self-managed due to specialized requirements.

## 14. Vendor Lock-In and Switching Costs

Managed services can create lock-in via:
- Proprietary APIs/configurations.
- Proprietary data or backup formats.
- Divergent extensions/plugins.
- Custom IAM and network integrations.
- Proprietary monitoring/alert formats.
- Proprietary features like serverless scaling or global replication.
- Contracts, support agreements, and pricing commitments.

Self-managed can improve portability when built on open source and standard protocols, though it is not automatically portable. Storage layouts, operators, Helm charts, custom plugins, data migrations, and operational knowledge can also couple you tightly to a platform.

### 14.1. Exit Costs

Estimate:
- Data export and transfer.
- Data format/schema conversion.
- Downtime or dual-running.
- Application refactoring.
- Rebuilding automation and monitoring.
- Security/compliance revalidation.
- Training and staffing.
- Contract termination or overlapping commitments.

Design an exit strategy when selecting a service: can backup formats be exported, can standard APIs be used, where does data reside, and how long would a migration take?

## 15. Sustainability and Resource Efficiency

Sustainability relates to the compute, storage, network, and energy needed per unit of useful work.

Managed providers can achieve strong utilization and efficiency via large-scale shared infrastructure; self-managed teams can trim waste through tuning, bin packing, and workload consolidation if they have the skills. Conversely:
- Overprovisioned managed tiers create idle capacity.
- Self-managed clusters holding excessive headroom waste resources.
- Unmanaged replicas/backups/retention bloat storage.
- Cross-region data transfers and huge log volumes inflate network footprint.
- Workloads without scale-to-zero or non-production shutdown waste energy.

Useful metrics:
- Energy/carbon intensity when reliably provided by the vendor.
- Compute hours and utilization per transaction.
- Storage GB-month and retention age.
- Network bytes/transaction.
- Idle capacity percentage.
- Useful throughput per unit of resource.
- Waste from overprovisioning and abandoned resources.

Do not infer carbon footprint solely from VM counts or bills. Use consistent methodology and provider data while explicitly noting metric limitations.

## 16. Managed Database vs. Self-Managed Database

This is a common comparison, provided you match engine, version, workload, and HA level.

| Criterion | Managed Database | Self-Managed Database |
| --- | --- | --- |
| Provisioning | Fast via API/console | Requires automation/installation |
| OS/host patching | Provider handles per service | Internal team |
| Engine upgrades | Per support matrix/maintenance policy | Planned by internal team |
| Backups | Often integrated snapshots/PITR | Built and tested in-house |
| HA | Supported topologies/failover | Self-implemented replication/failover |
| Tuning | Limited parameters/extensions | Deeper customization |
| Access | Endpoints and IAM/network policies | Deeper OS/engine control |
| Cost | Service premium and feature charges | Compute/storage/tooling + labor |
| Portability | May depend on extensions/service features | Can be flexible, still requires migration |
| Operations | Lighter at the managed layer | Heavier and requires specialized expertise |

### 16.1. Items to Verify

- Storage autoscaling and maximum size.
- IOPS/throughput and read replicas.
- Backup retention, snapshot copies, and PITR.
- Multi-AZ failover semantics and downtime.
- Database connection limits/proxying.
- Extensions, version compatibility, and parameter access.
- Maintenance windows and forced upgrade policies.
- Data egress, cross-region replication, and restore fees.
- Performance under peak load and failover.

## 17. Managed Kubernetes vs. Self-Managed Kubernetes

Managed Kubernetes typically manages the control plane and select integrations; teams still manage workloads, node groups, add-ons, network policies, storage, upgrades, and security according to the service scope.

Self-managed Kubernetes allows deeper customization of control plane/network/runtime, at the cost of owning:
- API server/etcd availability.
- Control-plane patching and backups.
- Certificate rotation.
- Scheduler/controller health.
- Upgrade compatibility.
- CNI/CSI/ingress lifecycles.
- Cluster autoscalers and node images.
- Multi-AZ quorum and restores.
- On-call, runbooks, and security hardening.

Never assume managed Kubernetes eliminates cluster operations. Compare based on the exact components the provider manages versus add-ons the customer still owns.

## 18. Managed Brokers, Caches, and Observability

Stateful/distributed systems such as message brokers, caches, and observability carry distinct operational complexity.

| Service | Typical Managed Value | Self-Managed Responsibility |
| --- | --- | --- |
| Message broker | Provisioning, broker replacement, managed replication per tier | Partitioning/rebalancing, upgrades, storage, replication, consumer lag |
| Cache | Node lifecycle, failover/topology per tier | Cluster/shard management, failover, eviction, memory sizing |
| Search engine | Cluster provisioning, snapshot/upgrade support | Shard allocation, JVM/heap, indexing, reindexing, snapshots |
| Observability | Ingest/storage/search backend | Collectors, index lifecycle, scaling, retention, query capacity |

Even when managed, customers still design partition keys, data retention, cache invalidation, consumer idempotency, and query/index strategies.

## 19. Shared Platforms and Economies of Scale

When an organization runs many workloads, a self-managed platform can be shared across teams:
- Shared compute clusters.
- Standardized database/broker platforms.
- Monitoring and logging pipelines.
- CI/CD and policy controls.
- On-call and platform engineering.

This can lower incremental cost per workload compared to each team operating independently. Yet shared platforms also incur costs for multi-tenancy, noisy-neighbor mitigation, chargeback, support, upgrade coordination, and blast radius management.

Managed services also leverage shared economics on the provider side; customers pay for capacity and abstraction without building a full-stack operations team.

### 19.1. Avoiding Flawed Labor Attribution

If a platform team exists regardless of a single workload, do not allocate the team's entire salary to one new service. Account for incremental effort or allocate by usage/consumption. Conversely, do not omit hiring/on-call capacity if a new workload genuinely forces adding headcount.

## 20. FinOps: Measuring and Optimizing After Selection

A TCO decision does not end at implementation. Track actual spend and operational effort:

- Cost per transaction/request/job.
- Cost per GB stored/processed.
- Compute utilization and idle capacity.
- Managed tier/instance size relative to load.
- Backup/replication/egress costs.
- Engineering hours spent on operations.
- Incident count, MTTR, and error budgets.
- Upgrade/patch cadence.
- Cost allocation by team/service/environment.
- Forecast versus actuals.

### 20.1. Unit Economics

Example:

```text
Cost per successful booking =
  total monthly platform TCO / successful bookings per month
```

Use successful business transactions instead of raw request counts to compare efficiency. If throughput rises alongside higher error/duplicate rates, cost per useful transaction may worsen.

### 20.2. Review Cadence

- Monthly: spend anomalies, utilization, idle resources, unit cost.
- Quarterly: capacity, support tiers, backups, operational toil.
- Before renewals: commitments, exit terms, feature usage, and pricing.
- Post-incident: outage costs, recovery, and remedial capacity.

Never optimize cost by dropping backups, patching, security, or headroom established as necessary for SLOs.

## 21. Decision Process: Managed vs. Self-Managed

1. **Describe the workload:** demand, data growth, peaks, bursts, traffic mix, and latency.
2. **Define service objectives:** availability, RPO/RTO, security, compliance, and support.
3. **Build a responsibility matrix:** what the provider handles, what the customer handles, and which shared controls need configuration.
4. **Design two equivalent architectures:** equal capacity, HA/DR, retention, and security.
5. **Estimate direct costs:** compute, storage, network, licenses, managed fees, backups, and support.
6. **Estimate labor/tooling:** initial build, patching, on-call, upgrades, monitoring, restores, and audits.
7. **Estimate risk costs:** incident scenarios, downtime, recovery, and residual risk.
8. **Calculate TCO/unit cost:** across 1–3 years and multiple growth scenarios.
9. **Run sensitivity analysis:** labor rates, traffic growth, utilization, egress, and provider pricing.
10. **Assess lock-in/exit:** export, formats, APIs, migration, and contracts.
11. **Run a proof of concept:** benchmarks, restores, failover, upgrades, and cost telemetry.
12. **Write an ADR and review periodically:** owners, assumptions, decision triggers, and review dates.

## 22. Practice Scenario: Booking Platform Selecting a Message Broker

**Context:** A booking platform needs a broker for booking events, payment statuses, and notifications. Current workload averages 5,000 messages/s with campaign peaks of 20,000 messages/s, 3-day retention, and multi-zone availability. The team has two platform engineers running Kubernetes and databases, with no dedicated broker specialist.

### 22.1. Managed Option

- Broker is provisioned on a managed tier supporting throughput and replication.
- Provider manages broker host lifecycles and contracted operational tasks.
- Team still designs topics/partitions, schemas, producer idempotency, consumer lag handling, retention, and alerts.
- Include service fees, storage, networking, cross-zone transfer, support, and backups/exports if needed.
- Verify peak throughput, quotas, failover, and data export.

### 22.2. Self-Managed Option

- Run the broker on Kubernetes or VMs.
- Team owns broker nodes, storage, replication, upgrades, security, monitoring, backups, and recovery.
- Reserve spare capacity for a node/AZ failure and partition rebalancing.
- Include compute, disk throughput, networking, persistent volumes, observability, automation, and on-call labor.
- Assess impact on the roadmap of the two platform engineers and hiring/backup coverage needs.

### 22.3. Illustrative TCO Model

Suppose in one month:

| Line Item | Managed | Self-Managed |
| --- | ---: | ---: |
| Service/compute/storage | 6,000 USD | 3,000 USD |
| Network/backup/tooling | 900 USD | 1,100 USD |
| Labor | 600 USD | 3,000 USD |
| Support/training | 300 USD | 400 USD |
| Total | 7,800 USD | 7,500 USD |

In this example, the TCO gap is only 300 USD/month. However, 60 hours/month of self-managed labor competes directly with other platform initiatives. If campaign traffic doubles or extra on-call engineers are required, the outcome could flip.

All figures are purely hypothetical to illustrate the method; replace them with quotes/provider calculators, usage tests, and internal labor rates.

### 22.4. Conditional Decision

You can choose managed initially so the team focuses on event contracts and product workflows. Once telemetry on throughput, retention, partition counts, and cost per event matures, revisit when workloads stabilize and platform staffing grows. Before deciding, run peak benchmarks, failover tests, consumer recovery tests, and export tests.

## 23. Sample ADR: Choosing a Managed Service After TCO Comparison

```text
ADR-173: Managed vs. self-managed message broker

Context:
- Booking platform requires 5,000 msg/s average and 20,000 msg/s peak.
- Requires multi-zone availability and 3-day retention.
- Platform team has two engineers, without deep broker specialization.
- Self-managed infrastructure bill is lower, but labor is higher.

Options:
A. Managed broker on a tier with appropriate throughput and HA.
B. Self-managed broker on Kubernetes.
C. Managed initially, revisited once usage evidence is collected.

Decision:
- Select C.
- Managed broker meets tested peak, retention, and failure objectives.
- Team owns topics/partitions/schemas, producer/consumer correctness, and alerts.
- Costs are tracked via monthly TCO and cost per successful event.
- Periodically re-evaluate based on growth, provider pricing, and staffing.

Trade-offs:
- Higher service invoice TCO.
- Lower operational toil and reduced need for full-time broker specialists.
- Dependency on provider features, quotas, and export semantics.

Verification:
- Benchmark throughput/latency at peak.
- Multi-zone failover and consumer recovery tests.
- Verify retention, replay, and data export.
- Measure actual monthly spend and engineering hours.
- Cost per successful booking event stays within budget.

Revisit triggers:
- Volume/retention changes significantly.
- Provider fees or quotas change.
- Platform team acquires broker expertise and additional staffing.
- TCO/unit cost or SLO misses targets.
```

## 24. Common Pitfalls

1. **Comparing service fees to raw VM bills:** omits labor, HA, backups, and tooling.
2. **Comparing two different service levels:** managed multi-AZ vs. self-managed single-node.
3. **Treating managed as zero operations:** applications, access, data, quotas, and recovery still need management.
4. **Treating open source as free:** labor, support, patching, and incident costs still exist.
5. **Ignoring egress/cross-zone transfer:** network costs can become substantial.
6. **Omitting standby/headroom:** post-failure capacity gaps distort comparisons.
7. **Double-counting or omitting labor:** skews TCO dramatically.
8. **Relying on average utilization:** misses peaks, bursts, and idle capacity.
9. **Skipping restore tests:** backup costs are paid without proving recovery works.
10. **Assuming the provider owns all compliance:** customers retain many controls.
11. **Ignoring migration/exit costs:** data lock-in or proprietary formats raise switching costs.
12. **Deciding based on Year 1 pricing:** misses growth, renewals, and commitments.
13. **Overlooking support tiers/contracts:** SLAs and escalations are not equivalent.
14. **Lacking unit economics:** no visibility into cost per useful transaction.
15. **Equating bills to carbon:** does not directly reflect energy/carbon intensity.
16. **Failing to review post-launch:** usage, pricing, and operational effort evolve over time.
17. **Counting cloud spend alone:** overlooks opportunity cost and team effectiveness.
18. **Skipping a PoC:** pricing estimates cannot replace benchmarks and failover tests.

## 25. Pre-Decision Checklist

- [ ] Both options use the same workload, region, growth, and time horizon.
- [ ] SLOs, RPO/RTO, security, and compliance baselines are explicitly documented.
- [ ] Responsibility matrix defines provider, customer, and shared controls.
- [ ] Managed fees include tiers, backups, support, requests, and capacity charges.
- [ ] Self-managed includes compute, storage, networking, licenses, and HA/DR headroom.
- [ ] Labor covers build, patching, upgrades, on-call, restores, audits, and training.
- [ ] Observability, security tooling, and backups are included in TCO.
- [ ] Egress, cross-AZ/region transfers, NAT, requests, and archive retrievals are included.
- [ ] Incident/risk costs and residual risk are documented.
- [ ] 1–3 year TCO covers multiple workload/growth scenarios.
- [ ] Sensitivity analysis covers labor, utilization, egress, and pricing.
- [ ] Cost per successful transaction/event is calculated where relevant.
- [ ] Lock-in, data export, migration, and exit costs are evaluated.
- [ ] Staffing, skill coverage, and on-call sustainability are confirmed.
- [ ] Backup restores, HA failover, upgrades, and peak load are tested.
- [ ] Pricing, contracts, SLAs, and provider service boundaries are verified.
- [ ] Owners, assumptions, decision triggers, and review dates are recorded in an ADR.
- [ ] Actual spend/labor will be tracked in production.

---

**Key takeaway:** Managed services typically trade a service premium for offloaded provisioning and operations; self-managed setups can cut certain infrastructure invoices while shifting work, risk, and responsibility onto the internal team. The right decision compares TCO across identical workloads and SLOs, accounts fully for labor, HA/DR, security, networking, tooling, and exit costs, and validates assumptions through a PoC and real operational telemetry.
