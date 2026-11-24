# Injecting Collaborators Without Starting ApplicationContext

When unit testing a Spring service, we often need to replace the components it calls with controllable objects: a repository, HTTP gateway, publisher, clock, or another service. Doing so does not require starting a Spring `ApplicationContext`.

A unit test can instantiate the object under test directly with `new` and pass its collaborators via the constructor. When simulating behavior or verifying calls is needed, we use stubs, fakes, or mocks. JUnit Jupiter executes the tests; Mockito can create mocks and manage mock lifecycles. The Spring container does not participate in this run.

This is the right testing approach when the goal is to verify a class's logic under controlled inputs and collaborator responses. It keeps tests fast, focused, and less coupled to application configuration.

## 1. Understanding Dependency Injection in Unit Tests

In a running application, the Spring container typically instantiates beans, locates dependencies, and injects them into configured constructors or fields. In a unit test without a container, the test itself is responsible for constructing the minimal object graph needed.

```text
Running application

Spring ApplicationContext
        │ creates and wires beans
        ▼
OrderService ───────► OrderRepository
      │
      └─────────────► NotificationGateway


Unit test without ApplicationContext

JUnit test
   │ creates directly
   ▼
OrderService ───────► mock OrderRepository
      │
      └─────────────► mock NotificationGateway
```

These two ways of building the object graph serve different purposes:

- The Spring container verifies and performs bean creation according to application configuration.
- A unit test creates a class directly and provides the collaborators needed to test that class's behavior.

Constructor injection makes this boundary explicit. A class declares its required dependencies in its constructor; at runtime, Spring supplies real or configured beans; in unit tests, the test supplies fakes or mocks.

## 2. Designing the Class Under Test with Constructor Injection

Suppose `OrderService` handles order creation. It needs to save the order via a repository and send a notification through a gateway.

```java
public interface OrderRepository {
    Order save(Order order);
}

public interface NotificationGateway {
    void orderCreated(Order order);
}

public record CreateOrderCommand(String customerId, String sku, int quantity) {}

public record Order(String customerId, String sku, int quantity) {
    public static Order from(CreateOrderCommand command) {
        return new Order(command.customerId(), command.sku(), command.quantity());
    }
}
```

The service accepts both collaborators through its constructor:

```java
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final NotificationGateway notificationGateway;

    public OrderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        this.orderRepository = Objects.requireNonNull(orderRepository);
        this.notificationGateway = Objects.requireNonNull(notificationGateway);
    }

    public Order create(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        Order saved = orderRepository.save(Order.from(command));
        notificationGateway.orderCreated(saved);
        return saved;
    }
}
```

`@Service` marks the class so Spring can detect and register it as a bean during component scanning. This annotation does not restrict the constructor to being called only by Spring. A unit test can still invoke `new OrderService(...)` normally; without starting an `ApplicationContext`, Spring does not scan the classpath, create beans, or perform dependency injection.

Constructor injection provides several clear benefits for testing:

- Inspecting the constructor immediately reveals all required dependencies of the class.
- Tests construct the object with the exact collaborators each test case requires.
- Dependencies can be declared `final`, helping the object maintain a stable structure after creation.
- No context startup is needed just to populate a few fields or invoke setters.
- Missing dependencies fail immediately at object construction rather than later when a method is called.

## 3. Injecting Mocks Manually with Mockito

Mockito can create test doubles so tests can control responses and observe interactions. With constructor injection, the most direct approach is to create mocks and pass them to the constructor of the class under test.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private NotificationGateway notificationGateway;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(orderRepository, notificationGateway);
    }

    @Test
    void savesOrderAndSendsNotification() {
        CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
        Order savedOrder = new Order("customer-1", "SKU-1", 2);
        when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);

        Order result = orderService.create(command);

        assertThat(result).isSameAs(savedOrder);
        verify(orderRepository).save(new Order("customer-1", "SKU-1", 2));
        verify(notificationGateway).orderCreated(savedOrder);
    }
}
```

In the test above:

1. `@ExtendWith(MockitoExtension.class)` tells JUnit Jupiter to use Mockito's extension to initialize and manage Mockito annotations in the test.
2. `@Mock` creates a mock for each collaborating interface.
3. `setUp()` constructs `OrderService` via its regular constructor and passes both mocks.
4. `when(...).thenReturn(...)` defines the repository's response.
5. `verify(...)` confirms the service called its collaborators with the expected data.

`MockitoExtension` is Mockito's extension for JUnit Jupiter. It is not `SpringExtension`, does not create Spring beans, and does not load an `ApplicationContext`. The test runs standalone on the JUnit Platform.

If annotations are not needed, you can also create mocks explicitly:

```java
import static org.mockito.Mockito.mock;

