# Events During Spring ApplicationContext Refresh

## 1. Lesson objectives

When a Spring application initializes, `ApplicationContext` does not merely create beans and return to the caller. It also performs a sequence of configuration steps, singleton initialization, event system preparation, `Lifecycle` component activation, and **publishes `ContextRefreshedEvent`** when the refresh process completes successfully.

In this lesson, `refresh context` refers to the `ConfigurableApplicationContext.refresh()` call and the corresponding operations performed by `AbstractApplicationContext`. You should understand:

- What `ContextRefreshedEvent` is, when it is published, and what information it holds.
- Which steps of `refresh()` relate to listener registration, bean initialization, and `SmartLifecycle`.
- How to receive the event using `ApplicationListener` or `@EventListener`.
- Differences among `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextClosedEvent`, and Spring Boot startup events.
- How to handle receiving events from child contexts, multiple refreshes, asynchronous handling, and errors in listeners.
- A standalone runnable Java 17+ example with Spring Framework to observe the exact initialization order.

## 2. What is `ContextRefreshedEvent`?

`org.springframework.context.event.ContextRefreshedEvent` is an `ApplicationContextEvent` whose source is the `ApplicationContext` that was just initialized or refreshed. Spring publishes this event after executing the main part of the context initialization process, and `ApplicationContext` is ready to use according to the framework's lifecycle.

Listener example:

~~~java
// Illustrative snippet inside a Spring-managed bean.
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    ApplicationContext source = event.getApplicationContext();
    System.out.println("Refreshed: " + source.getId());
}
~~~

Spring will register the method with the application events system. When the source context publishes `ContextRefreshedEvent`, the method is invoked according to the current dispatch mode (synchronous by default). From `event.getApplicationContext()`, you can identify **the specific context that published the event**; this is very important if the application has parent/child contexts.

**Key meaning:** this is a signal about the **Spring context lifecycle**, not a signal that "all background tasks have been processed", "all external services are healthy", or "the application is ready to receive traffic" in every architecture.

### What is and is not guaranteed

When `ContextRefreshedEvent` is published at the end of a normal `refresh()`:

- Bean definitions, the bean factory, and necessary bean post-processors have been set up.
- **Non-lazy singletons** requiring eager initialization have been instantiated and have run initialization callbacks, such as `InitializingBean.afterPropertiesSet()`.
- Spring has completed `finishBeanFactoryInitialization(...)`.
- Inside `finishRefresh()`, `LifecycleProcessor.onRefresh()` is invoked before `ContextRefreshedEvent` is published; eligible `SmartLifecycle` beans with `autoStartup` may already have been started.
- `@Lazy` beans, prototypes, or auto-started asynchronous work **are not guaranteed to have all finished**. External processes such as migrations/consumers/remote APIs may also not be ready yet, depending on the application.

Do not confuse the concept of "context refreshed" with "all application tasks have finished".

## 3. Position of the event in `AbstractApplicationContext.refresh()`

