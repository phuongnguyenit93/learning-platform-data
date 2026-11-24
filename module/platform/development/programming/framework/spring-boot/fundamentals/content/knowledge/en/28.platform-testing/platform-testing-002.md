# Testing Beans via Spring Context vs. Direct Object Instantiation

A Java class in a Spring Boot application is commonly annotated with `@Service`, `@Component`, `@Repository`, or registered via a `@Bean` method. Yet when writing tests, there are two very different approaches:

- **Create the object directly with `new`** and pass the required dependencies. This focuses on the class's Java logic without booting Spring.
- **Retrieve the bean from a Spring `ApplicationContext`**. This verifies bean registration, dependency injection, configuration, lifecycle, bean post-processors, or AOP proxies when those mechanisms are relevant.

Both are right in the appropriate situation. A class annotated with `@Service` is still an ordinary Java class and can be instantiated directly. However, `new SomeService()` **does not cause Spring to automatically run `@Autowired`, `@PostConstruct`, `@Transactional`, or `@ConfigurationProperties`**. Conversely, using `@SpringBootTest` for a simple calculation can make tests slow, harder to isolate, and pull in unrelated components.

**Core principle:** test objects directly when verifying algorithms and business rules; use a Spring context when what you need to verify lies in how **Spring creates, configures, or intercepts the bean**.

This lesson builds a running example around a shipping fee service, writes unit tests with fakes and Mockito, and then places the same service into a minimal Spring context, a Spring Boot context, and an MVC slice. Afterward, we examine common pitfalls: constructor/field injection, bean lifecycle, transaction proxies, conditional beans, profiles, caching, test isolation, and choosing the right test level.

## 1. A @Service class can be a plain object or a Spring bean

Suppose we have a rate lookup contract:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

public interface ShippingRateClient {
    BigDecimal rateFor(String city);
}
~~~

Service:

~~~java
package com.example.shipping;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class ShippingQuoteService {

    private final ShippingRateClient rateClient;

    public ShippingQuoteService(ShippingRateClient rateClient) {
        this.rateClient = Objects.requireNonNull(rateClient);
    }

    public BigDecimal quote(String city) {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException(
                    "city must not be blank"
            );
        }

        return rateClient.rateFor(city)
                .add(new BigDecimal("2.00"));
    }
}
~~~

`ShippingQuoteService` works both for Spring and as a standalone Java class:

- `@Service` allows component scanning to register the class as a bean.
- The public constructor lets any Java caller supply `ShippingRateClient`.
- The `quote` method contains only Java logic and does not directly call `ApplicationContext`.
- A real integration adapter might fetch rates over HTTP; tests can substitute a fake or mock.

We need to separate two questions:

**Question 1:** Does `quote("Hue")` return the right price when the client returns 10.00? You only need to instantiate the object and call the method.

**Question 2:** Does Spring find the service and provide an appropriate `ShippingRateClient` bean? That requires testing with a context.

Passing Question 1 does not automatically prove Question 2; a context startup test passing also does not prove every pricing branch is correct.

## 2. How does a Spring bean differ from a directly instantiated Java object?

A plain object:

~~~java
ShippingRateClient client = ...;

ShippingQuoteService subject =
        new ShippingQuoteService(client);
~~~

A Spring-managed bean:

~~~java
ApplicationContext context = ...;

ShippingQuoteService subject =
        context.getBean(ShippingQuoteService.class);
~~~

When managing a bean, Spring may perform multiple steps:

~~~text
@ComponentScan / @Bean / auto-configuration
                    |
                    v
             Bean definition
                    |
                    v
       Bean creation + dependency resolution
                    |
                    v
    Property binding / post-processors / lifecycle
                    |
                    v
          AOP proxy if needed
                    |
                    v
          Bean used by the application
~~~

Those steps do not happen automatically during a `new` call.

### 2.1. When created directly

~~~text
JUnit test
    |
    +--> new FakeRateClient()
    |
    +--> new ShippingQuoteService(fake)
    |
    +--> quote("Hue")
    |
    +--> assertEquals(...)
~~~

The test controls exactly which dependency is used. There is no component scan, bean selection, or Boot auto-configuration.

### 2.2. When created via a Spring context

~~~text
Spring Test bootstrap
        |
        v
ApplicationContext
        |
        +--> Bean definitions
        +--> Dependency injection
        +--> Lifecycle callbacks
        +--> Configuration and conditions
        +--> Possible proxies
        |
        v
ShippingQuoteService bean
        |
        v
Test calls method and asserts
~~~

The biggest difference is whether **the container participates** in constructing the object and shaping observable behavior.

## 3. Comparison table of the two testing styles

| Aspect | Directly instantiated object | Spring context |
| --- | --- | --- |
| Subject created via | `new` / constructor / factory in test | Spring `ApplicationContext` |
| Must Spring be started? | No | Yes |
| Verifying business logic | Very well suited | Possible, though sometimes unnecessary |
| Constructor injection | Test passes dependencies manually | Spring resolves beans |
| `@Autowired` field/method | Not processed automatically | Processed when bean is properly managed |
| `@PostConstruct` | Does not run automatically | Runs when lifecycle infrastructure processes it |
| `@Transactional`, `@Cacheable` | No advice applied automatically | Can be applied when proxy/infrastructure is enabled |
| `@ConfigurationProperties` | Not bound automatically | Bound when class is properly registered |
| `@Profile` / bean conditions | Not evaluated automatically | Spring evaluates when processing bean definitions |
| `@Primary` / `@Qualifier` | Test chooses object directly | Spring selects bean by rules |
| Startup time | Usually very low | Depends on context size |
| External dependencies | Can be faked/mocked | Real beans may exist, requiring control |
| Errors primarily caught | Class logic and interactions with test doubles | Wiring, conditions, lifecycle, proxies, and bean-mediated behavior |

Do not turn this table into a mechanical rule that "any Spring means a heavy integration test." A Spring context might contain only two beans; conversely, a direct unit test can accidentally hit a database if you pass a real adapter.

## 4. Direct unit test with JUnit 5 and a fake

Create a fake client returning a fixed rate:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

final class FixedRateClient implements ShippingRateClient {

    private final BigDecimal rate;

    FixedRateClient(BigDecimal rate) {
        this.rate = rate;
    }

    @Override
    public BigDecimal rateFor(String city) {
        return rate;
    }
}
~~~