@Test
void createsOrderWithExplicitMocks() {
    OrderRepository repository = mock(OrderRepository.class);
    NotificationGateway notifications = mock(NotificationGateway.class);
    OrderService service = new OrderService(repository, notifications);

    // Configure mock behavior, call the service, and verify the result.
}
```

This makes every initialization step explicit inside the test. It is helpful when each test needs a different object graph configuration or only a couple of mocks.

## 4. Using `@InjectMocks` When You Want Mockito to Instantiate the Class Under Test

Mockito provides the `@InjectMocks` annotation to ask Mockito to instantiate the class under test and attempt to inject matching mocks or spies into that instance.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceWithInjectMocksTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private NotificationGateway notificationGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void savesAndNotifies() {
        CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
        Order savedOrder = new Order("customer-1", "SKU-1", 2);
        when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);

        assertThat(orderService.create(command)).isEqualTo(savedOrder);
        verify(notificationGateway).orderCreated(savedOrder);
    }
}
```

Mockito tries constructor injection first, and may then attempt setter/property injection and field injection according to its rules. This is a Mockito convenience mechanism, not Spring's dependency injection algorithm. Mockito does not process `@Autowired`, perform component scanning, run auto-configuration, or create Spring proxies for objects annotated with `@InjectMocks`.

A few points to remember when using `@InjectMocks`:

- Appropriate mocks or spies must exist in the test for the matching collaborators.
- If Mockito cannot find a mock for a constructor parameter, it may pass `null` while attempting constructor injection. Thus, the test can still fail when a method runs if a dependency is missing.
- When multiple constructors or same-typed dependencies exist, dependency selection and wiring can be less clear than manual instantiation.
- `@InjectMocks` does not automatically create mocks for deeply nested dependencies in the object graph.
- The annotation is no substitute for clear constructor design and does not guarantee that application bean configuration works correctly.

Therefore, use `@InjectMocks` when the object graph is simple and automatic wiring makes the test easier to read. When you need to see exactly which object is passed where, `new OrderService(mockA, mockB)` is usually more transparent.

## 5. Choosing the Right Test Double: Stub, Mock, Fake, and Dummy

Not every collaborator needs a Mockito mock. A test double is an object that stands in for a real collaborator in a test. Common types serve different purposes:

| Type | Purpose | Example |
|---|---|---|
| Dummy | Passed in to satisfy a method signature but never used. | A placeholder object for a required test parameter. |
| Stub | Returns predefined data to control execution paths. | A stub repository that always returns a specific order. |
| Fake | Simple implementation with real behavior, usually storing state in memory. | A repository backed by a `Map` instead of a database. |
| Mock | Records interactions so the test can verify calls or arguments. | Verifying that a gateway receives the right notification. |
| Spy | Wraps a real object and allows tracking or overriding part of its behavior. | Observing calls on a real collaborator. |

### 5.1. Stub: controlling return values

If the goal is to test service logic when the repository returns a specific result, a stub is enough. With Mockito, stubs are usually configured with `when(...).thenReturn(...)`:

```java
when(orderRepository.save(any(Order.class))).thenReturn(savedOrder);
```

The service receives a predefined response and the test checks the output. There is no need to verify every incidental call if that behavior is not what the test needs to prove.

### 5.2. Fake: using a lightweight in-memory implementation

A fake is useful when a collaborator holds state and the test needs to verify results across multiple calls. For example, a simple fake repository:

```java
import java.util.ArrayList;
import java.util.List;

class InMemoryOrderRepository implements OrderRepository {

    private final List<Order> orders = new ArrayList<>();

    @Override
    public Order save(Order order) {
        orders.add(order);
        return order;
    }

    List<Order> findAll() {
        return List.copyOf(orders);
    }
}
```

A test can pass the fake to the service:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

