# Testing Success, Error, and Exception Paths

A business method often has multiple execution paths: valid data leads to a successful outcome, data violating rules leads to a business error, and dependencies can raise exceptions when accessing a database or calling another service. Unit tests must verify that each significant execution path produces the expected result and performs only permitted interactions.

In JUnit Jupiter, `@Test` defines a test case, assertions verify outcomes, and `assertThrows` verifies expected exceptions. Mockito replaces dependencies with mocks, configures return values or exceptions, and verifies calls happen at the right times. Combining these tools keeps tests focused on the contract of the class under test.

## 1. Distinguishing Execution Paths

Before writing tests, read the method's rules and list the meaningful branches. An order processing method might have the following paths:

| Execution Path | Condition | Expected Outcome |
|---|---|---|
| Success | Valid quantity, product exists and is active, sufficient stock | Save the order and return the saved order |
| Invalid input | Quantity is less than or equal to 0 | Throw parameter error before calling repository |
| Resource not found | Repository does not find product | Throw business error; do not check inventory or save order |
| Disallowed state | Product is discontinued | Throw business error; do not reserve stock or save order |
| Insufficient stock | Inventory service refuses to reserve requested quantity | Throw business error; do not save order |
| Dependency failure | Repository or inventory service throws an exception | Exception is handled per service contract; do not proceed to later steps |

Each row in the table represents a behavior to protect. Avoid having just one generic success test and one generic failure test, as they do not show which branch is being verified.

### 1.1. Success path

The success path confirms valid data flows through the expected sequence and yields the expected output. Typically verify:

- The return value has the right content or object per contract.
- Dependencies receive the right arguments.
- Required operations are called the expected number of times.
- Outbound data has been transformed properly, such as an encrypted password or tax-adjusted amount.
- No redundant calls or off-contract operations occur.

Not every test needs to assert every internal call. Verify only interactions meaningful to the class's contract, especially those producing side effects like persisting data, sending notifications, or reserving resources.

### 1.2. Business error paths

A business error is an intentional outcome when input conditions or domain state disallow an operation. Examples include invalid quantity, nonexistent product, locked account, or insufficient balance.

For these paths, tests should verify the error type, key error details, and that subsequent steps do not run. For instance, if a product does not exist, neither the stock reservation service nor the order save repository may be called.

### 1.3. Exceptions from dependencies

An exception from a dependency indicates a failure in a component the class under test uses, such as a broken database connection or an unresponsive external service. Clarify whether the service is responsible for:

- Propagating the exception to the caller while preserving the cause;
- Translating a technical exception into a meaningful application exception;
- Or retrying, using a fallback, or performing a recovery action per policy.

Tests must reflect that policy. Do not catch any `RuntimeException` and merely check that an error occurred; verify the concrete error type or cause to catch cases where a different error is mishandled.

## 2. Defining the Service Contract Before Writing Tests

Consider an order creation service. The service checks quantity, looks up the product, confirms the product is active, reserves stock, and saves the order. This example uses Java records to keep data concise.

Data types and dependencies:

```java
import java.util.Optional;

record Product(String id, boolean active) {
}

record Order(String productId, int quantity) {
}

interface ProductRepository {
    Optional<Product> findById(String productId);
}

interface InventoryService {
    boolean reserve(String productId, int quantity);
}

interface OrderRepository {
    Order save(Order order);
}
```

Business exceptions:

```java
class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String productId) {
        super("Product not found: " + productId);
    }
}

class ProductUnavailableException extends RuntimeException {
    ProductUnavailableException(String productId) {
        super("Product is unavailable: " + productId);
    }
}

class InsufficientStockException extends RuntimeException {
    InsufficientStockException(String productId, int quantity) {
        super("Insufficient stock for product " + productId
                + ", requested quantity: " + quantity);
    }
}
```

Service implementing the paths:

```java
class OrderService {

    private final ProductRepository productRepository;
    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    OrderService(
            ProductRepository productRepository,
            InventoryService inventoryService,
            OrderRepository orderRepository
    ) {
        this.productRepository = productRepository;
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    Order placeOrder(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Product product = productRepository.findById(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));

        if (!product.active()) {
            throw new ProductUnavailableException(productId);
        }

        if (!inventoryService.reserve(productId, quantity)) {
            throw new InsufficientStockException(productId, quantity);
        }

        return orderRepository.save(new Order(productId, quantity));
    }
}
```

