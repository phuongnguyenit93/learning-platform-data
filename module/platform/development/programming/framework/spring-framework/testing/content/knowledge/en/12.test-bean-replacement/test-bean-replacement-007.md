# Requiring the Bean to Exist and Avoiding Unexpected Mock Creation

When replacing a Spring bean with a Mockito mock in a test, sometimes what matters is not only having a mock to inject into the object under test. The test also needs to verify that **the bean actually exists in the ApplicationContext before being replaced**. If Spring automatically creates a mock when no bean is found, the test can pass even when the application configuration is missing a bean, a profile is not enabled, or component scanning omits a component.

Spring Framework 6.2 provides the **@MockitoBean** annotation with the **enforceOverride** attribute to control this behavior. By default, @MockitoBean can replace an existing bean or create a new mock if no matching bean exists. When **enforceOverride = true** is set, Spring only replaces an already-registered bean; if no bean to replace is found, preparing the ApplicationContext fails.

This is a useful option for integration tests that need to verify application wiring. For a test slice such as @WebMvcTest, where services are intentionally excluded from the context, creating a new mock may be exactly what the test needs. Therefore, before enabling enforceOverride, determine whether the bean belongs to the scope of the context under test.

## 1. Why Can a Mock Be Created Even When the Real Bean Does Not Exist?

Suppose an application has a CheckoutService that depends on PaymentGateway:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

~~~java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    CheckoutResult checkout(CheckoutCommand command) {
        PaymentResult payment = paymentGateway.charge(
            new PaymentRequest(command.orderId(), command.amount())
        );
        return payment.accepted()
            ? CheckoutResult.completed(command.orderId())
            : CheckoutResult.rejected(command.orderId());
    }
}
~~~

In the real application, PaymentGateway may be registered with @Component or a @Bean method:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

When writing a test, we want to replace PaymentGateway with a Mockito mock to control payment outcomes:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        CheckoutResult result =
            checkoutService.checkout(validCommand());

        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

With the configuration above, Spring finds the PaymentGateway bean in the context and replaces it with a mock. CheckoutService is still created by Spring and receives the mock via constructor injection.

However, if PaymentConfiguration is accidentally omitted from the configuration list, or the PaymentGateway bean is not registered due to a profile or configuration condition, default @MockitoBean can still create a new mock. The context can then still initialize and CheckoutService still receives a dependency. The test can pass even though the application configuration is missing the bean we intended to check.

This is the key difference between two questions:

- “I need a mock PaymentGateway to test CheckoutService.”
- “I need to replace the exact PaymentGateway bean registered by the application.”

If the goal is the second question, require the bean to exist.

## 2. Using enforceOverride = true

You can enable strict bean-replacement mode with the enforceOverride attribute:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        // Arrange
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        // Act
        CheckoutResult result =
            checkoutService.checkout(validCommand());

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

When the context is prepared, Spring must find a bean matching PaymentGateway to replace. If no bean is found, the test context fails to initialize. Test methods will not run.

This behavior helps catch several errors early:

- The configuration containing the PaymentGateway bean is not imported or scanned.
- The required profile has not been activated.
- A @Conditional condition is not satisfied so the bean is not created.
- The bean name or qualifier in the test points to a different bean.
- The bean type declared in the test does not match the actual bean.
- The test uses a context with a narrower scope than the author assumed.

The exact error message may vary by Spring version and context configuration. What to watch for is that the error occurs during creation of the test ApplicationContext because there is no matching bean to replace.

## 3. Understanding the Two Bean-Replacement Strategies of @MockitoBean

In Spring Framework 6.2, Spring Test's bean override mechanism has these primary strategies:

| Strategy | Meaning | Behavior When Bean Is Not Found |
|---|---|---|
| REPLACE_OR_CREATE | Replace matching bean or create a new mock bean | Creates a new mock |
| REPLACE | Replace only an existing bean | Fails when bean is not found |
| WRAP | Wrap an existing bean with a spy | Fails when no matching bean is found |

