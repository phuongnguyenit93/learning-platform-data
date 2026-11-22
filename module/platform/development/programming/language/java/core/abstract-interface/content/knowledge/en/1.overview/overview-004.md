# The Role of Abstract Classes and Interfaces in Java

## 1. The Problem the Two Mechanisms Solve

When multiple objects share common traits, Java lets you describe the **stable part** in an abstract type and let each concrete type decide the **varying part**. As a result, calling code can work with the common type instead of knowing each implementation class.

- **An abstract class** is appropriate when subclasses truly belong to the same family, share state or processing logic, yet still need certain steps provided by the subclasses.
- **An interface** describes a **capability/behavior contract** that multiple classes—even classes outside the same inheritance hierarchy—can implement.
- Both support **polymorphism**: a variable whose type is the parent class or interface can reference an object of an implementation class; calling an instance method runs the version appropriate for the actual object.

Conceptual example: multiple subscription types share a subscriber and the same fee-reporting workflow, so you can use an abstract class `Subscription`. Sending notifications can happen via email, console, or another system, so you can model it with an interface `Channel`. These are **two independent axes of change**.

## 2. Abstract Classes: Sharing a Foundation and Defining a Processing Framework

Declare a class with the `abstract` keyword:

```java
abstract class Vehicle {
    private final String id;

    protected Vehicle(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }

    public abstract int maxSpeed();
}
```

The snippet above is a type declaration, not a standalone program with `main`. It illustrates that an abstract class can contain **instance data**, **constructors**, **implemented methods**, and **abstract methods**.

Key characteristics to understand:

1. You cannot directly instantiate `new Vehicle("V1")`. You must create an object of a concrete subclass.
2. The abstract class's constructor is still invoked as part of the subclass initialization chain; it can establish and validate shared invariants.
3. An `abstract` method declares only a signature without a body; a concrete subclass must implement the missing abstract methods. A subclass that has not implemented all of them must remain `abstract`.
4. An abstract class can also declare no `abstract` methods at all: the `abstract` keyword still prevents direct instantiation and expresses that this is a base class.
5. You can use `private`, `protected`, `public`, `static`, `final`, concrete methods, and instance fields according to standard Java class rules. A method cannot be both `abstract` and `final` because one requires subclasses to implement it while the other forbids overriding.
6. A Java class has only **one direct superclass** (`extends` a single class); abstract classes do not change this limitation.

An important usage is **Template Method**: the parent class keeps the order of common steps, while abstract methods provide extension points. When the workflow must remain uniform, you can mark the coordinating method `final` and allow subclasses to change only clearly defined steps.

## 3. Interfaces: Contracts for Classes to Collaborate

Example:

```java
interface Payable {
    int amount();

    default boolean isFree() {
        return amount() == 0;
    }
}
```

`Payable` requires the implementing class to provide `amount()`; the `isFree()` method is shared default behavior.

Important rules in Java 17+:

- Regular methods declared in an interface are implicitly `public abstract`. An implementing class must use `public` visibility for the overridden method; it cannot narrow it to package-private or `protected`.
- An interface can have `default` methods (with a body and inherited), `static` methods (called via the interface name), and `private`/`private static` methods (supporting logic reuse inside the interface). Not every interface method is abstract.
- Fields declared in an interface are always `public static final`, meaning constants; an interface **has no instance fields or constructors** to hold per-object state.
- A class can `implements` **multiple interfaces**, while an interface can `extends` multiple interfaces. This enables combining independent capabilities without multiple class inheritance.
- `default` does not turn an interface into an ideal place to hold all shared processing or state. It is useful for providing default behavior closely tied to the contract; implementing classes can still override it.
- An interface can be the type of a parameter, variable, field, or return type. Consequently, a component accepting `Payable` only needs to know `amount()`, without needing to know which concrete class provides it.

Example of a class with two capabilities:

```java
interface Printable {
    void print();
}

interface Exportable {
    void export();
}

final class Report implements Printable, Exportable {
    @Override
    public void print() {
        System.out.println("Print report");
    }

    @Override
    public void export() {
        System.out.println("Export report");
    }
}
```

