# Filtering Instances by Zone with Zone Preference

When a service has multiple instances running across different availability zones, client-side load balancing should not necessarily distribute requests evenly across all instances in the entire region. Cross-zone requests can increase latency, data transfer costs, or dependency on inter-zone network infrastructure. **Zone preference** is a policy that prioritizes selecting instances located in the same zone as the calling application, while still retaining the ability to use another zone when no same-zone instances are found.

In Spring Cloud LoadBalancer, this mechanism is provided by **ZonePreferenceServiceInstanceListSupplier**. It is not an algorithm that replaces Round Robin or Random: it **filters the candidate list first**, and then the LoadBalancer selects an instance from the filtered list.

This lesson focuses on how to attach a zone to a ServiceInstance, how to determine the client's zone, the filtering and fallback mechanism, configuring ServiceInstanceListSupplier, interactions with caching/health checks, and the limitations to be aware of when routing across multiple zones.

## 1. Why Prioritize Same-Zone Instances?

Suppose a retail system has an **Order Service** calling an **Inventory Service**. Each service is deployed across multiple instances in two infrastructure zones:

| Service | Instance | Zone | Sample Address |
| --- | --- | --- | --- |
| Order Service | order-1 | zone-a | 10.10.1.11:8080 |
| Inventory Service | inventory-a1 | zone-a | 10.10.1.21:8080 |
| Inventory Service | inventory-a2 | zone-a | 10.10.1.22:8080 |
| Inventory Service | inventory-b1 | zone-b | 10.10.2.31:8080 |

Without zone filtering, a Round Robin LoadBalancer may route requests from order-1 sequentially to a1, a2, and then b1. When zone preference is enabled and the calling application is configured in **zone-a**, the LoadBalancer prioritizes the set **[a1, a2]**. Instance b1 only returns to the candidate list when no matching zone-a instance exists in the filter's input data.

Potential benefits include:

- **Reduced latency:** network paths within the same zone typically have fewer hops or are better optimized.
- **Reduced cross-zone traffic:** can lower data transfer costs or load on inter-zone links.
- **Optimized locality:** keeps most requests close to the calling application when the system has sufficient capacity in that zone.
- **Increased resilience when local capacity is lacking:** fallback allows trying instances in other zones instead of forcing request rejection.

These are *conditional* benefits, not guarantees. An overloaded same-zone instance can be slower than a cross-zone instance. Zone preference does not measure actual RTT, bandwidth, CPU, connection count, or cost; it uses configured **metadata labels**.

### Zone is not synonymous with region or cluster

Infrastructure terms to distinguish:

| Term | Example | Role |
| --- | --- | --- |
| Region | ap-southeast-1 | Large geographic/infrastructure area |
| Availability zone | zone-a, zone-b | Independent partition within a region or cluster |
| Kubernetes node | worker-01 | Machine running pods; a node may belong to a zone |
| ServiceInstance | inventory-a1 | Application instance with host/port/metadata |
| Client zone | zone-a | The zone the calling application wants to prioritize |

Spring Cloud LoadBalancer does not infer the region from the service ID or IP address. In the basic zone preference mechanism, matching depends on the **client's zone value** and the **instance's zone metadata**.

## 2. Two Required Information Sources: Client Zone and Instance Zone

For filtering to take effect, two questions must be answered:

1. **Which zone does the client want to prioritize?**
2. **Which zone is each ServiceInstance registered under?**

Spring Cloud supports configuring the client's zone with:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

This value is the zone that the **application making the call** uses as the filtering criterion. In environments with multiple replicas of the caller itself, each replica should receive the zone corresponding to where it is deployed, for example via profiles or environment variables.

For discovered instances, ZonePreferenceServiceInstanceListSupplier retrieves the zone from:

~~~java
String instanceZone = serviceInstance.getMetadata().get("zone");
~~~

The metadata of the three instances might look like:

~~~text
inventory-a1  metadata = {"zone": "zone-a", "version": "v2"}
inventory-a2  metadata = {"zone": "zone-a", "version": "v2"}
inventory-b1  metadata = {"zone": "zone-b", "version": "v2"}
~~~

**Note:** the key name must be **zone** in the ServiceInstance metadata map. A value located in a Kubernetes label, a different metadata key, or a registry-specific configuration will not be automatically used by ZonePreference unless the integration maps it to this exact key.

### 2.1. Two Non-Interchangeable Configurations

