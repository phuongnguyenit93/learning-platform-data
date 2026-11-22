# Phase Ordering and Dependency Relationships Between Beans

In Spring Boot, an application is built from many beans: services, repositories, DataSources, HTTP clients, schedulers, message listeners, and other infrastructure components. The Spring IoC container is responsible for instantiating beans, injecting dependencies, invoking initialization callbacks, applying BeanPostProcessors, and managing the lifecycle of registered components.

To understand execution order, you must distinguish three concepts:

- **Refresh phase:** the stages Spring executes when ApplicationContext is initialized or refreshed.
- **Bean dependency:** relationships between beans that determine which dependent bean must be created before a bean using it.
- **Lifecycle phase:** the start/stop order of beans implementing Lifecycle or SmartLifecycle.

These concepts are related yet do not replace one another. In an application using CRaC, there is also a fourth lifecycle: callbacks before checkpoint and after restore. Understanding each layer clearly prevents starting services too early, closing resources in the wrong order, or assuming beans will be re-initialized after restore.

## 1. What Is ApplicationContext Refresh?

ApplicationContext is Spring's central container. During refresh, Spring prepares the BeanFactory, registers processors, instantiates required singletons, starts lifecycle beans, and publishes events to the application.

In a typical Spring Boot application, SpringApplication creates an ApplicationContext appropriate to the application type and calls refresh. The internal steps follow a sequence defined by AbstractApplicationContext.

Simplified diagram:

~~~text
SpringApplication
       |
       v
Create ApplicationContext
       |
       v
prepareRefresh()
       |
       v
obtainFreshBeanFactory()
       |
       v
prepareBeanFactory()
       |
       v
postProcessBeanFactory()
       |
       v
invokeBeanFactoryPostProcessors()
       |
       v
registerBeanPostProcessors()
       |
       v
initMessageSource()
       |
       v
initApplicationEventMulticaster()
       |
       v
onRefresh()
       |
       v
registerListeners()
       |
       v
finishBeanFactoryInitialization()
       |
       v
finishRefresh()
       |
       v
ApplicationContext ready
       |
       v
Spring Boot invokes ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
~~~

This is a high-level diagram. Certain steps can be extended by ApplicationContext subclasses; for example, a web application context creates an embedded web server inside the onRefresh() hook.

## 2. Main Phases During Refresh

### prepareRefresh()

Spring prepares the context state before creating beans:

- Records the refresh start timestamp.
- Sets the context active flag.
- Initializes or verifies required property sources.
- Validates that required properties are declared.
- Prepares the internal event management infrastructure.

At this stage, most application beans have not been initialized yet. This is the environment-preparation step for the refresh process.

### obtainFreshBeanFactory()

Spring obtains or creates a new BeanFactory for the ApplicationContext. The BeanFactory contains BeanDefinitions describing how to create beans: class, constructor, factory method, scope, dependencies, lazy flag, and other metadata.

A BeanDefinition is not a bean instance. Registering a bean definition does not mean that bean's constructor has been called.

For example, a bean can be declared via component scanning:

~~~java
@Component
public class PaymentService {
}
~~~

Or via Java configuration:

~~~java
@Configuration
public class PaymentConfiguration {
    @Bean
    PaymentService paymentService() {
        return new PaymentService();
    }
}
~~~

In this step, Spring builds the foundation describing beans and the relationships between them.

### prepareBeanFactory()

Spring configures the BeanFactory with foundational components such as class loader, expression resolver, property editors, and special interfaces that beans may implement.

Certain beans may receive callbacks via Aware interfaces, such as BeanNameAware or BeanFactoryAware. Those callbacks occur when the bean itself is instantiated, not during the prepareBeanFactory() step.

### postProcessBeanFactory()

This is a hook for ApplicationContext subclasses to customize the BeanFactory after it has been prepared. Web contexts or specialized contexts can add their own configuration.

Regular applications rarely need to override this step. Most container extensions are performed via BeanFactoryPostProcessor or BeanDefinitionRegistryPostProcessor.

### invokeBeanFactoryPostProcessors()

Spring invokes registered BeanFactoryPostProcessors. They can alter BeanDefinition metadata before application beans are instantiated.

There are two important kinds:

- BeanDefinitionRegistryPostProcessor: can register additional BeanDefinitions and runs during registry processing.
- BeanFactoryPostProcessor: can modify metadata inside BeanFactory after the registry has been processed.

These processors are commonly used by configuration, property sources, component scanning, and framework integrations.

