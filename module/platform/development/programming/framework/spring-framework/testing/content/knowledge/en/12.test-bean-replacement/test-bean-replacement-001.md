# Choosing a Real Bean, a Test Bean, or a Mockito Mock

When testing a Spring application, a dependency can be provided as a real application bean, a replacement bean written specifically for tests, or a Mockito mock. Each option serves a different purpose. A real bean verifies how components collaborate in a configuration close to the application; a test bean provides simple, stable control over data and behavior; a Mockito mock simulates dependency responses and verifies interactions at a specific boundary.

Choosing the wrong kind of bean can make a test slow, hard to set up, or test the wrong behavior. For example, mocking a repository in a test meant to verify database mappings and queries skips the exact part that needs to be tested. Conversely, using a real database and starting the entire application context for a simple fee-calculation rule ties a unit test to many unrelated components.

## 1. Three Options and Their Purposes

### 1.1. Real Bean

A real bean is the implementation that the application uses during normal execution. When a test initializes the Spring context and injects this bean, it can verify the behavior of multiple components working together: the controller calls the service, the service calls the repository, transactions are applied, and data is persisted.

For example, `OrderService` using the real `OrderRepository`:

```java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Order create(String customerId) {
        return repository.save(new Order(customerId));
    }
}
```

In an integration test, you can inject `OrderService` and the real repository to verify that data is actually written. If the goal is to test persistence, a real repository and an appropriate test database are an essential part of the test.

A real bean is appropriate when the behavior under test resides in that implementation itself or in the collaboration between components. In return, the test must set up the dependencies required by the real bean, such as a database, files, a message broker, or an HTTP service. Out-of-process dependencies should be provided via test resources with a clear lifecycle, such as a database container or a mock server.

### 1.2. Test Bean (Fake or Stub)

A test bean is an implementation created specifically for tests and registered in the Spring context. It typically implements a small subset of the contract, stores data in memory, or returns predetermined results. Fakes and stubs can be real beans from Spring's perspective: Spring instantiates and injects them like any other bean, but their internal logic is simplified for testing purposes.

For example, the application uses the `PaymentGateway` interface, while the test provides an implementation that does not call a real payment provider:

```java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

final class SuccessfulPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return new PaymentResult("TEST-PAYMENT", true);
    }
}
```

This bean is suitable when multiple tests need stable, readable, and reusable behavior. It is also useful when you want to keep the Spring context structure and test the call flow through an interface without depending on external services.

A fake/stub usually focuses on return values or a simplified model of the dependency. It does not necessarily record every call or provide interaction verification like Mockito. If a test needs to verify the exact number of times a method was called and with what arguments, a Mockito mock is usually more appropriate.

### 1.3. Mockito Mock

A Mockito mock is an object created by Mockito to replace a dependency. A test can configure responses with `when(...).thenReturn(...)`, `thenThrow(...)`, or `doAnswer(...)`, and then verify interactions with `verify(...)`.

Example:

```java
PaymentGateway gateway = mock(PaymentGateway.class);
when(gateway.charge(any(PaymentRequest.class)))
        .thenReturn(new PaymentResult("TEST-1", true));

OrderService service = new OrderService(gateway);
```

A mock is suitable when you need to isolate a class from its dependencies, simulate success/failure scenarios, and verify outgoing data or interactions. A Mockito mock does not automatically create a Spring bean; to replace a bean in a Spring `ApplicationContext`, you need to use Spring Test's bean override mechanism such as `@MockitoBean` or the corresponding annotation for your version.

## 2. Distinguishing Fake, Stub, Mock, and Real Bean

Test double terms are often used closely together, but they emphasize different purposes:

| Type | Characteristics | Common Goal |
|---|---|---|
| Real implementation | Actual production logic | Verify real behavior or integration between components |
| Stub | Returns predefined data | Control indirect inputs to the system under test |
| Fake | Simple implementation with working behavior, often storing data in memory | Replace a heavy dependency with a small, controllable model |
| Mockito mock | Object created by Mockito that supports stubbing and verification | Verify interactions and responses of a dependency |
| Mockito spy | Wraps a real object, usually invoking real behavior unless stubbed | Inspect or replace part of the behavior of an existing object |

