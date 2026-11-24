# Checking Status, Headers, Cookies, and JSON Content with WebTestClient in Spring WebFlux

In a Spring WebFlux application, returning the right data from an endpoint is not enough to satisfy the API contract. The response must also carry the appropriate HTTP status, exact Content-Type, meaningful headers such as Location or ETag, cookies with the required security attributes, and the JSON structure that clients actually expect. For example, a POST creating a resource that returns HTTP 200 instead of 201, a cookie missing HttpOnly, or JSON missing a required field are all contract violations even if the controller throws no exception.

**WebTestClient** is Spring's HTTP testing API for both reactive applications and applications testable via a server. It builds requests similarly to WebClient, but after exchange() it provides a dedicated DSL for assertions: expectStatus(), expectHeader(), expectCookie(), expectBody(), jsonPath(), and body decoding options.

This lesson belongs to the **WebFlux Testing** group of the Spring Framework - reactive module. The focus is on distinguishing assertion types, choosing the appropriate test level, testing what truly matters, and building a runnable Java 17+ / Spring Boot 3.3.5 example project with Maven.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish HTTP status, response headers, Set-Cookie, and JSON body.
- Build GET/POST/PUT/DELETE requests with WebTestClient and call exchange().
- Accurately verify statuses 200, 201, 204, 400, 404, 405, and 415.
- Verify Content-Type, Location, ETag, Cache-Control, and custom headers.
- Use HeaderAssertions.exists(), doesNotExist(), valueEquals(), and valueMatches().
- Distinguish response cookies from cookies sent in the request.
- Use CookieAssertions to check name, value, path, Max-Age, HttpOnly, Secure, and SameSite.
- Compare JSON with json() in lenient or strict mode.
- Use JSONPath to check fields, arrays, data types, and nested values.
- Decode bodies with expectBody(Class) and expectBodyList(Class).
- Distinguish empty body, missing field, null value, and error status.
- Choose @WebFluxTest for controller slices or @SpringBootTest for integrated HTTP testing.
- Use expectAll and consumeWith when built-in assertions are insufficient.
- Avoid flakiness caused by JSON object ordering, current time, random IDs, and security cookies.
- Write a runnable sample project and request/response tests on Java 17+.

## 2. What parts of an HTTP response need checking?

An HTTP response typically contains:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/p-new
X-Request-Id: req-123
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax

{"id":"p-new","name":"Notebook","price":700,"available":true,"tags":["new"]}
~~~

Corresponding test layers:

| Component | Question | WebTestClient API |
| --- | --- | --- |
| Status line | Did the creation API succeed or fail? | expectStatus() |
| Content-Type | Is the response JSON? | expectHeader().contentTypeCompatibleWith(...) |
| Location | Where is the newly created resource URL? | expectHeader().location(...) |
| Custom header | Is the correlation ID returned? | expectHeader().valueEquals(...) |
| Set-Cookie | Does the cookie have secure attributes? | expectCookie() |
| JSON object | Are ID, name, price, boolean flag right? | expectBody().jsonPath(...) |
| Whole JSON | Does the body contract have exact fields and types? | expectBody().json(..., true) |
| Decoded DTO | Can it deserialize into a Java record? | expectBody(Product.class) |
| Empty body | Is HTTP 204 actually empty? | expectBody().isEmpty() |

Do not just check HTTP 200 and assume the entire response is valid. A regression can change headers or the body while leaving the status unchanged.

## 3. WebTestClient API flow

The typical test flow is:

~~~text
WebTestClient
    |
    +-- get() / post() / put() / delete()
    |       |
    |       +-- uri(...)
    |       +-- accept(...) / contentType(...)
    |       +-- headers(...) / cookie(...) / bodyValue(...)
    |
    +-- exchange()
            |
            +-- expectStatus()
            +-- expectHeader()
            +-- expectCookie()
            +-- expectBody()
                    |
                    +-- json(...)
                    +-- jsonPath(...)
                    +-- isEmpty()
            +-- expectBody(Product.class)
            +-- expectBodyList(Product.class)
~~~

Example:

~~~java
client.get()
    .uri("/api/products/p1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader()
        .valueEquals("X-Catalog-Version", "v1")
    .expectBody()
        .jsonPath("$.id").isEqualTo("p1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

Before exchange(), the API resembles WebClient's request building. After exchange(), WebTestClient no longer gives you a Mono<ResponseEntity<...>> to subscribe to yourself; instead, it returns ResponseSpec to declare assertions. WebTestClient executes the exchange itself and verifies the relevant signals.

### Which layer do assertions operate on?

- expectStatus() verifies the HTTP response status code.
- expectHeader() verifies HTTP headers without reading the JSON body.
- expectCookie() reads response cookies, including attributes from Set-Cookie.
- expectBody() reads the body and can compare JSON or decode into a DTO.
- returnResult(...) lets you process the response further, especially for streams.

## 4. Three ways to bind WebTestClient

There are three common scenarios.

### Binding directly to a controller

~~~java
WebTestClient client = WebTestClient
    .bindToController(new CatalogController(new CatalogService()))
    .build();
~~~

No real TCP port needs to be opened. Suitable when you want to test handlers, mappings, codecs, and minimal WebFlux infrastructure within the scope created for the test. Not equivalent to testing all production auto-configuration, filter chains, or reverse proxies.

### Binding to an ApplicationContext

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .build();
~~~

The test uses an existing WebApplicationContext and configured beans. Spring Boot typically provides WebTestClient automatically when using @WebFluxTest.

### Binding to a running server

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

Can test HTTP exchanges over a real socket. When running @SpringBootTest(webEnvironment = RANDOM_PORT) with @AutoConfigureWebTestClient, Spring Boot can inject a WebTestClient pointed at the embedded test server.

The three approaches have different levels of isolation. For testing controller status/header/cookie/JSON contracts, @WebFluxTest is usually fast and thorough enough. For HTTP security filters, codec configuration, network behavior, or server integration, add @SpringBootTest or end-to-end tests.

## 5. Checking HTTP status

WebTestClient supports expressive shortcuts:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk();
~~~

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Notebook", 700))
    .exchange()
    .expectStatus().isCreated();
~~~

~~~java
client.get().uri("/api/products/missing")
    .exchange()
    .expectStatus().isNotFound();
~~~

~~~java
client.get().uri("/api/diagnostics/empty")
    .exchange()
    .expectStatus().isNoContent();
~~~

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.TEXT_PLAIN)
    .bodyValue("not-json")
    .exchange()
    .expectStatus().isEqualTo(415);
~~~

Common HTTP statuses and their meanings:

| Status | Context | Test expectation |
| --- | --- | --- |
| 200 OK | Successful GET | isOk() |
| 201 Created | POST creates a resource | isCreated() |
| 204 No Content | Success, no body | isNoContent() combined with isEmpty() |
| 400 Bad Request | Invalid input | isBadRequest() |
| 401 Unauthorized | No valid authentication | isUnauthorized() |
| 403 Forbidden | Authenticated but unauthorized | isForbidden() |
| 404 Not Found | Resource not found | isNotFound() |
| 405 Method Not Allowed | Method has no mapping | isEqualTo(405) |
| 415 Unsupported Media Type | Request Content-Type not supported | isEqualTo(415) |
| 500 Internal Server Error | Unhandled server error | is5xxServerError() |

Do not use only is2xxSuccessful() when the contract specifically requires 201 or 204. is2xxSuccessful() allows any 2xx status and can miss a regression.

### Checking the error chain at the right layer

If a POST body is invalid yet the server returns 500, do not change the test to expect 500. Determine whether input errors should map to 400, 422, or another status per the API contract, and fix the server or test accordingly.

## 6. HeaderAssertions: ways to check headers

Take an example GET /api/products/p1 returning:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "catalog-p1-v1"
Cache-Control: no-store
X-Catalog-Version: v1
~~~

Key assertions:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader()
        .valueEquals(HttpHeaders.ETAG, "\"catalog-p1-v1\"")
    .expectHeader()
        .cacheControl(CacheControl.noStore())
    .expectHeader()
        .valueEquals("X-Catalog-Version", "v1");
~~~

### contentType and contentTypeCompatibleWith

- contentType(MediaType.APPLICATION_JSON): checks the exact expected Content-Type value; suitable when the format must be exact.
- contentTypeCompatibleWith(MediaType.APPLICATION_JSON): checks a compatible media type; useful when the server appends a charset parameter or uses a compatible JSON media type.

Do not overuse compatibleWith if the contract mandates a specific media type. Conversely, do not enforce byte-for-byte headers with inconsequential parameters when the client only needs to know the content is JSON.

### exists and doesNotExist

~~~java
.expectHeader().exists("X-Catalog-Version")
.expectHeader().doesNotExist("X-Legacy-Flag");
~~~

exists only checks that the header is present; it does not prove the header has a valid value. For correlation IDs or token formats, verify with a regex or consumer.

### valueEquals and valueMatches

~~~java
.expectHeader().valueEquals("X-Catalog-Version", "v1")
.expectHeader().valueMatches("X-Request-Id", "req-[0-9]{3}");
~~~

valueMatches uses a regular expression. It is useful for dynamic IDs with a fixed format. Avoid overly broad regexes like .* because they verify almost nothing about the value.

### Location, ETag, and Cache-Control

~~~java
.expectHeader().location("/api/products/p-new")
~~~

Location suits status 201 when an API creates a resource. ETag supports caching/concurrency control. Cache-Control expresses caching policy. For reliable tests, identify which headers belong to the public contract rather than asserting all headers added by servers/proxies.

## 7. Cookies: distinguishing request and response

Cookies travel in two directions:

~~~http
GET /api/profile HTTP/1.1
Cookie: language=vi
~~~

This is a **request cookie** sent by the client to the server.

~~~http
HTTP/1.1 200 OK
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax
~~~

This is a **response cookie** the server wants the browser to store.

In WebTestClient:

- cookie("language", "vi") puts Cookie into the request.
- expectCookie() checks cookies in the response.
- expectHeader().valueMatches(HttpHeaders.SET_COOKIE, ...) checks the raw Set-Cookie header if needed.
- CookieAssertions helps inspect parsed attributes rather than matching raw strings whose attribute order may vary.

Example sending a request cookie:

~~~java
client.get()
    .uri("/api/profile")
    .cookie("language", "vi")
    .exchange();
~~~

The snippet above does not assert that the server returned a response cookie. To check Set-Cookie, you must use expectCookie().

## 8. CookieAssertions: values and security attributes

Given a response cookie:

~~~http
Set-Cookie: demo_pref=enabled; Path=/api; Max-Age=900; Secure; HttpOnly; SameSite=Lax
~~~

WebTestClient supports:

~~~java
client.get().uri("/api/diagnostics/cookie")
    .exchange()
    .expectStatus().isOk()
    .expectCookie().exists("demo_pref")
    .expectCookie().valueEquals("demo_pref", "enabled")
    .expectCookie().path("demo_pref", "/api")
    .expectCookie().maxAge(
        "demo_pref", Duration.ofMinutes(15))
    .expectCookie().secure("demo_pref", true)
    .expectCookie().httpOnly("demo_pref", true)
    .expectCookie().sameSite("demo_pref", "Lax");
~~~

Meanings:

| Cookie assertion | Checks |
| --- | --- |
| exists(name) | Cookie is present in response |
| doesNotExist(name) | Cookie is absent from response |
| valueEquals(name, value) | Cookie value |
| path(name, path) | Path attribute |
| maxAge(name, Duration) | Max-Age attribute |
| secure(name, boolean) | Presence/absence of Secure |
| httpOnly(name, boolean) | Presence/absence of HttpOnly |
| sameSite(name, value) | SameSite attribute |
| domain(name, expected) | Domain attribute |

### Security and test limitations

An HttpOnly cookie prevents JavaScript from reading that cookie via document.cookie; Secure requires browsers to send it only over connections meeting HTTPS policy; SameSite helps govern cookie transmission in cross-site scenarios. These flags **do not replace proper authentication, authorization, CSRF protection, or session management**.

WebTestClient can verify that the server emits the cookie attributes, but by itself it does not prove every browser will store or send the cookie. If a response includes Secure over a mock HTTP test, the assertion can still succeed; production browsers must be tested over HTTPS under real cookie policies.

Do not write security cookie tests that only check exists(). A regression removing HttpOnly would still pass that check. When attributes are part of the security contract, check each attribute directly.

### Raw Set-Cookie

The raw header can be checked:

~~~java
.expectHeader().valueMatches(
    HttpHeaders.SET_COOKIE,
    "demo_pref=enabled;.*");
~~~

However, asserting an entire Set-Cookie string in the exact order of Path, Max-Age, Expires, Secure, HttpOnly, and SameSite is brittle because attribute ordering or Expires formatting can vary. Prefer CookieAssertions for semantic checks.

## 9. JSON body: three assertion strategies

Suppose the API returns:

~~~json
{
  "id": "p1",
  "name": "Keyboard",
  "price": 1200,
  "available": true,
  "tags": ["input", "office"]
}
~~~

Three main strategies:

1. **JSON structural comparison** when matching an object or the entire response.
2. **JSONPath** when you only want to check a few key fields/nested values.
3. **Decoding to a DTO** when other clients share the same Java model and object checks are needed.

Not every test has to check all three. Choose the clearest option for the behavior being guarded.

### Checking partial JSON

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("{\"id\":\"p1\",\"name\":\"Keyboard\"}");
~~~

In Spring Framework 6.1, json(String) uses lenient JSON comparison, allowing the actual object to have extra fields and not requiring arrays to preserve exact order in many cases. It is not a JSON byte-string match.

### Strict JSON comparison

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json(
        "{\"id\":\"p1\",\"name\":\"Keyboard\","
        + "\"price\":1200,\"available\":true,"
        + "\"tags\":[\"input\",\"office\"]}",
        true);
~~~

In Spring Framework 6.1, json(expected, true) performs **strict** JSON comparison: no extra fields are allowed and exact array ordering is required as expected. JSON object key order is insignificant; JSONAssert compares structure rather than requiring byte order.

Since Spring 6.2 there is an overload taking JsonCompareMode, so when studying code across versions, consult the exact Javadoc of the Spring Framework version in use.

### When can strict be too tight?

If the API allows backward-compatible field additions, strict JSON will fail when a new field is added even though clients keep working. Use JSONPath or lenient when guarding only core fields. Use strict when the schema is a closed contract, such as a response used for digital signing or a contract that must forbid unexpected fields.

## 10. JSONPath: checking fields and arrays accurately

JSONPath accesses locations within the JSON response:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("p1")
    .jsonPath("$.price").isEqualTo(1200)
    .jsonPath("$.available").isEqualTo(true)
    .jsonPath("$.tags[0]").isEqualTo("input");
~~~

Common selectors:

| JSONPath | Meaning |
| --- | --- |
| $ | Entire root |
| $.id | Field id of the root object |
| $.customer.name | Nested field |
| $.tags[0] | First element in the tags array |
| $[0].id | Field id of the first element if root is an array |
| $.items[*].id | List of IDs of all items |
| $.metadata.traceId | Field traceId inside the metadata object |

If the response is an array:

~~~json
[
  {"id":"p1","name":"Keyboard"},
  {"id":"p2","name":"Mouse"}
]
~~~

Test:

~~~java
client.get().uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$").isArray()
    .jsonPath("$[0].id").isEqualTo("p1")
    .jsonPath("$[1].name").isEqualTo("Mouse");
~~~

Specialized assertions like exists(), doesNotExist(), isArray(), isMap(), isNumber(), isBoolean(), and isNotEmpty() express data types. Pick the type matching the actual data.

### Null and missing fields are not the same

~~~json
{"nickname": null}
~~~

differs from:

~~~json
{}
~~~

If the API requires a field to be present even with a null value, check the schema/JSONPath in a way that clearly distinguishes them. Some existence-checking helpers have semantics that treat null as absent; consult the exact Javadoc and use structural JSON comparison or body decoding when this distinction is core.

### JSON numbers and Java numbers

JSON has only a number type; when JSONPath decodes through Java libraries, a number may become Integer, Long, or BigDecimal depending on its form. If an assertion fails due to numeric type, check the decoded value and type instead of turning all expectations into Strings.

## 11. Decoding JSON bodies into Java records or DTOs

If the API returns a Product and you want to compare the model at the Java level:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .consumeWith(result -> {
        Product product = result.getResponseBody();

        assertNotNull(product);
        assertEquals("p1", product.id());
        assertEquals(1200, product.price());
    });
~~~

This is a two-step test: WebTestClient decodes JSON into Product via configured codecs; then assertions check the object.

For an array response:

~~~java
client.get().uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(Product.class)
    .hasSize(2)
    .contains(
        new Product(
            "p1", "Keyboard", 1200, true,
            List.of("input", "office")));
~~~

Java records automatically have field-based equals/hashCode, so contains() compares record contents. If a DTO is a regular class that does not override equals(), contains() may not compare as you expect. In that case use consumeWith and AssertJ/JUnit to check fields.

### Generic responses

For responses like ApiPage<Product>, you can use expectBody(new ParameterizedTypeReference<ApiPage<Product>>() {}) to preserve the generic type. Do not use raw ApiPage.class when the decoder needs to know the collection element type.

### Do not overfit to the server's own DTO

In contract tests aimed at independent consumers, decoding with the server's internal DTO can miss incompatibilities with consumers on different versions. Combine structural JSON assertions at the boundary with integration/consumer-contract tests when cross-microservice compatibility is needed.

## 12. Empty bodies and no-content statuses

HTTP 204 No Content has no response body. Appropriate assertions:

~~~java
client.get().uri("/api/diagnostics/empty")
    .exchange()
    .expectStatus().isNoContent()
    .expectHeader().doesNotExist(HttpHeaders.CONTENT_TYPE)
    .expectBody().isEmpty();
~~~

Do not check JSONPath when the endpoint contract specifies an empty body. An HTTP 204 status accompanied by a JSON body is a contract contradiction.

For error statuses without a body:

~~~java
client.get().uri("/api/products/missing")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody().isEmpty();
~~~

If the API follows RFC 9457 and returns ProblemDetail JSON on 404, replace the expectation above with the ProblemDetail content type and JSON schema. There is no single "universal rule" for every 404 body; rely on the endpoint's own contract.

### HTTP HEAD

HEAD also returns no response body, but headers and status must reflect the corresponding GET per the protocol. If the API supports HEAD, test status/headers independently without assuming GET and HEAD always share the same body assertions.

## 13. Controlling request inputs to understand responses

Response assertions make more sense when the request is constructed properly.

### GET with Accept

~~~java
client.get()
    .uri("/api/products/p1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange();
~~~

Accept states that the client accepts a JSON response; it differs from Content-Type, which describes the outgoing request body.

### POST JSON

~~~java
client.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Notebook", 700))
    .exchange();
~~~

WebTestClient uses codecs to serialize CreateProduct to JSON. If Content-Type is omitted and the endpoint declares consumes application/json, the test may receive 415 depending on request/codec configuration.

### Custom request header

~~~java
client.get()
    .uri("/api/products/p1")
    .header("X-Correlation-Id", "test-001")
    .exchange();
~~~

A header sent **in the request** does not automatically become a response header. Unless the server has logic to echo or generate a corresponding response header, expectHeader() cannot see it by itself.

### Request cookie

~~~java
client.get()
    .uri("/api/diagnostics/cookie")
    .cookie("locale", "vi")
    .exchange();
~~~

A request cookie does not prove a response cookie exists; expectCookie is needed after exchange. This helps separate the two directions of data flow.

## 14. @WebFluxTest and @SpringBootTest: choosing the test level

With Spring Boot WebFlux, two common test styles:

| Style | Scope | Strengths | Limitations |
| --- | --- | --- | --- |
| @WebFluxTest(CatalogController.class) | WebFlux MVC-like controller slice, codecs, mappings, advice | Fast, isolated, easy to trace errors | Does not load all services/repositories/filters outside slice |
| @SpringBootTest + @AutoConfigureWebTestClient | Larger ApplicationContext; can run embedded server | Verifies auto-configuration, beans, and HTTP integration | Slower, requires controlling dependencies |
| WebTestClient.bindToController | Directly instantiated controller | Very fast, no Boot context needed | May lack production infrastructure and filters |
| WebTestClient.bindToServer | HTTP to an existing server | Tests over a real network | Depends on environment/port/server |

### Slice tests and dependencies

If CatalogController injects CatalogService, a @WebFluxTest does not automatically bring every @Service into the context. You can use @MockBean to stub the service per test goal or @Import(CatalogService.class) if the service is simple with no side effects. In the project below, the service is immutable and deterministic, so @Import is used to test real data/serialization.

### Integration tests

With RANDOM_PORT, the embedded server opens a random port; @AutoConfigureWebTestClient creates a matching client for the test. Do not hardcode port 8080 in integration tests. Tests that genuinely need a database/external service must use test fixtures and an isolated environment, never calling production endpoints.

### Security testing

If Spring Security is present, @WebFluxTest may load security filters depending on configuration and produce 401/403 before the controller. Clearly determine whether you are testing an anonymous or authenticated contract, and use spring-security-test and appropriate WebTestClientMutators. Do not disable all security in tests if the goal is to verify authorization and session cookies.

## 15. Hands-on Java 17+ Spring Boot WebFlux project

The demo application returns fixed catalog data so tests produce deterministic results without needing a database. It includes:

- GET /api/products: returns an array of two products.
- GET /api/products/{id}: returns 200 + Content-Type, ETag, Cache-Control, and X-Catalog-Version; returns 404 if the ID is absent.
- POST /api/products: validates input, returns 201 + Location + X-Request-Id + JSON Product; returns 400 + JSON error if name is blank or price is negative.
- GET /api/diagnostics/cookie: returns response cookie demo_pref with Secure, HttpOnly, SameSite, Path, Max-Age.
- GET /api/diagnostics/empty: returns 204 with no body.

Note: POST in the demo only **simulates a resource-creation response** and does not persist to a database. The ID p-new is fixed for test readability; production apps must persist properly, generate suitable IDs, and handle idempotency/concurrency. The demo_pref cookie represents a preference only, **not an access token or session authentication**.

### Project structure

~~~text
webflux-response-contract-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogApiModels.java
    │   ├── CatalogService.java
    │   └── CatalogController.java
    └── test/java/com/example/catalog/
        ├── CatalogControllerTest.java
        └── CatalogHttpIntegrationTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-response-contract-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

spring-boot-starter-test provides JUnit Jupiter, AssertJ, JsonPath, and JSONAssert needed for the assertions in this lesson. Reactor Test is declared separately for streaming tests using StepVerifier later on. There is no need to add the Spring MVC starter; adding spring-boot-starter-web unintentionally alongside it can cause Spring Boot to choose the servlet stack instead of WebFlux.

### CatalogApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### CatalogApiModels.java

~~~java
package com.example.catalog;

import java.util.List;

public final class CatalogApiModels {

    private CatalogApiModels() {
    }

    public record Product(
            String id,
            String name,
            int price,
            boolean available,
            List<String> tags) {
    }

    public record CreateProduct(
            String name,
            int price) {
    }

    public record ApiError(
            String code,
            String message) {
    }

    public record CookieInfo(
            boolean enabled) {
    }
}
~~~

Nested records are implicitly public static in Java, and Jackson can use them as DTOs. Product.price is an int to keep the example simple; in financial applications, use BigDecimal and an explicit currency unit to avoid rounding/semantic errors.

### CatalogService.java

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.stereotype.Service;

import com.example.catalog.CatalogApiModels.Product;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private static final List<Product> PRODUCTS = List.of(
        new Product(
            "p1", "Keyboard", 1200, true,
            List.of("input", "office")),
        new Product(
            "p2", "Mouse", 450, false,
            List.of("input"))
    );

    public Flux<Product> all() {
        return Flux.fromIterable(PRODUCTS);
    }

    public Mono<Product> findById(String id) {
        return all()
            .filter(product -> product.id().equals(id))
            .next();
    }
}
~~~

Immutable data keeps tests independent of each other. In production, CatalogService can be replaced with a reactive repository; control test data and avoid relying on a shared database.

### CatalogController.java

~~~java
package com.example.catalog;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.catalog.CatalogApiModels.ApiError;
import com.example.catalog.CatalogApiModels.CookieInfo;
import com.example.catalog.CatalogApiModels.CreateProduct;
import com.example.catalog.CatalogApiModels.Product;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/products",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Product> all() {
        return service.all();
    }

    @GetMapping(
        path = "/products/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Product>> byId(
            @PathVariable String id) {

        return service.findById(id)
            .map(product -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Catalog-Version", "v1")
                .eTag("\"catalog-" + id + "-v1\"")
                .cacheControl(CacheControl.noStore())
                .body(product))
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PostMapping(
        path = "/products",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Product>> create(
            @RequestBody Mono<CreateProduct> request) {

        return request.map(input -> {
            if (input.name() == null
                    || input.name().isBlank()) {
                throw new IllegalArgumentException(
                    "name must not be blank");
            }
            if (input.price() < 0) {
                throw new IllegalArgumentException(
                    "price must not be negative");
            }

            Product created = new Product(
                "p-new",
                input.name(),
                input.price(),
                true,
                List.of("new"));

            return ResponseEntity
                .created(URI.create("/api/products/p-new"))
                .header("X-Request-Id", "req-123")
                .contentType(MediaType.APPLICATION_JSON)
                .body(created);
        });
    }

    @GetMapping(
        path = "/diagnostics/cookie",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CookieInfo> demoCookie() {
        ResponseCookie cookie = ResponseCookie
            .from("demo_pref", "enabled")
            .path("/api")
            .maxAge(Duration.ofMinutes(15))
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .header("X-Request-Id", "req-123")
            .contentType(MediaType.APPLICATION_JSON)
            .body(new CookieInfo(true));
    }

    @GetMapping("/diagnostics/empty")
    public ResponseEntity<Void> empty() {
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidInput(
            IllegalArgumentException error) {

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ApiError(
                "INVALID_INPUT", error.getMessage()));
    }
}
~~~

Explanation of test design decisions:

1. Product data is fixed and deterministically ordered.
2. GET /products/p1 emits JSON along with headers actively produced by the endpoint.
3. GET when not found returns ResponseEntity.notFound(), with no JSON body.
4. POST returns 201 and Location, along with header X-Request-Id.
5. POST with blank name throws IllegalArgumentException, translated by @ExceptionHandler into status 400 and ApiError JSON.
6. POST with text/plain is rejected by consumes application/json, typically returning 415.
7. Cookies are built using ResponseCookie rather than manually concatenating raw attributes.
8. Secure/HttpOnly/SameSite are tested, though demo_pref carries no sensitive credentials.
9. The 204 endpoint returns ResponseEntity<Void> with no body.
10. There is no background work or volatile source, keeping tests low-flakiness.

## 16. Controller slice tests with @WebFluxTest

The test class below uses @WebFluxTest(CatalogController.class) and @Import(CatalogService.class) to bring the immutable service into the context. WebTestClient is injected by Spring Boot. No real embedded HTTP server runs in a slice test.

### CatalogControllerTest.java

~~~java
package com.example.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import com.example.catalog.CatalogApiModels.CreateProduct;
import com.example.catalog.CatalogApiModels.Product;

@WebFluxTest(CatalogController.class)
@Import(CatalogService.class)
class CatalogControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void getProductChecksStatusAndImportantHeaders() {
        client.get()
            .uri("/api/products/p1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectHeader()
                .valueEquals(
                    "X-Catalog-Version", "v1")
            .expectHeader()
                .valueEquals(
                    HttpHeaders.ETAG,
                    "\"catalog-p1-v1\"")
            .expectHeader()
                .cacheControl(CacheControl.noStore());
    }

    @Test
    void getProductChecksJsonPathValuesAndTypes() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1")
            .jsonPath("$.name").isEqualTo("Keyboard")
            .jsonPath("$.price").isEqualTo(1200)
            .jsonPath("$.available").isEqualTo(true)
            .jsonPath("$.tags").isArray()
            .jsonPath("$.tags[0]").isEqualTo("input");
    }

    @Test
    void getProductChecksStrictJsonDocument() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json(
                "{\"id\":\"p1\","
                + "\"name\":\"Keyboard\","
                + "\"price\":1200,"
                + "\"available\":true,"
                + "\"tags\":[\"input\",\"office\"]}",
                true);
    }

    @Test
    void listChecksJsonArrayPaths() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$").isArray()
            .jsonPath("$[0].id").isEqualTo("p1")
            .jsonPath("$[1].id").isEqualTo("p2")
            .jsonPath("$[1].available").isEqualTo(false);
    }

    @Test
    void listCanBeDecodedIntoTypedJavaRecords() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Product.class)
            .hasSize(2)
            .contains(new Product(
                "p1", "Keyboard", 1200, true,
                List.of("input", "office")));
    }

    @Test
    void missingProductReturns404AndEmptyBody() {
        client.get().uri("/api/products/unknown")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().isEmpty();
    }

    @Test
    void createReturns201LocationHeaderAndProduct() {
        client.post().uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProduct("Notebook", 700))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .location("/api/products/p-new")
            .expectHeader()
                .valueMatches(
                    "X-Request-Id", "req-[0-9]{3}")
            .expectBody(Product.class)
            .consumeWith(result -> {
                Product created = result.getResponseBody();

                assertNotNull(created);
                assertEquals("p-new", created.id());
                assertEquals("Notebook", created.name());
                assertEquals(700, created.price());
            });
    }

    @Test
    void invalidInputReturns400AndErrorJson() {
        client.post().uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProduct("", -1))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .json(
                "{\"code\":\"INVALID_INPUT\","
                + "\"message\":\"name must not be blank\"}",
                true);
    }

    @Test
    void unsupportedRequestMediaTypeReturns415() {
        client.post().uri("/api/products")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("raw-text")
            .exchange()
            .expectStatus().isEqualTo(415);
    }

    @Test
    void unsupportedHttpMethodReturns405() {
        client.put().uri("/api/products/p1")
            .exchange()
            .expectStatus().isEqualTo(405);
    }

    @Test
    void responseCookieHasRequiredAttributes() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectCookie().exists("demo_pref")
            .expectCookie().valueEquals(
                "demo_pref", "enabled")
            .expectCookie().path("demo_pref", "/api")
            .expectCookie().maxAge(
                "demo_pref", Duration.ofMinutes(15))
            .expectCookie().httpOnly("demo_pref", true)
            .expectCookie().secure("demo_pref", true)
            .expectCookie().sameSite("demo_pref", "Lax");
    }

    @Test
    void rawSetCookieAndCustomHeaderCanBeChecked() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .valueMatches(
                    HttpHeaders.SET_COOKIE,
                    "demo_pref=enabled;.*")
            .expectHeader()
                .valueEquals("X-Request-Id", "req-123")
            .expectBody()
                .jsonPath("$.enabled").isEqualTo(true);
    }

    @Test
    void ordinaryProductResponseHasNoDemoCookie() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectCookie().doesNotExist("demo_pref")
            .expectHeader()
                .doesNotExist(HttpHeaders.SET_COOKIE);
    }

    @Test
    void noContentResponseHas204AndNoBody() {
        client.get().uri("/api/diagnostics/empty")
            .exchange()
            .expectStatus().isNoContent()
            .expectHeader()
                .doesNotExist(HttpHeaders.CONTENT_TYPE)
            .expectBody().isEmpty();
    }

    @Test
    void expectAllCanReportSeveralFailuresAtOnce() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                    .valueEquals("X-Catalog-Version", "v1"),
                spec -> spec.expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1");
    }

    @Test
    void rawBodyCanBeConsumedWhenCustomAssertionIsNeeded() {
        client.get().uri("/api/products/p1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .consumeWith(result -> {
                byte[] bytes = result.getResponseBody();

                assertNotNull(bytes);
                String json = new String(
                    bytes, StandardCharsets.UTF_8);
                assertTrue(json.contains("\"Keyboard\""));
            });
    }
}
~~~

