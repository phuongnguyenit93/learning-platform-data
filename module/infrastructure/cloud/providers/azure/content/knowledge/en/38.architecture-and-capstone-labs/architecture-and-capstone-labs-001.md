# Evaluating Architecture with Azure Well-Architected Review

## 1. Why Is a Working Architecture Not Necessarily a Good One?

An application can be successfully deployed to Microsoft Azure, return HTTP 200, and handle initial test traffic while still having serious weaknesses: the database lacks an appropriate recovery mechanism, all components depend on a single zone, administrative permissions are overly broad, deployments must be done manually, costs have no accountable owner, or the system cannot withstand sudden request spikes. Those issues usually surface only during an incident or when scaling up.

In the **Architecture and Capstone Labs** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lesson guides you through evaluating a **workload** on Azure using the **Azure Well-Architected Framework** and the **Azure Well-Architected Review** process. It synthesizes knowledge across subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, data, deployment, security, monitoring, and cost control.

**The goal is not to get a high score on a questionnaire**, but to uncover real architectural risks, prove them with evidence, and choose improvements that deliver the greatest value relative to effort, cost, and change risk.

After this lesson, you can:

1. Define workload boundaries, owners, critical journeys, and non-functional requirements before an evaluation session.
2. Explain and apply the **five pillars** of Azure Well-Architected: Reliability, Security, Cost Optimization, Operational Excellence, and Performance Efficiency.
3. Use the Well-Architected Review process to perform a self-assessment, document assumptions, link evidence, and review recommendations.
4. Cross-check answers against telemetry, configuration, testing, and supporting tools such as Azure Advisor, Azure Monitor, and Azure Policy.
5. Build a risk register, prioritize remediation, and construct a roadmap with owners, acceptance criteria, and ways to measure effectiveness.
6. Perform a capstone evaluation for a multi-tier application and present trade-offs across reliability, performance, security, and cost.

## 2. What Are the Azure Well-Architected Framework and Review?

The **Azure Well-Architected Framework (WAF)** is a set of principles, design guidelines, and evaluation methods aimed at improving workload quality on Azure. The **Azure Well-Architected Review** is a structured self-assessment based on the framework's pillars: the team answers questions about workload design and operations, reviews the provided recommendations, and builds an improvement plan.

Key distinctions:

| Component | What is it used for? | Do not misunderstand as |
| --- | --- | --- |
| **Well-Architected Framework** | Design principles and trade-off considerations across five pillars | Not an Azure SKU or a service that automatically fixes architecture |
| **Well-Architected Review** | Assessment questionnaire to identify gaps and receive recommendations | Does not automatically verify all configurations, nor certify security or compliance |
| **Azure Advisor** | Provides recommendations based on supported Azure resources/signals | Does not replace assessing business requirements and end-to-end workload dependencies |
| **Azure Policy** | Audits/enforces governance rules according to definitions and scope | Compliant resources do not guarantee the application meets SLO/RPO |
| **Azure Monitor / Application Insights** | Provides metrics, logs, traces, alerts, and operational evidence | Does not automatically conclude that every architectural decision is sound |
| **Team architecture review** | Validates using system knowledge, processes, tests, and governance decisions | Should not rely solely on personal opinion or a single dashboard |

Answers in a Well-Architected Review are a **self-assessment**: if the team selects "disaster recovery is in place" without ever restoring a backup or testing failover, the review result does not prove DR meets requirements. Every critical recommendation should be linked to **evidence or a test**.

### 2.1. Why Evaluate at the Workload Level?

A workload is a collection of components that together serve a business outcome, and it does not necessarily align with a single resource group or subscription. For example, an `orders` workload includes:

- An API in an application resource group.
- Azure SQL or a database in a data resource group.
- Azure Front Door/ingress and Azure Firewall managed by the platform team.
- A shared Azure Monitor workspace and Key Vault.
- CI/CD, Microsoft Entra ID authentication, and an external payment provider.

If you look only at the API VMs, the team will miss failure points in the database, routing, secrets, identity, or payment service. Therefore, you must **define the workload before evaluating**, and treat subscriptions/resource groups as technical boundaries within the architecture.

### 2.2. When Should You Perform a Review?

Perform one at least at milestones with major design decisions:

- Before releasing a new system to production.
- Before a major migration or architectural shift from VMs to PaaS/AKS.
- After a severe incident, data error, security event, or SLO breach.
- When traffic grows rapidly, costs exceed forecasts, or the workload's criticality changes.
- On an operational cadence based on business risk.

A review can lead to a decision **not to make changes** if current choices have supporting evidence and fit requirements. The objective is deliberate decision-making, not adopting every best practice at any cost.

## 3. Five Pillars of Azure Well-Architected

~~~mermaid
flowchart TB
    W["Workload and business goals"] --> R["Reliability"]
    W --> S["Security"]
    W --> C["Cost Optimization"]
    W --> O["Operational Excellence"]
    W --> P["Performance Efficiency"]
    R --> G["Risks, trade-offs, and improvement plan"]
    S --> G
    C --> G
    O --> G
    P --> G
~~~

