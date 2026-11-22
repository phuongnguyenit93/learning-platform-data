# Decorator: Adding Behavior Through the Same Interface

Decorator is a structural design pattern used to add responsibilities to an object by wrapping it inside another object that has the same interface. The client continues to call the same methods as before, while the decorator can add behavior before or after forwarding the call to the wrapped object.

This pattern is useful when optional features need to be combined at runtime, such as sending notifications across multiple channels, adding logging, measuring time, encrypting data, or caching. In Java, Decorator is typically implemented using composition: a decorator holds a reference to the object to be wrapped and implements the same interface as it.

## 1. The Problem Decorator Solves

Suppose an application has a `Notifier` interface and an email-sending implementation. Later, requirements arise to add SMS delivery, an importance prefix, logging, and processing-time measurement. You could create a subclass for each combination, but the number of classes would grow quickly:

- Standard email
- Email with SMS
- Email with prefix
- Email with SMS and prefix
- New combinations when adding logging or retry

This is a class explosion caused by using inheritance to represent every combination of behaviors. Decorator allows independent additions to be combined by wrapping an object multiple times. Each decorator is responsible for one piece of behavior, and decorators can be assembled when initializing the application.

## 2. Structure and Roles

A common Decorator design consists of four roles:

1. **Component**: the common interface that the client uses.
2. **Concrete Component**: the base object that provides the initial behavior.
3. **Base Decorator**: also implements Component, holds a reference to another Component, and forwards calls.
4. **Concrete Decorator**: extends the base decorator, adds behavior and then forwards the call, or adds processing before/after the call.

Relationship diagram:

~~~mermaid
classDiagram
    class Notifier {
        <<interface>>
        +send(message)
    }
    class EmailNotifier {
        +send(message)
    }
    class NotifierDecorator {
        #delegate
        +send(message)
    }
    class PrefixDecorator {
        +send(message)
    }
    class SmsDecorator {
        +send(message)
    }
    Notifier <|.. EmailNotifier
    Notifier <|.. NotifierDecorator
    NotifierDecorator <|-- PrefixDecorator
    NotifierDecorator <|-- SmsDecorator
    NotifierDecorator o--> Notifier : delegates to
~~~

The key point is that both the original object and decorators can be assigned to a variable of the Component type. Therefore, the client does not need to know whether it is calling the original object directly or a chain of decorators.

## 3. Runnable Java Example

The following example uses email as the base behavior. `PrefixDecorator` adds a prefix to the message, while `SmsDecorator` sends an additional SMS notification. Both decorators implement the same `Notifier` interface.

Save as `DecoratorDemo.java`:

~~~java
import java.util.Objects;

interface Notifier {
    void send(String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}

abstract class NotifierDecorator implements Notifier {
    protected final Notifier delegate;

    protected NotifierDecorator(Notifier delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }
}

final class PrefixDecorator extends NotifierDecorator {
    PrefixDecorator(Notifier delegate) {
        super(delegate);
    }

    @Override
    public void send(String message) {
        delegate.send("[IMPORTANT] " + message);
    }
}

final class SmsDecorator extends NotifierDecorator {
    SmsDecorator(Notifier delegate) {
        super(delegate);
    }

