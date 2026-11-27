# Random: random selection and distribution across many requests

In **Spring Cloud LoadBalancer**, a client calls a service via a *service ID* such as `inventory-service` and needs to pick a specific `ServiceInstance` to send the HTTP request to. Spring Cloud provides two basic selection algorithms: **Round Robin** (default) and **Random**. Random chooses a candidate at random from the instance list provided at selection time, so the same instance can be selected multiple times in a row; a roughly even distribution is only a statistical expectation when the number of selections is sufficiently large and conditions are stable.

This lesson focuses on the meaning of `RandomLoadBalancer`, the probability of selecting each replica, how distribution is observed across many requests, and how to enable Random for a specific service ID. The final sections present a hands-on model with RestClient, how to measure request counts, the effects of discovery/health checks/retries, and pitfalls to avoid in operations.

## 1. What does Random solve?

Suppose a system has an `order-service` application that needs to call `inventory-service`. Discovery returns three replicas:

| Service ID | Instance ID | Address |
|---|---|---|
| `inventory-service` | `inventory-1` | `http://localhost:8081` |
| `inventory-service` | `inventory-2` | `http://localhost:8082` |
| `inventory-service` | `inventory-3` | `http://localhost:8083` |

The caller does not need to know in advance which instance will serve the request. When using an HTTP client integrated with LoadBalancer, the caller invokes the logical URL:

~~~text
http://inventory-service/api/items/SKU-001
~~~

Spring Cloud LoadBalancer receives the service ID `inventory-service`, queries the list of eligible `ServiceInstance`s, and selects a candidate. With Random, on each valid selection, the selector randomly picks a position in the candidate list.

~~~mermaid
flowchart LR
    A["Order service"] -->|"http://inventory-service"| B["Spring Cloud LoadBalancer"]
    S["Discovery / ServiceInstanceListSupplier"] -->|"[inventory-1, inventory-2, inventory-3]"| B
    B --> R["RandomLoadBalancer"]
    R -->|"select one instance"| C["HTTP transport"]
    C --> D["inventory-1 :8081"]
    C --> E["inventory-2 :8082"]
    C --> F["inventory-3 :8083"]
~~~

The diagram shows the targets that can be selected, not that one HTTP request is sent to all three. Normally, one selection returns **one** `ServiceInstance` for that request dispatch. Retry, if configured, may cause a business call to trigger additional selections/dispatches afterward.

## 2. Mechanism for selecting a random instance

You can picture the selection mechanism like this:

~~~java
List<ServiceInstance> candidates = supplier.getInstances(serviceId);

if (candidates.isEmpty()) {
    // No suitable instance found: return empty/appropriate error result.
} else {
    int index = ThreadLocalRandom.current().nextInt(candidates.size());
    ServiceInstance selected = candidates.get(index);
    // HTTP client will use selected's host, port, and scheme.
}
~~~

This is **pseudocode illustrating the algorithm**, not a direct drop-in replacement for Spring Cloud's reactive API. The actual `RandomLoadBalancer` class receives the list from `ServiceInstanceListSupplier` and returns the selection result via the LoadBalancer API.

Edge cases:

- **Empty list:** no instance to select. LoadBalancer returns a no-server result, and the HTTP integration may report an error/response such as 503 depending on the client, adapter, and error-handling policy.
- **Single-instance list:** Random always selects that instance; multi-replica distribution cannot occur.
- **Multi-instance list:** picks a random position from the candidate set at that moment.
- **Changing list:** the next selection can use the new list after discovery and cache/supplier layers refresh.

Random does not need to maintain a circular pointer like Round Robin. It also does not track connection counts, latency, CPU, or request history per replica to balance by load.

## 3. Probability when the list is stable

Suppose the list consists of `n` **distinct instances, each appearing once**, chosen uniformly. Then the probability of selecting a given instance in one turn is:

\[
P(\text{select instance } i)=\frac{1}{n}
\]

| Available instances | Selection probability per instance in one turn |
|---:|---:|
| 1 | 100% |
| 2 | 50% |
| 3 | About 33.33% |
| 4 | 25% |
| 5 | 20% |