### Reading the tests by group

- Tests 1–3: GET status, key headers, JSONPath, and strict JSON.
- Tests 4–5: JSON array list via JSONPath and typed body list.
- Test 6: 404 must have an empty body per contract.
- Test 7: POST has 201, Location, custom header, and right DTO.
- Test 8: invalid input turns into 400 + JSON error schema.
- Tests 9–10: 415 and 405 are regression checks for the request contract.
- Tests 11–13: cookie value, Path, Max-Age, Secure, HttpOnly, SameSite; raw header and absence of cookie on another endpoint.
- Test 14: 204 response has no Content-Type/body.
- Test 15: expectAll to group assertions on the same exchange.
- Test 16: consumeWith when a custom assertion on raw response bytes is needed.

Several tests intentionally combine status, header, and body assertions in the same exchange to guard multiple parts of **one HTTP response**. Avoid splitting into separate requests when producing a response has side effects or variable data.

## 17. Integrated HTTP testing via embedded server

Slice tests verify the WebFlux handler in a narrowed context. Add an integration test to confirm the application actually runs the embedded server, encodes JSON, and emits cookies over HTTP.

### CatalogHttpIntegrationTest.java

~~~java
package com.example.catalog;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CatalogHttpIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void productContractWorksOverEmbeddedHttpServer() {
        client.get().uri("/api/products/p1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Catalog-Version", "v1")
            .expectBody()
            .jsonPath("$.id").isEqualTo("p1");
    }

    @Test
    void cookieIsSerializedWithSecurityAttributes() {
        client.get().uri("/api/diagnostics/cookie")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists(HttpHeaders.SET_COOKIE)
            .expectCookie().exists("demo_pref")
            .expectCookie().httpOnly("demo_pref", true)
            .expectCookie().secure("demo_pref", true)
            .expectCookie().sameSite("demo_pref", "Lax")
            .expectCookie().maxAge(
                "demo_pref", Duration.ofMinutes(15));
    }
}
~~~

