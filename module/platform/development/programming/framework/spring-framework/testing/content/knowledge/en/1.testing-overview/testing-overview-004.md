# Distinguishing Unit, Integration, and System Testing

In a Spring application, the same behavior can be verified at multiple scopes. For an order creation feature, you can test the total-calculation rule on its own, test the collaboration among controller, service, and repository, and test the customer journey of submitting a request and receiving a saved order.

Those three scopes are commonly called **unit testing**, **integration testing**, and **system testing**. They differ primarily in the boundary being tested, how many real components participate, and the environment the test needs to set up.

Do not classify a test solely by its test class name or a single annotation. A class using **@SpringBootTest** is not necessarily a system test; a class using **@WebMvcTest** is usually an MVC slice test; and a test that instantiates a service directly via its constructor can be a unit test even though the project uses Spring. Look at what the test is actually proving.

## 1. Three Scopes Viewed from the Test Boundary

Picture an order creation request flowing through the components:

~~~text
HTTP request
    |
    v
OrderController
    |
    v
OrderService ------> PaymentGateway
    |
    v
OrderRepository
    |
    v
Database
~~~

Each test type places its boundary at a different spot:

- **Unit tests** focus on a small unit, such as **OrderService**. Collaborators outside that unit are typically replaced with mocks, stubs, or fakes.
- **Integration tests** verify two or more real components collaborating across a boundary, such as a controller calling a service, a service working with a repository, or a repository querying a database.
- **System tests** verify the complete system in an environment close to how it is operated, based on inputs and observable outcomes at the system boundary. For web applications, a common realization is end-to-end (E2E) testing along user journeys.

The three scopes complement each other. Unit tests find local bugs quickly; integration tests catch wiring, configuration, and contract mismatches between components; system tests uncover issues that appear only when many layers of the system run together.

### Distinguishing System Tests and E2E

In practice, these two terms are often used almost synonymously, though they can be distinguished more precisely:

- **System testing** means testing the system as a complete product against requirements. Its scope may include API flows, background processing, batch jobs, authorization, recovery, or operational behaviors.
- **End-to-end testing** is a way of testing a flow from its starting point all the way to the final outcome. For web products, the flow typically starts at the UI or public API and traverses the necessary components to produce the result.

E2E is usually an important part of system testing. A test calling APIs directly can verify an end-to-end flow within backend scope, yet it does not cover browser UI or external systems outside the backend.

## 2. Unit Testing

### Objective and Scope

Unit tests verify the behavior of a small unit under controlled conditions. The unit may be a function, a method, a class, or a very small group with a cohesive responsibility. What matters is that the test boundary is narrow enough that when it fails, the faulty logic is easy to pinpoint.

For example, for **OrderService**, unit tests can verify:

- The order is rejected when the cart is empty.
- The total amount is calculated accurately when discounts apply.
- The order is not saved if payment is rejected.
- The order status transitions to **PAID** when the payment gateway confirms success.

In this test, **OrderService** is the real object. The repository and payment gateway are typically replaced with test doubles to control return values and observe calls.

### Example with JUnit 5 and Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void shouldNotSaveOrderWhenPaymentIsRejected() {
        var command = new CreateOrderCommand("customer-1", 250_000);

        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.rejected());

        var result = orderService.create(command);

        assertEquals(OrderStatus.PAYMENT_REJECTED, result.status());
        verify(orderRepository, never()).save(any());
    }
}
~~~

The data types in the example are illustrative models; constructor and method names should match your actual application.

Here:

- **OrderService** is instantiated and tested directly.
- **@Mock** creates simulated collaborators.
- **@InjectMocks** supplies the mocks to the service.
- **when(...).thenReturn(...)** defines the payment gateway's response.
- **verify(..., never())** asserts that the repository is not called when payment fails.

The test does not need to start a Spring ApplicationContext. It checks the service's logic in a lightweight environment, so it normally runs fast and yields focused failures.

### When to Use Unit Tests?

Use unit tests when verifying business rules, conditional branches, calculations, data transformations, input normalization, state transitions, and edge cases. Unit tests are also useful for verifying decisions to call or skip collaborators, and behavior when collaborators return faulty data, empty results, or throw exceptions.

You can deliberately construct each scenario without setting up a database, web server, or external service.

### Strengths and Limitations

**Strengths**

