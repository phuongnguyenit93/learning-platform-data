# Spring Framework Web — Creating RestClient and Configuring Default Base URL, Headers, and Cookies

## 1. Objectives

`RestClient` is Spring Framework's **synchronous** HTTP client using a fluent API. Introduced in Spring Framework 6.1 and expanded in 6.2, RestClient enables Spring MVC services, scheduled jobs, or batch applications to call another REST API, decode JSON, and manage HTTP statuses without manually opening sockets.

This lesson focuses on **a reusable RestClient** with shared configuration:

- Creating a client using `RestClient.create()` or `RestClient.builder()`.
- `baseUrl(String/URI)` to avoid repeating the host/prefix URL on every request.
- `defaultUriVariables(...)` and its relationship with `uriBuilderFactory(...)`.
- `defaultHeader(...)` and `defaultHeaders(...)` for default headers.
- `defaultCookie(...)` and `defaultCookies(...)` for default cookies **starting in Spring Framework 6.2**.
- Overriding headers/cookies at the **single-request** level.
- `defaultRequest(...)` when dynamic per-request values need to be set.
- How Spring Boot 3.5 auto-configures and injects `RestClient.Builder`, distinguishing the builder from the built client.
- Testing with `MockRestServiceServer.bindTo(builder)` and JUnit 5 without needing an external Internet API.
- Avoiding sensitive default cookies/tokens on a singleton shared across multiple users.
- Advanced configuration for timeouts, request factories, error handling, pooling, logging, and authorization.

**Context:** the parent module is **synchronous HTTP clients**. Do not confuse `RestClient` with `WebClient` (reactive) or WebFlux server APIs. `retrieve().body(Class)` blocks the executing thread until a response or error is received.

## 2. Comparing Spring's Three HTTP Clients

| Client | Model | Primary Usage |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent | Blocking/MVC applications, outbound REST |
| `RestTemplate` | Synchronous, template methods | Legacy applications, migration |
| `WebClient` | Non-blocking, `Mono`/`Flux` | WebFlux/reactive pipelines |

A RestClient can be created as:

~~~java
RestClient client = RestClient.create();
String body = client.get()
        .uri("https://example.org/api/health")
        .retrieve()
        .body(String.class);
~~~

This is a fragment: the endpoint is illustrative only. Once `build()` is called, RestClient can be safely reused across multiple threads according to Spring documentation. **A mutable builder should not be modified concurrently at runtime**: configure it once at bootstrap and inject the built client.

### 2.1. Why Not Create a New RestClient Per Request?

Recreating RestClient and the underlying HTTP request factory/connection pool each time can incur overhead and make connection management and observability harder. In an application, declare one `@Bean RestClient` per upstream. Individual request specs created via `client.get()`/`post()` on the shared client hold values specific to each HTTP call.

### 2.2. When Must WebClient Be Used?

If code is executing on a Reactor Netty event loop, an outbound RestClient call can block the event loop. In a WebFlux/reactive pipeline, prefer `WebClient`; if you must call a blocking legacy API, offload it and bound concurrency—never call `block()` on the event loop.

## 3. Ways to Initialize

### 3.1. Without Defaults

~~~java
RestClient client = RestClient.create();
~~~

Requests typically must use absolute URLs:

~~~java
String body = client.get()
        .uri("https://service.example.test/info")
        .retrieve()
        .body(String.class);
~~~

This URL is not a real service.

### 3.2. Using the Builder

~~~java
RestClient catalog = RestClient.builder()
        .baseUrl("https://catalog.example.test/api/v1")
        .defaultHeader("X-Client-Name", "inventory-service")
        .defaultCookie("locale", "vi")
        .build();
~~~

Calling:

~~~java
Product product = catalog.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
~~~

`Product` is an application-defined DTO. For example, `record Product(long id, String name) {}` can deserialize a JSON body like `{"id":42,"name":"Tea"}` when Jackson is present.

### 3.3. Creating from RestTemplate

Spring provides the factory method `RestClient.create(RestTemplate)` to support migration:

~~~java
RestTemplate template = new RestTemplate();
RestClient client = RestClient.create(template);
~~~

