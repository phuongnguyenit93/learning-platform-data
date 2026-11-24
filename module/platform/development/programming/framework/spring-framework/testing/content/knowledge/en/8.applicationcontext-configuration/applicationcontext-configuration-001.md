# @ContextConfiguration with Java Configuration Classes

In Spring Framework Test, the `@ContextConfiguration` annotation tells the TestContext Framework which configurations to use to create an `ApplicationContext`. When a project uses Java-based configuration, you pass the configuration classes to the `classes` attribute. Those classes can declare beans using `@Configuration` and `@Bean`, import other configurations, or enable component scanning.

This approach allows a test to build a Spring context with a clear scope: only the beans and configurations that the test needs. It is suitable for plain Spring Framework applications without requiring Spring Boot or `@SpringBootTest`.

## 1. The Role of @ContextConfiguration

The TestContext Framework separates test lifecycle management from how the test framework executes test methods. The `@ContextConfiguration` annotation describes the configuration used to create the context; Spring TestContext reads that metadata, selects the appropriate context loader, loads the beans, and manages the context across test runs.

With Java configuration, the basic declaration is:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // Invoke the service and assert the result.
    }
}
```

Here:

- `@ExtendWith(SpringExtension.class)` connects JUnit Jupiter with the Spring TestContext Framework.
- `@ContextConfiguration(classes = OrderTestConfiguration.class)` specifies the Java class used to create the context.
- `@Autowired` instructs Spring to inject the `OrderService` bean into the test instance.
- `@Test` remains the JUnit Jupiter annotation that controls test execution.

`@ContextConfiguration` belongs to Spring Framework Test. It does not automatically start a Spring Boot application, nor does it automatically create a web server. The context scope depends on the specified configuration classes.

## 2. Declaring Java Configuration with @Configuration and @Bean

A Java configuration class is typically annotated with `@Configuration`. The `@Bean` methods inside describe how to create the objects that Spring will manage.

For example, suppose an application has a service that depends on a repository and a notification gateway:

```java
public interface OrderRepository {
    Order save(Order order);
}

public interface NotificationGateway {
    void orderCreated(Order order);
}

public class OrderService {

    private final OrderRepository orderRepository;
    private final NotificationGateway notificationGateway;

    public OrderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        this.orderRepository = orderRepository;
        this.notificationGateway = notificationGateway;
    }

    public Order create(Order order) {
        Order saved = orderRepository.save(order);
        notificationGateway.orderCreated(saved);
        return saved;
    }
}
```

You can create a configuration dedicated to tests:

```java
@Configuration
public class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }

    @Bean
    OrderService orderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        return new OrderService(orderRepository, notificationGateway);
    }
}
```

The example above assumes `InMemoryOrderRepository` and `RecordingNotificationGateway` are suitable implementations already defined in the test sources or in the application. Spring invokes the `@Bean` methods to create the objects, registers them in the context, and resolves method parameters to the corresponding beans.

Once the context is loaded, the test can receive the bean:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderUsingConfiguredCollaborators() {
        Order input = new Order("customer-1", "SKU-1", 2);

        Order result = orderService.create(input);

        assertThat(result).isEqualTo(input);
    }
}
```

The key point is that the test does not call the `OrderService` constructor directly. Spring creates the bean from the configuration, and then Spring Test injects the bean into the test instance. The test therefore also verifies that the context wires the dependencies according to the Java configuration.

### 2.1. The Role of @Configuration

`@Configuration` marks a class as a source of bean definitions. In the default full configuration mode, Spring can process calls between `@Bean` methods to ensure they reference the managed bean in the context.

For configurations that do not need proxy behavior between `@Bean` methods, you can use `@Configuration(proxyBeanMethods = false)` (available since Spring Framework 5.2). In that mode, if one bean method calls another bean method directly via a normal Java call, that call is not intercepted to retrieve the managed bean. You can pass dependencies via `@Bean` method parameters instead of making cross-method calls.

```java
@Configuration(proxyBeanMethods = false)
class OrderTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(
            OrderRepository orderRepository,
            NotificationGateway notificationGateway) {
        return new OrderService(orderRepository, notificationGateway);
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }
}
```

Passing dependencies via `@Bean` method parameters makes relationships between beans explicit and works well with both full configuration and lite configuration.

