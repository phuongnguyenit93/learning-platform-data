# Recognizing API versioning support by Spring Framework version

## 1. Goal

API versioning is how an application maintains multiple versions of an **HTTP contract** during a transition period. Older clients continue sending requests per the old contract, while newer clients use the new request/response structure. For example, API 1.0 returns a simple status; API 2.0 adds currency or changes how status is represented.

What needs to be recognized in Spring WebFlux is that **built-in versioning capabilities depend on the Spring Framework version**:

- Spring Framework 5.x and 6.x allow building API versioning yourself using mapping conditions, filters, routers, or application logic. Those branches do not yet have a first-class API versioning suite like Framework 7.
- **Spring Framework 7.0 and later** adds built-in API versioning for both Spring MVC and Spring WebFlux. It includes resolver/parser/validation configuration, a `version` attribute on request mappings, a route predicate for functional endpoints, client support, and test support.
- Spring Framework 7.1 was in preview at the time this document was updated; in production you must use a stable release compatible with Spring Boot and the libraries in your project.

This lesson focuses on WebFlux. The native API versioning examples below require **Spring Framework 7.0+**. If the project is still on Framework 6.x, you cannot simply add the `version` attribute to `@GetMapping` and expect the framework to handle it automatically.

## 2. Distinguishing three kinds of "version"

In a Spring project, the word "version" can refer to different things:

1. **Spring Framework version:** the version of the underlying library, for example 6.2.19 or 7.0.10. It determines which APIs are available at compile time and runtime.
2. **Application/API version:** the version of the contract the server advertises to clients, for example API 1.0 and API 2.0. This is the version designed by the API development team.
3. **Resource/static asset version:** a version or hash in the URL of JavaScript, CSS, or images for cache busting, for example `/assets/app-8f3a.js`. `VersionResourceResolver` handles this category, not REST API versioning.

An application running Spring Framework 7.0.10 can serve API 1.0, 2.0, and 3.0 at the same time. There is no rule requiring the API numbers to match the Spring Framework number. Upgrading Spring Framework from 6.2 to 7.0 also does not automatically turn the application's API from v1 into v2.

## 3. Support matrix by Spring Framework

| Spring Framework | First-class API versioning in WebFlux | Can you version APIs with custom configuration? | How to recognize |
| --- | --- | --- | --- |
| 5.0–5.3 | No `ApiVersionConfigurer` and no `version` attribute on `@RequestMapping` | Yes, via path/header/query/media type, mapping conditions, or custom filters/routers | Must manage version resolution, validation, and deprecation yourself |
| 6.0–6.2 | Does not yet have Framework 7's built-in API versioning suite | Yes, via existing mapping and routing mechanisms | Cannot use native `configureApiVersioning` or `@GetMapping(version=...)` |
| 7.0.x | Yes, for MVC and WebFlux | Yes; prefer the native infrastructure when appropriate | Has `ApiVersionStrategy`, resolver/parser, mapping version, validation, and deprecation |
| 7.1.x | Inherits 7.0's native foundation; check stable/preview status before upgrading | Yes | Check release notes and compatibility of the version being used |

**The key milestone is 7.0.** The Javadoc of `ApiVersionConfigurer` explicitly notes that this API was introduced in Spring Framework 7.0. The 7.0 release notes also confirm first-class support for API versioning in MVC and WebFlux.

At the time this lesson was updated (2026-11-08), Spring documentation lists Framework 7.0.10 as the stable release and 7.1.0-RC2 as a preview release. Patch numbers change over time; check the official release/version page before choosing dependencies.

### 3.1. Why can Framework 6.x still version APIs?

Versioning is not a capability unique to Spring. An HTTP request already has a path, query string, headers, and media types. Spring Framework 6.x has mapping conditions such as:

- `path`: creates separate routes such as `/api/v1/orders` and `/api/v2/orders`.
- `headers`: matches only when a header has a given value.
- `params`: matches only when a query parameter has a given value.
- `produces`: selects a handler according to the media type the client accepts.

These mechanisms are enough to build versioned routing. What is missing is **a shared version management suite**: standardizing how versions are extracted, parsing and comparing versions, validating the list of supported versions, applying defaults, selecting mappings by baseline, emitting deprecation notices, and configuring matching support for clients/tests.

That is the difference between "being able to implement API versioning yourself" and "the Framework having first-class API versioning".

