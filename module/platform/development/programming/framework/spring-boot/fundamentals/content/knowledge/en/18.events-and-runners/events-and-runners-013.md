# Distinguishing Bean Initialization Callbacks, Runners, and Readiness Signals

In Spring Boot, there are multiple ways to execute code when an application starts. You can put logic in `@PostConstruct`, implement `InitializingBean`, declare `initMethod` in `@Bean`, write an `ApplicationRunner` or `CommandLineRunner`, or listen for `ApplicationReadyEvent`.

These mechanisms appear at **different times** and answer **different questions**:

- **Bean initialization callback:** What does this individual bean need to prepare before it can be used?
- **Runner:** After the application context has started, what tasks must the application perform before announcing readiness?
- **Readiness signal:** Has the application passed the required startup steps and can it begin receiving traffic according to the readiness mechanism?

If you confuse these milestones, you may accidentally invoke a service before dependencies are ready, run heavy queries inside constructors, or let a load balancer route requests into the application while startup initialization is still incomplete.

## 1. Big Picture of the Startup Process

In a Spring Boot application using a standard application context, the sequence can be visualized as:

```text
SpringApplication.run(args)
          |
          v
Prepare Environment and ApplicationContext
          |
          v
Load configuration and register BeanDefinitions
          |
          v
Create required singleton beans
          |
          +--> Constructor
          |
          +--> Dependency injection / property population
          |
          +--> @PostConstruct
          |
          +--> InitializingBean.afterPropertiesSet()
          |
          +--> @Bean(initMethod = "...")
          |
          v
ApplicationContext refresh completes
          |
          +--> ContextRefreshedEvent
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
```

The diagram is simplified to focus on the milestones studied here. In practice, there are also `BeanPostProcessor` invocations, proxy creation, `SmartLifecycle`, embedded web server startup, other events, and internal steps depending on the Spring Boot version.

An important point: **a web server may already be initialized and listening before `ApplicationReadyEvent`**. Therefore, distinguish a socket's ability to accept connections from the readiness signal used to coordinate traffic routing.

### 1.1. Quick Comparison Table

| Mechanism | Typical Timing | Scope | Used For |
| --- | --- | --- | --- |
| Constructor | When Spring instantiates bean | One bean | Receiving dependencies and setting object state |
| `@PostConstruct` | After dependency injection, during bean initialization | One bean | Validating and preparing internal state |
| `InitializingBean` | During bean initialization phase | One bean | Spring-interface initialization callback |
| `@Bean(initMethod = "...")` | During bean initialization phase | One bean | Custom callback, especially for library classes |
| `SmartInitializingSingleton` | After pre-instantiating non-lazy singletons in bean factory | Bean/container | Work needing eager singletons already instantiated |
| `ContextRefreshedEvent` | When context refresh completes | One `ApplicationContext` | Observing the refresh milestone |
| `ApplicationRunner` | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` | Application run | Startup tasks needing `ApplicationArguments` |
| `CommandLineRunner` | Same phase as `ApplicationRunner` | Application run | Startup tasks receiving `String... args` |
| `ApplicationReadyEvent` | After runners finish executing | Spring Boot run | Observing the application ready milestone |
| `AvailabilityChangeEvent<ReadinessState>` | When readiness state changes | Availability state | Signaling acceptance or refusal of traffic |

## 2. Bean Initialization Callbacks: Tied to Each Object's Lifecycle

Spring manages beans through instantiation, dependency injection, initialization, and destruction per their scope. Initialization callbacks are where a bean completes everything needed to reach a usable state.

For example, a component might need to:

- Validate injected configuration values.
- Build an internal data structure from configuration.
- Prepare a small mapper or lookup table.
- Register local resources owned by the bean.

This callback is **not** a signal that the entire application has started, because other beans may still be waiting to be created and the application context may not have finished refreshing yet.

### 2.1. Constructors and Callbacks Are Not the Same

Example:

```java
package com.example.demo;

import org.springframework.stereotype.Component;

@Component
public class CurrencyFormatter {

    private final CurrencySettings settings;