| Pillar | Core question | Typical evidence |
| --- | --- | --- |
| **Reliability** | When a component fails, does the service continue or recover within targets? | SLO, health probes, availability zones, backup restore, DR test, RTO/RPO |
| **Security** | Are data and access protected throughout their lifecycle? | Threat model, RBAC, identity, secret management, encryption, audit, vulnerability findings |
| **Cost Optimization** | Is the organization paying the right amount for the value and required usage? | Cost Analysis, budget, unit cost, utilization, reserved capacity, ownership |
| **Operational Excellence** | Can the system be deployed, observed, incident-handled, and changed safely? | IaC, pipeline, runbook, alert, postmortem, deployment/rollback evidence |
| **Performance Efficiency** | Does the system meet current and future load with appropriate capacity? | Load test, p95/p99, throughput, autoscale, quota, bottleneck analysis |

No single pillar "wins" absolutely. You may need to **pay extra for redundant zones to achieve Reliability**, or keep headroom to protect latency when a zone fails; that is a reasonable trade-off if measured and approved.

### 3.1. Reliability: Does the Application Survive When Failures Occur?

Sample questions:

1. Are SLI/SLO and RTO/RPO defined in line with business priorities?
2. Which failures are tolerable: a single process, a VM, an Availability Zone, a region, or an external dependency?
3. Is compute distributed across zones/regions where the service supports it? Does ingress route traffic away from unhealthy backends?
4. Do databases, storage, and queues have appropriate, tested redundancy/failover policies?
5. Are backup/restore, DR drills, data recovery steps, and protection against logic errors/accidental deletion in place?
6. Do clients implement bounded retries, exponential backoff, jitter, and idempotency for write transactions?
7. Is there enough capacity to handle traffic after losing a zone, or will the remaining instances become overloaded?

**Example:** App Service has zone redundancy in a supported configuration, but the database has only a single serving point or ingress DNS points directly to one VM. Concluding that "the workload is multi-zone" is **inaccurate end-to-end**.

### 3.2. Security: Protecting Data, Identity, and Permissions

Sample questions:

1. Are data classification and threat modeling in place for critical attack paths?
2. Do Entra ID/RBAC permissions follow least privilege, separate production/non-production, and undergo periodic review?
3. Does the workload use Managed Identity or managed authentication where possible instead of hard-coded secrets?
4. Are secrets/keys managed in Key Vault or an appropriate mechanism with rotation, auditing, and restricted access?
5. Is the network clearly segmented: public ingress, private endpoints, NSGs, firewall, egress, and appropriate DNS?
6. Are TLS/encryption per service, policies, and protection for data at rest and in transit enabled?
7. Are dependency updates, image scanning, vulnerability management, pipeline hardening, and incident response processes in place?

**Example:** Using a Private Endpoint for Azure SQL while a service principal still holds overly broad permissions and the password sits in an unprotected pipeline variable. Private networking reduces only one group of risks; it **does not replace** identity and credential protection.

### 3.3. Cost Optimization: Is Total Cost Commensurate with Value?

Sample questions:

1. Does each workload have a clear owner and cost allocation scope?
2. Are budgets/alerts sufficient to detect rapid cost increases, with someone accountable to act?
3. Are compute, database, storage, network, and monitoring rightsized based on actual utilization?
4. Do you know the cost per successful transaction, completed job, or business unit?
5. Are steady baseline workloads evaluated for Reservations/Savings Plans using eligible hourly usage data?
6. Have shared costs, egress costs, backup/replication, and unused commitments been accounted for?
7. Do cost-saving optimizations impact SLO, RTO/RPO, or security requirements?

**Example:** Reducing replicas from three to one may cut compute spend but break Availability Zone fault tolerance. A good review **weighs financial savings against downtime risk**, rather than marking an improvement solely because the bill dropped.

### 3.4. Operational Excellence: Can It Be Operated Repeatably and Safely?

Sample questions:

1. Is infrastructure managed with Bicep/Terraform/ARM or controlled configuration management?
2. Does CI/CD include reviews, testing, staged rollouts, and verified rollback?
3. Are logs, metrics, traces, synthetic tests, and alerts tied to critical SLIs?
4. Do on-call, incident severity, runbooks, Azure Support escalation, and post-incident reviews have owners?
5. Are drift, configuration, quotas, certificates, backups, and permission changes managed?
6. Are new environments validated for operability and tested through game days?
7. Is automation safe, idempotent, and tracked with an audit trail?

**Example:** The team claims "5-minute rollback," yet rollback requires a specialist to edit DNS manually and has never been rehearsed. That is an **unverified assumption**, not an established capability.

### 3.5. Performance Efficiency: Meeting Load with Appropriate Resources

Sample questions:

1. Are p95/p99 response time and throughput targets defined for critical journeys?
2. Has load testing covered normal, peak, burst, and single-zone failure scenarios?
3. How are bottlenecks in CPU, memory, disk, network, connections, throttling, database queries, and cache measured?
4. Does autoscale use the right metrics, cooldown, and capacity floor; do quotas/instance limits support it?
5. Are async/queue patterns, caching, or data partitioning applied appropriately?
6. Have cross-region performance, downstream latency, and egress costs been checked?
7. When scaling out, does performance scale proportionally or does a centralized dependency become a bottleneck?

