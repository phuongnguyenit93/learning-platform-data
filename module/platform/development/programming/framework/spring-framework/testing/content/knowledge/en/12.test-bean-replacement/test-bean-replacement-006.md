# REPLACE, REPLACE_OR_CREATE, and WRAP

In Spring testing, we often need to replace a real bean with a mock, fake, or observable wrapper. Replacing a bean helps control external systems, simulate errors, and focus on the behavior of the component under test. However, the replacement strategy should reflect the exact goal: some tests must verify that a production bean actually exists before replacing it; some tests need to add a fake bean when a slice configuration does not load that bean; and some tests need to keep the real implementation while wrapping it in a spy to observe interactions.

The Spring TestContext Framework provides three bean override strategies:

- **REPLACE:** replaces an existing bean. If no matching bean is found, context creation fails.
- **REPLACE_OR_CREATE:** replaces the bean if it already exists; if not, registers a new replacement bean.
- **WRAP:** takes an existing bean and wraps that instance, typically with a Mockito spy. If a single matching bean cannot be found, context creation fails.

These three strategies differ in more than just syntax. They express three different assumptions about the application configuration and the kind of evidence the test wants. Choosing the wrong strategy can let a test pass even when the production configuration is missing a bean, or cause a test to accidentally execute real logic and call external systems.

## 1. Bean Overrides in Spring TestContext

Bean overriding is a test-only mechanism for altering a bean inside an `ApplicationContext`. Spring builds the context from test configuration, identifies the target bean by type and qualifier or name, and applies the requested strategy.

In Spring Framework 6.2, this mechanism is provided in the package:

~~~java
org.springframework.test.context.bean.override
~~~

Common built-in annotations include:

- **`@MockitoBean`:** registers a Mockito mock as a bean in the `ApplicationContext`.
- **`@MockitoSpyBean`:** wraps an existing bean with a Mockito spy.
- **`@TestBean`:** replaces or supplies a bean using a test-declared factory method.

These annotations share the common bean override infrastructure. Each annotation selects a strategy aligned with its semantics. `@MockitoBean` uses `REPLACE_OR_CREATE` by default; you can require the bean to exist via `enforceOverride = true`, corresponding to `REPLACE`. `@MockitoSpyBean` uses `WRAP` because a spy needs a real instance to wrap.

Bean overriding is applied inside the test's `ApplicationContext`. It does not edit production configuration, alter beans in an application running in another JVM, or serve as a dynamic bean-replacement mechanism for production runtime.

### 1.1. Bean Override Differs from `@Primary` and `@Profile`

These three mechanisms have different purposes:

| Mechanism | Purpose |
| --- | --- |
| Bean override | Replace or wrap a bean in the test's `ApplicationContext` |
| `@Primary` | Prefer one bean when multiple candidates exist for a single-valued dependency |
| `@Profile` | Select a group of beans based on active profiles |

If a test uses `@Primary` to add a new mock, the old production bean can still exist in the context. In that case, the test might not actually replace the collaborator used by the SUT. Bean overrides target the bean to be replaced following candidate resolution rules.

### 1.2. Determining Which Bean Will Be Overridden

Spring needs to identify a matching bean candidate. Resolution typically relies on:

- The field type or the type declared in the bean override.
- Qualifier metadata such as `@Qualifier` or a custom qualifier.
- A specified bean name when selecting by name.
- The field name as supplementary resolution information in matching field-level declarations.

If multiple beans share the same type, declare an explicit qualifier or bean name. Do not rely on component scan order or `@Bean` method order to pick an implementation.

Example:

~~~java
@Bean
@Qualifier("stripe")
PaymentGateway stripeGateway() {
    return new StripePaymentGateway();
}

@Bean
@Qualifier("adyen")
PaymentGateway adyenGateway() {
    return new AdyenPaymentGateway();
}
~~~

A test wanting to replace the Stripe gateway needs to specify the `stripe` qualifier. If it declares a mock solely by the `PaymentGateway` type when the context has two candidates, Spring cannot reliably infer the test's intent.

## 2. REPLACE: Only Replace an Existing Bean

`REPLACE` means the test requires Spring to find a matching bean in the context configuration and replace it with the test bean. If no matching candidate exists, the context must fail.

