# Scope of Spring Framework Testing vs. Spring Boot Tools

When testing a Spring application, we frequently encounter two similarly named API groups: testing support provided by **Spring Framework** and testing utilities added by **Spring Boot**. They work together, yet solve different problems.

Spring Framework provides the foundation for building and managing a test environment for Spring components: loading an `ApplicationContext`, injecting dependencies into tests, managing transactions, setting up a simulated web environment, and providing helper objects such as `MockMvc`. Spring Boot builds on that foundation to start applications close to real configuration, auto-configure test components, and offer test slices such as MVC or JPA.

The boundary can be pictured as follows:

```text
JUnit / test engine / assertion / mocking libraries
                    │
                    ▼
Spring Framework Test
  - TestContext Framework
  - SpringExtension and JUnit integration
  - transactions, profiles, properties, SQL for tests
  - MockMvc, WebTestClient, MockRestServiceServer
                    │
                    ▼
Spring Boot Test
  - application startup with SpringApplication
  - @SpringBootTest and test slices
  - test environment auto-configuration
  - Boot-specific utilities
```

This is a layered relationship, not two competing toolsets. A Spring Boot test typically relies on Spring Framework mechanisms underneath.

## 1. What Is Spring Framework Testing Responsible For?

Spring Framework Testing focuses on **testing components that use Spring** and provides infrastructure so a test can interact with the Spring container in a controlled manner. Most APIs live in the `spring-test` module, with familiar packages such as `org.springframework.test.context`, `org.springframework.test.context.junit.jupiter`, `org.springframework.test.web.servlet`, and `org.springframework.test.web.reactive.server`.

### 1.1. TestContext Framework

The TestContext Framework is the core foundation. It bridges the test framework (such as JUnit Jupiter) and Spring's `ApplicationContext`. Through it, a test can instruct Spring to load configuration, inject beans into the test instance, apply dedicated profiles or properties, and reuse contexts across tests when configurations match.

Some common annotations:

| Annotation | Role in Testing |
|---|---|
| `@ExtendWith(SpringExtension.class)` | Connects JUnit Jupiter with the Spring TestContext Framework. |
| `@ContextConfiguration` | Specifies configuration classes or resources used to create the test `ApplicationContext`. |
| `@SpringJUnitConfig` | Convenient composed annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. |
| `@ActiveProfiles` | Selects profiles activated when creating the test context. |
| `@TestPropertySource` | Adds property sources dedicated to tests. |
| `@DynamicPropertySource` | Registers dynamic properties, often used when values become available only after starting test resources. |
| `@DirtiesContext` | Marks the context as mutated by the test and needing eviction from the cache. |

Example of a test using Spring Framework without Spring Boot:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsAnOrder() {
        Order order = orderService.createOrder(new CreateOrderCommand("SKU-1", 2));

        assertThat(order.getItems()).hasSize(1);
    }
}
```

In this example, the test specifies the Spring configuration to load. Spring Test builds the context from that configuration and injects `OrderService` into the test. No full Spring Boot application bootstrap occurs.

The TestContext Framework also manages context lifecycles and listeners executing before/after tests. Context caching avoids reinitializing the same configuration for each test method. Thus, tests run faster when multiple tests share a context. In return, tests must avoid leaving unintended shared state; use `@DirtiesContext` only when a test genuinely corrupts context state and requires a fresh context on next use.

### 1.2. Transactions and Test Data

Spring Framework provides transaction testing support via the TestContext Framework. When a test is annotated with `@Transactional`, Spring can run the test inside a test-managed transaction and roll it back afterward by default.

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAnAccount() {
        accountRepository.save(new Account("ACC-100"));

        assertThat(accountRepository.findByCode("ACC-100")).isPresent();
    }
}
```

Other supporting annotations include `@Commit`, `@Rollback`, `@BeforeTransaction`, `@AfterTransaction`, `@Sql`, and `@SqlConfig`. They help control data before, during, and after tests. For example, `@Sql` can run data-setup scripts; `@Commit` requests a commit instead of rollback when you need to confirm data persists after the transaction.

