# Evaluating Architecture Against SLOs, Security, Operability, and Cost

A compute architecture cannot be evaluated solely by whether the application runs or has enough CPU and memory. A sound architecture must satisfy service quality objectives (SLOs), protect data and workloads, remain deployable, observable, and recoverable by the operations team, and stay within budget under both steady-state and incident conditions.

These four perspectives are tightly coupled. Increasing replica counts can boost availability while raising compute costs and attack surface. Choosing serverless reduces host management while introducing concurrency limits or cold starts. Using Spot cuts unit compute price while elevating retry rates and deadline risk. Encryption and private networking strengthen protection while requiring careful key lifecycle, DNS, egress, and observability design. Architecture evaluation must surface these trade-offs using requirements, measurements, and evidence.

Within the `CLOUD_CORE_SERVICES_COMPUTE` module, this capstone synthesizes knowledge across VMs, containers, Kubernetes, serverless, CPU/memory/network/storage, scaling, availability, identity, security, monitoring, backup/recovery, quotas, and cost governance. You will conduct a structured architecture review, score against criteria, identify risks, and propose verifiable improvements.

After this lesson, you will be able to:

- Define the scope, assumptions, stakeholders, and requirements of an architecture review.
- Translate business requirements into SLIs/SLOs, error budgets, RPO/RTO, and capacity targets.
- Evaluate compute architectures across availability, latency, throughput, durability, and scalability.
- Perform threat modeling and inspect identity, networking, data protection, workload hardening, and supply chain controls.
- Evaluate observability, deployment pipelines, incident response, backup/restore, and disaster recovery.
- Calculate TCO and unit economics, including redundancy, egress, managed services, operations, and failure costs.
- Compare options using trade-offs, a scoring rubric, and evidence-based decisions.
- Write findings, a risk register, ADRs, and a prioritized improvement roadmap.

## 1. Objectives and Scope of an Architecture Review

An architecture review is a systematic evaluation to verify whether a design meets requirements and can operate sustainably. A review does not merely hunt for misconfigurations; it examines the entire path across clients, workloads, compute, networking, storage, dependencies, operational processes, and costs.

### Core Questions

- Who does the system serve and which business workflows depend on it?
- How much disruption or data loss is acceptable?
- Do workloads run on VMs, containers, Kubernetes, serverless, or a hybrid model?
- What is current capacity versus peak and failover capacity?
- Who can deploy, access, modify, and recover the system?
- What evidence proves that SLOs, security controls, and recovery plans actually work?
- What is the total cost of ownership and cost per unit of work?
- Which assumptions remain unverified?

### Scope to Lock Down

| Scope Area | Examples | Must Specify |
|---|---|---|
| Business service | Checkout, reporting, image processing | Owner, criticality, business hours |
| Workload | API, worker, batch, database, cache | Runtime, duration, traffic pattern |
| Compute | VM, container, Kubernetes, function | Instance shape, requests/limits, scaling |
| Network | VPC/VNet, subnet, load balancer, NAT | Trust boundaries, ingress/egress, zones |
| Storage/data | Block, file, object, database | Data class, durability, retention |
| Identity/security | IAM, service account, certificates, secrets | Principals, permissions, trust |
| Operations | CI/CD, monitoring, on-call, backups | Teams, runbooks, recovery |
| Cost | Compute, storage, network, support | Budget, allocation, forecast horizon |

A review can focus on a single service or an entire platform. Even with a narrow scope, document external dependencies because they directly affect SLOs, security, and costs.

### Stakeholders

At minimum, involve the workload owner, platform/cloud engineer, SRE/operations, security, data owner, and FinOps/finance. For systems with regulatory requirements or sensitive data, include privacy, compliance, or risk owners. Every finding needs an owner authorized to execute remediation and an accountable person to accept risk if it is not remediated.

## 2. Gathering Evidence Before Evaluating

Architectural conclusions must rest on evidence. Architecture diagrams describe intent; live configurations and test results show actual state.

### Evidence Typically Needed

- Architecture diagrams and data flows.
- IaC, deployment manifests, and runtime configurations.
- Inventories of VMs, node pools, Pods, functions, databases, storage, and networks.
- SLI/SLO dashboards, alert history, and incident records.
- Load tests, benchmarks, and capacity forecasts.
- IAM/RBAC policies, security groups, network policies, and audit logs.
- Vulnerability scans, image provenance, and patch reports.
- Backup policies, restore tests, and DR exercises.
- Cost exports, billing reports, budgets, and allocation tags.
- Runbooks, on-call rotas, change records, and postmortems.
- Quota inventories, provider limits, and reservations/commitments.

### Evidence Confidence Levels

| Evidence Level | Description | Example |
|---|---|---|
| E0 – None | Mere assumption or verbal claim | "The database definitely has backups" |
| E1 – Documented | Exists in docs but unverified | Backup policy written in a design doc |
| E2 – Configured | Configuration or dashboard exists | Backup job enabled, alert rule deployed |
| E3 – Tested | Repeatable test results exist | Successful restore test with measured duration |
| E4 – Proven in production | Proven by live production history | Executed DR exercises and real incident responses |

Never mark a control as "passing" simply because documentation claims it exists. For example, having a backup job does not prove data restores cleanly; having an autoscaler does not prove quotas and provider capacity permit scaling.

### Evidence Register

For each criterion, record:

- Criterion ID.
- Requirement to satisfy.
- Evidence source and collection timestamp.
- Environment/region/version tested.
- Outcome and test limitations.
- Verifier.
- Remaining gaps.

Handle evidence according to security policies; exclude secrets, tokens, private keys, and unnecessary personal data from review artifacts.

## 3. System Modeling and Workload Profile

Before examining SLOs or costs, understand what the system actually does.

