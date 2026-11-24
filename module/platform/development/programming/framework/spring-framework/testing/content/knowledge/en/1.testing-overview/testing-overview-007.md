# From Behavioral Requirements to Success and Failure Scenarios

Spring Framework testing is valuable when each test proves a behavior that a user, an integrating system, or another component can observe. To achieve this, the test author must start from a behavioral requirement, identify initial state and input data, and specify both expected outcomes and what the system must reject or leave untouched on error.

Annotations such as **@SpringBootTest**, **@WebMvcTest**, or **@DataJpaTest** only select the environment in which tests run. They do not automatically produce a good set of scenarios. A test class can start a full Spring context and still miss critical cases if the requirement has not been turned into concrete scenarios. Conversely, a small unit test can accurately prove a business rule without starting Spring.

The workflow in this lesson covers five steps: reading a requirement and identifying observable behavior; clarifying preconditions, data, rules, and outcomes; splitting the requirement into success, alternative, and failure scenarios; choosing the appropriate Spring test layer; and writing assertions that prove both the right outcome and the side effects that must not happen.

## 1. Start from Behavior, Not from Annotations

A behavioral requirement describes how the system should react to an actor or an event. For example:

> When a customer submits a valid order creation request and the product has enough stock, the system creates the order and deducts the corresponding inventory quantity.

This sentence describes a success flow, yet is not enough to build a test suite. We still need to know what counts as valid, when inventory is checked, what information the response contains, and how the system must preserve state if the order cannot be created.

A requirement can be broken down into the following elements:

| Element | Question to Answer | Example |
| --- | --- | --- |
| Actor | Who or what triggers the behavior? | Authenticated customer |
| Trigger | Which action starts processing? | Send POST to create an order |
| Precondition | What state must already exist? | Product exists and is active for sale |
| Input | What data is sent in? | Product ID, quantity |
| Rule | Which conditions govern the outcome? | Quantity from 1 to 10 and not exceeding stock |
| Success outcome | What does the caller observe? | Receives an order-created success response |
| State change | What data is created, updated, or deleted? | Order created and stock reduced |
| Failure outcome | How does the system respond when conditions are not met? | Rejects request with an appropriate error |
| Forbidden effect | What must never happen? | No partial order created, no stock deducted on rejection |

The last two rows are critical. A test that only checks that the API returns an error can still miss a severe bug if the system persisted partial data before returning the error. For state-mutating operations, verify both what happened and what must not happen.

### 1.1. Rewrite Requirements into Testable Statements

A useful behavioral statement typically takes this form:

**When** an actor performs an action with defined data and initial state, **then** the system produces an observable outcome and performs the committed state changes; if conditions are not met, the system returns an appropriate rejection result and leaves no unintended side effects.

What matters is that the test author can specify:

- Which data or state distinguishes one scenario from another.
- Which action is performed.
- Which result is observable from outside.
- Which state must change or remain unchanged.
- Which rule decides whether the scenario is accepted or rejected.

If a word in a requirement can be interpreted multiple ways — such as "fast", "valid", "authorized", "non-duplicate", or "safe retry" — record the ambiguity for the requirement owner to clarify. Do not pick one interpretation yourself and turn it into an official test criterion.

### 1.2. Distinguish Behavior from Implementation Details

Requirements usually state what the system must do, while source code decides how the system does it. Behavioral testing should prioritize the observable contract:

- Which status code and response body the API returns.
- Whether a record is created or not.
- How a balance, quantity, or business state changes.
- Which events or integration calls are emitted.
- Whether an unauthorized user is denied.

Do not make private method names, non-contractual function call order, or the structure of an implementation class the primary target of tests. When internal structure changes while behavior remains correct, behavioral tests should remain valid.

## 2. Turn Requirements into Acceptance Criteria

Acceptance criteria are specific conditions that determine whether a behavior has been satisfied. They form a bridge between business prose and test scenarios.

For example, "the order quantity must be valid" is still too vague. Clarify:

- Is quantity required?
- Must quantity be a positive integer?
- Is there a maximum limit per order?
- Is the maximum limit an input rule or dependent on stock?
- When invalid, what response does the API return?
- Do order and stock data remain unchanged?

