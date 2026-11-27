# Measuring Time from Change to Usable in the Target Environment

A code change only creates value when users or the target system can actually use it. A merged commit, a green pipeline, or a deploy command returning success is not enough to prove that. The artifact might still be rolling out, Pods might not be Ready yet, traffic might still be going to the old version, a feature flag might not be enabled yet, or post-deploy business workflows might still be failing.

Therefore, when measuring software delivery speed, it is necessary to determine the time from when a change enters the development stream until that change is genuinely usable in the target environment. This metric is commonly called **lead time for changes** or change-to-usable lead time. For the measurement to be meaningful, the team must precisely define the start point, end point, how commits are linked to deployments, and how failed releases are handled.

In CI/CD, the goal is not to make a single number small at any cost. The goal is to find out which waiting times and processing steps are delaying changes from reaching users, and then improve the flow while maintaining quality, security, and resilience.

## 1. What does lead time measure?

Lead time for changes measures the duration from when a change is committed to version control until that change is successfully deployed and usable in the target environment. It is a metric of flow speed from code to production.

For a service with a clear release process, it can be defined as:

~~~text
LeadTime = T_usable - T_change
~~~

Where:

- **T_change:** the timestamp when the change is recorded on the integration branch or the revision is selected as release input.
- **T_usable:** the timestamp when the change has been deployed, verified, and is genuinely usable according to the target environment's criteria.

For example: a commit is merged into main at 09:00. Build, tests, and review complete at 09:18; the artifact is published at 09:22; production rollout starts at 09:30; all instances are Ready, traffic has shifted, and smoke tests pass at 09:42. The lead time is 42 minutes, not the 18 minutes of the build/test pipeline or the 12 minutes of the deploy command.

### 1.1. Why do we need the “usable” milestone?

A change may already be pushed to production without being usable yet:

- The deployment controller has accepted the manifest, but the rollout is still in progress.
- The container is running, but the readiness probe has not passed yet.
- New instances are Ready, but the load balancer is not routing traffic to them yet.
- The new API is deployed, but the feature flag is still off.
- The schema has been updated, but background workers have not processed the required data yet.
- The endpoint returns 200, but critical business transactions still fail.
- The feature is only enabled for a small cohort, while the metric is reported as if it were open to all users.

The end milestone must reflect the measurement objective. If the team wants to measure “code running in production”, they can use the time when the runtime confirms the right artifact. If they want to measure “customers can use the feature”, they need to include traffic, feature flag, access permission, and smoke/synthetic transaction conditions. Both measurements are useful, but they must be named and reported separately.

## 2. Choosing a consistent start milestone

The start milestone determines which segment of the process the team is measuring.

A common choice for DORA Lead Time for Changes is the timestamp when a commit is introduced into version control. For a CI/CD flow with an integration branch, the team can use the time when the commit is merged into the main branch or when the revision becomes the official input of the release pipeline.

Possible milestones to use:

| Start milestone | What is being measured? | Limitations |
|---|---|---|
| When the developer starts coding | Time from starting work to usable | Hard to measure accurately, easily skewed by task switching |
| Pull request is opened | PR cycle time from review to production | Ignores coding time before the PR |
| First commit of the change | Close to when code is recorded | May include draft commits or commits not yet selected for release |
| Commit merged into integration branch | Time from an accepted change in the main stream to usable | Suits trunk-based flow; requires mapping merge/squash commits |
| Commit/revision selected for release | Time from identified revision to usable | Suits release trains; may ignore waiting time before release selection |

Do not mix multiple definitions on the same dashboard. If the team uses merge time for one service and PR-open time for another, the comparison will not be fair.

### 2.1. Practical definition recommendation

For a CI/CD module, an easy-to-implement definition is:

- Start at the timestamp when the commit containing the change is integrated into the protected/default branch or the revision is accepted as release input.
- End at the timestamp when the deployment of that revision meets the usable criteria in the target environment.
- Use UTC timestamps recorded by the source control, pipeline, and deployment systems.
- Tag every milestone with change ID, commit SHA, artifact digest, deployment ID, and environment.
- Report lead time to staging and lead time to production separately if both are valuable.

If organizing releases in batches, there must be rules determining which commits belong to that deployment. Never pick a favorable commit timestamp retroactively after knowing the outcome.

## 3. Defining the end milestone: deploy succeeded or usable?

The end milestone should not just be when the deploy command returns exit code 0. The command might only submit a request to the control plane while the rollout continues in the background.

A deployment can be considered usable when service-appropriate conditions are met:

