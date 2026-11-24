# Consumer-Driven Contracts When Multiple Services Evolve Independently

## 1. Why is consumer-driven contract testing needed?

Suppose three teams develop independently:

- **CheckoutWeb** makes HTTP calls to **InventoryService** to display product details.
- **BillingService** also calls InventoryService, but only cares about price and SKU.
- **InventoryService** wants to refactor its model, add fields, change databases, split services, and deploy quickly without coordinating simultaneous deployments with both consumers.

Each repository's unit tests can all PASS while production still breaks: one consumer needs the `title` field yet the provider renames it to `name`; the provider changes status 404 to 200 with an error body; the consumer sends malformed headers/JSON; or the provider removes an endpoint while an older consumer is still running.

**Consumer-driven contracts (CDC)** solve the communication boundary: each consumer describes the requests it **actually sends** and the responses it **needs to function properly**. The provider continuously verifies that it meets those expectations. Contracts are versioned alongside consumer/provider builds to determine **which versions can deploy together** without forcing all teams to release simultaneously.

Core idea:

~~~text
CheckoutWeb consumer                         InventoryService provider
         |                                             |
         |  Consumer Pact test                         |  Provider verification
         |  runs real HTTP client                      |  runs real application
         v                                             v
  Pact MockServer                              Real HTTP endpoint
         |                                             ^
         | writes interactions as Pact JSON            |
         +---- publish artifact / Pact Broker ---------+
                           |
                           +--- verification matrix
                           +--- can-i-deploy release gate
~~~

The consumer does not prescribe “every API the provider must have”. The consumer publishes only **what it uses**. The provider remains free to add fields/endpoints beyond those requirements.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish **consumer**, **provider**, **interaction**, **provider state**, **Pact file**, and **Pact Broker**.
2. Compare CDC with unit, integration, end-to-end, OpenAPI/schema validation, and Spring Cloud Contract.
3. Write consumer tests with Pact JVM/JUnit 5, invoking the **production HTTP client** against a mock server and generating a Pact artifact.
4. Write provider tests with Spring Boot and `@PactFolder`/`@Provider`/`@State`, verifying Pacts against a real endpoint.
5. Understand why provider verification is mandatory: a passing consumer mock **does not prove the real provider is compatible**.
6. Design flexible Pact matchers without over-specifying unused fields.
7. Verify 200 and 404 statuses, request headers, bodies, error contracts, and provider states.
8. Use Pact Broker, branch/version/deployment metadata, `can-i-deploy`, and `record-deployment`.
9. Distinguish `pending pacts` from `WIP pacts` so neither stalls provider pipelines nor hides compatibility bugs.
10. Plan expand–migrate–contract when multiple consumers/versions deploy independently.
11. Recognize contract test limits regarding timeouts, retries, idempotency, security, performance, and messaging.
12. Build a CDC pipeline that accurately determines which consumer/provider versions are safe for each environment.

## 2. What is a contract, and how does it differ from an API schema?

An *HTTP interaction* consists of a concrete request and the response the consumer expects:

~~~http
GET /api/books/42 HTTP/1.1
Accept: application/json
~~~

The consumer expects:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Clean Code"}
~~~

Another interaction when the book does not exist:

~~~http
GET /api/books/404 HTTP/1.1
Accept: application/json
~~~

The expectation is status `404 Not Found`; if the client does not read the error body, the contract **does not need** to freeze the entire error body contents.

**OpenAPI** can describe every endpoint and many schemas that might be called. A **consumer contract** captures the exact subset of requests/responses that **a specific consumer version depends on**. The two complement rather than replace each other.

| Aspect | OpenAPI/schema validation | Consumer-driven Pact |
| --- | --- | --- |
| Who states expectations? | Usually governed by provider/API owners | Consumers write tests for actual needs |
| Scope | Broader API surface | Only interactions the consumer uses |
| Can the provider change? | Controlled via schema and versioning policy | Must pass Pacts of relevant consumer versions |
| Is there a mock service? | Mocks/stubs can be generated from schema | Pact consumer tests run a mock from interactions |
| Does it verify the real provider? | Needs provider implementation tests | Provider verifier replays Pacts on the real service |
| Is there a deploy matrix? | Not automatically from standalone YAML/JSON | Pact Broker Matrix + `can-i-deploy` |
| Sufficient end-to-end? | No | Also no |

**Do not interpret contract tests as “forcing two services to deploy together”.** The very purpose of Pact Broker and deployment checks is to enable **independent deployments backed by compatibility evidence**.

## 3. Multi-team context and ownership boundaries

Suppose checkout needs only two things:

- `GET /api/books/{id}` with `id=42` returns status 200 with JSON numeric field `id` and string `title`.
- `GET /api/books/404` returns status 404 so CheckoutWeb treats it as “not found”.

The provider may include `stock`, `author`, or `updatedAt` in the 200 response without CheckoutWeb reading them. Consumers **should not pin exact default values for fields they do not need**; Pact defaults to matchers supporting appropriate types and policies.

Consumer v1 may read only `title`. Consumer v2 also reads `availability`; the provider must supply the new field before v2 deploys. Meanwhile, the provider must continue serving active v1 consumers.

### 3.1 Ownership

| Component | Typical owner | Responsibility |
| --- | --- | --- |
| Consumer application code | CheckoutWeb team | Defines outgoing requests, response parsing, fallbacks |
| Consumer Pact | CheckoutWeb team | Selects meaningful interactions and matchers |
| Provider implementation | InventoryService team | Ensures all relevant Pacts verify |
| Provider state fixtures | InventoryService team | Prepares data for each interaction |
| Broker | Platform/shared team | Stores Pact versions, verification results, and deployments |
| Release gate | Each service's CI/CD | Runs `can-i-deploy` for exact version and environment |
| Governance/API docs | API owner or platform | Manages public API contracts, deprecation, security |

The provider should **not** write a fake consumer that bypasses real client code and claim consumer behavior is verified. CDC only carries meaning when the consumer test executes the **client/adapter** the application actually runs in production.

## 4. Consumer tests and provider tests prove two different statements

Consumer tests prove:

> Given a response conforming to the contract, CheckoutWeb code builds the right request and extracts the required information properly.

Provider verification proves:

> Under specific provider states, the real InventoryService version returns responses conforming to the published contract.

When running only the consumer test:

~~~text
Consumer test PASS:
    client sends GET /api/books/42
    mock server returns fake JSON
    client parses BookDto

DOES NOT imply:
    real InventoryService supports /api/books/42
    real provider response contains title
    production authentication works
    consumer v2 can deploy alongside provider v1
~~~

Running only provider verification without the latest consumer tests can also verify a stale Pact and miss new needs. Thus both sides must share the **same Pact artifact** generated by the consumer and verified by the provider.

## 5. Pact interactions and provider states

A Pact file can hold multiple interactions for a consumer/provider pair:

~~~text
CheckoutWeb -> InventoryService
    1. given "book 42 exists"
       request GET /api/books/42
       response 200, JSON id=number,title=string

    2. given "book 404 is absent"
       request GET /api/books/404
       response 404
~~~

`given(...)` describes the **provider state**: the data/conditions that must exist before the request runs. The consumer-side Pact mock server **does not need to spin up a real database**. During provider verification, the provider team writes `@State` callbacks to seed that state in the test application.

Benefits:

- Data does not depend on production records.
- Does not assume the provider already has book ID 42 in every environment.
- A 404 test will not flake because another test created book 404.
- Every interaction has isolated fixtures, independent of test order.
- The provider can swap persistence implementations as long as the external contract holds.

### 5.1 Provider state names are part of the coordination contract

If a Pact declares `given("book 42 exists")` yet the provider only defines `@State("a book exists")`, verification fails because the **state name mismatches**. Do not work around this by omitting `given` or relying on arbitrary records in a production DB; align meaningful state names and parameters.

