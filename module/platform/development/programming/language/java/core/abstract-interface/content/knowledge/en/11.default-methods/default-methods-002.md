# Syntax and Body of Default Methods in Java Interfaces

A `default` method is an instance method with a body declared **inside an interface**. Since Java 8, it allows an interface to provide shared behavior; an implementing class can inherit that behavior without having to write it itself.

## 1. Syntax and Access

```java
interface CounterView {
    int value();

    default boolean isEmpty() {
        return value() == 0;
    }

    default void printStatus() {
        System.out.println(isEmpty() ? "Rỗng" : "Có dữ liệu");
    }
}
```

`value()` is an abstract method, while `isEmpty()` and `printStatus()` have bodies. A default method can use parameters, local variables, conditionals, loops, `return`, `throw`, and call other valid methods like a regular instance method.

A default method is always **public**, even when the `public` keyword is not written. When overridden in a class, the overriding method must also be `public`. The `default` keyword does not mean package-private and does not turn the method into `static`.

## 2. Distinguishing Method Types

| Declaration | Has a body? | Meaning |
| --- | --- | --- |
| `void run();` | No | Abstract contract; a concrete class needs an appropriate implementation. |
| `default void run() { ... }` | Yes | Default instance behavior; a class can inherit or override it. |
| `static void help() { ... }` | Yes | Belongs to the interface, called via `InterfaceName.help()`; not overridden through instance polymorphism. |
| `private void helper() { ... }` | Yes, since Java 9 | Internal helper for interface methods to reuse logic. |

A default method is required to have a body. To declare an abstract method, omit `default` and end with a semicolon. `default` cannot be used in a regular class.

## 3. Runnable Example

Save to `Main.java`:

```java
public class Main {
    interface Greeting {
        default String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class BasicGreeter implements Greeting {
        // Inherits greet(String).
    }

    static final class FriendlyGreeter implements Greeting {
        @Override
        public String greet(String name) {
            return "Chào bạn, " + name;
        }
    }

    public static void main(String[] args) {
        System.out.println(new BasicGreeter().greet("An"));
        System.out.println(new FriendlyGreeter().greet("An"));
    }
}
```

Run with JDK 17 or later:

```bash
javac Main.java
java Main
```

Output:

```text
Xin chào, An
Chào bạn, An
```

`BasicGreeter` uses the default body. `FriendlyGreeter` provides a `public` instance method with the same signature to change the behavior. The class does not add the `default` keyword.

## 4. Common Syntax Errors

```java
interface Invalid {
    default void run();          // Invalid: missing body.
    abstract default void a() {} // Invalid: abstract and default conflict.
    static default void b() {}   // Invalid: static and default conflict.
    protected default void c() {} // Invalid: default methods are public.
}
```

A method with a body in an interface also cannot be declared `default` to override the corresponding public methods of `Object`, such as `toString()`, `equals(Object)`, or `hashCode()`. If a custom implementation is needed, place the override in a class.

Do not confuse `default method` with the `default:` branch of a `switch`, the default value of an annotation, or package-private access. This is a dedicated modifier for instance methods with a body in an interface.

## 5. How to Decide

Use a default method when there is sensible shared behavior that implementations can inherit. If every implementation must define an important policy itself, use an abstract method. If the behavior requires its own state, constructors, or resource management, consider a class or composition. The rules for choosing among inherited methods are covered in the lessons on overriding and inheritance; the basic syntax here does not resolve all conflicts on its own.

## Self-Check

1. Why is `default void run();` invalid?
2. Is a default method a package-private method?
3. Does a class overriding a default method need to write `default`?
4. From which Java version do interfaces have private helper methods?

**Remember:** `default ReturnType method(...) { ... }` is used only for instance methods with a body in an interface. It is public and can be overridden by implementing classes with a normal instance method.
