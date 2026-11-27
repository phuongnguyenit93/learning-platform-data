# Applying Service Quotas, Budgets, and Organization Policies

## 1. Why Is Resource Governance an Architectural Decision?

A cloud application may work fine during testing yet fail at production scale: the autoscaler fails to launch machines because it hits a **service quota**, costs spike due to forgotten resources, or a development team spins up a database in a disallowed region. These issues happen even when application code has zero bugs. Therefore, **resource organization** is part of architecture design and operations, not merely a post-deployment administrative chore.

In the **CLOUD_ARCHITECTURE** module, translating business requirements into networking, compute, data, and deployment choices must be accompanied by mechanisms protecting **reliability, security, scalability, cost, and operability** goals. Three essential toolsets are:

- **Service quotas/limits:** caps on the number of resources, capacity, or operation rates the platform permits within a given scope.
- **Budgets:** spending targets paired with alerts, forecasts, and response workflows when costs approach or exceed allowed levels.
- **Organization policies/guardrails:** rules governing which actions, locations, configurations, and resource types are permitted.

Running example throughout this lesson: a business operating a booking platform with **development, staging, and production** environments; search traffic spikes seasonally, while booking data requires strict access control and disaster recovery. The numbers below are **study assumptions**, not default quotas or guaranteed pricing from any cloud provider.

## 2. Distinguishing Quotas, Budgets, Policies, and Access Control

| Mechanism | Question answered | Example | What not to assume |
| --- | --- | --- | --- |
| **Service quota** | What is the maximum allowed usage within which scope? | vCPUs per instance family/region, IP count, API requests per second | Does not guarantee physical provider capacity is available; does not grant user permissions |
| **Budget** | How much is being or projected to be spent versus the target? | Alert when end-of-month forecast exceeds budget | Alerts usually do not automatically shut off services or cap billing at the threshold |
| **Organization policy** | Which configurations or actions are permitted? | Block creating production resources outside approved regions | Does not grant IAM permissions to users |
| **IAM/RBAC** | Which identity can perform which actions on which resources? | Dev can view dev logs, cannot delete the production DB | Does not replace quotas or cost forecasting |
| **Application rate limit** | How many requests can a client send to the product's API? | Each account may search 100 times/minute | Does not replace cloud provider quotas on service APIs |

Someone authorized to launch VMs can still hit an error from a quota limit. A project with spare quota can still blow through its budget. A policy banning public resources can reject an action even when the user has IAM permissions and available quota. Thus all three mechanisms must be designed together.

### Types of Limits to Recognize

- **Adjustable quotas:** can be requested to increase, subject to review and available supply; submitting a request does not guarantee approval.
- **Non-adjustable limits:** inherent properties of a service or architecture, which may force partitioning workloads or changing the solution.
- **Count/capacity quotas:** number of instances, vCPUs, IP addresses, volumes, connections, or concurrent jobs.
- **Rate quotas:** number of requests or operations per time window, causing throttling when exceeded.
- **Internal warning thresholds:** team-defined utilization thresholds—such as 70% or 85% of allocated quota—providing lead time before hitting hard caps.

**Quota scope matters:** quotas may apply per account, subscription, project, region, zone, machine family, or individual resource. Names, accounting rules, increase eligibility, and default thresholds vary by provider, service, and time. Always pull exact values at **the actual operating scope** from the provider API/console and official service documentation.

## 3. Designing Organizational Boundaries Before Setting Limits

How resources are partitioned affects security, quotas, accountability, and budget allocation. An organization can use a logical structure like:

~~~mermaid
flowchart TB
    ORG["Organization"]
    ORG --> SHARED["Shared units"]
    ORG --> PROD["Production units"]
    ORG --> NONPROD["Non-production units"]
    SHARED --> LOG["Logging & security account/project"]
    SHARED --> NET["Shared network account/project"]
    PROD --> API["Prod application account/project"]
    PROD --> DATA["Prod data account/project"]
    NONPROD --> STAGING["Staging account/project"]
    NONPROD --> DEV["Dev account/project"]
~~~

