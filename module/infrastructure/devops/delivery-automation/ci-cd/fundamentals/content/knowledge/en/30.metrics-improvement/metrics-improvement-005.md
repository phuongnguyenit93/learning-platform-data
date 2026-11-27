# Distinguishing Pipeline Metrics from Software Delivery Outcomes

## Learning objectives

After this lesson, learners will be able to:

- Distinguish metrics measuring pipeline efficiency and reliability from metrics measuring software delivery outcomes.
- Identify measurement layers from CI jobs, pipeline runs, release flow, and production services to customers and business goals.
- Select appropriate metrics for wait time, execution time, failure rate, release speed, stability, and user-received value.
- Understand the relationships and interpretation limits of DORA metrics, flow metrics, SLOs, and product metrics.
- Design contextual, segmented dashboards that link pipeline runs to releases, deployments, and operational outcomes.
- Avoid optimizing a local metric in ways that degrade quality or software delivery outcomes.
- Establish baselines, improvement goals, and evidence-based feedback loops.
- Use data to locate bottlenecks and run improvement experiments rather than creating reporting pressure or ranking individuals.

## 1. Why distinguish these two groups of metrics?

CI/CD systems typically provide a wealth of numbers: build duration, runner wait time, job success rate, test execution time, deploy count, and rollback rate. These numbers help explain how the pipeline behaves, but they do not by themselves prove that the delivered software creates value.

For example:

- A pipeline finishes in 4 minutes, yet releases wait 5 days for manual approval.
- Build success rate reaches 99%, yet post-deploy user error rates increase.
- A team increases daily deployments yet has to roll back frequently.
- Unit tests run fast and pass, yet integration bugs only appear in production.
- Runner utilization is very high, yet the time from when a request is accepted until customers receive the feature does not drop.

These situations show the need to separate:

**Pipeline metrics** measure the efficiency, capacity, and reliability of the CI/CD system: whether pipelines trigger properly, how long jobs wait, how long builds/tests take, whether runners have sufficient capacity, and whether workflows fail often.

**Software delivery outcomes** measure the results of the entire process of bringing changes into the target environment and their impact: how fast changes reach production, whether releases cause incidents, whether services meet SLOs, and whether users experience improvements.

The pipeline is one part of the software delivery system. Improving the pipeline can contribute to better delivery, but the two metric groups cannot substitute for one another.

## 2. Four measurement layers to distinguish

A measurement system can be organized into four layers. Each layer answers a different kind of question and needs to be linked via shared identifiers.

| Layer | Subject measured | Core question | Examples |
|---|---|---|---|
| 1. Pipeline execution | Jobs, workflows, runners | Does CI/CD run fast and reliably? | Queue time, job duration, pipeline success rate |
| 2. Delivery flow | Changes, releases, deployments | How do changes move from request to production? | Lead time, deployment frequency, throughput, WIP |
| 3. Service/operational outcome | Services after deployment | Do changes keep the service stable? | SLO, error rate, latency, change failure rate |
| 4. Customer/business outcome | Users and product goals | Does the software create the desired value? | Adoption, task completion, conversion, customer satisfaction |

~~~mermaid
flowchart TD
    A["Pipeline execution metrics"] --> B["Delivery flow metrics"]
    B --> C["Service and operational outcomes"]
    C --> D["Customer and business outcomes"]
    A -. "Supporting capability" .-> C
    B -. "Release impact" .-> C
    C -. "Real experience" .-> D
~~~

The layers are related, though not via automatic cause-and-effect. For instance, reducing pipeline duration may trim part of lead time, yet if review or approval wait times stay unchanged, overall lead time may barely move.

Similarly, increasing deployment frequency does not guarantee better customer outcomes if releases fail to address actual needs or raise defect rates.

## 3. What do pipeline metrics measure?

Pipeline metrics help platform teams and development teams understand the capability of the automation system.

### 3.1. Wait time (queue time)

Queue time is the duration from when a job is ready to run until a runner is assigned and execution begins.

It can rise due to:

- Insufficient runners or concurrency quotas.
- Many pipeline runs executing simultaneously.
- Mismatched runner labels.
- Concurrency groups serializing jobs.
- Unfinished approvals or dependencies.
- Cloud capacity or rate limits.

