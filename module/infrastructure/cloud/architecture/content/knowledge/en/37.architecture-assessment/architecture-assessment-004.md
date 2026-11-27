# Proof of Concept for Validating High-Risk Assumptions

## 1. Why Run a PoC When Assessing Cloud Architecture?

In **CLOUD_ARCHITECTURE**, cloud application design begins with business requirements before choosing networking, compute, data, and deployment models. A plausible diagram on paper is not enough to prove an application can meet its desired reliability, security, performance, scalability, cost, and operational goals.

A **Proof of Concept (PoC)** is a scoped, time-boxed experiment designed to gather **evidence for one or a few high-uncertainty architectural assumptions**. A PoC's value lies not in building a production-looking system, but in enabling the architecture team to make a better decision: proceed, adjust, pick an alternative, or stop.

For example: a team proposes moving the API to a managed container service while keeping the transactional database in a legacy data center. The assumption that "cross-network latency is negligible" could make or break the entire plan. A PoC measuring real transaction times across the hybrid link under peak load is far more valuable than building out the new app's entire UI.

By the end of this lesson, you will be able to:

- Identify **high-impact, unproven** assumptions in a target architecture.
- Write falsifiable hypotheses, verification metrics, and clear acceptance thresholds.
- Design experiments with baselines, representative data, controlled configs, and reproducibility.
- Interpret PoC results within their actual limits, avoiding mistaking one test for production-readiness certification.
- Record architectural decisions with traceability from requirements to test data and next steps.

## 2. Distinguishing a PoC from Similar Activities

| Activity | Core Question | Priority Output | Completion Signal |
| --- | --- | --- | --- |
| Discovery / Assessment | What is the current system and what are its dependencies? | Inventory, dependency map, requirements | Critical components and information gaps identified |
| Technical spike | How does this technology work, and how is its API used? | Knowledge, small code samples, learnings | Enough understanding to estimate or choose research direction |
| **PoC** | Does this high-risk assumption hold under target conditions? | Measured data, pass/fail/inconclusive verdict | Sufficient evidence for a conditional decision |
| Prototype | Does the user experience or interaction design fit? | Mockup for discussion/user testing | Answers questions on usability and business flows |
| MVP | Does a minimal product deliver value to real users? | Controlled feature release | Feedback and business value measured |
| Pilot | Does a near-production option work in real operations? | Test results across processes, people, and systems | Passes acceptance gates to expand rollout |

A PoC may deploy a few real components, but it does not automatically need full features, HA, CI/CD, autoscaling, or production-grade release pipelines. **The attributes under test must be realistic enough for results to be meaningful.** If a PoC aims to prove failover, you cannot skip multi-zone readiness just for speed.

## 3. Selecting the Right High-Risk Assumptions

### 3.1. Start from the Decision That Needs to Be Made

Do not start with "let's try tech X to see how it feels." First identify **what architectural decision is blocked by an unknown**:

- Should we keep the database on-premises while moving the API to the cloud?
- Is the managed database compatible with current transactions, extensions, and peak load?
- Does container autoscaling scale out fast enough when traffic triples?
- Do encryption and data access meet the organization's mandatory requirements?
- Does recovery meet RTO/RPO after losing an availability zone?
- Does object storage paired with a CDN meet expected latency and data transfer costs?

Every question connects to a **business goal or non-functional requirement (NFR)**. Without knowing the impact if an assumption fails, there is no basis to prioritize it.

### 3.2. List and Rank Uncertainties

A simple scoring method can structure the discussion:

- **Impact (I):** 1 = minor, 5 = can cause a primary goal to fail.
- **Uncertainty (U):** 1 = relevant data already exists, 5 = virtually no evidence.
- **Exposure / Blast Radius (E):** 1 = affects a small slice, 5 = affects many workloads/customers.

**Exploration Priority Score = I × U × E** (from 1 to 125). This is a **qualitative ranking scale**, not a probability-of-failure formula. Legal or safety requirements may act as mandatory gates that must be resolved regardless of score.