In Spring, a fake or stub can be registered as a bean using `@TestConfiguration`. A Mockito mock can be placed into the context using `@MockitoBean`. Both can replace a dependency during Spring injection, though they differ in how they are created and how behavior is verified.

Do not choose a test double purely out of habit. Start with the question: what behavior does this test need to verify? If you need to confirm that the database stores the right data, using real persistence in the test is appropriate. If you need to check that a service sends the right command to the payment gateway, mock the gateway and capture the arguments. If multiple tests need a fake gateway with simple behavior, a fake bean may be easier to maintain than repeated stubbing blocks.

## 3. When Should You Keep the Real Bean?

You should keep the real bean when the implementation is within the scope under test or when behavior depends on how Spring components collaborate.

Common cases:

- Testing repositories, JPA mappings, transactions, or database queries.
- Testing security configuration, serialization, validation, or message conversion.
- Testing multiple services collaborating through the Spring context.
- Testing `@Transactional`, `@Cacheable`, `@Async`, or proxies created by Spring.
- Testing the actual application configuration assembled from component scanning, configuration classes, and properties.

For example, if you want to verify that `OrderService` saves an order and rolls back the transaction when an operation fails, you need to run the flow with Spring and appropriate persistence. Mocking `OrderRepository` would bypass the database and transaction behavior that the test is meant to protect.

A real bean is also suitable when a test needs to verify wiring. Errors such as a missing bean, wrong qualifier, or conditional configuration issue may only surface when Spring creates the context. Plain Java unit tests cannot detect these wiring errors because they do not run the Spring container.

However, keeping all real dependencies in every test can tie tests to external services, consume time, and make failures hard to reproduce. You can keep the parts within the test scope real and replace external boundaries with fakes or mocks.

## 4. When Should You Use a Test Bean?

A test bean is appropriate when you need a replacement dependency with small, clear behavior that can be reused across multiple tests.

For example, an application has an interface for reading exchange rates:

```java
interface ExchangeRateProvider {
    BigDecimal rate(String currency);
}
```

Tests can use a fake that returns deterministic exchange rates:

```java
final class FixedExchangeRateProvider implements ExchangeRateProvider {

    @Override
    public BigDecimal rate(String currency) {
        return switch (currency) {
            case "USD" -> new BigDecimal("1.00");
            case "EUR" -> new BigDecimal("1.08");
            default -> throw new IllegalArgumentException(
                    "Unsupported currency: " + currency
            );
        };
    }
}
```

This fake has executable behavior and clear rules. It can serve multiple tests without repeating `when(provider.rate("USD"))...` in every class.

A simpler stub can return a predetermined result without simulating the full set of rules:

```java
final class StubExchangeRateProvider implements ExchangeRateProvider {

    private final BigDecimal configuredRate;

    StubExchangeRateProvider(BigDecimal configuredRate) {
        this.configuredRate = configuredRate;
    }

    @Override
    public BigDecimal rate(String currency) {
        return configuredRate;
    }
}
```

This stub is useful when a test only cares about how a service handles a specific exchange rate. If you need to verify that the service requests the exact currency code, a Mockito mock with `verify(...)` may express that intent better.

Use a fake when you need a small model with consistent behavior, such as an in-memory repository or a fake gateway. Use a stub when you only need to control return values. Avoid building an overly complex fake that mimics almost the entire real implementation; at that point, the fake becomes a separate system to maintain and risks diverging from production behavior.

## 5. Registering a Test Bean with @TestConfiguration

In Spring Boot, `@TestConfiguration` is used to declare additional beans for tests. It is a test-specific form of `@Configuration` and is not automatically picked up by regular component scanning as an application configuration. Therefore, a top-level `@TestConfiguration` class is usually imported explicitly with `@Import`.

Example configuring a fake gateway:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway paymentGateway() {
        return new SuccessfulPaymentGateway();
    }
}
```

A test class imports this configuration:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(PaymentTestConfiguration.class)
class OrderPaymentIntegrationTest {
    // Spring injects the test PaymentGateway as the primary candidate.
}
```

`@Primary` instructs Spring to prefer this bean when selecting a single bean of type `PaymentGateway` among multiple candidates. The configuration above allows `OrderService` to receive the fake gateway while other application beans are still created according to the Spring Boot configuration.

