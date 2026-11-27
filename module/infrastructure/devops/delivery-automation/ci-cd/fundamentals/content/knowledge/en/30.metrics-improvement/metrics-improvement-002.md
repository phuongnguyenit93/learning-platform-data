# Distinguishing Deployment Frequency from Pipeline Run Count

A team can run pipelines hundreds of times a week yet deploy to production only a few times. There is no contradiction: a pipeline is an automated process for checking, building, packaging, or deploying; whereas a deployment is an actual change applied to a target environment. A pull request can trigger many pipeline runs without creating any deployment. Conversely, a single pipeline run can deploy multiple services or multiple environments.

Therefore, **deployment frequency** and **pipeline run count** are two metrics measuring two different activities. Deployment frequency reflects the cadence of delivering changes into an environment, usually focusing on production. Pipeline run count reflects the usage and activity level of the CI system. Using pipeline run count as a proxy for deployment count will distort the picture of release speed.

In CI/CD, it is essential to clearly define which events are counted, which service is the unit of measurement, which environments are in scope, and how retries, rollbacks, canaries, or GitOps are handled. When defined consistently, the two metrics can be used together to understand both release throughput and automation process efficiency.

## 1. The two metrics answer two different questions

**Deployment frequency** answers: how many times is a service successfully deployed to the target environment within a time period?

**Pipeline run count** answers: how many pipeline executions did the CI system launch during the same time period?

| Aspect | Deployment frequency | Pipeline run count |
|---|---|---|
| Unit of measurement | Successful deployment event | Pipeline execution/run |
| Question | How often are changes delivered to an environment? | How many times are pipelines triggered/run? |
| Common scope | One service and one environment, especially production | Repository, workflow, branch, team, or CI platform |
| Includes | Changes actually applied and verified per definition | PR checks, push builds, scheduled jobs, manual runs, deploy jobs |
| Automatically excludes | Failed deploy jobs, no-ops with no state change | Deployment events; a run might not deploy |
| Purpose | Measure release throughput | Measure CI system activity and load |

For example: a commit opening a pull request triggers lint, unit tests, security scans, and a preview build. Four pipeline runs may be recorded, yet if no change has been deployed to production, deployment frequency does not increase.

A release pipeline afterward might deploy the same artifact to staging and then production. Pipeline run count increases by one; production deployment frequency increases by one for the corresponding service. If that pipeline deploys three independent services, the service-level deployment event count may be three even though there is only one pipeline run.

## 2. Defining a deployment event before counting

Deployment frequency cannot be measured accurately if each team interprets “one deployment” differently. Write an operational definition that can be verified automatically.

A commonly used service-level definition:

> A deployment event is counted when a new artifact version or configuration of a service is successfully applied to the target environment, reaches a completed state according to the deployment controller, and is recorded with a unique deployment ID.

The definition needs to answer:

- **Service:** what unit is being measured? A microservice, application, workload, or entire product?
- **Environment:** production, staging, or all? If measuring DORA deployment frequency, separate production from test environments.
- **Success:** does the deploy command return success, must the rollout complete, or must post-deployment validation also pass?
- **Change:** must the observed version/config change, or does a no-change reconcile also count?
- **Identity:** which deployment ID identifies one logical deployment?
- **Time:** use start time, completion time, or verification time?

For release metrics, the deployment success/verification timestamp is typically used. This avoids counting an incomplete deployment in the measurement period. Keep both started_at and completed_at to analyze lead time and rollout duration.

Definitions must remain consistent across services and over time. If counting rules change, version the metric definition and annotate historical comparisons.

## 3. What is a pipeline run?

A pipeline run is one execution of a workflow or pipeline started by the CI system. A run can be triggered by:

- Pushing commits to a branch.
- Opening, updating, or synchronizing a pull request.
- Merging into the main branch.
- Creating a tag or release.
- Scheduled triggers such as nightly builds.
- Manual runs by a user.
- Events from a registry, dependency bot, or external system.
- Retries/re-runs after a job fails or is canceled.

A pipeline run might only run tests, might produce artifacts, or might deploy. Not every run has a deployment. Also distinguish between workflow run, job attempt, and step retry: one workflow can have multiple jobs; a job can be retried; a workflow run can be re-run in full.

