# Avoiding Duplicate Listener Registration and Repeated Side Effects in Spring Boot

**Topic:** Spring Boot Application Runtime → Listener. This lesson guides you through identifying and resolving situations where a single event triggers side effects from multiple listeners, or where the same business operation is re-emitted. You need a solid grasp of three things: **listener registration**, **event dispatch**, and **side-effect idempotency**. The hands-on example uses **Java 17+**, **Spring Boot 3.5.x**, Spring MVC, and Maven.

## 1. Objectives

After completing this lesson, you should be able to:

1. List the ways to register `ApplicationListener` and `@EventListener` in Spring Boot.
2. Distinguish **one event with two listeners** from **two events published to one listener**.
3. Distinguish **the same listener object added twice** from **two listener instances of the same class**.
4. Diagnose repeated event handling caused by `@Component`, `@Bean`, `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, `META-INF/spring.factories`, or parent/child contexts.
5. Build a lab with one default bean listener and one listener added via an optional API; verify callback counts over HTTP.
6. Guard a simulated side effect inside **one ApplicationContext** using a shared singleton and `AtomicBoolean.compareAndSet`, while explaining why this is not safe enough for real transactions.
7. Choose the right durable deduplication mechanism for events with stable IDs, multiple replicas, retries, and partial failures.
8. Recognize that `@Order`, `@Async`, and `@TransactionalEventListener` each have distinct roles and **do not** guarantee exactly-once execution.

**Core rule:** remove redundant registrations to maintain **a single business owner**, then design side effects to tolerate **at-least-once delivery** across retries, restarts, or multiple instances. Never infer how many times data was mutated from how many log lines appeared.

## 2. Why Do Side Effects Easily Repeat?

Suppose an application publishes `ApplicationReadyEvent` once after startup. Two listeners receive the event and both call a function sending a request to an external system:

~~~text
ApplicationReadyEvent (1 event)
     |
     +---- ListenerBean ----------> sendNotification()
     |
     +---- ListenerFromApi -------> sendNotification()
                                  two side effects may occur
~~~

That is **duplicate handling due to multiple registrations**. Conversely:

~~~text
Publisher publish(event-123) ------> Listener
Publisher retry(event-123) --------> Listener
                                      same business event received twice
~~~

That is **duplicate delivery due to publisher/retries**, even when there is only a single listener.

There is also the case where each context emits a valid event:

~~~text
parent ApplicationContext -- ContextRefreshedEvent(parent)
child ApplicationContext  -- ContextRefreshedEvent(child)
                             |
                             +-- forwarded to parent listeners
~~~

A parent listener can receive both the parent's event and the child's event. This is a propagation feature, not necessarily a registration bug.

### 2.1. Side Effects Carry Different Risks

| Side effect | If executed twice | Appropriate response |
|---|---|---|
| Logging "ready" | Noisy logs, skewed metrics | Fix registration and log metadata |
| Building cache from immutable data | May waste CPU, overlap threads | Single owner, idempotent rebuild |
| Starting consumer/scheduler | Two workers consume the same work | Lifecycle owner, controlled start/stop |
| Sending email/SMS | Duplicate messages to users | Event ID + inbox/outbox/idempotency |
| Writing audit records | Duplicates or inaccurate reports | Unique business key, audit rules |
| Payment/granting permissions | Double charge or duplicate grants | Idempotency key at target system and durable dedupe |

Do not assume only the event framework causes duplicates. With brokers, client retries, or multiple replicas, failures often sit outside the Spring event bus.

## 3. Listener Registration Paths to Audit

| Registration | How it is used | When appropriate | Overlap risk |
|---|---|---|---|
| Bean implementing `ApplicationListener<E>` | `@Component class X implements ApplicationListener<E>` | Listener needs DI and context is ready | App also adds `new X()` via API |
| `@EventListener` method | `@EventListener void on(E event)` on a bean | Runtime / late startup events | Another method handles the same side effect |
| `@Bean` listener | Factory method returning `ApplicationListener<E>` | Programmatically configured listener | Same logic also picked up by component scan |
| `SpringApplication.addListeners(...)` | `app.addListeners(new X())` | Early events before beans exist | Adds an instance duplicating bean behavior |
| `SpringApplicationBuilder.listeners(...)` | Builder attaching listeners | Projects using builder/context hierarchy | Listener attached to multiple contexts |
| `META-INF/spring.factories` | Interface key and implementation FQCN | Library auto-registration | App also manually instantiates that listener |
| Context hierarchy | Child events forwarded to parent | Parent monitors multiple children | Parent unintentionally handles child events |

**Note:** Some very early events such as `ApplicationStartingEvent` happen before `ApplicationContext` is created. You cannot rely on `@EventListener` in a regular bean to receive them; use the API or factories. For `ApplicationReadyEvent`, the context has already refreshed, so a bean listener is simple and easy to manage.

Do not add both `@Component` and `addListeners(new ...)` just to "be sure the event is received." Having two listeners for two distinct purposes (e.g., one for telemetry, one for cache warmup) is valid; just avoid two places owning the same non-idempotent side effect.

### 3.1. Does Adding the Same Object Twice Always Run It Twice?

**You cannot assume so.** Some internal listener collections use sets that deduplicate by equality on **the exact same object**. However, if code calls `new MyListener()` twice, each call creates a distinct instance, so equality and registration outcomes differ. In particular, a Spring-managed instance and a manually constructed instance are usually **two distinct objects**.

Investigations must record **class name, bean name/instance identity, and context**. Do not use class name alone as proof that two callbacks came from the same object.

## 4. Lab Project: Counting Callbacks and Simulated Effects

Create a project from Spring Initializr:

- Maven, Java 17, Spring Boot 3.5.x.
- Group `com.example`, Artifact `listener-repeat-lab`, Package `com.example.listenerrepeat`.
- Dependency **Spring Web**, packaging **JAR**.
- Keep the generated `pom.xml` and Maven Wrapper.

Structure:

~~~text
listener-repeat-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/listenerrepeat/
    ListenerRepeatApplication.java
    ReadyEffect.java
    BeanReadyListener.java
    ApiReadyListener.java
    CountController.java
  src/main/resources/application.properties
~~~

These are separate Java files within **the same Maven project**, not standalone files compiled via `javac` without Spring dependencies. Every public class must reside in a matching file name.

### 4.1. Main: Enabling the Second Registration via JVM System Property

File `ListenerRepeatApplication.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ListenerRepeatApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ListenerRepeatApplication.class);

        if (Boolean.getBoolean("lab.extra-listener")) {
            app.addListeners(new ApiReadyListener());
        }

        app.run(args);
    }
}
~~~

