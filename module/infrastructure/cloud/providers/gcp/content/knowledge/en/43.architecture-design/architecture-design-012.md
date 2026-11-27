# Evaluating Trade-Offs in Security, Reliability, and Cost

A good Google Cloud architecture is not simply the one that is **most locked down**, **never goes down**, or **has the lowest bill**. Every objective carries limits, costs, and risks. Adding replicas can improve fault tolerance yet also raises cost and complexity. Tightening access and blocking all egress shrinks the attack surface yet makes deployment, integration, and incident troubleshooting harder. Over-optimizing cost can cut standby instances until the system fails to absorb traffic spikes.

The architect's job is to **identify non-negotiable constraints**, compare options with evidence, and select the combination of security controls, resilience, and cost that best fits business goals. The evaluation should be transparent about assumptions, unknowns, and triggers that require revisiting the decision.

This lesson belongs to the **GCP Architecture Design** chapter of the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, monitor reliability, and manage costs. In this lesson, we bring those three lenses together to evaluate architectural decisions for Java/Spring applications on Google Cloud.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish mandatory constraints from criteria open to optimization or trade-offs.
- Describe two-way interactions among security, reliability, performance, delivery speed, and cost.
- Apply shared responsibility, threat modeling, and defense in depth to GCP designs.
- Use SLIs, SLOs, error budgets, RTO, RPO, and failure-mode analysis to drive decisions.
- Estimate Total Cost of Ownership (TCO), including resources, networking, observability, and operational labor.
- Compare options via weighted matrices, run sensitivity analysis, and avoid substituting scores for hard constraints.
- Analyze examples across Cloud Run, GKE, Compute Engine, Cloud SQL, storage, and private networking.
- Author an Architecture Decision Record (ADR) backed by evidence, mitigations, and revisit triggers.

## 1. What Is an Architectural Trade-Off?

A trade-off is a choice where improving one property typically comes at the expense of another. For example:

- Adding replicas and expanding multi-region can raise availability yet adds compute, network, and operational costs.
- Enabling private networking and restricting egress reduces some unauthorized-access risk yet adds DNS, routing, and monitoring requirements.
- Lowering Cloud Run minimum instances cuts idle costs yet increases cold-start probability.
- Splitting into microservices supports independent development yet multiplies network hops, service identities, dependencies, and failure modes.
- Extending log retention aids incident investigation and compliance yet raises storage costs and exposure risk for sensitive data.

Not everything is negotiable. Mandatory encryption, keeping data within a specific legal jurisdiction, auditing mandates, or policy-mandated least privilege may be **hard constraints**. Any option violating a hard constraint must be eliminated, even if its overall score or monthly bill is lower.

### Three Tiers of Decisions

| Tier | Question | Example |
|---|---|---|
| Mandatory constraints | What must never be violated? | Data residency, regulatory controls, secret access boundaries |
| Quantitative targets | How good must the system be? | 99.95% availability SLO; 300 ms P95 latency; monthly budget |
| Priorities & trade-offs | Among compliant options, what matters more? | Release velocity, operational simplicity, variable cost |

For example, if data must stay inside one specific region, an option replicating to another region may be invalid. You cannot simply give it a low security score and compensate with a high availability score.

## 2. Evaluation Framework: Requirements → Options → Evidence → Decision

Follow a six-step process:

1. **Understand business impact:** who uses the system, when, and what does one hour of downtime cost?
2. **Define guardrails:** sensitive data, IAM, residency, auditing, quotas, budget ceilings, and recovery deadlines.
3. **Design at least two viable options:** e.g., single-region Cloud Run + Cloud SQL HA versus multi-region Cloud Run + properly replicated database.
4. **Assess risks and failure modes:** what can fail, with what likelihood/impact, and how is it detected and mitigated?
5. **Estimate, test, and compare:** measure latency, throughput, failover, data volume, and cost under representative load.
6. **Record an ADR and monitor:** document the decision, rationale, residual risks, owners, verification metrics, and review triggers.

~~~mermaid
flowchart TD
    A["Business requirements and SLOs"] --> B["Guardrails: security, compliance, budget"]
    B --> C["Design compliant options"]
    C --> D["Threat model + failure modes"]
    D --> E["Load test + recovery drill + cost estimate"]
    E --> F{"Meets mandatory thresholds?"}
    F -->|"No"| C
    F -->|"Yes"| G["Compare trade-offs, record ADR"]
    G --> H["Controlled rollout, measure real metrics"]
    H --> I["Re-evaluate periodically or when conditions change"]
~~~

This framework avoids two pitfalls: picking services on gut feel, and building a seemingly precise scorecard founded on unverified assumptions.

## 3. Security: Identifying Assets, Actors, and Attack Paths

Security is not merely turning on a couple of products. An architecture must know **what it is protecting**, **who can access it**, **where data flows**, and **what happens if a component is compromised**.

### Assets to Protect

- Customer data, transactions, and personal information.
- Credentials: database passwords, API tokens, OAuth secrets, cryptographic keys.
- Software artifacts and build/release pipelines.
- Privileges to alter infrastructure and production configurations.
- Integrity of data, messages, and audit records.
- Availability of endpoints, queues, and databases.

### Concise Threat Modeling

For an Orders API application:

1. Map components and data flows: Internet or internal clients → load balancer/Cloud Run → Cloud SQL → Pub/Sub → workers.
2. Mark trust boundaries: public Internet, VPC, service identities, projects, staging vs. production environments.
3. Enumerate actors and threats: unauthenticated users, hijacked accounts, compromised dependencies, malicious images, leaked secrets.
4. Define preventive, detective, and corrective controls for each threat.
5. Document residual risk, prioritizing by impact and likelihood.

| Threat | Impact Path | Suggested Controls | Cost / Complexity |
|---|---|---|---|
| Token leaked in Git | Unauthorized API or DB access | Secret Manager, rotation, code scanning | Requires IAM and secret lifecycle management |
| Over-privileged runtime identity | One compromised service affects many resources | Least privilege, separate service accounts | More IAM bindings and review overhead |
| API abuse | Anomalous traffic inflates load/bills | Authentication, rate limiting, appropriate Cloud Armor | Extra policy tuning and false-positive tracking |
| Tampered build pipeline | Production artifact runs malicious code | Protected branches, trusted builders, attestations | Added supply-chain engineering effort |
| Data accessed in wrong region | Residency violation | Resource location policies, replication design | Narrows DR / cross-region choices |
| Logs containing PII | Data exposure via observability systems | Redaction, access controls, retention limits | Instrumentation and audit complexity |

