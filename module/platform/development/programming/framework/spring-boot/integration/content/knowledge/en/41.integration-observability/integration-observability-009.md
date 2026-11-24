# Health Indicators and the Meaning of Dependency Unavailability in Spring Boot

A Spring Boot service can have a healthy JVM, accept HTTP requests, and serve `/actuator/health`, yet **fail to complete business operations** because PostgreSQL, Redis, RabbitMQ, or a partner API lost connectivity. Conversely, losing an external dependency does not mean the entire application should restart: if the outage sits in an external system, mass-restarting pods will not fix the root cause and will actually amplify load.

Within the **Integration Observability** chapter of **SPRING_BOOT_INTEGRATION**, this lesson focuses on **`HealthIndicator`**, **`ReactiveHealthIndicator`**, Spring Boot Actuator health groups, and how to interpret dependency unavailability. This ties directly into integrations via HTTP clients, databases, caches, message brokers, and Spring Integration adapters; proper health decisions must account for business contracts, transactions, retries, deduplication, testing, and operational signals.

**Core message:** *Liveness* asks "can the process still make forward progress on its own?", *readiness* asks "should this instance receive **new traffic**?", and *dependency health* provides a dedicated signal about a component. **Do not collapse all three questions into one boolean** and feed the same answer into restarts, routing, and alerting.

Examples target Spring Boot 3.x, Spring Framework 6.x, Java 17+, and Actuator. Property names and integration capabilities can vary across Boot releases or starters; always verify your version and live application behavior before deploying.

## 1. Context: What Does "Dependency Unavailable" Mean?

Suppose `checkout-service` exposes these paths:

- `POST /orders`: writes the order to PostgreSQL and emits an outbox event for RabbitMQ.
- `GET /catalog`: reads from Redis cache, with fallback to the database.
- `GET /shipping/quote`: calls a shipping partner's REST API; can temporarily display "quote unavailable".
- `@RabbitListener` worker: consumes `PaymentCaptured` and updates the database.
- Spring Integration flow: receives messages via an HTTP adapter, transforms them, and forwards to another system.

If RabbitMQ is interrupted for 60 seconds, **the order-creation API can keep accepting requests** while the SQL outbox stays healthy and the relay waits for broker recovery. However, if `POST /orders` must publish synchronously **before returning success**, that capability may be unavailable. Likewise, a Redis outage does not break `GET /catalog` if database fallback is designed and the database has spare capacity.

~~~mermaid
flowchart TD
    APP["checkout-service / Spring Boot"] --> DB[("PostgreSQL")]
    APP --> REDIS[("Redis cache")]
    APP --> PARTNER["Shipping HTTP API"]
    APP --> OUTBOX[("SQL outbox")]
    OUTBOX --> RELAY["Outbox relay"]
    RELAY --> MQ[("RabbitMQ")]
    APP --> L["HTTP liveness/readiness probes"]
    L --> POLICY{"Traffic acceptance policy"}
    POLICY -->|Ready| YES["Accept new requests"]
    POLICY -->|Not ready| NO["Stop routing traffic to instance"]
~~~

**"Dependency unavailable" is an observed event**, not yet an operational command. Ask at least: which dependency, which business capabilities are impacted, whether fallback exists, how long it lasts, whether other instances are healthy, and whether pulling pods from the load balancer actually helps.

### Health Does Not Equal Business Correctness

A passing `SELECT 1` proves the database can answer a trivial query. It **does not** prove migrations ran cleanly, business table write permissions exist, deadlocks are absent, data is consistent, or the outbox relay is keeping up.

A TCP connection to RabbitMQ proves connectivity under test conditions. It **does not** prove queues are bound properly, consumers are ACKing messages, DLQs are flat, or events were processed effectively once.

Therefore, health indicators belong alongside metrics, tracing, logs, and business contract tests—never as replacements for them.

## 2. Three Distinct Signals: Liveness, Readiness, and Dependency Health

| Signal | Question | What should happen on failure? | Examples |
| --- | --- | --- | --- |
| **Liveness** | Can the process still make progress, or is it internally broken beyond self-recovery? | Orchestrator **may restart** the instance | Unrecoverable internal deadlock, application liveness state |
| **Readiness** | Should the instance accept new traffic **right now**? | Orchestrator **removes from routing** until recovered | Still warming up, graceful shutdown in progress, essential local resource unusable |
| **Dependency health** | Does a target DB/cache/broker/API pass a specific check? | Alerting, fallback, circuit breaker, or readiness impact per policy | `db=UP`, `partnerApi=DOWN`, `rabbit=UP` |

Spring Boot Actuator provides an aggregated health endpoint and **health groups**. In Kubernetes environments or when probe properties are enabled, Boot supports default groups such as `liveness` and `readiness`, backed by `livenessState` and `readinessState` indicators.

