# Recommender and Evaluating Optimization Proposals

When an organization runs many Google Cloud services, infrastructure costs and configurations change continuously: VMs end up with excess CPU, disks sit detached from VMs, GKE clusters run unoptimized workloads, BigQuery tables scan too much data, or service accounts hold unnecessary permissions. Reviewing every resource manually is labor-intensive, yet **blindly applying every automated recommendation** can cause outages, data loss, or security violations.

**Google Cloud Recommender** generates insights and recommendations from resource utilization, telemetry, and service-specific rules. These suggestions appear in Active Assist, FinOps hub, optimization pages, or directly inside service consoles. Operations teams must turn them into verified decisions: weigh benefits, understand SLO impacts, check financial constraints, execute under change management, and measure actual outcomes.

This lesson focuses on **reading and evaluating optimization proposals** across GCP infrastructure—from Compute Engine, Cloud SQL, GKE, Cloud Run, and Cloud Storage to BigQuery and IAM. The goal is not running deletion commands as fast as possible, but building a traceable, safe, and measurable FinOps and SRE feedback loop.

## 1. What Recommender Is and What It Is Not

Recommender is a service that generates optimization suggestions for supported Google Cloud resource types and usage patterns. Each recommender has a distinct ID, support scope, and input dataset suited to the service being analyzed.

A recommendation may suggest:

- Changing a Compute Engine VM's machine type based on utilization trends.
- Reviewing whether to stop or delete resources identified as idle.
- Adjusting Cloud SQL configuration when provisioning mismatches load.
- Improving resource allocation for GKE workloads.
- Evaluating partitioning or clustering for BigQuery tables.
- Tightening an IAM policy to remove unused permissions.
- Considering commitment discount models when steady consumption exists.

**A recommendation is not a mandatory command.** A low-CPU VM might be a DR standby, a detached disk might hold an active recovery copy, and a rarely used IAM role might be critical for rare incident recovery. Every proposal must be evaluated in business and architectural context.

| Term | Meaning |
|---|---|
| Recommender | Service type or rule engine generating suggestions for a resource category |
| Insight | Observed findings explaining current state or usage trends |
| Recommendation | Specific optimization action proposed from data/insights |
| Resource | Affected target such as a VM, disk, table, service, or IAM policy |
| Impact | Expected cost, performance, security, or other impact |
| Operation group | Set of operations describing how to enact the suggested change |
| State | Tracking state showing where the team is in handling the proposal |
| Etag | Optimistic concurrency token checked when updating recommendation state |

Recommender does not replace Cloud Monitoring, Cloud Billing, quota management, load testing, backups, or change approvals. It supplies decision inputs; other systems and processes validate those decisions.

## 2. Where Recommendations Appear on Google Cloud

Recommendation data surfaces across several interfaces.

| Surface | Typical Users | Purpose |
|---|---|---|
| Recommender API and gcloud | Platform/SRE/automation | Fetch structured proposals, filter, and update states |
| Active Assist in Google Cloud console | Project administrators | Browse proposals and inspect impact details |
| FinOps hub in Cloud Billing | FinOps/billing owners | Aggregate cost opportunities and track optimization progress |
| Optimization pages in Cloud Hub | Developers and platform teams | Discover workload-relevant recommendations |
| Individual product config pages | Service owners | View suggestions directly alongside the resource |

Do not assume every recommender appears in every UI. Some recommendation types are scoped to projects, billing accounts, folders, or organizations; others publish at regional, zonal, or `global` locations.

### Distinguishing FinOps Hub and the Recommender API

FinOps hub emphasizes a billing-account-wide cost optimization view and can deduplicate overlapping opportunities when aggregating. The Recommender API returns recommendations from each individual recommender. Therefore, **never mechanically sum estimated savings across every API row and treat it as one net cost opportunity**.

The same VM might simultaneously receive a rightsizing recommendation and appear inside a committed use discount recommendation. Those two benefits overlap and do not simply add together.

## 3. How Insights and Recommendations Relate

An **Insight** describes observed facts—such as low resource utilization, minimal activity, or risky configuration. A **Recommendation** translates those signals into a concrete proposed change.

~~~mermaid
flowchart LR
    A[Usage and configuration signals] --> B[Recommender analysis]
    B --> C[Insight]
    B --> D[Recommendation]
    C --> E[Human impact review]
    D --> E
    E --> F{Safe and valuable?}
    F -->|Yes| G[Plan change and approval]
    F -->|Not yet| H[Defer or dismiss with reason]
    G --> I[Apply in controlled window]
    I --> J[Measure outcome and close loop]
~~~

Example:

- Insight: an instance consistently shows low CPU over the observation window.
- Recommendation: consider a smaller machine type.
- Team-supplied context: this host runs month-end batch spikes.
- Decision: do not rightsize immediately; run load tests and cross-check batch schedules first.

Claims about usage or configuration fit must be verified. Never infer that **idle** equals **unowned** or **safe to delete**.

