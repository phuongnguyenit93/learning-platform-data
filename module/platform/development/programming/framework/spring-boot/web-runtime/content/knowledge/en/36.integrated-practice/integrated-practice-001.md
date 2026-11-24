# Building an MVC REST API with Server Configuration, Validation, and Consistent Errors

A Spring Boot REST API that simply runs with `@RestController` is only the starting point. For an application to be testable, deployable, maintainable, and ready to serve real clients, you need to align **HTTP server configuration**, **resource/HTTP method design**, **DTOs and Bean Validation**, **structured error handling**, **request correlation**, and **end-to-end contract testing** at the same time.

This integrated practice guide walks through building a **product management REST API** with **Java 17+, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, Jakarta Bean Validation, and RFC 9457 Problem Details**. No database is needed to run the lab: the repository is synchronized in-memory to demonstrate the HTTP contract and application flow. From there, we move on to how to apply it with a database, Spring Security, a reverse proxy, Kubernetes, and production.

**Final result:** The API exposes `GET /api/v1/products`, `POST /api/v1/products`, `GET /api/v1/products/{id}`, `PUT /api/v1/products/{id}`, and `DELETE /api/v1/products/{id}`. Valid commands create/list/update/delete; invalid commands produce the same error shape:

```http
HTTP/1.1 400
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "Invalid input data.",
  "instance": "/api/v1/products",
  "code": "VALIDATION_FAILED",
  "requestId": "550e8400-e29b-41d4-a716-446655440000",
  "errors": [
    { "field": "name", "rule": "NotBlank" },
    { "field": "price", "rule": "DecimalMin" }
  ]
}
```

The response only **illustrates the structure**; the UUID and list of violations vary per request, and JSON field order is not a required contract. The `errors` entries do not include `rejectedValue` or the raw request body to avoid echoing sensitive data into the HTTP error response.

**Important point:** depending on configuration, errors from the container, security filters, reverse proxy, or serialization that occur outside MVC advice may have a different representation. This practice unifies **errors handled by Spring MVC/the application** and explains how to extend the policy at other layers, without promising that a single `@RestControllerAdvice` controls every byte of every response in a distributed system.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the request path: Tomcat → Servlet filters → DispatcherServlet → HandlerMapping → controller → service → exception resolver → HTTP response.
2. Choose appropriate status codes: 200, 201, 204, 400, 404, 405, 409, 415, and 500.
3. Create Java `record` DTOs with `@NotBlank`, `@Size`, `@Pattern`, `@DecimalMin`, `@Digits`, `@NotNull`, `@Min`, and `@Max`.
4. Enable real validation using `spring-boot-starter-validation` and `@Valid @RequestBody`.
5. Use `ResponseEntity` to control `Location`, status, body, and headers.
6. Distinguish JSON syntax errors, field validation errors, URL data type errors, and business conflicts.
7. Write a `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` to unify Spring MVC errors with `ProblemDetail`.
8. Return stable machine-readable error codes such as `VALIDATION_FAILED`, `PRODUCT_NOT_FOUND`, `SKU_ALREADY_EXISTS`, and `INVALID_JSON`.
9. Add a server-side request ID using `OncePerRequestFilter`, return `X-Request-ID`, and include the ID in error bodies.
10. Configure `server.port`, `server.address`, `server.shutdown`, `server.compression`, `server.error.*`, and resource mapping.
11. Distinguish local loopback lab configuration from Docker/Kubernetes deployments and trusted proxy headers.
12. Test CRUD, validation, duplicates, malformed JSON, unsupported media type, unsupported method, and unknown routes using `MockMvc`.
13. Test real HTTP over `RANDOM_PORT` and `TestRestTemplate`.
14. Recognize the limits of an in-memory repository, security, concurrency, idempotency, and optimistic locking.
15. Take the API to production with a checklist covering timeouts, observability, data durability, and versioning.

## 2. Designing the HTTP Contract Before Writing Code

The API uses the collection resource `/api/v1/products` and individual resource `/api/v1/products/{id}`. Main outcomes:

| Method | URL | Purpose | Success | Common Errors |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/products` | List products | 200 and `[]`/JSON array | 500 internal |
| POST | `/api/v1/products` | Create product | **201** + `Location` + JSON | 400, 409, 415 |
| GET | `/api/v1/products/{id}` | Get by ID | 200 + JSON | 400 malformed ID, 404 missing |
| PUT | `/api/v1/products/{id}` | Replace entire editable representation | 200 + JSON | 400, 404, 409, 415 |
| DELETE | `/api/v1/products/{id}` | Delete product | **204** no body | 400/404 |
| PATCH | Not supported | Partial update | Not implemented | **405** Method Not Allowed |

You do not necessarily return 201 for a PUT that replaces an existing resource. For this lab, PUT **only updates an existing ID** and returns 404 if it does not exist. DELETE for a missing ID returns 404 per lab policy; many production APIs may choose idempotent DELETE 204 even when the resource is already gone, but this must be documented and kept consistent.

### 2.1. Valid Payload

```json
{
  "name": "Mechanical keyboard",
  "sku": "KEY-001",
  "price": 129.90,
  "stock": 12
}
```

`name` is a non-blank string, 2..100 characters long. `sku` is a code of 3..32 characters allowing only ASCII uppercase A–Z, digits 0–9, and hyphens. `price` is a positive decimal of at least 0.01 with at most 10 integer digits and 2 fractional digits. `stock` is an integer 0..100000.

**The API does not trust the client to send an ID to create a product.** The ID is assigned by the server and returned in the `id` field along with `Location`. Unit price uses `BigDecimal` instead of `double` to avoid binary floating-point rounding errors in monetary calculations. The demo product has no currency; production must define currency, rounding rules, tax, precision, and price change rules.

### 2.2. Distinguishing Client Errors and Server Errors

- **400 Bad Request:** Malformed JSON syntax, invalid DTO, path variable cannot be converted to `long`.
- **404 Not Found:** Product ID is syntactically valid but does not exist; or no MVC route matches.
- **405 Method Not Allowed:** The URL exists but the HTTP method is not supported; preserve the `Allow` header if provided by the framework.
- **409 Conflict:** The SKU already exists, violating uniqueness in the current state.
- **415 Unsupported Media Type:** POST/PUT requires JSON, but the client sent `text/plain` or another media type.
- **500 Internal Server Error:** Unexpected server-side failure; never return stack traces, SQL, input JSON, or raw exception messages to the client.

**Do not conflate 404 and 400**: `/api/v1/products/abc` matches the route pattern, but `abc` cannot be converted to long (400); `/api/v1/products/123` converts cleanly, but does not exist (404).

### 2.3. A Single Error Contract

Use **RFC 9457 Problem Details** instead of inventing an ad-hoc JSON structure with only `success:false`. Standard fields:

| Field | Meaning |
| --- | --- |
| `type` | URI identifying the problem type; defaults to `about:blank` |
| `title` | Short, potentially stable summary title |
| `status` | HTTP status code |
| `detail` | Short explanation, safe to display |
| `instance` | URI identifying the specific occurrence, may be the request path |
| `code` | Application-added extension for client branching |
| `requestId` | Extension for correlation with server-side logs |
| `errors` | Optional extension listing field/constraint violations, without rejected values |

Clients should branch logic on **HTTP status + `code`**; do not parse the `detail` text because it may change or be localized. The status inside the body does not replace the actual HTTP status. `ProblemDetail` is serialized by Spring/Jackson with content type `application/problem+json` when handled properly.

## 3. Spring MVC Processing Flow in the Demo

```text
HTTP client
    |
    v
Embedded Tomcat :8080
    |
    v
RequestIdFilter
  generate UUID + X-Request-ID + request attribute
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping selects ProductController
    |         |
    |         v
    |    Jackson reads JSON -> ProductInput record
    |         |
    |         v
    |    Bean Validation (@Valid)
    |         |
    |         v
    |    ProductCatalog (in-memory synchronized)
    |         |
    |         v
    |    ResponseEntity / Jackson serialization
    |
    +--> On error: ExceptionHandlerExceptionResolver
                   |
                   v
          ApiErrorHandler (ProblemDetail)
                   |
                   v
         application/problem+json
    |
    v
