# Principles of Observing and Verifying Distributed Behavior

> **Chapter:** Distributed Foundations  
> **Module:** SPRING_CLOUD_CORE  
> **Focus:** Detecting, explaining, and verifying the actual behavior of Spring Cloud applications when multiple services, instances, configuration sources, and networks collaborate to handle a request.

A successful call in a development environment only proves that **one single case** worked. When deploying a distributed system, outcomes can vary by instance placement, registry update timing, network latency, timeouts, configuration refresh timing, and client retry policies. Therefore, learners need two complementary capabilities:

1. **Observability:** from logs, metrics, traces, and system state, infer what happened, where, and under what conditions.
2. **Verification:** define expected behavior upfront, create controlled test conditions, collect evidence, and conclude whether the system satisfies those conditions.

This forms the foundation for studying **Spring Cloud Commons**, **Spring Cloud Context**, externalized configuration, refresh scope, discovery, service registries, load balancing, and inter-service communication in a testable way. Examples assume the project uses a **compatible Spring Boot – Spring Cloud release train – JDK** combination per the actual version documentation. Library names, instrumentation mechanisms, and observability endpoints may differ across software generations.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish observing signals, diagnosing root causes, and verifying a hypothesis.
- Follow a request across multiple services using **contextual logs**, **aggregated metrics**, and **distributed traces**.
- Define verification criteria for discovery, service registries, load balancing, externalized configuration, and refresh scope.
- Design experiments with disconnected instances, stale registry data, increased latency, timeouts, retries, and configuration changes.
- Separate observed facts from what cannot yet be concluded; avoid generalizing "always works" from a few successful calls.
- Write an incident report or test summary with verifiable evidence: conditions, actions, observations, conclusions, and limitations.

## 2. Why Are Distributed Systems Harder to Observe Than a Single Application?

Suppose a `POST /orders` request arrives at `order-service`. This service checks inventory via `inventory-service` and then calls `payment-service`. Each service may run multiple instances. One external request turns into multiple internal operations that can finish at different times.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant O as order-service
    participant D as Discovery
    participant I as inventory-service
    participant P as payment-service
    U->>O: POST /orders
    O->>D: Look up inventory-service
    D-->>O: Known instance list
    O->>I: GET /stock/{sku}
    I-->>O: In stock / Error / Timeout
    O->>P: POST /charge
    P-->>O: Result or uncertain response
    O-->>U: Aggregated result
~~~

Observability questions to answer:

- Did the request spend its time in `order-service`, in `inventory-service`, or on the network?
- Which instance did the caller pick, and from which set of instances?
- Did the client retry; if so, which attempt was this?
- Did an HTTP 500 originate from the target service, or did the caller translate another exception?
- If payment processed the charge yet the response was lost, how did the system prevent charging twice?
- From which property source and revision was configuration read, and have beans received the updated config?

**A single log line cannot answer that entire chain of questions.** Each instance has its own clock, lifecycle, and connections. An event observed late did not necessarily happen late; logs emitted out of order do not prove causal order. Context must be attached and cross-checked across multiple sources of evidence.

### 2.1. Sources of uncertainty

| Source of uncertainty | Concrete example | Impact to verify |
| --- | --- | --- |
| **Network** | Delayed packets, connection refused, TCP reset, DNS resolution failure. | Are timeouts and retries bounded? |
| **Timing** | Request arrives right before instance stops; two hosts have clock skew. | Can event ordering be concluded from timestamps alone? |
| **Discovery** | Registry still holds dead instance; discovery client caches results. | Is the client's visible instance set still valid? |
| **Load distribution** | One instance overloaded while another stays healthy. | Which target did the request pick? Is the selection policy appropriate? |
| **Configuration** | External value changed yet beans have not refreshed. | Which value was actually active at request time? |
| **Partial failure** | Inventory succeeded, payment timed out. | Is order state consistent with the transaction outcome? |
| **Missing observability** | Error logged without request ID or target instance. | Is there enough evidence to attribute the fault to the right hop? |

A properly functioning system must define how it handles uncertain cases, not only the case where every component is healthy.

## 3. Three Foundational Questions: What Happened? Why? Is It Correct?

To avoid vague interpretations, follow a structured investigation sequence:

1. **Identify the symptom:** p95 latency rises; `order-service` error rate climbs; readiness endpoint flips state.
2. **Isolate scope:** compare before/after across endpoints, deployment versions, instances, dependencies, and timestamps.
3. **Form a testable hypothesis:** "errors spiked because callers still pick stopped instance `inventory-2`."
4. **Choose measurements and experiments:** inspect `ServiceInstance` lists, target instances in logs, and traces of failing requests; isolate or stop an instance in a test environment.
5. **Verify:** compare observations against predefined criteria; if evidence contradicts the hypothesis, revise it.
6. **State a bounded conclusion:** "under this configuration and test window, once cache refresh elapsed, zero requests targeted the stopped instance"; do not claim every system or scenario shares the same delay.

Distinguish three kinds of information:

- **Signal:** "12 requests returned HTTP 503 within 1 minute."
- **Hypothesis:** "Slow registry updates caused the load balancer to keep using a stale endpoint."
- **Verification evidence:** "Traces show those 12 requests picked instance X, while instance X's logs show it stopped earlier and lookups still returned X until timestamp Y."

With signals alone, you cannot yet conclude the root cause.

## 4. Four Signal Groups to Collect

### 4.1. Logs: individual events with context

Logs should tell **who** acted, **what** happened, **when**, **with what outcome**, and **for which request**. Prefer structured logs with typical fields:

| Field | Meaning | Note |
| --- | --- | --- |
| `timestamp` | Instant the event occurred. | Standardize on UTC and format; watch for clock skew. |
| `service` / `instance` | Application name and instance identifier. | Needed to distinguish multiple replicas of the same service. |
| `traceId` / `spanId` | Links event to a distributed trace. | Present only if instrumentation/tracing is enabled and context propagates properly. |
| `requestId` | Request identifier at business or ingress level. | Useful backup when traces are sampled out or context propagation breaks. |
| `operation` / `dependency` | Operation name and downstream service. | E.g., `inventory.lookup`, `inventory-service`. |
| `targetInstance` | Address or ID of selected instance. | Helpful for inspecting discovery and load balancing. |
| `status` / `errorType` / `durationMs` | Outcome, error category, and duration. | Never log just a generic `"request failed"` string. |
| `configRevision` | Non-sensitive configuration version. | Enables before/after comparison across refreshes/deploys. |

