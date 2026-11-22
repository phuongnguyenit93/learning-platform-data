# Replacing a Hard-to-Extend Inheritance Hierarchy with Composition

When a system has multiple ways to send notifications, multiple content formats, and multiple processing policies, using a subclass for every combination quickly creates an inheritance hierarchy that is hard to maintain. **Composition** solves this problem by having an object hold and coordinate components with distinct responsibilities, instead of encoding every variant into `extends` relationships.

This practice moves from a design prone to bloat to a design that combines independent behaviors, then verifies it with a runnable Java 17+ program.

## 1. Identifying an Inheritance Hierarchy That Is Hard to Extend

Suppose an application sends notifications and has the following dimensions of variation:

- Delivery channel: email, SMS, push notification.
- Presentation style: plain text, priority-prefixed, or language-specific template.
- Delivery policy: send once, retry on failure, or detailed logging.

If each subclass represents one combination, we may have to create `EmailNotifier`, `UrgentEmailNotifier`, `SmsNotifier`, `UrgentSmsNotifier`, `RetryingEmailNotifier`, `UrgentRetryingSmsNotifier`, and continue adding classes whenever new variants appear. With multiple independent dimensions, the number of combinations can grow as the product of the choices in each dimension. For example, 3 channels × 3 presentation styles × 2 policies already produce 18 potential combinations.

The problem is not that “having many subclasses is always wrong.” Inheritance remains useful when a subclass is genuinely a specialized form of its superclass and can honor the superclass contract. The problem arises when we use inheritance solely to combine independent features together.

Common signs:

- Adding a new channel forces creating multiple subclasses for each priority level or policy.
- The same sending or formatting code is duplicated across multiple subclasses.
- Changing behavior at runtime requires choosing a different class or rebuilding the entire object tree.
- A subclass inherits behavior it does not need, or overrides multiple methods to disable behavior from the superclass.
- Changes in the superclass cause unexpected effects on subclasses.

## 2. Why Is Composition a Good Fit?

Composition means that an object uses other objects to perform work. The higher-level object is responsible for coordination; each component is responsible for one specific behavior.

For the notification example, we can separate it into:

- `MessageSender`: sends a message over a channel.
- `MessageFormatter`: transforms the input content into the content to be sent.
- `NotificationService`: coordinates the formatter and sender in the proper order.

As a result, the delivery channel and presentation style become two independent dimensions. We can combine `EmailSender` with `PlainFormatter`, or `SmsSender` with `PriorityFormatter`, without writing a subclass for each pair.

Composition often goes hand in hand with dependency injection: components are passed in through the constructor. This approach makes replacing implementations easy, makes testing with fakes/mocks convenient, and clearly expresses the dependencies that a class needs.

## 3. Designing in Java with Small Interfaces

Define contracts by role rather than by combination:

```java
interface MessageSender {
    void send(String message);
}

interface MessageFormatter {
    String format(String message);
}
```

`MessageSender` only cares about sending a string. `MessageFormatter` only cares about how to transform a string. They do not need to know about each other and do not depend on `NotificationService`.

The coordinating object holds the dependencies and delegates the work:

```java
final class NotificationService {
    private final MessageSender sender;
    private final MessageFormatter formatter;

    NotificationService(MessageSender sender, MessageFormatter formatter) {
        this.sender = java.util.Objects.requireNonNull(sender);
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    void notify(String message) {
        String formatted = formatter.format(message);
        sender.send(formatted);
    }
}
```

The constructor ensures that the dependencies are not `null`, and the `final` fields prevent these dependencies from being accidentally replaced after the service is created. The `notify` method does not need to know whether it is sending via email or SMS, nor how the content is formatted.

## 4. Complete Runnable Program

Save the code below as `CompositionDemo.java`. The senders in the example only print to the console to illustrate the architecture; they do not send real emails or SMS messages.

```java
public class CompositionDemo {
    interface MessageSender {
        void send(String message);
    }

    interface MessageFormatter {
        String format(String message);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("EMAIL: " + message);
        }
    }

    static final class SmsSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("SMS: " + message);
        }
    }

    static final class PlainFormatter implements MessageFormatter {
        @Override
        public String format(String message) {
            return message;
        }
    }

    static final class PriorityFormatter implements MessageFormatter {
        @Override
        public String format(String message) {
            return "[PRIORITY] " + message;
        }
    }

    static final class NotificationService {
        private final MessageSender sender;
        private final MessageFormatter formatter;

        NotificationService(MessageSender sender, MessageFormatter formatter) {
            this.sender = java.util.Objects.requireNonNull(sender);
            this.formatter = java.util.Objects.requireNonNull(formatter);
        }

        void notify(String message) {
            sender.send(formatter.format(message));
        }
    }

    public static void main(String[] args) {
        NotificationService normalEmail = new NotificationService(
                new EmailSender(), new PlainFormatter());
        normalEmail.notify("Build completed");

        NotificationService prioritySms = new NotificationService(
                new SmsSender(), new PriorityFormatter());
        prioritySms.notify("Server is down");

        NotificationService priorityEmail = new NotificationService(
                new EmailSender(), new PriorityFormatter());
        priorityEmail.notify("Deployment started");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CompositionDemo.java
java CompositionDemo
```

