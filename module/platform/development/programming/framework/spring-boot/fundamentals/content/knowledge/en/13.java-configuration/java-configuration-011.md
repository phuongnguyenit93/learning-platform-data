# EnvironmentAware, ApplicationContextAware, and Limiting Container Coupling

Spring provides the **Aware** family of interfaces so a bean can receive infrastructure objects from the container during initialization. Two key interfaces are `EnvironmentAware` and `ApplicationContextAware`:

- `EnvironmentAware` provides `Environment` for reading property sources and profiles.
- `ApplicationContextAware` provides the `ApplicationContext` managing the bean, granting access to broader container capabilities such as bean lookup, resource loading, event publishing, and message resolution.

These interfaces are useful for certain framework integration or infrastructure components. However, they couple a class directly to the Spring container. For ordinary business services, constructor injection, `@Value`, or `@ConfigurationProperties` usually express dependencies more clearly and are easier to test.

This lesson explains when Aware callbacks are invoked, how to use both interfaces, appropriate use cases, lifecycle and testing limitations, and narrower abstractions to avoid turning `ApplicationContext` into a global service locator.

## 1. What Is an Aware Callback?

A bean can implement an interface ending with the `Aware` suffix to receive an object supplied by the container. When Spring instantiates a bean, it detects supported Aware interfaces and invokes the corresponding callbacks during bean preparation.

Example:

~~~java
public class ExampleBean implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

Spring calls `setEnvironment` and passes the `Environment` of the context managing the bean. Developers do not invoke this callback manually in normal usage.

An Aware callback is part of the **lifecycle contract**. It is not a component scanning mechanism, does not register beans on its own, and does not replace dependency injection. The class must be created and managed by Spring for the callback to execute.

### 1.1. Common Aware Interfaces

| Interface | Object received by the bean | Purpose |
| --- | --- | --- |
| `BeanNameAware` | Bean name in the container | Knows the registered bean name |
| `BeanClassLoaderAware` | ClassLoader | Loads classes/resources using the class loader |
| `BeanFactoryAware` | BeanFactory | Accesses the factory managing the bean |
| `EnvironmentAware` | Environment | Reads properties and profiles |
| `EmbeddedValueResolverAware` | StringValueResolver | Resolves placeholders/expressions with the configured resolver |
| `ResourceLoaderAware` | ResourceLoader | Loads resources via Spring's abstraction |
| `ApplicationEventPublisherAware` | ApplicationEventPublisher | Publishes application events |
| `MessageSourceAware` | MessageSource | Looks up configured messages |
| `ApplicationContextAware` | ApplicationContext | Accesses the current application context |

No bean should implement all of these interfaces needlessly. Receive the narrowest abstraction the component actually requires.

### 1.2. Aware Callbacks vs. Constructor Injection

Constructor injection passes dependencies as part of the instantiation contract:

~~~java
@Service
public class GreetingService {
    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }
}
~~~

An Aware callback passes the dependency after the object has already been constructed:

~~~java
@Component
public class GreetingEnvironment implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

Constructor injection makes required dependencies visible right in the constructor and allows `final` fields. An Aware callback is a lifecycle hook invoked by the container; the field usually cannot be `final` because it is assigned after construction. If a class needs `Environment` to perform business work, passing it via constructor is usually clearer.

## 2. What Is Environment?

`Environment` is Spring's abstraction for accessing environment characteristics of the application, primarily comprising:

- `PropertySources`: property sources such as system properties, environment variables, configuration files, and application-added sources.
- `Profiles`: active or default profile sets used to select matching configurations/beans.
- APIs for reading properties by name, data type, and default value.

In Spring Boot, `Environment` is configured from sources such as `application.properties`, `application.yml`, profile-specific configuration, environment variables, JVM system properties, and other sources in precedence order.