## 4. What does native API versioning in Framework 7.0 include?

Framework 7.0 adds components that work together:

| Component | Role |
| --- | --- |
| `ApiVersionStrategy` | Coordinates how versions are resolved, parsed, validated, and deprecation is notified |
| `ApiVersionResolver` | Extracts the version value from the request |
| `ApiVersionParser` | Converts a version string into a comparable form |
| `ApiVersionConfigurer` | Configures the resolver, parser, default, and supported versions |
| `ApiVersionDeprecationHandler` | Sends deprecated version information via response headers |
| `@RequestMapping(version=...)` | Selects an annotated controller method by version |
| `version(...)` predicate | Selects a functional route by version |

Applications usually configure this via `WebFluxConfigurer.configureApiVersioning(...)` or Spring Boot properties. Once configured, `ApiVersionStrategy` is used by WebFlux during request mapping. Most controllers do not need to call the strategy themselves.

Native support applies to:

- Annotated controllers: `@RequestMapping`, `@GetMapping`, `@PostMapping`, and other specialized annotations.
- Functional endpoints: `RouterFunction` with the `version(...)` request predicate.
- Clients: `WebClient`, `RestClient`, and HTTP Service clients.
- Testing: `WebTestClient`; Spring MVC also has corresponding support in MockMvc.

## 5. Choosing where to place the API version in the request

There is no single HTTP standard forcing every API to place the version in the same location. Framework 7.0 has built-in resolvers:

| Delivery method | Example request | WebFlux configuration | Characteristics |
| --- | --- | --- | --- |
| Header | `X-API-Version: 2.0` | `useRequestHeader("X-API-Version")` | URL does not change; caches/proxies must be configured to account for the version header |
| Query parameter | `?apiVersion=2.0` | `useQueryParam("apiVersion")` | Easy to try with browser/curl; version appears in URL and cache key |
| Path segment | `/api/v2/orders/42` | `usePathSegment(index)` | Easy to read, easy to route/cache; version becomes part of the URL |
| Media type parameter | `Accept: application/json;version=2.0` | `useMediaTypeParameter(...)` | Ties the version to the representation; client and content negotiation are more complex |
| Custom resolver | Per the application's contract | `useVersionResolver(...)` | Used when the rule for extracting the version is specialized |

### 5.1. Version in a header

Example:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
X-API-Version: 2.0
Accept: application/json
```

Headers fit when you want to keep a stable URL and treat the version as metadata of the API contract. When using a CDN, reverse proxy, or HTTP cache, ensure the cache key accounts for the version header; otherwise, a v1 response could be mistakenly served for a v2 request.

### 5.2. Version in the path

Example:

```http
GET /api/v2/orders/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

For the path resolver, you specify the 0-based index of the segment containing the version. The path must declare a URI variable, for example `/api/{version}/orders`. If the path segment does not exist or is invalid, the resolver may throw `InvalidApiVersionException`. You can configure a predicate to determine which paths actually carry a version.

Path versioning is easy to observe and cache, but requires URL planning and can create multiple public routes for the same resource.

### 5.3. Version in a query parameter

Example:

```http
GET /api/orders/42?apiVersion=2.0 HTTP/1.1
```

Query parameters are convenient for testing and simple clients. However, you must keep the parameter name consistent, handle clients sending multiple values, and ensure proxies/caches do not ignore the parameter when forming cache keys.

### 5.4. Version in a media type parameter

Example:

```http
GET /api/orders/42 HTTP/1.1
Accept: application/json;version=2.0
```

This expresses that the client wants a specific version of the representation. Configuring the resolver specifies the compatible media type and parameter name. Do not confuse a version parameter with a separate MIME subtype such as `application/vnd.example.order-v2+json`; the two strategies can appear together, but they are two different contracts.

### 5.5. When is a custom resolver needed?

If the version comes from a standardized gateway header, a token claim, or a special routing rule, you can implement `ApiVersionResolver`. The resolver should:

- Return a clear version value or a no-version state according to the contract.
- Not query the database or make blocking network calls when resolving a request.
- Handle missing/invalid values according to a consistent rule.
- Not trust version data as authentication or authorization information.
- Be tested for valid requests, missing versions, and unsupported versions.

If multiple resolvers are configured, resolver order matters. When combining a header and a query parameter, configure the order explicitly in Java config rather than assuming an order from multiple independent properties.

