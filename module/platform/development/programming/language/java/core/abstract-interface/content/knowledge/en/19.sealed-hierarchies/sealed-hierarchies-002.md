# Sealed abstract class and sealed interface in Java

## 1. Purpose and concept

Since Java 17, `sealed class` and `sealed interface` have been official features that restrict which types are allowed to directly extend or implement a type. They are useful when a domain model has a known set of variants, such as geometric shapes, processing states, or transport vehicles.

`abstract` and `sealed` solve two different problems:

- `abstract` prevents creating objects directly from a class and allows declaring methods without an implementation.
- `sealed` restricts the set of classes or interfaces permitted to directly inherit from that type.
- Combining `abstract sealed class` creates a base class that cannot be instantiated, while explicitly controlling its inheritance branches.

`sealed` does not make objects immutable, does not automatically turn every method into `final`, and does not replace input validation.

## 2. How do sealed abstract class and sealed interface differ?

| Aspect | `sealed abstract class` | `sealed interface` |
| --- | --- | --- |
| Common purpose | Share state, constructors, and common behavior for a family of classes | Define a contract for a controlled set of types |
| Object state | Can have instance fields | Has no instance fields; fields declared in an interface are `public static final` constants |
| Constructor | Can declare constructors to initialize shared state | Has no constructors |
| Methods | Can have abstract, concrete, final, or protected methods | Can have abstract, `default`, `static`, and private methods according to interface rules |
| Inheritance | A class can only extend one class | A class can implement multiple interfaces |
| Types allowed to inherit directly | Subclasses | Subclasses or subinterfaces |

Choose an abstract class when variants have common data or workflows that need to be reused. Choose an interface when the focus is a capability or contract that types can implement in multiple ways. Both can be used in the same design.

## 3. Rules of a sealed hierarchy

### Declaration and `permits`

```java
sealed abstract class Vehicle permits Car, Truck {
    abstract double maxLoad();
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}
```

`permits` lists the permitted direct subtypes. List the exact types that directly `extends` or `implements` the sealed type; do not list classes deeper in the inheritance tree.

`permits` can be omitted when all direct subtypes are declared in the same compilation unit as the sealed type; the compiler will infer that list. If the types are declared in different source files, declare `permits` explicitly.

### Policy for direct subtypes

A class permitted to directly extend or implement a sealed type must be `final`, `sealed`, or `non-sealed`; a record is implicitly `final`. `final` closes the branch, `sealed` continues restricting level by level, while `non-sealed` opens the branch for descendants that do not need to appear in the ancestor's `permits` list. Specifically, a **subinterface** cannot be `final`, so it can only choose `sealed` or `non-sealed`.

A `non-sealed` `Truck` branch can have `DeliveryTruck` extending it, but `DeliveryTruck` is still an **indirect** descendant of `Vehicle`.

### Package and module rules

- When not using a named module, the sealed type and its permitted direct subtypes must be in the same package.
- When using a named module, they must be in the same module; packages may differ.
- Each type listed in `permits` must actually be a direct subtype of the corresponding sealed type.
- A `record` is an implicitly `final` type, so it can directly implement a sealed interface when the remaining rules are satisfied. A record always extends `java.lang.Record`, so it **cannot** directly `extends` a sealed class.

### Sealed does not mean abstract

A sealed class can be concrete. `abstract` is only necessary when you want to forbid direct instantiation of the base class or when there are still unimplemented abstract methods. A sealed interface already cannot be instantiated directly, so it does not need the `abstract` keyword.

## 4. Complete Java 17 example

The example below illustrates two independent hierarchies: `Shape` is a sealed interface; `Vehicle` is a sealed abstract class. `Circle` and `Car` close their branches with `final`, while `Rectangle` and `Truck` open their branches with `non-sealed`.