| Assumption | I | U | E | Score | Appropriate Verification Method |
| --- | ---: | ---: | ---: | ---: | --- |
| Hybrid link is fast enough for synchronous transactions | 5 | 4 | 5 | 100 | Load PoC measuring end-to-end latency |
| Managed DB is compatible with queries/extensions | 5 | 4 | 4 | 80 | Schema migration PoC running real SQL |
| Autoscaling handles traffic spikes | 4 | 3 | 4 | 48 | Ramp-load PoC observing scale-out |
| Log format is convenient for ops to query | 2 | 2 | 2 | 8 | Spike or using existing tools |

Beyond scores, estimate the **cost to learn the answer** and **likelihood of changing the decision**. If two assumptions carry equal impact, prioritize the one faster to verify and capable of altering the chosen option. Avoid expensive PoCs to rediscover facts already established in documentation and tests closely matching your conditions.

### 3.3. Scoping the Test

A good PoC typically verifies one primary risk and its essential supporting conditions. For example, testing hybrid latency needs a realistic network link, database engine, read/write ratio, and API deployment model, without needing full admin portals or UI polish.

Use this rule of thumb: **if removing this component does not change or invalidate the conclusion, consider dropping it from the PoC.**

## 4. Writing Falsifiable Hypotheses

A vague statement like "the managed service is fast enough" does not define what counts as passing.

Follow this template:

> **Given** the described volume and architecture, **when** test condition X occurs, **then** metric Y must meet threshold Z within time T; **otherwise**, consider alternatives.

Examples:

**H1 – Performance:** At 180 requests/sec with a 70% read / 30% write mix for 20 minutes, the ordering API running on cloud containers and accessing the DB over a hybrid link achieves **p95 latency ≤ 300 ms**, **error rate < 0.5%**, and **zero dropped iterations caused by load generator resource exhaustion**.

**H2 – Recoverability:** With the planned managed DB configuration, when executing an approved failover drill, the service restores order creation within **20 minutes**, and data loss measured on successfully confirmed transactions does not exceed **5 minutes**.

**H3 – Security:** Within the defined access flows, unauthorized users cannot read transaction tables; all sensitive accesses are logged per policy, even across application restarts.

Before running, explicitly define:

| Component | Question to Answer |
| --- | --- |
| Hypothesis | Which statement could turn out false? |
| Decision | On pass/fail, how does the architecture choice change? |
| Independent variables | Load, data size, network placement, config, failure scenarios? |
| Observed variables | Latency, error rate, lag, RTO/RPO, cost, audit logs? |
| Thresholds | What defines pass, fail, or needing further tests? |
| Evidence | Which data source, timestamp, method, and result files? |
| Limitations | Which factors did the PoC omit or only simulate? |
| Decision maker | Who approves the criteria and interprets results? |

**A hypothesis must be able to fail.** If any outcome could be spun as "the technology is viable," the experiment design is not sharp enough.

## 5. Designing Controlled and Representative Experiments

### 5.1. Sketching the Causal Chain to Verify

Suppose you are verifying latency for moving the API to the cloud while keeping data on-premises:

~~~mermaid
flowchart LR
    C[Load generator] --> G[Ingress / Load balancer]
    G --> API[Cloud API]
    API --> NET[Hybrid link]
    NET --> DB[(On-prem DB)]
    API --> OBS[Logs / Metrics / Traces]
    NET --> OBS
    DB --> OBS
~~~

During testing, observe both client-side API latency and sub-components like DNS, TLS, DB connection, query execution, connection queueing, and retries. Having only the final p95 tells the team the option failed, without revealing **why**.

### 5.2. Baselines, Variants, and Controls

Maintain a **baseline** representing the existing architecture or active service level, then compare it against one or more alternatives:

| Group | API | DB | Purpose |
| --- | --- | --- | --- |
| Baseline | On-premises | On-premises | Measure current performance under equivalent load |
| A | Managed containers on cloud | On-premises via hybrid | Test network and runtime assumptions |
| B | Managed containers on cloud | Managed DB on cloud | Test eliminating cross-link network hops |