**Example:** Increasing VM size may improve CPU headroom but will not fix an exhausted database connection pool or capped IOPS. Measure the **actual bottleneck** before deciding how to scale.

## 4. Required Inputs Before the Review Session

Do not open the questionnaire before the team agrees on business needs. A quality review requires a **workload profile**.

### 4.1. Sample Workload Profile

~~~yaml
workload:
  name: orders-prod
  business_owner: "Orders Product Lead"
  technical_owner: "SRE and Orders Engineering"
  criticality: "Business-critical (assumed)"
  environments:
    - production
    - staging
  primary_region: "<azure-region>"
  subscriptions:
    - "<subscription-id>"
  primary_journeys:
    - "Create order and confirm payment"
    - "View order status"
  dependencies:
    - "Azure ingress"
    - "Application compute"
    - "Azure SQL database"
    - "Queue/worker"
    - "Azure Storage"
    - "Microsoft Entra ID / Key Vault"
    - "Payment provider"
  objectives:
    availability_slo: "99.9% per month, assumed"
    api_p95_latency: "< 500 ms at design load, assumed"
    rto: "30 minutes, assumed"
    rpo: "5 minutes for data permitted to be lost, assumed"
  business_constraints:
    - "No duplicate payment transactions"
    - "Personal data is protected"
    - "Costs stay within approved budget"
~~~

This is a **simulated requirements template** for discussion, not a YAML file automatically imported or exported by Azure Well-Architected Review. Replace the targets with commitments approved by the business owner. If the business cannot tolerate losing confirmed transactions, a **5-minute RPO** may be unsuitable for that flow; classify data and design reconciliation separately.

### 4.2. Mapping Boundaries and Critical Paths

~~~mermaid
flowchart LR
    U["Customer"] --> FD["Azure ingress / WAF"]
    FD --> API["Orders API"]
    API --> DB["Azure SQL"]
    API --> Q["Queue"]
    Q --> WK["Worker"]
    WK --> ST["Blob Storage"]
    API --> PAY["External payment provider"]
    API --> KV["Key Vault / Managed Identity"]
    OPS["IaC / CI-CD / On-call"] -.-> API
    OBS["Azure Monitor / App Insights"] -.-> FD
    OBS -.-> API
    OBS -.-> DB
~~~

This diagram does not yet indicate which components are truly zone-redundant or use private endpoints; all such attributes must be recorded from the **actual deployment**. Mark trust boundaries (Internet, VNet, PaaS, third-party), what data traverses each path, and access permissions at every step.

### 4.3. Document and Evidence Checklist

| Fact | Owner | Evidence or source |
| --- | --- | --- |
| Current architecture, dependencies, traffic flow | Solution architect | Reviewed diagrams, network/data flow |
| SLA/SLO, business criticality, RTO/RPO | Business + SRE | SLO document, test reports |
| Subscription, resource group, region, SKU | Platform | Resource inventory, IaC |
| RBAC, identities, access paths, secrets | Security | Role assignments, identity audit, policy compliance |
| Availability/backup/failover | Platform + DBA | Health probes, backup restore, DR drill |
| Deploy/rollback/runbook | Engineering | CI/CD configuration, incident records |
| Performance, capacity, quota | SRE | Load test, p95/p99, autoscale, service metrics |
| Cost, unit economics, budgets | FinOps | Cost Analysis, cost exports, budget alerts |

Collect only what is necessary. **Do not** place passwords, client secrets, API tokens, connection strings with credentials, or raw personal data into review forms or architecture tickets.

## 5. Preparing a Well-Architected Review Session

A workshop does not need to be huge, but it must include people who know the truth across all layers.

| Role | Decisions / areas to verify |
| --- | --- |
| **Business/Product owner** | Business goals, criticality, acceptable cost |
| **Solution architect** | Workload boundaries, trade-offs, and recommendations |
| **App/Data owner** | Code, dependencies, data correctness, database resilience |
| **Platform/Cloud engineer** | Azure subscriptions, network, IaC, quotas, operations |
| **Security/IAM lead** | Threat model, RBAC, Entra ID, network/security controls |
| **SRE/Operations** | SLO, monitoring, incident response, RTO/RPO, and drills |
| **FinOps** | Cost, efficiency, commitments, and budgets |

Assign a **facilitator** to keep to the criteria and a **scribe** to record evidence, assumptions, debates, and actions. Workload owners must be able to revise answers when evidence shows reality differs from the initial description.

### 5.1. Distinguishing Facts, Assumptions, and Targets

For every answer, use three statuses:

- **Verified:** up-to-date evidence exists and can be linked.
- **Assumed:** the team believes it is true, but lacks a test or sufficient evidence.
- **Not implemented / Gap:** the corresponding control or architecture is not in place.

You may add **Not applicable** if a question is genuinely out of scope, with an explanation. Do not mark "not applicable" just to avoid a difficult finding.

For example, "Backup enabled" is proven by backup configuration. "Recovery works within RTO" requires evidence from a **restore drill and measured elapsed time**; these two statements are not equivalent.

