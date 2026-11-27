# Fault-Tolerance Testing with Azure Chaos Studio

## 1. Why Inject Failures Proactively?

An application running on Azure can pass functional and performance tests yet still go down when a virtual machine, process, network path, or dependent service fails. Those failures often surface only under production conditions—when the system faces load, concurrency, and cross-component dependencies.

**Chaos engineering** is the practice of introducing a **controlled** fault into a system, observing real behavior, and testing a hypothesis about fault tolerance. The goal is not breaking as much as possible, but uncovering weaknesses while the blast radius remains small and manageable.

**Azure Chaos Studio** is an Azure service for defining and running *chaos experiments* against supported resource types and *faults*. An experiment can simulate stopping a virtual machine or another fault in the service's fault library, letting operations compare application metrics against predefined acceptance criteria.

In an Azure architecture spanning subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and databases, resilience does not come merely from adding replicas. It also depends on health probes, traffic routing, retries, timeouts, permissions, data consistency, alerts, and recovery runbooks. Chaos Studio helps **verify** those mechanisms empirically.

After this lesson, you will be able to:

- Distinguish chaos engineering, load testing, disaster recovery drills, and functional testing.
- Explain Chaos Studio components: experiment, target, capability, fault, step, branch, and managed identity.
- Define steady state, hypotheses, blast radius, and safe abort conditions.
- Design and run an experiment stopping a test VM in a redundant setup, measuring results with Azure Monitor / Application Insights.
- Analyze outcomes against SLIs/SLOs, detection time, recovery time, and RTO/RPO boundaries.
- Establish a controlled progression from lab to staging and production.

## 2. What Does Chaos Engineering Test?

A **fault-tolerance hypothesis** must be falsifiable with metrics. For example:

> When one of two API VMs stops, Azure Load Balancer removes the unhealthy VM from rotation, and at least 99.5% of valid read requests still succeed during the test window.

This hypothesis beats "the system has high availability" because it states the fault, conditions, and measurable outcome. If traffic is too low, telemetry is missing, or the success rate misses target, you cannot conclude the system tolerates faults as expected.

| Testing type | Question it answers | Key difference |
| --- | --- | --- |
| Unit / integration test | Do functions, APIs, and integrated components return right results? | Primarily tests logic under predictable conditions |
| Load / performance test | How much load can the app handle, and how does latency scale? | Focuses on throughput and capacity |
| **Chaos experiment** | When a dependency or component fails, does the live service still meet objectives? | Intentionally injects faults and observes end-to-end reaction |
| Backup / restore test | Can data actually be recovered from backups? | Verifies data, recovery points, and restore procedures |
| DR exercise | During a major disaster, are RTO/RPO and business recovery met? | Evaluates the whole recovery plan, often multi-step and multi-team |
| Penetration test | Can security vulnerabilities be exploited? | Evaluates security, distinct from reliability faults |

Testing disciplines **complement one another**. Chaos Studio alone does not prove data durability, fully assess security, or replace cross-region DR drills.

### 2.1 Experimentation Loop

~~~mermaid
flowchart TD
    A["Observe steady state"] --> B["State hypothesis and SLIs"]
    B --> C["Select one fault, target, and blast radius"]
    C --> D["Set up monitoring and abort conditions"]
    D --> E["Run experiment"]
    E --> F["Measure during fault and post-recovery"]
    F --> G{"Criteria met?"}
    G -->|No| H["Fix architecture, config, or runbook"]
    G -->|Yes| I["Record evidence, expand cautiously"]
    H --> A
    I --> A
~~~

A good experiment produces **evidence**: when the fault started, affected resources, application signals, detection latency, recovery speed, abort decisions, and final verdict.

## 3. Concepts in Azure Chaos Studio

