# Cloud Advisor and Detecting Underutilized Resources

## 1. Lesson Objectives

In the **Cost and Capacity Management** chapter of the Oracle Cloud Infrastructure (OCI) module, Cloud Advisor helps surface resources worth investigating to cut waste. However, low CPU, an unattached volume, or an estimated savings number alone is not enough to decide to downsize or delete a resource.

This lesson guides how to place recommendations in the right tenancy, compartment, and workload context; verify them with monitoring telemetry; execute controlled changes; and reconcile actual impact. The scope covers Compute, storage, and Oracle database workloads, tied to IAM, availability, and automation capabilities.

After this lesson, you can:

- Distinguish low utilization signals from capacity that can genuinely be reduced.
- Verify access permissions and data quality before evaluating recommendations.
- Select remediation options by resource type and application requirements.
- Plan execution, rollback, and savings measurement.
- Use OCI CLI to gather recommendations for an optimization backlog.

## 2. Role of Cloud Advisor

Cloud Advisor analyzes OCI resources and issues recommendations on cost, performance, and availability. The service scans daily, aggregating data from subscribed regions into the tenancy's home region. Results therefore depend on observed telemetry and have latency. See [About Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm).

Treat each recommendation as **an operational hypothesis backed by initial evidence**. For example, a VM might be able to run on a smaller configuration. Operators must verify the hosted application, peak load, batch schedule, and fault-tolerance requirements before locking in a target configuration.

An optimization workflow must answer in order:

1. **Which resources warrant investigation?** Use Cloud Advisor to narrow the list.
2. **Does low utilization reflect true demand?** Use telemetry and business context to explain it.
3. **Which change is feasible and beneficial?** Evaluate dependencies, recoverability, and cost.
4. **Did the outcome meet requirements?** Re-measure both service health and spend after the change.

### 2.1. Division of Labor Across Tools

| Tool or data | Question addressed | How to use in the workflow |
|---|---|---|
| Cloud Advisor | Which optimization opportunities need investigation? | Build the candidate list |
| Monitoring and application metrics | How does the workload consume capacity? | Verify CPU, RAM, network, I/O, latency, and errors |
| Cost Analysis, usage data, and invoices | What charges is the resource scope generating? | Reconcile estimates with actual costs |
| Budgets and budget alerts | Is spend exceeding plan? | Add urgency to investigation |
| Service limits and compartment quotas | Does provisioning fit within allowed limits? | Check conditions for resizing and scaling back up |
| Audit, deployment history, and IaC | Who changed what, and where does desired config live? | Trace changes and keep post-optimization config consistent |

Provisioning quotas and available physical hardware capacity must be checked separately. A compartment having remaining quota does not prove the needed shape is available at the deployment location.

## 3. Low Utilization Does Not Automatically Mean Waste

**Underutilized** describes low usage relative to provisioned capacity over an observation window. **Overprovisioned** describes a configuration exceeding verified demand. The two often relate, yet additional evidence is needed to move from the first statement to the second.

A node at 8% CPU may have to absorb the entire load if another node fails. A VM idle mid-month may run reconciliation at month-end. Conversely, an end-of-life test environment serving no active work is a much clearer reclamation candidate.

Cloud Advisor cost recommendations can cover overprovisioned Compute or databases, unattached block/boot volumes, load balancers with excessive minimum bandwidth, and buckets lacking lifecycle rules. Supported scope must be checked against current resources. See [Cost Management Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/recommendations-costmanagement.htm).

When investigating, distinguish these patterns:

| Pattern to investigate | Example | Additional evidence | Potentially suitable option |
|---|---|---|---|
| Over-allocated capacity | VM has more CPU or RAM than needed | Peak load, memory, network, app requirements | Step down gradually within supported bounds |
| End-of-life resources | Volumes left over after testing | Owner, data, dependencies, retention deadline | Reclaim after verification |
| Mismatched active schedule | Test environment used only during business hours | Background jobs, user timezone, startup time | Evaluate run schedule and remaining costs |
| Mismatched storage pattern | Old data rarely read | Access frequency, restore time, retention | Design data lifecycle |
| Incomplete observability | VM missing RAM metrics | Agent, plugin, Monitoring connectivity | Restore telemetry first |
| Intentional redundancy | Failover standby node | Fault-tolerance requirements and drill results | Keep capacity with documented rationale, set review date |

This table is an operational investigation framework, not a guarantee that Cloud Advisor detects or fixes every example automatically.

## 4. Verify Scope, IAM, and Input Data

### 4.1. Identify Resources Accurately

Use OCID as the primary identifier. Display names aid readability but can collide or change. An investigation record should capture:

- Tenancy, compartment, region, and resource OCID.
- Availability domain or fault domain when relevant to capacity and fault tolerance.
- Application, environment, technical owner, and cost-bearing unit.
- Recommendation type, data retrieval timestamp, and observation window.
- Current configuration, recommended configuration, and recent changes.

If you can see only one compartment, conclusions apply only within that scope. Across multiple tenancies, explicitly record the analyzed tenancy and the tenancy owning the target resource.

### 4.2. Design Read and Execution Permissions

Cloud Advisor's IAM resource family is **optimizer-api-family**. Using Advisor and modifying target resources require appropriate permissions; Advisor access does not replace permission to modify Compute, storage, or databases. See [Required IAM policies](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/implementing-iam-policies.htm).

Responsibilities can be split as follows:

| Role in workflow | Responsibility | Permission scope to design |
|---|---|---|
| Analyst | Read recommendations, metrics, and costs | Read access within assigned scope |
| Application owner | Explain demand and accept outcomes | Read app metrics, confirm service targets |
| Operator | Execute agreed changes | Write access to exact service and compartment |
| IAM administrator | Manage policies, resolve permission gaps | Permissions aligned with org governance duties |

This is an illustrative delegation model for this lesson, not a set of roles created automatically by Cloud Advisor.

Extended metadata can be governed by **optimizer-resource-metadata**. A **No access** message must be treated as an access-permission issue. See [Additional Required Permissions](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/additional_required_permissions.htm).

### 4.3. Missing Metrics Differ from Zero Usage

For agent-emitted Compute metrics, Oracle Cloud Agent and the **Compute Instance Monitoring** plugin must be active. Verify data in the **oci_computeagent** namespace. The VM needs connectivity to Monitoring; Oracle documentation instructs using a service gateway for private subnets without public IPs. See [Enabling Monitoring for Compute Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/enablingmonitoring.htm).

Before reading an average curve, verify:

1. Are data points present during hours the workload actually runs?
2. Do gaps coincide with maintenance, reboots, or agent downtime?
3. Are metrics aggregated for a single instance or an entire application group?
4. Do timezone and range cover batch runs, weekends, and month-end?
5. Was there a recent traffic shift, resize, or new release deployment?

A chart with sparse data points can create false reassurance. When observation is insufficient, the proper conclusion is to gather more evidence.

## 5. Turn a Recommendation into a Grounded Decision

### 5.1. Distinguish Recommendation from Resource Action

A recommendation describes an improvement opportunity category; a resource action binds a recommendation to a specific resource. The CLI provides commands to list resource actions. See [resource-action-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action-summary/list.html).

One recommendation type can span many resources. Evaluate each resource individually before choosing bulk execution.

| Detail to inspect | Evaluation question |
|---|---|
| Recommendation type | Which signal was detected and what action is proposed? |
| Target resource | Does the OCID match the resource confirmed by the app owner? |
| Observation window | Does data cover the required business cycle? |
| Current and recommended config | Which CPU, RAM, network, VNIC, or limit changes? |
| Estimated savings | What are currency, scope, and period? Is there overlap? |
| Dependencies | Are instance pools, backups, IaC, databases, or DR plans involved? |
| Feasibility | Are permissions, capacity, maintenance window, and rollback ready? |