Never judge security posture solely by tool count. A system with many security products whose runtime service account still holds project-wide Editor can be riskier than a simpler system with crisp permission boundaries.

## 4. Shared Responsibility and Layered Security

Google manages underlying infrastructure security, yet customers remain responsible for configuration, data, application code, identities, and many additional controls. Responsibility boundaries vary by service.

| Layer | Compute Engine | GKE | Cloud Run / App Engine |
|---|---|---|---|
| Host / guest OS | Self-managed guest OS and patching | GKE manages many node layers; self-management varies by mode | Google manages the runtime environment |
| Container / app dependencies | Team-managed if using containers | Team-managed | Team manages image/runtime code |
| IAM & runtime identity | Team configures | Team configures IAM/RBAC/Workload Identity | Team configures service accounts, invokers, and policies |
| Network exposure | Firewalls, LB, routes | VPC, Service/Gateway, NetworkPolicy | Ingress/egress, VPC connectivity |
| Secrets & data | Team manages access, rotation, and protection | Team manages access, rotation, and protection | Team manages access, rotation, and protection |
| Logs / audit / IR | Team designs and operates | Team designs and operates | Team designs and operates |

### Defense in Depth

A payment API should never rely on a single authentication gate:

- IAM and application authentication at entry points.
- Action- and object-level authorization inside the application.
- Dedicated least-privilege runtime service accounts.
- Secret Manager without embedding credentials in images.
- Private connectivity and fitting network policies.
- Restricted database users scoped to required schemas/tables.
- Input validation, rate limiting, and anti-abuse protections.
- Audit logs, alerts, and incident response procedures.

These layers do not replace each other. Putting Cloud SQL on a private IP does not stop an over-privileged API from accidentally deleting data; tight IAM does not replace application-layer authorization checks.

### Least Privilege and Availability

Overly broad permissions widen the blast radius, yet IAM must also be operated safely: a botched policy edit can strip service access and cause an outage. Balanced safeguards include:

1. Separating build, deploy, and runtime identities.
2. Using narrow roles at the lowest applicable resource level.
3. Testing IAM/configs in staging or policy-as-code checks prior to rollout.
4. Keeping controlled, time-bound, audited break-glass procedures for emergencies.
5. Monitoring denied requests and actual permission usage to tighten gradually.

Never fix a `PERMISSION_DENIED` error in production by hastily granting Owner/Editor. Identify the exact denied operation and craft the minimal permission change.

## 5. Network Isolation: Is More Restrictive Always Better?

Private networks, tight egress policies, and avoiding public IPs shrink the attack surface. However, they also add operational components: VPCs, DNS, routing, NAT, firewalls, gateways, peering, or Private Service Connect depending on services.

### Example: Three Deployment Tiers for Orders API

| Option | Configuration | Benefits | Trade-Offs |
|---|---|---|---|
| A | Public Cloud Run endpoint with fitting app/IAM auth | Easy external client integration | Requires abuse monitoring, ingress controls, and WAF/rate-limiting as needed |
| B | Cloud Run behind Load Balancer / Cloud Armor with fitting ingress policy | Edge governance, rate limits, L7 protection | Higher cost and configuration effort |
| C | Internal-only ingress with fitting VPC/connectivity | Shrinks direct exposure | Requires a gateway or private path for external clients |

**Do not conclude A is insecure or C is automatically secure.** A public API with strong auth, authorization, rate limiting, and observability can meet requirements; an internal-only API lacking per-tenant authorization can still leak data. Choose based on client types, threat models, and trust boundaries.

### Network Cost and Reliability

- Private egress can introduce billable components like Cloud NAT, load balancers, or interconnectivity.
- Complex routing raises the chance of DNS/firewall misconfigurations breaking deployments or health checks.
- Splitting VPCs/projects shrinks blast radius but adds cross-project permissions and connectivity paths.
- Multi-region designs can make network egress and data replication a substantial cost driver.

Before production, test both the request path **and** the management path: image pulls, Secret Manager access, metrics/logging, DNS resolution, database reachability, and rollback execution.

## 6. Data Protection: Encryption, Keys, and Data Residency

Google Cloud services provide encryption at rest and in transit within defined scopes, yet the architecture must choose key management, replica placement, and data access rights aligned with requirements.

| Decision | Benefit | Operational Cost / Risk |
|---|---|---|
| Service-managed default encryption | Minimal key management effort | Less direct control over custom key lifecycles |
| CMEK via Cloud KMS on supported services | Greater key control and compliance alignment | Must manage key IAM, lifecycle, audits, key availability, and fees |
| Additional application-layer encryption | Protects data along custom business boundaries | Complex key management; impacts search/indexing and recovery |
| Multi-region replication | Broadens recovery options and durability | Expands storage footprint, network costs, and residency constraints |
| Long retention | Aids audits and investigations | Increases stored volume, privacy exposure, and cost |
| Minimal retention | Cuts unnecessary data storage | Risks lacking evidence for investigations/restores if misconfigured |

### CMEK Is Not Free for Reliability

When using customer-managed encryption keys, key availability becomes an operational dependency of the service. If a key is disabled, permissions are revoked, or key config breaks, data may become unreadable or unwritable depending on service behavior. Therefore:

- Verify the service and resource support CMEK in the target region.
- Scope key locations and permissions per requirements.
- Govern rotation, key versions, and key-usage rights under review.
- Monitor KMS access errors and audit logs.
- Drill recovery for unavailable keys, not solely data restores.

Never delete or disable a key protecting live data without an impact assessment. Separate key administration rights from data administration rights when organizational policy demands separation of duties.

## 7. Reliability: Measuring What Users Actually Care About

Reliability cannot be measured solely by CPU uptime or Running Pod counts. A system can return HTTP 200 while failing to save orders, or an API can look healthy while workers miss committed message-processing deadlines.

### SLIs, SLOs, and Error Budgets

- **SLI (Service Level Indicator):** a quantitative measure of service quality, such as successful request ratio or percentage of orders completed within 30 seconds.
- **SLO (Service Level Objective):** a target threshold for an SLI over a rolling or calendar window.
- **Error budget:** the maximum allowable unreliability under that SLO.

Example: an API targets **99.9% of valid requests succeeding over 30 days**. With 1,000,000 valid requests in the period, at most 1,000 failed requests fall within the mathematical error budget. Defining an SLI requires specifying exactly which requests count, which errors are client-caused versus server-caused, and how invalid traffic is excluded.

~~~text
Good request ratio = good_events / valid_events
Error budget (events) = valid_events * (1 - target_ratio)
~~~

