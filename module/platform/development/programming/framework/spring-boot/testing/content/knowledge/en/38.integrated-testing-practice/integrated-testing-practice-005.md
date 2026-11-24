# Testing the Same Business Logic via @SpringBootTest with RANDOM_PORT

When a controller returns `201 Created` in a test calling a Java method directly or using `MockMvc`, we have only proved **part** of the request path. To verify that **business logic genuinely operates when the application opens an HTTP port**, Spring Boot provides `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`. This annotation initializes an `ApplicationContext` close to the real application, runs an embedded web server on a **dynamically chosen TCP port**, and lets tests send an HTTP request through serialization, servlet filters, mapping, validation, controller, service, and JDBC before receiving a real HTTP response.

This lesson belongs to **Integration Practice** in **Spring Boot - testing**, focusing on **“Testing the same business logic via @SpringBootTest with RANDOM_PORT”**. We use **an order-creation business rule** to compare pure Java testing of the pricing table against direct service tests and real HTTP tests. The project (**Java 17 + Spring Boot 3.5.0 + Spring MVC + Bean Validation + JDBC/H2 + JUnit Jupiter**) can be built from the files below without Docker or external services. The API covers both success and `400/404/409/422` errors; tests read the database after the response to verify the server transaction committed and clean up using test-owned request keys.

**Key distinctions to remember:**
- `RANDOM_PORT` is a **real web server**, not a mock request dispatcher.
- `TestRestTemplate` sends **real HTTP**; it does not throw exceptions by default on `4xx/5xx` responses, so you must assert `status code`/body.
- Client tests and the server run on **two different threads and transaction boundaries**; `@Transactional` on a test does not roll back writes committed by an HTTP endpoint.
- `@LocalServerPort` holds the actual port **only after the web server starts**, not a user-chosen fixed port.
- Running inside one JVM with an embedded server is **not yet** E2E across ingress, TLS, API gateways, load balancers, or a production environment.

## 1. Choosing the test level based on the evidence needed

| Level | How it runs | Can verify | Cannot verify |
|---|---|---|---|
| Pure unit | `new PricingPolicy()` + JUnit | Pricing table, parameter constraints, domain exceptions | Spring wiring, HTTP, JSON, JDBC |
| Service integration | `@SpringBootTest` + calling `OrderService` directly | Bean wiring, `@Transactional`, repository, H2 data | HTTP contract, serialization, web filters, network socket |
| Controller/mock | `@WebMvcTest` + `MockMvc` | Mapping, validation, exception advice, serialized response in mocked MVC | Embedded TCP server, servlet container/network behavior; service/repo usually mocked |
| Full Spring + MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Real service/repository + MVC stack in-JVM | Real client/server TCP exchange, container-level error pages |
| Full Spring + real HTTP | **`@SpringBootTest(RANDOM_PORT)`** + `TestRestTemplate` | TCP listener, HTTP status/headers, JSON, validation, controller → service → JDBC commit | Ingress/proxy/TLS/network ACLs/cloud resources unless configured |
| Deployment/E2E | Deployed app + real client | Deployed ports/routes/proxy/TLS/auth and real dependencies | Harder to stabilize and isolate data |

### 1.1. The four values of `webEnvironment`

Spring Boot 3.5 provides:

- `MOCK` (**default**): creates a mock servlet/web context when Spring MVC is on the classpath, without opening a TCP listener. Combine with `@AutoConfigureMockMvc` to execute HTTP-like requests inside the MVC stack.
- `RANDOM_PORT`: starts a real embedded server and binds a **dynamic port** (effectively equivalent to setting `server.port=0` on the main web server).
- `DEFINED_PORT`: runs a real server on the configured `server.port`, or default port 8080; prone to collisions in CI, so use only when testing a fixed port is required.
- `NONE`: starts the Spring application context without setting up a web environment.

**Do not confuse random port with “a new server per `@Test`”:** TestContext can cache and share an `ApplicationContext` across multiple test methods/classes with identical configuration. The port can **stay the same across methods sharing a context**, changing only when the context is recreated or run in another JVM. Never assert that two methods must receive two different ports.

### 1.2. Execution model of tests in this lesson

```text
JUnit Jupiter, test JVM
  |
  +-- @SpringBootTest(webEnvironment=RANDOM_PORT)
  |        |
  |        v
  |   SpringApplication -> ApplicationContext
  |        |
  |        +--> Embedded Tomcat binds ephemeral TCP port
  |        +--> DispatcherServlet, Jackson, Validator
  |        +--> OrderController, OrderService, PricingPolicy
  |        +--> JdbcTemplate -> isolated H2
  |
  +-- @Autowired TestRestTemplate
  |        |
  |        +-- POST /api/orders (real TCP -> server thread)
  |        |        |
  |        |        +-- HTTP 201 + Location + JSON receipt
  |        |
  |        +-- GET /api/orders/{id}
  |                 |
  |                 +-- HTTP 200 / 404
  |
  +-- @Autowired JdbcTemplate (test thread)
           |
           +-- verify server-committed row
           +-- delete rows by OWN request_key in @AfterEach
```

With this API, tests can verify the **same pricing invariant** from plain Java `PricingPolicy` through HTTP responses and database rows. This provides complementary evidence at each boundary, without writing pointless identical duplicate assertions in every test.

## 2. What is actually tested through `RANDOM_PORT`?

A `POST` request passes through:

1. `TestRestTemplate` serializes `CreateOrderRequest` to JSON and sends HTTP to `http://localhost:<random-port>`.
2. The servlet container accepts the request over a socket and hands it to `DispatcherServlet`.
3. Spring MVC matches `@PostMapping("/api/orders")`, uses Jackson to parse JSON, and invokes Jakarta Bean Validation via `@Valid`.
4. `OrderController` calls the **real `OrderService` bean** (not replaced by Mockito).
5. `OrderService` invokes `PricingPolicy` and `OrderStore`, opening a transaction via Spring AOP `@Transactional`.
6. `JdbcTemplate` inserts a row into H2, and the server transaction commits once the service method succeeds.
7. The controller returns `ResponseEntity.created(location).body(receipt)`; Jackson writes JSON.
8. The client receives **HTTP status, `Location` header, and JSON body** for assertions.
9. The test reads the H2 row via `JdbcTemplate` and deletes it by its own `request_key`.

A bug in any layer can fail the test: missing `@RestController`, `@Valid` not triggered, JSON field mismatch, missing DI bean, broken DB constraint, wrong HTTP status in exception advice, or server failing to bind a port.

### 2.1. Why is `TestRestTemplate` more convenient than plain `RestTemplate` in tests?

With `RANDOM_PORT`, Spring Boot 3.5 auto-configures `TestRestTemplate` with a root URI pointing to the newly started server. So:

```java
@Autowired TestRestTemplate client;

ResponseEntity<String> response =
        client.getForEntity("/api/orders/missing", String.class);
```

needs no manual port concatenation for most requests. This snippet assumes a test class annotated with `@SpringBootTest(RANDOM_PORT)`; the full code is in Section 6.

**Unlike ordinary `RestTemplate`:** `TestRestTemplate` is built for testing and **does not throw by default on `4xx/5xx`**. When calling an API with missing data, inspect the returned `ResponseEntity` and assert `isBadRequest()`/`isNotFound()` instead of expecting to catch `HttpClientErrorException`. That makes negative tests easier to write, though a test that merely calls the API without asserting the response can **falsely pass**.

### 2.2. When is `@LocalServerPort` used?

`@LocalServerPort` (Boot 3.5: `org.springframework.boot.test.web.server.LocalServerPort`) injects the actual listening port:

```java
@LocalServerPort
private int port;
```

Use it when you need to:
- Send requests using a client not configured by Boot with a root URI, such as JDK `HttpClient`.
- Build a callback URL for a fake client injected into test code.
- Explicitly ensure a request hits the primary listener without pointing at an external host by mistake.
- Debug base-path/proxy mismatches in the test environment.

**Do not** read this field in a static initializer or too early before the Spring context is running. Avoid setting `server.port=8080` in tests; `RANDOM_PORT` avoids port collisions across Maven forks/CI jobs on the same host.

### 2.3. Differences among `TestRestTemplate`, `WebTestClient`, and `RestClient`

- `TestRestTemplate` is a **Spring Boot test** utility suited to Spring MVC without adding WebFlux; it is auto-configured under `RANDOM_PORT`.
- `WebTestClient` offers a fluent response assertion API and can also bind to a live server, though Boot 3.5 setup requires `spring-webflux` on the classpath for it to be available per docs. Add WebFlux only with reason; do not accidentally change the application type.
- `RestClient` (Spring Framework) is a synchronous production HTTP client whose base URL can be built from the server port. It does not replace test assertion utilities on its own.
- `MockMvc` is a mock request dispatcher; used with `@SpringBootTest` to test internal MVC, it **does not turn into a real TCP request** just because the context uses `RANDOM_PORT`.
- `TestRestTemplate.withBasicAuth(...)` works for secured endpoints, though the sample omits Spring Security to stay focused on a business contract. In a real system, test authorization rather than disabling filters for convenience.

## 3. A single business contract used throughout the lesson

The example is an **order placement API for two product SKUs**:

| `sku` code | Unit price VND | Rule |
|---|---:|---|
| `BOOK` | 120.000 | Quantity from 1 to 10 |
| `PEN` | 20.000 | Quantity from 1 to 10 |
| Other codes | Unsupported | HTTP **422** |

Request JSON:

```json
{
  "requestKey": "run-001",
  "sku": "BOOK",
  "quantity": 2
}
```

Success: `POST /api/orders` → `201 Created` + `Location: /api/orders/<id>` + body containing `id`, `requestKey`, `sku`, `quantity`, `totalPriceVnd = 240000`. `GET /api/orders/{id}` → `200 OK` + body matching the stored record. The table has a **`UNIQUE(request_key)`** constraint so a client re-sending the same request key receives **409 Conflict**. This is a **demo duplicate-rejection policy**, not standard idempotent replay; if a real API wants idempotency, it may return the prior response for the same key and must store the request fingerprint/outcome.

Error cases:

| Case | Expected status | JSON error code |
|---|---:|---|
| Empty/blank `requestKey` | 400 | `INVALID_INPUT` |
| Null/blank `sku` | 400 | `INVALID_INPUT` |
| `quantity = 0` or `11` | 400 | `INVALID_INPUT` |
| Malformed JSON or empty body | 400 | `MALFORMED_JSON` |
| `sku = "UNKNOWN"` | 422 | `UNKNOWN_SKU` |
| `GET` non-existent ID | 404 | `ORDER_NOT_FOUND` |
| Same `requestKey` reused | 409 | `DUPLICATE_REQUEST` |

**Test data boundary:** No external database is called. Each test generates a UUID-based request key and deletes rows by key in `@AfterEach`. Each Spring context startup uses an in-memory H2 database and table solely for testing.

### 3.1. Why is there no fixed output ID?

Each order gets `UUID.randomUUID()`, so the `id` value cannot be predicted beforehand. Tests assert **non-blank**, that `Location` ends with the returned ID, and that `GET` works with that exact ID. Never hardcode a UUID and assert `response == a static string`; that is a classic cause of fixture collisions across repeated runs.

### 3.2. Testing business rules and HTTP contract separately yet linked

- **`PricingPolicy` unit test:** `BOOK x 2 = 240000`, invalid quantity throws, unknown SKU throws.
- **`OrderService` direct call:** same policy, stores in H2, transaction runs on the test thread.
- **Real HTTP POST:** same service code path, now passing through JSON, validation, routing, and the server thread. Compares total/invariants with the direct service call.
- **Real HTTP GET:** verifies the response reads from the persisted row rather than echoing the request in the controller.
- **JDBC readback:** confirms the HTTP write committed and is readable from another connection after the response.

Comparing “the same business logic” means asserting **the same invariants and meaningful error branches**, not blindly copying identical tests across layers to inflate test counts.

## 4. Runnable Java 17 + Spring Boot 3.5 project

Directory tree:

```text
random-port-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/orders/
    │       ├── OrdersApplication.java
    │       ├── PricingPolicy.java
    │       ├── UnknownSkuException.java
    │       ├── OrderNotFoundException.java
    │       ├── CreateOrderRequest.java
    │       ├── OrderReceipt.java
    │       ├── ApiError.java
    │       ├── OrderStore.java
    │       ├── OrderService.java
    │       ├── OrderController.java
    │       └── OrderExceptionAdvice.java
    └── test/
        ├── java/com/example/orders/
        │   ├── PricingPolicyTest.java
        │   └── OrderApiRandomPortTest.java
        └── resources/
            ├── application-test.properties
            └── schema.sql
```

No `src/main/resources/application.properties` is required. Only the test class activates profile `test`; H2 lives in **test dependencies**. When running the application with a production configuration, supply a real `DataSource`/DB inside an **authorized environment**, never using demo launch commands against live systems.

