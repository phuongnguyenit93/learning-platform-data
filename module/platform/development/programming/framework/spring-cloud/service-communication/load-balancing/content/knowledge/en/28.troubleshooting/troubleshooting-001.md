# No available replicas: tracing from the list source to filters

In a microservices system using **Spring Cloud LoadBalancer**, a caller sends a request to a service ID such as `http://inventory-service/api/stock/SKU-001`. Spring Cloud retrieves the list of `ServiceInstance` objects—potentially going through discovery, caching, and health/zone/hint/version filters—and then Round Robin, Random, or a custom algorithm selects one instance.

When encountering a warning like **“No servers available for service: inventory-service”**, a message like **“No instances available for inventory-service”**, or an HTTP 503 on the caller side, the most effective fix is **not** increasing retries or hardcoding an IP in code. You need to pinpoint the exact stage where the candidate list becomes empty: **the discovery source, the refresh/cache step, the filtering suppliers, or the final chooser**.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will build an inspection workflow applicable to RestClient, WebClient, OpenFeign, health checks, zone/hint routing, and custom policies. It also includes a two-replica lab, local diagnostic snippets, observation commands, an error differentiation table, and regression tests.

> **Principle:** “No instance was selected” and “an instance was selected but connecting to it failed” are **two different phenomena**. Errors caused by LoadBalancer having no candidates usually require checking the service ID/discovery/supplier. `Connection refused`, `ConnectTimeoutException`, or HTTP 503 from the backend require checking the network, instance, and retry/timeout settings.

## 1. Identify the exact symptom before fixing

For the same failing request, different layers can surface different symptoms:

| Symptom | Initial clue | **Cannot conclude yet** |
|---|---|---|
| Log `No servers available for service: inventory-service` | LoadBalancer could not select a `ServiceInstance` | Does not mean all backend processes have stopped |
| `Response.hasServer() == false` | The chooser returned a response without a server | Does not tell at which layer the list became empty |
| `HTTP 503` from caller/gateway | Might be no instance, or the real upstream returned 503 | Do not assume this is a discovery error by default |
| `UnknownHostException: inventory-service` | The HTTP client might be trying to resolve the service ID via DNS directly | Not certain LoadBalancer is integrated |
| `Connection refused` to `10.0.0.12:8081` | A host/port was selected but could not be reached | Should not diagnose as “empty discovery” |
| `Read timeout` | The request may have reached the backend, which did not respond in time | Not certain the supplier list is empty |
| `CallNotPermittedException` | Circuit breaker is OPEN and blocking the HTTP call | Do not conclude LoadBalancer has no instances |
| Some requests succeed, others return `503` | Could be different caller replicas, cache snapshots, or route/version | Does not prove the registry is always empty |

Evidence must be collected at the **exact time** and on the **exact caller replica** experiencing the error. Running `curl` directly against the backend only shows a process is responding; it **does not prove** Spring Cloud on the caller can see it under the expected service ID.

### Conventions used in this lesson

- **Raw discovery list:** the list returned by `DiscoveryClient` or `ReactiveDiscoveryClient` before LoadBalancer filters.
- **Candidate snapshot:** the list returned by `ServiceInstanceListSupplier` after one or more decorators.
- **Selected response:** the result of `ReactorServiceInstanceLoadBalancer.choose(Request)`; either has an instance or does not.
- **Attempt:** a single actual effort by the HTTP client to connect/send a request.
- **Logical request:** a business request that may generate multiple attempts due to retries.

Do not mix these metrics when investigating.

## 2. Diagram of the instance list flow

~~~mermaid
flowchart TB
    REQ["Caller: service ID + Request context"] --> FACT["LoadBalancerClientFactory / client context"]
    REG["Registry / SimpleDiscoveryClient / DiscoveryClient"] --> SRC["ServiceInstanceListSupplier source"]
    FACT --> SRC
    SRC --> CACHE["Caching or HealthCheck per configuration"]
    CACHE --> FIL["Zone / Hint / Version / Custom filters"]
    FIL --> CHOOSE["RoundRobin / Random / Custom chooser"]
    CHOOSE --> DEC{"Has instance?"}
    DEC -->|Yes| HTTP["RestClient / WebClient / OpenFeign transport"]
    DEC -->|No| EMPTY["EmptyResponse / no-server"]
    HTTP --> DEST["Instance host:port"]
~~~

This is a **conceptual diagram**. Not every application enables caching, health checks, zone, hint, and version together; the actual order is determined by the configured `ServiceInstanceListSupplier`, built-in/custom decorators, and release train. Some suppliers have fallbacks or maintain their own state.

Identify **the list at each checkpoint**:

~~~text
serviceId = inventory-service

Registry / discovery                  [A, B, C]    size=3
Caching / health layer                [A, B]       size=2
Zone preference                       [A, B]       size=2
Hint preference                       [B]          size=1
API version strict filter             []           size=0
LoadBalancer choose                   no server
HTTP transport                        DOES NOT run
~~~

The scenario above illustrates a **strict version filter** emptying the list. Looking only at the registry where three instances remain will not reveal the root cause.

## 3. Isolation workflow using three comparisons

~~~mermaid
flowchart TD
    A["Request failed: no instance"] --> B{"Service ID/caller client correct?"}
    B -->|No| B1["Fix logical URL, @LoadBalanced, Feign name/url"]
    B -->|Yes| C{"Raw discovery has instances?"}
    C -->|No| C1["Check registry, registration, namespace, network, config"]
    C -->|Yes| D{"Final supplier list has instances?"}
    D -->|No| D1["Check cache, health, and each filter"]
    D -->|Yes| E{"choose() returns hasServer?"}
    E -->|No| E1["Check custom chooser/request context/EmptyResponse"]
    E -->|Yes| F["Check HTTP transport, instance host:port, timeout/retry"]
~~~

**Practical order:**

1. Record the **service ID**, logical URI, client type, caller instance, trace/correlation ID, timestamp, status, and exception class.
2. Verify whether the HTTP client itself is integrated with LoadBalancer or using direct DNS/a static URL.
3. Inspect the raw discovery list for the exact **service ID**.
4. Inspect the final output of `ServiceInstanceListSupplier` with the **corresponding request context**.
5. If the final list is empty, disable/test **each decorator individually** in a test environment or standalone supplier test.
6. If the final list is non-empty yet `choose()` still returns empty, inspect custom choosers or `Request` handling bugs.
7. If an instance was selected, move on to network/health/timeout checks instead of continuing to investigate an empty list.