Do not mechanically substitute uptime downtime formulas for a request-based SLO. If an SLO is time-based, unavailability converts to minutes; if request-based, count events strictly by definition.

### Latency SLOs

Do not rely solely on average latency. Example:

~~~text
99% of valid requests complete in < 400 ms
over a 28-day window
~~~

P95/P99 latency and histograms expose tail latency. Anchor SLOs in user experience and baselines rather than picking arbitrarily tight numbers just to sound impressive.

### RTO and RPO

- **RTO (Recovery Time Objective):** maximum acceptable time to restore service after an outage.
- **RPO (Recovery Point Objective):** maximum acceptable data loss, typically expressed as time back to the recovery point.

For example, a 30-minute RTO and a 5-minute RPO are two distinct constraints. Adding API replicas can speed up compute recovery without ensuring the database loses at most 5 minutes of data.

### Reliability Does Not Mean Multi-Region

Multi-region can improve regional fault tolerance yet introduces new failure modes: replication lag, split-brain, routing flaws, inconsistent writes, key availability, and failover coordination. If the business accepts a longer RTO, single-region multi-zone with rehearsed backups/restores may beat multi-region on both cost and complexity.

## 8. Analyzing Failure Modes Before Buying More Redundancy

Systems rarely fail solely because a server powers off. Trace the entire dependency chain:

~~~mermaid
flowchart LR
    A["Client"] --> B["Ingress / Load Balancer"]
    B --> C["Orders API"]
    C --> D["Cloud SQL"]
    C --> E["Payment API"]
    C --> F["Pub/Sub"]
    F --> G["Order Worker"]
    G --> H["Cloud Storage"]
    C --> S["Secret Manager / Identity"]
    G --> S
~~~

Deploying Orders API across two regions while keeping an unmitigated single-point-of-failure database may still miss the target RTO. Likewise, extra API replicas help little if every replica relies on one revoked credential or one failing external dependency.

### Sample Failure Mode Table

| Failure Mode | Impact | Detection Signal | Containment / Recovery | Residual Risk |
|---|---|---|---|---|
| Container/Pod crash | Partial request errors | Restarts, error rate, readiness | Multiple replicas, restarts, health checks | Higher load on remaining replicas |
| Zone unavailability | Partial capacity loss | Region/zone metrics, failed nodes | Multi-zone placement, regional resources | Shared regional dependencies |
| Database failover | Transactions may time out | Connection errors, DB metrics | HA, bounded retries, idempotency | Active open connections drop |
| Payment dependency timeout | Orders fail to complete | Dependency latency, business SLIs | Timeouts, circuit breakers, queues/fallbacks if allowed | Backlog or business impact |
| Misconfigured IAM or secret | App cannot access data/APIs | `PermissionDenied`, startup failures | Change reviews, canaries, rollbacks, audits | Recovery depends on admin access |
| Buggy logic release | Widespread errors | Error budget burn, traces, synthetic tests | Progressive rollouts, kill switches, rollbacks | Schema/data may not roll back |
| Region outage | Multiple components unreachable | External cross-region monitoring | Multi-region DR or standby region recovery | Replication lag and failover complexity |
| Compromised build artifact | Security/integrity breach | Provenance/scans/audits | Signed provenance, approvals, rollbacks, revocation | Detection may lag |

Do not score severity and probability purely by intuition. Cite evidence: observed frequency, prior incidents, dependency behavior, failover test results, and design assumptions.

### Single Points of Failure Take Many Forms

- **Compute:** a single VM/Pod/instance.
- **State:** a database or storage bucket with no recovery plan.
- **Control plane:** CI/CD pipelines, IAM permissions, or DNS.
- **People / process:** only one engineer knows how to roll back, with no runbooks.
- **Changes:** all replicas receive the exact same buggy release simultaneously.
- **Organization:** unclear ownership where alerts route to nobody on call.

HA design must address common-mode failures, not just count instances.

## 9. Reliability Mechanisms and Their Trade-Offs

### Redundancy and Multi-Zone Placement

Multiple replicas across zones dampen instance/zone failures, yet consume resources and complicate distributed state. Stateless tiers replicate easily; databases and write paths require understanding consistency, replication, and failover.

### Timeouts, Retries, Backoff, and Idempotency

Retries smooth over transient blips yet **can trigger retry storms** when a dependency is overloaded. For example, 100 initial requests each retrying three times can multiply load on a struggling backend. Apply:

- Bounded timeouts fitted to the request latency budget.
- Retries strictly for retryable errors; never blindly retry invalid data or authorization failures.
- Exponential backoff, jitter, and retry budgets/caps.
- Circuit breakers, bulkheads, or queues to isolate failures.
- Idempotency keys for writes, payments, and order creation to prevent duplicates.

Pseudocode example for calling a payment partner:

~~~text
idempotencyKey = orderId + ":payment"
attempt = 0

while attempt < maxAttempts:
    result = callPartner(
        idempotencyKey=idempotencyKey,
        timeout=perAttemptTimeout)

    if result.success:
        return result
    if result.permanentFailure:
        stopAndReport(result)

    sleep(backoffWithJitter(attempt))
    attempt += 1

return pendingForReconciliation
~~~

The pseudocode highlights idempotency and separating transient from permanent failures. Real payment integrations require partner idempotency contracts, tracking unknown outcomes, and reconciliation; never treat a timeout as proof that a transaction did not execute.

### Queue Buffering and Asynchronous Processing

Pub/Sub decouples APIs from workers, reduces temporal coupling, and enables independent scaling. Yet queues add cost, end-to-end latency, duplicate handling, retries, and dead-letter queues. If an operation must finish synchronously within a few hundred milliseconds, pushing everything into a queue violates user expectations.

### Backups and Restores

Backups recover data after logic bugs or accidental deletions; synchronous replicas **do not replace backups**, because an erroneous `DELETE` replicates right to the standby. Conversely, backups do not preserve real-time availability during a zone failure if restoring takes hours. Pair HA and DR per RTO/RPO.

### Progressive Delivery

A 5–10% canary shrinks the blast radius of bad releases, yet requires enough traffic to catch errors and shared-state compatibility across versions. Platforms like Cloud Run support revision traffic splitting, while GKE Deployments pair with progressive delivery tools for finer control. More release stages add pipeline and monitoring complexity.

### Resilience Trade-Offs Summary

