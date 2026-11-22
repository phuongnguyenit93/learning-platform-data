# Concrete Methods and Shared Implementation Code in Abstract Classes (Java)

## 1. Core Nature: An Abstract Class Can Still Implement Methods

In Java, an `abstract class` cannot be instantiated directly with `new`, yet **not all of its methods have to be abstract**. It can combine:

- **Concrete methods (methods with a body):** have a code block `{ ... }`, providing default behavior or a shared workflow for subclasses.
- **Abstract methods:** declare only a contract, end with `;`, and have no body. Concrete subclasses must implement the abstract methods that have not yet been implemented along the inheritance chain.
- **Fields and constructors:** store shared state and ensure the initialization conditions that the shared methods require.

Formal example:

```java
abstract class BaseTask {
    public void start() {                    // Has a body: shared
        System.out.println("Bắt đầu");
        execute();
    }

    protected abstract void execute();       // No body: provided by subclass
}
```

`start()` is a method already implemented in the superclass. Each subclass inheriting from `BaseTask` can reuse `start()` without rewriting the statement that prints the message and calls `execute()`. When `execute()` runs, Java selects the implementation corresponding to the actual object at runtime.

A class declared `abstract` **is still valid even without any `abstract` methods**; in that case, this keyword primarily prevents direct instantiation and reserves the class as a base for subclasses.

## 2. Why Is Shared Implementation Code Needed?

Suppose several kinds of notification senders must all validate input, normalize content, and write logs, while each kind sends notifications using a different mechanism. If each class duplicates the three common operations, bug fixes are easily missed and behavior gradually becomes inconsistent.

Moving the identical steps into an abstract superclass creates a shared point of maintenance:

1. The superclass contains **the invariant part of the workflow**: validation, normalization, logging, and the call sequence.
2. The superclass declares **variation points** as abstract methods or concrete methods that allow overriding.
3. Subclasses only write the part that actually differs: how to send via email, SMS, or another channel.

This is the foundation of the **Template Method** design pattern: a skeleton method in the superclass defines the steps, while subclasses provide certain specific steps. Not every shared method has to participate in the Template Method pattern; a concrete `protected` utility method for subclasses to call is also valid reuse.

## 3. Java 17+ Example: Sharing the Notification Sending Flow

Save the entire following program in the file `Main.java`:

```java
import java.util.Objects;

abstract class NotificationSender {
    private final String channelName;

    protected NotificationSender(String channelName) {
        this.channelName = Objects.requireNonNull(channelName);
    }

    // Shared workflow: subclasses must not change the order of steps.
    public final void send(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        if (recipient.isBlank()) {
            throw new IllegalArgumentException("recipient không được trống");
        }

        String normalized = normalize(message);
        log(recipient);
        deliver(recipient, normalized);
    }

    // Has a default body; subclasses can customize it if needed.
    protected String normalize(String message) {
        return message.strip();
    }

    // Has a body, reused intact for all sending channels.
    private void log(String recipient) {
        System.out.println("[" + channelName + "] Chuẩn bị gửi tới " + recipient);
    }

    // Variable part: each channel must implement this itself.
    protected abstract void deliver(String recipient, String message);
}

final class EmailSender extends NotificationSender {
    EmailSender() {
        super("email");
    }

    @Override
    protected void deliver(String recipient, String message) {
        System.out.println("EMAIL tới " + recipient + ": " + message);
    }
}

final class SmsSender extends NotificationSender {
    SmsSender() {
        super("sms");
    }

    // Only changes the normalization step; still reuses the superclass step.
    @Override
    protected String normalize(String message) {
        return super.normalize(message).replaceAll("\\s+", " ");
    }

    @Override
    protected void deliver(String recipient, String message) {
        System.out.println("SMS tới " + recipient + ": " + message);
    }
}

public class Main {
    public static void main(String[] args) {
        NotificationSender email = new EmailSender();
        NotificationSender sms = new SmsSender();

        email.send("an@example.com", "  Xin chào An  ");
        sms.send("0901234567", "  Hẹn     gặp  ");
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac -encoding UTF-8 Main.java
java Main
```

Standard output:

```text
[email] Chuẩn bị gửi tới an@example.com
EMAIL tới an@example.com: Xin chào An
[sms] Chuẩn bị gửi tới 0901234567
SMS tới 0901234567: Hẹn gặp
```

Explanation of each role:

| Component | Method Type | Role |
| --- | --- | --- |
| `send(...)` | `public final`, with body | Provides the entire shared processing flow; `final` forbids subclasses from overriding so validation and logging are not bypassed. |
| `normalize(...)` | `protected`, with body | Provides the default `strip()`; `SmsSender` overrides it and calls `super.normalize(...)` to reuse what is already there. |
| `log(...)` | `private`, with body | Internal detail called only by the superclass; all subclasses still benefit from the logging behavior through `send(...)`. |
| `deliver(...)` | `protected abstract`, no body | Forces each concrete subclass to supply its own delivery operation. |
| `NotificationSender(...)` | `protected` constructor | Initializes `channelName` when a subclass is created; does not instantiate `NotificationSender` directly. |

