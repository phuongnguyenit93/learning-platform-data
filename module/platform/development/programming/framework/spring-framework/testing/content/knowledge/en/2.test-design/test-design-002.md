# Structure of Arrange, Act, and Assert

A good test should tell the reader three things: what state the system is placed into, what action is being tested, and what evidence proves the expected behavior occurred. In Spring Framework Testing, these three parts are usually organized using the **Arrange – Act – Assert (AAA)** pattern, corresponding to **Given – When – Then**:

1. **Arrange (Given):** create data, configure the initial state, and set up necessary collaborators.
2. **Act (When):** invoke the action under test.
3. **Assert (Then):** verify the observable outcome and any side effects meaningful to the component's contract.

Spring adds an important layer of preparation: the test environment may need to initialize part or all of an `ApplicationContext`, create beans, apply configuration, and wire components together. Therefore, authors should distinguish **preparing the Spring environment** from **preparing scenario-specific data**. When these two concerns are organized cleanly, tests are both easy to read and less coupled to hidden state.

## 1. Overall Structure of a Test

A test method typically has the following shape:

~~~java
@Test
void createsOrderWhenRequestIsValid() {
    // Arrange: prepare input state and collaborators.
    CreateOrderCommand command = validCommand();

    // Act: perform the exact action under test.
    Order result = orderService.create(command);

    // Assert: verify the outcome observable by the caller.
    assertEquals(OrderStatus.CREATED, result.status());
    assertEquals(command.customerId(), result.customerId());
}
~~~

This is a conceptual structure; class names and data types in the example can be replaced with the application's models. What matters is that the three parts have clear boundaries:

- The Arrange section does not invoke the scenario's primary action.
- The Act section does not contain a series of checks or data setup operations.
- The Assert section focuses on outcomes and side effects directly tied to the behavior being described.

Not every test has just one statement per section. A scenario may need multiple setup steps and multiple assertions. However, there should normally be only **one primary action**. If a test method performs multiple independent actions, readers struggle to identify which behavior failed and which outcome is the focus.

### AAA and Given – When – Then

Both terms express the same structure:

| AAA | Given – When – Then | Question to answer |
|---|---|---|
| Arrange | Given | What are the initial conditions and data? |
| Act | When | What did the user or component under test do? |
| Assert | Then | What must the observable behavior be? |

AAA is often useful when structuring Java code. Given – When – Then is often useful when expressing business scenarios or test names. You can combine both: name the test after the expected outcome, then divide the method body into the three AAA blocks.

Good test names typically describe the condition and outcome:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

When testing exceptions, the action and assertion often share the `assertThrows` expression because the assertion needs to execute the lambda to catch the exception. Conceptually, the setup remains separate from the execution and assertion.

## 2. Arrange: Setting Up the Right Initial Conditions

The Arrange section defines which situation the test describes. A good Arrange section answers:

- Which component is the subject under test?
- What input data does it receive?
- What is the system's initial state?
- Which dependencies are real, mocked, or replaced?
- What Spring configuration is required to run the scenario?

### 2.1. Prepare Clear and Minimal Data

Create only the data needed for the behavior under test. If a test verifies order creation, prepare a valid customer, product, and required quantity. Avoid creating unrelated objects because they increase reading overhead and can introduce unrelated failure causes.

You can use factory helpers with descriptive names:

~~~java
private CreateOrderCommand validCommand() {
    return new CreateOrderCommand("customer-01", "product-01", 2);
}

private CreateOrderCommand commandWithQuantity(int quantity) {
    return new CreateOrderCommand("customer-01", "product-01", quantity);
}
~~~

Helper names should describe the data created rather than hiding too much behavior. When a scenario needs a special value, make that difference visible right inside the test:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

Avoid an overly generic fixture with many boolean parameters such as `createOrder(true, false, true)`. Readers have to open the implementation to understand the state. Prefer builders or meaningfully named helpers, such as `anOrder().withCancelledStatus().build()`, when the data model has many fields.

### 2.2. Keep Test Data Deterministic

Test results must be repeatable. Common sources of non-determinism include:

- Current time read directly from the system clock.
- Random numbers or randomly generated identifiers.
- Shared data left over from a previous test.
- Test execution order or database row order.
- External services changing state or returning network-dependent results.

If business logic depends on time, inject a `Clock` into the component under test and supply a fixed clock in the test. If random data is needed, use a fixed seed or construct concrete data for the scenario. If querying multiple records, sort by an explicit criterion instead of relying on implicit database ordering.

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

A fixed clock lets tests verify expiration dates, creation timestamps, or time-based rules without depending on the test machine's system clock.

### 2.3. Prepare the System Under Test and Dependencies

The object under test is often called the **SUT (System Under Test)**. Distinguish the SUT from its collaborators:

- **Real dependency:** suitable when the goal is to verify real collaboration between components.
- **Mock:** suitable when you need to control responses or verify an interaction that belongs to the contract.
- **Stub:** provides fixed return data without necessarily verifying interactions.
- **Fake:** a simplified implementation with working behavior at the required level, such as an in-memory store.

Do not mock everything by habit. When testing a service alongside a real repository against a test database, mocking the repository can prevent the test from catching mapping, query, or transaction boundary bugs. Conversely, when testing service rules in isolation, mocking an external payment gateway keeps the scenario independent of networks and live accounts.

With Mockito, preparing responses can look like this:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockBean
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        // Arrange
        CheckoutCommand command = validCheckoutCommand();
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted("payment-01"));

        // Act
        CheckoutResult result = checkoutService.checkout(command);

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
        then(paymentGateway).should()
            .charge(any(PaymentRequest.class));
    }
}
~~~

The example assumes the application defines `CheckoutService`, `PaymentGateway`, and corresponding data types. `@MockBean` replaces the `PaymentGateway` bean in the context with a mock so Spring still injects that dependency into the service. This works well when the test needs real Spring wiring while isolating an external gateway.

Verify interactions only when the interaction has business meaning or is a contract to protect. When the return value already proves the behavior, checking too many internal calls makes tests fragile during refactoring.

### 2.4. Prepare the Appropriate Spring ApplicationContext

Spring Test can create a context and inject beans into tests. Choose context scope based on the question under test:

| Configuration approach | Typical scope | When to choose |
|---|---|---|
| No Spring context, instantiate directly | A single class or independent rule | Pure Java logic, no DI or Spring config needed |
| `@SpringJUnitConfig` | A purposefully declared Spring context | Verify wiring or configuration of a small group of beans |
| `@SpringBootTest` | Spring Boot application context | Verify collaboration across many beans or near-production behavior |
| `@WebMvcTest` | Selected MVC layer | Test controllers, binding, validation, exception handlers, and HTTP responses |
| `@DataJpaTest` | JPA/repository components | Test mapping, queries, and persistence behavior |

Small context example:

~~~java
@SpringJUnitConfig(TestConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void calculatesPriceUsingConfiguredPolicy() {
        // Arrange, Act, Assert
    }
}
~~~

Full application test example:

~~~java
@SpringBootTest
class OrderWorkflowTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderAndPersistsIt() {
        // Arrange, Act, Assert
    }
}
~~~

`@SpringBootTest` is not automatically the best choice for every test. Starting a large context is slower, pulls in more configuration, and allows failures to originate from components outside the target scope. Using a small context speeds up tests and sharpens boundaries. Use the full context when the collaboration of application beans itself is what needs verification.

Spring TestContext caches the `ApplicationContext` across tests with equivalent configurations. Caching reduces startup time, but singleton beans in the context can retain state if a test mutates them. Therefore:

- Avoid storing scenario state in shared singleton beans.
- Restore configuration changes or mutable state if a test introduces them.
- Do not assume every test method always receives a brand-new context.
- Use `@DirtiesContext` only when a test truly leaves the context unsafe to reuse; this annotation invalidates the cache and can force subsequent tests to recreate the context.

### 2.5. Choose Test Slices When Only One Infrastructure Layer Is Needed

