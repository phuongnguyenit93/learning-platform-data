# Applying @RefreshScope to Beans and Its Relationship with Singletons

> **Chapter:** Refresh Scope  
> **Module:** SPRING_CLOUD_CORE

In Spring, beans by default typically have **`singleton`** scope: one shared instance per bean definition within an `ApplicationContext`. This suits stateless services, repositories, and many infrastructure components. However, some beans hold configuration values that are allowed to change while the application is running—such as a dependent service endpoint, a timeout, or a set of operational parameters.

Spring Cloud Context provides **`@RefreshScope`** to manage the lifecycle of beans that need to be recreated after configuration is refreshed. It works via a **scoped proxy**: other beans can hold a stable proxy reference, while the target behind the proxy is destroyed and recreated on refresh. Understanding this relationship helps prevent a common mistake: singletons keeping stale values even after the configuration bean has been refreshed.

## 1. What Is a Singleton and Why Can Configuration Become Stale?

When a Spring bean does not declare another scope, the default scope is `singleton`. Spring creates one instance per bean definition in an `ApplicationContext` and reuses that instance wherever it is injected.

Example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogSettings {

    private final String baseUrl;

    public CatalogSettings(
            @Value("${catalog.client.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

If `CatalogSettings` is a default singleton, its constructor runs when the bean is created and the `baseUrl` value is stored in a field. When the external configuration source changes, Spring does not automatically re-invoke that singleton's constructor. Even if `Environment` is updated, the already-assigned field still holds the old value.

This is a normal characteristic of dependency injection: a value read at bean creation time does not automatically turn into a live binding to the property source.

### 1.1. When Is Singleton the Right Choice?

Singleton is appropriate when a bean:

- Does not hold state that changes per request or per user.
- Can be safely shared across multiple threads.
- Does not need to be recreated just because a few configuration properties change.
- Has a lifecycle aligned with the `ApplicationContext`.

Most business services should remain singletons and stateless. Do not put `@RefreshScope` on every bean in the application just because the application uses Config Server. Refresh scope carries lifecycle management overhead and can lose internal target state when the target is replaced.

## 2. `@RefreshScope` Is a Separate Scope with a Scoped Proxy

`@RefreshScope` belongs to Spring Cloud Context, in the package `org.springframework.cloud.context.config.annotation`. This annotation marks a bean as using the `refresh` scope and creates a proxy so other components can interact with the bean.

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final URI baseUri;

    public CatalogEndpoint(
            @Value("\${catalog.client.base-url}") URI baseUri) {
        this.baseUri = baseUri;
    }

    public URI baseUri() {
        return baseUri;
    }

    public String currentEndpoint() {
        return baseUri.toString();
    }
}
~~~

When this bean is injected into another bean, the recipient typically holds a **proxy**. The proxy forwards method calls to the current target in the refresh scope. Targets are managed in the scope's cache.

You can visualize it like this:

~~~mermaid
flowchart LR
    S["Singleton bean\nCatalogGateway"]
    P["Scoped proxy\nCatalogEndpoint"]
    C["RefreshScope cache"]
    T["Current target\nCatalogEndpoint"]
    S -->|"holds reference"| P
    P -->|"looks up target"| C
    C --> T
    R["Refresh event"] -->|"invalidate target"| C
    C -. "next call creates new target" .-> N["New target"]
~~~

**The proxy and the target are two distinct objects:**

- The proxy is the access point held by the singleton.
- The target is the instance performing the work.
- Refresh scope manages the target and caches the target.
- When the target is refreshed, the proxy can stay the same; the next call obtains the new target.

In normal usage, a refresh-scoped bean is initialized when first invoked through the proxy and the target is cached for reuse. When the cache is refreshed, the old target is evicted per scope mechanics and a new target is created on the next call.

## 3. Relationship Between Singletons and Refresh-Scoped Beans

Suppose `CatalogGateway` is a singleton and injects the `@RefreshScope`-annotated `CatalogEndpoint`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final CatalogEndpoint endpoint;

    public CatalogGateway(CatalogEndpoint endpoint) {
        this.endpoint = endpoint;
    }

    public String endpointForRequest() {
        return endpoint.currentEndpoint();
    }
}
~~~

At the time `CatalogGateway` is created, Spring injects the scoped proxy of `CatalogEndpoint`. The singleton holds a reference to that proxy throughout its lifecycle.

When `endpointForRequest()` is called, the proxy looks up the current target and forwards the call. After a refresh, the old target is evicted from the refresh scope. `CatalogGateway` does not need to be recreated; the next call still goes through the same proxy, which resolves the new target.

### 3.1. Lifecycle Table

| Moment | Singleton `CatalogGateway` | Proxy `CatalogEndpoint` | Refresh-scoped target |
| --- | --- | --- | --- |
| Context startup | Created | Injected into singleton | May not be created until the first call |
| First call | Unchanged | Forwards call | Created and cached |
| Subsequent calls | Unchanged | Still the same proxy | Reuses cached target |
| After refresh | Still the old instance | Still the same proxy | Old target is evicted |
| Call after refresh | Still the old instance | Looks up new target | New target is created and cached |

The key takeaway is that **the singleton holds the proxy, not the target directly**. This is why a singleton can continue seeing new configuration without having to reinitialize the singleton itself.

### 3.2. Do Not Copy Values from the Proxy into a Singleton Field

The following example easily causes a stale configuration bug:

~~~java
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final URI baseUri;

    public CatalogGateway(CatalogEndpoint endpoint) {
        // Calls the proxy immediately when the singleton is created and copies the value.
        this.baseUri = endpoint.baseUri();
    }

    public URI baseUri() {
        return baseUri;
    }
}
~~~

