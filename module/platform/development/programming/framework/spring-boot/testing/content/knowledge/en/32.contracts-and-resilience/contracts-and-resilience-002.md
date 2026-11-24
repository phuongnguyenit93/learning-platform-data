# Request, Response, Schema, and Compatibility Contracts in Spring Boot Test

## 1. Why can a working API still break clients?

A Spring Boot application exposes an order API. All service unit tests are green, the endpoint returns HTTP 200, and the database reads and writes properly. Yet after a deployment, an older client stops working because the backend team renamed `customerId` to `customer`, changed `quantity` from a JSON number to a string, removed a required field, or replaced HTTP 404 with 200 and an empty body. This is an **API contract violation**, not necessarily a bug in an isolated Java method.

A **contract** is the set of expectations that the caller (*consumer*) and the supplier (*provider*) both rely on:

- **Request**: URL/path variables, HTTP method, query parameters, headers, `Content-Type`, `Accept`, authentication, body, and constraints such as required/minimum/enum.
- **Response**: HTTP status, headers (`Location`, ETag, content type...), JSON field names/types/required/nullable, body, and the meaning of each error code.
- **Schema**: a machine-readable and verifiable representation, such as **JSON Schema Draft 2020-12** for payloads, **OpenAPI** for the full HTTP interface, or Avro/Protobuf schemas for messaging.
- **Compatibility**: whether a new provider version still satisfies supported consumers, both structurally **and semantically**.
- **Resilience**: when requests time out, drop connections, retry, or downstream fails, the **error contract and idempotency** must remain consistent; contract tests do not replace fault injection.

**Lesson objectives (parent context: “Contracts and Resilience”):**

1. Turn HTTP request/response specifications into implementation-independent assertions.
2. Distinguish **provider contract test**, **consumer-driven contract (CDC)**, **schema test**, **integration test**, and **end-to-end test**.
3. Verify method/path, headers, media type, status, response body, and schema with **MockMvc**.
4. Validate request bodies against **JSON Schema**, while proving Spring MVC `@Valid` and Jackson enforce critical cases.
5. Understand **required/optional/nullable**, `additionalProperties`, JSON types, enums, and the impact of renaming fields.
6. Distinguish **backward compatibility** (old consumers can read new producer output) from **forward compatibility** (new consumers accept old producer output when planned).
7. Verify an **added optional response field** does not break a V1 consumer, whereas removing `id`, changing `quantity` to a string, or introducing an unknown enum value can break the contract.
8. See clearly why **adding a request field** can fail if an old server uses strict deserialization, and why **changing requiredness** is a dangerous change.
9. Build a **Java 17 + Spring Boot 3.3.5 + Gradle** project with controller/service/fixtures and versioned JSON Schemas.
10. Use a **real JSON Schema validator** to test schemas instead of mistaking a few `jsonPath` assertions for full Schema Draft validation.
11. Verify **ProblemDetail/RFC 9457** for 400/404 errors and ensure no stack traces or sensitive data leak.
12. Design CI publishing/verification for contracts, Pact or Spring Cloud Contract, OpenAPI diff, versioning, and deprecation policies.
13. Clearly separate what is proven in MockMvc from what requires supplementary HTTP transport/database/consumer tests.

**Pinned versions:** Java 17; **Spring Boot 3.3.5** (Spring Framework 6.1/Spring MVC); Jackson 2; JUnit Jupiter; JSON Schema Draft 2020-12; `com.networknt:json-schema-validator:1.5.9` in **test scope**. This code targets **Boot 3.3**; Spring Boot 4 has different packages/modules and Jackson defaults that must be re-verified on upgrade.

## 2. Concrete contract of the example API

The API manages an in-memory set of mock orders without connecting to a database or making outbound HTTP calls:

| Operation | Request | Valid response | Primary errors |
|---|---|---|---|
| Read an order | `GET /api/v1/orders/{id}`; `Accept: application/json` | `200 OK`, `Content-Type: application/json`, `X-Contract-Version: 1`, order JSON | `404`, `application/problem+json` when ID does not exist |
| Create an order | `POST /api/v1/orders`; `Content-Type: application/json` | `201 Created`, `Location: /api/v1/orders/{id}`, `X-Contract-Version: 1`, order JSON | `400` validation/malformed, `415` wrong media type |
| JSON request | `customerId` non-empty/non-whitespace string; `quantity` integer >= 1 | Undeclared fields are rejected per the example's **strict input** policy | `400`, ProblemDetail |
| JSON response | `id`, `customerId`, `quantity`, `status` **required** | Status `NEW` or `SHIPPED`; `deliveryNote` **optional** | Do not arbitrarily alter field/type/status |
| `deliveryNote` | **Optional** | May include a string when the order has a note, or be **absent** | Must not become required for old consumers |

**Sample request:**

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"cust-a","quantity":2}
~~~

**Sample response:**

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/orders/ord-201
X-Contract-Version: 1

{"id":"ord-201","customerId":"cust-a","quantity":2,"status":"NEW"}
~~~

**Not-found error:**

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Order not found",
  "errorCode": "ORDER_NOT_FOUND"
}
~~~

The error snippet above illustrates the minimal contract fields. Spring may add `instance` in specific cases; the project's error schema allows that field or approved metadata. Do not assert raw JSON strings by property order, whitespace, or boundary formatting.

**Why does status 201 matter?** A consumer may only proceed or read `Location` when receiving 201. Changing 201 to 200 even with the same body is an observable behavioral change. **Why do headers matter?** Content-Type drives the parser, Location gives the path of the newly created resource, and X-Contract-Version is example-specific metadata; this header does not replace a versioning policy.

## 3. Four distinct testing layers

| Layer | Who defines expectations? | Evidence | Limitations |
|---|---|---|---|
| Service unit test | Provider developers | Pure Java business logic/validation | Unaware of HTTP serialization/status |
| **Provider HTTP test (MockMvc)** | HTTP contract checked inside provider repo | Spring MVC mapping, Jackson, validation, status, headers, body | No TCP, TLS, proxy, DNS |
| **Schema validation** | Governed JSON Schema/OpenAPI | Payloads match types/required/enum/range | Does not automatically verify business semantics or HTTP headers |
| **Consumer-driven contract** | Consumers require the provider to fulfill interactions | Provider verifies contracts across provider states, stubs for consumer | Does not prove every integration/network edge case |
| Real HTTP server integration | API runs over real sockets and HTTP client | Transport, filters, URL, serializer, sometimes DB | Higher environment cost |
| End-to-end with real consumer | Two systems collaborating | Real runtime compatibility | Flaky, slow, data/infra dependent |

**MockMvc mocks servlet requests/responses inside the JVM** and does not run embedded Tomcat over a TCP port. It is well suited for keeping controller contracts stable in CI. When you need to test connection pooling, TLS, redirects, proxy cookies, or client SDKs, add `@SpringBootTest(webEnvironment = RANDOM_PORT)` + a real client.

**“API documentation” does not equal “contract enforcement”.** Having a pretty OpenAPI YAML while tests mock out the entire controller can fail to catch a provider returning the wrong field. To be useful, contracts must be **tied to automated verification**. Do not simply generate an output snapshot and regenerate it whenever code changes without asking whether any consumer broke.

## 4. Backward/forward compatibility: defined by the data reader

**Backward compatibility (provider direction):** A new provider P2 still serves committed consumers P1. For example, the new response adds an *optional* `deliveryNote`, while preserving `id`, `customerId`, `quantity`, and `status` with the same types and meaning. A consumer designed to **ignore unknown response fields** can keep working.

