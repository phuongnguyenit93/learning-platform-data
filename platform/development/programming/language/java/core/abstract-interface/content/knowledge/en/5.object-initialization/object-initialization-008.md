# A Factory Creating a Concrete Class but Returning an Abstract Type in Java

## Objectives

Understand why a factory can call the constructor of a concrete class while declaring its return type as an `interface` or `abstract class`; distinguish between the reference type and the runtime object type; and write, use, test, and extend a simple factory yourself in Java 17+.

## 1. The Essence: Concrete Object, Abstract Contract

In Java, an `interface` defines a set of behaviors that implementing classes must provide. An `abstract class` can define shared behavior, state, and abstract methods for subclasses. You cannot directly instantiate an interface or abstract class with `new`; you can only create objects of a **concrete class**.

An object of a class that implements an interface or inherits from an abstract class can be referenced using the **corresponding abstract type**:

```java
MessageSender sender = MessageSenderFactory.create("email");
sender.send("an@example.com", "Xin chào");
```

The snippet above illustrates usage; the full definitions of the classes are in Section 3. The factory can call `new EmailSender()` internally, but exposes the signature `static MessageSender create(String channel)`. After assignment, `sender` is a **variable of type `MessageSender`** holding a reference to an **actual object of type `EmailSender`**. The object is not transformed into an interface.

This is valid upcasting: Java allows using a subclass object wherever a superclass/interface it satisfies is required. When calling `sender.send(...)`, Java selects the implementation of the actual class at runtime (**dynamic dispatch**). Meanwhile, the compiler uses the declared type `MessageSender` to check which methods the caller's code is allowed to invoke.

For example, if `EmailSender` has its own additional method `configureSmtp()` that `MessageSender` does not have, `sender.configureSmtp()` fails to compile. Hiding class-specific APIs helps callers depend on the shared contract.

## 2. Why Use a Factory?

If every call site calls `new EmailSender()` or `new SmsSender()` directly, the choice of implementation becomes scattered across usage sites. A factory centralizes the object creation decision:

1. The caller requests a capability, such as `create("sms")`.
2. The factory checks the input and selects the corresponding concrete class.
3. The factory calls `new SmsSender()` to instantiate the object.
4. The factory returns the reference typed as `MessageSender`.
5. The caller uses `send` without needing to know the constructor or the class that was just selected.

A factory does not eliminate the existence of concrete classes: **the factory itself still knows** the classes it instantiates. The benefit is that business code does not need to put that selection logic everywhere. If Email is replaced with another implementation that still satisfies the contract, the parts that depend only on `MessageSender` usually remain unchanged.

## 3. A Runnable Java 17+ Program

Create a file named `Main.java` with the following content:

```java
import java.util.Locale;

public class Main {
    interface MessageSender {
        void send(String recipient, String message);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String recipient, String message) {
            System.out.println("Email -> " + recipient + ": " + message);
        }
    }

    static final class SmsSender implements MessageSender {
        @Override
        public void send(String recipient, String message) {
            System.out.println("SMS -> " + recipient + ": " + message);
        }
    }

    static final class MessageSenderFactory {
        private MessageSenderFactory() {
            // No need to create an instance of this utility factory class.
        }

        static MessageSender create(String channel) {
            if (channel == null) {
                throw new IllegalArgumentException("Kênh không được null");
            }

            return switch (channel.trim().toLowerCase(Locale.ROOT)) {
                case "email" -> new EmailSender();
                case "sms" -> new SmsSender();
                default -> throw new IllegalArgumentException(
                    "Kênh không hỗ trợ: " + channel
                );
            };
        }
    }

    public static void main(String[] args) {
        MessageSender email = MessageSenderFactory.create("email");
        MessageSender sms = MessageSenderFactory.create("sms");

        email.send("an@example.com", "Xin chào");
        sms.send("0900000000", "Xin chào");

        System.out.println("Lớp thực tế: " + email.getClass().getSimpleName());
    }
}
```

Run with JDK 17 or later, from the directory containing the file:

```bash
javac Main.java
java Main
```

Stdout:

```text
Email -> an@example.com: Xin chào
SMS -> 0900000000: Xin chào
Lớp thực tế: EmailSender
```

