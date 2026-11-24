# Choosing Additional Tools by Risk Instead of Using Every Tool for Every Test

A Spring project can use many testing tools: JUnit, Mockito, Spring TestContext, MockMvc, WebTestClient, RestTestClient, Testcontainers, WireMock, MockWebServer, Awaitility, StepVerifier, ArchUnit, and other libraries. Having many tools available does not mean every test needs all of them. Each tool brings a different level of simulation, confidence, execution cost, and maintenance cost.

Start from the risk you need to uncover. If a bug can happen inside the logic of a plain Java method, a unit test with JUnit and Mockito is usually enough. If the risk lies in request mapping, validation, or JSON binding, you need to test through Spring MVC infrastructure. If the application depends on specific behavior of PostgreSQL, Kafka, or an HTTP service, you need integration tests with the corresponding infrastructure or a simulation backed by a clear contract. If the risk lies in when an asynchronous task completes, you need synchronization tools and verification of publishers or final state.

The goal is to pick the smallest set of tools that still yields reliable evidence for important risks. This selection keeps tests fast, easy to understand, and meaningful when they fail.

## 1. Start from Risk, Not from a Tool Checklist

Before picking tools, describe what can break and its consequences. A practical analysis examines four factors:

| Factor | Question to answer |
|---|---|
| Impact | If a bug occurs, how severely are users, data, or the system affected? |
| Likelihood | Is this logic or configuration prone to breaking when code, dependencies, or environments change? |
| Detection difficulty | Do existing unit tests or logs catch the bug before release? |
| Dependency level | Does behavior depend on the Spring container, database, HTTP protocol, broker, threads, or real infrastructure? |

Examples:

- A simple fee calculation function with clear inputs and outputs: the risk lies mostly in logic; JUnit and AssertJ are usually sufficient.
- A controller receiving JSON with LocalDate, validation, and exception advice: the risk lies in mapping, message converters, and MVC configuration; an MVC slice test is needed.
- A repository using native queries or relying on PostgreSQL-specific behavior: mocking the repository cannot verify real SQL; a database of the same or equivalent kind is needed.
- A client calling a payment service: the risk lies in URI, method, headers, serialization, timeouts, and error responses; outbound requests must be tested.
- A background task updating status after processing: the risk lies in dispatch, synchronization, retries, and race conditions; completion and competing states must be verified.

Not every risk needs a production-like environment. Choose the exact boundary where bugs can emerge.

## 2. Match Test Level to the Boundary Under Verification

Tests can be categorized by increasing scope:

~~~text
Plain Java logic
    |
    v
Unit test
JUnit + Mockito + AssertJ
    |
    v
A Spring slice
@WebMvcTest / @DataJpaTest / @JsonTest
    |
    v
ApplicationContext
@SpringBootTest
    |
    v
Real integration infrastructure or protocol simulation
Testcontainers / WireMock / MockWebServer
    |
    v
System running over HTTP and deployment-like environment
Random port / external test environment
~~~

Broader scopes typically bring higher startup costs, longer runtimes, and more reasons a test can fail. Therefore, use a broader scope when it verifies a risk that narrower scopes cannot check.

### 2.1. Unit tests for logic that does not need Spring

Choose JUnit Jupiter, Mockito, and AssertJ when:

- The object does not need a Spring container to execute.
- Dependencies can be substituted with interfaces or fake collaborators.
- What needs verification is rules, logic branches, calculations, or how collaborators interact.
- There is no need to test serialization, dependency injection, transaction managers, or request mapping.

Example:

~~~java
class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void waivesFeeWhenOrderMeetsThreshold() {
        Money fee = calculator.calculate(
                Money.of(600_000, "VND"),
                DeliveryRegion.CITY);

        assertThat(fee).isEqualTo(Money.zero("VND"));
    }
}
~~~

You do not need `@SpringBootTest` just to instantiate an object with a simple constructor. Booting a context for plain Java logic slows tests down and can let unrelated configuration errors obscure business logic failures.

Mockito is well-suited for isolating collaborators and checking meaningful interactions. Do not mock every object just to inflate assertion counts. If a test mocks every underlying class and only verifies mock calls in exact implementation order, it becomes brittle when code is refactored without changing external behavior.

### 2.2. Spring test slices for part of the framework

Use a test slice when the risk sits in a specific part of Spring:

| Slice | Boundary tested |
|---|---|
| @WebMvcTest | Controllers, request mappings, argument binding, validation, converters, and advice in the MVC slice |
| @DataJpaTest | Repositories, entity mappings, queries, and JPA integration in a test context |
| @JsonTest | JSON serialization/deserialization and related Jackson configuration |
| @RestClientTest | REST client components and Spring Boot outbound HTTP testing configuration |