Exact stdout:

```text
EMAIL: Build completed
SMS: [PRIORITY] Server is down
EMAIL: [PRIORITY] Deployment started
```

Three configurations use two sender types and two formatter types without needing classes like `PriorityEmailNotifier` or `PrioritySmsNotifier`. `NotificationService` only coordinates the behaviors, while each small implementation focuses on a single responsibility.

## 5. Adding Variants Without Modifying the Service

Suppose we need to send notifications via push notification. We add a new implementation:

```java
static final class PushSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("PUSH: " + message);
    }
}
```

Then create the service with `new PushSender()` and the desired formatter. There is no need to add an `if/else` branch to `NotificationService`, and no need to create new subclasses for every presentation style.

Similarly, to add a format with an event code, we create a new `MessageFormatter` implementation. Only the configurations that need the new behavior will use that formatter. Existing components continue to operate independently.

In real-world applications, dependencies can be configured directly via constructors, factories, or a dependency injection framework. A framework is not a prerequisite for applying composition; passing dependencies through the constructor already demonstrates this principle.

## 6. Comparing Inheritance and Composition

| Criterion | Per-Combination Inheritance Hierarchy | Composition |
| --- | --- | --- |
| Adding a new channel | May require creating multiple new subclasses. | Add one `MessageSender` implementation. |
| Adding a formatting style | May multiply the number of subclasses across existing variants. | Add one `MessageFormatter` implementation. |
| Combining behaviors | Combinations are often encoded in class names and structure. | Choose dependencies when creating the object. |
| Testing | May require instantiating a complex class hierarchy. | Can pass simple fake senders and formatters. |
| Modeling relationship | Suitable when the subclass is truly a kind of the superclass. | Suitable when an object coordinates independent roles. |
| Cost | The class hierarchy can bloat and create tight coupling. | Adds interfaces/objects and a configuration step. |

Composition is not automatically better in every case. If there is only one stable behavior, not many variants, and the “is-a” relationship is genuinely clear, a simple class or inheritance may be easier to understand. Avoid creating interfaces and wrapper classes solely to forward a single call without providing any design benefit.

## 7. Common Mistakes When Switching to Composition

### Splitting into Too Many Abstractions

Do not create interfaces for every class out of habit. Extract a responsibility when there is a practical reason: the behavior varies independently, there are multiple implementations, it needs to be swapped in tests, or that boundary makes the design easier to understand.

### Putting Coordination in the Wrong Place

`NotificationService` should coordinate the sequence of formatting and then sending. `EmailSender` should not decide priority formatting on its own if that formatting is a separate dimension of variation. If each sender contains the same formatting logic, we end up recreating duplication.

### Using Inheritance Unnecessarily Among Small Components

Implementations can be independent concrete classes. Only use `extends` when you genuinely need to reuse or specialize a type with an appropriate relationship; there is no need to create a common superclass just because a few classes happen to share one line of code.

### Making Dependencies Mutable Without Control

If a dependency does not need to change after the service is created, use a `final` field and pass it through the constructor. If behavior needs to change during the object's lifecycle, design an explicit change point rather than allowing every field to be replaced arbitrarily.

### Forgetting Business Rules When Composing Components

Composition only helps combine behaviors; it does not automatically solve sending order, retries, timeouts, error handling, or consistency. If adding retries, specify which operation is retried, which exceptions are considered transient, and the risk of duplicate sends. Those rules require their own contracts and tests.

## 8. How to Practice Safe Refactoring

When encountering a hard-to-extend inheritance hierarchy in a project, proceed step by step:

1. List the independent dimensions of variation, such as delivery channel, formatting, and retry policy.
2. Look for duplicated code or subclasses that differ only in one small behavior.
3. Choose a responsibility with a clear boundary and define a small interface if multiple implementations or easy replacement are needed.
4. Move that behavior into a separate component; let the main object retain the coordination role.
5. Pass the component through the constructor and preserve the existing contract of the public object.
6. Add tests to prove that the behavior before and after refactoring is equivalent for the currently supported scenarios.
7. Add a new variant to test the design: if it only requires adding an implementation and reconfiguring dependencies, the boundary is usually sound.

There is no need to convert the entire class hierarchy in one go. Refactor one high-value branch, keep the tests passing consistently, and continue when a concrete need arises.

## 9. Self-Check Exercises

1. If there are 4 delivery channels and 3 formats, how many combination classes might a per-combination subclass design need? Why can that number increase further when retries are added?
2. In the example, why does `NotificationService` not need to know the concrete sender class?
3. Add an `UppercaseFormatter` that converts the message to uppercase. Do you have to modify `NotificationService`?
4. Write a fake `MessageSender` that only records the received message, then test that the formatter runs before the sender.
5. When does composition become unnecessarily complex? Give an example of a case where a simple class would be clearer.

## Conclusion

When an inheritance hierarchy encodes multiple independent dimensions of variation, consider turning each behavior into a component with a clear responsibility and having the main object coordinate them through composition. This design enables flexible combinations, adding variants with fewer changes, and testing each behavior independently. Keep abstractions at the necessary level, preserve existing contracts, and refactor step by step with tests.