    public CurrencyFormatter(CurrencySettings settings) {
        this.settings = settings;
        System.out.println("1. Constructor CurrencyFormatter");
    }
}
```

Constructors express mandatory dependencies. Spring must resolve a matching `CurrencySettings` before invoking the constructor.

Avoid putting heavy side effects—such as network API calls, creating database schemas, or running batch jobs—inside constructors. If a constructor throws an exception, bean creation fails; if an operation takes a long time, startup stalls during the container's bean creation phase.

### 2.2. `@PostConstruct`

In Spring Boot 3.x applications using Jakarta APIs, the annotation lives at:

```java
import jakarta.annotation.PostConstruct;
```

Example:

```java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ExchangeRateTable {

    private final CurrencySettings settings;
    private int defaultPrecision;

    public ExchangeRateTable(CurrencySettings settings) {
        this.settings = settings;
    }

    @PostConstruct
    public void initialize() {
        defaultPrecision = settings.precision();
        if (defaultPrecision < 0) {
            throw new IllegalArgumentException(
                    "Currency precision must be non-negative"
            );
        }
        System.out.println("ExchangeRateTable initialized");
    }

    public int precision() {
        return defaultPrecision;
    }
}
```

Here `CurrencySettings` is a project-defined dependency, such as a suitable bean or configuration properties object. `@PostConstruct` executes after Spring performs required dependency injection for the bean and before the bean is exposed as fully initialized.

If a project uses Spring Boot 2.x, the annotation may be `javax.annotation.PostConstruct`; use the package matching your project's Spring Framework/Boot version.

### 2.3. `InitializingBean.afterPropertiesSet()`

Spring also provides the interface:

```java
import org.springframework.beans.factory.InitializingBean;
```

Example:

```java
@Component
public class TemplateRegistry implements InitializingBean {

    private final TemplateProperties properties;

    public TemplateRegistry(TemplateProperties properties) {
        this.properties = properties;
    }

    @Override
    public void afterPropertiesSet() {
        if (properties.directory() == null) {
            throw new IllegalStateException(
                    "Template directory is required"
            );
        }
        System.out.println("TemplateRegistry initialized");
    }
}
```

`InitializingBean` couples the class directly to Spring APIs. That fits certain framework components, yet for ordinary business classes, `@PostConstruct` or a configuration-declared init method keeps the class less coupled to the framework.

### 2.4. `@Bean(initMethod = "...")`

If you cannot modify a class's source code—such as a class from an external library—you can still configure an initialization callback:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ParserConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public ParserEngine parserEngine() {
        return new ParserEngine();
    }
}
```

The example assumes `ParserEngine` has matching `initialize()` and `close()` methods. Spring invokes `initialize()` during bean initialization, and calls `close()` during the corresponding destruction lifecycle.

The init-method callback is useful when library classes lack `@PostConstruct` and do not implement `InitializingBean`.

### 2.5. Callback Order Within a Single Bean

For a standard singleton using all mechanisms, the general order is:

```text
Constructor / factory method
          |
          v
Dependency injection
          |
          v
BeanPostProcessor before initialization
          |
          v
@PostConstruct
          |
          v
InitializingBean.afterPropertiesSet()
          |
          v
Custom init method
          |
          v
BeanPostProcessor after initialization
          |
          v
Bean exposed to other components
```

`@PostConstruct` is typically triggered by a dedicated `BeanPostProcessor`, so the diagram separates it into a step for clarity; in the actual implementation, it sits inside the pre-initialization processing of the bean. Proxies can be created at an appropriate point during post-processing.

**Callback order within one bean does not imply initialization order between different beans.** If bean B requires bean A, declare the dependency via constructor injection or use `@DependsOn` when only an initialization ordering constraint is needed.

## 3. Initialization Callbacks Do Not Mean Every Bean Is Ready

Suppose two components exist:

```java
@Component
public class CatalogCache {
    @PostConstruct
    public void initialize() {
        System.out.println("CatalogCache initialized");
    }
}
```

```java
@Component
public class PriceIndex {
    @PostConstruct
    public void initialize() {
        System.out.println("PriceIndex initialized");
    }
}
```

Do not assume `CatalogCache` always initializes before `PriceIndex` merely because its file appears earlier in the source tree. Neither has a declared dependency relationship.

If `PriceIndex` genuinely needs `CatalogCache`, express that relationship:

```java
@Component
public class PriceIndex {

    private final CatalogCache cache;

    public PriceIndex(CatalogCache cache) {
        this.cache = cache;
    }

    @PostConstruct
    public void initialize() {
        // Cache has been resolved and properly initialized
    }
}
```

