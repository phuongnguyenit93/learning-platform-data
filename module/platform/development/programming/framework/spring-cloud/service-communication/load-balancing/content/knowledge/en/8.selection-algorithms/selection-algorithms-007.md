# Weights in replica selection and metadata sources

When replicas of a service have different processing capacities, splitting requests evenly by instance count may not be appropriate. A replica running on a larger machine can process more requests than a CPU-constrained replica; a canary version should only receive a small fraction of traffic during testing. **Weight** represents the relative priority of each `ServiceInstance` during target selection.

This lesson belongs to the **Selection Algorithms** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module aims to explain Spring Cloud LoadBalancer's client-side load balancing: selecting a `ServiceInstance` by service ID, discovery, health checks, and routing policies; while practicing `RestClient`, `WebClient`, OpenFeign, retries/timeouts, and error observability. In this lesson, we focus on two questions: **how weights affect selection probability** and **where weights come from in instance metadata**.

After studying this lesson, you will be able to explain weighted traffic distribution ratios, attach `weight` metadata to each replica, construct a weight-aware supplier chain, verify that metadata actually reaches LoadBalancer, design distribution measurements, and recognize cases where actual results differ from expectations.

## 1. Why are weights needed?

Suppose `inventory-service` has three instances:

| Instance | Address | Relative processing capability | Weight |
|---|---|---|---:|
| `inv-a` | `localhost:8081` | Large machine, more CPUs | 5 |
| `inv-b` | `localhost:8082` | Medium machine | 3 |
| `inv-c` | `localhost:8083` | Small machine or canary | 2 |

If the selector splits evenly across all three instances, each replica receives roughly one-third of requests regardless of actual capacity. With weights `5:3:2`, the relative distribution target is close to `50%:30%:20%` when all three instances are available and no other filtering policy applies.

The target share for an instance `i` can be expressed as:

\[
p_i = \frac{w_i}{\sum_{j=1}^{n}w_j}
\]

Where `w_i` is the positive weight of instance `i`, and the denominator is the sum of weights of **instances still remaining in the candidate set** at selection time.

With `w_A=5`, `w_B=3`, `w_C=2`:

- Total weight: `5 + 3 + 2 = 10`.
- `A`: `5 / 10 = 50%`.
- `B`: `3 / 10 = 30%`.
- `C`: `2 / 10 = 20%`.

This is an **expected ratio** calculation, not an exact guarantee for every batch of 10 requests. Actual outcomes depend on the selection algorithm, call volume, instance list churn, caching, health checks, retries, and other proxy layers.

## 2. Where do weights take effect in Spring Cloud LoadBalancer?

A client calls by service ID, such as `http://inventory-service`. Spring Cloud LoadBalancer fetches the `ServiceInstance` list via `ServiceInstanceListSupplier`, then a selector such as `RoundRobinLoadBalancer` uses the candidate list to pick an address.

