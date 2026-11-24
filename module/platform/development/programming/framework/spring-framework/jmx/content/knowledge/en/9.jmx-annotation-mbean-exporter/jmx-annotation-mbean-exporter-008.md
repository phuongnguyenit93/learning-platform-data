# Initialization Order of AnnotationMBeanExporter with Dependent Beans

## 1. The Problem: Where Does the Exporter Run in the Spring Lifecycle?

In Spring Framework, `AnnotationMBeanExporter` discovers beans declared for management via annotations such as `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`, then exports them as MBeans into an `MBeanServer`. Issues arise when a bean exported to JMX **depends on other components**: a datasource, cache, message consumer, scheduler, connection-initializing service, or runtime configuration.

A seemingly simple yet crucial question: **when the exporter registers an MBean, to what extent are the managed bean's dependencies actually ready?**

Three milestones must be separated:

1. **Bean created and dependency injection completed**: dependent objects have been resolved by Spring according to singleton initialization mechanics.
2. **Bean has executed its own initialization callbacks**: `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom init methods; callbacks are applied per the corresponding lifecycle.
3. **External systems are ready to serve**: remote connections are active, cache warm-up has finished, listeners have subscribed, or background tasks have reached `READY`. The third milestone does not necessarily coincide with the first two.

An MBean may already appear in JConsole before an external resource reaches the expected state. A JMX client calling `getStatus()` or an operation may then observe `STARTING`, receive incomplete data, or encounter errors if the code assumes the system is already `READY`.

This lesson focuses on understanding and controlling **initialization order**, without turning the JMX exporter into an orchestrator for the entire system.

## 2. Participating Components

A typical diagram:

```text
ApplicationContext.refresh()
          |
          +--> register BeanDefinitions / BeanFactoryPostProcessors
          |
          +--> register BeanPostProcessors
          |
          +--> instantiate non-lazy singletons
                  |
                  +--> DataSource / Cache / BusinessService
                  |
                  +--> ManagementFacade (@ManagedResource)
                  |
                  +--> AnnotationMBeanExporter
                             |
                             +--> locate managed beans
                             +--> build MBeanInfo from annotation metadata
                             +--> register MBean into MBeanServer
          |
          +--> complete refresh / lifecycle startup
          |
       JMX clients can access the MBean
```

Exact ordering between independent singletons should not be inferred from class name order, source declaration order, or package scan order. Spring creates dependencies before it can create objects requiring them; singletons without an explicit dependency relationship may be initialized in an implementation order that should not be relied upon as a business contract.

Roles:

| Component | Responsibility | What to Watch Out For |
|---|---|---|
| `ManagementFacade` | Exposes management state/operations | Do not assume all resources are always READY |
| `BusinessService` | Runs business logic | May need a datasource or cache |
| `DataSource` / external client | Accesses external systems | Bean existence does not prove the connection works |
| `AnnotationMBeanExporter` | Discovers and registers MBeans from annotations | Can make MBeans visible during context startup |
| `MBeanServer` | MBean registry, handles JMX requests | Does not manage service business lifecycle |
| `SmartLifecycle` | Coordinates start/stop by phase | Intended for lifecycle components, does not replace dependency injection |

In particular, `AnnotationMBeanExporter` is an export utility. `@ManagedResource` merely states that the bean wants to expose a management interface; it **does not start background services** and does not prove that resources used by the service are completely healthy.

## 3. Which Ordering Does Dependency Injection Establish?

Suppose:

```java
@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }
}
```

and a management bean depends on the service:

```java
@Component
@ManagedResource(objectName = "demo.inventory:type=InventoryMonitor")
public class InventoryMonitor {
    private final InventoryService inventoryService;