The container understands `CatalogCache` is a dependency of `PriceIndex`. There is no need to use `@Order` to establish this relationship.

### 3.1. Impact of `@Lazy`

```java
@Component
@Lazy
public class HeavyDictionary {

    @PostConstruct
    public void initialize() {
        System.out.println("HeavyDictionary initialized");
    }
}
```

A bean marked lazy may only be created when a component actually requests it. Thus, a lazy bean's initialization callback **can run after `ApplicationReadyEvent`** if no eager dependency asks for it during startup.

Conversely, if a non-lazy singleton injects `HeavyDictionary` directly, Spring needs to resolve the dependency and will instantiate the bean during startup.

Do not use a lazy bean's `@PostConstruct` as a milestone indicating the entire application has initialized.

### 3.2. Impact of Prototype Scope

A `prototype` bean is created fresh every time Spring is asked for an instance in that scope:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    @PostConstruct
    public void initialize() {
        System.out.println("New JobContext initialized");
    }
}
```

This example requires the appropriate imports for `Scope` and `ConfigurableBeanFactory`. The callback can run many times as new prototype instances are created, including after the application is already ready.

Therefore, bean initialization is a **per-bean-instance lifecycle**, not a once-per-application startup event.

## 4. `SmartInitializingSingleton`: After Non-Lazy Singletons

Spring Framework provides `SmartInitializingSingleton` with the method `afterSingletonsInstantiated()`.

```java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistryInspector
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println(
                "Regular non-lazy singletons have been instantiated"
        );
    }
}
```

This callback runs after the pre-instantiation phase of non-lazy singletons in the `BeanFactory`. It is useful when a component needs to inspect state prepared by eager singletons.

However, limitations remain:

- Lazy beans might not be created yet.
- Prototype beans are not pre-instantiated like eager singletons.
- The application context may not have finished refreshing yet.
- Startup runners have not executed yet.
- There is no guarantee external systems are ready.

`SmartInitializingSingleton` fits infrastructure components coordinating across beans, yet **does not replace `ApplicationReadyEvent`** when observing the post-runner milestone.

## 5. When Is `ApplicationContext` Considered Refreshed?

When `ApplicationContext.refresh()` finishes, Spring Framework has performed major steps such as processing bean definitions, creating eligible eager singletons, registering listeners, and starting associated lifecycle processors.

Spring Framework publishes:

```java
ContextRefreshedEvent
```

Example:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshReporter {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: " +
                event.getApplicationContext().getId()
        );
    }
}
```

In a Spring Boot application, this event typically arrives **before `ApplicationStartedEvent` and before startup runners**.

If the application has multiple application contexts, such as a parent-child hierarchy, contexts can refresh independently and events can propagate. Do not treat `ContextRefreshedEvent` as the single global signal for the entire Spring Boot application.

### 5.1. `SmartLifecycle` and Server Startup

Spring also has the `SmartLifecycle` interface for components needing start/stop tied to context lifecycle. These components can be orchestrated when the context refreshes or when the context starts/stops, depending on phase and configuration.

This differs from `@PostConstruct`:

- Initialization callbacks prepare **a single bean**.
- `SmartLifecycle.start()`/`stop()` manages **the active operation of a component inside the context**.
- Runners perform **startup tasks in the phase after context refresh**.

For example, a message listener container that needs to begin consuming messages can use lifecycle management. Yet a component starting does not prove all startup runners finished or readiness switched to accepting traffic.

## 6. What Are `ApplicationRunner` and `CommandLineRunner`?

Two interfaces provided by Spring Boot to run work **after the application context has been refreshed**, yet **before Spring Boot publishes `ApplicationReadyEvent`**.

`CommandLineRunner`:

```java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

`ApplicationRunner`:

```java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

When Spring Boot starts successfully through to the runner phase, it finds beans implementing these two interfaces, sorts them per supported ordering, and calls their `run(...)` methods.

### 6.1. `CommandLineRunner` Receives Raw Arguments

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class PrintArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
```

The runner receives the raw argument strings passed to the program. For instance, `--mode=import` remains a single string; to parse it you must process it manually or use `ApplicationRunner`.

### 6.2. `ApplicationRunner` Receives `ApplicationArguments`

```java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportModeRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("mode")) {
            List<String> values = args.getOptionValues("mode");
            System.out.println("Modes: " + values);
        }

        System.out.println(
                "Non-option arguments: " + args.getNonOptionArgs()
        );
    }
}
```

For example, if launching the application with:

```text
--mode=import catalog.json
```

`ApplicationArguments` separates the `mode` option and the non-option argument `catalog.json`. It is helpful for command-line tools or batch jobs.

### 6.3. Runners Can Use Spring-Managed Beans

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {

    private final CatalogService catalogService;

    public CatalogWarmupRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.warmUp();
    }
}
```

