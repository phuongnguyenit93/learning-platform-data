# Exceptions from Synchronous Listeners in Spring Framework Application Events

## 1. What Happens When a Synchronous Listener Throws an Exception?

When business code calls `ApplicationEventPublisher.publishEvent(event)`, the Spring Framework passes the event to `ApplicationEventMulticaster` to look up and invoke matching listeners. With the default configuration of `SimpleApplicationEventMulticaster`, listeners run **synchronously on the exact thread calling `publishEvent(...)`**. Because of this, an error inside a listener can directly affect the event publisher.

**Core rule:** If a synchronous listener throws an exception and the multicaster has no `ErrorHandler`, that exception propagates back to the `publishEvent(...)` call. The current dispatch pass stops at the failing listener; subsequent listeners that have not been invoked yet will not execute during that pass.

This is the default behavior of `SimpleApplicationEventMulticaster`, not a guarantee applying to custom multicaster implementations or asynchronous listeners.

~~~text
Service / Controller (thread T)
    |
    | publishEvent(OrderCreated)
    v
ApplicationEventMulticaster (still on thread T)
    |
    +-- Listener A: finishes processing
    |
    +-- Listener B: throw IllegalStateException
    |        |
    |        +-- no ErrorHandler: propagates exception outward
    |
    X-- Listener C: not invoked
    |
    v
publishEvent(...) throws exception back to Service / Controller
~~~

Do not confuse **stopping invocation of subsequent listeners** with **rolling back listeners that already ran**. If Listener A wrote a file, called an external service, or sent an email, Listener B's exception does not automatically reverse those effects.

## 2. Exception Propagation Path and Impact on the Publisher

In the standard case, the synchronous call chain looks like this:

1. The publisher calls `publishEvent(event)`.
2. `ApplicationContext` forwards the event to the context's multicaster.
3. The multicaster identifies matching listeners and invokes each one.
4. A listener throws a `RuntimeException`, such as `IllegalStateException`.
5. No handler catches and handles the error, so the exception unwinds out of the listener, through the multicaster, and out of `publishEvent(...)`.
6. The code calling `publishEvent(...)` can catch the exception with `try/catch` or let it keep propagating up the call stack.

Observable consequences:

- `publishEvent(...)` **does not return normally** when an exception escapes; statements after the call within the same `try` block may be skipped.
- Listeners invoked **before** the failing listener still executed; listeners positioned **after** the failing listener were not invoked in that publish pass.
- The publisher can catch the exception, log it, translate it into a business result, or let transaction management handle it according to its rules.
- Spring Application Events do not come with built-in retries, durable queues, or automatic replay of the failed listener.

**Listener ordering matters in testing.** You can use `@Order` on `@EventListener` methods or `Ordered` on `ApplicationListener` beans to control invocation order during synchronous execution. Without explicit ordering, never rely on arbitrary order for business correctness.

## 3. Java 17+ Example: Comparing Default Failure vs. ErrorHandler

The example below uses Spring Framework 6.2.9, Java 17+, and Maven. Two event publications use the same pair of listeners: the first listener intentionally throws an exception; the second merely prints a line to check whether it was invoked.

Create two files:

~~~text
listener-exception-demo/
├── pom.xml
└── src/main/java/ListenerExceptionDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-exception-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

Contents of `src/main/java/ListenerExceptionDemo.java`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;

public class ListenerExceptionDemo {

    public record TaskQueued(String id) {}

    public static void main(String[] args) {
        System.out.println("=== Default: without ErrorHandler ===");

        try (var context =
                     new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            try {
                context.publishEvent(new TaskQueued("T-1"));
                System.out.println("Publisher: finished publishing T-1");
            } catch (IllegalStateException ex) {
                System.out.println("Publisher: caught error " + ex.getMessage());
            }
        }

        System.out.println("=== With ErrorHandler suppressing errors ===");

        try (var context =
                     new AnnotationConfigApplicationContext(HandledConfig.class)) {
            context.publishEvent(new TaskQueued("T-2"));
            System.out.println("Publisher: finished publishing T-2");
        }
    }

    public static class Listeners {
        @EventListener
        @Order(10)
        public void first(TaskQueued event) {
            System.out.println("Listener 1: " + event.id());
            throw new IllegalStateException("cannot process " + event.id());
        }

