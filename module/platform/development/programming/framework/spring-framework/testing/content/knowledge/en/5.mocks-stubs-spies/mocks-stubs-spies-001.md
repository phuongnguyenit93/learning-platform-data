# Distinguishing Real Objects, Fakes, Stubs, Mocks, and Spies

When testing a Spring application, a class often collaborates with a repository, HTTP client, payment gateway, message publisher, clock, or other services. If every test connects to real dependencies, test execution becomes slow, hard to isolate, and easily affected by the environment. If all dependencies are replaced with mocks, tests may run fast but overlook the actual behavior of the components.

To choose an appropriate replacement, it is necessary to distinguish five concepts: **real object, fake, stub, mock, and spy**. They describe different ways to provide or observe the behavior of a dependency in a test.

Fakes, stubs, mocks, and spies are collectively referred to as *test doubles* (replacement objects in testing). A Mockito object can act as a stub in one test and as a mock in another, depending on how the test uses it. The API name does not determine the role; the purpose of the check determines it.

## 1. Real Object

A real object is the actual implementation used by the application. It performs the real behavior of that class or component, such as:

- A service that calculates fees according to business rules.
- A JPA repository that queries the database.
- An HTTP client that sends requests to another service.
- An adapter that writes messages to a broker.
- A formatter that converts data according to application configuration.

For example, a Spring Data JPA repository is a real component when a test calls the repository created by Spring and it accesses the database configured for the test.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesAndFindsAnOrder() {
        var order = new OrderEntity("order-18", "customer-7");

        OrderEntity saved = repository.save(order);

        Optional<OrderEntity> loaded =
                repository.findById(saved.getId());

        assertTrue(loaded.isPresent());
        assertEquals("customer-7", loaded.get().getCustomerId());
    }
}
~~~

Here, the repository is not a mock. Spring provides the repository implementation, and it performs persistence operations in the database used by the test.

**Advantages**

- Verifies the actual behavior of the implementation.
- Can catch configuration, mapping, transaction, query, or cross-component interaction errors.
- Increases representativeness of the real application environment when the test uses the right kind of infrastructure.

**Costs and limitations**

- May require a Spring context, database, network, or supporting services.
- Execution and setup time are usually higher than tests using replacement objects.
- Results can depend on data, environment state, and the stability of external services.
- Hard to reproduce some rare failure scenarios, such as timeouts or abnormal responses from third-party services.

Real objects are appropriate when integration behavior itself is what needs to be verified. If testing a pure Java calculation rule, starting a database only increases cost without adding necessary evidence.

## 2. Fake: a simple implementation with real behavior

A **fake** is a working implementation, usually simpler than the production implementation, that may omit certain characteristics of the real environment.

A fake does not merely return a fixed value. It can hold state and perform basic operations according to the interface contract.

For example, the application has a repository interface:

~~~java
public interface OrderRepository {
    Optional<Order> findById(String id);

    void save(Order order);
}
~~~

In production, the implementation may use JPA and a database. In a unit test, we can create a fake that stores data in memory:

~~~java
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }
}
~~~

This fake supports saving and finding orders. It can be used across many tests as a small repository without needing a database.

~~~java
@Test
void retrievesAnOrderThatWasPreviouslySaved() {
    OrderRepository repository = new InMemoryOrderRepository();
    var order = new Order("order-18", OrderStatus.PENDING);

    repository.save(order);

    assertEquals(Optional.of(order), repository.findById("order-18"));
}
~~~

A fake implements part of the contract by simplifying storage or processing. It might use a Map instead of a database, an in-memory list instead of a message broker, or a simple router instead of a real routing service.

Therefore, a fake can verify service logic when the service collaborates with an interface, but it does not prove that the production implementation works correctly. InMemoryOrderRepository does not test SQL, transactions, constraints, indexes, locking, or JPA mappings.

**When should you use a fake?**

- When you need a stateful dependency so multiple operations in a test work together.
- When multiple tests need the same simple, reusable implementation.
- When you want to test a service through an interface without configuring complex mocks for every call.
- When in-memory data is sufficient to simulate the behavior the test cares about.

A fake should be kept simple. If a fake starts simulating all database transactions, locking, queries, and rules, it becomes a second implementation that is hard to maintain and risks diverging from production.

