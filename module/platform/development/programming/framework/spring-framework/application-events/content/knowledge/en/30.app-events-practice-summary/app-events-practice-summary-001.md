# Building a Minimal Publisher and Listener with Spring Framework Application Events

## 1. Practice Objectives

This lesson implements an event flow **within the same Spring ApplicationContext** using Java 17:

- Create an `OrderSubmitted` event as a Java `record`.
- Create a publisher service using `ApplicationEventPublisher` via constructor injection.
- Create a listener using an `@EventListener` method on a Spring bean.
- Start a Spring context without Spring Boot, publish two valid events, and receive them.
- Verify that an invalid input does not create an event.
- Observe stdout and the counter to confirm exactly what happens.

This small model demonstrates the value of the internal Observer mechanism: the publisher **does not need to know specific listeners**. However, Spring events are not by themselves a broker, durable queue, transaction, or guaranteed-delivery notification system.

## 2. Components to Understand

| Component | Role | In the example |
| --- | --- | --- |
| Event | Describes what just happened; carries the needed payload | `OrderSubmitted(orderId, amountInCents)` |
| Publisher | Creates the event and asks Spring to distribute it | `OrderService.submit(...)` |
| Publish API | Decouples the service from listeners | `ApplicationEventPublisher.publishEvent(...)` |
| Listener | Receives the matching event and reacts | `OrderSubmittedListener.onSubmitted(...)` |
| Multicaster | Finds and invokes registered listeners | Default `SimpleApplicationEventMulticaster` |
| Container | Creates beans, injects dependencies, and registers listener methods | `AnnotationConfigApplicationContext` |

Flow:

```text
main()
   |
   v
OrderService.submit("ORD-001", 1250)
   |
   +-- validate orderId, amount
   +-- new OrderSubmitted(...)
   +-- publisher.publishEvent(event)
                    |
                    v
          Spring event multicaster
                    |
                    v
          @EventListener onSubmitted(event)
                    |
                    +-- read event.orderId()
                    +-- increment receivedCount
                    +-- write output line
                    |
                    v
          publishEvent(...) returns
   |
   v
OrderService continues processing
```

The example runs **synchronously by default**: the listener is invoked on the publisher thread. This is a property of the standard multicaster configuration, not a guarantee that every `publishEvent` configuration is always synchronous. If you later use an executor or `@Async`, ordering and error handling will differ.

## 3. Environment Preparation

Requirements:

- JDK **17 or higher** (including `javac`).
- Apache Maven.
- A terminal and Java editor.
- Ability to download Maven dependencies on the first run.

Verification:

```bash
java -version
javac -version
mvn -version
```

Note that Maven must also run on Java 17+, not just `java -version`. The example below uses **Spring Framework 6.2.8**. No Spring Boot, HTTP server, database, or message broker is needed to publish and listen to application events.

## 4. Maven Directory Structure

```text
minimal-spring-events/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MinimalEventDemo.java
```

The `package demo;` declaration in the source must match the `demo` directory. The name `public class MinimalEventDemo` must match the file name.

### 4.1. Contents of pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>minimal-spring-events</artifactId>
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
                    <mainClass>demo.MinimalEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides `ApplicationEventPublisher`, `@EventListener`, `@Configuration`, `@Bean`, and `AnnotationConfigApplicationContext`. Maven downloads the required transitive dependencies. There is no need to import a Spring Boot starter to use Spring Application Events.