| Component | Role | Things to watch |
| --- | --- | --- |
| **Experiment** | Azure resource describing the test scenario and fault schedule | Has identity, config, permissions, steps, and run history; creating an experiment does not run it |
| **Target** | Resource or entity onboarded to Chaos Studio targeting | Must be explicitly enabled; verify exact resource ID and environment |
| **Capability** | Enables applying a specific fault type to a target | Enable only faults you intend to test, per supported capability list |
| **Fault** | Fault action such as stopping a VM or simulating network issues where supported | Each fault has distinct parameters, limits, impact, and prerequisites |
| **Step** | A stage inside an experiment | Multiple stages can be sequenced |
| **Branch** | An execution path within a step | Branches can run in parallel; control cumulative blast radius |
| **Action** | Operation inside a branch, e.g., a fault with specific parameters | Duration and post-completion behavior depend on the fault |
| **Managed identity / RBAC** | Grants the experiment authority to act on target resources | Needs scoped permissions; same subscription does not grant access automatically |

Portal labels and options evolve with service updates. Supported fault libraries, SKUs/regions, and per-target prerequisites also change. **Choose only faults shown as compatible with your exact resource after checking current support conditions and service docs.**

### 3.1 Service-Direct Faults vs. Agent-Based Faults

Chaos Studio uses two main fault-injection models:

**Service-direct**: Chaos Studio interacts with the target Azure service's control plane / API. A suitable learning example is simulating stopping an Azure VM when that fault is supported by the current library and setup. No Chaos Studio guest agent is needed for a service-direct fault; grant appropriate resource-control RBAC instead.

**Agent-based**: an agent or helper running alongside the target system executes faults inside the runtime environment, such as CPU, memory, network, or process pressures on supported platforms. You must install/register the agent, enable the right capability, and satisfy OS, networking, permission, and fault-duration requirements. Never assume every fault runs on every VM type, AKS cluster, or App Service.

| Criterion | Service-direct | Agent-based |
| --- | --- | --- |
| Injection point | Controls resources via supported Azure service APIs | Inside a host/workload running a supported agent |
| Prerequisites | Target, capability, identity, and RBAC | Above requirements plus agent/extension and runtime permissions |
| Conceptual example | Stopping one VM in a backend pool | Injecting network latency on a supported workload |
| Easy-to-miss detail | API actions alter real resource state and may need explicit recovery | Agent disconnects, fault fails to run, or rollback behavior depends on fault |

**Never confuse "experiment Completed" with "service recovered."** Workflow completion only indicates the engine finished running; inspect individual action states, logs, and SLIs to evaluate business success. Some faults require restarts, config restoration, or manual recovery after the experiment ends.

## 4. Preparing a Scenario on a Hypothetical System

We use a read-only order API in a **lab** environment:

- Two Azure VMs running the same API version inside an Azure Standard Load Balancer backend pool.
- Load-balancing rules and health probes configured on the right port and readiness path.
- A synthetic load generator **outside the backend pool** sending non-mutating GET requests.
- Azure Monitor and Application Insights collecting request success, duration, dependency failures, and availability tests.
- Operations holding permissions to read metrics/logs, run experiments against **one** chosen VM, and recover that VM.

~~~mermaid
flowchart LR
    G["Load generator / synthetic client"] --> LB["Azure Load Balancer"]
    LB --> VM1["VM-A: API"]
    LB --> VM2["VM-B: API"]
    VM1 --> DB["Data service (serving reads)"]
    VM2 --> DB
    VM1 --> MON["Application Insights"]
    VM2 --> MON
    CS["Chaos Studio"] -. "Fault on VM-A" .-> VM1
~~~

This assumes the data tier, database, and access path remain healthy. This experiment measures **single-VM** fault tolerance—not loss of an availability zone, region, or database. If the API relies on one unredundant database, passing a VM-stop test does not mean the system survives database failures.

### 4.1 Setting Criteria Before Running

Example targets chosen **strictly for this lab**, not Azure product SLAs:

| Metric | Pre-fault (baseline) | During and after fault | Pass criterion |
| --- | --- | --- | --- |
| Good request rate | Sufficient samples, steady near 100% | Observe per minute, including transient errors | Total good rate ≥ **99.5%** across fault + recovery window |
| p95 latency | e.g., under 200 ms | May rise when one VM drops | Steady-state p95 after traffic shift ≤ **500 ms** |
| Health probe | Both VM-A and VM-B healthy | VM-A evicted, VM-B stays healthy | Requests stop hitting VM-A once probe marks it unhealthy |
| Incident detection | Alerts active | Detects VM-A stop or SLI drop | Alert fires in **≤ 2 minutes** if telemetry interval supports |
| Recovery time | API responding normally | From fault impact until good requests stabilize | **≤ 3 minutes** for single-VM fault |
| Data integrity | Consistent test data present | Zero writes/edits during GET test | Zero test-induced data mutations |

