# Health Check Path, Interval, and Initial Delay

In systems using **Spring Cloud LoadBalancer**, the list of `ServiceInstance` objects provided by discovery may contain stopped, starting, or unready instances. To reduce the likelihood of sending calls to unhealthy instances, the caller can use `HealthCheckServiceInstanceListSupplier` to probe instance health endpoints and include only instances evaluated as healthy in the selection pool.

Three settings determine most of the probing behavior:

- **Health check path**: which HTTP endpoint on the target service is called?
- **Initial delay** (`initial-delay`): how long does the scheduler wait before starting the first check cycle?
- **Check interval** (`interval`): how often does the scheduler rerun checks?

These are configured under the `spring.cloud.loadbalancer.health-check` prefix, not under the HTTP timeout configuration of RestClient/WebClient/OpenFeign. This lesson explains how these properties interact with discovery, instance filters, retry mechanisms, and error observability, and then builds an example you can test with multiple instances.

## 1. Where Does Health Checking Sit in Instance Selection?

In the client-side load balancing model, the caller sends requests to a **service ID** such as `inventory-service`. A discovery source supplies instances with host, port, and metadata. The `ServiceInstanceListSupplier` chain can filter the list before an algorithm like Round Robin or Random picks an instance.

~~~mermaid
flowchart LR
    A["RestClient / WebClient / OpenFeign"] --> B["Service ID: inventory-service"]
    D["SimpleDiscoveryClient / Registry"] --> S["ServiceInstanceListSupplier"]
    S --> H["HealthCheckServiceInstanceListSupplier"]
    H -->|"Selectable list"| L["RoundRobin / Random"]
    B --> L
    L --> I["ServiceInstance"]
    I --> T["HTTP request to instance"]
~~~

`HealthCheckServiceInstanceListSupplier` proactively sends health check requests to the instances provided by its delegate. Once the list is updated, the algorithm only sees the list returned by the supplier; it does not run an HTTP probe per business request.

Key points to remember:

1. **Discovery** indicates which instances are registered or known.
2. **Caller-side health checking** estimates which instances are responding on the check endpoint.
3. **LoadBalancer** chooses an instance from the processed list.
4. **HTTP client** actually connects and sends the business request.

An instance that just returned a successful health check can still fail immediately afterward. Conversely, a failed health check request does not by itself prove every API on the instance is broken. Health checks reduce risk; they do not replace timeouts, controlled retries, or error observability.

## 2. The Three Core Properties and Default Values

According to the Spring Cloud Commons properties documentation, the common default values are:

| Property | Default | Meaning |
|---|---|---|
| `spring.cloud.loadbalancer.health-check.path` | `/actuator/health` if unconfigured | HTTP path probed on the instance |
| `spring.cloud.loadbalancer.health-check.initial-delay` | `0` | Delay before the first scheduled check cycle |
| `spring.cloud.loadbalancer.health-check.interval` | `25s` | Time period between scheduler cycles |
| `spring.cloud.loadbalancer.health-check.port` | Port of `ServiceInstance` | Overrides the port for check requests if needed |

Example configuration in the **caller application**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 2s
        interval: 10s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
~~~

Meaning:

- If a health-check supplier exists for `inventory-service`, it checks `/internal/ready` on inventory instances.
- If a health-check supplier exists for another service without a service-specific entry, the default path is `/actuator/health`.
- The health-check supplier's scheduler uses `initial-delay` and `interval` according to the effective configuration.
- These properties **do not create a health-check supplier on their own**. If you only add YAML without creating the supplier or selecting the corresponding preset, instances may still be selected without any probing step.

Property values and names should be verified against the Spring Cloud Commons version in use. When using a Boot/Cloud BOM, keep compatible versions aligned before running the lab.

## 3. Configuring the Check Path per Service ID

The `health-check.path` property has a map structure, where the `default` key is the fallback path and other keys are specific service IDs:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          payment-service: /actuator/health/readiness
          catalog-service: /internal/health
~~~