## 3. Stub: providing predefined responses

A **stub** provides predefined answers to calls made by the object under test. Its main purpose is to control indirect inputs to the test so it can focus on the behavior of the class being tested.

For example, OrderService needs to ask PaymentGateway for the payment result. In the test, we want to simulate the case where the payment gateway declines the transaction:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void rejectsOrderWhenPaymentIsDeclined() {
        var order = new Order("order-18", OrderStatus.PENDING);

        when(orderRepository.findById("order-18"))
                .thenReturn(Optional.of(order));

        when(paymentGateway.charge(order))
                .thenReturn(PaymentResult.declined());

        OrderResult result = orderService.pay("order-18");

        assertEquals(OrderStatus.REJECTED, result.status());
    }
}
~~~

The two **when(...).thenReturn(...)** configurations set up responses for the dependencies: the repository returns a known order and PaymentGateway returns a declined result. In this test, the PaymentGateway mock is being used in the role of a stub because the test needs a predefined answer. The goal of the assertion is to confirm that OrderService handles the declined result according to business rules.

### Hand-written stubs

A stub does not have to be created with Mockito. You can write a small implementation that only returns a configured response:

~~~java
class DecliningPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(Order order) {
        return PaymentResult.declined();
    }
}
~~~

This implementation is a stub if its goal is to provide a fixed response for a test scenario.

A stub can have one or a few preconfigured branches. For example, a stub might return success for one order ID and decline for another. When the number of scenarios grows, consider using a fake or explicit mock configuration to avoid creating a hand-written stub with too many conditionals.

**Advantages**

- Controls dependency responses.
- Easy to simulate errors, timeouts, empty data, or special states.
- Helps the test focus on the outcome of the class under test.
- Does not require calling external services.

**Limitations**

- A stub does not prove the real dependency will return such data in a real environment.
- A stub typically does not verify whether a call occurred or occurred the right number of times.
- If the stub response no longer matches the dependency contract, the test can create an unrealistic scenario.

Stubs are appropriate when the important thing is checking how the class under test reacts to a known response.

## 4. Mock: verifying interactions with dependencies

A **mock** is a replacement object configured to record calls and allow the test to verify meaningful interactions. A test can check that a method was called, what arguments were passed, or how many times it was called.

For example, when payment succeeds, OrderService must save the order with status PAID:

~~~java
@Test
void savesOrderAfterSuccessfulPayment() {
    var order = new Order("order-18", OrderStatus.PENDING);

    when(orderRepository.findById("order-18"))
            .thenReturn(Optional.of(order));

    when(paymentGateway.charge(order))
            .thenReturn(PaymentResult.approved());

    orderService.pay("order-18");

    verify(orderRepository).save(
            argThat(saved -> saved.status() == OrderStatus.PAID)
    );
}
~~~

Here, the test uses mocks to supply data and check that OrderRepository receives an order that has transitioned to the PAID status.

Some commonly used interaction assertions in Mockito:

~~~java
verify(repository).save(order);

verify(repository, times(2)).save(any());

verify(repository, never()).delete(any());

verify(repository, atLeastOnce()).save(any());
~~~

These methods verify calls and invocation counts. Choose a verification level that reflects the contract you need to protect.

### How do stubs and mocks differ?

These two concepts are often confused because Mockito uses the same mock object to set up responses and verify calls.

| Aspect | Stub | Mock |
|---|---|---|
| Primary purpose | Provide predefined responses | Verify interactions |
| Test question | What does the dependency return? | Did the class under test call the dependency properly? |
| Common usage | when(...).thenReturn(...) | verify(...) |
| Assertion focus | Outcome or state of the class under test | Calls, arguments, invocation counts, or meaningful ordering |

A Mockito mock configured with **when(...).thenReturn(...)** without any **verify(...)** assertion may be acting as a stub. If the test uses **verify(...)** to check calls, it is acting as a mock in the interaction-testing sense.

Therefore, stubs and mocks should not be thought of as necessarily two separate kinds of classes. They are two common roles of test doubles.

### When should you verify interactions?

Verifying interactions makes sense when the call itself is part of the behavior to protect, for example:

- A service must send a message after a transaction is confirmed.
- A repository must save changes when a business operation completes.
- A payment service must not be called when input data is invalid.
- An email-sending operation must be executed only once in a specific scenario.