## 6. Configuring API versioning in Spring WebFlux 7.0

### 6.1. Configuring with WebFluxConfigurer

Example using a request header:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.ApiVersionConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiVersioningConfiguration implements WebFluxConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("X-API-Version");
        configurer.addSupportedVersions("1.0", "2.0");
    }
}
```

Key points to understand:

- `configureApiVersioning` is a callback added in Framework 7.0.
- `useRequestHeader` selects the header used to resolve the version.
- `addSupportedVersions` declares accepted versions.
- By default, the Framework can auto-detect versions declared in controller mappings. If you want to use only an explicitly declared list of versions, you can disable mapping-based version detection with `detectSupportedVersions(false)` and then declare the supported list.
- When a version resolver is enabled, a request version is required by default. This can be changed with a default version or required configuration per the Framework 7.0 API.

There is no need to call `ApiVersionStrategy` directly in each controller. Let the WebFlux configuration manage the shared strategy.

### 6.2. Configuring with Spring Boot properties

In Spring Boot with Framework 7 API versioning integration, you can configure with properties:

```properties
spring.webflux.apiversion.use.header=X-API-Version
```

If you want requests missing the header to use a default version:

```properties
spring.webflux.apiversion.default=1.0
spring.webflux.apiversion.use.header=X-API-Version
```

YAML equivalent:

```yaml
spring:
  webflux:
    apiversion:
      default: 1.0
      use:
        header: X-API-Version
```

Spring Boot also has properties for the query parameter, path segment, and media type parameter resolvers. If you need multiple resolvers or a custom order, use `WebFluxConfigurer`.

**Compatibility note:** the `spring.webflux.apiversion.*` properties belong to Spring Boot configuration supporting Framework 7's API versioning. Do not copy these properties into a Boot 3.x project managing Framework 6.x and expect them to work automatically; check the dependency tree and documentation for the right Boot version.

### 6.3. Choosing default and required version

When API versioning is enabled:

- By default, a request needs to supply a version; if missing, the Framework throws `MissingApiVersionException` and returns 400.
- A default version can be configured so requests that do not send a version are assigned a default value.
- Requests without a version can be allowed; in that case, design unversioned mappings and version-specific mappings so the outcome is unambiguous.
- If using a default, state the default version explicitly in the API contract and client documentation.

Do not arbitrarily use the latest version as the default just because it is newer. Older clients without the header might unexpectedly receive a changed representation. A stable default or requiring clients to send the version explicitly is usually easier to control.

## 7. Mapping controller methods by version

After enabling the resolver, you can declare `version` on `@RequestMapping` or specialized annotations.

### 7.1. Fixed version

Example of two methods on the same path:

```java
@GetMapping(path = "/{id}", version = "1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    return Mono.just(new OrderV1(id, "PAID"));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}
```

Both methods handle the same path, yet are selected only when the request version matches. This is suitable when version 2 has a different representation or semantics from version 1.

### 7.2. Baseline version

A mapping with version `1.2+` is a **baseline mapping**: it supports version 1.2 and higher versions within the supported versions set, until a more specific mapping is selected.

Example:

```java
@GetMapping(path = "/{id}", version = "1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    return Mono.just(new OrderV1(id, "PAID"));
}

@GetMapping(path = "/{id}", version = "1.2+")
public Mono<OrderV2> getFromV1_2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}
```

A baseline helps one method continue serving newer versions when the contract remains compatible, reducing the need to duplicate controller methods for every version.

Remember that a baseline does not automatically make every version number valid. The request version must still be in the set of supported versions per the configuration or mappings.

### 7.3. Mappings without a declared version

A method without a `version` attribute is considered able to match any version, but will have lower priority than a version-specific mapping. This is a way to keep an endpoint compatible with older clients while a new-version handler already exists.

Conceptual example:

```java
@GetMapping("/{id}")
public Mono<LegacyOrder> getLegacy(@PathVariable String id) {
    return Mono.just(loadLegacyOrder(id));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(loadOrderV2(id));
}
```

This is illustrative code; the load functions are defined by the application. If the request is version 2.0, the specific 2.0 mapping takes priority. For an unversioned request, the result also depends on the required/default configuration; test explicitly rather than guessing.

### 7.4. How the Framework selects a mapping

| Declared mapping | Request version | Result |
| --- | --- | --- |
| `1.0` | `1.0` | Match fixed version 1.0 |
| `1.0` | `2.0` | No match |
| `1.2+` | `1.2` | Match baseline |
| `1.2+` | `1.5` | Matches if 1.5 is a supported version |
| No version declared | Any version | Can match, but is superseded by a specific mapping |
| `2.0` and `1.2+` | `2.0` | The specific fixed 2.0 mapping takes priority |
| Only `1.2+` | `1.1` | Does not match the baseline |
| Higher fixed version exists, but request exceeds that version | For example, request 1.6 while highest fixed mapping is 1.5 and a lower baseline exists | May have no suitable mapping; Framework returns an unacceptable version error |

Detailed example per Framework docs: if mappings have version 1.1, baseline 1.2+, and fixed 1.5, a request for 1.3 selects baseline 1.2+; a request for 1.5 selects fixed 1.5. A request for 1.6 does not automatically fall back to baseline 1.2+ because the fixed 1.5 mapping has higher priority yet does not match the request. Therefore, design the set of mappings and supported versions deliberately.

## 8. Semantic version parser and validation

### 8.1. Parsing versions for accurate comparison

By default, the Framework uses a semantic version parser. A version is split into major, minor, and patch for numeric comparison, rather than lexicographical string comparison.

| Version A | Version B | Comparison result |
| --- | --- | --- |
| `1.2` | `1.10` | 1.2 is less than 1.10 |
| `2.0` | `1.9.9` | 2.0 is greater than 1.9.9 |
| `1.2` | `1.2.0` | Missing component is treated as 0 by the semantic parser |
| `2.0.1` | `2.0` | 2.0.1 is greater than 2.0 |

Do not use `String.compareTo` to decide versions yourself if the version has numeric components. String comparison can give wrong results, for example the string "1.10" comes before "1.2" in lexicographical order.

### 8.2. Date-based or custom-format versions

If an organization uses date-based versions such as `2026-11`, or a custom rule, a custom `ApiVersionParser` can be configured. The parser must produce a type with a consistent comparison order and handle invalid input.

Do not switch the parser to a custom format just to accommodate one client. Pick a simple format, document it clearly in the API documentation, and keep it stable over time.

### 8.3. How are supported versions determined?

By default, the Framework can derive versions from the values declared in controller mappings. This is convenient when versions 1.0 and 2.0 appear directly in the mappings.

If you want an explicit list of supported versions:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("X-API-Version");
    configurer.detectSupportedVersions(false);
    configurer.addSupportedVersions("1.0", "2.0", "2.1");
}
```