Do not change the discovery server, cache TTL, health path, and retries simultaneously: when the error disappears, you will not know which change had an effect.

## 4. Verify the service ID and how the HTTP client calls it

An easy mistake to make is registering `inventory-service` while calling `http://inventory` or `http://INVENTORY-SERVICE` and relying on names “looking similar.” Service IDs may be normalized by some registries, but you should not assume all providers, keys, and caches handle case sensitivity and aliases identically.

~~~text
Registered service ID: inventory-service
Caller URI:           http://inventory-service/api/items/1  <-- same ID
Wrong URI:            http://inventory/api/items/1          <-- different service
Physical URI:         http://localhost:8081/api/items/1     <-- bypasses selection
~~~

### RestClient (synchronous)

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Having only a plain `RestClient.Builder` and calling the hostname `inventory-service` **without LoadBalancer attached** can lead to `UnknownHostException`, not `EmptyResponse`.

### WebClient (reactive)

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}

@Bean("inventoryWebClient")
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.clone()
            .baseUrl("http://inventory-service")
            .build();
}
~~~

WebClient only performs network I/O when the reactive publisher is subscribed to. Without a subscription, there is no request and possibly no selection either; do not interpret “no LoadBalancer log seen” as proof of an empty list.

### OpenFeign

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/api/items/{sku}")
    ItemView get(@PathVariable("sku") String sku);
}
~~~

You need `spring-cloud-starter-openfeign`, `@EnableFeignClients`, and proper LoadBalancer integration. If you configure `@FeignClient(url = "http://localhost:8081", name = "inventory-service")`, or a fixed URL property is bound, Feign may **bypass discovery selection**, even though `name` is still present. Therefore, a successful request using a fixed Feign URL **does not prove** the supplier is working.

## 5. Check the discovery source before looking at filters

Spring Cloud Commons provides both `DiscoveryClient` (blocking) and `ReactiveDiscoveryClient`. When you add an implementation such as Eureka/Consul/Zookeeper, the client queries the corresponding registry. When no registry-backed client is present, `SimpleDiscoveryClient` can read instances from properties.

Common causes of an empty raw list:

- The caller queries the wrong **service ID**.
- The provider has not registered yet, has not reached the appropriate registration state, or the registry recently evicted the instance.
- The caller and provider do not belong to the same namespace/cluster/environment.
- The caller is missing the discovery client dependency, has it disabled/disconnected, or points to the wrong registry endpoint.
- Credentials/TLS/network to the registry fail; the application still starts up, but discovery lacks the expected data.
- With static discovery, YAML/properties define the wrong `spring.cloud.discovery.client.simple.instances` key or the wrong profile.
- The registry returns only partial data due to registry-side health/status/capability filters.
- Multiple `DiscoveryClient` beans exist and ordering/composite behavior causes unexpected results.

### Quick check with `DiscoveryClient`

This probe is **for local/test environments only**, running in the caller within the same application context as the HTTP client:

~~~java
package com.example.order.diagnostics;

import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class DiscoverySnapshotProbe {

    private final DiscoveryClient discovery;

    public DiscoverySnapshotProbe(DiscoveryClient discovery) {
        this.discovery = discovery;
    }

    public void inspect() {
        List<ServiceInstance> instances =
                discovery.getInstances("inventory-service");

        System.out.println("raw discovery count=" + instances.size());

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "id=%s service=%s host=%s port=%d secure=%s%n",
                    instance.getInstanceId(),
                    instance.getServiceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure()
            );
        }
    }
}
~~~

This is only an **inspect method** and is not automatically invoked at startup. It can be called from an `ApplicationRunner` under a local profile or a unit test; do not expose backend addresses directly via a public endpoint. If the application uses reactive discovery exclusively, inspect `ReactiveDiscoveryClient.getInstances(serviceId)` with a subscription in a test and compare results. Do not call `block()` arbitrarily on a WebFlux event loop.

**Note:** `DiscoveryClient.getInstances(...)` on the caller measures the registry/discovery source, not the final candidates after suppliers. If the raw list still contains A/B/C while the HTTP client reports no-server, continue to the supplier layer.

### Checking on the registry and provider

For a real registry, verify registration directly using the official tool/endpoint of the registry in use. Confirm **service ID, instance ID, host, port, protocol, metadata, status, and last lease/heartbeat timestamp**. Do not rely solely on a UI from a different environment (e.g., staging registry while the caller points to the production registry).

For Kubernetes, if discovery works through Service/Endpoints or a custom provider, verify selectors/labels, endpoints, and namespace in the **right cluster**. If the infrastructure actually uses DNS/server-side LB rather than DiscoveryClient, the diagnostic story differs: confirm the architecture before expecting a `ServiceInstanceListSupplier` to contain data.

## 6. Create a reproduction environment with SimpleDiscoveryClient

To isolate the issue without an external registry, use an `order-service` caller on 8080 and two `inventory-service` backends on 8081/8082.

~~~mermaid
flowchart LR
    O["order-service :8080"] --> LB["Spring Cloud LoadBalancer"]
    REG["SimpleDiscoveryClient"] --> LB
    LB --> A["inventory A :8081"]
    LB --> B["inventory B :8082"]
~~~

Caller `application.yml`:

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
              - instance-id: inventory-a
                uri: http://localhost:8081
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "3"
              - instance-id: inventory-b
                uri: http://localhost:8082
                metadata:
                  zone: hn
                  hint: green
                  weight: "1"
    loadbalancer:
      zone: hcm
      retry:
        enabled: false
~~~

**Distinguishing the configuration fields:**

- `inventory-service` is the target service ID to call.
- `instance-id` is used to correlate logs; `uri` is the actual network target.
- `zone/hint/weight` metadata only take effect if the corresponding suppliers are enabled.
- `spring.cloud.loadbalancer.zone=hcm` **does not guarantee by itself** that zone policy is applied; `ZonePreferenceServiceInstanceListSupplier` is required in the supplier chain or configuration.
- `retry.enabled=false` is used in the lab so one request corresponds more cleanly to one selection attempt. If retries exist in Feign/WebClient/gateway, disable or control them separately.
- `SimpleDiscoveryClient` is a static source; when a backend stops, it may still return the stale address.

The backend can use a simple controller:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryDebugController {

    private final Environment env;

    InventoryDebugController(Environment env) {
        this.env = env;
    }

    @GetMapping("/whoami")
    Map<String, String> whoami() {
        return Map.of(
                "instance", env.getProperty("server.port", "?"),
                "service", "inventory-service"
        );
    }
}
~~~