Test slices let Spring configure only part of the application. For example, `@WebMvcTest` focuses on the web layer:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsCreatedWhenOrderIsAccepted() throws Exception {
        // Arrange
        given(orderService.create(any(CreateOrderRequest.class)))
            .willReturn(new OrderResponse("order-01"));

        // Act + Assert
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"product-01","quantity":2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("order-01"));
    }
}
~~~

The example assumes the controller accepts JSON and returns a response with an `id` field. `MockMvc` dispatches requests through the MVC processing chain in a test environment, allowing you to test routing, JSON conversion, validation, status, and response without opening a real HTTP port.

For repositories, `@DataJpaTest` focuses on persistence:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        // Arrange
        Customer customer = customerRepository.save(
            new Customer("customer@example.test")
        );
        customerRepository.flush();

        // Act
        Optional<Customer> result =
            customerRepository.findByEmail("customer@example.test");

        // Assert
        assertTrue(result.isPresent());
        assertEquals(customer.getId(), result.orElseThrow().getId());
    }
}
~~~

`flush()` pushes changes down to the database within the current transaction. This is useful when you want constraint violations or SQL statements to execute at a predictable point rather than only late when the transaction finishes.

### 2.6. Organize Shared Setup at the Right Level

JUnit Jupiter provides `@BeforeEach`, `@AfterEach`, `@BeforeAll`, and `@AfterAll`:

- `@BeforeEach`: prepare parts that are genuinely identical for every test method.
- `@AfterEach`: release resources created specifically for a test method.
- `@BeforeAll`: prepare resources shared across the entire test class; methods must be `static` by default unless using `PER_CLASS` lifecycle.
- `@AfterAll`: release shared resources after the test class finishes.

Do not move all of Arrange into `@BeforeEach`. If each test has different data or state, place them inside the test method so the scenario is self-explanatory. Shared setup should hold only genuinely repeated parts and must not obscure critical conditions.

~~~java
class DiscountPolicyTest {

    private DiscountPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new DiscountPolicy();
    }

    @Test
    void appliesDiscountForEligibleCustomer() {
        // Scenario-specific data is placed right here.
    }

    @Test
    void doesNotApplyDiscountForIneligibleCustomer() {
        // This scenario declares its own distinct condition.
    }
}
~~~

In Spring-based tests, you do not need to recreate every bean in `@BeforeEach` if Spring already manages them. Let dependency injection handle wiring while each test method handles scenario data setup.

## 3. Act: Invoking the Exact Action Under Test

The Act section marks the transition from prepared state to the behavior under test. It should highlight one primary action, such as:

- Calling a service method.
- Sending an HTTP request via `MockMvc`.
- Calling a repository to run a query.
- Publishing an event or triggering an intentional operation.

Example:

~~~java
// Arrange
CreateOrderCommand command = validCommand();

// Act
Order result = orderService.create(command);

// Assert
assertEquals(OrderStatus.CREATED, result.status());
~~~

Avoid mixing data creation, mock stubbing, multiple service calls, and result verification in one undifferentiated block. When the Act section is short and clear, readers can immediately pinpoint the exact action that triggered a failure.

### 3.1. Call Through the Right Boundary Under Test

Choose the entry point matching the target:

- Testing a service: call a public method of the service.
- Testing a controller: send a request via `MockMvc` or an appropriate HTTP environment.
- Testing a repository: call actual repository methods.
- Testing configuration: retrieve beans from the context and verify the beans or configured behavior.

Do not call a private method directly just to test an internal branch. Verify behavior through the class's public API. If a private method holds logic complex enough to need standalone tests, that may indicate the logic should be extracted into a component with a clear responsibility.

### 3.2. Keep One Primary Action per Test

A test may execute multiple technical steps to trigger a single behavior, but it should not bundle multiple independent scenarios into one test method.

Hard-to-read example:

~~~java
@Test
void handlesSeveralOrderScenarios() {
    Order first = orderService.create(validCommand());
    orderService.cancel(first.getId());
    Order second = orderService.create(anotherValidCommand());
    orderService.confirm(second.getId());

    // Multiple assertions for different states.
}
~~~