~~~mermaid
flowchart LR
    A["RestClient / WebClient / OpenFeign"] --> B["Per-service-ID LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["Discovery + metadata"]
    D --> E["Instance list with weight"]
    E --> F["Weight-supporting layer"]
    F --> G["Effective candidate list/selection odds"]
    G --> H["Instance selector"]
    H --> I["HTTP to selected instance"]
~~~

In Spring Cloud LoadBalancer, `WeightedServiceInstanceListSupplier` is a component supporting weight-based selection. It can participate in the supplier chain to reflect weights in the candidate set used by the selection algorithm.

Three roles must be distinguished:

1. **Discovery** locates replicas by service ID and provides metadata.
2. **Supplier chain** supplies or transforms the candidate list, including weighting policies and any configured filters.
3. **Instance selector** chooses a `ServiceInstance` to send the request to.

Merely adding `weight` metadata to the registry is **not enough** for every LoadBalancer configuration to automatically distribute by weight. The caller must also use a weight-aware supplier or selection mechanism. Conversely, enabling a weighted supplier without properly providing metadata can leave instances using the default weight.

## 3. `ServiceInstance` metadata as the source of weights

`ServiceInstance` can expose map-based metadata via `getMetadata()`. Metadata typically contains string key-value pairs mapped by the discovery client or instance provider.

Example of an instance as seen from the caller:

~~~text
serviceId = inventory-service
instanceId = inv-a
host = localhost
port = 8081
metadata = {
    "weight": "5",
    "zone": "zone-a",
    "version": "v1"
}
~~~

In Spring Cloud LoadBalancer's default weighting mechanism, the metadata key commonly used is `weight`. Any instance without a declared weight uses a **default weight of 1**. Metadata values are strings, so place content in the format supported by the weight-reading mechanism of the version in use.

A clean data convention is:

| Attribute | Example | Purpose |
|---|---|---|
| `weight` | `"5"` | Relative priority when distributing requests |
| `zone` | `"zone-a"` | Locality hint for applying zone preference |
| `version` | `"v1"` | Marks serving or deployment version |
| `trafficTier` | `"stable"` | Supports canary/stable filtering policies if present |

Do not use these attributes interchangeably. `zone` identifies location, `version` indicates version, and `weight` describes relative distribution share. Weights are not automatically derived from CPU count, RAM usage, HTTP latency, or health scores unless the application actively implements a mechanism to compute and update that value.

### Common metadata sources

Metadata can originate from several places:

- **Dynamic registry**: Eureka, Consul, or another discovery implementation receives service metadata upon registration and populates `ServiceInstance`.
- **Static configuration**: `SimpleDiscoveryClient` constructs instances and metadata from the caller's `application.yml`.
- **Deployment platform**: the corresponding discovery client may map platform labels/annotations/tags into metadata, depending on the library and configuration.
- **Custom supplier**: constructs `ServiceInstance` directly or provides a weighting mechanism from an internal management source.

The critical point is that the weight must appear in the **metadata that the calling application actually receives**. A field in server config, a response body, or a deployment tag does not automatically become `ServiceInstance` metadata unless the discovery adapter propagates it.

## 4. Static source example with `SimpleDiscoveryClient`

In a local environment, three replicas of `inventory-service` can be declared using `SimpleDiscoveryClient`. Example configuration placed in the **caller** application:

~~~yaml
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
                metadata:
                  weight: "5"
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  weight: "3"
                  zone: zone-a
              - uri: http://localhost:8083
                metadata:
                  weight: "2"
                  zone: zone-b
~~~

Ports `8081`, `8082`, and `8083` represent three separate target service processes. Each process should have a diagnostic endpoint `GET /internal/instance` returning its own identifier to observe request routing.

The configuration above only creates a static discovery list. It does not start the three servers, automatically drop a server that just stopped, or guarantee a dynamic registry is used if the application has another discovery mechanism installed. For local examples, verify each endpoint directly before measuring distribution via LoadBalancer.

The advantage of a static source is easy input control for testing. The disadvantage is that changing instances or metadata usually requires updating application configuration rather than automatic registry synchronization.

## 5. Reading weights from a dynamic registry

In an environment with Eureka, each replica can declare its weight via registration metadata. Example on an `inventory-service` instance:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      weight: "5"
      zone: zone-a
~~~

The second replica can set `weight: "3"`, and the third `weight: "2"`. This is an **Eureka-specific** example; it only takes effect when the application has Eureka Discovery Client integrated and the instance registers successfully.

Other registries use their own metadata configuration. For example, with Consul or Kubernetes platforms, do not copy the `eureka.instance.metadata-map` key assuming the client will understand it. Use the configuration supported by that discovery implementation and verify metadata after it is mapped into `ServiceInstance`.

Important steps when the metadata source is a registry:

1. Ensure replicas register under the same service ID but have distinct instance IDs and addresses.
2. Set weight metadata on each instance using a consistent key-value convention.
3. Verify the registry stored the right value for each replica.
4. Verify `ServiceInstance.getMetadata()` on the caller side contains the `weight` key with the expected value.
5. Observe propagation delay when changing weights; re-registration, discovery sync, or caching can prevent updates from taking effect immediately.

Do not assume that merely editing a YAML file on a running instance causes all callers to immediately see the new weight. Consider the refresh and registration mechanisms of the actual environment.

## 6. Enabling weighted selection with the supplier builder

Configure a dedicated `ServiceInstanceListSupplier` for `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryWeightedLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withWeighted()
                .build(context);
    }
}
~~~

Meaning:

- `withDiscoveryClient()`: builds the list source from the discovery client.
- `withCaching()`: caches the source list to reduce repeated discovery queries.
- `withWeighted()`: adds weight handling based on instance information.
- `build(context)`: finalizes the chain for the context being configured.

Register the configuration with the **target service ID**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryWeightedLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

The `InventoryWeightedLoadBalancerConfiguration` class should be placed outside the application's general component scan scope (or excluded from scanning) so the supplier bean only appears inside the corresponding LoadBalancer context. For example, place the application in `com.example.order` and the custom configuration in `com.example.loadbalancer.inventory`.

The code examples assume a compatible Spring Boot/Spring Cloud line supporting the builder and weighted supplier. When implementing on a specific version, confirm dependency versions and available builder APIs. Do not create multiple competing supplier beans for the same service ID; a single chain with its source and steps defined suffices.

## 7. How weights interact with Round Robin, Random, and the candidate list

Weight is not a standalone command saying “for every 10 requests, A gets 5, B gets 3, C gets 2”. Instead, it alters selection chances across instances according to the configured weighting mechanism.

| Approach | Input | How to interpret results |
|---|---|---|
| Standard Round Robin | Three instances with equal priority | Generally moves toward alternating candidates |
| Standard Random | Three instances with equal priority | Picks a random candidate each time |
| Weighted supplier combined with selector | Three instances with `weight=5,3,2` | Moves toward weighted relative distribution absent other filters or errors |
| Zone filtering before weighting | Only instances in valid zones remain | Weights only matter within the remaining candidate set |

For example, zone preference keeps only `inv-a` and `inv-b`, with weights `5` and `3` respectively. When `inv-c` is excluded from the candidate set, target shares are now based on sum `5+3=8`: roughly `62.5%` for A and `37.5%` for B, **no longer 50%-30%-20%**.

If only one valid candidate exists, it is the sole choice regardless of weight. If the list is empty, LoadBalancer has no target to call. If an unhealthy instance is removed, its weight stops participating in distribution until the instance returns to the candidate set.

### Canary version scenario

Suppose two replicas run the stable release and one runs canary:

~~~text
stable-A weight=9
stable-B weight=9
canary-C weight=2
~~~

If all three are candidates, canary targets roughly `2/(9+9+2) = 10%`. This helps load-test with limited blast radius. However, weight only adjusts request distribution; it does not automatically guarantee data isolation, user-specific routing, session stability, or rollback capability. For a canary needing strict constraints, additionally design routing policies, observability, and rollout abort conditions.

## 8. Combining a weighted supplier with caching, health checks, and zones

In real applications, the supplier chain can have multiple stages. Ordering matters greatly because stages can transform the candidate set:

~~~text
Discovery source
     |
     v
Caching / Health check (as designed)
     |
     v
Zone or metadata filter
     |
     v
Weighted supplier
     |
     v
LoadBalancer selects instance
~~~

This diagram illustrates responsibilities and data relationships; it does not assert every version always builds the chain in the exact order shown. With the builder, verify the actual decorator order and compatibility.

Several design principles:

- **Cache close to the discovery source.** Caching the registry list reduces lookup overhead; avoid accidentally caching request-dependent results without an appropriate cache key.
- **Health checks reflect serving capability.** A high weight cannot make a dead instance succeed on requests. Use discovery status, a health-check supplier, or unhealthy instance eviction.
- **Filter by zone and metadata before final share ratios.** Total weight must be based on the eligible candidate set after filtering policies.
- **Never substitute weight for timeout.** Low-weight instances can still be slow or time out; configure timeouts per HTTP communication channel.
- **Never use weight to guarantee session stickiness.** Sticky sessions or per-user consistency require dedicated policies.
- **Never treat weight as a hard concurrency cap.** A high-weight replica can still overload if work costs are uneven.

If an application needs health, zones, and weights together, do not assemble steps by guesswork. Identify which supplier builds the base list, which reads cache, which filters instances, and which alters selection chances; then test both the exact list and output distribution.

## 9. Calling via RestClient and observing replica identities

On the caller, configure a LoadBalancer-integrated `RestClient.Builder`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Create a minimal diagnostic response type:

~~~java
public record InstanceResponse(
        String serviceId,
        String instanceId
) {}
~~~

Example performing multiple calls and tallying counts received by each instance:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class WeightedDistributionProbe {

    private final RestClient client;

    public WeightedDistributionProbe(
            @LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }

    public Map<String, Integer> collect(int requests) {
        Map<String, Integer> counts = new HashMap<>();

        for (int i = 0; i < requests; i++) {
            InstanceResponse response = client.get()
                    .uri("http://inventory-service/internal/instance")
                    .retrieve()
                    .body(InstanceResponse.class);

            if (response != null) {
                counts.merge(response.instanceId(), 1, Integer::sum);
            }
        }

        return counts;
    }
}
~~~

Each `inventory-service` replica must return its own `instanceId` at `/internal/instance`. That lets the caller see which instance actually served the request instead of only knowing the logical address.

Example with `1,000` successful requests in an illustrative run:

~~~text
inv-a: 506
inv-b: 294
inv-c: 200
~~~

These numbers are **hypothetical data only** to illustrate reading results. Do not treat them as real execution output of the code or as guaranteed ratios. Re-running may yield different numbers depending on selection behavior and system state.

With `WebClient` or OpenFeign configured with Spring Cloud LoadBalancer, the observation principle is identical: call the service's logical hostname, read the instance ID in the response, and tally counts. The weighted supplier remains inside the target service ID's LoadBalancer context.

## 10. How to evaluate distribution ratios properly

Evaluating weights by request count must account for measurement conditions. A sound test should:

1. Start all replicas and verify the diagnostic endpoint works when called directly.
2. Confirm the caller uses a weight-supporting supplier for the right service ID.
3. Inspect `ServiceInstance.getMetadata()` on each instance to verify expected `weight` values.
4. Send a sufficiently large number of requests through the same LoadBalancer mechanism; exclude startup periods or moments when the list is still changing.
5. Record total calls, successes, errors, and retries per instance if observable.
6. Compare ratios over a clearly defined request set, then cross-check against health, zone, cache, and retry status.

Observed share formula:

\[
\hat p_i = \frac{N_i}{\sum_j N_j}
\]

Where `N_i` is the count for instance `i` **using the same counting method**. If you only count successful responses, proportions can differ from instance selection proportions whenever one replica fails frequently. When retries are active, one logical request can generate multiple HTTP attempts and hit multiple instances.

Do not write brittle tests requiring an exact `500/300/200` split after `1,000` requests. Instead, unit tests should verify metadata parsing and weight interpretation; integration tests should verify distribution falls within an acceptable tolerance under controlled test conditions. Acceptable tolerances must be set based on requirements and the properties of the active algorithm.

## 11. What happens when weights are missing, invalid, or change?

These situations require consistent policies:

| Situation | What to check |
|---|---|
| Missing `weight` metadata | Default mechanism usually uses weight 1; confirm version and received data. |
| Non-numeric `weight` value | Check how the supplier handles it; normalize metadata and catch early at deploy time. |
| Zero or negative weight | Do not assume it means “disable instance”; pick positive valid values and verify behavior on your version. |
| Very large weight compared to other instances | That instance may receive most traffic; evaluate capacity and measurement error. |
| Registry just updated weights | May need to wait for registration/discovery refresh and cache TTL. |
| An instance stops working | Ensure discovery/health removes or marks the instance to avoid continuing to send failing requests. |
| Metadata key casing mismatch | Standardize exact `weight` key name and inspect the caller-side map. |
| Only caller A has weighted supplier | Caller B may still distribute differently even when calling the same service ID. |

Declared weights should be simple positive integers such as `1`, `2`, `5`; avoid relying on undocumented behavior for empty values, negative numbers, or decimals.

### Updating weights at runtime

A plan to shift weights from `5:3:2` to `3:3:4` might serve an experiment sending more traffic to the third replica. Update sequencing matters:

- Update metadata via the mechanism supported by the registry.
- Wait for the registry to reflect the new data and callers to refresh lists past cache TTL.
- Verify all relevant callers have applied the corresponding policy.
- Read actual distribution along with errors and latency.
- Keep a plan to restore old weights if the replica receiving extra traffic fails to keep up.

Because each caller can have different caches and discovery intervals, transitions are rarely synchronized everywhere instantaneously.

## 12. Weight is not an automatic load controller

Weight is a **relative** configuration; it does not directly measure active requests or current latency. Setting `weight=5` on a replica does not mean that replica is guaranteed to serve five times faster than a `weight=1` replica. Actual capacity also depends on request size, data, CPU, I/O, connection pools, and downstream dependencies.

Several operational principles:

- Measure throughput, latency, error rate, saturation, and resource limits before setting weights.
- Avoid raising weights across multiple instances simultaneously if a downstream system remains the bottleneck.
- Do not treat weight as a rate limiter, circuit breaker, or timeout.
- With heterogeneous request processing costs, request-count distribution may not equal CPU or processing-time distribution.
- When traffic is session-bound, sticky routing can affect observed ratios.
- When retries exist, separate initial calls from total attempts to assess weight impact.
- For canary rollouts, pair weights with error/latency metrics, version tracking, and rollback capability.

If you want weights to self-adjust from real-time load metrics, that is an additional control loop requiring design, noise filtering, and oscillation damping. Do not assume the default weighted supplier alters weights automatically based on CPU or latency.

## 13. Troubleshooting diagram when distribution misses expectations

~~~mermaid
flowchart TD
    A["Instance ratio differs from expected weight ratio"] --> B{"Is caller using weighted supplier?"}
    B -- "No" --> C["Check beans and @LoadBalancerClient per service ID"]
    B -- "Yes" --> D{"Did weight metadata reach caller?"}
    D -- "No" --> E["Check registry, weight key, refresh, cache"]
    D -- "Yes" --> F{"Does candidate set contain all replicas?"}
    F -- "No" --> G["Check health, zone, hint, and filters"]
    F -- "Yes" --> H{"Are there retries/errors or other proxies?"}
    H -- "Yes" --> I["Correlate attempts, responses, errors, and proxies"]
    H -- "No" --> J["Increase sample size, verify algorithm and measurement"]
~~~

Real investigation example: `inv-a` declares weight 5 but returns only 10% of successful responses. It might be failing heavily, excluded by health checks, or callers might be reading stale discovery data. Looking only at successful responses and immediately raising weight can worsen overload. Check instance selection counts, attempts, error rates, and cache refresh timestamps.

For hard-to-reproduce issues, logs should capture service ID, selected instance ID, deployment version, candidate count, and error status. Avoid logging raw sensitive payloads. For metrics, control label cardinality; never create unbounded labels varying per request.

## 14. Lab completion checklist

| Check | Expected outcome |
|---|---|
| Service discovery | `inventory-service` has three valid instances |
| Metadata | Three instances carry weights `5`, `3`, `2` respectively |
| Supplier chain | Caller includes `withWeighted()` for the right service ID |
| Client | HTTP client is integrated with LoadBalancer and calls by service ID |
| Diagnostic endpoint | Each replica returns its own instance ID |
| Distribution | After enough requests, traffic tends toward target ratios under stable conditions |
| Instance filtering | Instances excluded by health/zone no longer contribute to total weight |
| Refresh | Weight changes are reflected after the appropriate discovery/cache cycle |
| Retry/timeout | Error handling configured; attempt counts distinguished from logical requests |
| Observability | Ability to correlate selected instance, responses, errors, and latency |

## 15. Key takeaways

- Weight expresses **relative priority** among `ServiceInstance`s, usually passed via `weight` metadata.
- Target ratios are calculated from the weights of the **remaining eligible candidate set**, not all historically registered instances.
- `WeightedServiceInstanceListSupplier` can be composed using `ServiceInstanceListSupplier.builder().withWeighted()`; adding metadata alone without enabling a weight-aware mechanism is insufficient.
- Metadata can originate from `SimpleDiscoveryClient`, dynamic registries, or discovery adapters; what decides behavior is what `ServiceInstance.getMetadata()` exposes on the caller side.
- Caching, health checks, zones, hints, and retries can all affect observed distribution.
- Weights do not guarantee exact ratios on small samples, nor do they replace health checks, timeouts, or CPU-based balancing.
- Measure selections, attempts, successful responses, and errors completely before evaluating a distribution policy.

Understanding weights alongside metadata sources lets you decide which replicas should carry more traffic and verify that policy in inter-service communication using Spring Cloud LoadBalancer.