A key point to understand: rollback applies only to the transaction managed by the test. If the test sends an HTTP request to a server listening on a real port, the transaction handling the request usually belongs to the server's thread and transaction boundary. The test's transaction does not automatically wrap that transaction. Therefore, never conclude that all data created by a real-server test rolls back automatically simply because the test method carries `@Transactional`.

### 1.3. Web and HTTP Testing Tools

Spring Framework Test supplies tools for testing the web or HTTP layer without necessarily launching a real server:

| Tool | Usage Scope |
|---|---|
| `MockMvc` | Dispatches requests to Spring MVC's `DispatcherServlet` in a test environment, verifying status, headers, models, and response content. |
| `WebTestClient` | Fluent API for sending requests and checking responses; usable with WebFlux and matching MVC test setups. |
| `MockMvcWebTestClient` | Bridge to use the `WebTestClient` API when testing Spring MVC applications via MockMvc. |
| `MockRestServiceServer` | Simulates external HTTP service responses when testing code using `RestTemplate`. |

Example using `MockMvc`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void returnsOrderList() throws Exception {
        mockMvc.perform(get("/orders"))
                .andExpect(status().isOk());
    }
}
```

`MockMvc` belongs to Spring Framework Test. It is not a Spring Boot-exclusive feature. Boot can auto-configure `MockMvc` for tests via Boot annotations, yet the object and request-dispatching mechanism still come from the Spring Test ecosystem.

## 2. What Does Spring Boot Add to Testing?

Spring Boot Testing focuses on the experience of testing a **Spring Boot application**. Instead of requiring each test to wire individual Spring configurations manually, Boot leverages auto-configuration, application config discovery, and `SpringApplication` to construct an environment suited to the test's intent.

These APIs generally live in modules such as `spring-boot-test` and `spring-boot-test-autoconfigure`. When building Boot applications, the `spring-boot-starter-test` dependency is commonly used to pull popular testing libraries onto the test classpath at Boot-managed versions.

### 2.1. `@SpringBootTest`: Starting the Application via Boot Configuration

`@SpringBootTest` tells Spring Boot to create the test context through the application startup mechanism. Boot locates application configuration, applies auto-configuration, and loads application-declared beans. This is the right choice when the goal is verifying collaboration among many application components.

```java
@SpringBootTest
class OrderApplicationIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsAnOrderUsingApplicationConfiguration() {
        Order order = orderService.createOrder(new CreateOrderCommand("SKU-1", 2));

        assertThat(order.getItems()).hasSize(1);
    }
}
```

`@SpringBootTest` can run with several web modes:

| `webEnvironment` | Meaning |
|---|---|
| `MOCK` | Creates a simulated web application context; does not start a real HTTP server. This is the default mode. |
| `RANDOM_PORT` | Starts the server on a random port so tests send requests over real HTTP. |
| `DEFINED_PORT` | Starts the server on the configured port. |
| `NONE` | Creates an application context with no web environment. |

Example testing over a random port:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void exposesTheOrderEndpoint() {
        // Send HTTP requests to localhost and the port assigned to the test.
    }
}
```

`RANDOM_PORT` is useful when verifying an HTTP flow through a real server, including server settings and components running during a request. It consumes more resources and time than MockMvc tests. Also remember that server-side requests have their own transaction boundaries and do not automatically sit inside the test method's transaction.

### 2.2. Test Slices: Loading Only the Application Part Under Test

Not every test needs the entire application context. Spring Boot provides test slice annotations to restrict loaded configuration to a single functional area. This keeps tests focused and typically starts faster than `@SpringBootTest`.

| Annotation | Application Area Targeted |
|---|---|
| `@WebMvcTest` | Spring MVC layer, typically focusing on controllers, binding, validation, exception handling, and related MVC configuration. |
| `@DataJpaTest` | JPA components, entities, repositories, and related persistence configuration. |
| `@JdbcTest` | JDBC layer and JDBC-based data queries. |
| `@JsonTest` | JSON serialization and deserialization. |
| `@RestClientTest` | Components calling external REST services and related client configuration. |