Common endpoints:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Illustrative aggregated JSON:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": { "status": "UP" },
    "shippingPartner": { "status": "DOWN" }
  }
}
~~~

**Note:** whether `components` and `details` appear depends on `show-components`, `show-details`, and authorization; never expose topology or exceptions publicly by default. This JSON illustrates an authorized view, not the default response contract in every environment.

### Difference Between Readiness `DOWN` and Liveness `DOWN`

~~~mermaid
flowchart LR
    A["External API returns 503"] --> B["Dependency indicator can be DOWN"]
    B --> C{"Dependency required to accept traffic?"}
    C -->|Yes| D["Readiness can be DOWN"]
    C -->|No / fallback| E["Readiness stays UP"]
    A --> F["Liveness stays UP if JVM/process is healthy"]
    D --> G["Kubernetes stops routing to pod"]
    F --> H["Do not restart just because external API failed"]
~~~

**Do not include external dependency health checks in liveness** by default. When all pods depend on the same failing Redis or external API, marking liveness `DOWN` causes Kubernetes to restart every pod, causing connection storms, losing warm caches, and delaying recovery.

## 3. Application Availability Lifecycle and Kubernetes Probes

Spring Boot manages `ApplicationAvailability` with two key state models:

- `LivenessState`: typically `CORRECT` or `BROKEN`.
- `ReadinessState`: typically `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`.

During startup, the application is not yet ready for traffic; once startup succeeds, readiness transitions to accepting traffic. During graceful shutdown, readiness can shift to refusing traffic before resources shut down. Transitions are tied to Boot lifecycle events; developers do not manually flip state on every failed request.

In Kubernetes:

- **Startup probe**: gives slow-starting applications extra time. Until the startup probe succeeds, Kubernetes holds off normal liveness/readiness checks.
- **Liveness probe**: exceeding failure thresholds allows kubelet to restart the container.
- **Readiness probe**: on failure, the pod is removed from ready endpoints of its Service; containers **do not automatically restart solely because readiness failed**.

Illustrative manifest snippet when probe paths run on application port `8080`:

~~~yaml
containers:
  - name: checkout-service
    image: registry.example/checkout-service:version
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
~~~

Numbers are illustrative: startup allows up to roughly 150 seconds, liveness requires 3 scheduled failures, and readiness requires 2 scheduled failures. Real timing depends on schedulers, request timeouts, and the environment. Pick thresholds from startup p99, GC pauses, system latency, and SLAs—never copy numbers blindly across services.

**Do not conflate meanings:** readiness failure means changing routing, not "please restart"; liveness failure can trigger restarts, not "a partner temporarily returned 503".

## 4. Spring Boot Actuator: Enabling Endpoints and Health Groups Properly

Add Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Example `application.yml` for a web application:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,shippingPartner
      show-details: never
      show-components: never
~~~

Key settings explained:

1. `probes.enabled: true` enables probe endpoints even outside a Boot-detected Kubernetes environment.
2. `add-additional-paths: true` exposes probe endpoints on the **main application port** under default paths `/livez` and `/readyz` in supported servlet/reactive web servers. Useful when Actuator runs on a separate management port.
3. The **default** readiness group typically includes `readinessState` and **does not automatically aggregate all dependency indicators**. `include: readinessState,shippingPartner` is an explicit choice that the shipping partner contributes to readiness. If no bean yields contributor ID `shippingPartner`, group initialization/membership validation can fail.
4. `show-details: never` and `show-components: never` protect endpoint security by hiding internal details. A separate restricted management group can be configured for authorized operators if details are needed.
5. When the API does not strictly require the shipping partner to serve remaining endpoints, **do not** include `shippingPartner` in shared readiness; see Section 6.

This configuration illustrates **readiness strictly depending on the shipping partner**, not a universal recommendation for every system. Subsequent sections show when dependencies should only trigger alerts.

### Separate Actuator Port and False Conclusions

If configured with:

~~~yaml
management:
  server:
    port: 8081
~~~

`/actuator/health/readiness` may succeed on port `8081` while application port `8080` cannot accept HTTP requests due to a blocked event loop or servlet connector failure. A healthy probe on the **management port** does not confirm the app is actually serving traffic on the **application port**.

When probes must validate the traffic-serving path, enable `management.endpoint.health.probes.add-additional-paths=true` and point probes to `/livez` and `/readyz` on the application port if supported. Test real HTTP calls over the same network path as ingress/Service traffic.

Never expose detailed health endpoints leaking exceptions, internal URLs, pool names, connection strings, or tenant states to the public Internet. Health endpoints for orchestration and observability must be protected by network controls and RBAC.

## 5. How Does `HealthIndicator` Work?

`HealthIndicator` is Spring Boot Actuator's synchronous SPI. It is typically registered as a Spring bean and returns a `Health` object carrying a `Status` and optional details.

