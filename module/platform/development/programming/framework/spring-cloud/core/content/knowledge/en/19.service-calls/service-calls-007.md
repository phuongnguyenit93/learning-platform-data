# Creating a WebClient.Builder with a Load Balancer Filter

This lesson belongs to the **Service Calls** chapter of the **SPRING_CLOUD_CORE** module. In Spring WebFlux applications, `WebClient` is the reactive HTTP client for calling other services' APIs. When combined with Spring Cloud LoadBalancer, a `WebClient.Builder` marked with `@LoadBalanced` is wired with an instance-selection filter. The application can call services by service ID, while LoadBalancer finds an appropriate instance and replaces the logical URI with the actual address before sending the request.

Configuring the builder properly is critical. A load-balanced builder must have Spring Cloud LoadBalancer on the classpath, use URIs containing a service ID, be injected with the right qualifier, and preserve customizers supplied by Spring Boot. If the application also calls external endpoints using ordinary hostnames, separate the load-balanced builder from the regular HTTP builder to avoid accidentally routing external requests through service discovery.

## 1. Learning outcomes

After this lesson, you can:

1. Explain the roles of `WebClient`, `WebClient.Builder`, and `ExchangeFilterFunction`.
2. Configure a `WebClient.Builder` bean with the `@LoadBalanced` qualifier.
3. Add compatible Spring Cloud LoadBalancer and Spring WebFlux dependencies.
4. Inject the load-balanced builder properly into service clients.
5. Call services using URIs with a service ID instead of an instance's IP/hostname.
6. Describe how the filter translates a logical URI into the selected instance's address.
7. Preserve Spring Boot's `WebClientCustomizer`s when creating a builder manually.
8. Distinguish a load-balanced builder from a regular HTTP builder.
9. Use `ReactorLoadBalancerExchangeFilterFunction` when attaching the filter explicitly.
10. Customize LoadBalancer configuration per service ID and inspect how discovery supplies instances.
11. Test instance selection, error handling, timeouts, and retries for reactive calls.
12. Diagnose errors caused by missing starters, wrong service IDs, missing instances, or injecting the wrong builder.

## 2. WebClient and the load balancer filter

### 2.1. WebClient.Builder creates HTTP clients

`WebClient` is an HTTP client supporting reactive APIs. Applications typically create the client using a builder:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com")
        .build();
~~~

`WebClient.Builder` allows configuring the base URL, default headers, codecs, connectors, and filters. After calling `build()`, the application receives an immutable, configured `WebClient` for reuse.

In Spring Boot applications, the builder is usually configured by auto-configured customizers. They can add observability, codecs, connectors, or application-wide settings. When declaring a builder bean manually, decide whether to apply those customizers.

### 2.2. ExchangeFilterFunction intercepts requests

`ExchangeFilterFunction` sits in WebClient's request processing chain. A filter can inspect requests, modify headers, log, measure timing, handle authentication, or route requests through another mechanism before calling the HTTP connector.

Spring Cloud LoadBalancer integrates with WebClient via a reactive filter. The filter receives a URI containing a service ID, asks LoadBalancer to pick a `ServiceInstance`, and builds a request targeting that instance's physical address.

Example logical request:

~~~text
http://inventory-service/api/items/42
~~~

If the registry has two instances:

~~~text
inventory-service
  ├── http://10.20.0.11:8080
  └── http://10.20.0.12:8080
~~~

LoadBalancer selects an instance—for example, the second instance—and sends the request to:

~~~text
http://10.20.0.12:8080/api/items/42
~~~

Service-calling code only needs to know the service ID. It does not need to query the registry itself or store individual instance addresses.

### 2.3. Processing flow