Distinguish queue time from job execution time. If a job takes 2 minutes to run yet waits 15 minutes for a runner, optimizing build scripts will not resolve the main bottleneck.

### 3.2. Job duration and pipeline duration

- Job duration measures the execution time of a single job.
- Pipeline duration measures the span from trigger or start until the pipeline reaches its final state.
- Critical path duration measures the time of the longest dependency chain in the DAG.

Pipeline duration must be defined consistently. Some systems count from event arrival to run creation; others count only from runner start. When comparing, state start and end points clearly.

### 3.3. Pipeline success rate

You can compute the ratio of successful runs to total evaluated runs over a period:

\[
Success\ Rate =
\frac{Successful\ Runs}{Eligible\ Runs}\times 100\%
\]

Establish rules for handling:

- Runs canceled because a newer commit superseded them.
- Manually canceled runs.
- Runs skipped by policy.
- Runs failing due to source code/tests.
- Runs failing due to runners, registries, or external services.
- Retried runs and multiple attempts.

If every canceled status is counted as a failure, the rate may misrepresent pipeline quality. If all canceled runs are excluded without recording reasons, teams might hide problems by canceling failing runs.

### 3.4. Flaky test rate

A flaky test produces inconsistent outcomes despite equivalent source code and execution conditions. Trackable metrics:

- Rate of tests that fail and then pass on retry.
- Count of confirmed flaky tests.
- Percentage of runs affected by flaky tests.
- Pipeline time wasted on retries.
- Number of test quarantines or disables.

Do not treat a retry pass as a normal pass while ignoring the first failure. The initial failure is evidence about test suite reliability and must be classified.

### 3.5. Runners and resources

Common metrics:

- Runner utilization.
- CPU, memory, and disk pressure.
- Queue depth.
- Concurrent job count.
- Runner disconnect rate.
- Runner provisioning time.
- Cache hit rate.
- Artifact upload/download duration.

High runner utilization is not automatically good. If constantly near 100%, new pipelines may queue for long periods and emergency releases may lack capacity. If utilization is low while queue time is high, the bottleneck may lie in quotas, labels, or concurrency policies.

## 4. What do delivery flow metrics measure?

Delivery flow metrics observe how a change moves through the system from acceptance to release.

### 4.1. Lead time for changes

Lead time for changes typically measures the duration from when a change is committed or integrated into the main branch until it is successfully deployed to production. Define a consistent start point aligned with the organization's development model.

Lead time can be influenced by:

- Review time.
- CI wait time.
- Time fixing pipeline failures.
- Waiting for security or product approvals.
- Batch releases or change windows.
- Deploy and verification duration.
- Manual steps or cross-team dependencies.

Do not confuse lead time with pipeline duration. A pipeline may run in 10 minutes, yet a change waits 2 days for review and another 3 days for a release window.

You can also measure stage-by-stage segments to locate bottlenecks:

- Commit to PR review.
- PR open to merge.
- Merge to artifact.
- Artifact to deployment.
- Deployment start to verified release.

### 4.2. Deployment frequency

Deployment frequency measures how often changes are deployed to production within a given period.

Define what a deployment is:

- One deploy of one service?
- One release of a product?
- One change to the production environment?
- One successful deployment after verification passes?

If each service deploys independently, measure per service or group of services sharing a lifecycle. Do not sum deploy counts across multiple services into one number without preserving context.

High deployment frequency can help shrink batch sizes and accelerate feedback. However, if frequent deployments do not reach users or degrade quality, high frequency is not the end goal.

### 4.3. Throughput and flow efficiency

Throughput is the number of completed changes per unit of time, such as work items or changes deployed per week.

Flow efficiency examines the ratio of time work is actively processed to total lead time. The remainder is typically time waiting for reviews, dependencies, environments, or decisions.

For example, a change takes 10 days from start to production, yet only 12 hours are spent writing/testing code. Most lead time sits in waiting time. Speeding up the build by 5 minutes will not solve the primary problem.

### 4.4. Work in progress (WIP)

WIP is the number of changes currently in flight and not yet finished. Excessive WIP can:

- Increase context switching.
- Prolong review times.
- Increase branches needing rebase or merge.
- Raise conflict probability.
- Make it hard to tell which change is blocking a release.
- Increase concurrent changes risking production stability.