Standard statuses:

| Status | Practical meaning | Default health endpoint HTTP status |
| --- | --- | --- |
| `UP` | Contributor check succeeded | Usually 200 |
| `DOWN` | Check failed | Default 503 |
| `OUT_OF_SERVICE` | Intentionally removed from service or unable to serve | Default 503 |
| `UNKNOWN` | Status could not be determined | Usually 200 by default mapping; must not be treated as proof of health |

**Status is not absolute truth about a resource.** `Health.up()` simply means the indicator implementation returned `UP` for its specific check. The aggregated endpoint combines statuses across contributors; having both `UP` and `DOWN` yields `DOWN` per status ordering.

To introduce custom statuses like `DEGRADED` or `MAINTENANCE`, you must **define aggregation ordering and HTTP status mappings** explicitly. When customizing HTTP status mappings, verify mappings for `DOWN` and `OUT_OF_SERVICE` as well, since custom configuration can override defaults. Never add arbitrary statuses assuming Kubernetes will interpret "degraded yet keep routing traffic" automatically.

### Indicator Names and Component IDs in Health Groups

Spring Boot normally derives the contributor ID from the bean name: a bean named `shippingPartnerHealthIndicator` registers contributor ID `shippingPartner` because the `HealthIndicator` suffix is stripped. Thus `include: readinessState,shippingPartner` must match the exact contributor ID, not the Java class name or an endpoint URL.

You can verify registered contributors in a test environment with authorized health details, or inspect beans/registries at startup. Never assign two indicators the same contributor ID.

## 6. Choosing Which Dependencies Affect Readiness

There is no rule saying "any dependency `DOWN` must make readiness `DOWN`". Classify based on **ability to serve incoming traffic** and instance role.

| Dependency | When disconnected | How should readiness usually behave? | Rationale |
| --- | --- | --- | --- |
| PostgreSQL holding state required by every request | Cannot read/write mandatory data | Can be `DOWN` | Instance cannot perform its core function |
| Redis used purely as a cache with DB fallback | Cache misses or higher latency | Usually keep `UP` if fallback meets SLO | Pulling all pods eliminates fallback capacity too |
| RabbitMQ in a service using transactional outbox | Cannot publish events yet; SQL still accepts orders | Can stay `UP` for HTTP ingress; alert on relay lag separately | Flow still ingests work durably |
| RabbitMQ in a worker dedicated solely to consuming a queue | Worker receives no jobs | Check worker/deployment policy | HTTP readiness is not the primary signal for non-ingress workers |
| Optional partner shipping API | Cannot quote shipping live; returns "pending quote" | Usually `UP`/degraded via metrics, if contract permits | App still returns useful results |
| Partner shipping API required by every incoming request | No valid path when partner is down | Can be `DOWN` if routing to healthier instances helps | Trade off against risk of knocking out all replicas |
| One partition or specific tenant failing | Only one traffic slice is affected | Pod-level readiness lacks granularity | Needs per-tenant/partition routing or request-level errors |

**Multi-replica warning:** if every pod shares **the same** external API and that API goes down, putting it into readiness marks **every pod unready**, leaving the Kubernetes Service with zero endpoints—even while pods could still serve status pages or independent endpoints. That is a **cascading outage** caused by health policy itself.

Conversely, if one instance hits a broken local connection pool while other replicas stay healthy, dependency-aware readiness helps the load balancer route around the bad pod. Distinguish **per-replica local faults** from **global dependency outages**.

### Decision Matrix

Before placing an indicator into the readiness group, answer:

1. Does **every** traffic path through the **Service/Kubernetes endpoint** need this dependency to finish acceptably?
2. Is there a fallback, cache, outbox, or queue allowing valid responses or durable intake?
3. If the dependency fails for every replica, will pulling all pods help or hurt the system?
4. Is recovery automatic, and can the pod recover readiness even while receiving zero traffic?
5. Do we only need alerts for this dependency, or genuine **traffic gating**?
6. Is the dependency check fast, cheap, and safe when 100 pods call it periodically in parallel?

For multi-purpose services, a single **pod-level readiness** cannot express "endpoint A works, endpoint B is degraded". You may need split deployments, smarter routing, endpoint-level degradation, or per-endpoint error statuses rather than pulling the entire app out of service.

## 7. Implementing a `HealthIndicator` for a Mandatory HTTP Dependency

Suppose a service requires the shipping API for every new request. Create a dedicated **`RestClient`** for health checks with tight timeouts and map outcomes to `Health`.

Configuration:

~~~yaml
app:
  shipping:
    base-url: https://shipping.internal.example
~~~

