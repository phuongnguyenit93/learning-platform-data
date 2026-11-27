# Service name resolved as DNS: finding client integration bugs

A common bug when integrating **Spring Cloud LoadBalancer** is when a developer writes:

~~~java
restClient.get()
        .uri("http://catalog-service/products/42")
        .retrieve()
        .body(ProductDto.class);
~~~

yet the application fails with an error like **`UnknownHostException: catalog-service`**. The author expected `catalog-service` to be treated as a **service ID** and for Spring Cloud to select a `ServiceInstance`; instead, the HTTP transport treats it as a **standard DNS hostname**.

This situation does not mean discovery is broken. The cause may be that **RestClient/WebClient/Feign is missing the LoadBalancer component**, a different bean was injected by mistake, the client was instantiated manually instead of using a Spring-managed builder, or a fixed configured URL bypassed instance selection.

However, there are also cases where LoadBalancer **successfully selected an instance**, and then the DNS of the **physical address returned by discovery** failed to resolve. Therefore, **looking only at the exception name is not enough to conclude where the bug lies**.

This lesson belongs to the **Troubleshooting** chapter of the Spring Cloud LoadBalancer module, focusing on how to spot the wrong boundary between **service ID → ServiceInstance → physical HTTP address → DNS/TCP**, how to fix `RestClient`, `WebClient`, OpenFeign, and HTTP Interface integrations, and a test suite to prove the fix truly takes effect.

## 1. Distinguish logical service ID from physical hostname

Suppose `order-service` needs to call `catalog-service`:

~~~http
GET http://catalog-service/api/products/42
Accept: application/json
~~~

There are two completely different paths.

### Correct path when using Spring Cloud LoadBalancer

~~~mermaid
flowchart TD
    A["order-service<br/>RestClient with LoadBalancer interceptor"]
    B["serviceId = catalog-service"]
    C["Spring Cloud LoadBalancer"]
    D["ServiceInstanceListSupplier<br/>discovery / cache / filter"]
    E["ServiceInstance<br/>host=10.0.1.12 port=8081"]
    F["HTTP transport"]
    G["DNS if physical host is a hostname<br/>TCP / TLS"]
    H["catalog instance returns response"]
    A --> B --> C
    C <--> D
    C --> E --> F --> G --> H
~~~

On this path:

1. The HTTP client is **integrated with Spring Cloud LoadBalancer**.
2. It receives a URL containing the logical hostname `catalog-service`.
3. LoadBalancer uses that name to retrieve the instance list and selects one instance.
4. The URI is rewritten to the selected instance address, e.g., `http://10.0.1.12:8081/api/products/42`.
5. The HTTP transport connects; if the physical host is a DNS name, DNS resolution happens at this point.

### Broken path when the client lacks LoadBalancer

~~~mermaid
flowchart TD
    A["order-service<br/>Plain RestClient"]
    B["URI = http://catalog-service/api/products/42"]
    C["HTTP transport"]
    D["DNS lookup hostname catalog-service"]
    E{"DNS record exists?"}
    F["UnknownHostException / DNS failure"]
    G["Connects via DNS<br/>bypassing Spring Cloud LB"]
    A --> B --> C --> D --> E
    E -->|"No"| F
    E -->|"Yes"| G
~~~

On this path, `ServiceInstanceListSupplier` is never queried. The HTTP transport simply sees a hostname to connect to.

**Foundational conclusion:** a URL string containing a service name **does not automatically enable** client-side load balancing. Integration must reside on the **actual HTTP client bean being used**.

## 2. UnknownHostException is not absolute proof of missing LoadBalancer

Two bugs can look identical:

| Scenario | Completed step | Host failing DNS | Assessment |
|---|---|---|---|
| Plain client calls `http://catalog-service` | No instance selection step | `catalog-service` | Suspect HTTP client integration error or intentional DNS usage |
| LB client selects `catalog-1` with URI `http://catalog-a:8081`, but container cannot resolve `catalog-a` | LoadBalancer **already selected** an instance | `catalog-a` | Suspect physical destination networking/DNS |
| LB client gets an empty list | Could not select an instance | May **not perform DNS** | Suspect discovery/filter/health/service ID config |
| LB client selects IP `10.0.1.12:8081` but connection refused | Selected an instance | No DNS needed when using IP | Suspect port/backend/firewall |
| Plain client uses a valid DNS URL in Kubernetes | No LB on caller | Valid DNS | Request may **succeed**, yet does not prove Spring Cloud LB works |

**Do not treat `UnknownHostException` as the sole condition for blindly adding annotations.** First determine **which hostname was sent to the resolver** and **whether LoadBalancer actually selected an instance**.

## 3. Quick decision flowchart on error