For generated IDs, Pact V3/V4 supports **provider state generators** so provider callbacks can return dynamic IDs. This lesson uses fixed IDs for clarity; production suites can use generators when IDs are known only after fixture insertion.

## 6. Hands-on project: two Gradle modules, two independent services

The mini-project uses **Java 17+, Spring Boot 3.5.0, Pact JVM 4.6.17, and JUnit 5**.

- `consumer`: CheckoutWeb module; Java HTTP client + Jackson + Pact consumer tests.
- `provider`: InventoryService module; Spring Boot REST controller + in-memory catalog + Pact provider verification on `RANDOM_PORT`.
- Consumer tests emit artifacts into `consumer/build/pacts`.
- Provider tests are configured in Gradle to run **after** consumer tests and read the exact Pact file without regenerating a second contract.

~~~text
independent-service-contracts/
  settings.gradle
  consumer/
    build.gradle
    src/main/java/example/consumer/
      BookDto.java
      InventoryClient.java
    src/test/java/example/consumer/
      InventoryConsumerPactTest.java
  provider/
    build.gradle
    src/main/java/example/provider/
      InventoryApplication.java
      BookDto.java
      BookCatalog.java
      BookController.java
    src/test/java/example/provider/
      InventoryProviderPactTest.java
~~~

The example set has **two JUnit `@Test` methods in the consumer** and one **provider `@TestTemplate` generating one verification invocation per interaction in the Pact** (two expected provider verification invocations). It uses no database, Docker, or Broker during local runs—only the localhost Pact mock HTTP server and Spring Boot's embedded HTTP server on a random port.

### 6.1 Limitations of the mini-project

The example focuses on HTTP GET/200/404 and provider states; it does not simulate full service discovery, OAuth, database transactions, Redis, or message brokers. Those mechanisms are covered in the extension sections. Pinned versions are for reproducibility, **do not claim to be the newest releases**, and **do not represent an executed build log**.

## 7. settings.gradle

Root `settings.gradle`:

~~~groovy
rootProject.name = 'independent-service-contracts'
include 'consumer', 'provider'
~~~

Each module has its own source/test classpath, so the consumer can evolve its client and the provider can evolve its implementation independently. In production, the two modules may live in separate repositories exchanging artifacts via a Pact Broker rather than a shared build folder.

## 8. consumer/build.gradle

~~~groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.0'
    }
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'au.com.dius.pact.consumer:junit5:4.6.17'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    // Consumer Pact files are written into the consumer build directory.
    systemProperty 'pact.rootDir',
            file("$buildDir/pacts").absolutePath
}
~~~

The consumer **does not need** the Spring Boot runtime to use Pact. The Boot BOM simply aligns Jackson and JUnit versions with the provider. `au.com.dius.pact.consumer:junit5` is the Pact JVM 4.6.x artifact coordinate, rather than legacy Pact 4.0 coordinates.

### 8.1 Why are Pact versions pinned?

When the consumer uses Pact JVM 4.6.x and the provider uses a compatible V3/V4 line, the generated Pact format is handled seamlessly. In production, plan version upgrades deliberately, re-testing JDK/Java dependencies and Pact specification compatibility. Do not upgrade one module alone assuming Pact JSON never changes.

## 9. provider/build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'au.com.dius.pact.provider:junit5:4.6.17'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    // Require consumer to generate artifacts before provider verification.
    dependsOn ':consumer:test'

    // @PactFolder relative paths resolve from projectDir.
    workingDir projectDir
}
~~~

`test.dependsOn(':consumer:test')` is strictly **local demo orchestration**; in truly independent systems, provider CI fetches published Pacts from the Broker rather than depending on the consumer source repo. The lesson omits the provider-specific Spring 6 extension because basic Pact `junit5` can already verify the HTTP target of a running Spring Boot app.

### 9.1 Gradle wrapper and test ordering

From the workspace root with the Gradle wrapper:

~~~bash
./gradlew :provider:test
~~~

The task graph puts `:consumer:test` ahead of `:provider:test`. If consumer tests fail, the Pact is not valid and provider verification should not be considered complete. If `:consumer:test` is UP-TO-DATE, Gradle reuses previous build outputs; a clean run regenerates the artifact.

For a clean run from the root:

~~~bash
./gradlew :consumer:clean :provider:clean :provider:test
~~~

**Do not delete Pact files before provider verification.** In distributed CI, artifact transfer must include checksums/versions rather than reading an ambiguous `latest` file.

## 10. Consumer domain model: BookDto.java

File `consumer/src/main/java/example/consumer/BookDto.java`:

~~~java
package example.consumer;

public record BookDto(long id, String title) {
}
~~~

A Java record keeps the model small. The consumer only cares about `id` and `title`. The provider can add a `stock` field in JSON that the consumer ignores. Jackson 2.18+ supports record deserialization on Java 17.

**A common backward-compatibility bug:** renaming `title` to `name` prevents the consumer's `title` field from being populated properly. When the consumer enforces `title` as required, provider Pact verification must fail before the incompatible provider change deploys.

## 11. Consumer HTTP client: InventoryClient.java

File `consumer/src/main/java/example/consumer/InventoryClient.java`:

~~~java
package example.consumer;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class InventoryClient {

    private final URI baseUrl;
    private final HttpClient http;
    private final ObjectMapper json;

    public InventoryClient(URI baseUrl, ObjectMapper json) {
        this.baseUrl = baseUrl;
        this.json = json;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }

    public Optional<BookDto> find(long id)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(
                baseUrl.resolve("/api/books/" + id))
                .timeout(Duration.ofSeconds(3))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 404) {
            return Optional.empty();
        }

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Inventory returned HTTP "
                    + response.statusCode());
        }

        return Optional.of(
                json.readValue(response.body(), BookDto.class));
    }
}
~~~

The consumer test invokes the **exact `find` method** used by CheckoutWeb code instead of manually building an `HttpClient.newHttpClient().send` call inside the test. That way the Pact test catches bugs in request path, `Accept` header, status handling, and mapping.

### 11.1 Error policy in the client

- `200`: parse JSON and return `Optional.of(BookDto)`.
- `404`: treat as missing, return `Optional.empty()`.
- Any other status: throw an exception so callers distinguish 401/403/5xx from a missing book.
- `IOException`/`InterruptedException` are propagated rather than silently turned into empty.

Production clients also need latency metrics, **selective** retries, circuit breakers, correlation IDs, and cancellation. This contract **does not** test real network timeouts/retries; that belongs to dedicated resilience tests.

### 11.2 Why use a configurable baseUrl?

The client accepts a URI in its constructor, allowing Pact tests to point `baseUrl` to the Pact mock server while production reads configuration/service discovery. **Never hardcode localhost:8080** in the client; CI runs in parallel and Pact picks random ports.

## 12. Consumer Pact test: InventoryConsumerPactTest.java

File `consumer/src/test/java/example/consumer/InventoryConsumerPactTest.java`:

~~~java
package example.consumer;

import java.net.URI;
import java.util.Map;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;

import au.com.dius.pact.consumer.MockServer;
import au.com.dius.pact.consumer.dsl.PactDslJsonBody;
import au.com.dius.pact.consumer.dsl.PactDslWithProvider;
import au.com.dius.pact.consumer.junit5.PactConsumerTest;
import au.com.dius.pact.consumer.junit5.PactTestFor;
import au.com.dius.pact.core.model.RequestResponsePact;
import au.com.dius.pact.core.model.annotations.Pact;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@PactConsumerTest
class InventoryConsumerPactTest {

    @Pact(
        consumer = "CheckoutWeb",
        provider = "InventoryService")
    public RequestResponsePact existingBook(
            PactDslWithProvider builder) {

        return builder
                .given("book 42 exists")
                .uponReceiving("get a book by ID")
                .path("/api/books/42")
                .method("GET")
                .headers(Map.of("Accept", "application/json"))
                .willRespondWith()
                .status(200)
                .headers(Map.of(
                        "Content-Type", "application/json"))
                .body(new PactDslJsonBody()
                        .integerType("id", 42L)
                        .stringType("title", "Clean Code"))
                .toPact();
    }

