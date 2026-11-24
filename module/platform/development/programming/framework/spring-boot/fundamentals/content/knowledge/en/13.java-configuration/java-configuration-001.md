# @Configuration and @Bean Methods

In Spring, a bean does not have to be a class you wrote and annotated with `@Component` or `@Service`. You can also **declare how to create a bean using a Java method**. Spring invokes that method as a factory method, takes the returned object, and manages it according to the bean definition.

This style of declaration is commonly used with `@Configuration` and `@Bean`:

- `@Configuration` marks a class that contains bean configuration.
- `@Bean` marks a method that provides a bean to the Spring container.
- Parameters of a `@Bean` method can represent dependencies that Spring must resolve before invoking the method.
- The return value becomes a container-managed object with its corresponding scope and lifecycle.

This is **Java-based configuration**: configuring an application using typed Java code with IDE refactoring support. This mechanism is especially useful when creating beans from third-party libraries, when constructor/factory customization is needed, or when you want to group a module's configuration in one clear place.

## 1. Why Are `@Configuration` and `@Bean` Needed?

For a class you own, component scanning can be used:

```java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Spring detects `@Service` within the scanned package and registers a bean definition for that class.

However, not every class can or should be modified to add annotations. For example, `Clock` belongs to the JDK, `ObjectMapper` belongs to a JSON library, and `DataSource` may be created by a database connection library. You may want to:

- Choose a specific constructor or static factory.
- Pass configuration parameters during instantiation.
- Create an implementation suited to the environment.
- Specify bean names, scope, or lifecycle callbacks.
- Register a library class without modifying its source code.

In these cases, a `@Bean` factory method is the natural choice:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

The `applicationClock()` method creates a `Clock`. Spring invokes the method during bean creation and manages the returned object. `Clock` does not need to carry any Spring annotation.

**`@Bean` declares a bean definition through a factory method; it does not turn the entire returned class into a component for component scanning to discover.** The container manages the instance provided by the factory method.

## 2. What Is `@Configuration`?

`@Configuration` is an annotation that marks a class as a source of bean definitions. A configuration class typically groups beans related to a single topic:

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    public PaymentService paymentService(
            PaymentGateway paymentGateway) {
        return new PaymentService(paymentGateway);
    }
}
```

When `PaymentConfiguration` is loaded into the Spring context, Spring processes the `@Bean` methods inside it and registers the corresponding beans.

A `@Configuration` class is typically brought into the context via component scanning, `@Import`, or another configuration. `@Configuration` is meta-annotated with `@Component`, so it is itself a component scan candidate.

Example package layout:

```text
com.example.shop/
├── ShopApplication.java
├── config/
│   └── PaymentConfiguration.java
├── service/
│   └── PaymentService.java
└── api/
    └── PaymentController.java
```

If the main class has `@SpringBootApplication` in the `com.example.shop` package, configurations in the `config` subpackage are normally discovered by component scanning.

### How Does `@Configuration` Differ from `@Component`?

Both can serve as a source of bean declarations using `@Bean`, but `@Configuration` carries dedicated configuration semantics and defaults to proxying bean methods.

| Class declaration | Can contain `@Bean`? | Default handling of calls between `@Bean` methods |
|---|---|---|
| `@Configuration` | Yes | Full configuration: Spring enhances the configuration class to intercept calls between bean methods. |
| `@Configuration(proxyBeanMethods = false)` | Yes | Lite configuration: direct Java calls, no interception. |
| `@Component` | Yes | Lite configuration: direct Java calls, no interception. |

Therefore, `@Configuration` is not just another name for `@Component`. It provides additional semantics for calls between `@Bean` methods when used in full mode.

## 3. How Does `@Bean` Work?

A `@Bean` method is a **factory method**. Spring invokes the method, receives the return value, and uses it as the bean instance.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Components of the declaration:

- `@Bean`: marks the method as a bean-producing source.
- `appClock`: default bean name.
- `Clock`: return type, indicating the type of object the method provides.
- `Clock.systemUTC()`: factory logic defined by the developer.
- Returned object: the instance that Spring places under management.