This is an illustrative structure. The actual number of accounts/projects depends on team size, isolation needs, policy enforcement model, and quota scoping. There is no need to split every microservice into its own account when operational overhead outweighs the benefits.

| Reason to split scope | Organizational approach | Benefits and trade-offs |
| --- | --- | --- |
| Protect production | Separate production accounts/projects from sandboxes | Reduces accidental damage; adds identity and connectivity management |
| Cost allocation | Partition by product/environment, paired with owner labels | Clearer reporting; shared costs still need allocation rules |
| Consistent policies | Apply guardrails at org group level and appropriate child levels | Reduces drift; requires understanding exact inheritance and exceptions |
| Different quota needs | Group workloads with distinct traffic and risk profiles | Reduces resource contention; never split solely to evade controls |
| Centralized operations | Dedicated owners for logging, security, and network hubs | Easier governance; must avoid single points of failure and overly broad access |

Conceptual examples: AWS has Organizations and accounts; Azure has management groups, subscriptions, and resource groups; Google Cloud has organization, folders, and projects. **These tiers are not strictly equivalent in inheritance, quotas, and denial mechanics.** When implementing a real policy, verify the exact semantics of the target service rather than inferring from generic diagrams.

Resource labels (tags/labels) describe the application, team, environment, and cost center. Labels assist auditing, querying, and bill allocation, but **are not a security boundary replacing IAM, network isolation, and account organization**.

## 4. From Quality Requirements to a Quota Plan

Service limits must be reviewed right when defining peak traffic, scaling, deployment window, and recovery requirements. The method is to forecast **normal demand → peak traffic → deployment/rollout → failure/DR scenarios**, then check quotas across every involved service.

### 4.1. Building a Quota Inventory

For each workload, record:

1. **Service name, quota name, and unit:** instances, vCPUs, IPs, connections, throughput, API calls, concurrent jobs, etc.
2. **Scope:** organization/account/subscription/project, region/zone, or specific resource.
3. **Allocated limit and current utilization:** retrieved from dashboard/API; record source and measurement date.
4. **Demand forecast:** baseline, peak, rollout expansion, cross-region failover, and recovery.
5. **Increase eligibility:** whether the quota is adjustable; whether tickets, lead time, and approvals are needed.
6. **Owner, alerts, and runbook:** who responds and how to mitigate when approaching the limit.

| Quota group | Why it affects architecture | Example failure if ignored |
| --- | --- | --- |
| vCPUs/instances by family and region | Autoscaling, redundancy, and recovery need to launch new instances | Cannot launch instances even as traffic climbs |
| IPs, subnets, network interfaces | Launching compute/endpoints also depends on network resources | vCPUs available, but subnet runs out of IP addresses |
| DB connections, storage, IOPS/throughput | Data services have separate capacity ceilings that do not scale automatically with app tiers | Scaling app instances exhausts the DB connection pool |
| Managed service requests/API rates | Batch jobs, deployments, or retries can trigger throttling | API throttling hits right during recovery |
| Queue, job, and concurrency limits | Impacts asynchronous processing latency | Large backlog builds even when app servers are idle |
| Logging, security, and networking quotas | Observability and controls require accompanying resources | Unable to create monitoring rules or backup endpoints |

### 4.2. Compute Demand Calculation Example

Suppose load testing confirms one instance sustainably handles **40 requests/second** while meeting the p95 target. Peak traffic forecast is **600 requests/second**. The team decides to add **20% spare instance headroom** over theoretical demand.

~~~text
Instances needed for peak = ceil(600 / 40) = 15
Target instances after headroom = ceil(15 * 1.20) = 18
~~~

The figure 18 is the **serving instance count in this illustrative scenario**, not a quota you should set to exactly 18. If rolling deployments require 6 temporary extra instances, peak verification demand reaches **24 concurrent instances**. Moreover, surviving an availability zone loss may require launching extra instances in remaining zones. You must therefore evaluate quotas across vCPUs and machine families, IPs, load balancers, volumes, DB connections, and dependent quotas. This calculation does not yet account for startup time, post-failover performance, or autoscaler reaction speed.

