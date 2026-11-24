# @Fallback and Utilities Available Only in Newer Spring Framework Versions

When a Spring application has multiple beans implementing the same interface, the container needs to decide which bean will be injected into a dependency. Previously, the common options were `@Primary`, `@Qualifier`, profiles, and conditional bean creation rules. Starting in **Spring Framework 6.2**, the bean selection mechanism adds `@Fallback` and the `defaultCandidate` attribute on `@Bean`, helping express default and fallback beans more clearly.

Spring Framework 6.2 also introduces bean override annotations in Spring Test such as `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean`. They provide a unified Spring Test mechanism for replacing or spying on beans in a test context.

This lesson focuses on these utilities and how to use them in a Spring Boot application:

- Understand `@Fallback` and how it affects autowiring.
- Distinguish between `@Fallback`, `@Primary`, `@Qualifier`, and `@Bean(defaultCandidate = false)`.
- Understand bean selection by parameter name in applicable injection scenarios.
- Use `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean` to override beans in tests.
- Determine the actual Spring Framework version managed by Spring Boot.
- Avoid using newer APIs on older runtimes or upgrading Spring Framework modules individually in a way that causes dependency mismatches.

## 1. Spring Framework and Spring Boot Are Two Different Layers

Spring Boot builds on top of Spring Framework and manages a compatible set of dependencies through dependency management/BOM.

- **Spring Framework** provides the IoC container, dependency injection, AOP, transactions, the web stack, and Spring Test.
- **Spring Boot** provides auto-configuration, starters, externalized configuration, Actuator, and conventions for building applications faster.
- **Spring Boot version** typically determines which Spring Framework version is managed in a project.

For example, `@Fallback` is a **Spring Framework** annotation located in the package:

```java
org.springframework.context.annotation.Fallback
```

Bean override annotations such as `@MockitoBean` also belong to Spring Test, not specifically to Spring Boot.

This matters when reading documentation: a feature introduced in Spring Framework 6.2 can be used in a Spring Boot application if the project is running with a compatible Spring Framework version. Simply upgrading a single Spring Boot starter or adding an import will not make a new class appear if the runtime still uses an older Framework version.

## 2. Identifying the Version That Introduces Each Feature

The main utilities covered in this lesson were introduced in **Spring Framework 6.2**:

| Utility | Spring Framework | Main Package |
|---|---:|---|
| `@Fallback` | 6.2+ | `org.springframework.context.annotation` |
| `@Bean(defaultCandidate = false)` | 6.2+ | `org.springframework.context.annotation.Bean` |
| Improved bean selection shortcut by parameter name | 6.2+ | Autowire candidate resolution |
| `@TestBean` | 6.2+ | `org.springframework.test.context.bean.override.convention` |
| `@MockitoBean` | 6.2+ | `org.springframework.test.context.bean.override.mockito` |
| `@MockitoSpyBean` | 6.2+ | `org.springframework.test.context.bean.override.mockito` |

Spring Boot 3.4 and later typically manage Spring Framework 6.2.x; older Boot lines may manage Framework 6.1.x or earlier. This relationship is governed by the BOM of each release line, so check the effective version in your project rather than inferring solely from a starter name.

If the project is on Framework 6.1, code importing `@Fallback` or using `defaultCandidate` may fail to compile. Do not upgrade `spring-context` alone to a different minor version from the rest of the Spring modules just to force a feature to work.

## 3. The Problem of Multiple Beans Implementing the Same Interface

Suppose an application has the interface:

```java
public interface PaymentGateway {
    String providerName();

    PaymentResult charge(PaymentRequest request);
}
```

There is one implementation using the primary payment provider:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "remote";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        // Call the payment provider via the configured client.
        return PaymentResult.accepted();
    }
}
```

And a fallback or simulated implementation:

```java
@Component
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "local";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        // Illustrative behavior for local/test.
        return PaymentResult.accepted();
    }
}
```

A service injects by interface:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedProvider() {
        return paymentGateway.providerName();
    }
}
```

If both beans are registered and there is no candidate selection rule, Spring may throw `NoUniqueBeanDefinitionException`.

The question is not only “which beans exist?” but also “which bean should be treated as the default choice when a consumer simply asks for a `PaymentGateway`?”

## 4. @Primary: Marking the Preferred Bean

`@Primary` has existed in Spring for a long time. It marks a bean to be preferred when multiple candidates match a single-valued injection point.

Example:

```java
@Component
@Primary
public class RemotePaymentGateway implements PaymentGateway {
    // Primary implementation.
}
```

```java
@Component
public class LocalPaymentGateway implements PaymentGateway {
    // Secondary implementation.
}
```

When `CheckoutService` injects a single `PaymentGateway`, `RemotePaymentGateway` is selected because it is the primary candidate.