## 4. Structure and Fields of a Recommendation

An API recommendation typically includes these fields:

| Field | Purpose |
|---|---|
| `name` | Recommendation resource name containing project, location, recommender ID, and recommendation ID |
| `description` | Description of the proposed action |
| `recommenderSubtype` | Specific subtype within a recommender |
| `primaryImpact` | Primary impact, such as cost or performance |
| `additionalImpact` | Secondary impacts if provided by the recommender |
| `content.operationGroups` | Operations describing the proposed resource changes |
| `stateInfo.state` | Processing state |
| `etag` | Token preventing updates against stale versions |
| `priority` | Recommender-assigned priority, when available |
| `lastRefreshTime` | Timestamp when recommendation data was last refreshed |
| `insightReference` | Reference to related insights, when available |

The conceptual resource name format:

~~~text
projects/PROJECT_ID/locations/LOCATION/
  recommenders/RECOMMENDER_ID/recommendations/RECOMMENDATION_ID
~~~

The string above is line-wrapped for readability. The actual resource name is a single continuous string without line breaks.

### Operation Groups Are Proposals, Not Unconditionally Safe Scripts

An operation may represent `test`, `add`, `replace`, `remove`, or other actions on a resource/configuration. Operations describe the target state suggested by the system, yet teams must verify:

- The exact target resource and environment impacted.
- Before/after properties.
- Dependent operations or `test` preconditions.
- Configurations managed by Terraform or other IaC tooling.
- Freshness of the underlying recommendation data.

Never copy an operation and run it blindly in production. An operation valid when generated may become inappropriate after workloads shift.

## 5. Recommendation State Lifecycle

Recommender supports states to track handling progress:

| State | Operational Meaning |
|---|---|
| `ACTIVE` | Suggestion is valid in the system and not yet acted on by the team |
| `CLAIMED` | A person or workflow has taken ownership to handle the suggestion |
| `SUCCEEDED` | Records that the proposal was successfully implemented |
| `FAILED` | Records that applying the proposal failed |
| `DISMISSED` | Team chose not to implement the suggestion at this time |

An `ACTIVE` recommendation may be updated by Google as resource conditions change. The `CLAIMED` state generally freezes recommendation contents for an active workflow. Once implemented, record the explicit outcome rather than leaving it `CLAIMED` indefinitely.

~~~mermaid
flowchart TD
    A[ACTIVE] --> B[CLAIMED]
    A --> C[DISMISSED]
    B --> D[SUCCEEDED]
    B --> E[FAILED]
    C --> F[Re-evaluate if conditions change]
    F --> A
    E --> G[Analyze and retry under change control]
~~~

This diagram is a reference operational flow and does not depict every valid state transition in the Recommender API.

### Etags and Concurrent Edits

When updating state via CLI/API, pass the `etag` from the most recent read of the recommendation. If someone else modified the recommendation or its contents refreshed, requests using a stale etag will be rejected.

Never fabricate or force an etag. Re-fetch the latest recommendation, re-review it, and perform the update with proper permissions.

**Marking `SUCCEEDED` does not automatically prove the resource was optimized.** It is a recommendation-tracking state; the team must still verify actual resource state and post-change billing.

## 6. Common Recommendation Categories in FinOps and SRE

| Category | Examples | Risks to Weigh |
|---|---|---|
| Compute Engine | Machine type rightsizing, idle VMs | Disruption, peak loads, standby/DR |
| Disks, IPs, and reservations | Unattached disks, unused IPs, excess reservations | Data loss or broken dependencies |
| Cloud SQL | Idle, overprovisioned, underprovisioned, reliability | Capacity, failover, backups, connections |
| GKE | Workload/cluster diagnostics, under/overprovisioning | Requests/limits, autoscaling, scheduling |
| Cloud Run | CPU allocation or security suggestions | Billing model, request latency, background tasks |
| BigQuery | Partitioning/clustering, slot/capacity | Shifting workloads, SQL scans, slot commitments |
| Cloud Storage | Soft delete and storage configuration tuning | Object recoverability, retention, cost |
| IAM | Removing excess permissions | Emergency access, rare jobs, service identities |
| CUD | Resource usage commitments | Term lock-in and underutilization risk |
| Reliability/quotas | HA, disk capacity, service limits | Reliability gains may raise spend |

Some recommendations focus on cost reduction; others improve security or performance and **may even increase the bill**. Prioritize by system objectives rather than dollar savings alone.

Supported recommenders and scopes evolve over time. Always verify recommender IDs in Google Cloud documentation for the service under review.

## 7. Access Permissions and Preparing the Recommender API

Before using `gcloud` or the API:

1. Select the project or resource scope to review.
2. Confirm the Recommender API is enabled on the appropriate project.
3. Grant IAM permissions to reviewers.
4. Identify the exact recommender ID and location.
5. Check project quotas if required by API clients.

Enable the API on a test or authorized project:

~~~bash
gcloud services enable recommender.googleapis.com \
  --project="PROJECT_ID"
~~~

Each recommender has dedicated permissions and roles, such as `recommender.*.list`, `recommender.*.get`, and `recommender.*.update` corresponding to its recommendation type. Never grant broad admin roles merely to read recommendations.

### Separation of Duties

| Workflow Role | Recommended Access |
|---|---|
| FinOps analyst | Read costs and recommendations; cannot modify resources |
| Resource owner/SRE | Review performance, reliability, and blast radius |
| Approver | Approve per change management policy |
| Deployment identity | Modify only target resources after approval |
| Auditor | Read review history, change requests, and outcomes |

Separate **permission to update recommendation state** from **permission to modify GCP resources**. Marking `SUCCEEDED` is not equivalent to permission to resize a VM or alter IAM policies.

## 8. Inspecting Recommendations with gcloud

Example listing Compute Engine VM machine type recommendations in a zone:

~~~bash
gcloud recommender recommendations list \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.MachineTypeRecommender" \
  --format="json"
~~~

This command is read-only and does not modify any VM. Substitute your real project, zone, and recommender ID. A project may return zero recommendations at check time; an empty list does not prove the entire infrastructure is optimal.

Check idle VMs in the same zone:

~~~bash
gcloud recommender recommendations list \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.IdleResourceRecommender" \
  --format="table(name,description,stateInfo.state)"
~~~

Inspect a specific recommendation in detail:

~~~bash
gcloud recommender recommendations describe "RECOMMENDATION_ID" \
  --project="PROJECT_ID" \
  --location="asia-southeast1-a" \
  --recommender="google.compute.instance.MachineTypeRecommender" \
  --format="json"
~~~

Take `RECOMMENDATION_ID` from the list output; never invent it. Some recommenders use `global` or a region instead of a zone; pass the location required by that recommender.

### Viewing Insights

Insights can be accessed via the Recommender API or Google Cloud console using the right insight type ID. Do not assume an insight type ID matches a recommender ID. For automation, query `projects/PROJECT_ID/locations/LOCATION/insightTypes/INSIGHT_TYPE_ID/insights` on the corresponding API.

### Caution When Exporting JSON

Recommendation payloads can contain project IDs, resource names, infrastructure topologies, or IAM policy details. Never publish raw JSON to public repositories. Apply proper access controls, retention, and redaction on reports.

## 9. Reading Impact and Estimating Benefits

A recommendation can carry primary impact categories such as:

- **COST:** projected spend increase or decrease.
- **PERFORMANCE:** capacity or performance changes.
- **SECURITY:** security posture improvements.
- **MANAGEABILITY:** reduction in manual operational toil.
- **SUSTAINABILITY:** estimated emissions impact per supported models.

Not every recommendation carries all impact types. A critical security recommendation cannot be dismissed simply because it lacks an estimated savings field.

### Reading Cost Projections

When reviewing a savings estimate, ask:

1. Over what period is it estimated: month, year, or another duration?
2. Does it use list prices or custom contract prices?
3. Which historical usage window does it analyze?
4. Are snapshot, backup, migration, and downtime costs included?
5. Do existing CUDs, credits, or other discounts affect realized savings?
6. Will the change introduce new egress, networking, or support costs?

Google Cloud documentation states that savings calculations in recommendations are meant for **comparison and prioritization**; figures may reflect list or custom pricing depending on billing viewer permissions, and do not necessarily reflect all credits or discounts.

### Do Not Double-Count Recommendations

If a VM shows 60 USD/month potential savings from rightsizing plus another commitment discount recommendation on the same compute footprint, total savings from applying both will not default to 120 USD/month. Model the sequence of changes and the remaining discount-eligible usage.

## 10. Financial Benefit Evaluation Model

A simple way to model net benefit for a proposal:

\[
\text{Net Monthly Benefit}
= \text{Avoided Cost}
- \text{Additional Ongoing Cost}
\]

If there is a one-time implementation cost:

\[
\text{Simple Payback (months)}
= \frac{\text{One-time Implementation Cost}}
       {\text{Net Monthly Benefit}}
\]

These formulas are basic governance aids and omit time value of money, taxes, workload growth, or contract discounts. If net monthly benefit is zero or negative, simple payback is meaningless under this formula.

Illustrative example:

- A VM rightsizing proposal nominally cuts ~140 USD/month.
- Extra backups/snapshots and monitoring add 15 USD/month.
- Engineering implementation, testing, and runbook updates translate to 200 USD one-time.
- Hypothetical net benefit: 125 USD/month; simple payback roughly 1.6 months.

Yet if the VM must be upgraded again at month-end for batch loads, rollback and disruption costs can wipe out the gain. Never conclude from simple arithmetic alone.

### Distinguishing Projected vs. Realized Savings

