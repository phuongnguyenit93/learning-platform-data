# Distinguishing Business Logic Failures from Collaborator Failures

A unit test usually verifies a single object or a small group of logic under controlled dependencies. When a test fails, the key question is: did the object under test make a wrong decision, or did a collaborator provide wrong output, get called incorrectly, or fail to work as expected?

Both failure types can produce the exact same external symptom. For instance, an order might be rejected because a business rule forbids that quantity, because inventory reports out of stock, because an adapter queries inventory wrongly, or because the test misconfigured a mock. Finding the real root cause requires defining the unit test's boundary, controlling collaborator outputs, and testing each component at the proper scope.

## How Do These Two Failure Groups Differ?

**A business logic failure** occurs when the rule or decision the application must enforce is wrong. Examples include calculating totals wrongly, applying discounts under wrong conditions, allowing invalid quantities, transitioning order state wrongly, or returning an outcome inconsistent with business policy.

**A collaborator failure** occurs when a dependency fails to fulfill its responsibility or when the object under test coordinates with a dependency wrongly. Examples include a repository querying the wrong record, an adapter converting data wrongly, an inventory gateway sending the wrong product code, an HTTP client mapping responses wrongly, or a bean not being configured or injected as expected.

Distinguish two concepts:

- A *collaborator* is an object or service that the unit under test calls to complete its work.
- A *component* is an implementation part with its own boundary and responsibility, such as a repository, adapter, client, service, or Spring bean.

A collaborator may be replaced by a mock in a unit test. In that case, the test verifies how the unit uses the collaborator under the declared contract, not the collaborator's real implementation.

| Observed Symptom | Likely Cause to Investigate |
|---|---|
| Collaborator returns the exact data configured by the test, yet the business result is wrong | Rule or calculation inside the unit under test |
| Unit passes wrong arguments, skips a call, or calls a collaborator at the wrong time | Coordination logic inside the unit |
| Real collaborator returns wrong data even when invoked standalone with valid input | Implementation bug in the collaborator |
| Unit tests pass with mocks yet integration tests fail | Contract, configuration, wiring, or interaction among real components |
| Test fails because a mock was stubbed wrongly or fixtures conflict | Test setup error; insufficient evidence that production code is broken |

Do not look only at the exception name or the first failing assertion and jump to a conclusion. Inspect the inputs, the outputs supplied by collaborators, actual calls made, and the scope covered by the test.

## Defining the Boundary of the Unit Under Test

Suppose an application has an order placement flow:

1. Receive product SKU and quantity.
2. Read product details from the catalog.
3. Calculate the total price.
4. Request the inventory system to reserve stock.
5. Save the order.

In this flow, `OrderService` can be the unit under test. Catalog, inventory, and repository are its collaborators.

~~~mermaid
flowchart TD
    A["OrderService"] --> B["ProductCatalog"]
    A --> C["Inventory"]
    A --> D["OrderRepository"]
    A --> E["Ordering and total calculation rules"]
~~~

If the goal is testing `OrderService` rules, tests can replace catalog, inventory, and repository with test doubles. That lets the test control which product is found, whether inventory accepts the reservation, and what the repository returns.

If the goal is testing that `ProductCatalog` queries the database properly, a dedicated test for the real catalog implementation against an appropriate test database is needed. Mocking the catalog in `OrderServiceTest` cannot prove that the real catalog's SQL, mapping, or transactions are right.

Test boundaries should be clear in both test names and structure. A test named `calculatesTotalForAvailableProduct` should focus on the pricing decision. A test named `jdbcProductCatalogFindsProductBySku` should test the data-access adapter. When a single test tries to verify everything at once, diagnosing failures becomes harder.

## Testing Business Logic When Collaborators Are Controlled

The example below illustrates a service that checks quantity, looks up a product, calculates the total, and asks inventory to reserve stock:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

record Product(String sku, BigDecimal unitPrice) {}

record OrderCommand(String sku, int quantity) {}

record Order(
    String sku,
    int quantity,
    BigDecimal total
) {}

interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}

