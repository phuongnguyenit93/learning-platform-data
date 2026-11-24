# Distinguishing Spring Framework Annotations from Spring Boot's `@MockBean`/`@SpyBean`

When testing a Spring application, we often need to replace a bean with a Mockito mock or spy to isolate the part under test. Prior to Spring Framework 6.2, many Spring Boot projects used `@MockBean` and `@SpyBean` from Spring Boot Test for this purpose. Starting in Spring Framework 6.2, Spring Test provides `@MockitoBean` and `@MockitoSpyBean` as a framework-level bean override mechanism. Spring Boot 3.4 deprecated `@MockBean` and `@SpyBean` in favor of the new annotations.

The two groups of annotations share similar goals, yet differ in packages, history, and several important behaviors. In particular, `@MockitoBean` can create a mock if no matching bean exists or replace an existing bean; `@MockitoSpyBean` requires an existing bean to wrap with a spy. The new annotations also offer `enforceOverride`, support class-level declarations by type, and can restrict overrides within a context hierarchy.

Understanding these differences helps you pick annotations based on the Spring version in use, avoid importing the wrong package, and prevent a test from silently adding a new mock when the real goal is to replace a real bean.

## 1. Version and Package Context

The annotations are provided by different modules:

| Annotation | Package | Provided By | Version Notes |
|---|---|---|---|
| `@MockBean` | `org.springframework.boot.test.mock.mockito` | Spring Boot Test | Widely used before Spring Boot 3.4; deprecated starting in Boot 3.4 in favor of Spring Framework annotations |
| `@SpyBean` | `org.springframework.boot.test.mock.mockito` | Spring Boot Test | Widely used before Spring Boot 3.4; deprecated starting in Boot 3.4 in favor of Spring Framework annotations |
| `@MockitoBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework Test | Available since Spring Framework 6.2 |
| `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework Test | Available since Spring Framework 6.2 |

Spring Boot 3.4 is based on Spring Framework 6.2, so Boot 3.4 projects can use the new annotations. In the Spring Boot 3.4 line, `@MockBean` and `@SpyBean` are marked deprecated for removal in Spring Boot 4.0. For projects upgraded to Boot 4, use the new Spring Framework annotations instead of the legacy imports.

In standalone Spring Framework projects without Spring Boot, `@MockitoBean` and `@MockitoSpyBean` can still be used as long as the Spring Framework version is 6.2 or later and the test classpath has the required dependencies. `@MockBean` and `@SpyBean` are Spring Boot Test APIs, so they are not an option for a Spring-Framework-only project.

### 1.1. Importing the Right Package

Legacy annotations:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

New annotations:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

The annotation names look similar, yet you cannot swap imports mechanically while ignoring version and semantics. During migration, remove the old imports and add the new ones from `org.springframework.test.context.bean.override.mockito`.

## 2. Spring Framework 6.2 Bean Override Mechanism

Spring Framework 6.2 introduced bean overriding into the Spring TestContext Framework via a shared mechanism. `@MockitoBean` and `@MockitoSpyBean` are two annotations integrating Mockito with that mechanism.

The core idea is that a test declares a bean override on a field or on the test class. Spring processes metadata before creating the `ApplicationContext`, locates matching beans, and applies the corresponding strategy:

- **Replace or create:** creates a Mockito mock and replaces a matching bean; if no bean exists, it can register a new mock. This is the default strategy of `@MockitoBean`.
- **Replace:** replaces only an already-existing matching bean. `@MockitoBean(enforceOverride = true)` requires this behavior.
- **Wrap:** finds an existing bean and wraps it with a Mockito spy. This is the strategy of `@MockitoSpyBean`.

The new annotations are not mere aliases for the legacy Boot annotations. They belong to Spring Test and use Spring Framework's bean override infrastructure, so they work in Spring Framework projects without Spring Boot.

## 3. Comparing `@MockBean` and `@MockitoBean`

### 3.1. Basic Declaration

In older Spring Boot projects, a dependency can be replaced with `@MockBean`:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @MockBean
    private PaymentGateway paymentGateway;
}
```

In Spring Framework 6.2 or Spring Boot 3.4 and later, use `@MockitoBean`:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;
}
```