Key points to remember:

- `@Primary` does not prevent other beans from being created.
- Non-primary beans can still be injected using a qualifier.
- If multiple matching primary candidates exist, Spring still cannot determine a single bean.
- `@Primary` primarily affects selecting one bean for a single-valued injection point; it is not a collection filter.

For example:

```java
@Autowired
PaymentGateway paymentGateway;
```

may receive `RemotePaymentGateway`, while:

```java
@Autowired
List<PaymentGateway> paymentGateways;
```

can still receive both matching implementations.

## 5. What Is @Fallback?

Spring Framework 6.2 introduces `@Fallback` to mark a bean as a **fallback candidate**.

```java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Component
@Fallback
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "local";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return PaymentResult.accepted();
    }
}
```

The main bean does not need `@Primary`:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "remote";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return PaymentResult.accepted();
    }
}
```

For an injection point requesting a single `PaymentGateway`, if there is one regular candidate and one fallback candidate, the regular candidate takes precedence. In this example, the service receives `RemotePaymentGateway`.

If no regular candidate matches and only one fallback candidate is available, Spring can select that fallback bean.

**Meaning:** `@Fallback` is not a bean-creation annotation or a profile activator. It changes how the container ranks already-registered beans when resolving autowiring.

## 6. Comparing @Primary and @Fallback

The two annotations express opposite intents:

- `@Primary`: this bean is the preferred choice.
- `@Fallback`: this bean should only be selected when no regular option matches.

| Scenario | Single-Valued Bean Selection Outcome |
|---|---|
| One regular bean, one fallback bean | Regular bean |
| Only one fallback bean | Fallback bean |
| One primary bean and other candidates | Primary bean |
| Multiple regular beans, no primary/qualifier | May be ambiguous |
| Multiple fallback beans, no regular candidate | May be ambiguous |
| Qualifier explicitly identifies a candidate | Candidate matching the qualifier is selected per resolution rules |

An easy-to-remember example:

```text
PaymentGateway candidates
       │
       ├── RemotePaymentGateway (regular)
       │
       └── LocalPaymentGateway  (@Fallback)
                    │
                    ▼
       Inject a single PaymentGateway
                    │
                    ▼
           RemotePaymentGateway
```

If the remote bean is removed from the context and local is the only fallback candidate, local can be selected.

Do not place both `@Primary` and `@Fallback` on the same bean to express two contradictory intents. Choose the annotation that reflects a clear policy.

## 7. @Fallback Is Not Business Failover

`@Fallback` only controls Spring's candidate resolution. It does not automatically perform retries, circuit breaking, failover, or request rerouting when a remote provider fails.

For example, if `RemotePaymentGateway` exists and is selected, and a network call times out, Spring does not automatically switch to `LocalPaymentGateway` just because the local bean has `@Fallback`.

These are two different layers:

| Layer | Mechanism |
|---|---|
| Bean selection at context creation/injection time | `@Primary`, `@Fallback`, `@Qualifier`, candidate rules |
| Switching providers when a runtime call fails | Resilience logic, routing service, circuit breaker, retry, or failover code |

Do not use `@Fallback` assuming the application will automatically fall back to another provider when a request fails. If runtime failover is needed, build an orchestration component and test that behavior separately.

## 8. @Fallback on a @Bean Method

You can mark a fallback bean by placing the annotation on a `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway remotePaymentGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Fallback
    PaymentGateway localPaymentGateway() {
        return new LocalPaymentGateway();
    }
}
```

Here, two beans of the same type are registered. The local bean still exists in the context, but is marked as a fallback candidate.

This approach is useful when the implementation is created by a factory method or needs constructor dependencies configured before instantiating the object.

You can also place `@Fallback` directly on the bean class as in the component example earlier. Choose one registration approach and avoid registering the same implementation twice via both component scanning and `@Bean`.

## 9. Using Fallback When No Regular Bean Exists

Suppose a module needs a `Clock`. The application can provide the main clock, while a library module provides a default clock:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @Fallback
    Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

The application configuration can supply the main clock:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

A service injecting `Clock` by type will receive the regular `businessClock` when both exist.

If the application does not supply its own clock, `defaultClock` can become the only choice.

This design is often useful for reusable configurations or libraries that want to provide default behavior while still letting the application override it.

**Note:** a fallback is only appropriate if the default is genuinely safe. Do not provide a dummy fallback for a payment gateway or security provider if it makes the application appear to work while bypassing mandatory business requirements.

## 10. @Qualifier Is Still Used When Exact Selection Is Needed

`@Qualifier` expresses that an injection point requires a specific candidate by qualifier.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Qualifier("primary")
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Qualifier("local")
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

A consumer that explicitly needs local:

```java
@Service
public class OfflineCheckoutService {

