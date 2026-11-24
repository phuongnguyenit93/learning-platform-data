# JMSException and Translation to Spring Unchecked Exceptions

## 1. Why Does This Lesson Matter?

When calling the Jakarta Messaging (JMS) API directly, many operations such as creating a `Session`, reading a `TextMessage`, or sending a message can throw `jakarta.jms.JMSException`. This is a **checked exception**: Java forces callers either to `catch` it or declare `throws`. In applications using Spring JMS, `JmsTemplate` and supporting components typically translate caught checked JMS exceptions into `org.springframework.jms.JmsException`, an **unchecked exception** extending `RuntimeException`.

Translation lets the business layer work with a cleaner API, yet **does not turn a failed operation into a success**, does not automatically trigger retries, and does not prove whether a message reached the broker. Understanding the translation boundary is essential for accurate logging, retries, and transaction handling.

After this lesson, you will be able to:
- Identify `JMSException`, `JMSRuntimeException`, and `JmsException` by their exact packages and checked/unchecked status.
- Understand where Spring performs exception translation and how to use `JmsUtils.convertJmsAccessException` when genuinely needed.
- Map original exception types to Spring's corresponding types while preserving `cause` and vendor error codes for diagnostics.
- Apply error handling in publishers/consumers without accidentally acknowledging an unprocessed message.

> Scope: Jakarta Messaging (`jakarta.jms`) and Spring Framework 6.x / Spring Boot 3.x, Java 17+. For older Spring code using `javax.jms`, imports and APIs must be verified per version; the two packages are not directly interchangeable.

## 2. What Is Jakarta Messaging's JMSException?

`jakarta.jms.JMSException` extends `java.lang.Exception`, not `RuntimeException`, making it a **checked exception**. Classic JMS APIs can declare `throws JMSException`; the compiler enforces that callers either handle or propagate it.

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

class RawJmsReader {
    String readText(Session session) throws JMSException {
        TextMessage message = session.createTextMessage("hello");
        return message.getText();
    }
}
~~~

The snippet above only illustrates how the API declares a checked exception: it creates no broker or real `Session`, so it is not a standalone runnable program.

`JMSException` carries useful diagnostic information:
- `getMessage()`: error description; wording and language may be chosen by the provider.
- `getErrorCode()`: provider-specific error code, which may be `null`; **not a standardized error-code catalog guaranteed across all brokers**.
- `getLinkedException()` and `setLinkedException(Exception)`: JMS's historical exception-linking mechanism; when investigating, inspect both the linked exception and the `Throwable.getCause()` chain, as they need not match.

Examples of specialized checked exceptions:

| `jakarta.jms` | Typical Meaning | Handling Hint |
|---|---|---|
| `InvalidDestinationException` | Invalid or unusable destination. | Check name, Queue/Topic type, permissions, and broker configuration. |
| `InvalidSelectorException` | Invalid JMS selector. | Fix selector expression, check property names and syntax. |
| `JMSSecurityException` | Authentication/authorization rejected. | Check credentials, ACLs, and auth mechanism; avoid infinite retries. |
| `ResourceAllocationException` | Broker/provider cannot allocate needed resources. | Evaluate quotas, pools, and resource pressure; retry with limits if genuinely transient. |
| `MessageFormatException` | Reading/accessing message with wrong format or type. | Fix contract/schema and payload reading logic. |
| `TransactionRolledBackException` | JMS transaction rolled back. | Inspect rollback cause and retry/duplicate policy. |

These are **API-defined** exception classes, not an exhaustive list of real-world failures. Providers may throw a generic `JMSException` or vendor codes; never infer recoverability solely from the exception class name.

### An Exception with the Same Name Can Belong to Two Different Packages

~~~text
jakarta.jms.InvalidDestinationException   -> checked, extends JMSException
org.springframework.jms.InvalidDestinationException
                                         -> unchecked, extends JmsException
~~~