Important distinction: RANDOM_PORT opens a real HTTP socket in the test, yet this test is still not browser end-to-end. WebTestClient verifies the HTTP response and cookie attributes; it does not fully simulate Chrome/Safari cookie policies, CORS, proxies, TLS termination, or CDNs.

If security filters or authentication need testing, add cases for 401, 403, CSRF, cookie sessions, and bearer tokens matching the application's real security configuration.

## 18. Running Maven and checking results

Environment requirements: Java 17+, Maven 3.8+, and ability to download Maven dependencies. Place files in the exact com.example.catalog package per the project structure.

### Running tests

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

There are 16 test methods in CatalogControllerTest and 2 test methods in CatalogHttpIntegrationTest, totaling 18 tests. If all succeed, Maven completes with exit code 0.

For more readable reporting:

~~~bash
mvn test
~~~

Typical final output looks like:

~~~text
Tests run: 16, Failures: 0, Errors: 0, Skipped: 0
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is an **illustration of expected output**, not Maven output executed while authoring this lesson. Line ordering and logs depend on Maven Surefire version, operating system, and test configuration.

### Running the application

~~~bash
mvn spring-boot:run
~~~

By default the application listens on http://localhost:8080 if no other port is configured.

### Testing GET

~~~bash
curl -i "http://localhost:8080/api/products/p1" \
  -H "Accept: application/json"
