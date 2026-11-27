# Lift-and-shift without reviewing networking, operations, and cost

## 1. What is the antipattern?

**Lift-and-shift** (*rehost*) is the practice of moving an application running on physical servers or virtual machines onto cloud infrastructure with minimal changes to source code and deployment structure. For example, an organization moves web, application, and database (DB) VMs from a data center to cloud VMs while keeping the same operating system, processes, and connectivity mechanisms.

Rehosting can be a **sound migration step** when you need to exit a data center quickly, minimize changes to legacy applications, or establish a foundation for later modernization. The antipattern appears when the delivery team treats a VM booting successfully in the cloud as proof that the architecture is ready, while **failing to re-evaluate networking, the operating model, and total cost**. As a result, the system carries its old weaknesses into an environment with different characteristics: traffic travels farther, operational responsibilities shift, and resources are billed in a new way.

This is the theme of the **Architecture Antipatterns** chapter in CLOUD_ARCHITECTURE: architects must trace from business requirements to decisions on networking, compute, data, and deployment; and evaluate trade-offs across reliability, security, scalability, cost, and operations under the **Well-Architected** pillars.

After this lesson, learners can:

- Recognize signs of a rehost that lacks architectural review and distinguish it from a planned rehost.
- Analyze the impact of data paths, latency, connectivity, network segmentation, and access permissions.
- Design observability, backup, recovery, security, and operational processes suited to the cloud.
- Estimate total operating cost, identify commonly overlooked line items, and plan optimization.
- Propose a migration roadmap with measurable acceptance criteria, even without modifying source code.

## 2. Scenario: what problems does moving VMs “as is” cause?

A company runs a three-tier order management application: a web server receives user requests, an application server processes business logic, and a database stores orders, inventory, and payments.

The system is currently hosted in a single data center. The project team moves the web and application tiers to cloud VMs while keeping the database in the data center during the initial phase. The post-migration architecture still works, but each application request requires many query round trips across the hybrid link. During peak hours, latency spikes sharply; the operations team lacks visibility into the detailed request path; and the cloud bill is higher than expected due to always-on VMs, disks, and network egress.

~~~mermaid
flowchart TB
    U[Users] --> LB[Cloud entry point]
    subgraph CLOUD[Cloud]
      LB --> W[Web VM]
      W --> A[Application VM]
    end
    subgraph DC[Data center]
      DB[(Primary DB)]
    end
    A <-->|Many round trips over hybrid network| DB
    note1["Risks: latency, link dependency,\ndata transfer cost, lack of observability"]
    A -.-> note1
~~~

**The problem lies in architectural assumptions:** previously, components sat close together and the operations team controlled most of the physical network; after migration, the application depends on link quality, underlying platform services, and the cloud billing model. Moving a VM does not automatically turn a system into a fault-tolerant, auto-scaling, or cost-optimized application.

## 3. Symptoms and root causes

| Symptom | Common flawed assumption | Potential consequence |
| --- | --- | --- |
| Copying the old IP/VLAN scheme to the cloud | VPC/VNet, subnets, and routing behave like switches in a data center. | Overlapping CIDRs, asymmetric routing, connectivity failures, or unintended access paths. |
| Moving the app to the cloud while leaving the DB or dependencies on-premises | Physical distance does not affect chatty protocols. | Round trips slow down transactions; link outages impact the entire system. |
| Placing all VMs in a single availability zone and calling it “high availability” | The cloud automatically protects against all failures once a VM has booted. | A single availability zone incident can take down the entire application. |
| Keeping manual scripts and shared admin accounts | Cloud operations are just SSH/RDP into VMs. | Uncontrolled drift, difficult auditing, and recovery dependent on individuals. |
| Measuring only CPU and RAM | If the VM is still running, the service is meeting its SLO. | Slow transactions and errors at the LB, DB, or network path go undetected. |
| Sizing VMs to match old physical server specs | The same vCPU/RAM count means the same performance and cost. | Overprovisioned resources or insufficient IOPS/bandwidth; rising costs. |
| Budgeting only for VM compute | Networking, storage, backups, logs, and platform services are negligible. | Actual bills exceed budget. |
| Not defining a parallel-run end date or optimization steps | “Getting onto the cloud” is the project finish line. | Two environments persist long-term, paying for redundant resources and carrying technical debt. |

