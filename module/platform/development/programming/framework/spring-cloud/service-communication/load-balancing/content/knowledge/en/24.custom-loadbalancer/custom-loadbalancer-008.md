# Transforming Requests After Target Selection with Request Transformers

Spring Cloud LoadBalancer enables an HTTP client to call a **logical** address by service ID, for example **http://inventory-service/api/stock/BOOK-01**. After retrieving the **ServiceInstance** list, LoadBalancer picks a replica such as **inventory-a.internal:8080** and uses the physical address to send the HTTP request. However, many systems also need to **attach information about the selected replica** to the request: the instance ID for diagnostics, the zone for routing verification, a standardized technical header, or a signal for an upstream trusted gateway.

A **request transformer** is the dedicated extension point for that purpose. It receives the **HTTP request** and the **selected ServiceInstance**, and returns the transformed request to be sent onward. Unlike standard filters/interceptors, a transformer has direct access to the exact instance chosen by LoadBalancer for the current attempt.

This lesson in the **Customizing LoadBalancer** chapter clarifies transformer scope, APIs for **RestTemplate/RestClient, WebClient, and OpenFeign**, configuring multiple transformers, header/metadata handling examples, differences from suppliers/filters, retry and security implications, and unit and HTTP integration testing. The overarching goal is reliable inter-service communication when combining service discovery, health checks, routing, timeouts, and retries.

> **Version note:** The APIs described appear in current Spring Cloud Commons/LoadBalancer and Spring Cloud OpenFeign documentation. For a specific repository, use a compatible Spring Boot–Spring Cloud BOM. No build/test was executed against a project while authoring this Knowledge guide; examples must be compiled and verified against your actual dependency set.

## 1. Where Exactly Does the Transformer Sit?

~~~mermaid
flowchart TD
    A["Application creates GET http://inventory-service/api/stock/X"] --> B["LoadBalancer filter/interceptor"]
    B --> C["ServiceInstanceListSupplier: discovery, cache, health, zone, hint"]
    C --> D["Reactive/Blocking LoadBalancer: select ServiceInstance"]
    D --> E{"Valid replica available?"}
    E -->|No| F["No target: error/response per integration"]
    E -->|Yes| G["Reconstruct URI using ServiceInstance"]
    G --> H["Request transformers receive request and selected instance"]
    H --> I["HTTP transport sends final request"]
    I --> J["Backend returns HTTP response"]
~~~

This is a **conceptual diagram**. The exact placement of URI reconstruction, request creation, and transformer invocation depends on the blocking/reactive/Feign integration and version. The stable core contract is that **transformers receive the selected ServiceInstance**; do not assume every transformer sees the URI in the exact same physical state without checking the implementation.

Before/after example:

~~~text
Logical request:
    GET http://inventory-service/api/stock/BOOK-01
    X-Correlation-Id: trace-123

LoadBalancer selects:
    ServiceInstance id=inventory-a
    host=10.20.1.11, port=8080, secure=false
    metadata={zone: zone-a, version: v2}

Request sent to backend (illustrative):
    GET http://10.20.1.11:8080/api/stock/BOOK-01
    X-Correlation-Id: trace-123
    X-LB-Selected-Instance: inventory-a
~~~

**X-LB-Selected-Instance** is an example header, **not a mandatory Spring Cloud header**. Do not rely on this header as identity authentication; another client could spoof it if the backend accepts unprotected direct requests.

### 1.1. Three Questions, Three Extension Points

| Goal | Extension point | Timing |
| --- | --- | --- |
| Decide **which instances are eligible** | ServiceInstanceListSupplier, zone/health/hint filtering | Before selection |
| Decide **which instance to pick** | RoundRobinLoadBalancer, RandomLoadBalancer, or custom implementation | During selection |
| Transform **the request for the selected instance** | LoadBalancer request transformer | After selection |
| Add instance-independent tracing/auth | RestClient/RestTemplate interceptor, WebClient filter, Feign RequestInterceptor | Along each client's pipeline |
| Control retry attempts | Retry policy / LoadBalancer retry | When retry conditions trigger |
| Bound errors/wait times | Timeout, bulkhead, circuit breaker | At communication or application layer |

**A transformer is not a second LoadBalancer algorithm.** If you want to route traffic only to `zone-a` or `canary-v2`, do so in the **supplier or LoadBalancer policy**, not by arbitrarily rewriting hostnames/headers after another instance was already picked.

## 2. Contracts of the Three Core Transformers

According to Spring Cloud documentation:

| HTTP client | Transformer interface | Input and output request |
| --- | --- | --- |
| RestTemplate | **LoadBalancerRequestTransformer** | Spring HttpRequest → HttpRequest |
| RestClient | **LoadBalancerRequestTransformer** | Spring HttpRequest → HttpRequest |
| WebClient | **LoadBalancerClientRequestTransformer** | Spring WebFlux ClientRequest → ClientRequest |
| OpenFeign | **LoadBalancerFeignRequestTransformer** | Feign Request → Request |

Methods:

~~~java
// Spring Cloud Commons, blocking:
HttpRequest transformRequest(HttpRequest request, ServiceInstance instance);

// Spring Cloud Commons, reactive WebClient:
ClientRequest transformRequest(
        ClientRequest request, ServiceInstance instance);

// Spring Cloud OpenFeign:
Request transformRequest(Request request, ServiceInstance instance);
~~~

Do not confuse:

- **LoadBalancerRequestTransformer** with Spring Framework **ClientHttpRequestInterceptor**; standard interceptors do not receive the selected ServiceInstance.
- **LoadBalancerClientRequestTransformer** with WebClient's **ExchangeFilterFunction**; standard filters see pipeline requests without receiving ServiceInstance in their method signature like a transformer does.
- **LoadBalancerFeignRequestTransformer** with **feign.RequestInterceptor**; RequestInterceptor operates primarily on RequestTemplate, whereas the transformer receives the **Request** and the instance.

These APIs are **request transformation functions**, not places to make extra HTTP calls. Never open sockets, query registries, synchronously refresh tokens, or perform retries inside a transformer.

### 2.1. When There Is No ServiceInstance

If discovery/supplier returns no candidates, the LoadBalancer integration may produce an error or error response before HTTP transmission. **There is no guarantee a transformer will always be called with a valid instance.** In some interfaces/versions, the ServiceInstance parameter is annotated as nullable.

Therefore, code should do:

~~~java
if (instance == null) {
    return request;
}
~~~

If your application contract treats no-instance as an error, handle it at the **LoadBalancer error adapter/response handler** layer; never fabricate a dummy host or instance inside a transformer.

## 3. Declaring Dependencies and Load-Balanced Clients

A Gradle example using dependency versions managed by your project's Spring Boot–Spring Cloud BOM:

~~~gradle
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.springframework.boot:spring-boot-starter-web")

    // If using WebClient:
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // If using Spring Cloud OpenFeign:
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    // MockWebServer or WireMock for integration testing
}
~~~

You do not need to add **all three HTTP client starters** if the application uses only one style. The example groups options together so learners can see the related APIs.

RestTemplate configuration:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    return new RestTemplate();
}
~~~

RestClient configuration:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

WebClient configuration:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

Note: **@LoadBalanced** marks beans for Spring Cloud LoadBalancer customization. If a WebClient is already built from a builder with the LoadBalancer filter, do not add **ReactorLoadBalancerExchangeFilterFunction** a second time. In production, preserve Boot customizers for observability, TLS, and codecs when defining custom builders.

### 3.1. Use Service IDs Instead of Physical Hosts

RestClient:

~~~java
StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

WebClient:

~~~java
Mono<StockResponse> stock = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

If code calls **http://localhost:8080/...** with a client lacking LoadBalancer integration, the transformer has no real ServiceInstance to receive. A succeeding HTTP call alone is not proof that it passed through Spring Cloud LoadBalancer's transformer.