When the checked service ID is `payment-service`, check requests use `/actuator/health/readiness`. A service ID without a specific entry uses `default`.

**Do not confuse the target service ID with the caller's `spring.application.name`.** For example, the caller has `spring.application.name: order-service` and calls `http://inventory-service` via a `@LoadBalanced` RestClient. In that case, the key to declare in the map is `inventory-service`.

The actual path must exist on the target service. If the endpoint is secured and returns `401` or `403` to the checker, the instance may be judged unhealthy even while business APIs work fine. If using Spring Boot Actuator and choosing `/actuator/health`, add `spring-boot-starter-actuator` to the **target application**, or implement an equivalent endpoint yourself.

Example dependency for inventory-service:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

The `/actuator/health/readiness` path only works when the Spring Boot application configures and exposes the corresponding health probes. Do not assume every version or every environment has this endpoint enabled out of the box.

### When Using a Separate Management Port

Suppose the inventory API runs on `8081`, while the health endpoint is only exposed on management port `9091`. A request to `http://localhost:8081/actuator/health` may return `404` even though `http://localhost:9091/actuator/health` works.

Spring Cloud LoadBalancer supports `spring.cloud.loadbalancer.health-check.port` to set a probe port different from the business port. If multiple replicas have different management ports, configuring a single shared port may not fit; design a readiness endpoint reachable through the discovery-advertised instance address, or configure a custom health-check mechanism based on per-instance metadata/port.

Distinguish between:

- `server.port`: the target application's port receiving business traffic.
- `management.server.port` (if set): the target application's Actuator port.
- `spring.cloud.loadbalancer.health-check.port`: set on the caller to adjust the port of **LoadBalancer's check requests**.

Changing the port on the caller does not change the target service's management port.

### When Intentionally Skipping Checks for a Service

According to Spring Cloud Commons documentation, if a service's specific path entry is set to empty or `null`, checks for that service may be skipped. Do not use this if you merely want to inherit the default: instead, **omit** the corresponding service key. An empty YAML entry and an absent entry can carry different meanings, so verify on your actual version.

## 4. initial-delay: When the Scheduler Starts

`spring.cloud.loadbalancer.health-check.initial-delay` is the delay before the scheduler begins health checking, for example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 3s
        interval: 15s
~~~

Conceptually, the timeline can be pictured as follows:

~~~text
Initialize health-check supplier
t = 0s
  |
  | initial-delay = 3s
  v
t ~ 3s       First scheduled probe cycle
  |
  | interval = 15s
  v
t ~ 18s      Next probe cycle
  |
  | interval = 15s
  v
t ~ 33s      Next probe cycle
~~~

This is strictly a timeline **per scheduler configuration**. Actual observed times may differ due to when the child context is created, thread scheduling, probe duration, and instance list refresh mechanics.

The default `initial-delay: 0` does not guarantee the first business request waits until **every instance has been checked**. Spring Cloud LoadBalancer normally creates a dedicated child context for a service ID on first use unless eager loading is configured. As a result, a newly started client may go through a brief period before stable probe results are available.

Do not use `initial-delay` to solve system-wide startup synchronization. If a service should receive traffic only when ready, combine instance readiness, discovery, and caller retry/timeout policies.

## 5. interval: Check Cycle, Not a Timeout

`spring.cloud.loadbalancer.health-check.interval` controls how often probing repeats:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 20s
~~~

`interval: 20s` does not mean a health check request is allowed to run for up to 20 seconds. **Interval is not an HTTP connect timeout or response timeout.** If probe requests take too long, the update schedule and when instance state is reflected can be affected. Transport timeouts must be set on the `WebClient`, `RestClient`, or `RestTemplate` executing the probe, depending on the supplier configuration.

Also distinguish it from LoadBalancer cache TTL:

| Concept | Question it answers |
|---|---|
| Health-check `interval` | When should probes run again? |
| Health-check `initial-delay` | When should the first cycle be scheduled? |
| Health-check `refetch-instances-interval` | When should the **instance list** be refetched from the delegate if refetch is enabled? |
| LoadBalancer `cache.ttl` | How long is the instance list cached in the separate cache layer? |
| HTTP response timeout | What is the maximum wait for a single request response? |