If no name is specified, Spring normally uses the **method name** as the bean name. You can specify a name and aliases:

```java
@Bean(name = {"appClock", "systemClock"})
public Clock clock() {
    return Clock.systemUTC();
}
```

In this example, `appClock` is the bean name and `systemClock` is an alias. Both names point to the same bean definition; they do not create two separate instances.

You can also use the shorthand form:

```java
@Bean("appClock")
public Clock clock() {
    return Clock.systemUTC();
}
```

Bean names should be consistent because lookups by name or `@Qualifier` depend on them.

## 4. `@Bean` Method Parameters Are Dependency Injection

A major advantage of Java configuration is that **Spring can inject dependencies into factory method parameters**.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService(Clock appClock) {
        return new ReportService(appClock);
    }
}
```

When creating `ReportService`, Spring resolves the `Clock` parameter from the container and passes it into the method. You do not need to call `appClock()` directly to obtain the bean.

This is a clear way to express dependency relationships:

```text
Clock bean definition
        │
        ▼
Clock instance
        │
        │ injected as parameter
        ▼
reportService(Clock appClock)
        │
        ▼
ReportService bean definition / instance
```

Benefits:

- Dependencies are visible right on the method signature.
- No manual access to `ApplicationContext` is needed.
- `final` fields can be used in the created object.
- Works well with `proxyBeanMethods = false`.
- Easier to read and refactor than nested factory method calls.

If multiple beans of the same type exist, the parameter can use `@Qualifier` or other bean selection metadata:

```java
@Bean
public PaymentService paymentService(
        @Qualifier("stripeGateway") PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Spring still applies standard dependency resolution rules to `@Bean` method parameters.

## 5. Full `@Configuration`: Spring Intercepts Calls Between Bean Methods

By default, `@Configuration` has `proxyBeanMethods = true`. Spring creates an enhanced class, typically via CGLIB, to intercept calls to `@Bean` methods when invoked on the container-managed configuration instance.

Consider this example:

```java
@Configuration
public class FullConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(appClock());
    }
}
```

In full configuration mode, the `appClock()` call inside `reportService()` is intercepted. Spring returns the `appClock` bean managed by the container according to its scope, rather than executing the factory method as a regular new Java call.

With the default singleton scope, this means `ReportService` receives the same `Clock` bean that the container provides to other dependents.

### Why Is Interception Needed?

If it were plain Java, the call:

```java
return new ReportService(appClock());
```

would invoke the `appClock()` method and create a new `Clock` every time `reportService()` runs. Full configuration mode ensures that calls between bean methods in the configuration are handled according to container semantics.

An easier example to observe:

```java
@Configuration
public class CounterConfiguration {

    @Bean
    public Counter counter() {
        return new Counter();
    }

    @Bean
    public CounterConsumer counterConsumer() {
        return new CounterConsumer(counter());
    }
}
```

In full mode, `counter()` is intercepted when called from `counterConsumer()`, so `CounterConsumer` receives the container-managed `Counter` bean. If the bean is a singleton, it is the registered singleton instance.

### Limitations of Full Mode

Because Spring needs to create a subclass and intercept methods, full mode configuration has certain constraints:

- The `@Configuration` class should not be `final`.
- Intercepted `@Bean` methods must not be `private` or `final`.
- Do not invoke configuration methods on an object manually instantiated with `new FullConfiguration()`, because that object is not the Spring-managed enhanced configuration instance.
- Proxy constraints also need attention with JVM languages where classes/methods are final by default, such as Kotlin if the appropriate compiler plugin is not enabled.

In most applications, you do not need to create subclasses manually or deal with CGLIB directly. You just need to understand that full mode allows calls between bean methods to be coordinated by the container.

## 6. Lite Configuration: `@Configuration(proxyBeanMethods = false)` and `@Component`

Lite mode does not enhance the configuration class to intercept calls between `@Bean` methods. Method calls are **regular Java method calls**.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(appClock());
    }
}
```

Here, `appClock()` inside `reportService()` is a normal Java call. It runs the factory method and creates a new object according to the method's code. It does not automatically go back to the container to retrieve the existing `appClock` bean.

As a result, `ReportService` may receive a different `Clock` from the singleton `appClock` bean registered by the container.

This is the core difference between full and lite configuration:

| Behavior | Full mode | Lite mode |
|---|---|---|
| Default `@Configuration` | Yes | No |
| `@Configuration(proxyBeanMethods = false)` | No | Yes |
| `@Component` containing `@Bean` | No | Yes |
| Calling `appClock()` from another `@Bean` method | Intercepted and resolved via container | Direct Java call |
| Requires CGLIB enhancement for inter-bean method calls | Yes | No |
| Using method parameters to inject dependencies | Supported | Supported and generally recommended |

### How to Write Properly in Lite Mode

Instead of calling `appClock()` directly, declare the dependency as a parameter:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService(Clock appClock) {
        return new ReportService(appClock);
    }
}
```

