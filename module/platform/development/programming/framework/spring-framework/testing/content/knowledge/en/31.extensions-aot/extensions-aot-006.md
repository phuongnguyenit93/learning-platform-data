# Custom Bean Override Annotations with the `BeanOverride` Infrastructure

## 1. Why Override Beans in Tests?

A Spring `ApplicationContext` typically contains real beans created from component scanning, Java configuration, auto-configuration, or external libraries. When testing a service, you sometimes need to replace a dependency with a mock or fake to control inputs and outcomes.

For example, `OrderService` uses `PaymentGateway` to call a payment system. Testing the logic of `OrderService` does not necessarily require sending requests to a real payment gateway. We want to replace the `PaymentGateway` bean in the test context with a mock, then control the mock to return the desired result.

You could create a test bean manually in `@TestConfiguration`, but that approach can lead to repetitive configuration, dealing with bean names or `@Primary`, and sometimes failing to replace the exact bean the application actually injects.

Spring Framework provides the **BeanOverride infrastructure** to declare bean replacements or wrappers directly on a test class using annotations. This infrastructure locates the target bean, applies the override strategy, and injects the replacement bean into test fields when needed.

Typical annotations:

- **`@TestBean`**: replaces a bean with an instance produced by a test factory method.
- **`@MockitoBean`**: replaces a bean with a Mockito mock.
- **`@MockitoSpyBean`**: wraps an existing bean with a Mockito spy to observe or stub part of its behavior.

These annotations make it explicit which dependencies are replaced in the test context. They do not alter the beans of the application running outside tests.

## 2. What Is the `BeanOverride` Infrastructure?

The `BeanOverride` infrastructure was introduced in Spring Framework **6.2**. It is Spring Test's unified mechanism for discovering and applying bean overrides within the TestContext Framework.

Instead of each annotation implementing its own separate pipeline, Spring provides a shared infrastructure with key concepts:

| Component | Responsibility |
|---|---|
| **`@BeanOverride`** | Meta-annotation marking an annotation as a bean override declaration annotation |
| **`BeanOverrideProcessor`** | Reads the annotation on the test class/field and creates the corresponding handler |
| **`BeanOverrideHandler`** | Describes the bean to replace, bean name/type, strategy, and how to create the replacement instance |
| **`BeanOverrideStrategy`** | Specifies replacing an existing bean, replacing or creating a new one, or wrapping an existing bean |
| **`TestContext Framework`** | Discovers overrides and applies them when building the test `ApplicationContext` |

High-level process:

~~~text
Test class with override annotation
          |
          v
Spring TestContext reads metadata
          |
          v
BeanOverrideProcessor
          |
          v
BeanOverrideHandler
          |
          v
Select bean by name / type / qualifier
          |
          v
Apply BeanOverrideStrategy
          |
          v
Create ApplicationContext used in test
          |
          v
Inject override bean into test field
~~~

Bean overriding is part of preparing the test context. When the test runs, controllers or services in the context receive the dependency replaced according to that declaration.

This is a mechanism for Spring Test. There is no need to enable global bean overriding in application configuration just to replace a dependency for tests.

## 3. Three Override Strategies

The `BeanOverride` infrastructure defines three fundamental strategies:

| Strategy | Behavior | Use Case |
|---|---|---|
| **`REPLACE`** | Requires the target bean to already exist and replaces that bean | The test wants to ensure the application configuration actually defines the bean to be replaced |
| **`REPLACE_OR_CREATE`** | Replaces the bean if found; if absent, registers a new bean | Test slices or test contexts that may not load the original bean |
| **`WRAP`** | Takes the existing bean and wraps it with another instance | Selectively observing or altering the behavior of a real bean |

Standard annotations use strategies suited to their purpose:

- **`@TestBean`** and **`@MockitoBean`** use replace-or-create behavior by default. You can require the bean to exist using the **`enforceOverride = true`** attribute.
- **`@MockitoSpyBean`** uses the wrap-existing-bean strategy. It needs a real bean to spy on and does not create a replacement bean if no target is found.

### `REPLACE`

Use when the test must replace a specific bean already configured in the application. If the bean does not exist, context preparation fails rather than silently creating an extra mock.

### `REPLACE_OR_CREATE`