These declarations compile as a group of types, though they have no `main` to run standalone. `Report` adopts two behavioral contracts without inheriting from two parent classes.

## 4. Comparison and Relationship Between the Two Mechanisms

| Criterion | Abstract class | Interface |
| --- | --- | --- |
| Design question | "What kind of thing are these classes together, and what foundation do they share?" | "What capability can this object perform?" |
| Typical relationship | `extends` one parent class | `implements` one or more interfaces |
| Instance state | Can contain instance fields and constructors | No instance fields or constructors; fields are constants |
| Shared processing code | Concrete methods, `protected`, `final`, template method | `default`, `static`, `private` per interface rules |
| Subclass requirement | Implement missing abstract methods | Implement missing abstract methods from the interfaces |
| Flexibility | Suited for class families with shared structure | Collaboration across different class families; easy to swap implementations |
| Number of direct relationships | One parent class | Multiple interfaces |

**The two mechanisms can be combined:** an abstract class can `implements` one or more interfaces and leave it to subclasses to complete the contract. A concrete class can also both `extends` an abstract class and `implements` multiple interfaces.

The key takeaway is to **choose based on the design relationship**, not on whether an interface is "more powerful" or an abstract class is "older". If you only need to advertise a capability so callers depend on a common type, an interface is usually the simpler choice. If you genuinely need to share valid state and coordinate lifecycle/behavior among classes in the same family, an abstract class has clear value.

## 5. Runnable Java 17+ Example: Using Both an Abstract Class and an Interface

Save the following code to **`Demo.java`** (without a `package` declaration):

```java
interface Channel {
    void send(String message);

    default void welcome() {
        send("Welcome!");
    }
}

abstract class Subscription {
    private final String subscriber;

    protected Subscription(String subscriber) {
        if (subscriber == null || subscriber.isBlank()) {
            throw new IllegalArgumentException("Subscriber is required");
        }
        this.subscriber = subscriber;
    }

    public final void report(Channel channel) {
        channel.send(subscriber + ": " + monthlyPrice() + " USD/month");
    }

    protected abstract int monthlyPrice();
}

final class FreeSubscription extends Subscription {
    FreeSubscription(String subscriber) {
        super(subscriber);
    }

    @Override
    protected int monthlyPrice() {
        return 0;
    }
}

final class PremiumSubscription extends Subscription {
    PremiumSubscription(String subscriber) {
        super(subscriber);
    }

    @Override
    protected int monthlyPrice() {
        return 15;
    }
}

final class ConsoleChannel implements Channel {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}

public class Demo {
    public static void main(String[] args) {
        Channel channel = new ConsoleChannel();
        Subscription[] plans = {
            new FreeSubscription("Lan"),
            new PremiumSubscription("Minh")
        };

        for (Subscription plan : plans) {
            plan.report(channel);
        }
        channel.welcome();
    }
}
```

Compile and run from the directory containing the file (JDK 17 or later):

```bash
javac Demo.java
java Demo
```

Expected output on stdout:

```text
Lan: 0 USD/month
Minh: 15 USD/month
Welcome!
```

Step-by-step execution flow:

1. Both `new FreeSubscription("Lan")` and `new PremiumSubscription("Minh")` go through the `Subscription` constructor, so the shared subscriber-name check is not duplicated in each subclass.
2. The `Subscription[]` array holds multiple implementation classes. The `report()` method is the same shared workflow; the `monthlyPrice()` call is dispatched according to the **actual type** of the element: `0` for `FreeSubscription` and `15` for `PremiumSubscription`.
3. `report(Channel channel)` depends only on the notification-sending contract. Therefore, `ConsoleChannel` can be replaced with another implementation without modifying `Subscription` or its two subclasses.
4. `channel.welcome()` uses the interface's `default` method, then calls the actual implementation's `send()` to print the final line.
5. `final` on `report()` preserves the processing order designed by the base class; subclasses only decide the fee via the `monthlyPrice()` extension point.

This is an example of **polymorphism + controlled inheritance + contract-oriented programming**. The part that depends on shared structure uses an abstract class; the part that communicates with an external service uses an interface.

## 6. When Should You Choose Which?

