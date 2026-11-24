# Roadmap from Health Checks to Observing a Running Application

You have called `/actuator/health` and seen the application return `UP`. That is a useful starting point: the application now provides a health signal that external tools can read. The next step is knowing what that signal reflects, then adding data to monitor service quality and investigate when problems arise.

The goal of this roadmap is to take you from **reading status at a point in time** to **understanding what is happening to the application in an operational environment**. Each milestone has a question, a hands-on step, and evidence showing you have understood it. Configuration examples use Spring Boot 3.3 as the baseline.

## 1. Envision the Destination Before Picking Tools

**Observability** is the ability to understand a system’s internal state and behavior from the data it emits. It becomes valuable when you need to ask follow-up questions after an anomaly, rather than only looking at prebuilt charts. See [OpenTelemetry — Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/).

One way to structure the learning path:

```text
Read health accurately
        ↓
Understand work acceptance readiness
        ↓
Measure load, errors, latency, and resources
        ↓
Retain history and verify the collection pipeline
        ↓
Measure business outcomes, link events to execution paths
        ↓
Detect impact and practice incident response
        ↓
Review lessons, improve signals and rules
```

This is a sequence for building understanding. In practice, many steps run in parallel; protecting data and access control must be done from the start.

| When you have this question | Which capability should you progress toward? |
| --- | --- |
| What status is the application reporting? | Reading and interpreting health |
| Should this running instance accept more work? | Understanding liveness/readiness and how the platform uses them |
| How slow or error-prone is the service? | Reading metrics with units, intervals, and scope |
| Did the issue start before or after a specific change? | Having history, version identity, and deployment markers |
| Which job was affected, and at which step did it slow down? | Having business metrics, correlated logs, and traces |
| When should we act, and how? | Having targets, alerts, runbooks, and post-action verification |

Throughout this lesson, imagine a service that receives files for background processing. Users care whether valid files are processed accurately and on time. Knowing the server is still up answers only a small part of that question.

## 2. Prepare an Application and a Clear Observation Scope

Use an existing Spring Boot web application with the `spring-boot-starter-actuator` dependency. You do not need to create extra business APIs just to begin reading operational data.

Before running commands, record clearly:

- Are you observing a study environment or a production environment?
- What are the service name, software version, and specific running instance?
- Which time zone is used for timestamps?
- Who is authorized to read management data?
- What are the current management path and port?