~~~mermaid
flowchart TD
    A["Error calling http://catalog-service"]
    B{"Is client wired with<br/>Spring Cloud LoadBalancer?"}
    C["Check starter, builder bean,<br/>filter/interceptor, fixed URL"]
    D{"Is there an instance list<br/>for catalog-service?"}
    E["Check service ID, registry,<br/>supplier, cache, health/filter"]
    F{"Did LoadBalancer select<br/>an instance?"}
    G["Collect selected URI / host:port"]
    H{"HTTP transport DNS error?"}
    I{"Is failing DNS host<br/>logical or physical?"}
    J["Fix client integration"]
    K["Fix instance address,<br/>Compose network / registry"]
    L["Continue checking TCP,<br/>TLS, timeout, and response"]
    A --> B
    B -->|"No / unsure"| C --> J
    B -->|"Yes"| D
    D -->|"No"| E
    D -->|"Yes"| F
    F -->|"Yes"| G --> H
    F -->|"No"| E
    H -->|"Yes"| I
    I -->|"Logical catalog-service"| J
    I -->|"Target catalog-a / IP"| K
    H -->|"No"| L
~~~

This diagram is a **runbook**, not an absolute exception mapping. An application may have proxies, DNS caches, or multiple retry layers that cause the final exception to lose information from the first attempt.

## 4. Symptom matrix and first verification step

| Sign | Likely cause | How to verify |
|---|---|---|
| `UnknownHostException: catalog-service` with `RestClient.create(...)` | Plain client passes service ID to DNS | Check how RestClient is created and which bean is injected |
| `UnknownHostException: catalog-service` with `WebClient.create(...)` | WebClient has no LoadBalancer filter | Check `@LoadBalanced WebClient.Builder` |
| Feign calls a physical URL instead of discovery | `url` declared in annotation/properties | Check URL on the named Feign client |
| Feign fails to start citing missing LoadBalancer client | Missing Spring Cloud LoadBalancer dependency in the corresponding configuration | Check classpath/starter and Feign configuration |
| “No instances available for catalog-service” | LB runs but supplier has no candidates | Check `DiscoveryClient.getInstances("catalog-service")` and filters |
| LB selects instance but `UnknownHostException: catalog-a` | Physical address does not resolve | Check advertised host/port and container network |
| `Connection refused: 10.0.1.12:8081` | Address resolved, backend not listening on port | Check port and readiness; do not fix DNS |
| HTTPS handshake failure | Host/port, SNI, certificate, or TLS mismatch | Check protocol and TLS transport |
| Same URI works in container but fails on host machine | DNS name only exists inside Compose network | Determine where the client actually runs |
| Calling service name succeeds even without `@LoadBalanced` | DNS/ClusterIP/mesh may handle hostname | Distinguish caller-side LB from infrastructure LB |

Error messages and exception wrappers may vary across Spring Framework, Reactor Netty, Feign, JVM, and HTTP transports.

## 5. Create a minimal reproduction: discovery exists but HTTP client calls wrong

Suppose catalog has two physical instances:

~~~text
catalog-service (service ID)
  -> http://127.0.0.1:8081
  -> http://127.0.0.1:8082
~~~

The caller declares a static instance list:

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
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

**This is only the instance source.** It does not automatically attach LoadBalancer to every `RestClient` created in the JVM.

### Broken code: plain RestClient

~~~java
import org.springframework.web.client.RestClient;

class BrokenCatalogGateway {

    private final RestClient client =
            RestClient.create("http://catalog-service");

