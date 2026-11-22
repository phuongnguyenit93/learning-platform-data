# Relationship Between Type, Object, State, and Behavior in Java

## 1. The Big Picture

In object-oriented programming, the four concepts **type**, **object**, **state**, and **behavior** are related to one another, yet not synonymous:

| Concept | Question Answered | Meaning in Java |
| --- | --- | --- |
| **Type** | How is a value/reference allowed to be used? | Classes (`class`), abstract classes (`abstract class`), interfaces (`interface`), `record`, `enum`… define accessible members, type constraints, and operational contracts. |
| **Object** | Which entity exists at runtime? | An instance created from a concrete class; it has its own identity, instance properties, and the ability to execute methods. |
| **State** | What condition is the entity currently in? | The current values of **instance fields** and the data that the object manages. |
| **Behavior** | What can the entity do? | Operations provided by instance methods; they can read, inspect, or modify state and interact with other objects. |

Key relationships:

- **A type describes the capabilities and usage constraints of an object**. An object can be viewed through multiple compatible types.
- **A concrete object owns instance state**. Each object typically has its own instance fields; two references pointing to the *same* object observe the same state.
- **Behavior is how an object exposes or modifies its state**. Encapsulation helps prevent arbitrary state modification.
- **The type of a reference variable is known at compile time; the actual class of the object is known at runtime**. These two pieces of information can differ.

Diagram read along the direction of relationships:

```text
Type / contract
   | specifies which operations may be called
   v
Reference variable ----points to----> Object
                                        | holds
                                        v
                                      State
                                        ^
                                        | is read / updated
                                        |
                                     Behavior
```

Note: primitive data types such as `int` or `boolean` are also types, but primitive values are not objects. What follows focuses on **reference types** and objects.

## 2. A Type Is Not an Object

Let us distinguish between **variable declaration**, **object creation**, and **reference assignment**:

```java
Vehicle vehicle = new Bicycle("City");
```

- `Vehicle` is the **declared type of the variable** `vehicle`; the compiler relies on this type to determine which members can be called directly.
- `new Bicycle("City")` creates **an object** of the concrete class `Bicycle` and runs the constructor to establish its initial state.
- `vehicle` stores a **reference** to the object. Reference assignment does not copy the entire object.
- If `Bicycle extends Vehicle`, a `Bicycle` object can be used wherever a `Vehicle` is expected. This relationship is subtype polymorphism.

For example: a variable of type `Vehicle` can invoke methods declared by `Vehicle`, even when the object it points to is actually a `Bicycle`. To invoke an operation that only exists on the `Movable` interface, you need a reference whose type permits that operation, or a valid type check/cast.

**Do not confuse the "is-a" relationship with "has-a":** `Bicycle extends Vehicle` describes a subtype relationship; whereas `Car` having a field `Engine engine` is an object composition/association (has-a) relationship and does not make `Car` a subtype of `Engine`.

## 3. Complete Example: One Object, Multiple Views, One State

Create a file named `TypeStateDemo.java` with the following contents. The example uses Java 17+, is complete, and compiles standalone:

```java
public class TypeStateDemo {
    interface Movable {
        void move(int steps);
    }

    static abstract class Vehicle {
        private final String name;
        private int distance;

        protected Vehicle(String name) {
            this.name = name;
        }

        public final String name() {
            return name;
        }

        public final int distance() {
            return distance;
        }

        protected final void addDistance(int steps) {
            if (steps < 0) {
                throw new IllegalArgumentException("steps must be >= 0");
            }
            distance = Math.addExact(distance, steps);
        }

        public abstract String kind();
    }

    static final class Bicycle extends Vehicle implements Movable {
        Bicycle(String name) {
            super(name);
        }

        @Override
        public void move(int steps) {
            addDistance(steps);
        }

        @Override
        public String kind() {
            return "bicycle";
        }
    }

    public static void main(String[] args) {
        Bicycle bike = new Bicycle("City");
        Vehicle asVehicle = bike;
        Movable asMovable = bike;

        asMovable.move(3);
        System.out.println(asVehicle.name()
                + " / " + asVehicle.kind()
                + " / " + asVehicle.distance());

        asMovable.move(2);
        System.out.println(bike.distance());
        System.out.println(bike == asVehicle);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac TypeStateDemo.java
java TypeStateDemo
```

Expected output:

```text
City / bicycle / 3
5
true
```

Analysis according to the four concepts:

1. **Type**: `Vehicle` is an abstract class with shared state and the `kind()` contract; `Movable` is an interface declaring the `move(int)` capability; `Bicycle` is a concrete class that extends and implements those contracts.
2. **Object**: there is only **one** `new Bicycle("City")` call. The variables `bike`, `asVehicle`, and `asMovable` all point to **one object**.
3. **State**: `name` is initialized to `"City"` and cannot be reassigned after initialization because it is a `final` field; `distance` starts at `0` and successively becomes `3` and `5`.
4. **Behavior**: `move(3)` and `move(2)` modify `distance`; `distance()` reads the state; `kind()` returns the vehicle type information.
5. **Polymorphism**: calling `asVehicle.kind()` executes the `Bicycle.kind()` implementation at runtime. The result of `bike == asVehicle` is `true` because both references point to the same object.