When migrating an existing application, verify the request factory, interceptors, status handlers, serializers, and actual timeouts. Having the code compile is not enough; default policies can differ.

## 4. baseUrl and URI Resolution

### 4.1. Single Configuration Source for Host and Prefix

~~~java
RestClient api = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .build();

Product p = api.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
~~~

Intended final URL:

~~~text
https://catalog.example.test/v1/products/42
~~~

Verify with MockRestServiceServer to avoid path mistakes. Do not put `/v1` in both baseUrl and `.uri("/v1/products/{id}")` because the prefix will be duplicated.

### 4.2. Absolute URIs Bypass baseUrl

Per Spring Framework 6.2 Javadoc, when a request uses an absolute URL, the configured baseUrl is ignored:

~~~java
api.get()
        .uri("https://other.example.test/products/42")
        .retrieve()
        .body(String.class);
~~~

This is dangerous if the upstream is chosen from user input and RestClient has a global Authorization/Cookie. Prevent SSRF/credential leakage with an allowlist of trusted hosts/schemes/ports, redirect policies, and separate clients per trust boundary.

### 4.3. URI Templates Are Better Than String Concatenation

Prefer:

~~~java
api.get()
        .uri("/products/{id}", userVisibleId)
        .retrieve()
        .body(String.class);
~~~

Do not concatenate input manually:

~~~java
api.get().uri("/products/" + rawInput);
~~~

An ID or search term containing spaces, `?`, `/`, or `#` can alter the meaning of the URI. Use URI templates and query builders so encoding is handled intentionally.

Query example:

~~~java
api.get()
        .uri(builder -> builder
                .path("/products")
                .queryParam("q", searchTerm)
                .queryParam("page", 1)
                .build())
        .retrieve()
        .body(String.class);
~~~

This fragment requires `searchTerm`. When passing a `URI` directly, encoding behavior differs from a String template; read the Javadoc and avoid double encoding.

### 4.4. Default URI Variables

If many API paths need a fixed variable, such as region:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultUriVariables(Map.of("region", "vn"))
        .build();

String body = client.get()
        .uri("/regions/{region}/products/{id}",
                Map.of("id", 42))
        .retrieve()
        .body(String.class);
~~~

Default variables are a shortcut for `DefaultUriBuilderFactory`; do not store per-user tenant IDs in globals on a shared client.

### 4.5. uriBuilderFactory and Precedence

`uriBuilderFactory(UriBuilderFactory)` replaces the default URI building mechanism. Per Spring 6.2 Javadoc, providing a custom factory **overrides the effect of the baseUrl/defaultUriVariables shortcuts**. If a custom factory is set, a baseUrl placed before/after it may not take effect as expected. Only use a custom factory when you genuinely have specialized encoding/URI template requirements.

## 5. defaultHeader and defaultHeaders

### 5.1. Single Default Header

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Client-Name", "inventory-service")
        .build();
~~~

`RestClient.Builder.defaultHeader(String, String...)` adds the default header **only if the request does not already have a header with the same name**. Therefore, a per-call header can replace the default:

~~~java
client.get()
        .uri("https://catalog.example.test/products/7")
        .header("X-Client-Name", "special-job")
        .retrieve()
        .body(String.class);
~~~

When the request already has X-Client-Name, defaultHeader does not automatically add inventory-service. If a header was previously added multiple times, use `headers(h -> h.set(...))` to replace rather than append.

### 5.2. defaultHeaders for Group Manipulation

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Client-Name", "inventory-service")
        .defaultHeaders(headers -> {
            headers.set("X-API-Version", "2026-10");
            headers.setAccept(
                    List.of(MediaType.APPLICATION_JSON));
            headers.remove("X-Legacy-Feature");
        })
        .build();
~~~

`defaultHeaders(Consumer<HttpHeaders>)` allows:

- `add(name,value)`: appends a value to the list.
- `set(name,value)`: replaces the list with a single value.
- `remove(name)`: removes a default.
- `setAccept(List.of(...))`: configures a properly typed Accept header.