### 4.2. Complete Contents of MinimalEventDemo.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class MinimalEventDemo {

    // 1. Immutable event payload, no need to extend ApplicationEvent.
    public record OrderSubmitted(String orderId, long amountInCents) {}

    // 2. Publisher is a Spring-managed service.
    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId, long amountInCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "orderId must not be blank");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            System.out.println("publisher: accepted " + orderId);
            OrderSubmitted event =
                    new OrderSubmitted(orderId, amountInCents);
            publisher.publishEvent(event);
            System.out.println("publisher: returned " + orderId);
        }
    }

    // 3. Listener receives the exact OrderSubmitted type.
    public static final class OrderSubmittedListener {
        private final AtomicInteger received = new AtomicInteger();

        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            int call = received.incrementAndGet();
            System.out.println(
                    "listener: order=" + event.orderId()
                    + " amount=" + event.amountInCents()
                    + " call=" + call);
        }

        public int receivedCount() {
            return received.get();
        }
    }

    // 4. Register both publisher and listener as Spring beans.
    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        OrderSubmittedListener orderSubmittedListener() {
            return new OrderSubmittedListener();
        }
    }

    // 5. Run two valid commands and one rejected command.
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service =
                    context.getBean(OrderService.class);
            OrderSubmittedListener listener =
                    context.getBean(OrderSubmittedListener.class);

            service.submit("ORD-001", 1250);
            service.submit("ORD-002", 2200);

            try {
                service.submit("ORD-003", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println(
                        "main: rejected " + ex.getMessage());
            }

            int received = listener.receivedCount();
            System.out.println("main: handled=" + received);

            if (received != 2) {
                throw new IllegalStateException(
                        "Expected exactly 2 events");
            }
        }
    }
}
```

**Code explanation:**

1. `record OrderSubmitted` has two fields; the compiler generates the constructor and the `orderId()`, `amountInCents()` accessors.
2. `OrderService` **only takes the `ApplicationEventPublisher` interface**, without importing or directly calling the listener class.
3. After validating the input, the service creates the event and calls `publishEvent(event)`. If the input is invalid, the method throws an exception **before publishing**.
4. `OrderSubmittedListener` has `@EventListener`; Spring registers this method via the `orderSubmittedListener()` bean.
5. `AtomicInteger` in the demo counts invocations; this is an in-RAM count and does not represent durably delivered messages.
6. `@Configuration` and `@Bean` create all required components without `@ComponentScan` or Spring Boot.
7. `AnnotationConfigApplicationContext` creates and refreshes the context; when `main` retrieves the beans, the listener is already registered.
8. The context is closed via `try`-with-resources at the end; no web server is needed.
9. At the end of the program, the condition `received == 2` verifies the basic flow; if the listener does not work, the program fails rather than silently succeeding.

## 5. Running and Checking stdout

From the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Lines printed by **the Java program**, excluding environment-dependent Maven logs:

```text
publisher: accepted ORD-001
listener: order=ORD-001 amount=1250 call=1
publisher: returned ORD-001
publisher: accepted ORD-002
listener: order=ORD-002 amount=2200 call=2
publisher: returned ORD-002
main: rejected amount must be positive
main: handled=2
```

| Observation | Meaning |
| --- | --- |
| `publisher: accepted ORD-001` | Service validated the first command |
| `listener: ... call=1` | Listener received event ORD-001 |
| `publisher: returned ORD-001` | The publish call returned |
| `listener: ... call=2` | Listener received event ORD-002 |
| `main: rejected ...` | Command ORD-003 was invalid so it was not published |
| `main: handled=2` | Exactly two events were processed by the listener |

In **this configuration**, the listener line appears before `publisher: returned` because Spring invokes the listener synchronously. Do not assume that ordering for every async configuration.

If execution fails, check: JDK/Maven version, file name and `package`, event type, listener bean registration, the `@EventListener` annotation, and the Maven stack trace.

## 6. Why Doesn't a Record Event Need to Extend ApplicationEvent?

Spring has two main ways to define events:

- **POJO/record:** `record OrderSubmitted(...)`; call `publishEvent(Object)`; Spring can wrap the payload in a `PayloadApplicationEvent` for distribution.
- **Subclass of `ApplicationEvent`:** the traditional style, which carries a `source` and can use the `ApplicationListener<YourEvent>` interface.

A traditional event subclass:

```java
// Snippet: place in the corresponding file/package if you want to use it.
import org.springframework.context.ApplicationEvent;

public final class OrderSubmittedEvent extends ApplicationEvent {
    private final String orderId;