Spring resolves `Clock` before calling the factory method. This approach is explicit and works correctly in both full mode and lite mode.

**Rule of thumb:** if you do not need to call one `@Bean` method directly from another, prefer `@Configuration(proxyBeanMethods = false)` and inject dependencies via parameters. If you need inter-bean call interception semantics, keep the default full mode.

## 7. Can `@Bean` Be Placed Inside a `@Component`?

Yes. Spring allows declaring `@Bean` methods inside a component class, not only in `@Configuration`.

Example:

```java
@Component
public class ClientFactory {

    @Bean
    public Clock clientClock() {
        return Clock.systemUTC();
    }
}
```

If `ClientFactory` is component-scanned or otherwise registered, Spring processes the `@Bean` method inside it. However, this class falls under **lite configuration**: calling `clientClock()` from another method is a regular Java call, not intercepted with full configuration semantics.

That does not mean `@Bean` in `@Component` is wrong. It is a valid approach when a component also provides a factory method. However, if a class's primary responsibility is declaring bean definitions, using `@Configuration` communicates intent more clearly.

### Do Not Confuse `@Component` with `@Bean`

```java
@Component
public class EmailSender {
    public void send(String message) {
        // ...
    }
}
```

In this example, component scanning discovers the `EmailSender` class and registers the bean.

Whereas:

```java
@Configuration(proxyBeanMethods = false)
public class EmailConfiguration {

    @Bean
    public EmailSender emailSender() {
        return new EmailSender();
    }
}
```

Here, Spring discovers the configuration class, then calls the factory method to create `EmailSender`. Both approaches can produce a bean, but **the registration source and how instantiation is controlled differ**. There is no need to apply both `@Component` and `@Bean` to the same instance just to "make sure Spring recognizes it."

## 8. Creating Beans from Third-Party Library Classes

This is a use case that fits `@Bean` very well.

Suppose the application needs a `Clock` or a client from an external library, and that class does not have any Spring stereotypes. You can declare:

```java
@Configuration(proxyBeanMethods = false)
public class InfrastructureConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Or configure a client with dependencies:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    public PaymentClient paymentClient(
            PaymentClientProperties properties) {
        return new PaymentClient(
                properties.endpoint(),
                properties.apiKey()
        );
    }
}
```

The second example assumes `PaymentClientProperties` is already registered and `PaymentClient` has the corresponding constructor. Production code must manage secrets from a secure source; do not hardcode real API keys in source code.

The advantage is that there is no need to modify library classes, and the initialization configuration resides in the application module responsible for integrating that library.

## 9. Bean Names and Aliases in `@Bean`

The default bean name is the factory method name:

```java
@Bean
public Clock systemClock() {
    return Clock.systemUTC();
}
```

The bean name is `systemClock`.

Multiple names can be specified:

```java
@Bean(name = {"systemClock", "utcClock"})
public Clock clock() {
    return Clock.systemUTC();
}
```

The first name is the bean name; the remaining ones are aliases. An alias is not a new bean instance.

Bean names matter when:

- Using `@Qualifier`.
- Looking up via `ApplicationContext.getBean("...")`.
- Multiple implementations of the same type exist.
- Integrating with configuration or libraries that rely on a conventional bean name.

If the name is not a required contract, type-based dependency injection is generally less coupled to method names.

