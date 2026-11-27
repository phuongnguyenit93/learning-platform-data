# SLOs for success, latency, and availability

In **SPRING_GRPC**, a service can continue accepting connections while responding slowly, processing incorrectly, or failing to serve a portion of RPCs. Reliability must therefore be measured with indicators reflecting what clients actually experience: whether requests are handled per contract, responses arrive within committed times, and the service is available to serve.

An SLO (Service Level Objective) is a quantitative target for one or more SLIs (Service Level Indicators). For gRPC, you must define clearly which requests count, what constitutes success, where latency is measured from start to finish, and which statuses represent operational failures. Without consistent definitions, dashboards can report a healthy service while clients continuously time out, or fire false alarms over valid business rejections.

## 1. Distinguishing SLI, SLO, and SLA

- **SLI:** an actual measurement, such as the proportion of RPCs completing per contract or the proportion finishing under 300 ms.
- **SLO:** a target for an SLI over a time window, such as 99.9% of eligible requests served successfully over 30 days.
- **SLA:** a service commitment to customers or consumers, potentially carrying support/credit remedies when missed.

SLOs should reflect what users care about, not just process state. A `Ready` pod does not prove every RPC succeeds; a `READY` channel does not guarantee the next call completes on time.

## 2. Choosing SLIs for success, latency, and availability

Three commonly used indicator groups:

| SLI | Question | Common measurement |
| --- | --- | --- |
| Success | Did the business operation achieve the desired outcome? | Successful operations / valid operations per business rules |
| Latency | Did the request complete within the target time? | Requests below threshold / total eligible requests |
| Availability | Can the service accept and process valid requests? | Served requests / total eligible requests; or uptime probes for low-traffic services |

A practical SLO can combine multiple targets concurrently:

- 99.9% of eligible requests served successfully over a rolling 30-day window.
- 95% of unary requests complete within 300 ms.
- 99% of unary requests complete within 1 second.
- Subscription streams meet connection-success and session-stability targets per dedicated policy.

Do not collapse everything into a single number. Success, latency, and availability capture distinct failure modes; each SLI needs its own denominator and classification rules.

## 3. Defining eligible requests and successful outcomes

Before calculating ratios, define **eligible requests**. For instance, include only production API RPCs while excluding health checks, reflection, test traffic, and internal methods outside user-facing SLOs.

For a request-based availability SLI, define a **good request** as an eligible request where the service returns a contract-allowed outcome before the request's deadline. For a latency SLI, a good request is one completing within threshold `T`. For a business success SLI, count only operations achieving the intended business outcome across defined valid operations.

One way to classify RPC outcomes for availability:

| RPC outcome | Treatment in availability SLI | Reason |
| --- | --- | --- |
| Valid response with OK status | Success | Server fulfilled the contract |
| INVALID_ARGUMENT | Can count as served | Request was invalid, yet server responded per contract |
| NOT_FOUND | Per contract | May be a valid business outcome |
| UNAUTHENTICATED / PERMISSION_DENIED | Can count as served | Server enforced authentication/authorization policy |
| UNAVAILABLE / INTERNAL / DATA_LOSS | Failure | Service unable to serve or server error |
| DEADLINE_EXCEEDED | Typically latency/availability failure | RPC failed to finish within deadline |
| CANCELLED | Classify by cause | Intentional caller aborts may be excluded from denominator; server cancels from overload must count |
| RESOURCE_EXHAUSTED | Per quota/capacity policy | Legitimate quota enforcement differs from server resource exhaustion |

Key point: **availability is not synonymous with business success**. If a caller asks for a nonexistent SKU and the service returns `NOT_FOUND` per contract, that still counts as a good request for availability because the service fulfilled the contract. It is not, however, a business success. Measure business outcomes separately if you need to track order acceptance, payment completion, or reservation success rates.

For `CANCELLED`, you cannot look at the status code alone and exclude everything from the denominator. Clients may cancel because users changed their minds, yet servers can also cancel due to shutdown or overload. Use client-side telemetry, cancellation reasons, or controlled exclusion policies to avoid hiding server failures.

## 4. SLI formulas

For request-based availability:

```text
Availability SLI =
  good eligible requests / total eligible requests

Error ratio = 1 - Availability SLI
```

For a latency threshold:

```text
Latency SLI(T) =
  eligible requests completed within T / total eligible requests
```

Example: over 30 days there are 2,000,000 eligible requests, and 1,998,200 are served successfully:

- Availability = 1,998,200 / 2,000,000 = 99.91%.
- Error ratio = 0.09%.
- With a 99.9% SLO, the service meets its target in this window.

If 1,940,000 out of those 2,000,000 requests finish within 300 ms, `Latency SLI(300 ms) = 97%`. With a 95% target, latency meets the objective even if a few tail requests are very slow.

Never average latencies and compare against a threshold as a substitute for a latency SLI. Averages conceal small groups of extremely slow requests. Use histograms to compute the fraction below threshold and track p50/p95/p99 to understand the distribution.

## 5. Choosing time windows and error budgets

SLOs are commonly evaluated over a rolling window, such as 7 or 30 days. Rolling windows reveal recent health without waiting for a calendar month to end.