Define **good request**: a valid GET request returning accurate data within acceptable latency. Exclude health probes from user traffic. Checking HTTP 200 alone without verifying payload correctness is unreliable.

Ensure enough traffic to observe: with only 20 requests during a test, **one error** drops success rate to 95% with huge variance. Choose duration and RPS carefully and document sample size upfront.

## 5. Designing Scope and Safe Abort Conditions

Chaos experiments can cause real disruption. Before onboarding targets or starting an experiment:

1. **Scope**: target only lab VM-A in the exact subscription, resource group, and region. Never select the wrong backend pool, VM-B, or a production resource group.
2. **Time bound**: keep faults brief—for instance, 2 minutes—within the chosen fault's supported settings. Timings are examples; valid bounds depend on capability.
3. **Abort conditions**: if good request rate stays below 98% for 2 straight minutes, both backends fail, data errors appear, or unexpected critical alerts fire, abort and execute the recovery runbook.
4. **Accountable operators**: designate someone watching dashboards, someone authorized to stop the experiment, and someone authorized to restart/recover the VM.
5. **Recoverability**: know upfront whether the fault self-reverts, how to restart, how health checks behave, and how to offboard targets/capabilities if needed.
6. **Test data**: safe read requests—never real customer data, live orders, or real payments.
7. **External dependencies**: coordinate with DB, network, and monitoring owners as needed; avoid maintenance windows.

**A team's abort criteria do not automatically become an SLI-driven kill switch inside Chaos Studio.** Unless automated monitoring gates are wired in, on-call staff must watch actively and trigger stops manually. Moreover, **stopping an experiment does not guarantee every effect reverts instantaneously**.

A review-friendly experiment spec:

~~~yaml
# Experiment test plan specification for team review.
# Illustrative YAML document ONLY, NOT a deployable Azure Chaos Studio schema.
experiment_id: lab-single-vm-failure
business_journey: "GET /orders/{id}"
scope: "rg-chaos-lab, VM-A only"
hypothesis: "LB removes unhealthy VM-A; service continues on VM-B"
fault:
  category: service-direct
  effect: "stop VM-A (only if supported capability is enabled)"
  planned_duration: "2 minutes"
traffic:
  source: "external synthetic client"
  load: "known constant rate; record request count"
success_conditions:
  success_rate: ">= 99.5% over fault + recovery window"
  recovery: "<= 3 minutes for this scenario"
abort_conditions:
  - "Both backends unhealthy"
  - "Success rate < 98% for 2 continuous minutes"
  - "Any unexpected data integrity impact"
cleanup:
  - "Ensure VM-A running"
  - "Verify both backends healthy"
  - "Compare SLI and publish evidence"
~~~

Never submit this planning file directly to the Chaos Studio REST API. Use it to review the hypothesis before entering fields in the Portal or authoring an experiment in the supported resource schema.

## 6. Preparing Azure Chaos Studio

### 6.1 Checking Subscription, Region, and Support Matrix

Administrators verify the target VM and Chaos Studio support the desired region, fault, OS/SKU, and trigger mechanism. Support evolves over time; check the current Azure Chaos Studio **fault library and prerequisites** for the exact resource.

These Azure CLI commands are **read-only** checks on subscription and resource provider registration:

~~~bash
az account show --query "{subscription:id,name:name,tenantId:tenantId}" -o table
az provider show --namespace Microsoft.Chaos \
  --query "{namespace:namespace,registrationState:registrationState}" -o table
~~~

If the provider is unregistered, an authorized admin can run:

~~~bash
# Administrative action: registers the resource provider on the real subscription.
az provider register --namespace Microsoft.Chaos
~~~

The `register` command **modifies subscription configuration**; it is not a fault, yet still requires appropriate admin rights. Also review Azure Policy, resource locks, quotas, and networking that could affect experiments or agents.

### 6.2 Onboarding Targets and Capabilities

In the Azure Portal:

1. Open **Azure Chaos Studio** and go to **Targets** (blade names may vary).
2. Select the exact lab VM-A; verify resource ID, subscription, resource group, and region.
3. Enable the matching target type. For this lab, pick **service-direct target** if VM shutdown faults are supported.
4. Enable only the **capability** for the specific fault under test. Avoid enabling unused faults.
5. Confirm target/capability readiness and double-check scope before creating an experiment.

Enabling a target merely allows Chaos Studio to address that resource; **it does not inject faults automatically**. For advanced agent-based faults, also install agents/extensions and verify connectivity per target requirements.

### 6.3 Experiment Identity and Permissions

Experiments need an identity and permissions to inject faults on target resources. Best practices:

- Use a Chaos Studio-supported **managed identity** for the experiment instead of embedding client secrets in docs or code.
- Grant **least-privilege roles/permissions** matching the exact fault and resource scope. Stopping a VM requires VM control permissions; Azure Monitor read access is insufficient.
- Whether using built-in or custom roles, verify required actions against the fault's current documentation.
- Restrict who can edit experiments, enable capabilities, assign roles, and start runs. Dashboard viewers should not automatically be allowed to inject faults.
- Verify role propagation after creating the identity, as RBAC assignments can take time to take effect.

Never grant subscription-wide permissions when an experiment only targets one lab VM. Keep an approval record and clear attribution for who starts every run.

## 7. Creating and Running a Single-VM Stop Experiment

### 7.1 Creating the Experiment in Azure Portal

General workflow:

1. In Azure Chaos Studio, open **Experiments** and create a new experiment in the lab resource group with a traceable name like `exp-lab-vm-single-failure`.
2. Assign the experiment's supported identity and grant permissions on VM-A.
3. In the designer, add **one step** with **one branch**, and add **one fault action** for the supported VM shutdown/stop fault.
4. Select **VM-A** as target, the exact capability, and a short valid duration. Note in docs whether the fault auto-recovers or requires a manual start.
5. Review the summary: experiment and target belong to the right subscription, excluding VM-B and production resources.
6. Save the experiment. Saving is distinct from clicking **Start**.

Some UIs allow multiple branches and combined faults. On your first run, **use one fault only** so results stay clear and blast radius stays minimal.

### 7.2 Establishing a Baseline

Before clicking Start:

- Confirm **both VMs are healthy** on the Load Balancer and probes.
- Measure from at least one location outside the backend pool: GET endpoint, success rate, latency, and response payload.
- Generate steady load with an approved tool like Azure Load Testing or a load generator; do not confuse a chaos experiment with a load generator.
- Open Azure Monitor / Application Insights dashboards, health probes, VM metrics, and dependency views, and verify alerts route to the right on-call person.
- Capture T-10 to T0 (e.g., 10-minute baseline), UTC timestamps, API commit/release version, and LB settings.

If the baseline already shows errors or missing telemetry, **do not run "just to see"**: fix measurement conditions first so background noise is not mistaken for fault impact.

### 7.3 Executing and Observing

1. On-call confirms readiness and signs off on scope and abort criteria.
2. Start the experiment and record **T0 = when the fault actually begins taking effect**, separate from clicking Start.
3. Watch action status, VM-A state, health probes, VM-B traffic, successful requests, and synthetic-client latency.
4. If an abort condition triggers, cancel the experiment and execute the recovery runbook; never rely entirely on fault auto-rollback.
5. When the fault duration ends, verify **VM-A is actually Running**, the app process is up, and LB probes mark it healthy again. Recover manually if that fault requires it.
6. Keep observing post-fault to catch lingering errors, queue backlogs, leaked connections, or a stuck backend.

Mark PASS only when the **user-experience hypothesis** is backed by sufficient telemetry; successful experiment execution is only part of the evidence.

### 7.4 Statuses to Distinguish

| Observation | Meaning | Sufficient to declare PASS? |
| --- | --- | --- |
| Experiment status is Completed | Engine finished running the workflow | No |
| Fault action reports success | Fault mechanism triggered | Not yet |
| VM-A observed stopped | Proves fault hit the intended target | Not yet |
| VM-B receives and handles requests | LB has a working backup path | Not yet; measure SLIs and correctness |
| SLI, latency, and recovery meet thresholds | System satisfied hypothesis | Conditionally, if sample size, telemetry, and cleanup are valid |
| VM-A restarted and healthy | Lab environment returned to normal state | Mandatory to close cleanup |