Without `-Dlab.extra-listener=true`, only the regular bean listener is registered in the project. When enabled, `SpringApplication.addListeners(...)` creates a **second registration** for the same `ApplicationReadyEvent`.

`Boolean.getBoolean(...)` reads a **Java system property**, not `application.properties`. When running the JAR, pass `-Dlab.extra-listener=true` **before `-jar`**. If placed after the JAR name, `SpringApplication` may see an application argument, yet the JVM's `Boolean.getBoolean(...)` will not treat it as a system property.

### 4.2. Shared Singleton Holding Two Counters

File `ReadyEffect.java`:

~~~java
package com.example.listenerrepeat;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ReadyEffect {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger effects = new AtomicInteger();
    private final AtomicBoolean once = new AtomicBoolean();

    public void handle(String source) {
        int attempt = attempts.incrementAndGet();
        boolean executed = once.compareAndSet(false, true);

        if (executed) {
            // Demo side effect: only increments an in-memory counter.
            effects.incrementAndGet();
        }

        System.out.println("LAB_READY source=" + source
                + " attempt=" + attempt
                + " effectExecuted=" + executed);
    }

    public Counts counts() {
        return new Counts(attempts.get(), effects.get());
    }

    public record Counts(int attempts, int effects) {
    }
}
~~~

Two separate concepts are tracked:

- `attempts` increments **every time** a listener calls `handle`.
- `effects` increments only if `once.compareAndSet(false, true)` succeeds.

Both listeners point to **the same `ReadyEffect` singleton bean**, so CAS inspects one shared flag and only one thread succeeds within a single process/context. The program uses an in-memory counter to avoid calling external services, which suffices to illustrate both the risk and its limits.

**Never apply this pattern directly to payments, emails, or critical data.** The flag is flipped before the effect; if the real effect fails or the process dies, state may not reflect the outcome. Another replica has its own separate flag. `AtomicBoolean` only demonstrates avoiding repetition **inside one JVM object**, not exactly-once execution.

### 4.3. Bean Listener Using @EventListener

