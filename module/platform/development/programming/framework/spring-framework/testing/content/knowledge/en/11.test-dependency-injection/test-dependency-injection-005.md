# Injecting ApplicationContext and Environment

In Spring tests, a test sometimes needs direct access to `ApplicationContext` or `Environment` to verify configuration, check registered beans, and read test environment properties. The Spring TestContext Framework supports injecting both objects into the test instance via dependency injection. This lets the test observe the context created by the framework and verify the active configuration values.

`ApplicationContext` represents Spring's bean-managing container. `Environment` provides information about profiles and the property sources used by the application. The two objects are closely related, yet serve two different purposes: context gives access to beans and application structure; environment gives access to profiles and configuration properties.

## 1. What are ApplicationContext and Environment?

### ApplicationContext

`ApplicationContext` is the central interface of the Spring IoC container. It extends `BeanFactory` and provides additional capabilities such as:

- Accessing registered beans by name or type.
- Accessing resources via the `ResourceLoader` mechanism.
- Publishing and receiving application events.
- Resolving messages via `MessageSource`.
- Exposing the `Environment` bound to the context.
- Supporting parent-child contexts in hierarchical application structures.

In an application, Spring builds the `ApplicationContext` from Java configuration, XML, component scanning, or Spring Boot configuration. Beans are created and wired in the context according to the declared dependency graph.

### Environment

`Environment` is an abstraction representing the runtime environment of the application. It aggregates two main groups of information:

- **Profiles:** active or default profiles used to select matching beans and configurations.
- **Properties:** properties aggregated from multiple `PropertySource` instances, such as JVM system properties, environment variables, configuration files, and test-specific properties.

An `Environment` can answer questions such as:

- Is the `test` profile active?
- What is the value of the `feature.inventory.enabled` property?
- Does the required `service.endpoint` property exist?
- Can the configuration value be converted into a number, boolean, or another data type?

### Relationship between the two objects

`ApplicationContext` exposes its own `Environment` through the `getEnvironment()` method. Therefore, in a typical test context, the injected `Environment` is the configuration environment used by that context.

~~~text
Spring TestContext Framework
          |
          v
   ApplicationContext
          |
          +---- Bean definitions and bean instances
          |
          +---- Environment
                    |
                    +---- Active / default profiles
                    |
                    +---- First PropertySource
                    +---- Second PropertySource
                    +---- Next PropertySource
~~~

A test can inject `ApplicationContext` to access beans while also injecting `Environment` to read configuration. If you only need to read a property, injecting `Environment` directly is usually simpler than retrieving `Environment` from `ApplicationContext`.

## 2. How does Spring inject both objects into the test instance?

The TestContext Framework integrates with JUnit via `SpringExtension`. During test instance preparation, `DependencyInjectionTestExecutionListener` instructs Spring to perform autowiring on the test class's injection fields or methods. `ApplicationContext` and `Environment` are infrastructure objects that Spring can supply to tests.

Simple example:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextAndEnvironmentTest {
    @Autowired
    private ApplicationContext applicationContext;

    @Autowired
    private Environment environment;

    @Test
    void injectsContextAndEnvironment() {
        assertNotNull(applicationContext);
        assertNotNull(environment);
    }
}
~~~

`@SpringJUnitConfig` combines registering `SpringExtension` with context configuration for JUnit Jupiter. When the test runs, Spring creates or retrieves the matching `ApplicationContext` from the context cache, then injects the required objects into the test instance.

The test class remains managed by JUnit. `ApplicationContext` is created and managed by Spring TestContext. Injecting the context into a test does not turn the test class into an application bean.

If you use `@ContextConfiguration` instead of `@SpringJUnitConfig`, you must register `SpringExtension` separately:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class ContextAndEnvironmentWithExtensionTest {
    // ApplicationContext and Environment can be injected here.
}
~~~

With JUnit Jupiter, `@SpringJUnitConfig` is usually more concise for standard cases.

## 3. Injecting ApplicationContext to inspect beans