Root causes are often measuring success by the number of VMs migrated, lacking a dependency inventory and pre-migration baseline, unclear ownership across infrastructure, application, security, and finance teams, or setting a migration deadline without allocating time to establish minimum operational readiness.

### When is lift-and-shift still the right choice?

Rehosting is appropriate when timeline, licensing, source-code, or business constraints make immediate refactoring too risky; when data paths have been measured and proven to meet performance requirements, or tightly coupled components are moved together; and when a landing zone, connectivity, monitoring, backups, security, sizing, cost estimation, and a post-cutover optimization plan are in place. Any remaining technical debt must have an owner and a target resolution date.

Therefore, **lift-and-shift is not inherently an antipattern**; the antipattern is *rehosting as if the target environment had no different characteristics or responsibilities*.

## 4. Networking mistakes: copying topology without measuring data flows

### 4.1. Start from dependency flows, not from a VM list

A list of 20 VMs does not tell you how many times the application calls the database, where it communicates with a payment provider, or whether it depends on DNS, LDAP/Active Directory, SMTP, a license server, or internal services. Before migrating, build a **dependency map** and record the following for each flow:

| Attribute | Example information to collect |
| --- | --- |
| Source → destination | App → DB, app → cache, app → payment API, user → web |
| Protocol and port | HTTPS/TLS, TCP to DB, DNS, NTP; including return paths |
| Purpose and sensitivity | Customer data, order writes, login |
| Traffic volume | Requests/sec, bytes/sec, payload size, peak windows |
| SLO | p95/p99 latency, error rate, timeouts, read-after-write requirements |
| Constraints | IP allowlists, data residency, encryption, authentication, recovery time |
| Owner | Application team, data team, network team, third party |

You must evaluate the **actual request path**, including ingress, service-to-service communication (*east–west*), traffic to the data center, Internet egress, and replication/backup traffic. These paths differ in latency, availability, and pricing.

### 4.2. Network latency amplified by chatty applications

Suppose each request executes **25 sequential database queries**. Before migration, single-trip network latency was about 1 ms; after migration, if the database stays on-premises, round-trip latency rises to 18 ms. The estimated network overhead difference is:

\[
\Delta T \approx 25 \times (18 - 1) = 425\ \text{ms/request}
\]

This is a **hypothetical example** accounting only for network transit across sequential calls, excluding query execution time, serialization, queuing, or retries. For parallel queries or pipelined connections, actual latency may differ. Even so, the calculation shows why a modest round-trip increase can noticeably slow down an application that makes many DB calls.

Mitigation approaches depend on the situation:

- **Co-locate with data:** migrate tightly coupled transactional applications and databases into the same region or shorten the hybrid path, after evaluating data requirements and cutover feasibility.
- **Reduce call count:** batch queries, process in bulk, or add caching with proper invalidation and consistency controls.
- **Split data domains:** use appropriate APIs or events if a legacy system must remain, avoiding per-user-request remote reads across multiple tables.
- **Measure instead of guessing:** use per-request tracing and hop-level metrics; run representative load tests with realistic latency, packet loss, and failover.

Do not use caching to mask every slow query when transactions require fresh data, such as inventory checks or payment authorization.

### 4.3. Networking decisions you cannot “copy verbatim”

**Addressing and routing:** plan non-overlapping CIDRs between on-premises and cloud; define route tables, return paths, NAT, VPNs or dedicated links, and failure domains. Overlapping IPs can prevent direct routing and force NAT or re-addressing.

**Security zoning:** design role-based subnets, firewall/security group rules, DB access controls, outbound restrictions, and private endpoints for suitable managed services. Do not replace a broad legacy ACL with a **0.0.0.0/0** rule opening administrative ports. Admin access should go through a controlled, audited mechanism.

**DNS and identity:** verify internal name resolution, split-horizon DNS, TTLs, certificates, reverse DNS where relevant, application identity mechanisms, and dependencies on legacy identity systems. Changing a VM's IP while overlooking DNS can leave services calling the old system.

**Ingress and egress:** separate Internet-facing LBs/reverse proxies from application servers; evaluate WAF, DDoS protection, TLS termination, outbound routing, NAT, connection limits, and Internet/cross-region transfer costs. Not all internal traffic is free.

**Connectivity availability:** a single VPN or a single dedicated circuit can become a single point of failure even if the app runs on multiple VMs. Consider independent redundant links, failover routing, BGP/routes where used, health checks, and failover testing.

