# A Running Example: Multiple Ways to Handle the Same Request

In the topic of **Java abstract classes, interfaces, and polymorphism**, the easiest way to see the difference between these tools is to keep a single business requirement fixed while varying how it is handled. The example below uses the requirement: **“Notify customer KH-42 that the order has been confirmed”**. The same message can be processed via email, SMS, or an in-app notification.

Lesson objectives:

- Identify the **stable** part of the requirement (customer ID, content, send operation, and result) and the **varying** part (how each channel sends it).
- Understand how an `interface` expresses a shared contract, an `abstract class` reuses a common workflow, and **polymorphism** selects the implementation at runtime.
- Know when to use an abstract class, when to use an interface, and why you should combine them with a common calling component.
- Read, compile, and explain a complete Java 17 program; clearly see the boundary between a simulated example and a real notification delivery system.

## 1. Defining One Request, Multiple Ways to Fulfill It

Imagine a service receiving a request object:

| Information | Example value | Varies by channel? |
| --- | --- | --- |
| Customer ID | `KH-42` | No |
| Content | `Đơn hàng đã được xác nhận` | No |
| Action | Send notification | No |
| Delivery mechanism | Email, SMS, in-app notification | **Yes** |
| Result | Handling channel and status | Same structure, different channel values |

If all the logic is written inside an `if/else` or `switch` block branching on the channel name, every new channel forces us to open up that branching block. Different cases can also easily share the wrong data, duplicate validation code, and make tests hard to isolate. With only a few short branches, that choice can still be simple enough; problems emerge as the number of handling approaches and rules grows.

We separate three roles:

1. **Request** (`NotificationRequest`): immutable data that every channel receives.
2. **Contract** (`NotificationChannel`): every channel has `name()` and `send(request)`.
3. **Coordinator** (`NotificationService`): uses a list of channels through the same `NotificationChannel` type, without needing to know the details of email, SMS, or in-app notifications.

## 2. Interface: Unifying How It Is Called, Allowing Different Implementations

`interface NotificationChannel` declares only the operations that callers are allowed to rely on:

```java
interface NotificationChannel {
    String name();
    SendResult send(NotificationRequest request);
}
```

`EmailChannel`, `SmsChannel`, and `InAppChannel` can all be viewed as a `NotificationChannel`. When `NotificationService` calls `channel.send(request)`, Java selects the method version of the **actual object** at runtime (dynamic dispatch). The variable type is the interface; the executed behavior comes from the implementing class.

The contract here must be understood in terms of **semantics** as well, not just signatures: accept a valid request, perform the channel's operation, and return a `SendResult`; if an error occurs, there must be a clear error-reporting policy. Declaring an interface **does not automatically** guarantee that every class has the same handling quality, validation, or safety when sending multiple times.

An interface can also declare `default`, `static`, and `private` helper methods to support implementations. However, an interface has no constructors and does not hold instance state like a base class. Fields declared on an interface are `public static final` constants; avoid placing per-channel mutable data there.

## 3. Abstract Class: Sharing a Common Workflow When Classes Are Truly Related

Email and SMS in the example share the same steps: validating the request object, logging the check step, performing the delivery, and creating the result. We can group the **shared workflow** into an abstract class:

```java
abstract class AbstractNotificationChannel implements NotificationChannel {
    @Override
    public final SendResult send(NotificationRequest request) {
        // Common check -> specific execution -> common result creation.
        ...
    }

    protected abstract void deliver(NotificationRequest request);
}
```

*This snippet illustrates the structure and is not a standalone program; the full runnable code is in Section 4.*

- An `abstract class` **cannot be instantiated directly** with `new AbstractNotificationChannel()`, though it can have constructors, instance fields, concrete methods, and abstract methods.
- `send()` is already implemented and marked `final`: subclasses cannot bypass the fixed processing order.
- `deliver()` is an “extension point” implemented by subclasses. This is a simple form of **Template Method**: the superclass holds the algorithm skeleton, and subclasses provide the varying step.
- Email and SMS extend `AbstractNotificationChannel`; they also satisfy the `NotificationChannel` interface because the superclass `implements` that interface.
- A Java class can directly `extends` only **one** class, but can `implements` multiple interfaces. Therefore, do not force every channel into the same superclass if they do not share a meaningful workflow.

`InAppChannel` will **implement the interface directly** to demonstrate that the contract is independent of the inheritance hierarchy. It does not need to perform the check-logging step imposed by the superclass.

## 4. Complete Java 17 Program

Save the following code to **`Main.java`**. All auxiliary types are nested inside `Main`, so it can be compiled as a single file. This is a **console-based notification simulation**: it does not call SMTP, an SMS provider, or a push notification API; `SENT` is a simulated result.