File `BeanReadyListener.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BeanReadyListener {

    private final ReadyEffect effect;

    public BeanReadyListener(ReadyEffect effect) {
        this.effect = effect;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        effect.handle("bean");
    }
}
~~~

This is the sole default owner for the simulated side effect. `@EventListener` is discovered only because the class is a Spring-managed bean. If you also instantiate `new BeanReadyListener(...)` outside Spring and register it manually, you add another execution path.

### 4.4. Listener Registered via API

File `ApiReadyListener.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public final class ApiReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        event.getApplicationContext()
                .getBean(ReadyEffect.class)
                .handle("api");
    }
}
~~~

This class **has no `@Component`** and is not listed in factories. It runs only when `main()` calls `addListeners(new ApiReadyListener())`. At `ApplicationReadyEvent`, the context has already refreshed, so the example can look up `ReadyEffect` from the context. **Do not** do this in `ApplicationStartingEvent` or other early events because the context does not fully exist yet.

### 4.5. Read-Only API for Counters

File `CountController.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CountController {

    private final ReadyEffect effect;

    public CountController(ReadyEffect effect) {
        this.effect = effect;
    }

    @GetMapping("/demo/counts")
    public ReadyEffect.Counts counts() {
        return effect.counts();
    }
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=listener-repeat-lab
server.address=127.0.0.1
server.port=8080
~~~

Binding `127.0.0.1` is just for local learning. The project includes Spring Web, and Jackson serializes the Java record to JSON.

## 5. Scenario A — Single Registration Only

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Wait for startup to finish. Because `lab.extra-listener` is off by default, the console shows the marker:

~~~text
LAB_READY source=bean attempt=1 effectExecuted=true
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8080/demo/counts
~~~

Expect HTTP 200 with a body equivalent to:

~~~json
{"attempts":1,"effects":1}
~~~

This is evidence of **one callback into `ReadyEffect` and one simulated effect** in the current context. Do not infer that the entire application has only one framework listener; Spring Boot has many other listeners for its own subsystems.

## 6. Scenario B — Two Registrations for the Same ApplicationReadyEvent

Stop the previous run and build the JAR:

~~~bash
./mvnw clean package
java -Dlab.extra-listener=true -jar target/listener-repeat-lab-0.0.1-SNAPSHOT.jar
~~~

On Windows replace `./mvnw` with `./mvnw.cmd`. If the project version differs from `0.0.1-SNAPSHOT`, use the actual JAR name in `target/`.

The logs will show **two `LAB_READY` markers** with sources `bean` and `api`. One valid order is:

~~~text
LAB_READY source=api attempt=1 effectExecuted=true
LAB_READY source=bean attempt=2 effectExecuted=false
~~~

The reverse order is also valid. `@Order` is not configured in this lab and is unnecessary for the expected outcome. Call:

~~~bash
curl -i http://127.0.0.1:8080/demo/counts
~~~

Expected:

~~~json
{"attempts":2,"effects":1}
~~~

**Interpretation:** two callbacks invoked the same shared bean, yet CAS allowed the effect to increment only once. This is a case of two eligible listeners receiving **the same ready event**, not Boot publishing ready twice in a single run.

In a separate test copy, if you remove `if (executed)` and increment `effects` unconditionally, running with two listeners yields `attempts=2, effects=2`. That is the behavioral bug we want to prevent. Never modify production code just to test against real payments, emails, or external APIs.

Running again **without** `-Dlab.extra-listener=true` returns to `attempts=1, effects=1` on a fresh context. The counter resetting on restart proves an in-RAM flag is not a durable deduplication mechanism.

### 6.1. Comparison Table

| Configuration | Callbacks into service | Simulated effects | Conclusion |
|---|---:|---:|---|
| Default | 1 | 1 | Single owner |
| System property enabled | 2 | 1 | Two registrations, local guard |
| Property enabled and unconditional increment | 2 | 2 | Duplicate side effect |

These numbers apply when the project runs **one context, one successful startup, and no other code calling `ReadyEffect`**. Test suites, DevTools, or application restarts produce additional lifecycle runs that must be accounted for separately.

## 7. Anti-Patterns That Commonly Cause Overlapping Registrations

### 7.1. A Class Is Both @Component and Instantiated with new in main

~~~java
@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // If there is a side effect, it may run more times than intended.
    }
}
~~~

And inside `main()`:

~~~java
app.addListeners(new ReadyListener());
~~~

These are **two illustrative snippets**; compiling requires appropriate imports and classes. `ReadyListener` is scanned by Spring as a bean, while a fresh instance is also added via the API. Do not mistake two objects for a single listener.

### 7.2. Having spring.factories While Still Calling addListeners Manually

In a library or application resource:

~~~properties
org.springframework.context.ApplicationListener=com.example.ReadyListener
~~~

If `ReadyListener` is also added programmatically, two instances performing the same logic can exist. Inspect the runtime classpath because a dependency JAR can also contain `META-INF/spring.factories`; checking only the app's `src/main/resources` is insufficient.

### 7.3. One Bean Receiving the Same Event via Two Mechanisms

For example, a class implements `ApplicationListener<MyEvent>` and also has an `@EventListener` method invoking the same logic for `MyEvent`. Two distinct dispatch paths can trigger two side effects even though there is only one class instance. Best practice is picking one owner method and letting any other listener perform only independent work (if genuinely needed).

### 7.4. Multiple @EventListener Methods Performing the Same Side Effect

If multiple methods across components all send notifications on `OrderPaidEvent`, each method may be a valid Spring registration while **the business action is still duplicated**. Choose one service to own notifications and let other listeners handle separate concerns or delegate to one idempotent shared owner.

### 7.5. Mixing Events Before and After Context Initialization

`ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` require early-registered listeners. `ApplicationReadyEvent` is a late event that a Spring bean can handle. Do not create two listeners just because one listens to early events; separate cleanly by event type and responsibility.

## 8. Context Hierarchy: Filtering Events by Source Context

Spring can propagate events from a child context up to a parent context. According to Boot documentation, when using multiple `SpringApplication` instances in a hierarchy, a listener can receive multiple events of the same type.

For `ContextRefreshedEvent`, a bean wanting to process **only its own context** can filter:

~~~java
@Component
public class LocalRefreshListener {

    private final ApplicationContext ownContext;

    public LocalRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }

        System.out.println("LAB_OWN_CONTEXT_REFRESHED");
    }
}
~~~

This is a **snippet** requiring imports for `ApplicationContext`, `ContextRefreshedEvent`, `EventListener`, and `Component`. The `!=` check compares context object identity; do not rely on names, PIDs, or similar-looking log lines. For `ApplicationReadyEvent`, `event.getApplicationContext()` can be checked similarly.

If a listener is intentionally designed to monitor all child contexts, do not filter them out; instead use context IDs to distinguish valid events and avoid running a non-idempotent global side effect for every child.

## 9. Publishing an Event Twice Differs from Registering Twice

Even with only one listener, systems still encounter:

- Request retries after timeouts.
- Message broker redeliveries because a consumer did not ack.
- Scheduler/job restarts.
- Transaction retries.
- Two service paths publishing the same business meaning.
- DevTools restarts or rolling deployments.
- Multiple replicas receiving the same message due to unexpected consumer group/topic settings.

If the same business event can be re-emitted, the listener needs a **stable business event identity**. Java 17 example:

~~~java
public record OrderPaidEvent(
        String eventId,
        String orderId,
        long amountInCents) {
}
~~~

This is an **illustrative data type**, not present in the main lab project. `eventId` must remain constant across retries of the same event. Generating `UUID.randomUUID()` **on every redelivery** turns an old task into a new ID and defeats deduplication. If business logic decides uniqueness by `orderId` and version, design the idempotency key around the real source contract rather than picking a random ID per attempt.

### 9.1. In-Memory Set: Fine for Demos, Not Enough for Production

Logic illustration:

~~~java
private final Set<String> observed =
        ConcurrentHashMap.newKeySet();

@EventListener
public void onOrderPaid(OrderPaidEvent event) {
    if (!observed.add(event.eventId())) {
        return;
    }
    process(event);
}
~~~

This is a **snippet** requiring `process`, `OrderPaidEvent`, and appropriate imports/beans. It has clear risks:

- Restarts wipe the set.
- Every replica has its own separate Set.
- If `process` fails after adding the ID, retries are blocked despite not succeeding.
- If the external effect succeeded yet `process` threw an exception, retries and clearing the marker can duplicate side effects.
- Memory grows unbounded without a retention policy.

Thus `ConcurrentHashMap.newKeySet()`, `AtomicBoolean`, or `synchronized` blocks **do not** guarantee end-to-end exactly-once execution.

### 9.2. Durable Inbox and Unique Constraints

For business logic writing to **the same database**, you can use a table tracking processed events with a unique constraint:

~~~sql
CREATE TABLE consumed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside an application transaction, attempt to insert the event key. PostgreSQL syntax example:

~~~sql
BEGIN;

INSERT INTO consumed_event(consumer_name, event_id)
VALUES ('order-projector', 'evt-001')
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Application checks INSERT row count:
-- 1 row: update business tables in the SAME transaction.
-- 0 rows: event already processed; skip DB side effect.

COMMIT;
~~~

This is a **SQL design pattern**, not a complete runnable script without schema and business tables. The constraint prevents multiple replicas racing on the same key from both committing a new marker. All critical DB updates must sit in the **same transaction** as the marker, otherwise a failure window remains.

When the side effect is an **email, payment gateway, message broker, or external HTTP API**, your DB transaction cannot be atomic with the outside world. Use a transactional outbox, inbox, bounded retries, and the target service's idempotency keys where supported. Exactly-once semantics must be proven across the participating systems' contracts, never inferred from `@EventListener`.

### 9.3. TransactionalEventListener Does Not Automatically Deduplicate

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` only ensures the handler runs after the source transaction commits. It **does not** deduplicate events sharing an ID, stop multiple listeners from registering, or stop publisher retries. By default, when no matching transaction exists, this listener is not invoked (unless fallback is configured).

