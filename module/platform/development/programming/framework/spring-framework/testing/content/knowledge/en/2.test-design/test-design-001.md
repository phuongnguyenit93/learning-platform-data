# Choose an Observable Behavior as the Target

Designing a good test starts by identifying **what the system must do that its users or calling components can observe**. The target of the test is that behavior, not a method name, line count, or how the developer chose to implement it.

In a Spring application, a behavior can appear at many boundaries: an HTTP endpoint returning a response, a service applying business rules, a repository saving and querying data, a listener handling an event, or a component calling an external service. Choosing the right behavior and observation boundary keeps tests meaningful to system users while making them less brittle when internal structure changes.

## 1. What Is an Observable Behavior?

An observable behavior is the system's response to a specific condition and trigger. That response can be verified from outside the boundary under test.

For example, the requirement "a customer creates a valid order" is still quite broad. It can be expressed as a clearer behavior:

> When a customer sends a request to create an order with valid data, the API returns HTTP 201, provides the new order ID, and the order is created in the PENDING state.

This behavior specifies:

- **Initial condition:** the request contains valid data.
- **Trigger:** the customer sends a request to create an order.
- **Observable outcome:** an HTTP 201 response and the order ID.
- **Required state change:** the new order has the PENDING status.

A single behavior can have multiple pieces of observable evidence. A test may need to verify the status code, response body, and persisted data state because together they confirm one business outcome. What matters is that the assertions serve the same target.

### Types of Observable Outcomes

| Outcome type | Example in a Spring application | How to observe |
|---|---|---|
| Return value | Service calculates total order amount | Verify the returned value |
| Protocol response | Controller handles POST /orders | Verify HTTP status, headers, and JSON body with MockMvc |
| Data state | New order is saved with status PENDING | Query the repository or database after the operation |
| External side effect | System sends a payment request or publishes an event | Observe a fake gateway, test message broker, or event receiver |
| Error outcome | User lacks permission to access a resource | Verify HTTP 403 and confirm data remains unchanged |

Not every detail visible at runtime is an appropriate test target. Internal logs, variable names, private method names, the call count of a helper method, or the order of internal processing steps are usually implementation details. Make them targets only when they are part of a meaningful contract for users or integrating components.

## 2. Express the Target Using Condition, Trigger, and Outcome

A useful pattern is:

**Given** [initial condition], **when** [actor performs an action], **then** [observable outcome] must occur.

Examples:

- When an account is locked and a user submits a login request, the system rejects the login and returns an appropriate error.
- When a cart has at least one in-stock product and the customer confirms the order, the system creates an order in the awaiting-payment state.
- When the repository is asked to find a customer by email case-insensitively, the result returns the matching customer.
- When an unauthenticated user accesses a resource that requires authentication, the application rejects the request according to the security policy.

The target must be specific enough that the test author can determine the input data and expected outcome without guessing business rules.

### Identify Who Is Observing the Behavior

Identify which component consumes the result:

- **A user or API client** observes status codes, headers, response bodies, and displayed errors.
- **A service calling another service** observes return values or exceptions from the dependency.
- **A data access component** observes records saved, updated, deleted, or queried.
- **An integrating system** observes events, messages, or requests sent to external services.
- **An administrator or operations system** may observe metrics, health status, or logs when those are published operational requirements.

Identifying the observer helps pick the right test boundary. For example, a REST client does not care which private methods a controller calls. The client cares about the HTTP response and the business outcome the API promises.

### Distinguish Behavior from Implementation

The following two ways of describing a test do not have the same quality:

| Implementation-based description | Behavior-based description |
|---|---|
| Verify that createOrder calls repository.save | When a valid request is accepted, a new order is created and can be queried by order ID |
| Verify that controller calls service once | When a client sends a valid request, the endpoint returns a success response per the API contract |
| Verify that private method calculateFee returns 10 | When an order is in the standard delivery zone and not eligible for free shipping, shipping fee is calculated using the standard rate table |
| Verify that listener calls a specific helper | When receiving an order-paid event, the system updates the order status according to published rules |