    @Pact(
        consumer = "CheckoutWeb",
        provider = "InventoryService")
    public RequestResponsePact missingBook(
            PactDslWithProvider builder) {

        return builder
                .given("book 404 is absent")
                .uponReceiving("get a missing book")
                .path("/api/books/404")
                .method("GET")
                .headers(Map.of("Accept", "application/json"))
                .willRespondWith()
                .status(404)
                .toPact();
    }

    @Test
    @PactTestFor(pactMethod = "existingBook")
    void clientParsesRequiredFields(MockServer mock)
            throws Exception {

        InventoryClient client = new InventoryClient(
                URI.create(mock.getUrl()), new ObjectMapper());

        Optional<BookDto> result = client.find(42L);

        assertEquals(
                new BookDto(42L, "Clean Code"),
                result.orElseThrow());
    }

    @Test
    @PactTestFor(pactMethod = "missingBook")
    void clientTreats404AsAbsent(MockServer mock)
            throws Exception {

        InventoryClient client = new InventoryClient(
                URI.create(mock.getUrl()), new ObjectMapper());

        assertTrue(client.find(404L).isEmpty());
    }
}
~~~

**Two JUnit `@Test` methods** and two `@Pact` definitions.

### 12.1 Most important lines explained

- `@Pact(consumer="CheckoutWeb",provider="InventoryService")` sets the **exact participant names**; the provider test and Broker must match verbatim.
- `given(...)` specifies the state the provider must set up, rather than having the consumer build a real database.
- `uponReceiving(...)` gives a human-readable interaction description for debugging.
- `path`/`method`/`headers` describe the request the consumer is allowed/expected to send.
- `status`/`Content-Type`/`PactDslJsonBody` describe the response the consumer needs.
- `integerType("id",42L)` and `stringType("title","Clean Code")` require matching JSON types without locking down extra fields.
- `@PactTestFor(pactMethod=...)` binds each test to its exact definition instead of implicitly picking the first Pact.
- `MockServer` injection supplies the test URL/port without starting a production server.

### 12.2 Why must the Pact be generated from consumer tests?

If the provider team writes a JSON contract by hand without running the consumer's real client, both sides can agree on a contract *unrelated to deployed code*. Calling the real `InventoryClient.find` is essential: the Pact test verifies the actual requests emitted by the client, not requests copy-pasted into a test.

### 12.3 Relationship to JUnit assertions

The Pact mock verifies that the outgoing request matches the defined interactions and was actually executed. JUnit assertions verify the consumer handles the response properly. Both must PASS; hitting the mock server over HTTP without asserting deserialization/fallbacks leaves consumer behavior untested.

## 13. How is the Pact artifact generated?

After consumer tests run, Pact JVM writes a file named after the participant pair inside `consumer/build/pacts`, e.g.:

~~~text
consumer/build/pacts/CheckoutWeb-InventoryService.json
~~~

The **simplified conceptual** content below shows the two interactions:

~~~json
{
  "consumer": {"name": "CheckoutWeb"},
  "provider": {"name": "InventoryService"},
  "interactions": [
    {
      "description": "get a book by ID",
      "providerStates": [{"name": "book 42 exists"}],
      "request": {
        "method": "GET",
        "path": "/api/books/42",
        "headers": {"Accept": "application/json"}
      },
      "response": {
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": {"id": 42, "title": "Clean Code"}
      }
    },
    {
      "description": "get a missing book",
      "providerStates": [{"name": "book 404 is absent"}],
      "request": {"method": "GET", "path": "/api/books/404"},
      "response": {"status": 404}
    }
  ]
}
~~~

**This is not the byte-for-byte generated Pact file.** Pact JVM also records matching rules, metadata/spec versions, and may format headers differently. **Do not copy this abbreviated JSON as input to the provider test**; always use the file generated by the consumer suite.

### 13.1 The generated contract is an artifact of one consumer version

In consumer CI, tag the Pact file with an immutable commit SHA/build version. This file is an **output of that consumer test version**, not a fixed global API contract detached from version history.

Whenever the consumer changes request/response expectations, the Pact content changes; the Broker needs to know which consumer version/branch published that Pact.

### 13.2 Do not blindly merge stale Pact files

Pact JVM may merge interactions into an existing Pact file depending on writer settings. In CI, run in a clean workspace or configure overwrite mode appropriately so interactions removed from consumer code do not linger. Never delete contracts of **deployed** consumer versions from the Broker; the provider must keep supporting them until those versions are retired.

## 14. Provider Spring Boot application: InventoryApplication.java

File `provider/src/main/java/example/provider/InventoryApplication.java`:

~~~java
package example.provider;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Root package `example.provider` scans the controller and catalog in the same package. The Pact test starts the embedded HTTP server on a random port to verify the **real Spring MVC response**.

## 15. Provider model: BookDto.java

File `provider/src/main/java/example/provider/BookDto.java`:

~~~java
package example.provider;

public record BookDto(long id, String title) {
}
~~~

This is the provider's independent model, separate from the consumer's `BookDto`. **Do not share a single Java DTO JAR across two services just for testing**, because shared models hide schema incompatibility: a change compiles both sides simultaneously even though production runs different deployed versions.

The two DTOs look alike in the example because they describe the same HTTP payload, yet their source code and ownership remain separate.

## 16. Provider in-memory state: BookCatalog.java

File `provider/src/main/java/example/provider/BookCatalog.java`:

~~~java
package example.provider;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Repository;

@Repository
public class BookCatalog {

    private final ConcurrentMap<Long, BookDto> books =
            new ConcurrentHashMap<>();

    public Optional<BookDto> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public void clear() {
        books.clear();
    }

    public void put(BookDto book) {
        books.put(book.id(), book);
    }
}
~~~

The catalog serves only this mini-project. Production can replace it with a JPA repository, tenant-scoped query, cache, or remote service. Provider state handlers are responsible for resetting/seeding the **actual source of truth** used by the HTTP controller.

### 16.1 Why use state setup instead of hardcoded controller data?

If the controller hardcodes returning `Book("Clean Code")` just to make Pact PASS, provider verification skips real service/repository wiring. Test state setup also validates the integration slice and allows the provider implementation to evolve independently.

## 17. Provider HTTP controller: BookController.java

File `provider/src/main/java/example/provider/BookController.java`:

~~~java
package example.provider;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> find(@PathVariable long id) {

        BookDto book = catalog.find(id).orElse(null);

        if (book != null) {
            return ResponseEntity.ok(book);
        }

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "BOOK_NOT_FOUND"));
    }
}
~~~

The endpoint returns:

- Book 42 exists: `200`, JSON with `id` and `title`.
- Book 404 does not exist: `404`, provider-chosen JSON error body.

The consumer Pact verifies status 404, **without** locking down the exact error body because the client returns `Optional.empty()` without parsing `code`. If CheckoutWeb later reads `code` to show distinct messages, the consumer must add matching expectations to the Pact.

## 18. Provider verification: InventoryProviderPactTest.java

File `provider/src/test/java/example/provider/InventoryProviderPactTest.java`:

~~~java
package example.provider;

