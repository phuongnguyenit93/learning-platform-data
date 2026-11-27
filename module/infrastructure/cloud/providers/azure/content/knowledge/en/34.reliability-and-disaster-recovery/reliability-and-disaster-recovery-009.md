# Failover and Failback Runbooks and Recovery Orchestration

## Lesson Objectives

In the **Reliability and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_AZURE** track, we move from provisioning standby infrastructure to **running a controlled recovery**. Azure provides subscriptions, resource groups, Microsoft Entra ID, virtual networks, VMs, storage, and data services; however, individual VMs booting successfully does not mean the application is operational again. You need a runbook defining decision authority, recovery order, traffic-cutover gates, and how to return to the primary environment.

After this lesson, you will be able to:

- Distinguish failover, failback, test failover, planned/unplanned failover, and re-protect.
- Design a runbook with clear owners, trigger conditions, gates, evidence, and fallback actions when checks fail.
- Use **Azure Site Recovery (ASR)** and **Recovery Plans** to orchestrate VM recovery according to application dependencies.
- Validate data, security, connectivity, services, and user experience before routing live traffic.
- Plan failback, run drills, and measure actual RTO/RPO.

## 1. Runbooks and Foundational Concepts

A **Disaster Recovery Runbook** is an executable operational playbook used when the primary region or a critical dependency chain fails. It answers six questions: **when to trigger, who decides, what to do in what order, how to verify, when to stop, and how to return to steady state**.

| Concept | Meaning | Key reminder |
| --- | --- | --- |
| **Failover** | Shifting workloads to a standby region/system | Complete only when business flows serve, not merely when VMs boot |
| **Planned failover** | Proactive cutover while primary remains reachable for coordinated sync | Can minimize data loss, yet still requires full verification |
| **Unplanned failover** | Cutover when primary is unreachable or cannot wait | May lose writes not yet captured in a recovery point |
| **Test failover** | Drill launching the DR environment without shifting production traffic | Use an isolated network and clean up afterward |
| **Failback** | Returning from DR to primary once recovered | Must preserve new data created in DR |
| **Re-protect** | Re-establishing replication direction after a region switch | After failover, reverse replication is needed; after failback, restore DR protection |

**Azure Backup** stores recovery points and supports restores, whereas **Azure Site Recovery** protects supported workloads via replication and failover orchestration. They complement each other. Replication does not replace backups: accidental deletions, buggy writes, or corrupted data replicate too.

Two targets to document before designing:

- **RPO (Recovery Point Objective)**: maximum acceptable data loss, expressed as the time gap between recoverable data and the incident timestamp.
- **RTO (Recovery Time Objective)**: maximum allowed time from incident start until essential business functions operate again—including detection, decision, recovery, validation, and traffic switching.

These are business targets, **not automatic guarantees** from turning on ASR. Measure them in drills and real incidents.

## 2. Example Two-Region Architecture

Suppose an ordering application operates across:

- **Region A (primary)**: API VMs, frontend VMs, database VMs, private networking, load balancers, and dependencies.
- **Region B (DR)**: pre-built VNet/subnets, NSGs, routes, compute quotas, and network configuration; ASR-protected VMs can recover here.
- **Recovery Services vault**: manages replication and the ASR Recovery Plan.
- **Azure Front Door** or **Azure Traffic Manager**: redirects user access according to pre-deployed routing design.
- **Azure Monitor, Application Insights, Log Analytics**: detect faults, verify recovery, and store observability data.

~~~mermaid
flowchart LR
    U[Users] --> R[Front Door / Traffic Manager]
    R --> A[Region A - Primary]
    R -. shift traffic when gates pass .-> B[Region B - DR]
    A --> VA[API / Web / DB VMs]
    B --> VB[Recovered VMs]
    VA -. ASR replication .-> VB
    S[Recovery Services vault] --> P[Recovery Plan]
    P --> VB
    O[Monitor and incident log] --> P
~~~

The diagram illustrates the VM case; **ASR does not automatically recover every PaaS component**. If the application uses Azure SQL Database, Azure Storage, Service Bus, Key Vault, or other managed services, each needs its own redundancy/replication and orchestration plan. Both Front Door and Traffic Manager also require DR origins/endpoints and health probes configured before an outage.

**Split-brain risk:** if Region A recovers partially, both sides could believe they are valid writers. The runbook must enforce **one authoritative write store** or use a separately engineered and tested multi-writer architecture. Never rely solely on DNS changes to stop writes in the old region.

Example assumptions: **60-minute target RTO, 15-minute target RPO**. These values are illustrative; real systems require test evidence and business-owner sign-off.