**Caution:** `Authorization` should usually only have one scheme/token chosen for the exact audience. Do not turn `defaultHeader("Authorization",...)` into storage for a single user's token on a singleton RestClient.

### 5.3. Accept and Content-Type

- `Accept` indicates the response representation you want to receive, such as JSON.
- `Content-Type` describes the media type of the **request body**, so do not force application/json as a default for every bodyless GET.
- `User-Agent` and `X-Client-Name` are useful for the upstream to identify the calling service when policy agrees.
- `X-API-Version` is used when the upstream has a header-based versioning contract.

If an API call POSTs JSON, configure it per-call:

~~~java
client.post()
        .uri("/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateProductRequest("Tea"))
        .retrieve()
        .toBodilessEntity();
~~~

This is a fragment; CreateProductRequest must be declared. When the client has a base URL, this path is appended appropriately. Prefer media type convenience methods rather than writing raw Content-Type strings manually.

### 5.4. A Common Request ID Mistake

Do not generate one request ID and attach it globally:

~~~java
RestClient client = RestClient.builder()
        .defaultHeader("X-Request-ID",
                UUID.randomUUID().toString())
        .build();
~~~

All requests from the client would share the same ID because the value is generated only at build time. If each call needs a fresh ID, use `defaultRequest`/an interceptor or standard tracing propagation.

## 6. defaultCookie and defaultCookies — Spring Framework 6.2

### 6.1. A Genuine New API

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultCookie("locale", "vi")
        .build();
~~~

`RestClient.Builder.defaultCookie(String, String...)` was added **in Spring Framework 6.2**. It supplies a default cookie to a request **if the request does not already have a cookie with the same name**. If your IDE says the method does not exist, check the effective `spring-web` dependency version rather than assuming RestClient does not support cookies.

### 6.2. defaultCookies Using MultiValueMap

~~~java
RestClient client = RestClient.builder()
        .defaultCookie("locale", "vi")
        .defaultCookies(cookies -> {
            cookies.set("theme", "light");
            cookies.remove("legacy");
        })
        .build();
~~~

`defaultCookies(Consumer<MultiValueMap<String,String>>)` exposes the defaults map to add, replace, or remove cookies. Using `cookies.set` replaces the value list for that cookie key.

To change an already declared default locale:

~~~java
RestClient client = RestClient.builder()
        .defaultCookie("locale", "en")
        .defaultCookies(cookies ->
                cookies.set("locale", "vi"))
        .build();
~~~

After building, the default locale is vi.

### 6.3. Per-Call Cookies Can Override Defaults

~~~java
client.get()
        .uri("/products/{id}", 42)
        .cookie("locale", "en")
        .retrieve()
        .body(String.class);
~~~

Spring 6.2 `RequestHeadersSpec.cookie(name,value)` and `cookies(Consumer<MultiValueMap<...>>)` manipulate request cookies. Because defaultCookie is inserted only when the name does not yet exist, a request cookie can replace the default of the same name.

Explicit replacement example:

~~~java
client.get()
        .uri("/products/{id}", 42)
        .cookies(cookies -> cookies.set("locale", "en"))
        .retrieve()
        .body(String.class);
~~~

When multiple layers add Cookie headers, inspect the actual request with a mock to detect duplicate values. Do not manually add a raw `Cookie` header when already using the cookie API, unless there is a tested compatibility reason.

### 6.4. Request Cookie vs Set-Cookie

- Outbound clients send **Cookie: locale=vi; theme=light**.
- Servers return **Set-Cookie** to instruct a user agent to store a cookie with Domain/Path/Expires/Secure/HttpOnly/SameSite.

RestClient.Builder.defaultCookie only sets **default request cookies**; it does **not act as a browser-like cookie jar** that stores/selects server-returned cookies by session/domain/expiry. For stateful cookie storage, configure an appropriate HTTP client transport and verify policies.

### 6.5. Cookie Security

Do not put per-user browser sessions, refresh tokens, CSRF tokens, or Authorization cookies on a global singleton RestClient. Users A and B could accidentally share credentials. Do not forward raw inbound Cookie headers to another host. If delegated access is needed, design per-request auth, OAuth/token exchange, host allowlists, TLS, and secret redaction.

DefaultCookie is better suited for non-sensitive application-level locale/theme and a few shareable service-specific metadata values.

## 7. defaultRequest and Dynamic Values

`defaultRequest(Consumer<RestClient.RequestHeadersSpec<?>>)` customizes every built request, for instance generating a correlation ID when the request does not already have one:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test/v1")
        .defaultRequest(spec -> spec.headers(headers -> {
            if (!headers.containsKey("X-Correlation-ID")) {
                headers.set("X-Correlation-ID",
                        UUID.randomUUID().toString());
            }
        }))
        .build();
~~~

This is a fragment requiring UUID import. Unlike `defaultHeader`, this can generate a UUID **per request**, not once at bootstrap. If the app uses distributed tracing, propagate reliable trace IDs from the observation context; avoid generating independent IDs at every hop that break the trace.

| API | Where Applied |
| --- | --- |
| `defaultHeader` | Stable header, when request does not already have it |
| `defaultHeaders` | Edit the entire default header map when configuring builder |
| `defaultCookie` | Stable cookie, when request does not already have the same name |
| `defaultCookies` | Edit the default cookie map |
| `defaultRequest` | Callback executed for each request spec |
| `get().header/cookie` | Single request only |
| `requestInterceptor` | Intercepts outbound execution, logging/tracing/policy |

With dynamic Authorization, ensure the identity/token is retrieved per request from a trusted context rather than storing a mutable `lastToken` on a singleton. Separate clients by trust boundary and avoid sending tokens if a caller can supply an absolute URL to another host.

## 8. Spring Boot 3.5 and RestClient.Builder Injection

Spring Boot auto-configuration creates a `RestClient.Builder` bean with **prototype scope**, meaning each injection point receives its own configured builder. Boot can apply HTTP converters, observation/tracing, HTTP client factories, and `RestClientCustomizer`.

In a Boot application:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", "inventory-service")
                .defaultCookie("locale", "vi")
                .build();
    }
}
~~~