    private final PaymentGateway paymentGateway;

    public OfflineCheckoutService(
            @Qualifier("local") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

A normal consumer without a qualifier can receive the regular candidate.

Do not use `@Fallback` as a substitute for a qualifier if a consumer needs **a specific implementation for its functional role**. Fallback is a general priority policy; a qualifier is a candidate selection directive for an injection point.

## 11. @Bean(defaultCandidate = false) in Spring Framework 6.2

Spring Framework 6.2 adds the `defaultCandidate` attribute to `@Bean`.

```java
@Bean(defaultCandidate = false)
@Qualifier("special")
SpecialClient specialClient() {
    return new SpecialClient();
}
```

The bean is still registered in the application context, but it is not considered a default candidate for unqualified autowiring. It can still be retrieved by name or selected through a matching qualifier.

Example consumer needing the special bean:

```java
@Service
public class SpecialJob {

    private final SpecialClient client;

    public SpecialJob(
            @Qualifier("special") SpecialClient client) {
        this.client = client;
    }
}
```

This is helpful when a module supplies an additional bean of the same type for a dedicated use case, without wanting that bean to cause ambiguity for normal injection points.

`defaultCandidate = false` does not mean the bean is disabled or not created. It remains a bean in the container and can be accessed explicitly.

## 12. Distinguishing @Fallback and defaultCandidate = false

Both mechanisms affect candidate selection, but they express different intents:

- `@Fallback`: the bean remains a fallback candidate for autowiring; it can be selected if no regular candidate matches.
- `@Bean(defaultCandidate = false)`: the bean is not a default autowire candidate; to use it, you should explicitly specify a qualifier or bean name.

| Aspect | `@Fallback` | `defaultCandidate=false` |
|---|---|---|
| Bean is created in the context | Yes | Yes |
| Selected when a regular candidate exists | Normally no for single-valued injection | Not a default candidate |
| Can be chosen when only fallback remains | Yes, if candidate resolution identifies a single bean | Not the purpose of this mechanism |
| Can be explicitly selected by qualifier/name | Yes | Yes |
| How it is declared | Annotation on class or `@Bean` method | Attribute on `@Bean` |
| Intent | Automatic fallback | Auxiliary bean, used only when explicitly requested |

Do not use the two mechanisms interchangeably just because both make a bean less likely to be picked by default.

## 13. Example of defaultCandidate=false with Two Clients of the Same Type

Suppose there is a primary client and a client dedicated to auditing:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    ApiClient apiClient() {
        return new ApiClient("general");
    }

    @Bean(defaultCandidate = false)
    @Qualifier("audit")
    ApiClient auditApiClient() {
        return new ApiClient("audit");
    }
}
```

Normal consumer:

```java
@Service
public class CatalogService {

    private final ApiClient apiClient;

    public CatalogService(ApiClient apiClient) {
        this.apiClient = apiClient;
    }
}
```

Audit consumer:

```java
@Service
public class AuditService {

    private final ApiClient apiClient;

    public AuditService(@Qualifier("audit") ApiClient apiClient) {
        this.apiClient = apiClient;
    }
}
```

The goal is for `CatalogService` to receive the general client, while `AuditService` selects the audit client by qualifier.

If `defaultCandidate=false` is omitted and no other qualifier/primary is present, having two default candidates of the same type can make single-valued injection ambiguous.

## 14. Candidate Resolution and Collection Injection

`@Primary` and `@Fallback` mainly help resolve injections that need a single bean. When injecting a collection, an application typically wants to receive all matching candidates.

Example:

```java
@Service
public class GatewayRegistry {

    private final List<PaymentGateway> gateways;