## 3. Preparing the Runbook Before an Incident

An operational runbook must document:

| Section | Required details |
| --- | --- |
| Identification | Service, subscription, Entra tenant, resource groups, Region A/B, vault, Recovery Plan name, version |
| Responsibilities | Incident Commander (IC), Azure ops, data team, network/DNS, app owner, approver, and backup comms channels |
| Triggers | SLIs/SLOs, user impact level, incident start timestamp, decision deadline |
| Dependencies | Databases, APIs, web tier, private DNS, identity, secrets, certificates, firewalls, queues, schedulers, external integrations |
| Targets | RTO, RPO, data-loss limits, Go/No-Go criteria |
| Procedures | Recovery Plan, validation scripts, dashboards, log locations, and remediation steps |
| Evidence | Job IDs, timestamps, recovery point, smoke-test results, data-reconciliation results |
| Closure | Active DR state, failback plan, re-protect, next operational owner |

Never store plaintext passwords, access keys, or tokens inside runbooks. Use scoped Azure RBAC, Managed Identities, and audited emergency access procedures. Incident communication channels should also not depend exclusively on Region A.

### Readiness Checklist

1. **Replication:** VMs have healthy protection/replication status; recovery points and lag meet targets; sync errors resolved.
2. **Capacity:** DR region holds sufficient quotas/SKUs, disks, IPs, network capacity, and availability zones; foundational components like load balancers, firewalls, and egress are ready.
3. **Networking and identity:** VNet/subnets/NSGs/routes, private DNS, TLS, certificates, Key Vault, Entra ID, RBAC, and Managed Identities do not block VMs running in B.
4. **Data and integrations:** clarity on where writes stop, how databases recover, which queues/schedulers could run twice; PaaS dependencies have dedicated plans.
5. **Observability and drills:** health checks, synthetic monitoring, logs, and notifications are ready; test failover has been executed in an isolated network, cleaned up, and improved.

Healthy replication **does not** prove the application runs correctly in DR or meets RTO.

## 4. Trigger Decision: Planned or Unplanned?

The IC determines whether the outage truly warrants switching regions—for instance, both external and internal health checks fail, core components cannot recover within acceptable bounds, and staying in A risks breaching RTO. Detection thresholds and wait windows are **organization-defined parameters tied to SLOs**, not Azure defaults.

~~~mermaid
flowchart TD
    I[Incident detected] --> V{Severe business impact?}
    V -- No --> X[Standard remediation]
    V -- Yes --> Q{Is Region A still safe and syncable?}
    Q -- Yes --> P[Evaluate planned failover]
    Q -- No --> U[Evaluate unplanned failover]
    P --> G{Approved and data conditions met?}
    U --> G
    G -- No --> H[Halt and resolve missing preconditions]
    G -- Yes --> F[Execute Recovery Plan]
    F --> B{Application and data pass validation?}
    B -- No --> C[Block traffic and remediate]
    B -- Yes --> T[Shift traffic to DR]
~~~

Before triggering failover, operators log: incident start time, approver, replication direction, current replication lag, chosen recovery point, potential data at risk, and justification for planned vs. unplanned mode. The newest recovery point minimizes data loss; an **application-consistent** point helps restore proper app state. Yet application-consistent alone does not guarantee distributed consistency across databases, queues, and external systems.

## 5. Orchestration with Azure Site Recovery Recovery Plans

An ASR **Recovery Plan** organizes protected VMs into ordered groups and can interleave manual actions or Azure Automation runbooks. Groupings should reflect **application dependencies**, not merely resource group names.

| Group / gate | Action | Owner | Gate to advance |
| --- | --- | --- | --- |
| **G0 – Declare DR** | IC decides; halt deployments, assess recovery points, enable single-writer protection | IC + data | Decision logged, timestamped, risk accepted |
| **G1 – Foundation** | Verify VNet, internal DNS, routes, firewalls, secrets, permissions, and base services in B | Network + platform | Essential dependency connectivity works |
| **G2 – Database** | Recover data VMs; verify DB state, integrity, and write permissions | Data team | Only one writable primary exists; DB healthy |
| **G3 – Backend/API** | Boot app VMs, load DR config, connect to DB | App owner | API readiness + normal logs/traces |
| **G4 – Web/integrations** | Boot frontend, check TLS, login, queues, callbacks, schedulers | App + ops | Business smoke tests pass |
| **G5 – Cutover** | Shift routing via Front Door/Traffic Manager; verify externally | IC + network | Real users reach B; SLIs recover |
| **G6 – Stabilize** | Monitor, drain backlogs, log status, and commit per procedure | IC + all teams | Verified stable DR operations |

