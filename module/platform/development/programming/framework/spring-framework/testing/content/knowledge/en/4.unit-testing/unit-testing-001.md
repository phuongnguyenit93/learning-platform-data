# Creating Domain Objects Directly with Constructors

In unit testing, we often only need a real domain object to invoke a method and observe the result. Create that object directly using a Java constructor with the `new` keyword. This keeps the test focused on the class's behavior without starting the Spring container, scanning components, or loading the entire application configuration.

For example, when testing `OrderService`, you can write `new OrderService(repository)` and pass in a mock repository. When testing `Money` or `Order`, you create those exact domain objects using their constructors with concrete data. Spring still plays the role of wiring beans when the application runs, but that wiring belongs to a different kind of test.

## Learning Objectives

After this lesson, you will be able to:

- Explain why unit tests usually create the object under test with `new`.
- Distinguish between Java constructors and Spring's bean creation mechanism.
- Create domain objects with controlled data and verify invariants in constructors.
- Pass dependencies via constructors when testing a service or a class that needs collaborators.
- Combine real objects with mocks, stubs, or fakes at the right boundaries.
- Organize test data using helpers or fixtures while keeping each test independent.
- Recognize when a Spring context test is needed instead of a plain Java unit test.

## 1. A Constructor Is Where an Object's Initial State Is Established

In Java, the `new` operator allocates an object and invokes the corresponding constructor. The constructor receives the values needed to establish the initial state. Once the constructor finishes, the object can be used according to the contract published by the class.

For example, a value object representing a quantity:

~~~java
public final class Quantity {

    private final int value;

    public Quantity(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        this.value = value;
    }

    public int value() {
        return value;
    }
}
~~~

A unit test creates the object directly:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void keepsTheProvidedPositiveValue() {
        Quantity quantity = new Quantity(3);

        assertEquals(3, quantity.value());
    }

    @Test
    void rejectsZeroAtConstructionTime() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Quantity(0)
        );
    }
}
~~~

The test does not need any Spring annotations. It calls the class's public constructor directly and verifies both parts of the contract: valid values are retained, while invalid values are rejected upon object creation.

This is a key benefit of direct instantiation: the test clearly shows which object is created, which constructor is called, and what the initial data is.

## 2. Domain Objects Do Not Need Spring to Exist

A class modeling business logic can be a plain Java object. For example:

~~~java
public final class Money {

    private final long amountInCents;
    private final String currency;

    public Money(long amountInCents, String currency) {
        if (amountInCents < 0) {
            throw new IllegalArgumentException(
                "Amount cannot be negative"
            );
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException(
                "Currency is required"
            );
        }

        this.amountInCents = amountInCents;
        this.currency = currency;
    }

    public long amountInCents() {
        return amountInCents;
    }

    public String currency() {
        return currency;
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }

        return new Money(
            amountInCents + other.amountInCents,
            currency
        );
    }
}
~~~

A test can construct two money values directly and verify addition:

~~~java
class MoneyTest {

    @Test
    void addsAmountsWithTheSameCurrency() {
        Money first = new Money(1250, "VND");
        Money second = new Money(750, "VND");

        Money total = first.add(second);

        assertEquals(2000, total.amountInCents());
        assertEquals("VND", total.currency());
    }

    @Test
    void rejectsDifferentCurrencies() {
        Money first = new Money(1250, "VND");
        Money second = new Money(500, "USD");

        assertThrows(
            IllegalArgumentException.class,
            () -> first.add(second)
        );
    }
}
~~~

`Money` does not need to know what Spring is. It does not need `@Component`, `@Service`, or `@Autowired` to test money addition rules. The public constructor and methods are sufficient to establish state and execute behavior.

Objects commonly created directly in unit tests include:

- Domain entities and aggregates.
- Value objects such as money, addresses, identifiers, and time intervals.
- Plain Java DTOs or commands.
- Validators, mappers, and calculators with no container dependencies.
- Services or policies that accept collaborators via constructors.

