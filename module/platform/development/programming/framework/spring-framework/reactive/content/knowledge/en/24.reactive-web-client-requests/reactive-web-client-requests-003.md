# Base URL, UriBuilder, Path, and Query Parameters When Sending WebClient Requests

## 1. Objectives and Request Components

`WebClient` is Spring WebFlux's reactive HTTP client. An HTTP request typically requires the following components:

- **Base URL**: the root address of the API.
- **Path**: the path to the resource.
- **Path variables**: dynamic data in a path segment.
- **Query parameters**: filters, pagination, sorting, or options.
- **Headers**: metadata such as Accept, Authorization, correlation ID.
- **Body**: payload for POST, PUT, or PATCH.

Example:

~~~text
Base URL: https://catalog.example.test
Path:     /v1/products/{category}
Query:    ?q={term}&page={page}&sort={sort}
~~~

With category as `books`, term as `Spring WebFlux`, and page as 2, the request URI takes the form:

~~~text
https://catalog.example.test/v1/products/books?q=Spring%20WebFlux&page=2&sort=newest
~~~

Separating the template from dynamic data makes code easier to read and test, and avoids errors when input contains spaces or reserved characters.

**Principle:** keep the URI structure in the template, pass dynamic data via URI variables, and let `UriBuilder`/`UriBuilderFactory` encode them. Do not concatenate URLs with strings from untrusted input.

## 2. Creating a WebClient and Configuring the Base URL

### 2.1. Three Ways to Initialize

Simple client without a base URL:

~~~java
WebClient client = WebClient.create();
~~~

Client with a base URL:

~~~java
WebClient client =
        WebClient.create("https://catalog.example.test");
~~~

Client via builder:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
~~~

`WebClient.builder()` is appropriate when configuring multiple components:

- `baseUrl` or `uriBuilderFactory`.
- `defaultUriVariables`.
- `defaultHeader`, `defaultHeaders`, `defaultCookie`.
- `filter` for requests/responses.
- `clientConnector` to choose the HTTP client.
- `codecs` to configure message readers/writers.

After `build()`, `WebClient` is immutable and can be reused across requests. When a variant is needed, use `client.mutate()` to create a new builder.

### 2.2. Base URL Applies Only to Relative URIs

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Mono<String> relative = client.get()
        .uri("/v1/health")
        .retrieve()
        .bodyToMono(String.class);

Mono<String> absolute = client.get()
        .uri("https://status.example.test/health")
        .retrieve()
        .bodyToMono(String.class);
~~~

The first request uses the catalog host. The second request calls the status host because the URI is absolute.

| Value passed to uri(...) | Result |
| --- | --- |
| `/v1/products` | Uses base URL |
| `v1/products` | Uses base URL via URI factory |
| `https://other.example.test/products` | Absolute URI; base URL is ignored |
| Complete `URI` | Uses the provided URI |

Base URL is a routing configuration, not a host-restriction mechanism. If user input can provide an absolute URL, that URL can bypass the base URL. For server-side fetches or webhooks, validate scheme, host, port, DNS, and redirects against an allowlist to prevent SSRF.

### 2.3. baseUrl and uriBuilderFactory