Once the rules are confirmed, you can write criteria:

1. The request must include a product ID and a quantity.
2. Quantity must be an integer from 1 to 10.
3. The product must exist.
4. Stock must be greater than or equal to the requested quantity when the system confirms the order.
5. When all conditions are met, the system creates one order and reduces stock by the exact ordered quantity.
6. When any condition is not met, the system rejects the request and creates no partial business changes.

These criteria are clear enough to derive individual scenarios. They also reveal follow-up questions, such as how to handle two concurrent requests trying to buy the last remaining unit.

### 2.1. Using Given – When – Then

Given – When – Then is a way to express a scenario in three parts:

- **Given**: initial state and prepared conditions.
- **When**: the action under test.
- **Then**: observable outcome and state that must be preserved or changed.

Example for a success scenario:

**Given**

- Product P exists.
- Product P has 5 units in stock.
- No order has been created by this request yet.

**When**

- The customer submits a request to order 2 units of product P.

**Then**

- The system returns an order-created success result per the API contract.
- The new order contains product P and quantity 2.
- Remaining stock is 3 units.
- Exactly one order is created for this operation.

For a failure scenario, the Then section must state both the returned error and the unchanged state:

**Given**

- Product P exists but has only 1 unit left.

**When**

- The customer requests 2 units of product P.

**Then**

- The system rejects the request per the agreed error contract.
- No new order is created.
- Stock remains 1.

Given – When – Then does not have to be written in Gherkin files or executed with a BDD framework. First and foremost, it is a way of thinking and presenting scenarios so authors, testers, and reviewers understand a scenario identically.

### 2.2. Break Down Observable Criteria

A good criterion must have a way to be verified. Words like "correct", "valid", "successful", or "safe" must be turned into evidence:

| Vague Wording | Verifiable Wording |
| --- | --- |
| Order created successfully | Exactly one new order exists with the submitted product ID and quantity |
| Stock deducted accurately | Post-processing stock equals pre-processing stock minus accepted quantity |
| Data unaffected on error | Order record count and stock quantity remain unchanged |
| Unauthorized user blocked | API returns a denial per the security contract and executes no business operation |
| No duplicate processing | Specify duplicate-detection key, response outcome, and maximum allowed side effects |

If you cannot point to data that proves a criterion, the criterion may still be ambiguous or the system may need greater observability.

## 3. Build a Suite of Success and Failure Scenarios

One requirement usually spawns multiple scenarios. Do not write a single test for the happy path and treat that as adequate coverage.

### 3.1. Primary Success Scenario

This is the most common flow when all preconditions and rules are satisfied. Pick simple, clear data to prove the core behavior:

- The product exists.
- Quantity is within bounds.
- Stock is sufficient.
- The caller has permission.
- The system creates the order and updates stock.

Success scenarios should check key outcomes, not merely that no exception was thrown. For write operations, assert the post-processing state.

### 3.2. Alternative Success Scenarios

The success flow can take several input or initial-state forms:

- The user orders the minimum quantity.
- The user orders the exact maximum allowed quantity.
- The user selects another supported shipping method.
- An optional field is omitted and the system applies the documented default value.

Create separate scenarios only when the difference matters to the contract or rules. Do not duplicate tests for different data in the same equivalence class if it adds no new evidence.

### 3.3. Invalid Input Scenarios

These are cases where input fails format or bound checks:

- Missing required field.
- Null value when disallowed.
- String that cannot parse into the required data type.
- Quantity of 0 or negative.
- Value exceeding published limits.
- Malformed identifier.

At the web layer, these scenarios usually involve binding, validation, and HTTP error mapping. Verify the error body as well when the API commits to a stable error structure.

### 3.4. Business Rule Violation Scenarios

Input may be syntactically valid yet still rejected by business rules:

- Product does not exist.
- Product is discontinued.
- Insufficient stock.
- Account is ineligible to perform the action.
- Current state does not allow transitioning to the next state.

Do not lump these together into one generic "request fails" test. Each rule may carry a different response and different state-preservation requirements.

### 3.5. Boundary Scenarios

Boundary scenarios check behavior at the transition between two data classes. If valid quantities range from 1 to 10, the values to watch are:

- 0: just below the lower bound.
- 1: right at the lower bound.
- 10: right at the upper bound.
- 11: just above the upper bound.

Boundary testing frequently catches mistakes mixing up `<` and `<=`, rounding bugs, unit mismatches, or mishandled empty values.

Not every number needs its own test. Derive boundaries from confirmed rules, then pick representative values on both sides of each boundary.

### 3.6. State and Action-Ordering Scenarios

An action's outcome can depend on current state:

- An order can only be canceled while in a cancelable state.
- A locked account cannot log in successfully.
- An already-processed resource must not be processed a second time if business rules forbid it.

List valid states, allowed transitions, and forbidden transitions. For each important transition, create at least one accepted scenario and one rejected scenario.

If requirements involve concurrency, clearly define the invariant to protect. For instance, when only one item remains and two buy requests arrive concurrently, the system may have to guarantee at most one request succeeds. Add concurrency tests only when the business contract requires that behavior; do not invent contention policies yourself.

### 3.7. Dependency or Technical Failure Scenarios

A behavior may depend on a database, external service, queue, or storage system. When requirements specify behavior under dependency failures, test:

- Dependent service fails to respond.
- Connection refused or timed out.
- Malformed dependency data.
- Transaction rolled back.
- Event publishing failed or retried.

These scenarios must clarify whether the system should return an error, retry, save a pending state, or compensate. Do not invent retry counts, timeout durations, or fallback policies if requirements have not specified them.

## 4. Systematic Scenario-Discovery Techniques

Scenario design should not rely solely on memory. The techniques below help uncover critical cases while keeping the test suite focused.

### 4.1. Equivalence Partitioning

Divide inputs into groups where values in the same group are processed by the same rule. Then pick one or a few representative values per group.

For order quantities from 1 to 10:

| Partition | Representative Value | Expectation |
| --- | ---: | --- |
| Below lower bound | 0 | Rejected |
| Within valid range | 4 | Accepted if stock suffices |
| Above upper bound | 11 | Rejected |
| Missing value | null or omitted field | Rejected if field is required |
| Wrong data type | non-numeric string | Rejected during binding or validation |

Equivalence partitioning avoids testing hundreds of consecutive values when many represent the same rule.

### 4.2. Boundary Value Analysis

After identifying valid ranges, pick values just below, at, and just above each boundary. For the range 1 to 10, the set 0, 1, 10, and 11 generally yields stronger evidence than testing only a single middle value.

For dates/times, currency, or sizes, boundaries may depend on units and precision. Use the exact units defined by the contract and avoid floating-point comparisons that introduce unnecessary error.

### 4.3. Decision Tables

When outcomes depend on multiple conditions, a decision table prevents missing important combinations.

Example for order creation:

| Product Exists | Valid Quantity | Sufficient Stock | Outcome |
| --- | --- | --- | --- |
| Yes | Yes | Yes | Create order |
| No | Yes | N/A | Reject because product not found |
| Yes | No | Irrelevant | Reject due to invalid input |
| Yes | Yes | No | Reject due to insufficient stock |

This table shows that check order can affect which error is returned when multiple conditions fail simultaneously. If that order is part of the contract, document it explicitly. If not, avoid writing assertions coupled to an uncommitted internal check order.

### 4.4. State Transition Tables

For stateful workflows, list the initial state, action, target state, transition guard, and state to preserve when the action is rejected.

For example, if an order may only be canceled while PENDING, include one successful cancellation from PENDING and one rejected cancellation from a completed state. Actual states and responses must come from system requirements.

### 4.5. Controlled Combination of Conditions

When there are many input fields, testing every combination is unnecessary. Prioritize:

- Every rule is tested at least once.
- Combinations that can change the business outcome are tested.
- Interdependent conditions are tested together.
- High-risk areas such as permissions, money, inventory, and state transitions have dedicated evidence.

Pairwise techniques can reduce configuration combinations when many parameters are independent. However, they do not replace testing specific combinations explicitly defined by business rules.

## 5. End-to-End Walkthrough Example: Creating an Order

Suppose the order-creation API has the following illustrative contract:

- The request contains product ID and quantity.
- Quantity must be an integer from 1 to 10.
- The product must exist.
- Stock must be sufficient at confirmation time.
- On success, the system creates one order and reduces stock by the ordered quantity.
- When data is invalid, the product does not exist, or stock is insufficient, the system rejects the request and leaves no partial business changes.

HTTP codes in the example are illustrative choices for a REST API. A real project must follow its agreed API contract, including status codes and error body structure.

### 5.1. Scenario Matrix

| ID | Initial State and Input | Expected Result | What Must Stay Unchanged |
| --- | --- | --- | --- |
| ORD-01 | Product exists, stock is 5, order 2 | Order created successfully | No extra orders beyond the request's order |
| ORD-02 | Product exists, stock is 5, order 1 | Order created at lower bound | Stock decreases by exactly 1 |
| ORD-03 | Product exists, stock is 10, order 10 | Order created at upper bound | Stock drops to 0, never negative |
| ORD-04 | Quantity is 0 | Input rejected | No order created, stock unchanged |
| ORD-05 | Quantity is 11 | Input rejected | No order created, stock unchanged |
| ORD-06 | Missing product ID or quantity | Input rejected | No order created, stock unchanged |
| ORD-07 | Non-existent product ID | Rejected per resource-lookup rule | No order created |
| ORD-08 | Stock is 1, order 2 | Rejected due to insufficient stock | No order created, stock stays 1 |

This matrix is a starting set, not a fixed checklist for every system. If the API adds rules for pricing, promo codes, per-user limits, or product status, each rule needs corresponding scenarios.

### 5.2. Writing Concrete Success and Failure Criteria

For ORD-01:

- Given: product P exists and has 5 units in stock.
- When: submit an order creation request with product P and quantity 2.
- Then: response indicates the order was created; order record has the right product and quantity; order count increases by exactly one; remaining stock is 3.

For ORD-08:

- Given: product P exists with only 1 unit left.
- When: submit a request to order 2 units.
- Then: response indicates the request was rejected due to insufficient stock; order count does not increase; stock remains 1.

For ORD-04:

- Given: product P exists with sufficient stock.
- When: submit quantity 0.
- Then: response indicates a validation error per the contract; order-creation logic is not executed; order and stock data remain unchanged.

These three scenarios can traverse different test layers. ORD-04 primarily verifies the HTTP contract and validation. ORD-08 must prove the business rule. ORD-01 needs to verify multiple components collaborating and data persisted consistently.

## 6. Choosing the Test Layer in Spring

Spring offers several ways to set up a test environment. Pick the smallest layer that can fully prove the behavior under consideration. If a requirement spans multiple components, add integration tests at that exact boundary.

| Test Layer | Common Spring Tools | Suited to Prove |
| --- | --- | --- |
| Unit test | JUnit and Mockito, no Spring context started | Pure business rules, calculations, service decisions |
| Web slice | **@WebMvcTest** and MockMvc | HTTP mapping, binding, validation, response, and required web configuration |
| Data slice | **@DataJpaTest** | Entity mappings, repository queries, and data constraints |
| Application integration | **@SpringBootTest** with MockMvc or a matching client | Collaboration among controller, service, repository, configuration, and real beans |
| HTTP integration | **@SpringBootTest(webEnvironment = RANDOM_PORT)** with an HTTP client | Behavior through a running server, serialization, and real network boundaries |

### 6.1. Unit Tests for Business Rules

If a rule can be verified with a plain Java object, prefer unit tests. For example, a service deciding whether to accept an order quantity can be tested with JUnit and a mock for the data-access port.

Unit tests generally run fast, need no ApplicationContext, make creating inputs and testing many branches easy, and pinpoint which rule failed. Do not mock every object just to call a method. Keep value objects and pure logic real; replace only external dependencies that need control.

### 6.2. Web Slice with @WebMvcTest

**@WebMvcTest** focuses on the MVC layer, usually paired with MockMvc. This layer is suited to verify:

- URLs and HTTP methods map properly.
- JSON requests bind into DTOs.
- Bean Validation is applied.
- Validation errors are converted into contract-compliant responses.
- Responses have expected status, headers, and JSON body.
- Necessary web configurations such as security filters work within the slice.

