# Replacing Inheritance with Composition (Replace Inheritance with Composition) in Java OOP

## 1. The Problem to Solve

**Inheritance** lets one class extend another using `extends`. It is useful when their classification genuinely satisfies an **is-a** relationship: a subclass object can be used anywhere the superclass is accepted while honoring its behavioral contract.

In practice, a class sometimes extends another simply to **reuse a few methods**. The subclass then becomes coupled to the parent's API, state, and changes. A parent-class change may unexpectedly affect it, and the subclass may need to override methods unrelated to its own responsibilities.

**Replace Inheritance with Composition** changes a design from "class A extends class B to borrow behavior" to "class A **contains an object** providing the needed capability and **delegates** work to it."

Goals:
- Separate **business responsibilities** from **execution mechanisms**.
- Reduce dependency on superclass implementation details.
- Make implementations configurable through interfaces.
- Enable unit testing with fakes/stubs without activating real external systems.
- Preserve observable behavior during refactoring, except for explicitly planned API changes.

This **does not prohibit inheritance**. Inheritance remains appropriate for stable classifications where subclasses satisfy the superclass contract. The goal is to choose a mechanism that fits the object's responsibility.

## 2. Comparing Inheritance and Composition

| Aspect | Inheritance | Composition |
| --- | --- | --- |
| Model relationship | **is-a**: a specialization of the parent | **has-a/uses-a**: owns or uses a collaborator |
| Java | `class Child extends Parent` | Reference field: `private final Capability capability;` |
| Reuse | Inherit the parent's methods and mechanisms | Invoke methods on an injected object |
| Coupling | Often tightly bound to superclass structure/contracts | Can depend on a small interface |
| Replacing implementations | Often requires another subclass or inheritance changes | Supply a different implementation at construction |
| Testing | May bring along superclass behavior | Inject fakes/mocks at collaboration boundaries |
| Costs | Fewer delegates; clear when the is-a relationship is real | Adds fields, constructors, delegation, and lifecycle decisions |

Note: In Java, **class inheritance** through `extends` and **interface implementation** through `implements` impose different forms of coupling. An object can `implements MessageChannel` to fulfill a contract while another uses `MessageChannel` through composition.

## 3. Before Refactoring: An Alert Class Inherits from an Email Sender

Suppose a system must send critical alerts to operations staff. Its first version uses email:

~~~java
class EmailSender {
    public void send(String address, String text) {
        System.out.println("EMAIL -> " + address + ": " + text);
    }
}

// Kế thừa chỉ để tận dụng phương thức send().
class CriticalAlert extends EmailSender {
    public void notifyOperator(String address, String incident) {
        send(address, "[CRITICAL] " + incident);
    }
}
~~~

This works while email is the only channel, but `CriticalAlert extends EmailSender` misrepresents the domain: **an alert is not a kind of email sender**. An alert merely *uses* a delivery mechanism.

Adding SMS, webhooks, or internal notifications can lead to separate alert subclasses for every channel. The alert also inherits the entire public/protected EmailSender API, including future methods unrelated to the alert's responsibility.

If a subclass must override parent methods to throw `UnsupportedOperationException` or weaken postconditions expected by superclass clients, it risks violating the **Liskov Substitution Principle (LSP)**. Not all inheritance violates LSP; the problem is failure to substitute under the contract.

Visualize the before-and-after structure:

~~~mermaid
classDiagram
    class EmailSender {
        +send(address, text)
    }
    class CriticalAlertOld {
        +notifyOperator(address, incident)
    }
    EmailSender <|-- CriticalAlertOld : kế thừa để dùng send

    class AlertService {
        -MessageChannel channel
        +sendCritical(recipient, incident)
    }
    class MessageChannel {
        <<interface>>
        +send(recipient, body)
    }
    class EmailChannel {
        +send(recipient, body)
    }
    class SmsChannel {
        +send(recipient, body)
    }
    class RetryingChannel {
        -MessageChannel delegate
        +send(recipient, body)
    }
    AlertService o--> MessageChannel : chứa và ủy quyền
    MessageChannel <|.. EmailChannel
    MessageChannel <|.. SmsChannel
    MessageChannel <|.. RetryingChannel
    RetryingChannel o--> MessageChannel : bọc