| Concept | Meaning |
|---|---|
| Potential saving | Pre-implementation estimate |
| Approved opportunity | Proposal reviewed and authorized for rollout |
| Implemented change | Infrastructure actually modified |
| Realized saving | Post-change spend reduction relative to a normalized baseline |
| Avoided future cost | Planned cost increase prevented by the action |

In FinOps reporting, never sum potential savings and realized savings as though they were two independent pools of money.

## 11. Technical Risks: Performance, Reliability, and Data

An optimization that looks great on paper can break SLOs or RPO/RTO. Validate against real workloads.

### Performance Questions

- How much p95/p99 latency headroom currently exists?
- Average CPU may be low, but what is the period-end peak?
- Do steady memory usage and working sets fit the smaller shape?
- Are network throughput, IOPS, disk latency, or concurrency bottlenecks?
- Can autoscaling absorb peaks if resource requests drop?
- Are there weekly or monthly batch/cron jobs?

### Reliability Questions

- Is the resource primary, standby, DR, backup, or a coordinator node?
- After deletion/resizing, do failover and recovery paths still work?
- Are there HA, placement, quota, or capacity reservation constraints?
- What is the expected downtime and rollback trigger?
- How are replication, cluster scheduling, and connection pools affected?

### Data Questions

- Does an "idle" disk hold logical backups or needed recovery data?
- Do object lifecycles or soft delete meet retention and legal rules?
- Does the database have verified backups/PITR?
- Does the resource have dependencies managed outside Terraform?

If telemetry is missing or owners have not confirmed, choose `DEFER` instead of rushing to apply.

## 12. Building an Explainable Prioritization Matrix

Teams should apply consistent scoring across all recommendations while enforcing **hard stops** for changes risking data loss, missing backups, or lacking clear ownership.

One scoring framework:

| Axis | Question | Suggested Scale |
|---|---|---|
| Benefit | Are savings or risk reductions meaningful? | 1–5 |
| Data confidence | Is the proposal backed by representative telemetry? | 1–5 |
| Low risk | Are SLOs, data safety, and rollback easy to preserve? | 1–5, higher means safer |
| Low effort | Are steps and dependencies minimal? | 1–5, higher means easier |
| Urgency | Is there a security or quota deadline? | 1–5 |

Example internal weighted score:

\[
\text{Priority Score}
= 0.30B + 0.20C + 0.25R + 0.15E + 0.10U
\]

Where `B` is benefit, `C` is confidence, `R` is safety (inverted risk), `E` is ease, and `U` is urgency. Weights are illustrative only; organizations should tune them to governance goals.

**Never let a composite score override mandatory gates.** A disk deletion proposal with high savings but unverified data must be blocked rather than greenlit just because its weighted average is high.

### Sample Decision Matrix

| Proposal | Illustrative Monthly Savings | Risk | Confidence | Initial Decision |
|---|---:|---|---|---|
| Delete unattached IP | 15 USD | Low after dependency check | High | Candidate |
| Rightsize month-end batch VM | 140 USD | Medium/high | Low if missing peak data | Defer |
| Downsize Cloud SQL tier | 250 USD | High on production DB | Medium | Deep review and load test |
| Remove broad unused IAM role | No direct savings | Could break incident access | Medium | Security review |

Numbers are learning examples, not real GCP pricing or recommendations.

## 13. Evaluating VM Rightsizing

The VM machine type recommender is an intuitive optimization example, yet also easy to misapply if you read only average CPU.

### Technical Checklist

1. Identify VM, zone, machine type, attached disks, labels, and owner.
2. Inspect CPU/memory utilization across multiple days and peak windows.
3. Check periodic workloads: month-end batches, backups, reports, or incident drills.
4. Classify VM role: stateless, stateful, singleton, MIG, or standby.
5. Check permissions, capacity/quotas, reservations, and CUDs.
6. Estimate downtime or restarts required to change machine types.
7. Test on staging or a canary VM with representative behavior.
8. Measure latency, throughput, error rate, CPU/memory, and rollback readiness.

Never rightsize solely because average CPU is low. A Java app may need memory to prevent excessive garbage collection or need CPU bursts for a few minutes.

### Strong Candidates to Prioritize

- Dev VMs with non-continuous usage and clear start/stop schedules.
- Multi-replica stateless VMs supporting canary rollouts.
- Steady-metric workloads with ample headroom and minimal hardware coupling.
- Adjustments that do not strand reserved capacity or contractual commitments.

If the VM is managed by Terraform, update the IaC source so the next apply does not revert the configuration.

## 14. Evaluating Idle VMs, Disks, IPs, and Reservations

A resource flagged as "unused" under recommender rules can still hold standby capacity or valuable data.

### Idle VMs

- Check whether the instance belongs to standby/DR runbooks.
- Inspect access logs, job schedules, network traffic, and owner accountability.
- Prove no external dependencies, DNS records, static IPs, or cron jobs remain.
- Consider stopping before deleting if processes and costs allow.
- Save configuration, verify disks, snapshots, and recovery steps before deletion.

