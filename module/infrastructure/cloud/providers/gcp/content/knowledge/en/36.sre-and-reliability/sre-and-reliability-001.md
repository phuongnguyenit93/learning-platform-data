# Applying SRE Practices to Services on GCP

A service running reliably on Google Cloud needs more than autoscaling infrastructure. The team also needs to know how users experience the service, what level of disruption is acceptable, when to intervene, and how to reduce recurring incidents. Site Reliability Engineering (SRE) provides a methodology to answer these questions using measurable metrics, automation, and disciplined operational processes.

SRE combines software engineering with systems operations. Instead of only reacting when servers throw errors, the team starts from the user experience, sets reliability targets, tracks the error budget, and improves service design based on actual data. On GCP, these principles apply to Cloud Run, Google Kubernetes Engine (GKE), Compute Engine, Cloud SQL, Pub/Sub, and distributed systems that combine multiple services.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of SRE and distinguish between SLI, SLO, SLA, and error budget.
- Select reliability metrics that reflect the user experience.
- Set up service observability using Cloud Monitoring, Cloud Logging, Cloud Trace, and related tools.
- Design alerts based on the error budget burn rate.
- Organize on-call operations, incident response, and blameless postmortems.
- Apply canary deployments, rollbacks, automation, and toil management.
- Design resilience, capacity planning, and disaster recovery for workloads on GCP.

## 1. What Is SRE and Why Apply It?

SRE is an approach to operating services using measurable engineering practices and automation. The goal is to keep services reliable enough for users while still allowing development teams to release features frequently.

SRE does not mean maximizing uptime at all costs. A system can achieve high uptime while still being slow, returning incorrect data, or failing to complete critical transactions. Conversely, over-investing in reliability can drive up costs and slow down innovation without delivering commensurate value to users.

SRE helps teams balance three goals:

- **User experience:** critical flows work correctly, are fast enough, and remain usable.
- **Velocity of change:** the team can release features, fix bugs, and improve the product.
- **Operational cost:** resources, on-call shifts, and maintenance effort stay within what the organization can sustain.

### SRE vs. Traditional Operations

In reactive-only operations, teams typically monitor CPU, RAM, and instance counts, and handle alerts when a technical threshold is crossed. These metrics are useful for diagnosis, but they do not necessarily indicate whether users are experiencing problems.

SRE adds a service-level measurement layer:

1. Identify critical user journeys or operations.
2. Define what counts as a good event.
3. Set quality targets over a time window.
4. Measure error budget consumption.
5. Use data to make decisions on release velocity, reliability investments, and automation.

A payment service might run on healthy VMs yet still fail transactions because Cloud SQL connections are exhausted. A Cloud Run service might return HTTP 200 yet take several seconds to complete a request. SRE directs monitoring toward the actual outcomes users receive.

## 2. SLI, SLO, SLA, and Error Budget

These are the four foundational concepts for turning reliability into a manageable target.

| Concept | Meaning | Example |
|---|---|---|
| SLI (Service Level Indicator) | A metric that measures service quality | Percentage of requests that succeed and complete under 300 ms |
| SLO (Service Level Objective) | The target to achieve for an SLI over a time window | 99.9% of eligible requests meet the condition over 30 days |
| SLA (Service Level Agreement) | A commitment to customers, potentially with compensation clauses | Contractual availability commitment |
| Error budget | The amount of failure allowed within the SLO window while still meeting the target | 0.1% of requests allowed to fail |

An SLI is a measurement; an SLO is an internal or operational target; an SLA is an external commitment. SLOs are typically set tighter than—or with a buffer relative to—SLAs so the team has time to detect and remediate issues before breaching the external commitment.

### Choosing SLIs from the User Perspective

A good SLI reflects what users care about, can be measured consistently, and has a clear denominator. Common SLI categories include:

| SLI Category | How It Is Measured | Question to Answer |
|---|---|---|
| Availability | Successful events / total eligible events | Can users complete the operation? |
| Latency | Percentage of requests completed below a time threshold | Is the service fast enough? |
| Throughput | Number of requests or tasks completed per unit of time | Is the service handling sufficient load? |
| Freshness | Percentage of data updated within a defined timeframe | Is the data recent enough? |
| Correctness | Percentage of results that satisfy business rules | Is the service returning accurate results? |
| Durability | Percentage of data preserved intact and retrievable | Is data lost or corrupted? |

