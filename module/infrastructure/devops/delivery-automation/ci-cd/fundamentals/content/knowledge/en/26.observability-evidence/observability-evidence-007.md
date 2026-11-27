# Monitoring CI Service and Runner Health

## 1. Why Observe the CI Service and Runners?

CI/CD is a critical internal service for software development and release delivery. When the CI system slows down, runners fail to pick up jobs, queues grow, or artifacts fail to publish, development teams cannot integrate changes, catch defects early, or release on schedule. A green pipeline does not prove the entire CI platform is healthy; conversely, a failed pipeline does not automatically mean the fault lies in application code.

Observability of the CI service and runners helps answer:

- Can users trigger pipelines and receive results within expected timeframes?
- Are jobs waiting due to a lack of runners, concurrency limit locks, or dependency waits?
- Do runners have sufficient CPU, memory, disk, and network capacity to execute jobs?
- Did a job fail due to code, the execution environment, the CI platform, or an external service?
- Are artifacts, logs, and test evidence completely stored after a job completes?
- Are any runners missing heartbeats, stuck, outdated, or no longer picking up jobs?
- Did a configuration change or runner upgrade increase errors, duration, or costs?

Good monitoring separates pipeline failures from platform failures, detects degradation before users report it, supports capacity planning, and provides evidence for incident investigations. It also helps teams evaluate CI service quality by real developer experience rather than just counting successful jobs.

## 2. Scope of Observation in a CI Platform

A CI/CD service typically spans multiple layers. Monitoring only the runner machines misses failures in the control plane, queues, or artifact storage.

| Layer | Components | Questions to answer |
|---|---|---|
| Control plane | API, scheduler, webhooks, pipeline orchestrator, metadata database | Can users create and control pipelines? |
| Queue/scheduler | Job queue, dispatcher, concurrency controller | How long do jobs wait and why have they not been assigned a runner? |
| Runner fleet | Runner manager, agent, worker VM/container, executor | Are runners online, sufficiently provisioned, and executing reliably? |
| Job execution | Checkout, build, test, scan, package, deploy | Which stage is slow or failing? |
| Dependency | Git server, package registry, container registry, test database, cloud API | Which dependency is causing timeouts or throttling? |
| Artifact/evidence | Artifact store, cache, test reports, logs, provenance | Are results stored and fully retrievable? |
| Security boundary | Identity, secret provider, runner isolation, policy | Does the job have the right permissions and is the runner isolated? |
| User experience | Pipeline UI/API, notifications, status checks | Do developers receive results and feedback in a timely manner? |

A pipeline only succeeds when all involved layers coordinate properly. For example, the scheduler might create a job successfully while no runner picks it up; a runner might finish executing while artifact upload fails; or an artifact might be saved while the status webhook back to source control fails.

## 3. Distinguishing Metrics, Logs, Traces, and Events

Different telemetry types complement one another:

| Evidence type | Description | Used to answer |
|---|---|---|
| Metric | Numeric values aggregated over time | How many jobs are queued? Is the error rate rising? |
| Log | Event with rich content and context | Which job failed? What error did the runner report? |
| Trace | Span chain describing a request or workflow across components | Was time spent in the scheduler, queue, or runner? |
| Event | Discrete occurrence with timestamp and actor | When was a runner registered, a job retried, or a deployment cancelled? |

Metrics fit dashboards and trend alerting. Logs support deep investigation. Traces connect processing durations across services. Events create a timeline of state transitions such as pipeline created, job queued, runner assigned, job started, artifact uploaded, and pipeline completed.

Do not choose one telemetry type to replace all others. For instance, a job failure rate metric shows that errors increased, whereas logs and traces reveal whether failures cluster in dependency download or in application tests.

## 4. Defining SLIs and SLOs for the CI Service

A Service Level Indicator (SLI) measures one aspect of service quality. A Service Level Objective (SLO) is the quality target over a time window. For CI, select SLIs that reflect developer experience and result delivery capability.

Commonly useful SLIs:

- **Pipeline submission availability:** ratio of pipeline creation requests accepted successfully.
- **Queue wait time:** time from when a job is ready to run until a runner begins execution.
- **Job start latency:** time from job creation until execution starts.
- **Pipeline completion latency:** time from pipeline trigger until final outcome is available.
- **Platform-attributable failure rate:** ratio of jobs failing due to the platform, runners, or managed dependencies.
- **Runner availability:** percentage of time a runner pool maintains target available capacity.
- **Artifact availability:** ratio of published artifacts retrievable within required timeframes.
- **Evidence completeness:** ratio of finished jobs having all mandatory logs, reports, and metadata.

Illustrative SLO examples:

| SLI | Example target | Scope |
|---|---|---|
| Pipeline submission | 99.9% of pipeline creation requests accepted per month | API/control plane |
| Queue wait | 95% of standard-pool jobs start within 3 minutes | Eligible jobs, excluding intentionally locked jobs |
| Platform failure | Under 1% of jobs fail due to platform causes per month | Evidence-backed root cause classification |
| Artifact retrieval | 99.9% of in-retention artifacts downloaded successfully | Artifact repository |
| Evidence completeness | 99.5% of completed jobs include required logs and reports | Jobs belonging to evidence-required workflows |

These numbers illustrate how to define objectives. Real SLOs must rely on development team needs, historical data, workload types, and operational cost. Do not set an SLO simply because a number is easy to remember.

## 5. Measuring Queue Wait and Execution Time Separately

Total pipeline duration comprises multiple intervals:

\[
T_{pipeline} = T_{queue} + T_{execution} + T_{post-processing}
\]

Where:

- Queue time: time a job waits for the scheduler or a runner.
- Execution time: time the runner spends executing scripts, builds, tests, or deploys.
- Post-processing: artifact upload, report aggregation, status updates, and webhooks.

If you measure only total duration, teams cannot tell whether to optimize runners, build scripts, or the scheduler. A pipeline increasing from 8 to 18 minutes might be caused by a 10-minute spike in queue wait even though compilation time stayed unchanged.

Record timestamps for these milestones:

- Pipeline requested/created.
- Job queued.
- Job assigned to runner.
- Job started.
- Job finished.
- Artifact upload completed.
- Final status published.

From these milestones you can compute queue wait, runner startup, execution, upload, and post-processing. Use consistent definitions across dashboards and reports to avoid misleading comparisons.

## 6. Monitoring Runner Fleet State

Runners are the compute resources executing jobs. A runner reporting online is not necessarily ready to accept work; it might be out of disk, draining, lacking the right executor, or at its concurrent job limit.

States to monitor:

| State | Operational meaning |
|---|---|
| Online/healthy | Agent connected to control plane and eligible to accept jobs |
| Busy | Actively executing one or more jobs |
| Idle | Available to pick up matching jobs |
| Draining | Accepting no new jobs, waiting for current jobs to finish |
| Provisioning | Creating VM/container or starting the agent |
| Offline | Missing heartbeats or unreachable |
| Unhealthy | Resource, executor, or agent error present |
| Quarantined | Isolated under security/operational policy |
| Terminated | Lifecycle ended |

Total runner count does not equal usable runner count. Track online, idle, busy, draining, provisioning, and unhealthy counts segmented by pool, label, region, and trust class.

## 7. Heartbeats and Detecting Disconnected Runners

Runner managers typically emit periodic heartbeats or status updates so the control plane knows a runner is alive. If heartbeats stop, the scheduler can mark the runner offline and handle in-flight jobs via timeout or retry policies.

Useful fields:

- Last heartbeat timestamp.
- Heartbeat lag and consecutive missed count.
- Agent version and uptime since startup.
- Executor/runner type and labels.
- Currently running job or most recent job.
- Host/VM/container identity.
- Offline or termination reason if provided by the platform.

Do not alert on a single slightly delayed heartbeat if jitter or transient network blips occur. Base thresholds on heartbeat interval, missed count, and in-flight job state. For ephemeral runners, distinguish runners that finished cleanly and terminated by design from runners that disconnected abnormally.

## 8. Observing Runner CPU, Memory, Disk, and Network