## 6. Process for Using Azure Well-Architected Review

The interface and question set may evolve across versions, but the workflow is repeatable:

1. Open the **Azure Well-Architected Review** experience provided by Microsoft via the Azure Well-Architected documentation. Read the guidance on scope and assessment modes at the time of use.
2. Create or select an assessment for the **right workload**; name it clearly for tracking, such as `orders-prod / 2026-11 / baseline`.
3. Select the relevant pillars/question sets and agree on scope. Evaluate all **five pillars** when you want a comprehensive view, or document why a single pillar is targeted.
4. Answer each question based on the **currently running** architecture, not what is planned for next quarter.
5. Record **evidence** in your working document: dashboard links, test runs, policy/architecture records, verification date, and owner.
6. Review the recommendations provided by the Review; evaluate their relevance to the workload, priority, and practical trade-offs.
7. Export/save results using whatever option the current Review experience provides, or record results in the team's **risk register/decision log** if export options differ.
8. Turn findings into an improvement backlog with owners and acceptance criteria; schedule a **re-review** after major changes.

**A Review is a question-based assessment; it does not mean the tool has scanned every resource in your subscription.** To verify real resources, use appropriate inspection tools and attach facts to each finding.

### 6.1. Example of an Evidence-Backed Response Sheet

| Equivalent internal question | Actual answer | Confidence level | Evidence | Finding |
| --- | --- | --- | --- | --- |
| "Is there an SLO?" | 99.9% SLO exists for order placement endpoint | Verified | SLI dashboard + SLO doc | No error-budget alerting yet |
| "Is there zone fault tolerance?" | API is multi-zone; SQL zone HA unverified | Assumed / Gap | API IaC, missing DB config | Risk of single-zone outage impacting order writes |
| "Is DR in place?" | Backups running, restore never tested | Gap | Backup jobs, no drill report | RTO/RPO unverified |
| "Do accounts use least privilege?" | Role assignments exist, but production operators have broad rights | Verified | Sanitized RBAC export | Reduce permissions and split roles |
| "Are costs tracked?" | Subscription budget exists, no workload unit cost | Verified + Gap | Cost Analysis and budget config | Missing workload-level showback |

The questions in the table are **illustrative internal questions**, not verbatim quotes from any specific version of Azure Well-Architected Review.

### 6.2. When Answers Contradict Facts

Suppose the application team states "all resources are private," but the resource inventory reveals public network access enabled on a storage account. Instead of marking it compliant, you must:

- Record the exact configuration, scope, and access paths that can actually be used.
- Assess whether network policies, firewalls, identities, and data create unintended access risk.
- Check the owner and why the public configuration was chosen.
- Create an **evidence-based** finding without assuming a data leak unless verified.

A public endpoint configuration might be protected by other controls, but it must be an **informed decision** compliant with policy.

## 7. Using Azure Tools as Supporting Evidence

The Review questionnaire is only one part; Azure provides telemetry and data to verify how a workload operates.

### 7.1. Azure Advisor and Azure Policy

**Azure Advisor** can suggest improvements across categories applicable to supported resources, such as reliability, security, operational excellence, performance, and cost. Use recommendations as signals for investigation and backlog creation, rather than applying all of them blindly.

**Azure Policy** is useful for detecting resources that drift from organizational configuration standards (for example, a resource group missing tags or a non-compliant configuration). However:

- Policy compliance evaluates only defined rules and resources within scope.
- Policy does not prove that a backup can be restored or that business transactions succeed.
- Exemptions require justification, an owner, and a review date.

### 7.2. Azure Monitor, Application Insights, and Cost Management

- **Azure Monitor**: verifies availability, saturation, latency, CPU/IOPS, alerts, and trends.
- **Application Insights**: request/dependency traces, exceptions, transaction latency, and synthetic availability.
- **Log Analytics**: KQL analysis across time and resources to produce log evidence.
- **Cost Management**: spend by subscription, resource group, tag, or workload when mapped; inspect actual/amortized cost and budgets.
- **Resource Health / Service Health**: signals on the status of supported Azure resources/services; does not replace end-to-end monitoring.
- **Defender for Cloud and appropriate security tools**: additional posture/recommendation signals; verify permissions and feature scope.

Do not treat "no alerts" as evidence of system reliability if alerts were never configured or tested.

### 7.3. Read-Only Inventory with Azure CLI

The commands below are **read-only**; confirm the subscription, permissions, and resource group in your actual environment:

~~~bash
# Confirm the right tenant/subscription.
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# Inventory workload resources in a known resource group.
az resource list \
  --resource-group rg-orders-prod \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# View Advisor recommendations for the selected subscription, if permitted.
az advisor recommendation list -o json
~~~

An empty Advisor result does not prove a workload has no risk. The tool only surfaces recommendations from its supported checks based on current scope and data.

### 7.4. KQL: Measuring API Availability and Performance

When the application sends telemetry to **workspace-based Application Insights** and has the `AppRequests` table, for example:

~~~kusto
AppRequests
| where TimeGenerated > ago(7d)
| summarize
    TotalRequests = sum(ItemCount),
    FailedRequests = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
  by AppRoleName, bin(TimeGenerated, 1h)