Limiting WIP and shrinking batch sizes usually make the software delivery flow more predictable.

## 5. DORA metrics and how to interpret them

DORA researches software delivery and operational performance. The commonly referenced metric set includes:

- Deployment frequency.
- Lead time for changes.
- Change failure rate.
- Failed deployment recovery time (referred to in many earlier publications as time to restore service).
- Deployment rework rate added in recent DORA models.

Names and definitions can vary across report editions and measurement frameworks. Specify clearly which framework version or internal definition is in use.

| Metric | Meaning | Measurement layer |
|---|---|---|
| Deployment frequency | Cadence of production deployments | Delivery flow |
| Lead time for changes | Time from change to production | Delivery flow |
| Change failure rate | Percentage of deploys requiring remediation or causing service degradation | Service/delivery outcome |
| Failed deployment recovery time | Time to recover after a failed deploy | Service/operational outcome |
| Deployment rework rate | Percentage of unplanned deploys performed to fix or remediate production issues | Delivery/service outcome |

These are not pure pipeline metrics. They reflect the performance of the entire delivery system—people, processes, architecture, testing, operations, and platforms.

### 5.1. Change failure rate

A simple formula:

\[
CFR =
\frac{Deployments\ causing\ failure}{Total\ production\ deployments}
\times 100\%
\]

However, you must define what counts as a failure:

- User-impacting incident.
- Rollback or hotfix.
- SLO burn exceeding threshold.
- Degradation requiring intervention.
- Deployment needing unplanned remediation.

If each organization uses different definitions, do not compare CFR directly across teams.

Link incidents or remediations to deployment IDs to identify which change was involved. Not every incident occurring after a deploy was caused by that deploy; attribution rules and reviews are required.

### 5.2. Failed deployment recovery time

This metric measures the duration from when a deployment-induced failure or degradation is identified until the service is restored to an acceptable state.

Define the end milestone:

- Traffic shifted back to the old version?
- Error rate back below threshold?
- SLO restored?
- Users able to complete business workflows?
- Data integrity verified?

Merely completing a rollback command does not guarantee the service has recovered. If data is corrupted or queue backlogs remain unprocessed, recovery is incomplete.

### 5.3. Deployment rework rate

Deployment rework rate reflects the share of unplanned deployments executed to fix production issues, such as hotfixes or corrective deployments.

This metric adds visibility into release volume spent fixing mistakes. Distinguish rework from planned deployments like feature rollouts or scheduled maintenance.

## 6. Service outcomes: does the software run well after deploy?

A technically successful release can still cause a service to perform poorly. Therefore, measure runtime outcomes.

Common metrics:

- Availability or success rate.
- Error rate by endpoint and version.
- Latency p50, p95, p99.
- CPU, memory, and connection pool saturation.
- Queue lag and processing delay.
- Dependency availability.
- Restart/crash rate.
- SLO compliance and error budget consumption.
- Business transaction success rate.

An SLI measures an aspect of service performance users care about. An SLO is the target for an SLI over a time window. For example, an SLI might be the percentage of successful API requests, while the SLO sets a 99.9% target over 30 days.

Pipeline metrics tell whether jobs finished. SLIs/SLOs tell whether the service meets operational expectations after deploy.

Do not use CPU utilization as the sole proxy for service health. A service with low CPU yet high payment failures is still an unhealthy service. Combine technical signals and business signals.

## 7. Customer and business outcomes

The final layer asks whether the software creates the results desired by users or the business.

Examples:

- Percentage of users completing checkout.
- Percentage of successful payment transactions.
- Time to complete a task.
- User retention/return rate.
- Onboarding completion rate.
- Number of feature-related support tickets.
- Customer satisfaction or NPS if used by the organization.
- Conversion rate or product-appropriate revenue metrics.

These metrics are influenced by many non-technical factors: market demand, UX, pricing, campaigns, seasonality, and changing user behavior. Do not attribute every fluctuation to a single release or to the pipeline.

Tie product metrics to the specific goal of a change. For example, a checkout-optimization release should track completion rate, payment success, and latency, rather than only tracking deploy counts.

## 8. Relationship between pipeline metrics and delivery outcomes

Pipeline metrics are often leading indicators for part of delivery capability. Delivery and service outcomes are often lagging outcomes, though not every metric fits a strict dichotomy.

