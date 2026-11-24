# Mock Is Not Injected Into the Object Actually Being Called

A test may create a mock properly and stub the expected values, yet still call the real dependency when executed. The usual result is that the test hits the database, makes HTTP calls, accesses the filesystem, or returns data different from the stub. A common cause is that the mock lives inside the test object, while the object actually invoked is a separate instance managed by Spring.

To diagnose this issue, determine precisely **which object is executing the behavior** and **who created that object**. Mockito's `@Mock` creates a mock within Mockito's scope; it does not automatically replace a bean inside the Spring `ApplicationContext`. When a test invokes a Spring bean, use Spring's bean override mechanism such as `@MockitoBean` or the mock bean configuration matching your project version.

## 1. Understanding the Two Object Graphs

In a test combining Spring and Mockito, two independent object graphs can exist simultaneously:

```text
Mockito graph in the test                     Spring graph in ApplicationContext

@Mock PaymentGateway                          Real PaymentGateway
       |                                               |
       v                                               v
Test field                                    OrderService bean
                                                       |
                                                       v
                                              Real PaymentGateway
```

Declaring `@Mock PaymentGateway` only creates a mock and assigns it to the test field when the Mockito extension processes the test. Spring does not automatically know that field exists, nor does it replace dependencies inside already-created beans.

If the test invokes an `orderService` injected by Spring, `orderService` may still hold the real `PaymentGateway`. Stubbing on the mock field has no effect on Spring's object graph.

There are two valid testing approaches, depending on your goal:

- Pure Mockito unit test: Mockito creates both the mocks and the object under test, then injects the mocks into that object.
- Spring test: Spring creates the object under test, and the test instructs Spring to replace the dependency bean with a mock in the `ApplicationContext`.

Bugs typically happen when mixing the two approaches without realizing they create two separate instances.

## 2. Symptoms That a Mock Is Not Being Used

Common symptoms include:

- `when(mock.method()).thenReturn(...)` is declared, yet the returned result still matches the real system.
- `verify(mock).method()` reports `Wanted but not invoked` even though the business flow appears to call the dependency.
- The test unexpectedly requires a database, message broker, or external HTTP service.
- Stubbing returns `null` or default values because the actual call goes to a different mock instance.
- The test runs through a different implementation than the one the author thought was replaced.
- One test class works, while another test uses a different bean due to qualifiers, profiles, or context configuration.

These symptoms do not necessarily mean Mockito is broken. Check wiring, context scope, and actual object instances before changing stubbing logic.

## 3. `@Mock` Does Not Replace a Bean in Spring

Consider a service receiving its dependency via constructor:

```java
interface PaymentGateway {
    PaymentResult charge(String orderId, long amount);
}

class OrderService {

    private final PaymentGateway paymentGateway;

    OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult pay(String orderId, long amount) {
        return paymentGateway.charge(orderId, amount);
    }
}
```

The application registers the real implementation:

```java
@Component
class HttpPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        // Call the payment provider over HTTP.
        return callPaymentProvider(orderId, amount);
    }
}
```

An easily confused test:

```java
@SpringBootTest
class OrderServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void usesStubbedPaymentResult() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

Here, `@Mock` creates a Mockito mock for the `paymentGateway` field. However, `orderService` comes from the Spring context; Spring already injected the `HttpPaymentGateway` bean into the service. The two dependencies are not the same object. The test's stubbing does not control the calls made by the service.

Do not try to fix this by stubbing repeatedly or tweaking matchers. Put the mock into the right object graph first.

## 4. Using `@MockitoBean` to Replace a Bean in ApplicationContext

In Spring Framework 6.2 and later, `@MockitoBean` declares a Mockito mock as a bean override in the test `ApplicationContext`. The annotation lives in the `org.springframework.test.context.bean.override.mockito` package.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class OrderServiceTest {

    @Autowired
    OrderService orderService;

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void usesThePaymentGatewayMockFromSpringContext() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

Spring applies the mock to the matching bean in the context. When creating `OrderService`, the dependency Spring injects is the mock declared by `@MockitoBean`, so stubbing and verifying on the `paymentGateway` field observe the actual call.

By default, `@MockitoBean` can replace an existing bean or create a mock bean if no matching bean exists yet. If the test must verify that a real bean actually exists in the context before overriding it, use `enforceOverride = true`:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
```