When counting pipeline runs, specify the scope: count per workflow execution or per attempt? Typically, created workflow runs are the primary metric; job attempts and retries are secondary metrics to understand load and stability. Do not mix them into a single unitless number.

## 4. Formulas and units of measurement

### Deployment frequency

At the level of one service and one environment:

```text
Deployment frequency =
  number of successful deployment events in the time period
  / length of the time period
```

For example, service A has 8 successful production deployments in 7 days:

```text
DF(A, production, 7 days) = 8 deployments / 7 days
                            ≈ 1.14 deployments per day
```

It can be reported as “8 deployments/week” instead of converting to a daily average so readers understand it easily. For low frequencies, report both the event count and observation window; a single average can hide long quiet periods.

### Pipeline run count

```text
Pipeline run count =
  number of workflow runs created in the time period
  within the selected repository/workflow/branch scope
```

This is a count, not a deployment rate. You can supplement with pipeline runs per day, per repository, or per workflow to monitor CI load.

Do not directly compare “8 deployments/week” with “120 pipeline runs/week” as two quantities with the same meaning. They can be placed side by side, but keep their names, units, and scopes distinct.

## 5. Example: many pipeline runs but few deployments

Suppose a team has the following data for one week:

| Activity | Count |
|---|---:|
| Pull request checks | 52 pipeline runs |
| Push/branch builds | 28 pipeline runs |
| Nightly/security scans | 14 pipeline runs |
| Manual/re-run jobs | 11 pipeline runs |
| Release workflows | 15 pipeline runs |
| **Total pipeline runs** | **120** |
| Successful production deployments of service A | 4 |
| Successful production deployments of service B | 1 |
| Successful production deployments of service C | 0 |

Total pipeline run count is 120. Total service-level production deployment events is 5. If one release workflow deploys services A and B in the same run, that run is still one pipeline run while generating two service-level deployment events.

Do not conclude that the team “deployed 120 times” or that pipelines are deploying too often. Most runs merely validate changes before merge. To understand release productivity, look at deployment frequency per service; to understand CI load, look at pipeline run count by trigger type and workflow.

## 6. Example: one deployment can generate multiple pipeline runs

A single release may consist of:

1. Pull request pipeline running when the PR opens.
2. Pull request pipeline re-running when commits are updated.
3. Required checks re-run after a runner error.
4. Merge into main triggering the build pipeline.
5. Release pipeline building artifacts and deploying to staging.
6. A manual approval job followed by production deployment.

Depending on how the platform records them, this may be 5–6 pipeline runs yet only one production deployment event for that service. If the release pipeline fails before applying changes, deployment frequency does not increase. If production deploy completes but the job times out waiting for a response, reconcile target state before deciding whether a deployment event occurred or a retry is needed.

## 7. How are retries, re-runs, and job attempts counted?

This is a common source of distortion. Distinguish:

- **Pipeline rerun:** re-running a workflow or entire pipeline.
- **Job retry:** re-running one job within the same workflow.
- **Step retry:** a step automatically retrying a request or command.
- **Deployment retry:** re-submitting a deployment request or resuming an already-accepted operation.

For pipeline run count, a new workflow re-run is usually a new run as defined by the CI platform. Job/step attempts should be measured separately. For deployment frequency, do not count each attempt as a deployment. Count only logical deployment events that succeeded according to the definition.

For example: the first deploy times out on the CI side, but the controller already updated production successfully. The runner queries status and confirms the previous deployment ID finished. This is still one deployment event, even though the client may have made multiple requests or job attempts.

If the first attempt fails before modifying production and a subsequent retry succeeds, there is only one successful deployment event. The attempt count is two and should be stored to measure stability.

## 8. Rollbacks, hotfixes, and configuration changes

A rollback is also a real change in production if it redeploys an older artifact or applies recovery configuration. Do not silently remove rollbacks from deployment history.

Store the event type separately:

- Normal release: planned version release.
- Hotfix: urgent change to fix a defect.
- Rollback: restoring a service to a previous artifact/config.
- Roll-forward: deploying a new fix to remediate.
- Config-only change: changing runtime configuration without changing binaries.

For overall deployment frequency reporting, an organization can count every successful deployment event that changes production state, including rollbacks. At the same time, classify by change_type so readers see the rollback/hotfix ratio. If the metric is used for DORA or benchmarks, publish the counting rule and keep it consistent; do not exclude incident-causing deployments just to polish numbers.