`baseUrl(...)` is a shortcut to configure `DefaultUriBuilderFactory` with a base URL. You can configure the factory directly:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory(
                "https://catalog.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient client = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

Use `baseUrl` and `uriBuilderFactory` as alternative ways to configure. When a factory is supplied directly, that factory takes precedence over the baseUrl shortcut.

### 2.4. Base URL with a Path Prefix

An API may place endpoints under a prefix:

~~~text
https://api.example.test/platform/catalog
~~~

You can configure the base URL with the prefix and use relative URIs for child endpoints. When the base URL has a path, test the final URI to confirm that the prefix, slashes, and path template combine as intended. Use a consistent convention for leading/trailing slashes throughout the client.

If endpoints call multiple different hosts or prefixes, consider creating separate WebClients for each API rather than changing hosts dynamically on a shared client.

## 3. WebClient's uri(...) Overloads

| Invocation | When to use |
| --- | --- |
| `uri(String template, Object... variables)` | Short template, few variables |
| `uri(String template, Map<String, ?> variables)` | Many variables, needing mapping by name |
| `uri(URI uri)` | Already built a complete URI |
| `uri(Function<UriBuilder, URI>)` | Need to add path/query or dynamic logic |
| `uri(String template, Function<UriBuilder, URI>)` | Start from a template then complete with builder |

### 3.1. Positional Variables

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", 42L)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Arguments are substituted in placeholder order. When a template is long, it is easy to pass values in the wrong order.

### 3.2. Named Variables Using Map

~~~java
Map<String, Object> variables = Map.of(
        "category", "books",
        "id", 42L);

Mono<Product> product = client.get()
        .uri("/v1/categories/{category}/products/{id}",
                variables)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Keys in the Map must match placeholders exactly. Named variables are usually easier to review when a template has many variables.

### 3.3. Pre-Built URI

~~~java
URI uri = URI.create(
        "https://catalog.example.test/v1/products/42");

Mono<Product> product = client.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(Product.class);
~~~

When passing a complete `URI`, the caller is responsible for parsing, encoding, and validation. WebClient does not expand templates in that URI object. Do not build a URI from input via string concatenation and expect the client to fix encoding automatically.

### 3.4. UriBuilder Function

This is the flexible approach when path and query have multiple components:

~~~java
Mono<ProductPage> products = client.get()
        .uri(builder -> builder
                .path("/v1/categories/{category}/products")
                .queryParam("q", "{term}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "category", category,
                        "term", searchTerm,
                        "page", page,
                        "size", size)))
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

The builder is created from WebClient's `UriBuilderFactory`, so the configured base URL and encoding mode are applied.

## 4. path and pathSegment

### 4.1. path(String)

`path(String)` appends a path template segment:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/v1/products/{productId}")
        .build(42);
~~~

Result:

~~~text
https://api.example.test/v1/products/42
~~~

Multiple segments can be chained:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .path("/v1")
        .path("/categories/{category}")
        .path("/products/{productId}")
        .build(Map.of(
                "category", "books",
                "productId", 42));
~~~

`path` appends path templates. When chaining multiple calls, standardize leading/trailing slash conventions to avoid missing slashes or unintended double slashes.

### 4.2. Do Not Concatenate Input Directly into Path

Avoid:

~~~java
String path = "/v1/products/" + category;
Mono<Product> result = client.get()
        .uri(path)
        .retrieve()
        .bodyToMono(Product.class);
~~~

If category is `books/../../admin`, slashes and dot segments can alter the path. Values with `?` or `#` can also affect the query or fragment.

Keep template and value separate:

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{category}", category)
        .retrieve()
        .bodyToMono(Product.class);
~~~

### 4.3. pathSegment(String...)

`pathSegment` explicitly states that each argument is a single segment:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("v1", "products", "{category}", "{id}")
        .encode()
        .buildAndExpand("books & media", 42)
        .toUri();
~~~

Result looks like:

~~~text
https://api.example.test/v1/products/books%20%26%20media/42
~~~

| API | Meaning |
| --- | --- |
| `path("/products/{id}")` | Appends a path template segment |
| `pathSegment("products", "{id}")` | Appends individual segments |

Use `pathSegment` when a value must belong to one segment, especially if it contains spaces or reserved characters.

### 4.4. Path Variables Containing Slashes

A normal URI variable represents a single path value and should not be used to join multiple segments. Strict encoding can encode a slash in a value to `%2F`. However, proxies, gateways, or servers might decode encoded slashes before routing. If identifiers contain slashes, run integration tests across the entire network path. For opaque IDs, consider Base64URL or a representation without slashes.

## 5. queryParam and queryParams

### 5.1. queryParam(name, value...)

`queryParam` adds query parameters:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/v1/products")
        .queryParam("category", "{category}")
        .queryParam("page", "{page}")
        .queryParam("size", "{size}")
        .encode()
        .buildAndExpand("books", 2, 20)
        .toUri();
~~~

Result:

~~~text
https://api.example.test/v1/products?category=books&page=2&size=20
~~~

Common query parameters:

| Parameter | Meaning |
| --- | --- |
| `q` / `keyword` | Search keyword |
| `page` | Current page |
| `size` / `limit` | Items per page |
| `sort` | Sort field and direction |
| `filter` | Filter criteria |
| `expand` | Relations or expanded data |
| `locale` | Language or region |

Values used for filtering, pagination, and sorting generally fit query parameters better than paths.

### 5.2. Multiple Values for the Same Key

`queryParam` supports multiple values:

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/products")
        .queryParam("tag", "spring", "reactive", "webflux")
        .build()
        .toUri();
~~~

Result:

~~~text
https://api.example.test/products?tag=spring&tag=reactive&tag=webflux
~~~

Keys can be repeated across multiple calls:

~~~java
builder.queryParam("tag", "{tag1}")
       .queryParam("tag", "{tag2}");
~~~

The target API must support repeated query key semantics. Some APIs expect `tag=a&tag=b`, while others expect `tag=a,b`; do not automatically convert to comma-separated unless specified by the contract.

### 5.3. queryParamIfPresent

Use `queryParamIfPresent` when a parameter should only appear if a value is present:

~~~java
Optional<String> status = Optional.of("ACTIVE");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/users")
        .queryParamIfPresent("status", status)
        .build()
        .toUri();
~~~

If the Optional is empty, the key is not added.

Distinguish:

- Key absent: client does not send the parameter.
- Key present with empty string: `q=`.
- Key present with value: `q=reactive`.

These three states can carry different business meanings.

### 5.4. replaceQueryParam

When the builder already has a key and you want to replace its values:

~~~java
builder.queryParam("page", 1)
       .replaceQueryParam("page", "{page}");
~~~

`replaceQueryParam` replaces existing values for that key. Use this when the builder is initialized from a template with existing query parameters or when a URI is assembled across multiple steps.

### 5.5. queryParams with MultiValueMap

When many query parameters live in a map structure:

~~~java
MultiValueMap<String, String> query =
        new LinkedMultiValueMap<>();

query.add("tag", "spring");
query.add("tag", "reactive");
query.add("page", "2");

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/products")
        .queryParams(query)
        .build()
        .toUri();
~~~

`MultiValueMap` is appropriate because one query key can have multiple values. A regular `Map<String, String>` does not naturally represent repeated keys.

## 6. WebClient Encoding and URI Variables

WebClient uses `UriBuilderFactory` to expand and encode URI templates. By default, `DefaultUriBuilderFactory` uses `TEMPLATE_AND_VALUES`:

- Encodes the URI template first.
- Strictly encodes URI variables upon expansion.
- Reserved characters inside values are treated as data and do not alter the URI structure.

Example:

~~~java
URI uri = UriComponentsBuilder
        .fromPath("/products/{category}")
        .queryParam("q", "{term}")
        .encode()
        .buildAndExpand(
                "books & media",
                "C++ WebFlux")
        .toUri();
~~~

Result:

~~~text
/products/books%20%26%20media?q=C%2B%2B%20WebFlux
~~~

### 6.1. EncodingMode Options

| Mode | How it works |
| --- | --- |
| `TEMPLATE_AND_VALUES` | Encodes the template first and strictly encodes URI variables on expansion |
| `VALUES_ONLY` | Preserves the template, strictly encodes variables before expansion |
| `URI_COMPONENT` | Expands first, then encodes each component |
| `NONE` | Does not encode automatically |

For most requests with dynamic data, `TEMPLATE_AND_VALUES` is a sensible choice. Only change the mode when a specific contract requires reserved characters in variables to remain unencoded.

Explicit configuration:

~~~java
DefaultUriBuilderFactory factory =
        new DefaultUriBuilderFactory(
                "https://api.example.test");

