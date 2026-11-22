# Interfaces Nested in a Class and Interfaces Nested in an Interface

This lesson explains how to declare, access, and use an interface placed inside a class or inside another interface in Java. Both cases share the same core rule: a member interface is always a `static` type, so it does not require an instance of the enclosing type.

## 1. Concepts

A **nested interface** is an interface declared inside another type. When an interface is declared directly as a member of a class or interface, it is called a **member interface**.

- **Interface nested in a class:** groups a small contract with the related class, such as a callback serving only a specific API.
- **Interface nested in an interface:** groups a supporting type with the API contract it describes, such as `Listener` inside `EventSource`.
- A nested interface is still an independent type. It can be implemented by another class, used as a parameter type or return type, and can be a lambda target type if it has only one abstract method.

## 2. Java Language Rules

### Interface Nested in a Class

```java
class TaskRunner {
    public interface CompletionCallback {
        void onComplete(String result);
    }
}
```

- `CompletionCallback` is a member interface of `TaskRunner` and is **implicitly `static`**, even though the `static` keyword does not appear. Writing `public static interface CompletionCallback` is also valid, but `static` is redundant.
- Within a class, a nested interface can use `public`, `protected`, `private`, or package-private access. Choose the access level based on where the contract needs to be used.
- From outside the enclosing class, the type name is typically written in full as `TaskRunner.CompletionCallback`. Within a scope where the member name is visible, the short name `CompletionCallback` can be used.
- Because the nested interface is `static`, it does not hold an implicit reference to a `TaskRunner` instance. You do not need to create a `TaskRunner` to access this type.
- Declaring an interface inside a class **does not automatically make the enclosing class implement that interface**. If implementation is needed, `implements TaskRunner.CompletionCallback` must be declared on an appropriate class.

### Interface Nested in an Interface

```java
interface EventSource {
    void start();

    interface Listener {
        void onEvent(String event);
    }
}
```

- `Listener` is implicitly `public static`. You can explicitly write `public static interface Listener`, but these two keywords are redundant in that context.
- From outside, the type name is `EventSource.Listener`. The nested type is still subject to the accessibility of `EventSource`: if the enclosing interface cannot be accessed from somewhere, the nested type name cannot be used from there either.
- Regular methods declared in an interface are implicitly `public abstract`, unless declared in another form permitted by Java such as `default`, `static`, or `private` (private methods in interfaces have been supported since Java 9).
- Do not declare `private` or `protected` for a member type in an interface; an interface's member types are always public and static according to the language rules.

### Common Points to Remember

1. A member interface is always `static`; do not use object-creation syntax like `outer.new NestedInterface()`.
2. An interface cannot be instantiated directly with `new`. Provide an appropriate implementing class, anonymous class, or lambda.
3. Nested type names are separated by dots, for example `TaskRunner.CompletionCallback` and `EventSource.Listener`.
4. If an interface has only one abstract method, it is a functional interface and can be used as a lambda target type. `default` and `static` methods do not increase the number of abstract methods.

## 3. Runnable Example with Java 17+

Save the entire code snippet below into the file `NestedInterfacesDemo.java`. The example has an interface nested in the `NestedInterfacesDemo` class and an interface nested in the `MessageSource` interface.

```java
public class NestedInterfacesDemo {
    // Member interface in a class: static is implicit.
    public interface CompletionCallback {
        void onComplete(String message);
    }

    public static void run(CompletionCallback callback) {
        callback.onComplete("job done");
    }

    public static void main(String[] args) {
        CompletionCallback callback =
                message -> System.out.println("callback: " + message);
        run(callback);

        // Listener is a member interface of MessageSource.
        MessageSource.Listener listener =
                message -> System.out.println("event: " + message);

        MessageSource source = (target, message) -> target.onMessage(message);
        source.publish(listener, "ready");
    }
}

interface MessageSource {
    void publish(Listener listener, String message);

    // Inside an interface, Listener is implicitly public static.
    interface Listener {
        void onMessage(String message);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac NestedInterfacesDemo.java
java NestedInterfacesDemo
```

