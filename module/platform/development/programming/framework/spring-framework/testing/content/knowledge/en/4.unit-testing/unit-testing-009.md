# When Unit Testing Is Not Enough to Verify Spring Configuration

Unit testing verifies a class's logic under controlled conditions. However, a Spring application does not consist solely of Java objects invoked directly. Spring also instantiates objects, locates beans, injects dependencies, reads configuration, selects profiles, evaluates bean registration conditions, and creates proxies to deliver behaviors such as transactions, caching, security, or asynchronous execution.

When a test instantiates a class directly via its constructor and replaces dependencies with mocks, that test can prove the class's logic works, yet it does not prove Spring can assemble and run that class under the application's configuration. This marks an important boundary between **plain Java unit tests** and **tests with a Spring ApplicationContext**.

This lesson explains when unit testing is not enough, which configuration errors unit tests cannot catch, how to choose an appropriate Spring test scope, and how to keep the test suite fast while retaining reliable evidence about application configuration.

## 1. A Class Running Properly Does Not Mean the Spring Application Is Configured Properly

Suppose the application has a shipping fee service:

~~~java
@Service
public class ShippingService {

    private final ShippingPolicy policy;
    private final ShippingProperties properties;

    public ShippingService(
            ShippingPolicy policy,
            ShippingProperties properties
    ) {
        this.policy = policy;
        this.properties = properties;
    }

    public BigDecimal calculate(Order order) {
        if (order.total().compareTo(properties.freeShippingThreshold()) >= 0) {
            return BigDecimal.ZERO;
        }

        return policy.calculate(order);
    }
}
~~~

A unit test can construct the service directly:

~~~java
class ShippingServiceTest {

    private final ShippingPolicy policy = mock(ShippingPolicy.class);

    private final ShippingProperties properties =
            new ShippingProperties(new BigDecimal("500000"));

    private final ShippingService shippingService =
            new ShippingService(policy, properties);

    @Test
    void shouldUseFreeShippingAboveThreshold() {
        var order = new Order(new BigDecimal("600000"));

        var fee = shippingService.calculate(order);

        assertEquals(BigDecimal.ZERO, fee);
        verifyNoInteractions(policy);
    }
}
~~~

The test above verifies the free-shipping rule. Yet it bypasses Spring's instantiation mechanism. It does not tell you:

- Whether Spring scans and registers ShippingService.
- Whether Spring finds the right ShippingPolicy to inject.
- Whether multiple beans of the same type prevent the application from starting.
- Whether ShippingProperties binds properly from application.yml.
- Whether configuration values are converted to the right types.
- Whether beans are registered under the active profile.
- Whether a conditional configuration accidentally skips a required bean.
- Whether the service is wrapped in a proxy to apply transactions, caching, or security.

The reason is simple: the unit test supplied everything the service needed itself. When a test creates an object with a constructor, it skips Spring's object creation and management process.

Therefore, a green unit test is evidence only of the unit's behavior within the constructed test setup. It does not automatically prove application configuration is correct.

## 2. Parts of Spring Configuration That Plain Java Unit Tests Do Not Check

### 2.1. Component scanning and bean registration

Spring Boot normally scans components starting from the main application class's package and its subpackages. Classes carrying annotations such as @Component, @Service, @Repository, or @Controller can be discovered within the component-scan scope.

If a class sits outside the scan scope, lacks an appropriate annotation, or scan filtering is restricted, the bean may be absent from the ApplicationContext.

A unit test instantiating the service directly still passes normally:

~~~java
var service = new ShippingService(policy, properties);
~~~

Yet when Spring starts, a controller requiring ShippingService can fail with a missing bean error.

Unit tests cannot catch this error because they never ask Spring to locate beans. When changing packages, scan configuration, or module structure, include a context test verifying key beans are actually registered.

### 2.2. Dependency injection, qualifiers, and duplicate beans

Spring must pick the right bean to inject. When multiple implementations share an interface, the application may need @Primary or @Qualifier.

Example:

~~~java
public interface ShippingPolicy {
    BigDecimal calculate(Order order);
}