@MockitoBean uses the REPLACE_OR_CREATE strategy by default. The enforceOverride attribute switches the behavior to REPLACE:

~~~java
// Default: replace if present, create a mock if absent.
@MockitoBean
PaymentGateway paymentGateway;

// Only replace an existing bean; if missing, context initialization fails.
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

The difference lies in when Spring processes the bean override—before test methods execute. enforceOverride is not a Mockito assertion running after calling the service. It is a precondition during ApplicationContext preparation.

### 3.1. Why Is the Default Still Useful?

A missing bean is not always an error. In a test slice, Spring intentionally loads only part of the application. For example, @WebMvcTest typically creates controllers and required MVC components, while business services may sit outside the slice. The test needs a mock service so the controller can be injected and handle requests.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenServiceFindsIt() throws Exception {
        given(orderService.findById("order-42"))
            .willReturn(new OrderResponse("order-42"));

        mockMvc.perform(get("/orders/order-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-42"));
    }
}
~~~

In this example, OrderService does not need to be a bean in the MVC slice. Creating a new mock is intentional to isolate the controller. If enforceOverride = true were set, the context could fail because the service is outside the slice scope.

Therefore, enable enforceOverride only when the test genuinely requires the original bean to be present in the context. Do not apply this attribute indiscriminately to every mock.

## 4. Selecting the Right Bean When Multiple Candidates Exist

Spring can have multiple beans implementing the same interface. For example, an application registers gateways for multiple providers:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("cardGateway")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("walletGateway")
    PaymentGateway walletGateway() {
        return new WalletPaymentGateway();
    }
}
~~~

If the test declares only a PaymentGateway field without specifying the candidate, Spring may fail to determine which bean to replace. Use @Qualifier to specify it precisely:

~~~java
@SpringJUnitConfig({
    PaymentConfiguration.class,
    CheckoutService.class
})
class CardCheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("cardGateway")
    private PaymentGateway paymentGateway;

    // ...
}
~~~

You can use the name attribute to specify the bean name:

~~~java
@MockitoBean(
    name = "cardGateway",
    enforceOverride = true
)
private PaymentGateway paymentGateway;
~~~

When selecting a bean, Spring uses data type and qualifier metadata. For field-level @MockitoBean, the field name can also be used as a fallback qualifier when disambiguating multiple candidates. Still, @Qualifier or name expresses intent more clearly and is less sensitive to field renames.

If multiple beans share the same type, check:

- Which bean is marked @Primary?
- Is there a @Qualifier matching the desired bean?
- Is the field name accidentally being used as a fallback qualifier?
- Is the test loading the right configuration that registers those beans?

Do not rename a field just to make the context start without understanding which bean is being selected. A test replacing the wrong gateway may pass while no longer protecting the right wiring.

## 5. Example: Detecting a Bean Missing Due to Configuration

Suppose the gateway bean is registered only in the production profile:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

The test activates the test profile:

~~~java
@SpringJUnitConfig({
    ProductionPaymentConfiguration.class,
    CheckoutService.class
})
@ActiveProfiles("test")
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    // ...
}
~~~

In this case, the production profile is not active so PaymentGateway is not registered. With enforceOverride = true, Spring cannot replace the bean and context initialization fails. This exposes the mismatch between the active test configuration and the bean configuration the test expects.

If the test's goal is to verify CheckoutService with a simulated gateway under the test profile, register an appropriate bean for the test profile or use an explicit test configuration:

~~~java
@TestConfiguration
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
~~~

When the test imports TestPaymentConfiguration, the bean exists and can be replaced by a Mockito mock with enforceOverride = true. This keeps two concerns distinct: the test configuration supplies the base bean, while @MockitoBean replaces that bean to control interactions.

If the test only needs a mock as a service dependency and is not meant to verify real bean configuration, default @MockitoBean can be used. What matters is defining clearly what scope the test protects.

## 6. Distinguishing @MockitoBean from @MockitoSpyBean

