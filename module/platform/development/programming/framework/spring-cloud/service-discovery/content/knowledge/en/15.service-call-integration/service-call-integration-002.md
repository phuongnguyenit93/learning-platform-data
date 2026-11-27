# The Boundary Between Discovery and Instance Selection with Spring Cloud LoadBalancer

In a microservice system, knowing which service instances exist and deciding which replica to send a request to are two different tasks. **Service discovery** answers the question "which instances does this service currently have?". **Load balancing** answers the question "for this request, which of those instances should it be sent to?".

Spring Cloud separates these two responsibilities into distinct abstractions. The discovery adapter fetches data from a registry such as Eureka or Consul; Spring Cloud LoadBalancer receives the instance list, applies suppliers and a selection algorithm, and coordinates with the HTTP client to send the request. Understanding this boundary helps avoid selecting instances incorrectly by hand, misconfiguring clients, or expecting the registry to perform load balancing on its own.

## 1. Three independent steps in a service-to-service call

Suppose the consumer `order-service` needs to call `catalog-service`, which currently has three instances:

| Instance | Address | Zone |
|---|---|---|
| catalog-a | `10.30.1.21:8080` | `zone-a` |
| catalog-b | `10.30.2.22:8080` | `zone-b` |
| catalog-c | `10.30.1.23:8080` | `zone-a` |

A request passes through three steps:

1. **Discovery:** find the instances registered under the serviceId `catalog-service`.
2. **Selection:** filter or order the candidate list according to a policy, then pick one instance for the current request.
3. **Transport:** resolve the logical URI to the selected instance's host/port and execute the HTTP call.

These three steps can be illustrated as follows:

~~~mermaid
flowchart LR
    A["Consumer calls<br/>catalog-service"] --> B["Discovery adapter"]
    R[("Eureka / Consul")] <--> B
    B --> C["ServiceInstance list"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Filter / prioritize candidates"]
    E --> F["LoadBalancer selects 1 instance"]
    F --> G["Load-balanced HTTP client"]
    G --> H["Instance host:port"]
~~~

The registry holds registration data. The discovery client converts that data into instance objects the application can use. LoadBalancer decides which instance in the list to pick at call time. The HTTP client establishes the network connection. Each layer can fail in different ways and needs to be observed independently.

## 2. DiscoveryClient provides the list, it does not decide where requests go

In Spring Cloud Commons, `DiscoveryClient` is the discovery lookup abstraction by serviceId. With the synchronous API, the key method is:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");
~~~

The result is a list of `ServiceInstance`. Each element describes an instance, typically containing host, port, URI, service ID, instance ID, metadata, and secure connection information. A discovery implementation may retrieve data directly from the registry or from an internal cache depending on the integration.

For example, a consumer can inspect the list:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogDiscovery {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> findAddresses() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(instance -> instance.getHost() + ":" + instance.getPort())
                .toList();
    }
}
~~~

This method only returns the addresses currently visible to the discovery client. It does not send HTTP requests and does not pick an optimal instance per request. If the consumer takes `instances.get(0)` and keeps using that address forever, the application has created a very naive selection policy that easily skews load. The order of elements in the list is not a contract of priority or health.

It is also important to distinguish the "registered" list from the "ready to serve requests right now" list. A record may still remain in the registry while a heartbeat or TTL has not yet expired, even though the process has stopped accepting traffic. Health checks, candidate filtering, and cache duration affect the quality of the list that LoadBalancer receives.

## 3. ServiceInstanceListSupplier is the bridge between discovery and selection

Spring Cloud LoadBalancer does not need to know every detail of Eureka or Consul directly. It receives candidates through the `ServiceInstanceListSupplier` abstraction. The supplier is responsible for providing the instance list for a serviceId; suppliers can add caching, health checks, zone preference, or filtering based on deployment policy.

A typical pipeline may include:

- **Discovery-backed supplier:** fetches instances from the discovery client.
- **Caching supplier:** keeps results for a duration to reduce lookup frequency and load on the registry.
- **Health-check supplier:** checks or filters out instances that fail health conditions, if the application enables and configures this mechanism.
- **Zone-preference supplier:** prioritizes instances in the same zone as the consumer when zone metadata and configuration are available.

Not every application uses all of the suppliers above. The actual list depends on configuration and the Spring Cloud version. Caching reduces latency and lookup traffic, but caching for too long can retain instances that have already left the system. Health checks add a health signal but also have their own interval and overhead; they do not guarantee an instance will remain healthy at the exact moment a request arrives.

