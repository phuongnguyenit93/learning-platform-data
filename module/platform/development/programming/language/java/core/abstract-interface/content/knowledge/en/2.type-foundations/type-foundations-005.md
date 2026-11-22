# Distinguishing `extends` and `implements` in Java

`extends` is used to inherit from a class or extend an interface. `implements` is used in a class declaration to state that the class fulfills the contract of one or more interfaces. The point to remember is that **interfaces also use `extends`**; `implements` is not the keyword for an interface inheriting from an interface.

## 1. Reading Declarations Before Reading Code

| Declaration | Meaning | Main Constraints |
|---|---|---|
| `class Child extends Parent` | Inherits from a class. | A class has only one direct superclass; `Parent` must not be `final`. |
| `abstract class Child extends Parent` | An abstract class inherits from a class. | Still has only one direct superclass. |
| `interface B extends A` | Interface B inherits contract A. | A must be an interface. |
| `interface C extends A, B` | Interface C combines multiple contracts. | Inherited declarations must be compatible. |
| `class Child implements A, B` | The class fulfills interfaces A and B. | A and B must be interfaces; a concrete class must implement the missing abstract methods. |
| `class Child extends Parent implements A, B` | Combines inheriting from a class and implementing multiple interfaces. | `extends` must appear before `implements`. |

Declaration examples:

```java
class Child extends Base implements Readable, Writable {
    // Must implement the missing abstract methods.
}

interface AdvancedReadable extends Readable, AutoCloseable {
    // Inherits the contracts of both interfaces.
}
```

There is no `class Child extends Base1, Base2` syntax. An interface can `extends` multiple interfaces, but it cannot `extends` a class. A class that does not declare `extends` implicitly inherits directly from `Object` (except `Object` itself).

## 2. `extends` Between Two Classes

With `class Dog extends Animal`, `Dog` is a subtype of `Animal` and can use inherited members according to Java rules.

- Suitable concrete methods can be reused or overridden.
- Instance fields belong to the object's state; `private` fields of the superclass cannot be accessed directly by the subclass.
- Constructors are **not inherited**. A subclass constructor calls `super(...)` to initialize the superclass part; if there is no suitable no-argument parent constructor, the required constructor must be called explicitly.
- A `final` class cannot have subclasses; a `final` method cannot be overridden. A `static` method with the same name is hidden rather than dispatched like an instance method.
- An abstract class can contain fields, constructors, concrete methods, and abstract methods. A concrete subclass must implement the missing abstract methods.

Only use `extends` when the "is-a" relationship also holds in terms of behavior: code using `Animal` must be able to work with `Dog` without violating `Animal`'s guarantees. If you only want to borrow a helper, composition is usually less restrictive.

## 3. `implements`: A Class Fulfills an Interface Contract

An interface declares capabilities that callers can require, such as `Runnable`, `Comparable`, or the business contract `Payable`. An object of an implementing class can be referenced through the interface; an interface does not provide constructors or instance state.

- Ordinary abstract methods of an interface are `public abstract`; the implementation must be `public` and cannot reduce access privileges.
- A `default` method has a body and can be inherited unless it is overridden or superseded by conflict rules.
- A `static` method is called through the interface name; it does not become an instance method of the implementing class.
- Since Java 9, an interface can declare `private` methods for internal use by other implementations within the interface itself.
- Fields in an interface are `public static final` by default, meaning shared constants rather than individual object state.

An abstract class can `implements` an interface while leaving some abstract methods for its subclasses. A concrete class must fulfill the entire missing abstract contract, either directly or through a valid inherited public implementation.

## 4. Runnable Example: Both `extends` and `implements`

Save the following complete program as `Main.java`:

```java
interface Named {
    String name();
}

interface Payable extends Named {
    double monthlyPay();

    default String label() {
        return name() + " / " + monthlyPay();
    }
}

abstract class Worker {
    private final String workerName;

    protected Worker(String name) {
        this.workerName = name;
    }

    public String name() {
        return workerName;
    }

    public abstract String role();
}

final class Developer extends Worker implements Payable {
    private final double salary;

    Developer(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Developer";
    }

    @Override
    public double monthlyPay() {
        return salary;
    }
}

public class Main {
    public static void main(String[] args) {
        Developer developer = new Developer("Lan", 1200.0);

        Worker bySuperclass = developer;
        Payable byContract = developer;
        Named byParentInterface = developer;

        System.out.println(bySuperclass.role());
        System.out.println(byContract.label());
        System.out.println(byParentInterface.name());
    }
}
```