Example hypothesis chain:

1. Lowering queue time helps jobs start sooner.
2. Shortening pipeline duration gives developers faster feedback.
3. Faster feedback can shorten bug fixing and merge wait times.
4. Smaller changes can be released more frequently.
5. Smaller batches can reduce blast radius when defects happen.
6. Combining strong tests and observability can lower change failure rate.
7. More stable services can improve user experience.

Each arrow is a hypothesis requiring verification. If review time accounts for most lead time, cutting build duration will not noticeably change lead time. If test suites lack integration coverage, raising deployment frequency can drive change failure rate up.

~~~mermaid
flowchart TD
    A["Pipeline queue/duration"] --> B["Feedback speed"]
    B --> C["Delivery lead time and batch size"]
    C --> D["Deployment frequency"]
    D --> E["Change failure and recovery"]
    E --> F["Service reliability / SLO"]
    F --> G["Customer task success"]
    H["Review, policy, architecture, team capacity"] --> C
    I["Test quality and observability"] --> E
    J["Product design and user needs"] --> G
~~~

Measurement should test the hypothesis chain, not just prove that a single metric went up or down.

## 9. Example: faster pipeline, yet delivery is no faster

A team improves dependency caching and runners. Results:

| Metric | Before | After |
|---|---:|---:|
| Median pipeline duration | 18 minutes | 8 minutes |
| Median queue time | 6 minutes | 1 minute |
| PR review waiting | 2.5 days | 2.4 days |
| Lead time for changes | 4.2 days | 4.0 days |
| Deployment frequency | 3 times/week | 3 times/week |

The pipeline clearly improved, yet lead time and deployment frequency barely budged. That does not mean pipeline optimization was useless. It shows a larger bottleneck sits in review or release processes.

Next steps should analyze review wait times, PR revision rounds, reviewer capacity, and release batching rules. Further optimizing runners will yield smaller returns than improving the review flow.

## 10. Example: deployment frequency increases, yet outcomes worsen

A team switches from weekly releases to deploying multiple times a day. Pipeline duration drops and deployment frequency climbs. However:

- Change failure rate rises.
- Hotfixes and rollbacks become more frequent.
- Error budget burns rapidly.
- Support tickets rise.
- User task completion rate falls.

This signals the team is optimizing release speed without sufficient quality controls or proper change decomposition.

Examine:

- Test coverage and test reliability.
- Batch size of each release.
- Canary and post-deploy verification.
- Feature flags and blast-radius containment.
- Schema and API compatibility.
- Alerting and rollback/recovery readiness.
- Readiness of on-call operators.

The goal is not to force deployment frequency back down at all costs. Find ways to preserve fast feedback while increasing the safety of each change.

## 11. Designing a metric tree for a specific goal

A metric tree connects a high-level goal with actionable metrics.

Example goal: reduce time to deliver valuable changes to users while preserving reliability.

~~~mermaid
flowchart TD
    A["Goal: deliver value fast and safely"]
    A --> B["Flow"]
    A --> C["Quality and reliability"]
    A --> D["Customer outcome"]
    B --> E["Lead time"]
    B --> F["Deployment frequency"]
    B --> G["WIP / waiting time"]
    C --> H["Change failure rate"]
    C --> I["Recovery time"]
    C --> J["SLO / error budget"]
    D --> K["Task completion"]
    D --> L["User adoption"]
    D --> M["Support contacts"]
~~~

From the metric tree, the team picks one or two bottlenecks to improve in a cycle. There is no need to set targets for every metric simultaneously.

For example, if lead time is high due to review waiting, leading indicators can be review wait time and open PRs per reviewer. If change failure rate is high due to migrations, measure migration failure rate, compatibility check duration, and data-change-related incidents.

## 12. Defining metrics before building dashboards

Every metric needs a clear definition so teams do not interpret it differently.

Document for each metric:

- Name and purpose.
- Unit.
- Formula.
- Population and scope.
- Start/end points if measuring time.
- Time window.
- Data source.
- Exclusion rules.
- Handling of missing/duplicate data.
- Owner.
- Required segments.
- Interpretation caveats.

Example pipeline duration definition:

| Attribute | Sample definition |
|---|---|
| Name | Pipeline duration |
| Unit | Minutes |
| Start | Timestamp when workflow run is created |
| End | Timestamp when run reaches final status |
| Population | CI validation runs of the repository |
| Exclusions | Manual test runs outside standard workflows, if explicitly documented |
| Aggregation | Weekly median and p90 |
| Segments | Repository, branch class, workflow type |
| Owner | Platform engineering |
| Caveat | Excludes time from commit to event receipt if the system does not provide that timestamp |

Specify clearly whether a pipeline retry counts as a new run or an attempt of the same run. Otherwise, duration and success rate may be double-counted.

## 13. Baselines, percentiles, and segmentation

Averages can hide abnormally slow cases. Examine medians and percentiles when analyzing durations.

- Median (p50) describes the typical experience.
- p90/p95 shows the slower tail of runs.
- p99 can be useful for pipelines with sufficient run volume.
- Mean helps estimate total resource usage, though sensitive to outliers.

For example, pipeline duration p50 is 8 minutes while p95 is 45 minutes. Shaving 1 more minute off the median may matter less than fixing the slow tail caused by runner labels or integration environments.

Segment by:

- Repository or service.
- Workflow type: PR, main, release, nightly.
- Language/build tool.
- Runner class.
- Change size or test group.
- Environment.
- Deployment strategy type.

Never rank teams using unnormalized numbers. A large monolith with heavy integration tests cannot be compared directly to a small library running only unit tests.

## 14. From correlation to causation

If pipeline duration drops at the same time as lead time, pipeline optimization is not necessarily the sole cause. Change volume may have dropped, reviewers may have been added, or the release process may have changed.

To evaluate an improvement:

1. State a specific hypothesis.
2. Identify the primary metric and guardrail metrics.
3. Record a baseline prior to the change.
4. Roll out the improvement in an appropriate scope.
5. Monitor over a sufficiently representative period.
6. Segment data to minimize effects of workload differences.
7. Compare against baseline or a control group if feasible.
8. Document confounding factors and conclusion limits.
9. Decide to keep, adjust, or revert the improvement.

Example hypothesis: increasing runner capacity will lower queue time. Primary metric is queue time p50/p95; guardrails are runner cost and utilization. If queue time drops while cost surges sharply, evaluate the trade-off.

Another experiment: limiting WIP may lower lead time. Primary metric is lead time; guardrails are throughput and delayed work items. Observe multiple cycles to avoid concluding from one low-change week.

## 15. Avoiding metric gaming and perverse optimization

When metrics become reward/punishment targets, people may optimize numbers instead of outcomes.

Examples:

| Mis-optimized metric | Possible behavior | Needed guardrail |
|---|---|---|
| Pipeline duration | Dropping slow tests or moving tests outside statistics | Test scope, escaped defects, quality gates |
| Build success rate | Retrying until green and reporting only the last run | First-attempt success and flaky test rate |
| Deployment frequency | Creating many tiny valueless deployments | Change outcomes, failure rate, user impact |
| Lead time | Splitting or shifting ticket states to shrink measured time | Workflow definitions and timestamp audits |
| Coverage | Writing weak assertions just to raise percentages | Mutation testing, defect escape, and review |
| Incident count | Failing to log minor incidents | SLOs, support signals, and blameless reporting |
| Runner utilization | Keeping runners busy even as queues grow | Queue time, cost, and service priority |

Never use a single metric to evaluate individual productivity. Metrics belong to diagnosing system issues and improving workflows, not inferring who works hard or poorly.

DORA also emphasizes assessing capabilities at the team/service level in context rather than using metrics to build simplistic leaderboards.

## 16. Dashboards tailored to each audience

A good dashboard answers the viewer's questions rather than cramming every metric onto one screen.

### Platform engineering

Focuses on:

- Queue time and runner capacity.
- Pipeline/job failures by cause.
- Cache effectiveness.
- Runner provisioning.
- CI cost.
- Workflow version adoption.

### Development team

Focuses on:

- PR feedback time.
- Build/test duration.
- Flaky tests.
- Time to merge.
- Lead time.
- Service-related change failures.

### QA

Focuses on:

- Test suite duration.
- Pass/fail/skipped/error counts.
- Flaky test rate.
- Defect escape.
- Coverage and test scope.
- Regression trends.