Synchronous client bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class ShippingHealthClientConfiguration {

    @Bean("shippingHealthRestClient")
    RestClient shippingHealthRestClient(
            RestClient.Builder builder,
            @Value("${app.shipping.base-url}") String baseUrl) {

        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(250);
        factory.setReadTimeout(500);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

The 250/500 ms bounds are illustrative; tune to actual latency, SLOs, and replica counts. Using a separate client for health avoids inheriting long retries or large pools into probes, though you should monitor overhead too. When sharing or constructing request factories/transports, verify resource ownership in your framework version.

Indicator:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component("shippingPartnerHealthIndicator")
public class ShippingPartnerHealthIndicator implements HealthIndicator {

    private final RestClient client;

    public ShippingPartnerHealthIndicator(
            @Qualifier("shippingHealthRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.get()
                    .uri("/internal/ready")
                    .retrieve()
                    .toBodilessEntity();

            return Health.up()
                    .withDetail("dependency", "shipping-partner")
                    .build();
        } catch (RestClientException ex) {
            // Never return exception messages, internal URLs, tokens, or stack traces.
            return Health.down()
                    .withDetail("dependency", "shipping-partner")
                    .withDetail("reason", "request_failed")
                    .build();
        }
    }
}
~~~

This assumes the partner's `/internal/ready` endpoint **is specifically designed for health probing**, returns HTTP codes reflecting real readiness, produces zero side effects, and is secured via auth/network controls. If `retrieve()` encounters HTTP 4xx/5xx or transport errors, it throws an exception and the indicator returns `DOWN`.

**What NOT to do inside an indicator:**

- Never trigger shipment creation, write to databases, or publish real messages just to test liveness.
- Never call APIs taking tens of seconds inside every readiness probe.
- Never configure unbounded retries: health checks must return fast so orchestrators act promptly.
- Never put credentials, customer-containing response bodies, or stack traces into `Health.details`.
- Never treat `200 OK` from an external endpoint as proof that all downstream business workflows work.
- Never fail liveness because an external dependency is `DOWN`.

### When Should an Indicator Report `UP` Despite Dependency Failure?

If shipping quotes are an **optional feature**, a dashboard-facing indicator can still report `DOWN` so operators see the failure, while **excluding it from the readiness group**—or using a distinct status policy. The key is **decoupling dependency signals from traffic-routing decisions**. Never hide an outage by returning `UP` for a broken dependency without emitting metrics or alerts.

## 8. `ReactiveHealthIndicator` in WebFlux Applications

`HealthIndicator` is synchronous. In reactive applications, running blocking I/O inside a check can block event-loop threads and degrade responsiveness. Spring Boot can adapt synchronous indicators, yet for dependencies with non-blocking clients, **`ReactiveHealthIndicator`** is the natural fit.

Example using `WebClient`:

~~~java
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component("shippingPartnerHealthIndicator")
public class ReactiveShippingPartnerHealthIndicator
        implements ReactiveHealthIndicator {

    private final WebClient client;

    public ReactiveShippingPartnerHealthIndicator(
            WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://shipping.internal.example")
                .build();
    }

    @Override
    public Mono<Health> health() {
        return client.get()
                .uri("/internal/ready")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofMillis(600))
                .map(response -> Health.up().build())
                .onErrorResume(ex -> Mono.just(
                        Health.down().build()));
    }
}
~~~

This is an **alternative** to the synchronous indicator in Section 7—do not register both under the same bean name/ID. In production, externalize base URLs, credentials, and timeouts into configuration and manage the `WebClient` HTTP connector lifecycle properly. `timeout` bounds waiting on the publisher yet does not prove the downstream avoided completing side effects before cancellation.

**Avoid common reactive mistakes:**

- Never call `.block()` inside `ReactiveHealthIndicator.health()`.
- Never configure `retryWhen` loops longer than the Kubernetes probe's period/timeout.
- Never return `Mono.never()` or leak connections upon cancellation.
- Never share a business client and mutate its retries/timeouts globally just for health checks.
- Validate HTTP response contracts properly: if a health endpoint returns HTTP 200 with JSON `{"ready":false}`, parse the body instead of relying only on `toBodilessEntity()`.

## 9. Database, Redis, RabbitMQ, and Kafka: Matching Checks to Transports

Spring Boot Actuator auto-configures health contributors based on **classpath/beans and configuration**, such as `db` for JDBC `DataSource`, `redis` when a Redis client exists, and `rabbit` when RabbitMQ infrastructure is present. Not every broker library or adapter ships built-in indicators with equal depth; verify your starter and version.

| Dependency | What health checks usually do | What they cannot prove |
| --- | --- | --- |
| JDBC/DataSource | Acquire a connection and/or run a validation query | Valid schema migrations, error-free business transactions, sufficient pool capacity under peak load |
| Redis | Ping/lightweight command over connection | Good cache hit ratio, adequate fallback performance, all keys synchronized |
| RabbitMQ | Test broker connectivity/reachability via client | Proper queue bindings, consumer ACKs, flat DLQs, publisher confirms for specific events |
| Kafka | Optional custom `AdminClient`/metadata check if provided by app | Low consumer-group lag, healthy partitions, processed events |
| REST/gRPC partner | Ping endpoint/readiness API | Specific business request succeeding or staying within quota |
| Object storage | Lightweight head/metadata request per policy | PUT permissions on all keys, valid checksums, lifecycle rules |
| Spring Integration flow | Inspect bean/channel/worker status metrics | That a specific message traversed the flow and committed cleanly |

### JDBC Health Checks

Avoid running `SELECT COUNT(*) FROM orders` on a hundred-million-row table every few seconds for readiness. Lightweight checks like `SELECT 1` or JDBC connection validation reduce overhead, yet still do not verify business logic. When the DB slows due to locks or pool exhaustion, bound check timeouts so probes do not pile onto connection wait queues.

With multiple `DataSource`s, check whether contributors are grouped under `db` or registered per bean/group; exact names depend on Boot/config. Never assume `db=UP` confirms every datasource in the app is healthy.

### RabbitMQ Differs from a Primary Database

In an HTTP service using a SQL outbox, a broker outage raises **outbox lag** while the API keeps ingesting requests safely. Wiring `rabbit=DOWN` into readiness can knock out all HTTP endpoints without helping the broker recover. Keeping HTTP ingress ready while alerting on outbox lag and oldest pending event age is often better.

For a dedicated RabbitMQ worker, HTTP readiness ("ready for HTTP traffic") means little. Monitor consumer counts, queue age, redeliveries, nack/requeues, DLQs, and business outcomes; readiness can reflect whether the worker finished configuring and subscribed, without replacing consumer processing metrics.

### Kafka Consumers Differ from Kafka Producers

A service can maintain a healthy Kafka broker connection while its consumer group suffers **millions of records of lag**. Connectivity-only health reports `UP` even while event SLOs are broken. Evaluate consumption via consumer lag, time since last successful commit, rebalance frequency, deserialization errors, and DLQ/delivery policies—never convert brief lag into liveness `DOWN` and trigger restart loops.

## 10. Health Checks Must Be Cheap, Time-Bounded, and Never Worsen Outages

When 100 pods probe a dependency every 5 seconds, that generates dozens of health requests per second. If the dependency is already overloaded, retries inside probes turn health checking itself into an **outage amplifier**.

Good indicators follow these rules:

1. **Short timeouts** safely below the orchestrator's `timeoutSeconds`.
2. Zero or minimal retries; health checks should not use business request retry/backoff policies.
3. Target downstream endpoints **must have zero side effects** and minimal cost.
4. Read pre-collected snapshots or apply short-TTL caching when live checks are expensive.
5. Never hold coarse locks, open long transactions, or run blocking I/O on event loops.
6. Produce clear outcomes on timeouts, exceptions, auth failures, or disabled dependencies.
7. Allow readiness to recover automatically once the dependency recovers—without restarting the app.

Spring Boot supports caching health endpoint results via `management.endpoint.health.cache.time-to-live` in matching versions. Caching lowers overhead at the cost of delayed failure/recovery detection; keep TTL within acceptable bounds and test probe behavior. Watch for race conditions or stale states if adding custom caches between `UP` and `DOWN`.

### Circuit Breakers and Health Indicators Are Different

A circuit breaker protects **business request paths** from failing downstreams via closed/open/half-open states and retry/fallback rules. A health indicator is an **observability/traffic signal**. Never force a circuit breaker open/closed inside every probe or turn readiness checks into business commands.

When a circuit breaker is OPEN because an external API is broken:

- Dependency health may show `DOWN` or a dedicated state.
- Readiness can stay `UP` if the API is non-essential or fallback meets SLOs.
- Liveness generally stays `UP` as long as the app itself is healthy.
- Circuit state, fallback rate, and business error rate must still be monitored and alerted separately.

## 11. Returning Errors to Callers While the Instance Remains Ready

An instance can report **readiness `UP`** and still return HTTP 503 for a specific endpoint whose downstream is broken. That is not a contradiction: readiness governs **instance-level traffic routing**, whereas request-level HTTP codes reflect **specific operation outcomes**.

Examples:

| Situation | Appropriate request behavior | Readiness state |
| --- | --- | --- |
| Redis catalog read fails, SQL fallback succeeds | Return 200 with valid data | `UP` |
| Mandatory shipping quote fails because partner is down | Return 503/502/504 per failure type and contract | `UP` if other endpoints still serve |
| Async API safely persists job into SQL/outbox | Return 202 Accepted with job ID per contract | `UP` even while broker is unreachable |
| Primary SQL unreachable for every request | Return 503 for dependent requests | `DOWN` if instance cannot serve core function |
| Graceful shutdown underway | Stop admitting new requests after drain | `OUT_OF_SERVICE`/readiness `DOWN` |
| One tenant suspended by policy | Return 403 or domain error | `UP` for other tenants |

**Never collapse every downstream failure into generic HTTP 500**; distinguish timeouts, unavailability, bad input, and business rejections. Still, HTTP status mapping is an API contract: pick 502/503/504 and `Retry-After` to match gateways, client behavior, and SLOs rather than blindly applying a rigid table.

With `@RabbitListener`, when a downstream fails, messages can retry, undergo delayed redelivery, or move to a DLQ. Health indicators must never substitute for message acknowledgment semantics. Messages needing effectively-once business effects still require idempotency keys, inboxes, and proper transactions.

## 12. How Does an Outage Ripple Through the System?

Suppose `order-service` runs three replicas sharing a shipping API, yet only `/shipping/quote` needs that API. Suppose the shipping API goes down for 5 minutes:

~~~mermaid
sequenceDiagram
    participant P as Kubernetes probe
    participant O as order-service pod
    participant S as Shipping API
    participant C as HTTP client
    P->>O: GET /livez
    O-->>P: 200 UP
    P->>O: GET /readyz
    O-->>P: 200 UP (shipping excluded from shared readiness)
    C->>O: GET /catalog
    O-->>C: 200 from cache/DB
    C->>O: GET /shipping/quote
    O->>S: GET quote
    S--xO: 503 / timeout
    O-->>C: Classified error or contract fallback
    Note over O,S: Metrics: shipping_dependency_up=0; quote_failure_rate rising
~~~

This is an intentional choice: **keep pods ready to serve unaffected capabilities**, protect the dependency with timeouts/circuit breakers, and raise alerts via metrics.

If instead every pod put the shipping API in its readiness group and flipped `DOWN`, Kubernetes would strip all three pods from the Service—breaking even `GET /catalog`. That is not automatically a "safer" default.

### When Is Readiness `DOWN` Appropriate?

Suppose a payment-command worker loses access to the primary database **on that single instance** due to a corrupted local connection pool while peer replicas stay healthy. Removing that pod from routing reduces errors and shifts traffic to healthy replicas. Similarly, during startup before mandatory caches/configurations finish loading, `REFUSING_TRAFFIC` is completely appropriate.

For global outages affecting every replica, design **degraded modes**, queues/partitioning, or service-wide notices. Readiness cannot substitute for resilient degradation when all replicas share the same broken dependency.

## 13. Distinguishing Health Endpoints from Metrics, Tracing, and Logging

A health endpoint provides only a point-in-time snapshot during a probe. It cannot explain why messages piled up or why latency climbed over several minutes.

| Signal | Question answered | Example |
| --- | --- | --- |
| Health | Can this instance take traffic or does a dependency pass a probe? | `readyz=UP`, `db=UP`, `shippingPartner=DOWN` |
| Metrics | How severe and widespread is the error trend? | Request error rate, retry count, consumer lag, outbox age |
| Tracing | Where did a specific request slow down or fail? | Span HTTP → SQL → shipping API |
| Logs | What detailed failure happened at which layer? | SQL timeout, DNS failure, broker disconnect |
| Business reconciliation | Are outcomes accurate and complete? | Committed orders, unpublished outbox, duplicate events |

### Useful Metrics When a Dependency Goes Down

- `dependency_health_status` tagged by **standardized dependency name**, never raw URLs or user IDs.
- Health check latency and timeout counts; distinguish 401/403 auth failures from 5xx/timeouts.
- Downstream HTTP p95/p99 latency, circuit breaker state, fallback rate.
- JDBC pool active/pending, transaction rollbacks, SQL query latency.
- Redis fallback hits/misses and DB load surge during cache outages.
- RabbitMQ publisher confirm failures, queue depth, DLQ depth, oldest message age.
- Kafka consumer lag, rebalances, time since last successful processing.
- Outbox backlog, retry attempts, commit-to-publish latency.
- Per-instance readiness transitions, unready replica count, total ingress errors.

Watch cardinality: **never create metric tags holding `requestId`, `orderId`, object keys, emails, or URLs with query strings**. Keep labels bounded: dependency name, operation, failure category, and environment. In logs, include `traceId` and correlation IDs while redacting credentials, personal payloads, and connection strings.

### Health Indicators and Alerts Are Not Identical

Alerting on a single `DOWN` probe triggers noisy false alarms from brief network jitter. Alerts usually require sustained duration, error ratio, affected replica counts, or business impact. Conversely, an optional dependency should not fail readiness yet **still warrants alerts** when fallback rates breach SLOs.

Never rely solely on uptime or restart counts to judge integration health. A service can have 100% liveness uptime and 0% business completion because an outbox relay crashed or consumers stalled.

## 14. Testing Health Policy—Not Just Indicator Code

Unit testing a `HealthIndicator` verifies it maps responses to `UP`/`DOWN`. **Integration tests** must verify health groups, HTTP status codes, security rules, and behavior during downstream failures.

| Scenario | Setup | Expectation |
| --- | --- | --- |
| Dependency returns 200 | Stub healthy shipping readiness | `shippingPartner=UP` |
| Dependency returns 503 | Stub unavailable shipping | `shippingPartner=DOWN` fast, no unbounded retries |
| TCP connect refused | Stop stub server | Indicator `DOWN` and completes within deadline |
| Downstream hangs | Stub never responds | Check times out within budget |
| Dependency returns 401/403 | Wrong credentials/network policy | `DOWN`; never logs tokens or swaps admin creds |
| Optional dependency down | Excluded from readiness group | Readiness stays `UP`; dependency metric/alert fires `DOWN` |
| Required dependency down | Group includes mandatory indicator | Readiness `DOWN` / HTTP 503 by default |
| Liveness during external outage | Only `livenessState` in liveness group | Liveness stays `UP` if app is healthy |
| App still starting | Startup/warmup state not yet ready | Readiness refuses traffic until ready |
| Graceful shutdown | Publish `REFUSING_TRAFFIC` | Readiness stops new traffic before shutdown completes |
| Separate management port healthy while main port broken | Actuator port up, app listener broken | Probes on main application port catch the failure |
| All replicas lose partner | Simulate global outage | Policy does not mistakenly wipe out every pod |
| Slow indicator | Stub delay exceeds probe timeout | Does not exhaust workers/threads/event loops |
| Indicator throws unexpected error | Throw `RuntimeException` in check | Endpoint reports status cleanly without leaking stack traces publicly |
| Unauthorized exposure | Call from untrusted network | Components/details and sensitive fields hidden |

### Quick Verification Against a Running Server

With probes enabled on the application port, test in a staging/test environment:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health
~~~

Sample expected responses when a mandatory shipping dependency is `DOWN`:

~~~text
GET /livez -> 200, status UP
GET /readyz -> 503, status DOWN
GET /actuator/health -> depends on contributors, possibly 503
~~~

Test through the real embedded/running web server, not only `MockMvc` or context tests: port bindings, reverse proxies, Spring Security filters, and network paths can behave differently. Also test scenarios where **all pods** lose the dependency to confirm readiness policy does not trigger cascading outages.

### Testing `ReactiveHealthIndicator`

Use `StepVerifier` and an HTTP stub to verify the reactive publisher completes without blocking:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class HealthPublisherContractTest {

    @Test
    void unavailableDependencyProducesDown() {
        Mono<Health> publisher = Mono.just(Health.down().build());

        StepVerifier.create(publisher)
                .expectNextMatches(health ->
                        Status.DOWN.equals(health.getStatus()))
                .verifyComplete();
    }
}
~~~

This illustrates the **publisher contract** without real HTTP calls. More valuable application tests back `WebClient` with an HTTP stub returning 200, 503, or hanging, then assert both `ReactiveShippingPartnerHealthIndicator` output and the aggregated readiness endpoint response.

## 15. Troubleshooting Health Endpoints Reporting False `DOWN` or False `UP`

| Symptom | Likely cause | What to inspect |
| --- | --- | --- |
| `/actuator/health` `DOWN` yet `/readyz` `UP` | Readiness includes only `readinessState`, not failing dependency | Review health group membership; decide whether inclusion is warranted |
| Liveness `DOWN` when Redis/RabbitMQ fails | External indicator added to liveness group | Remove remote dependencies from liveness; review policy |
| All pods turn unready together | Readiness depends on a globally broken service | Separate optional vs. required dependencies and evaluate cascading risk |
| Health endpoint times out | Blocking/slow check or repeated retries | Tighten timeouts, simplify check, avoid blocking event loops |
| Health `UP` yet business requests fail | Check only runs TCP ping/`SELECT 1`, missing schema/perms/queue lag | Add business metrics and integration tests |
| Custom indicator missing | Bean not scanned, wrong name, missing Actuator | Inspect beans/context, contributor ID, health groups |
| Readiness group fails at startup | `include` lists nonexistent contributor ID | Check `shippingPartner` ID and profile configs |
| Probe returns 200 on management port while app refuses traffic | Probe hits port 8081 independently of port 8080 | Enable additional paths on main port |
| Health endpoint leaks URLs/stack traces | `show-details`/authorization misconfigured | Hide details, restrict network and RBAC |
| Health stays `DOWN` after dependency recovers | Stale TTL/cache or unrefreshed circuit/connection | Check health cache, connector, retry intervals, pools |
| Kafka shows `UP` despite huge consumer lag | Check tests connectivity only | Alert on lag and processing progress |
| RabbitMQ shows `UP` while messages stop processing | Dead consumers, wrong bindings, or growing DLQ | Watch consumer metrics, queue age, DLQ, replay |
| Readiness flaps continuously | Overly sensitive probes, jitter, flaky dependency | Cap timeouts, consider hysteresis/caching and `failureThreshold` |

### Procedure for Analyzing a Dependency Outage

1. **Identify the failing layer:** process, application port, internal state, dependency connection, or business logic.
2. **Read health groups separately:** liveness, readiness, individual contributors—never rely solely on aggregated `/actuator/health`.
3. **Correlate metrics:** HTTP/SQL/broker errors, latency, queue lag, circuit breakers, connection pools.
4. **Determine blast radius:** one pod, one AZ/region, one tenant, or all replicas.
5. **Assess fallbacks:** which endpoints still work; would marking the whole cluster unready help or worsen impact?
6. **Choose action:** restart only for unrecoverable internal breakage; traffic gating for isolated unready pods; fallback/queuing/retries/alerts for external outages.
7. **Verify recovery:** readiness returns `UP`, business requests succeed, outbox/queue backlogs drain, and no duplicate side effects occurred.

## 16. Common Misconceptions

**"Why is `/actuator/health/liveness` still `UP` when the database is `DOWN`?"**

That can be the right policy. The JVM/app is alive and can recover once the database returns. Liveness focuses on unrecoverable internal breakage, not mirroring every external dependency.

**"Why does Kubernetes still treat the pod as ready when `/actuator/health` is `DOWN`?"**

The default readiness group typically uses `readinessState` rather than aggregating all contributors. Inspect `/actuator/health/readiness`, its `include` list, and actual probe paths; Kubernetes ignores the aggregate endpoint when manifests target the readiness group.

**"If a required dependency is `DOWN`, must readiness always go `DOWN`?"**

Not always. When every replica depends on that external service, marking all pods unready leaves zero endpoints—breaking fallbacks and admin routes too. Decide based on traffic paths and SLAs, not theoretical importance alone.

**"If a TCP check to RabbitMQ passes, is the integration flow healthy?"**

No. Messages can be backing up, dead-lettering, misrouted, or unacked. Monitor publisher confirms, queue age, consumer progress, DLQs, and business completions.

**"If a health indicator returns `UP`, is the next business request guaranteed to succeed?"**

No. Health is a point-in-time check; the dependency can fail milliseconds later. Clients must still handle timeouts, safe retries, and unknown outcomes.

**"Should health checks call write endpoints to prove things really work?"**

No. Probes run frequently across many replicas; writing real data causes side effects, extra load, duplicates, and cost. For end-to-end canary checks, run a separate synthetic monitor with dedicated test identities, isolated data, and cleanup.

**"Does health `DOWN` cause the service to restart itself?"**

No. Restarts are triggered by orchestrator liveness policies. Readiness `DOWN` removes the instance from routing, while dependency indicators going `DOWN` may strictly drive alerts and observation.

### Implementation Checklist

1. Separate **liveness**, **readiness**, and individual dependency health; never use one status for every action.
2. Enable Actuator and probes on the proper endpoints/ports; if management runs on a separate port, verify additional paths and network routes.
3. Choose mandatory readiness contributors **based on traffic paths and fallback availability**, not blindly listing every dependency.
4. Keep external dependencies out of liveness by default; avoid mass-restarting pods during shared Redis/partner outages.
5. Keep indicators cheap, side-effect-free, tightly time-bounded, without infinite retries or sensitive leaks in logs/details.
6. In WebFlux, use `ReactiveHealthIndicator` with non-blocking I/O where appropriate.
7. Design degraded modes, circuit breakers, and outboxes so apps continue serving safely when optional dependencies fail.
8. Monitor error/latency metrics, pools, queue lag, DLQs, outboxes, and business completions beyond health status.
9. Test single-pod failures, **cluster-wide** external outages, and dependency recovery; observe real Kubernetes behavior.
10. Verify business failure paths independently: ACKs, idempotency, retries, SQL transactions, and event delivery cannot be replaced by `UP`/`DOWN` probes.

### Version-Specific References

- [Spring Boot Reference – Endpoints: Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): `HealthIndicator`, health groups, statuses, and security.
- [Spring Boot Reference – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness, readiness groups, and additional paths.
- [Spring Boot API – HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html): synchronous SPI.
- [Spring Boot API – ReactiveHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html): reactive SPI.
- [Kubernetes Docs – Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): restart and routing behavior per probe.

**Remember:** When a dependency is unavailable, a **`HealthIndicator` is a signal**, not an automated action and never a transaction or business guarantee. Design readiness around traffic capability, reserve liveness for internal process health, leverage fallbacks/outboxes/idempotency where appropriate, and observe everything an `UP`/`DOWN` boolean can never capture.