**A quota is not a capacity reservation.** Even with a high enough limit, a region/zone may lack available physical capacity or the required instance type. Resilience also demands fallback instance-family strategies, multi-zone/multi-region distribution, network/data capacity, and provisioning drills.

### 4.3. Responding When Approaching Limits

Quota utilization must be monitored alongside overload and provisioning failures. Common technical measures include:

- Retries with **backoff, jitter, and max retry caps**, distinguishing transient errors from non-retryable failures.
- Queuing and **backpressure** to avoid crashing downstream dependencies under load spikes.
- Timeouts and **circuit breakers** on synchronous paths so one congested dependency does not trigger cascading failures.
- **Idempotency** on repeatable operations so retries do not create duplicate resources or transactions.
- Alerts before quota exhaustion and owner-assigned runbooks, instead of waiting for the autoscaler to fail.

## 5. Quota Governance in Operations and Recovery

A quota governance record might look like this:

| Attribute | Illustrative value |
| --- | --- |
| ID | Q-COMPUTE-PROD-01 |
| Workload/owner | Search API / Platform SRE |
| Quota/scope | Target machine family vCPUs in production region |
| Current quota limit | Pending verification from provider API/console |
| Demand | 18 peak instances with headroom; up to 24 during rollout |
| Operational thresholds | 70% review, 85% priority action; illustrative thresholds |
| Plan | Check related quotas, submit increase requests if needed, test scaling |
| Evidence | Load tests, quota dashboard, quota increase tickets, drill results |

Operational lifecycle:

1. **Before deployment**, reconcile quotas and demand at the exact region, environment, resource group, and timing; check every dependency along the deployment path.
2. **Before peak season**, compare peak load with dependency capacity, refresh forecasts, file quota increase requests early enough, and prepare a fallback if an increase is denied.
3. **After an increase is approved**, re-read the live quota; a submitted ticket does not mean the quota has actually changed.
4. **During operations**, alert on utilization and throttling errors, auditing quotas that grow rapidly or have caused past incidents.
5. **Before DR drills**, check separate quotas in the standby region, provisioning permissions, IP/vCPU counts, DB restore permissions, and required storage.

Do not raise every quota unconditionally thinking it is safest. Too-low limits break scaling; overly loose limits paired with weak IAM raise consumption and cost risks. Limits are just **one protective layer** in the architecture.

## 6. Budgeting and Accountable Cost Allocation

Budgets must tie to business goals, estimated load profiles, and cost-decision owners. A single server's sticker price does not represent total lifecycle cost.

~~~text
Cloud cost to forecast =
    compute + database + storage
  + networking, NAT/load balancers, and egress data transfer
  + logs/metrics/traces, security, keys, and auditing
  + backups, replication, DR, and recovery
  + support plans, licensing, and related operations
~~~

An illustrative budget plan for the booking system is **15,000 USD/month**:

| Line item | Forecast USD/month | What to verify |
| --- | ---: | --- |
| Compute and app services | 5,000 | Average/peak load, autoscaling, idle capacity |
| Databases and storage | 3,500 | Volume, growth rate, read/write ops, backups |
| Networking and data transfer | 2,000 | Egress, NAT, cross-zone/cross-region traffic, internal traffic |
| Logging, monitoring, security | 1,000 | Metric count, logs/traces, retention, and auditing |
| Backup and DR | 1,500 | Replicas, cross-region data, recovery drills |
| **Projected operating total** | **13,000** | Must re-measure once live system runs |
| **Budget contingency buffer** | **2,000** | Planning variance, not an automatic fee |
| **Target budget** | **15,000** | Includes shared-cost allocation plan |

Explicitly document assumptions for load, data size, growth, regions, services, support fees, and taxes/exchange rates if applicable. Maintain at least **three scenarios: normal, peak season, and incident/DR**; a single major restore or load test can push spend above normal daily levels.

### 6.1. Allocation by Environment and Owner

