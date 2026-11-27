# Declaring a @LoadBalanced RestClient.Builder

In a microservice architecture, `order-service` generally should not hard-code `localhost:8081` for `inventory-service`. A service can have multiple `ServiceInstance` entries running on different hosts/ports, and the instance list changes during deployments or scaling. With **Spring Cloud LoadBalancer**, you can call services by **service ID** through `RestClient` by declaring a `@LoadBalanced` `RestClient.Builder`.

This lesson belongs to the **RestClient** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module focuses on understanding client-side load balancing: selecting a `ServiceInstance` by service ID, discovery, health checks, routing policies, and reliable communication with `RestClient`, `WebClient`, OpenFeign, retries/timeouts, and error observability. This lesson focuses on how to properly declare a **load-balanced builder**, use it in an application, and verify that requests reach the intended replicas.

After this lesson, you will be able to:

- Distinguish between `RestClient`, `RestClient.Builder`, and the meaning of the `@LoadBalanced` annotation.
- Add the required dependencies and register a `@LoadBalanced` builder bean.
- Create a client calling `http://inventory-service` instead of a fixed host/port.
- Use a load-balanced builder alongside a direct HTTP builder/client without mixing up beans.
- Understand where LoadBalancer selects an instance and the limits of `@LoadBalanced` regarding retries, timeouts, and health checks.
- Troubleshoot common errors when a service ID is not resolved or requests fail to reach a replica.

## 1. Why does RestClient need @LoadBalanced?

A call to a physical address uses a URI like this:

~~~http
GET http://localhost:8081/internal/instance
~~~

Here, `localhost:8081` is a **specific target address**. If the instance moves to `8082`, the client must know the new address. If there are three replicas, a plain `RestClient` does not automatically know which replica to choose from a discovery list.

When using Spring Cloud LoadBalancer, the caller can send:

~~~http
GET http://inventory-service/internal/instance
~~~

Here, `inventory-service` is the **service ID**. If the builder is integrated with Spring Cloud LoadBalancer, the logical hostname portion of the URI identifies the target service. LoadBalancer fetches the list of `ServiceInstance` entries, picks one instance, and sends the HTTP request to that instance's physical address.