Controller test example:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsBadRequestWhenInputIsInvalid() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` is a Spring Boot utility. It narrows the context to MVC configuration and selected components. `MockMvc` is injected thanks to Boot's auto-configuration, while `MockMvc` and the request/response assertion API remain part of Spring Framework Test. Controller business dependencies usually need to be mocked or explicitly imported because the slice does not load all services and repositories like the full application.

Similarly, `@DataJpaTest` focuses on persistence. This slice configuration typically runs tests in a transaction and rolls back afterward. When verifying behavior across multiple layers — such as an HTTP request traversing controller, service, and database — a standalone test slice may not suffice; consider `@SpringBootTest` or a well-scoped integration test.

### 2.3. Boot Auto-Configuration and Testing Utilities

Boot also provides annotations and helpers to configure test environments faster, for example:

- `@AutoConfigureMockMvc` configures MockMvc inside a Boot test context, often paired with `@SpringBootTest` when using a broader application context while still dispatching requests without opening a real HTTP port.
- `@TestConfiguration` declares supplementary configuration for tests. It can add test-purpose beans without making them normal application configuration.
- `@MockBean` and Boot's mock-bean utilities let you replace beans in the application context with mocks during tests. Use the exact API matching your project's Spring Boot version.
- `TestRestTemplate` assists in sending HTTP requests in Boot tests with a running server.
- Extensions and helpers such as `OutputCaptureExtension` support verifying output when appropriate.

Example combining a Boot context and MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationWebTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void respondsWithNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", 99999))
                .andExpect(status().isNotFound());
    }
}
```

In this example, `@SpringBootTest` governs how the application context is created; `@AutoConfigureMockMvc` is Boot's utility requesting MockMvc setup; and `MockMvc` performs requests and assertions using Spring Test's API.

## 3. Comparing Responsibility Boundaries

| Aspect | Spring Framework Testing | Spring Boot Testing |
|---|---|---|
| Primary goal | Provide testing infrastructure for Spring Framework and Spring components. | Make testing Spring Boot applications convenient and close to how the app boots. |
| Context creation | Specify Spring configuration via TestContext, such as `@ContextConfiguration`. | Boot using application configuration via `@SpringBootTest` and `SpringApplication`. |
| JUnit integration | `SpringExtension`, `@SpringJUnitConfig`, and TestContext Framework. | Boot annotations integrate with Spring Test; normally no need to declare `SpringExtension` manually when using `@SpringBootTest`. |
| Web testing | Supplies `MockMvc`, `WebTestClient`, `MockRestServiceServer`, and related APIs. | Auto-configures those tools for the application context or test slice. |
| Test transactions | Supplies `@Transactional`, rollback/commit, and SQL script support for tests. | Reuses Spring's transaction foundation while supplying slice configs for data tests. |
| Context scope | Test-specified, flexible from small configs to web contexts. | Can use the full application or a Boot-defined slice. |
| Dependencies | Usually requires `spring-test` plus a test engine and assertion/mocking libraries. | Usually uses `spring-boot-starter-test`, with dependency versions managed by Boot. |

A quick way to tell them apart is looking at the question an annotation answers:

- "From which configuration should a Spring `ApplicationContext` be loaded?" is a Spring Framework TestContext concern (`@ContextConfiguration`).
- "How should the Boot application start with main config and auto-configuration?" is a Spring Boot concern (`@SpringBootTest`).
- "How do I send requests and verify status/body without opening a real server?" can use `MockMvc` or `WebTestClient` from Spring Framework Test.
- "How do I have Boot auto-configure the MVC context and MockMvc for a controller test?" is a test slice and auto-configuration concern in Spring Boot (`@WebMvcTest`, `@AutoConfigureMockMvc`).

## 4. Choosing Tool Layers by Test Objective

Do not assume every test must use `@SpringBootTest`. Start from the behavior to verify and load a larger scope only when the test truly needs it.