factory.setEncodingMode(
        DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

WebClient client = WebClient.builder()
        .uriBuilderFactory(factory)
        .build();
~~~

### 6.2. Do Not Double-Encode Data

If the raw input is `a/b`, the builder may produce `a%2Fb`. If you pass the already-encoded string `a%2Fb` as raw data, `%` can be encoded to `%25`, producing `a%252Fb`.

Keep data raw and let a single builder layer encode it. Do not call `URLEncoder` or `UriUtils.encode` before passing values to a factory that already encodes.

### 6.3. Plus Signs and Spaces

- Spaces in URI components typically become `%20`.
- Literal plus signs typically must become `%2B`.
- `URLEncoder` uses form semantics, which can represent a space as `+`.

Do not use `URLEncoder` to encode an entire URL. Use `queryParam` and URI variables for WebClient queries.

## 7. DefaultUriVariables and Shared Variables

`WebClient.Builder.defaultUriVariables` declares default values for URI template variables when using Map expansion:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .defaultUriVariables(Map.of(
                "version", "v1",
                "locale", "vi-VN"))
        .build();
~~~

A template can then use the default variables:

~~~java
client.get()
        .uri("/api/{version}/products?locale={locale}")
        .retrieve()
        .bodyToMono(String.class);
~~~

Default variables are useful for shared configuration values. Do not use them to hide important per-request inputs. Variables affecting resources, tenants, or access permissions should be passed explicitly and validated per use case.

`defaultUriVariables` and `uriBuilderFactory` are mutually exclusive shortcuts on the builder. If supplying a factory directly, set default variables on that factory.

## 8. Distinguishing Path, Query, Header, and Body

| Location | Example | When to use |
| --- | --- | --- |
| Path | `/products/{id}` | Resource identification or resource hierarchy |
| Query | `?page=2&sort=name` | Filtering, pagination, sorting, and options |
| Header | `Authorization: Bearer ...` | Authentication, metadata, content negotiation |
| Body | JSON or binary | Payload for POST/PUT/PATCH |

Search request:

~~~java
Mono<ProductPage> result = client.get()
        .uri(builder -> builder
                .path("/v1/products")
                .queryParam("q", "{q}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "q", searchTerm,
                        "page", 0,
                        "size", 20)))
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Resource creation request:

~~~java
Mono<Product> created = client.post()
        .uri("/v1/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateProductRequest(
                "Spring WebFlux Guide",
                "books"))
        .retrieve()
        .bodyToMono(Product.class);
~~~

Do not place large payloads or secret data in the query string. Body is more suitable for creation/update payloads; tokens should use headers or an appropriate security mechanism.

## 9. Structure of a Complete WebClient Request

~~~java
Mono<ProductPage> result = client.get()
        .uri(builder -> builder
                .path("/v1/products/{category}")
                .queryParam("q", "{term}")
                .queryParam("page", "{page}")
                .queryParam("size", "{size}")
                .build(Map.of(
                        "category", category,
                        "term", term,
                        "page", page,
                        "size", size)))
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "catalog-service")
        .retrieve()
        .bodyToMono(ProductPage.class);
~~~

Steps:

1. `get()` selects HTTP GET.
2. `uri(...)` builds the path and query.
3. `accept(...)` requests a JSON response.
4. `header(...)` adds request metadata.
5. `retrieve()` processes the response via the retrieve API.
6. `bodyToMono(ProductPage.class)` decodes the response body into a DTO.

This is an illustrative snippet inside a service; client, category, term, page, DTOs, and JSON codec dependencies must be declared accordingly.

### 9.1. HTTP Error Handling with retrieve

By default `retrieve()` converts 4xx/5xx response statuses into `WebClientResponseException` if no custom handler is defined.

~~~java
Mono<ProductPage> result = client.get()
        .uri("/v1/products/{id}", productId)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.error(
                        new ProductNotFoundException(productId)))
        .bodyToMono(ProductPage.class);
~~~

This is an illustrative example assuming `ProductNotFoundException` exists. If you need to read the error response body, use `response.bodyToMono(String.class)` inside the callback and map it into a domain exception.

### 9.2. When to Use exchangeToMono?

`exchangeToMono` fits when the response status dictates how the body is read:

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", productId)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createException()
                    .flatMap(Mono::error);
        });
~~~

Spring manages the response body according to the exchange handler contract. Consume the body or return an appropriate Publisher; do not keep the response body beyond the lifecycle and try to read it later.

## 10. Organizing WebClient Beans in Spring Boot

In Spring Boot, inject the auto-configured `WebClient.Builder` and create a dedicated client per API:

~~~java
@Configuration
class PartnerClientConfig {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.test")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Service:

~~~java
@Service
class PartnerProductClient {

    private final WebClient client;