### 5.2. Average, P95, and Peak Load

Cloud Advisor Compute profiles offer Average or P95 options, alongside Conservative, Standard, and Aggressive levels. Evaluation also considers RAM, network, and supported VNIC counts; never use one universal CPU threshold for every case. See [Profile Descriptions](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/cloudadvisor-customizing-profiles.htm).

**Average** reveals baseline load but hides short bursts. **P95** describes the level not exceeded by roughly 95% of samples in the observed set. Samples still sit above it, so a low P95 does not rule out a critical peak.

Self-constructed example: a reconciliation machine runs 20 minutes each night and sits nearly idle otherwise. Daily average is low, yet the job deadline is 25 minutes. Downsizing so the job takes 40 minutes breaches requirements even though full-day average CPU stays low.

Pick windows matching the business cycle:

- Weekly-cycle apps need both workdays and weekends observed.
- Accounting systems need period-close data.
- Campaign-serving services need event traffic or equivalent load tests.
- Newly deployed systems need more observation before long-term extrapolation.

Adjusting a profile or override takes effect on Cloud Advisor's next run. Record the adjustment rationale and review date. See [Cloud Advisor settings](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/cloudadvisor-cloud_advisor_settings.htm).

### 5.3. Distinguish Opportunities from Realized Savings

Cloud Advisor provides savings estimates for supported recommendations; not every proposal includes this value. Missing an estimate does not prove zero benefit. See [How Cost Savings Estimates Are Calculated](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/recommendations-costmanagement.htm).

Separate three stages in reporting:

- **Identified opportunity:** candidate and initial estimate exist.
- **Verified opportunity:** demand, dependencies, and execution plan checked.
- **Verified savings:** change completed, with post-change data reconciled.

If two proposals are mutually exclusive alternatives for the same resource, count only the selected option. Do not add savings from deleting a VM to savings from downsizing that exact same VM.

## 6. Evaluate by Resource Type

### 6.1. Compute: Consider Both Application and Fault Tolerance

Low CPU can accompany high RAM or I/O bottlenecks. For Java applications, inspect heap, off-heap, RSS, GC, swap, and sidecar processes. Keeping maximum heap unchanged while cutting VM RAM can cause out-of-memory failures.

| Evaluation dimension | Evidence to inspect | Risk if omitted |
|---|---|---|
| CPU | Baseline, P95, peaks, and batch duration | Queues grow or batches miss deadlines |
| RAM | Host RAM, heap, off-heap, GC, OOM | Process killed or latency spikes |
| Network/VNIC | Actual throughput and VNIC count | Target shape cannot support required connections |
| Storage I/O | IOPS, throughput, and latency | Low CPU while app stalls on I/O |
| Application | Latency, errors, throughput, deadlines | Infra looks healthy yet service misses SLAs |
| Fault tolerance | Capacity when losing one node | System overloads during an incident |
| Deployment source | IaC, instance configurations, JVM flags | Next deployment recreates mismatched config |

Changing shape can alter CPU, RAM, bandwidth, and supported VNICs. For running instances, documentation notes shape changes trigger a reboot; verify compatible images, limits, and target capacity. See [Changing the Shape of an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resizinginstances.htm).

Execution order should include:

1. Lock baseline config and application pass criteria.
2. Test target config under representative load.
3. Start with one node or a small group first.
4. Coordinate traffic draining and maintenance windows.
5. Apply change, verify startup and service health.
6. Monitor through peak load before scaling rollout.
7. Update IaC or templates used to provision future nodes.

Recording the old shape alone does not guarantee rollback. Prepare recovery duration, capacity re-acquisition conditions, and fallback actions if immediate restoration fails.

### 6.2. Unattached Block/Boot Volumes: Verify Data

Unattached only describes current attachment state. A volume may hold data needed for recovery, investigation, or re-attachment after migration.

Before reclaiming, clarify:

- Data owner and application that previously used the volume.
- Re-attachment, recovery, or ongoing migration plans.
- Contractual, audit, and internal retention obligations.
- Required backups, recoverability, and cost of retaining copies.
- Deletion window and accountable approver.

You can structure a flow: **verify owner → confirm data → agree on timing → reclaim → reconcile residual cost**. Waiting periods are set by the organization based on criticality and data requirements.

Failure to locate an owner is a governance gap to resolve. No response yet is not proof the data has no value.

### 6.3. Object Storage: Lifecycle by Data Usage Pattern

Object Lifecycle Management can transition storage tiers or delete objects via rules. Execution requires permissions granted to the Object Storage service in addition to the user's configuration permissions. See [Object Storage Object Lifecycle Management](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm).

When reviewing lifecycle opportunities, classify data:

| Hypothetical data group | What to verify | Evaluation approach |
|---|---|---|
| Recent logs | Frequent lookup window | Keep accessibility aligned with investigation phase |
| Historical logs | Is restore wait acceptable? | Choose storage tier based on recovery target |
| Re-generable reports | Source to rebuild, time, and cost | Compare keeping copies vs. regenerating |
| Regulated records | When is tiering or deletion permitted? | Follow verified retention requirements |

Before enabling a rule, inspect prefixes, object versions, target scope, and retention locks. For deletion rules, disabling a rule later will not restore lost data. Test on dev data and small object sets before broad rollout.

When calculating benefit, include read/restore costs, target tier minimum retention rules, and required restore duration. An option that lowers storage fees yet misses recovery requirements remains unsuitable.

### 6.4. Oracle Databases: Follow the Exact Service Type

First identify deployment type, CPU model, autoscaling options, billing rules, and supported scaling operations. Do not apply one OCPU/ECPU conversion or one generic CPU-downsizing workflow across all services.

Coordinate with the DBA to verify:

- Is low CPU caused by lock contention, I/O waits, or external services?
- Did ETL, backups, reporting, or period close fall outside the observation window?
- How does reducing capacity affect concurrency, queries, and batch windows?
- Are standby, recovery targets, and fault tolerance still satisfied?
- How do storage, backups, and contract licensing impact total cost?

After resizing, CPU percentage may rise because less capacity is provisioned. Evaluate that increase alongside response times, errors, concurrency, and peak-burst handling.

### 6.5. Load Balancers: Account for Event Traffic

For minimum bandwidth downsizing opportunities, review peak hours and events like launches, large file downloads, or promotions. One ordinary week may not be representative.

Verify minimum, maximum, and limits of the current configuration. After changing, monitor latency, load balancer/backend errors, connections, and bandwidth. A change succeeds only when backends and user experience remain stable.

## 7. Prioritize and Manage Recommendation Lifecycle

### 7.1. Order by Realizable Benefit

| Evaluation dimension | Higher priority when | What lowers readiness |
|---|---|---|
| Benefit | Eliminates meaningful spend | Merely shifts cost allocation |
| Confidence | Complete telemetry, app owner confirmed | Missing peak load, architecture changing |
| Blast radius | Impact can be isolated | Involves shared data or shared services |
| Recoverability | Rollback tested, ample window | Uncertain capacity, hard-to-reverse actions |

A single composite score is not mandatory. A table showing owner, benefit, evidence, and blockers usually drives clearer decisions.

### 7.2. Tie Status to Work Records

The CLI supports **PENDING**, **IMPLEMENTED**, **POSTPONED**, and **DISMISSED**. See [recommendation-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/recommendation-summary/list.html).

In team workflows, pair each status with evidence:

| Status | Accompanying record |
|---|---|
| Pending | Investigator, missing data, next action date |
| Implemented | Actual change, resulting configuration, service health, and cost |
| Postponed | Deferral reason, review milestone, resumption conditions |
| Dismissed | Non-applicability rationale, approver, re-evaluation triggers |