    @Override
    public void send(String message) {
        delegate.send(message);
        System.out.println("SMS: " + message);
    }
}

public class DecoratorDemo {
    public static void main(String[] args) {
        Notifier notifier =
                new PrefixDecorator(new SmsDecorator(new EmailNotifier()));

        notifier.send("Deployment complete");
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac DecoratorDemo.java
java DecoratorDemo
~~~

Stdout output:

~~~text
Email: [IMPORTANT] Deployment complete
SMS: [IMPORTANT] Deployment complete
~~~

The call flow proceeds as follows:

1. The client calls `notifier.send("Deployment complete")`.
2. `PrefixDecorator` adds the `[IMPORTANT] ` prefix and forwards the new message to `SmsDecorator`.
3. `SmsDecorator` forwards the updated message to `EmailNotifier`, so the email is sent first.
4. After the inner call completes, `SmsDecorator` sends an additional SMS with the exact message it received.

In the example, the wrapping order is `PrefixDecorator(SmsDecorator(EmailNotifier))`. Changing the wrapping order can alter the behavior because the outermost decorator receives the call first. Clearly determine whether each class needs to modify data, perform an additional action, or process after the delegate completes.

## 4. How to Implement a Decorator Properly

A decorator should preserve the Component's contract and forward the methods it does not need to change. For an interface with multiple methods, the base decorator typically implements all methods by calling the corresponding delegate method; subclasses only override the methods that need to be extended.

Some practical guidelines:

- **Same interface:** both the original component and the decorator must be usable through the same Component type.
- **Clear delegation:** the decorator holds a delegate object and calls it at the appropriate time.
- **Single additional responsibility:** each decorator should do one thing with a clear name and purpose, such as adding logging or encryption.
- **Allow composition:** callers can wrap a component with multiple decorators according to runtime configuration.
- **Preserve the contract:** if a method is expected to return a value, throw a specific exception type, or guarantee a postcondition, the decorator must uphold those commitments.
- **Guard against null and cycles:** the constructor should validate the delegate if null is not a valid value; avoid configuring a decorator to reference itself.
- **Preserve order and error handling:** decide clearly whether the decorator executes its behavior before or after the delegate, and what happens if the delegate throws an exception.

A base decorator is optional. For a small interface or one with only a single method, each decorator can implement the interface directly. For a large interface, a base decorator helps reduce boilerplate code when forwarding methods.

## 5. Combining Decorators and Runtime Configuration

A decorator chain can be built conditionally without changing the variable type that the client uses:

~~~java
Notifier notifier = new EmailNotifier();

if (sendSms) {
    notifier = new SmsDecorator(notifier);
}
if (markImportant) {
    notifier = new PrefixDecorator(notifier);
}

notifier.send("Deployment complete");
~~~

This snippet is a partial illustrative example; the variables `sendSms` and `markImportant` must be declared in the enclosing context. Both before and after wrapping, the reference type remains `Notifier`. The client only calls `send`, while configuration determines which behaviors are added.

When the number of decorators grows larger, chain construction should be centralized into a factory or configuration function so that initialization rules are easy to test. Avoid letting multiple places in the application assemble different chains on their own if the decorator order matters to business logic.

## 6. How Does Decorator Differ from Regular Inheritance?

Inheritance extends behavior by creating subclasses with a fixed type relationship to a parent class. Decorator extends behavior by holding another object and forwarding calls. A single decorator can wrap multiple types of Concrete Components as long as they all implement Component.

| Criterion | Inheritance | Decorator |
|---|---|---|
| How behavior is added | Define a subclass | Wrap an object and delegate |
| Combining features | Often requires subclasses for combinations | Can stack multiple decorators |
| When decided | Usually tied to the compiled class type | Can be decided at runtime |
| Primary dependency | Relationship with the parent class | Interface and delegate |
| Limitation | Can create many subclasses; hard to combine independently | Wrapping chains can become complex if not clearly managed |

Decorator does not eliminate inheritance completely. In the example, the concrete decorators extend `NotifierDecorator` to reuse the delegate storage and forwarding mechanism. The important part is that the extended behavior is applied to a delegate object via composition, rather than relying solely on inheriting from a base implementation class.

## 7. Comparison with Similar Design Patterns

- **Adapter:** converts one interface into another so that two incompatible components can work together. Decorator preserves the original interface to add responsibilities.
- **Proxy:** also holds a reference to an object and forwards calls, but its primary goal is typically access control, creating objects on demand, remote distribution, or lifecycle management.
- **Chain of Responsibility:** passes a request through a chain of handlers so that each handler decides whether to process or forward it. Decorator typically wraps a component to extend its behavior, and wrappers can perform behavior both before and after the delegate.
- **Strategy:** changes the algorithm used through an interface. Decorator focuses on composing behavior around a component; the two patterns can be used together.

Naming does not determine the design pattern; look at the actual intent and control flow of the code. A wrapper may look like a Decorator, yet in purpose be a Proxy or an Adapter.

## 8. Examples in the Java Library

The Java standard library uses object wrapping across many APIs. For example, `BufferedInputStream` wraps an `InputStream` to add buffering, while `DataInputStream` adds the capability to read primitive data. They are still used through their respective stream types, so multiple wrappers can be combined:

~~~java
InputStream input = new BufferedInputStream(
        new FileInputStream("data.bin"));
~~~

The example above only illustrates the wrapping structure; real code needs to import the classes and handle or declare `IOException`. When combining streams, follow resource-closing rules, typically using try-with-resources. Closing the outermost stream generally closes the inner streams through the delegation mechanism.

## 9. Common Mistakes

- **Failing to call the delegate:** the decorator accidentally replaces the entire original behavior, even though the goal is only to add part of it. Decide clearly whether a call is intentionally intercepted or needs to be forwarded.
- **Adding behavior at the wrong time:** whether behavior runs before or after the delegate affects the result, especially if the delegate can throw an exception.
- **Reversing decorator order:** preprocessing, encryption, logging, or data transformation may not be commutative. Test the exact wrapping order configured in the application.
- **Altering the contract:** the decorator returns invalid results, swallows exceptions, or mutates state in a way the caller does not expect.
- **Creating overly deep chains:** many layers of wrapping make stack traces and debugging hard to read. Name each decorator clearly and centralize chain configuration in one place.
- **Confusing Decorator with Adapter:** if you have to convert to a different interface, Adapter may be the right choice.
- **Holding unsafe shared state:** if multiple threads use the same decorator, state fields may need to be immutable, synchronized, or designed to be thread-safe.

## 10. How to Test and Decide When to Use It

Test a decorator in isolation by providing a fake or mock component to verify that the delegate is called with the expected arguments and invocation count. For decorators that add behavior after the delegate, test both the ordering and the case where the delegate throws an exception. Then test the complete chain to verify that the wrapping order produces the correct result.

Decorator is suitable when you need to add optional, independent, composable features while preserving the interface for the client. If the new behavior completely changes the API's purpose, requires converting interfaces, or orchestrates a multi-step workflow, consider Adapter, Strategy, or Chain of Responsibility.

A helpful design question to ask is: "Can I wrap this component in another object with the same interface, add a clear responsibility, and still preserve the component's contract?" If yes, Decorator is a good candidate.