If an external side effect is needed after commit, consider an outbox so events are not lost if the process crashes between commit and sending. Do not equate `AFTER_COMMIT` with the effect executing exactly once.

## 10. @Order, @Async, and Concurrency Bugs

`@Order` can order listeners in applicable scenarios; it **does not cancel** lower-priority listeners and **does not** deduplicate. If two listeners both send emails, setting orders 1 and 2 still sends twice.

`@Async` lets events run on other threads without deduplicating. Two callbacks can execute concurrently:

~~~text
Thread A: read done=false
Thread B: read done=false
Thread A: execute effect
Thread B: execute effect
~~~

Using a plain boolean with check-then-act introduces races. `AtomicBoolean.compareAndSet` protects a simulated effect inside **one object** as in the lab, yet does not guarantee I/O success and does not coordinate across JVMs.

Exceptions from async listeners are not automatically thrown back to the publisher like synchronous callbacks; you need logging, an error handler, retries, and telemetry. Return values from `@EventListener` methods can be used by Spring to publish follow-up events in synchronous mode, whereas async listeners do not share the same return-to-publish semantics. When explicit publishing is needed, use `ApplicationEventPublisher`.

## 11. DevTools, Tests, Restarts, and Multi-Instance Deployments

An `ApplicationReadyEvent` is typically published once per successful `SpringApplication.run()` of a simple application instance—not "once in the entire lifetime of a deployment."