Names **G0–G6 are illustrative runbook gates**, not fixed ASR group names. G1 infrastructure is usually pre-provisioned via IaC or standard procedures; Recovery Plans do not automatically create every non-VM dependency.

### Azure Portal Execution Flow

In the **Recovery Services vault**, open **Site Recovery → Recovery Plans** (menu labels may vary across portal updates), then open the approved plan:

1. Verify replication direction, VMs in the plan, target region, target network, and manual/automation steps.
2. For drills, pick **Test failover** with an isolated test network. During real incidents, choose the appropriate **Planned failover / Failover** option.
3. Monitor ASR jobs group by group; verify VM and app status and record job IDs. Never wave through a manual gate if checks fail.
4. Validate data, APIs, and business flows independently of "VM running" status; shift routing only after checks pass.
5. Once failover results are accepted, run **Commit** per ASR workflow. Commit finalizes the failover and can lock out re-selecting earlier recovery points from that failover session.
6. Run **Re-protect** in the required direction to protect the active DR environment and prepare for failback.

During incidents, **automation assists execution**, while decisions to accept data loss, fence writes in A, open live traffic, and commit require clear authority and evidence. Never assume a failed script will automatically halt routing changes performed by external systems.

## 6. Example Post-Recovery Automated Validation Runbook

This example uses an **Azure Automation PowerShell runbook** to confirm a VM is running and the app's HTTP readiness endpoint responds. It is a validation step—**not a command to trigger failover or change DNS**.

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $VmName,

    [Parameter(Mandatory = $true)]
    [string] $HealthUrl
)

$ErrorActionPreference = 'Stop'

# Azure Automation has system-assigned managed identity enabled.
Disable-AzContextAutosave -Scope Process | Out-Null
Connect-AzAccount -Identity | Out-Null

$vm = Get-AzVM -ResourceGroupName $ResourceGroupName -Name $VmName -Status
$powerState = $vm.Statuses |
    Where-Object { $_.Code -like 'PowerState/*' } |
    Select-Object -First 1 -ExpandProperty Code

if ($powerState -ne 'PowerState/running') {
    throw "VM $VmName is not in running state: $powerState"
}

$response = Invoke-WebRequest -Uri $HealthUrl -Method Get -TimeoutSec 15
if ($response.StatusCode -ne 200) {
    throw "Health endpoint returned HTTP $($response.StatusCode)"
}

Write-Output "PASS: VM is running and health endpoint is ready."
~~~

Execution prerequisites:

- The Azure Automation Account has Managed Identity enabled, read permissions on the VM's resource group, and matching `Az.Accounts` / `Az.Compute` modules in its runtime.
- `HealthUrl` points to the recovered service in B—never accidentally checking Region A. If the endpoint is private-network only, use an appropriate connectivity path such as a **Hybrid Runbook Worker** instead of assuming cloud workers can reach private VNets.
- `/health/ready` must check at least critical dependencies (such as the database), not merely web-process liveness.
- Never log tokens/secrets, and never treat HTTP 200 alone as enough evidence for cutover. Add transaction, data, TLS, and queue tests, and inspect both **Automation jobs** and **ASR jobs**.
- For newly booted VMs, bounded retries and clear timeouts may be appropriate; any persistent failure must still alert the responsible owner.

A business smoke test can create a **test order with a unique idempotency key**, read that exact order back in B, verify queues process without duplication, inspect traces, and confirm no worker in A still accepts writes. Tag test data clearly and include a cleanup step.

## 7. Executing Failover Across Control Gates

**Step A – Open incident, freeze changes.** The IC declares severity, opens coordination channels, and starts the timeline log. Pause deployments, schema migrations, schedulers, or batch jobs that could skew data. Assign ASR operators, DB validators, routing operators, and business sign-off owners.

**Step B – Protect write authority.** If Region A is reachable, stop writes, drain in-flight transactions, and run final planned sync. If A is unreachable, enforce **fencing** or primary-authority locks so A cannot come back later and write alongside B. For databases with leader election, the data team must verify only one leader accepts writes.

**Step C – Start the Recovery Plan.** Select the recovery point and failover mode with documented rationale. Watch every job and validate groups G1–G4 by dependency order. DB, secret, internal DNS, or quota failures are grounds to **stop before G5**.

**Step D – Three-layer verification.** Infrastructure layer: VMs, NSGs, routes, DNS, certificates. Service layer: readiness, login, APIs, error rates, traces. Data/business layer: controlled test transactions, integrity checks, queue lag, order write/readback, duplicate-request handling. Open DR to users only after all three layers pass.