Use the Boot-injected builder instead of calling `RestClient.builder()` manually in multiple places if you need to retain application customizers and observation policies.

### 8.1. RestClientCustomizer

Spring Boot 3.5 provides a `RestClientCustomizer` callback to configure RestClient builders:

~~~java
@Bean
RestClientCustomizer platformCustomizer() {
    return builder -> builder.defaultHeader(
            "X-Platform", "learning-platform");
}
~~~

This is a fragment importing `org.springframework.boot.web.client.RestClientCustomizer`. A global customizer should only set policy headers genuinely **shared across all upstreams**. Do not set a base URL or catalog cookie on every client, since billing/auth destinations have different audiences.

### 8.2. RestClientBuilderConfigurer

Spring Boot also provides `RestClientBuilderConfigurer` to apply Boot defaults onto a manually created builder. It is useful for extension libraries or custom builder factories. Typical applications just inject Boot's builder.

### 8.3. One Client Per Upstream

If both catalog and billing are needed:

~~~java
@Bean
RestClient catalogClient(RestClient.Builder builder) {
    return builder.baseUrl("https://catalog.example.test").build();
}

@Bean
RestClient billingClient(RestClient.Builder builder) {
    return builder.baseUrl("https://billing.example.test").build();
}
~~~

Across two beans, use explicit `@Qualifier` in consumers when multiple RestClient beans exist. The prototype builder prevents sharing the same mutable builder between two upstreams.

### 8.4. Properties and Secrets

~~~properties
catalog.base-url=https://catalog.example.test/v1
catalog.client-name=inventory-service
catalog.locale=vi
~~~

Configure baseURL from environment/config management. Tokens/passwords belong in a secret manager or protected environment variables, never hardcoded in Git/README. Validate scheme=https and host allowlists before the app uses dynamic endpoint settings.

## 9. Standalone Maven Project (Java 17 + Spring Boot 3.5.0)

### 9.1. Structure