Do not add Spring dependencies to a class just so a test can create it. If an object only needs input data and Java rules, keep object creation simple.

## 3. Creating the Object Under Test and Passing Data Explicitly

A unit test should show the reader the object's input state. Pass data through the constructor rather than creating an empty object and mutating multiple fields afterward.

For example, an order:

~~~java
public final class Order {

    private final String orderNumber;
    private final String customerId;
    private final Quantity quantity;

    public Order(
            String orderNumber,
            String customerId,
            Quantity quantity) {

        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                "Order number is required"
            );
        }
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                "Customer id is required"
            );
        }

        this.orderNumber = orderNumber;
        this.customerId = customerId;
        this.quantity = Objects.requireNonNull(
            quantity,
            "quantity"
        );
    }

    public String orderNumber() {
        return orderNumber;
    }

    public String customerId() {
        return customerId;
    }

    public Quantity quantity() {
        return quantity;
    }
}
~~~

A test can prepare the entire state right at the creation site:

~~~java
class OrderTest {

    @Test
    void exposesTheValuesUsedToCreateTheOrder() {
        Order order = new Order(
            "ORD-1001",
            "CUS-42",
            new Quantity(2)
        );

        assertEquals("ORD-1001", order.orderNumber());
        assertEquals("CUS-42", order.customerId());
        assertEquals(2, order.quantity().value());
    }

    @Test
    void requiresAQuantity() {
        assertThrows(
            NullPointerException.class,
            () -> new Order("ORD-1001", "CUS-42", null)
        );
    }
}
~~~

This style makes it clear which data belongs to the object. If the constructor enforces invariants, the test also exercises the exact valid-state creation path used by production code.

In real-world examples, a class might use a `record`, a multi-parameter constructor, or a constructor taking a command object. Regardless of the form, prefer the object-creation API that production code actually calls. Do not use reflection to assign private fields or bypass validation just to construct a state that the application could not normally produce.

## 4. Creating Services Directly and Passing Dependencies via Constructor

A service often needs a repository, a gateway, or another collaborator. A unit test can still create the service via its constructor; the passed dependency can be a simple real object, a fake, or a mock depending on the goal.

Example service:

~~~java
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Order place(
            String orderNumber,
            String customerId,
            int quantityValue) {

        Quantity quantity = new Quantity(quantityValue);

        Order order = new Order(
            orderNumber,
            customerId,
            quantity
        );

        return repository.save(order);
    }
}
~~~

The interface the service depends on:

~~~java
public interface OrderRepository {
    Order save(Order order);
}
~~~

The test creates the service directly and passes a mock into the constructor:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Test
    void createsAnOrderAndSendsItToTheRepository() {
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        OrderService service = new OrderService(repository);

        Order result = service.place(
            "ORD-1001",
            "CUS-42",
            2
        );

        assertEquals("ORD-1001", result.orderNumber());
        assertEquals("CUS-42", result.customerId());
        assertEquals(2, result.quantity().value());

        verify(repository).save(any(Order.class));
    }

    @Test
    void doesNotSaveAnOrderWithInvalidQuantity() {
        OrderService service = new OrderService(repository);

        assertThrows(
            IllegalArgumentException.class,
            () -> service.place("ORD-1001", "CUS-42", 0)
        );

        verifyNoInteractions(repository);
    }
}
~~~

The key line to note is `new OrderService(repository)`. The test decides for itself which dependency is passed in. There is no need for Spring component scanning, no need to create an application context, and no need to start a database.

`@Mock` here only instructs Mockito to create a mock repository. It does not create the service. The test itself calls the constructor to create the service under test.

## 5. Choosing a Real Object, Mock, Stub, or Fake for a Dependency

When creating an object via its constructor, all constructor parameters must be supplied. Not every dependency should be mocked. Choose the creation approach based on the behavior the test needs to verify.