- Execution time is usually very short.
- Easy to construct input data for every case.
- Few environment dependencies, easy to repeat reliably.
- On failure, the scope of possible causes is narrow.
- Well suited for testing many edge cases.

**Limitations**

- Mocks do not prove that real components are compatible with one another.
- A test can stay green even when SQL queries, JPA mappings, or Spring configuration are broken.
- If mocks reach too deeply, the test may mirror the current implementation rather than the behavior users need.
- Unit tests do not prove the application can start up or accept HTTP requests successfully.

Do not try to turn every class into a unit test by mocking all dependencies. Mock boundaries outside the unit under test, while keeping collaborations that need verification real.

## 3. Integration Testing

### Objective and Scope

Integration tests verify that components collaborate properly. They focus on the boundaries where data, calls, or configuration pass from one component to another.

Examples:

- A controller receives JSON, passes data to a service, and returns the right HTTP status.
- A service calls a real repository and data is written and read accurately in the database.
- JPA entities map properly to tables and relationships.
- Spring configuration creates the right beans and injects the right dependencies.
- An adapter sends a properly formatted message to a test message broker.

Integration tests do not necessarily have to start the entire application. You can spin up just a Spring slice to verify a related group of components.

### Common Testing Levels in Spring

#### Testing the MVC Layer with @WebMvcTest

**@WebMvcTest** loads the MVC infrastructure and web components in the selected scope, typically a controller. It is suited for checking routing, binding, validation, serialization, HTTP status, and exception handling at the web layer.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void shouldReturnCreatedWhenOrderIsAccepted() throws Exception {
        when(orderService.create(any()))
                .thenReturn(OrderResponse.accepted("order-42"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 250000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("order-42"));
    }
}
~~~

**OrderController** and the MVC infrastructure are real Spring components in the test; **OrderService** is mocked so the test focuses on the controller's HTTP contract.

This is commonly called an **MVC slice test**. It serves as an integration test at the web-slice scope, though it does not prove that the service, repository, or database works correctly.

In Spring Boot 3.3, **@MockBean** is the common way to replace a bean in the ApplicationContext with a mock. On different Spring Boot versions, check the test API corresponding to the version in use.

#### Testing Repositories with @DataJpaTest

**@DataJpaTest** loads configuration and components needed for JPA, such as entities, repositories, and persistence infrastructure. It is suited for testing queries, mappings, relationships, constraints, and save/read operations.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrderByCustomerId() {
        var order = new Order("customer-1", 250_000);
        orderRepository.save(order);

        var results = orderRepository.findByCustomerId("customer-1");

        assertEquals(1, results.size());
        assertEquals("customer-1", results.get(0).getCustomerId());
    }
}
~~~

By default, **@DataJpaTest** typically uses an embedded database if one is on the classpath and runs tests inside a transaction rolled back after each test. This isolates data, yet also means the default environment may differ from the production database.

If the application runs on PostgreSQL or MySQL, consider testing against the exact database engine using Testcontainers. That way, tests can catch differences in data types, SQL dialects, constraints, and transactional behavior that embedded databases cannot reveal.

#### Integration Testing with Spring TestContext

Spring Framework provides the TestContext Framework to load an ApplicationContext for tests. With JUnit Jupiter, you can use **@SpringJUnitConfig** to combine Spring Test support with context configuration:

~~~java
@SpringJUnitConfig(TestApplicationConfig.class)
class PricingConfigurationTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void shouldUseConfiguredPricingPolicy() {
        var result = pricingService.calculate(100_000);

        assertEquals(100_000, result.total());
    }
}
~~~

**@SpringJUnitConfig** fits when you want to verify selected Spring configuration without loading the entire Spring Boot application. Context configuration can be declared via Java configuration or other suitable Spring configuration sources.

#### Multi-Layer Testing with @SpringBootTest