Use when the test may run with a pared-down context, such as an MVC slice that only loads controllers without loading real services. In that case, a mock can be registered if the context does not yet have the corresponding bean.

Consider carefully: if a full-application test is missing a bean that should have been configured, defaulting to creating a new one can mask a configuration error. Use **`enforceOverride = true`** when the presence of the original bean is something the test wants to verify.

### `WRAP`

Use when you need to keep real logic while observing or stubbing some calls. The spy wraps the existing bean; unstubbed methods still execute the real implementation. Therefore, the test must appropriately prepare the real bean's state and dependencies.

## 4. `@TestBean`: Replacing a Bean with a Test Factory Method

**`@TestBean`** allows a test class to supply a replacement instance via a `static` factory method. This is a good choice when you want a hand-written fake or stub without needing Mockito.

For example, the application has an interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(String orderId, BigDecimal amount);
}
~~~

A service depends on that interface:

~~~java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult pay(String orderId, BigDecimal amount) {
        return paymentGateway.charge(orderId, amount);
    }
}
~~~

In the test, declare the replacement bean:

~~~java
import org.springframework.test.context.bean.override.convention.TestBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AppConfig.class)
class OrderServiceTest {

    @TestBean
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return (orderId, amount) ->
                new PaymentResult("TEST-" + orderId, true);
    }

    @Autowired
    OrderService orderService;

    @Test
    void shouldUseTheTestPaymentGateway() {
        PaymentResult result = orderService.pay(
                "O-42",
                new BigDecimal("120.00")
        );

        assertThat(result.approved()).isTrue();
        assertThat(result.transactionId()).isEqualTo("TEST-O-42");
    }
}
~~~

By default, the factory method is looked up by the field name. In the example, the field is named **`paymentGateway`**, so the factory method is named **`paymentGateway()`**. The method must be **`static`**, take no parameters, and return a type compatible with the field type.

If you want to use a different factory method name, you can specify it with the **`methodName`** attribute:

~~~java
@TestBean(methodName = "createFakeGateway")
PaymentGateway paymentGateway;

static PaymentGateway createFakeGateway() {
    return (orderId, amount) ->
            new PaymentResult("FAKE-" + orderId, true);
}
~~~

You can set **`enforceOverride = true`** if the test requires the original bean to exist. Otherwise, the default mechanism can replace a matching bean or create a new bean when the context does not yet have one.

**`@TestBean`** fits deterministic fakes, such as a gateway returning input-based results, a small in-memory fake repository, or a fixed clock. When you need to verify call counts and arguments, Mockito is usually more convenient.

## 5. `@MockitoBean`: Replacing a Bean with a Mockito Mock

**`@MockitoBean`** creates a Mockito mock and registers it as a bean in the test `ApplicationContext`. The annotation is typically placed on a field of the test class:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringJUnitConfig(AppConfig.class)
class OrderServiceMockitoTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void shouldReturnApprovedPayment() {
        given(paymentGateway.charge(
                "O-42",
                new BigDecimal("120.00")
        )).willReturn(new PaymentResult("TX-42", true));

        PaymentResult result = orderService.pay(
                "O-42",
                new BigDecimal("120.00")
        );

        assertThat(result.approved()).isTrue();
        then(paymentGateway).should().charge(
                "O-42",
                new BigDecimal("120.00")
        );
    }
}
~~~

The Mockito mock is injected into the **`paymentGateway`** field and is also used as the bean dependency received by **`OrderService`**. The test controls the outcome via stubbing, then checks interactions with **`then(...).should()`** or **`verify(...)`**.

### Finding the Bean to Replace

Spring normally looks up the bean by the field's type. If multiple beans share the same type, you can identify the bean using:

- **`@Qualifier`** on the field.
- The field name, used as a qualifier hint when disambiguation is needed.
- The **`name`** attribute of **`@MockitoBean`** to specify the bean name explicitly.

Example:

~~~java
@MockitoBean(name = "remotePaymentGateway")
PaymentGateway paymentGateway;
~~~

Or using a qualifier:

~~~java
@MockitoBean
@Qualifier("remotePaymentGateway")
PaymentGateway paymentGateway;
~~~

When multiple candidates share the same type without a clear qualifier or name, Spring may be unable to determine the target bean and fail context initialization.