| Scope | Example budget USD/month | Accountable owner |
| --- | ---: | --- |
| Production | 10,000 | Product Owner and SRE |
| Staging | 3,000 | QA/Platform |
| Development | 2,000 | Engineering Manager |
| **Total** | **15,000** | Consolidated by Finance/FinOps |

Shared costs such as a network hub, centralized logging, backups, or support require a consistent allocation method. You can allocate proportionally by usage, resource count, environment, or approved financial rules. Avoid **double counting** and avoid omitting untaggable charges.

A label taxonomy might include:

| Label | Example values | Purpose |
| --- | --- | --- |
| environment | prod, staging, dev | Separate lifecycles and risk profiles |
| application | booking-platform | Attribute spend to products |
| team | reservations | Owning team |
| cost-center | CC-104 | Financial allocation |
| data-classification | confidential | Support data policies |
| managed-by | terraform | Identify resource declaration source |

Not every service supports labels on every resource or every billing line item. Cost allocation must combine **account/project structure, billing exports, valid tags/labels, and shared-cost allocation rules**. Never put secrets or personal information in labels.

### 6.2. Alerts Do Not Equal Hard Spending Caps

A reference escalation workflow:

- **50% actual budget:** compare elapsed days in the month against expected burn; verify planned campaigns or load tests.
- **80% actual or forecast:** alert the application owner and FinOps; analyze cost drivers, forgotten resources, egress, retention, and recent changes.
- **100% or forecast over target:** trigger formal justification and approved adjustment workflow; prioritize preserving critical services and data obligations.

The 50/80/100% levels are **illustrative thresholds** only. Spending 80% on the last day of the month differs from hitting 80% on day three. Combine actuals, forecasts, burn rate, and anomaly detection; billing data itself may lag.

**Budget alerts usually do not stop resources or cap bills.** If you must prevent high-cost actions, combine permission limits, policies, approval workflows for large machine/resource types, or carefully designed and tested automation. Never automatically shut down production or DR solely on a budget alert when doing so would breach SLOs, RTOs, or data protection requirements.

## 7. Organization Policies: Turning Rules into Guardrails

**Organization policies** constrain how resources are created and used within a governance scope. Policies must derive from **concrete obligations, risks, or operational goals**. A rule like "all resources must be secure" is too vague to verify; a rule like "no database holding customer data may expose a public endpoint in production" is testable.

### 7.1. Policy Categories to Consider

| Category | Example rule | Things to watch |
| --- | --- | --- |
| Deployment location | Data classified confidential may only be processed in approved regions | Account for logs, backups, replicas, and supporting systems too |
| IAM and admin access | Only ops roles may alter/delete production databases, using strong authentication | Org-level restrictions do not grant IAM permissions |
| Network security | Production databases must not have direct Internet endpoints | Check routes, firewalls, endpoints, DNS, and valid connectivity exceptions |
| Encryption and secrets | Sensitive data encrypted in transit/at rest; secrets stored in a secrets manager | Requires key management, rotation, auditing, and recovery procedures |
| Compute standards | Only vetted images and machine families in production; size caps in sandboxes | Avoid accidentally blocking approved failover machine types |
| Tagging | Taggable resources must carry environment, application, team, cost-center | Some services do not support tags at creation or billing by tag |
| Logging and auditing | Enable audit logs for admin actions; retain logs for approved duration | Minimize superfluous sensitive logging and protect logs from tampering/deletion |
| Critical resource protection | Deny deleting backups or production DBs outside approved workflows | Must preserve a safe break-glass path for incidents |

Capabilities of **organization-level policies** and **IAM** are not identical. For example, in AWS, Service Control Policies (SCPs) cap the maximum permissions principals in scope can use; SCPs **do not grant IAM permissions**. On other platforms, a policy may deny creating misconfigured resources or evaluate compliance state. When implementing, verify **supported resource types, inheritance rules, evaluation order, exemptions, and impact on existing resources**.

### 7.2. Preventive, Detective, and Corrective