Runners require adequate resources to execute workloads. Collect both utilization and throttling/saturation signals:

| Resource | Suggested metrics | Signs requiring investigation |
|---|---|---|
| CPU | utilization, load/run queue, throttled time | Job duration rises as concurrency increases |
| Memory | working set, available memory, swap, OOM events | Builds/tests get killed or GC stalls |
| Disk | free bytes, inodes, I/O latency, queue depth | Slow checkout/extract/upload or full workspace |
| Network | throughput, errors, retransmits, DNS latency | Dependency download timeouts |
| Process | process count, open file descriptors, thread count | Cannot spawn processes or sockets |
| Container | CPU/memory limits, throttling, restart count | Jobs constrained by cgroup/container quotas |

Tracking by runner pool and workload type helps pinpoint issues. For example, browser tests often require more memory than unit tests; image builds generate heavy disk I/O; integration tests may block on a database even while runner CPU remains idle.

## 9. Runner Capacity and Saturation

Capacity is maximum deliverable throughput; utilization is the fraction currently in use; saturation indicates resource contention or queue buildup. High utilization is not necessarily bad if wait times stay low, whereas rising saturation usually signals impending user impact.

Key signals:

- Ratio of busy runners to online runners.
- Queued jobs per eligible runner.
- p50/p95/p99 queue wait.
- New runner provisioning latency.
- CPU throttling and memory pressure.
- Rate of jobs hitting OOM or disk exhaustion.
- Ratio of offline or quarantined runners.

If a runner pool is constantly 100% busy and queue wait climbs, you may need extra capacity, tuned concurrency, workload partitioning, or reduced fan-out. If runners sit idle while jobs remain queued, check for label mismatches, resource locks, project quotas, or scheduler policies.

## 10. Tracking Ephemeral Runner Lifecycles

Ephemeral runners are created for a single job or short-lived batch and then destroyed. This pattern reduces workspace persistence and improves workload isolation, but requires observing the full lifecycle:

1. Provisioning requested.
2. VM/container created.
3. Agent boots and registers.
4. Runner accepts job.
5. Job executes and uploads outputs.
6. Agent deregisters or exits.
7. VM/container and temporary data are cleaned up.

Critical metrics include provisioning latency, startup failures, registration failures, job assignment delay, cleanup duration, orphan runner count, and provisioning cost.

A runner lingering after job completion may be an orphan; a runner terminated before uploading logs can lose evidence. Configure timeouts, cleanup policies, and evidence storage independent of the runner's ephemeral filesystem.

## 11. Monitoring Pipeline and Job States

Pipelines and jobs transition through multiple states: created, queued, running, waiting for approval, skipped, canceled, failed, succeeded, or timed out. Exact state names depend on the platform.

Metrics to track:

- Pipelines/jobs created over time.
- Counts currently queued/running/blocked.
- Success/failure/cancel/timeout rates.
- Retry counts and retry success rates.
- Rate of jobs skipped by workflow conditions.
- Time spent in each state.
- Count of hung or timed-out jobs.

Distinguishing code failures from platform failures is essential. Use exit codes, runner system errors, dependency errors, timeout reasons, cancellation actors, and stage names. Never classify every failed job as a CI platform error; doing so renders platform SLOs meaningless.

## 12. Failure Cause Taxonomy

A consistent taxonomy makes dashboards and incident reviews comparable:

| Category | Examples | Typical owner |
|---|---|---|
| Source/test failure | Compile error, unit test assertion failure | Development team |
| Runner failure | Agent crash, disk full, OOM, executor error | CI platform/runner team |
| Scheduler/queue | Job unassigned, queue stuck | CI platform |
| Dependency failure | Registry 429, database unavailable, cloud API timeout | Dependency owner or platform |
| Configuration/policy | Wrong runner label, permission denied, environment lock | Platform/security/release owner |
| Artifact/evidence | Upload failure, missing report, checksum mismatch | Platform/artifact owner |
| User cancellation | Developer cancelled pipeline or superseded commit | Requester/workflow policy |
| Unknown | Insufficient evidence to classify | Needs investigation, do not assign arbitrarily |

