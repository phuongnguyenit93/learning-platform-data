# Declaring `sealed class`, `sealed interface`, and `permits` in Java 17

**Topic:** Java 17 → Sealed Basics

Starting in **Java 17**, `sealed` is an official language feature that lets a class or interface **directly restrict which types are allowed to inherit or implement it**. When declaring a type as `sealed`, you can use `permits` to specify the list of direct subclasses or subinterfaces allowed to participate in that hierarchy.

This mechanism is useful when a model has only a fixed number of valid variants, such as processing states, transaction outcomes, or application event groups. The examples in this lesson use **standard Java 17** syntax without needing `--enable-preview` or experimental APIs.

## 1. What problem does `sealed` solve?

Suppose an application has a `PaymentResult` type representing a payment outcome. Two cases are designed upfront: `Success` and `Failure`. If you declare a regular interface:

~~~java
interface PaymentResult {
}
~~~

then any class that can see this interface and satisfies access rules can `implements PaymentResult`. Another library or module might introduce unexpected result types. This is not always wrong, but it becomes problematic when a business domain **allows only a defined set of cases**.

With a sealed interface:

~~~java
sealed interface PaymentResult permits Success, Failure {
}

record Success(String transactionId) implements PaymentResult {
}

record Failure(String reason) implements PaymentResult {
}
~~~

Java 17 enforces at compile time that only the permitted types may directly `implements PaymentResult`. The two `record` types here are permitted direct subtypes, and because they are implicitly `final`, they cannot be subclassed further.

**Distinguishing three concepts:**

| Declaration | Inheritance meaning |
| --- | --- |
| Regular `class` / `interface` | Subtypes can be declared according to standard access and inheritance rules. |
| `final class` | No class may inherit from that class. |
| `sealed class` / `sealed interface` | Only a defined list of **direct** subtypes is allowed; each subtype decides how the hierarchy continues. |

`sealed` **does not mean immutable**. It controls inheritance relationships, not whether an object's properties can change.

## 2. Declaration syntax with `permits`

### 2.1. Sealed class

General syntax:

~~~java
sealed class Parent permits ChildA, ChildB {
    // Fields, constructors, and methods
}
~~~

The `Parent` class explicitly lists the classes permitted to **directly** `extends Parent`. The listed classes must actually declare `extends Parent` and adhere to the constraints of a sealed hierarchy.

A sealed class can also be abstract:

~~~java
abstract sealed class Shape permits Circle, Rectangle {
    abstract double area();
}

final class Circle extends Shape {
    @Override
    double area() {
        return Math.PI;
    }
}

non-sealed class Rectangle extends Shape {
    @Override
    double area() {
        return 1.0;
    }
}
~~~

This snippet illustrates **the declaration syntax**: `Shape` is an abstract superclass, and `Circle` and `Rectangle` are the two permitted direct subclasses. A later section builds a full example with fields that compiles and runs.

### 2.2. Sealed interface

General syntax:

~~~java
sealed interface Parent permits ChildA, ChildB {
    // Method declarations
}
~~~

For a sealed interface, names in `permits` can be **classes directly using `implements`** or **subinterfaces directly using `extends`**.

~~~java
sealed interface Event permits LoginEvent, LogoutEvent, SystemEvent {
}

record LoginEvent(String username) implements Event {
}

record LogoutEvent(String username) implements Event {
}

non-sealed interface SystemEvent extends Event {
    String description();
}
~~~

`LoginEvent` and `LogoutEvent` are records; `SystemEvent` is a direct subinterface. Because `SystemEvent` is `non-sealed`, other types can implement `SystemEvent` under normal Java rules. They are **indirect** descendants of `Event`, so they do not need to be named in `Event.permits`.

### 2.3. What exactly does `permits` mean?

In the declaration:

~~~java
sealed interface Message permits TextMessage, ImageMessage {
}
~~~