| Mechanism | Benefit | Trade-Off |
|---|---|---|
| Minimum instances | Cuts cold starts, keeps capacity warm | Idle compute cost |
| Multi-zone | Survives zone failures better | Replicas, cross-zone networking, placement constraints |
| Multi-region | Adds recovery path for region outages | Replication, routing, cost, consistency |
| Retries / backoff | Recovers from transient errors | Adds latency and load if misconfigured |
| Circuit breaker | Shields downstream from cascading failure | Rejects requests while dependency heals |
| Queues | Decouples processing, absorbs spikes | Eventual consistency, duplicates, backlogs, DLQs |
| Backups / PITR | Recovers deleted or corrupted data | Storage/logging costs and restore time |
| Canary / rollback | Limits blast radius of bad releases | Requires metrics, automation, and schema compatibility |

## 10. Cloud Cost: Total Cost of Ownership Over VM Unit Prices

Evaluate architectural cost across the whole lifecycle: development, staging, production, backups, incidents, recovery, and upgrades. Line items absent from raw compute pricing can dominate the bill.

~~~text
Total Cost of Ownership (TCO)
  = runtime resources
  + data storage, backups, and replication
  + network egress, load balancing, NAT/connectivity
  + managed databases, caches, messaging
  + observability, logging, security, and key management
  + build/release and artifact storage
  + operational labor, incidents, and maintenance
~~~

### Commonly Overlooked Cost Drivers

| Category | Examples |
|---|---|
| Compute | CPU/memory, disks, GPUs, minimum instances, reservations |
| Network | Internet egress, billable cross-zone/region transfer, LBs, Cloud NAT |
| Data | Database instances, storage, read/write ops, backups, PITR, replicas |
| Telemetry | Log ingestion/storage, metrics, trace samples |
| Security | KMS operations, security tooling, secrets, supply-chain checks |
| Operations | On-call rotations, GKE upgrades, OS patching, failover drills, incident recovery |
| Non-production | Staging, CI test projects, ephemeral environments, and orphaned resources |

Never claim Cloud Run is always cheaper than GKE or VMs. Cloud Run fits bursty workloads and scale-to-zero; GKE shines with shared multi-service capacity; Compute Engine can optimize steady loads for skilled VM ops teams. Decide using measured resources and current pricing.

### Cost Allocation and Accountability

An architecture without a cost owner is hard to optimize. Best practices:

- Separate environments or teams by project/folder.
- Apply consistent labels/tags for cost allocation where services support them.
- Enable Cloud Billing export to BigQuery for periodic cost analysis.
- Set budget alerts; **budget alerts do not automatically cut off spending or enforce hard caps**.
- Track service owners, cost centers, and TTLs for experimental resources.
- Reconcile estimates against real bills after several weeks or a full load cycle.

## 11. Workload-Based Cost Modeling

Before opening the Pricing Calculator, measure or estimate your workload profile.

### Request-Driven Model

Suppose Orders API sees:

- Average 20 requests/second during business hours.
- Peak 300 requests/second for 15 minutes.
- Varying CPU time and memory per request.
- Very low traffic overnight.

Variables to measure:

- CPU time per request and request concurrency.
- Memory per instance, startup duration, and DB connection counts.
- Minimum/maximum instances required for latency SLOs.
- Request/response payload sizes and network egress.
- Call frequency to supporting services and log/trace volume.

Cloud Run saves idle time when properly configured, yet minimum instances or instance-based billing shifts the cost curve. For GKE, model Pod requests, system overhead, node capacity, autoscalers, cluster fees, and slack capacity. For VMs, include continuous VM uptime, disks, and LB/HA overhead.

### CPU Utilization Alone Is Insufficient

Seeing 30% CPU does not mean you can cut 70% of costs. A workload may be bounded by memory, I/O, connection pools, or tail latency. Conversely, high RPS might burn minimal CPU if requests only hit caches.

Run load tests capturing:

1. Throughput and error ratios.
2. P50/P95/P99 latency.
3. CPU and memory per replica/instance.
4. Connection pool saturation, queue depth, and dependency latency.
5. Test-environment spend during the test window.

For production forecasts, model full daily/weekly/monthly traffic curves rather than multiplying a 15-minute peak across the entire month.

### Persistent Data Model

Suppose a database starts at 100 GiB and grows by 10 GiB/month:

- Primary storage expands over time.
- HA or replicas multiply compute/storage usage.
- Backups, transaction logs, and PITR add storage charges.
- Cross-region replicas or exports incur network/data transfer fees.
- Queries and transactions consume CPU, IOPS, and latency headroom.

Never estimate total database cost from raw per-GiB storage pricing alone. For Cloud SQL, account for instance tiers, HA, backups, storage, networking, and applicable licensing/editions.

### Business-Unit Economics

A simple formula:

~~~text
Unit cost per successful order
  = attributable monthly service cost
    / successful orders completed in that month
~~~

This metric works well when measured consistently with a stable definition of “successful”. If higher reliability reduces failed orders, runtime spend might increase while **cost per successful order** drops. Hence, “the lowest monthly bill” is not always the business optimum.

## 12. Cost Optimizations and Their Security/Reliability Impacts

| Measure | Potential Savings | Risk if Overdone | Safeguard |
|---|---|---|---|
| Right-size CPU/memory | Eliminates overprovisioning | OOMs, throttling, latency spikes | Load test and monitor percentiles |
| Reduce min instances | Cuts idle compute | Cold starts, startup bottlenecks | Monitor user-facing latency SLOs |
| Use preemptible/Spot capacity where fitting | Lower unit compute rates | Preemption, interrupted jobs | Checkpointing, retries, non-critical workloads |
| Shorten log retention | Cuts log storage | Missing forensic/audit evidence | Tier retention by log classification |
| Sample traces | Lowers telemetry spend | Misses rare edge-case errors | Error-biased or targeted sampling |
| Cut standby replicas/regions | Saves compute/network | Lower availability / failover headroom | Verify RTO/SLOs and run fault tests |
| Batch requests/messages | Cuts per-call overhead | Higher latency and batch blast radius | Cap batch size and deadlines |
| Reserved/committed capacity where fitting | Discounts steady usage | Lock-in and loss of flexibility | Forecast and analyze long-term utilization |
| Schedule off-hours shutdown for test envs | Cuts non-prod waste | Breaks off-hours integrations/backups | Clear schedules, owners, and restart automation |

Never sacrifice foundational protections—encryption, required backups, auditability, or least privilege—merely to trim bills. If a cost-cutting proposal breaks a guardrail, reject it or seek an approved policy exception.

### FinOps Is a Continuous Loop