**Forward compatibility (reader/consumer direction):** A new consumer C2 can read data produced by an older provider P1 when required by policy. To do so, C2 must not require a response field that exists only in P2 unless a documented default/fallback exists.

**Asymmetry note:** For **responses**, adding an optional field is usually safe if consumers ignore unknown properties; for **requests**, adding an unknown field to a payload sent to a **strict old server** can cause the server to return 400. “Additive = always compatible” is a false conclusion.

| Change | What can old consumers hit? | Policy/recommendation |
|---|---|---|
| Add optional response field | Usually safe if reader is tolerant | Verify with real consumer contract |
| Add required response field on new consumer | Old provider lacks that field | Use fallback or new version |
| Remove/rename required response field | Old consumer cannot find key | **Breaking** |
| Change `quantity: 2` to `"2"` | JSON number → string | **Breaking**, even if UI still displays “2” |
| Change `status: NEW` to `READY` | Unknown enum | Potentially breaking, depends on consumer tolerance |
| `null` instead of absent field | Parser/validation may differ | Define explicit nullable/optional contract |
| Replace 201 with 200 | Consumer may branch on status | Potentially **breaking** |
| Change `Location` or media type | Consumer parsing/follow-up request breaks | Potentially **breaking** |
| Add optional request field | Strict old server may return 400 | Check provider policy |
| Add required request field on new server | Old client does not send it | **Breaking** |
| Change optional query param to required | Old client omits param | **Breaking** |
| Narrow error codes/statuses | Consumer error handling diverges | Review compatibility |
| Increase/decrease timeouts or rate limits | Affects runtime/retries | Verify resilience contract outside schema |

**Open-world vs. closed-world:** For the response schema serving V1 consumers, this lesson uses `additionalProperties: true` so consumers can ignore future optional fields. For the **strict request schema**, it uses `additionalProperties: false` to avoid silently accepting undeclared fields (this policy can trade off forward compatibility). For the V2 provider schema, it uses `additionalProperties: false` to catch accidental field leaks in the implementation's output; do not blindly apply that strictness to every consumer.

**Compatibility is a contract, not just “valid JSON syntax”.** For instance, if `status` remains a string yet changes from NEW to READY, the JSON is valid, but a consumer `switch` handling only NEW/SHIPPED can fail. Enum schemas and semantic tests catch such changes.

## 5. JSON Schema Draft 2020-12: essential keywords

Example JSON Schema for the V1 response:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]}
  },
  "additionalProperties": true
}
~~~

- **`required`**: the key must be present. It does not say whether the key may be null; to forbid null, `type` must exclude `"null"`.
- **`type`**: validates JSON string/integer/number/boolean/object/array/null; `2` and `"2"` are **different types**.
- **`enum`**: closes the supported value set; adding a new value can break consumers relying on a closed enum.
- **`minimum`**, **`minLength`**, **`pattern`**, **`format`**: corresponding constraints. `format` in JSON Schema Draft 2020-12 has annotation/assertion semantics depending on vocabulary and validator configuration; do not assume every email/URI is deeply validated just because `"format": "email"` is present.
- **`additionalProperties`**: governs unlisted keys. Tolerant consumer outputs may use `true`; provider API responses that must avoid leaking fields can use `false` in an exact-version schema.
- **`oneOf`**, **`anyOf`**, **`allOf`**, **`$ref`**, **`$defs`**: useful when a schema has variants/unions/discriminators. Tests should distinguish variants so consumers do not misinterpret them.
- **`deprecated`**, **`default`**, **`readOnly`**, **`writeOnly`**: useful annotations/vocabularies, but **JSON Schema `default` does not populate payload values** in all validators. Do not rely on `default` without an explicit transformation layer.

**Nullable vs. optional:**

~~~json
{
  "type": "object",
  "properties": {
    "deliveryNote": {
      "type": ["string", "null"]
    }
  }
}
~~~

In this schema `deliveryNote` **may be absent**, or present as a string **or null**, because the key is not in `required`. If the schema says `"type": "string"` yet Java emits `null`, the validator must reject it when the key appears. The runnable example deliberately omits `deliveryNote` when null using Jackson `@JsonInclude(NON_NULL)`, and **forbids it from appearing as null** in the V2 response schema.

### 5.1. Version baseline and validator library

This lesson validates JSON Schema using **networknt json-schema-validator 1.5.9**, with `JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)`, `getSchema(InputStream)`, and `validate(JsonNode)`. This is the **Jackson 2** line matching Spring Boot 3.3.x. When moving to Spring Boot 4 with Jackson 3, select a compatible validator line; do not mix `com.fasterxml.jackson` and `tools.jackson` packages.

**Why is a dedicated validator needed?** `MockMvcResultMatchers.jsonPath("$.id").exists()` cannot verify full `required`, `enum`, `additionalProperties`, or nested arrays. `content().json(expected)` checks a sample JSON document, but does not turn a sample into **a schema with constraints**. Both assertion styles complement each other.

## 6. Runnable project: Spring Boot 3.3.5, Jackson, MockMvc, JSON Schema

The project uses an in-memory repository to exercise the full HTTP path without needing a database or Docker. It includes:
- GET/POST endpoints with versioned path `/api/v1`.
- Java 17 record DTOs, `@Valid` Bean Validation, and strict Jackson request settings.
- `ProblemDetail` with stable errorCodes for 400/404.
- JSON Schemas for **V1 response**, **additive V2 response**, **strict request**, and **ProblemDetail**.
- MVC tests and schema compatibility tests; no snapshot style that “updates expected JSON to match new code”.

**Directory tree:**

~~~text
settings.gradle
build.gradle
src/main/resources/application.properties
src/main/java/demo/contract/ContractDemoApplication.java
src/main/java/demo/contract/CreateOrderRequest.java
src/main/java/demo/contract/OrderView.java
src/main/java/demo/contract/OrderRepository.java
src/main/java/demo/contract/OrderService.java
src/main/java/demo/contract/OrdersController.java
src/main/java/demo/contract/ContractErrorAdvice.java
src/test/resources/contracts/order-v1.json
src/test/resources/contracts/order-v2.json
src/test/resources/contracts/create-order.json
src/test/resources/contracts/problem.json
src/test/java/demo/contract/ContractSchemas.java
src/test/java/demo/contract/OrdersHttpContractTest.java
src/test/java/demo/contract/SchemaCompatibilityTest.java
~~~

### 6.1. Gradle and settings

**settings.gradle**

~~~groovy
rootProject.name = 'spring-api-contract-check'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.networknt:json-schema-validator:1.5.9'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Dependency notes:**
- `starter-web`: Spring MVC, HTTP converters, Jackson 2, and servlet tests.
- `starter-validation`: Jakarta Bean Validation/Hibernate Validator so `@Valid` on the request DTO catches missing or invalid constraints.
- `starter-test`: JUnit Jupiter, Spring Test, and MockMvc.
- `json-schema-validator:1.5.9`: **test-only** JSON Schema Draft 2020-12 validator. It does not automatically block production HTTP requests; `@Valid` and Jackson still handle real requests.
- Spring Boot dependency management supplies compatible Spring Framework/Jackson versions. The schema library 1.5.9 is pinned for this example; when running CI security scans, apply dependency update policies.

### 6.2. Jackson strict request policy

**src/main/resources/application.properties**

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.mapper.allow-coercion-of-scalars=false
~~~

These two lines establish an **intentional policy**:
1. Unknown fields in request objects are not silently ignored.
2. Jackson will not coerce `"2"` into integer `2` on an Integer field via scalar coercion.