For example, @WebMvcTest fits when verifying that JSON fields bind properly and validation errors return the right status. Services are usually mocked because the test is not meant to verify service logic or the database.

For example, @DataJpaTest fits when checking mappings, constraints, relationships, and repository queries. If the default test database differs from production, consider Testcontainers to catch differences in dialect, data types, or SQL behavior.

Slices have the advantage of starting faster than a full application context and narrowing test scope. However, a slice only tests configuration loaded in that slice. If a test needs a bean or configuration absent from the slice, import it intentionally or switch to an appropriate test context; do not pile on arbitrary configurations that defeat the slice's purpose.

### 2.3. Full ApplicationContext when integrating multiple beans

@SpringBootTest fits when the risk lies in how multiple beans and configurations collaborate:

- Dependency injection, conditional configuration, or bean selection.
- Transaction manager working alongside services and repositories.
- Security filter chain or application-wide configuration.
- Event listeners, schedulers, or executors registered in the context.
- Multiple application layers collaborating through Spring configuration.

Example:

~~~java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void storesOrderAndPublishesApplicationEvent() {
        Order order = orderService.placeOrder(
                new PlaceOrderCommand("COFFEE-01", 2));

        assertThat(orderRepository.findById(order.getId()))
                .isPresent();
    }
}
~~~

This is only an illustrative skeleton. A full test context does not automatically mean the database, broker, or external HTTP services are real. External dependencies still depend on test configuration. Explicitly document which parts are real, which are mocks, and which are containers.

Do not use @SpringBootTest for every test simply because the application uses Spring Boot. A full-context test can be slower and harder to diagnose than several small tests with equal bug-finding power.

## 3. Choosing Tools by Risk Type

The following table maps common risks to suitable tools:

| Risk to detect | Usually suitable tool | When to broaden scope |
|---|---|---|
| Incorrect plain Java business rules | JUnit, AssertJ, Mockito | When rules depend on real data or framework behavior |
| Incorrect HTTP mapping, status, headers, or JSON binding | MockMvc for Spring MVC; WebTestClient for WebFlux; RestTestClient when version supports it | When connectors, Servlet containers, or networking must be verified |
| Incorrect JSON serialization/deserialization | @JsonTest, Jackson tests, or MVC/WebFlux tests | When JSON must be verified across the full endpoint request/response |
| Incorrect JPA queries or mappings | @DataJpaTest | When SQL/dialect depends on a specific database, use Testcontainers |
| Incorrect outbound requests from RestClient/RestTemplate | MockRestServiceServer | When socket-level protocol, TLS, or real HTTP client behavior must be checked |
| Incorrect outbound requests from WebClient | MockWebServer or WireMock | When testing against a real external service in an integration environment |
| Incorrect database, broker, or cache behavior | Testcontainers with the matching technology | When verifying multi-service deployment or real environments |
| Incorrect completion timing of async tasks | CompletableFuture, CountDownLatch, Awaitility | When testing multiple workers, queues, rejections, or race conditions |
| Incorrect reactive stream or backpressure | Reactor StepVerifier | When verifying end-to-end HTTP/reactive connections |
| Cross-module dependency violations | ArchUnit or Spring Modulith | When enforcing architecture at multi-module scale |

You do not need to include every tool in the table in a single test suite. Pick tools matching the boundary where the risk arises.

## 4. Inbound HTTP: MockMvc, WebTestClient, or RestTestClient

Inbound HTTP tools test requests entering the application. Tool choice depends on the web stack and Spring version:

| Tool | Best suited for | Key point to remember |
|---|---|---|
| MockMvc | Spring MVC on the Servlet stack | Tests MVC via the mock Servlet API without opening a socket |
| WebTestClient | Spring WebFlux; can also test some MVC endpoints via an appropriate adapter | Reactive API supporting publisher and streaming verification |
| RestTestClient | Spring Framework 7.0+ for synchronous REST endpoint testing | Can bind to controllers, contexts, router functions, or servers |
| TestRestTemplate | Spring Boot integration tests with a real running server | Sends HTTP over a server port, better suited for end-to-end checks |

Examples:

- MVC controller with mappings, validation, and @ControllerAdvice: use @WebMvcTest with MockMvc.
- WebFlux endpoint returning Flux or Server-Sent Events: use WebTestClient and StepVerifier.
- Spring Framework 7 project using RestTestClient for REST endpoints: choose the bind mode matching the test scope.
- Need to verify real server ports, connectors, or filters: run the server on a random port and use an HTTP client.