In both cases, the test receives a Mockito mock for `PaymentGateway`, while `OrderService` remains a bean created and injected by Spring. The test can stub gateway responses and verify interactions.

### 3.2. Replacing an Existing Bean or Creating a New Mock

`@MockitoBean` uses the replace-or-create strategy by default:

- If the context contains a matching bean, that bean is replaced with the mock.
- If the context does not yet contain a matching bean, the mock can be registered as a new bean.

This is useful in test slices, where a dependency might not be in the initial context yet a controller or component still needs it to be constructed.

If you want to ensure the test is replacing a real configured bean, enable `enforceOverride`:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

When no matching bean is found to replace, Spring reports an error during context creation. This is a good choice when the test verifies wiring of an application where `PaymentGateway` must be registered.

Spring Boot's `@MockBean` can also replace an existing bean or add a mock if no matching bean exists, yet it lacks an equivalent `enforceOverride` attribute in the legacy API. Therefore, when migrating from `@MockBean` to `@MockitoBean`, consider whether `enforceOverride = true` should be enabled to make the intent explicit.

### 3.3. Field-Level vs. Class-Level Declaration

The new annotation supports declaring mocks on fields:

```java
@MockitoBean
private PaymentGateway paymentGateway;
```

And declaring by type at the class level:

```java
@MockitoBean(types = {
        PaymentGateway.class,
        InventoryClient.class
})
@SpringBootTest
class OrderServiceTests {
}
```

Class-level declarations fit when a test only needs to replace beans and does not need to inject the mocks into fields for direct stubbing or verification. If you need to interact with a mock inside test methods, field-level declarations are usually easier to read.

With `@MockitoBean`, the `types` attribute is used for class-level declarations; for field-level declarations, the mock type is inferred from the field type. You can specify the bean name when the context has multiple beans of the same type:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

In the legacy `@MockBean` API, authors often used `value` or `classes` for class-level declarations and `name` to identify the bean. When migrating to `@MockitoBean`, update declarations to the new API—especially `types` for class-level type lists.

## 4. Comparing `@SpyBean` and `@MockitoSpyBean`

### 4.1. Spies Preserve Real Behavior

A Mockito spy wraps a real object. Unless a method is stubbed, calls normally execute the real implementation. Tests can use a spy to observe calls or override the behavior of one specific method while keeping the remaining methods intact.

Legacy Boot annotation:

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpringBootTest
class PricingServiceTests {

    @SpyBean
    private PricingService pricingService;
}
```

New Spring Framework annotation:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class PricingServiceTests {

    @MockitoSpyBean
    private PricingService pricingService;
}
```

Spring locates the `PricingService` bean in the context, creates a spy wrapping that bean, and uses the spy as the injected bean. The test can invoke real methods, stub a method, or verify that a method was called.

### 4.2. Important Difference: A Spy Requires an Existing Bean

`@MockitoSpyBean` uses the wrap strategy: it requires a matching existing bean to wrap. If no matching bean exists, Spring cannot create a spy out of thin air and the context fails.

This is a critical point when replacing the legacy `@SpyBean`. Spring Boot's `@SpyBean` API could register a new spy bean when no corresponding bean was found, whereas Spring Framework's `@MockitoSpyBean` is designed to wrap an existing bean. If a test needs a new implementation, register a fake with `@TestConfiguration` or `@TestBean`, and then spy on the created bean if you genuinely need to observe its behavior.

Example:

```java
@SpringBootTest
@Import(PricingTestConfiguration.class)
class PricingServiceTests {

    @MockitoSpyBean
    private PricingService pricingService;
}
```

`PricingTestConfiguration` needs to register `PricingService` before Spring applies the spy. If `PricingService` is already created via component scanning or application configuration, there is no need to add a second bean.

### 4.3. Spying by Type or by Name

If multiple beans share the same type, identify the bean to wrap using a qualifier or name:

```java
@MockitoSpyBean(name = "standardPricingService")
private PricingService pricingService;
```

Or:

```java
@MockitoSpyBean
@Qualifier("standardPricingService")
private PricingService pricingService;
```

