# ConfigurableApplicationContext and Refresh Phases in Spring Framework

## 1. What is ApplicationContext, and why do we need ConfigurableApplicationContext?

In the Spring Core Container, **`ApplicationContext`** is the interface representing the container that already knows the bean definitions and provides beans, events, resources, message resolution, and environment information. Business code usually only needs this read-oriented interface or injects a specific dependency.

**`ConfigurableApplicationContext`** extends lifecycle management capabilities: configuring the context before startup, requesting `refresh()`, `start()`, `stop()`, `close()`, registering application listeners, shutdown hooks, and working with `ConfigurableEnvironment`. When building an application/framework or manually bootstrapping a Spring container, we use this management API.

Two familiar examples:
- `AnnotationConfigApplicationContext`: standalone container using `@Configuration`, `@Component`, and Java annotations; created via an empty constructor, `register(...)`, and then calling `refresh()`.
- `ClassPathXmlApplicationContext`: context reading bean definitions from XML on the classpath, with its own specific context-building mechanism. XML is not needed if a modern Java application uses annotation config.

Example of the difference at the interface level:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

void useBeans(ApplicationContext context) {
    Object service = context.getBean("someService"); // Look up existing bean.
}

void manageContext(ConfigurableApplicationContext context) {
    context.start(); // Lifecycle signal, does NOT replace refresh().
    context.stop();
    context.close(); // End context lifecycle.
}
```

This is a fragment illustrating the API, not a standalone Java program (methods must reside inside a class). In a Spring Boot-managed application, do not arbitrarily call `refresh()` or `close()` from an HTTP request: the framework typically bears responsibility for coordinating the overall lifecycle.

### States to distinguish

```text
CONSTRUCTED (not yet refreshed)
     |
     | register / scan / customize Environment / BeanFactoryPostProcessor
     v
refresh() running:
     prepare -> bean definitions -> processors -> infrastructure
               -> instantiate regular singletons -> finish refresh
     |
     v
ACTIVE / REFRESHED
     |                  |
     | start()/stop()   | getBean()/publishEvent()/application serving work
     | controls         |
     | Lifecycle beans  |
     +------------------+
     |
     v
close() / shutdown
     |
     v
CLOSED (resources released according to lifecycle)
```

`isActive()` indicates whether the context has been marked active and has not been closed; this flag is set from the **beginning** of `refresh()`, so it must not be used alone to prove that the entire application is ready. The concepts of "context finished refreshing", "Lifecycle component started", "server is accepting connections", and "external dependency is healthy" are different things.

## 2. Typical lifecycle of AnnotationConfigApplicationContext

There are two common initialization approaches:

**Approach 1 — constructor performs refresh immediately:**

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    MyService bean = context.getBean(MyService.class);
}
```

The constructor accepting configuration classes will register the class and **refresh the context** before returning. `AppConfig` and `MyService` in the fragment must be defined in the project.

**Approach 2 — explicitly separating the configuration phase:**

```java
try (var context = new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.getEnvironment().setActiveProfiles("dev");
    context.refresh();
    MyService bean = context.getBean(MyService.class);
}
```

This pattern allows modifying the environment configuration **before** `refresh()`. `register(AppConfig.class)` does not yet run the full bean lifecycle; it declares the input configuration. Only after `refresh()` do we have a container that has completed bootstrap. In practice, one should choose a clear configuration management mechanism and avoid changing active profiles late when bean definitions have already been processed.

With `AnnotationConfigApplicationContext`, the bean factory mechanism is `GenericApplicationContext`: **it can only be refreshed once** on the same instance. Calling `refresh()` a second time is not a way to "reload" the application from scratch; it can throw `IllegalStateException`. Some other implementations such as `ClassPathXmlApplicationContext`/`AbstractRefreshableApplicationContext` support repeated refreshes while the context is still open. Therefore, do not infer from the method name that every `ConfigurableApplicationContext` supports hot-reloading.

## 3. Complete list of main phases in refresh()