Once auto detection is turned off, the explicit list must be complete. If an initial version is not yet declared in a mapping but is used as a default, add it to supported versions via the appropriate configuration.

### 8.4. Missing, invalid, or unmapped version errors

Important cases:

- Version not sent when version is required: `MissingApiVersionException`, usually HTTP 400.
- Sending an unsupported version: `InvalidApiVersionException`, HTTP 400.
- Valid version with no compatible mapping: may receive `NotAcceptableApiVersionException`, HTTP 400.
- Sending a valid version with a matching mapping: the appropriate controller method is invoked.

Distinguish version errors from business errors. An unsupported API version is a contract/routing error, not a 404 "resource does not exist" error.

## 9. Deprecation and version lifecycle

Versioning is not just keeping multiple controller methods. An API also needs a policy for announcing and retiring old versions.

Framework 7.0 provides `ApiVersionDeprecationHandler`. The default handler `StandardApiVersionDeprecationHandler` can add response headers:

- `Deprecation`: announces that the version is deprecated.
- `Sunset`: information on when the version is expected to be retired.
- `Link`: link to documentation or migration guide.

The headers are described in RFC 9745 (Deprecation) and RFC 8594 (Sunset). Applications can configure a custom handler if a different schema or policy is needed.

An operational process should include these steps:

1. Release the new version and maintain the old version during the transition period.
2. Mark the old version deprecated once a retirement plan is in place.
3. Send deprecation/sunset information in responses so clients can migrate proactively.
4. Monitor request counts per version and which clients are still using it.
5. Announce the end-of-support schedule via appropriate documentation/channels.
6. Remove the old mapping only after assessing impact and completing the compatibility policy.

Do not attach deprecation headers just "to try them out for fun". The sunset date must reflect a real commitment by the operations team.