**Step E – Shift traffic.** Update origins/routing in **Front Door**, or endpoint states/priorities in **Traffic Manager**, per architecture. For DNS-based steering, account for TTLs and resolver caching. Test from multiple networks, monitor error rates, and verify traffic to A no longer writes.

**Step F – Stabilize and accept.** The IC records when real users are served in B, checks key SLIs, load, DB, queues, and costs, and announces DR active. Commit the ASR failover only after understanding recovery-point consequences and accepting the state. Configure re-protect from B to A matching actual state.

**No-Go:** if write authority cannot be guaranteed, duplicate transactions risk occurring, data lacks integrity, DR lacks capacity, or core transaction tests fail, **do not open user traffic**. Infrastructure-level Recovery Plan completion does not override business Go/No-Go criteria.

## 8. Failback: Returning to Region A Without Losing DR Data

After failover, **Region B holds newly created business data**. Simply booting the old VMs in A and pointing DNS back can lose orders placed while B served traffic. Failback is a distinct region transition with its own data workflow and approvals.

### Conditions to Start Failback

- Region A is stabilized, root cause is resolved, and infra, permissions, certificates, and dependencies are verified.
- Data, backlogs, transactions, and schemas in B are inventoried, with fresh backups covering the new state.
- **Re-protect / reverse replication B → A** is ready via ASR for supported workloads; PaaS data and queues outside ASR have dedicated sync plans.
- A cutover schedule, owners, stop gates, and a fallback plan to keep B serving if A checks fail are approved.

### Execution Sequence

1. **Restore and verify A:** fix the incident root cause and verify quotas, networking, identities, configs, and target endpoints.
2. **Reverse replicate:** after committing per ASR workflow, run **Re-protect** from active B back to A and wait for healthy replication and valid recovery points. Sync non-ASR services using their native tools.
3. **Reconcile data:** check order counts, duplicate transactions, message IDs, queues, schema changes, and financial totals. VM replication does not replace business reconciliation.
4. **Prepare planned failover B → A:** announce the maintenance window, throttle or stop writes in B, drain in-flight transactions, confirm the final sync point, and execute planned failover.
5. **Verify in A:** bring up components in dependency order DB → API → web, run health checks and smoke tests, verify integrity, and confirm single write authority.
6. **Shift routing back to A:** cut over via Front Door/Traffic Manager per design; test externally and watch clients holding cached DNS.
7. **Commit and re-establish protection:** accept results, commit, then **Re-protect A → B**; verify healthy replication and adjust monitoring to the restored roles.
8. **Close the incident:** record actual RPO/RTO, job history, open issues, costs, and runbook updates.

If A fails **before cutover**, keep B serving and fix A. If traffic already moved to A and A fails again, returning to B is a new failover: inspect data written in A before switching routing to avoid losing transactions.

~~~mermaid
stateDiagram-v2
    [*] --> ActiveA
    ActiveA --> Decision: Incident or scheduled switch
    Decision --> ActiveB: Failover + verify + cutover
    ActiveB --> ReverseReplication: Commit / re-protect B to A
    ReverseReplication --> FailbackReady: A stable, data synced
    FailbackReady --> ActiveA: Planned failover to A + cutover
    ActiveA --> ProtectedA: Commit / re-protect A to B
    ProtectedA --> [*]
~~~

This diagram shows **operational service states**, not ASR job status codes. Always inspect actual replication direction in the vault.

## 9. Customizable Operations Runbook Template

The YAML below is an **operational documentation template**, not a file you can import directly into an Azure Recovery Plan.

~~~yaml
runbook:
  service: order-service
  primary_region: "<region-A>"
  dr_region: "<region-B>"
  rto_target_minutes: 60
  rpo_target_minutes: 15
  incident_commander: "<on-call-owner>"
  recovery_plan: "<vault/recovery-plan>"
  traffic_controller: "<front-door-or-traffic-manager>"
  gates:
    - id: declare
      pass_when: "IC approves; incident time and mode recorded"
      evidence: "incident ID, approver"
    - id: protect_data
      pass_when: "single write authority is verified"
      evidence: "primary/fencing checks"
    - id: recover
      pass_when: "ASR jobs finish; dependencies are healthy"
      evidence: "job IDs, recovery point, VM/DB status"
    - id: validate
      pass_when: "critical business transactions succeed"
      evidence: "test IDs and traces"
    - id: cutover
      pass_when: "external clients reach DR and SLIs recover"
      evidence: "routing change and external checks"
    - id: stabilize
      pass_when: "IC accepts DR-active status"
      evidence: "dashboard and handover notes"
  failback_requirements:
    - "region A stable and secured"
    - "reverse replication healthy"
    - "DR data reconciled"
    - "change window approved"