~~~mermaid
flowchart LR
    A["RestClient calls http://inventory-service"] --> B["LoadBalancer interceptor"]
    B --> C["Service ID: inventory-service"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Discovery: inv-a, inv-b, inv-c"]
    E --> F["Select one ServiceInstance"]
    F --> G["Replace URI with actual host:port"]
    G --> H["HTTP request to replica"]
~~~

Important point: `@LoadBalanced` **is not a round-robin algorithm**. The annotation marks the builder so Spring Cloud's auto-configuration attaches LoadBalancer capability. Fetching the list and selecting an instance belong to Spring Cloud LoadBalancer components.

## 2. Distinguishing the three objects

| Component | Role | Does it load-balance automatically? |
|---|---|---|
| `RestClient` | Synchronous HTTP client with a fluent API to send requests and receive responses | No, if created from a plain builder |
| `RestClient.Builder` | Configures and builds a `RestClient` | No, unless integrated with LoadBalancer |
| `@LoadBalanced RestClient.Builder` | Builder bean recognized by Spring Cloud to attach service instance selection capability | Yes, when the corresponding dependencies and auto-configuration are active |

`RestClient` is Spring Framework's **synchronous** HTTP client. If an application needs asynchronous/non-blocking calls, `WebClient` follows a different model. Both can integrate with Spring Cloud LoadBalancer, though this lesson covers only `RestClient.Builder`.

`RestClient.Builder` holds settings such as base URL, headers, request factory, message converters, and interceptors. After calling `build()`, you obtain a reusable `RestClient`. Do not continuously mutate a shared builder across request threads to swap service IDs dynamically: build appropriate clients during application startup.

## 3. Conditions for the example to work

The example assumes the project uses **compatible** Spring Boot/Spring Cloud versions, includes `RestClient` (Spring Framework 6.1 or later), and supports Spring Cloud LoadBalancer integration with `RestClient.Builder`.

Gradle dependencies typically needed in the caller application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

In a real project, use a **Spring Cloud BOM compatible with your Spring Boot version** to manage Spring Cloud library versions; do not place arbitrary standalone versions side by side. If the application uses Eureka/Consul/Kubernetes discovery, add the corresponding discovery starter/adapter for your project's platform.

You can start with `SimpleDiscoveryClient` to experiment without a dynamic registry. With static configuration, no running Eureka server is needed; however, the configured instance addresses must actually serve HTTP for end-to-end verification.

### Remember the difference between dependencies and annotations

- **The LoadBalancer dependency** provides the instance-selection mechanism and HTTP client integration.
- **Discovery** provides instance information. It can be a dynamic registry or a static list.
- **The `@LoadBalanced` annotation on the builder** tells Spring Cloud that the bean must be equipped with service-ID instance selection.
- **The HTTP transport** executes the final request to the chosen address.

Adding only the dependency without selecting the right builder can leave requests treating the hostname as an ordinary DNS address. Putting `@LoadBalanced` without matching auto-configuration or an instance source is also insufficient for requests to succeed.

## 4. Declaring a @LoadBalanced RestClient.Builder bean

Minimal configuration:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Breakdown of each part:

1. `@Configuration` indicates a Spring bean declaration class.
2. `@Bean` registers the `RestClient.Builder` object into the application context.
3. `@LoadBalanced` acts as a marker/qualifier so Spring Cloud components recognize that the builder should be configured for load balancing.
4. `RestClient.builder()` creates the builder. Spring Cloud attaches the load-balancing integration through the appropriate bean-processing and interceptor mechanism when dependencies are present.
5. The name `loadBalancedRestClientBuilder` makes it easy to distinguish from a plain builder when the application has multiple clients.

**Place the annotation on the builder bean declaration method**, not only on a controller making HTTP calls. The object injected downstream must be the exact builder that has been configured for load balancing.

Note that exact configuration details depend on the Spring Cloud version: if the annotation is not processed or the bean does not appear in the context, fix dependencies/auto-configuration first instead of assuming service IDs will be resolved automatically.

## 5. Injecting the builder and creating a RestClient for a specific service

In `InventoryClient`, create the client from the `@LoadBalanced` builder:

~~~java
package com.example.order.client;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {

    private final RestClient inventoryRestClient;

    public InventoryClient(
            @LoadBalanced RestClient.Builder builder) {
        this.inventoryRestClient = builder
                .clone()
                .baseUrl("http://inventory-service")
                .build();
    }

    public String readInstanceIdentity() {
        return inventoryRestClient.get()
                .uri("/internal/instance")
                .retrieve()
                .body(String.class);
    }
}
~~~

Here:

- `@LoadBalanced` on the constructor parameter requests the exact marked builder bean, especially when multiple builders exist.
- `baseUrl("http://inventory-service")` uses the service ID, **not the physical hostname of one instance**.
- `clone()` creates a separate builder before changing the base URL, preventing side effects on a shared builder if multiple clients use it.
- `build()` creates a reusable client for subsequent requests.
- `uri("/internal/instance")` appends the path to the base URL; Spring Cloud LoadBalancer handles the request's service ID.

If there is only a single builder in the context, injection by type alone can also work. Still, adding the `@LoadBalanced` qualifier makes the intent explicit and reduces risk when other HTTP clients are added later.

### Using a DTO instead of String

In a real application, responses should have a clear data contract. Suppose the target service returns:

~~~json
{
  "serviceId": "inventory-service",
  "instanceId": "inv-a",
  "zone": "zone-a"
}
~~~

You can define a DTO:

~~~java
public record InstanceIdentity(
        String serviceId,
        String instanceId,
        String zone
) {}
~~~

And read the response:

~~~java
public InstanceIdentity fetchInstanceIdentity() {
    return inventoryRestClient.get()
            .uri("/internal/instance")
            .retrieve()
            .body(InstanceIdentity.class);
}
~~~

This DTO helps observe which instance was selected, though `instanceId` in the response is **information supplied by the target application**. It does not necessarily match the registry's instance ID verbatim. Keep the two identifiers distinct if you use them to correlate logs and metrics.

## 6. Preparing two replicas with SimpleDiscoveryClient

For local testing, the caller can know two addresses for the same service ID ahead of time. In the **caller application's** `application.yml`:

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
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

This data indicates that `inventory-service` has two instances. To test properly:

1. Start the first replica on port `8081`, returning `instanceId=inv-a`.
2. Start the second replica on port `8082`, returning `instanceId=inv-b`.
3. Ensure both expose `GET /internal/instance`.
4. Run `order-service` with the dependencies and `@LoadBalanced RestClient.Builder` bean.
5. Call `InventoryClient.readInstanceIdentity()` multiple times from a test controller.

Example endpoint in the caller:

~~~java
package com.example.order.web;

import com.example.order.client.InventoryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final InventoryClient inventoryClient;

    public ProbeController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/demo/selected-instance")
    public String selectedInstance() {
        return inventoryClient.readInstanceIdentity();
    }
}
~~~