### Workload Profile

Capture:

- Requests/second, concurrent users, and traffic bursts.
- Batch volume, queue depth, task duration, and deadlines.
- CPU time, memory working set, and peak memory.
- Storage IOPS, throughput, latency, and capacity.
- Network throughput, packet rate, egress, and cross-zone traffic.
- Dependency call rates, connection pools, and service quotas.
- Statefulness, sessions, checkpoints, and durable data.
- Growth rate, seasonality, and major events.
- Sequential stages, parallel stages, and bottlenecks.

### Workload Classification

| Workload | Characteristics | Review Focus |
|---|---|---|
| Interactive API | Latency-sensitive, variable traffic | p95/p99, autoscaling, dependencies |
| Stateful service | Data and identity bound to members | Persistence, quorum, fencing, backups |
| Batch | Deadline-bound, partitioned tasks | Throughput, queues, retries, cost/run |
| Event-driven | Scales by events/invocations | Concurrency, cold starts, downstream |
| HPC/GPU | Compute/network/accelerator intensive | Utilization, interconnects, data feeds |
| Edge/hybrid | Connectivity and locality constraints | Offline behavior, sync, local recovery |

### Drawing Data Flows and Trust Boundaries

Diagrams must show clients, ingress, compute, service-to-service paths, databases, object storage, secrets, logging, backups, and the control plane. Mark public/private endpoints, account/project boundaries, regions, zones, identity principals, and where data is stored or transmitted.

Overly abstract diagrams cannot support security or failure-mode reviews. For instance, you need to know whether a function calls the database over a private endpoint or a public endpoint, and which account/region receives backups.

## 4. Evaluating SLOs and SLIs

An SLO (Service Level Objective) is an internal target for service quality over a time window. An SLI (Service Level Indicator) is the measurement used to evaluate performance. An SLA is an external commitment to customers or partners that may carry service remedies. Never treat these three terms as interchangeable.

### Choosing User-Meaningful SLIs

Common SLIs:

- Availability: fraction of valid requests served successfully.
- Latency: fraction of requests completing below a time threshold.
- Correctness: fraction of accurate outcomes or valid transactions.
- Freshness: delay before data becomes available as needed.
- Durability: ability to retain acknowledged data.
- Batch completion: fraction of jobs finishing before deadline.
- Queue age: age of unprocessed messages/tasks.

SLIs must measure user experience or business outcomes. 90% CPU utilization is an operational metric, not a service-quality SLI on its own.

### Sample SLOs

| Service | SLI | Sample SLO | Window |
|---|---|---|---|
| Checkout API | Successful eligible requests | 99.9% | 30 days |
| Checkout API | p95 latency | Under 300 ms | 30 days |
| Order database | Successful committed writes | 99.95% | 30 days |
| Analytics batch | Jobs completed by deadline | 99% before 05:30 | 30 days |
| Object processing | Valid output objects | 99.9% checksum pass | 30 days |

Numbers are illustrative. Real SLOs must reflect business impact, user expectations, architecture, and the cost of achieving the target.

### Availability and Error Budgets

For an availability SLO \(S\), the error budget over the window is:

\[
ErrorBudget = 1 - S
\]

For a 99.9% SLO, the error budget is 0.1% of requests or time depending on the SLI definition. Over a 30-day window measured continuously in time, 0.1% equals roughly 43.2 minutes. When measured by requests, compute against total eligible requests rather than converting directly to minutes.

Error budgets govern change velocity:

- Ample budget remaining: continue releasing per policy.
- Budget burning rapidly: increase testing, reduce change risk, or pause risky releases.
- Budget exhausted: prioritize reliability work and remediate root causes.

### Latency Percentiles

Average latency hides tail latency. Reviews should inspect p50, p90, p95, and p99 per endpoint and dependency. An API with an 80 ms p50 yet a 3-second p99 can deliver an unreliable user experience.

Evaluate end-to-end latency including DNS, TCP connect, TLS, queue wait, compute, database, serialization, and response—not merely function or container execution time.

## 5. Evaluating Availability, Resilience, and Failure Domains

Availability does not come from a single replica count. Identify components that can fail independently and verify how the system continues serving.

### Failure Domains

- Process/container.
- VM or worker node.
- Rack/host group or availability zone.
- Region.
- Network gateway, DNS, load balancer.
- Database primary/replica.
- Identity provider, secret manager, or KMS.
- Cloud control plane and external dependencies.
- Human/operator error.

### Review Questions

- Are there any single points of failure?
- Are replicas distributed across independent failure domains?
- If one node or zone fails, is surviving capacity sufficient?
- Does the load balancer route traffic strictly to Ready backends?
- Does database failover enforce fencing and consistency checks?
- Could retries cause duplicate transactions or retry storms?
- Are circuit breakers, timeouts, and bulkheads properly tuned?
- Is there a degraded mode when non-critical dependencies fail?

### RTO and RPO

- **RTO:** maximum tolerable time to restore service.
- **RPO:** maximum tolerable data loss measured in time.

Define RTO/RPO per data class or service tier. A regenerable cache has a near-irrelevant RPO; a transactional database typically requires a much tighter RPO.

### Availability Is Not Durability

Replication improves service continuity, but also replicates logic bugs or accidental deletes. Backups improve recoverability, yet do not necessarily enable instant failover. Reviews must evaluate replication, backups, point-in-time recovery, and restore tests together.

## 6. Evaluating Compute Choices and Resource Sizing

Every compute model carries trade-offs. Evaluate choices against the workload profile and lifecycle.

