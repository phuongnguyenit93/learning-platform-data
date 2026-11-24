# Tracing Constructors, Init, Proxies, Runners, and Destroy Callbacks

When a Spring Boot application starts, many steps happen in sequence: Spring instantiates objects, injects dependencies, invokes initialization callbacks, optionally wraps objects in AOP proxies, refreshes the application context, runs startup runners, and finally reports the application as ready. When the application stops, Spring invokes resource-closing callbacks and stops lifecycle-managed components.

If you only put `System.out.println()` in a constructor and `@PostConstruct`, you only observe part of the lifecycle. To understand the full log, you must distinguish **a bean's lifecycle**, **when proxies appear**, **the application context lifecycle**, and **Spring Boot startup steps**.

This lesson walks through tracing those stages using constructors, `@PostConstruct`, `InitializingBean`, `BeanPostProcessor`, AOP proxies, `SmartInitializingSingleton`, `ApplicationRunner`, `CommandLineRunner`, `@PreDestroy`, `DisposableBean`, and `SmartLifecycle`. The examples use modern Spring Boot with Spring Framework 6 and Jakarta annotations.

## 1. Four Major Milestones in the Application Lifecycle

An overview:

```text
APPLICATION START
      │
      ▼
Prepare Environment and ApplicationContext
      │
      ▼
Refresh ApplicationContext
      │
      ├── Create eager singletons
      │      │
      │      ├── Constructor
      │      ├── Inject dependencies / populate properties
      │      ├── Aware callbacks
      │      ├── BeanPostProcessor before initialization
      │      ├── Init callbacks
      │      └── BeanPostProcessor after initialization
      │
      ├── SmartInitializingSingleton callbacks
      ├── SmartLifecycle start
      └── ContextRefreshedEvent
      │
      ▼
ApplicationStartedEvent
      │
      ▼
ApplicationRunner / CommandLineRunner
      │
      ▼
ApplicationReadyEvent
      │
      ▼
APPLICATION READY
      │
      │  Requests / scheduled work / message processing
      │
      ▼
SHUTDOWN
      │
      ├── ContextClosedEvent
      ├── SmartLifecycle stop
      ├── Bean destruction callbacks
      └── Release container resources
```

The diagram shows two different kinds of timing:

- `init`/`destroy` callbacks belong to **a single bean**.
- Runners and application events belong to **application startup**.

`SmartLifecycle` is yet another lifecycle mechanism: components are started and stopped by the application context's lifecycle processor.

Not every bean is created immediately at startup. Lazy beans, prototype beans, and beans created only on request can appear later. Therefore, actual log ordering also depends on the dependency graph, lazy initialization, and application configuration.

## 2. Bean Lifecycle vs. `ApplicationContext` Lifecycle

**Bean lifecycle** describes how Spring manages one object:

1. Instantiate the object.
2. Inject dependencies and populate properties.
3. Invoke pre/post-initialization callbacks.
4. Put the bean into use.
5. Invoke destruction callbacks when the bean is managed and the context closes.

**`ApplicationContext` lifecycle** describes building and closing the container:

- Prepare the environment and bean definitions.
- Refresh the context.
- Start lifecycle components.
- Publish context/application events.
- Execute startup runners.
- Close the context and destroy singleton beans.

For instance, `@PostConstruct` runs when a specific bean is initialized. `ApplicationRunner` runs after the application context has refreshed. The two callbacks are not in the same phase.

## 3. Constructor: Spring Creates the Instance

The constructor is called when Spring needs to create a bean instance.

```java
@Component
public class OrderService {

    public OrderService() {
        System.out.println("[OrderService] constructor");
    }
}
```

If the bean uses constructor injection:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
        System.out.println("[OrderService] constructor");
    }
}
```

Spring must resolve `OrderRepository` before invoking `OrderService`'s constructor, then pass the dependency into the constructor.

Inside the constructor, constructor-injected dependencies are already available. However, field injection and setter injection on that same bean have not yet completed when the constructor runs.

Therefore, avoid reading `@Autowired` fields inside a constructor if those fields are injected after object creation.

## 4. Constructor Injection and Field Injection Happen at Different Times

Constructor injection:

```java
@Component
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
        System.out.println("constructor: repository available");
    }
}
```

Field injection:

```java
@Component
public class ReportService {

    @Autowired
    private ReportRepository repository;

    public ReportService() {
        System.out.println("constructor: repository is not injected yet");
    }

    @PostConstruct
    void initialize() {
        System.out.println("init: repository available = "
                + (repository != null));
    }
}
```

In the second example, Spring instantiates the object first and populates the field afterward. By the time `@PostConstruct` is invoked, field injection has finished.

Constructor injection is usually easier to observe and test because an object cannot be created without its required dependencies. It also allows declaring dependencies as `final`.

## 5. Property Population and Dependency Injection

After creating the instance, Spring populates bean properties. This can include:

- Resolving dependencies for field injection.
- Invoking setter injection.
- Applying values configured via bean definitions.
- Performing container-managed population steps.

Setter injection example:

```java
@Component
public class SearchService {

    private SearchRepository repository;

