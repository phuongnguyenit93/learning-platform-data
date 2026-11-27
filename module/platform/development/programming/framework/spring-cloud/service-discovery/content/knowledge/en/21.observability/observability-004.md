# Measuring Registration Errors, Lookup Errors, and Registry Connection Latency

## Objectives

After this lesson, you will be able to:

- Distinguish service registration errors, discovery lookup errors, and lookup results with no instances.
- Measure success/failure counts and latency for register, deregister, and lookup operations.
- Separate registry connection establishment time from HTTP request or discovery query duration.
- Use Micrometer to create counters, timers, and gauges with controlled tag cardinality.
- Export metrics via Spring Boot Actuator and Prometheus, and build dashboards/alerts.
- Use metrics to isolate configuration, network, authentication, registry server, and client-side cache issues.

## 1. Why Measure Each Operation Type Separately?

A service registry is critical infrastructure. If a provider fails to register, consumers may fail to find instances. If lookups are slow, business requests can suffer increased latency even when services are otherwise healthy. If registry connectivity is flaky, clients may fall back on stale cached data or fail to refresh instance lists.

Do not lump every issue into a single metric named `discovery.errors`. Distinguish at least three groups:

1. **Registration:** a provider registers or deregisters an instance.
2. **Discovery lookup:** a consumer looks up a service ID and retrieves its instance list.
3. **Registry connectivity/request:** the client establishes a connection and sends requests to the registry.

| Group | Questions to Answer | Key Metrics |
| --- | --- | --- |
| Registration | How many registrations failed? Is registration duration increasing? | Operation count, failure count/rate, operation duration, retry count. |
| Lookup | How many queries returned instances, came back empty, or failed? How long does lookup take? | Lookup count by outcome, empty result count, lookup duration, instance count. |
| Connectivity | Can the client connect to the registry? How long do connections or requests take? | Connection state, connect attempt/result, connect duration, registry request duration. |

These three groups are related, but not synonymous. A lookup returning an empty list can be a valid outcome. A lookup throwing a timeout is a query error. An HTTP request to the registry can be slow even when a TCP connection was reused from a connection pool.

## 2. Distinguishing Operations, Requests, and Connections

Define precisely which interval each metric measures:

- **Registration duration:** time from when the application begins the registration operation until the client API completes or throws an error.
- **Lookup duration:** time from calling `DiscoveryClient.getInstances()` until a result or exception is returned. Depending on the implementation, this may include cache reads, local processing, and/or registry queries.
- **Registry request duration:** time to execute an HTTP/gRPC request or protocol operation to the registry, measured on the client side.
- **Connection establishment duration:** time from starting a new connection until the connection is ready. Depending on transport, this may include DNS resolution, TCP handshake, and TLS handshake.
- **Connection state:** current connection status or state-transition events, such as `CONNECTED`, `SUSPENDED`, `RECONNECTED`, `LOST` with Curator.

A `Timer` wrapping `getInstances()` measures lookup duration; it does not automatically measure TCP handshake time. When an HTTP client reuses a connection pool, many requests do not establish a new connection at all. Therefore, never label request duration as connect latency.

For Eureka, measure HTTP requests at the transport layer actually instantiated by the version in use. For ZooKeeper/Curator, track `ConnectionStateListener` and the duration from starting an attempt until receiving `CONNECTED`/`RECONNECTED`. For Consul or other HTTP clients, use the corresponding HTTP client hooks/observations.

## 3. Designing Metrics for Registration

Measure each operation separately:

- `register`: registering a new instance or re-registering.
- `deregister`: deregistering during shutdown or when an instance is removed.
- `renew`/`heartbeat`: renewing a lease if the registry/client exposes such an operation.
- `registration_retry`: number of retries for a registration operation.

Suggested metrics:

| Logical Metric | Type | Meaning |
| --- | --- | --- |
| service.registry.operations | Counter | Total register/deregister operations, categorized by outcome. |
| service.registry.operation | Timer | Time to complete a registration or deregistration operation. |
| service.registry.retries | Counter | Number of retries for registration or registration updates. |
| service.registry.registration.active | Gauge | Number of instance registrations the application believes are active, if a reliable status source exists. |

Tags should be bounded to stable values:

- `registry`: `eureka`, `consul`, `zookeeper`, `kubernetes`.
- `operation`: `register`, `deregister`, `renew`.
- `outcome`: `success`, `failure`, `timeout`, `rejected` if distinguishable.
- `service`: service name from a known configuration set, never taken arbitrarily from incoming requests.