@Component("standardShippingPolicy")
class StandardShippingPolicy implements ShippingPolicy {
    // ...
}

@Component("expressShippingPolicy")
class ExpressShippingPolicy implements ShippingPolicy {
    // ...
}
~~~

If a service requests ShippingPolicy without a bean selection rule, Spring can fail due to multiple candidates.

A unit test passing StandardShippingPolicy directly to the constructor will not detect Spring's bean-selection failure. Only a context test can verify actual injection configuration.

For instance, a service requiring the express shipping policy:

~~~java
@Service
public class ExpressShippingService {

    private final ShippingPolicy policy;

    public ExpressShippingService(
            @Qualifier("expressShippingPolicy") ShippingPolicy policy
    ) {
        this.policy = policy;
    }
}
~~~

A test can verify that the bean is managed and the dependency was injected:

~~~java
@SpringBootTest
class ShippingWiringTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private ExpressShippingService shippingService;

    @Test
    void shouldRegisterExpressShippingService() {
        assertNotNull(shippingService);
        assertThat(context)
                .hasBean("expressShippingPolicy");
    }
}
~~~

Imports and package declarations are omitted in the example to focus on the verification technique. Context tests catch wiring errors right during ApplicationContext creation.

### 2.3. Reading and binding configuration

A service may run properly with values passed directly in unit tests while the application misreads application.yml.

Example configuration:

~~~yaml
app:
  shipping:
    free-shipping-threshold: 500000
    currency: VND
~~~

Properties class:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
@Validated
public record ShippingProperties(
        @NotNull BigDecimal freeShippingThreshold,
        @NotBlank String currency
) {
}
~~~

Spring configuration registering the properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingConfiguration {
}
~~~

Unit tests can instantiate ShippingProperties with any valid value. They do not verify that Spring registered the configuration properties, read the right prefix, bound the right field names, converted data types, or triggered validation.

A test with a Spring Context can verify the bound values:

~~~java
@SpringBootTest(properties = {
        "app.shipping.free-shipping-threshold=500000",
        "app.shipping.currency=VND"
})
class ShippingPropertiesTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldBindShippingProperties() {
        assertEquals(
                new BigDecimal("500000"),
                properties.freeShippingThreshold()
        );
        assertEquals("VND", properties.currency());
    }
}
~~~

This test verifies the path from Spring's Environment to the properties object. It catches properties registration or binding bugs invisible to plain Java unit tests.

If configuration uses @Validated with constraints such as @NotNull or @NotBlank, you can add tests starting a context with missing or malformed values to confirm startup fails on invalid configuration.

### 2.4. Profiles and environment-specific configuration

Applications often have different settings for local, test, staging, and production. Spring can enable beans or load configurations by profile:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

~~~java
@Configuration
@Profile("test")
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

A unit test can instantiate FakePaymentGateway directly and pass. Yet it does not prove the test profile is actually activated or that the production profile registers the right bean.

Profiles can be tested with:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentProfileTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void shouldUseTestPaymentGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

This test verifies which bean is selected in the ApplicationContext when the test profile is active.

Note that @ActiveProfiles sets profiles for the test context. It does not prove production deployment configuration is loaded properly on real servers. When you need to check production configuration, use a separate context test with corresponding profiles or properties while avoiding unintended connections to real systems.

### 2.5. Conditional beans and auto-configuration

Spring Boot and libraries can register beans based on conditions:

- @ConditionalOnProperty: depends on property values.
- @ConditionalOnClass: depends on classes present on the classpath.
- @ConditionalOnMissingBean: creates a bean only when no matching bean exists yet.
- @ConditionalOnBean: creates a bean only when another bean exists.
- @Profile: depends on active profiles.

A unit test can check the logic inside a conditional class or create the needed implementation directly, yet it does not verify that bean registration conditions evaluate properly in the ApplicationContext.

For example, shipping configuration enabled only when a property permits:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.shipping",
            name = "enabled",
            havingValue = "true"
    )
    ShippingService shippingService(ShippingProperties properties) {
        return new ShippingService(
                new StandardShippingPolicy(),
                properties
        );
    }
}
~~~