~~~

## 4. After Refactoring: Composition Through an Interface

Separate two responsibilities:
- `AlertService` understands the business: what constitutes a critical alert and how its message is composed.
- `MessageChannel` handles message delivery. Email, SMS, and retry-capable channels are alternative implementations.

`AlertService` **has a** `MessageChannel`; it **is not a** `MessageChannel`.

The delegated workflow:

~~~mermaid
sequenceDiagram
    actor Operator as Ứng dụng
    participant A as AlertService
    participant C as MessageChannel
    Operator->>A: sendCritical(recipient, incident)
    A->>A: Kiểm tra dữ liệu và tạo nội dung
    A->>C: send(recipient, "[CRITICAL] ...")
    C-->>A: Trả về hoặc ném lỗi
    A-->>Operator: Hoàn thành hoặc truyền lỗi
~~~

### 4.1. Project Structure

The example uses **Java 17, Maven, and JUnit Jupiter 5**. Production classes are provided as separate Java files so they can be copied and run.

~~~text
composition-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── MessageChannel.java
    │   ├── AlertService.java
    │   ├── EmailChannel.java
    │   ├── SmsChannel.java
    │   ├── DeliveryException.java
    │   ├── RetryingChannel.java
    │   └── Main.java
    └── test/java/vn/example/
        └── AlertServiceTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>composition-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Define the Message-Delivery Contract

**src/main/java/vn/example/MessageChannel.java**

~~~java
package vn.example;

@FunctionalInterface
public interface MessageChannel {
    /**
     * Gửi nội dung tới người nhận. Có thể ném RuntimeException nếu lỗi.
     * Trả về bình thường nghĩa là kênh đã xử lý yêu cầu theo hợp đồng.
     */
    void send(String recipient, String body);
}
~~~

A small interface is enough for AlertService. It does not require the alert class to know SMTP, HTTP endpoints, or SMS formatting. In a real project, the contract must specify whether `send` means provider acceptance, queueing, or actual device delivery; those guarantees differ.

### 4.3. Let the Business Object Delegate to a Collaborator

**src/main/java/vn/example/AlertService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class AlertService {
    private final MessageChannel channel;

    public AlertService(MessageChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel");
    }

    public void sendCritical(String recipient, String incident) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("recipient is blank");
        }
        if (incident == null || incident.isBlank()) {
            throw new IllegalArgumentException("incident is blank");
        }

        channel.send(recipient, "[CRITICAL] " + incident);
    }
}
~~~

Important points:
1. Constructor injection supplies dependencies during application assembly.
2. `final` keeps the collaborator reference fixed for AlertService's lifetime, preventing unexpected replacement mid-operation.
3. Public methods express **business behavior** instead of exposing the entire delivery-channel API.
4. Validation happens **before calling the channel**, so invalid inputs have no external side effects.
5. AlertService knows no concrete implementation; it only requires the channel to fulfill `send`.

### 4.4. Email and SMS Implementations

To run without external accounts, the following classes **print to the console**. They are illustrative adapters, not real email/SMS senders.

**src/main/java/vn/example/EmailChannel.java**

~~~java
package vn.example;

public final class EmailChannel implements MessageChannel {
    @Override
    public void send(String recipient, String body) {
        System.out.println("EMAIL -> " + recipient + ": " + body);
    }
}
~~~

**src/main/java/vn/example/SmsChannel.java**

~~~java
package vn.example;

public final class SmsChannel implements MessageChannel {
    @Override
    public void send(String recipient, String body) {
        System.out.println("SMS -> " + recipient + ": " + body);
    }
}
~~~

Both follow the same interface without becoming superclasses of AlertService. To add another channel, create an implementation instead of making the business class inherit from a new transport type.

### 4.5. Combine Capabilities: A Wrapper That Retries Classified Failures