~~~mermaid
sequenceDiagram
    participant App as Service caller
    participant WC as WebClient
    participant Filter as LoadBalancer filter
    participant LB as ReactiveLoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Registry as Discovery / registry
    participant Instance as Selected instance

    App->>WC: GET http://inventory-service/api/items/42
    WC->>Filter: Exchange request
    Filter->>LB: Select instance by service ID
    LB->>Supplier: Fetch instance list
    Supplier->>Registry: Query/cached discovery data
    Registry-->>Supplier: ServiceInstance list
    Supplier-->>LB: Instance list
    LB-->>Filter: Selected instance
    Filter->>Instance: Send request to actual host:port
    Instance-->>App: HTTP response
~~~

In a standard discovery-backed setup, `ServiceInstanceListSupplier` fetches instances from DiscoveryClient and may then apply caching or filters. LoadBalancer chooses an instance from the received list.

## 3. Required dependencies

To use `@LoadBalanced WebClient.Builder`, the application needs both WebFlux and a Spring Cloud LoadBalancer implementation.

With Maven, common dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

The Spring Cloud starter should be managed by a Spring Cloud BOM compatible with the project's Spring Boot version. Do not pick an independent starter version if the project already imports `spring-cloud-dependencies`.

If instances are obtained from Eureka, Consul, or Zookeeper, add the corresponding discovery starter. Without a registry-backed DiscoveryClient, Spring Cloud Commons can use `SimpleDiscoveryClient` with a statically configured URI list, suitable for local development or testing.

Gradle configuration example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

You do not need to add an entire discovery provider if your task only requires testing with a static instance list. Conversely, having the LoadBalancer starter does not create real instances by itself; the application still needs a `ServiceInstance` source.

## 4. Creating WebClient.Builder with @LoadBalanced

### 4.1. Basic configuration

The simplest way is to declare a `WebClient.Builder` bean and annotate it with `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`@LoadBalanced` is a qualifier annotation so Spring Cloud identifies builders needing LoadBalancer integration. Spring Cloud LoadBalancer provides the mechanism to process this builder and attach the corresponding reactive filter.

The annotation does not install a discovery provider automatically. A LoadBalancer implementation must be on the classpath along with an appropriate instance source.

### 4.2. Why annotate the bean method?

The qualifier must be attached to a Spring-managed bean. When a builder is created from a method without `@Bean`, Spring does not manage that object and cannot apply the integration's required post-processors/customizations.

Therefore, declaring the builder as a bean ensures:
- Spring manages the builder's lifecycle.
- Spring Cloud recognizes which bean needs load balancing.
- Service clients can inject the builder via the qualifier.
- Related configurations are applied consistently across the ApplicationContext.

### 4.3. Preserving Spring Boot's WebClientCustomizers

If you call `WebClient.builder()` yourself inside a bean method, you can bypass `WebClientCustomizer`s that Spring Boot auto-configured. To preserve available customizers, apply them in order:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }
}
~~~

`ObjectProvider` lets you retrieve available customizers without manually managing a list. `orderedStream()` preserves the application order arranged by Spring.

This approach is useful when the application needs to keep observability, codecs, or shared Spring Boot WebClient configuration while still creating a builder with the load-balanced qualifier.

## 5. Injecting the builder and creating service clients

### 5.1. Injecting by qualifier

When the application has a load-balanced builder, you can inject the builder annotated with `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<Item> getItem(String itemId) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{id}", itemId)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
~~~

This example demonstrates a client calling the inventory service by service ID. `InventoryClient` builds `WebClient` once in its constructor and reuses it for subsequent requests.

`WebClient` is immutable once built, making it suitable as a long-lived dependency of a service client. You do not need to call `builder.build()` per request if client configuration does not change.

### 5.2. Using a URI with a service ID

URIs should have the format:

~~~text
http://<service-id>/<path>
~~~

Example:

~~~java
webClient.get()
        .uri("http://pricing-service/api/prices/{sku}", sku)
        .retrieve()
        .bodyToMono(PriceResponse.class);
~~~

`pricing-service` is the service ID recognized by DiscoveryClient/ServiceInstanceListSupplier. It is not a Java class name, nor does it have to be a directly resolvable DNS hostname.

