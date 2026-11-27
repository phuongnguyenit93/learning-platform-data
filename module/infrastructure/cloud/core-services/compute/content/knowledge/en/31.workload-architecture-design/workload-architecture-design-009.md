# Building a Decision Matrix Across Latency, Reliability, Cost, and Operational Capability

When designing a compute workload, you can choose among VMs, containers, serverless, managed platforms, or hybrid/edge architectures. Each choice has distinct strengths and limits: VMs give control over the OS and runtime; containers provide consistent packaging and deployment; serverless reduces server management; managed services shift part of operational responsibility to the provider; hybrid/edge brings processing close to data or devices. No single model is best for every workload.

To make a well-grounded decision, build an evaluation matrix across four core dimensions: **latency**, **reliability**, **lifecycle cost**, and **operational capability**. Scoring only becomes meaningful after defining mandatory constraints such as data residency, latency ceilings, RTO/RPO, execution duration, CPU architecture, connectivity, and security boundaries. An option with a high total score must still be disqualified if it violates any mandatory constraint.

## 1. Start with the Workload and Desired Outcomes

Never choose a compute model solely because the team already knows a technology or because a service type is popular. First, describe the workload in business and technical terms:

- Does the workload serve live requests, run continuous background processing, execute scheduled batches, or perform distributed computing?
- Who or what generates load; what do baseline, peak, burst, and growth look like?
- How fast do users need results; must data be processed near where it originates?
- When an instance, node, zone, region, or link fails, how must the system continue operating?
- What data is created, stored, or transmitted, and where must it be protected?
- Can work be paused, retried, checkpointed, or rerun?
- What level of deployment, monitoring, patching, and incident response can the current team sustain?

The output of this step is a workload profile used to compare candidates. A strong profile states both targets and bounds—for example: "The order lookup API needs p95 under 250 ms in the primary region, 99.9% availability, 30-minute RTO, 5-minute RPO, baseline load of 300 requests/s and peak of 1,500 requests/s; data must remain in approved regions; the operations team knows Kubernetes but lacks 24/7 on-call staffing for self-managed clusters."

## 2. Distinguish Hard Constraints from Optimization Criteria

A common mistake is summing all criteria into one overall score from the outset. That allows a very cheap option to make up points despite violating legal rules or SLOs. Separate two layers:

1. **Hard constraints:** if unmet, disqualify the option regardless of scores on other criteria.
2. **Scored criteria:** used to compare remaining feasible options.

Examples of hard constraints:

- Data must stay inside an approved region/site.
- Maximum latency to devices must not exceed measured thresholds.
- Workload must run on a specified CPU architecture or accelerator.
- Job duration must fit within platform runtime limits.
- RPO/RTO must satisfy business requirements.
- Mandatory private connectivity, isolation, or access controls must exist.
- Must support offline mode at the edge or keep operating during WAN outages.
- Must be compatible with certified software/vendors.

If an option fails a hard constraint, mark it `Ineligible` with the reason; exclude it from weighted-average scoring.

## 3. Defining the Four Criteria Groups

### Latency

Latency is the time from when an operation starts until the required result or response is ready. Distinguish:

- **Request latency:** time a client waits for a request-response.
- **Queueing delay:** time a task waits before a worker begins processing.
- **Processing time:** time CPU/GPU or application logic spends executing the work.
- **Network latency:** transit and response time across the network.
- **End-to-end latency:** total elapsed time across steps in the business flow.
- **Tail latency:** high percentiles like p95/p99 reflecting slow-request experience.

Never rely solely on average latency. An API averaging 40 ms with a 2-second p99 can breach its SLO for a meaningful share of requests. For background work, queue age and time from event creation to completion often matter more than a single function's execution duration.

### Reliability

Reliability reflects the workload's ability to deliver correct, continuous functionality under predictable failure modes. Factors include:

- Availability/SLOs and error budgets.
- Tolerance to instance, node, rack, zone, or region failures.
- RTO (target recovery time) and RPO (maximum acceptable data loss).
- Backups, restores, replication, and consistency.
- Health checks, failover, retries, idempotency, and graceful shutdown.
- Observability, incident detection, and response times.
- Dependencies on control planes, WANs, DNS, identity, or external services.