`CatalogService` is an appropriate Spring bean injected via the constructor. When the runner is called, the application context has already refreshed, making this usually a better place than `@PostConstruct` to coordinate startup work needing multiple services.

Still keep lazy beans, external connections, and actual initialization state in mind; a refreshed context does not by itself guarantee Redis, databases, or partner services will respond.

## 7. What Should and Shouldn't Runners Do?

Good fits:

- Validating critical configuration before announcing readiness.
- Loading small reference datasets or caches mandatory for the first request.
- Executing finite startup jobs in console applications.
- Checking availability of a dependent service if the application **cannot serve** without that service.
- Recording startup info or purpose-built migration/initialization steps.

Situations requiring caution:

- Running infinite loops inside a runner.
- Calling APIs without timeouts.
- Synchronizing huge datasets without time bounds.
- Launching background threads and assuming the work is already complete.
- Running competing database migrations across multiple replicas without locking/idempotency.

Because runners execute **before `ApplicationReadyEvent`**, a long-running synchronous runner delays or prevents the application from reaching readiness. This may be desirable if the work is mandatory for serving traffic, provided timeouts, error handling, and monitoring are in place.

### 7.1. When a Runner Throws an Exception

Example:

```java
@Component
public class StartupValidationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        throw new IllegalStateException(
                "Required reference data is missing"
        );
    }
}
```

If the exception goes unhandled, Spring Boot treats startup as failed and does not reach `ApplicationReadyEvent` on the successful startup path. Spring Boot may publish `ApplicationFailedEvent`, shut down, and report the error accordingly.

Difference from an exception in `@PostConstruct`: a bean callback error occurs during bean creation/context refresh; a runner error occurs **after the context has refreshed**, during the startup task phase.

### 7.2. Asynchronous Runners Do Not Block Readiness

Example to think carefully about:

```java
@Component
public class BackgroundWarmupRunner implements ApplicationRunner {

    private final Executor executor;
    private final CatalogService catalogService;

    public BackgroundWarmupRunner(
            Executor executor,
            CatalogService catalogService) {
        this.executor = executor;
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(catalogService::warmUp);
    }
}
```

Suppose a suitable `Executor` is configured. The runner simply **submits the work to the executor and returns**. Spring Boot can proceed to publish `ApplicationReadyEvent` while `warmUp()` is still executing.

If warm-up data is mandatory to serve requests, this approach does not prevent the application from accepting traffic too early. Either await completion inside the runner, or design a dedicated readiness gate reflecting actual preparation state.

## 8. Execution Order of Multiple Runners

A Spring Boot app can have multiple `ApplicationRunner` and `CommandLineRunner` beans. You can use `@Order` or the `Ordered` interface to sort them.

Example:

```java
@Component
@Order(10)
public class ValidateConfigurationRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("1. Validate configuration");
    }
}
```

```java
@Component
@Order(20)
public class LoadCatalogRunner
        implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2. Load catalog");
    }
}
```

When two runners are sorted by order, the runner with the smaller value is invoked first. Spring Boot sorts runners from both interfaces within the same startup phase.

**`@Order` here adjusts the invocation order of `run(...)`; it does not dictate the constructor or `@PostConstruct` order of those runner beans.**

If the second runner strictly needs results produced by the first runner, consider:

- Combining the steps into one coordinator with explicit order.
- Expressing the dependency via an appropriate service.
- Using `@Order` when both are genuine startup tasks and order is part of the application contract.
- Ensuring results are validated, errors reported, and tasks safe to re-run.

Do not rely on order between two runners sharing the same order value when order carries business meaning.

### 8.1. How Does It Differ from `@DependsOn`?