With three instances `A`, `B`, `C`, a completely valid sequence of outcomes is:

~~~text
Request:     1  2  3  4  5  6  7  8  9 10 11 12
Selected:    B  B  A  C  C  B  B  B  A  C  A  B
~~~

`B` being selected multiple times consecutively is normal. Random **has no rule** saying “since B was just selected, the next turn cannot select B”. As long as the candidate set and probability distribution remain unchanged, the probability of the next turn selecting B again is still `1/3`, regardless of who was selected previously.

Distinguish two statements:

1. **True:** each instance has an equal chance in a single selection turn when the input list consists of distinct, unweighted candidates.
2. **False:** after three requests, the three instances are guaranteed to have received exactly one request each.

The Random algorithm makes no guarantee of exact distribution within short windows.

## 4. Distribution over many requests: expectation and variance

Suppose there are `N` independent selections, the list stays the same, and the probability of one instance is `p = 1/n`. The number of times that instance is selected is a binomial random variable:

\[
X_i \sim \operatorname{Binomial}(N,p)
\]

Expectation and standard deviation:

\[
E[X_i]=Np=\frac{N}{n}
\]

\[
\sigma_i=\sqrt{Np(1-p)}
\]

For example, with three instances, sending 3,000 requests where **each request produces exactly one selection**:

- Each instance is expected to receive 1,000 selections.
- The standard deviation of the selection count for one instance is about 25.8.
- Under the binomial model assumption, an approximate 95% interval **for a single instance** is roughly 949–1,051 selections (mean ±1.96 standard deviations).

This does not mean the counts of all three instances simultaneously fall within this interval with exactly 95% probability; the counters are correlated because their sum is always 3,000. Nor is this a hard bound guaranteed by the system.

As the number of requests grows, the **proportion** tends to approach `1/n`, but the **absolute difference** between counters can still grow on the order of the square root of `N`. For instance, 10,000 requests are not guaranteed to yield an exact 5,000/5,000 split in a two-instance system.

You can observe the following cases:

| Requests | Two instances, expected per side | What to understand |
|---:|---:|---|
| 10 | 5 | 7–3 or 8–2 can still happen |
| 100 | 50 | Differences of a few to over ten turns can occur |
| 1,000 | 500 | Proportions are usually steadier than a sample of 10 |
| 10,000 | 5,000 | Percentage deviation is usually small, still not exact |

If you evaluate Random using only 5–10 requests, it is easy to mistake natural variance for a misconfiguration. Observe a sufficiently large number of calls while verifying that the instance list is stable.

## 5. How do Random and Round Robin differ?

By default, Spring Cloud LoadBalancer typically uses `RoundRobinLoadBalancer`. You can switch to `RandomLoadBalancer` through client-specific configuration.

| Criterion | Round Robin | Random |
|---|---|---|
| Selection method | Moves through the list by a circular index | Picks a random index in the list |
| Selection state | Maintains position/counter to determine the next turn | No circular pointer needed between turns |
| First 3 selections, 3 stable instances | Usually hits each instance once if the sequence starts at the corresponding position | All three turns can hit the same instance |
| Balance in short windows | Usually more even if order/list is stable | Can skew noticeably |
| Under many requests | Relatively even distribution by selection count | Even distribution by statistical expectation |
| Incidents / actual load | Not inherently aware of latency or CPU from the algorithm name | Not inherently aware of latency or CPU from the algorithm name |
| Suitable when | Predictable alternation is desired | Simple, non-sequential distribution is desired |

Neither algorithm should be viewed as universally better. If the goal is a nearly even distribution **by request count over short windows**, Round Robin is usually easier to observe. If variance is acceptable and avoiding cyclic order dependency is desired, Random is a reasonable choice.

Neither equates to **least connections**, **least response time**, **weighted**, **consistent hashing**, or **sticky session**. To account for differing replica capacities, design an appropriate supplier chain/strategy.

## 6. Where does Random sit in the supplier chain?