Running multiple replicas does not automatically create HA. If all replicas share the same zone, storage, or dependency, a single shared failure can take down the entire workload.

### Cost

Compare full lifecycle cost rather than looking solely at VM or function unit prices. TCO should include:

- Compute, memory, GPUs, and reserve capacity.
- Storage, IOPS, snapshots, backups, and retention.
- Networking, egress, cross-zone transfer, NAT, load balancers, and connectivity.
- Licenses, support plans, and managed service fees.
- Logging, metrics, tracing, security tooling, and data retention.
- Migration, parallel-run, testing, and decommissioning costs.
- Engineering labor for platform development, on-call, patching, backups, and incident response.
- Cost of downtime, data loss, or missed deadlines where quantifiable.

Compute unit economics such as cost per successful request, completed task, processed record, or useful compute hour. A higher total bill can still be an improvement if completed units of work grow faster while SLOs hold.

### Operational Capability

Evaluate whether the organization can run the option safely and reliably:

- Skills across OS, networking, storage, containers, Kubernetes, serverless, or databases.
- On-call coverage, incident response, and vendor coordination.
- Tooling for CI/CD, IaC, secrets, observability, and policy enforcement.
- Processes for patching, vulnerability management, backup/restore, and DR testing.
- Capacity, quota, autoscaling, and cost governance capabilities.
- Maturity of runbooks, ownership, change management, and service catalogs.
- Number of self-managed components and degree of vendor reliance.

An architecture with great benchmark performance that exceeds current operational capability can raise downtime and staffing costs. Account for capability-building in the roadmap—do not assume the team will magically acquire all skills on go-live day.

## 4. Gathering Evidence Before Scoring

A trustworthy decision matrix relies on data rather than gut feelings. Gather at least:

| Group | Data Needed | Typical Sources |
|---|---|---|
| Latency | p50/p95/p99, queue age, network RTT, processing duration, cold starts | APM, tracing, load tests, synthetic checks |
| Reliability | Uptime, error rates, incident history, RTO/RPO, restore times, failover tests | Monitoring, incident logs, DR drills |
| Cost | Usage profiles, invoices/exports, storage growth, egress, licenses, staffing estimates | Billing exports, cost calculators, inventory, operations time estimates |
| Operations | Deployment frequency, recovery time, on-call coverage, patch cadence, skill matrix | CI/CD, incident reviews, team assessments, runbook audits |
| Workload | Request rate, concurrency, job duration, payload size, data locality, dependency graph | Metrics, profiling, application inventory |

If an existing workload lacks metrics, run a baseline or pilot. Document measurement window, sample size, test load, region, instance types, cache state, and assumptions. A short benchmark on an idle test environment does not represent production peaks.

## 5. Setting Latency Thresholds by Workload Type

No single latency threshold fits every system. Derive thresholds from user behavior and dependencies:

| Workload | Primary Metric | Decision Questions |
|---|---|---|
| Interactive API | p95/p99 request latency | Can users wait? What are gateway and client timeouts? |
| Internal transactions | End-to-end transaction latency | Is a synchronous reply needed or can it return a job ID? |
| Background worker | Oldest message age, queue wait, task duration | Within what time after creation must events finish? |
| Batch | Job duration, throughput, completion deadline | By what wall-clock time must the job finish? |
| HPC/distributed AI | Communication latency, all-reduce time, step time | Is the network on the critical path? |
| Edge control | Local response time and WAN dependency | Must it respond even when cloud connectivity drops? |

For latency-sensitive workloads, inspect placement, network hops, zone/region distance, cold starts, connection setup, storage I/O, and dependency chains. When data lives at the edge, bringing compute near data cuts latency and egress, while increasing the number of sites to manage.

## 6. Evaluating Reliability via Failure Scenarios

Do not score reliability solely by replica count or published service SLAs. List failure scenarios and verify how the workload recovers:

- A process/container crashes.
- A VM or node loses connectivity.
- A rack or availability zone becomes unavailable.
- The database, queue, or identity provider suffers an outage.
- The WAN link from edge to cloud drops.
- A region fails or the control plane becomes unreachable.
- A bad release deploys and requires rollback.
- Backups exist, yet restores are slow or fail.

For each scenario, record detection time, recovery action, actual RTO, potential data loss, functional degradation, and responsible owner. Award strong reliability scores only when backed by test evidence or rehearsed runbooks.

