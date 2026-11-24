# `@MockitoBean` and Replacing Collaborators in the Context

When testing a Spring application, it is sometimes necessary to keep the `ApplicationContext`, controllers, services, or real configuration intact while replacing a collaborator with a mock. For example, an MVC test needs to run a request through Spring MVC and security filters without calling a real database or payment gateway. We want the real controller to be instantiated in the context, while `OrderService` is replaced by a Mockito mock to control the outcome.

Spring Framework 6.2 introduced `@MockitoBean` to register a mock directly in the test `ApplicationContext`. This annotation replaces a matching bean with a Mockito mock; if no matching bean is found, Spring can create a new mock bean by default. As a result, beans that depend on the mocked type receive the mock during dependency injection.

`@MockitoBean` is especially useful in tests using `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or `@ContextConfiguration`, when the goal is to test part of the application inside a real context while isolating certain external dependencies.

## 1. What Is `@MockitoBean`?

`@MockitoBean` belongs to the package:

```java
org.springframework.test.context.bean.override.mockito.MockitoBean
```

It is an annotation of the Spring TestContext Framework, available since **Spring Framework 6.2.0**. It integrates Mockito with Spring's bean override mechanism to add a mock to the test `ApplicationContext` or replace an existing bean.

Basic example:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrderDetails() throws Exception {
        when(orderService.findById("order-42"))
            .thenReturn(new OrderResponse("order-42", "PAID"));

        mockMvc.perform(get("/orders/order-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-42"))
            .andExpect(jsonPath("$.status").value("PAID"));

        verify(orderService).findById("order-42");
    }
}
```

In this example, `OrderController` is a real bean created by Spring MVC. `OrderService` is replaced with a mock. The request flows through `MockMvc`, while the service result is controlled by the test using `when()` and `thenReturn()`.

When the controller injects `OrderService` through its constructor, it receives the exact mock registered in the context. The `orderService` field in the test class is also assigned the same mock by Spring, allowing the test to stub and verify directly.

## 2. Distinguishing `@MockitoBean` from `@Mock`

Both annotations create a Mockito mock, but their management scopes differ:

| Criterion | `@Mock` | `@MockitoBean` |
| --- | --- | --- |
| Source | Mockito | Spring Test |
| Common usage | Plain unit tests | Tests with an `ApplicationContext` |
| Registered in Spring context | No | Yes |
| Replaces an existing bean | No | Yes |
| Other beans automatically injected with mock | No | Yes, by matching type/qualifier |
| Creates Spring context | Not required | Requires Spring Test integration |
| Appropriate goal | Testing a class by passing mocks to its constructor | Testing part of an application inside a Spring context |

Plain unit test example using `@Mock`:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(repository);
    }

    @Test
    void returnsOrderWhenItExists() {
        when(repository.findById("order-42"))
            .thenReturn(Optional.of(sampleOrder()));

        Order result = orderService.findById("order-42");

        assertEquals("order-42", result.getId());
    }
}
```

This unit test does not need a Spring context. We instantiate the real service directly and pass the mock repository to its constructor.

When you need to test controllers, filters, converters, bean wiring, or Spring configuration, `@MockitoBean` lets you replace a collaborator directly in the context. There is no need to use `@MockitoBean` for every unit test; use it only when the Spring context is part of what needs to be tested.

## 3. Spring Framework 6.2 and Version Compatibility

`@MockitoBean` was introduced in Spring Framework 6.2.0. If the project uses Spring Framework 6.1 or earlier, this annotation does not exist in `spring-test`.

| Version | Approach |
| --- | --- |
| Spring Framework prior to 6.2 | Use the mechanism supported by that version, typically Spring Boot Test's `@MockBean` or manual mocks in unit tests |
| Spring Framework 6.2 and above | Use Spring Test's `@MockitoBean` |
| Spring Boot 3.4 and above | `@MockitoBean` can be used; Spring Boot's `@MockBean` is deprecated in favor of the Spring Framework annotation |

In Spring Boot, the Spring Framework version is usually controlled by dependency management. Check the actual `spring-test` version on the test runtime classpath before using the annotation.

With Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
```

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