Leaving state as unknown when evidence is lacking is better than forcing it into code failure. A taxonomy should include definitions, examples, and rules for updating classification after investigation.

## 13. Monitoring Dependencies from CI's Perspective

CI often depends on services the platform team does not directly operate. Track latency, error rates, throttling, and timeouts when calling dependencies:

- Git hosting and webhook delivery.
- Package repositories and dependency proxies.
- Container registries.
- Secret managers and identity providers.
- Cloud provisioning APIs.
- Kubernetes API server and admission webhooks.
- Databases, message brokers, and test environments.
- Artifact stores, object storage, and caches.

CI-side metrics should tag dependency name, operation, and outcome. Never put tokens, credentialed URLs, or sensitive payloads in labels or logs.

If a registry slows down, many jobs may retry simultaneously and worsen the outage. Correlating dependency metrics with queue and retry metrics reveals the root issue instead of only showing rising job durations.

## 14. Caches and Artifact Stores Also Need Monitoring

Caches reduce download/build times, yet cache hit rate is not the sole objective. Stale caches or bad keys can cause inconsistent builds; mass cache misses can overload registries.

Track:

- Cache hit/miss rates by cache type.
- Cache download/upload latency.
- Cache size, evictions, and failed restores.
- Artifact upload/download success rates.
- Artifact transfer duration and throughput.
- Storage capacity, retention deletions, and replication lag.
- Checksum/digest verification failures.
- Jobs finishing without mandatory reports or artifacts.

Caches can be regenerated; release artifacts and evidence require stronger retention, integrity, and retrievability guarantees. Do not merge both into a single SLO when lifecycle requirements differ.

## 15. Structured Logging for Pipelines and Runners

Logs should use consistent fields to search and correlate components:

~~~json
{
  "timestamp": "2026-11-18T08:30:00Z",
  "level": "ERROR",
  "service": "ci-runner",
  "runner_id": "runner-42",
  "runner_pool": "linux-medium",
  "pipeline_id": "pipe-1042",
  "job_id": "job-3",
  "stage": "integration-test",
  "event": "dependency_timeout",
  "dependency": "integration-db",
  "duration_ms": 30000,
  "correlation_id": "corr-7f..."
}
~~~

Useful fields:

- Standardized timestamp and timezone.
- Severity/level.
- Service/component and version.
- Runner ID, pool, executor, and host identity.
- Pipeline ID, job ID, stage, and attempt.
- Event name, error category, and exit code.
- Dependency/operation.
- Duration and retry count.
- Trace ID/correlation ID if available.

Never log full environment variables, command lines containing tokens, secrets, private source code contents, or user data. Enforce masking, access controls, retention, and incident procedures if secrets accidentally enter logs.

## 16. Tracing a Pipeline Across Components

Distributed tracing connects requests from webhook receipt through pipeline completion. A trace may include spans such as:

~~~text
webhook_received
  └── pipeline_created
       └── job_queued
            └── runner_provisioned
                 └── runner_registered
                      └── job_started
                           ├── checkout
                           ├── dependency_restore
                           ├── build
                           ├── test
                           └── artifact_upload
       └── status_callback
~~~

Traces help locate slow segments within a specific run. When direct instrumentation of every build tool is not feasible, create spans in wrappers/orchestrators around major phases and attach trace context to logs.

Traces must not contain secrets or sensitive payloads. For pipelines with many independent jobs, use trace links or a shared correlation ID rather than forcing every job into one long trace that exceeds time limits. Review sampling settings so rare failures are not completely dropped.

## 17. Metric Naming, Labels, and Cardinality

Metrics should have names describing units and meaning, for example:

- **ci_jobs_queued**
- **ci_job_queue_wait_seconds**
- **ci_job_duration_seconds**
- **ci_job_failures_total**
- **ci_runner_online**
- **ci_runner_cpu_utilization_ratio**
- **ci_runner_memory_working_set_bytes**
- **ci_runner_disk_free_bytes**
- **ci_artifact_upload_duration_seconds**