For example, ConfigurationClassPostProcessor processes @Configuration classes, @ComponentScan, @Import, and @Bean methods to register bean definitions.

Do not use a BeanFactoryPostProcessor to fetch a regular service by calling getBean() without a clear reason. Instantiating beans too early can alter initialization order and cause beans to be created before required BeanPostProcessors are registered.

### registerBeanPostProcessors()

Spring registers BeanPostProcessors. They intercept bean instances before and after initialization callbacks.

Features such as annotation injection, @PostConstruct handling, AOP proxies, and certain framework mechanisms are implemented via BeanPostProcessors.

Therefore, BeanPostProcessors must be registered before most application beans are created. A bean initialized too early may miss passing through all processors, or may trigger warnings about not being eligible for processing by all BeanPostProcessors.

### initMessageSource() and initApplicationEventMulticaster()

Spring initializes internal components for:

- MessageSource: message resolution and internationalization support.
- ApplicationEventMulticaster: dispatching ApplicationEvents to listeners.

Listeners are registered or discovered in subsequent steps. The event system is a notification mechanism within ApplicationContext; it does not automatically guarantee all asynchronous work has completed before another phase.

### onRefresh()

ApplicationContext invokes the onRefresh() hook for subclasses to perform specialized work.

For example, ServletWebServerApplicationContext creates the embedded web server during refresh. Creating the server and having the server start accepting traffic must be distinguished; starting is typically coordinated by the web server's lifecycle bean during the finish-refresh stage.

### registerListeners()

Spring registers declared ApplicationListeners. Some listeners may receive events during refresh and throughout the context's lifetime.

Event listeners are not the right tool to express every initialization dependency. If service B strictly requires service A to be ready, declare the dependency or use an explicit lifecycle coordinator instead of relying on an event happening to fire first.

### finishBeanFactoryInitialization()

Spring finishes configuring the BeanFactory and instantiates remaining non-lazy singletons.

Notable steps include:

- Finalizing required type conversion components.
- Freezing BeanFactory configuration where appropriate.
- Instantiating remaining non-lazy singletons.

This is when most application services, repositories, and singleton components are created. Lazy beans may remain uninstantiated until first access.

### finishRefresh()

Spring completes refresh:

- Initializes the LifecycleProcessor if not already present.
- Calls LifecycleProcessor.onRefresh() to start eligible lifecycle beans, especially SmartLifecycles with autoStartup.
- Publishes ContextRefreshedEvent.

For web applications, lifecycle components such as the web server can begin operating during this phase.

After context refresh completes, Spring Boot continues the application-level startup flow. ApplicationRunners and CommandLineRunners are invoked before Spring Boot publishes ApplicationReadyEvent and marks the application ready under Boot's lifecycle.

## 3. Initialization Order Inside a Bean

When Spring needs to instantiate a bean, the general process typically includes:

~~~text
Select BeanDefinition
       |
       v
Create instance via constructor / factory method
       |
       v
Inject dependencies and populate properties
       |
       v
Invoke matching Aware callbacks
       |
       v
BeanPostProcessor.postProcessBeforeInitialization()
       |
       v
@PostConstruct
       |
       v
InitializingBean.afterPropertiesSet()
       |
       v
Custom init-method
       |
       v
BeanPostProcessor.postProcessAfterInitialization()
       |
       v
Bean ready for use
~~~

Detailed ordering can be extended by the framework and processors. The diagram above depicts the common initialization flow of a singleton bean.

### Constructor or Factory Method

Spring creates the object via the selected constructor or factory method. With constructor injection, required dependencies must be resolved before the dependent bean's constructor can complete.

~~~java
@Service
public class OrderService {
    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

In the example, Spring must have PaymentService before creating OrderService.

### Property Population and Dependency Injection

After the instance is created, Spring injects dependencies via fields, setters, or other injection mechanisms.

~~~java
@Service
public class ReportService {
    @Autowired
    private ReportRepository repository;
}
~~~

Field injection happens after the constructor. Therefore, ReportService's constructor cannot use the repository injected via field.

Constructor injection is usually easier to test because dependencies are explicit and objects are never constructed missing mandatory dependencies.

### Aware Callbacks

If a bean implements Aware interfaces, Spring can supply container information before initialization callbacks, for example:

- BeanNameAware: bean name.
- BeanClassLoaderAware: class loader.
- BeanFactoryAware: BeanFactory.
- ApplicationContextAware: ApplicationContext.

Do not use ApplicationContextAware as a service locator for all dependencies. Constructor injection usually makes dependency relationships clearer.

### Initialization Callbacks

Spring supports multiple ways to declare initialization:

~~~java
@Component
public class CacheLoader implements InitializingBean {

