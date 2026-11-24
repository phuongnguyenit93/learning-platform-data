# Event Published Before Listener Registration in Spring Application Events

## 1. Scenario: Publisher Ran, Yet the Listener Missed the Event

A tricky bug to diagnose in Spring systems is **the producer called `ApplicationEventPublisher.publishEvent(...)`, yet the expected listener never received the event**. Especially when events fire during startup or before a listener is registered with `ApplicationContext`, adding `@EventListener` afterward will not make past events reappear automatically.

For example, a system initializes a configuration record during bootstrap:

~~~text
Time             Producer                          Listener
---------        -----------------------           -------------------------
t0               ApplicationContext refreshing     not yet registered
t1               publish(ReferenceDataLoaded)      no matching listener yet
t2               ...                               @EventListener registered
t3               application ready                 waiting for ReferenceDataLoaded
t4               no new events                     does nothing
~~~

Consequences can include unpopulated caches, incomplete read models, event-driven tasks never running, or a component assuming system initialization is still incomplete.

**Key takeaway:** `ApplicationEventPublisher` is Spring's event-dispatching mechanism, **not a durable event store or message broker**. A listener registered late does not automatically receive events dispatched earlier.

There is, however, one exception to state accurately: during part of `refresh()`, `AbstractApplicationContext` collects **early application events** and dispatches them once the corresponding multicaster/listeners are ready. This is a **bounded bootstrap buffer**, not a promise of replay for every `@EventListener` regardless of registration time. This lesson separates the two scenarios rather than simply concluding that "startup events are always lost".

### Learning Objectives

After this lesson, you will be able to:

- Distinguish **publish occurred**, **listener registered**, **listener invoked**, and **handler succeeded**.
- Explain the initialization order of `ApplicationContext`, `ApplicationListener`, `@EventListener`, and `ContextRefreshedEvent`.
- Reproduce the case of registering a listener **after** an event was published with **no replay**.
- Recognize premature events from constructors, `@PostConstruct`, bootstrap steps, or Spring Boot startup events.
- Choose the proper fix: register listeners early, shift publish timing, use runners/lifecycle hooks, or use durable storage when guaranteed delivery of all events is mandatory.
- Write integration tests verifying ordering without confusing it with type/transaction/async bugs.

## 2. Does Spring's Publish/Subscribe Mechanism Store History?

`ApplicationEventPublisher.publishEvent(Object)` hands an event object to the event-publishing mechanism. `ApplicationContext` uses `ApplicationEventMulticaster` to deliver it to matching `ApplicationListener` instances **that are already registered and present in the receiving context**.

For a POJO/record event:

~~~java
public record CatalogLoaded(String catalogName) { }

// Given a Spring-managed publisher:
publisher.publishEvent(new CatalogLoaded("country-codes"));
~~~

Spring can wrap the payload in `PayloadApplicationEvent` for internal transport. A bean with method:

~~~java
@EventListener
public void onCatalogLoaded(CatalogLoaded event) {
    // Handles the CatalogLoaded fact.
}
~~~

will be invoked once this method has been turned into a listener by the framework, registered, and the event is dispatched within the matching context.

The snippets above are **illustrative code inside an application with Spring beans**, not a standalone Java program; section 6 provides a complete project.

### Four Milestones That Must Not Be Equated

| Milestone | Fact that can be asserted | What cannot yet be asserted |
| --- | --- | --- |
| Producer calls `publishEvent(event)` | Code asked Spring to publish the event | Expected listener was already present |
| Multicaster selects listener | Listener was registered, event type/condition matched | Handler completed successfully |
| Listener starts processing | Handler code was invoked | Side effects committed or external API succeeded |
| Listener finishes | Listener returned / worker finished per contract | Event is durably persisted or replayed after a crash |

In **default synchronous** dispatch, `publishEvent` normally waits for standard listeners to finish; however, having no matching listeners still results in **no operation**, and the publish call returns normally. In asynchronous dispatch, the publisher can even return before the handler begins running.

Therefore, **no exception on publish** does not mean "the event reached the right listener".

## 3. Listener Registration in the ApplicationContext Lifecycle

Spring Framework has two familiar models:

1. A bean implementing `ApplicationListener<E>`, or a listener added directly via `ConfigurableApplicationContext.addApplicationListener(...)`.
2. A bean method annotated with `@EventListener`; Spring detects the method and creates a corresponding listener adapter.

The two models have different registration points during refresh.

### 3.1. Startup Milestones Worth Watching

Simplified outline of `AbstractApplicationContext.refresh()` in Spring Framework 6.2:

~~~text
prepareRefresh()
    |
    +-- begins collecting earlyApplicationEvents
    |
obtainFreshBeanFactory()
prepareBeanFactory()
invokeBeanFactoryPostProcessors()
registerBeanPostProcessors()
initMessageSource()
initApplicationEventMulticaster()
onRefresh()
registerListeners()
    |
    +-- adds known ApplicationListeners
    +-- dispatches early events collected during bootstrap
    |