@MockitoBean replaces a bean with a Mockito mock. A mock does not execute real logic unless stubbed or configured with a corresponding answer.

@MockitoSpyBean creates a spy on an existing bean, preserving the bean's real behavior while allowing observation or stubbing of selected methods. A spy uses the WRAP strategy, so Spring must find the original bean to wrap.

~~~java
@SpringJUnitConfig(InventoryConfiguration.class)
class InventoryServiceTest {

    @MockitoSpyBean
    private InventoryService inventoryService;

    @Test
    void tracksInvocationWhileUsingRealBehavior() {
        inventoryService.recalculate("SKU-10");

        then(inventoryService).should()
            .recalculate("SKU-10");
    }
}
~~~

The example assumes InventoryConfiguration registers an InventoryService bean. If the bean does not exist, @MockitoSpyBean does not create a replacement instance automatically. If multiple matching beans exist, specify the bean via qualifier or name.

With a spy, the real method can execute even during stubbing if you use `when(spy.method()).thenReturn(...)`. To avoid invoking the real method while configuring stubs, Mockito generally recommends `doReturn(...).when(spy).method()`.

~~~java
doReturn(10).when(inventoryService).availableQuantity("SKU-10");
~~~

Key differences:

| Annotation | Behavior | Can Create Bean When Absent? | Goal |
|---|---|---|---|
| @MockitoBean | Replaces with mock | Yes, by default | Isolate dependency and control outcomes |
| @MockitoBean(enforceOverride = true) | Only replaces existing bean | No | Ensure the bean is registered before replacing |
| @MockitoSpyBean | Wraps real bean with spy | No | Keep real logic and observe/stub selectively |

## 7. Using enforceOverride with Test Configurations and Test Slices

Choosing the mode depends on context scope:

| Test Type | Does Mocked Bean Belong to Context? | Commonly Appropriate Choice |
|---|---|---|
| @SpringBootTest testing full application config | Usually yes, if the application must register that bean | enforceOverride = true when protecting wiring |
| @SpringJUnitConfig with explicit bean config | Yes if the config declares the bean | enforceOverride = true |
| @WebMvcTest controller | Services are usually excluded from the slice | Default @MockitoBean to create collaborating mocks |
| @DataJpaTest repository | Business services usually do not belong to the slice | Do not require overriding out-of-slice services |
| Custom test slice | Depends on imported components | Enable strict override only for beans inside the slice |

### 7.1. Full Application Context

When testing application configuration, the goal often includes confirming that required beans are registered. Example:

~~~java
@SpringBootTest
class CheckoutApplicationTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void wiresCheckoutServiceWithConfiguredGateway() {
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        CheckoutResult result =
            checkoutService.checkout(validCommand());

        assertEquals(CheckoutStatus.COMPLETED, result.status());
    }
}
~~~

If the application configuration does not create PaymentGateway, the test fails during context preparation. Thus, the test confirms that the bean required by the service actually belongs to the application configuration.

### 7.2. Test Slice

With a test slice, certain beans are intentionally excluded to bound scope. Example:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CheckoutService checkoutService;

    // ...
}
~~~

CheckoutService is outside the MVC slice, so creating a new mock makes sense. If the goal is to verify that CheckoutService is configured across the whole application, use a test with an appropriate context scope.

## 8. Cases Where enforceOverride Helps Detect Bugs

### 8.1. Missing Bean Due to Component Scanning

A package excluded from component scanning or a changed scan configuration can prevent a bean from being registered. A default mock can hide this problem. enforceOverride makes the context fail immediately when the bean is not found.

### 8.2. Missing Configuration Due to Profiles

A bean is annotated with @Profile while the test activates a different profile. If the bean must exist in the profile under test, strict override catches that the profile fails to supply the bean.

### 8.3. Unsatisfied @Conditional Condition

A bean may be created only when a property is enabled or a class is present. If the condition is not met, default @MockitoBean may add a new mock. enforceOverride confirms the bean was actually created under that condition.

### 8.4. Selecting the Wrong Qualifier