### RTO and RPO Must Tie to Data

RTO is the target maximum time to restore service. RPO is the maximum acceptable data loss measured in time or data points. A stateless workload can recover by spawning new replicas; a stateful database needs backups/replication and consistency checks. Never apply the same RTO/RPO assumption to compute and data stores when recovery mechanics differ.

## 7. Building a Comparable TCO Model

To compare VMs, containers, serverless, and managed services, use the same workload profile, same region/network conditions, same SLOs, and same analysis horizon.

A general model:

\[
TCO = C_{compute} + C_{storage} + C_{network} + C_{platform} + C_{license} + C_{observability} + C_{operations} + C_{migration}
\]

Where `C_operations` covers operational and support labor. If reliable monetary data for staffing is unavailable, track it as a separate effort estimate or score—do not add arbitrary dollar guesses onto cloud invoices.

Example compute formula for always-on VMs:

\[
C_{VM} = N \times H_{month} \times P_{hour}
\]

For load-scaled workers:

\[
C_{worker} \approx \sum_i (N_i \times H_i \times P_i) + C_{queue} + C_{network} + C_{storage}
\]

For functions:

\[
C_{function} \approx N_{invocations} \times Duration \times AllocatedResources + C_{requests} + C_{dependencies}
\]

These formulas are conceptual models; billing units, minimums, free tiers, provisioned concurrency, request metering, egress, and discounts vary by provider. Verify using actual billing calculators and exports.

## 8. Assessing Operational Capability by Actual Responsibilities

For each option, list what the team manages directly versus what is managed by the provider:

| Responsibility | Self-Managed VMs | Containers on Kubernetes | Serverless / Managed Platform |
|---|---|---|---|
| OS patching | Usually managed by workload/platform team | Worker nodes/OS managed by platform depending on mode; images still need updates | Host/runtime mostly managed by provider; app dependencies still updated by team |
| Runtime/app dependencies | Application team | Application team and image pipelines | Application team and package/dependencies |
| Scheduling/placement | VM/orchestrator or operator | Kubernetes scheduler and platform | Provider runtime/event service |
| Autoscaling | Must configure VM groups/agents or orchestrator | HPA/VPA/node autoscalers and quotas | Provider scales on requests/events within service limits |
| Network/security | OS, firewalls, subnets, IAM, endpoints | Cluster/network policies, ingress, service accounts, nodes | IAM, trigger permissions, VPC access, and service policies |
| Observability | Self-configured agents/stacks | Cluster + workload telemetry | Integrated service logs/metrics/traces; dashboards/alerts still needed |
| Backup/DR | Self-designed across OS/app/data | Manage state, PVs, cluster, and data | Provider may offer features; retention/restore still must be designed |
| On-call | Depends on team and automation | Requires cluster/platform expertise | Must understand events, quotas, timeouts, retries, and provider limits |

Managed does not mean "zero operations." Responsibility shifts from host administration to service configuration, IAM, quotas, retries, data lifecycles, costs, and observability. Review each specific service's shared responsibility model.

## 9. Establishing a Consistent Scoring Scale

A 1–5 scoring scale can be defined as follows:

| Score | General Meaning | Latency | Reliability | Cost | Operations |
|---:|---|---|---|---|---|
| 1 | Very poor / misses soft targets | Far exceeds target thresholds | Hard to recover, lacks evidence | Very high TCO vs. value | Exceeds current team capability |
| 2 | Poor | Frequently near/breaching thresholds | Multiple single points of failure, weak runbooks | High | Requires many new skills/processes |
| 3 | Acceptable | Meets most measured load | Basic HA/backups with partial testing | Within expected budget | Team can operate with support |
| 4 | Good | Meets SLO with headroom | Failure-tested, clear recovery | Competitive TCO | Clear automation and ownership |
| 5 | Very good | Strong headroom at peak/tail | Multiple rehearsed scenarios, reliable recovery | Low TCO on unit economics | Mature capability, automation, and on-call |

Anchor the scoring rubric concretely to the workload. For instance, a latency score of 5 might mean p99 under half the threshold; a reliability score of 5 might require DR drills meeting RTO/RPO; an operations score of 5 requires automated deployments, patching, and incident response. Never leave a score of 4 open to personal interpretation.