Once injected, the test can use `ApplicationContext` to verify that beans are registered, check bean types, or retrieve a specific bean.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void registersInventoryService() {
        assertTrue(context.containsBean("inventoryService"));

        InventoryService service =
                context.getBean(InventoryService.class);

        assertNotNull(service);
    }
}
~~~

Commonly used methods:

| Method | Purpose |
|---|---|
| `getBean(Class<T>)` | Retrieve a bean by type |
| `getBean(String)` | Retrieve a bean by name |
| `getBean(String, Class<T>)` | Retrieve a bean by name and check its type |
| `containsBean(String)` | Check whether a bean name exists in the context |
| `getBeanNamesForType(Class<?>)` | Get bean names matching a type |
| `getBeansOfType(Class<T>)` | Get beans matching a type as a map |
| `getParent()` | Access the parent context if present |
| `getEnvironment()` | Get the `Environment` attached to the context |

If multiple beans implement the same interface, `getBean(Interface.class)` can throw `NoUniqueBeanDefinitionException`. In that case, the test can look up by bean name, inspect the set of beans by type, or verify qualifier/primary configuration.

Example verifying multiple implementations:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentTestConfig.class)
class PaymentConfigurationTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void registersTheExpectedPaymentGateways() {
        Map<String, PaymentGateway> gateways =
                context.getBeansOfType(PaymentGateway.class);

        assertEquals(2, gateways.size());
        assertTrue(gateways.containsKey("cardPaymentGateway"));
        assertTrue(gateways.containsKey("bankTransferGateway"));
    }
}
~~~

This test snippet illustrates inspecting the bean graph. In an actual test, the test class needs a corresponding Spring configuration, such as `@SpringJUnitConfig(PaymentTestConfig.class)`.

### Checking beans by name and type

A bean name can be generated from the class name when using component scanning or explicitly specified in `@Bean`. When a test checks a bean name, it asserts a configuration detail. Only lock down the bean name when that name is a meaningful part of the configuration contract; otherwise, checking by type or behavior is usually less coupled to naming choices.

~~~java
@Configuration
class InventoryTestConfig {
    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}
~~~

The test can retrieve `InventoryService` by type without knowing the bean name generated by the configuration method. This approach is appropriate when you only need to verify that the context can supply a bean according to its contract.

## 4. Injecting Environment to read properties

`Environment` allows tests to read properties aggregated from different configuration sources. The `getProperty()` method returns `null` if the property is not found; you can provide a default value or require the property to be present.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(properties = {
        "feature.inventory.enabled=true",
        "inventory.retry-count=3",
        "inventory.region=ap-southeast-1"
})
class EnvironmentPropertyTest {
    @Autowired
    private Environment environment;

    @Test
    void readsTestProperties() {
        assertEquals(
                "true",
                environment.getProperty("feature.inventory.enabled"));

        assertEquals(
                3,
                environment.getProperty("inventory.retry-count", Integer.class));

        assertEquals(
                "ap-southeast-1",
                environment.getRequiredProperty("inventory.region"));

        assertFalse(
                environment.getProperty("feature.missing", Boolean.class, false));
    }
}
~~~

In the example, `@TestPropertySource` adds properties to the test context's environment. The test reads values via `Environment` without directly accessing the operating system or configuration files. The `getProperty(key, targetType)` method asks Spring to convert the value to the target type using the appropriate conversion mechanism.

Common ways to read properties:

~~~java
String endpoint = environment.getProperty("service.endpoint");

String endpointOrDefault = environment.getProperty(
        "service.endpoint",
        "http://localhost:8080");

int timeout = environment.getProperty(
        "service.timeout",
        Integer.class,
        2000);

String requiredEndpoint = environment.getRequiredProperty(
        "service.endpoint");
~~~

`getRequiredProperty()` throws `IllegalStateException` when the property does not exist. This is suitable when the test needs to confirm a required configuration was provided. For optional configuration, using `getProperty()` with a default value expresses the intent better.

