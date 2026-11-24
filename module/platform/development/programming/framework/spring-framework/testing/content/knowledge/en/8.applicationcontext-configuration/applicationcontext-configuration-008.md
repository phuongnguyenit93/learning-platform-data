# ContextInitializer for Pre-Refresh Preparation

Spring creates and configures an ApplicationContext in multiple phases. During the preparation phase, the context has been created but not yet refreshed: beans are not yet fully initialized, singletons have not been eagerly instantiated, and the application is not ready to serve requests. This is the right moment to modify the Environment, add property sources, select profiles, or register certain configurations needed before Spring processes bean definitions.

Spring provides the **ApplicationContextInitializer** interface for this purpose. In the Spring TestContext Framework, an initializer can be declared via the initializers attribute of @ContextConfiguration. Spring invokes the initializer after creating the context and before refreshing it.

This lesson explains the role of ContextInitializer in the ApplicationContext lifecycle, how to implement and register an initializer, what is appropriate to do in the pre-refresh phase, how to test it, and common mistakes when using it.

## 1. ApplicationContext Has a Preparation Phase Before Refresh

An ApplicationContext does not appear immediately in a ready state. Spring must create the context, configure the Environment, load configuration and bean definitions, and then refresh to finalize container initialization.

The high-level flow can be described as follows:

~~~text
Create ApplicationContext
        |
        v
Prepare context
- Attach parent context if any
- Prepare Environment and property sources
- Apply settings from context loader
        |
        v
ApplicationContextInitializer.initialize(context)
        |
        v
Load or finalize bean definitions
        |
        v
ApplicationContext.refresh()
- Register and run BeanFactoryPostProcessors
- Register BeanPostProcessors
- Instantiate eager singletons
- Finalize context management mechanisms
        |
        v
Context ready for use
~~~

Exact step details can vary depending on how the context is bootstrapped, the ContextLoader, or Spring Boot. The key contract of an initializer is that it is invoked once the context exists and still before the corresponding refresh.

Before refresh, an initializer can prepare information Spring needs when reading bean definitions or creating beans, such as:

- Adding property sources to the Environment.
- Adding or adjusting active profiles.
- Setting certain configuration metadata on the context.
- Registering bean definitions or singletons for special environments, if the context type supports it.
- Setting a parent context or container customizations appropriate for the context type in use.

After refresh, many decisions have already been made: conditional configurations have been evaluated, bean definitions have been processed, and eager singletons may have been instantiated. Modifying the Environment at that point usually does not cause already-initialized beans to re-read configuration automatically. Therefore, if a property must affect binding or conditional bean registration, it must be supplied before refresh.

## 2. What Is ApplicationContextInitializer?

The ApplicationContextInitializer interface has a single initialize method that receives the context to prepare:

~~~java
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

The type parameter C lets the initializer constrain the type of context it supports. For example, an initializer can accept ConfigurableApplicationContext in general, or accept only a specific context type when the configuration requires specialized APIs.

An initializer is typically a standalone class:

~~~java
public class TestEnvironmentInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        // Prepare the context before refresh.
    }
}
~~~

Spring instantiates and calls the initializer during context preparation. It is not a regular bean retrieved from the ApplicationContext being initialized, because that context has not been refreshed yet and is not ready to provide beans in the normal way.

Therefore, design an initializer as an independent configuration component:

- Can be instantiated via a default constructor when using class-based initializer declarations.
- Does not depend on @Autowired beans from the very context being prepared.
- Receives the context through the initialize parameter.
- Should avoid holding shared mutable state across multiple initializations.
- Performs only necessary, repeatable, and controllable preparation work.

If an initializer needs input data, supply it via properties, a constructor supported by a dedicated instantiation mechanism, or an independent configuration object. For initializers declared by class in @ContextConfiguration, the simplest and most compatible approach is usually a class that requires no dependency injection.

## 3. Example: Adding a Property Source Before Refresh

Suppose an application has shipping configuration:

~~~yaml
app:
  shipping:
    free-shipping-threshold: 500000
    currency: VND
~~~

The application binds configuration to a record:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(
        BigDecimal freeShippingThreshold,
        String currency
) {
}
~~~

A configuration registers the properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingConfiguration {
}
~~~

In some tests or special environments, we want to add properties before Spring creates ShippingProperties. You can use MapPropertySource:

~~~java
public class ShippingTestInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of(
                "app.shipping.free-shipping-threshold", "750000",
                "app.shipping.currency", "VND"
        );

        var propertySource =
                new MapPropertySource("shippingTestOverrides", values);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(propertySource);
    }
}
~~~

