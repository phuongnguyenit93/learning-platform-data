# Learning Flow from Java Objects to HTTP and Real Resources

Testing in Spring has multiple levels because an application crosses many boundaries: Java objects, collaborating components, the Spring container, HTTP handlers, and external resources such as databases or message brokers. Each level answers a different set of questions. Choosing the right level keeps tests reliable while remaining readable, fast, and effective at isolating bugs.

This lesson follows a progressive path: starting with a standalone Java object, introducing collaborators, verifying Spring bean wiring, going through MVC or WebFlux, sending HTTP requests, and finally connecting to real resources in the test environment.

## Learning Objectives

After this lesson, you can:

- Distinguish unit tests, component tests, slice tests, integration tests, and end-to-end tests.
- Choose between plain JUnit, Mockito, Spring TestContext, Spring Boot test slices, and `@SpringBootTest`.
- Explain precisely what `MockMvc` verifies and when you need to start a real web server.
- Test repositories and persistence configuration against a test database.
- Connect the application to isolated resources using Testcontainers or equivalent test configuration.
- Design data, transactions, and configuration so tests run independently and repeatably.

## Map of Testing Boundaries

Suppose an order creation feature traverses a controller, service, repository, and PostgreSQL. We can verify each boundary in the following order:

~~~mermaid
flowchart LR
    A["Java object<br/>value objects, rules"] --> B["Logic and collaborators<br/>service + Mockito"]
    B --> C["Spring TestContext<br/>bean wiring, configuration"]
    C --> D["In-process HTTP<br/>MockMvc / WebTestClient"]
    D --> E["HTTP over sockets<br/>real server + client"]
    E --> F["Real resources<br/>PostgreSQL, Redis, broker"]
~~~

Later levels cover more components and come closer to production runtime behavior. In return, they usually require more startup time, data setup, and infrastructure. A higher-level test does not automatically replace all lower-level tests: when a test fails, a small unit test usually points to the cause much faster.

| Level | Components Executed | Primary Question |
|---|---|---|
| Java unit test | Object or class under test | Are rules and outputs correct for the inputs? |
| Unit test with mocks | Class under test and simulated collaborators | Does the class collaborate properly with its dependencies? |
| Spring context test | One or a group of real beans | Does Spring create and wire beans properly? |
| Slice test | One framework slice, such as MVC or JPA | Does that framework part work with its related configuration? |
| Application integration test | Most of the application's configuration and beans | Do real components collaborate properly? |
| HTTP test with real server | Embedded server and HTTP client | Does the application receive and return requests over sockets properly? |
| Integration with real resources | Application with test database, broker, or service | Is communication with external systems correct? |

## 1. Starting from a Standalone Java Object

A Java object does not need Spring to exist. For example, a value object can enforce its own invariants:

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
~~~

We verify its behavior with JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsPositiveValue() {
        Quantity quantity = new Quantity(2);

        assertEquals(2, quantity.value());
    }

    @Test
    void rejectsZero() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Quantity(0)
        );
    }
}
~~~

This test does not initialize an `ApplicationContext`, needs no `@SpringBootTest`, and needs no database. It directly verifies `Quantity`'s contract.

Prefer this level for:

- Value objects, conversion functions, and data validators.
- Pure Java calculation rules or business decisions.
- Logic that does not depend on the container, network, or out-of-process resources.

A good unit test usually has three clear parts: preparing inputs, invoking the behavior under test, and asserting outcomes or side effects. Test names should describe the behavior and condition, such as `rejectsZero` or `calculatesTotalForMultipleItems`.

## 2. Testing Services and Collaborators with Mockito

Services typically coordinate multiple components. For example, `OrderService` validates quantity and then saves an order via `OrderRepository`. We can keep the service real and replace the repository with a mock to verify coordination logic:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @Test
    void rejectsNonPositiveQuantityBeforeSaving() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.create("BOOK-1", 0)
        );

        verifyNoInteractions(repository);
    }

    @Test
    void savesAnOrderForValidInput() {
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Order result = service.create("BOOK-1", 2);

        assertEquals("BOOK-1", result.getSku());
        assertEquals(2, result.getQuantity());
        verify(repository).save(any(Order.class));
    }
}
~~~

`@Mock` creates fake dependencies, while `@InjectMocks` injects those dependencies into the service. `MockitoExtension` integrates Mockito with JUnit Jupiter. Spring does not participate in this test.

Mocks fit when the goal is to verify the logic of the class under test and how it calls collaborators. For example, you want to confirm the service rejects invalid input before calling the repository, or passes the right arguments to a payment gateway.

Do not mock the very object the test is supposed to verify. Nor should you assert excessive internal details like non-contractual call order. If you mock every dependency in every test, you will never verify whether real components are compatible with one another.