Whether config-only changes are counted depends on the organization's deployment definition. If configuration changes are released as controlled production changes, record them as separate events. Modifying a dashboard or metadata that does not affect runtime should not be counted as a service deployment.

## 9. Canary, blue-green, and multi-step rollouts

One logical deployment may pass through multiple stages:

- Starting a canary with 5% traffic.
- Increasing to 25%, 50%, then 100%.
- Switching blue-green traffic from the old pool to the new pool.
- Updating multiple replicas or multiple availability zones.

Do not count each traffic increment, pod restart, or region wave as a new deployment if they are phases of the same rollout under the same deployment ID. Record rollout phases separately to analyze timing, health, and promote/abort decisions.

If a rollout is aborted and rolled back to the previous version, record a rollback event linked to the original deployment. If a different digest is released later, that is a new deployment event.

For multi-region setups, pick one reporting unit:

- **Logical service deployment:** one release of the same release unit for a service across all target regions; suitable for measuring service-level release cadence.
- **Per-region deployment:** each updated region is one event; useful for operations and rollout analysis.

Do not add the two counting methods into the same metric. You can store both dimensions, but dashboards must state clearly whether they show logical deployments or region-level operations.

## 10. GitOps and no-op reconciliations

In GitOps, controllers reconcile desired state continuously. One sync or reconcile does not necessarily constitute a deployment event.

Distinguish:

- Reconcile loop checking state with no changes: do not count a deployment.
- Applying a new manifest that alters runtime state: may generate a deployment event.
- Retrying a reconcile due to a controller error while targeting the same desired revision: do not count multiple deployment events.
- Drift correction bringing runtime back to the desired revision: record a change/reconciliation event; count a deployment only if there is an actual runtime change per definition.
- A config commit successfully applied that modifies the service: count one event for the selected service/target.

Pull data from controller events or deployment records containing revision/digest and observed state, rather than counting GitOps syncs. If the controller emits multiple events for the same revision, deduplicate by deployment ID or change identity.

## 11. One pipeline deploying multiple services

Monorepos or release trains can use one pipeline to deploy multiple services. Counting deployments at the pipeline level loses granularity:

For example, one workflow deploys:

- orders-service digest A to production.
- payments-service digest B to production.
- notifications-service is unchanged so it is skipped.

Pipeline run count increases by one. Deployment frequency increases by one for orders-service and one for payments-service; notifications-service does not increase. If the organization also measures the release train as a single product, an extra product-level release event can be recorded, but it must not replace service-level metrics when evaluating individual services.

The event model should support a one-to-many relationship between pipeline runs and deployment events. Each deployment event has its own service, environment, target, and digest, along with pipeline_run_id referencing the run that created it.

## 12. Designing event data for consistent counting

A deployment event can store the following fields:

| Field | Meaning |
|---|---|
| deployment_id | Unique ID of the logical deployment |
| service_id | Deployed service |
| environment | Target environment |
| target_scope | Cluster, namespace, region, or target group |
| release_id | Related release or change request |
| pipeline_run_id | Pipeline run that initiated the operation |
| artifact_digest | Deployed artifact content digest |
| config_revision | Applied configuration revision |
| change_type | normal, hotfix, rollback, roll-forward, config-only |
| status | accepted, running, succeeded, failed, cancelled |
| started_at | Start timestamp |
| completed_at | Completion timestamp |
| verified_at | Timestamp when post-deployment validation passed |
| source_commit | Source commit |

Pipeline run records should contain run_id, workflow, repository, trigger, branch/ref, commit SHA, attempt, started_at, completed_at, and conclusion. The two records link via pipeline_run_id; do not infer deployment count from run count.

Event example:

```json
{
  "deployment_id": "dep-2026-004281",
  "service_id": "orders-service",
  "environment": "production",
  "target_scope": "ap-southeast-1/prod-orders",
  "release_id": "orders-2.7.1",
  "pipeline_run_id": "ci-18452",
  "artifact_digest": "sha256:abc123...",
  "config_revision": "7c91e2...",
  "change_type": "normal",
  "status": "succeeded",
  "started_at": "2026-11-18T09:24:00Z",
  "completed_at": "2026-11-18T09:28:42Z",
  "verified_at": "2026-11-18T09:30:00Z",
  "source_commit": "4f2a9c1..."
}
```

