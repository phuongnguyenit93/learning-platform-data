# Setter Injection for Optional or Reconfigurable Dependencies

In Spring, **constructor injection** is usually the first choice for required dependencies: a service needs a repository, a controller needs a service, or a processor needs a business policy. However, some dependencies are not always present, are only used in certain environments, or require a separate configuration point after the object has been created. In those cases, **setter injection** can be an appropriate choice.

Setter injection is a way of passing a dependency into an object through a setter method after the constructor has created the object. Spring invokes that method during bean initialization and resolves the dependency according to configuration. This approach allows a dependency to be omitted or changed via a setter API, while also leaving the object with state that can change after creation.

It is important to distinguish two ideas:

- **Optional dependency:** the application still works when a supporting bean is absent, such as metrics, secondary notifications, or environment-specific integrations.
- **Reconfigurable dependency:** the object exposes a point to receive a different value or implementation when configuration is intentionally updated.

Setter injection supports providing dependencies flexibly. However, setter injection by itself **does not create a mechanism to automatically reload configuration or swap dependencies while the application is running**. Runtime changes require a separate design and mechanism.

## 1. How Does Setter Injection Work?

Example of a Java class with a setter:

~~~java
public class ReportService {

    private ReportExporter exporter;

    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

If the object is constructed manually, the caller can do:

~~~java
ReportService service = new ReportService();
service.setExporter(new PdfReportExporter());
~~~

With Spring, you can annotate the setter with **@Autowired**:

~~~java
@Service
public class ReportService {

    private ReportExporter exporter;

