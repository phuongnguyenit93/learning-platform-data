# Ordering in Synchronous Processing — Spring Framework Application Events

## 1. What Does Synchronous Processing Mean?

Spring Framework allows a component to publish an event via `ApplicationEventPublisher.publishEvent(...)` and multiple listeners to receive that event. Under the default `ApplicationContext` configuration, the event dispatcher is `SimpleApplicationEventMulticaster`; regular listeners are invoked **synchronously on the thread that published the event**.

Suppose three listeners are interested in the `InvoiceIssued` event. In a single call to `publishEvent(event)`:

1. Spring identifies the listeners matching the event type.
2. Spring sorts the listeners according to their declared priority.
3. Spring invokes each listener synchronously, one by one; only after one listener completes does it move on to the next listener.
4. Only when all listeners have been invoked and completed normally does `publishEvent(...)` return control to the event-publishing code.

Illustration:

```text
Event publishing thread
  |
  +-- log("before")
  +-- publishEvent(invoiceIssued)
        |
        +-- listener priority 10: completed
        +-- listener priority 20: completed
        +-- listener priority 30: completed
        |
        +-- returns
  +-- log("after")
```

Thanks to this mechanism, code after `publishEvent(...)` can observe that **synchronous listeners have finished executing**, provided no error interrupts the thread and no asynchronous mechanism is used. Listener execution time also adds directly to the latency of the event-publishing call.

## 2. Configuring Order with `@Order`

For methods annotated with `@EventListener`, place `@Order` directly on the method to specify priority. **Smaller numbers run first**; negative values are also valid.

| Declaration | Relative Meaning |
| --- | --- |
| `@Order(-10)` | Runs before listeners with order 0, 10, 20... |
| `@Order(0)` | Runs before `@Order(10)` |
| `@Order(10)` | Runs before `@Order(20)` |
| `@Order(20)` | Runs after `@Order(10)` |
| No order declared | Defaults to low priority, equivalent to `Ordered.LOWEST_PRECEDENCE` |

Rules to distinguish:

- `@Order` determines **the invocation order of listeners selected together for a single event publication**, not bean creation order, the order of publishing independent events, or task order across different threads.
- Listeners with the same `@Order` value (or neither declared) **should not be assumed to have a stable relative order**. If a deterministic order is needed, give them different values or invoke them explicitly from an orchestration service.
- For listeners written with the `ApplicationListener<E>` interface, you can implement `org.springframework.core.Ordered` and return the value from `getOrder()`. For `@EventListener` methods, declaring `@Order` on the method itself is concise and clear.
- The number in `@Order` is a **priority**, not an immutable business step number. You can leave gaps such as 10, 20, 30 to easily add new listeners, but do not turn listener ordering into a mandatory multi-step business workflow.

## 3. Complete Runnable Example with Java 17 and Spring Framework

The following example has three `@EventListener` methods in the same bean. They are written in the source code in the order 30, 10, 20, yet when the event is published they still run in **10 → 20 → 30** order.

Maven project structure:

```text
spring-sync-event-order/
├── pom.xml
└── src/main/java/demo/SyncEventOrderDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-sync-event-order</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.SyncEventOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/SyncEventOrderDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SyncEventOrderDemo {

    public record InvoiceIssued(String invoiceId) {}

    @Configuration(proxyBeanMethods = false)
    public static class InvoiceListeners {

        @EventListener
        @Order(30)
        public void notifyCustomer(InvoiceIssued event) {
            System.out.println("listener 30: notify " + event.invoiceId());
        }

        @EventListener
        @Order(10)
        public void validate(InvoiceIssued event) {
            System.out.println("listener 10: validate " + event.invoiceId());
        }

        @EventListener
        @Order(20)
        public void audit(InvoiceIssued event) {
            System.out.println("listener 20: audit " + event.invoiceId());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(InvoiceListeners.class)) {
            System.out.println("publisher: before");
            context.publishEvent(new InvoiceIssued("INV-42"));
            System.out.println("publisher: after");
        }
    }
}
```

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Output from the `System.out.println` statements in the program:

```text
publisher: before
listener 10: validate INV-42
listener 20: audit INV-42
listener 30: notify INV-42
publisher: after
```

Why does this output occur?

- `new AnnotationConfigApplicationContext(InvoiceListeners.class)` registers the configuration bean and Spring's event publishing/listening mechanism.
- `context.publishEvent(new InvoiceIssued(...))` publishes a plain Java object; Spring supports payload events so event classes are not required to extend `ApplicationEvent`.
- All three methods taking `InvoiceIssued` are matching listeners. `@Order` is applied when Spring sorts them, regardless of the order the methods are declared in the file.
- `publisher: after` appears only after all three synchronous listeners have completed; the example neither enables `@Async` nor supplies an asynchronous `TaskExecutor` to the multicaster.