**Reading the code by type relationships:**

- `MessageSender` is the caller's contract: it only requires `send(String, String)`.
- `EmailSender` and `SmsSender` are concrete classes that can be instantiated with `new`. Each class `implements MessageSender` and overrides `send`.
- `MessageSenderFactory.create` declares its return type as `MessageSender`. Each `switch` branch returns an object of a concrete class. Both branches are valid thanks to the `implements` relationship.
- `channel.trim().toLowerCase(Locale.ROOT)` allows `" EMAIL "` to match `"email"` without depending on the host machine's locale. `null` and unsupported channels produce a clear error.
- In `main`, both variables are declared as `MessageSender`, yet `email.send` runs the Email implementation and `sms.send` runs the SMS implementation. `getClass().getSimpleName()` is used solely to observe the runtime class.
- Each successful call to the **specific factory in this example** executes `new`, thereby creating a new object. That is not a general guarantee for every factory.

Try changing `create("email")` to `create("sms")` on the line that creates the `email` variable. You do not need to modify the `email.send(...)` statement; only the resulting behavior differs. If you change it to `create("push")`, the factory throws `IllegalArgumentException` with the message `Kênh không hỗ trợ: push`.

## 4. A Factory Can Also Return an Abstract Class

Not only `interface`: a factory can return an `abstract class` when multiple subclasses share part of an algorithm or state. The following standalone example is placed in the file `MainAbstract.java`:

```java
public class MainAbstract {
    abstract static class Greeting {
        final void greet(String name) {
            System.out.print("Xin chào, ");
            sayName(name);
        }

        protected abstract void sayName(String name);
    }

    static final class FormalGreeting extends Greeting {
        @Override
        protected void sayName(String name) {
            System.out.println("anh/chị " + name + "!");
        }
    }

    static class GreetingFactory {
        static Greeting create() {
            return new FormalGreeting();
        }
    }

    public static void main(String[] args) {
        Greeting greeting = GreetingFactory.create();
        greeting.greet("An");
    }
}
```

Run `javac MainAbstract.java` and then `java MainAbstract`. Stdout:

```text
Xin chào, anh/chị An!
```

Here, `Greeting` cannot be instantiated directly, but `new FormalGreeting()` is completely valid. `GreetingFactory.create()` returns a `Greeting` referencing a `FormalGreeting` object. The `greet` method is the shared part of the algorithm; when calling `sayName`, Java executes the subclass implementation. If you only need a behavioral contract, an interface is usually chosen; if you need to inherit truly shared implementation/state, an abstract class may be more suitable.

## 5. Comparing Return Types

| Approach | What does the caller know? | Consequence |
| --- | --- | --- |
| `EmailSender e = new EmailSender();` | Knows the concrete class and constructor. | Directly tied to EmailSender. |
| `EmailSender e = Factory.createEmail();` | Knows the concrete class even though creation logic is in the factory. | Can still depend on EmailSender's specific methods. |
| `MessageSender s = Factory.create("email");` | Knows the `MessageSender` contract and the selection request. | Easy to replace the implementation class as long as the contract is kept. |
| `MessageSender s = new EmailSender();` | Uses the contract but still chooses the concrete class itself. | Valid assignment, yet the usage site still depends on the constructor. |

An abstract return type makes the API clearer: “You need an object that knows how to send messages”, rather than requiring the caller to use details specific to Email or SMS. This is one way of applying interface-based programming, aligning with polymorphism and the goal of reducing coupling.

However, an interface does not by itself guarantee immutability, thread safety, singleton behavior, or lazy initialization. Those properties depend on the implementation and the lifecycle conventions that the factory commits to.

## 6. Designing a Good Factory

**A right-sized contract.** Put inside `MessageSender` the exact behavior that needs to be used in common. If you force every implementation to implement many meaningless methods, the interface becomes too broad and hard to extend.

**Clear parameters.** In the example, the input is the string `"email"` or `"sms"`. For a finite set of choices in a real application, an `enum` can help avoid mistyped strings. However, input from HTTP, config, or files still needs to be validated at the boundary with meaningful errors reported. A factory should not silently return `null` for any unsupported choice if the contract does not clearly state that.