| Model | Strengths | Risks / Review Questions |
|---|---|---|
| VM | Control over OS, disk, network, and runtime | Patching, boot time, drift, instance quotas, idle cost |
| Container | Consistent images, packaged dependencies | Image security, runtime, resource limits, node capacity |
| Kubernetes | Scheduling, rollouts, service discovery, orchestration | Control plane, cluster complexity, quotas, CNI/CSI, operators |
| Serverless | Reduced host management, event-driven scaling | Concurrency, cold starts, runtime limits, vendor constraints |
| Managed batch/data service | Integrated scheduler and worker lifecycle | Pricing units, quotas, capacity availability, portability |
| GPU/HPC | Specialized accelerators and interconnects | Utilization, VRAM, data pipelines, capacity reservations |

### CPU

Inspect requests, limits, throttling, utilization, run queues, and CPU architecture. Overly tight CPU limits inflate latency; overly generous requests strand paper capacity and block Pod scheduling.

### Memory

Inspect working set, peak memory, heap, native memory, GC, OOMs, and memory pressure. Capacity planning must include sidecars, system daemons, and runtime overhead.

### Storage

Evaluate capacity, IOPS, throughput, latency, durability, topology, snapshots, and restores. A volume with plenty of GB yet insufficient IOPS will still cause a database to breach its SLO.

### Network

Evaluate bandwidth, packet rates, connection counts, NAT/egress, DNS, MTU, cross-zone transfer costs, and private endpoints. Compute-intensive workloads can still become network-bound during shuffles or large dataset downloads.

### Capacity Headroom

Never plan solely around average usage. Use peak, p95 demand, scale-out duration, quota runway, and surviving capacity when a failure domain is lost. Account for headroom across compute, subnet IPs, database connections, storage throughput, and API quotas.

## 7. Security Assessment via Threat Modeling

A security review starts with assets, actors, trust boundaries, and threat scenarios—not merely a checklist.

### Assets to Protect

- Business data and personal data.
- Credentials, tokens, certificates, and encryption keys.
- Images, packages, source code, and deployment artifacts.
- Compute resources and the control plane.
- Network paths and service endpoints.
- Backups, logs, and audit records.
- Workload availability and integrity.

### Threat Modeling

Use STRIDE or an equivalent methodology:

| Threat | Compute Architecture Example | Controls to Evaluate |
|---|---|---|
| Spoofing | Pod/VM impersonating another service | Workload identity, mTLS, attestation |
| Tampering | Modifying an image or data volume | Image signing, integrity checks, encryption |
| Repudiation | Unable to trace who altered configuration | Audit logs, immutable events, identity |
| Information disclosure | Secrets or data leaking via logs/egress | Secret manager, data classification, egress controls |
| Denial of service | Burst exhausting concurrency/connections | Rate limits, quotas, backpressure, autoscaling caps |
| Elevation of privilege | Pod abusing overly broad node role | Least privilege, RBAC, workload identity, isolation |

### Identity and Access

- Each workload has its own appropriate principal.
- Permissions follow least privilege.
- Long-lived access keys are never baked into images.
- Tokens enforce audience, expiration, and rotation.
- Instance metadata endpoints are protected.
- Admin access uses JIT/break-glass and auditing.
- RBAC/Cloud IAM is reviewed periodically.
- Backup creation and backup deletion permissions are separated.

### Network Security

- Public and private paths are documented.
- Security groups/firewalls open only required ports.
- Network policies segment workloads.
- Egress is controlled.
- Private endpoints/DNS are configured accurately.
- Ingress is protected by TLS/WAF/gateway where appropriate.
- On-premises/private links enforce bidirectional routing and firewalls.

### Data Protection

- Encryption at rest and in transit.
- Key management, rotation, and separation of duties.
- Backups have retention, immutability, or deletion protection where needed.
- Data residency and retention rules are satisfied.
- Secrets never appear in logs, images, public manifests, or tickets.

### Supply Chain and Runtime

- Images come from trusted registries with provenance/signatures.
- Dependencies are scanned for vulnerabilities.
- SBOMs and version pinning follow policy.
- OS/kernel/runtime patching is maintained.
- Non-root execution, seccomp, and minimal capabilities.
- Privileged mode is prohibited without explicit justification.
- Admission policies block non-compliant workloads.

## 8. Evaluating Operability

An architecture is operable only if the team can deploy, observe, diagnose, recover, and evolve it under real-world conditions.

### Deployment and Change Management

Verify:

- IaC and configurations are version-controlled.
- Build artifacts are immutable with provenance.
- Dev/staging/prod promotion is explicit.
- Deployments enforce health gates and rollbacks.
- Database/schema migrations follow compatibility strategies.
- Canary/blue-green/rolling updates fit the workload.
- Changes have owners, approvals, and audit trails.
- Drift is detected and remediated.

### Observability

Three common pillars:

- **Metrics:** SLIs/SLOs, saturation, capacity, quotas, cost.
- **Logs:** events, errors, audits, and context with correlation IDs.
- **Traces:** request paths across services and dependencies.

Add events and profiling where useful. Dashboards should answer: are users impacted, which stage is slow, which dependency is failing, how much capacity remains, and how are costs trending?

### Alert Quality

Alerts must be actionable with severity, owner, runbook, and escalation criteria. Avoid alerting purely on high CPU if that is normal behavior. Prefer symptom-based alerts such as error budget burn, p95 latency, queue age, database connection saturation, or shrinking batch deadline slack.

### Runbooks

Runbooks must specify:

- Symptoms and blast radius.
- Dashboards/logs/events to inspect.
- Safe verification steps.
- Available mitigations.
- Abort or escalation criteria.
- Rollback/recovery procedures.
- Criteria to confirm service restoration.
- Owner and contact paths.

### On-Call and Operational Load

Assess alert volume, incidents, toil, manual approvals, patching effort, restore time, and system complexity. An architecture might meet its SLO today while relying on heavy manual steps or a single hero engineer—that is an operational risk.