### Persistent Disks

A detached disk may hold data needed for recovery. Before deleting:

1. Confirm it is not attached to any VM, GKE workload, or other service.
2. Inspect labels, owner, and retention rationale.
3. Verify whether data has retention or legal hold obligations.
4. If backup is approved, create a snapshot and **test restoring** in an appropriate scope.
5. Price snapshot storage and retention; never assume snapshots are always cheaper than disks.
6. Delete only after approval matching the exact resource ID.

### Static IPs and Reservations

- Unattached IPs may be reserved for cutovers, allowlists, or DR.
- Unused reservations may guarantee capacity for batches or peak events.
- Review runbooks, rollout calendars, and dependent contracts before releasing.

Idle recommendations rely on finite observation windows. A workload running once per quarter may not appear during that window.

## 15. Cloud SQL: Optimization Must Prioritize Data and SLOs

Cloud SQL provides recommendations covering idle, overprovisioned, underprovisioned, reliability, and security configurations. Database decisions require greater caution than stateless VMs.

### Overprovisioned Instances

When tier downsizing is suggested, check:

- CPU, memory, and working set across peak windows.
- Connection counts, app pool sizes, and database connection limits.
- Query latency, lock waits, and long-running transactions.
- Disk I/O, storage auto-increase, and replication lag.
- HA/standby configuration, backups/PITR, and maintenance settings.
- Whether resizing triggers a restart or downtime.

Run load tests with representative read/write ratios and datasets rather than relying on average CPU.

### Idle Instances

A zero-traffic database may be a recovery environment, upcoming staging environment, or audit archive. Never delete an instance without verifying backups and retention. When decommissioning, follow archive/restore procedures and confirm all downstream consumers have migrated away.

### Underprovisioned and Reliability

A recommendation advising **adding** resources or enabling HA may raise the bill while improving reliability. For strict-SLO systems, that spend increase can deliver far greater business value than minor cost cuts elsewhere.

## 16. GKE and Cloud Run: Understand Autoscaling Before Optimizing

### GKE

GKE workload or cluster diagnostics can highlight mismatched resource requests/limits and utilization.

When lowering CPU/memory requests:

- Inspect percentile and peak usage, not just averages.
- Check CPU throttling, OOMKilled events, restarts, and Pod readiness.
- Cross-check HPA targets, replica counts, PodDisruptionBudgets, and topology.
- Verify cluster autoscaler has node capacity headroom when needed.
- Identify where cost actually drops: node counts, reservations, waste, or merely utilization chart percentages.

Lowering Pod CPU requests does not necessarily lower your bill if node count stays unchanged. Conversely, setting requests too low can trigger erratic HPA scaling and scheduling issues. Compare at the **cluster + workload** level, not a single Pod.

### Cloud Run

Suggestions around CPU allocation or runtime settings must be read in context:

- Does the workload only serve requests or also run background tasks?
- How are concurrency and min/max instances configured?
- What are instance startup times and p95/p99 latencies under load?
- Which billing model is active, and what is actual billed usage?
- Do other jobs or services share the same downstream dependencies?

Never assume always-allocated CPU is always pricier or always cheaper. Cost depends on request patterns, idle gaps, and settings; run small comparative tests.

## 17. BigQuery and Cloud Storage: Optimize Both Queries and Data

### BigQuery Partitioning and Clustering

When receiving a table partitioning/clustering recommendation:

1. Inspect real query patterns: WHERE, JOIN, GROUP BY, and filtered columns.
2. Check table size, bytes processed, slot usage, and query latency.
3. Check data freshness, write patterns, and late-arriving events.
4. Assess whether schema/table changes affect BI contracts.
5. Pilot on a copy or staging table with representative data.
6. Compare query cost and latency before and after.

Partition pruning works only when queries filter on the partition key. Partitioning a table while every report still runs `SELECT *` with no date filter yields minimal savings.

### Cloud Storage Soft Delete and Retention

Suggestions to change soft delete settings affect the balance between cost and recoverability. Before applying, verify:

- Accidental deletion recovery requirements.
- Retention policies, Object Versioning, and compliance mandates.
- Monthly deleted/overwritten volume and storage fees.
- Backup workflows or pipelines generating temporary objects.
- RPO/RTO and restore drill procedures.

Never disable soft delete or retention purely to trim bills when data policies mandate recoverability. Conversely, enabling broad protection uniformly across temporary-file buckets inflates costs unnecessarily.

### Choosing Storage and Query Strategies

Recommender is one input. The broader design spans storage classes, lifecycles, BigQuery query design, materialized views, and reservation strategy. Optimize end-to-end from source data to consuming tools rather than isolated individual resources.

## 18. IAM Recommendations: Saving Risk, Not Just Dollars

The IAM recommender can suggest removing roles or replacing overly broad roles with narrower permissions. This primarily improves security posture without direct financial savings.

### Review Workflow