Save the following content as `Main.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class Main {
    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape rectangle = new Rectangle(3.0, 4.0);
        System.out.printf(Locale.ROOT, "Circle area: %.2f%n", circle.area());
        System.out.printf(Locale.ROOT, "Rectangle area: %.2f%n", rectangle.area());

        Vehicle car = new Car("51A-123.45");
        Vehicle truck = new DeliveryTruck("51C-678.90", 8.5);
        System.out.println(car.description());
        System.out.printf(Locale.ROOT, "Truck max load: %.1f t%n", truck.maxLoad());

        if (truck instanceof Truck t) {
            System.out.println("Truck registration: " + t.registration());
        }
    }
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}

final class Circle implements Shape {
    private final double radius;

    Circle(double radius) {
        if (radius <= 0) {
            throw new IllegalArgumentException("radius must be positive");
        }
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

non-sealed class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}

sealed abstract class Vehicle permits Car, Truck {
    private final String registration;

    protected Vehicle(String registration) {
        this.registration = Objects.requireNonNull(registration, "registration");
    }

    public final String registration() {
        return registration;
    }

    public String description() {
        return getClass().getSimpleName() + " [" + registration + "]";
    }

    public abstract double maxLoad();
}

final class Car extends Vehicle {
    Car(String registration) {
        super(registration);
    }

    @Override
    public double maxLoad() {
        return 0.0;
    }
}

non-sealed class Truck extends Vehicle {
    private final double maxLoad;

    Truck(String registration, double maxLoad) {
        super(registration);
        if (maxLoad < 0) {
            throw new IllegalArgumentException("maxLoad must not be negative");
        }
        this.maxLoad = maxLoad;
    }

    @Override
    public double maxLoad() {
        return maxLoad;
    }
}

final class DeliveryTruck extends Truck {
    DeliveryTruck(String registration, double maxLoad) {
        super(registration, maxLoad);
    }
}
```

Compile and run with JDK 17 or later:

```text
javac --release 17 Main.java
java Main
```

Stdout output:

```text
Circle area: 12.57
Rectangle area: 12.00
Car [51A-123.45]
Truck max load: 8.5 t
Truck registration: 51C-678.90
```

## 5. Reading the example part by part

- `Shape` defines the `area()` contract. `Circle` and `Rectangle` are the two permitted direct implementations.
- `Circle` is `final`, so it cannot have subclasses. `Rectangle` is `non-sealed`, so it can be extended further without modifying `Shape`'s `permits` list.
- `Vehicle` is both `sealed` and `abstract`. The shared constructor validates `registration`, while `description()` is common behavior and `maxLoad()` is a requirement that each vehicle type must implement.
- `Car` is a `final` direct subclass; `Truck` is a `non-sealed` direct subclass. `DeliveryTruck` extends `Truck`, illustrating an indirect subclass permitted by the opened branch.
- The variable `truck` has declared type `Vehicle`, but the actual object is `DeliveryTruck`. The expression `truck instanceof Truck t` checks the type and creates the pattern variable `t` when the condition is true; this syntax has been available since Java 16, so it is suitable for Java 17.
- `Locale.ROOT` keeps the decimal point of number formatting stable, helping the stdout in the example not depend on the machine's locale.

## 6. Common mistakes

1. **Forgetting to declare the modifier of a direct subtype.** A direct subtype of a sealed class or interface must declare `final`, `sealed`, or `non-sealed` (a record is implicitly `final`). Missing this choice will cause a compilation error.
2. **Putting indirect subtypes in `permits`.** Only types that directly `extends` or `implements` may be listed.
3. **Placing subtypes in the wrong package or module.** Check the package rules when using an unnamed module and the module rules when using a named module.
4. **Using `non-sealed` on a type without a direct sealed parent.** This keyword is only valid when the type directly extends or implements a sealed type.
5. **Confusing `abstract` with `sealed`.** An abstract class can be extended freely if there are no other constraints; sealed is the keyword that restricts direct subtypes.
6. **Assuming `sealed` locks the entire inheritance tree.** `non-sealed` branches still allow further extension. If you need to close a branch completely, use `final`; if you want to continue controlling level by level, use `sealed` at the next level.
7. **Using syntax examples newer than the target version.** Sealed types were finalized in Java 17. If using pattern matching for `switch`, you need to check the corresponding Java version; the example above does not depend on newer `switch` features.

## 7. When should you use them?

Use a sealed hierarchy when the set of valid variants can be clearly defined at the design level and adding a new variant should force maintainers to review the related handling points. This is a suitable choice for domain models, syntax trees, transaction states, or result types with a finite set of cases.

Avoid using sealed just to add extra keywords to a hierarchy that needs to be extended freely by external libraries or applications. In that case, a regular interface or abstract class may be more suitable.

Before finalizing the design, check:

- Does the list of direct subtypes accurately reflect the valid variants?
- Has each direct subtype chosen `final`, `sealed`, or `non-sealed`?
- Should state and implementation be shared with an abstract class, or is only a contract with an interface needed?
- Do you really want to open an inheritance branch with `non-sealed`?
- Does the JDK version used for compilation support the features appearing in the source code?