## 3. When Do You Need Spring TestContext?

Unit tests do not verify how Spring creates beans, resolves dependencies, applies profiles, or reads configuration. When that wiring itself is what needs confirmation, spin up a small `ApplicationContext`.

Spring TestContext provides context testing infrastructure and JUnit integration. For plain Spring Framework configurations, you can use `@SpringJUnitConfig`; for Spring Boot applications, annotations like `@SpringBootTest` or test slices already integrate Spring TestContext.

Minimal configuration example:

~~~java
@Configuration
class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

~~~java
@SpringJUnitConfig(GreetingConfiguration.class)
class GreetingServiceContextTest {

    @Autowired
    GreetingService greetingService;

    @Test
    void createsServiceFromConfiguration() {
        assertEquals("Hello, Ada", greetingService.greet("Ada"));
    }
}
~~~

This test confirms Spring reads the configuration and provides the bean to the test. It does not need to start the entire application.

Several common Spring TestContext tools:

- `@ContextConfiguration` specifies configuration used to create the context.
- `@SpringJUnitConfig` combines context configuration with JUnit Jupiter integration.
- `@ActiveProfiles` activates test profiles.
- `@TestPropertySource` adds test-specific properties.
- `@DirtiesContext` marks a context as modified and needing eviction from the cache.
- `@Transactional` manages test transactions when a suitable transaction manager is present.
- `@Sql` runs SQL scripts to prepare or clean up data.

Spring can cache contexts across tests with compatible configurations. This reduces startup time. Use `@DirtiesContext` only when a test genuinely mutates context state in a way that cannot be restored; using it casually defeats caching and slows down the suite.

## 4. Testing HTTP with Test Slices

An MVC controller accepts requests, passes data to services, and builds responses. When you want to check mappings, binding, validation, status codes, headers, and JSON without starting the entire application, consider `@WebMvcTest`.

Controller example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResult> create(
            @RequestBody CreateOrderRequest request) {

        OrderResult result =
            orderService.create(request.sku(), request.quantity());

        URI location = URI.create("/api/orders/" + result.id());
        return ResponseEntity.created(location).body(result);
    }
}

record CreateOrderRequest(String sku, int quantity) {}

record OrderResult(UUID id, String sku, int quantity) {}
~~~

MVC test:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderAndReturnsLocation() throws Exception {
        UUID id = UUID.fromString(
            "7c1d4e5a-9b2f-4a6c-8d0e-123456789abc"
        );

        when(orderService.create("BOOK-1", 2))
            .thenReturn(new OrderResult(id, "BOOK-1", 2));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": "BOOK-1",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/orders/" + id
            ))
            .andExpect(jsonPath("$.sku").value("BOOK-1"))
            .andExpect(jsonPath("$.quantity").value(2));
    }
}
~~~

`@WebMvcTest` loads only the MVC configuration needed for the selected controller and related components. Services are typically replaced with mocks so the test focuses on the controller's HTTP contract.

`MockMvc` dispatches requests through the Spring MVC infrastructure in the same process. It exercises routing, argument resolvers, converters, validation, and MVC components configured in the context. However, it **does not open a TCP port and does not send requests over the network**. Therefore, `MockMvc` does not verify the embedded server, sockets, TLS, reverse proxies, or external network settings.

For WebFlux applications, you can use `@WebFluxTest` and `WebTestClient` to test the reactive slice. `WebTestClient` can also work against a running live application; what the test means depends on how the client is wired.

When a controller has validation or security, test both valid and invalid cases: malformed bodies, missing required fields, constraint-violating data, unauthenticated users, or insufficient permissions. Make sure the test runs the exact filters and security configuration you intend to verify.

## 5. Testing Persistence with JPA Test Slices

A repository sits at the boundary between the application and the database. Testing a service with a mocked repository cannot prove queries, entity mappings, constraints, or transactions actually work.

With Spring Data JPA, `@DataJpaTest` creates a test slice focused on JPA and repositories:

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesAndFindsOrder() {
        Order saved = repository.save(new Order("BOOK-1", 2));

        Optional<Order> found = repository.findById(saved.getId());

        assertTrue(found.isPresent());
        assertEquals("BOOK-1", found.orElseThrow().getSku());
        assertEquals(2, found.orElseThrow().getQuantity());
    }
}
~~~

By default, `@DataJpaTest` may use an embedded database if a matching dependency is present. This is handy for many basic mapping and repository checks. However, H2 or another embedded database is not guaranteed to behave identically to PostgreSQL, MySQL, or the production engine. Differences in dialects, data types, collations, constraints, locking, and SQL statements can let tests stay green while production fails.

If the behavior under test depends on a specific database engine, run tests against that exact engine in an isolated environment. When preserving a datasource supplied by Testcontainers, you can configure `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`.