    @PostConstruct
    public void initializeCache() {
        // Prepare cache.
    }

    @Override
    public void afterPropertiesSet() {
        // Spring initialization callback.
    }

    public void warmUp() {
        // Custom init method if configured.
    }
}
~~~

With common mechanisms, initialization order is:

1. Method annotated with @PostConstruct.
2. InitializingBean.afterPropertiesSet().
3. Custom init-method declared in the bean definition or @Bean(initMethod = "...").

Pick one primary mechanism for ease of tracking. Do not split one initialization sequence across multiple callbacks with implicit ordering dependencies when it can be grouped into one clear method.

Java configuration example:

~~~java
@Configuration
public class CacheConfiguration {

    @Bean(initMethod = "warmUp", destroyMethod = "close")
    CacheClient cacheClient() {
        return new CacheClient();
    }
}
~~~

### BeanPostProcessor After Initialization

A BeanPostProcessor can return a different object instead of the original instance. An AOP auto-proxy creator is one example: a bean can be wrapped in a proxy to apply transactions, security, caching, or advice.

Consequently, the object received by another bean may be a proxy rather than the direct target object.

This matters when:

- Calling a @Transactional method from inside the same object (self-invocation usually bypasses the proxy).
- Holding a reference to the target before the proxy is created.
- Calling methods on the bean inside initialization callbacks.
- Inspecting the bean's actual class via getClass().

Do not rely on a bean having executed its constructor to conclude all AOP or proxy behavior is already ready.

## 4. Dependency Relationships Determine Bean Creation Order

Spring creates beans on demand. When bean A needs bean B, the container must resolve B before finishing creating A.

Example:

~~~java
@Repository
public class OrderRepository {
}

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}

@RestController
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }
}
~~~

Dependency relationship:

~~~text
OrderController
      |
      v
OrderService
      |
      v
OrderRepository
~~~

When Spring creates OrderController, it needs OrderService. When creating OrderService, it needs OrderRepository. Thus the repository is created before the service, and the service before the controller.

This is a true dependency relationship. It is not based on alphabetical order, source file order, or the order components are discovered in packages.

### Constructor Injection

Constructor injection expresses mandatory dependencies:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxService taxService;

    public InvoiceService(
            InvoiceRepository repository,
            TaxService taxService) {
        this.repository = repository;
        this.taxService = taxService;
    }
}
~~~

Spring must resolve both InvoiceRepository and TaxService before creating InvoiceService.

Advantages:

- Dependencies are immutable after object creation.
- Easy to write unit tests.
- Avoids beans existing in a state lacking injected dependencies.
- Dependency relationships are visible right in the constructor.

### Setter and Field Injection

Setter injection suits optional dependencies or dependencies that need to change across the lifecycle:

~~~java
@Component
public class NotificationService {
    private TemplateProvider templateProvider;

    @Autowired
    public void setTemplateProvider(
            TemplateProvider templateProvider) {
        this.templateProvider = templateProvider;
    }
}
~~~

Field injection is concise yet hides dependencies inside the class and makes creating standalone instances in unit tests harder.

Both setter and field injection are processed after the constructor has created the object. If the constructor needs to use that dependency, fields or setters are not yet ready.

### @DependsOn

When two beans have an initialization relationship not expressed via dependency injection, @DependsOn can be used:

~~~java
@Component
public class DatabaseBootstrap {
    @PostConstruct
    public void prepareSchemaMetadata() {
        // Prepare required metadata.
    }
}

@Component
@DependsOn("databaseBootstrap")
public class BackgroundIndexer {
    @PostConstruct
    public void startIndexing() {
        // Runs only after databaseBootstrap is initialized.
    }
}
~~~

@DependsOn requires the specified bean to be initialized before the current bean. For singletons, the dependent bean is destroyed in reverse order upon container shutdown.

However, @DependsOn only expresses initialization ordering. It does not inject an object into the bean and does not replace constructor injection. If BackgroundIndexer actually needs to call DatabaseBootstrap, declare the dependency directly in the constructor.

Do not use @DependsOn to fix a circular dependency architecture or to guarantee an external service is always available.

## 5. Distinguishing @DependsOn, @Order, @Primary, and @Lazy

These annotations solve different problems.

