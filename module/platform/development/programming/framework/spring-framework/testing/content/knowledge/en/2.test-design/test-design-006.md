# Minimal and Readable Test Fixtures

A test can only deliver trustworthy results when its initial state is clear. When too much fixture data is prepared, readers struggle to see what actually drives the outcome. When data is missing or invalid, the test can fail because of how it was set up rather than because of the behavior under test.

In Spring Framework Testing, a *fixture* is the data and state prepared so a test can execute its scenario. Fixtures may include domain objects, database records, requests, configuration, or mocked dependencies. The goal is to create the exact context needed to test one behavior, written clearly enough that readers immediately understand the scenario.

## 1. What Is a Fixture?

Imagine a test that needs to verify the system can reserve two items in stock when available quantity exceeds requested quantity. Before calling the behavior under test, the test must have a stock object with a product code and initial quantity. That is fixture data.

A test typically has three steps:

1. **Arrange:** prepare the fixture, inputs, and required collaborators.
2. **Act:** perform the action under test.
3. **Assert:** verify the observable outcome.

Example:

```java
@Test
void reservesRequestedQuantityWhenStockIsAvailable() {
    Stock stock = new Stock("BOOK-01", 5);

    boolean reserved = stock.reserve(2);

    assertTrue(reserved);
    assertEquals(3, stock.getAvailableQuantity());
}
```

In this example, `new Stock("BOOK-01", 5)` is the fixture preparation. Calling `stock.reserve(2)` is the action. The two assertions verify the outcome.

A fixture does not have to be a separate class or a separate data file. It can be just a few initialization lines right inside the test. What matters is that the initial state is easy to understand and serves the exact scenario under test.

## 2. Why Should Fixtures Be Minimal?

A minimal fixture contains only the data needed to establish a valid state and trigger the behavior under test. Minimal does not mean creating objects missing required fields or bypassing domain rules. It means excluding unrelated data.

Suppose a test only checks inventory reservation for one product code. If the fixture also creates customers, shipping addresses, invoices, promotions, and several other products, readers must wade through information that contributes nothing to explaining the outcome.

Small fixtures help:

- Reveal the scenario's key condition immediately.
- Clarify why the expected outcome makes sense.
- Identify quickly which data to adjust when a test fails.
- Reduce dependencies and state that could cause unintended side effects.
- Keep tests from breaking when unrelated model attributes change.

You can use this question to decide whether a value belongs in a fixture: **If I remove this value, can the test still create a valid state and test the exact same behavior?** If yes, that value may not belong in this test's fixture.

Conversely, do not omit a field merely because assertions do not read it directly. That field may be required to construct a valid object, persist data via JPA, or pass Spring MVC validation. Fixtures must satisfy domain invariants and the contract of the component under test.

## 3. Characteristics of Readable Fixtures

### Highlight the Data That Drives the Outcome

Variable names and values should help readers spot the test condition. For instance, `availableQuantity = 5` and `requestedQuantity = 2` are easier to follow than numbers scattered across calls without context.

When a test has multiple values, give them meaningful names:

```java
int availableQuantity = 5;
int requestedQuantity = 2;

Stock stock = new Stock("BOOK-01", availableQuantity);

boolean reserved = stock.reserve(requestedQuantity);
```

This helps when a value is reused or when the variable name clarifies a business condition. For a very short test, passing values directly into a constructor can be concise and still clear. You do not need variables solely to replace every literal.

### Use Representative, Deterministic Values

Fixture values should clarify the scenario without mimicking production data. Using codes like `BOOK-01`, emails in the `example.test` domain, or fixed timestamps helps readers recognize test data and avoids relying on real information.

Avoid generating random data unless randomness itself is under test. When a test fails, fixed data makes reproducing and analyzing the root cause much easier.

### Respect Model Rules

If an object requires an identifier, status, and valid line items, the fixture must supply valid values for them. Do not use reflection to bypass constructors, disable validation, or construct states the application could never reach in normal operation.

A valid fixture lets the test observe real system behavior. An invalid fixture can cause the test to fail at a point unrelated to its target.