**Performance:** beyond latency, measure actual throughput, packet loss, MTU, retransmissions, timeouts, connection pooling, and connection limits on appliances/managed services.

### 4.4. Example path that needs redesign

~~~mermaid
flowchart LR
    U[Client] --> EDGE[DNS / WAF / Load Balancer]
    subgraph AZ1[Availability zone A]
        APP1[App instance A]
    end
    subgraph AZ2[Availability zone B]
        APP2[App instance B]
    end
    EDGE --> APP1
    EDGE --> APP2
    APP1 --> DB[(DB near application)]
    APP2 --> DB
    APP1 --> OBS[Centralized observability]
    APP2 --> OBS
    DB --> BCK[Independent backup & restore testing]
    ONPREM[Systems remaining in data center] <-->|Controlled hybrid connectivity| API[API / data sync]
    API --> APP1
    API --> APP2
~~~

This diagram illustrates only the **principle of separating the primary transaction path from chatty hybrid links**. An actual design must also define the database's fault tolerance and deployment scope (such as cross-zone replication/failover), consistency, backups, security boundaries, and cross-zone transfer costs. Having two app instances does not automatically make the database highly available.

## 5. Operational mistakes: moving VMs to the cloud while keeping old management habits

The cloud changes responsibility boundaries. The provider operates part of the underlying infrastructure, while the organization remains responsible for workload configuration, VM operating systems, access permissions, data, patching, backups, and recoverability under the **shared responsibility model** of the chosen service.

### 5.1. Lack of SLOs, observability, and flow-level diagnostics

A dashboard showing only CPU and RAM cannot explain why “login takes 8 seconds.” You need observability aligned with user behavior and dependencies:

- **Business metrics and SLIs:** order creation success rate, p95/p99 response time, error rate, job and queue lag.
- **Infrastructure metrics:** CPU, RAM, disk capacity, IOPS/latency, network throughput, packet loss, instance/LB health, DB connections, and replication lag.
- **Centralized logging:** request/correlation IDs, error levels, queryable structure; masking/encrypting sensitive data per policy.
- **Distributed tracing:** time spent at the edge, app, DB, cache, and services across the hybrid network; propagating trace IDs across hops.
- **Synthetic tests and health checks:** verify critical user flows from user locations, not just whether a TCP port is open.

Hypothetical SLO example for an order-creation flow: “Over a 30-day window, at least 99.9% of valid order-creation requests succeed and p95 latency is under 800 ms.” Both conditions require agreed measurement definitions, scope, and exclusions. Alerts should tie to user-impacting errors and *error budgets*, rather than firing hundreds of alerts whenever a host hits 70% CPU.

### 5.2. High availability does not come from the “cloud” label

If all three VMs and a single data disk reside in the same failure domain, one outage can still halt the entire service. Consider:

- Distributing instances across multiple availability zones where requirements and services support it; having the LB remove unhealthy instances based on functional health checks.
- Avoiding local disk storage on a single VM for sessions, file uploads, or critical state if you want replaceable VMs or horizontal scaling.
- Designing failure modes for the DB, cache, queue, DNS, and hybrid links; each component needs its own RTO/RPO.
- Implementing appropriate limits, timeouts, retries with backoff, and circuit breakers to prevent retry storms when a dependency slows down.
- Running failure drills for VM loss, zone/hybrid link outages, lost credentials, or disk exhaustion, and measuring actual recovery times.

**Backup is not the same as high availability.** A highly available replica can replicate accidental deletions too; backups with retention/versioning policies and independent copies enable recovery from logical errors. You must **test restores**, verify the application runs on restored data, and compare against RPO (acceptable data loss) and RTO (maximum acceptable recovery time).

### 5.3. Security and configuration-driven operations

Keeping shared admin accounts, secrets in config files, or SSH/RDP ports exposed directly to the Internet carries old vulnerabilities onto a broader attack surface. Foundational controls include:

1. **Landing zone and policies:** separate environments/accounts/subscriptions/projects; establish role assignments, logging/auditing, policy guardrails, tags, and budgets upfront.
2. **Identity and secrets:** SSO/MFA for administrators, least-privilege IAM, workload identities instead of static keys where possible, vaults, and secret rotation workflows.
3. **Infrastructure as Code (IaC):** declare networks, VMs, disks, LBs, IAM, and configurations with code review; control drift and run builds through testing pipelines.
4. **Golden images/patching:** manage OS baselines, endpoint security, updates, vulnerability scanning, and base configurations; rebuild VMs rather than patching manually.
5. **Runbooks and change management:** deployment schedules, application rollback, post-deploy monitoring, on-call rotations, ownership, and drills.