`AbstractApplicationContext.refresh()` is a template method shared across many context implementations. It ensures the steps of preparation, container configuration, singleton creation, event notification, and cleanup upon failure. This is the **conceptual order** of the core phases in Spring Framework 6.x; detailed implementation may vary between subclasses/versions.

```text
refresh()
  |
  +--  1. prepareRefresh()
  |       state, startup time, property sources, required properties
  |
  +--  2. obtainFreshBeanFactory()
  |       load/obtain BeanFactory and bean definitions
  |
  +--  3. prepareBeanFactory(beanFactory)
  |       standard resolvers, Aware, ApplicationContext integration
  |
  +--  4. postProcessBeanFactory(beanFactory)
  |       subclass hook (such as WebApplicationContext)
  |
  +--  5. invokeBeanFactoryPostProcessors(beanFactory)
  |       configure/transform bean definitions before creating regular beans
  |
  +--  6. registerBeanPostProcessors(beanFactory)
  |       register processors for each bean's lifecycle
  |
  +--  7. initMessageSource()
  |       internationalized message resolution
  |
  +--  8. initApplicationEventMulticaster()
  |       infrastructure for distributing application events
  |
  +--  9. onRefresh()
  |       subclass hook, e.g., some web contexts build web infrastructure
  |
  +-- 10. registerListeners()
  |       application listeners and early application events
  |
  +-- 11. finishBeanFactoryInitialization(beanFactory)
  |       prepare conversion service, preInstantiateSingletons()
  |       create regular singletons, initialization + corresponding callbacks
  |
  +-- 12. finishRefresh()
          clear caches / lifecycleProcessor.onRefresh()
          publish ContextRefreshedEvent
  |
  +-- refresh completed successfully
```

It is necessary to distinguish the **infrastructure registration milestone** from the **bean method execution milestone**. Registering `BeanPostProcessor` in step 6 does not mean all user beans have already been created. Regular singleton beans are created in step 11, when processors already have the chance to apply to each target's lifecycle.

### Quick reference table

| Phase | Main work | Observable consequence |
| --- | --- | --- |
| `prepareRefresh` | Mark startup, prepare property sources, validate required properties | Missing required config can cause refresh to fail |
| `obtainFreshBeanFactory` | Obtain or load BeanFactory/bean definitions | Configuration classes and bean definitions are managed by the container |
| `prepareBeanFactory` | Set up default infrastructure (class loader, expression resolver, resolvable dependencies, etc.) | Beans can receive certain `Aware` dependencies |
| `postProcessBeanFactory` | Hook for subclasses | Web contexts can add web environment support |
| `invokeBeanFactoryPostProcessors` | Run **bean definition** processors | `@Configuration`/`@Bean`, component scanning are processed with the proper mechanism |
| `registerBeanPostProcessors` | Register **bean instance** processors | Supports `@Autowired`, `@PostConstruct`, proxy/AOP as configured |
| `initMessageSource` | MessageSource | `getMessage(...)` is available according to context |
| `initApplicationEventMulticaster` | System for publishing/listening to events | Events have a distribution hub |
| `onRefresh` | Hook of the context implementation | Specialized contexts complete specific steps |
| `registerListeners` | Register listeners and publish appropriate early events | Listeners receive lifecycle events as supported |
| `finishBeanFactoryInitialization` | Create eager singletons, run initialization callbacks | Default singletons are initialized |
| `finishRefresh` | Conclude bootstrap, start appropriate auto-start Lifecycles, publish refresh event | `ContextRefreshedEvent` appears |

The method names above belong to the implementation mechanism of `AbstractApplicationContext`; they are not "12 methods that applications always call themselves". An application calls `refresh()` once, and Spring executes the algorithm itself. Do not manually call `protected` methods or attempt to change their order from business code.

## 4. Phases 1–4: preparing the environment and BeanFactory

### 4.1. prepareRefresh()

Spring sets the startup timestamp, establishes the active state, initializes property sources via the `initPropertySources()` hook, and validates the required properties declared in `Environment`. Additionally, the context prepares infrastructure to hold events published while listeners are not yet ready.