finishBeanFactoryInitialization()
    |
    +-- instantiates required regular singletons
    +-- EventListenerMethodProcessor.afterSingletonsInstantiated()
        registers @EventListener methods
    |
finishRefresh()
    |
    +-- publish(ContextRefreshedEvent)
~~~

This diagram omits many internal details and serves solely to explain **relative ordering**. It is not an API for application code to invoke step by step.

In Spring 6.2, `EventListenerMethodProcessor` is a `SmartInitializingSingleton`: it registers `@EventListener` methods at the end of singleton pre-instantiation. Consequently, if another bean publishes an event **very early during singleton initialization** (such as in a constructor or `@PostConstruct`), the expected method listener may **not be registered yet**, even though the bean object containing that method exists later.

### 3.2. ApplicationListener and @EventListener Do Not Share the Same Timing

| Mechanism | Relevant point | Key characteristic |
| --- | --- | --- |
| `context.addApplicationListener(listener)` **before** `refresh()` | Listener known before context emits refresh events | Suitable when an early context listener is needed |
| Bean implementing `ApplicationListener<E>` | Discovered by `registerListeners()` as a listener bean | Can be present earlier than `@EventListener` methods are processed |
| `@EventListener` method on a regular bean | Discovered by `EventListenerMethodProcessor` during singleton bootstrap | Should not be assumed registered before every other bean's `@PostConstruct` |
| `context.addApplicationListener(listener)` **after** `refresh()` | Added immediately to the active context's multicaster | Receives events **after registration**, does not automatically receive past events |
| `@EventListener` on a lazy bean | Depends on bean lifecycle and method discovery | Spring warns against defining such listener beans as lazy when standard registration is expected |

A listener added programmatically before `refresh` can receive `ContextRefreshedEvent` published at the end of refresh. That same listener, if added only **after refresh returns**, will not receive the `ContextRefreshedEvent` that just fired, unless another corresponding refresh/event actually occurs.

### 3.3. Early Events Are Not a Durable Queue

`AbstractApplicationContext` can temporarily buffer some events in `earlyApplicationEvents` during the early part of `refresh()`, before completing initial listener registration. After `registerListeners()`, the buffered events are dispatched.

What must **not** be inferred:

- There is no long-lived event log lasting until an `@EventListener` bean is initialized minutes later.
- There is no automatic replay for listeners added after `refresh()`.
- There is no guarantee an event emitted from any constructor/`@PostConstruct` reaches every `@EventListener` method, because annotation processing may occur after the buffer has already been flushed.
- There is no durability guarantee across restarts, crashes, or container kills.
- It does not replace a transactional outbox, persistent job storage, or a broker with retention.

Additional note: calling `publishEvent` on a newly constructed **yet unrefreshed** `ApplicationContext` is not a recommended bootstrap pattern. The multicaster may not be initialized yet; do not use pre-`refresh` `publishEvent` as a homemade "pre-start queue".

## 4. Five Common Causes of Events Appearing Before Listeners

### 4.1. Publishing Inside a Constructor or @PostConstruct

~~~java
@Component
class DataLoader {
    private final ApplicationEventPublisher publisher;