Do not use `cache.ttl` as a substitute for the health-check schedule, and do not use `interval` to bound HTTP wait times.

### Choosing a Long or Short Interval?

Shortening the interval detects unhealthy states faster, at the cost of more probe requests. With `M` callers, each checking `N` instances at an interval of `T` seconds, the approximate probe load is:

\[
\text{probe requests/second} \approx \frac{M \times N}{T}
\]

For example, with 40 callers, each seeing 12 instances, and an interval of 10 seconds, the system generates an average of roughly `48` probes/s, excluding list refetches, retries, or scheduling variations.

Therefore, do not apply `interval: 1s` across hundreds of callers merely for a sense of “instant failure detection.” Measure health endpoint load, failure detection latency, and failover time requirements before choosing an interval.

## 6. Enabling HealthCheckServiceInstanceListSupplier: YAML Alone Is Not Enough

The scheduler only runs when a health-check supplier is instantiated in the supplier chain. In a Spring MVC application using blocking RestClient, you can create a per-service-ID configuration.

**Caller application:**

~~~java
package com.example.caller;

import com.example.lb.InventoryHealthLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryHealthLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

**Supplier configuration for inventory-service:**

~~~java
package com.example.lb;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.ConfigurableApplicationContext;

public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withBlockingHealthChecks()
                .build(context);
    }
}
~~~

`InventoryHealthLoadBalancerConfiguration` lives outside the package scan of `com.example.caller`; avoid letting it accidentally become a global configuration. For reactive stacks, use `.withHealthChecks()` instead of `.withBlockingHealthChecks()` alongside the appropriate reactive HTTP components.

You can use the configuration preset `spring.cloud.loadbalancer.configurations: health-check` if your release train supports that preset, but understand which configuration scope it applies to and avoid mixing it with a custom supplier bean that causes duplication.

**Supplier ordering matters.** Place the health-check supplier right after the network instance source, before request-based filter suppliers like zone/hint. `HealthCheckServiceInstanceListSupplier` already uses its own replay/caching mechanism; generally avoid wrapping it further with `CachingServiceInstanceListSupplier` without clear benchmarked justification.

In systems relying on Eureka/Consul or a registry that already filters healthy instances, adding caller-side health checks may cause redundant probing. This mechanism is especially useful with `SimpleDiscoveryClient` declaring static instances, because a static list cannot detect processes that have shut down on its own.

## 7. Complete Caller Configuration Example

Suppose the caller needs to call inventory and catalog. Inventory has a dedicated readiness endpoint; catalog uses the default Actuator endpoint:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
            catalog-service:
              - uri: http://localhost:8091

    loadbalancer:
      health-check:
        initial-delay: 2s
        interval: 10s
        path:
          default: /actuator/health
          inventory-service: /internal/ready

      clients:
        inventory-service:
          health-check:
            interval: 5s
~~~

When both services are configured with a health-check supplier, the effective values are:

| Service ID | Path | Initial delay | Interval |
|---|---|---:|---:|
| `inventory-service` | `/internal/ready` | 2s | 5s |
| `catalog-service` | `/actuator/health` | 2s | 10s |

The `clients.inventory-service` branch overrides the interval for inventory in versions that support per-client configuration, without needing to duplicate initial-delay. If no supplier is declared for catalog, catalog's interval property **does not cause catalog to automatically run probes**.

Do not place the instance list under `spring.cloud.loadbalancer.clients.inventory-service`: the instance list belongs to discovery (`spring.cloud.discovery.client.simple.instances`) or a `ServiceInstanceListSupplier` source. The LoadBalancer namespace holds selection policies, not fixed target URI definitions.

## 8. Hands-on Practice: Custom Health Endpoint on Each Instance