If the project uses only Spring Framework without Spring Boot, you can use a dedicated test `@Configuration` class and import it with `@Import` or declare it in `@ContextConfiguration(classes = ...)`. `@TestConfiguration` belongs to Spring Boot Test; it is not a core Spring Framework configuration annotation.

### 5.1. Caution: @Primary Does Not Remove the Real Bean

`@Primary` only affects candidate selection when Spring needs to inject a single bean by type. If the real bean is still registered, the context may contain both the real bean and the fake.

This can matter in the following situations:

- A bean injecting `List<PaymentGateway>` or `Map<String, PaymentGateway>` will see multiple implementations.
- A bean using `@Qualifier` or a specific bean name may select the real bean.
- Another component retrieving all beans by type may use both implementations.
- Initializing the real bean may cause side effects, even if it is not selected for regular injection.

Therefore, `@Primary` is suitable when the goal is to prioritize a fake in a context with multiple candidates and coexisting beans are acceptable. If you need to explicitly replace an existing bean, use an appropriate bean override mechanism such as `@MockitoBean` or `@TestBean` when supported by your Spring version.

### 5.2. Using Nested Configuration in a Test Class

You can declare `@TestConfiguration` directly inside the test class:

```java
@SpringBootTest
class OrderPaymentIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        @Primary
        PaymentGateway paymentGateway() {
            return new SuccessfulPaymentGateway();
        }
    }
}
```

Spring Boot supports using a nested `@TestConfiguration` as additional configuration for the test. This approach is convenient when the fake serves only one test class. If multiple test classes share the fake, extracting the configuration into a separate file and importing it where needed reduces duplication.

## 6. Replacing a Bean in the Spring Context with @MockitoBean

Starting with Spring Framework 6.2, `@MockitoBean` is a Spring Test annotation for registering a Mockito mock as a bean override in the `ApplicationContext`. It replaces a dependency injected by Spring with a mock managed by Mockito.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void completesOrderWhenPaymentSucceeds() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-100", true));

        OrderResult result = orderService.completeOrder("CUS-42");

        assertTrue(result.completed());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

Spring creates a mock for `PaymentGateway` and places it into the context in place of the matching bean. `OrderService` is created by Spring as usual, but the injected dependency is a Mockito mock. The test can configure return values and verify calls.

### 6.1. Selecting the Right Bean When Multiple Candidates Exist

If the context has multiple beans of the same type, you need to specify which bean is being replaced. You can use a qualifier on the field:

```java
@MockitoBean
@Qualifier("stripePaymentGateway")
private PaymentGateway paymentGateway;
```

The field name can also participate as a fallback qualifier when Spring needs to disambiguate candidates. Even so, using `@Qualifier` explicitly makes the intent easier to read when multiple gateways of the same type exist.

If you want to ensure the test only replaces an already-existing bean, you can enable `enforceOverride`:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

When no matching bean exists to override, the context fails with an error. This helps catch missing test configurations or misspelled names, rather than silently adding a new mock while the test still runs.

By default, the bean override mechanism may create a mock if no matching bean exists yet. Creating a new one can be useful in some test slices, but if the goal is to replace a specific real bean, `enforceOverride = true` makes that condition explicit.

### 6.2. @MockitoBean and @MockBean

In older Spring Boot projects, you may encounter `@MockBean` from `org.springframework.boot.test.mock.mockito`. Spring Framework 6.2 introduced `@MockitoBean` in Spring Test; Spring Boot 3.4 deprecated `@MockBean` in favor of the new annotation.

For projects already using Spring Framework 6.2 or Spring Boot 3.4 and above, prefer `@MockitoBean` for new tests if there are no compatibility constraints with older configurations. For projects on earlier versions, use the annotation supported by the version in use. Do not import two annotations with the same role from two different packages in the same test class.

## 7. Plain Mockito Mocks in Unit Tests

Not every test needs a Spring context. For a unit test of a service, you can create mocks with `@Mock` and inject them into the target object via its constructor or `@InjectMocks`.

Example:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void completesOrderWhenPaymentSucceeds() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-100", true));

        OrderResult result = orderService.completeOrder("CUS-42");

        assertTrue(result.completed());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