Similarly, `jakarta.jms.IllegalStateException` is a subclass of `JMSException`, distinct from `java.lang.IllegalStateException`. When both Jakarta and Spring APIs appear in the same file, use explicit package qualifiers or deliberate imports to avoid name collisions.

## 3. Spring JmsException: Unchecked Exception Hierarchy

Spring defines the abstract base class `org.springframework.jms.JmsException`. It extends `org.springframework.core.NestedRuntimeException`, which extends `RuntimeException`:

~~~text
java.lang.Exception
  └─ java.lang.RuntimeException
       └─ org.springframework.core.NestedRuntimeException
            └─ org.springframework.jms.JmsException
                 ├─ InvalidDestinationException
                 ├─ InvalidSelectorException
                 ├─ JmsSecurityException
                 ├─ ResourceAllocationException
                 ├─ MessageFormatException
                 ├─ TransactionRolledBackException
                 └─ UncategorizedJmsException
~~~

This diagram lists representative classes, not the entire inheritance tree.

Key points:

1. **Unchecked does not force `catch` or `throws`.** Services can still explicitly `catch (JmsException ex)` to log, classify, and apply retry policies.
2. **Spring preserves the original error as the cause** when translating from checked `JMSException`, keeping the underlying stack trace and provider details intact.
3. `JmsException.getErrorCode()` is a convenience method retrieving the error code when the root cause is a `JMSException`. It may return `null` if there is no provider error code or JMS root cause.
4. A `JmsException` **does not necessarily** originate from a `JMSException`. For instance, destination-name resolution errors, payload conversion failures, or internal framework errors can arise directly from the Spring layer.
5. `JmsException` is not `org.springframework.dao.DataAccessException`; both hierarchies are runtime exceptions, but belong to different integration layers.

**Reason for translating to runtime:** decouple messaging access mechanics from business method signatures. Instead of forcing every service to declare `throws JMSException`, Spring lets failures propagate cleanly as runtime exceptions while placing recovery logic at appropriate boundaries.

### Typical Path of an Error

~~~text
Application calls publisher.publish(...)
            |
            v
       JmsTemplate
            |
            v
    Jakarta JMS provider
            |
            | throws jakarta.jms.JMSException (checked)
            v
   Spring catches JMSException
            |
            v
   convertJmsAccessException(...)
            |
            v
 org.springframework.jms.JmsException (runtime)
            |
            v
 Caller catches JmsException or lets error propagate
~~~

This depicts the flow **when Spring catches a checked `JMSException`**. Exceptions thrown by listener code itself, payload conversion errors generated by Spring, listener-container startup failures, and asynchronous connection errors follow other handling paths; do not assume this diagram applies to every throwable.

## 4. How Does Spring Perform Translation?

Public utility:

~~~java
org.springframework.jms.support.JmsUtils
    .convertJmsAccessException(jakarta.jms.JMSException ex)
~~~

The return type is `org.springframework.jms.JmsException`. The method selects a matching Spring subclass when it recognizes the Jakarta subtype; if no specialized mapping exists, it falls back to a general Spring exception such as `UncategorizedJmsException`.

Common mapping examples:

| Checked Jakarta Exception | Unchecked Spring Type |
|---|---|
| `jakarta.jms.InvalidDestinationException` | `org.springframework.jms.InvalidDestinationException` |
| `jakarta.jms.InvalidSelectorException` | `org.springframework.jms.InvalidSelectorException` |
| `jakarta.jms.JMSSecurityException` | `org.springframework.jms.JmsSecurityException` |
| `jakarta.jms.ResourceAllocationException` | `org.springframework.jms.ResourceAllocationException` |
| `jakarta.jms.MessageFormatException` | `org.springframework.jms.MessageFormatException` |
| Generic `jakarta.jms.JMSException` outside specialized subtypes | `org.springframework.jms.UncategorizedJmsException` |

Spring class names closely mirror Jakarta class names, but the two exception hierarchies share no inheritance relationship. When code needs to `catch` the Spring type, make sure to import `org.springframework.jms.*`.