| Control layer | How it works | Illustration |
| --- | --- | --- |
| **Preventive** | Rejects non-compliant configs/actions at creation or inside the pipeline | Block creating a production database with public access |
| **Detective** | Scans and alerts on non-compliant state, including legacy resources | Detect a bucket missing an owner or disabled audit logs |
| **Corrective** | Opens tickets, runs runbooks, or auto-remediates within allowed scope | Remove unauthorized public config, notify owner, archive evidence |

Checking IaC in CI/CD alone is insufficient because users can still make console/API edits or legacy resources may exist outside code. Conversely, relying solely on cloud-side policies gives developers feedback too late. Combine **pre-deploy checks, deploy-time guardrails, and post-deploy drift monitoring**.

### 7.3. Expressing Policies as Data

The example below is a **vendor-neutral specification for discussion**, not syntax directly deployable to AWS, Azure, or Google Cloud:

~~~yaml
policyId: GOV-REGION-01
description: Restrict deployment regions for confidential data
scope:
  environment: prod
  dataClassification: confidential
rule:
  when: resource.region NOT_IN approvedRegions
  effect: DENY
approvedRegions:
  - region-a  # Illustrative name; replace with actual approved regions
owner: cloud-platform-team
evidence:
  - policy-evaluation-log
  - compliance-report
exception:
  approver: security-owner
  reasonRequired: true
  expiryDateRequired: true
  auditRequired: true
~~~

When translating this rule into policy-as-code, verify how the platform treats **global services**, special-region resources, resources spawned by managed services, and backup/log data. A blanket rule denying all other regions can accidentally break platform services or legitimate DR flows if untested.

## 8. Rolling Out Policies with Control and Exceptions

Overly broad policies disrupt operations; policies easy to bypass protect nothing. For rules affecting multiple accounts/projects, follow these steps:

1. **Identify objective and source:** which security requirement, contract obligation, cost rule, or operational constraint motivates the policy?
2. **Inventory current state:** how many existing resources fail compliance, and do any services lack support for the condition?
3. **Test in nonproduction:** validate both allowed and disallowed actions, pipelines, backups, config edits, and DR drills.
4. **Use audit/dry-run mode if supported:** observe blast radius before enabling hard denies.
5. **Roll out by scope:** start on one group of resources/accounts, watch for errors, and support remediation.
6. **Monitor and review:** track policy evaluations, direct edits, exceptions, and false-positive blocks.

### What Must an Exception Record Capture?

An exception must contain at minimum **policy ID, scope, workload, justification, risk, compensating controls, approver, expiration date, and revocation check**. For instance, to temporarily open an endpoint for an integration partner, restrict source IP, duration, data types, and logging. Upon expiration, revoke or re-review; never let temporary exceptions become permanent privileges.

For emergency access (*break-glass*), the organization needs specially protected accounts/procedures, audit logging, and post-incident review. Test this procedure alongside backups and recovery; never craft policies so rigid that approved recovery actions become impossible.

### Reference Responsibility Split

| Role | Responsibilities |
| --- | --- |
| Product Owner | Confirm business priorities and impact of restrictions |
| Platform/Cloud Engineering | Design resource boundaries, automation, quota monitoring, policy-as-code |
| SRE/Operations | Capacity forecasting, failover readiness, alerting, runbooks, and drills |
| Security/Compliance | Audit data controls, approve sensitive policies and exceptions |
| Finance/FinOps | Cost forecasting/monitoring, allocation, and budget anomaly handling |
| Application owner | Apply labels, justify resources, fix violations, and maintain acceptance criteria |

## 9. Combining Quotas, Budgets, and Policies Across the Architecture Lifecycle

Sound limit decisions must also consider effects across **compute, networking, data, security, and operations**:

~~~mermaid
flowchart TD
    A["Business goals, SLOs, and data constraints"]
    A --> B["Organization structure and resource boundaries"]
    B --> Q["Quotas and capacity planning"]
    B --> C["Budgets, tagging, and cost allocation"]
    B --> P["Policies, IAM, and exception workflow"]
    Q --> D["IaC, CI/CD, and change control"]
    C --> D
    P --> D
    D --> W["Running workloads"]
    W --> M["Telemetry: quotas, cost, audit, SLIs"]
    M --> R["Review and adjust"]
    R --> A