When app.shipping.enabled is not enabled, ShippingService should not be registered by this configuration. When enabled, the bean must appear.

This is container and conditional-configuration behavior, so test it using ApplicationContextRunner or an appropriate Spring context test.

## 3. When Should You Test with a Spring ApplicationContext?

Using Spring does not mean every unit test must boot Spring. Use plain Java unit tests when the question to answer concerns only an object's logic.

Add a context test when the question relates to any of the following:

| Question to Verify | Plain Java Unit Test | Spring Context Test |
|---|---|---|
| Does a calculation method return the right value? | Appropriate | Usually unnecessary |
| Are constructor and processing logic right? | Appropriate | Optional |
| Does Spring discover and register components? | Not verified | Needed |
| Does dependency injection select the right bean? | Not verified | Needed |
| Do @Qualifier or @Primary work properly? | Not verified | Needed |
| Does application.yml bind properly into properties? | Not verified | Needed |
| Do profiles select the right configuration? | Not verified | Needed |
| Does @ConditionalOnProperty register beans under the right conditions? | Not verified | Needed |
| Does auto-configuration work with the current classpath and beans? | Not verified | Needed |
| Does @Transactional produce proper rollback behavior? | Not verified if calling object directly | Must call Spring-managed bean |
| Do security filters or MVC configuration work? | Not verified | Needs web slice or appropriate context |

A context test does not have to boot the entire application. Pick the smallest context capable of proving what needs verification.

## 4. Options for Testing Spring Configuration

### 4.1. ApplicationContextRunner for configuration and auto-configuration

Spring Boot Test provides ApplicationContextRunner to start a minimal context per test execution. This tool is especially helpful when testing auto-configuration or conditional beans.

Example:

~~~java
@ConfigurationProperties(prefix = "app.discount")
public record DiscountProperties(
        BigDecimal rate
) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DiscountProperties.class)
public class DiscountConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.discount",
            name = "enabled",
            havingValue = "true"
    )
    DiscountService discountService(DiscountProperties properties) {
        return new DiscountService(properties.rate());
    }
}
~~~

Test verifying the enabled case:

~~~java
class DiscountConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DiscountConfiguration.class)
                    .withPropertyValues(
                            "app.discount.enabled=true",
                            "app.discount.rate=0.10"
                    );

    @Test
    void shouldRegisterDiscountServiceWhenEnabled() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(DiscountService.class);

            var properties =
                    context.getBean(DiscountProperties.class);

            assertEquals(
                    new BigDecimal("0.10"),
                    properties.rate()
            );
        });
    }
}
~~~

Test verifying the disabled case:

~~~java
@Test
void shouldNotRegisterDiscountServiceWhenDisabled() {
    new ApplicationContextRunner()
            .withUserConfiguration(DiscountConfiguration.class)
            .withPropertyValues(
                    "app.discount.enabled=false",
                    "app.discount.rate=0.10"
            )
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(DiscountService.class);
            });
}
~~~

These examples require the spring-boot-test dependency and corresponding domain classes in the project. The key is that the test does not construct DiscountService via its constructor. It asks Spring to process configuration, bind properties, and evaluate bean registration conditions.

Advantages of ApplicationContextRunner:

- Loads only the specified configurations.
- Makes changing properties between scenarios easy.
- Makes asserting bean presence or absence straightforward.
- Gives each run an isolated context to test configuration combinations independently.
- Avoids starting a web server or the entire application.

When writing libraries or auto-configurations, you can use WebApplicationContextRunner or ReactiveWebApplicationContextRunner if the configuration requires a matching web environment.

### 4.2. @SpringJUnitConfig and @ContextConfiguration

When you need to test a specific group of Spring configurations, use @SpringJUnitConfig to combine JUnit Jupiter support with Spring TestContext.

~~~java
@Configuration
class PricingTestConfiguration {

    @Bean
    PricingPolicy pricingPolicy() {
        return new StandardPricingPolicy();
    }

    @Bean
    PricingService pricingService(PricingPolicy policy) {
        return new PricingService(policy);
    }
}
~~~