interface Inventory {
    boolean reserve(String sku, int quantity);
}

interface OrderRepository {
    Order save(Order order);
}

class OrderService {
    private final ProductCatalog catalog;
    private final Inventory inventory;
    private final OrderRepository repository;

    OrderService(
        ProductCatalog catalog,
        Inventory inventory,
        OrderRepository repository
    ) {
        this.catalog = catalog;
        this.inventory = inventory;
        this.repository = repository;
    }

    Order place(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        Product product = catalog.findBySku(command.sku())
            .orElseThrow(() -> new ProductNotFoundException(command.sku()));

        BigDecimal total = product.unitPrice()
            .multiply(BigDecimal.valueOf(command.quantity()));

        if (!inventory.reserve(command.sku(), command.quantity())) {
            throw new OutOfStockException(command.sku());
        }

        return repository.save(
            new Order(command.sku(), command.quantity(), total)
        );
    }
}
~~~

`ProductNotFoundException` and `OutOfStockException` are illustrative business exceptions for this example. Notice how responsibilities are split: the service validates quantity and orchestrates the flow; the catalog finds products; inventory reserves stock; the repository persists orders.

In unit tests, Mockito can specify collaborator responses:

~~~java
import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    ProductCatalog catalog;

    @Mock
    Inventory inventory;

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @Test
    void calculatesTotalAndSavesOrder() {
        when(catalog.findBySku("SKU-1"))
            .thenReturn(Optional.of(
                new Product("SKU-1", new BigDecimal("12.50"))
            ));
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Order result = service.place(new OrderCommand("SKU-1", 2));

        assertThat(result.total())
            .isEqualByComparingTo("25.00");
        assertThat(result.quantity()).isEqualTo(2);

        verify(inventory).reserve("SKU-1", 2);
        verify(repository).save(any(Order.class));
    }
}
~~~

Here the test explicitly sets the outputs of catalog and inventory. If the service returns a total of `24.00` instead of `25.00`, the cause lies in the pricing logic of the unit under test, assuming the test fixtures and expectations are accurate. Collaborators did not query a database or call a real inventory service, so those implementations cannot be blamed.

Additional tests can verify other business branches:

~~~java
@Test
void rejectsZeroQuantity() {
    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 0))
    ).isInstanceOf(IllegalArgumentException.class);
}

@Test
void rejectsOrderWhenInventoryCannotReserve() {
    when(catalog.findBySku("SKU-1"))
        .thenReturn(Optional.of(
            new Product("SKU-1", new BigDecimal("12.50"))
        ));
    when(inventory.reserve("SKU-1", 2)).thenReturn(false);

    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 2))
    ).isInstanceOf(OutOfStockException.class);

    verify(repository, never()).save(any(Order.class));
}
~~~

The second test confirms the service's decision when the collaborator reports it cannot reserve stock: the service raises an out-of-stock business outcome and does not save the order. It does not prove the real warehouse system's stock-checking algorithm works; the test verifies how the service responds to the `Inventory.reserve()` contract.

Imports and exception classes must be declared accordingly in a real project; the code focuses on illustrating how to set test boundaries and control collaborators.

## When Does a Failure Belong to a Collaborator?

Mocks help control a unit's inputs, yet if a mock returns wrong outputs due to bad test stubbing, tests can fail even when production code is right. Distinguish three situations:

**Collaborator is stubbed properly, unit misuses it.** For example, the test specifies `reserve("SKU-1", 2)` returns `true`, yet the service calls `reserve("SKU-1", 1)`. This is a coordination bug inside the unit under test because the passed argument does not match requirements.

**Collaborator is called properly, real implementation returns wrong output.** For example, the service passes the right SKU, yet `JdbcProductCatalog` queries the wrong column or maps the wrong price. This is a bug to investigate in the catalog adapter and verify with the adapter's own tests.

**Mock or fixture is misconfigured.** For example, the service looks up `SKU-1`, yet the test stubs `findBySku("SKU-01")`. The mock returns its default value, sending the test down an unintended branch. This is a test setup error, not evidence that the service is broken.

