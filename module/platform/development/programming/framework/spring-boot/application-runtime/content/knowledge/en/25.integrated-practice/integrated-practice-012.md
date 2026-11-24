# Building a Decision Matrix for Choosing Extension Points by Timing, Dependencies, and Completion Requirements in Spring Boot

## 1. Practice Problem: Choose the Right Hook, Not Just Memorize Callback Names

A Spring Boot application may need to add a PropertySource, alter bean definitions, warm up a cache, verify an external service, start a consumer, publish readiness, or close resources. These are **distinct timing requirements**, even though all of them might loosely be called application initialization.

Before choosing an extension point, answer three questions:

1. **When?** Before Environment, before bean definitions, as a bean is created, after eager singletons are created, after refresh, before readiness, after readiness, at runtime, or during shutdown?
2. **What can it depend on?** Does Environment exist yet? Does ApplicationContext exist yet? Is BeanDefinitionRegistry ready? Can it inject services/repositories? Does an embedded server or DataSource exist yet?
3. **How complete must it be?** Merely register configuration, run a synchronous callback, wait for an external check to succeed, fire-and-forget, or stop asynchronously and invoke a confirmation callback?

These three questions govern the correctness of lifecycle logic. For example:

~~~text
Order processing application
    |
    +-- read and merge configuration
    +-- select bean definitions to register
    +-- create services and connection pools
    +-- verify mandatory gateway before readiness
    +-- publish traffic-accepting state
    +-- start consuming messages
    |
    +-- long-running execution
    |
    +-- receive SIGTERM
          +-- stop accepting new messages and HTTP requests
          +-- await in-flight work with bounded time
          +-- close executors, connections, caches
          +-- process exits
~~~

Putting everything into **`@PostConstruct`** can run logic too early. Putting everything into **`ApplicationReadyEvent`** can run mandatory steps too late. Using **`@PreDestroy`** for a consumer needing ordered shutdown makes it impossible to accurately signal when asynchronous work has finished draining.

**Objective:** build a reusable selection table, practice it with Java 17+/Spring Boot 3.3.13, and prove each milestone with real tests instead of guessing from logs or `Thread.sleep`.

## 2. Lifecycle Map to Remember

The diagram models the order of major milestones; internal callbacks within the same phase and context hierarchies may introduce specific details.

~~~text
SpringApplication.run()
    |
    +-- ApplicationStartingEvent
    |
    +-- Prepare Environment
    |     +-- EnvironmentPostProcessor / Config Data
    |     +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Create ApplicationContext
    |     +-- ApplicationContextInitializer
    |     +-- ApplicationContextInitializedEvent
    |
    +-- Load bean definitions
    |     +-- ApplicationPreparedEvent
    |
    +-- Refresh ApplicationContext
    |     +-- BeanDefinitionRegistryPostProcessor
    |     +-- BeanFactoryPostProcessor
    |     +-- Register BeanPostProcessors
    |     +-- Instantiate non-lazy singleton beans
    |     |     +-- Constructor/injection
    |     |     +-- @PostConstruct and init callbacks
    |     |     +-- BeanPostProcessor callbacks
    |     +-- SmartInitializingSingleton
    |     +-- SmartLifecycle auto-start
    |     +-- ContextRefreshedEvent
    |     +-- WebServerInitializedEvent when relevant
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- ApplicationRunner / CommandLineRunner
    |     +-- synchronous mandatory checks
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run returns
    |
    +-- Runtime: requests / jobs / messages
    |
    +-- ApplicationContext.close / normal JVM shutdown
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop, ordered phases
          +-- @PreDestroy, DisposableBean, destroyMethod
~~~

There are two special constraints:

- **Environment and Config Data:** EnvironmentPostProcessors and event listeners have ordering. A listener running too early on ApplicationEnvironmentPreparedEvent may observe Environment before other configuration processors have finished. Do not assume every listener on the same event sees an identical set of PropertySources.
- **Ready and availability:** Spring Boot 3.3 publishes **ApplicationStartedEvent after refresh but before runners**, then **ApplicationReadyEvent after runners**. On the normal success flow, **ReadinessState.ACCEPTING_TRAFFIC** is published after ReadyEvent. The server port may open before these milestones; socket listening does not equal routing readiness.

## 3. Extension Point Selection Matrix Across Three Axes

| Extension Point | Timing | Can Depend On | Completion Requirement / Best-Fit Purpose |
| --- | --- | --- | --- |
| **BootstrapRegistryInitializer** | Very early bootstrap | BootstrapRegistry, bootstrap helpers | Synchronous: set up infrastructure serving Config Data/startup |
| **ApplicationStartingEvent** | Start of run, before full Environment | Application and startup args from event | Ultra-early observation/tracing; no beans |
| **EnvironmentPostProcessor** | Preparing Environment before context | ConfigurableEnvironment, SpringApplication | Synchronous: add/edit PropertySources and config sources |
| **ApplicationEnvironmentPreparedEvent** | Environment published before context | Environment in event; no app beans yet | Early listener; pay attention to ordering with Config Data |
| **ApplicationContextInitializer** | After context creation, before loading bean definitions | ConfigurableApplicationContext, Environment | Synchronous: customize context/PropertySources |
| **ApplicationContextInitializedEvent** | After initializers, before definitions | Context, Environment | Observe initialized context |
| **ApplicationPreparedEvent** | Definitions loaded, before refresh | Context and metadata | Observe prepared step; no runtime beans yet |
| **BeanDefinitionRegistryPostProcessor** | During refresh, before regular beans | BeanDefinitionRegistry | Add/modify bean definitions |
| **BeanFactoryPostProcessor** | Before regular bean instantiation | ConfigurableListableBeanFactory, bean metadata | Modify/read metadata; avoid calling business getBean |
| **BeanPostProcessor** | Per bean being initialized | Bean object, beanName | Wrap/proxy or process bean instances |
| **Constructor / @PostConstruct** | When the bean itself is initialized | Dependencies injected into that bean | Synchronous bean-local state/resource initialization |
| **SmartInitializingSingleton** | End of regular singleton pre-instantiation | Regular eager singletons | Verify after eager beans; does not guarantee lazy beans |
| **SmartLifecycle.start()** | During refresh/start lifecycle, by phase | Managed beans and dependencies | Start long-running components; start completion needs its own contract |
| **ContextRefreshedEvent** | Context has refreshed | Context, regular bean graph | Observe refresh; no guarantee runners finished |
| **WebServerInitializedEvent** | Embedded web server initialized | WebServer and actual port | Know port/server; does not equal readiness |
| **ApplicationStartedEvent** | After refresh, before runners | Beans/context after refresh | Observe started; not yet Ready |
| **ApplicationRunner / CommandLineRunner** | After Started, before Ready | Services, repositories, bean dependencies | **Run synchronously and complete/throw before readiness** |
| **ApplicationReadyEvent** | After runners | Bean graph and startup finished | Post-startup notification; does not await async tasks |
| **AvailabilityChangeEvent** | When liveness/readiness state changes | ApplicationAvailability/state | Coordinate traffic eligibility |
| **ContextClosedEvent** | Context begins closing | Context/managed beans transitioning to shutdown | Signals shutdown start; does not prove cleanup finished |
| **SmartLifecycle.stop(Runnable)** | During shutdown phases | Remaining compatible components/dependencies | Ordered stopping; callback after stopping completes |
| **@PreDestroy / destroyMethod** | Bean destruction | Bean-owned resources | Close resources; do not block indefinitely |

