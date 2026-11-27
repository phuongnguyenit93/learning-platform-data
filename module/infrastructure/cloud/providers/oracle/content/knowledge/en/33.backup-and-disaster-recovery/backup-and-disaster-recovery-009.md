# Measuring Recovery Time and Maintaining DR Runbooks

## 1. Objectives and scope

In the **Backup and Disaster Recovery** chapter of the Oracle Cloud Infrastructure (OCI) module, this lesson addresses two operational questions: **how long does the service actually take to recover**, and **how can the on-call team reliably execute the DR runbook during an incident**.

After this lesson, you can:

- Choose start milestones, end milestones, and evidence sources for recovery measurements.
- Compare actual recovery time against RTO while verifying the recovered data point against RPO.
- Distinguish infrastructure operation time, DR plan execution time, and user-experienced downtime.
- Design scoped drills on OCI and explain the limits of their findings.
- Build runbooks with clear owners, execution preconditions, acceptance criteria, and maintenance processes.

You should understand basics of tenancy, compartment, IAM, VCN, Compute, storage, backups, and Oracle database recovery options. This lesson focuses on measurement and process governance; configuring individual backup or replication mechanisms belongs to the respective infrastructure design lessons.

Numbers, application names, and test thresholds in this lesson are **learning examples**, not Oracle recovery-time commitments.

## 2. Defining what "recovered" means

### 2.1. Separate objectives from measured results