## 8. Measuring Results with Azure Monitor and Application Insights

Azure Monitor provides metrics, logs, alert rules, and workbooks. Application Insights captures requests, dependencies, exceptions, and distributed traces depending on integration. For **workspace-based Application Insights**, request telemetry usually lives in `AppRequests` inside Log Analytics; verify your actual schema.

### 8.1 KQL: Per-Minute Success Rate and Latency

Example querying a hypothetical API with `AppRoleName == "orders-read-api"` over the last 60 minutes:

~~~kusto
let observationWindow = 60m;
AppRequests
| where TimeGenerated >= ago(observationWindow)
| where AppRoleName == "orders-read-api"
| where Name contains "/orders"
| where Name !contains "/health"
| summarize
    Eligible = sum(ItemCount),
    Good = sumif(ItemCount, Success == true),
    P95LatencyMs = percentile(DurationMs, 95)
  by bin(TimeGenerated, 1m)
| extend
    SuccessRatePct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(Good) / todouble(Eligible)
    )
| project TimeGenerated, Eligible, Good, SuccessRatePct, P95LatencyMs
| order by TimeGenerated asc
~~~

**How to interpret:**

- `Eligible` estimates request volume from `ItemCount` when sampling is active; understand sampling rules before making SLO decisions.
- `Success` depends on instrumentation. For order GETs, legitimate 404s or wrong business payloads must follow your explicit SLI rules.
- `P95LatencyMs` computes across observed rows; sampling or uneven load can skew percentiles. Cross-check with edge metrics or unsampled telemetry where needed.
- Route filtering is illustrative; `Name` in real apps may normalize routes differently.
- **Zero requests** does not mean 100% success. If logs drop during a VM outage, cross-check load-generator logs and LB metrics.

To compare pre/during/post periods, align on exact UTC timestamps from experiment/fault logs:

~~~text
13:50 - 14:00  Baseline: no fault injected
14:00 - 14:02  VM-A under fault impact
14:02 - 14:07  Recovery and steady-state observation
~~~

Adjust query time filters to match those exact intervals rather than using the Start button click time.

### 8.2 KQL: Did Dependency Failures Spike?

If the application emits dependency telemetry:

~~~kusto
AppDependencies
| where TimeGenerated >= ago(60m)
| where AppRoleName == "orders-read-api"
| summarize
    Calls = sum(ItemCount),
    FailedCalls = sumif(ItemCount, Success == false)
  by Target, bin(TimeGenerated, 1m)
| extend
    DependencyFailurePct = iff(
        Calls == 0,
        real(null),
        100.0 * todouble(FailedCalls) / todouble(Calls)
    )
| order by TimeGenerated asc
~~~

Inspecting dependencies exposes issues hidden behind HTTP success rates: surging retries, exhausted DB connection pools, timeouts, or downstream errors. Use distributed tracing/correlation to see which dependencies impacted user requests.

### 8.3 Evidence Beyond KQL

| Source | What to record |
| --- | --- |
| Chaos Studio experiment run | Timestamps, action statuses, fault/target, errors, operator |
| Azure VM metrics / Activity Log | Exact time VM-A was impacted, power state, control actions |
| Load Balancer metrics / health probes | Backend healthy/unhealthy transitions and traffic shift |
| Azure Monitor / Application Insights | Request SLIs, latency, exceptions, dependencies, traces |
| Load generator / synthetic client | Sent requests, timeouts, HTTP codes, response correctness |
| Alerting / incident record | Detection time, on-call paging, response, abort decisions |
| Runbook cleanup | Time VM-A returned healthy, post-test verification |

**A test can be technically valid yet unmeasurable** if it lacked a baseline, lacked traffic, dropped telemetry, or failed to inject the fault. Mark such runs **INCONCLUSIVE**, never PASS.

## 9. Scoring Results: PASS, FAIL, or INCONCLUSIVE?

Illustrative hypothetical results (not real Azure data):