Run two backend processes on 8081 and 8082 (for example via `--server.port=8081`/`--server.port=8082`), then test:

~~~powershell
Invoke-RestMethod http://localhost:8081/whoami
Invoke-RestMethod http://localhost:8082/whoami
~~~

If both commands succeed while the caller still reports no-server, the issue lies in **the caller's connection to discovery/config/supplier**, not in missing backend processes. If both commands fail, fix the backend/network before testing instance selection.

## 7. Observe the source and post-supplier output on the same caller

A useful technique is to capture **two list snapshots** inside a deliberately triggered diagnostic method: one from `DiscoveryClient`, and one from the supplier bean of the **per-service-ID LoadBalancer child context**.

Example for a **Spring MVC/test caller**, not to be run on a Reactor event loop:

~~~java
package com.example.order.diagnostics;

import java.time.Duration;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.DefaultRequest;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class InventorySupplierProbe {

    private static final String SERVICE = "inventory-service";

    private final DiscoveryClient discovery;
    private final LoadBalancerClientFactory factory;

    public InventorySupplierProbe(
            DiscoveryClient discovery,
            LoadBalancerClientFactory factory) {
        this.discovery = discovery;
        this.factory = factory;
    }

    public void inspect() {
        List<ServiceInstance> raw = discovery.getInstances(SERVICE);

        ServiceInstanceListSupplier supplier = factory.getInstance(
                SERVICE, ServiceInstanceListSupplier.class
        );

        System.out.println("discovery=" + instanceIds(raw));

        if (supplier == null) {
            System.out.println("supplier bean is absent");
            return;
        }

        List<ServiceInstance> finalList = supplier
                .get(new DefaultRequest<>())
                .next()
                .block(Duration.ofSeconds(3));

        System.out.println("finalSupplier=" +
                instanceIds(finalList == null ? List.of() : finalList));
        System.out.println("supplierType=" +
                supplier.getClass().getName());
    }

    private static List<String> instanceIds(
            List<ServiceInstance> instances) {

        return instances.stream()
                .map(ServiceInstance::getInstanceId)
                .toList();
    }
}
~~~

**Limitations of the probe:**

1. `@Profile("local")` restricts its use; do not expose backend metadata endpoints or logs publicly in production.
2. `LoadBalancerClientFactory` creates/reads a child context per service ID. Fetch the bean from the **`inventory-service` context**, not from the parent context where the real supplier may not be found.
3. `DefaultRequest<>` contains no HTTP headers, hint, or API version context. This probe only reflects **the path without request-specific filters**; it does not verify the hint/version path of the failing request.
4. `block(Duration)` is only suitable on a local blocking diagnostic thread and must not be called on a Reactor event loop.
5. Some suppliers emit multiple snapshots over time; `next()` takes **the first snapshot**, which is not guaranteed to be the snapshot another request used seconds earlier.
6. If `raw` and `final` differ, inspect **each decorator individually** rather than immediately blaming the health filter.
7. With multiple caller replicas, repeat the measurement **on the failing replica**, since each JVM has its own client context/cache/scheduler.

If your code uses an older Spring Framework/JDK version, adjust `Stream.toList()` and APIs accordingly. Examples must run with a compatible Spring Boot/Spring Cloud BOM.

### Can this safely measure request-specific hints?

To test a request carrying `X-SC-LB-Hint` or an API version, use an **integration test/client passing the proper `RequestDataContext`** into `supplier.get(request)` or observe `LoadBalancerLifecycle`. Do not stuff an arbitrary string into `DefaultRequest<>` and assume it behaves like HTTP headers. Prefer writing tests for the supplier decorator itself or exercising a real WebClient/RestClient/OpenFeign endpoint with the appropriate request context.


## 8. Cache layer: an empty or stale list may persist after the registry is fixed

`CachingServiceInstanceListSupplier` can cache discovery results to avoid querying the registry on every selection. This reduces overhead, but causes the state observed on the caller to be **not immediately synchronized** with the registry.

Example:

~~~text
14:00:00  Registry does not yet have inventory-service
14:00:01  Caller fetches list [] and caches the snapshot
14:00:05  Inventory A/B register successfully
14:00:06  Registry returns [A, B], but caller may still use cached []
14:00:36  Cache refreshes/expires; caller can see [A, B]
~~~

This timeline is illustrative only, not a strict guarantee on refresh timing. Actual TTL depends on how the cache is created, eviction, traffic, and release train configuration. Spring Cloud Commons documents `spring.cloud.loadbalancer.cache.ttl` as defaulting to **35s** in the corresponding versions, and the cache may use Caffeine or a default implementation depending on the classpath.

### Three questions for caching

1. What is `DiscoveryClient.getInstances(serviceId)` returning **right now**?
2. What is `CachingServiceInstanceListSupplier` or the underlying discovery provider returning?
3. Where does the cache sit in the supplier chain, and how many cache layers exist?

In particular, do not configure caching simultaneously in the Eureka/registry client **and** in LoadBalancer without knowing the combined TTL. Spring Cloud recommends avoiding double caching when the discovery client already caches.

Illustrative configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

To **isolate the cause in a lab environment**, you can try disabling caching:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

**Do not treat disabling cache as a default production fix.** Under high request rates, querying discovery on every selection can place heavy load on the registry. Instead, identify where the cache goes stale, choose an appropriate TTL, and handle updates/invalidation when topology changes.

### Place caching before per-request filters

Conceptually sound configuration:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Place `CachingServiceInstanceListSupplier` right after the supplier fetching instances over the network and **before** zone/hint/request filters, to avoid accidentally caching a list filtered for request A and serving it to request B with a different context.

During diagnosis, if the final list is empty while discovery already has A/B, recheck after the TTL expires or run a no-cache test to determine whether caching is the differentiating factor.

## 9. Health layer: probe failure does not necessarily mean an empty list

`HealthCheckServiceInstanceListSupplier` periodically probes the health endpoint and produces a list of instances considered alive. It is especially useful when `SimpleDiscoveryClient` only holds static addresses. However, health-check misconfigurations often mislead operators:

- Business endpoints return HTTP 200 at `/api/items`, yet `/actuator/health` returns 404 because Actuator is not installed.
- The health endpoint runs on a management port different from the service port used by LoadBalancer.
- Spring Security blocks the health endpoint (401/403), or the TLS certificate/truststore is incorrect.
- Health paths differ across service IDs.
- Probes time out even though business endpoints can still respond (or vice versa).
- Startup/probe/refetch timing causes health state to still be stabilizing.
- The health supplier is not actually enabled even though the team assumes it is just because properties were set.