~~~

### Four Scenarios Showing Coordination

**Scenario A — seasonal traffic spike:** the autoscaler needs more compute. SRE checks quotas **ahead** of the campaign, combining load tests with increase requests; Finance reviews the cost forecast, while policies permit the approved machine families and regions. If a size-cap rule blocks legitimate capacity, get an approved policy update before peak arrives.

**Scenario B — wrong deployment region:** a team creates a database in an unapproved region. Quota is available and budget is not yet breached, so policies must block or detect it, verify whether any data crossed boundaries, and log remediation. Then add an equivalent check to the pipeline.

**Scenario C — budget overrun during incident recovery:** DR requires spinning up standby compute, networking, and data restoration. Budgets fire alerts so owners acknowledge the spend; do not auto-halt recovery flows and violate RTO/RPO. Budget and provisioning exceptions should be decided and recorded.

**Scenario D — insufficient DR quota:** diagrams show standby capacity in another region, yet the standby account lacks enough vCPU, IP, or DB quota. Teams must verify quotas **in each target region and real scope**, confirm provisioning capability, restore rights, and ensure policies do not block failover; then drill to measure actual RTO/RPO.

### Traceability Matrix: Requirement → Control → Evidence

| Requirement | Quotas to verify | Cost/budget | Policy/IAM | Evidence |
| --- | --- | --- | --- | --- |
| Search sustains 600 rps | vCPUs, IPs, LB, DB connections, API rates | Peak forecast and scaling cost | Allowed regions and machine families; autoscaler role | Load tests, quota dashboard, test billing |
| Prevent booking data leaks | Quotas do not enforce security | Audit, encryption, retention costs | Private endpoints, IAM, key policies, audit | Access tests and config assessments |
| RTO 2 hours / RPO 15 minutes | DR region resources, backup/restore, APIs | Backup, replication, standby, drill costs | Approved recovery roles and scopes | DR drill logs, actual recovery time and point |
| Target cost 15,000 USD/month | Cap sandbox sizes where appropriate | Budgets by owner, actual, forecast, anomaly alerts | Mandatory owner/tags, approvals for large resources | Billing reports and decision records |

Tie each requirement to **an owner and review date**, especially load and cost assumptions. Tagging resources or building dashboards does not turn a requirement into an effective control by itself; verify outcomes.

## 10. Evaluating with Well-Architected Thinking

| Pillar / perspective | Questions to evaluate |
| --- | --- |
| **Operational Excellence** | Are owners, runbooks, change control, policy tests, and workflows for quota/budget alerts in place? |
| **Security** | Do data-location policies, IAM, encryption, logging, auditing, and exceptions align with confirmed risks? |
| **Reliability** | Are quotas/capacity sufficient for peak, rollouts, and recovery; have zone loss, link loss, and provisioning denials been tested? |
| **Performance Efficiency** | Do limits hinder autoscaling, create DB/API bottlenecks, or trigger retry storms? |
| **Cost Optimization** | Are costs allocated to owners, idle resources optimized, anomaly alerts active, and multi-scenario forecasts built? |
| **Sustainability** | Are capacity utilization and data/log retention managed to avoid long-term idle waste? |

Raising quotas can improve resilience while increasing potential maximum spend. Locking down machine types/regions helps control spend or data residency but may impair performance or DR options. Therefore, **trade-offs must be approved based on real needs and evidence**, not rigid blanket rules.

## 11. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Checking quotas only in the primary region | Cannot provision infrastructure in the DR region | Inventory per region/scope and run failover tests |
| Confusing quota with guaranteed capacity | Autoscaler still fails when physical capacity is tight | Maintain fallback machine strategies, headroom, and drills |
| Assuming budgets stop bills | Spend continues rising past the threshold | Combine actuals, forecasts, approval gates, and dedicated controls |
| Relying on labels to isolate access | Misprivileged users can still access resources | Enforce IAM, network isolation, and active policies |
| Blocking regions/resource types without testing DR | Cannot spin up recovery resources | Test policies against failure scenarios with controlled exceptions |
| Leaving alerts without owners | Alerts get ignored or go unhandled | Assign on-call owners, escalation, handling SLOs, and runbooks |
| Counting only compute prices | Egress, logs, backups, and support blow the budget | Build multi-scenario TCO and reconcile against bills |
| Raising quotas to solve every performance bug | DB, algorithms, or retries remain bottlenecks | Measure saturation, analyze bottlenecks, and optimize the app |
| Turning on org-wide denies immediately | Breaks legacy environments and automation | Inventory, test narrowly, monitor, then expand enforcement |