| Objective | Usually Suitable Choice | Reason |
|---|---|---|
| Verify an algorithm or pure Java logic | JUnit and assertion/mocking libraries, no Spring context | Fast, minimal coupling to application configuration. |
| Verify beans and wiring of a specific Spring config | Spring TestContext with `@ContextConfiguration` or `@SpringJUnitConfig` | Precisely controls loaded configuration without bootstrapping Boot. |
| Verify a Spring MVC controller | `@WebMvcTest` and `MockMvc` | Focuses on MVC, avoiding unrelated layers. |
| Verify repositories/JPA | `@DataJpaTest` | Focuses on persistence and Boot's data configuration. |
| Verify integration of multiple beans and auto-configuration | `@SpringBootTest` | Needed to confirm components collaborate inside the app context. |
| Verify HTTP communication over a running server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Includes real server and request flow over the test's local network. |

Practical rule: use the smallest scope capable of proving the behavior under test. When a test slice does not load enough components, expand configuration deliberately or move to a broader integration test. Do not load the full context just to resolve a single dependency when a cleaner test setup works.

## 5. Dependencies and Versions

In a Spring Boot application, the common practice is declaring `spring-boot-starter-test` in test scope. This starter bundles Spring Test and popular testing libraries such as JUnit Jupiter, AssertJ, Mockito, and data assertion helpers. Exact components depend on the Boot version and project dependency configuration; inspect your build's dependency tree when you need to know precisely which libraries are included.

If an application uses Spring Framework without Spring Boot, declare `spring-test` alongside JUnit Jupiter and your chosen test libraries. When managing dependencies manually, keep Spring modules aligned on the same version line. In a Boot application, let Boot's dependency management govern versions rather than pinning `spring-test` to a different version.

Conceptual Gradle example:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

For non-Boot applications, test dependencies can start with `org.springframework:spring-test` and required JUnit/assertion libraries. `spring-boot-starter-test` is not a prerequisite for using Spring TestContext, `MockMvc`, or Spring Framework's transaction support.

## 6. Common Misconceptions

### Mistaking `MockMvc` for a Spring Boot-Only Tool

`MockMvc` is provided by Spring Framework Test. Spring Boot makes configuring and injecting it more convenient through `@WebMvcTest` or `@AutoConfigureMockMvc`. Hence, you can use MockMvc in a non-Boot Spring MVC application by assembling an appropriate web application context yourself.

### Assuming `@SpringBootTest` and `@ContextConfiguration` Have the Same Scope

`@ContextConfiguration` tells Spring Test which configuration to load. `@SpringBootTest` instructs Boot to bootstrap the application, usually pulling in auto-configuration and application settings. Both annotations can lead to a Spring context, yet their initialization path and configuration scope differ.

### Using Full Context for Every Test

A full context is useful when confirming application-wide integration. For a single controller or repository, test slices are usually more focused and start faster. Overusing full contexts inflates runtime and lets configuration issues in one area break tests meant to check another area.

### Thinking a `@Transactional` Test Always Rolls Back Every Operation

Spring's test transactions manage the transaction bound to the test. Requests sent through a real server typically run in the request's own transaction. Pick a cleanup strategy matched to the test type, especially when using `RANDOM_PORT` or `DEFINED_PORT`.

### Confusing the Starter with a Standalone Testing Framework

`spring-boot-starter-test` is primarily a dependency starter bringing required libraries onto the test classpath at Boot-managed versions. Test engines, assertion libraries, mocking libraries, and Spring Test remain distinct components with separate responsibilities.

### Copying Annotations from Examples Without Checking Versions

Testing annotations and utilities can change across Spring Framework/Spring Boot versions. When adapting examples, check your dependency versions and actual package imports. Avoid mixing a `spring-test` module from one version line with Spring Boot managed on another line.

## 7. Conclusion on Scope

Spring Framework Testing supplies the testing foundation: integrating test frameworks with Spring, managing test contexts, transactions, and web/HTTP tools like MockMvc. Spring Boot Testing adds Boot application bootstrapping, test auto-configuration, test slices, and Boot-specific helpers.

When reading a test, identify its three layers separately: foundational testing libraries like JUnit/Mockito, Spring Framework Test infrastructure, and Spring Boot Test utilities. Distinguishing these three layers helps pick the right dependencies, understand why the context is built the way it is, and decide on a test scope just large enough for the behavior to verify.