    @Autowired
    public void setExporter(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

When creating the **ReportService** bean, Spring instantiates the object first, then calls the setter and passes in the matching **ReportExporter** bean. General sequence:

~~~text
Spring ApplicationContext
        │
        ▼
Call constructor ReportService()
        │
        ▼
ReportService object is created
        │
        ▼
Resolve ReportExporter bean
        │
        ▼
Call setExporter(exporter)
        │
        ▼
Subsequent bean initialization steps
        │
        ▼
ReportService ready for use
~~~

Spring manages finding the bean and invoking the setter; **ReportService** still defines how the exporter is used in business logic. The annotation does not decide report formats or file contents on its own.

### How does setter injection differ from constructor injection?

| Criterion | Constructor injection | Setter injection |
|---|---|---|
| When dependency is received | During object creation | After the constructor completes |
| Best suited for | Required dependencies | Optional dependencies or dedicated configuration points |
| Object state | Can be complete immediately after constructor | May lack dependencies until the setter is called |
| Immutability | Easy to use `final` for dependencies | Dependencies typically live in mutable fields |
| Plain Java testing | Pass dependencies directly at creation | Create object, then call setter |
| Main risk | Constructor has too many parameters if class takes on too many responsibilities | Object may exist in an incomplete state or be mutated unexpectedly |

Example of constructor injection for a required dependency:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

If **InvoiceRepository** is missing, Spring should fail context initialization. This is good behavior: the service cannot perform its core function without the repository.

By contrast, a **MetricsRecorder** used only to record secondary metrics may be optional. If this bean is not configured in some environment, the service can still create invoices normally. Setter injection can express that case.

## 2. Setter Injection for Optional Dependencies Using @Autowired(required = false)

Spring allows marking an injection method with **@Autowired(required = false)**. If the dependency cannot be resolved, that injection method will not be called.

~~~java
public interface MetricsRecorder {
    void recordInvoiceCreated();
}
~~~

A service using this dependency as a supporting feature:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private MetricsRecorder metricsRecorder;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Autowired(required = false)
    public void setMetricsRecorder(MetricsRecorder metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        if (metricsRecorder != null) {
            metricsRecorder.recordInvoiceCreated();
        }

        return invoice;
    }
}
~~~

In the example:

- **InvoiceRepository** is a required dependency, received via the constructor.
- **MetricsRecorder** is an optional dependency, received via the setter.
- If no **MetricsRecorder** bean exists, Spring skips the setter and the field remains **null**.
- When creating an invoice, the service checks whether the recorder is present before calling it.

Important condition: an optional dependency must genuinely be **optional for business correctness**. If its absence causes data loss or prevents orders from completing, do not silently treat it as optional.

### What does @Autowired(required = false) mean?

The value **required = false** applies to the annotated injection point. For a single-parameter setter like the example, if no matching bean exists, Spring does not call that method. For an injection method with multiple parameters, Spring only invokes the method when it can resolve the required dependencies according to that injection point's rules.

If there are **multiple MetricsRecorder beans** and Spring does not know which one to pick, **required = false** does not mean "ignore all errors." Ambiguity in bean selection still needs to be resolved with **@Qualifier**, **@Primary**, or explicit configuration.

### Avoiding NullPointerException

After using an optional setter, the field may remain unassigned. Therefore, every call site must handle the absent state:

~~~java
if (metricsRecorder != null) {
    metricsRecorder.recordInvoiceCreated();
}
~~~

Never call **metricsRecorder.recordInvoiceCreated()** directly if the bean truly might not exist.

Additionally, if the object is created manually outside Spring, Spring will not call the setter automatically. In that case the field can also be null. This is another reason for the class's API to make clear which dependencies are mandatory and which are optional.

## 3. Using Optional<T> to Represent Absence

Another approach is to declare the dependency using **Optional<T>**. Spring supports resolving an Optional dependency: if a matching bean exists, Optional wraps the bean; if not, it receives **Optional.empty()**.

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private Optional<MetricsRecorder> metricsRecorder = Optional.empty();

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Autowired
    public void setMetricsRecorder(
            Optional<MetricsRecorder> metricsRecorder) {
        this.metricsRecorder = metricsRecorder;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        metricsRecorder.ifPresent(
                MetricsRecorder::recordInvoiceCreated);

        return invoice;
    }
}
~~~

Compared to a nullable field, **Optional** makes the absent state more explicit in the type system:

~~~text
Optional<MetricsRecorder>
        │
        ├── Optional.of(recorder)  → recorder present
        │
        └── Optional.empty()       → no recorder
~~~

In this example, the setter is annotated with **@Autowired** (which defaults to required), yet a dependency of type **Optional<MetricsRecorder>** can still resolve to **Optional.empty()** when no bean exists. There is no need to combine **required = false** just to make Optional optional.

**Choose one consistent style.** For optional dependencies, you can use a setter with **@Autowired(required = false)** plus a nullable field, or a setter accepting **Optional<T>**. Avoid mixing multiple mechanisms without reason.

## 4. Setter Injection with @Nullable

Spring also supports marking an injection parameter as nullable using the **@Nullable** annotation:

~~~java
@Autowired
public void setMetricsRecorder(
        @Nullable MetricsRecorder metricsRecorder) {
    this.metricsRecorder = metricsRecorder;
}
~~~

In Spring Framework, you can use **org.springframework.lang.Nullable** in compatible versions. Different nullability annotations may be used depending on the ecosystem and version; choose one consistently across the project.

When the bean is absent, the parameter can receive null. This is concise, but the field and all call sites must still follow null-handling conventions. If you want to express the absent state directly in the parameter type, **Optional<T>** is often easier to read.

Do not mark an important dependency as nullable just so the application can start. If the service cannot do its job properly without the dependency, let Spring report the error clearly at startup.

## 5. Comparing Ways to Express Optional Dependencies

| Approach | When dependency is absent | Points to note |
|---|---|---|
| **@Autowired(required = false)** on setter | Setter is not called | Field must have a default value or handle null |
| Setter accepting **Optional<T>** | Receives `Optional.empty()` | Expresses optionality directly in the type |
| **@Nullable T** parameter | May receive null | Requires consistent null-checks |
| **ObjectProvider<T>** | Can check or retrieve bean when needed | Suitable for deferred lookup or multiple candidates |
| **No-op implementation** | Always has a bean, but action does nothing | Eliminates null branches; requires clear naming and behavior |

### No-op implementation: an often simpler alternative

Instead of allowing the metrics bean to be absent, you can provide a default implementation that does nothing:

~~~java
@Component
public class NoOpMetricsRecorder implements MetricsRecorder {

