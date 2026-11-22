# @Override in Java: Checking Overriding and Interface Method Implementation

## 1. What Is @Override?

`@Override` is a standard annotation in the `java.lang` package, written immediately before a **method** declaration. By using it, the developer instructs `javac` to verify that this method actually **overrides** a matching method in a supertype or **implements** a method declared in an interface according to Java language rules.

For example, suppose you intend to override `send(String)` but accidentally write `send(Object)`. Without `@Override`, this may simply be a new overload: the program compiles, but its behavior is not what you expect. With `@Override`, the error is caught immediately at compile time.

This annotation has `@Target(ElementType.METHOD)` and `@Retention(RetentionPolicy.SOURCE)`:

- **Checked at compile time:** if there is no valid override/implement relationship, the compiler reports an error.
- **Expresses intent:** readers recognize that the method fulfills a contract from a supertype or interface.
- **Does not create polymorphism:** dynamic dispatch is already the rule for overridable instance methods in Java; adding or removing the annotation does not change which method is called at runtime.
- **Not mandatory for every override:** Java allows valid overrides without the annotation, but using `@Override` is a good practice because it enables early checking.

## 2. Three Common Scenarios

### Overriding an instance method of a superclass

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

`Cat.sound()` replaces the `Animal.sound()` implementation. If `Animal a = new Cat();`, the expression `a.sound()` returns `"meow"` through dynamic dispatch based on the actual object.

### Implementing an abstract method from an interface

```java
interface PaymentMethod {
    String pay(int amount);
}

class CardPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "Paid " + amount + " by card";
    }
}
```

Although an interface only declares a contract, `@Override` is still valid on the implementing method in `CardPayment`. Regular interface methods are `public`, so the implementing method must be `public`. This is a common way to have the compiler verify classes implementing an interface.

### Overriding a default method of an interface

An interface can declare a `default` method with a body. An implementing class can override it with `@Override`. If multiple interfaces introduce conflicting default methods with the same signature, the class must resolve the conflict according to Java rules; annotating the implementation with `@Override` also helps clarify intent.

You can also use this annotation when overriding eligible `Object` methods, such as `toString()`, `equals(Object)`, and `hashCode()`. For `equals`, writing `equals(MyClass)` only creates an overload, rather than overriding `equals(Object)`.

## 3. Complete Java 17+ Example: Interface, Superclass, and Polymorphism

Save the **entire** following program into the file `OverrideDemo.java`:

```java
import java.util.Locale;

interface MessageFormatter {
    String format(String text);

    default String kind() {
        return "default";
    }
}

class UppercaseFormatter implements MessageFormatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    @Override
    public String kind() {
        return "uppercase";
    }
}

class BracketFormatter extends UppercaseFormatter {
    @Override
    public String format(String text) {
        return "[" + super.format(text) + "]";
    }
}

public class OverrideDemo {
    public static void main(String[] args) {
        MessageFormatter formatter = new BracketFormatter();

        System.out.println(formatter.format("java"));
        System.out.println(formatter.kind());
        System.out.println(new UppercaseFormatter().format("core"));
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 OverrideDemo.java
java OverrideDemo
```

Exact stdout:

```text
[JAVA]
uppercase
CORE
```

Analysis:

1. `MessageFormatter` declares the `format(String)` method and provides a `default` definition for `kind()`.
2. `UppercaseFormatter.format` **implements the interface method**; `UppercaseFormatter.kind` **overrides the default method**.
3. `BracketFormatter.format` **overrides the superclass method**; the call `super.format(text)` reuses the uppercasing step and then adds brackets.
4. The variable `formatter` has the **reference type** `MessageFormatter`, while the actual object is a `BracketFormatter`. Calling `format("java")` runs `BracketFormatter.format`; calling `kind()` runs the version inherited from `UppercaseFormatter`.

You can remove only the `@Override` lines and recompile: stdout remains the same. This demonstrates that the annotation checks the contract at compile time, whereas polymorphism is a rule of the Java runtime.

## 4. Rules for Valid Overriding

| Aspect | Rule |
| --- | --- |
| Name and parameters | Must have an override-compatible signature with the supertype method. The same name with different parameter types or count typically creates an **overload**. Generics add subsignature/erasure rules. |
| Return type | The return type must be compatible: the same type, or an appropriate subtype for reference types (**covariant return**). You cannot arbitrarily change from `int` to `long`. |
| Access modifier | Visibility cannot be reduced. For example, an override of a `public` method must remain `public`. |
| Checked exceptions | Cannot declare new or broader checked exceptions than the supertype method's contract; they may be omitted or narrowed. Unchecked exceptions are not subject to this restriction. |
| Instance / static | Instance methods can be overridden if conditions are met; `static` methods follow **hiding**, not overriding. |
| Inheritance | A `final` instance method cannot be overridden. `private` methods are not inherited for overriding; constructors are also not overridden methods. |