## 4. RestTemplate and RestClient: LoadBalancerRequestTransformer

**LoadBalancerRequestTransformer** receives a Spring Framework **HttpRequest** and a **ServiceInstance**. Official documentation uses **HttpRequestWrapper** to wrap the original request and override **getHeaders()** to add headers based on the selected replica.

Complete bean example:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.support.HttpRequestWrapper;

@Configuration(proxyBeanMethods = false)
class InventoryBlockingTransformers {

    @Bean
    LoadBalancerRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerRequestTransformer() {
            @Override
            public HttpRequest transformRequest(
                    HttpRequest request, ServiceInstance instance) {
                if (instance == null || instance.getInstanceId() == null) {
                    return request;
                }

                return new HttpRequestWrapper(request) {
                    @Override
                    public HttpHeaders getHeaders() {
                        HttpHeaders headers = new HttpHeaders();
                        headers.putAll(super.getHeaders());
                        headers.set("X-LB-Selected-Instance",
                                instance.getInstanceId());
                        return headers;
                    }
                };
            }
        };
    }
}
~~~

**Points to observe:**

1. The transformer **does not call ServiceInstanceListSupplier itself**. It receives the instance from LoadBalancer integration.
2. **HttpRequestWrapper** preserves all other parts of the original request and changes only what is overridden.
3. Construct a **new HttpHeaders** rather than mutating the original request's headers directly.
4. Use **headers.set()** instead of add() to prevent duplicate values when other filters/transformers touch the same header.
5. When ID is missing, skip adding the header; never turn null into the literal string **null**.

**Security note:** the interface can receive instances with metadata from external registries; validate values before placing them into HTTP headers. Section 11 illustrates allowlist-based validation.

### 4.1. Why Not Mutate request.getHeaders() Directly?

HttpRequest implementations may hold mutable or read-only headers, or share them with other interceptors. Code like:

~~~java
request.getHeaders().add(
        "X-LB-Selected-Instance", instance.getInstanceId());
return request;
~~~

can throw UnsupportedOperationException, cause unintended side effects, or duplicate headers across repeated transformations. **Returning a wrapper/new request** is the pattern shown in Spring Cloud docs and is easier to test.

### 4.2. Preserve Request Method and URI Carefully

If you only need to add a header, do not alter:

- **getMethod()**: GET/POST/PUT/DELETE have distinct semantics and idempotency.
- **getURI()**: holds the target resolved by LoadBalancer according to integration version.
- **Path, query, and fragment**: can affect routing, signatures, or cache keys.
- **Content-Length/Content-Type**: must stay consistent with the body if payloads change.

A transformer is not the place to buffer/replay request bodies by re-reading the request InputStream. Bodies may not be replayable, especially when retrying large uploads.

## 5. WebClient: LoadBalancerClientRequestTransformer

For **WebClient**, Spring Cloud provides **LoadBalancerClientRequestTransformer**. The request type is **org.springframework.web.reactive.function.client.ClientRequest**, built immutably; we create a new request from the original using **ClientRequest.from(request)**.

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.reactive.LoadBalancerClientRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;

@Configuration(proxyBeanMethods = false)
class InventoryReactiveTransformers {

    @Bean
    LoadBalancerClientRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerClientRequestTransformer() {
            @Override
            public ClientRequest transformRequest(
                    ClientRequest request, ServiceInstance instance) {
                if (instance == null || instance.getInstanceId() == null) {
                    return request;
                }

                return ClientRequest.from(request)
                        .headers(headers -> headers.set(
                                "X-LB-Selected-Instance",
                                instance.getInstanceId()))
                        .build();
            }
        };
    }
}
~~~

**Important:** WebClient is reactive, so requests are typically sent only when the Publisher is subscribed. Do not assume the transformer has run merely upon constructing the Mono.

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);

// At this point no request may have been sent yet, so no instance has been selected yet.

StepVerifier.create(call)
        .expectNextMatches(stock -> stock.available() >= 0)
        .verifyComplete();
~~~

One subscription triggers one instance selection; when **retryWhen** resubscribes, the LoadBalancer/transformer path may execute again for the new attempt. Test this rather than assuming instance ID was fixed when the Mono was created.

### 5.1. Placing Tracing and Auth in the Pipeline

WebClient can have:

~~~text
Client code
  -> Authentication ExchangeFilterFunction
  -> Observability/trace filters
  -> Spring Cloud LoadBalancer filter
  -> selected-instance request transformers
  -> ClientHttpConnector
~~~

Actual ordering depends on how the builder and filters are configured. **WebClient filters can run before or after the LoadBalancer filter**, whereas the dedicated transformer is always invoked within LoadBalancer integration using that attempt's ServiceInstance. If a trace filter writes a header after the transformer or vice versa, a header with the same name can be overwritten depending on order.

Never attach the LoadBalancer filter twice, and never attach a global WebClient filter carrying Inventory credentials to Payment/Catalog requests. When per-service scoping is needed, use **dedicated WebClients** or reliable service-ID checks.

### 5.2. When Should You Transform the URI in WebClient?

**ClientRequest.from(request).url(URI)** allows changing the URI in Spring Framework's API, but should not be used to pick a different host after LoadBalancer already selected a ServiceInstance. Doing so can:

- Bypass applied discovery/health/zone policies.
- Cause traces/metrics to log selectedInstance=A while real HTTP goes to B.
- Break TLS hostname verification/SNI or Host headers.
- Send Authorization headers to an untrusted host.
- Corrupt retry paths and observability.

If the goal is **changing paths by API version, rewriting base paths, or gateway routing**, configure the request URI before target selection, use gateway rewrite policies, or use dedicated version-routing mechanisms. Only transform URIs post-selection with a well-defined contract and integration tests covering URI, TLS, and auth.

## 6. OpenFeign: LoadBalancerFeignRequestTransformer

Spring Cloud OpenFeign provides a separate transformer, **LoadBalancerFeignRequestTransformer**, because Feign uses **feign.Request** rather than Spring Framework's HttpRequest/ClientRequest.

Example following official principles: copy headers, add service ID and instance ID, and build a new Request preserving method, URL, body, charset, and request template:

~~~java
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import feign.Request;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.openfeign.loadbalancer.LoadBalancerFeignRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryFeignTransformers {

    @Bean
    LoadBalancerFeignRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerFeignRequestTransformer() {
            @Override
            public Request transformRequest(
                    Request request, ServiceInstance instance) {
                if (instance == null) {
                    return request;
                }

                Map<String, Collection<String>> headers =
                        new HashMap<>(request.headers());
                headers.put("X-LB-Service",
                        Collections.singletonList(instance.getServiceId()));

                if (instance.getInstanceId() != null) {
                    headers.put("X-LB-Selected-Instance",
                            Collections.singletonList(instance.getInstanceId()));
                }

                return Request.create(
                        request.httpMethod(),
                        request.url(),
                        headers,
                        request.body(),
                        request.charset(),
                        request.requestTemplate());
            }
        };
    }
}
~~~

Here **Request.create(...)** is the overload illustrated in Spring Cloud OpenFeign documentation. For other Feign versions, verify the exact Request.create overload against your real dependencies before compiling.

### 6.1. The Feign Client Must Actually Go Through LoadBalancer

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

When the OpenFeign and LoadBalancer starters are present, **name** is the service ID used for discovery. Conversely, when a fixed URL is declared via **url** on @FeignClient or **spring.cloud.openfeign.client.config.<name>.url**, Feign may call the URL directly **without going through LoadBalancer**, and load-balanced request transformers will not necessarily run.

**Feign RequestInterceptor** operates on the template prior to/during request creation; it does not receive the selected ServiceInstance in its signature. If a header must reflect the actually chosen replica, use **LoadBalancerFeignRequestTransformer** rather than merely reading a static service ID in RequestInterceptor.