1. The exact artifact digest/revision is running in the target environment.
2. The rollout has reached a completed state or reached the defined cohort scope.
3. Required instances are Ready and included in endpoint/traffic routing.
4. Mandatory health checks and smoke/synthetic checks pass.
5. Feature flags, entitlements, or routing are opened to the target user scope.
6. Representative business workflows can execute successfully.
7. No mandatory guardrails are blocking the release, such as error rate or latency exceeding thresholds.

### 3.1. Different “usable” levels

| End level | Condition | Appropriate metric |
|---|---|---|
| Deployed | Control plane has applied the revision | Deploy request/operation duration |
| Runtime active | Instances run the right artifact | Commit-to-runtime lead time |
| Ready for traffic | Instances are Ready and in routing | Commit-to-ready lead time |
| Verified | Smoke/synthetic checks and guardrails pass | Commit-to-verified lead time |
| Available to cohort | Flag/permission/routing opened to approved cohort | Change-to-cohort-usable lead time |
| General availability | Feature expanded as planned to the entire target audience | Change-to-GA lead time |

Choose one primary milestone for lead time reporting and optionally keep intermediate milestones for analysis. For instance, for a backend service, Verified can be the primary milestone. For a feature requiring a feature flag, Available to cohort or General availability might reflect value better.

## 4. Distinguishing lead time from other time metrics

Time metrics in delivery are often loosely grouped as “build time” or “deployment time”, yet they measure different segments.

| Metric | Start | End | Question |
|---|---|---|---|
| Lead time for changes | Commit/change integrated | Change usable in production | How long from code to usable value? |
| PR cycle time | PR opened | PR merged | How long do review and integration take? |
| CI duration | Pipeline/job starts | Pipeline/job ends | How long do automated checks take to run? |
| Queue time | Job created | Runner starts executing | How long must work wait for a worker? |
| Build duration | Build task starts | Artifact build finishes | How long do compile/package take? |
| Deployment duration | Deploy starts | Rollout/deploy operation ends | How long does deploying take? |
| Time to usable | Deploy starts or commit depending on definition | Usable criteria met | How long until the version actually serves? |
| Time to restore service | Incident starts | Service restored | How long to recover after a failure? |

Lead time aggregates multiple segments. A short CI duration does not guarantee a short lead time if changes must wait for reviews, release windows, approvals, runner capacity, or environments.

## 5. Event model for calculating lead time

To calculate reliably, collect events rather than only reading the final pipeline status.

A change can go through this sequence:

~~~mermaid
flowchart LR
    A[Change integrated] --> B[CI queued]
    B --> C[CI started]
    C --> D[Checks passed]
    D --> E[Artifact published]
    E --> F[Deploy requested]
    F --> G[Rollout complete]
    G --> H[Runtime verified]
    H --> I[Traffic / feature enabled]
    I --> J[Usable]
~~~

Each event should include:

- **event_id:** unique event identifier.
- **event_type:** event type such as change_integrated, build_started, artifact_published, deployment_usable.
- **occurred_at:** timestamp when the event actually occurred.
- **recorded_at:** timestamp when the collection system received/recorded the event.
- **change_id** or list of related commit SHAs.
- **repository**, **service**, **environment**.
- **pipeline_run_id**, **build_id**, **release_id**, **deployment_id** when available.
- **artifact_digest** to identify the artifact.
- **result** or **status**.
- **actor** or workload identity if needed for audit.

### 5.1. Event record example

~~~json
{
  "event_id": "evt-9f21",
  "event_type": "deployment_usable",
  "occurred_at": "2026-11-18T09:42:00Z",
  "recorded_at": "2026-11-18T09:42:02Z",
  "change_id": "chg-1842",
  "commit_sha": "a1b2c3d4",
  "service": "orders",
  "environment": "production",
  "release_id": "rel-2026-11-18-07",
  "deployment_id": "dep-7731",
  "artifact_digest": "sha256:abc123...",
  "result": "verified"
}
~~~

This example only illustrates the schema. In real systems, use stable identifiers from the SCM, build system, and deployment platform; do not invent IDs with no link to their origin.

### 5.2. Using event time and processing time properly

occurred_at represents when the event occurred; recorded_at represents when telemetry reached the collection system. If events are delivered late, using recorded_at to calculate lead time can artificially inflate results.

Calculate using event time while monitoring ingestion lag:

~~~text
IngestionLag = T_recorded - T_occurred
~~~