Even though `CatalogEndpoint` is refresh-scoped, `CatalogGateway` called the proxy in its constructor and copied the URI into a singleton field. After a refresh, the new target of `CatalogEndpoint` has the new URI, but the `baseUri` field in `CatalogGateway` still retains the old value.

The right approach is to keep the proxy and call the configuration-reading method at the time of use, or make the consuming bean refreshable too if it must rebuild internal state.

~~~java
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final CatalogEndpoint endpoint;

    public CatalogGateway(CatalogEndpoint endpoint) {
        this.endpoint = endpoint;
    }

    public URI currentBaseUri() {
        // Call through the proxy at the time of use.
        return endpoint.baseUri();
    }
}
~~~

Do not store a snapshot of a refresh-scoped value inside a singleton if you expect it to change upon refresh.

## 4. Complete Example: Changing the Catalog Endpoint While the Application Is Running

Suppose `order-service` calls `catalog-service`. The catalog endpoint is centrally managed and can change across environments or infrastructure migrations.

### 4.1. Declaring Initial Configuration

`application.yml`:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog-v1.internal"
~~~

This value can be overridden by profiles, environment variables, or Spring Cloud Config according to property source precedence.

### 4.2. Creating a Refreshable Configuration Bean

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final URI baseUri;

    public CatalogEndpoint(
            @Value("${catalog.client.base-url}") URI baseUri) {
        this.baseUri = baseUri;
    }

    public URI baseUri() {
        return baseUri;
    }

    public URI productUri(String productId) {
        return UriComponentsBuilder.fromUri(baseUri)
                .pathSegment("api", "products", productId)
                .build()
                .encode()
                .toUri();
    }
}
~~~

The `CatalogEndpoint` target reads `catalog.client.base-url` when created. After `Environment` is updated and the refresh scope is refreshed, a new target will be created with the new value.

### 4.3. Singleton Service Using the Proxy