### Keep Data Close to Where It Is Used

If only one test needs special data, declare it directly inside that test. Readers can inspect Arrange and immediately see the scenario's condition without jumping through helpers or configuration classes.

When multiple tests share fixtures with the same meaning, consider extracting a factory method. The method name should describe the state it creates.

## 4. Start with Inline Fixtures in the Test

The simplest approach is usually instantiating objects directly in Arrange. This fits unit tests with few objects and short constructors especially well.

For example, a service test might use Mockito to replace the repository:

```java
@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    private StockRepository stockRepository;

    @InjectMocks
    private InventoryService inventoryService;

    @Test
    void reservesRequestedQuantityWhenStockIsAvailable() {
        Stock stock = new Stock("BOOK-01", 5);

        when(stockRepository.findBySku("BOOK-01"))
                .thenReturn(Optional.of(stock));

        boolean reserved = inventoryService.reserve("BOOK-01", 2);

        assertTrue(reserved);
        assertEquals(3, stock.getAvailableQuantity());
        verify(stockRepository).save(stock);
    }
}
```

The test's primary fixture is a `Stock` object with five units. The mock repository is configured to return that object when the service looks up `BOOK-01`. The action requests reserving two units; observable outcomes are success, three units remaining, and the repository saving the updated object.

The example assumes `InventoryService` uses `StockRepository` to load and save stock, and `Stock.reserve` updates quantity when sufficient stock exists. Domain and repository classes are omitted to focus on data setup.

Because data is written inline, there is no need to look up a helper to know how much stock existed initially. When only one test uses this scenario, inline setup is usually the most readable choice.

## 5. Extract Fixture Factory Methods When Repetition Appears

When multiple tests need to construct the same object type, repeating long constructors can make Arrange hard to read. A small factory method consolidates object creation in one place.

Example:

```java
private static Stock stockWithAvailableUnits(int quantity) {
    return new Stock("BOOK-01", quantity);
}
```

The test can be written as:

```java
@Test
void rejectsReservationWhenStockIsInsufficient() {
    Stock stock = stockWithAvailableUnits(1);

    when(stockRepository.findBySku("BOOK-01"))
            .thenReturn(Optional.of(stock));

    boolean reserved = inventoryService.reserve("BOOK-01", 2);

    assertFalse(reserved);
    assertEquals(1, stock.getAvailableQuantity());
    verify(stockRepository, never()).save(stock);
}
```

The name `stockWithAvailableUnits` tells what object is created, and the `quantity` parameter expresses the condition that varies across scenarios. Readers immediately understand this fixture represents stock with only one unit left.

A good factory should have a narrow scope and clear purpose:

- Name describes the object's state or role.
- Parameters represent the factors each test needs to vary.
- Internal defaults are valid and deterministic.
- Performs no extra business actions or external system calls.
- Does not hide critical scenario conditions.

Avoid generic names like `createData()`, `prepare()`, or `buildObject()` when they do not reveal what data is built. Also avoid methods with many boolean parameters, as a call like `createOrder(true, false, true, false)` obscures the intended state.

If only one test uses a fixture, do not extract a method just to save a few lines. A helper does not improve readability if readers must open it to learn the initial conditions.

## 6. When to Use a Builder or Test Data Builder?

An object with many attributes can lead to long constructors where important values are hard to spot. A builder lets you describe data by field name:

```java
Order order = Order.builder()
        .id("ORDER-100")
        .customerId("CUSTOMER-42")
        .status(OrderStatus.DRAFT)
        .build();
```

This is easier to read than a constructor taking several parameters of the same type. Still, a builder does not automatically make a fixture better. If an object has only two fields, adding a builder and a separate helper class can make tests longer and harder to follow.

A *Test Data Builder* is a builder placed in test code to produce data variations across scenarios. For instance, a builder can supply a valid default order, then let tests override the needed status or customer.

```java
private static OrderBuilder aDraftOrder() {
    return Order.builder()
            .id("ORDER-100")
            .customerId("CUSTOMER-42")
            .status(OrderStatus.DRAFT);
}
```