### 6.2. Preserve Body and Charset When Creating a New Feign Request

A common mistake when customizing Feign:

~~~java
// Wrong approach: recreating Request while dropping body, charset, or template.
// Use the appropriate overload and preserve fields from the original request.
~~~

Especially for POST/PUT, dropping the body or corrupting Content-Type/Content-Length causes backends to return 400/415 or behave incorrectly. Transformers should **modify only what is needed** and preserve all remaining fields.

## 7. Quick Reference Table for Choosing the Right Client API

| Scenario | Interface | Creating the new request |
| --- | --- | --- |
| Blocking RestTemplate GET | LoadBalancerRequestTransformer | HttpRequestWrapper; override getHeaders() |
| Blocking RestClient POST | LoadBalancerRequestTransformer | HttpRequestWrapper; keep method, URI, body managed by transport |
| Reactive WebClient GET/POST | LoadBalancerClientRequestTransformer | ClientRequest.from(original).headers(...).build() |
| Feign declarative client | LoadBalancerFeignRequestTransformer | Copy headers and Request.create(...) keeping original fields |

Declaring a **Spring bean of this interface does not automatically attach LoadBalancer to an HTTP client**. The corresponding integration and logical service-ID URI must be present. Nor can you register a LoadBalancerRequestTransformer in place of a LoadBalancerClientRequestTransformer, because request types and pipelines differ.

## 8. Multiple Transformers: Order Is Part of the Contract

Spring Cloud allows declaring **multiple transformers**. LoadBalancer documentation notes that application order follows defined bean ordering and can be explicitly controlled via **@Order** / the interface's **DEFAULT_ORDER** constant.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderedTransformers {

    @Bean
    @Order(-100)
    LoadBalancerClientRequestTransformer ensureInstanceHeader() {
        return (request, instance) -> {
            if (instance == null || instance.getInstanceId() == null) {
                return request;
            }
            return ClientRequest.from(request)
                    .headers(h -> h.set("X-LB-Selected-Instance",
                            instance.getInstanceId()))
                    .build();
        };
    }

    @Bean
    @Order(100)
    LoadBalancerClientRequestTransformer markDiagnostics() {
        return (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-LB-Transform-Version", "1"))
                        .build();
    }
}
~~~

In this example, bean `-100` runs before bean `100` **provided the transformation pipeline consumes the ordered bean list as expected in your version**. Avoid relying on component-scan order or bean method names as a contract when reordering would alter headers.

If two transformers both write **X-LB-Selected-Instance**:

~~~text
Transformer A: set X-LB-Selected-Instance = inventory-a
Transformer B: set X-LB-Selected-Instance = override

Result: depends on which transformer runs later.
~~~

If **add** is used instead of **set**, the result can even become two header values, causing ambiguity in backends or proxies. That is why each field should have **one owner** with tested ordering.

### 8.1. DEFAULT_ORDER and Equal Precedence

The interfaces define **DEFAULT_ORDER**; for instance, LoadBalancerRequestTransformer.DEFAULT_ORDER and LoadBalancerClientRequestTransformer.DEFAULT_ORDER serve as default ordering values. With multiple beans sharing the same order, never rely on implicit ordering for business contracts.

If one transformer must run before all others, assign an explicit order and verify via unit/integration tests. Do not equate this order with **relative position against ClientHttpRequestInterceptor, WebClient filters, or Feign RequestInterceptor**; those belong to separate pipelines.

### 8.2. Do Not Use a Transformer to Make Secondary Calls

Transformers should perform **pure, fast transformations**:

- Never call a REST API to fetch a new token inside `transformRequest`.
- Never query a database or registry over the network per attempt.
- Never mutate shared state unsafely.
- Never perform blocking I/O on WebClient's reactive pipeline.

If OAuth2 tokens are needed, prefer **OAuth2AuthorizedClientManager** and dedicated auth filters/interceptors; if instance metadata is needed, read from the passed-in **ServiceInstance**.

## 9. Scope Transformers to the Right Service ID

A transformer bean in the **parent ApplicationContext** can apply to multiple HTTP clients of the same type. If only Inventory should receive a custom header, **do not assume a global bean is automatically scoped by @LoadBalancerClient(name = "inventory-service")**.

Conditional guard example:

~~~java
@Bean
LoadBalancerClientRequestTransformer inventoryOnlyHeader() {
    return (request, instance) -> {
        if (instance == null
                || !"inventory-service".equals(instance.getServiceId())
                || instance.getInstanceId() == null) {
            return request;
        }

        return ClientRequest.from(request)
                .headers(h -> h.set("X-LB-Selected-Instance",
                        instance.getInstanceId()))
                .build();
    };
}
~~~

This is a **transformer-layer guard**, not a security boundary. If service discovery metadata is wrong or an instance maps to an unauthorized host, a header guard does not replace mTLS, DNS policy, or endpoint allowlists.

When configurations must differ completely per service ID, Spring Cloud also provides **@LoadBalancerClient(name, configuration)** to customize suppliers/algorithms in a child context. **Do not assume** every transformer bean declared in a child config integrates identically across all clients and versions; verify actual registration and scope against your project's dependencies.

## 10. Using ServiceInstance Metadata Safely

A ServiceInstance can expose:

~~~java
instance.getInstanceId();
instance.getServiceId();
instance.getHost();
instance.getPort();
instance.isSecure();
instance.getMetadata();
~~~

Example Inventory registry:

| Instance ID | zone | release | weight |
| --- | --- | --- | ---: |
| inventory-a | zone-a | stable | 90 |
| inventory-b | zone-a | canary | 10 |
| inventory-c | zone-b | stable | 90 |

Metadata like **zone, release, weight** can be used during **instance filtering/selection**, and after selection a transformer can also attach validated information to headers sent to the backend:

~~~java
@Bean
LoadBalancerClientRequestTransformer selectedZoneHeader() {
    return (request, instance) -> {
        if (instance == null) {
            return request;
        }

        String zone = instance.getMetadata().get("zone");
        if (!Set.of("zone-a", "zone-b").contains(zone)) {
            return request;
        }

        return ClientRequest.from(request)
                .headers(h -> h.set("X-Selected-Zone", zone))
                .build();
    };
}
~~~

The **allowlist** condition stops arbitrary metadata from being copied straight into headers. **X-Selected-Zone** is a technical example, never to be used by a backend as proof of geographic region, tenant identity, or authorization.

### 10.1. Do Not Trust Discovery Metadata Blindly

Some registries let applications self-register metadata. If an instance carries metadata like:

~~~text
zone = zone-a
header-value = invalid or overly long data
~~~

copying `header-value` directly into the request can cause:

- HTTP header validation exceptions.
- Header injection or proxy policy conflicts.
- High-cardinality logs/metrics.
- Security scope bypasses.

Enforce **allowlists, length limits, schema validation, and normalization**. Never let metadata dictate sending Bearer tokens, private keys, or tenant headers to an untrusted host.

### 10.2. Attaching Instance IDs More Safely

A helper validating the ID before setting the header:

~~~java
final class InstanceHeaderPolicy {

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    static Optional<String> validId(ServiceInstance instance) {
        if (instance == null || instance.getInstanceId() == null) {
            return Optional.empty();
        }
        String id = instance.getInstanceId();
        return SAFE.matcher(id).matches()
                ? Optional.of(id)
                : Optional.empty();
    }
}
~~~

This example requires imports for **java.util.Optional**, **java.util.regex.Pattern**, and **ServiceInstance**. It only illustrates a safe-character policy for a technical header. If your system uses Kubernetes pod UIDs, UUIDs, or another instance ID format, pick a regex matching your **real contract**—do not truncate data arbitrarily or invent untraceable values.