**Read the last column before choosing:** If a check **must complete before readiness**, a synchronous ApplicationRunner is usually the clearest choice. If a daemon consumer must **stop and signal completion**, SmartLifecycle.stop(callback) fits. If you only need to alter bean blueprints, choose BeanDefinitionRegistryPostProcessor/BeanFactoryPostProcessor rather than instantiating real beans prematurely.

### 3.1. Limitations Table: What Must Not Be Assumed?

| Inside Extension Point | Cannot Yet Assume |
| --- | --- |
| EnvironmentPostProcessor | `@Autowired` business services or datasource exist |
| ApplicationContextInitializer | Bean definitions and business singletons are ready |
| BeanFactoryPostProcessor | Services can be fetched via `getBean` without breaking lifecycle |
| BeanPostProcessor | All other beans are initialized and auto-proxied |
| `@PostConstruct` | All singletons are created or runners have executed |
| SmartInitializingSingleton | Lazy singletons are created or external services are healthy |
| SmartLifecycle.start | ApplicationRunner startup gates have finished |
| ContextRefreshedEvent | ApplicationReadyEvent has occurred |
| ApplicationStartedEvent | Runners have finished |
| WebServerInitializedEvent | Readiness is ACCEPTING_TRAFFIC |
| ApplicationReadyEvent | All `@Async`/background tasks have finished |
| ContextClosedEvent | SmartLifecycle.stop and `@PreDestroy` have finished |
| `@PreDestroy` | SIGKILL/crash will still invoke cleanup |

An API named **Ready** does not guarantee all background workers are done. An API named **Initialized** does not guarantee the entire container or web gateway is ready.

## 4. Practical Decision Tree

~~~text
New requirement
    |
    +-- Need to configure config sources before beans exist?
    |      +-- Bootstrap helper -> BootstrapRegistryInitializer
    |      +-- PropertySource/config loader -> EnvironmentPostProcessor
    |
    +-- Context exists, bean definitions not loaded yet?
    |      +-- Customize context -> ApplicationContextInitializer
    |
    +-- Need to modify bean metadata?
    |      +-- Add/remove definitions -> BeanDefinitionRegistryPostProcessor
    |      +-- Modify registered metadata -> BeanFactoryPostProcessor
    |
    +-- Need to intercept each bean instance?
    |      +-- Wrapping/proxy -> BeanPostProcessor
    |      +-- Bean-local init -> @PostConstruct
    |
    +-- Need milestone after eager singleton creation?
    |      +-- SmartInitializingSingleton
    |
    +-- Need to start/stop long-running component?
    |      +-- SmartLifecycle start/stop/callback
    |
    +-- Need to finish critical setup before Ready?
    |      +-- ApplicationRunner / CommandLineRunner
    |             +-- await result synchronously, bounded
    |             +-- throw if prerequisites fail
    |
    +-- Only need notification after startup?
    |      +-- ApplicationReadyEvent
    |
    +-- Need to manage traffic when dependency state changes?
    |      +-- Readiness / ApplicationAvailability / HealthIndicator
    |
    +-- On shutdown?
           +-- Stop intake, drain async -> SmartLifecycle.stop(callback)
           +-- Close bean resources -> @PreDestroy / destroyMethod
~~~

These are **default selection rules**, not a reason to write custom SPIs when Spring already provides a better specialized abstraction. For example, for database schema migrations, use Flyway/Liquibase integration instead of creating a custom BeanPostProcessor just to run SQL.

## 5. Completion Gauge: "Invoked" Does Not Mean "Finished"

A callback may be synchronous yet merely submit an async task and return.

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(this::loadRequiredCache);
    // Runner returned, yet cache may not be finished.
}
~~~

This is an illustrative snippet with app-declared executor/loadRequiredCache. Spring Boot waits for **`run()`** to complete, **not automatically for tasks submitted by `run()`**.

Therefore you cannot call the snippet above a valid startup gate when the cache is required before readiness. You must:

- Run bounded logic synchronously inside the runner, **or**
- Await real completion via `Future.get(timeout)`, `CompletableFuture.get(timeout)`, or `CountDownLatch.await(timeout)` with error handling **before returning**.
- Throw an exception if mandatory conditions are not met; never log an error and silently proceed to ready.

### 5.1. Four Levels of Completion

| Level | What It Proves | What Cannot Be Inferred |
| --- | --- | --- |
| **REGISTERED** | Callback/bean definition was registered | Bean was created or task ran |
| **STARTED** | Task entered execution logic | Job has completed |
| **COMPLETED** | Future/callback recorded task termination | Side effects committed, if API doesn't guarantee it |
| **CLEANED_UP** | Component/resource closed per contract | JVM will survive SIGKILL |

For a background consumer, **`start()` returning** may only prove the consumer received the start command. If you must wait until a broker subscription is truly ready, the component needs **a dedicated signal** or integration with an appropriate readiness state.

### 5.2. When Does `ApplicationRunner` Genuinely Gate Ready?

~~~text
ApplicationStartedEvent
      |
ApplicationRunner
      |-- verify configuration
      |-- verify critical external service (bounded timeout)
      |-- Future.get(timeout) if there is a mandatory async task
      |-- return success or throw
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Results must be observed inside the runner itself before returning. For remote checks, set connect/read timeouts, bounded retries, and distinguish critical vs. optional backends. A remote check succeeding at startup does not guarantee it won't fail later; runtime still needs circuit breakers/retries/fallbacks.

### 5.3. `SmartLifecycle.stop` Callback Must Reflect Real Stopping

~~~java
@Override
public void stop(Runnable callback) {
    CompletableFuture.runAsync(this::drainAndClose)
            .whenComplete((unused, error) -> {
                if (error != null) {
                    recordStopError(error);
                }
                callback.run();
            });
}
~~~