This strategy fits when the existence of the production bean is part of the test condition. For example:

- The application is required to have a `PaymentGateway`.
- A service requires a configured repository adapter.
- The test wants to replace an integration bean while still confirming that the application configuration registers that bean.
- The test needs to catch component scan, profile, or configuration class errors that cause the bean to disappear.

With `@MockitoBean` in Spring Framework 6.2, you can use:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

`enforceOverride = true` requires the corresponding bean to exist before replacing it. If the production configuration does not register the Stripe gateway or the qualifier does not match, Spring does not silently create a new mock to let the test proceed.

### 2.1. Why Is REPLACE Useful?

Suppose production has:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("stripe")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
~~~

`CheckoutService` receives the gateway:

~~~java
@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("stripe") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    PaymentResult pay(PaymentRequest request) {
        return gateway.charge(request);
    }
}
~~~

If the test wants to replace the exact production gateway, `REPLACE` checks two things at once:

1. The context configuration contains a bean with the `stripe` qualifier.
2. The test replaces that exact bean with a mock to control responses.

The test can verify service behavior:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void returns_approved_result_when_gateway_approves_payment() {
        PaymentRequest request = PaymentRequestFixtures.validRequest();
        PaymentResult approved = PaymentResult.approved("PAY-101");

        when(stripeGateway.charge(request)).thenReturn(approved);

        PaymentResult actual = checkoutService.pay(request);

        assertThat(actual).isEqualTo(approved);
        verify(stripeGateway).charge(request);
    }
}
~~~

The test uses a mock gateway while the real `CheckoutService` is created by Spring. Because the bean override requires the candidate to exist, the test also protects the application's dependency configuration.

### 2.2. When Will REPLACE Cause a Test to Fail?

For example, the test declares:

~~~java
@MockitoBean(enforceOverride = true)
@Qualifier("stripe")
PaymentGateway stripeGateway;
~~~

but the context only registers a bean with the `adyen` qualifier. The test will be unable to replace the desired bean. This is the right outcome if the test requires production to have a Stripe gateway.

Common causes:

- The bean is missing because component scanning does not cover the package.
- The configuration class was not imported.
- The active profile does not register the bean.
- The qualifier on the bean or injection point is wrong.
- The test loads the wrong application context.
- The bean name or declared type does not match.

Do not remove `enforceOverride` just to make a test green if the production bean is required to exist. First check whether the test is using the right configuration under test.

## 3. REPLACE_OR_CREATE: Replace If Present, Create If Absent

`REPLACE_OR_CREATE` means:

- If a matching bean is found, Spring replaces it.
- If no matching bean is found, Spring registers a new test bean.

This is the default strategy of `@MockitoBean` in Spring Framework 6.2:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;
}
~~~

If the context already has a `stripe` bean, it is replaced with a mock. If no matching bean exists, a new mock bean can be registered according to the override declaration.

### 3.1. When Is REPLACE_OR_CREATE Appropriate?

This strategy is useful when the test needs a mock collaborator without aiming to verify that the production bean is already registered:

- A test slice loads only the controller and not the real service.
- A minimal test context only needs a dependency to construct the SUT.
- An integration point is optional in the current configuration.
- The test verifies a component consuming an interface, not whether a specific adapter is configured.
- The test wants to supply a mock for a dependency missing from a minimal context.

For example, a controller test can use a mock service to verify the HTTP contract:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
~~~

In a web slice, `CheckoutService` is typically not created as in a full application context. The test needs a mock so the controller can be injected and responses can be controlled. `REPLACE_OR_CREATE` matches that intent.

### 3.2. Risk: Masking a Missing Production Bean

Suppose a service requires a Stripe gateway, yet the production configuration accidentally fails to register that bean. If the test uses `REPLACE_OR_CREATE`, Spring can create a new mock and the `ApplicationContext` still starts.

The test may pass even though the real application will fail to start with the same configuration.

This is an important reason to choose `REPLACE` when the existence of the production bean must be safeguarded. `REPLACE_OR_CREATE` is appropriate when creating a new test bean is an intentional part of the test.

### 3.3. Using `enforceOverride` to Switch to REPLACE

With `@MockitoBean`:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

`enforceOverride = true` requires the bean to already exist. This is the right choice when the test needs to replace an already-configured production integration bean.