Not every rehosted workload needs a rewrite into microservices or Kubernetes. Bringing VM administration under clear processes, automating risky steps, and improving resilience usually take higher priority than changing tech stacks just to look “cloud-native.”

## 6. Cost mistakes: counting VM compute while ignoring the full lifecycle

### 6.1. Cloud TCO includes multiple categories

Depending on the provider and service type, total cost of ownership (TCO) can include:

| Category | Items to include in the estimate | Why it is easily overlooked |
| --- | --- | --- |
| Compute | VMs, licensing fees, standby servers, instances left running after hours | Sized to legacy physical core counts without considering utilization hours |
| Storage | Block/object capacity, disk tiers, extra IOPS/throughput, snapshots, versioning/retention | Price per GB does not reflect performance tiers or backup copy counts |
| Network | Internet egress, cross-zone/cross-region transfer, NAT gateways, LBs, endpoints, VPN/dedicated links | A single request traversing multiple hops can trigger multiple charges |
| Observability | Log ingestion, long-term retention, log queries, custom metrics, traces | Leaving full debug logging enabled continuously |
| Security and operations | Key management, management tooling, vulnerability scanning, ops tools, on-call staffing | Counting only the infrastructure bill and omitting operational overhead |
| Migration and parallel run | Migration tooling, testing, replication, temporary environments, and running two systems concurrently | No firm cutoff date for legacy infrastructure |
| Recovery | Independent backups, replicas, DR environments, and restore testing | Treating backup/DR as a free built-in feature |

Pricing varies by region, resource type, timing, usage commitments, and contracts. For real budgets, use current pricing schedules and calculate charges along actual data paths rather than relying on a generic rule of thumb across clouds.

### 6.2. Quantitative example (purely hypothetical unit prices)

Suppose after rehosting there are 10 VMs running continuously, 5 TiB of block storage, and 3 TiB of Internet egress per month. To illustrate how to check costs, **assume** a VM rate of \$0.30/hour, block storage at \$0.10/GiB-month, and Internet egress at \$0.08/GiB. A month is modeled as 730 hours and 1 TiB = 1,024 GiB.

| Line item | Calculation | Monthly estimate |
| --- | --- | ---: |
| VMs | 10 × 730 × 0.30 | \$2,190.00 |
| Block storage | 5 × 1,024 × 0.10 | \$512.00 |
| Internet egress | 3 × 1,024 × 0.08 | \$245.76 |
| **Incomplete illustrative total** | | **\$2,947.76** |

This is **not a quote** from any provider. The figures above exclude cross-zone transfer, LBs, NAT, backups, logs, DB licenses, support, staffing, taxes, or remaining on-premises infrastructure.

In this example, 10 always-on VMs alone account for roughly \$2,190/month. If post-migration load measurements allow reducing from 10 to 7 equivalent VMs (while still meeting SLOs and HA), hypothetical VM spend drops by about **\$657/month**, before other line items. Do not cut standby capacity purely to save money if it is required for availability.

### 6.3. Optimization levers and trade-offs

| Measure | Potential benefit | Conditions / trade-offs |
| --- | --- | --- |
| Load-based rightsizing | Avoids overprovisioning CPU/RAM, disk, and IOPS | Requires observing peak windows, headroom, and load tests; smaller VMs may have lower bandwidth |
| Auto-scaling or shutting down non-prod environments | Reduces idle capacity | Requires statelessness, health checks, startup time, and avoiding disruption to work |
| Usage commitments / reservations / savings plans per service | Lowers unit rates for steady baseline load | Reduces flexibility if workload shape changes; establish a baseline before committing |
| Choosing the right storage tier and lifecycle | Avoids expensive disks or unnecessary retention | Access latency, IOPS, backup, and compliance requirements must still be met |
| Reducing cross-zone/cross-region chatter and adding controlled caching | Cuts egress and latency | Must not degrade availability or break business consistency |
| Cost allocation via tags, budgets, and alerts | Identifies services/owners driving spend | Tagging discipline and reporting must be maintained |
| Reclaiming temporary VMs, disks, IPs, LBs, and snapshots | Eliminates lingering post-project spend | Requires checking dependencies, data retention policies, and decommission evidence |