In Spring Boot 3.3, `spring.jackson.deserialization.*` and `spring.jackson.mapper.*` properties map to the corresponding Jackson enums. Re-verify property bindings when changing major versions.

**Trade-off:** strict requests catch client typos/wrong keys and keep the input schema tight, but can **reduce forward compatibility** with newer clients sending optional fields unknown to an older server. This is a contract decision, not an “unconditional best practice”. If an API uses a tolerant request policy, update configuration and tests together rather than merely changing 400 to 201 to make tests green.

**Do not mechanically apply strict unknown-field rules to response consumers.** In the legacy consumer test, we explicitly use `@JsonIgnoreProperties(ignoreUnknown=true)` because response readers are expected to ignore added fields.

### 6.3. Main class

**src/main/java/demo/contract/ContractDemoApplication.java**

~~~java
package demo.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractDemoApplication.class, args);
    }
}
~~~

### 6.4. Request DTO and response DTO

**src/main/java/demo/contract/CreateOrderRequest.java**

~~~java
package demo.contract;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull @Positive Integer quantity) {
}
~~~

**src/main/java/demo/contract/OrderView.java**

~~~java
package demo.contract;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderView(
        String id,
        String customerId,
        int quantity,
        String status,
        String deliveryNote) {
}
~~~

`CreateOrderRequest` omits `id` and `status` so clients cannot set them; the server generates them. `@NotBlank` rejects `null`, empty strings, and whitespace-only strings; `@NotNull @Positive` requires `quantity` to be present and greater than 0. If JSON `quantity` is a string, the strict Jackson setting rejects it before Bean Validation runs.

`OrderView` is a **response DTO**, not a JPA entity. `@JsonInclude(NON_NULL)` makes `deliveryNote` **absent** when null—distinguishing it from `deliveryNote:null`. Field `status` is a `String` so the lesson can illustrate enum changes; in practice a Java enum can be used, while the JSON contract must still document the published values.

### 6.5. In-memory repository with deterministic data

**src/main/java/demo/contract/OrderRepository.java**

~~~java
package demo.contract;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final ConcurrentMap<String, OrderView> rows =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong(200);

    public OrderRepository() {
        reset();
    }

    public void reset() {
        rows.clear();
        rows.put(
                "ord-100",
                new OrderView(
                        "ord-100", "cust-a", 2, "NEW", null));

        rows.put(
                "ord-101",
                new OrderView(
                        "ord-101",
                        "cust-b",
                        3,
                        "SHIPPED",
                        "Deliver after 17:00"));

        sequence.set(200);
    }

    public Optional<OrderView> findById(String id) {
        return Optional.ofNullable(rows.get(id));
    }

    public OrderView create(CreateOrderRequest request) {
        String id = "ord-" + sequence.incrementAndGet();

        OrderView result = new OrderView(
                id,
                request.customerId(),
                request.quantity(),
                "NEW",
                null);

        rows.put(id, result);
        return result;
    }
}
~~~

The repository holds two fixtures: `ord-100` is a V1 response with only the four required fields; `ord-101` adds a string `deliveryNote`. Adding an optional field **does not change the `/api/v1` path** because the example demonstrates a **backward-compatible additive change** within the same major contract.

`reset()` is invoked in `@BeforeEach` so each test starts with two orders and `sequence=200`. This is an in-memory singleton test fixture and **does not replace database transaction tests**. The JUnit class does not run methods in parallel; in real DB projects use `@Sql`, transaction rollback, or disposable Testcontainers databases.

### 6.6. Service and domain exception

**src/main/java/demo/contract/OrderService.java**

~~~java
package demo.contract;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderView read(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new OrderNotFoundException(id));
    }

    public OrderView create(CreateOrderRequest request) {
        return repository.create(request);
    }
}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(String id) {
        super("Order not found");
    }
}
~~~

The `OrderNotFoundException` class at the end of the **same Java file** is package-private, which is valid Java. The exception message omits the ID to keep the error body stable and avoid echoing arbitrary input; production observability can safely log correlation/trace IDs internally. Do not wrap the exception into `200 OK` with empty data if the contract specifies `404`.

### 6.7. Controller: status, headers, and path are all part of the contract

**src/main/java/demo/contract/OrdersController.java**

~~~java
package demo.contract;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(
        path = "/api/v1/orders",
        produces = MediaType.APPLICATION_JSON_VALUE)
public class OrdersController {

    private final OrderService service;

    public OrdersController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> get(
            @PathVariable String id) {

        return ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(service.read(id));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderView created = service.create(request);

        return ResponseEntity
                .created(URI.create(
                        "/api/v1/orders/" + created.id()))
                .header("X-Contract-Version", "1")
                .body(created);
    }
}
~~~

**Key points to test:**
- `GET` returns 200 and `X-Contract-Version=1`, not 201.
- `POST` returns **201 Created** and `Location` pointing to the new ID.
- `@RequestBody @Valid` enforces DTO constraints.
- `consumes=application/json` rejects undeclared media types.
- `produces=application/json` handles content negotiation for GET/POST; `Accept: application/xml` will not match.
- Do not write undeclared query params/headers into contracts; if added later, clarify whether they are required or optional.
- The URI returned in `Location` is a **relative path** in this example. Production APIs may publish an absolute URL; if so, test scheme/host/proxy forwarding per contract.

Do not create or mock external HTTP clients here: these tests run the **real controller + service + repository in-JVM**, catching serialization mismatches between Java records and JSON Schemas.

### 6.8. ProblemDetail: stable error contract

**src/main/java/demo/contract/ContractErrorAdvice.java**

~~~java
package demo.contract;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ContractErrorAdvice {

    private ProblemDetail problem(
            HttpStatus status,
            String title,
            String detail,
            String errorCode) {

        ProblemDetail value = ProblemDetail
                .forStatusAndDetail(status, detail);

        value.setTitle(title);
        value.setProperty("errorCode", errorCode);
        return value;
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ProblemDetail missing() {
        return problem(
                HttpStatus.NOT_FOUND,
                "Not Found",
                "Order not found",
                "ORDER_NOT_FOUND");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail invalidRequest() {
        return problem(
                HttpStatus.BAD_REQUEST,
                "Bad Request",
                "Request validation failed",
                "VALIDATION_FAILED");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ProblemDetail unreadableRequest() {
        return problem(
                HttpStatus.BAD_REQUEST,
                "Bad Request",
                "Request body is invalid",
                "MALFORMED_JSON");
    }
}
~~~

In Spring Framework 6.1, `ProblemDetail` supports standardized error bodies (RFC 9457), and custom `errorCode` is serialized by Jackson as a top-level property via Spring integration. Because each exception has **status + title + errorCode**, consumers do not need to infer errors from text messages that might be localized.

**Do not return raw exception messages or stack traces to consumers.** Especially on deserialization errors, the original JSON may contain PII/tokens; the body “Request body is invalid” preserves the contract and limits data exposure. `415 Unsupported Media Type`/`406 Not Acceptable` errors are handled by Spring MVC defaults in this demo; the tests assert only status codes for those cases, **not claiming the same errorCode schema** without dedicated handlers.

## 7. JSON Schemas stored and versioned as source code

### 7.1. Response V1: consumer accepts extra fields

**src/test/resources/contracts/order-v1.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Order response contract V1 - tolerant reader",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]}
  },
  "additionalProperties": true
}
~~~

The V1 schema intentionally omits `deliveryNote` while **allowing** additional fields so older consumers can ignore optional additions. This is **a consumer-tolerant contract**, not a license for the provider to send secret fields freely; the provider must still control what is exposed.

### 7.2. Response V2: optional field, strict provider output

**src/test/resources/contracts/order-v2.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Order response contract V2",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]},
    "deliveryNote": {"type": "string", "maxLength": 120}
  },
  "additionalProperties": false
}
~~~