Oracle notes Implemented can also appear when a recommendation expires because usage patterns changed. Therefore, that status alone does not prove operations achieved savings. See [Cloud Advisor Concepts](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm).

For instance, a standby VM that passed failover tests may be kept intentionally. The record should state which fault-tolerance requirement it meets and when to review it next.

### 7.3. Recommended Decision Flow

~~~mermaid
flowchart TD
    A[Receive recommendation] --> B[Identify resource and owner]
    B --> C{Sufficient data and context?}
    C -- No --> D[Add telemetry and schedule review]
    C -- Yes --> E{Reducible capacity exists?}
    E -- No evidence --> F[Record retention rationale and review trigger]
    E -- Yes --> G[Assess dependencies and recovery plan]
    G --> H{Ready to execute?}
    H -- No --> I[Refine plan or postpone]
    H -- Yes --> J[Execute on small scope]
    J --> K{Service targets met?}
    K -- No --> L[Roll back and analyze root cause]
    K -- Yes --> M[Measure cost and update deployment source]
~~~

## 8. Practice on the OCI Console

The output is an evaluation report for one resource. Reading and analysis can be completed prior to any infrastructure change window.

### Step 1: Select Scope

Select an authorized tenancy and compartment, prioritizing a learning environment with clear ownership. Record the resource region and observation date. Prepare necessary read permissions for recommendations, metrics, and costs.

### Step 2: Open the List

Go to **Governance & Administration → Cloud Advisor → Recommendations**, or search Cloud Advisor in the Console. Filter by Category, Service, and Status; if a Tenancy filter exists, confirm the target tenancy. See [Listing Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/list-recommendations.htm).

Start with Cost management and a familiar resource type. Check filters before concluding no optimization opportunities exist.

### Step 3: Record the Candidate

Record OCID, name, compartment, region, current configuration, and displayed recommendation. Confirm the owner. If OCID or application owner mismatches, clarify before acting.

### Step 4: Gather Evidence

Align infrastructure metrics and application metrics over the same time range. For Compute, check CPU, RAM, network, and relevant I/O; add latency, errors, and batch schedules.

If data is missing, state how to collect it and set a review milestone. One mid-month week may be insufficient to finalize sizing for a period-close workload.

### Step 5: Write the Plan

Describe target configuration or resource reclamation, blast radius, expected interruption, rollback triggers, and executor. With IaC, specify edits in the configuration source.

Cloud Advisor offers fix-it flows for supported recommendations; other cases follow the target service's standard procedure. Verify the selected resource set before acting. See [Implementing Cloud Advisor Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/implementing_cloud_advisor_recommendations.htm).

### Step 6: Verify

After the change, verify actual configuration, application health, and refreshed cost data. For asynchronous operations, inspect work requests, errors, and logs. See [Managing Work Requests](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/work-requests.htm).

The final outcome may be to implement, gather more data, or keep the configuration with rationale. If no relevant recommendation appears, record checked scope, filters, permissions, and telemetry; do not spin up billable resources solely to trigger recommendations.

## 9. Collect Recommendations with OCI CLI

Cloud Advisor uses the **oci optimizer** command group. The examples below run in PowerShell, assuming CLI authentication and proper IAM are configured. Commands are read-only; replace placeholders with real values.

### 9.1. List Recommendations in a Compartment

~~~powershell
$advisorRegion = '<home-region-identifier>'
$targetCompartmentOcid = '<compartment-ocid>'

$advisorScopeArgs = @(
    '--region', $advisorRegion,
    '--compartment-id', $targetCompartmentOcid,
    '--compartment-id-in-subtree', 'false',
    '--all'
)

oci optimizer recommendation-summary list @advisorScopeArgs --status PENDING
~~~

The example sets subtree to false to keep scope within the specified compartment. **--all** retrieves all pages. When traversing from root, use tenancy OCID and check subtree rules in the [CLI reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/recommendation-summary/list.html).