A key target is **cost per unit of value**—for example, USD per 1,000 completed orders or USD per 1 million valid API requests—paired with SLOs. Lowering the total bill while increasing transaction failure rates is not optimization.

## 7. Redesign around requirements, not old server specs

Instead of asking “Which instance type matches this VM?”, determine:

1. **Business requirements:** user counts, transactions/sec, peak periods, served regions, contractual SLAs.
2. **Non-functional requirements:** p95/p99 latency, availability, RPO/RTO, data residency, security, auditing, deployment time, budget.
3. **Current state:** dependency graph, data volume, throughput, IOPS, access patterns, common failures, on-premises operating cost.
4. **Architecture options:** keep VMs with guardrails, adjust topology/data placement, move the DB to a managed service, or modernize incrementally by capability.
5. **Evidence-based decision:** load and recovery testing, total cost, migration risk, reversibility, and accountable owners.

### Illustrative decision matrix

| Option | Migration speed | App changes | Advantages | Limitations to validate |
| --- | --- | --- | --- | --- |
| **A. As-is rehost**, DB stays on-premises | Often fast for the VM step | Low | Minimizes code changes | Hybrid latency, network single points of failure, two environments, long-term cost |
| **B. Dependency-group rehost**, moving DB near app | Moderate | Low–moderate | Cuts round trips; less hybrid dependency in the transaction path | Data cutover, licensing, backups, HA, consistency |
| **C. Partial replatform**, e.g., managed DB, app stays on VMs | Moderate | Moderate | Offloads some DB operations; can leverage built-in HA/backups | DB compatibility, migration method, service limits and cost |
| **D. Gradual refactor by business domain** | Longer | High | Enables independent scaling/deployment and deep optimization | Code complexity, data splitting, business change risk |

No option wins by default across every pillar. For a low-change, low-traffic app with a tight deadline, Option A may suffice if SLOs and operations are assured; for a chatty transactional system, Option B or C can deliver larger gains even before changing business architecture.

### Example decision documented as an ADR

> **Context:** The order application currently makes 25 sequential DB calls per request; hybrid testing increases p95 by 420–500 ms. Target p95 is under 800 ms; maximum cutover window is one overnight maintenance window.
>
> **Decision:** Migrate the app and DB together using snapshot + CDC under a tested cutover plan; run the app on VMs first without splitting into microservices. Use private networking, an LB, centralized observability, and tested backups.
>
> **Trade-offs:** Increases data migration and cutover rehearsal effort; removes hybrid dependency from everyday requests. Horizontal scaling remains technical debt, scheduled for review after establishing a cloud baseline.
>
> **Validation criteria:** p95 under 800 ms at target load, zero data loss beyond agreed RPO, tested recovery meeting RTO, and a cost estimate covering compute, storage, networking, and operations.

An ADR records the **rationale behind the chosen option, its limitations, and how to verify it**, not just the final diagram.

## 8. Phased process to eliminate the antipattern

You do not need to refactor everything before moving to the cloud. You can turn a “copy VMs” project into a controlled migration using decision gates:

| Phase | Core activities | Evidence required before proceeding |
| --- | --- | --- |
| **1. Discovery and baseline** | Inventory apps, dependencies, data flows, SLOs, peak loads, costs, and risks. | Dependency map, performance/cost baseline, owner per system. |
| **2. Landing zone and network design** | Plan accounts, IAM, CIDRs, routes, DNS, ingress/egress, logging, security, and hybrid links. | Flow diagrams, threat review, connectivity tests, and egress estimates. |
| **3. Pilot / load testing** | Migrate a representative workload; measure latency, IOPS, failover, backup restore, and projected cost. | Results against SLOs, error logs, sizing/topology decisions. |
| **4. Migration by dependency group** | Cut over apps and data in waves; prepare rollback/roll-forward and verify functionality. | Runbooks, cutover window, monitoring, and go/no-go decision. |
| **5. Stabilization and optimization** | Observe multiple load cycles, rightsize, tune storage/network, and automate. | KPI/SLO and unit-cost reports, tested changes. |
| **6. Legacy decommission** | Verify no remaining dependencies, archive per policy, retire excess resources and contracts. | Decommission sign-off, data/backup checks, and final cost report. |

### Phase 1: capture a baseline before losing your reference point

Measure under real traffic and peak days: response time, throughput, errors, DB connection count, query count, network latency, IOPS, disk queue, log volume, and backup size. Without a baseline, if the cloud deployment is slower or more expensive, it is hard to tell migration effects apart from organic business load growth.