## 10. Choosing Weights Aligned with Workload Goals

Weights express the relative importance of each category. Weights must sum to 100% or 1.0.

Illustrative reference weights:

| Workload Type | Latency | Reliability | Cost | Operations | Rationale |
|---|---:|---:|---:|---:|---|
| Interactive API | 35% | 30% | 15% | 20% | User experience and availability dominate |
| Critical transactions | 20% | 40% | 10% | 30% | Correctness and recovery take priority |
| Batch/analytics | 15% | 25% | 35% | 25% | Cost per record and deadlines matter most |
| HPC/distributed AI | 40% | 20% | 25% | 15% | Network/compute performance dominates |
| Edge/industrial | 30% | 35% | 15% | 20% | Local responsiveness and WAN-offline operation |

These are starting points only. For regulated or mission-critical workloads, reliability may be a hard constraint rather than merely carrying extra weight. Never apply identical weights blindly across a whole module or every application.

## 11. Calculating Weighted Scores

After eliminating options that violate hard constraints, compute:

\[
Score = W_L \times S_L + W_R \times S_R + W_C \times S_C + W_O \times S_O
\]

Where:

- `W_L`, `W_R`, `W_C`, `W_O` are weights for latency, reliability, cost, and operations, summing to 1.
- `S_L`, `S_R`, `S_C`, `S_O` are 1–5 scores for each criterion.

A higher score indicates a better fit under the chosen weights and rubric. It is neither a probability of success nor a performance guarantee. Record component scores, supporting evidence, assumptions, and confidence levels.

When two options are separated by a tiny margin, do not declare an absolute winner. Run sensitivity checks: vary weights, cloud pricing, peak load, or operational assumptions to see if rankings flip.

## 12. Sample Decision Matrix Across Compute Models

The table below provides an initial qualitative comparison for a common web/API workload—not a universal conclusion for all systems. Replace scores with real measurements and constraints.

| Option | Latency | Reliability | Cost | Operations | Strengths | Key Limitations |
|---|---:|---:|---:|---:|---|---|
| Self-managed VMs | 3 | 3 | 3 | 2 | OS/runtime control, legacy compatibility | Patching, HA, scaling, and capacity require manual operations |
| Containers on Kubernetes | 4 | 4 | 3 | 2 | Deployment, scheduling, scaling, and portability | Requires cluster, network, storage, and platform expertise |
| Serverless functions | 3 | 4 | 4 | 4 | Minimal host management, event/request scaling | Cold starts, timeouts, quotas, runtime constraints, vendor limits |
| Managed app/container platform | 4 | 4 | 3 | 4 | Reduces cluster/host overhead, integrated autoscaling | Service fees and platform limits must be verified |
| Hybrid/edge compute | 5 on local path | 3 | 2 | 2 | Processing near devices/data, continues offline | Complex fleet, site connectivity, updates, and identity |

Scores in this table are illustrative to explain the method. They are not benchmarks, SLAs, or quotes from any provider. In particular, hybrid/edge does not automatically score 5 on latency or 3 on reliability; real outcomes depend on topology, hardware, WANs, power, site operations, and synchronization.

## 13. Scoring Example for a Commercial API

Suppose an API requires p95 under 200 ms in the primary region, 99.9% availability, 30-minute RTO, and a team with basic container skills but no 24/7 Kubernetes on-call coverage. After a pilot, three options are scored:

| Criterion | Weight | VM | Kubernetes | Managed Container Platform |
|---|---:|---:|---:|---:|
| Latency | 0.35 | 4 | 4 | 4 |
| Reliability | 0.30 | 3 | 4 | 4 |
| Cost | 0.15 | 3 | 3 | 3 |
| Operations | 0.20 | 3 | 2 | 4 |

Calculations:

\[
Score_{VM} = 0.35(4)+0.30(3)+0.15(3)+0.20(3)=3.35
\]

\[
Score_{K8s} = 0.35(4)+0.30(4)+0.15(3)+0.20(2)=3.45
\]

\[
Score_{Managed} = 0.35(4)+0.30(4)+0.15(3)+0.20(4)=3.85
\]

Under these assumptions, the managed container platform scores highest because it matches latency/reliability while fitting current operational capability. If the team already had a 24/7 platform team and a shared cluster with spare capacity, Kubernetes' operations score would rise and rankings could shift.