### Security

Focuses on:

- Findings by severity and age.
- Remediation time.
- Scan coverage and freshness.
- Exceptions with expiration dates.
- Artifact provenance and policy compliance.

### Operations/SRE

Focuses on:

- Deployment frequency.
- Change failure rate.
- Recovery time.
- SLO/error budget.
- Rollout health.
- Incident and rollback trends.

### Product/business

Focuses on:

- Feature adoption.
- Task success.
- Customer feedback.
- Conversion or business KPIs.
- Post-release impact.

Dashboards can share underlying data sources while presenting appropriate views. Do not ask a product owner to interpret runner CPU or hold the platform team directly accountable for conversion rate.

## 17. Linking data through release and deployment identity

To connect pipeline metrics with delivery outcomes, stable identifiers are required:

- Repository ID.
- Commit SHA.
- Pull request/change ID.
- Pipeline run ID and attempt.
- Artifact digest.
- Release ID.
- Deployment ID.
- Environment ID.
- Service/version label.
- Incident ID.
- Trace/correlation ID.

Example data chain:

~~~text
Commit SHA
   |
   v
Pull Request / Change ID
   |
   v
Pipeline Run ID
   |---- Queue time / Job duration
   |---- Test and scan results
   |
   v
Artifact digest
   |
   v
Release ID
   |
   v
Deployment ID + Environment
   |---- Deployment frequency
   |---- Verification result
   |
   v
Service telemetry / Incident
   |---- SLO / Change failure / Recovery
   |
   v
Customer or business metric
~~~

Without these links, a team might know an incident happened without knowing which release was involved; or know the pipeline got faster without knowing which changes actually reached production.

Attach release IDs/versions to logs, metrics, and traces while controlling cardinality. Avoid using full commit SHAs or user IDs as high-cardinality metric labels; detailed identifiers belong in traces/logs or release records.

## 18. Data-driven improvement loop

Measurement creates value only when it leads to action and verification of results.

A practical loop:

1. **Observe:** gather trustworthy metrics and evidence.
2. **Diagnose:** analyze bottlenecks or missed outcomes.
3. **Hypothesize:** state likely root causes and improvement approaches.
4. **Experiment:** test a bounded change with guardrails.
5. **Evaluate:** compare against baseline and check side effects.
6. **Standardize:** keep effective improvements, update pipelines or policies.
7. **Review:** check whether metrics remain relevant and free of perverse incentives.

~~~mermaid
flowchart TD
    A["Observe metrics and evidence"] --> B["Diagnose bottleneck"]
    B --> C["Form a testable hypothesis"]
    C --> D["Run a bounded experiment"]
    D --> E["Evaluate outcomes and guardrails"]
    E --> F{"Improvement sustained?"}
    F -- "Yes" --> G["Standardize and document"]
    F -- "No" --> H["Adjust or revert"]
    G --> I["Review metric definitions"]
    H --> I
    I --> A
~~~

Do not create too many improvement goals at once. Pick one major bottleneck, assign an owner and evaluation window, and only then move to the next issue.

## 19. Data-driven improvement example

An organization observes:

- Pipeline duration p50: 12 minutes.
- Queue time p50: 4 minutes.
- Lead time for changes: 3.5 days.
- Deployment frequency: 4 times/week.
- Change failure rate: 8%.
- SLO met at 99.95%.

Analysis:

1. Queue time makes up a substantial share of pipeline duration; examine runner capacity and concurrency policies.
2. Lead time of 3.5 days far exceeds pipeline duration; measure review waiting, approvals, and release batching.
3. An 8% change failure rate needs breakdown by change type, service, and failure mode.
4. SLO meets target currently, yet error budget and per-release trends need inspection.
5. Deployment frequency should not be pushed higher before understanding change failure causes.

Two separate experiments can be selected:

**Experiment A — Runner scheduling**

- Hypothesis: scaling the right runner pool and capping fan-out will reduce queue time.
- Primary metric: queue time p50/p95.
- Guardrails: runner cost, utilization, and pipeline failures.
- Scope: a representative group of repositories.

**Experiment B — Reducing change failures**

- Hypothesis: adding integration tests for recurring failure paths and canary verification will lower failures.
- Primary metric: change failure rate.
- Guardrails: lead time, deployment frequency, and test duration.
- Scope: one service with a clear incident trend.