Random only chooses from the candidate set returned by `ServiceInstanceListSupplier`. Before the Random step, the list may have been affected by discovery, caching, health checks, zone preference, or hints.

~~~mermaid
flowchart LR
    D["DiscoveryClient"] --> C["Instance list cache (if enabled)"]
    C --> H["Health / zone / hint filtering (if configured)"]
    H --> L["Effective candidate list"]
    L --> R["RandomLoadBalancer"]
    R --> I["Selected ServiceInstance"]
    I --> T["RestClient / WebClient / OpenFeign"]
~~~

For example, discovery initially sees:

~~~text
[A, B, C, D]
~~~

If zone preference leaves only `[A, C]`, Random chooses evenly between A and C rather than all four. If health check removes C and the list becomes `[A]`, every selection goes to A. If a filter finds no matching candidates and falls back to the original set, behavior depends on that supplier's fallback rules.

**Do not equate the registered list with the eligible selection list.** When request counts appear unevenly distributed, check the actual instance set received by LoadBalancer and its filters before concluding Random is broken.

Also note: the uniform `1/n` property applies to **elements in the input list**. If a supplier intentionally returns multiple copies of the same instance or applies weights, the probability per *logical instance* can change. That is an effect of the supplier, not Random reading CPU or metadata on its own.

## 7. Enabling Random for a specific service ID

The default configuration is usually Round Robin. There is no standard global property like `spring.cloud.loadbalancer.strategy=random` that automatically changes the algorithm for every service. The approach documented by Spring Cloud is to register a dedicated `ReactorLoadBalancer<ServiceInstance>` via `@LoadBalancerClient`.

Suppose the caller application has root package `com.example.caller`. Place the Random configuration in a package **outside the caller's component scan scope**, for example `com.example.lbconfig`.

Main application class:

~~~java
package com.example.caller;

import com.example.lbconfig.InventoryRandomLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryRandomLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Random configuration per client ID:

~~~java
package com.example.lbconfig;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

public class InventoryRandomLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryRandomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId = environment.getRequiredProperty(
                LoadBalancerClientFactory.PROPERTY_NAME
        );

        return new RandomLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class
                ),
                serviceId
        );
    }
}
~~~

Explanation of components:

- `@LoadBalancerClient(name = "inventory-service")` binds the configuration to that exact service ID.
- `LoadBalancerClientFactory` manages the contexts and LoadBalancer beans for each service ID.
- `LoadBalancerClientFactory.PROPERTY_NAME` provides the service ID name of the context being created.
- `getLazyProvider(serviceId, ServiceInstanceListSupplier.class)` supplies the corresponding supplier for that service.
- `RandomLoadBalancer` selects an instance from the list returned by the supplier.
- `ReactorLoadBalancer<ServiceInstance>` is the common selector interface; `Reactor` in the interface name does not mean the application can only use WebClient.

**The component scan boundary is important:** if `InventoryRandomLoadBalancerConfiguration` is scanned into the main ApplicationContext as a regular `@Configuration`, the Random bean can leak beyond the intended service ID. You can omit `@Configuration` on the configuration class as shown in the example, or place a `@Configuration`-annotated class outside the scan scope and reference it solely via `@LoadBalancerClient`.

The configuration above only changes the **instance selection** algorithm for `inventory-service`. If the caller also invokes `payment-service` without a custom configuration, payment continues using its default algorithm (usually Round Robin).

## 8. Creating an instance list to test Random locally

To verify Random, the caller needs multiple instances under the same service ID. You can use `SimpleDiscoveryClient` to declare a static list without needing Eureka or Consul.