~~~java
@SpringJUnitConfig(PricingTestConfiguration.class)
class PricingSpringConfigurationTest {

    @Autowired
    private PricingService pricingService;

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldCreatePricingServiceWithConfiguredPolicy() {
        assertNotNull(pricingService);
        assertThat(context)
                .hasSingleBean(PricingPolicy.class);
    }
}
~~~

This works well when verifying specific Java configuration without loading the application's entire Spring Boot configuration.

You can use @ContextConfiguration to specify context configuration sources explicitly. When tests integrate with Spring TestContext mechanisms, annotations such as @SpringJUnitConfig keep declarations concise.

### 4.3. @SpringBootTest for broad application configuration

When you need to verify multiple parts of the application assembled together, @SpringBootTest can boot an ApplicationContext using Spring Boot configuration.

~~~java
@SpringBootTest
class ApplicationConfigurationTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private ShippingService shippingService;

    @Test
    void shouldLoadRequiredApplicationBeans() {
        assertNotNull(shippingService);
        assertThat(context)
                .hasSingleBean(ShippingPolicy.class);
    }
}
~~~

By default, @SpringBootTest does not necessarily open a real HTTP server. It normally creates a context with a mock web environment if the application has web dependencies. If only checking bean wiring, opening a server is unnecessary.

Test-specific properties can be passed directly:

~~~java
@SpringBootTest(properties = {
        "app.shipping.enabled=true",
        "app.shipping.currency=VND"
})
class ShippingApplicationConfigurationTest {
    // Inject beans and verify that the configuration was loaded.
}
~~~

If you want to use a separate configuration file, combine @TestPropertySource or an appropriate test configuration mechanism. Keep in mind that properties passed directly to a test can override values in application.yml; thus the test verifies configuration under the test-supplied properties, not automatically every deployment environment.

### 4.4. Slice tests when verifying only a portion of Spring

Several Spring Boot annotations create an ApplicationContext scoped to a specific functional layer:

- @WebMvcTest: focuses on MVC, controllers, converters, validation, and related web components.
- @DataJpaTest: focuses on entities, repositories, and JPA infrastructure.
- @JsonTest: focuses on JSON serialization/deserialization.
- @RestClientTest: focuses on HTTP clients and request/response conversion configuration.
- @JdbcTest: focuses on JDBC and database operations.

For instance, if changing Jackson configuration causes an API to emit wrongly formatted JSON, testing Java objects directly is not enough. Use @JsonTest to verify JSON configuration in Spring Boot.

If changing the security filter chain or MVC configuration, @WebMvcTest helps test requests, responses, and filters within the web test slice. When verifying both backend flow and database together, pick a broader context.

Slice tests intentionally omit unrelated beans. If a controller depends on a service outside the slice, tests may need mock beans or to import the necessary test configuration. That is not a flaw in the slice; it is the boundary the slice is designed to enforce.

## 5. When Annotations Create Proxies, Direct Unit Tests Bypass Spring Behavior

An important class of configuration errors involves proxies and AOP.

Spring can wrap beans in proxies to apply behaviors such as:

- @Transactional: transaction management.
- @Cacheable: cache reads/writes.
- @Async: asynchronous execution.
- @PreAuthorize or method security annotations: access control checks.
- Other retry, tracing, or interceptor mechanisms.

Example:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(Account source, Account target, BigDecimal amount) {
        source.withdraw(amount);
        accountRepository.save(source);

        target.deposit(amount);
        accountRepository.save(target);
    }
}
~~~

If a unit test creates the service directly:

~~~java
var service = new TransferService(repository);
service.transfer(source, target, amount);
~~~

then invoking the method on the plain object does not pass through a Spring-managed transaction proxy. The test can still verify withdrawal and deposit logic, yet it does not verify that a transaction starts, commits, or rolls back properly.

To test transactions, retrieve the bean from ApplicationContext and invoke it through that bean:

~~~java
@SpringBootTest
class TransferTransactionTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void shouldRollbackTransferWhenOperationFails() {
        // Prepare two accounts in the test database.