```java
import java.util.List;
import java.util.Objects;

public class Main {
    record NotificationRequest(String customerId, String message) {
        NotificationRequest {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(message, "message");
            if (customerId.isBlank() || message.isBlank()) {
                throw new IllegalArgumentException("Thông tin không được để trống");
            }
        }
    }

    record SendResult(String channel, String status) {}

    interface NotificationChannel {
        String name();
        SendResult send(NotificationRequest request);
    }

    static abstract class AbstractNotificationChannel
            implements NotificationChannel {
        @Override
        public final SendResult send(NotificationRequest request) {
            Objects.requireNonNull(request, "request");
            System.out.println("Kiểm tra yêu cầu: " + request.customerId());
            deliver(request);
            return new SendResult(name(), "SENT");
        }

        protected abstract void deliver(NotificationRequest request);
    }

    static final class EmailChannel extends AbstractNotificationChannel {
        @Override
        public String name() {
            return "EMAIL";
        }

        @Override
        protected void deliver(NotificationRequest request) {
            System.out.println("EMAIL -> " + request.customerId()
                    + ": " + request.message());
        }
    }

    static final class SmsChannel extends AbstractNotificationChannel {
        @Override
        public String name() {
            return "SMS";
        }

        @Override
        protected void deliver(NotificationRequest request) {
            System.out.println("SMS -> " + request.customerId()
                    + ": " + request.message());
        }
    }

    static final class InAppChannel implements NotificationChannel {
        @Override
        public String name() {
            return "IN_APP";
        }

        @Override
        public SendResult send(NotificationRequest request) {
            Objects.requireNonNull(request, "request");
            System.out.println("IN_APP -> " + request.customerId()
                    + ": " + request.message());
            return new SendResult(name(), "SENT");
        }
    }

    static final class NotificationService {
        private final List<NotificationChannel> channels;

        NotificationService(List<NotificationChannel> channels) {
            this.channels = List.copyOf(channels);
        }

        void sendAll(NotificationRequest request) {
            for (NotificationChannel channel : channels) {
                SendResult result = channel.send(request);
                System.out.println("Kết quả " + result.channel()
                        + ": " + result.status());
            }
        }
    }

    public static void main(String[] args) {
        NotificationRequest request = new NotificationRequest(
                "KH-42", "Đơn hàng đã được xác nhận");

        NotificationService service = new NotificationService(List.of(
                new EmailChannel(),
                new SmsChannel(),
                new InAppChannel()));

        service.sendAll(request);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac Main.java
java Main
```

Expected output (UTF-8 when the terminal supports Vietnamese):

```text
Kiểm tra yêu cầu: KH-42
EMAIL -> KH-42: Đơn hàng đã được xác nhận
Kết quả EMAIL: SENT
Kiểm tra yêu cầu: KH-42
SMS -> KH-42: Đơn hàng đã được xác nhận
Kết quả SMS: SENT
IN_APP -> KH-42: Đơn hàng đã được xác nhận
Kết quả IN_APP: SENT
```

**Tracing the execution flow:** `main()` creates **one** `NotificationRequest`, then passes that exact object sequentially to three implementations. `NotificationService` only sees three elements of type `NotificationChannel`. The first two elements run the shared `send()` of `AbstractNotificationChannel`, which then calls `EmailChannel.deliver()` and `SmsChannel.deliver()` respectively; the last element runs `InAppChannel.send()` directly. Therefore, the first two channels print the extra “Kiểm tra yêu cầu” line, while the third channel does not.

`record` provides a data-carrying object with the accessors `customerId()` and `message()`. The compact constructor checks for `null` and whitespace-only strings, so the example has a consistent validation point when creating a request. `List.copyOf(channels)` creates a list whose elements cannot be added or removed through the `channels` variable; it **does not** make the channel objects themselves immutable.

## 5. What Actually Provides Polymorphism?

Look at the call inside the loop:

```java
for (NotificationChannel channel : channels) {
    SendResult result = channel.send(request);
    // ...
}
```

The call is the same, yet the behavior is selected based on the object:

| Runtime object | Reference type in loop | `send()` implementation executed | Specific step |
| --- | --- | --- | --- |
| `EmailChannel` | `NotificationChannel` | `AbstractNotificationChannel.send()` | `EmailChannel.deliver()` |
| `SmsChannel` | `NotificationChannel` | `AbstractNotificationChannel.send()` | `SmsChannel.deliver()` |
| `InAppChannel` | `NotificationChannel` | `InAppChannel.send()` | Does not use the abstract superclass |

The interface contract is **type polymorphism**; overriding methods within an inheritance hierarchy is one way to provide **behavioral polymorphism**. A reference with an interface type can directly invoke only the methods declared by the interface, even if the concrete class has additional methods of its own.