**Choose an abstract class when:**

- Subclasses have a clear "is-a" relationship, such as variants of a domain object.
- They need the same instance state protected by a constructor and shared invariants.
- An algorithm has a stable skeleton of steps, while a few steps can be implemented differently by subclasses.
- You have a solid reason to maintain a single base class and accept the coupling introduced by inheritance.

**Choose an interface when:**

- You need to define a contract for multiple implementations not in the same class family, such as `Comparable`, `Runnable`, or an application interface like `Channel`.
- Client code needs to swap implementations via parameters, dependency injection, or testing with mock objects.
- A class must combine multiple independent capabilities (`Printable`, `Exportable`, …).
- The contract is small and behavior-focused; there is no need to share instance state.

**Consider composition (containment and delegation) when:** you only want to reuse processing logic, and an "is-a" relationship does not hold. For example, `OrderService` *has a* `Channel` to send events; it does not necessarily have to *be a* `Channel`. Inheriting from a base class too early makes changing dependencies and separating responsibilities harder later on.

A common way to organize this is **using an interface as the client API and an abstract class to provide an optional base implementation**. For example, you might have `interface Storage` and `abstract class BaseStorage implements Storage`; an implementation is free to extend `BaseStorage` or implement `Storage` directly. The base class is an optional convenience, not a requirement of the contract.

## 7. Common Pitfalls

**Confusing `extends` with `implements`.** A class inherits from another class using `extends`; a class implements an interface using `implements`. An interface extends another interface using `extends`.

**Assuming an interface never has any implementation.** Since Java 8, interfaces have `default`/`static` methods, and since Java 9, `private` methods. However, interfaces still have no instance state or constructors.

**Assuming an abstract class has no constructor or that every method must be abstract.** Both are false. An abstract class can contain constructors, fields, concrete methods, and even no abstract methods at all.

**Narrowing visibility when implementing an interface.** Given `interface Task { void run(); }`, the corresponding method in the implementing class must be `public void run()`. Writing `void run()` (package-private) causes a compile error.

**Using inheritance just to reuse a few lines of code.** If two types are not truly substitutable for each other, a parent–child relationship can violate the Liskov Substitution Principle. Consider extracting shared logic into a collaborator object or an appropriate utility.

**Creating overly large interfaces.** An interface that forces every implementation to carry unrelated methods makes the contract hard to use and hard to test. Prefer small contracts with clear responsibilities (Interface Segregation).

**Two interfaces with `default` methods sharing the same signature.** If a class implements both interfaces that provide conflicting default methods, that class must override the method itself to resolve the conflict. For example:

```java
interface A {
    default String name() {
        return "A";
    }
}

interface B {
    default String name() {
        return "B";
    }
}

final class C implements A, B {
    @Override
    public String name() {
        return A.super.name() + B.super.name();
    }
}
```

This snippet is a type-declaration example, not a program with `main`. Calling `new C().name()` returns the string `"AB"`. You cannot rely merely on the listing order `implements A, B` for Java to automatically pick one default method.

**Putting mutable data into interface fields.** Every interface field is `public static final`, not per-instance data. Data belonging to individual objects should be placed in an appropriate class or record.

## 8. Self-Check Questions

1. Why does `Subscription` need a constructor even though a `Subscription` object cannot be created directly?
2. When adding `EmailChannel implements Channel`, does `Subscription.report()` need to be modified? Why?
3. If `FreeSubscription` does not implement `monthlyPrice()`, how must that class be declared?
4. When does adding a parent abstract class solely to reuse code make a design less flexible?
5. Why is the class `C implements A, B` in the last example required to override `name()`?

**Self-check answers:** (1) to initialize/validate shared state when a subclass is instantiated; (2) no, because `report()` accepts `Channel`; (3) it must be `abstract`, or it will cause a compile error if it is a concrete class; (4) when the classes do not have a valid is-a / mutual substitutability relationship; (5) because two default methods with the same signature cause a conflict.

Remember the design selection rule: **abstract classes share the foundation of a class family; interfaces advertise capabilities and serve as connection points between implementations**. Both can be combined when each mechanism genuinely addresses a distinct need.