The example's contract is: quantity must be positive; the product must exist and be active; inventory must accept the request; only when every condition holds is the order saved. Constructor injection makes dependencies explicit and lets unit tests construct the service with mocks without booting a Spring context.

## 3. Setting Up JUnit Jupiter and Mockito

With Spring Boot, `spring-boot-starter-test` typically provides JUnit Jupiter, Mockito, and the Mockito extension. In a plain Java project without Spring Boot, declare `junit-jupiter` alongside `mockito-junit-jupiter` in test scope.

A JUnit Jupiter test using `MockitoExtension`:

```java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private InventoryService inventoryService;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;
}
```

`@Mock` creates a mock for each dependency. `@InjectMocks` instructs Mockito to instantiate `OrderService` and pass the matching mocks into its constructor. `MockitoExtension` initializes and manages Mockito annotations across the JUnit Jupiter lifecycle.

You can initialize mocks with `Mockito.mock(...)` inside `@BeforeEach`, though avoid mixing initialization styles within the same test class without reason so mocks are not duplicated or tests accidentally use the wrong instance.

## 4. Testing the Success Path

When all conditions are valid, the service must return the saved result from the repository and pass the right data to its dependencies. Use `when(...).thenReturn(...)` to configure mock responses.

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void placesOrderWhenProductIsActiveAndStockIsAvailable() {
    Product product = new Product("p-100", true);
    Order savedOrder = new Order("p-100", 3);

    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(product));
    when(inventoryService.reserve("p-100", 3))
            .thenReturn(true);
    when(orderRepository.save(org.mockito.ArgumentMatchers.any(Order.class)))
            .thenReturn(savedOrder);

    Order result = orderService.placeOrder("p-100", 3);

    assertThat(result).isSameAs(savedOrder);

    ArgumentCaptor<Order> orderCaptor = ArgumentCaptor.forClass(Order.class);
    verify(orderRepository).save(orderCaptor.capture());
    assertThat(orderCaptor.getValue())
            .isEqualTo(new Order("p-100", 3));

    verify(productRepository).findById("p-100");
    verify(inventoryService).reserve("p-100", 3);
}
```

`ArgumentCaptor` lets you inspect the object sent to the repository. Checking only whether `save()` was called would miss cases where the service persisted the wrong `productId` or `quantity`.

`assertThat(result).isSameAs(savedOrder)` fits this example because the service returns the exact instance returned by the repository. If the contract only requires value equality, use `isEqualTo(...)` and verify key fields. Choose assertions according to the API's meaning rather than incidental implementation details.

Some projects use `@Captor` instead of creating a captor inside the test. Use captors only when inspecting arguments is needed; if direct assertions already verify the outcome, do not add captors for every call.

## 5. Testing Invalid Input Paths

With `quantity <= 0`, the service must throw `IllegalArgumentException` immediately. Because this check occurs before accessing repositories, the test should verify that no dependency was called.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsZeroQuantityBeforeCallingDependencies() {
    IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", 0)
    );

    assertThat(exception).hasMessage("quantity must be positive");
    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

`assertThrows` returns the thrown exception so you can verify its message or additional properties. It also accepts subclasses of the specified exception type. If the contract demands an exact exception class, JUnit Jupiter provides `assertThrowsExactly` in versions supporting that API.

Also test negative quantities if they represent a meaningful boundary. If both zero and negative numbers go through the same check and produce the same error type, a parameterized test avoids code duplication.

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(ints = {0, -1, -100})
void rejectsNonPositiveQuantity(int quantity) {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", quantity)
    );

    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

Parameterized tests fit well when multiple inputs test the same rule and share the same expected outcome. When each value requires a distinct message, state, or behavior, separate tests are usually easier to read.

## 6. Testing Individual Business Error Paths

### 6.1. Product not found

When the repository returns `Optional.empty()`, the service must throw `ProductNotFoundException`. Stock reservation and order saving must not run.

```java
@Test
void throwsWhenProductDoesNotExist() {
    when(productRepository.findById("missing"))
            .thenReturn(Optional.empty());

    ProductNotFoundException exception = assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder("missing", 2)
    );

    assertThat(exception).hasMessage("Product not found: missing");
    verify(productRepository).findById("missing");
    verifyNoInteractions(inventoryService, orderRepository);
}
```

This test confirms both the error result and an important business ordering rule: you cannot reserve stock for a nonexistent product.

### 6.2. Inactive product

The product exists, yet `active` is `false`. This is a distinct branch from product-not-found and requires its own test.

```java
@Test
void throwsWhenProductIsInactive() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", false)));

    ProductUnavailableException exception = assertThrows(
            ProductUnavailableException.class,
            () -> orderService.placeOrder("p-100", 2)
    );

    assertThat(exception).hasMessage("Product is unavailable: p-100");
    verify(productRepository).findById("p-100");
    verifyNoInteractions(inventoryService, orderRepository);
}
```

If you only test `Optional.empty()`, the `!product.active()` branch remains unverified. Every meaningful conditional branch needs inputs that evaluate it to both true and false, or an explainable equivalent set of tests.

### 6.3. Insufficient stock

When the product is valid yet `reserve(...)` returns `false`, the service must throw `InsufficientStockException` and not save the order.

```java
@Test
void throwsWhenInventoryCannotReserveRequestedQuantity() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", true)));
    when(inventoryService.reserve("p-100", 5))
            .thenReturn(false);

    InsufficientStockException exception = assertThrows(
            InsufficientStockException.class,
            () -> orderService.placeOrder("p-100", 5)
    );

    assertThat(exception)
            .hasMessage("Insufficient stock for product p-100, requested quantity: 5");
    verify(inventoryService).reserve("p-100", 5);
    verifyNoInteractions(orderRepository);
}
```

This illustrates asserting blocked side effects: the order repository is not called when inventory rejects the request. If the system has more complex reservation or compensation mechanisms, tests must verify the corresponding reserve/release contract.

## 7. Testing Exceptions Raised by Dependencies

Business errors intentionally thrown by the service differ from technical exceptions coming from dependencies. In this example, if the repository cannot query data, the service has no error translation policy, so the exception must propagate to the caller.

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void propagatesRepositoryFailureAndStopsProcessing() {
    IllegalStateException databaseFailure =
            new IllegalStateException("database unavailable");

    when(productRepository.findById("p-100"))
            .thenThrow(databaseFailure);

    assertThatThrownBy(() -> orderService.placeOrder("p-100", 2))
            .isSameAs(databaseFailure);

    verifyNoInteractions(inventoryService, orderRepository);
}
```