Not every service needs every SLI. For a payment API, availability, latency, and transaction correctness are usually important. For a data pipeline, freshness, completeness, and correctness may matter more than per-request latency.

### Defining Good Requests and Eligible Requests

Before calculating an SLI, the team needs to agree on:

- Which requests are in scope for measurement?
- Are health checks, bots, internal requests, or retries counted?
- Are errors caused by users sending invalid data counted as service errors?
- Is HTTP 429 due to capacity limits considered a bad event?
- How are requests that time out after the client disconnects handled?
- When is a multi-step transaction considered successful?

There is no single HTTP status rule that fits every service. For instance, 4xx responses might be user input errors, whereas 429 responses due to system overload might be an experience failure that the SLO should count. Define good-event criteria based on the API contract and actual user journeys.

### Example: Building an SLO for a Checkout API

Suppose a checkout API receives valid requests from a shopping application. The team defines a good request as one where:

- The transaction completes according to business rules.
- A success response is returned.
- Processing time is under 300 ms.

Sample SLO:

**Over every 30-day window, at least 99.9% of eligible checkout requests must complete successfully within 300 ms.**

This is a request-based SLO: the numerator is the number of good requests, and the denominator is total eligible requests. A request is counted as good only when it satisfies both the outcome condition and the latency condition.

To measure the two aspects separately, you can define two SLOs:

- Availability: at least 99.9% of eligible requests complete successfully over 30 days.
- Latency: at least 99% of eligible requests complete in under 300 ms over 30 days.

Having two SLOs helps determine whether an incident is caused by a functional failure or a performance issue. A combined SLO is appropriate when the experience is only considered good if both conditions are met simultaneously.

## 3. Calculating Error Budgets and Using Them for Decisions

The error budget is the share of bad events a service can experience during the evaluation period while still meeting its SLO.

Formula for a request-based SLO:

~~~text
Error budget = (1 - SLO goal) × number of eligible events in the period
~~~

For example, if the SLO is 99.9%, the allowed error rate is 0.1%. If there are 1,000,000 eligible requests in the period:

~~~text
Error budget = (1 - 0.999) × 1,000,000
             = 1,000 failed requests
~~~

If the SLI is measured by availability time rather than request count, the same 99.9% target over 30 days corresponds to roughly 43.2 minutes of continuous unavailability. Do not apply this time figure directly to a request-based SLO; the two SLI types have different denominators and calculation methods.

### Error Budget Policy

An error budget establishes shared alignment across product, development, and operations teams. A sample policy might look like:

| Budget Status | Reference Decision |
|---|---|
| Above 50% remaining | Continue releasing per the normal process while monitoring the SLO |
| 25–50% remaining | Increase verification checks, prioritize bug fixes, and reduce high-risk changes |
| Below 25% remaining | Require a reliability review before releasing major features |
| Exhausted | Freeze non-essential risky changes and focus on fixing root causes consuming the budget |

The thresholds above are examples only. Each organization needs to agree on a policy aligned with service criticality, customer commitments, and acceptable risk. The policy should also include clear exceptions for emergency security patches or changes needed to restore service.

An error budget is not meant to punish the development team. It gives all stakeholders visibility into the cost of incidents and supports data-driven decisions when balancing release velocity against reliability.

## 4. Designing Observability for Services on GCP

Observability is the ability to understand a system's internal state from the telemetry it emits. Three common signal types are metrics, logs, and traces; each answers a different set of questions.

| Telemetry | Role | Common GCP Tools |
|---|---|---|
| Metrics | Measure trends and state over time | Cloud Monitoring, Managed Service for Prometheus |
| Logs | Record discrete events and detailed context | Cloud Logging |
| Traces | Track a single request across multiple components | Cloud Trace, OpenTelemetry |
| Error events | Group and track application errors | Error Reporting |
| Profiling | Analyze CPU and heap to find bottlenecks | Cloud Profiler |

Google Cloud Observability provides tools to collect, query, visualize, and alert on these signals. Depending on the runtime, you can use built-in telemetry or install an agent/collector.

### The Four Golden Signals

Four signals commonly used as a starting point for monitoring a service are:

1. **Latency:** the time taken to process a request. Distinguish between latency of successful requests and latency of failed requests, because fast-failing errors can skew averages downward while users still fail to complete their actions.
2. **Traffic:** the volume of requests, messages, or tasks the system is receiving.
3. **Errors:** the rate of failed operations, including application errors, timeouts, and dependency failures.
4. **Saturation:** how close resources or queues are to their limits, such as CPU, memory, connection pools, concurrency, or backlogs.

Golden signals are a starting point for observing a service. They do not replace SLIs/SLOs: low CPU does not prove checkout is succeeding, and a low error rate can hide data errors or high latency.

### Choosing Telemetry by Workload Type

| GCP Workload | Signals to Monitor |
|---|---|
| Cloud Run service | Request count, request latency, response codes, instances/concurrency, startup, and revision errors |
| GKE | Requests per service, pod readiness, restarts, CPU/memory, node pressure, ingress, and network |
| Compute Engine | CPU, memory, disk I/O, network, processes, and VM/instance group health |
| Cloud SQL | Connection count, query latency, CPU, storage, locks, replication lag, and connection errors |
| Pub/Sub | Backlog, oldest unacked message age, publish/delivery rate, redelivery, and dead-letter |
| Data pipeline | Latest data timestamp, processed record count, failed record count, and batch completion time |

With Compute Engine, the Ops Agent can collect OS metrics and logs. With GKE, Managed Service for Prometheus can scrape Prometheus metrics from workloads. Cross-platform applications can be instrumented with OpenTelemetry to send traces, metrics, and logs to the corresponding observability backend.

### Correlating Logs, Metrics, and Traces

To investigate a slow request:

- Metrics show when latency increased and what percentage of traffic was affected.
- Logs show what error the request encountered and which inputs or dependencies were involved.
- Traces show how long the request spent at each hop across the API gateway, Cloud Run, Pub/Sub, and Cloud SQL.
- Error Reporting helps group recurring application exceptions.
- Profiler helps pinpoint functions or execution paths consuming CPU/heap when needed.

Use structured logging with severity, service name, version, and trace identifier where appropriate. Avoid logging tokens, passwords, personal data, or sensitive payloads. Limit high-cardinality metric labels such as user ID, email, or request ID; unique values are unsuitable as metric labels because they can increase costs and degrade query performance.

## 5. Building SLOs and Alerts in Cloud Monitoring

Cloud Monitoring provides Service Monitoring and the SLO API to describe services, SLIs, targets, and compliance periods. You can create SLOs from metrics or configure SLIs based on supported service types and data sources.

An SLO should include these components:

- Service and responsible owner.
- SLI definition, including numerator and denominator or good-event criteria.
- Goal, such as 99.9%.
- Compliance period, such as a rolling 30-day window or calendar month.
- Telemetry source and rules for excluding out-of-scope traffic.
- Alert policies and notification channels.

### Example SLI Using PromQL

Suppose the application exports a counter named **http_server_requests_total** with labels **service** and **sli_outcome**. The application sets **sli_outcome="good"** when a request meets the agreed-upon success definition.

Good-request ratio over 5 minutes:

~~~promql
sum(rate(http_server_requests_total{
  service="checkout",
  sli_outcome="good"
}[5m]))
/
sum(rate(http_server_requests_total{
  service="checkout"
}[5m]))
~~~

This is an example of a custom application-instrumented metric, not a default metric name across all GCP workloads. You must handle cases where the denominator is 0 and choose an appropriate measurement window. When creating a long-term SLO, Cloud Monitoring evaluates the SLI across the configured compliance period rather than relying solely on a single 5-minute window.

Example measuring the ratio of requests with latency under 300 ms using a Prometheus histogram:

~~~promql
sum(rate(http_server_request_duration_seconds_bucket{
  service="checkout",
  le="0.3"
}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{
  service="checkout"
}[5m]))
~~~

This second example assumes the application exports a histogram with a bucket at 0.3 seconds and the corresponding count metric. Verify actual metric names and instrumentation conventions before using queries in production.

### Burn-Rate Alerting

Burn rate indicates how fast the error budget is being consumed relative to the pace required to meet the SLO.

~~~text
Burn rate = actual bad-event rate / allowed bad-event rate
~~~

With a 99.9% SLO, the allowed error rate is 0.1%. If 1.44% of requests fail during a measurement interval:

~~~text
Burn rate = 1.44% / 0.1% = 14.4
~~~