You can use `ArgumentCaptor` to inspect the object the unit actually passes to a collaborator:

~~~java
ArgumentCaptor<Order> captor = ArgumentCaptor.forClass(Order.class);

verify(repository).save(captor.capture());

Order saved = captor.getValue();

assertThat(saved.sku()).isEqualTo("SKU-1");
assertThat(saved.quantity()).isEqualTo(2);
assertThat(saved.total()).isEqualByComparingTo("25.00");
~~~

Captors are useful when the passed payload is part of the collaboration contract. However, do not verify every internal call. Tests overly coupled to interaction details become brittle when refactoring while external business behavior remains correct.

## Testing Real Collaborators at the Appropriate Scope

When suspecting a bug in a collaborator, test that component with real dependencies or a test double suited to its boundary.

For example, `JdbcProductCatalog` must be tested against a test database to verify:

- SQL filters by the right SKU.
- Columns map properly to `Product`.
- Missing records return `Optional.empty()`.
- Data types and monetary values are read accurately.
- Transactions and database error handling match the adapter's contract.

A service unit test with a mocked catalog covers none of these points.

You can use Spring Test to load the needed persistence configuration, set up a test database, and inject the real catalog into the test:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class JdbcProductCatalogTest {

    @Autowired
    ProductCatalog catalog;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void findsProductAndMapsItsPrice() {
        jdbcTemplate.update(
            "insert into product(sku, unit_price) values (?, ?)",
            "SKU-1",
            new BigDecimal("12.50")
        );

        var result = catalog.findBySku("SKU-1");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().unitPrice())
            .isEqualByComparingTo("12.50");
    }
}
~~~

This example assumes `PersistenceTestConfig` configures the datasource, schema, transaction manager, and `JdbcProductCatalog` bean; the table has two columns `sku` and `unit_price`. Test-managed transactions roll back test data after each test method finishes.

If the real catalog test fails due to wrong price mapping, you have concrete evidence to investigate the adapter. If the catalog test passes while `OrderServiceTest` fails with properly stubbed collaborator results, focus on the service's logic or coordination.

For HTTP adapters, use a mock web server or HTTP stub to test requests, responses, and mappings. For message publishers, test that messages are built properly and use integration tests to confirm the broker receives them. Pick tools according to the component's responsibility.

## Distinguishing Business Failures from Technical Collaborator Failures

Not every collaborator failure is a business failure. Separate valid business outcomes from technical failures preventing a collaborator from doing its job:

| Situation | Outcome Classification |
|---|---|
| Inventory confirms insufficient stock | Business outcome: order cannot be placed |
| Catalog does not find product | Business outcome or invalid input, per contract |
| Database loses connection while saving order | Technical infrastructure or repository failure |
| HTTP client receives malformed response | Adapter communication or mapping failure |
| Service calculates total wrongly when catalog returns right unit price | Business logic error in service |
| Service passes wrong SKU to inventory | Coordination error between service and collaborator |

A technical error may be translated into an upper-layer exception or result per application policy. Yet that translation must preserve meaning. Never catch every exception and return `OutOfStockException`, as you lose the ability to distinguish genuine out-of-stock from an unreachable inventory system.

Tests should also cover technical error handling when that is the unit's responsibility:

~~~java
@Test
void propagatesInventoryInfrastructureFailure() {
    when(catalog.findBySku("SKU-1"))
        .thenReturn(Optional.of(
            new Product("SKU-1", new BigDecimal("12.50"))
        ));
    when(inventory.reserve("SKU-1", 2))
        .thenThrow(new InventoryUnavailableException());

    assertThatThrownBy(() ->
        service.place(new OrderCommand("SKU-1", 2))
    ).isInstanceOf(InventoryUnavailableException.class);

    verify(repository, never()).save(any(Order.class));
}
~~~

This test confirms the service does not save the order when the inventory system cannot answer. It prevents code from turning an infrastructure outage into a wrong business decision.

## Reading Test Results to Isolate Root Causes

When a test fails, trace the data flow and locate the first value diverging from the expected contract.

