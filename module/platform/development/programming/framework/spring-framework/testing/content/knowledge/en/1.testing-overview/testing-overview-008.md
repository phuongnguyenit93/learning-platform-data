# Relationship Between Testability and Dependency Injection Design

Testability is the degree of ease with which an object can be instantiated under controlled conditions, supplied with input data, have external services substituted, and have its outcomes observed. In a Spring application, Dependency Injection (DI) design directly governs that testability: a class that receives its dependencies from outside is generally far easier to instantiate, isolate, and test than a class that locates or creates the services it needs on its own.

DI is not a technique solely for tests. It is a way of structuring object creation and wiring in the application. When dependencies are declared explicitly, Spring can assemble them at runtime, while tests can assemble the object themselves with suitable test doubles. Good design therefore supports both production code and test code.

## 1. Testability Reflects Design Quality

A class with good testability typically exhibits four traits:

1. **Easy to instantiate:** test authors can create the object under test without starting the entire application.
2. **Controllable dependencies:** tests can supply fake data, fake storage, a fixed clock, or a mock gateway in place of databases, networks, and external systems.
3. **Repeatable outcomes:** identical inputs and initial state yield consistent results; tests do not depend unpredictably on wall-clock time, networks, or environment data.
4. **Observable behavior:** return values, persisted state, or interactions with an external boundary can be verified through a clear contract.

For instance, an expiration service calling Instant.now() directly depends on the test machine's clock. Tests would have to guess the time or wait until a specific timestamp. If the service receives a Clock from outside, tests can use a fixed clock:

~~~java
import java.time.Clock;
import java.time.Instant;

public class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
~~~

Tests can control the exact current instant:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ExpirationPolicyTest {
    @Test
    void considersAnInstantBeforeTheFixedTimeExpired() {
        Instant fixedNow = Instant.parse("2026-11-12T10:00:00Z");
        Clock clock = Clock.fixed(fixedNow, ZoneOffset.UTC);
        ExpirationPolicy policy = new ExpirationPolicy(clock);

        boolean expired = policy.isExpired(
                Instant.parse("2026-11-12T09:59:59Z"));

        assertTrue(expired);
    }
}
~~~

Not every object needs to be managed by Spring or turned into an interface. Clock is a meaningful dependency because current time is an external factor that can make tests non-deterministic. Small, pure value objects without external state can still be constructed directly inside a method or test.

Testability often surfaces alongside other design issues. If a class can only be tested after booting the entire application, connecting to a database, and calling real services, it may be too tightly coupled to infrastructure. If tests must use reflection to assign a private field, or mutate static state before and after each test, the class's dependencies are hidden. Hard-to-write tests are a signal to revisit responsibility boundaries and dependency management.

## 2. Dependency Injection Makes Dependencies Explicit

Dependency Injection is the pattern where an object receives the objects or values it needs from outside instead of locating them itself. In Spring, the container creates beans, resolves dependencies, and wires them according to configuration, component scanning, or bean declarations.

Consider an ordering service that needs a payment gateway and an order store:

~~~java
public record Order(String id, java.math.BigDecimal amount) {
}

public interface PaymentGateway {
    void charge(String orderId, java.math.BigDecimal amount);
}

public interface OrderRepository {
    void save(Order order);
}
~~~

The service receives both dependencies via its constructor:

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository) {
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public Order place(String orderId, BigDecimal amount) {
        Order order = new Order(orderId, amount);
        paymentGateway.charge(orderId, amount);
        orderRepository.save(order);
        return order;
    }
}
~~~

The constructor fully declares what OrderService needs to operate. When Spring creates the bean, the container must find one PaymentGateway bean and one OrderRepository bean. If a required dependency is missing or multiple ambiguous beans exist, failure occurs at context creation time instead of waiting until a rare business branch runs.

In a unit test, we can instantiate the service directly and supply substitutes. There is no need to run component scanning, create an ApplicationContext, or start Spring Boot just to verify the logic of place.

### Constructor Injection and Testability

Constructor injection is usually the best choice for required dependencies:

- **Dependencies are declared explicitly:** looking at the constructor shows everything the class needs.
- **Complete object upon creation:** there is no window where the object exists with a required field still unassigned.
- **Easy to instantiate in unit tests:** tests call the constructor directly and pass mocks or fakes.
- **Supports immutability:** dependency fields can be declared final, preventing rewiring after construction.
- **Configuration errors caught early:** Spring cannot create the bean if required constructor parameters cannot be resolved.

With a single constructor, Spring automatically uses it for injection; placing @Autowired on the constructor is normally unnecessary. Calling the constructor directly in tests requires no Spring annotations either.