~~~text
restclient-defaults-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RestClientDefaultsApplication.java
    │   └── resources/application.properties
    └── test/java/demo/CatalogGatewayTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>restclient-defaults-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Use `spring-boot-starter-web` because this is a **synchronous** HTTP client in a Boot MVC app; it brings in `spring-web`, Jackson, and core dependencies. The demo does not need the WebFlux starter.

### 9.3. application.properties

~~~properties
catalog.base-url=https://catalog.example.test/v1
catalog.client-name=inventory-service
catalog.locale=vi
~~~

The URL `catalog.example.test` is example-only. The app does not call the URL at startup; unit tests use mock HTTP responses so no network is used.

### 9.4. RestClientDefaultsApplication.java

Save the **entire** Java code below into `src/main/java/demo/RestClientDefaultsApplication.java`. Only one public top-level class, with the remaining classes/records package-private, Java 17 compatible.

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class RestClientDefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                RestClientDefaultsApplication.class, args);
    }
}

record Product(long id, String name) {
}

@Configuration(proxyBeanMethods = false)
class CatalogConfig {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl,
            @Value("${catalog.client-name}") String clientName,
            @Value("${catalog.locale}") String locale) {
        return create(builder, baseUrl, clientName, locale);
    }

    static RestClient create(RestClient.Builder builder,
                             String baseUrl,
                             String clientName,
                             String locale) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", clientName)
                .defaultHeaders(headers -> {
                    headers.set("X-API-Version", "2026-10");
                    headers.setAccept(
                            List.of(MediaType.APPLICATION_JSON));
                })
                .defaultCookie("locale", locale)
                .defaultCookies(cookies ->
                        cookies.set("theme", "light"))
                .build();
    }
}

@Service
class CatalogGateway {
    private final RestClient client;

    CatalogGateway(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    Product getProduct(long id) {
        Product response = client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
        return Objects.requireNonNull(
                response, "Empty product response");
    }

    Product getProductWithOverrides(long id) {
        Product response = client.get()
                .uri("/products/{id}", id)
                .header("X-Client-Name", "special-job")
                .cookie("locale", "en")
                .retrieve()
                .body(Product.class);
        return Objects.requireNonNull(
                response, "Empty product response");
    }
}
~~~

**Explanation:**

- Spring Boot manages the RestClient.Builder bean; the code builds one reusable RestClient.
- `CatalogConfig.create(...)` allows unit tests to pass a mock builder so no real API is called.
- `baseUrl` combines the upstream host and version path.
- Default headers include X-Client-Name, X-API-Version, and Accept JSON.
- Default cookies include `locale=vi` and `theme=light`.
- The override method replaces X-Client-Name and locale for that request only.
- `Objects.requireNonNull` illustrates handling an empty response body; production should map to a typed domain exception.
- `Product` is an immutable record suited for JSON decoding by Spring/Jackson.
- No per-user tokens or global session cookies are used.
- The app declares no inbound controller; it runs to demonstrate DI and the HTTP client bean. Tests are the way to run the full demo without needing a catalog server.

### 9.5. CatalogGatewayTest.java

Save `src/test/java/demo/CatalogGatewayTest.java`:

~~~java
package demo;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogGatewayTest {
    private MockRestServiceServer server;
    private CatalogGateway gateway;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        // Bind before RestClient.build().
        server = MockRestServiceServer.bindTo(builder).build();
        RestClient rest = CatalogConfig.create(
                builder,
                "https://catalog.example.test/v1",
                "inventory-service",
                "vi");
        gateway = new CatalogGateway(rest);
    }