    public InventoryMonitor(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ManagedAttribute
    public boolean isAvailable() {
        return inventoryService.isAvailable();
    }
}
```

Spring must resolve `InventoryService` before finishing `InventoryMonitor`; the service in turn needs `InventoryRepository`. Constructor injection relationships express a **direct dependency graph**:

```text
InventoryRepository
       -> InventoryService
              -> InventoryMonitor
```

This guarantees required dependencies are supplied before the monitor's constructor finishes. However, it does not necessarily guarantee the repository can connect to the database immediately, or that the service has completed a background task started after refresh.

If a JMX getter queries the database to check availability, it may perform a network operation right on the management request thread. A more resilient design usually returns an **observed/updated state** such as `STARTING`, `READY`, `DEGRADED`, or `STOPPED` instead of triggering initialization inside a getter.

## 4. When AnnotationMBeanExporter Participates

`AnnotationMBeanExporter` is a convenient variant of `MBeanExporter` with built-in support for management annotation metadata. The exporter integrates with the Spring bean lifecycle to register MBeans as the context starts up. Specific details around scanning timing, registration, and deferred registration depend on the Spring version and exporter configuration, such as `autodetect`, explicit mappings, and registration mode.

What to understand at the model level:

- The exporter must have an `MBeanServer` to register MBeans.
- Exported beans must be resolved and provided via Spring's appropriate mechanism.
- Registering an MBean only establishes **management accessibility**; it does not wait for all background jobs to finish.
- Once an MBean is registered, JMX clients can read attributes or invoke operations if connected and authorized.
- If bean initialization or registration fails, refresh may fail or the exporter may act according to its configured registration policy.

Do not rely on Java configuration file ordering to assume `AnnotationMBeanExporter` will always run after every service. You need an explicit dependency/lifecycle model or a management interface that tolerates unready states.

## 5. @DependsOn: Forcing a Bean to Initialize First

When one bean requires another bean **to be initialized first**, without a direct constructor/property dependency, Spring provides `@DependsOn`:

```java
@Configuration
public class InitializationConfig {

    @Bean("managementInfrastructure")
    public ManagementInfrastructure managementInfrastructure() {
        return new ManagementInfrastructure();
    }

    @Bean
    @DependsOn("managementInfrastructure")
    public InventoryMonitor inventoryMonitor(
            InventoryService inventoryService) {
        return new InventoryMonitor(inventoryService);
    }
}
```

`@DependsOn` tells Spring that `managementInfrastructure` must be initialized before `inventoryMonitor`. For singletons in the same context, this relationship also applies to destruction order: the dependent bean is typically destroyed before the bean it depends on.

**Important limitation:** `@DependsOn` waits for **bean initialization** to complete per the Spring contract, not for arbitrary async tasks to finish. For example, if `managementInfrastructure` submits a task to an executor in `@PostConstruct` and returns, `@DependsOn` does not mean the task has finished.

An unsuitable pattern is:

```java
@PostConstruct
void start() {
    executor.submit(this::connectToRemoteSystem);
}
```

and then inferring that another bean with `@DependsOn` can already use the remote connection immediately. To reflect readiness, you need a separate `READY` mechanism or a lifecycle barrier with an explicit wait contract.

### 5.1. Should you put @DependsOn on the exporter?

If there is an explicit requirement that an infrastructure bean must be initialized before the exporter, you can declare a dependency on the exporter's `BeanDefinition`. However, do not use `@DependsOn` as a "cure-all for race conditions." It does not wait for external readiness on its own, and changing exporter order can sometimes delay management visibility or introduce circular dependencies.

It is usually clearer to give exported beans explicit dependencies, use `SmartLifecycle` for background activity, and let the MBean report an unready state. If you genuinely need to defer MBean registration, pinpoint the exact lifecycle milestone and registration mechanism rather than relying on arbitrary bean names/annotations.

## 6. When Do @PostConstruct and InitializingBean Run?

During Spring bean initialization, constructor and injection run before init callbacks like `@PostConstruct` or `InitializingBean.afterPropertiesSet()`. `BeanPostProcessor` implementations can wrap these phases; proxies can also be created during post-processing.

Example:

```java
@Component
public class CacheManager {

    private volatile boolean initialized;

    @PostConstruct
    public void initialize() {
        // Illustrates synchronous initialization only.
        loadLocalConfiguration();
        initialized = true;
    }

    public boolean isInitialized() {
        return initialized;
    }

