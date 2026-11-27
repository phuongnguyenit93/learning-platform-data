# Evaluating Cost, Observability, and Platform Constraints

## Learning Objectives

**Serverless** architecture lets development teams focus on application logic while the cloud provider manages most of the execution infrastructure. However, "no server management" does not mean zero operational cost, no need for observability, or the ability to move workloads across platforms without changes.

In **Cloud Architecture** design, adopting serverless must be evaluated using workload data, pricing models, operational requirements, platform limits, and quality criteria. This lesson focuses on three lenses to assess before and during operations: **cost, observability, and platform constraints**.

After this lesson, you will be able to:

- Break down serverless costs across requests, execution duration, resources, storage, networking, logs, events, and supporting services.
- Calculate cost per successful business transaction, compare serverless against always-on compute, and run load sensitivity analyses.
- Design metrics, logs, traces, correlation IDs, alerts, and dashboards to observe distributed flows.
- Identify cold starts, timeouts, concurrency limits, quotas, runtime limits, payload limits, networking, and service-specific constraints.
- Assess reliance on managed services, portability, and exit costs.
- Build quality scenarios, TCO models, ADRs, and test plans grounded in Well-Architected principles.

## 1. Serverless Does Not Mean Zero Cost or Zero Operations

Serverless typically provisions compute per event or request. The provider operates the host, runtime infrastructure, and portions of scaling. The application team still remains responsible for:

- Application code, dependencies, configuration, and runtime versions.
- Identities, access control, secrets, data, and tenant isolation.
- Performance, concurrency limits, quotas, and behavior when dependencies fail.
- Logs, metrics, traces, alerting, investigation, and incident response.
- Queue capacity, retries, DLQs, retention, backups, and recoverability.
- Usage costs, budgets, egress, log storage, and downstream service calls.

A function may execute in just 100 ms yet emit verbose logs, query a database multiple times, publish events, and transfer large payloads. Real cost does not sit solely on the function compute line item. Conversely, infrequently invoked applications benefit from pay-per-use pricing as long as platform, network, and observability fees do not dominate TCO.

**Rule:** Evaluate serverless across the entire business path and system-wide cost, never by single-invocation price alone.

## 2. Breaking Down the Serverless Cost Model

### 2.1. Common Cost Drivers

| Component | How costs arise | Questions to clarify |
| --- | --- | --- |
| Invocation/request | Number of function calls or requests | Are retries billed as extra invocations? |
| Compute duration | Execution time multiplied by memory/CPU or resource tier | Does billed duration include I/O wait time? |
| Provisioned/minimum capacity | Pre-allocated instances/concurrency to reduce cold starts | Is always-ready capacity actually needed? |
| API gateway/edge | Requests, connections, data processed, rules, and WAF | How many requests are retries or invalid? |
| Event bus/queue | Operations, message size, deliveries, retention, and polling | Are messages replayed or fanned out to many subscribers? |
| Database/cache | Requests, read/write units, storage, throughput, connections, replication | Does function fan-out trigger excessive queries? |
| Object storage | Storage, PUT/GET requests, lifecycle, retrieval, replication | Are temporary job files cleaned up on schedule? |
| Network/egress | Internet egress, cross-region, cross-zone, or private endpoints | Where does data flow and across how many hops? |
| Observability | Log ingestion, indexing, retention, queries, metrics, traces | Does debug logging emit excessive volume? |
| Security/governance | KMS, secret managers, policy evaluations, audits, scanning | Are managed services called on every single request? |
| Support/operations | Support plans, on-call rotations, skills, tooling | Is operational labor accounted for in TCO? |

Rates and billing units vary by service, region, configuration, and contract. When budgeting, use current pricing sheets and verify service-specific billing rules. Figures in this lesson are illustrative examples, not quotes.

### 2.2. Request and Duration Compute Costs

A simple modeling formula:

~~~text
Compute cost
  ≈ invocation count × invocation price
  + billable compute duration × configured resource price
  + minimum/provisioned capacity cost (if any)
~~~

Distinguish business processing time from billable time. A function waiting on network or database I/O still accrues billable execution time. Sequential outbound calls stretch billable duration without increasing useful throughput.

Suppose a function handles 2 million invocations per month with an average billable duration of 250 ms at 1 unit of configured compute in this example. Total execution time:

~~~text
2,000,000 × 0.25 seconds = 500,000 seconds
                         ≈ 138.9 hours
~~~

This calculation shows only raw duration before unit pricing and service rounding rules. It excludes invocation fees, API gateway calls, databases, logs, networking, queues, and retries.

### 2.3. Never Ignore Downstream Dependency Costs

A function may query databases multiple times or trigger a chain of events. For example, a single booking API request can trigger:

1. One API handler invocation.
2. Two or three database queries.
3. One outbox write or message publish.
4. One notification worker invocation.
5. One outbound call to an email provider.
6. Multiple logs, traces, and metrics.

Counting only the entry function severely underestimates spend. Use **cost per business transaction** to divide end-to-end cost by successful business completions.

## 3. Modeling Cost per Business Unit

### 3.1. Cost per Successful Transaction

~~~text
Cost per successful transaction
  = Total cost of the workload in the measurement period
    / Number of successful business transactions
~~~

Illustrative example—a booking system has the following monthly costs:

| Item | Hypothetical cost (million VND/month) |
| --- | ---: |
| Function compute + invocations | 18 |
| API gateway and edge | 12 |
| Database and cache | 35 |
| Queue/event bus | 6 |
| Object storage | 4 |
| Network and egress | 8 |
| Logs, metrics, traces | 10 |
| Security, KMS, secrets, and audit | 5 |
| **Total** | **98** |

If that month sees 700,000 successful bookings:

~~~text
98,000,000 / 700,000 = 140 VND / successful booking
~~~

This covers only workload infrastructure within the listed scope. It omits engineering/operations labor, commercial support, shared platform overhead, or migration costs unless allocated. When comparing with containers or VMs, compare across the exact same cost scope and successful booking count.

### 3.2. Factoring Failures and Retries into the Equation

Suppose 1 million jobs are submitted, yet only 980,000 complete successfully. The remaining 20,000 fail, retry, hit DLQs, or need manual remediation. The cloud bill still charges compute, queues, networking, and logs for every failed attempt.

Never use total invocations as the denominator for cost per transaction. Use **valid business outcomes** as the denominator. Simultaneously track cost per attempt on dashboards to spot abnormal retry activity.

A useful metric:

~~~text
Retry overhead
  = Cost of retry attempts / Total processing cost
~~~

If this ratio spikes suddenly, downstream dependencies may be unstable, timeouts too tight, idempotency causing duplicate work, or poison messages looping. Optimizing application code alone may not fix the root cause.

### 3.3. Allocating Shared Costs

A platform may share an API gateway, log workspace, KMS, network hub, or database across multiple workloads. Allocate costs using appropriate drivers:

- Request count or compute duration for API/function platforms.
- Log bytes for ingestion and retention.
- Data transferred for networking/egress.
- Storage bytes and requests for object/database storage.
- Tenant counts, workloads, or key operations for shared services.

Avoid arbitrary allocation that burdens small workloads with most shared overhead. Tags, labels, and account/project boundaries improve cost attribution.

## 4. Comparing Serverless with Always-On Compute

### 4.1. Example Workload Shapes

| Workload characteristic | Model worth evaluating |
| --- | --- |
| Infrequent traffic, sharp bursts, short processing | Event-driven functions |
| Steady all-day traffic requiring consistent latency | Containers/VMs or serverless with pre-warmed capacity |
| Short background jobs, retryable and chunkable | Functions or event-driven workers |
| Long-running jobs needing heavy RAM/CPU or custom runtimes | Container jobs, batch services, or dedicated compute |
| Long-lived connections, custom protocols, stateful processes | Containers/VMs or services explicitly built for those patterns |
| Very large scheduled batches | Managed batch, container jobs, or worker clusters |

Serverless cuts idle compute, yet can cost more under steady load, long durations, high memory needs, or heavy provisioned capacity. Containers/VMs maximize sustained resource utilization, but demand engineering time for capacity planning, patching, cluster lifecycle, scaling, and resilience.

### 4.2. Illustrative Break-Even Model

Suppose we compare two options meeting the same SLO:

- Serverless: billed per request and duration, scaling linearly with transaction volume.
- Container: baseline monthly capacity cost plus variable scaling cost under load.
- Database, network, logs, and security costs are equal in this example and omitted for simplicity.
- Migration and engineering labor are excluded to keep the math focused.

| Volume | Serverless (million VND/month) | Container (million VND/month) |
| --- | ---: | ---: |
| 100,000 transactions | 8 | 24 |
| 500,000 transactions | 20 | 27 |
| 1,000,000 transactions | 38 | 31 |
| 2,000,000 transactions | 74 | 42 |

These hypothetical figures illustrate how the cost advantage can flip as volume grows. Never assume a universal break-even threshold across all services. Each workload differs in duration, memory, concurrency, DB call ratio, and traffic shape.

### 4.3. Accounting for Operational Labor

Lower compute bills do not guarantee lower total cost of ownership (TCO). Containers require patching, capacity planning, deployment pipelines, cluster upgrades, node lifecycle management, scaling tuning, and on-call support. Serverless removes some host administration, yet demands deeper fluency in quotas, event semantics, distributed tracing, cold starts, and per-service billing models.

Estimate **TCO**:

~~~text
TCO
  = Infrastructure and managed-service charges
  + Network and data transfer
  + Observability and security
  + Engineering and operational effort
  + Support, migration and exit cost allocation
  - Discounts / credits that are actually applicable
~~~

Estimate labor from real engineering hours or realistic allocations—never default it to zero merely because a platform is managed.

## 5. Sensitivity Analysis: Load, Duration, and Retries

Cost models need at least three scenarios: low, expected, and peak. For functions, key variables include:

- Invocation/job count.
- Average execution duration and tail distribution.
- Memory/CPU or resource tier configuration.
- Concurrency and provisioned capacity.
- Retry, failure, and DLQ rates.
- Cache hit ratio vs. database query rate.
- Request/response/message sizes and egress volume.
- Log verbosity, trace sampling, and retention.

For example, if duration climbs from 200 ms to 800 ms because a downstream service slows down, compute duration rises roughly fourfold for the same invocation count (before rounding and tier specifics). That signals a need to investigate dependency latency rather than merely micro-optimizing function code.

One modeling approach:

~~~text
Monthly execution seconds
  = invocation count × average billable duration

Estimated peak concurrency
  ≈ arrival rate per second × average execution time in seconds
~~~

This estimates concurrency via Little's Law under steady arrival. Actual peaks also depend on bursts, duration variance, concurrency limits, and scaling mechanics. Never provision capacity for short spikes solely from long-term averages without testing.

## 6. Observability Costs Can Become Significant

Logs and traces are essential for diagnostics, yet debug-logging every request, storing full payloads, and capturing 100% of traces indefinitely can inflate bills dramatically.

Governance practices:

- Emit structured logs with explicit fields and avoid logging unnecessary payloads.
- Set retention policies per log class and audit requirement.
- Sample traces selectively; keep higher sampling for errors and critical transactions.
- Control label/metric cardinality; never create metric labels per user ID or request ID.
- Tune log levels per environment.
- Separate long-retention audit logs from short-lived debug logs.
- Track observability spend per workload, team, and tenant.
- Configure ingest quotas and alerts so a logging loop cannot cause runaway bills.

Never cut logging costs by deleting mandatory security or audit evidence. Optimize strictly in alignment with data purpose and retention policies.

## 7. Serverless Observability: Metrics, Logs, and Traces

### 7.1. Why Is Serverless Harder to Observe Than a Single Process?

In an event-driven flow, one business transaction may traverse an API gateway, function A, a queue, function B, a database, and external services. Each function is an independent invocation; per-process logs cannot automatically stitch the full journey together.

An ideal trace:

~~~mermaid
flowchart LR
    CLIENT["Client"] --> GW["API Gateway"]
    GW --> F1["Function: create order"]
    F1 --> DB[("Order DB")]
    F1 --> Q[("Queue")]
    Q --> F2["Function: notification"]
    F2 --> EXT["Email provider"]
    F1 -. trace context .-> Q
    Q -. trace context .-> F2
~~~

Propagate correlation and trace context across events/messages and outbound calls. Business IDs like `orderId` help operators look up records; trace IDs let tracing backends link spans across one execution; both serve distinct purposes.

### 7.2. Metrics: Measuring Health and Outcomes

| Metric group | Examples | Meaning |
| --- | --- | --- |
| Invocation | Request count, invocation count, throttles | Traffic volume and throttling pressure |
| Duration | Average, p95/p99, max duration | Execution speed and timeout risk |
| Errors | Error count, failure rate, timeout rate | Processing reliability |
| Concurrency | Concurrent executions, reserved/provisioned capacity | Resource pressure and saturation |
| Cold starts | Cold-start count/duration (when exposed by platform) | Impact of fresh environment initialization |
| Queue | Depth, oldest message age, DLQ count | Backlog and async processing lag |
| Database | Connections, throttling, latency, capacity | Data-layer health |
| Business | Orders completed, payment success, reports completed | Outcomes users actually care about |
| Cost | Cost per successful transaction, log bytes, egress | Economic efficiency |

Infrastructure metrics never replace business metrics. A function reporting 0% errors can still return 200 with wrong results or persist orders in invalid states. Track metrics confirming **valid business completion**.

### 7.3. Logs: Contextual Events

Logs should follow a consistent structure, for example:

~~~json
{
  "timestamp": "2026-11-18T02:04:05Z",
  "level": "ERROR",
  "service": "booking-worker",
  "function_version": "42",
  "invocation_id": "invoke-7f1a",
  "correlation_id": "corr-8e1c",
  "order_id": "order-1842",
  "tenant_id": "tenant-12",
  "event": "inventory_reservation_failed",
  "error_type": "DownstreamTimeout",
  "retry_attempt": 2
}
~~~

This structure is illustrative. Never log access tokens, secrets, payment details, or full personal information. If a tenant ID or order ID could identify an individual in a given context, apply appropriate protection policies.