You can call:

~~~bash
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
~~~

The responses may alternate showing `inv-a` and `inv-b`. This is a demonstration for observing distribution; **do not treat strict alternation in every scenario as an absolute guarantee**. The LoadBalancer algorithm, instance states, concurrency, and supplier filters can affect the outcome.

The `SimpleDiscoveryClient` list is **static**. If you stop `8082` without updating configuration and without health checks, the supplier can still return the dead address. `@LoadBalanced` does not automatically remove broken replicas or retry requests.

## 7. Inside a request: what happens?

Suppose the client calls `GET /internal/instance` using the base URL `http://inventory-service`.

~~~mermaid
sequenceDiagram
    participant App as Order application
    participant RC as RestClient
    participant LB as LoadBalancer integration
    participant S as Instance supplier
    participant Inv as Inventory replica
    App->>RC: GET http://inventory-service/internal/instance
    RC->>LB: HTTP request with service ID
    LB->>S: Fetch ServiceInstance list
    S-->>LB: inv-a, inv-b
    LB->>LB: Select one ServiceInstance
    LB->>Inv: GET http://host:port/internal/instance
    Inv-->>LB: Response / instance identity
    LB-->>RC: Response
    RC-->>App: DTO body or String
~~~

Exact interceptor path details can vary by version and configured HTTP client, but the division of responsibilities stays the same:

- `RestClient` executes the synchronous request-sending API.
- The LoadBalancer integration extracts the **logical hostname in the URI** as the service ID.
- `ServiceInstanceListSupplier` retrieves the list from discovery, possibly through caches or filters.
- The instance-selection algorithm picks the physical target.
- The HTTP request is sent to the selected instance's host/port.

If the URI already uses `http://localhost:8081`, that is a concrete address; do not use it in a client intended to select by service ID. Conversely, if you call `http://inventory-service` with a plain non-integrated RestClient, the hostname may be treated as a normal DNS name and cause a name-resolution error.

## 8. One application having both direct RestClient and LoadBalanced RestClient

In a system, you may need both styles:

- **LoadBalanced** client: calls `inventory-service` or `payment-service` by service ID.
- **Direct** client: calls an endpoint with a fixed URL, such as a third-party API or a service not using service discovery.

Declare two intentional builders:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientBuilders {

    @Bean
    @Primary
    RestClient.Builder directRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

`@Primary` marks the plain builder as the default choice when injecting by type alone. `@LoadBalanced` selects the builder integrated with Spring Cloud LoadBalancer.

Example of intentional injection:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

public SomeClient(
        @LoadBalanced RestClient.Builder internalBuilder,
        @Qualifier("directRestClientBuilder") RestClient.Builder directBuilder) {
    this.inventory = internalBuilder.clone()
            .baseUrl("http://inventory-service")
            .build();

    this.external = directBuilder.clone()
            .baseUrl("https://api.example.com")
            .build();
}
~~~

This is a **constructor illustration** and must be placed inside a class with matching `inventory` and `external` fields. This injection style prevents an external URL from accidentally being passed to a builder expecting a service ID in discovery.

If you use Spring Boot's auto-configured `RestClient.Builder` as the direct builder, you do not necessarily have to declare `directRestClientBuilder()` yourself. What matters is **clearly defining which bean is direct and which is load-balanced**, especially when the application context contains multiple builders of the same type.

## 9. Timeouts and retries do not appear automatically because of @LoadBalanced

`@LoadBalanced` solves **instance selection**. It does not automatically provide a timeout/retry setup suited to every business API. A load-balanced request can still be slow, fail to connect, or receive a `5xx` status.

Example configuring timeouts on a builder via a request factory in an application using the synchronous client:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class HttpTimeoutConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(3000);

        return RestClient.builder().requestFactory(factory);
    }
}
~~~