| Criterion | Observed | Target threshold | Verdict |
| --- | --- | --- | --- |
| Fault hit VM-A | Yes; VM-B stayed healthy | Only VM-A impacted | PASS |
| Good request rate during fault + recovery | 99.2% | ≥ 99.5% | **FAIL** |
| p95 after LB completed traffic shift | 420 ms | ≤ 500 ms | PASS |
| Incident detection | 75 seconds | ≤ 2 minutes | PASS |
| Steady experience recovery | 3 minutes 20 seconds | ≤ 3 minutes | **FAIL** |
| VM-A cleanup | VM running again, backends healthy | Must be verified | PASS |

Overall verdict is **FAIL for the reliability hypothesis**, even though the experiment executed cleanly. Investigate root causes:

1. Did health probes take too long to mark VM-A unhealthy?
2. Did VM-B have enough CPU, memory, DB connections, and concurrency limits for full load?
3. Did bad client retries, overly short timeouts, or non-idempotency amplify errors?
4. Did connection pools, session state, or sticky sessions pin users to VM-A?
5. Did the traffic generator or instrumentation glitch and skew measurements?

After fixing configuration or architecture, re-run **the exact versioned experiment** under identical SLIs and load. Never loosen thresholds after seeing a failure just to force a PASS.

### 9.1 Measuring Recovery Time for a Single-VM Fault

Define milestones:

- T0: fault begins affecting VM-A or requests.
- T1: Azure Monitor fires alert or on-call detects the error.
- T2: LB evicts VM-A and good request rate returns to target.
- T3: VM-A restarts and both backends return healthy.

In this lab, the goal may be **T2 − T0 ≤ 3 minutes**. T3 can occur later while one VM recovers, yet must still be checked to close cleanup. Separating T2 from T3 avoids confusing **user-facing functional recovery** with **full redundancy restoration**.

## 10. Connecting to SLI/SLO and RTO/RPO

Chaos experiment measurements must link back to business goals:

**SLI/SLO** measures service quality over a defined window. A 99.9% good-request SLO over rolling 28 days budgets 0.1% bad requests. Running chaos tests consumes error budget—especially under high load or in production.

~~~text
ErrorBudgetRequests = EligibleRequests × (1 − SLOTarget)
BudgetConsumed      = BadRequestsDuringWindow / ErrorBudgetRequests
~~~

With 500,000 eligible requests in the window and a 99.9% SLO, the budget is 500 bad requests. A chaos experiment causing 120 bad requests consumes 24% of that window's budget in this hypothetical example; any real incidents shrink remaining margin further. Never exclude chaos-induced errors from SLO reporting unless that exclusion was pre-approved and documented publicly.

**RTO** bounds recovery time after a disruption scenario. The VM-A experiment measures recovery for **single-VM loss**, not regional or database outages.

**RPO** bounds time-based data loss. Stopping a stateless API VM **cannot measure RPO for Azure SQL or storage**. To prove RPO, design a data-layer scenario, capture consistent commit markers, execute approved backup/restore or failover, and reconcile transactions.

| Target | Result from VM-A test | What remains unverified |
| --- | --- | --- |
| SLI/SLO | Measured success, latency, errors during/after fault | Longer windows, diverse faults, real user traffic |
| Single-VM RTO | Measured T2 − T0 until API stabilized | Peak load, multi-VM loss, network/dependency faults |
| Region-loss RTO | Unverified | Cross-region DR orchestration, DNS/routing, DB, identity |
| Data RPO | Unverified | Replication lag, backups/PITR, consistency, reconciliation |

Chaos engineering produces evidence for **one scoped hypothesis**. Never extrapolate "survives one VM failure" into "survives every disaster."

## 11. Advanced Scenario: Injecting Dependency Latency

Once service-direct VM tests run safely with strong observability, consider an agent-based **network latency** fault **if the target, agent, OS, and fault are supported by Chaos Studio**.

Example hypothesis:

> When connection latency from one backend to a dependency increases by 300 ms for 2 minutes, the API fails cleanly within timeouts without hanging requests indefinitely or exhausting connection pools; read-path p95 stays below the defined threshold after stabilization.

Design steps:

1. Target a single backend or narrow traffic slice. Never inject network faults across an entire cluster before running small tests.
2. Configure HTTP client and dependency **timeouts**, bounded retries with exponential backoff/jitter, circuit breakers where suitable, and idempotency for writes.
3. Keep health/readiness probes decoupled from deep checks that would mark every node unhealthy on a brief dependency slowdown.
4. Onboard the supported agent-based target/capability; carefully review agent installation, connectivity, and host/container impact.
5. Track request duration, dependency duration, retry counts, connections, and queues—not just CPU.
6. Run a short fault, monitor abort triggers, and confirm zero lingering traffic shaping/latency after completion.

**Never use infinite retries** to mask faults. If all backends retry simultaneously, the system amplifies failures via a *retry storm*. Chaos tests should prove retry caps and timeouts protect overall stability.

Another valuable test is simulating a slowed or unreachable data-path component using only supported faults and an explicit data-recovery plan. Faults risking data loss or broad access outages demand far stricter review than stopping one lab VM.

## 12. Integrating Chaos Testing into Operations

### 12.1 Expanding Scope in Stages

A practical rollout path:

| Stage | Environment | Test scope | Gate to advance |
| --- | --- | --- | --- |
| 1 | Isolated lab | Single VM, single fault, synthetic load | Fault verified real; telemetry, cleanup, and runbook pass |
| 2 | Production-like staging | Single instance, supported network or dependency fault | Architecture, config, and monitoring match closely; hypothesis passes |
| 3 | Constrained production | Single instance/canary slice, approved window, on-call present | Error budget healthy, tiny blast radius, active kill switch/runbook |
| 4 | Scheduled broader scenarios | Diverse fault types executed controllably one wave at a time | Proven stability and post-run reviews; no reckless parallel chaos |

Every stage needs abort triggers, owners, scoped permissions, and proven recovery. If a lab fault reveals a single point of failure, **fix and re-verify** before considering production testing.

### 12.2 Integrating with IaC and CI/CD

Manage experiment definitions with Infrastructure as Code (ARM/Bicep or supported APIs) for peer review and traceability; verify current resource schemas, API versions, and fault parameters. Never copy an old fault template into production without checking target resource IDs and RBAC.

An operational pipeline might follow:

~~~mermaid
flowchart LR
    A["Deploy test build"] --> B["Smoke test + baseline"]
    B --> C{"Pre-run gates met?"}
    C -->|No| D["Halt pipeline"]
    C -->|Yes| E["Approve chaos test"]
    E --> F["Run Chaos Studio experiment"]
    F --> G["Collect metrics + verify cleanup"]
    G --> H{"SLI and recovery met?"}
    H -->|No| I["Open issue + remediate"]
    H -->|Yes| J["Publish report + proceed release"]
~~~

Automation can invoke experiments via supported APIs/SDKs. **Distinguish "triggered start" from "finished and verified"**: a successful start API call does not prove the fault hit the target, the app recovered, or SLIs passed.

For release gates, collect:

- Final status of the experiment **and every fault action**.
- Evidence the fault hit the exact target within scope.
- Confirmation that the observation window had adequate samples/traffic and zero telemetry gaps.
- Explicit SLI, latency, and recovery checks evaluated by code or a designated approver.
- Completed cleanup with zero leftover faults or broken resources.

**Enforce least privilege and branch protection**: never let untrusted pull requests access credentials or managed identities capable of running Chaos Studio against production.

### 12.3 Post-Experiment Report

Include:

| Field | Example |
| --- | --- |
| Hypothesis | With one VM down, API maintains ≥ 99.5% good requests |
| Experiment version | `exp-lab-vm-single-failure`, commit/config version |
| Scope | Subscription, resource group, VM resource ID, region |
| Fault | Type, parameters, duration, capability |
| Timeline | T0 fault; T1 alert; T2 app stabilized; T3 cleanup |
| Observations | SLIs, p95, probes, request count, dependencies, action logs |
| Verdict | PASS / FAIL / INCONCLUSIVE with rationale |
| Remediation | Issue, owner, due date, architecture/runbook updates |
| Re-test | Conditions and scheduled date for re-running fixed setup |

Store reports with restricted access; they often contain resource IDs, network layouts, and failure triggers. Never include tokens, secrets, or customer data in reports.

## 13. Common Issues When Using Chaos Studio