1. Identify principal, role, scope, target resource, and owner.
2. Inspect actually exercised permissions and supporting insights.
3. Check infrequent workflows: incident response, quarterly jobs, DR, deployments/migrations.
4. Inspect IAM conditions, inheritance, and service account impersonation.
5. If needed, craft custom roles or tighter predefined roles covering real use cases.
6. Test in sandbox/staging and run integration tests.
7. Roll out under change control while monitoring for `PERMISSION_DENIED`.
8. Keep a fast revert path ready if critical workflows break.

A role unused during the observation window may still be vital for rare operational tasks. Never turn permission recommendations into bulk unverified IAM deletions.

### Principle of Least Privilege

The goal is not minimizing role counts regardless of fallout, but granting **just enough permissions, at the narrowest scope, for the right duration**.

APIs do not always capture every permission usage signal. Pair recommender findings with audit logs, runbooks, and dependency inventories.

## 19. Committed Use Discounts and Overlapping Benefits

Commitment recommendations can cut future usage rates, yet bind you to contract terms and durations. For CUDs, model:

- Steady baseline demand across the entire commitment term.
- Workloads planned to move to Cloud Run, GKE, or another region.
- Planned machine type changes and rightsizing.
- Eligible resource types and usage scopes.
- Existing commitments and attribution rules.
- Upside/downside load scenarios during the term.

Never buy commitments simply because a few recent weeks looked steady. Separate optimization campaigns can shrink consumption and leave CUDs underutilized.

### Sequencing

Generally:

1. Eliminate verified waste and perform safe rightsizing.
2. Re-assess remaining post-optimization compute demand.
3. Build high-confidence usage forecasts.
4. Only then size commitments aligned with contractual risk.

This is a decision principle, not a replacement for official billing tools or contract terms.

## 20. Safe Recommendation Implementation Workflow

A standard loop:

~~~mermaid
flowchart TD
    A[Collect recommendations] --> B[Assign owner and classify]
    B --> C[Check freshness and context]
    C --> D[Estimate benefit and risk]
    D --> E{Guardrails satisfied?}
    E -->|No| F[Defer or dismiss with evidence]
    E -->|Yes| G[Design change and rollback]
    G --> H[Change approval]
    H --> I[Canary or controlled rollout]
    I --> J[Validate service and cost]
    J --> K{Outcome verified?}
    K -->|Yes| L[Record SUCCEEDED and realized effect]
    K -->|No| M[Rollback and investigate]
    M --> N[Record FAILED or next action]
~~~

### Before Applying

- Snapshot current resource state and configuration.
- Verify the recommendation is fresh and `test` operations still pass.
- Confirm owner and risk-appropriate approval.
- Ensure backups/snapshots or restore plans exist when data is involved.
- Define SLOs, RTO, rollback triggers, and monitoring.
- If IaC manages the resource, update Terraform/manifests and review `plan`/diffs first.
- Avoid stacking multiple simultaneous changes on shared dependencies.

### During Rollout

- Prefer canaries or a small batch of resources.
- Log change ID, commit SHA, approver, and timestamp.
- Watch CPU, memory, throughput, request latency, error rates, and dependencies.
- Abort or roll back immediately if pre-defined thresholds trip.

### After Rollout

- Verify resources reached the expected state.
- Compare pre- and post-change SLIs/SLOs under comparable load.
- Measure spend in billing data once sufficient reconciliation data arrives.
- Record results and update recommendation state.
- Open follow-up items if realized gains disappoint or regressions appear.

Link recommendation state to change tickets so multiple engineers do not act on the same recommendation concurrently.

## 21. Managing State with gcloud and Audit Trails

After review and decision-making, you can use these commands:

~~~bash
gcloud recommender recommendations mark-claimed --help
gcloud recommender recommendations mark-dismissed --help
gcloud recommender recommendations mark-succeeded --help
gcloud recommender recommendations mark-failed --help
~~~

These commands only print help documentation; they do not modify any state.

When actually transitioning state, commands require the recommendation ID, `--project`, `--location`, `--recommender`, `--etag`, and optionally `--state-metadata`. The example below is a **syntax template** for use only after approval:

~~~bash
gcloud recommender recommendations mark-claimed "RECOMMENDATION_ID" \
  --project="PROJECT_ID" \
  --location="ZONE_OR_REGION" \
  --recommender="RECOMMENDER_ID" \
  --etag="ETAG_FROM_LAST_READ" \
  --state-metadata="ticket=CHANGE_1234"
~~~

Replace `ETAG_FROM_LAST_READ` with the real value formatted as expected by the CLI; never paste placeholders into live environments. After claiming, re-read the recommendation to fetch the new etag before subsequent state transitions.

**`mark-claimed` does not modify VMs, disks, or IAM.** Actual resource changes happen through service tools or IaC under your normal change workflow.

### Dismissing Does Not Mean Deleting Evidence