Explanation:

- ConfigurableApplicationContext provides a configurable Environment.
- MapPropertySource wraps property name-value pairs.
- addFirst places the property source at a high-priority position in the list.
- When Spring reads properties, values in shippingTestOverrides take precedence over property sources behind it.

Use addFirst intentionally: it can override values from application.yml or lower-precedence configuration sources. If you want new properties to have lower precedence than certain existing sources, choose addLast or addBefore/addAfter using the appropriate property source name.

You can test the initializer with Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = ShippingConfiguration.class,
        initializers = ShippingTestInitializer.class
)
class ShippingConfigurationTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldUsePropertiesAddedBeforeRefresh() {
        assertEquals(
                new BigDecimal("750000"),
                properties.freeShippingThreshold()
        );
        assertEquals("VND", properties.currency());
    }
}
~~~

This test does not instantiate ShippingProperties manually. Spring creates the context, invokes the initializer, loads the configuration, and binds properties during bean initialization. Assertions verify the actual values injected into the test.

If you omit the initializer while keeping the base configuration, the test will receive values from another configuration source or fail if required properties are absent. The difference lies in when and from which source properties are placed into the Environment.

## 4. Setting Active Profiles Before Refresh

Profiles can decide which configuration classes or beans are registered. If an initializer needs to add profiles for the context, it can operate on ConfigurableEnvironment.

~~~java
public class TestProfileInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment().addActiveProfile("integration-test");
    }
}
~~~

Once the profile is added, configurations like the following can be applied when Spring processes the context:

~~~java
@Configuration
@Profile("integration-test")
class IntegrationTestConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

In the test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = IntegrationTestConfiguration.class,
        initializers = TestProfileInitializer.class
)
class PaymentConfigurationTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void shouldLoadTestPaymentGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

Two operations are easy to confuse:

- addActiveProfile adds a profile to the current set of active profiles.
- setActiveProfiles resets the list of active profiles to the passed values.

If the context already has profiles set by the environment or other configurations, setActiveProfiles can overwrite that list. Choose the method matching your intent: adding a profile or replacing all profiles.

Do not use an initializer to enable a production profile in tests if doing so could cause tests to connect to real databases, payment gateways, or live services. Use a dedicated test profile and explicitly control external dependencies.

## 5. Registering Initializers in the Spring TestContext Framework

With JUnit Jupiter, initializers can be declared in @ContextConfiguration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = TestApplicationConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class ApplicationContextTest {
}
~~~

The Spring TestContext Framework uses the initializer while creating the context for the test class. The configuration above has three parts:

- @ExtendWith(SpringExtension.class) connects JUnit Jupiter with Spring TestContext.
- classes specifies the configuration used to create the context.
- initializers specifies the classes to be invoked before refresh.

You can write this more concisely with @SpringJUnitConfig if you want to combine SpringExtension and @ContextConfiguration:

~~~java
@SpringJUnitConfig(
        classes = TestApplicationConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class ApplicationContextTest {
}
~~~

When using composed annotations or inherited @ContextConfiguration setups, ensure metadata merges into the desired configuration. Explicit declaration in a single @ContextConfiguration is usually easiest to read when there is only one configuration group.

### Multiple Initializers

A test may require multiple initializers, such as one that adds properties and another that sets up a different context configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = TestApplicationConfiguration.class,
        initializers = {
                TestEnvironmentInitializer.class,
                TestProfileInitializer.class
        }
)
class ApplicationContextTest {
}
~~~

When order matters, declare and order initializers explicitly. Spring TestContext supports ordering via initializer ordering mechanisms such as Ordered or @Order in the appropriate cases. Do not let a later initializer silently overwrite what an earlier initializer prepared.

For example, if initializer A adds a property source and initializer B reads that property to decide configuration, B must run after A. If both modify active profiles or alter property sources, establish clear precedence rules.

An initializer should modify one clearly scoped configuration concern. If multiple initializers depend on each other, consider merging related preparation into a single initializer to reduce ordering complexity.

## 6. Using Initializers with Spring Boot

Spring Boot builds on Spring's ApplicationContext and therefore also supports ApplicationContextInitializer.

You can register an initializer directly with SpringApplication:

~~~java
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                new TestEnvironmentInitializer()
        );

        application.run(args);
    }
}
~~~

Or with SpringApplicationBuilder:

~~~java
new SpringApplicationBuilder(Application.class)
        .initializers(new TestEnvironmentInitializer())
        .run(args);
~~~

In real applications, initializers are usually registered using the mechanism appropriate for the runtime environment. The examples above only illustrate the registration API, not that production applications should always use an initializer named TestEnvironmentInitializer.

In Spring Boot tests, you can declare initializers via @ContextConfiguration alongside @SpringBootTest when combining with Boot configuration:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = ShippingTestInitializer.class)
class ShippingApplicationTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldReadInitializerProperties() {
        assertEquals(
                new BigDecimal("750000"),
                properties.freeShippingThreshold()
        );
    }
}
~~~

@SpringBootTest creates the context using Spring Boot's mechanism. @ContextConfiguration adds initializers to prepare the context before refresh.

Avoid registering the same initializer multiple times through different mechanisms unless intentional. Running an initializer repeatedly can cause duplicate bean definitions, add property sources multiple times, or produce confusing side effects.

## 7. Registering Bean Definitions from an Initializer

An initializer can do more than modify the Environment. With a supporting context type, it can also register configurations or bean definitions before refresh.

For example, if the concrete context is a GenericApplicationContext, you can register a test bean:

~~~java
public class FixedClockInitializer
        implements ApplicationContextInitializer<GenericApplicationContext> {

    @Override
    public void initialize(GenericApplicationContext context) {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        context.registerBean(
                Clock.class,
                () -> fixedClock
        );
    }
}
~~~

After refresh, the Clock bean can be injected into services:

~~~java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAt(Duration duration) {
        return clock.instant().plus(duration);
    }
}
~~~

In the test:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = FixedClockInitializer.class)
class ExpirationServiceTest {

    @Autowired
    private ExpirationService expirationService;

    @Test
    void shouldUseFixedClock() {
        assertEquals(
                Instant.parse("2026-01-01T01:00:00Z"),
                expirationService.expiresAt(Duration.ofHours(1))
        );
    }
}
~~~

This example requires a context type supporting GenericApplicationContext and should only be used when the test configuration genuinely needs to register beans that way. For a simple bean, @TestConfiguration and @Bean are usually clearer:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

You can import the test configuration with @Import or declare it in test configuration. This is usually easier to read if the goal is simply replacing a dependency in tests.

When registering beans using GenericApplicationContext APIs, the initializer must accept the right context type. Do not assume every ConfigurableApplicationContext has a registerBean method like GenericApplicationContext. If an initializer needs to work across multiple context types, use appropriate general APIs or separate configurations by context type.

## 8. How ContextInitializer Differs from Other Spring Extension Points

Spring has several extension points in the container lifecycle. They differ in timing and purpose.

| Mechanism | Main Timing | What Is It Used For? |
|---|---|---|
| ApplicationContextInitializer | After context creation, before refresh | Preparing the Environment and context |
| BeanDefinitionRegistryPostProcessor | During refresh, in the bean definition processing phase | Registering or modifying bean definitions |
| BeanFactoryPostProcessor | During refresh, after bean definitions are loaded and before regular singleton instantiation | Adjusting bean factory metadata |
| BeanPostProcessor | During creation of each bean | Customizing beans before/after initialization |
| ApplicationRunner / CommandLineRunner | After Spring Boot finishes context initialization | Running tasks after application startup |

### When to Choose ApplicationContextInitializer?

Choose an initializer when you need to prepare the context before refresh, especially when changes must take effect before Spring processes configuration or creates beans.

Examples:

- Adding property sources.
- Adding active profiles.
- Preparing the Environment for configuration properties.
- Applying initial settings to the context.
- Registering certain bean definitions in a compatible context.

### When to Choose BeanFactoryPostProcessor?

If you need to inspect or modify bean definitions after they have been loaded, BeanFactoryPostProcessor or BeanDefinitionRegistryPostProcessor is usually more appropriate.

For example, a library that inspects bean definition metadata or registers definitions based on existing definitions belongs at the bean factory phase, not initial Environment preparation.

### When to Choose BeanPostProcessor?

If you need to intercept objects while Spring creates beans—such as wrapping proxies or customizing beans before/after initialization—BeanPostProcessor is the right extension point.

### When to Choose ApplicationRunner?

If work needs to run after the application has started and beans are ready, ApplicationRunner or CommandLineRunner fits better. Do not use a runner to add properties required for bean binding, because by then it is too late.

## 9. ContextInitializer vs. Other Ways to Supply Properties in Tests