This test has multiple actions and multiple outcomes. When it fails, it is hard to tell which behavior broke. Split it into separate tests describing order creation, cancellation, and confirmation. If you need to test a full business workflow, name the test after that workflow and treat the steps intentionally as an integration scenario.

### 3.3. Handling Asynchronous Actions

With asynchronous processing, the Act section may only initiate the work; the outcome appears later. Avoid using `Thread.sleep()` with an arbitrary wait time because tests become slow and flaky across machines.

Synchronize on a meaningful signal instead:

- Wait for a `Future` or `CompletableFuture` to complete.
- Use a latch or synchronization primitive designed for testing.
- Use a condition-waiting library such as Awaitility if already used by the project.
- Poll the final state through an observable API with a bounded timeout.

Conceptual example with `CompletableFuture`:

~~~java
// Arrange
JobCommand command = validJobCommand();

// Act
CompletableFuture<JobResult> future = jobService.submit(command);

// Assert
JobResult result = future.get(2, TimeUnit.SECONDS);
assertEquals(JobStatus.COMPLETED, result.status());
~~~

A finite timeout ensures the test terminates predictably if the task never completes. The timeout value should allow for the expected CI environment and must not be used to mask race conditions.

## 4. Assert: Checking the Evidence of Behavior

Assertions answer the question: what proves the behavior is correct? A test that runs to completion without assertions does not protect the expected behavior. Every test should have at least one meaningful assertion, except in rare cases verifying that an operation throws no exception—where an explicit assertion is still worth considering to make intent clear.

### 4.1. Asserting Return Values

For services or components returning data, verify the properties directly tied to the requirement:

~~~java
Order result = orderService.create(command);

assertEquals(OrderStatus.CREATED, result.status());
assertEquals(command.customerId(), result.customerId());
assertEquals(command.quantity(), result.quantity());
~~~

You do not need to assert every field if some are unrelated to the scenario. Too many purposeless assertions make tests hard to maintain and can cause unrelated changes to break tests.

### 4.2. Asserting State After the Action

For write operations, checking only the returned object is sometimes insufficient. If the goal is to confirm data was persisted, read it back across the persistence boundary:

~~~java
// Arrange
CreateOrderCommand command = validCommand();

// Act
Order created = orderService.create(command);

// Assert
Order stored = orderRepository.findById(created.getId())
    .orElseThrow();
assertEquals(OrderStatus.CREATED, stored.getStatus());
~~~

This checks collaboration between service and repository. If you only want to test service rules, you can replace the repository with a mock and verify the save call when that call is a contract to protect. Choose an assertion style matching the selected test scope.

### 4.3. Asserting Exceptions and Error Cases

JUnit Jupiter provides `assertThrows` to verify exceptions:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act
    InvalidOrderException exception = assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );

    // Assert
    assertEquals("Quantity must be positive", exception.getMessage());
}
~~~

Check the exception type when it is a required contract. Check the message when the message is part of the guarantee to callers; if the message is only an internal detail, prefer an error code or a more stable property. You can also verify that no data write occurred if that is part of the rule:

~~~java
assertThrows(
    InvalidOrderException.class,
    () -> orderService.create(command)
);

then(orderRepository).shouldHaveNoInteractions();
~~~

Asserting no interactions should be used only when not calling the repository is an important requirement. Avoid asserting that every non-call never happens, as that couples the test to the implementation.

### 4.4. Asserting Mock Interactions

Mockito lets you verify that a dependency was called:

~~~java
then(paymentGateway).should()
    .charge(argThat(request ->
        request.orderId().equals("order-01")
    ));
~~~

Verifying interactions is useful when:

- An outbound command to an external system is a key outcome.
- You need to guarantee an operation is called only when a condition is met.
- You need to check the data sent across an integration gateway.

Do not verify interactions merely because you know the current implementation calls a particular method. For instance, if the contract only requires returning the exact total amount, the test should assert the total amount; there is no need to verify how many times the service calls an internal helper.

### 4.5. Asserting HTTP Responses with MockMvc