| Configuration Location | Example | Meaning |
| --- | --- | --- |
| Caller | spring.cloud.loadbalancer.zone=zone-a | Prioritize instances in zone-a |
| Provider (Eureka) | eureka.instance.metadata-map.zone=zone-a | Register instance with zone-a metadata |
| Discovery data | ServiceInstance.getMetadata().get("zone") | The data actually matched by the filter |

If the zone is only configured on the caller while instances lack zone metadata, the filter will **find no same-zone instances** and fall back to the entire list. If the zone is only set on the provider while the caller does not specify a preferred zone, the result is likewise not filtered to a specific zone.

## 3. How Does ZonePreferenceServiceInstanceListSupplier Filter?

The **ZonePreferenceServiceInstanceListSupplier** class belongs to the **org.springframework.cloud.loadbalancer.core** package. It is a decorator of ServiceInstanceListSupplier, meaning it receives the list from the inner supplier and applies the zone policy before passing the list to the LoadBalancer.

The core logic of the current implementation can be expressed in pseudocode:

~~~java
List<ServiceInstance> filterByZone(
        List<ServiceInstance> input,
        String preferredZone) {

    if (preferredZone == null) {
        return input;
    }

    List<ServiceInstance> matches = input.stream()
            .filter(instance ->
                    preferredZone.equalsIgnoreCase(
                            instance.getMetadata().get("zone")))
            .toList();

    return matches.isEmpty() ? input : matches;
}
~~~

This is **simplified illustrative pseudocode**, not a public API called by applications. The real implementation also handles reading the zone configuration and forwarding the Request through the supplier chain.

Three key rules:

1. A preferred zone is set and **at least one instance matches**: return **only the matching instances**.
2. **No client zone is configured**: return the delegate's list as-is.
3. **A preferred zone is set but no instance matches**: return the delegate's list as-is, **do not return an empty list**.

Zone value matching uses **equalsIgnoreCase** in the referenced implementation. Even so, keep naming conventions consistent: do not rely on automatic whitespace trimming, aliases, or zone name normalization, as these operations are not part of the basic filtering logic.

### 3.1. Sample Output Table

Suppose the input from discovery is **[A(zone-a), B(zone-a), C(zone-b), D(no zone)]**:

| Caller Zone | Result After ZonePreference | Explanation |
| --- | --- | --- |
| zone-a | [A, B] | Two instances in the same zone |
| zone-b | [C] | One instance in the same zone |
| zone-c | [A, B, C, D] | No match, fall back to full input |
| Not configured | [A, B, C, D] | No zone criterion to filter by |
| ZONE-A | [A, B] | Case-insensitive match |

If the input from discovery is an empty list **[]**, ZonePreference also returns **[]**. It does not create instances itself, refresh the service registry, or decide what HTTP error will be returned.

### 3.2. Zone Preference vs. Strict Zone Affinity

The name **preference** has an exact meaning: this is a **soft preference**, not a hard restriction:

~~~text
Client zone-a
    |
    +-- Has [A(zone-a), B(zone-a)]? --> return only [A, B]
    |
    +-- No zone-a instances?        --> return all delegate instances
                                        (including zone-b, zone-c, ...)
~~~

Do not use this filter as a mandatory control for data sovereignty, compliance, tenant partitioning, or security isolation. If **cross-zone calls must be strictly prohibited**, a hard filtering policy or a dedicated routing/security layer capable of rejecting requests when no matching-zone instance is available is required.

## 4. Placing Zone Preference in the Instance Selection Chain