**Intentional object lifecycle.** Some factories always create new objects, while others return cached objects or shared instances. If an object has mutable state or holds resources, consider access contention, thread safety, and resource-closing responsibility. Declaring an abstract type does not replace lifecycle design.

**Choose static or instance based on needs.** `static create` is adequate for simple logic. If creating a sender requires configuration, an HTTP client, or other dependencies, an injected factory instance can be used. The core formula remains: instantiate a concrete class and expose an abstract type.

**Separate implementation selection from business logic.** Business code that receives `MessageSender` through a constructor or parameter will be easy to test using a fake implementation that records `send` calls. Test the factory separately to verify that `"email"` creates `EmailSender`, `"sms"` creates `SmsSender`, and invalid inputs are handled properly. If every business method calls a static factory itself, then the business code itself remains coupled to that factory, even though the return type is already an interface.

**Extend when needed.** To add `PushSender`, implement `MessageSender` and then update the selection logic in the factory. In large systems, a registry or dependency injection can replace `switch`; such mechanisms are not necessarily needed when there are only a few stable choices.

## 7. Distinguishing From Other Factory Concepts

- **Constructor** `new EmailSender()` directly instantiates a concrete class.
- **Simple factory / factory function**, like `MessageSenderFactory.create`, groups object creation and selection logic together. It is a common way of organizing code, not necessarily a separate GoF design pattern.
- **Static factory method** is a static method that returns/provides an instance. It may create a new instance, use a cache, or return a singleton according to its contract.
- **Factory Method pattern (GoF)** defines a product-creation method in a superclass, letting subclasses decide the type of product created. One cannot conclude that an arbitrary `static create()` method is the Factory Method pattern.
- **Abstract Factory pattern (GoF)** represents an interface for creating *a family of related products* without depending on concrete classes. It addresses a broader scope than the example of selecting a single sender.

The title “A Factory Creating a Concrete Class but Returning an Abstract Type” expresses the principle of **separating the consumer API from instantiation details**. This principle can be applied across many factory variants without needing to apply an entire complex pattern to a small problem.

## 8. Common Mistakes

1. **Trying to use `new` on an interface or abstract class:** `new MessageSender()` and `new Greeting()` are invalid. Instantiate a concrete class that implements/extends the appropriate contract.
2. **Assuming an abstract variable loses its actual type:** the object still has a runtime class such as `EmailSender`; method calls are dynamically dispatched.
3. **Calling a subclass-specific API through the interface:** only methods belonging to the shared contract can be called directly. Do not downcast just to bypass the API, unless required and accompanied by a safe type check.
4. **Invalid casting:** `(EmailSender) MessageSenderFactory.create("sms")` may compile, but at runtime it throws `ClassCastException`. If both capabilities are needed, prefer designing an appropriate shared interface.
5. **Leaving unknown/`null` channel cases undefined:** leads to vague errors or a `NullPointerException` far from the source. Check and report failures at the factory.
6. **Equating a static factory with a singleton:** a static method can still call `new` every time; two calls may return two different objects.
7. **Overusing `instanceof` at call sites:** if business code keeps branching on Email/SMS to choose behavior, review the contract and how polymorphism is used.
8. **Unnecessarily complex factories:** only add a factory class when selection, configuration, lifecycle control, or dependency decoupling truly makes the code easier to understand.

## 9. Practice Questions

1. Why is `MessageSender sender = MessageSenderFactory.create("email")` valid even though you cannot call `new MessageSender()`?
2. When changing the channel to `"sms"`, what happens at the `sender.send(...)` statement, and why does the variable type not need to change?
3. Do two calls to `create("email")` in the **current example** return the same object? If you want caching, which part of the implementation must change?
4. If you add a class `PushSender implements MessageSender`, what needs to be added in the factory, and does caller code that only uses `send` have to be modified?
5. If you want to test a service that calls `sender.send(...)` without sending real messages, what type of dependency would you pass into the service?

Remember: **a factory can know and use `new` on a concrete class, but declare an interface/abstract class return type so callers depend on the shared contract.** The compiler checks operations against the declared type; the JVM executes the overridden method according to the object's actual class.