Encapsulation appears in the `private int distance` field: external code cannot directly assign `distance = -100`. Every update through `move()` must pass the non-negative step check. `Math.addExact` also detects integer overflow and throws an `ArithmeticException`, rather than silently wrapping the value around.

Note on compile-time callability: `asVehicle.move(1)` **does not compile** because `Vehicle` does not declare `move`, whereas `asMovable.move(1)` is valid. This does not contradict the fact that both point to the same object.

## 4. Distinguishing Compile-Time and Runtime Binding

Java checks valid operations based on the **static type** of an expression, and then uses dynamic dispatch for **overridable instance methods** (virtual instance methods).

| Scenario | Determined By | Outcome |
| --- | --- | --- |
| Is writing `reference.someMethod()` allowed? | Static type and access level at compile time | Calling a method not present in the type's contract causes a compile-time error. |
| Which implementation of an **overridden** method runs? | Actual class of the object at runtime | Supports dynamic polymorphism. |
| Which **overloaded** version is selected? | Parameter/expression types at compile time | Does not re-select the overload based on the object's actual class. |
| Accessing a same-named field due to **field hiding**? | Static type of the expression | Fields are not dynamically dispatched like overridden methods. |
| Calling a `static` or `private` method? | Class rules/accessibility, not dynamic overriding | `static` belongs to the class; `private` is not overridden. |

Example illustrating a **hidden field** and an **overridden method**. Save to `DispatchDemo.java`:

```java
class Parent {
    String label = "Parent.field";

    String label() {
        return "Parent.method";
    }
}

class Child extends Parent {
    String label = "Child.field";

    @Override
    String label() {
        return "Child.method";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.label);
        System.out.println(value.label());
    }
}
```

```bash
javac DispatchDemo.java
java DispatchDemo
```

```text
Parent.field
Child.method
```

`value.label` reads the field resolved by the `Parent` type, whereas `value.label()` invokes the overridden method of `Child`. In real-world design, prefer `private` fields and access them through methods rather than declaring two fields with the same name as in this example.

With **overloading**, if both `print(Object)` and `print(String)` exist, a variable expression with the declared type `Object text = "hi";` will select `print(Object)` when you write `print(text)`; merely seeing that the object is a `String` at runtime does not change the selected overload.

## 5. How Do Class, Abstract Class, and Interface Express This Relationship?

### Concrete Class

- Can create objects with `new` (if the constructor and access rules permit).
- Declares instance fields, constructors, and methods that operate on data; can implement interfaces and extend a superclass.
- Choose appropriate access modifiers (`private`, `protected`, `public`) to protect the object's invariants.

### Abstract Class

- You **cannot** directly instantiate an `abstract` class with `new`, but its state and behavior still become part of objects of concrete subclasses.
- Can have instance fields, constructors, implemented methods, and `abstract` methods that concrete subclasses must implement.
- Useful when subtypes have **shared state and shared logic**, such as `Vehicle.name`, `Vehicle.distance`, and `Vehicle.addDistance()`.
- Java allows only one direct superclass (even if the superclass is abstract), so avoid using inheritance merely to reuse a few lines of code.

### Interface

- Describes a **capability contract**: what operations an object supports, such as `Movable.move(int)`.
- Has no **instance fields** or constructors to store per-object state. Fields declared in an interface are `public static final` by default (constants belonging to the interface), **not the state of each object**.
- Can have `abstract`, `default`, and `static` methods; Java 9+ also supports `private` methods to assist implementation within the interface. A `default` method has a method body, yet still does not introduce instance fields for the interface.
- A class can `implements` multiple interfaces. An interface can `extends` multiple interfaces.
- Useful when unrelated classes share a common capability; for example, `Bicycle` and `Robot` both `implements Movable` while managing their state using different structures.

**Key takeaway:** an interface defines how **behavior is observed/invoked**; a concrete class decides **how state is stored and how behavior is carried out**. However, an interface is not necessarily completely "implementation-free": a `default` method can share logic built on top of the contract's operations.

## 6. State, Invariants, and Object Lifecycle

### Where Does State Live?

- **Instance fields** belong to each individual object: two `new Bicycle("City")` calls create two objects with independent `distance` fields.
- **Static fields** belong to the class and are shared within the loaded class context, so they do not represent the individual state of each object.
- **Local variables/parameters** exist within the scope of an invocation and do not automatically become persistent state of the object.
- Reference fields are also part of state: for example, `private Engine engine;` stores a reference to another object. State can indirectly depend on the graph of related objects.

### Behavior Protects Invariants

An **invariant** is a condition that must always hold true at valid observation points of an object. For example, with an odometer: `distance >= 0`. Good design maintains invariants by:

1. Establishing a valid initial state in the constructor.
2. Keeping sensitive fields `private`.
3. Validating inputs before updating and handling errors clearly.
4. Centralizing changes through methods with domain-meaningful names, such as `move()` or `deposit()`.
5. Not returning an internal mutable object in a way that lets callers modify state while bypassing checks (when needed, return a copy or a read-only type).