    @Test
    void baseUrlHeadersAndCookiesAreApplied() {
        server.expect(requestTo(URI.create(
                        "https://catalog.example.test/v1/products/7")))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        "X-Client-Name", "inventory-service"))
                .andExpect(header(
                        "X-API-Version", "2026-10"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andExpect(request -> {
                    String cookie = request.getHeaders().getFirst(
                            HttpHeaders.COOKIE);
                    assertTrue(cookie != null
                            && cookie.contains("locale=vi"));
                    assertTrue(cookie != null
                            && cookie.contains("theme=light"));
                })
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Coffee\"}",
                        MediaType.APPLICATION_JSON));

        Product p = gateway.getProduct(7);
        assertEquals(7L, p.id());
        assertEquals("Coffee", p.name());
        server.verify();
    }

    @Test
    void requestHeaderAndCookieOverrideDefaults() {
        server.expect(requestTo(
                        "https://catalog.example.test/v1/products/8"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("X-Client-Name", "special-job"))
                .andExpect(request -> {
                    String cookie = request.getHeaders().getFirst(
                            HttpHeaders.COOKIE);
                    assertTrue(cookie != null
                            && cookie.contains("locale=en"));
                    assertFalse(cookie != null
                            && cookie.contains("locale=vi"));
                    assertTrue(cookie != null
                            && cookie.contains("theme=light"));
                })
                .andRespond(withSuccess(
                        "{\"id\":8,\"name\":\"Tea\"}",
                        MediaType.APPLICATION_JSON));

        Product p = gateway.getProductWithOverrides(8);
        assertEquals(8L, p.id());
        server.verify();
    }

    @Test
    void http404ThrowsByDefault() {
        server.expect(requestTo(
                        "https://catalog.example.test/v1/products/999"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.NotFound.class,
                () -> gateway.getProduct(999));
        server.verify();
    }
}
~~~

### 9.6. Running Tests

~~~bash
mvn test
~~~

Tests use `MockRestServiceServer.bindTo(RestClient.Builder)` to replace the outgoing HTTP request factory **before building RestClient**, avoiding real DNS/network calls. They verify:

1. The URI includes the exact host + `/v1/products/7`.
2. Default client header and API-version.
3. Accept JSON.
4. Cookies are sent via the HTTP Cookie header.
5. A single request can override a header/cookie of the same name.
6. JSON decodes into a Java record properly.
7. `retrieve()` throws a typed HttpClientErrorException on a 404 response.

Cookie assertions use `contains` so they do not depend on cookie pair ordering. If config changes or version upgrades cause tests to fail, inspect the actual request and the corresponding version's Javadoc before relaxing the test.

Running the app standalone:

~~~bash
mvn spring-boot:run
~~~

The application starts the Spring Boot MVC runtime and creates the CatalogGateway bean, **making no outbound HTTP calls** until you invoke the gateway from another service/controller. To call a real upstream, configure a safe URL, TLS/timeouts/auth, and the real contract. Do not put sensitive tokens in README or Git.

## 10. Advanced Customization for Production

### 10.1. Timeouts

`baseUrl`, header defaults, and cookie defaults **do not configure timeouts**. The underlying HTTP request factory determines connect/read/response timeouts, which can differ across JDK HttpClient, Apache HttpComponents, and other clients.

Fragment example with SimpleClientHttpRequestFactory:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(Duration.ofSeconds(2));
factory.setReadTimeout(Duration.ofSeconds(5));

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://catalog.example.test/v1")
        .build();
~~~

Verify against the Javadoc for your exact Spring version and transport; Boot provides request-factory configuration to preserve observability/SSL/pooling settings.

### 10.2. Error Handling

`retrieve()` throws exceptions by default for HTTP 4xx/5xx, such as `HttpClientErrorException.NotFound`. You can use per-request `onStatus` or `defaultStatusHandler` on the builder.

~~~java
RestClient client = RestClient.builder()
        .defaultStatusHandler(
                status -> status.value() == 429,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Upstream rate-limited");
                })
        .build();
~~~

This is a fragment. Production should use typed domain exceptions and never return raw upstream bodies that may contain SQL/secrets/tokens. When using lower-level `exchange(...)`, status/body handling has a different contract than `retrieve()`; read the Javadoc before switching.

### 10.3. Interceptors

~~~java
ClientHttpRequestInterceptor interceptor =
        (request, body, execution) -> {
            request.getHeaders().set(
                    "X-Platform", "spring-course");
            return execution.execute(request, body);
        };

RestClient client = RestClient.builder()
        .requestInterceptor(interceptor)
        .build();
~~~

