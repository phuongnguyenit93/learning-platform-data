# Do Not Use Liveness as a Business Metric in Spring Boot

> **Chapter:** Health and readiness  
> **Lesson:** Do not use liveness as a business metric  
> **Module:** SPRING_BOOT_OBSERVABILITY — Set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What question does liveness answer?

Liveness is a signal indicating whether a process/container is still alive and able to continue running. In Kubernetes, when a liveness probe fails consecutively beyond the configured threshold, kubelet may restart the container. Therefore, liveness must reflect conditions that a process restart can actually recover from.

Liveness is not a business quality score. It does not answer how many orders were accepted, what the payment success rate is, whether users completed checkout, whether a queue is draining within SLA, or whether the request success ratio meets its target. Those questions require business metrics, service-level indicators (SLIs), logs, and traces.

~~~mermaid
flowchart TD
  A["Application process"] --> B["Liveness probe"]
  B --> C{"Process can continue?"}
  C -->|"No"| D["Restart container"]
  C -->|"Yes"| E["Keep process running"]
  F["Business operations"] --> G["Business metrics / SLIs"]
  G --> H["Dashboards and alerts"]
  I["Dependency / request health"] --> J["Readiness probe"]
  J --> K["Route or remove traffic"]
~~~

If liveness is used to check a business KPI such as payment success rate, a spike in business errors can cause all pods to restart. Restarting will not fix a business rule, invalid input data, or a failing payment provider; it only reduces capacity and can worsen the incident.

## 2. Distinguishing liveness, readiness, and business metrics

Three mechanisms serve three different decisions:

| Mechanism | Question | Primary action |
| --- | --- | --- |
| Liveness | Does the process need a restart to recover? | Restart container when probe fails per policy |
| Readiness | Should this instance currently receive new traffic? | Add/remove instance from serving endpoints |
| Business metrics | What results are business operations achieving? | Dashboards, alerts, SLO reviews, and investigation |

Examples:
- JVM deadlock or stalled event loop: likely a liveness concern.
- Database temporarily unavailable and API cannot serve DB-backed requests: likely a readiness concern.
- Rising order rejection rate due to out-of-stock items: business metric, not a liveness failure.
- Payment success rate dropping due to the payment provider: business/availability metric that may affect readiness per contract; not automatically a liveness failure.

A service can have liveness UP, readiness DOWN, and a declining business success rate at the same time. That is not a contradiction: the process is still alive, the instance should not currently accept traffic, and business outcomes are degraded.

## 3. Why should business KPIs not be placed into liveness?

Liveness failures typically trigger restarts. If a probe depends on a business KPI, a business fluctuation can create a feedback loop:

1. Payment provider errors lower the payment success rate.
2. The liveness endpoint reads the KPI and returns DOWN.
3. Kubernetes restarts pods.
4. New pods must warm up, open connections, and initialize caches.
5. Capacity drops while the dependency is still failing.
6. Request timeouts rise and the KPI drops further.

Restarting does not change the provider's state or business data. It merely adds startup load and can trigger cascading failures.

Business KPIs are usually computed over a time window, with a sample size and baseline. Liveness probes are typically called frequently with short timeouts. Putting a windowed metric into a probe introduces mismatched semantics and can cause oscillating results.

## 4. Example: payment success rate is not liveness

Suppose `checkout-service` has business metrics:

~~~text
payment_attempts_total
payment_success_total
payment_declined_total
payment_provider_errors_total
~~~

Success ratio can be calculated over a window:

~~~text
payment_success_ratio =
  increase(payment_success_total[5m])
  /
  increase(payment_attempts_total[5m])
~~~

If the payment provider encounters an outage, the ratio may drop. That is a signal for alerting and investigation. The checkout process can still handle other endpoints, record pending states, or respond per a fallback contract.