    String whoami() {
        return client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

If `catalog-service` has no DNS record in the running environment, the call may fail with an unresolvable hostname error **even though the `SimpleDiscoveryClient` list is completely valid**.

### Fixed code: Spring Cloud-integrated RestClient

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean("catalogLoadBalancedBuilder")
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

And inject **that exact configured RestClient bean**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    String whoami() {
        return client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

In this example, the application needs compatible starters including Spring Cloud LoadBalancer and Spring Framework with `RestClient` (from Framework 6.1).

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

With Spring Boot 4, HTTP MVC starter names/dependency versions may differ. Always use a **compatible Spring Cloud release train/BOM** instead of mixing versions manually.

**Note:** a `RestClient.Builder` bean annotated with `@LoadBalanced` only works when managed by Spring and when the relevant Spring Cloud auto-configuration is present. Calling `RestClient.builder()` elsewhere and using that builder will not automatically inherit the LoadBalancer interceptor.

## 6. Why does it still fail even with the annotation in place?

### 6.1. Injecting the wrong Builder

Suppose the same application defines:

~~~java
@Bean("ordinaryBuilder")
RestClient.Builder ordinaryBuilder() {
    return RestClient.builder();
}

@Bean("catalogLoadBalancedBuilder")
@LoadBalanced
RestClient.Builder catalogLoadBalancedBuilder() {
    return RestClient.builder();
}
~~~

If a class uses `ordinaryBuilder` instead of `catalogLoadBalancedBuilder`, the `http://catalog-service` URL may still be handed to DNS.

Use `@Qualifier` by bean name or `@LoadBalanced` at the injection point to ensure the client uses the right builder. When multiple beans of the same type exist, name/qualify them clearly and verify the actual wired bean rather than guessing from an annotation on an unused method.

### 6.2. Configuring the right builder, then creating another client

~~~java
// A catalogRestClient bean already exists in Spring,
// but this snippet ignores the bean and creates a new client manually.
RestClient client = RestClient.create("http://catalog-service");
~~~

This is a common integration mistake in gateway classes, test fixtures, and custom factories. Inject the properly configured singleton RestClient or build the client from the injected builder.

### 6.3. Placing the annotation on the wrong target

Do not assume:

~~~java
// Does NOT substitute for @LoadBalanced RestClient.Builder:
@LoadBalanced
class CatalogGateway {
    // ...
}
~~~

will cause every HTTP call inside the class to be load-balanced automatically. `@LoadBalanced` is processed by Spring Cloud on **supported client extension points**, such as `RestClient.Builder`, `WebClient.Builder`, and `RestTemplate`.

### 6.4. Using a direct client to test a logical URL

`RestClient.create("http://catalog-service")` is not a test that proves discovery. To test Spring Cloud LoadBalancer, use the integrated client. To test DNS or a proxy, use a direct client. **Do not swap the two test goals.**

### 6.5. Auto-configuration disabled or missing dependency

Verify:

- `spring-cloud-starter-loadbalancer` is present on the **caller**.
- Required `RestClient`/Spring Web classes are on the classpath.
- A Spring-managed `RestClient.Builder` bean exists.
- No override/customizer replaces or strips the LoadBalancer interceptor/filter.
- Auto-configuration is not excluded and profiles do not disable it in one environment.
- Spring Boot/Framework and Spring Cloud versions are compatible.

**Do not work around the bug by adding a fake DNS record for the service ID** before confirming the architecture. A DNS record may make requests appear to succeed while hiding broken client integration.

## 7. Distinguish plain beans from load-balanced beans in RestClient

An application may need **both**:

~~~java
@Configuration(proxyBeanMethods = false)
class SplitClientsConfiguration {

    @Bean("paymentDirectRestClient")
    RestClient paymentDirectRestClient() {
        return RestClient.create("https://payments.example.test");
    }

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogLbRestClient")
    RestClient catalogLbRestClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

| Bean | Purpose | How hostname is interpreted |
|---|---|---|
| `paymentDirectRestClient` | Calls a known external/gateway URL | DNS/proxy via HTTP transport |
| `catalogLbRestClient` | Calls internally via service ID | Spring Cloud LoadBalancer before transport |
| Another RestClient created via `RestClient.create(...)` | New direct client | Does not inherit interceptors from catalog bean |
| RestClient from `@LoadBalanced` builder calling an IP directly | May treat the IP as a service ID to look up | Do not use as a direct client if you want to bypass LB |

**Do not reuse a single load-balanced builder for every URL across the entire application.** For physical URLs, IPs, or external hosts without a service ID in discovery, doing so can produce confusing “no available instance” errors.

## 8. Verify the instance list before modifying the HTTP client

Once you are sure the client is load-balanced yet still failing, the next step is checking whether `DiscoveryClient` has valid data.

Example diagnostic bean **for test/local environments only**:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("diagnostic")
class CatalogDiscoveryProbe {

    private final DiscoveryClient discovery;

    CatalogDiscoveryProbe(DiscoveryClient discovery) {
        this.discovery = discovery;
    }

    List<String> candidateUris() {
        return discovery.getInstances("catalog-service").stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .toList();
    }
}
~~~

Expected example with `SimpleDiscoveryClient`:

~~~text
http://127.0.0.1:8081
http://127.0.0.1:8082
~~~

**Important:** `DiscoveryClient.getInstances(...)` shows the list **from the discovery source**, which does not guarantee the final list after the full `ServiceInstanceListSupplier` chain is identical. Zone, hint, health, caching, or strict filters may eliminate candidates.

An empty result can be caused by:

1. Wrong service ID or mismatched casing/format.
2. Registry not running / failing to fetch registry.
3. Wrong `SimpleDiscoveryClient` property path or profile not active.
4. Discovery has not updated registration yet, or cache is stale.
5. Suppliers filtered out all candidates by zone/hint/region/health.
6. A strict policy intentionally failing closed.

**Do not fall back automatically by calling another service's DNS if policy forbids it.** For hard constraints, no-instance may be the right behavior.

## 9. WebClient: inspect ExchangeFilterFunction, not just baseUrl

With `WebClient`, Spring Cloud LoadBalancer integration is typically configured via **`@LoadBalanced WebClient.Builder`**. A client created with plain `WebClient.create(...)` does not automatically attach this exchange filter.

### Proper configuration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogReactiveConfiguration {

    @Bean("catalogLoadBalancedWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLoadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLoadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

On a caller with compatible WebFlux/WebClient and `spring-cloud-starter-loadbalancer` dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Example reactive call:

~~~java
Mono<String> request = catalogWebClient.get()
        .uri("/whoami")
        .retrieve()
        .bodyToMono(String.class);
~~~

### Common mistake with WebClient

~~~java
// Even if the app already has a @LoadBalanced WebClient.Builder,
// the client created below is completely independent.
WebClient wrong = WebClient.create("http://catalog-service");
~~~

If `catalog-service` does not exist in DNS, Reactor Netty may raise a hostname resolution error. Do not fix it with unconditional `retryWhen(...)`, because resubscribing multiple times **will not materialize a missing LoadBalancer filter**.

### Two cases to separate

- **No LB filter:** transport treats `catalog-service` as a DNS hostname.
- **LB filter present:** the filter picks a physical URI; Reactor Netty then performs DNS/connection against **the host inside that URI**.

For an instance with URI `http://catalog-a:8081`, `UnknownHostException: catalog-a` occurs **after selection**. Inspect DNS/networking for `catalog-a`; do not rename the `catalog-service` service ID just to test.

## 10. OpenFeign: why does the client still use a fixed URL?

OpenFeign by service ID typically looks like:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/whoami")
    String whoami();
}
~~~

The application must enable client scanning on the right package and include the proper dependencies:

~~~java
@SpringBootApplication
@EnableFeignClients(basePackages = "com.example.orders.client")
class OrderApplication {
}
~~~

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

When no fixed URL is provided and the corresponding integration is present, Spring Cloud OpenFeign can use `FeignBlockingLoadBalancerClient` to pick a `ServiceInstance`.

### Mistake 1 — Specifying a URL in the annotation

~~~java
@FeignClient(
        name = "catalog-service",
        url = "http://catalog-service:8081")
interface CatalogDirectFeign {

    @GetMapping("/whoami")
    String whoami();
}
~~~

This is an **explicit URL**, so it is no longer equivalent to Feign selecting an instance by service ID. If the hostname only exists in Docker DNS, Feign may connect successfully via DNS yet **not use Spring Cloud LoadBalancer by service ID** for that client.

### Mistake 2 — URL configured via properties

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            url: http://catalog-service:8081
~~~

An explicit URL in named client configuration can bypass instance selection by service ID. When switching to discovery-based load balancing, inspect **both annotations and configuration properties**, not just the interface source code.

### Mistake 3 — Missing LoadBalancer starter or overriding the Feign Client

If you add OpenFeign without the matching Spring Cloud LoadBalancer dependency, Feign may fail at startup reporting **no load-balancing client**, rather than silently falling back to DNS resolution. Behavior and wording depend on version.

If you register a custom `feign.Client` bean or build one manually via `Feign.builder().target(...)`, verify whether the delegate/wrapper still goes through `FeignBlockingLoadBalancerClient`. A custom transport can bypass LB if it replaces the configuration improperly.

### Quick checklist for Feign

| Condition | Want selection by service ID | Want direct URL call |
|---|---|---|
| `@FeignClient(name=...)` | Yes | May be present |
| `@FeignClient(url=...)` | **Do not set** | May be set |
| URL in `spring.cloud.openfeign.client.config.*.url` | **Do not set** | May be set |
| `spring-cloud-starter-loadbalancer` | Required per integration | Not needed for direct URL |
| HTTP delegate | Has proper LB wrapper | Plain HTTP client |
| `ServiceInstance` list | Must have candidates | Not used to pick target |

## 11. HTTP Interface: which RestClient backs the proxy is what matters

Spring HTTP Interface uses `@HttpExchange` and `@GetExchange` to declare APIs as interfaces. However, **the interface itself does not decide load balancing**. It executes on top of an adapter wrapping a specific RestClient/WebClient.

Example:

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
interface CatalogHttpApi {

    @GetExchange("/whoami")
    String whoami();
}
~~~

Create the proxy using the **load-balanced RestClient**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Bean
CatalogHttpApi catalogHttpApi(
        @Qualifier("catalogRestClient") RestClient client) {

    HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                    RestClientAdapter.create(client))
                    .build();

    return factory.createClient(CatalogHttpApi.class);
}
~~~

If `client` is replaced with `RestClient.create("http://catalog-service")`, the proxy follows that client's DNS behavior. **The `@HttpExchange` annotation does not attach a LoadBalancer interceptor by itself.**

The same applies to `WebClientAdapter`: create the proxy from a Spring Cloud-integrated WebClient, not from a plain WebClient.

## 12. DNS can work and mask an integration bug

In **Docker Compose**, containers on the same network can resolve service names like `catalog-service`. In **Kubernetes**, DNS can resolve `catalog-service` to a Service's ClusterIP.

Consequently, the following code can **actually work** in a deployed environment:

~~~java
RestClient directDns =
        RestClient.create("http://catalog-service:8081");
~~~

However, request success only proves that **DNS/network has a route to an endpoint**. It **does not prove** traffic went through Spring Cloud LoadBalancer.

| Environment | `catalog-service` via DNS | Meaning when plain RestClient succeeds |
|---|---|---|
| Laptop without DNS record | Usually fails to resolve | Likely sees `UnknownHostException` |
| Docker Compose same network | Can resolve service name | Docker DNS/network resolves the name |
| Kubernetes with Service DNS | Can resolve | ClusterIP/CNI/kube-proxy/mesh may route it |
| Host machine outside Compose network | Does not necessarily resolve | Cannot use internal service DNS if host is outside network |
| Service ID only exists in Eureka | DNS may not know the name | Requires Spring Cloud LB + Eureka discovery |

For a Compose static list, you can configure:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a:8081
              - uri: http://catalog-b:8081
~~~

Here:

- `catalog-service` is the **logical key** for LoadBalancer.
- `catalog-a` and `catalog-b` are **real hostnames** the HTTP client must resolve via Compose DNS.
- If `catalog-a` is not on the same network or the service is renamed, DNS for the physical instance can fail even though LoadBalancer selected properly.

**Do not use `127.0.0.1` inside a container to target another container.** `localhost` inside `order-service` refers to the `order-service` container itself, not `catalog-service`.

## 13. LoadBalancer selected an instance, yet DNS/transport still fails

A second case:

~~~text
serviceId = catalog-service
instanceId = catalog-a
ServiceInstance.uri = http://catalog-a:8081
selected = catalog-a
HTTP transport -> UnknownHostException(catalog-a)
~~~

The runbook here differs completely from missing LB:

1. Grab the exact URI chosen by discovery/LoadBalancer from controlled logs/tracing or a test-only diagnostic endpoint.
2. Check whether the physical hostname exists in the **caller's network namespace**.
3. With Compose, verify containers share the same network, the service name is accurate, and the backend is running.
4. With Kubernetes, verify DNS name/namespace, Service/EndpointSlice, and network permissions.
5. With Eureka, verify the instance advertises a hostname/IP/port **actually reachable** from the caller; avoid `localhost` or host-only addresses.
6. Check reverse proxies, DNS caching, TTL, and HTTP connection reuse if addresses changed after a restart.
7. If DNS succeeds yet calls still fail, move on to checking TCP/TLS/port/timeout.

### Registry recording the wrong endpoint

For instance, a Eureka client inside a container advertises:

~~~text
host = localhost
port = 8081
~~~

A caller in another container receives this instance. LoadBalancer selects it completely validly based on registry data, yet when the HTTP client connects to `localhost:8081`, it calls **the caller itself**, not the backend.

This cannot be solved by adding `@LoadBalanced` to an already load-balanced bean; you must fix **the address advertised to the registry** or the network topology.

### A selected instance does not mean it is healthy

Discovery cache may still hold a stopped instance. Post-selection failures can be `Connection refused`, connection timeout, or response timeout. That is a membership/health/transport issue, not a service name mistakenly resolved as DNS.

## 14. Difference between “no instance” and “cannot resolve hostname”

Two error types are often lumped together as “service not found”:

**Case A — Discovery has no candidates**

~~~text
RestClient with LoadBalancer
  -> serviceId=catalog-service
  -> ServiceInstanceListSupplier returns []
  -> LoadBalancer cannot pick a server
  -> no-instance error / corresponding HTTP error mapping
  -> typically no HTTP request sent to backend
~~~

**Case B — Client lacks LoadBalancer**

~~~text
Plain RestClient
  -> URI http://catalog-service/whoami
  -> HTTP transport resolves hostname catalog-service
  -> UnknownHostException if no DNS record exists
~~~

**Case C — Wrong physical destination**

~~~text
RestClient with LoadBalancer
  -> catalog-service -> selects catalog-a:8081
  -> HTTP transport resolves catalog-a
  -> UnknownHostException if catalog-a does not resolve
~~~

| Scenario | Stage to fix | Does raising read timeout help? |
|---|---|---|
| A | Discovery/filter/service ID/health/cache | Does not solve missing candidates |
| B | Builder/filter/Feign URL/client integration | Does not create a missing interceptor |
| C | Physical URI, registry, network/DNS | Does not fix wrong host; may only wait longer |

**Warning:** libraries may wrap root causes in `RestClientException`, `WebClientRequestException`, `FeignException`, or other exceptions. Inspect the **cause chain** and selection context; do not rely solely on the top-level exception name.

## 15. Check request URL and scheme/port configuration

### 15.1. Logical URL needs an appropriate scheme

Example:

~~~java
RestClient client = lbBuilder
        .baseUrl("http://catalog-service")
        .build();
~~~

The host portion is the service ID. Do not copy the `lb://catalog-service` URI scheme from certain gateway ecosystems into a regular RestClient if the integration uses HTTP URIs with `@LoadBalanced`.

### 15.2. Do not use a port on the service ID to choose a replica

~~~java
// Misleading when trying to use port 8081 to select a replica:
RestClient client = lbBuilder
        .baseUrl("http://catalog-service:8081")
        .build();
~~~

LoadBalancer picks an instance from the list by service ID, and an instance's physical URI may have its own port. If you want to call **one fixed endpoint** for debugging, use a direct RestClient. If you want LoadBalancer selection, do not use a logical port as an unintended routing signal.

### 15.3. HTTPS is a separate decision

If the selected URI uses HTTPS, the HTTP transport needs appropriate TLS/certificate trust/SNI. A handshake failure or invalid certificate does not prove that the service ID was resolved by DNS incorrectly.

In a service mesh environment, a logical HTTP name may pass through a sidecar; confirm the architecture to avoid confusing the target selection layer with the connection encryption layer.

## 16. Diagnose with logs/tracing without exposing sensitive data

To tell the two errors apart, the most useful signal is a controlled observability event:

~~~text
operation=catalog.whoami
serviceId=catalog-service
loadBalancerApplied=true
candidateCount=2
selectedInstance=catalog-a
selectedEndpointCategory=compose-network
httpStatus=none
errorCategory=DNS_RESOLUTION
dnsHostCategory=PHYSICAL_INSTANCE
traceId=lab-123
~~~

This is an **illustrative format**, not a metric/log set automatically emitted by Spring Cloud by default.

Only include **allowlisted** fields in logs:

- Configured `serviceId`.
- Fixed `operation` or route template.
- Candidate count before/after filters, if instrumented.
- Permitted instance/instance-group selection outcome.
- Error category such as `NO_INSTANCE`, `DNS_RESOLUTION`, `CONNECT_FAILURE`, `TIMEOUT`.
- Latency and safe trace ID.
- Classification of the failing DNS host as `LOGICAL_SERVICE_NAME` or `PHYSICAL_INSTANCE`.

**Do not unconditionally log raw URLs containing query tokens, `Authorization`, `Cookie`, response bodies, or full exception messages/stacktraces.** Exception messages can embed URLs and private data; when deep analysis is needed, use an appropriately restricted investigation channel.

### Do not confuse HTTP DEBUG logs with safe evidence

Spring Cloud LoadBalancer DEBUG logs can be used in a **lab with dummy data** to understand selection. However, enabling Feign `FULL`, Reactor Netty wiretap, or HTTP wire logs can record sensitive headers/bodies. In production, prefer controlled metrics/tracing or dedicated events at the client boundary.

## 17. Lab: intentionally misconfigure then fix RestClient

### Preparation

Run a simple `catalog-service` backend returning an instance ID. Example:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogWhoamiController {

    private final String instanceId;

    CatalogWhoamiController(
            @Value("${demo.instance-id:catalog-a}")
            String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/whoami")
    String whoami() {
        return instanceId;
    }
}
~~~

Run two instances of the same app—for instance on ports 8081/8082—with `demo.instance-id=catalog-a` and `catalog-b` respectively. The caller uses `SimpleDiscoveryClient` as in Section 5.

### Run 1 — Plain client

~~~java
RestClient wrong =
        RestClient.create("http://catalog-service");

String value = wrong.get()
        .uri("/whoami")
        .retrieve()
        .body(String.class);
~~~

If the hostname `catalog-service` does not exist in the caller's DNS, a resolver error is expected. This is an **environment-dependent outcome**, not a universally guaranteed assertion: in Compose/Kubernetes a DNS record may already exist.

### Run 2 — Load-balanced client

Inject `catalogRestClient` from Section 5. Call `/whoami` 10–12 times and record the set of returned instance IDs:

~~~java
Set<String> observed = new HashSet<>();

for (int i = 0; i < 12; i++) {
    String id = catalogRestClient.get()
            .uri("/whoami")
            .retrieve()
            .body(String.class);

    observed.add(id);
}

// With two healthy instances and default round-robin,
// observed is expected to contain both catalog-a and catalog-b.
~~~

If the result contains both, that is practical proof of the **service ID → instance list → HTTP** path in the lab, provided no DNS/proxy infrastructure is mimicking the result.

### Run 3 — Keep LB but break the physical hostname

In the static list, replace one instance's URI with `http://nonexistent-catalog-host.invalid:8081`. This is a synthetic hostname under the `.invalid` reserved domain for testing, not a real endpoint.

Verify:

- LoadBalancer can still see and select that instance.
- The HTTP transport fails to resolve the physical hostname.
- This is a **post-selection** error, not proof of missing `@LoadBalanced`.
- Requests routed to the remaining healthy instance may succeed, depending on policy/retries.

Do not configure a proxy or wildcard DNS in the lab if you want to observe resolver failures directly; if the environment intercepts every request, results may differ.

## 18. Integration test: prove independence from service ID DNS

A more reliable integration test than asserting exception messages should:

1. Start a **mock HTTP server** on a dynamic port.
2. Register that server in `SimpleDiscoveryClient` via `@DynamicPropertySource`.
3. Boot a **real Spring context** with `@LoadBalanced RestClient.Builder`.
4. Call `http://catalog-service` through the injected bean.
5. Assert the response matches the ID returned by the mock backend.
6. Require no DNS entry for `catalog-service`.

JUnit Jupiter + Spring Boot test example:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = ServiceIdRestClientIT.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.cloud.loadbalancer.cache.enabled=false",
            "spring.cloud.loadbalancer.retry.enabled=false"
        })
class ServiceIdRestClientIT {

    private static final HttpServer CATALOG =
            startServer("catalog-a");

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
                () -> "http://127.0.0.1:"
                        + CATALOG.getAddress().getPort());
    }