The schema above is an example. Enforce a unique constraint on deployment_id within the appropriate scope, preserve event history, and do not overwrite attempts. For multi-target rollouts, you can maintain parent deployment and child target records.

## 13. Deduplication and reliable data sources

Deployment frequency will be overcounted if the same deployment is recorded from multiple sources: CI jobs, deployment controllers, webhooks, and observability collectors. Determine the source of truth and deduplication mechanism.

Principles:

- Generate a stable deployment ID when creating the operation.
- All phase events of the same rollout share the same deployment ID.
- Retries reuse the operation/idempotency identity when continuing the same intent.
- Transition to succeeded only after success criteria are met.
- Do not count an event merely because an API accepted a request or a job started.
- Deduplicate webhook/event deliveries by event ID or deployment ID + sequence.
- Store verification source and timestamps for auditing.

If no deployment controller record exists, CI can emit the event after verifying the observed digest/config revision. Avoid using the deploy command's exit code alone as proof.

## 14. Dashboards should display the two metrics separately

A useful dashboard can place both metrics side by side while preserving their proper units:

| Dashboard panel | Metric | Grouping |
|---|---|---|
| Production deployment frequency | Successful deployment events / service / week | Service, environment, change type |
| Pipeline run volume | Workflow runs / week | Repository, workflow, trigger |
| Pipeline success rate | Successful runs / total completed runs | Workflow, branch |
| Deployment success rate | Successful deployment events / attempted deployments | Service, environment |
| Deployment duration | Started to completed/verified | Strategy, service |
| Retry/re-run rate | Runs or attempts retried / initial runs | Workflow, failure reason |
| Rollback rate | Rollback events / deployment events | Service, release |

Do not merge “pipeline success rate” with “deployment success rate”. A pipeline may succeed running tests without deploying; a pipeline may end in failure after the deployment succeeded if a reporting step failed. Maintain distinct statuses for deployment operations and workflow runs.

## 15. Using both metrics to diagnose issues

Both metrics are more meaningful when analyzed together:

| Observation | Possible interpretation | Follow-up questions |
|---|---|---|
| Pipeline runs rise, deployment frequency flat | More PRs/builds, more tests, or more retries | Are runs increasing due to dev activity, scheduled scans, or flaky tests? |
| Pipeline runs low, deployment frequency low | Fewer changes or slow release process | Are there review, approval, test, or release window bottlenecks? |
| Pipeline runs stable, deployment frequency rises | Smaller, more frequent releases | Are change failures/rollbacks increasing? |
| Pipeline runs surge, success rate drops | Unstable CI or dependency/runner failures | Queues, flaky tests, quotas, or toolchain changes? |
| Deployment frequency rises, rollbacks rise | Fast releases but quality may be slipping | Check change failure rate and post-deploy signals |
| One pipeline run creates many deployment events | A release train deploying multiple services | Should both per-service and product-release metrics be reported? |

Do not jump to root causes from just two numbers. Combine lead time for changes, change failure rate, failed deployments, rollbacks, MTTR, and pipeline metrics to understand the whole delivery flow.

## 16. Avoiding metric gaming

When deployment frequency becomes a target, teams may inadvertently optimize the number rather than safe release capability:

- Unnecessarily splitting one change into many small deployments just to raise counts.
- Counting every pod, region wave, or canary step as a separate deployment.
- Counting deploy requests even when rollouts fail.
- Removing rollbacks from data to lower incident rates.
- Inflating pipeline runs by re-running workflows that add no value.
- Bundling multiple services into one unit to hide slow-deploying services.

Countermeasures:

- Define events and units of measurement before setting targets.
- Measure at the service and production environment level where appropriate.
- Retain successes, failures, rollbacks, and attempts so context is not lost.
- Track change failure rate, recovery time, and quality alongside deployment frequency.
- Never use pipeline run count as a proxy for deployment frequency.
- Never tie rewards to a single isolated metric.
- Audit changes to counting rules and dashboards.

The goal is to increase the ability to deliver valuable changes safely to users, not to make a deployment count chart climb at all costs.

## 17. Example data queries