    @Override
    public void recordInvoiceCreated() {
        // Intentionally do not record metrics.
    }
}
~~~

Then the service always receives **MetricsRecorder** via its constructor:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final MetricsRecorder metricsRecorder;

    public InvoiceService(
            InvoiceRepository repository,
            MetricsRecorder metricsRecorder) {
        this.repository = repository;
        this.metricsRecorder = metricsRecorder;
    }
}
~~~

If only **NoOpMetricsRecorder** exists, the dependency is no longer optional at the container level; the service can always invoke the interface. In environments that need real metrics, a different implementation can be selected using profiles/conditional configuration or appropriate bean configuration.

The **No-op pattern** is useful when you want to avoid null branches in services. Only use it, however, if "doing nothing" is genuinely valid behavior. Do not provide a no-op for a mandatory dependency like payment authorization checks, because it can turn a serious configuration error into behavior that appears to succeed.

## 6. ObjectProvider<T> for Flexible Dependency Lookup

**ObjectProvider<T>** is a Spring abstraction that lets you fetch a bean on demand instead of requiring a concrete instance immediately in the constructor or setter.

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final ObjectProvider<MetricsRecorder> metricsProvider;

    public InvoiceService(
            InvoiceRepository repository,
            ObjectProvider<MetricsRecorder> metricsProvider) {
        this.repository = repository;
        this.metricsProvider = metricsProvider;
    }

    public Invoice create(CreateInvoiceCommand command) {
        Invoice invoice = repository.save(Invoice.from(command));

        metricsProvider.ifAvailable(
                MetricsRecorder::recordInvoiceCreated);

        return invoice;
    }
}
~~~

The container can inject **ObjectProvider<MetricsRecorder>** as a bean-access handle. Only when the service calls **ifAvailable** does the provider search for a matching bean; if none exists, the callback does not run.

A provider is useful when:

- The dependency may not exist.
- You want to defer when the bean is resolved.
- Multiple beans exist and you want to use APIs like **orderedStream()** or select according to rules.
- You want to obtain a scoped instance at call time instead of holding a single instance injected upfront.

However, **ObjectProvider** is a Spring API. If the goal is to keep application services independent of the container, you can place an application-owned interface/factory at the appropriate boundary and inject its implementation. Do not use a provider just to avoid declaring dependencies explicitly.

## 7. Setter Injection for Configuration

Setters can also receive configuration values:

~~~java
@Component
public class MessageFormatter {

    private String prefix = "[APP]";

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public String format(String message) {
        return prefix + " " + message;
    }
}
~~~

Spring can call the setter to assign a property when configuring the bean. For a single property, you can use **@Value** on the setter to bind a property placeholder from the Environment, with a default value if needed. If no binding mechanism or caller invokes the setter, the class's default value is retained.

This is **setter-based property injection**. It is still configuration binding at bean creation time. Having a public setter does not mean Spring will automatically watch config files and re-invoke the setter whenever a file changes.

### When there are multiple properties, use @ConfigurationProperties

If a component has several related configuration values, group them into a strongly typed object:

~~~yaml
app:
  notification:
    enabled: true
    sender-name: Learning Platform
    retry-limit: 3
~~~

Using JavaBean setters:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private boolean enabled;
    private String senderName;
    private int retryLimit;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getSenderName() {
        return senderName;
    }

    public void setSenderName(String senderName) {
        this.senderName = senderName;
    }

    public int getRetryLimit() {
        return retryLimit;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }
}
~~~

Registering the properties:

~~~java
@Configuration
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfiguration {
}
~~~

The service can then inject **NotificationProperties** via its constructor. The Spring Boot binder invokes the corresponding setters when binding properties.

~~~java
@Service
public class NotificationService {

    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }
}
~~~

For immutable configuration, you can use constructor binding/records depending on your version and registration style. Setter-based JavaBean properties are an option when a mutable type is needed and the binder uses setters.

**Do not scatter individual property setters across services** if they belong to the same configuration group. A centralized properties class makes configuration easier to read, validate, and manage per environment.