### Checking whether a property exists

`Environment` has `containsProperty()` to check whether a key can be resolved from current property sources:

~~~java
assertTrue(environment.containsProperty("service.endpoint"));
~~~

`containsProperty()` only verifies that the key can be found. If you need to verify the value or data type, read the property and assert on the result.

## 5. Reading and checking active profiles

Profiles allow Spring to select beans or configurations per environment, such as `test`, `development`, `staging`, or `production`. `Environment` exposes the list of active profiles and default profiles.

A test can declare profiles using `@ActiveProfiles`:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
class ActiveProfileTest {
    @Autowired
    private Environment environment;

    @Test
    void activatesTheTestProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
    }
}
~~~

You can also read the profiles directly:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
~~~

`getActiveProfiles()` returns the profiles that have been activated. If no profile is active, Spring may fall back to the default profile, typically `default`. `getDefaultProfiles()` returns the default profile set of the `Environment`.

The `acceptsProfiles(Profiles.of("test"))` method checks profile conditions using Spring's profile expression. For multiple profiles, you can write:

~~~java
boolean testOrIntegration = environment.acceptsProfiles(
        Profiles.of("test", "integration"));
~~~

In this expression, `Profiles.of("test", "integration")` means the test accepts if either of the listed profiles is active. You can use negation in profile expressions, such as `!production`, when checking inverse conditions.

### Which beans are affected by profiles?

`@Profile` can control bean registration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class PaymentConfiguration {
    @Bean
    @Profile("test")
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway livePaymentGateway() {
        return new LivePaymentGateway();
    }
}
~~~

The test can inject `Environment` to confirm the `test` profile is active and use `ApplicationContext` to confirm the matching bean is registered:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentConfiguration.class)
@ActiveProfiles("test")
class PaymentProfileTest {
    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Test
    void loadsTheFakeGatewayForTests() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertTrue(context.containsBean("fakePaymentGateway"));
        assertFalse(context.containsBean("livePaymentGateway"));
    }
}
~~~

The example shows how the two objects support two kinds of assertions: `Environment` verifies the profile; `ApplicationContext` verifies the resulting bean graph from that profile.

## 6. Checking properties and profiles together

A configuration test can verify both profiles and property values. For example, an application enables a feature based on the `test` profile and a property:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
class FeatureTestConfig {
    @Bean
    @Profile("test")
    FeatureService featureService(Environment environment) {
        boolean enabled = environment.getProperty(
                "feature.inventory.enabled",
                Boolean.class,
                false);
        return new FeatureService(enabled);
    }
}

class FeatureService {
    private final boolean enabled;

    FeatureService(boolean enabled) {
        this.enabled = enabled;
    }

    boolean isEnabled() {
        return enabled;
    }
}
~~~

The test can supply both the profile and the property:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.inventory.enabled=true")
class FeatureEnvironmentTest {
    @Autowired
    private Environment environment;

    @Autowired
    private FeatureService featureService;

    @Test
    void loadsFeatureConfigurationForTestProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertTrue(environment.getProperty(
                "feature.inventory.enabled",
                Boolean.class,
                false));
        assertTrue(featureService.isEnabled());
    }
}
~~~

Here, the bean configuration reads `Environment` when Spring creates `FeatureService`. The test simultaneously checks the property value and the behavior of the created bean. If you only need to check the property, asserting on `Environment` is enough; if you need to confirm the property actually affects bean configuration, verify the corresponding bean or behavior as well.

## 7. Environment and @Value serve different roles

`@Value` is a mechanism to inject a resolved value into a field, constructor parameter, or method. `Environment` is an abstraction that allows querying multiple properties flexibly at runtime.