## 9. Backup, Restore, and Disaster Recovery

The review must verify that data and services can be recovered within target windows.

### Backup Design

- Backup frequency supports RPO.
- Application-consistent database backups where needed.
- Snapshots and object versioning follow policy.
- Isolated backup account/region where required.
- Encryption keys remain accessible during recovery.
- Retention and deletion protection enforced.
- Backup job success monitored.
- Scheduled restore testing in place.

### Restore Evidence

Record:

- Dataset/backup used.
- Recovery point.
- Start and completion timestamps.
- Actual RTO.
- Actual data loss/RPO.
- Errors encountered and manual interventions.
- Sign-off from application/data owners.

Backup job success does not prove restore success. Reviews require at least one documented restore test covering representative data scope.

### DR Strategy

| Model | Typical Cost | Relative RTO | Must Verify |
|---|---|---|---|
| Backup and restore | Lower steady-state | Long | Restore throughput, quotas, keys, IaC |
| Pilot light | Moderate | Moderate | Scale-up, dependencies, DNS |
| Warm standby | Higher | Shorter | Replication, capacity, failover |
| Active-active | High and complex | Potentially very short | Data consistency, conflicts, routing |

Actual RTO covers detection, decision, provisioning, restore/catch-up, validation, and traffic switch—not merely VM creation time.

### DR Testing

Rehearsals must verify compute quotas, storage quotas, networking/IPs, identities, secrets, certificates, DNS, load balancers, and dependencies in the target region. A standby region can experience capacity contention if many customers fail over simultaneously during a major outage.

## 10. Evaluating Performance and Scalability

Capacity reviews must answer whether the system handles both current load and forecasted demand.

### Performance Evidence

- Benchmarks with representative data/load.
- Load tests at steady-state, peak, and burst levels.
- p50/p95/p99 latency.
- Throughput and error rates.
- CPU/memory/storage/network saturation.
- Queue age and processing lag.
- Database connections and query latency.
- Scale-out and scale-in times.
- Cold start, image pull, and bootstrap durations.
- Performance when losing a node or zone.

### Autoscaling

Inspect metric triggers, min/max bounds, cooldowns, stabilization windows, quotas, startup delays, and dependency capacity. An autoscaler can launch additional replicas without increasing throughput if the database or an external API is already saturated.

### Quotas and Provider Capacity

Verify:

- Regional vCPU and instance family quotas.
- GPU/accelerator quotas.
- Subnet IP, ENI/NIC, and load balancer quotas.
- Serverless concurrency/request quotas.
- Storage size, IOPS, and snapshot quotas.
- Database connection and service API limits.
- Reservations or fallback instance families.

A quota increase does not guarantee physical provider capacity in a specific zone. When deadlines are strict, secure reservations/fallbacks or implement load-shedding plans.

## 11. Evaluating Cost and TCO

A cost review goes beyond comparing instance hourly rates. Total Cost of Ownership (TCO) spans infrastructure, managed services, networking, storage, operations, security, support, and failure costs.

### Cost Categories

| Category | Examples |
|---|---|
| Compute | VMs, container nodes, functions, GPUs, batch workers |
| Storage | Block volumes, object storage, snapshots, backups, IOPS |
| Network | Egress, NAT, load balancers, cross-zone/region transfer, VPN |
| Managed services | Databases, caches, queues, search, API gateways |
| Security | KMS, secrets, WAF, scanning, SIEM |
| Observability | Log ingestion/retention, metrics, traces |
| Operations | On-call, patching, platform engineering, support |
| Reliability | Redundant replicas, headroom, reservations, DR environments |
| Failure cost | Retries, downtime, data recovery, missed deadlines |

### Cost Model

A general model:

\[
TCO_{\text{period}} =
C_{\text{compute}} + C_{\text{storage}} + C_{\text{network}} +
C_{\text{managed}} + C_{\text{security}} + C_{\text{observability}} +
C_{\text{operations}} + C_{\text{DR}} + C_{\text{failure}}
\]

Use an identical time period and workload scope when comparing two options.

### Unit Economics

Measure cost per unit of business output:

- Cost per 1,000 successful API requests.
- Cost per processed order.
- Cost per GB transformed.
- Cost per batch completed on time.
- Cost per training step or inference.
- Cost per active tenant.

Cost per successful unit exposes configurations that look cheap per hour yet suffer low throughput, high retries, or heavy idle capacity.

### Idle Capacity and Overprovisioning

Inspect hourly utilization, idle nodes, unused reserved capacity, orphaned storage, log retention, and dev/test waste. However, never strip out headroom required for SLOs, N+1 resilience, or DR merely to trim short-term bills.

### Commitments and Spot

- Commitments suit steady baselines; monitor coverage and utilization.
- Spot suits retryable/checkpointable workloads.
- On-demand suits bursts or fallback.
- Reservations suit strict capacity needs where providers offer guarantees.

Compare cost per successful workload after factoring in interruptions, retries, provisioning lag, and idle time.

## 12. Evaluating Risks and Trade-Offs

No architecture optimizes every criterion simultaneously. Reviews must articulate benefits, costs, risks, and conditions under which trade-offs are acceptable.

### Example Trade-Offs

| Decision | Benefit | Cost / Risk | Acceptance Condition |
|---|---|---|---|
| Multi-zone replicas | Higher availability | Higher compute/network cost | Sufficient dependencies and data replication |
| Serverless | Less host operations | Runtime/concurrency/vendor limits | Workload fits duration and trigger model |
| Spot workers | Lower compute unit price | Interruptions, retries, deadline risk | Checkpointing/idempotency and fallback |
| Private endpoints | Less public exposure | Endpoint/DNS cost and complexity | Managed DNS, routing, and policies |
| Managed database | Lower DB ops toil | Service cost and control constraints | Clear SLAs, backups, exports, and exit plan |
| Multi-region active-active | Fast failover | Data conflicts, cost, complexity | Validated consistency model and thorough tests |
| Tight memory limit | Protects host node | OOMs and retries | Working set measured and headroom verified |