import au.com.dius.pact.provider.junitsupport.Provider;
import au.com.dius.pact.provider.junitsupport.State;
import au.com.dius.pact.provider.junitsupport.loader.PactFolder;
import au.com.dius.pact.provider.junit5.PactVerificationContext;
import au.com.dius.pact.provider.junit5.PactVerificationInvocationContextProvider;
import au.com.dius.pact.provider.junit5.HttpTestTarget;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestTemplate;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@Provider("InventoryService")
@PactFolder("../consumer/build/pacts")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryProviderPactTest {

    @LocalServerPort int port;

    @Autowired BookCatalog catalog;

    @BeforeEach
    void beforeEachInteraction(PactVerificationContext context) {
        context.setTarget(new HttpTestTarget("localhost", port));
    }

    @State("book 42 exists")
    void bookExists() {
        catalog.clear();
        catalog.put(new BookDto(42L, "Clean Code"));
    }

    @State("book 404 is absent")
    void missingBook() {
        catalog.clear();
    }

    @TestTemplate
    @ExtendWith(PactVerificationInvocationContextProvider.class)
    void verifyEachConsumerInteraction(
            PactVerificationContext context) {
        context.verifyInteraction();
    }
}
~~~

This is **a JUnit `@TestTemplate`**: the Pact extension creates **one verification invocation per interaction** in the Pact file (expected two invocations from the consumer demo).

### 18.1 Role of the annotations

- `@Provider("InventoryService")`: provider name must match the Pact.
- `@PactFolder("../consumer/build/pacts")`: loads the Pact artifact generated by the consumer. In the Gradle demo, the path resolves relative to the `provider` project working directory.
- `@SpringBootTest(RANDOM_PORT)`: starts a real Spring Boot HTTP server rather than hand-mocking responses.
- `@LocalServerPort`: supplies the dynamic port to the verifier via `HttpTestTarget`.
- `@BeforeEach`: configures the target before each interaction verification, following the Pact JUnit 5 lifecycle.
- `@State("book 42 exists")`: seeds data for the success interaction.
- `@State("book 404 is absent")`: clears data for the not-found interaction.
- `@TestTemplate` and `PactVerificationInvocationContextProvider`: Pact sends requests to the provider and compares status/headers/body against the consumer Pact.
- `context.verifyInteraction()`: actually executes the verifier, rather than merely booting the test context.

### 18.2 The test must fail when Pacts are missing

Pact provider JUnit 5 normally fails if no Pact is found to verify. **Do not** add `@IgnoreNoPactsToVerify` just to keep the pipeline green when no Pacts exist; it hides artifact delivery or Broker selector errors. Keep the failure so CI catches empty folders, wrong provider names, bad paths, or skipped consumer tests.

### 18.3 Why must provider states be independent and reset?

The 404 interaction must not depend on whether the success test ran before or after it. `catalog.clear()` inside each `@State` keeps runs deterministic. If the provider uses a DB, prepare fixtures with proper cleanup and transaction visibility; Pact verification sends HTTP requests handled on a different thread than the test thread.

**Do not rely on `@Transactional` rollback on the test thread** to clean up writes made by the HTTP server thread: their transaction boundaries differ. Use an isolated test DB, explicit setup/teardown, or Testcontainers.

## 19. Running locally and reading results accurately

From the root of the multi-project with the Gradle wrapper:

~~~bash
./gradlew :consumer:clean :provider:clean :provider:test
~~~

Because the provider task depends on the consumer task:

~~~text
:consumer:compileJava
:consumer:compileTestJava
:consumer:test              -> 2 consumer @Test methods
                             -> generated Pact JSON
:provider:compileJava
:provider:compileTestJava
:provider:test              -> Pact @TestTemplate
                             -> expected 2 interaction invocations
~~~

The order diagram above is an **illustration of task dependencies**, not captured Gradle stdout. Gradle can interleave compile tasks; what is guaranteed is that `:consumer:test` completes before `:provider:test` runs.

Expected behavior:

| Interaction | Consumer test | Provider verification |
| --- | --- | --- |
| Book 42 exists | Mock GET 200; client parses `BookDto(42,"Clean Code")` | `@State` seeds book 42, HTTP 200 with matching id/title |
| Book 404 absent | Mock GET 404; client returns `Optional.empty` | `@State` clears catalog, HTTP 404 |
| Provider renames `title` to `name` | Consumer mock still PASSES per old Pact | Provider verification **FAILS** due to missing `title` field |
| Provider removes endpoint | Consumer mock still PASSES | Provider verification **FAILS** on status/path |
| Provider adds `stock` field | Consumer still PASSES | Provider usually PASSES if Pact does not forbid extra fields |

No build/test execution was actually run in this text; these PASS/FAIL outcomes are **expected results per contract definition**. When running locally, inspect:

~~~text
consumer/build/reports/tests/test/index.html
provider/build/reports/tests/test/index.html
consumer/build/pacts/
~~~

### 19.1 When provider verification fails

Check each failure category:

1. Pact path or provider name mismatch.
2. Missing or misconfigured provider state callback.
3. Request method/path/header mismatch against controller mapping.
4. Status 200 vs. 404/401/500 mismatch against contract.
5. Response `Content-Type` differs from what the consumer expects.
6. Body missing `title`, wrong `id` type, or different serialization.
7. Test target points to wrong localhost port; server not ready.
8. Incompatible Pact version/spec/tooling.
9. Test state leaked between interactions.
10. Request blocked by security filters or authorization not configured.

**Never** edit the generated Pact file by hand to make the provider test PASS; it belongs to the consumer. The provider can fix its code/state if compatible, or negotiate contract changes with the consumer team.

## 20. Consumer contracts should be small, specific, and meaningful

An anti-pattern is copying the provider's **entire response JSON** into a Pact with every field, exact value, and array order even when the consumer only reads `title`.

For instance, suppose a provider response has:

~~~json
{
  "id": 42,
  "title": "Clean Code",
  "description": "...",
  "stock": 6,
  "warehouse": "HCM-01",
  "debugVersion": "abcdef",
  "timestamp": "2026-11-08T00:00:00Z"
}
~~~

If CheckoutWeb uses only `id` and `title`, the Pact should require only those fields and appropriate types/patterns; freezing `stock=6`, `debugVersion`, or `timestamp` breaks the provider build for no business reason.

### 20.1 Exact values vs. matchers

| Expectation | Appropriate matcher | Reason |
| --- | --- | --- |
| Specific URL to call | Exact method/path or intentional regex | Ensures consumer calls the right resource |
| JSON ID | `integerType("id",42L)` | Contract needs a number, not always 42 |
| JSON Title | `stringType("title","Clean Code")` | Consumer needs a string |
| Enum/status | Exact allowed value or regex where valid | Matches business branching |
| Timestamp | Datetime matcher if consumer parses format | Does not pin fixture timestamp value |
| Products array | Type matcher + minimum size if consumer needs it | Does not lock ordering/size needlessly |
| Optional field | Omit if consumer does not use it; test fallback if used | Avoids over-specification |

**Overly broad matchers are also dangerous.** If a client requires a UUID-formatted order ID yet the contract only asks for “any string”, the provider could return `"abc"` and break the client downstream. Expectations must match the actual invariants the consumer relies on.

### 20.2 Do not mistake mocks for reality

A mock server can satisfy a contract perfectly even before the provider implements the endpoint. Passing consumer tests lets the consumer team build features **early**, yet safe deployment still waits for provider verification and `can-i-deploy` in the target environment. Dropping the gate reduces CDC to “green mock tests”.

## 21. Independent evolution mechanism: expand, migrate, contract

Suppose the provider wants to rename `title` to `displayName`.

**Compatibility-breaking approach:**

~~~text
InventoryService v1 -> {"title":"Clean Code"}
InventoryService v2 -> {"displayName":"Clean Code"}
CheckoutWeb v1 still reads title -> broken
~~~

Safe approach:

1. **Expand:** Provider v2 returns both `title` and `displayName`. Old consumer Pacts still PASS.
2. **Migrate:** CheckoutWeb v2 updates code to read `displayName`, writes a new Pact, and provider verifies PASS. Deploy CheckoutWeb v2 and record deployment on the Broker.
3. **Observe:** Confirm no active consumer versions still depend on `title` (including mobile/partners/old branches as needed).
4. **Contract:** Provider v3 removes `title`; deploy only once `can-i-deploy` shows safety against remaining deployed versions.