In the test inventory-service application, create a controllable-status endpoint to test the probing schedule. The code below is for lab use only; do not expose health-mutating endpoints publicly in production.

~~~java
package com.example.inventory;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class DemoHealthController {

    private final AtomicBoolean ready = new AtomicBoolean(true);

    @GetMapping("/ready")
    public ResponseEntity<Map<String, String>> ready() {
        if (ready.get()) {
            return ResponseEntity.ok(Map.of("status", "UP"));
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("status", "DOWN"));
    }

    // For local testing environment only.
    @PostMapping("/demo/unready")
    public void markUnready() {
        ready.set(false);
    }

    @PostMapping("/demo/ready")
    public void markReady() {
        ready.set(true);
    }
}
~~~

Run the same inventory artifact on ports 8081 and 8082. Each process maintains an independent `ready` state. The caller configures both URIs under service ID `inventory-service` and `health-check.path.inventory-service: /internal/ready`.

Check directly with PowerShell:

~~~powershell
Invoke-WebRequest http://localhost:8081/internal/ready
Invoke-WebRequest http://localhost:8082/internal/ready
~~~

Initially both return 200. Next, mark instance 8082 as unready:

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8082/internal/demo/unready
~~~

Once the probe request has executed, instance 8082 can be excluded from the list eligible for LoadBalancer selection. When the change takes effect depends on `initial-delay`, `interval`, context state, probe duration, and the supplier implementation. Do not expect the change immediately after running the POST command.

Restore the instance:

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8082/internal/demo/ready
~~~

After subsequent probe cycles, instance 8082 can return to the healthy list.

### Observing via a Load-Balanced RestClient

In the caller, declare the builder:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

The inventory service can add a diagnostic endpoint:

~~~java
@GetMapping("/internal/instance")
public Map<String, String> instance(Environment environment) {
    return Map.of("port", environment.getProperty("server.port", "8081"));
}
~~~

The caller creates a RestClient with `baseUrl("http://inventory-service")` and forwards `GET /internal/instance`. Then send multiple requests through the caller:

~~~powershell
1..30 | ForEach-Object {
    Invoke-RestMethod http://localhost:8080/proxy/instance
}
~~~

`/proxy/instance` is a sample endpoint that the caller must implement to forward requests. The expected result when both are healthy is seeing both ports selected. When 8082 transitions to unready and **8081 remains healthy**, new selections after the supplier updates typically go only to 8081.

Record timestamps for marking `unready`, the corresponding probe, and the first time the caller stops selecting that instance. This is a better way to observe the effect of `interval` than merely reading YAML.

## 9. refetch-instances and repeat-health-check Do Not Mean the Same Thing

Two independent processes must be distinguished:

1. **Fetching the instance list:** the delegate `ServiceInstanceListSupplier` supplies or updates the known instances.
2. **Health checking:** the health-check supplier calls endpoints on known instances to determine the eligible subset.

A delegate may provide a fixed list and not re-emit lists when the registry changes. `HealthCheckServiceInstanceListSupplier` has additional properties to proactively refetch the list:

| Property | Default | Effect |
|---|---|---|
| `health-check.refetch-instances` | `false` | Whether to proactively refetch the instance list |
| `health-check.refetch-instances-interval` | `25s` | Interval for refetching the list when refetch is enabled |
| `health-check.repeat-health-check` | `true` | Whether to keep repeating probes independently |
| `health-check.update-results-list` | `true` | Whether to emit list updates per healthy instance discovered or collect all before emitting |

For example, to refetch the list every 30 seconds without running a separate repeating probe schedule:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 30s
        repeat-health-check: false
~~~

Spring Cloud documentation notes that each refetch can also trigger health checks, so disabling independent repetition is sometimes appropriate. However, this configuration **does not** keep a 10s `interval` running as before: the probe cycle depends on the refetch timing and how the delegate emits the list.

If `update-results-list: false` is used, the supplier collects all discovered healthy instances before emitting the new list, instead of emitting incremental updates. Depending on observation needs, this option avoids seeing intermediate lists being built mid-probe.