## 10. Functional endpoints in WebFlux

API versioning is not only for annotated controllers. For functional endpoints, after configuring WebFlux versioning, you can add the `version(...)` predicate to routes:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.RequestPredicates.version;

@Configuration(proxyBeanMethods = false)
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return route()
                .GET("/api/orders/{id}", version("1.0"), handler::getV1)
                .GET("/api/orders/{id}", version("2.0"), handler::getV2)
                .build();
    }
}
```

This is an illustrative route configuration; `OrderHandler` needs to provide two methods returning `Mono<ServerResponse>` accordingly. The version predicate supports fixed versions such as 1.2 and baselines such as 1.2+.

Crucial point: you must enable API versioning in WebFlux Config first. Without an ApiVersionStrategy, the version predicate cannot resolve the request version according to the contract you want.

## 11. Client support and testing

### 11.1. WebClient and RestClient

Framework 7.0 provides `ApiVersionInserter` so clients know how to attach the version to requests. For example, WebClient can configure an inserter using a header once, after which requests only need to specify the version to call.

Concept:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://localhost:8080")
        .apiVersionInserter(
                ApiVersionInserter.useHeader("X-API-Version"))
        .build();
```

The client then calls the API with the corresponding version using API version client support. `RestClient` and HTTP Service clients have similar support. The client-side resolver name should match the server-side contract.

If not using an API inserter, the client can still set the header/query/path manually. The inserter helps avoid repeating version-setting logic on each request.

### 11.2. WebTestClient

In WebFlux tests, you can send the version via a header to verify each mapping. Example:

```java
client.get()
        .uri("/api/orders/42")
        .header("X-API-Version", "1.0")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("PAID");
```

When using an ApplicationContext setup, WebTestClient can use the context's API versioning configuration. If testing in a standalone setup, you need to provide an ApiVersionStrategy and configure an appropriate client inserter. Do not assume the test client automatically knows how to add the version unless configured.

### 11.3. Test scenarios to include

- Version 1.0 invokes the right handler and returns the right response schema.
- Version 2.0 invokes the right handler and returns the new field.
- A request missing the version returns the status per the required/default policy.
- An unsupported version is rejected.
- A valid version with no compatible mapping is handled properly.
- Baseline mappings work with each supported version.
- An unversioned mapping does not accidentally shadow a version-specific mapping.
- Deprecation headers appear properly for marked versions.
- WebClient/HTTP Service clients send the right header/query/path.
- WebTestClient tests both valid versions and version errors.

## 12. Complete Spring Boot WebFlux example with Framework 7.0+

The following example uses Java 17+, Spring Boot 4.x compatible with Spring Framework 7.0+, and the API version is passed via the `X-API-Version` header. The project needs no database; illustrative data is created in the controller.

### 12.1. Dependency

Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The project needs the Spring Boot plugin and appropriate dependency management. Use Boot 4.x's BOM to select Spring Framework 7.x consistently; do not override `spring-webflux` individually to a different version from Framework core.

### 12.2. Configuring application.properties

File `src/main/resources/application.properties`:

```properties
spring.webflux.apiversion.use.header=X-API-Version
```

This configuration makes the `X-API-Version` header the source of the request version. Once the resolver is enabled, a version is required by default if no default is configured.

### 12.3. Application class

File `src/main/java/demo/ApiVersioningApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiVersioningApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiVersioningApplication.class, args);
    }
}
```

### 12.4. Controller with two versions

File `src/main/java/demo/OrderController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(path = "/{id}", version = "1.0")
    public Mono<OrderV1> getV1(@PathVariable String id) {
        return Mono.just(new OrderV1(id, "PAID"));
    }

    @GetMapping(path = "/{id}", version = "2.0")
    public Mono<OrderV2> getV2(@PathVariable String id) {
        return Mono.just(new OrderV2(id, "PAID", "VND"));
    }

    public record OrderV1(String id, String status) {
    }

    public record OrderV2(
            String id,
            String status,
            String currency) {
    }
}
```

Both methods handle the `/api/orders/{id}` path. A version 1.0 request receives the `OrderV1` representation; a version 2.0 request receives `OrderV2` with an added currency. Both methods return Mono, so the controller still complies with WebFlux reactive return types.

### 12.5. Testing with WebTestClient