Example of **covariant return** (this is a snippet of class definitions that can be placed in a Java file, not a standalone program with its own `main`):

```java
class Counter {
    Number getValue() {
        return 1;
    }
}

class FixedCounter extends Counter {
    @Override
    Integer getValue() {
        return 42;
    }
}
```

`Integer` is a subtype of `Number`, so `FixedCounter.getValue()` is a valid override. If you change the return type to `String`, the compiler will reject it.

## 5. Common Errors Caught by @Override

### 5.1. Confusing override and overload

**Intentionally invalid** example that does not compile:

```java
class Printer {
    void print(String message) {}
}

class FancyPrinter extends Printer {
    @Override
    void print(Object message) {}
}
```

`print(Object)` does not override `print(String)`. `javac` reports an error such as `method does not override or implement a method from a supertype`. If the goal is to override, change it to `print(String message)`; if the intention is to add an overload, remove `@Override`.

A similar trap is `equals(MyType)`: only `equals(Object)` with a `boolean` return type overrides the method in `Object`.

### 5.2. Forgetting public when implementing an interface

The following snippet is **intentionally invalid**:

```java
interface Greeter {
    void greet();
}

class BadGreeter implements Greeter {
    @Override
    void greet() {}
}
```

`Greeter.greet()` is `public`, whereas `BadGreeter.greet()` has only package-private access. Java does not allow reducing visibility. Fix it to `@Override public void greet() {}`.

### 5.3. Confusing static hiding with override

The following snippet is **intentionally invalid**:

```java
class BaseTool {
    static void reset() {}
}

class Tool extends BaseTool {
    @Override
    static void reset() {}
}
```

Two `static` methods with the same name follow **method hiding**. `@Override` on `Tool.reset()` is invalid. When calling a static method, method selection is bound to the type used in the expression according to Java rules, unlike dynamic dispatch for instance methods.

### 5.4. final, private, and constructors

- You cannot override an instance method with the `final` modifier; the override declaration itself causes an error.
- A `private` method in a superclass is not inherited for overriding. A method with the same name in a subclass does not become an override of that private method.
- Constructors are not inherited methods, so `@Override` is not placed on them.
- `@Override` also does not turn field hiding into method overriding.
- A signature can match and still fail if the return type is incompatible, visibility is reduced, or checked exceptions are broadened.

## 6. @Override with Generics and Interface Inheritance

The declarations below are valid and can be placed in the same Java file:

```java
interface Converter<T> {
    T convert(T value);
}

final class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
```

When the class chooses `T = String`, the contract is implemented by `convert(String)`. `@Override` checks this relationship according to Java's generics rules. After **type erasure**, the compiler may generate a **bridge method** in the bytecode to preserve polymorphism; a bridge method is a compiler detail, and you do not declare `@Override` on it yourself.

An interface can extend another interface. A class implementing a subinterface must still satisfy any inherited abstract methods that have not yet been implemented, unless the class is declared `abstract` or inherits a valid implementation. `@Override` marks the method that the class actually provides; there is no need to add a method just to attach the annotation if a suitable implementation is already inherited.

## 7. What @Override Does Not Guarantee

`@Override` does not force a subclass to override a method that already has an implementation (unlike a concrete class's obligation to implement abstract methods); it does not verify business logic; it does not generate code; and it does not replace testing. For example, an `equals(Object)` method with the exact right signature can still violate the symmetry rule or be inconsistent with `hashCode()`.

The annotation also does not interfere with **overload resolution**: Java selects the matching overload based on expression and argument types at compile time; dynamic dispatch then selects the overriding implementation of that chosen signature based on the object's runtime type.

## 8. How to Use It in Practice

1. Start from the superclass/interface contract: determine the signature, return type, visibility, and checked exceptions.
2. Write the exact method to be implemented or replaced, placing `@Override` immediately above its declaration.
3. Run `javac` or the project build: if an interface or superclass changes a signature, treat the compile error as a signal that the implementation needs to be updated.
4. Test behavior through a supertype/interface-typed variable to confirm correct dispatch; pay attention to `super` calls, `default` methods, and generics.
5. If you get an `@Override` error, compare against the actual contract; do not simply delete the annotation to make the build green, as doing so can mask an accidental overload.

**Key takeaway:** `@Override` is a compile-time-checked way of expressing intent. It helps prevent signature mistakes when overriding a superclass method or implementing an interface; Java's own method rules determine the actual overriding and dispatch.