~~~

In a real runbook, replace placeholders with exact resource names, dashboard links, tested script paths, contact rosters, evidence templates, and per-failure remediation steps. Never put passwords or customer data inside runbook files.

### Example RTO/RPO Measurement

Suppose Region A stops serving at **09:00**. The IC approves failover at **09:12**; VM recovery completes at **09:34**; transaction validation and cutover finish at **09:46**. The latest recoverable data point is **08:53**.

- **Actual RTO:** 09:00 → 09:46 = **46 minutes**; meets the 60-minute target **if** essential business flows worked accurately at 09:46.
- **Recovery point lag:** 08:53 → 09:00 = **7 minutes**; within the 15-minute RPO, though it does not by itself tell you how many transactions were lost.
- **Reconciliation:** inspect transactions between 08:53 and 09:00 plus events from external services outside the region, since some requests may have partially completed or been retried.

If VMs and health endpoints turned green at 09:46 yet orders could not succeed until 10:05, business RTO **must count until 10:05**. Never substitute ASR job completion time for essential business service recovery time.

## 10. Drills and Troubleshooting Common Failures

Drill on an organization-approved schedule—for example, quarterly or after major changes. Use **ASR Test failover** with an **isolated VNet**; block real emails, live payments, callbacks, workers, or schedulers from affecting production. Collect evidence, then run **Cleanup test failover**. Failback drills need their own scenario because they involve reversing protection and handling new data in DR.

| Metric | Evidence to collect |
| --- | --- |
| Detection and decision | Incident timestamp, approval, planned/unplanned rationale |
| Replication | Health, lag, recovery point, data at risk |
| Infrastructure | ASR job IDs, VM/DB ready timestamps, quota/permission gaps |
| Business | Time first critical transaction succeeds, missing/duplicate data, backlog |
| Routing | Cutover duration, user errors, DNS caching, latency |
| Failback | Reverse replication, final sync, cutback to A, re-protect A → B |
| Documentation | Script bugs, unclear gates, missing contacts, actual step durations |

**Failure 1 – VM boots yet API returns 500.** Inspect internal DNS, firewalls, DB connections, Key Vault/secrets, TLS, and distributed traces. Stop at the validation gate; do not open traffic.

**Failure 2 – DR lacks quota or SKU.** Inspect job errors and regional limits. Fall back only to pre-evaluated VM/SKU options; provision capacity ahead of incidents because emergency quota requests can blow past RTO.

**Failure 3 – Some clients keep writing to A after cutover.** Check DNS caching, old origins, direct access paths, and single-writer fencing; route misdirected transactions into reconciliation rather than trusting DNS alone.

**Failure 4 – Failback to A misses data created in B.** Stop writes to A, inspect re-protect direction, replication status, and sync mechanisms for every data store; proceed only after data owners verify integrity.

**Failure 5 – Automation step succeeds yet transactions fail.** Distinguish job, VM, HTTP endpoint, and business-flow states. Add idempotent synthetic transactions and manual approval gates before cutover.

After drills or incidents, update the runbook with real lessons learned and run a postmortem covering root causes, timeline, impact, decisions, and corrective actions with assigned owners.

## 11. Applied Exercise

A service consists of two API VMs, one queue-worker VM, and one database; target RTO is **45 minutes** and RPO is **10 minutes**. The system already has Azure Front Door and an ASR Recovery Plan, but lacks queue checks, transaction validation, and a failback plan.

1. **Design recovery group ordering** from data to APIs and workers. Which steps can be automated? Which require human approval? How do you prevent workers from running simultaneously in both regions?
2. **Write at least five Go/No-Go criteria** before Front Door shifts users to DR. Separate infrastructure, API, data, and business checks.
3. **Draft a failback plan** covering: Region A readiness, B → A sync, write freeze timing, transaction verification, cutover, and A → B re-protect.

A complete answer demonstrates **one valid write authority, clear decision-makers, business verification before cutover, data reconciliation, and post-switch re-protect**. An ASR Recovery Plan reporting completion proves only that part of the infrastructure recovered.

## Conclusion

Runbooks turn Azure backup and replication configurations into repeatable, testable, and accountable recovery procedures. **ASR Recovery Plans** orchestrate supported VMs, while networking, identity, data, PaaS services, traffic routing, and transactions must be validated with dedicated mechanisms. **Failover ends when business flows serve from DR; failback is safe only after new DR data is preserved and protection direction is re-established.**