### How Do You Define a Successful Registration?

With synchronous APIs, an operation is considered successful when the client completes without throwing an error according to the implementation's contract. With asynchronous APIs, measure the final outcome of the callback/future rather than only the task-enqueue time.

Not every `ServiceRegistry.register()` method returns a response confirming that the registry persisted the entry and all peers can see the instance. For instance, a `void` method might only signal failure by throwing an exception. In that case, a `success` counter means the client operation completed per the API contract, not proof that all consumers already see the instance.

If you need to confirm visibility, measure a separate signal such as `registration.visibility.delay`: the time from when a provider registers until an independent check observes the instance. Never mix visibility delay into registration duration.

## 4. Designing Metrics for Discovery Lookup

Each lookup should be classified into distinct outcomes:

- `found`: at least one instance returned.
- `empty`: query succeeded, but the instance list is empty.
- `error`: lookup threw an exception.
- You may add `timeout` if timeouts are separately identifiable while keeping total outcomes consistent.

Suggested metrics:

| Logical Metric | Type | Meaning |
| --- | --- | --- |
| service.discovery.lookups | Counter | Total lookups by service and outcome. |
| service.discovery.lookup | Timer | Lookup latency. |
| service.discovery.instances | Distribution summary/Gauge | Number of instances returned per lookup or currently cached. |
| service.discovery.empty | Counter | Number of lookups that found no instances. |
| service.discovery.errors | Counter | Number of lookups that failed with an exception. |

Do not merge `empty` into `error`. An empty list can result from an unregistered service, a wrong service ID, mismatched namespace/filters, or an unrefreshed cache. Exceptions typically indicate connectivity, authentication, timeout, or implementation failures.

When counting instances, specify clearly whether the number represents instances at lookup time, instances in cache, or instances on the registry server. These three sources can differ due to caching and replication lag.

## 5. Measuring Connection Latency and Registry Requests

Connection latency helps detect issues before register/lookup operations fail outright:

- Slow or unstable DNS resolution.
- TCP connect timeouts, packet loss, or firewall resets.
- Slow TLS handshakes, certificate or trust-chain problems.
- Connection pool exhaustion, forcing requests to wait for a connection.
- Slow or overloaded registry servers.

Separate the following metrics when supported by the transport:

| Metric | Interval Measured | Used to Diagnose |
| --- | --- | --- |
| service.registry.connect | Start of new connection creation until connection is ready. | DNS/TCP/TLS or network path issues. |
| service.registry.connection.acquire | Waiting to acquire a connection from the pool. | Pool too small or connections held too long. |
| service.registry.request | Sending request until receiving response. | Registry server, network round-trip, and request processing. |
| service.registry.connection.events | Number of connection state transitions. | Flaky connectivity or continuous reconnects. |
| service.registry.connected | Current connection state, typically 0 or 1. | Connection status at scrape time. |

If the library only exposes total request duration, name it accurately as request latency. Never infer connect latency without connection-layer instrumentation.

### Measuring Connection State with Curator

With ZooKeeper, `ConnectionStateListener` delivers events such as `CONNECTED`, `SUSPENDED`, `RECONNECTED`, and `LOST`. You can use these to update a gauge and increment an event counter. Initial connection or reconnect duration should be measured from the start of the attempt until the success event arrives; never measure from an arbitrary timestamp.

Example event-handling skeleton:

~~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.curator.framework.state.ConnectionState;

public class RegistryConnectionMetrics {

    private final AtomicInteger connected = new AtomicInteger(0);

    public RegistryConnectionMetrics(MeterRegistry meters) {
        Gauge.builder("service.registry.connected", connected, AtomicInteger::get)
                .tag("registry", "zookeeper")
                .register(meters);
    }

    public void onState(ConnectionState state, MeterRegistry meters) {
        switch (state) {
            case CONNECTED:
            case RECONNECTED:
                connected.set(1);
                break;
            case SUSPENDED:
            case LOST:
                connected.set(0);
                break;
            default:
                break;
        }

        Counter.builder("service.registry.connection.events")
                .tag("registry", "zookeeper")
                .tag("state", state.name().toLowerCase())
                .register(meters)
                .increment();
    }
}
~~~~

This is illustrative instrumentation, not a bean automatically provided in every Spring Cloud Zookeeper version. Attach the listener to the exact Spring-managed `CuratorFramework` bean following the application lifecycle. Never create a second Curator client solely to collect metrics.