        assertThatThrownBy(() ->
                transferService.transfer(
                        sourceAccount(),
                        targetAccount(),
                        new BigDecimal("100")
                )
        ).isInstanceOf(IllegalStateException.class);

        // Read the data back and verify that the transaction rolled back.
    }
}
~~~

This is an illustrative skeleton. In a real test, save records before invoking the service, use deterministic IDs or test data, and query the repository afterward to verify both accounts retain their original balances when the transfer fails.

Several important points:

- Transactions roll back by default on RuntimeException and Error; checked exceptions follow different rules unless rollbackFor is configured.
- A test should not run inside an outer test transaction if the goal is observing commit/rollback of the service's own transaction, as the test transaction changes how inner transactions participate.
- Calling a @Transactional method from another method on the same object is usually a self-invocation and bypasses the proxy under default proxy mode.
- If a method is unsupported by proxies due to visibility, proxy type, or bean structure, the annotation may fail to produce the expected behavior.

The same principle applies to @Cacheable, @Async, and method security: when verifying behavior supplied by Spring interceptors, invoke the Spring-managed bean through the appropriate context.

## 6. Signs That You Need to Add a Context Test

During development, consider adding a test with a Spring Context whenever the following changes or issues appear:

**Package or module structure changes**

- Moving a class to another package.
- Splitting modules or changing the application class package.
- Modifying @ComponentScan, @Import, or bean registration configuration.

These changes can prevent a component from being discovered even while its unit tests keep passing.

**Dependency injection changes**

- Adding a new implementation of an interface.
- Adding @Qualifier or @Primary.
- Changing a bean's constructor.
- Switching beans by profile or condition.

Verify Spring picks the right bean and the context starts successfully.

**Configuration changes**

- Renaming a property or prefix.
- Changing field types in @ConfigurationProperties.
- Adding validation to properties.
- Modifying profiles or environment variables.
- Changing precedence among configuration sources.

Verify the final values received by the bean.

**Auto-configuration changes**

- Adding or editing @ConditionalOnProperty.
- Changing @ConditionalOnMissingBean.
- Upgrading starter or library versions.
- Changing dependencies so a class appears or disappears from the classpath.

Test bean registration conditions across enabled, disabled, and missing-configuration scenarios.

**Proxy-driven behavior changes**

- Adding @Transactional.
- Adding @Cacheable or @CacheEvict.
- Enabling @Async.
- Enabling method security.
- Modifying AOP or transaction manager configuration.

Invoke the bean through Spring and verify actual interceptor effects.

**Web or persistence configuration changes**

- Modifying SecurityFilterChain.
- Changing converters, formatters, Jackson modules, or validators.
- Changing DataSource, JPA dialect, or transaction manager.
- Modifying migrations or repository configuration.

Use the corresponding slice test or integration test.

## 7. Choosing the Right Context Test for the Question

Do not default to @SpringBootTest for every configuration check. Booting the entire application slows tests down and drags in unrelated dependencies.

| Goal | Appropriate Tool | Scope |
|---|---|---|
| Test logic of one class | JUnit + Mockito | No Spring Context needed |
| Test a simple @Configuration | @SpringJUnitConfig | Only selected context and configuration |
| Test auto-configuration, conditional beans, properties | ApplicationContextRunner | Minimal context, easy to vary properties |
| Test overall Boot application configuration | @SpringBootTest | Application's ApplicationContext |
| Test controllers, filters, validation, HTTP JSON | @WebMvcTest | Web slice |
| Test repositories and JPA mappings | @DataJpaTest | JPA slice |
| Test JSON serialization | @JsonTest | JSON slice |
| Test HTTP clients | @RestClientTest | REST client slice |
| Test requests through a real server | @SpringBootTest with RANDOM_PORT | Application and real HTTP server |

You can apply these selection rules:

1. If the question is purely object logic, use unit tests.
2. If the question is whether Spring creates the right bean from a specific configuration, use context runner or @SpringJUnitConfig.
3. If the question is whether multiple application beans wire together properly, use @SpringBootTest.
4. If the question concerns only MVC, JPA, JSON, or REST clients, use the matching slice test.
5. If the question involves real network communication or the full journey, expand to a real server or system/E2E test.