### Field Injection Hides Initialization Requirements

A style less friendly to testing is:

~~~java
@Service
public class ReportService {
    @Autowired
    private ReportRepository repository;

    public Report find(String id) {
        return repository.findById(id);
    }
}
~~~

When calling new ReportService() in a test, the repository field has not been assigned by Spring. The test cannot supply the dependency through the constructor and must typically start a Spring context or use reflection to mutate internal state. This couples tests to the framework's initialization mechanism rather than testing the class's behavior.

It can be rewritten with constructor injection:

~~~java
@Service
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    public Report find(String id) {
        return repository.findById(id);
    }
}
~~~

Setter injection still has a place for genuinely optional dependencies or ones that can change after construction. However, avoid using setters to dodge a constructor with many required dependencies. If a class has too many constructor parameters, that usually signals the class holds too many responsibilities and should be considered for splitting.

## 3. Substituting Dependencies to Verify Behavior

For OrderService, a test can use Mockito to simulate the two external boundaries:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(paymentGateway, orderRepository);
    }

    @Test
    void chargesAndSavesTheOrder() {
        BigDecimal amount = new BigDecimal("125.00");

        Order result = service.place("O-100", amount);

        assertEquals(new Order("O-100", amount), result);
        verify(paymentGateway).charge("O-100", amount);
        verify(orderRepository).save(new Order("O-100", amount));
    }

    @Test
    void doesNotSaveWhenPaymentFails() {
        BigDecimal amount = new BigDecimal("125.00");
        doThrow(new IllegalStateException("Payment declined"))
                .when(paymentGateway)
                .charge("O-100", amount);

        assertThrows(
                IllegalStateException.class,
                () -> service.place("O-100", amount));

        verify(paymentGateway).charge("O-100", amount);
        verifyNoInteractions(orderRepository);
    }
}
~~~

The test constructs OrderService via its constructor and deliberately controls the payment gateway's outcome. The first test verifies the returned order and required interactions. The second simulates a payment failure and confirms the repository was not called. This is a unit test: it checks a single class's behavior in isolation, not Spring bean registration.

Substitutes can take several forms:

| Test Double Type | Purpose | Usage Example |
|---|---|---|
| Stub | Returns predefined data | A repository returning a sample order |
| Fake | Simple but working implementation | A repository storing data in a Map instead of a database |
| Mock | Records or expects a specific interaction | Verifying PaymentGateway.charge() was called |
| Spy | Wraps a real object or part of real behavior | Used only when observing interactions while keeping real implementation |

Mocks are useful when a class's contract includes calling an external boundary. However, if every test verifies every internal call, tests break easily during refactoring even when external behavior is unchanged. Prefer checking meaningful outcomes and state; verify interactions only when the interaction itself is part of the requirement, such as not charging payment twice or not saving an order after payment fails.

## 4. Testing Spring Wiring Separately from Unit Tests

The unit test above proves OrderService's logic with test-supplied dependencies. It does not prove Spring can create and wire the beans in the application. That is a separate test question requiring an appropriate Spring context.

Spring TestContext Framework provides @SpringJUnitConfig to create a context for JUnit Jupiter. You can register only the service under test and substitute beans:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderServiceContextTest.TestConfig.class)
class OrderServiceContextTest {
    @Autowired
    OrderService service;

    @Autowired
    InMemoryOrderRepository repository;

    @Test
    void springCreatesTheServiceWithTheConfiguredDependencies() {
        BigDecimal amount = new BigDecimal("80.00");

        service.place("O-200", amount);

        assertEquals(
                new Order("O-200", amount),
                repository.findById("O-200"));
    }

    @Configuration
    @Import(OrderService.class)
    static class TestConfig {
        @Bean
        PaymentGateway paymentGateway() {
            return (orderId, amount) -> {
                // Do not call the real payment system in the test.
            };
        }

        @Bean
        InMemoryOrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }
    }
}

class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    public Order findById(String id) {
        return orders.get(id);
    }
}
~~~

In this example, @Import(OrderService.class) registers the service in the context; @Bean methods supply the test payment gateway and repository. Spring performs constructor injection just as when running the application. The fake repository still stores data so the test can check state after calling the service.

This style of test catches wiring bugs such as missing beans, unresolvable constructors, or configuration creating the wrong bean. It costs more than a unit test because it builds a context, so use it only when the question genuinely involves the Spring container. @SpringJUnitConfig does not start a full Spring Boot application; the test configuration includes only what is explicitly declared or imported.

### Choosing the Right Test Scope in the Spring Ecosystem