### Risk Register

Each risk entry needs:

- ID and description.
- Affected asset/service.
- Threat or failure scenario.
- Likelihood and impact.
- Existing controls.
- Residual risk.
- Planned mitigation.
- Owner and due date.
- Verification evidence.
- Risk acceptance owner if left unmitigated.

Apply a consistent likelihood/impact scale. Never mask severe risks behind high average scores in other areas.

## 13. Scoring Rubric for Architecture Reviews

A rubric helps compare options and highlight gaps. Scores never replace engineering judgment or mandatory gates.

### Scoring Scale

| Score | Level | Meaning |
|---:|---|---|
| 0 | Absent | No design, control, or evidence |
| 1 | Weak | Concept exists but lacks implementation or relies on manual steps |
| 2 | Partial | Controls exist with limited coverage or testing |
| 3 | Meets standard | Satisfies requirements with evidence and an owner |
| 4 | Good | Periodic testing, automation, and metrics in place |
| 5 | Strong | Continuous resilience/optimization, production evidence, ongoing improvement |

### Illustrative Weights

| Domain | Weight | Criteria |
|---|---:|---|
| SLO and resilience | 30% | Availability, latency, durability, RTO/RPO, scaling |
| Security | 25% | Identity, data, network, runtime, supply chain, auditing |
| Operability | 25% | Deployment, observability, incident response, backup/restore, ownership |
| Cost | 20% | TCO, unit economics, budget, utilization, forecasting |

Domain scores are weighted averages of their criteria. Overall score:

\[
Score_{\text{total}} = \sum_i Weight_i \times Score_i
\]

On a 0–5 scale, normalize weights to sum to 1. Example with SLO 3, security 4, operability 2, cost 3:

\[
Score = 0.30(3) + 0.25(4) + 0.25(2) + 0.20(3) = 3.0
\]

### Mandatory Gates

Never let an average score conceal critical defects. Define automatic review failures if:

- Critical data lacks backup/restore capability.
- Admin credentials or long-lived secrets are baked into images.
- Production services or incidents lack an owner.
- Critical SLOs cannot be measured.
- Mandatory RPO/RTO targets lack a viable recovery plan.
- Unapproved public exposure or over-privileged access violates policy.
- The DR region lacks quotas/capacity for critical workloads.

Review outcomes should capture scores, mandatory gates, the risk register, and the final decision. Never use a single numerical cutoff to auto-approve systems.

## 14. Evaluation Checklist by Domain

### SLO and Resilience

- SLIs reflect user/business outcomes.
- SLOs have owners and measurement windows.
- Error budget policy exists.
- Load tests validate peak and p95.
- Failure domains and N+1 capacity are accounted for.
- RPO/RTO are tested.
- Dependency timeouts, retries, and circuit breakers are tuned.
- Quotas/capacity suffice for failover.

### Security

- Threat model and data classification exist.
- Identities follow least privilege.
- Secret/key/certificate rotation and revocation are enforced.
- TLS/mTLS and network segmentation are configured.
- Image provenance and vulnerability management are active.
- Runtime hardening is applied.
- Audit logs and access reviews exist.
- Backups and data are protected.

### Operability

- IaC, CI/CD, rollouts, and rollbacks are in place.
- Metrics/logs/traces and actionable alerts exist.
- Runbooks and on-call rotations are established.
- Incident/postmortem and change management processes exist.
- Backup restores and DR exercises run periodically.
- Clear ownership covers services and dependencies.
- Toil and operational complexity are evaluated.
- Re-review triggers exist for major architecture changes.

### Cost

- TCO covers consistent scope and period.
- Unit economics are tracked.
- Compute/storage/network/managed-service costs are included.
- Logging/security/operations/DR costs are included.
- Headroom and reservations are justified.
- Spot/commitments match workload traits.
- Budget alerts and forecasts exist.
- Cost owners, allocation tags, and review cadences are defined.

## 15. Capstone Case Study: Order Processing Platform

A retail company operates a cloud order-processing platform. The system includes a checkout API, transactional database, event-processing workers, inventory service, and nightly reporting pipeline.

### Business Requirements

- Checkout operates 24/7.
- Peak load of 2,500 requests/second during campaigns.
- Monthly availability SLO of 99.95%.
- Checkout p95 latency under 250 ms.
- Zero loss of confirmed transactions.
- Database RPO max 1 minute and RTO max 30 minutes.
- Reporting finishes before 05:30 with 99% on-time rate.
- Production cloud budget capped at \$30,000/month.
- Order data stored strictly in approved regions.
- Admin access requires MFA and auditing.

These are exercise assumptions. In real practice, confirm SLOs, peaks, budgets, and data residency with stakeholders.

### Current Architecture

- API runs on 6 general-purpose VMs in one region, autoscaling on CPU.
- One managed primary database and one read replica.
- Workers run as containers on Kubernetes, scaling on queue depth.
- Serverless functions send emails and process webhooks.
- Object storage holds invoices and reports.
- A NAT gateway provides outbound Internet access.
- Monitoring focuses on CPU, memory, and error logs.
- Database backups run daily, with no recent restore exercise.
- Several services share a common cloud role.
- No quota dashboard exists; quota requests are submitted only when deployments fail.
- FinOps reviews total monthly bills without cost per order.

### Review Assignment

Evaluate the architecture across all four domains. For each finding, document current evidence, gaps, impact, likelihood, mitigation, and owner.