- **DevTools:** restarts can create a new context, reinitializing listeners.
- **Tests:** multiple contexts in a suite may be cached or recreated.
- **Parent/child:** each context has its own lifecycle; child events can propagate.
- **Multiple `SpringApplication`s:** one JVM can host more than one app/context.
- **Rolling deployments:** each replica emits its own ready event. Using ready events to run migrations or send newsletters can make multiple instances run the same task.
- **Startup failures:** partial side effects can occur before failure, then the process restarts and retries.

For once **per context**, pick a single singleton bean owner aligned with the context lifecycle. For once **per business event**, use durable event IDs. For once **cluster-wide**, use a dedicated job/migration owner, leader election, or architectural distributed coordination—never rely on each replica's ready event.

A `static boolean alreadyRan` flag is a poor solution because of classloaders, tests, memory visibility, restarts, and multiple processes. It also risks blocking valid work in fresh contexts.

## 12. Filtering Logs and Evidence-Based Diagnostics

To find the root cause, log in a pattern like:

~~~text
eventType=ApplicationReadyEvent eventId=... contextId=...
listener=BeanReadyListener bean=beanReadyListener instance=...
attempt=1 effectStarted=true effectSucceeded=true
~~~

`eventId` is an example for custom business events; `ApplicationReadyEvent` has no built-in stable business ID designed for cross-startup deduplication. Do not generate a new ID inside a listener and pretend it is the original event's ID. Instance, context, publisher counts, and event identity fields must come from the true source.

A simple code search query on Unix systems:

~~~bash
grep -R -nE 'ApplicationListener|@EventListener|addListeners|spring.factories' src
~~~

This command searches only `src`, not JAR dependencies. For libraries, inspect `META-INF/spring.factories` on the runtime classpath. `SpringApplication.getListeners()` returns listeners registered on the application instance, **not** the full list of `@EventListener` methods or listener beans discovered later by the context.

### Diagnostic Table