~~~java
import java.net.URI;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {

    private final WebClient client;
    private final CatalogEndpoint endpoint;

    public CatalogGateway(
            WebClient.Builder builder,
            CatalogEndpoint endpoint) {
        this.client = builder.build();
        this.endpoint = endpoint;
    }

    public Mono<String> findProduct(String productId) {
        return client.get()
                .uri(endpoint.productUri(productId))
                .retrieve()
                .bodyToMono(String.class);
    }

    public URI currentBaseUri() {
        return endpoint.baseUri();
    }
}
~~~

`CatalogGateway` is a singleton. It holds the `CatalogEndpoint` proxy and calls `endpoint.productUri(productId)` for each request. When the endpoint target is refreshed, the next call through the proxy fetches the URI from the new target.

This example assumes the application already has `WebClient.Builder` from Spring Boot WebFlux auto-configuration and the required dependencies. In a real project, you must configure timeouts, error handling, tracing, and authentication separately for the HTTP client.

### 4.4. What Happens During a Refresh?

Suppose configuration changes from:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v1.internal"
~~~

to:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v2.internal"
~~~

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant Config as Config Server / Config Source
    participant Context as Spring Environment
    participant Scope as RefreshScope
    participant Proxy as CatalogEndpoint proxy
    participant Target as CatalogEndpoint target
    participant Gateway as Singleton CatalogGateway

    Config-->>Context: New base-url configuration
    Context->>Context: Update property sources
    Context->>Scope: Refresh scope / invalidate target
    Scope->>Target: Destroy old target
    Note over Gateway,Proxy: Singleton and proxy remain intact
    Gateway->>Proxy: findProduct(...)
    Proxy->>Scope: Get current target
    Scope->>Target: Create new target when needed
    Target-->>Proxy: URI from new configuration
    Proxy-->>Gateway: Return new URI
~~~

The exact order of loading configuration, updating `Environment`, and publishing refresh events depends on the mechanism used—such as Spring Cloud Config Client, the Actuator refresh endpoint, or Spring Cloud Bus. The diagram illustrates the relationship between `Environment` and refresh scope; it does not assert that a specific endpoint is always enabled.

## 5. Triggering Refresh and the Role of `@RefreshScope`

`@RefreshScope` specifies that a bean has its own scope and can be refreshed when the refresh scope receives a refresh command. The annotation **does not automatically watch files**, does not automatically poll Config Server, and does not automatically detect changes in an external system.

A typical refresh flow includes:

1. The configuration source is updated, or Config Client fetches new configuration.
2. The refresh mechanism updates `Environment`/property sources.
3. Refresh scope receives a refresh request and evicts cached targets.
4. When the bean is next invoked, the proxy requests a new target.
5. The new target is created and binds/resolves current configuration values.

In some applications with Actuator and Spring Cloud Context, a refresh endpoint may be enabled to receive refresh operations, such as `POST /actuator/refresh`. This endpoint needs appropriate exposure, authentication, and authorization configuration. If using Spring Cloud Bus, an event can be broadcast to multiple instances; exact behavior and endpoints depend on Bus dependencies and configuration.

You can use the `RefreshScope.refreshAll()` API in administrative code or tests to invalidate all targets in the scope. Do not call refresh arbitrarily on every business request; refresh is a lifecycle-management operation and can cause targets to be recreated.

### 5.1. Refreshing Environment and Refreshing Beans Are Two Distinct Steps

Distinguish between:

- **Environment refresh:** the configuration source is reloaded or property sources are updated.
- **Refresh scope:** targets of annotated beans are invalidated so they can be recreated.
- **Singleton refresh:** default singletons are not automatically recreated just because refresh scope runs.

If you only call `RefreshScope.refreshAll()` without updating `Environment`, the new target may still read the same old value. Conversely, if `Environment` changed but a singleton bean stored a snapshot in a field, that snapshot does not change on its own.

## 6. When Should You Apply `@RefreshScope`?

Consider refresh scope for beans with these characteristics:

- Holds a group of configuration values that need to change while the application is running.
- Can be safely recreated from the new `Environment`.
- Does not hold long-lived business state that must survive a refresh.
- Is accessed through a proxy by other components.
- Can tolerate the old target being destroyed and a new target being created on the next call.

Suitable examples:

| Bean | Why it can be refreshed |
| --- | --- |
| Client endpoint settings | URLs or routing parameters may change |
| Timeout/retry parameter sets | Need to adjust service invocation policies |
| A lightweight client built from configuration | Can be recreated when endpoints or credentials change |
| Application-level feature settings | Values are re-read from the configuration source after refresh |

Do not apply refresh scope by default to:

- Business services holding workflow or transaction state.
- Repositories or transaction-managing beans with complex lifecycles.
- Beans holding large business caches where clearing the cache would cause data loss or traffic spikes.
- Objects holding threads, schedulers, or resources needing controlled shutdown without a designed destruction lifecycle.
- Every singleton in the application just to make "configuration auto-update."

If a bean needs to recreate resources, verify destruction callbacks, closing connections, stopping schedulers, and handling in-flight requests before the target is replaced.

## 7. Relationship with `@Configuration` and `@Bean` Beans

`@RefreshScope` can be placed on a component class or on a `@Bean` method.

Example using a bean method:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    @RefreshScope
    CatalogEndpoint catalogEndpoint(
            @Value("${catalog.client.base-url}") URI baseUri) {
        return new CatalogEndpoint(baseUri);
    }
}
~~~

When the scope is placed on the bean method, the bean created by that method is refresh-scoped.

A common misconception: putting `@RefreshScope` on a `@Configuration` class **does not mean every bean declared by `@Bean` methods inside that class automatically gets refresh scope**. If a specific bean needs to be refreshed, annotate that bean itself with `@RefreshScope` or explicitly design its scope.

Also remember that other singletons injecting a refresh-scoped bean will hold a proxy. If a singleton calls the proxy and uses the result immediately, it can see the new target. If the singleton copies the result into a field or builds an immutable infrastructure object from that value at initialization, that snapshot object may still remain stale.

## 8. Limitations and Common Pitfalls

### 8.1. Environment Changed, But the Singleton Still Has Old Values

The usual cause is that the singleton read the property via `@Value` in its constructor or field injection and stored the value. How to fix:

- Move the configuration group into a refresh-scoped bean.
- Inject the scoped proxy into the singleton.
- Call the proxy when the latest value is needed.
- If the singleton builds a client from configuration, consider refreshing that client itself or designing the client to read configuration through the proxy.

### 8.2. `@RefreshScope` Is Applied, But the Bean Does Not Update

Check:

- Was a refresh operation/event actually triggered?
- Did `Environment`/property sources receive the new value?
- Was the bean actually created in refresh scope?
- Is the consumer calling the proxy, or holding a copied target/value?
- Was the bean created from another factory method not annotated with refresh scope?
- Does a dependent singleton hold a stale cache or old client?

### 8.3. Losing State Inside the Bean

The old target is destroyed and a new target is created. Mutable fields that existed only inside the old target will not automatically transfer to the new target. Do not place business state that must be preserved inside a refresh-scoped bean; store state in a database or a component with an appropriate lifecycle.

### 8.4. Proxy Errors and `final` Classes

Refresh scope typically uses a scoped proxy to forward calls. Class-based proxies have inheritance constraints; `final` classes or methods can cause issues depending on the proxy type and configuration. If you encounter proxy creation errors, inspect the logs, bean type, interfaces, and proxy mode for your Spring Cloud version. Do not assume every Java type can be proxied the same way.

### 8.5. Concurrent Refresh Alongside In-Flight Requests

A request may have already started calling the old target before the refresh happened. Do not assume refresh will immediately halt all in-flight calls. For clients holding connections or resources, establish proper graceful shutdown, timeout, and error-handling policies so executing requests are not disrupted.

## 9. Testing the Relationship Between Singleton, Proxy, and Target

A useful test should prove three things:

1. The singleton consumer is created once and holds the proxy.
2. The initial target returns the old configuration value.
3. After updating `Environment` and refreshing the scope, that same consumer receives the value from the new target.

Example test in a Spring Boot test context:

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.core.env.ConfigurableEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "catalog.client.base-url=https://catalog-v1.internal"
})
class RefreshScopeSingletonTest {

    @Autowired
    CatalogGateway gateway;

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void singletonUsesNewTargetAfterRefresh() {
        URI first = gateway.currentBaseUri();

        assertThat(first)
                .isEqualTo(URI.create("https://catalog-v1.internal"));

        TestPropertyValues.of(
                "catalog.client.base-url=https://catalog-v2.internal"
        ).applyTo(environment);

        refreshScope.refreshAll();

        URI second = gateway.currentBaseUri();

        assertThat(second)
                .isEqualTo(URI.create("https://catalog-v2.internal"));
    }
}
~~~

This example assumes `CatalogGateway` is a singleton holding the `CatalogEndpoint` scoped proxy as shown earlier; `CatalogEndpoint` reads the property in its constructor. The test uses `TestPropertyValues` to update `Environment` before calling `refreshAll()`. In an isolated test context, refreshing all targets in the scope is appropriate; larger test suites may need context separation to avoid refreshing unrelated beans.

This test does not fully simulate Config Server loading remote configuration or Spring Cloud Bus broadcasting events. It focuses on the relationship between `Environment`, refresh scope, proxy, and singleton consumer.

### 9.1. Additional Test Scenarios

| Scenario | What to verify |
| --- | --- |
| First call to the bean | Target is created and configuration value is correct |
| Multiple calls before refresh | Target is reused, not recreated on every call |
| Update Environment then refresh | Subsequent call reads the new value |
| Refresh while singleton stays alive | Singleton consumer does not need to be recreated |
| Singleton stores snapshot in a field | Test proves the snapshot does not change automatically |
| Target has resources that need closing | Destruction callback executes according to the designed lifecycle |
| Configuration source unchanged, refresh runs | New target can still receive the same value |
| Environment changed without refreshing scope | Refresh-scoped bean may continue using the cached target until invalidated |

## 10. Adoption Workflow in a Spring Cloud Application

When a bean needs to change based on runtime configuration, you can follow these steps:

1. Identify exactly which properties need to change and which source provides them.
2. Choose a lightweight, recreatable bean that does not hold long-lived business state.
3. Apply `@RefreshScope` to the bean or bean method that needs refreshing.
4. Have singleton consumers inject the scoped proxy instead of injecting a snapshot.
5. Access values through the proxy at the time of use; avoid copying values into singleton fields.
6. Define the mechanism for updating `Environment` and emitting refresh events.
7. Protect refresh endpoints/events with appropriate authentication, authorization, and network policies.
8. Test the old target, new target, singleton consumer, and refresh failure cases.
9. Monitor logs/metrics to verify refresh succeeded and targets were recreated on time.

If an HTTP client or pool is built from configuration and cannot read values dynamically, place the client itself in refresh scope or build a factory that manages controlled client replacement. Do not just refresh a bean holding a URL string while another singleton already created the client and saved the old URL.

## 11. Conclusion

`@RefreshScope` creates a separate scope with a scoped proxy so targets can be invalidated and recreated after the application performs a refresh. When a singleton injects a refresh-scoped bean, the singleton keeps a stable proxy; the proxy forwards calls to the current target. Consequently, the singleton can continue using new configuration without needing to be recreated itself.

The crucial condition is that the consumer must keep calling through the proxy. If a singleton reads the value once and copies it into a field, or creates a client holding an old snapshot, refreshing the target cannot update that copied data. Use refresh scope for safely recreatable beans, distinguish updating `Environment` from invalidating targets, and test both the proxy-target lifecycle and singleton consumers in **SPRING_CLOUD_CORE** applications.