File `src/test/java/demo/OrderControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(
        controllers = OrderController.class,
        properties = "spring.webflux.apiversion.use.header=X-API-Version")
class OrderControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void version10SelectsV1Representation() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "1.0")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.status").isEqualTo("PAID")
                .jsonPath("$.currency").doesNotExist();
    }

    @Test
    void version20SelectsV2Representation() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "2.0")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.status").isEqualTo("PAID")
                .jsonPath("$.currency").isEqualTo("VND");
    }

    @Test
    void missingVersionIsRejected() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unsupportedVersionIsRejected() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "3.0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

The test uses the ApplicationContext WebFlux test slice and the property version resolver. No real server needs to be started. Run with:

```bash
./gradlew test
```

If the project enables Spring Security or has custom filters, configure the test slice accordingly so those filters do not mask the results of API version mapping.

### 12.6. Calling with curl

Start the application:

```bash
./gradlew bootRun
```

Request version 1.0:

```bash
curl -i -H "X-API-Version: 1.0" http://localhost:8080/api/orders/42
```

Main JSON body:

```json
{
  "id": "42",
  "status": "PAID"
}
```

Request version 2.0:

```bash
curl -i -H "X-API-Version: 2.0" http://localhost:8080/api/orders/42
```

Main JSON body:

```json
{
  "id": "42",
  "status": "PAID",
  "currency": "VND"
}
```

Requests that do not send the header or send unsupported version 3.0 will receive HTTP 400 under the example configuration.

## 13. Doing API versioning on Framework 6.x

If the project is on Spring Framework 6.x, you can still version endpoints using existing mapping conditions. Example using headers:

```java
@RestController
@RequestMapping("/api/orders")
public class LegacyOrderController {

    @GetMapping(path = "/{id}", headers = "X-API-Version=1.0")
    public Mono<OrderV1> getV1(@PathVariable String id) {
        return Mono.just(new OrderV1(id, "PAID"));
    }

    @GetMapping(path = "/{id}", headers = "X-API-Version=2.0")
    public Mono<OrderV2> getV2(@PathVariable String id) {
        return Mono.just(new OrderV2(id, "PAID", "VND"));
    }
}
```

This is a way to route manually by header value. Other variants:

```java
@GetMapping(path = "/{id}", params = "apiVersion=1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    // ...
}

@GetMapping(path = "/{id}", params = "apiVersion=2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    // ...
}
```

Or separate URLs:

```java
@GetMapping("/v1/orders/{id}")
public Mono<OrderV1> getV1(@PathVariable String id) {
    // ...
}