Do not use MockMvc to conclude that networking, TLS, or proxies work properly. It does not open sockets. Conversely, do not start a real server just to verify that a JSON field binds properly in a controller.

## 5. Outbound HTTP: Mock Requests or Run a Mock Server?

Services often call external APIs via an HTTP client. Choose the tool by client type and what needs verification:

| Client in the application | Suitable test tool |
|---|---|
| RestClient | MockRestServiceServer.bindTo(RestClient.Builder) |
| RestTemplate | MockRestServiceServer.createServer(RestTemplate) |
| WebClient | MockWebServer or WireMock |

MockRestServiceServer inspects requests at Spring's RestClient or RestTemplate abstraction. It is useful when checking URI, method, headers, body, and response mapping without opening network ports.

MockWebServer or WireMock spins up a mock HTTP server that the client actually sends requests to. They are useful when checking requests through connectors, timeouts, retries, or HTTP protocol-dependent behavior. WireMock can also simulate multiple responses and stateful error scenarios.

Do not mock RestClient or WebClient methods directly in every test if the goal is verifying that HTTP requests are built properly. Mocking method calls can bypass URI builders, serialization, default headers, and connector setup that need testing.

Call real external services in tests only when that environment is controlled and has a clear purpose. Tests depending on public APIs can fail due to network issues, quotas, changing data, or provider outages, making CI unstable.

## 6. Databases and Middleware: When Is Testcontainers Needed?

Mocking repositories does not test real SQL, real mappings, or database transaction behavior. Embedded databases can help for some tests, yet if production runs PostgreSQL, MySQL, or an engine with specific behavior, a different database type can miss bugs.

Testcontainers lets tests start real dependencies inside containers during test execution:

~~~java
@Testcontainers
@DataJpaTest
class OrderRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersUsingProductionDatabaseDialect() {
        // Save test data and verify repository queries.
    }
}
~~~

The example above requires Testcontainers dependencies for JUnit and PostgreSQL, a Docker-compatible runtime in the test environment, and database configuration matching the project. Image versions should be pinned according to the project's dependency policy rather than using tags that shift over time.

Testcontainers is appropriate when:

- Queries use database-specific syntax or features.
- Mappings involve JSON, UUID, arrays, sequences, or engine-dependent types.
- Transaction isolation, locking, or constraints matter.
- Migrations must run cleanly on the production database engine.
- The application integrates brokers like Kafka or Redis and real dependency behavior is a major risk.

You do not need to start a container for every repository test if a test only checks a calculation or a plain Java mapper. Nor do you need containers for every test merely because the project has Docker; startup overhead and environment requirements must be proportional to the risk being uncovered.

## 7. Asynchronous and Reactive Tasks: Choose Tools by Behavior

A background task may finish after the calling method returns. Tests must synchronize on real signals:

- CompletableFuture.get(timeout, unit) when the API returns a future.
- CountDownLatch when waiting for a void task.
- Awaitility when final state is updated across multiple beans or repositories.
- StepVerifier when verifying Mono or Flux.

Example waiting for a status update:

~~~java
worker.startProcessing(jobId);

await()
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(jobRepository.findStatus(jobId))
                        .isEqualTo(JobStatus.COMPLETED));
~~~

Awaitility fits when a test needs to wait for an eventual condition without a direct future or latch. If a test needs to assert exact signals emitted by a publisher, StepVerifier is usually clearer.

Do not use `Thread.sleep(...)` as a synchronization mechanism. Sleep does not confirm that a task ran, does not propagate exceptions from worker threads to the test, and flakes easily on CI. Also avoid collecting an entire Flux into a list if the API is designed for streaming and the test only needs to verify a few elements.

## 8. Module Architecture: Tools Needed Only When Architectural Risk Exists

A unit test can prove a method returns the right value while failing to detect that module A has begun depending directly on internal implementations of module B. If the project has explicit architectural rules, you can add:

- ArchUnit to check packages, layers, naming rules, and dependency directions.
- Spring Modulith to check module boundaries, cross-module dependencies, and certain module integration behaviors in Spring applications.

Example ArchUnit rule:

~~~java
@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule controllersShouldNotAccessRepositories =
            noClasses()
                    .that().resideInAPackage("..web..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..repository..");
}
~~~

Architecture checks are valuable when multiple teams collaborate or a codebase has module boundaries that must remain stable. For a small application without explicit module rules, adding a pile of generic architecture tests only adds maintenance overhead.