    private void loadLocalConfiguration() {
        // Synchronously load file/configuration.
    }
}
```

If `loadLocalConfiguration()` runs synchronously and does not return until finished, beans created afterward with a mandatory dependency on `CacheManager` receive a bean that has passed normal initialization callbacks.

However, if `initialize()` merely triggers a `CompletableFuture`, `initialized=true` must be set **when the work actually completes**, not right after submitting it. Nor should you try to serialize the entire startup by blocking indefinitely inside `@PostConstruct`: that can stall the application context and cause deadlocks if the awaited work needs beans/context still completing refresh.

## 7. Example: Exposing an Explicit Lifecycle State

Instead of letting getters throw exceptions when a service is not ready, design an observable state:

```java
public enum StartupState {
    NEW, STARTING, READY, FAILED, STOPPED
}
```

A service managing startup:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicReference<StartupState> state =
        new AtomicReference<>(StartupState.NEW);

    public StartupState getState() {
        return state.get();
    }

    public void markStarting() {
        state.set(StartupState.STARTING);
    }

    public void markReady() {
        state.set(StartupState.READY);
    }

    public void markFailed() {
        state.set(StartupState.FAILED);
    }

    public void markStopped() {
        state.set(StartupState.STOPPED);
    }
}
```

Read-only management MBean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "demo.catalog:type=CatalogStatus",
    description = "Catalog startup state"
)
public class CatalogStatusMBean {
    private final CatalogService service;

