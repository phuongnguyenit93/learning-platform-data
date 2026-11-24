# MockEnvironment and MockPropertySource

When a Spring component needs to read configuration through Environment, tests for that component do not necessarily need to start an entire Spring ApplicationContext or read real environment variables from the machine. Spring Test provides two small utilities for creating an in-memory configuration environment: **MockEnvironment** and **MockPropertySource**.

- **MockEnvironment** is a test implementation of ConfigurableEnvironment. It allows the component under test to read properties, convert types, and query profiles through the familiar Environment contract.
- **MockPropertySource** is a PropertySource that can be controlled in a test. You can add arbitrary properties, configure multiple configuration sources, and test the precedence order between them.

These two classes are especially useful when unit testing a class that accepts Environment via its constructor, or when you want to verify configuration selection logic without accessing files, OS environment variables, JVM system properties, or external services.

They belong to Spring Test and are usually available via the spring-test or spring-boot-starter-test dependency in test scope. They do not create a Spring container by themselves, do not inject @Value automatically, and do not replace tests that need to verify Spring Boot binding or auto-configuration.

## 1. Environment and PropertySource in Spring

Spring provides the Environment abstraction so applications can read configuration values by name. Instead of forcing a class to call System.getenv or System.getProperty directly, the class can accept Environment and request the needed value:

~~~java
String region = environment.getProperty("service.region");
~~~

Environment also supports:

- Reading a property as a String or converting it to a requested type.
- Providing a default value when a property does not exist.
- Resolving placeholders in strings.
- Checking active profiles.
- Accessing property sources through ConfigurableEnvironment.

Values do not necessarily reside in a single Map. Spring represents each configuration source with a PropertySource and manages them in MutablePropertySources.

An application can receive configuration from multiple places, for example:

- JVM system properties.
- Operating system environment variables.
- Configuration files.
- Configuration sources added by the application.
- Properties declared specifically for tests.

Each PropertySource has a name and its own way of looking up values. When multiple sources contain the same key, the order in MutablePropertySources determines which source takes precedence.

~~~mermaid
flowchart TD
    Consumer["Component using Environment"] --> Env["Environment / PropertyResolver"]
    Env --> Sources["MutablePropertySources"]
    Sources --> First["High-priority source"]
    Sources --> Next["Next source"]
    Sources --> Last["Low-priority source"]
    First --> Lookup["Look up key and return first value found"]
    Next --> Lookup
    Last --> Lookup
~~~

**MockEnvironment** provides a controllable environment for tests. **MockPropertySource** provides property sources where data can be set explicitly. Combining these two classes helps test how a component reads configuration and how source ordering affects the result.

## 2. MockEnvironment: creating an in-memory Environment

MockEnvironment is located in the package:

~~~java
import org.springframework.mock.env.MockEnvironment;
~~~

You can create a new instance in each test:

~~~java
MockEnvironment environment = new MockEnvironment();
~~~

Then add a MockPropertySource to the list of configuration sources:

~~~java
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.env.MockPropertySource;

MockEnvironment environment = new MockEnvironment();

MockPropertySource properties =
        new MockPropertySource("unitTestProperties");

properties.setProperty("feature.checkout.enabled", "true");
properties.setProperty("service.region", "ap-southeast-1");

environment.getPropertySources().addFirst(properties);
~~~

From here, Environment can look up the configured values:

~~~java
assertEquals(
        "true",
        environment.getProperty("feature.checkout.enabled")
);

assertEquals(
        "ap-southeast-1",
        environment.getProperty("service.region")
);
~~~

MockEnvironment implements ConfigurableEnvironment, so in addition to reading properties, tests can also configure active profiles and access the list of property sources.

Some Spring versions provide the fluent withProperty method on MockEnvironment to add properties directly. Whether using the fluent style or attaching a MockPropertySource explicitly, the meaning is still creating in-memory configuration data for tests. When you need to observe source names, precedence order, or replace a specific source, creating a separate MockPropertySource is usually easier to understand.

### Example: a component reading a feature flag

Suppose the application has a feature flag:

~~~java
import org.springframework.core.env.Environment;

public final class CheckoutFeature {

    private final Environment environment;

    public CheckoutFeature(Environment environment) {
        this.environment = environment;
    }

    public boolean isEnabled() {
        return environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

The class only depends on the Environment interface. A test can create a MockEnvironment and supply the property:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.env.MockPropertySource;

class CheckoutFeatureTest {

    @Test
    void enablesCheckoutWhenPropertyIsTrue() {
        MockEnvironment environment = new MockEnvironment();

        MockPropertySource properties =
                new MockPropertySource("testProperties");
        properties.setProperty("feature.checkout.enabled", "true");

        environment.getPropertySources().addFirst(properties);

        CheckoutFeature feature = new CheckoutFeature(environment);

        assertTrue(feature.isEnabled());
    }
}
~~~

This test runs directly on Java objects. It does not need component scanning, an ApplicationContext, an application.yml file, or real environment variables. It verifies that **CheckoutFeature** reads the right property and applies the default value as written.

You can add a test for the missing-property case:

~~~java
@Test
void disablesCheckoutWhenPropertyIsMissing() {
    CheckoutFeature feature =
            new CheckoutFeature(new MockEnvironment());

    assertFalse(feature.isEnabled());
}
~~~

With the getProperty overload that takes a target type and default value, a non-existent property yields the default value. The test can protect this fallback behavior without modifying the host machine's configuration.

## 3. MockPropertySource: controlling a configuration source

MockPropertySource is located in the package:

~~~java
import org.springframework.mock.env.MockPropertySource;
~~~

It allows creating a PropertySource with test-defined data. For example:

~~~java
MockPropertySource properties =
        new MockPropertySource("testOverrides");

properties.setProperty("service.timeout", "2500");
properties.setProperty("service.name", "checkout-test");
~~~

Once created, the source can be added to a ConfigurableEnvironment:

~~~java
environment.getPropertySources().addFirst(properties);
~~~

Common operations on MutablePropertySources include:

| Operation | Meaning |
|---|---|
| addFirst(source) | Adds the source at the start of the list, with the highest priority |
| addLast(source) | Adds the source at the end of the list, with the lowest priority |
| addBefore(name, source) | Inserts the source before an existing named source |
| addAfter(name, source) | Inserts the source after an existing named source |
| remove(name) | Removes a source by name |
| replace(name, source) | Replaces a named source with a new source |

Source names should be chosen clearly and uniquely within a test so that replacing or removing one does not accidentally affect another source.

### An Environment with multiple property sources

Suppose the application has default configuration and override configuration. You can create two MockPropertySource instances:

~~~java
MockEnvironment environment = new MockEnvironment();

MockPropertySource defaults =
        new MockPropertySource("defaults");
defaults.setProperty("service.timeout", "5000");
defaults.setProperty("service.region", "default-region");

MockPropertySource testOverrides =
        new MockPropertySource("testOverrides");
testOverrides.setProperty("service.timeout", "1000");

environment.getPropertySources().addLast(defaults);
environment.getPropertySources().addFirst(testOverrides);
~~~

When reading properties:

~~~java
assertEquals("1000", environment.getProperty("service.timeout"));
assertEquals("default-region", environment.getProperty("service.region"));
~~~

The key service.timeout is present in both sources. The testOverrides source was added with addFirst, so it is looked up first and overrides the default value. The key service.region is only in defaults, so the value there is used.

You can visualize the order as follows:

~~~text
High priority
    testOverrides
    mockProperties of MockEnvironment (if values remain)
    defaults
Low priority
~~~

The exact order depends on the sources the test has added. The rule to remember is that Spring looks up property sources in their order within MutablePropertySources and uses the first value found. addFirst creates a high-priority source; addLast creates a low-priority source.

### Testing override behavior explicitly

An independent test can prove that an override value beats a default value:

~~~java
@Test
void firstPropertySourceOverridesLaterSource() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource defaults =
            new MockPropertySource("defaults");
    defaults.setProperty("service.timeout", "5000");

    MockPropertySource overrides =
            new MockPropertySource("overrides");
    overrides.setProperty("service.timeout", "1000");

    environment.getPropertySources().addLast(defaults);
    environment.getPropertySources().addFirst(overrides);

    assertEquals("1000", environment.getProperty("service.timeout"));
}
~~~

This test does not verify YAML file ordering or how Spring Boot loads configuration. It tests Environment lookup rules with two directly added PropertySource instances.

## 4. Testing data types and default values

Configuration values are usually represented as strings. Environment has overloads that allow requesting a target type:

~~~java
Boolean enabled =
        environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class
        );