Distinguish application logs, platform logs, audit logs, and access logs. Each serves a different purpose with distinct access controls and retention windows.

### 7.4. Tracing: Stitching Distributed Steps

A distributed trace links spans via parent/child relationships. Propagate trace context across HTTP headers and message metadata. If a message queue or trigger does not automatically preserve W3C Trace Context, safely embed required context in message attributes.

Traces pinpoint time spent in functions, databases, queues, external calls, and waits. However, tracing does not retain all business events forever; pair it with logs and audit trails with appropriate retention.

When sampling, consider:

- Head sampling by percentage for routine traffic.
- Tail sampling to keep traces with errors, high latency, or critical transaction types.
- Consistent sampling across services to avoid broken partial traces.
- Protecting sensitive attributes and bounding collector/backend costs.

## 8. Business-Journey Dashboards and Alerting

An effective dashboard answers four questions:

1. **Are users completing transactions?** Booking success rate, payment confirmations, p95/p99 latency.
2. **Where is the system bottlenecked?** Function duration, throttling, DB latency, queue age, external dependencies.
3. **Is any work getting dropped or delayed?** Job age, DLQs, missed schedules, retry rates.
4. **Why is cost rising?** Invocations, duration, networking, DB operations, log ingestion, and cost per transaction.

Alerts must reflect user impact or actionable anomalies. Examples:

- Valid booking success rate drops below SLO over an evaluation window.
- API p99 stays above threshold for a sustained period.
- Functions suffer continuous throttling or rising timeout rates.
- Oldest queue message age exceeds business deadlines.
- New messages enter the DLQ or grow rapidly.
- Scheduled reports fail to appear on time.
- Costs or log ingestion exceed baselines/budgets.
- Database connections/concurrency hit thresholds risking cascading failures.

Avoid paging on every isolated invocation error if it creates alert fatigue. Use evaluation windows, sustained-breach conditions, severity tiers, runbooks, and clear owners for each alert.

## 9. Platform Constraints to Evaluate

Serverless limits vary widely by service. Every design must inspect current documentation and quotas for the target platform, test real configurations, and record critical limits. Never assume all FaaS platforms share runtime limits or semantics.

### 9.1. Execution Duration and Workload Types

Functions enforce maximum execution durations. Jobs exceeding limits must be split into smaller steps, workflows, queues, or moved to containers/batch compute. Timeouts never prove side effects did not happen; retries can still redeliver work.

Questions to answer:

- What is the maximum execution duration per invocation?
- Are long-running jobs or async executions supported?
- Upon timeout, does the platform kill the process immediately or follow a grace policy?
- Are graceful shutdown signals and checkpoints available?
- Does the workload need specific CPU/GPU, memory, or OS libraries?

### 9.2. Cold Starts and Latency

Cold start is the environment initialization time prior to handling an invocation. It is shaped by runtime, artifact size, dependencies, VPC/network setup, concurrency spikes, and platform settings.

Ways to reduce impact:

- Trim dependencies and package size.
- Initialize SDKs/clients efficiently and reuse execution environments when allowed.
- Use provisioned/minimum concurrency when latency gains justify cost.
- Move heavy work off the synchronous request path.
- Measure p95/p99 under both steady load and bursts—never rely on a single warm call.

Keeping pre-warmed capacity cuts cold starts at the cost of paying during low traffic. Decide based on latency SLOs and business value.

### 9.3. Concurrency, Throttling, and Quotas

Concurrency measures simultaneous executions. Limits exist at account, function, region, and downstream service levels. Traffic bursts can scale compute faster than databases or external APIs can absorb.

Implement:

- Reserved/concurrency limits or equivalent controls for critical workloads.
- Concurrency caps on consumers and DB connections.
- Queue buffering and backpressure for deferrable work.
- Rate limits toward payment, ERP, and external APIs.
- Capacity plans covering bursts, cold starts, and quota increases.
- Quota-exhaustion tests to observe responses, retries, and alerts.

Autoscaling is not infinite. If multiple functions scale concurrency together, databases can run out of connections long before compute hits its ceiling.

### 9.4. Payloads, Events, and Ephemeral Storage

Platforms cap request/response sizes, events, environment variables, and messages. Store large payloads in object storage or databases and pass references/keys rather than embedding data inside events.

Local filesystems are typically ephemeral and vanish when environments recycle. Never store job state, idempotency keys, or durable files in temporary directories without external persistence.

### 9.5. Runtimes, Languages, and Dependencies

Platforms support specific runtimes, versions, support lifecycles, and binary packaging models. A package relying on native libraries, extensions, fonts, or executables may run locally in a container yet fail inside a serverless runtime.

Evaluate:

- Runtime/ABI compatibility and version support lifecycle.
- Deployment artifact/layer size limits.
- Native dependencies and CPU architecture (x86/ARM).
- Parity across local, CI, and production testing.
- Runtime upgrade procedures and end-of-support handling.

### 9.6. Networking and Private Connectivity

Functions placed in private networks can reach private databases, though network attachment can impact cold starts, throughput, IP exhaustion, and NAT/egress costs. Platforms differ in VPC attachment models, private endpoints, and interface/connection caps.

Verify:

- Is outbound Internet needed, or can private endpoints suffice?
- Are static source/egress IPs required for partner allowlists?
- Are long-lived DB connections supported, or is pool/proxy management needed?
- Does DNS resolution work properly in private zones?
- Are security groups/firewalls and routes configured symmetrically?
- How are egress, NAT, and cross-zone traffic billed?

Never open an entire subnet to functions just to bypass a connectivity error. Specify exact destinations, ports, identities, and allowed traffic flows.

### 9.7. Storage, State, and Long-Lived Connections

Functions suit stateless execution. Place state in databases, object storage, caches, queues, or dedicated state stores. Workloads requiring long-lived WebSockets, sticky sessions, continuous background processes, or stable connection pools need services built for those patterns—such as managed gateways paired with other compute.

Never let every invocation open excessive fresh DB connections. Reusing clients across warm environments lowers overhead, provided expired connections are handled and environment longevity is never assumed.

### 9.8. Observability, Debugging, and Environment Restrictions

Managed runtimes restrict host access, debuggers, filesystems, processes, and networking. Logs may flush asynchronously; align timestamps, cold-start markers, and invocation IDs carefully when correlating events.

Verify the ability to:

- Correlate requests and messages across functions.
- Capture timeouts, throttling, and platform-level errors.
- Debug race conditions or failures appearing only at high concurrency.
- Audit configuration changes under least-privilege access.
- Export metrics/logs to centralized observability without runaway charges.

## 10. Provider Constraints and Vendor Lock-In

### 10.1. Where Lock-In Typically Appears

Lock-in extends far beyond function handler signatures. It emerges in:

- Event triggers, event filtering, and delivery semantics.
- IAM policies, role assumption, and service-to-service identities.
- Managed workflows, state machines, and retry behaviors.
- Databases, query APIs, indexing, and transaction semantics.
- API gateways, authorizers, routing, and WAF integrations.
- Object storage events, lifecycles, and notifications.
- VPC integrations, private endpoints, and network policies.
- Logging/metrics/tracing schemas and query engines.
- Deployment packages, runtimes, layers, and secret formats.

Using HTTP, JSON, SQL, or containers does not automatically make an entire application portable. Semantic differences in events, timeouts, retries, transactions, and IAM still create lock-in.

### 10.2. Deliberate Dependency Assessment

Maintain a dependency register:

| Component | Service/standard used | Migration impact | Risk mitigation |
| --- | --- | --- | --- |
| Compute | Specific FaaS runtime | Rewrite handlers, runtime, packaging, timeout model | Keep domain logic independent; isolate adapters at edges |
| Events | Managed event bus | Rewrite routing rules, filtering, delivery semantics | Explicit event contracts and schema versioning |
| Workflows | Managed state machine | Port orchestration, retries, and state definitions | Separate business state; document workflow logic |
| Data | Managed database | Export schema/data, adapt queries/consistency | Test backups/exports, enforce data ownership and contracts |
| Identity | Provider-specific IAM | Rewrite roles/policies, trust chains, auth flows | Use standard federation/protocols where suitable |
| Observability | Vendor logging/tracing | Rebuild dashboards, alerts, retention, queries | OpenTelemetry, standard log schemas, export paths |
| Networking | VPC endpoints and private routing | Reconfigure IPs, routing, security rules | IP planning, interface-driven IaC modules |

The goal is not to eliminate all lock-in. Specialized managed services dramatically cut operational toil and improve reliability. Know where lock-in lives, what value it buys today, and what switching will cost if migration becomes necessary.

### 10.3. Levels of Portability

Portability can be divided into three tiers:

1. **Code portability:** building and running core logic on another runtime with minor edits.
2. **Operational portability:** deploying, authorizing, observing, scaling, and troubleshooting in another environment.
3. **Data and workflow portability:** migrating data, preserving event semantics, transferring state, and recovering job history.

A container running on two clouds proves partial code/runtime portability; it does not prove IAM, managed databases, event triggers, or disaster recovery can move unmodified.

## 11. Designing Just-Enough Abstraction

### 11.1. Place Boundaries Around Volatile Dependencies

A Java application can define an interface for a business action and implement it via a concrete adapter:

~~~java
public interface InvoicePublisher {
    PublishResult publish(InvoiceEvent event);
}

public final class BillingUseCase {
    private final InvoicePublisher publisher;