### 2.2. Bean Name and Bean Type

By default, the bean name produced by a `@Bean` method is the method name. For example, `orderRepository()` creates a bean named `orderRepository`. You can specify a different name:

```java
@Bean("primaryOrderRepository")
OrderRepository orderRepository() {
    return new InMemoryOrderRepository();
}
```

Spring typically resolves dependencies by type. When multiple beans of the same type exist, you need to use `@Qualifier` or mark the preferred bean with `@Primary` to remove ambiguity:

```java
@Bean
@Primary
OrderRepository inMemoryOrderRepository() {
    return new InMemoryOrderRepository();
}

@Bean
@Qualifier("archive")
OrderRepository archiveOrderRepository() {
    return new ArchiveOrderRepository();
}
```

When a test needs to ensure a specific bean is selected, declare the qualifier at both the bean creation site and the injection point:

```java
@Bean
OrderService orderService(
        @Qualifier("archive") OrderRepository repository,
        NotificationGateway notificationGateway) {
    return new OrderService(repository, notificationGateway);
}
```

## 3. Combining @ContextConfiguration with JUnit Jupiter

`@ContextConfiguration` describes the context, but it does not automatically register the JUnit Jupiter extension. When using this annotation directly with JUnit Jupiter, you need to add:

```java
@ExtendWith(SpringExtension.class)
```

`SpringExtension` implements JUnit Jupiter integration with the Spring TestContext Framework. The extension coordinates test instance preparation, dependency injection, test transaction management, and lifecycle callbacks supported by Spring Test.

### 3.1. Using @SpringJUnitConfig as a Shorthand

Spring provides the composed annotation `@SpringJUnitConfig`. This annotation combines `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // Assertions on orderService.
    }
}
```

The following two declarations are equivalent in configuration intent:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfiguration.class)
class ExplicitConfigurationTest {
}

@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class ComposedAnnotationTest {
}
```

Use `@ContextConfiguration` when you want each annotation to be explicit or need to combine it with other annotations. Use `@SpringJUnitConfig` when you want a concise declaration for JUnit Jupiter tests.

### 3.2. Injecting Beans into the Test Instance

Spring Test can inject dependencies into fields, setters, or constructors of a test class. Field injection is a concise example:

```java
@SpringJUnitConfig(classes = OrderTestConfiguration.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void serviceBeanIsAvailable() {
        assertThat(orderService).isNotNull();
    }
}
```

If you want to use constructor injection for a test class, you can annotate the constructor with `@Autowired` or configure `@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)`. With JUnit Jupiter, you can also set the constructor autowiring mode globally via the `spring.test.constructor.autowire.mode` property. Choose one approach clearly to avoid confusion with JUnit's constructor resolution mechanism.

## 4. Passing Multiple Configuration Classes

An application often splits configurations by responsibility: service, persistence, web, security, or external integrations. The `classes` attribute accepts an array of classes so a test can combine multiple Java configuration sources:

```java
@SpringJUnitConfig(classes = {
        ServiceTestConfiguration.class,
        PersistenceTestConfiguration.class,
        NotificationTestConfiguration.class
})
class OrderIntegrationTest {

    @Autowired
    private OrderService orderService;
}
```

Spring loads the specified configuration classes into the same context. Beans in one configuration can receive dependencies declared in another configuration if their types and qualifiers match.

When multiple tests share a common set of configurations, name the classes to reflect their responsibilities and reuse them. Avoid loading the entire application configuration into every test if the test only needs a small subset; the larger the context, the longer the initialization time and the more dependencies involved.

### 4.1. Composing Configurations with @Import

Instead of listing every class in each test, a root configuration can import smaller configurations:

```java
@Configuration
@Import({
        RepositoryTestConfiguration.class,
        NotificationTestConfiguration.class
})
class OrderServiceTestConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            NotificationGateway notificationGateway) {
        return new OrderService(repository, notificationGateway);
    }
}
```

The test only needs to reference the root configuration:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceTest {
    // Inject OrderService and run the tests.
}
```

`@Import` is useful when an aggregate configuration needs to reuse independent configuration modules. It also prevents a test class from having to know too many internal configuration details.

### 4.2. Component Scanning in Java Configuration

