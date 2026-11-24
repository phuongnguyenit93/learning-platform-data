# Testing Services Through Their Public Contract

In a Spring application, services are typically where business rules are enforced and where repositories, integration ports, or other services are coordinated. When unit testing a service, call the methods that other components are allowed to use and assert the outcomes those callers can observe.

This approach makes the **service's public contract** the target of testing. The contract describes what inputs the service accepts, what results it returns, which situations it rejects, and what business effects it produces. Because tests focus on those commitments, they remain valuable even when developers change algorithms or reorganize internal methods.

## 1. What Is a Service's Public Contract?

The public contract is the set of behaviors a caller is entitled to rely on when invoking the service. It usually includes:

- **Inputs and preconditions:** which arguments are valid and what initial state is required.
- **Return values:** the data type, values, and state returned upon successful processing.
- **Published errors:** exceptions or error results a caller may receive when preconditions are not met.
- **Business effects:** data created, updated, or deleted; messages published; external operations requested.
- **Invariants:** rules that must always hold, such as a non-negative total or a paid order not being cancellable.

A service may have several public methods, yet not every visible detail in code is part of the contract. A public method used as an internal helper may not be an API callers are meant to depend on. Conversely, an interface or facade may serve as the primary contract even when the implementation resides in another class.

Start by asking: **What is a caller entitled to expect after calling this method?**

For example, instead of describing “OrderService calls repository.save”, describe:

> When a customer orders an in-stock product with a valid quantity, the service creates an order in the PENDING state, reserves the corresponding stock quantity, and returns the order ID along with the total amount.

This description states outcomes meaningful to the caller and the system. It does not dictate how many private methods the service must use or in what order internal calculations are arranged.

## 2. Defining the Public Boundary Before Writing Tests

A service is typically invoked by a controller, another service, a message listener, or a scheduled task. In a unit test, invoke the same method that callers use.

~~~text
REST Controller
      |
      | calls public method
      v
  OrderService  <---- Unit test calls via public method
      |
      +---- ProductCatalog
      |
      +---- Inventory
      |
      +---- OrderRepository
~~~

Service tests do not need to send HTTP requests if the goal is solely the business rules inside the service. HTTP statuses, JSON, headers, and request mappings belong to the controller/API contract. Service tests focus on business inputs, return values, exceptions, and collaborator effects.

For example:

~~~java
public class OrderService {

    public OrderReceipt placeOrder(
            String customerId,
            String productId,
            int quantity) {
        // Business rules and dependency coordination.
    }

    private BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity) {
        // Internal implementation details.
    }
}
~~~

Callers use `placeOrder`. Therefore, tests should call `placeOrder` and verify the total amount or status in the result. There is no need to call `calculateTotal` directly just because it contains a calculation worth testing. If that calculation is a business rule, test it through `placeOrder` results or through a separate public domain abstraction with its own meaning.

### Public methods do not mean every detail is part of the contract

Do not conclude that a test must assert every public method call on every dependency in its exact current order. Distinguish among:

- The result returned to the caller.
- External effects the business operation commits to.
- How the service currently structures its steps to reach that result.

For instance, the service calling `inventory.reserve(productId, quantity)` matters if the contract requires reserving stock. Whether the service calls a helper named `normalizeProductCode` before or after another helper is usually an implementation detail, unless that ordering produces an observable business difference.

## 3. Turning the Contract into Test Scenarios

A clear way to identify test cases is to describe each scenario in three parts:

1. **Given – Condition:** initial data and state.
2. **When – Action:** the caller invokes the public method with specific inputs.
3. **Then – Outcome:** return values, errors, or effects required by the contract.

Example with `placeOrder`:

| Condition | Action | Expected Contract Outcome |
|---|---|---|
| Product exists, sufficient stock, valid quantity | Place order | Returns order ID and total; order is in PENDING state; stock is reserved |
| Quantity is zero or negative | Place order | Rejects input; does not reserve stock or create an order |
| Product does not exist | Place order | Returns product-not-found error; does not reserve stock or save an order |
| Product exists but insufficient stock | Place order | Returns out-of-stock error; does not save an order |
| Saving order fails after reserving stock | Place order | Executes the defined rollback or reservation-release policy |