## 10. Return Type of a `@Bean` Method

You should declare a return type specific enough so that Spring and tooling can identify the bean appropriately.

Example:

```java
@Bean
public PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Here the return type is the `PaymentGateway` interface. Consumers can inject by the interface, and the configuration does not force callers to depend on the `StripePaymentGateway` class.

If you declare an overly broad type like `Object`, Spring has less information to predict the bean type before the factory method is invoked. This can affect type-based autowiring, auto-configuration conditions, and early dependency checks.

**Recommendation:** return the interface or abstraction that consumers need, but do not declare a type broader than necessary. If some consumers require the concrete type, consider whether depending on the implementation is truly warranted.

## 11. Scope of Beans Declared with `@Bean`

Beans created by `@Bean` methods still follow Spring scopes. You can place `@Scope` on the method:

```java
@Configuration(proxyBeanMethods = false)
public class DraftConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public ReportDraft reportDraft() {
        return new ReportDraft();
    }
}
```

In this example, each time the container is asked for the `reportDraft` bean, the prototype scope creates a new instance.

Web scopes can be used if the application has an appropriate web context:

```java
@Bean
@RequestScope
public RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

Or declare `@SessionScope`/`@ApplicationScope` for the corresponding bean factory method.

Remember that scope governs instance-level behavior, while `@Bean` is simply a way to declare a factory method. These two concepts address two different concerns.

## 12. Lifecycle Callbacks for Beans Created with `@Bean`

Beans created via `@Bean` still participate in the Spring lifecycle. You can use standard callbacks like `@PostConstruct`, `@PreDestroy`, or specify init/destroy method names.

Example:

```java
public class ManagedClient {

    public void connect() {
        System.out.println("Client initialized");
    }

    public void close() {
        System.out.println("Client closed");
    }
}
```

Declaration:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "connect", destroyMethod = "close")
    public ManagedClient managedClient() {
        return new ManagedClient();
    }
}
```

Spring calls `connect()` during bean initialization and calls `close()` when the container destroys the bean during normal lifecycle shutdown.

Spring also supports `@PostConstruct`, `@PreDestroy`, `InitializingBean`, and `DisposableBean`. There is no need to mix every mechanism into a single class; choose one clear approach.

Some beans with a `close()` or `shutdown()` method may have it inferred by Spring as a default destroy method. If you do not want Spring to invoke an inferred destroy method, `@Bean(destroyMethod = "")` can disable that inference behavior.

Notes:

- Destruction callbacks depend on the container having the opportunity to shut down cleanly.
- If the process is forcefully killed or the machine stops abruptly, destruction callbacks are not guaranteed to run.
- Prototype beans are created and initialized by the container, but the container does not fully manage destruction callbacks for each prototype after handing the instance to the caller.
- Do not use lifecycle callbacks as a substitute for business transaction handling or persisting critical data.

## 13. Combining `@Bean` with `@Primary`, `@Qualifier`, and `@Profile`

Bean selection metadata can be placed on `@Bean` methods.

### `@Primary`

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Primary
    public PaymentGateway defaultGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

If an injection point simply requests `PaymentGateway` without a qualifier, the primary bean can be selected as the preferred candidate.

### `@Qualifier`

```java
@Bean
@Qualifier("external")
public PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}
```

Injection points can use the corresponding qualifier to select the bean by role.

### `@Profile`

```java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean
    @Profile("local")
    public StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("prod")
    public StorageClient productionStorageClient() {
        return new RemoteStorageClient();
    }
}
```

The corresponding bean is registered only when the matching profile is active. If neither profile is enabled and a consumer requires `StorageClient`, the application may lack a bean. If both profiles are enabled, there may be multiple candidates requiring explicit selection.

Additionally, `@Bean` methods can be combined with conditional annotations in the Spring Boot ecosystem such as `@ConditionalOnProperty` or `@ConditionalOnMissingBean` when used in the appropriate type of configuration context.

## 14. `@Bean` Methods and Initialization Order

You should not rely on the declaration order of methods within the same class to control bean creation order. Spring resolves dependencies based on bean definitions and dependency relationships.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationConfiguration {

    @Bean
    public ReportService reportService(Clock clock) {
        return new ReportService(clock);
    }

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Even though `reportService()` is written before `appClock()`, Spring still knows `ReportService` needs `Clock` and resolves the dependency accordingly.

If there is an initialization order requirement beyond constructor/method dependencies, consider an appropriate lifecycle mechanism such as `@DependsOn`, `SmartLifecycle`, or application events. Do not reorder methods in a file hoping the container will follow textual order.

### A Bean Depending on Another Bean Should Use Method Parameters

This is the clearest way to express dependencies:

```java
@Bean
public ReportService reportService(Clock clock) {
    return new ReportService(clock);
}
```

The alternative call style:

```java
@Bean
public ReportService reportService() {
    return new ReportService(appClock());
}
```

has different semantics between full and lite mode. Therefore, method parameters are the less surprising choice and do not depend on `proxyBeanMethods`.

## 15. When Is a `static @Bean` Method Needed?

Most `@Bean` methods can be regular instance methods. Some infrastructure beans such as `BeanFactoryPostProcessor` or `BeanDefinitionRegistryPostProcessor` are created very early while the container is preparing bean definitions.

In that case, declaring the factory method as `static` avoids premature instantiation of its enclosing configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class PlaceholderConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer
            propertySourcesPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

This example illustrates an infrastructure bean that processes placeholders. In a typical Spring Boot application, auto-configuration already provides common components, so do not re-add them without a clear need.

A `static @Bean` method cannot access instance fields of the configuration class. It also does not receive the inter-bean call interception semantics that instance `@Bean` methods get in full configuration.

Only use static factory methods when the bean type and its lifecycle truly require early creation or framework documentation recommends it.

## 16. Organizing Multiple Configuration Classes

As an application grows, you should not cram all beans into a single configuration class. You can split them by responsibility:

```text
config/
├── WebConfiguration.java
├── PersistenceConfiguration.java
├── SecurityConfiguration.java
├── ClientConfiguration.java
└── TimeConfiguration.java
```

Each class can hold related beans. If they reside under the root package, component scanning can find them; if they are in an external package, they can be imported explicitly:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    ClientConfiguration.class,
    TimeConfiguration.class
})
public class InfrastructureConfiguration {
}
```