| Symptom | Possible causes | Resolution |
| --- | --- | --- |
| Cannot find desired target or fault | Unsupported resource type, region, fault, agent, or prerequisites | Check current fault library and support matrix; adjust fault or scope |
| Experiment fails to affect VM | Capability disabled, missing RBAC, wrong resource ID, blocking policy/lock | Check target/capability, managed identity, RBAC, and activity logs |
| Agent-based fault fails to run | Agent unready, connectivity/extension issue, or missing permissions | Inspect agent health and platform prerequisites |
| Experiment finishes yet app stays broken | Fault needs manual recovery, app needs restart, LB probe or dependency stuck | Follow runbook; monitor app until healthy |
| No errors observed when stopping VM | Fault missed target, zero traffic, viewed only VM-B metrics, or redundancy worked | Verify fault action, target ID, traffic, and hypothesis evidence |
| Good request rate low even at baseline | Unstable app beforehand or missing traffic/telemetry | Stop scoring; stabilize baseline and re-measure |
| Confusing measurement glitches with app bugs | Sampling, telemetry filters, dropped logs, clock skew | Cross-check synthetic client, ingress, experiment logs, and UTC timestamps |
| VM-A never rejoins pool post-test | VM not Running, readiness failing, network/probe misconfigured | Check each layer and cleanup; never close test while redundancy remains degraded |

Additional reminder: **Chaos Studio does not enforce business safety guardrails automatically.** Deciding when to run, who has authority, what approvals apply, and when to abort remains the organization's responsibility.

## 14. Exercises and Self-Check Questions

### Exercise 1: Write a Measurable Hypothesis

A system runs two VMs behind Azure Load Balancer. The team says: "If one VM fails, the system will be fine."

Rewrite this into a testable hypothesis specifying fault, target, SLI, pass thresholds, observation window, and abort conditions.

**Reference solution:** "When lab VM-A is stopped for 2 minutes via a supported fault, at least 99.5% of valid `GET /orders` requests during the fault + recovery window succeed, post-shift p95 latency stays ≤ 500 ms, and request success stabilizes within ≤ 3 minutes; abort immediately if both backends turn unhealthy or success rate stays under 98% for 2 straight minutes." Thresholds are hypothetical and should be calibrated to baseline and business impact.

### Exercise 2: Score Results and Decide Next Steps

Over a 5-minute experiment, the client sends **10,000 valid GET requests**. **9,930 good requests** succeed, post-shift p95 latency is 450 ms, and steady recovery takes 2 minutes 45 seconds. Thresholds: good rate ≥ 99.5%, p95 ≤ 500 ms, recovery ≤ 3 minutes.

Calculation:

\[
\mathrm{SuccessRate}=\frac{9\,930}{10\,000}\times100\%=99.3\%.
\]

**Verdict:** FAIL because 99.3% falls short of 99.5%, even though latency and recovery duration passed. Investigate LB probe detection speed, VM-B capacity, and retries/timeouts before re-testing. Never rationalize a pass by cherry-picking the two passing metrics.

### Exercise 3: Verification Scope

Suppose the VM-A experiment passes all thresholds. The team plans to write in its report: "The application meets a 30-minute RTO and RPO=0 for a full-region outage."

**Evaluation:** Invalid conclusion. The test affected only one VM in one region and never measured data recovery. Proving regional RTO/RPO requires a dedicated DR scenario covering compute, data stores, replication, networking, identities, access routing, consistent checkpoints, and transaction reconciliation.

### Self-Check Questions

1. Why must you define SLIs and a baseline before injecting a fault?
2. What is the main difference between service-direct and agent-based faults?
3. What roles do target, capability, and managed identity play in a Chaos Studio experiment?
4. Why is an experiment's `Completed` status insufficient to declare PASS?
5. When stopping one VM behind a Load Balancer, what must you observe besides VM state?
6. Why does stopping an experiment not guarantee every fault automatically reverts?
7. Why does a single-VM failure test not prove regional-outage RTO/RPO?
8. What prerequisites must be met before expanding from lab to production?

**Target outcome:** You can turn a vague claim like "our Azure app is redundant" into a **measurable fault-tolerance hypothesis**, use Azure Chaos Studio to inject faults on the exact target, evaluate against SLIs/SLOs, and restore the system safely. Chaos engineering's value comes from measured evidence, lessons learned, and architectural improvements after every experiment.