Before deciding, verify all three candidates satisfy every hard constraint: p95 latency, availability, RTO, data location, network paths, security, and quotas. If the managed platform fails a networking or data-residency rule, it is disqualified despite scoring 3.85.

## 14. Decision Example for Batch Data Processing

An ETL job runs 2–3 hours nightly, processes large files, can be partitioned, and must finish before 05:00. Users do not wait on synchronous responses.

Options:

- Scheduled VMs: full environment control, but requires managing boot, patching, scheduling, and capacity.
- Container Jobs: packages dependencies cleanly, runs finite tasks, scales easily by partition if supported.
- Serverless functions: fits short steps or tiny partitions; unsuitable if single invocations breach timeouts or payload limits.
- Managed batch service: provides queues, job scheduling, retries, and placement; check fees and limits.

Weights might be 15% latency/deadline, 25% reliability, 35% cost, 25% operations. Key metrics include cost per million records, completion time, retry rate, checkpoint recovery, and storage/network throughput. A slightly slower option that is cheaper and finishes reliably ahead of the deadline can beat the highest-throughput option.

## 15. Decision Example for an Edge Workload

A factory gateway must process local control signals within 20 ms and keep operating during 4-hour WAN outages. Data syncs to the cloud afterward.

Cloud-only serverless violates hard constraints if control loops must traverse the WAN. An on-site edge runtime/container or native service handles local control, while the cloud handles fleet management, long-term analytics, and reporting.

Criteria to evaluate:

- Local p99 latency under heavy CPU/storage load.
- Offline operation, buffer quotas, and buffer-full behavior.
- RTO on gateway reboot and state recovery capability.
- Certificates/device identities and revocation/rotation workflows.
- Hardware costs, replacements, site support, and offline updates.
- Site operator capability to troubleshoot without the cloud control plane.

In this case, a hybrid architecture fits best: edge compute for latency-critical control loops; cloud services for orchestration, analytics, and centralized storage. This decision stems from hard constraints and data locality—not because edge is inherently cheaper or more reliable than cloud.

## 16. Considering Hybrid Architectures Instead of a Single Platform

One workload can split into components with differing needs:

| Component | Characteristics | Potentially Suitable Model |
|---|---|---|
| Ingestion API | Low latency, request-response | Managed containers, VMs, or serverless HTTP |
| Workers | Async tasks, retries, queue scaling | Container workers or event-driven functions |
| Batch analytics | Finite jobs, throughput, checkpoints | Container Jobs, scheduled VMs, or managed batch |
| Database | State, consistency, backup/restore | Managed database or self-managed database when specialized controls are needed |
| Edge collector | Local I/O, offline buffering, device protocols | Edge containers/native services |
| Control plane | Fleet, policy, and rollout management | Cloud managed services or platform services |

Never force every component onto one compute model solely for technological uniformity. You can share CI/CD, image conventions, identity standards, logging schemas, and service catalogs while letting runtimes match each component's workload profile.

## 17. Incorporating Operational Capability into the Decision Matrix

To avoid scoring operations subjectively, rate each capability by maturity level:

| Capability | Level 1: Manual | Level 2: Process-Driven | Level 3: Basic Automation | Level 4: Mature Operations |
|---|---|---|---|---|
| Deployment | Manual installs | Controlled runbooks | CI/CD and rollbacks | Progressive delivery, policy, and auditing |
| Infrastructure | Manual configuration | Standardized templates | IaC, reviews, and drift detection | Reusable platform, policy as code |
| Observability | Scattered logs | Basic dashboards | Metrics/logs/traces and alerts | SLOs, error budgets, anomalies, linked runbooks |
| Incident response | Hero-dependent | On-call and runbooks | Drills and postmortems | SLO-driven response, automation, continuous improvement |
| Security/patching | Ad-hoc updates | Patch schedules and scans | Image/base patch pipelines | Risk-based remediation, attestation, compliance evidence |
| Backup/DR | Untested backups | Policies and restore runbooks | Periodic restore tests | DR exercises, measured RTO/RPO, automation |
| Cost governance | Read end-of-month bills | Budgets and owners | Tagging, allocation, and alerts | Unit economics, forecasting, continuous optimization |