| Dependency Type | Common Approach | When Appropriate |
|---|---|---|
| Simple value object or entity | Create real instance with `new` | Its behavior and state are part of what the test needs |
| Plain Java calculator or policy | Create real instance with `new` | Simple, stable logic requiring no infrastructure |
| Repository or gateway | Mock or fake | Want to isolate the service from a database or external system |
| Clock or time source | Pass `Clock.fixed(...)` | Need deterministic date/time test results |
| ID generator or UUID | Stub/fake with fixed output | Need to verify results without randomness |
| Network client or external system | Mock or fake | Do not want to send real requests in unit tests |

### Mock: verifying interactions with a collaborator

A mock is appropriate when you need to verify that the service calls a dependency with the right data, or does not call the dependency on invalid input. In the example above, `verify(repository).save(...)` confirms the save behavior.

Do not mock value objects just to avoid calling their constructors. A real `Money` or `Quantity` is usually simpler and more reliable than a mock, because the test exercises the actual logic of the value object.

### Stub: providing fixed answers

A stub supplies predefined responses so the test takes a specific branch. Mockito can configure stubs using `when(...).thenReturn(...)` or `thenAnswer(...)`.

### Fake: a substitute dependency with real behavior

A fake is a lightweight implementation that can run in memory. For example, a fake repository storing orders in a `Map` lets a service test verify save and lookup flows without a database:

~~~java
class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.orderNumber(), order);
        return order;
    }

    public Optional<Order> findByOrderNumber(String orderNumber) {
        return Optional.ofNullable(orders.get(orderNumber));
    }
}
~~~

A test can create both the fake and the service directly:

~~~java
@Test
void savesAnOrderInTheInMemoryRepository() {
    InMemoryOrderRepository repository =
        new InMemoryOrderRepository();

    OrderService service = new OrderService(repository);

    Order saved = service.place(
        "ORD-1001",
        "CUS-42",
        2
    );

    assertTrue(
        repository.findByOrderNumber("ORD-1001").isPresent()
    );
    assertEquals("ORD-1001", saved.orderNumber());
}
~~~

Fakes are useful when multiple tests need meaningful collaboration behavior. However, a fake only simulates the required contract; it does not prove that SQL queries, transactions, or real database mappings work. Those require separate persistence tests.

## 6. Constructors Help Tests Control Time and Varying Data

If a service calls `LocalDate.now()`, `Instant.now()`, or `UUID.randomUUID()` directly, tests may receive different results depending on the time or run. You can keep logic deterministic by passing the time source or identifier source through the constructor.

Example service using `Clock`:

~~~java
public class SubscriptionService {

    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate renewalDate(int trialDays) {
        if (trialDays < 0) {
            throw new IllegalArgumentException(
                "Trial days cannot be negative"
            );
        }

        return LocalDate.now(clock).plusDays(trialDays);
    }
}
~~~

A test passing a fixed clock:

~~~java
@Test
void calculatesRenewalDateFromTheInjectedClock() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-01-10T00:00:00Z"),
        ZoneOffset.UTC
    );

    SubscriptionService service =
        new SubscriptionService(clock);

    assertEquals(
        LocalDate.of(2026, 1, 17),
        service.renewalDate(7)
    );
}
~~~

The constructor makes the time source an explicit dependency. Each test can create a new service with a fixed clock tailored to its case.

The same principle applies to:

- `Supplier<UUID>` or an `IdGenerator` interface.
- Exchange rate or reference data sources.
- Random generators with a fixed seed.
- Configuration readers or calculation strategies.

There is no need to create an abstraction for every Java call. Only pass a dependency via constructor when controlling it genuinely makes the logic easier to test, replace, or configure.

## 7. Organizing Constructor Arguments and Test Data

When a constructor takes many parameters, data setup can make tests verbose. You can use test-specific helpers or factories, provided the helper keeps important state clearly visible.

Example helper creating a valid order:

~~~java
class OrderTest {

    private Order anOrder() {
        return new Order(
            "ORD-1001",
            "CUS-42",
            new Quantity(2)
        );
    }

    @Test
    void exposesTheOrderNumber() {
        Order order = anOrder();

        assertEquals("ORD-1001", order.orderNumber());
    }
}
~~~