Organizing by module helps to:

- Know which beans belong to which integration.
- Easily disable or replace part of the configuration.
- Avoid giant configuration classes.
- Keep dependencies between modules clear.
- Test a configuration within an appropriate scope.

Do not split classes purely by method count; group by responsibility and boundaries of change.

## 17. Common Pitfalls with `@Configuration` and `@Bean`

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Cannot inject a bean declared with `@Bean` | Configuration class was not scanned/imported; condition/profile does not match. | Check package scanning, `@Import`, active profiles, and conditions. |
| Two instances of the same dependency exist | Lite mode directly calls one `@Bean` method from another. | Use method parameters to inject dependencies or enable full configuration if interception is needed. |
| Bean name is not as expected | Default name is the method name or a different alias is declared. | Explicitly set `@Bean(name = "...")` and check aliases. |
| `NoUniqueBeanDefinitionException` | Multiple `@Bean` methods provide the same type. | Use `@Qualifier`, `@Primary`, or redesign the types. |
| Configuration class cannot be proxied | Final/private class or method in full mode, or proxy restrictions. | Allow the class/method to be subclassed/intercepted, or use lite mode and method parameter injection. |
| `@Bean` can be called, but the object is not the intended bean | Method was called on a manually `new`-ed configuration object, or direct call in lite mode. | Let the container invoke the factory method and inject dependencies via parameters. |
| Bean initializes unexpectedly early | Dependency chain or infrastructure bean requires early initialization. | Check lazy mode, factory methods, and infrastructure bean types. |
| Destroy callback does not run | Context did not shut down cleanly, or bean scope does not manage destruction as expected. | Check lifecycle, scope, and application shutdown mechanism. |

### Common Mistake: Calling a `@Bean` Method from Business Code

Do not write:

```java
@Service
public class ReportService {

    public void generate() {
        Clock clock = new TimeConfiguration().appClock();
        // ...
    }
}
```

This code instantiates the configuration object manually and calls the method as plain Java. It does not ask Spring to provide the managed `Clock` bean.

Inject the dependency instead:

```java
@Service
public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public void generate() {
        // Use the container-injected clock.
    }
}
```

Business code should not depend on configuration classes to re-create dependencies.

## 18. Inspecting Beans Provided by `@Bean` Methods

You can inspect bean names and types in tests:

```java
@SpringBootTest
class TimeConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void applicationClockIsRegistered() {
        Clock clock =
                context.getBean("applicationClock", Clock.class);

        assertNotNull(clock);
    }
}
```

This example assumes `TimeConfiguration` is loaded and has a bean named `applicationClock`.

You can query all beans by type:

```java
Map<String, Clock> clocks = context.getBeansOfType(Clock.class);

clocks.forEach((name, clock) ->
        System.out.println(name + " -> " + clock.getClass().getName()));
```

If there are multiple `Clock` beans, the map shows the candidate names. If an object is proxied, `getClass()` may reflect the proxy rather than the concrete target; combine this with bean definitions and configuration to understand the creation source.

For applications with Actuator appropriately configured, the `/actuator/beans` endpoint can also provide bean information. Only expose management endpoints within a protected scope; do not make them public just for debugging.

## 19. Practice Exercises

### Exercise A — Creating a Bean from a JDK Class

1. Create `TimeConfiguration` with `@Bean Clock applicationClock()`.
2. Inject `Clock` into `TimeService` via constructor.
3. Write a unit test using `Clock.fixed(...)`.
4. Explain why `Clock` does not need `@Component`.

### Exercise B — Comparing Full and Lite Configuration

Create two configurations with `counter()` and `counterConsumer()`; the consumer method calls `counter()` directly.

- Try default `@Configuration`.
- Try `@Configuration(proxyBeanMethods = false)`.
- Compare the identity of the object passed into the consumer with the bean returned by the context.
- Then replace the direct call with a method parameter and observe both modes behaving consistently.

### Exercise C — Bean Names and Qualifiers

Declare two `PaymentGateway` beans using two `@Bean` methods. Inject by type without a qualifier to observe ambiguity. Add `@Primary`, then add `@Qualifier` to select a specific implementation.

### Exercise D — Scope and Lifecycle

Declare a prototype bean using `@Scope` and add init/destroy callbacks. Request multiple instances from the container and observe which callbacks are invoked. Explain why prototype destruction is not managed by the container in the same way as singleton destruction.

### Exercise E — Profile-Based Configuration

Declare two `StorageClient` factory methods with `@Profile("local")` and `@Profile("prod")`. Run with each profile and verify which bean appears. Try running without any profile enabled and note the consumer's behavior.

### Exercise F — Registering Configuration Outside the Main Package

Place a configuration class in a package not under the main package. Try default component scanning, then add `@Import`. Compare how the bean definition is brought into the context.

## 20. Principles to Remember

1. **`@Configuration`** marks a class containing bean configuration; it is typically loaded via component scanning or import.
2. **`@Bean`** marks a factory method; the return value is a Spring-managed object.
3. **`@Bean` method parameters** are container-resolved dependency injection, usually the clearest way to wire beans together.
4. **Full configuration** intercepts calls between bean methods by default; **lite configuration** uses regular Java method calls.
5. **`@Configuration(proxyBeanMethods = false)`** and `@Component` containing `@Bean` are lite mode; do not call methods directly to obtain another singleton bean.
6. **The default bean name** comes from the factory method name; explicit names and aliases can be specified.
7. Beans created with `@Bean` still have scopes, lifecycles, qualifiers, primary markers, and registration conditions like any other bean.
8. Using `@Bean` is especially suited for JDK/third-party library objects or when custom factory logic is needed.

When designing Java configuration, treat each `@Bean` method as **a typed declaration of how the container creates a dependency**. Let Spring resolve dependencies through method parameters, name beans intentionally when needed, and choose full or lite mode based on whether you genuinely need to intercept calls between factory methods.