        @EventListener
        @Order(20)
        public void second(TaskQueued event) {
            System.out.println("Listener 2: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DefaultConfig {
        @Bean
        public Listeners listeners() {
            return new Listeners();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(DefaultConfig.class)
    public static class HandledConfig {
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setErrorHandler(error ->
                    System.out.println("ErrorHandler: " + error.getMessage()));
            return multicaster;
        }
    }
}
~~~

From the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ListenerExceptionDemo
~~~

Lines printed by the program to stdout, ignoring runner-specific messages:

~~~text
=== Default: without ErrorHandler ===
Listener 1: T-1
Publisher: caught error cannot process T-1
=== With ErrorHandler suppressing errors ===
Listener 1: T-2
ErrorHandler: cannot process T-2
Listener 2: T-2
Publisher: finished publishing T-2
~~~

**Run T-1:** `publishEvent(...)` invokes listener 1. Listener 1 throws `IllegalStateException`. Since there is no `ErrorHandler`, the exception reaches the publisher's `catch` block; listener 2 does not run. The line "Publisher: finished publishing T-1" never appears.

**Run T-2:** `HandledConfig` declares a special bean named exactly `applicationEventMulticaster`. This multicaster has an `ErrorHandler` that prints the error and **returns normally**. Because the exception was absorbed by the handler, the multicaster proceeds to invoke listener 2. `publishEvent(...)` finishes normally and prints "Publisher: finished publishing T-2".

In both cases, **listener invocation remains synchronous**. `setErrorHandler(...)` does not turn execution into asynchronous processing by itself. A suppressed error only changes exception handling and dispatch continuation.

## 4. Three Ways to Handle Exceptions: Propagate, Catch Locally, or ErrorHandler

### Approach 1 — Let the Exception Propagate to the Publisher

Use the default configuration and let the listener throw a `RuntimeException` when work fails:

~~~java
@EventListener
public void validatePayment(PaymentAccepted event) {
    if (!isValid(event)) {
        throw new IllegalStateException("Invalid payment data");
    }
}
~~~

*This is illustrative code placed inside an existing bean; `PaymentAccepted` and `isValid` are domain elements to define, not a standalone program.*

This approach is appropriate when a listener failure must cause the event-publishing business flow to fail. However, you must understand that `publishEvent(...)` can then throw an exception and stop dispatching to remaining listeners.

### Approach 2 — Listener Catches Recoverable Errors Itself

~~~java
@EventListener
public void updateSearchIndex(ProductChanged event) {
    try {
        searchIndex.update(event.id());
    } catch (SearchBackendUnavailableException ex) {
        logger.warn("Search index not updated for {}", event.id(), ex);
        // Record for retry via a separate mechanism if required by business logic.
    }
}
~~~

*This is illustrative code assuming existing domain dependencies `searchIndex`, `logger`, `ProductChanged`, and `SearchBackendUnavailableException`.*

Because the method does not throw an exception outward, the multicaster can invoke the next listener. Yet `publishEvent(...)` returning normally **does not prove** that the index update succeeded. If the task is mandatory, you need an error/retry persistence mechanism or to propagate the error to the publisher by design.

### Approach 3 — Configure an ErrorHandler on the Multicaster

`SimpleApplicationEventMulticaster.setErrorHandler(...)` accepts an `org.springframework.util.ErrorHandler`. The handler is called when a listener throws an error while the multicaster is invoking that listener. Two common options:

- **Log and do not rethrow:** the handler returns normally; the dispatch pass continues to subsequent listeners.
- **Log and rethrow:** the exception continues propagating; in a synchronous call, the dispatch pass stops and the publisher receives the error.

Spring also provides convenience handlers such as `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` and `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`. You must choose based on business semantics rather than swallowing all errors by default.

**Scope:** An `ErrorHandler` configured on the multicaster handles errors thrown while the multicaster *invokes a listener*. It does not catch arbitrary exceptions across the whole application, does not replace `@ControllerAdvice`, and does not perform rollbacks or retries on its own.

## 5. Checked Exceptions, RuntimeException, and Error

### RuntimeException

When a listener method throws `IllegalArgumentException`, `IllegalStateException`, or another `RuntimeException`, a synchronous `@EventListener` invocation normally propagates that runtime error out to the publisher (unless caught by the listener or handled by the multicaster).

This is the scenario demonstrated by the runnable program above.

### Checked Exceptions

An `@EventListener` method can declare `throws IOException` or another checked exception type. However, the event-publishing API does not declare arbitrary checked exceptions. According to the `@EventListener` Javadoc, when a listener method throws a checked exception, Spring wraps it in `java.lang.reflect.UndeclaredThrowableException` before propagating the error outward.

Illustrative example (not a standalone program):

~~~java
@EventListener
public void importFile(FileImported event) throws java.io.IOException {
    throw new java.io.IOException("Unable to read file");
}
~~~

On the publisher side, you cannot assume a `publishEvent(...)` call directly throws `IOException`; you must handle the corresponding runtime wrapper exception and inspect the root cause (`getCause()`) if needed. Do not catch `Exception` and silently ignore all errors just to keep execution going.

### Error

`Error`, such as serious JVM errors, extends `Throwable` rather than `Exception`. When configured with an `ErrorHandler`, `SimpleApplicationEventMulticaster` passes caught `Throwable` instances to the handler. That does **not** mean an application should try to swallow critical errors: errors of this kind are usually unsafe to recover from.

## 6. Synchronous Listener Exceptions and `@Transactional`

An important impact arises when the publisher runs inside a `@Transactional` method. If the event is published right **inside** the transactional method, the default synchronous listener also runs on the same thread while the transaction is still active.

~~~text
@Transactional serviceMethod()
    |
    | modifies data inside transaction
    |
    | publishEvent(event)
    |      |
    |      +-- synchronous listener throws RuntimeException
    |
    +-- exception escapes serviceMethod()
           |
           +-- TransactionInterceptor applies rollback rules
~~~

With Spring Transaction Management defaults, `@Transactional` marks a transaction for rollback when a `RuntimeException` or `Error` escapes the transaction-managed method call. Consequently, **a runtime exception from a synchronous listener can cause the publisher's transaction to roll back**, provided the exception propagates past the transactional method boundary.

Four cases must be kept distinct:

| Scenario | Typical outcome |
| --- | --- |
| Listener throws `RuntimeException`; nobody catches it; error escapes past the `@Transactional` proxy | Transaction is marked for rollback according to default rules. |
| Publisher catches the error inside the method and continues normally | Does not automatically roll back solely because a listener threw earlier; outcome still depends on transaction state and configuration. |
| `ErrorHandler` absorbs the error and returns normally | Publisher usually sees no exception; this cannot be relied upon to trigger automatic rollback. |
| Listener already called an external API or wrote to a non-transactional resource | Database rollback does not automatically undo external side effects. |

For example, if business logic already called a shipping system and a later listener throws an error, rolling back SQL records does **not** mean the external call is canceled. That is why transaction boundaries and side effects must be designed deliberately.

**Do not confuse with `@TransactionalEventListener`.** That mechanism binds execution to a transaction phase such as `AFTER_COMMIT` and follows separate rules; an error occurring after commit cannot undo an already committed transaction. That is a different kind of listener from the synchronous `@EventListener` example running immediately at `publishEvent(...)`.

## 7. Where Should Handling Live?

| Need | Option to consider |
| --- | --- |
| Listener performs a mandatory step for the operation to succeed | Let the error propagate, or call the mandatory component directly when explicit results are needed. |
| Listener only produces auxiliary logs/metrics | Catch errors inside the listener, or use an `ErrorHandler` that records errors, depending on the desired scope. |
| One listener fails but other listeners must still run | Use a non-rethrowing `ErrorHandler`, or catch errors inside the listener; ensure failures are still observable somewhere. |
| Need retries, guaranteed event delivery, or multi-process handling | Use a queue, outbox, or suitable durable work mechanism; default Application Events do not provide these guarantees. |
| Only want to reduce publisher wait time | Consider `@Async` or an executor, while adapting error handling and thread context; that is a separate topic from synchronous exceptions. |

Decide based on the question: *"If the listener's work fails, should the original operation still be considered successful?"* The answer determines whether to let the error propagate to the publisher, catch it in the listener, or absorb it at the multicaster.

## 8. Misconceptions to Avoid

1. **"Exceptions in listeners are just logged."** False under defaults: unhandled exceptions propagate to the publisher and stop the dispatch pass.
2. **"If one listener fails, all previous listeners are rolled back."** False: there is no automatic rollback of all side effects; only resources actually participating in a matching transaction can roll back under transaction rules.
3. **"Catching the exception in the publisher guarantees a safe state."** Not necessarily: earlier listeners may have made irreversible changes, and remaining listeners may not have run.
4. **"Configuring an ErrorHandler always makes the publisher fail."** Only if the handler rethrows the error (or the handler itself throws). A handler returning normally allows the multicaster to continue.
5. **"Using `@Order` ensures all listeners run even if one fails."** False: `@Order` only adjusts ordering; it does not handle exceptions.
6. **"Synchronous listeners behave like `@Async` listeners."** False: exceptions from `@Async` methods are normally handled on the asynchronous thread and do not propagate directly back to the publisher as in the synchronous example.

## 9. Self-Check Exercises

**Scenario A.** Three listeners are invoked in order A → B → C. A succeeds; B throws `IllegalStateException`; the multicaster stays at defaults. Which listeners ran and who receives the error?

**Answer:** A and B were invoked; C was not invoked. B's exception propagates to the publisher's `publishEvent(...)` call if nothing handles it in between.

**Scenario B.** Same three listeners as above, but an `ErrorHandler` is configured to log and return normally. What changes?

**Answer:** After handling B's exception, the multicaster continues and invokes C. The publisher can observe `publishEvent(...)` finishing normally even though B failed; therefore, dedicated logging/metrics or error recovery is needed.

**Scenario C.** The publisher runs inside `@Transactional`, and listener B throws a `RuntimeException`. Are all side effects guaranteed to roll back?

**Answer:** No. When the error escapes through the proxy under default rollback rules, the associated database transaction can roll back. Side effects outside the transaction (emails, HTTP calls, files, external services) are not automatically undone; catching errors or configuring a handler can also change the transaction outcome.

## References

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): default synchronous invocation, `setErrorHandler`, how errors propagate and stop dispatch.
- [Spring Framework — @EventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html): exceptions from listener methods and wrapping of checked exceptions.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): event publishing and handling mechanism in the context.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): default rollback rules of `@Transactional`.