If it returns an actual builder, tests can customize attributes before calling `build()`:

```java
Order order = aDraftOrder()
        .customerId("CUSTOMER-99")
        .build();
```

This illustrates the organization pattern; `OrderBuilder` depends on the builder API provided by the project's model.

Builders fit well when:

- An object has many attributes and constructors are hard to read.
- Many tests need variations of the same object.
- Some attributes have valid default values.
- Tests need to intentionally override a few fields without repeating all data.

When using a builder, keep scenario-critical fields visible in the test. If order status determines the outcome, write `.status(OrderStatus.DRAFT)` or call an equivalently named method rather than hiding the status inside a builder default.

## 7. Use `@BeforeEach` Within the Right Scope

JUnit Jupiter provides `@BeforeEach` to run setup before each test method. It suits shared fixtures needed by most tests in the class.

```java
@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    private StockRepository stockRepository;

    @InjectMocks
    private InventoryService inventoryService;

    private Stock stock;

    @BeforeEach
    void setUp() {
        stock = new Stock("BOOK-01", 5);
    }

    @Test
    void reservesAvailableStock() {
        when(stockRepository.findBySku("BOOK-01"))
                .thenReturn(Optional.of(stock));

        boolean reserved = inventoryService.reserve("BOOK-01", 2);

        assertTrue(reserved);
        assertEquals(3, stock.getAvailableQuantity());
    }
}
```

Each test method receives a fresh `Stock` instance because `@BeforeEach` runs before every test. This prevents an earlier test from mutating quantity and affecting a subsequent test.

However, do not push every scenario's data into `setUp()`. If only one test needs empty stock, create that state inside that test or via a parameterized factory. If `setUp()` creates many objects unused by a test, readers struggle to identify each scenario's true preconditions.

A practical rule is: use `@BeforeEach` for common baseline setup, and keep scenario-specific data close to each test. When a class contains groups of tests with very different fixtures, consider splitting test classes by behavior so each class has simpler setup.

### Distinguishing `@BeforeEach` and `@BeforeAll`

`@BeforeEach` runs before every test method and usually fits creating mutable objects.

`@BeforeAll` runs once before all tests in the class. It can fit immutable shared data or expensive initialization. In JUnit Jupiter, a `@BeforeAll` method normally must be static unless the class uses `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`.

Do not put a shared mutable object in `@BeforeAll` if individual tests can mutate it. Sharing mutable state makes results depend on execution order and hurts reproducibility.

## 8. Fixtures in Spring Tests

Fixtures in Spring tests may be Java objects, requests sent via MockMvc, or records saved in a test database. How you prepare them depends on the scope the test aims to verify.

### For Service Unit Tests

Instantiate domain objects directly and configure mock dependencies. Create only the objects needed for the business branch under test. Mocks should return concrete, understandable data rather than long unrelated chains of behavior.

### For MVC Slice Tests

A test using `@WebMvcTest` can prepare request bodies, query parameters, or return values from mocked services. Requests should include the fields needed for the current scenario. If a test verifies required-field validation, omitting that field is intentional; remaining fields should still be valid so the observed error stems from the exact condition under test.

For example, a test for an order-creation endpoint can use a short JSON payload with only customer ID and required line items. There is no need to include response fields or metadata that clients do not send.

### For Persistence Slice Tests

A test using `@DataJpaTest` typically prepares entities via repositories before querying. Fixtures must satisfy entity and schema constraints.

```java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void findsProductBySku() {
        Product product = new Product(
                "BOOK-01",
                "Spring Testing",
                new BigDecimal("120000")
        );

        productRepository.save(product);

        Optional<Product> result =
                productRepository.findBySku("BOOK-01");

        assertTrue(result.isPresent());
        assertEquals("Spring Testing", result.orElseThrow().getName());
    }
}
```

The fixture here is one product with a valid SKU, name, and price. The test creates only one record because only one product is needed to verify SKU lookup. If the query must distinguish between two products, create a second record only then to express the distinguishing condition.