If you want Spring to discover components automatically, you can use `@ComponentScan`. You should limit the package or specify a root class to avoid scanning too broadly:

```java
@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
class ApplicationComponentTestConfiguration {
}
```

`basePackageClasses` lets you specify a marker class; Spring uses the package containing that class as the package to scan. This option relies less on hardcoded package strings than `basePackages`.

When using component scanning, avoid registering the same bean twice via both component scanning and a `@Bean` method. If there are two beans of the same type, injection can become ambiguous or the application might use the wrong implementation.

### 4.3. Static Nested Configuration in a Test Class

For a configuration used by only a single test, you can place a static configuration class inside the test class to keep its scope localized:

```java
@SpringJUnitConfig(classes = OrderServiceTest.Config.class)
class OrderServiceTest {

    @Configuration
    static class Config {

        @Bean
        OrderRepository orderRepository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        NotificationGateway notificationGateway() {
            return new RecordingNotificationGateway();
        }

        @Bean
        OrderService orderService(
                OrderRepository repository,
                NotificationGateway notificationGateway) {
            return new OrderService(repository, notificationGateway);
        }
    }

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        assertThat(orderService).isNotNull();
    }
}
```

A nested configuration must be `static` so Spring can instantiate it independently of a test class instance. This approach is suited for small, isolated configurations; if multiple tests share it, move the configuration into a separate class for reuse.

## 5. Using Profiles and Properties in the Test Context

Java configuration can read properties or create beans based on profiles. Spring Test provides annotations to control the environment when loading the context.

### 5.1. Selecting Profiles with @ActiveProfiles

`@ActiveProfiles` activates one or more profiles for the test's context:

```java
@Configuration
class OrderConfiguration {

    @Bean
    @Profile("test")
    NotificationGateway testNotificationGateway() {
        return new RecordingNotificationGateway();
    }

    @Bean
    @Profile("production")
    NotificationGateway productionNotificationGateway() {
        return new SmtpNotificationGateway();
    }
}

@SpringJUnitConfig(classes = OrderConfiguration.class)
@ActiveProfiles("test")
class OrderProfileTest {

    @Autowired
    private NotificationGateway notificationGateway;
}
```

In this test, Spring only registers the bean whose `test` profile is active. `@ActiveProfiles` keeps test configuration independent from the default profile of the application runtime environment.

### 5.2. Loading Properties with @TestPropertySource

`@TestPropertySource` adds a property source to the test context. You can specify files or inline properties:

```java
@Configuration
class FeatureConfiguration {

    @Value("${orders.max-items:10}")
    private int maxItems;

    @Bean
    OrderLimit orderLimit() {
        return new OrderLimit(maxItems);
    }
}

@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(properties = "orders.max-items=25")
class OrderLimitTest {

    @Autowired
    private OrderLimit orderLimit;
}
```

The example assumes the application has an `OrderLimit` class that accepts the item limit. Inline properties help tests control configuration input values. If a configuration requires many properties or is shared, you can use a resource file:

```java
@TestPropertySource(locations = "classpath:/order-test.properties")
```

Property values can be read using `@Value` or through the appropriate Spring Framework binding mechanism. With plain Java config, tests can use `Environment` inside a `@Bean` method if they want to read values explicitly.

## 6. Initializers and Context Loaders

Usually, passing Java config via `classes` is enough. Spring Test will select the appropriate default context loader to load the configuration. You do not need to specify a loader manually in common cases.

### 6.1. ApplicationContextInitializer

When you need to customize the context before it is refreshed, you can use an `ApplicationContextInitializer`. The initializer receives the unrefreshed context and can register additional property sources or bean definitions:

```java
public class TestPropertyInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of("feature.enabled", "true");
        MapPropertySource source = new MapPropertySource("testOverrides", values);
        context.getEnvironment().getPropertySources().addFirst(source);
    }
}
```