For example, configuration code before refresh:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
context.getEnvironment().setRequiredProperties("app.region");
context.register(AppConfig.class);
context.refresh(); // Fails if app.region is not yet in Environment.
```

This is a fragment requiring an `AppConfig` class and appropriate `close()` handling. `setRequiredProperties` belongs to `ConfigurablePropertyResolver` of `ConfigurableEnvironment`; `refresh()` will validate and may throw an exception before creating regular singletons. The example omits creating the `app.region` property, intentionally illustrating the missing-configuration branch.

**Do not confuse the `isActive()` flag with startup completed**: `prepareRefresh()` can set the active flag before most of the remaining steps occur.

### 4.2. obtainFreshBeanFactory()

This phase obtains a `ConfigurableListableBeanFactory` representing the bean configuration. In some contexts that can refresh multiple times, Spring creates a new bean factory and reloads the configuration; in `GenericApplicationContext`, the bean factory already exists beforehand and is not allowed to be arbitrarily re-initialized.

`BeanFactory` stores bean definitions, scopes, the dependency graph, and creates instances. `ApplicationContext` is the layer integrating additional events, resources, messages, and lifecycle orchestration. Not every BeanFactory automatically publishes `ContextRefreshedEvent` like ApplicationContext.

### 4.3. prepareBeanFactory() and postProcessBeanFactory()

Spring configures standard supporting components such as the class loader, expression resolution, property editors, `ApplicationContextAware`/`EnvironmentAware` integration, and resolvable dependencies. For web contexts, subclasses add wiring related to ServletContext/request/session in the appropriate hook.

Most applications **do not need to override** these hooks. They are intended for infrastructure or custom `ApplicationContext` authors; applications typically configure via `@Configuration`, `@Bean`, and public extension points.

## 5. Phases 5–6: processing metadata first, instances later

This is the bridge between **bean declaration** and **bean instantiation**, and also explains why Spring does not simply scan classes and immediately invoke constructors:

| Extension point | Main operation | Timing in `refresh()` |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Register/modify `BeanDefinition`, such as detecting `@Configuration` and `@Bean` via `ConfigurationClassPostProcessor` | Phase 5, before regular factory processors |
| `BeanFactoryPostProcessor` | Modify metadata, resolve configuration and placeholders | Phase 5, before creating application singletons |
| `BeanPostProcessor` | Inject, execute callbacks, or wrap a proxy around an **instance** | Registered in phase 6, invoked when each bean is created |

For example, `AutowiredAnnotationBeanPostProcessor` handles appropriate injection points; `CommonAnnotationBeanPostProcessor` participates in `@PostConstruct`/`@PreDestroy` callbacks when the corresponding annotation APIs are available. For a regular singleton, the local flow consists of **constructor/factory → injection → before-initialization processors (which may include `@PostConstruct`) → `afterPropertiesSet`/custom init → after-initialization processors (which may create a proxy)**. The `SmartInitializingSingleton.afterSingletonsInstantiated()` milestone arrives after the pre-instantiation loop and before `ContextRefreshedEvent`.

If a processor tries to call `getBean()` too early, it may create a service before other processors are fully registered, causing missing expected injection/proxies. The next lesson dives deeper into registration, ordering, and testing of post-processors; in this lesson, just remember **phase 5 processes definitions, phase 6 prepares instance processing, and phase 11 initializes eager singletons**.

## 6. Phases 7–10: messages, events, and context-specific infrastructure

`initMessageSource()` sets up the bean named `messageSource` if it exists, or an appropriate fallback to support internationalized messages. Users normally declare `MessageSource` via configuration rather than overriding the lifecycle phase.

`initApplicationEventMulticaster()` creates or obtains the `ApplicationEventMulticaster` by Spring's naming convention. By default, event listeners usually run synchronously on the publishing thread; if an asynchronous executor is configured, completion order and timing change. **Do not** assume by default that all listeners have finished all external tasks when an event is published.

`onRefresh()` is a hook for subclasses, such as web application infrastructure. It runs **before** the initialization phase of all regular singletons. A bean created by specific infrastructure can cause early side effects; do not write logic relying on assumptions about classpath scanning order between independent beans.

`registerListeners()` adds statically registered listeners or `ApplicationListener` beans to the event multicaster, and publishes retained early application events. With `@EventListener`, an infrastructure adapter processes the annotation into a corresponding listener; do not assume all listeners are created before the singleton phase.

### Standard context events

| Event | Typical timing | Meaning |
| --- | --- | --- |
| `ContextRefreshedEvent` | End of a successful `refresh()` | Context has loaded definitions, processors, eager singletons, and completed the refresh process |
| `ContextStartedEvent` | After `start()` call | Lifecycle beans are sent the start signal |
| `ContextStoppedEvent` | After `stop()` call | Lifecycle beans are sent the stop signal |
| `ContextClosedEvent` | During `close()`/shutdown hook | Context is closing, preparing to destroy singletons and release resources |

A parent/child ApplicationContext hierarchy can cause events from a child to propagate up to the parent. Listeners should check `event.getApplicationContext()` if business logic is meant only for its own context. Events are not distributed messages: contexts in different JVMs/pods do not automatically receive the same Spring event.

## 7. The last two phases: singleton pre-instantiation and finishRefresh

In `finishBeanFactoryInitialization(beanFactory)`, Spring finalizes the conversion service and necessary setups, then calls `preInstantiateSingletons()` on the corresponding BeanFactory. Regular eager singletons are created, injected, and initialized. Spring does not guarantee that all independent singletons are created in class name or source file order; dependencies and configuration determine much of the sequence.

In `finishRefresh()`, `LifecycleProcessor.onRefresh()` is called before `ContextRefreshedEvent` is published. For auto-start `SmartLifecycle` beans, Spring can start them here according to phase/depends-on. **Therefore a `ContextRefreshedEvent` listener may see that lifecycle components have already received auto-start**, though this does not mean all external dependencies or asynchronous tasks they launch are already operating healthily.

`SmartLifecycle` differs from `SmartInitializingSingleton`:
- `SmartInitializingSingleton`: one-time callback at the end of regular singleton pre-instantiation, suitable for validating/building registries.
- `SmartLifecycle`: participates in start/stop, has phase and autoStartup, suitable for listeners, consumers, or long-running components.
- `ContextRefreshedEvent`: ApplicationContext-level signal after refresh, can occur multiple times in implementations supporting re-refresh.
- `ApplicationRunner`/`CommandLineRunner`: Spring Boot extensions running after context refresh per Boot's workflow, not part of the 12 core phases of Spring Core `refresh()`.

## 8. Complete runnable Java 17+ example: observing refresh, start/stop, close

The following example uses **Java 17+, Maven 3.9+, and Spring Framework 6.2.19**, without requiring Spring Boot, servlets, or a database. We create an `AnnotationConfigApplicationContext` in an unrefreshed state, register configuration, call `refresh()`, and observe the order of callbacks and events.

### Project structure

```text
context-refresh-demo/
├── pom.xml
└── src/main/java/edu/example/context/
    ├── AppConfig.java
    ├── DemoBean.java
    ├── ContextEvents.java
    └── Main.java