Comparisons are only meaningful when environment, data, workload, and measurement methods match. If B runs faster because it was given 4x larger instances, you cannot attribute the speedup to data architecture.

### 5.3. Data and Load Must Mirror Failure-Prone Conditions

A test model must specify:

- **Data:** volume, value distribution, indexes, hot-key ratio, foreign keys, record size, heavy-query share. Generate synthetic data matching real distributions; avoid copying sensitive data against policy.
- **Workload:** business journeys, read/write ratio, sessions, concurrent queries, batches, and background jobs.
- **Load tiers:** average, peak load, sudden spikes, sustained soak, and ramp-down.
- **Environment:** region/zone, compute tier, DB config, runtime version, subnets, DNS, connection methods.
- **Load generator placement:** aligned with target users or network paths; the load generator must never become the bottleneck.
- **Run duration:** long enough to warm caches/JIT/connection pools, reach steady state, and observe autoscaling; execute multiple runs when measuring variance.
- **Noise:** other deployment alerts, quota changes, noisy-neighbor shared services, account limits, warm vs. cold caches.

**Never extrapolate large-scale performance from tiny datasets** if the question involves indexes, partitioning, locking, compaction, or restore time. You may start small to catch early bugs, then scale up to a dataset size meaningful for the hypothesis.

### 5.4. Controlling Measurement Error

- Synchronize clocks and measure end-to-end from the client perspective.
- Report p50, p95, and p99 as appropriate; never use average latency to hide tail distributions.
- Record completed requests, failed requests, dropped requests due to generator capacity limits, and retries.
- Measure across multiple runs or windows, preserving variance and configuration metadata instead of cherry-picking the best run.
- Distinguish **client-observed response time** from internal service processing time.
- Monitor saturation of CPU, RAM, connection pools, IOPS, throughput, queue depth, and service limits.
- For cost comparison tests, control for resource differences and include all relevant billing components.

## 6. Linking PoCs to Well-Architected Pillars

A PoC need not verify every pillar simultaneously, yet the decision must state impacts and gaps across these perspectives. Pillar names and detailed guidance may vary across cloud providers.

| Perspective | Common High-Risk Assumptions | Test Types and Evidence |
| --- | --- | --- |
| **Operational excellence** | Can the team detect, deploy, and resolve incidents? | IaC deployments, rollback drills, alert tables, runbooks |
| **Security** | Do authorization and data controls work as designed? | Negative access tests, encryption checks, secrets, audit trails |
| **Reliability** | Can the system survive instance, zone, and link failures? | Scoped fault injection, failovers, backup/restore, RTO/RPO measurement |
| **Performance efficiency** | Are throughput and latency sufficient at target load? | Load tests, stress tests, scale-out, bottleneck analysis |
| **Cost optimization** | Do operating costs fit budget under realistic load? | Measure resource-hours, storage, requests, network egress, TCO forecast |
| **Sustainability** | Can resources be used efficiently? | Right-sizing, idle capacity, autoscaling, data lifecycle |

Security and compliance may include **hard gates**: strong latency numbers do not permit bypassing data residency rules or mandatory access controls.

## 7. Defining Metrics, Thresholds, and Conclusions

### 7.1. Metrics to Select per Hypothesis

| Category | Suggested Metrics | Interpretation Notes |
| --- | --- | --- |
| Performance | Throughput, p50/p95/p99 latency, timeouts, error rate | Measure from user perspective at defined load |
| Scalability | Scale-out duration, latency during spikes, queue depth, backlog | Also measure backlog drain speed post-spike |
| Data | Replication lag, record drift, reconciliation errors, transaction consistency | Low lag does not prove all transactions are correct |
| Reliability | Time to detect, empirical RTO, data loss/empirical RPO | Define incident start and recovery milestones beforehand |
| Security | Successful unauthorized access attempts, audit coverage, secrets leaked in logs | Passing negative tests means proper denial |
| Operations | Deployment time, rollback time, diagnosis time | Note remaining manual steps |
| Cost | Cost per runtime hour, per transaction, egress, backups, monitoring | Separate PoC spend from projected production spend |