The description on the right can still be tested by observing an internal interaction if that interaction itself is the contract between two components. However, the starting point is always the outcome the system must guarantee.

## 3. Process for Choosing a Behavior as the Target

### Step 1: Find a Meaningful Requirement or Rule

Start from a user story, acceptance criteria, business rule, API contract, or integration requirement. Find a statement describing what the system must guarantee.

Example requirement: "Only authenticated users with the ADMIN role may view the account list."

This is a testable rule. You do not need to start by hunting for controller or security methods in the code.

### Step 2: Choose the Observation Boundary

Determine where the outcome becomes meaningful to the consuming component:

- For an API, the boundary is usually an HTTP request/response.
- For business rules, the boundary may be a public method on a service.
- For data queries, the boundary is usually a repository interface.
- For event handling, the boundary may be an input event and an output state or message.

The boundary should be close enough to the requirement to verify the exact commitment, but should not expand to the entire application if the target belongs to a single component.

### Step 3: Describe the Initial State

State the data and preconditions needed before the action takes place. Include only conditions that affect the outcome.

Examples:

- The account exists, is active, and has the ADMIN role.
- Inventory has sufficient quantity for the ordered product.
- The email has not been registered yet.
- The order is in the PENDING state.

If the initial state is unclear, the same action can lead to multiple outcomes and the test target becomes ambiguous.

### Step 4: Identify the Triggering Action

Specify the action that makes the system react: calling an endpoint, invoking a public service method, saving an entity, publishing an event, or running a scheduled job.

Avoid describing the trigger as an internal implementation step such as "call helper A then call helper B." The test author needs to know what triggers the behavior from the consumer's perspective.

### Step 5: Choose Observable Evidence

Ask: After the action, what proves the requirement has been met?

It may be:

- A return value or object.
- Status code, headers, and response body.
- Data queryable after the operation.
- A message or event emitted.
- A prevented side effect, such as not creating a payment when an order is invalid.
- A specific error returned while system state remains preserved.

Choose the most direct evidence. If the target is that the API returns 403, there is no need to verify that a private method inside a security filter was called.

### Step 6: Split Distinct Outcomes into Separate Targets

One requirement often has multiple branches: valid, invalid, unauthorized, not found, limit exceeded, or dependency failure. When each branch has a different outcome, write separate targets.

Example for login:

1. Valid account and correct password: login succeeds.
2. Wrong password: login is rejected.
3. Locked account: login is rejected per account policy.

Splitting like this keeps test names descriptive of the behavior, keeps test data setup simple, and makes failures easy to locate.

## 4. Example: Choosing a Behavior for a REST Controller

Suppose an API has an order creation endpoint. Acceptance criteria state that valid data creates a new order and the client receives the order identifier.

Test target:

> When a client sends POST /api/orders with valid data, the endpoint returns HTTP 201, a Location header pointing to the new order, and a response body containing the order ID and status PENDING.