    DataLoader(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostConstruct
    void init() {
        publisher.publishEvent(new CatalogLoaded("country-codes"));
    }
}
~~~

This is **illustrative** code, requiring appropriate beans/types/imports. If the receiver uses another `@EventListener` method, that receiver may not yet have been registered by the annotation processor at init time. The code does not necessarily throw an error; you simply observe missing reactions.

Especially avoid publishing critical events in constructors: the bean is still under construction, other dependencies/lifecycles may be incomplete, and event listener infrastructure may not be in its expected state.

**Contract-based fix:** move work that listeners need to receive to after bean infrastructure is ready, or call a service method directly when an initialization step must be guaranteed within the same use case.

### 4.2. Registering a Listener Late in Code

~~~java
context.publishEvent(new CatalogLoaded("A"));
context.addApplicationListener(listener);
context.publishEvent(new CatalogLoaded("B"));
~~~

If the context is already active, the newly added listener **sees only events after the registration point** under normal dispatch. It does not automatically see `CatalogLoaded("A")`. This scenario is demonstrated in the runnable demo in section 6.

### 4.3. Listener Bean Marked @Lazy or Unregistered

If a bean containing `@EventListener` is not discovered at the right lifecycle stage (e.g., outside the context, inappropriately declared lazy, wrong component scan), the method may not become an active listener. Spring Framework Reference warns against declaring listener beans with lazy initialization if standard annotation-based registration is desired.

Not every symptom is "event too early"; sometimes **the listener was never present at all**. When diagnosing, verify **registration** before blaming the producer.

### 4.4. Spring Boot Publishes Events Before Creating the Context

Spring Boot has startup events emitted by `SpringApplication` **before `ApplicationContext` exists**. Examples include `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.

An `@EventListener` method on a context-created bean **cannot** hear events that already occurred before that context/bean was created. Likewise, merely declaring `@Bean ApplicationListener<ApplicationStartingEvent>` inside the context is too late to receive that early event.

With Spring Boot, register very early listeners via `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or discovery via `META-INF/spring.factories` according to your Boot version. Section 8 contrasts this with standard application events.

### 4.5. Creating a Child ApplicationContext After a Parent Event

When using a hierarchy, events from a child context can generally propagate up to the parent context. However, **a context created after another context's event does not automatically inherit that event's history**. Placing a listener in the wrong context also leaves producer and receiver without a valid delivery path.

Distinguish:

- Event emitted in context A while listener in context B **never receives it due to scope/hierarchy**.
- Listener resides in context A yet **was registered after the event**.
- Listener in parent can receive child events via propagation, sometimes leading to **duplicate delivery** rather than missed events.

Do not fix every case by "registering earlier"; first determine **which context emitted the event**.

## 5. Signs of "Early Publish" and How to Rule Out Other Causes

Diagnostic table:

| Symptom | Hypothesis | Evidence to look for |
| --- | --- | --- |
| Event emitted in `@PostConstruct`, handler does not run | Listener method not yet registered | Log init timing and post-refresh; try republishing after refresh in a test |
| Published after refresh, `ApplicationListener` added late | No replay of pre-registration events | Test emitting A before add, emitting B after add |
| `@EventListener` bean never runs at all | Bean not scanned/registered or lazy | Check bean creation config and framework event-method processing |
| `@TransactionalEventListener` does not run | No active transaction, phase mismatch | Check transaction boundary and `fallbackExecution` |
| `@Async` handler produces no side effect before assertion | Worker has not finished | Wait on outcome via latch/future/await, do not rely on sleep |
| Event is a POJO yet listener expects a different type | Type/generic/condition mismatch | Check runtime type and `@EventListener(condition=...)` |
| Producer in child, handler in sibling | Contexts lack a propagation path | Identify context IDs and parent chain |
| Event published yet consumer misses it after restart | No durable history | Check outbox/broker/event store, do not expect `ApplicationEventPublisher` replay |
| Listener logs "START" without "DONE" | Handler ran then errored, not a lost event | Check exceptions/logs/metrics and retry policy |

**Important:** "not seeing the listener's effect" does not mean "the listener was not registered". The handler may have been called and thrown an error, its condition may have evaluated false, it may be waiting asynchronously, or a transaction-bound callback may have been skipped due to no transaction.

### 5.1. An Outside-In Investigation Workflow

1. **Record publish checkpoints:** event class, eventId, correlationId, timestamp, context ID, thread.
2. **Verify the publisher:** confirm the call actually happened without being blocked by an `if` guard, exception, or unreached branch.
3. **Verify the context:** which context is the producer publishing to; does the listener belong to the same context or an eligible ancestor?
4. **Verify listener registration:** bean exists, not unintentionally lazy, processor finished, method has right annotation/type.
5. **Compare timestamps:** was the event dispatched before registration? Which refresh stage was active?
6. **Check dispatch/transaction:** `@Async`, `@TransactionalEventListener`, condition, handler errors, `ErrorHandler`.
7. **Test a fresh event after the listener is definitely active:** if the new event is received, timing is very likely the culprit.
8. **Conclude the root cause and fix the contract:** choose early registration, shifted publication, state reconciliation, or durable delivery.

You do not need to read the entire codebase if logs capture all checkpoints and a small reproducible test exists.

## 6. Runnable Java 17+ Example: Event Before Registration Is Missed

Standalone example using Spring Framework 6.2.8, Java 17+, and Maven, without Spring Boot or a database.

It demonstrates **three phenomena**:

1. The context finished `refresh()`, yet **has no listener** for `DiagnosticSignal`. Publishing `"before"` has no receiver.
2. Registering a listener via `context.addApplicationListener(...)` **after** that publish. Publishing `"after"` is received, yet the older event is not replayed.
3. An `@EventListener` bean declared upfront in `Config` receives `ReadySignal` published **after refresh**, confirming annotation-based handling works when registered at the proper lifecycle point.

This is an intentional test isolating **registration timing**; do not publish to an unrefreshed context.

### 6.1. Project Structure

~~~text
late-event-listener-demo/
├── pom.xml
└── src/main/java/LateListenerDemo.java
~~~

### 6.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>late-event-listener-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>LateListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. File src/main/java/LateListenerDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class LateListenerDemo {

    public record DiagnosticSignal(String label) { }
    public record ReadySignal(String label) { }