The `connected` gauge reflects the state currently reported by the client. It does not prove that every registry request succeeds or that all service instances are healthy. `SUSPENDED` indicates lost connectivity; `LOST` indicates session loss according to the Curator version's semantics.

## 6. Instrumenting DiscoveryClient with Micrometer

Spring Boot Actuator uses Micrometer as its metrics facade. You can instrument lookups at the layer calling `DiscoveryClient`, where the application knows the service ID and can distinguish `found`/`empty`/`error`.

Example helper:

~~~~java
import java.util.List;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.cloud.client.ServiceInstance;

public class DiscoveryMetrics {

    private final MeterRegistry meters;

    public DiscoveryMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public List<ServiceInstance> recordLookup(
            String registry,
            String boundedService,
            Supplier<List<ServiceInstance>> lookup) {

        Timer.Sample sample = Timer.start(meters);
        String outcome = "error";

        try {
            List<ServiceInstance> instances = lookup.get();
            outcome = instances.isEmpty() ? "empty" : "found";
            return instances;
        } finally {
            sample.stop(Timer.builder("service.discovery.lookup")
                    .tag("registry", registry)
                    .tag("service", boundedService)
                    .tag("outcome", outcome)
                    .register(meters));

            meters.counter("service.discovery.lookups",
                    "registry", registry,
                    "service", boundedService,
                    "outcome", outcome).increment();
        }
    }
}
~~~~

Usage:

~~~~java
List<ServiceInstance> instances = metrics.recordLookup(
        "eureka",
        "inventory-service",
        () -> discoveryClient.getInstances("inventory-service")
);
~~~~

If `getInstances()` returns an empty list, `outcome` is `empty`. If a `RuntimeException` occurs, `outcome` stays `error`, both timer and counter are still recorded in `finally`, and the exception continues propagating to the caller.

In this example, `boundedService` must come from a known service ID list or allowlist. Never use arbitrary user-supplied values as a metric tag.

## 7. Instrumenting Registration Operations

You can wrap register/deregister operations with `Timer.Sample` and a counter. Example helper accepting a `Runnable` to avoid coupling to a specific registry implementation:

~~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class RegistrationMetrics {

    private final MeterRegistry meters;

    public RegistrationMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void record(
            String registry,
            String boundedService,
            String operation,
            Runnable action) {

        Timer.Sample sample = Timer.start(meters);
        String outcome = "failure";

        try {
            action.run();
            outcome = "success";
        } finally {
            sample.stop(Timer.builder("service.registry.operation")
                    .tag("registry", registry)
                    .tag("service", boundedService)
                    .tag("operation", operation)
                    .tag("outcome", outcome)
                    .register(meters));

            meters.counter("service.registry.operations",
                    "registry", registry,
                    "service", boundedService,
                    "operation", operation,
                    "outcome", outcome).increment();
        }
    }
}
~~~~

Example invocation:

~~~~java
registrationMetrics.record(
        "eureka",
        "inventory-service",
        "register",
        () -> serviceRegistry.register(registration)
);
~~~~

In practice, place the wrapper at the exact operation boundary so you do not double-count when the framework retries automatically. If measuring individual attempts, use a dedicated operation/tag such as `attempt`; if measuring the final result, increment the counter only once for the entire logical operation. Document the exact semantics in the metric name and dashboard.

Never catch and swallow an exception just so the metric outcome becomes `success`. The example above preserves the exception so the caller handles it according to retry/failure policy.

## 8. Exporting Metrics with Spring Boot Actuator

Add Actuator and the appropriate registry dependency. For Prometheus:

~~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~~

Endpoint configuration:

~~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    distribution:
      percentiles-histogram:
        service.registry.operation: true
        service.registry.request: true
        service.registry.connect: true
        service.discovery.lookup: true
~~~~

The `/actuator/metrics` endpoint helps inspect metrics in development environments. The `/actuator/prometheus` endpoint exports data in Prometheus format when the corresponding registry is configured.

In production, restrict access to management endpoints via authentication, network policies, or a dedicated management port. Never expose metrics endpoints containing internal details to the public Internet.

### Histograms and Percentiles

By default, a `Timer` can expose count, total time, and max. To compute p95/p99 in Prometheus, enable histograms for the relevant timers. Histograms create additional time series per bucket, so enable them only for metrics you genuinely need to track and choose appropriate buckets/SLOs.

Client-computed percentiles and histogram buckets have different properties. Histogram buckets can be aggregated across multiple instances; client-side percentiles generally cannot be accurately combined into cluster-wide percentiles.