If the project is not yet on Spring Framework 6.2, you cannot simply add the `@MockitoBean` import without upgrading compatible dependencies. Within the Spring Boot ecosystem, upgrade via a supported Boot version rather than forcing a Spring Framework version that conflicts with the project's dependency management.

## 4. How Spring Replaces Beans in the Context

When `@MockitoBean` is detected, Spring Test registers a bean override while building the test `ApplicationContext`. The mock is created by Mockito and placed into the context by matching type, bean name, or qualifier.

By default, the strategy is **replace or create**:

- If a matching bean is found, that bean is replaced with a Mockito mock.
- If no matching bean is found, Spring creates a new mock bean and registers it in the context.

This is useful in test slices. For example, `@WebMvcTest(OrderController.class)` loads only part of the web layer; `OrderService` may not be included in the slice. `@MockitoBean OrderService` creates a mock so the controller can still be injected.

If you want to require that an existing bean be replaced, set `enforceOverride = true`:

```java
@MockitoBean(enforceOverride = true)
OrderService orderService;
```

With this configuration, if the context has no matching bean to replace, Spring fails when creating the context. This is useful when a test must ensure the production bean actually exists and is being overridden; it prevents the test from silently creating a new mock due to missing context configuration.

## 5. Declaring a Mock on a Test Class Field

The most common pattern is placing `@MockitoBean` on a field in the test class:

```java
@SpringBootTest
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsApproved() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-123"));

        CheckoutResult result = checkoutService.checkout(validCommand());

        assertTrue(result.isCompleted());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

`CheckoutService` and the remaining beans in the context are created according to the application configuration. When Spring injects `PaymentGateway` into `CheckoutService`, the mock registered by `@MockitoBean` is used.

The annotated field also receives the mock so the test can configure behavior and verify calls. Consequently, the test does not need to call `applicationContext.getBean(PaymentGateway.class)` to retrieve the mock.

### Field Name and Qualifier

If the context has multiple beans of the same type, Spring needs to know which bean to replace. You can place `@Qualifier` on the field:

```java
@MockitoBean
@Qualifier("primaryPaymentGateway")
PaymentGateway paymentGateway;
```

Or specify the bean name:

```java
@MockitoBean(name = "primaryPaymentGateway")
PaymentGateway paymentGateway;
```

If neither a qualifier nor a name is specified, Spring first searches for beans by type. The field name can be used as a fallback qualifier when disambiguating multiple beans of the same type. Thus, the field name in a test can also influence which bean is selected.

Use explicit qualifiers or bean names when multiple implementations exist, such as `sandboxPaymentGateway`, `primaryPaymentGateway`, and `fallbackPaymentGateway`. Do not rely on bean declaration order to choose an implementation.

## 6. Replacing a Specific Bean When Multiple Implementations Exist

Suppose the application has two adapters implementing `PaymentGateway`:

```java
@Component("cardPaymentGateway")
class CardPaymentGateway implements PaymentGateway {
    // Calls the card payment gateway
}

