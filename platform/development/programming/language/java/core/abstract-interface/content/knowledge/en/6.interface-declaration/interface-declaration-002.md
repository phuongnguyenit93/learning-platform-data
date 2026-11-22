# Interfaces Are Reference Types and Implicitly Abstract in Java

## 1. Reference Type and Actual Object

An interface name is a **reference type**. It can appear in variable declarations, parameters, return types, fields, and generic arguments, just like other reference types.

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("Sent: " + message);
    }

    public void clearHistory() {
        System.out.println("History cleared");
    }
}

public class Main {
    public static void main(String[] args) {
        MessageSender sender = new ConsoleSender();
        sender.send("hello");
        System.out.println(sender instanceof MessageSender);
    }
}
```

Output:

```text
Sent: hello
true
```

There are three things to distinguish:

- **The declared type of the variable** is `MessageSender`, so the compiler only allows calling members accessible through that type.
- **The runtime type of the object** is `ConsoleSender`, so an instance method call is dispatched to the object's appropriate implementation.
- The `implements` relationship allows assigning a `ConsoleSender` to a `MessageSender` variable; the assignment does not create a separate interface object.

Even though the actual object has the `clearHistory()` method, the expression `sender.clearHistory()` still does not compile because that method does not belong to the API declared by the `MessageSender` type.

## 2. Why Are Interfaces Implicitly Abstract?

An interface declaration is inherently abstract. The following two forms have the same meaning regarding abstractness:

```java
interface Task {
    void execute();
}

abstract interface LegacyTask {
    void execute();
}
```

The common form is `interface Task`; the `abstract` keyword in an interface declaration is redundant. An instance cannot be created directly with `new Task()` because an interface has no constructor and does not define a concrete implementation for every behavior.

A concrete class implementing `Task` must provide valid implementations for the missing abstract methods, or inherit a suitable implementation. A class that is still missing methods can be declared `abstract`.

**Do not infer that every method in an interface is abstract.** For example, modern Java allows `default`, `static`, and `private` methods to have a body. A regular instance method declared without a body in an interface has `public abstract` semantics even if those two modifiers are not written.

## 3. Anonymous Classes and Lambdas Are Not Interface Constructors

Java allows creating an implementing object through an anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
task.run();
```

The object above belongs to an anonymous class created by the syntax; there is no direct instance of `Runnable`. For a functional interface, a lambda can also provide an implementation:

```java
Runnable task = () -> System.out.println("running");
task.run();
```

A lambda applies only when the interface satisfies the functional interface condition: having one qualifying abstract method after considering Java's rules. `default`, `static`, and `private` methods do not count as additional abstract methods.

## 4. Mistakes to Recognize

| Usage | Why |
| --- | --- |
| `new Task()` | Cannot instantiate an interface directly. |
| Concrete class omitting an abstract method | Does not fulfill the type contract. |
| Implementation with the same name but different parameters | That may be an overload, not an override. |
| Calling a class-specific method through an interface variable | The compiler checks against the declared type of the expression. |
| Assuming `default` means every interface method has a body | `default` only applies to the kind of method declared with that syntax. |

**Self-check:** Given `MessageSender sender = new ConsoleSender()`, which type determines the methods that can be called at compile time? `MessageSender`. Which type provides the implementation that runs for `send`? The actual object `ConsoleSender`.