**V2 does not require `deliveryNote` to be present**, so a V1 response with only four fields remains valid under the V2 schema. Conversely, when `deliveryNote` is present, it **must be a string**, not null or a number. `additionalProperties:false` helps V2 provider output tests detect out-of-contract field leaks such as `debugToken`, while V1 consumers can still accept extras.

**The V1/V2 names in these two schema files are contract milestones for testing**, not an implication that the project has `/api/v1` and `/api/v2` endpoints. The example proves **an additive change on the same API route**, rather than implementing separate version routing.

### 7.3. Strict JSON request

**src/test/resources/contracts/create-order.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Create order request contract",
  "type": "object",
  "required": ["customerId", "quantity"],
  "properties": {
    "customerId": {
      "type": "string",
      "minLength": 1,
      "pattern": "\\S"
    },
    "quantity": {
      "type": "integer",
      "minimum": 1
    }
  },
  "additionalProperties": false
}
~~~

`pattern:"\\S"` in JSON represents regex `\S`—requiring at least one non-whitespace character. In the demo, `@NotBlank` is the **actual server validation**, whereas JSON Schema is the **test contract**; Spring Boot does not automatically keep them in sync. When DTO validation changes, schema and HTTP validation tests should catch the mismatch.

### 7.4. ProblemDetail JSON

**src/test/resources/contracts/problem.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Application ProblemDetail contract",
  "type": "object",
  "required": ["type", "title", "status", "detail", "errorCode"],
  "properties": {
    "type": {"type": "string"},
    "title": {"type": "string", "minLength": 1},
    "status": {"type": "integer", "minimum": 400, "maximum": 599},
    "detail": {"type": "string"},
    "instance": {"type": "string"},
    "errorCode": {
      "type": "string",
      "enum": [
        "ORDER_NOT_FOUND",
        "VALIDATION_FAILED",
        "MALFORMED_JSON"
      ]
    }
  },
  "additionalProperties": true
}
~~~

This schema preserves required fields/`errorCode` while allowing optional `instance` and controlled extensions. If the provider error response drops `errorCode`, changes status from 404 to 200, or turns `status` into a string, the test fails. **Not every Spring Boot 4xx necessarily follows this schema**: only errors with documented handlers are published in this example.

### 7.5. Schema files are contract artifacts, not just fixtures

Placing schemas next to tests is step one; in multi-team projects, manage:
- Ownership/approvals when changing contracts.
- Versioning and changelogs.
- Publication to an artifact registry, OpenAPI portal, or Pact broker.
- The range of consumer versions to support (N, N−1...).
- CI verifying the provider implementation against **all contracts still in use**, not just the newly updated one.
- Deprecation and sunset policies when a breaking change is unavoidable.

Keeping a schema only on a new branch means consumers in production have never seen the change. Contract tests must act as a **compatibility gate**, not just documentation.

## 8. Real helper for JSON Schema validation

**src/test/java/demo/contract/ContractSchemas.java**

~~~java
package demo.contract;

import java.io.IOException;
import java.io.InputStream;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;

import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

final class ContractSchemas {

    private static final JsonSchemaFactory FACTORY =
            JsonSchemaFactory.getInstance(
                    SpecVersion.VersionFlag.V202012);

    private static final ObjectMapper MAPPER =
            new ObjectMapper();

    private ContractSchemas() {
    }

    static JsonSchema schema(String filename) throws IOException {
        var resource = new ClassPathResource(
                "contracts/" + filename);

        try (InputStream stream = resource.getInputStream()) {
            return FACTORY.getSchema(stream);
        }
    }

    static Set<ValidationMessage> errors(
            JsonSchema schema, String json) throws Exception {

        JsonNode node = MAPPER.readTree(json);
        return schema.validate(node);
    }

    static void assertValid(
            JsonSchema schema, String json) throws Exception {

        Set<ValidationMessage> errors = errors(schema, json);

        assertTrue(
                errors.isEmpty(),
                () -> "Schema mismatches: " + errors);
    }

    static void assertInvalid(
            JsonSchema schema, String json) throws Exception {

        Set<ValidationMessage> errors = errors(schema, json);

        assertFalse(
                errors.isEmpty(),
                "An incompatible payload unexpectedly matches schema");
    }
}
~~~

This helper **does not rewrite a manual validator**. It uses `com.networknt` to load JSON schemas from the classpath and validate a Jackson `JsonNode`. `assertValid` requires **0 mismatches**; `assertInvalid` is used in negative compatibility tests to verify schema-breaking changes are caught.

One distinction to keep clear: **JSON Schema validates JSON data**, not HTTP methods/statuses/headers. Thus HTTP tests in section 9 always combine `MockMvcResultMatchers.status/header/content` with `ContractSchemas.assertValid(...)`. Do not misuse `assertInvalid` to turn a production provider bug into an unintended “PASS”: negative tests only verify that an intentionally invalid fixture **is rejected by the schema**.

## 9. HTTP integration test class: request, response, errors, and compatibility

**src/test/java/demo/contract/OrdersHttpContractTest.java**