Do not verify every internal call just because Mockito allows it. If a test checks that a service calls three helpers in an exact internal order, refactoring can break the test even though external behavior remains correct.

Prefer checking observable outcomes. Only verify interactions when the interaction itself has business significance or is a contract between components.

## 5. Spy: keeping real behavior and observing calls

A **spy** is an object that wraps an instance with real behavior. Methods typically run the real implementation by default, while Mockito allows verifying calls or overriding the behavior of specific methods.

A simple example with a list:

~~~java
@Test
void spyKeepsRealListBehaviorAndRecordsInteraction() {
    List<String> events = spy(new ArrayList<>());

    events.add("order-created");

    assertEquals(List.of("order-created"), events);
    verify(events).add("order-created");
}
~~~

The list still performs the real ArrayList behavior: the element is added and can be read back. At the same time, the test can verify that the add method was called.

### A spy can override part of the behavior

A spy also allows stubbing a specific method while other methods still run for real. For example, a service that reads system time can be spied to fix the time in a test:

~~~java
class SystemTimeProvider {
    Instant now() {
        return Instant.now();
    }
}
~~~

~~~java
@Test
void usesFixedTimeFromSpy() {
    SystemTimeProvider timeProvider = spy(new SystemTimeProvider());
    Instant fixedTime = Instant.parse("2026-04-12T10:00:00Z");

    doReturn(fixedTime).when(timeProvider).now();

    assertEquals(fixedTime, timeProvider.now());
    verify(timeProvider).now();
}
~~~

In this example, the spy is created from a real object, but the now() method is replaced with a fixed result. Other unstubbed methods can still run the real implementation.

When using a spy, there is an important detail: the syntax **when(spy.method()).thenReturn(value)** can invoke the real method during stub setup. If the real method has side effects, performs I/O, or throws an exception, setting up the test can trigger unintended effects.

With a spy, you should generally use the **doReturn(...).when(spy).method(...)** form when you need to stub a method without calling the real implementation during setup.

**Risks of using spies**

- Real methods may perform side effects such as writing files, making network calls, or updating state.
- Tests can become coupled to many internal details of the object.
- Partially stubbing behavior can make the object operate in a state that does not match production.
- A complex spy is often a sign that the class is doing too much or has hard-to-replace dependencies.

Spies are useful when you need to keep most of the real behavior and only observe or replace a small part. If you have to stub many methods on a spy, consider extracting an interface or collaborator so the test has clearer boundaries.

## 6. Quick comparison of the five concepts

| Object type | Primary behavior | Executes real logic? | Commonly used to |
|---|---|---|---|
| Real object | Production implementation | Yes | Verify real behavior and integration |
| Fake | Simplified replacement implementation | Yes, but simplified | Simulate stateful dependencies |
| Stub | Returns predefined responses | Usually does not execute real dependency logic | Control input scenarios |
| Mock | Records and verifies interactions | Usually no | Verify calls and side effects |
| Spy | Tracks an instance with real behavior | Yes by default | Observe or replace part of the behavior |

You can remember them with five questions:

- **Real object**: how does the real implementation behave?
- **Fake**: can a simplified implementation satisfy the required contract?
- **Stub**: if the dependency returns this data, how does the class under test react?
- **Mock**: did the class under test perform the required interaction?
- **Spy**: can we keep real behavior while still observing or overriding part of the calls?

## 7. A running example: OrderService and types of test doubles

Suppose OrderService depends on OrderRepository and PaymentGateway:

~~~java
public class OrderService {

    private final OrderRepository repository;
    private final PaymentGateway paymentGateway;

    public OrderService(
            OrderRepository repository,
            PaymentGateway paymentGateway) {
        this.repository = repository;
        this.paymentGateway = paymentGateway;
    }

    public OrderResult pay(String orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        PaymentResult payment = paymentGateway.charge(order);

        if (payment.approved()) {
            order.markPaid();
        } else {
            order.reject();
        }

        repository.save(order);

        return new OrderResult(order.id(), order.status());
    }
}
~~~

The same behavior can be tested in multiple ways.

### Using real objects

Start the Spring context, use a real repository, and use a PaymentGateway that may connect to a sandbox or test service. The test verifies that the components actually work together. This approach suits integration tests, though it requires managing data and environment state.