Example DTO:

~~~java
public record CreateOrderRequest(
    @NotNull Long productId,
    @NotNull @Min(1) @Max(10) Integer quantity
) {}
~~~

Example controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
~~~

Example validation test:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void rejects_zero_quantity_before_calling_service() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": 10, "quantity": 0}
                    """))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orderService);
    }
}
~~~

This is an illustrative example; packages, response types, security configuration, and mock declarations must match the actual application. The key point is that the scenario confirms two things: the invalid request is rejected and the service does not receive a request that validation already eliminated.

Do not use **@WebMvcTest** to conclude that data was saved properly in the database. At this layer, the service is typically replaced with a test double, so the test only proves the web layer.

### 6.3. Data Slice with @DataJpaTest

**@DataJpaTest** is suited for testing persistence-layer behavior:

- Entities are mapped properly.
- Repository queries return the right dataset.
- Filtering and pagination conditions work properly.
- Data constraints or relationships are enforced as expected.

This layer does not replace order-creation business tests. A valid repository query does not prove the service checked stock before creating the order.

The test database environment also matters. Embedded databases may differ from the production database engine in data types, collations, SQL dialects, locks, or transaction behavior. For queries or constraints relying on features of the real engine, consider Testcontainers to run the exact database type to verify.

### 6.4. Integration Testing with @SpringBootTest

When a scenario must prove controller, service, and repository collaborate, use **@SpringBootTest**. You can combine it with MockMvc to send requests through the MVC stack without opening a network port.

Example test skeleton:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CreateOrderFlowTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ProductRepository productRepository;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void creates_order_and_decreases_stock_when_stock_is_sufficient()
            throws Exception {
        // Create a product via the project's fixture or factory with stock = 5.
        Product product = productRepository.save(
            ProductFixtures.withStock(5)
        );

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId": %d, "quantity": 2}
                    """.formatted(product.getId())))
            .andExpect(status().isCreated());

        assertThat(orderRepository.count()).isEqualTo(1);
        Product savedProduct = productRepository
            .findById(product.getId())
            .orElseThrow();
        assertThat(savedProduct.getStock()).isEqualTo(3);
    }
}
~~~

**ProductFixtures.withStock** is an illustrative factory name, not a built-in Spring API. In real projects, use a consistent builder, factory, or test data helper to construct valid entities.

Integration tests must verify the scenario's critical invariants. For the out-of-stock case, prepare stock of 1, submit a request for 2, assert the rejection response, then read back from the database to prove no new order exists and stock remains 1.

MockMvc runs requests in an MVC test environment without opening a real HTTP server. When you need to verify behavior over a network port, configure a random-port server via **@SpringBootTest(webEnvironment = RANDOM_PORT)** and send requests with an appropriate client.

### 6.5. Testing Reactive Applications

For WebFlux applications, scenarios are still derived from behavioral requirements as above; what changes is the web stack and request-sending tool. **@WebFluxTest** with WebTestClient fits web slices. **@SpringBootTest** combined with WebTestClient can verify integrated flows or a live server depending on configuration.

Do not port an MVC test verbatim to reactive merely by swapping client names. Verify asynchronous behavior, error handling in publishers, cancellation, and stream completion when those aspects belong to the application's contract.

## 7. Writing Assertions for Both Success and Failure

A good test answers the question: what evidence shows that the behavior is correct?

### 7.1. Checking the Response Contract

For HTTP APIs, items to verify may include HTTP status, committed Content-Type and headers, JSON body fields, stable error codes or error structures, and identifiers or links of created resources. Avoid asserting the entire JSON payload when many fields are unrelated to the behavior; focus on fields required by the contract.

### 7.2. Checking Post-Processing State

When behavior mutates data, read state back through a repository or suitable observation interface:

- Does the new record exist?
- Was the exact right number of records created?
- Do before and after values relate properly?
- Did the status transition accurately?
- Does related data remain consistent?

For failure scenarios, the key assertion is usually that state did not change. That is how you catch partial writes or transactions failing to roll back as intended.

### 7.3. Checking Side Effects

Some behaviors also emit events, send emails, call external services, or enqueue messages. If those side effects belong to the contract, check:

- Is the side effect emitted on success?
- Is the side effect prevented when the request is rejected?
- Does the event payload contain accurate business data?
- Does one action emit only the specified number of times?

In unit tests, mocks can observe calls to an integration port. In integration tests, prefer a test adapter or simulated queue. Do not assert an internal call just because the method exists; assert it when the call represents a contractually meaningful effect.

### 7.4. Do Not Stop at Error Codes

For a rejected request, checking only 400, 404, or 409 is insufficient if the behavior writes data. For example:

- The API returns 409 Conflict.
- Yet an order was already created before checking stock.
- Stock was decremented before the error was detected.

If you only assert the status, the test stays green even though data is corrupted. Verify record counts, stock quantities, or relevant invariants afterward.

### 7.5. Choosing Error Codes per Contract

A REST API might use:

- 400 Bad Request for malformed requests or validation violations.
- 401 Unauthorized when unauthenticated.
- 403 Forbidden when authenticated but lacking permission.
- 404 Not Found when the requested resource does not exist.
- 409 Conflict when the operation conflicts with current business state.

These are common mappings, not mandatory rules for every API. Status codes and error bodies must be defined in the system's contract. Tests should protect that contract rather than imposing a mapping merely because it is popular.

## 8. Test Data and Independence

A scenario is reliable only when initial state is controlled. If outcomes depend on data left over from an earlier run, tests become unstable.

### 8.1. Each Scenario Prepares Its Own Preconditions

Create required data inside the test itself or a fixture the test calls. Avoid depending on execution order, records created by another test, or manual data in a development environment.

A good fixture builds minimal valid state, allows explicit overrides of relevant attributes, avoids silently creating excessive unneeded data, and uses meaningful names such as a product with 1 unit left or a discontinued product.

### 8.2. Data Cleanup and Transactions

Spring Test supports transactions for many test types. For tests marked **@Transactional**, Spring Test typically rolls back the test's transaction after the test method finishes. This isolates data, yet requires understanding transaction boundaries.

When using MockMvc in a server-less test environment, requests execute in the same thread/process and can participate in the test transaction depending on configuration. With **RANDOM_PORT**, requests run on a server thread, and the client-side test transaction does not automatically wrap the server request's transaction. Therefore, do not assume adding **@Transactional** to a real HTTP test automatically rolls back server-side changes.

Additionally, rollbacks can hide bugs that only surface upon commit or inside post-commit callbacks. For behaviors depending on commits, event listeners, transaction boundaries, or multiple connections, design tests that verify that exact boundary.

### 8.3. Avoid Time and Environment Dependencies

If logic depends on current time, pass a Clock or controllable time source into the component under test. If logic uses random numbers or generated IDs, create an appropriate seam so tests stay deterministic.

For asynchronous processing, wait on a meaningful condition using an appropriate synchronization mechanism. Do not use Thread.sleep with an arbitrary duration as proof that work completed.

For external services, use test doubles or dedicated containers aligned with the test objective. Never let a unit test depend on public networks, real accounts, or shared data.

## 9. Organizing the Test Suite and Naming

Test names should describe the behavior and key condition. A readable convention is:

~~~text
<expected_behavior>_when_<condition>
~~~

Examples:

- creates_order_when_stock_is_sufficient
- rejects_order_when_stock_is_insufficient
- rejects_quantity_below_minimum
- keeps_stock_unchanged_when_order_is_rejected

The name need not repeat every detail of Given – When – Then. The test body should clearly show three phases:

1. Arrange: set up initial state and data.
2. Act: execute one primary action.
3. Assert: verify outcomes and post-processing state.

When multiple values share the same rule, JUnit Parameterized Tests can express input datasets and expectations in one place. Each row should carry a clear name or display label so failures immediately indicate which case failed.

Do not bundle multiple unrelated business actions into one giant test. When a test fails, readers need to pinpoint which behavior broke without tracing through a long script.

## 10. Common Mistakes

### Testing Only the Happy Path

A single success path does not prove the system handles invalid input, missing permissions, non-existent resources, or state conflicts properly. Derive scenarios from every rule and every rejection condition.

### Checking Only Status or Exception