Labels can include pool, executor, job type, stage, result class, and region. Avoid high-cardinality labels like pipeline ID, job ID, commit SHA, arbitrary branch names, or usernames on metric time series. Those identifiers belong in logs, traces, or events.

Excessive cardinality drives up storage and query costs and can cause metric drops. When drilling down from dashboards, link to logs/traces or event stores by pipeline ID instead of generating a separate time series per pipeline.

## 18. Prometheus Metric and Query Examples

An internal exporter or instrumentation may expose metrics such as:

~~~text
ci_jobs_queued{pool="linux-medium",priority="normal"} 14
ci_runner_online{pool="linux-medium"} 12
ci_runner_busy{pool="linux-medium"} 10
ci_job_failures_total{stage="integration-test",cause="dependency"} 23
ci_job_queue_wait_seconds_bucket{pool="linux-medium",le="60"} 120
ci_job_queue_wait_seconds_bucket{pool="linux-medium",le="180"} 185
~~~

Illustrative PromQL queries:

~~~promql
# Ratio of busy runners to online runners
sum(ci_runner_busy) / clamp_min(sum(ci_runner_online), 1)

# Job failure rate by stage and cause
sum by (stage, cause) (rate(ci_job_failures_total[15m]))

# p95 queue wait from histogram
histogram_quantile(
  0.95,
  sum by (le, pool) (rate(ci_job_queue_wait_seconds_bucket[15m]))
)
~~~

Metric and label names must match your actual exporter. These examples only illustrate representation and querying; if busy/online runner gauges are unsynchronized or histograms lack suitable buckets, adjust instrumentation before alerting on them.

## 19. Dashboards for Developers vs. Platform Operators

Do not cram everything into a single dashboard. Developers need to see where their pipelines stand; platform operators need fleet-wide and dependency health.

A developer dashboard can show:

- Pipeline status and current stage.
- Queue wait vs. execution time.
- Recent success/failure history.
- Job failure reasons and log links.
- Available vs. missing artifacts/reports.
- Runner pool in use.

A platform dashboard can show:

- Pipeline submission rate and control plane availability.
- Queue depth, oldest job age, and p50/p95 queue wait.
- Online/idle/busy/unhealthy runners by pool.
- CPU, memory, disk, network, and provisioning latency.
- Job failures/cancellations/timeouts by cause.
- Dependency latency, 429s, 5xx errors, and retry rates.
- Artifact/cache upload/download health and storage capacity.
- SLO/error budgets and active alerts.

Dashboards should provide drill-down links from overview to pipeline, job, runner, and traces/logs. Never display sensitive data on organization-wide public dashboards.

## 20. Designing Actionable Alerts

Good alerts communicate the problem, impact, urgency, and first investigative step. Avoid alerting merely because a metric crossed a threshold in one brief sample.

Example alert group:

| Alert | Suggested condition | Action |
|---|---|---|
| Queue wait elevated | p95 queue wait exceeds SLO over a sustained window | Check runner capacity, labels, locks, and scheduler |
| Runner pool unavailable | Healthy runners below minimum threshold | Check provisioning, agent, network, and quotas |
| Runner disk pressure | Free disk low or inodes nearly exhausted | Identify pool/job filling disk, clean up per policy |
| CI platform failure spike | Platform-attributable failure rate increases | Check control plane, runner rollout, and dependencies |
| Artifact upload failure | Upload failures exceed threshold | Check object store, credentials, network, and quotas |
| Dependency throttling | 429/timeout spikes | Reduce concurrency, apply backoff, and check quotas |
| Evidence missing | Job completed without mandatory reports | Check upload/finalization and retention path |

Alerts should include owner, runbook, dashboard link, and resolution criteria. Use grouping, inhibition, and deduplication to avoid sending hundreds of alerts for one underlying incident.

## 21. Error Budgets and Prioritizing CI Service Improvements

When an SLO defines an availability or queue wait objective, the error budget represents the allowable degradation within the evaluation window. When the error budget burns rapidly, teams can prioritize platform stability over shipping risky changes.

For example, with a 99.9% monthly availability target, the remaining allowance represents the corresponding error budget. Exact calculations must use the right SLI and exclude predefined states such as user-cancelled jobs or pipelines waiting on manual approvals.