Suppose the deployment_events table has one row per logical deployment with normalized final statuses. Query deployment frequency per service for one week:

```sql
SELECT
    service_id,
    COUNT(*) AS successful_production_deployments
FROM deployment_events
WHERE environment = 'production'
  AND status = 'succeeded'
  AND completed_at >= TIMESTAMP '2026-11-11 00:00:00'
  AND completed_at <  TIMESTAMP '2026-11-18 00:00:00'
GROUP BY service_id
ORDER BY service_id;
```

Query pipeline run count by trigger:

```sql
SELECT
    trigger_type,
    COUNT(*) AS pipeline_runs
FROM pipeline_runs
WHERE started_at >= TIMESTAMP '2026-11-11 00:00:00'
  AND started_at <  TIMESTAMP '2026-11-18 00:00:00'
GROUP BY trigger_type
ORDER BY pipeline_runs DESC;
```

These queries are examples and must be adapted to your actual schema. If the deployment_events table has multiple rows per phase or region, query the logical deployment parent or deduplicate by deployment_id before COUNT. If the metric uses verified_at as the recording timestamp, replace completed_at with verified_at and state this clearly in the definition.

## 18. Implementation process for measurement

You can build the metrics in steps:

1. Select the services and environments to measure; prioritize production.
2. Write definitions for deployment events and pipeline runs.
3. Identify the source of truth: CI platform, deployment controller, or event collector.
4. Generate deployment IDs and link pipeline_run_id.
5. Normalize statuses, change types, and timestamps.
6. Handle retries, reruns, multi-region, canary, and GitOps deduplication.
7. Backfill historical data if sources are trustworthy enough; document data limitations.
8. Build separate dashboards for deployment frequency and pipeline run count.
9. Reconcile several actual releases against counted records.
10. Review definitions periodically as architecture or processes evolve.

Early on, run metrics in observation mode and manually cross-check them before using them for goal setting. If data is incomplete, report confidence levels instead of presenting false precision.

## 19. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using pipeline run count as deployment frequency | Misjudges release cadence | Count actual deployment events per service/environment |
| Including PR checks and nightly scans as deployments | Artificially inflated numbers | Separate workflow activity from deployments |
| Counting each retry as a new deployment | Double-counts the same change | Use deployment IDs and deduplication |
| Counting each canary step or pod update | One rollout counted multiple times | Use a logical deployment ID, store phases separately |
| Omitting rollbacks from history | Loses recovery and quality data | Classify rollbacks separately, publish rules |
| Counting successful runs when deploy was skipped | Reports non-existent deployments | Verify observed state and deployment records |
| Merging multiple services into one unit | Hides slow-releasing services | Report service-level and product-level separately |
| Failing to define production/target | Numbers across teams cannot be compared | Standardize environment taxonomy |
| Using inconsistent timestamps | Events fall into wrong reporting periods | Pick completed/verified time and UTC standard |

## 20. Checklist for distinguishing and measuring both metrics

- [ ] Separate definitions exist for pipeline runs and deployment events.
- [ ] Deployment frequency is measured clearly by service and environment.
- [ ] Only successful deployments meeting published criteria are counted.
- [ ] Pipeline run count has clear workflow/repository/trigger scope.
- [ ] Job attempts, step retries, and workflow reruns are measured separately when needed.
- [ ] Retries of the same deployment do not create duplicate deployment events.
- [ ] Rollbacks, hotfixes, roll-forwards, and config-only changes are classified.
- [ ] Canary phases, region waves, and GitOps no-op reconciles are not miscounted.
- [ ] One-pipeline-to-many-deployments is supported in the event model.
- [ ] Deployment ID, pipeline_run_id, artifact digest, and source commit are captured.
- [ ] Events are deduplicated and reconciled against observed state.
- [ ] Dashboards keep separate units, scopes, and time windows for each metric.
- [ ] Both metrics are analyzed alongside success rate, rollbacks, change failure, and recovery time.
- [ ] Definitions are reviewed and checked for metric gaming periodically.

Deployment frequency shows how often a service delivers changes to its target environment; pipeline run count shows how many times the CI system executes workflows. When these two measurement units are properly separated, deployment events are recorded by service/environment, and retries, rollbacks, canaries, and GitOps are handled consistently, teams can evaluate release throughput and automation load without confusing the two activities.