```java
@Component
@DependsOn("schemaInitializer")
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

`@DependsOn("schemaInitializer")` requires the bean named `schemaInitializer` to be initialized before `ImportRunner`. It does **not** automatically tell Spring to invoke another runner's `run()` before this runner.

Therefore, distinguish:

| Mechanism | Controls |
| --- | --- |
| Constructor injection | Dependency that must be resolved to instantiate a bean |
| `@DependsOn` | Bean initialization order relationship |
| `@Order` on runner | Execution order of runners during startup phase |

## 9. `ApplicationStartedEvent` and `ApplicationReadyEvent`

Spring Boot publishes two easily confused events:

```text
ApplicationContext refresh completes
             |
             v
ApplicationStartedEvent
             |
             v
Run ApplicationRunner / CommandLineRunner
             |
             v
ApplicationReadyEvent
```

### 9.1. `ApplicationStartedEvent`

`ApplicationStartedEvent` is published after context refresh and before runners. It fits when you want to record that the Spring foundation is built while startup tasks have not yet run.

Example:

```java
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartedReporter {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners not yet called");
    }
}
```

Do not use this event to assert that data prepared by `CatalogWarmupRunner` is complete.

### 9.2. `ApplicationReadyEvent`

`ApplicationReadyEvent` is published after startup runners complete successfully.

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Spring Boot application ready");
    }
}
```

This is a helpful milestone for announcing that Spring Boot startup has reached the end of its normal path.

However, **`ApplicationReadyEvent` does not by itself prove all external services are healthy or all background jobs have finished**. Its meaning rests on the startup steps the application actually performs and waits to complete.

### 9.3. `ApplicationReadyEvent` Listeners Can Block Event Dispatch

In the standard synchronous event multicaster model, listeners execute on the event-publishing thread. If a listener runs long work, publishing `ApplicationReadyEvent` stalls until the listener completes.

```java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    // If a long blocking operation runs here,
    // completing startup can be delayed.
}
```

If the listener launches an async thread/task and returns immediately, it also cannot guarantee the task has finished as Spring Boot continues updating readiness state.

For work **required before ready**, a synchronous runner with clear timeouts and error handling is usually clearer. For **optional** work, an event listener or lifecycle-managed background component may be more suitable.

## 10. Readiness: Signal for Accepting Traffic

Spring Boot provides availability APIs to represent two concepts:

- **Liveness:** the process/application is still running and has not entered a state requiring restart.
- **Readiness:** the application is ready to receive requests from an orchestrator or load balancer.

Common enums:

```java
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

They reside in package `org.springframework.boot.availability`.

### 10.1. Across Which Milestones Does Readiness Change?

Conceptually:

```text
Startup process
       |
       v
ReadinessState.REFUSING_TRAFFIC
       |
       v
Context refresh
       |
       v
Startup runners
       |
       v
ApplicationReadyEvent
       |
       v