~~~java
package demo.contract;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Execution(ExecutionMode.SAME_THREAD)
class OrdersHttpContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    OrderRepository repository;

    @BeforeEach
    void freshState() {
        repository.reset();
    }

    private String json(MvcResult result) {
        return result.getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
    }

    private MvcResult create(String payload) throws Exception {
        return mvc.perform(post("/api/v1/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andReturn();
    }

    private JsonSchema v1() throws Exception {
        return ContractSchemas.schema("order-v1.json");
    }

    @Test
    void getChecksMethodPathStatusMediaTypeHeaderAndV1Schema()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-100")
                                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Contract-Version", "1"))
                .andExpect(jsonPath("$.id").value("ord-100"))
                .andExpect(jsonPath("$.customerId").value("cust-a"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.status").value("NEW"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));

        // No optional note yet: field must be absent, not null.
        assertFalse(
                mapper.readTree(json(result)).has("deliveryNote"));
    }

    @Test
    void additiveOptionalResponseFieldStillMatchesV1()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-101")
                                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SHIPPED"))
                .andExpect(jsonPath("$.deliveryNote")
                        .value("Deliver after 17:00"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));
        ContractSchemas.assertValid(
                ContractSchemas.schema("order-v2.json"),
                json(result));
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record LegacyOrderReader(
            String id,
            String customerId,
            int quantity,
            String status) {
    }

    @Test
    void legacyConsumerCanDeserializeNewOptionalField()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-101"))
                .andExpect(status().isOk())
                .andReturn();

        LegacyOrderReader legacy = mapper.readValue(
                json(result), LegacyOrderReader.class);

        assertEquals("ord-101", legacy.id());
        assertEquals("cust-b", legacy.customerId());
        assertEquals(3, legacy.quantity());
        assertEquals("SHIPPED", legacy.status());
    }

    @Test
    void missingOrderHas404AndStableProblemContract()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/not-here"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode")
                        .value("ORDER_NOT_FOUND"))
                .andReturn();

        ContractSchemas.assertValid(
                ContractSchemas.schema("problem.json"),
                json(result));

        assertFalse(json(result).contains("Exception"));
    }

    @Test
    void postValidRequestHas201LocationHeaderAndResponseSchema()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":2}";

        ContractSchemas.assertValid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = mvc.perform(
                        post("/api/v1/orders")
                                .contentType(MediaType.APPLICATION_JSON)
                                .accept(MediaType.APPLICATION_JSON)
                                .content(request))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/v1/orders/ord-201"))
                .andExpect(header().string(
                        "X-Contract-Version", "1"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("ord-201"))
                .andExpect(jsonPath("$.status").value("NEW"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));

        mvc.perform(get("/api/v1/orders/ord-201"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void postMissingCustomerIdReturnsValidationProblem()
            throws Exception {

        String request = "{\"quantity\":2}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());

        ContractSchemas.assertValid(
                ContractSchemas.schema("problem.json"),
                json(result));

        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postBlankCustomerIdReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"   \",\"quantity\":2}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postQuantityZeroReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":0}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postNullQuantityReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":null}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postStringQuantityIsRejectedBySchemaAndJackson()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":\"2\"}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postUnknownFieldIsRejectedByStrictInputPolicy()
            throws Exception {

        String request = """
                {
                  "customerId":"cust-a",
                  "quantity":2,
                  "adminOverride":true
                }
                """;

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void malformedJsonDoesNotProduceSuccess()
            throws Exception {

        MvcResult result = create(
                "{\"customerId\":\"cust-a\",\"quantity\":");

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());

        mvc.perform(get("/api/v1/orders/ord-201"))
                .andExpect(status().isNotFound());
    }

    @Test
    void postWrongMediaTypeReturns415()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("customerId=cust-a&quantity=2"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void getUnacceptableAcceptMediaTypeReturns406()
            throws Exception {

        mvc.perform(get("/api/v1/orders/ord-100")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void wrongPathDoesNotMatchPublishedEndpoint()
            throws Exception {

        mvc.perform(get("/api/v1/order/ord-100"))
                .andExpect(status().isNotFound());
    }

    @Test
    void repeatedValidPostsCreateDistinctLocations()
            throws Exception {

        MvcResult first = create(
                "{\"customerId\":\"cust-a\",\"quantity\":1}");

        MvcResult second = create(
                "{\"customerId\":\"cust-b\",\"quantity\":3}");

        assertEquals(201, first.getResponse().getStatus());
        assertEquals(201, second.getResponse().getStatus());

        assertEquals(
                "/api/v1/orders/ord-201",
                first.getResponse().getHeader("Location"));
        assertEquals(
                "/api/v1/orders/ord-202",
                second.getResponse().getHeader("Location"));

        ContractSchemas.assertValid(v1(), json(first));
        ContractSchemas.assertValid(v1(), json(second));

        mvc.perform(get("/api/v1/orders/ord-202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customerId")
                        .value("cust-b"));
    }
}
~~~

**Exact count: 16 `@Test` methods in this class.** `@BeforeEach` resets the repository, and the helpers `create`, `v1`, `json` and nested record `LegacyOrderReader` are not JUnit tests. Tests operate purely in the application context sandbox; no DB or TCP HTTP server is needed.

**Why include `status`, `header`, `jsonPath`, and JSON Schema?**
- `status().isCreated()` catches changing 201 to 200.
- `header().string("Location",...)` catches wrong resource paths after POST.
- `contentTypeCompatibleWith` protects `application/json`/`application/problem+json`.
- `jsonPath` highlights important **business examples**.
- `ContractSchemas.assertValid` checks all required/type/enum/range/additionalProperties constraints against the schema.
- `legacyConsumerCanDeserializeNewOptionalField` proves a **concrete consumer reader** actually ignores the new field, rather than merely assuming so from the schema.

**Negative tests do not just check status:** validation cases verify both the request schema and `errorCode`, and the malformed-body test verifies `ord-201` was not created. Expand similarly for authentication/authorization, ETag, query params, pagination, and idempotency if they are part of your real API contract.

**An important point:** Strict Jackson settings are part of the project. If `allow-coercion-of-scalars=false` is removed, `"2"` can be coerced by Jackson into number 2 before validation, causing `postStringQuantityIsRejectedBySchemaAndJackson` to fail. That signals **the schema contract and runtime parsing have drifted apart**; do not edit the test to mask the discrepancy.

## 10. Compatibility test class: intentionally creating incompatible payloads

**src/test/java/demo/contract/SchemaCompatibilityTest.java**

~~~java
package demo.contract;

import com.networknt.schema.JsonSchema;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SchemaCompatibilityTest {

    private static final String OLD_RESPONSE = """
            {
              "id":"ord-100",
              "customerId":"cust-a",
              "quantity":2,
              "status":"NEW"
            }
            """;

    private static final String ADDITIVE_RESPONSE = """
            {
              "id":"ord-101",
              "customerId":"cust-b",
              "quantity":3,
              "status":"SHIPPED",
              "deliveryNote":"Deliver after 17:00"
            }
            """;

    private JsonSchema v1() throws Exception {
        return ContractSchemas.schema("order-v1.json");
    }

    private JsonSchema v2() throws Exception {
        return ContractSchemas.schema("order-v2.json");
    }

    @Test
    void additiveOptionalFieldIsAcceptedByOldAndNewSchema()
            throws Exception {

        ContractSchemas.assertValid(v1(), ADDITIVE_RESPONSE);
        ContractSchemas.assertValid(v2(), ADDITIVE_RESPONSE);
    }

    @Test
    void oldResponseIsStillValidForNewOptionalSchema()
            throws Exception {

        ContractSchemas.assertValid(v1(), OLD_RESPONSE);
        ContractSchemas.assertValid(v2(), OLD_RESPONSE);
    }

    @Test
    void missingRequiredIdWouldBreakOldConsumer()
            throws Exception {

        String withoutId = """
                {
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), withoutId);
    }

    @Test
    void renamingCustomerIdWouldBreakOldConsumer()
            throws Exception {

        String renamed = """
                {
                  "id":"ord-100",
                  "customer":"cust-a",
                  "quantity":2,
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), renamed);
    }

    @Test
    void changingIntegerQuantityToStringBreaksContract()
            throws Exception {

        String changedType = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":"2",
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), changedType);
    }

    @Test
    void introducingUnknownStatusBreaksClosedEnum()
            throws Exception {

        String newEnumValue = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"READY"
                }
                """;

        ContractSchemas.assertInvalid(v1(), newEnumValue);
    }

    @Test
    void nullOptionalNoteIsNotEquivalentToAbsentNote()
            throws Exception {

        String noteIsNull = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW",
                  "deliveryNote":null
                }
                """;

        // V1 allows unknown additional properties; V2 knows this
        // field and requires a string when it appears.
        ContractSchemas.assertValid(v1(), noteIsNull);
        ContractSchemas.assertInvalid(v2(), noteIsNull);
    }

    @Test
    void unknownRequestFieldViolatesStrictInputSchema()
            throws Exception {

        String futureRequest = """
                {
                  "customerId":"cust-a",
                  "quantity":1,
                  "promotionCode":"SAVE10"
                }
                """;

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                futureRequest);
    }

    @Test
    void missingRequiredRequestQuantityBreaksProducer()
            throws Exception {

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                "{\"customerId\":\"cust-a\"}");
    }

    @Test
    void newUnreviewedResponseFieldFailsStrictV2Schema()
            throws Exception {

        String leakedField = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW",
                  "debugToken":"secret"
                }
                """;

        ContractSchemas.assertValid(v1(), leakedField);
        ContractSchemas.assertInvalid(v2(), leakedField);
    }
}
~~~

**Exact count: 10 `@Test` methods in the schema compatibility class.** **Incompatible** fixtures are placed deliberately and must be rejected by `assertInvalid`. Therefore they PASS when the validator catches violations; no intentionally red test is shipped into CI.

**Project total: 16 HTTP integration tests + 10 schema compatibility tests = 26 JUnit Jupiter `@Test` methods.**

**Two distinct compatibility layers:**
- In `OrdersHttpContractTest`, **real** HTTP responses from Spring MVC are validated against schemas, and a legacy reader actually parses a response containing the new field.
- In `SchemaCompatibilityTest`, intentionally mutated payloads are validated to prove **the schemas themselves can catch breaking changes**. This class starts no server and must not be treated as proof of full-system runtime compatibility.

### 10.1. Which mutations will be caught?

| Change in provider or fixture | Test that should fail |
|---|---|
| Remove `customerId` from response | `getChecks...` JSONPath + V1 schema |
| Change `quantity` to JSON string | V1 response schema |
| Return unpublished status `READY` | V1 enum schema |
| Change POST 201 to 200 | `postValidRequestHas201...` |
| Omit or alter `Location` | Location header assertion |
| Change HTTP 404 to 200 | `missingOrderHas404...` |
| Omit `errorCode` from ProblemDetail | ProblemDetail schema |
| Forget `@Valid` | Required/blank/quantity negative HTTP tests |
| Enable Jackson scalar coercion for requests | `postStringQuantityIsRejectedBySchemaAndJackson` |
| Enable ignoring unknown request fields | `postUnknownFieldIsRejected...` |
| Omit `deliveryNote` despite business fixture having it | `additiveOptionalResponseField...` |
| Set optional field to `null` | V2 schema test |
| Leak `debugToken` in provider response | Strict V2 schema |
| Legacy DTO stops ignoring unknown fields | `legacyConsumerCanDeserialize...` |

**Do not immediately update all expected schemas when a test turns red.** Ask first whether the change is **intentional**, whether active consumers use it, and whether a migration/deprecation plan exists. Changing expected JSON without notifying consumers can turn a regression test into rubber-stamping a breaking change.

## 11. Running the project and expected results

**Prerequisites:** JDK 17; Gradle compatible with Spring Boot 3.3.5; ability to download dependencies from Maven Central on the first run; no Docker, database, external HTTP server, or real tokens/secrets required.

If you have the Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only created the files from this lesson and **do not yet have `gradlew`, `gradlew.bat`, and the wrapper JAR**, `./gradlew` does not exist yet. Use an installed Gradle to generate the wrapper or run:

~~~bash
gradle test
~~~

Run individual classes:

~~~bash
./gradlew test --tests demo.contract.OrdersHttpContractTest
./gradlew test --tests demo.contract.SchemaCompatibilityTest
~~~

JUnit reports normally appear at `build/reports/tests/test/index.html`.

| Class | `@Test` count | Focus |
|---|---:|---|
| `OrdersHttpContractTest` | **16** | HTTP method/path/status, Content-Type, headers, POST/GET, ProblemDetail, request validation, and legacy reader |
| `SchemaCompatibilityTest` | **10** | Optional additive, backward/forward schema, missing required, rename, number↔string, enum, nullable, extra request fields |
| **Total** | **26** | In-JVM tests, no real network required |

**Expected result:** All tests are designed to PASS when the source code is created accurately with Boot 3.3.5, Jackson/Spring dependencies, and JSON Schema validator 1.5.9. This is **expected behavior based on the API, source, and assertions**, **not a claim that Gradle was executed in the reader's environment**. When a project has different dependencies or profiles, run it directly to verify.

**Do not use `@Transactional` on this test class** because the repository is an in-memory singleton; each test resets via `@BeforeEach`. With a real DB, separate transactions/cleanup and concurrency checks are needed. `@SpringBootTest` defaults to a mock web environment, and MockMvc is enabled via `@AutoConfigureMockMvc`—no HTTP port is opened.

## 12. OpenAPI, Pact, and Spring Cloud Contract: when are they needed?

### 12.1. OpenAPI is the HTTP interface-level contract

**OpenAPI** describes endpoints (`paths`), methods, parameters, `requestBody`, responses by status, headers, security schemes, and schemas. This lesson's JSON Schemas are only **one part**: they cannot express HTTP status, `Location`, or `Content-Type` by themselves. For real APIs, store `openapi.yaml` or JSON in source control and use CI to:

1. Validate syntax/specification.
2. Check that code-generated OpenAPI matches the spec (or use spec-first generation).
3. Use OpenAPI diff to compare the released version with the current candidate: deleted paths, changed required fields/types/statuses.
4. Run HTTP contract tests against the implementation as in section 9.
5. Run consumer contract verification when specific consumers exist.
6. Enforce approval/migration policies for breaking changes.

**Abbreviated OpenAPI 3.1 sample (illustrative, not a runnable file in this project):**

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order exists
          headers:
            X-Contract-Version:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          description: Order not found
          content:
            application/problem+json:
              schema:
                type: object
  /api/v1/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Created
          headers:
            Location:
              schema:
                type: string
components:
  schemas:
    CreateOrder:
      type: object
      required: [customerId, quantity]
      properties:
        customerId:
          type: string
        quantity:
          type: integer
          minimum: 1
    Order:
      type: object
      required: [id, customerId, quantity, status]
      properties:
        id:
          type: string
        customerId:
          type: string
        quantity:
          type: integer
        status:
          type: string
          enum: [NEW, SHIPPED]
        deliveryNote:
          type: string
~~~

This is a **high-level sketch** of OpenAPI 3.1 form, not a complete spec of all error cases/statuses/headers; use a full specification with security, examples, error codes, and complete schema constraints. Springdoc/OpenAPI generators can help, yet **never treat documentation auto-generated from the implementation as proof of compatibility** if the expected baseline is regenerated at the same time.

### 12.2. Consumer-driven contract testing

In the CDC model, the consumer specifies the interactions it actually needs:

~~~text
Consumer "billing-ui"
  Given order ord-100 exists
  When GET /api/v1/orders/ord-100, Accept application/json
  Then status 200
       content-type application/json
       body has id:string, quantity:integer, status:NEW|SHIPPED

Publish contract artifact (version + consumer identity)
     |
     v
Provider CI verifies it against service implementation
     |
     v
Provider deploy is gated by active supported consumers
~~~

**Spring Cloud Contract** lets you define contracts and generate tests/stubs in the Spring ecosystem (e.g., Groovy DSL/YAML depending on version); **Pact** uses consumer-driven pact files and provider verification, optionally using a broker to manage the consumer/provider version matrix. Both tools have their own versioning/plugin/dependency setup: do not drop an undeclared DSL/Pact snippet into the runnable project expecting it to work automatically.

**Provider state** is crucial: a contract saying “order ord-100 exists” must have matching seed/test data before verification rather than depending on a development database. For state “order absent”, the provider must genuinely return 404 rather than mocking the implementation incorrectly. If consumers use Kafka, CDC also includes message contracts (key/schema/headers/event compatibility), not just HTTP.

### 12.3. Provider-first vs. consumer-first

- **Provider-first:** the provider team publishes OpenAPI/schemas and verifies the implementation; fits public APIs with clear spec ownership. Risk: the provider team alters schemas without knowing what consumers actually rely on.
- **Consumer-first:** consumers write the interactions they need and publish them for provider verification; fits multi-service/multi-team systems. Risk: overly tight constraints can make the provider hard to evolve.
- **Combined:** OpenAPI serves as the official baseline; consumer-specific contracts act as the **compatibility gate**; full-stack tests cover a few key flows. The goal is not “pick one tool” but verifying each commitment at the right layer.

## 13. Resilience is also an observable contract

An API with a flawless JSON Schema can still break consumers during network errors or retries. Reliability contracts include:

- **Timeouts**: consumers know connect/read timeouts, max latency, and fallbacks; schemas do not verify timeouts.
- **Retries**: POST is not always idempotent. If a client retries because the HTTP response dropped after the server created the order, it can create two orders. An **idempotency key**, business deduplication, or proper retry policy is required.
- **429/503**: status codes, `Retry-After`, response `errorCode`, and rate-limit policy; do not silently turn every error into 200.
- **Circuit breaker/fallback**: when the backend fails, define which responses represent degraded mode and whether stale data is distinguished.
- **Correlation IDs**: request/response headers and logs can carry trace IDs without exposing tokens/PII.
- **Pagination/ordering**: cursors, stable sorting, and consistency semantics affect consumers more than whether JSON parses cleanly.
- **Version skew**: new providers and old consumers coexist during rolling/canary deployments, requiring version-range testing.
- **Security**: auth scopes/roles, 401/403, and field redaction are also part of the contract, not just controller paths.

**Dangerous retry example:**

~~~text
T0: Consumer POST /orders, body order A
T1: Server creates ord-201, commits successfully
T2: Network drops before client reads 201
T3: Client retries the same POST
T4: Server creates ord-202 again
=> Two orders even though every response strictly matches JSON Schema.
~~~

If an API needs retry-safe creation, design an `Idempotency-Key` durably stored by the server within the same business transaction and test that **two POSTs with the same key return the same outcome**, including races/concurrency. The runnable demo in section 6 intentionally does not support idempotency; `repeatedValidPostsCreateDistinctLocations` reflects that current behavior. **Do not mistake a request contract test for proof of exactly-once semantics.**

### 13.1. Supplementary fault injection

| Failure | Contract to verify | Suitable tool |
|---|---|---|
| Server returns 503 | Client retry/fallback/timeout | WireMock/MockWebServer, resilience test |
| HTTP status is 200 but body violates schema | Consumer parser fails | MockMvc + JSON Schema/provider verification |
| 404 changed to 200 with null body | Error policy broken | MockMvc HTTP contract |
| Connection reset after server commit | Duplicate creation risk | Real HTTP mock server + DB integration |
| Old consumer reads new response | Backward compatibility | Pact/Spring Cloud Contract/provider states |
| Old provider sees request from new consumer | Strict unknown field may return 400 | Consumer/provider version matrix |
| New event schema adds required field | Consumer message deserialization fails | Schema registry compatibility + messaging tests |
| ETag/If-Match dropped | Lost update/precondition behavior | HTTP integration + concurrent DB tests |

**Contract tests do not replace performance, chaos, or security testing.** They form a clear guardrail: external observability matches agreed promises. To prove an application recovers from outages/restarts, run fault injection, timeouts, broker/storage state checks, and metrics.

## 14. Compatibility analysis for JSON Schema, Avro, and Protobuf

The runnable lesson uses JSON/JSON Schema, yet **schema compatibility** also appears in messaging:

**JSON/REST**
- Required/optional fields, nullability, enums, types, formats, HTTP status/headers.
- `additionalProperties` and Jackson unknown-field settings determine tolerant reader behavior.
- No protocol-enforced registry; manage schemas/OpenAPI/Pact artifacts via CI or an architectural registry.

**Avro**
- Writer/reader schema resolution, defaults for new fields, union types, enum symbols, and field aliases follow distinct semantics.
- Registries commonly offer BACKWARD/FORWARD/FULL compatibility modes; mode names and scope (transitive vs. latest-only) depend on the registry.
- Do not apply JSON `additionalProperties:true` rules directly to Avro.

**Protobuf**
- Field numbers are wire identity. Adding a new field number is generally compatible, whereas **reusing an old field number with a different meaning** is not.
- Removing fields requires reserving numbers/names where appropriate; changing wire types or `oneof` semantics can be breaking.
- Unknown-field handling varies by runtime/language/version; verify with the real serializer/consumer rather than guessing.
- A schema registry can enforce syntactic policy, but cannot guarantee semantic compatibility of a business event.

**GraphQL** also has its own mechanics: adding optional fields to the schema usually does not break existing queries, whereas removing fields or changing nullability/enums can break clients. Use introspection/schema diffs plus consumer operation checks.

**Key takeaway:** “Compatible” is a relationship among the **producer writer, consumer reader, protocol, serialization library, and behavioral contract**; it is not an absolute property of a standalone schema file.

## 15. Choosing strictness and avoiding brittle contract tests

**Where should assertions be strict?**
- Method, route, status, required headers, content type: whenever consumers rely on them.
- Required JSON fields, types, non-null constraints, enum semantics: when part of the public contract.
- Error codes/shapes, `Location`, API version semantics.
- Absence of secret fields or extra properties in provider output when disclosure is a risk.

**Where should you avoid over-strictness?**
- JSON object key ordering or whitespace; JSON parsers do not depend on key order.
- Raw `Date`, request ID, trace ID, or dynamic timestamps unless a strict format rule is contracted.
- Server header ordering or HTTP-insignificant header casing.
- Optional response fields unused by the consumer.
- Internal database IDs, stack traces, or implementation class names.
- Absolute hostnames in tests if the API contract only promises relative paths (and vice versa).

**Consumer tolerance must be bounded by design.** If a consumer “ignores all unknown fields”, an accidental `debugToken` sent by the provider is still dangerous. Thus the lesson uses a **tolerant V1 schema for reading tests**, alongside a **strict V2 schema for provider output tests**. Real APIs should also verify field redaction, security classification, and schema publication approvals.

**Do not disable validation just to force compatibility.** If a V2 provider drops `quantity` or changes its JSON type while a client parser silently defaults to 0, the request may “parse” yet compute the wrong charge. **Syntactic compatibility does not guarantee semantic correctness.** Especially for money, units, timezones, enums, and decimal precision, write dedicated business-meaning assertions.

### 15.1. When should an endpoint be versioned?

A breaking change may justify creating `/api/v2`, a versioned media type, or another versioning strategy. Decide per your public API policy:

- **Additive, compatible:** add optional fields, documentation, and provider contract tests; no major version bump required if consumers are tolerant.
- **Breaking:** remove required fields or alter semantics/critical statuses; introduce a new version or coordinate deployment across all consumers if internal environments permit.
- **Deprecation:** publish a schedule, measure traffic on the old version, support an overlap window, and emit deprecation warnings/headers per policy.
- **Retirement:** remove V1 only when usage metrics and consumer contracts prove no dependency remains, or after the sunset policy has been properly enforced.

**Do not merely rename `/v1` to `/v2` and call it safe.** Old consumers still need V1 served until migration finishes, and data/migrations must tolerate version skew if the provider shares a database.

## 16. Common pitfalls and fixes

| Symptom | Cause | Evidence/fix |
|---|---|---|
| MockMvc returns 200 yet client app breaks | Asserted status only, skipped body schema | Validate JSON Schema + consumer parsing |
| Tests pass after changing `quantity` from number to string | `jsonPath` only compared `.asText` or Jackson coerced | Strict JSON Schema type; disable coercion if policy requires |
| Removing `id` goes unnoticed by tests | Missing `required` in schema | Add `required` and negative fixture |
| New `status=READY` crashes UI | Closed enum lacked compatibility review | Enum tests + consumer capability checks |
| Adding optional response field breaks legacy parser | Consumer rejects unknown fields | Test tolerant reader, versioning, or rollout |
| Adding new request property causes old server 400 | `additionalProperties:false`/strict Jackson | Check forward compatibility and release ordering |
| Adding required request property | Old clients do not provide it | Breaking; versioning/migration/default policy |
| `deliveryNote` is `null` instead of absent | `null` differs from optional | JSON Schema type + `@JsonInclude` |
| `@Valid` does not run | Missing `starter-validation` or annotation | Negative HTTP validation tests |
| JSON Schema passes yet HTTP status is wrong | Schema is unaware of HTTP status | MockMvc status assertions |
| 400 response contains stack trace | Error handler leaks exception | ProblemDetail stable code + security tests |
| Problem JSON custom field nests under `properties` | Jackson ProblemDetail integration differs from expectation | Test actual HTTP JSON / flattened property |
| Provider schema and code edited together to stay green | No independent baseline contract artifact | Publish/verify versioned contracts |
| MockMvc passes, client fails to connect over network | Mock servlet opens no socket | `RANDOM_PORT`/WebTestClient/MockWebServer |
| Tests depend on execution order due to repository state | Singleton fixtures not reset | `@BeforeEach`, DB rollback/cleanup |
| Pact provider verification fails due to missing fixture | Provider state not set up | Provider-state arrangement |
| OpenAPI diff yields false positives | Generated schemas are unstable | Review semantically, normalize |
| Schema validator uses wrong Draft | Defaulted to V4 instead of V202012 | `V202012` factory, explicit `$schema` |
| Jackson 3 mixed with Jackson 2 on Boot 4 | Package/module changed | Pick validator version compatible with Boot |
| Response body leaks new secret while V1 tolerant passes | `additionalProperties:true` | Provider strict schema/redaction tests |
| POST retry creates two resources | Missing idempotency contract | `Idempotency-Key` + DB dedup + failure tests |
| HTTP timeouts untested | MockMvc only tests normal responses | MockWebServer/network fault injection |
| Unknown which consumer uses a removed field | Missing registry/consumer telemetry | CDC/Pact broker/deprecation logs |

### 16.1. Checklist before merging an API change

1. Is there a baseline **OpenAPI/JSON Schema/CDC** managed outside the new implementation itself?
2. Are active consumer versions and the supported range listed?
3. For **requests**: are method/path/query/headers/Content-Type and required/optional JSON verified?
4. For **responses**: are status, `Location`, media type, headers, required fields/types/enums verified?
5. Are **missing field, renamed field, wrong type, new enum, and null vs. absent** tested?
6. Is an **optional additive field** tested against both the old consumer and new provider?
7. Is a real consumer reader or CDC provider verification run, not just schema validity?
8. Is strictness for unknown fields confirmed for both requests and responses?
9. Do Bean Validation and Jackson behavior match the JSON Schema?
10. Do error bodies use stable codes and avoid leaking stack traces/PII?
11. Are HTTP 400/404/415/406 tested per contract without silently switching to 200?
12. Is there a migration plan if breaking, plus a deprecation timeline and rollout order?
13. Are retries/idempotency/timeouts/error statuses verified in dedicated resilience tests?
14. During rolling/canary deploys, can the new provider serve old consumers in the overlap window?
15. If schemas are used in Kafka/Avro/Protobuf, are the right registry compatibility mode and runtime-specific rules applied?
16. Does CI fail when an old contract breaks rather than auto-updating golden files to ignore it?
17. Are secrets/auth/real customer data excluded from snapshots and logs?
18. Does test evidence clearly state MockMvc/JSON Schema vs. real HTTP network without overstating scope?

## 17. Practice exercises

**Exercise 1.** Remove `customerId` from `OrderView`. Which test fails first? Explain how `required` catches an absent field even when JSON still parses.

**Exercise 2.** Change response `quantity` to a string. Prove JSON Schema rejects it, and evaluate whether having consumers auto-coerce it is safe.

**Exercise 3.** Add an optional `deliveryNote` string. Why can the V1 consumer still parse it? Try replacing `@JsonIgnoreProperties(ignoreUnknown=true)` with a strict reader.

**Exercise 4.** Add `deliveryNote` to V2's `required` list. Is the old response still valid? Decide between a default/fallback or a new API version.

**Exercise 5.** Change absent `deliveryNote` to `null`. Inspect the schema and prove the difference between optional and nullable.

**Exercise 6.** Change 201 to 200 for POST. Why does a response schema test still pass while an HTTP contract test fails?

**Exercise 7.** Remove `Location` after 201. Write a consumer follow-up GET test and explain the value of header contracts.

**Exercise 8.** Change `status=NEW` to `status=READY` without updating the schema. Why is enum compatibility review vital even when the type stays string?

**Exercise 9.** Send `{"customerId":"cust-a","quantity":"2"}`. Prove the schema rejects it and explain why Jackson scalar coercion can make server behavior diverge from the schema.

**Exercise 10.** Send a request containing an extra `promotionCode`. What must the strict server return? If you want forward-compatible requests, how do the policy and tests change?

**Exercise 11.** Replace required `customerId` with a field named `customer`. Sketch API v2 and a migration path for older clients.

**Exercise 12.** Write a complete OpenAPI spec for GET/POST including 200/201/400/404/415/406 responses, `Location` header, and error schema.

**Exercise 13.** Write a consumer-driven interaction for `billing-ui` with provider state `"order ord-100 exists"`, and verify it against the current API build.

**Exercise 14.** Enable Spring Security on the API. Add 401/403 contracts and appropriate scopes, distinguishing schema tests from authorization policy tests.

**Exercise 15.** Add `Idempotency-Key` for POST. Simulate a network timeout after DB commit, retry with the same key, and prove only one order is created.

**Exercise 16.** Move the `OrderCreated` message to Avro or Protobuf; identify which schema changes are breaking under writer/reader and field-number semantics.

**Exercise 17.** Set up canary provider P2 with consumers C1/C2; map out deployment ordering and contract verification before retiring P1.

**Exercise 18.** Review a real API: list its requests, responses, headers, errors, optional/required/enum rules, and turn them into contract tests running in CI.

## 18. Official references

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, `@WebMvcTest`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MVC request/response assertions without a TCP server.
- [Spring Boot 3.3 — JSON/Jackson](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson mapping and customization.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jackson.*`.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ResponseEntityExceptionHandler`, and RFC 9457.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid` request bodies and method argument validation.
- [JSON Schema — Specification](https://json-schema.org/specification): Draft 2020-12 keywords/vocabularies and schema semantics.
- [NetworkNT json-schema-validator 1.5.9 API](https://www.javadoc.io/static/com.networknt/json-schema-validator/1.5.9/index.html): Java validator, `SpecVersion`, `JsonSchemaFactory`, `validate`.
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.1.html): paths, parameters, `requestBody`, responses/headers/schema.
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer-driven contracts, generated tests, and stubs.
- [Pact](https://docs.pact.io/): consumer contracts, provider verification, broker/version workflows.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized error responses.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP methods, status semantics, media types, and headers.
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): Avro/Protobuf/JSON Schema registry policies.

**Remember:** An API contract includes **requests, responses, schemas, and HTTP behavior**, not just “does the JSON parse”. Whenever changing an API, ask **which consumers are still active and how they will read this data**. Use JSON Schema with `required`, `type`, `enum`, and `additionalProperties` to check payloads; use MockMvc to check method/path/status/headers/media types/errors; use CDC/consumer tests to protect real integrations. **Adding an optional response field can be compatible; removing a required field, changing number→string, changing enums/statuses, or adding a required request field usually breaks the contract.** For resilience, also test timeouts, retries, idempotency, and version skew—a single schema test does not prove the whole system is safe.