### Using a fake repository

Create InMemoryOrderRepository to store orders in a Map. The service can find, update, and save orders via real in-memory operations. This approach is suited for testing service logic without a database.

### Using a stub payment gateway

Configure PaymentGateway to return approved or declined. The test checks that OrderService transitions state accordingly. This makes it easy to control business branches.

### Using a mock repository

Use **verify(repository).save(...)** to verify that the service saves the order after processing payment. You can also verify that the repository is not called if the order does not exist or input is rejected before the save operation.

### Using a spy

If you have a real component with suitable behavior but need to observe certain calls, you can create a spy for it. For example, spy on an in-memory event recorder to verify that the publish method is called while preserving the real event-storing behavior.

You do not need to use all five types in the same test. Each type answers a different question. A unit test may use a fake repository and a stub payment gateway; an integration test may use a real repository and a stubbed payment service; another separate test may verify publish interactions with a mock.

## 8. Using Mockito in unit tests

Mockito provides common annotations and APIs:

| API | Meaning |
|---|---|
| @Mock | Creates a mock |
| @Spy | Creates a spy from an instance or instantiated object |
| @InjectMocks | Creates the object under test and attempts to inject matching mocks/spies |
| when(...).thenReturn(...) | Configures a response for a mock |
| doReturn(...).when(...) | Configures a response using syntax suitable for spies |
| verify(...) | Verifies interactions |
| ArgumentCaptor | Captures arguments passed into a call |
| reset(...) | Clears mock state; usually best avoided if you can create fresh mocks per test |

JUnit Jupiter can integrate Mockito via MockitoExtension:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService service;

    @Test
    void returnsPaidWhenPaymentIsApproved() {
        var order = new Order("order-18", OrderStatus.PENDING);

        when(repository.findById("order-18"))
                .thenReturn(Optional.of(order));

        when(paymentGateway.charge(order))
                .thenReturn(PaymentResult.approved());

        OrderResult result = service.pay("order-18");

        assertEquals(OrderStatus.PAID, result.status());
        verify(repository).save(order);
    }
}
~~~

**@InjectMocks** lets Mockito construct OrderService with matching mock dependencies. It is not Spring dependency injection and does not start an ApplicationContext.

If the object under test has a clear constructor and only a few dependencies, instantiating it directly in the test is also a good option. That makes dependencies explicit and avoids confusing Mockito's injection mechanism with Spring's.

## 9. Using mocks and spies in Spring TestContext

In pure unit tests, **@Mock** creates a Mockito object without registering it as a Spring bean. If a test starts a Spring context and needs to replace a bean in the context, use the appropriate bean override mechanism.

With Spring Framework 6.2 and later, you can use the annotations in the **org.springframework.test.context.bean.override.mockito** package:

- **@MockitoBean**: creates a mock and places it into the Spring ApplicationContext to replace the matching bean.
- **@MockitoSpyBean**: creates a spy from an existing bean in the ApplicationContext, keeping real behavior by default and allowing partial observation or stubbing.