~~~

Expected status and data:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Catalog-Version: v1
ETag: "catalog-p1-v1"
Cache-Control: no-store
~~~

~~~json
{"id":"p1","name":"Keyboard","price":1200,"available":true,"tags":["input","office"]}
~~~

Technical headers such as Date, Content-Length, or Transfer-Encoding depend on the server. Do not write tests requiring all technical headers to appear in one exact order.

### Testing POST

~~~bash
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","price":700}'
~~~

Expected status: 201 Created; Location /api/products/p-new; X-Request-Id req-123. Expected body:

~~~json
{"id":"p-new","name":"Notebook","price":700,"available":true,"tags":["new"]}
~~~

### Testing response cookies

~~~bash
curl -i "http://localhost:8080/api/diagnostics/cookie"
~~~

Expected Set-Cookie header has the following attributes, though order and Expires format may vary:

~~~text
demo_pref=enabled
Path=/api
Max-Age=900
Secure
HttpOnly
SameSite=Lax
~~~

This cookie has no authentication effect. With a browser, HTTPS is needed to test sending behavior for cookies with Secure.

## 19. Which assertion to choose for each contract type?

| Requirement | Preferred assertion | Do not rely solely on |
| --- | --- | --- |
| POST must return 201 | expectStatus().isCreated() | is2xxSuccessful() |
| Response is JSON | contentTypeCompatibleWith(APPLICATION_JSON) | exists(Content-Type) |
| Exact Location | expectHeader().location(...) | exists(Location) |
| Exact ETag | valueEquals(ETag, ...) | exists(ETag) |
| X-Request-Id has format | valueMatches(...) | exists(...) |
| Cookie has HttpOnly | expectCookie().httpOnly(name, true) | exists(name) |
| Cookie has Secure | expectCookie().secure(name, true) | valueEquals(name, value) |
| Cookie must not appear | expectCookie().doesNotExist(name) | Skipping check |
| JSON only needs ID field | jsonPath("$.id").isEqualTo(...) | Strict whole document |
| Closed JSON schema | json(expected, true) | Checking only one field |
| Array has n elements | expectBodyList(...).hasSize(n) | exists("$") |
| Empty body | expectBody().isEmpty() | Only status 204 |
| Error JSON has code | jsonPath("$.code").isEqualTo(...) | Only 400 |
| Business model deserializes | expectBody(Product.class) | Raw string comparison |