Helpers work well when multiple tests share a default configuration and differ only in the behavior under test. If a test needs special data, create it directly in the test or pass arguments into the helper so the difference stands out clearly.

Example parameterized helper:

~~~java
private Order anOrder(
        String orderNumber,
        String customerId,
        int quantity) {

    return new Order(
        orderNumber,
        customerId,
        new Quantity(quantity)
    );
}
~~~

A test can call:

~~~java
Order order = anOrder("ORD-2002", "CUS-77", 5);
~~~

For objects with many fields, a test data builder can improve readability:

~~~java
class OrderBuilder {

    private String orderNumber = "ORD-1001";
    private String customerId = "CUS-42";
    private int quantity = 2;

    OrderBuilder withOrderNumber(String value) {
        this.orderNumber = value;
        return this;
    }

    OrderBuilder withCustomerId(String value) {
        this.customerId = value;
        return this;
    }

    OrderBuilder withQuantity(int value) {
        this.quantity = value;
        return this;
    }

    Order build() {
        return new Order(
            orderNumber,
            customerId,
            new Quantity(quantity)
        );
    }
}
~~~

Usage:

~~~java
Order order = new OrderBuilder()
    .withOrderNumber("ORD-2002")
    .withCustomerId("CUS-77")
    .withQuantity(5)
    .build();
~~~

A builder is only a data preparation tool. It should not obscure the behavior the test aims to verify. If a test only needs three parameters, calling the constructor directly is usually clearer than a long builder.

Avoid sharing a single mutable object across multiple tests. One test mutating a field can make other tests depend on execution order. Create a fresh instance in each test or in `@BeforeEach`, and avoid holding mutable state in `static` fields.

## 8. Public Constructors, Factory Methods, and Domain Invariants

Not every class needs a public constructor. Some domain objects may require creation through a factory method to express conditions clearly or protect state-creation rules.

For example:

~~~java
public final class EmailAddress {

    private final String value;

    private EmailAddress(String value) {
        this.value = value;
    }

    public static EmailAddress of(String value) {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email address"
            );
        }

        return new EmailAddress(value);
    }

    public String value() {
        return value;
    }
}
~~~

Tests should invoke the object-creation API that consumers of the class are allowed to use:

~~~java
@Test
void createsAnEmailAddressFromAValidValue() {
    EmailAddress email = EmailAddress.of("ada@example.com");

    assertEquals("ada@example.com", email.value());
}
~~~

Here the test does not call the private constructor. The factory method is the object-creation entry point published by the class. The spirit remains the same as direct constructor invocation: the test creates a real object using Java APIs without relying on the Spring container.

When a constructor or factory performs validation, test both valid and invalid inputs. When an object has multiple domain states, test each valid creation path instead of forcing fields to reach that state.

For entities with a lifecycle, the constructor may establish the initial state, while subsequent domain methods transition state. Create the entity via its constructor or factory and invoke public behaviors in the proper domain sequence. Do not modify private fields directly with reflection.

## 9. Comparing Object Creation in Unit Tests and Spring Tests

Three mechanisms are commonly confused:

| Creation Approach | Who Creates the Object? | Appropriate Scope |
|---|---|---|
| `new MyService(dependency)` | The test invokes the Java constructor | Unit tests for class logic |
| `@InjectMocks` | Mockito instantiates the object and injects mocks according to its rules | Unit tests when you want Mockito to handle initialization |
| `@Autowired` in a Spring test | The Spring container provides the bean | Testing configuration, wiring, and context-dependent behavior |

### Direct creation with `new`

The test explicitly creates the instance and passes the exact dependencies:

~~~java
OrderService service = new OrderService(repository);
~~~

This is easy to read, has no hidden initialization steps, and lets the compiler check constructor parameters.

### Using `@InjectMocks`

Mockito can instantiate the class under test and attempt to inject matching mocks or spies. This is convenient when a class has many dependencies, though instantiation is no longer explicit at the object creation line. If you need to see exactly which dependencies are passed, call the constructor yourself.

