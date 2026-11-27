# Testing APIs with WebTestClient and a Real Database

An API built with Spring WebFlux and Spring Data Relational R2DBC should be tested across both boundaries: HTTP and the database. Tests that invoke only the controller with a fake service can verify status codes, JSON, and request handling, but they do not prove that SQL, mapping, constraints, transactions, or the R2DBC driver work properly. Conversely, testing repositories directly can prove persistence, yet it does not verify that the API returns the right status, headers, body, or protects endpoints properly.

**WebTestClient** sends HTTP requests and asserts responses in reactive Spring tests. Combined with a real database, such as PostgreSQL or Oracle running in a dedicated test environment, you can exercise the entire flow:

~~~text
Test
 |
 | HTTP request
 v
WebTestClient
 |
 v
WebFlux server / Security filters
 |
 v
Controller
 |
 v
Service / reactive transaction
 |
 v
Spring Data repository / DatabaseClient
 |
 v
R2DBC driver
 |
 v
Real database
 |
 v
HTTP response
 |
 v
Assertions on status, headers, JSON, and persisted data
~~~

This lesson covers choosing a WebTestClient mode, launching the application with a real database via Testcontainers, loading schemas and fixtures, verifying requests/responses alongside persistence state, testing security and transactions, handling reactive streams, cleanup, and running tests reliably in CI.

## 1. Distinguishing Types of API Tests

Not every test using WebTestClient runs the full application or hits a real database. Pick the right scope.

| Testing approach | Scope | When appropriate |
|---|---|---|
| Calling controller directly | Controller method, no HTTP stack | Unit testing simple orchestration logic |
| WebTestClient.bindToController | Controller and part of WebFlux test infrastructure | Testing routing/serialization with fake dependencies |
| WebTestClient.bindToRouterFunction | Functional endpoints | Testing router functions |
| WebTestClient.bindToApplicationContext | Handlers, filters, and context beans via mock server | Integration testing within context; can connect to real database |
| WebTestClient.bindToServer | Sends HTTP to a running server | Testing HTTP over the network |
| @WebFluxTest | Slice focused on WebFlux/controllers | Verifying API contracts with mocked services |
| @SpringBootTest with RANDOM_PORT | Full application context and real web server on random port | End-to-end integration tests with a real database |

When the goal is testing an API together with a real R2DBC database, **@SpringBootTest(webEnvironment = RANDOM_PORT)** paired with **WebTestClient** and a dedicated database is usually the best fit. This starts a real server and sends HTTP requests to it.

**@WebFluxTest** normally loads only the web slice and selected dependencies. It works well for controller tests, but does not automatically verify that repositories and a real database are configured properly. You can import persistence components, though once scope includes both the application and database, a full application integration test is usually clearer.

## 2. How Does WebTestClient Work?

WebTestClient offers a fluent API to construct requests and declare assertions:

~~~java
webTestClient.get()
        .uri("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
            .jsonPath("$.id").isEqualTo(42);
~~~

Steps:

1. Select an HTTP method such as GET, POST, PUT, PATCH, or DELETE.
2. Specify the URI and query parameters.
3. Set headers, cookies, or authentication.
4. Send a request body if needed.
5. Call **exchange()** to execute the request.
6. Verify status, headers, and body.

WebTestClient can target either a mock server or a real server. The assertion API looks nearly identical, while the scope of the system exercised differs.

### 2.1. bindToController

Example:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new CustomerController(customerService))
        .build();
~~~

This fits when services are mocked or supplied as test doubles. It does not start the full application context, security filter chain, R2DBC connection factory, or database.

### 2.2. bindToApplicationContext

Example:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
~~~

This uses beans from the context with mock web server infrastructure. If the application context configures repositories and connects to a real test database, requests can hit real persistence without opening a network socket on a random port.

It is a useful integration test for handlers/filters and context wiring, though it does not test every detail of the embedded server or networking.

### 2.3. bindToServer

Example:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