~~~mermaid
flowchart TD
    A["Environment"] --> B["PropertySources"]
    B --> C["application.yml / properties"]
    B --> D["Profile-specific config"]
    B --> E["Environment variables"]
    B --> F["JVM system properties"]
    B --> G["Additional property sources"]
    A --> H["Active profiles"]
    A --> I["Default profiles"]
~~~

Precedence among property sources determines the final value when multiple sources define the same key. Do not assume configuration files always override environment variables or system properties; check Spring Boot's property precedence rules and how sources are added to the application.

## 3. EnvironmentAware and How to Implement It

`EnvironmentAware` belongs to package `org.springframework.context` and defines the callback:

~~~java
public interface EnvironmentAware extends Aware {
    void setEnvironment(Environment environment);
}
~~~

A bean implementing this interface receives `Environment` from Spring during initialization.

### 3.1. Reading Properties

~~~java
package com.example.infrastructure;

import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeEnvironmentInfo implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String applicationRegion() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

Configuration:

~~~yaml
app:
  region: apac
~~~

When invoked, `applicationRegion()` returns the `app.region` property if present; otherwise it returns `local`.

In this example, the field cannot be `final` because the callback assigns it after construction. This is a practical difference compared to constructor injection.

### 3.2. Reading Typed Properties

`Environment` supports type conversion through `getProperty` overloads:

~~~java
String region = environment.getProperty("app.region");

Integer maxAttempts = environment.getProperty(
        "app.retry.max-attempts",
        Integer.class,
        3
);

Boolean enabled = environment.getProperty(
        "feature.audit.enabled",
        Boolean.class,
        false
);
~~~

You can use `getRequiredProperty` when a property is mandatory:

~~~java
String apiEndpoint =
        environment.getRequiredProperty("partner.api.endpoint");
~~~

If the property does not exist, `getRequiredProperty` throws an error instead of returning null. This enables failing fast when required configuration is missing.

Do not log secrets or credentials when reading properties. Being able to access a value does not mean that value should be written to the console or responses.

### 3.3. Checking Profiles

`Environment` allows inspecting active profiles:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

public boolean isProduction(Environment environment) {
    return environment.acceptsProfiles(Profiles.of("prod"));
}
~~~

Or reading the list of profiles:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
~~~

Important points to keep in mind:

- Profiles are a mechanism for selecting configurations or beans, not an authorization system.
- Do not use the `prod` profile as a substitute for authorization or security checks.
- If no profile is active, Spring may fall back to configured default profiles.
- A bean can be registered conditionally using `@Profile` instead of querying `Environment` manually inside every method.

Example:

~~~java
@Configuration
@Profile("prod")
public class ProductionIntegrationConfiguration {
    // Beans are registered only when the prod profile matches.
}
~~~

When the goal is selecting an implementation per environment, `@Profile` usually communicates intent better than a service asking `Environment` on every call.

## 4. What Is ApplicationContextAware?

`ApplicationContextAware` belongs to package `org.springframework.context`. It lets a bean receive the context managing it:

~~~java
public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException;
}
~~~

Example:

~~~java
package com.example.infrastructure;

import org.springframework.beans.BeansException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Component;

@Component
public class ContextInformation implements ApplicationContextAware {
    private ApplicationContext applicationContext;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException {
        this.applicationContext = applicationContext;
    }

    public String contextDisplayName() {
        return applicationContext.getDisplayName();
    }
}
~~~

`ApplicationContext` is a broader abstraction than `Environment`. Beyond properties and profiles, the context provides access to beans, resources, event publishing, message sources, and bean lifecycle management.

### 4.1. Capabilities of ApplicationContext

| API | Purpose |
| --- | --- |
| `getBean(...)` | Look up beans by name or type |
| `getEnvironment()` | Access `Environment` |
| `getResource(...)` | Load a `Resource` by location |
| `publishEvent(...)` | Publish an application event |
| `getMessage(...)` | Look up messages via `MessageSource` |
| `ConfigurableApplicationContext.getBeanFactory()` | Access the bean factory when working with a configurable context |
| `getDisplayName()` | Retrieve the context display name |