Both approaches can be used in unit tests; neither requires a Spring context.

### Using `@Autowired`

`@Autowired` asks Spring to supply a bean from the context. This is the right choice when the test question is whether Spring selects the right bean, applies the right scope, activates the right profile, or wires dependencies properly.

A plain Java unit test does not need `@Autowired`. If a test uses `@SpringBootTest`, it has moved into context or integration test scope.

## 10. When Is Direct Instantiation Not Enough?

Creating objects with constructors verifies the object's Java logic and how it uses test-provided dependencies. It does not verify that Spring configures beans correctly.

Use Spring TestContext or Spring Boot tests when you need to verify:

- Whether component scanning discovers the required classes.
- Whether Spring selects the right implementation for an interface.
- Whether `@Qualifier`, `@Primary`, profiles, or conditional configurations work.
- Whether beans are created with the intended scope and lifecycle.
- Whether configuration properties are bound properly.
- Whether proxies, transactions, AOP, or container-dependent features are applied.

For example, if you need to verify that two `PaymentGateway` implementations are selected by qualifier, creating the service with `new` cannot answer that question. Start a small test context and inject the beans under real configuration.

Conversely, if a test only wants to check that `OrderService` rejects a zero quantity before saving, booting the entire application is far too broad. Creating the service directly with a mock repository is enough.

## 11. Common Mistakes

- **Booting Spring for every unit test:** creating a context makes tests slow and obscures the logic under test. Create plain Java objects when a class does not depend on the container.
- **Using an empty constructor and mutating fields with setters:** intermediate state may be invalid, and the test no longer reflects how production creates the object.
- **Mocking every object:** value objects and simple domain objects should be real instances so the test exercises their real behavior.
- **Using a different constructor than production:** the test might bypass validation or required dependencies. Call the object-creation API that application code actually uses.
- **Generating random data or depending on system time:** results become hard to reproduce. Pass a fixed clock, generator, or deterministic data when needed.
- **Sharing mutable fixtures:** tests can affect one another. Create fresh instances for each test.
- **Mocking concrete implementations instead of boundaries:** mocking a repository or gateway through its interface keeps boundaries clear and reduces coupling to internal details.
- **Assuming `new` tests Spring wiring:** calling a constructor directly does not run component scanning, resolve qualifiers, or apply bean lifecycles.
- **Using reflection to bypass constructors:** the test creates states that production code cannot produce, making results less trustworthy.
- **Adding too many constructor dependencies without reviewing the design:** this may indicate a class is taking on too many responsibilities. Review the design when it surfaces in real code rather than adding an extra constructor just to make tests easier to write.

## 12. Workflow for Writing Unit Tests with Direct Constructors

When testing a class, you can follow this sequence:

1. Identify the class under test and the public behavior to verify.
2. Read the constructor to see required data and dependencies to pass.
3. Create real value objects or domain objects via public constructors or factory methods.
4. Create real collaborators if simple; use mocks, stubs, or fakes for boundaries to isolate.
5. Call the constructor of the class under test right inside the test or a readable helper.
6. Exercise a single behavior to test.
7. Assert the outcome and meaningful interactions with collaborators.
8. Create fresh instances for other tests to avoid shared state.
9. If the question shifts to Spring wiring or lifecycle, move to a separate context test.

For example, with `OrderService`, each test can create a new service from a mock repository, pass a clear set of data, and verify one behavior. Tests for `Order` or `Quantity` can create those objects directly without setting up a service or Spring.

## Conclusion

Creating domain objects directly with constructors is the natural way to write unit tests for Java objects. The test explicitly chooses the data, creates real instances, and passes the necessary dependencies. This keeps the test scope small, results repeatable, and failure causes easy to isolate.

When you need to test a class's logic, use its public constructor or factory method to create the object. When you need to verify how Spring wires beans, profiles, proxies, or lifecycles, use Spring TestContext. Separating these two goals ensures each test answers a clear question.