Do not turn `payment_success_ratio < 0.9` into liveness DOWN. Instead:
- Alert on business SLIs/SLOs.
- Track provider error rates and latency.
- Inspect traces of payment client calls.
- Evaluate readiness if the instance cannot serve a mandatory capability.
- Keep liveness tied to the process's ability to continue running.

## 5. Example Spring Boot health groups configuration

Spring Boot Actuator can provide liveness/readiness health groups. Illustrative configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Include `db` in readiness when the database is genuinely required for the instance to accept the traffic under consideration. Do not put `db` or the payment provider into liveness just so a business dependency failure restarts pods.

Spring Boot can expose corresponding probe paths such as `/actuator/health/liveness` and `/actuator/health/readiness` when probes are enabled. Verify paths, group membership, and HTTP mapping in your application version.

### 5.1. Readiness also requires intentional dependency selection

If an optional dependency fails while the service still has a fallback, putting it into readiness can unnecessarily remove the instance from traffic. Conversely, if the database is mandatory for all requests, readiness can reflect database status.

Readiness policy should rely on instance capability and the traffic-routing contract, not on an unstable aggregate KPI.

## 6. Designing a proper liveness check

Liveness should be lightweight, fast, deterministic, and independent of downstreams that can fail separately.

Consider:
- Spring `ApplicationAvailability`/`LivenessState`.
- Process-local conditions indicating the application cannot make progress.
- An internal watchdog for deadlocks or stuck worker loops if it has reliable semantics.
- A health indicator checking only essential internal components recoverable by a restart.

Avoid:
- Calling the database or payment provider over the network on every liveness probe.
- Checking business success rates.
- Running heavy queries or transactions.
- Checking queue backlog and restarting because the queue is large.
- Using a health endpoint that aggregates all dependencies as liveness.
- Using overly short timeouts that cause restarts on brief spikes.

Not every process-local error warrants a restart. Only include conditions in liveness where restarting is a sound, tested recovery action.

## 7. What should business metrics measure?

Business metrics measure outcomes that users or the organization care about. Choose metrics by domain rather than treating health check counts as business activity.

Example for an order service:

~~~java
@Service
public class OrderMetrics {

    private final Counter accepted;
    private final Counter rejected;

    public OrderMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("orders.submission")
                .tag("outcome", "accepted")
                .register(registry);
        this.rejected = Counter.builder("orders.submission")
                .tag("outcome", "rejected")
                .register(registry);
    }

    public void recordAccepted() {
        accepted.increment();
    }

    public void recordRejected() {
        rejected.increment();
    }
}
~~~

These are custom metrics; call `record` at the business boundary after determining the outcome per contract. Avoid incrementing counters across multiple layers for the same business operation.

Helpful metrics include: orders submitted/accepted/rejected, payments authorized/declined/failed, checkout completion rate, fulfillment processing duration, queue enqueue-to-completion latency, refund rate, or cancellation rate.

Never use user ID, order ID, email, or raw exception messages as metric labels. Pick finite dimensions such as operation, outcome, channel group, or normalized region group.

## 8. Business SLIs and SLOs

An SLI is a quantitative measurement of an aspect of a service; an SLO is the target for an SLI over a time window.

Examples:
- Availability SLI: proportion of eligible requests completing per contract.
- Latency SLI: proportion of requests completing below a threshold.
- Checkout SLI: proportion of checkout attempts achieving an accepted outcome.
- Payment SLI: proportion of payment authorizations succeeding, excluding valid declines per business definition.

Hypothetical targets:
- 99.9% of eligible API requests return responses per contract over 30 days.
- 95% of checkouts complete within 2 seconds.
- Payment provider technical error rate below 0.5% over 5 minutes.

Targets must rest on real requirements with a clearly defined denominator. Do not treat 2xx ratio as business conversion rate if 4xx can be a valid business outcome.

Liveness is not an SLI. Liveness probes help the platform self-heal processes; SLIs/SLOs help teams evaluate user experience and service reliability.