**When using `JmsTemplate`, you rarely need to call `JmsUtils` manually.** Template methods handle resource access/cleanup and translate checked `JMSException` at the Spring boundary. Calling translation manually is only useful when interacting directly with checked JMS APIs outside a template or writing a custom adapter.

## 5. Standalone Java 17 Example: Translating Checked to Unchecked

The following experiment **requires no broker**: a method simulates a provider throwing `InvalidDestinationException`, and then uses Spring's API to translate and inspect the resulting class, error code, and cause. This tests **exception translation**, not live JMS connectivity.

Structure:

~~~text
jms-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/TranslationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-exception-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-jms:6.2.14'
    implementation 'jakarta.jms:jakarta.jms-api:3.1.0'
}

application {
    mainClass = 'example.TranslationDemo'
}
~~~

`src/main/java/example/TranslationDemo.java`:

~~~java
package example;

import jakarta.jms.JMSException;
import jakarta.jms.InvalidDestinationException;
import org.springframework.jms.JmsException;
import org.springframework.jms.support.JmsUtils;

public final class TranslationDemo {
    private TranslationDemo() {
    }

    // Simulate an error returned by the provider; no broker connection.
    private static void rawJmsOperation() throws JMSException {
        throw new InvalidDestinationException(
                "Destination does not exist", "DEST-404");
    }

    public static void main(String[] args) {
        try {
            rawJmsOperation();
        } catch (JMSException checked) {
            JmsException translated =
                    JmsUtils.convertJmsAccessException(checked);

            System.out.println("checkedType="
                    + checked.getClass().getSimpleName());
            System.out.println("springType="
                    + translated.getClass().getName());
            System.out.println("isRuntime="
                    + (translated instanceof RuntimeException));
            System.out.println("errorCode="
                    + translated.getErrorCode());
            System.out.println("sameCause="
                    + (translated.getCause() == checked));
        }
    }
}
~~~

Run in the project directory with JDK 17+ and Gradle supporting the matching toolchain. If the project includes a Gradle Wrapper, prefer `./gradlew run --quiet`; otherwise:

~~~bash
gradle run --quiet
~~~

Standard output **expected from the Java code** (excluding Gradle's own messages):

~~~text
checkedType=InvalidDestinationException
springType=org.springframework.jms.InvalidDestinationException
isRuntime=true
errorCode=DEST-404
sameCause=true
~~~

Line-by-line explanation:
- `checkedType` remains the original `jakarta.jms.InvalidDestinationException`.
- `springType` is Spring's corresponding runtime subclass.
- `isRuntime=true` confirms it is an unchecked exception.
- `errorCode=DEST-404` shows Spring can access the original `JMSException`'s error code.
- `sameCause=true` means the Spring exception wraps **the exact original checked exception** as its cause; translation does not erase the original stack trace.

Change `rawJmsOperation` to `throw new JMSException("Transport failed", "PROVIDER-1");` to observe the non-specialized case. The Spring type becomes `UncategorizedJmsException` per standard mapping, while the error code and original cause remain available for diagnostics.

## 6. In Spring Applications, JmsTemplate Already Handles Most of This

Example event-publishing service (the snippet assumes the application already has a `ConnectionFactory`, an active broker, and a configured `JmsTemplate` bean):

~~~java
package example;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public final class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishCreated(String orderId) {
        jmsTemplate.convertAndSend(
                "orders.created", "OrderCreated:" + orderId);
    }
}
~~~

The `publishCreated` method **does not declare `throws JMSException`**. At the Spring boundary, `JmsTemplate` translates any `JMSException` raised inside the managed operation into `JmsException`. Calling code can catch the Spring exception:

~~~java
try {
    publisher.publishCreated("42");
} catch (org.springframework.jms.InvalidDestinationException ex) {
    // Check destination/provider configuration.
    throw ex;
} catch (org.springframework.jms.JmsException ex) {
    // Other JMS error: log, classify, and let retry policy decide.
    throw ex;
}
~~~