### Phase 2: build a secure foundation

Establish a minimal landing zone: environment separation, accounts/roles, private networks, subnets, firewalls, audit trails, secret management, tags, and budgets. Verify ingress/egress flows, DNS, CIDRs, and hybrid link availability. Document both the data plane and the control plane (deployment, administration, backup).

### Phase 3: pilot against real risks

Do not stop at pinging hosts or opening a web UI. The pilot must simulate the query count, data volume, peak load, and failure modes of the real workload. Measure at least the critical transaction flows, test VM/zone/link failures, restore from backups, and inspect sample billing. Adjust topology before migrating in bulk.

### Phase 4: cutover with a recovery path

Define traffic scope, the authoritative write system, data sync method if moving the DB, cutoff point, DNS cache TTLs, and rollback path. Once the cloud has accepted new writes, rolling back on-premises requires preserving newly created data; flipping DNS back alone does not prevent data loss. Shift traffic via canary where appropriate and watch SLOs immediately after cutover.

### Phases 5–6: optimize and close out

Review sizing from post-migration metrics, remove redundant capacity, optimize network flows and log retention, and add automated recovery where beneficial. Set an end date for parallel runs. Verify all dependency paths and retention requirements before decommissioning legacy systems.

## 9. Well-Architected assessment

| Pillar | Questions to evaluate a rehost | Strong evidence |
| --- | --- | --- |
| **Operational Excellence** | Are runbooks, IaC, deployment permissions, logging/tracing, and on-call ownership in place? | SLO dashboards, pipelines, incident drills, alert owners. |
| **Security** | Do network paths, IAM, secrets, encryption, backups, and auditing meet the new controls? | Trust boundary diagrams, policy/IAM reviews, access logs, config checks. |
| **Reliability** | Which components remain single points of failure; have RPO/RTO been verified? | Failure domain diagrams, failover/restore results, recovery runbooks. |
| **Performance Efficiency** | Do data placement, round trips, and CPU/IOPS/network limits match real load? | Load tests, traces, p95/p99, capacity plans, metric-based sizing. |
| **Cost Optimization** | Are there TCO estimates, unit-value cost tracking, budget alerts, and an optimization schedule? | Cost breakdowns, tags, forecasts, unit-cost reports, resource cleanup. |
| **Sustainability** | Is there wasted idle compute, redundant storage, or unretired temporary capacity? | Utilization metrics, lifecycle policies, rightsizing/decommission plans. |

All six pillars must be balanced. For example, placing every VM in a single zone can trim cross-zone transfer fees while raising outage risk; multi-zone deployment improves fault tolerance under a proper design while adding cost and operational effort. Choose based on **SLOs and business risk**, then measure both cost and the protection achieved.

## 10. Quick “fixes” that create new antipatterns

| Knee-jerk reaction | Why it falls short | Better approach |
| --- | --- | --- |
| Upsizing every VM when the app is slow | Slowness may stem from 25 DB round trips or network limits, not CPU. | Use traces, DB metrics, and network metrics to pinpoint bottlenecks before scaling. |
| Inserting a cache in front of every call | Caching does not solve write consistency; invalidation adds complexity. | Classify reads/writes, choose TTLs/invalidation carefully, and place authoritative data appropriately. |
| Enabling multi-zone for the app and declaring HA | The DB, hybrid link, or session state may still be a single point of failure. | Build a failure-mode matrix across the whole transaction path and test failover end-to-end. |
| Buying long-term VM commitments right after migration | Un-rightsized workloads can lock in excess spend. | Measure a real baseline, identify steady base load, and only then commit. |
| Moving everything to Kubernetes/microservices immediately | Increases risk and effort before fixing networking, data, and operations issues. | Prioritize high-impact optimizations; replatform/refactor when benefits and operational readiness justify it. |
| Shutting down on-premises as soon as the new app returns HTTP 200 | Batch jobs, consumers, backup schedules, or DB replication may still be running there. | Verify business flows, dependencies, and data across full cycles before decommissioning. |

## 11. Case study: choosing an option for an ordering system

**Prompt.** An enterprise has 12 application VMs, a 6 TiB database, and a user-management system in a data center. The project team must exit the old facility within three months and lacks resources to rewrite the application. At peak, the app handles 500 requests/sec; on average, each request makes 20 sequential DB queries. Hybrid testing shows a 16 ms round trip from the cloud to the DB compared with 2 ms inside the data center. Target p95 response time is under 1 second, RPO is 15 minutes, RTO is 1 hour, and cloud budget is constrained.