This is a conceptual snippet; `drainAndClose` and `recordStopError` are application-implemented methods. If `drainAndClose` submits a task and returns immediately, the callback still fires too early. **`SmartLifecycle.stop(Runnable)`** must invoke the callback after the component has stopped per contract. If the callback is never invoked, `LifecycleProcessor` may wait until the shutdown phase timeout expires.

Use bounded draining, error reporting, and no unbounded blocking. When stopping fails, do not falsely report completion; define explicit failed-stop state and final cleanup.

### 5.4. Event Listeners Are Not Necessarily Barriers

By default, Spring application events are usually dispatched synchronously, yet behavior changes when configuring an asynchronous multicaster, `@Async` listeners, or error handlers.

**Do not choose an `@Async` listener on `ApplicationReadyEvent` as a mandatory step before readiness.** Publishing the event may finish while background tasks are still running. Use a runner or an explicit gate.

## 6. Before the Context: `BootstrapRegistryInitializer` and `EnvironmentPostProcessor`

### 6.1. `BootstrapRegistryInitializer`

An integration may need a credentials provider, bootstrap connection, or helper used to **load Config Data itself**. It cannot wait for a service bean because the container has not created beans yet.

In that case, **`BootstrapRegistryInitializer`** is an extension point designed for bootstrap infrastructure. This is typically a library/infrastructure responsibility, not a default vehicle for running arbitrary business logic.

An illustrative interface method:

~~~java
@Override
public void initialize(BootstrapRegistry registry) {
    registry.registerIfAbsent(
            BootstrapHelper.class,
            context -> new BootstrapHelper());
}
~~~

The snippet requires a `BootstrapHelper` class and corresponding imports. Registering the initializer must follow Spring Boot's integration mechanism; do not treat `@Component` scanning as an early bootstrap mechanism.

### 6.2. `EnvironmentPostProcessor`: Configuration Before the Bean Graph

An `EnvironmentPostProcessor` can add PropertySources with appropriate precedence. Standalone Java 17+ class example:

~~~java
package com.example.extension;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class FallbackEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "extensionDefaults",
                        Map.of("demo.region", "local")));
    }
}
~~~

Register via **META-INF/spring.factories** if you want Boot to discover it:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.extension.FallbackEnvironmentPostProcessor
~~~

- **`addLast`** serves as a fallback, avoiding overriding higher-precedence user configuration.
- **`Ordered`** controls ordering relative to other `EnvironmentPostProcessor`s. Config Data also participates in preparing Environment, so never assume all sources have loaded before a callback of arbitrary order.
- This is not the place to `@Autowired` repositories/services; the bean graph is not ready yet.

### 6.3. `ApplicationEnvironmentPreparedEvent` Is Not Caught by Regular `@Component`

This event fires before application beans are created. To receive it, register early:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                event -> System.out.println("Environment available"));
app.run(args);
~~~

This snippet requires `MyApplication`, imports, and `args`. A listener marked `@Component`/`@EventListener` cannot be expected to retroactively receive an early event published before the bean existed.

### 6.4. `ApplicationContextInitializer`: Context Exists, Service Beans Do Not

Initializers suit adjusting Environment, context ID, or property sources before bean definitions are loaded.

~~~java
application.addInitializers(context -> {
    context.getEnvironment().getPropertySources().addLast(
            new MapPropertySource(
                    "demoDefaults",
                    Map.of("demo.name", "fallback")));
});
~~~

This is a snippet; a real project needs `SpringApplication`, imports, and the source map. **Having a context object does not mean `context.getBean(OrderService.class)` is valid yet.**

If you want to modify logging properties from a custom source, pay close attention to timing: an `@PropertySource` loaded during refresh can be **too late** for certain `logging.*` or `spring.main.*` properties consumed earlier. You cannot use ReadyEvent to "retroactively apply" a setting already read earlier.

## 7. When the Container Processes Metadata and Bean Instances

### 7.1. `BeanDefinitionRegistryPostProcessor`

To register additional `BeanDefinition`s before Spring instantiates beans, use `BeanDefinitionRegistryPostProcessor` or an appropriate registrar/import SPI.

~~~java
@Override
public void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry) {

    if (!registry.containsBeanDefinition("featureMarker")) {
        registry.registerBeanDefinition(
                "featureMarker",
                new RootBeanDefinition(FeatureMarker.class));
    }
}
~~~

This code is an illustrative method, not a standalone class: you need a class implementing `BeanDefinitionRegistryPostProcessor`, `postProcessBeanFactory`, imports, and `FeatureMarker`. It **registers metadata**, rather than calling `new` on a service and bypassing lifecycle.

### 7.2. `BeanFactoryPostProcessor`

`BeanFactoryPostProcessor` operates on configuration metadata, typically editing property values, scopes, or definitions before regular bean creation.

~~~java
@Bean
static BeanFactoryPostProcessor metadataCount() {
    return factory -> System.out.println(
            "BFPP | definitions=" + factory.getBeanDefinitionCount());
}
~~~

This is a snippet for an `@Configuration`. **`static @Bean`** avoids instantiating the configuration instance prematurely. Avoid calling `beanFactory.getBean("businessService")` from a BFPP: it can cause premature instantiation and bypass part of AOP/`BeanPostProcessor`s.

### 7.3. `BeanPostProcessor`

`BeanPostProcessor` receives each instance before/after initialization. It is meant for wrapping/proxying or framework instrumentation; **not as a callback after full app startup**.

~~~java
@Bean
static BeanPostProcessor traceBeans() {
    return new BeanPostProcessor() {

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if (bean instanceof MyTrackedType) {
                System.out.println("BPP | " + beanName);
            }
            return bean;
        }
    };
}
~~~

This snippet requires a `MyTrackedType` and imports. `BeanPostProcessor`s and their very early dependencies may **not be fully auto-proxied**. When declaring a BPP via a `@Bean` method, make it `static` with minimal dependencies whenever possible.

### 7.4. `@PostConstruct`: Local Initialization of One Bean

When `@PostConstruct` runs, injection for that bean itself has happened, yet:

- There is no guarantee all other beans have been created.
- There is no guarantee `ApplicationRunner` has run.
- You should not perform heavy external I/O merely because the method runs at init.
- Calls like `this.someAsyncMethod()` or `this.transactionalMethod()` may bypass the Spring proxy, especially on self-invocation.

Choose `@PostConstruct` for **bean-owned** state/resources; provide an appropriate `@PreDestroy`/`destroyMethod`.

### 7.5. `SmartInitializingSingleton`