If this rate persists, the 30-day budget will be exhausted in roughly 30 / 14.4 = 2.08 days. A high burn rate signals an ongoing incident before the end-of-period SLO is breached.

Combine multiple time windows to distinguish severe incidents from short-lived noise. For example, one policy can check burn rate over 1-hour and 5-minute windows, while another uses 6-hour and 30-minute windows. Window pairs, thresholds, and sustain durations must be tuned to the service's traffic volume and criticality.

Alerts should be categorized by action:

- **Page/on-call:** user-facing errors are rising rapidly, the budget is burning quickly, or the service cannot complete critical operations.
- **Ticket/work queue:** the budget is eroding slowly, latency is slightly elevated, or resources are approaching limits without severe impact yet.
- **Dashboard/trend:** signals used for long-term analysis, capacity planning, and architectural improvements.

Do not page on every CPU spike or single pod restart. Prioritize alerting on symptoms and SLO impact; infrastructure metrics assist in identifying the root cause once an alert fires.

## 6. Organizing Incident Response and On-Call

During an incident, the primary objective is to reduce user impact and restore service. Finding the root cause is necessary, but it must not delay mitigation actions.

An incident response workflow can include:

1. **Detect:** alerts from SLOs, monitoring, or user reports.
2. **Triage:** assess severity, blast radius, and affected services and dependencies.
3. **Declare:** assign an incident commander and open the appropriate coordination channel.
4. **Mitigate:** roll back, shed traffic, disable a feature flag, switch to degraded mode, or isolate a dependency.
5. **Communicate:** share status updates, impact, and the next update time with stakeholders.
6. **Recover:** verify the service has returned to acceptable quality and monitor to prevent immediate recurrence.
7. **Review:** compile the timeline, contributing factors, response effectiveness, and action items.

### Incident Roles

For major incidents, divide responsibilities clearly:

- **Incident commander:** coordinates response, prioritizes work, and makes overall decisions.
- **Operations lead:** investigates technically, executes mitigations, and performs recovery actions.
- **Communications lead:** updates customers, leadership, and partner teams on status.
- **Scribe:** records the timeline, decisions, impact, and actions taken.

One person may fill multiple roles during smaller incidents, but it must be clear who is in charge to prevent multiple responders from making uncoordinated changes in production.

### Runbooks and Escalation

A runbook should document:

- Associated symptoms and alerts.
- How to identify the affected service, revision, cluster, or dependency.
- Dashboards and log queries to open.
- Verified mitigation steps.
- Criteria for rollback or failover.
- Contacts or teams for escalation.
- Steps to verify recovery and how to log the incident.

Runbooks must be updated whenever the system changes. Documentation that no longer matches production can prolong an incident.

### Blameless Postmortems

After a significant incident, the team should write a postmortem focused on the system and the conditions that led to the failure. It typically includes:

- Summary and impact level.
- Timeline of detection, response, and recovery.
- What happened and why the system allowed that situation to occur.
- What worked well and what caused delays.
- Action items with owners and due dates.

A blameless postmortem does not mean ignoring accountability. The goal is to understand why decisions that seemed reasonable in context still produced a bad outcome, and then improve guardrails, processes, telemetry, or design to reduce the likelihood of recurrence.

## 7. Reducing Toil Through Automation

Toil is operational work that is repetitive, manual, reactive, and lacks enduring value proportional to the effort. Examples include:

- Executing the same sequence of manual commands for every deployment.
- On-call engineers clearing queues or restarting workloads using the same manual steps.
- Operations teams manually compiling SLO figures every week.
- A noisy alert that always requires someone to open and then close a ticket.

SRE teams should measure toil and look for automation opportunities. Prioritize work that occurs frequently, carries high operator error risk, or slows down incident response.

Automation examples on GCP:

| Task | Improvement Approach |
|---|---|
| Repetitive deployments | Cloud Build and Cloud Deploy with standardized pipelines |
| SLO tracking | Cloud Monitoring dashboards and alert policies |
| Application error detection | Error Reporting and log-based metrics |
| Workload scaling | Cloud Run autoscaling, GKE autoscaler, or Managed Instance Group autoscaling |
| Handling failed messages | Dead-letter topics, bounded retries, and replay procedures |
| Configuration drift detection | Terraform plan, policy validation, and review workflows |
| Operational reporting | Scheduled queries on metrics/logs with automated report exports |