This table illustrates a hypothetical contract. In a real project, derive rules from the business requirements or agreed service API. Do not invent requirements like “do not call catalog when quantity is invalid” unless callers or the system actually rely on that behavior.

Each test should check one primary outcome. When different inputs lead to different outcomes, split them into separate tests so test names and setup clearly communicate the scenario.

## 4. Designing Services Testable Through Collaborators

Services often depend on repositories or external gateways. In unit tests, these collaborators can be replaced with mocks or fakes to control inputs and observe contract-level effects.

The example below uses constructor injection:

~~~java
public class OrderService {

    private final ProductCatalog productCatalog;
    private final Inventory inventory;
    private final OrderRepository orderRepository;

    public OrderService(
            ProductCatalog productCatalog,
            Inventory inventory,
            OrderRepository orderRepository) {
        this.productCatalog = productCatalog;
        this.inventory = inventory;
        this.orderRepository = orderRepository;
    }

    public OrderReceipt placeOrder(
            String customerId,
            String productId,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        Product product = productCatalog.findById(productId)
                .orElseThrow(() ->
                        new ProductNotFoundException(productId));

        boolean reserved = inventory.reserve(productId, quantity);
        if (!reserved) {
            throw new InsufficientStockException(productId);
        }

        BigDecimal total = product.unitPrice()
                .multiply(BigDecimal.valueOf(quantity));

        Order draft = Order.pending(
                customerId, productId, quantity, total);

        Order saved = orderRepository.save(draft);

        return new OrderReceipt(
                saved.id(), saved.status(), saved.total());
    }
}
~~~

Collaborators represent the boundaries the service coordinates across:

~~~java
public interface ProductCatalog {
    Optional<Product> findById(String productId);
}

public interface Inventory {
    boolean reserve(String productId, int quantity);
}

public interface OrderRepository {
    Order save(Order order);
}
~~~

`Product`, `Order`, `OrderReceipt`, `ProductNotFoundException`, and `InsufficientStockException` are illustrative domain types. The example assumes `Order.pending(...)` creates a new order in the `PENDING` state and `Order.withId(...)` returns a copy carrying the repository-assigned identifier.

Constructor injection makes dependencies explicit. Unit tests can construct `OrderService` without starting a Spring `ApplicationContext`.

## 5. Writing Unit Tests with JUnit Jupiter and Mockito

JUnit Jupiter provides the test structure and assertions. Mockito creates mocks for collaborators, configures responses, and verifies meaningful effects.

With `MockitoExtension`, a test class can declare mocks with `@Mock` and let Mockito construct the service via `@InjectMocks`:

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private ProductCatalog productCatalog;

    @Mock
    private Inventory inventory;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void createsPendingOrderWhenProductHasEnoughStock() {
        Product product = new Product(
                "sku-1", new BigDecimal("12.50"));

        when(productCatalog.findById("sku-1"))
                .thenReturn(Optional.of(product));

        when(inventory.reserve("sku-1", 2))
                .thenReturn(true);

        when(orderRepository.save(any(Order.class)))
                .thenAnswer(invocation -> {
                    Order draft = invocation.getArgument(0);
                    return draft.withId("order-42");
                });

        OrderReceipt receipt = orderService.placeOrder(
                "customer-7", "sku-1", 2);

        assertAll(
                () -> assertEquals("order-42", receipt.orderId()),
                () -> assertEquals(
                        OrderStatus.PENDING, receipt.status()),
                () -> assertEquals(
                        new BigDecimal("25.00"), receipt.total())
        );

        ArgumentCaptor<Order> orderCaptor =
                ArgumentCaptor.forClass(Order.class);

        verify(orderRepository).save(orderCaptor.capture());

        Order savedOrder = orderCaptor.getValue();

        assertAll(
                () -> assertEquals(
                        "customer-7", savedOrder.customerId()),
                () -> assertEquals(
                        "sku-1", savedOrder.productId()),
                () -> assertEquals(2, savedOrder.quantity()),
                () -> assertEquals(
                        new BigDecimal("25.00"), savedOrder.total()),
                () -> assertEquals(
                        OrderStatus.PENDING, savedOrder.status())
        );

        verify(inventory).reserve("sku-1", 2);
    }
}
~~~