If a workload demands Level 4 while the team sits at Level 1, build capability upgrades, budget, and timeline into the plan prior to go-live. Choose managed services initially to limit operational scope, then self-manage later only if capability matures and economic benefits are proven.

## 18. Assessing Vendor Lock-In Risk and Portability

Costs and operations are also shaped by reliance on provider-specific APIs, runtimes, databases, event services, or proprietary networking.

Evaluate:

- Can artifacts run on another runtime?
- Can data be exported in reasonable formats and timeframes?
- Are APIs, IAM, event schemas, and observability tied to proprietary extensions?
- Can the managed database or queue be swapped without rewriting the whole app?
- Do egress, transfer, and migration fees create lock-in barriers?
- Does the team have skills to run the alternative option?
- Can operations continue during a migration or provider outage?

Maximum portability is not always necessary. Deep adoption of managed services cuts operational burden and speeds delivery. Balance immediate gains against exit costs, resilience goals, and commercial leverage.

## 19. Sensitivity Analysis

Total scores shift when assumptions change. Test at least these scenarios:

- Load doubles or peaks last longer than expected.
- Compute/network prices rise or commitment discounts change.
- Availability target rises from 99.9% to 99.95%/99.99%.
- One zone fails and the workload runs on remaining capacity.
- The team fails to hire assumed operational skills in time.
- Provider enforces quota limits or target instance types face capacity shortages.
- Edge WAN outages last longer or site counts grow rapidly.

If tweaking one small assumption flips the winner, the decision has high sensitivity. In that case, run a pilot, negotiate terms, improve measurements, or pick a more adaptable architecture.

## 20. Decision Matrix Template for a Workload

Use this template in design reviews. Replace placeholders with measured data and evidence sources.

| Field | What to Record |
|---|---|
| Workload/service ID | Service name in catalog |
| Business owner / technical owner | Business unit and engineering team |
| Workload type | Online, worker, batch, HPC, edge, or hybrid |
| Region/site/data location | Permitted processing and storage locations |
| Latency target | p95/p99 or queue age/end-to-end deadlines |
| Reliability target | Availability, RTO, RPO, and failure scenarios |
| Cost envelope | Budget, TCO horizon, and unit economics |
| Operations capability | Skills, on-call, automation, runbooks, and support |
| Hard constraints | Mandatory rules and compliance evidence |
| Candidate architectures | VM, container, serverless, managed, hybrid/edge |
| Weighted score | Score under agreed weights |
| Risks/assumptions | Risks, assumptions, and data confidence |
| Decision | Selected option and rationale |
| Review trigger | Conditions prompting re-evaluation (e.g., load/price/site growth) |

Scorecard template:

| Criterion | Weight | Option A | Evidence A | Option B | Evidence B |
|---|---:|---:|---|---:|---|
| Latency |  |  |  |  |  |
| Reliability |  |  |  |  |  |
| Cost |  |  |  |  |  |
| Operations |  |  |  |  |  |
| Total | 100% |  |  |  |  |

Score strictly on the 1–5 scale and never leave evidence cells blank. If data is missing, mark `Not measured` and schedule a pilot—never invent high scores just to finish the table.

## 21. Decision and Approval Process

A design decision can follow these steps:

1. **Identify owners and goals:** service owner, business owner, SLOs, budget, and data boundaries.
2. **Gather workload profile:** load, latency, dependencies, state, runtime, and data location.
3. **Define hard constraints:** disqualify candidates failing mandatory requirements.
4. **Build shortlist:** pick genuinely viable candidates, typically 2–4 options.
5. **Gather evidence:** benchmarks, cost estimates, failure tests, and operational assessments.
6. **Set weights and score:** involve application, platform, security, operations, and finance stakeholders.
7. **Sensitivity analysis:** vary key assumptions to verify decision stability.
8. **Record ADR/design doc:** capture selection, rationale, trade-offs, risks, and rejected options.
9. **Pilot and verify:** run a small-scale deployment under representative load and failure scenarios.
10. **Approve and deploy:** define go/no-go criteria, rollout, and rollback plans.
11. **Post-launch review:** compare actuals to assumptions and re-evaluate as the workload evolves.

Architecture decisions need explicit revisit triggers. For example, when traffic grows 5x, the workload moves regions, RTO tightens, or the team gains new platform capabilities, an old decision matrix may no longer hold.