Write the test:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingQuoteServiceTest {

    @Test
    void addsHandlingFee() {
        ShippingRateClient fake =
                new FixedRateClient(new BigDecimal("10.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(fake);

        BigDecimal actual = subject.quote("Hue");

        assertEquals(new BigDecimal("12.00"), actual);
    }

    @Test
    void rejectsBlankCity() {
        ShippingRateClient fake =
                new FixedRateClient(new BigDecimal("10.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(fake);

        assertThrows(
                IllegalArgumentException.class,
                () -> subject.quote("  ")
        );
    }
}
~~~

### 4.1. Why doesn't this test need @SpringBootTest?

The subject is created via its constructor. Its dependency is a fake whose behavior is controlled by the test. `quote` does not need Spring to perform addition.

The test does not wait for an application context, nor does it require a database, HTTP server, or Spring Boot auto-configuration.

### 4.2. What does this test prove?

It verifies:

- The service calls the dependency to get the base rate.
- The handling fee is added correctly.
- Blank input is rejected according to contract.

### 4.3. What does this test not prove?

It does not verify:

- `@Service` is scanned.
- A valid `ShippingRateClient` bean exists in the application.
- Spring picks the right implementation when multiple candidates exist.
- Transactions, caching, or aspects are applied to the bean.
- Runtime configuration is bound properly.

This is an intentional boundary, not a flaw in unit testing.

## 5. Constructor injection makes both application and tests easier to write

A service depending on an interface:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal total(BigDecimal subtotal) {
        return subtotal.add(taxCalculator.taxFor(subtotal));
    }
}
~~~

In production, Spring can resolve the `TaxCalculator` bean. In a unit test, you simply pass an implementation:

~~~java
TaxCalculator fake =
        subtotal -> new BigDecimal("2.50");

InvoiceService subject = new InvoiceService(fake);
~~~

**Dependency injection is a design principle, not a container monopoly.** Calling a constructor with a dependency is a completely valid form of injection.

### 5.1. Field injection makes direct testing harder

~~~java
@Service
public class InvoiceService {

    @Autowired
    private TaxCalculator taxCalculator;

    public BigDecimal total(BigDecimal subtotal) {
        return subtotal.add(taxCalculator.taxFor(subtotal));
    }
}
~~~

If a test calls:

~~~java
InvoiceService subject = new InvoiceService();
subject.total(new BigDecimal("100.00"));
~~~

the `taxCalculator` field has not been injected by Spring and may be `null`. Adding `@Autowired` does not make Java automatically supply the dependency.

The preferred approach is constructor injection:

~~~java
public InvoiceService(TaxCalculator taxCalculator) {
    this.taxCalculator = taxCalculator;
}
~~~

### 5.2. Should reflection be used to set private fields in unit tests?

Usually there is no need. A test that relies heavily on reflective field injection can be a sign that the production class is hard to use independently. When you control the class design, constructor injection is typically simpler, type-safe, and clearer.

### 5.3. @Service does not prevent new

Even if a class has:

~~~java
@Service
public class ShippingQuoteService {
    // ...
}
~~~

a test can still call `new ShippingQuoteService(fake)`. The annotation has meaning to Spring when Spring processes the class; it does not turn the class into a Java type that cannot be directly instantiated.

## 6. Unit testing with Mockito without starting Spring

If you do not want to write a fake class, Mockito can create a dependency test double.

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ShippingQuoteMockitoTest {

    @Test
    void usesRateClientResult() {
        ShippingRateClient client =
                mock(ShippingRateClient.class);

        when(client.rateFor("Da Nang"))
                .thenReturn(new BigDecimal("15.00"));

        ShippingQuoteService subject =
                new ShippingQuoteService(client);

        assertEquals(
                new BigDecimal("17.00"),
                subject.quote("Da Nang")
        );

        verify(client).rateFor("Da Nang");
    }
}
~~~

Mockito does not need a Spring container here.

### 6.1. Fakes and mocks differ

A fake is a small implementation with real yet simplified behavior. A mock is a test double that can be stubbed and verified:

~~~java
when(client.rateFor("Hue"))
        .thenReturn(new BigDecimal("10.00"));

verify(client).rateFor("Hue");
~~~

There is no need to verify every implementation-detail call. Good tests focus on contracts and meaningful behavior, avoiding breaking on refactors that preserve outcomes.

### 6.2. MockitoExtension

JUnit Jupiter can integrate with Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ShippingWithMockitoExtensionTest {

    @Mock
    ShippingRateClient client;

    @InjectMocks
    ShippingQuoteService subject;

    @Test
    void calculatesQuote() {
        when(client.rateFor("Hue"))
                .thenReturn(new BigDecimal("10.00"));

        assertEquals(
                new BigDecimal("12.00"),
                subject.quote("Hue")
        );
    }
}
~~~

`@Mock` creates a Mockito mock and `@InjectMocks` assists in assembling the subject with matching mocks. They are **not** Spring's bean creation mechanism.

If the subject has a concise constructor, calling the constructor manually in the test is sometimes even clearer than `@InjectMocks`.

### 6.3. @Mock is not a Spring bean

A field:

~~~java
@Mock
ShippingRateClient client;
~~~

does not register a `ShippingRateClient` bean into the ApplicationContext. If a Spring context test needs to replace a bean with a mock, an appropriate Spring Test bean override must be used.

## 7. When must you use a Spring context?

Use a Spring context when the behavior being verified genuinely comes from the container:

- `@ComponentScan` finds the right components.
- `@Bean` factory methods register the right beans.
- Spring selects beans by type, `@Primary`, or `@Qualifier`.
- `@ConfigurationProperties` are bound and validated.
- `@Profile`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean` determine which beans exist.
- `@PostConstruct`, bean post-processors, or lifecycle callbacks execute.
- Spring AOP proxies apply transactions, caching, or advice.
- Spring Data generates repository implementations.
- Spring MVC configures controller mappings and message converters.
- Spring Boot auto-configuration creates beans based on dependencies and properties.

However, **using a Spring context does not automatically mean loading the entire application**. There are minimal contexts, test slices, application context runners, and full Boot contexts.

## 8. Small context with @SpringJUnitConfig

`@SpringJUnitConfig` comes from Spring Test and integrates a Spring context with JUnit Jupiter. It can load a very small test configuration.

~~~java
package com.example.shipping;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(ShippingContextTest.TestConfig.class)
class ShippingContextTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void springCreatesServiceAndInjectsDependency() {
        assertNotNull(service);

        assertEquals(
                new BigDecimal("12.00"),
                service.quote("Hue")
        );
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        ShippingRateClient rateClient() {
            return city -> new BigDecimal("10.00");
        }

        @Bean
        ShippingQuoteService shippingQuoteService(
                ShippingRateClient client) {
            return new ShippingQuoteService(client);
        }
    }
}
~~~

### 8.1. What steps does Spring perform?

Spring processes `TestConfig`, creates the `ShippingRateClient` bean, resolves the dependency of the `shippingQuoteService` factory method, creates `ShippingQuoteService`, and injects the service into the `@Autowired` test field.

This tests a **test-configured context** along with service behavior through the bean.

### 8.2. A small context does not prove production scanning

The example uses explicit `@Bean` methods rather than component scanning. It verifies that these two beans wire together properly, but **does not prove** that production component scanning finds `@Service` or that application auto-configuration is ready.

Include the relevant configuration in the test corresponding to whatever target you need to verify.

### 8.3. @SpringJUnitConfig vs. @ContextConfiguration

You can declare the equivalent explicitly:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ShippingContextTest {
}
~~~

`@SpringJUnitConfig` is a convenient composed annotation. With JUnit 5, appropriate Spring Test and JUnit Jupiter dependencies are required.

### 8.4. Context tests can inject into parameters

~~~java
@SpringJUnitConfig(ShippingTestConfiguration.class)
class ShippingInjectionTest {

    @Test
    void canInjectTestMethodParameter(
            @Autowired ShippingQuoteService service) {
        assertNotNull(service);
    }
}
~~~

`ShippingTestConfiguration` is a test configuration that must be defined in the project. `SpringExtension` resolves the parameter from the test ApplicationContext.

## 9. @Autowired in tests does not work automatically with plain JUnit

The following test is not enough:

~~~java
class PlainJUnitTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void works() {
        service.quote("Hue");
    }
}
~~~

JUnit Jupiter does not automatically activate Spring dependency injection simply upon seeing `@Autowired`. If the test does not use the appropriate Spring Test extension or bootstrap, the field may remain `null`.

Distinguish between:

- `@Autowired` on a Spring bean is processed by Spring when creating the bean.
- `@Autowired` on a test class is processed by Spring Test infrastructure when the test is integrated with Spring.
- Without a Spring context, instantiate the subject and its dependencies manually via constructor.

### 9.1. Do not treat successful autowiring as the whole test

A test containing only:

~~~java
assertNotNull(service);
~~~

checks for bean presence, but does not prove the service returns the right result for business inputs.

Tests should pose a clear question and assert accordingly, not merely check that "the context had no errors."

## 10. @SpringBootTest: when a more realistic Spring Boot application is needed

`@SpringBootTest` typically loads a Boot application context based on the main application configuration.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ShippingApplicationTest {

    @Autowired
    ShippingQuoteService service;

    @Test
    void createsShippingService() {
        assertThat(service).isNotNull();
    }
}
~~~

Spring Boot Test typically searches up the package hierarchy for a class annotated with `@SpringBootApplication` or `@SpringBootConfiguration`. You can also specify it explicitly:

~~~java
@SpringBootTest(classes = ShippingApplication.class)
~~~

`ShippingApplication` is the actual application configuration class provided in the project.

### 10.1. Does @SpringBootTest always open an HTTP server?

No. The default value of `webEnvironment` is `MOCK`. For an appropriate web application, tests can use a mock servlet environment **without starting a real HTTP server**.

If a real HTTP server on a random port is desired:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShippingHttpIntegrationTest {
}
~~~

Testing over real HTTP verifies networking, serialization, filter, and transaction boundaries that differ from invoking Java methods directly.

### 10.2. Context loads is not a full functional test

~~~java
@SpringBootTest
class ContextLoadsTest {

    @Test
    void contextLoads() {
    }
}
~~~

This test confirms that the application context starts cleanly under the test configuration in use. It does not prove that all endpoints, database queries, external integrations, or business rules work properly.

### 10.3. Why not use @SpringBootTest for every unit test?

A large context can load hundreds of beans, auto-configurations, database connections, security filters, startup runners, and integration adapters. This increases execution time and complexity when a test fails.

Reserve the full context for when you genuinely need to test how those components wire together.

## 11. Simulating external dependencies when testing with a Spring context

In a real application, `ShippingRateClient` might be an HTTP adapter calling a pricing service.

If a test uses a full context without wanting to make external network calls, the real bean must be replaced with a fake or mock **at the context level**.

There are three mental models:

1. Use a mock bean override to replace the Spring bean in tests.
2. Import a test configuration containing a fake bean with explicit override options.
3. Run a local test HTTP server or Testcontainers when real integration testing is needed.

Avoid letting a test accidentally call a production API because the context scanned the real adapter.

### 11.1. Spring Test @MockitoBean

In supported Spring Framework versions, use:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

Example:

~~~java
@SpringBootTest
class ShippingWithMockBeanTest {

    @MockitoBean
    ShippingRateClient rateClient;

    @Autowired
    ShippingQuoteService service;

    @Test
    void usesClientMockFromContext() {
        when(rateClient.rateFor("Hue"))
                .thenReturn(new BigDecimal("10.00"));

        assertThat(service.quote("Hue"))
                .isEqualByComparingTo("12.00");
    }
}
~~~

`@MockitoBean` instructs Spring Test to replace or create the corresponding mock bean in the test context according to the annotation's override rules. When Spring creates `ShippingQuoteService`, the injected dependency is the mock provided by the test context.

Depending on the version and configuration, strict replacement can be required instead of automatically creating a bean if one does not already exist.

### 11.2. Spring Boot @MockBean in older projects

In many older Spring Boot projects, you will see:

~~~java
@MockBean
ShippingRateClient rateClient;
~~~

Spring Boot's `@MockBean` is a test context bean replacement mechanism, **unlike** Mockito's `@Mock`. In newer Boot lines, this API is deprecated in favor of `@MockitoBean` when paired with a compatible Spring Framework version.

Check the project version before changing imports or annotations. Do not assume every Boot project supports `@MockitoBean`.

### 11.3. Comparison table

| Annotation | Processed by | Replaces Spring bean? |
| --- | --- | --- |
| `@Mock` | Mockito | Not automatically |
| `@InjectMocks` | Mockito | No, only helps assemble the subject |
| `@MockitoBean` | Supported Spring Test versions | Yes |
| `@MockBean` | Supported Spring Boot Test lines | Yes |

**A Mockito mock on a test field does not automatically become a Spring bean.** If the goal is to verify that Spring injects the mock dependency into the service, use the proper bean override mechanism.

## 12. Test slices: you don't only have to choose between new and full context

Spring Boot offers test slices focused on a single framework layer:

- `@WebMvcTest`: controllers and related Spring MVC components.
- `@DataJpaTest`: JPA repositories, entity mapping, and persistence.
- `@JdbcTest`: JDBC.
- `@JsonTest`: Jackson/JSON mapping.
- `@RestClientTest`: testing HTTP clients within an appropriate scope.

A slice does not load all business services like a full context does, except for components intentionally brought in by the test or auto-configuration.

### 12.1. @WebMvcTest example

Controller:

~~~java
@RestController
@RequestMapping("/api/shipping")
public class ShippingController {

    private final ShippingQuoteService service;

    public ShippingController(ShippingQuoteService service) {
        this.service = service;
    }

    @GetMapping
    public QuoteResponse quote(@RequestParam String city) {
        return new QuoteResponse(service.quote(city));
    }

    public record QuoteResponse(BigDecimal amount) {
    }
}
~~~

Test:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ShippingController.class)
class ShippingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ShippingQuoteService service;

    @Test
    void returnsQuoteAsJson() throws Exception {
        when(service.quote("Hue"))
                .thenReturn(new BigDecimal("12.00"));

        mockMvc.perform(
                get("/api/shipping").param("city", "Hue")
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.amount").value(12.0));
    }
}
~~~

The example assumes the Boot/Spring Test version supports the annotation used and has appropriate JSON conversion configured.

### 12.2. What does this test actually verify?

It verifies HTTP mapping, query parameters, controller invocation, and the JSON response contract. Because `ShippingQuoteService` is mocked, this test **does not verify the pricing calculation algorithm**.

That is why a separate unit test for `ShippingQuoteService` is needed.

### 12.3. @DataJpaTest checks what new cannot fully simulate

Spring Data JPA repositories are typically interfaces whose implementations/proxies are generated by the framework at runtime. Calling `new` directly on a repository interface is impossible.

An appropriate `@DataJpaTest` verifies entity mapping, repository queries, and database behavior in a test environment. Results depend on the database type, transaction manager, and how the data slice is configured.

### 12.4. @JsonTest

If the goal is Jackson serialization and modules/converters configured by Boot, `@JsonTest` makes sense. If you only want to test a Java string-concatenation method, a JSON test slice is unnecessary.

## 13. ApplicationContextRunner: testing bean conditions and auto-configuration

`ApplicationContextRunner` builds a small context, supplies properties and bean definitions, and inspects the result.

Example configuration:

~~~java
import java.math.BigDecimal;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RateClientConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.shipping",
            name = "enabled",
            havingValue = "true"
    )
    ShippingRateClient shippingRateClient() {
        return city -> new BigDecimal("10.00");
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class RateClientConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            RateClientConfiguration.class
                    );

    @Test
    void registersBeanWhenEnabled() {
        runner.withPropertyValues("app.shipping.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(ShippingRateClient.class);
                });
    }

    @Test
    void omitsBeanWhenDisabled() {
        runner.withPropertyValues("app.shipping.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(ShippingRateClient.class);
                });
    }
}
~~~

### 13.1. Why is calling the factory method directly off-target?

~~~java
RateClientConfiguration config =
        new RateClientConfiguration();

ShippingRateClient client =
        config.shippingRateClient();
~~~

The plain Java call above still returns a client even if `app.shipping.enabled=false`, because `@ConditionalOnProperty` is not an `if` statement inside the Java method. Spring only evaluates the condition when processing bean definitions.

### 13.2. Testing library-provided auto-configuration

Auto-configurations can be supplied to the runner:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyAutoConfiguration.class)
        );
~~~

`MyAutoConfiguration` is an auto-configuration class defined by the project. This is a focused way to test `@ConditionalOnMissingBean`, property conditions, and back-off behavior without loading the entire application.

## 14. Bean lifecycle: @PostConstruct and @PreDestroy

A bean may have initialization and destruction callbacks:

~~~java
@Component
public class CacheIndex {

    private boolean initialized;

    @PostConstruct
    public void initialize() {
        initialized = true;
    }

    @PreDestroy
    public void close() {
        initialized = false;
    }

    public boolean isInitialized() {
        return initialized;
    }
}
~~~

In Spring Boot 3+, these annotations are typically imported from:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

### 14.1. Object created with new

~~~java
CacheIndex index = new CacheIndex();
assertFalse(index.isInitialized());
~~~

The `initialize` method is not invoked automatically. If a unit test wants to verify the method's logic, it can call the method explicitly, though that does not prove Spring executed the lifecycle.

### 14.2. Bean created via context

In a Spring context with appropriate bean lifecycle infrastructure, once the bean is initialized:

~~~java
CacheIndex index = context.getBean(CacheIndex.class);
assertTrue(index.isInitialized());
~~~

When the context closes, Spring can invoke the bean's destroy callback according to its scope and lifecycle semantics.

### 14.3. Not every bean is created immediately at context startup

Lazy, prototype, or custom-scoped beans have their own creation and destruction timing. Verify the specific scope and timing needed rather than assuming all beans are created at startup.

## 15. Spring AOP proxies: @Transactional and @Cacheable

A method:

~~~java
@Service
public class PaymentService {

    @Transactional
    public void charge(String paymentId) {
        // ...
    }
}
~~~

does not automatically start a transaction when called via:

~~~java
PaymentService service = new PaymentService();
service.charge("p-1");
~~~

Spring transactions are generally applied through appropriate infrastructure and proxies. Creating an object with `new` bypasses that layer.

Similarly:

~~~java
@Cacheable("products")
public Product findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

is not automatically cached when called on a plain object, unless a separate mechanism has been configured and applied.

### 15.1. When should you test through a context?

To verify transaction boundaries, commit/rollback, caching, or actual aspect advice, you need a context with the appropriate infrastructure and must invoke the method through the bean/proxy.

### 15.2. Self-invocation remains a limitation

Even when the subject is a Spring bean:

~~~java
@Service
public class PaymentWorkflow {

    public void process() {
        save(); // this.save()
    }

    @Transactional
    public void save() {
        // ...
    }
}
~~~

the internal call `this.save()` typically does not pass through the Spring AOP proxy and may bypass transaction advice for that method. Adding `@SpringBootTest` does not automatically fix self-invocation design issues.

### 15.3. Direct tests remain useful for pure logic

If `PaymentService` has a fee-calculation method that does not require a transaction, you can test that logic on a directly instantiated object. Having `@Transactional` somewhere in a class does not mean every method requires an integration test.

## 16. @ConfigurationProperties and @Value: new does not perform binding

Record:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(
        String region,
        Duration timeout
) {
}
~~~

If a test calls:

~~~java
ShippingProperties properties =
        new ShippingProperties(
                "vn-central",
                Duration.ofSeconds(2)
        );
~~~

this is a Java object with values **passed directly by the test**, not values read from `Environment` by the Binder.

To verify that `app.shipping.timeout=2s` binds to a `Duration`, you need a test using the Spring Binder with the configuration properties bean properly registered, such as via `@EnableConfigurationProperties`.

### 16.1. Separate the two goals

**Test the consumer:** construct a `ShippingProperties` directly and pass it to the service. The goal is verifying how the service uses config values.

**Test binding:** provide a property source, obtain the bean from the context, and verify type conversion, defaults, nested fields, and validation.

Both are valuable and do not replace each other.

### 16.2. @Value does not inject on new

~~~java
@Component
public class LegacyShippingClient {

    @Value("${app.shipping.region}")
    private String region;
}
~~~

Calling `new LegacyShippingClient()` does not populate `region`. This is why constructor injection or a typed configuration-properties object usually makes unit tests easier to write.

### 16.3. Properties classes must be registered

Annotating a class with `@ConfigurationProperties` may not be enough by itself to create a bean. When testing via a context, `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or an equivalent bean registration path is required.

If the context lacks the properties bean, check how it is registered before editing property names in YAML.
## 17. @Profile and conditional bean registration

Suppose the application has an adapter for the development environment:

~~~java
@Configuration(proxyBeanMethods = false)
public class ShippingConfiguration {

    @Bean
    @Profile("dev")
    ShippingRateClient developmentClient() {
        return city -> new BigDecimal("5.00");
    }
}
~~~

In a Spring context with the `dev` profile, this bean can be registered. When the profile does not match, Spring does not register the bean from that factory method.

Yet if a test calls:

~~~java
ShippingConfiguration config =
        new ShippingConfiguration();

ShippingRateClient client =
        config.developmentClient();
~~~

Java still executes the method normally. `@Profile` is not an `if` statement inside the Java method.

### 17.1. @ActiveProfiles

When testing through a Spring Test context, you can choose profiles:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ShippingTestProfileIntegrationTest {
}
~~~

The `@ActiveProfiles` annotation affects the Spring test context's active profiles. In plain JUnit tests without Spring Test infrastructure, that annotation does not alter how `new` objects behave.

### 17.2. @ConditionalOnMissingBean

Example:

~~~java
@Bean
@ConditionalOnMissingBean(ShippingRateClient.class)
ShippingRateClient defaultRateClient() {
    return city -> new BigDecimal("8.00");
}
~~~

A Spring Boot condition lets the default bean back off when another implementation has already been registered at the appropriate time.

If you call `defaultRateClient()` directly, Java has no knowledge of what beans exist in a context. To test back-off behavior, use `ApplicationContextRunner` or an appropriate context test.

### 17.3. Do not turn tests into production profile logic

Check bean composition and configuration at environment boundaries, but do not put logic like:

~~~java
if (isRunningUnitTest) {
    // ...
}
~~~

inside business services. Separating external dependencies behind interfaces and passing appropriate implementations is much cleaner.

## 18. Multiple beans for the same interface: @Primary and @Qualifier

Suppose the system has two implementations:

~~~java
@Component("standardRateClient")
public class StandardRateClient implements ShippingRateClient {
    // ...
}
~~~

~~~java
@Component("expressRateClient")
public class ExpressRateClient implements ShippingRateClient {
    // ...
}
~~~

A constructor like:

~~~java
public ShippingQuoteService(ShippingRateClient client) {
    this.rateClient = client;
}
~~~

can become ambiguous if Spring finds multiple candidates without clear selection rules.

Spring provides mechanisms such as:

- `@Primary` to prefer a default bean.
- `@Qualifier` to specify a candidate by qualifier.
- Other container dependency resolution rules.

### 18.1. Direct tests select dependencies in Java

~~~java
ShippingRateClient fake =
        city -> new BigDecimal("10.00");

ShippingQuoteService subject =
        new ShippingQuoteService(fake);
~~~

There is no bean ambiguity issue here. The test explicitly specifies the object to pass.

### 18.2. Context tests can catch real wiring errors

If the production context fails to start because two `ShippingRateClient` beans exist while the service requires a single one, a test using only `new ShippingQuoteService(fake)` will not detect that error.

Maintain a context test that exercises the real configuration or a representative subset of production bean definitions.

### 18.3. @Qualifier is not an object-selection mechanism in unit tests

`@Qualifier` has meaning for Spring injection. When a test invokes a constructor with an argument directly, the annotation is not needed to decide which object is passed.

## 19. Bean scopes and shared state across tests

Spring beans have scopes. Singleton is the common default; prototype creates a new instance on requests according to scope rules.

### 19.1. Directly instantiated objects

~~~java
Counter first = new Counter();
Counter second = new Counter();
~~~

These are two distinct objects because the test called `new` twice. That proves nothing about any Spring scope.

### 19.2. Beans retrieved from a Spring context

~~~java
Counter first = context.getBean(Counter.class);
Counter second = context.getBean(Counter.class);

assertThat(first).isSameAs(second);
~~~

If `Counter` is registered as a singleton, the assertion typically holds.

If the bean is prototype-scoped and requested twice, two distinct instances can be expected.

### 19.3. Stateful singletons cause tests to interfere with one another

Example:

~~~java
@Service
public class CounterService {

    private int count;

    public int increment() {
        return ++count;
    }
}
~~~

If the context is reused across test methods and the counter is not reset, a later test may observe an unexpected `count`.

Direct unit tests that call `new CounterService()` in each method generally start with fresh instance state, though they can still be affected by static fields or external storage.

**Test independence depends on actual state**, not merely whether an `ApplicationContext` is present.

### 19.4. Do not use @DirtiesContext to mask every shared-state issue

If a bean holds state used in tests, consider resetting it via a test API or redesigning the state. `@DirtiesContext` can be necessary in certain cases, but overusing it forfeits the benefits of context caching.

## 20. What are the limits of @Transactional and rollback on tests?

Spring Test supports running certain tests inside a transaction when appropriate Spring transaction infrastructure is present.

Example repository test:

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrder() {
        OrderEntity order = new OrderEntity();
        // Set up entity then persist/assert...
    }
}
~~~

In suitable data test slices, Spring Boot / Spring Test can open a transaction for the test and roll it back after the method completes. However, do not assume **every** external side effect will be rolled back.

### 20.1. Test transactions do not span every thread

If a test starts a real HTTP server:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

requests may be handled on a different thread using a different transaction. A transaction wrapping the test method does not automatically roll back changes committed by the server request.

### 20.2. Brokers, emails, and HTTP calls do not roll back with the database transaction

Even when the database rolls back, an email sent or a message published to a broker may still exist. Tests need to control these boundaries using fakes, sandboxes, transaction-aware patterns, or dedicated cleanup.

### 20.3. new does not enable transactions

If a service is created with `new` and a `@Transactional` method is called, no Spring transaction interceptor appears. A direct test can verify the logic inside the method, but cannot verify transaction boundaries.

## 21. Spring TestContext caching: the context does not restart for every test method

Spring Test has an **ApplicationContext cache** that allows multiple tests to reuse a context if their configurations produce an equivalent cache key.

This means:

~~~text
10 test methods
    |
    +--> Not necessarily 10 context startups
    |
    +--> Suitable contexts can be reused
~~~

Factors such as test configuration, profiles, property sources, mock bean overrides, and customizers affect whether tests share a context.

### 21.1. @DirtiesContext

~~~java
@DirtiesContext
@SpringBootTest
class MutatingContextTest {
}
~~~

`@DirtiesContext` instructs Spring Test to mark the context as dirty so it is not reused as before from the cache.

Use it when a test genuinely alters context state in a way that cannot be safely cleaned up. Do not apply it to all test classes "just to be safe," as context restarts can increase dramatically.

### 21.2. Isolating external state

Whether a context is cached does not determine:

- Whether the database was cleaned up.
- Whether a Redis cache retains data from an earlier test.
- Whether system properties were restored.
- Whether tests share the same temp directory or output file.
- Whether an external service stub had its interaction history reset.

A fast test suite that is sensitive to execution order is still unreliable.

### 21.3. Mock beans and context reuse

Mock bean definitions are part of the test context configuration. Using different sets of mock overrides results in different contexts, affecting caching.

Therefore, avoid mocking every bean for a test that only checks a calculation. Using a direct unit test is usually simpler and avoids creating unnecessary context variants.

## 22. Choosing the test level based on cost and behavior to verify

You can picture a spectrum of options:

~~~text
                 Test isolated logic
                           |
                           v
                 JUnit + new + fake
                           |
                           v
                    JUnit + Mockito
                           |
                           v
            @SpringJUnitConfig (small context)
                           |
                           v
          ApplicationContextRunner (conditions)
                           |
                           v
              @WebMvcTest / @DataJpaTest ...
                           |
                           v
               @SpringBootTest (context)
                           |
                           v
    @SpringBootTest(RANDOM_PORT) + real dependencies
                           |
                           v
            Test integration across boundaries
~~~

The ordering in the diagram is only a guide. Actual execution time depends on context size, caching, build setup, startup runners, databases, containers, and CI infrastructure. Not every slice test is heavier than every `ApplicationContextRunner` test.

### 22.1. Why do small tests usually give faster feedback?

A unit test instantiating a few objects needs no Spring bootstrap and is less affected by unrelated dependencies. When a calculation is wrong, the failure points straight to the logic branch.

### 22.2. Why are context tests still necessary?

A service can be correct line-by-line in Java yet the app can fail to run due to:

- A missing bean candidate.
- A wrong profile or conditional property.
- Configuration properties failing to bind properly.
- Wrong entity mappings or JPA queries.
- Transaction advice not being applied.
- Incorrect security filter chain or MVC mappings.

You cannot eliminate integration or context tests simply by increasing the number of unit tests.

### 22.3. Do not overload one test with every goal

A full `@SpringBootTest` that calculates fees, sends HTTP, writes to a database, and checks emails can catch end-to-end issues, but when it fails it is harder to narrow down.

A balanced design usually has many unit tests for logic branches, context/slice tests for wiring and framework behavior, and a number of integration tests for primary flows.

## 23. One feature, multiple testing questions

For `ShippingQuoteService`, you might organize tests as:

~~~text
src/test/java/com/example/shipping/
├── ShippingQuoteServiceTest.java
├── ShippingQuoteMockitoTest.java
├── ShippingContextTest.java
├── ShippingControllerTest.java
├── RateClientConfigurationTest.java
└── ShippingApplicationSmokeTest.java
~~~

| Test class | Boundary | What is being verified |
| --- | --- | --- |
| `ShippingQuoteServiceTest` | Direct object + fake | Calculation and validation |
| `ShippingQuoteMockitoTest` | Direct object + Mockito | Interactions with client |
| `ShippingContextTest` | Small Spring context | Bean definitions/wiring |
| `ShippingControllerTest` | MVC slice | URL mapping, parameters, JSON |
| `RateClientConfigurationTest` | Context runner | Conditional bean registration |
| `ShippingApplicationSmokeTest` | Boot context | Application startup with test config |

Not every project needs all six test classes. The table merely shows how to separate questions so a single confusing test does not try to do too much.

### 23.1. Name tests after behavior

Examples:

~~~java
void rejectsBlankCity()
void registersRateClientOnlyWhenEnabled()
void returnsQuoteAsJson()
void startsWithTestProfile()
~~~

Names that describe the question are much clearer than `test1` or `everythingWorks`.

### 23.2. Do not re-test the entire algorithm in the controller slice

If service logic is already covered across branches by unit tests, the controller slice can mock the service and verify only the HTTP contract. That is not an omission; it avoids duplicating tests at the wrong layer.

### 23.3. An end-to-end test is still valuable

For critical business flows, an integration test going from HTTP through the service to the database confirms the layers connect. However, it should complement rather than replace fast isolated tests.

## 24. Verifying bean registration instead of just assertNotNull

If you want to verify there is **exactly one** bean of a given type:

~~~java
Map<String, ShippingRateClient> beans =
        context.getBeansOfType(ShippingRateClient.class);

assertThat(beans).hasSize(1);
~~~

If you want to verify bean identity:

~~~java
ShippingQuoteService first =
        context.getBean(ShippingQuoteService.class);

ShippingQuoteService second =
        context.getBean(ShippingQuoteService.class);

assertThat(first).isSameAs(second);
~~~

For a singleton bean, the same context typically returns the same instance/proxy.

If you want to check for a proxy:

~~~java
boolean proxied = AopUtils.isAopProxy(
        context.getBean(PaymentService.class)
);
~~~

`AopUtils` helps identify a Spring AOP proxy, though **it does not prove a specific advice ran**. To verify advice, perform a real call and assert the expected result or side effect.

### 24.1. Test bean names and qualifiers when they truly matter

If a consumer injects a bean by qualifier, the test should use a configuration with the right number of candidates to exercise the selection. Do not build a context with only one candidate and conclude `@Qualifier` has been verified.

### 24.2. Watch out for test-specific beans masking production errors

If tests always register:

~~~java
@Bean
ShippingRateClient rateClient() {
    return city -> BigDecimal.TEN;
}
~~~

tests may pass even if production has no real adapter. When verifying production wiring, at least one test must use a representative set of production bean definitions with appropriately controlled external environments.

## 25. Handling external dependencies in integration tests

A context test can trigger:

- Database connection pools.
- HTTP clients.
- Message consumers/producers.
- Caches and Redis connections.
- Scheduled tasks.
- Startup runners.
- Security-related initialization.

To keep tests reliable:

1. **Never use production endpoints or real credentials** as test defaults.
2. Use test profiles and dedicated configuration.
3. Stub/mock boundaries outside the scope under test.
4. For database/broker integrations, use an isolated test environment such as a test database or Testcontainers when appropriate.
5. Clean up data after tests and manage transaction semantics.
6. Configure timeouts so tests do not hang indefinitely when external dependencies are unreachable.
7. Avoid making tests depend on execution order.
8. Document clearly which dependencies are real and which are doubles.

### 25.1. Mocking too much can also make a test meaningless

If the goal is to verify HTTP client configuration but you mock that client, the test no longer verifies serialization, URLs, headers, or network behavior.

Mock **outside the boundary being tested**, not the very component the test is meant to prove.

### 25.2. Do not let startup runners cause hard-to-control side effects

A full Boot context can invoke `ApplicationRunner` or `CommandLineRunner`. If a runner loads data, creates files, or calls external systems, tests may experience side effects right at startup.

Design startup logic to be idempotent, configurable, or have dependencies separated so test contexts can control it.

## 26. Common mistakes in direct tests

### 26.1. @Autowired field is null

**Cause:** an object created with `new` bypasses the container.

**Fix:** use constructor injection and pass fakes/mocks; if testing injection itself, use a context test.

### 26.2. @PostConstruct does not run

**Cause:** a Java constructor does not automatically invoke Spring lifecycle callbacks.

**Fix:** test lifecycle via a context; unit tests can call the initialization method explicitly if only checking that method's logic.

### 26.3. @Transactional does not start a transaction

**Cause:** there is no transaction interceptor or proxy.

**Fix:** use a bean in a context with an appropriate transaction manager to verify transaction behavior.

### 26.4. @Cacheable does not cache

**Cause:** the annotation alone does not apply cache advice on objects created with `new`.

**Fix:** test caching via a proxy and appropriate cache infrastructure; test pure logic separately.

### 26.5. Conditional annotations do not apply

**Cause:** `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, and `@Profile` are evaluated by the container during the registration phase, not when Java directly calls a method.

**Fix:** use a context runner or a Spring context with explicit properties/profiles.

### 26.6. Direct tests pass yet the application still fails to start

**Cause:** Java logic is valid, but production bean wiring, properties, or auto-configuration is misconfigured.

**Fix:** add a context smoke test or targeted configuration test. There is no need to discard existing unit tests.

### 26.7. Fakes do not reflect the full contract

**Cause:** the fake always returns a clean value, whereas the real adapter encounters errors, timeouts, null/missing data, or complex formats.

**Fix:** add reasonable error branches to unit tests; use integration tests to verify the real adapter at its own boundary.

## 27. Common mistakes in Spring context tests

### 27.1. @SpringBootTest cannot find application configuration

**Cause:** the test is outside the appropriate package hierarchy or no configuration class was specified.

**Fix:** place the test in an appropriate package or use `@SpringBootTest(classes = Application.class)`.

### 27.2. Multiple beans of the same type cannot resolve dependency

**Cause:** ambiguous candidates.

**Fix:** check `@Primary`, `@Qualifier`, profile/conditional registration, and intended application configuration.

### 27.3. @WebMvcTest is missing a service bean

**Cause:** the MVC slice does not load all business services.

**Fix:** provide a mock bean in the test context or import the needed configuration rather than automatically switching to full `@SpringBootTest`.

### 27.4. @Mock does not replace a Spring bean

**Cause:** the mock is only a field on the test instance, not a BeanDefinition or bean override.

**Fix:** use `@MockitoBean` or `@MockBean` depending on supported version, or configure an explicit fake bean.

### 27.5. Context takes too long to start

**Cause:** using a full context for a narrow problem, slow external dependencies, or startup runners unsuitable for tests.

**Fix:** use direct tests, small contexts, slices, or runners depending on the goal; avoid loading unnecessary components.

### 27.6. @DirtiesContext slows down the entire suite

**Cause:** many contexts are evicted from the cache and must be rebuilt.

**Fix:** clean up state, leverage transaction rollbacks at proper boundaries, or mark dirty only when genuinely necessary.

### 27.7. Tests pass but deployment fails

**Potential causes:** tests use properties, mocks, or profiles different from production; real infrastructure was not tested.

**Fix:** state boundaries clearly in test names and docs, and add smoke/integration tests using deployment-representative configurations.

### 27.8. Tests are order-dependent

**Cause:** shared singleton state, static fields, database, cache, or external stubs not reset.

**Fix:** isolate and clean up state; do not rely on test method execution order.

### 27.9. A proxy exists but advice still does not run

**Cause:** mismatched pointcut, `final`/`private` method, self-invocation, or callers bypassing the proxy.

**Fix:** inspect the actual bean, `AopUtils`, pointcuts, and call paths; verify advice via observable behavior.

### 27.10. Tests unintentionally open a real server

**Cause:** using `RANDOM_PORT` or `DEFINED_PORT` when only controller mapping is needed.

**Fix:** use `@WebMvcTest` + `MockMvc` or an appropriate mock web context.

## 28. Test dependencies and run commands

Spring Boot projects typically use the test starter.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Depending on the Spring Boot major version, test starter organization and annotations may vary. Use dependencies and imports matching your project's version.

### 28.1. Pure unit tests do not depend on the Spring Test runtime

If a test only calls `new`, JUnit and Mockito may suffice. A Boot project may already have Spring Test via the starter, yet tests are not required to start Spring.

### 28.2. Running tests

With Maven:

~~~bash
mvn test
~~~

With Gradle:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

These are commands learners can run in a properly configured project; the lesson does not require running a build to prove each snippet.

## 29. Workflow for choosing a test type by goal

Before writing test annotations, answer the following questions:

1. **What is the behavior?** An algorithm, validation, HTTP mapping, wiring, transaction, or configuration?
2. **Does the behavior need a container?** If not, prefer JUnit + `new`.
3. **Can dependencies be passed via constructor?** If so, fakes/mocks are easy to use.
4. **Do you need to verify bean definitions or lifecycle?** Use `@SpringJUnitConfig` or an appropriate small context.
5. **Do you need to verify auto-configuration or conditions?** Use `ApplicationContextRunner`.
6. **Do you need to verify a framework slice?** Use `@WebMvcTest`, `@DataJpaTest`, or the relevant slice.
7. **Do you need to verify Boot application startup?** Use `@SpringBootTest`.
8. **Do you need a real HTTP server or real database/broker?** Use integration tests with isolated test infrastructure.
9. **Is there state or side effects?** Design rollback, reset, or cleanup.
10. **Do the assertions protect the right contract?** Do not assume `assertNotNull` suffices for every feature.

Decision diagram:

~~~text
             What needs to be tested
                    |
                    v
     Depends on the Spring container?
              /           \
            No            Yes
             |             |
             v             v
       JUnit + new    Need full Boot app?
       + fake/mock        /        \
                        No         Yes
                         |          |
                         v          v
                 Small context/  @SpringBootTest
                 runner/slice
                         \          /
                          \        /
                           v      v
                         Targeted
                         assertions
~~~

There is no single rigid rule for every team, yet every test should clarify what belongs to Java logic, what belongs to Spring configuration, and what represents integration with external systems.

## 30. Hands-on exercises

### Exercise A: Direct test for a @Service

Create `DiscountService` with a constructor taking a `DiscountPolicy` interface. Write tests computing discounts via a fake policy without using `@SpringBootTest`.

Check three price levels and one invalid input.

### Exercise B: Replace the fake with Mockito

Use `mock(DiscountPolicy.class)`, `when(...)`, and `verify(...)`. Compare the fake against the mock in terms of readability, reusability, and coupling to interaction details.

### Exercise C: Null @Autowired field

Create a service with an `@Autowired` field, try `new`, and call a method. Explain why the field was not injected.

Refactor to constructor injection and rewrite the test without Spring.

### Exercise D: Small Spring context

Create a `@Configuration` with two `@Bean` methods: a fake `DiscountPolicy` and a `DiscountService`.

Use `@SpringJUnitConfig` and `@Autowired` to call the service from the Spring context. Describe which beans Spring registered and resolved.

### Exercise E: @Mock and @MockitoBean

In a unit test, use Mockito `@Mock` and the subject's constructor.

In a Spring context test, use `@MockitoBean` or the bean override mechanism supported by your version. Observe the difference between a mock test field and a Spring mock bean.

### Exercise F: Conditional bean

Create:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.discount",
        name = "enabled",
        havingValue = "true"
)
DiscountPolicy discountPolicy() {
    return amount -> amount.multiply(
            new BigDecimal("0.10")
    );
}
~~~

Use `ApplicationContextRunner` to test `true`, `false`, and missing property values. Then call the method directly in Java and explain the difference.

### Exercise G: Lifecycle

Create a bean with an `initialized` field set inside `@PostConstruct`. Compare an object created via `new` with a bean in a Spring context that has appropriate lifecycle infrastructure.

### Exercise H: Proxy and transaction

Create a service with a `@Transactional` method and a repository test. Verify transaction behavior when invoked through the Spring bean.

Compare with a direct test that only verifies logic without assuming the annotation creates a transaction.

### Exercise I: MVC slice

Write a `GET /api/discount` controller depending on `DiscountService`. Use `@WebMvcTest`, mock the service bean, and verify HTTP status and JSON response.

Explain why the controller slice does not test the discount algorithm.

### Exercise J: Full context smoke test

Write a `@SpringBootTest` with a test profile and controlled dependencies. Verify the context starts, then list three important business behaviors **not proven** by an empty `contextLoads()` test.

### Exercise K: Context cache

Run two test classes with identical context configuration and observe startup logs. Try using `@DirtiesContext` in a test setup and explain its impact on context caching.

### Exercise L: Build a test matrix for a module

A module has a calculation service, REST controller, JPA repository, conditional bean, and external HTTP API. Choose the right test type for each boundary and explain why full `@SpringBootTest` should not be used for every calculation.

## 31. Self-check questions

**1. Can a class annotated with `@Service` be instantiated with `new`?**

Yes. It is still a Java class; the annotation only matters when Spring processes the class inside a context.

**2. Does constructor injection require Spring?**

No. Tests can pass objects, fakes, or mocks directly into the constructor.

**3. Why is an `@Autowired` field null in a direct test?**

Because Spring did not participate in creating the object, so it did not perform field injection.

**4. Does Mockito's `@Mock` automatically become a Spring bean?**

No. It does not automatically replace a bean in the ApplicationContext.

**5. What is `@MockitoBean` used for?**

In supported Spring Test versions, it overrides or provides a Mockito mock bean in the test context according to the annotation's rules.

**6. When should you use `@SpringJUnitConfig`?**

When you need a small Spring context with specified configuration/bean definitions without needing the full Boot application.

**7. Does `@SpringBootTest` always open a real HTTP server?**

No. By default it uses a mock web environment; `RANDOM_PORT` is used when a real HTTP server is needed under appropriate configuration.

**8. Why is `@WebMvcTest` typically missing business service beans?**

Because the MVC slice focuses on the web layer. Tests must mock or supply dependencies intentionally.

**9. Why doesn't calling a `@Bean` method directly apply `@ConditionalOnProperty`?**

Because Spring evaluates conditions when processing bean definitions; direct Java method invocation does not perform that evaluation.

**10. Does `@PostConstruct` run automatically after `new`?**

No. It is a lifecycle callback handled by Spring for managed beans.

**11. Does `@Transactional` on a directly instantiated object automatically open a transaction?**

No. Spring transactions generally require an interceptor/proxy and a suitable transaction manager.

**12. Does a Spring context always restart for each test method?**

No. The TestContext framework can cache and reuse contexts when configurations match.

**13. Should `@DirtiesContext` be placed on every context test?**

No. It reduces reuse and increases startup time; use it only when genuinely needing to invalidate the context.

**14. Does a direct test with a fake HTTP client prove the real external API works?**

No. It verifies service logic against the fake; HTTP integration requires its own test.

**15. When is `ApplicationContextRunner` especially suitable?**

When testing conditional bean registration, properties, and auto-configuration in a small context.

**16. Does a passing `contextLoads()` test prove all features work correctly?**

No. It only verifies that the context can start under test conditions; other behaviors need corresponding assertions.

## 32. Conclusion

Testing beans through a Spring context and testing directly instantiated objects **complement one another**. They answer two distinct sets of questions:

- **Directly instantiated objects:** is the Java logic right when dependencies are provided explicitly?
- **Spring context:** does the container register, select, inject, configure, and apply lifecycle/proxies to beans as expected?

For calculations, validation, and pure business rules, starting with JUnit, `new`, and fakes/mocks usually yields fast, readable, and easy-to-diagnose tests. Constructor injection makes this natural even when the class is a `@Service` in production.

When the target involves `@Autowired`, `@ConfigurationProperties`, bean conditions, `@PostConstruct`, Spring AOP, transactions, caching, or framework integration, choose an appropriate context. `@SpringJUnitConfig` and `ApplicationContextRunner` are well suited for small configurations; test slices such as `@WebMvcTest` and `@DataJpaTest` focus on individual layers; `@SpringBootTest` is meant for scenarios requiring a broader Boot application context.

A reliable test suite is defined not by the number of Spring annotations, but by **clear boundaries, controlled dependencies, and assertions verifying the exact behavior to protect**. Combining fast unit tests with intentional context and integration tests keeps a Spring Boot application adaptable while catching both logic defects and container configuration mistakes.