## 9. Assessing Risk Levels to Select Test Scope

You can use the following qualitative matrix to decide investment level:

| Impact of failure | Low uncertainty | High uncertainty |
|---|---|---|
| Low | Unit test or existing tests; no extra infrastructure needed | Unit tests covering edge cases; optional small slice test |
| Medium | Unit tests and a slice test at the main boundary | Slice test plus a focused integration test |
| High | Integration tests for dependencies with direct impact | Integration tests with matching dependencies, error and recovery path checks; targeted end-to-end tests |

Examples of high-risk criteria:

- Money transactions, payments, refunds, or balance updates.
- Bulk data deletions or updates.
- Security, authentication, authorization, and data leaks.
- Asynchronous tasks that could duplicate, drop, or reorder work.
- Integrations with external systems carrying strict contracts or quotas.
- Migrations or queries that could corrupt production data.

High risk does not mean every test must run end-to-end. For example, payments might need unit tests for fee math, contract tests for outbound requests, integration tests with the database, and a few workflow tests. Each test covers a specific layer of risk.

## 10. Example: Choosing Tools for an Order Placement Flow

Suppose an order placement flow consists of:

~~~text
HTTP request
    |
    v
OrderController
    |
    v
OrderService
    |--------------------|
    v                    v
OrderRepository      PaymentClient
    |                    |
    v                    v
PostgreSQL           Payment API
    |
    v
OrderPlaced event
    |
    v
Background worker
~~~

A single test does not need to spin up every component. Tools can be allocated by risk:

| Component | Risk | Suitable tool |
|---|---|---|
| Order total and shipping fee math | Wrong calculation rules | JUnit + AssertJ |
| Order creation controller | Wrong JSON binding, validation, or status | @WebMvcTest + MockMvc |
| Repository | Wrong query, mapping, or transaction | @DataJpaTest; Testcontainers PostgreSQL if dialect-dependent |
| PaymentClient | Wrong URI, method, token, body, or error mapping | MockRestServiceServer if using RestClient; WireMock/MockWebServer if a mock HTTP server is needed |
| Event worker | Task never completes, fails, or duplicates | CompletableFuture, latch, Awaitility; test retry/idempotency per design |
| Full workflow | Wrong bean wiring or multi-layer integration | A few @SpringBootTest tests with controlled dependencies |

Controller tests do not need a real database when the goal is request mapping. Repository tests do not need a payment API. Client tests do not need to boot the entire application when only checking outbound requests. A few workflow integration tests verify that parts cooperate, without replacing small tests that report clear failure details.

## 11. Selecting Test Volume and Avoiding Redundant Checks

A behavior can be tested at multiple layers, yet each layer should contribute distinct evidence:

- Unit tests check many logic cases and edge conditions at high speed.
- Slice tests verify integration with part of the framework.
- Integration tests verify real dependencies and configuration within a controlled scope.
- End-to-end tests verify a critical flow across multiple boundaries.

For example, if unit tests already cover dozens of fee-calculation cases, there is no need to repeat all of them inside `@SpringBootTest`. An integration test can check a few representative scenarios to confirm configuration and integration wiring.

Avoid creating multiple tests that differ only in how the context is started while asserting the exact same condition without extra value. Duplicate tests force small changes to be updated in many places and inflate CI duration without proportionally increasing defect detection.

However, the same final outcome may need verification at multiple boundaries if those boundaries have different failure mechanisms. For example, unit tests prove the service handles 404 properly; client tests prove an HTTP 404 response is translated into an exception; integration tests can confirm endpoint configuration and client cooperation.

## 12. Tool Cost Is Also Part of the Decision

Before adding a tool, weigh:

| Cost | What to consider |
|---|---|
| Runtime | Does the tool keep tests fast or add seconds/minutes of startup? |
| Environment | Does CI have Docker, ports, filesystem, or required services? |
| Stability | Do tests depend on timing, networks, external data, or execution order? |
| Maintenance | Who updates images, stubs, fixtures, versions, and configuration? |
| Fidelity | Does the simulation reflect the behavior under test or skip a critical boundary? |
| Diagnostics | When a test fails, do logs pinpoint the failing request, SQL, task, or dependency? |

A tool can be ideal for integration tests yet unsuitable for hundreds of unit tests run on every file save. Conversely, over-mocking makes tests fast yet misses configuration or protocol bugs. Choose based on both defect-detection value and operational cost.

## 13. Organizing the Test Suite by Feedback Speed