- `sealed`: tells the compiler to restrict direct subtypes.
- `interface Message`: the supertype being declared.
- `permits TextMessage, ImageMessage`: **the list of permitted direct subtypes**. This is not a list of objects created at runtime, nor is it an access-control mechanism.
- `TextMessage` and `ImageMessage` must directly `implements Message` or, if interfaces, directly `extends Message`.

`permits` does not list every descendant at all depths. A `non-sealed` subtype can continue to be extended or implemented, depending on its kind.

## 3. How must each direct subtype be declared?

A class permitted to directly extend a sealed class, or a class directly implementing a sealed interface, must have one of the following modifiers:

| Status | Meaning | Example |
| --- | --- | --- |
| `final` | Terminates the inheritance branch at this class. | `final class Circle extends Shape` |
| `sealed` | Continues restricting the list of direct subtypes at the next level. | `sealed class Polygon extends Shape permits Triangle` |
| `non-sealed` | Reopens inheritance along that branch. | `non-sealed class Rectangle extends Shape` |

For an **interface** directly extending a sealed interface, the two options are `sealed` or `non-sealed`; an interface cannot be declared `final`. For a **record** directly implementing a sealed interface, the record is already implicitly `final`, so no extra `final` modifier is required.

Structural example:

~~~text
Shape (abstract sealed)
├── Circle (final)
└── Rectangle (non-sealed)
    └── Square (final)
~~~

The sealed class `Shape` permits strictly two **direct** subclasses: `Circle` and `Rectangle`. `Square` can still inherit from `Rectangle` because that branch is marked `non-sealed`. `Square` is not a direct subclass of `Shape`, so it does not appear in `Shape`'s `permits` list.

> **Key point:** `sealed`, `non-sealed`, and `final` cannot be combined arbitrarily. A class cannot be both `final` and `sealed`. A `non-sealed` class/interface must have a direct sealed supertype for "reopening" inheritance to make sense.

## 4. Complete example with `sealed class`

Create the file **`SealedClassDemo.java`**:

~~~java
public class SealedClassDemo {
    static abstract sealed class Shape permits Circle, Rectangle {
        abstract double area();
    }

    static final class Circle extends Shape {
        private final double radius;

        Circle(double radius) {
            this.radius = radius;
        }

        @Override
        double area() {
            return Math.PI * radius * radius;
        }
    }

    static non-sealed class Rectangle extends Shape {
        private final double width;
        private final double height;

        Rectangle(double width, double height) {
            this.width = width;
            this.height = height;
        }

        @Override
        double area() {
            return width * height;
        }
    }