| Scope | Common Tools | What to Verify |
|---|---|---|
| Unit test | JUnit Jupiter, Mockito, custom fakes | Logic of a single class under controlled dependencies |
| Spring context test | @SpringJUnitConfig, @ContextConfiguration | Beans are created and injected properly in a focused context |
| Boot integration test | @SpringBootTest | Application configuration and multi-component collaboration in a near-runtime context |
| Boot slice test | @WebMvcTest, @DataJpaTest | A slice such as MVC or JPA works with its related configuration |

Slice annotations such as @WebMvcTest and @DataJpaTest belong to the Spring Boot Test ecosystem. They let you test a single infrastructure layer without booting the entire application. Do not default to @SpringBootTest for every test simply because the project uses Spring Boot.

A sensible scope split is:

- Use unit tests for business rules, calculations, and branches testable with plain Java objects.
- Use Spring context tests when verifying how beans are declared, injected, or configured.
- Use slice tests when verifying a specific integration layer such as controllers, JSON mapping, or repositories.
- Use broader integration tests when verifying multi-component collaboration, transactions, security configuration, or infrastructure communication.

Test layers complement one another. Fast unit tests cannot verify Spring configuration; a passing integration test does not replace numerous unit tests focused on business branches.

## 5. DI Designs That Hurt Testability

DI only helps when it clarifies dependency boundaries. Certain patterns still make tests hard to write or maintain.

### Instantiating Infrastructure Dependencies Inside Business Classes

For example, a service directly creating a concrete HTTP client, repository, or adapter:

~~~java
public class CustomerService {
    private final CustomerRepository repository =
            new JdbcCustomerRepository();

    public Customer find(String id) {
        return repository.findById(id);
    }
}
~~~

Tests cannot replace the repository without modifying source code or tampering with internal state. The business class decides both behavior and infrastructure creation. Move repository creation to the composition root (where objects are assembled), typically the Spring container, and pass the repository via constructor.

Using new is not always wrong. Instantiating a DTO, value object, collection, or pure, cheap, deterministic helper inside a method is normal. The problem is instantiating a dependency that tests need to substitute, especially one accessing networks, databases, system time, or shared state.

### Using ApplicationContext as a Service Locator

A class might accept ApplicationContext and call getBean() on demand:

~~~java
public class CustomerService {
    private final ApplicationContext context;

    public CustomerService(ApplicationContext context) {
        this.context = context;
    }

    public Customer find(String id) {
        CustomerRepository repository =
                context.getBean(CustomerRepository.class);
        return repository.findById(id);
    }
}
~~~

The constructor reveals only a dependency on ApplicationContext; the services actually required are hidden inside the method body. Tests must spin up a context or simulate the service locator itself. Inject CustomerRepository directly so the dependency graph stays readable and tests can replace the exact boundary.

### Creating Too Many Interfaces Just to Mock

Do not create an interface for every single class. If a class is small, stable, performs no I/O, and has no need for interchangeable implementations, injecting the concrete type directly can be simpler. Interfaces add value when they define a contract, decouple business logic from infrastructure, have multiple valid implementations, or establish a meaningful substitution seam.

An interface created solely for test mocking inflates type count and obscures program flow. Good testability comes from well-managed dependencies, not from interface count.

### Packing Too Many Responsibilities into One Service

A constructor with too many parameters usually signals the class coordinates too many groups of work. Adding mocks for every parameter may get tests running, yet does not solve the responsibility problem. Check whether the class can be split into components with clearer focus. Each component should carry just enough dependencies to fulfill its responsibility.

Do not stuff dependencies into a Map, an ApplicationContext, or a generic provider class just to shorten the constructor. Doing so hides which services are truly required.

### Using Static State or Mutable Singletons

Static state shared across tests allows execution order to alter outcomes. One test mutating global configuration or data can break another test. Prefer instance-scoped or context-scoped state, pass needed dependencies from outside, and initialize test data independently. If shared state is unavoidable, enforce explicit reset mechanisms and check parallel execution safety.

## 6. Designing Clean Dependency Boundaries

A testable design does not mean every class must be mocked. What matters is separating pure logic from capabilities that communicate externally.

| Dependency Category | Examples | Appropriate Organization |
|---|---|---|
| Values and pure logic | Money, converters, fee-calculation rules | Instantiate directly; test via inputs/outputs |
| Time and mutable data sources | Clock, ID generators, random sources | Inject so tests can control results |
| Storage | Repositories, caches | Inject via suitable contracts; use fakes or test databases by scope |
| External communication | HTTP clients, email senders, payment gateways | Inject adapters or ports; mock/fake in isolated tests |
| Configuration | URLs, timeouts, business limits | Bind to typed configuration; test with explicit values |