~~~

You can request a default value:

~~~java
boolean enabled =
        environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class,
                false
        );
~~~

This is useful when a configuration option can be omitted. Tests should describe both the case where the property exists and the case where the property is absent.

~~~java
@Test
void convertsStringPropertyToBoolean() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty("feature.enabled", "true");

    environment.getPropertySources().addFirst(properties);

    assertEquals(
            Boolean.TRUE,
            environment.getProperty("feature.enabled", Boolean.class)
    );
}
~~~

Conversion depends on the conversion mechanism configured for Environment. For simple types such as Boolean, Integer, or Duration under appropriate configuration, you can test via the type-conversion API. If the application has custom converters, custom formats, or complex binding, you should test that converter/binder itself within an appropriate scope.

You should not assume every string can be converted to every type. A malformed property can cause a conversion error. If invalid-value handling behavior is part of the component's contract, write a separate test for that case.

## 5. Testing components that depend on Environment

A common reason to use MockEnvironment is testing a class that accepts Environment through its constructor. This often suits a class that needs to read configuration to make a decision.

For example, a component selecting an endpoint based on a property:

~~~java
import org.springframework.core.env.Environment;

public final class ServiceEndpoint {

    private final Environment environment;

    public ServiceEndpoint(Environment environment) {
        this.environment = environment;
    }

    public String baseUrl() {
        return environment.getProperty(
                "partner.base-url",
                "https://partner.example.test"
        );
    }
}
~~~

A test can verify that the configured value overrides the default:

~~~java
@Test
void usesConfiguredPartnerUrl() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty(
            "partner.base-url",
            "https://stub.example.test"
    );

    environment.getPropertySources().addFirst(properties);

    ServiceEndpoint endpoint = new ServiceEndpoint(environment);

    assertEquals(
            "https://stub.example.test",
            endpoint.baseUrl()
    );
}
~~~

This only checks the URL value returned by the component. It does not open a connection to the URL and does not verify that the endpoint is reachable. If the component later uses the URL to make HTTP calls, the HTTP adapter needs to be tested separately.

### Testing profiles

MockEnvironment is also a ConfigurableEnvironment, so tests can set active profiles:

~~~java
@Test
void recognizesTestProfile() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("test", "local");

    assertTrue(environment.acceptsProfiles(Profiles.of("test")));
    assertTrue(environment.acceptsProfiles(Profiles.of("local")));
    assertFalse(environment.acceptsProfiles(Profiles.of("production")));
}
~~~

This test is useful when a class checks profiles itself through Environment. It does not prove that the Spring container selected the right beans according to @Profile. Selecting beans by profile happens during ApplicationContext creation and requires a context test if that is the behavior to verify.

## 6. Resolving placeholders and nested properties

Environment extends PropertyResolver, so it can resolve placeholders based on existing property sources. For example, one configuration entry can reference another key:

~~~java
@Test
void resolvesPlaceholderFromMockPropertySource() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty("service.host", "localhost");
    properties.setProperty("service.port", "8081");

    environment.getPropertySources().addFirst(properties);

    String resolved = environment.resolveRequiredPlaceholders(
            "http://$" + "{service.host}:$" + "{service.port}"
    );

    assertEquals("http://localhost:8081", resolved);
}
~~~

Here, the placeholder string is concatenated in the Java example to avoid confusing documentation syntax with template syntax. In real code, you can write the standard Spring placeholder string directly.