This `try/catch` is an **illustrative fragment inside a caller holding a `publisher` variable**, not a standalone program. Rethrowing preserves the stack trace. In production code, add logging with correlation ID / event ID and handle errors at the right boundary rather than adding empty catch blocks across every layer.

`JmsTemplate` also supports low-level callbacks where the callback itself may declare `JMSException`:

~~~java
String value = jmsTemplate.execute(session -> {
    // Session.createTextMessage/getText declares JMSException.
    return session.createTextMessage("hello").getText();
});
~~~

This snippet sits inside a method holding a `jmsTemplate` variable. Outside the callback, no `throws JMSException` is needed because the template catches and translates checked `JMSException`. `value` is `"hello"` if the template acquires a session; **a broker/`ConnectionFactory` is still required** to actually execute the callback.

### Distinguishing Two Kinds of "Convert" in `JmsTemplate`

There are two completely separate concepts:

- `convertAndSend(...)` converts a **Java payload** into a JMS `Message` (via `MessageConverter`) and sends it.
- `convertJmsAccessException(...)` converts a **checked exception type** into a Spring unchecked type.

Both contain `convert`, yet one transforms data while the other handles errors. Additionally, Spring can throw `MessageConversionException` when payload conversion fails; that failure does not necessarily originate from a `jakarta.jms.JMSException`.

## 7. When Must Exceptions Be Translated Manually?

If you call the classic `Connection`/`Session` API directly in a custom adapter, your code must catch or declare `JMSException`. At the adapter boundary interfacing with Spring code, you can translate at **one single boundary**:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import org.springframework.jms.JmsException;
import org.springframework.jms.support.JmsUtils;

final class RawSessionAdapter {
    String createPayload(Session session) {
        try {
            return session.createTextMessage("payload").getText();
        } catch (JMSException ex) {
            throw JmsUtils.convertJmsAccessException(ex);
        }
    }
}
~~~

This example compiles with dependencies present, yet needs a real caller-supplied `Session` to run. The adapter translates errors without creating or closing the session; whichever component creates the resource must own closing/cleanup. Avoid mixing `JmsTemplate` with manually created `Connection`/`Session` instances unless specifically required, as it easily breaks transaction boundaries and resource management.

**Do not mechanically use `new RuntimeException(ex)` instead of purposeful translation.** Generic wrapping prevents callers from catching useful Spring subtypes and loses classification semantics. When deliberately converting to a business exception, document the reason clearly and preserve `cause`.

### `JMSRuntimeException` Is a Different Case

Since JMS 2.0, Jakarta Messaging offers the simplified API using `JMSContext`; some operations throw `jakarta.jms.JMSRuntimeException` or its subtypes. This is **already an unchecked exception** from the Jakarta API, neither `JMSException` nor `org.springframework.jms.JmsException`.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;

final class DirectContextExample {
    void sendDirectly(ConnectionFactory factory) {
        try (JMSContext context = factory.createContext()) {
            context.createProducer().send(
                    context.createQueue("orders.created"), "hello");
        } catch (JMSRuntimeException ex) {
            // Error directly from Jakarta JMSContext, not via JmsTemplate.
            throw ex;
        }
    }
}
~~~

This snippet requires a real `ConnectionFactory`/broker. You cannot pass `JMSRuntimeException` to `JmsUtils.convertJmsAccessException(JMSException)` because the parameter types differ. If a project uses `JMSContext` directly, catch the `JMSRuntimeException` family or an appropriate supertype.