## 9. Alert on business metrics, do not restart on KPIs

Business alerts should notify or trigger runbooks, not directly turn KPIs into liveness results.

Examples:
- Payment technical failures spiking: alert the payment team.
- Checkout completions dropping: alert business/on-call per severity.
- Fulfillment age exceeding SLA: alert the queue owner.
- Unusual refund rate increase: investigate releases, policies, or fraud signals.

Good alerts typically combine threshold, duration, baseline, traffic volume, and error budget. Avoid alerting when only a handful of transactions cause ratios to swing widely.

~~~mermaid
flowchart TD
  A["Business event"] --> B["Counter / histogram"]
  B --> C["SLI calculation"]
  C --> D{"SLO / alert condition"}
  D -->|"Breached"| E["Notify / incident workflow"]
  D -->|"Healthy"| F["Continue monitoring"]
  G["Liveness probe"] --> H["Restart only if process unhealthy"]
  I["Readiness probe"] --> J["Control traffic admission"]
~~~

Alerting and orchestration are two distinct control loops. Alerts feed incident workflows; liveness controls process lifecycle; readiness controls routing.

## 10. Combining health with metrics, traces, and logs

When a business KPI degrades, move from symptom to root cause:

1. Business metrics show which outcome dropped.
2. Service metrics show request rate, latency, errors, and saturation.
3. Traces pinpoint which operation/dependency is slow or failing.
4. Logs provide event and exception context.
5. Health/readiness indicates which instances are still eligible to accept traffic.

Example when payment success drops:
- Business metric: payment technical errors rise.
- HTTP client metrics: payment API 5xx/timeouts rise.
- Traces: payment client spans are slow or ERROR.
- Logs: timeouts/circuit breaker open.
- Readiness: DOWN only if the service cannot serve a mandatory capability per the routing contract.

Do not turn every trace error into a liveness failure. A trace error is evidence of a single operation; the process can still be operating normally.

## 11. Queue backlog and worker health

Queue depth, consumer lag, and oldest message age are operational metrics. Growing backlog does not automatically mean the worker process needs a restart.

Scenarios:
- Large producer burst: depth rises while throughput is also high.
- Slow consumer due to DB pool waits: worker is alive yet bottlenecked.
- Poison message: one message retries repeatedly, lag grows.
- Worker deadlock: process stops progressing, potentially a liveness concern if a watchdog detects it reliably.

Track arrival rate, successful processing rate, queue depth/consumer lag, oldest message age, processing duration, retry/DLQ count, and active consumers.

Alert when backlog breaches SLA and investigate consumers/downstreams. Only use liveness when the worker process is genuinely stuck and a restart can recover it; avoid restarting continuously because of a large queue.

## 12. Readiness when a business capability degrades

Readiness can depend on the ability to serve a class of traffic, yet should not be driven by an unstable aggregate KPI.

Examples:
- Service serves read-only when a database replica fails: may remain ready for read endpoints if routing supports it.
- Payment provider fails while order service still accepts orders in pending state: service can remain ready.
- One tenant has a high error rate: should not mark all instances not-ready if errors belong only to that tenant.
- Queue consumer falls behind while the HTTP API still accepts messages: API readiness and worker readiness may need separate evaluation.

For multi-capability services, one overall readiness boolean may be too coarse. Use health groups or endpoints/probes tailored to the architecture while keeping semantics clear for the platform.

## 13. Avoiding cardinality and sensitive data in business metrics

Business metrics have tempting dimensions like customer, product, order, or tenant. Putting high-cardinality IDs into labels causes time-series explosions and can expose data.

Instead use outcome (`accepted`/`rejected`/`pending`), operation (`checkout`/`payment`/`refund`), finite channel or region groups, and reason categories like `out_of_stock`/`invalid_request`/`provider_unavailable`.

Never use `customer_id`/`order_id`/`payment_id`, email, phone, arbitrary IP, raw exception messages, or request payloads as labels.