~~~text
time --->
Provider v1: title
Provider v2: title + displayName   (both consumers work)
Consumer v2: uses displayName
Provider v3: displayName only      (remove after old consumers retire)
~~~

**Do not equate a semver MAJOR bump with guaranteed safety.** A v2 API with a breaking change can still break deployed consumers if routed to the same endpoint without preserving v1 semantics; Broker verification and `can-i-deploy` provide per-version evidence.

### 21.1 Typically compatible vs. incompatible changes

| Provider change | Compatibility outlook | Notes |
| --- | --- | --- |
| Add JSON field unused by consumer | Usually compatible | Strict consumer deserializers may differ; test for real |
| Keep field, change fixture value | Usually compatible if matchers allow | Must not break enums/business rules |
| Remove field in use | Breaking | Pact will fail if field is required |
| Rename path or HTTP method | Breaking | Old consumer requests fail |
| Change status 404 to 200 | Potentially breaking | Consumers branch on status |
| Change string to number | Breaking for typed JSON consumers | Matchers catch it |
| Tighten auth requiring new header | Potentially breaking | Old consumer contracts do not send header |
| Add required request field | Breaking for old consumers | Expand API to accept both old and new |
| Change field meaning while keeping type | Semantically breaking | Pact type matchers **do not catch this automatically** |
| Change sort/order/page defaults | Potentially breaking | Part of contract if consumer depends on order/pagination |

CDC is a contract over **interactions** and does not automatically safeguard deeper semantics such as balances, VAT, or pricing rules unless consumer tests assert them appropriately.

## 22. Pact Broker: source of truth for versions and verification

The local demo transfers Pacts through a build folder. In organizations, independent repos/teams should never hand-copy JSON via Slack or commit it into provider repos. Use a Pact Broker or equivalent service to track:

- Consumer participant/version/branch and Pact contents.
- Provider participant/version/branch and verification results.
- Deployment/release state transitions per environment.
- Matrix showing which consumer versions are compatible with which provider versions.
- `can-i-deploy` API/CLI gating against versions **currently in** the target environment.
- Webhooks triggering provider verification when a new contract is published.

Diagram:

~~~text
CheckoutWeb CI              Pact Broker                InventoryService CI
  |                             |                              |
  |--- publish pact (cSHA) ---->|                              |
  |                             |---- webhook new pact ------->|
  |                             |                              |
  |                             |<--- provider verification ---|
  |                             |     (pSHA, PASS/FAIL)         |
  |                             |                              |
  |--- can-i-deploy cSHA ------>|                              |
  |<-- YES / NO --------------- |                              |
  |--- deployment --------------|                              |
  |--- record-deployment ------>|                              |
  |                             |                              |
  |                             |<--- can-i-deploy pSHA --------|
  |                             |---- YES / NO ---------------->|
  |                             |<--- record provider deploy ---|
~~~

**Always publish verification results with the exact provider version.** If local provider tests use `@PactFolder` without a Broker source/link, the Broker never sees results even when JUnit PASSES. In CI, switch the test source to `@PactBroker`/selectors and configure result publishing.

## 23. Can I Deploy and the deployment matrix

Pact Broker provides a compatibility matrix by version.

Suppose production currently runs:

| Participant | Deployed | Relevant Pact/verification |
| --- | --- | --- |
| CheckoutWeb | `checkout-a1` | Needs `title` |
| BillingService | `billing-b7` | Needs `price` |
| InventoryService | `inventory-p9` | Verified both contracts |

The InventoryService team prepares `inventory-p10`. The provider pipeline must verify **Pacts of deployed consumers**; if p10 breaks CheckoutWeb a1, `can-i-deploy` must return NO even if provider unit tests are green.

This matrix is an **illustrative example**, not the live Broker state of any real system.

### 23.1 The can-i-deploy command

Example from CI with Pact Broker CLI and credentials passed via environment:

~~~bash
pact-broker can-i-deploy \
  --pacticipant InventoryService \
  --version "$CI_COMMIT_SHA" \
  --to-environment production
~~~

After a successful deployment:

~~~bash
pact-broker record-deployment \
  --pacticipant InventoryService \
  --version "$CI_COMMIT_SHA" \
  --environment production
~~~

For CheckoutWeb, substitute the participant name. Depending on PactFlow/OSS Broker and auth setup, the CLI may also require `--broker-base-url`/`--broker-token` or environment variables. **Never** hardcode tokens in source/READMEs or print them in CI logs.

### 23.2 Sequence of actions is a release contract

1. Build/test version `v`.
2. Publish Pacts or provider verification results tagged with `v`.
3. Wait for required verifications to be published.
4. Run `can-i-deploy` for the **exact `v`** and **target environment**.
5. Deploy only when it returns YES.
6. After successful deployment, invoke `record-deployment` so the Matrix reflects the latest running versions.

Skipping step 6 causes future deployments to compare against **stale versions** and make wrong decisions. Running `can-i-deploy` for `latest` instead of an immutable SHA risks gating the **wrong artifact** when a concurrent build arrives.

### 23.3 Never “fix” NO by switching environments

A provider candidate incompatible with a production consumer does not become compatible by running `can-i-deploy` against a different environment. On NO, inspect the specific Pact verification, restore backward compatibility, or coordinate a migration. Do not switch selectors to `main branch only` and drop active consumer versions just to make the pipeline green.

## 24. Pending Pacts and WIP Pacts

Two easily confused concepts:

**Pending Pact** is a dynamic property of Pact verification inside the provider pipeline. When a consumer publishes a new expectation the provider does not yet support, verification can **FAIL** without breaking the main provider build—preventing an undeployed consumer branch from blocking unrelated provider deployments.

**Work-in-progress (WIP) Pact** is a newly published Pact not yet accepted by the provider branch, automatically included in verification by the Broker when configured with appropriate WIP timestamps/selectors; it lets the provider see new expectations early without manual selector edits every time.

| Property | Pending | WIP |
| --- | --- | --- |
| What is it? | State of a Pact during verification | Selection rule adding in-development Pacts |
| Purpose | Keep provider main unblocked by unaccepted new expectations | Auto-verify new contracts |
| Is provider verification recorded as FAIL? | **Yes**, true outcome is still recorded | **Yes**, if actually incompatible |
| Can the new consumer deploy if verify FAILS? | **No**, `can-i-deploy` still requires compatibility | No |
| Does it replace `can-i-deploy`? | No | No |

### 24.1 Pending does not turn FAIL into PASS

If consumer v2 requires `availability` while provider v1 does not yet return it:

~~~text
Provider verifies new Pact:
    interaction FAILS
    Pact Broker records FAILED verification
    provider main build MAY remain green (pending policy)

CheckoutWeb v2:
    can-i-deploy -> NO until provider supports contract
~~~

This behavior is **intentional**, not a bug in pending pacts. The provider still needs to add the field; consumer v2 stays blocked from deploying until the target environment is compatible.

### 24.2 Configuration requires branch/version metadata

For pending/WIP to work properly:

- Consumers publish Pacts with **consumer version** and **branch**.
- Providers publish verifications with **provider version** and **branch**.
- Define the main branch for participants.
- Select deployed/released Pacts plus required main-branch Pacts.
- Enable pending and WIP per your Pact Broker feature/version.
- Do not confuse the provider-triggered verification webhook with the main provider pipeline: pending plays different roles across those two workflows.
- Always run `can-i-deploy` at the release gate regardless of whether the main provider build stayed green due to pending.

### 24.3 Never use “pending everything” to hide breaking changes

Once a provider has successfully verified a Pact for a deployed consumer, later breaking that Pact **is no longer an unaccepted new change**. The provider pipeline must catch and block breaking regressions. Pending exists to protect independent upgrade paths, **not to excuse regressions**.

## 25. Provider verification from the Broker in CI