**Recovery Time Objective (RTO)** is the maximum outage duration acceptable to the business. **Recovery Point Objective (RPO)** is the maximum acceptable data loss, typically expressed as a time interval. These are objectives that must be agreed upon before choosing a DR approach. [Oracle: Plan Your Disaster Recovery Strategy](https://docs.oracle.com/en/solutions/oci-best-practices/plan-your-disaster-recovery-strategy.html).

In reports, use distinct names for targets and results:

| Metric | Meaning | Example |
| --- | --- | --- |
| Target RTO | Outage limit approved by the business | 45 minutes |
| Actual recovery time | Elapsed time from service disruption until recovery criteria are met | 37 minutes |
| Target RPO | Limit on potentially unrecoverable data window | 120 seconds |
| Observed recovery-point lag | Gap from disruption timestamp to verified consistent data point | 80 seconds |
| DR plan execution time | Elapsed time of the orchestration workflow run alone | 15 minutes |

Never write "RTO = 15 minutes" simply because the orchestration tool finished in 15 minutes. State explicitly whether a figure is an objective, an end-to-end result, or a single component's timing.

### 2.2. Write exit criteria before running

A Compute instance in running state or an open database is insufficient to confirm an ordering system has recovered. Criteria must bind to the functions and service levels required by the business.

For example, the operations team agrees the ordering service is recovered when:

1. Test users sign in via the protected access path as designed.
2. Submitting a test order with a deduplication key succeeds, reads back, and shows expected status.
3. Orders with attachments successfully read corresponding files from target storage.
4. Required background jobs are running; external-side-effect jobs are enabled at the designated phase.
5. Under agreed test load, error rate stays below 1% and p95 latency stays below 1 second for 5 continuous minutes.
6. Data reconciliation meets RPO with no business-blocking inconsistencies found.
7. The business owner signs off per runbook authority.

Load thresholds must be meaningful: 100 requests/minute does not prove capacity for 10,000 requests/minute. If DR only restores a minimal mode—such as allowing lookups while disabling order creation—assign a separate name and objective to that mode.

In the example above, the 5-minute stability window counts toward recovery time. If a team adopts a different convention, record stability start and verification end timestamps explicitly; never alter conventions after seeing results.

### 2.3. Specify the start milestone

For real incidents, pick the earliest timestamp with reliable evidence that the service stopped meeting serving criteria. Sources may include synthetic user probes, error metrics, or transaction logs.

For drills, record at least two milestones if they differ:

- **Fault-injection command time:** when the controller starts the scenario.
- **Service-impacted time:** when end-to-end probes confirm disruption.

A drill spinning up a target copy without disrupting the source has no production outage duration to measure. Its report must state "time to provision and validate DR copy," along with tested scope.

If probes poll every 60 seconds, disruption onset may lie anywhere between the last success and first failure. Preserve this uncertainty interval. Never report one-second precision when observation sources only have one-minute resolution.

## 3. Building the recovery timeline

### 3.1. Minimum milestones

A milestone set applicable across many DR procedures:

| Milestone | Event | Appropriate evidence |
| --- | --- | --- |
| `t_outage` | Service begins failing | Probe outputs, failed transactions |
| `t_detected` | System or on-call detects disruption | Alerts, on-call acknowledgment events |
| `t_declared` | Authorized owner decides to activate DR | Decision entry in incident log |
| `t_execution_start` | Chosen recovery workflow begins | Execution ID, orchestrator logs |
| `t_execution_end` | Orchestration workflow completes | Execution result and step logs |
| `t_route_verified` | Access via target serving path confirmed | Probes from representative locations |
| `t_service_restored` | End-to-end recovery criteria met | Test report and business sign-off |

If prechecks run immediately before the workflow, record their duration and note whether they sit inside `t_execution_start → t_execution_end`. Regardless of log organization, that time still belongs to outage duration if the service is down.

Safety confirmations, approval waits, retries, and error handling must all appear on the timeline. Never pause the clock when the team switches from automation to manual intervention.

### 3.2. Worked numerical example

Suppose the ordering app uses Compute, Load Balancer, and Oracle Database. A standby region has networking and data recovery ready. The team sets RTO at 45 minutes and RPO at 120 seconds.

All timestamps below are UTC:

| Event | Timestamp on 2026-11-21 | Elapsed since prior event |
| --- | --- | --- |
| Service disrupted | 03:00:00 | — |
| Detected and acknowledged | 03:02:00 | 2 minutes |
| Decision to activate DR | 03:07:00 | 5 minutes |
| Orchestration workflow starts | 03:09:00 | 2 minutes |
| Orchestration workflow completes | 03:24:00 | 15 minutes |
| Target access path verified | 03:29:00 | 5 minutes |
| End-to-end verification and stability window pass | 03:37:00 | 8 minutes |

Results:

```text
Actual recovery time
  = t_service_restored - t_outage
  = 03:37:00 - 03:00:00
  = 37 minutes

Orchestration workflow runtime
  = t_execution_end - t_execution_start
  = 03:24:00 - 03:09:00
  = 15 minutes

Remaining RTO headroom
  = 45 - 37
  = 8 minutes
```

Within the final 8-minute verification phase, checks might take 3 minutes to pass followed by 5 minutes of stability observation. Record these sub-milestones so readers understand exit conditions.

Suppose the verified consistent data point is `02:58:40Z`:

```text
Recovery-point lag
  = 03:00:00 - 02:58:40
  = 80 seconds

Comparison against RPO target
  = 80 seconds <= 120 seconds
```

The proper conclusion is: **this test recovered the service in 37 minutes and verified a data point 80 seconds prior to disruption**. This is evidence for the tested scenario, configuration, and load. It does not prove every future incident yields the same outcome.

### 3.3. Allocating a time budget

Breaking RTO into a budget highlights areas for improvement:

| Phase | Example budget | Actual | Notes |
| --- | --- | --- | --- |
| Detection | 3 minutes | 2 minutes | 1 minute remaining |
| Decision | 5 minutes | 5 minutes | Full phase budget used |
| Pre-execution prep and checks | 2 minutes | 2 minutes | Watch closely if permission errors occur |
| Recovery orchestration | 20 minutes | 15 minutes | Analyze slowest step |
| Access path verification | 5 minutes | 5 minutes | Zero headroom |
| Application and stability checks | 10 minutes | 8 minutes | 2 minutes remaining |
| **Total** | **45 minutes** | **37 minutes** | **8 minutes remaining** |

Values are internal allocations, not OCI technical limits. Sum only non-overlapping sequential intervals. If data verification runs concurrently with app startup, represent the parallel relationship instead of double-counting.

## 4. Collecting trustworthy evidence on OCI

### 4.1. Separate three observation layers

| Layer | What to know | Evidence source |
| --- | --- | --- |
| Operations governance | Who detected, who decided, why waits occurred | Incident or drill record |
| Infrastructure and orchestration | Which APIs ran, which steps passed or failed | OCI Audit, DR plan executions, automation logs |
| Service and data | What users can execute, which data survived intact | Synthetic tests, app logs, reconciliation queries |

OCI Audit records calls to supported public APIs, including timestamp, caller, target resource, and response. It correlates control-plane actions; a successful API response does not prove the application is ready. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

OCI Logging provides service logs and custom logs. Required log categories must be enabled or configured beforehand with appropriate IAM access for on-call lookup. Never assume every application log automatically appears in the tenancy. [Oracle: Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm).

For Full Stack DR, save execution IDs, statuses, and per-step logs. Console viewers may show only tails; download complete logs for root-cause analysis and evidence archival. [Oracle: View Logs for Disaster Recovery Plan Executions](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/view-logs-dr-plan-executions.html).

### 4.2. Standardize timestamps and identifiers

Each event should include:

- Incident or drill ID to correlate multiple sources.
- Event timestamp in ISO 8601 with time zone; prefer UTC.
- Collector ingestion timestamp if materially different.
- Relevant region, compartment, resource, or execution ID.
- Runbook version, automation revision, and scenario branch.
- Evidence source, recording person, or recording system.
- Outcome, attempt number, and errors if any.

Synchronize clocks across log-producing hosts and document known skew. Within a single process measuring duration, monotonic clocks avoid system-clock-jump artifacts. When correlating logs across hosts, standardized timestamps and skew metadata remain necessary.

The JSON sample below is an **operations-team-defined schema**, not default fields in OCI APIs:

```json
{
  "exercise_id": "orders-dr-20261121-01",
  "scenario": "primary-unreachable",
  "event": "service_restored",
  "event_time": "2026-11-21T03:37:00Z",
  "observed_time": "2026-11-21T03:37:02Z",
  "runbook_version": "2.4",
  "automation_revision": "git:<commit-id>",
  "region": "<dr-region>",
  "compartment_id": "<dr-compartment-ocid>",
  "plan_execution_id": "<execution-ocid-if-used>",
  "attempt": 1,
  "result": "passed",
  "evidence_ref": "<restricted-evidence-location>"
}
```

Never place passwords, tokens, private keys, or customer payloads in events. Runbooks record locations and authorized secret-retrieval methods rather than raw secret values.

### 4.3. Place observability outside the blast radius

If monitoring systems and the sole runbook copy both depend on the lost region, the team may not know when the outage began or what to do next.

Verify accessibility under drill conditions:

- On-call staff can read runbooks and contact lists from a surviving location.
- End-to-end probe outputs and decision logs still persist.
- Operational accounts can sign in, including organizationally approved emergency break-glass paths.
- The evidence store has proper read/write permissions at the target and clear retention rules.
- Logs not yet shipped to central storage remain buffered at source for later backfill.

The goal is preventing loss of both the recovery system and the means to prove recovery occurred.

## 5. Verifying RPO alongside recovery time

### 5.1. Identify the usable data point

Let:

- `t_outage` be the chosen disruption timestamp.
- `t_recovery_point` be the latest timestamp where recovered data is proven complete, consistent, and usable within business scope.

When `t_recovery_point <= t_outage`:

```text
recovery_point_gap = t_outage - t_recovery_point
```

This interval represents recovery-point lag. To determine which actual transactions were lost, still reconcile the set of source-accepted transactions against those present at target.

Never rely solely on backup file creation time or the record with the maximum timestamp. A newer record may exist while earlier transactions are missing, attachments have not arrived, or queues hold unprocessed tasks.

### 5.2. Reconciliation procedure for an ordering application

In the drill environment, prepare synthetic transactions with unique IDs and deduplication keys. Record which transactions the source application truly confirmed per its durability semantics.

An independent witness store can hold IDs and confirmation timestamps without sensitive payloads. If no reachable witness exists, explicitly document the limitation of your conclusion.

After recovery:

1. Determine the database recovery point via the active mechanism.
2. Compare source-confirmed IDs against IDs readable at the target.
3. Verify a contiguous watermark before which all scoped transactions are complete.
4. Check relationships across orders, order items, and attachments.
5. Inspect background tasks, outboxes, or queues per application design.
6. Record missing transaction counts, duplicates, ambiguous cases, and recovery-point lag.

If multiple writers, partitions, or out-of-order completions exist, a single highest sequence number does not prove all preceding data arrived. Maintain per-stream watermarks or full-scope witness sets.

A replication lag metric is a useful input for decisions, yet never replaces checking recovered data. For Oracle Data Guard or backup recovery, runbooks must cite the exact procedures and evidence of the database service in use; never assume one universal promote command fits all services.

Full Stack DR orchestrates workflows and does not itself determine application RPO. RPO also depends on underlying storage, database services, and replication configuration. [Oracle: Full Stack Disaster Recovery FAQ, RTO and RPO section](https://www.oracle.com/cloud/full-stack-disaster-recovery/faq/).

### 5.3. Never declare "passed" without evidence

For instance, a DR plan finishes in 15 minutes and the app reads a newest record visible at `02:59:50Z`. Without evidence that earlier transactions are complete, you cannot conclude data loss was only 10 seconds.

Reports should distinguish:

| Status | Meaning |
| --- | --- |
| Passed | Measurements and evidence satisfy objectives within published scope |
| Failed | Evidence shows objectives exceeded or mandatory criteria violated |
| Unverified | Insufficient evidence available to conclude |
| Out of scope | Item excluded by drill design and explicitly documented |

A drill can pass recovery time while leaving RPO unverified. Report these two outcomes independently.

## 6. Timing analysis in Full Stack DR

Full Stack DR structures plans into groups and steps. Groups execute sequentially, while steps within the same group execute in parallel. Prechecks validate plan and config readiness; prechecks themselves do not mutate topology. [Oracle: Overview of Disaster Recovery Plan Executions](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/overview-dr-plan-executions.html).

Thus, if a group contains three independent steps taking 4, 7, and 5 minutes, group duration is roughly 7 minutes plus orchestration overhead, rather than 16 minutes. Use real timestamps because waits, retries, or error handling may occur.

Example:

```text
Group A: Precondition checks       2 minutes
Group B: Data recovery             7 minutes
Group C: Start app components      4 minutes
Group D: In-plan checks            2 minutes
                                  ----------
Orchestration runtime             15 minutes
```

The path governing total duration is the longest dependent chain, called the **critical path**. Shaving a parallel step from 4 minutes to 2 minutes will not speed up the group if the 7-minute step still dictates completion.

When diagnosing slowness, ask in order:

1. Which group consumes the most time?
2. Which step determines when that group finishes?
3. Is that step actively processing, waiting on capacity, waiting on permissions, or waiting on humans?
4. Can it be pre-staged, automated, or parallelized while preserving dependencies?
5. After optimizing, do data verification and single-writer guarantees still hold?

Passing prechecks does not prove the service recovered, data met RPO, or resources will always provision during a real outage. End-to-end execution and validation are required to evidence those claims.

Never skip a failing step merely to make total duration look better. If continuing in a degraded state is acceptable, the runbook must pre-define conditions, authority, and impact.

## 7. Choosing drills aligned with what must be proven

### 7.1. Formats and limits

| Format | What it tests | Limits to record |
| --- | --- | --- |
| Tabletop walkthrough | Decisions, comms, sequence, responsibilities | Cannot measure real infrastructure recovery times |
| Isolated copy restore | Backup usability, config, data verification | May omit user routing or source-outage failures |
| Orchestrated DR drill | Provisioning and testing stack at target | Bound by supported components and isolation setup |
| Planned switchover | Role-swap flow while source stays healthy | May be easier than source-unreachable outages |
| Test failover with isolated source | Recovery branch without relying on source | Represents only simulated faults and scale |
| Controlled failback | Reverse sync, role swap, repeat validation | Requires its own plan and measurements |

In Full Stack DR terminology, Start DR Drill spins up a test stack in the standby group and Stop DR Drill tears down that drill stack. Switchover and failover are distinct transition types. [Oracle: Full Stack Disaster Recovery Terminology and Concepts](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/disaster-recovery-terminology.html).

Spinning up a stack copy does not mean all application side effects are isolated. Runbooks must address payment endpoints, emails, webhooks, job schedules, and write paths. Check supported resource types and plans in your actual configuration; never assume every component shares identical drill support.

### 7.2. Making measurements representative

Before drilling, record:

- Data volume, growth rate, and timestamp of chosen backups.
- Which resources were pre-staged vs. provisioned only upon activation.
- How much advance notice staff received and whether operators knew the system.
- Load levels, probe locations, and external integrations tested.
- Whether detection, decision, and prep times are included in results.
- Where source loss is simulated: host, network, service, or management plane.
- Reachability of IAM, secret stores, automation code, and evidence stores during source outage.
- Abort criteria, cost caps, and drill teardown procedures.

If data was preloaded, permissions pre-opened, or all Compute pre-created before starting the clock, those conditions must appear in the report.

When verifying access paths, probe from representative networks and resolvers. Updating a DNS record or receiving API success only confirms control-plane action. When users actually reach the target still depends on caches, open connections, and application name resolution.

## 8. Designing runbooks so on-call engineers can execute them

### 8.1. Header metadata

Runbooks must be executable documents with version IDs and verification status. The template below is merely a sample header for operational docs:

```yaml
runbook_id: orders-oci-dr
version: "2.4"
owner_role: platform-operations
backup_owner_role: database-operations
service: orders
scenario: primary-unreachable
source_region: "<source-region>"
target_region: "<dr-region>"
source_compartment_ocid: "<source-compartment-ocid>"
target_compartment_ocid: "<target-compartment-ocid>"
rto_target_minutes: 45
rpo_target_seconds: 120
plan_reference: "<dr-plan-ocid-or-approved-workflow>"
automation_revision: "<commit-id>"
last_exercise_id: orders-dr-20261121-01
last_validated_at: "2026-11-21T03:37:00Z"
next_review_due: "<date-by-team-policy>"
evidence_location: "<restricted-location>"
```

Placeholders must be replaced with exact values before putting the runbook into service. Display names aid human recognition, whereas OCIDs and regions identify exact operational targets.

Beyond header fields, runbooks need dependency diagrams, service addresses, authentication methods, authorized decision-makers, and backup contact lists. A runbook lacking clear incident branches easily leads responders to run switchover by mistake when the source is already unreachable.

### 8.2. Clear role assignments

| Role | Core responsibility |
| --- | --- |
| Incident commander | Decide activation, adjust scope, approve degraded modes |
| Infrastructure executor | Run approved workflows, verify region, compartment, and resources |
| Database lead | Verify data, role-transition criteria, and data-loss exposure |
| Network and security lead | Check routes, permissions, secrets, and old-writer isolation |
| App/business validator | Run synthetic verification transactions and sign off recovery criteria |
| Scribe | Record timeline, decisions, attempts, and evidence links |

One person may cover multiple roles on small teams, yet responsibilities must remain explicit. Designate alternates and backup communication channels when primary tools fail.

During an incident, exercise pre-delegated organizational authority rather than hunting for approvals from scratch. Decisions outside that mandate—such as accepting data loss beyond limits—must escalate to the appropriate authority.

### 8.3. Reference recovery sequence

The table below outlines a runbook structure for the ordering example. Concrete steps must be tailored to real OCI services and designs before operational use.

| Step | Action | Condition to proceed |
| --- | --- | --- |
| 1. Confirm incident | Identify affected services, blast radius, outage onset, evidence reliability | Incident ID, commander, and matching scenario selected |
| 2. Verify permissions and target | Check execution identity, tenancy, region, compartment, plan, and runbook version | Right target, sufficient rights, required tools reachable |
| 3. Assess data | Check backups/replicas, expected data point, decryption readiness, RPO threshold | Clear decision on recovery data source |
| 4. Ensure single active writer | Execute designed isolation or fencing; inspect evidence | Safe conditions for target to become writer |
| 5. Execute workflow | Run approved plan or recovery branch; save IDs and logs | Mandatory steps finished; error states resolved |
| 6. Internal target checks | Verify DB, app config, connections, secrets, and needed files | Ready to open service in stages |
| 7. Shift and verify access | Update routing per design, probe externally, manage background jobs | Traffic reaches right target; zero uncontrolled writers |
| 8. Business verification | Reconcile data, run synthetic transactions, monitor stability window | Criteria defined at start of runbook satisfied |
| 9. Declare recovery and protect | Record recovery time, confirm owners, verify new protection | Evidence archived, ongoing monitoring, follow-up plan set |

Steps in the table show logical dependencies. If automated workflows already include fencing or validation, reference those exact steps and reuse their evidence rather than repeating side-effecting actions.

### 8.4. Every step needs sufficient structure

An executable step should answer:

- **Inputs:** which resources, current states, and permissions.
- **Actions:** exact commands, Console paths, or workflows with versions.
- **Expected outcomes:** observable states and evidence to archive.
- **Timeout:** how long to wait and where to poll status.
- **On failure:** who handles it, fallback branch, and whether retry is allowed.
- **Stop condition:** when to halt to avoid data loss or dual writers.

Example application verification step specification:

```text
ID: APP-VERIFY-01
Owner: application-on-call

Inputs:
- Target endpoint identified and authenticated.
- Least-privilege test account.
- Test transaction ID bound to exercise_id.
- Email/payment side effects isolated for drill.

Actions:
1. Sign in via the designated access path.
2. Submit a synthetic order with a recorded idempotency key.
3. Read back the order, status, and attachment.
4. If the request times out, query by the same key before deciding to retry.
5. Reconcile data and monitor serving thresholds for 5 minutes.

Success:
- Transaction executes exactly once per application semantics.
- Related data reads back cleanly.
- Agreed load, error rate, and latency pass.

Stop:
- Active writer cannot be uniquely determined.
- Duplicate orders, missing mandatory data, or wrong environment accessed.

Evidence:
- Timestamps, request ID, transaction ID, read-back outputs, and window charts.
```

In real runbooks, the "actions" section must link to tested commands or test suites. A single line reading "verify application" is not enough for another engineer to reproduce the measurement.

## 9. Handling errors, retries, and failback

### 9.1. Stop at the right time

Runbooks must highlight situations where operators must not proceed unilaterally:

- Cannot determine usable data or data-loss scope.
- Permissions or OCIDs indicate the wrong environment is targeted.
- Designed dual-write prevention cannot be proven.
- Role-transition step ends in an unknown state after timeout.
- Checks reveal skewed data, missing decryption keys, or unrecovered mandatory dependencies.

Source unresponsiveness does not prove the source stopped processing. Changing DNS alone does not guarantee old clients or background jobs stopped writing. Fencing mechanisms must fit the architecture and be verified.

When progress lags behind budget, the commander needs remaining headroom and predefined options. Never skip data verification or open dual writers just to "hit RTO."

### 9.2. Retry based on actual state

After a timeout, the service-side operation may still be running or may have already succeeded. Before retrying:

1. Query execution/work request or resource state using saved IDs.
2. Determine true outcome and any side effects already produced.
3. Retry only steps eligible under current conditions; use deduplication if supported.
4. Record prior attempts, new attempts, and wait intervals.

Never blindly re-issue promote, resource-create, or transaction calls merely because the first response timed out. Runbooks must clearly distinguish "failed," "running," and "unknown."

### 9.3. Failback is a separate plan

After failover, the DR region may become the receiver of new transactions. Returning to the old site requires:

- Identifying which side holds authoritative data.
- Repairing and verifying infrastructure at the intended return site.
- Synchronizing data using exact service-supported mechanisms.
- Verifying role-switch criteria, dual-write prevention, and re-testing the application.
- Recording separate measurements for failback disruption.
- Re-establishing data protection and monitoring post-cutover.

Never simply boot the old source and flip DNS back by default. For drill copies, execute drill-teardown procedures and clean up created resources; that workflow differs from failback after real failover.

## 10. Maintaining runbooks as the system changes

### 10.1. Version control and ownership

Runbooks should live in version-controlled repositories. Every executable version should link to:

- Primary owner and backup owner.
- Related infrastructure configs or Infrastructure as Code commits.
- Script, test-suite, and tool versions.
- Plans/DR protection groups if using Full Stack DR.
- Plan config snapshots or exports captured at drill time.
- Latest verification results, known limits, and next review date.

A plan OCID identifies the resource, yet alone does not describe its full configuration at runtime. If plans are edited in place, save config snapshots or equivalent change-tracking trails.

Distinguish **documentation updated** from **revision verified in execution**. A recent edit date does not make a runbook validated.

### 10.2. Event-driven updates

| Change | Items to review |
| --- | --- |
| Add Compute, change image, or boot config | Recovered components, launch time, readiness checks |
| Modify VCN, subnets, NSGs, or cross-region links | Admin paths, app paths, probes, and fencing |
| Modify IAM, dynamic groups, or compartments | Executor rights, workflow rights, evidence read access |
| Rotate secrets, wallets, certs, or encryption keys | Target retrieval and readability of recovered data |
| Change DB type, standby config, or backup mechanism | Recovery branches, RPO, role-switch steps, failback |
| Alter schemas, outboxes, or file storage locations | Data verification checks and cross-component consistency |
| Change DNS, endpoints, or external integrations | Traffic steering, test suites, drill isolation |
| Staffing, authority, or business target changes | Contacts, decision-makers, RTO/RPO, recovery criteria |

When topology or DR protection group members change, review plans and update via supported workflows; re-run prechecks and drill affected branches. Never assume an older plan automatically covers newly added resources.

### 10.3. Choose testing cadence by criticality

A reference cadence adaptable by teams:

- **After DR-impacting changes:** review affected runbook sections, permissions, configs, and checks.
- **Monthly:** verify contacts, doc accessibility, target permissions, and prerequisites.
- **Quarterly:** drill priority branches with an executor other than the runbook author.
- **Periodically by risk and after major shifts:** test full data scale, source outages, and failback.

This is an operational suggestion, not an OCI default mandate. Base selection on service criticality, change velocity, and organizational commitments.

A high-value test is handing the runbook to a backup on-call engineer and noting everywhere they must ask the author. Every question needed to proceed signals missing inputs, criteria, or context in the doc.

### 10.4. Close the loop after drills

After each run:

1. Preserve raw measurement data and original logs.
2. Build a unified timeline; flag uncertain timestamps.
3. Evaluate every recovery criterion plus time and data targets.
4. Record wait points, off-runbook actions, and retried steps.
5. Create remediation tasks with owners, deadlines, and acceptance criteria.
6. Update runbooks and automation accordingly.
7. Re-execute affected scope to verify fixes worked.

For example, "improve IAM" is too vague. A verifiable action is: "backup on-call account runs prechecks in the DR compartment using approved roles; save output and update the access section in the runbook."

If recovery mechanisms, data layouts, or key dependencies change, re-measure end to end. A script syntax check does not prove a new RTO.

## 11. Reporting results without hiding risk

### 11.1. Minimum report template

| Field | Example value |
| --- | --- |
| Run ID | `orders-dr-20261121-01` |
| Scenario | Source unreachable in test environment |
| Runbook and automation | Version 2.4, commit recorded in dossier |
| Scope | DB, Compute, attachments, access paths, synthetic transactions |
| Entry conditions | Warm standby; data size and load documented separately |
| Target / actual RTO | 45 minutes / 37 minutes |
| Target / verified RPO lag | 120 seconds / 80 seconds |
| Workflow runtime | 15 minutes |
| Attempt count | 1 |
| Exceptions | Live payments replaced with test endpoint |
| Untested items | Real full-region recovery, peak production load |
| Post-run cleanup and protection | Completed status or open items recorded |
| Evidence | Timeline, execution ID, full logs, reconciliation results |
| Sign-off approver | Role and approval timestamp |

Exceptions and out-of-scope sections tell readers exactly what the evidence covers. Never turn "not tested" into "passed" merely because no error was observed.

### 11.2. Tracking across multiple runs

Track:

- Pass rate across total runs for the same scenario.
- End-to-end and per-phase recovery durations.
- Frequency of off-runbook interventions or extra permission grants.
- Count of runs with unverified RPO.
- Age of last verified runbook version and unverified changes.
- Drill cost, lingering resources, and overdue remediation items.

Never drop failed runs from historical reports. If a run reached 50 minutes without recovering, record "not recovered after 50 minutes" with run status; never enter 0 or discard the sample.

Compute medians or percentiles only with sufficient data and meaningful cohorts. Three drills across three different scenarios cannot support a credible p95. Comparisons require consistent conditions across data scale, load, pre-staged capacity, and exit criteria.

When optimizing, weigh measured gains against cost: staging extra capacity, keeping Compute warm, or increasing protection frequency may shorten phases while raising ongoing spend. Never infer an optimal design from a single metric alone.

## 12. Hands-on calculation and runbook completion

### 12.1. Recompute the example with PowerShell

The snippet below calculates durations purely from in-memory sample data and makes no OCI resource calls:

```powershell
$timeline = @{
    Outage         = [DateTimeOffset]::Parse('2026-11-21T03:00:00Z')
    ExecutionStart = [DateTimeOffset]::Parse('2026-11-21T03:09:00Z')
    ExecutionEnd   = [DateTimeOffset]::Parse('2026-11-21T03:24:00Z')
    Restored       = [DateTimeOffset]::Parse('2026-11-21T03:37:00Z')
    RecoveryPoint  = [DateTimeOffset]::Parse('2026-11-21T02:58:40Z')
}

$rtoTargetMinutes = 45
$rpoTargetSeconds = 120

if ($timeline.ExecutionStart -lt $timeline.Outage -or
    $timeline.ExecutionEnd -lt $timeline.ExecutionStart -or
    $timeline.Restored -lt $timeline.ExecutionEnd -or
    $timeline.RecoveryPoint -gt $timeline.Outage) {
    throw 'Timeline does not match sample scenario.'
}

$recoveryMinutes = ($timeline.Restored - $timeline.Outage).TotalMinutes
$executionMinutes = ($timeline.ExecutionEnd - $timeline.ExecutionStart).TotalMinutes
$recoveryPointGapSeconds = ($timeline.Outage - $timeline.RecoveryPoint).TotalSeconds

[pscustomobject]@{
    RecoveryActualMinutes   = $recoveryMinutes
    ExecutionMinutes        = $executionMinutes
    RtoHeadroomMinutes      = $rtoTargetMinutes - $recoveryMinutes
    RecoveryPointGapSeconds = $recoveryPointGapSeconds
    RtoTimeCheck            = $recoveryMinutes -le $rtoTargetMinutes
    RpoTimeCheck            = $recoveryPointGapSeconds -le $rpoTargetSeconds
}
```

Expected values are `37`, `15`, `8`, `80`, `True`, and `True` respectively. The two Booleans only compare sample intervals against targets; they do not verify data completeness or serving quality.

### 12.2. Practice in a dedicated learning OCI environment

1. Choose an application with verifiable transactions and define its data scope.
2. Fill in runbook headers, targets, and exit criteria before running.
3. Verify target access, least-privilege permissions, backups/replicas, logs, and drill abort paths.
4. Choose a clone drill or failure scenario permitted by the environment; record explicitly what is untested.
5. Log all milestones, attempts, decisions, and execution IDs if used.
6. Run the business test suite, reconcile data, and observe the stability window.
7. Calculate end-to-end duration, orchestration duration, and recovery-point lag.
8. Have someone else execute the revised runbook to test reproducibility.
9. Conclude the drill, inspect data protection mechanisms, and reconcile billable resources.

Drill resources need clear identifiers, time bounds, and cleanup owners. Monitor Compute, data copies, storage, logs, and network traffic generated; never assume stopping the app eliminates all costs.

## 13. Mistakes that invalidate measurements and runbooks

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Starting clock at plan launch | Omits detection and decision time | Track timeline from defined disruption milestone |
| Stopping clock when DB opens | Skips app and user-path validation | Use end-to-end criteria with load and stability window |
| Summing all parallel steps | Misstates critical-path duration | Use group and step start/end timestamps |
| Checking only newest record | Misses earlier missing data | Reconcile IDs, watermarks, and cross-store relations |
| Storing logs only at source | Evidence lost when source fails | Place observability and storage outside blast radius |
| Using admin rights in all drills | Hides permission bugs for real on-call staff | Test with exact designed operational identities |
| Retrying after timeout without status check | Risks duplicate actions or bad role flips | Query IDs and state before retrying |
| Editing docs without verifying | Revised runbook lacks execution proof | Bind verification status to every version |
| Drilling only with healthy source | Source-unreachable branch untested | Add scoped scenarios with clear stop gates |
| Omitting failed runs | Overly optimistic duration reports | Retain all runs, statuses, and observed timings |
| Leaving drill copies uncleaned | Ongoing spend and orphaned resources | Run teardown steps, inventory, and owner sign-off |

A ready runbook needs a concrete version, accurate system inputs, clear executors and decision-makers, safety gates, result-verification procedures, and evidence from representative runs. The ultimate measure is whether the on-call team can restore committed functions within agreed time and data limits using a repeatable process.