```

**pom.xml:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>context-refresh-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.context.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/context/DemoBean.java:**

```java
package edu.example.context;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.SmartInitializingSingleton;

public final class DemoBean
        implements InitializingBean, SmartInitializingSingleton, DisposableBean {

    public DemoBean() {
        System.out.println("bean: constructor");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("bean: afterPropertiesSet");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("bean: afterSingletonsInstantiated");
    }

    @Override
    public void destroy() {
        System.out.println("bean: destroy");
    }
}
```

**src/main/java/edu/example/context/ContextEvents.java:**

```java
package edu.example.context;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;

public final class ContextEvents
        implements ApplicationListener<ApplicationContextEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextEvent event) {
        if (event instanceof ContextRefreshedEvent) {
            System.out.println("event: refreshed");
        } else if (event instanceof ContextStartedEvent) {
            System.out.println("event: started");
        } else if (event instanceof ContextStoppedEvent) {
            System.out.println("event: stopped");
        } else if (event instanceof ContextClosedEvent) {
            System.out.println("event: closed");
        }
    }
}
```

**src/main/java/edu/example/context/AppConfig.java:**

```java
package edu.example.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public DemoBean demoBean() {
        return new DemoBean();
    }

    @Bean
    public ContextEvents contextEvents() {
        return new ContextEvents();
    }
}
```

**src/main/java/edu/example/context/Main.java:**

```java
package edu.example.context;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        System.out.println("before refresh: active=" + context.isActive());
        context.register(AppConfig.class);

        try {
            context.refresh();
            System.out.println("after refresh: active=" + context.isActive());

            context.start();
            context.stop();
        } finally {
            context.close();
        }

        System.out.println("after close: active=" + context.isActive());
    }
}
```

Run inside the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**The program's `System.out.println` lines, in order:**

```text
before refresh: active=false
bean: constructor
bean: afterPropertiesSet
bean: afterSingletonsInstantiated
event: refreshed
after refresh: active=true
event: started
event: stopped
event: closed
bean: destroy
after close: active=false
```

Spring/Maven may produce separate logs, but the `System.out` lines are the deterministic output of this minimal program when refresh succeeds. Note that `context.start()` and `context.stop()` **still publish events** even though the example has no custom `Lifecycle` bean to start or stop. `close()` publishes `ContextClosedEvent` before singletons are destroyed, so the closed event is printed **before** `bean: destroy`.

The example intentionally does not call `refresh()` a second time: `AnnotationConfigApplicationContext` does not support refreshing the same instance again. In production, use a framework-managed context and close it according to the application lifecycle, avoiding calling `close()` while requests are still running.

## 9. Configuring context before refresh and management responsibilities

`ConfigurableApplicationContext` allows additional configuration before bootstrap. Common APIs:

| API | Effect | When to call |
| --- | --- | --- |
| `setEnvironment(...)` | Provide a custom `ConfigurableEnvironment` | Before refresh |
| `getEnvironment().setActiveProfiles(...)` | Select profiles | Before processing bean definitions/refresh |
| `addBeanFactoryPostProcessor(...)` | Add a BeanFactory-level processor | Before refresh |
| `addApplicationListener(...)` | Register a static listener | Before refresh or after event system is active, per API |
| `setParent(...)` | Set parent context | Before refresh |
| `refresh()` | Bootstrap the container | Per implementation rules, usually once |
| `getBeanFactory()` | Access internal ConfigurableListableBeanFactory | Use cautiously, usually for framework/infrastructure |
| `registerShutdownHook()` | JVM hook to auto-close context on shutdown | When app manages context itself without another shutdown manager |
| `start()/stop()` | Send Lifecycle signals | After refresh, does not replace refresh/close |
| `close()` | Close context, destroy singletons | When ending application/container |

Do not attach `registerShutdownHook()` and also manually call `close()` out of worry that beans might not be destroyed, or worry they will be destroyed twice: Spring has a mechanism to avoid duplicate closes on the same context, yet shutdown design should still have **one primary responsible place**. `try-with-resources` is convenient for CLI/tests creating contexts manually because `ConfigurableApplicationContext` supports `close()`.

### Where should BeanFactoryPostProcessor be registered?

Example fragment:

```java
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();
ctx.addBeanFactoryPostProcessor(factory -> {
    // Modify metadata before regular beans are instantiated.
});
ctx.register(AppConfig.class);
ctx.refresh();
```

This is only an illustrative snippet, without `AppConfig` and cleanup. The callback receives `ConfigurableListableBeanFactory`, allowing access to bean definitions; avoid arbitrarily calling `factory.getBean(...)` inside so as not to instantiate beans too early.

If you need to customize definitions via Java config, prefer supported annotations/Spring extensions, and only use low-level processors when genuinely needing to alter metadata.

## 10. Refresh failure: exceptions, rollback, and cleanup

When refresh encounters an exception, Spring proactively cleans up already-created singletons in the BeanFactory according to the lifecycle mechanism, cancels context bootstrap, and propagates the error to the caller. `ConfigurableApplicationContext.refresh()` has a contract to avoid leaving half-created singletons behind in a failed startup. However, that **does not guarantee rolling back all side effects** of application code: if `@PostConstruct` sends an email, writes to a DB, opens an unmanaged socket, or starts a thread, Spring cannot "undo" those operations automatically.

```text
refresh()
  |
  +-- prepare, process bean definitions, instantiate beans
  |
  +-- @PostConstruct / factory method / processor throws exception
  |
  +-- destroy already-created singletons (best effort)
  +-- cancelRefresh() / reset status
  +-- propagate failure to caller