1. **Inform:** attribute costs by project, service, team, and business unit.
2. **Optimize:** right-size, clean up orphaned resources, align billing models.
3. **Operate:** assign owners, set alerts, and run periodic optimization reviews.

Measure every major cost optimization before and after against SLO guardrails. If bills drop 15% while error budgets burn dramatically faster, reconsider.

## 13. Comparing GCP Platforms Through the Three Lenses

Choosing Compute Engine, GKE, Cloud Run, or App Engine affects all three dimensions. The table below outlines design traits—**not an absolute safety ranking**.

| Platform | Security | Reliability | Cost / Operations |
|---|---|---|---|
| Compute Engine | Self-managed guest OS, firewalls, image patching; high OS control | MIGs, multi-zone, LBs; self-designed HA/DR | VM/disk/network charges; heavy OS/patching effort |
| GKE Standard | RBAC, NetworkPolicy, Workload Identity; higher node responsibility | Kubernetes orchestration, HPA/node autoscaling, rollouts | Cluster/node capacity, storage, networking, and platform team |
| GKE Autopilot | Managed node/security policies; still needs workload IAM/RBAC | GKE manages workload capacity; still design Pod topology/SLOs | Workload-mode pricing; reduced node administration |
| Cloud Run | Runtime service accounts, ingress/egress, container/image controls | Revisions, traffic splitting, autoscaling; dependencies still need HA | Resource/billing-mode charges, min instances, networking |
| App Engine | Managed runtime/service identity, environment-scoped limits | Versions/traffic splitting, autoscaling per Standard/Flexible | Instance pricing, legacy coupling, migration effort if moving |

### Example: Comparing Two Spring Boot API Designs

**Option A — Single-region Cloud Run + Cloud SQL**

- No cluster management or node patching.
- Uses Cloud Run IAM, Secret Manager, controlled ingress, and audits.
- Adds Cloud SQL HA if RTO/availability and budget justify it.
- May need min instances to bound cold starts.
- Requires a separate DR plan for full-region outages.

**Option B — Regional GKE + Cloud SQL HA in one region**

- Deeper control over Kubernetes networking, scheduling, and policies.
- Multi-zone Nodes/Pods with HPA and rolling updates.
- Requires mastering cluster admission, node pools, RBAC, probes, and resource requests.
- Cost-effective if leveraging an existing shared cluster; overkill for one small API.
- Still vulnerable to full-region outages if tied to one Cloud SQL region.

**Conclusion:** if API SLOs and compliance are met, lower operational overhead usually wins. Yet if Kubernetes policies/sidecars are mandatory or an existing shared cluster runs efficiently, GKE can make more sense.

## 14. Quantitative Comparison Methods and the Trap of Misleading Scores

A weighted scoring matrix brings structure to discussions, but only apply it after eliminating options that violate guardrails.

Suppose three options exist:

- A: Single-region Cloud Run + Cloud SQL HA.
- B: Multi-region Cloud Run + custom-designed data DR strategy.
- C: Regional GKE + Cloud SQL HA.

Score each criterion 1–5 (5 = best in this scenario). These are **illustrative scores assigned by an architecture team**, not official Google Cloud benchmarks or rankings.

| Criterion | Weight | A | B | C |
|---|---:|---:|---:|---:|
| Meets SLOs and resilience | 35% | 3 | 5 | 4 |
| Reduces security/compliance risk | 30% | 4 | 4 | 4 |
| Low Total Cost of Ownership | 25% | 5 | 2 | 3 |
| Operational & deployment simplicity | 10% | 5 | 2 | 2 |

Illustrative totals:

~~~text
Score(A) = 0.35*3 + 0.30*4 + 0.25*5 + 0.10*5 = 4.00
Score(B) = 0.35*5 + 0.30*4 + 0.25*2 + 0.10*2 = 3.65
Score(C) = 0.35*4 + 0.30*4 + 0.25*3 + 0.10*2 = 3.55
~~~

On these hypothetical scores, A leads. Yet if the organization mandates **10-minute recovery from a region outage** and A cannot meet it, A is eliminated before scoring begins. B wins despite a higher bill.

### Do Not Use Scores to Rubber-Stamp Assumptions

- “Security 4/5” means nothing without enumerating threats and controls.
- “Reliability 5/5” cannot be assumed just from two regions; test failover and data consistency.
- “Cost 2/5” must come from a cost model or real billing, not a hunch that “multi-region sounds expensive”.
- Every score needs an owner, evidence source, and confidence level. Use score ranges when uncertain.

### Sensitivity Analysis

Vary weights to see if the winner flips. Raising reliability's weight from 35% to 55% while cutting cost to 10% (keeping total 100%) may push B ahead of A depending on other scores. If tiny weight tweaks repeatedly flip the winner, the decision is **assumption-sensitive**—gather more data or clarify stakeholder priorities.

Ask:

1. Which option holds up best if traffic triples?
2. If the database is 70% of the bill, does runtime cost tuning still move the needle?
3. If RTO shrinks by half, what structural changes become unavoidable?
4. If on-call staffing shrinks, how does GKE/VM operational cost shift?
5. If data residency rules tighten, which options become invalid?

### Pareto Frontier

An option is **dominated** if another compliant option equals or beats it on every key criterion and strictly beats it on at least one. Drop dominated options from the shortlist.

In practice, no single option dominates everywhere: one is cheaper with slower RTO; another recovers faster at higher cost and complexity. These sit on the **Pareto frontier**, requiring a business-driven decision.

## 15. End-to-End Example: Orders API at Two Criticality Tiers

Suppose `orders-api` is built with Spring Boot, Cloud SQL PostgreSQL, Pub/Sub, and Cloud Storage. It handles payment records without storing raw card details directly. This is a **hypothetical scenario**, not any real organization's system or numbers.

### Context

- API serves customers in one market with daytime peak hours.
- Order data must be durable with an audit trail.
- Deployed multiple times per week.
- Small ops team favoring simplicity.
- Database handles critical transactions; duplicate payments are forbidden.

### Tier 1: Non-Mission-Critical Application

Suppose:

- Availability SLO: 99.9% of valid requests.
- Target RTO: 2 hours for a region outage.
- Target RPO: 15 minutes for data recoverable via verified procedures.
- Limited budget; partial downtime tolerable.

A candidate design:

~~~mermaid
flowchart TD
    U["Clients"] --> CR["Cloud Run Orders API<br/>single region"]
    CR --> DB["Cloud SQL<br/>HA where appropriate"]
    CR --> PS["Pub/Sub"]
    PS --> W["Cloud Run worker/Job"]
    CR --> SM["Secret Manager"]
    DB --> BK["Backups + PITR<br/>per configuration"]
    CR --> MON["Cloud Monitoring / Logging"]
    W --> MON