**Error rate** = requests classified as errors / total requests issued in the corresponding measurement set. Define beforehand how business errors differ from infrastructure errors and how retries are counted.

**Empirical RTO** = timestamp when service again meets minimum defined criteria − incident start timestamp. **Actual data loss** must be measured using transactions confirmed successful prior to the incident versus recovered state, not merely replication settings.

**Cost per 1,000 transactions** = total cost attributed to the workload in the period / successful transactions × 1,000. Explicitly list numerator items: compute, DB, storage, data transfer, backups, monitoring, shared services, and allocation ratios. Never extrapolate production pricing from a few-minute run containing idle overhead, fixed fees, or commitment discounts.

### 7.2. Example Conclusion Criteria

| Conclusion | When to Use | Accompanying Decision |
| --- | --- | --- |
| **Passed within test scope** | All defined hypothesis criteria met with valid evidence | Proceed to pilot or detailed design, subject to other gates |
| **Failed** | One or more essential criteria failed in a valid test | Revise design or switch options; re-run only after changes |
| **Insufficient evidence** | Unrepresentative scenario, high noise, generator bottleneck, missing metrics | Collect more measurements or redesign the experiment |
| **Halted for risk** | Signals of safety, budget, or live-system impact violations | Stop test, isolate environment, and remediate risk |

Never alter thresholds after seeing results just to mark a "pass." If business goals genuinely change, record a new criteria version, rationale, and re-run the corresponding evaluation.

## 8. Process for Building and Running a PoC

~~~mermaid
flowchart TD
    A[Decision blocked by uncertainty] --> B[Prioritize high-risk assumptions]
    B --> C[Write hypotheses and thresholds]
    C --> D[Design scenarios, baseline, data]
    D --> E[Build controlled test environment]
    E --> F[Measure baseline and variants]
    F --> G{Evidence reliable?}
    G -- No --> H[Check noise / improve measurement]
    H --> F
    G -- Yes --> I{Hypothesis passed?}
    I -- Yes --> J[Recommend pilot and hard gates]
    I -- No --> K[Choose another option or revise design]
    J --> L[ADR and next-step backlog]
    K --> L
~~~

### Step 1: Lock Decision, Budget, and Timeline

Record the business sponsor, architectural decision authority, time box, and budget limit. Select a small number of critical hypotheses. Define **stop conditions**: budget overrun, impact on shared systems, security risks discovered, or enough evidence to falsify the hypothesis.

### Step 2: Prepare Test Design

Create a **test plan** with a matrix of conditions, loads, data, thresholds, and measurement methods. Pick an equivalent baseline. Pre-define reproducibility artifacts: code versions, container images, IaC configs, seed data, deployment commands, and result storage locations.

### Step 3: Build a Minimal Safe Environment

Set up a test account/project isolated from production with least privilege, encryption, secrets management, restricted networking, budget alerts, and resource owners. Use synthetic or policy-compliant sanitized data. For fault injection, confirm blast radius and immediate abort procedures.

**IaC helps** by recreating identical environments and reducing variance across runs. After the PoC, clean up infrastructure and data per policy; archive measurements, configs, and decisions for traceability.

### Step 4: Run a Smoke Test to Validate Tooling

Run light load to verify instrumentation, logs, network paths, test data, and statistical accuracy. If the load generator cannot sustain target load, fix load generation before judging the system good or bad.

### Step 5: Run Baseline and Variants

Use identical scenarios, recording timestamps, configs, versions, and anomalies. Run order can affect caches and shared loads; when possible, repeat in balanced order and distinguish cold vs. warm starts.

### Step 6: Analyze and Decide

Compare against defined thresholds, investigate causes of deviations, inspect residual risks and untested pillars. The verdict must be one of **pass, fail, or insufficient evidence**, paired with concrete next actions.

## 9. Example Performance Test Scenario Implementation