| Mechanism | Purpose | Determines bean creation order? |
|---|---|---|
| @DependsOn | Requires another bean to be initialized first | Yes, for the declared relationship |
| @Order | Sorts elements in certain collections or ordered lists | Not a general rule for bean initialization |
| @Primary | Selects the preferred bean when multiple candidates of the same type exist | No |
| @Qualifier | Selects a candidate by a specific qualifier | No |
| @Lazy | Defers initialization until the bean is requested | May make creation time later, yet is not a dependency ordering mechanism |
| @DependsOn + dependency injection | Combines creation order with usage relationship | Yes |

### @Order Is Not Initialization Order

Example:

~~~java
@Component
@Order(1)
public class FirstHandler implements Handler {
}

@Component
@Order(2)
public class SecondHandler implements Handler {
}
~~~

If injecting List<Handler>, Spring can sort the elements in the corresponding order when applying Ordered/@Order rules.

However, @Order(1) does not guarantee FirstHandler is initialized before every other bean in ApplicationContext. Do not use @Order as a substitute for @DependsOn.

### @Primary and @Qualifier

When multiple implementations of the same type exist:

~~~java
public interface PaymentGateway {
    void pay();
}

@Component
@Primary
public class CardGateway implements PaymentGateway {
    public void pay() {
    }
}

@Component
public class BankGateway implements PaymentGateway {
    public void pay() {
    }
}
~~~

@Primary makes CardGateway the default candidate when injection needs a PaymentGateway and no specific qualifier is present.

If you want to choose explicitly:

~~~java
@Service
public class BankTransferService {
    private final PaymentGateway gateway;

    public BankTransferService(
            @Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

These annotations solve bean selection, not lifecycle phases.

### @Lazy

A lazy bean is not necessarily instantiated during finishBeanFactoryInitialization(). It may only be created when another bean or application code requests it.

~~~java
@Component
@Lazy
public class ExpensiveReportEngine {
}
~~~

If a non-lazy bean directly needs a lazy bean, that dependency can still cause the lazy bean to be created when the non-lazy bean is initialized. @Lazy on an injection point can use a proxy to defer obtaining the target.

Do not rely on @Lazy to bypass a bad dependency or defer a required resource without a readiness check.

## 6. Circular Dependencies and Early-Created Beans

A circular dependency occurs when A needs B and B in turn needs A:

~~~text
ServiceA ----> ServiceB
   ^              |
   |              |
   +--------------+
~~~

With constructor injection, such a cycle cannot be resolved by creating one complete bean before the other; Spring typically reports BeanCurrentlyInCreationException or a corresponding dependency cycle error.

~~~java
@Service
public class ServiceA {
    public ServiceA(ServiceB serviceB) {
    }
}

@Service
public class ServiceB {
    public ServiceB(ServiceA serviceA) {
    }
}
~~~

Some circular dependencies between singletons using setter/field injection can be resolved via early singleton references in configurations where Spring permits it. However, this complicates lifecycles and proxies. Spring Boot disallows circular references by default in normal application configurations since Boot 2.6, unless explicitly enabled.

A better approach is extracting shared responsibility into a third service or using events/port abstractions if the relationship is genuinely bidirectional communication.

### Why Can Early-Created Beans Lack Proxies?

Spring can provide an early reference to resolve certain circular dependencies. If a bean is created before BeanPostProcessors or auto-proxy creators finish, it may be injected as a raw target or early proxy not equivalent to the final proxy.

This can cause calls to bypass expected transactions, security, or advice. That is another reason to avoid circular dependencies and avoid calling getBean() early inside BeanFactoryPostProcessors.

## 7. BeanFactoryPostProcessor and BeanPostProcessor Must Be Declared Carefully

These two processor types are often confused:

| Type | Timing | Effect |
|---|---|---|
| BeanFactoryPostProcessor | After BeanDefinitions are loaded, before regular beans are created | Modifies BeanDefinition metadata |
| BeanPostProcessor | When a bean instance is created | Intercepts before/after initialization, can create proxies |

Example declaring a BeanFactoryPostProcessor with @Bean:

~~~java
@Configuration
public class FeatureConfiguration {

    @Bean
    static PropertyOverrideConfigurer propertyOverrides() {
        return new PropertyOverrideConfigurer();
    }
}
~~~

For processors that may be created very early, a static @Bean method lets Spring create the processor without prematurely instantiating the @Configuration class containing it.

For BeanPostProcessor, declare a concrete return type instead of just Object whenever possible. Spring needs to identify the processor to register it at the right time.

Do not inject many application services into a BeanPostProcessor unnecessarily. Creating the processor can trigger early instantiation of part of the application graph and prevent those beans from passing through all other processors.

## 8. Bean Lifecycle After Initialization

A bean finishing instantiation does not mean it has already started accepting work. Spring has a separate lifecycle for components that must start and stop.

Two common interfaces:

- Lifecycle: start(), stop(), isRunning().
- SmartLifecycle: extends Lifecycle, adding autoStartup(), getPhase(), and stop(Runnable callback).

SmartLifecycle is useful for components such as message listeners, schedulers, background workers, or server connectors.

~~~java
@Component
public class ImportWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Start accepting work.
    }