The local demo uses:

~~~java
@Provider("InventoryService")
@PactFolder("../consumer/build/pacts")
~~~

In provider CI with independent repos, replace `@PactFolder` with a Pact Broker source, e.g., `@PactBroker` and selectors matching your Pact JVM version:

~~~java
@Provider("InventoryService")
@PactBroker
class InventoryBrokerVerificationTest {
    // @TestTemplate, @State, HttpTestTarget
    // Similar to InventoryProviderPactTest.
}
~~~

**This is an illustrative snippet, not a complete file in the mini-project.** Broker host/scheme/auth/selector settings must follow Pact JVM 4.6.x docs and your real pipeline. Do not arbitrarily combine `@PactFolder` and a Broker source on the same provider test; select the right source per environment.

Pact JVM provider JUnit 5 supports publishing verification results when system properties are set on the **test JVM**. Example Gradle provider config:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'pact.provider.version',
            System.getenv('CI_COMMIT_SHA') ?: 'local'

    systemProperty 'pact.provider.branch',
            System.getenv('CI_COMMIT_BRANCH') ?: 'local'

    systemProperty 'pact.verifier.publishResults',
            System.getenv('CI') == 'true'
                    ? 'true' : 'false'
}
~~~

This is a **CI template for Broker mode**, not a drop-in replacement for the local demo `build.gradle` while tests use `@PactFolder`. Many build tools run tests in a forked JVM; passing `-Dpact.provider.version` on the Gradle CLI **does not always propagate automatically into the test JVM**, so configure it on the `Test` task as shown.

For pending, WIP, provider version selectors, and Broker tokens, use the official Pact/CI configuration mechanisms. Never publish `local` results to a production Broker as if they were immutable deployable artifacts.

## 26. Typical independent pipelines

### 26.1 Consumer CI

~~~text
checkout feature branch
      |
      +-- compile + unit tests
      |
      +-- Pact consumer tests using MockServer
      |
      +-- publish immutable Pact (consumer SHA + branch)
      |
      +-- trigger provider verification via Broker webhook
      |
      +-- await required verification results / can-i-deploy
      |
      +-- deploy CheckoutWeb SHA
      |
      +-- record-deployment
~~~

Consumers do not wait for provider deployment to **write code and run unit/Pact mock tests**. However, the new consumer version **must not** enter an environment running a provider that fails its Pact.

### 26.2 Provider CI

~~~text
inventory feature branch
      |
      +-- unit/integration tests
      |
      +-- fetch relevant deployed/main/WIP pacts
      |
      +-- setup provider states and verify real HTTP endpoints
      |
      +-- publish verification result (provider SHA + branch)
      |
      +-- protect main with pending-pacts semantics
      |
      +-- can-i-deploy against target environment
      |
      +-- deploy InventoryService SHA
      |
      +-- record-deployment
~~~

The provider must verify **Pacts of every supported consumer version**, not just the latest Pact of one consumer.

### 26.3 When one team has multiple CI workflows

A team may run a provider-changed workflow, a consumer-pact-published webhook workflow, and a deployment workflow. Keep responsibilities clear:

- Webhook verification can FAIL on a brand-new contract, informing the consumer team the provider does not support it yet.
- The provider main branch build is protected by pending so an undeployed Pact does not turn main red.
- The deployment gate still evaluates the true matrix against the target environment.
- Verification reports must carry the exact provider version/branch.
- Never treat a missing verification result as PASS or assume no Pacts exist.

## 27. When multiple distinct consumers exist

CheckoutWeb reads `title`, BillingService reads `price`, and MobileApp reads `stock`. The provider wants to evolve its response. Pact Broker stores multiple Pact contents and versions.

Example:

| Deployed consumer | Required contract | Provider must retain |
| --- | --- | --- |
| CheckoutWeb a1 | GET /books/42 → id,title | id,title |
| BillingService b7 | GET /pricing/42 → currency,amount | currency,amount |
| MobileApp m3 | GET /books/42 → stock | stock |
| CheckoutWeb a2 (undeployed) | GET /books/42 → displayName | displayName before a2 deploys |

If InventoryService v2 adds `displayName` while keeping `title`, `stock`, and `price`, it can stay compatible with all of them. Before v3 deletes `title`, you must know whether a1 is still in production.

**Do not drop support for installed mobile clients merely because a newer version hit the app store.** For external clients, active versions can be hard to measure; combine telemetry, deprecation windows, API versioning, and consumer registration rather than watching only branch HEAD.

## 28. Negative contracts: errors are part of the API too

A CDC suite covering only HTTP 200 misses many breakages:

- Provider changes 404 to 200 with body `{"error":"not found"}`.
- Unauthorized request returns 500 instead of 401/403.
- Validation error changes JSON schema so consumer parsing fails.
- Rate-limit 429 omits `Retry-After` that the consumer relies on.
- Provider turns a timeout error into a 200 response with incomplete data.
- `Content-Type` header changes to XML when the client only speaks JSON.

### 28.1 When should you assert error bodies?

If the consumer displays messages based on a `code` field, that is a contract requirement:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "message": "Book does not exist"
}
~~~

If the consumer only checks status 404 to return `Optional.empty()`, pinning every word of `message` over-specifies the contract. Write assertions matching **how the consumer actually behaves**.

### 28.2 401/403/429 also need provider states

For example, `given("token missing")`, `given("user lacks permission")`, and `given("rate limit exceeded")` may need provider state handlers/token fixtures. **Never** hardcode production tokens, user passwords, or secrets in Pact files; use dummy/test credentials, a token injector, or a request modification hook appropriate to your provider verifier.

## 29. Security boundary: contract tests do not prove auth is secure

If a consumer test sends a dummy header:

~~~http
Authorization: Bearer test-token
~~~

and the Pact mock accepts it, that **does not** prove production JWTs verify signatures, issuers, audiences, or expiration. Provider verification can configure test authentication to pass filters, yet verifying **security** requires dedicated tests for:

- Authorized vs. unauthorized statuses.
- Role/scope/tenant authorization.
- Token parsing/verification on the real security filter chain.
- CSRF when using browser/session cookies.
- Secrets rotation and mTLS when required for service-to-service calls.
- Retries/circuit breakers never leaking tokens into logs.

**Never store real tokens in Pact JSON or the Broker.** If auth headers are short-lived, use a verifier hook to modify requests at test runtime per docs, clearly documenting what is contract vs. credential injection.

## 30. Contract testing is part of resilience, not a replacement for it

CDC verifies request/response **shape and selected semantics**, and does not prove the system stays healthy during:

- Network timeouts or DNS failures.
- Provider 500/503 under overload.
- Retries causing duplicate side effects.
- Circuit breaker OPEN/HALF_OPEN states.
- Out-of-order or duplicate events.
- Partial outages or zone failovers.
- Successful serialization carrying stale data.
- Database transaction rollbacks after a response was published.

| Concern | Additional test/control |
| --- | --- |
| HTTP connect/read timeouts | Client integration tests with faulting server/network proxy |
| Retry/backoff | Exact request count and retry condition tests |
| Idempotency | Duplicate request/payment/event tests |
| Circuit breaker | State transition + fallback tests |
| Authentication | Security integration tests |
| DB transactions | Repository/transaction integration |
| p99 latency/SLO | Load/performance tests |
| Provider availability | Probes/monitoring/failover |
| Async event delivery | Messaging integration + CDC message tests |

**A passing contract is a compatibility prerequisite, not an uptime guarantee.** In production, combine CDC with chaos testing, observability, bounded retries, and data consistency checks.

### 30.1 Especially for POST/commands

A consumer contract stating `POST /orders` returns 201 does not prove two retries will not create two orders. For commands with side effects, contracts should include idempotency keys/headers/statuses when consumers rely on them, paired with implementation tests verifying duplicate calls with the same key behave properly.