Slice tests like `@DataJpaTest` normally run inside a Spring Test-managed transaction and roll back after each test method. This prevents test data from accumulating across methods. If a test uses custom transactions, commits, async threads, or external resources, understand the corresponding cleanup mechanism; do not assume every Spring test rolls back data automatically.

### When Fixtures Require Many Related Records

A complex query scenario may need multiple related entities. You can create them with role-named factories, or place data in an SQL file when the dataset is large, stable, and easily expressed in SQL.

For instance, `@Sql` can load data from a script before a test. This is helpful when a test needs a specific relational structure or data shared by multiple tests. Still, SQL files are part of the fixture and should be readable, named after the scenario, and paired with an appropriate cleanup strategy.

Do not load a huge dataset for every test when each test only needs a couple of records. Excess data slows execution and obscures what caused the outcome.

## 9. Keep Fixtures Independent and Repeatable

A good fixture produces identical initial conditions on every test run. Shared state, system time, and random data are common sources of flaky results.

### Create Fresh Objects per Test

Mutable objects should be created fresh inside each test or in `@BeforeEach`. Avoid using a static object and mutating its fields across tests.

### Control Time

If logic depends on the current date, tests should not rely directly on the machine clock. Inject a `Clock` into the component under test and supply a fixed clock in tests:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

With time fixed, tests can determine exact timestamps for expiration calculations or overdue checks. If time is outside the test target, do not add a clock to the fixture.

### Control External Dependencies

If a test only verifies service logic, do not call a live HTTP service. Use mocks or fakes to control dependency responses. If the goal is verifying real HTTP or database integration, prepare the matching component in the fixture and environment; in that case, do not substitute the very component the test aims to verify.

Choosing mocks versus real resources depends on the test's question. Fixtures should reflect the exact scope of evidence the test intends to gather.

## 10. Fixture Patterns That Cause Confusion

| Practice | Problem | How to improve |
|---|---|---|
| Creating many unrelated objects | Obscures the data driving the outcome | Keep only data needed for the scenario |
| Generic helper names like `createData()` | Readers must open the helper to learn the state | Name after role or state |
| Many boolean parameters | Call sites hide what each value means | Use enums, named helpers, or descriptive builders |
| Shared mutable fixtures | Tests can interfere with one another | Create fresh fixtures per test |
| Uncontrolled current time or randomness | Results can vary between runs | Use fixed values or deterministic seeds |
| Putting all data into `@BeforeEach` | Individual tests are obscured by heavy setup | Keep scenario-specific data near the test |
| Defaulting too many critical fields | Test conditions become hidden | Explicitly state values that drive the outcome |
| Using invalid fixtures to bypass constructors | Test does not reflect states the app can create | Construct valid objects via public APIs |

A common mistake is writing an overly general helper to serve every scenario. The helper ends up taking ten parameters, most of them booleans or empty strings. Over time, readers can no longer tell what state each call produces. When fixtures have genuinely distinct variants, consider specifically named factories like `anActiveCustomer()`, `anExpiredSubscription()`, or `aDraftOrder()`.

Nor should every test be forced to share one fixture simply because they test the same class. Two different behaviors may need different initial states. Fixtures should serve each test's goal, while shared setup holds only genuinely identical structure.

## 11. Evolving Fixtures from Simple to Fit-for-Purpose

You do not need to design a full data-generation framework before writing your first test. Start with inline data and extract only when there is a clear reason:

1. Write the test with data directly in Arrange so the scenario stands out clearly.
2. Assign variables to important values or values that look cryptic inline.
3. When multiple tests repeat the same object construction, extract a descriptively named factory.
4. When objects have many fields or variants, consider a builder.
5. When multiple tests genuinely need the same baseline setup, move that baseline into `@BeforeEach`.
6. When data involves databases or external resources, choose fixture loading and cleanup strategies matching the transaction and test scope.

After each extraction, the test itself should still show the critical conditions. If readers must trace through multiple helper layers to see what state a test uses, abstraction has gone too far.

Minimal and readable fixtures let a test tell its story through concrete data: what state the system starts in, what action runs, and what outcome must be verified. When setup is clear, readers can focus on the protected behavior and interpret PASS or FAIL results in the right context.