    @Autowired
    @Qualifier("catalogRestClient")
    RestClient client;

    @Test
    void resolvesServiceIdViaLoadBalancer() {
        String response = client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);

        assertEquals("catalog-a", response);
    }

    @AfterAll
    static void stopServer() {
        CATALOG.stop(0);
    }

    private static HttpServer startServer(String id) {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/whoami", exchange -> {
                byte[] bytes = id.getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean("catalogLbBuilder")
        @LoadBalanced
        RestClient.Builder catalogLbBuilder() {
            return RestClient.builder();
        }

        @Bean("catalogRestClient")
        RestClient catalogRestClient(
                @Qualifier("catalogLbBuilder")
                RestClient.Builder builder) {
            return builder
                    .baseUrl("http://catalog-service")
                    .build();
        }
    }
}
~~~

This test assumes `spring-boot-starter-test`, Spring Cloud LoadBalancer, and a compatible Spring Framework `RestClient`. The JDK runtime must include the `jdk.httpserver` module; on some minimal JPMS/runtime images, add the module or replace it with WireMock/MockWebServer.

**Meaningful outcome:** the Spring-configured caller can invoke `catalog-service` via the registered instance URI even though the logical URL **is not a hostname registered in DNS for the test**. This is an integration test of **client wiring**, not a performance benchmark or verification of every policy.