Do not use `enforceOverride` merely out of a desire to make tests stricter. If a test uses `@WebMvcTest` and the service is not part of the loaded slice, requiring the production bean to exist goes against the purpose of a slice test. In that case, `REPLACE_OR_CREATE` is usually the right choice.

## 4. WRAP: Wrapping a Real Bean with a Spy

`WRAP` does not create an entirely new replacement implementation. Spring locates the existing bean, obtains its instance, and wraps it with a Mockito spy. The spy preserves real behavior by default while letting the test observe calls or stub selected methods.

In Spring Framework 6.2, `@MockitoSpyBean` uses the `WRAP` strategy:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

This strategy requires exactly one matching bean to wrap. If there is no bean, or if there are multiple candidates that cannot be unambiguously resolved, Spring cannot perform `WRAP`.

### 4.1. When Is WRAP Useful?

A spy fits when the test wants to keep the real implementation and observe interactions:

- Verify that a service calls a real adapter with the right command.
- Check whether a real collaborator was invoked.
- Keep most of a bean's logic while overriding one specific method to simulate a hard-to-reach scenario.
- Test an integration layer while controlling one response branch.

Example:

~~~java
@SpringBootTest
class CheckoutServiceSpyTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void delegates_payment_to_real_gateway() {
        PaymentRequest request = PaymentRequestFixtures.validRequest();

        checkoutService.pay(request);

        verify(stripeGateway).charge(request);
    }
}
~~~

In this example, the real bean's `charge` method executes. That could invoke an HTTP client or a real payment system if the adapter is configured as in production. Therefore, a spy does not automatically make a test safe from external side effects.

If the goal is solely to verify that `CheckoutService` handles a payment result, using a mock with `REPLACE` is usually more appropriate. If the goal is to verify that the adapter makes the right HTTP call, use a mock server or sandbox environment to control the partner side.

### 4.2. Partially Stubbing a Spy

A spy invokes the real implementation by default. If a method can cause side effects or needs a fixed response, stub that method:

~~~java
doReturn(PaymentResult.approved("PAY-TEST"))
    .when(stripeGateway)
    .charge(any(PaymentRequest.class));
~~~

With a spy, `doReturn(...).when(spy)...` is generally safer than `when(spy.method()).thenReturn(...)` because the latter can call the real method while setting up the stub.

Stub only what needs to be controlled. Unstubbed methods still execute real logic. Be clear about what the test proves when combining real code and overridden behavior.

### 4.3. WRAP Requires an Existing Singleton Bean

Bean overriding in Spring TestContext focuses on singleton beans. `WRAP` requires an existing instance to wrap. If no candidate exists, multiple candidates cannot be resolved, or the bean has an unsuitable scope, the context may fail.

If you need to observe a collaborator created with request or prototype scope, reconsider the test boundary. You can test the factory/scope in a separate test or use an adapter with a suitable lifecycle, rather than trying to wrap a bean that does not satisfy `WRAP` requirements.

## 5. Comparing the Three Strategies

| Characteristic | REPLACE | REPLACE_OR_CREATE | WRAP |
| --- | --- | --- | --- |
| Matching bean already exists | Replaces that bean | Replaces that bean | Wraps that instance |
| No matching bean exists | Error during context creation | Creates a new test bean | Error during context creation |
| Multiple candidates | Must resolve to one exact candidate | Must resolve to the candidate to replace; fails if unresolvable | Must identify one exact instance to wrap |
| Default behavior of production bean | Replaced | Replaced if present | Continues running through the spy |
| Common Spring API | `@MockitoBean(enforceOverride = true)` | Default `@MockitoBean` | `@MockitoSpyBean` |
| Typical goal | Protect existing bean configuration, replace collaborator | Supply a mock to the context, even if the bean is not yet registered | Observe or stub a real bean |

You can remember their meanings with three sentences:

- **REPLACE:** “This bean must exist; replace it.”
- **REPLACE_OR_CREATE:** “If the bean exists, replace it; if not, create a test bean.”
- **WRAP:** “This bean must exist; keep the real instance and wrap it.”

## 6. Choosing a Strategy by Testing Goal

### 6.1. Testing a Service in a Full Application Context

If a production service requires an adapter, use `REPLACE` so the test both replaces the adapter and protects the configuration.