`@MockitoSpyBean` also supports class-level declarations by type via `types`:

```java
@MockitoSpyBean(types = PricingService.class)
@SpringBootTest
class PricingServiceTests {
}
```

When only one bean of the type exists, Spring can identify the candidate by type. When multiple beans exist, a qualifier or bean name is required for unique selection.

## 5. Behavior Comparison Table

| Criterion | `@MockBean` (Boot) | `@MockitoBean` (Framework) | `@SpyBean` (Boot) | `@MockitoSpyBean` (Framework) |
|---|---|---|---|---|
| Test double type | Mockito mock | Mockito mock | Mockito spy | Mockito spy |
| Role | Replaces dependency with mock | Replaces or creates mock bean | Spies on bean in context | Wraps existing bean with spy |
| When no matching bean exists | Can add a mock bean | Can create a mock by default | Can register a new spy bean per Boot API | Context fails because no bean exists to wrap |
| Replace only existing bean | No equivalent enforce attribute | `enforceOverride = true` | Spies on found bean; Boot API adds a bean if absent | Requires finding a matching bean to wrap |
| Field-level | Yes | Yes | Yes | Yes |
| Type-level | Yes, via `classes`/`value` | Yes, via `types` | Yes, via `classes`/`value` | Yes, via `types` |
| Candidate selection | Bean name, qualifier, and type | `name`, qualifier, and type | Bean name, qualifier, and type | `name`, qualifier, and type |
| Default mock reset | After each test method by default configuration | `MockReset.AFTER` | After each test method by default configuration | `MockReset.AFTER` |
| Providing module | Spring Boot Test | Spring Framework Test | Spring Boot Test | Spring Framework Test |

The most important differences during migration are spy semantics and the ability to enforce overriding an existing bean for mocks. Do not simply swap annotation names without checking whether the test relies on creating a new bean or wrapping an old one.

## 6. Selecting the Right Bean When Multiple Implementations Exist

Suppose the application has two implementations:

```java
@Component("stripePaymentGateway")
class StripePaymentGateway implements PaymentGateway {
    // Calls Stripe.
}

@Component("bankPaymentGateway")
class BankPaymentGateway implements PaymentGateway {
    // Calls a bank provider.
}
```

If the test only declares:

```java
@MockitoBean
private PaymentGateway paymentGateway;
```

Spring may be unable to identify a single unique candidate. You can specify a qualifier:

```java
@MockitoBean
@Qualifier("stripePaymentGateway")
private PaymentGateway paymentGateway;
```

Or specify the bean name directly:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

When using a field-level annotation, the field name can also be used as a fallback qualifier if no other qualifier is present. For example, a field named `stripePaymentGateway` can help Spring choose the bean of the same name. Even so, when multiple candidates exist, an explicit `@Qualifier` or `name` makes intent clearer and reduces reliance on field naming.

The same rule applies to `@MockitoSpyBean`. A spy must wrap a single existing bean; if multiple candidates exist, Spring needs a qualifier to know which instance to wrap.

## 7. Spies and Safe Method Stubbing

Because a spy calls the real implementation by default, stubbing syntax can trigger side effects during test setup.

With a mock, the common style is:

```java
when(paymentGateway.charge(any(PaymentRequest.class)))
        .thenReturn(new PaymentResult("PAY-1", true));
```

With a spy, the `when(spy.method())` expression can invoke the real method right during stubbing setup. If the real method connects to a database, makes HTTP calls, or throws an exception when data is missing, the test can fail before reaching the main action.

With a spy, it is usually better to use `doReturn(...).when(spy).method(...)`:

```java
doReturn(new BigDecimal("90.00"))
        .when(pricingService)
        .calculateDiscount(any(Order.class));
```

This configures the return value without invoking the real method during stubbing. Other methods on the spy can still execute the real implementation.

Do not spy on an entire service just to stub one dependency. If `PricingService` calls an external gateway, replacing the gateway with a mock usually creates a clearer test boundary. A spy fits when the bean under test itself has real behavior to preserve and one specific method needs to be observed or overridden.

## 8. Resetting Mocks and Spies After Each Test