## 8. Is Setter Injection Runtime Reconfiguration?

This is the most important distinction in this lesson.

When Spring initializes a singleton bean, the container calls setter injection to supply dependencies. Once complete, the setter **is not automatically called again** just because:

- An `application.yml` file is edited on disk.
- A process environment variable changes.
- An external service gets a new version.
- A value in the database changes.

Setter injection provides a **point to receive a value**. It is not a mechanism for watching changes, synchronizing state, refreshing beans, or coordinating dependency replacement.

### Case 1: configuration is only needed at startup

If a service URL, timeout, or sender name only needs to be determined at application startup, use **@ConfigurationProperties** or bean configuration. Setter injection may be how the binder assigns properties, but there is no need to expose public setter APIs for arbitrary mutation afterward.

### Case 2: dependencies genuinely need to change at runtime

Suppose the application needs to switch between two implementations of a routing service while the process is running. You can design an abstraction with explicit replacement capability:

~~~java
public interface RouteProvider {
    String routeFor(String destination);
}
~~~

A registry managing the current implementation:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class RouteProviderRegistry {

    private final AtomicReference<RouteProvider> current;

    public RouteProviderRegistry(RouteProvider initialProvider) {
        this.current = new AtomicReference<>(initialProvider);
    }

    public String routeFor(String destination) {
        return current.get().routeFor(destination);
    }

    public void replace(RouteProvider newProvider) {
        Objects.requireNonNull(newProvider, "newProvider");
        current.set(newProvider);
    }
}
~~~

This illustrates an application-owned runtime reconfiguration API, **not Spring setter injection**. Swapping the reference is atomic, yet a real system must also define who is authorized to call **replace**, how the new provider is created and validated, how resources of the old provider are reclaimed, and how in-flight calls are handled.

If you use a public setter on a singleton service to swap dependencies arbitrarily:

~~~java
public void setRouteProvider(RouteProvider provider) {
    this.routeProvider = provider;
}
~~~

then you must consider:

- Another thread might be reading the field while the setter mutates it.
- Is `null` an acceptable value?
- Who is allowed to change it and when?
- Has the new dependency been initialized, connectivity-checked, and made ready?
- Does the old dependency need to close connections, threads, or resources?
- Should an in-progress request continue with the old provider or the new one?

An ordinary setter does not answer these questions on its own. If runtime changes are required, design an intentional replacement API and lifecycle.

## 9. Dynamic Configuration Changes: Setters, Refresh, and State Updates

There are several approaches when a system needs to pick up new configuration:

| Approach | Meaning | Behavior |
|---|---|---|
| **Setter injection** | Assigns dependencies/properties during bean creation | Does not automatically reload when configuration sources change |
| **ConfigurationProperties binding** | Binds configuration into a typed object | Typically occurs during context initialization or when the binder runs |
| **Refresh mechanism** | Requires specific infrastructure to refresh beans/configuration | Only available when the application enables and configures the corresponding refresh mechanism |
| **Application-managed registry** | Application actively swaps implementations/configuration via an API | Requires concurrency management, validation, and lifecycle handling |
| **Recreate ApplicationContext** | Creates a new context with new configuration | Incurs overhead; requires traffic shifting and closing the old context |

Some Spring ecosystems provide context/bean refresh mechanisms, but not every Spring Boot application automatically supports configuration reloading. Be clear about which libraries, versions, and bean types support refresh.

**Do not equate setter injection with refresh scope.** A setter is merely a receiver for a dependency or value. Refresh scope, when provided by specific infrastructure, is a mechanism that manages refreshing targets/proxies under its own contract.

## 10. When Should You Use Setter Injection?