If per-entity analysis is needed, use event analytics or an access-controlled business data store; metric time series are not a per-transaction storage warehouse.

## 14. Testing liveness, readiness, and business metrics

Test the three mechanisms independently.

Liveness tests:
- Healthy process returns UP.
- Simulate a non-progressing process state per your designed watchdog.
- Verify dependency outages do not automatically turn liveness DOWN if restarting does not resolve them.

Readiness tests:
- Mandatory dependency unavailable marks readiness DOWN if required by contract.
- Optional dependency failures do not necessarily remove the instance from traffic.
- When the dependency recovers, readiness returns to UP.

Business metrics tests:
- Accepted/rejected/payment failed events increment the right counters.
- Each business event is recorded only once at the chosen boundary.
- KPIs calculate denominator and time window accurately.
- Metric labels have finite cardinality.

Example test scenario:

~~~java
@Test
void businessRejectionDoesNotChangeProcessLiveness() {
    // Arrange: process liveness is healthy.
    // Act: record a business rejection.
    // Assert: rejection counter increases; liveness remains UP.
}
~~~

This is a test scenario; implement it with your project's test framework and health configuration. Test the real HTTP endpoints to verify status mapping and probe behavior.

## 15. Troubleshooting when liveness and business metrics are mixed

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Pods restart when payment provider fails | Liveness calls provider or uses payment KPI | Remove dependency from liveness; use alerts/readiness per contract |
| Restart loop during DB outage | DB included in liveness | Move dependency check to readiness if appropriate |
| Business KPI bad while health UP | Health only reflects process/dependency checks | Create business dashboards/alerts |
| Health DOWN even though API serves fallback | Indicator checks an optional dependency | Define capabilities and readiness membership |
| Alert does not fire even when liveness fails | Alert relies on KPI instead of probe events | Track probe failure/restart metrics separately |
| Business success rate fluctuates wildly | Small sample size or wrong denominator | Use appropriate window and minimum traffic |
| Metric cardinality rises | Entity IDs used as labels | Normalize dimensions |
| Worker restarts continuously as lag grows | Queue backlog used as liveness | Alert on lag; check progress/dependencies |
| Readiness DOWN across all replicas | Shared dependency and overly broad policy | Evaluate fallback/failure domain |
| Liveness always UP even when process hangs | Probe does not reflect progress | Design process-local watchdog with bounded semantics |
| Business counter double-counts | Metric recorded at multiple layers or on retries | Pick business boundary, distinguish attempt/completion |

### Investigation workflow

1. Identify which probe is failing: startup, liveness, or readiness.
2. Inspect pod restart count and probe failure events.
3. Check which indicators belong to the health group.
4. Determine whether the business metric is merely a symptom or an actual loss of capability.
5. Correlate request metrics, traces, logs, and dependency health.
6. Assess whether restarting improves state or reduces capacity.
7. Separate business alerts from process lifecycle policies.
8. Test in staging with dependency outages and KPI regressions.

## 16. Real-world scenario: payment success rate drops while the process stays healthy

**Context:** `checkout-service` runs 8 replicas. The payment provider experiences an incident, dropping the payment success ratio from 99% to 60%. The API can still create pending orders and serve other functions. A custom liveness indicator returns DOWN when the payment ratio drops below 90%.

### Step 1 — identify the misplaced boundary

The liveness probe is reading a 5-minute windowed business KPI. The low KPI causes Kubernetes to restart pods even though the JVM and request handlers are functioning.

### Step 2 — remove the business KPI from liveness

Switch liveness back to process-local state. Continue recording the payment ratio via Counters/SLIs and separate alerts.

### Step 3 — evaluate readiness

If the service still accepts orders and stores pending states, readiness can stay UP. If a deployment mode only serves live payments without a fallback, readiness policy can reflect that capability per contract.

### Step 4 — supplement telemetry

