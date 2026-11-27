# Version Requirements and Supported Auto-Configuration Scope

**Spring HTTP Interface** lets you declare an HTTP API using a Java interface with `@HttpExchange`, `@GetExchange`, `@PostExchange`, and related annotations, then invoke it through a proxy backed by `RestClient` or `WebClient`. However, **creating an HTTP proxy does not mean the proxy automatically uses Spring Cloud LoadBalancer**. Proxy registration, HTTP client configuration, and automatic `ServiceInstance` selection depend explicitly on the **Spring Framework, Spring Boot, and Spring Cloud generation**.

In the Spring Cloud LoadBalancer module, understanding version boundaries prevents three common mistakes:

1. Applying `@ImportHttpServices` or `spring.http.serviceclient.*` to a Spring Boot 3 / Spring Framework 6 project expecting Boot 4 auto-configuration.
2. Manually creating an HTTP Interface proxy while forgetting to attach LoadBalancer to the underlying `RestClient`/`WebClient`.
3. Assuming that merely setting `base-url: http://catalog-service` makes a Spring Cloud 5 HTTP Service group load-balance automatically — when in fact that setting **does not trigger the group LoadBalancer integration**.

This lesson belongs to the **HTTP Interface** chapter and focuses on version prerequisites, classpath/bean conditions, and the **actual supported auto-configuration scope**. Examples use a logical service `catalog-service` with multiple replicas provided by discovery.

## 1. Distinguishing Four Layers of Responsibility

Four components are often mentioned together, even though they are not the same feature:

| Layer | Technology | Responsibility |
|---|---|---|
| **HTTP contract declaration** | Spring Framework `@HttpExchange` / `@GetExchange` | Describes HTTP method, path, headers, parameters, body, and return type |
| **HTTP proxy creation** | `HttpServiceProxyFactory`; from Framework 7 onward, `@ImportHttpServices` and group registry | Generates the object implementing the interface so business code can inject and invoke it |
| **HTTP transport configuration** | `RestClient` / `WebClient`; from Boot 4 onward, HTTP Service group auto-configuration | Sets URL, timeouts, SSL, default headers, codecs, and executes HTTP |
| **Client-side load balancing** | Spring Cloud LoadBalancer, `ServiceInstanceListSupplier`, interceptor/filter | Resolves a service ID to retrieve and pick a `ServiceInstance` before sending the request |

~~~mermaid
flowchart TD
    A["Business code calls CatalogHttpApi"]
    B["HTTP Interface proxy"]
    C["Group's RestClient or WebClient"]
    D{"Does group/client have<br/>LoadBalancer integration?"}
    E["LoadBalancer selects ServiceInstance"]
    F["Use direct URL"]
    G["HTTP transport sends request"]
    H["Backend returns response"]
    A --> B --> C --> D
    D -->|"Yes"| E --> G
    D -->|"No"| F --> G
    G --> H
~~~

`@GetExchange` does not query Eureka directly; `@ImportHttpServices` does not provide a replica registry on its own. Calling by service ID requires both a `ServiceInstance` source and LoadBalancer integration on the executing HTTP client.

## 2. Compatibility Matrix Across Spring Generations

Support conditions should be evaluated by **specific capabilities**, rather than merely seeing an annotation on the classpath.