If ingestion lag is large or timestamps are unreliable, flag the data as low quality instead of silently falling back to the event reception time.

## 6. Linking changes to artifacts and deployments

This is the hardest part of measuring lead time in real systems. One deployment often contains multiple commits; one commit may be deployed multiple times; an artifact may be promoted through staging then production; hotfixes may be cherry-picked; monorepos have multiple services and a release only includes changes for a subset.

A traceability chain is required:

**Change → Commit(s) → Build → Artifact digest → Release → Deployment → Environment → Usable event**

A release record should store:

- Repository and service.
- Commit SHA or list of included commits.
- Build/pipeline run ID.
- Artifact coordinates/version/digest.
- Release ID and deployment ID.
- Environment/region/cohort.
- Deploy timestamp and usable timestamp.
- Validation and approval results.

### 6.1. One deployment containing multiple commits

If a production deployment contains 8 commits, each commit can inherit the same T_usable of that deployment when computing per-change commit-to-production lead time. When computing statistics, keep this rule consistent and avoid double-counting the deployment as multiple deployment events.

Example:

| Commit | Integrated at | Deployment usable at | Lead time |
|---|---|---|---:|
| C101 | 08:10 | 09:00 | 50 minutes |
| C102 | 08:25 | 09:00 | 35 minutes |
| C103 | 08:40 | 09:00 | 20 minutes |

There is only one deployment usable event at 09:00, yet three changes have three different lead times.

### 6.2. One commit deployed multiple times

If the same commit is deployed to staging then production, each environment is a separate measurement:

- Commit-to-staging-usable.
- Commit-to-production-usable.

Do not sum or average the two milestones and call it a single lead time. Dashboards must clearly specify the target environment.

### 6.3. Squash, cherry-pick, and merge commits

If the SCM creates a squash commit or a new cherry-pick SHA, store the relationship between the original change/PR and the actual commit in the release. You can use PR/MR ID or change ID as the business key, while still storing the commit SHA that was actually built.

## 7. Breaking down lead time to find where work waits

Aggregate lead time does not directly tell you where to improve. Split it into intervals between events:

~~~text
T_total =
  T_integration_to_CI +
  T_CI +
  T_artifact_to_deploy +
  T_deployment +
  T_verification
~~~

Depending on the process, you can also include pre-merge review time, waiting for a release train, waiting for approval, waiting for capacity, or time before a feature flag is enabled.

Example breakdown of a change taking 6 hours:

| Stage | Duration | Share |
|---|---:|---:|
| Waiting for merge/review | 2 hours | 33.3% |
| Waiting for runner | 20 minutes | 5.6% |
| CI build/test | 25 minutes | 6.9% |
| Waiting for release approval/window | 2 hours | 33.3% |
| Publish and deploy | 35 minutes | 9.7% |
| Verification and opening traffic | 40 minutes | 11.1% |
| Total | 6 hours | 100% |

In this example, shaving another 5 minutes off the compiler has far less impact than shortening review or approval wait times. Breakdown helps pick the right bottleneck.

### 7.1. Distinguishing processing time and waiting time

- **Processing time:** time when actual work is performed, such as building, testing, scanning, or rolling out.
- **Waiting time:** time a change waits for a reviewer, runner, approval, release window, or dependency.
- **Rework time:** time spent fixing errors, re-running pipelines, or handling failed deployments.

A pipeline with 15 minutes of processing time but 90 minutes waiting for a runner still has a long lead time. Do not focus solely on optimizing CPU time if most latency comes from queues or handoffs.

## 8. Calculating lead time with structured data

Suppose a change_deployments table has the following columns:

- change_id
- service
- environment
- integrated_at
- usable_at
- deployment_id
- artifact_digest
- usable_status

A conceptual SQL query:

~~~sql
SELECT
    service,
    environment,
    change_id,
    deployment_id,
    EXTRACT(EPOCH FROM (usable_at - integrated_at)) AS lead_time_seconds
FROM change_deployments
WHERE usable_status = 'verified'
  AND integrated_at IS NOT NULL
  AND usable_at IS NOT NULL
  AND usable_at >= integrated_at;
~~~

This query is just an example; time calculation syntax may vary by database. Ensure one row corresponds to the exact change/environment/deployment mapping without row multiplication from joining multiple commits or events.

### 8.1. Checking for anomalous data

Before placing metrics on a dashboard, check:

- Is usable_at earlier than integrated_at?
- Are there undeployed changes that lack usable_at?
- Does a single change have multiple deployments or rollbacks?
- Does a single deployment contain multiple changes?
- Do timestamps include timezone information?
- Are there duplicate events sent?
- Does the artifact digest match between build and deployment?
- Are environment names normalized?
- Are there canceled or superseded changes?

Do not discard anomalous values without recording the reason. A negative lead time might indicate a clock or mapping bug; a change waiting 30 days might be a real held-back change rather than garbage data.

## 9. Using medians and percentiles instead of averages alone

Lead time usually has a skewed distribution: many changes are released quickly, while some wait for days. Averages can be pulled up by a few long outliers; medians show the typical experience but fail to reflect the tail.

Track the following:

- **p50/median:** half of the changes have a lead time below this level.
- **p75:** 75% of changes complete within this duration.
- **p90/p95:** represents the slow cohort of changes and tail length.
- **Average:** useful for total time cost, though sensitive to outliers.
- **Count/sample size:** number of changes in the period to gauge distribution confidence.

Example:

| Statistic | Lead time |
|---|---:|
| p50 | 42 minutes |
| p75 | 1 hour 20 minutes |
| p90 | 5 hours |
| p95 | 1.4 days |
| Average | 4.2 hours |
| Changes | 180 |

A median of 42 minutes shows most changes move fast, while a p95 of 1.4 days reveals a group stuck at release windows or approvals. Analyze the tail instead of only publishing the median.

### 9.1. Comparing under equal conditions

When comparing week-over-week or across services, keep conditions comparable:

- Same start/end definitions.
- Same environment.
- Same commit-to-deployment mapping method.
- Same change type or stratified by type.
- Same time units and timezone.
- Sufficient sample size.
- Documented changes in measurement methodology.

Do not compare staging p50 with production p95, or compare a continuously deployed service with a monthly-release service without explaining the differences.

## 10. Non-usable changes and censored data

If you only count successfully deployed changes, the dashboard may omit changes that have been waiting for days. This is survivorship bias: fast completed cases get counted, while slow cases without an end time vanish from the report.

Track additionally:

- Number of changes integrated but not yet usable.
- Age of incomplete changes (change age).
- Number of changes waiting for review, approval, release window, or fixes.
- Number of failed/canceled/superseded changes.
- Number of changes rolling out but not yet verified.

For changes without an end time, a complete lead time cannot be computed. You can report their current age as a separate metric and apply survival/censored data analysis if the team needs advanced statistics. At a minimum, dashboards should not silently drop them.

### 10.1. Distinguishing failed attempts and final changes

A change may go through a failed deploy before a successful re-deploy. Lead time to usable should be measured from the initial change milestone to the first time the final usable criteria are met, while keeping failed attempts and recovery duration separate. Never reset the start time on each retry to make lead time look artificially short.

If a release is rolled back before users can use it, do not mark the change as usable. If it became usable first and then an incident and rollback occurred, keep the historical usable event while linking change failure/recovery metrics; do not erase the initial success milestone.

## 11. Time synchronization and timestamp quality

Lead time is the subtraction of two timestamps across multiple systems: SCM, CI server, artifact registry, deployment platform, and telemetry. If clocks are out of sync, results can be negative or significantly wrong.

Principles:

- Store timestamps in UTC with explicit timezone information.
- Synchronize clocks on runners, controllers, and self-managed systems using NTP or equivalent mechanisms.
- Prefer timestamps recorded by servers/control planes over arbitrary client-submitted times.
- Keep both event time and ingestion time.
- Within a single process, use a monotonic clock to measure internal duration; use wall-clock UTC to correlate events across systems.
- Monitor clock skew and ingestion lag.
- Never alter historical timestamps to make reports look better.

If the SCM and deployment platform clocks drift by several minutes, change-to-usable measurements of just a few minutes become unreliable. Emit data quality alerts or exclude faulty periods under a transparent policy.

## 12. DORA Lead Time for Changes and related metrics

Lead time for changes is one of the DORA metrics for software delivery performance. It should be viewed alongside other metrics rather than becoming an isolated target.

Metrics commonly used in modern DORA models include:

- **Deployment frequency:** how often deployments reach production.
- **Lead time for changes:** time from commit until a change runs in production.
- **Change failure rate:** percentage of deployments causing service degradation or requiring remediation.
- **Failed deployment recovery time:** time to recover after a failed deployment.
- **Deployment rework rate:** percentage of deployments performed to fix defects or recover from an earlier change.

Naming and operationalization may vary across model versions and tools. What matters is publishing the definition in use. Low lead time with high change failure rate is not a good result; high deployment frequency with rising rework may indicate the pipeline is pushing low-quality changes.