In layered or ports-and-adapters architectures, business classes depend on the contracts they need. Concrete adapters implement those contracts via JDBC, HTTP, or another technology. Spring wires implementations in the live application; tests can supply fakes or mocks. This is purposeful DI: pointing dependencies toward stable contracts and letting infrastructure change without altering business logic.

You do not need to create interfaces for every dependency upfront. Start from actual needs: which dependencies do I/O, hold mutable state, are hard to construct in tests, or may have multiple implementations? Separate contracts at those boundaries. For pure logic, keeping code simple and testing directly is usually more effective.

## 7. Managing the Spring Context in Tests

Spring TestContext Framework can cache ApplicationContext instances so tests with matching configurations reuse contexts. This cuts startup time, yet requires organizing test configuration and shared state carefully.

Practical rules:

- Keep context configurations centralized and stable when many tests can share them.
- Do not let mutable data inside singleton beans make tests order-dependent.
- Clean up data in repositories or databases explicitly per test.
- Use @DirtiesContext only when a test genuinely mutates context state beyond reuse; this annotation tells Spring to evict the context from the cache and recreate it when needed.
- Avoid creating numerous slightly different context configurations if they do not test distinct behaviors, since each configuration may require its own context.

If a test only checks a service's calculation or branch, instantiate the service directly. If it must verify bean wiring, use a small context. If it must verify broad application configuration, use @SpringBootTest deliberately. Broader scope brings higher startup cost and greater infrastructure coupling.

## 8. Reading Signals from a Hard-to-Write Test

When a test is hard to set up or fails intermittently, identify the root cause before adding more annotations or mocks. These questions help pinpoint the issue:

1. **Must the test boot Spring just to instantiate one object?** If so, check whether the class can use constructor injection and be created as a plain Java object.
2. **Are any dependencies created or looked up inside the class?** Move dependency creation outside and inject via constructor.
3. **Do outcomes depend on time, randomness, networks, or environment data?** Move the source of variation behind a controllable dependency.
4. **Does the test need reflection to set private fields?** Revisit how dependencies are declared and the class's public API.
5. **Does one test have to mock too many collaborators?** Check class responsibilities and the boundary between business logic and infrastructure.
6. **Does the test only verify internal interactions?** Shift focus toward outputs, state, or contracts meaningful to callers.
7. **Do failures appear only when running alongside other tests?** Look for static state, mutable singletons, shared data, or mutated context configuration.

Not every hard test proves bad design. Some behaviors inherently need an integration environment, such as real transactions or interactions with a database engine. The goal is placing each behavior at the right test level and clarifying what the test controls versus what must be verified against real infrastructure.

## 9. Workflow When Designing a New Service

When building a Spring service with strong testability, follow this sequence:

1. State the service's responsibilities and public behavior clearly.
2. List inputs, outputs, and external capabilities the behavior relies on.
3. Keep pure rules in plain Java when possible; do not pull them into Spring solely for testing convenience.
4. Declare required dependencies via constructor. Define contracts at storage, network, time, or external-system boundaries when implementations need substitution.
5. Write unit tests by instantiating the service directly and supplying mocks/fakes. Test both normal outcomes and key error paths.
6. Add Spring context tests to verify bean wiring when wiring carries risk or is part of the change.
7. Add integration or slice tests when behavior depends on Spring MVC, JPA, transactions, security, or infrastructure configuration.
8. If a test needs excessive mocks or pulls in unrelated components, revisit responsibility boundaries before expanding test setup.

This sequence separates two questions: "is the class's logic correct?" and "does the application assemble and configure the classes properly?". Unit tests answer the first; Spring context and integration tests answer the second at their respective scopes.

## 10. Principles to Remember

- DI makes dependency graphs explicit and lets tests substitute collaborators.
- Constructor injection generally fits required dependencies best because objects are complete upon creation.
- Unit tests need no Spring context if the class can be instantiated directly and dependencies are controlled.
- Spring context tests verify bean creation and wiring; they complement unit tests.
- @SpringBootTest suits broad integration testing, not as the default choice for every test.
- Create abstractions only at meaningful boundaries; do not create interfaces for every class just to mock.
- Time, randomness, networks, databases, and global state are sources of non-determinism; manage them via explicit dependencies.
- Overly large constructors, service locators, or excessive mocks are signals to review design.

Good Dependency Injection design lets Spring assemble the application cleanly and lets tests actively control the execution environment. Testability is therefore both an important consequence of proper dependency management and a feedback tool for refining component boundaries and responsibilities.