### Checking the endpoint from the caller's location

Example where inventory A/B are on localhost in the lab:

~~~powershell
Invoke-WebRequest "http://localhost:8081/actuator/health"
Invoke-WebRequest "http://localhost:8082/actuator/health"
~~~

In container/Kubernetes environments, `localhost` on the caller refers to the **caller container**, not the backend. Use the host/port/info returned by discovery from the caller's exact network namespace.

Reference configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 0
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /actuator/health
~~~

In documented Spring Cloud versions, the default path is `/actuator/health`, default `initial-delay` is `0`, and default `interval` is `25s`. `initial-delay/interval` control the probe schedule, **not** the connect/read timeout of business calls.

If Actuator is absent, a controlled dedicated readiness endpoint can be used. If management runs on a separate port, check `spring.cloud.loadbalancer.health-check.port` and how that port applies to instances; a single global port may not fit when backends use different management ports.

### Configuring the supplier at the right layer

Reactive app / WebClient:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .build(context);
~~~

Blocking app / RestClient:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withBlockingHealthChecks()
        .build(context);
~~~

Spring Cloud notes that the health supplier includes its own replay/caching; do not arbitrarily stack `withCaching()` on top without understanding the ordering and snapshot updates. Health checks should sit directly after the discovery source and before per-request filters.

### What if all health probes fail?

**Do not guess the outcome from the name “HealthCheck”.** Spring Cloud Commons documentation for the referenced stable versions (such as 4.3 and 5.0/5.1) describes the behavior: if no healthy instances remain, the health supplier can **fall back to returning the entire retrieved list** to preserve availability (*fail-open*). However, development branches and custom implementations may enforce different policies, including returning an empty list (*fail-closed*). Verify the **running release train and implementation**.

Therefore:

- If raw discovery is already `[]`, the health supplier cannot “rescue” it by inventing instances.
- If raw discovery contains A/B yet all probes fail, **do not assume** this results in no-instance; some versions return A/B and the caller subsequently encounters connect/read failures.
- If a custom strict health filter returns `[]`, it can indeed be the layer emptying the candidate set.
- If the health list is stale, inspect replay/refetch mechanics rather than blindly lowering the interval.

### Refetching instances vs. repeating probes

Properties that may be helpful:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 25s
        repeat-health-check: true
        update-results-list: true
~~~

`refetch-instances` actively re-fetches **the instance list**, whereas `repeat-health-check` re-checks health status. `update-results-list` affects how results are emitted; these are not HTTP timeouts.

Do not enable continuous refetching in production solely to mask a misconfigured registry. When the discovery provider updates the list naturally, manual refetching may be unnecessary; measure the actual event flow.

## 10. Zone layer: soft preference, not a hard filter by default