Do not replace the URI with a single instance's IP/port if you want LoadBalancer to select instances. When using a fixed physical address, the filter no longer has a service ID to perform selection.

### 5.3. Using a URI builder with query parameters

~~~java
public Mono<List<Item>> search(String category, int page) {
    return webClient.get()
            .uri(uriBuilder -> uriBuilder
                    .scheme("http")
                    .host("inventory-service")
                    .path("/api/items")
                    .queryParam("category", category)
                    .queryParam("page", page)
                    .build())
            .retrieve()
            .bodyToFlux(Item.class)
            .collectList();
}
~~~

The crucial point is that the authority must still contain the service ID. The LoadBalancer filter needs to recognize the logical host accurately before forwarding the request to a physical instance.

## 6. Separating load-balanced and regular builders

An application may both call internal services by service ID and call external APIs such as a payment gateway or public API. The two request types serve different purposes:

- Internal requests use a service ID and need LoadBalancer.
- External requests use a real hostname/URI and do not need internal discovery.

Declare two separate builders so code expresses intent clearly.

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    @Primary
    public WebClient.Builder webClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Services needing LoadBalancer inject the qualifier:

~~~java
public InventoryClient(
        @LoadBalanced WebClient.Builder builder) {
    this.webClient = builder.build();
}
~~~

Clients calling external APIs inject the regular builder:

~~~java
public PaymentGatewayClient(WebClient.Builder builder) {
    this.webClient = builder
            .baseUrl("https://payments.example.com")
            .build();
}
~~~

`@Primary` on the regular builder resolves unqualified injection when multiple beans share the same type. In code calling internal services, always use `@LoadBalanced` to avoid injecting the wrong builder.

In production configurations, if both builders need observability/customizations, apply `WebClientCustomizer`s following the same pattern as in the previous section.

## 7. Manually attaching a filter with ReactorLoadBalancerExchangeFilterFunction

Besides annotating a builder bean with `@LoadBalanced`, Spring Cloud LoadBalancer also provides a reactive filter that can be injected directly:

`ReactorLoadBalancerExchangeFilterFunction`

When `spring-cloud-starter-loadbalancer` and `spring-webflux` are on the classpath, Spring Cloud can auto-configure this filter.

Example:

~~~java
import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancerExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class ManualLoadBalancedClient {

    private final WebClient webClient;

    public ManualLoadBalancedClient(
            ReactorLoadBalancerExchangeFilterFunction loadBalancerFilter) {

        this.webClient = WebClient.builder()
                .filter(loadBalancerFilter)
                .build();
    }

    public Mono<String> getInventory() {
        return webClient.get()
                .uri("http://inventory-service/api/inventory")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

This approach shows explicitly which filter is attached to the builder. It is useful when only one specific client needs load balancing or when constructing `WebClient` programmatically.

However, if many service clients all need the same integration, a builder bean annotated with `@LoadBalanced` is usually easier to manage and inject. Avoid manually attaching the same filter multiple times to one builder, as it can send requests through duplicate processing steps unintentionally.

### 7.1. Do not confuse the reactive filter with the legacy filter

Spring Cloud has older filter APIs that use a non-reactive LoadBalancer client underneath. For WebFlux applications, prefer `ReactorLoadBalancerExchangeFilterFunction` so `ReactiveLoadBalancer` is used.

The non-reactive `LoadBalancerExchangeFilterFunction` is marked deprecated in current documentation. Do not choose the legacy API for new applications unless there is a specific compatibility reason.

## 8. Where does LoadBalancer find instances?

### 8.1. Discovery-backed service instances

In typical configurations, LoadBalancer uses `ServiceInstanceListSupplier` to retrieve instances. The supplier can use a DiscoveryClient provider such as Eureka, Consul, or Zookeeper.

High-level flow:

1. WebClient sends a request containing a service ID.
2. LoadBalancer resolves the client by service ID.
3. ServiceInstanceListSupplier fetches the instance list.
4. ReactiveLoadBalancer picks an instance according to its strategy.
5. The filter replaces the logical URI with the instance's URI.
6. WebClient sends the HTTP request.

Spring Cloud provides strategies such as round-robin and random. Exact configuration depends on the release train and the service's LoadBalancer client.

### 8.2. SimpleDiscoveryClient for local/test

If you do not want to run a registry locally, you can declare static instances:

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

When calling `http://inventory-service/...`, LoadBalancer can choose one of the configured URIs. This approach is useful for integration tests or simple development environments.

If a registry-backed DiscoveryClient is on the classpath, that provider usually takes precedence via auto-configuration. Verify the actual instance source rather than assuming `SimpleDiscoveryClient` configuration always overrides a registry.

### 8.3. Service IDs must match

If the request uses:

~~~text
http://inventory-service/api/items
~~~

then the instance source must register the matching service ID. Common pitfalls:
- Service registers as `inventory` while client calls `inventory-service`.
- Wrong namespace or profile.
- Registry does not yet have healthy instances.
- Discovery provider was not auto-configured.
- Supplier cache has not refreshed after topology changed.

The service ID must agree between the registering side and the calling side.

## 9. Customizing LoadBalancer per service ID

Spring Cloud allows declaring custom LoadBalancer configuration for a service via `@LoadBalancerClient`:

~~~java
@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`name` is the service ID to which the custom configuration applies. `InventoryLoadBalancerConfiguration` can declare a `ReactorLoadBalancer` or `ServiceInstanceListSupplier` tailored to requirements.

Custom configuration examples must be organized carefully:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId,
                        ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

The class passed to `@LoadBalancerClient` should not be picked up by component-scan as an unintended global configuration. Spring Cloud documentation recommends leaving this configuration class without `@Configuration` or placing it outside component-scan scope to prevent beans from applying to the entire main context.

Only customize the algorithm when there is a clear requirement. Default round-robin is usually sufficient for basic scenarios.

## 10. Handling HTTP errors and timeouts

Load balancing only selects an instance. It does not replace HTTP client error handling.

### 10.1. Handling error statuses

`retrieve()` converts HTTP 4xx/5xx statuses into reactive errors if no custom handler is present. You can map errors:

~~~java
public Mono<Item> getItem(String itemId) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{id}", itemId)
            .retrieve()
            .onStatus(
                    status -> status.is4xxClientError(),
                    response -> response.createException())
            .onStatus(
                    status -> status.is5xxServerError(),
                    response -> response.createException())
            .bodyToMono(Item.class);
}
~~~

The application can translate these errors into domain exceptions, log correlation IDs, or return an appropriate response to the caller. Do not log entire bodies if responses might contain sensitive data.

### 10.2. Timeouts

You can bound the duration of a call:

~~~java
public Mono<Item> getItem(String itemId) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{id}", itemId)
            .retrieve()
            .bodyToMono(Item.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

A Reactor pipeline timeout does not mean all socket-level timeouts are configured. For production needs, configure appropriate timeouts on the HTTP connector and verify wait times of LoadBalancer/discovery providers.

### 10.3. Retries must respect semantics

Spring Cloud LoadBalancer supports retries for reactive WebClient via configuration such as:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

Retries can help when an instance temporarily fails to respond, but not every request is safe to resend. Only retry idempotent operations or requests with an appropriate idempotency key. Bound attempt counts, total deadlines, and backoff to avoid amplifying load when a service is failing.

Do not confuse Spring Cloud LoadBalancer retries with Reactor `retryWhen` added manually at the business layer. Enabling both can multiply the total request count beyond expectations.

## 11. Other WebClient filters and application order

A WebClient can have multiple filters:

- LoadBalancer filter to translate a service ID into an instance.
- Authentication filter to attach tokens.
- Correlation filter to propagate trace/correlation IDs.
- Logging/metrics filter to observe requests.
- Error mapping filter to standardize errors.

Example filter adding a correlation ID:

~~~java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Correlation-Id", UUID.randomUUID().toString())
                    .build();

            return next.exchange(updated);
        };
~~~

You can attach filters to the builder:

~~~java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(loadBalancerFilter)
        .build();
~~~

Filter order affects requests/responses passing through the chain. With custom filters, avoid modifying the host/service ID in a way that prevents LoadBalancer from recognizing the request. Do not manually resolve the service ID to an IP before the LoadBalancer filter runs.

If you need to add headers based on the selected instance, Spring Cloud LoadBalancer provides `LoadBalancerClientRequestTransformer` for WebClient. The transformer receives both the request and the selected `ServiceInstance`, making it better suited for logic that needs the final instance details.

## 12. Testing a load-balanced WebClient.Builder

### 12.1. Checking bean qualifiers

An integration test can verify that the load-balanced builder is registered:

~~~java
@Autowired
@LoadBalanced
WebClient.Builder loadBalancedBuilder;

@Test
void loadBalancedBuilderIsAvailable() {
    assertThat(loadBalancedBuilder).isNotNull();
}
~~~

This test only confirms the bean is injected. It does not prove the filter can locate instances or that requests are routed to the right host.

### 12.2. Testing with SimpleDiscoveryClient

Configure a test with two instances:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Start two HTTP stub servers on those two ports. Each server returns a distinct identifier, such as `instance-1` and `instance-2`.

Invoke multiple times:

~~~java
Flux<String> responses = Flux.range(0, 10)
        .flatMap(index -> inventoryClient.getInstanceMarker());
~~~

Verify:
- Requests use the service ID `inventory-service`.
- The filter replaces the URI with one of the two test host/ports.
- Responses come from valid instances.
- No request targets the logical hostname as if it were a real DNS host.
- When the instance list is empty, errors propagate to the caller as expected.

If the default algorithm is round-robin, tests can observe distribution across multiple requests, but should not assert strict ordering when caching, concurrency, or configuration changes are present.

### 12.3. Testing the regular builder

Spin up an additional HTTP test server with an ordinary hostname/URI. Call it with the non-`@LoadBalanced` builder and verify requests go straight to that endpoint.

This test helps detect accidental injection of the wrong builder causing external URLs to be passed to service discovery.

### 12.4. Testing errors and timeouts

Include cases for:

1. Non-existent service ID.
2. Registry returns an empty list.
3. An instance fails to respond.
4. Instance returns HTTP 4xx/5xx.
5. Request exceeds timeout.
6. Retries are enabled and only execute for safe operations.
7. Discovery provider is temporarily unreachable.

Tests should verify both reactive signals and relevant logs/metrics, rather than merely checking that a method returns a `Mono`.

## 13. Common errors and fixes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Cannot inject `@LoadBalanced WebClient.Builder` | Missing Spring Cloud LoadBalancer starter or WebFlux integration not auto-configured. | Check `spring-cloud-starter-loadbalancer`, `spring-webflux`, and dependency tree. |
| Builder bean exists but request throws UnknownHost | URI uses service ID but LoadBalancer filter is not attached. | Check qualifiers and which builder bean is actually injected. |
| Request calls wrong host | Code injects regular builder instead of load-balanced builder. | Use `@LoadBalanced` qualifier at the injection point. |
| No instance found | Service ID mismatch, registry has no instances yet, or provider inactive. | Check service ID, DiscoveryClient, and instance list. |
| Request directly calls service ID hostname | Filter not installed or request does not go through load-balanced builder. | Check filter chain and how WebClient is built. |
| Observability/customizers lost | Manually created builder skips `WebClientCustomizer`s. | Apply customizers via `ObjectProvider` in order. |
| External API treated as service discovery | Load-balanced builder mistakenly used for external hostname. | Create a separate regular builder and inject with explicit qualifiers. |
| Requests not evenly distributed | LoadBalancer cache, concurrency, instance list, or customized algorithm. | Check supplier, cache, and client configuration. |
| 503 error or no server instance | Supplier could not obtain suitable instances. | Check registry, service health, and service ID. |
| WebClient still blocks | An underlying dependency/provider performs blocking I/O. | Check implementations and avoid blocking on the Reactor event loop. |
| Retries amplify load | Retries stacked with retryWhen or applied to non-idempotent requests. | Cap retries, set overall deadlines, and restrict to safe operations. |
| @LoadBalancerClient config has no effect | Configuration class component-scanned into main context or service ID mismatch. | Keep class outside component scan and verify service name. |

## 14. Implementation principles

1. **Use matching starters.** WebClient needs Spring WebFlux; load balancing needs a Spring Cloud LoadBalancer implementation.
2. **Declare the builder as a bean.** Annotate the bean with `@LoadBalanced` so Spring Cloud integrates the filter.
3. **Inject with the right qualifier.** Do not use the regular builder for service ID requests.
4. **Call by service ID.** Logical URIs must match the ID in the discovery source.
5. **Separate internal and external clients.** Use separate builders when both HTTP call types are needed.
6. **Keep Boot customizers.** Apply `WebClientCustomizer`s in order if building the builder manually.
7. **Prefer the reactive filter.** Use `ReactorLoadBalancerExchangeFilterFunction` for WebFlux.
8. **Do not resolve addresses manually.** Let LoadBalancer handle instance selection and URI replacement.
9. **Design bounded timeouts/retries.** Do not unconditionally retry write operations.
10. **Test with mock instances.** Use SimpleDiscoveryClient or a test provider to verify URIs are translated properly.
11. **Observe requests.** Record correlation ID, service ID, outcome, and latency; avoid logging sensitive tokens/bodies.
12. **Verify against the release train.** Check compatible Spring Boot, Spring Cloud Commons, and LoadBalancer BOM versions before upgrading.

## 15. Completion checklist

- [ ] Can explain WebClient, WebClient.Builder, and ExchangeFilterFunction.
- [ ] Added spring-boot-starter-webflux and spring-cloud-starter-loadbalancer.
- [ ] Imported a compatible Spring Cloud BOM.
- [ ] Created a WebClient.Builder bean annotated with @LoadBalanced.
- [ ] Injected the builder via the @LoadBalanced qualifier.
- [ ] Used URIs with service IDs instead of instance addresses.
- [ ] Understood how the filter uses ReactiveLoadBalancer to select a ServiceInstance.
- [ ] Applied WebClientCustomizer if creating the builder manually.
- [ ] Distinguished load-balanced builders from regular builders.
- [ ] Know how to attach ReactorLoadBalancerExchangeFilterFunction manually.
- [ ] Avoided deprecated non-reactive filters for new apps unless required for compatibility.
- [ ] Verified service IDs and instance sources from DiscoveryClient/SimpleDiscoveryClient.
- [ ] Know how to customize LoadBalancer per service ID.
- [ ] Configured timeouts, error handling, and bounded retries.
- [ ] Wrote tests verifying URIs route to real instances and external clients are not load-balanced.
- [ ] Checked observability, security, and release train compatibility.

**Official documentation to cross-check for your project version:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): integrating WebClient with the @LoadBalanced qualifier and LoadBalancer implementation requirements.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ReactiveLoadBalancer, WebClient filters, suppliers, caching, and per-service-ID configuration.
- [Spring – Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/): examples of WebClient.Builder, filters, and calling services by service ID.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): how to create and attach ExchangeFilterFunction.

Class names, auto-configuration, and behaviors may vary across Spring Cloud release trains. Verify the BOM dependencies, confirm the builder has the right filter attached, and run integration tests with at least two service instances before deploying.