Example:

~~~java
@SpringBootTest
class InvoiceServiceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("invoiceRepository")
    InvoiceRepository invoiceRepository;

    @Autowired
    InvoiceService invoiceService;
}
~~~

The test verifies that the application context contains the required repository bean before replacing it. If the test only needs to control repository responses and does not care whether the production configuration includes the bean, `REPLACE_OR_CREATE` may be more appropriate.

### 6.2. Testing a Controller with a Web Slice

In `@WebMvcTest`, services are typically not loaded as in a full application context. The test needs to create a mock so the controller can be injected:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    InvoiceService invoiceService;

    @Autowired
    MockMvc mockMvc;
}
~~~

`REPLACE_OR_CREATE` is the natural choice for this scenario. The test verifies the MVC contract and needs a mock collaborator. It does not claim that the production `InvoiceService` is configured in the slice.

### 6.3. Observing a Real Bean

If you need to verify that a real adapter or collaborator is called, use `WRAP`:

~~~java
@SpringBootTest
class AuditServiceIntegrationTest {

    @MockitoSpyBean
    @Qualifier("auditWriter")
    AuditWriter auditWriter;

    @Autowired
    UserService userService;
}
~~~

Ensure the real implementation does not write data to shared systems or cause unintended side effects. If it does, use an isolated test environment or stub the side-effecting method.

### 6.4. Testing for Missing Bean Configuration

If a test needs to prove that a configuration must include a bean, use `REPLACE`. If you use `REPLACE_OR_CREATE`, the new mock bean could allow the context to start even when the production configuration lacks the bean.

This is a classic example showing that the override strategy affects the meaning of the test, not just how annotations are written.

## 7. Resolution When Multiple Beans Share the Same Type

Suppose the context has:

~~~java
@Bean
@Qualifier("primary")
PaymentGateway primaryGateway() {
    return new PrimaryPaymentGateway();
}

@Bean
@Qualifier("backup")
PaymentGateway backupGateway() {
    return new BackupPaymentGateway();
}
~~~

To replace the exact `primary` bean:

~~~java
@MockitoBean(enforceOverride = true)
@Qualifier("primary")
PaymentGateway primaryGateway;
~~~

To wrap the exact `backup` bean:

~~~java
@MockitoSpyBean
@Qualifier("backup")
PaymentGateway backupGateway;
~~~

If no qualifier is declared, Spring can use other resolution details such as the field name or bean name when appropriate. However, with multiple beans of the same type, an explicit qualifier makes the test's intent clear and prevents replacing the wrong candidate.

### 7.1. A Qualifier Does Not Override All Beans of the Same Type

A bean override typically targets the identified candidate; it does not mean every bean sharing the interface is replaced. If a test wants to replace multiple beans, declare each override explicitly or use an appropriate test configuration mechanism.

Do not assume that replacing `PaymentGateway` with a mock automatically replaces every `PaymentGateway` implementation in the context. That could cause routers, registries, or collection injections to behave differently from the real configuration.

### 7.2. Field Names Can Influence Selection

When declaring an override on a field, the field name can serve as a fallback qualifier if no clearer qualifier or bean name is provided. This is convenient for simple cases but can create implicit coupling.

If the context has multiple beans of the same type, declare `@Qualifier` or a bean name instead of renaming fields to subtly steer selection.

## 8. Bean Overrides and the `ApplicationContext` Lifecycle

Bean override declarations are part of the test context configuration. They can affect context customizers and the TestContext Framework's cache key.

This means:

- Two test classes with the same configuration and the same override declarations can share an `ApplicationContext`.
- Two test classes with different overrides may require separate contexts.
- Adding or removing a mock bean can change which context needs to be loaded.
- `@MockitoBean` and `@MockitoSpyBean` are not merely Java fields in a test class; they participate in container configuration.

When multiple tests share a context containing mock beans, Spring manages mock resetting according to the annotation's reset configuration. By default, mocks are typically reset after each test method to prevent interactions and stubbing from leaking into other tests. If you change the reset mode, understand clearly that mock state can be shared.

Avoid using a mock bean that accumulates state across multiple tests unless the test intentionally verifies that state. Set up stubbing within each test and let the default lifecycle reset clean up interactions.