Use the tenancy's Advisor region when calling the CLI; record the resource's own region separately in the ticket. Where recommendations are aggregated and where resources run are two distinct facts.

### 9.2. Fetch Resource Actions

Take the recommendation ID from the previous output:

~~~powershell
$selectedRecommendationOcid = '<recommendation-ocid>'

$resourceActionArgs = $advisorScopeArgs + @(
    '--recommendation-id', $selectedRecommendationOcid,
    '--include-resource-metadata', 'true',
    '--status', 'PENDING'
)

oci optimizer resource-action-summary list @resourceActionArgs
~~~

Requesting additional metadata does not bypass IAM; permissions still govern returned fields. See [resource-action-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action-summary/list.html).

Read a specific resource action:

~~~powershell
$selectedResourceActionOcid = '<resource-action-ocid>'

$resourceActionDetailArgs = @(
    '--region', $advisorRegion,
    '--resource-action-id', $selectedResourceActionOcid,
    '--include-resource-metadata', 'true'
)

oci optimizer resource-action get @resourceActionDetailArgs
~~~

**--resource-action-id** takes the resource action OCID, not a VM or volume OCID. See [resource-action get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action/get.html).

### 9.3. Automate the Investigation Backlog

A periodic collector job can:

1. Paginate completely within authorized scope.
2. Normalize keys by tenancy, resource, and recommendation type.
3. Record observation timestamp and enrich owner and environment metadata.
4. Deduplicate records; group mutually exclusive options.
5. Update existing work items instead of creating duplicates on every scan.
6. Track new candidates, completed items, and items needing review.

The example below is an **illustrative internal record**, not an Oracle API schema:

~~~json
{
  "resourceOcid": "<resource-ocid>",
  "recommendationOcid": "<recommendation-ocid>",
  "resourceActionOcid": "<resource-action-ocid>",
  "owner": "payments-platform",
  "environment": "staging",
  "decision": "collect-more-evidence",
  "reason": "Missing metrics from the month-end test run",
  "estimatedMonthlySavings": null,
  "currency": null,
  "changeReference": null
}
~~~

A null value indicates unconfirmed. Substituting 0 misleads readers into thinking it was calculated and yielded zero benefit.

When extending toward automated execution, re-evaluate the resource right before acting, restrict eligible targets, limit concurrency, and halt if service metrics degrade. For data-deletion actions, require confirmed ownership and retention sign-off.

## 10. End-to-End Example: Downsizing a Java VM

All figures and prices below are **hypothetical for practicing evaluation**, not OCI pricing or Cloud Advisor default thresholds.

A staging application runs on an 8 OCPU, 64 GB RAM VM. The team plans to test 4 OCPUs, 32 GB RAM. Telemetry collected across a representative test cycle:

| Hypothetical evidence | Observation | Initial interpretation |
|---|---|---|
| Average CPU | 6% | Low baseline demand |
| P95 CPU | 12% | Most CPU samples are low |
| Peak CPU during batch | 45% | Must check batch deadline |
| Peak host RAM | 18 GB | Can test lower RAM with suitable headroom |
| Max JVM heap | 12 GB | Need RAM for off-heap, OS, and other processes |
| p95 latency | 120 ms | Pre-change application benchmark |
| Batch deadline | 30 minutes | Constraint to preserve |

You cannot use 6% average CPU to conclude an eightfold capacity cut is safe. Testing must verify latency, errors, and batch window on the target configuration.

Assuming identical architecture, identical load, and CPU capacity scaling roughly linearly with OCPUs:

~~~text
Expected average CPU ≈ 6% × 8 / 4 = 12%
Expected P95 CPU     ≈ 12% × 8 / 4 = 24%
Expected peak CPU    ≈ 45% × 8 / 4 = 90%
~~~

This is an approximate screening model built by the operator. The projected 90% peak signals the batch job needs close verification despite low baseline load. Actual runtime also depends on I/O, parallelism, scheduler, and GC.

The test plan should include:

- Saving current VM, JVM, and deployment source configurations.
- Running representative load and batch tests on the target configuration.
- Picking a maintenance window accommodating a reboot.
- Setting rollback triggers, such as batch exceeding 30 minutes or latency breaching agreed targets.
- Monitoring through a critical load cycle before updating IaC upon acceptance.

Suppose pre-change hypothetical cost is 240 currency units/month for Compute and 30 for storage. Post-change, Compute is 150 while storage stays unchanged:

~~~text
Pre-change total  = 240 + 30 = 270
Post-change total = 150 + 30 = 180
Expected savings  = 270 - 180 = 90
Share of total    = 90 / 270 × 100% ≈ 33.3%
~~~

Halving OCPUs does not automatically halve total cost. The example also excludes testing effort, deployment work, and payment commitment impacts.

If 4 OCPUs miss the batch window, the team can test an intermediate shape size, optimize the job, or keep the current configuration with rationale. The goal is an evidence-backed decision, not forced downsizing.

## 11. Verify Post-Change Effectiveness

### 11.1. Select a Comparable Baseline

Before/after comparison must account for day counts, load levels, and other changes. Total cost can rise when transaction volume grows even if cost per transaction fell.

One reconciliation approach:

~~~text
Normalized savings
  = Baseline cost scaled to post-change load and duration
    - Actual post-change cost over the same scope

Cost per 1,000 transactions
  = Cost of selected scope / Successful transactions × 1,000
~~~

Keep cost-scope selection and transaction counting consistent. For batch jobs, measure cost per completed run or per processed data unit while maintaining completion-time requirements.

### 11.2. Separate Reduced Usage from Reduced Cash Spend

Reducing usage can free capacity without proportionally lowering payable cash if commitments, fixed minimums, or contract pricing conditions apply.

Report separately:

- Capacity or usage reduced.
- Usage-based cost reduction per measured data.
- Impact on actual cash paid or commitment utilization.
- Implementation effort and ongoing maintenance costs incurred.

This reporting style prevents treating every Advisor estimate directly as cash saved on the invoice.

### 11.3. Completion Criteria

An optimization task is complete in the team's workflow when:

- Actual configuration matches the approved plan.
- Application metrics meet targets under representative load.
- Costs have been reconciled across a consistent scope.
- IaC source or deployment configuration is updated.
- Execution evidence, accountable owner, and review conditions are archived.

When deciding to keep a configuration unchanged, the deliverable is the verified rationale plus a re-evaluation milestone. Retaining necessary redundant capacity is also a valid capacity management outcome.

## 12. Common Scenarios

| Symptom | Possibilities to check | Next action |
|---|---|---|
| No recommendations shown | Filters, permissions, scope, resource type, insufficient data | Verify each condition and record scope |
| Metadata not visible | Permissions or hidden table columns | Check before assuming data is missing |
| Low CPU yet high latency | I/O wait, locks, GC, external services | Investigate bottlenecks before cutting capacity |
| Unattached volume holds needed data | DR, migration, or retention | Confirm owner and data handling plan |
| Change completed yet dashboard unchanged | Scan and sync cadence | Verify actual config; recheck after next scan |
| Old configuration reappears | IaC, instance pool, or CI/CD pipeline | Update deployment source of truth |
| Projected total savings look too large | Double counting, summing alternatives, mixed periods | Normalize and pick one option per cost item |
| Difficult to scale back up | Capacity or limits not prepared | Complete capacity and recovery plan |

## 13. Key Takeaways

Cloud Advisor helps locate optimization candidates in OCI. Decisions require an accountable owner, representative telemetry, and clear service targets. Low utilization must be interpreted alongside redundancy, periodic jobs, data value, and scale-back feasibility.

An effective workflow connects **discovery → verification → controlled execution → outcome measurement**. Claim realized savings only with evidence of both configuration changes and cost impact; keep source configurations aligned so benefits persist across future deployments.