| API You Call | Exception Family to Watch | Who Translates? |
|---|---|---|
| `jakarta.jms.Session` / classic JMS API | `JMSException` (checked) | Caller handles, declares, or translates at the boundary. |
| `jakarta.jms.JMSContext` / simplified API | `JMSRuntimeException` (unchecked) | Normally handled directly by caller; not automatically a Spring `JmsException`. |
| `org.springframework.jms.core.JmsTemplate` | `JmsException` (unchecked) when template translates checked errors; other runtime errors may also occur | Spring handles within the template-managed calls. |
| `@JmsListener` | Business errors thrown by listener, JMS/provider/container errors | Listener container and transaction/error-handling settings govern routing and redelivery. |

## 8. Designing Error Handling: Classify Before Retrying

An exception being unchecked does **not** mean every failure should be retried automatically. Base your policy on root cause, side effects, and idempotency:

| Situation | Initial Direction |
|---|---|
| Wrong Queue/Topic name, invalid selector syntax | Fix code/configuration; retrying with the same input only repeats the error. |
| Invalid credentials/ACL | Fix authentication/authorization; do not retry in tight infinite loops. |
| Temporary broker outage, pool/connection exhaustion, timeout | May retry with backoff, jitter, and limits; inspect specific error and broker health. |
| Invalid payload / schema mismatch | Isolate bad message, alert; fix schema/consumer, route to DLQ where appropriate. |
| Transaction rollback or caller unsure if broker accepted message | Expect redelivery/resending; use message ID or business key to prevent duplicate processing. |
| Provider throws uncategorized error | Preserve error code/cause, observe, and classify using operational evidence before enabling retries. |

### For Publishers: Errors Do Not Prove the Message Was Not Sent

Suppose a send request times out right after the broker receives the message but before the client receives acknowledgment. The caller sees only an error and cannot be certain the broker did not receive it. Retrying immediately risks creating two copies of the message.

Proper safeguards: attach a stable `eventId`, record event publication state in an outbox if publishing must reliably follow a DB commit, and build consumer-side idempotency/deduplication keyed by `eventId` or business key. Spring translation changes only the **exception type**, not the duplicate-delivery problem.

### For Consumers: Never Swallow Exceptions If You Expect a Rollback

Example of a listener that catches and ignores an error:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String payload) {
    try {
        updateDatabase(payload);
    } catch (RuntimeException ex) {
        // Wrong if treating the message as handled with no compensation/redelivery policy.
        System.err.println("Processing failed: " + ex.getMessage());
    }
}
~~~

This intentionally illustrates an anti-pattern: `updateDatabase` is application-defined. When the listener returns normally, the container may acknowledge/commit the message depending on configuration, even though business processing failed.

When redelivery is desired, let the error propagate to the listener container and configure **session transactions, acknowledgment, retry/backoff, and DLQ** in alignment with the broker. For example, a `DefaultJmsListenerContainerFactory` configured with `setSessionTransacted(true)` rolls back the JMS session when the listener fails, though broker policies determine how many times and when the message is redelivered. A JMS rollback does not automatically roll back database changes unless both resources participate in a proper coordinated transaction.

Nor should you catch `JmsException` on the publisher and assume you caught errors **occurring later inside `@JmsListener`**: publisher and consumer run asynchronously, usually on different threads or processes.

## 9. Accurate Diagnostics When Spring Wraps an Exception

In production logs, track both the Spring-level exception class and the underlying root cause. Example:

~~~java
catch (org.springframework.jms.JmsException ex) {
    String type = ex.getClass().getName();
    String code = ex.getErrorCode(); // May be null.
    Throwable cause = ex.getCause();

    System.err.println("springType=" + type);
    System.err.println("providerCode=" + code);
    System.err.println("causeType="
            + (cause == null ? "(none)" : cause.getClass().getName()));

    // Decide whether to retry or rethrow at the appropriate boundary.
    throw ex;
}
~~~

This is a `try/catch` fragment around a Spring JMS call, not a standalone program. When using a real logger, prefer parameterized logging, pass the exception object to preserve the stack trace, include correlation ID and destination, and avoid logging sensitive payloads directly. If an error code carries broker-specific details, never make it a cross-broker business contract.