@GetMapping("/v2/orders/{id}")
public Mono<OrderV2> getV2(@PathVariable String id) {
    // ...
}
```

The snippets above are routing patterns, with business bodies omitted. On Framework 6.x, these mappings can work, but there is **no** native `version` attribute on `@RequestMapping` or `configureApiVersioning` callback.

### 13.1. What must be managed manually on 6.x

If implementing it yourself, the application needs to decide and control:

- A resolver to extract the version from header, query, path, or media type.
- A parser and version comparison rules; avoid wrong string comparisons.
- The list of supported versions and behavior for missing/invalid versions.
- Baseline mappings and fallbacks for older clients.
- Default version and deprecation policy.
- Response headers announcing deprecation/sunset.
- Client helpers to send the right version.
- Test cases for every version, missing, unsupported, and mapping conflicts.

Logic can be centralized into a WebFilter, custom HandlerMapping/RequestCondition, router predicate, or a dedicated library. However, do not scatter header/version parsing logic across individual controllers because it easily becomes inconsistent.

### 13.2. Why not override Framework 7 into a Boot 3 project?

Spring Boot manages a compatible set of dependencies. Boot 3.x is built on Spring Framework 6.x generations; native API versioning requires Framework 7.0+. Overriding only the `spring-webflux` or `spring-web` dependency to 7.0 while other Spring modules remain 6.x can create an incompatible classpath and runtime errors.

If you want native support, upgrade along a supported Spring Boot/Framework version suite together. If you cannot upgrade yet, keep a manual routing solution on Framework 6.x and write thorough tests.

## 14. Common mistakes when recognizing version support

| Misconception | Reality | How to handle |
| --- | --- | --- |
| Thinking Framework 6.2 has `@GetMapping(version=...)` | The mapping version attribute belongs to Framework 7.0+ | Check the Spring Framework dependency before using |
| Thinking API versioning exists only in MVC | Framework 7.0 supports both MVC and WebFlux | Use WebFluxConfigurer for the reactive stack |
| Thinking just adding a header makes the Framework understand versions | A resolver must be configured first | Configure ApiVersionConfigurer or a Boot property |
| Thinking any string version is accepted | The Framework validates supported versions | Declare mappings or a supported list |
| Thinking baseline 1.2+ accepts every future version automatically | The version must be in the supported versions set and a mapping must fit | Manage supported versions and test version boundaries |
| Thinking an omitted version always uses the latest version | Behavior depends on required/default/mapping | Configure default or required explicitly |
| Thinking `@RequestMapping(version=...)` replaces path/header/query | Mapping version works only after the resolver knows where to extract the version | Configure strategy and mapping together |
| Using non-numeric-order version strings | Comparisons can be wrong | Use the semantic parser or a custom parser |
| Using an API version to represent every deploy | Creates unnecessary versions | Increment the version only when contract changes require separate compatibility |
| Treating the API version as the Spring library version | The two versions are independent | State Framework version and API version clearly in docs |
| Thinking `VersionResourceResolver` is REST API versioning | It versions static resource URLs/caches | Use ApiVersionStrategy for the API contract |
| Enabling multiple resolvers without defining precedence | May resolve versions from different sources unexpectedly | Configure the order via Java config |
| Upgrading Framework individually inside old Boot | Can mismatch Spring module versions | Upgrade via BOM/compatibility matrix |

## 15. Checklist when upgrading or designing API versioning

1. **Check the real version:** inspect the dependency tree or BOM to see whether Spring Framework/WebFlux is running on 5.x, 6.x, or 7.x.
2. **Check native APIs:** use `ApiVersionConfigurer` and `@RequestMapping(version=...)` only when the project has Framework 7.0+.
3. **Choose a resolver:** header, query, path, media type, or custom; document the contract clearly for clients.
4. **Choose a parser:** default semantic version or custom format; do not compare strings arbitrarily.
5. **Declare supported versions:** use auto detection from mappings or an explicit list.
6. **Decide missing version:** required or default; do not let older clients be switched to a new contract unexpectedly.
7. **Design mappings:** fixed version, baseline, and unversioned fallback; test mapping precedence.
8. **Establish a deprecation policy:** notify clients, sunset time, Link, and measure request volume still using old versions.
9. **Configure clients:** WebClient, RestClient, and HTTP Service clients must send the version matching the resolver.
10. **Test:** valid versions, missing, unsupported, baseline, no-match, deprecation, and content contract.
11. **Check caches/proxies:** if the version is in a header, ensure cache keys distinguish versions.
12. **Upgrade together:** use compatible Spring Boot/Framework versions; do not swap only a single JAR.

## 16. Official references

- [Spring Framework 7.0 – API Versioning in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-versioning.html): ApiVersionStrategy, resolver, parser, validation, and deprecation.
- [Spring Framework 7.0 – WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring `configureApiVersioning`, resolver, and supported versions.
- [Spring Framework 7.0 – Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): the `version` attribute, fixed version, baseline version, and how mapping selection works.
- [Spring Framework 7.0 – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `version(...)` predicate for RouterFunction.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): the `spring.webflux.apiversion.*` properties and WebFlux versioning configuration.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): confirming first-class API versioning for MVC and WebFlux.
- [Spring Framework 6.2 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes): comparing changes in the 6.2 branch.
- [API Versioning in Spring](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): reasons for adding the feature, server/client/testing support, and overview examples.
- [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): stable branches, support timelines, and upgrade paths.

## 17. Key takeaways

**Native API versioning in Spring WebFlux starts in Spring Framework 7.0.** On Framework 7.0+, configure the resolver with `WebFluxConfigurer.configureApiVersioning` or Boot properties, then use `@RequestMapping(version=...)` for annotated controllers or `version(...)` for functional routes. The Framework supports resolving, parsing, validating, supported versions, client integration, WebTestClient, and deprecation announcements.

On Framework 5.x/6.x, you can still version APIs by path, header, query parameter, or media type using existing mapping conditions; the application must manage version rules, validation, fallback, and deprecation itself. Do not confuse the Spring Framework version with the application API version. Check the real dependencies before choosing an implementation approach, and upgrade the Framework only as part of a compatible Spring Boot/BOM suite.