In that case, the test fails if no bean is found to override. This option is useful for catching slice configurations or component scans missing a bean that the test expects.

## 5. Choosing the Right Annotation for Your Spring Version

Spring projects may use different annotations depending on version:

| Annotation | Package | Role |
|---|---|---|
| `@Mock` | `org.mockito.Mock` | Creates a mock in the test; does not replace a Spring bean |
| `@InjectMocks` | `org.mockito.InjectMocks` | Mockito creates the object under test and injects matching mocks/spies |
| `@MockitoBean` | `org.springframework.test.context.bean.override.mockito.MockitoBean` | Overrides a bean with a Mockito mock in the Spring context |
| `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito.MockitoSpyBean` | Wraps an existing bean with a spy in the Spring context |
| `@MockBean` | `org.springframework.boot.test.mock.mockito.MockBean` | Legacy Spring Boot mechanism to add/replace a bean with a mock |

`@MockitoBean` and `@MockitoSpyBean` were introduced in Spring Framework 6.2. Spring Boot 3.4 switched to recommending these newer annotations; the older `@MockBean` and `@SpyBean` were marked deprecated in the Boot 3.4 line. For older Boot projects without Spring Framework 6.2, use `@MockBean` according to your managed version.

Example compatible with older Spring Boot projects:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class OrderServiceLegacyTest {

    @Autowired
    OrderService orderService;

    @MockBean
    PaymentGateway paymentGateway;
}
```

Do not accidentally import `org.mockito.Mock` when the goal is to replace a Spring bean. The annotation names look similar, yet their scopes of impact differ.

## 6. Using `@Mock` and `@InjectMocks` for Pure Unit Tests

If no Spring context is needed, let Mockito instantiate the object under test. This is the proper way to use `@Mock`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    OrderService orderService;

    @Test
    void returnsTheResultFromGateway() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

`MockitoExtension` initializes Mockito annotations. `@InjectMocks` tells Mockito to create an `OrderService` instance and inject matching mocks. The test invokes that exact instance, so the mock dependency is used.

`@SpringBootTest` is unnecessary for the test above. Nor should you simultaneously inject a separate `OrderService` via `@Autowired` and call the Spring bean while stubbing mocks created for `@InjectMocks`. Calling the wrong instance brings back the exact original bug.

Mockito generally prefers constructor injection, then attempts setter/property and field injection per `@InjectMocks` semantics. However, `@InjectMocks` is not a full dependency injection container: it does not run the Spring lifecycle, nor apply bean post-processors, `@Value`, `@Transactional`, `@Async`, qualifier semantics, or Spring AOP configuration. If a test needs those behaviors, use a Spring context.

## 7. Testing the Right Bean in a Spring MVC Slice

A common case is testing a controller with `@WebMvcTest`. This slice creates the MVC infrastructure and selected controllers; services are typically replaced with mocks.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void delegatesToTheMockedService() throws Exception {
        when(orderService.findStatus("ORD-1"))
                .thenReturn("PAID");

        mockMvc.perform(get("/orders/ORD-1/status"))
                .andExpect(status().isOk());

        verify(orderService).findStatus("ORD-1");
    }
}
```

In a slice test, `@MockitoBean` supplies the dependency required by the controller. There is no need to load the database or entire service layer when the test only cares about the MVC contract.

If the controller requires another bean outside the slice, you can mock that bean, import the needed configuration, or choose a broader test context. `@WebMvcTest` does not automatically load every service or repository in the application.

## 8. Qualifiers and Multiple Beans of the Same Type

If multiple beans implement the same interface, declaring a mock by type alone may fail to identify the bean used by the target object. For example:

```java
@Component("cardPaymentGateway")
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("walletPaymentGateway")
class WalletPaymentGateway implements PaymentGateway {
    // ...
}
```

The service selects the implementation via qualifier:

```java
class OrderService {

    private final PaymentGateway paymentGateway;

    OrderService(@Qualifier("cardPaymentGateway") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

The test must also override the matching candidate:

```java
@MockitoBean
@Qualifier("cardPaymentGateway")
PaymentGateway cardPaymentGateway;
```

Or specify the bean name directly:

```java
@MockitoBean(name = "cardPaymentGateway")
PaymentGateway paymentGateway;
```

`@Primary` only influences candidate selection when Spring resolves by-type injection without a specific qualifier. If the constructor asks for a specific qualifier, mock the exact bean selected by that qualifier.

The field name of `@MockitoBean` can also act as a fallback qualifier when no explicit qualifier is present. Therefore, when multiple beans of the same type exist, the field name should reflect the bean the test intends to override. The clearest approach remains declaring `@Qualifier` or `name` whenever the application configures multiple implementations.

## 9. Distinguishing Mock Beans from Spy Beans

`@MockitoBean` replaces a bean with a mock. Unstubbed calls follow Mockito's default behavior, typically returning default values such as `null`, `0`, or `false`.

`@MockitoSpyBean` wraps an existing bean with a spy, so unstubbed calls can still execute real logic. Use a spy when you want to retain most of a bean's behavior while observing or overriding specific calls.

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class PricingServiceTest {

    @Autowired
    PricingService pricingService;

    @MockitoSpyBean
    ExchangeRateProvider exchangeRateProvider;
}
```

With a spy, be careful when stubbing methods that have side effects. Using `when(spy.method()).thenReturn(...)` can invoke the real method while setting up the stub. Mockito provides `doReturn(...).when(spy).method(...)` to avoid invoking the real method in certain cases.

Do not reach for a spy simply because a mock was not injected. First determine whether the test intends to replace the entire dependency or preserve the real implementation. If the goal is to prevent calls to external systems, a mock bean is usually a better fit than a spy.

## 10. Objects Created with `new` Do Not Receive Spring Dependency Overrides

Another mistake is creating a controller/service with `new` while expecting `@MockitoBean` to affect that object:

```java
@SpringBootTest
class OrderControllerTest {

    @MockitoBean
    OrderService orderService;

    @Test
    void test() {
        OrderController controller = new OrderController(
                new RealOrderService());

        // This controller holds RealOrderService.
    }
}
```

`@MockitoBean` only replaces beans inside the Spring context. Manually instantiated objects are not managed by Spring, so the constructor keeps whichever `RealOrderService` the test passed in.

Choose one of two approaches:

**Spring-managed approach:** inject the controller from the context and let Spring pass the mock bean into its constructor.

```java
@Autowired
OrderController controller;

@MockitoBean
OrderService orderService;
```

**Unit test approach:** construct the controller manually while passing the mock directly.

```java
@ExtendWith(MockitoExtension.class)
class OrderControllerUnitTest {

    @Mock
    OrderService orderService;

    @InjectMocks
    OrderController controller;
}
```

Do not construct an instance with `new` and then test it as if it were a Spring bean.

## 11. Verifying Whether the Bean Actually Exists in the Test Context

If `@MockitoBean` is not being used as expected, check whether the target bean exists in the context. A slice may not load the service; a profile may exclude the bean; or a `@ConditionalOnProperty` may not be satisfied.

Example when the exact bean name is known:

```java
@Autowired
ApplicationContext applicationContext;

@MockitoBean(name = "paymentGateway")
PaymentGateway paymentGateway;

@Test
void contextUsesTheExpectedMock() {
    assertThat(applicationContext.getBean("paymentGateway"))
            .isSameAs(paymentGateway);
}
```

This is a helpful diagnostic assertion when you need to confirm that the override was applied. It does not need to be repeated in every test once configuration is clear.