A good test suite does not necessarily have the most assertions; it should protect properties that are error-prone and meaningful to consumers.

## 20. Checking error JSON and ProblemDetail

An error can be returned according to a custom schema:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "name must not be blank"
}
~~~

Then:

~~~java
client.post().uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("", 100))
    .exchange()
    .expectStatus().isBadRequest()
    .expectBody()
    .jsonPath("$.code").isEqualTo("INVALID_INPUT")
    .jsonPath("$.message").isEqualTo("name must not be blank");
~~~

If the application uses ProblemDetail/RFC 9457, the response can be application/problem+json with a body containing type, title, status, detail, and instance. Test against the structure the real API actually commits to:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid input"
}
~~~

Do not copy the ProblemDetail test into the default demo without matching error handling; CatalogController's response currently uses custom ApiError.

### Negative tests help catch unintended changes

Do not test only the happy path. Common bugs may not show up in the happy path:

- Invalid request body.
- Unsupported Content-Type.
- Non-existent resource.
- Unmapped HTTP method.
- Response missing a promised header.
- Cookie losing HttpOnly/SameSite.
- JSON field renamed or changed type.

Write tests against the intended contract rather than current buggy behavior if that behavior is wrong.

## 21. When to use consumeWith, returnResult, and StepVerifier?