    public GatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
```

Collection injection is a different use case from selecting a single bean. Do not use `@Fallback` expecting the fallback bean to vanish automatically from every bean list or map.

If business logic needs only a subset of beans, use an appropriate qualifier, design a marker interface, create a custom qualifier annotation, or filter by explicit metadata/domain rules.

For example, retrieving all beans by type:

```java
Map<String, PaymentGateway> allGateways =
        applicationContext.getBeansOfType(PaymentGateway.class);
```

The fallback bean is still a bean in the context and remains visible via bean-listing APIs. Candidate ranking is not a mechanism for removing beans from the container.

## 15. Parameter Name Matching in Injection

Spring can use parameter names to resolve dependencies in certain situations when no clearer directive is present.

For example, suppose there are two beans:

```java
@Bean
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}
```

Constructor:

```java
public CheckoutService(PaymentGateway remoteGateway) {
    this.paymentGateway = remoteGateway;
}
```

If parameter name metadata is retained and resolution conditions fit, the name `remoteGateway` can help Spring pick the bean with the matching name when no qualifier/primary rule takes precedence.

However, this is a name-based resolution mechanism in specific contexts and should not be used as a substitute for the explicit contract of `@Qualifier`.

In Spring Framework 6.2, bean-name matching has a fast shortcut in eligible cases, avoiding full candidate lookup when the parameter name matches a bean name. This mechanism does not turn every constructor parameter into an immutable qualifier.

## 16. Why the Compiler Needs to Retain Parameter Names

Java parameter names may not be preserved in bytecode unless the project enables the corresponding compiler option.

With the Maven compiler plugin, the standard configuration is:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

With Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

If parameter names are absent from metadata, Spring cannot rely on source-code names that the compiler stripped out.

Prefer `@Qualifier` for injection points that carry specific business meaning. Parameter-name matching should be treated as a supplemental convenience, not the sole guarantee of bean resolution.

## 17. When to Use @Primary, @Fallback, Qualifier, or defaultCandidate?

| Need | Mechanism to Consider |
|---|---|
| One clear default implementation | `@Primary` |
| A fallback implementation when no regular option exists | `@Fallback` |
| Consumer needs a specific implementation | `@Qualifier` |
| Auxiliary bean should only be used when explicitly named/qualified | `@Bean(defaultCandidate=false)` |
| Select bean by profile/environment | `@Profile` |
| Only create bean when a property/condition is satisfied | `@Conditional...` |

Decision examples:

- `RemotePaymentGateway` is the main provider: can be a regular bean or `@Primary`.
- `LocalPaymentGateway` is used only when no other provider exists: `@Fallback`.
- `AuditApiClient` is used only in `AuditService`: `@Qualifier` combined with `defaultCandidate=false`.
- `DevPaymentGateway` exists only in dev: `@Profile("dev")`.

These mechanisms can be combined, but each annotation should express an intentional rule. Avoid piling on annotations just to make Spring “pick something.”

## 18. What Is Spring Test Bean Overriding?

Spring Framework 6.2 brings bean overriding into Spring Test with the following annotations:

- `@TestBean`: replaces a bean with an object provided by a test factory method.
- `@MockitoBean`: creates a Mockito mock and registers/overrides the bean in the test context.
- `@MockitoSpyBean`: creates a spy wrapping an existing bean.

These annotations allow tests to swap out a dependency without needing to write a separate configuration class for every scenario.

For example, `CheckoutService` needs `PaymentGateway`, but a test only wants to verify how the service reacts to a declined result. You can replace the real bean with a Mockito mock in the test context.

The override mechanism belongs to Spring Test. It does not change how the production application registers beans and should not be imported into main source code.

## 19. @MockitoBean: Replacing a Bean with a Mockito Mock

Example:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void handlesAcceptedPayment() {
        given(paymentGateway.providerName())
                .willReturn("mock-provider");

        assertThat(checkoutService.selectedProvider())
                .isEqualTo("mock-provider");
    }
}
```

`@MockitoBean` creates a mock and places it into the test application context. By default, the override mechanism can replace a matching bean if one exists or register a new mock depending on configuration/target resolution.

If there are multiple beans of the same type, identify the target bean using a qualifier or matching field name. Do not let a test accidentally mock the wrong implementation.

The static imports `given` and `willReturn` come from the Mockito BDD API; you can use `when(...).thenReturn(...)` if the project uses that style.

## 20. Using @MockitoBean When Requiring the Bean to Exist

When the goal is to replace **a bean already declared by the application context**, you can require the override mode to replace an existing bean rather than silently creating a new one, using the `enforceOverride` attribute in the corresponding APIs.

Example:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
```

This makes the test fail if no bean is found to replace, subject to the test context's candidate/qualifier resolution.

This is useful when you want to verify that the test is mocking a real dependency from production wiring. If the bean is missing due to a wrong profile or component scan issue, the test should not create a new mock and mask that error.

Verify annotation attributes against the Spring Framework version you are using; do not copy 6.2 APIs into a project running an older Framework version.

## 21. Selecting a Specific Bean to Mock

If the application has two `PaymentGateway` beans, merely writing:

```java
@MockitoBean
PaymentGateway paymentGateway;
```

may not provide enough information to pick a single target bean in the context.

You can combine it with a qualifier:

```java
@MockitoBean
@Qualifier("remoteGateway")
PaymentGateway paymentGateway;
```

Or use a field name matching the bean name when resolution supports it:

```java
@MockitoBean
PaymentGateway remoteGateway;
```

Using clear field names and explicit qualifiers when multiple candidates exist makes tests much easier to read over the long term.

If you want to test whether `LocalPaymentGateway` or `RemotePaymentGateway` is selected via `@Fallback`, do not mock the very `PaymentGateway` you are testing. Keep the real beans and assert on the concrete type so the test does not hide candidate resolution.

## 22. @MockitoSpyBean: Observing a Real Bean

`@MockitoSpyBean` creates a spy from an existing bean. Unlike a mock, a spy keeps the real behavior by default, while allowing the test to stub specific methods and verify invocations.

Example:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class RemoteGatewaySpyTest {

    @MockitoSpyBean
    RemotePaymentGateway remotePaymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void invokesRemoteGateway() {
        checkoutService.selectedProvider();

        then(remotePaymentGateway)
                .should()
                .providerName();
    }
}
```

This example illustrates verification; an actual test needs to ensure the method is called through the spy bean injected into the consumer.

A spy requires an existing target bean and must resolve to a single matching candidate. If the bean does not exist or multiple indistinguishable candidates exist, the test context may fail.

Do not use a spy when you want to eliminate external side effects completely. A spy still executes real methods unless you stub those methods.

## 23. Differences Between Mock and Spy

| Criterion | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Object in context | Mockito mock | Spy wrapping a real bean |
| Default behavior | Mock does not run real implementation | Calls real methods unless stubbed |
| Purpose | Isolate a dependency | Observe or partially stub a real bean |
| Existing bean | Can replace or create depending on override mode | Needs a matching bean to spy on |
| Side effects | Does not run real behavior unless stubbed/delegated | Can trigger real side effects |
| Risk | Mocking the wrong bean makes tests diverge from real wiring | Spy may hit real network/database |

Use a mock to isolate boundaries. Use a spy when you have a reason to observe a real bean in the context. Do not spy on a production client that can send real requests unless the test controls those side effects.

## 24. @TestBean: Replacing a Bean with a Test Factory Method

`@TestBean` is suitable when you want to replace a bean with an implementation or object provided directly by the test, without needing Mockito.

Example:

```java
import org.springframework.test.context.bean.override.convention.TestBean;

@SpringBootTest
class CheckoutWithStubGatewayTest {

    @TestBean(methodName = "paymentGatewayOverride")
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGatewayOverride() {
        return new StubPaymentGateway();
    }

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesStubGateway() {
        assertThat(checkoutService.selectedProvider())
                .isEqualTo("stub");
    }
}
```

The factory method supplies the object used to override the target bean. The method is normally declared static in the test class and must return a type compatible with the field.

The method name can be specified explicitly via `methodName`; if omitted, Spring Test uses a naming convention based on the field name. Specifying an explicit name helps readers immediately see which object replaces which bean.

`StubPaymentGateway` is a test implementation you write yourself; it is not a built-in Spring class.

## 25. When to Use @TestBean Instead of @MockitoBean?

Choose `@TestBean` when:

- You want a fake/stub with deterministic behavior.
- You want to test multiple calls with simple internal state.
- You do not need Mockito verification or stubbing APIs.
- You want the test code itself to describe the replacement implementation.

Choose `@MockitoBean` when:

- You want per-test method stubbing.
- You want to verify invocations/arguments.
- The dependency is an easy-to-mock boundary.
- You want to replace a bean with a mock quickly.

Choose `@MockitoSpyBean` when:

- You need to preserve real behavior.
- You need to verify method invocations.
- You only want to stub part of the behavior and already control side effects.

You do not have to pick a single annotation for the entire suite. Each test should use the tool suited to what it wants to prove.

## 26. Bean Overrides and Test Slices

Bean override annotations can be used in appropriate Spring Test contexts, including full `@SpringBootTest` and many test slices.

Example with an MVC slice:

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
```

`@WebMvcTest` loads only a partial context for the web layer. Mocking the service here makes sense because the test verifies controller mapping and serialization.

However, if the goal is to verify which implementation `@Fallback` selects across the application, an MVC slice with `@MockitoBean PaymentGateway` does not prove that. Write a separate context test that keeps the real candidate beans.

## 27. Spring Framework 6.2 and Older Boot Annotations

Before Spring Framework 6.2, many Spring Boot projects used:

- `@MockBean`.
- `@SpyBean`.

These annotations were provided by Spring Boot Test. In newer Spring Boot lines compatible with Spring Framework 6.2, Spring Test provides `@MockitoBean` and `@MockitoSpyBean` as the Framework-level bean override mechanism.

Spring Boot 3.4 deprecated the older `@MockBean` and `@SpyBean` annotations in favor of the new Spring Test annotations. When upgrading, check the Boot version and corresponding migration notes.

Do not mechanically replace every annotation in one sweep if the test suite has custom configuration or different semantics. Read warnings/deprecations and verify that tests still override the right beans.

## 28. Common Errors When Using the New Test Annotations

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `@MockitoBean` not found | Spring Test version is too old | Check Spring Framework dependency |
| `@Fallback` fails to compile | Spring Context below 6.2 | Upgrade to a compatible Boot/BOM line |
| `defaultCandidate` not recognized | Older `@Bean` API | Check `spring-context` compile version |
| Test mocks the wrong bean | Multiple candidates of the same type | Use an explicit `@Qualifier`/bean name |
| Spy cannot find bean | Bean does not exist or candidate is ambiguous | Check context/profile/qualifier |
| `@TestBean` cannot find factory | Method name/visibility/static/return type mismatch | Specify `methodName` and check signature |
| Test passes even though production bean is missing | Mock override creates a new bean instead of requiring replacement | Use the appropriate enforce-override mode |
| Test does not verify real `@Fallback` | Candidate was mocked/overridden | Keep real bean implementations |
| Test slice does not see bean | Slice does not load that configuration | Use full context or appropriate runner |
| `NoSuchMethodError` at runtime | Compile/runtime Spring versions mismatch | Align dependency management |
| Multiple Spring modules on different versions | Manual BOM/dependency overrides | Use a single unified Spring Boot BOM |

## 29. Checking the Actual Spring Framework Version

Do not blindly trust the Spring Boot version written in `build.gradle` or `pom.xml`. Inspect the resolved dependencies.

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
```

You can also check Spring Core:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-context
```

Or:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
```

These commands show the version chosen after dependency mediation/BOM management.

If the output shows an unusual minor version mismatch between `spring-context` and `spring-core`, investigate dependency overrides or dependency management before running the application.

## 30. Do Not Upgrade a Single Spring Module in Isolation

Spring Framework consists of many interconnected modules, for example:

- `spring-core`.
- `spring-beans`.
- `spring-context`.
- `spring-aop`.
- `spring-expression`.
- `spring-test`.
- Web, transaction, JDBC, and ORM modules.

Some new APIs may be declared in `spring-context`, yet runtime execution still depends on other modules.

If the project uses Spring Boot dependency management, let the BOM manage Spring Framework artifacts. Avoid pinning a separate version for `spring-context` without aligning related modules.

An inconsistent dependency graph can lead to:

- `NoSuchMethodError`.
- `NoClassDefFoundError`.
- `ClassNotFoundException`.
- Different behavior between test compilation and runtime.
- Test context startup failing before any test method runs.

## 31. Checking the Classpath in IDEs and CI

A project might compile on a developer's machine while CI uses a different dependency cache or build configuration.

Check:

1. Gradle/Maven wrapper version.
2. The JDK the build tool actually uses.
3. Spring Boot plugin/parent/BOM version.
4. Resolved versions of `spring-context` and `spring-test`.
5. Dependency exclusions and forced versions.
6. The test runtime classpath, not only the main runtime classpath.
7. Whether IDE delegated builds use the same build tool as CI.

For test annotations, `spring-test` belongs to the test classpath. For `@Fallback` and `@Bean(defaultCandidate=...)`, `spring-context` belongs to the application compile/runtime classpath.

If an annotation exists at compile time but a class or method is missing at runtime, look for a version mismatch rather than changing imports.

## 32. Writing Tests to Verify @Fallback

Suppose you have this configuration:

```java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Context test:

```java
@SpringBootTest(
    classes = GatewayConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class FallbackSelectionTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Autowired
    ApplicationContext context;

    @Test
    void regularCandidateWinsOverFallback() {
        assertThat(paymentGateway)
                .isInstanceOf(RemotePaymentGateway.class);

        assertThat(context.getBeansOfType(PaymentGateway.class))
                .hasSize(2);
    }
}
```

The test proves:

- Both beans exist.
- A consumer injects a single `PaymentGateway`.
- The regular candidate is selected while the fallback candidate still exists in the context.

This is a candidate resolution test; it does not prove runtime failover when a remote call fails.

## 33. Testing Fallback When No Regular Bean Exists

You can create a configuration providing only the fallback:

```java
@Configuration(proxyBeanMethods = false)
class FallbackOnlyConfiguration {