Not all of these capabilities are needed by a business bean. Receiving the entire context creates broader coupling than injecting a specific dependency.

### 4.2. Looking Up Beans via ApplicationContext

Example of a simple plugin registry:

~~~java
@Component
public class ExporterRegistry implements ApplicationContextAware {
    private ApplicationContext applicationContext;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public Exporter exporter(String beanName) {
        return applicationContext.getBean(beanName, Exporter.class);
    }
}
~~~

This snippet demonstrates dynamic bean lookup. However, it also couples `ExporterRegistry` directly to the container and runtime bean names. Consumers cannot tell from the constructor which exporters the registry can return, and invalid bean name errors only surface when the method is called.

If the set of exporters is known upfront, collection injection is much more transparent:

~~~java
@Component
public class ExporterRegistry {
    private final Map<String, Exporter> exporters;

    public ExporterRegistry(Map<String, Exporter> exporters) {
        this.exporters = Map.copyOf(exporters);
    }

    public Exporter exporter(String name) {
        Exporter exporter = exporters.get(name);
        if (exporter == null) {
            throw new IllegalArgumentException("Unknown exporter: " + name);
        }
        return exporter;
    }
}
~~~

Spring can inject a map of bean name → bean instance when the constructor requests `Map<String, Exporter>`. This makes the dependency explicit at initialization time without holding `ApplicationContext`.

### 4.3. Do Not Store ApplicationContext in a Static Field

A common anti-pattern:

~~~java
@Component
public class SpringContextHolder implements ApplicationContextAware {
    private static ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        SpringContextHolder.context = applicationContext;
    }

    public static <T> T getBean(Class<T> type) {
        return context.getBean(type);
    }
}
~~~

This creates a global service locator. It carries significant risks:

- Any class can silently fetch beans without declaring dependencies.
- Unit tests become hard to isolate because static state leaks across tests.
- Multiple contexts or closed/restarted contexts can leave stale references behind.
- Bean lifecycles are hidden behind a static API.
- Business code becomes tightly coupled to Spring and difficult to reuse outside Spring.

Only build a context holder if there is a very specific framework/integration requirement with an explicit lifecycle policy. Never use it as a default injection strategy.

## 5. When Are Aware Callbacks Invoked?

Aware callbacks occur during bean creation, after the instance has been instantiated and dependencies/properties have been populated, but before initialization callbacks such as `@PostConstruct`.

For an ordinary bean, the general sequence is:

~~~mermaid
flowchart TD
    A["Instantiate bean"] --> B["Populate properties / inject dependencies"]
    B --> C["BeanNameAware / BeanClassLoaderAware / BeanFactoryAware if present"]
    C --> D["ApplicationContextAwareProcessor invokes ApplicationContext Aware callbacks"]
    D --> E["BeanPostProcessor before initialization"]
    E --> F["@PostConstruct"]
    F --> G["InitializingBean.afterPropertiesSet()"]
    G --> H["Custom init method"]
    H --> I["BeanPostProcessor after initialization"]
    I --> J["Bean ready for use"]
~~~

`ApplicationContextAwareProcessor` is a `BeanPostProcessor` registered by Spring to handle interfaces such as `EnvironmentAware`, `ResourceLoaderAware`, `ApplicationEventPublisherAware`, `MessageSourceAware`, and `ApplicationContextAware`.

You do not need to create this processor manually in ordinary applications. This detail simply explains why the callbacks execute at that point in the lifecycle.

### 5.1. Aware Callbacks Are Not Constructors

Do not read fields assigned inside `setEnvironment` or `setApplicationContext` from the constructor of the same bean. At the time the constructor runs, the callback has not executed yet.

If a property is needed to establish an object's initial state, constructor injection or configuration properties are better suited.

### 5.2. Callbacks Run Only for Spring-Managed Beans

Instantiating a Java object with `new` does not trigger Spring's lifecycle:

~~~java
RuntimeEnvironmentInfo info = new RuntimeEnvironmentInfo();
// Spring does not call setEnvironment(...) on this instance.
~~~

If a method relying on the `environment` field is called, that instance will not have the injected value. This is why classes using Aware callbacks must be instantiated and managed by the container as expected.

## 6. EnvironmentAware vs. Constructor-Injecting Environment

Both approaches can provide `Environment`. The choice depends on the class's role.

### 6.1. Constructor Injection

~~~java
@Service
public class FeaturePolicy {
    private final Environment environment;

    public FeaturePolicy(Environment environment) {
        this.environment = environment;
    }

    public boolean auditEnabled() {
        return environment.getProperty(
                "feature.audit.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Benefits:

- Dependency is explicitly declared.
- Field can be `final`.
- Unit tests can pass a `StandardEnvironment` or a suitable mock/fake.
- Does not rely on lifecycle callbacks for the object to be complete.

If a service only needs a few properties, `@ConfigurationProperties` or `@Value` is even narrower and clearer.

### 6.2. EnvironmentAware

~~~java
@Component
public class EnvironmentDiagnostics implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String activeProfileSummary() {
        return String.join(",", environment.getActiveProfiles());
    }
}
~~~

This can fit an infrastructure component designed to receive standard Spring callbacks, or an integration component that must implement several Aware interfaces per framework contracts.

Yet if it is simply a business service needing to read configuration, constructor injection is usually simpler.

### 6.3. Using @Value for a Single Value

If a class only needs one property, there is no need to inject the entire `Environment`:

~~~java
@Component
public class EmailPolicy {
    private final String senderAddress;

    public EmailPolicy(
            @Value("${mail.sender-address}") String senderAddress) {
        this.senderAddress = senderAddress;
    }
}
~~~

`@Value` can resolve property placeholders and convert types using the conversion service. For required properties, a placeholder without a default can cause context startup to fail if the value is missing.

Use `@Value` for a few simple values; avoid scattering too many isolated properties in the constructor of a large class.

### 6.4. Using @ConfigurationProperties for Configuration Groups

When multiple related properties exist, group them into a typed configuration object:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.client")
public record PartnerClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
    public PartnerClientProperties {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("baseUrl is required");
        }
        if (connectTimeout == null || connectTimeout.isNegative()) {
            throw new IllegalArgumentException("connectTimeout must be non-negative");
        }
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
    }
}
~~~

YAML:

~~~yaml
partner:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    max-attempts: 3
~~~

Register the properties using an appropriate method, such as:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

Or `@EnableConfigurationProperties(PartnerClientProperties.class)` on a configuration class.

Consumers simply accept the configuration object:

~~~java
@Service
public class PartnerClient {
    private final PartnerClientProperties properties;

    public PartnerClient(PartnerClientProperties properties) {
        this.properties = properties;
    }
}
~~~

This is usually the best choice for structured configuration because data types, validation, and relationships between attributes are made explicit. `EnvironmentAware` still has a place when a component genuinely needs to interact with the general `Environment` abstraction rather than a fixed configuration group.

## 7. ApplicationContextAware vs. Injecting Narrower Abstractions

`ApplicationContext` provides many capabilities, yet most classes only need a small slice. Spring lets you inject the corresponding narrower abstractions directly.

| Need | Narrower dependency to consider |
| --- | --- |
| Reading properties and profiles | `Environment` or configuration properties |
| Publishing application events | `ApplicationEventPublisher` |
| Loading resources | `ResourceLoader` or injected `Resource` |
| Optional/lazy bean lookup | `ObjectProvider<T>` |
| Using multiple implementations of an interface | `List<T>`, `Set<T>`, or `Map<String, T>` |
| Looking up messages | `MessageSource` |
| Bean-factory-level operations | `BeanFactory` only if factory APIs are truly required |
| Full container access | `ApplicationContext` only when the responsibility needs the full context |

