# Testing Compatible Changes and Client-Breaking Changes in Spring Boot

## 1. Objectives

An API can boot normally, return `200 OK`, pass every unit test, and still **break clients running in production**. This happens when changes alter JSON shape, HTTP statuses, headers, validation, permissions, units of measure, enums, event ordering, or timing that API consumers depend on.

**Backward compatibility testing** answers a specific question: **Does the new provider version still satisfy the contract that existing consumers have integrated against?** When a change prevents an older consumer from sending valid requests, reading responses, interpreting values, or maintaining its workflow, it can be a **breaking change** even if a schema compiler considers the change valid.

This lesson belongs to the **Contracts and Resilience** section of the **Spring Boot – testing** module, covering **Testing compatible changes and client-breaking changes**.

After this lesson, you will be able to:

1. Distinguish **request**, **response**, **semantic**, **behavioral**, **security**, **timing**, and **event** compatibility.
2. Evaluate whether an “additive field” change is truly backward-compatible for a specific consumer.
3. Build a breaking/non-breaking classification table across the provider–consumer interface.
4. Design **provider contract tests** using Spring MVC `MockMvc`, checking method/path/status/content type/JSON shape.
5. Design **consumer compatibility tests** running a real legacy client with `RestClient` and `MockRestServiceServer`.
6. Use **golden fixtures** storing the old contract and new candidate; verify JSON with Jackson without generating expected outputs from the SUT itself.
7. Catch “schema valid, semantics broken” changes: cents turned into dollars, new enums, nulls, list ordering, idempotency, timezones.
8. Choose complementary tools such as Spring Cloud Contract, Pact, OpenAPI diff, and schema registries for the right scenario.
9. Structure CI compatibility gates, supported-consumer matrices, versioning, and zero-downtime rollout/rollback.
10. Separate **contract tests**, **component tests**, **real-HTTP integration tests**, and **production observability**.
11. Write a **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter** project running offline without a broker, DB, or Docker.
12. Understand the limits of a single-provider and single-legacy-client harness, and extend to GraphQL, gRPC, Avro/Kafka, SOAP, and database migrations when applicable.

**Rule of thumb:** “Green build” does not mean “old clients survive”. For any API used by independently deployed clients, the **public contract** and **real consumer behavior** must gate releases.

## 2. Provider, consumer, and contract

Imagine a Spring Boot application named **Catalog Service**:

~~~text
                  Independent Deploys
                       |
                       v
Legacy Mobile App --------\
Partner Integrator --------> GET /api/v1/products/{sku}
Internal Checkout --------/          |
                                    v
                          Spring Boot Catalog API
                                    |
                                    v
                            JSON ProductResponse
~~~

Consumers may use different technologies:

- A mobile app can stay offline for weeks before updating.
- A partner uses Jackson with `FAIL_ON_UNKNOWN_PROPERTIES=true`.
- A Java client uses `@JsonIgnoreProperties(ignoreUnknown=true)`.
- A consumer parses `priceCents` as `long`.
- A consumer reads enums via `Enum.valueOf`, throwing on unknown values.
- A batch job expects `404` for missing SKUs and has no handler for `200 + null`.
- A webhook consumer implements retries/idempotency based on status codes and event IDs.

A **contract** is more than a JSON schema. It can encompass:

| Component | Contract example | What to protect |
| --- | --- | --- |
| HTTP method | `GET /api/v1/products/{sku}` | Do not unexpectedly switch GET to POST |
| URL/path | `/api/v1/products/BOOK-1` | Do not delete/rename paths old clients call |
| Query parameters | Optional `?locale=vi` | Do not turn optional params into required |
| Request headers | `Authorization`, `Idempotency-Key` | Do not force old clients to send unrolled-out headers |
| Request body | `sku`, `quantity` | Do not alter requiredness of existing fields |
| Response status | 200 when found, 404 when absent | Do not swap statuses when consumers branch on status |
| Response headers | `Content-Type: application/json` | Do not switch to XML/plain text |
| Response JSON fields | `sku`, `name`, `priceCents` | Do not delete, rename, or change types |
| Field semantics | Price denominated in **cents** | Do not switch to dollars under the old name |
| Nullability | `priceCents` always non-null | Do not unexpectedly return null |
| Enum domain | `PENDING`, `COMPLETED` | New values can crash older clients |
| Pagination | Stable cursor, next link | Do not silently change ordering/cursor semantics |
| Timing | Retry-After, timeouts, eventual consistency | Do not turn sync into async unbeknownst to clients |
| Security | OAuth scopes/permissions/cookies | Do not silently require new scopes old clients lack |
| Error format | `{"code":"PRODUCT_NOT_FOUND"}` | Do not replace JSON errors with HTML/stack traces |
| Event delivery | OrderCreated includes event ID | Do not drop fields or break partition/order guarantees |

Compatibility must be judged by the **receiver** and the **published/used contract**, not merely whether the type system compiles.

## 3. Backward, forward, and full compatibility

### 3.1. Backward compatibility

A **new** provider still properly serves an **old** consumer:

~~~text
Consumer v1  ---- request v1 ----> Provider v2
Consumer v1  <--- response OK ---- Provider v2
~~~

If clients previously sent `{"sku":"BOOK-1","quantity":2}`, provider v2 must still accept it while the old contract remains supported.

### 3.2. Forward compatibility

A **new** consumer handles **old** responses from an un-upgraded provider:

~~~text
Consumer v2  ---- request --------> Provider v1
Consumer v2  <--- response v1 ---- Provider v1
~~~

This matters when clients and servers deploy out of sync. For instance, consumer v2 treats `availability` as optional and falls back when provider v1 does not yet return it.

### 3.3. Full/transitive compatibility

Some ecosystems—especially schema registries for messaging—define **BACKWARD**, **FORWARD**, **FULL**, and **TRANSITIVE** variants. “Compatibility” depends on encoding/schema resolution rules (Avro, Protobuf, JSON Schema) and which versions are compared. **Do not copy Avro schema compatibility conclusions directly onto REST/JSON with custom semantics.**

### 3.4. Multiple versions often coexist in production

With mobile apps, consumer v1, v2, and v3 may hit provider v4 simultaneously. A PR making API v4 compatible only with v3 while breaking v1 is still breaking if v1 remains within the **support window**. Maintain explicit **supported consumer versions** and sunset dates rather than using only “the consumer's current main branch” as the baseline.

## 4. Classifying changes: compatible or client-breaking?

| Change | Usually | Conditions and exceptions |
| --- | --- | --- |
| Add optional response field | Can be compatible | Consumers must ignore unknown fields; strict schema validators may reject |
| Add new endpoint | Usually compatible | Must not shadow old paths/matchers or alter routing |
| Add optional query parameter | Usually compatible | Default behavior must preserve old semantics |
| Add optional request field | Usually compatible | Provider must still accept old requests omitting the field |
| Add required request field | **Breaking** | Old clients do not send it |
| Rename response field | **Breaking** | Unless keeping an alias/old field during transition |
| Delete response field | **Breaking** | If old consumers read it |
| Change JSON number → string | **Breaking** | Can break parsers/type validation |
| Number int → decimal | Potentially breaking | Integer-parsing clients may coerce/truncate/throw |
| Add value to string enum | Potentially breaking | Clients using exhaustive `switch`/`Enum.valueOf` break |
| Make non-null nullable | **Breaking** | Old clients may NPE |
| Make optional request field required | **Breaking** | Old requests receive 400 |
| Return 202 instead of 201/200 | **Behavioral breaking** | Clients expect immediate final result |
| Replace 404 with 200 + null | **Behavioral breaking** | Clients branch on HTTP status |
| Add required permission/scope | **Potential breaking** | Old clients may hit 401/403 |
| Change unit cents → dollars | **Semantic breaking** | JSON Schema may not catch it |
| Replace `priceCents` 1999 with 19.99 | **Breaking** | Both schema and semantics changed |
| Change timezone or rounding | **Semantic breaking** | Financial reports/schedules drift |
| Change pagination order/cursor | Potentially breaking | UI/batch paging skips or duplicates records |
| Add caching | Potentially breaking | Staleness/ETag/Cache-Control behavior shifts |
| Add automatic retries | Potentially breaking | Side effects may run multiple times |
| Performance optimization with identical output | Usually compatible | Must preserve published timing/SLAs and ordering |