### Requiring the Original Bean to Exist

By default, **`@MockitoBean`** can replace a bean if found or register a new mock if not found. If the test needs to guarantee that the application configuration already declared the real bean, use:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

When no matching bean exists to replace, the context will fail to start. This is useful for integration tests that need to verify wiring configuration.

### Placing Overrides at the Class Level

**`@MockitoBean`** can also be declared at the type level to define mocks for a test class without needing fields to receive them. The **`types`** attribute lets you specify the bean types to mock:

~~~java
@MockitoBean(types = {
        PaymentGateway.class,
        InventoryGateway.class
})
@SpringJUnitConfig(AppConfig.class)
class OrderWorkflowTest {
}
~~~

When you need to stub or verify a mock, declaring it on a field is usually easier to work with because the test has a direct reference to the mock. Class-level declaration is useful when you only need to replace beans in the context or when using a composed annotation across multiple tests.

## 6. `@MockitoSpyBean`: Wrapping a Real Bean with a Mockito Spy

**`@MockitoSpyBean`** is used when a test wants to keep the real implementation while still being able to observe or stub certain methods.

For example, `TaxCalculator` is a real bean:

~~~java
@Component
public class TaxCalculator {

    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"));
    }
}
~~~

The test wraps the bean with a spy:

~~~java
@SpringJUnitConfig(AppConfig.class)
class InvoiceServiceTest {

    @MockitoSpyBean
    TaxCalculator taxCalculator;

    @Autowired
    InvoiceService invoiceService;

    @Test
    void shouldUseTheRealTaxCalculator() {
        BigDecimal tax = taxCalculator.calculate(
                new BigDecimal("100.00")
        );

        assertThat(tax).isEqualByComparingTo("10.00");
        then(taxCalculator).should().calculate(
                new BigDecimal("100.00")
        );
    }
}
~~~

A spy retains real behavior for unstubbed methods. If you need to stub a method, avoid accidentally invoking the real implementation while configuring Mockito. With spies, **`doReturn(...).when(spy).method(...)`** is usually safer than **`when(spy.method()).thenReturn(...)`**, because the second form invokes the real method before setting up the stub.

Example:

~~~java
doReturn(new BigDecimal("0.00"))
        .when(taxCalculator)
        .calculate(any(BigDecimal.class));
~~~

**`@MockitoSpyBean`** requires the original bean to exist and wraps it. It is not an option for creating a new mock for a dependency absent from the context. The spied bean must conform to the override infrastructure's constraints; in particular, spies are supported for singleton beans.

### When Should You Use a Spy?

Spies are useful when:

- You want to check which arguments a real bean was called with.
- You want to replace one specific branch in a dependency while keeping the rest.
- You want to test an integration flow without replacing the entire implementation.

Spies can couple tests to internal implementations and cause real behavior to run unexpectedly. If you only need to verify a service's contract, mocking an interface dependency or using a fake is usually simpler and more stable.

## 7. Comparing `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean`

| Annotation | Bean Placed into Context | Requires Original Bean? | Use When |
|---|---|---|---|
| **`@TestBean`** | Instance created by a test `static` factory method | Not required by default; can require via `enforceOverride` | Fake/stub with test-controlled behavior |
| **`@MockitoBean`** | Mockito mock | Not required by default; can require via `enforceOverride` | Stubbing and verifying dependencies |
| **`@MockitoSpyBean`** | Mockito spy wrapping a real bean | Yes | Selectively observing or stubbing a real bean |

Do not treat these three annotations as interchangeable ways of writing the same thing:

- Choose **`@TestBean`** when you need a small, deterministic test implementation without a mocking framework.
- Choose **`@MockitoBean`** when you need to control outcomes and verify dependency interactions.
- Choose **`@MockitoSpyBean`** when you have a reason to keep the real implementation and only intervene selectively.

If a test needs to replace a large service with a mock just to test controller logic, **`@MockitoBean`** is a common choice. If a test needs an in-memory fake repository with clear rules, **`@TestBean`** can make the test easier to understand.

## 8. How Is the Target Bean Selected?

The override infrastructure must identify the exact bean before replacing it. Bean selection is usually based on the field type and associated qualifiers.

Some practical rules:

1. If only one bean is compatible with the field type, Spring can select that bean.
2. If multiple beans share the same type, add **`@Qualifier`** or specify the bean name.
3. The field name may be used as a fallback qualifier when resolving candidates.
4. If no bean is found, **`@MockitoBean`** and **`@TestBean`** can create a new bean per the default strategy; **`enforceOverride = true`** requires the original bean to exist.
5. **`@MockitoSpyBean`** must find an existing bean to wrap.

Example where the application has two implementations:

~~~java
@Configuration
class PaymentConfig {

    @Bean
    @Qualifier("card")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
~~~

A test wanting to replace the bank gateway:

~~~java
@MockitoBean
@Qualifier("bank")
PaymentGateway bankGateway;
~~~

If you only declare a field of type **`PaymentGateway`** when the context has two beans and no distinguishing metadata, Spring should not pick randomly. Declare a qualifier so the test's intent is explicit.

Bean overrides are designed for singleton beans. If the target is prototype or another scope, do not assume the replacement mechanism will preserve scope semantics. In particular, **`@MockitoSpyBean`** requires a singleton bean to wrap.

### Beans Created by `FactoryBean`

If the target bean is produced through a **`FactoryBean`**, the override targets the object provided by the `FactoryBean`. For a mock, Spring replaces the product bean with a mock; for a spy, Spring wraps the created product object. Tests normally care about the dependency injected into the application, not the `FactoryBean` implementation itself.

## 9. `BeanOverride` Can Be Extended with Custom Annotations

A key benefit of the `BeanOverride` infrastructure is allowing projects to create their own override annotations instead of relying only on the three built-in ones.

For example, a project might want a **`@StubPaymentGateway`** annotation to replace the gateway with a fake shared across many tests. A custom annotation helps the team standardize how fakes are created and avoid repeating factory methods.

A custom annotation is marked with Spring Test's **`@BeanOverride`** meta-annotation. This meta-annotation links the custom annotation to a **`BeanOverrideProcessor`** implementation. Example:

~~~java
import org.springframework.test.context.bean.override.BeanOverride;

@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
@BeanOverride(StubPaymentGatewayProcessor.class)
public @interface StubPaymentGateway {
}
~~~

**`StubPaymentGatewayProcessor`** is a processor implemented by the project. The processor reads the annotation metadata and creates one or more **`BeanOverrideHandler`** instances describing the override to perform.

Conceptually, the processor needs to determine:

- Which bean type will be replaced.
- Which bean name or qualifier distinguishes the target.
- Which strategy applies: **`REPLACE`**, **`REPLACE_OR_CREATE`**, or **`WRAP`**.
- How to create the replacement instance or wrap the existing bean.
- Which test field should receive the override instance, if the annotation supports field injection.

**`BeanOverrideHandler`** encapsulates the information Spring Test needs to apply the override during context construction. A processor should not mutate singleton beans itself after the test has started; it must describe the override so the infrastructure applies it in the proper lifecycle.

### When Do You Need a Custom Annotation?

Create a custom annotation when the project has a repeated override convention with a clear meaning, such as:

- Replacing an external adapter with the test suite's standard fake.
- Replacing a clock or ID generator with a deterministic implementation.
- Creating a mock with shared default configuration.
- Wrapping a bean to collect events or metrics in tests.

If only one test needs a simple fake, **`@TestBean`** is usually enough. There is no need to build a new processor just to avoid writing a few lines of factory method.

## 10. Scope and Lifecycle of Overrides

Bean overrides are applied within the `ApplicationContext` managed by Spring Test. When the TestContext Framework prepares the context, overrides are discovered and registered before tests use beans.

This has several implications:

- The replacement bean is used by other beans in the context, not just by the test field.
- Overrides belong to the test context configuration; they do not alter production application bean configuration.
- Test classes can share a cached context if their configurations are compatible.
- Mocks and spies have a lifecycle tied to the context; stubbing and invocations must be managed across test methods.
- Replacing a bean in the context does not automatically clean up database data, caches, or systems outside the context.

With **`@MockitoBean`** and **`@MockitoSpyBean`**, Spring Test resets Mockito mocks/spies after each test method by default. You can configure the reset mode via the **`reset`** attribute when needed. Even so, you should not rely on test execution order to retain stubs or invocation history from an earlier method.

When tests run in parallel, a cached context may be shared. Lifecycle-based mock resets do not mean concurrent operations on the same mock become independent. Avoid having multiple test methods concurrently modify stubbing or assert invocations on a shared mock at the same time.

## 11. `BeanOverride` in a Context Hierarchy

Some tests use **`@ContextHierarchy`** to create multiple `ApplicationContext` levels, such as a root context containing services and a child context containing the web layer.

When multiple contexts exist, you must specify which level the override belongs to. An override applied to the wrong context can create a mock in the root while the real bean is fetched from the child, or vice versa.

Modern override annotations support metadata to specify the context hierarchy level in corresponding versions, such as the **`contextName`** attribute. This name must match the context configuration name declared in the hierarchy.

Illustrative example:

~~~java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebLayerTest {

    @MockitoBean(contextName = "root")
    PaymentGateway paymentGateway;
}
~~~

Use **`contextName`** when the test actually has a hierarchy and needs to scope the override to a specific level. If there is only a single `ApplicationContext`, there is no need to add this attribute.

## 12. Relationship with Spring Boot `@MockBean` and `@SpyBean`

Before Spring Framework had the `BeanOverride` infrastructure, Spring Boot provided **`@MockBean`** and **`@SpyBean`** to replace or spy on beans in the test context.

Starting with Spring Framework 6.2, Spring provides **`@MockitoBean`** and **`@MockitoSpyBean`** directly in Spring Test. Spring Boot 3.4 shifted toward these new annotations and deprecated the older **`@MockBean`**/**`@SpyBean`** for migration.

| Old API | New API |
|---|---|
| Spring Boot **`@MockBean`** | Spring Framework **`@MockitoBean`** |
| Spring Boot **`@SpyBean`** | Spring Framework **`@MockitoSpyBean`** |

When upgrading a project:

- Check the Spring Framework version managed by the Spring Boot BOM.
- Switch imports to the Spring Framework package when supported by the version.
- Re-check annotation attributes because the old and new APIs are not necessarily identical in every detail.
- Do not mix old and new annotations on the same bean override without a clear reason.
- Run test slices and test contexts with multiple candidates to verify the right bean is selected.

Example imports for the new annotations:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.bean.override.convention.TestBean;
~~~

If a project is still on Spring Framework 6.1 or an older Spring Boot, the new annotations may not exist yet. You cannot solve that simply by changing imports; you must upgrade dependencies appropriately or keep using the API supported by your current version.

## 13. Combining `BeanOverride` with Test Slices

Test slices load only part of the `ApplicationContext`. This makes `BeanOverride` especially helpful because a controller's dependencies may not be present in the slice.

Spring Boot MVC slice example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void shouldReturnOrder() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

**`@WebMvcTest`** loads the MVC slice and the selected controller. **`@MockitoBean`** provides the service mock so the controller can be instantiated in the context. The mock is used both when the test stubs behavior and when the controller calls the dependency during a request.

For an integration test loading the entire application, you can use **`enforceOverride = true`** to ensure the original bean truly exists in the configuration before replacing it:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;
}
~~~

Do not use mocks to replace the very components the test is supposed to verify. For instance, if the goal is to test real repositories and transactions, do not replace the repository with a mock; replace only dependencies outside the scope under test.

## 14. `BeanOverride` and AOT

AOT (Ahead-of-Time) in Spring prepares part of the application metadata at build time to reduce startup work or support native images. The TestContext Framework also has AOT mechanisms for test contexts in supported Spring versions.

`BeanOverride` is part of customizing the test `ApplicationContext`. Override annotations are read while Spring Test prepares the context; processors and handlers describe which beans to replace before tests execute.

Distinguish three things:

1. **Production application AOT:** prepares metadata and initialization code for the production application context. Test-only bean overrides do not automatically become production beans.
2. **Test context AOT:** prepares the context used in tests. If a test uses override annotations, the context creation mechanism must receive the corresponding metadata and processors.
3. **Running tests in a native image:** beyond creating the context, you must ensure mocking libraries, reflection, proxies, and runtime hints fit the native environment.

With custom override annotations, the processor must be present on the test runtime and compatible with the AOT workflow the project uses. If a processor relies on reflection, classpath scanning, or dynamic proxy creation, check runtime hints requirements and native image limitations for your specific Spring/GraalVM versions.

Do not conclude that because a test using **`@MockitoBean`** runs on the JVM, it will automatically run in a native image. Conversely, do not assume every bean override is AOT-incompatible. Verify support in your Spring version, how the test context is processed by AOT, and the capabilities of the mocking library in the target runtime.

## 15. Common Mistakes When Using `BeanOverride`

| Symptom | Common Cause | Solution |
|---|---|---|
| Context fails to start due to multiple beans of the same type | The bean to override is not clearly specified | Use **`@Qualifier`**, field name, or **`name`** |
| Test passes even though the original bean is missing | **`@MockitoBean`** can create a new bean by default | Use **`enforceOverride`** when the bean must exist |
| **`@MockitoSpyBean`** cannot find bean | Spy requires an existing bean to wrap | Check component scan/configuration and context slice |
| Spy invokes real implementation unexpectedly | Stubbing with **`when(spy.method())`** already called the real method | Use **`doReturn(...).when(spy).method(...)`** when appropriate |
| Later test method sees unexpected mock history | Mock/spy shares a cached context or reset mode differs from expected | Check **`reset`**, do not depend on test order |
| Override targets the wrong context in a hierarchy | Annotation is applied at a context level not containing the target | Specify the appropriate context level |
| Unable to override arbitrary bean scope | `BeanOverride` targets singleton beans | Design test dependencies appropriately or use another mechanism |
| Test slice creates unexpected mock | Context did not load original bean while strategy allows creating new | Use **`enforceOverride`** if wiring needs verification |
| Custom annotation is not discovered | Missing **`@BeanOverride`** or processor misconfigured | Check meta-annotation and processor |
| JVM test passes but native test fails | Reflection/proxy/mock library requires runtime support | Check AOT/native hints and version support |

Another mistake is using `BeanOverride` to mask configuration errors. If a test always creates a new mock when the real bean is missing, the test may stay green even though component scanning or auto-configuration is broken. For tests verifying wiring, require the original bean to exist.

## 16. Choosing the Right Mechanism

| Need | Choice |
|---|---|
| Creating a fake in test code | **`@TestBean`** |
| Mocking a dependency and stubbing/verifying interactions | **`@MockitoBean`** |
| Keeping the real bean while selectively observing or stubbing | **`@MockitoSpyBean`** |
| Adding an independent test bean without replacing an existing one | **`@TestConfiguration`** and **`@Import`** |
| Ensuring the original bean exists in the context | **`enforceOverride = true`** |
| Multiple beans of the same type | **`@Qualifier`** or explicit bean name |
| Shared override convention across a project | Custom annotation with **`@BeanOverride`** and **`BeanOverrideProcessor`** |
| Using multiple contexts in a hierarchy | Specify the appropriate context level |
| Native/AOT testing | Verify support for Spring version, processor, and mocking library |

**`@TestConfiguration`** still has its own place. If you want to add an independent test bean without replacing any bean, test configuration is the right choice. `BeanOverride` is appropriate when the primary intent is to replace or wrap a selected bean.

## 17. Principles for Maintainable Test Design

- Override only dependencies outside the scope the test aims to verify.
- Use interfaces at integration boundaries for easy mocking/faking.
- Use **`enforceOverride = true`** when the presence of the real bean is part of the test condition.
- Provide explicit qualifiers or bean names when multiple implementations exist.
- Use fakes for rule-based behavior and mocks for interactions that need verification.
- Use spies selectively because spies still execute real code.
- Do not rely on stubbing or invocation history from an earlier test method.
- Do not use overrides to hide component scan, profile, or auto-configuration errors.
- For custom processors, keep bean selection and handler creation logic small, deterministic, and easy to test.
- When using AOT/native images, separately verify test contexts and mocking libraries in the target runtime.

The `BeanOverride` infrastructure standardizes how Spring Test replaces beans in an `ApplicationContext`. **`@TestBean`** creates an instance via a factory method, **`@MockitoBean`** replaces a dependency with a mock, and **`@MockitoSpyBean`** wraps a real bean. By choosing the right strategy, target bean, and context scope, tests can isolate dependencies while preserving meaningful Spring configuration for the behavior under test.