Do not count every failed job against the CI platform's error budget. Test assertion failures caused by code belong to software quality; runner crashes or scheduler assignment failures belong to platform SLOs. Define and publish these boundaries clearly.

## 22. Protecting Telemetry and Evidence Data

CI logs, traces, and reports can contain source paths, branch names, usernames, internal endpoints, test data, or accidental secrets. Design observability together with security:

- Restrict log and artifact read access by project, environment, and role.
- Mask secrets before storage and test log redaction.
- Never log full environments or command lines containing credentials.
- Bound retention based on purpose and audit requirements.
- Encrypt data in transit and at rest per policy.
- Keep audit logs for access/deletion of sensitive evidence.
- Store evidence independently of ephemeral runners.
- Verify report/artifact integrity with checksums or signatures where needed.
- Maintain a response procedure if secrets or sensitive data appear in logs.

Not every log needs indefinite retention. Set distinct retention periods for operational logs, debug logs, test reports, release artifacts, and audit evidence based on utility and organizational obligations.

## 23. Distinguishing Platform Telemetry from Application Telemetry

CI platform metrics show whether jobs executed and runners functioned. Application telemetry shows whether the built/deployed software operates properly. Both must be linked without conflating their definitions.

Examples:

- CI job success rate: did the pipeline finish?
- Deployment success: was the workload applied?
- Post-deployment verification: is the version right and healthy?
- Application SLO: are users receiving service within targets?

A pipeline may succeed while the deployed application fails afterward. Conversely, the application may be healthy while a CI job fails due to an unrelated test or a temporarily offline runner. Dashboards should enable pivoting from a release ID to deployment records and application telemetry to find correlations.

## 24. Investigation Workflow When CI or Runners Degrade

When an alert fires, following an ordered workflow narrows down the scope quickly:

1. Determine scope: entire platform, one project, one pool, or one job type.
2. Check control plane/API and webhook delivery.
3. Check queue depth, oldest job age, and scheduler assignment.
4. Check runner online/idle/busy counts, heartbeats, and provisioning.
5. Check CPU, memory, disk, network, and executor errors.
6. Check dependency latency, quotas, 429/5xx responses, and retries.
7. Cross-reference pipeline/job logs, traces, and event timelines.
8. Identify recent changes: runner image, agent version, concurrency, secret policies, or registries.
9. Mitigate load or isolate the affected pool per runbook.
10. Verify service recovery using live queue wait, job starts, and job completions.

Do not restart the entire runner fleet immediately when queues grow. If the cause is registry throttling, restarting runners can trigger a pull burst and prolong the incident. Mitigation actions must follow evidence of the bottleneck.

## 25. Example: Analyzing a Growing Queue While Runners Sit Idle

Suppose the dashboard shows 40 jobs queued while 8 runners remain idle. This does not necessarily indicate a capacity shortage.

Hypotheses to test:

- Jobs request label `linux-large`, while idle runners only carry label `linux-small`.
- Jobs are blocked by a resource group or environment lock.
- The project hit its concurrency quota.
- Runners are online but not permitted to accept jobs from the pipeline's trust class.
- The scheduler has an error or a queue partition is stuck.
- Jobs request an architecture, region, or executor absent from the pool.

Workflow:

1. Inspect a representative queued job and read its requested labels/constraints.
2. Compare against labels, capacity, and trust class of idle runners.
3. Check concurrency/resource locks and project quotas.
4. Inspect scheduler events and assignment failure reasons.
5. Check whether a similar job gets assigned in another pool.
6. Fix the mismatch or quota if authorized, then observe queue age and assignment latency.

This example illustrates why total runner count alone is insufficient. Track capacity per pool/label and reasons why jobs remain unassigned.

## 26. Measuring Runner Fleet Operational Efficiency

Several metrics help evaluate efficiency:

- Runner utilization by pool and over time.
- p50/p95/p99 queue wait.
- Job throughput per runner-hour.
- Provisioning success rate and startup latency.
- Runner failure/replacement rate.
- Cost per successful job or pipeline.
- Rate of job retries due to runner/platform issues.
- Orphan runners and cleanup failures.
- Rate of jobs missing logs/reports/artifacts.