    @Autowired
    public void setRepository(SearchRepository repository) {
        this.repository = repository;
        System.out.println("[SearchService] setter injection");
    }
}
```

When tracing logs, you will see constructors run before setters. Do not rely on global bean creation order to assume one bean is always created before another; Spring instantiates dependencies according to the graph, and other beans may be initialized for various reasons.

## 6. Aware Callbacks: Beans Receiving Container Information

Some beans need information about the container managing them. Spring provides `Aware` interfaces.

Example:

```java
@Component
public class ContainerAwareProbe
        implements BeanNameAware, BeanFactoryAware {

    @Override
    public void setBeanName(String name) {
        System.out.println("[Aware] bean name = " + name);
    }

    @Override
    public void setBeanFactory(BeanFactory beanFactory) {
        System.out.println("[Aware] BeanFactory injected");
    }
}
```

Common interfaces:

| Interface | Information provided |
|---|---|
| `BeanNameAware` | Bean name in the container |
| `BeanClassLoaderAware` | Associated ClassLoader |
| `BeanFactoryAware` | BeanFactory managing the bean |
| `EnvironmentAware` | Environment |
| `ResourceLoaderAware` | ResourceLoader |
| `ApplicationEventPublisherAware` | Event publisher |
| `MessageSourceAware` | MessageSource |
| `ApplicationContextAware` | ApplicationContext |

`Aware` callbacks run after the bean has been created and dependency population has occurred, prior to normal initialization callbacks.

Do not implement multiple `Aware` interfaces merely as a shortcut to pull arbitrary dependencies from the container. Constructor injection generally expresses dependencies more clearly. Use `Aware` when a bean genuinely integrates with container infrastructure.

## 7. `BeanPostProcessor`: Observing Before and After Initialization

`BeanPostProcessor` lets Spring process beans before and after initialization callbacks.

Two key methods:

```java
Object postProcessBeforeInitialization(
        Object bean,
        String beanName
)

Object postProcessAfterInitialization(
        Object bean,
        String beanName
)
```

A simple processor:

```java
public class TraceBeanPostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) {

        System.out.println(
                "[BPP before] " + beanName
                        + " : " + bean.getClass().getName()
        );

        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) {

        System.out.println(
                "[BPP after] " + beanName
                        + " : " + bean.getClass().getName()
        );

        return bean;
    }
}
```

The processor must return the bean (or a replacement wrapper/proxy) for the container to keep using. Returning `null` can halt subsequent post-processing according to the `BeanPostProcessor` contract; do not return `null` arbitrarily to skip a bean.

## 8. Registering `BeanPostProcessor` Properly

You can register a processor via a `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class TraceConfiguration {

    @Bean
    static BeanPostProcessor traceBeanPostProcessor() {
        return new TraceBeanPostProcessor();
    }
}
```

`BeanPostProcessor` is part of bean-creation infrastructure and is registered early during refresh. Using a `static` `@Bean` method for the processor avoids prematurely instantiating the enclosing configuration class.

In large applications, an unfiltered processor can emit a huge amount of logs. Filter beans by package or name to observe, avoiding logging all framework beans and sensitive details.

Do not inject ordinary application beans into a `BeanPostProcessor`'s constructor unless you fully understand the early-initialization consequences. Dependencies of a processor may be instantiated before other processors are registered, leaving some beans un-processed or ineligible for auto-proxying.

## 9. Order of Initialization Callbacks

For an ordinary bean, Spring's standard initialization callback order is:

1. `BeanPostProcessor.postProcessBeforeInitialization(...)`.
2. `@PostConstruct`.
3. `InitializingBean.afterPropertiesSet()`.
4. Custom init method declared on the bean definition or `@Bean(initMethod=...)`.
5. `BeanPostProcessor.postProcessAfterInitialization(...)`.

Corresponding `Aware` callbacks run before the pre-initialization post-processing step.

Example:

```java
@Component
public class LifecycleProbe implements InitializingBean {

    public LifecycleProbe() {
        System.out.println("1. constructor");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("2. @PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("3. afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("4. custom init");
    }
}
```

Declare a custom init method for the bean using `@Bean` or a bean definition as shown in the next section. The numbers in the logs merely illustrate the expected order for a single bean; logs from other beans may interleave due to the dependency graph.

## 10. `@PostConstruct`

`@PostConstruct` marks a method called after dependency injection completes and before the bean enters normal use.

```java
import jakarta.annotation.PostConstruct;

@Component
public class CacheWarmup {

    private final ProductRepository repository;

    public CacheWarmup(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void warmup() {
        System.out.println("CacheWarmup initialized");
        // Can prepare required internal state.
    }
}
```

In Spring Framework 6 and Spring Boot 3, the standard annotation is `jakarta.annotation.PostConstruct`. Older Spring 5/Boot 2 projects typically use `javax.annotation.PostConstruct`.

Modern JDKs no longer bundle these Java EE/Jakarta annotations by default; the dependency providing the annotation may need to be declared depending on the framework line and starter in use.

`@PostConstruct` methods typically take no parameters, return nothing, and should be brief. Do not use them to start an infinite loop or block indefinitely waiting on an external system.

## 11. `InitializingBean.afterPropertiesSet()`

`InitializingBean` is a Spring-provided interface:

```java
public interface InitializingBean {
    void afterPropertiesSet() throws Exception;
}
```

Example:

```java
@Component
public class SearchIndexManager implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("SearchIndexManager ready");
    }
}
```

`afterPropertiesSet()` runs after property/dependency injection and after `@PostConstruct` in the standard initialization sequence.

Its advantage is expressing the callback via an interface. Its drawback is coupling the class directly to Spring APIs. If you want domain/application classes less coupled to Spring, `@PostConstruct` or a custom init method may be a better fit.

Do not implement `InitializingBean` just to print a log line; it is meaningful when the bean genuinely needs an initialization step tied to the interface contract.

## 12. Custom Init Method with `@Bean`

You can use `initMethod` on `@Bean`:

```java
public class ExternalClientHolder {

    public void connect() {
        System.out.println("ExternalClientHolder initialized");
    }

    public void disconnect() {
        System.out.println("ExternalClientHolder destroyed");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(
        initMethod = "connect",
        destroyMethod = "disconnect"
    )
    ExternalClientHolder externalClientHolder() {
        return new ExternalClientHolder();
    }
}
```

This works well when the class was not designed to implement Spring lifecycle interfaces or when you want to keep lifecycle configuration inside a configuration class.

Spring calls the custom init method after `@PostConstruct` and `afterPropertiesSet()` if the bean uses those mechanisms as well.

The method must fit the init/destroy contract: typically a no-argument method returning `void` or a compatible lifecycle invocation type; public no-arg `void` methods are the clearest choice.

## 13. Combining All Three Init Callbacks

A bean can use multiple mechanisms:

```java
@Component
public class MultiInitProbe implements InitializingBean {