@Test
void storesCreatedOrderInMemory() {
    InMemoryOrderRepository repository = new InMemoryOrderRepository();
    NotificationGateway notifications = mock(NotificationGateway.class);
    OrderService service = new OrderService(repository, notifications);

    service.create(new CreateOrderCommand("customer-1", "SKU-1", 2));

    assertThat(repository.findAll())
            .containsExactly(new Order("customer-1", "SKU-1", 2));
}
```

A fake brings tests closer to the behavior of a real repository than a pure mock, but it does not prove that SQL statements, JPA mappings, transactions, or real database configurations work. Those require an appropriate persistence test.

### 5.3. Mock: verifying meaningful interactions

A mock is suitable when the contract of the class under test includes calling a collaborator. For example, the service must send a notification after a successful save. The test can use `verify(notificationGateway).orderCreated(savedOrder)` to confirm the interaction.

Do not mechanically verify every internal call. If a test checks invocation counts, call ordering, or argument details unrelated to external behavior, it becomes tightly coupled to the implementation and breaks during refactoring even when behavior remains correct.

### 5.4. Spy: use with caution

A spy wraps a real object, so unstubbed calls normally execute that object's real logic. Spies are useful in certain special cases, but they can cause tests to inadvertently touch files, the network, or real state. For collaborators with side effects, mocks or fakes are usually easier to control.

## 6. Testing Multiple Logic Branches Without Spring

Once collaborators are under control, tests can focus on the success path, error paths, and interaction rules.

For example, the service rejects an invalid quantity before calling the repository:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsNonPositiveQuantityBeforeCallingCollaborators() {
    CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 0);

    assertThatThrownBy(() -> orderService.create(command))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Quantity must be positive");

    verifyNoInteractions(orderRepository, notificationGateway);
}
```

This example verifies the service's contract: invalid input is rejected without producing side effects. No database, HTTP server, or application context is required.

For repository failure cases, an exception can be configured to verify that the service propagates the appropriate error and does not send a notification:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@Test
void doesNotNotifyWhenSavingFails() {
    CreateOrderCommand command = new CreateOrderCommand("customer-1", "SKU-1", 2);
    when(orderRepository.save(any(Order.class)))
            .thenThrow(new IllegalStateException("Storage unavailable"));

    assertThatThrownBy(() -> orderService.create(command))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Storage unavailable");

    verifyNoInteractions(notificationGateway);
}
```

These examples use Mockito to isolate collaborators. When testing pure Java rules, Mockito may not even be needed; real objects or small fakes are enough.

## 7. Dependency Injection Does Not Mean Booting Spring

A common misconception is seeing `@Service`, `@Repository`, or `@Component` on a class and assuming testing it requires the Spring container. In reality, these annotations are metadata Spring uses when assembling the application. The Java class itself remains a regular class that can be instantiated directly.

| Component | Context-Free Unit Test | Spring Integration Test |
|---|---|---|
| Service instantiation | `new OrderService(...)` | Spring creates beans per configuration. |
| Providing collaborators | Pass mocks, stubs, or fakes to the constructor. | Spring resolves beans from the context. |
| `@Service` / `@Component` | Annotation does not need to be active for direct instantiation. | Used by component scanning or bean configuration. |
| `@Autowired` | Not processed without a Spring container. | Spring performs injection from the context. |
| `@Mock` | Mockito creates standalone mocks. | Can be used alongside the test framework when Mockito integration is enabled. |
| `@MockBean` / `@MockitoBean` | Unnecessary and does not replace manual mocks. | Replaces or registers mock beans in the Spring test context per the corresponding API/version. |

If a class only has `@Autowired` fields and no constructor to pass dependencies, calling `new` will not cause Spring to populate those fields. They remain `null` unless the test sets them itself. This is why constructor injection generally makes classes much easier to unit test.

Do not boot `@SpringBootTest` just to let Mockito create mocks. `@SpringBootTest` is meant to construct a Boot application environment; `MockitoExtension` is meant to initialize mocks for unit tests. The two tools serve different testing scopes.

## 8. Required Dependencies for Standalone Tests

A unit test using JUnit Jupiter and Mockito needs JUnit's test engine/API along with Mockito core and the JUnit Jupiter integration module. In Gradle, an explicit declaration looks like:

```groovy
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