### 4.1. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>random-port-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
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
```

Boot's parent manages compatible versions of Spring MVC, TestContext, Jackson, H2, Hibernate Validator, HikariCP, and JUnit 5. `spring-boot-starter-validation` is critical: without a Bean Validation provider, `@NotBlank`/`@Min` may not execute as expected. `spring-boot-starter-test` brings in `TestRestTemplate`/Jupiter/AssertJ. Scoping H2 as `test` avoids shipping an in-memory DB driver in the production artifact.

### 4.2. Boot application

File **`src/main/java/com/example/orders/OrdersApplication.java`**:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

All code and tests reside in package `com.example.orders`, so Spring Boot finds `@SpringBootApplication` and component-scans controllers, services, and repositories. Tests using `RANDOM_PORT` start the default real Tomcat from `spring-boot-starter-web`.

### 4.3. Pure Java pricing policy

File **`src/main/java/com/example/orders/PricingPolicy.java`**:

```java
package com.example.orders;

import org.springframework.stereotype.Component;

@Component
public class PricingPolicy {

    public long totalFor(String sku, int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException(
                    "Quantity must be 1..10");
        }
        if (sku == null) {
            throw new UnknownSkuException();
        }

        long unitPrice = switch (sku) {
            case "BOOK" -> 120_000L;
            case "PEN" -> 20_000L;
            default -> throw new UnknownSkuException();
        };

        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

**Single source of truth:** the controller and service never recalculate totals; every order-creation path calls `PricingPolicy.totalFor(...)`. Unit tests can instantiate `new PricingPolicy()` directly to test rules without starting Spring. `Math.multiplyExact` guards against overflow if price ranges grow later, though test prices here are small.

File **`src/main/java/com/example/orders/UnknownSkuException.java`**:

```java
package com.example.orders;

public class UnknownSkuException extends RuntimeException {
    public UnknownSkuException() {
        super("SKU is not supported");
    }
}
```

File **`src/main/java/com/example/orders/OrderNotFoundException.java`**:

```java
package com.example.orders;

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException() {
        super("Order not found");
    }
}
```

Do not include sensitive SKUs, requestKeys, or IDs in public messages. API advice returns stable error codes and generic messages.

### 4.4. Request/response records

File **`src/main/java/com/example/orders/CreateOrderRequest.java`**:

```java
package com.example.orders;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank @Size(max = 64) String requestKey,
        @NotBlank String sku,
        @Min(1) @Max(10) int quantity) {
}
```

File **`src/main/java/com/example/orders/OrderReceipt.java`**:

```java
package com.example.orders;

public record OrderReceipt(
        String id,
        String requestKey,
        String sku,
        int quantity,
        long totalPriceVnd) {
}
```

File **`src/main/java/com/example/orders/ApiError.java`**:

```java
package com.example.orders;

public record ApiError(
        String code,
        String message) {
}
```

Java 17 records support JSON serialization/deserialization via Jackson in Spring Boot 3.5. `CreateOrderRequest` carries Bean Validation annotations; when the controller accepts `@Valid @RequestBody`, blank `requestKey`/`sku` or `quantity` outside 1..10 triggers `MethodArgumentNotValidException` → a 400 response via advice.

**Do not confuse DTO validation with domain invariants:** if another service calls `PricingPolicy` directly, controller `@Valid` does not run. `PricingPolicy` still checks `quantity` and `sku` as business rules, verified separately by plain Java tests. A production API should also cap `sku` length and request body size, normalize/canonicalize identifiers when required by contract, and enforce proper authorization.

### 4.5. JDBC repository

File **`src/main/java/com/example/orders/OrderStore.java`**:

```java
package com.example.orders;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OrderReceipt receipt) {
        jdbc.update("""
                INSERT INTO purchase_order
                    (order_id, request_key, sku,
                     quantity, total_price_vnd)
                VALUES (?, ?, ?, ?, ?)
                """,
                receipt.id(),
                receipt.requestKey(),
                receipt.sku(),
                receipt.quantity(),
                receipt.totalPriceVnd());
    }

    public Optional<OrderReceipt> findById(String id) {
        List<OrderReceipt> rows = jdbc.query("""
                SELECT order_id, request_key, sku,
                       quantity, total_price_vnd
                FROM purchase_order
                WHERE order_id = ?
                """,
                (rs, index) -> new OrderReceipt(
                        rs.getString("order_id"),
                        rs.getString("request_key"),
                        rs.getString("sku"),
                        rs.getInt("quantity"),
                        rs.getLong("total_price_vnd")),
                id);

        return rows.stream().findFirst();
    }
}
```

The repository uses prepared parameters rather than interpolating raw request values into SQL. `UNIQUE(request_key)` in the schema serves as the final barrier against re-submitting the same key; checking duplicates only in application memory races under concurrent requests. In the demo, Spring JDBC translates H2's unique constraint violation into `DuplicateKeyException`, which the advice maps to HTTP 409.

### 4.6. Service sharing the same rule and transaction

File **`src/main/java/com/example/orders/OrderService.java`**:

```java
package com.example.orders;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderStore store;
    private final PricingPolicy pricing;

    public OrderService(
            OrderStore store,
            PricingPolicy pricing) {
        this.store = store;
        this.pricing = pricing;
    }

    @Transactional
    public OrderReceipt create(CreateOrderRequest request) {
        long total = pricing.totalFor(
                request.sku(), request.quantity());

        OrderReceipt receipt = new OrderReceipt(
                UUID.randomUUID().toString(),
                request.requestKey(),
                request.sku(),
                request.quantity(),
                total);

        store.insert(receipt);
        return receipt;
    }

    @Transactional(readOnly = true)
    public OrderReceipt find(String id) {
        return store.findById(id)
                .orElseThrow(OrderNotFoundException::new);
    }
}
```

The HTTP controller simply delegates to the service; a test calling `OrderService.create(...)` directly runs the same pricing/store code, yet does not prove JSON/HTTP and executes its transaction **on the test thread**. Conversely, a POST over TCP runs the service on a **server request thread**. Sharing `OrderService` between two tests does not mean they share a transaction boundary.

### 4.7. Real REST controller

File **`src/main/java/com/example/orders/OrderController.java`**:

```java
package com.example.orders;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest input) {

        OrderReceipt saved = service.create(input);
        URI location = URI.create(
                "/api/orders/" + saved.id());

        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable String id) {
        return service.find(id);
    }
}
```

`ResponseEntity.created(...)` produces HTTP `201` and the `Location` header, and Jackson writes the JSON body. `@Valid` activates Bean Validation on the request DTO. `GET` returns the record or throws `OrderNotFoundException` so the advice returns 404.

**Status 201 does not mean data has committed in every architecture:** in this demo, the service transaction finishes before the controller returns, so JDBC readback works accurately. If a real app uses an outbox/async queue or eventual consistency, the contract may be `202 Accepted` requiring bounded polling instead of forcing synchronous commits.

### 4.8. Exception advice: structured HTTP errors

File **`src/main/java/com/example/orders/OrderExceptionAdvice.java`**:

```java
package com.example.orders;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidInput() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT", "Invalid order input"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> malformedJson() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "MALFORMED_JSON", "Malformed JSON body"));
    }

    @ExceptionHandler(UnknownSkuException.class)
    public ResponseEntity<ApiError> unknownSku() {
        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(new ApiError(
                        "UNKNOWN_SKU", "Unknown SKU"));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> missingOrder() {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND", "Order not found"));
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<ApiError> duplicateRequest() {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "DUPLICATE_REQUEST", "Duplicate request key"));
    }
}
```

Never catch every `DataIntegrityViolationException` and return `409`: the error could be a different constraint or broken schema rather than a duplicate request key. Catching `DuplicateKeyException` suffices here to represent the UNIQUE constraint. Real apps may need vendor-safe constraint-name inspection while avoiding logging PII/SQL with secrets.

The handler never leaks raw exception messages. In negative HTTP tests, assert **status + error code** instead of expecting a Java exception to be thrown across TCP to the client.

### 4.9. H2 schema and test-specific profile

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE purchase_order (
    order_id VARCHAR(36) PRIMARY KEY,
    request_key VARCHAR(64) NOT NULL UNIQUE,
    sku VARCHAR(32) NOT NULL,
    quantity INT NOT NULL,
    total_price_vnd BIGINT NOT NULL
);

CREATE INDEX idx_purchase_order_sku
    ON purchase_order(sku);
```

File **`src/test/resources/application-test.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

# For tests only; RANDOM_PORT chooses the web port dynamically.
spring.main.banner-mode=off
```

**Do not fix `server.port`**. `@SpringBootTest(RANDOM_PORT)` uses an actual random listening port. `@ActiveProfiles("test")` selects the H2 configuration in `src/test/resources`. CI must ensure no stray `SPRING_DATASOURCE_URL` or system property overrides this target; in environments with secrets or production networks, isolate runners and verify resolved targets before running SQL init.

**In-memory H2 does not replace every production DB:** PostgreSQL/MySQL dialects, locking, JSON, isolation levels, and schema rules can differ. When vendor-specific behavior must be proved, use Testcontainers with the matching DB engine and disposable containers. You can still keep `RANDOM_PORT` to test real HTTP ingress. Never run tests against a production or staging DB containing real data.

## 5. JUnit unit tests for plain Java business logic

File **`src/test/java/com/example/orders/PricingPolicyTest.java`**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PricingPolicyTest {

    private final PricingPolicy pricing =
            new PricingPolicy();

    @Test
    void bookTwoUnitsCost240000() {
        assertThat(pricing.totalFor("BOOK", 2))
                .isEqualTo(240_000L);
    }

    @Test
    void penThreeUnitsCost60000() {
        assertThat(pricing.totalFor("PEN", 3))
                .isEqualTo(60_000L);
    }

    @Test
    void maximumAllowedQuantityCanBePriced() {
        assertThat(pricing.totalFor("BOOK", 10))
                .isEqualTo(1_200_000L);
    }

    @Test
    void zeroQuantityIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("BOOK", 0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void quantityAboveLimitIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("BOOK", 11))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void unknownSkuIsRejected() {
        assertThatThrownBy(() ->
                pricing.totalFor("OTHER", 2))
                .isInstanceOf(UnknownSkuException.class);
    }
}
```

These **6 JUnit tests** open no Spring context and use no DB/port/HTTP. `PricingPolicy` invariants are tested rapidly here; they serve as the oracle for integration tests checking the same logic through the controller. When a subsequent HTTP test fails, we can tell a pure Java pricing bug apart from wiring/serialization/JDBC bugs.

## 6. JUnit `RANDOM_PORT` integration tests: business logic over real TCP and H2

File **`src/test/java/com/example/orders/OrderApiRandomPortTest.java`**:

```java
package com.example.orders;

import java.net.URI;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class OrderApiRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private OrderService service;

    @Autowired
    private PricingPolicy pricing;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Environment env;

    // JUnit Jupiter defaults to PER_METHOD:
    // each test invocation owns a separate Set.
    private final Set<String> requestKeys = new HashSet<>();

    private String ownedKey() {
        String key = "run-" + UUID.randomUUID();
        requestKeys.add(key);
        return key;
    }

    private long countForKey(String key) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM purchase_order
                WHERE request_key = ?
                """,
                Long.class, key);
        return count;
    }

    private ResponseEntity<OrderReceipt> post(
            String key, String sku, int qty) {

        return http.postForEntity(
                "/api/orders",
                new CreateOrderRequest(key, sku, qty),
                OrderReceipt.class);
    }

    private ResponseEntity<ApiError> postError(
            String key, String sku, int qty) {

        return http.postForEntity(
                "/api/orders",
                new CreateOrderRequest(key, sku, qty),
                ApiError.class);
    }

    @AfterEach
    void cleanOnlyOwnedRows() {
        for (String key : requestKeys) {
            jdbc.update("""
                    DELETE FROM purchase_order
                    WHERE request_key = ?
                    """, key);
            assertThat(countForKey(key)).isZero();
        }
    }

    @Test
    void randomPortStartsARealHttpServer() {
        assertThat(port).isBetween(1, 65535);

        ResponseEntity<ApiError> response =
                http.getForEntity(
                        "/api/orders/not-present", ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(404);
        assertThat(response.getBody().code())
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void postCreatesOrderAndReturns201WithLocation() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "BOOK", 2);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(response.getBody()).isNotNull();

        OrderReceipt body = response.getBody();
        assertThat(body.id()).isNotBlank();
        assertThat(body.requestKey()).isEqualTo(key);
        assertThat(body.sku()).isEqualTo("BOOK");
        assertThat(body.quantity()).isEqualTo(2);
        assertThat(body.totalPriceVnd()).isEqualTo(240_000L);

        URI location = response.getHeaders().getLocation();
        assertThat(location).isNotNull();
        assertThat(location.getPath())
                .isEqualTo("/api/orders/" + body.id());
    }

    @Test
    void httpTotalMatchesPureBusinessPolicy() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "PEN", 3);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(response.getBody().totalPriceVnd())
                .isEqualTo(pricing.totalFor("PEN", 3))
                .isEqualTo(60_000L);
    }

    @Test
    void directServiceAndRealHttpShareBusinessInvariant() {
        String directKey = ownedKey();
        OrderReceipt direct = service.create(
                new CreateOrderRequest(directKey, "BOOK", 3));

        String httpKey = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(httpKey, "BOOK", 3);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);

        OrderReceipt overHttp = response.getBody();
        assertThat(direct.id()).isNotEqualTo(overHttp.id());
        assertThat(direct.requestKey())
                .isNotEqualTo(overHttp.requestKey());
        assertThat(overHttp.totalPriceVnd())
                .isEqualTo(direct.totalPriceVnd())
                .isEqualTo(pricing.totalFor("BOOK", 3));
        assertThat(countForKey(directKey)).isEqualTo(1L);
        assertThat(countForKey(httpKey)).isEqualTo(1L);
    }

    @Test
    void getReadsThePersistedOrderThroughHttp() {
        String key = ownedKey();
        OrderReceipt created = post(key, "BOOK", 1).getBody();

        ResponseEntity<OrderReceipt> fetched =
                http.getForEntity(
                        "/api/orders/" + created.id(),
                        OrderReceipt.class);

        assertThat(fetched.getStatusCode().value())
                .isEqualTo(200);
        assertThat(fetched.getBody()).isEqualTo(created);
    }

    @Test
    void serverCommittedRowIsVisibleToTestJdbcConnection() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> response =
                post(key, "BOOK", 4);

        assertThat(response.getStatusCode().value())
                .isEqualTo(201);
        assertThat(countForKey(key)).isEqualTo(1L);

        Long savedTotal = jdbc.queryForObject("""
                SELECT total_price_vnd
                FROM purchase_order WHERE request_key = ?
                """, Long.class, key);

        assertThat(savedTotal).isEqualTo(480_000L);
    }

    @Test
    void sameRequestKeyProducesConflictAndOneRow() {
        String key = ownedKey();
        ResponseEntity<OrderReceipt> first =
                post(key, "BOOK", 1);
        ResponseEntity<ApiError> second =
                postError(key, "BOOK", 1);

        assertThat(first.getStatusCode().value())
                .isEqualTo(201);
        assertThat(second.getStatusCode().value())
                .isEqualTo(409);
        assertThat(second.getBody().code())
                .isEqualTo("DUPLICATE_REQUEST");
        assertThat(countForKey(key)).isEqualTo(1L);
    }

    @Test
    void differentRequestKeysCanCreateSameProduct() {
        String firstKey = ownedKey();
        String secondKey = ownedKey();

        OrderReceipt a = post(firstKey, "PEN", 2).getBody();
        OrderReceipt b = post(secondKey, "PEN", 2).getBody();

        assertThat(a.id()).isNotEqualTo(b.id());
        assertThat(a.totalPriceVnd())
                .isEqualTo(b.totalPriceVnd());
        assertThat(countForKey(firstKey)).isEqualTo(1L);
        assertThat(countForKey(secondKey)).isEqualTo(1L);
    }

    @Test
    void blankRequestKeyReturns400() {
        ResponseEntity<ApiError> response =
                postError("  ", "BOOK", 1);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
    }

    @Test
    void missingSkuReturns400AndDoesNotInsert() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, null, 1);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void zeroQuantityReturns400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "BOOK", 0);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void quantityAboveLimitReturns400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "BOOK", 11);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("INVALID_INPUT");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void unsupportedSkuReturns422Not400() {
        String key = ownedKey();
        ResponseEntity<ApiError> response =
                postError(key, "UNKNOWN", 2);

        assertThat(response.getStatusCode().value())
                .isEqualTo(422);
        assertThat(response.getBody().code())
                .isEqualTo("UNKNOWN_SKU");
        assertThat(countForKey(key)).isZero();
    }

    @Test
    void unknownOrderIdReturns404() {
        ResponseEntity<ApiError> response =
                http.getForEntity(
                        "/api/orders/" + UUID.randomUUID(),
                        ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(404);
        assertThat(response.getBody().code())
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void malformedJsonReturnsStructured400() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request =
                new HttpEntity<>("{ invalid json", headers);

        ResponseEntity<ApiError> response = http.exchange(
                "/api/orders",
                HttpMethod.POST,
                request,
                ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("MALFORMED_JSON");
    }

    @Test
    void emptyBodyReturnsStructured400() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<String> request =
                new HttpEntity<>("", headers);

        ResponseEntity<ApiError> response = http.exchange(
                "/api/orders",
                HttpMethod.POST,
                request,
                ApiError.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
        assertThat(response.getBody().code())
                .isEqualTo("MALFORMED_JSON");
    }

    @Test
    void absoluteUrlUsingInjectedPortReachesSameServer() {
        String key = ownedKey();
        OrderReceipt created =
                post(key, "PEN", 1).getBody();

        String absoluteUrl =
                "http://127.0.0.1:" + port
                        + "/api/orders/" + created.id();

        ResponseEntity<OrderReceipt> response =
                http.getForEntity(
                        absoluteUrl, OrderReceipt.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isEqualTo(created);
    }

    @Test
    void selectedProfileUsesTestOnlyDatabase() {
        assertThat(env.getActiveProfiles())
                .contains("test");

        String jdbcUrl =
                env.getProperty("spring.datasource.url");
        assertThat(jdbcUrl)
                .startsWith("jdbc:h2:mem:orders_test");
    }
}
```

**QA notes on the example:**
- `@SpringBootTest(RANDOM_PORT)` already integrates `SpringExtension` for JUnit Jupiter; no extra `@ExtendWith` is needed.
- `@Autowired TestRestTemplate`'s root URI binds automatically to the server; the absolute URL test proves `@LocalServerPort` holds a real value.
- Negative tests **assert response status and JSON `error.code`**, rather than catching `HttpClientErrorException`, because `TestRestTemplate` intentionally does not throw on 4xx/5xx.
- `@AfterEach` deletes only the `request_key`s registered by the current test invocation; it never runs `TRUNCATE` or a whole-table `DELETE`.
- Direct `OrderService.create` and HTTP `POST` execute the same pricing/store logic, yet run in different **transactions and threads**.
- `@TestInstance(PER_METHOD)` is Jupiter's default, so `Set<String> requestKeys` is not shared across test methods; the suite does not enable parallelism. If enabling concurrency, re-evaluate context/DB/cleanup resource ownership.
- `GET` after `POST` confirms the record is serialized/deserialized consistently and read back from the saved DB, rather than merely echoing the request in the controller.

## 7. Run commands and expected results

Requires JDK **17 or higher**, Maven, and dependencies reachable from the configured repository. Run from the directory containing `pom.xml`:

```bash
mvn --batch-mode --no-transfer-progress test
```

Run each class individually:

```bash
mvn -Dtest=PricingPolicyTest test
mvn -Dtest=OrderApiRandomPortTest test
```

Inspect dependency versions:

```bash
mvn dependency:tree
```

**Expected:** `PricingPolicyTest` has **6 `@Test` methods**; `OrderApiRandomPortTest` has **18 `@Test` methods**, totaling **24 tests**, all passing with Spring Boot 3.5.0 + H2/Java 17 on a runner configured as described. These are **source-derived expectations**, not Maven output executed while authoring this document. Check `target/surefire-reports` for actual class counts, failures, and elapsed time during execution.

Never hardcode ports in stdout or assertions: the port is chosen by the OS/embedded server at each `ApplicationContext` startup and can differ across runs. Do not claim `server.port=8080`, nor assert `port != 8080`, since a dynamic port could theoretically land on any free port.

### 7.1. HTTP contract example (illustrative, not captured output)

Suppose the server is running and a client sends an example key:

```http
POST /api/orders HTTP/1.1
Host: localhost:54231
Content-Type: application/json

{"requestKey":"example-key-123","sku":"BOOK","quantity":2}
```

Response structure:

```http
HTTP/1.1 201 Created
Location: /api/orders/<generated-uuid>
Content-Type: application/json

{
  "id": "<generated-uuid>",
  "requestKey": "example-key-123",
  "sku": "BOOK",
  "quantity": 2,
  "totalPriceVnd": 240000
}
```

`<generated-uuid>` above is **only placeholder notation representing dynamic JSON/HTTP output in the example**, not a literal string returned by the code; tests never use placeholder IDs or compare requests against static snapshots. In a real run, the port/UUID differ and `Content-Type` may include charset/other headers. The stable values tests assert are **status, URI path shape, request key, sku, quantity, total**.

Duplicate error:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"DUPLICATE_REQUEST","message":"Duplicate request key"}
```

This is the expected shape defined by `OrderExceptionAdvice`; it contains no PII or exception stack traces. If a real API uses RFC 9457 Problem Details, replace `ApiError` with `ProblemDetail` and test the corresponding contract fields.

## 8. `RANDOM_PORT` and rollback: the risk of leftover data

This is especially important. In Spring TestContext, a test method annotated with `@Transactional` is usually wrapped in a test-managed transaction that rolls back after the test. With `RANDOM_PORT`, however, **the HTTP client and server run on different threads**; `ThreadLocal`-bound transaction context does not propagate across a TCP request. Therefore:
- Data written by a test **calling the service directly** inside the test transaction can roll back with the test.
- Data created by an HTTP request **on the server request thread** has its own transaction and **really commits**.
- `@Transactional` on the test class **does not** turn `POST`/`GET` into one cross-TCP transaction.
- `@AfterEach` runs inside the test-managed transaction if the test has `@Transactional`; a JDBC cleanup statement there can **also roll back**, leaving the HTTP-committed row behind.

### 8.1. A common anti-pattern

```java
// Illustrative anti-pattern, NOT part of the runnable tests.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class MisleadingRollbackTest {

    @Autowired TestRestTemplate client;

    @Test
    void createsOrder() {
        client.postForEntity("/api/orders", request, String.class);
        // Wrong if you believe the server POST will roll back with the test!
    }
}
```

The `request` variable in this snippet is hypothetical and not part of the runnable project in Section 6. What matters is that **a test-managed transaction on the client test thread does not roll back server-side transactions**. Even when the test method passes and the `@Transactional` test rolls back, HTTP writes can persist.

### 8.2. The strategy used by this demo: out-of-transaction cleanup by request key

`OrderApiRandomPortTest` **does not put `@Transactional`**, so that:
- The service called over HTTP commits/rolls back according to the real service configuration.
- The test can read the committed row via `JdbcTemplate` after the response.
- `@AfterEach` runs a **fresh JDBC operation** to delete rows for its own keys without getting rolled back by a test transaction.
- Other tests stay unaffected because each test method owns unique request keys, and cleanup never deletes another test's rows.
- If HTTP returns a validation error before insert, key-based cleanup remains safe (deletes 0 rows).

**This does not guarantee every side effect was cleaned up.** If the service publishes Kafka events, sends emails, or creates files, configure appropriate cleanup, mocking, or isolated sandboxes. If a test fails mid-async workflow, wait for async work to finish with a timeout before teardown. Never use `Thread.sleep` as proof of eventual consistency.

### 8.3. When you want to use `@Transactional` alongside `RANDOM_PORT`

You may want transaction tests in a separate **direct-service scenario**, unmixed with HTTP cleanup. For HTTP tests, use:
- Per-test schema/database or container;
- Scoped fixture keys + cleanup;
- Bounded polling for eventual consistency;
- A tightly secured test-only reset endpoint **only in an isolated environment** if truly needed;
- Cleanup via `TransactionTemplate` that does not join a rolling-back transaction, with clear transaction semantics.

**Do not enable `@DirtiesContext` after every HTTP test as a patch**: a fresh context does not delete rows committed to an external DB, and restarts are expensive. With in-memory H2, closing the context can affect DB lifecycle, yet it is not a data-isolation strategy that transfers to production PostgreSQL.

## 9. Choosing assertions for application-level end-to-end HTTP

### 9.1. Success must verify status, body, headers, and persisted state

A minimal yet worthwhile `POST` test checks:

- Exact status **201**, not merely “2xx”.
- Response `Location` present, path matching `/api/orders/{id}`.
- JSON body has accurate `requestKey`, `sku`, `quantity`, `totalPriceVnd`.
- `GET Location` returns the newly created order.
- A JDBC read from a separate connection sees the committed row.
- After cleanup, `countByKey == 0`.

Asserting only `postForObject(...) != null` misses returning 200 instead of 201, missing `Location`, quantity mismatches, or unpersisted rows.

### 9.2. Negative tests must not call the service directly to fake failures

To prove JSON validation:
- Send an **HTTP request** via `TestRestTemplate`, not `controller.create(...)` directly.
- For blank/invalid payloads, assert HTTP **400** and `error.code` `INVALID_INPUT`.
- For malformed JSON, assert HTTP **400** and code `MALFORMED_JSON`.
- For unknown domain SKUs, assert **422** (per demo contract), distinct from validation 400.
- For duplicate keys, assert **409** and DB row count **1**, not just counting exceptions.
- For unknown IDs, assert **404** and code `ORDER_NOT_FOUND`.

Controller unit tests remain valuable for fast feedback, yet they do not replace negative HTTP contract tests when routing, converters, and exception resolvers are the goal.

### 9.3. `ResponseEntity` and type safety

`TestRestTemplate.postForEntity(path, body, OrderReceipt.class)` uses HTTP message converters to deserialize JSON into a Java record. If the response renames a field or changes a type, the test fails at JSON binding or assertion. For collections/generic types, use `exchange(...)` with `ParameterizedTypeReference<List<OrderReceipt>>` instead of raw `List.class`.

For error bodies, the example uses `ApiError.class` matching the contract. If the server returns non-JSON errors (gateway/404 HTML), Jackson deserialization fails—**which is useful evidence** of a contract violation. Do not use `String.class` for every response just to dodge type-mismatch handling when the API promises a JSON schema.

## 10. Diagnosing CI failures at the right layer

| Symptom | Likely cause | Diagnosis |
|---|---|---|
| `Connection refused` calling localhost | Server didn't start or client hit wrong port | Check `RANDOM_PORT`, `@LocalServerPort`, context startup errors |
| Fixed port 8080 already in use | `DEFINED_PORT` used or config override | Drop fixed port, use `RANDOM_PORT`; check system properties |
| `@Autowired TestRestTemplate` is null | Wrong Boot test context | Ensure `@SpringBootTest(RANDOM_PORT)`, dependencies, package |
| `404` on POST when controller exists | Wrong mapping/base path/context path | Check request URI, servlet path, controller scanning |
| `400` instead of 201 | `@Valid`/JSON binding/input fields wrong | Check status + `error.code`; inspect request DTO |
| `409` appears from another test | Fixed `requestKey` reused, leftover data | UUID keys, per-test cleanup, DB isolation |
| `422` even though SKU is valid | Pricing policy disagrees with contract | Unit test `PricingPolicy` + direct-service check |
| `500` from unhandled `DuplicateKeyException` | Advice missing mapping or different exception type | Check JDBC translator/constraint; avoid catch-all |
| `200` but no DB row | Controller echoed request, async persistence | JDBC readback or bounded await on eventual outcome |
| `@Transactional` test green yet DB row remains | Server thread transaction committed | Scoped cleanup outside test tx |
| Same tests randomly PASS/FAIL | Shared H2 DB, test-order/parallel cleanup | Unique keys, no global TRUNCATE, inspect test reports |
| JDBC test sees wrong URL | Runner property override, `@ServiceConnection` | Verify resolved/actual DataSource in sandbox |
| Tests return `401/403` when app has Security | Authentication/CSRF active | Supply proper test identity, never disable security |
| `WebTestClient` fails to inject | Missing `spring-webflux`/test setup | Use `TestRestTemplate` or add required config |
| MockMvc passes but HTTP test fails | Servlet container, routing, filter/socket mismatch | Keep both layers when needed, debug HTTP status/headers |
| Management endpoint test hits wrong port | Management server runs separately | Use `@LocalManagementPort`/management test client |
| JSON error fails to parse as `ApiError` | Proxy/HTML error or advice didn't run | Inspect sanitized raw response |
| CI hangs for a long time | Real HTTP client timeout/retry or DB wait | Bounded request timeouts, CI test budget, diagnostics |

### 10.1. Find the exact root cause instead of blindly raising timeouts

A request timeout is not always because the server is “slow”. Possibilities include wrong TCP port, DNS/proxy env settings, Tomcat failing to start, exhausted DB connection pool, deadlock when tests share a connection across transaction and server, or an async task waiting forever. Use bounded client timeouts, log non-sensitive timestamps/trace IDs, and distinguish connect timeouts from response timeouts.

`RANDOM_PORT` avoids port collisions, yet does not replace **readiness/liveness of real dependencies**. CI should never hit production services; when production-like DB semantics are needed, use disposable containers with clear startup timeouts and cleanup.

## 11. When the application uses Spring Security

The sample project **omits** `spring-boot-starter-security` to focus on HTTP + business logic. In a real application, requests to `POST /api/orders` may encounter:
- `401` if identity is missing;
- `403` if roles are insufficient;
- `403` due to missing CSRF token on unsafe methods when CSRF policy applies;
- `302` redirect if a form-login entry point is configured;
- `429` if rate limiting/filters enforce limits.

**Never** fix tests by deleting `SecurityFilterChain` just to get 201 from GET/POST. Test with sandbox accounts/tokens, proper authorities/roles, and real CSRF policies. `TestRestTemplate.withBasicAuth(...)` fits only HTTP Basic apps; for OAuth2/JWT, send **test-only** Authorization bearer tokens and never print tokens in logs.

When asserting authorization:
1. Anonymous requests are rejected with the right status code;
2. Wrong roles are rejected with the right status code;
3. Right roles traverse full HTTP and create **exactly one** row;
4. Rejected requests produce zero side effects;
5. Error bodies leak no stack traces or secrets.

Security is part of the real HTTP integration contract and must not be turned off just to measure business logic.

## 12. `MANAGEMENT_PORT`, HTTPS, proxies, and network boundaries

### 12.1. Separate management server port

If `management.server.port` differs from application `server.port`, Spring Boot 3.5 can start the management server on **a separate random port** under `RANDOM_PORT`. `@LocalServerPort` gives the main application port, **not necessarily** the management port. To test Actuator health/metrics on a separate management context, obtain the actual management port appropriately (e.g., `@LocalManagementPort`) and test its security/network path separately.

Never take a `200` from `/api/orders` as proof that `/actuator/health` on the management port also returns `200`. They can use different ports, servlet contexts, and security configs.

### 12.2. HTTPS and reverse proxies

The sample tests use loopback HTTP:
- They test the real Tomcat HTTP stack, **not** TLS certificates/truststores/mTLS.
- They do not test nginx/ingress `/api` rewrites, forwarded headers, sticky sessions, or load balancers.
- They do not test firewalls, network policies, or public DNS.
- They do not test cookie Domain/SameSite/Secure on a public hostname unless configured.

When deployment contracts rely on proxies/TLS, add E2E tests against an **ephemeral deployed environment** with proper hostnames and identities. Avoid running destructive tests against production data just because `RANDOM_PORT` cannot cover edge infrastructure.

### 12.3. WebFlux vs Spring MVC

In a WebFlux-only application, `RANDOM_PORT` still starts a real web server, though threading, body streaming, and client stacks differ. `WebTestClient` suits WebFlux/reactive tests. When both MVC and WebFlux are on the classpath, Spring Boot defaults to MVC unless `spring.main.web-application-type=reactive`. Never copy a servlet `@AutoConfigureMockMvc` snippet assuming it tests Netty/reactive semantics.

## 13. Test isolation and performance in larger suites

### 13.1. Context caching

Spring's TestContext cache is keyed by merged test configuration, including `classes`, profiles, properties, context customizers (such as `@MockitoBean`/`@DynamicPropertySource`), loaders, and more. Two test classes with identical configuration share the same `ApplicationContext` + embedded server; port numbers are not test identity. Changing profiles, properties, or bean overrides produces a different cache key and starts a new server.

Never put `@DirtiesContext` after every test just to “get a fresh port”. It restarts the context and **does not delete DB rows outside the context**. Clean up data at the proper scope, separating contexts only when the bean graph/state genuinely differs.

### 13.2. Running in parallel without wiping the whole DB

If JUnit parallel execution is enabled, tests may share the Spring context and H2:
- Every test uses a unique `request_key`.
- Queries/cleanup filter by request key; never `TRUNCATE purchase_order`.
- `@AfterEach` cleanup must execute after server side effects finish.
- Never share Mockito stubs or mutable global static state casually.
- If code performs async writes, await completion before verifying or cleaning up data.
- If the DB has shared global inventory/quotas, unique request keys alone are **not enough** to prevent races; transactions, isolation, locks, and dedicated concurrency tests are needed.

The demo keeps parallel execution off to keep the focus clear. Running a `@DirtiesContext` test class concurrently with another class sharing the same context can shut down the server mid-request, causing flaky connection errors.

### 13.3. Why not mock `OrderService` in this lesson?

If you use `@MockitoBean OrderService`, the test only proves the controller and mocked client talk to each other; it **does not** prove prices are calculated by `PricingPolicy`, the real JDBC repository runs, unique constraints work, or transactions commit. Mocking makes complete sense in a `@WebMvcTest` slice isolating controller mappings, yet **defeats the goal of “testing the same business logic end-to-end via `RANDOM_PORT`”**.

Reasonable exception: external gateways (payment, email, cloud) should use fakes/stubs to avoid real-world side effects, while keeping internal services and repositories real. Never use production credentials, databases, or API endpoints in integration tests.

## 14. Test plan for similar business features

| Test case | Approach | Required evidence |
|---|---|---|
| Business pricing | Unit `PricingPolicy` | BOOK/PEN and valid quantity pass; unknown SKU throws |
| Spring bean path | Direct service call | Same total + JDBC row |
| Server startup | `RANDOM_PORT` + `@LocalServerPort` | Actual port > 0, HTTP GET gets handler response |
| Successful POST | `TestRestTemplate` | 201 + Location + JSON fields |
| GET persistence | GET by ID returned from POST | 200 + matching receipt |
| Commit visibility | JDBC read after HTTP POST | H2 row committed with exact total |
| Duplicate key | Two POSTs with same `requestKey` | 201, 409, and single row |
| Unique requests | Two different keys | Two different IDs, one row per key |
| Invalid body | Blank/missing fields, bad quantity | 400 + `INVALID_INPUT`, no insert |
| Invalid JSON syntax | Malformed raw HTTP request | 400 + `MALFORMED_JSON` |
| Invalid domain value | Unsupported SKU | 422 + `UNKNOWN_SKU` |
| Missing ID | GET unknown UUID | 404 + `ORDER_NOT_FOUND` |
| Error disclosure | Negative responses | Safe code/message only; no stacktrace |
| Cleanup | `@AfterEach` by `ownedKey` | Zero leftover test rows |
| Test profile | `@ActiveProfiles("test")` | In-memory H2, never production |
| Security (when present) | Token/role/CSRF | 401/403/2xx per policy |
| Split management port | Separate real port | Actuator path/status/security verified |
| Async business logic | HTTP 202 and poll | Await outcome, timeout, zero cross-test residue |
| Production DB semantics | Disposable Testcontainers | Matching dialect/isolation/locking |
| Proxy/TLS | Deployment-like E2E | Edge config verified |

### Test naming style

A test named `createsOrder` is vague; prefer `postCreatesOrderAndReturns201WithLocation`, `sameRequestKeyProducesConflictAndOneRow`, `serverCommittedRowIsVisibleToTestJdbcConnection`. Specific names tell readers **the path and the evidence** without opening the implementation.

**Do not turn every case into a fresh server startup.** Sharing a context via TestContext caching plus independent request keys keeps the suite fast while preserving isolation.

## 15. Checklist before accepting `RANDOM_PORT` tests in CI

- [ ] Chose `RANDOM_PORT` because evidence of real TCP/server execution is required, not just controller method calls.
- [ ] POM includes Spring Boot web/test/JUnit and required data dependencies.
- [ ] `@LocalServerPort` is used when absolute URLs are needed; port 8080 is never hardcoded.
- [ ] `@Autowired TestRestTemplate` or a real client bound to the actual port is used.
- [ ] Tests assert **exact** HTTP status codes, not just 2xx.
- [ ] Location header, JSON response, and error body contracts are asserted.
- [ ] Business rules are unit-tested separately and re-verified over HTTP on representative cases.
- [ ] Internal services/repositories are not all mocked out when proving business integration.
- [ ] Bean Validation dependency is present; `@Valid` runs before the service.
- [ ] Negative tests distinguish 400 (input), 404 (missing), 409 (duplicate), and 422 (unsupported domain).
- [ ] Persistence is verified by real JDBC readback after the HTTP response.
- [ ] You understand the test thread does not share a transaction with the server thread and HTTP writes do not auto-roll back.
- [ ] Cleanup deletes by test-owned key in `@AfterEach`/finally, without global truncate.
- [ ] H2/test config lives only on the test classpath and cannot be overridden by a production URL.
- [ ] Zero secrets, PII, real customer data, or external production clients in the test suite.
- [ ] If vendor DB semantics matter, disposable Testcontainers replace production DBs.
- [ ] `@SpringBootTest(RANDOM_PORT)` is not confused with `@AutoConfigureMockMvc`.
- [ ] You do not assume random ports must differ across every test method; context caching may reuse them.
- [ ] If security is enabled, authentication, authorization, and CSRF are tested per real policy.
- [ ] If a separate management port is configured, the actual management listener is tested separately.
- [ ] You do not claim `RANDOM_PORT` tests TLS, ingress, proxies, or public network paths.
- [ ] Test data and async operations are cleaned up/awaited before the test finishes.
- [ ] Parallelism is not enabled over shared mutable DB/global state without evaluation.
- [ ] Ran `mvn test`, verified discovered test count and `target/surefire-reports`.
- [ ] When a test FAILS, sanitized status/headers/body plus actual request URI/test key are captured for diagnosis.

**Conclusion:** `@SpringBootTest(webEnvironment = RANDOM_PORT)` is the right tool to verify **the same business logic inside a real Spring Boot application at the HTTP boundary**, from JSON input through validation/controller/service/transaction/JDBC to HTTP responses and stored data. Combine **unit tests for invariants**, **real HTTP tests for contracts**, and **ownership-scoped cleanup** to avoid order-dependent test suites. Understanding transaction boundaries and what is proved prevents two common misconceptions: **`MockMvc` is not an HTTP socket**, and **test-thread rollback does not automatically undo a `POST` executed on the server thread**.

### Official documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications: MOCK, RANDOM_PORT, TestRestTemplate, and Transactions](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @SpringBootTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot 3.5 — @LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html)
- [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)
- [Spring Framework 6.2 — Integration Testing / Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
- [Spring Boot 3.5 — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [JUnit Jupiter 5.12 — User Guide](https://docs.junit.org/5.12.0/user-guide/)