Values are in milliseconds in this example: 2-second connect timeout, 3-second read timeout. This is an **illustrative configuration for one application**, not a universal default recommendation for all services. In a real project, select an HTTP request factory aligned with connection pooling, TLS, and throughput needs.

This snippet is an **alternative** to the builder bean in section 4, not a second `@LoadBalanced` bean of the same type to place alongside it.

Regarding retries:

- Retries may require enabling the corresponding retry mechanism in Spring Cloud or a resilience framework; do not assume the annotation retries all errors automatically.
- A retry may re-select an instance depending on the LoadBalancer/retry client policy and configuration.
- For idempotent HTTP `GET`, controlled retries are generally safer.
- For `POST` creating orders or payments, retrying without an idempotency key risks creating duplicate side effects.
- Timeouts, retry counts, backoff, and overall time limits must be designed together.

An endpoint with no remaining available instances must be handled as a failure to find a serving target. The exception type or how upper layers map it to an HTTP status depends on the stack and version, so do not rely on a hardcoded error message string as an application contract.

## 10. How ServiceInstanceListSupplier, health, and caching affect RestClient

RestClient does not decide the instance list itself. It uses the service ID's LoadBalancer context, which can have its own supplier chain:

~~~text
InventoryClient
    |
    v
@LoadBalanced RestClient
    |
    v
LoadBalancer for inventory-service
    |
    v
ServiceInstanceListSupplier
    |
    +--> Discovery client
    +--> Cache (if configured)
    +--> Health checks (if configured)
    +--> Zone/metadata policy (if configured)
    |
    v
Selected ServiceInstance
    |
    v
HTTP transport
~~~

Practical consequences:

- If discovery returns an empty list, RestClient has no physical target to call.
- If the cache still holds a removed instance, requests can still be sent to an instance that is no longer serving.
- If a health-check supplier filters out a replica, the algorithm only picks from the group considered healthy.
- If zone preference is active, you may see RestClient primarily pick instances in the same zone rather than alternating across all replicas.
- If retries re-select instances, actual HTTP call counts can exceed calls to `InventoryClient.readInstanceIdentity()`.

Therefore, when distribution behaves unexpectedly, do not inspect only RestClient code. Check the list from discovery, the supplier chain, and the instance-selection algorithm.

## 11. Common errors and how to verify them

| Symptom | Possible cause | How to check |
|---|---|---|
| Cannot resolve `inventory-service` | Client uses a non-load-balanced builder, or LoadBalancer dependency is missing | Verify the `@LoadBalanced` bean and proper builder injection |
| Reports no instance available | Service ID mismatch, empty discovery, or supplier filtered all out | Check the service ID and `ServiceInstance` list on the caller side |
| Calls only one replica | Discovery has only one entry, health/zone filter, or algorithm/policy | Inspect the candidate list and response instance IDs |
| Requests still hit a stopped port | Static source, old snapshot, or unrefreshed cache | Inspect registry, discovery, and LoadBalancer cache |
| Ambiguous bean injection | Multiple `RestClient.Builder` beans without distinction | Use `@LoadBalanced`, `@Qualifier`, or `@Primary` as intended |
| Builder configuration has no effect | `@Configuration` class outside component scan, or RestClient built with another builder | Check which bean is actually injected into the client |
| TLS error or connection timeout | Instance returns mismatched scheme/port, networking, or request factory | Check the `ServiceInstance` URI and HTTP client config |
| Retries cause duplicate requests | Retry policy lacks bounds/idempotency | Log attempt counts, inspect HTTP method and idempotency key |

### Easily overlooked mistakes

**Wrong service ID:** the target service's `spring.application.name` and the name used by the caller must match consistently per the discovery implementation. For example, registering as `stock-service` while the caller uses `inventory-service` will fail to find matching instances unless custom mapping exists.

**Wrong bean:** `@LoadBalanced` on one builder does not make every `RestClient.builder()` call elsewhere automatically load-balanced. Every client must be built from the integrated builder.