    public MultiInitProbe() {
        System.out.println("constructor");
    }

    @PostConstruct
    void postConstruct() {
        System.out.println("@PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("customInit");
    }
}
```

If the bean is registered via component scanning, there is no automatic `initMethod` attribute pointing to `customInit`. You would need to declare the custom init via an appropriate bean definition or choose a different registration mechanism.

In production code, pick a single callback suited to your needs. Using all three is useful in an observation exercise, but in real applications it fragments initialization logic and makes it harder to follow.

## 14. Post-Initialization `BeanPostProcessor` and AOP Proxies

Several Spring features use a `BeanPostProcessor` to create proxies, for example:

- `@Transactional`.
- `@Async`.
- `@Cacheable`.
- Custom Spring AOP aspects.

The auto-proxy creator typically detects beans requiring advice and wraps the target in a proxy during post-initialization processing.

General flow:

```text
Create target object
      │
      ▼
Inject dependencies
      │
      ▼
Init callbacks on target
      │
      ▼
BeanPostProcessor after initialization
      │
      ▼
AOP infrastructure checks advisors
      │
      ├── No proxy needed ────► Return target
      │
      └── Proxy needed ───────► Return proxy
                                  │
                                  ▼
                         Consumer receives bean
```

This is the normal model. Circular dependencies and early references can complicate the process; avoid using a simplified diagram to reason about every advanced edge case.

## 15. Proxy Differs from Target Object

Suppose:

```java
@Service
public class InvoiceService {

    @Transactional
    public void createInvoice() {
        System.out.println("create invoice");
    }
}
```

Spring can expose a proxy in place of the target `InvoiceService`. Consumers inject the bean by type and call methods through the proxy. The proxy applies transaction advice before delegating to the target.

You can inspect this in diagnostic code:

```java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(invoiceService);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(invoiceService);
boolean cglibProxy = AopUtils.isCglibProxy(invoiceService);
```

Do not put these proxy checks into business logic. They belong in diagnostics or tests when verifying AOP configuration.

## 16. JDK Dynamic Proxy vs. Class-Based Proxy

Two common proxy forms:

| Type | Characteristics |
|---|---|
| JDK dynamic proxy | Interface-based proxy |
| Class-based proxy (usually via CGLIB) | Creates a subclass of the target class |

With a JDK proxy, consumers typically access the bean through its interface. A class-based proxy can expose the class type, but carries subclassing limitations, such as being unable to override `final` methods.

Proxy selection depends on AOP and framework configuration. Do not assume every bean with `@Transactional` has the exact same runtime class as in source code.

When logging `bean.getClass().getName()` in a `BeanPostProcessor`, you may see the proxy class in the after-initialization stage. Proxy names can be long and differ between JDK and CGLIB; never use generated class names as an application contract.

## 17. Self-Invocation: Calling via `this` Bypasses the Proxy

Example:

```java
@Service
public class BillingService {

    public void process() {
        save();
    }