The resolveRequiredPlaceholders method requires the referenced placeholders to be resolvable; if a required property is missing, the operation throws an error. The resolvePlaceholders method is more lenient with missing placeholders and may leave the unresolved string intact, depending on how the resolver is configured.

Choose the API according to the application's contract. If configuration is required, the test should verify that missing properties are detected. If configuration has a fallback, the test should verify that fallback.

## 7. MockEnvironment does not replace Spring ApplicationContext

This is the most important boundary when using these two utilities.

MockEnvironment helps test an object that reads Environment. It does not perform container responsibilities on its own:

- Does not scan components and register beans.
- Does not perform constructor or field injection for application beans.
- Does not process @Value on beans like BeanFactoryPostProcessor does in a context.
- Does not evaluate @Conditional or @ConditionalOnProperty to decide bean creation.
- Does not run Spring Boot auto-configuration.
- Does not perform @ConfigurationProperties binding like a configured Boot ApplicationContext.
- Does not apply AOP, transaction proxies, or method security.

For example, if the goal is to test that a plain class calls getProperty with the right key, MockEnvironment is enough. If the goal is to test that @Value is injected properly into a bean, you need to build a Spring context with the corresponding property.

Other tools can be used depending on the question:

| Goal | Suitable testing approach |
|---|---|
| Class reading Environment directly via constructor | MockEnvironment |
| Testing PropertySource precedence order | MockEnvironment + MockPropertySource |
| Testing beans created based on a property | ApplicationContextRunner or context test |
| Testing @Value injection | Spring TestContext or Spring Boot context test |
| Testing @ConfigurationProperties binding | Spring Boot Binder test or ApplicationContextRunner |
| Testing profile-based implementation selection | ApplicationContext with corresponding profile |
| Testing dynamic values from Testcontainers | @DynamicPropertySource or appropriate property registration mechanism |

### Example with ApplicationContextRunner

Suppose there is a bean configuration that depends on a property:

~~~java
@Configuration
class CheckoutConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "feature.checkout.enabled",
            havingValue = "true"
    )
    CheckoutFeature checkoutFeature(Environment environment) {
        return new CheckoutFeature(environment);
    }
}
~~~

If you want to verify that the bean appears when the property is true, you can use Spring Boot's ApplicationContextRunner:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(CheckoutConfiguration.class);

@Test
void registersFeatureWhenPropertyIsEnabled() {
    contextRunner
            .withPropertyValues("feature.checkout.enabled=true")
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(CheckoutFeature.class);
            });
}
~~~

This example tests bean creation conditions inside a Spring Boot context. That is a different question from creating a MockEnvironment and calling CheckoutFeature directly. The context runner initializes the required configuration mechanism and evaluates bean conditions during refresh.

### Example with @TestPropertySource

For tests using Spring TestContext, you can supply properties inline:

~~~java
@SpringJUnitConfig(CheckoutConfiguration.class)
@TestPropertySource(properties = {
        "feature.checkout.enabled=true"
})
class CheckoutConfigurationTest {
    // Autowire beans and verify the context here.
}
~~~

This approach is suitable when you want the property to participate in building a real test context. If you only need to test a small class reading a property, starting a context may be unnecessary.

## 8. Real application configuration sources and MockEnvironment limitations

MockEnvironment creates a controllable environment in tests, but it does not automatically reproduce every runtime configuration source.

A StandardEnvironment in an application normally includes system properties and the system environment. A Spring Boot application also has mechanisms for loading configuration files, profile-specific configuration, command-line arguments, and Boot-managed property sources.

Meanwhile, MockEnvironment is designed for tests. It does not automatically read application.properties, application.yml, machine environment variables, or deployment configuration sources.

This has two consequences:

1. Tests can explicitly set the exact keys needed without depending on a developer's machine or CI.
2. Tests with MockEnvironment do not prove that the production application loads and prioritizes configuration sources in the expected way.

If code needs to simulate a specific source, create the corresponding PropertySource and add it explicitly. Do not read real environment variables just to make a test pass on a personal machine.