If you decide not to apply a recommendation because a host is a DR standby, dismiss it per process with a clear reason. The recommendation may regenerate or update if conditions change. Keep records in your ticketing system to explain past decisions later.

## 22. Measuring Realized Savings and Detecting Regressions

Post-change costs only make sense against a fair baseline.

### Measurement Workflow

1. Save the baseline: spend, usage, config, SLOs, and observation period.
2. Log change timestamps and concurrent events.
3. Wait long enough for billing data and traffic to stabilize.
4. Compare per usage unit or transaction, not raw dollars alone.
5. Normalize for confounding factors: traffic growth, region shifts, price changes, CUDs, and credits.
6. Monitor for regressions across at least one representative usage cycle.
7. Summarize verified realized savings alongside implementation costs.

For example, a service cuts VM bills by 20% while throughput drops 25% and p99 doubles. That is not a successful optimization if SLOs are violated.

### KPIs for a Recommender Program

| KPI | Meaning |
|---|---|
| Recommendations reviewed | Number of proposals evaluated per period |
| Acceptance rate | Share of proposals approved for rollout |
| Time to review | Elapsed time from appearance to decision |
| Realized net savings | Verified net cost reduction |
| SLO regressions | Number of optimizations causing SLO breaches |
| Reverted changes | Number of changes rolled back |
| Stale recommendations | Old proposals lacking decisions |
| Coverage by owner | Share of proposals with an assigned owner |

Never game acceptance rate by rubber-stamping unsuitable recommendations. Real value comes from verified savings, lower risk, or higher efficiency with service quality intact.

## 23. Scaling Automation Across Many Projects

When managing dozens or hundreds of projects, inspecting every recommender manually becomes slow. Build a scheduled workflow:

1. Collect recommendations via the API across supported recommender IDs and locations.
2. Normalize resource, project, owner, labels, impact, state, and last refresh time.
3. Store time-bounded snapshots in a secured data store.
4. Classify into cost/performance/security/reliability tracks.
5. Deduplicate overlapping opportunities on the same resource.
6. File prioritized tickets for owners.
7. Sync change outcomes, approval states, and realized savings back to dashboards.

### BigQuery Export

Google Cloud supports exporting certain insights and recommendations to BigQuery for large-scale analysis. **Not every recommender falls under the same export scope**, so check supported lists before building aggregate reports.

In BigQuery, build dashboards tracking recommendation counts by project, type, age, priority, and owner. Never make export tables public if they contain resource names, IAM details, or sensitive spend figures.

### Risk-Tiered Automation

| Recommendation Type | Reference Automation Policy |
|---|---|
| Read-only reporting | Automated on schedule |
| Low-risk labels or metadata | May auto-apply with guardrails if approved |
| Production VM/Cloud SQL rightsizing | Human review, change window, and rollback |
| Deleting disks, buckets, databases, or projects | Independent approval, backup/retention checks |
| IAM policy edits | Security owner review and testing |
| CUDs/financial commitments | FinOps/billing approval with forecast validation |

Never grant an automated job organization-wide Owner rights to execute every operation group returned by the API. Scope permissions per project and change class with rate limits, audit logs, and kill switches.

## 24. Hands-On Scenario: Optimizing an Orders Platform on GCP

Suppose a platform includes:

- `orders-api` running on Cloud Run.
- A worker VM processing periodic reports.
- Cloud SQL storing orders.
- GKE running event consumers.
- BigQuery storing analytics data.
- Cloud Storage holding report files and backups.

A review cycle surfaces four illustrative recommendations:

| ID | Proposal | Est. Monthly Savings | Signal |
|---|---|---:|---|
| REC-01 | Rightsize worker VM | 140 USD | Low average CPU |
| REC-02 | Review deleting unattached disk | 35 USD | Disk detached long-term |
| REC-03 | Downsize Cloud SQL tier | 250 USD | Relatively low utilization |
| REC-04 | Replace broad IAM role | Not directly quantified | Infrequently used permissions |

### Step 1 — Collect and Verify

Query the Recommender API via `gcloud` at the right project/location, recording ID, recommender, resource, timestamp, etag, and impact. Cross-check Cloud Monitoring, Billing, Asset Inventory, and Terraform state per granted permissions.

### Step 2 — Consult Owners

- Does the worker VM run large jobs on the last day of each month?
- Is the detached disk a retained recovery volume?
- What are Cloud SQL's peak transaction volumes and HA requirements?
- Is the IAM role needed for incident response or migrations?

### Step 3 — Formulate Plans

- REC-01: defer until month-end peak batch telemetry is captured; then test a smaller shape in staging.
- REC-02: confirm data owner, create a tested backup/snapshot, and delete only once all dependencies are cleared.
- REC-03: measure connections, query latency, and CPU under load tests; prepare rollback and a maintenance window.
- REC-04: swap to a narrower role after verifying rare jobs and securing security approval.

### Step 4 — Measure and Conclude