### 7.1. Replacing ApplicationContextAware with ApplicationEventPublisher

If a class only needs to publish events:

~~~java
@Component
public class OrderEventPublisher {
    private final ApplicationEventPublisher publisher;

    public OrderEventPublisher(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publishOrderCreated(String orderId) {
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Event type:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

Consumer:

~~~java
@Component
public class OrderAuditListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Record audit based on event.
    }
}
~~~

The publisher class does not need to know about the entire `ApplicationContext`. It only needs the event-publishing abstraction.

Note: synchronous event publishing by default means listeners run within the same call flow. If async listeners, transaction-bound events, or durable delivery guarantees are needed, design the appropriate mechanism; in-memory application events do not replace a message broker.

### 7.2. Replacing ApplicationContextAware with ObjectProvider

If a class needs a bean that might be absent or wants deferred resolution:

~~~java
@Service
public class OptionalSearchService {
    private final ObjectProvider<SearchExtension> extensionProvider;

    public OptionalSearchService(
            ObjectProvider<SearchExtension> extensionProvider) {
        this.extensionProvider = extensionProvider;
    }

    public void search(String query) {
        SearchExtension extension = extensionProvider.getIfAvailable();
        if (extension != null) {
            extension.enrich(query);
        }
    }
}
~~~

`ObjectProvider` makes it clear that only one specific dependency is looked up dynamically. It avoids forcing the service to accept the entire context.

If all extensions are needed, inject a collection upfront. If selection by a runtime criterion is needed, build a registry/factory with an explicit API rather than letting business services call `getBean` freely.

### 7.3. Replacing ApplicationContextAware with ResourceLoader

If the goal is reading resources:

~~~java
@Component
public class TemplateCatalog {
    private final ResourceLoader resourceLoader;

    public TemplateCatalog(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource template(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

The consumer depends only on resource-loading functionality. Classpath or URL locations can be used according to `ResourceLoader` and the application environment. Handle missing resources or read errors explicitly.

## 8. Limitations and Risks of Depending on ApplicationContext

`ApplicationContextAware` can be useful, yet it couples a class directly to the container.

### 8.1. Hiding Dependencies

~~~java
@Service
public class CheckoutService implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void checkout(String orderId) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge(orderId);
    }
}
~~~

Looking at the constructor, a reader cannot tell `CheckoutService` needs `PaymentGateway`. The dependency only reveals itself when the method runs. This makes understanding the bean graph, writing tests, and refactoring harder.

Clearer approach:

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

### 8.2. Increasing Coupling to Spring

A class implementing `ApplicationContextAware` is no longer a standalone Java service. It depends directly on Spring APIs and lifecycles. If you want to reuse that logic in another application, plain unit tests, or a Spring-free domain module, you must carry along the container abstraction or build an adapter.

A helpful rule is keeping domain/application logic dependent on plain Java interfaces and types; let adapters/configurations at the Spring boundary handle wiring into the container.

### 8.3. Can Create Hidden Circular Dependencies

If bean A fetches B via `getBean` in a callback or `@PostConstruct`, while B depends on A, a circular dependency can be masked behind dynamic lookups. Errors then surface at runtime and are harder to diagnose than constructor cycles.

Constructor injection makes the dependency graph explicit at startup. If a cycle exists, re-examine responsibilities, extract a collaborator, or use appropriate events/ports rather than calling `getBean` to bypass cycle detection.

### 8.4. Do Not Use ApplicationContext for Manual Scope Management

Calling `getBean` repeatedly in an attempt to manage request/session lifecycles or create fresh instances can bypass scope contracts. For prototypes, scoped beans, or lazy dependencies, use the proper mechanisms such as `ObjectProvider`, scoped proxies, or factory abstractions.

### 8.5. Multiple ApplicationContexts

An application may have parent and child contexts, or multiple contexts created in tests/embedded setups. `ApplicationContextAware` receives the context managing that specific bean, not a single global context.

If code stores a context in a static field, a new context can overwrite an older one or a closed reference may linger. Never assume `getBean` always accesses the exact same set of beans across every context.

## 9. Aware Callbacks and Lifecycle Order

Aware callbacks execute before initialization callbacks. By the time `@PostConstruct` runs, the bean has already received the Spring-supported Aware dependencies.

~~~java
@Component
public class EnvironmentStartupReporter implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @PostConstruct
    public void report() {
        String[] profiles = environment.getActiveProfiles();
        // Environment can be read here.
    }
}
~~~

`@PostConstruct` occurs after the `setEnvironment` callback in the normal lifecycle. The constructor runs before that, so do not access this field inside the constructor.

### 9.1. Do Not Use Callbacks to Run Long Startup Tasks

Do not turn `setApplicationContext` or `setEnvironment` into a place to run database queries, call external APIs, or spawn background threads. Aware callbacks should simply accept and store the abstraction the bean needs, while startup work should use an appropriate lifecycle mechanism with error/timeout handling.

Options include `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent`, or `SmartLifecycle` depending on requirements. Do not use an Aware callback merely because it runs early.

### 9.2. Aware Callbacks Do Not Guarantee Business Readiness of All Dependencies

Spring guarantees that dependencies needed for bean creation are resolved according to container lifecycle. However, that does not mean external databases are ready, brokers accept connections, schema migrations have completed, or remote services are healthy. Those conditions require dedicated health checks, retries, readiness probes, or orchestration.

## 10. Testing EnvironmentAware

A class implementing `EnvironmentAware` can be tested by creating a small context and letting Spring invoke the callback, or by invoking the callback directly in a unit test if you only want to test environment-reading logic.

Example class:

~~~java
@Component
public class RegionResolver implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String resolve() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

Unit testing the callback directly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class RegionResolverTest {
    @Test
    void returnsConfiguredRegion() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("app.region", "apac");

        RegionResolver resolver = new RegionResolver();
        resolver.setEnvironment(environment);

        assertEquals("apac", resolver.resolve());
    }