Example with a web slice:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsExpectedOrder() throws Exception {
        when(orderService.findById("order-18"))
                .thenReturn(new OrderView("order-18", "PAID"));

        mockMvc.perform(get("/orders/order-18"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-18"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

The controller is created by Spring in the context, while OrderService is replaced with a mock. The test can verify the HTTP contract without running service logic or the database.

If you want to track a real bean in the context, you can use **@MockitoSpyBean** instead of mocking the entire bean. Remember that real methods can still execute and cause side effects. Only use a spy when the test genuinely needs to keep that bean's behavior.

In older Spring Boot versions, projects may be using Spring Boot's **@MockBean** or **@SpyBean**. These APIs have been marked deprecated in newer Spring Boot versions as Spring Framework's bean override mechanism was introduced. Use the annotation compatible with your project's Spring Framework and Spring Boot versions.

## 10. Choosing the object type based on test goal

There is no single right choice for every situation. Start from what the test needs to prove:

| Goal | Usually suitable choice | Reason |
|---|---|---|
| Test pure Java class logic | Real object for the class under test; stub/mock/fake for dependencies | Keeps focus on the behavior being tested |
| Test multiple operations on a simulated repository | Fake | Provides consistent state and behavior |
| Simulate a service returning errors or special results | Stub | Easy to configure responses |
| Verify a message is sent or repository save is called | Mock | Checks meaningful interactions |
| Keep most real behavior while observing some calls | Spy | Allows tracking the real implementation |
| Test SQL, mappings, or transactions | Real repository and test database | Needs to verify real infrastructure |
| Test controller with isolated service | @WebMvcTest and @MockitoBean | Loads MVC slice, replaces service with a mock |

Some practical rules:

- Prefer real objects for the class under test.
- Use fakes when you need a dependency with simple state and behavior.
- Use stubs when you need to control dependency responses.
- Use mocks when calls or side effects are what you need to verify.
- Use spies selectively because real methods can still execute.
- Use integration tests with real infrastructure when you need to prove interactions with that infrastructure.

## 11. Common mistakes when using test doubles

### Mocking everything

If a test mocks the class under test itself or mocks too many dependencies, the test may end up only confirming that mocks were configured according to the script. Keep the real implementation of the object under test and replace only the boundaries that need isolation.

### Using mocks instead of fakes when state is needed

A mock repository can be configured to return individual results, but when a test needs multiple save-then-find operations, an in-memory fake is usually easier to understand. Fakes help simulate state consistently.

### Verifying too many interactions

Tests that verify every internal call can break during refactoring. Only verify interactions that belong to the contract being protected, such as ensuring a message is sent after a successful payment.

### Using spies to hide hard-to-test designs

If you have to spy on a large service and stub many methods, that class may have too many responsibilities. Splitting collaborators or smaller interfaces usually leads to clearer tests.

### Assuming fakes prove the real implementation

A fake repository does not test SQL, database constraints, or transactions. When those factors matter, add tests with a real repository and an appropriate database.

### Stubs that do not match the real contract

A mock can return data that the real service would never return. That makes the test pass without reflecting realistic scenarios. Use responses with the right types, states, and rules of the dependency contract.

### Letting real side effects run in a spy

A spy may make network calls or write data if real methods are executed. Control methods with side effects, stub them intentionally, or choose a more suitable fake or mock.

## 12. Designing boundaries for easier testing

Choosing the right test double is easier when the application has clear dependency boundaries.

A business service can depend on interfaces:

~~~java
public interface PaymentGateway {
    PaymentResult charge(Order order);
}

public interface OrderRepository {
    Optional<Order> findById(String id);

    void save(Order order);
}
~~~

Production provides implementations using HTTP and JPA. Unit tests can provide stubs or fakes. Interaction tests can use mocks. Integration tests load the real implementations in the Spring context and configure test infrastructure.

This design has several benefits:

- The service does not need to know HTTP client or JPA details.
- Tests can swap dependencies without modifying business logic.
- Each test can choose the level of representativeness matching the risk.
- Contracts between components are expressed via interfaces and input/output data.

Do not create an interface for every class just to use mocks. An interface is valuable when it represents a meaningful boundary, such as an external service, a data store, or a replaceable capability. For a small pure Java class, instantiating the real object is usually simpler.

## 13. Checklist before choosing a replacement object

Before writing a test, determine:

1. Which object is under test and should keep its real implementation?
2. Which dependencies need state? If any, would a fake make the test easier to understand?
3. Does the test need a fixed response or does it need to verify an interaction?
4. Is it necessary to keep the real behavior of part of a dependency? If so, is a spy truly needed?
5. Which behaviors can only be confirmed with real implementations and infrastructure?
6. Is the test verifying internal details that do not belong to the class contract?
7. Does the data provided by the fake, stub, or mock match the real contract?

A Spring test suite typically combines multiple object types. Unit tests keep the service real and use stubs or fakes for dependencies; interaction tests use mocks when verifying side effects; MVC tests replace service beans with **@MockitoBean**; integration tests use real repositories and infrastructure; spies appear only when observing a real implementation within a controlled scope.

Clearly distinguishing real objects, fakes, stubs, mocks, and spies gives each test a specific purpose. Tests run faster when dependencies can be isolated while still preserving confidence when important boundaries are verified with real implementations. Choose replacement objects based on the evidence the test needs to provide, then assert on outcomes or interactions that are meaningful to the application's behavior.