@Component("walletPaymentGateway")
class WalletPaymentGateway implements PaymentGateway {
    // Calls the digital wallet gateway
}
```

The service injects an implementation by qualifier:

```java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(
            @Qualifier("cardPaymentGateway") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

The test replaces only the card adapter:

```java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(name = "cardPaymentGateway")
    PaymentGateway cardGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesTheCardGatewayForCardCheckout() {
        when(cardGateway.charge(any()))
            .thenReturn(PaymentResult.approved("card-123"));

        checkoutService.checkout(cardCommand());

        verify(cardGateway).charge(any());
    }
}
```

The digital wallet bean remains a real bean in the context. The test replaces the exact bean named `cardPaymentGateway`. If the service requires a specific implementation, the production qualifier and the test mock name should match.

## 7. Declaring Mocks at the Class Level with `types`

`@MockitoBean` can be placed at the type level on a test class. When used at the class level, declare the types to mock via the `types` attribute:

```java
@SpringBootTest
@MockitoBean(types = {
    PaymentGateway.class,
    NotificationGateway.class
})
class OrderWorkflowTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderWithoutCallingExternalSystems() {
        // Mocks are registered in the ApplicationContext
    }
}
```

Class-level declarations are useful when a group of tests or a test configuration shares the same set of mocks. If a test needs to stub or verify directly, it can inject the mock with `@Autowired` or use field-level declarations for clear field references.

Field-level declarations are usually easier to read when each mock has distinct behavior in tests. Type-level declarations fit when you want to group shared bean overrides for an entire class or reuse configuration via a composed annotation.

## 8. `@MockitoBean` with `@WebMvcTest`

`@WebMvcTest` loads only the required MVC slice, such as controllers, MVC configuration, converters, selected filters, and related web components. Services or repositories are generally not loaded as in a full context.

When a controller depends on a service, supply a mock with `@MockitoBean`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsNotFoundWhenOrderDoesNotExist() throws Exception {
        when(orderService.findById("missing"))
            .thenThrow(new OrderNotFoundException("missing"));

        mockMvc.perform(get("/orders/missing"))
            .andExpect(status().isNotFound());
    }
}
```

This test verifies request mapping, exception handlers, and controller responses through the MVC pipeline. `OrderService` is replaced by a mock so the test needs neither a database nor external services.

If a controller has multiple collaborators, declare a mock for each dependency the controller requires. If a dependency is created by a separate test configuration, ensure the test context loads that configuration properly.

Do not use `@MockitoBean` to replace the controller under test. If the controller itself is replaced by a mock, requests will not run through the real controller implementation and the test loses its purpose.

## 9. `@MockitoBean` with `@SpringBootTest`

`@SpringBootTest` creates a broader context and is commonly used to test multiple beans collaborating together. You can replace an external system with a mock while keeping other application components real:

```java
@SpringBootTest
class PlaceOrderIntegrationTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    PaymentPort paymentPort;

    @Test
    @Transactional
    void persistsOrderWhenPaymentSucceeds() {
        when(paymentPort.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-42"));

        OrderId orderId = placeOrderService.place(validCommand());

        assertTrue(orderRepository.findById(orderId).isPresent());
        verify(paymentPort).charge(any(PaymentRequest.class));
    }
}
```

In this example, the repository and service are real beans, while the payment port is a mock. The test can verify that the service collaborates with real persistence and handles controlled payment responses.

If the goal is to test the payment gateway's HTTP adapter, do not replace that adapter with a mock in the same test. Write a separate adapter test using a mock server to verify request/response mapping.

## 10. `@MockitoBean` with Other Test Slices

Other test slices can also use bean overrides when they need to replace a collaborator outside the slice's scope.

For example, `@DataJpaTest` focuses on JPA:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @MockitoBean
    AuditPublisher auditPublisher;

    @Test
    void savesOrderWithoutPublishingToExternalBroker() {
        // Tests the real repository; the publisher is replaced by a mock if the bean belongs to the slice
    }
}
```

However, `@DataJpaTest` does not automatically load every application bean. If `AuditPublisher` is not in the slice, `@MockitoBean` may create a new mock by default. If you want to verify that the slice actually had the bean to replace, use `enforceOverride = true`.

Keep each slice focused on its objective. If you have to import too many services and adapters just to make the test run, you may need a `@SpringBootTest` or a dedicated configuration test rather than over-expanding the slice.

## 11. Controlling Mocks with Mockito

Once `@MockitoBean` registers a mock, standard Mockito APIs can be used:

```java
when(paymentGateway.charge(any()))
    .thenReturn(PaymentResult.approved("payment-123"));

verify(paymentGateway).charge(any());
verify(notificationGateway, never()).send(any());
```

Common techniques:

| API | Purpose |
| --- | --- |
| `when(...).thenReturn(...)` | Configure return values |
| `when(...).thenThrow(...)` | Simulate exceptions |
| `doAnswer(...)` | Produce responses based on arguments or custom logic |
| `verify(...)` | Verify that a collaborator was called |
| `never()` | Verify no invocations occurred |
| `times(n)` | Verify invocation count |
| `ArgumentCaptor` | Capture actual arguments for assertions |

Example verifying payload:

```java
@Test
void sendsConfirmationForTheCreatedOrder() {
    when(paymentGateway.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    OrderId orderId = orderService.place(validCommand());

    ArgumentCaptor<OrderConfirmation> captor =
        ArgumentCaptor.forClass(OrderConfirmation.class);

    verify(notificationGateway).send(captor.capture());

    assertEquals(orderId, captor.getValue().orderId());
    assertEquals("customer@example.test", captor.getValue().email());
}
```

Verify only interactions that are meaningful to the contract. If a test verifies every internal call, a behavior-preserving refactor can easily break the test.

## 12. Resetting Mocks Between Test Methods

A mock in the context can be used by multiple test methods. If stubbing or invocation history remains, subsequent tests may be affected.

`@MockitoBean` supports the `reset` attribute. By default, mocks are reset after each test method using the `MockReset.AFTER` policy:

```java
@MockitoBean(reset = MockReset.AFTER)
PaymentGateway paymentGateway;
```

Main options:

| Value | Meaning |
| --- | --- |
| `MockReset.AFTER` | Reset after each test method; this is the default |
| `MockReset.BEFORE` | Reset before each test method |
| `MockReset.NONE` | Do not automatically reset the mock |

Example using `NONE`:

```java
@MockitoBean(reset = MockReset.NONE)
PaymentGateway paymentGateway;
```

Choose `NONE` only when there is a clear reason and the test manages stubs and invocation history itself. Otherwise, mock state can leak between test methods.

Resetting a mock clears stubbing and interaction history according to Mockito's mechanism. It does not undo side effects previously executed by a real implementation. With `@MockitoBean`, the bean is replaced by a mock so that bean's real methods do not run; however, other beans in the context can still perform their side effects.

## 13. `@MockitoBean` and the Context Cache

Spring Test caches the `ApplicationContext` so tests with equivalent configurations can reuse the context. Bean overrides are part of the test context configuration. Therefore, test classes with different sets of `@MockitoBean` declarations may require different context cache entries.

Several factors can make bean override configurations differ:

- Type of the mock.
- Specified bean name.
- Qualifier metadata.
- Override configuration attributes.
- Number and declaration style of mocks in the test class.

The field name can also act as a fallback qualifier. Consequently, two test classes mocking the same type with different field names may be treated as having different override configurations. To improve context reuse, keep field names and metadata consistent for shared mocks.

Avoid adding many `@MockitoBean` declarations to a shared base class if each subclass actually needs a different set of dependencies. That can bloat the context or produce many distinct cache keys. Mock only the collaborators needed for the test.

## 14. Sharing Mock Configurations via a Test Superclass or Meta-Annotation

When multiple test classes need the same bean overrides, you can organize a shared configuration. For example, a base test class:

```java
abstract class ExternalGatewayTestSupport {

    @MockitoBean
    protected PaymentGateway paymentGateway;

    @MockitoBean
    protected NotificationGateway notificationGateway;
}
```

Subclasses can use these mocks:

```java
@SpringBootTest
class OrderWorkflowTest extends ExternalGatewayTestSupport {

    @Autowired
    OrderService orderService;
}
```

Spring Test supports inheriting test configurations and bean overrides following TestContext rules. Keep the base class small with a genuinely shared group of mocks, and avoid creating a superclass containing every mock for the entire system.