After each experiment, verify sufficiently large and representative sample data before rolling out organization-wide.

## 20. Common anti-patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Treating pipeline duration as lead time | Ignores review, approval, and release waits | Measure every stage of delivery flow |
| Treating pipeline success as release success | Misses runtime errors or user impact | Combine deployment verification and SLOs |
| Increasing deployment frequency at all costs | Change failures and rework climb | Track both speed and stability |
| Using a single average | Hides slow run cohorts | Inspect p50/p90/p95 and segment |
| Comparing teams with different workloads | Unfair conclusions | Normalize scope and context |
| Retrying and ignoring first-attempt failures | Flaky tests stay hidden | Track retries and flaky rates separately |
| Setting absolute coverage targets | Encourages weak tests | Combine risk-based testing and defect escape |
| Counting all deploys identically | Fails to distinguish services and change types | Define deployment units clearly |
| Blaming every post-deploy incident on the release | Wrong attribution | Link deployments and review root causes |
| Using metrics to rank individuals | Drives gaming and harms collaboration | Use metrics to improve systems |
| Dashboards without owners | Numbers lead to no action | Tie metrics to people and decisions |
| No baseline | Cannot tell if improvements worked | Capture baseline before experiments |

## 21. Measurement system design checklist

Before using metrics to steer CI/CD, confirm:

- [ ] Pipeline execution, delivery flow, service outcomes, and customer/business outcomes are layered clearly.
- [ ] Pipeline duration, queue time, and job duration have distinct definitions.
- [ ] Pipeline runs, attempts, retries, canceled runs, and skipped runs are handled consistently.
- [ ] Lead time has clear start and end points.
- [ ] Deployment frequency defines the deployment unit.
- [ ] Change failures and recoveries have attribution to deployments.
- [ ] SLOs/SLIs reflect critical service experiences.
- [ ] Product metrics align with the specific objectives of changes.
- [ ] Primary metrics and guardrails exist for every improvement experiment.
- [ ] Baselines and measurement windows are recorded.
- [ ] Medians/percentiles are used where appropriate.
- [ ] Data is segmented by service, workflow, runner, and change type.
- [ ] Release/deployment identities connect pipelines with runtime.
- [ ] Metrics have owners and decision-makers.
- [ ] Missing data and definition changes are documented.
- [ ] No single metric is used to judge individuals or teams.
- [ ] Periodic reviews check for metric gaming.
- [ ] Improvement results are evaluated against outcomes and guardrails.

## 22. Self-assessment exercise

A team reports over the past month:

- Pipeline duration dropped from 20 to 9 minutes.
- Pipeline success rate rose from 92% to 98%.
- Deployment frequency rose from 2 to 8 times/week.
- Lead time for changes stayed at 4 days.
- Change failure rate rose from 4% to 11%.
- Median recovery time rose from 25 to 50 minutes.
- User checkout completion rate dropped by 3%.
- Runner utilization rose to 95%.

Analyze:

1. Which metrics measure pipeline execution?
2. Which metrics reflect delivery flow?
3. Which metrics reflect service/customer outcomes?
4. Why did the pipeline improve while lead time stayed flat?
5. How might rising deployment frequency relate to the change failure rate?
6. What does rising recovery time indicate about operational capability?
7. What risks might 95% runner utilization create?
8. How should release IDs, deployment IDs, and checkout metrics be linked for analysis?
9. Which improvement experiment should be prioritized first and which guardrails should be monitored?
10. What additional data is needed before concluding the releases caused the checkout drop?

A strong answer does not try to invent one single composite score. Classify the metrics, locate bottlenecks, form a testable hypothesis, and propose a bounded experiment.

## Conclusion

Pipeline metrics tell how fast and reliably the CI/CD system executes work. Software delivery outcomes tell whether changes reach production properly, keep services reliable, and create user value. The two groups are related yet not interchangeable.

Measure from pipeline execution through delivery flow to service and customer outcomes; connect them using commit, artifact digest, release, and deployment IDs. Define metrics clearly, inspect percentiles and context, and pair speed metrics with stability and user outcomes. Use data to find bottlenecks, run improvement experiments, and check guardrails rather than optimizing isolated numbers or ranking people.