For a 99.9% availability SLO:

```text
Allowed error ratio = 1 - 0.999 = 0.001 = 0.1%

Error budget = eligible requests x 0.1%
```

With 2,000,000 eligible requests in the window, the error budget is 2,000 failed requests. If 1,500 have been spent, 500 remain in the budget.

Error budgets guide release velocity and reliability prioritization. When budget burns quickly, the team should lower change risk, address root causes, and consider rollbacks/deployment freezes per policy. While budget remains healthy, feature delivery can proceed within agreed risk limits.

Never use error budgets to rationalize recurring outages. SLOs are tools for managing risk and prioritizing engineering work, not targets to game by stripping failed requests out of the denominator.

## 6. Setting SLOs per gRPC service and method

One server hosts multiple services with differing latency profiles. You should not apply the same threshold to every method.

Example:

| Service/method | Processing pattern | Suggested latency SLI |
| --- | --- | --- |
| Inventory/GetStock | Unary, fast read | Fraction finishing under 150 ms |
| Order/CreateOrder | Unary, transactional | Fraction finishing under 500 ms |
| Report/Generate | Unary, heavy task | Fraction under 2 seconds or convert to async job |
| Notification/Subscribe | Long-lived server streaming | Connection success rate, time to first message, abnormal disconnect rate |
| Upload/SendChunks | Client streaming | Upload completion rate, throughput, and per-session error rate |

Set SLOs at the service/method level whenever user experience differs. You can maintain an overall product API SLO, yet you need per-method breakdowns on dashboards to see which method is burning error budget.

Avoid unbounded labels such as user ID, order ID, SKU, or dynamic full request paths. Use bounded-cardinality dimensions like service, method, status class, outcome, and deployment version.

## 7. Measuring latency with accurate start and end points

For unary RPCs, client-side latency should measure from call initiation until receiving the response or terminal error. This captures the end-to-end experience callers perceive, including networking, queueing, server processing, and the return path.

Server-side duration typically measures from when the server receives the call until the call closes. The two measurements need not match:

- Client latency includes DNS/connect/reconnect, TLS, proxies, networking, and client-side waiting.
- Server duration reflects server processing after the call reaches the server.
- Downstream spans reflect individual dependencies.
- Queue waits and connection acquisition explain time spent before actual processing starts.

Measure both client and server sides to separate slow server processing from network issues or client-side queues. Never infer client latency solely from server timers.

## 8. Defining latency for streaming RPCs

Streaming RPCs have a different lifecycle from unary calls, so a single latency metric is insufficient:

- **Time to first message:** from when the client starts the call until the first message arrives.
- **Inter-message gap:** interval between consecutive messages.
- **Stream completion duration:** total time from stream open until stream termination.
- **Unexpected termination rate:** share of streams ending due to out-of-policy errors.
- **Reconnect success/time:** time required for clients to reconnect and resume.

A subscription stream can stay open for hours; feeding total stream duration into a unary histogram produces meaningless distributions. Set dedicated SLOs for time-to-first-message, message freshness, disconnects, and reconnects. For upload/download streaming, normalize completion duration by payload size or chunk count for fair comparisons.

## 9. Accounting for retries and logical requests

One logical request can generate multiple attempts via retries. Counting only server attempts inflates request volume; counting only final client outcomes masks attempt failures.

Maintain two perspectives:

- **Client-side logical-call SLI:** one user operation, from first attempt through final outcome after retries.
- **Attempt telemetry:** attempt count, per-attempt status, backoff, and per-attempt duration.

User-facing SLOs usually track logical calls. Attempt metrics uncover retry amplification and unstable backends. If retries let a logical call succeed yet push total duration past the threshold, availability passes while the latency SLI fails.

For writes, retry only when operations are idempotent or carry an idempotency key. An attempt cut by a reset may have already committed; unprotected retries can duplicate side effects.

## 10. Instrumentation with Micrometer

You can record duration histograms by service, method, and outcome using Micrometer. The helper below is invoked when an RPC finishes:

```java
@Component
public class GrpcSloMetrics {

    private final MeterRegistry registry;

    public GrpcSloMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String service,
            String method,
            String outcome,
            Duration duration) {

        Timer timer = Timer.builder("grpc.server.call.duration")
                .tag("service", service)
                .tag("method", method)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(150),
                        Duration.ofMillis(300),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(2))
                .register(registry);

        timer.record(duration);
    }
}
```

`Timer` provides counts, total time, and histogram/percentile data depending on the registry backend. `outcome` must stay a small enum-like set such as `success`, `caller_error`, `server_error`, `unavailable`, or `cancelled`; never use exception messages as tags.

In production, prefer built-in Spring gRPC Observation/instrumentation or OpenTelemetry if already available. Avoid recording the same RPC twice across multiple interceptors with inconsistent metric names and semantics. If instrumenting manually, record exactly one terminal event and measure duration with a monotonic clock such as `System.nanoTime()`.

## 11. Consistent outcome classification

Use a shared classifier so client and server dashboards do not interpret statuses differently:

```java
public enum RpcOutcome {
    SUCCESS,
    CALLER_ERROR,
    AUTH_REJECTED,
    SERVER_ERROR,
    UNAVAILABLE,
    DEADLINE,
    CANCELLED,
    CAPACITY_REJECTED
}
```

The classifier should take the status code plus needed context such as cancellation origin, method policy, or quota decision. You cannot classify every scenario accurately from status code alone: for example, `CANCELLED` may come from caller or server; `RESOURCE_EXHAUSTED` may represent a valid quota or server capacity exhaustion.

Separate two metrics if needed:
- `grpc.server.call.outcome`: server-side processing outcome.
- `grpc.client.logical_call.outcome`: final outcome seen by the caller.

Use the exact same taxonomy and document policies so dashboards, alerts, and SLO reports align.

## 12. Alerting on error budgets and burn rate

Alerts should not rely solely on a raw absolute error threshold. With a 99.9% SLO, the allowed error ratio is 0.1%. Burn rate is calculated as:

```text
Burn rate = observed error ratio / allowed error ratio
```

If the error ratio in a recent window is 2%, burn rate = 2% / 0.1% = 20x. At that pace, the error budget drains rapidly.

Use multi-window alerting to separate major outages from brief noise:
- Short windows catch sudden outages or sharp degradation.
- Longer windows confirm sustained budget consumption.
- Alert per high-impact service/method rather than creating per-user or per-request alerts.

Latency SLOs also need alerts when the fraction of requests exceeding thresholds rises, even if availability stays green. A service returning valid responses slower than its SLA still degrades user experience.

## 13. What should an SLO dashboard display?

A well-rounded dashboard should include:

| Panel | Content |
| --- | --- |
| Availability | Good/eligible requests, error ratio, SLO target |
| Latency | Histogram, p50/p95/p99, fraction under thresholds |
| Error budget | Remaining budget, burn rate across windows |
| gRPC status | Status distribution by service/method |
| Client vs server | Logical-call latency compared with server duration |
| Retry | Attempts/logical call, retry success, backoff |
| Streaming | Time-to-first-message, inter-message gap, disconnect/reconnect |
| Dependency | Downstream latency, timeouts, and failures |
| Deployment | Version, rollout timestamps, and post-release deltas |

Display traffic volume alongside percentages. A high error rate across 5 requests means something very different from the same rate across millions of requests. For low-traffic services, external synthetic probes help detect outages between real user requests.

## 14. Testing and validating SLOs

SLOs should be verified with controlled tests:

1. Unit test the classifier for every status code and cancellation origin.
2. Integration test via generated stubs to record client logical-call duration.
3. Test server interceptors/metrics to guarantee exactly one terminal measurement per RPC.
4. Inject faults for downstream latency, connection failures, and server overload.
5. Test streaming to measure time-to-first-message and inter-message gaps.
6. Load test to verify histograms and error ratios under expected traffic.
7. Verify retries do not hide logical-call latency or create duplicate side effects.
8. Reconcile dashboard numbers against actual RPC counts and logs/traces.

Use a fake clock or clock abstraction when testing time windows/burn rates so tests do not depend on wall-clock timing. Avoid `Thread.sleep` to test histograms or alert windows whenever test fixtures can control time and events directly.

## 15. Example: building SLOs for InventoryService

Suppose `InventoryService` serves unary reads and writes. The team can define:

| Objective | Example SLO | Scope |
| --- | --- | --- |
| Availability | 99.9% of eligible logical calls over 30 days | GetStock, ReserveStock |
| Read latency | 95% of GetStock under 150 ms | Client-side logical call |
| Write latency | 95% of ReserveStock under 500 ms | Client-side logical call |
| Server capacity | Within agreed rejection threshold | RESOURCE_EXHAUSTED due to capacity |
| Streaming | Not applicable to these two unary methods | Separate SLO if a watch API is added |

`INVALID_ARGUMENT` or `NOT_FOUND` can count as served per contract without counting as business success. `UNAVAILABLE`, `INTERNAL`, and deadlines caused by slow server processing count as failures per policy. Caller cancellations are excluded from the availability denominator only when confirmed caller-initiated; cancellations from server overload are not excluded.

After a month, if availability hits 99.95% yet read latency reaches only 88% under 150 ms, the service meets its availability objective but misses its latency objective. The team needs to optimize caching, database queries/indexes, queues, or downstream calls rather than looking solely at `OK` status counts.

### Key takeaway

**SLOs are meaningful only when success, latency, and availability are defined by SLIs with clear denominators and classification rules.** Measure client logical RPCs, server processing, and downstream stages; separate server errors from caller errors, cancellations, and business outcomes; use histograms/thresholds for latency and error budgets/burn rates for alerting. For streaming, set dedicated SLOs for time-to-first-message, message gaps, and disconnects rather than mixing long stream durations into unary latency.

## References

- [Google SRE — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Google SRE — Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [gRPC — OpenTelemetry Metrics](https://grpc.io/docs/guides/opentelemetry-metrics/)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring gRPC — Observability](https://docs.spring.io/spring-grpc/reference/observability.html)