Spring's Mockito integration annotations support resetting mocks after test methods. By default, `@MockitoBean` and `@MockitoSpyBean` use the `MockReset.AFTER` reset mode. The legacy Boot annotations also support reset configuration and typically reset after each test by default.

This prevents stubbing or invocation history from an earlier test from affecting subsequent tests when the same context is cached and mock beans are reused.

Example:

```java
@MockitoBean(reset = MockReset.AFTER)
private PaymentGateway paymentGateway;
```

In most cases, there is no need to write the `reset` attribute because resetting after each test is already the default. Change the reset mode only when you have a specific reason and understand the impact of retaining stubbing or invocation history.

Resetting a mock does not mean resetting all application state. If a fake bean stores data in a map, list, or mutable field itself, Mockito does not manage that state. Tests must reset the fake separately or create a fresh context when needed.

## 9. Context Hierarchy and `contextName`

Spring Test supports context hierarchies, where a test can have a parent context and child contexts. For example, the parent context holds shared services, while the child context holds web configuration.

The new bean override annotations have a `contextName` attribute to limit the override to a named level in the hierarchy. This is useful when the same bean type appears at multiple levels and the test only wants to replace the bean in one specific context.

Illustrative example:

```java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTests {

    @MockitoBean(contextName = "root")
    private UserDirectory userDirectory;
}
```

`contextName` must match the level name declared in `@ContextConfiguration`. If this attribute is omitted in a hierarchy, the override may be applied across multiple levels according to the bean override infrastructure's rules. Specify the level name when you want precise control over where the bean is replaced.

This is a capability of the new Spring Framework annotations, helping tests express override scope clearly in multi-context configurations. When migrating a hierarchy test from legacy Boot annotations, review which beans actually need to be replaced at each level.

## 10. Usage in Spring Boot Test Slices

`@MockitoBean` can be used with test slices such as `@WebMvcTest` or `@DataJpaTest` to supply dependencies that the slice does not create on its own.