This test verifies two groups of commitments:

- The caller receives a receipt with the right order ID, status, and total amount.
- The service sends a stock reservation request and requests saving an order carrying the right domain data.

`ArgumentCaptor` helps inspect the object passed across the repository boundary. The test does not need to know which private method the service used to compute the total or construct the order object.

`thenAnswer` simulates the repository returning an object with an assigned ID. This is how collaborator results are simulated in unit tests; it does not prove data was persisted to a real database.

### Testing invalid input cases

Suppose the contract requires quantity to be a positive integer. When input is invalid, the service must reject it and produce no order-saving or stock-reservation side effects.

~~~java
@Test
void rejectsNonPositiveQuantityWithoutReservingOrSaving() {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder(
                    "customer-7", "sku-1", 0)
    );

    verify(inventory, never())
            .reserve(anyString(), anyInt());

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

Assertions about effects should only be kept when they are part of the contract. In this example, not reserving stock and not saving an order are meaningful commitments because otherwise the system could create wrong business effects even though the caller received an error.

It is not always necessary to assert that every collaborator was never called. For instance, whether the catalog is queried before or after input validation might merely be a code organization choice. Only verify that if requirements actually mandate it or if it prevents a significant effect.

### Testing insufficient stock cases

~~~java
@Test
void rejectsOrderWhenInventoryCannotReserveQuantity() {
    Product product = new Product(
            "sku-1", new BigDecimal("12.50"));

    when(productCatalog.findById("sku-1"))
            .thenReturn(Optional.of(product));

    when(inventory.reserve("sku-1", 2))
            .thenReturn(false);

    assertThrows(
            InsufficientStockException.class,
            () -> orderService.placeOrder(
                    "customer-7", "sku-1", 2)
    );

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

The test verifies that the service rejects the order when reservation fails and does not save the order. It does not check the call order of all internal helpers; it only verifies the contractually important effect.

### Testing product-not-found cases

~~~java
@Test
void reportsProductNotFoundWhenCatalogHasNoMatchingProduct() {
    when(productCatalog.findById("missing-sku"))
            .thenReturn(Optional.empty());

    assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder(
                    "customer-7", "missing-sku", 1)
    );

    verify(inventory, never())
            .reserve(anyString(), anyInt());

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

This scenario clarifies the error the caller receives and ensures the service does not proceed to reserve stock or save an order when the product does not exist.

## 6. Should You Assert Outcomes or Verify Interactions?

A service unit test may need both outcome assertions and interaction verifications. Choose based on the meaning of each commitment.

### Asserting return values

Use this when the caller relies on the value returned by the service:

~~~java
OrderReceipt receipt = orderService.placeOrder(
        "customer-7", "sku-1", 2);

assertEquals("order-42", receipt.orderId());
assertEquals(OrderStatus.PENDING, receipt.status());
~~~

This is usually the most direct evidence of a public method's contract.

### Asserting data sent to collaborators

Use this when data passed across a boundary is part of the commitment:

~~~java
ArgumentCaptor<Order> captor =
        ArgumentCaptor.forClass(Order.class);

verify(orderRepository).save(captor.capture());

assertEquals("customer-7", captor.getValue().customerId());
assertEquals(2, captor.getValue().quantity());
~~~

If the service must save an order with the right customer, product, and quantity, inspecting the object passed to the repository verifies the domain data before the persistence adapter processes it.

### Asserting that an effect did or did not occur

Use `verify` when that effect matters to the system:

~~~java
verify(inventory).reserve("sku-1", 2);
verify(orderRepository, never()).save(any(Order.class));
~~~

For instance, reserving stock is a business commitment; not saving an order when stock is insufficient is also a commitment.

### Avoiding interaction assertions meaningless to callers

The following assertions typically couple tests to internal structure:

- A private helper was called exactly twice.
- A specific mapper was called instead of another mapping approach.
- The repository must be called via a helper method with a particular name.
- Dependencies are called in the exact current order even when order does not affect the outcome.
- Every mock must be called or not called solely to achieve coverage.

When the implementation changes while business outcomes stay correct, such assertions cause false test failures. Keep only interactions that belong to an integration contract or are needed to prove a meaningful effect.

### When is interaction ordering part of the contract?

There are cases where order truly matters. For instance, the system must check permissions before performing a write, or must succeed in reserving stock before creating an order. When ordering is a business or safety requirement, `InOrder` can be used to verify it.

~~~java
InOrder inOrder = inOrder(permissionService, orderRepository);

inOrder.verify(permissionService).checkCanCreateOrder("customer-7");
inOrder.verify(orderRepository).save(any(Order.class));
~~~

Use this only when order is a guaranteed commitment. If it is merely an accidental ordering of the current code, do not lock tests to it.

## 7. Testing Exceptions as Part of the Contract

Exceptions are a form of outcome observable by callers. Tests must verify the right error type or error details if those belong to the service API.

~~~java
@Test
void throwsProductNotFoundForUnknownProduct() {
    when(productCatalog.findById("missing-sku"))
            .thenReturn(Optional.empty());

    ProductNotFoundException exception = assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder(
                    "customer-7", "missing-sku", 1)
    );

    assertEquals("missing-sku", exception.productId());
}
~~~