    PartnerProductClient(
            @Qualifier("partnerWebClient") WebClient client) {
        this.client = client;
    }

    Mono<Product> findById(UUID id) {
        return client.get()
                .uri("/v1/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);
    }
}
~~~

If there are multiple external APIs, name beans clearly and separate base URL configurations per service. Do not share one base URL and swap hosts using dynamic data from requests.

Base URL, port, and API prefix should come from configuration:

~~~yaml
clients:
  catalog:
    base-url: https://catalog.example.test
~~~

Inject using `@ConfigurationProperties` or `@Value` according to the project's configuration standards. Do not hard-code production hosts in business methods.

## 11. Runnable Java 17+ Program: WebClient, Base URL, Path, and Query

The following example starts a local HTTP server using the JDK, then uses WebClient to send a GET request to that server. The server echoes the raw request target so we can inspect the encoded path and query.

The program demonstrates:

- Base URL configured once.
- Path template with a category variable.
- Query with keyword, page, and repeated tags.
- Values with spaces, plus signs, and ampersands properly encoded.
- Map expansion passing variables by name.
- Assertion checking the exact request target.

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Boot BOM manages compatible Spring Framework, Reactor, and Reactor Netty versions.

### 11.1. Project Structure

~~~text
webclient-uri-demo/
  pom.xml
  src/main/java/example/webclient/WebClientUriDemo.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-uri-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. WebClientUriDemo.java

~~~java
package example.webclient;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

public final class WebClientUriDemo {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/v1/products", exchange -> {
            String path = exchange.getRequestURI().getRawPath();
            String query = exchange.getRequestURI().getRawQuery();

            String requestTarget = path +
                    (query == null ? "" : "?" + query);

            byte[] body = requestTarget.getBytes(
                    StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            String requestTarget = client.get()
                    .uri(builder -> builder
                            .path("/v1/products/{category}")
                            .queryParam("q", "{term}")
                            .queryParam("page", "{page}")
                            .queryParam("tag", "{tag1}")
                            .queryParam("tag", "{tag2}")
                            .build(Map.of(
                                    "category", "books & media",
                                    "term", "C++ & WebFlux",
                                    "page", 2,
                                    "tag1", "spring",
                                    "tag2", "reactive")))
                    .accept(MediaType.TEXT_PLAIN)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5));

            String expected =
                    "/v1/products/books%20%26%20media"
                    + "?q=C%2B%2B%20%26%20WebFlux"
                    + "&page=2&tag=spring&tag=reactive";

            if (!expected.equals(requestTarget)) {
                throw new AssertionError(
                        "Expected " + expected
                        + " but received " + requestTarget);
            }

            System.out.println("requestTarget=" + requestTarget);
        }
        finally {
            server.stop(0);
        }
    }
}
~~~

`block(Duration)` is only used here in the demo program's `main` to await request completion. In controllers or reactive services running on the event loop, do not call block; return Mono/Flux to the caller.

### 11.4. Running the Program

In the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.webclient.WebClientUriDemo
~~~

**Exact stdout:**

~~~text
requestTarget=/v1/products/books%20%26%20media?q=C%2B%2B%20%26%20WebFlux&page=2&tag=spring&tag=reactive
~~~

Explanation:

- The base URL contains the local host and port.
- `path` builds the category segment.
- `queryParam` adds q, page, and two tag values.
- `build(Map)` expands placeholders by name.
- `TEMPLATE_AND_VALUES` encodes spaces to `%20`, plus signs to `%2B`, and ampersands in values to `%26`.
- The server returns the raw path and raw query; the assertion verifies the exact request target string.

The program does not call the Internet or external APIs; both server and client run locally.

## 12. Testing WebClient URIs and Requests

The URI is part of the API contract. Test both normal values and boundary values.

### 12.1. Important Cases to Verify

| Input | What to verify |
| --- | --- |
| Numeric ID or UUID | Placeholder expands properly |
| Category with spaces | Spaces are encoded properly |
| Value with `+` | Literal plus does not turn into a space |
| Query value with `&` or `=` | Does not create unintended extra parameters |
| Vietnamese Unicode | Proper UTF-8 percent-encoding |
| Empty Optional | Query key is omitted or kept empty per contract |
| Repeated key | All values appear in the expected order |
| Absolute URI | Base URL does not override the absolute host |
| Base URL with path prefix | Final path has the correct prefix |
| Encoded slash | Proxy/gateway/server handle it consistently |