| Ecosystem | HTTP Interface Client | Automatic Group Registration | Auto-Integrated LoadBalancer for HTTP Service Group |
|---|---|---|---|
| **Spring Framework 6.0**, typically with Boot 3.0/3.1 | Has `@HttpExchange`, `HttpServiceProxyFactory`, and proxy creation via a matching adapter such as `WebClientAdapter` | **No `@ImportHttpServices` from Framework 7 yet** | No Spring Cloud LoadBalancer 5 group auto-config; configure client and proxy manually |
| **Spring Framework 6.1–6.x**, typically with Boot 3.2–3.x | Adds `RestClient` / `RestClientAdapter`; proxies can be configured manually with `RestClient` or `WebClient` | No Framework 7 group registry model | Use `@LoadBalanced RestClient.Builder` or `@LoadBalanced WebClient.Builder` with `HttpServiceProxyFactory` manually |
| **Spring Framework 7 + Spring Boot 4** | Has HTTP Interface, `@ImportHttpServices`, `HttpServiceProxyRegistry`, and HTTP Service groups | **Yes** — group proxy registration and group properties via `spring.http.serviceclient.<group>.*` | Not load-balanced by default without matching Spring Cloud integration |
| **Spring Framework 7 + Boot 4 + Spring Cloud LoadBalancer 5.0+** | All capabilities above | **Yes** | **Yes** — auto-configuration integration for HTTP Service groups subject to URL and bean/classpath conditions described below |

Key milestones from official documentation:

- Spring Framework **6.0** introduced HTTP Service Interface.
- Spring Framework **6.1** introduced `RestClient` and its corresponding HTTP Interface adapter.
- Spring Framework **7.0** introduced `@ImportHttpServices` and registry/group support for registering proxies as Spring beans.
- Spring Boot **4.0** provides group-based HTTP Service Clients auto-configuration.
- Spring Cloud LoadBalancer **5.0.0** introduced **automatic LoadBalancer integration for HTTP Service groups** via group configurers.

These are **per-feature milestones**, not a recommendation to mix versions arbitrarily. In practice, select a compatible Spring Boot/Spring Cloud release train via BOM rather than forcing Framework 7 into a Boot 3 project or Spring Cloud 5 into an unsupported combination.

## 3. Scope of HTTP Interface in Spring Framework 6

In Spring Framework 6, you can define an HTTP contract:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto findProduct(@PathVariable("id") Long id);
}

record ProductDto(Long id, String name) {}
~~~

The proxy uses whichever HTTP client you pass to `HttpServiceProxyFactory`. In Spring Framework 6.x projects, developers typically **create the factory and register proxy beans manually**, rather than relying on `@ImportHttpServices`.

### Spring Framework 6.1+ and RestClient Example