If a qualifier points to a nonexistent bean, strict override prevents the test from initializing. This catches naming or qualifier mistakes instead of creating a mock disconnected from the intended bean.

### 8.5. Test Loading an Incomplete Context

A test may import only a service class and forget to import the configuration containing its dependency. If the goal is to verify wiring, strict override helps detect the incomplete context.

## 9. Limitations and Bean Selection Rules

Spring Test's bean override mechanism has several limitations to know:

- The mock/spy mechanism is designed for singleton beans. Beans with other scopes may not be overridden this way.
- If multiple beans share the same type, clearly identify the target bean via qualifier, name, or bean selection metadata.
- @MockitoSpyBean requires an existing bean to wrap; it does not create a bean when missing.
- Default @MockitoBean can create a new bean; this can alter components in the test context compared to the original application configuration.
- Overriding occurs when the context is prepared, so missing-bean errors usually appear before any test method runs.

When testing a request- or session-scoped bean, examine how the test creates and manages scope. Do not assume @MockitoBean can replace every bean regardless of scope.

If the application has a FactoryBean, proxies, or multiple proxy layers, identify which product bean the test replaces and what type is exposed in the context. For complex bean selection, inspect the actual bean definitions and context in the test configuration rather than relying solely on implementation class names.

## 10. Relationship with Spring Boot's @MockBean

Prior to Spring Framework 6.2, many Spring Boot projects used @MockBean from spring-boot-test to register or replace Mockito mocks in the ApplicationContext.

Spring Framework 6.2 added @MockitoBean and @MockitoSpyBean in the spring-test module. Starting with Spring Boot 3.4, Spring Boot's @MockBean and @SpyBean are marked deprecated in favor of the Spring Framework bean override annotations.

Points to keep in mind when migrating:

- @MockitoBean is a Spring Framework annotation, imported from org.springframework.test.context.bean.override.mockito.MockitoBean.
- The older @MockBean belongs to Spring Boot test and has no equivalent enforceOverride attribute in the legacy API.
- When using Spring Framework 6.2 or later, you can use enforceOverride to require the bean to exist before replacing it.
- For older Spring projects without @MockitoBean, continue using the mock mechanism compatible with the current version or upgrade the framework per project plans.

Do not mix both annotations for the same bean in a single test context. Choose one consistent bean override mechanism so two tools do not simultaneously try to register or replace the same bean.

## 11. Mock Reset Configuration and Context Lifecycle

@MockitoBean typically resets mocks after each test method according to Spring Test's default policy. Resetting clears mock stubbing and invocation state so test methods do not reuse interactions from previous tests.

Resetting a mock and closing an ApplicationContext are two distinct actions:

- Resetting a mock keeps the context and mock bean intact, cleaning only Mockito state.
- @DirtiesContext removes the context from the cache and closes it, after which Spring can recreate all beans.

If a test only needs a mock to have no lingering invocations or stubbing from a prior method, the default reset mechanism is usually sufficient. There is no need to mark the context dirty merely because a mock was invoked.

Conversely, if a test modifies another bean in the context or alters context structure, resetting mocks will not solve that issue. Choose the mechanism suited to the kind of state being mutated.

## 12. Common Mistakes and How to Handle Them

### 12.1. Enabling enforceOverride in a Test Slice

A slice context may not contain the service the test wants to mock. When enforceOverride is enabled, Spring reports that the bean cannot be found. Determine whether the service should be imported into the slice or is intentionally out of scope. If it is a dependency of a controller that needs to be mocked, use default @MockitoBean.

### 12.2. Forgetting to Register the Configuration Containing the Bean

In tests using @SpringJUnitConfig or @ContextConfiguration, ensure the configuration class creating the bean is loaded. If the configuration is missing, strict override fails the context. Check class lists, component scanning, and @Import.

### 12.3. Wrong Qualifier or Bean Name

If multiple implementations exist, use @Qualifier or name to select the right bean. Check spelling, the bean name produced by `@Bean` methods, and the qualifier declared on the bean.