An additional test should start **two mock servers** and assert `Set.of("catalog-a","catalog-b")` across multiple calls to verify multi-instance selection. Do not assert that the first request always picks A or that round-robin splits exactly 6/6 without controlling state.

### Negative tests should not depend on CI environment DNS

Do not write an absolute assertion such as:

~~~java
RestClient.create("http://catalog-service")
        .get().uri("/whoami").retrieve().body(String.class);
// MUST throw UnknownHostException
~~~

Because in Docker/Kubernetes CI, `catalog-service` might happen to resolve in DNS. Positive tests that pass through LoadBalancer to a **deterministic mock HTTP server** are far more reliable.

## 19. Priority-ordered diagnostic checklist

During an active incident, check from least disruptive to most:

| Step | Question | Evidence to gather | Action |
|---|---|---|---|
| 1 | Which client is executing? | Bean name, client type, constructor/config | Confirm the actual RestClient/WebClient/Feign/HTTP Interface |
| 2 | Is the logical URL configured properly? | `baseUrl`/Feign name, URL properties | Separate service ID from physical URL |
| 3 | Is the client wired with LB? | `@LoadBalanced` bean, filter/interceptor, Feign wrapper | Fix wiring, starter, inject right bean |
| 4 | Is there an instance list? | `DiscoveryClient`, supplier/filter output | Fix service ID, registry, metadata/filters |
| 5 | Which instance did LB pick? | Selected instance/URI via instrumentation | Separate logical DNS from physical DNS |
| 6 | Does HTTP transport reach the right host:port? | DNS/network inside caller, instance URI | Fix address, network, port, registry |
| 7 | Did the request reach the backend? | Trace/correlation and safe backend logs | Separate connect failure from server/response error |
| 8 | Are retries/cache skewing diagnosis? | Attempt count, cache TTL, refresh | Test a single attempt to isolate root cause |
| 9 | Does it hold across scaling/restarts? | Multi-instance integration test, outage test | Add regression tests and metrics |