Caller dependencies, managed with compatible Spring Boot and Spring Cloud BOM versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Caller-side `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083
~~~

Two details to verify:

1. The key `inventory-service` must match the name in `@LoadBalancerClient` and the logical hostname of the request.
2. All three URIs must actually have an inventory process listening. A static list does not automatically remove a stopped port.

On the target service, provide an instance identification endpoint, for example:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoAmI() {
        return Map.of(
                "serviceId", "inventory-service",
                "instance", "inventory:" +
                        environment.getProperty("server.port", "8081")
        );
    }
}
~~~

Run **the same inventory source code** as three processes with `--server.port=8081`, `--server.port=8082`, and `--server.port=8083`. The caller runs on port 8080. Each process needs its own Spring Boot application for the endpoint above to operate.

## 9. Testing calls with a load-balanced RestClient

Define a `RestClient.Builder` bean integrated with LoadBalancer:

~~~java
package com.example.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Create an endpoint that forwards a call to inventory:

~~~java
package com.example.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {

    private final RestClient inventoryClient;

    public ProxyController(@LoadBalanced RestClient.Builder builder) {
        this.inventoryClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @GetMapping("/proxy/whoami")
    public InstanceResponse whoAmI() {
        return inventoryClient.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceResponse.class);
    }

    public record InstanceResponse(
            String serviceId,
            String instance
    ) {
    }
}
~~~

When calling `GET http://localhost:8080/proxy/whoami`, RestClient receives the logical URI, Spring Cloud LoadBalancer selects a `ServiceInstance` using Random, and then sends the request to one of the ports 8081/8082/8083. The `instance` field in the response is used to verify the actual instance.

With a `@LoadBalanced`-annotated WebClient or OpenFeign using service ID `inventory-service`, the selector in this service's dedicated context is still Random. **The target selection algorithm does not dictate whether the HTTP client operates in blocking or non-blocking mode.** RestClient typically uses blocking calls, WebClient supports reactive pipelines, and OpenFeign is a declarative call interface.

## 10. Hands-on observation of a random sequence

In PowerShell, invoke 15 times to inspect the sequence:

~~~powershell
1..15 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/whoami").instance
}
~~~

An **illustrative** output example, not a fixed order:

~~~text
inventory:8082
inventory:8082
inventory:8081
inventory:8083
inventory:8083
inventory:8081
inventory:8082
inventory:8083
inventory:8081
inventory:8081
inventory:8082
inventory:8082
inventory:8083
inventory:8081
inventory:8082
~~~

Do not write tests expecting this fixed sequence. Random can produce many different sequences even when code and configuration stay identical.

To observe the distribution over 900 requests:

~~~powershell
$selected = 1..900 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/proxy/whoami").instance
}

$selected |
    Group-Object |
    Sort-Object Name |
    Select-Object Name, Count
~~~

An example output:

~~~text
Name             Count
----             -----
inventory:8081     309
inventory:8082     286
inventory:8083     305
~~~

The three counters add up to 900. If the instances each have probability 1/3, the expectation is 300 turns each, though hitting exactly 300 across all three is not guaranteed. Each instance's selection count fluctuates randomly; a sample of 900 is generally enough to spot the trend, though not enough to prove absolute configuration accuracy.

If you want to estimate proportions, use:

~~~powershell
$total = $selected.Count

$selected |
    Group-Object |
    Sort-Object Name |
    ForEach-Object {
        [pscustomobject]@{
            Instance = $_.Name
            Requests = $_.Count
            Percent  = [math]::Round(100 * $_.Count / $total, 2)
        }
    }
~~~

For meaningful testing, record successful requests, failures, retry counts, and the available instance list throughout the test. Do not silently drop failed requests from the sample and conclude the selector balances evenly.

## 11. Factors that make actual distribution differ from theory

The uniform distribution assumption is only approximate under conditions where the candidate list is stable, each instance appears once, and each request gets one independent selection. The following factors can change what you observe:

| Factor | Impact |
|---|---|
| Discovery refreshes list | Number of candidates `n` changes over time |
| Instance list cache | Some instance changes do not appear immediately at the caller |
| Health check | Unhealthy instances can be filtered out before Random selects |
| Zone/hint filtering | Only instances matching criteria enter the selection pool |
| Retry | One business request can generate multiple selections/HTTP dispatches |
| Heterogeneous backends | Random does not auto-adjust based on CPU or response time |
| Client and server timeouts | Completed request count differs from selection count |
| Multiple callers | Each caller has its own context/selector; system-wide stats must aggregate multiple sources |
| Sticky session or infrastructure-layer routing | Can alter the final backend compared to what the client thinks it is calling |