At a high level, the refresh sequence in `AbstractApplicationContext` consists of the following steps (method names are Spring's internal hooks, not APIs an application must call step by step):

| Step | Work | Impact on events/listeners |
| --- | --- | --- |
| `prepareRefresh()` | Prepares context state, validates properties, records startup time | Sets the foundation for the refresh cycle and early events |
| `obtainFreshBeanFactory()` | Prepares or obtains the bean factory for this refresh | Bean definitions must be ready according to the context type |
| `prepareBeanFactory(...)` | Registers foundational components on the factory | Supports dependencies, context-aware callbacks, and infrastructure |
| `postProcessBeanFactory(...)` | Allows subclasses to customize the bean factory | Depends on context type |
| `invokeBeanFactoryPostProcessors(...)` | Runs `BeanFactoryPostProcessor` and registry post-processors | Configuration/definition modifications complete before instantiation |
| `registerBeanPostProcessors(...)` | Installs `BeanPostProcessor` beans | Prepares proxies and bean callbacks |
| `initMessageSource()` | Prepares the internationalization message source | Context service |
| `initApplicationEventMulticaster()` | Initializes the multicaster | Ready to dispatch application events |
| `onRefresh()` | Subclass hook, e.g., some web contexts initialize infrastructure | Not `ContextRefreshedEvent` yet |
| `registerListeners()` | Registers `ApplicationListener` beans and replays early events if any | Listeners are wired to the multicaster |
| `finishBeanFactoryInitialization(...)` | Initializes remaining singletons | Annotation-based listeners and related `SmartLifecycle` beans are prepared |
| `finishRefresh()` | Runs the lifecycle processor and publishes the completion event | **`ContextRefreshedEvent` is published here** |

Simplified:

~~~text
refresh()
   |
   +-- prepare BeanFactory and BeanPostProcessors
   +-- create ApplicationEventMulticaster
   +-- register listeners
   +-- initialize non-lazy singletons
   |
   +-- finishRefresh()
          |
          +-- lifecycleProcessor.onRefresh()
          |       +-- start eligible autoStartup SmartLifecycle beans
          |
          +-- publishEvent(new ContextRefreshedEvent(this))
   |
   +-- refresh() returns when synchronous dispatch finishes
~~~

**Do not confuse `onRefresh()` with `finishRefresh()`:** `onRefresh()` is a subclass hook at an earlier step, before singleton initialization finishes. `ContextRefreshedEvent` is published in `finishRefresh()`, after the `LifecycleProcessor.onRefresh()` call.

### Why can listeners receive the event at the end of refresh?

- Spring registers beans implementing `ApplicationListener` during the `registerListeners()` phase.
- Methods annotated with `@EventListener` are discovered/registered by annotation-processing mechanisms such as `EventListenerMethodProcessor` during the bean initialization lifecycle.
- When `ContextRefreshedEvent` is published at the end of refresh, eligible listeners are already registered to receive the event.

Do not treat the declaration order of `@Bean` methods in a file as a callback ordering contract. Dependency management, post-processors, and lifecycle mechanisms are the deciding factors.

### What about events published very early during refresh?

Some events published when the multicaster/listeners are not yet fully registered may be temporarily stored by Spring in the `earlyApplicationEvents` mechanism and dispatched when `registerListeners()` runs. This is a lifecycle detail of `AbstractApplicationContext`; do not rely on it as a durable message queue or assume every event type at every moment is stored/retried.

## 4. Two ways to listen for `ContextRefreshedEvent`

### Approach 1: `ApplicationListener<ContextRefreshedEvent>`

~~~java
// Illustrative snippet: the class must be registered as a bean.
@Component
public class RefreshListener
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getId());
    }
}
~~~

`ApplicationListener` provides a type-safe API, useful when the listener is registered early or the logic needs reuse. There is no need to call `publishEvent` manually to generate the refresh event; the context itself publishes it.

### Approach 2: `@EventListener`

~~~java
// Illustrative snippet: the class must be registered as a bean.
@Component
public class RefreshHandler {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getDisplayName());
    }
}
~~~

Spring infers the event type from the method parameter. You can also declare `@EventListener(ContextRefreshedEvent.class)` explicitly. Choose the approach that fits your project; both use Spring's event mechanism and there is no need to register both for the same action.

**Especially with parent/child contexts:** when a child context publishes an event, Spring can forward the event up to the parent context. A listener in the parent can therefore receive events from both the parent and the child. To handle only the refresh of **the context the bean belongs to**, inject the owning context and compare identity:

~~~java
// Illustrative snippet inside a Spring-managed bean.
private final ApplicationContext ownContext;

public RefreshHandler(ApplicationContext ownContext) {
    this.ownContext = ownContext;
}

@EventListener
public void onRefresh(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return; // event came from another context, such as a child
    }
    initializeForThisContext();
}
~~~

The two illustrative methods/classes above are not standalone programs; apply them inside proper Spring bean classes. If you need to handle **all contexts** in the hierarchy, do not filter, but explicitly define how many times the task is allowed to run.

## 5. Runnable Java 17+ example: observing startup and refresh events

The following program uses Spring Framework only (no Spring Boot required). The goal is to verify:

1. Before `refresh()`, the context is not active yet.
2. `InitializingBean.afterPropertiesSet()` runs when singletons are initialized.
3. `SmartLifecycle.start()` runs during the lifecycle part of refresh.
4. `@EventListener(ContextRefreshedEvent)` observes that beans are initialized and `SmartLifecycle` has started.
5. After `refresh()`, the caller sees one refresh event; after `close()`, the context is no longer active.

The example uses `AtomicInteger` to count events and state flags. It does not rely on `Thread.sleep` or framework logs to draw conclusions.

Structure:

~~~text
context-refresh-event/
├── pom.xml
└── src/main/java/demo/ContextRefreshDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-refresh-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/ContextRefreshDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class ContextRefreshDemo {

    public static final class State {
        volatile boolean beanInitialized;
        volatile boolean lifecycleStarted;
        final AtomicInteger refreshEvents = new AtomicInteger();
    }

    // Initialized as a singleton before refresh finishes.
    public static final class ResourceBean implements InitializingBean {
        private final State state;

        public ResourceBean(State state) {
            this.state = state;
        }

        @Override
        public void afterPropertiesSet() {
            state.beanInitialized = true;
        }
    }

    // SmartLifecycle auto-starts during LifecycleProcessor.onRefresh().
    public static final class Worker implements SmartLifecycle {
        private final State state;
        private final ResourceBean dependency;
        private volatile boolean running;

        public Worker(State state, ResourceBean dependency) {
            this.state = state;
            this.dependency = dependency;
        }

        @Override
        public void start() {
            if (!state.beanInitialized || dependency == null) {
                throw new IllegalStateException("ResourceBean not ready");
            }
            running = true;
            state.lifecycleStarted = true;
        }

        @Override
        public void stop() {
            running = false;
        }

        @Override
        public void stop(Runnable callback) {
            stop();
            callback.run();
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
            return 0;
        }
    }

    public static final class RefreshObserver {
        private final State state;
        private final ApplicationContext ownContext;

        public RefreshObserver(State state, ApplicationContext ownContext) {
            this.state = state;
            this.ownContext = ownContext;
        }

        @EventListener
        public void onContextRefreshed(ContextRefreshedEvent event) {
            // Handle only the context owning the listener, avoiding child events.
            if (event.getApplicationContext() != ownContext) {
                return;
            }
            if (!state.beanInitialized || !state.lifecycleStarted) {
                throw new AssertionError("Refresh event arrived too early");
            }
            state.refreshEvents.incrementAndGet();
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public State state() {
            return new State();
        }

        @Bean
        public ResourceBean resourceBean(State state) {
            return new ResourceBean(state);
        }

        @Bean
        public Worker worker(State state, ResourceBean resourceBean) {
            return new Worker(state, resourceBean);
        }

        @Bean
        public RefreshObserver refreshObserver(
                State state, ApplicationContext context) {
            return new RefreshObserver(state, context);
        }
    }

    public static void main(String[] args) {
        var context = new AnnotationConfigApplicationContext();

        try (context) {
            context.register(Config.class);
            System.out.println("before-refresh active=" + context.isActive());

            context.refresh();

            State state = context.getBean(State.class);
            Worker worker = context.getBean(Worker.class);

            System.out.println("bean-initialized=" + state.beanInitialized);
            System.out.println("lifecycle-running=" + worker.isRunning());
            System.out.println("refresh-events=" + state.refreshEvents.get());
            System.out.println("after-refresh active=" + context.isActive());
        }

        System.out.println("after-close active=" + context.isActive());
    }
}
~~~

Run in the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextRefreshDemo
~~~

Lines printed by the program in order:

~~~text
before-refresh active=false
bean-initialized=true
lifecycle-running=true
refresh-events=1
after-refresh active=true
after-close active=false
~~~

### 5.3. Why is the result predictable?

- `new AnnotationConfigApplicationContext()` creates an unrefreshed context; `isActive()` is `false`.
- `register(Config.class)` registers the configuration, but does not complete the refresh cycle by itself.
- `refresh()` initializes singletons according to dependencies. `ResourceBean` invokes `afterPropertiesSet()`, setting `beanInitialized=true`.
- In `finishRefresh()`, `LifecycleProcessor.onRefresh()` starts `Worker` because it is an auto-starting `SmartLifecycle`. `Worker` checks that its dependent bean is initialized and sets `lifecycleStarted=true`.
- Afterward the context publishes `ContextRefreshedEvent`. `RefreshObserver` is registered via `@EventListener` and increments the counter to 1 after checking the conditions.
- With the default synchronous multicaster and no parent context, `refresh()` completes after that dispatch. Therefore main reads `refreshEvents=1`.
- At the end of the `try (context)` block, `close()` runs; `LifecycleProcessor` stops eligible beans and `isActive()` becomes `false`.

The example calls `refresh()` once. Do not call `refresh()` a second time on `AnnotationConfigApplicationContext` because this class is based on `GenericApplicationContext`, which does not support re-refreshing the same instance. To simulate a fresh startup, create a new context. Some other Spring implementations may support multiple refreshes; do not apply a "one ContextRefreshedEvent per JVM" rule across the entire system.

## 6. Relationship with other lifecycle events

| Event | Source / trigger | Should be understood as |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context just initialized or refreshed | Successful end of a context refresh cycle |
| `ContextStartedEvent` | Calling `ConfigurableApplicationContext.start()` | Explicit start signal for `Lifecycle` beans, distinct from refresh |
| `ContextStoppedEvent` | Calling `ConfigurableApplicationContext.stop()` | Context received a stop signal |
| `ContextClosedEvent` | Context is `close()`-ed or shut down | Context lifecycle ends and beans will be destroyed per procedure |
| `ApplicationStartedEvent` (Spring Boot) | Boot has refreshed the context, before `ApplicationRunner`/`CommandLineRunner` | Boot application has started up to the pre-runner stage |
| `ApplicationReadyEvent` (Spring Boot) | After Boot runs application/command-line runners | Later point, used when logic needs to know Boot startup has completed |

**Plain Spring Framework** has no obligation to publish `ApplicationReadyEvent` — that is a **Spring Boot** event. In a typical Boot application, `ContextRefreshedEvent` occurs before `ApplicationStartedEvent`, followed by `ApplicationReadyEvent` after the runners. Do not write a `ContextRefreshedEvent` listener assuming runners have already finished.

Also avoid confusing the `onRefresh()` method of `AbstractApplicationContext` with `ContextRefreshedEvent`, or confusing `ContextStartedEvent` from calling `start()` with the event published automatically at the end of `refresh()`.

## 7. Cases where the event occurs multiple times

### 7.1. Parent/child contexts

Spring allows a child context to have a parent context. Events published by a child can propagate up to the parent, so a listener located in the parent may receive `ContextRefreshedEvent` for both. If a callback performs actions with side effects like importing data, receiving multiple events can create duplicates.

Distinguish accurately with:

~~~java
@EventListener
public void onRefresh(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    warmUpCacheForThisContext();
}
~~~

This is an illustrative snippet requiring a bean containing `ownContext` and a `warmUpCacheForThisContext` method. Comparing context references ensures handling **the right context**, though if that context can refresh multiple times, the callback can still be called multiple times by design.

### 7.2. Multiple independent contexts or restarts

In a test suite, many different `ApplicationContext` instances can be created and closed. Each time a context finishes refreshing, it has its own event. Do not use a JVM-wide static `initialized` variable to assume the event appears only once; this easily breaks in integration tests and applications containing multiple contexts.

If a startup action must be **idempotent**, store state at the right scope (context, resource, deployment, or business key), and design pre/post checks and safe repeatability. Do not try to solve it with a static flag without knowing the actual lifecycle.

## 8. Choosing appropriate tasks for `ContextRefreshedEvent`

Valid examples:

- Loading runtime configuration or warming up a small cache after required singletons have initialized.
- Registering a task tied to the context's own lifecycle, with a cleanup mechanism on `ContextClosedEvent`.
- Checking and recording metrics for the startup phase scoped to the context.
- Coordinating a **fast**, explicit bootstrap step that can safely re-run on refresh (if the context type supports it).

Should not do:

- Running very long network tasks directly inside a synchronous listener if doing so prolongs `refresh()` and delays startup.
- Assuming database migrations, schedulers, HTTP listeners, message consumers, and external services are all ready just because a `ContextRefreshedEvent` appeared.
- Sending payment emails, creating irreversible tasks, or executing non-idempotent migrations every time the event is published.
- Using it as a complete substitute for health/readiness checks or crash-recovery mechanisms.

**If a background process needs to be started:** consider `SmartLifecycle` when the requirement belongs to start/stop lifecycle management; if using the event to schedule an async task, explicitly specify the executor, timeout, failure handler, and separate readiness flag. The event may have finished processing **before the async work completes**.

**If work needs to run after Boot startup:** consider `ApplicationRunner`, `CommandLineRunner`, or `ApplicationReadyEvent` depending on desired behavior. Runners are called by Boot after refresh and before `ApplicationReadyEvent`; if readiness monitoring is needed, combine with appropriate availability/health mechanisms.

## 9. Dispatch order, error handling, and `@Async`

### 9.1. Synchronous listeners and `@Order`

With the default synchronous event multicaster, Spring calls listeners on the event-publishing thread. `@Order` or `Ordered` can be used to control invocation priority among matching listeners **within the same dispatch**.

~~~java
// Illustrative inside a Spring bean.
@EventListener
@Order(10)
public void afterRefresh(ContextRefreshedEvent event) {
    // Step called in priority order relative to listeners for the same event.
}
~~~

`@Order` is not a mechanism to guarantee whole-application startup, ordering across refreshes of multiple contexts, or **completion** order if listeners offload work to other threads.

### 9.2. `@Async`

When placing `@Async` on a listener and enabling `@EnableAsync` with a valid executor, the listener method body can run on another thread. Then:

- `refresh()` does not wait for the async body to finish just because the event was dispatched.
- Do not assume `ApplicationReadyEvent` or the first request only arrives after that async task finishes.
- If the async task fails, logging/metrics/retries and an `AsyncUncaughtExceptionHandler` are needed where appropriate.
- If the task needs the right thread/request/transaction context, switching threads does not automatically copy `ThreadLocal`, security context, or transactions.

For tasks that must complete **before the application is considered ready**, use explicit coordination mechanisms or appropriate startup runners with clear error control; fire-and-forget will not produce that guarantee.

### 9.3. Exceptions

An exception in a default synchronous listener can propagate to the event-publishing flow (depending on multicaster and error handler configuration), causing failure in the `finishRefresh()` stage. Therefore, do not place failure-prone processing unrelated to bean initialization into this callback without a failure-handling policy. If catching exceptions, do not silently discard serious errors causing the application to assume it is ready.

Conversely, a listener running async can fail **after refresh returns**, so independent monitoring is required.

## 10. Self-check checklist

1. Is `ContextRefreshedEvent` published after `finishBeanFactoryInitialization` and `LifecycleProcessor.onRefresh()`?
2. Which context does the listener belong to, and can it receive events from children?
3. Is the work in the listener idempotent if the event occurs multiple times?
4. Are you relying on `ContextRefreshedEvent` as a Spring Boot readiness signal even though runners have not finished?
5. Are there long I/O tasks, `@Async`, exceptions, or timeouts causing prolonged startup or premature readiness?
6. Does the current context actually support multiple refreshes, or should a new instance be created?
7. Do resources need to be started/stopped by lifecycle? If yes, consider `SmartLifecycle`.
8. Have context open/close, hierarchy, and startup failure cases been tested?

**Remember:** `ContextRefreshedEvent` marks that a Spring context has completed a refresh cycle. It is published at the end of `AbstractApplicationContext.finishRefresh()`, after non-lazy singletons have been prepared and the lifecycle processor has been invoked. Choose listeners to react to the **context refreshed** state, while designing separately for readiness, async processing, durability, and multi-context handling.

## Official documentation

- Spring Framework — ApplicationContext events, built-in event types, and `ContextRefreshedEvent`: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 — `AbstractApplicationContext.refresh()` and `finishRefresh()`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2 — `LifecycleProcessor` and `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.2 — `ContextRefreshedEvent` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Boot — SpringApplication events, Started/Ready, and parent-child contexts: https://docs.spring.io/spring-boot/reference/features/spring-application.html