Suppose temporary failures should trigger retries. Inheritance can lead to classes such as `RetryingEmailChannel`, `RetryingSmsChannel`, and `LoggingRetryingEmailChannel`, creating a combinatorial explosion of variants.

With composition, create a **wrapper (decorator)** implementing the same interface while containing another `MessageChannel`. The wrapper retries only when the delegate throws `DeliveryException`.

**src/main/java/vn/example/DeliveryException.java**

~~~java
package vn.example;

/** Trong ví dụ, biểu thị lỗi có thể thử lại. */
public final class DeliveryException extends RuntimeException {
    public DeliveryException(String message) {
        super(message);
    }
}
~~~

**src/main/java/vn/example/RetryingChannel.java**

~~~java
package vn.example;

import java.util.Objects;

public final class RetryingChannel implements MessageChannel {
    private final MessageChannel delegate;
    private final int maxAttempts;

    public RetryingChannel(MessageChannel delegate, int maxAttempts) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1");
        }
        this.maxAttempts = maxAttempts;
    }

    @Override
    public void send(String recipient, String body) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                delegate.send(recipient, body);
                return;
            } catch (DeliveryException failure) {
                if (attempt == maxAttempts) {
                    throw failure;
                }
            }
        }
    }
}
~~~

These can be composed as needed:
- `new RetryingChannel(new EmailChannel(), 3)`
- `new RetryingChannel(new SmsChannel(), 3)`
- `new AlertService(new EmailChannel())`
- `new AlertService(new RetryingChannel(new SmsChannel(), 3))`

**Count attempts correctly:** `maxAttempts = 3` means at most **3 total sends**, not an initial send plus three retries. This wrapper lacks backoff, timeouts, and idempotency policies; it only demonstrates behavior composition.

### 4.6. Composition Root: Selecting Implementations

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