For instance, REC-01 is deployed after staging passes SLOs: save baseline cost and before/after p95 job duration; mark succeeded only after the real change runs across a full batch cycle. REC-03 stays in review if peak telemetry is missing, even though its estimated savings are larger.

### Step 5 — Update Backlog

Each recommendation tracks:

~~~text
recommendation_id: REC-01
resource_owner: data-platform-team
decision: approved-after-validation
risk: medium
change_id: CHG-2026-0119
baseline_window: previous representative batch cycle
expected_savings_monthly: 140 USD (illustrative)
actual_savings_monthly: pending verification
rollback: restore previous machine type through IaC
status: awaiting post-change measurement
~~~

This is an illustrative internal operational record, not a Recommender API JSON schema.

## 25. Common Evaluation Pitfalls

| Anti-Pattern | Why It Is Dangerous | Remedy |
|---|---|---|
| Treating savings estimates as guaranteed cash | Ignores discounts, credits, and usage shifts | Measure realized net savings |
| Auto-applying all `ACTIVE` suggestions | Can disrupt services or lose data | Risk-classify and require approvals |
| Looking only at average CPU | Misses peaks or memory pressure | Use percentiles, batch windows, and load tests |
| Deleting "idle" disks/IPs without asking owners | Can break recovery or dependencies | Check inventory, backups, and runbooks |
| Resizing VMs without updating Terraform | Next IaC apply reverts the change | Update source-of-truth and review plans |
| Deleting IAM roles from short windows | Periodic/DR jobs lose access | Audit rare operational workflows |
| Summing savings across overlapping proposals | Inflates total opportunity | Deduplicate by resource and financial model |
| Treating CLI `mark-succeeded` as proof of success | Does not verify resource or billing | Reconcile post-change metrics and billing |
| Ignoring `etag` and refresh times | Acting on stale recommendations | Re-fetch and re-review |
| Ignoring SLOs after optimization | Saves money while degrading quality | Guardrails and rollback triggers |
| Ignoring IAM/organization policies | Changes may violate security rules | Security reviews and compliance gates |
| Giving automation one super-admin identity | Huge blast radius | Least privilege and strict scope caps |

## 26. Evaluation and Implementation Checklist

### Reading Proposals

- [ ] Project, resource, recommender ID, and location match.
- [ ] Description, subtype, impact, and operation groups reviewed.
- [ ] `lastRefreshTime` and `etag` are current.
- [ ] Cross-checked resource owner, labels, and architecture.
- [ ] Insights are not conflated with deployment decisions.
- [ ] Supporting telemetry exists (Monitoring/Billing/Logs).

### Financial Evaluation

- [ ] Price basis (list/custom), duration, and currency are clear.
- [ ] CUDs/credits/discounts and overlaps with other suggestions reviewed.
- [ ] Implementation, backup, monitoring, and egress costs factored in.
- [ ] Post-change baseline defined to measure realized savings.
- [ ] Expected and realized savings are not double-counted.

### Technical Evaluation

- [ ] p95/p99, peak CPU/memory, and dependencies checked.
- [ ] SLOs, HA, DR, RPO/RTO, and quotas checked.
- [ ] Backup/restore drills planned when touching data.
- [ ] Test/canary plan, rollback, and change window ready.
- [ ] IAM/security owner sign-off secured for permission edits.
- [ ] IaC configs updated prior to or alongside rollout.

### Post-Change

- [ ] Resource is in expected state and APIs/workloads run cleanly.
- [ ] SLIs/SLOs remain within approved bounds.
- [ ] Sufficient billing data elapsed for reconciliation.
- [ ] Recommendation state and ticket updated accurately.
- [ ] Realized savings and newly incurred costs reported.
- [ ] Lessons fed back into the FinOps/SRE backlog.

## 27. References and Further Learning

Official documentation to verify recommender IDs, commands, and service behavior at implementation time:

- [Google Cloud Recommender overview](https://docs.cloud.google.com/recommender/docs)
- [Recommender key concepts](https://docs.cloud.google.com/recommender/docs/key-concepts)
- [Use the Recommender API](https://docs.cloud.google.com/recommender/docs/use-api)
- [Supported recommenders](https://docs.cloud.google.com/recommender/docs/recommenders)
- [Understanding cost-saving estimates](https://docs.cloud.google.com/recommender/docs/understand-cost-recs)
- [FinOps hub](https://docs.cloud.google.com/billing/docs/how-to/finops-hub)

Documentation updates with service and tool versions. Before automating, verify recommender availability in your project/location, IAM permissions, and organizational data governance rules.

**Conclusion:** Recommender helps teams surface optimization opportunities hard to spot when managing infrastructure manually. Real value only materializes when each suggestion is linked to measured telemetry, an owner, SLOs, risk analysis, implementation cost, and post-change verification. By combining Recommender with Active Assist, FinOps hub, Cloud Monitoring, Billing, IAM, and Infrastructure as Code, organizations can optimize GCP infrastructure safely rather than chasing headline savings numbers blindly.