    @Override
    public void stop() {
        running = false;
        // Stop accepting work and stop worker.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Simplified example. In a real application, stop() must perform draining or ask the worker to stop in a controlled manner; do not merely toggle a boolean if tasks are still running.

## 9. SmartLifecycle Phases and Start/Stop Ordering

SmartLifecycle allows assigning a phase to control the start and stop order of lifecycle beans.

General rules:

- Lower phases start first.
- Higher phases start later.
- When stopping, the order reverses: higher phases stop first.
- Actual dependency relationships between beans still take precedence over phase ordering.

Example:

| Bean | Phase | Role |
|---|---:|---|
| DatabaseConnector | 0 | Prepares connection dependency |
| MessageListener | 50 | Begins receiving messages |
| ImportWorker | 100 | Processes background work |
| MetricsReporter | 200 | Reports status |

Expected start order:

~~~text
DatabaseConnector (0)
        |
        v
MessageListener (50)
        |
        v
ImportWorker (100)
        |
        v
MetricsReporter (200)
~~~

Expected stop order:

~~~text
MetricsReporter (200)
        |
        v
ImportWorker (100)
        |
        v
MessageListener (50)
        |
        v
DatabaseConnector (0)
~~~

The diagram only illustrates phases. If MessageListener depends on DatabaseConnector, the dependency graph must also reflect that relationship. Do not rely on phase numbers to hide missing dependencies.

### Lifecycle Phase Differs from Refresh Phase

The refresh phase is the sequence in which the container creates and prepares ApplicationContext. SmartLifecycle phase is the start/stop order of lifecycle components after the container has created beans.

A bean having getPhase() equal to 100 does not mean it is instantiated after every bean with phase 50. Phases do not govern constructors or dependency injection.

### SmartLifecycle and autoStartup

SmartLifecycle can declare isAutoStartup() to tell Spring whether to start the component automatically during context refresh.

If autoStartup() returns false, the component can be created yet not start running automatically. The application can start it after dependencies or business conditions are ready.

Do not use start() to perform one-time heavy object initialization if that belongs in @PostConstruct. Separate:
- Initialization: configure the object and check internal invariants.
- Lifecycle start: begin accepting work or open active resources.
- Lifecycle stop: stop accepting work and release active state.

## 10. Application Events and ApplicationRunner

Spring Boot publishes several events during startup. Some common events:

| Event | High-level timing |
|---|---|
| ApplicationStartingEvent | SpringApplication begins |
| ApplicationEnvironmentPreparedEvent | Environment is prepared |
| ApplicationContextInitializedEvent | Context has been initialized yet not refreshed |
| ApplicationPreparedEvent | Bean definitions are loaded, before refresh |
| ContextRefreshedEvent | ApplicationContext completes refresh |
| ApplicationStartedEvent | Context refresh finished, before runners |
| ApplicationReadyEvent | Runners have finished, application is about to accept traffic |
| ApplicationFailedEvent | Startup failed |

Exact names and sequences can depend on Spring Boot version and context type. When needing phase-dependent logic, consult the lifecycle contract of the version in use.

### ApplicationRunner and CommandLineRunner

Runners are invoked after ApplicationContext refresh finishes:

~~~java
@Component
public class InitialDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Load initial data or run startup task.
    }
}
~~~

If there are multiple runners, Ordered or @Order can sort the order in which runners are called. This is runner execution order, not bean creation order.

Do not use ApplicationRunner to create a dependency that a SmartLifecycle bean already starts using during finishRefresh(). If a dependency must be ready before listeners start, put that logic in dependency initialization or appropriate lifecycle coordination.

## 11. Bean Destruction Order on Context Shutdown

When ApplicationContext closes, Spring stops lifecycle beans and destroys singletons in dependency order.

Initialization callbacks have corresponding callbacks on destruction:

- @PreDestroy.
- DisposableBean.destroy().
- Custom destroy-method declared in bean definition or @Bean.

The common order of destruction callbacks on a bean is @PreDestroy, DisposableBean.destroy(), then custom destroy-method.