| Symptom | Hypothesis | Check / fix |
|---|---|---|
| One event yet processed twice by bean and API | Overlapping registrations | Pick one owner, remove extra listener |
| Same class name yet different instances | `new` outside container or factory loader | Compare bean name/identity and creation path |
| Identical event IDs | Publisher retry/redelivery | Durable dedupe by stable ID |
| Parent handler receives child event | Context hierarchy | Compare event context with own context |
| Repeats only after DevTools restart | Fresh context | Check lifecycle; do not use static flags |
| Repeats when scaling multiple replicas | Each replica receives same work | Inbox/unique constraint or cluster owner |
| Used `@Async` and sent two emails | Concurrency race | Idempotency key and durable mechanism |
| Guard blocks retries even though effect failed | Flag set too early | Real processing state and recovery |
| Changed `@Order` yet still repeats | Order does not remove registrations | Remove extra owner and deduplicate |
| `@TransactionalEventListener` received twice | Re-emitted event / duplicate handlers | Transaction phases do not prevent duplicates |
| Two logs appear yet only one effect | Two callbacks, local guard worked | Check counters and actual external state |
| App failed startup before ready | Ready event never fired | Use the proper event/hook and stack trace |

## 13. Hands-On Exercises

### Exercise A — Registration Count

1. Run the app with defaults; note the `LAB_READY source=bean` marker.
2. Call `GET /demo/counts`: `attempts=1, effects=1`.
3. Stop the app, enable `-Dlab.extra-listener=true`, and rerun the JAR.
4. Confirm both `bean` and `api` sources appear; order is not a business guarantee.
5. Call the endpoint: `attempts=2, effects=1`. Explain CAS and shared singleton scope.
6. Stop and restart the app; confirm counters belong to the new context.

### Exercise B — Removing Redundant Registration

In the flagged lab build, remove `addListeners(new ApiReadyListener())` or turn off the system property and rerun. Do not change `ReadyEffect`. Compare logs/counters before and after to prove the double callback came from overlapping registration, not `SpringApplication` firing ready twice by default.

### Exercise C — Same Event ID Redelivered

Simulate publishing the same `OrderPaidEvent("evt-001", "ord-101", 2500)` twice. Design a `(consumer_name, event_id)` unique key and update the DB only when the first insert succeeds. Test two concurrent consumers, then add a process-crash scenario. Distinguish **duplicate delivery** from **duplicate registration**.

### Exercise D — Multiple Contexts

In an example using `SpringApplicationBuilder` with parent/child, log `event.getApplicationContext().getId()` for `ContextRefreshedEvent`. Add a predicate matching only own context to avoid handling child events when a side effect is parent-only. When monitoring all contexts is required, use clear correlation IDs instead of filtering everything out.

### Exercise E — Post-Commit Scenario

Describe a `@TransactionalEventListener(AFTER_COMMIT)` listener receiving the same event ID from two successful transactions. Explain why both callbacks can still be invoked. Propose an inbox/outbox/idempotency key instead of just changing the phase.

## 14. Acceptance Checklist

- [ ] Distinguish registration duplication, event duplication, and context propagation.
- [ ] Locate all listener registration paths in the application and its dependencies.
- [ ] Build the Java 17/Spring Boot 3.5.x project with the Maven files described.
- [ ] Verify one listener: `attempts=1, effects=1`.
- [ ] Verify two listeners: `attempts=2, effects=1`.
- [ ] Explain the limitations of `AtomicBoolean` across multi-process, restarts, and partial failures.
- [ ] Know that events published in a child context can reach parent listeners.
- [ ] Show that `@Order` and `@Async` do not deduplicate.
- [ ] Distinguish `@TransactionalEventListener(AFTER_COMMIT)` from exactly-once execution.
- [ ] Design stable event IDs, inbox unique keys, and outboxes when external I/O is involved.
- [ ] Log/emit metrics separating callback attempts, dedupe decisions, and completed side effects.
- [ ] Avoid running global side effects on every ready event across all replicas without a single owner.

## 15. Official References

- Spring Boot 3.5 — Application Events and Listeners, parent/child context propagation: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — SpringApplication API `addListeners`, `getListeners`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.2 — Application events and `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound application events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — `ApplicationListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationListener.html

**Conclusion:** Preventing listeners from causing repeated effects requires **a single clear business owner**, **proper checking of source event/context**, and **idempotency at the right fault-tolerance level**. Clean registration prevents one kind of duplicate; durable deduplication prevents the other. Both matter when an application restarts, scales, or experiences retries.