For cases that need to test how Spring handles environment variables, system properties, or real configuration files, choose an appropriately scoped test and provide that source in a controlled way. If the goal is to verify Spring Boot Config Data behavior, test through a Spring Boot context or the corresponding configuration mechanism.

## 9. Common mistakes when using MockEnvironment and MockPropertySource

### Adding a property source at the wrong position

If a test has multiple sources containing the same key, the source added first in order takes priority. Using addLast when intending to override can cause the test to receive a different value than expected.

Name sources and add them intentionally with addFirst/addLast. In precedence tests, assertions should directly check the final value returned by Environment.

### Reusing one MockEnvironment across multiple tests

MockEnvironment and MockPropertySource are mutable. If a static instance is shared, one test can leave behind properties or active profiles that affect the next test.

Create a fresh environment per test or per fixture. If a shared helper exists, it should return a new instance with explicitly declared data.

### Testing Environment and concluding @Value already works

An object instantiated directly and given a MockEnvironment does not go through Spring's @Value processing. To verify injection, the bean must be created by a context and assertions must check the injected value.

### Testing a property directly and concluding @ConditionalOnProperty is correct

Bean conditions are evaluated during context configuration. Having Environment return the string "true" does not by itself prove that conditional configuration registered the bean. Use ApplicationContextRunner or a context test to check bean creation results.

### Assuming MockEnvironment contains data from the host machine

Do not assume MockEnvironment automatically carries all system properties or environment variables from the machine. Set the required data directly using MockPropertySource. This keeps tests stable across local machines, CI, and different environments.

### Using mock properties to test external services

MockPropertySource only provides configuration data. It does not create a database, HTTP server, or broker. If a test needs to verify connectivity to an endpoint, test the adapter or run a separate integration test.

### Not testing missing or invalid property cases

A test that only checks valid configuration values may miss fallback behavior or errors when a property is invalid. Clearly specify which properties are required, which have defaults, and how invalid values are handled.

## 10. Organizing helpers to create readable test environments

If many tests need the same group of properties, you can create a small factory. The factory should create a new instance on each call and let tests override the keys they need.

~~~java
final class TestEnvironments {

    private TestEnvironments() {
    }

    static MockEnvironment checkoutEnabled() {
        MockEnvironment environment = new MockEnvironment();

        MockPropertySource properties =
                new MockPropertySource("checkoutTest");

        properties.setProperty("feature.checkout.enabled", "true");
        properties.setProperty("service.region", "test-region");

        environment.getPropertySources().addFirst(properties);

        return environment;
    }
}
~~~

A test using the factory:

~~~java
@Test
void enablesCheckoutInConfiguredEnvironment() {
    CheckoutFeature feature =
            new CheckoutFeature(TestEnvironments.checkoutEnabled());

    assertTrue(feature.isEnabled());
}
~~~

If a test needs to disable a feature, create a dedicated fixture or pass a meaningful parameter to the factory rather than mutating global state. Do not build an overly complex test utility suite just to avoid a few lines of setup.

## 11. When to choose each utility?

**Choose MockEnvironment when:**

- A class accepts Environment or ConfigurableEnvironment via its constructor.
- You need to test property-reading logic, default values, or type conversion.
- You need to test active-profile logic at the object level.
- You want tests independent of real system properties or environment variables.

**Choose MockPropertySource when:**

- You need to create an in-memory configuration source.
- You need to test precedence order across multiple sources.
- You need to add, replace, or remove a source by name.
- You need to supply a group of keys to Environment in a test.

**Choose a Spring context test when:**

- You need to verify beans are registered based on properties/profiles.
- You need to test @Value or @ConfigurationProperties binding.
- You need to test auto-configuration, conditional beans, or injection mechanisms.
- You need to prove Spring configuration is actually applied in an ApplicationContext.

MockEnvironment and MockPropertySource are well suited for unit tests because they make configuration data explicit, controllable, and network-free. Use them to test how a component reads and interprets Environment; when the question shifts to how Spring loads configuration, binds properties, or creates beans, switch to the corresponding context test. This distinction keeps tests fast, independent, and focused on proving the exact behavior they are designed to protect.