**@SpringBootTest** creates an ApplicationContext according to the Spring Boot application configuration. It fits when you need to verify many real beans collaborating, such as controllers, services, repositories, and persistence configuration.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderRepository orderRepository;

    @MockBean
    private PaymentGateway paymentGateway;

    @Test
    void shouldPersistOrderAfterSuccessfulPayment() throws Exception {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved("payment-7"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 250000
                                }
                                """))
                .andExpect(status().isCreated());

        assertEquals(1, orderRepository
                .findByCustomerId("customer-1").size());
    }
}
~~~

The test above keeps the controller, service, repository, and test-configured database real, while replacing the payment gateway with a mock. It verifies collaboration across multiple internal layers, making it an integration test.

**@SpringBootTest** does not by default mean starting a real HTTP server. When combined with **@AutoConfigureMockMvc**, requests flow through **MockMvc** in an MVC test environment. This remains useful for checking routing and the Spring MVC processing chain, yet does not test real HTTP network connections.

### Using Real Databases or Services in Integration Tests

An integration test may require a real database to verify persistence behavior. Testcontainers launches databases or dependent services inside test containers and supplies connection details to Spring.

Illustrative example with PostgreSQL:

~~~java
@Testcontainers
@DataJpaTest
class OrderRepositoryPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldPersistAndReadOrder() {
        var saved = orderRepository.save(
                new Order("customer-1", 250_000));

        var loaded = orderRepository.findById(saved.getId());

        assertTrue(loaded.isPresent());
    }
}
~~~

The snippet requires matching Testcontainers dependencies and the project's entity/repository configuration. It illustrates replacing an embedded database with real PostgreSQL within test scope.

A test using a real database can still be an integration test. Test type is determined by the boundary under test, not by whether containers are used.

### Strengths and Limitations

**Strengths**

- Catches wiring, configuration, and communication errors between beans.
- Verifies mappings, transactions, queries, and serialization in a more realistic environment than unit tests.
- Can test contracts between modules or adapters.
- Uncovers bugs that mocks cannot detect.

**Limitations**

- Runs slower than unit tests because it must create contexts, databases, or containers.
- May depend on network ports, Docker, machine resources, or test services.
- If data is not properly isolated and cleaned up, tests easily become order-dependent.
- When multiple layers participate, pinpointing the cause of failure can take longer.

Integration tests should stay measured in count and scope. Target boundaries with high integration risk precisely, rather than starting the whole system for every small business rule.

## 4. System Testing

### Objective and Scope

System tests verify that the complete system satisfies requirements when all necessary components operate together. The test observes behavior from the system's external boundary, such as a public HTTP API, a user interface, or a workflow entry point.

For order creation, a system/E2E flow could look like:

~~~text
Customer opens the order page
        |
        v
Enters details and confirms
        |
        v
Frontend sends HTTP request
        |
        v
Backend authenticates and processes
        |
        v
Database persists the order
        |
        v
System processes payment
        |
        v
Customer sees the order ID
~~~

The test focuses on the outcome the system delivers: a valid request creates an order, data is persisted properly, the appropriate status is returned, and the user can observe the expected outcome.

System tests usually aim to keep components within test scope real. If an external service must be replaced, document clearly which boundary is simulated. Substituting a third-party service can make sense due to cost, stability, or environment limits, yet the test then does not prove real integration with that service.

### Testing APIs Against a Live Server

Spring Boot can start an embedded server on a random port via **webEnvironment = RANDOM_PORT**. The test then sends HTTP requests through a client instead of calling **MockMvc**.

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiSystemTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void shouldCreateOrderThroughHttpEndpoint() {
        var request = new CreateOrderRequest("customer-1", 250_000);

        var response = http.postForEntity(
                "/api/orders",
                request,
                OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("customer-1", response.getBody().customerId());
    }
}
~~~

This test passes through the Spring Boot application's real HTTP server. If the database and required components are also backed by real services in the test environment, the verification scope becomes broader.

However, merely using **RANDOM_PORT** does not automatically turn a test into a system test. If critical dependencies remain mocked, or the test only checks an internal endpoint, its actual scope may still be an HTTP integration test. The test name does not decide the scope; the real components and journey exercised do.

### Testing User Journeys with a Browser

For products with a frontend, an E2E test typically uses browser automation tools like Playwright or Selenium:

1. Open the login page.
2. Sign in with a test account.
3. Open the order creation page.
4. Enter data and submit the form.
5. Check the success message and order ID.
6. Open order history to confirm the newly created order appears.

This test traverses many layers: UI, HTTP API, authentication, business logic, and persistence. It holds high value by simulating how users actually use the product, yet also has many potential failure points: browser, network, test data, wait timings, dependent services, and deployment environment.

### Strengths and Limitations

**Strengths**

- Verifies business flows from an external perspective.
- Catches collaboration errors that only surface when many parts of the system run together.
- Validates deployment configuration, authentication, routing, and real behavior through the UI or API.
- Provides evidence close to the user experience.

**Limitations**

- Usually the slowest and most resource-intensive of the three scopes.
- Hard to pinpoint the exact failing layer when a long flow breaks.
- Prone to flakiness if dependent on timing, networks, shared data, or external services.
- Difficult to cover every branch and edge case.
- High maintenance cost when the UI or workflow changes.

System/E2E tests should concentrate on critical, high-risk journeys: registration, login, checkout, order creation, authorization, or flows with major data impact. Small rules and numerous edge cases still belong in unit or integration tests.

## 5. Comparison Table

| Criterion | Unit Test | Integration Test | System Test / E2E |
|---|---|---|---|
| Primary question | Does one unit process its logic correctly? | Do related components collaborate properly? | Does the complete system meet requirements? |
| Scope | Function, class, or small unit | Multiple beans, modules, or adapters across a boundary | A whole system or end-to-end journey |
| Real components | The unit under test | Components within the integration boundary | Components required for the system flow |
| External dependencies | Usually mocks, stubs, or fakes | Can be real or deliberately simulated | Real or equivalent environment preferred |
| Typical Spring usage | JUnit 5, Mockito; no context needed | @WebMvcTest, @DataJpaTest, @SpringJUnitConfig, @SpringBootTest | @SpringBootTest(RANDOM_PORT), HTTP client, browser tools |
| Speed | Fastest | Moderate | Usually slowest |
| Fault isolation | High | Moderate | Lower |
| Environment risk | Low | Moderate | Higher |
| Example | Calculate shipping fee | Service persists data through real repository | User creates an order from UI through final outcome |

The cells in this table describe common tendencies, not absolute rules. An integration test running many containers can take longer than a small system test; a unit test overly coupled to the environment may no longer be lightweight.

## 6. Common Misconceptions

### Does Using @SpringBootTest Make It a System Test?

No. That annotation states that Spring Boot will create an ApplicationContext using the application configuration. It does not specify how many components or which journey the test verifies.

Examples:

- **@SpringBootTest** + mocked repository + checking a single service rule: the scope may still resemble a unit test with a context, though that setup is usually heavier than necessary.
- **@SpringBootTest** + real controller, service, repository, and database: typically a broad integration test.
- **@SpringBootTest(webEnvironment = RANDOM_PORT)** + HTTP client + real required dependencies: can serve as a backend system/API E2E test.

Classify tests based on their actual objective and boundary.

### Is Using MockMvc an HTTP E2E Test?

**MockMvc** executes the Spring MVC processing chain in a mock environment without sending requests over a network server listening on a real port. It is great for testing routing, filters, argument binding, validation, controller advice, and responses.

When you need to verify the embedded server, network ports, and HTTP clients, use **RANDOM_PORT** with **TestRestTemplate**, **WebTestClient**, or an appropriate HTTP client. When you need to verify the user interface as well, test with browser automation.

### Can Integration Tests Use Mocks?

Yes. An integration test can keep the real database and repository while mocking an external payment gateway. It then verifies integration among internal components while isolating the payment service.

What needs to be clear is which boundary the test is verifying. If the goal is to test the payment adapter itself, mocking that adapter defeats the test's value. If the goal is to verify the internal order creation flow without depending on the payment provider, mocking the payment gateway can be reasonable.

### Does Using Testcontainers Turn a Test into a System Test?

No. Testcontainers simply provides real dependent services in containers so tests run in a more realistic environment. A **@DataJpaTest** using a PostgreSQL container is still a repository integration test. Scope is determined by the behavior and boundary being verified.

### Do Unit Tests Need a Spring Context?

Usually not. If the goal is to test a single class's logic, instantiating objects directly via constructors is generally simpler, faster, and clearer. Load a Spring Context only when Spring configuration or wiring mechanisms themselves lie within the scope to verify.

## 7. Choosing Test Scope for a Change

You can choose test scope according to risk and the question you need answered.

| Change | Priority Testing | Reason |
|---|---|---|
| Add a pricing calculation rule | Unit test | Many logic branches, needs fast verification of each case |
| Fix how service handles repository errors | Unit test and integration test | Unit tests decisions; integration verifies repository/transaction behavior |
| Add a REST endpoint | MVC slice test | Verifies routing, binding, validation, and HTTP response |
| Change JPA mapping or query | Repository integration test | Needs a database to verify actual SQL and mappings |
| Change transactions spanning multiple repositories | Integration test | Needs to verify commit, rollback, and consistency |
| Change security configuration | Integration tests and selected system tests | Needs to test filters, authentication, authorization, and access flows |
| Change payment flow | Unit, integration, and selective E2E | Each scope verifies a distinct slice of risk |
| Change purchase journey UI | System/E2E test | Needs to verify users can complete the journey |

A practical workflow can be:

1. Write unit tests for new logic and edge cases.
2. Write integration tests for changed boundaries, such as MVC, persistence, or messaging.
3. Run a handful of system/E2E tests for affected critical journeys.
4. When tests fail, use the narrowest possible scope to isolate the bug; then re-verify the broader flow.

Not every change needs all three test types. A pure calculation change may only need unit tests. A migration or query change needs integration tests. A login flow change may also need system tests to verify end-to-end behavior.

## 8. How to Determine a Test's Scope Yourself

When inspecting an existing test class, answer these questions in order:

**1. What is the primary target being verified?**

If it is a class or small logic unit, the test leans toward a unit test. If it is collaboration across beans, repositories, or adapters, it leans toward an integration test. If it is the system viewed from outside, it leans toward a system test.

**2. Which components are real?**

List which controllers, services, repositories, databases, message brokers, HTTP servers, and external services are real versus simulated. This tells you what the test can prove.

**3. Which boundaries does the test cross?**

Calling a Java method directly differs from sending an HTTP request. Calling a repository with an embedded database differs from testing the system via a browser. The closer the boundary is to real operation, the wider the test scope.

**4. If the test is green, what can we conclude?**

For instance, a passing service unit test only proves service logic against the configured mock responses. It does not prove the database can save data. A passing repository integration test proves queries work against the test database, but not that the frontend calls the right API. A passing E2E test provides evidence for the executed journey, but not that every business branch is correct.

**5. If the test is red, where can we isolate the cause?**

If a unit test fails, inspect the unit's logic and input data. If an integration test fails, inspect component contracts, configuration, transactions, or dependent environments. If an E2E test fails, check logs and traces across each layer before concluding the bug lies in the UI or backend.

Asking these questions avoids labeling tests by gut feeling. A test may sit at the intersection of two scopes; describe accurately what it checks rather than forcing it into a single label.

## 9. A Balanced Testing Strategy in a Spring Application

A solid test suite typically has many unit tests, enough integration tests to guard key boundaries, and a smaller set of system/E2E tests for high-value journeys. This layout is commonly illustrated as the **test pyramid**:

~~~text
          [E2E]             Fewer, slower
      [Integration]         Enough for key boundaries
       [Unit tests]         More, fast feedback
~~~

This is guidance on cost and feedback speed, not a mandatory percentage split. A system with complex integrations may need a higher share of integration tests. What matters is that each test protects a specific risk without repeating the exact same evidence excessively.

When designing a test suite for a Spring application:

- Keep business logic framework-independent when possible so unit tests do not need to start a context.
- Use Spring slice tests when verifying a specific framework layer such as MVC or JPA.
- Use **@SpringBootTest** when verifying configuration and collaboration among many beans in the application.
- Use compatible databases or containers when risks involve SQL, transactions, or infrastructure services.
- Use a real server and HTTP client when verifying HTTP communication.
- Use browser automation for a select set of critical user journeys.
- Isolate test data, manage container lifecycles, and clean up external state so tests stay repeatable.
- Avoid relying on fixed sleep durations; prefer waiting on observable conditions or state.
- Keep failure diagnostics clear enough to identify which step in the flow failed.

## 10. Conclusion on Scope and Evidence

The three test types answer three different questions:

- Unit test: **is the logic of the unit under test correct?**
- Integration test: **do components across the chosen boundary collaborate properly?**
- System test: **does the complete system produce the outcome required?**

In Spring, JUnit and Mockito typically support unit tests; Spring TestContext, **@WebMvcTest**, **@DataJpaTest**, and **@SpringBootTest** support multiple integration scopes; and **RANDOM_PORT**, HTTP clients, Testcontainers, and browser tools extend verification toward production-like runtime environments.

Choose scope from the risk to verify, make clear which components are real and which are simulated, and pick the appropriate annotations or tools. Once you understand what evidence a test generates, you will know which tests to write, which ones are missing, and just how far a green result lets you conclude.