#### SLO/Resilience

- Do six VMs retain enough capacity if one VM or zone fails?
- Does CPU-based autoscaling react fast enough to request bursts?
- Does primary database failover meet the 30-minute RTO and 1-minute RPO?
- Could the read replica be misused for consistency-sensitive reads?
- Do worker queues have backlog and deadline alerts?
- Do email/webhook functions have retries, idempotency, and DLQs?

#### Security

- Is the shared cloud role overly permissive?
- Do the database and object storage use private paths and TLS?
- Does admin access enforce MFA, JIT, and auditing?
- Could secrets leak into environment variables, logs, or images?
- Are data region restrictions enforced by policy?
- Are webhook signatures and replay protections verified?

#### Operability

- Do SLO dashboards and error budgets exist?
- Are runbooks available for database failover, queue backlogs, and quota exhaustion?
- Have backup restores been tested?
- Are IaC and rollbacks defined for schemas and deployments?
- Does on-call know the owner of every dependency?
- Does monitoring include correlation IDs and end-to-end traces?

#### Cost

- Are compute VMs idle or suboptimally shaped?
- Could workers run on Spot with checkpointing?
- How much do NAT egress and cross-zone transfers cost?
- Is the database read replica right-sized for read load?
- Are log retention and trace sampling reasonable?
- Are unit cost per order and budget alerts tracked?

## 16. Sample Findings and Prioritization

| ID | Finding | Domain | Severity | Action |
|---|---|---|---|---|
| F-01 | Daily backups lack restore evidence | Operability/SLO | High | Execute restore test and measure RPO/RTO |
| F-02 | Multiple services share a broad role | Security | Critical | Split workload identities and apply least privilege |
| F-03 | Autoscaling relies solely on CPU | SLO | High | Add RPS, queue age, latency, and capacity signals |
| F-04 | No quota runway tracking | SLO/Operations | High | Build quota inventory, forecasts, and alerts |
| F-05 | No cost per order metric | Cost | Medium | Allocate costs via tags and unit metrics |
| F-06 | Webhook retries lack idempotency keys | Security/Reliability | High | Add signature validation, deduplication, and DLQ |
| F-07 | NAT egress unclassified by destination | Security/Cost | Medium | Review egress policies and private endpoints |

Severities are illustrative. Base severity on likelihood, impact, exposure, and detection/recovery capability. Findings often span multiple domains because a single flaw impacts SLOs, security, and cost simultaneously.

### Risk-Based Prioritization

A simple approach computes a risk score:

\[
Risk = Likelihood \times Impact
\]

Use a 1–5 scale for each factor. Scores help rank work; mandatory gates or severe compliance/security risks must still be addressed per policy even if their arithmetic score appears lower.

## 17. Architecture Improvement Roadmap

Do not attempt every change simultaneously. Sequence the roadmap by risk reduction, dependencies, and effort.

### 0–30 Days: Close Critical Gaps

- Split shared roles for critical workloads.
- Verify admin MFA/JIT/auditing.
- Run a database restore test.
- Create checkout SLO dashboards and alerts.
- Add quota inventories and near-limit alerts.
- Add idempotency/DLQs to critical webhooks.

### 31–60 Days: Strengthen Operability

- Load-test at 2,500 RPS and failure scenarios.
- Verify N+1/zone capacity.
- Add end-to-end distributed tracing.
- Author runbooks for database failover and queue backlogs.
- Implement cost allocation and cost per order.
- Review NAT egress, private endpoints, and log retention.

### 61–90 Days: Optimize and Validate

- Conduct a DR exercise and measure RPO/RTO.
- Tune autoscaling using latency, RPS, and queue age.
- Benchmark worker pools and Spot suitability.
- Tune database connection pools.
- Test patching and rolling upgrades.
- Evaluate TCO and 6–12 month growth forecasts.

Roadmaps require owners, due dates, effort estimates, expected risk reduction, dependencies, and completion evidence. Never treat ticket creation as completed mitigation.

## 18. Architecture Decision Record (ADR)

Every major decision should be documented so others understand its rationale and constraints.

### ADR Structure

~~~markdown
# ADR-012: Selecting a Compute Model for the Checkout API

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
- Peak 2,500 RPS
- Availability SLO 99.95%
- p95 latency < 250 ms
- Operations team has Kubernetes and VM capabilities

## Decision
- Run API on a multi-zone container platform
- Keep database on a managed service
- Autoscale on RPS/latency with CPU guardrails

## Alternatives
- VM autoscaling group
- Serverless containers/functions
- Managed application platform

## Consequences
- Increases platform complexity
- Requires node quotas and cluster operations
- Improves rollouts and resource isolation
- Requires DR/restore evidence

## Evidence
- Load test report
- Cost model
- Security review
- Failure exercise
~~~

Link ADRs to evidence and the risk register. When assumptions change, update or supersede the ADR; never let obsolete decisions remain treated as current policy.

## 19. Illustrative TCO Comparison for Two Options

Assume both options serve the same workload over one month:

| Cost Item | Option A: Self-Managed VMs | Option B: Managed Containers |
|---|---:|---:|
| Compute baseline/peak | \$8,000 | \$7,000 |
| Storage/database | \$5,000 | \$5,000 |
| Network/egress/NAT | \$1,800 | \$1,500 |
| Observability/security | \$1,200 | \$1,400 |
| Platform/support | \$900 | \$1,500 |
| Estimated operations effort | \$2,500 | \$1,800 |
| DR/headroom | \$1,600 | \$1,800 |
| **Illustrative total** | **\$21,000** | **\$20,000** |