For example, instances A, B, and C are all registered, but B has died while the static list has not been updated. Random can still pick B and cause connection errors. **Random is not a health check**. To filter out B, a discovery/health-check supplier or another operational mechanism is needed to update the candidate set.

On the other hand, if infrastructure already provides a load-balancing VIP behind a single `ServiceInstance`, Random on the Spring Cloud side only sees that VIP. It does not directly select the replicas behind the VIP. When designing multi-tier load balancing, clearly identify which tier selects instances and which tier distributes traffic to actual backends.

## 12. Retries, timeouts, and continuing to select failing instances

Spring Cloud LoadBalancer selects the instance; the HTTP client is responsible for connecting and sending the request. If the selected instance returns an error or times out, retrying depends on retry configuration in Spring Cloud LoadBalancer, RestClient/WebClient, OpenFeign, or other resilience libraries.

Do not assume Random remembers the instance that just failed to avoid it on the next turn. Under the pure algorithm, if the list is still [A, B, C], the probability of selecting B again on the next turn remains 1/3.

Spring Cloud has supporting components for retries, such as `RetryAwareServiceInstanceListSupplier` when configured properly, to help avoid the instance that just failed during a retry attempt. Exact rules depend on the retry mechanism, the `spring.cloud.loadbalancer.retry.avoid-previous-instance` property, and whether enough instances remain in the list.

Example flow:

~~~mermaid
sequenceDiagram
    participant U as Client
    participant L as RandomLoadBalancer
    participant A as inventory A
    participant B as inventory B

    U->>L: Selection for HTTP GET
    L-->>U: Selects inventory A
    U->>A: GET /whoami
    A--xU: Connection error / timeout
    Note over U: Retry only if configured and eligible
    U->>L: Selection for retry attempt
    L-->>U: May select B or another candidate
    U->>B: GET /whoami
    B-->>U: 200 OK
~~~

The diagram illustrates the possibility of selecting B on retry, without claiming that every error is retried or that a retry always picks a different instance. For write operations like a payment creation POST, ensure idempotency before enabling retries to avoid executing business logic twice.

Connection/response read timeouts must be configured on the appropriate HTTP transport or HTTP client. There is no Random property that automatically caps total request duration. Retries and backoff can increase total processing time significantly; set a deadline aligned with business requirements.

## 13. Is Random suitable when instances have different capacities?

Suppose:

- Instance A has 4 CPUs.
- Instance B has 1 CPU.
- Both serve the same API, but their maximum capacities are unequal.

Uniform Random will select A and B roughly 50/50 by count, even though B can handle less load. If requests have similar cost, B risks overloading before A.

You can use **weighted load balancing** when weighted distribution is desired. Spring Cloud provides `WeightedServiceInstanceListSupplier`; with `weight` metadata or a custom `WeightFunction`, the supplier can influence the candidate list passed to the selector.

If you want 80% of requests to go to A and 20% to B, you need a clearly designed and tested weighted policy. You cannot expect pure `RandomLoadBalancer` to infer an 80/20 ratio from CPU.

Other requirements may call for dedicated strategies:

- **Affinity/sticky session:** users need to keep reaching the same backend.
- **Locality/zone preference:** prefer instances in a zone near the caller.
- **Least connections or latency-aware:** avoid busy instances.
- **Canary rollout:** send only a fraction of requests to the new version, potentially based on metadata and policy.
- **Idempotent retry:** avoid the previously failed instance when conditions permit.

Choose Random when replicas are relatively homogeneous, short-term variance is acceptable, and there are no special affinity or routing requirements.

## 14. How to test Random meaningfully

Do not write unit tests that only assert `RandomLoadBalancer` returns a specific fixed sequence. Random does not promise a fixed order. Instead, test at two levels:

**Functional level:** With a list containing a single instance, verify the selection returns that exact instance. With an empty list, verify the system signals no instance is available and the client handles it appropriately. With multiple instances, verify the result always belongs to the candidate set.