Very low utilization may suggest excess capacity; very high utilization accompanied by rising queue wait indicates insufficient capacity or poor scheduling. Do not optimize utilization in isolation: the goal is meeting SLOs at reasonable cost and risk.

## 27. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Monitoring only runner CPU | Misses queue, scheduler, and dependencies | Observe end-to-end from control plane to artifacts |
| Checking only total online runners | Unknown whether runners match labels/capacity | Segment by pool, executor, region, and trust class |
| Folding queue time into job duration | Cannot pinpoint bottlenecks | Record separate timestamps for each state |
| Blaming platform for every job failure | Skews SLOs and dashboards | Use a well-defined cause taxonomy |
| Using pipeline ID as a metric label | Cardinality explosion | Put IDs in logs/traces/events |
| Alerting on a single metric sample | Noise and false alarms | Use windows, baselines, and minimum sample rules |
| Mass-restarting runners when queues grow | Can worsen provisioning/pull bursts | Identify bottleneck before acting |
| Keeping logs indefinitely or without access control | Cost and data leak risk | Enforce retention, masking, and access control |
| Relying solely on cache hit rate | Can mask artifact errors or stale caches | Track integrity, upload/download, and build results |
| Not storing evidence outside runners | Loses logs when ephemeral runners terminate | Upload and verify evidence before cleanup |

## 28. CI and Runner Observability Design Checklist

Before putting a platform into production or scaling a runner fleet, verify:

- [ ] Architecture diagram covers control plane, queues, runners, dependencies, and artifact stores.
- [ ] SLIs/SLOs reflect submission, queue wait, job start, platform failures, and evidence availability.
- [ ] Timestamps are recorded across pipeline/job lifecycles to separate queue and execution time.
- [ ] Runners report heartbeats, lifecycle states, and pool/label/executor metadata.
- [ ] CPU, memory, disk, network, processes, and container throttling are tracked.
- [ ] Metrics exist for capacity, saturation, provisioning, and orphan runners.
- [ ] Job states, retries, cancellations, timeouts, and failure causes are classified.
- [ ] Dependency latency, quotas, 429/5xx errors, and retries are monitored.
- [ ] Artifact/cache uploads-downloads, integrity, and retention are tracked.
- [ ] Logs are structured with trace/correlation IDs and event timelines.
- [ ] Metric label cardinality is controlled.
- [ ] Dashboards separate developer and platform operator views.
- [ ] Alerts include owners, runbooks, severity, and resolution criteria.
- [ ] Evidence is masked, access-controlled, retained per policy, and stored outside ephemeral runners.
- [ ] Investigation runbooks exist for growing queues, lost runner heartbeats, and dependency throttling.
- [ ] Post-remediation recovery is verified via live metrics and recorded in timelines.

## 29. Core Practical Principles

1. Observe the entire CI service from control plane, queues, runners, and dependencies to artifacts/evidence.
2. Measure queue wait, execution, and post-processing separately to pinpoint the true bottleneck.
3. Track runners by pool, label, executor, and lifecycle; online does not mean eligible for every job.
4. Combine metrics, logs, traces, and events to view trends and investigate individual runs.
5. Set SLIs/SLOs around developer experience and cleanly separate platform errors from source/test failures.
6. Monitor runner resources and dependencies; do not tune concurrency by CPU alone.
7. Monitor artifacts, caches, and evidence for retrievability, integrity, and retention.
8. Use dashboards/alerts with context, owners, and runbooks for rapid response.
9. Protect telemetry from leaking secrets and sensitive data; store evidence independently of ephemeral runners.
10. Verify recovery using live queue, job start, completion, and actual user experience metrics.

Monitoring CI service and runner health turns a platform that normally only gets noticed when pipelines break into a measurable, proactively operated service. With clear SLIs/SLOs, telemetry linking pipelines to runners and dependencies, and actionable alerts, teams detect degradation early, pinpoint true root causes, and improve the reliability of the entire release process.