An initializer is not the only way to supply properties to the context. Choose the tool according to data type and complexity.

| Configuration Approach | Suitable When | Characteristics |
|---|---|---|
| application.yml / application.properties | Default application configuration | Standard configuration source |
| @TestPropertySource | Test needs a fixed set of properties | Declared inline or via property files |
| @SpringBootTest(properties = ...) | Boot test needs a few simple overrides | Concise and readable directly on the test |
| @DynamicPropertySource | Property values are determined dynamically, e.g., container URLs | Registers suppliers for runtime values |
| ApplicationContextInitializer | Need to prepare Environment/context via logic or multiple steps | Flexible, but requires managing lifecycle and order |

### @TestPropertySource for Fixed Properties

~~~java
@SpringJUnitConfig(TestApplicationConfiguration.class)
@TestPropertySource(properties = {
        "app.shipping.free-shipping-threshold=750000",
        "app.shipping.currency=VND"
})
class ShippingPropertiesTest {
}
~~~

If you only need to override a few static properties, this approach is usually more readable than creating a dedicated initializer.

### @DynamicPropertySource for Runtime Values

When a test uses Testcontainers, URLs and connection details are only available after containers start. @DynamicPropertySource lets you register suppliers:

~~~java
@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

This is a specialized, convenient option for properties supplied by test resources. If you only need to push those values into the Environment, you do not necessarily need to write an initializer yourself.

### When Does an Initializer Have an Advantage?

An initializer fits when you need a composite preparation step, such as:

- Adding property sources and active profiles under a unified rule.
- Integrating a test framework that must configure the context before refresh.
- Registering beans or context metadata based on runtime information that static annotations cannot easily express.
- Sharing a single preparation procedure across multiple test classes or contexts.

If the logic is just declaring a property, consider @TestPropertySource or the properties attribute of @SpringBootTest first.

## 10. Testing the Initializer Itself

Testing can be split into two layers:

1. Unit-testing pure logic of the initializer if it contains computation or property-selection rules.
2. Verifying the actual effect on an ApplicationContext before refresh.

For effects on a context, ApplicationContextRunner is well suited because it registers the initializer and lets you inspect the context once the runner completes refresh.

Example:

~~~java
class ShippingInitializerTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withInitializer(new ShippingTestInitializer())
                    .withUserConfiguration(ShippingConfiguration.class);

    @Test
    void shouldExposeShippingOverridesToTheContext() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(ShippingProperties.class);

            var properties = context.getBean(ShippingProperties.class);

            assertEquals(
                    new BigDecimal("750000"),
                    properties.freeShippingThreshold()
            );
        });
    }
}
~~~

ApplicationContextRunner invokes the initializer while building the context, then refreshes and hands the ready context to the test callback. Assertions therefore read the bean constructed with the properties added by the initializer.

You can also test cases where profiles or property sources are configured:

~~~java
@Test
void shouldActivateIntegrationProfile() {
    new ApplicationContextRunner()
            .withInitializer(new TestProfileInitializer())
            .withUserConfiguration(IntegrationTestConfiguration.class)
            .run(context -> {
                assertThat(context.getEnvironment().getActiveProfiles())
                        .contains("integration-test");
                assertThat(context)
                        .hasSingleBean(PaymentGateway.class);
            });
}
~~~

In real tests, you can check active profiles directly from the Environment and verify the specific bean types registered. Assertions should reflect the initializer's configuration contract.

If an initializer only adds a property source, there is no need to assert every internal detail of MapPropertySource. Assert the effective values that Spring actually uses.

## 11. Common Mistakes When Using ContextInitializer

### 11.1. Modifying the Environment After Refresh

A common mistake is trying to add properties after the context has already been refreshed:

~~~java
context.refresh();

// Mutating properties after beans have already been created.
context.getEnvironment()
        .getPropertySources()
        .addFirst(propertySource);
~~~

If beans have already bound properties or configuration conditions have already been evaluated, adding properties afterward will not automatically recreate beans or re-evaluate the entire configuration.

Add properties inside an initializer or a configuration mechanism executed before refresh.

### 11.2. Confusing an Initializer with an Injected Bean

An initializer is created before the context is complete. Do not expect to @Autowired a service from the very context being prepared.

If an initializer needs a value, obtain it from the Environment, configuration parameters, or an allowed independent source. If the work needs an already-initialized bean, it likely belongs to a later extension point.

### 11.3. Using the Wrong Context Type

An initializer accepting GenericApplicationContext only works with compatible contexts. If used with another context type, a cast error or inability to call specialized APIs may occur.