**Do not disable all security controls, TLS, or enable token-exposing DEBUG logging to troubleshoot a DNS issue.** Evidence collection must stay scoped to allowed environments, permissions, and data.

## 20. Subtle edge cases easy to misdiagnose

### 20.1. Multiple Spring contexts

`@LoadBalancerClient(name=..., configuration=...)` can create per-service-ID configuration inside a Spring Cloud LoadBalancer **child context**. If a configuration class is accidentally picked up into the parent context by main component scanning, beans or suppliers will not apply to the intended scope.

However, if the client is using direct DNS because `@LoadBalanced` is missing, **tweaking supplier algorithms will not fix the primary cause**.

### 20.2. Stale caches

`CachingServiceInstanceListSupplier` can retain an older list. Eureka/Consul also have their own synchronization/caching mechanisms. A failure to resolve a selected instance hostname after scale-down may be due to registries/caches still holding an old URI. Disabling LB cache in a test **does not make all other discovery caches disappear**.

### 20.3. HTTP proxies

An HTTP proxy can receive an absolute URI and resolve the host itself. In that case, `UnknownHost` may originate from the proxy or transport layer rather than the DNS resolver inside the caller. Confirm proxy settings and the actual request route before concluding which component resolved the name.

### 20.4. Circuit breakers and retries