A method does not necessarily modify state: `distance()` only reads; `kind()` provides information. Conversely, a method can cause external side effects (writing files, making network calls) without modifying instance fields; therefore, **behavior is broader than changing state**.

`final` must be understood properly: a primitive field `final int x` cannot be reassigned; however, `final List<String> items` only fixes the **reference**, while the list object itself can still be mutated if it is mutable.

### Two References and Two Objects

```java
Bicycle first = new Bicycle("A");
Bicycle alias = first;
Bicycle second = new Bicycle("A");
```

The snippet above uses the `Bicycle` class defined in the previous example and is **not a standalone program**.

- `first == alias` is `true`: same object identity; updates through one variable are observed through the other.
- `first == second` is `false`: two `new` calls create two distinct objects even with the same name and the same initial distance.
- `==` between two reference variables compares **reference identity**; `equals()` compares according to the class's contract. If a class does not override `equals()`, the default behavior from `Object` still compares identity.
- Assigning `alias = second` only changes which object the `alias` variable points to; it does not alter `first` or `second`.

## 7. From Problem Model to Java Design

For example, an ordering system can divide responsibilities as follows:

| Perspective | Example | Design Decision |
| --- | --- | --- |
| Domain types | `Order`, `PaymentMethod` | Define valid operations and clear contracts. |
| Concrete objects | A specific order, a specific payment gateway object | Each entity has an appropriate lifecycle and identity. |
| State | Order ID, line items, `CREATED/PAID/CANCELLED` status | Encapsulate data and restrict invalid states. |
| Behavior | `addItem()`, `pay()`, `cancel()` | Validate state transitions and coordinate with other objects. |

For instance, the rule that a cancelled order must not be paid is a **business invariant rule**. It should be enforced inside behavior such as `pay()`, rather than letting external code directly assign `order.status = PAID`.

When deciding whether to use an **abstract class** or an **interface**, ask:

- Do the types share *actual state* and the same way of maintaining invariants? If so, an abstract superclass may be appropriate.
- Do the types only share *capabilities* while storing data differently? An interface usually expresses the contract better.
- Can **composition** (containing/delegating to an object) be used instead of inheritance to avoid tight coupling to a superclass structure?
- Does the object need to be mutable? If not, consider an immutable object: initialize all state in the constructor with no methods that mutate state; `record` is convenient for simple data models, but **does not automatically make every referenced component deeply immutable**.

## 8. Common Misconceptions and Mistakes

1. **"Whatever type a variable has, the object must belong to that exact class."** False: a `Vehicle` variable can point to a `Bicycle` object; the condition is type compatibility.
2. **"Assigning a reference variable creates a copy of the object."** False: regular assignment only copies the reference value; copying state requires an explicit copying strategy.
3. **"Interfaces have nothing to do with state."** Incomplete: an interface does not hold instance fields, yet the behavior defined by the interface can certainly read or modify the state of the object implementing it.
4. **"An abstract class cannot have constructors or fields."** False: an abstract class can initialize its inherited portion of state; you simply cannot directly instantiate the abstract class itself.
5. **"Every member is polymorphic at runtime."** False: hidden fields, `static` methods, `private` methods, and overloading follow different rules from instance method overriding.
6. **"Having getters/setters for every field already means good encapsulation."** Not necessarily: unrestricted setters can break invariants. Domain behavior such as `withdraw(amount)` expresses and enforces rules more clearly than `setBalance(value)`.
7. **"A `final` reference means an immutable object."** False: the reference cannot be reassigned, but the state of the referenced object can still change.
8. **"Mutable objects are automatically thread-safe."** False: sharing a mutable object across threads requires proper synchronization, immutability, or thread-safe mechanisms. The `Bicycle` example above does **not** guarantee thread safety.

## 9. Self-Check

**Question 1.** Given `Vehicle v = new Bicycle("X");`, what are the static type and the runtime class?

**Answer:** the static type is `Vehicle`, and the runtime class is `Bicycle`. Only members visible through `Vehicle` can be called directly, yet instance methods overridden by `Bicycle` will execute `Bicycle`'s version.

**Question 2.** If two variables point to the same `Bicycle` and `move(4)` is called through the first variable, what does the second variable see when reading `distance()`?

**Answer:** the state has increased by 4 compared to before (if the call succeeded), because only one object is shared.

**Question 3.** Why does `Movable` not directly store a separate `distance` for each object?

**Answer:** interfaces cannot have instance fields; an implementing class like `Bicycle` or a superclass like `Vehicle` must store the state.

**Question 4.** If you want to add a `Robot` that can `move()` but is not a vehicle, what should you use?

**Answer:** make `Robot implements Movable` and manage its own state. You should not force `Robot extends Vehicle` just to obtain the move method.

**Key point:** **type** is the usage contract, **object** is the entity carrying identity, **state** is the entity's current data, and **behavior** is the set of operations that act on or observe that entity. Separating these four roles helps you understand polymorphism, encapsulation, and choosing among `class`, `abstract class`, and `interface` in Java design.