A hypothetical test using a load-generation tool could be configured as follows. This is a **conceptual template for an existing read API in a test environment**, not representative of the full read/write ordering journey.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    peak_read: {
      executor: 'constant-arrival-rate',
      rate: 180,
      timeUnit: '1s',
      duration: '20m',
      preAllocatedVUs: 150,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.005'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const url = __ENV.API_URL + '/api/orders/seeded-read';
  const response = http.get(url, {
    headers: { 'X-Test-Run': 'architecture-poc' },
  });
  check(response, {
    'HTTP 200': (r) => r.status === 200,
  });
}
~~~

Set **API_URL** to point at the test environment, ensuring the endpoint matches the application fixture without hardcoding secrets. The path **/api/orders/seeded-read** is a placeholder and must be replaced with a real read endpoint in the test system.

To verify H1 from Section 4, you must **add real write scenarios on test data** at a 70/30 ratio with representative payloads and business logic; running only the read script above is **insufficient** to conclude H1. Also capture application metrics, DB connections, network latency, and business errors. Never generate load using real user accounts or live payment transactions.

## 10. End-to-End Case Study: Choosing DB Placement When Migrating an API

### 10.1. Context

An enterprise is evaluating the target architecture for its ordering service:

- The API currently runs on VMs in an internal data center, accessing a relational database.
- The team wants to deploy the API on managed containers to reduce operational toil and ease scaling.
- Two options are under evaluation: **A** keeping the DB on-premises over a hybrid link, and **B** migrating to a managed DB in the cloud.
- Assumed requirements: peak load **180 requests/sec**, roughly **70% read / 30% write**, p95 not exceeding **300 ms**, error rate below **0.5%**. System recovery targets: **RTO ≤ 20 minutes** and **RPO ≤ 5 minutes** for the defined scenario.

These requirements are only an educational example. In real projects, thresholds must be approved by business owners according to SLOs and tolerable loss.

### 10.2. Test Design

~~~mermaid
flowchart TB
    L[Load generator with sample transactions] --> S{Option}
    S --> A[Cloud API - Option A]
    S --> B[Cloud API - Option B]
    A --> N[Hybrid connection]
    N --> D1[(On-prem DB)]
    B --> D2[(Managed cloud DB)]
    A --> O[Telemetry / Trace]
    B --> O
    D1 --> O
    D2 --> O
~~~

Use the exact same API version and transaction suite. Replicate schema and synthetic data with distributions, indexes, and sizes close to the target environment. Run at least one steady-load pass, one ramp-up pass, and one failure test targeting the primary risk. Separately document uncontrollable differences such as disk tiers, replication modes, and cache state.

**Key Hypotheses**:

- **H1:** A meets performance thresholds at 180 requests/sec.
- **H2:** B meets performance thresholds at the same load.
- **H3:** B meets RTO/RPO in a failover drill with transaction verification.
- **H4:** B satisfies access control, logging, and data residency requirements.

### 10.3. Illustrative Results (Not Real Measurements)

Suppose three runs under matching conditions yield the representative summary below:

| Metric | On-prem Baseline | A – Cloud API + On-prem DB | B – Cloud API + Managed Cloud DB | Criterion |
| --- | ---: | ---: | ---: | --- |
| p95 at 180 req/s | 210 ms | **410 ms** | **240 ms** | ≤ 300 ms |
| p99 at 180 req/s | 390 ms | 880 ms | 420 ms | Monitor trend |
| Error rate | 0.2% | 0.4% | 0.2% | Below 0.5% |
| DB failover RTO | Untested | Untested | 12 minutes | ≤ 20 minutes |
| Empirical RPO | Untested | Untested | 30 seconds | ≤ 5 minutes |
| Test-set transaction reconciliation | Match | Match | Match | No unexplained discrepancies |
| Audit / data residency requirements | Needs review | Needs review | **Insufficient evidence** | Hard gate |

**Interpretation**:

1. **H1 failed** because A's p95 exceeded the threshold. Hypothetical traces show multiple synchronous DB round-trips across the hybrid link inflating total latency; the team must confirm with query-level breakdowns rather than asserting root cause from a single p95 number.
2. **H2 passed under measured conditions**: B satisfies p95 and error rate at target load. You cannot yet conclude B handles all load profiles or all user geographies.
3. **H3 passed in one drill scenario**, yet other failure modes, larger datasets, and live operational conditions still require validation during the pilot.
4. **H4 has insufficient evidence**, so B is not ready for go-live approval until security and compliance assessments conclude.

**Conditional decision:** do not prioritize A under the current architecture; advance B into detailed design and pilot subject to hard gates, data validation results, cost checks, and operational procedures. Retain A as an option requiring redesign if the enterprise mandates keeping data on-premises—such as reducing round-trips or replacing synchronous calls with mechanisms aligned to business consistency.

### 10.4. What If Results Look "Good" Yet the Conclusion Is Still Wrong?

Suppose B runs fast because the test dataset has only 5,000 rows and a constantly warm cache, whereas production holds hundreds of millions of rows, locking queries, and end-of-day batch jobs. Then the results are unrepresentative. The sound decision is to expand the test data or narrow the conclusion to "passed on a small dataset," never assuming production will pass.

## 11. Assessing Residual Risks and Transition Gates

A PoC rarely reduces risk to zero. State clearly **what was proven, what remains unproven, and the consequences if an assumption still fails**.

| Tested Assumption | Residual Risk | Next Action | Owner |
| --- | --- | --- | --- |
| p95 good at peak load | 3× flash crowds and peak-hour batches untested | Stress tests and quota/autoscaling checks | Application + Platform lead |
| DB failover in 12 minutes | Network link loss and logical corruption untested | Additional drills and backup/restore tests | DBA + SRE |
| Test data matches | Not all extensions, collations, and edge transactions checked | Migration rehearsal on safely sanitized data | DBA + Data owner |
| Security incomplete | IAM, auditing, and residency may fall short | Threat modeling and security/compliance review | Security + Legal/Compliance |
| PoC cost acceptable | Egress, backups, parallel ops, commitments omitted | 1–3 year scenario-based TCO forecast | FinOps + Architect |

To advance to a pilot or deployment, the organization may require **gates**: assigned business owner; complete network and data docs; verified IAM, encryption, and auditing; tested restores; alerts and runbooks; costs within budget; and a data cutover/rollback or forward-fix plan. Thresholds and approval authority must match workload criticality.

## 12. Reporting PoC Results for Independent Verification

A concise report backed by evidence beats a pile of unexplained dashboard screenshots. A reusable template:

~~~yaml
poc:
  id: POC-ARCH-004
  decision: "Keep DB on-premises or migrate with API to cloud?"
  owner: "Architecture lead"
  reviewed_by: ["Application owner", "DBA", "Security", "Operations"]
  hypothesis:
    id: H1
    statement: "Option A achieves p95 <= 300 ms at 180 req/s"
    business_reason: "Meet order creation SLO during peak hours"
  scope:
    workload: "70% read / 30% write"
    data: "Synthetic data with representative distribution"
    environment: "Container cloud to database over hybrid link"
  acceptance:
    p95_ms_max: 300
    error_rate_max: 0.005
    dropped_iterations_max: 0
  evidence:
    run_id: "run-001"
    config_version: "git-sha-or-release-id"
    dashboard: "internal-evidence-link"
    raw_results: "internal-artifact-path"
  conclusion: "FAIL"
  limitation: "Hybrid link interruption not yet tested"
  decision_next: "Evaluate Option B and reduce round-trips"
~~~

The content above is a sample schema, not results from a real system. Replace paths and identifiers with actual project repositories under proper access control.

A complete report should answer:

- **Why test:** which requirement and decision were blocked?
- **What was tested:** diagram, hypothesis, conditions, data, configuration, versions.
- **How it was measured:** tools, measurement side, duration, repetitions, sample confidence.
- **What was observed:** raw metrics or evidence links, thresholds, variances, and anomalies.
- **What was concluded:** pass, fail, or inconclusive; scope of validity and unknowns.
- **What was decided:** selected/deferred options, remaining work, approvers, and re-review date.