Example using `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class InventoryClientSettings {
    private final String endpoint;
    private final int timeout;

    InventoryClientSettings(
            @Value("\u0024{inventory.endpoint}") String endpoint,
            @Value("\u0024{inventory.timeout:2000}") int timeout) {
        this.endpoint = endpoint;
        this.timeout = timeout;
    }

    String endpoint() {
        return endpoint;
    }

    int timeout() {
        return timeout;
    }
}
~~~

Example using `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventoryEndpointResolver {
    private final Environment environment;

    InventoryEndpointResolver(Environment environment) {
        this.environment = environment;
    }

    String endpointFor(String region) {
        String key = "inventory.endpoint." + region;
        return environment.getRequiredProperty(key);
    }
}
~~~

`@Value` fits when a bean needs a fixed set of configured values. `Environment` fits when you need to look up properties by dynamic keys, check profiles, or handle a dynamic set of properties. For configurations with many related fields, `@ConfigurationProperties` generally provides a cleaner typed model.

In tests, you can inject `Environment` to verify property sources and inject the settings bean to verify the final bound values. Do not replace all bean configuration tests with mere property reads, because beans can also apply defaults, validation, or custom conversion logic.

## 8. PropertySource and precedence order

`Environment` aggregates values from multiple `PropertySource` instances. When the same key appears in multiple sources, precedence order determines which value is returned.

Common sources include:

- JVM system properties, such as `-Dinventory.timeout=3000`.
- Operating system environment variables.
- Application configuration files.
- Properties declared with `@TestPropertySource`.
- Dynamic properties registered via `@DynamicPropertySource`.
- Property sources added by custom configuration or framework integrations.

With the Spring TestContext Framework, inline properties of `@TestPropertySource` have higher precedence than resource locations declared in the same annotation. Other property sources follow specific ordering rules under `Environment` and `TestContext`. In Spring Boot, Config Data and Boot configuration sources also participate in Boot's precedence hierarchy.

Tests can inspect the active `PropertySource` entries:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySource;

void printPropertySources(Environment environment) {
    ConfigurableEnvironment configurableEnvironment =
            (ConfigurableEnvironment) environment;

    for (PropertySource<?> source :
            configurableEnvironment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

`Environment` is a query-focused interface. To iterate over the `PropertySource` list, use `ConfigurableEnvironment`, an extended interface exposing configuration APIs and access to `PropertySources`. In tests, if the goal is to inspect ordering, you can cast when the actual context provides a `ConfigurableEnvironment`.

~~~java
ConfigurableEnvironment configurableEnvironment =
        (ConfigurableEnvironment) environment;

MutablePropertySources propertySources =
        configurableEnvironment.getPropertySources();

PropertySource<?> highestPrioritySource =
        propertySources.iterator().next();
~~~

The snippet above requires importing `MutablePropertySources`. Do not assume a `PropertySource` has the exact same name or position across all versions and context types. Use `environment.getProperty(key)` to check effective values; only inspect property sources when diagnosing where a value comes from.

## 9. Using ApplicationContext and Environment in a context hierarchy

A test can load a parent context and a child context. The child context can access beans from the parent context while having its own `Environment` attached to the context. Injecting `ApplicationContext` into the test lets you inspect the context the test uses; `getParent()` checks the hierarchy relationship when a parent is configured.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.ContextHierarchy;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void exposesTheParentContextWhenConfigured() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);
    }
}
~~~

This test must be declared with `@ContextHierarchy` or an equivalent configuration to have a parent context. Without a hierarchy, `getParent()` can return `null`. In the example, `@ContextHierarchy` integrates hierarchical context configuration; you do not also need `@SpringJUnitConfig`.

With hierarchical contexts, beans from the parent can be found through the child context. Therefore, `containsBean()` or `getBean()` on the child can see beans inherited from the parent. If you need to verify at which level a bean is defined, query the parent separately and compare with the child.

A context's `Environment` may be influenced by parent-child relationships and property source configuration. When checking profiles or properties in a hierarchy, be clear about which context the test injects and at which configuration level the value is supplied.

## 10. Injecting via constructor or test method parameters