When `enforceOverride = true` is set, Spring fails if no bean exists to replace. This helps distinguish two cases:

- The context has the right bean, but the test did not override the right candidate.
- The context did not load the bean that the test assumed it was testing.

In a slice test, if the bean to mock is outside the slice, letting `@MockitoBean` create a new mock satisfies the controller's dependency. If you want to test full production wiring, use a broader context and `enforceOverride = true` to verify the bean is actually present in that configuration.

## 12. Other Wiring Causes to Check

Beyond using the wrong annotation, a mock might go unused for the following reasons:

| Cause | Symptom | Resolution |
|---|---|---|
| Multiple beans share an interface | Service receives a different implementation than the mock | Use `@Qualifier` or `@MockitoBean(name = ...)` |
| Test invokes a manually created object | Spring bean override has no effect | Inject the bean from context or pass the mock to the constructor |
| Test slice does not load the target bean | Bean is missing or dependency is unconfigured | Import configuration, use the right slice, or widen the context |
| Profile/condition differs from test expectation | Production bean is not registered | Check `@ActiveProfiles`, properties, and `@Conditional...` |
| Factory creates another object | Test field and runtime bean are not the same instance | Inspect `@Bean` methods and where the object is instantiated |
| Dependency is held by another singleton | New mock bean does not replace a reference created elsewhere | Inspect lifecycle and object graph of that singleton |
| Proxy/AOP is present | Injected object may be a proxy | Identify the target bean and verify the mock field is properly overridden |
| Wrong stub arguments or matchers | Mock is invoked but does not match stub | Use `ArgumentCaptor`, consistent matchers, and inspect actual calls |
| Test runs async or on another thread | Verification runs before the call completes | Wait for completion via latch/Awaitility or publisher verification |

Proxies from `@Transactional`, `@Async`, security, or AOP do not automatically cause mocks to be bypassed. However, proxies can make inspecting instances harder. Check the dependency bean actually passed into the target and verify against the mock field registered in the context.

## 13. Distinguishing Injection Errors from Stubbing Errors

Not every `Wanted but not invoked` error is a Spring wiring issue. The mock may be wired correctly, yet the call never happens because execution took a different conditional branch, or actual arguments failed to match the stub.

### Inspecting Calls with `ArgumentCaptor`

```java
ArgumentCaptor<String> orderIdCaptor = ArgumentCaptor.forClass(String.class);

verify(paymentGateway).charge(orderIdCaptor.capture(), anyLong());
assertThat(orderIdCaptor.getValue()).isEqualTo("ORD-1");
```

If `verify` succeeds yet the stub was not applied, inspect your matchers. Mockito requires that when one argument uses a matcher, all remaining arguments must also use matchers:

```java
when(paymentGateway.charge(eq("ORD-1"), anyLong()))
        .thenReturn(new PaymentResult("APPROVED"));
```

If `verify` finds no invocation at all, go back and verify the instance and object graph before changing matchers.

### Checking Whether the Mock Received Any Interactions

```java
verifyNoInteractions(paymentGateway);
```

This assertion is only appropriate when the test's contract requires the dependency not to be called. If the test expects a call, verify the exact method and arguments. Do not use `verifyNoInteractions` as a default diagnostic tool after calling the service.

## 14. Testing with Multiple Dependencies

When a service has multiple dependencies, mock only the boundaries you need to control. For example:

```java
@SpringBootTest
class OrderWorkflowTest {

    @Autowired
    OrderWorkflow orderWorkflow;

    @MockitoBean
    PaymentGateway paymentGateway;

    @MockitoBean
    FraudCheckClient fraudCheckClient;

    @Test
    void approvesOrderWhenChecksPass() {
        when(fraudCheckClient.isAllowed("ORD-1")).thenReturn(true);
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        OrderResult result = orderWorkflow.process("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("PAID");
        verify(fraudCheckClient).isAllowed("ORD-1");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

Both mocks are registered in the Spring context, so the `OrderWorkflow` bean receives those exact dependencies. Repositories or the database may remain real if the test intentionally verifies persistence. The test boundary should stay consistent: mocking external gateways while using a real database is a valid integration test.

## 15. Resetting Mocks and Sharing ApplicationContext

Spring TestContext can cache contexts to speed up execution across test classes. Mock beans registered in a context may be reused alongside that context under the test framework's rules. Spring bean overrides reset mocks after each test method by default so previous invocations or stubbings do not leak into the next test.

If you alter the reset policy, understand the impact when tests run concurrently. Never use a singleton mock to store test-specific state. Each test should declare its own stubbing and verify only interactions produced by that test.

If a test changes context configuration or uses a different override, Spring may create a separate context. This affects execution time, not whether the mock was injected. Check test configuration and bean identity before adding `@DirtiesContext`.

## 16. Systematic Diagnostic Workflow

When a stub is ignored or `verify` reports no invocations on the mock, follow this sequence:

1. Identify the method actually being called and the object receiving that call.
2. Determine whether that object was created by Spring or via `new`/a custom factory.
3. Check whether the test calls an `@Autowired` bean or an `@InjectMocks` instance.
4. For pure Mockito tests, use `@Mock` and `@InjectMocks` within the same object graph.
5. For Spring tests, replace dependencies using `@MockitoBean` or `@MockBean` appropriate for your version.
6. Check bean candidates by type, name, qualifier, profile, and conditional configuration.
7. For slice tests, confirm the target bean is in the context or mocked to satisfy dependencies.
8. Stub with the right arguments and matchers; use `ArgumentCaptor` to observe actual calls.
9. For async flows, wait for the call to finish before verifying.
10. Only after confirming the right instance is used should you consider changing stubbing or matchers.

## 17. Common Pitfalls

| Practice | Why it fails | Better approach |
|---|---|---|
| Using `@Mock` then calling an `@Autowired` service | The mock exists only on the test field and does not replace the context bean | Use `@MockitoBean` or `@MockBean` |
| Using `@InjectMocks` yet calling a Spring bean | Mockito and Spring create two separate instances | Choose either a pure unit test or a Spring test cleanly |
| Creating a controller with `new` while expecting bean overrides to apply | Manually created objects bypass Spring injection | Inject the controller from the context or pass mocks directly |
| Mocking by type when multiple implementations exist | Spring may select a different bean | Declare a qualifier or bean name |
| Using `@MockitoBean` in a slice while expecting all production services to load | Slices build only a partial context | Import configurations or choose a broader context |
| Using a spy to block calls to external systems | Spies still run real methods unless stubbed | Use a mock bean for dependencies that must be replaced completely |
| Tweaking matchers before confirming the mock is even called | Can hide wiring errors | Verify the instance and arguments first |
| Adding `@DirtiesContext` immediately when `verify` fails | Does not fix injection causes | Diagnose the object graph and bean overrides first |

## 18. References

- [Spring Framework Reference — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): bean overriding mechanism in Spring TestContext.
- [Spring Framework Javadoc — `@MockitoBean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): replacing a bean with a Mockito mock.
- [Spring Framework Javadoc — `@MockitoSpyBean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): wrapping an existing bean with a Mockito spy.
- [Spring Boot Reference — Mocking and Spying Beans](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): mock/spy bean support in Spring Boot tests and transition to Spring Framework annotations.
- [Mockito — `@InjectMocks`](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/InjectMocks.html): how Mockito constructs instances and injects mocks in unit tests.
- [Mockito — JUnit Jupiter Extension](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html): initializing and managing Mockito annotations for JUnit Jupiter.

A mock only affects the object graph it is actually wired into. In unit tests, let Mockito construct the object under test and inject mocks into it. In Spring tests, instruct Spring to override the right bean using `@MockitoBean` or the annotation matching your project's version. When stubbing has no effect, verify the instance, bean type/name/qualifier, and context scope before adjusting matchers.