### 8.1. Override Differences Can Reduce Cache Reuse

For example, several test classes may all use `@SpringBootTest`, yet each declares a different set of mock beans. Because context customization differs, Spring may have to create multiple contexts instead of reusing a single shared one.

Group tests with similar override needs when appropriate. However, do not merge tests into the same configuration solely to boost cache hits if doing so alters test scope or creates hard-to-control shared state.

## 9. Limitations and Notes

### 9.1. Only Override Beans Compatible with the Singleton Mechanism

Bean overriding in Spring TestContext is designed for singleton beans. Beans with other scopes such as prototype or request scope may not be overridden as expected and can cause context failures.

If you need to test scope behavior, test scope/lifecycle in a dedicated test. Do not assume a singleton mock replaces all semantics of a request-scoped bean.

### 9.2. WRAP Can Execute Real Logic

A spy is not a pure mock. Real methods are called unless stubbed by the test. A spy on an HTTP client, mail sender, or payment adapter can issue real requests.

Before using `WRAP`, assess the bean's side effects. If effects cannot be controlled, using `REPLACE` with a mock or fake is usually safer and clearer in intent.

### 9.3. REPLACE_OR_CREATE Can Hide Configuration Errors

If a bean must exist in production but the test uses `REPLACE_OR_CREATE`, the new mock can allow the context to start even though the real configuration is missing the bean. Use `REPLACE` when the bean's existence is part of what needs to be verified.

### 9.4. REPLACE Does Not Mean Replacing Every Candidate

If multiple beans share the same type, the test still needs to identify the exact bean. If the qualifier or name is not clear enough, Spring may fail because it cannot resolve the candidate. Declare qualifiers explicitly.

### 9.5. Not Every Dependency Needs to Be Mocked

Mocking too many beans can leave the test verifying only a chain of mock-to-mock interactions without testing real collaboration behavior. Keep beans within the scope to be proven and replace collaborators outside that boundary.

### 9.6. `FactoryBean` and Proxied Beans

Some beans are created through a `FactoryBean` or wrapped by Spring proxies. Bean overriding has specific handling rules for these cases and can affect which kind of object is replaced or wrapped. When tests target a `FactoryBean`, AOP proxy, transaction, or security advice, clarify whether the test needs to observe the factory, the product bean, or the bean proxy, and consult the documentation for your Spring version.

Do not use a spy on the target object to conclude that calls passed through a proxy and interceptors. If the goal is to test transaction or security advice, retrieve the bean from the `ApplicationContext` through the proper proxy and verify its effects.

## 10. Spring Boot Versions and Corresponding Annotations

The three strategies above belong to Spring Framework 6.2's bean override infrastructure. The `@MockitoBean` and `@MockitoSpyBean` annotations were introduced in that version.

Spring Boot 3.3.x is based on Spring Framework 6.1.x, so projects on that baseline typically use the older Spring Boot annotations:

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
~~~

`@MockBean` and `@SpyBean` are Spring Boot APIs predating Framework 6.2's bean override mechanism. They share a similar usage-level purpose, but you should not assume all of their attributes or semantics match `@MockitoBean(enforceOverride = true)` and `@MockitoSpyBean` identically.

In Spring Boot 3.4 and later, `@MockBean` and `@SpyBean` are marked deprecated to gradually transition to the new Spring Framework annotations. When writing tests, check the actual Spring Boot and Spring Framework versions selected by dependency management.

| Platform | Commonly Used Annotations |
| --- | --- |
| Spring Boot 3.3 / Spring Framework 6.1 | `@MockBean`, `@SpyBean` |
| Spring Framework 6.2 and above | `@MockitoBean`, `@MockitoSpyBean` |
| Spring Boot 3.4 and above | Framework 6.2 annotations can be used; older Boot annotations are deprecated |

Do not upgrade `spring-test` alone or mix Spring versions just to get the new annotations while bypassing Spring Boot's dependency alignment. Let the project's BOM or dependency management control compatible Spring modules.

## 11. Comprehensive Example: Choosing the Right Strategy for `PaymentGateway`

Suppose `CheckoutService` receives a `PaymentGateway` with the `stripe` qualifier. We want to test three different objectives.

### 11.1. Objective A: Replace an Already-Configured Production Bean