Automation needs guardrails. For example, auto-restarting a workload can mask a memory leak, and unbounded automatic retries can overload a dependency. Define trigger conditions, retry caps, timeouts, execution permissions, and rollback mechanisms before automating production actions.

## 8. Safe Releases with Canary and Rollback

A new change can degrade reliability even when all unit and integration tests pass. SRE uses progressive delivery to limit how many users are affected if a bug is detected.

### Canary Deployment

A canary deployment routes a small portion of traffic to the new version first, observes SLIs, and gradually increases the share if results look good. For example:

~~~text
Old version: 100%
        |
        v
Canary 5% traffic
        |
        v
Evaluate error rate, latency, and business metrics
        |
        +---- Fails checks ---> Halt rollout / rollback
        |
        v
Canary 25% -> 50% -> 100%
~~~

With Cloud Run, traffic can be split across revisions. With GKE, you can use Cloud Deploy and configure a canary strategy aligned with service networking or Gateway API. Cloud Deploy supports percentage-based canary rollout phases and can integrate deploy analysis to evaluate metrics before advancing phases.

### Canary Evaluation Criteria

Do not look only at pod counts or deployment status. Compare the new version against the stable version on:

- Error rate and latency according to SLIs.
- Business operation completion rate.
- Timeout and dependency error rates.
- CPU, memory, restarts, and saturation.
- Queue backlog or message processing delay.
- Cost per request or task if the change affects resource efficiency.

If canary traffic is low, metrics may not yet be statistically representative. You may need longer observation windows, synthetic probing, or representative staging validation before increasing traffic share.

### Rollbacks and Feature Flags

A rollback restores the workload to a known-good version. Feature flags allow disabling a feature without redeploying the entire application. The two techniques work well together:

- If the bug comes from new code, roll back to a stable release.
- If the bug is isolated to one feature, turn off its feature flag to limit impact.
- If the database schema changed incompatibly, rolling back the application alone may not suffice; design migrations to be backward-compatible.
- If corrupted data was written, a data repair and integrity verification procedure is needed, not just a binary rollback.

Rollbacks must be rehearsed. A rollback button is useless if the previous release is no longer compatible with current schemas, secrets, APIs, or configurations.

## 9. Designing Resilience for GCP Workloads

Resilience is the ability to maintain or recover functionality when a component fails. No single architectural pattern fits every service; start from SLOs, RTO/RPO, and dependency failure modes.

### Timeouts, Retries, and Backoff

A request spanning multiple services can suffer multiplied wait times if every dependency uses overly long timeouts. Set explicit timeouts at each hop and ensure total processing time stays within the request's latency budget.

Retries should include:

- Exponential backoff to progressively lengthen wait intervals.
- Jitter to prevent many clients from retrying in lockstep.
- A maximum retry count and an overall deadline.
- Idempotency keys or deduplication mechanisms for operations with side effects.
- Classification rules separating retryable errors from non-retryable ones.

Do not infinitely retry 4xx errors or configuration errors. If a dependency is overloaded, aggressive retries can amplify the outage. Circuit breakers, concurrency limits, and rate limits prevent workloads from continuing to send traffic to a failing component.

### Queues and Asynchronous Processing

Pub/Sub decouples producers from consumers, absorbs traffic bursts, and allows message reprocessing. However, queues can back up when consumers slow down or messages repeatedly fail.

Monitor oldest unacked message age, backlog, delivery attempts, and dead-letter topics. Consumers should be idempotent so redelivered messages do not create duplicate transactions. Configure retry policies, ack deadlines, and dead-letter policies appropriate to the workload.

### Failure Domains and High Availability

For critical workloads:

- Deploy across multiple zones when supported by the runtime and services.
- Use load balancing and health checks to stop routing traffic to unhealthy instances.
- Configure autoscaling while enforcing quota and capacity limits.
- Identify which dependencies represent single points of failure.
- Test behavior during zone loss, database connection loss, or a regional cloud disruption.
- For multi-region setups, design replication, routing, consistency, and failover before an incident occurs.

Running two instances in the same zone does not protect against a zonal outage. Multi-region does not automatically solve everything either: data may not have replicated yet, and failover can cause split-brain or higher latency. Recovery paths must be tested using realistic data and traffic.

