# `static` Methods in Interfaces Since Java 8

Since **Java 8**, an interface can declare a `static` method with a body. This method belongs to the interface itself, making it suitable for operations associated with the type, such as input validation, data normalization, or creating an implementation. It does not describe behavior that needs to be selected per object.

## 1. Distinguishing the Three Types of Methods

| Type | Role | Typical call | Can it be overridden as instance behavior? |
|---|---|---|---|
| Abstract instance method | Declares what an object must do | `sender.send(message)` | Yes; a concrete class must provide an appropriate implementation |
| `default` instance method | Provides default behavior for an object | `sender.description()` | Yes |
| `static` method | Provides an operation belonging to the interface | `MessageSender.normalize(text)` | No |

For example, `send` is the behavior of each sender, whereas `normalize` is a string-processing rule that can be shared without needing a `MessageSender` object.

## 2. Syntax and Key Rules

~~~java
interface MessageSender {
    void send(String message);

    static String normalize(String message) {
        if (message == null) {
            return "";
        }
        return message.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

A `static` method in an interface must have a body. If no access modifier is specified, it is `public`; you can explicitly write `public static` to emphasize the public API.

A method cannot simultaneously be `static` and `abstract` or `default`. A `static` method does not have `this` representing the current instance, so it cannot directly call an instance method without an object receiving the call.

A `static` method of an interface is called using the name of the interface that declared it. This rule differs from calling an instance method through an object; the next lesson goes into detail on how to write the call correctly.

## 3. Complete Example

Save the following code as `Main.java`. This example is compatible with Java 8.

~~~java
interface MessageSender {
    void send(String message);

    static String normalize(String message) {
        if (message == null) {
            return "";
        }
        return message.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("Sent: " + MessageSender.normalize(message));
    }
}

public class Main {
    public static void main(String[] args) {
        MessageSender sender = new ConsoleSender();
        sender.send("  hello Java  ");
        System.out.println("Normalized: " + MessageSender.normalize(" java "));
    }
}
~~~

Compile and run on JDK 9 or later:

~~~bash
javac -encoding UTF-8 --release 8 Main.java
java Main
~~~

Stdout:

~~~text
Sent: HELLO JAVA
Normalized: JAVA
~~~

The call `sender.send(...)` is resolved based on the actual object and invokes the implementation of `ConsoleSender`. The call `MessageSender.normalize(...)` is determined by the interface written before the dot; it does not require creating a sender and does not participate in instance polymorphism.

## 4. Static Methods in Generic Interfaces

A static method is not tied to a specific `Box<T>` object, so it cannot directly use the interface's type parameter `T`. If the method itself needs to be generic, declare its own type parameter:

~~~java
interface Box<T> {
    T get();

    static <U> U identity(U value) {
        return value;
    }
}
~~~

`Box.identity("Java")` infers `U` as `String`, while `Box.identity(42)` infers `U` as `Integer`. The type parameter `U` belongs to the method; it does not depend on `T` of a `Box<T>` instance.

## 5. When to Use Them?

Consider `static` when an operation makes sense directly on the interface and does not require object state, such as data validation or a factory method. If each implementation needs to provide its own behavior, use an abstract instance method; if you need default behavior that can vary per object, consider `default`.

Do not mechanically put every utility into an interface. If the logic does not belong to the interface's contract, a utility class can express the responsibility more clearly.

**Self-Check**

- Must a `static` method in an interface have a body? **Yes.**
- Can it be called through an instance variable to receive polymorphic dispatch? **No.**
- If a static method needs to be generic on its own, do you use the interface's type parameter or declare a method type parameter? **Declare a method type parameter.**