**Avoid mechanical rules like “additions = good, removals = bad”.** Systems have strict consumers and subtle semantics. Check **contracts per supported client**.

## 5. Contract tests are not unit tests

A unit test calling only the service:

~~~java
Product product = catalog.find("BOOK-1");
assertEquals(1999, product.priceCents());
~~~

does not prove:

- The HTTP path is right.
- The controller returns 200 and `Content-Type: application/json`.
- Jackson serializes `priceCents`, not `priceInCents`.
- V1 requests omitting a new field still bind properly.
- 404 has a stable error code and status.
- Old clients deserialize the provider v2 response.

Conversely, a provider MockMvc test checking JSON shape **does not prove** a real consumer with different configuration can read it. Both sides complement each other.

### A balanced pyramid

~~~text
                 Real HTTP smoke
                     /  \
        Provider MockMvc  Consumer RestClient
                  \       /
           Golden fixtures + schema checks
                     |
             Unit business invariants
~~~

- **Provider contract tests:** protect the API exposed through controllers, serialization, and validation.
- **Consumer contract tests:** run **old client code** against contract stubs with explicit requests/responses.
- **Schema/API diff:** flags structural changes across OpenAPI/AsyncAPI/Avro.
- **Real HTTP smoke:** verifies the servlet container, network stack, port, and real client, though not full production.
- **Observability/canary:** detects untracked consumer versions and unexpected failures.

Do not cram every check into a slow E2E test; split tests by boundary to pinpoint root causes fast.

## 6. Consumer-driven contracts (CDC)

With **consumer-driven contracts**, each consumer states **the interactions it actually needs**: which requests, response statuses, headers, and body fields. The provider must verify that new versions satisfy those contracts.

Typical workflow:

~~~text
Consumer v1
  |
  | Record contract: GET /api/v1/products/BOOK-1
  | Expect 200 application/json; sku/name/priceCents
  v
Contract artifact/stub registry
  |
  +-- Consumer tests run against stub
  |
  +-- Provider CI downloads contract and verifies implementation
  |
  v
Provider v2 release gate
  |
  +-- PASS: allow release per support policy
  +-- FAIL: fix provider or version endpoint / plan migration
~~~

Key points:

- Contracts should express **expectations the consumer actually uses**, not copy the entire provider DTO.
- Provider tests must run against the **real provider implementation**, not a stub self-written and self-verified by the provider.
- Contracts need **version/consumer identity** and deployment/support status, not an unowned fixture.
- Consumer tests should catch deserialization, retry/error handling, and status expectations; provider tests should catch schema/validation behavior.
- Comparing JSON produced by the same `ObjectMapper` and new DTO lets expected and actual shift together -> **false confidence**.
- Not every compatibility bug is a schema bug: units, currency, enum semantics, ordering, and idempotency still need business assertions.

### Popular tools

**Spring Cloud Contract** generates provider verification tests and consumer stubs from Groovy/YAML contracts. With Spring Boot 3.3.x, pick the compatible Spring Cloud Contract and Spring Cloud BOM line rather than dropping the newest dependency into an older build.

**Pact** excels at managing per-consumer/provider contracts with a broker, provider verification, and deployment checks. “Pact verified” means the declared interactions passed under that setup, **not** that all behavior is proven safe.

**OpenAPI diff** compares base/target specs by rules, flagging deleted endpoints and altered required fields/statuses/schemas. Yet specs can drift from code, and semantic shifts rarely show up in schemas. Combine **spec diffs + runtime contract tests**.

In the lab below, plain JUnit/Spring Test/Jackson keep setup simple without extra tooling. Later sections cover upgrading to dedicated CDC tooling.

## 7. Golden fixtures: baselines must not shift with the new provider

A **golden fixture** is an independently stored baseline request/response. For example, consumer v1 previously received:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999
}
~~~

Provider v2 adds `availability`:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999,
  "availability": "IN_STOCK"
}
~~~

If **consumer v1 ignores unknown fields**, it can still deserialize and read the three original fields. A strict consumer, however, might fail on the new field. Calling a change “backward compatible” must tie back to **verified consumer behavior**.

Breaking rename example:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceInCents": 1999,
  "availability": "IN_STOCK"
}
~~~

An old consumer reading `priceCents` sees a missing value and may throw or default to 0. Both outcomes are dangerous.

Semantic break example that a JSON parser still accepts:

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 20,
  "availability": "IN_STOCK"
}
~~~

If the real price is still $19.99 yet the field silently changed from cents to rounded dollars, the JSON type remains integer. **Schema-only diffs miss this.** Guard it with business invariants and expected price/currency fixtures.

### Fixture management rules

1. Freeze the v1 baseline per supported consumer version.
2. Document clear semantics and requiredness per field.
3. When the provider changes, **never auto-regenerate all expected JSON** and call the test green.
4. Keep candidate fixtures for both **positive and negative compatibility cases**.
5. Never put real PII/credentials into fixtures.
6. Require reviews on contract edits alongside a deprecation plan.
7. When multiple consumer versions exist, store fixtures per consumer/version/interaction.
8. Do not turn full-JSON snapshots into a “no fields may ever be added” rule if the contract allows additive extensions.

## 8. Runnable project: Spring Boot 3.3.5 / Java 17

We build **Catalog API v2** still serving route **`/api/v1/products/{sku}`**, because URI version `v1` denotes the **supported contract version**, not the binary release of the Spring Boot app. Provider v2 can add `availability` without immediately requiring a v2 endpoint.

Legacy consumer `LegacyCatalogClient` knows only `sku`, `name`, `priceCents`, and uses Spring Framework `RestClient`. The test suite uses:

- `@SpringBootTest` + `@AutoConfigureMockMvc` to test the real provider.
- `MockRestServiceServer.bindTo(RestClient.Builder)` to test the old client against fixtures.
- `ObjectMapper` to check baseline/candidate shapes independently.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` to test the old client over a real socket.
- A POST `/api/v1/reservations` endpoint proving **old requests omitting a new optional field remain valid**.

No Docker, DB, external HTTP server, or pseudocode is needed. Demo data is deterministic for reproducible assertions.

### 8.1. Directory layout

~~~text
api-compatibility-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/contracts/
    │   ├── ContractLabApplication.java
    │   ├── api/
    │   │   ├── CatalogController.java
    │   │   └── CatalogErrorHandler.java
    │   └── consumer/
    │       ├── LegacyProduct.java
    │       └── LegacyCatalogClient.java
    └── test/
        ├── resources/contracts/
        │   ├── product-v1.json
        │   ├── product-v2-additive.json
        │   ├── product-breaking-rename.json
        │   ├── product-breaking-units.json
        │   ├── reservation-v1-request.json
        │   └── reservation-v2-request.json
        └── java/com/example/contracts/
            ├── CatalogProviderContractTest.java
            ├── LegacyCatalogClientContractTest.java
            ├── JsonCompatibilityGateTest.java
            └── LiveHttpCompatibilityTest.java
~~~

Gradle Wrapper scripts/JAR must be generated via Gradle or taken from a repository; `gradle-wrapper.jar` is a binary and cannot be copied from Markdown. All other source and fixture files are listed below.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'api-compatibility-lab'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Spring Boot 3.3.x uses Spring Framework 6.1.x, which includes `RestClient` and `MockRestServiceServer.bindTo(RestClient.Builder)`. `spring-boot-starter-web` provides Jackson, Spring MVC, the servlet container, and the `RestClient` API; `spring-boot-starter-validation` provides Jakarta Validation. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, MockMvc, and mock REST client support.

**Do not add the Spring Cloud Contract plugin to this build**: the demo runs pure JUnit. The advanced CDC section explains how to configure it with a matching dependency BOM instead of mixing an unconfigured plugin into the runnable project.

### 8.4. ContractLabApplication.java

~~~java
package com.example.contracts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractLabApplication.class, args);
    }
}
~~~

The root package covers both `api` and `consumer`. The consumer is a plain Java class **without `@Component`**, because in this demo it represents a legacy client tested directly without needing an external base URL or `RestClient` bean in the Spring context.

## 9. Provider implementation: keeping old fields while adding optional ones

**src/main/java/com/example/contracts/api/CatalogController.java**

~~~java
package com.example.contracts.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CatalogController {

    @GetMapping(
        value = "/products/{sku}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductResponse getProduct(
            @PathVariable String sku) {

        if (!"BOOK-1".equals(sku)) {
            throw new ProductMissingException();
        }

        // Old fields preserve exact names, types, and meanings.
        // The availability field is a provider v2 addition.
        return new ProductResponse(
            "BOOK-1", "Java Basics",
            1999L, "IN_STOCK");
    }

    @PostMapping(
        value = "/reservations",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public ReservationResponse reserve(
            @Valid @RequestBody ReservationRequest request) {

        // note is optional: old requests remain valid.
        return new ReservationResponse(
            "RSV-1", request.sku(),
            request.quantity(), "PENDING");
    }

    public record ProductResponse(
            String sku,
            String name,
            long priceCents,
            String availability) {
    }

    public record ReservationRequest(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity,
            String note) {
    }

    public record ReservationResponse(
            String reservationId,
            String sku,
            int quantity,
            String status) {
    }

    public static class ProductMissingException
            extends RuntimeException {
    }
}
~~~

### What is protected?

**GET v1 shape** continues returning `sku`, `name`, `priceCents` with accurate units, while the provider adds `availability`. Endpoint path and HTTP method do not change.

**POST request** adds `note` as a nullable optional field: legacy JSON with only `sku`/`quantity` still binds to the `ReservationRequest` record with `note` as null, and validation accepts it. If a developer adds `@NotBlank` to `note`, old requests hit 400—a **breaking change** that provider tests must catch.

**Statuses** are preserved: GET 200, POST 201, missing product 404. Clients branching on status do not handle a POST success silently changing from 201 to async 202.

**Records** use Java 17 and Jackson configured via Spring Boot auto-configuration. Fixed values serve testing rather than a production data layer.

## 10. Error contract: stable 404 and 400 validation errors

**src/main/java/com/example/contracts/api/CatalogErrorHandler.java**

~~~java
package com.example.contracts.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CatalogErrorHandler {

    @ExceptionHandler(
        CatalogController.ProductMissingException.class)
    public ResponseEntity<ApiError> productMissing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalidReservation() {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_INPUT"));
    }

    public record ApiError(String code) {
    }
}
~~~

An error contract must verify **status**, **Content-Type**, and **body code** whenever consumers actually depend on them.

Why not return exception messages? Public JSON errors must not expose internal class names, SQL, credentials, or stack traces. The example keeps only a stable `code`. If your real app uses RFC 9457 `ProblemDetail`, test the `type/title/status/code` schema accordingly. Never change the error format just because Spring Boot was upgraded; create a migration plan.

**Limitation:** 415 Unsupported Media Type, 405 Method Not Allowed, and filter/container errors can emit different bodies. The demo specifies stable JSON error codes only for **404 missing SKU** and **400 bean validation**.

## 11. Legacy consumer: real Java code from an older client's viewpoint

**src/main/java/com/example/contracts/consumer/LegacyProduct.java**

~~~java
package com.example.contracts.consumer;

import java.util.Objects;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyProduct(
        String sku,
        String name,
        Long priceCents) {

    public LegacyProduct {
        if (sku == null || sku.isBlank()
                || name == null || name.isBlank()
                || priceCents == null
                || priceCents < 0) {
            throw new IllegalArgumentException(
                    "Invalid product contract");
        }
    }
}
~~~

Using `Long` instead of primitive `long` plus non-null validation prevents a dangerous bug: if `priceCents` is deleted from JSON, Java/Jackson could silently assign 0. A price of 0 might look like free merchandise; **silent corruption is worse than failing fast**.

`@JsonIgnoreProperties(ignoreUnknown=true)` lets this client ignore `availability` from provider v2. **Do not extrapolate that all consumers share this setting**: generated code, JSON Schema validators, or other languages can be strict. Verify compatibility across supported consumers.

**src/main/java/com/example/contracts/consumer/LegacyCatalogClient.java**

~~~java
package com.example.contracts.consumer;

import java.util.Objects;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class LegacyCatalogClient {

    private final RestClient http;

    public LegacyCatalogClient(RestClient http) {
        this.http = Objects.requireNonNull(http);
    }

    public LegacyProduct getProduct(String sku) {
        LegacyProduct value = http.get()
            .uri("/api/v1/products/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(LegacyProduct.class);

        if (value == null) {
            throw new IllegalStateException(
                    "Empty catalog response");
        }

        if (!sku.equals(value.sku())) {
            throw new IllegalStateException(
                    "Mismatched product SKU");
        }

        return value;
    }
}
~~~

When the provider returns HTTP 404/500, `RestClient.retrieve()` throws the corresponding error exception before trying to deserialize the body as `LegacyProduct`. Production consumers may map errors to domain-specific exceptions, which **must also be contract-tested**—never write `catch(Exception) -> return empty product` that masks bad data.

`RestClient` is a synchronous client, unlike reactive `WebClient`. Using it keeps the lab straightforward with `spring-boot-starter-web`; in production services using `WebClient`, test `WebClient` codecs and status handling explicitly.

## 12. Frozen JSON fixtures

Create these files under `src/test/resources/contracts/`. They are kept frozen rather than generated from provider DTOs at runtime.

### 12.1. product-v1.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999
}
~~~

This is the **consumer v1 baseline contract**. It has no `availability`.

### 12.2. product-v2-additive.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 1999,
  "availability": "IN_STOCK",
  "displayHint": "new field ignored by v1"
}
~~~

A tolerant old client ignores both new fields while original fields remain intact.

### 12.3. product-breaking-rename.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceInCents": 1999,
  "availability": "IN_STOCK"
}
~~~

This simulates a breaking change: `priceCents` vanished; the test expects the legacy client to reject it instead of creating price=0.

### 12.4. product-breaking-units.json

~~~json
{
  "sku": "BOOK-1",
  "name": "Java Basics",
  "priceCents": 20,
  "availability": "IN_STOCK"
}
~~~

The JSON shape is valid, yet the value breaks the business oracle “BOOK-1 costs 1,999 cents”. The consumer deserializes it cleanly; schema diffs **cannot catch this**. Provider contract tests must keep semantic assertions.

### 12.5. reservation-v1-request.json

~~~json
{
  "sku": "BOOK-1",
  "quantity": 2
}
~~~

Client v1 **has no `note`**. Provider v2 must continue returning 201.

### 12.6. reservation-v2-request.json

~~~json
{
  "sku": "BOOK-1",
  "quantity": 2,
  "note": "Gift wrap requested"
}
~~~

Provider v2 accepts the new field without **making it required**. Old and new requests must be tested separately to prove backward compatibility.

## 13. Provider contract tests with Spring MVC MockMvc

**src/test/java/com/example/contracts/CatalogProviderContractTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.core.io.ClassPathResource;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = ContractLabApplication.class)
@AutoConfigureMockMvc
class CatalogProviderContractTest {

    @Autowired
    private MockMvc mvc;

    private static String fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {

            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    @Test
    void providerKeepsLegacyResponseFieldsAndUnits()
            throws Exception {
        mvc.perform(get("/api/v1/products/BOOK-1")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.name")
                .value("Java Basics"))
            .andExpect(jsonPath("$.priceCents")
                .isNumber())
            .andExpect(jsonPath("$.priceCents")
                .value(1999));
    }

    @Test
    void additiveAvailabilityFieldDoesNotReplaceOldFields()
            throws Exception {
        mvc.perform(get("/api/v1/products/BOOK-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.priceCents")
                .value(1999))
            .andExpect(jsonPath("$.availability")
                .value("IN_STOCK"));
    }

    @Test
    void missingProductStillReturns404AndCode()
            throws Exception {
        mvc.perform(get("/api/v1/products/UNKNOWN")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                .value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void oldReservationRequestStillWorksWithoutNote()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(fixture(
                    "reservation-v1-request.json")))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.reservationId")
                .value("RSV-1"))
            .andExpect(jsonPath("$.sku")
                .value("BOOK-1"))
            .andExpect(jsonPath("$.quantity")
                .value(2))
            .andExpect(jsonPath("$.status")
                .value("PENDING"));
    }

    @Test
    void newOptionalNoteIsAcceptedToo()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(fixture(
                    "reservation-v2-request.json")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.reservationId")
                .value("RSV-1"));
    }

    @Test
    void missingQuantityIsStillValidationError()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"BOOK-1\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void invalidQuantityStillReturns400()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"BOOK-1\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void wrongContentTypeIsNotSilentlyTreatedAsJson()
            throws Exception {
        mvc.perform(post("/api/v1/reservations")
                .contentType(MediaType.TEXT_PLAIN)
                .content(
                    "{\"sku\":\"BOOK-1\",\"quantity\":2}"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

### Which test guards which change?

- `providerKeepsLegacyResponseFieldsAndUnits`: path, status, content type, and **old fields/price**.
- `additiveAvailabilityFieldDoesNotReplaceOldFields`: new fields may coexist alongside old fields without renaming.
- `missingProductStillReturns404AndCode`: status/error code was not changed to “200 + null”.
- `oldReservationRequestStillWorksWithoutNote`: old clients unaware of `note` can still create reservations.
- `newOptionalNoteIsAcceptedToo`: provider supports the extra input.
- `missingQuantityIsStillValidationError`: quantity requiredness was not accidentally loosened.
- `invalidQuantityStillReturns400`: `@Min(1)` remains active.
- `wrongContentTypeIsNotSilentlyTreatedAsJson`: media-type contract was not inadvertently relaxed.

**Do not use exact JSON string equality to block new fields**, because that enforces an overly rigid policy when consumers are tolerant. Assert required fields and semantics; evaluate extensions separately.

### What if the provider renames `priceCents` to `priceInCents`?

`jsonPath("$.priceCents")` fails. If price changes from 1999 to 20 while staying a number, `value(1999)` fails. That is why both **shape** and **business oracles** are necessary.

### What if the provider edits tests to match new code?

That is the risk of **self-agreement**. Editing the API and updating expected values without consumer contract review turns a breaking change into a “green test”. Baselines must have clear ownership, consumer review, or automated gates against supported versions.

## 14. Consumer contract tests with RestClient and MockRestServiceServer

**src/test/java/com/example/contracts/LegacyCatalogClientContractTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.example.contracts.consumer.LegacyCatalogClient;
import com.example.contracts.consumer.LegacyProduct;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class LegacyCatalogClientContractTest {

    private static final String BASE =
            "https://catalog.example.test";

    private MockRestServiceServer server;
    private LegacyCatalogClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl(BASE);

        server = MockRestServiceServer
                .bindTo(builder)
                .build();

        client = new LegacyCatalogClient(
                builder.build());
    }

    private static String fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {
            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    private void expectProductJson(String fileName)
            throws IOException {
        server.expect(requestTo(
                BASE + "/api/v1/products/BOOK-1"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                fixture(fileName),
                MediaType.APPLICATION_JSON));
    }

    @Test
    void legacyClientReadsOriginalV1Contract()
            throws Exception {
        expectProductJson("product-v1.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        assertEquals("BOOK-1", product.sku());
        assertEquals("Java Basics", product.name());
        assertEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void tolerantLegacyClientIgnoresAdditiveFields()
            throws Exception {
        expectProductJson(
                "product-v2-additive.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        assertEquals("BOOK-1", product.sku());
        assertEquals("Java Basics", product.name());
        assertEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void renamingRequiredFieldBreaksLegacyClient()
            throws Exception {
        expectProductJson(
                "product-breaking-rename.json");

        assertThrows(
            RestClientException.class,
            () -> client.getProduct("BOOK-1"));

        server.verify();
    }

    @Test
    void semanticUnitChangeMayDeserializeWithoutError()
            throws Exception {
        expectProductJson(
                "product-breaking-units.json");

        LegacyProduct product =
                client.getProduct("BOOK-1");

        // Deserializer DOES NOT catch the unit mismatch.
        assertEquals(
                20L, product.priceCents().longValue());
        assertNotEquals(
                1999L, product.priceCents().longValue());

        server.verify();
    }

    @Test
    void oldClientStillDistinguishes404()
            throws Exception {
        server.expect(requestTo(
                BASE + "/api/v1/products/UNKNOWN"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(
                withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(
                        "{\"code\":\"PRODUCT_NOT_FOUND\"}"));

        HttpClientErrorException error = assertThrows(
            HttpClientErrorException.class,
            () -> client.getProduct("UNKNOWN"));

        assertEquals(
                404, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("PRODUCT_NOT_FOUND"));

        server.verify();
    }

    @Test
    void changingResponseMediaTypeCanBreakReader()
            throws Exception {
        server.expect(requestTo(
                BASE + "/api/v1/products/BOOK-1"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                "<product/>", MediaType.APPLICATION_XML));

        assertThrows(
            RestClientException.class,
            () -> client.getProduct("BOOK-1"));

        server.verify();
    }
}
~~~

### Why `MockRestServiceServer.bindTo(RestClient.Builder)`?

Spring Framework 6.1 lets a mock server bind to `RestClient.Builder` to intercept HTTP calls from the client under test, assert method/URL, and return fixture responses. No real socket is opened; this is a **client boundary test**, not full network transport testing.

**Ordering note:** bind the mock server to `builder` **before calling `builder.build()`**. Creating the `RestClient` first or binding a different builder bypasses the mock server and makes the client attempt an outbound network connection.

### Limitations of the client test

- Consumer v1 sets `ignoreUnknown=true`, so additive fields pass **for this client**; a stricter consumer may still fail.
- Renaming `priceCents` is caught because `LegacyProduct` validates non-null in its constructor; using primitive `long` without validation could let Jackson return 0 and cause silent corruption.
- Semantic unit changes **still deserialize cleanly**. This test intentionally demonstrates the blind spot of schema/type checking; the **business oracle in the provider test** is what catches price 20 vs. 1999.
- HTTP 404 is verified by exception/status; if a new client changes error mapping, add explicit contracts for business callers.
- The mock server does not simulate real DNS, TLS, proxies, or socket timeouts; test network issues at another layer.

Do not interpret “`semanticUnitChangeMayDeserializeWithoutError` passed” as provider compatibility: it is a **negative illustration** showing that deserializers cannot catch semantic errors.

## 15. JSON compatibility gate with Jackson

Consumer code is not always available to run directly. You can build a **structural compatibility gate** comparing baseline and candidate payloads, treating it as a **supplementary** layer rather than sole proof.

**src/test/java/com/example/contracts/JsonCompatibilityGateTest.java**

~~~java
package com.example.contracts;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

class JsonCompatibilityGateTest {

    private final ObjectMapper mapper =
            new ObjectMapper();

    private JsonNode fixture(String name)
            throws IOException {
        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {
            return mapper.readTree(input);
        }
    }

    private static void assertLegacyFieldsRemain(
            JsonNode baseline, JsonNode candidate) {

        for (String field : List.of(
                "sku", "name", "priceCents")) {

            assertTrue(
                baseline.hasNonNull(field),
                "Baseline missing: " + field);

            assertTrue(
                candidate.hasNonNull(field),
                "Candidate removed: " + field);

            assertEquals(
                baseline.get(field).getNodeType(),
                candidate.get(field).getNodeType(),
                "Type changed: " + field);
        }
    }

    @Test
    void additiveCandidatePassesShapeGate()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode next = fixture(
                "product-v2-additive.json");

        assertDoesNotThrow(
            () -> assertLegacyFieldsRemain(old, next));

        assertTrue(next.has("availability"));
    }

    @Test
    void missingLegacyFieldFailsShapeGate()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode broken = fixture(
                "product-breaking-rename.json");

        assertThrows(
            AssertionError.class,
            () -> assertLegacyFieldsRemain(old, broken));
    }

    @Test
    void shapeOnlyCannotDetectChangedPriceUnits()
            throws Exception {
        JsonNode old = fixture("product-v1.json");
        JsonNode changed = fixture(
                "product-breaking-units.json");

        // Structural shape still passes.
        assertDoesNotThrow(
            () -> assertLegacyFieldsRemain(old, changed));

        // Yet the expected business value was broken.
        assertNotEquals(
                old.get("priceCents").longValue(),
                changed.get("priceCents").longValue());
    }
}
~~~

### Scope of this gate

`assertLegacyFieldsRemain` is **not** a complete JSON Schema compatibility checker. It checks only **three fields** and Jackson node types; it does not check arrays, nested objects, enums, min/max bounds, required request fields, regex constraints, nullability of all fields, or semantics.

In production:

- Protect the full schema using versioned OpenAPI/JSON Schema specs.
- Add consumer-driven contract interactions.
- For monetary fields, attach schema descriptions/`x-` properties and business invariants.
- Distinguish additive response rules from request widening/narrowing rules.
- Never treat an unreviewed snapshot diff approval as proof that clients will not break.

### Why not assert exact JSON equality?

If `candidate` validly adds `availability`, deep equality between v1 and v2 fails even though tolerant legacy clients still work. Conversely, an overly loose schema gate misses `priceCents` changing units. Assertions must reflect the **team's agreed compatibility policy**.

## 16. Real HTTP smoke: running the legacy client against provider v2

Provider MockMvc tests and consumer `MockRestServiceServer` tests sit on opposite sides independently. To close the “stubs pass, live app differs” gap, we run an integration smoke test over an HTTP server on a random port.

**src/test/java/com/example/contracts/LiveHttpCompatibilityTest.java**

~~~java
package com.example.contracts;

import com.example.contracts.consumer.LegacyCatalogClient;
import com.example.contracts.consumer.LegacyProduct;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ContractLabApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpCompatibilityTest {

    @LocalServerPort
    int port;

    private RestClient restClient() {
        return RestClient.create(
            "http://localhost:" + port);
    }

    @Test
    void legacyReaderWorksAgainstActualProviderV2() {
        LegacyCatalogClient legacy =
            new LegacyCatalogClient(restClient());

        LegacyProduct value = legacy.getProduct("BOOK-1");

        assertEquals("BOOK-1", value.sku());
        assertEquals("Java Basics", value.name());
        assertEquals(
            1999L, value.priceCents().longValue());
    }

    @Test
    void legacyPostBodyStillGets201AcrossSocket() {
        ResponseEntity<String> response =
            restClient()
                .post()
                .uri("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .body(
                    "{\"sku\":\"BOOK-1\","
                    + "\"quantity\":2}")
                .retrieve()
                .toEntity(String.class);

        assertEquals(
            HttpStatus.CREATED,
            response.getStatusCode());

        assertNotNull(response.getBody());
        assertTrue(
            response.getBody().contains("\"RSV-1\""));
        assertTrue(
            response.getBody().contains("\"PENDING\""));
    }

    @Test
    void missingSkuStillReports404OverHttp() {
        LegacyCatalogClient legacy =
            new LegacyCatalogClient(restClient());

        HttpClientErrorException error =
            assertThrows(
                HttpClientErrorException.class,
                () -> legacy.getProduct("UNKNOWN"));

        assertEquals(
            404, error.getStatusCode().value());
        assertTrue(error.getResponseBodyAsString()
                .contains("PRODUCT_NOT_FOUND"));
    }
}
~~~

### What is confirmed?

- The real server boots on a **random local port**.
- The legacy consumer and new provider run with the demo's actual Jackson/HTTP semantics.
- Additive response JSON fields still deserialize cleanly.
- Legacy POST bodies omitting `note` still receive HTTP 201.
- Missing SKUs still return 404 and the error code.

This does not test TLS proxies, gateway auth, rate limiting, CDNs, multi-instance load balancing, or data migrations. Those real boundaries require dedicated staging/canary environments.

**Do not slap `@Transactional` onto real-server tests expecting rollback**: HTTP client and server run in different thread/transaction contexts. This lab has no DB/side effects, keeping repeatability simple.

## 17. Total test count and run commands

| Test class | `@Test` count | Role |
| --- | ---: | --- |
| `CatalogProviderContractTest` | 8 | Provider HTTP routes/status/JSON/requests |
| `LegacyCatalogClientContractTest` | 6 | Consumer deserialization/error handling |
| `JsonCompatibilityGateTest` | 3 | Structural gate and semantic limitations |
| `LiveHttpCompatibilityTest` | 3 | Legacy client calling live HTTP provider v2 |
| **Total** | **20** | Multi-tier compatibility |

### Run commands

Requires JDK 17, Gradle Wrapper, and Maven Central access on first run:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run individual test classes:

~~~bash
./gradlew test --tests 'com.example.contracts.CatalogProviderContractTest'
./gradlew test --tests 'com.example.contracts.LegacyCatalogClientContractTest'
./gradlew test --tests 'com.example.contracts.JsonCompatibilityGateTest'
./gradlew test --tests 'com.example.contracts.LiveHttpCompatibilityTest'
~~~

Generate the Gradle Wrapper if missing and compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Force tests to re-run instead of using Gradle's up-to-date cache:

~~~bash
./gradlew test --rerun-tasks
~~~

Expected: **20 JUnit test methods succeed** with full source/fixtures/dependencies; this is expected behavior, **not a report of an executed Gradle/JUnit run** here. The lab uses no Docker/DB and writes nothing outside the Gradle build/test runtime. If a test fails locally, inspect `build/reports/tests/test/index.html` and JUnit XML to see whether the failure is in the provider, consumer, schema, or real HTTP integration.

### When running, which cases intentionally test for failure?

`renamingRequiredFieldBreaksLegacyClient` and `missingLegacyFieldFailsShapeGate` use `assertThrows` because they **deliberately feed breaking fixtures** to prove the detection mechanism works. They pass when the validator/consumer **catches the breakage**.

In a pipeline validating a **real provider candidate**, a breaking response must never be flipped into “green because we expected an error”. Provider tests and live HTTP smoke tests **must fail** when a candidate breaks the contract.

## 18. Compatibility concerns beyond JSON shape

### 18.1. Nullability

If an existing field was promised non-null, turning it into null breaks clients using primitives or unboxing. If the Java model uses `Long`, it may deserialize null and fail during arithmetic; add validation or business-layer contract tests.

### 18.2. Enum evolution

Suppose `status` used to only be:

~~~json
{"status":"PENDING"}
~~~

V2 adds:

~~~json
{"status":"ON_HOLD"}
~~~

A Java consumer using `enum Status { PENDING, COMPLETED }` can throw when Jackson parses an unknown enum. Tolerant clients can configure unknown-enum fallbacks (e.g., `@JsonEnumDefaultValue` with appropriate Jackson features), verified by real tests. **Adding enum values is not safe by default**.

### 18.3. Numeric precision and units

Cents as integers vs. dollars as decimals; numbers vs. strings; decimal precision; overflow on large amounts; and rounding when converting `BigDecimal` to `double` can corrupt reports while JSON remains a “number”. Tests should compare exact domain units, limits, and edge values—especially for payments and tax.

### 18.4. Dates and timezones

`2026-11-08T08:00:00Z` differs from `2026-11-08T08:00:00+07:00` as an instant. Switching from UTC to timezone-less local time can break clients even though JSON stays a string. Check ISO-8601 formatting, zone/offset, and semantics (“event time” vs. “processing time”).

### 18.5. List ordering

An API returning items sorted by `createdAt DESC` switches in v2 to `updatedAt DESC` while keeping the same schema. A cursor-paginated consumer may drop or duplicate items. Test sorting, cursors, stable tie-breakers, pagination boundaries, and concurrent writes.

### 18.6. Error handling and retries

If the provider turns a retryable `503` into `400`, old consumers may stop retrying. Changing `404` to `200 + empty` prevents old clients from noticing missing data. Raising `429` without `Retry-After` disrupts backoff policies. Error contracts need the same protection as happy paths.

### 18.7. Idempotency

An old client may retry a POST after a timeout using `Idempotency-Key`. If the new provider drops deduplication, the same request double-charges or creates duplicate orders. Contract tests must verify **stateful behavior and key reuse**, not just a one-off JSON status.

### 18.8. Authentication and authorization

Requiring a new OAuth scope can cause old clients to hit 403 even with unchanged request/response schemas. Rotating JWT issuers/audiences or changing `SameSite` cookie attributes can also break clients. Test with an identity/permission matrix; never treat CORS as an authorization substitute.

### 18.9. Eventual consistency

If POST used to return 201 after DB commit and now returns 202 for async processing, consumers reading state immediately afterward will fail. Treat this as a **behavioral contract change**, with job-status endpoints, retry semantics, and a migration plan.

### 18.10. Content negotiation and headers

If old clients send `Accept: application/json` while a new provider emits only `application/problem+json` on errors or switches `Content-Type` to XML/CSV, readers can fail. `ETag`, `Location`, `Cache-Control`, `Vary`, CORS, and pagination headers can also be part of the contract.

## 19. JSON response vs. JSON request: asymmetric compatibility directions

**Response:** Providers can typically **add** an optional field if consumers ignore unknown fields. Strict clients or canonical JSON signatures, however, may reject it.

**Request:** A new provider must still accept old requests; adding an optional request field is usually compatible because old clients **do not send it**. Adding `@NotNull`/`@NotBlank` to the new field causes old requests to fail with 400—breaking.

**Request coercion:** Changing Jackson property binding or unknown-field strictness on the provider can break clients that previously sent extra fields. Test against each consumer's request corpus, not just happy-path DTOs.

**Validation tightening:** Raising `quantity` min from 1 to 10 breaks old clients sending 2, even though the JSON schema type stays `int`. This is a behavioral/schema constraint break.

**Response field removal:** To rename a field, emit **both old and new fields** during a migration window, mark the old field deprecated, and track usage; delete it only after the support window closes. Verify consistency across aliases.

**Response new required field:** “Required field” in a **response schema** differs from required fields in a **request**. Adding a required response field helps new clients, yet does not guarantee old clients tolerate the unknown field; verify strictness.

## 20. Versioning alone does not solve compatibility

Common options:

- URI versioning: `/api/v1/...`, `/api/v2/...`.
- Header versioning: `API-Version: 2`.
- Media-type versioning: `Accept: application/vnd.example.v2+json`.
- Schema registry versioning (events).
- gRPC/Protobuf protocols with field numbering rules.

### A sensible migration path

To rename `priceCents` to `priceMinorUnits`:

1. Keep `priceCents` on `/api/v1` or in the same response during the transition window.
2. Add the new field with documented semantics and units.
3. Write tests for both consumer v1 and v2.
4. Migrate consumer v2 to the new field, keeping backward fallbacks if needed.
5. Measure usage of the old field/endpoint and announce deprecation.
6. Set a sunset date aligned with the actual support policy.
7. Once no supported consumers rely on the old field, release the breaking v2 endpoint/schema.
8. Only after migration completes, remove the v1 contract from CI as a recorded decision.

Simply changing `/v1` to `/v2` does not make an unmigrated change safe. Conversely, you can deploy provider binary v5 while keeping `/api/v1` stable for older clients.

### Expand–migrate–contract

This is a standard pattern for both data and APIs:

~~~text
EXPAND: add new field/endpoint/DB column while keeping the old one
   |
   v
MIGRATE: new consumers move onto the new contract
   |
   v
MONITOR: confirm old consumers have exited the support window
   |
   v
CONTRACT: remove old field/endpoint in a planned release
~~~

Never execute `contract` (removal) before old clients finish migrating.

## 21. Compatibility in message contracts: Kafka, RabbitMQ, and Avro

Event consumers can break when:

- `eventId` or `aggregateId` is dropped.
- Event type `OrderPaid` is renamed to `PaymentSettled`.
- A new enum value hits a handler with an exhaustive switch.
- Timestamp milliseconds change to seconds.
- Partition keys/ordering change, reordering workflows.
- Schema subject/registry compatibility mode changes.
- At-least-once delivery, retry, or DLQ policies relied upon by consumers change.
- Avro/Protobuf schema evolution rules are violated.

**Avro:** reader/writer schema resolution has specific rules for defaults, unions, and compatibility. A change marked BACKWARD-compatible by a schema registry still does not prove business semantics (e.g., cents->dollars).

**Protobuf:** never arbitrarily reuse field numbers; changing wire types breaks compatibility. Do not merely rename a Java class assuming the binary schema stays compatible. Reserve deleted tags/names.

**RabbitMQ JSON:** similar to HTTP JSON, with metadata also covering routing keys, exchanges, content types, message headers, retries, and DLQ behavior.

**Consumer-driven messaging contract tests** verify the payloads and headers consumers require; real broker integration tests verify listeners, serialization, and acks. Never treat “broker accepted the message” as proof the consumer processes business rules properly.

## 22. GraphQL, SOAP, and gRPC

### GraphQL

- **Adding fields** to a schema usually does not break existing queries.
- **Removing/renaming fields** breaks validation of old queries.
- **Changing nullable to non-null or vice versa** affects both schema clients and runtime null propagation; switching nullable to non-null changes error bubbling in responses.
- **Adding enum values** can break generated clients with exhaustive mappings.
- **Making an argument required** invalidates old queries.
- **Changing resolver semantics/performance** can break clients even when SDL stays unchanged.

Tests should run **real legacy queries** via `GraphQlTester` against the new schema/resolvers, beyond static schema diffs.

### SOAP/WSDL

- Changing namespaces, operations, or XSD request/response elements can break generated clients.
- Adding elements when schemas are strict can fail validation.
- Altering fault codes/details is a behavioral contract change.
- Test with XML/WSDL/XSD fixtures and real SOAP clients where needed.

### gRPC/Protobuf

- Protobuf field numbers and wire types matter more than Java names.
- Adding fields usually has schema-evolution support, yet does not promise business semantics.
- Streaming behavior, deadlines, metadata headers, and status codes are part of the contract too.
- Test old generated clients against the new server implementation; avoid testing only a freshly generated v2 client.

## 23. Database schema evolution and indirect clients

When two services share a DB schema (an arrangement generally best avoided), a DB migration can be a breaking change even when the HTTP API does not change.

Examples:

- Renaming/dropping a column while an older version still queries it.
- Adding a `NOT NULL` column without a default, breaking `INSERT`s from an older version.
- Changing an enum/check constraint, invalidating older values.
- Changing indexes/collations, affecting query semantics/ordering.
- Changing timezone/precision on timestamps/decimals.
- Changing transaction isolation or consistency behavior.

**Expand–contract migrations**:

1. Add nullable column or alias view first.
2. New app reads both old/new or performs controlled dual-writes.
3. Backfill data and verify totals.
4. Switch reads to the new schema.
5. Maintain rollback compatibility across the deployment overlap window.
6. Drop the old column after the support window.

Database migration tests need an integration harness matching production (e.g., Testcontainers PostgreSQL/MySQL); do not use H2 as a substitute for all PostgreSQL-specific semantics and claim migration compatibility.

## 24. CI release gate for compatibility

A realistic pipeline might look like:

~~~text
Pull Request opened
  |
  v
Unit tests
  |
  v
Generate OpenAPI/AsyncAPI/schema artifact
  |
  +-- Diff against released baseline
  |      +-- Breaking? -> review and block
  |
  v
Provider contract verification
  |      +-- Consumer v1, v2, v3 supported
  |
  v
Consumer stub tests
  |      +-- HTTP, deserialization, errors
  |
  v
Real HTTP/component smoke
  |
  v
Staging/canary traffic and observability
  |
  v
Release / rollback per policy
~~~

### A good compatibility gate

- Pulls its baseline from the **last released version** or approved contract registry, not just the prior commit on the branch.
- Knows deployed consumer versions and the **support window**.
- Checks method/path/status/headers/body/validation, not just Java DTOs.
- Includes semantic invariants for money, units, timezones, enums, and pagination.
- Uses server-side generated tests from consumer contracts where appropriate.
- Runs a real HTTP smoke test with the packaged artifact or equivalent server.
- On breaking changes, **fails the pipeline** or demands a documented exception/migration plan.
- Never auto-rewrites golden fixtures on every CI run.
- Tracks contract artifact version/owner and traceability to consumers.
- Never writes sensitive payloads/tokens into artifacts or CI logs.

### When a check FAILS

A useful diagnostic report:

~~~text
Contract: catalog-v1 / consumer mobile-2.9
Provider candidate: build 9f4...
Interaction: GET /api/v1/products/BOOK-1
Expected: HTTP 200, application/json
Expected fields: sku:string, name:string,
                 priceCents:integer cents
Actual: HTTP 200, application/json
Missing: priceCents
Unexpected: priceInCents
Impact: LegacyCatalogClient cannot deserialize
Decision: BLOCK release until alias restored or v2 migration
~~~

This is an **illustrative sample report**, not real stdout from the project. Never include tokens/credentials/PII in diagnostics. Reports must identify **which client breaks**, not just show a “JSON diff”.

## 25. Mutation tests: proving tests go red when the contract breaks

On a sandbox branch, try each mutation and revert immediately:

| Mutation | Test expected to turn red |
| --- | --- |
| Rename `priceCents` → `priceInCents` | Provider JSONPath + live client |
| Change price 1999 → 20 in provider | Business invariant provider/live tests |
| Delete `sku` | Provider JSONPath + legacy constructor |
| Delete `name` | Provider JSONPath + legacy constructor |
| Switch `ProductResponse` to XML | Provider Content-Type + client conversion |
| Change GET product from 200 to 202 | Provider status test |
| Change missing SKU from 404 to 200+null | Provider 404 + live HTTP error |
| Add `@NotBlank` to request `note` | Old reservation POST test |
| Change `@Min(1)` to `@Min(10)` | Old POST quantity=2 test |
| Change POST success 201 to 200 | Provider POST + live POST tests |
| Change error code `PRODUCT_NOT_FOUND` | Provider + consumer 404 tests |
| Change path `/api/v1` to `/api/v2` | All provider/live path tests |
| Switch unknown-field reader to strict | Consumer additive fixture test |
| Remove non-null price validation | Rename fixture may silently parse -> client test turns red |
| Enable caching serving stale data | Needs stateful cache contract tests |
| Drop idempotency key | Needs retry/stateful tests |
| Introduce new enum status | Needs enum consumer fixture tests |
| Change date timezone | Needs semantic/time tests |

**Just asserting “the test suite passes” is not enough.** A useful test must fail when the specific behavior it guards changes. When a mutation goes undetected, add a test at the right boundary instead of raising timeouts or weakening assertions.

## 26. Common pitfalls when testing compatibility

### 26.1. Provider writes both expected and actual

If a test serializes the new DTO and compares against that same JSON, a field rename updates both sides and keeps the test green. Fix this with **frozen consumer contract fixtures** and consumer-owned contracts.

### 26.2. Relying solely on OpenAPI diff

Specs can fall out of date, misrepresent the actual serializer, or miss semantic shifts. Treat diffs as an early warning, **not proof of runtime compatibility**.

### 26.3. Testing only the happy path

Statuses, errors, validation, auth, pagination, and retries can break clients even when GET 200 works. Add error interactions and negative tests.

### 26.4. Seeing an additive field and assuming it is safe

Strict, coercing, or codegen consumers can reject unknown response fields. Verify real consumers or publish a tolerant-reader contract.

### 26.5. Using primitives for mandatory JSON fields

A missing `long priceCents` can deserialize to 0 under some Jackson settings, letting the client silently misbehave. Use wrapper types + explicit validation when missing/null is unacceptable.

### 26.6. Testing only against the latest consumer

Mobile and partner clients stay on older versions. Tie contract checks to the deployed/supported consumer list, retiring gates only after the support window expires.

### 26.7. Updating fixtures when tests turn red without review

That “fixes” the test by silently rewriting a published contract. Contract version migrations require review, never blind regeneration to pass CI.

### 26.8. Assuming schema diffs catch currency/unit changes

Same JSON number changing between cents and dollars, rounding, or currency never appears in a type diff. Use semantic tests and domain constraints.

### 26.9. Using retries to mask breaking errors

If the provider returns a new 400 due to altered validation, retrying 3 times helps nothing. Retries belong strictly to transient/permitted failures with idempotency, never to hiding contract mismatches.

### 26.10. Too few cases in full HTTP integration

A random-port smoke suite tests only a handful of flows. Provider MockMvc and consumer stubs cover many branches quickly. Combine layers instead of replacing everything with slow E2E.

## 27. Contract review before deployment

When reviewing a PR that modifies an API, ask:

1. Does it change a **public contract** or only internal implementation?
2. Which clients/versions currently call this path?
3. Are any consumers strict about unknown fields, enums, or nulls?
4. When adding a request field, do old requests omitting it remain valid?
5. If status, error body, `Content-Type`, or permissions change, how do old clients react?
6. Did units, timezones, rounding, sorting, pagination, or idempotency change?
7. Can we keep an alias/default for a migration window?
8. Are real interaction tests and frozen old fixtures in place?
9. If schema diff warns, who approves a waiver and under what criteria?
10. Can the provider be rolled back without breaking consumers already using the new contract?
11. Are logs/metrics tagged by client version and error code to observe the rollout?
12. Have deprecation/sunset dates been announced with enough update time?
13. Could consumers deploy before the provider, or the provider before consumers?
14. For messaging, are schema registry compatibility modes and consumer lag policies right?
15. For DBs, is the migration backward-compatible during mixed-version deployments?

## 28. Practice exercises

**Exercise A — response rename:** Rename `priceCents` to `priceInCents` in the provider without touching the consumer. Identify which tests turn red and why the decoder fails on the missing required field.

**Exercise B — semantic units:** Keep the field name and type, but return `20` instead of `1999`. Observe the JSON shape gate passing while business invariants fail.

**Exercise C — additive:** Add `warehouse` to the response. Run the tolerant old client and verify it reads the 3 original fields without depending on `warehouse`.

**Exercise D — strict reader:** Create a legacy client without `@JsonIgnoreProperties(ignoreUnknown=true)` and enable unknown-property failure. Observe an additive field breaking the client.

**Exercise E — request optional:** Add `note` to `ReservationRequest` without `@NotBlank`; verify old POSTs still return 201.

**Exercise F — required request:** Add `@NotBlank` to `note` to induce breakage; old POSTs must turn red. Revert afterward.

**Exercise G — status semantics:** Change POST success from 201 to 202. Analyze migrating to an async job contract and what old clients receive.

**Exercise H — error mapping:** Change missing SKU from 404 to 200 with empty JSON. Check provider and live HTTP tests.

**Exercise I — enum:** Add `ON_HOLD` status to the response alongside a legacy enum parser that lacks support. Design a fallback or versioning plan.

**Exercise J — null:** Make the provider return `priceCents=null` for a SKU. The legacy record constructor should fail fast.

**Exercise K — pagination:** Build a GET list sorted by `createdAt DESC` with a cursor. Change the sort tie-breaker and write tests preventing duplicates/gaps.

**Exercise L — idempotency:** Add `Idempotency-Key` to POST, send two requests with the same key, and assert a single business effect.

**Exercise M — version gate:** Take a released OpenAPI baseline, run a diff against a candidate, and review breaking warnings.

**Exercise N — Spring Cloud Contract:** Write a contract DSL for GET product and generate provider verification tests/stubs using the Spring Cloud Contract version compatible with Boot 3.3.

**Exercise O — Pact:** Declare a consumer interaction and verify the provider against a Pact broker; explore keeping contracts per deployed consumer version.

**Exercise P — multi-version:** Add consumer v2 while retaining v1 in CI. Set a clear support window without deleting v1 just because v2 deployed.

**Exercise Q — network:** Use `@SpringBootTest(RANDOM_PORT)` to call the live endpoint with the old client and inspect statuses/errors. Compare with MockMvc-only.

**Exercise R — security:** Change a required OAuth scope on the endpoint, supply a v1 client principal in tests, and verify permissions do not regress silently.

**Exercise S — messaging:** Create Avro/Kafka v1/v2 schemas and verify compatibility mode; add semantic tests for timestamp units.

**Exercise T — expand–contract:** Draft a migration plan keeping `priceCents` during transition to `priceMinorUnits`, tracking consumer adoption and cutover.

## 29. Checklist before merging breaking-sensitive changes

- [ ] Identified whether the contract is public or internal?
- [ ] Identified deployed consumers and supported versions?
- [ ] Pulled baseline from last released/stable contract rather than generating from SUT?
- [ ] Provider tests check HTTP method/path/status/content type/headers per contract?
- [ ] JSON shape tests check required fields, types, and nullability?
- [ ] Request compatibility tests preserve old bodies and optional/required behavior?
- [ ] Old consumer code actually runs against candidate responses or matching stubs?
- [ ] Error responses (400/401/403/404/429/5xx) tested per consumer usage?
- [ ] Semantic assertions cover cents/currency/timezone/sorting/enums?
- [ ] Both positive/additive and negative/breaking tests exist?
- [ ] Response field additions verified against strict vs. tolerant consumers?
- [ ] API/schema diff used without treating it as the sole test layer?
- [ ] Status shifts, retries, idempotency, and timeouts addressed?
- [ ] Real HTTP smoke present when packaging/serialization/wiring matters?
- [ ] Schema evolution and broker/event integration tested for messaging?
- [ ] Mixed-version compatibility verified for DB migrations?
- [ ] CI blocks breaking changes or enforces documented migrations/waivers?
- [ ] Old fixtures never auto-regenerated when candidates change?
- [ ] Deprecation, sunset, and communication plan in place?
- [ ] Rollout includes canary, per-client-version telemetry, and rollback path?
- [ ] Never treating a passing “negative illustration” test as proof of provider compatibility?
- [ ] Clearly distinguished backward, forward, and full compatibility?
- [ ] Tested both new-provider/old-client and new-client/old-provider when deploys skew?
- [ ] Test reports confirm test methods executed rather than relying only on Gradle cache?
- [ ] No PII or secrets exposed in golden fixtures or CI artifacts?

## 30. References

Official documentation aligned with continuing from the **Spring Boot 3.3.5 / Java 17** lab:

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, MockMvc, `RANDOM_PORT`, `@RestClientTest`.
- [Spring Framework — Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): `MockRestServiceServer` and RestClient/RestTemplate test boundaries.
- [Spring Framework 6.1 — MockRestServiceServer API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): `bindTo(RestClient.Builder)`.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient request/response and error handling.
- [Spring Cloud Contract 4.1 Reference](https://docs.spring.io/spring-cloud-contract/reference/4.1/): consumer-driven/provider-driven contracts and stubs.
- [Spring Cloud 2023.0.x Reference](https://docs.spring.io/spring-cloud/docs/2023.0.x/reference/htmlsingle/): release train compatible with Boot 3.3.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): schemas, request/response definitions, status codes, and API descriptions.
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step): types, required fields, nullability, and object evolution.
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods, status semantics, HTTP fields.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): reader/writer schemas and resolution.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field numbers and wire compatibility.
- [Pact Documentation](https://docs.pact.io/): consumer-driven contracts, provider verification, and deployment checks.
- [Jackson JsonIgnoreProperties](https://fasterxml.github.io/jackson-annotations/javadoc/2.16/com/fasterxml/jackson/annotation/JsonIgnoreProperties.html): tolerant reading behavior.

**Remember:** An API change is backward-compatible only after proving **old consumers still send requests, read responses, and preserve business behavior**. Combine frozen contracts, provider MockMvc, legacy consumer tests, JSON/schema diffs, real HTTP smoke tests, and semantic assertions. When breaking changes are unavoidable, choose **versioning + expand–migrate–contract + parallel support**, never silently updating fixtures just to turn tests green and ship.