### 12.2. Testing via MockWebServer or a Local HTTP Server

You can use MockWebServer, WireMock, or a local server to capture the actual request. Verify:

- HTTP method.
- Raw path and raw query.
- Headers.
- Request body.
- Response status and body.
- Number of requests sent.
- Timeouts, errors, and cancellation if needed.

Do not only assert the URI object before sending; connectors or network layers may process the URI in ways that must be checked at the boundary.

### 12.3. Avoid Tests Dependent on Map Iteration Order

If using `Map.of`, do not rely on map iteration order to determine query parameter order. Add query parameters in an explicit order in the builder, then use the map only to expand declared placeholders. If the API signs requests, follow the API's official canonicalization rules.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an absolute URI and expecting baseUrl to be prepended | Host/base path is not applied | Use a relative URI or template |
| Configuring both baseUrl and uriBuilderFactory | Direct factory takes precedence, baseUrl shortcut is ignored | Choose one configuration mechanism |
| Concatenating category into path with strings | Input can inject extra segments or queries | Use path templates and URI variables |
| Manually concatenating query strings | `&`, `#`, or `=` can alter structure | Use queryParam |
| Using positional variables for long templates | Easy to pass arguments in wrong order | Use a named Map |
| Using path instead of pathSegment when value is one opaque segment | Data with slashes can change path structure | Use pathSegment and strict encoding |
| Using URLEncoder for the entire URI | Structural delimiters get encoded as data | Use UriBuilder per component |
| Pre-encoding input before passing to WebClient | Can double-encode into `%25` | Pass raw values |
| Switching EncodingMode to NONE to fix URLs | Data can become URI syntax | Find which layer pre-encoded first |
| Using queryParam for large payloads | Long URLs, data exposure, and potential limit errors | Use request body |
| Putting tokens in query | Tokens appear in access logs/history | Use Authorization header |
| Accepting user-controlled absolute URLs | Risk of SSRF or calling hosts outside policy | Validate destination and redirects |
| Using one WebClient for many hosts and swapping host from input | Difficult to control routing and security | Create separate clients per service |
| Calling block in reactive request flow | Blocks the event loop | Compose Mono/Flux |
| Not handling 4xx/5xx | Exceptions do not clearly reflect domain errors | Use onStatus or exchangeToMono |
| Relying on Map order to sign URIs | Signatures may mismatch across runs | Canonicalize per contract |
| Only testing URI strings without real requests | Misses connector/proxy behavior | Test with local server or mock server |

## 14. Security When Building WebClient URIs

### 14.1. SSRF and Absolute URLs

If an application accepts a URL from a user and calls it with WebClient, an attacker may attempt to reach localhost, private internal network addresses, cloud metadata services, or administrative endpoints.

Countermeasures:

- Prefer accepting a service ID or resource ID rather than a full URL.
- Use a base URL taken from trusted configuration.
- Allowlist scheme, host, and port.
- Inspect DNS resolution and resolved IP addresses.
- Control redirects so they cannot bypass the destination policy.
- Account for proxies, retries, and DNS rebinding in the threat model.

### 14.2. Path and Query Are Not Places for Secrets

Do not put passwords, API keys, bearer tokens, or sensitive data in URIs. URLs are frequently recorded in access logs, traces, browser history, and monitoring systems. Use headers or body according to the API contract.

### 14.3. Do Not Trust Path/Query Data Just Because It Is Encoded

Encoding protects URI syntax; it does not validate that data is valid for business rules. You must still validate:

- Does the ID exist?
- Does the user have permission to access the resource?
- Is the query filter allowed?
- Are page/size within limits?
- Is the sort field in the allowlist?
- Does the category belong to the valid set of values?

## 15. Production Readiness Checklist for WebClient URIs

