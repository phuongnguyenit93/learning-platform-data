# `abstract` Method Declaration Syntax and the Semicolon

An `abstract` method declares **a behavior that requires an implementation** but contains no method body at the point of declaration. In a class, the syntax is identified by the `abstract` keyword and the semicolon `;` at the end of the declaration.

## 1. Declaration Pattern in a Class

```java
[access-modifier] abstract [TypeParameters] ReturnType methodName(Parameters)
        [throws ExceptionTypes];
```

Square brackets in the pattern only mark optional parts; do not type them into Java code. `TypeParameters` is a generic declaration such as `<T>`, `Parameters` can be empty, and `throws` appears only when the contract needs to declare exceptions. For example:

```java
abstract class Shape {
    public abstract double area();
    protected abstract void describe(String label);
}
```

`area()` returns `double`, while `describe(String)` takes one parameter and returns `void`. Both end with `;` and have no `{ ... }`. Because `Shape` directly declares abstract methods, `Shape` must also be an `abstract class`.

## 2. Why Does the Declaration End with `;`?

The `;` ends the signature without declaring a body:

```java
abstract class Worker {
    abstract void work(); // Valid: no implementation yet
}

class ConcreteWorker {
    void work() { }       // Valid: an empty body is still a concrete body
}
```

The two forms have different meanings. `abstract void work();` requires a concrete class to provide a valid implementation; `void work() { }` already has an implementation, even though the body does nothing yet.

Do not write:

```java
abstract class InvalidWorker {
    abstract void work() { } // Error: an abstract method cannot have a body
}
```

To declare a contract, remove `{ ... }` and use `;`. To implement the behavior in the current class, remove `abstract` and write the method body.

## 3. Placement of Generics, Parameters, and `throws`

A generic method places its type parameter list before the return type. If `throws` is present, the `;` still comes after that entire clause:

```java
abstract class Parser {
    protected abstract <T> T parse(
            String source, Class<T> targetType)
            throws java.text.ParseException;
}
```

Here, `<T>` is the method's type parameter, `String` and `Class<T>` are the parameter types, `T` is the return type, and `ParseException` is the declared exception. The declaration contains no string-parsing code; the implementing class will provide the body. Detailed rules on parameter compatibility, return types, and checked exceptions when overriding fall within the scope of the lesson on signature contracts.

## 4. Corresponding Syntax in an Interface

A regular instance method without a body in an interface is `public abstract` by default; both keywords can be omitted:

```java
interface Sender {
    void send(String message); // Equivalent to public abstract
}
```

When a class implements `Sender`, the `send` method must be `public`. Do not infer that every interface method is abstract: `default`, `static`, and `private` are other kinds of methods and must have a body according to their rules.

```java
interface MessageSender {
    void send(String message);

    default void sendWelcome() {
        send("Welcome");
    }

    static String protocol() {
        return "v1";
    }

    private String normalize(String message) {
        return message.strip();
    }
}
```

`send` is an abstract contract; `sendWelcome` has a default implementation; `protocol` belongs to the interface; `normalize` is an internal helper with a body. This example illustrates interface syntax, not an application with `main`.

## 5. Runnable Java 17+ Example

Save the code below to `AbstractMethodSyntaxDemo.java`:

```java
abstract class MessageFormatter {
    protected abstract String format(String message);

    public String show(String message) {
        return format(message);
    }
}

final class UppercaseFormatter extends MessageFormatter {
    @Override
    protected String format(String message) {
        return message.toUpperCase(java.util.Locale.ROOT);
    }
}

public class AbstractMethodSyntaxDemo {
    public static void main(String[] args) {
        MessageFormatter formatter = new UppercaseFormatter();
        System.out.println(formatter.show("hello java"));
    }
}
```

Compile and run using JDK 17 or later:

```bash
javac AbstractMethodSyntaxDemo.java
java AbstractMethodSyntaxDemo
```

Output:

```text
HELLO JAVA
```

`MessageFormatter` declares the `format` contract; `show` already has a body and calls that method. `UppercaseFormatter` provides the implementation. A call through a variable of type `MessageFormatter` still runs the implementation of the actual `UppercaseFormatter` object.

## 6. Common Syntax Errors

| Declaration | Result | How to Fix |
|---|---|---|
| `abstract void run()` in a class | Error if the declaration terminator is missing | Write `abstract void run();` |
| `abstract void run() { }` | Error because an abstract method has a body | Remove the body or remove `abstract` |
| `class A { abstract void run(); }` | Error because the class directly declares an abstract method without being abstract | Declare `abstract class A` or provide a concrete body |
| `class A { void run(); }` | Error because a concrete method in a class requires a body | Write `void run() { ... }` or change the design to an abstract class |
| A class implementing an interface with `void send(...)` without `public` | Error if the method is implementing a public interface method | Declare `public void send(...)` |

A quick checklist when reading a declaration: identify whether the enclosing type is a `class` or an `interface`; check for the `abstract` keyword; find the `;` at the end of the declaration; confirm there is no `{ ... }` body; then verify that concrete classes have a valid implementation. Conflicting modifier combinations such as `private abstract`, `static abstract`, and `final abstract` are explained separately in the lessons on modifiers.