## 22. Recording Decisions with an Architecture Decision Record

An ADR documents why a choice was made so future teams understand the context without relitigating everything from scratch.

Short template:

```markdown
# ADR-014: Select Managed Container Platform for Orders API

## Context
- p95 latency target: 200 ms
- Availability target: 99.9%
- RTO: 30 minutes
- Team has container skills, lacks 24/7 Kubernetes on-call coverage

## Decision
Select a managed container platform in the approved region.

## Rationale
- Met latency and reliability targets during pilot.
- Higher operations score than self-managed Kubernetes.
- TCO fits within projected budget.

## Trade-offs
- Dependency on platform APIs and service quotas.
- Must validate egress costs and exit plan.

## Validation
- Load test, zone failure exercise, restore test, and cost review.

## Revisit when
- Traffic grows 3x, platform pricing shifts significantly, or data residency rules change.
```

This is an illustrative example, not a decision applied to a real system. Real ADRs must link to actual test results, cost estimates, and named approvers.

## 23. Common Mistakes When Building Decision Matrices

- **Scoring before checking hard constraints:** an invalid option can win on low price. Disqualify constraint violations first.
- **Using average latency:** hides tail latency. Track p95/p99 and end-to-end times.
- **Equating replicas with HA:** ignores shared failure domains and dependencies. Rehearse node/zone/dependency failures.
- **Comparing compute prices alone:** misses networking, storage, licenses, observability, and staffing. Use TCO and unit economics.
- **Measuring operations by count of managed services:** managed services still need IAM, quotas, data lifecycles, alerts, and incident response. Use a responsibility matrix.
- **Using identical weights for all workloads:** APIs, batches, HPC, and edge have different priorities. Align weights with SLOs and business impact.
- **Scoring without evidence:** turns rankings into personal opinions. Attach metrics, benchmarks, invoices, or test reports to every score.
- **Assuming future team capabilities exist today:** never assume skills appear overnight. Document hiring, training, or managed-support plans.
- **Skipping sensitivity checks:** rankings flip when prices or load shift. Test multiple scenarios.
- **Treating portability as free:** excessive abstraction adds cost and dilutes managed-service value. Weigh exit costs against realistic risks.
- **Never reviewing post-launch:** workloads evolve while architectures stagnate. Set explicit review triggers and schedules.

## 24. Pre-Finalization Checklist

**Workload and Hard Constraints**

- [ ] Workload profile covers request rate, peaks, concurrency, data size, and dependencies.
- [ ] Request latency, queue age, processing time, and end-to-end latency are separated.
- [ ] Clear p95/p99 latency targets or processing deadlines exist.
- [ ] Availability/SLOs, RTO, RPO, and failure scenarios are defined.
- [ ] Data residency, security, CPU architecture, networking, and runtime limits are identified.
- [ ] Options violating hard constraints are eliminated with documented reasons.

**Scorecard and Cost**

- [ ] Weights match workload goals and sum to 100%.
- [ ] The 1–5 rubric is anchored to measurable thresholds.
- [ ] Every score cites evidence or is marked unmeasured.
- [ ] TCO includes compute, storage, network, licenses, managed services, observability, operations, and migration.
- [ ] Unit economics are calculated per successful request/task/record.
- [ ] Low/expected/high scenarios and sensitivity analysis are completed.

**Operational Capability and Decision**

- [ ] Owners, on-call coverage, skill matrices, runbooks, and support models exist.
- [ ] Patching, security, backup/restore, scaling, and incident duties are assigned.
- [ ] Pilots, load tests, and failure tests ran on representative workloads.
- [ ] An ADR records the decision, rationale, trade-offs, risks, and rejected alternatives.
- [ ] Go/no-go criteria, rollout, rollback, and review triggers are defined.
- [ ] A schedule exists to compare actual latency, reliability, cost, and operations post-launch.

Building a decision matrix across latency, reliability, cost, and operational capability turns architectural selection into an explainable, verifiable process. Eliminate options that break hard constraints first; only then score survivors using workload-specific weights backed by metrics, benchmarks, failure tests, and TCO. By documenting assumptions, evidence, trade-offs, and revisit triggers, an organization can choose the right compute model today while staying ready to adapt as load, business needs, or operational capabilities evolve.