Example of configuring a supplier using a discovery client and caching:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

This example illustrates one way to construct a supplier. The application's discovery starter integration and LoadBalancer configuration must be compatible with the release train in use. If adding health checks or zone preference, verify the wrapper order in the supplier chain and confirm that health/zone data is provided accurately.

## 4. Spring Cloud LoadBalancer selects an instance

After obtaining the candidate list, LoadBalancer applies a selection strategy to return a `ServiceInstance`. Two common algorithms are:

| Strategy | How it works | When appropriate |
|---|---|---|
| Round robin | Cycles through candidates in order | Instances have roughly equal capacity and simple distribution is desired |
| Random | Picks a candidate at random | Random distribution is desired and short-term variance is acceptable |

Round robin does not mean every instance is guaranteed to receive the exact same number of requests over every interval. Each consumer maintains its own selection state; the number of consumers, uneven traffic, processing time, retries, and changes in the instance list all affect actual distribution. If an instance processes slowly, round robin may still send new requests to it unless another filtering mechanism or policy is in place.

Selection also does not imply automatic failover in all cases. LoadBalancer may pick a valid instance from the current list, yet the connection can still fail due to network issues, the process crashing right after a health check, or the application returning an error. Retry is a separate mechanism that must be configured intentionally; it must have bounds, timeouts, and consider request idempotency.

### Distinguishing the core abstractions

| Component | Responsibility |
|---|---|
| `DiscoveryClient` | Looks up the instance list by serviceId |
| `ServiceRegistry` | Registers, deregisters, and manages registration status |
| `ServiceInstanceListSupplier` | Provides the candidate list to LoadBalancer |
| `LoadBalancerClient` | Synchronous API to select an instance and assist request execution |
| `ReactiveLoadBalancer` | Reactive API to select an instance |
| `@LoadBalanced` HTTP client | Enables serviceId resolution via LoadBalancer before sending requests |

`ServiceRegistry` belongs to the provider's registration side. `DiscoveryClient` belongs to the lookup side. `ServiceInstanceListSupplier` and LoadBalancer belong to the consumer's candidate selection side. These abstractions should not be conflated into a single "registry client" because they have different lifecycles and purposes.

## 5. Let the HTTP client perform selection instead of picking an element manually

For regular HTTP calls, the simplest approach is to mark the HTTP client bean with `@LoadBalanced`. Example using `RestTemplate`:

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