| extend SuccessRatePercent =
    iff(TotalRequests == 0, real(null),
        100.0 * (TotalRequests - FailedRequests) / TotalRequests)
| order by TimeGenerated asc
~~~

Verify the actual schema because tables/columns and sampling may vary depending on integration. If log sampling makes p95 or error rate unrepresentative, note this limitation in the review. Hourly aggregation helps spot trends, but critical requests should be analyzed by endpoint and traffic profile rather than just overall API averages.

### 7.5. Cross-Checking with Real Tests

Any finding on Reliability/Performance needs appropriate testing:

- Load testing at normal, peak, and burst traffic levels.
- Checking n−1 capacity when an Availability Zone is isolated in a controlled environment.
- Restoring backups into a test environment and comparing checksums/transaction state.
- Testing rollback when a release misses SLOs.
- Testing sign-in, authorization, tokens, and secret access after IAM changes.
- Measuring SLIs from the **user's perspective** rather than only VM/Pod health.

Reports must record **date, environment, version, test data, and test limitations**. Low-load staging tests do not prove production has enough capacity.

## 8. Capstone Example: Surveying an Ordering Application Architecture

Suppose a company runs `orders-prod` on Azure, handling 60,000 successful orders/month and prioritizing continuous availability during peak hours.

**Initial architecture (assumed):**

- Azure Front Door routes requests to an Azure App Service plan.
- App Service runs a single always-on instance; zone redundancy configuration is unverified.
- Azure SQL Database uses a tier suitable for current load, but lacks failover documentation.
- Blob Storage stores order confirmation files; redundancy is not recorded in the architecture record.
- Key Vault stores secrets; the app uses a connection string with credentials in app settings.
- CI/CD deploys automatically, but rollback is manual and untested.
- Application Insights is integrated; only CPU and HTTP 5xx alerts exist.
- Cost Management has a subscription budget; cost per successful order is unknown.

**Do not assume** these components have or lack HA/security features without checking SKU, region, and configuration. The assessment below illustrates assumptions that need verification.

### 8.1. Mapping Risks by Pillar

| Pillar | Assumed finding | Impact | Needed evidence/test |
| --- | --- | --- | --- |
| Reliability | Single-instance API and missing DB failover test | Single instance/zone fault can cause outage | Placement, health probe, DR test |
| Security | DB credentials stored in app settings; permissions unreviewed | Risk of secret exposure and excessive privileges | RBAC, config audit, threat model |
| Cost Optimization | No cost per order or shared cost tracking | Hard to gauge efficiency as load grows | Amortized cost, owner mapping, valid order count |
| Operational Excellence | Unrehearsed rollback; alerts not tied to SLO | Slow detection/recovery | CI/CD run logs, game day, on-call runbook |
| Performance Efficiency | No peak load test or quota review | Throttling risk during campaigns | Benchmark, p95, connection/DB metrics |

### 8.2. Adjusting the Architecture Based on Findings

A feasible improvement plan could include:

1. Add replicas/zone-aware architecture **if supported by the service, SKU, and region**, measure capacity after losing one zone; verify corresponding database and storage availability tiers.
2. Review RBAC permissions, migrate Azure PaaS access to Managed Identity where supported, move applicable secrets to Key Vault, and apply network restrictions/Private Endpoints according to the threat model.
3. Adopt reviewed IaC, staged rollouts, and a rollback plan; run a game day to prove the process.
4. Add synthetic transactions for the order-creation flow and alert on error rate/latency rather than CPU alone.
5. Enable direct + shared cost reporting, define unit cost; evaluate Reservations/Savings Plans once baseline load is steady.
6. Benchmark from normal to peak load to tune autoscale, database SKU, and quotas without compromising SLOs.

Do not apply these changes directly to production straight from an assessment. Every change requires **design review, approval, a rollback plan, and testing**.

## 9. Assessing and Prioritizing Risks Transparently

Azure Well-Architected Review provides recommendations based on Microsoft's design guidance/questionnaires. To convert them into a backlog, the team can build an **internal prioritization matrix**. This matrix is **not an official Microsoft score**.

### 9.1. Risk Register

| ID | Pillar | Risk | Impact 1–5 | Likelihood 1–5 | Score I×L | Owner |
| --- | --- | --- | ---: | ---: | ---: | --- |
| R-01 | Reliability | Database failover unverified | 5 | 3 | 15 | Data/SRE |
| S-01 | Security | Application credentials overly privileged | 5 | 3 | 15 | Security/App |
| O-01 | Operational Excellence | No rehearsed rollback | 4 | 3 | 12 | Engineering |
| P-01 | Performance Efficiency | Peak throughput untested | 4 | 3 | 12 | SRE |
| C-01 | Cost Optimization | Missing workload cost allocation | 3 | 4 | 12 | FinOps |

**The 1–5 scale is only a governance example:** 1 = low, 5 = high. Equal scores do not mean equal risk; the severity of data loss, regulatory impact, or security exposure may require immediate action regardless of the product. Scores do not replace security/business owner judgment or risk acceptance policies.

For each finding, include:

- **Evidence:** source, timestamp, version, and confidence level.
- **Impact:** affected journeys and data, relevant RTO/RPO/SLO.
- **Mitigation:** approach, effort, cost, and impact on other pillars.
- **Owner/approver:** who implements, and who accepts residual risk.
- **Due date:** based on urgency and change schedule.
- **Acceptance criteria:** objective test confirming the finding is resolved.

### 9.2. Prioritizing by Value and Feasibility

A high-risk item that is difficult to implement still needs interim controls. For example:

- **Short-term:** verify backup restore, add database alerts, and document a manual runbook.
- **Medium-term:** deploy HA/zone redundancy and conduct controlled failover drills.
- **Long-term:** decouple dependencies, design multi-region, or change the data model if RTO/RPO requires it.

Do not mask risk by marking "will fix" and treating it as resolved. Statuses must be **open, mitigated, accepted, or closed-with-evidence**, with a clear owner.

## 10. Trade-Offs: There Is No "Absolutely Optimal" Architecture

One objective can affect multiple pillars. For instance, adding replicas to reduce outage risk raises cost and may require tuning DB connections. A decision table should capture both benefits and costs.

| Decision | Expected benefit | Side effects | How to verify |
| --- | --- | --- | --- |
| Distribute compute across multiple AZs | Higher Reliability during single-zone failure | Headroom cost; data/ingress dependencies | n−1 drill at peak load |
| Enable private endpoints / restrict public access | Reduced attack surface | More complex DNS, networking, and operations | DNS/TLS/auth synthetic tests |
| Add replicas + autoscale | Higher throughput and redundancy | Higher cost; backend DB may bottleneck | Load test and DB metrics |
| Use caching | Lower latency and DB read pressure | Cache invalidation, stale data, cost | Correctness test + p95 + hit ratio |
| Reduce log ingestion | Lower monitoring cost | Potential loss of observability/security data | Define required logs, measure alert coverage |
| Purchase suitable compute commitments | Discount on steady baseline usage | Underutilization if workload changes | Hourly eligible usage and full-term ROI |
| Multi-region active/passive | Resilience to regional outage | Complex replication, routing, failover, and cost | DR drill, RTO/RPO, data integrity |

An **Architecture Decision Record (ADR)** should capture the decision, context, options considered, trade-offs, approver, and evidence to be used for validation. A good review produces clear decisions, not just a list of flaws.

### 10.1. Short ADR Example

~~~markdown
# ADR-007: Increase fault tolerance for orders API

**Status:** Proposed
**Context:** Currently single instance; target RTO 30 minutes, SLO 99.9%.
**Options:**
- A: Keep a single instance with backup/restore.
- B: Multiple replicas distributed across zones where the service config supports it.
- C: Design multi-region immediately at this stage.

**Proposed decision:** B for the near term; evaluate C against DR goals.
**Rationale:** Mitigates instance/zone failures with a scope of change fitting the schedule.
**Impact:** Increases compute cost; requires backend and health probe testing.
**Acceptance criteria:** N-1 load test, SLO, database failover, and runbook.
**Owner/approver:** SRE lead / Product owner / Security review.
~~~

The ADR content is an **example**, not a guarantee that Option B will always meet targets if the tier/database is not suitable.

## 11. Turning Recommendations into an Improvement Roadmap

### 11.1. Creating an Action Backlog Table

| Priority | Finding | Specific action | Owner | Acceptance criteria |
| --- | --- | --- | --- | --- |
| P0 | R-01: Unverified DR | Restore database from backup into isolated environment, reconcile transactions | DBA/SRE | Measured RTO/RPO, valid data |
| P0 | S-01: Overly broad secrets | Audit permissions, migrate to appropriate identity, and rotate secrets | Security/App | Least-privilege test, audit log, no exposed secrets |
| P1 | O-01: Manual rollback | Add staged rollout and rollback runbook; rehearse | DevOps | Rollback tested within approved window |
| P1 | P-01: No peak test | Run load test at peak + single-zone failure | SRE | Throughput, p95, saturation within targets |
| P2 | C-01: Unclear unit cost | Allocate direct/shared costs and compute cost/order | FinOps | Totals reconciled, confirmed by owner |

Priority levels are **illustrative assumptions**; not every organization must assign these exact priorities to those findings. If an active security incident is occurring, incident response may dictate different priorities.

### 11.2. How Do You Define "Done"?

Define **Definition of Done** by outcome:

- IaC is updated, reviewed, and deployed to the proper environment.
- New controls are active; logs/configs/permissions are checked and business journeys tested.
- Metrics or measurements prove the target improved.
- Impact on other pillars is evaluated, such as redundancy changes increasing cost.
- Runbooks, architecture diagrams, and owners are updated.
- Finding has linked evidence and sign-off to close.

A merged PR alone is **not sufficient** to close a Reliability or Security finding without verifying operational impact.

### 11.3. Three-Phase Roadmap

~~~mermaid
flowchart LR
    B["Baseline<br/>Review + evidence"] --> Q["Quick wins<br/>Alerts, permissions, backup test"]
    Q --> M["Structural fixes<br/>HA, IaC, scaling, data design"]
    M --> V["Validation<br/>Load test, DR drill, security test"]
    V --> R["Re-review<br/>Update risk register + roadmap"]