Exact stdout output:

```text
callback: job done
event: ready
```

In the example, `CompletionCallback` is the parameter type for `run`. The lambda provides the implementation of `onComplete`. Similarly, `MessageSource.Listener` describes how to receive messages; the second lambda implements the listener, while the lambda for `MessageSource` provides the behavior of the `publish` method.

## 4. Accessing and Implementing a Nested Interface

### Using the Full Type Name

```java
TaskRunner.CompletionCallback callback = result ->
        System.out.println(result);

EventSource.Listener listener = event ->
        System.out.println("Nhận sự kiện: " + event);
```

This is the style commonly used when referencing from another class. The nested type is still accessed through the enclosing type, not through an instance of the enclosing type.

### Using an Explicit Implementing Class

```java
class ConsoleListener implements EventSource.Listener {
    @Override
    public void onEvent(String event) {
        System.out.println("Nhận sự kiện: " + event);
    }
}
```

`ConsoleListener` implements the `EventSource.Listener` contract. Because `onEvent` is a `public` method of the interface, the implementing method must also have `public` access; reducing the access level will cause a compile error.

## 5. When to Nest an Interface?

- Place an interface inside a class when the contract is tightly coupled to that class and does not need to become a standalone concept in the API. For example: a dedicated callback for a task processor.
- Place an interface inside an interface when the supporting type makes sense as part of the public contract. For example: `EventSource.Listener` describes how to receive events emitted by the event source.
- Keep the interface at the top level when multiple classes or multiple packages need to use it independently. This keeps type names shorter and avoids unnecessary dependency on the enclosing type.
- Keep the nesting depth reasonable. Names like `A.B.C.Listener` can make the API hard to read if nesting provides no clear benefit.

## 6. Common Mistakes

| Mistake or Misconception | Correct Understanding |
| --- | --- |
| Writing `new TaskRunner.CompletionCallback()` to create an interface | An interface cannot be instantiated directly. Use a lambda if it is a functional interface, or write an implementing class/anonymous class. |
| Assuming `new TaskRunner()` is needed to use `TaskRunner.CompletionCallback` | A member interface is `static`, so no instance of the enclosing class is needed. |
| Thinking the enclosing class automatically implements the nested interface | Declaring a nested type does not create an `implements` relationship. Declare the implementation explicitly on the required class. |
| Forgetting the enclosing name when using the type from elsewhere | Use the `Outer.Nested` form, such as `EventSource.Listener`, and ensure the enclosing type is accessible. |
| Thinking an interface nested in an interface can be `private` or `protected` | A member type of an interface is implicitly `public static`; its access cannot be reduced with `private` or `protected`. |
| Using a lambda for an interface with multiple abstract methods | A lambda is only suitable when the target type is a functional interface, meaning it has exactly one abstract method according to Java rules. |
| Assuming a nested interface can directly access instance fields of the enclosing class | Because a member interface is `static`, it has no implicit enclosing instance. To use instance data, pass the required object or value in. |

## 7. Quick Checklist

- [ ] Identify whether the interface is declared in a class or in an interface.
- [ ] Use the correct type name: `Outer.Nested` when referencing from outside the enclosing scope.
- [ ] Check the access level of the enclosing type and the nested interface.
- [ ] Remember that a member interface is implicitly `static`; no enclosing instance needs to be created.
- [ ] Choose a lambda only when the interface is a functional interface; otherwise, provide a full implementing class.
- [ ] For the runnable example, check that the file name matches the `public` class name, the compile command, and stdout.

## 8. Summary of the Rules

The main difference between the two declaration locations lies in the implicit access level: an interface nested in a class has an access level chosen by the author, while a member interface in an interface is always `public static`. Both are static member interfaces, are referenced by the enclosing type name, and can be implemented or used as a lambda target type when they satisfy the functional interface condition.