    public static class ReadyListener {
        @EventListener
        public void onReady(ReadySignal event) {
            System.out.println(
                "ANNOTATED_RECEIVED=" + event.label()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ReadyListener readyListener() {
            return new ReadyListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.register(Config.class);
            context.refresh();

            // Only ReadyListener (listening for ReadySignal) is registered.
            List<String> seenByLateListener = new ArrayList<>();
            System.out.println("CONTEXT_READY");

            // Nobody is listening for DiagnosticSignal at this point.
            context.publishEvent(new DiagnosticSignal("before"));
            System.out.println(
                "BEFORE_COUNT=" + seenByLateListener.size()
            );

            // Registered after refresh: receives NEW events,
            // does not replay already-published events.
            ApplicationListener<ApplicationEvent> lateListener =
                new ApplicationListener<ApplicationEvent>() {
                    @Override
                    public void onApplicationEvent(
                            ApplicationEvent event) {
                        if (event instanceof PayloadApplicationEvent<?> wrapped
                                && wrapped.getPayload()
                                   instanceof DiagnosticSignal signal) {
                            seenByLateListener.add(signal.label());
                            System.out.println(
                                "LATE_RECEIVED=" + signal.label()
                            );
                        }
                    }
                };

            context.addApplicationListener(lateListener);

            context.publishEvent(new DiagnosticSignal("after"));
            System.out.println(
                "AFTER_COUNT=" + seenByLateListener.size()
            );

            // @EventListener was registered during context.refresh().
            context.publishEvent(new ReadySignal("after-refresh"));
            System.out.println("DONE");
        }
    }
}
~~~

In the `late-event-listener-demo` directory, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines **printed by the program itself** in order (excluding extra Maven messages):

~~~text
CONTEXT_READY
BEFORE_COUNT=0
LATE_RECEIVED=after
AFTER_COUNT=1
ANNOTATED_RECEIVED=after-refresh
DONE
~~~

### 6.4. Explaining the Results

**Before adding the listener:** `context.refresh()` has finished, yet the configuration only has `ReadyListener` listening for `ReadySignal`; there is no listener for `DiagnosticSignal`. Calling `context.publishEvent(new DiagnosticSignal("before"))` does not grow `seenByLateListener`; prints `BEFORE_COUNT=0`.

**Late listener registration:** `context.addApplicationListener(lateListener)` registers the listener directly on the active context. Because the listener method accepts `ApplicationEvent`, it can observe framework events; the code filters for `PayloadApplicationEvent<?>` carrying a `DiagnosticSignal` payload. After publishing `"after"`, the listener prints `LATE_RECEIVED=after`, the list grows to one, and `AFTER_COUNT=1`. There is no `LATE_RECEIVED=before`, proving **there is no replay**.

**The @EventListener method:** `ReadyListener` is a non-lazy bean defined by `Config` from the start. Spring registers `onReady` during refresh. When `ReadySignal("after-refresh")` is published, `ANNOTATED_RECEIVED=after-refresh` appears.

**Why not `@Async`?** To separate registration errors from worker-waiting issues, the example intentionally uses default synchronous dispatch. The program has no thread races or sleeps, making output easy to verify.

**Illustration scope:** the example does not claim every event published during any `refresh` phase is lost. It demonstrates **an event dispatched after refresh yet before a new listener was registered**. This is the simplest, most consistent case for understanding the mechanism.

### 6.5. Reordering to Fix It

If the application controls listener registration from the start, reorder as:

~~~java
// With an appropriate context:
context.addApplicationListener(lateListener);
context.refresh();
context.publishEvent(new DiagnosticSignal("after-registration"));
~~~

This is an **illustrative snippet**; do not copy it verbatim into the program above without moving `lateListener`'s declaration and context setup. In production, configuring listener registration at bootstrap is usually better than installing a dynamic listener once the application is already running.

Additionally, replacing a dynamic listener with a non-lazy `@EventListener` Spring bean declared in initial configuration is an appropriate choice for events **published after refresh**.

## 7. Is @PostConstruct a Good Place to Publish Mandatory Events?

Usually **no**, if the receiver relies on an `@EventListener` method that is only registered after regular singletons have been instantiated. `@PostConstruct` executes during bean creation; applications should not assume every other event method is already registered at that moment.

Risky example:

~~~java
@Component
public class BootstrapPublisher {

    private final ApplicationEventPublisher publisher;