For shared type-level configuration, you can create a composed annotation using the appropriate Spring Test annotations. This is useful when multiple classes need the same set of bean overrides. Make sure the configuration does not inadvertently replace a collaborator that one test needs to verify for real.

## 15. Bean Overrides in a Context Hierarchy

Some applications use `@ContextHierarchy` to create a parent context and child contexts. If a test needs to replace a bean at a specific level, `@MockitoBean` provides the `contextName` attribute to restrict the bean override to the correspondingly named context configuration.

Illustrative example:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "parent", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class OrderWebIntegrationTest {

    @MockitoBean(contextName = "web")
    OrderViewService orderViewService;
}
```

When using a hierarchy, identify whether the bean is defined in the parent or child context. Without scoping to the right context, a bean override may apply at multiple levels by default and produce unexpected results. `contextName` must match the name declared in `@ContextConfiguration`.

If the application does not need a parent-child context hierarchy, do not include `contextName` in standard configurations.

## 16. Distinguishing `@MockitoBean` and `@MockitoSpyBean`

Both annotations belong to Spring Test 6.2's bean override infrastructure, but they serve different purposes:

| Annotation | Behavior |
| --- | --- |
| `@MockitoBean` | Replaces the bean with a mock; calls are controlled by Mockito and do not run the original implementation by default |
| `@MockitoSpyBean` | Wraps an existing bean with a spy; unstubbed methods continue running the real implementation |

Spy example:

```java
@SpringBootTest
class PricingServiceTest {

    @MockitoSpyBean
    PricingService pricingService;