    @Transactional
    public void save() {
        // Persist data.
    }
}
```

Calling `save()` from `process()` is an internal call via `this`, which does not pass through the outer proxy in the standard proxy-based AOP model. Consequently, transaction advice may not be applied to that call.

Common fixes:

- Move the transactional operation to a separate bean and inject it through its proxy.
- Call through the proxied bean from an appropriate consumer.
- Use AspectJ weaving if the project genuinely requires interception for self-invocation and is configured properly.

Tracing proxies reveals that **having a proxied bean does not mean every method call passes through the proxy**.

## 18. Constructors and `@Transactional` Methods

Do not call methods requiring AOP advice from a constructor, and do not expect the proxy to be ready inside a constructor.

When the constructor runs, the target instance is still being created. Proxies are normally created during post-initialization processing.

Similarly, inside `@PostConstruct`, the bean is running initialization on the target. Calling another method on the same bean from this callback should not be assumed to pass through the final proxy.

If you need to execute an action after the context has finished refreshing or after the application is ready, pick an appropriate callback/event rather than using a constructor or `@PostConstruct` to force proxy behavior early.

## 19. Circular Dependencies and Early Proxy References

A circular dependency occurs when bean A needs B while B also needs A.

Some singleton circular reference cases can be handled via early references; Spring AOP has related mechanisms to ensure objects are exposed and proxied consistently in certain configurations. However, this makes lifecycle traces more complex.

Common signs:

- A bean is initialized earlier than expected.
- Logs mention "currently in creation."
- The injected bean differs from the target object you observed.
- Some beans are ineligible to be processed by all `BeanPostProcessor`s.
- Constructor circular dependencies generally cannot be resolved the way setter/field circular references sometimes can.

The best approach is designing a cycle-free dependency graph. Separate responsibilities, use events, or invert dependencies where appropriate. Do not rely on early singleton exposure as a routine design technique.

## 20. `SmartInitializingSingleton`

`SmartInitializingSingleton` provides the callback:

```java
void afterSingletonsInstantiated()
```

This callback is invoked after regular singleton beans have been pre-instantiated during refresh.

Example:

```java
@Component
public class StartupRegistry implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println(
                "All regular singletons have been instantiated"
        );
    }
}
```

It is useful when a component needs to know that the creation phase for regular singleton beans has finished, such as building a registry from registered beans.

This is not yet the `ApplicationReadyEvent` signal. After this callback, the context still completes remaining refresh steps and Spring Boot runs application runners.

Un-initialized lazy singleton beans are not guaranteed to exist simply because this callback has run.

## 21. `SmartLifecycle`: Components with Their Own Start/Stop

`SmartLifecycle` extends Spring's lifecycle management with phase control, auto-startup, and asynchronous stop callbacks.

A simple implementation:

```java
@Component
public class MessageConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("Message consumer started");
    }

    @Override
    public void stop() {
        running = false;
        System.out.println("Message consumer stopped");
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

The interface also has related methods/default behaviors such as:

- `isAutoStartup()`.
- `getPhase()`.
- `stop(Runnable callback)`.

Use `SmartLifecycle` when a component must be started and stopped by the context's lifecycle processor, such as consumers, connectors, or background infrastructure with an explicit lifetime.

For a bean that only needs to prepare internal state after injection, `@PostConstruct` is simpler.

## 22. `SmartLifecycle` Phase

`getPhase()` determines start/stop ordering among lifecycle components.

General rule:

- Lower phases start earlier.
- Higher phases start later.
- On stop, the order reverses: higher phases stop first.

Example:

```java
@Override
public int getPhase() {
    return 100;
}
```

If component B requires component A to have started first, you can use appropriate phases to express that order. Keep lifecycle dependencies simple, however, and verify shutdown behavior as well.

`@Order` on a bean does not replace `SmartLifecycle.getPhase()` for controlling start/stop phases. These are two distinct mechanisms.

## 23. `SmartLifecycle` Asynchronous Stop

`SmartLifecycle` has an overload:

```java
@Override
public void stop(Runnable callback) {
    try {
        running = false;
        // Stop accepting new messages and wait for in-flight work.
    }
    finally {
        callback.run();
    }
}
```

The Spring lifecycle processor uses the callback to know when the component has finished stopping. If the callback is not invoked, shutdown may wait until timeout.

In a real implementation, if stopping asynchronously, invoke the callback exactly once after the component has stopped. Do not invoke the callback immediately while resources are still in use.

Use bounded timeouts and log shutdown durations. Never wait indefinitely on an external dependency.

## 24. `ContextRefreshedEvent`

When the application context has refreshed, Spring publishes `ContextRefreshedEvent`.

```java
@Component
public class ContextRefreshListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: "
                        + event.getApplicationContext().getId()
        );
    }
}
```

Events may be published for multiple contexts in a hierarchy. If an application has parent/child contexts, a listener may receive multiple events. When needed, inspect the context ID or context hierarchy to process only the intended context.

`ContextRefreshedEvent` indicates the context has refreshed, but in Spring Boot it does not yet mean the application has completed all startup runners.

## 25. Spring Boot Application Events

Spring Boot publishes several application events during startup/shutdown.

Common events in approximate sequence:

| Event | Approximate timing |
|---|---|
| `ApplicationStartingEvent` | Very early, before Environment and context are ready |
| `ApplicationEnvironmentPreparedEvent` | Environment has been prepared |
| `ApplicationContextInitializedEvent` | Context has been created and initializers have run |
| `ApplicationPreparedEvent` | Context is ready for refresh |
| `ContextRefreshedEvent` | Spring context has refreshed |
| `ApplicationStartedEvent` | Context has refreshed, before runners |
| `ApplicationReadyEvent` | After runners have completed |
| `ContextClosedEvent` | Context is closing |

Some very early events are published before the application context exists. Listeners for those events may need to be registered via `SpringApplication.addListeners(...)` or an appropriate bootstrap mechanism; a `@Component` inside the context will not necessarily receive events that fired before the component was created.

## 26. `ApplicationStartedEvent` and `ApplicationReadyEvent` Differ

`ApplicationStartedEvent` is published after the application context has refreshed and before `ApplicationRunner`/`CommandLineRunner` finish.

`ApplicationReadyEvent` is published after runners complete.

```text
Context refresh complete
        │
        ▼
ApplicationStartedEvent
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
Application accepts traffic
```

Therefore:

- Use `ApplicationStartedEvent` when observing that the context is initialized.
- Use `ApplicationRunner`/`CommandLineRunner` for startup work that must run after refresh.
- Use `ApplicationReadyEvent` when you need to know runners have finished and the application has reached the ready stage.

Do not use `@PostConstruct` as a substitute for the application-ready signal.

## 27. `ApplicationRunner`

`ApplicationRunner` receives `ApplicationArguments`, allowing command-line arguments to be read in parsed form.

```java
@Component
@Order(10)
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ImportRunner started");

        if (args.containsOption("import")) {
            System.out.println("Import option supplied");
        }

        System.out.println("ImportRunner finished");
    }
}
```

`ApplicationArguments` provides:

- `getSourceArgs()`: raw arguments.
- `getOptionNames()`: option names.
- `containsOption(name)`: checks for an option.
- `getOptionValues(name)`: values of an option.
- `getNonOptionArgs()`: non-option arguments.

Example run:

```bash
java -jar app.jar --import=initial data.csv
```

How options are parsed depends on command-line syntax; use `ApplicationArguments` rather than splitting strings manually.

## 28. `CommandLineRunner`

`CommandLineRunner` receives raw arguments as `String...`.

```java
@Component
@Order(20)
public class StartupReportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "StartupReportRunner args = "
                        + Arrays.toString(args)
        );
    }
}
```

It fits when you want to read raw arguments directly or run a simple startup task.

Comparison:

| Criterion | `ApplicationRunner` | `CommandLineRunner` |
|---|---|---|
| Parameter | `ApplicationArguments` | `String... args` |
| Parsed options | Yes | Handle manually |
| Non-option args | Dedicated API | Present in raw array |
| Execution timing | After context refresh | After context refresh |
| Purpose | Startup task | Startup task |

The two interfaces are not separate phases. Spring Boot invokes both during startup runner invocation.

## 29. Ordering Multiple Runners with `@Order`

If there are multiple runners, you can use `Ordered` or `@Order`.

```java
@Component
@Order(10)
public class DatabaseCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("10 - database check");
    }
}
```

```java
@Component
@Order(20)
public class CacheWarmupRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("20 - cache warmup");
    }
}
```

```java
@Component
@Order(30)
public class StartupSummaryRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("30 - startup summary");
    }
}
```

During runner invocation, Spring Boot applies ordering based on `Ordered`/`@Order` across runner beans. Lower order values run earlier.

Do not rely on component scanning order or class names. If one runner depends on another, declare ordering explicitly or consolidate orchestration into a component with clear responsibility.

## 30. When Do Runners Execute Compared to `@PostConstruct`?

A comparative example:

```java
@Component
public class StartupProbe {

    public StartupProbe() {
        System.out.println("constructor");
    }

    @PostConstruct
    void initialize() {
        System.out.println("@PostConstruct");
    }
}
```

```java
@Component
public class StartupProbeRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner");
    }
}
```

`StartupProbe`'s logs appear while beans are being created, typically before context refresh finishes. The runner executes after the context has refreshed.

If the runner injects `StartupProbe`, the dependency is created before the runner runs. However, unrequested lazy beans may not exist yet.

Use init callbacks for a bean's internal initialization; use runners for application-level work after the context is ready and ordinary dependencies are injected.

## 31. Does a Failing Runner Fail Startup?

Yes. If an `ApplicationRunner` or `CommandLineRunner` throws an unhandled exception, startup can fail and the application will not publish `ApplicationReadyEvent` along the normal success path.

Example:

```java
@Component
public class RequiredDataCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (!requiredDataAvailable()) {
            throw new IllegalStateException(
                    "Required startup data is unavailable"
            );
        }
    }

    private boolean requiredDataAvailable() {
        return true;
    }
}
```

This provides fail-fast behavior for mandatory prerequisites.

If the work is optional, handle errors intentionally and record degraded state. Do not catch all exceptions and ignore them, causing the application to report ready when core functionality is not prepared.

## 32. Do Not Use Runners for Infinite Loops

Runners are designed for finite startup work. Avoid writing:

```java
@Override
public void run(ApplicationArguments args) {
    while (true) {
        pollMessages();
    }
}
```

Such a loop prevents startup from completing, blocking `ApplicationReadyEvent` and stopping readiness from transitioning to accept traffic as expected.

For lifecycle-managed background components, consider:

- `SmartLifecycle`.
- Managed `TaskExecutor`/`TaskScheduler`.
- Spring-managed message listener containers.
- `@Scheduled` for appropriate periodic tasks.
- A worker service with explicit start/stop mechanisms.

Do not spawn unmanaged threads and leave them running across shutdown without a stop mechanism.

## 33. `ApplicationReadyEvent`

You can listen for when the application has finished startup:

```java
@Component
public class ReadyListener {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "Application ready: "
                        + event.getApplicationContext().getId()
        );
    }
}
```

This event is suitable for:

- Recording startup completion.
- Emitting an internal observability signal.
- Starting a small post-startup action if required by design.

Do not use this listener to replace the entire readiness/health system. Spring Boot has availability states and Actuator health to coordinate with orchestrators.

If a prerequisite failure must block the application from becoming ready, perform it in a runner or an appropriate startup mechanism before `ApplicationReadyEvent`.

## 34. `ApplicationAvailability` and Readiness

Spring Boot provides `ApplicationAvailability` to observe the application's availability states.

Two key states:

- `LivenessState`: whether the application is alive.
- `ReadinessState`: whether the application is ready to accept traffic.

You can observe them:

```java
@Component
public class AvailabilityProbe {

    private final ApplicationAvailability availability;

    public AvailabilityProbe(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public void printState() {
        System.out.println(
                availability.getLivenessState()
        );
        System.out.println(
                availability.getReadinessState()
        );
    }
}
```

Runner completion is a milestone in the startup sequence before the application is marked ready in the normal Boot flow.

Do not manually mark readiness `ACCEPTING_TRAFFIC` before application prerequisites finish. For custom startup workflows, publish availability events at the right time and check how orchestrators consume readiness probes.

## 35. `@PreDestroy`

`@PreDestroy` marks a method called when Spring destroys a managed bean.

```java
import jakarta.annotation.PreDestroy;

@Component
public class FileBuffer {

    @PreDestroy
    public void cleanup() {
        System.out.println("FileBuffer cleanup");
    }
}
```

The method typically takes no arguments and returns `void`.

Use cases:

- Closing internal resources.
- Flushing bounded buffers.
- Stopping a task managed by the bean.
- Releasing file/socket handles owned by the bean.

Do not use `@PreDestroy` to perform lengthy business work or rely on remote services guaranteed to still be available. Shutdown has time limits and may be cut short by process/container termination.

## 36. `DisposableBean.destroy()`

`DisposableBean` defines:

```java
public interface DisposableBean {
    void destroy() throws Exception;
}
```

Example:

```java
@Component
public class ConnectionRegistry implements DisposableBean {

    @Override
    public void destroy() {
        System.out.println("ConnectionRegistry destroyed");
    }
}
```

This interface couples the class directly to Spring APIs. If you prefer less Spring coupling, `@PreDestroy` or a custom destroy method may be better.

When a bean uses both `@PreDestroy` and `DisposableBean`, Spring calls `@PreDestroy` first and then `destroy()` according to the standard destruction callback order.

## 37. Custom Destroy Method with `@Bean`

Example:

```java
public class ClientPool {

    public void initialize() {
        System.out.println("ClientPool initialized");
    }

    public void shutdown() {
        System.out.println("ClientPool shutdown");
    }
}
```

Registration:

```java
@Configuration(proxyBeanMethods = false)
public class PoolConfiguration {

    @Bean(
        initMethod = "initialize",
        destroyMethod = "shutdown"
    )
    ClientPool clientPool() {
        return new ClientPool();
    }
}
```

Spring calls the custom destroy method when the singleton bean is destroyed by the container.

With `@Bean`, Spring has default destroy-method inference for common method names like `close` or `shutdown`. You can use `destroyMethod = ""` to disable inference when needed, such as when an object is borrowed from elsewhere and Spring should not close it.

Declare the destroy method explicitly whenever resource ownership is not obvious.

## 38. Order of Destruction Callbacks

For an ordinary bean, the standard destruction callback order is:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method in the bean definition/`@Bean`.

Example:

```java
@Component
public class DestroyProbe implements DisposableBean {

    @PreDestroy
    void preDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy");
    }

    public void customShutdown() {
        System.out.println("3. custom destroy");
    }
}
```

For `customShutdown()` to execute, the bean definition must declare that method as its destroy method.

If a bean has dependencies, Spring typically destroys dependent beans before the beans they depend on, so dependencies remain available while dependent beans clean up. Do not rely on arbitrary ordering among independent singletons with no dependency relationship.

## 39. Dependencies and `@DependsOn` Affect Destruction Order

Suppose `ReportService` uses `ReportRepository`. When the container manages dependency relationships, Spring ensures the dependent bean is destroyed before the dependency it needs.

You can declare explicit ordering dependencies with `@DependsOn`:

```java
@Component("databaseConnection")
public class DatabaseConnection {

    @PreDestroy
    void close() {
        System.out.println("database connection closed");
    }
}
```

```java
@Component
@DependsOn("databaseConnection")
public class ReportService {

    @PreDestroy
    void cleanup() {
        System.out.println("report service cleanup");
    }
}
```

`ReportService` depends on `databaseConnection`; during destruction, the service cleans up before the connection.

`@DependsOn` also affects initialization order so the dependency initializes before the dependent bean. However, constructor injection already expresses real dependencies better. Only use `@DependsOn` when ordering is needed between beans without direct dependency injection.

## 40. Do Prototype Beans Auto-Invoke Destroy Callbacks?

No. Spring manages creating and configuring prototype beans, but does not track their full lifecycle to auto-invoke destruction callbacks as it does for singleton beans.

Example:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryDocument implements AutoCloseable {

    @Override
    public void close() {
        System.out.println("TemporaryDocument closed");
    }
}
```

When obtaining a prototype bean from the container:

```java
TemporaryDocument document =
        applicationContext.getBean(TemporaryDocument.class);
```

the application must take responsibility for closing that object's resources when finished.

If a prototype bean owns file handles, streams, or other resources, manage them using `try-with-resources`, `AutoCloseable`, a custom factory, or an appropriate lifecycle scope.

Do not assume `@PreDestroy` on a prototype will run automatically when the application context closes.

## 41. Lazy Singletons and Destruction

A singleton annotated with `@Lazy` may not be initialized until a consumer requests it.

```java
@Component
@Lazy
public class ExpensiveCatalog {

    public ExpensiveCatalog() {
        System.out.println("ExpensiveCatalog constructed");
    }

    @PreDestroy
    void cleanup() {
        System.out.println("ExpensiveCatalog destroyed");
    }
}
```

If the bean was never created, there is no instance on which to run initialization or destruction callbacks.

If the lazy bean was created and is managed by the container as a singleton, it participates in destruction when the context closes.

This explains why a bean with `@PreDestroy` might not appear in shutdown logs: the instance may never have been initialized, or the bean belongs to a scope whose destruction the container does not manage automatically.

## 42. Context Close and the JVM Shutdown Hook

Spring can close the application context explicitly:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);

context.close();
```

In a typical Boot application, `SpringApplication` registers a shutdown hook to close the context during normal JVM shutdown. The hook can be disabled via `SpringApplication` configuration if the application manages its own lifecycle, provided an alternative context-closing mechanism exists.

Shutdown hooks do not run in every scenario:

- Process is forcibly killed (`SIGKILL`).
- Machine/container loses power suddenly.
- Severe JVM crash.
- Runtime is halted without a normal shutdown opportunity.

Therefore, destroy callbacks are a best-effort cleanup mechanism during controlled shutdown, not the sole guarantee of data durability.

## 43. Graceful Shutdown in Spring Boot

With Boot-supported web servers, you can enable graceful shutdown:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Graceful shutdown allows the server to stop accepting new requests and drain in-flight requests according to the server's mechanism, within the configured timeout.

`spring.lifecycle.timeout-per-shutdown-phase` sets the wait time per lifecycle phase. It is not a guarantee that total shutdown finishes in a single flat number of seconds; there can be multiple phases and components.

When running in a container/orchestrator, the external termination grace period must be long enough for the application's shutdown process. If the container is killed before Spring finishes, callbacks can be cut off.

## 44. What Should a Shutdown Callback Do?

A good cleanup callback should:

- Stop accepting new work.
- Wait for or reject in-flight work according to a clear policy.
- Flush bounded data.
- Close resources owned by the bean.
- Log concisely and helpfully.
- Complete within a predictable timeout.

Avoid:

- Waiting indefinitely on a remote server.
- Starting a new long-running workflow.
- Relying on another bean that has already been destroyed.
- Throwing exceptions that mask root errors without logging.
- Performing non-idempotent side effects that could corrupt state on repeated shutdowns.

If critical data must be preserved, persist it during normal operation and treat shutdown callbacks as final cleanup, not the only time data is written.

## 45. Tracing the Full Lifecycle with Logs

A helpful logging convention attaches a consistent bean name and stage to each message:

```text
[bean=orderService] constructor
[bean=orderService] dependencies populated
[bean=orderService] before initialization
[bean=orderService] @PostConstruct
[bean=orderService] afterPropertiesSet
[bean=orderService] after initialization / proxy
[application] ContextRefreshedEvent
[application] ApplicationStartedEvent
[application] ApplicationRunner
[application] ApplicationReadyEvent
[application] ContextClosedEvent
[bean=orderService] @PreDestroy
[bean=orderService] destroy
```

In real applications, logs from different beans interleave. Log `beanName`, class name, context ID, and timestamp when helpful.

Do not log entire objects via `toString()` if an object may contain passwords, tokens, or user data. Bean name and class are usually enough to trace lifecycle.

## 46. A Probe for Initialization Callbacks

Example combining callbacks on a single bean:

```java
@Component
public class OrderLifecycleProbe
        implements BeanNameAware, InitializingBean, DisposableBean {

    private String beanName;

    public OrderLifecycleProbe() {
        System.out.println("[probe] constructor");
    }

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
        System.out.println("[probe] BeanNameAware: " + name);
    }

    @PostConstruct
    void postConstruct() {
        System.out.println("[probe] @PostConstruct: " + beanName);
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("[probe] afterPropertiesSet: " + beanName);
    }

    @PreDestroy
    void preDestroy() {
        System.out.println("[probe] @PreDestroy: " + beanName);
    }

    @Override
    public void destroy() {
        System.out.println("[probe] DisposableBean.destroy: " + beanName);
    }
}
```

This bean lets you observe callback order. To also see `BeanPostProcessor` before/after initialization, register a separate `TraceBeanPostProcessor`.

Do not make the probe a dependency of production beans just to force log ordering. Adding dependencies can alter the very lifecycle you are trying to observe.

## 47. Tracing Runners and Events with a Component

Example:

```java
@Component
public class StartupTimeline {

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("[application] started event");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("[application] ready event");
    }

    @EventListener(ContextClosedEvent.class)
    public void closed() {
        System.out.println("[application] context closed");
    }
}
```

Runner:

```java
@Component
@Order(10)
public class StartupTask implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("[application] runner started");
        // Finite startup task.
        System.out.println("[application] runner finished");
    }
}
```

A normal log will show `ApplicationStartedEvent` before the runner and `ApplicationReadyEvent` after runners complete.

If a runner throws an exception, do not expect `ApplicationReadyEvent` to appear along the success path.

## 48. Observing Proxies with `BeanPostProcessor`

You can extend the processor to print the class before and after initialization:

```java
public class ProxyTracePostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) {

        if (beanName.equals("invoiceService")) {
            System.out.println(
                    "before: " + bean.getClass().getName()
            );
        }

        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) {

        if (beanName.equals("invoiceService")) {
            System.out.println(
                    "after: " + bean.getClass().getName()
            );
            System.out.println(
                    "isProxy: " + AopUtils.isAopProxy(bean)
            );
        }

        return bean;
    }
}
```

In a typical AOP setup, you can see the target class in the before stage and the proxy in the after stage.

Not every bean is proxied. A bean is only wrapped when matching infrastructure/advisors exist and the bean is eligible. Not seeing a proxy is not necessarily a bug; check annotations, pointcuts, method visibility, proxy mode, and the dependency graph.

## 49. Testing Callback Order

A simple way to test is recording stages into a test-controlled collection.

Example bean:

```java
@Component
public class OrderedLifecycleProbe implements InitializingBean {

    private final List<String> events;

    public OrderedLifecycleProbe(List<String> events) {
        this.events = events;
        events.add("constructor");
    }

    @PostConstruct
    void init() {
        events.add("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        events.add("afterPropertiesSet");
    }
}
```

In real projects, do not use an arbitrary global `List<String>` bean shared across tests. Create dedicated fixtures/test configurations to avoid state leaks and ensure the list is properly shared between the probe and the test.

A test can initialize the context, retrieve the list, and assert callback ordering. When testing destruction, close the context and then assert the destruction events.

For runner/event ordering, create a small test context or `@SpringBootTest` and record the event sequence in a test-only collector.

## 50. Closing the Context in Tests

Example using `AnnotationConfigApplicationContext` to observe init/destroy without launching a web server:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {

    context.register(LifecycleConfiguration.class);
    context.refresh();

    LifecycleProbe probe =
            context.getBean(LifecycleProbe.class);

    System.out.println("context is running");
}
```

Upon exiting try-with-resources, the context closes and Spring invokes destruction callbacks for managed singleton beans.

This approach works well for testing small bean lifecycles. For startup runners and Boot application events, use `SpringApplication`/`@SpringBootTest` since they belong to Spring Boot's startup flow.

## 51. Differences by Scope

| Scope | Initialization | Destruction |
|---|---|---|
| Singleton | When container creates the bean (eager or lazy) | Container invokes callbacks when context closes |
| Prototype | Each time container creates an instance | Client/application manages cleanup itself |
| Request/session | Per corresponding web scope | Per request/session lifecycle and scope infrastructure |
| Custom scope | Per custom scope implementation | Per custom scope contract |

Do not apply a single destruction rule to every scope. When a bean owns resources, determine who the owner is and who is responsible for closing them.

If a prototype bean is injected directly into a singleton, the singleton only receives one instance at injection time under the standard configuration; to get a fresh prototype each time, use `ObjectProvider`, a provider, or an appropriate scoped proxy.

## 52. Common Pitfalls When Reading Lifecycle Logs

| Symptom | Possible cause | Investigation |
|---|---|---|
| `@Autowired` field is null in constructor | Field injection occurs after constructor | Use constructor injection or check after population |
| `@PostConstruct` does not run | Bean not created, wrong annotation namespace, or not Spring-managed | Check registration/scope/dependencies |
| Init method is not called | Wrong method name or `initMethod` not declared | Check bean definition |
| `@Transactional` does not work in init | Target not yet exposed via final proxy or self-invocation | Move work to an appropriate phase |
| No proxy observed | No matching advisor or bean is ineligible for proxying | Check AOP configuration and pointcuts |
| Self-invocation skips advice | Call goes through `this`, not the proxy | Extract bean or call through proxy |
| Runner does not run | Context startup failed before runners or runner bean not registered | Read startup exception and bean definitions |
| `ApplicationReadyEvent` never appears | Runner failed or startup never finished | Check runner logs/exceptions |
| Runner prevents app from becoming ready | Long or blocking work | Move background work to a lifecycle-managed component |
| `@PreDestroy` does not appear | Bean never created, scope not destroyed by container, or forced shutdown | Check scope and how context closed |
| Prototype is not destroyed | Prototype destruction is caller-managed | Use `close()`/resource management |
| Shutdown hangs | Callback waits forever or stop callback not invoked | Set timeouts and complete callback |
| Init callback runs twice | Bean/context created multiple times or multiple contexts | Log context ID and bean identity |
| Log order changes | Dependency graph/lazy init/order differs | Identify actual dependencies and required order |
| BeanPostProcessor misses some beans | Processor registered too late or dependency initialized early | Check BPP registration and early initialization |

## 53. Procedure for Investigating Confusing Logs

When startup logs do not appear in the order you expected:

1. Record the bean name and context ID of each line.
2. Classify each log line as constructor, population, Aware, BPP, init, proxy, runner, event, or destroy.
3. Inspect the bean's dependency graph.
4. Check whether the bean is lazy.
5. Check related `BeanPostProcessor`s and AOP advisors.
6. Identify which application context each log came from.
7. Check `@Order`/`Ordered` when comparing runners or lifecycle phases.
8. Check whether an exception halted startup partway through.
9. Check how the context is closed and the bean's scope.
10. Rely only on ordering guarantees provided by Spring; do not assume ordering among independent beans.

Good logs need clear stage and identity. A bare timestamp is insufficient when multiple beans initialize concurrently or logs originate from multiple contexts.

## 54. Practice Exercises

### Exercise A — Constructors and Dependency Injection

Create `OrderService` injecting `OrderRepository` via constructor. Log in the constructor and in `@PostConstruct`. Compare with field injection to observe when fields are populated.

### Exercise B — Init Callback Order

Create a bean using `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and a custom init method. Register the custom method via `@Bean(initMethod=...)`. Observe the callback order.

### Exercise C — `BeanPostProcessor`

Write `TraceBeanPostProcessor` and register it using a static `@Bean` method. Print bean name/class before and after initialization. Try filtering by package to avoid excessive logs.

### Exercise D — AOP Proxy

Create a service with `@Transactional` or a simple aspect. Use `AopUtils.isAopProxy()` to inspect the injected bean. Compare the target type and proxy type.

### Exercise E — Self-Invocation

Create two methods in the same service, one with `@Transactional` and the other calling it internally. Observe that advice does not run as expected. Extract the method into another bean and compare.

### Exercise F — `SmartInitializingSingleton`

Create a bean implementing `SmartInitializingSingleton`. Log `afterSingletonsInstantiated()` and compare its timing with `ContextRefreshedEvent` and `ApplicationRunner`.

### Exercise G — Runner Ordering

Create two `ApplicationRunner`s and one `CommandLineRunner` with different `@Order` values. Run the application with arguments and record the order.

### Exercise H — Runner Failure

Make one runner throw an exception. Observe startup logs and determine whether `ApplicationReadyEvent` appears. Then handle the failure per a fail-fast or degraded-startup policy.

### Exercise I — `ApplicationReadyEvent`

Create listeners for `ApplicationStartedEvent` and `ApplicationReadyEvent`. Add a runner that logs start/finish to confirm ordering.

### Exercise J — Destroy Callbacks

Create a bean using `@PreDestroy`, `DisposableBean`, and a custom destroy method. Close the context explicitly and observe the order.

### Exercise K — Prototype Cleanup

Create a prototype bean owning a simulated resource. Fetch multiple instances from the container and close them via `AutoCloseable` or a dedicated management mechanism. Verify the context does not auto-manage destruction for prototype instances like singletons.

### Exercise L — `SmartLifecycle`

Create two lifecycle components with different phases. Log start/stop and confirm reverse ordering during shutdown. Try asynchronous `stop(Runnable)` and ensure the callback runs exactly once.

### Exercise M — Graceful Shutdown

Enable `server.shutdown=graceful`, configure an appropriate timeout, and send an in-flight request when the application receives a shutdown signal. Observe the server stop accepting new requests and wait for the active request within the configured limit.

### Exercise N — Lifecycle Timeline

Combine a probe bean, BPP, AOP service, `SmartInitializingSingleton`, runner, application event listeners, and destruction callbacks. Sketch the timeline from startup to shutdown based on actual logs.

## 55. Key Takeaways

1. Constructors create the instance; constructor dependencies must be resolved before calling the constructor.
2. Field/setter injection happens after instance creation; do not read field-injected dependencies in constructors.
3. Aware callbacks provide container info prior to initialization callbacks.
4. `BeanPostProcessor` has two main phases: before and after initialization.
5. Common init order is `@PostConstruct`, `afterPropertiesSet()`, custom init method.
6. The AOP auto-proxy creator typically wraps targets during post-processing; consumers receive proxies when beans require advice.
7. Having a proxied bean does not mean self-invocation passes through the proxy.
8. `SmartInitializingSingleton` runs after regular singleton beans have been pre-instantiated.
9. `SmartLifecycle` manages start/stop by phase in the application context.
10. `ContextRefreshedEvent` does not mean a Spring Boot application has finished its runners.
11. `ApplicationRunner` and `CommandLineRunner` run after context refresh, before `ApplicationReadyEvent`.
12. `@Order`/`Ordered` determines runner order; do not rely on component scanning order.
13. A failing runner can fail startup and prevent the application from reaching the ready state.
14. Do not use runners for infinite loops or unmanaged background tasks.
15. `@PreDestroy`, `DisposableBean.destroy()`, and custom destroy methods run in standard destruction order.
16. Singleton bean destruction is managed by the container; prototype cleanup is the caller's responsibility.
17. Un-instantiated lazy beans have no instance on which to invoke init/destroy callbacks.
18. `SmartLifecycle` stop can be asynchronous; the callback must complete within a reasonable timeout.
19. Graceful shutdown requires aligning Spring Boot timeouts with container/orchestrator termination grace periods.
20. Shutdown hooks do not run if the process is forcibly killed or the machine/JVM crashes abruptly.
21. Cleanup callbacks should be short, bounded, idempotent, and only close resources owned by the bean.
22. Logs need bean name, stage, and context ID to distinguish multiple beans and contexts.
23. When analyzing order, rely only on dependency/order/phase guarantees from the framework; never assume ordering among independent beans.

**Core mental model:** constructors and init callbacks tell you **how a bean is created and prepared**; `BeanPostProcessor` and AOP tell you **which object is exposed to consumers**; runners and application events tell you **when the application completes startup**; destroy callbacks and `SmartLifecycle` tell you **how the application stops and releases resources**. Classifying logs across these four layers lets you trace a Spring Boot lifecycle from bean creation to shutdown without mistaking a single callback for whole-application readiness.