### 12.1. Not equating lead time with throughput

Lead time measures the duration of individual changes; throughput measures the number of completed changes over a period. A team can have short lead time yet low throughput if changes are tiny or few people are contributing. A team can have high throughput yet long lead time if many changes sit together in batches or wait for a release window.

Track both to understand flow.

## 13. Measuring by service and environment

An organization with many services should not report only one aggregate number. Each service has different release characteristics:

- Stateless APIs may deploy multiple times a day.
- Database services have migrations and maintenance windows.
- Mobile/backend features may depend on app stores or client rollouts.
- Batch processing may only become usable after the next job run.
- Feature flags may open per tenant or cohort.

Segment by:

- Service/component.
- Environment: staging, production, region, or cluster.
- Change type: feature, bugfix, security patch, config, migration.
- Release strategy: rolling, canary, blue/green, feature flag.
- Repository/team if ownership context is needed.
- Risk level or change scope.

Do not lump all services into a simple ranking. Use metrics to find flow issues within each service, not to create competitions between teams with different architectures and obligations.

## 14. Building a useful lead time dashboard

A good dashboard needs to answer three layers of questions.

### 14.1. Overall outcomes

- p50/p75/p90/p95 lead time.
- Number of usable changes in the period.
- Number of waiting changes and their age.
- Percentage of changes lacking deployment mapping.
- Percentage of events missing timestamps or artifact digests.
- Deployment frequency and change failure rate for context.

### 14.2. Bottleneck breakdown

Display time spent in each segment:

- Change integrated → CI queued.
- CI queued → CI started.
- CI started → checks passed.
- Checks passed → artifact published.
- Artifact published → deploy requested.
- Deploy requested → rollout complete.
- Rollout complete → verification passed.
- Verification passed → feature available to target cohort.

You can use stacked bars per change or percentiles per phase. When one phase takes a large share, drill down into pipeline runs, approval records, or deployment events.

### 14.3. Quality and risk

Place next to lead time:

- Failed pipelines and retry counts.
- Failed deployments and rollbacks.
- Change failure rate.
- Incident/recovery time.
- Post-deploy error rate, latency, saturation.
- Skipped or bypassed tests/quality gates.
- Percentage of artifacts without traceable provenance.
- Number of changes expanding cohorts after an observation window.

Do not use the dashboard solely to rank teams. Use it to locate waiting points, remove redundant handoffs, and detect when speed rises at the expense of quality.

## 15. Improving lead time by bottleneck

After breaking down lead time, choose improvements targeting the root cause. Common directions include:

| Bottleneck | Symptoms | Improvements to try |
|---|---|---|
| Slow review | Changes wait long for PR review | Smaller PRs, clear reviewer ownership, review rotation, automated style checks |
| Runner queue | Jobs wait long before running | Tune capacity, autoscaling, runner labels, and concurrency |
| Overlong CI | Build/tests dominate duration | Proper caching, incremental builds, parallel tests, test pyramid |
| Flaky tests | Many retries, unstable results | Fix root causes of flakiness, quarantine tests, keep bounded retries with observability |
| Slow approval | Waiting for approvers or release windows | Risk-based approvals, clear owners/on-call, approval on release candidates |
| Slow artifact publish | Large uploads or slow registry | Layering, registry close to runners, compression, and artifact size control |
| Slow rollout | Prolonged readiness or capacity issues | Optimize startup, capacity planning, rollout strategy, and probes |
| Slow verification | Long or manual smoke/synthetic tests | Short, representative, automated tests and layered verification |
| Feature unenabled | Deploy finished but flag/cohort waits | Integrate release decisions and flag operations into an owned flow |
| Batch release | Changes must wait for release windows | Smaller releases, more frequent deploys if risk controls allow |

### 15.1. Optimize queues before optimizing compute

If CI duration is only 10 minutes but runner queue time is 60 minutes, adding caches or faster CPUs will not solve the main cause. Measure queue time separately and examine runner capacity, concurrency limits, quotas, label mismatches, and job scheduling.

### 15.2. Optimize tests selectively while preserving required coverage

You can run unit tests in parallel, use affected tests, or separate fast checks from the full suite. However, selective testing must have a fallback mechanism when impact cannot be determined; never skip mandatory tests just to reduce lead time.

### 15.3. Reduce batch size and handoffs

Small changes that are quick to review and independently deployable typically cut wait times. Yet splitting changes does not mean dropping compatibility testing or deploying continuously when the system is not ready. Maintain contracts, migrations, and rollout controls.