    public OrderSubmittedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

This snippet is not used in the main project; it only helps distinguish the old mechanism from the new one. With Java 17, a record combined with `@EventListener` is a very simple approach.

Do not write `ApplicationListener<OrderSubmitted>` for a plain record: the generic type of `ApplicationListener<E>` requires `E extends ApplicationEvent`. To receive a record payload, simply use `@EventListener` as shown in the example.

## 7. How Does Spring Discover the Listener?

The annotation-based listener mechanism relies on Spring-managed beans:

1. The context reads `Config` and creates the `OrderService`/`OrderSubmittedListener` beans.
2. Spring processes `@EventListener` metadata via the `EventListenerMethodProcessor` infrastructure and listener adapters.
3. When the publisher publishes an event, the multicaster selects matching adapters by **event type**.
4. The adapter invokes `onSubmitted(OrderSubmitted)` with the record payload.
5. The listener executes its reaction logic and returns `void`.

A class with `@EventListener` that is instantiated manually outside the Spring container **is not automatically registered**:

```java
// Illustrates a common mistake, no need to add to the main program.
OrderSubmittedListener listener = new OrderSubmittedListener();
// This bean was created with "new", so Spring does not auto-detect it as a listener.
```

In the main code, `@Bean` is used so Spring owns the lifecycle. If using `@Component`, you must configure component scanning on the right package; the demo does not need scanning because it registers beans directly.

Avoid overusing lazy initialization for listener methods: the Spring documentation notes that lazily defined listener beans may not be registered to receive events the way you expect.

## 8. The Publisher Should Not Depend Directly on Listeners

With direct calls:

```java
// Illustrative snippet, not used in the runnable example.
auditListener.handle(order);
emailListener.handle(order);
cacheListener.handle(order);
```

The service has to know all three components. Whenever a new listener is added, the service has to change. Sometimes direct orchestration is the right choice, especially when results and strict ordering are required; however, it does not represent the observer mechanism.

With a publisher:

```java
publisher.publishEvent(new OrderSubmitted(orderId, amountInCents));
```

`OrderService` only states that an event has occurred. Other modules can subscribe to react without modifying the publisher's logic. In exchange, the relationship between the publisher and listeners **is less visible in the call graph**, so you need good event naming, tests, and an exception/error policy.

Do not use an event bus just to hide a mandatory business call: if step B must complete for A to be valid, a direct dependency or workflow orchestration can be more accurate and easier to test.

## 9. Extension: Adding a Second Listener

Suppose you need to write an audit log after receiving `OrderSubmitted`. You can add another bean:

```java
// Additional snippet inside MinimalEventDemo.
public static final class AuditListener {
    @EventListener
    public void onOrderSubmitted(OrderSubmitted event) {
        System.out.println("audit: accepted " + event.orderId());
    }
}

// In Config, add:
@Bean
AuditListener auditListener() {
    return new AuditListener();
}
```

These are just change snippets, **not a standalone file**. Once added, a single `publishEvent` can cause **both `OrderSubmittedListener` and `AuditListener` to run**.

Make sure to distinguish:

| Metric | One listener | Two listeners of the same type |
| --- | ---: | ---: |
| Number of `publishEvent` calls for one command | 1 | 1 |
| `OrderSubmittedListener` invoked | 1 | 1 |
| `AuditListener` invoked | 0 | 1 |
| Total handler invocations | 1 | 2 |

Do not conclude "Spring published two events" just because you see two log lines from two listeners. If you need ordering constraints between listener methods, you can use `@Order`; do not rely on incidental bean registration order, especially when switching to async.

Run the original example and verify its output **before** adding this listener, because stdout after the extension will naturally include the audit line.

## 10. Error Handling and Synchronous Configuration

In the original example, the listener runs on the publisher thread. If the listener throws an unchecked exception, it can propagate back through `publishEvent(...)` to `submit(...)`:

```java
// Illustrative snippet, do not replace the entire main code.
@EventListener
public void onSubmitted(OrderSubmitted event) {
    if ("ORD-FAIL".equals(event.orderId())) {
        throw new IllegalStateException("listener failed");
    }
}
```

Without a special `ErrorHandler` swallowing exceptions, the `submit` method can stop at `publishEvent` and never print `publisher: returned ORD-FAIL`. This helps explain why events are **not fire-and-forget by default**.

Points to keep in mind:

- A listener should not arbitrarily swallow all exceptions and report false success.
- If there are multiple listeners, an earlier listener may have already performed side effects before a later listener fails.
- If inside a transaction, an unchecked exception propagating across the transaction boundary can trigger a rollback under Spring's policy; **however, the demo has no transaction**.
- An outgoing HTTP request or email already sent is not automatically rolled back along with the database.
- Do not blindly retry the entire `publishEvent` call when one listener fails, because that can re-invoke listeners that already succeeded.

Clearly separate **event dispatch** from **mandatory business logic** and side-effect handling policies.

## 11. What If Asynchronous Processing Is Needed?

This exercise **does not enable async**. In Spring, you can use `@Async` on a listener with `@EnableAsync` and an appropriate executor, or configure `SimpleApplicationEventMulticaster` with a task executor.

Comparison:

| Behavior | Default synchronous | Configured async |
| --- | --- | --- |
| Listener thread | Usually the publisher thread | Can be a worker thread |
| `publishEvent` returns | After sync handlers finish | Possibly before handlers finish |
| stdout ordering | Predictable with one listener | Not guaranteed as in the demo |
| Exception | Can propagate to publisher | Requires async error handling |
| Transaction context | Can share the same thread | Thread-bound transaction does not transfer automatically |
| Testing invocation count | Immediate assert may be valid | Must wait for a completion signal |

If you add `@Async` yourself, do not keep an immediate assertion `receivedCount() == 2` right after publishing and assume it is always true; the worker might not have finished yet. Tests should use `CountDownLatch`, a future, or an await mechanism with a deadline.

Async only changes execution; it **does not create a durable queue**. When delivery guarantees across process crashes are required, another architecture is needed, such as transactional outbox, a broker, or an appropriate job queue.

## 12. Distinguishing Plain Events, Transactional Events, and Integration Events

- **Spring application event:** a mechanism for passing notifications between beans in the same context, as in this example.
- **`@TransactionalEventListener`:** reacts to an event according to a transaction phase, defaulting to `AFTER_COMMIT`. If there is no transaction, this type of listener does not run by default unless `fallbackExecution=true`.
- **Integration event:** a shared contract between applications, typically requiring attention to schema versioning, serialization, broker, auth, retries, and idempotency.
- **Transactional outbox:** a pattern that records message-publishing intent in the same transaction as state changes, enabling a relay to continue after a crash.

Do not equate `publishEvent` with `KafkaTemplate.send`. A Spring event can be bridged to a broker by a custom listener, but consistency must be designed carefully: sending to a broker before commit can emit a message for a transaction that later rolls back. `AFTER_COMMIT` gives the right timing, yet by itself still does not guarantee durable delivery.

In this minimal lesson there is no DB yet, so `OrderSubmitted` should only be understood as the service **having accepted the submit command**; do not claim "order saved" or "payment completed" when there is no real persistence or payment.

## 13. Designing Good Event Payloads and Names

`OrderSubmitted` should be named in the past tense or clearly describe a fact the system has confirmed. Do not call an event `EmailSent` when you have only enqueued an email request; that is different from the email actually having been sent.

Minimal payloads reduce coupling:

- Include only the values listeners need in order to react.
- Avoid copying an entire request DTO or JPA entity with many unrelated fields.
- Do not include passwords, OTPs, access tokens, secret keys, card numbers, or unnecessary PII.
- Use records/immutable DTOs; note that records are **shallowly immutable**. If a record holds a mutable `List`, the collection's contents can still change; make defensive copies when needed.
- If a listener needs current state, consider passing an ID reference and performing an authorized lookup. An ID can still be indirect personal data if it can be linked to a subject.
- When there are multiple consumers or a broker, clearly define snapshot semantics, versioning, and retention.

In the demo, `amountInCents` is an integer in minor units under **an assumed convention**. For multi-currency products, use an accurate Money/`amountMinor + currency` convention rather than cents for every currency.

## 14. Testing Events by Layer

Directly inside `main`, the program verifies:

1. Two valid commands are accepted by the service.
2. Each command calls the publisher once according to the implemented logic.
3. The listener receives and counts both events in the sync configuration.
4. An input amount of 0 is rejected **before publishing**.
5. The final check throws `IllegalStateException` if the listener count does not reach 2.

With a test framework, separate responsibilities clearly:

**Publisher unit test:** mock `ApplicationEventPublisher` using Mockito. Conceptual example (not a complete test class):

```java
ApplicationEventPublisher mockPublisher =
        mock(ApplicationEventPublisher.class);
OrderService service = new OrderService(mockPublisher);

service.submit("ORD-001", 1250);

verify(mockPublisher, times(1))
        .publishEvent(any(OrderSubmitted.class));
verifyNoMoreInteractions(mockPublisher);
```

This snippet requires the Mockito dependency, static imports, and the demo classes. It verifies **the publisher call**, without running real Spring listeners. For invalid input, use `verifyNoInteractions(mockPublisher)`. You can use `ArgumentCaptor<OrderSubmitted>` to assert the payload.

**Spring integration test:** use Spring TestContext, `@RecordApplicationEvents`, and `ApplicationEvents.stream(OrderSubmitted.class)` to record/count events published during a test method. Pair with a listener spy/counter if you need to prove handler invocation. Note that the recorder counts published events and does not automatically mean committed events or broker delivery.

**If async:** wait for processing to complete with a timeout; do not use `Thread.sleep(500)` and guess. If there are multiple listeners, total handler invocations can exceed the number of publisher calls.

## 15. Common Pitfalls

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| No `listener: ...` line printed | Listener is not a Spring bean | Confirm `@Bean orderSubmittedListener()` or component scan |
| Listener does not receive event | Wrong parameter type | `onSubmitted(OrderSubmitted event)` exact class/package |
| `@EventListener` has no effect | Listener created with `new` outside container; lazy bean | Put listener into Spring-managed context |
| Only `publisher: accepted` appears | Listener threw an exception | Check stack trace, error policy |
| Maven fails to compile | Old JDK or wrong file/package name | `mvn -version`, `MinimalEventDemo.java`, `package demo` |
| `NoClassDefFoundError` | Incorrect dependencies | Check POM, Maven resolution, and classpath |
| `mainClass not found` | `exec-maven-plugin` points to wrong class | `demo.MinimalEventDemo` |
| Listener runs multiple times | Publisher called multiple times or multiple sources | Count publisher calls and event IDs |
| Out-of-order logs after adding async | Worker runs on a different thread | Wait for completion, do not depend on ordering |
| Event missing after crash | Stored only in JVM memory | Need durable outbox/queue if required by contract |

Do not look for an `@EnableEvents` annotation: with an annotation-configured Spring ApplicationContext, no such annotation is needed to use `@EventListener`. `@EnableAsync` is only relevant when enabling annotation-driven async support.

### Why Not Call the Listener Directly?

`listener.onSubmitted(event)` is a normal method call and does not prove that Spring registration/dispatch works. Direct calls can be used if the semantics require mandatory orchestration; to learn Spring events, call `publisher.publishEvent(event)` as in the demo.

### Can There Be Zero Listeners?

Yes. If no matching bean/method exists, an event can be published without any business listener handling it. By default, `publishEvent` does not raise a "nobody received this" error. Therefore, if an event is essential for business correctness, design proper validation/observability and architecture rather than assuming the event bus guarantees a consumer.

## 16. Extended Practice Exercises

**Exercise 1 — Add another valid event.** Call `service.submit("ORD-004", 3300)` before the invalid command, and adjust the self-check to 3. Expect a listener count of 3, while the invalid command still publishes no event.

**Exercise 2 — Test an empty order ID.** Call `service.submit("", 100)` inside `try/catch`; no new listener line should appear. Replace the input with `null` and verify the service rejects it similarly.

**Exercise 3 — Add an audit listener.** Create an `AuditListener` bean with `@EventListener` receiving `OrderSubmitted`. One event causes two handlers to react while the publisher still calls `publishEvent` only once. If ordering between listeners is needed, explore `@Order`.

**Exercise 4 — Add another event type.** Create `record OrderCancelled(String orderId) {}` and a dedicated listener for it. Verify that `OrderSubmittedListener` is not invoked when only `OrderCancelled` is published.

**Exercise 5 — Try exception propagation.** Add a listener branch that throws `IllegalStateException` when the order ID is `ORD-FAIL`; observe whether `publisher: returned ORD-FAIL` is printed in the default sync setup. Do not retry the entire publication when another listener has already succeeded.

**Exercise 6 — Write a JUnit integration test.** Use Spring TestContext `@RecordApplicationEvents` to count 0/1/2 events across commands. Add a Mockito unit test to verify publisher call counts and record data.

**Exercise 7 — Try Boot after understanding the core.** Replace the manual context with a Spring Boot application, register the service/listener with `@Component`, and use an `ApplicationRunner` to invoke the service. Verify there is no fundamental difference in event types and `@EventListener`.

**Exercise 8 — Draw production boundaries.** Suppose the listener needs to send an email; choose among a synchronous listener, after-commit, or outbox depending on requirements. Explicitly state transaction boundaries, retries, idempotency, and when completion truly happens; do not assume simply adding `@Async` is enough.

## 17. Self-Assessment Checklist

- [ ] Correctly created `pom.xml` and `src/main/java/demo/MinimalEventDemo.java`.
- [ ] Have JDK 17+ and ran `mvn -q clean compile exec:java` successfully.
- [ ] Event is a simple Java record without `extends ApplicationEvent`.
- [ ] Publisher service injects `ApplicationEventPublisher` and publishes the event after validation.
- [ ] Listener is a Spring-managed bean with an `@EventListener` method and matching parameter type.
- [ ] Application context properly registers both publisher and listener.
- [ ] There are two `listener: ...` lines corresponding to ORD-001 and ORD-002.
- [ ] Command ORD-003 with amount 0 is rejected before publishing.
- [ ] Final output is `main: handled=2`; self-check does not throw an exception.
- [ ] Understand why the synchronous listener runs before `publisher: returned` in the example.
- [ ] Distinguish the number of publisher calls from total listener invocations.
- [ ] Know that a Spring in-process event is not a durable broker message.
- [ ] Know the principle of excluding secrets and unnecessary PII from events.

## 18. Review Questions

1. **How are the publisher and listener connected?** — Via Spring's `ApplicationEventPublisher` and the multicaster in the context.
2. **Why doesn't the publisher import the listener?** — It only publishes the event; listeners are registered independently.
3. **Does a record need to extend ApplicationEvent?** — No; `publishEvent(Object)` supports POJOs.
4. **Will placing @EventListener on a class not managed by Spring run?** — It will not be registered automatically.
5. **What condition selects the listener in the demo?** — The event type `OrderSubmitted`.
6. **How many callbacks do two valid events and one invalid command produce?** — Two callbacks for one matching listener in the default sync setup.
7. **Does one event with three listeners mean three publish calls?** — No, a single publish call can trigger all three.
8. **Why does the listener line appear before publisher returned?** — The default multicaster is synchronous, with one listener.
9. **Can a listener throwing an exception cause the publisher to fail?** — Yes, when synchronous and not swallowed by a handler.
10. **Does @Async make events durable?** — No.
11. **Does @TransactionalEventListener(AFTER_COMMIT) work outside a transaction by default?** — Not by default, unless `fallbackExecution` is set appropriately.
12. **When is a separate integration event needed?** — When sending events out to other applications requiring contracts, schemas, delivery guarantees, and security.
13. **What does a unit test mocking the publisher prove?** — Publish call count and payload; it does not prove a real listener ran.
14. **What must be done when sensitive data is involved?** — Apply payload minimization, authorization, and logging/retention policies.

## References

- [Spring Framework — Application Events and Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2.8 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.8 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