## 6. Full-Application Integration Still Using Simulated HTTP

When you need to confirm controller, service, repository, and application configuration collaborate, you can use:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsOrderThroughApplicationConfiguration()
            throws Exception {

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": "BOOK-1",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated());
    }
}
~~~

Unlike `@WebMvcTest`, `@SpringBootTest` loads a broader application configuration. Services and repositories can be real beans; the datasource and other integrations use whichever configuration is active.

Combining `@AutoConfigureMockMvc` lets you send requests through MVC in-process. This is a good fit for verifying flows across multiple application layers without opening a real HTTP port.

The label integration test does not mean the test touches every external system. If the datasource is still an embedded database, or the email client is still a mock, those parts remain unverified against real resources. Document clearly which boundaries are real and which are substituted.

## 7. Starting a Web Server and Sending Real HTTP

When you need to test the embedded server and communication over sockets, use a random-port web environment:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void acceptsRequestOverRealHttpServer() {
        CreateOrderRequest request =
            new CreateOrderRequest("BOOK-1", 2);

        ResponseEntity<OrderResult> response =
            http.postForEntity(
                "/api/orders",
                request,
                OrderResult.class
            );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("BOOK-1", response.getBody().sku());
    }
}
~~~

With `RANDOM_PORT`, Spring Boot starts the embedded web server on an available port. `TestRestTemplate` sends HTTP requests to that server. This additionally tests accepting requests over sockets and returning responses from the server.

Common web environment values:

| Value | Behavior |
|---|---|
| `MOCK` | Creates a simulated web application context; does not start an embedded server. This is the default for `@SpringBootTest`. |
| `RANDOM_PORT` | Starts the embedded server on a random port. |
| `DEFINED_PORT` | Starts the embedded server on the configured port. |
| `NONE` | Creates a non-web application context. |

For Servlet applications, `MockMvc` generally fits in-process MVC checks; `TestRestTemplate` or an appropriate HTTP client is used when a server is running. For WebFlux, `WebTestClient` can target a mock server or a live server depending on configuration. Choose the client by stack and boundary to verify.

Tests against a real server usually take longer. Use them only when sockets, server configuration, filter chains, codecs, or real HTTP communication are part of the requirement.

## 8. Connecting to Real Resources in the Test Environment

At this point, the application may run over HTTP yet still not use a real database or broker. To verify that integration, provide test resources with controlled lifecycles and data.

Testcontainers can launch containers for PostgreSQL, Redis, Kafka, and many other services. Example with PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class OrderPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInPostgres() {
        Order saved = repository.save(new Order("BOOK-1", 2));

        assertTrue(repository.findById(saved.getId()).isPresent());
    }
}
~~~

In Spring Boot versions supporting service connections, `@ServiceConnection` lets Spring Boot infer connection details from the container. Another approach is `@DynamicPropertySource` to register the container's URL, username, and password into the Environment. Pick one suited to your project version and configuration; do not declare both mechanisms redundantly.

Manual property registration example:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Combined with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, a test can send real HTTP to an application connected to PostgreSQL in a container. The exercised path is then:

~~~mermaid
sequenceDiagram
    participant T as HTTP test client
    participant S as Embedded server
    participant C as Controller
    participant V as Service
    participant R as Repository
    participant D as PostgreSQL container

    T->>S: POST /api/orders
    S->>C: Dispatched request
    C->>V: create(sku, quantity)
    V->>R: save(order)
    R->>D: INSERT
    D-->>R: Persistence result
    R-->>V: Order
    V-->>C: OrderResult
    C-->>S: HTTP 201 + JSON
    S-->>T: Response
~~~

Such a test covers many boundaries, yet introduces more environment requirements: Docker must be running, images must pull cleanly, ports and resources must be allocated, migrations must finish, and data must be isolated.

"Real resources" here means using the real engine or service in a disposable, reproducible test environment. Never use a production database or production service account as a test resource. Each run should have isolated data or a deterministic setup and cleanup procedure.

## 9. Transactions, Data, and Independence Between Tests

A suite is trustworthy only when outcomes do not depend on execution order. Key rules:

**Test transactions do not always wrap HTTP requests.** With slice tests like `@DataJpaTest`, Spring usually runs each test in a transaction and rolls it back afterward. Yet with `RANDOM_PORT`, requests are handled on separate server threads and transactions. A transaction bound to the test method does not automatically roll back database writes performed by that request. Actively clean up data, use separate schemas/databases, or create throwaway resources.

**Test data needs clear ownership.** Avoid relying on a record created earlier by another test. Each test should prepare the data it needs and assert only outcomes within its own scope. When tests run in parallel, avoid sharing fixed keys or names that can collide.