Run with JDK 17 or later:

```bash
javac Main.java
java Main
```

Stdout:

```text
Developer
Lan / 1200.0
Lan
```

In the example, `Developer extends Worker` to receive the shared implementation; `Developer implements Payable` to fulfill the payment contract; and `Payable extends Named`, so `Developer` is also a subtype of `Named`. `Worker.name()` is public and compatible with `Named.name()`, so this method does not need to be rewritten in `Developer`. The default method `Payable.label()` calls `name()` on the actual object.

## 5. Interface `extends` Interface

A subinterface can combine contracts from multiple interfaces:

```java
interface Identified {
    long id();
}

interface Described {
    String description();
}

interface CatalogItem extends Identified, Described {
    // Inherits both id() and description().
}
```

A concrete class that `implements CatalogItem` must implement both methods, unless it has already inherited a compatible implementation from a superclass. Two interfaces having the same abstract method and compatible signature/return type can share a single implementation; incompatible signatures or return types can make the declaration invalid.

## 6. When Syntax Is Valid but the Contract Is Incomplete

A class using `extends` and `implements` correctly can still fail to compile if an abstract method is missing, a signature is wrong, access privileges are reduced, or conflicting default methods occur. In the example in Section 4, `Worker.name()` is `public`, so it already satisfies `Named.name()` for `Developer` without needing to be rewritten. An overload `name(String)` or a package-private method cannot substitute for `public String name()`.

When the compiler reports an error, check the missing method, return type, `throws`, and access level; then examine the source of the default implementation. The order of writing `implements A, B` does not resolve conflicts. Cases of two competing default methods, class precedence, and `InterfaceName.super.method()` already have runnable examples in the article **Single Class Inheritance and Multiple Interface Inheritance**.

## 7. Common Invalid Declarations

The following lines are compilation error examples; they are commented out so they do not break the valid declarations around them:

```java
class Animal {}
interface Flyable { void fly(); }

// class Bird extends Flyable {}       // Invalid: a class cannot extend an interface.
// class Bird implements Animal {}     // Invalid: implements must take an interface.
// interface FastFlyer implements Flyable {} // Invalid: an interface uses extends.
// class Bird extends Animal, Object {} // Invalid: only one direct superclass.
// class Bird implements Flyable {}    // Invalid if Bird is concrete and does not have fly() yet.

abstract class AbstractBird implements Flyable {}

class Eagle extends AbstractBird {
    @Override
    public void fly() {
        System.out.println("Flying");
    }
}
```

Points to review:

- `class X implements A extends B` has the wrong order; if `B` is a class and `A` is an interface, write `class X extends B implements A`.
- The implementation of an interface method must be `public`.
- `implements` does not automatically provide a body for an abstract method.
- `private` fields of a superclass cannot be accessed directly from a subclass.
- Two default methods with the same signature only cause a conflict when the inheritance rules cannot select a valid implementation.

## 8. Another Use of `extends`: Generic Bounds

In a type parameter declaration, `extends` sets an **upper bound**, not a superclass relationship of the enclosing class:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T extends Number` restricts the generic type argument to `Number` or a suitable subtype. A bound can also be an interface, for example `<T extends Comparable<T>>`; if there are multiple bounds, use `&`, and the class bound (if any) must come first. `? extends Number` is an upper-bounded wildcard, a related syntax with a different role.

Since Java 17, a `sealed` class/interface can restrict the permitted subtypes via `permits`. This adds constraints on subtypes without changing the meaning of `extends` or `implements`.

## 9. Self-Check

1. `interface B extends A` and `class C implements B`: Does C fulfill A? **Yes**, contracts are inherited transitively.
2. Is `class C extends Base implements X, Y` valid? **Yes**, if Base can be inherited from, X/Y are interfaces, and all abstract methods/conflicts are handled.
3. Is `class C implements Runnable` enough to run on a new thread? **Not yet**; a concrete class must implement `public void run()`, and execution requires a `Thread` or an appropriate executor.
4. If two interfaces have matching default methods, does changing their order in `implements` resolve it? **No**; apply the inheritance rules and explicitly override when needed.

**Remember:** `class Child extends Parent`, `class Child implements Contract`, `interface MoreSpecific extends Contract`. For a class that uses both, the order is `extends` then `implements`. Choose class inheritance for a stable "is-a" relationship and an interface for a contract that can be implemented by many kinds of classes.