**Missing URI scheme:** for instance, `baseUrl("inventory-service")` is not cleanly equivalent to `baseUrl("http://inventory-service")`. Always use a URI with the appropriate `http://` or `https://` scheme.

**Failing to distinguish client and server errors:** `retrieve()` normally handles error HTTP statuses with exceptions per default/configured policy. Connection failures before reaching a server and received `4xx/5xx` responses are two distinct error groups and should be observed separately.

**Not testing with multiple instances:** one successful request only proves a single replica was reachable; it does not prove multi-instance listing or the load-balancing algorithm works properly.

## 12. Hands-on testing from configuration to request

An end-to-end verification should follow these steps.

### Step 1: Test the two replicas directly

~~~bash
curl http://localhost:8081/internal/instance
curl http://localhost:8082/internal/instance
~~~

Both responses should show distinct instance IDs.

### Step 2: Check caller configuration

Verify `application.yml` contains both URIs under service ID `inventory-service`. Confirm the project has `spring-cloud-starter-loadbalancer`, the `@LoadBalanced RestClient.Builder` bean exists, and `InventoryClient` injects that bean.

### Step 3: Call via service ID

~~~bash
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
~~~

Record `instanceId` from the responses. If only one ID appears, check the candidate list before concluding the algorithm is broken.

### Step 4: Stop one replica to observe failure

Stop port `8082` and call again. With a static source and no health checks, some requests may fail because the address is still configured. This experiment demonstrates that **`@LoadBalanced` selects instances; it does not guarantee every selected instance is healthy**.

### Step 5: Evaluate timeouts and retries

Configure reasonable timeouts, test a slow-responding replica, and record error timings and request send counts. Never use uncontrolled retries to mask a stale instance list.

### Step 6: Record results

| Check | Expectation |
|---|---|
| Direct requests to 8081 and 8082 | Both endpoints return distinct identities |
| Request via `http://inventory-service` | Caller is processed through LoadBalancer |
| Repeating multiple requests | Multiple selected instances can be observed |
| Stopping one replica with static discovery | Errors can occur without health/discovery refresh |
| Enabling proper timeouts | Hung requests terminate according to policy |
| Correlating logs | Know the service ID, actual instance, and error reason |

## 13. Production checklist

Before deploying a `@LoadBalanced` `RestClient.Builder` to a real environment, check:

- **Versions:** Spring Boot/Spring Cloud support `RestClient` and compatible LoadBalancer integration.
- **Beans:** the builder has `@Bean` + `@LoadBalanced`, is picked up by component scan, and is injected in the right places.
- **Service ID:** the logical hostname in the URI matches the registered service.
- **Discovery:** a `ServiceInstance` source exists with appropriate freshness.
- **HTTP:** request factory, connection pooling, TLS, headers, serialization, and timeouts are defined.
- **Retries:** bounded attempts/backoff, avoiding duplicate side effects on non-idempotent methods.
- **Health:** a mechanism exists to detect or exclude unavailable instances.
- **Observability:** ability to correlate service ID, selected instance address, attempt count, duration, and errors.
- **Fallback:** behavior when no instances exist is clearly handled at the application layer.
- **Security:** no sensitive data in logs; internal diagnostic endpoints are not unnecessarily exposed.

## 14. Summary

- A default `RestClient.Builder` builds synchronous HTTP clients without service discovery or load balancing.
- A bean annotated with `@LoadBalanced` enables Spring Cloud to integrate `ServiceInstance` selection when the client calls URIs containing a **service ID**.
- With `@LoadBalanced RestClient.Builder`, build a `RestClient` using `baseUrl("http://inventory-service")` and reuse the built client.
- When both direct and load-balanced HTTP clients exist, differentiate beans with `@LoadBalanced`, `@Qualifier`, or `@Primary`.
- `@LoadBalanced` **does not automatically configure timeouts, retries, health checks, or business policies**; those must be designed separately.
- Verify end-to-end using multiple replicas with endpoints returning an instance ID, and inspect both the candidate list and HTTP results.

A proper `RestClient.Builder` configuration is the starting point for callers to invoke services by logical name. Reliable communication is only achieved by combining that builder with accurate discovery, a suitable supplier chain, instance selection, sensible timeouts/retries, and thorough error observability.