Choose `REPLACE`:

~~~java
@SpringBootTest
class CheckoutReplaceTest {

    @MockitoBean(enforceOverride = true)
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

Meaning: the test requires the `stripe` bean to exist in the context. If missing, the context fails. When present, the mock replaces the real bean so the test can control payment outcomes.

### 11.2. Objective B: Web Slice Needs a Mock Service

Choose `REPLACE_OR_CREATE`:

~~~java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
~~~

Meaning: the web slice needs a collaborator so the controller can be injected. If the service is not in the slice, a new mock is created. The test verifies only the controller's HTTP contract and mapping.

### 11.3. Objective C: Observe a Real Implementation

Choose `WRAP`:

~~~java
@SpringBootTest
class CheckoutSpyTest {

    @MockitoSpyBean
    @Qualifier("stripe")
    PaymentGateway stripeGateway;

    @Autowired
    CheckoutService checkoutService;
}
~~~

Meaning: the `stripe` bean must exist. The spy wraps the real instance so the test can verify interactions or stub specific methods. Unstubbed methods can still run real logic and cause side effects.

These three tests can examine the same business flow at different boundaries. They should not be merged into a single test merely to reduce class count, because each test embodies a different assumption about beans and how much real code executes.

## 12. Process for Choosing REPLACE, REPLACE_OR_CREATE, or WRAP

Before declaring a bean override, answer these questions:

**Step 1 – Identify the SUT and objective.** Is the test verifying a service, controller, adapter, or context configuration?

**Step 2 – Identify the bean to intercept.** Specify its type, qualifier, or bean name. If multiple candidates exist, never let selection depend on registration order.

**Step 3 – Determine whether the production bean must exist.** If yes, choose `REPLACE`. If the test intentionally creates a collaborator in a minimal context, choose `REPLACE_OR_CREATE`.

**Step 4 – Determine whether the real implementation needs to run.** If you need to keep real behavior and only observe or partially stub it, choose `WRAP`. If real logic is unnecessary, use a replacement mock.

**Step 5 – Assess side effects.** `WRAP` can hit real HTTP endpoints, databases, brokers, or filesystems. Prepare an isolated environment or choose `REPLACE`.

**Step 6 – Verify the context.** Ensure the bean candidate resolves properly and the strategy reflects the test's assumptions.

**Step 7 – Write behavioral assertions.** Assert meaningful outputs, state, and interactions. Do not merely verify that a mock was injected.

**Step 8 – Consider caching and lifecycle.** Different override declarations can produce different context cache entries; mocks are reset according to lifecycle configuration.

## 13. Quick Decision Table

| Question | Suitable Strategy |
| --- | --- |
| The production bean must exist and I want to replace it with a mock? | `REPLACE` |
| The test slice does not load the bean and I need to create a mock to inject into the SUT? | `REPLACE_OR_CREATE` |
| I want to keep the real bean while observing calls or partially stubbing it? | `WRAP` |
| I want the test to detect a missing production bean? | `REPLACE` |
| I do not care whether the production bean is registered in a minimal context? | `REPLACE_OR_CREATE` |
| The bean has external side effects and I do not want to call the real implementation? | `REPLACE` or `REPLACE_OR_CREATE` |
| I need to verify that a real adapter is called and can control its side effects? | `WRAP`, combined with an appropriate mock/test environment |
| Multiple beans share the same type? | Any strategy still needs a qualifier or name to select the right candidate |

## Conclusion

`REPLACE`, `REPLACE_OR_CREATE`, and `WRAP` express three distinct intents when replacing beans in Spring tests. `REPLACE` requires the production bean to exist and replaces it; `REPLACE_OR_CREATE` replaces the bean if present or creates a test bean if absent; `WRAP` requires an existing bean and wraps the real instance, typically with a Mockito spy.

With Spring Framework 6.2, `@MockitoBean` defaults to `REPLACE_OR_CREATE` and can enable `enforceOverride` to require `REPLACE`; `@MockitoSpyBean` uses `WRAP`. Choose the strategy based on what the test needs to prove, declare qualifiers explicitly when multiple beans share the same type, and watch out for side effects when using spies. In particular, if the existence of a production bean is part of the configuration contract, use `REPLACE` so tests do not accidentally hide a missing bean.