In addition to field injection, `SpringExtension` supports parameter injection for JUnit Jupiter. This is useful when only a single test method needs `ApplicationContext` or `Environment`.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextParameterTest {
    @Test
    void receivesContextAndEnvironment(
            @Autowired ApplicationContext context,
            @Autowired Environment environment) {
        assertNotNull(context);
        assertNotNull(environment);
    }
}
~~~

If you want constructor parameter injection for the whole test class, you can use `@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)` or configure the global autowire mode per Spring TestContext. `SpringExtension` will then participate in resolving constructor parameters.

Choose field injection when many test methods share the context or environment. Choose method parameter injection when only a few methods need them and you want dependencies expressed directly in the method signature. Neither approach turns the test class into a bean.

## 11. Avoid using ApplicationContext as a service locator in application code

`ApplicationContext` can look up beans by name or type, but that does not mean every service should receive the context and pull dependencies on demand.

Example of hidden dependency design:

~~~java
public class OrderService {
    private final ApplicationContext context;

    public OrderService(ApplicationContext context) {
        this.context = context;
    }

    public void placeOrder(Order order) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge(order);
    }
}
~~~

The constructor only shows that `OrderService` depends on `ApplicationContext`; the real dependency `PaymentGateway` is hidden inside the method. Unit tests must create or mock an entire `ApplicationContext` and stub `getBean()`. That couples tests to the bean lookup mechanism and makes the dependency graph hard to read.

A clearer design injects the collaborator directly:

~~~java
public class OrderService {
    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public void placeOrder(Order order) {
        paymentGateway.charge(order);
    }
}
~~~

`ApplicationContext` injection is useful in tests that inspect container configuration or in certain infrastructure components that genuinely need container access. For normal business logic, constructor injection of specific dependencies makes code easier to understand and test.

`Environment` should also be used deliberately. A bean needing a fixed set of configuration values can usually receive them via its constructor or `@ConfigurationProperties`. Injecting the whole `Environment` into many services to look up arbitrary properties can scatter configuration and make it hard to track.

## 12. Do not arbitrarily mutate context or Environment in tests

`ApplicationContext` and `Environment` are shared across tests with the same cache key. If one test mutates property sources or shared bean state, another test may observe the altered state.

`ConfigurableEnvironment` allows adding, removing, or reordering `PropertySource` entries. This API is useful while building a context, but mutating it after the context is already in use can make test results depend on execution order.

When configuring properties for tests, prefer declarative mechanisms:

- `@TestPropertySource` for fixed test properties.
- `@ActiveProfiles` for test profiles.
- `@DynamicPropertySource` for values only available at runtime, such as Testcontainers ports.
- Dedicated test configuration or bean overrides for dependencies that need replacement.

Example of static property declaration:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(properties = {
        "inventory.endpoint=http://localhost:8081",
        "inventory.timeout=1500"
})
class InventoryEndpointTest {
    @Autowired
    private Environment environment;

    @Test
    void readsTheConfiguredEndpoint() {
        assertEquals(
                "http://localhost:8081",
                environment.getRequiredProperty("inventory.endpoint"));
    }
}
~~~

If you genuinely need to add a `PropertySource` programmatically, do it during context initialization via an initializer or appropriate configuration mechanism. Avoid adding property sources inside a test method and expecting other tests to remain isolated.

## 13. Common mistakes when injecting ApplicationContext and Environment

### Test does not receive injection