~~~

Design elements:

- Cloud Run service with load-tested min/max instances, concurrency, and timeouts.
- Intra-region Cloud SQL HA if zone fault tolerance is needed, plus matching backups/PITR.
- Externalized secrets; least-privilege runtime service account.
- Idempotency keys for orders and payments.
- Alerts on error-budget burn and business latency.
- Rehearsed DB restore and standby-region service bring-up to verify RTO/RPO.

**Trade-off:** lower platform ops cost than GKE, yet requires a region-outage recovery plan; a single-region deployment does not meet regional RTO merely because Cloud Run manages instances.

### Tier 2: Mission-Critical Transactional System

Suppose requirements tighten:

- 99.99% SLO for the order-creation flow.
- 10-minute RTO for primary region outages.
- Near-zero RPO for critical transactions with strict business criteria.
- Data may reside/replicate across approved regions.

A candidate design:

- Two regional API deployments with designed and tested routing/failover.
- Data architecture matching RPO: evaluate databases with true multi-region capabilities, replication modes, consistency, and failover behavior.
- Write-path idempotency, reconciliation, and conflict resolution.
- Independent monitoring and failover orchestration procedures.
- Security and key/secret availability in both regions.

Near-zero RPO cannot be reliably achieved merely by adding an asynchronous cross-region replica without accounting for replication lag. If the workload requires multi-region writes with strict consistency, evaluate databases and data models built for that requirement—such as Spanner where fitting—recognizing significant impacts on code, schema, and cost.

**Trade-off:** enables much faster recovery at higher cost, networking complexity, distributed state, testing effort, and operational load. Justified only when downtime and data-loss costs outweigh the investment.

### Comparing Both Tiers

| Criterion | Tier 1 | Tier 2 |
|---|---|---|
| Compute routing | Single region | Multi-region with verified failover |
| Database | HA/backups within RTO/RPO bounds | Multi-region design or fitting consistency strategy |
| Cost | Typically lower all else equal | Higher due to redundancy and replication |
| Operations | Fewer components | More complex runbooks/automation and drills |
| Security | Mandatory IAM, networking, secrets, audits | Same controls enforced across multiple regions |
| Residual vulnerabilities | Region outage and restore time | Data consistency/failover orchestration, common-mode failures |

Crucially, **never treat security, reliability, and cost as three independent sliders**. Switching databases to tighten RPO ripples across data access, schemas, network transfer, bills, and ops skills.

## 16. Risk, Likelihood, and Cost of Downtime

Not every choice needs complex scoring, yet many decisions become clearer to stakeholders through **expected loss**:

~~~text
Expected annual incident loss (illustrative)
  = probability of scenario per year
    * business impact if scenario occurs
~~~

Hypothetical example:

- A prolonged region outage has an estimated 2%/year probability.
- If it happens, total business impact is estimated at 500,000 currency units.
- Corresponding expected annual loss is 10,000 currency units/year.

This is purely a calculation method example—**not real probabilities or Google Cloud estimates**. Even if multi-region costs more than expected annual loss, it may still be warranted by compliance, reputational damage, tail risk, or mandatory RTOs. Conversely, low expected loss never justifies skipping foundational security controls.

### When Probabilities Are Unknown

Do not invent a number and treat it as exact. Use three scenarios:

- **Optimistic:** rare incidents, low resource prices, traffic on forecast.
- **Base case:** grounded in current metrics and median forecasts.
- **Stress case:** peak traffic, a failing dependency, and elevated failover costs.

Cite assumption sources and run sensitivity checks. For rare, catastrophic risks, evaluate business impact analysis rather than relying solely on averages.

### Risk Register

| ID | Risk | Likelihood | Impact | Current Controls | Action / Owner |
|---|---|---|---|---|---|
| R1 | Bad IAM config deployed | Unknown | API loses DB access | Peer review | Add policy validation, platform team |
| R2 | DB failover exceeds RTO | Unmeasured | Failed transactions | HA, monitoring | Run failover drill, SRE |
| R3 | Traffic spike blows budget | Campaign-driven | Budget overrun | Max instances | Cost forecasts + alerts, FinOps |
| R4 | Secret leaked in logs | Unmeasured | Security breach | Log redaction | Test zero-secret logging, security |
| R5 | Cross-region replica falls behind | Unmeasured | Missed RPO | Replication monitoring | Measure lag and test failover, DB owner |

Never mark a risk “Mitigated” just because a ticket was filed. Actions close only with evidence: tests, metrics, enforced policies, or recovery drills.

## 17. Verifying Trade-Offs with Experiments Rather Than Assumptions

Every major architectural decision needs a **test plan** tied to its goals.

### Security Testing

- Audit IAM and service accounts for least privilege.
- Attempt out-of-scope secret access and confirm denial.
- Verify unauthenticated endpoints cannot invoke internal APIs.
- Enforce image and dependency scans in CI.
- Test egress rules using non-sensitive synthetic workloads.
- Verify audit logs capture required events with policy-compliant retention.

### Reliability Testing

- Load-test base, peak, and burst traffic profiles.
- Practice restarts/rollouts to measure request impact.
- Simulate dependency timeouts and verify retries/circuit breakers.
- Drill database failover in an approved environment.
- Test restoring from backups and validate business data integrity.
- Verify retries never create duplicate orders or double payments.
- Confirm alerts page the right responders and runbooks suffice for recovery.

### Cost Testing

- Tag test infrastructure with owners and resource labels.
- Enable budget alerts and watch resource counts during load tests.
- Run time-bounded tests with strict deadlines and automated cleanup.
- Measure CPU/memory, egress, storage, logs, and DB requests.
- Reconcile cost dashboards against Billing exports and test duration.
- Extrapolate cautiously using realistic traffic curves and document assumptions.

**Safety rule:** never run destructive chaos experiments in production without scope, safeguards, and operational sign-off. In test environments, enforce quotas, max instances, deadlines, and teardown plans to prevent runaway bills.

### Before / After Proof Criteria

| Goal | Before Metric | Change | After Acceptance Criterion |
|---|---|---|---|
| Cut cold starts | P95 latency after idle gaps | Carefully raise min instances | P95 meets SLO within budget |
| Shrink runtime privileges | Broad project-wide SA | Scope IAM per secret/database | Functional tests pass; out-of-scope denied |
| Survive zone failure | Single-node/zone SPOF | Configure fitting replicas/HA | Zone-failure drill meets RTO |
| Trim log spend | High log ingestion | Sample/drop unneeded verbose logs | Mandatory audit/security logs intact |
| Reduce failed orders | Timeouts and duplicates | Idempotency + bounded retries | Duplicate rate drops; latency meets SLO |