If written in Spring Boot, the idea remains the same: place `@EventListener` methods in a Spring-managed bean (such as `@Component`) and publish via an injected `ApplicationEventPublisher`.

## 4. Situations That Affect the Observed Order

### 4.1. A Listener Throws an Exception

Under the default `SimpleApplicationEventMulticaster` configuration, if a synchronous listener throws an unhandled exception, the exception propagates back to the caller of `publishEvent(...)` and the current event distribution stops there. For instance, if the `@Order(10)` listener throws `IllegalStateException`, the `@Order(20)` and `@Order(30)` listeners may not have been invoked yet, and statements after `publishEvent(...)` will not execute unless the publisher catches the exception.

An `ErrorHandler` can be configured on the multicaster to handle errors under a different policy, but that policy must be explicitly designed. **`@Order` does not guarantee that every listener will run successfully.**

### 4.2. A Listener Publishes Another Event

A synchronous listener can in turn call `publishEvent(childEvent)`. When it does, distribution of the child event occurs nested within the current call. For example:

```text
Event A:
  listener A-10 starts
    publishEvent(B)
      listener B-10 runs
    B completes
  listener A-10 finishes
  listener A-20 runs
```

This sequence does not violate `@Order`: each event publication has its own set of listeners and its own order. There is no global queue that automatically collects all events together to sort them by `@Order`.

### 4.3. Switching to Asynchronous Processing

The guarantee that "an earlier listener completes before the next listener runs" **no longer applies** if the `@EventListener` method uses `@Async` (with async support enabled), or if the application configures `SimpleApplicationEventMulticaster.setTaskExecutor(...)` with an asynchronous executor for listeners permitted to run asynchronously.

`@Order` is then no longer a mechanism for waiting on task completion: the time listeners start, finish, and log output may differ from the priority order. If steps truly need to run sequentially, keep that part on the synchronous flow or build an appropriate orchestration mechanism.

### 4.4. Multiple Threads Publishing Events Simultaneously

"Synchronous" is understood **within the scope of a single `publishEvent(...)` call per thread**. Two threads simultaneously publishing two events can cause listener logs to interleave. `@Order` does not lock event-publishing threads, does not serialize independent events, and does not guarantee global ordering across publishers.

### 4.5. Events Inside a Transaction

Regular synchronous listeners run on the event-publishing thread, so if the publisher has an active thread-bound transaction, listeners may run while that transaction **has not yet committed**. A listener running earlier in `@Order` does not mean data changes are already committed, and side effects outside the database (sending emails, calling external APIs, etc.) are not automatically rolled back.

`@TransactionalEventListener` has different semantics: by default, the listener is bound to the `AFTER_COMMIT` phase of the transaction, rather than necessarily running immediately in the normal listener chain at the moment of `publishEvent(...)`. If the requirement is "process only after commit", choose the transaction-phase mechanism; `@Order` alone cannot replace transaction boundaries.

## 5. How to Apply in Applications

- **Use `@Order` when** multiple independent listeners need a clear priority within the same event publication, such as writing an audit/tracking marker before a step that enriches information. Pick distinct levels and document the reason for the order.
- **Call directly through an orchestrating service when** a later step must use the result of an earlier step, when all steps must be guaranteed to succeed, or when consistent rollback is needed. Explicit sequential calls, transactions, and error-handling rules are usually easier to control in those cases.
- **Keep synchronous listeners concise** because `publishEvent(...)` has to wait for them. Work that may be slow, involves retries, or calls external systems should have dedicated policies for asynchrony, transactions, and reliability.
- **When ordering is not as expected**, check whether the listener genuinely receives the right event type; whether `@Order` is placed on the right `@EventListener` method; whether there are duplicate values; whether `@Async` or an asynchronous executor is active; whether an earlier listener threw an exception or nested events occurred. Do not infer order from bean names or method declaration positions.

## 6. Self-Check Knowledge

1. With three listeners `@Order(50)`, `@Order(-5)`, and `@Order(0)` receiving the same event and all running synchronously without error, the order is **-5 → 0 → 50**.
2. After `publishEvent(...)` returns normally in the synchronous example, matching listeners have completed. If a listener throws an unhandled exception, that statement no longer holds for the entire listener set.
3. Two listeners both with `@Order(10)` **do not establish a deterministic business rule** for which runs first.
4. `@Order` **does not** cause two event publications from two different threads to line up sequentially, and **does not** turn async callbacks into sequential processing.
5. If you want logic to run after a transaction commits, you must consider `@TransactionalEventListener` and transaction phases, rather than just changing numbers in `@Order`.

## Spring Framework Documentation

- [ApplicationContext: Application Events, Ordering Listeners, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [`SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