    public CatalogStatusMBean(CatalogService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Current lifecycle state")
    public String getState() {
        return service.getState().name();
    }

    @ManagedAttribute(description = "Whether catalog can serve requests")
    public boolean isReady() {
        return service.getState() == StartupState.READY;
    }
}
```

When properly exported, a JMX client can observe `State=NEW`, `STARTING`, `READY`, `FAILED`, or `STOPPED` depending on timing. The getter does not force the service to initialize itself or open connections. This lets operations distinguish **MBean accessibility** from **business readiness**.

If a management operation is only valid when `READY`, it should check state:

```java
@ManagedOperation
public void refreshCatalog() {
    if (service.getState() != StartupState.READY) {
        throw new IllegalStateException("Catalog is not READY");
    }
    service.refresh();
}
```

When Spring/JMX invokes the operation, the client must handle exceptions per JMX mechanics. Do not use the MBean's presence in the registry as the sole signal to enable operations with side effects.

## 8. SmartLifecycle and Phase: Coordinating Start/Stop Activity

Spring provides `SmartLifecycle` for components with start/stop behavior. An important feature is that `SmartLifecycle` beans can be started by **phase** during application context refresh; lower phases typically start before higher phases, and shutdown runs in reverse order.

Illustrative example:

```java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class ConsumerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        // Start synchronously or track readiness separately if async.
        running.set(true);
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

`SmartLifecycle` also has a `stop(Runnable callback)` contract for asynchronous shutdown depending on implementation and version; the callback must be invoked when stopping completes. The example code uses simple synchronous stop only.

**Common misconception:** phase coordinates **lifecycle start/stop** of beans participating in that mechanism; it is not a general rule for ordering arbitrary `@Bean` instantiation or automatically guaranteeing `AnnotationMBeanExporter` registers after every component. If the MBean needs to report status before `SmartLifecycle` starts, `State=STARTING` is a valid result.

Distinguish:

```text
Dependency ordering:   A must be created before B.
Lifecycle phasing:     A.start() runs before B.start() by phase.
Operational readiness: dependent systems can actually serve requests.
```

These three relationships may be related, but they are not identical.

## 9. ApplicationReadyEvent and ContextRefreshedEvent

In Spring Framework, `ContextRefreshedEvent` is published when the application context has been initialized or refreshed. In Spring Boot, `ApplicationReadyEvent` typically signals that the boot sequence has finished and the application is ready according to the Boot model.

Spring Boot example:

```java
@Component
public class ReadinessMarker {
    private final CatalogService service;

    public ReadinessMarker(CatalogService service) {
        this.service = service;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        service.markReady();
    }
}
```

Import `org.springframework.boot.context.event.ApplicationReadyEvent` and `org.springframework.context.event.EventListener` when using this example. This is a **Spring Boot** hook, not available in plain Spring Framework without Boot.

However, `ApplicationReadyEvent` only marks a milestone in Boot's startup sequence. If the service depends on an external system or has an incomplete background warm-up, the application itself must still decide when it is truly `READY`. Do not mark `READY` unconditionally if business conditions are not yet met.

A sound model is:

```text
Context refresh completes
    -> core infrastructure has been created
    -> lifecycle start proceeds
    -> readiness is published from verified state
    -> JMX getter returns current state
```

Thus, the exporter can export the MBean before or during startup milestones while clients still observe valid progression.

## 10. Complex Dependency Chains and Circular Dependencies

If a management bean depends on a service, and the service in turn depends on the exporter or a bean the exporter indirectly creates, you can create a circular dependency:

```text
ManagementFacade
      -> BusinessService
             -> ManagementFacade
```

or:

```text
Exporter -> ManagementFacade -> MonitoringInfrastructure -> Exporter
```

Constructor injection usually surfaces circular dependency errors clearly during bean creation. Using setter injection or lazy proxies can mask the cycle in some cases, but does not make the architecture easier to understand.

To avoid this:

1. Keep `ManagementFacade` a thin observation layer with a one-way dependency on the service or state holder.
2. Do not make business services require the exporter simply to operate.
3. Separate `LifecycleState`/metrics holders from management UI/facades if multiple components need the same information.
4. Do not invoke JMX operations inside the constructor or initialization of the very dependency that operation needs.
5. Only use `@Lazy` when deferred initialization is genuinely a design choice, not a way to hide a flawed dependency graph.

Lower-risk diagram:

```text
BusinessService ---> SharedOperationalState <--- ManagementFacade
                                               |
                                       registered by exporter
```

If the exporter initializes a bean to inspect metadata, that must not trigger a chain of side effects causing the service to access unprepared resources.

## 11. Exporter and Proxies: Which Object Gets Exported?

In Spring applications, beans can be wrapped by proxies, such as AOP, transactional, or scoped proxies. When `AnnotationMBeanExporter` interacts with a bean, distinguish the **bean definition**, the instantiated object, the proxy returned by the container, and the interface/methods actually exported.

Possible phenomena:

- Annotations are placed on the implementation while metadata inspection goes through the proxy.
- The management interface declares only some methods, while the implementation has many more.
- The bean is lazy and only instantiated when requested by the exporter or another component.
- A management method calls into a service with a transactional proxy, so the result depends on execution context.

Do not assume annotations on any arbitrary class will always be exposed identically under all proxy types. When encountering issues, check the `MBeanInfo` of the registered ObjectName, the actual bean type, and the exporter/assembler mechanism. Resolve it according to proxy configuration and your Spring version rather than arbitrarily rearranging bean creation order.

## 12. Do Not Confuse "Registration Succeeded" with "Dependency Healthy"

Suppose `DatabaseClient` has a constructor that does not connect immediately; the real connection is only opened on the first query. Spring has created the bean and the exporter has registered the monitor, yet the database might be down.

Three observations:

| Observation | Can Assert | Cannot Yet Assert |
|---|---|---|
| `ManagementFacade` is in the context | Bean was created or is resolvable per scope | External dependencies are healthy |
| MBean appears in JConsole | Registration succeeded | Service is READY |
| `getState() == READY` | Application declared itself READY | All features will succeed forever |

A health/readiness attribute should be updated from meaningful signals, which might include pings, warm-up completion, circuit breakers, or subscription status. Avoid performing heavy health checks inside a getter on every JConsole refresh; it is better to update periodically or via events, and have the getter return a concise state.

## 13. When Should MBean Registration Be Deferred?

It is not always necessary. Many systems intentionally let MBeans appear **early** so operations tools see `STARTING` and why startup is slow. Hiding an MBean until `READY` can blind observability right when the system hits a startup failure.

However, if an MBean is only valid after a mandatory resource exists, registration may need control. Options:

- Design the management bean to return `NOT_READY` initially.
- Initialize mandatory synchronous dependencies before the exporter through genuine bean dependencies, provided it does not unreasonably block startup.
- Register the MBean explicitly upon reaching a specific lifecycle milestone instead of default auto-detection; remember to manage unregistration on shutdown.
- Use a registration/exporter mechanism compatible with your Spring version and `MBeanServer` ownership.

The last option must account for early client connections, registration error handling, ObjectName collisions, and operational permissions. Removing MBeans during shutdown also has an order; management callbacks may still be running as the application begins closing, so operations must check state and handle shutdown safely.

## 14. AnnotationMBeanExporter Configuration Example

The simplest way to enable annotation-based JMX export in Spring Framework is using `@EnableMBeanExport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Spring creates the appropriate exporter infrastructure to detect `@ManagedResource` along with accessor/operation annotations. In configurations needing deeper customization, you can declare `AnnotationMBeanExporter` directly:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ManualJmxConfiguration {

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

**Choose one clear exporter creation mechanism.** Avoid combining `@EnableMBeanExport` with declaring multiple exporters that register the same set of ObjectNames unless a registration policy is intentionally designed. Two exporters can compete for the same name and cause `InstanceAlreadyExistsException` or unintended policy-driven overrides.

With Spring Boot, auto-export configuration may differ; check `spring.jmx.enabled` and your Boot version. The examples above target core Spring Framework.

### 14.1. Configuring a BeanDefinition name dependency

If explicit ordering is genuinely required for a self-declared exporter bean, you can attach a dependency:

```java
@Bean
@DependsOn("managementPrerequisite")
public AnnotationMBeanExporter annotationMBeanExporter() {
    return new AnnotationMBeanExporter();
}
```

This works when `managementPrerequisite` is a synchronously initialized bean with that exact name. `@DependsOn` does not wait for async work triggered by that bean to complete. If the prerequisite is not truly ready, a separate readiness state/condition is still required.

## 15. Observing Actual Order via Logs and JMX

When studying lifecycle, do not guess solely from class names. Place logs at key milestones, for example:

```java
@Component
public class StartupProbe {
    private static final Logger log =
        LoggerFactory.getLogger(StartupProbe.class);