## 18. Operating Decisions: Dashboards, Alerts, and Change Workflows

Once an architecture is chosen, maintain dashboards tracking **all three dimensions**:

| Lens | Metrics to Watch | How to Use |
|---|---|---|
| Security | Access denials, auth failures, anomalous secret reads, image scan findings | Spot privilege abuse or unauthorized changes |
| Reliability | Good request ratio, P95/P99 latency, error budget burn, queue age, DB failovers | Spot user impact and dependency degradation |
| Cost | Spend per project/service, runtime utilization, network egress, unit cost/order | Compare against budget and spot safe optimizations |
| Delivery | Deploy frequency, rollbacks, change failure rate, time to restore | Track release risk and recovery speed |

Do not alert on every metric. Alerts must indicate actionable conditions with defined severity and owners. Examples:

- Rapid continuous error-budget burn → throttle traffic or roll back.
- Anomalous Secret Manager permission change → investigate via security runbook.
- Spend exceeds forecast due to surging instances → inspect anomalous traffic, abuse, or retry storms.
- DB replication lag exceeds RPO → halt DR actions relying on unsynced replicas.

A cost alert should never blindly shut down production in a way that causes an outage costlier than the savings. Any automated spend caps must be scoped carefully with explicit exceptions and approvals, since billing budget alerts do not hard-cap usage by themselves.

## 19. Advanced Controls and Cross-Cutting Impacts

### VPC Service Controls Do Not Replace IAM

VPC Service Controls establish service perimeters to mitigate exfiltration risks across supported services. They complement IAM rather than replacing authentication, application-level authorization, or protection for unsupported services.

When proposing a service perimeter:

1. Identify protected data, APIs, and projects.
2. Verify whether target services and access paths are supported.
3. Inventory CI/CD runners, developers, service accounts, backup/export jobs, and monitoring needing access.
4. Run in dry-run mode and inspect audit/violation logs before enforcing.
5. Roll out in phases with a rollback plan.

**Trade-off:** well-scoped perimeters reduce exfiltration risk, yet a misconfigured policy can block pipelines, exports, or production apps. Monitor reliability and operational impact before enforcing blocks.

### Observability: Cutting Log Volume Without Losing Forensics

Trimming verbosity saves money, yet a security or production incident cannot be diagnosed without evidence. Best practices:

- Preserve mandatory audit logs and required security events.
- Never log secrets, tokens, raw credentials, or unnecessary personal data.
- Use structured logs with correlation IDs, service, version, severity, and error codes.
- Consider sampling high-volume request logs while preserving errors and key events for debugging.
- Set retention per data classification; identify sources needing long-term archival.
- Re-measure log ingestion after tuning and confirm investigation runbooks still work.

Never use “turn off all logs” as a cost optimization. The cost of being blind during an outage or breach dwarfs legitimate logging spend.

### Quotas and Spend Caps

Quotas and instance caps limit blast radius from retry storms or abuse and make spend predictable. Yet they can also reject legitimate traffic spikes. Balance via:

- Quotas preventing runaway resource creation.
- Max instances or concurrency protecting downstream DB connections.
- Responsive autoscaling with headroom for legitimate peaks.
- Cost forecasts, budget alerts, and anomaly response plans.
- Pre-agreed rules on when availability wins over throttling and vice versa.

A mission-critical payment API with tight SLOs will prioritize staying online over auto-halting on a budget alert. Conversely, a sandbox environment can enforce tight caps and strict TTLs. **Spend policies must match workload criticality.**

## 20. Recording Decisions in an Architecture Decision Record

An ADR documents why the team chose an option, who accepts residual risks, and when the decision must be revisited. It is more than meeting notes—it links directly to data and evidence.

### ADR Template

~~~markdown
# ADR-012: Choose Architecture for Orders API

## Context
- Business owner:
- Technical owner:
- Criticality tier:
- Workload and dependencies:
- Data classification:
- Base / peak traffic:
- SLOs and SLI definitions:
- RTO / RPO:
- Cost ceiling and review cadence:

## Mandatory Constraints
- Data residency:
- Authentication / authorization:
- Encryption / key ownership:
- Auditing, retention, backups:
- Recovery deadline:

## Options
- A: Single-region Cloud Run + Cloud SQL HA
- B: Multi-region Cloud Run + matching data DR
- C: Regional GKE + Cloud SQL HA

## Comparison Evidence
| Criterion | A | B | C | Data Source |
|---|---|---|---|---|
| Security guardrails | | | | |
| Load test / P95 | | | | |
| RTO drill | | | | |
| RPO observation | | | | |
| Monthly TCO range | | | | |
| Operational effort | | | | |

## Decision
- Chosen option:
- Rationale:
- Rejected options:
- Unverified assumptions:

## Risks and Mitigations
| Risk | Mitigation | Owner | Verification | Due Date |
|---|---|---|---|---|
| | | | | |

## Rollout and Rollback
- Staging tests:
- Canary:
- Smoke tests:
- Rollback triggers:
- Database migration compatibility:

## Re-Evaluation
- Scheduled date:
- Triggers: SLO burn, 3x traffic growth, budget breach,
  compliance changes, or major incidents
~~~

Never put credentials, customer data, or sensitive security rules inside widely shared ADRs. Link to appropriately restricted storage for sensitive details.

## 21. Practice Exercise: Deciding Under Constraints and Budget

Suppose a team operates a Spring Boot API backed by Cloud SQL and Pub/Sub, currently running as one Cloud Run deployment in a single region. The business wants higher availability on a limited incremental budget.

### Part A — Gather Requirements

1. Identify API users, peak hours, and the impact of a one-hour outage.
2. Define at least two SLIs: request success rate and on-time order completion rate.
3. Propose business-justified SLOs, RTO, and RPO.
4. Classify data into public, internal, confidential, and secret per policy.
5. List guardrails: allowed data regions, IAM boundaries, encryption, auditing, and retention.
6. Identify the budget ceiling, current cost baseline, and cost owner.

### Part B — Design Options

Compare at least three options:

- A: Current Cloud Run + Cloud SQL setup with improved canaries, backups, and monitoring.
- B: Cloud Run + intra-region Cloud SQL HA, adding fault isolation and backups/PITR.
- C: A multi-region option aligned with data residency and operational capabilities.