For a static SimpleDiscoveryClient list declared in `application.yml`, enabling refetch will not automatically discover new instances that are not in the configuration; if dynamic updates are needed, use a registry or an appropriate dynamic instance source.

## 10. Pay Attention to Behavior When No Healthy Instances Exist

This is crucial for failover expectations: according to official documentation, `HealthCheckServiceInstanceListSupplier` **normally returns only healthy instances, except when none are healthy; in that case it may return the entire retrieved list**.

Example:

~~~text
Discovery returns: [A, B, C]

A healthy, B failing, C healthy
  -> Supplier may return [A, C]
  -> Round Robin / Random chooses from [A, C]

A failing, B failing, C failing
  -> Supplier may fall back to [A, B, C]
  -> Business calls still risk hitting failing instances
~~~

Therefore, never describe this mechanism as an absolute **fail-closed** filter. It has fallback behavior when no healthy instances are found to avoid returning an empty result in certain situations. If the system requires “never send requests to any instance marked unhealthy,” design a separate filtering or fail-fast policy and test that exact condition.

This also means:

- Losing connectivity to all health endpoints can cause the caller to still attempt business requests.
- Returning 503 from every instance does not guarantee the caller immediately stops calling instances.
- HTTP timeouts, retries, circuit breakers, and proper user-facing error responses still need to be designed independently.

## 11. Why Do Requests Still Fail Even with a Healthy List?

Health checks are snapshots at probe timestamps; state can change **between two probes**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant H as HealthCheck supplier
    participant I as Inventory instance

    H->>I: GET /internal/ready
    I-->>H: 200 OK
    Note over H: Marks instance healthy
    Note over I: Process stops after probe
    C->>H: Fetch eligible list
    H-->>C: Still includes just-stopped instance
    C->>I: GET /api/items/SKU-001
    I--xC: Connection refused / timeout
    Note over H: Next probe cycle reflects status
~~~

This is not necessarily a bug in Spring Cloud LoadBalancer. It is an inherent limitation of **periodic probing**.

If a failed request can be safely repeated, you can consider retrying against another instance with a cap on total attempts. For payment creation or data-mutating operations, retries require an idempotency key or guarantees against duplicate side effects.

Configure timeouts on the HTTP client separately: RestClient timeouts differ from the scheduler interval, WebClient timeouts differ from waiting for the next probe, and OpenFeign has its own connect/read timeout configuration keys. Do not use `health-check.interval` to infer the wait limit for business requests.

## 12. Configuring path, interval, and initial-delay per Service

Suppose order-service calls inventory and payment. Inventory uses faster health checks because replicas are redeployed often; payment uses less frequent health checks to avoid probing a sensitive system.

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          payment-service: /actuator/health/readiness

      clients:
        inventory-service:
          health-check:
            initial-delay: 0s
            interval: 5s

        payment-service:
          health-check:
            initial-delay: 3s
            interval: 30s
~~~

In versions that support per-client-ID properties, service-specific configurations take higher precedence than defaults. This applies to the **target service ID**, not the caller's application name.

If the same application configures a health-check supplier for inventory but not for payment, payment's properties still bind, yet they will not spawn a health-check scheduler for payment automatically.

Verify your specific Spring Cloud version when combining the `health-check.path` map and nested `clients.<serviceId>.health-check`: scalar values like interval/initial-delay merge easily, whereas maps/lists may follow specific binder merge rules. Verify the actual path via network logs or breakpoints in operation.

## 13. Avoiding Extra Incidents Caused by Health Endpoints

A health check endpoint should be **lightweight, stable, and reflective of traffic-handling readiness**. If every call to the health endpoint runs multiple database queries, calls other services, and checks every dependency, probe load from hundreds of callers can add unnecessary pressure.

Some principles:

- Use readiness to decide whether to serve traffic; liveness is generally reserved for deciding whether to restart a process.
- Avoid automatically marking instances unhealthy en masse when a non-essential dependency fails; cascading failures can evict many replicas at once.
- Do not put tokens or sensitive data into health check paths.
- If the endpoint is not public, ensure the caller can access it via proper network/auth policies; returning 401/403 usually fails probes.
- Verify security groups, TLS, hostnames, and certificates; network/TLS errors also make endpoints appear unhealthy.
- Do not expose state-mutating endpoints like `/internal/demo/unready` in production.
- Monitor probe failures separately from business API errors; they have different causes and priorities.

If your system has a registry or orchestration layer that already provides instance readiness status, measure whether extra probes per caller are truly needed. Avoid running two overly aggressive health check mechanisms at the same time.

## 14. Common Troubleshooting Table

| Symptom | Possible cause | How to check |
|---|---|---|
| Changed `interval` but no probe requests happen | Health-check supplier not created | Verify actual `ServiceInstanceListSupplier` and `@LoadBalancerClient` configuration |
| Probe returns 404 | Wrong path or Actuator not present | Call path directly on instance, check `spring-boot-starter-actuator` |
| Probe returns 401/403 | Security blocks endpoint | Check authorization rules for the URL and probe requests |
| Probe hits wrong port | Management port differs from business port | Check `ServiceInstance.getPort()`, `management.server.port`, and `health-check.port` |
| Stopped 8082 but requests still hit 8082 | Next probe cycle not reached, list not updated, or fallback when all unhealthy | Compare timestamps, candidate list, and probe results |
| Added a replica but caller does not see it | Delegate is not emitting updated list | Check registry/discovery, consider `refetch-instances` |
| Path config for inventory has no effect | Wrong service ID | Compare logical URL/`@FeignClient(name)` and map key |
| High volume of probe requests | Interval too short, too many callers, or two health-check layers | Calculate probe load, inspect registry/Actuator |
| All instances return 503 yet caller still sends requests | Supplier fallback when no healthy instances remain | Evaluate fail-closed requirements and resilience policy |
| Errors occur during startup | Context initialization does not have stable probe results yet | Check `initial-delay`, eager load, readiness, and timeouts/retries |

## 15. Implementation Checklist

- [ ] Identify the service ID and the `ServiceInstance` list source.
- [ ] Ensure `HealthCheckServiceInstanceListSupplier` is actually configured; YAML alone is not enough.
- [ ] Choose the right path per service ID and confirm the endpoint returns HTTP success when the instance is ready.
- [ ] If using `/actuator/health`, the target application must include Actuator or an equivalent endpoint.
- [ ] Set `initial-delay` and `interval` based on desired failure-detection latency and probe cost.
- [ ] Distinguish scheduler interval, refetch interval, cache TTL, and HTTP timeout.
- [ ] If a separate management port is used, verify the probe port configuration.
- [ ] Do not layer both a caching supplier and a health-check supplier redundantly without need.
- [ ] Understand fallback behavior when **no healthy instances remain**.
- [ ] Observe actual requests, traces/metrics, and health-check logs when one instance fails or all fail.
- [ ] Test adding, removing, and restarting instances; do not test only once right after deploy.
- [ ] When using a discovery registry, determine whether re-checking on the caller is truly necessary.
- [ ] Configure timeouts, retries, circuit breakers, and idempotency policies separately at the appropriate layer.

## References

- [Spring Cloud Commons — Instance Health-Check for LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): how to configure the supplier, paths per service ID, refetching, and behavior when no healthy instances exist.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): look up default values for `initial-delay`, `interval`, `path`, `port`, and additional properties.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): learn how to expose health endpoints and health probes for target services.

**Conclusion:** `path` decides *where to check*, `initial-delay` decides *when to start the check schedule*, and `interval` decides *how often to repeat*. They only take effect when a health-check supplier participates in the `ServiceInstance` selection pipeline. Designing these three values properly—alongside discovery, readiness, observability, and fault-tolerance mechanisms—helps RestClient, WebClient, and OpenFeign reduce the risk of sending requests to unready instances while keeping the limits of periodic probing in mind.