## 12. Practice Exercise: Governing the Booking Platform

**Prompt:** the search system must sustain a 600 requests/second peak. Benchmark testing shows one instance handles 40 requests/second at the required SLO; add 20% spare headroom over required instances. Rolling deployments may use 6 temporary extra instances. The team must deploy in a primary region with a DR plan in another region. Assumed budget is 15,000 USD/month; customer data may only be processed in approved regions.

**Deliverables:**

1. **Draw the resource structure:** separate production, staging, development, and shared logging/networking; explain permission, quota, policy, and cost-ownership boundaries.
2. **Calculate capacity:** peak serving instances, headroom, and rollout needs; list other quotas that can still block deployment even with sufficient compute.
3. **Create six quota records:** cover compute, IP/network, database, queues, APIs, and the DR region. For each record, state scope, allocated limit (to verify), utilization, owner, alert thresholds, and response actions.
4. **Propose a budget:** split across environments and explain how logging, egress, and backups are allocated; design actual, forecast, and anomaly alerts.
5. **Propose four policies:** restrict regions, production database deletion rights, public endpoint controls, and cost-tagging standards; specify enforcement, verification, and exception mechanisms.
6. **Run a tabletop drill:** simulate the autoscaler failing due to quota and DR recovery blocked by policy. Measure detection time, impact, remediation, and recovery-target feasibility.
7. **Write an architecture decision record:** state choices, residual risks, approvers, mandatory tests, and review date.

### Evaluation Rubric

| Criterion | Signs of mastery |
| --- | --- |
| Quota accuracy | Distinguishes quota scopes and types; accurately computes 15 base instances, 18 target with headroom, and 24 during illustrative rollout |
| Reliability fit | Includes dedicated DR checks, dependency limits, zone-loss scenarios, and recovery testing |
| Governability | Defines owners, alert thresholds, runbooks, and quota-increase/exception workflows |
| Financial clarity | Covers actual vs. forecast, shared costs, peak/incident scenarios, and does not mistake alerts for spend caps |
| Security | Applies policies at right scopes, includes test evidence and paths for handling false-positive blocks |
| Traceability | Links controls to approved business, quality, or compliance requirements |

## 13. Pre-Production Checklist

- [ ] Account/project/environment structure and owners for every resource group are defined.
- [ ] Critical quotas are recorded at exact scopes and regions, identifying which ones are adjustable.
- [ ] Normal, peak, rollout, failover, and data-recovery demand are forecasted.
- [ ] Quota alert thresholds and increase-request or denial-mitigation plans exist.
- [ ] Owner-scoped actual/forecast budgets, shared-cost allocation policies, and anomaly alerts are active.
- [ ] Budget alerts are not mistaken for hard spending caps.
- [ ] Risk-based rules cover data, regions, IAM, networking, auditing, labels, and resources.
- [ ] Policies are tested against allowed actions, disallowed actions, deployments, and DR.
- [ ] Exceptions are approved, time-bound, audited, and paired with revocation steps.
- [ ] IaC/CI/CD checks, drift detection, and post-deployment monitoring are integrated.
- [ ] Trade-offs across reliability, security, performance, cost, and operations are documented.

**Core takeaway:** quotas answer **"how much maximum can we use?"**, budgets answer **"how does spend compare to target?"**, and organization policies answer **"what is allowed and must be complied with?"**. Combining all three along resource boundaries—backed by measurements, owners, alerts, test evidence, and an exception process—enables a cloud architecture to **scale, operate, and recover under control**.