Decisions can be recorded in an **Architecture Decision Record (ADR)**: context, options, evidence, decision, consequences, and re-review triggers. One ADR may spawn multiple PoCs; each PoC should link back to its ADR so readers understand its purpose.

## 13. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| "Build a trial just to see" with no hypothesis | No exit criteria or decision basis | Write falsifiable questions and thresholds before building |
| Overscoped PoC resembling a new product | Inflates time and cost, dilutes focus | Trim scope strictly to the risks under test |
| Demoing only the happy path on tiny data | Hides bottlenecks, transaction bugs, and outages | Use representative data, load, and edge cases |
| No baseline or changing multiple variables at once | Cannot tell what caused improvements or regressions | Keep controls and configuration logs |
| Looking at average latency, ignoring p95/p99 | Misses slow tail experiences for a subset of transactions | Record latency distributions and error rates |
| Load generator becomes saturated | Mistakes generator limits for system limits | Monitor dropped iterations and generator resources |
| Testing failover by checking VM status only | Unknown whether services, transactions, and data recovered | Measure service availability and reconcile transactions |
| Testing only performance while ignoring security | Fast options might be legally non-compliant to deploy | Enforce hard gates and compliance reviews |
| Treating PoC success as production approval | Misses ops, data, cost, and other failure modes | Progress through pilot, rehearsals, and go/no-go |
| Not archiving configs and results | Others cannot verify or reproduce findings | Save scripts, seeds, IaC, run IDs, metrics, ADRs |
| Leaving test resources running afterward | Incurs ongoing bills and data exposure risks | Assign owner, budget, TTL, and cleanup checklist |

## 14. Practice Exercise: Designing a PoC from Start to Decision

**Context:** An e-commerce platform wants to handle promotional campaigns at **4× normal traffic** using autoscaling containers and a queue. The team proposes a managed queue but does not know whether consumers can drain the backlog within 10 minutes after a traffic spike without causing duplicate order writes.

Create a **one-page PoC plan** covering:

1. The blocked architectural decision, risk if wrong, and a falsifiable hypothesis.
2. Baseline volume, peak volume, spike duration, message size, and simulated failure rate.
3. Diagram of producer – queue – consumer – database and telemetry measurement points.
4. Pass criteria for backlog, drain time, duplicate orders, error rate, and cost.
5. Three scenarios: steady load, 4× spike, and consumer crash followed by recovery.
6. Approach for synthetic data, idempotency keys, reconciliation, and retry rules.
7. Decision rules for pass, fail, or insufficient data outcomes.
8. Remaining conditions to verify before moving to pilot/production.

**Hint:** You cannot judge "backlog drains in 10 minutes" without defining spike start and end markers, producer rate, consumer rate, and what backlog level counts as drained. Never treat an empty queue as proof of zero lost or duplicate orders; reconcile unique transaction IDs against persisted DB records. If 4× passes during normal runs yet fails when one consumer stops, state the conclusion's exact limits and consider adjusting resources, batching/acks, retries, dead-letter queues, or idempotent design.

## 15. Pre-Publication Results Checklist

- [ ] Hypothesis links to a specific requirement or architectural decision.
- [ ] Pass/fail thresholds, stop conditions, and approvers are defined.
- [ ] Baseline, data, load, environment, and limitations are documented.
- [ ] Every run records version ID, config, timestamps, and raw outputs.
- [ ] Measurement tooling has sufficient capacity and major noise sources are noted.
- [ ] Evidence covers scenarios capable of disproving the high-risk assumption.
- [ ] Security, reliability, operations, cost, and scalability impacts are reviewed.
- [ ] Conclusions do not overreach beyond what was actually tested.
- [ ] Residual risks, hard gates, and next actions have assigned owners.
- [ ] Decisions are recorded in an ADR or architecture assessment log.

**Core principle:** the best PoC is not the one that "always succeeds," but the one that **meaningfully reduces uncertainty** before the organization commits heavy cost and risk. In cloud architecture, an evidence-backed conclusion that "this assumption is false" is still valuable: it lets you fix the design while changes are still cheap and safe.