    @Bean
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

And test:

```java
@Test
void usesFallbackWhenItIsTheOnlyCandidate() {
    new ApplicationContextRunner()
        .withUserConfiguration(FallbackOnlyConfiguration.class)
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(PaymentGateway.class);

            assertThat(context.getBean(PaymentGateway.class))
                    .isInstanceOf(LocalPaymentGateway.class);
        });
}
```

`ApplicationContextRunner` is a good fit because you only need to spin up a small context with the configuration under test.

If there are multiple fallback beans of the same type and no other candidates, do not assume Spring will arbitrarily pick one. Add a qualifier/primary or design the candidate set so there is a unique outcome.

## 34. Testing defaultCandidate=false

Example configuration:

```java
@Configuration(proxyBeanMethods = false)
class ApiClientConfiguration {

    @Bean
    ApiClient generalClient() {
        return new ApiClient("general");
    }

    @Bean(defaultCandidate = false)
    @Qualifier("audit")
    ApiClient auditClient() {
        return new ApiClient("audit");
    }
}
```

Default consumer under test:

```java
class GeneralClientConsumer {

    private final ApiClient client;

    GeneralClientConsumer(ApiClient client) {
        this.client = client;
    }

    String mode() {
        return client.mode();
    }
}
```

The test can verify that unqualified injection receives the general client, while explicit lookup receives the audit client:

```java
new ApplicationContextRunner()
    .withUserConfiguration(
        ApiClientConfiguration.class,
        GeneralClientConsumerConfiguration.class
    )
    .run(context -> {
        assertThat(context.getBean(GeneralClientConsumer.class).mode())
                .isEqualTo("general");

        assertThat(context.getBean("auditClient", ApiClient.class).mode())
                .isEqualTo("audit");
    });
```

This tests the intent that “the auxiliary bean still exists in the context, but does not participate in default autowiring.”

If a test needs to inject the audit client by qualifier, add a consumer with `@Qualifier("audit")` and verify it separately.

## 35. Checking Which Bean Is Injected vs. Checking Bean Existence

Three assertions answer different questions:

```java
// Does the bean exist?
assertThat(context.containsBean("localGateway")).isTrue();

// How many beans share this contract?
assertThat(context.getBeansOfType(PaymentGateway.class)).hasSize(2);

// Which implementation does the consumer actually receive?
assertThat(checkoutService.selectedProvider()).isEqualTo("remote");
```

A test that only checks `containsBean` can pass even if the consumer injects the wrong bean. A test that only checks consumer behavior might miss a redundant bean if both implementations return the same result.

For configurations with candidate ranking, check both the context inventory and the injection outcome according to the contract you need to protect.

## 36. Context Caching and Bean Override Annotations

Spring Test caches application contexts. Test configuration elements, including bean override customizers, can affect the context cache key.

Consequences:

- Tests with the same configuration and the same override declarations can reuse the context.
- Tests with different overrides may require separate contexts.
- A mock is reset according to the Spring Test/Mockito integration lifecycle; do not rely on mock state persisting across test methods.
- `@DirtiesContext` forces a context to be evicted from the cache, but should not be used by default on every test with mocks.

Keep tests independent: each test method sets up its own stubbing and verification without depending on execution order.

If the test suite becomes too slow, inspect how many distinct contexts are created and how annotations are configured before adding `@DirtiesContext` everywhere.

## 37. New Utilities Do Not Replace Profile/Property Conditions

`@Fallback` and `defaultCandidate` only assist candidate resolution. They do not replace:

- `@Profile`: should the bean be registered in the active profile?
- `@ConditionalOnProperty`: should the bean be registered when a property matches?
- `@ConditionalOnClass`: should the bean be registered when a class is on the classpath?
- `@Qualifier`: which candidate does the injection point need?
- `@Primary`: which candidate takes precedence?

Example:

```java
@Bean
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment",
    name = "remote-enabled",
    havingValue = "true"
)
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
@Fallback
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}
```

If `prod` is active and `payment.remote-enabled=true`, the remote bean exists and the regular candidate is selected.

If the remote bean is not created, the local fallback is the only candidate and can be selected. That is only right if local fallback is actually permitted in production; otherwise, design the application to fail fast instead of supplying an unsafe fallback.

## 38. Limitations to Keep in Mind

1. `@Fallback` does not create beans by itself.
2. `@Fallback` does not reroute requests when the primary provider fails.
3. `@Fallback` does not remove a bean from the application context.
4. `@Fallback` does not resolve ambiguity among multiple regular candidates.
5. `defaultCandidate=false` does not disable a bean.
6. `@Qualifier` remains the explicit choice when a dependency requires a specific implementation.
7. `@Primary` and `@Fallback` do not replace `@Profile` or `@Conditional...`.
8. `@MockitoBean` can hide the very bean selection behavior a test intends to verify.
9. `@MockitoSpyBean` can execute real methods and cause side effects.
10. `@TestBean` requires a factory method compatible with the bean being overridden.
11. The 6.2 APIs do not exist in older Spring Framework versions.
12. The Spring Boot BOM should manage compatible Spring Framework modules.

## 39. Workflow for Choosing the Right Tool

When dealing with multiple beans implementing the same interface:

1. Determine whether the consumer needs a single bean or a collection.
2. Determine whether there is a primary implementation or a true fallback.
3. Use `@Primary` if there is a preferred default.
4. Use `@Fallback` if an implementation should only be selected when no regular candidate exists.
5. Use `@Qualifier` if the consumer requires a specific implementation.
6. Use `defaultCandidate=false` for auxiliary beans that should not participate in default autowiring.
7. Use profile/property conditions if a bean should only exist in a given environment or configuration state.
8. Write context tests verifying both candidate counts and the bean received by the consumer.
9. Use `@MockitoBean`, `@MockitoSpyBean`, or `@TestBean` for test isolation, but do not override the bean whose selection is under test.
10. Verify that the actual Spring Framework version supports the APIs you are using.

## 40. Hands-On Exercises

### Exercise A — Two Candidates and @Fallback

Create `PaymentGateway` with `RemotePaymentGateway` and `LocalPaymentGateway`. Mark local with `@Fallback`. Inject the interface into `CheckoutService`, then verify that remote is selected and both beans still exist.

### Exercise B — Only Fallback Remaining

Create a test context registering only `LocalPaymentGateway` marked with `@Fallback`. Verify that single-valued injection can receive the fallback bean when it is the only candidate.

### Exercise C — Multiple Regular Candidates

Register two `PaymentGateway` beans without primary, fallback, or qualifier. Observe the ambiguity error. Then try `@Primary` and `@Qualifier`, recording the differences.

### Exercise D — defaultCandidate=false

Create two `ApiClient` beans, marking the audit bean with `@Bean(defaultCandidate=false)`. Verify that the default consumer receives the general client and a consumer with `@Qualifier("audit")` receives the audit client.

### Exercise E — Fallback Combined with Profile

Create the remote bean only in `prod` and only when `payment.remote-enabled=true`; create a local fallback. Test each profile/property combination. Evaluate whether local fallback is actually safe when remote is unconfigured.

### Exercise F — Bean Parameter Name

Create two beans of the same type and a constructor parameter whose name matches one bean name. Enable the compiler option `-parameters`. Observe the behavior, and then add `@Qualifier` to express the dependency explicitly.

### Exercise G — @MockitoBean

Write a `@SpringBootTest` for `CheckoutService`, using `@MockitoBean` to replace `PaymentGateway`. Stub the result and verify the service. Then try enforcing override mode to guarantee the target bean exists.

### Exercise H — @MockitoSpyBean

Spy on an existing bean. Verify that a method is called when the service handles a request. Ensure the real method does not cause unintended network or database side effects.

### Exercise I — @TestBean

Create a `StubPaymentGateway` and a factory method in the test class. Use `@TestBean` to replace the production bean. Compare test readability with a Mockito mock.

### Exercise J — Checking Compatibility

Inspect your project's dependency tree and identify the resolved versions of `spring-context` and `spring-test`. Verify whether those versions support `@Fallback`, `defaultCandidate`, `@MockitoBean`, and `@TestBean`.

## 41. Key Takeaways

1. `@Fallback` was introduced in **Spring Framework 6.2** to mark a fallback bean in autowiring candidate resolution.
2. When a regular candidate and a fallback candidate both exist for a single-valued injection, the regular candidate takes precedence.
3. If only one matching fallback candidate exists, Spring can select that fallback.
4. `@Fallback` does not create beans, does not replace profile/property conditions, and does not provide runtime failover.
5. `@Primary` expresses a preferred choice; `@Fallback` expresses a fallback choice.
6. `@Qualifier` is used when a consumer needs a specific bean.
7. `@Bean(defaultCandidate=false)` marks a bean as not being a default candidate, while keeping it in the context for explicit selection.
8. Parameter-name matching is a supplemental convenience; it requires parameter name metadata and should not replace qualifiers for important dependencies.
9. Spring Framework 6.2 provides `@TestBean`, `@MockitoBean`, and `@MockitoSpyBean` for bean overriding in Spring Test.
10. Mocks replace behavior; spies preserve real behavior unless stubbed; test bean factories provide custom implementations.
11. Do not mock the bean whose `@Fallback` or `@Primary` selection your test is trying to prove.
12. The Spring Boot BOM manages Framework versions; inspect resolved dependencies rather than looking only at starter versions.
13. Do not upgrade a single Spring Framework module without aligning related modules.
14. When upgrading, address `@MockBean`/`@SpyBean` deprecations according to the migration path for your Spring Boot release line.
15. Always test both bean inventory and the bean actually injected when candidate selection is an important contract.

**Core mindset:** `@Primary` answers “which bean is preferred?”, `@Fallback` answers “which bean should only be used when no regular choice exists?”, `@Qualifier` answers “which specific bean does the consumer need?”, and `defaultCandidate=false` answers “should this bean participate in default selection?”. The new test annotations provide controlled bean overrides in test contexts. Using each mechanism for its intended role makes Spring configuration clearer and easier to verify.