If an exception carries an error code, domain error type, or identifier used by callers, verify those fields. If the message is merely internal wording outside the contract, avoid coupling too tightly to the entire message string.

Some notes:

- Verify specific exception types when callers distinguish error cases.
- Do not catch overly broad `Exception.class` when the contract specifies a concrete error type.
- Verify state remains unchanged when an operation fails if that is part of the commitment.
- If exceptions are translated into HTTP statuses in a controller, test that translation in a separate controller test.

## 8. Mocks, Stubs, and Fakes in Service Unit Tests

Different test double techniques serve different purposes:

| Test Double Type | Purpose | Example |
|---|---|---|
| Stub | Supplies predefined responses | Catalog returns a `Product` |
| Mock | Allows configuring and verifying interactions | Inventory is asked to reserve the exact quantity |
| Fake | Provides a simple implementation with real behavior | In-memory repository using a `Map` |

Mockito can act as a stub when configured with `when(...).thenReturn(...)`, and as a mock when `verify(...)` is needed. Not every dependency needs a mock.

A fake can fit well when a service interacts with a collaborator that has simple behavior and mocking makes tests hard to read. For instance, a lightweight in-memory repository can store objects in a `Map` and allow querying them back. However, a fake only simulates programmed behavior; it does not replace testing the real adapter/database.

Choose the test double based on the question to answer:

- Need to control a dependency's output to enter a branch? Use a stub.
- Need to verify a meaningful integration effect? Use a mock.
- Need a small collaborator working naturally across many tests? Consider a fake.
- Need to verify real queries, mappings, transactions, or SQL? Use an integration test with the appropriate adapter/database.

## 9. Is Starting a Spring ApplicationContext Necessary?

A class annotated with `@Service` does not mean every test for it must use `@SpringBootTest`. The `@Service` annotation primarily helps Spring detect and manage the bean. If the goal is testing rules inside service methods and dependencies can be passed via constructors, the service can be constructed directly in a unit test.

### Plain unit test with Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class PricingServiceTest {

    @Mock
    private DiscountPolicy discountPolicy;

    @InjectMocks
    private PricingService pricingService;

    @Test
    void appliesDiscountReturnedByPolicy() {
        when(discountPolicy.discountRateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        BigDecimal total = pricingService.calculate(
                new BigDecimal("100.00"), "VIP");

        assertEquals(new BigDecimal("90.00"), total);
    }
}
~~~

This works well when verifying service logic and responses to collaborators. It runs fast and needs no database setup or full Spring context loading.

### When is a test with a Spring context needed?

A unit test instantiating a service via its constructor does not run through the Spring container and does not create proxies. Therefore, it cannot verify Spring-managed behaviors such as:

- Whether dependency injection and bean configuration are actually right.
- `@Transactional` being applied through a transaction proxy.
- `@Cacheable`, `@Retryable`, or AOP interceptors working properly.
- Method validation being triggered via a Spring proxy when using `@Validated`.
- Security configuration, event listeners, or integration beans being wired correctly.

If the goal is to verify one of those behaviors, write an integration test scoped appropriately for what needs to be checked. You can use `@SpringBootTest` for broad flows or a smaller Spring configuration if only a group of beans is needed.