When an ID is invalid, omit the header and log a safe warning. Do not dump untrusted raw IDs into logs if they could originate externally.

## 11. Diagnostic Headers Differ from Authentication Headers

A request transformer is often helpful for adding:

~~~text
X-LB-Service: inventory-service
X-LB-Selected-Instance: inventory-a
X-Selected-Zone: zone-a
~~~

These headers are strictly **observability information**. The backend must never infer that:

- The request is authenticated.
- The user belongs to a specific tenant.
- The request traversed the right network policy.
- The token has the right audience.
- The server may skip rate limiting or authorization.

Any HTTP client can send self-named headers unless a gateway/server stripping policy exists. **Instance headers do not replace mTLS/JWT/OAuth2.**

### 11.1. Prevent Callers from Spoofing Transformer-Managed Headers

Suppose an API gateway receives from the Internet:

~~~http
X-LB-Selected-Instance: inventory-admin
~~~

If the gateway forwards that header intact to Order, and the transformer uses **headers.add()**, the backend can see two values and pick the wrong one depending on its parser. Use:

~~~java
headers.set("X-LB-Selected-Instance", safeInstanceId);
~~~

to **overwrite any caller-supplied value** within your HTTP client's scope. At the same time, the gateway must **strip or normalize** headers treated as internal, and the backend must trust identity solely from authenticated channels.

### 11.2. Authorization Headers Must Be Decided in the Right Place

**Authorization: Bearer ...** should be attached by an OAuth2 authorized client/filter or security interceptor configured for the specific audience/downstream. A transformer only receives ServiceInstance to enrich the final call; attaching tokens based on unverified metadata/hosts risks **token exfiltration**.

When instance-scoped token audiences are genuinely needed, build a dedicated **credential provider with trust policy, audience mapping, and caching**—never make a transformer call a Token Endpoint synchronously on every attempt.

**Do not modify Authorization, Cookie, Host, Content-Length, or hop-by-hop headers** when the goal is merely adding an instance ID. In HTTP/2, certain hop-by-hop headers are even forbidden or represented differently.

## 12. Do Not Arbitrarily Modify Host, TLS SNI, or X-Forwarded-* Headers

In HTTP, the logical request uses the service ID as host, while the physical request goes to the selected ServiceInstance's host/port. The **Host header** and **TLS Server Name Indication (SNI)** are related yet distinct: changing the HTTP Host header **does not fix TLS certificate validation**.

Example:

~~~text
Logical URI: https://inventory-service/stock
Instance:    inventory-a.internal:8443
TLS peer:    certificate SAN inventory-a.internal
~~~

If a transformer explicitly sets:

~~~text
Host: inventory-service
~~~

while the TLS handshake happens against `inventory-a.internal`, you must evaluate **certificate SAN, SNI, virtual host routing, and proxy policies**. Never try to "fix" `SSLHandshakeException` by disabling hostname verification.

### 12.1. OpenFeign's X-Forwarded Headers Support

Spring Cloud OpenFeign supports:

~~~yaml
spring:
  cloud:
    loadbalancer:
      x-forwarded:
        enabled: true
~~~

OpenFeign documentation describes this feature for adding **X-Forwarded-Host** and **X-Forwarded-Proto** via its built-in transformer. You do not need to write a second custom transformer to overwrite these headers unless a specific, tested requirement demands it.

X-Forwarded-Host/Proto affect URL generation, redirects, and server-side security policies. Trust them only behind a known proxy/gateway that sanitizes external caller headers; **never treat X-Forwarded-* as verified identity**.

### 12.2. Never Rewrite the URL to an Unapproved Host

The client API allows a transformer to alter requests, yet using metadata to pick a different host can send requests outside the health/discovery-vetted candidate set while carrying sensitive credentials.

If the goal is **targeting canary or zone**, apply:

~~~text
Client hint / API version / zone
        |
        v
ServiceInstanceListSupplier filters candidates
        |
        v
LoadBalancer selects
        |
        v
Transformer only writes observability metadata
~~~

Do not apply:

~~~text
LoadBalancer selects A
        |
        v
Transformer reads A's metadata and rewrites URL to B
        |
        v
Metrics record A, actual HTTP goes to B
~~~

## 13. Transformers and Hint-Based Routing Work in Opposite Directions

**HintBasedServiceInstanceListSupplier** can narrow candidates based on a request hint, such as a Spring Cloud-supported header or corresponding hints config. That is data **entering** instance selection.

A transformer receives the selected ServiceInstance *after* selection, so headers added by the transformer **cannot retroactively alter the decision just made**.

~~~text
Request header X-SC-LB-Hint: canary
         |
         v
HintBasedServiceInstanceListSupplier
         |
         v
Selects inventory-b (metadata hint=canary)
         |
         v
Transformer adds X-LB-Selected-Instance: inventory-b
~~~

If selection must depend on **tenant, API version, or sticky session**, pass that data into context/suppliers **before selection**. Never write a transformer expecting a header added afterward to redirect LoadBalancer on that same call.

### 13.1. Recording Selected Instance Data to Audit Policy

Suppose a request arrives with hint **canary**, yet the backend receives:

~~~text
X-LB-Selected-Instance: inventory-a
~~~

This could indicate:

- No instance matched the hint, so the supplier fell back.
- The hint header did not propagate into the request context properly.
- Instance metadata was misconfigured.
- Supplier ordering filtered the list unexpectedly.

The transformer helps **observe the outcome**, though it cannot fix the root cause itself. Inspect the supplier chain and request-context propagation.

## 14. Retries and Transformers: Each Attempt Can Pick a Different Target

Suppose Spring Cloud LoadBalancer / the HTTP client has a retry policy:

~~~text
Logical GET /stock/X

Attempt 1:
  selectedInstance = inventory-a
  transformer -> X-LB-Selected-Instance: inventory-a
  backend A -> 503

Attempt 2:
  selectedInstance = inventory-b
  transformer -> X-LB-Selected-Instance: inventory-b
  backend B -> 200
~~~

If a transformer reads the instance **from a constructor or singleton field** rather than the method parameter, it can emit the wrong header on the second attempt. **Always use the ServiceInstance passed to the current attempt.**

### 14.1. Do Not Assume Every Retry Picks a Different Instance

Retries can:

- Retry on the **same ServiceInstance**.
- Run selection again, with the policy picking the previous instance once more.
- Avoid the previous instance when other candidates exist and a retry-aware supplier is active.
- Skip re-running the transformer if failure occurred too early or in a different client integration.

Transformer invocation counts and HTTP attempts should be **counted in integration tests**. Never assume one logical request calls the transformer exactly once or that every retry re-executes the identical chain.

### 14.2. Never Track Attempt Counts via a Mutable Shared Counter in a Transformer

Transformer beans are typically singletons. Storing:

~~~java
private int attemptNumber = 0;
~~~

and incrementing it per request mixes **all concurrent requests** to the service rather than counting attempts of one logical call. To distinguish retries, use tracing/RetryContext or properly scoped request context; only emit an attempt header when the value is scoped accurately by the framework or application.

### 14.3. HTTP Method and Idempotency Do Not Change Because of a Transformer

A transformer cannot make a non-idempotent POST safe merely by adding an instance-ID header. When retrying order/payment POSTs, require **idempotency keys with server-side deduplication** plus explicit deadline and attempt budgets.

A streamed request body may also be non-replayable. Never implement retries inside a transformer, avoiding body replays outside the HTTP client's control.

## 15. Unit Testing LoadBalancerRequestTransformer Directly

Before spinning up a Spring ApplicationContext, you can test a transformer as a **pure function mapping request + instance to a new request**. You control instance ID and headers directly without relying on Round Robin.

JUnit Jupiter example with Spring Test:

~~~java
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpRequest;
import org.springframework.mock.http.client.MockClientHttpRequest;