## 9. Metric Naming and Cardinality

Metrics must have stable names and tags. Examples:

| Micrometer Metric | Typical Prometheus Name | Meaning |
| --- | --- | --- |
| service.registry.operations Counter | service_registry_operations_total | Total register/deregister operations by outcome. |
| service.registry.operation Timer | service_registry_operation_seconds_count, _sum, _bucket | Count and duration distribution of operations. |
| service.discovery.lookups Counter | service_discovery_lookups_total | Total lookups by outcome. |
| service.discovery.lookup Timer | service_discovery_lookup_seconds_count, _sum, _bucket | Distribution of lookup latency. |
| service.registry.connected Gauge | service_registry_connected | Current connection state. |
| service.registry.connection.events Counter | service_registry_connection_events_total | Number of connection state events emitted. |

Exact names may vary according to the registry/exporter naming convention. Check `/actuator/prometheus` to verify the actual names before writing PromQL queries.

### Avoiding High Cardinality

Do not use the following values as tags:

- Randomly generated instance IDs.
- Individual Pod IPs/hostnames if Pods churn frequently.
- Request IDs, trace IDs, correlation IDs.
- User IDs, tenant IDs, order IDs.
- Full URLs with query strings or exception messages.
- Arbitrary service names passed by callers.

Use tags with small value sets: `registry`, `operation`, `outcome`, `environment`, `service` from an allowlist. Exception class can be used if the set of exception types is bounded and contains no dynamic names; otherwise classify into `timeout`, `connection`, `authentication`, `other`.

High cardinality increases memory usage, scrape cost, storage, and Prometheus query cost. Granular details such as instance IDs or trace IDs belong in logs and traces, not metric labels.

## 10. Dashboards and PromQL

A registry observability dashboard should have at least four sections:

1. **Registration:** success/failure rate, retry count, p95/p99 registration duration.
2. **Lookup:** found/empty/error rate, returned instance count, p95/p99 lookup duration.
3. **Connectivity:** connection state, reconnect count, connect duration, and registry request duration.
4. **Impact:** failed requests due to no instance selected, 5xx rate, and caller service latency.

Example PromQL for registration failure rate:

~~~~promql
sum(rate(service_registry_operations_total{
  operation="register",
  outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(service_registry_operations_total{
    operation="register"
  }[5m])),
  1
)
~~~~

Lookup error rate:

~~~~promql
sum(rate(service_discovery_lookups_total{
  outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(service_discovery_lookups_total[5m])),
  1
)
~~~~

Lookup empty rate:

~~~~promql
sum(rate(service_discovery_lookups_total{
  outcome="empty"
}[5m]))
/
clamp_min(
  sum(rate(service_discovery_lookups_total[5m])),
  1
)
~~~~

p95 of registry request duration:

~~~~promql
histogram_quantile(
  0.95,
  sum by (le, registry) (
    rate(service_registry_request_seconds_bucket[5m])
  )
)
~~~~

p99 of discovery lookup:

~~~~promql
histogram_quantile(
  0.99,
  sum by (le, registry, service) (
    rate(service_discovery_lookup_seconds_bucket[5m])
  )
)
~~~~

The queries above assume metrics are exported under the corresponding Prometheus names and histograms are enabled. Adjust metric/tag names according to the actual exporter output.

Do not look at ratios alone. At low traffic volume, a single error can spike the percentage without major impact; at high volume, even a small error ratio can mean many failed requests. Dashboards should show rates, absolute counts, latency, and instance counts together.

## 11. Operationally Meaningful Alerts

A good alert should be tied to impact and persist long enough to filter out noise. Examples:

| Alert | Suggested Condition | Response |
| --- | --- | --- |
| Registration failure spike | Registration failure rate exceeds threshold for several minutes with sufficient attempts. | Check credentials, URLs, registry health, network, and rollouts. |
| Lookup error spike | Lookup errors rise continuously, excluding `empty` outcomes. | Check registry connectivity, timeouts, TLS, and API server. |
| Lookup empty spike | `empty` rate rises abnormally for a critical service. | Check provider registration, service ID, namespace, labels, and cache. |
| Registry latency high | Request or lookup p95/p99 exceeds SLO over a steady window. | Check server load, connection pool, DNS/TLS, and network. |
| Registry disconnected | `connected` gauge equals 0 or connection error state persists. | Check ensemble/server, routing, DNS, and credentials. |
| Reconnect storm | Reconnect count rises continuously. | Check network flapping, GC pauses, timeouts, and server saturation. |

Do not alert on a single empty lookup. Some services are deployed on a schedule or do not require instances in certain environments. Alerts should consider service criticality, duration, actual traffic, and baseline.

Use `for` in Prometheus alert rules to require a condition to hold continuously before firing. Set thresholds from SLOs and real operational data rather than copying one fixed number across every registry.

## 12. Diagnostics Workflow from Metrics

When you detect that consumers cannot find instances, follow this sequence:

1. **Check lookup outcome:** is it `empty` or `error`? If `error`, inspect exception categories and timeouts.
2. **Check registration:** did the provider see increased registration failures or retries? Did the errors coincide with a deployment?
3. **Check visibility:** did the registration operation succeed while the instance is still missing from the registry view? Is there replication/cache lag?
4. **Check connectivity:** are the `connected` gauge, connect attempts, reconnect events, and registry request latency abnormal?
5. **Check server:** inspect registry CPU/memory, request queues, peer/leader state, and server-side latency.
6. **Check configuration:** verify service ID, namespace, labels, URLs, TLS, authentication, timeouts, and proxies.
7. **Correlate logs/traces:** use timestamps and trace IDs in logs/tracing to inspect a specific operation; do not put trace IDs into metric tags.
8. **Verify recovery:** confirm registration and lookup return to normal after remediation, and confirm cached data refreshes properly.

For example, empty lookups rise while lookup errors stay flat, and registration failures rise on a provider. Most likely the consumer is querying successfully, while the provider is failing to register. If both lookup errors and registry request latency rise together, investigate the registry/network before concluding the service does not exist.

## 13. Common Instrumentation Mistakes

- **Counting retries as new operations:** inflates the registration failure rate. Separate logical operations from individual attempts.
- **Counting empty as error:** distorts dashboard semantics and causes noisy alerts.
- **Measuring only total latency:** hides whether slowness comes from DNS/TCP/TLS, pool acquisition, the registry server, or local cache.
- **Measuring getInstances() and calling it network latency:** the lookup may be served from cache.
- **Measuring enqueue instead of completion:** async metrics report success prematurely.
- **Using instance ID as a tag:** causes cardinality to grow with every deployment.
- **Catching exceptions and returning an empty list:** disguises connectivity errors as empty results, corrupting metrics.
- **Looking only at averages:** p95/p99 can degrade badly even when the average stays low.
- **Not distinguishing accepted registration from visibility:** the provider thinks it registered while consumers cannot yet see the instance.
- **Not testing when the registry is unavailable:** instrumentation is only verified on the happy path.

## 14. Implementation Checklist

- [ ] Counters exist for register/deregister and lookup.
- [ ] Distinct outcomes exist for `success`, `failure`, `found`, `empty`, and `error`.
- [ ] Timers exist for operation, lookup, and registry request.
- [ ] Connection establishment is measured separately if supported by the transport.
- [ ] Connection state and reconnect events are tracked.
- [ ] Registration success is clearly defined per the API implementation.
- [ ] Visibility delay is measured if you need to know when consumers see the instance.
- [ ] Uses Micrometer and exports via Actuator/Prometheus.
- [ ] Histograms are enabled for timers requiring p95/p99 calculation.
- [ ] Tags are restricted to stable value sets; no dynamic IDs or personal data.
- [ ] Exceptions are never converted into empty results.
- [ ] Dashboards include counts, rates, latency, and instance counts.
- [ ] Alerts distinguish registration failure, lookup error, lookup empty, and connectivity.
- [ ] Tested for timeouts, DNS/TLS, auth, registry restarts, stale caches, and retries.
- [ ] Management endpoints are protected and no sensitive data is exported.

## Key Takeaways

- Registration failure, lookup error, and lookup empty are three distinct outcomes.
- A timer wrapping `getInstances()` measures lookup duration, not necessarily TCP/TLS connection latency.
- Request duration, connection-pool acquire time, and connection establishment time should be named separately.
- Use Micrometer `Counter` for counting, `Timer` for measuring duration, and `Gauge` for reflecting current state.
- Define registration success clearly; API completion does not always mean all consumers can already see the instance.
- Separate logical operations from retry attempts to avoid double-counting.
- Use histograms to aggregate p95/p99 and bound metric tag cardinality.
- Combine metrics with logs, traces, and registry state to find root causes.

## Official References

- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot – Prometheus Endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer – Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html)
- [Prometheus – Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
- [Spring Cloud Commons – DiscoveryClient and ServiceRegistry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