For beans with dependencies, the dependent bean is destroyed before the dependency it uses. For example:

~~~text
Creation:
DataSource -> Repository -> Service -> Listener

Destruction:
Listener -> Service -> Repository -> DataSource
~~~

The diagram shows foundational dependencies are created before consumers and are usually closed after consumers.

With SmartLifecycle, Spring stops components in reverse phase order compared to start order. Components can use stop(Runnable callback) to signal when asynchronous stopping has completed.

Do not close DataSource while listeners or workers are still using it. Stop consumers first, wait for in-flight work to finish, and only then close dependencies.

## 12. Bean Relationships in a Spring Boot Application Using CRaC

CRaC adds a lifecycle distinct from Spring bean lifecycle.

In a normal run:

~~~text
SpringApplication
       |
       v
ApplicationContext refresh
       |
       v
Bean initialization
       |
       v
SmartLifecycle start
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
       |
       v
Application serves requests
~~~

When a checkpoint is requested:

~~~text
Application serving
       |
       v
Stop accepting new requests / triggers
       |
       v
Drain workers and transactions
       |
       v
Stop lifecycle components
       |
       v
Resource.beforeCheckpoint()
       |
       v
Checkpoint image
~~~

After restore:

~~~text
Restore heap and process
       |
       v
Resource.afterRestore()
       |
       v
Recreate connections / clients / file handles
       |
       v
Verify dependencies
       |
       v
Start workers and listeners
       |
       v
Open request gate
~~~

Key point: restoring from a checkpoint image is not synonymous with Spring creating a new ApplicationContext and re-running all constructors, @PostConstruct methods, or the entire refresh phase. Bean state already in the heap is restored. External resources that need recreating must be handled via CRaC mechanisms or corresponding integrations.

### Bean Dependencies Do Not Automatically Handle Resources After Restore

For example, OrderService has a constructor dependency on PaymentClient:

~~~java
@Service
public class OrderService {
    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

Constructor injection guarantees the PaymentClient bean exists before OrderService is created. Yet it does not guarantee sockets inside PaymentClient remain valid after restore.

PaymentClient needs its own lifecycle to close connections before checkpoint and recreate them after restore. OrderService still holds the reference to the PaymentClient bean; therefore the PaymentClient bean should hold a replaceable delegate or update internal state upon reconnect.

### Do Not Treat @DependsOn as CRaC Callback Order

@DependsOn controls singleton bean initialization and destruction order. It is not a general contract for controlling the callback order of all Resources in CRaC.

Similarly, SmartLifecycle phases control starting/stopping lifecycle beans; they do not automatically control the order of all Resource.beforeCheckpoint() and Resource.afterRestore() calls.

If resource order matters, you should:
- Use a single coordinator with an explicit sequence.
- Or use the CRaC integration of your exact Spring Boot version and follow the callback order defined by that integration.
- Declare explicit dependencies between resources.
- Open traffic only after all mandatory dependencies are ready.

Do not rely on accidental component scan order or bean registration order.

## 13. Example Coordinating Spring Lifecycle and CRaC

Suppose an application has:

- DatabasePool: creates and closes the JDBC pool.
- ImportWorker: receives and processes background work.
- RequestGate: stops accepting new work.
- CheckpointCoordinator: coordinates the checkpoint.

An abstraction can be:

~~~java
public interface RequestGate {
    void stopAccepting();
    void awaitInFlight() throws Exception;
    void resumeAccepting();
}

public interface DatabaseResource {
    void closeForCheckpoint() throws Exception;
    void reopenAfterRestore() throws Exception;
}
~~~

Worker implements SmartLifecycle so Spring manages start/stop:

~~~java
import org.springframework.context.SmartLifecycle;

public final class ImportWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Start consumer or worker loop.
    }

    @Override
    public void stop() {
        running = false;
        // Request worker to stop and drain work.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stopAndAwaitCompletion();
        } finally {
            callback.run();
        }
    }

    private void stopAndAwaitCompletion() {
        // Wait for running tasks to complete with timeout.
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Coordinator implements CRaC Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.context.LifecycleProcessor;

public final class SpringCheckpointCoordinator implements Resource {
    private final RequestGate requestGate;
    private final LifecycleProcessor lifecycleProcessor;
    private final DatabaseResource database;

    public SpringCheckpointCoordinator(
            RequestGate requestGate,
            LifecycleProcessor lifecycleProcessor,
            DatabaseResource database) {
        this.requestGate = requestGate;
        this.lifecycleProcessor = lifecycleProcessor;
        this.database = database;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        requestGate.stopAccepting();
        requestGate.awaitInFlight();

        lifecycleProcessor.stop();
        database.closeForCheckpoint();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        database.reopenAfterRestore();
        lifecycleProcessor.start();

        requestGate.resumeAccepting();
    }
}
~~~

This is an illustrative skeleton, not a complete integration for every Spring Boot version. Error handling, timeouts, readiness, and rollback if checkpoint is aborted must be added. DatabaseResource and RequestGate are abstractions implemented by the application.

In practice, avoid letting lifecycleProcessor.stop() stop the very component the coordinator needs to complete its callback. If the context has many lifecycle beans that should not stop during checkpointing, use a separate lifecycle coordinator or manage components needing stop by groups.

Do not call resumeAccepting() if the database is not yet connected, workers have not started, or any mandatory dependency is not ready.

### Handling Aborted Checkpoints

If the application calls Core.checkpointRestore() directly and the checkpoint fails, the original process continues. afterRestore() does not run for this branch.

The coordinator needs to catch CheckpointException on the API-calling thread and recover closed resources, then restart lifecycle components and open the gate if all recovery steps succeed.

If checkpointing is requested externally via jcmd, business threads have no try/catch block around that call. A separate operational procedure or in-application management mechanism is needed to coordinate rollback.

## 14. Common Mistakes When Ordering Beans

### Using @Order to Force a Bean to Initialize First

@Order primarily sorts certain collections or lists processed by the framework. It is not a general rule for controlling constructors or singleton initialization order.

How to handle: declare dependencies via constructor or @DependsOn when an initialization relationship not expressed by injection is genuinely needed.

### Using @DependsOn Instead of Dependency Injection

Bean A is created after Bean B, yet A has no reference to B. That does not help A invoke B or know B is business-ready.

How to handle: use constructor injection if A needs B. Use @DependsOn only when initialization ordering is needed without injecting the object.

### Starting Workers Inside @PostConstruct

@PostConstruct runs during bean initialization. At that moment, the full ApplicationContext may not have finished refreshing and other lifecycle beans have not started.

If a worker starts receiving messages right inside @PostConstruct, it may run before listeners, database pools, or readiness gates are fully configured.

How to handle: use SmartLifecycle or a startup coordinator mechanism to start workers after dependencies are ready.

### Using Constructors to Open Long-Lived Connections

Constructors should establish object state and receive dependencies. Opening sockets, running background threads, or registering long-lived schedules inside a constructor gives the object side effects before proxies and lifecycle processors finish.

How to handle: separate object creation from starting resources; use appropriate lifecycle callbacks and CRaC Resources for checkpoint/restore.

### Assuming @PostConstruct Re-Runs After Restore

Restore recovers the process heap. It does not by default recreate every bean and re-invoke constructors or @PostConstruct.

How to handle: register Resources or use appropriate CRaC integration to reopen external resources.

### Relying on Component Scan Order

Class discovery order is not an initialization contract. If bean A depends on bean B, declare the dependency explicitly.

### Using @DependsOn to Control All CRaC Callbacks

@DependsOn and SmartLifecycle phases do not replace Resource callback order. Use a coordinator or supported integration to control checkpoint/restore.

### Opening Traffic Before Dependencies Are Ready

The context may finish refreshing while databases, brokers, or remote services are not yet ready. ContextRefreshedEvent is not proof that every out-of-process service is healthy.

How to handle: use readiness state, health checks, and startup gates. Open traffic only when mandatory dependencies are operational.

## 15. How to Design a Clear Dependency Graph

A good dependency graph has these characteristics:

- Dependency direction flows from application layers down to infrastructure layers or abstractions.
- No unnecessary cycles.
- Mandatory dependencies are declared via constructor injection.
- Optional dependencies use ObjectProvider or an explicit mechanism.
- Side effects and background threads start during the lifecycle phase.
- External resources have callbacks to close/reopen appropriately for CRaC.
- Readiness transitions to ready only after dependencies are genuinely operational.

Example:

~~~text
Request Listener
       |
       v
Application Service
       |
       v
Repository
       |
       v
DataSource
       |
       v
Database
~~~

For background workers:

~~~text
SmartLifecycle Worker
       |
       +------> Application Service
       |
       +------> Scheduler
       |
       +------> Message Client
                      |
                      v
                   Broker
~~~

Before checkpoint, stop consumers and workers before closing the clients, schedulers, or DataSources they use. After restore, recreate infrastructure dependencies first and only then start consumers.

## 16. Inspecting Actual Ordering in Spring Boot

When initialization order is not as expected, you can use the following approaches:

### Logging Constructors and Lifecycle Callbacks

In development environments, log at:

- Constructors or factory methods.
- @PostConstruct.
- afterPropertiesSet().
- BeanPostProcessor before/after initialization.
- SmartLifecycle.start() and stop().
- ApplicationRunner.
- ApplicationReadyEvent.
- CRaC beforeCheckpoint() and afterRestore().

Attach bean name, thread name, timestamp, and instance ID to observe the sequence.

Do not log sensitive data in production or log excessively inside frequently invoked callbacks.

### ApplicationContext and Actuator

Spring Boot Actuator can provide the beans endpoint to observe registered beans and the conditions endpoint to see auto-configuration conditions. Expose only necessary endpoints and protect access permissions.

### ApplicationStartup

Spring Framework provides ApplicationStartup and StartupSteps to record startup steps. Spring Boot can configure BufferingApplicationStartup to collect startup information.

Example:

~~~java
SpringApplication application =
    new SpringApplication(MyApplication.class);

application.setApplicationStartup(
    new BufferingApplicationStartup(2048)
);

application.run(args);
~~~

Startup info helps identify time-consuming phases and beans created during refresh. It does not replace thread dumps or lifecycle logs when investigating post-restore errors.

### Inspecting the Dependency Graph

You can enable Spring debug logs and observe bean creation and dependency resolution. When needed, use ApplicationContext.getBeanDefinitionNames() to view the list of bean definitions; this list should not be treated as bean creation order.

## 17. Implementation Workflow

### When the Application Starts

1. Let Spring load BeanDefinitions and register processors.
2. Declare mandatory dependencies using constructor injection.
3. Use @DependsOn for initialization ordering relationships not expressible via injection.
4. Let BeanPostProcessors complete proxying and initialization.
5. Use SmartLifecycle to start listeners, workers, and schedulers.
6. Publish readiness only when out-of-process dependencies are ready.

### Before Checkpoint

1. Stop accepting new requests and triggers.
2. Drain in-flight requests, transactions, and messages being processed.
3. Stop workers/listeners via the lifecycle coordinator.
4. Close DataSources, HTTP clients, file handles, and resources needing recreation.
5. Complete pre-checkpoint callbacks after all components have reached a safe state.

### After Restore

1. Keep the request gate closed.
2. Recreate external resources.
3. Update delegates or wrappers held by beans.
4. Verify databases, brokers, and remote services.
5. Start workers/listeners according to dependencies and lifecycle phases.
6. Start schedulers when dependencies are ready.
7. Open the request gate and mark the application ready.

### When a Checkpoint Is Aborted

If the application proactively calls Core.checkpointRestore(), catch CheckpointException and recover closed resources in the original process. Then restart lifecycle components in dependency order and open the gate only if all steps succeed.

If rollback fails, keep readiness false and report an error to monitoring systems. Do not use afterRestore() to handle the aborted checkpoint branch.

## 18. Key Principles to Remember

- ApplicationContext refresh has clear phases; most non-lazy singletons are created in finishBeanFactoryInitialization().
- BeanDefinitions are registered before bean instances are created.
- Constructors/factory methods, dependency injection, Aware callbacks, initialization callbacks, and BeanPostProcessors have their own order.
- @PostConstruct usually runs before afterPropertiesSet() and custom init-method.
- Dependency injection determines bean creation order following the dependency graph.
- @DependsOn controls singleton initialization order; @Order is not a general rule for bean creation.
- @Primary and @Qualifier select beans; @Lazy defers bean creation.
- SmartLifecycle phases control start/stop order: lower phases start first and higher phases stop first.
- ApplicationRunner and CommandLineRunner run after context refresh; @Order can sort runners.
- Destroy callbacks and dependency destruction typically run in reverse initialization order.
- Restoring from a checkpoint does not by default re-run constructors, @PostConstruct, or the entire refresh phase.
- @DependsOn and SmartLifecycle phases do not automatically control CRaC Resource callback order.
- Recreate external resources before starting workers/listeners and opening the request gate.
- Use an explicit coordinator to coordinate dependencies, readiness, and rollback when a checkpoint is aborted.

Bean ordering in Spring Boot is determined by ApplicationContext phases, the dependency graph, and lifecycle contracts. By properly distinguishing these three layers and coordinating separately with CRaC, the application can start in a predictable order, stop consumers before dependencies, and restore resources before accepting work after restore.