Tests can be grouped to run at different stages:

| Group | Contents | When to run |
|---|---|---|
| Fast tests | Unit tests, mock-based tests, small slices | Every commit or pull request |
| Integration tests | Database/containers, HTTP mock servers, broader application contexts | Pull requests or integration pipelines |
| Extended tests | Many dependencies, migrations, concurrency, or complex workflows | Before release or on a scheduled cadence |
| Environment tests | Checks against external test/staging systems | Following deployment workflows and environment contracts |

This is a reference organization, not a rigid rule. A fast and stable integration test can still run on every pull request. A critical end-to-end test may need to run before every release. Base decisions on duration, risk level, and reproducibility.

Separate test groups using JUnit tags or Gradle source sets/tasks matching your project structure. Do not build complex multi-tier build setups if there are only a handful of tests. What matters is that developers know which groups run by default, which require Docker or external services, and how to run them locally.

## 14. Signs of Overusing Tools

- Every test boots `@SpringBootTest`, even plain Java calculation tests.
- Every repository test starts a container even when not testing database-specific behavior.
- Every HTTP client test calls a real service over the network.
- Tests use so many mocks that requests, serialization, or SQL are no longer verified.
- Async tests rely on long sleeps and guesswork timeouts.
- End-to-end tests repeat every case already thoroughly checked in unit and slice tests.
- A single test starts a database, broker, web server, mock HTTP server, and multiple executors just to assert one behavior.
- When a test fails, you cannot tell whether the bug came from code, configuration, environment, or an external service.

If you observe these signs, revisit the question: which risk is being tested, and which tools are actually required to uncover it?

## 15. Signs of Underusing Tools

Conversely, a test suite may be too light if:

- Repositories are tested only with mocks while SQL contains critical logic.
- Controllers are called directly as Java methods without testing mapping or serialization.
- Outbound clients only mock method calls without checking URI/headers/body.
- Transactions or locking matter, yet no tests run against a matching database.
- Security is checked only on service methods, skipping filter chains or request authentication.
- Async tasks are invoked without waiting for completion or observing exceptions.
- Migrations are never executed in tests against a compatible database.
- Bean configurations have multiple profiles/conditions, yet no context tests verify critical profiles.

In these cases, adding a test at the right boundary adds far more value than many extra unit tests.

## 16. Pre-Test Tool Selection Workflow

For each feature or change, follow these steps:

1. Describe the user behavior or system contract to protect.
2. List how that behavior could fail and the consequences.
3. Identify the boundary where bugs can occur: logic, Spring MVC/WebFlux, database, HTTP client, broker, executor, or application configuration.
4. Pick the tool closest to that boundary that can still verify the required behavior.
5. Decide which dependencies are real, which are mocked, and why.
6. Check execution cost, CI environment, and reproducibility.
7. Add broader-scope tests only when narrower tests cannot catch a major risk.
8. Name tests after the behavior being protected, not the library or implementation details.
9. When a test fails, ensure enough diagnostic information is available to trace the relevant request, data, task, or dependency.

Decision examples:

| Question | If yes | Choice to consider |
|---|---|---|
| Can the logic run without Spring? | Yes | Unit test |
| Need to verify MVC requests/responses? | Yes | MockMvc or matching MVC tool |
| Need to verify application-wide beans/configuration? | Yes | ApplicationContext test or @SpringBootTest |
| Does SQL depend on a specific database? | Yes | Testcontainers with the same database type |
| Need to verify outbound HTTP requests? | Yes | MockRestServiceServer, WireMock, or MockWebServer depending on client |
| Need to wait for asynchronous state? | Yes | Future, latch, or Awaitility |
| Need to verify reactive publishers? | Yes | StepVerifier |
| Need to enforce cross-module dependency rules? | Yes | ArchUnit or Spring Modulith |
| Need to verify real connectors/networking? | Yes | Real running server and HTTP client |

## 17. Concluding Principles

No single Spring testing tool fits every risk. Unit tests provide fast feedback and check logic; slice tests verify integration with part of the framework; application context tests check multiple beans and configurations working together; Testcontainers and mock HTTP servers verify dependency boundaries; Awaitility and StepVerifier verify asynchronous or reactive behavior.

Choose tools based on failure impact, likelihood, detection difficulty, and the real boundary that needs verification. Keep tests small wherever possible, add integration tests when they produce new evidence, and reserve production-like environments for behaviors that mocks or slices cannot reliably represent. In this way, the test suite stays focused on important risks while remaining fast enough to run frequently.