`ZonePreferenceServiceInstanceListSupplier` compares `spring.cloud.loadbalancer.zone` (the caller's zone) with the `zone` metadata key on each `ServiceInstance`.

Example:

~~~text
Discovery: [A(zone=hcm), B(zone=hn)]
Caller zone=hcm
After zone preference: [A]
~~~

If the caller zone is wrong or **no instance is in the same zone**:

~~~text
Discovery: [A(hcm), B(hn)]
Caller zone=unknown-zone
After ZonePreference: [A, B] (fallback)
~~~

According to Spring Cloud documentation, `ZonePreferenceServiceInstanceListSupplier` **returns the entire delegate list** if the zone is null or has no match. Thus, a no-instance error when raw discovery has A/B **usually does not originate from default ZonePreference alone**; check custom filters, downstream filters after zone, or whether the delegate list was already empty.

### Zone checklist

- Does the caller have the correct `spring.cloud.loadbalancer.zone`?
- Does each instance's metadata have the exact **`zone`** key/value?
- Is `ZonePreferenceServiceInstanceListSupplier` actually enabled, or was only the property set?
- If the policy requires **hard isolation** by region/zone, is a custom filter intentionally returning `[]` when there is no match?
- If the zone list is empty after a strict filter, does it report no-instance rather than silently routing cross-zone?

Do not “fix” the error by disabling a hard zone filter if it protects data residency or security. In that case, returning a controlled error while scaling capacity in the same zone or fixing registry metadata is the right behavior.

## 11. Hint layer: check both the header and the Request context

`HintBasedServiceInstanceListSupplier` looks for a hint value in the request header—defaulting to `X-SC-LB-Hint`—or the hint configured in properties when the request carries none. It filters by the `hint` metadata key.

~~~text
Discovery: [A(hint=blue), B(hint=green)]
Request header: X-SC-LB-Hint: blue
After HintBased: [A]
~~~

If the hint is unknown:

~~~text
Discovery: [A(blue), B(green)]
X-SC-LB-Hint: unknown
After HintBased: [A, B] (default fallback)
~~~

**Not every missing hint causes an `EmptyResponse`.** The default hint supplier returns the delegate list if no hint is present or no matching instance is found. A no-instance failure after hint filtering usually points to an already-empty delegate list or a custom **strict hint filter**.

### Two easily overlooked questions

1. Did the HTTP client actually send the header?
2. Did `ServiceInstanceListSupplier.get(request)` **actually receive the hint context**?

The backend seeing the header does not automatically prove the supplier filtered by the hint: those happen at two different points. Across WebClient, RestClient, and OpenFeign, how context is passed to LoadBalancer can vary by transport and release train.

Illustrative configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint-header-name: X-SC-LB-Hint
      hint:
        default: blue
~~~

In a “no hint” test, remember that `hint.default` can still affect the policy. To isolate, test a request with neither header nor default and compare it against a request carrying `X-SC-LB-Hint` supplied from a trusted source.

**Security:** hints are not authorization. Never forward a user-controlled header verbatim to route to sensitive data pools or unauthorized versions.

## 12. Version filters and custom hard filters can truly empty the list

This is an easy place to miss when raw discovery still has instances, zone/hint both fall back, yet LoadBalancer ultimately fails to find a server.

Some Spring Cloud release trains provide `BlockingApiVersionServiceInstanceListSupplier` and `ReactiveApiVersionServiceInstanceListSupplier`. Per documentation, when an API version is determined but **no instance matches**, the supplier **returns an empty list** by default; there is an option to fall back to available instances if policy allows.

Example:

~~~text
Discovery: [A(version=1), B(version=1)]
Caller requests: API version=2
Version filtering: []
LoadBalancer: EmptyResponse
HTTP client: sends no attempt to A/B
~~~

This can be the **correct behavior** if version 2 is incompatible with version 1. Blindly enabling fallback could cause the caller to receive the wrong JSON schema or corrupt writes.

Mandatory questions:

- From which header/query/path/media type is the API version actually extracted?
- Is there a default version configured?
- Do instance metadata entries have the exact version key expected by the supplier/release train?
- Is there a **custom** version filter or hard canary routing feature flag?
- Is there a `fallback-to-available-instances` policy, and is it permitted?
- On no match, does the code return a controlled `EmptyResponse` or throw an unexpected exception?

### Example of a strict custom filter

Pseudo-code:

~~~text
request = {requiredVersion: "v2"}
candidates = discoverySupplier.get(request)

eligible = candidates.filter(
    instance -> instance.metadata["version"] == request.requiredVersion
)

if eligible.isEmpty():
    return []  // Do not silently fall back to another version.

return eligible
~~~

A custom filter may be **compliant with the security/business contract** when returning empty. In that case, the diagnostic goal is to find **why there are no eligible candidates**, not to “force LoadBalancer to always pick a server.”

## 13. Weights, subsets, stickiness, and retries: do not conflate their effects

Other suppliers/policies also alter the candidate set or selection preference:

| Policy | Primary effect | What to check on no-instance |
|---|---|---|
| `WeightedServiceInstanceListSupplier` | Adjusts selection weights from `weight` metadata | Is the delegate list empty? Does `WeightFunction` error or return invalid numbers? |
| Subset supplier | Picks a subset from a large list | Is the subset input empty, too small, or misconfigured in subset size/config? |
| Same-instance preference | Prefers the previously selected instance | Is the previous instance still in candidates? What are the fallback semantics? |
| Request-based sticky session | Prefers by cookie/context | Does the cookie point to a gone instance, and does the supplier fall back? |
| Retry-aware supplier | Prefers avoiding the recently failed instance | If only one instance remains, does the policy allow retrying it? |
| Custom zone/version/tenant filter | Restricts eligibility | Does it filter out everything due to missing metadata, wrong key, wrong case, or lack of permission? |

Per documentation, `WeightedServiceInstanceListSupplier` defaults to reading `weight` metadata, using weight 1 if absent. Do not assume `weight: 0` automatically removes an instance from discovery. Similarly, a retry-aware supplier can modify the list for a new attempt, not conjure a new instance out of thin air.

If a custom picker sees non-empty candidates yet returns no-server, check the `choose()` branch and data races instead of blaming weights or hints before reading the code.

## 14. Verify supplier configuration ordering

With per-service customization for `inventory-service`:

~~~java
package com.example.order.config;

import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryLoadBalancerRegistration {
}
~~~

And the supplier configuration class placed **outside the application's component scan**:

~~~java
package com.example.lb;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

Notes:

- `@LoadBalancerClient` defines configuration inside a **per-service-ID child ApplicationContext**.
- Do not accidentally let `InventoryLoadBalancerConfiguration` get component-scanned into a **global** config; it could alter suppliers for other service IDs.
- `withDiscoveryClient()` must pull from the right source. If using reactive discovery, pick the builder/provider matching your release train.
- `withCaching()`/`withHealthChecks()` should directly follow retrieval and come **before** request-aware filters.
- When adding health checks, you can use `.withDiscoveryClient().withHealthChecks().withZonePreference().withHints()` for reactive; blocking requires `withBlockingHealthChecks()`.
- Do not register another supplier for the same service ID without knowing which bean the client context actually picks.
- If using multiple custom decorators, document their order and behavior on empty/error inputs.

### How to isolate without breaking production

In a dedicated test profile, you can **temporarily configure** an incremental supplier chain:

~~~text
Test 1: Discovery
Test 2: Discovery -> Cache
Test 3: Discovery -> Cache -> Zone
Test 4: Discovery -> Cache -> Zone -> Hint
Test 5: Discovery -> Cache -> Zone -> Hint -> Version/custom
~~~

Using the **same service ID, same snapshot, and same request context**, record the output size at each step. Whichever layer transitions from `size>0` to `size=0` is where you need to inspect contracts, metadata, or config in depth.

Do not request enabling these test modes by modifying production config serving live traffic; use a test context, local/staging profile, or component tests with a mock supplier.

## 15. A non-empty list can still yield EmptyResponse from a custom chooser

After `ServiceInstanceListSupplier`, `ReactorServiceInstanceLoadBalancer.choose(Request)` selects the server.

A custom chooser can fail in situations such as:

- Computing `index % candidates.size()` when the list is empty and throwing an exception instead of returning `EmptyResponse`.
- Reading candidates from a separate source or stale cache rather than the injected list supplier.
- Having an overly strict `if (requestContext == null) return new EmptyResponse()` condition.
- Requiring metadata that does not exist and returning empty for all instances.
- Managing the index in a non-thread-safe way or retaining an index from an older snapshot size.
- Using `Mono.empty()` instead of emitting a `Response<ServiceInstance>` with `hasServer=false`, causing callers to behave unexpectedly.
- Skipping `ServiceInstanceListSupplier.get(request)`, thereby ignoring hint/version/retry information and filtering incorrectly.

A minimal no-instance handling branch:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.Response;

Response<ServiceInstance> chooseFrom(
        java.util.List<ServiceInstance> candidates) {

    if (candidates == null || candidates.isEmpty()) {
        return new EmptyResponse();
    }

    return new DefaultResponse(candidates.get(0));
}
~~~

This is only an **illustrative helper**, not a production algorithm. Always picking the first element risks unbalancing traffic. It demonstrates the contract that `EmptyResponse` is appropriate when no candidates actually exist; never return `new DefaultResponse(null)` just to “have a response.”

A chooser may legitimately reject a subset due to hard constraints (version, tenant), but it must **emit the reason** into metrics/logs/tests to distinguish “no instance in registry” from “no instance allowed to serve.”

## 16. “Raw discovery has instances but final list is empty”: layer lookup table

| Raw discovery | Cache/health | Zone/hint | Version/custom | Priority diagnosis |
|---|---|---|---|---|
| `[]` | `[]` | `[]` | `[]` | Wrong service ID, registry, discovery client, or registration |
| `[A,B]` | `[]` | `[]` | `[]` | Stale cache or strict health/custom filter; verify implementation |
| `[A,B]` | `[A,B]` | `[A]` | `[A]` | Normal zone/hint preference; failure may be post-selection |
| `[A,B]` | `[A,B]` | `[A,B]` | `[]` | Version/custom hard filter eliminated all candidates |
| `[A,B]` | `[A,B]` | `[A,B]` | `[A,B]` | If chooser returns empty: investigate custom chooser/Request context |
| `[A,B]` | `[A,B]` | `[A,B]` | `[A]` | A was selected; HTTP failure is a network/backend issue |

This table is a **diagnostic pattern**, not a claim that every supplier always executes in these exact columns. Observed data must come from the same caller and request context, or differences must be explicitly noted.

### Rule when observation sources conflict

If the registry UI shows two instances while the diagnostic probe sees 0:

- The caller may point to a different registry/namespace.
- The UI cache has not refreshed.
- The service ID is wrong or registered under another name.
- A composite DiscoveryClient has different ordering or behavior.
- The caller lacks credentials/TLS to query the registry.
- Profiles/override properties alter the discovery source.

If the raw probe sees two while final leaves only one:

- A filter is active and may be working completely as intended.
- Check **metadata** and the filter policy before immediately disabling it.

If both raw and final have two yet HTTP 503 occurs:

- Check `choose().hasServer()`, the host/port connection path, and the **origin of the HTTP 503**.
- Do not conclude 503 came from LoadBalancer solely from the status code.

## 17. Why a burst of 503 requests can occur even when the app boots “UP”?

The **caller's** `/actuator/health` reflects the caller's own health indicator policies. It does not guarantee that `inventory-service` has at least one eligible instance for **every request**.

Example:

~~~text
order-service process: UP
  - datasource UP
  - local web server UP
  - discovery client bean UP

inventory-service:
  - raw discovery []
  - no eligible instances
  - /api/orders -> 503 from client-side routing
~~~

Likewise, inventory's health endpoint is a liveness signal for the **backend**; it does not confirm that the caller has the right registered instance, unexpired TTL, matching zone/hint, or permission from a version filter.

Do not “fix” the caller's liveness/readiness by forcing it DOWN simply because an optional dependency temporarily has no instances: that can trigger restart loops and amplify load. If a dependency is mandatory for an API, surface a degraded status/SLO or business error per application policy; health groups must balance “able to serve” against the risk of cascading restarts.


## 18. Enable time-bounded diagnostic logging

When the application is still running but a service ID frequently reports no-server, you can **temporarily** raise log levels in a test environment or via a controlled runtime management mechanism.

~~~yaml
logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
    org.springframework.cloud.client.loadbalancer: DEBUG
    org.springframework.cloud.client.discovery: DEBUG
~~~

These loggers are **package-scope suggestions**, not a guarantee that every release train prints identical message strings. Inspect actual logs according to your implementation and class versions.

Order for reading logs:

1. Identify the **caller instance**, timestamp, trace/correlation ID, and target service ID.
2. Look for no-server/empty-candidates selection messages.
3. Check warnings from the registry client: unreachable registry, stale lease, misregistration, or missing permissions.
4. Check filter logs if custom code has instrumentation.
5. Record the exception type and HTTP status **at the client adapter**, not just the controller/gateway message.
6. After collecting enough information, revert the logger back to INFO to avoid high log volume and increased cost.

Do not log bearer tokens, cookies, sensitive internal addresses in public systems, payloads containing PII, or full registry metadata dumps. For a failed HTTP request, trace IDs may be used in controlled logs; never put trace IDs in metric labels.

### How to log candidate counts at the right layer

When building a custom supplier, you can log **bounded** data such as:

~~~text
serviceId=inventory-service
supplierStage=discovery  candidates=3
supplierStage=health     candidates=2
supplierStage=zone      candidates=2
supplierStage=version   candidates=0
outcome=no_server
~~~

All counts must come from **the same request context evaluation**. Do not stitch together a cached snapshot from 10 seconds ago with a freshly read discovery list and treat that as absolute proof.

Do not log a huge replica list on every request. In production, prefer aggregated metrics and sampled debug traces; if specific instance IDs are needed, enable them briefly with proper access controls.

## 19. Use Micrometer to distinguish no-instance from failed HTTP attempts

Spring Cloud LoadBalancer includes `MicrometerStatsLoadBalancerLifecycle` when a `MeterRegistry` and proper configuration are present. With Spring Boot Actuator, for example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Meters documented by Spring Cloud include:

| Meter | Interpretation | Useful when |
|---|---|---|
| `loadbalancer.requests.discard` | Requests that failed to obtain a service instance to forward to | Suspecting empty final candidates/no-server |
| `loadbalancer.requests.failed` | Load-balanced requests ending in an exception | Transport/caller encounters execution failure |
| `loadbalancer.requests.success` | Timer when a load-balanced request has relayed a response | Checking whether a response arrived; **does not imply HTTP business success** |
| `loadbalancer.requests.active` | Gauge of requests currently in flight | Assessing pressure/in-flight concurrency |

A request receiving an HTTP 503 response from the backend is **not necessarily** recorded the same way as an `EmptyResponse` request. Cross-check HTTP client metrics, backend access logs, and exception types.

### Querying metrics with PowerShell

Once traffic has occurred and Actuator is enabled:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"
~~~

Meters are only created once recorded; an endpoint returning 404 for a meter that has not appeared yet **does not prove** there are no errors. Verify the `spring-boot-starter-actuator` dependency, `MeterRegistry`, metrics toggle, and that traffic has actually run.

Alert along these dimensions:

- No-instance/discard rate by service ID and caller replica.
- Failure/connect timeout rate compared against the no-instance rate.
- Instance count returned by discovery vs. final count after filters (if the app exports custom metrics).
- Time since the last registry refresh/candidate update.
- Fallback rate, retry attempts, and circuit breaker OPEN state.
- **Origin** of HTTP 503/504 status: LoadBalancer, gateway, or backend.

For histogram labels, limit tag cardinality. `spring.cloud.loadbalancer.stats.include-path=false` helps reduce the risk of tagging by dynamic paths.

## 20. Reproduction lab: caller has two backends but cannot pick a server

In Section 6, we set up static discovery for A:8081 and B:8082. Add a caller endpoint to issue requests by service ID.

### Caller REST endpoint to test selection

Assuming `inventoryRestClient` is configured as in Section 4. Example controller:

~~~java
package com.example.order.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {

    private final RestClient inventoryClient;

    public ProxyController(
            @Qualifier("inventoryRestClient") RestClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/proxy/whoami")
    public InstanceView whoami() {
        return inventoryClient.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceView.class);
    }

    public record InstanceView(String instance, String service) {}
}
~~~

Illustrative code: declare the proper Spring Boot Web/LoadBalancer starters, REST client config, and project exception handler. If a network error occurs, the controller may return 500 unless an adapter handles the exception; **read the root exception** instead of guessing from the outer HTTP status.

Send multiple requests:

~~~powershell
1..6 | ForEach-Object {
    try {
        Invoke-RestMethod "http://localhost:8080/proxy/whoami"
    }
    catch {
        Write-Host ("HTTP call failed: " + $_.Exception.Message)
    }
}
~~~

When both backends are running, expected output: responses contain `instance=8081` or `instance=8082` with no no-server errors. Exact replica ordering is not guaranteed if concurrent traffic or a different cursor is involved.

### Scenario A — Wrong service ID

In an **isolated lab**, change the caller base URL to `http://inventroy-service` (transposed letters), while YAML discovery still registers `inventory-service`.

~~~text
DiscoveryClient.getInstances("inventory-service") -> [A, B]
DiscoveryClient.getInstances("inventroy-service") -> []
LoadBalancer request service ID             -> inventroy-service
Result                                      -> no server
~~~

Takeaway: always query the **exact service ID actually used by the URI/Feign client**, not just the intended name in documentation. Restore the correct base URL after testing.

### Scenario B — No instances in SimpleDiscoveryClient

In the lab profile, remove both `uri` entries for service ID `inventory-service` from caller config (or use a YAML profile containing only an empty list). Restart the caller.

Expected:

~~~text
raw discovery:   []
final supplier:  []
LoadBalancer:    EmptyResponse
HTTP backend:    receives no requests
~~~

This is the classic example of no-instance **at the source**.

### Scenario C — Instances exist but backend is stopped

Restore YAML [A, B], run the caller, **stop process 8082**, and keep 8081 running.

~~~text
raw discovery:   [A, B]  (static SimpleDiscoveryClient)
final supplier:  [A, B]  (no health filter enabled)
LoadBalancer:    may select A or B
If B selected:   connection refused/timeout
~~~

This is **not** a no-instance error caused by an empty list. Increasing cache TTL, changing zones, or disabling retries will not bring 8082 back to life. Fix via discovery deregistration/health policy, restoring the backend, or bounded retries if appropriate for the business operation.

### Scenario D — Strict version filter eliminates the entire list

Create a **test-only** `ServiceInstanceListSupplier` or adapter illustrating filtering on `api-version` metadata:

~~~text
raw discovery:
  A(metadata api-version=v1)
  B(metadata api-version=v1)

request requires: v2

strict filter:
  [A, B] -> []

choose:
  EmptyResponse

transport:
  no HTTP attempt
~~~

This scenario demonstrates the exact error “discovery has two instances, yet no **instance is available per policy**.” When version v2 is a hard requirement, a no-server result may be **contractually correct**. Fix by deploying a v2 instance or making an **approved** change to the caller requirement, not by silently falling back to v1.

### Scenario E — Configuring zone/hint assuming it is a hard filter

With A having metadata zone hcm/hint blue and B having zone hn/hint green, enable default `ZonePreferenceServiceInstanceListSupplier` and `HintBasedServiceInstanceListSupplier`.

- Caller zone hcm, hint blue: after zone+hint, only A may remain.
- Caller zone unknown: zone supplier falls back to A/B.
- Non-existent hint: hint supplier falls back to its input (A/B or A depending on the earlier zone result).
- If you **want** no-server when zone/hint does not match, a **custom hard policy** is needed; built-in default preferences may not produce that result.

**Goal of this test:** verify you do not equate “filter did not match” with “filter definitely returns an empty list.”

## 21. Three-layer regression testing

### 21.1. Unit test for empty input handling in the chooser

A selection function must handle empty input per contract:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.Response;

class SelectionContractTest {

    Response<ServiceInstance> select(
            List<ServiceInstance> candidates) {

        if (candidates.isEmpty()) {
            return new EmptyResponse();
        }

        return new DefaultResponse(candidates.get(0));
    }

    @Test
    void returnsNoServerWhenCandidatesEmpty() {
        assertFalse(select(List.of()).hasServer());
    }

    @Test
    void returnsServerWhenAnyCandidateExists() {
        ServiceInstance a = new DefaultServiceInstance(
                "a", "inventory-service", "localhost", 8081, false
        );

        assertTrue(select(List.of(a)).hasServer());
    }
}
~~~

The illustrative function intentionally picks the first element to focus on the empty/nonempty contract; **do not use it as a production load-balancing algorithm**.

### 21.2. Component tests for the supplier chain

With a fake discovery list A/B, verify at least:

| Test case | Input | Expected result |
|---|---|---|
| Empty discovery | `[]` | Final list `[]`, chooser returns no-server |
| Valid list | `[A,B]` | Final list preserves candidates or filters per policy |
| Zone hcm | A(hcm), B(hn) | ZonePreference selects A |
| Zone unknown | A(hcm), B(hn) | ZonePreference falls back to A/B |
| Hint blue | A(blue), B(green) | HintBased selects A when request context matches |
| Hint unknown | A/B | HintBased falls back to delegate |
| Strict version v2 | A/B both v1 | Empty list (fail-closed policy) |
| One unhealthy | A unhealthy, B healthy | Health filter selects per policy/release train |
| Both unhealthy | A/B unhealthy | **Verify actual behavior for your release train**, do not assume |
| Cache stale | Registry changes after snapshot | Results before/after refresh match mechanism |
| Discovery error | Upstream supplier throws error | Does not turn error into a fake success instance |
| Request-aware supplier | Hint/version in `Request` | Does not drop context when calling `get(request)` |

When using Reactor Test, `StepVerifier` can assert `Flux<List<ServiceInstance>>` or `Mono<Response<ServiceInstance>>`. Control the health scheduler's timing in tests to avoid flaky assertions.

### 21.3. Integration tests via real HTTP clients

Reproduce the same service ID across:

- **RestClient:** `@LoadBalanced` builder; verify whether empty/no-server and connection refused produce distinct exceptions.
- **WebClient:** verify subscription, request context, `StepVerifier`, and reactive error/fallback.
- **OpenFeign:** `@FeignClient(name=...)` without a static URL; verify integration and actual exception class.
- **Gateway/proxy:** distinguish client-side no-instance HTTP 503 from backend HTTP 503.
- **Retry:** ensure no-instance does not create an infinite retry loop; if one healthy instance exists, retries remain within total timeout/deadline.

In tests, record how many times the backend actually receives a request. When no-server occurs before the network layer, backend access logs show **no new attempts**. This is useful evidence to distinguish it from sending a request to an instance and getting a 503 back.

## 22. Choose remediation matched to the root cause

| Root cause | Right remediation | Harmful workaround |
|---|---|---|
| Wrong service ID | Fix name in URI/`@FeignClient(name)`, registry metadata | Hardcoding backend IP |
| Instance not registered | Restore registration/lease, namespace, client credentials | Enabling infinite retries on caller |
| Discovery client failure | Fix registry endpoint/TLS/network, inspect errors | Disabling all validation/SSL |
| Empty stale cache | Tune TTL/refresh/invalidation per design | Disabling caching in high-load production without measuring |
| Health probe wrong path/port | Fix actuator/management path, port, TLS, security | Forcing every instance “healthy” without checking |
| All-unhealthy behavior differs from expectation | Verify implementation/release train, design fail policy | Assuming health always fails closed |
| Zone/hint mismatch | Fix metadata/request context, verify soft fallback | Disabling mandatory hard isolation |
| API version strict filter | Deploy matching version instances or fail fast | Falling back to incompatible version |
| Buggy custom supplier filter | Write tests, fix predicate, log candidate counts | Returning full list bypassing security policy |
| Custom chooser returns empty | Fix contract and unit/concurrency tests | Returning `DefaultResponse(null)` |
| Server selected but connection refused | Fix host/port/network and deregistration | Continuing to chase “no instance” |
| Circuit breaker OPEN | Inspect dependency failures/thresholds/recovery | Raising LoadBalancer TTL to “open the circuit” |
| Backend HTTP 503 | Inspect backend access logs, capacity, health, overload | Labeling it an empty registry purely from status |

**Good recovery** requires observing both infrastructure recovery and request path restoration: the registry regains instances, the supplier sees eligible candidates, the chooser returns `hasServer=true`, HTTP attempts reach the backend, and responses meet SLOs.

Do not apply emergency changes like disabling version/zone hard filters if they enforce authorization or data residency boundaries. For policy-valid no-instance errors, the application should return a structured error with bounded retry/backoff rather than routing to a disallowed backend.

## 23. Incident response runbook

Use the following sequence when receiving an alert related to `inventory-service`:

~~~text
[1] Scope the failing request
    caller instance, timestamp, traceId, serviceId,
    status, exception class, logical request vs attempt

[2] Verify client integration
    RestClient/WebClient @LoadBalanced?
    Feign name/url?
    Calling the right service ID vs DNS/static URL?

[3] Query discovery source from the caller itself
    getInstances(serviceId) or reactive counterpart
    If [] -> registry/registration/profile/namespace

[4] Query final supplier with request context
    If [] while raw != []:
      cache -> health -> zone -> hint -> version/custom

[5] If final != [] yet choose returns no-server:
    custom chooser / response wrapper / concurrency

[6] If choose returns a server:
    host:port / connect / TLS / timeout / backend 503

[7] Fix root cause without dropping security policies
    monitor refresh, recovery, and counters

[8] Close incident with regression tests
    test empty, stale, no-match, and healthy behavior
~~~

### Minimum incident report output

| Field | Illustrative example |
|---|---|
| Event | `inventory-service` has no eligible instances |
| Time window | 14:05–14:12 UTC+7 (example) |
| Caller replica | `order-2` |
| Service ID | `inventory-service` |
| Raw discovery | 2 instances |
| Final supplier | 0 instances |
| Emptying layer | Strict version filter requiring v2 |
| HTTP attempts | 0 for rejected requests |
| Backend state | Both replicas registered as v1 |
| Remediation | Deploy v2 / update policy per plan |
| Verification | Final supplier >0, `hasServer=true`, HTTP SLO met |
| Prevention | Contract tests during API version rollout, no-instance alert |

This is a **sample report**, not an actual investigation result from any system.

## 24. Checklist before concluding the bug is fixed

- [ ] Verified exact service ID from logical URL/Feign name.
- [ ] Distinguished no-server, `UnknownHostException`, connection refused, timeout, and backend 503.
- [ ] Checked `DiscoveryClient`/`ReactiveDiscoveryClient` from the affected caller.
- [ ] Confirmed registry/provider has the right namespace, environment, and registration state.
- [ ] Compared raw discovery list against final `ServiceInstanceListSupplier` list.
- [ ] Accounted for cache TTL and multi-layer caching before comparing timestamps.
- [ ] Verified health path, port, security/TLS, schedule, and refetch settings.
- [ ] Verified all-unhealthy fallback behavior for the running version.
- [ ] Checked `spring.cloud.loadbalancer.zone` and `zone` metadata.
- [ ] Checked hint header/property, `hint` metadata, and `Request` context.
- [ ] Checked API version filter and custom hard filters.
- [ ] Did not disable mandatory tenant, version, or data-residency filters just to “fix” 503s.
- [ ] `@LoadBalancerClient` config targets the right child context/service ID and is not globally scanned.
- [ ] Confirmed that when the final list has servers, custom choosers return a valid response rather than abnormal null/empty.
- [ ] Confirmed that when a server is selected, host/port, TLS, network, and backend health were checked.
- [ ] Read no-instance/discard and HTTP failed/success metrics using their exact definitions.
- [ ] Bounded retries/timeouts so no-instance does not trigger a retry storm.
- [ ] Ran tests for single instance, multiple instances, empty list, stale cache, and no-match filter.
- [ ] Observed actual recovery rather than testing only a single HTTP 200.
- [ ] Documented root cause, remediation actions, and regression tests.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, caching, health, zone, hint, API version, retry, metrics, and custom LoadBalancer.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `DiscoveryClient`, `ReactiveDiscoveryClient`, `SimpleDiscoveryClient`, and registration.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): cache TTL, health-check path/refetch, hint, retries, and statistics.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): synchronous HTTP client, URI templates, and exception handling.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive client, error/cancellation, and request filters.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign name, URL, LoadBalancer integration, and exceptions.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `/actuator/metrics`, MeterRegistry, and application observability.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` for publishers and reactive state.

**Conclusion:** to troubleshoot **no available replicas**, do not merely ask “is inventory-service running?”. Prove each stage with data: **caller uses the right service ID → discovery has instances → cache/health are up to date → filters keep the right eligible candidates → chooser returns a server → HTTP transport actually sends the request**. Once you locate the first layer turning the list from populated to empty, you can fix the exact configuration or policy, preserve necessary security constraints, and add tests so the incident does not recur.