This is a fragment requiring imports. Interceptors run close to I/O time and can modify the request/response. Do not log Authorization, Cookie, Set-Cookie, or raw request bodies. If Spring Boot already configures Micrometer tracing, avoid manually creating duplicate spans.

### 10.4. Pooling and Thread Usage

RestClient itself is an API abstraction; pooling/keepalive belongs to the underlying HTTP client. Reuse client beans, configure appropriate max connections/pending acquire/idle eviction/response timeouts, and measure latency. Synchronous RestClient holds the caller thread for the entire HTTP call: calling 100 remote endpoints in parallel with 100 threads still incurs real resource costs.

### 10.5. Retries and Idempotency

Do not retry every `POST /payments` without an idempotency key/deduplication. For idempotent GETs and transient failures, use a resilience library/circuit breaker with bounded retries, backoff, jitter, overall deadlines, and metrics. Cookies/Authorization for one upstream must not be sent to redirect destinations outside the allowlist.

## 11. Safety of Default Headers/Cookies

### 11.1. Mistake of Sharing User Sessions

Wrong in a multi-user service:

~~~java
@Bean
RestClient client() {
    return RestClient.builder()
            .defaultCookie("session", "user-a-session")
            .build();
}
~~~

Every request through the singleton could carry user A's credentials. Do not forward raw inbound Cookie headers to a different downstream host. Separate service credentials and user-delegated tokens; use token exchange/per-request authorization rather than mutable user sessions at bean scope.

### 11.2. Confusing Request Cookies with a Browser Cookie Store

`defaultCookie("locale","vi")` adds a Cookie request header for matching calls. It does not accept Set-Cookie, store expires/domain/path/SameSite, and pick cookies per host like a browser; real session cookie management requires a specific request factory/HTTP client cookie store. Do not assume auto-login.

### 11.3. SSRF and Absolute URIs

A malicious caller could supply `http://169.254.169.254/...` or a private-network URL if you allow arbitrary absolute destinations. If RestClient has a default Authorization/Cookie, the risk increases. Restrict outgoing hosts, disable/block redirects per policy, validate DNS/IP before connecting per architecture, and never mix trusted and untrusted destinations.

### 11.4. Redaction/Observability

Logs should include method, route template, upstream service name, HTTP status, and latency. Do not log raw Authorization/Cookie/Set-Cookie, do not put raw query strings containing tokens into trace tags, and do not use requestId/userId as high-cardinality metric labels. Tracing context is a more reliable correlation source than attaching IDs manually at every layer.

## 12. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `defaultCookie` fails to compile | Spring Framework < 6.2 | Check effective `spring-web` version |
| HTTP URL ignores baseUrl | Request uses an absolute URL | Verify final URI with a mock |
| Path `/v1/v1` | Duplicate prefix | Choose a single owner for the path prefix |
| defaultUriVariables has no effect | Custom `uriBuilderFactory` overrides it | Check URI builder setup |
| Default header ignored | Request already has a header with that name | Check per-call specs |
| Unexpected multiple header values | Used add instead of set | Use headers(h -> h.set(...)) |
| Default locale cookie missing | Request sets a different locale cookie | Expected behavior of defaultCookie |
| Duplicate Cookie | Added both raw Cookie header and cookie API | Use one source only |
| Cookie present but upstream still 401 | Invalid session token or wrong audience | Separate auth protocol |
| User A session leaks to user B | Sensitive global cookie | Switch to per-request auth |
| Boot observability lost | Raw builder instead of Boot-injected builder | Inject RestClient.Builder |
| 404 throws exception | Retrieve defaults | Handle with typed error |
| Mock test still calls the Internet | Bound mock to wrong/already-built builder | bindTo(builder) before build |
| Cookie test fails due to field order | Different serialization/ordering | Assert content semantics |
| Requests hang | No timeout set on underlying HTTP client | Configure connect/read timeouts |
| Poor throughput | Many blocking calls/no pooling | Reuse client, optimize threads |
| Credentials appear in logs | Logging raw headers | Redact sensitive headers |

## 13. Exercises

**Exercise 1.** Build a RestClient with baseUrl, default X-Client-Name, and locale cookie. GET /products/{id} and decode JSON into a record.