~~~

You can split into 0–30 days, 30–90 days, and long-term **if** aligned with capacity. Do not assign rigid deadlines before understanding severity, technical dependencies, and the production change calendar.

## 12. Validating After Changes and Keeping the Review Current

A Review is a snapshot of architectural quality at **one point in time**. It becomes outdated when:

- The application changes region/SKU, adds a database, or swaps ingress.
- Major changes occur in Identity/RBAC, Key Vault, or networking.
- Traffic grows, peak patterns shift, or new dependencies are added.
- Backup/redundancy/DR or deployment architecture changes.
- SLOs, budgets, or business ownership change.

Set a review cadence based on workload criticality, and re-review after major architectural changes or severe incidents. Avoid "annual check-the-box reviews" where no action items are ever implemented or tested.

### 12.1. Acceptance Verification Suite

| Pillar | Before/after measurements |
| --- | --- |
| Reliability | SLI availability, n−1 capacity, restore/failover RTO/RPO |
| Security | Least privilege, secret exposure, policy findings, identity tests |
| Cost Optimization | Cost per successful order, budget variance, unused capacity |
| Operational Excellence | Change failure rate, recovery time, rollback drill, alert coverage |
| Performance Efficiency | Peak throughput, p95/p99 latency, CPU/IOPS/quota utilization |

Metrics must share the same **definition and data source** before and after. Comparing p95 under low load before a change with high load after a change is insufficient to conclude whether performance improved or degraded.

### 12.2. Accepted Risk Is Not Eliminated Risk

A business may lack the budget to deploy multi-region today. If current RTO/RPO is still accepted by the business owner, document:

- The existing risk and scope of impact if it materializes.
- Why it is deferred and interim workarounds.
- Who holds authority to accept the risk.
- Review milestones or triggers if demand increases.
- Interim monitoring and mitigation measures.

Do not change status to **Closed** simply because "doing nothing" was approved. Track it as **Accepted risk** with specific monitoring conditions.

## 13. Well-Architected Review Report Template

Use the following template to store workshop results and align with owners. This is an **internal report template**, not an assumed export format from an Azure tool.

~~~markdown
# Well-Architected Review — <workload> — <date>

## 1. Information and scope
- Workload, business owner, technical owner:
- Subscription(s), resource group(s), region(s):
- System diagram / data flow:
- Critical business journeys:
- SLO, RTO, RPO, data requirements:
- Items in scope and out of scope:

## 2. Methodology
- Participants and assessment date:
- Azure Well-Architected Review version/question set used:
- Supporting tools and tests:
- Evidence limitations, assumptions, and confidence levels:

## 3. Five-pillar summary
| Pillar | Strengths | Risks | Evidence | Owner |
| --- | --- | --- | --- | --- |
| Reliability | ... | ... | ... | ... |
| Security | ... | ... | ... | ... |
| Cost Optimization | ... | ... | ... | ... |
| Operational Excellence | ... | ... | ... | ... |
| Performance Efficiency | ... | ... | ... | ... |

## 4. Risk register
| ID | Risk/Impact | Likelihood | Priority | Evidence | Owner |
| --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... |

## 5. Decisions and trade-offs
- Options:
- Chosen option and rationale:
- Impact on other pillars:
- Approver/exceptions:

## 6. Remediation plan
| Action | Owner | Deadline | Dependency | Acceptance test |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

## 7. Verification and re-review
- Before/after metrics:
- Remaining tests to execute:
- Residual risk and acceptor:
- Trigger/date for next review:
~~~

Do not attach secrets, connection strings, tokens, or records containing personal data to the report. If using screenshots/diagnostic logs, sanitize unnecessary fields and control document access.

## 14. Capstone Lab: Conducting an Evidence-Backed Review

**Assumed scenario:** A company operates `orders-prod` in Azure, responsible for taking orders and processing payments. The workload uses an application Azure subscription, a data resource group, and shared platform components. The product owner plans a major campaign next month with a forecasted peak load of **900 requests/second**; target RTO is **30 minutes**, availability SLO is **99.9%**, and API p95 latency is under **500 ms** at the defined load. These values are exercise targets, not Azure SLAs.

### 14.1. Assumed Input Documentation

| Item | Initial state |
| --- | --- |
| Ingress | Azure Front Door with health probes, but failover has not been rehearsed |
| Compute | API runs on one primary instance; autoscale has no evidence |
| Data | Azure SQL with backups reported as Success; restore never tested |
| Security | Key Vault exists; API still holds DB credentials in config |
| Operations | CI/CD deploys automatically; rollback depends on a single engineer |
| Monitoring | HTTP 5xx alert; missing end-to-end synthetic create-order check |
| Cost | Compute/database costs are stable; subscription budget exists, but no cost/order |
| Load testing | Last test ran at 350 RPS; no 900 RPS peak test exists |

**Requirement:** Do not automatically infer from "Backup Success" that restore works, or from "Front Door has health probes" that the entire region can fail over. Clearly distinguish what is **known**, **unverified**, and **not implemented**.