Monitor payment provider client latency/errors, circuit breaker state, pending orders, retry count, and payment completion age. Client span traces help investigate provider timeouts.

### Step 5 — verify

Simulate a provider outage:
- Liveness remains UP.
- Readiness accurately reflects traffic-serving ability.
- Payment SLI drops and alerts fire.
- Pods do not enter a restart loop.
- Pending orders are tracked and processed once the provider recovers.

**Expected outcome:** process lifecycle is not driven by business KPIs; business degradation is still detected through appropriate telemetry and alerts.

## 17. Practice exercises and self-check questions

### Exercise A — signal classification

List 10 scenarios: JVM deadlock, DB outage, rising payment declines, rising queue lag, rising invalid requests, stuck worker, rising cache misses, disk full, provider timeout, and falling checkout conversion. Classify each as liveness, readiness, business metric, or a combination.

### Exercise B — separating liveness/readiness

Configure health groups in Spring Boot. Keep `livenessState` separate; put only mandatory dependencies in readiness. Simulate a database outage and verify pods do not enter a restart loop.

### Exercise C — business metrics

Create counters for orders accepted/rejected and payments authorized/declined/technical_error. Verify denominators, retry attempts, and duplicate recording. Keep labels finite.

### Exercise D — SLO-based alerting

Define business SLIs/SLOs for checkout. Create an alert on error budget burn or success ratio drops over a window with sufficient traffic. Verify the alert does not alter the liveness response.

### Exercise E — queue worker

Simulate queue backlog and slow worker processing. Track lag, oldest age, processing duration, and DB pool. Only mark liveness DOWN when the worker process truly cannot progress and restarting makes sense.

### Exercise F — failure drill

Simulate a payment provider timeout in staging. Verify liveness, readiness, business metrics, client traces, logs, and pod restart behavior. Write a runbook to handle KPI regressions without restarting the entire service.

### Self-check questions

1. What question does a liveness probe answer?
2. Why is a business success rate not a liveness signal?
3. How do liveness and readiness differ in platform actions?
4. When a payment provider fails, does the process necessarily need a restart?
5. What data should be used to measure business SLIs/SLOs?
6. Why are time-windowed business KPIs unsuited for short probes?
7. Is rising queue depth/lag a liveness failure?
8. When should a dependency affect readiness?
9. Why should not all dependencies be placed in liveness?
10. How do you distinguish HTTP success rate from business conversion rate?
11. Which metric labels can trigger a cardinality explosion?
12. How do you combine metrics, traces, and logs when a business KPI degrades?
13. How can a restart loop amplify a dependency outage?
14. What behaviors should be tested separately for liveness/readiness/business metrics?
15. How should a multi-capability service design readiness?

**Completion criteria:** explain liveness/readiness/business metrics; configure health groups properly; define business SLIs/SLOs; measure business outcomes with metrics; alert without restarting on KPIs; control cardinality; test dependency outages and KPI regressions.

## 18. Key takeaways

- Liveness decides whether a process needs restarting; it does not measure business quality or success rates.
- Readiness decides whether an instance should receive traffic; dependencies should only participate when they affect traffic-serving capability per contract.
- Business metrics measure accepted/rejected/failed outcomes, conversion, latency, and user-facing results.
- Degraded business KPIs generally require alerts, dashboards, and investigation; restarting processes will not fix business rules or external provider outages.
- Putting business KPIs into liveness can trigger restart loops and cut capacity right when the system needs capacity most.
- Spring Boot health groups separate `livenessState` and `readinessState` from dependency checks.
- Use Micrometer `Counter`/`Timer`/`DistributionSummary` with finite labels to measure business outcomes.
- Define SLIs/SLOs with clear denominators, eligibility, time windows, and expected business rejections.
- Combine business metrics with HTTP metrics, traces, logs, and dependency telemetry to locate root causes.
- Test liveness, readiness, and business metrics independently; verify outages do not cause unintended restarts.

## References

- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