## 31. API changes and schema evolution in message/event-based systems

CDC is not limited to HTTP. In Kafka/RabbitMQ/event-driven integrations:

- **Producers** emit events/messages.
- **Consumers** receive and parse messages.
- Contracts describe message metadata, headers, and the body/fields consumers need.
- Provider verification checks that the producer can generate valid messages from a provider state.
- Schema Registry (Avro/Protobuf/JSON Schema) enforces schema compatibility across versions; CDC verifies concrete consumer usage.

Example event:

~~~json
{
  "eventType": "BookStockChanged",
  "version": 2,
  "bookId": 42,
  "available": true
}
~~~

If a consumer only needs `bookId` and `available`, Pact matchers can require just those fields and types. **Additional tests are still needed:**

- Is the event published within an appropriate transaction/outbox?
- Are duplicate/out-of-order events handled safely?
- Does the partition key preserve ordering when needed?
- Are retry/DLQ/poison-message policies accurate?
- Is the consumer idempotent on replay?

Pact JVM supports **asynchronous message interactions**; V4/message APIs differ from HTTP `RequestResponsePact`. **Do not copy the HTTP `@PactTestFor` sample directly for Kafka expecting it to run**; pick the appropriate message DSL/target/plugin, test handlers/producers at the right layer, and add broker integration tests.

## 32. Spring Cloud Contract: another option in the Spring ecosystem

Spring Cloud Contract (SCC) is a popular option when both provider and consumer live in the Spring stack.

Comparison:

| Need | Pact JVM + Broker | Spring Cloud Contract |
| --- | --- | --- |
| Consumers define interactions from live client code | Very well suited | Supports CDC workflow with contracts/stubs |
| Provider auto-verifies contracts | JUnit Pact verifier | Generated tests from contract DSL |
| Consumers use stubs without running provider | Pact MockServer | Stub Runner/WireMock-generated stubs |
| Version & deployment compatibility matrix | Built into Pact Broker | Requires workflow metadata/release-gate management |
| Multi-language consumers | Broad multi-SDK Pact ecosystem | Focused on Spring/JVM, with other language support |
| Async messages | Pact message interactions/plugins | SCC supports messaging contracts via integrations |
| Tests full service topology | No | No |

Example Spring Cloud Contract DSL:

~~~groovy
org.springframework.cloud.contract.spec.Contract.make {
    description("Read an existing book")
    request {
        method GET()
        url("/api/books/42")
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            title: "Clean Code"
        )
    }
}
~~~

This is an **SCC DSL illustration**, not a runnable file in the Pact mini-project. The SCC version must match your repo's Spring Boot/Spring Cloud BOM. Never mix Pact and SCC schemas without a clear source-of-truth strategy: maintaining separate contracts in two tools invites drift.

### 32.1 Which should a team pick?

If you need **cross-team, multi-repo, multi-language, and independent deployment gates** per consumer/provider version, the Pact Broker matrix offers a clear advantage. If your provider is a Spring app and you want contract DSLs + auto-generated provider tests + published consumer stubs, Spring Cloud Contract may fit well.

You do not need both for the same integration just because you can; one system with clear ownership, versioning, and CI feedback beats two conflicting contract suites.

## 33. Test pyramid: don't use contract tests for everything

~~~text
                Few E2E tests
             /------------------\
            /   End-to-end       \
           /----------------------\
          / Contract verification  \
         /--------------------------\
        / Component/integration      \
       /------------------------------\
      /  Many unit/service tests       \
     /----------------------------------\
~~~

Sensible division of labor:

- Unit: business rules, DTO parsing, fallbacks, mappings.
- Consumer Pact: real client requests + expected response handling.
- Provider Pact verification: real provider endpoints/states satisfying Pacts.
- Integration: databases, transactions, authentication, Redis, message brokers, and network-specific failures.
- End-to-end: a few customer journeys on real infrastructure, not every combination on every commit.
- Production monitoring: business metrics, traces, and canaries/rollbacks when assumptions shift.

Pact reduces the need for E2E tests across every service pair, **without eliminating E2E completely**. A valid contract can still hit broken service discovery, routing, or environment config in staging.

## 34. Independent-team scenarios and release decisions

### 34.1 Consumer wants a new field before the provider adds it

CheckoutWeb v2 writes a Pact requiring `displayName`, consumer tests PASS against the mock; provider v1 verification FAILS. The Broker records the failure, and consumer `can-i-deploy` returns NO. The provider team ships v2 adding the field. Once provider verification succeeds and v2 is deployed (in safe order), consumer v2 can ship.

### 34.2 Provider needs to swap databases

InventoryService migrates from Postgres to DynamoDB while keeping external responses (`id`/`title`/404) intact. Provider Pact verification PASSES; consumers need neither code edits nor synchronized deploys. Separate integration/data-migration tests are required, while CDC confirms the API contract holds.

### 34.3 Provider wants to remove an old field

The provider must not delete `title` merely because CheckoutWeb's main branch moved to `displayName`. You must know which **CheckoutWeb versions are currently deployed** and whether any other consumers still read the old field. Pact Broker deployment records and `can-i-deploy` inform this check.

### 34.4 Two consumers need different error schemas

CheckoutWeb only cares about status 404; MobileApp needs `code`. The provider can keep 404 and return `code`, staying compatible with both. Do not force CheckoutWeb to assert the exact error body if it does not use it.

### 34.5 Contract changes, yet provider test is not triggered

The consumer publishes a new Pact, yet webhooks are disabled or the provider selector is wrong; no verification result exists. `can-i-deploy` must treat missing/unknown status as **insufficient evidence**, never substituting “consumer unit tests PASS”.

## 35. Observing contract failures in CI and production

Useful signals:

| Signal | Why it matters |
| --- | --- |
| Consumer Pact version/branch | Identifies which build produced the expectation |
| Verified provider version/branch | Identifies which implementation ran verification |
| Pact verification PASS/FAIL | Blocks regressions on exact interactions |
| Pending/WIP labels | Separates new requests from accepted breakages |
| Broker matrix/`can-i-deploy` result | Gates deploys per environment |
| Deployment/release records | Prevents comparing against outdated versions |
| Interaction mismatch | Shows which path/method/header/status/body failed |
| Provider state failure | Shows which fixture failed setup |
| CI webhook lag | Provider has not verified yet due to queued jobs |
| Contract coverage | Which consumers/endpoints have or lack Pacts |
| Runtime error rate by integration | Catches semantic/timing issues outside Pact |
| Correlation IDs/traces | Follows live calls across services |

Never publish secrets or customer PII into Pact examples. Use synthetic values and cleanup/test data. In ephemeral test environments, namespace provider state fixtures by build ID to prevent races.

### 35.1 Quick triage when provider verification fails

1. Confirm exact consumer/provider participant names.
2. Confirm Pact content version and consumer branch/deployment selectors.
3. Read the interaction description and provider state.
4. Check that the provider state callback sets up data deterministically, independent of order.
5. Check status codes and `Accept`/`Content-Type` headers.
6. Check JSON fields, types, regexes, and array cardinality.
7. Check the provider service runs on the right port and HTTP layer.
8. Check security filters if 401/403 are not covered in the Pact.
9. Check matcher over-specification vs. real client requirements.
10. Update contracts only for real consumer code needs, never just to force “green”.

## 36. Common mistakes

**1. Treating a passing consumer mock test as proof the provider is compatible.**  
Wrong: provider verification on the real implementation is mandatory.

**2. Having the provider write Pacts instead of the consumer.**  
Loses consumer-driven feedback. Contracts must originate from consumer code/tests.

**3. Consumer tests bypassing the production client.**  
Hand-crafted HTTP requests can diverge from what the live app sends.

**4. Pact tests checking only 200.**  
404/401/403/429 and validation/error paths can also be breaking.

**5. Locking every field and value in JSON responses.**  
Over-specification prevents the provider from evolving independently.