HTTP response
```

The filter in the demo **does not read the request body**, and does not log Authorization/Cookie or raw query strings. Generating `X-Request-ID` in the filter lets clients report errors with a server-generated random ID. DTO validation runs after HTTP JSON has been successfully deserialized into a Java object. If the JSON cannot be parsed, `@Valid` never gets a chance to run; the error is handled in `handleHttpMessageNotReadable`.

### 3.1. Spring MVC Is Not WebFlux

This lab uses `spring-boot-starter-web` and `jakarta.servlet.*`. Moving to Spring WebFlux uses `ServerWebExchange`, `WebExceptionHandler` or `@RestControllerAdvice` for the reactive stack, `WebTestClient`, and Reactor semantics; do not copy `OncePerRequestFilter`/`MockMvc` verbatim into WebFlux.

### 3.2. Do Not Catch Exceptions in Every Controller

Anti-pattern:

```java
// Anti-pattern: produces multiple inconsistent response formats.
try {
    return service.create(request);
} catch (Exception e) {
    return Map.of("error", e.getMessage());
}
```

This approach easily returns 200 for errors because no status is set, leaks exception messages, and leaves endpoints with inconsistent error schemas. Controllers should express the business action and let `@RestControllerAdvice` translate exceptions into HTTP errors.

## 4. Creating a Runnable Project with Java 17 and Spring Boot 3.3

Use [Spring Initializr](https://start.spring.io/) and select:

- Build: **Gradle, Groovy DSL**;
- Language: **Java**;
- Spring Boot: **3.3.x**, e.g., `3.3.13`;
- Java: **17+**;
- Dependencies: **Spring Web**, **Validation**, **Spring Boot Actuator**;
- Test: `spring-boot-starter-test`.

When initializing a project with Initializr, the Gradle Wrapper (`gradlew`, `gradlew.bat`, and `gradle/wrapper/*`) is generated. If you only copy Gradle files into an empty directory without a wrapper, generate the wrapper with a compatible Gradle installation or use Initializr.

### 4.1. settings.gradle

```groovy
rootProject.name = 'catalog-api-lab'
```

### 4.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Commonly forgotten point:** `spring-boot-starter-web` alone is not enough to guarantee Jakarta Bean Validation runs; you need `spring-boot-starter-validation`. With Boot 3.x, the annotation packages are `jakarta.validation.*` and `jakarta.servlet.*`, not `javax.validation.*` from Boot 2.x.

### 4.3. Directory Structure

```text
catalog-api-lab/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/
    main/
      java/demo/
        CatalogApiApplication.java
        ProductInput.java
        Product.java
        ProductCatalog.java
        ProductController.java
        RequestIdFilter.java
        ApiErrorHandler.java
      resources/
        application.properties
    test/
      java/demo/
        ProductApiMockMvcTest.java
        ProductApiHttpTest.java
```

All Java classes live in package `demo` under `CatalogApiApplication` so component scanning discovers the controller, service, filter, and advice. File names must match their corresponding `public class/record` names. No database schema is needed because data is stored in memory. On restart, data is lost; this is an intentional lab property, not a bug to work around with `@PreDestroy`.

## 5. HTTP Server Configuration in application.properties

File `src/main/resources/application.properties`:

```properties
spring.application.name=catalog-api-lab

# For local lab only. Container deployments must override the bind address.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.3: graceful HTTP shutdown is opt-in.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Gzip applies only to responses of sufficient size/matching MIME type.
server.compression.enabled=true
server.compression.min-response-size=2KB

# Limit exposing internal errors on the /error fallback.
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false

# Disable logging certain request details at DEBUG/TRACE.
spring.mvc.log-request-details=false

# Pure REST lab does not serve static assets, avoiding /** fallback.
spring.web.resources.add-mappings=false

# Use the custom @RestControllerAdvice below;
# avoid Boot also auto-registering its separate problem handler.
spring.mvc.problemdetails.enabled=false

# In the lab, do not trust Forwarded/X-Forwarded headers from the Internet.
server.forward-headers-strategy=none

# Management Actuator on loopback only for the lab.
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
```

This is a **local configuration**, not something to copy verbatim into Kubernetes: `server.address=127.0.0.1` makes the web server accept only localhost, so kubelet/Service/Ingress calls to the Pod IP will get connection refused. When running in a container, override `SERVER_ADDRESS=0.0.0.0` or use an appropriate profile. Access must still be protected by firewalls, network policies, and authentication—not by bind address alone.

### 5.1. Why Disable Static Mapping in the REST Lab?

In Spring Boot 3.3, static resources are typically mapped to `/**`. If an API path does not match a controller, the request may fall into `ResourceHttpRequestHandler` and raise `NoResourceFoundException` rather than `NoHandlerFoundException`. For a pure JSON API demo, `spring.web.resources.add-mappings=false` disables the default static handler, making route 404s easier to unify in MVC advice.

If the application serves a UI or assets, do **not** blindly disable static handling. Instead configure `spring.mvc.static-path-pattern=/assets/**`, static locations, and handle both `NoHandlerFoundException` and `NoResourceFoundException`. Do not put private files or uploads in public static directories.

### 5.2. Why Is spring.mvc.problemdetails.enabled=false When We Still Use ProblemDetail?

That property enables **Boot's auto-configured handler** for Problem Details of MVC exceptions. In this lesson we **write our own** `ApiErrorHandler extends ResponseEntityExceptionHandler` and return `ProblemDetail` via `@RestControllerAdvice`, so we do not need Boot to register another advice. Spring MVC/Jackson still supports RFC 9457 when we return `ProblemDetail` in code. If a project chooses to enable Boot's auto handler, check `@Order` precedence so custom advice is not preempted by another handler.

### 5.3. Server Configuration Differs from Business Logic

- `server.port`: TCP listener port; does not determine which paths are valid.
- `server.address`: network interface binding; local loopback and container Pod IP differ.
- `server.servlet.context-path`: prefix for the entire servlet application if configured; do not confuse with `@RequestMapping`.
- `server.compression.*`: criteria for response compression; the client must send an appropriate Accept-Encoding, and MIME type and size must qualify.
- `server.shutdown=graceful`: opportunity to drain HTTP requests when the context closes; does not guarantee completion on SIGKILL or expired Pod grace.
- `server.error.*`: limits fallback error details; does not replace custom advice and does not hide raw exception messages explicitly logged/returned by code.
- `server.forward-headers-strategy`: determines how Forwarded/X-Forwarded-* from a reverse proxy are handled; requires a clear trust boundary.
- `management.*`: Actuator health/metrics, not business routes.

## 6. CatalogApiApplication.java — Spring Boot Entry Point

File `src/main/java/demo/CatalogApiApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApiApplication.class, args);
    }
}
```

`@SpringBootApplication` bundles auto-configuration, component scanning, and Spring Boot app configuration. Placing the class in the root package `demo` automatically scans the classes beneath it. You do not need to manually instantiate `DispatcherServlet` or `TomcatServletWebServerFactory` when using defaults.

## 7. ProductInput.java — Validation at the HTTP Boundary

File `src/main/java/demo/ProductInput.java`:

```java
package demo;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ProductInput(

    @NotBlank
    @Size(min = 2, max = 100)
    String name,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,32}")
    String sku,

    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 10, fraction = 2)
    BigDecimal price,

    @NotNull
    @Min(0)
    @Max(100000)
    Integer stock
) {
}
```

### 7.1. Meaning of Each Constraint

- `@NotBlank`: String must be non-null and contain at least one non-whitespace character.
- `@Size(min=2,max=100)`: limits length of the name string. `@Size` **does not check for null by itself**, which is why it is combined with `@NotBlank`.
- `@Pattern`: applies to String, accepts only SKUs matching the regex; `@NotBlank` handles null/blank.
- `@NotNull`: requires price/stock; uses wrapper `Integer` instead of `int` to distinguish missing/null from 0.
- `@DecimalMin("0.01")`: BigDecimal value must be ≥ 0.01.
- `@Digits(integer=10,fraction=2)`: bounds integer and fractional digit counts.
- `@Min(0)`/`@Max(100000)`: keeps stock within range.
- `record`: generates constructor/accessors/equals/hashCode/toString from components; Jackson in Boot 3.3 supports binding JSON to records.

**Do not log `ProductInput.toString()`** in production: the record prints all request values. For DTOs containing email/token/PII, logging raw payloads or rejectedValue can cause data leaks. The advice below returns only the server-defined **field name + constraint code**.

### 7.2. When Does Validation Run?

In the controller, `@Valid @RequestBody ProductInput input` tells Spring to apply Jakarta Bean Validation after Jackson parses the JSON. On violation, Spring MVC throws `MethodArgumentNotValidException`. If the JSON is syntactically invalid, BigDecimal cannot be converted, or there is a JSON type mismatch, `HttpMessageNotReadableException` occurs before validation.

**Without `spring-boot-starter-validation`**, the project may lack the validation provider or annotation classes depending on the dependency tree. Do not just see `@Valid` in source code and assume the API is validated.

### 7.3. DTO Validation Differs from Business Rules

A syntactically valid SKU may already exist in the catalog. `@Pattern` cannot know repository state; uniqueness must be checked in the service/DB. Conversely, `stock=-5` is a request shape/range error and is caught by Bean Validation before reaching the service. Separating the two gives HTTP 400 vs 409 clear meaning.

## 8. Product.java — Response Model

File `src/main/java/demo/Product.java`:

```java
package demo;

import java.math.BigDecimal;

public record Product(
        long id,
        String name,
        String sku,
        BigDecimal price,
        int stock
) {
}
```

In the demo, the domain model is also the JSON response model because all fields are public. In production with cost price, internal notes, supplier secrets, or entity relationships, use a dedicated **response DTO** to avoid exposing internal fields or JPA lazy-loading/serialization cycles. Never expose a JPA entity directly just to save code.

Example success JSON:

```json
{
  "id": 1,
  "name": "Mechanical keyboard",
  "sku": "KEY-001",
  "price": 129.90,
  "stock": 12
}
```

Jackson can serialize BigDecimal in an appropriate numeric representation; clients should not rely on the numeric format always keeping two trailing decimal places. If the API has a strict monetary contract, define encoding/scaling, currency, and test serialization explicitly.

## 9. ProductCatalog.java — Service and Fake Repository

File `src/main/java/demo/ProductCatalog.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class ProductCatalog {

    private final Map<Long, Product> products =
            new LinkedHashMap<>();

    private long nextId = 1;

    public static final class MissingProduct
            extends RuntimeException {
    }

    public static final class DuplicateSku
            extends RuntimeException {
    }

    public synchronized List<Product> list() {
        return new ArrayList<>(products.values());
    }

    public synchronized Product get(long id) {
        Product found = products.get(id);

        if (found == null) {
            throw new MissingProduct();
        }

        return found;
    }

    public synchronized Product create(ProductInput input) {
        ensureSkuAvailable(input.sku(), null);

        long id = nextId++;

        Product created = new Product(
                id,
                input.name(),
                input.sku(),
                input.price(),
                input.stock()
        );

        products.put(id, created);
        return created;
    }

    public synchronized Product replace(
            long id, ProductInput input) {

        if (!products.containsKey(id)) {
            throw new MissingProduct();
        }

        ensureSkuAvailable(input.sku(), id);

        Product updated = new Product(
                id,
                input.name(),
                input.sku(),
                input.price(),
                input.stock()
        );

        products.put(id, updated);
        return updated;
    }

    public synchronized void delete(long id) {
        if (products.remove(id) == null) {
            throw new MissingProduct();
        }
    }

    private void ensureSkuAvailable(
            String sku, Long currentId) {

        boolean exists = products.values().stream()
                .anyMatch(product ->
                    product.sku().equals(sku)
                    && (currentId == null
                        || product.id() != currentId));

        if (exists) {
            throw new DuplicateSku();
        }
    }
}
```

### 9.1. Why Use synchronized?

`LinkedHashMap` is not thread-safe. Public methods use `synchronized` so the SKU check and insert/update happen in the same critical section, preventing two concurrent requests from passing the uniqueness check on **a single demo instance**. `synchronized` on a singleton service is simple but limits throughput; it does not replace transactions or unique constraints across multiple replicas.

### 9.2. Why Throw Domain Exceptions?

`MissingProduct` and `DuplicateSku` are pure business signals with no HTTP dependency. The controller/service does not build `ResponseEntity` inside the service. `ApiErrorHandler` maps them:

- `MissingProduct` → HTTP 404 + `PRODUCT_NOT_FOUND`.
- `DuplicateSku` → HTTP 409 + `SKU_ALREADY_EXISTS`.

Even though the Java exceptions carry no detailed message, clients still receive appropriate code/title/detail. Do not embed raw SKUs or user-supplied data in exception messages just for debugging.

### 9.3. What the Lab Intentionally Leaves Unsolved

- Data is **lost on restart** because it lives on the heap.
- Multiple Pods have separate product maps; there is no shared state.
- No transactions, database unique indexes, optimistic locking, soft deletes, auditing, or authentication.
- SKU uniqueness is case-sensitive per the uppercase regex; production must decide Unicode/case/whitespace normalization.
- Long IDs are sequential and guessable; authorization is still mandatory.
- Price and stock have no consistency guarantees under distributed concurrency.
- `synchronized` does not make a cluster data-consistent; production uses databases and constraints.

This is an **HTTP contract lab**, not a production catalog repository.

## 10. ProductController.java — REST Endpoints

File `src/main/java/demo/ProductController.java`:

```java
package demo;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductCatalog catalog;

    public ProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping
    public List<Product> list() {
        return catalog.list();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Product> create(
            @Valid @RequestBody ProductInput input) {

        Product created = catalog.create(input);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(created.id())
                .toUri();

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable("id") long id) {
        return catalog.get(id);
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Product replace(
            @PathVariable("id") long id,
            @Valid @RequestBody ProductInput input) {

        return catalog.replace(id, input);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @PathVariable("id") long id) {

        catalog.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

### 10.1. Why Use Constructor Injection?

Spring instantiates the `ProductCatalog` `@Service` bean and passes it to the controller via constructor. This makes unit testing easy and avoids static globals or hard-to-control field injection. With a single constructor, Spring does not require an explicit `@Autowired`.

### 10.2. URL Mapping and HTTP Methods

- `@RequestMapping("/api/v1/products")` defines the collection prefix.
- `@GetMapping` without an extra path handles the collection.
- `@GetMapping("/{id}")` uses `@PathVariable` to convert the URL segment into a long.
- `@PostMapping(consumes="application/json")` permits only JSON request bodies; wrong media types are handled by Spring MVC as 415.
- `@Valid` triggers validation for create/replace. Do not put `@Valid` only on the service and expect HTTP requests to validate automatically.
- `@DeleteMapping` returns 204 with an empty body; do not return a `"deleted"` string alongside 204.

### 10.3. Why Build Location from the Current Request?

Per HTTP semantics, 201 Created should point to the newly created resource using `Location`. `ServletUriComponentsBuilder.fromCurrentRequestUri()` builds from the current request URL and appends the ID segment, avoiding hardcoded `http://localhost:8080` in the controller. When a context path or a **trusted and normalized** reverse proxy is enabled, it reflects the public request URI accordingly.

**Security:** never blindly trust `X-Forwarded-Host` or `X-Forwarded-Proto` from Internet clients outside a trusted proxy. If forwarded headers are spoofed, Location/redirects can be manipulated (host header poisoning). The lab sets `server.forward-headers-strategy=none`. Production must configure the proxy to strip/overwrite headers and have the application trust only the right hop.

### 10.4. PUT vs PATCH

PUT in this demo **replaces all editable fields**: the client must send name, sku, price, and stock, and all are re-validated. If you only want to update a single field, `PATCH` needs its own contract and post-merge validation—do not accept partial JSON on PUT and perform half-updates. PATCH is not implemented in the lab; calling it returns 405.

### 10.5. Do Not Mix HTTP Responsibilities into the Service

The controller builds `Location` and chooses `201`; the service enforces uniqueness and manages state; the advice turns exceptions into status/body. This separation keeps tests clear: unit tests for business rules, MockMvc tests for the HTTP contract, and live tests against the embedded server.

## 11. RequestIdFilter.java — Safe Request Correlation

File `src/main/java/demo/RequestIdFilter.java`:

```java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_ATTR =
            "demo.requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        request.setAttribute(REQUEST_ID_ATTR, requestId);
        response.setHeader("X-Request-ID", requestId);

        chain.doFilter(request, response);
    }
}
```

### 11.1. Why Is the ID Generated on the Server?

A client-supplied `X-Request-ID` header may be forged, overly long, contain control characters, or contain PII. In the demo, the filter **ignores** any incoming header from the client and always generates a new UUID. With a trusted gateway in production, you can propagate a gateway-generated/normalized ID with length/charset allowlisting; there must be a clear contract on who the trusted source is.

### 11.2. Why Not Read the Body in the Filter?

The filter only sets a request attribute and response header. It never calls `getInputStream()`, `getReader()`, or `getParameterMap()`, so it does not accidentally consume JSON before `@RequestBody`. Never log raw Authorization, Cookie, query strings, or product input. For metrics/HTTP traces, use Actuator/Micrometer instead of serializing request bodies yourself.

### 11.3. Limitations

`OncePerRequestFilter` has dispatch semantics; with async/error dispatches, response wrappers or security filters may behave differently. Headers may already be committed, and container- or proxy-generated errors may bypass the filter. Therefore, do not promise that **every** HTTP error outside the app carries a request ID. For end-to-end correlation, you need gateway-generated trace/request IDs and a unified logging policy.

## 12. ApiErrorHandler.java — Consistent ProblemDetail Errors

This is the core of the lesson. Spring Framework 6.1 provides `ResponseEntityExceptionHandler` to handle common MVC exceptions: JSON parsing, validation, missing parameters, 405, 415, type mismatch, 404, and more. We subclass it, override the cases that need explicit error codes, and use `createResponseEntity` to attach `code` and `requestId` to all errors passing through the advice.

File `src/main/java/demo/ApiErrorHandler.java`:

```java
package demo;

import java.util.Comparator;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.beans.TypeMismatchException;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiErrorHandler
        extends ResponseEntityExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiErrorHandler.class);

    public record FieldViolation(String field, String rule) {
    }

    @ExceptionHandler(ProductCatalog.MissingProduct.class)
    public ResponseEntity<Object> missing(
            ProductCatalog.MissingProduct exception,
            WebRequest request) {

        return problem(
                HttpStatus.NOT_FOUND,
                "PRODUCT_NOT_FOUND",
                "Product not found",
                "Product does not exist.",
                request
        );
    }

    @ExceptionHandler(ProductCatalog.DuplicateSku.class)
    public ResponseEntity<Object> duplicate(
            ProductCatalog.DuplicateSku exception,
            WebRequest request) {

        return problem(
                HttpStatus.CONFLICT,
                "SKU_ALREADY_EXISTS",
                "Duplicate SKU",
                "SKU is already in use.",
                request
        );
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<Object> unexpected(
            RuntimeException exception,
            WebRequest request) {

        // Do not log payload, rejectedValue, or exception message.
        log.error(
                "Unhandled type={} requestId={}",
                exception.getClass().getSimpleName(),
                requestId(request)
        );

        return problem(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "Internal server error",
                "An internal error occurred.",
                request
        );
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                "Validation failed",
                "Invalid input data."
        );

        List<FieldViolation> errors =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getCode() == null
                                        ? "Invalid"
                                        : error.getCode()
                        ))
                        .distinct()
                        .sorted(
                            Comparator.comparing(
                                    FieldViolation::field)
                                .thenComparing(
                                    FieldViolation::rule)
                        )
                        .toList();

        body.setProperty("errors", errors);

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                "Invalid JSON",
                "Malformed JSON or invalid value type."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.BAD_REQUEST,
                "INVALID_PARAMETER",
                "Invalid parameter",
                "URL or query parameter has an invalid type."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleNoHandlerFoundException(
            NoHandlerFoundException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "Route not found",
                "No matching API route found."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleNoResourceFoundException(
            NoResourceFoundException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = detail(
                HttpStatus.NOT_FOUND,
                "ROUTE_NOT_FOUND",
                "Resource not found",
                "No matching API or resource found."
        );

        return handleExceptionInternal(
                exception, body, headers, status, request);
    }

    private ResponseEntity<Object> problem(
            HttpStatus status,
            String code,
            String title,
            String message,
            WebRequest request) {

        ProblemDetail body = detail(
                status, code, title, message);

        return createResponseEntity(
                body, new HttpHeaders(), status, request);
    }

    private static ProblemDetail detail(
            HttpStatusCode status,
            String code,
            String title,
            String message) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(
                        status, message);

        body.setTitle(title);
        body.setProperty("code", code);
        return body;
    }

    private static String requestId(WebRequest request) {
        Object value = request.getAttribute(
                RequestIdFilter.REQUEST_ID_ATTR,
                WebRequest.SCOPE_REQUEST
        );

        return value instanceof String id
                ? id : "unavailable";
    }

    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem =
                body instanceof ProblemDetail existing
                        ? existing
                        : ProblemDetail.forStatus(status);

        if (problem.getProperties() == null
                || !problem.getProperties()
                           .containsKey("code")) {

            problem.setProperty(
                    "code", "HTTP_" + status.value());

            problem.setTitle(
                    status.is5xxServerError()
                            ? "Internal server error"
                            : "HTTP request failed");

            problem.setDetail(
                    status.is5xxServerError()
                            ? "An internal error occurred."
                            : "Unable to process HTTP request.");
        }

        problem.setProperty(
                "requestId", requestId(request));

        HttpHeaders outputHeaders = new HttpHeaders();
        outputHeaders.addAll(headers);
        outputHeaders.setContentType(
                MediaType.parseMediaType(
                        "application/problem+json"));

        return super.createResponseEntity(
                problem, outputHeaders, status, request);
    }
}
```

### 12.1. Notes on Imports and Framework Version

The hook signatures above belong to **Spring Framework 6.1 / Spring Boot 3.3**, specifically:

```java
handleMethodArgumentNotValid(
    MethodArgumentNotValidException,
    HttpHeaders, HttpStatusCode, WebRequest)

createResponseEntity(
    Object, HttpHeaders, HttpStatusCode, WebRequest)
```

Do not blindly copy older Spring 5/Boot 2 signatures that take `HttpStatus` instead of `HttpStatusCode`. Using `@Override` makes the compiler catch version/signature mismatches immediately.

In the listing, `org.springframework.web.ErrorResponse` is imported for easy cross-reference with Spring MVC RFC 9457 APIs; it is not invoked directly. Java allows unused imports without failing compilation under default Gradle Java configuration. If using Checkstyle/Spotless, you can remove the unused import to match project style.

### 12.2. How an Error Flows Through the Advice

**Validation failure**:

1. Jackson parses JSON into `ProductInput`.
2. `@Valid` applies constraints and throws `MethodArgumentNotValidException`.
3. `handleMethodArgumentNotValid` builds a ProblemDetail with code `VALIDATION_FAILED`.
4. `errors` contains field name + constraint code, without values.
5. `handleExceptionInternal` delegates to `createResponseEntity`.
6. `createResponseEntity` attaches `requestId` and content type while preserving HTTP status 400.

**Domain error**: the service throws `MissingProduct`/`DuplicateSku`, and the advice produces a 404/409 ProblemDetail with the same `requestId`.

**Framework error**: unsupported method 405 or wrong content type 415 is handled by `ResponseEntityExceptionHandler`; `createResponseEntity` adds default code `HTTP_405`/`HTTP_415` and preserves framework headers (such as `Allow` for 405).

**JSON parse error**: malformed braces or an unconvertible price → code `INVALID_JSON`, 400; raw Jackson exception text is not returned.

### 12.3. Why Not Return rejectedValue?

Errors such as an invalid email, short password, or wrong OTP can cause `BindingResult` to hold client-supplied values. Serializing `exception.getBindingResult().getAllErrors()` or `error.getRejectedValue()` into an HTTP response or logs can leak PII. In the demo, `FieldViolation` holds only `field` and `rule`. Constraint codes like `NotBlank`, `Size`, and `Pattern` are server-defined, not raw user input.

### 12.4. Why HTTP_415 Instead of a Dedicated Code?

Framework errors not customized individually in the demo use `HTTP_<status>`. Clients can handle them generically by status; for larger APIs, define a clearer taxonomy such as `UNSUPPORTED_MEDIA_TYPE`, `METHOD_NOT_ALLOWED`, and `MISSING_PARAMETER`. **Never use exception text as an error code**, since it can contain sensitive data and change across versions or locales.

### 12.5. Errors Not 100% Covered by Advice

`@RestControllerAdvice` handles errors that pass through Spring MVC exception resolvers within the matching handler scope. It does not automatically control:

- Connections rejected by Tomcat before reaching DispatcherServlet;
- TLS handshake failures or request-line/header parse errors;
- Spring Security authentication/authorization failures in the FilterChain before the controller;
- NGINX 413/502/504 or CDN/WAF 403;
- Already-committed responses or network errors while streaming;
- JSON serialization failures after headers/body have already been partially sent;
- An `/error` fallback triggered by a dispatch outside the advice;
- Client disconnects or JVM SIGKILL.

For end-to-end error consistency, you need corresponding policies: Spring Security `AuthenticationEntryPoint`/`AccessDeniedHandler`, gateway error mapping, correlation IDs, container configuration, and per-layer tests. **Do not add `@ExceptionHandler(Exception.class)` and promise that every 5xx will return clean JSON**.

## 13. Running the Application

From a project with the Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

To package first:

```bash
./gradlew bootJar
java -jar build/libs/catalog-api-lab-0.0.1-SNAPSHOT.jar
```

Spring Boot depends on its classpath and Gradle BOM and cannot be compiled as a whole application using bare `javac CatalogApiApplication.java` on a raw JDK. `./gradlew` exists only when Initializr/Gradle Wrapper has been created. Dependencies download from Maven Central, requiring network access or a local cache.

### 13.1. Initial State

`GET` collection right after startup:

```bash
curl -i http://127.0.0.1:8080/api/v1/products
```

HTTP 200 with JSON:

```json
[]
```

If the app was already running or tests in the same context added items, the array may be non-empty. This lab has no persistent DB, so launching a fresh JAR initializes an empty map.

### 13.2. Creating a Product

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/api/v1/products' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Mechanical keyboard","sku":"KEY-001","price":129.90,"stock":12}'
```

Illustrative response on a fresh app with no existing products:

```http
HTTP/1.1 201
Content-Type: application/json
Location: http://127.0.0.1:8080/api/v1/products/1
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

{"id":1,"name":"Mechanical keyboard","sku":"KEY-001","price":129.90,"stock":12}
```

Header order, serialization scale, UUID, and ID depend on actual runtime state. **Location must be the created resource URL**, not the collection URL. `201 Created` does not mean every production database transaction is committed; it is the server contract announcing resource creation succeeded.

### 13.3. Read, Update, Delete

Use the actual ID returned from the creation step:

```bash
curl -i http://127.0.0.1:8080/api/v1/products/1

curl -i -X PUT \
  http://127.0.0.1:8080/api/v1/products/1 \
  -H 'Content-Type: application/json' \
  -d '{"name":"Mechanical keyboard V2","sku":"KEY-001","price":139.50,"stock":10}'

curl -i -X DELETE \
  http://127.0.0.1:8080/api/v1/products/1

curl -i http://127.0.0.1:8080/api/v1/products/1
```

This is an **illustrative sequence** assuming ID 1 when a fresh app creates its first product; if POST assigned a different ID, replace every `1` with the actual ID. GET before DELETE returns 200, PUT returns 200 with updated body, DELETE returns 204 empty, and GET after DELETE returns 404 `PRODUCT_NOT_FOUND`.

### 13.4. Testing Duplicate SKU: 409

While `KEY-001` still exists:

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"Another keyboard","sku":"KEY-001","price":99.00,"stock":5}'
```

Response:

```http
HTTP/1.1 409
Content-Type: application/problem+json

{"type":"about:blank","title":"Duplicate SKU","status":409,"detail":"SKU is already in use.","code":"SKU_ALREADY_EXISTS","requestId":"..."}
```

The `...` in the JSON example is a placeholder for the dynamic request ID, **not an exact JSON response**; the actual header/body contains a UUID and may include `instance`. If the product with that SKU has been DELETEd, a new POST will succeed; that is the expected business state.

### 13.5. Validation 400

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","sku":"lowercase","price":0,"stock":-1}'
```

For example, violations include `NotBlank`/`Size`, `Pattern`, `DecimalMin`, and `Min`. Response is HTTP 400 ProblemDetail with code `VALIDATION_FAILED`. **Do not hardcode assertions on the exact order of all errors** because multiple constraints can fail simultaneously and iteration/validation provider order may vary.

### 13.6. Malformed JSON: 400

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  --data '{'
```

Results in code `INVALID_JSON` with HTTP 400. You do not need to parse stack traces from the body to determine the error type; use `code` and requestId.

### 13.7. Unsupported Media Type: 415

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/products \
  -H 'Content-Type: text/plain' \
  --data 'this is not json'
```

Because of `@PostMapping(consumes="application/json")`, Spring MVC returns HTTP 415. The advice generates default code `HTTP_415` and keeps `application/problem+json` if the response stays in the MVC pipeline.

### 13.8. Unsupported Method: 405

```bash
curl -i -X PATCH \
  http://127.0.0.1:8080/api/v1/products/1 \
  -H 'Content-Type: application/json' \
  -d '{"stock":9}'
```

The demo declares no `@PatchMapping`. The framework responds 405 `HTTP_405`; the `Allow` header lists supported methods when provided by the framework. Do not convert every HTTP method error into 404, because clients need to know the route exists but the method is wrong.

### 13.9. Unknown Route 404 vs Missing ID 404

```bash
curl -i http://127.0.0.1:8080/api/v1/unknown

curl -i http://127.0.0.1:8080/api/v1/products/99999
```

Both are HTTP 404, yet distinguishable by `code`: `ROUTE_NOT_FOUND` vs `PRODUCT_NOT_FOUND`. With static resource mapping disabled in the lab, `NoHandlerFound` routes through the advice. If you re-enable the `/**` static handler, support `NoResourceFoundException` (already overridden in the advice) and re-test so HTML/other 404 pages are not leaked.

### 13.10. Invalid Path Variable Type: 400

```bash
curl -i http://127.0.0.1:8080/api/v1/products/abc
```

The string `abc` cannot be converted to `long`; Spring MVC triggers type mismatch, and the advice returns `INVALID_PARAMETER` HTTP 400. Do not mistake this for a 404 missing product ID.

## 14. MockMvc Integration Tests Verifying the Contract

`MockMvc` runs on mock Servlet objects with the Spring MVC context; it does not use real TCP or embedded server networking. It is well suited for testing JSON binding, validation, status codes, exception resolvers, headers, and controller/service wiring. When configuring server/proxy/compression/connection timeouts, complement it with live HTTP tests.

Create `src/test/java/demo/ProductApiMockMvcTest.java`:

```java
package demo;

import java.util.Locale;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductApiMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private String sku() {
        return "SKU-"
                + UUID.randomUUID().toString()
                      .substring(0, 8)
                      .toUpperCase(Locale.ROOT);
    }

    private String body(String value) {
        return """
            {
              "name":"Mechanical keyboard",
              "sku":"%s",
              "price":129.90,
              "stock":12
            }
            """.formatted(value);
    }

    @Test
    void createReadReplaceDeleteWork() throws Exception {
        String sku = sku();

        MvcResult created = mvc.perform(
                post("/api/v1/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(sku)))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andExpect(header().exists("X-Request-ID"))
            .andExpect(jsonPath("$.sku").value(sku))
            .andReturn();

        JsonNode result = json.readTree(
                created.getResponse().getContentAsString());

        long id = result.get("id").asLong();
        assertThat(id).isPositive();

        mvc.perform(get("/api/v1/products/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id))
            .andExpect(jsonPath("$.sku").value(sku));

        String changed = """
            {
              "name":"Mechanical keyboard V2",
              "sku":"%s",
              "price":139.50,
              "stock":10
            }
            """.formatted(sku);

        mvc.perform(put("/api/v1/products/{id}", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content(changed))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.stock").value(10));

        mvc.perform(delete("/api/v1/products/{id}", id))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/v1/products/{id}", id))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void validationReturnsProblemWithoutInputValues()
            throws Exception {

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name":"",
                      "sku":"bad-sku",
                      "price":0,
                      "stock":-1
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                    HttpHeaders.CONTENT_TYPE,
                    containsString("application/problem+json")))
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.requestId")
                    .isNotEmpty())
            .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void duplicateSkuIs409() throws Exception {
        String sku = sku();

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(sku)))
            .andExpect(status().isCreated());

        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(sku)))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code")
                    .value("SKU_ALREADY_EXISTS"));
    }

    @Test
    void malformedJsonUsesStableCode() throws Exception {
        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_JSON"));
    }

    @Test
    void unsupportedContentTypeIs415() throws Exception {
        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.TEXT_PLAIN)
                .content("plain text"))
            .andExpect(status().isUnsupportedMediaType())
            .andExpect(jsonPath("$.code").value("HTTP_415"));
    }

    @Test
    void unsupportedHttpMethodIs405() throws Exception {
        mvc.perform(patch("/api/v1/products/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"stock\":2}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().exists(HttpHeaders.ALLOW))
            .andExpect(jsonPath("$.code").value("HTTP_405"));
    }

    @Test
    void unknownRouteAndBadIdAreDifferent()
            throws Exception {

        mvc.perform(get("/api/v1/unknown"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("ROUTE_NOT_FOUND"));

        mvc.perform(get("/api/v1/products/abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PARAMETER"));
    }
}
```

### 14.1. What the Tests Verify

- **201 + Location + X-Request-ID**: POST creates the resource and returns expected headers.
- **200 read/update**: GET by ID and PUT full replacement still bind JSON properly.
- **204 delete**: resource disappears, GET after delete returns 404.
- **400 validation**: `@Valid` runs, ProblemDetail schema contains `code`/`errors`.
- **409 duplicate**: service uniqueness translates to a business conflict.
- **400 invalid JSON**: parser failure maps to `INVALID_JSON`.
- **415**: consumes mapping works.
- **405 + Allow**: method mapping and framework headers are preserved.
- **404 unknown route** vs **400 nonnumeric id**: avoids conflating error causes.
- **Request ID**: filter is registered and runs in MockMvc.

### 14.2. Avoiding Order-Dependent Tests

Tests generate UUID-based SKUs so they do not collide across methods. They do not assert that the ID must be 1, assume test execution order, or share a fixed SKU across the suite. Because `ProductCatalog` holds state in the Spring context between tests, this prevents flakiness when JUnit reorders tests. However, if tests run in parallel and mutate the same object or port, isolation still needs to be managed.

### 14.3. Testing That rejectedValue Is Not Echoed

The validation test checks the basic schema; to verify there is no leak, you can add:

```java
MvcResult failed = mvc.perform(
        post("/api/v1/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"SECRET-SENTINEL",
                 "sku":"x","price":0,"stock":-1}
                """))
    .andExpect(status().isBadRequest())
    .andReturn();

assertThat(failed.getResponse().getContentAsString())
    .doesNotContain("SECRET-SENTINEL");
```

This is an **extension snippet** placed inside a test method that has `mvc` and `assertThat` imports. It proves the response does not echo the test sentinel value; the test cannot detect logging in a reverse proxy, APM, or other servers. When using Bean Validation message templates that interpolate input values, avoid returning raw `getDefaultMessage()` without review.

### 14.4. Do Not Mistake MockMvc for Testing Tomcat Networking

MockMvc does not actually test: port 8080 binding, TLS, thread pools, HTTP header size limits, compression negotiation, reverse proxy forwarding, container errors before DispatcherServlet, startup/shutdown socket behavior, or Kubernetes probes. Add `RANDOM_PORT` and deployment tests for those.

## 15. HTTP Integration Test with a Real Embedded Server

`@SpringBootTest(webEnvironment=RANDOM_PORT)` starts Tomcat on a random port. `TestRestTemplate` uses real HTTP and does not throw exceptions on HTTP 4xx/5xx responses, making it suitable for testing error contracts.

Create `src/test/java/demo/ProductApiHttpTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProductApiHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void validationIsProblemJsonOverRealHttp() {

        String url = "http://127.0.0.1:"
                + port + "/api/v1/products";

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request = new HttpEntity<>(
            """
            {
              "name":" ",
              "sku":"invalid",
              "price":0,
              "stock":-1
            }
            """,
            headers
        );

        ResponseEntity<String> response =
                client.exchange(
                    url,
                    HttpMethod.POST,
                    request,
                    String.class
                );

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(response.getHeaders()
                .getContentType())
            .isNotNull()
            .satisfies(type ->
                assertThat(type.toString())
                    .startsWith(
                        "application/problem+json"));

        assertThat(response.getHeaders()
                .getFirst("X-Request-ID"))
            .isNotBlank();

        assertThat(response.getBody())
            .contains("\"code\":\"VALIDATION_FAILED\"")
            .contains("\"requestId\"")
            .doesNotContain("invalid");
    }
}
```

**Important testing note:** The body above uses the string `"invalid"` as the SKU, and the problem detail code should not echo the SKU. `.doesNotContain("invalid")` could accidentally match the word "invalid" inside a generic title/error code if wording or language changes later. For long-lived contracts, put a distinctive sentinel like `"SENTINEL-SECRET-PAYLOAD"` in an invalid field and assert the absence of that exact sentinel rather than a common word. That is the difference between testing a "safety property" and writing a wording-dependent test.

### 15.1. What Does the Live Test Prove?

- Tomcat binds a real TCP port.
- A client can POST JSON to the Spring MVC stack.
- Validation, advice, and Jackson behave over the network.
- The actual response has HTTP 400, `Content-Type: application/problem+json`, and `X-Request-ID`.
- The response body includes machine-readable error code `VALIDATION_FAILED`.

It does **not** test TLS, NGINX, CDN, Kubernetes, DB transactions, or concurrency across multiple replicas. Because `RANDOM_PORT` uses a random port, CI does not need port 8080 to be free.

### 15.2. Why Not Use @Transactional Test Rollback?

In a live HTTP test, Tomcat handles requests on a different thread than the test method. `@Transactional` on the test thread does not automatically roll back transactions committed by the HTTP request handler. If you migrate the lab to JPA, use an isolated test DB, fixtures, and explicit cleanup; do not assume DB changes are rolled back by the test transaction.

### 15.3. Testing HTTP Methods and Content Types Over the Network

You can add to the live test class:

- POST with `text/plain` → 415/`HTTP_415`.
- GET on a nonexistent route → 404/`ROUTE_NOT_FOUND`.
- Sending very large JSON → container/proxy may return 413 or 400 before the controller, depending on configuration.
- `Accept: application/problem+json` on errors → still returns ProblemDetail.
- Successful GET has `Content-Type: application/json`.
- Sending `Accept-Encoding: gzip` with sufficiently large JSON → verify actual compression, not just the property.

These are targeted tests aligned with the production contract; do not force MockMvc to prove networking behavior.

## 16. Server Configuration for Different Environments

### 16.1. Bind Address and Port

Lab:

```properties
server.address=127.0.0.1
server.port=8080
```

`127.0.0.1` accepts connections only from the local machine. When running in Docker/Kubernetes, you must bind on the container interface, typically:

```properties
server.address=0.0.0.0
server.port=8080
```

**0.0.0.0 does not add authentication to your API**; it merely opens the listener on all network interfaces. You must protect it with Security, network policies, firewalls, and ingress. To override local config in container deployments, use env vars `SERVER_ADDRESS=0.0.0.0`, `SERVER_PORT=8080`, or profile-specific properties rather than editing source code across environments.

### 16.2. Context Path Differs from API Version Prefix

Optional in an environment profile:

```properties
server.servlet.context-path=/shop
```

With this set, `@RequestMapping("/api/v1/products")` stays unchanged, while the external URL becomes `/shop/api/v1/products`. Do not add `/shop` inside the controller if context path is set, to avoid doubling the prefix. Re-test `Location` generated by `ServletUriComponentsBuilder`, redirects, security matchers, ingress rewrites, and health endpoints.

### 16.3. Server Compression

```properties
server.compression.enabled=true
server.compression.min-response-size=2KB
```

A small JSON payload may not be compressed even when the property is enabled; the response must meet the size threshold, MIME type, and client `Accept-Encoding`. Spring Boot 3.3 disables compression by default and uses a 2KB threshold. When NGINX/CDN compresses at the edge, define a clear compression owner to avoid double compression, wrong Content-Length, or cache variants.

Verify over real HTTP:

```bash
curl -i -H 'Accept-Encoding: gzip' \
  http://127.0.0.1:8080/api/v1/products
```

`curl -i` may print unreadable compressed bytes if the endpoint responds with gzip. Use `curl --compressed -i` so the client decompresses output for display; verify `Content-Encoding: gzip` on the response **only when conditions are met**. The demo typically has only a few products, below 2KB, so do not promise gzip on small examples.

### 16.4. Graceful Shutdown

`server.shutdown=graceful` gives Spring Boot 3.3 an opportunity to wait for in-flight HTTP requests when the context closes. `spring.lifecycle.timeout-per-shutdown-phase=20s` is a per-phase budget, not a guarantee that the Pod will always wait 20s. When a Kubernetes Pod has `terminationGracePeriodSeconds=30`, there are also `preStop`, route propagation, and other lifecycle phases; budget the entire timeline.

`SIGKILL`/OOMKill does not let Java shutdown hooks finish. Business operations need transactions, idempotency, and persistence rather than relying solely on `@PreDestroy`.

### 16.5. Forwarded Headers and TLS Termination

Locally:

```properties
server.forward-headers-strategy=none
```

When a trusted reverse proxy terminates HTTPS, the app may need to know the original scheme/host to generate correct `Location`/redirect URLs:

```properties
server.forward-headers-strategy=framework
```

**Enable only when the proxy is a trust boundary**: the edge must strip/overwrite `Forwarded` and `X-Forwarded-*` from the Internet, and the app must not be directly reachable over another route where attackers can send forged headers. Misconfiguration lets attackers poison `Location` hostnames. On Tomcat, depending on architecture, native strategy and `RemoteIpValve` may be used; check docs for your exact version.

### 16.6. Error Fallback and Debug

`server.error.include-stacktrace=never`, `server.error.include-message=never`, and `server.error.include-binding-errors=never` prevent the default `/error` fallback from leaking internal details. However, they do not strip stack traces your app explicitly returns via `ex.getMessage()`, nor do they suppress proxy-generated logs/headers. Use correlation IDs, sanitized error codes, metrics/traces, and properly access-controlled internal logs.

## 17. Advanced Validation Handling

### 17.1. Nested DTOs and @Valid Cascade

Example request with a nested address:

```java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String street) {
}

public record CheckoutInput(
        @NotNull @Valid AddressInput address,
        @NotBlank String customerRef) {
}
```

This is an **illustrative snippet** requiring Jakarta validation imports and separate class files if used. `@Valid` on the nested component enables cascade validation; `@NotNull` alone does not validate fields inside it. For collections, use `List<@Valid AddressInput>` along with size/pattern constraints.

### 17.2. Cross-Field Validation

Some business constraints span multiple fields: startDate ≤ endDate, discount ≤ price, stock non-negative when reserved. You can write a custom class-level Jakarta validation constraint or check in the service. Do not try to cram multi-field relationships into a giant regex on one field. Distinguish **400 invalid request representation** from **409 conflict with system state**.

### 17.3. DTO Groups

Jakarta Bean Validation supports validation groups, though groups increase complexity when create/PUT/PATCH have different constraints. For small-to-medium APIs, **separate DTOs for create/update/patch** are usually easier to understand. Do not use groups as an excuse to skip validating PATCH after merging.

### 17.4. @Validated and Method Validation

`@Valid @RequestBody` triggers validation on body DTOs. `@Validated` on a class/service enables method-level constraints via Spring/Bean Validation integration, while Spring MVC 6.1 also has built-in method validation directly on handler parameters. Do not apply Boot 2.x solutions to Boot 3.3 without checking exception types: method validation can raise `HandlerMethodValidationException` instead of body `MethodArgumentNotValidException`.

Advice extending `ResponseEntityExceptionHandler` handles the framework exception; if you want structured `errors` for method parameters, override the corresponding hook and add tests. Do not assume every `@Min` on `@RequestParam` passes through `handleMethodArgumentNotValid`.

### 17.5. Do Not Use Localized Messages as Error Codes

`@NotBlank(message="...")` can render messages via `MessageSource` and `Accept-Language`. Clients should never branch logic on translated messages. Return a stable `code` and `field`/`rule`; if localized `detail` is needed, translate on the server per locale with an explicit fallback and i18n tests.

### 17.6. Do Not Abuse Validation as a Substitute for Authorization

`@Pattern` on SKU does not prevent user B from editing user A's product. `@Valid` validates input shape; authorization must verify actor/resource/tenant at the service/security boundary. Do not rely on hard-to-guess IDs or UUIDs in place of authentication.

## 18. Designing Consistent Errors: Tricky Edge Cases

### 18.1. 404: No Route vs No Resource

`GET /api/v1/products/5` has a valid route, yet the catalog has no ID 5 → `PRODUCT_NOT_FOUND`. `GET /api/v1/ghost` has no controller mapping → `ROUTE_NOT_FOUND`. Both return HTTP 404, giving clients and support extra context. However, avoid disclosing fine-grained resource existence to unauthorized users to prevent enumeration; production may return a generic 404 for unauthorized resources.

### 18.2. 405: Preserving the Allow Header

Spring MVC knows the route exists but the HTTP method is wrong; it can populate `Allow`. When customizing errors globally, **do not drop original headers**. `ApiErrorHandler.createResponseEntity` copies `HttpHeaders` from the base handler and only sets `Content-Type` to Problem JSON. Tests verify `Allow` is present. `OPTIONS`/CORS preflight has its own semantics; do not turn every OPTIONS into 405.

### 18.3. 415 and 406

`415 Unsupported Media Type`: client sent a **request** Content-Type incompatible with `consumes`. `406 Not Acceptable`: client requested a **response** format via `Accept` that the server cannot produce. When returning ProblemDetail for 406, content negotiation may impose constraints: if the client only accepts `text/html`, you cannot promise an `application/problem+json` body will always be sent cleanly. Test both Accept and Content-Type sides rather than assuming one catch-all handler covers everything.

### 18.4. JSON Null, Missing Fields, and Data Types

If JSON omits `stock`, the Java record component `Integer` receives null and `@NotNull` triggers 400 validation. Using primitive `int` can cause missing fields to default to 0 and silently pass if 0 is valid. Thus, input DTOs should distinguish absence/null from 0 when a field is required. Jackson parse errors when a client sends `"stock":"abc"` produce `INVALID_JSON`, distinct from `stock=-1` which has a valid type but violates `@Min`.

### 18.5. Unknown Properties

With default Jackson/Boot settings, unknown JSON fields may be ignored rather than rejected. An API requiring a strict schema can configure Jackson fail-on-unknown-properties in a controlled profile and test for 400; evaluate backward-compatibility impacts first. Do not rely on Bean Validation and assume undeclared fields are automatically rejected.

### 18.6. Concurrency and 409

In the lab, `synchronized` keeps check+insert atomic within one JVM. Across multiple replicas and a DB, two concurrent requests creating the same SKU can both pass the service check on two Pods; a **database unique index** is the final source of truth. Mapping a database constraint violation to 409 must identify the exact unique constraint (SKU) and avoid leaking SQL/queries/record values in the HTTP response.

### 18.7. Optimistic Locking / 412

When one client GETs a product and PUTs after another client updated it, lost updates can occur. Production can use JPA `@Version`, ETag, and `If-Match`; stale representation errors commonly return HTTP `412 Precondition Failed` when `If-Match` fails, or 409 for a defined business conflict. Do not fake optimistic locking in an in-memory repository simply with `synchronized`: a critical section does not know which version the client originally read.

### 18.8. 500 and Fallback Paths

Unexpected failures should return a generic message and log category + request ID server-side to an internal channel. Never expose stack traces, SQL, credentials, or raw Java class/package names in a public ProblemDetail. If headers or response body are already committed, the handler may not be able to send a complete ProblemDetail—that is an HTTP streaming limit, not an `@ExceptionHandler` syntax issue.

## 19. Observability for REST APIs

### 19.1. Request ID, Trace ID, and Logs

`X-Request-ID` in the demo is a per-request UUID, not an authentication token. Clients can quote that ID when reporting errors; backend teams can locate matching logs if the app logs cleanly. In production, use structured logs (service, route template, status, duration, requestId, traceId) and cross-service correlation without logging full JSON bodies or Authorization/Cookie headers.

### 19.2. Actuator Metrics

With the Actuator starter, Spring Boot/Micrometer produces HTTP server metrics such as `http.server.requests`, useful for latency, throughput, and 4xx/5xx rates. Use the route template `/api/v1/products/{id}` as the tag rather than raw URLs containing IDs; never attach requestId/userId/SKU to metric labels due to high cardinality.

In the lab, bound to loopback only:

```bash
curl -sS http://127.0.0.1:8080/actuator/health
curl -sS http://127.0.0.1:8080/actuator/metrics
curl -sS http://127.0.0.1:8080/actuator/metrics/http.server.requests
```

Metric output depends on requests executed and the active registry. Production Actuator metrics/health endpoints require private management networking/authentication; never expose debug/admin endpoints to the Internet.

### 19.3. Rate Limits, Timeouts, and Circuit Breakers

A REST API needs protection against request bursts, oversized bodies, and slow clients. Tomcat thread pools, connections, and timeouts must be tuned via load tests rather than raised unboundedly. APIs calling downstream dependencies need connection/read timeouts, bounded retries, and circuit breakers; never place blocking remote calls inside a filter or per-request health endpoint.

### 19.4. Security Errors May Differ from JSON Advice

With Spring Security, authentication failures (401) and forbidden responses (403) are usually handled in the servlet filter chain **before** controller advice. To return consistent ProblemDetail for 401/403, configure dedicated `AuthenticationEntryPoint` and `AccessDeniedHandler` beans using a shared error factory or policy-compliant HTTP converter. Do not write `@ExceptionHandler(Exception.class)` assuming it will intercept every security exception.

## 20. Moving the Lab to Database/JPA in Production

A sensible migration path:

1. Create separate domain entities/repositories; never expose JPA entities directly as API JSON.
2. Add `spring-boot-starter-data-jpa`, the appropriate JDBC driver, and Flyway/Liquibase migrations.
3. Define the products table with ID/price/stock and a unique index on normalized SKU.
4. Use `@Transactional` on the service for create/replace/delete with appropriate isolation.
5. Map between `ProductInput`, the entity, and a response DTO.
6. Catch `DataIntegrityViolationException` **selectively** (matching the specific unique constraint) to return 409; other integrity errors must not be masked as duplicates.
7. Handle lost updates using version/ETag when multiple writers exist.
8. Add separate repository integration tests with Testcontainers or a test DB; do not rely on an in-memory fake to validate transaction behavior.
9. Configure connection pools, DB timeouts, and a schema migration/rollback plan.
10. Add authentication, authorization, and tenant isolation to every read and write path.

### 20.1. Why Service-Level Uniqueness Checks Are Not Enough

If two concurrent requests hit two Pods, each Pod may observe that the "SKU does not exist yet." Checking before insert without a DB unique index allows both to commit. The database constraint must be the source of truth, while the service check helps produce a friendly message in normal cases.

### 20.2. Do Not Turn the API into an Unreliable Transaction Coordinator

If POST product also calls a payment or inventory service, a failed HTTP response does not mean all downstream side effects rolled back. Use outbox, sagas, or idempotency keys for distributed transactions and retries; ProblemDetail reports errors cleanly, but does not create consistency guarantees by itself.

## 21. Deployment: Environment Configuration and Reverse Proxies

The lab sets `server.address=127.0.0.1`, so a Docker image will refuse connections from port publishing unless overridden. Example Dockerfile after building the JAR:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY build/libs/catalog-api-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build and run a local container:

```bash
./gradlew bootJar

docker build -t catalog-api-lab:local .

docker run --rm -p 8080:8080 \
  -e SERVER_ADDRESS=0.0.0.0 \
  catalog-api-lab:local
```

**Exec-form ENTRYPOINT** lets the JVM receive stop signals directly; if using a shell wrapper, ensure `exec java ...`/signal forwarding. For real deployments, use your organization's image tags and registry, enable network policies and Security, configure liveness/readiness/startup probes, and set Pod shutdown grace longer than the app needs.

### 21.1. Environment-Separated Configuration

Never hardcode production secrets in `application.properties` or commit credentials to Git. Use environment variables, Kubernetes Secrets, or a secret manager with Spring config import/profiles. For instance, `SERVER_PORT=8080`, `SERVER_ADDRESS=0.0.0.0`, and `SPRING_PROFILES_ACTIVE=prod` bind automatically via Boot. Never put production database URLs or passwords into code examples or logs.

### 21.2. HTTPS and Trusted Proxies

If a proxy terminates HTTPS and forwards plain HTTP to Java internally, configure the right forwarded-headers strategy. On the reverse proxy:

- Strip any client-supplied forwarded headers.
- Set `X-Forwarded-Proto`/`Host`/`Forwarded` from the trusted public request.
- Allow the app to receive traffic only from the proxy/allowed network.
- Evaluate `server.forward-headers-strategy=framework` or native with a security review.
- Test `Location` on POST through the public HTTPS URL so it does not point back to `http://localhost`.
- Test Secure/SameSite cookies if session login is added later.

### 21.3. Kubernetes Readiness and Graceful Shutdown Do Not Guarantee Idempotency

A Ready Pod means it passes health policy to receive traffic, not that a business transaction is guaranteed to succeed. During termination, readiness removes traffic asynchronously and keep-alive requests may still arrive. For side-effecting POSTs, client retries require an idempotency key and server-side deduplication to avoid creating two products when the first response is lost.

### 21.4. Do Not Break Routing with Context Path

If ingress rewrites `/catalog/api/v1/products` to `/api/v1/products` while the app also sets `server.servlet.context-path=/catalog`, you can end up with a double prefix or broken mappings. Establish single ownership of the prefix: either proxy rewrite or servlet context path. Test with curl through ingress and inspect the actual `Location` header.

## 22. Additional Tests Needed Before Production

| Test | Purpose | Appropriate Layer |
| --- | --- | --- |
| DTO null/blank/size/pattern/price/stock | Catch validation regressions | MockMvc |
| Malformed JSON syntax | Verify INVALID_JSON and 400 | MockMvc/live |
| Missing Content-Type or text/plain | Prove consumes 415 | MockMvc/live |
| Unknown API route and malformed ID | Distinguish 404/400 | MockMvc/live |
| PUT missing fields | Full replacement validation | MockMvc |
| Concurrent duplicate SKU | Business 409, atomicity | Integration/database |
| POST Location absolute after TLS proxy | Correct scheme/host/path | Staging via gateway |
| Unauthorized GET/PUT/DELETE | Object-level permissions | Spring Security integration |
| Accept JSON/Problem JSON headers | Content negotiation | Live HTTP |
| Very large body/headers | Container/proxy limits | Live HTTP/ingress |
| Gzip compression and Vary | HTTP server/edge owner | Live HTTP/CDN |
| X-Request-ID consistency | Header/body correlation | MockMvc/live |
| 500 does not leak stacktrace | Safe fallback error | Integration with synthetic fault |
| Database unique constraint race | No duplicates across Pods | DB integration |
| Graceful SIGTERM | Drain active HTTP requests | Process/container test |
| 404 static fallback behavior | MVC advice vs static resource | Full Boot context |
| 401/403 error format | Security chain outside advice | Security integration |
| Actuator not publicly exposed | Network/security posture | Staging/cloud |
| Retry/idempotency | Non-repeating side effects | Integration/E2E |

### 22.1. Testing with a Controller-Only Slice

`@WebMvcTest(ProductController.class)` runs the MVC slice and may require mocking/importing `ProductCatalog`. It is good for fast binding/HTTP mapping checks, but does not verify the repository or full app wiring. This lesson uses `@SpringBootTest + @AutoConfigureMockMvc` to exercise the real service, advice, and filter; `RANDOM_PORT` verifies the HTTP listener.

### 22.2. JSON Responses Should Not Depend on Field Order

Jackson does not guarantee clients can rely on key ordering. Tests should use `jsonPath` or a JSON parser rather than `assertEquals` against an entire string with fixed ordering. Likewise, do not assert exact error `detail` strings if localization may change them, unless the wording is explicitly part of the public contract.

### 22.3. Dynamic UUIDs and Timestamps

Request IDs, product IDs, and timestamps (if added) vary at runtime. Tests should assert that `requestId` is non-empty, matches between header and body on the same request, and conforms to UUID format if required by the contract. Do not hardcode illustrative UUIDs. Ensure tests do not leak IDs into metric labels.

## 23. Common Error Diagnosis Matrix

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@Valid` does not return 400 | Missing starter-validation or missing `@Valid` | Check dependencies and controller |
| Boot 3 compile fails on javax validation | Using Boot 2.x imports | Switch to `jakarta.validation.*` |
| Valid POST returns 415 | `Content-Type` header is not JSON | Send application/json |
| Invalid JSON POST returns 400 INVALID_JSON | Jackson parse/bind failed | Check JSON types/format |
| Invalid value POST returns 400 VALIDATION_FAILED | Bean Validation violated | Inspect field/rule, not rejectedValue |
| Duplicate SKU returns 409 | Uniqueness business rule | Choose another SKU, handle conflict |
| URL `/products/abc` returns 400 | PathVariable long conversion failed | Send numeric ID |
| URL `/products/9999` returns 404 | Product ID does not exist | Check state, do not confuse with route |
| Unknown API path returns 404 HTML | BasicErrorController/static handler/config | Check resource mappings and advice |
| 405 missing Allow header | Custom handler dropped original headers | Preserve ResponseEntityExceptionHandler headers |
| Error returns 200 with error body | Caught exception in controller and returned JSON | Return proper status via advice |
| 500 leaks stacktrace | Returning ex.toString/getMessage or Boot debug | Sanitize details, server.error.* |
| ProblemDetail missing code | Custom advice not invoked/ordered differently | Check @RestControllerAdvice and Boot auto handler |
| Body `errors` contains email/password | Serialized BindingResult/rejectedValue | Only field/rule, add leak test |
| Content-Type JSON instead of problem+json | Handler returned Map instead of ProblemDetail | Use RFC 9457 and proper converter |
| Location points to http behind HTTPS | Forwarded headers/proxy trust misconfigured | Strip/normalize trusted headers |
| Location missing context prefix | Hardcoded URI in controller | Build from current request URI, test ingress |
| Docker curl connection refused | server.address=127.0.0.1 in container | Override 0.0.0.0/network policy |
| GET list empty after restart | In-memory store reset | Persistent DB |
| Concurrent duplicate across multiple Pods | synchronized is single-JVM only | DB unique constraint |
| PUT overwrites another client's changes | Missing ETag/version check | Optimistic locking, If-Match |
| CORS preflight 403 | Missing Security/CORS config | Configure trusted origins and OPTIONS |
| HTTP client retries create duplicates | POST lacks idempotency | Idempotency key/dedup |
| MockMvc passes, gateway returns 413 | Proxy/container body limit | Live HTTP/ingress tests |
| Gzip does not appear | Response below threshold/missing Accept-Encoding | Test with qualifying conditions |
| Actuator metrics public | Wrong management exposure/network | Private listener + auth |
| Error missing X-Request-ID | Error before filter or returned by gateway | Correlation at edge and boundary tests |

## 24. Self-Check Exercises

**1.** Why must `spring-boot-starter-validation` be added if `spring-boot-starter-web` is already present?  
**Answer:** The validation provider/annotations require the appropriate dependency; `@Valid` alone does not automatically enable full Bean Validation in every web app.

**2.** Does `@NotNull` on a String replace `@NotBlank`?  
**Answer:** No. `"   "` is non-null but blank, so `@NotBlank` is more appropriate.

**3.** Why does the DTO use `Integer` instead of `int` for stock?  
**Answer:** To distinguish null/missing from 0 so `@NotNull` catches an omitted field.

**4.** Should malformed JSON and valid JSON with `price=-1` share the same error code?  
**Answer:** Not necessarily. The demo uses `INVALID_JSON` and `VALIDATION_FAILED`, both with HTTP 400.

**5.** On a successful POST, why is `Location` needed?  
**Answer:** 201 Created should indicate the URI of the new resource so clients can GET it next.

**6.** A client sends a duplicate SKU; is this syntax validation or state conflict?  
**Answer:** Business state conflict, so the demo returns 409 `SKU_ALREADY_EXISTS`.

**7.** If a client calls GET /api/v1/products/abc, should it return 404?  
**Answer:** No. The path variable cannot be converted to long → 400 `INVALID_PARAMETER`.

**8.** Why not return `MethodArgumentNotValidException.getMessage()` in the body?  
**Answer:** It can expose rejected values, internal details, and is unstable across framework versions.

**9.** If a client sends PATCH when the controller only supports PUT, what should be returned?  
**Answer:** 405 Method Not Allowed, preserving the `Allow` header.

**10.** Does `spring.mvc.problemdetails.enabled=false` prohibit using `ProblemDetail`?  
**Answer:** No. It disables Boot's auto handler; custom advice still uses Spring MVC `ProblemDetail`.

**11.** Why does `spring.web.resources.add-mappings=false` help 404 handling in an API lab?  
**Answer:** It disables the default `/**` resource handler so unknown paths are not caught by the static handler and instead flow to MVC no-handler advice.

**12.** When the app sits behind an HTTPS reverse proxy but Location points to HTTP, what is the cause?  
**Answer:** Misconfigured forwarded headers/strategy/trust boundary or a hardcoded URL.

**13.** Is `synchronized` enough to guarantee unique SKUs across three Kubernetes Pods?  
**Answer:** No. Synchronization applies only within one JVM; a DB unique constraint/transaction is required.

**14.** Why does a passing `MockMvc` test not prove the server compresses with gzip?  
**Answer:** MockMvc does not execute real networking or embedded server compression; live HTTP responses are required.

**15.** On a successful DELETE, should a 204 response include a JSON body `{"ok":true}`?  
**Answer:** No. 204 No Content has no representation body.

**16.** Does an HTTP 500 from NGINX/upstream always pass through `@RestControllerAdvice`?  
**Answer:** No. Gateway-generated errors occur outside Spring MVC; a dedicated edge/gateway policy is required.

**17.** Why should `requestId` not be used as a metric tag?  
**Answer:** Every distinct request ID causes high cardinality and time-series explosion.

**18.** Is PUT in the demo a partial update?  
**Answer:** No. It replaces all fields of an existing resource; PATCH requires its own contract.

**19.** Can retrying a POST after a timeout create a duplicate product?  
**Answer:** Yes, if the server committed before the client lost the response. Idempotency/deduplication is required when the contract demands it.

**20.** Is an `application/problem+json` response with `status:409` in the body but HTTP status 200 valid?  
**Answer:** No. Clients and proxies rely on the actual HTTP status; the body status must match.

## 25. Completion Checklist

- [ ] Controller accepts only valid DTOs and handles HTTP mapping/status/Location clearly.
- [ ] Java 17, Boot 3.3, and `jakarta.*` imports are properly aligned.
- [ ] `spring-boot-starter-validation`, `@Valid`, and negative input tests are in place.
- [ ] Domain uniqueness is checked in the service and enforced by a database constraint in production.
- [ ] POST returns 201 + Location, GET/PUT return 200, DELETE returns 204.
- [ ] Missing product returns 404, duplicate returns 409, malformed JSON returns 400, unsupported media type returns 415.
- [ ] 405 returns Allow, 404 unknown route does not leak HTML/stacktraces outside the contract.
- [ ] Errors use RFC 9457 ProblemDetail with `code` and `requestId`, without `rejectedValue`.
- [ ] Error Content-Type is `application/problem+json` for MVC-handled cases.
- [ ] RequestIdFilter does not read or log payloads or credentials.
- [ ] Checked `server.port`, address, context path, and bind interface per deployment environment.
- [ ] Compression has a clear owner (app/proxy/CDN) and an appropriate live HTTP test.
- [ ] Forwarded headers are trusted only from trusted proxies, with Location/redirects using the right scheme/host.
- [ ] Graceful shutdown is enabled for Boot 3.3, with sufficient Pod termination grace.
- [ ] Error fallback does not expose exception messages, stacktraces, or sensitive binding values.
- [ ] Security authentication/authorization/CSRF/CORS/rate limits are added per threat model.
- [ ] DB migrations/unique indexes/transactions/optimistic locking when moving to a persistent store.
- [ ] MockMvc tests and RANDOM_PORT tests cover HTTP contracts and error content types.
- [ ] Concurrency, retries, idempotency, and failover tested when running multiple replicas.
- [ ] Actuator/metrics are secured, with low-cardinality tags and proper correlation.
- [ ] CI builds the JAR and runs smoke tests through a production-like container/ingress.
- [ ] Diagnostic playbook exists covering status, code, requestId, route, and trace.

## References

1. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
2. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
3. [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
4. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
6. [Spring Framework 6.1 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller.html)
7. [Spring Framework 6.1 — Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-rest-exceptions.html)
8. [Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
9. [Spring Framework 6.1 — Validation](https://docs.spring.io/spring-framework/reference/6.1/core/validation/beanvalidation.html)
10. [Spring Framework 6.1 — MVC Input/Validation](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-validation.html)
11. [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/)
12. [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
13. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
14. [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
15. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

**Conclusion:** A high-quality MVC REST API is more than `@GetMapping` and `@PostMapping`. It requires **accurate HTTP statuses and Location headers, environment-appropriate server properties, boundary validation, business constraints in the service/DB, stable RFC 9457 errors without data leaks, request correlation, and tests at both the MVC and real HTTP server layers**. Properly separating responsibilities across controller, service, advice, filter, and infrastructure is the foundation for turning a Spring Boot demo into a safely operable service.