    public BootstrapPublisher(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostConstruct
    public void init() {
        publisher.publishEvent(new CacheWarmupRequested("products"));
    }
}
~~~

This snippet requires importing `PostConstruct`, `Component`, `ApplicationEventPublisher`, and defining `CacheWarmupRequested`. It **does not guarantee** the bean handling `@EventListener(CacheWarmupRequested.class)` is registered in time.

**Alternatives depending on goal:**

- If the initialization step is **mandatory and part of the same use case**, call the data-preparing service directly instead of relying on an event listener whose registration state is uncertain.
- If you want a step to start **once the context finishes refreshing**, use `@EventListener(ContextRefreshedEvent.class)` on a properly declared bean in the context; with parent–child contexts, filter by source context.
- For **Spring Boot** applications needing work at the end of startup, consider `ApplicationRunner`/`CommandLineRunner` or `ApplicationReadyEvent` depending on readiness and ordering contracts.
- If you only need to wait until **all basic singletons are created**, `SmartInitializingSingleton` is a useful lifecycle callback, yet **do not assume every other `@EventListener` has already been registered before your `SmartInitializingSingleton` callback**; `EventListenerMethodProcessor` uses this same callback type.
- If the event is **mandatory information that must not be lost**, move to a durable outbox/job store rather than merely shifting annotations.

## 8. Spring Boot Startup Events: Before and After ApplicationContext

Spring Boot adds lifecycle events for `SpringApplication`. Several are emitted **before `ApplicationContext` exists**, making bean-annotation registration too late.

Common milestone diagram in Spring Boot:

~~~text
SpringApplication.run()
    |
    +-- ApplicationStartingEvent               [context not yet created]
    |
    +-- ApplicationEnvironmentPreparedEvent    [context not yet created]
    |
    +-- ApplicationContextInitializedEvent
    |
    +-- ApplicationPreparedEvent               [before refresh]
    |
    +-- context.refresh()
    |     +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent                [after refresh]
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent                  [after runners]
~~~

Liveness/readiness and web server events add corresponding milestones; the diagram focuses solely on **listeners registered too late**.

### 8.1. How to Listen to Early Boot Events

For `ApplicationStartingEvent`, register the listener **before calling `run`**:

~~~java
// Illustration in the main class of a Spring Boot application.
SpringApplication app = new SpringApplication(MyBootApp.class);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        System.out.println("Boot startup is beginning");
    }
);

app.run(args);
~~~

This is a Spring Boot application snippet requiring corresponding dependencies/imports; **it does not belong** to the plain Spring Framework project in section 6. Listeners like this are known to `SpringApplication` before startup events fire and thus can receive early events.

Another documented option in Spring Boot is `SpringApplicationBuilder.listeners(...)` or registration via `META-INF/spring.factories` under the key:

~~~properties
org.springframework.context.ApplicationListener=com.example.EarlyStartupListener
~~~

Early listeners **must not assume bean injection or a full ApplicationContext exists**, since their purpose is running in the pre-context phase.

### 8.2. Events Emitted After Refresh

Spring Boot's `ApplicationStartedEvent` fires **after refresh but before runners**; `ApplicationReadyEvent` fires **after runners**, near the point where Boot considers the application ready. A normally Spring-registered `@EventListener` bean can listen to events emitted after refresh.

However, do not use `ApplicationReadyEvent` for work that must **finish before the application is ready** without explicitly designing blocking/readiness policies; long-running or async listeners can alter startup behavior. For work that must complete before readiness, a synchronous `ApplicationRunner` expresses intent more clearly.

**Do not confuse names:** Spring Framework's `ContextStartedEvent` only fires when `ApplicationContext.start()` is explicitly invoked per lifecycle semantics, and is **not** equivalent to Spring Boot's `ApplicationStartedEvent`.

## 9. Other Causes That Look Like Missed Events

### 9.1. @TransactionalEventListener Without a Transaction

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderPlaced(OrderPlaced event) {
    // ...
}
~~~

By default, `@TransactionalEventListener` runs only when the published event is bound to a matching transaction. If the publisher is called **outside a transaction**, the listener will not execute (default `fallbackExecution=false`), even though it **was already registered beforehand**.

To handle non-transactional calls, you may choose `fallbackExecution=true` when genuinely appropriate. However, this changes **the business contract**; do not enable it merely to "make tests green". For critical data requiring commit guarantees, use a real transaction or an outbox.

### 9.2. Event Type or Generic Mismatch

A record event:

~~~java
public record OrderPlaced(long orderId) { }
~~~

is not a subclass of another custom `ApplicationEvent`. If a listener declares a mismatched type, the multicaster will filter it out. With `PayloadApplicationEvent<T>`, pay attention to generics and how Spring wraps payloads; the simplest option is usually an `@EventListener` method accepting the `OrderPlaced` payload class directly.

### 9.3. Condition Is False

~~~java
@EventListener(condition = "#event.urgent")
public void onAlert(AlertEvent event) {
    // ...
}
~~~

This is an illustrative snippet; actual SpEL/property access depends on the event and parameter name preservation. If the condition evaluates false or the expression is invalid, the method either does not run or raises an expression error; that is not evidence that the event arrived before registration. When needed, temporarily remove the condition in a minimal integration test to isolate the fault.

### 9.4. Async Has Not Finished Yet

With `@Async @EventListener`, the handler may have been scheduled yet not finished executing. Asserting immediately after `publishEvent(...)` can observe an empty variable/list and misdiagnose the event as lost. Use a `CountDownLatch`, future, result state, or await utility with a timeout to verify outcomes.

### 9.5. Listener Belongs to Another Context

A producer in a child context does not automatically broadcast to sibling contexts. Spring propagates certain events from child up to parent, yet does not symmetrically push parent events down to children. Check event source/context, parent chain, and where the listener is actually registered.

### 9.6. Listener Errored Without Observable Logs

An exception in a synchronous listener may propagate; if an `ErrorHandler` is present or the exception is caught/swallowed, the publisher can still return. Async errors generally pass through worker exception handling. In either case, not seeing side effects is **not enough** to conclude the event arrived before registration.

## 10. Solution Selection Table by Timing and Requirements

| Scenario | Typically appropriate solution | Why |
| --- | --- | --- |
| Listener needs `ContextRefreshedEvent` of initial refresh | Register `ApplicationListener` before `refresh`, or properly configured non-lazy `@EventListener` bean | Present before the context emits refresh |
| Custom event published inside `@PostConstruct` | Move publish to post-refresh or invoke service directly | Avoids depending on registration still in bootstrap |
| Must listen to Boot's `ApplicationStartingEvent` | `SpringApplication.addListeners(...)` or early listener discovery | Context beans do not exist yet |
| Component dynamically added to a running context | Accept receiving future events only; use storage if history is required | Event bus does not replay the past |
| Mandatory reference data initialization | Synchronous runner, appropriate lifecycle hook, or migration | Clearer completion/failure contract |
| Current state must be synced for late subscribers | Send snapshot/state reconciliation on registration, then listen for change events | Does not rely on past events |
| Committed events must all be delivered to consumers | Transactional outbox + retry/idempotency | Survives crashes and registration gaps |
| `AFTER_COMMIT` listener skips event | Check transaction phase and fallback policy | Not every skip is due to late registration |
| Async listener has not updated projection | Wait for outcome / monitor worker; check executor | May simply not have run yet, not a lost event |
| Multiple ApplicationContexts | Pick the right context, inspect hierarchy and filter source | Avoids both missed and duplicate deliveries |

### 10.1. Prefer Current-State Sync Over "Replay Everything"

If a new listener only needs **to know the current state** (e.g., a catalog cache when a module turns on), a **snapshot + change events** flow is usually better than replaying event history:

~~~text
Listener registers
       |
       +--> load current data snapshot
       |
       +--> receive subsequent change events
       |
       +--> reconcile with version/checkpoint
~~~

However, if snapshot loading and listener registration are non-atomic, a **race** can occur between reading the snapshot and starting to listen. Production solutions require versions/checkpoints, registering first then reconciling, or proper transaction/snapshot mechanisms. Do not trade a "missed pre-registration event" bug for a snapshot-loading race.

### 10.2. When Every Event Is Truly Needed: Durable Outbox

Suppose `OrderPlaced` is a critical fact for billing:

~~~text
T1 BEGIN
  save order
  insert outbox(eventId, aggregateId, type, payload)
T1 COMMIT
              |
              v
Outbox dispatcher / broker
              |
              v
Consumer registers or starts late
              |
              v
reads from offset/checkpoint + idempotent processing
~~~

When the publisher commits, the outbox event has been saved in the same transaction. Consumers can process it after restarting, provided the log/queue retains messages with proper retention/ack. Deduplication/idempotency is necessary because delivery is typically at-least-once.

**Do not simply re-invoke `publisher.publishEvent(...)` with an old event** without knowing consumer state, because both new and existing listeners may react, creating duplicate side effects such as emails, payment charges, or inventory holds.

## 11. Testing: Verify Timing Instead of Using Thread.sleep

A solid integration test must prove **when the listener existed** relative to **when the event was published**.

### 11.1. Case Matrix

| Test | Expectation |
| --- | --- |
| Publish after context refresh before dynamic listener is added | No handler invocation for the old event |
| Add listener then publish a new event of the same type | New event is received exactly once |
| Register listener before refresh | Listener is present when `ContextRefreshedEvent` fires |
| Non-lazy `@EventListener` bean in initial config | Receives custom event published after refresh |
| Publish inside init callback before method registration finishes | Test exposes unreliability of delivery; shift milestone as needed |
| Early Spring Boot listener registered before `run` | Receives pre-context Boot startup events |
| Listener registered only as normal Boot bean for early event | Not expected to receive events emitted before context |
| `@TransactionalEventListener` published outside transaction | Skipped by default; distinguish from registration gap |
| Slow `@Async` processing | Test waits for result with timeout instead of asserting immediately |
| Event type differs from handler signature | Listener filtered out, not treated as timing loss |
| Parent/child/sibling contexts | Verify propagation path and context source |
| Retry/replay from outbox after consumer restart | Consistent event ID and working idempotency |

### 11.2. Testing with Counters/Latches

For synchronous listeners, invocation counts/counters can be checked right after `publishEvent`. Section 6's demo uses a `List<String>` and deterministic output without sleep.

For async listeners, use a latch or await utility with a timeout; **do not** write:

~~~java
publisher.publishEvent(new CatalogLoaded("A"));
Thread.sleep(100);
assertEquals(1, handledCount.get());
~~~

This is an **anti-pattern**: schedulers, CI load, and executor queues can make 100 ms insufficient, causing flaky tests. The right approach is waiting for a signal emitted by the handler before asserting state.

### 11.3. Notes on @RecordApplicationEvents

Spring TestContext supports `@RecordApplicationEvents` and `ApplicationEvents` to record events published **within the test's scope**. It helps prove code published an event and filter by type. However:

- Events emitted **before the test began recording** will not appear in the test's list.
- Having an event in the recorder **does not mean** a specific listener succeeded.
- The test recorder is not a production event store.
- To test a listener, measure the listener's actual output or use a capturing listener.

When testing timing bugs, measure **both** publication and consumption; asserting only recorder event counts can hide registration issues.

### 11.4. Do Not Rely on Accidental Bean Creation Order

A test intentionally publishing an event inside a constructor or `@PostConstruct` may pass or fail differently if bean creation order or dependencies shift. To verify "late listeners do not replay", section 6's demo intentionally **controls ordering**: refresh finishes -> publish A -> register listener -> publish B. That milestone sequence is deterministic and repeatable.

If real tests must guarantee a bootstrap step, adjust the architecture to establish an **explicit lifecycle milestone contract** rather than writing tests pinned to lucky initialization order.

## 12. Logging and Metrics to Find Missed Events

An observability strategy should log these checkpoints:

~~~text
phase=publish    event=CatalogLoaded eventId=e1 context=app-1
phase=register   listener=CatalogListener  context=app-1
phase=handle     event=CatalogLoaded eventId=e2 listener=CatalogListener
phase=complete   event=CatalogLoaded eventId=e2 status=success
~~~

In the logs above, `e1` appears **before** the register line and has no handle line; `e2` appears after registration and is processed. That trace fits the timing hypothesis. Still, verify logs share the same clock/context; distributed logs can have skewed timestamps.

Useful log fields:

- `eventId`, `eventType`, `aggregateId`, `correlationId`.
- `contextId`, `listenerName`, `listenerBeanName`.
- `startupPhase` or `refreshStarted/refreshCompleted` milestones.
- `threadName`, `transactionPhase`, `isAsync`.
- `publishedAt`, `registeredAt`, `handledAt`.
- `success/failure/skipped` and error code.

Custom metrics might include:

~~~text
app_event_published_total{eventType="CatalogLoaded"}
app_event_handled_total{listener="CatalogListener"}
app_listener_registered_total{type="CatalogLoaded"}
app_event_processing_errors_total{listener="CatalogListener"}
app_event_backlog{consumer="billing"}
~~~

These names are **suggestions**, not default built-in Spring metrics. Do not put `eventId`/`orderId` in Prometheus labels because it creates excessive cardinality; keep IDs in logs and traces.

### Enabling Framework Logging Carefully

In diagnostic environments you can raise log levels for `org.springframework.context.event` or context lifecycle, yet **do not expect the framework to log every custom event publisher/consumer automatically at that level**. In production applications, add instrumentation at publish and handle boundaries, limit payloads, and never log tokens/PII.

## 13. Common Mistakes When Fixing

1. **Merely adding `@EventListener` and expecting old events:** registration does not replay history.
2. **Marking the listener `@Lazy` hoping it initializes on event arrival:** Spring warns lazy listener beans may not have their methods registered.
3. **Calling `publishEvent` in a constructor:** container and other beans are not guaranteed ready.
4. **Publishing in `@PostConstruct` assuming all `@EventListener`s exist:** depends on `EventListenerMethodProcessor`'s registration point.
5. **Using `@DependsOn` as a replay system:** bean creation dependencies do not replay past events.
6. **Assuming `earlyApplicationEvents` is a durable queue:** it is only a bounded bootstrap buffer.
7. **Catching Spring Boot `ApplicationStartingEvent` with an `@Bean` listener in context:** the context does not exist yet at event time.
8. **Calling `publishEvent` before refresh on a newly created context as a "queue":** the multicaster may not be ready.
9. **Confusing `@TransactionalEventListener` lacking a transaction with a registration gap:** the listener may be registered yet ineligible for the phase.
10. **Confusing incomplete `@Async` work with a lost event:** wait for the outcome.
11. **Failing to check event type/generic/condition:** the listener exists yet does not match.
12. **Failing to check parent-child contexts:** publishing does not automatically reach every context in the JVM.
13. **Concluding publish succeeded just because no exception was thrown:** does not confirm any listener processed it.
14. **Re-emitting old events arbitrarily:** can trigger duplicate side effects in listeners that already received them.
15. **Using an in-memory queue as a restart-safe delivery guarantee:** lost on crash/process kill.
16. **Lacking idempotency when enabling replay:** listeners may execute the same side effect multiple times.
17. **Relying on accidental bean creation order:** refactoring or adding dependencies brings the bug back.
18. **Reading only publisher logs without instrumenting handlers/registration:** lacks evidence to identify the cause.
19. **Tests asserting only that `@RecordApplicationEvents` captured an event:** does not prove the handler ran.
20. **Failing to define whether an event is a fact or a command:** timing bugs can mask a workflow needing orchestration or a direct call.

## 14. Remediation Levels by Reliability Requirement

### Level 1: Register Properly and Publish at a Sensible Time

Use when events are internal notifications that do not require stored history:

1. Include listeners in the context from the start; use `@EventListener` on non-lazy beans or `ApplicationListener` registered before refresh when needed early.
2. Publish events once the context has listeners; for bootstrap, choose post-refresh or an appropriate runner.
3. Add integration tests with real listeners and publishers.
4. Log publish/handle clearly to inspect future builds.

### Level 2: State Reconciliation for Late Subscribers

Use when a new listener only needs **current state**, not every historical fact:

1. Subscriber registers or activates.
2. Read current snapshot/state with an appropriate version.
3. Apply subsequent change events using checkpoints or race-prevention mechanisms.
4. Use idempotency so state transitions are not applied twice.

Example: a per-tenant configuration cache can load a snapshot from the DB before serving, then receive change events; missing an old `ConfigInitialized` no longer leaves the cache permanently stale.

### Level 3: Make Business Events Durable

Use when every event carries an obligation to reach consumers, even if a consumer is offline:

1. Save business state and outbox in the same transaction.
2. Dispatcher delivers events from the outbox/log per retry and retention policies.
3. Consumer processes events with stable event IDs, checkpoints, and idempotency.
4. Provide dead-letter/quarantine, alerts, and selective replay capability.
5. Test crash/restart, duplicate delivery, and late-starting consumers.

At Level 3, **Spring `ApplicationEventPublisher` can still be used for internal events**, yet it is no longer the sole component responsible for delivery.

## 15. Self-Check Exercises

1. A listener is registered after `context.publishEvent(new CatalogLoaded("A"))`. Does it automatically receive `A`? Why?
2. Why does putting `@EventListener` on a bean not guarantee the method is ready when another bean runs `@PostConstruct`?
3. What is the role of `earlyApplicationEvents` in `AbstractApplicationContext`, and what is its most important limitation?
4. Why is `ContextRefreshedEvent` a better milestone than a constructor for publishing an event that needs initially configured listeners?
5. When needing to listen for Boot's `ApplicationStartingEvent`, should you use an `@Bean ApplicationListener` in context or `SpringApplication.addListeners(...)`?
6. In the demo, why does `LATE_RECEIVED=after` appear while `LATE_RECEIVED=before` does not?
7. If an `@EventListener` bean is lazy and fails to register at the expected lifecycle stage, how can that be fixed?
8. If `@TransactionalEventListener(AFTER_COMMIT)` does not run when published outside a transaction, is it due to late listener registration?
9. Why might an `@Async` handler have no visible result right after `publishEvent` even though it received the event?
10. When a new listener only needs current configuration, what advantage does snapshot + version have over replaying all old events?
11. If a domain event is a business obligation that must not be lost, what mechanism is needed beyond the in-process event bus?
12. In a context hierarchy, do events from a parent automatically flow down to all children?
13. When testing timing, why is **refresh -> publish A -> register -> publish B** more reliable than depending on bean creation order?
14. Why can manually re-emitting old events cause duplicate emails or payments?
15. What is the difference between "event published", "listener ran", and "side effect completed"?

**Answer key:** (1) no, the event bus does not automatically replay history; (2) annotation processing happens at the end of singleton pre-instantiation; (3) buffers certain early events during refresh, not a durable queue for late subscribers; (4) basic listener registration completes before that milestone; (5) `addListeners`; (6) the listener was added only after the first event; (7) use a properly discovered/initialized bean, not unintentionally lazy; (8) no, it is a transaction phase condition; (9) worker executes asynchronously; (10) syncs current state and prevents races via versions; (11) transactional outbox/log + retry/idempotency; (12) no; (13) milestones are explicitly controlled; (14) some consumers already processed them; (15) three distinct guarantee levels.

## 16. Summary

**"Event published before listener registration"** is a bug of **timing, scope, and delivery contract**, not merely a missing annotation.

- Listeners added after an event was dispatched **do not automatically receive past events**.
- During `refresh()`, Spring provides **bounded early event buffering** for bootstrap, yet `@EventListener` methods may be registered at a later point.
- Boot events emitted before the context exists require listeners registered early via `SpringApplication`, not beans created afterward.
- To run work at a specific startup milestone, choose the intended lifecycle hook or runner; do not rely on arbitrary `@PostConstruct` publishing.
- For late subscribers needing current state, use race-safe snapshot/reconciliation.
- For guaranteed delivery across crashes, use storage/outbox and idempotent consumers; Spring's event bus does not provide durable replay.
- Diagnosis must distinguish registration gaps from `@TransactionalEventListener` phases, `@Async` delays, type mismatches, false conditions, or context hierarchies.

## References

- Spring Framework 6.2 — *Application Events and Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2.8 Javadoc — *EventListenerMethodProcessor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot Reference — *Application Events and Listeners*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Source — *AbstractApplicationContext, earlyApplicationEvents/registerListeners*: https://github.com/spring-projects/spring-framework/blob/v6.2.8/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java