Two **illustrative** log entries (not Spring Boot's default format):

~~~json
{"timestamp":"2026-01-01T10:00:00Z","service":"order-service","instance":"order-1","traceId":"trace-a1","spanId":"span-o1","operation":"inventory.lookup","targetInstance":"inventory-2","attempt":1,"status":"TIMEOUT","durationMs":800}
{"timestamp":"2026-01-01T10:00:01Z","service":"order-service","instance":"order-1","traceId":"trace-a1","spanId":"span-o2","operation":"inventory.lookup","targetInstance":"inventory-1","attempt":2,"status":"OK","durationMs":42}
~~~

From this example you can infer the application logged **two attempts** in the same trace and picked **two different instances**. From these logs alone you cannot infer why the first attempt timed out, whether the retry was safe, or whether the final business outcome was correct.

Never write passwords, API keys, access tokens, full sensitive payloads, or personal identifiers into logs solely for diagnostics. For very high-cardinality IDs, be careful not to promote them into metric labels.

### 4.2. Metrics: observing trends and blast radius

Metrics aggregate numerous observations into time-series numbers. They help answer: how many requests, how many errors, what latency distribution, and whether system pressure is rising or falling.

Core measurements:

| Metric category | Question | Example insight |
| --- | --- | --- |
| **Request rate** | How many requests per second/minute arrive? | Distinguishes traffic spikes from incidents under steady load. |
| **Error rate** | What is the failure proportion? | Separate client 4xx from 5xx and network errors depending on SLO goals. |
| **Latency** | What do p50/p95/p99 or histograms look like? | Averages can hide a slow tail affecting a subset of requests. |
| **Saturation** | Are connection pools, threads, CPU, or queues near limits? | Detects congestion before error rates climb. |
| **Dependency health** | How many calls to inventory/payment fail? | Separates internal bugs from downstream failures. |
| **Discovery/instance state** | How many instances are visible, and how long are lookups empty? | Spots divergence between registry state and reality. |

A practical lens is **RED** (Rate, Errors, Duration) for request-handling services and **USE** (Utilization, Saturation, Errors) for resources. These are operational views and do not replace business correctness checks.

Example SLO defined by a team for a **lab exercise**:

- Over a predefined observation window, ≥ 99.5% of valid `GET /orders/{id}` requests succeed.
- p95 latency for valid requests stays below 300 ms at the specified test load.
- Dependency failures must not hang requests indefinitely; every outbound call must have a timeout.

Do not treat the thresholds above as Spring Cloud defaults or universal production standards. Proper thresholds depend on each system's requirements and workload.

**Note on labels:** low-cardinality labels like `service`, `route`, and `outcome` aggregate cleanly. Never use `traceId`, emails, order IDs, or raw URLs containing IDs as metric labels, as they cause massive cardinality explosion.

### 4.3. Traces: the path of a single request

A distributed trace models a sequence of operations (**spans**) linked via parent/child or other appropriate relationships. Each span captures duration, operation name, service context, and attributes.

Illustrative example:

~~~text
trace: T-481
  POST /orders                          order-service    1040 ms
    inventory.lookup                    order-service     830 ms
      GET /stock/{sku}                  inventory-service  820 ms
    payment.charge                      order-service     150 ms
      POST /charge                      payment-service    145 ms
~~~

Traces pinpoint which segment consumed the most time; cross-reference logs/metrics to explain why that span was slow. Trace trees do not automatically cover async tasks, message queues, or uninstrumented systems.

**Context propagation** is essential: trace correlation headers must travel across HTTP/messaging via an appropriate tracing mechanism, commonly W3C Trace Context (`traceparent`, `tracestate`). Custom-created clients or off-thread work that omit context propagation can break traces.

Clocks can skew across machines; prefer span parent/child relationships and local duration timers over inferring causality purely from absolute timestamps. Sampling saves cost, meaning not every request gets a full trace. A missing trace does not prove a request never occurred.

### 4.4. Application and infrastructure state

Beyond logs, metrics, and traces, inspect state signals:

- **Liveness:** is the process still alive per probe definitions?
- **Readiness:** is the instance ready to accept requests per application and deployment definitions?
- **Registry/discovery:** is the instance published and visible to clients?
- **Deployment:** version, rollout timestamp, restart count, and resource fluctuations.
- **Configuration:** config source, active profiles, applied config revision.

**Healthy**, **ready**, and **registered** are distinct concepts. An instance can be alive yet not ready; a registry can still hold a stale address; a load balancer can see unrefreshed discovery data. Never conclude "the service is healthy" from a single endpoint.

## 5. Invariants to Verify: Don't Look Only at HTTP 200

In distributed systems, key requirements are often **business invariants** or **system properties** that hold even under partial failure.

| Requirement type | Verifiable phrasing | Evidence to collect |
| --- | --- | --- |
| **Safety** | One transaction idempotency key never creates two valid payment charges. | Transaction decision log, persisted state, and record counts. |
| **Liveness (progress)** | Once the dependency recovers and fairness assumptions hold, new requests can succeed again. | Repeated call results over a defined window. |
| **Time bounds** | Dependency calls do not exceed configured timeout plus acceptable overhead. | Duration metrics and traces, client configuration. |
| **Consistency** | Order and payment states satisfy business state-transition rules. | Database state checks and related events. |
| **Fault tolerance** | When one inventory instance dies, the system does not remain permanently stuck on that address. | Lookups over time, chosen-instance logs, error recovery rate. |
| **Adequate observability** | A failing request can be traced to the offending service and dependency in an instrumented environment. | Trace ID, target instance, error category. |

**Safety** states what must never happen. **Liveness** states what good outcome eventually happens **under explicit assumptions**, such as the dependency recovering and the system still having capacity. Testing a finite number of cases is not a formal proof across all interleavings, network faults, or partitions.

### 5.1. Define the unit of observation

Error rates can be computed per:

- **Client request:** one user action, which may involve multiple dependency calls.
- **Dependency attempt:** each outbound call, including retries.
- **Business transaction:** one order/payment spanning multiple requests.

Example: 100 user requests, where 20 require one retry; 120 total dependency attempts. If 20 initial attempts fail yet all 100 user requests ultimately succeed, the **attempt error rate** is 20/120 while the **user-visible error rate** is 0/100. Both are useful, yet answer different questions. Always state the denominator when reporting.

## 6. Observing Each Spring Cloud Abstraction Properly

### 6.1. Spring Cloud Commons: discovery and load balancing

Spring Cloud Commons provides contracts such as `DiscoveryClient`, `ServiceInstance`, and `ServiceRegistry`. Instance sources may be registries like Eureka/Consul, static configuration, or environment-specific implementations. Spring Cloud LoadBalancer can use the instance list to pick an actual target.

Collect these separately:

1. **Lookup result:** service ID, returned instance count, timestamp, and discovery source.
2. **Selection decision:** chosen instance ID/host/port for the request.
3. **Connection outcome:** whether connection succeeded, HTTP status, timeout, and duration.
4. **Registry and instance status:** instance start/stop times, and whether registration remains valid.

| Symptom | Distinct hypotheses to separate |
| --- | --- |
| `getInstances("inventory-service")` returns empty. | Wrong service ID, discovery not ready, not registered, registry disconnect, instance filtering policy. |
| Instance present, connection refused. | Process stopped, wrong port, network policy blocking, stale metadata/registry. |
| Instance present, HTTP 503. | Instance/app rejecting requests, proxy returning error, or internal dependency failing. |
| Requests hit only one instance. | Are multiple instances actually discovered? Does the algorithm fit? Too few test requests? Caching or external routing? |
| Instance died, client still calls it. | Registry lag, discovery cache, load balancer cache, unsynchronized shutdown/health states. |

Do not assume every provider immediately evicts a stopped instance from lookup results. Also do not assume load balancing is always round-robin or yields a perfect split across a tiny sample size.

**Verification test:** run two instances of `inventory-service` returning an `instanceId` field in responses; record the URI set returned by the discovery client and the actual URI picked per call. Stop one instance; measure **when errors start**, **time until lookup stops returning that instance**, and **time until the client stops picking it**. Those three timestamps may differ.

### 6.2. Spring Cloud Context: externalized configuration and refresh scope

Spring Boot externalized configuration can come from `application.yml`, profiles, environment variables, launch arguments, and other integrations. Spring Cloud Context provides configuration and context mechanisms, including refresh scope when appropriately triggered. Editing a file does not automatically guarantee running beans receive the new value.

To verify refresh, separate four steps:

1. **Source changed:** external file or config source actually holds the new value.
2. **Environment updated:** new value is loaded into the application's property sources.
3. **Scope/bean updated:** `@RefreshScope` bean is invalidated and recreated upon proxy access.
4. **Request behavior:** requests to **that specific instance** reflect the new behavior.

Illustrative property example:

~~~yaml
app:
  feature:
    mode: standard
~~~

Suppose a bean reads `app.feature.mode` at initialization. Experiment: record mode before change; update to `safe` in the config source; trigger the supported refresh workflow; inspect each instance's environment and responses. If instance A receives `safe` while instance B keeps `standard`, that **cross-instance configuration skew** must be recorded and handled per system requirements.

Do not assume refresh propagates to **every** instance, every bean, or every config source. Do not assume a refresh endpoint exists, is exposed, or is safe to call externally. Verify dependencies, procedures, and access controls for your specific version.

### 6.3. Inter-service communication: timeouts, retries, and uncertain responses

From the client's perspective, outcomes typically fall into:

- **HTTP response received:** status and payload present; success/failure follows the business contract.
- **Timeout:** wait duration exceeded; uncertain whether the target service processed the request.
- **Connection refused/reset:** communication failed to complete; server execution progress depends on when the drop occurred.
- **Target unresolvable:** discovery/DNS/client config did not yield a usable endpoint.

Crucially, **a timeout does not prove the operation did not execute**. If a client calls `POST /charge` and times out, automatic retry without an idempotency key can double-charge. For side-effecting operations, design idempotency keys, persist execution state, and verify status before retrying per business rules.

**Rule for verifying retries:** record `requestId` or idempotency key, attempt number, target instance, retry reason, and final outcome. Post-retry success rate alone does not prove safety.

## 7. Setting Up Minimal Observability in Spring Boot / Spring Cloud

### 7.1. Define instrumentation before running tests

In a mini-system with `order-service` and `inventory-service`, first choose:

- **Logs:** service, instance, request ID, trace ID (if available), operation, target, duration, outcome.
- **Metrics:** request count, error count, latency histogram/timer, active requests, and useful resource metrics.
- **Traces:** a trace spanning HTTP client and HTTP server, with spans for dependency calls.
- **State:** health/liveness/readiness when configured, plus the instance list returned by discovery.

These signals can be collected with Spring Boot Actuator, Micrometer, and matching logging/tracing/metrics stacks. **Which dependencies are needed, which property names apply, and whether auto-instrumentation takes effect** must be checked in documentation for your chosen Boot/Cloud release; adding a BOM alone does not enable telemetry.

Partial Actuator config example for a **lab** (requires matching starters and registry/exporter as needed):

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      probes:
        enabled: true
~~~

On supported Spring Boot versions, this config enables corresponding installed Actuator endpoints; **do not assume every environment or deployment exposes the exact same endpoints and outputs**. To use a Prometheus endpoint, include the appropriate registry and explicitly expose `prometheus`. In production, restrict network access, authorization, and exposed details.

Local inspection:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/metrics
~~~

If commands do not return expected output, inspect Actuator dependencies, management port, health probe config, security, exposure settings, and Spring Boot version. Never relax security arbitrarily just to make a demo command work.

### 7.2. Propagating context across services

To trace across services, use an HTTP client participating in framework-supported instrumentation (such as a Spring-managed builder/client for your version), then confirm trace headers propagate and the receiver creates linked spans. For async processing or custom unmanaged clients, verify context propagation explicitly.

Verification checklist:

1. Issue a request with a known ID from the client.
2. Locate logs on both receiver and caller; verify matching trace or request ID.
3. Confirm the trace shows matching outbound/inbound spans.
4. Intentionally trigger a call timeout and verify dependency name, error type, duration, and attempt count appear clearly enough to diagnose.
5. Under low sampling rates, fall back to request IDs in logs when traces are unsampled; do not mistake an unsampled trace for a lost request.

In labs you can raise sampling for learning, while keeping export overhead and data volume in mind; never use 100% sampling as a default for high-traffic production systems.

### 7.3. Timestamps and clock synchronization

Standardize timestamps in UTC and use synchronized system clocks. For durations, prefer in-process timers/clocks. Never measure end-to-end latency by subtracting timestamps from two different machines without accounting for clock skew. Span parent/child links and request IDs aid reasoning, though they cannot replace causal modeling when async tasks or message brokers are involved.

## 8. Designing Repeatable Experiments

Every experiment should have a **verification contract** before starting:

| Component | Question to answer |
| --- | --- |
| **Hypothesis** | What is the system expected to do when a specific fault occurs? |
| **Setup** | What are the versions, topology, instance counts, registry, timeouts, retries, profiles, and load? |
| **Stimulus** | Stop process, inject delay, change config, block network, or return HTTP 500? |
| **Timeline** | What initial state, when is the fault injected, how long do we observe? |
| **Oracle (pass/fail criteria)** | What conditions mark PASS vs. FAIL? |
| **Collected signals** | Which logs, metrics, traces, business states, and config snapshots? |
| **Recovery** | How is the system restored to baseline afterward? |
| **Limitations** | How many runs; which fault types can this environment simulate? |

**Example contract:** "When one of two inventory instances stops, once discovery/convergence settles, new requests can use the surviving instance; transitional errors are logged, and no request hangs beyond the configured timeout." Define **convergence wait windows** and **timeouts** via configuration or test criteria—avoid saying "immediately" without measuring.

### 8.1. Practical test pyramid

| Test level | Method | Good for proving | Limitations |
| --- | --- | --- | --- |
| **Unit** | Mock dependencies, fake clocks, test retry/fallback/idempotency rules. | Code decisions for specific inputs. | Does not prove networking, auto-configuration, or real discovery. |
| **Component/Spring integration** | Boot context, test config binding, stub HTTP servers or `DiscoveryClient`. | Wiring, property precedence, HTTP error mapping, partial instrumentation. | Cannot fully represent production topology. |
| **Multi-instance integration** | Run order + 2 inventory instances with static discovery or test registry. | Instance selection, propagation, behavior when an instance dies. | Depends on runtime and test setup. |
| **Controlled failure/chaos test** | Inject latency, drop/reset connections, kill instances, pause registry. | Partial-failure detection and recovery mechanics. | Cannot cover every fault combination; needs a safe environment. |
| **Operational validation** | Inspect dashboards, alerts, traces, health, simulated incident reports. | System yields enough data to diagnose and respond. | Complete telemetry alone does not prove business correctness. |

Prefer automated verification assertions. For stable tests, use fake servers/clocks, latches, deadline-bounded polling, or controlled fault injection; avoid asserting exact timings like "after `Thread.sleep(1000)` the instance must be evicted" because caches, schedulers, and infrastructure fluctuate.

### 8.2. Minimum scenario matrix

| ID | Injected scenario | Signals to observe | Verification criterion |
| --- | --- | --- | --- |
| D1 | Discovery returns 0 instances. | Lookup count = 0; target-resolution error. | Client returns defined error and sends no HTTP request to any URI. |
| D2 | Discovery returns 2 healthy instances. | Target instance in logs/traces; successful call count. | Requests reach valid instances; do not assume 50/50 split over a few calls. |
| D3 | Stop a published instance. | Stop timestamp, lookup results, chosen target, connection error. | Captures stale-discovery window and confirms post-convergence state. |
| N1 | Inject network latency. | p95/p99 rises, dependency trace span lengthens. | Timeout cuts off request per policy; error is classified accurately. |
| N2 | Target returns HTTP 500. | HTTP status, upstream service, error rate. | Client handles error per contract; retries only if policy permits. |
| N3 | Response lost after target processed request. | Request ID and business state on target. | No duplicate side effects when client chooses to retry. |
| C1 | Config changed without refresh/restart. | Config revision, bean output. | Explains why the old value can remain active. |
| C2 | Proper refresh on one instance. | Before/after revision and response on that instance. | Appropriately scoped beans reflect the new value post-refresh per contract. |
| C3 | Refresh on only one of two instances. | Per-instance config revision. | Divergence is observed when rollout/refresh is not coordinated. |
| O1 | Tracing breaks between two services. | Split spans or mismatched trace IDs. | Pinpoints where propagation broke; logs/request IDs still aid investigation. |

**Every scenario requires at least one behavioral assertion and one piece of observability evidence.** Verifying only "logs exist" does not prove the system behaves properly; verifying only HTTP 200 does not prove the system is observable.

## 9. Hands-On Example: Tracking a Dead Instance and Request Recovery

### 9.1. Lab setup

Use three processes:

- `order-service`: port `8080`, calls `inventory-service` by service ID.
- `inventory-a`: port `8081`, returns JSON including `instanceId: "a"`.
- `inventory-b`: port `8082`, returns JSON including `instanceId: "b"`.

In the initial lab, use `SimpleDiscoveryClient` to simulate the instance set for the service ID:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

**Note:** with **static** configuration, stopping an instance **does not automatically update** the URI list because there is no dynamic registry updating it. This experiment therefore tests connection-failure handling and the limits of static discovery. If your goal is **measuring registration/deregistration convergence**, use a dynamic registry/discovery implementation. Report the two experiments separately.

With Spring Cloud LoadBalancer integrated into an appropriate HTTP client, `order-service` can call a logical URL like:

~~~text
http://inventory-service/api/stock/ABC-123
~~~

For the sample code to work, use an actually load-balanced client and include the matching dependencies; a plain HTTP client **does not automatically understand** the `inventory-service` service ID.

### 9.2. Step-by-step experiment

1. Start all three processes; record JDK, Spring Boot, Spring Cloud release train, discovery/load-balancer dependencies, and active timeouts.
2. Call the order endpoint multiple times; confirm success. Capture `traceId` or `requestId`, target instance, duration, and response.
3. Record the URI list returned by `DiscoveryClient` as a baseline.
4. Stop `inventory-b` by intentionally terminating its process.
5. Continue calling at a **defined rate**; record request counts, errors, timeouts, and selected instances.
6. Compare order logs with `inventory-b` process state. With static simple discovery, the list is expected to retain the old URI; do not mistake this for a dynamic registry bug.
7. Restart `inventory-b`; rerun calls and verify connection recovery.
8. If switching to a dynamic registry, repeat and separately measure instance removal/return timestamps in the registry, discovery cache, and target selection.

A **sample** results log template to fill in during execution:

| Milestone | Discovery sees | Target selected | HTTP outcome | Notes |
| --- | --- | --- | --- | --- |
| Baseline | A, B | A | 200 | Both processes running |
| After stopping B | A, B (static simple) | B | Connection error/timeout | Static list still contains B |
| Subsequent call | A, B (static simple) | A | 200 | Success does not prove B was evicted |
| After restarting B | A, B | B | 200 | Recovery check |

Target and outcome values in the table are **illustrative**, not a guarantee that the algorithm or run will match row-for-row in live execution.

### 9.3. How to write an appropriately scoped conclusion

Appropriate conclusion:

> "In the lab using SimpleDiscoveryClient, stopping instance B does not automatically update the static instance list. Some requests routed to B fail; requests routed to A can still succeed. We distinguished connection errors from service-lookup failures."

Conclusions you **must not** draw from the lab above: "Spring Cloud registries automatically evict dead instances within X seconds" or "the load balancer will definitely shift all requests to A."

## 10. Coded Verification Example: Application-Layer Rules

Use unit tests to verify decisions before running integration tests. Business logic should be decoupled from HTTP clients and registries for clean testing.

Suppose `InventoryGateway` is an application-defined interface:

~~~java
public interface InventoryGateway {
    StockResult lookup(String sku);
}

public record StockResult(String sku, int available) {}
~~~

A service that disallows placing an order when the gateway reports insufficient stock:

~~~java
public class OrderDecisionService {
    private final InventoryGateway inventory;

    public OrderDecisionService(InventoryGateway inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String sku, int requestedQuantity) {
        if (requestedQuantity <= 0) {
            return false;
        }
        StockResult stock = inventory.lookup(sku);
        return stock.available() >= requestedQuantity;
    }
}
~~~

JUnit 5 test with a simple fake gateway, needing no Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class OrderDecisionServiceTest {
    @Test
    void acceptsOrderOnlyWhenStockIsSufficient() {
        InventoryGateway fake = sku -> new StockResult(sku, 3);
        OrderDecisionService service = new OrderDecisionService(fake);

        assertTrue(service.canPlaceOrder("SKU-1", 2));
        assertFalse(service.canPlaceOrder("SKU-1", 4));
        assertFalse(service.canPlaceOrder("SKU-1", 0));
    }
}
~~~

This test verifies **the stock-quantity rule**. It **does not verify discovery, HTTP, timeouts, retries, telemetry, or network fault tolerance**. Those require separate integration/component tests:

- Stub discovery returning 0, 1, or multiple `ServiceInstance`s.
- Make a stub HTTP server return 200/500 or delayed responses.
- Verify retry and timeout policies with explicit attempt counts.
- For non-idempotent operations, inspect target-side state to confirm no duplicate side effects.
- Verify instrumentation emits spans and contextual logs if that is a quality criterion of the test.

As test levels increase, keep scenario names and outcome definitions consistent so results compare cleanly across unit, integration, and multi-instance runs.

## 11. Monitoring, Alerting, and Incident Investigation

Observability pays off only when it helps **detect incidents** and **decide the next action**. A basic dashboard should show:

1. Traffic, success/error rates, and latency by key endpoint.
2. Latency and error rates by dependency.
3. Timeout/connection-error rates and total attempts including retries.
4. Instances seen by discovery versus deployment/health status when available.
5. Application version changes, config changes, and restart/rollout events.

When building alerts, prioritize user-facing symptoms and real SLOs. For example, **error budget burn** or sustained error-rate spikes over an adequate window are usually more meaningful than a single isolated failure. Separate synthetic test/health probe errors from user traffic if they skew measurements.

### Workflow for investigating an intermittent error

- **Step 1:** check the time window and confirm real errors, request volume, and error rate.
- **Step 2:** pull specific requests by trace ID or request ID; compare successful and failing requests on the same endpoint.
- **Step 3:** inspect target instance, dependency span duration, status/exception, and attempt count.
- **Step 4:** inspect discovery, process/health, registry/cache, deployments, and config revisions at the same timestamp.
- **Step 5:** reproduce in a controlled environment changing one variable at a time.
- **Step 6:** document evidence-backed root cause, impact, fix, regression test, and detection signal for next time.

Seeing HTTP 503 only at the gateway is no reason to jump to blaming inventory: 503 could come from the gateway, load balancer, discovery, or an intermediate proxy layer.

## 12. Common Misconceptions and Practical Pitfalls

| Misconception | What to re-verify |
| --- | --- |
| "HTTP 200 means the whole business chain succeeded." | Side effects, final persisted state, async tasks, and business invariants. |
| "Having logs means observability is sufficient." | Do logs include correlation/targets, do metrics show impact, and do traces cross services? |
| "Having a `traceId` means the trace is complete." | Missing spans due to instrumentation gaps, async calls, sampling, or context propagation. |
| "Health UP guarantees traffic can be handled." | Readiness, registry membership, and dependency health. |
| "Timeout means the server didn't process it." | Server committed while response was lost; idempotency and reconciliation. |
| "More retries always means safer." | Retry amplification, attempt limits, backoff, deadlines, and business safety. |
| "Registry returning an instance means it is alive." | Caches, heartbeats, update lag, actual connectivity/health. |
| "Editing a config file makes beans pick it up immediately." | Property source reload, `@RefreshScope`, which instance refreshed, bean recreation timing. |
| "One passing test proves the system is fault-tolerant." | Sample size, load rate, fault types, topology, and environment assumptions. |
| "Putting trace IDs in metric labels makes debugging easier." | High cardinality; use exemplars/log/trace linking if your observability stack supports them. |

## 13. Capstone Exercise: Building an Evidence Dossier

For the `order-service` and `inventory-service` mini-system, assemble a **verification dossier** with the following parts.

### A. Diagram and baseline state

Record topology, versions, instance counts, discovery configuration, endpoints, and timeouts/retries. List installed observability components: Actuator, logging, metrics, tracing. Note where telemetry is not yet enabled and the resulting limitations.

### B. Three hypotheses to test

1. **Discovery:** "when the instance list is empty, the caller returns a controlled error without calling an invalid URI."
2. **Network:** "when a dependency is slower than the timeout, the caller terminates the request per policy and logs sufficient context."
3. **Config:** "after a supported refresh on instance A, appropriately scoped beans return the new config value; instance B does not automatically adopt the same revision unless updated."

You may add a registry convergence hypothesis, provided the lab uses a dynamic registry.

### C. Experiment results

For each hypothesis, record:

~~~text
Scenario ID:
Versions: JDK / Spring Boot / Spring Cloud release train
Topology: service + instance + ports + discovery provider
Baseline: metric / health / config revision
Stimulus: timestamp, how fault or change was induced
Expected: one measurable behavioral assertion
Observed: request count, outcome, latency, instance, duration
Evidence: log correlation ID, trace ID, metric window, test assertion
Result: PASS / FAIL / INCONCLUSIVE
Limitations: unmeasured aspects, cache/sampling/clock skew, environment scope
Cleanup: post-recovery state
~~~

Use **INCONCLUSIVE** when measurements cannot distinguish among hypotheses; never force a PASS simply because no errors were seen.

### D. Completion rubric

- [ ] Can explain the roles of logs, metrics, traces, and health/readiness in investigations.
- [ ] Request ID or trace ID links key events, with documented sampling/propagation limits.
- [ ] Captured `ServiceInstance` lists and actual call target instances.
- [ ] Distinguished discovery errors, connection errors, timeouts, and HTTP error responses.
- [ ] Reproduced at least one partial-failure scenario with clear expected/observed results.
- [ ] Verified when configuration took effect before/after refresh on each relevant instance.
- [ ] Separated per-user-request metrics from per-attempt metrics when retries are enabled.
- [ ] Included business assertions, not merely HTTP status or log-existence checks.
- [ ] Documented experiment limitations and repeatability without claiming beyond the evidence.
- [ ] Restricted access to observability endpoints/telemetry and prevented sensitive data leaks.

## 14. When to Move to the Next Topic?

You are ready to dive into specific technologies—registry providers, Spring Cloud LoadBalancer, Spring Cloud Config, resilience libraries, or tracing backends—once you can answer four questions about any inter-service request:

1. **Where did it go?** Service ID, known instance list, chosen instance, and request path.
2. **What happened?** Response/status, duration, errors, retries, and business state.
3. **Why trust this conclusion?** Logs, metrics, traces, source state, and controlled verification tests.
4. **What are the evidence limits?** Sampling, caching, clock skew, test scale, versions, and untested failure modes.

**Implementation references:** Official Spring Boot guides on Actuator, Micrometer/Observability, and externalized configuration; Spring Cloud Commons, Context, LoadBalancer, and service discovery guides for your **active release train**; and documentation for your chosen registry, HTTP client, and telemetry backend. Always verify exact API names and property keys against your actual version set before promoting conceptual examples to production configuration.