In Spring Boot applications, `spring-boot-starter-test` typically provides common test libraries including JUnit Jupiter, Mockito, and AssertJ under Boot's dependency management. However, the Spring Boot starter is not a prerequisite for writing standalone unit tests. A non-Boot Spring Framework project can declare JUnit and Mockito directly.

If a test does not use any Spring Test APIs, it does not need `spring-test` simply because the class under test is annotated with `@Service`. Only add dependencies when tests actually use APIs from those modules.

## 9. When Is a Context-Free Unit Test Enough?

Choose a unit test without an `ApplicationContext` when the question you need to answer focuses on a single class's logic:

- Given the same input, does the service compute the right result?
- When a collaborator returns a value or throws an exception, how does the service handle it?
- Does the service invoke required collaborators with the right data?
- Do input checks prevent side effects?
- Does an error branch stop subsequent steps from running?

These tests typically run fast because they skip creating a context, initializing connection pools, scanning components, or setting up a web environment. They also pinpoint bugs in the class's logic without interference from other beans' configurations.

However, standalone unit tests do not prove Spring has wired the application properly. They do not verify component scanning, auto-configuration conditions, qualifiers, profiles, property binding, transaction proxies, security filter chains, or registered endpoints. When you need to verify those contracts, add Spring integration tests with an appropriate scope.

A balanced strategy typically consists of:

1. Context-free unit tests to cover numerous service logic cases and error paths.
2. Focused Spring context tests to verify bean configuration and key integrations.
3. Specialized tests for persistence, MVC, security, or HTTP when the behavior under test belongs to those layers.

There is no need to turn every unit test into an integration test. Conversely, you cannot rely on mocked unit tests to conclude that all Spring wiring and configuration are correct.

## 10. Cases Requiring Special Attention

### Dependencies provided via `@Value`

If a service reads configuration via `@Value` fields, direct `new` instantiation will not populate those values. Consider moving configuration values into constructor parameters or a configuration object passed to the constructor. Unit tests can then supply concrete values without Spring property resolution.

```java
public class RetryPolicy {
    private final int maxAttempts;

    public RetryPolicy(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean canRetry(int attempt) {
        return attempt < maxAttempts;
    }
}
```

The test simply calls `new RetryPolicy(3)` to check thresholds. A separate context test can verify that the property value binds to the bean as configured in the application.

### Proxied dependencies or AOP-reliant behavior

When running in Spring, a bean may be wrapped in a proxy to apply transactions, caching, security, or other advice. `new` creates the Java object directly without creating a proxy. Direct unit tests verify method logic; they do not verify proxy-added behavior. If you need to confirm `@Transactional` or advice is actually applied, test with a Spring context and an appropriate transaction manager.

### Classes depending on request scope or web context

Some beans rely on request, session, or security contexts. If business logic can be decoupled from web state, pass the needed data as method arguments or explicit collaborators so unit tests remain easy to control. If the goal is to test how Spring binds scopes and request contexts, write a corresponding web/context test.

### Objects that cannot be constructed because the constructor is too complex

If a class requires too many collaborators or has complex constructor branching, revisit the class's responsibilities and object graph. Do not use reflection to write arbitrarily into private fields in tests just to bypass constructors. You can create clear test data factories/builders, split responsibilities, or provide meaningful constructor dependencies.

## 11. Habits That Keep Unit Tests Maintainable

- Create the object under test via an explicit constructor; keep required dependencies `final` where appropriate.
- Mock collaborators that have side effects or need controlled responses; use fakes when a small in-memory implementation makes tests more natural.
- Stub only the responses needed for the branch under test; avoid configuring excessive unrelated behavior.
- Verify interactions when the call is part of the contract, such as sending a notification after a successful save.
- Avoid verifying internal details that add no value for readers of the test.
- Do not treat `@InjectMocks` as proof that Spring wiring works; it is merely Mockito's object instantiation helper.
- Do not boot a Spring context if the test only needs Java logic and collaborators that can be supplied directly.
- Add context tests when you need to verify Spring configuration, proxies, property binding, or framework integration.

Injecting collaborators without starting an `ApplicationContext` is a direct and effective approach to unit testing: the test creates the class under test, passes dependencies with controlled behavior, and verifies outcomes and interactions. Spring can still manage the exact same class when the application runs; the unit test simply chooses to test the class's own responsibilities without standing up the entire container.