Key point: the variable `email` has the declared type `NotificationSender`, while the actual object is an `EmailSender`. The call `email.send(...)` uses the `send` body inherited from the superclass; inside it, the call to `deliver(...)` is dynamically dispatched to `EmailSender.deliver(...)`. Similarly, the `SmsSender` object uses the overridden `normalize(...)`. Calling a concrete method of the superclass **does not eliminate polymorphism** for the steps overridden by subclasses.

In the example, `SmsSender.normalize` calls `super.normalize(message)` to get the leading-and-trailing whitespace trimming logic, and then collapses internal whitespace sequences. `super` is the way to directly reuse the superclass implementation when overriding; it does not create a new superclass object.

## 4. Distinguishing Inheritance, Overriding, and Calling `super`

If a subclass does not override an inheritable concrete method, it reuses that implementation as is. Override only when the behavior needs variation; use `@Override` so the compiler verifies the signature. When part of the original behavior needs to be preserved, the subclass can call `super.method(...)`, like `SmsSender.normalize` in the example.

Overriding must preserve a compatible signature and must not narrow access privileges. A `private` method is not a hook for overriding, a `static` method undergoes hiding rather than dynamic dispatch, and a `final` method forbids overriding. The dedicated lesson on modifiers goes deeper into the validity matrix; this lesson focuses on organizing shared steps and variation points.

## 5. Relationship with State and Constructors

Concrete methods can read superclass state and call other hooks; the superclass constructor establishes that state before the shared workflow is called. Avoid calling overridable hooks inside a constructor, because the subclass may not have finished initializing its own fields yet. Rules on constructors, access modifiers, and initialization order are explained separately in the lesson on constructors.

## 6. How to Choose Between Concrete, Abstract, and Final Methods?

| Requirement | Suggested Declaration | Reason |
| --- | --- | --- |
| Every subclass must have the same processing step | `final` concrete method | Preserves the shared rule properly and prevents unintended overriding. |
| Sensible default behavior exists, occasionally needing variation | Concrete method allowing override | Can be used as is or customized, including calling `super`. |
| No default implementation is valid for all subclasses | `abstract` method | Forces concrete subclasses to provide an implementation. |
| Detail used only by the superclass itself | `private` concrete method | Encapsulation, reducing the inherited API surface. |
| Shared utility method for subclasses | `protected` concrete method, consider `final` | Reuses logic without forcing algorithm duplication. |

Practical selection process: first identify which steps are **identical** and which steps **actually vary** across subclasses; put the identical parts into concrete methods, and represent the parts that must differ with `abstract` methods. Only allow overriding at designed extension points.

## 7. When Should You Use an Abstract Class to Share Code?

It is suitable when subclasses have a natural **is-a** relationship and share part of an algorithm or state—for example, kinds of processors, file readers, or notification senders that have a similar lifecycle and baseline rules. It is especially useful when you must protect the **order of steps** with the Template Method pattern while still allowing certain steps to be customized.

However, Java inheritance allows only one direct superclass (`extends` a single class). If the goal is merely to reuse a few independent utilities, creating an entire hierarchy is not necessarily warranted:

- **Composition / dependency injection:** move the reusable behavior into a service object that other classes call. This approach is flexible if multiple unrelated object types still need that logic.
- **Interfaces with `default method`:** appropriate when multiple classes need to share minor default behavior without needing instance state or constructors from the same superclass. A `default method` does not replace every role of an abstract class.
- **`static` utility methods:** appropriate for pure transformations that require neither state nor polymorphism.

Prefer the simplest structure that accurately expresses the domain relationship; do not create a base class just because two classes happen to have a few similar lines of code.

## 8. Common Mistakes and How to Self-Check

1. **Confusing an “abstract class” with “all abstract methods”.** An abstract class is allowed to have many concrete methods, or even no abstract methods at all.
2. **Writing a body for an `abstract` method.** A declaration like `protected abstract void execute();` must not include `{ ... }`. To provide default logic, remove `abstract` and supply a body.
3. **Defining an abstract method in a regular class.** A class containing an `abstract` method must be marked `abstract`; a concrete subclass must implement any remaining abstract methods.
4. **Mistakenly overriding `private`/`final`/`static` methods.** `private` cannot be overridden, `final` forbids overriding, and `static` only performs hiding. Use `@Override` and compile to catch errors.
5. **Duplicating validation in every subclass.** This easily creates inconsistencies. Place validation in a `final` skeleton method so subclasses only handle their specialized part.
6. **Changing shared logic in an override without understanding the contract.** If extension is permitted, override only the right hook; call `super` when the default part must be preserved.
7. **Calling an overridable hook from a constructor.** Move that call to a method executed after the object is completely initialized.
8. **Abusing inheritance to share a few functions.** Consider composition or utility methods to reduce dependency on a fixed superclass.

To verify the example, try adding a `PushSender` class extending `NotificationSender` that implements only `deliver(...)`: the new class automatically receives all input validation, default normalization, and logging. Next, try calling `send("  ", "test")`: the program throws `IllegalArgumentException` **before** logging and calling `deliver`. These two tests confirm that the shared code is used consistently across subclasses.

**Remember:** concrete methods in an abstract class create shared inherited behavior; abstract methods specify what subclasses must supply; `final` methods protect steps or algorithms that must not be changed. Combining these three purposefully enables both code reuse and customization in the right places.