`isSameAs(databaseFailure)` verifies that the service propagates the exact exception received. If the service is designed to wrap errors into `OrderProcessingException`, assertions should check the new exception class and the root cause via `hasCause(...)` or `getCause()`.

Inventory service failures can be tested similarly:

```java
@Test
void propagatesInventoryFailureWithoutSavingOrder() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", true)));

    IllegalStateException inventoryFailure =
            new IllegalStateException("inventory service unavailable");
    when(inventoryService.reserve("p-100", 2))
            .thenThrow(inventoryFailure);

    assertThatThrownBy(() -> orderService.placeOrder("p-100", 2))
            .isSameAs(inventoryFailure);

    verifyNoInteractions(orderRepository);
}
```

Do not use `thenThrow(new RuntimeException())` for every dependency failure if the application distinguishes timeouts, connection errors, authentication failures, or business errors. Use the exception type the real dependency throws or a representative test exception so the handling policy is clearly verified.

### 7.1. Exceptions on `void` methods

Mockito uses `doThrow(...)` to configure exceptions for `void` methods:

```java
doThrow(new IllegalStateException("notification unavailable"))
        .when(notificationService)
        .sendOrderCreated("order-1");
```

Then invoke the method under test and verify the outcome per contract. For methods returning a value, use `when(...).thenThrow(...)` as in earlier examples.

### 7.2. Checked and unchecked exceptions

If a dependency declares a checked exception, tests must handle it matching the method signature. For example, a test method may declare `throws IOException`, and a lambda passed to `assertThrows(IOException.class, ...)` can execute that call inside an appropriate test method.