    @PostConstruct
    void initialized() {
        log.info("StartupProbe: PostConstruct");
    }

    @EventListener(ContextRefreshedEvent.class)
    void contextRefreshed() {
        log.info("StartupProbe: ContextRefreshedEvent");
    }
}
```

Required imports for a Spring project using SLF4J and Jakarta annotations:

```java
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
```

In `ManagementFacade`, add logs in the constructor and init callback (if needed); meanwhile, you can use `MBeanServer.queryNames(new ObjectName("demo.catalog:*"), null)` to inspect registered MBeans after a lifecycle milestone. Only perform this query when you already hold the right `MBeanServer` reference; avoid creating an extra exporter just to log.

Observe the sequence:

```text
CatalogService constructed
CatalogService initialized
ManagementFacade constructed
ManagementFacade initialized
MBean registered
Context refreshed
Application ready (if using Spring Boot)
```

This is an **illustrative desired order**, not a guaranteed output for every Spring application. Actual results depend on configuration, auto-detection, lazy initialization, post-processors, and other dependencies. Capture timestamps/traces from the actual running application.

## 16. Common Pitfalls

### 16.1. MBean is registered, but getter throws NullPointerException

The usual cause is a management bean holding a dependency assigned outside the injection contract or accessing data initialized only afterward. Use constructor injection for mandatory dependencies, represent a `STARTING` state when external dependencies are not ready, and avoid dereferencing before `READY`.

### 16.2. Added @DependsOn, yet resource-not-ready errors persist

The dependent bean was created first, but its async work has not finished. Fix the readiness contract or switch to synchronous init where appropriate, rather than chaining long `@DependsOn` sequences experimentally.

### 16.3. Bean circular dependency

A monitor calls a service that calls back into the monitor/exporter right in its constructor; Spring may report a circular dependency error. Extract a state holder and avoid reverse dependencies from business services to the JMX layer.

### 16.4. MBean not visible in JConsole

Verify that the exporter is configured, the bean has `@ManagedResource`, the ObjectName is valid, the context has refreshed, no duplicate registration occurred, and JConsole is connected to the right JVM. An annotated bean not scanned by the exporter still will not appear.

### 16.5. MBean only appears after the bean is called the first time

Lazy initialization or registration strategy can alter when it appears. Check lazy/proxy settings and the exporter; do not assume every singleton is always created at the start of refresh.

### 16.6. Exporter registers duplicate ObjectName

Two exporters or two beans with the same ObjectName can collide. Design clear naming strategies and ownership, and enable only one auto-export configuration for the same bean set unless there is a specific reason otherwise.

### 16.7. Operation runs while the service is STOPPING

A client kept a connection open and invoked an operation during shutdown. The operation must reject or handle calls safely according to lifecycle state, rather than relying solely on whether the MBean was still in the registry when the call began.

## 17. Hands-On Exercises

**Exercise 1 — Dependency injection and startup state.** Create `CatalogService` and `CatalogStatusMBean` using constructor injection. Transition the service through `NEW -> STARTING -> READY` via a background worker. Open JConsole and record `State` across milestones. Explain why the MBean is readable before `READY`.

**Exercise 2 — Comparing synchronous and asynchronous init.** Create an `Initializer` bean with `@PostConstruct`: first perform synchronous work before returning; second, only submit a task to an executor. Add `@DependsOn("initializer")` to another bean and observe when the second bean is created. Explain the limitation of `@DependsOn`.

**Exercise 3 — SmartLifecycle phase.** Create two `SmartLifecycle` beans `A` and `B` with phases 0 and 100 respectively. Log `start()` and `stop()` and compare their order. Explain why phase is not a general-purpose tool for ordering initialization of arbitrary beans.

**Exercise 4 — MBean operation in error state.** Add `refreshCatalog()` to the monitor. When the service is `FAILED` or `STOPPED`, reject the operation with a clear message. Compare the behavior of `getState()` and the operation.

**Exercise 5 — Breaking a circular dependency.** Start with the graph `ManagementFacade -> BusinessService -> ManagementFacade`. Refactor into a `SharedOperationalState` referenced by both, then explain the new dependency graph.

**Exercise 6 — Observing the exporter.** Enable `@EnableMBeanExport`, create a bean with `@ManagedResource`, and log init callbacks and context events. After startup, query `MBeanServer` to inspect the ObjectName. This exercise is for observing lifecycle—do not assume the output before running it.

## 18. Self-Check Questions

1. Does Spring finishing creation of a dependency guarantee an external service is `READY`?
2. What kind of ordering do constructor injection and `@DependsOn` resolve?
3. Does `@PostConstruct` finishing mean a `CompletableFuture` submitted inside it has completed?
4. Which callbacks does `SmartLifecycle.getPhase()` affect?
5. Does `ContextRefreshedEvent` belong to Spring Framework or Spring Boot?
6. Which framework does `ApplicationReadyEvent` belong to, and does it prove every external dependency is healthy?
7. Why can an MBean returning `State=STARTING` be more useful than hiding the MBean until `READY`?
8. Why can registering multiple `AnnotationMBeanExporter` instances for the same beans cause errors?
9. What should a management operation do if the service is `STOPPING`?
10. When encountering startup ordering errors, which log milestones and JMX metadata help narrow down the cause?

## 19. Key Takeaways

**Initialization order and readiness state are two different contracts.** Spring dependency injection and `@DependsOn` coordinate bean creation order; init callbacks complete per the Spring lifecycle; `SmartLifecycle` coordinates start/stop activity; and readiness of external systems must be represented and verified separately.

`AnnotationMBeanExporter` publishes the management interface into `MBeanServer`. A successfully registered MBean only proves it is accessible via JMX; safe getters and operations must handle cases where the service is still `STARTING`, `FAILED`, or `STOPPING`. Designing one-way dependencies, using clear lifecycle states, and verifying runtime results will keep JMX reliable when a Spring application has many dependent beans.