Circuit breakers, timeouts, retries, and fallbacks can mask the initial failure behind another exception or response. In a diagnostic lab, temporarily control or disable unnecessary retry layers to get a clean single-attempt trace; in production, do not alter resilience policies without risk evaluation.

### 20.5. Bugs that only pass in tests

Mocking `RestClient`/`WebClient` or using `MockRestServiceServer` can bypass real HTTP transport, letting unit tests pass even without a LoadBalancer interceptor. Maintain an **integration test with a real Spring ApplicationContext + real HTTP server** to prove the service ID path.

### 20.6. Do not confuse Kubernetes discovery with Kubernetes Service DNS

When using Spring Cloud Kubernetes DiscoveryClient, service/endpoint mapping depends on configuration and Kubernetes API permissions. When using a **plain RestClient targeting Kubernetes Service DNS**, selection happens at the network layer rather than Spring Cloud LoadBalancer picking a `ServiceInstance` on the caller. Both architectures can be valid, but you must choose and measure the right one.

## 21. Post-fix regression test matrix

| Case | Configuration | Expected outcome |
|---|---|---|
| Plain RestClient + service ID without DNS | No `@LoadBalanced` | May fail DNS; outcome depends on environment |
| RestClient right LB bean + static instances | `@LoadBalanced RestClient.Builder` | Calls registered HTTP instance |
| RestClient injected wrong direct bean | Ordinary builder injected | Does not use Spring Cloud LB as intended |
| LB with empty list | Supplier returns `[]` | No instance selected; handles no-server error |
| LB picks instance URI with bad host | `catalog-a` URI unresolvable | Physical host DNS fails after selection |
| Plain WebClient + service ID | `WebClient.create(...)` | May DNS-lookup logical hostname |
| LB WebClient + static instances | `@LoadBalanced WebClient.Builder` | Requests reach selected physical URI |
| Feign with name, no URL | Feign + LB integration present | Selects by service ID |
| Feign with URL | `@FeignClient(url=...)` or URL property | Calls direct URL; skips selection by name |
| HTTP Interface with LB RestClient | Proxy built from integrated RestClient | Routes through client-side LB |
| HTTP Interface with direct RestClient | Proxy built from plain client | Follows client's DNS/direct behavior |
| Docker Compose different network | Instance URI `http://catalog-a:8081` | Physical host DNS/network fails |
| Kubernetes Service DNS + plain RestClient | Valid DNS/ClusterIP | Request may succeed **without Spring Cloud LB** |
| Scale-down and stale registry/cache | Stale URI | May still fail prior to refresh |