    @Test
    void usesRealPricingLogic() {
        BigDecimal total = pricingService.calculateTotal(sampleCart());

        assertTrue(total.signum() > 0);
        verify(pricingService).calculateTotal(any());
    }
}
```

With a spy, be careful when stubbing. The `when(spy.method()).thenReturn(...)` syntax can invoke the real method during setup. Use `doReturn(...).when(spy).method(...)` when you want to avoid side effects during stubbing.

When the goal is to completely replace an external collaborator such as a payment gateway, email sender, or remote client, `@MockitoBean` is usually clearer. Use a spy when you need to preserve real behavior and only observe or selectively override part of a bean.

## 17. Bean Overrides Should Not Replace the Target Under Test

When using `@MockitoBean`, keep the bean under test as a real bean. For example:

- Controller test: keep the controller real, mock the service.
- Service test: keep the service real, mock the repository or outbound port.
- Orchestration test: keep the use case real, mock external systems.
- HTTP adapter test: keep the adapter real and use a mock server on the partner side.

If you replace `OrderService` itself with a mock in a test named `OrderServiceIntegrationTest`, the test may only verify that the mock was called without executing any service logic. The test name and assertions then fail to prove the service's business behavior.

Similarly, if you replace a repository with a mock in `@DataJpaTest`, the test no longer verifies that repository's queries or JPA mappings. Decide on the boundary under test before choosing which beans to replace.

## 18. Conditional Bean Replacement and `enforceOverride`

By default, `@MockitoBean` uses a replace-or-create strategy. This works well when a test slice does not contain the production bean but still needs a mock collaborator to instantiate a controller or component.

When a test needs to guarantee that the real bean was already configured, enable `enforceOverride`:

```java
@SpringBootTest
class PaymentConfigurationTest {

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;
}
```

If there is no `PaymentGateway` bean in the context, Spring throws an error instead of silently creating a new mock. This helps catch errors in component scanning, configuration imports, profiles, or test setup.

Comparison example:

| Config | Existing Bean Present | Result |
| --- | --- | --- |
| Default | Yes | Replaces bean with mock |
| Default | No | Creates a new mock bean |
| `enforceOverride = true` | Yes | Replaces bean with mock |
| `enforceOverride = true` | No | Context fails to initialize because no bean exists to replace |

Choose the mode based on the test's intent. For slice tests, creating a new mock often makes sense; for tests verifying full-application wiring, strict override helps prevent missing configuration from being hidden.

## 19. Limitations and Points to Keep in Mind

Bean overriding is a mechanism for replacing beans in the test context, so several points should be kept in mind:

- **Does not test the replaced bean's implementation:** a mock does not prove the original bean's logic, transactions, or side effects.
- **Only overrides matching beans:** if type, qualifier, or name does not match, Spring may create a new mock or fail depending on `enforceOverride`.
- **Multiple beans of the same type require disambiguation:** use `@Qualifier`, bean names, or intentional field names.
- **Bean scope must be considered:** the bean override infrastructure is designed for singleton beans; beans with special scopes or factories require checking version-specific constraints.
- **Context cache may fragment:** different mock sets and qualifiers can produce different cache keys.
- **Mocks can still return confusing defaults:** stub important methods so tests do not accidentally rely on default `null`, `false`, or empty collections.
- **Resetting does not clean up external systems:** resetting a mock does not delete database data, messages, or files created by other beans.
- **Do not use as a substitute for adapter tests:** HTTP, SQL, broker communication, and serialization need dedicated tests when those are the goal.

## 20. Common Mistakes

- **Using `@MockitoBean` in unit tests without a Spring context:** the annotation does not replace Mockito's `@Mock` in plain unit tests.
- **Forgetting Spring Framework 6.2:** older `spring-test` dependencies do not include this annotation.
- **Accidentally mocking the bean under test:** the test does not run the real implementation and therefore fails to prove the target behavior.
- **Not specifying a qualifier:** Spring selects the wrong bean or cannot determine which bean to replace when multiple implementations exist.
- **Omitting `enforceOverride` when strict replacement is required:** the test creates a new mock even though the expected production bean is missing.
- **Mocking too many collaborators:** the test context becomes complex and most of the application is no longer tested for real.
- **Not resetting or arbitrarily using `NONE`:** stubs and invocation history leak across test methods.
- **Relying on context restarts to clear mock state:** mock resetting has its own mechanism; `@DirtiesContext` is usually far too expensive for that purpose.
- **Using mocks instead of adapters in adapter tests:** the test only checks the mock instead of real communication.
- **Confusing `@MockitoBean` with `@MockitoSpyBean`:** a mock replaces the implementation, whereas a spy continues calling real methods unless stubbed.

## 21. Process for Choosing and Using `@MockitoBean`

When you need to replace a collaborator in a test context, follow this sequence:

1. **Identify the bean under test:** keep this bean real in the context.
2. **Identify the collaborator to replace:** choose dependencies with side effects or outside the test scope.
3. **Check versions:** confirm Spring Framework 6.2 or later and that `spring-test` provides the corresponding API.
4. **Choose how to identify the bean:** use type when there is only one bean; use a qualifier or bean name when multiple implementations exist.
5. **Choose the override strategy:** use the default if a slice may lack the bean; enable `enforceOverride` if replacing an existing bean is mandatory.
6. **Stub necessary behavior:** configure meaningful success and error outcomes.
7. **Invoke behavior through the real bean:** execute requests, call services, or run the application flow the test needs to verify.
8. **Verify the contract:** check meaningful data and interaction counts, avoiding verification of unnecessary internal details.
9. **Manage reset behavior:** keep the `AFTER` default unless there is a specific reason to change it.
10. **Add adapter/integration tests when needed:** mock beans do not prove configuration and communication with external systems.

`@MockitoBean` lets you replace collaborators directly within the `ApplicationContext`, allowing part of a real Spring application to be tested with controlled dependencies. It fits when you need to keep real controllers, services, or configurations while isolating an adapter or external service. Choose the right bean to replace, identify it clearly when multiple implementations exist, and maintain a clear boundary between application logic tests and infrastructure communication tests.

## 22. References

- [Spring Framework Reference — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework Javadoc — `@MockitoBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