Figures are for exercise illustration only. Option B has higher platform/observability lines yet lower operations effort, yielding a lower illustrative TCO. However, if the team lacks Kubernetes/managed-platform skills or SLOs do not need orchestration, transition costs and operational risk could negate Option B's advantage.

### Comparing Unit Cost

If Option A processes 10 million orders/month:

\[
CostPerOrder_A = \frac{21{,}000}{10{,}000{,}000}
= 0.0021\ USD
\]

If Option B processes 11 million orders/month:

\[
CostPerOrder_B = \frac{20{,}000}{11{,}000{,}000}
\approx 0.00182\ USD
\]

Ensure both options meet equivalent SLOs, security controls, and data quality before comparing unit costs. Comparing raw bills while ignoring workload volume or reliability is misleading.

## 20. Lifecycle-Based Architecture Evaluation

Architecture reviews must look beyond go-live day. Examine all lifecycle stages:

- Design: requirements, threat models, capacity models, and ADRs.
- Build: images, IaC, dependencies, scans, and provenance.
- Deploy: approvals, rollouts, health gates, and rollbacks.
- Run: SLOs, monitoring, incidents, quotas, and costs.
- Scale: forecasts, autoscaling, reservations, and dependency limits.
- Recover: backups, restores, DR, identity reissuance, and validation.
- Change: patching, upgrades, schema migrations, and deprecations.
- Retire: data retention, credential revocation, and resource cleanup.

A design may meet SLOs today yet lack the quota runway or patching process to sustain SLOs 12 months from now.

## 21. Evaluating Risk Cost and Cost of Failure

Cost of failure can include:

- Revenue lost during downtime.
- Transactions requiring reconciliation or refunds.
- Engineering and on-call overtime during incidents.
- Data recovery, reprocessing, and customer support.
- SLA credits or contractual penalties.
- Reputational damage and customer churn.
- Missed business opportunities from delayed launches.

Not every loss converts cleanly into exact currency. Use ranges or qualitative impact, state assumptions, and avoid false precision.

### Expected Annual Loss

A simple model:

\[
ExpectedLoss = ProbabilityOfEvent \times ImpactPerEvent
\]

If an outage carries a 10% annual probability and \$100,000 impact, simple expected annual loss is \$10,000. Investing \$6,000/year in a control or capacity buffer can be justified if it lowers probability or impact sufficiently. Analyze multiple scenarios and avoid treating correlated risks as independent.

## 22. End-to-End Architecture Review Process

1. **Intake:** identify service owner, review objective, scope, and timeline.
2. **Requirements:** gather business criticality, SLOs, RPO/RTO, budget, and compliance needs.
3. **Discovery:** collect diagrams, inventories, configs, dependencies, and workload profiles.
4. **Evidence collection:** gather dashboards, tests, policies, audits, restore logs, and cost data.
5. **Evaluation:** score SLO, security, operability, and cost against the rubric.
6. **Threat/failure analysis:** analyze attack paths, failure domains, and dependencies.
7. **Findings:** document gaps, severities, evidence, impact, owners, and mitigations.
8. **Trade-off review:** compare alternatives and record ADRs.
9. **Decision:** approve, approve with conditions, or reject/defer.
10. **Roadmap:** assign actions, owners, due dates, and completion evidence.
11. **Follow-up:** verify mitigations and update scores.
12. **Re-review:** trigger whenever workloads, regions, data classes, SLOs, or architectures change significantly.

### Decision Outcomes

- **Approve:** meets mandatory gates and residual risk fits risk appetite.
- **Approve with conditions:** tracked actions have deadlines, owners, and compensating controls.
- **Defer:** missing evidence or unclear dependencies require clarification.
- **Reject:** violates mandatory requirements or leaves unacceptable residual risk.

Approvers must hold proper authority. Reviewers must never accept risks on behalf of business or security owners.

## 23. Common Mistakes in Architecture Reviews

**Scoring by gut feel.** Back every conclusion with evidence, a rubric, and an owner.

**Reviewing diagrams alone.** Cross-check against live configurations and telemetry.

**Using CPU utilization as a stand-in for SLOs.** Measure latency, success rate, correctness, and batch deadlines.

**Treating multi-zone as complete HA.** Inspect databases, DNS, NAT, identity, quotas, and surviving capacity.

**Equating successful backup jobs with recovery readiness.** Execute restore tests and measure actual RTO/RPO.

**Checking IAM roles while ignoring networks and data.** Threat models must cover identity, networking, storage, runtime, and supply chain.

**Comparing compute prices instead of TCO.** Include operations, egress, logging, DR, retries, and failure costs.

**Averaging every criterion together.** Enforce mandatory gates for security, data protection, and critical SLOs.

**Leaving findings without owners or deadlines.** A review without tracked actions reduces zero risk.

**Skipping re-reviews after major changes.** Adding a new region, workload, data class, or dependency can invalidate the prior assessment.

## 24. Architecture Review Report Template

~~~markdown
# Architecture Review Report

## 1. Executive decision
- Service:
- Owner:
- Review date:
- Outcome: Approve / Conditional / Defer / Reject
- Overall score:
- Mandatory gates:

## 2. Scope and assumptions
- Workloads:
- Regions/accounts:
- Dependencies:
- Data classification:
- SLO/RPO/RTO:
- Budget and growth horizon:

## 3. Architecture summary
- Compute model:
- Network:
- Storage/data:
- Identity:
- Deployment/operations:

## 4. Scorecard
| Domain | Weight | Score | Evidence | Main gap |
|---|---:|---:|---|---|
| SLO/resilience | | | | |
| Security | | | | |
| Operability | | | | |
| Cost | | | | |

## 5. Findings and risks
| ID | Severity | Finding | Evidence | Owner | Due date |
|---|---|---|---|---|---|