### 12.4. Bean Disabled by Profile

Check @ActiveProfiles and @Profile conditions on configurations. If the bean exists only under another profile, determine which profile the test is meant to verify and load the matching configuration.

### 12.5. Bean Disabled by Property

With @ConditionalOnProperty or similar conditions, check values in the Environment. If the bean must exist in the test scenario, supply the right property via test configuration and enable enforceOverride.

### 12.6. Confusing a Newly Created Mock with a Replaced Bean

A test context initializing successfully does not by itself prove the original bean existed. If the goal is to verify replacing a registered bean, use enforceOverride = true. If the goal is merely to create a mock dependency for a slice, the default is appropriate.

### 12.7. Replacing the Wrong One Among Multiple Beans

When multiple beans share a type, do not rely on implicit selection. Specify a qualifier or name and use strict override if the bean must exist.

### 12.8. Expecting a Test Method to Catch Context Initialization Errors

A bean-not-found error occurs while Spring prepares the ApplicationContext, before the test method begins. You cannot use assertThrows inside a test method to catch this bootstrap failure. Read the root cause in the context loading error and inspect the bean configuration.

## 13. Practice Pattern: Verifying the Bean Is Registered Before Mocking

A complete example can use a small configuration to show the original bean clearly:

~~~java
@Configuration
class CheckoutTestConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
~~~

The test replaces the exact registered bean:

~~~java
@SpringJUnitConfig(CheckoutTestConfiguration.class)
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenGatewayAcceptsPayment() {
        // Arrange
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted());

        // Act
        CheckoutResult result =
            checkoutService.checkout(validCommand());

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
        then(paymentGateway).should()
            .charge(any(PaymentRequest.class));
    }
}
~~~

In this example, the configuration declares PaymentGateway and CheckoutService. Spring builds the context, locates the PaymentGateway bean, and replaces it with a mock. CheckoutService receives the mock when created. If you remove the `@Bean paymentGateway()` method from the configuration, the context cannot initialize because enforceOverride requires that bean to exist.

By contrast, if the test only needs a mock for a dependency that the context does not register:

~~~java
@SpringJUnitConfig(CheckoutService.class)
class CheckoutServiceUnitContextTest {

    @MockitoBean
    private PaymentGateway paymentGateway;

    // A mock is created if the context does not yet have PaymentGateway.
}
~~~

The second example illustrates create-or-replace. It fits when the test proactively creates a mock to satisfy the service's dependency. The specific configuration must ensure CheckoutService is registered and can be constructed with that dependency.

## 14. Decision Process for Enabling enforceOverride

Before adding @MockitoBean, answer these questions:

1. Should the mocked bean be registered by the application in this context?
2. Is the test verifying application wiring or merely isolating one component?
3. Is the context a full application context or a test slice?
4. Are there multiple beans of the same type requiring selection via qualifier or name?
5. Is the bean conditioned by a profile or property?
6. If the bean does not exist, is that a bug to catch or a normal state of the slice?

You can apply this rule of thumb:

| Goal | Declaration |
|---|---|
| Replace an application bean and require it to be present | @MockitoBean(enforceOverride = true) |
| Create a new mock for a dependency outside the slice | @MockitoBean |
| Replace one specific implementation among multiple beans | @MockitoBean(enforceOverride = true) combined with @Qualifier or name |
| Observe real behavior of a registered bean | @MockitoSpyBean |
| Verify whether a bean is created under profile/conditional config | Use a context containing that config and strict override when replacing the bean |

## Conclusion

By default, @MockitoBean can replace an existing bean or create a new mock if no matching bean is found. Set enforceOverride = true to require Spring to replace only an already-registered bean and fail immediately during context preparation if the bean is missing. This helps tests catch errors in component scanning, profiles, conditional configurations, and qualifiers. For test slices that intentionally exclude services from the context, creating a new mock is often part of the test design; use strict override when the existence of the bean in that very context is what needs to be protected.