import static org.junit.jupiter.api.Assertions.*;

class BlockingTransformerTest {

    private final LoadBalancerRequestTransformer transformer =
            new InventoryBlockingTransformers().selectedInstanceHeader();

    @Test
    void addsSelectedInstanceWithoutMutatingOriginal() {
        URI originalUri =
                URI.create("http://inventory-service/api/stock/BOOK-01");
        MockClientHttpRequest original =
                new MockClientHttpRequest(HttpMethod.GET, originalUri);
        original.getHeaders().set("X-Correlation-Id", "trace-123");

        ServiceInstance selected = new DefaultServiceInstance(
                "inventory-a", "inventory-service",
                "localhost", 8081, false);

        HttpRequest transformed =
                transformer.transformRequest(original, selected);

        assertEquals(HttpMethod.GET, transformed.getMethod());
        assertEquals(originalUri, transformed.getURI());
        assertEquals("trace-123",
                transformed.getHeaders().getFirst("X-Correlation-Id"));
        assertEquals("inventory-a",
                transformed.getHeaders().getFirst("X-LB-Selected-Instance"));

        // Original headers were not modified by the transformer.
        assertNull(original.getHeaders().getFirst("X-LB-Selected-Instance"));
    }

    @Test
    void noInstanceDoesNotInventTarget() {
        MockClientHttpRequest original = new MockClientHttpRequest(
                HttpMethod.GET, URI.create("http://inventory-service/test"));

        HttpRequest result =
                transformer.transformRequest(original, null);

        assertSame(original, result);
    }
}
~~~

This test uses the **InventoryBlockingTransformers** implementation from section 4, Spring Test's **MockClientHttpRequest**, and a fixed ServiceInstance. If your project enables nullable type checks or uses a different API version, adjust annotations and imports accordingly.

**What this test proves:** the transformer returns a wrapper with the right header, preserves original URI/method/headers, and handles null instances. It **does not yet prove** that a real RestTemplate/RestClient registered the transformer and runs through LoadBalancer.

### 15.1. Testing Pre-Existing Spoofed Headers

A security test case to include:

~~~java
original.getHeaders().set(
        "X-LB-Selected-Instance", "attacker-supplied");

HttpRequest result = transformer.transformRequest(original, selected);

assertEquals("inventory-a",
        result.getHeaders().getFirst("X-LB-Selected-Instance"));
assertEquals(1,
        result.getHeaders().get("X-LB-Selected-Instance").size());
~~~

This assertion belongs inside the **same test fixture** above. It verifies **set rather than add**, preventing spoofed headers from lingering as duplicate values.

## 16. Unit Testing WebClient Transformers: Immutable Requests

For ClientRequest:

~~~java
@Test
void webClientTransformerPreservesRequestAndAddsHeader() {
    URI uri =
            URI.create("http://inventory-service/api/stock/BOOK-01?q=1");

    ClientRequest original =
            ClientRequest.create(HttpMethod.GET, uri)
                    .header("X-Correlation-Id", "trace-456")
                    .build();

    ServiceInstance instance = new DefaultServiceInstance(
            "inventory-b", "inventory-service",
            "localhost", 8082, false);

    LoadBalancerClientRequestTransformer transformer =
            new InventoryReactiveTransformers().selectedInstanceHeader();

    ClientRequest changed =
            transformer.transformRequest(original, instance);

    assertEquals(original.url(), changed.url());
    assertEquals(original.method(), changed.method());
    assertEquals("trace-456",
            changed.headers().getFirst("X-Correlation-Id"));
    assertEquals("inventory-b",
            changed.headers().getFirst("X-LB-Selected-Instance"));
    assertNull(
            original.headers().getFirst("X-LB-Selected-Instance"));
}
~~~

Key imports include **java.net.URI**, **HttpMethod**, **ClientRequest**, **DefaultServiceInstance**, **ServiceInstance**, **LoadBalancerClientRequestTransformer**, and JUnit assertions. No sockets or Mono subscriptions are needed because the transformer method is invoked directly.

This is a **pure request-transformation** unit test. To prove the transformer is invoked at the right time by the **Spring Cloud WebClient filter**, write an integration test or test the filter wired with ReactiveLoadBalancer.

### 16.1. Verifying Multiple Ordered Transformers

You can compose two transformers:

~~~java
LoadBalancerClientRequestTransformer first =
        (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-Phase", "first"))
                        .build();

LoadBalancerClientRequestTransformer second =
        (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-Phase", "second"))
                        .build();

ClientRequest afterFirst =
        first.transformRequest(original, instance);
ClientRequest afterSecond =
        second.transformRequest(afterFirst, instance);

assertEquals("second",
        afterSecond.headers().getFirst("X-Phase"));
~~~

This tests only **composition**, not Spring bean ordering. In integration tests, if order is a strict requirement, verify live order when beans are sorted by `@Order` and auto-injected by the framework.

## 17. Unit Testing Feign Transformers: Preserving Method, URL, and Body

A proper Feign transformation must never drop fields from the original request:

~~~java
@Test
void feignTransformerPreservesMethodUrlAndBody() {
    byte[] body = "{\"sku\":\"BOOK-01\"}"
            .getBytes(StandardCharsets.UTF_8);

    Request original = Request.create(
            Request.HttpMethod.POST,
            "http://inventory-service/api/reservations",
            Map.of("Content-Type", List.of("application/json")),
            body,
            StandardCharsets.UTF_8,
            new RequestTemplate());

    ServiceInstance selected = new DefaultServiceInstance(
            "inventory-c", "inventory-service",
            "localhost", 8083, false);

    LoadBalancerFeignRequestTransformer transformer =
            new InventoryFeignTransformers().selectedInstanceHeader();

    Request changed = transformer.transformRequest(original, selected);

    assertEquals(original.httpMethod(), changed.httpMethod());
    assertEquals(original.url(), changed.url());
    assertArrayEquals(body, changed.body());
    assertEquals(
            List.of("inventory-c"),
            List.copyOf(changed.headers().get("X-LB-Selected-Instance")));
}
~~~

Imports include **feign.Request**, **feign.RequestTemplate**, **StandardCharsets**, **Map**, **List**, **DefaultServiceInstance**, and Spring Cloud OpenFeign's transformer interface. Check the exact **Request.create** overload provided by your OpenFeign version.

**This is not a POST retry test**: it only verifies the transformer does not drop the body. Retrying side-effecting POSTs must obey business idempotency policies.

## 18. Integration Testing: Verifying Headers at a Real HTTP Backend

A unit test calling the transformer directly can pass even when **the client does not use @LoadBalanced at all**. An integration test must issue requests by **service ID**, let LoadBalancer pick an instance, and inspect **which headers the backend actually received**.

Fixture:

~~~text
        GET http://inventory-service/api/stock/X
                         |
                         v
                  Spring LoadBalancer
                       /     \
                      /       \
             A localhost:portA  B localhost:portB
                  |                 |
             MockWebServer A   MockWebServer B
                  |                 |
              observe:         observe:
              method, URI,     method, URI,
              X-LB-Selected-Port
~~~

### 18.1. A Spring Boot + MockWebServer Example for WebClient

To avoid depending on SimpleDiscoveryClient's **getInstanceId()**, this fixture uses the **X-LB-Selected-Port** header; the port is always read directly from the selected ServiceInstance. Condensed yet structurally complete test example:

~~~java
@SpringBootTest(
        classes = RequestTransformerIT.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RequestTransformerIT {

    static final MockWebServer A = new MockWebServer();
    static final MockWebServer B = new MockWebServer();

    static {
        try {
            A.start();
            B.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @DynamicPropertySource
    static void instances(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
            () -> A.url("/").toString());
        registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
            () -> B.url("/").toString());
        registry.add(
            "spring.cloud.loadbalancer.retry.enabled",
            () -> "false");
    }

    @Autowired
    @LoadBalanced
    WebClient.Builder builder;

    @Test
    void transformerRunsAfterSelectionAndReachesBackend() throws Exception {
        for (int i = 0; i < 6; i++) {
            A.enqueue(new MockResponse().setBody("A"));
            B.enqueue(new MockResponse().setBody("B"));
        }

        WebClient webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        for (int i = 0; i < 6; i++) {
            StepVerifier.create(webClient.get()
                    .uri("/api/stock/{sku}?wh={wh}", "BOOK-01", "HCM")
                    .retrieve()
                    .bodyToMono(String.class))
                    .expectNextMatches(body -> Set.of("A", "B").contains(body))
                    .verifyComplete();
        }

        int countA = A.getRequestCount();
        int countB = B.getRequestCount();
        assertEquals(6, countA + countB);
        assertTrue(countA > 0);
        assertTrue(countB > 0);

        for (int i = 0; i < countA; i++) {
            RecordedRequest request = A.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("/api/stock/BOOK-01?wh=HCM", request.getPath());
            assertEquals(Integer.toString(A.getPort()),
                    request.getHeader("X-LB-Selected-Port"));
        }

        for (int i = 0; i < countB; i++) {
            RecordedRequest request = B.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("/api/stock/BOOK-01?wh=HCM", request.getPath());
            assertEquals(Integer.toString(B.getPort()),
                    request.getHeader("X-LB-Selected-Port"));
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        A.shutdown();
        B.shutdown();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        @LoadBalanced
        WebClient.Builder builder() {
            return WebClient.builder();
        }

        @Bean
        LoadBalancerClientRequestTransformer selectedPort() {
            return (request, instance) ->
                    ClientRequest.from(request)
                            .headers(h -> h.set(
                                    "X-LB-Selected-Port",
                                    Integer.toString(instance.getPort())))
                            .build();
        }
    }
}
~~~

**Libraries/test imports:** Spring Boot Test, Spring Context/Test, JUnit Jupiter, Reactor Test, Spring Cloud LoadBalancer, and **OkHttp MockWebServer 4.x** (package `okhttp3.mockwebserver`); import the classes shown in the test, plus **java.io.IOException**, **java.util.Set**, **java.util.concurrent.TimeUnit**, and **org.springframework.web.reactive.function.client.WebClient**.

Fixture assumptions:

- `SimpleDiscoveryClient` is created by Spring and returns the two service instances from properties.
- Selection uses Round Robin over both replicas without zone/health/hint filters dropping candidates.
- No concurrent test requests share the same Spring ApplicationContext/MockWebServer.
- The HTTP client actually received the LoadBalancer filter from **@LoadBalanced WebClient.Builder**.

**Do not assert the first request always hits A.** Round Robin may start at another index; what matters is that **every real request reaches the chosen host/port** and the total request count matches.

### 18.2. Testing Blocking RestClient/RestTemplate

For RestClient, the same fixture can register:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}

@Bean
LoadBalancerRequestTransformer selectedPort() {
    return (request, instance) -> {
        if (instance == null) {
            return request;
        }
        return new HttpRequestWrapper(request) {
            @Override
            public HttpHeaders getHeaders() {
                HttpHeaders copy = new HttpHeaders();
                copy.putAll(super.getHeaders());
                copy.set("X-LB-Selected-Port",
                        Integer.toString(instance.getPort()));
                return copy;
            }
        };
    };
}
~~~

Then call **http://inventory-service/...** using a RestClient built from that builder, and inspect **RecordedRequest** identically. Do not call localhost directly and assume the blocking LoadBalancer interceptor ran.

### 18.3. Testing OpenFeign

Create **@FeignClient(name = "inventory-service")** without **url**, add a **LoadBalancerFeignRequestTransformer** setting **X-LB-Selected-Port**, and verify MockWebServer receives the header matching the selected port. Test both GET and POST payloads to ensure URL/method/body stay intact.

OpenFeign may use a different client/retry setup than RestClient, so **do not reuse expected attempt counts** from a WebClient test without aligning retry configurations.

## 19. Testing Edge Cases and Failure Modes

Many transformer bugs appear only when discovery metadata is missing, retries occur, or another filter touches the same header. A thorough test suite covers more than the **happy path**.

| Case | Input / test setup | Expectation |
| --- | --- | --- |
| Single instance | [A] | Transformer receives A; header reflects A |
| Two instances | [A, B] | Header matches the actual instance of each HTTP attempt |
| No instance | [] | LoadBalancer reports error/no-instance; no request sent to backend |
| `instance.getInstanceId()` null | Null ID | Skips header or handles per contract; never throws NPE |
| Missing `zone` metadata key | metadata={} | Does not add X-Selected-Zone |
| Zone outside allowlist | zone=unknown | Does not put value into header |
| Caller sends X-LB-Selected-Instance | Spoofed header | Transformer sets new value; no duplicate values |
| Two transformers write same header | Different `@Order` | Final value matches defined order |
| GET with query/encoding | URI with encoded characters | Method, path, and query stay intact |
| POST with JSON body | body, Content-Type | Body/method/charset preserved |
| Retry same instance | A → A | Header on every attempt reflects A |
| Retry different instance | A → B | Next attempt's header reflects B; no stale cached ID |
| TLS/HTTPS scheme | Secure instance, valid cert/SAN | Does not alter Host/SNI to break handshake |
| Another service Payment | Not inventory-service | Does not leak Inventory-only headers/credentials |
| WebClient cancellation | Mono cancelled | Transformer holds no resources and never blocks |

### 19.1. No ServiceInstance Available

When the supplier is empty, LoadBalancer produces an error or error response. Depending on Spring Cloud version and config, WebClient may receive **503 Service Unavailable** (some adapters allow 404), yet this is **not** a real backend returning 503.

Tests should verify:

~~~text
source instance list = []
selected instance    = none
backend request count = 0
caller result         = error/no-instance per contract
~~~

**Transformers are not required to be invoked with instance=null** across all integrations. A null-guard unit test is defensive; integration tests should not expect a transformer to invent instance headers for a targetless request.

### 19.2. Timeouts Before vs. After the Transformer

If a timeout occurs:

- **Before selecting an instance** (slow discovery, publisher cancellation): the transformer may never have run.
- **After selection but before HTTP send** (pool acquire/connect): the transformer may have run while the backend received nothing.
- **After backend receives request** (response/read timeout): the backend may have processed it; the transformer is usually unrelated to the timeout.

Thus, **transformer invocations** do not equal **backend-processed requests**, let alone logical successes. Measure HTTP client attempts, backend recorded requests, and trace states separately.

### 19.3. Filter Ordering and Security Properties

A test should produce:

~~~text
Authorization from auth filter
X-Correlation-Id from tracing
X-LB-Selected-Instance from transformer
~~~

Verify all three at MockWebServer. Then add a call to **payment-service** and confirm Inventory-only credentials/headers are not sent to Payment. If a filter/proxy rewrites headers, tests will catch mismatches before or after selection.

## 20. Observability and Performance of Transformers

A well-behaved transformer is a brief transformation with no I/O and no mutable state shared across concurrent requests. If every request calls a registry or backend from inside a transformer, throughput suffers an **extra network hop** on top of LoadBalancer.

### 20.1. Which Logs and Metrics Are Enough?

| Field | Purpose | Note |
| --- | --- | --- |
| logical service ID | Inventory/Payment/Catalog | Low cardinality |
| selected instance ID | Correlate chosen host/instance | Avoid high-cardinality metric tags if instance churn is high |
| selected zone | Diagnose zone routing | Accept only from controlled metadata |
| operation/URI template | Group GET stock, reserve, etc. | Never put real SKUs/customer IDs in metric tags |
| retry attempt | Separate logical call from HTTP attempt | Read from properly scoped retry context |
| transform outcome | Header added/skipped/invalid metadata | Never log credential contents |
| request status/duration | Success, 4xx/5xx, timeout | Separate transport errors from backend status |
| correlation/trace ID | Link caller and backend logs | Never use as high-cardinality metric tag |

Spring Cloud LoadBalancer supports meters such as:

~~~text
loadbalancer.requests.success
loadbalancer.requests.failed
loadbalancer.requests.discard
~~~

These names are documented by Spring Cloud LoadBalancer for request statistics in supported integrations; they **do not automatically measure transformer execution counts separately**, and availability depends on dependencies and auto-configuration.

If custom metrics are needed, define:

~~~text
lb_transformer_applied_total{client="webclient",service="inventory-service"}
lb_transformer_skipped_total{reason="missing-instance-id"}
lb_transformer_invalid_metadata_total{key="zone"}
~~~

These are **suggested metric names**, not built-in Spring meters. Never use **instanceId, trace ID, SKU, or user ID** as unbounded tags; record those values in traces/logs with appropriate sampling and masking.

### 20.2. Never Log Payloads or Tokens in a Transformer

A transformer sees request headers and the selected ServiceInstance. Never log:

- Authorization/Bearer tokens.
- Cookies, Set-Cookie, or API keys.
- Raw URLs containing secrets or sensitive query parameters.
- Full request bodies containing customer data.
- ServiceInstance metadata containing internal secrets.

Log only allowlisted technical fields. On header validation errors, log key name, error type, and service ID; avoid printing untrusted raw header values.

### 20.3. Transformers Are Not for Health Checking

Never write:

~~~java
if (!httpPing(instance.getHost(), instance.getPort())) {
    // Pick another instance by calling REST inside the transformer.
}
~~~

This causes:

- Doubled I/O on every attempt.
- Slowed request paths and WebClient backpressure.
- Race conditions between the ping and the real HTTP request.
- Bypassing official retry/deadline handling and metrics.

For health-aware selection, use **HealthCheckServiceInstanceListSupplier** or discovery/provider health semantics. For circuit breaking, configure it per operation and policy.

## 21. Symptom-Based Diagnostic Guide

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Missing selected-instance header | Client lacks `@LoadBalanced` or transformer bean is outside integrated context | Verify bean, starters, and filters/interceptors |
| Transformer does not run in WebClient unit test | Mono was never subscribed | Use `StepVerifier.verify` or subscribe |
| Header appears with wrong ID | Singleton cached instance or non-request metadata used | Always use the current `ServiceInstance` parameter |
| Header contains two instance IDs | Used `add()` instead of `set()` or multiple transformers | Define single owner/order; use `set()` |
| Header wrong after retry | Retry sits at another layer; transformer not invoked as expected | Test HTTP attempts alongside selected instances |
| Backend receives another service's header | Transformer too global without service-ID guard | Use dedicated client or per-service guard |
| 401/403 after adding transformer | Touched `Authorization`/Host/forwarded security headers | Separate auth provider from transformer |
| `SSLHandshakeException` after rewrite | URI host/SNI/cert SAN mismatch | Check physical URI and certificate |
| Actual request hits B while metric says A | Transformer rewrote URL or tracing hooked wrong step | Never rewrite host post-selection; compare recorded requests |
| No instance and backend receives zero requests | Discovery/health/supplier returned empty | Diagnose provider/cache/filter chain |
| HTTP 503 blamed on transformer | Backend or LoadBalancer returned 503 | Check backend request counts |
| WebClient event loop blocked | Transformer performed blocking I/O | Remove all I/O from transformer |
| CPU/GC spike after adding transformer | Heavy metadata copying/serialization per request | Add small headers only; avoid heavy allocations |
| Feign Request lost its body | `Request.create` dropped body/charset/template | Copy all fields from original `Request` |
| RestClient works while RestTemplate does not | Separate beans/client integrations | Verify `@LoadBalanced` and request factories |
| Round Robin does not alternate A/B cleanly | Snapshot/seed/concurrency/filter/retry differs from assumption | Assert membership/selected port, not fixed first pick |

### 21.1. Ten-Step Debugging Workflow

~~~text
1. Which client does the code call? RestTemplate, RestClient, WebClient, Feign?
2. Does the client have @LoadBalanced or the LoadBalancer filter/interceptor?
3. Does the logical URI host match the exact service ID?
4. Which instances does ServiceInstanceListSupplier return?
5. Which ServiceInstance ID/host/port did LB select?
6. Is the transformer bean of the right interface and in the right Spring context?
7. Was the transformer actually invoked on that specific attempt?
8. What are the transformed request headers/URI (masked)?
9. Which MockWebServer/backend actually received the HTTP request?
10. Did any retry, timeout, auth, proxy, or filter alter/replace the result?
~~~

Without step 9, you have verified only **client intent**, not that the HTTP request reached the real target with the final headers.

## 22. Case Study: Controlled Diagnostic Header for Inventory

### Context

Order Service calls Inventory with both **RestClient** and **WebClient**. Meanwhile, Inventory runs three replicas A/B/C across two zones. Operations wants to know **which request went to which instance**, especially when retries change targets.

Requirements:

- Keep request method, body, path, query, and authentication intact.
- Add **X-LB-Selected-Instance** after an instance is selected.
- Apply exclusively to **inventory-service**.
- Omit the header if the instance ID is invalid.
- Prevent callers from spoofing internal values.
- Prove via tests that A→B retries write the right header on each attempt.

### Design

~~~mermaid
flowchart TD
    A["Order HTTP adapter"] --> B["LoadBalanced client"]
    B --> C["Supplier fetches instance list"]
    C --> D["LB selects A/B/C"]
    D --> E{"serviceId = inventory-service?"}
    E -->|No| F["Keep original request"]
    E -->|Yes| G{"instanceId valid?"}
    G -->|No| H["Omit header + invalid metric"]
    G -->|Yes| I["Set X-LB-Selected-Instance"]
    I --> J["HTTP connector"]
    F --> J
    H --> J
    J --> K["Backend logs trace using verified identity"]
~~~

**Technical decision:** one transformer for blocking clients, one transformer for WebClient; share the same **InstanceHeaderPolicy.validId** helper so rules never diverge. If Feign is also used in the same project, add a matching Feign transformer.

### Acceptance Scenarios

| Condition | Assertion |
| --- | --- |
| A selected | A receives header `inventory-a` |
| B selected | B receives header `inventory-b` |
| Caller sends spoofed header | Value at backend matches real instance, single value |
| Retry A→B | Requests arriving at A and B carry distinct headers matching each target |
| Payment called | No Inventory header present |
| Registry returns null ID | No NPE; header omitted safely |
| Header violates allowlist | Raw value never forwarded to backend |

**Never ask the transformer to do LoadBalancer's job**: A/B/C are chosen by the supplier/algorithm; the header merely reflects the decision already made. When the real backend needs caller identity verification, keep using **mTLS/JWT** rather than trusting request headers.

## 23. Self-Check Exercises with Solutions

### 23.1. Exercise A: Supplier or Transformer?

Requirement: requests with header **X-SC-LB-Hint: canary** must route to ServiceInstances marked canary, never going to stable when valid canary replicas exist.

**Question:** Should you write a `LoadBalancerClientRequestTransformer` to rewrite the URL to a canary instance after selection?

**Answer:** No. This is a pre-selection **instance filtering/selection** problem. Use **HintBasedServiceInstanceListSupplier** or an equivalent policy; a transformer may add a header recording **which instance was picked**, never reverse the selection decision.

### 23.2. Exercise B: Two Transformers Modifying the Same Header

~~~text
Transformer #1: set X-Environment = prod
Transformer #2: add X-Environment = test
~~~

**Question:** What might the backend observe? How do you fix it?

**Answer:** The header can end up with **multiple values**, depending on builder/HTTP transport. Designate **one owner**, use **set** instead of add when a single value is desired, assign explicit `@Order`, and test the end-to-end result across the full chain.

### 23.3. Exercise C: Retry Switches Instances

~~~text
GET Inventory
Attempt 1: A -> 503
Attempt 2: B -> 200
Transformer holds inventory-a in a singleton field.
~~~

**Question:** What goes wrong?

**Answer:** The second attempt's header may still report **inventory-a** even though the request went to B. Never cache selected instances in a singleton field; use the **ServiceInstance parameter of each invocation**. To verify, count requests at A/B and assert matching headers.

### 23.4. Exercise D: Transformer Returns a Different URL

LoadBalancer selects **inventory-a.internal**, and the transformer reads self-registered metadata and rewrites the URL to **unknown-host.example**.

**Question:** What is the main risk?

**Answer:** Bypassing the vetted candidate set, risk of **SSRF/token leakage**, metric mismatches, TLS hostname/SNI failures, and broken retry policies. Metadata is not authorization. If routing to another host is truly required, update discovery/suppliers or a gateway with clear trust boundaries rather than blindly rewriting post-selection.

### 23.5. Exercise E: Using WebClient but the Transformer Never Runs

~~~java
Mono<String> result = webClient.get()
        .uri("http://inventory-service/ping")
        .retrieve()
        .bodyToMono(String.class);
~~~

**Question:** Why does a unit test see zero transformer invocations?

**Answer:** Usually the Mono **has not been subscribed**, and WebClient may **lack LoadBalancer integration** if the builder is not `@LoadBalanced`. Use StepVerifier/subscription and verify the bean/filter. Never merely call **result.toString()** and assume HTTP executed.

### 23.6. Exercise F: Using a Transformer as Authentication

A backend skips JWT checks if this header is present:

~~~http
X-LB-Selected-Instance: inventory-a
~~~

**Question:** Is this design safe?

**Answer:** No. Headers sent by HTTP clients can be spoofed whenever trust boundaries are unprotected; moreover, an instance ID does not prove caller identity. Backends still require **mTLS/JWT or trustworthy authn/authz mechanisms** alongside network-policy traffic restrictions.

## 24. Checklist Before Using Request Transformers in Production

- [ ] Clearly understand that **transformers run after ServiceInstance selection**, never replacing suppliers/algorithms.
- [ ] Pick the right interface: `LoadBalancerRequestTransformer`, `LoadBalancerClientRequestTransformer`, or `LoadBalancerFeignRequestTransformer`.
- [ ] HTTP client is genuinely integrated with Spring Cloud LoadBalancer and calls by **service ID**.
- [ ] `ReactorLoadBalancerExchangeFilterFunction` is not attached twice to WebClient.
- [ ] Transformer is registered by Spring in the proper ApplicationContext/bean scope.
- [ ] If scoped only to Inventory, an explicit service-ID guard or dedicated client is in place.
- [ ] Zero blocking I/O, registry lookups, token fetches, or recursive HTTP calls inside the transformer.
- [ ] Method, URI, query, path, body, charset, and Content-Type/Length are preserved.
- [ ] For blocking clients, prefer `HttpRequestWrapper` over mutating the original request.
- [ ] For WebClient, prefer `ClientRequest.from(request)` to build a new request.
- [ ] For Feign, copy headers and preserve all fields in `Request.create`.
- [ ] Use **set** when a single header value is needed; avoid duplicate `add` across retries/filters.
- [ ] Assign explicit `@Order` if multiple transformers can affect the same header.
- [ ] New headers use fixed internal names not controlled by callers.
- [ ] Instance IDs/metadata are allowlisted and checked for length and character set.
- [ ] Never treat selected-instance headers as authentication/authorization.
- [ ] Do not overwrite `Authorization`, `Cookie`, `Host`, `Content-Length`, or hop-by-hop headers without reason.
- [ ] Never rewrite to hosts outside ServiceInstance selection/trust policies.
- [ ] TLS SAN/SNI/hostname verification stays valid against the physical URI.
- [ ] Distinguish pre-selection hint/zone/API version from post-selection headers.
- [ ] Retries never read an instance ID cached from an earlier attempt.
- [ ] Never use a mutable singleton counter to track logical retry attempts.
- [ ] Unit tests cover request/header immutability and null/invalid metadata.
- [ ] Integration tests route via service ID against MockWebServer/WireMock.
- [ ] Verify the selected-instance header directly on the real HTTP-receiving server.
- [ ] Test no-instance, 404/503, timeouts, A→B retries, and cancellation (if reactive).
- [ ] Tracing/metrics record the right layer without exposing credentials or high-cardinality tags.
- [ ] Preserve Spring Boot customizers for observability/TLS when creating custom HTTP client builders.
- [ ] Cross-check interfaces and `Request.create` overloads against your BOM/release train.

## 25. Conclusion

**Request transformers are a small yet valuable Spring Cloud LoadBalancer extension point** for enriching requests with **selected ServiceInstance** details. They are especially well suited for attaching technical headers such as selected instance or zone to debug inter-service calls, verify retries/routing, or pass controlled metadata to trusted backends.

Three principles to remember:

1. **Select the target first, transform the request second:** Suppliers/LoadBalancer decide the instance. Transformers must never re-pick hosts.
2. **Each HTTP client has its own interface:** RestTemplate/RestClient use `LoadBalancerRequestTransformer`; WebClient uses `LoadBalancerClientRequestTransformer`; OpenFeign uses `LoadBalancerFeignRequestTransformer`.
3. **Never trade away security and correctness:** Preserve the original request, validate metadata, manage multi-transformer ordering, protect Authorization headers, and verify actual HTTP requests at the backend.

When a system includes retries, timeouts, health checks, and multiple replicas, verify that **each attempt carries the header matching the instance that actually received the request**, rather than checking only one Java method call or an isolated transformer unit test. Sound design increases observability without undermining load-balancing decisions.

## 26. References

- [Spring Cloud LoadBalancer – Transform the load-balanced HTTP request](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#transform-the-load-balanced-http-request): official examples for LoadBalancerRequestTransformer and LoadBalancerClientRequestTransformer, multiple transformers, and ordering.
- [Spring Cloud Commons – LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, discovery, health, hints, zone, request context, retry-aware selection, and metrics.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): configuring `@LoadBalanced` RestTemplate, RestClient.Builder, and WebClient.Builder.
- [Spring Cloud Commons – LoadBalancerRequestTransformer source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerRequestTransformer.java): blocking `transformRequest` signature and `DEFAULT_ORDER`.
- [Spring Cloud Commons – LoadBalancerClientRequestTransformer Javadoc](https://www.javadoc.io/static/org.springframework.cloud/spring-cloud-commons/3.1.9/org/springframework/cloud/client/loadbalancer/reactive/LoadBalancerClientRequestTransformer.html): ClientRequest type, ServiceInstance, and `DEFAULT_ORDER`.
- [Spring Cloud OpenFeign – Transform the load-balanced HTTP request](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html#transform-the-load-balanced-http-request): LoadBalancerFeignRequestTransformer, `Request.create`, header copies, and X-Forwarded support.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@FeignClient` name vs. URL, LoadBalancer integration, RequestInterceptor, and retry.
- [Spring Framework – ClientRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientRequest.html): `ClientRequest.from`, headers, url, method, and build.
- [Spring Framework – HttpRequestWrapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/support/HttpRequestWrapper.html): HttpRequest wrapping mechanism.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): ExchangeFilterFunction, filter ordering, and request processing.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient/RestTemplate and ClientHttpRequestInterceptor.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): HTTP mock server integration testing.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, subscription, and testing Mono/Flux.
- [Spring Security – OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): token acquisition and authorization via dedicated interceptors/filters.