In the commands below, assume the app runs at `localhost:8080`, the root path is unchanged, and Actuator uses the default `/actuator` prefix. If configured differently, use the real address. Spring Boot lets you change management path and port; refer to [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

The YAML snippets are per-milestone configurations. When applying them together, merge into one valid `management` tree in your study environment’s config without creating duplicate keys at the same level. If the app uses Spring Security, follow your existing authentication and authorization rules.

## 3. Milestone 1 — Read Health Check Results Accurately

**Question:** what health status is the application reporting, based on which checks?

Try calling on Windows:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

On Linux/macOS, use the corresponding `curl` command. Record both the HTTP status code and the actual response body.

A minimal illustrative response:

```json
{
  "status": "UP"
}
```

This is a structural example, not a guaranteed response for every call. Responses may contain components and details depending on configuration, permissions, and actual state. See [Actuator Health REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 3.1. Interpret Health Scope Properly

Health aggregates configured checks. You need to know which checks participate and what conditions make them change.

In a file-processing service, a database connectivity check can succeed while the job queue grows rapidly. Or the process still reports healthy while a business bug produces wrong output data. Never stretch a check’s conclusion beyond what it actually verifies.

In Spring Boot 3.3, only the `health` endpoint is exposed over HTTP by default. Enabling an endpoint, exposing it over HTTP, and authorizing users to access it must be verified separately. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.2. Practice and Milestone Completion Evidence

In a test environment, identify one real health check component in your application. Read that check’s configuration or documentation, then note:

```text
Hypothetical check: test connection to the data store.
Healthy: the designed connectivity test succeeds.
Unhealthy: the connectivity test fails.
Not covered: output correctness and per-file processing deadlines.
```

This is a note template filled with a hypothetical check. Replace it with a real check and exact conditions from your application; this template is not configuration.

**Milestone achieved when:** you can explain why the current result appears and name at least one user-facing failure scenario where health still reports good.

## 4. Milestone 2 — Distinguish Liveness from Readiness to Accept Work

**Question:** does the process need to be restarted, or should it simply stop receiving new work temporarily?

Spring Boot defines two important operational availability states:

- **Liveness:** reflects ability to function or self-recover from internal state. When broken, the platform may need to restart the process.
- **Readiness:** reflects ability to accept traffic or work at the current moment.

These states and application lifecycle are described in [Spring Boot 3.3 — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 4.1. Do Not Use the Same Signal for Every Decision

For the file-processing service, ask: if an external storage service is temporarily unreachable, does restarting every process help? If all processes depend on one failing external service, mass restarts can make recovery harder.

For a worker pulling jobs from a queue, also verify how the worker itself pauses consumption; do not infer that behavior solely from HTTP readiness status.

Readiness should also reflect actual serving needs: an external dependency may be mandatory for all jobs, needed for only one job type, or have a fallback. Do not lump every dependency check into the same probe group without assessing the impact.

### 4.2. Observe Probe Groups in a Study Environment

To enable probe groups outside Kubernetes:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

After applying the config and restarting the app:

```powershell
curl.exe -i "http://localhost:8080/actuator/health/liveness"
curl.exe -i "http://localhost:8080/actuator/health/readiness"
```

Spring Boot enables these groups automatically when it detects a Kubernetes environment. By default, these groups do not automatically include every external dependency check; adding them must be an explicit decision. See [Spring Boot 3.3 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Reading the URL does not configure the orchestrator. Kubernetes needs probe definitions configured to act accordingly; startup probes also protect slow-starting applications from premature restarts. Refer to [Kubernetes — Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

If the management port is separate from the main serving port, verify whether the signal represents the real serving path. One port still responding does not prove another port is accepting connections cleanly.

**Milestone achieved when:** you can explain the difference between restarting and pausing incoming traffic, and the consequences of picking the wrong signal.

## 5. Milestone 3 — Measure Service Quality Instead of Watching Status Alone

**Question:** while the application is running, what are users and resources experiencing?

Start with four question groups: how much work arrives, how long it takes, how much fails, and which resources are nearing saturation. This aligns with traffic, latency, errors, and saturation signals presented in [Google SRE — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/).

| Question group | Example for file-processing service | What must be specified |
| --- | --- | --- |
| Traffic | Files received per minute | Counting requests, retries, or unique jobs? |
| Latency | Request acceptance time; time from receipt to completion | Units and exact start/end timestamps |
| Errors | Failed jobs; outputs failing validation | Definition of failure and eligible job set |
| Saturation | Queued jobs, connections in use, memory | Limits or normal baseline for comparison |

### 5.1. Discover Available Metrics

In test-environment configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

Inspect the list and query only names that actually exist:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
```

The second command is an example if `jvm.memory.used` appears in the list. Read the unit and classification tags rather than extracting a single bare number. The `metrics` API is for inspecting registered meters; it is not designed as a monitoring store or periodic scraping target in production. See [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Spring Boot integrates Micrometer to record and provide metrics to many backends. Automatic metrics depend on active components and config; they do not automatically understand your full file-processing workflow. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 5.2. Read Metrics in Context

Three mistakes to avoid:

- Taking a cumulative total since process startup and calling it traffic per minute.
- Treating a fast HTTP acknowledgment as proof that background work finished fast.
- Treating mean duration as proof that all users have a similar experience.

When using p95/p99, know the time window, observation count, and estimation method. Per-instance percentiles cannot be averaged across instances to get a service-wide percentile. Aggregating across dimensions requires an appropriate method, such as histograms with counted buckets. See [Micrometer 1.13 — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

**Milestone achieved when:** for a given metric, you can state its quantity, unit, scope, time window, and a question it cannot answer on its own.

## 6. Milestone 4 — Build History and Verify the Collection Pipeline

**Question:** is data exported outside the application and still queryable after an issue occurs?

One Actuator call gives you one point-in-time observation. Comparing before/after a deployment or reviewing a past window requires a collection pipeline and storage.

Example with the Prometheus model:

```text
Application records metrics via Micrometer
              ↓
Registry provides data for the target system
              ↓
Prometheus scrapes /actuator/prometheus periodically
              ↓
Samples are stored over time
              ↓
Queries, dashboards, and condition evaluation
```

Prometheus uses active HTTP scraping and stores time-series data. This is one illustrative option, not a mandatory prerequisite for observability in every application. See [Prometheus — Overview](https://prometheus.io/docs/introduction/overview/).

### 6.1. Set Up a Minimal Learning Pipeline

In an app whose versions are already managed by the Spring Boot plugin/BOM, add the Prometheus registry to dependencies:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Merge the study environment exposure list to `health,metrics,prometheus`. Verify `/actuator/prometheus` on the application side first.

Example configuration for Prometheus running directly on the same host:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "file-service-lab"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

This is a configuration file for Prometheus; do not put `scrape_configs` inside Spring Boot’s `application.yml`. The target address must be reachable from where Prometheus runs; `localhost` inside a container refers to that container. Refer to [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

For monitoring backends using push transport, configure the registry and receiver per that protocol. In that case, Actuator’s HTTP exposure list does not replace export configuration.

### 6.2. Check Both Source and Collector

For the example job:

```promql
up{job="file-service-lab"}
```

A value of 1 means the scrape succeeded, 0 means it failed. Missing series must be distinguished from 0: the target might not be configured, no data may exist yet, or the label filter might not match. See [Prometheus — Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

Do not equate `up=1` with Actuator health reporting `UP` or with business tasks succeeding. Those three signals answer three different questions.

Correlating data with service, running instance, and deployment markers makes comparisons meaningful. Also verify retention period: a polished dashboard cannot recreate data that was lost or never scraped.

**Milestone achieved when:** you can point out the source, transport, storage, and a query to inspect past data, while also detecting when collection stops working.

## 7. Milestone 5 — Measure What Users Truly Need and Link Evidence

**Question:** is the application completing work as expected, and can an affected case be traced?

In the file-processing service, an HTTP response accepting a request is not the final outcome. You must look at queuing, processing, and output generation.

### 7.1. Write the Definition Before Adding Metrics

An illustrative definition:

```text
Subject: valid file-processing jobs accepted.
Good outcome: accurate output within 2 minutes of receipt.
Evaluation window: 30 days.
Indicator: jobs with good outcome / total eligible jobs.
Illustrative target: at least 99%.
```

Specify clearly which jobs are eligible, when the clock starts, how accurate output is confirmed, and when enough time has elapsed to classify. Do not exclude failed or overdue jobs from the denominator just to make the indicator look better.

A **Service Level Indicator (SLI)** measures service quality; a **Service Level Objective (SLO)** sets the target for that indicator over an evaluation window. Concepts and selection criteria are covered in [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/).

Hypothetical example for a set that has finished its evaluation period: out of 1,000 eligible jobs, 920 produced accurate output within the deadline. The good rate for that set is:

```text
920 / 1000 × 100% = 92%
```

This calculation applies to the illustrative set. To evaluate a 30-day SLO, use data across the full 30-day window under the exact definition; do not substitute a short test run for the whole window.

### 7.2. Fill Missing Data in the Workflow

Identify where the application knows for sure that:

- The job was durably accepted.
- Processing started.
- Output was confirmed as success or failure.
- The job waited past its deadline.

Choose appropriate metrics and recording points from there. With retries, distinguish retry attempts from unique jobs to avoid double-counting.

In a Spring Boot app, use managed instrumentation properly integrated with your export pipeline. Spring Boot supports Micrometer Observation to describe observed work along with handlers for metrics and traces. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Never put file contents, tokens, or per-job unique IDs indiscriminately into metric tags. Keep tag cardinality bounded; use properly access-controlled event records when locating a specific case.

### 7.3. Logs Help Locate Events

**Logs** record events with timestamps and context. Structured fields help find related events; linking to traces depends on captured and propagated context. See [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

The example below is hypothetical data invented for this lesson, not Spring Boot’s default log format:

```json
{
  "timestamp": "2026-02-12T10:15:30Z",
  "service": "file-service",
  "version": "v3",
  "event": "file_processing_delayed",
  "jobId": "lab-job-42",
  "stage": "waiting",
  "waitingMs": 125000,
  "traceId": "11112222333344445555666677778888"
}
```

The record helps find a job waiting too long via its recorded context. It does not automatically prove which component caused the delay. Event names and fields must be designed around the application’s real semantics.

### 7.4. Traces Help Understand Execution Paths

**Traces** link operations; each **span** describes an instrumented unit of work. That lets you see which step or remote call consumed time. Refer to [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

For background jobs, context must be propagated across queues and execution boundaries per your chosen mechanism. Do not assume a trace ID from HTTP ingestion will automatically appear in every downstream worker.

Spring Boot supports Micrometer Tracing; configure the matching tracer, exporter, and receiver. HTTP clients must also be built through integrated builders so context propagates as expected. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Sampling may retain only a subset of traces. Hence, not finding a trace is insufficient to conclude a job never ran. See [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/).

**Milestone achieved when:** starting from an abnormal indicator, you locate a representative case, identify its related events and processing steps, and state remaining data gaps.

## 8. Milestone 6 — Turn Signals into Detection and Action

**Question:** which signal deserves attention, who handles it, and how?

Alerts should tie to concrete user impact or risk to service goals. A resource metric crossing a threshold can assist investigation, yet may not warrant waking someone on call if there is no risk or actionable step. Relating alerts to SLOs is covered in [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/).

### 8.1. Design an Actionable Alert

For the file-processing service, describe alerts using these questions:

| Element | Example decision to make |
| --- | --- |
| Symptom | In which group is the overdue-job rate rising? |
| Window and sample volume | How long to evaluate, and what minimum job count is required? |
| Impact severity | Are users failing to receive output, or only facing delay risk? |
| Owner | Which team can verify and take action? |
| Investigation links | Queries, time range, version, and correlated data |
| Resolution criteria | What evidence confirms the service has recovered? |

Thresholds in a study example are not defaults for every service. At low traffic, percentages must be read alongside absolute counts. For flaky errors, balance detection sensitivity against alert noise.

Creating the alert rule and delivering the notification are two separate checkpoints. Run a controlled test to confirm alerts reach the right recipient with sufficient context and can be acknowledged/resolved cleanly.

### 8.2. Write a Short Runbook

An incident runbook should let someone else begin without guessing:

1. Confirm scope of impact and start time.
2. Check whether telemetry is being collected completely.
3. Compare traffic, wait time, errors, versions, and recent changes.
4. Pick one hypothesis and look for confirming or refuting evidence.
5. Mitigate impact with an action aligned to permissions and procedures.
6. Re-verify service quality after the action.

Use hypothesis-and-evidence reasoning instead of changing multiple variables at once. Refer to [Google SRE — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/).

**Milestone achieved when:** someone else can use your alert and runbook to verify the issue, know the next diagnostic step, and confirm recovery after remediation.

## 9. Milestone 7 — Validate Capability Through an Operational Scenario

**All events and numbers in the scenario below are hypothetical for practice.**

The file-processing service just deployed `v3`. Users report slow delivery of results. Health still reports good, and HTTP request-acceptance success rates remain high.

### 9.1. Use Each Layer of Evidence to Narrow the Issue

| Hypothetical evidence | What it tells us | What is not yet concluded |
| --- | --- | --- |
| Health stays good | Existing checks report no anomaly | All files are processed on time |
| HTTP response time is nearly unchanged | Request ingestion has not slowed noticeably | The overall workflow is not slow |
| Queued jobs and job age rise | Bottleneck occurs after ingestion | Which specific component caused it |
| Output errors do not rise; on-time rate drops | The prominent issue is meeting deadlines | Simply adding resources will suffice |
| Logs show jobs waiting long before running | Investigation can focus on the queuing/wait stage | Every job shares the same cause |
| Wait-time rise aligns near `v3` deployment | There is a change worth reviewing | `v3` is definitely the sole cause |

Next, the investigation team forms a hypothesis: the concurrency setting for worker threads changed. Evidence to gather includes effective configuration, active worker count, and a test under comparable load.

Suppose a controlled test shows reverting to the verified configuration reduces wait time. That supports the hypothesis. You still must document test conditions, concurrent changes, and the limits of your conclusion.

### 9.2. Confirm Recovery Through User Outcomes

After taking action, observe:

- Are older queued jobs draining completely?
- Are new jobs producing accurate output within deadlines?
- Are any new errors or duplicate executions occurring?
- Did the telemetry collection pipeline remain operational throughout the incident?

Seeing the process restart cleanly is not enough to confirm the queue has returned to normal.

### 9.3. Turn Lessons into Improvements

Record which signals helped, which were missing, and which actions need clarification. If queued job age could not be measured, plan how to add it. If alerts watched only HTTP endpoints, consider adding signals for background outcomes.

You do not need to add every tool after every incident. Prioritize changes that answer a specific question, then verify them in the next drill.

**Milestone achieved when:** you can reproduce the chain “detect → narrow scope → verify → remediate → confirm → improve”, with clear evidence and stated limits.

## 10. Principles to Keep Throughout the Roadmap

### 10.1. Fit Access Control to Purpose

Expose only needed endpoints, protect management paths, and restrict read access. Data such as configuration, heap/memory snapshots, or logs can contain sensitive information.

Do not expose all of Actuator as a default workaround for missing data. Identify which endpoint, registry, permission, or collection pipeline is actually missing.

### 10.2. Sufficient Data at Controlled Cost

Choose metric tags, log levels, sampling rates, and retention based on investigative needs. Collecting more data increases cost and can impact application performance.

Keep fields identifying service, version, and timestamps consistent. Distinguish nonexistent data from data not found due to wrong filters, time zones, or permissions.

### 10.3. Observation Channels Can Also Fail

A flat chart may mean low application activity, a broken collection pipeline, or a stale query. Keep evidence of data freshness and collector health.

When using a separate management port, test the user-facing path as well. When splitting across multiple processes, do not aggregate metrics in a way that erases instance identities needed for investigation.

### 10.4. Every Conclusion Needs a Scope

State clearly whether you are talking about one request, one process, one job group, or the entire service; about one moment or a long window. This keeps a single health response, trace, or short test from turning into an overbroad conclusion.

## 11. Choose the Right Starting Point for Your Application

| What you have today | Valuable next practice step |
| --- | --- |
| Cannot read health yet | Verify dependency, address, endpoint, and permissions |
| Can read health but do not know what it checks | Explain participating components and limits of the result |
| Only know the app is still running | Separate liveness/readiness and measure service quality |
| Have metrics inside the app | Verify collection pipeline, history, and freshness |
| Have resource charts | Add business-outcome questions and signals |
| See bad indicators yet struggle to investigate | Link metrics with events, traces, and versions |
| Have alerts yet struggle to respond | Add owners, runbooks, and drills |

This table helps choose study steps based on current gaps. You do not need to wait until every metric is complete before writing useful logs, nor wait for a distributed system before defining service targets.

### Closing Exercise

Pick a real operation in your application and write a one-page note:

1. What outcome do users expect, and within what time?
2. What does current health check related to that operation?
3. Which single signal detects when that outcome is missed?
4. Where is that data collected and stored, and for how long?
5. How do you locate an affected case and its processing steps?
6. Who acts, following which runbook, and how is recovery confirmed?

You have moved beyond basic health checks once you can use data to answer these questions and validate those answers in a controlled scenario.