The client sends requests to an already running server. The test must manage server lifecycle and base URL itself.

In Spring Boot integration tests, let Spring launch the server on a random port and inject WebTestClient instead of hard-coding fixed ports.

## 3. Dependencies for Integration Tests

For a Spring Boot WebFlux and R2DBC application, tests typically need:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")

    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    // Add only if the application uses Spring Security.
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Versions should be managed by Spring Boot dependency management/BOM and a compatible Testcontainers version. This example uses PostgreSQL; if production uses Oracle, SQL Server, or another engine, swap in the matching driver and container/test environment for your target database.

Spring Boot starter test typically includes JUnit Jupiter, AssertJ, and Spring testing utilities. WebTestClient is configured via Spring Boot/WebFlux test infrastructure.

Do not add a JDBC driver solely to run R2DBC tests unless the project uses a migration tool or other task requiring JDBC. If using traditional Flyway, configure a separate JDBC connection for migrations while runtime repositories keep using R2DBC.

## 4. Starting a Real Database with Testcontainers

Testcontainers runs a database in a container and supplies dynamic host/port coordinates. Tests use the real database engine rather than relying on mocks or an embedded database with differing SQL semantics.

PostgreSQL example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
class CustomerApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + database.getHost()
                        + ":"
                        + database.getMappedPort(5432)
                        + "/"
                        + database.getDatabaseName());

        registry.add("spring.r2dbc.username", database::getUsername);
        registry.add("spring.r2dbc.password", database::getPassword);
    }

    @Autowired
    WebTestClient webTestClient;
}
~~~

Key points:

- The container starts before Spring builds the application context.
- **@DynamicPropertySource** registers the container's live R2DBC URL and credentials.
- **RANDOM_PORT** avoids port conflicts when multiple test suites run on the same host.
- **WebTestClient** is injected and sends requests to the running Spring Boot server.
- Tests do not need to know assigned ports before the container/server starts.

The image tag in the example illustrates a major version. In CI, pick a pinned tag or digest so one run does not pull a different image than the last. If the application uses another database, run the engine and version compatible with production.

### 4.1. When Not Using Testcontainers

You can run a dedicated external test database outside containers, such as a CI instance or an ephemeral database provisioned by the pipeline. In that case, supply:

- R2DBC URL.
- Test-dedicated username/password.
- Test database/schema.
- TLS configuration if required.
- Migration/schema initializer.

Never point tests at a shared development or production database. A profile name alone does not ensure safety; verify the URL and database user permissions.

### 4.2. Testing Oracle or Databases with Special Requirements

For Oracle, SQL Server, or databases requiring licensed images, use vendor-supported container images and configurations or a dedicated test instance. Never assume every database has a freely usable public image.

Whether using containers or a test service, the goal is running the right engine, the right R2DBC driver, and a version close to production. H2 compatibility modes do not substitute for this.

## 5. Configuring Schemas and Migrations

A fresh database container initially has no tables. The application must create the schema before tests send requests.

Two common options:

1. Run the project's migrations, such as Flyway or Liquibase.
2. Use SQL initialization for small tests or exercises.

If using Spring Boot SQL initialization for R2DBC, the test profile can specify scripts:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/test-schema.sql
      data-locations: classpath:db/test-data.sql
      continue-on-error: false
~~~

Verify exact property names and initialization ordering for your Spring Boot version. Never allow scripts with DROP/TRUNCATE to run in default or production profiles.

In real projects, prefer running the same migrations used during deployment. That lets tests catch broken migrations, missing indexes, constraints, or column types differing from the expected schema.

### 5.1. Flyway/Liquibase May Use JDBC While the Application Uses R2DBC