## 6. Decisions and trade-offs
- Alternatives:
- Selected option:
- Consequences:
- ADR links:

## 7. Roadmap
- Immediate:
- 30 days:
- 60 days:
- 90 days:

## 8. Residual risk acceptance
- Risk:
- Business impact:
- Compensating control:
- Risk owner:
- Review date:
~~~

Keep the executive decision concise and the evidence/findings detailed enough for independent verification. Never place secrets, credentials, or sensitive data into reports.

## 25. Capstone Exercise: Conducting a Complete Architecture Review

Use the order-processing platform case study in Section 15 or choose an equivalent authorized system.

### Deliverables

1. Architecture diagram showing trust boundaries, data flows, and failure domains.
2. Workload profile and 6–12 month growth forecast.
3. SLO/SLI table, error budgets, and RPO/RTO targets.
4. Threat model identifying assets, actors, attack paths, and controls.
5. Operability review covering deployment, monitoring, on-call, runbooks, backup/restore, and DR.
6. Capacity model covering CPU, memory, storage, networking, quotas, and headroom.
7. TCO and cost per successful unit analysis.
8. Scorecard with evidence references and mandatory gates.
9. Risk register and at least three ADRs or architectural decisions.
10. 30/60/90-day roadmap with owners and acceptance evidence.

### Acceptance Criteria

- Every SLO specifies an SLI, query/measurement method, owner, and window.
- Evidence or test results exist for peak load and at least one failure scenario.
- Every security finding maps to an asset, threat, and control.
- Restore or DR has measured results, not merely policies.
- Cost model includes compute, storage, networking, managed services, and operations.
- Quotas and provider physical capacity are distinguished.
- Every high/critical finding has an owner and due date.
- Mandatory gates are explicitly adjudicated.
- Assumptions, limitations, and residual risks are documented.
- Conclusions trace directly back to evidence.

### Suggested Presentation Structure

- 1-page executive summary.
- 1 architecture diagram.
- 1 scorecard.
- 1 risk register.
- 1 TCO table.
- 1 roadmap.
- Appendix for evidence and test results.

## 26. Architecture Evaluation Checklist

### SLO and Resilience

- [ ] SLIs measure user/business outcomes.
- [ ] SLOs have owners, windows, and error budget policies.
- [ ] p95/p99 and dependency latencies are measured.
- [ ] Peak load and scale-out are benchmarked.
- [ ] Failure domains and N+1 capacity are accounted for.
- [ ] RPO/RTO are tested.
- [ ] Retries, timeouts, circuit breakers, and idempotency are appropriate.
- [ ] Quotas/capacity suffice for peak and DR.

### Security

- [ ] Data classification and threat model exist.
- [ ] Workload identities follow least privilege.
- [ ] Secret/key/certificate lifecycles are managed.
- [ ] Network segmentation and egress controls are enforced.
- [ ] Encryption at rest and in transit is enabled.
- [ ] Image provenance, vulnerability scanning, and patching are active.
- [ ] Runtime hardening and admission policies are applied.
- [ ] Audit logs, admin access controls, and backup protections are verified.

### Operability

- [ ] IaC, CI/CD, rollouts, and rollbacks exist.
- [ ] Metrics/logs/traces and actionable alerts are configured.
- [ ] Runbooks, on-call rotations, and escalations are defined.
- [ ] Incident/postmortem and change management processes exist.
- [ ] Backup/restore and DR exercises run regularly.
- [ ] Clear ownership exists for services and dependencies.
- [ ] Operational toil and skill requirements are evaluated.
- [ ] Re-review triggers exist for architectural changes.

### Cost

- [ ] TCO covers consistent scope and time windows.
- [ ] Cost per successful unit is calculated.
- [ ] Compute/storage/network/managed-service costs are accounted for.
- [ ] Logging/security/operations/DR costs are accounted for.
- [ ] Headroom and reservations are justified.
- [ ] Spot/commitments suit workload characteristics.
- [ ] Budget alerts and forecasts are configured.
- [ ] Cost owners, allocation tags, and review cadences are defined.

### Review Governance

- [ ] Evidence register is maintained.
- [ ] Rubric and mandatory gates are applied consistently.
- [ ] Findings have severities, owners, and due dates.
- [ ] ADRs document alternatives and consequences.
- [ ] Residual risks are signed off by authorized owners.
- [ ] Roadmap specifies acceptance evidence.

## 27. Self-Check Questions

1. How do SLIs, SLOs, and SLAs differ?
2. Why is CPU utilization insufficient to prove availability or latency SLOs?
3. How is an error budget calculated and used to pace releases?
4. Distinguish availability, durability, recoverability, RPO, and RTO.
5. Why can a multi-zone deployment still contain single points of failure?
6. How does threat modeling strengthen a compute architecture review?
7. Which layers of risk do workload identity, network policies, and encryption address?
8. What information does a strong runbook need for on-call incident response?
9. Why does backup job success fail to prove restore readiness?
10. How does TCO differ from a raw compute bill?
11. Why is cost per successful unit essential when comparing VMs, containers, and serverless?
12. How do mandatory gates prevent average scores from hiding critical risks?
13. How does level E1 evidence differ from E3 evidence?
14. When should an architecture be re-reviewed?
15. Evaluate the checkout case study across SLOs, security, operability, and cost; list your top three prioritized findings, missing evidence to gather, and a 90-day roadmap.

An architecture review creates value when conclusions rest on requirements and evidence, clarify trade-offs, surface residual risks, and translate into owned actions. SLOs define target quality; security defines how workloads and data are protected; operability proves the team can deploy, observe, and recover; and cost reveals whether the architecture remains financially sustainable as it grows. Evaluating all four dimensions together guides selecting a compute architecture suited to both present needs and long-term evolution.