```

Points to note:
- Invalid configuration, missing dependencies, and unsupported circular dependencies typically raise `BeansException` or `BeanCreationException` with detailed causes.
- Lazy beans may not be created at startup; errors in such beans might only appear on the first call, **not** necessarily during refresh.
- A context that only allows a single refresh may not be retried for refresh after an error; create a new context instance and fix the root cause instead of blindly calling it again.
- Cleanup depends on whether the singleton is already fully managed by Spring. If creating a resource and then throwing an exception mid-constructor/init, ensure local cleanup yourself.
- Multiple contexts in a parent-child hierarchy have independent lifecycles; closing a child does not automatically close the parent, and refreshing a child should not be treated as refreshing the entire hierarchy.

Appropriate fail-fast patterns: use `@ConfigurationProperties` validation, constructor preconditions, or `@PostConstruct` checks for mandatory conditions; if an external resource might be temporarily unavailable, use clear readiness/retry/timeout handling rather than hanging indefinitely during refresh.

## 11. start(), stop(), close(), and events do not replace one another

`refresh()` **creates and prepares** the container. `start()` and `stop()` belong to `Lifecycle` control; they send signals to managed `Lifecycle` beans and publish corresponding context events. `close()` **terminates** the context: publishes the closing event, stops lifecycle components via the appropriate processor, and destroys singletons.

```text
          refresh
 NEW  ----------------->  CONTEXT REFRESHED
                                  |
                                  | start()
                                  v
                           Lifecycle STARTED
                                  |
                                  | stop()
                                  v
                           Lifecycle STOPPED
                                  |
                                  | start()
                                  v
                           Lifecycle STARTED
                                  |
                                  | close()
                                  v
                            CONTEXT CLOSED