**Integration level:** With multiple real instances, send enough HTTP requests and tally which instances handled them. Observe proportions over a longer window while confirming no filter/retry alters the selection set.

For statistical tests, use a precalculated allowable tolerance and avoid overly tight thresholds that cause flaky tests. For example, with three instances and 900 independent selections, one instance has an expected count of 300 and a standard deviation of about 14.1; a difference of a few dozen turns is not enough to conclude a bug. Combining statistics with checks on **selector configuration** and the **candidate list** is more reliable than looking at just a handful of requests.

If testing a custom algorithm requires strict reproducibility, design the algorithm to accept an injected random source or isolate the index-selection step for separate testing. Standard `RandomLoadBalancer` is intended for runtime selection; do not assume a fixed random seed can be set through ordinary configuration.

## 15. Observability and troubleshooting

When proving the Random algorithm is active, collect at least three groups of data:

1. **Caller layer:** service ID, call timestamp, status, retry count, request correlation ID.
2. **LoadBalancer layer:** available instance set, selected instance if appropriate logging/tracing is present, lifecycle metrics.
3. **Backend layer:** actual instance ID receiving the request, response time, CPU, connection count, and error rate.

Spring Cloud LoadBalancer can integrate Micrometer lifecycle statistics when a registry is present and `spring.cloud.loadbalancer.stats.micrometer.enabled` is turned on. Use an appropriate Actuator/metrics exporter and check the documentation for your Spring Cloud version.

A quick diagnostic table:

| Symptom | What to check |
|---|---|
| Always selects one instance | Does the candidate list truly contain more than one? Is a filter or discovery cache holding only one replica? |
| Rigidly alternating results | Client may still be using Round Robin; inspect `@LoadBalancerClient` and configuration class placement |
| Multiple consecutive requests hit the same replica | May simply be a valid Random streak; increase sample size and measure ratios |
| Requests fail despite healthy instances | Is the failing instance still in the supplier? Are retries/health checks configured properly? |
| Backend stats don't match caller counters | Retries, gateway/VIP, sticky routing, or failed requests can cause counters to diverge |
| Random applies to other services too | Was the custom LoadBalancer configuration picked up by component scan into the main context? |
| Ratio still heavily skewed over long runs | Check instance set, weights, filters, backend capacity, errors, retries, and sampling method |

## 16. Pre-use checklist

- [ ] Identify the service ID called by the caller and the `ServiceInstance` list provided by discovery.
- [ ] Distinguish the instance selection algorithm from filtering steps such as caching, health checks, zones, or hints.
- [ ] Know that Round Robin is the default; if Random is desired, configure `RandomLoadBalancer` explicitly.
- [ ] Register the algorithm per service with `@LoadBalancerClient` and place the configuration class outside general component scan scope.
- [ ] Use a LoadBalancer-integrated RestClient/WebClient/OpenFeign and a service ID URL.
- [ ] Do not expect Random to alternate strictly in cycles or guarantee equal request counts per instance in short windows.
- [ ] With `N` requests and `n` stable candidates, use expectation `N/n` and account for probabilistic variance.
- [ ] Monitor the actual backend receiving requests instead of only observing the logical URI at the caller.
- [ ] Configure health checks, retries, timeouts, and circuit breakers at the appropriate layers if fault tolerance is needed.
- [ ] If replicas differ in capacity or stickiness is needed, consider weighted/affinity strategies.
- [ ] After changing configuration, verify inventory individually without unintentionally affecting other service IDs.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): guide for switching from Round Robin to `RandomLoadBalancer` with `@LoadBalancerClient`, HTTP client integration, suppliers, and metrics.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): reference for LoadBalancer, retry, and observability configuration properties by version.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): service discovery and retry abstractions.

Random in Spring Cloud LoadBalancer picks **a random element from the eligible instance list** on each selection. When instances have equal chance and the list stays unchanged, selection counts tend toward an even distribution over the long run, though there is no guarantee of order or evenness within small batches of requests. Understanding probability, the supplier pipeline, and the boundary between selection, connection, and retry lets you evaluate Random by its actual behavior rather than expecting it to alternate like Round Robin.