To use `RestClient` (available from Framework 6.1) with a compatible Spring Cloud LoadBalancer version:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class CatalogHttpInterfaceConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
            @LoadBalanced RestClient.Builder catalogLoadBalancedBuilder) {

        RestClient restClient = catalogLoadBalancedBuilder
                .baseUrl("http://catalog-service")
                .build();

        HttpServiceProxyFactory factory = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

This flow has two clear steps:

1. `@LoadBalanced RestClient.Builder` adds instance-selection capability to the HTTP client; `http://catalog-service` is the **logical** URL.
2. `HttpServiceProxyFactory` builds the `CatalogHttpApi` proxy; the proxy uses the **LoadBalancer-integrated** `RestClient` to make HTTP calls.

If you replace `catalogLoadBalancedBuilder` with a plain `RestClient.create("http://catalog-service")`, the proxy is still created, but the hostname may go through DNS instead of Spring Cloud LoadBalancer.

In Boot 3 applications, if you need Boot customizations such as observability, message converters, or tracing on the builder, pair with `RestClientBuilderConfigurer` rather than always calling raw `RestClient.builder()`. Proxy-building APIs evolved across Framework 6 minor versions; consult the docs for your exact compile version.

### What About WebClient?

Spring Framework 6.0 already supported HTTP Interface backed by `WebClientAdapter`. With `WebClient`, the architectural pattern is the same: create a `@LoadBalanced WebClient.Builder`, build a `WebClient` with `baseUrl("http://catalog-service")`, wrap it in the adapter, and build the proxy using your version's `HttpServiceProxyFactory` API.

Do not copy Framework 6.1 `RestClientAdapter` code into a Framework 6.0 project, because `RestClient` did not exist in 6.0.

**In short:** Spring Framework 6 supports HTTP Interface, but does not yet have **Framework 7 / Boot 4 automatic HTTP Service group registration**. Developers can still integrate LoadBalancer manually on the underlying HTTP client.

## 4. What Do Framework 7 and Boot 4 Auto-Configure?

Spring Framework 7 introduces `@ImportHttpServices`. This annotation identifies HTTP Interfaces to register and places them into **groups**. Each group can share HTTP client and proxy factory configuration.

Example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.service.registry.ImportHttpServices;

@SpringBootApplication
@ImportHttpServices(
        group = "catalog-service",
        types = CatalogHttpApi.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

With Boot 4 and the required modules on the classpath, HTTP Service client auto-configuration can:

- Create HTTP Interface proxies and register them as injectable Spring beans.
- Organize proxies by group via `HttpServiceProxyRegistry`.
- Configure a `RestClient` or `WebClient` for each group; `RestClient` is used by default when no other type is specified.
- Apply properties such as `base-url`, `connect-timeout`, `read-timeout`, SSL bundles, headers, or version-supported options.
- Allow fine-tuning via `RestClientHttpServiceGroupConfigurer` or `WebClientHttpServiceGroupConfigurer`.

**Boot 4 auto-config primarily manages proxies and HTTP clients**; it does not create server instances, enable retries, choose a LoadBalancer algorithm, provide Eureka/Consul, or guarantee endpoint health.

If `group` is omitted, the proxy joins a default group named **`default`**. When calling multiple service IDs, naming the group after the service ID avoids accidentally routing to a service named `default`.

### Group Property Configuration Example

~~~yaml
spring:
  http:
    clients:
      connect-timeout: 1s
    serviceclient:
      catalog-service:
        connect-timeout: 2s
        read-timeout: 3s
~~~

These properties belong to **Spring Boot 4's** `spring.http.*` hierarchy, not syntax that automatically takes effect for HTTP Interfaces in Boot 3.

Likewise, HTTP Service group properties **do not replace** `spring.cloud.loadbalancer.*`. One configures the HTTP client and proxy; the other configures instance selection, suppliers, health checks, and caching.

## 5. When Does Spring Cloud Auto-Attach LoadBalancer to an HTTP Service Group?

Starting in **Spring Cloud LoadBalancer 5.0.0**, Spring Cloud provides dedicated integration with HTTP Service Clients AutoConfiguration through two group configurers:

- `LoadBalancerRestClientHttpServiceGroupConfigurer` — for groups using `RestClient` (blocking).
- `LoadBalancerWebClientHttpServiceGroupConfigurer` — for groups using `WebClient` (reactive).

These components attach the matching LoadBalancer integration when the required beans exist in the application context:

- `DeferringLoadBalancerInterceptor` for `RestClient`.
- `DeferringLoadBalancerExchangeFilterFunction` for `WebClient`.

Crucially, **group auto-configuration does not apply unconditionally to every URL**. The rules described in Spring Cloud LoadBalancer documentation are:

1. If `spring.http.serviceclient.<group>.base-url` is **not declared** (`null`), Spring Cloud constructs a logical URL from the group name and attaches LoadBalancer.
2. If `base-url` is declared with the **`lb://` scheme**, Spring Cloud also attaches LoadBalancer.
3. If `base-url` is declared with a **scheme other than `lb`**, group LoadBalancer integration **is not attached**, even if the URL host looks like a service ID.

~~~mermaid
flowchart TD
    A["@ImportHttpServices<br/>group=catalog-service"]
    B{"spring.http.serviceclient<br/>.catalog-service.base-url?"}
    C["Not declared"]
    D["lb://catalog-service"]
    E["http://catalog-service or<br/>https://some-host"]
    F["Add LoadBalancer adapter<br/>and logical URL"]
    G["Do not auto-attach LB<br/>call URL via HTTP client"]
    H["ServiceInstanceListSupplier<br/>selects matching instance"]
    A --> B
    B --> C --> F --> H
    B --> D --> F
    B --> E --> G
~~~

### HTTP Service Group URL Behavior Table

Assuming group name `catalog-service` and Cloud 5 integration active:

| Group `base-url` Value | Group LoadBalancer Auto-Config? | How Target Is Resolved |
|---|---|---|
| **Property omitted** | **Yes** | Builds logical URL `http://catalog-service`; selects instances by group name as service ID |
| `lb://catalog-service` | **Yes** | Attaches LB, uses service ID from `lb://` URL |
| `lb://catalog-service/api` | **Yes** | Attaches LB, preserves path segment when building requests |
| `http://catalog-service` | **No** | Treats URL as an ordinary hostname; may trigger DNS resolution |
| `https://catalog.example.internal` | **No** | HTTP client calls real hostname or DNS/proxy infrastructure |
| `http://127.0.0.1:8081` | **No** | HTTP client calls specific endpoint |

**Most common pitfall:** `http://catalog-service` works as a logical URL when you manually create a `@LoadBalanced RestClient.Builder`, yet **setting it as the `base-url` property of an HTTP Service group under Cloud 5 auto-configuration does not trigger group LoadBalancer attachment**.

The two mechanisms have different activation triggers; never infer behavior from the surface appearance of a URL.

### HTTPS and Secure Instances

When `base-url` is omitted or uses `lb://`, the initial HTTP scheme is set so LoadBalancer can resolve the target. If the chosen `ServiceInstance` is marked secure in its metadata, the final scheme can switch to `https`. This does not replace configuring a TLS trust store, certificate validation, or the actual HTTP connector.

## 6. Complete Auto-Configuration Example with Boot 4 and Spring Cloud 5

This example targets a compatible **Spring Boot 4 + Spring Framework 7 + Spring Cloud LoadBalancer 5.x** stack.

### 6.1. Declare the HTTP Interface

~~~java
package com.example.orders.client;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto getProduct(@PathVariable("id") Long id);
}
~~~

Assuming `ProductDto` is a DTO in the same package:

~~~java
package com.example.orders.client;

public record ProductDto(Long id, String name) {}
~~~

### 6.2. Import into a Group Named After the Service ID

~~~java
package com.example.orders;

import com.example.orders.client.CatalogHttpApi;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.service.registry.ImportHttpServices;

@SpringBootApplication
@ImportHttpServices(group = "catalog-service", types = CatalogHttpApi.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

From here, `CatalogHttpApi` is a Spring bean ready to be injected into services. Example:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogHttpApi;
import com.example.orders.client.ProductDto;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private final CatalogHttpApi catalog;

    CatalogGateway(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    ProductDto load(long id) {
        return catalog.getProduct(id);
    }
}
~~~

### 6.3. Add Matching Dependencies

With **Spring Boot 4** and Gradle Kotlin DSL, minimal blocking dependencies can look like:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-restclient")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Compatible Spring Boot plugins and Spring Cloud BOM/release train must be configured; this snippet does not represent an entire `build.gradle.kts`.

If the application exposes REST controllers, add the appropriate WebMVC starter. If using dynamic discovery such as Eureka or Consul, add the corresponding starter. For demos, static instance configuration works.

### 6.4. Supply `ServiceInstance` Entries via `SimpleDiscoveryClient`

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
  http:
    serviceclient:
      catalog-service:
        connect-timeout: 2s
        read-timeout: 3s
~~~

**Intentionally omit `spring.http.serviceclient.catalog-service.base-url`.** Under Cloud 5 mechanics, when a group has no base URL, the logical URL defaults to the group name (e.g., `http://catalog-service`), and the LoadBalancer interceptor is automatically attached when conditions are met.

When you want to state explicitly that the URL requires load balancing, an alternative configuration is:

~~~yaml
spring:
  http:
    serviceclient:
      catalog-service:
        base-url: lb://catalog-service
        connect-timeout: 2s
        read-timeout: 3s
~~~

These two YAML blocks are **alternatives**, not meant to be merged into a single configuration with new semantics.

`127.0.0.1` only works when test servers and caller share the same host or network namespace. In containers, use hostnames/URIs reachable by the caller.

### Expected Outcome

If both instances serve `GET /products/42`, a call to `catalog.getProduct(42L)` follows this path:

~~~text
HTTP Interface proxy
  -> RestClient of group catalog-service
  -> DeferringLoadBalancerInterceptor
  -> LoadBalancer selects 127.0.0.1:8081 or :8082
  -> HTTP transport sends GET /products/42
  -> Decode response into ProductDto
~~~

Selecting an instance successfully does not guarantee the HTTP request succeeds: network timeouts, wrong endpoints, or server errors can still raise exceptions.

## 7. Configuring a Reactive WebClient Group

Framework 7 allows defining a group backed by `WebClient` instead of `RestClient`. In `@ImportHttpServices`, specify `clientType`:

~~~java
import org.springframework.web.service.registry.HttpServiceGroup;
import org.springframework.web.service.registry.ImportHttpServices;

@ImportHttpServices(
        group = "catalog-service",
        types = ReactiveCatalogHttpApi.class,
        clientType = HttpServiceGroup.ClientType.WEB_CLIENT
)
class ReactiveHttpClientsConfiguration {
}
~~~

The reactive interface can return `Mono<ProductDto>`:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange
interface ReactiveCatalogHttpApi {

    @GetExchange("/products/{id}")
    Mono<ProductDto> getProduct(@PathVariable("id") Long id);
}
~~~

With matching WebFlux dependencies and LoadBalancer integration, the HTTP Service group auto-config uses `WebClient.Builder` together with `DeferringLoadBalancerExchangeFilterFunction`.

If the project lacks `WebClient`/reactive HTTP client types on the classpath or lacks matching group auto-config, reactive auto-configuration will not appear merely because the interface returns `Mono`.

**Rule:** the client type must match the invocation model. `RestClient` is blocking; `WebClient` is reactive. `@ImportHttpServices` does not turn blocking connections into non-blocking ones just because business code asks for reactive types.

## 8. Scopes Not Guaranteed by Auto-Configuration

The following assumptions are frequently overestimated:

| Assumption | What Must Actually Be Checked |
|---|---|
| Having `@HttpExchange` creates the proxy | In Framework 6, proxies must be created manually; Framework 7 can register them via `@ImportHttpServices` or a registrar |
| Having Boot 4 includes LoadBalancer | Requires compatible Spring Cloud LoadBalancer and integration beans; Boot auto-config does not supply discovery policies |
| Having Spring Cloud 5 makes every HTTP Interface load-balanced | Default support only wires **auto-configured HTTP Service groups**, subject to base URL rules |
| Any URL containing a service ID auto-load-balances | A group with explicit `http://service-id` is not wired by the Cloud 5 group configurer |
| The `default` group automatically calls the right backend | Undeclared group names default to `default`; name groups deliberately |
| Having LoadBalancer guarantees instances exist | Needs `ServiceInstanceListSupplier` or populated discovery |
| Having LoadBalancer optimizes health checks/retries/timeouts automatically | Those mechanisms have separate dependencies, properties, and semantics |
| Group properties apply to Feign | `@FeignClient` has Spring Cloud OpenFeign's own mechanism and config |
| Group auto-config attaches to manual `HttpServiceProxyFactory` proxies | Manually built proxies do not automatically inherit Boot 4 group configurers; wire the right builder/adapter |
| Running in a native image matches JVM without verification | Verify AOT/native support, service IDs, and reflection/config for your exact version and app |

Spring Cloud's group configurers apply to eligible groups registered in the HTTP Service Clients registry. They are not a global interceptor automatically applied to every `RestClient`, `WebClient`, or `RestTemplate` in the JVM.

### Circuit Breakers Do Not Replace LoadBalancer

Some Spring Cloud versions support circuit breaker integration for HTTP Service groups when appropriate dependencies and config are present. However, circuit breakers, retries, and fallbacks are not automatic consequences of enabling an HTTP Service group. They are distinct resilience layers that affect total latency and call counts.

## 9. Classpath and Configuration Conditions to Verify

When an HTTP Interface does not behave as expected, check in this order:

**1. Versions**

- `Spring Framework 6.x` or `7.x`?
- `Spring Boot 3.x` or `4.x`?
- `Spring Cloud Commons/LoadBalancer 4.x` or `5.x`?
- Is the release train genuinely compatible with Spring Boot?

**2. Proxy Registration**

- Framework 7/Boot 4: is `@ImportHttpServices` present with the right `types` or `basePackages`?
- Framework 6: is there a bean invoking `HttpServiceProxyFactory.createClient(...)`?
- Do interface methods carry `@GetExchange`, `@HttpExchange`, or matching exchange annotations?

**3. HTTP Client**

- Does the group use `RestClient` or `WebClient`?
- Are client starter dependencies on the classpath?
- Are you using Boot 4 auto-config or a manual Framework 6 builder/adapter?

**4. LoadBalancer**

- Is `spring-cloud-starter-loadbalancer` present?
- Is `spring.cloud.loadbalancer.enabled` accidentally set to `false`?
- Is the LoadBalancer interceptor/filter attached to the right group or builder?
- Is there a discovery/`ServiceInstanceListSupplier` source, and does the service ID actually have replicas?

**5. URL**

- Is the group `base-url` omitted, set to `lb://`, or configured with `http://`?
- Does the `group` name match the service ID, or is the `lb://` host correct?
- Are instance URIs reachable (scheme/host/port) from the client?

## 10. Diagnosing Common Failures

| Symptom | Common Cause | How to Check |
|---|---|---|
| IDE does not recognize `@ImportHttpServices` | Framework 6 instead of 7, or missing matching `spring-web` module | Inspect dependency tree; do not bump a single Spring jar in isolation |
| No `CatalogHttpApi` bean | Group not imported / wrong package scanned / manual proxy missing | Inspect import/bean config and application context |
| `spring.http.serviceclient.*` properties appear ignored | Running Boot 3 or using a manual proxy outside auto-config groups | Check Boot version and how the client was registered |
| Group cannot find instances | Wrong group/service ID, empty discovery, or supplier filtered all out | Check `DiscoveryClient.getInstances(serviceId)` |
| `UnknownHostException: catalog-service` | Group explicitly set `base-url: http://catalog-service` bypassing auto LB; or missing interceptor | Check properties and bean configuration |
| HTTP Interface always hits one endpoint | Using physical URL or group lacks LB attachment | Check `base-url`, HTTP client config, and service list |
| Reactive client fails to initialize | Selected `WEB_CLIENT` without WebClient/reactive dependencies | Check WebFlux, connector, and auto-config |
| HTTP 503 error | May be no instances available, or backend/proxy returned 503 | Check whether selection ran and whether requests reached the server |
| Timeout calling selected replica | Transport/server issue or stale endpoint | Check network, backend latency, and client timeouts |
| Legacy Framework 6 code fails to compile after migration | Proxy/adapter/group APIs changed between versions | Use the right API for the release and review migration guides |

Never diagnose from an HTTP status code alone. Separate **missing proxy**, **proxy present without integration**, **LoadBalancer has no instances**, and **HTTP transport failure after instance selection**.

### Observing via Logs/Metrics

Useful fields to capture:

~~~text
group=catalog-service
baseUrl=lb://catalog-service
loadBalancerIntegration=true
selectedServiceId=catalog-service
selectedInstance=127.0.0.1:8082
httpStatus=200 durationMs=45
~~~

This is only an example target log format, **not default log field names automatically emitted by Spring**. Combine HTTP client, Spring Cloud LoadBalancer, and distributed tracing logging/observability when configured. Avoid logging sensitive headers or tokens.

## 11. Lab Exercise: Verifying Exact Supported Scope

### Scenario A: Boot 4 + Cloud 5 Auto-Config Group

1. Run two `catalog-service` backends exposing `GET /whoami` returning distinct instance IDs.
2. Declare `CatalogHttpApi` with `@GetExchange("/whoami")` and use `@ImportHttpServices(group = "catalog-service", types = ...)`.
3. Add HTTP client and LoadBalancer starters, and configure two URIs in `SimpleDiscoveryClient`.
4. **Omit `spring.http.serviceclient.catalog-service.base-url`**; call multiple times via the proxy and observe selected instances.
5. Rerun with `base-url: lb://catalog-service`; confirm LoadBalancer remains integrated.
6. Rerun with `base-url: http://catalog-service` in an environment without matching DNS; confirm this does not activate automatic group LB integration.
7. Rerun with `base-url: http://127.0.0.1:8081`; confirm all requests hit the fixed endpoint.

### Scenario B: Boot 3 / Framework 6.1 Manual Proxy

1. Declare the same HTTP interface.
2. Register `@LoadBalanced RestClient.Builder` and use `HttpServiceProxyFactory` to create the proxy as in section 3.
3. Call `http://catalog-service` through the LB-integrated `RestClient`; verify selection across multiple instances.
4. Switch to `RestClient.create("http://catalog-service")` and compare in an environment without DNS/mesh for that hostname.
5. Do not add Framework 7's `@ImportHttpServices` into Boot 3 code; that API does not exist in this generation.

### Verification Criteria

| Question | Evidence to Collect |
|---|---|
| Was the proxy created? | Interface bean exists and injects cleanly |
| Does the group have the right service ID? | `group` or `lb://` host matches instance source |
| Is LoadBalancer running? | Logs/observations show `ServiceInstance` selection or multi-instance hits |
| Which target received the request? | Instance ID from server, target host/port, or network trace |
| Which layer owned the timeout? | Exception and elapsed time at selection vs. HTTP transport |
| Did property changes take effect? | Compare omitted `base-url`, `lb://`, and direct URL |

## 12. Guidelines for Choosing the Integration Style

- **Projects on Boot 3 / Framework 6:** HTTP Interface still fits; build proxies manually and attach LoadBalancer explicitly to `RestClient` or `WebClient`.
- **Projects on Boot 4 / Framework 7:** leverage `@ImportHttpServices`, group registry, and `spring.http.serviceclient.*` to reduce boilerplate configuration.
- **Projects wanting an HTTP Service group to auto-load-balance:** add compatible Spring Cloud LoadBalancer 5.x, a `ServiceInstance` source, and **either omit `base-url` or use `lb://`**.
- **Projects calling external APIs over fixed hostnames:** configure `https://api.example.com` directly on the group and do not expect LoadBalancer instance selection.
- **Projects with multiple HTTP clients:** maintain clear boundaries between group auto-config, manual proxies, and Spring Cloud OpenFeign; each mechanism has its own prerequisites and properties.

**Conclusion:** Spring HTTP Interface is the **HTTP call contract**; automatic group-based proxy registration comes from **Framework 7 / Boot 4**; and automatic **Spring Cloud LoadBalancer** attachment for groups comes from **LoadBalancer 5.0+** in a supported version stack. Keeping these milestones clear, inspecting your classpath, and reading the `base-url` rules carefully will let you integrate `RestClient`, `WebClient`, discovery, timeouts, and service-ID routing without relying on false assumptions about auto-configuration.

**Official References:**

- [Spring Framework – HTTP Interface](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Boot – Calling REST Services / HTTP Service Interface Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html#io.rest-client.http-service-clients)
- [Spring Cloud Commons – LoadBalancer Integration for Spring HTTP Service Clients AutoConfiguration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring – HTTP Service Client Enhancements (23/09/2025)](https://spring.io/blog/2025/09/23/http-service-client-enhancements/)