    @Test
    void usesDefaultWhenPropertyIsMissing() {
        RegionResolver resolver = new RegionResolver();
        resolver.setEnvironment(new MockEnvironment());

        assertEquals("local", resolver.resolve());
    }
}
~~~

This test calls the callback directly to verify property-reading logic; it does not verify that Spring invokes the Aware callback automatically during bean creation.

To test container integration, use `ApplicationContextRunner` or `AnnotationConfigApplicationContext` to register the class and retrieve the bean after context refresh.

### 10.1. Testing with StandardEnvironment

You can create a `StandardEnvironment` and add a property source:

~~~java
var environment = new StandardEnvironment();
environment.getPropertySources().addFirst(
        new MapPropertySource(
                "test",
                Map.of("app.region", "emea")
        )
);
~~~

Then pass the environment into the bean or register an appropriate environment for the test context. Spring Test's `MockEnvironment` is usually more convenient for simple property unit tests.

## 11. Testing ApplicationContextAware

If a class genuinely needs the context, tests can spin up a small context:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ContextInformationTest {
    @Test
    void receivesOwningApplicationContext() {
        try (var context =
                new AnnotationConfigApplicationContext(ContextInformation.class)) {
            ContextInformation bean = context.getBean(ContextInformation.class);
            assertNotNull(bean.contextDisplayName());
        }
    }
}
~~~

This example requires the `ContextInformation` class declared earlier. When the context refreshes, Spring creates the bean and calls `setApplicationContext`. The test retrieves the bean after context initialization.

The test only proves the callback is invoked inside that context. It does not prove that using `ApplicationContext` is the best design for business logic. If the real goal is publishing events or looking up an extension, test the narrower abstraction instead.

## 12. Narrower Aware Interfaces Worth Knowing

Spring offers multiple Aware interfaces so a bean receives only the capability it needs. Using narrower interfaces reduces coupling.