### Degraded Mode and Graceful Degradation

When a non-essential dependency fails, a service can continue providing core functionality. For example, a product page can still show cached product details while the recommendation engine is temporarily unavailable. Secondary features can be disabled while checkout continues to operate.

Clearly define:

- Which functions belong to the critical path.
- Which data can be served from cache and for how long.
- When to return stale data, show an error message, or ask the user to retry.
- Which actions must be halted to avoid writing inconsistent data.

## 10. Capacity Planning and Performance

Autoscaling adjusts resources with load, but it does not replace capacity planning. A service may fail to scale fast enough for bursts, hit quotas, exhaust database connections, or be bottlenecked by a dependency that cannot scale proportionally.

Identify:

- Average, peak, and burst traffic.
- Expected growth rate.
- Concurrency levels and resource requests/limits.
- Quotas by project, region, and API.
- Database connection, throughput, and storage limits.
- Startup time for new instances and warm-up behavior.
- Cost at normal load and peak load.

### Examples by Runtime

**Cloud Run:** monitor request latency, concurrency, instance count, startup latency, and max instances limits. If max instances is too low, the service may return errors or spike in latency under load. If it is set too high for Cloud SQL to handle the concurrent connections, the database can become the bottleneck.

**GKE:** monitor pod resource usage, pending pods, HPA, cluster autoscaler, node pool capacity, restarts, and readiness. HPA can increase replicas, but the cluster still needs node capacity to schedule pods. Misconfigured resource requests can cause poor scheduling decisions or workload evictions.

**Compute Engine:** with Managed Instance Groups, monitor autoscaling, instance health, CPU, disk, and network. Verify quotas and VM creation times; autoscaling cannot provision additional capacity if the project or region has hit its limits.

Load tests should simulate normal traffic, bursts, slow dependencies, and failures. After each test, update capacity models, SLOs, and autoscaling bounds.

## 11. Backups, Disaster Recovery, and Recovery SLOs

Reliability is not just uptime. A system can stay continuously available yet lose data or fail to recover after accidental deletion. Targets must be set for backups and disaster recovery.

Two key metrics:

- **RPO (Recovery Point Objective):** the maximum amount of data an organization can tolerate losing, typically expressed in time.
- **RTO (Recovery Time Objective):** the maximum time allowed to restore a service to an acceptable operating level.

For example, a 15-minute RPO means that in a disaster scenario, the target is to limit data loss to at most the last 15 minutes. A 2-hour RTO means the team aims to restore the service within at most 2 hours. These are design and drill targets, not automatic guarantees from merely enabling backups.

On GCP, you can combine Cloud SQL backups, Persistent Disk snapshots/policies, Backup for GKE, and service-specific data backups. Verify backup consistency, retention, encryption, access permissions, and replica storage locations.

A DR plan should include:

1. An ordered list of services and dependencies for recovery.
2. RPO/RTO approved by business owners.
3. Configured backups and replication.
4. Failover/failback runbooks covering DNS, load balancers, secrets, and IAM permissions.
5. Methods to verify data integrity after recovery.
6. A drill schedule and evidence of actual recovery times.

An untested backup is not sufficient proof of recoverability.

## 12. Sample SRE Workflow for a Service on GCP

Suppose an e-commerce system consists of:

- Cloud Run serving the checkout API.
- Cloud SQL storing orders.
- Pub/Sub publishing events after order creation.
- A consumer on GKE processing invoices and notifications.
- Cloud Monitoring, Logging, and Trace collecting telemetry.

An SRE lifecycle can be organized as follows:

| Phase | Actions Required | Evidence |
|---|---|---|
| Define | Identify critical user journeys, SLIs, and SLOs | SLO document with owners and measurement windows |
| Instrument | Collect metrics, logs, traces, and business events | Dashboards and traces correlating requests end-to-end |
| Alert | Create alerts on SLO burn rate and dependencies | Alerts with thresholds, owners, and runbooks |
| Operate | Run on-call, triage, and handle incidents | Incident timelines and status updates |
| Improve | Write postmortems, resolve action items, and reduce toil | Issues with owners, deadlines, and verification |
| Release | Run canaries, evaluate metrics, and roll back when needed | Rollouts with verification results |
| Recover | Test backups, failover, and restores | RTO/RPO drill results |