If you only need to modify the Environment, accepting ConfigurableApplicationContext is usually more flexible.

### 11.4. Unexpected Property Source Precedence

addFirst and addLast create different precedence positions. If a property still resolves to an old value, inspect the property source order and which source provides the final value.

Avoid adding multiple property sources with the same name or running an initializer repeatedly without control.

### 11.5. Accidentally Overwriting Active Profiles

setActiveProfiles replaces the current profile list. If your goal is only to add a profile, use addActiveProfile.

Inspect the final profile set when tests combine multiple configuration sources.

### 11.6. Hard-to-Repeat Initialization Side Effects

Initializers run when Spring creates the context. If an initializer calls real APIs, creates production data, opens unclosed resources, or modifies shared files, tests become unstable.

Keep initializers lightweight, with clearly scoped resources and repeatable execution. Operations with significant side effects require proper lifecycle and cleanup mechanisms.

### 11.7. Using an Initializer for Tasks Belonging to Another Mechanism

If you only need to mock a bean, @TestConfiguration, @Import, or Spring Boot's mock bean mechanisms may be clearer. If you need to run a task after application startup, use ApplicationRunner. If you need to modify bean definitions after loading, consider BeanFactoryPostProcessor or BeanDefinitionRegistryPostProcessor.

Choose the extension point according to when you need to intervene.

## 12. Ordering Multiple Initializers and Independence

When there are multiple initializers, clarify which initializer supplies data and which consumes it.

Example:

~~~text
EnvironmentInitializer
    |
    +-- Add property sources
    +-- Add active profiles
            |
            v
ConditionalConfigurationInitializer
    |
    +-- Read prepared values
    +-- Prepare dependent configuration
            |
            v
ApplicationContext.refresh()
~~~

If initializer order is not clearly defined, tests may behave differently when configuration changes or when an initializer is used in a different context.

Some principles:

- Each initializer should have a narrow responsibility.
- Avoid relying on implicit side effects of another initializer.
- Use ordering when order is part of the design.
- Do not use static mutable state to pass data between initializations.
- Do not retain references to the context after the initializer finishes unless necessary.
- If two steps must always run together, consider combining them to make the contract explicit.

An initializer must be safe when applied to compatible contexts and should not assume it runs only once in the entire process. Spring can create multiple contexts for different test classes or configurations.

## 13. Workflow for Choosing and Implementing an Initializer

When preparing an ApplicationContext, you can follow these steps:

1. Identify the exact data or configuration that must exist before refresh.
2. Check whether @TestPropertySource, @SpringBootTest(properties), @DynamicPropertySource, or @TestConfiguration already solves the need.
3. If composite preparation logic is needed, create a class implementing ApplicationContextInitializer with the right context type.
4. Modify the Environment or context through supported APIs before refresh.
5. Register the initializer via @ContextConfiguration or the corresponding Spring Boot mechanism.
6. If multiple initializers exist, define their order and avoid unintended overrides.
7. Write context tests to verify values, profiles, or beans after the context refreshes.
8. Ensure the initializer leaves no side effects outside test scope and can run repeatedly.

For example, if the goal is simply changing one fixed property, there is no need to create an initializer. If the goal is integrating multiple preparation steps that static annotations cannot express clearly, an initializer is an appropriate extension point.

## 14. Conclusion

ApplicationContextInitializer is an extension point for preparing a ConfigurableApplicationContext after the context is created and before refresh. It allows adding property sources, active profiles, and necessary configurations or bean definitions before Spring processes and instantiates beans.

Keep these key points in mind:

- Initializers run before refresh; changes must take effect before beans are created or configuration conditions are evaluated.
- In Spring TestContext, register initializers via the initializers attribute of @ContextConfiguration.
- With Spring Boot, initializers can be registered via SpringApplication or by combining @SpringBootTest with @ContextConfiguration.
- An initializer is not a regular bean of the context being prepared, so do not rely on dependency injection from that context.
- addFirst, addLast, addActiveProfile, and setActiveProfiles have distinct meanings; understand precedence and impact on existing configuration.
- Use ApplicationContextRunner or context tests to verify results after refresh.
- Choose an initializer when pre-refresh preparation logic is genuinely needed; use simpler property annotations or test configurations when they suffice.

By placing configuration operations properly in the pre-refresh phase, Spring reads the necessary Environment and metadata right as the container is built. That helps tests reproduce configuration in a controlled way and catch initialization errors earlier.