Note on `getLinkedException()`:
- The JMS API has its own linked-exception mechanism. If the root cause is a `JMSException`, you can inspect `((JMSException) cause).getLinkedException()` when investigating.
- `getCause()` on a Spring exception usually points to the wrapped `JMSException`; if there is a deeper linked exception inside it, it may not automatically appear at the expected spot in the Java cause chain.
- Keep the stack trace, error code, timestamp, and broker logs together before concluding; reading `getMessage()` alone is insufficient.

### Should You Catch Generic `Exception` or `RuntimeException`?

At a boundary deciding retry/logging, catching `JmsException` classifies Spring JMS errors better than catching every `RuntimeException`. However, if code also calls `JMSContext` directly, `JMSRuntimeException` lies outside that hierarchy. Overly broad catches can hide programming bugs like `NullPointerException`; separate infrastructure failures from code bugs.

## 10. Common Misconceptions

| Misconception | What to Remember |
|---|---|
| “Jakarta's JMSException is a RuntimeException.” | `JMSException extends Exception` (checked); `JMSRuntimeException` is Jakarta's unchecked type. |
| “Spring's JmsException is checked.” | Spring `JmsException` extends `NestedRuntimeException`, so it is unchecked. |
| “Using JmsTemplate requires declaring throws JMSException.” | Spring template APIs typically throw unchecked `JmsException`; callers do not declare checked `JMSException`. |
| “Every RuntimeException is a JmsException.” | Many other runtime families exist: Jakarta's `JMSRuntimeException`, conversion/validation errors, listener bugs. |
| “Spring translation loses provider error codes.” | Spring preserves the cause; `JmsException.getErrorCode()` retrieves the JMS code when present. |
| “Using catch (JmsException) gives you retries.” | Catching only controls flow; retries, backoff, attempt limits, and DLQs must be configured or designed explicitly. |
| “Throwing an exception means the broker definitely never received the message.” | Timeouts or network failures can leave send outcomes unknown; deduplication is still required. |
| “Swallowing exceptions in @JmsListener does not affect ACK.” | Returning normally can trigger ACK/commit depending on mode; verify transaction and container configuration. |

## 11. Self-Check Questions

1. Why might a method calling `Session.createTextMessage(...)` need `throws JMSException`, whereas a method calling `JmsTemplate.convertAndSend(...)` generally does not?
2. There are two `InvalidDestinationException` classes: one in `jakarta.jms` and one in `org.springframework.jms`. Which is checked and which is runtime?
3. After calling `JmsUtils.convertJmsAccessException(ex)`, how do you access the provider's error code and the original exception object?
4. Is `JMSRuntimeException` a subclass of Spring's `JmsException`?
5. A send times out. Why can you not conclude automatically that the broker never accepted the message?
6. A listener catches all errors, logs them, and returns normally. What can happen to acknowledgment/transactions?

**Suggested answers:**
1. The classic Jakarta JMS API declares checked exceptions; Spring's template manages the checked API layer and translates caught exceptions into runtime `JmsException`.
2. `jakarta.jms.InvalidDestinationException` is checked; `org.springframework.jms.InvalidDestinationException` is unchecked.
3. `translated.getErrorCode()` and `translated.getCause()`; if needed, also inspect `JMSException.getLinkedException()` on the cause.
4. No. They belong to two different exception hierarchies; `JMSRuntimeException` is already unchecked from Jakarta.
5. The broker may have received it while the response was lost; retrying risks duplicates, so event IDs and idempotency are needed.
6. The container may treat execution as successful and acknowledge the message; exact behavior depends on ack mode/transactions; redelivery must not be assumed.

## 12. References

- [Jakarta Messaging 3.1 — JMSException API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/jmsexception).
- [Jakarta EE Tutorial — Messaging exception handling](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html).
- [Spring Framework — JmsException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/JmsException.html).
- [Spring Framework — JmsUtils Javadoc (convertJmsAccessException)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/JmsUtils.html).
- [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