```

This is a conceptual model; in Spring, some `SmartLifecycle` beans can **auto-start right inside finishRefresh()** without the application calling `start()`. When `stop()` is called, the context still exists and `getBean()` can usually still be called; only components managing `Lifecycle` receive the stop signal. `stop()` does not destroy all singletons, does not remove all definitions, and does not re-instantiate them on `start()`.

After `close()`, the context ends its lifecycle; do not call `refresh()`/`start()` as a way to reuse a closed context. For implementations supporting multiple refreshes while **not yet closed**, that is an exception with its own rules and does not turn a closed context into a reusable container.

### SmartLifecycle with phases

`SmartLifecycle` provides `isAutoStartup()`, `getPhase()`, and the `stop(Runnable)` callback (alongside `Lifecycle` methods). Depending on the version, Spring processes startup in ascending phase order and shutdown in descending phase order, combined with dependency ordering. If a consumer needs to wait for a repository or connection infrastructure, declare dependencies and phases explicitly; do not rely on a `ContextRefreshedEvent` listener to solve all startup ordering.

## 12. Common pitfalls with refresh in Spring Boot, Web, and tests

### 12.1. Calling refresh() again to "reload configuration"

In `AnnotationConfigApplicationContext` and many Spring Boot-managed contexts, calling `refresh()` again is not a valid runtime configuration reload mechanism. It can fail because the implementation does not support multiple refreshes. If runtime configuration changes are needed, design dynamic config with a clear lifecycle, publish an immutable snapshot, or rebuild a new context under controlled conditions.

### 12.2. Changing Environment after refresh and expecting beans to change

`@Value`, `@ConfigurationProperties`, `@Profile`, and `@Conditional` are processed at different stages. Calling `environment.setActiveProfiles("prod")` after refresh does not mean Spring will automatically destroy/recreate beans according to the new profile. Bean definitions have already been processed and singletons already created. Set profiles/property sources before refresh, or use a specialized controlled config refresh mechanism when the application provides one.

### 12.3. Launching long-running jobs in @PostConstruct

`@PostConstruct` runs during bean initialization, usually before `finishRefresh()`. Long-running network jobs can slow down, time out, or fail context startup; self-invocation calls to `@Transactional`/`@Async` methods may also bypass the proxy. Use an appropriate lifecycle hook after refresh or `SmartLifecycle` for long-lived components. In Spring Boot, runners can be used if the work needs to execute at the application level.

### 12.4. Mistaking ContextRefreshedEvent for the server being healthy

The event confirms context refresh completion; it does not prove that the database, Kafka, Redis, DNS, external APIs, or server readiness are completely ready. In Spring Boot, actuator health/readiness has its own semantics and needs system-appropriate configuration. If a `ContextRefreshedEvent` listener calls an external service directly, clear timeout/retry/failure policies are required.

### 12.5. Creating beans manually outside the container

`new MyService()` does not go through the Spring BeanFactory, so it does not receive automatic injection, BeanPostProcessors, init callbacks, or destruction management. For dependencies needing container management, declare `@Bean`, `@Component`/scan, or appropriate factory infrastructure. Do not scatter `getBean()` throughout business code when constructor injection already solves it.

### 12.6. ApplicationListener invoked multiple times when a child context exists

A context hierarchy can propagate `ApplicationEvent` from child to parent. Listeners should check `event.getApplicationContext() == myContext` when they only want to handle their own context's refresh; additionally, an implementation supporting hot refresh may publish the event multiple times. Do not treat `ContextRefreshedEvent` as a global exactly-once job.

### 12.7. Registering listeners too late

Calling `addApplicationListener(...)` after `ContextRefreshedEvent` has already been published does not automatically replay past events. If you need to observe the first refresh, register the listener **before** `refresh()` (or declare a listener bean beforehand). The standard event mechanism does not provide history replay for all late subscribers.

### 12.8. Forgetting close() when creating a context in integration tests / CLI

A context can hold thread pools, connections, and singleton resources. With a manually created `AnnotationConfigApplicationContext`, use `try-with-resources` or `finally { context.close(); }`. `close()` triggers lifecycle shutdown and singleton destruction callbacks; container-created prototypes typically do not automatically have full destruction management like singletons. The Spring Test framework has context caching and its own lifecycle management; do not arbitrarily close cached contexts in individual tests.

## 13. Debugging when context fails to start or starts in the wrong order

A practical checklist:

1. **Confirm the context implementation**: `AnnotationConfigApplicationContext`, `ClassPathXmlApplicationContext`, `WebApplicationContext`, or a Spring Boot context? Re-refresh capabilities differ.
2. **Check pre-refresh configuration**: active profiles, property sources, required properties, class scanning, `@Import`, and `@Bean` definitions.
3. **Inspect the exception root cause**: `NoSuchBeanDefinitionException`, `BeanCreationException`, circular dependencies, constructor exceptions, or BeanPostProcessor failures.
4. **Distinguish the phase**: if it has not entered `finishBeanFactoryInitialization()`, the error may belong to parsing/processor/infrastructure; if the error is inside `@PostConstruct`, the bean has already passed constructor and most injection.
5. **Observe events**: log `ContextRefreshedEvent` and `ContextClosedEvent`, verifying the exact application context when parent-child exists.
6. **Diagnose init order**: missing dependency relationship? Explicitly specify `@DependsOn` or constructor dependencies; `@Order` is not a general tool to coordinate all singleton creation.
7. **Check lazy beans**: a broken lazy bean might not fail immediately at refresh, but fail on the first request.
8. **Monitor bean post-processors**: are a processor's dependencies being created before infrastructure finishes? This is a subtle source of proxy/injection bugs.
9. **Avoid infinite blocking**: timeout, retry policies, and managing background work in the right lifecycle.
10. **Inspect shutdown**: has the context closed? Are `@PreDestroy`/`DisposableBean`/custom destroy methods registered and is the scope managed by Spring for destruction?

### Tracking startup time

Spring provides the `ApplicationStartup` API to record startup steps. `BufferingApplicationStartup` can collect steps into a buffer for analysis; `FlightRecorderApplicationStartup` integrates with Java Flight Recorder for more detailed profiling. This is instrumentation to see which parts are slow and does not alter lifecycle ordering/contracts. With Spring Boot, related startup endpoint/observability features need appropriate configuration if exposing measurement data is desired.

## 14. Self-check

1. How do `ApplicationContext` and `ConfigurableApplicationContext` differ in intended use?
2. Does `new AnnotationConfigApplicationContext(AppConfig.class)` already call `refresh()`?
3. When using the empty constructor of `AnnotationConfigApplicationContext`, what operation is needed after `register(...)` to create eager singletons?
4. How do `BeanFactoryPostProcessor` and `BeanPostProcessor` differ in timing and target objects processed?
5. Does `@PostConstruct` of bean A guarantee that bean B, which has no dependency with A, has already been created?
6. When does `SmartInitializingSingleton.afterSingletonsInstantiated()` run compared to `ContextRefreshedEvent`?
7. Why is `isActive() == true` not sufficient to prove refresh is complete and the server is ready?
8. Does calling `start()` recreate singletons or re-run `@PostConstruct`?
9. Is `stop()` the same as `close()`? Why?
10. Does `ContextClosedEvent` appear before or after Spring destroys regular singletons?
11. Can `refresh()` be called a second time on an `AnnotationConfigApplicationContext`?
12. When a `@Bean` factory creates a resource and init throws an exception, does Spring roll back all side effects outside the container?
13. If code adds a listener after the context has already refreshed, does the listener automatically receive the earlier `ContextRefreshedEvent`?
14. If a context has a parent and child, does closing the child close the parent?
15. An application has three pods, each pod with one context. Is `ContextRefreshedEvent` published only once across the entire cluster?

**Suggested answers:**

1. `ApplicationContext` is the API for using beans/services; `ConfigurableApplicationContext` adds startup, environment, and shutdown management.
2. Yes, that constructor registers the configuration and refreshes.
3. Call `refresh()` exactly once.
4. Factory processors transform metadata before instantiation; bean processors participate in the instance lifecycle.
5. No; the hook belongs only to bean A.
6. The smart callback runs at the end of pre-instantiation; the refresh event is published after `finishRefresh()`.
7. Active is enabled at the start of refresh, not as a health signal.
8. No; it only signals `Lifecycle` beans and publishes the started event.
9. No; stop does not destroy the context, whereas close terminates the lifecycle and destroys singletons.
10. Before, during the normal closing process.
11. No; the generic bean factory does not support multiple refreshes.
12. No; external side effects must be actively controlled.
13. No; events are not automatically replayed.
14. No; each context has its own lifecycle.
15. No; each context/pod has its own refresh event.

## Official Documentation

- Spring Framework — Additional Capabilities of the ApplicationContext (lifecycle events): https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — `ConfigurableApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework — `AbstractApplicationContext` Javadoc (`refresh()` and template hooks): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework — `AbstractRefreshableApplicationContext` Javadoc (refreshable context): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractRefreshableApplicationContext.html
- Spring Framework — `AnnotationConfigApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html
- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