For controllers, the HTTP response is natural evidence. You can verify status, headers, JSON content, and service interactions when needed:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"productId":"product-01","quantity":2}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.id").isNotEmpty());
~~~

Assertions should reflect the HTTP contract:

- Does the status code match the business outcome?
- Are important headers, such as `Location`, set?
- Does the JSON have the required structure and values?
- Is invalid input translated into the right error response?

If a controller accepts JSON, verify both content type and body. Calling a controller method directly bypasses much of MVC—such as argument resolvers, message converters, validation, and exception handlers—so doing so cannot replace an MVC test when those parts are in scope.

### 4.6. Using assertAll for Multiple Related Properties

JUnit Jupiter supports `assertAll` to run a group of independent assertions and report all failures:

~~~java
assertAll(
    () -> assertEquals(OrderStatus.CREATED, result.status()),
    () -> assertEquals("customer-01", result.customerId()),
    () -> assertEquals(2, result.quantity())
);
~~~

Group assertions that together describe a single outcome. Do not use `assertAll` to bundle independent behaviors that belong in separate tests.

## 5. Cleanup and Isolation Between Tests

Cleanup is usually not part of AAA, yet it is a precondition for runs not interfering with each other. Before adding manual cleanup, determine who manages each resource:

- Spring manages bean and context lifecycles.
- Spring Test manages test transactions when tests are configured as transactional.
- JUnit manages test instance lifecycles and lifecycle callbacks.
- Tests are responsible for releasing self-created resources such as temporary files, sockets, servers, or containers.

### 5.1. Transaction Rollback in Spring Test

Tests using `@Transactional` with Spring Test typically run inside a framework-managed transaction and roll back after each test by default. `@DataJpaTest` also usually includes transactional tests with rollback by default. This prevents one test's data from leaking into the next test.

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void savesProduct() {
        Product product = productRepository.save(new Product("Keyboard"));
        productRepository.flush();

        assertTrue(productRepository.findById(product.getId()).isPresent());
    }
}
~~~

Do not treat rollback as a universal cleanup mechanism for every side effect. The following cases may run outside the test transaction or fail to roll back as expected:

- Work running on another thread.
- Asynchronous tasks processed after the test transaction ends.
- Separately created transactions, such as `REQUIRES_NEW` propagation.
- Data written to an external system.
- Tests marked with `@Commit` or `@Rollback(false)`.

When tests involve these cases, use a dedicated isolation strategy, such as data with unique identifiers and explicit cleanup operations.

### 5.2. Avoid Execution Order Dependencies

Each test must create the state it needs. Do not allow test B to pass only after test A because test A created data or mutated a bean. Results must stay consistent whether running a single test, the whole class, tests in parallel, or re-running after a failure.

Ways to preserve independence:

- Use dedicated data for each test.
- Avoid mutable static variables shared across test methods.
- Do not rely on database row order without an `ORDER BY`.
- Reset mocks and mutable state at the proper lifecycle point.
- Use transaction rollback when appropriate.
- Clean up non-transactional resources in `@AfterEach` or an appropriate management mechanism.

## 6. Putting the Three Parts Together in Common Spring Test Types

The three phases—Arrange – Act – Assert—do not change across test types. What changes is how the environment is prepared and where execution occurs.

### 6.1. Unit Tests for Standalone Logic

When a class does not need a Spring container, instantiate the SUT directly. Tests are typically fast, easy to control, and need no Spring annotations:

~~~java
class TaxCalculatorTest {

    private TaxCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new TaxCalculator();
    }

    @Test
    void calculatesTaxFromNetAmount() {
        // Arrange
        BigDecimal netAmount = new BigDecimal("100.00");

        // Act
        BigDecimal tax = calculator.calculate(netAmount);

        // Assert
        assertEquals(new BigDecimal("10.00"), tax);
    }
}
~~~

Unit tests suit verifying calculations, validation rules, data transformations, or pure business decisions. Do not use `@SpringBootTest` if the test is not testing Spring.

### 6.2. Integration Tests for Services and Beans

When you need to confirm Spring injects the right beans and components collaborate, use an appropriate context. You can mock an external dependency so the test does not call a real service:

~~~java
@SpringBootTest
class RegistrationServiceIntegrationTest {

    @Autowired
    private RegistrationService registrationService;

    @MockBean
    private EmailSender emailSender;

    @Test
    void registersUserAndRequestsWelcomeEmail() {
        // Arrange
        RegistrationCommand command = validRegistrationCommand();
        given(emailSender.send(any(EmailMessage.class)))
            .willReturn(SendResult.accepted());

        // Act
        RegistrationResult result = registrationService.register(command);

        // Assert
        assertEquals(RegistrationStatus.REGISTERED, result.status());
        then(emailSender).should()
            .send(any(EmailMessage.class));
    }
}
~~~

This test verifies the service inside a Spring context and its interaction with a mocked bean. If the target also covers actually sending emails through real infrastructure, write a separate integration test against a test mail environment; mocks do not prove SMTP configuration or external services work.

### 6.3. MVC Tests for Requests and Responses

`@WebMvcTest` prepares the web layer and related MVC components. Services are usually mocked so the test focuses on the HTTP contract. Act is sending the request through `MockMvc`; Assert is checking the response.

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CustomerService customerService;

    @Test
    void returnsBadRequestWhenEmailIsInvalid() throws Exception {
        // Arrange: no service stubbing needed if validation blocks the request.

        // Act + Assert
        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"invalid"}
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

When testing validation, ensure the request goes through actual MVC validation and the DTO has proper constraints. When testing service logic, call the service directly or via a service context instead of making controller tests carry business logic.

### 6.4. Repository Tests for Persistence

`@DataJpaTest` is suitable for testing repositories, entity mappings, queries, and database constraints. Verify results via the repository or database after execution rather than checking only in-memory objects:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void findsAccountByAccountNumber() {
        // Arrange
        Account account = accountRepository.save(
            new Account("ACC-100")
        );
        accountRepository.flush();

        // Act
        Optional<Account> found =
            accountRepository.findByAccountNumber("ACC-100");

        // Assert
        assertTrue(found.isPresent());
        assertEquals(account.getId(), found.orElseThrow().getId());
    }
}
~~~

If queries rely on features specific to a database engine—such as dialect, collation, functions, or special constraints—ensure tests run against the matching database type. An embedded database may not faithfully reproduce production database behavior.

## 7. Organizing Test Classes So Readers Can Find Scenarios

A test class should be named after the component or behavior under test. Test method names should describe the condition and outcome. Example:

~~~java
class OrderServiceTest {

    @Test
    void createsOrderWhenCustomerIsActive() {
        // ...
    }

    @Test
    void rejectsOrderWhenCustomerIsSuspended() {
        // ...
    }

    @Test
    void rejectsOrderWhenQuantityIsNotPositive() {
        // ...
    }
}
~~~

When many scenarios share a grouping, JUnit Jupiter `@Nested` can organize them by context:

~~~java
class OrderServiceTest {

    @Nested
    class WhenCustomerIsActive {

        @Test
        void createsOrderForValidCommand() {
            // ...
        }
    }

    @Nested
    class WhenCustomerIsSuspended {

        @Test
        void rejectsNewOrder() {
            // ...
        }
    }
}
~~~

`@Nested` can make test structure easier to read, though it is not needed for every class. When there are only a few simple tests, flat methods are often easier to find.

For data cases testing the same rule, `@ParameterizedTest` helps avoid repetition:

~~~java
@ParameterizedTest
@ValueSource(ints = {0, -1, -10})
void rejectsNonPositiveQuantity(int quantity) {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(quantity);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

Parameterized tests fit when different inputs test the same behavior and share the same verification logic. When individual cases have different business meanings or outcomes, separate tests with clear names can be easier to understand.

## 8. Organizational Patterns That Make Tests Untrustworthy

### 8.1. Preparing Too Much Data

A test verifies a single rule yet constructs many unrelated objects. When fixture data is complex, readers struggle to see which condition actually drives the outcome. Keep fixtures minimal and highlight what distinguishes the scenario.

### 8.2. Hiding Critical Conditions in Shared Setup

If `@BeforeEach` silently creates a verified customer, enables a feature flag, and configures admin roles, the test name fails to show which condition produced the outcome. Move scenario-specific data into the test method or use precisely named helpers.

### 8.3. One Test Executing Many Independent Behaviors

When one test creates, updates, cancels, and queries multiple objects, the first failure can mask the remaining behaviors. Split by behavior unless the test's goal is verifying a complete end-to-end integration workflow.

### 8.4. Missing Meaningful Assertions

A test that merely calls a method and returns proves nothing about the outcome. Assert return values, persisted state, HTTP responses, exceptions, or significant interactions.

### 8.5. Over-Mocking

If every dependency is mocked, the test may only prove that mocks were called according to a scripted scenario. Keep components within the target scope real and replace only the boundaries that need isolation.

### 8.6. Using `@SpringBootTest` for Every Test

Large contexts slow feedback loops and make configuration errors harder to pinpoint. Use a full context only when verifying application-level collaboration. For pure logic, instantiate objects directly; for MVC or JPA, consider test slices.

### 8.7. Relying on Order or Arbitrary Timing

Tests that depend on other tests, use `Thread.sleep()`, or read the system clock directly tend to fail intermittently. Create isolated state, use a controllable clock, and wait on conditions with timeouts.

### 8.8. Cleanup Altering the State Under Assertion

Do not delete data before assertions read back the state under verification. Assert behavior first, then release resources. With transaction rollback, understand rollback boundaries before skipping manual cleanup.

## 9. How to Read a Failing Test

When a test fails, read it in the order of the three sections:

1. **Arrange:** do the data and configuration truly establish the condition described by the test name?
2. **Act:** does the test call the right entry point and trigger only the intended behavior?
3. **Assert:** does the checked evidence match the contract being protected?

Then classify the failure:

- **Setup failure:** context fails to start, missing bean, misconfigured test, or unexpectedly invalid input data.
- **Execution failure:** action throws an unexpected exception, calls the wrong dependency, or fails to complete.
- **Assertion failure:** behavior runs but the outcome differs from expectations.
- **Isolation failure:** test fails only when run with the class or full suite, usually related to shared state, transactions, ordering, or external resources.

For context startup failures, inspect the root cause in the exception chain instead of reading only Spring's top-level message. For persistence failures, check whether operations were flushed and which transaction wraps the test. For async tests, check completion signals and timeouts. For failures appearing only in full suite runs, re-run the test individually and check shared data or bean state.

## 10. Reusable Structure Template

For a typical test method, you can start from this skeleton:

~~~java
@Test
void describesExpectedBehaviorUnderCondition() {
    // Arrange
    // 1. Create minimal input data.
    // 2. Set up initial state.
    // 3. Configure mocks/fakes if needed.

    // Act
    // Invoke one primary action through the API under test.

    // Assert
    // Verify observable outcomes or side effects.
}
~~~

When using a Spring context, environment configuration stays at the class level:

~~~java
@SpringBootTest
class SomeServiceIntegrationTest {

    @Autowired
    private SomeService someService;

    @MockBean
    private ExternalGateway externalGateway;

    @Test
    void performsExpectedBehavior() {
        // Arrange: scenario-specific data.
        // Act: call someService.
        // Assert: check outcomes and required interactions.
    }
}
~~~

Before finalizing a test, ask these design questions:

- Does the test name describe the condition and expected outcome?
- Is the prepared data minimal, meaningful, and repeatable?
- Does the Spring context scope fit the verification target?
- Is the test calling the right public boundary to protect?
- Do the assertions prove an observable behavior?
- Do mocks replace only dependencies that need isolation?
- Can the test run independently without order dependencies?
- Does transaction handling or cleanup properly handle resources the test creates?

## Conclusion

A maintainable Spring test starts with clear initial conditions, performs one deliberate action, and finishes with concrete evidence. Spring Test offers several ways to prepare the environment, from direct instantiation and small contexts to full application contexts and test slices. Choosing the right scope gives fast feedback, isolates the right boundary, and verifies the exact behavior the test claims to protect.