In the example, the program uses *both* ideas: `NotificationService` depends on the **interface**, while some implementing classes choose to reuse the **abstract class**. These are independent choices and can be combined.

## 6. Adding a New Handling Mechanism Without Modifying the Coordinator

Suppose we need to add a `WebhookChannel`. We can `implements NotificationChannel` directly, similar to `InAppChannel`, and then add an instance to the list at the configuration site:

```java
// Example of the configuration point; this snippet is not a standalone Java file.
NotificationService service = new NotificationService(List.of(
        new EmailChannel(),
        new SmsChannel(),
        new InAppChannel(),
        new WebhookChannel()));
```

`WebhookChannel` must be defined for the extension example above to compile. The key takeaway is that **the code of `NotificationService.sendAll()` does not need to be modified**. The object assembly site (here `main()`) still has to be updated so it knows about the new channel. In larger applications, the list can be configured via dependency injection; an interface on its own does not automatically discover implementing classes.

When should you choose `extends AbstractNotificationChannel`? When the new channel needs the exact validate → delegate → create result workflow, with a fixed order that must not be changed. When should you `implements NotificationChannel` directly? When the channel uses a different workflow while still fulfilling the shared contract. If two classes only share a few small lines, a **shared component passed in** (composition) is sometimes a better fit than a superclass.

## 7. Limitations of the Example and Decisions in Real-World Application

| Concern | Current example | When implementing a real system |
| --- | --- | --- |
| Sending data | `System.out.println()` | Adapters integrating SMTP/SMS/push; credentials and configuration kept separate |
| Status | Returns `SENT` after printing | Distinguish accepted for processing, submitted to provider, delivered successfully, and failed |
| Request validation | `record` disallows null/blank | Also validate format, permissions, length, and destination routing |
| When a channel fails | Exception stops `sendAll()` | Decide on fail-fast, continuing to other channels, retries, timeouts, and idempotency |
| Sequential invocation | Executes in list order | Consider asynchronous execution, concurrency, and resource limits |
| Logging and tracing | Console printing | Contextual logging, metrics, tracing; do not log sensitive data |

Do not assume that “calling `send()` returns `SENT`” means the customer has received the notification. In a distributed system, successful delivery may only be confirmed via a callback or an event from the provider. Define the semantics of `SendResult` to match the real system and error-handling policy before replacing simulated code with production code.

## 8. Common Misconceptions

- **“If you have an interface, you don't need an abstract class.”** An interface unifies the contract; an abstract class can store state and shared workflows. You can use both, as in the program above.
- **“An abstract class must contain only abstract methods.”** False: it can contain constructors, fields, concrete methods, `final` methods, and abstract methods; an `abstract` class can even declare no abstract methods at all.
- **“Every subclass must override `send()`.”** False: two classes inherit `final send()` from the superclass and only implement `deliver()`. Overriding a `final` method is a compile-time error.
- **“Adding an interface automatically makes code extensible.”** You must keep the contract stable, choose where implementations are instantiated/registered, and avoid reintroducing `instanceof` or `switch` on concrete classes back into `NotificationService`.
- **“Inheritance is just for avoiding code duplication.”** If classes do not share the same nature or workflow, inheritance can impose wrong coupling. Prefer composition when you only want to share a dependency or policy.
- **“Polymorphism means overloading.”** Overloading selects the matching signature based on parameters at compile time; this example uses overriding/interface implementation and dynamic dispatch at runtime.
- **“Validating once guarantees the system is safe.”** Validation when constructing `NotificationRequest` protects the record's data; you still need to handle `null` requests, provider errors, and specific business rules.

## 9. Self-Check Questions

1. Why does `NotificationService` still compile if a new channel is written with `implements NotificationChannel` instead of `extends AbstractNotificationChannel`?
2. If you remove the `final` keyword from `AbstractNotificationChannel.send()`, what could a subclass do that would prevent the common validation workflow from being executed?
3. Why do only email and SMS print the “Kiểm tra yêu cầu” line, even though all three receive the same `NotificationRequest`?
4. Try adding a `ConsoleChannel` that implements `NotificationChannel` and adding it to the list. Verify that `NotificationService.sendAll()` does not change.
5. Try making `EmailChannel.deliver()` throw `IllegalStateException`. Predict whether the remaining channels will run in the current version; then design an error-handling policy suitable for the business requirements.

**Learning takeaway:** When **one request has multiple ways of being handled**, a useful model is a shared input data type + an interface representing the capability + independent implementing classes. Only add an abstract class where there is genuinely a common workflow worth reusing. Polymorphism allows the coordinator to send the same command through that contract, while the concrete decision is made by the object at runtime.