`SmartInitializingSingleton.afterSingletonsInstantiated` runs at the end of pre-instantiation for regular **non-lazy** singletons. It fits when a bean needs to validate or aggregate after typical eager singletons have been created.

It **does not prove lazy singletons have been created**, does not replace `ApplicationRunner`, and does not manage stop phases. If the object is truly a long-running worker, choose `SmartLifecycle`.

## 8. After Refresh: Started, Runners, Ready, and Readiness

### 8.1. `ContextRefreshedEvent`

`ContextRefreshedEvent` is a framework milestone after context refresh. An application with multiple contexts may see event propagation from child to parent. Listeners targeting a specific context should compare the event's context when needed.

Do not equate `ContextRefreshedEvent` with runners having finished, because runners run after refresh.

### 8.2. `WebServerInitializedEvent`

When using `server.port=0`, `WebServerInitializedEvent` exposes the actual embedded server port. This is not a guarantee that a load balancer is routing traffic to the instance, because runners/ready/availability may still follow afterward.

### 8.3. `ApplicationStartedEvent`

`ApplicationStartedEvent` arrives after refresh and before `ApplicationRunner`/`CommandLineRunner`. It can be used to observe that the container has started, yet must not be used to declare critical startup checks succeeded.

### 8.4. `ApplicationRunner` and `CommandLineRunner`

Both interfaces run before Ready; they differ mainly in input argument types:

- `ApplicationRunner` uses `ApplicationArguments`.
- `CommandLineRunner` receives `String... args`.

With multiple runners, `Ordered`/`@Order` can order them per Boot's contract. However, **`@Order` only orders `run` invocations**, not awaiting Futures spawned internally by a runner.

### 8.5. `ApplicationReadyEvent` and `ApplicationAvailability`

`ApplicationReadyEvent` is published after runners on the success path. `ReadinessState.ACCEPTING_TRAFFIC` follows afterward. If a Ready listener sends an optional notification and fails, isolate its policy so a side task does not trigger cluster restarts.

For dynamic critical dependencies, health/readiness must reflect ongoing ability to serve and runtime error handling; a passing startup probe does not guarantee a remote service stays online forever.

## 9. Stopping the Application: Completion at Shutdown

### 9.1. `ContextClosedEvent` Is the Starting Point

`ContextClosedEvent` is published when the context begins closing. It can update metrics or stop generating new work, yet **does not prove all components and resources have stopped**.

### 9.2. `SmartLifecycle.start` / `stop` and Phases

`SmartLifecycle` auto-starts per `isAutoStartup` and the lifecycle processor. Start phases run from **lowest to highest**, and stop phases run in **reverse**. When `depends-on` relationships exist, the dependency graph can override phase order.

**`SmartLifecycle.stop(Runnable callback)`** must invoke the callback **after the component has actually stopped**. Never call it right after submitting a drain command, and never omit the callback so shutdown stalls until the phase timeout expires.

If a component must start accepting work only after a startup gate in `ApplicationRunner`, note that `SmartLifecycle` auto-start during refresh runs **before runners**. In that case, set `isAutoStartup=false` or use an explicit gate so the consumer does not accept work too early.

### 9.3. `@PreDestroy` and `destroyMethod`

These close files, sockets, caches, executors, connection pools, or unregister bean-managed callbacks. If a task is active, `shutdown()` does not always mean the task finished; use bounded `awaitTermination`/interrupts per policy.

Never wait infinitely inside `@PreDestroy`. Never rely on Java cleanup on SIGKILL/crashes. A resource may get cleaned up twice via multiple mechanisms; `close` should be idempotent or have clear single ownership.

### 9.4. Web Graceful Shutdown Differs from Background Worker Drain

In Spring Boot 3.3:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

lets the embedded web server drain in-flight HTTP requests when the context closes. However, it does not automatically wait for arbitrary `@Async`/`@Scheduled` tasks, message consumers, or long-lived WebSocket streams. Background components need their own lifecycles, and phase budgets must fit within container termination grace periods.

## 10. Maven/Java 17+ Demo Choosing One Right Hook per Job

The lab includes:

| Need | API Used |
| --- | --- |
| Early notification | `ApplicationEnvironmentPreparedEvent` listener registered before run |
| Adding fallback config | `ApplicationContextInitializer` + `MapPropertySource.addLast` |
| Observing metadata | Static `@Bean BeanFactoryPostProcessor` |
| Observing a bean instance | Static `@Bean BeanPostProcessor` |
| Local state init | `@PostConstruct` |
| After eager singletons | `SmartInitializingSingleton` |
| Managed long-running lifecycle | `SmartLifecycle` |
| Mandatory work gate | Synchronous `ApplicationRunner` |
| Observing started/ready | `@EventListener` `ApplicationStartedEvent` and `ApplicationReadyEvent` |
| Closing context and resources | `ContextClosedEvent`, `SmartLifecycle.stop`, `@PreDestroy` |

The application is a **non-web CLI** so milestone logs are clear. When `SpringApplication.run` completes, `main` proactively closes the context via `try-with-resources`.

### 10.1. Structure

~~~text
lifecycle-choice-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/choice/LifecycleChoiceApplication.java
  src/test/java/com/example/choice/LifecycleChoiceApplicationTest.java
~~~

### 10.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>lifecycle-choice-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. `application.properties`

~~~properties
demo.name=from-file
demo.fail-on-startup=false
spring.main.web-application-type=none
~~~

There is no HTTP server. CLI arguments can override file configuration via **`--demo.name=from-cli`** per default property precedence.

### 10.4. Complete Java Application

Create **src/main/java/com/example/choice/LifecycleChoiceApplication.java**:

~~~java
package com.example.choice;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.validation.constraints.NotBlank;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.MapPropertySource;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication(proxyBeanMethods = false)
@EnableConfigurationProperties(
        LifecycleChoiceApplication.DemoOptions.class)
public class LifecycleChoiceApplication {