If justified, include GKE or Compute Engine as candidates and explain which requirements justify the added operational load.

For each option, document:

1. Component and trust-boundary diagram.
2. Failure modes and single points of failure.
3. IAM/service identities, ingress/egress, and secret management.
4. HA, backup, restore, failover, and schema migration strategies.
5. Minimum/base/peak cost estimates and unmeasured unknowns.
6. Pre-production verification tests.

### Part C — Scoring and Sensitivity Analysis

1. Eliminate options violating guardrails.
2. Identify dominated options.
3. Score remaining criteria using stakeholder-agreed weights.
4. Vary weights across security, reliability, and cost.
5. Check whether the winning option changes under stress scenarios.
6. Document residual risks and accountable owners.

### Part D — Empirical Verification

In an approved test project and environment:

1. Load-test base traffic and bounded peak traffic.
2. Measure P95 latency, error rates, database connections, and instance counts.
3. Run smoke tests after a canary release.
4. Inject a dependency timeout; observe retries and error-budget impact.
5. Execute a restore or failover drill per the prepared runbook.
6. Reconcile test spend against the cost model.
7. Finalize the ADR with the decision and revisit triggers.

**Never perform destructive tests or forced failovers in production outside approved operational procedures.** Creating test resources requires owners, quotas/caps, and cleanup plans.

### Grading Rubric

| Requirement | Passing Standard |
|---|---|
| Clear guardrails | Pass/fail checklist with owners |
| Quantitative reliability | Defined SLIs/SLOs/RTO/RPO with evidence |
| Data-flow security | Covers IAM, trust boundaries, secrets, audits |
| Complete costing | Includes networking, storage, backups, observability, operations |
| Option selection | Explicit trade-offs and sensitivity analysis |
| Next steps | Test plan, owners, deadlines, and ADR |

## 22. Pre-Approval Architecture Checklist

- [ ] Business goals and workload criticality are documented.
- [ ] Mandatory compliance, residency, security, and budget constraints are defined.
- [ ] Hard gates are separated from negotiable trade-offs.
- [ ] Threat model and data trust boundaries exist.
- [ ] Least privilege is designed for build, deploy, and runtime identities.
- [ ] Network ingress/egress, firewalls, VPCs, and in-transit encryption are reviewed.
- [ ] Secret/key lifecycles and key-unavailability recovery are decided.
- [ ] SLIs, SLOs, and exact error-budget formulas are defined.
- [ ] RTO, RPO, and matching failure scenarios are defined.
- [ ] Common-mode failures are analyzed, not just replica counts.
- [ ] HA, backups, PITR, and DR match targets and are drilled.
- [ ] Retries, idempotency, timeouts, circuit breakers, and queues are evaluated.
- [ ] DB connection limits and downstream quotas are sized for autoscaling.
- [ ] Consistency and replication are verified for any multi-region deployment.
- [ ] TCO covers compute, storage, networking, backups, telemetry, and operations.
- [ ] Cost allocation, budget alerts, and cost owners are assigned.
- [ ] Appropriate load, security, and failover tests ran in a safe environment.
- [ ] Rollout and rollback conditions for both app and data are verified.
- [ ] Assumptions, confidence levels, residual risks, and sensitivity are recorded.
- [ ] An ADR, review schedule, and approvers are documented.

## Self-Check Questions

**1. Why shouldn't a single weighted scorecard alone pick an architecture?**

Because a high score in one area can mask a violation of a mandatory constraint. Apply hard gates first, then compare compliant options using scores and evidence.

**2. How does a 99.9% request-based SLI differ from 99.9% uptime?**

A request-based SLI measures the ratio of valid requests succeeding; time-based uptime measures the duration the system meets availability conditions. Never convert between them without explicit definitions.

**3. Why doesn't adding API replicas guarantee meeting RPO?**

RPO depends on data, replication, backups, and restore points. API replicas scale compute, not database durability.

**4. Can CMEK introduce reliability risks?**

Yes. Broken key permissions, disabled keys, or wrong key locations can block a service from reading or writing data. Both access controls and key runbooks/monitoring are required.

**5. Why does lowering minimum instances require checking SLOs?**

Because it can increase cold starts and latency after idle periods. Lower it only if real latency stays within target.

**6. When might multi-region not be worth the investment?**

When a region outage's impact fits within RTO/RPO, multi-region cost and complexity outweigh the benefit, or the data layer cannot yet ensure consistency. Base this on requirements and tests, not dogma.

**7. Does setting a budget alert automatically stop spending?**

Typically no. Budget alerts notify at thresholds; automated spend caps must be built explicitly while weighing availability impacts.

**8. Why can retries worsen an outage?**

If many clients retry simultaneously or indefinitely, an overloaded dependency gets flooded with extra requests, prolonging the failure. Use backoff, jitter, timeouts, retry caps, and idempotency.

**9. What distinguishes TCO from a single instance's price?**

TCO also counts databases, networking, storage, telemetry, security, non-production environments, and operational labor across the lifecycle.

**10. When should an ADR be revisited?**

When traffic, SLOs, regulations, team capabilities, or costs shift substantially; after a major incident; or at the scheduled review trigger in the record.

## References

- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework)
- [Security, privacy, and compliance pillar](https://docs.cloud.google.com/architecture/framework/security)
- [Reliability pillar](https://docs.cloud.google.com/architecture/framework/reliability)
- [Cost optimization pillar](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Google Cloud Disaster Recovery Planning Guide](https://docs.cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Cloud SQL high availability for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud Run minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [Cloud Run multi-region](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud KMS customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [VPC Service Controls overview](https://docs.cloud.google.com/vpc-service-controls/docs/overview)
- [Cloud Logging routing overview](https://docs.cloud.google.com/logging/docs/routing/overview)
- [Cloud Billing budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)

## Conclusion

Evaluating trade-offs across **security, reliability, and cost** is an ongoing decision process. Security sets non-negotiable boundaries and controls; reliability is measured via SLIs, SLOs, error budgets, RTO, and RPO; cost reflects the entire lifecycle across infrastructure, data, networking, observability, and operations. These goals interact constantly: CMEK adds key dependencies, multi-region adds replication and routing, autoscaling strains databases, and trimming logs or compute alters incident detection and recovery.

A strong decision is not the option that wins every cell in a table, but the option that **satisfies mandatory guardrails, backs its trade-offs with evidence, operates within budget, and carries a verification plan for residual risks**. Measure before and after, record ADRs, assign owners, and proactively revisit choices as business requirements evolve.