Do not wrap checked exceptions into `RuntimeException` in tests just to avoid the signature. Verify the exact exception type required by the public contract. If the class under test translates exceptions, verify both the target exception and its cause so diagnostic information is preserved.

## 8. Verifying Interactions and Side Effects

Assertions on return values tell you what output the method produced. Mockito verification tells you how the method interacted with its dependencies. Both checks complement each other.

| Mockito API | Purpose | Example |
|---|---|---|
| `verify(mock).method(...)` | Verify call happened once | `verify(orderRepository).save(any())` |
| `verify(mock, times(2))` | Verify exact call count | Operation invoked twice per contract |
| `verify(mock, never())` | Verify method was never called | Order not saved when out of stock |
| `verifyNoInteractions(mock)` | Verify mock had zero interactions | No dependencies called when input fails up front |
| `verifyNoMoreInteractions(mock)` | Verify no interactions remain beyond verified calls | Use only when remaining interactions genuinely belong to a locked contract |
| `ArgumentCaptor<T>` | Capture passed arguments to inspect contents | Inspecting the order sent to repository |

Do not overuse `verifyNoMoreInteractions` in every test. It tightly locks internal call ordering and counts, causing behavior-preserving refactors to break tests. Verify meaningful interactions such as saving data, publishing events, or calling required dependencies.

For failure paths, verify steps after the failure point do not execute. For instance, if the repository finds no product, `inventoryService.reserve(...)` and `orderRepository.save(...)` must not be called. For the success path, verify all required interactions and key arguments.

When a dependency produces real side effects—such as deducting inventory or sending email—mocks only prove the service called it with certain arguments. Mocks do not prove the database or external system actually updated properly. That behavior requires integration tests with real components or an appropriate test environment.

## 9. Distinguishing Expected Exceptions from Unexpected Bugs

Not every exception represents the same kind of failure.

| Category | Example | How to Test |
|---|---|---|
| Parameter violation | `IllegalArgumentException` when quantity is non-positive | Call with invalid input and verify error occurs before dependencies |
| Business error | `ProductNotFoundException`, `InsufficientStockException` | Set up domain state causing the rule to fail and check error type |
| Infrastructure failure | Timeout, connection error, or repository error | Configure mock to throw technical error and verify propagation or translation per contract |
| Unexpected programming bug | `NullPointerException` from wrong null access | Never make it an expected outcome of a business test; fix the cause in code |

A test like this is too broad:

```java
assertThrows(RuntimeException.class,
        () -> orderService.placeOrder("p-100", 2));
```

If the method accidentally throws `NullPointerException`, the test still passes even when the expected behavior is `InsufficientStockException`. Specify the concrete exception type:

```java
assertThrows(InsufficientStockException.class,
        () -> orderService.placeOrder("p-100", 5));
```

When the exception type is part of the contract, also assert its message, error code, or cause if they are stable and meaningful to callers. Avoid hardcoding entire non-contract wording since phrasing or localization may change.

## 10. Testing Multiple Branches with `@ParameterizedTest`

Parameterized tests are helpful when one rule has multiple input values sharing the same behavior. For example, zero and negative quantities must all be rejected. `@ValueSource` suits a single simple parameter; `@CsvSource` can represent multiple data columns.