For example, testing transaction behavior typically requires a real database or suitable test database and a transaction manager configured in the context. Calling `new OrderService(...)` directly cannot prove that `@Transactional` created a transaction.

### Distinguishing scopes

| Question to Answer | Appropriate Test Scope |
|---|---|
| Do service rules return the right result for given inputs? | Service unit test |
| Does the service handle errors returned by dependencies properly? | Unit test with stubs/mocks |
| Does the repository actually save and query entities properly? | Repository integration test |
| Does Spring inject the right beans and create required proxies? | Spring context test |
| Do transactions, caching, or retries work through proxies? | Spring integration test |
| Does the API map service outcomes to HTTP responses properly? | MVC/controller test |

Do not use a single test to claim all layers are verified. Tie conclusions strictly to the boundary the test actually observes.

## 10. Testing Data State and External Effects

A service may mutate state through repositories, publish domain events, send messages, or invoke external services. These effects must be verified according to the contract.

### Data state

If a unit test mocks a repository, it can inspect the object passed to `save`, but it cannot verify that the database actually persists it properly. Separate the two questions:

- Does the service build a save request with the right data? A unit test with a mock or captor is suitable.
- Does the persistence adapter save and query data properly? A repository integration test is suitable.

### Domain events and messages

If the contract specifies the service publishes `OrderCreated`, you can mock the event publisher and verify the event contains the right order ID, customer, and status. If you need to verify the broker actually receives the event or a listener processes it, a message infrastructure integration test is required.

### External services

For payment gateways, email senders, or shipping services, unit tests usually replace the adapter with a mock to control outcomes. Tests can confirm the service sends the right request or sends nothing when conditions are invalid.

Do not call real production services in unit tests. Real communication should be verified in an integration test with a controlled test environment.

### Handling mid-flow failures

An important scenario is when a service performs one effect and a later step fails. For instance, stock was reserved, then saving the order failed. The contract must specify how the system recovers:

- If the reservation participates in the same rollback-capable transaction, integration tests must verify transaction behavior.
- If the reservation is an external effect, a release/compensation action may be required.
- If the operation is processed asynchronously, intermediate states and retry policies must be defined.

A unit test can verify that the service requests releasing the reservation when the repository fails if that is service logic. However, testing with mocks alone does not prove that a transaction or compensation actually succeeded in an external system.

## 11. Structuring Tests for Readability and Maintainability

A good test clearly shows conditions, action, and outcome. You can use the Arrange–Act–Assert or Given–When–Then structure:

~~~java
@Test
void returnsDiscountedTotalForVipCustomer() {
    // Arrange
    when(discountPolicy.discountRateFor("VIP"))
            .thenReturn(new BigDecimal("0.10"));

    // Act
    BigDecimal total = pricingService.calculate(
            new BigDecimal("100.00"), "VIP");

    // Assert
    assertEquals(new BigDecimal("90.00"), total);
}
~~~

### Naming tests after behavior

Test names should describe the condition and expected result:

- `createsPendingOrderWhenStockIsAvailable`
- `rejectsOrderWhenQuantityIsNotPositive`
- `throwsProductNotFoundWhenCatalogHasNoMatch`
- `doesNotSaveOrderWhenReservationFails`

Avoid generic names like `testPlaceOrder`, `testSuccess`, or `testError`. Clear names let readers understand test reports without immediately opening the code.

### Preparing data close to the test

If each test needs a different product, create that data inside the test or use meaningful builders/test data factories. Avoid a `@BeforeEach` stuffed with data for all scenarios where each test only uses a small piece.

A helper like `aProductWithPrice(...)` can make tests easier to read, provided its name describes the created data and does not hide important behavior.

### Avoid sharing mutable state

Each test should be independent. Use mocks managed by `MockitoExtension` or create fresh fakes per test. Avoid static mutable fields, shared caches, or test execution-order dependencies.

### Keep assertions purposeful

A test can contain multiple assertions if they describe a single outcome, such as a receipt having an ID, status, and total. There is no need to check every internal field of an object if callers do not depend on them.

## 12. Common Test Design Mistakes

### Calling private methods directly