public final class Main {
    public static void main(String[] args) {
        MessageChannel reliableEmail =
                new RetryingChannel(new EmailChannel(), 3);
        AlertService emailAlerts = new AlertService(reliableEmail);

        AlertService smsAlerts =
                new AlertService(new SmsChannel());

        emailAlerts.sendCritical(
                "ops@example.com", "Database is unavailable");
        smsAlerts.sendCritical(
                "+84900000000", "API latency is high");
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Expected demo output:

~~~text
EMAIL -> ops@example.com: [CRITICAL] Database is unavailable
SMS -> +84900000000: [CRITICAL] API latency is high
~~~

Concrete choices belong in the **composition root**, where the object graph is assembled at startup. AlertService has no `if (channelType.equals("SMS"))` branch and does not construct `new EmailChannel()` inside business methods.

## 5. Unit Tests: Verify Substitutability and Retry Rules

Test behavior with in-memory fake implementations, without connecting to real email or SMS services.

**src/test/java/vn/example/AlertServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class AlertServiceTest {
    record Sent(String recipient, String body) {}

    private static final class RecordingChannel implements MessageChannel {
        final List<Sent> messages = new ArrayList<>();

        @Override
        public void send(String recipient, String body) {
            messages.add(new Sent(recipient, body));
        }
    }

    private static final class FlakyChannel implements MessageChannel {
        final int failuresBeforeSuccess;
        int calls;
        int successfulSends;

        FlakyChannel(int failuresBeforeSuccess) {
            this.failuresBeforeSuccess = failuresBeforeSuccess;
        }

        @Override
        public void send(String recipient, String body) {
            calls++;
            if (calls <= failuresBeforeSuccess) {
                throw new DeliveryException("Temporary error");
            }
            successfulSends++;
        }
    }

    @Test
    void sendsCriticalMessageThroughInjectedChannel() {
        RecordingChannel channel = new RecordingChannel();
        AlertService alerts = new AlertService(channel);

        alerts.sendCritical("ops@example.com", "Disk full");

        assertEquals(
                List.of(new Sent("ops@example.com", "[CRITICAL] Disk full")),
                channel.messages);
    }

    @Test
    void invalidInputDoesNotTouchTheChannel() {
        RecordingChannel channel = new RecordingChannel();
        AlertService alerts = new AlertService(channel);

        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical(" ", "Disk full"));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", ""));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical(null, "Disk full"));
        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", null));

        assertTrue(channel.messages.isEmpty());
    }

    @Test
    void retryingChannelEventuallySucceeds() {
        FlakyChannel flaky = new FlakyChannel(2);
        AlertService alerts = new AlertService(
                new RetryingChannel(flaky, 3));

        alerts.sendCritical("ops@example.com", "Database down");

        assertEquals(3, flaky.calls);
        assertEquals(1, flaky.successfulSends);
    }

    @Test
    void retryingChannelStopsAfterAttemptLimit() {
        FlakyChannel flaky = new FlakyChannel(10);
        AlertService alerts = new AlertService(
                new RetryingChannel(flaky, 2));

        assertThrows(DeliveryException.class,
                () -> alerts.sendCritical(
                        "ops@example.com", "Database down"));

        assertEquals(2, flaky.calls);
        assertEquals(0, flaky.successfulSends);
    }

    @Test
    void unexpectedExceptionIsNotRetried() {
        AtomicInteger calls = new AtomicInteger();
        MessageChannel broken = (recipient, body) -> {
            calls.incrementAndGet();
            throw new IllegalArgumentException("Bad configuration");
        };

        AlertService alerts =
                new AlertService(new RetryingChannel(broken, 5));

        assertThrows(IllegalArgumentException.class,
                () -> alerts.sendCritical("ops@example.com", "Disk full"));
        assertEquals(1, calls.get());
    }

    @Test
    void dependenciesAndRetryLimitMustBeValid() {
        assertThrows(NullPointerException.class,
                () -> new AlertService(null));
        assertThrows(NullPointerException.class,
                () -> new RetryingChannel(null, 3));
        assertThrows(IllegalArgumentException.class,
                () -> new RetryingChannel(new RecordingChannel(), 0));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With the files above, JUnit provides **6 `@Test` methods**. The tests need no network and can deliberately simulate success, transient failures, and non-retryable failures.

| Test | What it verifies | Benefit of composition |
| --- | --- | --- |
| sendsCriticalMessageThroughInjectedChannel | Correct message and recipient reach the collaborator | Replace real email with a fake without changing AlertService |
| invalidInputDoesNotTouchTheChannel | Invalid input is blocked before side effects | Business rules remain independent of implementation |
| retryingChannelEventuallySucceeds | Fails 2 times and succeeds on attempt 3 | The wrapper can decorate any implementation |
| retryingChannelStopsAfterAttemptLimit | A maximum of 2 calls is respected | Retry policy can be tested independently |
| unexpectedExceptionIsNotRetried | Non-retryable failures do not trigger repeated calls | Clear failure-policy boundaries |
| dependenciesAndRetryLimitMustBeValid | Objects cannot be created with missing required dependencies | Constructors establish invariants |

Because AlertService accepts a `MessageChannel`, the same business behavior can be tested with email, SMS, or fake channels. Adapters talking to external services still need **separate integration tests** for real APIs, configuration, and failures.

## 6. Steps for Refactoring Inheritance into Composition

Do not remove `extends` before understanding clients and public contracts. A safe sequence:

1. **Confirm the current relationship.** Ask "Is AlertService really an EmailSender?" and "does it inherit for classification or just to use `send`?"
2. **Establish existing behavior.** Test messages, parameters, errors, and send counts. In particular, check whether callers rely on using the subclass as its superclass.
3. **Find the minimal dependency.** If the subclass only needs `send(recipient, body)`, introduce `MessageChannel` rather than exposing all of EmailSender's API.
4. **Introduce composition.** Add `private final MessageChannel channel` and a constructor receiving the interface. During gradual migration, retain a short delegating method for old APIs if needed.
5. **Replace inherited calls.** Change `send(...)` to `channel.send(...)`. Regression tests must still pass.
6. **Migrate callers.** Code that previously created `new CriticalAlert()` now supplies an appropriate implementation. If an API accepts `EmailSender` and clients pass `CriticalAlert`, assess transitional adapters; removing `extends` is a **type-compatibility change**.
7. **Remove unnecessary inheritance.** After checking callers and compatibility, remove `extends` and overrides that existed solely for the superclass.
8. **Verify design and behavior.** Compile, run unit and necessary integration tests, check public APIs, and confirm implementation selection through configuration.

~~~mermaid
flowchart TD
    A["Lớp con extends lớp cha chỉ để dùng một chức năng"] --> B["Khoanh vùng hợp đồng và các caller"]
    B --> C["Viết test hồi quy"]
    C --> D["Tạo interface cho chức năng cần dùng"]
    D --> E["Tiêm đối tượng qua constructor"]
    E --> F["Đổi lời gọi kế thừa thành ủy quyền"]
    F --> G["Chuyển caller và kiểm tra tính tương thích"]
    G --> H{"Test và hợp đồng đạt?"}
    H -->|Không| I["Chỉnh sai lệch hoặc adapter chuyển tiếp"]
    I --> G
    H -->|Có| J["Bỏ extends dư thừa, rà soát thiết kế"]
~~~

### 6.1. When Is a Compatibility Adapter Needed?

For example, if a public library exposes `CriticalAlert extends EmailSender`, external code may write:

~~~java
// Ví dụ từ API cũ:
EmailSender sender = new CriticalAlert();
~~~

Once CriticalAlert becomes a class containing MessageChannel, that line **no longer compiles**. This is not an algorithmic defect but a breaking change for callers. Determine binary/source compatibility requirements, plan versioning, or supply a public adapter during migration.

In an internal codebase where all callers can be changed, migration may be simpler. For a published API, altering inheritance relationships requires more scrutiny than renaming a private method.

## 7. How Do Strategy, Decorator, and Dependency Injection Relate?

**Composition** is the relationship in which one object contains or uses another. It is the underlying mechanism.

**Strategy pattern** uses interchangeable implementations of the same interface. Here, `EmailChannel` and `SmsChannel` are alternative delivery strategies selected when constructing AlertService.

**Decorator pattern** wraps an implementation with another implementation of the same interface to extend behavior. `RetryingChannel` implements `MessageChannel` while also containing a `MessageChannel`, adding retries without modifying EmailChannel/SmsChannel.

**Dependency Injection (DI)** supplies collaborators externally. `new AlertService(new SmsChannel())` already uses constructor injection; composition does not require a DI framework.

| Question | Relevant concept |
| --- | --- |
| How does object A use the capabilities of B? | Composition + delegation |
| How can email or SMS be selected for the same need? | Strategy |
| How can retries or logging be added without modifying the base channel? | Decorator |
| Who constructs and supplies the channel to AlertService? | Dependency injection / composition root |

These patterns **can work together** rather than exclude one another. `AlertService` receives a Strategy through its constructor; that Strategy may itself be a Decorator wrapping another adapter.

## 8. When Is Inheritance Still Appropriate?

Inheritance adds value when subclasses are genuine specializations of their superclass, honor a stable contract, and do not unexpectedly strengthen preconditions or weaken postconditions. Examples include internal hierarchies with documented extension hooks or stable framework base classes. Even then, shared superclass-contract tests may be warranted.

Conversely, if subclasses override many methods to do nothing, throw exceptions, or rely on superclass `protected` fields to maintain consistent state, revisit the design.

A practical decision guide:

| Signal | Preferred direction |
| --- | --- |
| "A is a B" and can substitute for B under its contract | Inheritance may fit |
| "A has a B" or "A uses B's service" | Composition |
| Different implementations are selected by environment | Composition through an interface |
| Logging, retries, and metrics need to be layered | Composition/Decorator |
| Subclasses proliferate for every feature combination | Separate and compose independent capabilities |
| Changing a superclass unexpectedly breaks many subclasses | Reduce superclass coupling; consider composition |
| One small algorithm exists with no need for substitution | Keep it directly in the class; avoid needless abstractions |

**Do not mechanically create an interface for every class.** If a simple pure calculation has no meaningful alternative implementation or boundary needing isolation, an interface and delegate object only increase reading overhead.

## 9. Common Conversion Mistakes

### 9.1. Replacing Extends with a Field While Exposing the Whole API

~~~java
// Ví dụ cách chuyển chưa tốt:
class PoorAlertService {
    private final EmailChannel email = new EmailChannel();

    void sendRaw(String recipient, String body) {
        email.send(recipient, body);
    }
}
~~~

This uses composition syntactically but remains bound to a concrete `EmailChannel`, and its public API still exposes raw sending instead of alert business behavior. If multiple channels are truly needed, receiving `MessageChannel` through the constructor gives a better separation.

### 9.2. Turning a Service into a "God Object"

Composition does not justify one class containing dozens of dependencies and making every decision. If AlertService calculates prices, authorizes users, schedules tasks, and sends emails, its primary problem is still too much responsibility. Separate use cases, policies, and adapters where needed.

### 9.3. Blindly Retrying Non-Idempotent Operations

The example retries only channel `DeliveryException` failures. In real services, the provider may accept the initial request while the response is lost; retrying can send duplicate emails/SMS messages. Critical actions such as payments require idempotency keys, durable state, queries/reconciliation, backoff, and explicit retry rules. Composition helps **locate** a policy in the right component; it does not automatically make that policy safe.

### 9.4. Confusing Composition with Interface Implementation

`EmailChannel implements MessageChannel` uses an interface to declare a contract. `AlertService` composes a `MessageChannel` because it has a `channel` field. Both relationships can coexist and serve different purposes.

### 9.5. Ignoring Lifecycle and Thread Safety

If multiple threads share a stateful collaborator, verify that the collaborator is concurrency-safe. `private final` fixes the **reference**, not the immutability or thread safety of the referenced object.

## 10. Guided Practice

**Exercise 1 — Add a Webhook Channel.** Implement `WebhookChannel implements MessageChannel` as a demo that records URLs and messages in a list. Use `new AlertService(new WebhookChannel(...))`, verify the alert content, and leave AlertService unchanged.

**Exercise 2 — Add LoggingChannel.** Write a decorator around `MessageChannel` that counts calls. Try `new LoggingChannel(new RetryingChannel(new EmailChannel(), 3))` and `new RetryingChannel(new LoggingChannel(new EmailChannel()), 3)`. Explain why wrapper order can produce different counts.

**Exercise 3 — Assess Retry Tests.** Create a fake that fails on attempt 1 and succeeds on attempt 2. Verify that maxAttempts = 1 propagates the failure, while maxAttempts = 2 succeeds. Ensure `IllegalArgumentException` is never retried.

**Exercise 4 — Identify Relationships.** Consider: "Car uses Engine," "SavingsAccount is an Account," "OrderService uses EmailSender," and "CSV exporter is a Formatter." For each, distinguish genuine business/data relationships from substitutable capabilities; explain when `extends`, `implements`, or a composed field is appropriate.

**Exercise 5 — Assess the Public API.** Find callers using subclass instances as their superclass type before refactoring. Document calls that rely on inheritance and propose adapters/migration paths before removing extends.

### Post-Refactoring Checklist

- [ ] Each class has a role that can be explained as one clear responsibility.
- [ ] Consumers depend on small interfaces without unnecessary knowledge of concrete adapter internals.
- [ ] Inherited methods inconsistent with the consumer's semantics are not exposed.
- [ ] Success, failure, validation, and retry-limit cases are tested.
- [ ] Callers and public contracts have been checked for compatibility.
- [ ] Real external side effects are covered by integration tests at infrastructure boundaries.
- [ ] Composition is used because it improves clarity, not merely to avoid the keyword `extends`.

**Expected outcome:** You can replace alert-delivery channels or add retries through **object composition** without editing business classes or adding subclass hierarchies for every feature combination.