### Problem analysis

Estimated network latency difference on the sequential query path:

\[
20 \times (16 - 2) = 280\ \text{ms/request}
\]

This hypothetical figure excludes DB execution time and app processing. It is already large enough to challenge the **app in cloud, DB on-premises** option when the SLO is close to 1 second. Adding CPU to app VMs will unlikely reduce this 280 ms. Meanwhile, moving a 6 TiB DB requires a data migration plan, consistency verification, and a controlled cutover.

### A reference approach

1. **Discovery:** capture real traces to confirm whether the 20 queries are sequential; map dependencies across the DB, identity, reporting, and batch jobs. Check data requirements and cross-hybrid authentication.
2. **Design:** prioritize placing the app near the DB by dependency group or moving the DB near the app where feasible; if an on-premises identity dependency remains, use redundant hybrid links with timeouts and observability. Do not require a business-logic rewrite yet.
3. **Compute/HA:** deploy an LB and multi-zone VMs if required by the SLO and supported by the app; inspect session state. Design DB replication, backup/restore, and failure domains aligned with RPO/RTO.
4. **Operations:** prepare IaC, least-privilege IAM, end-to-end monitoring, runbooks, and recovery testing. Re-measure p95 at 500 req/s, observed peak load, and under single-component failures.
5. **Cost:** estimate VMs, DB/storage, replication, backups, hybrid links, NAT/LB, logs, and operations; set up budgets/tags and a post-cutover rightsizing plan.
6. **Cutover:** run a pilot, schedule data sync, verify consistency, define the write owner, and prepare safe rollback/roll-forward paths. Decommission only after reconciliation and monitoring meet acceptance criteria.

### Self-check questions

1. Why is moving 12 VMs with the same specs to the cloud insufficient to guarantee the app meets its SLO?
2. If the app spans two zones while the DB is a single instance in one zone, what risk remains?
3. Why must data transfer between cloud and on-premises be factored in when comparing options?
4. Within three months, if refactoring is not possible, what changes can still reduce risk?
5. Which metrics indicate whether trimming VMs yields real savings without harming user experience?

**Answer hints:** (1) latency, I/O/network, DB performance, load distribution, and dependency failures still matter; (2) the DB remains a single point of failure for transactions; (3) it affects latency, reliability, and egress/connectivity bills; (4) improving data placement, routing, IAM, backups, HA, observability, IaC, and runbooks; (5) unit cost alongside transaction success rate, p95/p99, saturation, and availability.

## 12. Checklist for reviewing a rehost plan

### Before migration

- [ ] Business objectives, deadline, success criteria, and measurable SLOs are defined.
- [ ] Dependency map, data flows, ingress/egress, and authoritative data locations are documented.
- [ ] Performance baselines (normal load, peak load, common failures) and current costs are captured.
- [ ] CIDRs, routing, DNS, TLS, firewalls, IAM, and redundant hybrid connectivity (if needed) are verified.
- [ ] Round-trip risks with the DB and synchronous systems in the transaction path are assessed.
- [ ] Failure domain model, RPO/RTO, backup/restore, and realistic DR plans exist.
- [ ] Cost estimates include compute, storage, data transfer, LB/NAT, logs, backups, and parallel-run duration.

### During cutover

- [ ] Pilot/load tests prove SLOs, not just that servers boot.
- [ ] Runbooks, go/no-go checklist, owners, rollback/roll-forward paths, and data protection steps are ready.
- [ ] Transaction-level metrics, logs, traces, and alerts are active; someone is monitoring post-cutover.
- [ ] Network, VM, and DB failures plus backup restores have been tested.

### After cutover

- [ ] Monitor SLOs and costs across sufficient load cycles against the pre-migration baseline.
- [ ] Rightsize from measurements; optimize network flows, IOPS, log retention, and idle resources.
- [ ] Maintain a technical debt list with owners and review dates for replatforming/refactoring if needed.
- [ ] Confirm all dependencies are migrated and data is archived per policy before retiring old resources.

**Key takeaway:** rehosting answers *where the application runs*; cloud architecture must also answer *which network the data traverses, how the system survives failures, who operates it, and what it costs*. When those follow-up questions go unverified, a technically successful migration can still become a performance, reliability, and budget failure.