Here, `MockitoExtension` initializes `@Mock` and processes `@InjectMocks`; Spring does not create an `ApplicationContext`. This approach is fast and suitable for testing `OrderService` logic when dependencies can be replaced by mocks.

If the constructor has several dependencies, explicitly calling the constructor in the test is also a good option:

```java
@Test
void calculatesDiscount() {
    PaymentGateway gateway = mock(PaymentGateway.class);
    OrderService service = new OrderService(gateway);

    // Arrange, act and assert
}
```

Constructor injection makes it clear which dependencies are replaced and avoids relying on the test framework's field injection mechanism.

## 8. Choosing Beans Based on Spring Test Type

Test slice and test context annotations often suggest which beans should remain real and which should be replaced.

| Test Type | Beans to Keep Real | Beans Commonly Replaced |
|---|---|---|
| Plain Java service unit test | The object under test and value objects | Repository, gateway, clock, or external client via Mockito mock/fake |
| `@WebMvcTest` | Controller and related MVC infrastructure | Service/application facade via `@MockitoBean` or corresponding mock bean |
| `@DataJpaTest` | Repository, entity mappings, JPA, and test database | HTTP client or non-persistence dependencies if brought into the slice |
| `@JsonTest` | Jackson configuration and serializer/deserializer within test scope | Unrelated application dependencies, if any |
| `@SpringBootTest` | Application components involved in the integration flow to verify | External services or boundaries outside the test objective |

For example, in `@WebMvcTest(OrderController.class)`, the real controller is created to test routing, binding, validation, and responses. Application services are usually mocked because the test is not meant to verify service logic or the database. In `@DataJpaTest`, the repository and persistence layer should run for real inside the test slice; mocking the repository would skip the behavior the test needs to verify.

With `@SpringBootTest`, pick a specific flow to test. If the goal is to verify that the controller, service, and repository collaborate, keep them real and replace the external payment system. If the goal is to test service integration with the database, you can keep the service and repository real, while mocking an out-of-scope email gateway.

## 9. Selecting Beans with @Profile or @ConditionalOnProperty

An application can provide multiple implementations and select among them using profiles or properties. Example:

```java
@Component
@Profile("!test")
class HttpPaymentGateway implements PaymentGateway {
    // Calls the real payment provider.
}

@Component
@Profile("test")
class TestPaymentGateway implements PaymentGateway {
    // Returns deterministic test results.
}
```

The test activates the profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderPaymentIntegrationTest {
}
```

This approach works well when the application genuinely has distinct per-environment configurations, such as local, sandbox, and production implementations. You must ensure the test profile is never accidentally activated in production and that test implementations do not contain logic or data that could cause unintended effects.

If only one or a few test classes need to replace a bean, `@TestConfiguration` or `@MockitoBean` usually expresses the scope more clearly. Profiles are context-level configuration; activating a profile can change multiple beans at once and affects all tests using that profile.

## 10. Replacing a Bean with @TestBean When a Custom Implementation Is Needed

Spring Framework 6.2 added `@TestBean` to replace a bean in the context with an instance provided by a test factory method. This mechanism is suitable when you need a specific test implementation without using Mockito.

Illustrative example:

```java
import org.springframework.test.context.bean.override.convention.TestBean;

@SpringBootTest
class OrderServiceTest {