This target focuses on the HTTP contract used by the client. With Spring MVC, you can use @WebMvcTest and MockMvc to test the controller at the HTTP boundary:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsCreatedResponseWhenOrderRequestIsValid() throws Exception {
        given(orderService.create(any(CreateOrderRequest.class)))
                .willReturn(new OrderResponse("ord-42", "PENDING"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "cus-7",
                                  "productId": "prd-3",
                                  "quantity": 2
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/orders/ord-42"))
                .andExpect(jsonPath("$.id").value("ord-42"))
                .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
```

In this example:

- MockMvc dispatches the request through Spring MVC infrastructure without opening a real HTTP port.
- The service is replaced by a mock so the test focuses on request mapping, controller handling, and response formatting.
- The assertions verify what the client can observe: status, Location, and JSON body.

This is a controller contract test. Because the service is mocked, this test **does not prove** that data was persisted to the database. If the requirement also includes actually saving the order, another test target at the service/repository boundary or an integration test covering the order creation flow is needed.

Note: @MockitoBean is available in Spring Framework 6.2 and later. For projects on older Spring Boot versions, use the bean override mechanism appropriate for your project's version, such as @MockBean in supported versions.

### Split Error Behavior into a Separate Target

If order quantity must be greater than 0, that is a distinct behavior:

> When a client sends a request to create an order with quantity equal to 0, the API returns HTTP 400 with valid error details and does not create an order.

The corresponding test should verify the error response the client receives. If "does not create an order" is part of the guarantee, you must observe data state or use a test boundary broad enough to confirm no new order exists. Checking only status 400 is not enough to prove there was no side effect.

## 5. Example: Choosing a Behavior for a Repository

A repository may have its own contract, such as finding a customer by email case-insensitively.

Target:

> When the database has a customer with email Lan@example.com, querying with lan@EXAMPLE.com returns that customer.

With Spring Data JPA, @DataJpaTest is suitable for testing repository behavior alongside persistence configuration:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmailIgnoringCase() {
        customerRepository.saveAndFlush(
                new Customer("Lan@example.com"));

        var result = customerRepository
                .findByEmailIgnoreCase("lan@EXAMPLE.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
                .isEqualTo("Lan@example.com");
    }
}
```

Here, the evidence is the actual query result. Verifying that Spring Data creates a repository proxy or calls a specific internal method does not verify this query contract.

@DataJpaTest typically configures a database suitable for testing and runs each test inside a transaction that is rolled back after the test. If the application relies on behavior specific to the database engine used in production, test against the same database type—often via Testcontainers—so results reflect the real environment.

## 6. Choosing Test Scope in Spring

After identifying the behavior, choose the test type that can observe that behavior at a reasonable cost.

| Behavior to verify | Appropriate scope | Reason |
|---|---|---|
| Pure Java calculation rules or decisions | Unit test for class/service | Runs fast, focuses on inputs and outputs |
| HTTP status, headers, JSON, validation, or mapping | @WebMvcTest with MockMvc | Verifies the MVC contract without starting the full application |
| Queries, entity mapping, and persistence constraints | @DataJpaTest | Focuses on JPA and the database |
| Multiple beans collaborating via Spring configuration | @SpringBootTest | Verifies wiring and broader integration flows |
| Request handling through a real HTTP server | @SpringBootTest with appropriate web environment | Tests both the server and real HTTP communication |
| Endpoint security | @WebMvcTest or @SpringBootTest with security config | Observes access permissions via actual responses |

Do not default to @SpringBootTest for every behavior. If the target is only to check a pricing rule, starting the entire application context makes tests slow and makes failures harder to isolate. Conversely, if the target is to confirm multiple beans are configured and collaborate properly, a unit test with mocks can miss wiring bugs.

Choose the scope based on the boundary identified during design, not out of habit of using a single annotation for every test.

## 7. When to Assert State and When to Assert Interactions?

Asserting state or output is usually the most direct way to prove behavior:

- A service returns the right business result.
- A repository reads back data after saving.
- An API returns status and body according to contract.
- An order transitions from PENDING to PAID after successful payment.

Asserting interactions with a dependency is useful when that communication is part of the guarantee. For example, when an order is invalid, the system must not send a charge request. A mock can be used to verify the payment gateway receives no charge command.

```java
verify(paymentGateway, never()).charge(any());
```

This assertion is meaningful because calling the gateway can cause external side effects. Conversely, verifying that a service calls an internal helper exactly twice usually has no business meaning. If a developer changes the algorithm while keeping the result and integration guarantees intact, a test relying on helper call counts will fail even though the behavior remains correct.

A useful rule of thumb is: prefer observing outcomes; verify interactions when the communication boundary or external side effect is what must be guaranteed.

## 8. Common Mistakes When Choosing Targets

### Choosing a Method Name Instead of a Behavior

Names like testCreateOrder or testUpdateUser do not describe what must hold true. Clearer names are returnsCreatedResponseWhenOrderIsValid or rejectsLoginWhenAccountIsLocked. A test name should state the condition and observable outcome.

### Target Too Broad

"Test order management functionality" can cover create, update, cancel, pay, and search. When a failure occurs, a broad target makes it hard to tell which branch broke. Split by each behavior that has a distinct outcome.

### Asserting Only That No Exception Was Thrown

An operation running without throwing an exception does not guarantee it did the right thing. If the target is updating order status, verify the new status. If the target is an API returning an order, verify the response body.

### Verifying Only Mock Calls

A test may verify that repository.save was called yet still fail to prove the data was saved properly or the API returned the right content. Determine whether that interaction is the guarantee to verify or merely the current implementation.

### Testing Too Many Internal Details

Testing private methods, helper call order, or specific bean names couples the test to code structure. When structure changes, tests can break even when behavior has not changed. Move assertions to a public boundary or an outcome observable by consumers.

### Failing to Specify Initial Conditions

A test that creates arbitrary data and calls a service may not make clear why the expected result is right. Explicitly state the account, order, inventory, or user permission state before triggering the behavior.

### Claiming More Than the Test Scope Proves

A controller test with a mocked service does not prove the database updated. A repository test does not prove an endpoint returns the right status code. When reporting results, conclude only within the scope of the behavior and boundary the test actually observes.

## 9. Handling Asynchronous Behavior and External Side Effects

Some behaviors do not complete immediately within the initial call. For example, a controller publishes an event and a listener updates the order status afterward. When picking a target, specify the exact final outcome to observe and when that outcome is expected to appear.

For asynchronous processing:

- Identify the input event or message.
- Identify the required output state, event, or side effect.
- Wait on a condition with a bounded timeout instead of using a fixed Thread.sleep.
- Clarify behavior on message redelivery, duplicate handling, or temporary dependency failure if those are system requirements.

For example, the target may be: "When the listener receives a valid OrderPaid event, the corresponding order eventually transitions to PAID." The test must observe the final state or output event. Checking that the listener calls a helper method does not prove the state transitioned.

For external services such as payment gateways or email senders, calling the real service in every test is not necessary. You can use a mock or fake at the integration boundary to verify outgoing requests and application reactions. A separate integration test can verify real configuration or communication when needed.

## 10. Template for Writing the Target Before Coding a Test

Before creating a test method, write one behavioral statement following this template:

```text
When [initial state and condition],
and [actor performs action],
the system must [observable outcome].

Observation boundary: [API / service / repository / event / integration].
Evidence: [response / return value / persisted state / event / side effect].
```

Complete example:

```text
When the order is in PENDING state and the payment transaction is confirmed as successful,
and the listener processes the OrderPaid event,
the system must transition the order to PAID state.

Observation boundary: order state via repository.
Evidence: query the order back and receive status PAID.
```

From this description, the test author can prepare a PENDING order, trigger the listener with the appropriate event, and query the status. The test does not need to know which private methods the listener calls.

## 11. Questions to Clarify the Target

When a requirement is still vague, use these questions to clarify before writing tests:

1. Which component or user consumes this behavior?
2. Which initial state makes the behavior meaningful?
3. What action triggers the system?
4. What outcome can the observer perceive?
5. Which error outcomes or prevented side effects are also part of the requirement?
6. Which test boundary allows observing the outcome most directly?
7. Are there branches that produce a different outcome and require a separate target?

If you cannot answer "what must change or be returned after the action?", the target is not clear enough yet. Go back to the requirements, acceptance criteria, or integration contract to pin down the expected outcome.

## Conclusion

Choosing an observable behavior as the target means clearly defining the condition, action, and outcome that a consuming component can perceive. In a Spring application, that target determines the boundary to test and the right test type: unit test, @WebMvcTest, @DataJpaTest, or @SpringBootTest. When the target is expressed in concrete outcomes, tests are easier to read, easier to diagnose, and remain valuable when internal implementation changes.