If `ApplicationContext` or `Environment` fields remain `null`, verify that the test integrates `SpringExtension`. With JUnit Jupiter, use `@SpringJUnitConfig` or combine `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. Also verify the test is running on JUnit Jupiter rather than another test engine that does not support the same mechanism.

### Bean not found when calling getBean()

`NoSuchBeanDefinitionException` indicates the current context has no matching bean. Check that the configuration class is loaded, component scanning covers the required package, the profile is active, and bean registration conditions are met.

### Multiple beans of the same type

`NoUniqueBeanDefinitionException` occurs when looking up by type and multiple beans match. Use the bean name, a qualifier, or inspect the set of beans by type. If the application needs a default choice, explicitly specify `@Primary` or `@Qualifier` in the configuration.

### Property returns null

`Environment.getProperty()` returns `null` when the key is not found. Check spelling, loaded property sources, profiles, resource paths, and precedence. Use `getRequiredProperty()` when a missing property must be treated as an error.

### Reading the wrong profile

`getActiveProfiles()` can return an empty array if the test does not explicitly activate a profile. In that case, Spring uses the default profile. Declare `@ActiveProfiles` if the test requires a specific profile and check with `acceptsProfiles(Profiles.of(...))`.

### Property source mutated between tests

If a test modifies `ConfigurableEnvironment` or mutates a singleton bean, the context cache can preserve that state across multiple tests. Move configuration to annotations or initializers and clean up shared state using a lifecycle-aware mechanism.

### Manually closing ApplicationContext

Do not manually close the context injected into a test. The TestContext Framework manages the context cache and context shutdown lifecycle when appropriate. Closing the context manually can cause other tests sharing the same cache entry to fail. Only manage the lifecycle of contexts that the test itself creates independently outside TestContext.

## 14. Comprehensive example: checking beans, profiles, and properties

The following example combines profile-based bean configuration with properties supplied to the test:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

interface NotificationGateway {
    String endpoint();
}

class TestNotificationGateway implements NotificationGateway {
    private final String endpoint;

    TestNotificationGateway(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String endpoint() {
        return endpoint;
    }
}

@Configuration
class NotificationTestConfig {
    @Bean
    @Profile("test")
    NotificationGateway notificationGateway(Environment environment) {
        String endpoint = environment.getRequiredProperty(
                "notification.endpoint");
        return new TestNotificationGateway(endpoint);
    }
}
~~~

Test injecting both `ApplicationContext` and `Environment`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NotificationTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties =
        "notification.endpoint=http://localhost:9090")
class NotificationContextTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private Environment environment;

    @Test
    void exposesTheExpectedTestConfiguration() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertEquals(
                "http://localhost:9090",
                environment.getRequiredProperty("notification.endpoint"));

        NotificationGateway gateway =
                context.getBean(NotificationGateway.class);

        assertEquals(
                "http://localhost:9090",
                gateway.endpoint());
    }
}
~~~

The test verifies three things: the `test` profile is active, `Environment` provides the expected endpoint, and `ApplicationContext` contains a `NotificationGateway` built from that configuration. The configuration does not need to start an external endpoint because the test implementation simply holds the endpoint value to demonstrate property binding.

## 15. Usage guidelines

- Inject `ApplicationContext` when a test needs to inspect the bean graph, container configuration, or parent-child context relationships.
- Inject `Environment` when a test needs to check profiles, property sources, or effective configuration values.
- Use `getProperty()` for optional properties and `getRequiredProperty()` for required properties.
- Use `getProperty(key, type)` to retrieve values already converted to the target type.
- Use `getActiveProfiles()`, `getDefaultProfiles()`, and `acceptsProfiles()` to verify profiles.
- Use `@TestPropertySource`, `@ActiveProfiles`, or `@DynamicPropertySource` to supply configuration for tests.
- Use `@Autowired` on fields, constructors, or method parameters via `SpringExtension` depending on scope.
- Distinguish mocks in a test fixture from beans in `ApplicationContext`; use bean overrides when replacing a dependency in the context.
- Do not use `ApplicationContext` as a service locator in regular business logic; inject concrete dependencies via constructors.
- Do not mutate `Environment` or close a TestContext-managed context inside a test method.
- Use logging and property source queries when diagnosing configuration sources, but prefer verifying effective values via `Environment`.

`ApplicationContext` and `Environment` are two useful infrastructure objects in Spring testing. The context lets you verify registered and wired beans; `Environment` lets you verify active profiles and properties. When you inject the right object and keep configuration inspection properly scoped, tests can verify how Spring assembles the application while maintaining a clear boundary between test fixtures and container-managed beans.