Sample SLOs for checkout:

- 99.9% of eligible requests complete successfully over 30 days.
- 99% of eligible requests complete within 300 ms.
- 99% of invoice messages are processed within 5 minutes of publishing.

These targets are examples for discussion only. Product and engineering owners must define SLIs, traffic eligibility, measurement windows, and realistic targets based on user data.

If Cloud SQL latency causes checkout to breach its latency SLO, traces help pinpoint whether the time is spent in database queries or application code. If the Pub/Sub backlog grows while checkout still succeeds, it may be a freshness issue in the invoicing pipeline rather than an API availability outage. Separating SLOs by user journey helps the team prioritize fixing the right component.

## 13. Common Pitfalls When Adopting SRE

| Pitfall | Consequence | Remedy |
|---|---|---|
| Using CPU as the sole SLI | Fails to reflect user experience | Measure good events, latency, and business outcomes |
| Setting a 100% SLO | Leaves no practical error budget to manage change | Choose measurable targets tied to acceptable risk |
| Not defining eligible requests | Denominator shifts by calculation, making SLIs inconsistent | Document which traffic is counted and why exclusions apply |
| Paging on every metric | Alert fatigue causes critical incidents to be missed | Page on user impact and burn rate |
| Unbounded retries | Amplifies load and collapses dependencies | Use timeouts, backoff, jitter, retry limits, and idempotency |
| Checking only deployment success for canaries | Business bugs can still reach users | Compare SLIs, business metrics, and saturation |
| Having backups without restore drills | Actual RTO/RPO fails during real outages | Run periodic recovery drills |
| Blameful postmortems | Staff hesitate to report issues and systemic flaws recur | Focus on conditions, guardrails, and improvements |
| Automation without guardrails | Mistaken actions can spread widely | Bound scope, permissions, retries, and rollback mechanisms |

## 14. Production Readiness SRE Checklist

- [ ] Service owner, on-call rotation, and escalation path are defined.
- [ ] Critical user journeys are identified.
- [ ] SLIs have clear numerators, denominators, eligibility rules, and telemetry sources.
- [ ] SLOs have goals, compliance periods, and an error budget policy.
- [ ] Cloud Monitoring dashboards display latency, traffic, errors, saturation, and SLOs.
- [ ] Alert policies prioritize user impact and burn rate; every page links to a runbook.
- [ ] Logs are structured, traces are correlated, and unnecessary sensitive data is not logged.
- [ ] Dependencies have timeouts, bounded retries, backoff, jitter, and idempotency where needed.
- [ ] Health checks, autoscaling, quota/capacity plans, and resource limits are in place.
- [ ] Releases use canary or progressive rollouts and tested rollbacks.
- [ ] Incident response defines roles, communication channels, and postmortems.
- [ ] Toil is measured with a plan for automation.
- [ ] Backups, restores, failover, and RTO/RPO have been rehearsed.
- [ ] Post-incident action items have owners, deadlines, and verification steps.

## Conclusion

Applying SRE on GCP starts with the user experience: defining SLIs, setting SLOs, and managing error budgets. Cloud Monitoring, Logging, Trace, and related observability tools help measure quality, detect anomalies, and investigate incidents. Canary rollouts, rollbacks, autoscaling, resilience patterns, backups, and DR reduce the impact of changes or infrastructure failures. When combined with incident response, postmortems, and toil automation, teams can continuously improve reliability while maintaining development velocity.

## References

- [Google Cloud: SRE and service monitoring concepts](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Monitoring: Service Level Objectives API](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Cloud Monitoring: Alerting on your burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Google Cloud Observability overview](https://docs.cloud.google.com/stackdriver/docs)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://docs.cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://docs.cloud.google.com/trace/docs)
- [Managed Service for Prometheus](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus)
- [Cloud Deploy: Canary deployment strategy](https://docs.cloud.google.com/deploy/docs/deployment-strategies/canary)
- [Cloud Deploy: Canary deployments to Cloud Run](https://docs.cloud.google.com/deploy/docs/deployment-strategies/canary/cloud-run)
- [Cloud Deploy: Roll back a target](https://docs.cloud.google.com/deploy/docs/roll-back)
- [Google Cloud: Reliability and disaster recovery](https://cloud.google.com/architecture/dr-scenarios-planning-guide)