## 16. Example lead time calculation for one change

A change CHG-1842 adds the deliveryWindow field to the orders service:

| Event | UTC Timestamp |
|---|---|
| Commit merged into main | 09:00 |
| CI started | 09:04 |
| Tests and quality gates passed | 09:19 |
| Artifact digest published | 09:23 |
| Production deploy started | 09:31 |
| Rollout complete, Pods Ready | 09:37 |
| Smoke tests and business checks passed | 09:41 |
| Feature flag enabled for pilot cohort | 09:45 |

If usable is defined as “pilot cohort can use the feature”, then:

~~~text
LeadTime = 09:45 - 09:00 = 45 minutes
~~~

Time segments:

- Waiting for CI: 4 minutes.
- CI: 15 minutes.
- Publish and handoff: 12 minutes.
- Rollout: 6 minutes.
- Verification: 4 minutes.
- Waiting/enabling feature flag: 4 minutes.

If you only take rollout completion time, lead time would be 37 minutes. If you only take pipeline duration, you might report 15 minutes. Both can be valid metrics for their specific questions, but neither represents the 45 minutes until the pilot cohort can use it.

## 17. Setting targets and improving by trend

Do not set the exact same lead time target for every service. Targets need to be based on baseline, risk profile, release model, and product expectations.

An implementation approach:

1. Define start/end milestones and event schema.
2. Collect data over several release cycles to establish a baseline.
3. Analyze median, p90/p95, and change age.
4. Identify the phase with the largest waiting time.
5. Choose one verifiable improvement.
6. Monitor lead time alongside change failure rate and recovery.
7. Evaluate after a period with sufficient sample size.
8. Adjust targets if the change/service mix shifts.

You can set an internal SLO like “90% of changes in service X are usable within 4 hours”, while clearly defining the cohort, environment, change types, and exclusions. SLOs should aim to improve flow, not incentivize bypassing gates.

### 17.1. Avoiding turning metrics into targets that drive wrong behavior

When lead time becomes a reward/punishment KPI, teams may:

- Bundle multiple changes into one commit or release to reduce sample count.
- Pick a later start timestamp.
- Mark usable immediately when the deploy command returns success.
- Ignore failed attempts or rollbacks.
- Cut necessary tests/approvals.
- Measure only small changes and exclude hard ones.
- Push bugs into the post-release stage.

To reduce risk, keep definitions transparent, pair with quality/reliability metrics, and inspect outliers. Metrics are a tool for learning about the system, not a measure of individual worth.

## 18. Lead time measurement implementation checklist

### Definition

- [ ] Start milestone is clearly defined: commit integrated or release input.
- [ ] End milestone reflects usable, not just deploy request success.
- [ ] Environment and cohort scope are explicitly recorded.
- [ ] Lead time is distinguished from PR cycle, CI duration, and deployment duration.
- [ ] Rules for mapping changes/commits to deployments are published.

### Data and traceability

- [ ] Event ID, change ID, commit SHA, pipeline run, artifact digest, and deployment ID exist.
- [ ] Timestamps include UTC/timezone, event time, and recorded time.
- [ ] Tested artifacts can be linked to runtime artifacts.
- [ ] Multi-commit deployments are handled consistently.
- [ ] Rules exist for squash, cherry-pick, batch releases, and multiple environments.
- [ ] Duplicate, missing, or out-of-order events are detected.

### Analysis

- [ ] Report p50, p75, p90/p95, and sample size.
- [ ] Track non-usable changes and change age.
- [ ] Break down waiting time, processing time, and rework time.
- [ ] Segment by service, environment, and change type.
- [ ] Do not silently drop failed/long-running changes.
- [ ] Monitor clock skew and ingestion lag.

### Improvement

- [ ] Select bottlenecks based on data.
- [ ] Monitor deployment frequency, change failure, and recovery alongside lead time.
- [ ] Improvements do not weaken security, quality gates, or rollback readiness.
- [ ] SLO definitions and measurement scope are auditable.
- [ ] Dashboards are used to improve flow, not to rank individuals/teams on a single number.

Measuring time from change to usable requires a clear definition of change and usable, along with an auditable event chain from commit to runtime. By separating lead time into waiting, processing, rollout, and verification; tracking distributions alongside incomplete changes; and placing them next to quality metrics, teams can pinpoint real bottlenecks. Good improvements bring changes to users faster while preserving system correctness, safety, and resilience.