    static final class Square extends Rectangle {
        Square(double side) {
            super(side, side);
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape square = new Square(3.0);

        System.out.println("Circle area: " + circle.area());
        System.out.println("Square area: " + square.area());
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 SealedClassDemo.java
java SealedClassDemo
~~~

In this example:

1. `Shape` is an **`abstract sealed class`**, defining the area contract and preventing direct instantiation.
2. `permits Circle, Rectangle` restricts which classes may directly extend `Shape`.
3. `Circle` is declared `final`, so `Circle` cannot have subclasses.
4. `Rectangle` is declared `non-sealed`, allowing `Square` to extend it.
5. `Square` extends `Rectangle`; it does not need to be declared in `Shape.permits`.

Here, the types are declared nested inside the same `SealedClassDemo` class so the whole example fits in one file and the type relationships are clear.

## 5. Complete example with `sealed interface` and `record`

A processing result model often suits a sealed interface because each variant carries different data while belonging to one defined set of outcomes.

Create the file **`SealedInterfaceDemo.java`**:

~~~java
public class SealedInterfaceDemo {
    sealed interface Result permits Success, Failure, Deferred {
    }

    record Success(String value) implements Result {
    }

    record Failure(String reason) implements Result {
    }

    non-sealed interface Deferred extends Result {
        String ticket();
    }

    static final class Pending implements Deferred {
        private final String ticket;

        Pending(String ticket) {
            this.ticket = ticket;
        }

        @Override
        public String ticket() {
            return ticket;
        }
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.reason();
        }
        if (result instanceof Deferred deferred) {
            return "Waiting: " + deferred.ticket();
        }
        throw new IllegalStateException("Unhandled Result type");
    }

    public static void main(String[] args) {
        Result a = new Success("Saved");
        Result b = new Failure("Invalid data");
        Result c = new Pending("REQ-001");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println(describe(c));
    }
}
~~~

Run:

~~~shell
javac --release 17 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Output:

~~~text
Success: Saved
Failure: Invalid data
Waiting: REQ-001
~~~

In this example:

- `Result` is a sealed interface with three **direct** permitted types.
- `Success` and `Failure` are `record` types directly implementing `Result`; records cannot be inherited further.
- `Deferred` is a direct subinterface, marked `non-sealed` to allow additional pending-type implementations.
- `Pending` implements `Deferred` rather than directly implementing `Result`, so it does not need to appear in `Result.permits`.
- `instanceof Success success` is **pattern matching for instanceof**, an official feature since before Java 17. It works well for handling result types in this lesson.

**Java 17 note:** avoid using *pattern matching for switch* to handle sealed types in standard Java 17 examples, because that feature is still in **preview in Java 17**. Regular `switch` expressions are already standard, but that is a different feature. The `if`/`instanceof` branches above use standard syntax with no preview flags required.

## 6. When can `permits` be omitted?

In Java 17, if the direct subclasses or subinterfaces are declared **in the same Java compilation unit** as the sealed type, the compiler can infer the permitted list. In that case, `permits` may be omitted.

For example, placing all of the following declarations in the **same `State.java` file**:

~~~java
sealed interface State {
}

final class Ready implements State {
}

final class Stopped implements State {
}
~~~

The compiler infers `Ready` and `Stopped` as the two permitted subtypes of `State`.

Semantically, the declaration above is equivalent to:

~~~java
sealed interface State permits Ready, Stopped {
}
~~~

When types are placed in **separate files**, declare `permits` explicitly to state the allowed relationships. For teaching code or domain models with multiple components, writing `permits` explicitly also helps readers quickly grasp the design structure.

> Inferring `permits` depends on being in the **same compilation unit**, not merely files in the same directory or package.

## 7. Rules for packages, modules, and direct subtypes

`sealed` is checked **at compile time** and imposes location constraints:

| Context | Permitted location for direct subtypes in `permits` |
| --- | --- |
| Sealed type belongs to a **named module** (a module with `module-info.java`) | Direct subtypes must be **in the same named module**; they may be in another package in that module if access rules permit. |
| Sealed type belongs to an **unnamed module** (typical in Java projects without JPMS) | Direct subtypes must be **in the same package**. |

For a simple non-modular project, you can place files in the `example.shapes` package:

**`Shape.java`:**

~~~java
package example.shapes;

public abstract sealed class Shape permits Circle, Rectangle {
    public abstract double area();
}
~~~

**`Circle.java`:**

~~~java
package example.shapes;

public final class Circle extends Shape {
    @Override
    public double area() {
        return Math.PI;
    }
}
~~~

**`Rectangle.java`:**

~~~java
package example.shapes;

public non-sealed class Rectangle extends Shape {
    @Override
    public double area() {
        return 1.0;
    }
}
~~~

The three types are in the same package, `Circle` and `Rectangle` directly `extends Shape`, and each subclass has a valid `final` or `non-sealed` modifier.

`permits` **does not bypass visibility rules**. For instance, if the superclass constructor or method is not accessible from the subclass, compilation can still fail even though the subclass name is in `permits`.

## 8. Common declaration mistakes

### 8.1. Missing modifier on a direct subclass

**Invalid** example intentionally showing the error:

~~~java
sealed class Vehicle permits Car {
}

class Car extends Vehicle {
    // Error: direct subclass of a sealed class
    // must be declared final, sealed, or non-sealed.
}
~~~

Fix this to `final class Car extends Vehicle` if closing the branch, or use `sealed` / `non-sealed` according to your design intent.

### 8.2. Declaring a subtype not listed in `permits`

**Invalid** example:

~~~java
sealed interface Command permits Start {
}

final class Start implements Command {
}

final class Stop implements Command {
    // Error: Stop directly implements Command
    // but is not in Command's permits list.
}
~~~

To make `Stop` a valid subtype, add it to the `permits` list and ensure it meets the package/module rules.

### 8.3. Mistakenly listing an indirect descendant

**Invalid** example:

~~~java
sealed class Animal permits Dog, Poodle {
}

non-sealed class Dog extends Animal {
}

final class Poodle extends Dog {
    // Error in Animal.permits: Poodle does not directly extend Animal.
}
~~~

The valid declaration is `sealed class Animal permits Dog`, since `Poodle` inherits from `Animal` only **indirectly**.

### 8.4. Using `non-sealed` without a sealed supertype

**Invalid** example:

~~~java
class PlainBase {
}

non-sealed class Other extends PlainBase {
    // Error: no direct sealed supertype whose branch needs reopening.
}
~~~

`non-sealed` makes sense within a hierarchy restricted by a sealed supertype. For a regular class, simply declare `class Other extends PlainBase`.

### 8.5. Confusing `sealed` with `final` or security mechanisms

You cannot declare `final sealed class`, because `final` forbids inheritance completely whereas `sealed` permits specific subclasses. Nor does `permits` grant permission to call methods, access fields, or bypass `private`, `protected`, or module rules.

## 9. Choosing between `sealed class` and `sealed interface`

| Criterion | `sealed class` | `sealed interface` |
| --- | --- | --- |
| Relationship | Subtypes **`extends`** a superclass. | Classes **`implements`** or subinterfaces **`extends`** a superinterface. |
| Shared state and behavior | Can hold fields, constructors, concrete methods, and abstract methods; suitable when sharing code or state. | Primarily represents a contract; can declare methods and `default` methods; has no constructors or instance fields. |
| Composability | A Java class can directly `extends` only one superclass. | A class can implement multiple interfaces, subject to inheritance and `permits` rules. |
| Combination with `record` | A `record` cannot arbitrarily `extends` a sealed class because it already extends `java.lang.Record`. | A `record` can directly `implements` a sealed interface, making it convenient for data variants. |
| When to consider | Hierarchies with shared behavior or state managed by the parent class. | Type sets representing business cases where each variant has a different data shape. |

If you want an API that lets external code create many new extensible implementations, `sealed` can reduce that API's extensibility. Choose `sealed` when **restricting subtypes is an intentional design requirement**.

## 10. Takeaways when working with Java 17

1. Use `sealed class` or `sealed interface` to restrict **direct subtypes**.
2. Write `permits` to list permitted direct subtypes, or omit the list only when the compiler can infer it from the same compilation unit.
3. Each direct subclass must be `final`, `sealed`, or `non-sealed`; direct subinterfaces choose `sealed` or `non-sealed`; records are implicitly `final`.
4. Follow the same-named-module rule, or same-package rule in an unnamed module.
5. Do not confuse `sealed` with `final`, data immutability, or access permissions.
6. When writing Java 17 examples, use standard `sealed` syntax and avoid *preview* features such as pattern matching in `switch` on Java 17 itself.

### Official references

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): proposal for sealed classes/interfaces finalized in JDK 17.
- [Java Language Specification, Java SE 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): rules for class declarations, sealed classes, and permitted direct subclasses.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): rules for sealed interfaces and interface extension relationships.
- [Java SE 17 Language Updates](https://docs.oracle.com/en/java/javase/17/language/): overview of Java 17 language features.