### consumeWith

Use when the assertion DSL lacks what you need:

~~~java
client.get().uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .consumeWith(result -> {
        Product value = result.getResponseBody();
        assertNotNull(value);
        assertEquals("Keyboard", value.name());
    });
~~~

consumeWith provides ExchangeResult for custom assertions and can observe status/headers depending on overload, though avoid repeating assertions already directly expressible in WebTestClient when unnecessary.

### returnResult

When you want to obtain EntityExchangeResult after checking:

~~~java
EntityExchangeResult<Product> result = client.get()
    .uri("/api/products/p1")
    .exchange()
    .expectStatus().isOk()
    .expectBody(Product.class)
    .returnResult();

Product product = result.getResponseBody();
assertNotNull(product);
~~~

For SSE or NDJSON streaming, use returnResult(Event.class) to get FluxExchangeResult and consume the stream with StepVerifier. Do not use expectBodyList() to wait for an infinite stream to complete.

### Bounded stream example

~~~java
FluxExchangeResult<Event> result = client.get()
    .uri("/api/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(Event.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

This is an **illustrative fragment** for an /api/events API, and the Event class would need to be defined in a project that has a streaming endpoint. It is not in the demo CatalogController, so it is not a standalone test for the project above. Use StepVerifier when testing event timing, backpressure, cancellation, or publishers that do not complete on their own.

## 22. Common mistakes and fixes

1. **Checking only status 200.** JSON/headers can be wrong; add assertions for important contract parts.
2. **Using is2xxSuccessful when 201 is strictly required.** A 200 response goes undetected; use isCreated().
3. **Enforcing Content-Type as a raw string when charset does not matter.** Use contentTypeCompatibleWith if that is the contract.
4. **Checking only header exists.** It does not catch wrong values; use valueEquals/valueMatches.
5. **Using regex .*.** An overly broad regex does not check the actual format; require the contract prefix/pattern.
6. **Confusing request Cookie with response Set-Cookie.** cookie(...) and expectCookie(...) have different meanings.
7. **Checking only cookie value while omitting security attributes.** Use httpOnly/secure/sameSite/path/maxAge.
8. **Matching the full Set-Cookie string.** Order/Expires can vary; prefer CookieAssertions.
9. **Assuming Secure cookies work fully over HTTP tests.** Tests only verify headers; test browser behavior over HTTPS separately.
10. **Comparing JSON with String.equals.** Whitespace and key order make tests brittle; use json()/JSONPath.
11. **Using strict JSON for APIs with extensible fields.** Adding valid fields breaks tests; consider lenient or JSONPath.
12. **Using lenient JSON for closed contracts.** Extra fields can slip through; use strict when needed.
13. **Using isEqualTo("1200") for JSON numbers.** Wrong data type; assert numbers or target DTOs.
14. **Assuming missing fields are identical to null fields.** Use assertions that clearly express the schema distinction.
15. **Using expectBodyList for infinite SSE.** The test waits for completion that never arrives; use returnResult + StepVerifier.
16. **Forgetting bodyValue on POST.** Endpoints with @RequestBody can fail on empty input.
17. **Forgetting Content-Type on POST.** Can return 415; configure contentType(APPLICATION_JSON).
18. **Not @Importing or mocking dependencies in @WebFluxTest.** Controller beans cannot be created and tests fail to run; declare dependencies clearly.
19. **Running @SpringBootTest with a hardcoded port.** Prone to CI port collisions; use RANDOM_PORT.
20. **Using shared mutable data across tests.** Order-dependent failures; use immutable fixtures or reset state.
21. **Disabling Spring Security in tests needing authorization.** Tests may falsely return 200 when production returns 401/403; use proper security config.
22. **Hardcoding uncontrolled timestamps or UUIDs.** Reduce flakiness with an injected clock/ID generator or pattern checks.
23. **Checking only 404 status when the API has an error schema.** Consumers may need code/message; assert the right error JSON.
24. **Not distinguishing 204 and 200 with an empty body.** Check both status and isEmpty.
25. **Using server DTOs to replace all consumer-contract tests.** Can miss version compatibility issues across services.
26. **Writing tests for proxy headers while running a slice without a proxy.** Choose the right test layer; separate server behavior from deployment infrastructure.
27. **Calling production APIs in integration tests.** Risks mutating real data; use an embedded test server and dedicated fixtures.
28. **Ignoring meaningful test names and failure messages.** Test names should state the contract; avoid generic names like test1.

## 23. WebFlux response testing checklist

Before finalizing an API, check:

- Do route and HTTP method match the contract?
- Do requests have the right Accept and Content-Type?
- Is the success status 200/201/204 as required by business rules?
- For 201, is Location present if required by the contract?
- For 204, is the body actually empty?
- For GET, is Content-Type application/json or the promised media type?
- Are ETag, Cache-Control, and correlation IDs returned accurately and consistently?
- Are headers that must not appear genuinely absent?
- Do response cookies have the right name and value?
- Are Path, Domain, Max-Age, SameSite, Secure, and HttpOnly checked when needed?
- Do tests distinguish request cookies from Set-Cookie responses?
- Does the JSON body have the required fields and types?
- Are null fields and missing fields handled per contract?
- Does the JSON array have the right size and order when order matters?
- Is strict/lenient JSON comparison chosen deliberately?
- Are error statuses and JSON schemas tested for invalid input?
- Are 404, 405, 415, and other error conditions covered?
- Has @WebFluxTest imported/mocked required dependencies?
- When testing real networking/filters, is @SpringBootTest with RANDOM_PORT used?
- Are test fixtures immutable, deterministic, and independent of execution order?
- Are there separate WebSocket/SSE/NDJSON tests if the endpoint streams?
- Are assertions requiring browsers/CDNs/TLS tested in an appropriate environment?

## 24. Self-check exercises

**Question 1.** Which WebTestClient API checks HTTP status?  
**Answer:** expectStatus(), such as isOk(), isCreated(), or isNotFound().

**Question 2.** How does is2xxSuccessful() differ from isCreated()?  
**Answer:** is2xxSuccessful allows any 2xx status; isCreated matches only 201.

**Question 3.** When is contentTypeCompatibleWith used?  
**Answer:** When confirming the response has a compatible media type without enforcing every header parameter.

**Question 4.** How does valueMatches differ from exists?  
**Answer:** exists only confirms the header is present; valueMatches also checks a regex against the header value.

**Question 5.** Does cookie("language", "vi") check the response Set-Cookie?  
**Answer:** No; it sends a Cookie in the request. Use expectCookie to check the response.

**Question 6.** How do you check HttpOnly?  
**Answer:** expectCookie().httpOnly(cookieName, true).

**Question 7.** How do you check Secure and SameSite?  
**Answer:** expectCookie().secure(name, true) and sameSite(name, "Lax") or the contracted value.

**Question 8.** What does JSONPath "$[0].id" select?  
**Answer:** The id value of the first element if the JSON root is an array.

**Question 9.** What does json(expected, true) mean in Spring Framework 6.1?  
**Answer:** Strict JSON comparison, disallowing extra fields and requiring array ordering.

**Question 10.** If you only want to check $.id, what should you choose?  
**Answer:** expectBody().jsonPath("$.id").isEqualTo(...).

**Question 11.** Can WebTestClient decode JSON into a Java record?  
**Answer:** Yes, using expectBody(RecordType.class), then asserting its fields.

**Question 12.** Does @WebFluxTest automatically import all @Service beans?  
**Answer:** No. Use @MockBean or @Import for the needed dependencies.

**Question 13.** When is @SpringBootTest(webEnvironment=RANDOM_PORT) needed?  
**Answer:** When you want to test a larger application context and HTTP over a real embedded server.

**Question 14.** Why should 204 be paired with expectBody().isEmpty()?  
**Answer:** To protect both the status and the no-body condition.

**Question 15.** Why shouldn't you assert the entire raw Set-Cookie string?  
**Answer:** The ordering and formatting of certain attributes can change even with identical semantics.

**Question 16.** Does WebTestClient fully simulate browser cookie policies?  
**Answer:** No. It checks the HTTP response; browser behavior must be tested separately in an appropriate environment.

## 25. Takeaways

Testing WebFlux responses requires verifying four facets of the contract: **HTTP status, response headers, response cookies, and JSON body**. WebTestClient provides matching DSL methods: expectStatus(), expectHeader(), expectCookie(), and expectBody(). Never check only the status when headers, cookies, or body directly affect consumers.

For headers, prefer semantic checks such as contentTypeCompatibleWith, location, cacheControl, valueEquals, or valueMatches. For cookies, distinguish request cookies from response Set-Cookie, and verify Path, Max-Age, HttpOnly, Secure, and SameSite whenever security-relevant. For JSON, use JSONPath for specific fields, lenient json() for open contracts, strict json(..., true) for closed contracts, or expectBody(Class)/expectBodyList(Class) to verify decoded objects.

Choose @WebFluxTest for fast controller slices and @SpringBootTest with RANDOM_PORT when real HTTP integration is needed. Keep fixtures stable, independent of time/random IDs, and cover error cases. For streaming such as SSE, use returnResult and StepVerifier instead of waiting for the entire stream as a finite body.

### References

- Spring Framework, [WebTestClient — Binding and Assertions](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- Spring Framework 6.1 Javadoc, [WebTestClient](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html).
- Spring Framework 6.1 Javadoc, [HeaderAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/HeaderAssertions.html).
- Spring Framework 6.1 Javadoc, [CookieAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/CookieAssertions.html).
- Spring Framework 6.1 Javadoc, [JsonPathAssertions](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/JsonPathAssertions.html).
- Spring Framework 6.1 Javadoc, [WebTestClient.BodyContentSpec](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.BodyContentSpec.html).
- Spring Boot 3.3, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/features.html#features.testing).
- Spring Boot, [AutoConfigureWebTestClient](https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html).