1. **Identify which unit the test targets.** Determine the method, inputs, expected result, and which collaborators were replaced by mocks or fakes.
2. **Check fixtures and stubs.** Confirm mocks are configured with the right arguments, return values, and exceptions.
3. **Check collaborator outputs.** If mocked, what value did the test specify? If real, what input did the component receive and what did it return?
4. **Check collaborator calls.** Did the unit pass the right data, call all required collaborators, and follow the contract-required order?
5. **Run isolated tests for suspected components.** Use an appropriate database, HTTP stub, broker, or context to verify real implementations.
6. **Check wiring and configuration if failures only appear on integration.** Inspect which beans are injected, which profiles/properties are active, and which adapter is actually used.

The table below suggests the next scope to check:

| Where Failure Is Observed | Next Scope to Check |
|---|---|
| Unit test with stubbed collaborators | Unit logic, fixtures, arguments, and coordination rules |
| Adapter test with real dependencies | SQL, mapping, protocol, configuration, and adapter error handling |
| Spring context or slice test | Bean registration, dependency injection, profiles, properties, and auto-configuration |
| Multi-component integration test | Contracts and data crossing boundaries between components |
| Fails only in deployed environments | Environment config, credentials, endpoints, network, and downstream services |

There is no need to run the entire system immediately whenever one unit test fails. Start with the narrowest test capable of reproducing the discrepancy, then expand when evidence points to a collaboration boundary.

## Avoiding Both Extremes When Using Mocks

**Mocking every collaborator** keeps tests fast and isolated, yet can create an imaginary world where every dependency returns just what the test wants. A service might pass all unit tests while SQL is broken, a bean is unregistered, or an HTTP adapter fails to parse real responses.

**Mocking no collaborators** can turn a supposed unit test into one that actually boots a database, web server, and multiple services. On failure, it becomes hard to tell whether the bug lies in the logic under test or an external dependency.

A balanced approach:

- Keep pure Java domain objects and logic real when they are part of the rule under test.
- Replace I/O boundaries or external services with mocks, stubs, or fakes in unit tests.
- Write dedicated tests for adapters and components with significant technical implementations.
- Use Spring Test or Spring Boot Test when verifying wiring, configuration, and real bean interactions.
- Add integration tests for key contracts across components.

Not every collaborator needs a mock. If a collaborator is small, pure Java, and stable, using the real implementation can align tests more closely with actual behavior. What matters is knowing what a test covers and what still requires separate verification.

## A Failing Test Does Not Always Mean a Bug in Production Code

Tests themselves can be wrong: miscalculated expected values, invalid fixtures, misconfigured mock stubs, shared state across tests, or assertions tied to non-contract implementation details.

When a test fails, do not patch production code just to make the test pass before confirming the test accurately expresses requirements. Conversely, do not change expected values to accept buggy behavior. Cross-check against business rules and collaborator contracts, and identify the authoritative source of truth.

Test names should express specific behaviors and conditions, for example:

- `rejectsOrderWhenQuantityIsNotPositive`
- `doesNotSaveOrderWhenInventoryCannotReserve`
- `passesRequestedQuantityToInventory`
- `mapsDatabasePriceToProductUnitPrice`
- `propagatesInventoryUnavailableFailure`

Clear names help readers tell whether a test proves a business rule, a coordination contract, or a component implementation.

## Guidelines When Designing Unit Tests

Before concluding a test failed due to business logic or a collaborator, check:

- What unit is under test and what is its responsibility?
- Which collaborators are real, and which are replaced by test doubles?
- Do each collaborator's inputs and outputs match the contract?
- Does the unit make the right business decision given those outputs?
- When using real components, does the test isolate and control databases, networks, or related resources?
- Which test proves each collaborator's implementation works properly?
- When Spring is needed, has the test loaded the right context, beans, profiles, and properties?

Business logic failures are found by testing the application's decisions on known inputs and collaborator responses. Collaborator failures are found by testing dependency contracts, calls, and implementations at their own boundaries. Combining isolated unit tests with well-scoped component and integration tests pinpoints defects accurately while preventing mocks from creating false confidence.