- [ ] Base URL comes from trusted configuration.
- [ ] One client is organized per external API or service boundary.
- [ ] Relative URIs are used when base URL should apply.
- [ ] Aware that absolute URIs bypass base URL.
- [ ] One of baseUrl or uriBuilderFactory is chosen.
- [ ] Path templates are never built from untrusted input.
- [ ] `pathSegment` is used when a value must belong to one segment.
- [ ] `queryParam`/`queryParams` are used for queries.
- [ ] `Map` is used to expand multiple URI variables by name.
- [ ] Encoding mode is explicit; prefer `TEMPLATE_AND_VALUES` for opaque values.
- [ ] Data is not double-encoded.
- [ ] Repeated, absent, and empty query parameters match the contract.
- [ ] Headers, query, and body are used for their proper purposes.
- [ ] Appropriate timeouts and error handling are in place.
- [ ] No blocking on the reactive request path.
- [ ] SSRF protection is present if destination can be influenced by input.
- [ ] No secrets are placed in URIs.
- [ ] Raw path/query, method, headers, body, status, and redirects are tested.
- [ ] Unicode, reserved characters, and encoded slashes are tested across the real network path.

## 16. Self-Check

**Question 1.** Is `baseUrl` applied to every WebClient request?

No. It is used for relative URIs. An absolute URI or a complete `URI` passed directly will use that URI's own address.

**Question 2.** Can `WebClient.Builder.baseUrl` and `uriBuilderFactory` be used together to stack configurations?

No. `uriBuilderFactory` is the direct configuration mechanism and overrides the `baseUrl` shortcut.

**Question 3.** When should you use `uri(builder -> ...)`?

When you need to dynamically construct paths, queries, optional values, or multiple URI components within a single request.

**Question 4.** How do `path` and `pathSegment` differ?

`path` appends a path template segment; `pathSegment` appends individual segments and explicitly defines segment boundaries.

**Question 5.** How do you add multiple values for the same query key?

Use `queryParam("tag", "a", "b")` or call `queryParam` multiple times with the same key.

**Question 6.** When should you use `queryParamIfPresent`?

When a parameter should only appear if an Optional has a value; if the Optional is empty, no key is added.

**Question 7.** Why is a Map useful when expanding URI variables?

A Map binds values by placeholder name, reducing the risk of passing positional arguments in the wrong order when a template has many variables.

**Question 8.** Which mode does WebClient use by default to encode URI variables in current Spring Framework?

`TEMPLATE_AND_VALUES`. It encodes the template first and strictly encodes URI variables upon expansion.

**Question 9.** Should you pass an already percent-encoded URI value into WebClient template variables?

Usually no. Pass raw values and let the factory encode once; if an already-encoded value is passed, `%` can get encoded again.

**Question 10.** Is `block()` always forbidden when using WebClient?

No. It can be used at synchronous boundaries such as command-line programs or tests. Do not call block on the event loop or on a reactive request path.

**Question 11.** If a query key is repeated, does WebClient automatically merge it into one value?

No. The builder can produce repeated keys; the server receives and interprets them according to the API contract.

**Question 12.** Does Base URL automatically protect the application from SSRF?

No. Absolute URIs can bypass the base URL; the application must validate destinations and redirects according to security policy.

## 17. Official References

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient reactive API, sending requests and handling responses.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): create, builder, base URL, uriBuilderFactory, default headers, filters, and connector.
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriBuilder, UriComponentsBuilder, UriBuilderFactory, path/query, and URI encoding.
- [WebClient.Builder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html): baseUrl, defaultUriVariables, and uriBuilderFactory.
- [WebClient.UriSpec JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.UriSpec.html): uri(String), uri(URI), and uri(Function) overloads.
- [UriBuilder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriBuilder.html): path, pathSegment, queryParam, queryParams, build, and URI variables.
- [DefaultUriBuilderFactory JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/DefaultUriBuilderFactory.html): base URI, default variables, and EncodingMode.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): URI components, reserved/unreserved characters, and percent-encoding.

**Key takeaway:** Configure the base URL once per API, use `uri(builder -> ...)` to compose paths and queries, pass data via named URI variables, and let the factory encode exactly once. `pathSegment` expresses segment boundaries; `queryParam` expresses query values. Absolute URIs can bypass the base URL, so validating hosts, access permissions, and business data remains the application's responsibility.