The consumer uses the serviceId in the URL:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class CatalogClient {

    private final RestTemplate restTemplate;

    public CatalogClient(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public CatalogItem findItem(String itemId) {
        return restTemplate.getForObject(
                "http://catalog-service/api/items/{id}",
                CatalogItem.class,
                itemId);
    }
}
~~~

With a bean annotated with `@LoadBalanced`, Spring Cloud integration adds processing to resolve `catalog-service`, fetch candidates, and select an instance before the HTTP request is sent. The URL still uses the logical name; the consumer does not need to assemble the IP and port manually.

If a regular `RestTemplate` without a load-balancing interceptor is used, the hostname `catalog-service` may be passed to the DNS resolver. In that case, the Eureka or Consul registry does not automatically participate in URL resolution. Verify that the right bean is injected and the right client is used; in an application with multiple HTTP clients, use clear qualifiers or bean names to avoid using the wrong one.

You can call `LoadBalancerClient` directly when you need to know the selected instance for diagnostics or special integrations:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogInstanceInspector {

    private final LoadBalancerClient loadBalancerClient;

    public CatalogInstanceInspector(LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public String selectedAddress() {
        ServiceInstance selected =
                loadBalancerClient.choose("catalog-service");

        if (selected == null) {
            throw new IllegalStateException(
                    "No available instance for catalog-service");
        }

        return selected.getHost() + ":" + selected.getPort();
    }
}
~~~

The `choose` call illustrates the selection decision at invocation time. If an application retrieves an instance this way and sends requests directly to the physical address itself, it is responsible for timeouts, error handling, URI construction, and retries. Do not call `choose` just to log and then send the request to the logical URL through another load-balanced HTTP client, because the HTTP client may perform a new selection and the actual request may go to a different instance.

## 6. Per-service configuration scope

An application may call multiple services with different requirements. For example:

- `catalog-service` has instances across multiple zones; prioritize the zone closest to the consumer to reduce latency.
- `payment-service` needs strict timeout and retry policies because requests have side effects.
- `report-service` can distribute load randomly if instances are equivalent.

Spring Cloud LoadBalancer supports per-serviceId configuration through client-specific configuration mechanisms, such as the `@LoadBalancerClient` or `@LoadBalancerClients` annotations. This allows customizing the supplier or LoadBalancer beans for one service without changing the policy for every service in the application.

Example of declaring a client-specific configuration point:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class)
public class CatalogLoadBalancerClientConfiguration {
}
~~~

The custom configuration class must follow the guidelines of the Spring Cloud version in use. Service-specific LoadBalancer configuration beans should not be accidentally component-scanned as application-wide defaults; if applied broadly, a policy meant for catalog could affect other clients.

Only customize the algorithm when there is a measurable requirement. For example, zone preference is only useful when zone metadata is consistently registered and the consumer has a clearly defined zone. A misconfigured zone preference can result in an empty candidate list or overload a single zone.

## 7. Caching, health, and decision consistency

Selection relies on the instance list provided by the supplier at request time. That list may lag behind actual state:

- A provider just shut down, but the consumer's cache has not expired yet.
- An instance just registered, but the consumer has not synced the new data yet.
- A health check passed, then the instance failed before the request arrived.
- The consumer is in another zone, but zone metadata is undeclared or incorrect.
- The registry is temporarily unreachable while the cache still holds previous data.

Therefore, clearly define desired data freshness, cache TTL, health check intervals, and behavior when the registry loses connectivity. Short TTLs update faster but increase query volume; long TTLs reduce load but extend how long stale data is kept. No single TTL value fits all systems.

Supplier health checks also do not replace application readiness. The provider must design its registration lifecycle and health endpoint so an instance is only considered eligible to receive traffic once ready according to system criteria. If the health endpoint only confirms the process is alive without reflecting critical dependencies, LoadBalancer may keep selecting an instance that cannot yet handle requests.

When the candidate list is empty, LoadBalancer cannot select an instance. The consumer must handle the service dependency error explicitly, return an appropriate error code, log, and emit metrics. Do not silently fall back to an unmanaged hardcoded address, as that breaks discovery and selection policies.

## 8. Testing and observing LoadBalancer

A good test suite should verify both the candidate list and the instance that actually receives the request. You can test the following scenarios:

| Scenario | Expected result to verify |
|---|---|
| One registered instance | Requests are sent to that instance |
| Multiple instances with the same serviceId | Selection uses the right candidate set and distributes per the configured strategy |
| An instance marked unhealthy | The instance is excluded or deprioritized per the configured supplier/health policy |
| An instance stops abruptly | Consumer handles connection errors; cache and health checks update within expected timing |
| No instances | Requests fail in a controlled manner without picking a wrong hostname or stale address |
| Consumer in a specific zone | Zone preference works properly when metadata and configuration are valid |
| Retries enabled | Retry count is bounded and next-instance selection behaves as configured |

Log the serviceId, instance ID, zone, selection result, connection duration, and HTTP status. Useful metrics include successful/failed selection counts, candidate instance counts, connection errors, and request duration per service. Avoid logging access tokens, personal data, or sensitive payloads.

When investigating incidents, identify which layer the error occurs in:

1. The registry has no record or the provider has not registered.
2. The discovery client does not return the expected list.
3. Supplier filtering or caching produces an incorrect candidate set.
4. LoadBalancer fails to select an instance or uses the wrong policy.
5. The HTTP client does not send to the selected address or the connection fails.

Separating these layers avoids tweaking the selection algorithm when the real cause is a provider registering the wrong address, a faulty health check, or a consumer using an HTTP client without `@LoadBalanced`.

## 9. Design principles

When designing calls between microservices, keep responsibility boundaries clear:

- The provider registers and maintains instance status in the registry.
- The discovery client provides the instance list by serviceId.
- The supplier prepares the candidate set, optionally adding caching, health, and zone handling.
- LoadBalancer selects an instance according to policy.
- The HTTP client sends the request and handles timeouts, responses, or connection errors.

**Discovery answers "which instances exist"; LoadBalancer answers "which instance this request goes to".** The registry does not load-balance for the consumer on its own, and LoadBalancer does not replace the provider's registration lifecycle. Keeping that boundary clear allows the application to swap registries, selection strategies, or HTTP clients without tangling responsibilities.