### Task A — Define Scope and Objectives

Complete the workload profile, draw the app/data/identity/network diagram, and identify the **create-order** journey. Mark the payment system outside Azure as an external dependency. Set verification criteria for SLO, RTO/RPO, and capacity after losing an instance or a zone.

### Task B — Conduct the Well-Architected Review

For each pillar, complete at least **three review questions** backed by evidence. If data is missing, mark "Unknown/Needs verification" and design a test rather than answering "in place" based on expectations.

Examples:

- Reliability: does backup restore complete within RTO?
- Security: does the API have least privilege to fetch secrets and access data?
- Cost: what is the cost per successful order including shared costs?
- Operational Excellence: can you roll back using a tested procedure?
- Performance Efficiency: does the environment keep p95 under 500 ms at 900 RPS?

### Task C — Attach Tools and Evidence

Use simulated or read-only data in a learning environment to:

1. Inventory resources and configurations within scope.
2. Find relevant Azure Advisor recommendations, if available.
3. Read Azure Monitor/App Insights metrics or build a sample SLI table.
4. Compare budget/cost per successful order using figures provided by the exercise.
5. Confirm every finding has an **owner, timestamp, and verification method**.

**Do not** modify production or purchase resources to complete the lab; if you lack Azure permissions, specify what data must be requested from the owner.

### Task D — Create Risk Register and Roadmap

Select at least **five findings**, with at least one per pillar. For each finding, record impact, likelihood, evidence, owner, priority, and acceptance test. Identify at least **two trade-offs** across pillars.

For example, "add API replicas and increase HA" must include checking cost, DB throughput, and zone distribution; "reduce log ingestion" must include a security/observability assessment.

### Task E — Present Decisions

Write a 1–3 page report using the Section 13 template, along with an evidence appendix table. Present assuming an audience of business owner, SRE, security, and FinOps. Conclude with three decisions:

1. What must be done **before the campaign**?
2. What can be deferred with a workaround/accepted risk?
3. Which tests will confirm the architecture has improved?

### 14.2. Self-Assessment Rubric

| Criterion | Meets bar when |
| --- | --- |
| **Scope** | Real workload and dependencies, not just one resource group |
| **Five pillars** | Answers and findings cover Reliability, Security, Cost, Operations, Performance |
| **Evidence** | Every key claim links to telemetry, configuration, tests, or "unknown" status |
| **Trade-offs** | States cost/performance/security/reliability impacts of each decision |
| **Prioritization** | Risk register has a clear prioritization method and explained exceptions |
| **Action plan** | Includes owner, approach, deadline, and acceptance test |
| **Verification** | Specifies before/after metrics and tests, not stopping at "configured" |
| **Communication** | Report is clear for technical, finance, and business stakeholders |

## 15. Common Mistakes

| Mistake | Why it is insufficient | How to fix |
| --- | --- | --- |
| Just opening Azure Advisor and calling it a Well-Architected Review | Advisor does not know all business needs and dependencies | Run a workload assessment across all five pillars |
| Answering based on future target architecture | Masks current production risks | Assess the as-is state; keep roadmap separate |
| Assuming Review automatically audits the entire subscription | The questionnaire is a self-assessment | Cross-check with monitoring, configs, tests, and SMEs |
| Treating policy compliance as total security | Policy covers only defined rules/scopes | Threat model, IAM review, application security testing |
| Having backups and concluding Reliability is met | Backups may fail to restore properly or in time | Run restore drills, measure RTO/RPO and data integrity |
| Scaling compute for every bottleneck | DB/network/queue may be the true bottleneck | Load test and dependency tracing |
| Nice risk scores without owners | Nobody fixes or verifies them | Risk register with assigned accountability and deadlines |
| Omitting residual risk when accepting exceptions | Risks are forgotten after a meeting | Risk acceptance with approver and re-review trigger |
| Cutting logs/backups to optimize cost | Can destroy investigation/recovery capability | Maintain security, retention, and RTO/RPO guardrails |
| Closing a finding when a PR merges | Does not prove the change improved behavior | Acceptance testing and real evidence |
| Reviewing once and never updating | Workloads evolve, assessments go stale | Periodic reviews and change/incident-driven reviews |

## 16. Summary and Principles of Application

**Azure Well-Architected Review** is a structured way to examine an Azure workload across **five pillars**: Reliability, Security, Cost Optimization, Operational Excellence, and Performance Efficiency. Assessment quality depends on workload scope, business goals, honest answers, and objective evidence.

The process should form a continuous loop:

~~~text
Define workload + SLO/RTO/RPO
  -> Gather architecture, telemetry, and cost data
  -> Conduct Well-Architected Review
  -> Verify findings with tools and tests
  -> Build risk register and evaluate trade-offs
  -> Prioritize actions with owner + acceptance criteria
  -> Execute controlled changes
  -> Measure before/after, update docs, and re-review
~~~

The most important outcome is not "what score the workload got," but **how well critical risks are understood and addressed**, and whether changes actually improve user experience, resilience, security, performance, and cost. This is how technical Azure knowledge connects to long-term architectural and operational accountability.