    public BillingUseCase(InvoicePublisher publisher) {
        this.publisher = publisher;
    }

    public void execute(InvoiceEvent event) {
        publisher.publish(event);
    }
}
~~~

The adapter integrates with the current managed event service while business logic stays decoupled from vendor SDKs. However, abstract only differences the application genuinely expects to swap. Do not build bloated universal cloud wrappers that strip away valuable platform features.

### 11.2. Keep Contracts and Semantics Explicit

- Version event schemas and enforce compatibility rules.
- Document ordering, duplicate, retry, retention, and failure semantics.
- Never leak SDK objects into domain/application layers.
- Separate business state from workflow execution metadata.
- Design idempotency around business keys.
- Maintain adapter integration tests and producer/consumer contract tests.

A generic interface cannot hide the fact that one queue guarantees per-partition ordering while another does not. When abstractions ignore semantics, bugs surface during migration or production load.

### 11.3. Validate Exit Capability Through Drills

A portability plan matters only if tested:

1. Build the application in an alternate pipeline.
2. Deploy a small workload slice on the target platform.
3. Provision IAM, networking, secrets, and observability.
4. Replay a sample set of test events.
5. Export/restore the database and verify integrity.
6. Run load and failure tests.
7. Measure cost, elapsed time, and required code changes.

Exercise a small slice quarterly or during major platform changes rather than discovering hidden dependencies during an urgent full-system migration.

## 12. Quality Scenarios and SLOs for Serverless

A quality scenario specifies source, stimulus, environment, artifact, response, and measure. Thresholds below are **educational examples only**.

| ID | Scenario | Expected response | Illustrative measure |
| --- | --- | --- | --- |
| QA-COST-01 | Traffic surges 5x during a promotion | Compute scales without runaway cost or DB overload | Cost per successful booking within budget; DB connections below cap |
| QA-OBS-01 | Message traverses API, queue, and two functions | On-call traces the entire journey | 99% of valid messages carry correlation IDs; trace connects all hops |
| QA-LAT-01 | Function receives burst after idle period | System holds latency within target | End-to-end request p95/p99 below threshold under load test |
| QA-REL-01 | Function times out after side effect commits | Retries create no duplicate transactions | Zero duplicate bookings/payments across test suite |
| QA-PLAT-01 | Concurrency quota hits limit | System applies backpressure with zero lost messages | Throttling alerted; oldest message age stays within bounds |
| QA-EXIT-01 | Event-driven capability must move to another runtime | Data/contracts export and reprocess cleanly | Working prototype within approved time/cost budget |
| QA-SEC-01 | Tenant A function attempts to read Tenant B data | Access denied and audited | 100% of unauthorized attempts blocked in test suite |

SLOs must state exact measurement points and windows. Function duration p95 does not equal end-to-end API p95 because it excludes gateway, queue, database, and downstream hops.

## 13. What Belongs on a Serverless Dashboard?

A workload dashboard should organize these sections:

| Section | Contents |
| --- | --- |
| Business outcomes | Successful bookings/payments, completion rates, business errors |
| Request path | Request rate, p50/p95/p99, HTTP errors, timeouts |
| Function health | Invocations, duration, errors, throttles, concurrency, cold-start indicators |
| Async processing | Queue depth, oldest age, retries, DLQ count, job duration |
| Dependencies | DB connections/latency, external API errors, networking/egress |
| Observability health | Log ingest, dropped traces, collector/backend errors |
| Cost | Cost by function, service, tenant/workload, cost per successful transaction |
| Governance | Runtime versions, deprecated versions, policy violations, quota utilization |

Maintain a product-level overview dashboard linking down to function, event pipeline, database, and cost views. On-call responders should start from **what users are experiencing**, not from dozens of isolated platform metrics.

## 14. Cost Governance and Guardrails

### 14.1. Budgets, Alerts, and Anomaly Detection

Set budgets by workload, environment, or team. Configure multi-threshold alerts before budgets breach; detect anomalies in invocations, duration, egress, DB operations, and log ingestion.

Define concrete actions per alert: lower debug log levels, shed non-critical traffic, halt unapproved load tests, trim concurrency, or switch workloads to degraded modes. Never auto-disable a critical payment or order function solely on a financial threshold without risk analysis.

### 14.2. Cost Allocation and Tagging

Apply consistent tags/labels such as `application`, `environment`, `team`, `owner`, `cost-center`, and `data-classification`. Separate accounts/projects for production, staging, and development where appropriate; use budgets and quotas so test workloads cannot incur runaway production-scale bills.

Logging and egress costs are frequently overlooked because they sit outside compute line items. Build dashboards per cost category and monitor variance relative to transaction volume.

### 14.3. Targeted Optimization

Effective levers:

- Cut unnecessary invocations via batch/bulk APIs when business rules allow.
- Avoid per-record function fan-out when records can be grouped.
- Offload non-blocking tasks to queues.
- Use caches with proper TTLs and invalidation to reduce DB calls.
- Tune memory/CPU via benchmarks rather than blindly picking the smallest tier.
- Trim dependencies/package size when measured cold starts matter.
- Align log retention and sampling with actual diagnostic/audit value.
- Enforce lifecycle cleanup on temporary objects, DLQs, and job data.
- Prevent retry storms and cap downstream concurrency.

Optimization must preserve SLOs, correctness, and security; saving money at the cost of double bookings or lost audit trails is never acceptable.

## 15. Operational Risks and Mitigations

| Risk | Symptom | Mitigation |
| --- | --- | --- |
| Rising cold starts | p95/p99 spikes after idle periods or bursts | Benchmark, add provisioned capacity if justified, shrink packages |
| Concurrency spikes | Throttling, DB connection exhaustion | Concurrency caps, queues, backpressure |
| Timeouts and retry storms | Surging invocations, slow dependencies, growing backlog | Timeout budgets, backoff/jitter, DLQs, circuit breakers |
| Log explosion | Rising ingest bills, sluggish dashboards | Sampling, log-level controls, retention, ingest alerts |
| Duplicate events | Repeated side effects | Idempotency and unique business keys |
| Quota exhaustion | Rejected deployments or invocations | Capacity forecasting, quota alerts/increases, graceful degradation |
| Runtime end-of-support | Blocked updates or security exposure | Runtime inventory, upgrade schedules, compatibility tests |
| Provider service changes | Altered triggers, permissions, or behavior | IaC reviews, contract tests, release-note tracking |
| Poor cross-function traceability | Cannot stitch logs for one transaction | Correlation IDs, trace propagation, structured logs |
| Surprise egress bills | Spiking charges on cross-region/provider calls | Data-flow mapping, egress dashboards, placement reviews |

## 16. Case Study: Serverless Booking Platform

### 16.1. Context

A company deploys a booking API on serverless. Users call an API through a gateway; a function authenticates, validates input, and writes the booking; an event enters a queue to trigger confirmation emails and analytics updates.

Hypothetical requirements:

- 300,000 successful bookings/month.
- Booking API p95 ≤ 500 ms under target load.
- Confirmation emails attempted within 2 minutes of booking confirmation.
- Retries create zero duplicate bookings or duplicate emails.
- Platform spend remains within approved budget.
- Operators can trace any booking across API, queue, worker, and email provider.

### 16.2. Architecture and Observability

~~~mermaid
flowchart LR
    USER["Web / Mobile"] --> GW["API Gateway"]
    GW --> F1["Booking Function"]
    F1 --> DB[("Booking DB")]
    F1 --> OUTBOX["Outbox / Event"]
    OUTBOX --> Q[("Queue")]
    Q --> F2["Notification Function"]
    F2 --> EMAIL["Email provider"]
    GW -. metrics / trace .-> OBS["Observability"]
    F1 -. logs / trace .-> OBS
    F2 -. logs / trace .-> OBS
    DB -. metrics .-> OBS
    Q -. queue age / DLQ .-> OBS
~~~

Each booking carries a correlation ID, while notification jobs carry distinct job/event IDs. Trace context propagates through message metadata; business IDs support domain status lookups.

### 16.3. Sample Cost Model

Assume 300,000 bookings/month with hypothetical costs:

| Component | Million VND/month |
| --- | ---: |
| Booking function + gateway | 22 |
| Database/cache | 28 |
| Queue/event + notification function | 10 |
| Network/egress | 5 |
| Logs/metrics/traces | 8 |
| Security/KMS/audit | 4 |
| **Total** | **77** |

~~~text
Cost per successful booking
  = 77,000,000 / 300,000
  ≈ 257 VND / booking
~~~

If booking volume drops by half, compute charges fall, yet database minimum capacity, provisioned concurrency, log retention, and fixed platform charges may not shrink proportionally. If traffic jumps fivefold, quotas, concurrency, and downstream DB limits matter—costs do not necessarily scale linearly with invocations alone.

### 16.4. Dashboard Diagnostics

Suppose the dashboard shows the booking API returning successes while oldest queue message age climbs from 20 seconds to 4 minutes. Booking creation is healthy, yet notifications are lagging and approaching SLO breach.

Operators inspect notification function duration, throttles, email provider latency, and concurrency. If downstream rate limits are the bottleneck, immediately raising worker concurrency makes things worse. Keep concurrency within provider quotas, apply backoff with jitter, monitor retries, and track email state clearly in the job store.

### 16.5. Verifying Platform Constraints

Before production launch, the team tests:

- Burst traffic and cold starts using real artifacts.
- Quotas/concurrency in the target deployment region.
- Timeouts when databases or email providers respond slowly.
- Database connections under high concurrent invocations.
- Payload/message sizes in reporting flows.
- Log/trace context preservation across queue triggers.
- Runtime upgrades in staging.
- Data export and running a prototype worker in an alternate environment.

Test evidence guides whether provisioned capacity, container workers for long jobs, or lower lock-in on specific components are warranted.

## 17. Serverless Platform Evaluation Checklist

### Cost

- [ ] Invocations, duration, memory/CPU, and pre-warmed capacity are modeled.
- [ ] Databases, queues, object storage, API gateways, egress, and private networking are accounted for.
- [ ] Log/trace ingestion, retention, security, and audit fees are included.
- [ ] Retries, failures, DLQs, replays, and manual interventions are budgeted.
- [ ] Cost per successful transaction is modeled across low, expected, and peak traffic.
- [ ] Budgets, tags/labels, cost allocation, and anomaly alerts are active.

### Observability

- [ ] SLIs/SLOs exist for both business outcomes and request paths.
- [ ] Structured logs, correlation IDs, and trace propagation span event boundaries.
- [ ] Metrics cover invocations, duration, throttles, concurrency, and cold-start indicators.
- [ ] Queue depth, oldest age, retries, DLQs, and expected-run monitors are tracked.
- [ ] Dashboards, alerts, runbooks, and owners are established.
- [ ] Cardinality, sampling, retention, and sensitive data redaction are enforced.

### Platform Constraints

- [ ] Runtimes, max durations, memory/CPU, and artifact sizes are verified.
- [ ] Cold starts, concurrency, timeouts, payloads, and quotas are tested.
- [ ] VPC/private networking, DNS, egress, and DB connections are validated.
- [ ] Ephemeral filesystems, state, connection lifecycles, and graceful shutdowns are verified.
- [ ] Event delivery, ordering, retries, retention, and trigger semantics are documented.
- [ ] Runtime upgrade schedules and deprecation procedures exist.
- [ ] A dependency register, ADRs, and portability/exit drills are maintained.
- [ ] Load, fault injection, security, and restore tests run prior to production.

## 18. Well-Architected Evaluation

| Pillar | Questions for serverless evaluation |
| --- | --- |
| **Operational Excellence** | Can the team trace jobs/requests across functions, maintain runbooks, IaC, and runtime upgrade workflows? |
| **Security** | Do functions enforce least privilege, secret protection, tenant isolation, and proper auditing? |
| **Reliability** | Are retries, idempotency, DLQs, timeouts, quotas, and dependency failures tested? |
| **Performance Efficiency** | Do cold starts, concurrency, memory, networking, and databases meet p95/p99 under real load? |
| **Cost Optimization** | Do end-to-end and per-transaction costs stay within budget across all load scenarios? |
| **Sustainability** | Are idle compute, excessive logging, duplicate processing, and redundant transfers minimized? |

## 19. Hands-On Exercise

An invoice management service plans to run serverless. Monthly volume is 2 million invoice-creation requests, plus a heavy end-of-month reconciliation batch. The API must acknowledge within 700 ms p95; PDF invoices generate asynchronously and must be downloadable within 3 minutes; operators must trace any invoice across API, queue, and worker. Budget is tight and the organization may migrate platforms in the future.

Complete the following:

1. Break down costs across compute, gateway, database, object storage, queues, networking, observability, and security.
2. Build cost per successful invoice across three volume scenarios, including retries and failed invoices.
3. Compare event-driven functions against always-on container workers for PDF generation.
4. Design a metrics/logs/traces dashboard linking correlation IDs from API through queue to worker.
5. Define alerts for p95 latency, throttling, oldest message age, DLQs, cost spikes, and missed batches.
6. List platform constraints: timeouts, payloads, runtimes, memory, concurrency, quotas, filesystems, and networking.
7. Identify the top three vendor lock-in points; propose which abstractions help and which add unnecessary bloat.
8. Design an experiment migrating one worker to another runtime/container, covering data, IAM, networking, observability, and load testing.
9. Write an ADR documenting the chosen approach, metrics, residual risks, and review triggers.

**Self-assessment hint:** A strong solution goes beyond citing function prices or claiming "serverless autoscales"—it explains the full cost path, traceability, service quotas, and platform limits backed by test evidence.

## Conclusion

Serverless reduces server-management toil and excels for event-driven, bursty, or uneven workloads. That value holds only when **end-to-end TCO** fits the budget, teams can observe complete business journeys, and platform constraints never violate SLOs.

Measure cost per successful transaction, govern logs and traces intentionally, cap concurrency and quotas, understand event/retry semantics, and document provider dependencies. When portability matters, test exporting, deploying, and operating a real slice rather than relying solely on generic interfaces or containerization claims. Final decisions must balance reliability, security, performance, scalability, cost, and operations in the Well-Architected spirit.