Traditional Flyway manages migrations over JDBC. When doing so, tests may need both configurations pointing to the same database:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
    String host = database.getHost();
    Integer port = database.getMappedPort(5432);
    String name = database.getDatabaseName();

    registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + host + ":" + port + "/" + name);
    registry.add("spring.r2dbc.username", database::getUsername);
    registry.add("spring.r2dbc.password", database::getPassword);

    registry.add("spring.datasource.url",
            () -> "jdbc:postgresql://" + host + ":" + port + "/" + name);
    registry.add("spring.datasource.username", database::getUsername);
    registry.add("spring.datasource.password", database::getPassword);
}
~~~

JDBC configuration is needed only if the migration tool uses it and tests include the corresponding JDBC driver. Do not assign a JDBC URL to the R2DBC property or assume Flyway automatically uses R2DBC simply because the app uses R2DBC.

### 5.2. Verifying Migrations Before API Tests

An API test should not silently create minimal tables differing from the production schema. Let migrations create the schema and then test the behaviors that matter:

- Valid inserts.
- Unique constraints.
- Foreign keys.
- Not-null/check constraints.
- Indexes and query plans if testing performance.
- Data types and converters.

If migrations fail, the application context should fail fast so errors surface immediately at test startup.

## 6. Sending Requests and Verifying Responses

Example customer creation API accepting JSON and returning status 201:

~~~java
@Test
void createsCustomerThroughHttp() {
    CreateCustomerRequest request =
            new CreateCustomerRequest(
                    "api-test@example.test",
                    "API Test Customer");

    webTestClient.post()
            .uri("/api/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").exists()
                .jsonPath("$.email")
                    .isEqualTo("api-test@example.test");
}
~~~

This test verifies:

- The route accepts POST.
- JSON request deserializes.
- Content type and response format match expectations.
- The API returns status 201.
- The body contains the expected ID and email.

Asserting only the response, however, does not prove data was saved accurately. Verify database state in the next step.

### 6.1. Extracting the Response Body to Use the Database-Generated ID

Example response DTO as a record:

~~~java
public record CustomerResponse(
        Long id,
        String email,
        String fullName) {
}
~~~

The test can extract the result:

~~~java
@Test
void createsAndPersistsCustomer() {
    CreateCustomerRequest request =
            new CreateCustomerRequest(
                    "persisted@example.test",
                    "Persisted Customer");

    EntityExchangeResult<CustomerResponse> result =
            webTestClient.post()
                    .uri("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(request)
                    .exchange()
                    .expectStatus().isCreated()
                    .expectBody(CustomerResponse.class)
                    .returnResult();

    CustomerResponse response = result.getResponseBody();

    assertThat(response).isNotNull();
    assertThat(response.id()).isNotNull();
    assertThat(response.email())
            .isEqualTo("persisted@example.test");

    StepVerifier.create(customerRepository.findById(response.id()))
            .assertNext(saved -> {
                assertThat(saved.getEmail())
                        .isEqualTo("persisted@example.test");
                assertThat(saved.getFullName())
                        .isEqualTo("Persisted Customer");
            })
            .verifyComplete();
}
~~~

This example assumes the repository is injected and DTOs/entities match the application. **The ID taken from the response** is the ID returned by the database; never guess the ID as 1 or query SELECT MAX(id).

The test calls the API over HTTP and then reads the repository in a separate subscription. For a standard request-response endpoint, the response is returned only after the service publisher completes; if the service transaction committed before completing, the subsequent query will see the persisted data.

### 6.2. Verifying Response JSON More Precisely

You can use JSONPath:

~~~java
webTestClient.get()
        .uri("/api/customers/{id}", customerId)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(customerId)
        .jsonPath("$.email").isEqualTo("persisted@example.test")
        .jsonPath("$.fullName").isEqualTo("Persisted Customer");
~~~

Assert against the API's public contract. Avoid asserting internal entity fields that the API does not guarantee to expose.

## 7. Verifying Stored Data with Repositories or DatabaseClient

The goal of integration tests is verifying both HTTP responses and actual stored data. You can use:

- Repositories to verify entity state and mapping.
- DatabaseClient to run specific SQL queries.
- Another GET endpoint to confirm clients can read the resource back.

Repository example:

~~~java
StepVerifier.create(customerRepository.findByEmail("persisted@example.test"))
        .assertNext(customer -> {
            assertThat(customer.getId()).isNotNull();
            assertThat(customer.getFullName())
                    .isEqualTo("Persisted Customer");
        })
        .verifyComplete();
~~~

DatabaseClient example:

~~~java
StepVerifier.create(
        databaseClient.sql("""
                SELECT COUNT(*) AS total
                FROM customer
                WHERE email = :email
                """)
                .bind("email", "persisted@example.test")
                .map((row, metadata) ->
                        row.get("total", Long.class))
                .one())
        .expectNext(1L)
        .verifyComplete();
~~~

The return type of COUNT depends on the database/driver; you may need to map to Number/BigInteger or a dialect-appropriate type. Adjust examples to match your real driver.

Use repositories to verify entity mapping. Use direct SQL when checking constraints, column values, or database behaviors not exposed by repository abstractions.

## 8. Testing GET, Not Found, and Lists

Successful GET test:

~~~java
@Test
void readsCustomerById() {
    Customer saved = customerRepository.save(
            CustomerFixtures.defaultCustomer())
            .block(Duration.ofSeconds(5));

    assertThat(saved).isNotNull();

    webTestClient.get()
            .uri("/api/customers/{id}", saved.getId())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(saved.getId())
            .jsonPath("$.email")
                .isEqualTo(saved.getEmail());
}
~~~

Using **block()** during test setup is acceptable when confined to the test boundary and given a timeout. Never put blocking calls inside reactive application services or controllers.

Not-found test:

~~~java
webTestClient.get()
        .uri("/api/customers/{id}", 999999999L)
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code").isEqualTo("CUSTOMER_NOT_FOUND");
~~~

List tests should verify query parameters and ordering:

~~~java
webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/customers")
                .queryParam("page", 0)
                .queryParam("size", 10)
                .queryParam("sort", "email,asc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.content").isArray()
        .jsonPath("$.page.totalElements").isEqualTo(2);
~~~

JSON field names and page structure depend on your application's response DTOs. Use a stable sort key, typically adding ID as a tie-breaker when multiple rows share values.

## 9. Testing Validation and Database Constraints

API validation and database constraints are two separate lines of defense.

For example, a request missing an email may be rejected by Bean Validation before reaching the database:

~~~java
webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
                {
                  "email": "",
                  "fullName": "No Email"
                }
                """)
        .exchange()
        .expectStatus().isBadRequest();
~~~

Unique constraint tests should send two requests with the same email:

~~~java
CreateCustomerRequest request =
        new CreateCustomerRequest(
                "duplicate@example.test",
                "Duplicate");

webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isCreated();

webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.CONFLICT);
~~~

This test proves the database constraint and exception mapping work if the API translates duplicate errors to 409. Results depend on the application's exception translator and handlers; if your API follows a different contract, assert according to the defined contract.

Do not test only service-level existence checks before inserting. Two concurrent requests can both pass an existence check. A database unique constraint is the final safeguard.

## 10. Testing Errors and Transaction Rollback Over HTTP

An API may perform multiple operations in a single transaction, such as creating an order and its line items. If the second step fails, the transaction must roll back per business contract.

Tests should:

1. Prepare valid fixtures.
2. Send a request triggering a failure at a step after the first step has written.
3. Verify the HTTP status/error body.
4. Query the database to confirm no partial data exists.
5. If audit/outbox tables exist, verify their state matches design.

Illustrative example:

~~~java
@Test
void rollsBackOrderWhenLineInsertFails() {
    CreateOrderRequest request =
            OrderFixtures.requestWithInvalidLine();

    webTestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isBadRequest();

    StepVerifier.create(orderRepository
                    .findByOrderNumber(request.orderNumber()))
            .verifyComplete();
}
~~~

This example assumes the failure maps to 400 and the repository returns empty when no order exists. If the error is a technical constraint violation mapped to conflict or server error, adjust the expected status to match the API contract.

### 10.1. Why Doesn't @Transactional on the Test Automatically Roll Back HTTP Requests?

When a test sends a request via WebTestClient to a running server, the server processes the request in its own subscription and reactive context. The service transaction starts and finishes along the server's execution flow.

A transaction attached to the test method does not automatically wrap the HTTP request's transaction. The test client and server request are two separate execution contexts; running inside the same JVM does not propagate Reactor Context or connection transactions across an HTTP boundary.

Therefore, do not rely on **@Transactional** on the test class to roll back work performed by the API automatically. Data may have committed and requires explicit cleanup.

### 10.2. Service vs. HTTP Rollback Tests Serve Different Purposes

- Service/repository transaction tests verify transaction semantics directly.
- API integration tests verify the right error response is returned and the database holds no half-written state.
- Both have value, and neither fully replaces the other.

If an endpoint returns 202 Accepted and processes work asynchronously after the response, tests must await final state with eventual assertions or a job status API. Never assume a 202 response means database work has completed.

## 11. Preparing and Cleaning Up Fixtures Reactively

Fixtures can be inserted through repositories or DatabaseClient before calling the API:

~~~java
@BeforeEach
void resetDatabase() {
    databaseClient.sql("DELETE FROM purchase_order_item")
            .then()
            .then(databaseClient.sql("DELETE FROM purchase_order").then())
            .then(databaseClient.sql("DELETE FROM customer").then())
            .block(Duration.ofSeconds(10));
}
~~~

This example deletes child tables before parent tables. Adjust SQL to match your real schema; in PostgreSQL you can use TRUNCATE/RESTART IDENTITY CASCADE on a dedicated test database, never on a shared database.

Synchronous JUnit lifecycle methods do not automatically subscribe to or await a Mono simply because a method returns a publisher. You must explicitly wait for cleanup to complete, such as calling .block(timeout) at the test boundary as shown above, or using a lifecycle extension with reactive support.

### 11.1. Using Distinct IDs or Namespaces per Test

If multiple tests share a database, fixtures with fixed unique keys such as fixed emails can collide. Use UUIDs or test namespaces:

~~~java
String email = "it-" + UUID.randomUUID() + "@example.test";
~~~

Retain this value in the test to query and clean up the right row. Never generate random data for fields compared against fixed expectations unless you retain the generated value.

### 11.2. Cleaning Up in Foreign Key Order

If a test creates a customer, then an order, then order items, cleanup typically runs in reverse order:

~~~text
DELETE order_item
       |
       v
DELETE purchase_order
       |
       v
DELETE customer
~~~

Use cascade only when allowed by schema semantics. Cleanup must complete before the next test reuses the database.

## 12. Testing Security Filters and Authentication

If the API uses Spring Security WebFlux, tests should verify both permitted and rejected endpoints.

With security test support, you can inject mock authentication into WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk();
~~~

For POST endpoints using CSRF protection in session-based security, you may also need a CSRF token:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isCreated();
~~~

Exact setup depends on the security filter chain. Many bearer-token APIs do not enable CSRF the same way session/cookie apps do.

Tests should cover:

- Unauthenticated requests.
- Authenticated users lacking required roles.
- Users with appropriate roles.
- Expired or invalid tokens if testing real token validation.
- Missing/present CSRF tokens when CSRF is enabled.
- Tenant or resource-owner authorization.
- Request auditor when auditing reads from SecurityContext.

### 12.1. Mock Authentication Differs from Real Token Verification

**mockUser()** or **mockJwt()** injects a security context for tests; they are great for testing authorization and controller behavior. They do not prove JWT signatures, issuers, audiences, key rotation, or identity providers work properly.

When you need end-to-end token verification, sign test tokens with a test key and configure the matching decoder, or test against an identity provider in an integration environment. Never use production tokens in tests.

If auditing expects a custom principal carrying a user ID, supply a principal matching your application's type. **mockUser("alice")** usually supplies a default UserDetails principal, which does not automatically become a custom principal holding a database ID.

## 13. Verifying Auditors and Audit Data

If entities carry **@CreatedBy**, **@LastModifiedBy**, **@CreatedDate**, and **@LastModifiedDate**, API tests can confirm the security context propagates to ReactiveAuditorAware and audit metadata is saved.

A scenario:

1. Send POST as user A.
2. Capture the returned entity ID.
3. Read the database and verify createdBy is A.
4. Send PATCH as user B.
5. Read back and verify createdBy remains A and lastModifiedBy is B.
6. Verify timestamps update appropriately.

Do not inspect only the response if auditors are populated by persistence callbacks. Read the entity or columns from the database to prove auditing ran along the real write path.

## 14. Testing Pagination, Sorting, and Filtering

List APIs commonly connect query parameters to Spring Data repositories. Testing against a real database verifies SQL dialects and sort mappings.

Fixtures should include:

- Rows matching the filter status.
- Rows not matching the filter.
- Two rows sharing the same timestamp to test tie-breakers.
- Enough rows to span at least two pages.

Example:

~~~java
webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/orders")
                .queryParam("status", "OPEN")
                .queryParam("page", 0)
                .queryParam("size", 2)
                .queryParam("sort", "createdAt,desc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.content.length()").isEqualTo(2)
        .jsonPath("$.totalElements").isEqualTo(3);
~~~

Request the next page as well and verify no duplicate or missing rows per contract. When the database can produce equal sort values, add ID as a tie-breaker for deterministic ordering.

## 15. Testing Streaming Endpoints and Flux Responses

WebTestClient supports reading streaming responses. With Server-Sent Events:

~~~java
FluxExchangeResult<OrderEvent> result =
        webTestClient.get()
                .uri("/api/orders/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(OrderEvent.class);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                event.type().equals("ORDER_CREATED"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Use **StepVerifier** to verify emitted items, completion, errors, and cancellation. If a stream is infinite, tests must apply a finite timeout and cancel the subscription explicitly.

When testing streams reading from a database:

- Check how long connections stay held.
- Check whether cancelling the stream releases resources.
- Avoid buffering large datasets in memory when streaming is the goal.
- Test errors occurring after part of the response has already been sent.
- Do not assume clients receive a complete JSON array if the endpoint is a stream.

For endpoints returning Flux<T> as a JSON array, the server encodes responses per codec settings. When inspecting items individually or testing backpressure, use returnResult instead of reading the entire body at once.

## 16. Timeouts and Asynchronous Tests

WebTestClient has a response timeout. You can configure the client:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .responseTimeout(Duration.ofSeconds(5))
        .baseUrl(baseUrl)
        .build();
~~~

In Spring Boot tests, you can configure the injected client or apply test framework timeouts according to your version's API.

Do not raise timeouts hugely just to hide slow queries. Identify what the test is waiting for:

- Server startup.
- Connection pool acquiring a connection.
- Migrations running.
- SQL queries.
- Background jobs.
- Stream event emissions.
- External services.

If an endpoint returns 202 and processes asynchronously, poll with a conditional timeout rather than using fixed Thread.sleep calls. Assert that the target business state was reached, not merely that time elapsed.

## 17. Testing Concurrency and Data Integrity

Some bugs only surface when multiple requests run concurrently:

- Two requests registering the same email.
- Two requests updating the same @Version entity.
- Two workers claiming the same job.
- Two requests decrementing inventory simultaneously.
- Connection pool exhaustion.
- Lock timeouts or deadlocks.

WebTestClient uses a fluent test API; when firing many concurrent reactive HTTP requests, you can use **WebClient** targeting the test server's port:

~~~java
Flux.range(0, 10)
        .flatMap(index ->
                webClient.post()
                        .uri("/api/reservations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(requestFor(index))
                        .retrieve()
                        .toBodilessEntity(),
                10)
        .collectList()
        .block(Duration.ofSeconds(20));
~~~

This is an illustrative concurrency test snippet. After all requests finish, query the database to verify invariants—for example, total reservations do not exceed stock, or only one unique record exists.

Do not assert only that every request returned 200. Under contention, returning 409/423 or another defined status can be the right answer for losing requests. What matters is that final database state never violates invariants.

## 18. Do Not Use H2 as Proof for the Production Database

H2 can be convenient for fast tests, but cannot replace a real database when the application depends on:

- Specific dialects and SQL syntax.
- Sequences/identities and generated keys.
- JSON, arrays, enums, and LOBs.
- Precision and timezones.
- Isolation levels and locking.
- DDL transaction semantics.
- Error codes and exception translation.
- Indexes, collations, and execution plans.

If production uses PostgreSQL, run integration tests against PostgreSQL. If using Oracle, test Oracle. If using SQL Server, test SQL Server. Compatibility modes only emulate partial syntax; they do not turn one engine into another.

You can keep H2 for some unit/in-memory tests, but do not use those results to claim production database persistence compatibility.

## 19. Running Tests Safely in Parallel

A static container can be shared across test methods in the same class. If multiple classes share one database, you need an explicit strategy.

Isolation options:

- One database/container per test class.
- A dedicated schema per test suite.
- Separate data namespaces per test.
- Cleanup by fixture ID.
- Disabling parallel execution for tests truncating shared tables.
- Dedicated containers/databases for destructive test groups.

Never run whole-database TRUNCATE in @BeforeEach if other tests could be reading or writing simultaneously. Never reuse a fixed email across tests running in parallel.

Testcontainers manages container lifecycles by default; do not enable global container reuse in CI without strict controls over data resets and image versions.

## 20. Testing API Errors and Error Contracts

A real database can emit errors that mocks fail to simulate accurately. Test how the API translates each error category:

| Situation | Response typically considered |
|---|---|
| Malformed request/validation failure | 400 Bad Request |
| Resource not found | 404 Not Found |
| Unique/business conflict | 409 Conflict |
| Missing authentication | 401 Unauthorized |
| Insufficient permissions | 403 Forbidden |
| Database temporarily unavailable | 503 Service Unavailable or system error per contract |
| Implementation SQL error | 500 Internal Server Error |

Exact status codes must match your application's API contract. Never expose raw SQL, stack traces, schema names, or vendor error codes to clients.

Tests should also check stable error body fields such as code, message, and traceId rather than asserting raw driver exception messages that can vary across database versions or locales.

## 21. Separating API Tests from Repository Tests

An API test with a real database incurs server, context, migration, and container startup costs. There is no need to duplicate every mapping edge case at both layers.

Divide responsibilities cleanly:

| Test | Primary verification |
|---|---|
| Service unit tests | Business rules and branching logic |
| Repository integration tests | SQL, mapping, converters, constraints, dialects |
| API slice tests | Routing, validation, status codes, serialization, security mapping |
| Full API + database integration tests | HTTP, security, services, transactions, and persistence together |
| Concurrency/load tests | Locking, pooling, throughput, and invariants under load |

API integration tests should focus on critical use cases and external contracts. Repository tests dig deeper into SQL and mapping details.

## 22. CI and Reproducibility

To keep tests trustworthy in CI:

- Pin database image versions.
- Use ephemeral test databases or containers.
- Wait for database health/readiness before running migrations.
- Run migrations from an empty state.
- Use credentials restricted to the test database.
- Never pull production secrets into test environment variables.
- Collect container logs on test failure.
- Set timeouts for container startup, HTTP responses, and queries.
- Clean up containers after tests.
- Re-run critical tests against the exact production database major version.
- Keep test fixtures small and deterministic.

When tests fail, capture useful diagnostics such as request correlation IDs, SQLState, exception classes, and redacted database logs. Never log tokens, passwords, or full request bodies carrying personal data.

## 23. Comprehensive API Integration Test Example

The example below combines WebTestClient, Testcontainers, repositories, and persistence verification:

~~~java
@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
class CustomerApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + database.getHost()
                        + ":"
                        + database.getMappedPort(5432)
                        + "/"
                        + database.getDatabaseName());
        registry.add("spring.r2dbc.username", database::getUsername);
        registry.add("spring.r2dbc.password", database::getPassword);
    }

    @Autowired
    WebTestClient client;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void createsCustomerAndPersistsIt() {
        CreateCustomerRequest request =
                new CreateCustomerRequest(
                        "integration@example.test",
                        "Integration Customer");

        EntityExchangeResult<CustomerResponse> result =
                client.post()
                        .uri("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .bodyValue(request)
                        .exchange()
                        .expectStatus().isCreated()
                        .expectBody(CustomerResponse.class)
                        .returnResult();

        CustomerResponse response = result.getResponseBody();

        assertThat(response).isNotNull();
        assertThat(response.id()).isNotNull();

        StepVerifier.create(customerRepository.findById(response.id()))
                .assertNext(saved -> {
                    assertThat(saved.getEmail())
                            .isEqualTo("integration@example.test");
                    assertThat(saved.getFullName())
                            .isEqualTo("Integration Customer");
                })
                .verifyComplete();

        client.get()
                .uri("/api/customers/{id}", response.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(response.id())
                .jsonPath("$.email")
                    .isEqualTo("integration@example.test");
    }
}
~~~

This is an integration skeleton. Real tests must import your project's DTOs/entities/repositories, configure schemas or migrations, clean up data, and align assertions with the API contract. Do not mock the repository in this test because the goal is exercising the real database.

## 24. Sequential Implementation Checklist

When building API integration tests with R2DBC, follow this order:

1. Choose a dedicated test database matching the production engine.
2. Select an R2DBC driver and version compatible with Spring Boot/Spring Data.
3. Configure Testcontainers or an external test database.
4. Initialize the application context with the test profile.
5. Supply R2DBC URL and credentials via dynamic properties.
6. Run migrations/schema initializers before tests send requests.
7. Inject WebTestClient and pick RANDOM_PORT when a real HTTP server is needed.
8. Create fixtures via repositories or DatabaseClient and wait for completion.
9. Send HTTP requests and assert status/headers/body.
10. Read back from the database to confirm inserts/updates/deletes.
11. Test validation, constraints, not-found cases, security, and transaction rollbacks.
12. Test streaming/cancellation if the API returns Flux or SSE.
13. Clean up data in an awaited step.
14. Isolate parallel tests and never share production data.
15. Run in CI against a database version and configuration close to production.

## 25. Key Takeaways

- WebTestClient tests HTTP requests/responses, with scope determined by binding mode: controller, application context, or real server.
- Combine @SpringBootTest with RANDOM_PORT and WebTestClient when testing the full HTTP stack with a database.
- Testcontainers provides a real database engine; use the engine and version matching production.
- Register the R2DBC URL, username, and password with DynamicPropertySource when containers allocate dynamic hosts/ports.
- Run migrations/schema initializers before running API tests.
- Assert both HTTP responses and persisted data; a 201 status alone does not prove rows saved accurately.
- Use the database-returned ID rather than guessing IDs or querying SELECT MAX(id).
- @Transactional on a test method does not automatically wrap server-handled HTTP request transactions.
- Reactive cleanup must be awaited; never call detached subscribe() inside lifecycle methods.
- Security tests must distinguish mock authentication from real token validation.
- Use StepVerifier to check Flux/SSE emissions, completion, errors, and cancellation.
- Test constraints and transaction rollbacks against a real database, not just mocked exceptions.
- Never treat H2 as proof of compatibility for production SQL, types, locking, or transactions.
- Parallel tests require separate databases/schemas/namespaces or constrained parallelism.
- Keep test databases ephemeral with dedicated credentials, and never put sensitive production data into fixtures.