## 8. Structuring the Test Suite to Stay Fast While Verifying Configuration

A well-structured test suite separates responsibilities cleanly:

~~~text
ShippingServiceTest
    |
    +-- Tests fee calculation rules
    +-- Mocks ShippingPolicy
    +-- Does not start Spring

ShippingConfigurationTest
    |
    +-- Tests bean registration
    +-- Tests property binding
    +-- Tests conditional configuration
    +-- Uses ApplicationContextRunner

ShippingApplicationIntegrationTest
    |
    +-- Tests wiring between beans
    +-- Tests broader application configuration
    +-- Uses @SpringBootTest when needed

ShippingApiTest
    |
    +-- Tests HTTP contract
    +-- Tests filters and validation
    +-- Uses @WebMvcTest or a real server depending on the goal
~~~

Each test group supplies a distinct kind of evidence:

- Unit tests prove object logic with controlled dependencies.
- Configuration tests prove Spring registers and configures beans under specified conditions.
- Integration tests prove real components collaborate across tested boundaries.
- System tests prove application behavior from external entry points.

Several practices keep these tests stable:

**Load only the needed context**

Use ApplicationContextRunner or slice tests when verifying only a portion of configuration. Avoid booting the entire application just to check a single property.

**Separate test data from production configuration**

Use test-specific properties or profiles. Never let a test context accidentally call a real payment gateway, send real emails, or write to production systems.

**Test both enabled and disabled cases**

For conditional beans, checking only the enabled property case is insufficient. Test disabled, missing property, or override-bean cases if they belong to the configuration contract.

**Test configuration failures deliberately**

For required properties, test that context startup fails when values are missing or malformed. This surfaces mistakes at startup rather than waiting for a rare runtime request.

**Do not duplicate all business logic inside context tests**

Context tests should verify bean graphs, properties, profiles, proxies, or integration. Detailed business branches belong in unit tests. This limits slow tests and avoids two test suites verifying the same rules.

**Observe behavior instead of merely checking context startup**

A context starting successfully is necessary, yet not sufficient to verify every setting. For instance, a bean may exist with misbound properties; a proxy may be created yet fail to roll back transactions as expected. Assert values, bean types, or corresponding runtime effects.

## 9. Reading Test Results Without Over-Claiming

When a unit test passes, you can conclude the tested logic works with the test's data and test doubles. You cannot infer that the Spring application boots successfully.

When an ApplicationContextRunner test passes, you can conclude the configuration loads inside a minimal context with the provided classpath and properties. You cannot infer the entire production application is configured properly.

When a @SpringBootTest passes, you can conclude the ApplicationContext builds with the chosen test configuration and the test's assertions pass. You cannot infer other profiles, other deployment environments, or all external services work.

When a @WebMvcTest passes, you can conclude web behavior in the tested slice works within the test context. You cannot infer the database or full service layer works if those were replaced by mocks.

When a system/E2E test passes, you can conclude the journey succeeded in that test environment with that test data. You cannot infer every business branch or every failure scenario is covered.

Always tie conclusions to the test's actual boundaries, configuration, and dependencies. That keeps test reporting technically honest and prevents false confidence.

## 10. Conclusion

Unit tests remain the best choice for testing small, fast logic with strong fault isolation. Yet when the question shifts to whether Spring creates beans, injects dependencies, binds properties, picks profiles, evaluates conditions, or applies proxies properly, tests must run through a Spring ApplicationContext.

Choose the smallest scope capable of answering the question:

- Use JUnit and Mockito to test object logic.
- Use ApplicationContextRunner to test configuration and auto-configuration across property sets.
- Use @SpringJUnitConfig when a bounded Spring context is needed.
- Use slice tests when verifying only MVC, JPA, JSON, or REST clients.
- Use @SpringBootTest when verifying application configuration and multi-bean collaboration.
- Invoke Spring-managed beans when testing transactions, caching, async execution, or proxy behaviors.

Separating business logic from framework configuration keeps your test suite fast for feedback while providing direct evidence for areas plain Java unit tests cannot verify.