    public static void main(String[] args) {
        SpringApplication app = newApplication();

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "MAIN | run returned, now closing context");
        }
    }

    static SpringApplication newApplication() {
        SpringApplication app =
                new SpringApplication(LifecycleChoiceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> System.out.println(
                                "EARLY | environment prepared"));

        app.addInitializers(
                (ApplicationContextInitializer<ConfigurableApplicationContext>)
                        context -> {
                            context.getEnvironment()
                                    .getPropertySources()
                                    .addLast(new MapPropertySource(
                                            "demoFallback",
                                            Map.of("demo.name", "fallback")));

                            System.out.println(
                                    "INITIALIZER | fallback registered");
                        });

        return app;
    }

    @Bean
    static BeanFactoryPostProcessor inspectMetadata() {
        return beanFactory -> System.out.println(
                "BFPP | definitions=" +
                beanFactory.getBeanDefinitionCount());
    }

    @Bean
    static BeanPostProcessor observeResource() {
        return new BeanPostProcessor() {

            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String beanName) {

                if (bean instanceof DemoResource) {
                    System.out.println("BPP | resource initialized");
                }
                return bean;
            }
        };
    }

    @Bean
    ApplicationRunner mandatoryGate(
            DemoOptions options,
            DemoResource resource) {

        return args -> {
            System.out.println("RUNNER | required check started");

            if (options.failOnStartup()) {
                throw new IllegalStateException(
                        "Required startup check failed");
            }

            resource.markGatePassed();
            System.out.println("RUNNER | required check completed");
        };
    }

    @Validated
    @ConfigurationProperties(prefix = "demo")
    public record DemoOptions(
            @NotBlank String name,
            boolean failOnStartup) {
    }
}

@Component
class DemoResource implements SmartInitializingSingleton {

    private final LifecycleChoiceApplication.DemoOptions options;
    private final AtomicBoolean gatePassed = new AtomicBoolean();

    DemoResource(
            LifecycleChoiceApplication.DemoOptions options) {
        this.options = options;
    }

    @PostConstruct
    void initialize() {
        System.out.println(
                "BEAN | name=" + options.name());
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("SINGLETONS | eager beans ready");
    }

    void markGatePassed() {
        gatePassed.set(true);
    }

    boolean isGatePassed() {
        return gatePassed.get();
    }

    @EventListener
    void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED | before runners");
    }

    @EventListener
    void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "READY | gatePassed=" + gatePassed.get());
    }

    @EventListener
    void onClosing(ContextClosedEvent event) {
        System.out.println("CLOSING | context closing");
    }

    @PreDestroy
    void destroy() {
        System.out.println("DESTROY | DemoResource");
    }
}

@Component
class DemoLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("LIFECYCLE | started");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
            System.out.println("LIFECYCLE | stopped");
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

### 10.5. Explanations and Limitations of the Demo

- **`@EnableConfigurationProperties`** registers nested record `DemoOptions`; `@NotBlank` is enforced thanks to the validation starter.
- **`newApplication()`** attaches the early listener/initializer before run. No `@Component` is expected to retroactively receive early events.
- **`MapPropertySource.addLast`** provides a fallback without overriding `application.properties`.
- **static `@Bean` BFPP and BPP** avoid instantiating the `@Configuration` class prematurely.
- BFPP merely observes definition count; BPP observes `DemoResource` after initialization and returns the same object.
- **`@PostConstruct`** only uses injected values; **`SmartInitializingSingleton`** observes the eager singleton milestone.
- **`SmartLifecycle`** auto-starts during refresh and stops when `context.close()` runs. The callback runs in `finally` after the example sets `running=false`; real apps must finish stopping real resources before invoking the callback.
- **`ApplicationRunner`** is a synchronous gate: if `failOnStartup=true` it throws; if false it marks the gate passed.
- **`@EventListener(ApplicationReadyEvent)`** observes `gatePassed=true` after the runner succeeds.
- **`Try-with-resources`** calls close after `run` to demonstrate shutdown, unsuitable right after `run` for a long-running web service.
- The program spawns no long-lived background threads, so `main` exiting and closing the context is intentional.

### 10.6. Build and Run

~~~bash
java -version
mvn -q -DskipTests package
java -jar target/lifecycle-choice-demo-1.0.0.jar
~~~

**Java 17+ and compatible Maven are required.** Spring Boot may print its own logs, so examine only the example's markers. By the lifecycle contract, key markers appear in this general order:

~~~text
EARLY | environment prepared
INITIALIZER | fallback registered
BFPP | definitions=...
BEAN | name=from-file
BPP | resource initialized
SINGLETONS | eager beans ready
LIFECYCLE | started
STARTED | before runners
RUNNER | required check started
RUNNER | required check completed
READY | gatePassed=true
MAIN | run returned, now closing context
CLOSING | context closing
LIFECYCLE | stopped
DESTROY | DemoResource
~~~

The ellipsis on definition count is not a fixed numeric output; the exact count depends on Spring Boot auto-configuration. **Do not assert stdout verbatim** because framework logs may interleave.

The two key markers proving the runner gate are:

~~~text
RUNNER | required check completed
READY | gatePassed=true
~~~

First must come completion of the mandatory step; only then comes ReadyEvent.

### 10.7. CLI Override and Failure Path

Override the name:

~~~bash
java -jar target/lifecycle-choice-demo-1.0.0.jar \
  --demo.name=from-cli
~~~

The bean init line reads:

~~~text
BEAN | name=from-cli
~~~

Make the runner fail:

~~~bash
java -jar target/lifecycle-choice-demo-1.0.0.jar \
  --demo.fail-on-startup=true
~~~

Runner output reaches:

~~~text
RUNNER | required check started
~~~

followed by throwing `IllegalStateException` with message **Required startup check failed**. The successful startup path **never emits `READY | gatePassed=true`**. Cleanup callbacks may still run while Spring handles the failure; do not assume one identical final stack trace/log order across every failure path.

## 11. JUnit 5: Verifying Real Order Without Sleep

Create **src/test/java/com/example/choice/LifecycleChoiceApplicationTest.java**:

~~~java
package com.example.choice;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LifecycleChoiceApplicationTest {

    @Test
    void startedThenReadyAfterRequiredRunner() {
        List<String> events = new CopyOnWriteArrayList<>();

        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        app.addListeners(
                (ApplicationListener<ApplicationStartedEvent>)
                        event -> events.add("STARTED"));

        app.addListeners(
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> events.add("READY"));

        try (ConfigurableApplicationContext context =
                     app.run(
                             "--demo.name=test",
                             "--demo.fail-on-startup=false")) {

            assertEquals(List.of("STARTED", "READY"), events);
            assertTrue(
                    context.getBean(DemoResource.class)
                            .isGatePassed());
        }
    }

    @Test
    void failedRunnerNeverPublishesSuccessfulReady() {
        AtomicBoolean ready = new AtomicBoolean();
        AtomicBoolean failed = new AtomicBoolean();

        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        app.addListeners(
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> ready.set(true));

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>)
                        event -> failed.set(true));

        assertThrows(RuntimeException.class,
                () -> app.run(
                        "--demo.name=test",
                        "--demo.fail-on-startup=true"));

        assertFalse(ready.get());
        assertTrue(failed.get());
    }

    @Test
    void configDataOverridesInitializerFallback() {
        SpringApplication app =
                LifecycleChoiceApplication.newApplication();

        try (ConfigurableApplicationContext context =
                     app.run("--demo.fail-on-startup=false")) {

            assertEquals(
                    "from-file",
                    context.getEnvironment()
                            .getProperty("demo.name"));
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**What the tests verify:**

1. **Started precedes Ready**, and by Ready, the startup runner has completed the gate step.
2. A failing runner never produces a **successful `ApplicationReadyEvent`**, while Spring emits `ApplicationFailedEvent` on the startup error path.
3. Property **demo.name=from-file** beats the initializer's fallback, because the fallback was added with low precedence.

These tests use a real `SpringApplication`, not `ApplicationContextRunner` mocking only part of lifecycle events. **`SpringApplication.run` is a synchronous call**, so listeners have finished recording events when `run` returns cleanly; no arbitrary millisecond sleep is needed.

**Limitation:** this does not yet test a real remote API, container SIGTERM shutdown, or load balancer readiness. Those layers need dedicated integration/process-level tests.

## 12. Real-World Scenario Table: Choosing the Right API and Completion

| Scenario | Extension Point to Choose | Rationale and Conditions |
| --- | --- | --- |
| Load low-priority default config | `EnvironmentPostProcessor` / `ContextInitializer` | Needs Environment, no beans; use `addLast` |
| Configure secret source for Config Data | `BootstrapRegistryInitializer` or config SPI integration | Must run before runtime bean graph |
| Register bean definitions from feature registry | `BeanDefinitionRegistryPostProcessor` | Alter blueprints before instantiation |
| Edit bean property metadata | `BeanFactoryPostProcessor` | Avoid creating business services early |
| Wrap a group of beans for metrics | `BeanPostProcessor` or AOP | Per-instance instrumentation |
| Validate a bean's own parameters | `@PostConstruct` / `initMethod` | Bean-local invariant; add `@PreDestroy` if holding resources |
| Aggregate state after eager singleton phase | `SmartInitializingSingleton` | Does not unintentionally make lazy beans eager |
| Log that context refreshed | `ContextRefreshedEvent` | Do not assume runners finished |
| Inspect random embedded port | `WebServerInitializedEvent` | ServerInitialized differs from Readiness |
| Verify mandatory schema before traffic | Flyway/Liquibase or synchronous custom Runner | Clear gate; DB dependencies already injected |
| Check critical remote before ready | `ApplicationRunner` with timeouts, fail-fast policy | Wait for real completion; coordinate with readiness |
| Start Kafka consumer needing ordered stop | `SmartLifecycle` | Phased start/stop/callback |
| Send optional ready notification | `ApplicationReadyEvent` | Never turn async notifications into startup gates |
| Mark unready when remote fails at runtime | `ApplicationAvailability` / `HealthIndicator` | Dynamic state, not just a startup event |
| Stop new HTTP and drain active requests | Graceful web shutdown | Combine load balancer/readiness, not just `@PreDestroy` |
| Stop background jobs and await bounded acks | `SmartLifecycle.stop(Runnable)` | Callback after real stop; explicit deadline |
| Close unmanaged sockets/files/executors | `@PreDestroy` / `destroyMethod` | Clear ownership and idempotent cleanup |
| Return process exit code for batch | `ExitCodeGenerator` / `SpringApplication.exit` | CLI process semantics, not web readiness |

### 12.1. Database Startup Tasks

If schema migration is genuinely required, prefer framework integrations like Flyway/Liquibase. If a custom invariant check must run after repositories/DB are ready, a synchronous `ApplicationRunner` fits well.

Do not invoke repositories inside `EnvironmentPostProcessor` or BFPP. Do not submit a migration task inside `@Async` and let the runner return, because ReadyEvent could fire before commit.

### 12.2. Cache Warm-Up

- **Small, bean-internal cache:** `@PostConstruct` may be appropriate.
- **Multi-service cache mandatory before traffic:** synchronous Runner or awaiting a Future inside Runner.
- **Optional cache warmed gradually:** `ApplicationReadyEvent` or managed background component with fallback.
- **Continuously refreshed cache:** `SmartLifecycle`/`@Scheduled` or dedicated infrastructure with clear shutdown policies.

Never pick a hook solely from the noun "cache"; know when it is used and whether it is mandatory.

### 12.3. Consumers That Must Start After a Gate

`SmartLifecycle` auto-start normally runs during refresh **before runners**. If a consumer must not pull messages until a runner finishes checking a remote service, you cannot assume a high phase makes it start after `ApplicationRunner`.

Set **`isAutoStartup=false`** and start it explicitly after the gate, or use a readiness/gate state inside the component depending on business needs. Never let a consumer process messages before mandatory system invariants hold.

### 12.4. Logging Properties from Custom Sources

An `@PropertySource` added only during context refresh may arrive too late to configure certain `logging.*` or `spring.main.*` properties already read earlier. Use `EnvironmentPostProcessor` or a Boot-supported configuration path with proper ordering.

Do not try to "fix" it via ReadyEvent or `@PostConstruct`, as earlier decisions cannot be retroactively applied.

### 12.5. Multi-Layer Cleanup

A web app may require:

- Readiness switching to refusing traffic.
- Embedded server gracefully draining HTTP requests.
- Consumers stopping new message intake.
- Consumers finishing in-flight jobs.
- Executors/datasources closing once no longer used.
- `@PreDestroy` releasing final resources.

Use proper phase/dependency ordering; never create a single `@PreDestroy` with an unbounded `Thread.sleep` to stall the entire process.

## 13. Ordering and Dependencies: Three Different Mechanisms

| Mechanism | What It Orders | What It Does Not Guarantee |
| --- | --- | --- |
| **`Ordered` / `@Order`** | Runners, listeners, processors within framework scope | Internal async tasks completed |
| **`@DependsOn`** | Bean creation/destruction dependencies | HTTP calls or jobs completed |
| **`SmartLifecycle.getPhase()`** | Start low-to-high, stop high-to-low | ReadyEvent or external readiness |
| **Default synchronous event dispatch** | Listeners called by publisher | If `@Async`/multicaster changes mode, no longer a completion barrier |
| **`Future`/`CompletionStage`** | Completion of a specific task | Bean definitions/ordering |

If a high-priority `@Order` runner merely submits a task and returns, a subsequent runner may still see unready data. **Order does not turn async into sync.**

If bean B depends on bean A, B initializes after A, yet `A.@PostConstruct` may have merely submitted a job; there is no guarantee that job finished. An explicit completion contract is needed.

## 14. Failure Policy: Fail-Fast or Degrade?

| Detection Milestone | Typical Outcome When Unhandled | Reasonable Choice |
| --- | --- | --- |
| Environment/config processing | Early startup failure | Fail-fast when required config source is invalid |
| ContextInitializer | Normal context creation halts | Fail-fast for context invariants |
| BFPP/BDRPP | Context refresh fails | Catch bad metadata; avoid network side effects |
| BPP / `@PostConstruct` | Bean creation/refresh fails | Bean invariants/initialization |
| SmartInitializingSingleton | Refresh fails | Eager singleton invariants |
| `SmartLifecycle.start` | Refresh/startup may fail | Control partial start and cleanup |
| `ApplicationRunner` | Startup fails after refresh, before Ready | Critical startup gate |
| `ApplicationReadyEvent` listener | Can affect run if synchronous listener throws | Avoid as gate; async work needs its own error policy |
| `SmartLifecycle.stop` | Error or timeout on shutdown | Report error, contractual callbacks, bounded cleanup |
| `@PreDestroy` | Error during destruction | Does not guarantee finishing all background tasks/resources |

Fail-fast makes sense when missing config or a critical remote outage breaks core requests. For optional remotes, degraded mode with monitoring may beat failing the entire system. Even after pre-ready checks succeed, runtime must still handle remote outages.

**A security note:** early callbacks may read secrets/credentials. Never log the entire Environment or expose unprotected `/env` or `/configprops` endpoints for debugging.

## 15. Testing at the Right Layer for Each Extension Point

### 15.1. Unit Tests

If logic simply selects config values, checks URI syntax, or calculates phases, pure Java unit tests usually suffice. No need to boot a full `SpringApplication`.

### 15.2. `ApplicationContextRunner`

When testing `@ConfigurationProperties` binding, auto-configuration conditions, or simple BFPP/BPP, `ApplicationContextRunner` builds a lightweight context and inspects dependency graphs easily.

However, **`ApplicationContextRunner` does not emit the entire `SpringApplication` event sequence by default**, so never use it alone to claim `ReadyEvent` fires at the right milestone.

### 15.3. `SpringApplication` Integration Tests

To verify Started → Runner → Ready and failure paths, use a real `SpringApplication.run`, registering listeners before run as in section 11. Never rely on `@Component` listeners registered after early events have passed.

### 15.4. Async Lifecycle Tests

For `SmartLifecycle.stop(Runnable)`, distinguish three signals:

~~~text
stopRequested
       |
       +-- draining
       |
stopCallbackCompleted
       |
ApplicationContext.close() returned
~~~

Use `CountDownLatch.await(timeout)` or `Future.get(timeout)` to await milestones, never fixed `Thread.sleep`. Tests must release gates in `finally` and clean up executors/threads if assertions fail.

### 15.5. Process-Level Tests

A context-closing test proves Spring lifecycle callbacks. It **does not by itself prove**:

- SIGTERM propagates cleanly through a container entrypoint.
- Kubernetes stops routing traffic in time.
- The web server gracefully drains HTTP requests over a real network.
- SIGKILL still runs `@PreDestroy` (not guaranteed).

Those requirements need integration/process/container tests in matching environments with clear overall deadlines.

## 16. Selection Exercises with Answers

**Exercise 1.** A library needs to add fallback properties without overriding `application.properties`.

**Answer:** A properly registered `EnvironmentPostProcessor` using a low-priority property source (`addLast`), or `ContextInitializer` for an application-specific case.

**Exercise 2.** Dynamically register a bean type from feature metadata before dependency injection.

**Answer:** `BeanDefinitionRegistryPostProcessor` or a specialized registrar/import SPI.

**Exercise 3.** Wrap beans implementing an interface for instrumentation.

**Answer:** `BeanPostProcessor` or an appropriate Spring AOP SPI; BFPP does not wrap runtime instances.

**Exercise 4.** Verify a mandatory payment gateway is online before readiness.

**Answer:** Synchronous Runner with bounded timeouts; throw on failure per policy. Runtime still needs timeouts/retries and readiness handling if the dependency fails post-startup.

**Exercise 5.** Stop a consumer, await acks, and invoke a callback after draining.

**Answer:** `SmartLifecycle.stop(Runnable)` with proper phase/depends-on and bounded stop.

**Exercise 6.** Send optional telemetry after the application finishes starting.

**Answer:** `ApplicationReadyEvent` listener or observability integration; do not treat async listeners as startup gates.

**Exercise 7.** Discover the embedded server port when `server.port=0`.

**Answer:** `WebServerInitializedEvent` or an appropriate test API. `ApplicationStartingEvent` is far too early.

**Exercise 8.** Confirm non-lazy singletons have been pre-instantiated.

**Answer:** `SmartInitializingSingleton`; do not assume lazy singletons exist.

**Exercise 9.** Close a custom executor created by a bean.

**Answer:** `@PreDestroy`/`destroyMethod` with bounded shutdown; if phase coordination and callbacks are needed, `SmartLifecycle`.

**Exercise 10.** Should mandatory migrations run inside a controller's `@PostConstruct`?

**Answer:** No. Prefer Flyway/Liquibase; if custom, use a synchronous startup gate after dependencies, not tied to controller initialization.

**Exercise 11.** Is a `SmartLifecycle` consumer guaranteed to start after runners?

**Answer:** No. Auto-start normally happens during refresh, before runners. Use `isAutoStartup=false` or policy-based gating.

**Exercise 12.** Does putting `@Order` on a runner calling an executor mean the cache is ready?

**Answer:** No. Order governs invocation order, not awaiting async completion.

**Exercise 13.** Can `ContextClosedEvent` be used to assert `@PreDestroy` has finished?

**Answer:** No. The event only marks that context closing has started; destruction occurs afterward on the normal path.

**Exercise 14.** Can `@Component @EventListener` reliably catch `ApplicationEnvironmentPreparedEvent`?

**Answer:** Not reliably, because the bean does not exist yet. Register an early listener before run or via `spring.factories`.

## 17. Common Selection Mistakes

### 17.1. Using `ApplicationReadyEvent` to Set Environment Properties Needed Before Bean Binding

Too late; properties may already have been consumed. Choose an earlier Environment hook.

### 17.2. Using `BeanFactoryPostProcessor` to Call a Repository

There is no stable bean graph yet, risking premature bean creation and bypassed post-processing.

### 17.3. Using `BeanPostProcessor` as an "After All Beans Are Done" Hook

It runs per instance. `SmartInitializingSingleton`, runners, or lifecycle events provide the proper milestone semantics.

### 17.4. Using `@PostConstruct` as a Global Custom Startup Task

Bean-local initialization differs from application readiness. For critical work needing all services, a runner is usually clearer.

### 17.5. Using `ApplicationStartedEvent` to Declare Startup Gates Complete

Started fires before runners. Do not infer mandatory runner steps have finished.

### 17.6. Using an `@Async` Ready Listener for Mandatory Work

An async listener may still be incomplete when readiness is published. Use a real completion gate.

### 17.7. Invoking `SmartLifecycle.stop` Callback Right After Requesting Drain

The context may close dependencies while the component still uses them. Fire the callback only after actual stopping.

### 17.8. Omitting the Callback and Letting the Lifecycle Processor Time Out

Shutdown drags out or appears hung. Design bounded stopping and clear callback semantics.

### 17.9. Assuming `@PreDestroy` Always Runs After SIGKILL

No. Hard kills prevent Java callbacks from finishing. Critical work needs persistence/recovery.

### 17.10. Using Unowned Static Global State

Context hierarchies/DevTools restarts can create multiple contexts in one JVM. Global state easily retains old classloaders and triggers duplicate callbacks.

### 17.11. Using `Thread.sleep` to Fix Races Between Runners and Background Workers

That only guesses scheduling; use Futures/latches/completion signals with timeouts.

### 17.12. Using One Default Policy for Every Remote Dependency

Critical and optional dependencies have different fail-fast/degrade policies. Never cause needless cluster-wide restarts when a secondary service blips.

## 18. Pre-Selection Checklist for Extension Points

- [ ] Documented exact required timing and completion conditions.
- [ ] Listed dependencies actually available at that milestone.
- [ ] Distinguished metadata from runtime bean instances.
- [ ] Early listeners registered before `SpringApplication.run`.
- [ ] PropertySource precedence/order chosen deliberately.
- [ ] No business beans fetched inside `EnvironmentPostProcessor`/Initializer/BFPP.
- [ ] BFPP/BPP `@Bean` methods marked `static` when appropriate to avoid eager configuration references.
- [ ] `@PostConstruct` manages only bean-local initialization.
- [ ] `SmartInitializingSingleton` not conflated with lazy beans or Ready.
- [ ] `SmartLifecycle` has clear start/stop policies and phases.
- [ ] Runners genuinely await critical tasks before returning.
- [ ] Async tasks have timeouts and cancellation/error handling if important.
- [ ] ReadyEvent treated solely as post-runner observation, not an async gate.
- [ ] Readiness distinguished from web server socket binding.
- [ ] `ContextClosedEvent` not treated as completed cleanup.
- [ ] `@PreDestroy`/`destroyMethod` have clear ownership and bounded cleanup.
- [ ] Understood differences between `@Order`, `@DependsOn`, and `getPhase`.
- [ ] Tests use events/completion signals instead of fixed sleeps.
- [ ] Integration tests cover both startup failure paths and shutdown.
- [ ] Container shutdown budgets aligned with lifecycle phases.
- [ ] Secrets redacted from logs/diagnostics.
- [ ] Specialized framework SPIs preferred over global custom hooks where available.

## 19. Self-Check Questions

**1. Can `EnvironmentPostProcessor` inject a JPA repository?**

**Answer:** No; application beans do not exist yet at that stage.

**2. When an initializer runs, are application bean definitions fully loaded?**

**Answer:** Not in the standard lifecycle; initializers run before definitions load.

**3. Should `BeanFactoryPostProcessor` work on metadata or instances?**

**Answer:** Metadata. `BeanPostProcessor` handles instances.

**4. Does `@PostConstruct` on one bean prove all singletons are created?**

**Answer:** No. `SmartInitializingSingleton` is the milestone after regular eager singleton pre-instantiation.

**5. Does `ApplicationStartedEvent` occur before or after runners?**

**Answer:** Before.

**6. Does `ApplicationReadyEvent` occur before or after runners?**

**Answer:** After, on the normal successful startup path.

**7. Once `ReadyEvent` fires, are all background tasks submitted by runners finished?**

**Answer:** No, unless the runner explicitly awaited them before returning.

**8. What order does `SmartLifecycle`'s `getPhase` control?**

**Answer:** Start low-to-high and stop in reverse; explicit dependencies may take precedence.

**9. Can `WebServerInitializedEvent` serve as proof of traffic readiness?**

**Answer:** No. The server can open a socket before runners and `ReadinessState`.

**10. Does `ContextClosedEvent` guarantee destroy callbacks have completed?**

**Answer:** No; the event signals the start of closing.

**11. When should `SmartLifecycle.stop(Runnable)` invoke its callback?**

**Answer:** After the component finishes stopping per contract; not immediately upon submitting a task.

**12. Does `@Order` make a Future from the first runner complete before the second runner?**

**Answer:** No, unless the first runner actively awaits completion.

**13. Is `@PreDestroy` enough for tasks that must never be lost on SIGKILL?**

**Answer:** No. Durable queues/checkpoints/transactions and recovery are required.

**14. When a remote serves only a secondary feature, should startup always fail?**

**Answer:** No. Consider degraded startup and runtime resilience per business needs.

## 20. Summary

Building a solid extension-point decision matrix requires combining **three axes**: when it is invoked, which dependencies are ready, and what completion guarantee Spring or the application must uphold.

- **Before beans:** `BootstrapRegistryInitializer`, `EnvironmentPostProcessor`, `ApplicationContextInitializer`.
- **During container refresh:** `BeanDefinitionRegistryPostProcessor`, `BeanFactoryPostProcessor`, `BeanPostProcessor`, `@PostConstruct`, `SmartInitializingSingleton`.
- **After refresh, before Ready:** `ApplicationStartedEvent` for observation; `ApplicationRunner`/`CommandLineRunner` for **synchronous mandatory startup work**.
- **After runners:** `ApplicationReadyEvent` and availability states.
- **Long-running components:** `SmartLifecycle` with phases and stop callbacks.
- **Shutdown/destroy:** `ContextClosedEvent` to know closing started; `SmartLifecycle.stop` to drain and `@PreDestroy`/`destroyMethod` for final release.

A sound design must answer: **when does the callback arrive, what dependencies exist, does it wait for completion, how do failures impact startup/readiness, and how does it stop**. Consult this matrix before adding any new hook to an application.

## 21. Official References

- Spring Boot 3.3 — SpringApplication Events, Runners, and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Customize Environment/ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3 — EnvironmentPostProcessor API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3 — ApplicationContextInitializedEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html
- Spring Framework 6.1 — BeanFactoryPostProcessor and BeanPostProcessor: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.1 — SmartInitializingSingleton: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework 6.1 — SmartLifecycle and callbacks: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Bean Lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html