A right status does not prove data is right. A right exception does not prove a transaction rolled back. For state-changing behaviors, verify state and side effects.

### Using @SpringBootTest for Everything

Starting the whole application for a small calculation makes tests slow and hard to isolate. Use unit tests or slice tests whenever they suffice to prove the behavior.

### Mocking Too Deeply

If every repository, mapper, and service is mocked, tests may only confirm that mocks were invoked in a particular sequence. Keep the components to verify real and replace only out-of-scope dependencies.

### Testing Non-Contractual Implementation Details

A refactor can change method call order while keeping outcomes intact. Assertions tightly coupled to internal details cause tests to fail even when behavior remains valid. Verify interactions only when they represent a meaningful business side effect or integration boundary.

### Shared Test Data

Tests relying on data created by other tests often fail when run individually or in parallel. Each scenario must prepare its own state and clean up along proper data boundaries.

### Guessing Missing Rules

If requirements do not specify how to handle retries, timeouts, concurrency conflicts, or error codes, record the question. Picking a behavior yourself can lock unapproved business decisions into tests.

## 11. Practical Workflow from Requirement to Test

**Step 1 – Underline behavioral verbs.** Identify what the system must create, update, delete, return, reject, emit as an event, or transition in state.

**Step 2 – Record preconditions and inputs.** Specify actor, permissions, initial state, required fields, optional fields, and dependencies.

**Step 3 – Split rules into conditions.** Each condition must have a verification method and outcomes for when satisfied or unsatisfied.

**Step 4 – Generate scenarios.** Include the main success path, boundary cases, invalid input, business rule violations, and required dependency failures.

**Step 5 – Record outcomes and invariants.** For each scenario, describe the response, state changes, and side effects. For failures, specify which data must stay untouched.

**Step 6 – Pick the test layer.** Use unit tests for pure rules, web slices for MVC contracts, data slices for persistence, and integration tests when proving collaboration across multiple components.

**Step 7 – Write contract-based assertions.** Verify what callers can observe and the invariants the system guarantees.

**Step 8 – Verify independence.** Run tests both individually and as a suite; ensure zero dependence on order, shared data, or wall-clock time.

**Step 9 – Cross-check against requirements.** Every key criterion must have at least one proving scenario. Every scenario must trace back to an identified rule or risk.

## 12. Reusable Scenario Description Template

Before writing test code, you can record each scenario using this template:

~~~text
ID:
Behavior name:
Related requirement / criterion:

Given:
- Initial state:
- Actor and permissions:
- Input data:
- Dependencies to prepare:

When:
- Single action under test:

Then:
- Observable result:
- State that must change:
- State that must remain unchanged:
- Allowed / forbidden side effects:

Suggested test layer:
Evidence / assertions:
Notes or open questions:
~~~

This template surfaces missing scenarios before writing test code. If you cannot fill in the Then section concretely, acceptance criteria may still be too vague. If you cannot determine the test layer, revisit the behavioral boundary: is it pure logic, a web contract, persistence, or full-application collaboration?

## 13. Assessing Coverage Against Requirements

Do not measure test suite quality purely by test count or percentage of executed lines. For a behavioral requirement, ask:

- Does every key acceptance criterion have a corresponding scenario?
- Are there both success and rejection scenarios for every key rule?
- Are boundary values tested?
- Do failures risking partial writes have state-preservation assertions?
- Are integration side effects verified at the right boundary?
- Are scenarios independent and reliably repeatable?
- Do assertions verify the contract or lock onto implementation details?

Source code coverage remains useful for spotting unexecuted branches, yet does not replace checking against requirements. A branch can execute without its result ever being asserted; a key requirement can go unmodeled despite high overall coverage.

## Conclusion

A trustworthy Spring Framework test suite begins by understanding the behavior the system commits to. When requirements are broken down into preconditions, inputs, rules, outcomes, and invariants, authors can systematically craft both success and failure scenarios. Spring tools such as **@WebMvcTest**, **@DataJpaTest**, and **@SpringBootTest** are then chosen according to the boundary to prove.

Always verify what the system must do on success and what the system must never do on failure. It is the evidence around state and side effects that catches bugs a simple HTTP status or exception assertion cannot see.