### 12.1. ApplicationEventPublisherAware

Used when a framework component needs a callback to receive the publisher:

~~~java
@Component
public class AuditEventSource implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

In ordinary applications, constructor-injecting `ApplicationEventPublisher` is usually clearer:

~~~java
@Component
public class AuditEventSource {
    private final ApplicationEventPublisher publisher;

    public AuditEventSource(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

### 12.2. MessageSourceAware

Used when a component needs to look up configured messages. If only the message source is needed, there is no need for the full context.

### 12.3. ResourceLoaderAware

Used when a framework integration component needs to receive the resource loader via callback. If ordinary application code needs to load resources, constructor-injecting `ResourceLoader` is easier to test.

### 12.4. BeanFactoryAware

`BeanFactoryAware` provides a lower-level bean factory than `ApplicationContext`. It is still container coupling and usually fits only infrastructure components, factories, or extension points that genuinely need the bean factory API.

Do not swap `ApplicationContextAware` for `BeanFactoryAware` merely to avoid the `ApplicationContext` name while keeping the service locator pattern. Inject the exact collaborators needed.

## 13. Distinguishing Aware Interfaces from Configuration Annotations

Certain annotations also let classes or methods consume Spring configuration, yet their semantics differ from Aware callbacks.

| Mechanism | Role |
| --- | --- |
| `EnvironmentAware` | Receives `Environment` via a lifecycle callback |
| Constructor injection of `Environment` | Receives `Environment` as a construction dependency |
| `@Value` | Binds a property/expression value into a field, parameter, or method |
| `@ConfigurationProperties` | Binds a structured group of properties into an object |
| `@Profile` | Conditional bean registration based on active profiles |
| `@ConditionalOnProperty` | Auto-configuration condition based on a property |
| `ApplicationContextAware` | Receives the entire context via a callback |
| `@Import` / `@Bean` | Registers and wires bean definitions |

If you merely want to select a bean by profile, there is no need to inject `Environment` and write `if`/`else` logic everywhere. You can use `@Profile` or an appropriate condition right in configuration.

Example:

~~~java
@Configuration
@Profile("dev")
class DevelopmentMailConfiguration {
    @Bean
    MailSender mailSender() {
        return new ConsoleMailSender();
    }
}

@Configuration
@Profile("prod")
class ProductionMailConfiguration {
    @Bean
    MailSender mailSender(ProductionMailClient client) {
        return new ProductionMailSender(client);
    }
}
~~~

Each configuration is responsible for registering the implementation matching the environment. Services simply inject `MailSender` without knowing which profile is active.

## 14. Common Errors and Misconceptions

| Symptom or misconception | Cause | How to resolve |
| --- | --- | --- |
| `Environment` field is null | Object was created with `new` or callback has not been called by Spring yet | Let Spring manage the bean or use constructor injection |
| `ApplicationContext` field is null | Bean was not created by the context or code accesses it too early | Check lifecycle and how the object is instantiated |
| `ApplicationContextAware` used to fetch every dependency | Service locator hides dependencies | Inject collaborators via constructor |
| Cannot read a property | Wrong key, property source not loaded, or different profile | Check `Environment`, active profiles, and configuration sources |
| Property returns null | Using `getProperty` without a default for a missing key | Supply a default or use `getRequiredProperty` if mandatory |
| `getBean` fails | Bean not registered, wrong name, or wrong type | Check bean definitions, scope, and qualifiers |
| Order-dependent tests | Static context or shared mutable state | Remove global holders, create isolated contexts, and close them properly |
| Aware callback ran, yet remote service is not ready | Callbacks only reflect container lifecycle | Use health checks/retries/readiness checks |
| Reading a property in the constructor from an Aware field | Callback happens after the constructor | Use constructor injection or read in an appropriate lifecycle callback |
| Bean coupled to a specific context | Container coupling limits reusability | Inject narrower abstractions |

### 14.1. Do Not Use Environment as Arbitrary Runtime State Storage

`Environment` primarily represents configuration and profiles. Do not add mutable property sources to store per-request data, user state, or frequently changing business state. Such data belongs in domain objects, databases, caches, or contexts with matching lifecycles.

### 14.2. Do Not Treat Profiles as Security

Profiles help choose beans/configurations per environment, such as dev/test/prod. They do not authenticate users and do not enforce endpoint authorization. Security requires proper authentication, authorization, and secret management.

### 14.3. Do Not Overuse ApplicationContextAware in the Domain Layer

If a business class receives the entire `ApplicationContext`, it can look up any bean in the future. This prevents the constructor from reflecting the full dependency graph and blurs architectural boundaries. Keep the container at the composition/infrastructure layer whenever possible.

## 15. Guide to Choosing the Right Mechanism

Based on practical needs:

| Need | Usually appropriate choice |
| --- | --- |
| Read a single property | `@Value` or constructor parameter |
| Read a structured group of settings | `@ConfigurationProperties` |
| Check profile to register beans | `@Profile` or conditional configuration |
| Infrastructure component needing an `Environment` callback | `EnvironmentAware` |
| Publish events | `ApplicationEventPublisher` |
| Optional/lazy bean lookup | `ObjectProvider<T>` |
| Need all implementations | Inject `List<T>` / `Map<String, T>` |
| Load resources | `ResourceLoader` |
| Framework extension needing the owning context | `ApplicationContextAware` |
| Business service calling collaborators | Constructor injection |

A practical principle: **choose the smallest dependency that satisfies the class's responsibility**. Accept the full `ApplicationContext` only when the class genuinely needs context-level functionality and itself belongs to the container-integration layer.

## 16. Practice Exercises

### Exercise 1 — Reading Profiles via EnvironmentAware

Create an `EnvironmentReporter` bean implementing `EnvironmentAware`. Configure two profiles `dev` and `prod`. Write a method returning the active profile list and test with two different configurations.

### Exercise 2 — Migrating from Aware to Constructor Injection

Take a `FeaturePolicy` class implementing `EnvironmentAware` solely to read `feature.audit.enabled`. Rewrite it using constructor injection of `Environment` or `@ConfigurationProperties`. Compare testability and container coupling.

### Exercise 3 — Replacing a Service Locator

Take a class using `ApplicationContextAware` and `getBean("csvExporter")` to retrieve an exporter. Replace it with constructor injection of `Map<String, Exporter>` or a registry with an explicit API. Write a unit test without Spring.

### Exercise 4 — Choosing a Narrower Abstraction

A component implements `ApplicationContextAware` solely to call `publishEvent`. Replace it with `ApplicationEventPublisher` via constructor. Explain why the new dependency expresses the exact responsibility.

### Exercise 5 — Testing Lifecycle Callbacks

Write a context test confirming Spring calls `setEnvironment` before `@PostConstruct`. Then instantiate the same class with `new` and explain why the callback does not run automatically.

## 17. Key Takeaways

`EnvironmentAware` and `ApplicationContextAware` are lifecycle callbacks that let a bean receive abstractions from the Spring container. `EnvironmentAware` supplies configuration environment and profiles; `ApplicationContextAware` supplies the broader context with access to beans, resources, events, and message sources.

They are invoked by Spring only when the bean is actually container-managed. Callbacks run after instance creation and dependency/property population, and before initialization callbacks such as `@PostConstruct`. Therefore, do not access Aware fields in constructors and do not expect `new`-ed objects to receive callbacks automatically.

For business services, constructor injection is usually clearer and easier to test. Use `@Value` for single properties, `@ConfigurationProperties` for grouped settings, `ApplicationEventPublisher` to publish events, `ResourceLoader` to load resources, or `ObjectProvider` for intentional dynamic lookup. Reserve `ApplicationContextAware` for infrastructure components that genuinely need the owning context; avoid turning it into a service locator or static global context.