Declare the initializer in the test:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = FeatureConfiguration.class,
        initializers = TestPropertyInitializer.class
)
class FeatureInitializerTest {
}
```

The initializer runs during the context preparation phase. Use it only when environment setup must happen before beans are created; for simple properties, `@TestPropertySource` is usually easier to read.

### 6.2. When Do You Need to Specify a Context Loader?

The `loader` attribute of `@ContextConfiguration` lets you specify a custom `ContextLoader` implementation (modern loaders typically implement the `SmartContextLoader` extension contract). With standard Java configuration, the default loader already supports loading configuration classes, so setting this attribute is usually unnecessary.

Only write a custom loader when you have a specialized context-loading mechanism that standard loaders do not support. Specifying an incorrect loader can cause Spring to misinterpret `locations` or `classes`, resulting in the context not being created as expected.

## 7. Inheriting Configuration Between Test Classes

If a group of tests shares a common configuration, you can place the annotation on a superclass:

```java
@SpringJUnitConfig(classes = SharedServiceTestConfiguration.class)
abstract class BaseServiceTest {

    @Autowired
    protected OrderService orderService;
}

class CreateOrderTest extends BaseServiceTest {

    @Test
    void createsOrder() {
        // Use the injected orderService.
    }
}
```

By default, context configuration is inherited. A child test class can add its own configuration classes:

```java
@ContextConfiguration(classes = SpecialCaseTestConfiguration.class)
class SpecialOrderTest extends BaseServiceTest {
}
```

When inherited, local configuration classes are typically merged with the superclass's configuration. If you want to replace the inherited configuration completely, you can set `inheritLocations = false`:

```java
@ContextConfiguration(
        classes = IsolatedTestConfiguration.class,
        inheritLocations = false
)
class IsolatedOrderTest extends BaseServiceTest {
}
```

The attribute name `inheritLocations` is retained from the original test configuration model and applies to the inherited `locations` or `classes` set. Use it when a subclass genuinely needs an independent set of configurations; if it only needs additional beans, merging configurations is usually easier to maintain.

## 8. Context Caching and @DirtiesContext

The Spring TestContext Framework caches `ApplicationContext` instances so tests with compatible configurations can reuse an already created context. Caching reduces execution time when a test suite has multiple classes using the same configuration.

The cache key is built from configuration metadata, such as:

- Configuration classes or resource locations.
- Context initializers.
- Active profiles.
- Property sources and inline properties.
- Context loaders and context customizers.
- Other related configurations managed by Spring TestContext.

If two tests use the same metadata, Spring can reuse the context. If the configuration changes, the context may have a different cache key and be created separately.

### 8.1. When to Use @DirtiesContext

`@DirtiesContext` marks a context as having been mutated by a test to the point where it should not be reused. Spring Test removes that context from the cache according to the selected mode and recreates it when needed.

```java
@SpringJUnitConfig(classes = MutableStateTestConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // Test mutates shared bean state and requires a fresh context after the class.
}
```

Do not use `@DirtiesContext` as a way to clean up all state after every test. If the issue is just data in a repository or collection, reset the data using an appropriate API. Recreating a context is expensive and can hide poor state management in tests.

## 9. Distinguishing @ContextConfiguration from Other Annotations

| Annotation | Role | When to Use |
|---|---|---|
| `@ContextConfiguration` | Specifies configurations or classes for TestContext to create an ApplicationContext. | When a test needs a Spring context explicitly defined via Java config or resources. |
| `@SpringJUnitConfig` | Combines SpringExtension with ContextConfiguration for JUnit Jupiter. | When writing Spring context tests on JUnit Jupiter. |
| `@ExtendWith(SpringExtension.class)` | Connects JUnit Jupiter with the Spring TestContext Framework. | When using the ContextConfiguration annotation directly along with Spring Test utilities. |
| `@SpringBootTest` | Bootstraps a Spring Boot application using Boot's mechanism. | When testing Boot application configuration, auto-configuration, and integration. |
| `@WebAppConfiguration` | Instructs TestContext to create a Servlet API-based web application context. | When a test needs a web application context in a Spring Framework Test environment. |

`@ContextConfiguration` does not enable component scanning automatically if the Java configuration does not declare `@ComponentScan` or import a configuration that scans. Nor does it automatically create a servlet environment just because controller classes are in the configuration list.

If the goal is to verify wiring of a few Spring Framework beans, Java config combined with `@ContextConfiguration` is sufficient. If the goal is to test a Boot application bootstrapped with auto-configuration, use Boot's test annotations and infrastructure.

## 10. Complete Example: Testing with Multiple Java Configurations

The example below illustrates a test configuration split into two classes: one declaring the repository and gateway, and one creating the service. The test uses `@SpringJUnitConfig` to load the composite configuration.

```java
@Configuration(proxyBeanMethods = false)
class RepositoryTestConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}