**Test configuration must be isolated.** Use test profiles and properties to configure endpoints, dummy credentials, and suitable options. Never let tests accidentally read real secrets or write data to a real environment.

**Cleanup must match the resource type.** Databases can use transactions, truncation, or isolated schemas; file systems can use temporary directories; brokers can use isolated topics/queues. Do not assume a database rollback removes files, messages, or side effects in other systems.

**Do not use `@DirtiesContext` to fix data bugs.** This annotation evicts the context from cache; it is not a general mechanism to wipe databases or reset external state. Clean up the specific state that was mutated.

**Asynchronous checks must wait on conditions, not arbitrary durations.** For message brokers or background tasks, use waiting mechanisms with explicit timeouts and clear completion criteria. A fixed `sleep` both slows tests down and causes random failures.

## 10. Choosing the Right Tool for the Question to Answer

| What You Want to Verify | Usually Appropriate Tooling |
|---|---|
| Rules of a Java object or function | JUnit Jupiter |
| Service logic and collaborator calls | JUnit Jupiter + Mockito |
| Whether Spring creates a group of beans properly | `@SpringJUnitConfig` or Spring TestContext |
| MVC mapping, binding, and responses | `@WebMvcTest` + `MockMvc` |
| Reactive controller | `@WebFluxTest` + `WebTestClient` |
| Entity mappings and repository queries | `@DataJpaTest` |
| Flow across full application configuration | `@SpringBootTest` |
| HTTP via real embedded server | `@SpringBootTest(RANDOM_PORT)` + HTTP client |
| Compatibility with a specific database or broker | Testcontainers + integration tests |
| User journey spanning multiple services | End-to-end tests in an integrated environment |

You do not need every test type for every feature. Ask concrete questions before picking annotations:

1. Does this behavior belong to a Java object or depend on Spring?
2. Do I need to test one class, one framework slice, or the entire application configuration?
3. Does the HTTP boundary need real sockets and an embedded server?
4. Does the outcome depend on dialects, transactions, or an external service's behavior?
5. Can I create isolated data and resources so the test repeats cleanly?

Pick the smallest level that still verifies the boundary of interest. Supplement with targeted integration tests for boundaries that mocks cannot confirm.

## 11. Common Misconceptions

- **Using `@SpringBootTest` for every test:** huge contexts slow the suite and make failures hard to pinpoint. Use unit tests or slices when the question involves only a small part.
- **Thinking `MockMvc` is real HTTP:** `MockMvc` tests the MVC pipeline in-process, not sockets or an embedded server.
- **Assuming `@DataJpaTest` always uses the same database as production:** embedded databases can differ in dialects and behavior from real engines.
- **Mocking the repository and concluding persistence works:** mocks only confirm how the service calls its collaborator; they do not check SQL, mappings, or constraints.
- **Thinking `@Transactional` on a test rolls back every request:** requests through a real server run in separate transactions.
- **Using `@DirtiesContext` to reset all state:** contexts, databases, files, and message brokers have independent lifecycles.
- **Checking only the status code:** a response with the right status can still carry the wrong body, headers, or data. Assert all parts belonging to the API contract.
- **Sharing data across tests:** order-dependent tests often pass in isolation yet fail in the full suite or under parallel runs.

## 12. Recommended Practical Workflow

For an order creation feature, you can structure tests in this sequence:

1. Write unit tests for value objects and input rules.
2. Write service unit tests with a mocked repository to verify business decisions and interactions.
3. If bean configuration carries specific risk, write a small context test for wiring or profiles.
4. Write MVC slice tests for requests, validation, status, headers, and JSON.
5. Write JPA slice tests for mappings and repository queries.
6. Write an application integration test to confirm controller, service, and repository collaborate.
7. If requirements depend on the HTTP server, add a `RANDOM_PORT` test.
8. If requirements depend on PostgreSQL or a specific broker, add Testcontainers tests.
9. Run each test group independently, then run the related suite; verify tests can rerun without a fixed order.

When a test fails, identify the nearest boundary that explains the failure. Failing unit tests usually point to rules or logic; slice tests may point to framework configuration; tests with real resources can expose dialect, transaction, or protocol differences. Keeping each test focused on one clear contract makes fixing bugs faster and safer.

## Conclusion

The progression from Java objects to HTTP and real resources is a ladder for verifying Spring application boundaries. JUnit and Mockito check logic quickly; Spring TestContext confirms bean wiring; test slices focus on MVC or persistence; `@SpringBootTest` verifies application integration; real servers and Testcontainers extend coverage to network communication and infrastructure.

A balanced test suite combines multiple levels with clear intent. Every test should answer: which boundary is being checked, which components are real, which are substituted, and how data is isolated.