**6. Using matchers so broad they miss business invariants.**  
`stringType` does not enforce UUID/enum/currency formats; choose the right matching rule.

**7. Sharing a DTO JAR between provider and consumer.**  
Simultaneous compilation hides incompatibilities across differently deployed versions.

**8. Provider state callbacks not resetting fixtures.**  
Verification becomes order-dependent and flaky.

**9. Provider test pointing to the wrong port.**  
`RANDOM_PORT` must be passed into `HttpTestTarget`, never hardcoding 8080.

**10. Test passing when no Pact is found.**  
Never suppress no-Pact verification failures when contracts are required.

**11. Provider tests mocking all business logic via MockMvc.**  
Can miss real wiring, security, and integration; choose the right verification layer and supplement with integration tests.

**12. Failing to publish provider verification results.**  
The Broker has no compatibility record even if local JUnit PASSES.

**13. Omitting provider version/branch.**  
The Broker cannot compute pending/matrix properly, leaving `can-i-deploy` without evidence.

**14. Skipping `record-deployment` after deploy.**  
The Broker compares against stale versions, invalidating release gates.

**15. Using `latest` Pacts without version pinning.**  
CI can verify different content than the deployed artifact.

**16. Verifying only the consumer's main-branch Pact.**  
Misses older consumer versions still running in production.

**17. Mistaking a pending Pact for successful verification.**  
FAILED is still FAILED; the consumer remains blocked by `can-i-deploy`.

**18. Letting WIP Pacts block provider main because pending is disabled.**  
An unready contract can stall unrelated provider releases.

**19. Removing compatibility as soon as consumer main changes.**  
Older deployed versions still rely on the old API.

**20. Confusing Pact Broker with a source code registry.**  
The Broker stores Pact versions, verifications, and deployment matrices, not Git/CI artifacts.

**21. Skipping auth/security tests because Pact runs a mock server.**  
Mocks do not verify real signatures or authorization.

**22. Assuming Pact guarantees retries/idempotency.**  
Contract shapes do not replace network and resilience tests.

**23. Sharing a production database to create provider states.**  
Dangerous and non-deterministic; use isolated test data.

**24. Failing to test extra fields/strict clients.**  
A consumer configured to reject unknown properties can fail when the provider adds a field; test real client behavior.

**25. Changing error semantics while keeping the schema.**  
Status 404 vs. 200-with-error can break clients even when JSON is “valid”.

**26. Ignoring message ordering and duplication.**  
Message contracts do not replace queue integration/idempotency tests.

**27. Deleting Pact files of deployed versions.**  
The provider loses visibility into compatibility with older live clients.

**28. Merging contract and code into an unconditional single release train.**  
Loses independent deployment benefits; coordinate via publish/verify/gate.

## 37. Step-by-step CDC implementation workflow

1. Pick a key integration across two teams/repos: e.g., CheckoutWeb → InventoryService.
2. Identify the exact endpoints, statuses, headers, and fields the consumer truly uses.
3. Write separate consumer unit tests for mapping and fallbacks.
4. Write Pact consumer tests calling the real HTTP client against Pact MockServer.
5. Generate the Pact artifact, inspect interactions, and strip out over-specification.
6. Publish the Pact with an immutable consumer version SHA and branch.
7. Register the Pact source and proper `@State` fixture handlers on the provider.
8. Run provider verification against the real endpoint or appropriate layer; publish results with provider version/branch.
9. Enable the Broker matrix and `can-i-deploy` before every deployment.
10. Call `record-deployment` after each successful deployment.
11. Enable webhooks so Pact updates trigger provider verification.
12. Configure pending/WIP semantics properly so unsupported future features do not block the provider.
13. Keep selectors covering deployed/released consumer versions, not just `latest`.
14. Roll out breaking API changes via expand–migrate–contract, avoiding forced simultaneous deploys.
15. On the provider side, maintain OpenAPI specs and docs alongside CDC.
16. Add security, DB, messaging, retry, and fault-injection tests for everything Pact does not cover.
17. Review production logs/metrics and deprecation windows before deleting old fields.
18. Monitor Pact Broker gate failures, missing results, webhook reliability, and build promotions.
19. Keep examples synthetic, avoiding tokens/secrets/PII in Pact artifacts.
20. Cover negative cases (404/401/403/429) per consumer behavior.
21. Define clear ownership/versioning and review contract changes like code changes.
22. Test provider compatibility against all active consumer versions in the target environment.

### Checklist before enabling the deploy gate

- [ ] Consumer tests call the real client, not hand-written requests.
- [ ] Pact files are generated from tests and versioned by SHA/branch.
- [ ] Provider and consumer names match identically on both sides.
- [ ] Provider states are deterministic and test data never touches production.
- [ ] Provider verification truly replays interactions against the real implementation.
- [ ] “No pacts to verify” is NOT suppressed.
- [ ] Matchers are neither overly broad nor overly strict.
- [ ] Both success and key error semantics are covered.
- [ ] Broker receives Pacts and verification results with accurate versions.
- [ ] Pending/WIP are configured and understood accurately.
- [ ] `can-i-deploy` runs for the exact artifact and environment before deployment.
- [ ] `record-deployment` is called after every successful deployment.
- [ ] Provider selectors cover deployed consumers.
- [ ] Compatibility/rollout follows expand–migrate–contract.
- [ ] Security, timeouts, retries, and idempotency still have independent tests.
- [ ] No secrets or real customer data are stored in Pacts.
- [ ] CI failures trigger clear remediation rather than arbitrary gate overrides.

## 38. Conclusion

**Consumer-driven contracts let teams develop independently while guaranteeing they do not break communication across deployed versions.**

For HTTP:

- Consumers generate Pacts using their real client/adapter and verify behavior on a mock server.
- Providers replay Pacts against the real service, setting up provider states so every interaction is deterministic.
- Pact Broker tracks versions, branches, the verification matrix, and deployments.
- `can-i-deploy` determines whether sufficient compatibility evidence exists for the target environment.
- Pending/WIP help teams move fast without hiding FAILED outcomes.
- Expand–migrate–contract evolves APIs without forcing simultaneous deployments.

**Do not treat contract tests as all of testing.** They verify communication boundaries, not database correctness, runtime availability, load, network resilience, auth, or all business invariants. Pair Pact/Spring Cloud Contract with integration, security, fault tests, and observability to keep release velocity high without breaking downstream services as they evolve.

### Official references

- [Pact JVM — Consumer JUnit 5](https://docs.pact.io/implementation_guides/jvm/consumer/junit5): `@PactConsumerTest`, `@PactTestFor`, `MockServer`, Pact DSL.
- [Pact JVM — Provider JUnit 5](https://docs.pact.io/implementation_guides/jvm/provider/junit5): `@Provider`, `@TestTemplate`, `HttpTestTarget`, result publishing.
- [Pact JVM — Spring6/Spring Boot3](https://docs.pact.io/implementation_guides/jvm/provider/spring6): Pact verification with Spring 6/Boot 3.
- [Pact JVM — Provider State Setup](https://docs.pact.io/implementation_guides/jvm/provider/junit): `@State` handlers and Pact sources.
- [Pact Broker — Can I Deploy](https://docs.pact.io/pact_broker/can_i_deploy): Matrix, `can-i-deploy`, and `record-deployment`.
- [Pact Broker — Pending Pacts](https://docs.pact.io/pact_broker/advanced_topics/pending_pacts): pending verification semantics.
- [Pact Broker — Work In Progress Pacts](https://docs.pact.io/pact_broker/advanced_topics/wip_pacts): WIP inclusion and pending relationship.
- [Pact JVM — JDK/Specification Support](https://docs.pact.io/implementation_guides/jvm/readme): compatibility and artifact coordinates.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `SpringBootTest`, `RANDOM_PORT`.
- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/): contracts DSL, verifier, stub runner.