When testing, do not assert HTTP 200 alone: a backend can return 200 via DNS/service mesh even when LoadBalancer is not wired. To verify client-side selection, observe the **candidate list and selected instance** or use mock servers with distinct IDs and a controlled discovery source.

## 22. Anti-patterns and operational lessons

**1. Adding `127.0.0.1 catalog-service` to the hosts file to “fix” the error.** This can make a DNS-based demo pass locally, but it does not attach LoadBalancer and breaks in container networks or clusters.

**2. Wrapping every exception in retries.** A client missing LB will not magically gain an interceptor after 10 retries; retries also increase latency and load.

**3. Renaming the service ID based on a DNS error without checking discovery.** This can break the caller/registry contract and mask misconfigured beans.

**4. Testing only by curling `http://catalog-service`.** Curl tests the DNS/network of the environment running curl; it does not verify Spring Cloud LoadBalancer inside the application.

**5. Assuming `@FeignClient(name=...)` guarantees LB usage.** A URL in annotations/properties or a custom HTTP client can still bypass selection by service ID.

**6. Using a `@LoadBalanced` builder for every external URL/IP.** LoadBalancer may attempt to look up instances for a physical hostname that is not a service ID.

**7. Enabling DEBUG wiretap/FULL logging in production to dump entire requests.** Risks leaking `Authorization`, `Cookie`, signed URLs, payloads, and sensitive metadata. Prefer safe observability events.

**8. Relying on a mock test to prove HTTP integration.** Mocks can return expected data even when the client is built from the wrong builder.

**9. Failing to distinguish logical DNS from physical DNS.** This causes teams to waste time debugging discovery when the real issue is Docker networking, or vice versa.

**10. Generalizing one environment's result to all environments.** Laptops, Docker Compose, Kubernetes, service meshes, VPNs, and HTTP proxies each have distinct DNS/network behavior.

## 23. Checklist before concluding the issue is resolved

- Identified **which RestClient/WebClient/Feign/HTTP Interface bean** is actually used?
- Built the client from a **`@LoadBalanced` builder/adapter** when service ID selection is intended?
- Verified `spring-cloud-starter-loadbalancer`, compatible Spring versions, and that auto-configuration is enabled?
- For Feign, checked `url` in annotations **and** properties?
- Distinguished `UnknownHostException` of the **logical hostname** from DNS errors on the **selected instance host**?
- Can inspect `DiscoveryClient.getInstances(serviceId)` and supplier/filter output without exposing sensitive metadata?
- Verified service ID spelling/casing and that the discovery source has data?
- Confirmed the advertised physical URI has a host/port/network reachable by the caller?
- In Docker/Kubernetes, verified the network namespace and avoided misusing `localhost`?
- Tested HTTP/HTTPS, proxy, TLS, and connect/read timeouts separately after selection?
- Controlled retries/circuit breakers/caches while reproducing the issue?
- Have a **real Spring context integration test** proving requests by service ID reach a mock HTTP server without depending on logical DNS?
- After fixing, added regression tests for RestClient, WebClient, Feign, or HTTP Interface matching the system's actual clients?
- Confirmed logging/tracing captures enough selection events **without logging tokens/cookies/raw URLs**?

**Conclusion:** When a service name gets resolved as DNS, do not blame the registry by default. First inspect the **HTTP client integration path**: `RestClient` and `WebClient` must come from a `@LoadBalanced` builder; OpenFeign must not have a fixed URL or custom client bypassing LoadBalancer; HTTP Interfaces must wrap an integrated client adapter. Only after that should you examine the **`ServiceInstance` list** and the **selected physical address**. Being able to separate **DNS for a logical service name** from **DNS for a physical instance** is the key to accurate diagnosis and avoiding fixes at the wrong layer.

**Official references:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – Load-Balanced RestClient and WebClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients and HTTP Interfaces](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Cloud OpenFeign – Declarative HTTP Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Docker Docs – Compose Networking](https://docs.docker.com/compose/how-tos/networking/)