| Scenario | Is setter injection appropriate? | Reason |
|---|---|---|
| Required repository of a service | Usually no | Missing dependency should fail startup; constructor expresses it more clearly |
| Non-mandatory metrics recorder | Possibly | Supporting bean can be absent while core business logic still works |
| Optional environment-specific notification | Possibly | Can be skipped or use a default implementation |
| Configuration group bound via JavaBean setters | Yes | Binder can populate mutable properties |
| Dependency that must change at runtime under controlled workflow | Simple setter is not enough | Needs a reconfiguration API, synchronization, and lifecycle management |
| Class with many required dependencies | Do not move all to setters to avoid a long constructor | Review whether the class has too many responsibilities |
| Dependency needed for rare invocations | Consider `ObjectProvider`/factory | Avoids holding or eagerly creating unnecessary dependencies |

General principles:

1. **Constructor injection for required dependencies.**
2. **Setter injection for truly optional dependencies or justified mutable configuration points.**
3. **Optional<T>, @Nullable, or ObjectProvider<T> to express absence explicitly.**
4. **No-op implementation** when doing nothing by default is valid and removes null branches.
5. **Dedicated runtime reconfiguration mechanism** when changes must happen while the application is running.

## 11. Initialization Order and What Not to Assume

For a normal Spring bean, the constructor is called first. Then the container performs field/method dependency injection and other bean processing steps before initialization callbacks run and the bean enters service according to its lifecycle.

Consequently, never assume inside a constructor that setter injection has already run:

~~~java
@Component
public class ExportService {

    private Exporter exporter;

    public ExportService() {
        // Do not use exporter here if it is only injected via a setter.
    }

    @Autowired
    public void setExporter(Exporter exporter) {
        this.exporter = exporter;
    }
}
~~~

If a dependency is required for the object to be in a valid state right upon creation, placing it in the constructor expresses that accurately. With optional setters, you can use a valid fallback or only access it after confirming the dependency is present.

Do not manually invoke setter injection from another bean to control initialization order. Let the container manage dependency resolution. If special initialization relationships exist, consider bean/factory configuration or appropriate lifecycle callbacks while avoiding circular dependencies.

### Multi-parameter setters

Spring can inject a method with multiple parameters:

~~~java
@Autowired
public void configure(
        Clock clock,
        MetricsRecorder metricsRecorder) {
    // Receive both dependencies.
}
~~~

For an injection method marked required by default, the method's dependencies must be resolved. If one dependency does not exist, Spring cannot invoke the method as expected and bean creation may fail. If the entire method is marked **required = false**, Spring skips the method when the required dependencies cannot be resolved.

If dependencies have different requirement levels, split them into separate constructors/setters or express the optional part with **Optional<T>**. Avoid lumping multiple dependencies into an optional setter and accidentally making required dependencies ambiguous.

## 12. Risks of Overusing Setter Injection

### Object can exist in an incomplete state

The constructor has run, but the setter has not yet been called. If a business method is invoked too early or the object is instantiated manually outside Spring, the field may have no value.

### Dependencies can be mutated unexpectedly

Public setters increase the number of places where an object's state can be modified. A singleton bean shared across many components can be affected if a setter is called after the bean is already active.

### Difficult to guarantee thread safety

Replacing a dependency while multiple threads are using it requires synchronization and clear transition rules. Merely changing a field from null to an object does not address the old dependency's lifecycle or the state of in-flight requests.

### Required dependencies disguised as optional

Marking **required = false** on a core repository or policy can allow the application to start, only to fail when a user invokes the feature. Configuration errors should be caught as early as possible.

### Tests require multi-step setup

With setter injection, tests must create the object and then call setters before asserting. If that step is forgotten, the test may hit null or run with an unintended fallback. Constructor injection usually makes required state explicit at creation time.

~~~java
InvoiceService service = new InvoiceService(repository);
service.setMetricsRecorder(metricsRecorder);
~~~

The test snippet above shows two setup steps. If **metricsRecorder** is required, it should be moved into the constructor so the API communicates the requirement from the start.

## 13. Testing Behavior When an Optional Dependency Is Absent

Suppose **InvoiceService** only requires **InvoiceRepository**; **MetricsRecorder** may be absent. A unit test can instantiate the service without Spring:

~~~java
class InvoiceServiceTest {