Private methods are not boundaries used by callers. Testing private methods directly often forces using reflection or widening visibility solely for tests. Call public methods and verify business outcomes instead.

If a private method contains a business rule large enough to need standalone testing, that may be a sign the rule should be extracted into a collaborator or domain object with clear responsibilities. Then test the new object through its public API.

### Asserting too many Mockito invocations

Calling `verifyNoMoreInteractions` on every mock can cause tests to fail when the implementation adds a query or logging collaborator that does not affect the contract. Verify only important interactions.

### Mocking the entire system

If you mock dependencies that hold important behavior without other tests verifying them, service tests may merely prove the mocks respond as configured in the test. Keep mocks at boundaries needing isolation and write separate integration tests for real adapters.

### Using `@SpringBootTest` for every unit test

Booting the entire context slows tests down and can allow wiring errors to mask logic bugs. Use plain unit tests when only checking service logic. Use a Spring context when container behavior, proxies, or configuration are what need to be tested.

### Checking only exceptions and forgetting side effects

A test that verifies a service throws an exception without checking stock reservations, persistence writes, or published events can miss unwanted side effects. If the contract dictates that failures must produce no effects, assert that.

### Testing implementation details instead of the contract

If a test fails merely because a private helper was renamed or the service switched mappers while outcomes remained right, the test is coupled too deeply to implementation. Shift assertions back to outcomes or meaningful collaborator boundaries.

### Using mocks to simulate what actually needs verification

If the goal is proving JPA mappings, SQL, transactions, or Spring proxies work, mocking the repository or transaction manager skips the very thing being tested. Choose an integration test for that part.

## 13. Practical Workflow: From Contract to Tests

You can follow these steps:

1. **Read business requirements:** determine what callers are entitled to expect from the service.
2. **Select the public entry point:** identify the method or interface callers actually invoke.
3. **List observable outcomes:** return values, exceptions, state changes, and effects across collaborators.
4. **Partition scenarios:** success, invalid inputs, missing data, business rejections, and dependency failures.
5. **Choose test doubles:** stubs to control responses, mocks to observe contract effects, fakes when a simple stateful collaborator is needed.
6. **Write tests via the public API:** do not call private helpers or access internal fields.
7. **Pick the right scope:** unit tests for service logic; integration tests for Spring proxies, persistence, or real communication.
8. **Read tests as a contract:** can someone understand what the service must do purely from test names, setup data, and assertions?

### Example contract description before writing tests

~~~text
Public method: OrderService.placeOrder(customerId, productId, quantity)

Success conditions:
- valid customerId
- product exists
- quantity > 0
- inventory can reserve the requested quantity

Success outcomes:
- returns a receipt with orderId
- order status is PENDING
- total equals unitPrice * quantity
- requests inventory to reserve the exact quantity
- sends the order to be saved to the repository

Failure outcomes:
- invalid quantity: IllegalArgumentException
- product does not exist: ProductNotFoundException
- insufficient stock: InsufficientStockException
- does not create an order when reservation fails
~~~

From this description, tests can be divided into individual methods for each outcome. When requirements change, update the contract and related scenarios rather than patching assertions to match a new implementation structure.

## 14. Short Checklist When Reviewing a Service Unit Test

- The test calls the public method or interface callers actually use.
- The test name states the condition and expected outcome.
- Initial data clearly expresses the business scenario.
- Assertions verify the outcome the caller receives.
- Collaborator interactions are checked only when they belong to a commitment or protect an important effect.
- Failure tests verify prohibited effects did not occur.
- No private methods, private fields, or internal helper call ordering are relied upon.
- Mock repositories are not mistaken for proof that the database persisted data.
- A Spring context is used when verifying containers, proxies, transactions, or integration configuration.
- Each test can run independently without relying on the order of other tests.

## Conclusion

Testing services through their public contract means calling the service like a real caller and asserting what callers are entitled to expect: return values, published errors, business state, and meaningful integration effects. JUnit Jupiter and Mockito make testing those behaviors fast without booting the entire Spring context. When you need to verify transactions, proxies, persistence, or real Spring configuration, add integration tests at the proper boundaries. This organization keeps unit tests focused on business rules and decoupled from internal implementation details.