    @TestBean
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new SuccessfulPaymentGateway();
    }
}
```

The `static` factory method provides the instance that Spring registers as a bean override. Check that the bean is selected by type or name when multiple implementations exist in the context. `@TestBean` can be used to put a fake in place of an existing bean, whereas `@TestConfiguration` typically adds configuration and beans to the context.

If the project uses Spring Framework prior to 6.2, this annotation is not available; use `@TestConfiguration` and bean configuration appropriate for that version. There is no need to introduce `@TestBean` just to replace a simple dependency if `@MockitoBean` or test configuration already expresses the intent clearly.

## 11. Considerations When Replacing Beans

### 11.1. Bean Overrides Can Affect Context Caching

Spring Test caches the `ApplicationContext` based on configuration metadata. Test classes with the same configuration and the same bean overrides can reuse the context. If mocks or test configurations differ, context customizers and override metadata can produce different cache keys.

Do not mutate the global behavior of a shared bean across tests without resetting or explicitly reconfiguring it. `@MockitoBean` includes a mechanism to reset mocks according to the test lifecycle; with `MockitoExtension` in unit tests, the extension also manages mock state. If using a fake bean with mutable state, reset its state between tests or create an appropriately isolated context.

### 11.2. Do Not Mock the Object Under Test

If `OrderService` is the object whose behavior needs to be verified, do not replace `OrderService` itself with a mock and then verify its methods. Doing so only verifies that Mockito works, not production logic. Keep the target object real and replace its dependencies.

### 11.3. Do Not Mock Too Deeply

If a service calls three dependencies and the test mocks all underlying layers, the test may only verify a hardcoded sequence of interactions. During internal refactoring, the test breaks easily even though public behavior has not changed.

Replace only the boundaries that need to be controlled, such as a payment gateway, email gateway, or external system. Keep components within the target behavioral scope real.

### 11.4. Be Careful with @Primary and Multiple Beans of the Same Type

Adding a fake bean with `@Primary` does not guarantee that every injection point uses the fake. `@Qualifier`, bean names, collection injection, and configuration conditions can alter the outcome. If the goal is to replace a specific bean, use an explicitly identified bean override or verify wiring via a context test.

### 11.5. Reset Fake State Between Tests

A fake storing data in a map or list can retain state from a previous test if the context is cached. You can provide a `clear()` method and call it in `@BeforeEach`, or design an immutable fake with data passed through its constructor. Shared state must be managed explicitly so tests do not depend on execution order.

## 12. Decision Example for an Order Flow

Suppose an order flow has the following components:

```text
OrderController
      |
      v
OrderService
   /       \
  v         v
OrderRepository   PaymentGateway
```

The test goal determines how beans are replaced:

| Goal | Controller | Service | Repository | PaymentGateway |
|---|---|---|---|---|
| Service rule unit test | Spring not needed | Real | Mock/fake | Mock |
| HTTP controller test | Real | Mock bean | Not involved | Not involved |
| Order persistence test | Controller not needed | Can be real | Real | Fake/mock if called by the flow |
| Order flow integration | Real | Real | Real | Fake or mock depending on scope |

Example service unit test focused on successful payment:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    OrderService service;

    @Test
    void savesOrderAfterSuccessfulPayment() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(new PaymentResult("PAY-1", true));

        service.createOrder("CUS-1");

        verify(repository).save(any(Order.class));
    }
}
```

Example controller test using the Spring MVC slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsAcceptedWhenOrderIsCreated() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"customerId":"CUS-1"}"""))
                .andExpect(status().isAccepted());

        verify(orderService).createOrder("CUS-1");
    }
}
```

An integration example with a real repository and payment fake can use `@SpringBootTest` with `@TestConfiguration`. The test verifies that the order is actually saved and the payment status is recorded accurately, while the fake gateway returns deterministic results so it does not call an external payment provider.

## 13. Process for Selecting and Replacing Beans

When starting to write a Spring test, you can make decisions by following these steps:

1. **Identify the target object and behavior to protect.** This object should be kept real in the test.
2. **Identify dependency boundaries.** Which components are within test scope, and which are external services or only need to supply results?
3. **Choose the implementation for each dependency.** Keep the real bean when verifying integration; use a fake/stub when simple, reusable behavior is needed; use a Mockito mock when controlling return values or verifying interactions.
4. **Choose how to bring the dependency into the test.** Plain Java unit tests use `@Mock` or `mock(...)`; Spring contexts use `@MockitoBean`, `@TestConfiguration`, `@TestBean`, or an appropriate profile.
5. **Identify the exact bean to replace.** If multiple beans of the same type exist, use a qualifier or bean name. If you need to ensure the bean already exists, enable override enforcement when supported by the annotation.
6. **Manage state and lifecycle.** Reset mocks/fakes as needed, ensure containers/servers remain running while the context uses them, and avoid unintended shared mutable state.
7. **Test at the right layer.** Unit tests for logic, test slices for a portion of Spring, and integration tests for collaboration across multiple components.

A maintainable test typically keeps the target object real, replaces out-of-scope dependencies with appropriate test doubles, and initializes a Spring context only when verifying behavior provided by Spring. Real beans, fakes/stubs, and Mockito mocks all have a place in a test suite; what matters is that each choice serves a specific behavior the test needs to prove.