    @Test
    void createsInvoiceWhenMetricsRecorderIsAbsent() {
        InvoiceRepository repository =
                command -> Invoice.from(command);

        InvoiceService service = new InvoiceService(repository);

        Invoice invoice = service.create(
                new CreateInvoiceCommand("INV-001"));

        assertNotNull(invoice);
    }
}
~~~

This is illustrative code, assuming **InvoiceRepository**, **Invoice**, **CreateInvoiceCommand**, and the **create(...)** method are defined accordingly. The goal is to prove that **the supporting metrics feature is not a prerequisite for creating an invoice**.

If you need to verify specifically that Spring skips the setter when the bean does not exist, you can write a small context test that registers **InvoiceService** and a fake repository without registering **MetricsRecorder**. That test verifies container wiring behavior, whereas the unit test verifies business behavior independently.

The two test scopes differ:

- **Unit test:** does the service behave correctly without the optional collaborator?
- **Spring context test:** does the bean configuration allow Spring to initialize the service successfully when the collaborator is absent?

## 14. Alternatives Worth Considering

### Constructor with Optional

If you still want an optional dependency to be expressed right at object creation:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final Optional<MetricsRecorder> metrics;

    public InvoiceService(
            InvoiceRepository repository,
            Optional<MetricsRecorder> metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }
}
~~~

This keeps the object fully set up after the constructor and explicitly shows the optional dependency. It is a good choice when mutable setters are not needed.

### Factory or ObjectProvider

If you need to retrieve a bean on demand or respect scope, you can use **ObjectProvider<T>** or an application-defined factory interface. This is preferable to holding a field that can be mutated uncontrollably by a setter.

### Conditional beans or profiles

If you want to select an implementation based on the environment, you can define conditional beans or use **@Profile**:

~~~java
@Configuration
public class MetricsConfiguration {

    @Bean
    @Profile("production")
    MetricsRecorder productionMetricsRecorder() {
        return new ProductionMetricsRecorder();
    }

    @Bean
    @Profile("test")
    MetricsRecorder testMetricsRecorder() {
        return new NoOpMetricsRecorder();
    }
}
~~~

This example illustrates selecting implementations by profile; in a real application, ensure only the appropriate implementation is registered for each profile. **Profiles select beans when building the ApplicationContext**, not as a mechanism that swaps beans automatically whenever a profile or environment changes.

## 15. Questions to Ask Before Choosing Setter Injection

Before moving a dependency from a constructor to a setter, ask yourself:

1. Is this dependency truly **optional** for the core functionality to work?
2. If the bean is absent, is the service's behavior well-defined and safe?
3. Can a **No-op implementation** be used to avoid null branches?
4. Would using **Optional<T>** express absence more clearly in code?
5. Is the setter called only during initialization, or is anyone allowed to call it again after the application is running?
6. If replacing a dependency at runtime, do we need thread synchronization, validation of the new provider, and closing of old resources?
7. Could this dependency be configuration like **@ConfigurationProperties** rather than a replaceable object?
8. Does the class have too many dependencies because it has taken on too many responsibilities?

If the dependency is required and the object has no valid state without it, constructor injection is usually the answer. If the dependency is genuinely an add-on feature, a setter/Optional/No-op may fit. If runtime changes are required, design an explicit reconfiguration mechanism instead of relying on a public setter.

## Conclusion

**Setter injection** allows Spring to pass dependencies after the constructor has instantiated the object. It is useful when a collaborator is genuinely optional, or when an object needs a setter API to receive mutable configuration under a defined workflow. With Spring, you can express optional dependencies via **@Autowired(required = false)**, **Optional<T>**, **@Nullable**, **ObjectProvider<T>**, or a default **No-op** implementation.

Use **constructor injection for required dependencies**, because it makes the preconditions for a valid object explicit. Use setters only when the benefits of optionality or mutability are truly needed and the absent state has been handled.

Finally, **setter injection does not equate to runtime reconfiguration**. Spring invokes setters during bean wiring; changing dependencies while the application is running requires its own mechanism to control authorization, concurrency, validity, and the lifecycle of the new implementation. Keeping this boundary clear keeps Spring Boot applications flexible while remaining predictable and maintainable.