ReadinessState.ACCEPTING_TRAFFIC
```

In the common Spring Boot flow, the accepting state is published after `ApplicationReadyEvent`. When shutdown begins, readiness can transition back to refusing before completing application shutdown.

This is a **logical** application signal. Whether a load balancer actually stops or starts sending requests also depends on probes, orchestration configuration, polling intervals, and endpoint update delays.

### 10.2. `ApplicationAvailability`

You can inject `ApplicationAvailability` to inspect current state:

```java
package com.example.demo;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(
            ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean acceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
```

`ApplicationAvailability` describes the state published by Spring Boot and the application, not an automatic check of every external dependency.

### 10.3. Publishing `AvailabilityChangeEvent`

An application can change its readiness state:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public void refuseNewTraffic(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
```

This example is useful when the application is alive yet temporarily unable to handle requests, such as when a required resource is unavailable.

**Publishing timing is critical:** if a listener publishes `REFUSING_TRAFFIC` directly inside `ApplicationReadyEvent`, Spring Boot can still publish `ACCEPTING_TRAFFIC` right after processing the ready event. Therefore, do not rely on a single publish inside a ready listener as a mechanism to block readiness across startup.

If you must hold back traffic until a task completes, pick an explicit design: wait for the work inside a startup runner, use a readiness health indicator/gate reflecting preparation state, or coordinate state explicitly after startup.

### 10.4. Readiness Does Not Mean Open TCP Connections

In web applications, the embedded server may start accepting connections before Spring Boot publishes accepting readiness. A client calling the port directly may still get a response while the orchestrator has not yet added the instance to the traffic pool.

This explains why readiness probes are needed in multi-replica deployments: probes help the orchestrator decide when to start routing requests to a new replica.

## 11. Readiness with Spring Boot Actuator

With Spring Boot Actuator, the application can expose health endpoints, including health groups for liveness/readiness when supported and properly configured.

Example dependency in a Spring Boot 3.x project using Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

To enable health probes in an appropriate local environment:

```properties
management.endpoint.health.probes.enabled=true
```

When endpoints are exposed over HTTP and not blocked by security configuration, you can inspect:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Exact paths also depend on `management.endpoints.web.base-path`, management port, and Actuator configuration. If running on Kubernetes, Spring Boot can auto-detect the environment and enable probes per the version's rules.

### 11.1. Example Kubernetes Probe Configuration

Conceptual example:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
```

This is only the probe snippet placed under a container in a Pod spec. Delay, timeout, and threshold parameters must be tuned to actual startup duration and requirements; do not copy verbatim into production.

If Actuator runs on a **separate management port**, probes on the management port can still succeed while the main application port has issues. When you need to probe close to the actual traffic path, look into exposing probes on the main application port per your Actuator version's configuration.

### 11.2. Should Every Dependency Be Added to Liveness/Readiness?

Liveness should only reflect conditions requiring a process restart. Including transient database errors in liveness can make the orchestrator repeatedly restart otherwise healthy replicas and worsen an outage.

Readiness can reflect dependencies **genuinely required to serve requests**, yet still requires judgment: if all replicas lose connection to one shared service simultaneously, marking every replica unready can leave zero endpoints accepting traffic.

Therefore, tie readiness to how the application serves traffic and recovers, rather than automatically treating every external dependency as a reason to refuse requests.

## 12. An End-to-End Example Across All Three Milestones

The following example shows a bean preparing internal state, a runner doing mandatory work after context refresh, and a listener recording the ready milestone.

### 12.1. Launcher Class

`DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 12.2. Bean with Initialization Callback

`LocalCatalog.java`:

```java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class LocalCatalog {

    private boolean initialized;
    private boolean warmedUp;

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("[1] LocalCatalog initialized");
    }

    public void warmUp() {
        if (!initialized) {
            throw new IllegalStateException(
                    "LocalCatalog has not been initialized"
            );
        }
        warmedUp = true;
        System.out.println("[3] LocalCatalog warm-up completed");
    }

    public boolean isWarmedUp() {
        return warmedUp;
    }
}
```

`LocalCatalog.initialize()` only prepares that bean's basic state. Warm-up work is invoked by the runner after context refresh.

In this example, `initialized` and `warmedUp` are simple flags for observation. If state is accessed concurrently by multiple threads, real applications need proper synchronization such as `volatile`, atomic types, or immutable design.

### 12.3. Recording `ApplicationStartedEvent`

`StartedListener.java`:

```java
package com.example.demo;

import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartedListener {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("[2] Application started");
    }
}
```

This listener runs after context refresh and before startup runners.

### 12.4. Runner Performing Mandatory Work

`CatalogWarmupRunner.java`:

```java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class CatalogWarmupRunner implements ApplicationRunner {

    private final LocalCatalog catalog;

    public CatalogWarmupRunner(LocalCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalog.warmUp();
    }
}
```

The runner is called in the post-refresh phase. Because `warmUp()` executes synchronously inside `run(...)`, Spring Boot waits for the runner to finish before advancing to `ApplicationReadyEvent`.

### 12.5. Listener Observing the Ready Milestone

`ReadyListener.java`:

```java
package com.example.demo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {

    private final LocalCatalog catalog;

    public ReadyListener(LocalCatalog catalog) {
        this.catalog = catalog;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "[4] Application ready; catalog warmed up = " +
                catalog.isWarmedUp()
        );
    }
}
```

### 12.6. Illustrative Output

In an application with the components above and no startup failures, the example log lines typically appear in this order:

```text
[1] LocalCatalog initialized
[2] Application started
[3] LocalCatalog warm-up completed
[4] Application ready; catalog warmed up = true
```

Other Spring Boot logs may appear in between. If the application contains other beans or runners, do not take this example as an absolute guarantee of callback order across all beans. What matters is the order of **the main milestones**:

```text
Bean initialization
       <
ApplicationStartedEvent
       <
Runners complete
       <
ApplicationReadyEvent
```

In this example, `LocalCatalog` is created early because the runner and listener depend on it. For a lazy bean not requested during startup, its bean callback can run after these milestones.

## 13. When Startup Fails, Which Milestones Still Occur?

This is a practical way to recognize the role of each mechanism.

### 13.1. Exception in `@PostConstruct`

```java
@PostConstruct
public void initialize() {
    throw new IllegalStateException("Invalid configuration");
}
```

If this is an eager bean created during refresh and the exception goes unhandled, context refresh can fail. Startup does not proceed to runners or `ApplicationReadyEvent`.

### 13.2. Exception in a Runner

```java
@Override
public void run(ApplicationArguments args) {
    throw new IllegalStateException("Catalog warm-up failed");
}
```

The context may have refreshed successfully and `ApplicationStartedEvent` may have been published. However, the startup runner fails, so `ApplicationReadyEvent` is not published on the success path.

### 13.3. Failures After Ready

Suppose `ApplicationReadyEvent` has been published, readiness switched to accepting, and then the application loses connectivity to a mandatory service.

That is a **runtime** error, no longer a startup cycle error. Handle it via retry policies, circuit breakers, monitoring, health/readiness states, and recovery mechanisms. You cannot ask Spring Boot to re-run `ApplicationRunner` simply because an external dependency failed.

### 13.4. Scenario Table

| Scenario | Context refresh | Runners | Ready event |
| --- | --- | --- | --- |
| Normal startup, valid eager beans | Completes | Run, complete | Yes |
| Eager bean fails in `@PostConstruct` during refresh | Fails | Never reaches runner phase | No |
| Runner throws exception | Completed | Called, yet failed | No |
| Async warm-up submitted to executor and runner returns | Completed | May complete early | May fire before warm-up finishes |
| Lazy bean only requested after ready | Completed | Not necessarily related | May have fired before lazy bean callback |

## 14. Using the Right Mechanism for the Purpose

### 14.1. Validating a Bean's Own Configuration

Use `@PostConstruct`, `InitializingBean`, or an init method when the work ties directly to **that bean's own operability**.

Examples: validating required properties, building an internal map, or preparing a parser.

### 14.2. Performing Application-Level Work Before Ready

Use `ApplicationRunner` or `CommandLineRunner` when coordinating multiple services or handling finite startup data that the application must complete before announcing ready.

Example: loading required catalog data so APIs can respond right away.

### 14.3. Recording That Startup Completed

Use `ApplicationReadyEvent` when observing the milestone that the application finished its runners.

Examples: logging startup duration, emitting metrics, or notifying internally that startup completed.

### 14.4. Deciding Whether to Accept or Refuse Traffic

Use readiness state/probes when controlling traffic based on current ability to serve requests.

Example: temporarily refusing requests while a mandatory component is recovering, even though the JVM is alive and beans have long been initialized.

### 14.5. Cleaning Up Resources When a Bean or Context Ends

This is the reverse direction of startup:

- `@PreDestroy`, `DisposableBean`, or custom destroy method: cleanup tied to a bean.
- `SmartLifecycle.stop()`: stopping a lifecycle-managed component.
- `ContextClosedEvent`: observing the context closing.
- Readiness `REFUSING_TRAFFIC`: traffic coordination signal during shutdown or runtime disruption.

Do not use `ApplicationReadyEvent` to manage cleanup, or `@PreDestroy` as a startup signal.

## 15. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`@PostConstruct` runs when the entire app is ready." | It runs when that specific bean initializes, which can be early or late depending on scope/lazy |
| "A bean with `@PostConstruct` means all other beans exist." | The callback belongs only to the lifecycle of the bean being created |
| "`SmartInitializingSingleton` equals ready." | It runs after pre-instantiating non-lazy singletons, before several later startup milestones |
| "`ContextRefreshedEvent` means runners finished." | Runners are normally invoked after refresh |
| "`ApplicationStartedEvent` and `ApplicationReadyEvent` are the same." | Started occurs before runners; Ready after runners finish |
| "If a runner runs async work, Spring Boot waits for the task." | Once the runner returns, Spring Boot can proceed; background tasks keep running |
| "Ready means every external API is healthy." | Readiness reflects whichever conditions/checks the application actually enforces |
| "Web server opening its port means readiness is accepting." | The server can listen before readiness is published |
| "`@Order` on a bean determines constructor order." | It sorts supported extension points, such as runner order |
| "A runner error means the context has not refreshed." | Runners are called after refresh; errors can occur after a successful refresh |
| "Readiness refusing means the process is dead." | The application may be alive yet temporarily unready for traffic |
| "`ApplicationReadyEvent` waits for all background threads." | Spring Boot only awaits synchronous startup work it orchestrates |

## 16. Practice Exercises

### Exercise 1 — Print Startup Milestones

Create a Spring Boot project with:

1. A bean with a constructor printing `"Constructor"`.
2. A `@PostConstruct` method printing `"PostConstruct"`.
3. A `ContextRefreshedEvent` listener printing `"ContextRefreshed"`.
4. An `ApplicationStartedEvent` listener printing `"Started"`.
5. An `ApplicationRunner` printing `"Runner"`.
6. An `ApplicationReadyEvent` listener printing `"Ready"`.

Start the app and record the log order. Separate lines tied to bean lifecycle from lines tied to application lifecycle.

### Exercise 2 — Move Work Out of `@PostConstruct`

Suppose a service is loading a large dataset from the database inside `@PostConstruct`, causing slow bean creation and hard-to-control errors.

Move that mandatory data loading into an `ApplicationRunner`, keeping only required internal state checks inside the bean callback.

**Question:** how does the timing of a data-loading failure change? Does Spring Boot publish `ApplicationReadyEvent` if the runner fails?

### Exercise 3 — Compare Two Runners

Create an `ApplicationRunner` with `@Order(10)` and a `CommandLineRunner` with `@Order(20)`.

Launch with:

```text
--mode=demo sample.txt
```

Observe how `ApplicationArguments` and `String... args` represent the arguments, as well as the `run(...)` order of the two runners.

### Exercise 4 — Trigger Startup Failures

Sequentially:

- Throw an exception inside `@PostConstruct` of an eager bean.
- Throw an exception inside `ApplicationRunner`.

Record whether `ContextRefreshedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent` appear. Explain the reason based on failure timing.

### Exercise 5 — Simulate Asynchronous Warm-Up

Create a runner that submits a warm-up task to an `Executor` and returns immediately. Inside an `ApplicationReadyEvent` listener, print the `warmUpCompleted` flag.

**Question:** why can the flag still be `false` when the ready event fires? How would you fix it if warm-up data is mandatory before taking traffic?

### Exercise 6 — Observe Readiness

Add Spring Boot Actuator and enable probes locally. Observe `/actuator/health/readiness` during startup and after runners complete.

If the app starts too fast, create a runner doing finite work long enough to observe. Do not use an infinite loop; do not use sleep as business logic in production applications.

### Exercise 7 — Distinguish Runtime Errors from Startup Errors

After the app is ready, simulate a mandatory dependency temporarily losing connection. Design an appropriate readiness update or custom health indicator, and explain why you should not restart every replica just because a shared dependency has a brief outage.

### Exercise 8 — Choose the Right Mechanism

Pick a mechanism for each requirement:

| Requirement | Suggested Choice |
| --- | --- |
| Validate a single bean's configuration upon bean creation | `@PostConstruct` or init method |
| Need to observe eager singletons already initialized | `SmartInitializingSingleton` |
| Must load catalog before application is ready | Synchronous runner with error handling |
| Log info once runners complete | `ApplicationReadyEvent` |
| Temporarily remove instance from load balancer | Appropriate readiness state/probe |
| Clean up a bean's resources when context closes | `@PreDestroy` or destroy method |

Explain why swapping a choice for `@Order` or `ContextRefreshedEvent` may fail to satisfy the requirement.

## 17. Key Takeaways

**Bean initialization callbacks serve each individual bean's lifecycle; runners serve application-level startup work; readiness expresses the ability to receive traffic.** These three layers of responsibility are related yet not identical.

In a typical startup flow, an eager bean is instantiated and runs its callbacks before context refresh completes. Afterward, Spring Boot publishes `ApplicationStartedEvent`, invokes runners, and publishes `ApplicationReadyEvent`; readiness can transition to `ACCEPTING_TRAFFIC` once startup finishes.

Place internal preparation in bean callbacks, place tasks mandatory before ready in bounded synchronous runners with clear error handling, use `ApplicationReadyEvent` to observe startup completion, and use readiness probes/states to coordinate traffic across the application's lifetime. Choosing the right mechanism makes startup predictable, catches errors at the right moment, and prevents serving requests before the application is truly capable of handling them.