**Exercise 2.** Use defaultHeaders to set Accept JSON, X-API-Version, and remove X-Legacy. Compare add/set/remove.

**Exercise 3.** Use defaultCookies to set theme=light, replace locale=en with vi, and remove an unused cookie.

**Exercise 4.** Override X-Client-Name and locale for a single GET only, proving subsequent requests still receive the defaults.

**Exercise 5.** Use a URI template path variable and URI query builder; verify special characters are encoded properly.

**Exercise 6.** Verify that an absolute URI bypasses baseUrl. Analyze how to block disallowed hosts.

**Exercise 7.** Use defaultRequest to generate a per-request correlation ID instead of a single UUID created at build time.

**Exercise 8.** Declare two RestClient beans using Boot prototype builder injection, one for catalog and one for billing, without mixing cookies.

**Exercise 9.** Write MockRestServiceServer tests verifying URL, method, Accept, headers, cookies, JSON decoding, and 404 exception.

**Exercise 10.** Reproduce the missing defaultCookie on Spring 6.1; upgrade Framework to 6.2 and analyze the new API.

**Exercise 11.** Configure HTTP timeouts, test a slow response, and distinguish a network timeout from HTTP 504.

**Exercise 12.** Design safe per-user delegated auth instead of a singleton defaultCookie session.

**Exercise 13.** Write an interceptor that logs only status/latency; ensure Cookie/Authorization are redacted.

**Exercise 14.** Compare RestClient and WebClient when used inside a WebFlux event-loop application.

**Exercise 15.** Add bounded retries for idempotent GETs, and explain why payment POSTs differ.

## 14. Checklist

- [ ] Use Spring Framework 6.2+ when calling `RestClient.Builder.defaultCookie(s)`.
- [ ] Base URL comes from trusted config and is validated.
- [ ] Header defaults are application-wide settings only, carrying no per-user credentials.
- [ ] Cookie defaults are safe for all calls through the shared RestClient.
- [ ] URL does not accept arbitrary user-controlled absolute destinations.
- [ ] Path/version prefixes are not duplicated.
- [ ] URI path/query variables use builders/templates with proper encoding.
- [ ] Per-call overrides are actually tested.
- [ ] Use Boot-injected RestClient.Builder if Boot customizations are needed.
- [ ] Never mutate builder/client internals concurrently while the app is running.
- [ ] Connect/read timeouts, TLS, and connection pool metrics are configured.
- [ ] 4xx/5xx are mapped safely when needed.
- [ ] Retries are used only for transient/idempotent operations.
- [ ] Cookie/Set-Cookie/Authorization/raw PII are not logged.
- [ ] MockRestServiceServer is bound before RestClient.build().
- [ ] Synchronous RestClient is not called directly on the WebFlux event loop.

## 15. Key Takeaways

- **RestClient is synchronous**: a request blocks the caller thread while waiting for HTTP I/O.
- `RestClient.Builder.baseUrl` sets the base URL for relative URIs; an absolute request URI can override the base.
- `defaultHeader/defaultCookie` only apply when the request does not already have a header/cookie of the same name.
- `defaultHeaders/defaultCookies` allow editing the defaults map.
- **Spring Framework 6.2 added RestClient.Builder.defaultCookie/defaultCookies**; check the BOM version.
- `defaultRequest` is suited for dynamic per-request custom metadata.
- Spring Boot 3.5 provides an auto-configured prototype `RestClient.Builder`; inject the builder to keep customizers/observations.
- A shared RestClient must not hold per-user auth/cookie secrets.
- Test outbound behavior with `MockRestServiceServer.bindTo(builder)` before `build()`.
- Base URL and defaults do not replace timeouts, TLS, authentication, or retry policies.

## 16. Official Documentation

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html).
- [RestClient.Builder 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.Builder.html).
- [RestClient.RequestHeadersSpec 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html).
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html).
- [Spring Boot 3.5 RestClientAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html).
- [Spring Boot 3.5 RestClientCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html).
- [MockRestServiceServer 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 6265 — HTTP Cookies](https://www.rfc-editor.org/rfc/rfc6265).