~~~mermaid
flowchart TD
    A["RestClient / WebClient / OpenFeign"] --> B["LoadBalancer by service ID"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["DiscoveryClient / ReactiveDiscoveryClient"]
    D --> E["Instance list"]
    E --> F["Cache or HealthCheck"]
    F --> G["ZonePreference: filter zone metadata"]
    G --> H{"Same-zone candidates?"}
    H -->|Yes| I["Same-zone list only"]
    H -->|No| J["Fallback: keep delegate list"]
    I --> K["RoundRobin / Random selects instance"]
    J --> K
    K --> L["Rebuild host/port URI"]
    L --> M["Send HTTP request"]
~~~

Step-by-step example:

~~~text
Request: GET http://inventory-service/api/stock/BOOK-01
Client zone: zone-a

Discovery:            [inventory-a1, inventory-a2, inventory-b1]
Cache:                [inventory-a1, inventory-a2, inventory-b1]
ZonePreference:       [inventory-a1, inventory-a2]
RoundRobin:           inventory-a1  (depending on current counter position)
Physical URI:         http://10.10.1.21:8080/api/stock/BOOK-01
~~~

The next request may select inventory-a2. **ZonePreference does not guarantee alternating between a1 and a2**; RoundRobin is the component that determines the selection position, and the order/policy can be affected by other suppliers.

## 5. Configuring the Builder to Enable Zone Preference

Spring Cloud LoadBalancer **does not automatically apply zone preference just because application.yml contains spring.cloud.loadbalancer.zone**. You must use ZonePreferenceServiceInstanceListSupplier, typically created via **ServiceInstanceListSupplier.builder()**.

### 5.1. Example with Blocking Discovery

Suitable when the instance source uses synchronous DiscoveryClient, such as SimpleDiscoveryClient in a local environment:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class InventoryZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

With this order, data flows along the path:

~~~text
Discovery -> Cache -> ZonePreference -> LoadBalancer
~~~

Although when read as a delegate relationship ZonePreference is the outermost wrapper, it **applies filtering after** Cache has provided the instance list. This is the order recommended by the Spring Cloud documentation: place caching immediately after the discovery source, followed by policy-filtering suppliers.

### 5.2. Example with Reactive Discovery

When the provider supports ReactiveDiscoveryClient:

~~~java
class InventoryReactiveZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

In this builder, **withDiscoveryClient()** selects the ReactiveDiscoveryClient source, while **withBlockingDiscoveryClient()** selects the DiscoveryClient source. Do not confuse the two APIs just because both ultimately provide a list of ServiceInstances.

### 5.3. Binding Configuration to a Service ID

To apply the supplier only to inventory-service:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryZoneLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

The **InventoryZoneLoadBalancerConfiguration** class in the example is defined **without @Configuration** and is referenced by @LoadBalancerClient. According to Spring Cloud guidelines, a LoadBalancer-specific configuration class should not be picked up by the main application's component scan as a global configuration. An alternative is placing that class outside the component scan scope.

If the application also calls payment-service, the same supplier does not necessarily apply to payment-service. Per-service-ID configuration helps tailor the policy to each downstream service.

### 5.4. Enabling Zone on the Caller

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      zone: zone-a
~~~

The **spring.cloud.loadbalancer.zone** property specifies the preferred zone on the caller side. It does not automatically register metadata for Inventory instances; that part is handled by the provider/discovery.

## 6. Configuring Zone Metadata from Discovery Sources

### 6.1. Eureka: Attaching Zone to an Instance

The Inventory application registers zone metadata:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

Another Inventory replica, in zone-b, uses:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-b
~~~

With Eureka, Spring Cloud includes integration to infer the **caller's zone** from Eureka configuration and pass it to the LoadBalancer; the documentation also describes fallback heuristics involving Eureka metadata or availability zones. However, **spring.cloud.loadbalancer.zone** lets you override the zone used by the LoadBalancer. To avoid relying on defaults or heuristics, explicitly configure the zone on the caller in practice exercises.

An application can be both a provider for its own service and a caller of another service. In that case, distinguish:

- **eureka.instance.metadata-map.zone**: the instance metadata **it registers** for other applications to read.
- **spring.cloud.loadbalancer.zone**: the zone **it uses to prioritize** when calling other applications.

In many deployments, both values are identical, but they serve two different data directions.

### 6.2. Consul, Kubernetes, and Other Providers

Do not assume all discovery providers automatically generate **zone** metadata in the same way. Spring Cloud LoadBalancer only reads:

~~~java
serviceInstance.getMetadata().get("zone")
~~~

If Kubernetes stores the zone in the node label **topology.kubernetes.io/zone**, that does not automatically guarantee this label appears in the exact ServiceInstance metadata entry. Depending on the integration, a label mapping mechanism or metadata enrichment from the discovery source may be needed.

Similarly, if Consul or another provider uses a different tag or key, normalize it when creating ServiceInstance or write a metadata-transforming supplier. Use **spring.cloud.loadbalancer.zone** on the caller if the integration does not automatically determine the local zone.

**Principle:** verify the data returned by DiscoveryClient/ReactiveDiscoveryClient first, rather than looking only at the registry dashboard or workload YAML.

### 6.3. SimpleDiscoveryClient for Local Testing

When no registry is set up yet, you can declare a static list in the caller:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

This example relies on SimpleDiscoveryClient and the metadata defined in the instance list configuration. Before interpreting results, inspect each **ServiceInstance.getMetadata()** to verify the zone key was bound properly in the Spring Cloud version in use. SimpleDiscoveryClient is a **static** source; it does not automatically detect instances that were recently stopped or started.

With SimpleDiscoveryClient, you can use **withBlockingDiscoveryClient()** in the builder from section 5.1. With a provider that has true reactive discovery, switch to **withDiscoveryClient()** as needed.

## 7. How Zone Preference Changes Round Robin Selection

Suppose all instances are healthy, there are no other filters, and the list sequence is stable:

~~~text
inventory-service
  A - zone-a
  B - zone-a
  C - zone-b
  D - zone-b
~~~

In a configuration without ZonePreference, Round Robin has four candidates **[A, B, C, D]**. When the client is in zone-a with ZonePreference, Round Robin only sees **[A, B]**.

| Policy | List RoundRobin Receives | Possible Selections |
| --- | --- | --- |
| No zone filtering | [A, B, C, D] | A, B, C, or D |
| Caller zone-a | [A, B] | A or B |
| Caller zone-b | [C, D] | C or D |
| Caller zone-c, no match | [A, B, C, D] | A, B, C, or D |

**Zone preference does not select instances directly.** It does not create a separate Round Robin turn per zone via a separate API; it only narrows the candidate list. The final selection algorithm still operates on the list returned by the supplier.

In a multi-instance system, load balancing **within a zone** can continue using Round Robin, Random, or a custom algorithm.

### 7.1. Why Multiple Requests May Not Yield a 50/50 Distribution

Even when zone-a has two instances, you should not use just two requests to conclude the algorithm is broken if the results do not alternate as expected. Account for:

- The state of the RoundRobin counter.
- Concurrent requests and execution order.
- The possibility that the supplier returns different snapshots.
- Cache or health checks updating the list.
- Retries triggering additional target selections.
- Other filters such as hints, sticky sessions, or weighted suppliers.

To verify distribution, a sufficiently large number of requests is needed, along with recording the actual candidate list at selection time.

## 8. Fallback When No Same-Zone Instances Exist

This is the most important behavior to understand before using ZonePreference:

~~~mermaid
flowchart TD
    A["List from delegate"] --> B{"Caller zone configured?"}
    B -->|No| C["Return original list"]
    B -->|Yes| D["Filter zone metadata"]
    D --> E{"Found >= 1 instance?"}
    E -->|Yes| F["Return same-zone list"]
    E -->|No| C
    F --> G["LoadBalancer selects instance"]
    C --> G
~~~

Example of a running system:

~~~text
T0:
  Caller: zone-a
  Discovery: [A(zone-a), B(zone-b)]
  ZonePreference: [A]

T1: A is deregistered, discovery updated
  Discovery: [B(zone-b)]
  ZonePreference: [B]    // fall back outside zone-a

T2: A is redeployed and appears in discovery
  Discovery: [A(zone-a), B(zone-b)]
  ZonePreference: [A]    // local preference resumes
~~~

This supports **continued service availability when local instances are absent**, but it does not mean automatic full-stack infrastructure failover. Update latency can depend on caching, health checks, the registry, and retry mechanisms.

### 8.1. Fallback Does Not Evaluate Instance Health

If A is still in the discovery list but has actually died, ZonePreference can still return **[A]**, because it only inspects zone metadata. It does not ping A itself to detect failures.

In this situation, you need to:

1. Update instance status via the registry/health checks.
2. Use HealthCheckServiceInstanceListSupplier if the instance source lacks reliable health status.
3. Configure appropriate timeouts and retries on the HTTP client.
4. Monitor connection errors and when the instance list changes.

You cannot expect a zone filter to replace a circuit breaker or health monitoring.

### 8.2. Fallback and Compliance Requirements

If data is only permitted to be processed within zone-a, falling back to zone-b can violate architectural requirements. In that case:

- **Do not use ZonePreference as the sole isolation mechanism.**
- A strict filtering supplier is needed: when no same-zone instance exists, return an empty list so the caller receives an error rather than crossing zones.
- Or apply separate routing/network policies combined with backend authentication/authorization.
- Check all retries, Gateways, and proxies to ensure traffic is not inadvertently sent outside the zone.

This is a trade-off between **availability** and **strict locality**. It must be decided explicitly based on system requirements.

## 9. Decorator Ordering: Cache, Health Check, and Zone

ZonePreference is a decorator; its output depends on the list provided by the preceding layers.

### 9.1. Placing Cache Before ZonePreference

Recommended chain:

~~~java
return ServiceInstanceListSupplier.builder()
        .withBlockingDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .build(context);
~~~

Transformation flow:

~~~text
Discovery -> Caching -> ZonePreference -> LoadBalancer
~~~

CachingServiceInstanceListSupplier caches the instance list by service ID, and then ZonePreference applies the zone policy. This configuration reduces registry reads while still using a discovery snapshot as the source for the zone policy.

If the cache is placed **outside** ZonePreference, the filtered result may be cached per service ID. With a fixed client zone, that might still appear to work; however, the filtered data is no longer the original discovery list and easily causes confusion when combining per-request filters, changing the zone policy, or reusing the supplier in other contexts.

Spring Cloud recommends placing the caching supplier **immediately after the supplier fetching instances over the network**, before filtering suppliers.

### 9.2. Health Check Before ZonePreference

If the discovery source does not fully reflect health:

~~~java
return ServiceInstanceListSupplier.builder()
        .withBlockingDiscoveryClient()
        .withBlockingHealthChecks()
        .withZonePreference()
        .build(context);
~~~

Flow:

~~~text
Discovery -> HealthCheck -> ZonePreference -> LoadBalancer
~~~

HealthCheck should see the **complete original list** before zone preference runs. If same-zone A is DOWN and cross-zone B is UP, HealthCheck gets the chance to eliminate A before ZonePreference evaluates fallback.

However, HealthCheckServiceInstanceListSupplier has a polling loop and emits results asynchronously; furthermore, depending on the version/configuration, when no healthy instances are found, it may fall back to the delegate list. Do not treat a health snapshot as a guarantee that a request will succeed.

**Do not enable both cache and health-check suppliers by default**: Spring Cloud's HealthCheckServiceInstanceListSupplier has its own result replay mechanism; adding cache on top can often make data stale or harder to reason about. Check the exact behavior of your release train.

### 9.3. Zone and Hint: Order Is Also Policy

Suppose:

~~~text
A: zone-a, hint=stable
B: zone-b, hint=canary
Client zone: zone-a
Request hint: canary
~~~

The two orderings produce different results because both ZonePreference and HintBased fall back when there is no match:

| Transformation Chain | Progression | Result |
| --- | --- | --- |
| Zone then Hint | [A,B] → Zone [A] → Hint has no match, fallback [A] | A |
| Hint then Zone | [A,B] → Hint [B] → Zone has no match, fallback [B] | B |

Therefore, priority must be defined:

- **Zone first, Hint second**: prioritize locality; canary only gets a chance if it exists within the filtered zone.
- **Hint first, Zone second**: prioritize the deployment group; zone is only optimized within instances belonging to the hint group.

This is not an algorithm bug. It is a consequence of **decorator ordering and fallback conditions**. If both conditions must be enforced simultaneously, do not use two soft-preference filters and assume they perform a strict intersection.

## 10. Integration with RestClient, WebClient, and OpenFeign

### 10.1. RestClient

The caller registers a builder with @LoadBalanced:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

The client calls by service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

If a zone preference supplier is configured for inventory-service, BlockingLoadBalancerClient receives the filtered list and then selects an instance. Business code still uses the logical URI **http://inventory-service/...**, without hardcoding zone-a IPs.

### 10.2. WebClient

With a reactive HTTP client:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

When the provider has ReactiveDiscoveryClient, you can use **withDiscoveryClient().withCaching().withZonePreference()** in the supplier configuration. ZonePreference does not require a separate algorithm for WebClient; it still filters the list before the ServiceInstance selection step.

### 10.3. OpenFeign

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

With Spring Cloud OpenFeign integrated with LoadBalancer, the name inventory-service is used to look up instances; the zone preference supplier can narrow the list before Feign calls the actual instance. **Do not declare a fixed URL** if you want service-ID resolution and load balancing via discovery.

In all three approaches, zone filtering happens in **ServiceInstanceListSupplier**, independent of the GET/POST method or response body. Timeouts, retries, idempotency, and authentication still need separate configuration.

## 11. Zone Preference Does Not Replace Other Mechanisms

| Mechanism | What Question Does It Answer? | Scope |
| --- | --- | --- |
| Discovery | What instances exist? | Service registry / ServiceInstance |
| Health check | Is the instance still ready? | Instance status |
| Zone preference | Which zone's instances should be prioritized? | Zone metadata |
| Round Robin | From the candidate list, who is picked next? | Selection algorithm |
| Weighted | Which instance has a higher selection weight? | Traffic distribution |
| Hint-based | Which group does the request belong to, e.g., canary/stable? | Hint metadata and request |
| Circuit breaker | When downstream fails repeatedly, how is the caller protected? | Call chain |
| Retry | Should we retry or re-select an instance? | Request/response control |

Zone preference only uses **metadata**, so it cannot:

- Sense real-time CPU or memory usage of an instance.
- Guarantee that same-zone connections are always faster.
- Detect dead instances if the registry/health status has not updated yet.
- Automatically shift traffic when one zone is overloaded but still has instances.
- Guarantee every request stays within one zone under all circumstances.
- Replace routing policies based on sensitive data, tenants, or regulatory requirements.

If you want to control traffic by latency, load, or circuit breakers, you must combine the corresponding policies and observability.

## 12. Operational Issue: When zone-a Is Overloaded

Suppose zone-a has two instances and zone-b has four instances. The caller is in zone-a, and the two zone-a instances are still registered as healthy but are overloaded.

~~~text
ZonePreference:
    zone-a: [A1, A2]   // matched
    zone-b: [B1, B2, B3, B4]
    result: [A1, A2]
~~~

ZonePreference **does not automatically fall back to zone-b** just because A1/A2 respond slowly or have high CPU. It only falls back when **no same-zone instances are found in the list provided by the delegate**.

If proactive load shedding is needed:

1. Add capacity/autoscaling in zone-a.
2. Use appropriate health checks when an instance can genuinely no longer serve requests.
3. Design a load-balancing policy based on load metrics or weights, if reliable data is available.
4. Monitor latency, saturation, 5xx errors, and retries per zone.
5. Consider a conditional cross-zone spillover policy, rather than assuming ZonePreference already has that built in.

A system may still need orchestration at the Kubernetes, Gateway, service mesh, or external proxy layer. These layers must align to avoid conflicting routing policies.

## 13. Unit Testing the Zone Preference Principle

You can verify the rule using a pure Java model before running Spring:

~~~java
import java.util.List;

public class ZonePreferenceDemo {

    record Instance(String id, String zone) {}

    static List<Instance> prefer(
            List<Instance> instances,
            String clientZone) {

        if (clientZone == null) {
            return instances;
        }

        List<Instance> local = instances.stream()
                .filter(i -> clientZone.equalsIgnoreCase(i.zone()))
                .toList();

        return local.isEmpty() ? instances : local;
    }

    public static void main(String[] args) {
        List<Instance> discovered = List.of(
                new Instance("A", "zone-a"),
                new Instance("B", "zone-a"),
                new Instance("C", "zone-b"));

        System.out.println(prefer(discovered, "zone-a"));
        System.out.println(prefer(discovered, "zone-b"));
        System.out.println(prefer(discovered, "zone-c"));
        System.out.println(prefer(discovered, null));
    }
}
~~~

Expected output:

~~~text
zone-a -> [A, B]
zone-b -> [C]
zone-c -> [A, B, C]   // fallback
null   -> [A, B, C]   // no filtering
~~~

This is a **conceptual model**, not directly calling the ZonePreferenceServiceInstanceListSupplier class. It lets you isolate the filtering rule from the service registry, Spring ApplicationContext, caching, and HTTP. Once you understand the rule, use integration tests with the real supplier.

### 13.1. Edge Cases to Test

| Input | Caller Zone | Expected |
| --- | --- | --- |
| [] | zone-a | [] |
| [A(zone-a)] | zone-a | [A] |
| [A(zone-b)] | zone-a | [A] due to fallback |
| [A(zone-a), B(zone-b)] | zone-a | [A] |
| [A(no metadata), B(zone-b)] | zone-a | [A, B] due to fallback |
| [A(zone-a), B(zone-a)] | ZONE-A | [A, B] |
| [A(zone-a)] | null | [A] |

In real unit tests, create DefaultServiceInstance objects with zone metadata attached, then pass them through a mock supplier that controls the list. The key is knowing what the filtering algorithm itself returns, without letting registry state or caching cause unpredictable changes.

## 14. Integration Test with SimpleDiscoveryClient

### 14.1. Setup

Start two backends with the same GET /whoami endpoint:

~~~text
inventory-a: http://localhost:8081/whoami -> {"instanceId":"inventory-a"}
inventory-b: http://localhost:8082/whoami -> {"instanceId":"inventory-b"}
~~~

The caller includes spring-cloud-starter-loadbalancer, using Spring Cloud SimpleDiscoveryClient and @LoadBalanced RestClient.Builder.

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Attach InventoryZoneLoadBalancerConfiguration from section 5.1 using @LoadBalancerClient.

### 14.2. Observation Steps

1. Call **http://inventory-service/whoami** multiple times through the LoadBalancer-integrated RestClient.
2. With client zone-a, confirm responses come only from inventory-a while both backends are running and metadata is bound properly.
3. Change **spring.cloud.loadbalancer.zone=zone-b**, restart the caller, and confirm only inventory-b is selected.
4. Change the zone to zone-c (no same-zone instances), and confirm requests can reach both inventory-a and inventory-b according to the final selection policy.
5. Remove zone metadata from both instances, and confirm zone preference no longer narrows the list.
6. Stop inventory-a while **keeping it in the static configuration**: requests may still attempt to call inventory-a. This is a limitation of SimpleDiscoveryClient, not evidence against automatic health-based fallback.
7. Try using the HealthCheck supplier immediately after discovery, wait for health status to update, and verify the ability to select the healthy instance in the other zone.

**Warning for step 6:** static configuration does not reflect an instance that just died. In production, registry/health updates and TTL durations determine when zone preference observes the updated list.

### 14.3. Expected Observation Table

| Change | List from Discovery/Health | ZonePreference Returns |
| --- | --- | --- |
| zone-a, both UP | [A(zone-a), B(zone-b)] | [A] |
| zone-b, both UP | [A(zone-a), B(zone-b)] | [B] |
| zone-c, both UP | [A(zone-a), B(zone-b)] | [A, B] |
| zone-a, A removed by health | [B(zone-b)] | [B] due to fallback |
| zone-a, empty list | [] | [] |

A reliable way to verify is to log the **selected ServiceInstance ID and zone** on the caller, while having the backend return its instanceId. Do not check only HTTP status 200, because multiple replicas can return identical business results.

## 15. Observability and Troubleshooting

To understand why a request left the desired zone, observe:

~~~text
serviceId: inventory-service
clientZone: zone-a
discovered: [A(zone-a), B(zone-b)]
healthy:    [B(zone-b)]
zoneOutput: [B(zone-b)]   // fallback, no local match
selected:   B
~~~

If the system already has tracing/metrics, add service ID, instance ID, and zone at an appropriate structured logging level. **Do not log tokens, sensitive identifiers, or full headers/cookies** when analyzing routing.

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Always selects cross-zone despite local instances | Missing spring.cloud.loadbalancer.zone or wrong zone metadata | Print caller configuration and metadata from ServiceInstance |
| Zone configured but list does not change | withZonePreference not added to supplier | Check the active ServiceInstanceListSupplier bean |
| All instances have metadata but no match | Key is not zone, zone name has whitespace or differs in convention | Inspect the actual metadata map |
| No failover when local instance dies | Registry/cache not updated or health filter hasn't removed instance | Check delegate list and TTL |
| Unexpected cross-zone calls | ZonePreference falls back when no local match exists | Measure same-zone instance count before and after filter |
| Canary not receiving expected traffic | Hint and Zone filters have unsuitable priority order | Check decorator order and each layer's fallback |
| WebClient fails to select an instance | Reactive discovery/supplier misconfigured | Check reactive provider and supplier chain |
| Feign calls a fixed URL | @FeignClient has url or fixed URL property | Remove fixed URL if discovery is needed |
| Local zone requests are very slow | Same-zone instances are healthy but overloaded | Check CPU, thread pools, latency, and timeouts |
| Never selects other-zone instances while local zone is UP | Expected zone preference behavior | Evaluate whether a load-based spillover mechanism is needed |

### Quick Verification Procedure

1. Check the actual **clientZone** received by the LoadBalancer.
2. Verify **ServiceInstance.getMetadata().get("zone")** for each instance.
3. Determine the list **before ZonePreference**, after discovery/cache/health.
4. Apply the **same-zone or full fallback** rule on that snapshot.
5. Check the instance selected by Round Robin/Random.
6. Observe the physical URI and any HTTP/TLS/timeout errors after selection.

If the list before ZonePreference is already empty, the issue lies in discovery or a preceding supplier. If zoneOutput contains local instances yet the request goes cross-zone, check whether an outer wrapper or a Gateway/proxy layer is rerouting it.

## 16. Designing a Zone Strategy for Production

### 16.1. Ensure Consistent Naming

Use a consistent zone taxonomy across teams:

~~~text
Correct:
  caller:   zone-a
  provider: zone-a

Error-prone:
  caller:   asia-1a
  provider: zone-a
~~~

If applications are deployed across different platforms, establish a formal mapping table between cloud/Kubernetes labels, registry metadata, and the zone used by the client-side LoadBalancer.

### 16.2. Configure per Deployment Environment

Each Order Service replica can be assigned an environment variable:

~~~text
SPRING_CLOUD_LOADBALANCER_ZONE=zone-a
~~~

The value should be injected by the deployment platform according to actual placement, not hardcoded uniformly across pods in multiple zones. After changing deployment placement or configuration, re-verify the active supplier bean and effective zone.

### 16.3. Define Clear Fallback Boundaries

For normal requests, falling back outside the zone can improve availability. For data permitted to be processed in only one zone, use a strict filter or other protective mechanisms. Both options should be tested when the local zone disappears.

### 16.4. Place Health/Caching in the Right Position

Recommended path:

~~~text
Discovery -> Caching or HealthCheck -> ZonePreference
          -> remaining request policies -> LoadBalancer
~~~

Do not assume decorator order can be swapped freely. A decorator with fallback can return the input list when no match is found, altering the semantics of policies before or after it.

### 16.5. Set Bounded Timeouts and Retries

Cross-zone calls may have different latency than local-zone calls. Measure and configure timeouts based on SLOs rather than using a threshold so low it only fits the local path. When retries re-select an instance, consider the total deadline, retry budget, backoff, and safety of non-idempotent operations.

### 16.6. Monitor Spillover Ratio

You can track a custom metric:

~~~text
cross_zone_selection_ratio =
  number of selections with instance zone != clientZone
  ----------------------------------------------------
  total selections with defined instance zone
~~~

This is a **suggested design metric**, not a default metric name provided by Spring Cloud LoadBalancer. Measurement must specify how instances without zone metadata and retried requests are handled. A sudden spike may indicate that the local zone lacks instances or metadata is inconsistent.

## 17. Deployment Checklist

- [ ] Distinguish the caller's zone from the provider's zone metadata.
- [ ] Configure spring.cloud.loadbalancer.zone on the caller or verify the discovery integration provides the correct zone.
- [ ] Every ServiceInstance has the **zone** metadata key following the convention.
- [ ] The supplier actually includes ZonePreferenceServiceInstanceListSupplier.
- [ ] Cache/HealthCheck is placed after the discovery source and before zone preference.
- [ ] Understand fallback behavior when no same-zone instances remain.
- [ ] Do not use zone preference as a security boundary or mandatory data-residency constraint.
- [ ] Verify interactions with hint, sticky session, retry, and weighted routing if used.
- [ ] Test local UP, local DOWN, missing metadata, and non-existent zone scenarios.
- [ ] Monitor selected instances, latency, cross-zone traffic, and connection errors.
- [ ] Evaluate local zone capacity limits; zone preference does not detect overload on its own.
- [ ] Ensure configuration consistency across RestClient, WebClient, and OpenFeign.

## 18. Conclusion

**ZonePreferenceServiceInstanceListSupplier** is Spring Cloud LoadBalancer's zone-based filtering layer. It uses **spring.cloud.loadbalancer.zone** or caller zone information provided by a discovery integration, compares it against **ServiceInstance.metadata["zone"]**, and prioritizes returning same-zone instances. If no caller zone is configured or no same-zone instances exist, it **returns the delegate list** so the LoadBalancer still has candidates.

A sound design requires all three conditions: **accurate zone metadata**, **a properly ordered supplier chain**, and **a fallback policy aligned with business/operational requirements**. With those in place, RestClient, WebClient, and OpenFeign can continue using logical service IDs while the LoadBalancer prioritizes physical addresses closer to the caller without hardcoding per-zone IPs.

## 19. References

- [Spring Cloud LoadBalancer – Zone-Based Load-Balancing](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): zone preference mechanism, the spring.cloud.loadbalancer.zone property, zone metadata, and builder configuration.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ServiceInstance, and HTTP client integrations.
- [ZonePreferenceServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ZonePreferenceServiceInstanceListSupplier.java): canonical source for zone matching (equalsIgnoreCase) and fallback.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): how to build the supplier/decorator chain.
- [Spring Cloud Netflix Eureka – Reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): instance metadata and Eureka integration with LoadBalancer zones.