```java
@ParameterizedTest
@ValueSource(ints = {0, -1, -20})
void rejectsQuantityThatIsNotPositive(int quantity) {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", quantity)
    );

    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

If each case expects a different outcome, separate the tests or use `@MethodSource` so test data has clear names and structure. Do not group cases just because they all happen to throw exceptions; each cause and expected behavior still needs to stand out clearly.

## 11. Branch Checking and Coverage

Line coverage shows which statements ran; branch coverage shows which conditional paths executed. With `placeOrder`, a test suite might execute an `if` statement yet only follow one side of the condition. Line coverage can look high while branch coverage remains incomplete.

For example, `if (!product.active())` has two outcomes:

- `active == true`: proceed to check inventory.
- `active == false`: throw `ProductUnavailableException`.

Covering both branches requires at least one test for an active product and one test for an inactive product. Likewise, `inventoryService.reserve(...)` needs both `true` and `false` cases.

Coverage is an indicator that helps find unexecuted areas, not proof that tests check the right outcomes. A test can run through a branch with no meaningful assertions. Prioritize verifying behavior, outputs, and side effects; use branch coverage to spot missing paths.

When using JaCoCo, you can configure line/branch coverage reports for the test task and inspect missing branches in the HTML report. Do not write tests solely to hit a percentage target if those tests protect no meaningful rule. Defensive branches unreachable under the contract should also be evaluated by design rather than fabricating fake data just to boost coverage.

## 12. Choosing Unit Tests or Spring Integration Tests?

Service unit tests typically only need JUnit Jupiter and mocked dependencies. `@SpringBootTest` is unnecessary when the goal is verifying pure rules of a single class.

| Goal | Appropriate Testing Approach |
|---|---|
| Verify business branches in a service | JUnit Jupiter + Mockito, instantiate service directly |
| Verify dependency injection and bean configuration | Spring Test or `@SpringBootTest` |
| Verify transactions, rollbacks, and real database interactions | Integration test with Spring context and test database |
| Verify HTTP statuses and exception handlers | `@WebMvcTest` with `MockMvc` or suitable integration test |
| Verify real errors from a database or message broker | Integration test with real components or test containers |

A unit test can verify the service throws `InsufficientStockException`, yet it does not prove the controller maps that exception to HTTP 409 or the right JSON response. That is a web contract and belongs in controller tests.

Similarly, mocking a repository to throw `DataAccessException` tests how the service reacts to a failing dependency; it does not prove the database transaction rolls back properly. Rollback needs verification in an integration test running inside a transaction and reading state back appropriately.

## 13. Common Mistakes

**Testing only the happy path.** Rejection branches, missing resources, and dependency failures often harbor control-flow bugs. List all branches before writing tests.

**Using one test to cover multiple failure causes.** If a single test sets up both a nonexistent product and insufficient stock, the service stops at the first branch. The inventory branch never executes. Each test should isolate the condition triggering the target branch.

**Asserting only that an exception occurred.** Using `RuntimeException.class` can let unexpected programming errors turn tests green. Verify the specific exception type and key details.

**Forgetting to verify steps after the failure point did not run.** A test may observe the expected exception while the service still calls the repository or emits an event after mishandling an error. Use `verifyNoInteractions`, `never()`, or state checks per contract.

**Mocking every object, including simple value objects.** DTOs, records, and value objects should generally be real instances. Mocking them hurts readability and offers no benefit when they hold no behavior needing replacement.

**Using `@SpringBootTest` for every unit test.** Booting the full context slows tests down and lets configuration issues obscure business logic bugs. For services with explicit dependencies, direct instantiation with Mockito mocks is usually enough.

**Over-verifying internal details.** Locking down every call makes tests brittle when refactoring implementations. Verify only contract-level interactions or critical side effects.

**Assuming mocks test external systems.** Mockito only simulates responses and records calls. It does not prove databases, brokers, or external APIs work properly; integration tests are needed for those.

## 14. Workflow for Building a Service Test Suite

For a service with multiple branches, you can follow this sequence:

1. Read the method and note every `if`, `switch`, `Optional`, loop, or meaningful throw point.
2. Determine the expected outcome for each branch: return value, exception, state, or side effect.
3. Write the success test first to confirm the normal flow and required dependencies.
4. Write a separate test for each important business error, setting up conditions so only that branch triggers.
5. Configure dependencies to throw exceptions to test propagation, translation, retry, or fallback policies.
6. Verify subsequent calls stop at the failure point and produce no off-contract side effects.
7. Run tests and inspect branch coverage to spot unexecuted paths; add tests for missing behaviors.
8. When transactions, HTTP mappings, or real dependency behaviors need verification, add integration tests at the corresponding layer.

For the `OrderService` example, the core suite includes: one success test; one invalid quantity test; one nonexistent product test; one inactive product test; one insufficient stock test; and tests for dependency exceptions. Each test focuses on the single condition that directs execution onto the branch being verified.

When testing success, error, and exception paths, the key is clearly defining triggering conditions, published outcomes, and permitted side effects. JUnit Jupiter provides assertions and parameterized testing; Mockito controls dependencies and verifies interactions; Spring Test or integration tests are used when checking coordination with the Spring context, transactions, HTTP, or real infrastructure. A good test suite shows readers what the service must do both in normal cases and when a condition fails.