Controller test example:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void delegatesOrderCreationToService() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""{"customerId":"CUS-1"}"""))
                .andExpect(status().isAccepted());

        verify(orderService).createOrder("CUS-1");
    }
}
```

The controller and MVC infrastructure are real components in the slice; `OrderService` is a mock bean so the test verifies that the controller delegates requests to the service. This keeps the test focused on routing, binding, validation, and HTTP responses.

With Spring Boot 3.3 and earlier, use `@MockBean` if the bundled Spring Framework version does not yet include `@MockitoBean`. With Boot 3.4 and later, use the new annotation to avoid deprecated APIs.

## 11. Usage in Non-Boot Spring Framework Projects

A project using only Spring Framework 6.2+ can use `@MockitoBean` and `@MockitoSpyBean` with the Spring TestContext Framework. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.Mockito.verify;

@SpringJUnitConfig(classes = OrderTestConfig.class)
class OrderApplicationServiceTests {

    @Autowired
    private OrderApplicationService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void delegatesPaymentToGateway() {
        orderService.complete("CUS-1");

        verify(paymentGateway).charge(org.mockito.ArgumentMatchers.any());
    }
}

@Configuration
class OrderTestConfig {
    // Declares OrderApplicationService and its other test dependencies.
}
```

`@SpringJUnitConfig` combines JUnit Jupiter with the Spring TestContext Framework. Spring Boot is not required to use Spring Framework's bean override annotations. The project still needs Mockito on the test classpath and needs to provide Spring configuration for the remaining beans.

With Spring Framework prior to 6.2, `@MockitoBean` and `@MockitoSpyBean` do not exist yet. Without Spring Boot, you can declare fakes via a test `@Configuration`, create Mockito mocks manually and register them as beans via test configuration, or use a bean-replacement mechanism compatible with your running version.

## 12. Migrating from `@MockBean`/`@SpyBean` to the New Annotations

### 12.1. Replacing `@MockBean` with `@MockitoBean`

Before:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@MockBean
private PaymentGateway paymentGateway;
```

After:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
private PaymentGateway paymentGateway;
```

If the test requires the bean to exist in the context, use:

```java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
```

If the old test used `@MockBean(name = "stripePaymentGateway")`, migrate to:

```java
@MockitoBean(name = "stripePaymentGateway")
private PaymentGateway paymentGateway;
```

If declared at the class level, move the `classes`/`value` list to the `types` attribute of `@MockitoBean`.

### 12.2. Replacing `@SpyBean` with `@MockitoSpyBean`

Before:

```java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
private PricingService pricingService;
```

After:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@MockitoSpyBean
private PricingService pricingService;
```

Before switching, confirm that the `PricingService` bean is actually registered in the context. `@MockitoSpyBean` requires an existing bean to wrap. If the old test relied on `@SpyBean` adding a bean when no implementation was found, register the implementation via test configuration first before spying on it.

### 12.3. Reviewing Legacy Attributes

Not every attribute of the legacy Boot annotations has the same name or semantics in the new annotations. When migrating, check:

- Whether `classes` or `value` on class-level declarations need to be converted to `types`.
- Whether `name` still identifies the exact bean in the context.
- Whether multiple beans share the same type and require `@Qualifier`.
- Whether the test needs `enforceOverride = true` to verify the real bean exists.
- Whether a spy has an existing bean to wrap or was relying on the legacy annotation's create-if-missing behavior.
- Whether the test has a context hierarchy and needs to specify `contextName`.
- Whether mock/spy reset configuration is preserved as intended.

After switching annotations, run the affected test class and other tests sharing the context to verify wiring and behavior remain correct. In particular, if a test previously created an extra mock or spy by accident, the new annotations may surface configuration errors that were previously masked.

## 13. When to Use Spring Annotations vs. Plain Mockito

`@MockitoBean` and `@MockitoSpyBean` are bean override annotations for tests with a Spring `ApplicationContext`. They do not replace all Mockito annotations.

| Declaration | Creates a Spring Bean Override? | Appropriate Scope |
|---|---|---|
| Mockito `@Mock` | No | Plain Java unit tests with `MockitoExtension` |
| Mockito `@Spy` | No | Unit tests needing to spy on a test-created object |
| Spring `@MockitoBean` | Yes | Replacing or adding a mock bean in a Spring context |
| Spring `@MockitoSpyBean` | Yes | Wrapping an existing bean in a Spring context with a spy |
| Legacy Spring Boot `@MockBean` | Yes | Spring Boot tests in versions prior to switching to Framework annotations |
| Legacy Spring Boot `@SpyBean` | Yes | Spring Boot tests in versions prior to switching to Framework annotations |

Example unit test without a context:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTests {

    @Mock
    private PaymentGateway paymentGateway;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(paymentGateway);
    }
}
```

This example does not need `@MockitoBean`, because Spring does not create an `ApplicationContext`. Using `@Mock` or `mock(...)` is sufficient.

If a test uses `@SpringBootTest`, `@WebMvcTest`, or `@SpringJUnitConfig` and needs to replace a Spring-managed dependency, use `@MockitoBean` or `@MockitoSpyBean`. Do not confuse Mockito's `@Mock` with bean override annotations: a mock on a field does not automatically replace the bean that Spring injects into a service.

## 14. Common Mistakes

### 14.1. Importing the Legacy Annotation from the Boot Package

A new test using Spring Framework 6.2 might accidentally import `org.springframework.boot.test.mock.mockito.MockBean` instead of `org.springframework.test.context.bean.override.mockito.MockitoBean`. If the project upgraded Boot, the IDE may show a deprecation warning or fail to find the old annotation after a major version upgrade. Check package imports.

### 14.2. Using `@MockitoSpyBean` When No Real Bean Exists

A spy must wrap an existing instance. If the context has no matching bean, create the bean first with `@TestConfiguration` or `@TestBean`, or use a mock if real behavior is not needed.

### 14.3. Multiple Beans of the Same Type

If Spring reports that a candidate cannot be determined, use `@Qualifier` or `name` to specify which bean to replace. Check the field name as well because it can participate as a fallback qualifier.

### 14.4. Expecting `@MockitoBean` to Always Fail When a Bean Does Not Exist

By default, `@MockitoBean` can create a new mock bean. If the test needs to verify that a configured production bean exists, enable `enforceOverride = true`.

### 14.5. Stubbing a Spy with `when(...)` Triggers the Real Method

With a spy, `when(spy.method())` can execute the real method during setup. Use `doReturn(...).when(spy).method(...)` when you need to avoid side effects during stubbing.

### 14.6. Expecting Mockito's `@Mock` to Replace a Spring Bean

`@Mock` only creates a mock for the test instance via Mockito. It does not register the mock in the `ApplicationContext`. Use `@MockitoBean` if a Spring-created service must receive that mock.

### 14.7. Using the New Annotations with an Older Spring Framework

`@MockitoBean` and `@MockitoSpyBean` were introduced in Spring Framework 6.2. If the project uses Framework 6.1 or earlier, the imports will not exist. With Spring Boot, check which Boot version manages Spring Framework before switching annotations.

### 14.8. Contexts Having Unexpectedly Different Bean Overrides

Override annotations are part of test configuration metadata and can affect the context cache. If multiple test classes declare different mocks, Spring may create multiple separate contexts. Keep test configuration intentional and avoid adding unnecessary overrides.

## 15. Annotation Selection Process

When you need to replace a dependency in a Spring test, decide in this order:

1. **Identify the Spring Framework version.** If 6.2 or later, you can use `@MockitoBean` and `@MockitoSpyBean`; if older, use the API supported by the current version.
2. **Determine whether a Spring context is needed.** If testing only a single Java class, use Mockito `@Mock`/`@Spy`; if replacing a Spring bean, use a bean override annotation.
3. **Choose mock or spy.** A mock replaces the dependency's entire behavior; a spy keeps the real implementation and enables partial stubbing/verification.
4. **Check whether the bean exists.** `@MockitoBean` can create a new one by default; enable `enforceOverride` if replacing an existing bean is mandatory. `@MockitoSpyBean` needs an existing bean to wrap.
5. **Select the right candidate.** Use type, `name`, or `@Qualifier` when the context has multiple beans of the same type.
6. **Check context scope.** With a context hierarchy, use `contextName` if the override applies to only one level.
7. **Migrate according to semantics.** When switching from `@MockBean` or `@SpyBean`, check class-level declarations, legacy attributes, create-if-missing behavior, and reset lifecycle.

## 16. Complete Migration Example

An older Boot test might be written as:

```java
@SpringBootTest
class PaymentServiceTests {

    @Autowired
    private PaymentService paymentService;

    @MockBean(name = "stripePaymentGateway")
    private PaymentGateway paymentGateway;

    @SpyBean
    private ReceiptFormatter receiptFormatter;
}
```

When migrating to Spring Framework 6.2/Spring Boot 3.4 or later:

```java
@SpringBootTest
class PaymentServiceTests {

    @Autowired
    private PaymentService paymentService;

    @MockitoBean(name = "stripePaymentGateway", enforceOverride = true)
    private PaymentGateway paymentGateway;

    @MockitoSpyBean
    private ReceiptFormatter receiptFormatter;
}
```

In this migration example, `enforceOverride = true` is added to express that `stripePaymentGateway` must be a real bean already present in the configuration. `ReceiptFormatter` must also exist so the spy can wrap it. If the test previously needed to create a new mock because the context lacked a gateway, omit `enforceOverride` or add appropriate configuration per the test objective.

When migrating, preserve assertions and stubbing that verify public behavior. Changing the annotation should only adjust how Spring places the test double into the context; it should not alter the system under test or the test's objective.

`@MockBean` and `@SpyBean` are Spring Boot Test APIs widely used in older projects. Starting in Spring Framework 6.2, `@MockitoBean` and `@MockitoSpyBean` provide bean overriding directly in Spring Test, usable even without Spring Boot. `@MockitoBean` can replace a bean or create a new mock by default, while `enforceOverride` requires replacing an existing bean; `@MockitoSpyBean` requires an existing bean to wrap. When switching annotations, check package imports, versions, candidate selection, class-level declarations, context hierarchies, and especially the difference between creating a new mock versus spying on an already-existing bean.