@Configuration(proxyBeanMethods = false)
class GatewayTestConfiguration {

    @Bean
    NotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }
}

@Configuration(proxyBeanMethods = false)
@Import({
        RepositoryTestConfiguration.class,
        GatewayTestConfiguration.class
})
class OrderServiceTestConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            NotificationGateway notificationGateway) {
        return new OrderService(repository, notificationGateway);
    }
}

@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceContextTest {

    @Autowired
    private OrderService orderService;

    @Test
    void contextProvidesOrderService() {
        assertThat(orderService).isNotNull();
    }

    @Test
    void createsOrderUsingBeansFromImportedConfigurations() {
        Order order = new Order("customer-1", "SKU-1", 2);

        assertThat(orderService.create(order)).isEqualTo(order);
    }
}
```

The `InMemoryOrderRepository` and `RecordingNotificationGateway` implementations are example test fixtures. If a real repository or database connection is used, the test expands in scope to a persistence integration test; in that case, appropriate database configuration must be added.

## 11. Common Mistakes

### Using @ContextConfiguration Without SpringExtension

With JUnit Jupiter, `@ContextConfiguration` only describes metadata. If the test class does not use `@ExtendWith(SpringExtension.class)` or a composed annotation such as `@SpringJUnitConfig`, Spring Test is not integrated to prepare the context and inject dependencies along the test lifecycle.

### Passing the Wrong Class to the classes Attribute

The classes in `classes` must be component/configuration classes that can be used to load a context. If a class declares no beans, is not a component, and does not import other configurations, the context may not contain the bean the test expects.

### Forgetting @Bean or @ComponentScan

Having a Java class in the source code does not mean Spring automatically registers it as a bean. Declare `@Bean`, use stereotype annotations with component scanning, or import a configuration that contains the bean.

### Multiple Beans of the Same Type

If multiple configuration classes declare the same interface, Spring may not know which bean to inject. Use `@Qualifier`, `@Primary`, or narrow the configuration to make the choice explicit.

### Mixing Java Configuration and Component Scan Causing Duplicate Beans

If a class is already discovered via `@ComponentScan` and is also declared with `@Bean`, the context may end up with multiple beans serving the same responsibility. Check scan packages and bean registration to avoid conflicts.

### Expecting @Value to Work Without a Context

`@Value` is processed by Spring during bean creation. If a test calls `new` directly on a class containing a `@Value` field, the field will not receive properties automatically. Load the bean through a context or pass the value via a constructor.

### Using @DirtiesContext Too Frequently

Marking a context dirty reduces the benefits of caching and increases test execution time. Use it only when context state has genuinely been altered and cannot be safely reset at the bean or data level.

### Confusing @ContextConfiguration with @SpringBootTest

`@ContextConfiguration` uses Spring TestContext to load specified classes or resources. `@SpringBootTest` tells Spring Boot to bootstrap the application and apply Boot's auto-configuration mechanism. Choose the annotation based on the context scope the test requires.

## 12. Choosing a Configuration Approach for Each Test

- Need a few beans from Java configuration? Use `@ContextConfiguration(classes = ...)` with `SpringExtension`.
- Want a concise declaration on JUnit Jupiter? Use `@SpringJUnitConfig(classes = ...)`.
- Need to combine multiple configurations? Pass multiple classes in `classes` or use `@Import`.
- Need automatic component discovery? Declare `@ComponentScan` with a clear package scope.
- Need specific profiles or properties? Combine `@ActiveProfiles` and `@TestPropertySource`.
- Need to modify the environment before context refresh? Use `ApplicationContextInitializer`.
- Need Boot application bootstrapping and auto-configuration? Choose `@SpringBootTest`.

When using Java configuration with `@ContextConfiguration`, treat the configuration class as a description of the object graph the test needs. Declare beans explicitly, import the right configuration modules, and let Spring Test manage the context and test lifecycle. This organization keeps tests focused on integration among Spring Framework beans without depending on Spring Boot's bootstrapping mechanism.
