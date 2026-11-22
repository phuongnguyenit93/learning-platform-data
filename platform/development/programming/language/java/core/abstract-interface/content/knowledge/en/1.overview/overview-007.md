# Prerequisites and Recommended Learning Sequence — Abstract Class & Interface (Java)

## 1. Learning Objectives

This is a roadmap for preparing and learning the topic of `abstract class` and `interface` in an orderly way. The focus is on **what to learn first, what to learn next, why that knowledge is needed, and when your foundation is solid enough to move forward**. Beginners do not need to understand these two concepts in advance.

After completing this roadmap, you should be able to explain on your own the relationship between inheritance, overriding, polymorphism, abstract classes, and interfaces; write working examples on JDK 17+; and have a sound basis when choosing a parent class, an interface, or a combination of both.

## 2. Prerequisites

| Topic | What You Need to Know | How to Verify |
| --- | --- | --- |
| Java syntax and tooling | Variable declarations, data types, `if`, methods, matching the file name with the `public class` name, using `javac`/`java`. | Create, compile, and run a `Hello` program. |
| Classes and objects | `class`, `new`, fields, methods, constructors, `this`; distinguishing between type definitions and runtime objects. | Write `Student` with a name, a constructor, and a method to read the name. |
| Encapsulation | `private`, `protected`, `public`, package-private; responsibility for managing state. | Hide a field with `private` and provide an appropriate accessor method. |
| Class inheritance | `extends`, the "is-a" relationship, `super(...)`, inherited members. | Write `Dog extends Animal` and call the `Animal` constructor. |
| Method overriding | `@Override`, method signatures; distinguishing overriding from overloading. | Override `sound()` in `Dog`; explain why creating a `sound(int)` method is overloading. |
| Polymorphism | `Animal a = new Dog();`; the reference type governs the API visible at compile time, while the actual object determines which overridden instance method executes. | Predict the result of `a.sound()` and run it to confirm. |

**Minimum review order:** Java syntax → classes/objects → constructors and encapsulation → inheritance → overriding → polymorphism. If you cannot explain `Animal a = new Dog();`, reinforce that part before learning abstract classes or interfaces.

**Not yet required:** generics, advanced collections, streams, reflection, Spring, dependency injection, and design patterns. These topics are useful later, but they are not starting prerequisites.

### Three Foundational Concepts to Distinguish

- **Class/type and object:** `Animal a` is a reference variable of type `Animal`; `new Dog()` creates an object of type `Dog`. An object can be referenced through the parent types or interfaces that it satisfies.
- **Overriding and overloading:** overriding provides a new implementation for an inherited instance method with a matching signature; overloading refers to methods with the same name but different parameter lists.
- **Abstraction and polymorphism:** abstraction defines the required capabilities, whereas polymorphism allows the same call to behave differently depending on the concrete object. You need to understand both, rather than merely memorizing the `abstract` and `interface` syntax.

## 3. Recommended Learning Sequence

| Stage | Content | Readiness Indicator |
| --- | --- | --- |
| 0. Tooling and OOP basics | Running Java 17+, classes, objects, constructors, fields, methods, encapsulation. | Compile a small example on your own without copying faulty commands. |
| 1. Inheritance and polymorphism | `extends`, `super`, `@Override`, parent reference types, runtime dispatch. | Correctly explain which method is called via `Animal a = new Dog();`. |
| 2. The need for contracts | Identifying common behavior that each concrete type must implement differently. | Describe "every vehicle moves, but how it moves depends on the vehicle". |
| 3. Abstract class | `abstract class`, abstract methods, constructors, state, and implemented methods. | Create a concrete subclass that implements all abstract methods. |
| 4. Interface | `interface`, `implements`, a class implementing multiple interfaces, interface-typed variables and parameters. | Have two independent classes satisfy the same contract. |
| 5. Combining and choosing | A class `extends` one class and `implements` multiple interfaces; comparing with composition. | Explain why each mechanism is chosen in a specific design. |
| 6. Modern Java features | Interface `default`, `static`, and `private` methods; default conflicts; functional interfaces when learning lambdas. | Read modern code without confusing a contract with instance state. |
| 7. Integrated practice | Designing an example from scratch, predicting output, fixing compilation errors, evaluating designs. | Write, run, and explain your own solution. |

This is a **knowledge-dependency sequence**, and you do not need to spend equal time on each stage. You can cover several steps in a single session if your OOP foundation is already solid; if you have not yet met the indicator in the last column, practice more before moving to the next step.

### Stages 1–2: Why Learn Polymorphism First?

Start with two regular classes, `Animal` and `Dog`; have `Dog` override `sound()`. With `Animal a = new Dog();`, the call `a.sound()` uses `Dog`'s overridden implementation. The compiler validates the call based on the `Animal` type; at runtime, the JVM selects the instance method version matching the actual object.

From there, ask the question: if every vehicle must have `move()` yet there is no sensible common way to move, how do you declare that requirement without writing a dummy method body? This is why you learn abstract methods.

### Stage 3: Learning Abstract Classes

An **abstract class** is suitable when types of objects belonging to the same family share a common skeleton (state, constructors, shared methods), while still leaving part of the behavior for subclasses to decide.

Make sure you grasp the following points:

1. `abstract class Vehicle` can contain fields, constructors, methods with bodies, and `abstract` methods without bodies.
2. It cannot be instantiated directly with `new Vehicle(...)`, but you can declare a variable of type `Vehicle` referencing a subclass object.
3. An abstract class constructor is invoked during the construction of a subclass object; `super(...)` allows initializing the shared part.
4. A **non-abstract** subclass must implement any inherited abstract methods that are still unimplemented.
5. `abstract` and `final` cannot be used together on a class: a final class does not allow inheritance.

**Milestone:** write `abstract class Shape` yourself with the method `abstract double area()`, then create `Rectangle` and `Circle` implementing the area calculation. Be able to explain why `Shape s = new Rectangle(...)` is valid even though `new Shape()` is invalid.

### Stage 4: Learning Interfaces

An **interface** represents a capability contract across multiple types of objects. For example, a vehicle, a parcel, or a device can all have an identifier without sharing a business-domain parent class. `Identifiable` with the `id()` method describes that capability.

Rules to remember:

- A class uses `implements` to implement an interface. A Java class can directly `extends` at most one class, but it can `implements` multiple interfaces. An interface can `extends` multiple interfaces.
- Regular abstract methods of an interface are implicitly `public abstract`; the implementing class must not reduce their access level.
- Fields declared in an interface are implicitly `public static final` (constants), not separate mutable per-instance fields.
- An interface does not have constructors like a class to instantiate objects directly; an interface-typed variable references an object of an implementing class.
- An interface can have `default`, `static` (Java 8+), and `private` (Java 9+) methods. Learn these forms **after** understanding `implements` and basic polymorphism.

**Milestone:** write `interface Printable { void print(); }`, have both `Invoice` and `Report` implement it, and then pass each object to a method that takes a `Printable` parameter. The caller only needs to know the `print()` contract, without needing to know the concrete class.

### Stage 5: Combining Them in a Runnable Java 17 Example

Create the file **`LearningPathDemo.java`** and save it in UTF-8:

```java
interface Identifiable {
    String id();

    default String label() {
        return "ID-" + id();
    }
}

abstract class Vehicle {
    private final String name;

    protected Vehicle(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String move();
}

final class Bicycle extends Vehicle implements Identifiable {
    private final String id;

    Bicycle(String name, String id) {
        super(name);
        this.id = id;
    }

    @Override
    public String move() {
        return name() + " đang chạy bằng sức người";
    }

    @Override
    public String id() {
        return id;
    }
}

public class LearningPathDemo {
    public static void main(String[] args) {
        Bicycle bicycle = new Bicycle("Xe đạp", "B01");
        Vehicle vehicle = bicycle;
        Identifiable identifiable = bicycle;

        System.out.println(vehicle.move());
        System.out.println(identifiable.label());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 LearningPathDemo.java
java LearningPathDemo
```

Output:

```text
Xe đạp đang chạy bằng sức người
ID-B01
```

Explanation of each role:

- `Vehicle` holds the name state and the `move()` contract for the same vehicle family. `Bicycle` calls the parent class constructor via `super(name)` and implements `move()`.
- `Identifiable` describes the capability of having an identifier, independent of the vehicle family. The `label()` method is pre-implemented using `default`.
- `Bicycle` is simultaneously a `Vehicle` and an `Identifiable`. The variables `bicycle`, `vehicle`, and `identifiable` all reference **the same object**.
- The call `vehicle.move()` executes `Bicycle`'s implementation thanks to overriding and polymorphism. `identifiable.label()` runs the default method, which then calls `id()` on the `Bicycle` object.
- This example intentionally includes both an abstract class and an interface for practice. A real-world design might need only an interface or only a regular class.

If you modify the code and encounter an error, read the first `javac` message first: common mistakes include missing `public` when implementing an interface method, missing `@Override` with the matching signature, failing to implement all abstract methods, or mismatching the file name and the `public class` name.

### Stage 6: Expanding in a Logical Order

1. **`default` methods:** have a body and provide a default implementation for instances; implementing classes can override them.
2. **`static` methods:** belong to the interface and are called via the interface name, rather than being inherited as regular instance methods.
3. **`private` methods:** are used to reuse internal logic among methods with bodies inside the interface; they are not part of the public contract.
4. **Default conflicts:** two interfaces providing default methods with the same signature typically force the implementing class to override the method itself to resolve the conflict. A matching concrete instance method from a superclass takes precedence over a default method from an interface.
5. **Functional interfaces and lambdas:** an interface with a single abstract method works with lambdas; `@FunctionalInterface` helps verify that intent at compile time. This is a follow-on topic and is not yet needed to understand basic interfaces.
6. **Finally**, explore `sealed` classes/interfaces (Java 17), designing small contracts, and principles such as SOLID if required by the scope of your study.

## 4. Practical Selection Guidelines

| Situation | Direction to Consider |
| --- | --- |
| Classes in the same family have shared state, validation rules, and common processing. | An `abstract class` can provide a shared skeleton and extension points. |
| Objects from different families need to expose the same capability. | An `interface` represents an independent contract. |
| A class needs shared parts from a parent while also fulfilling multiple different capabilities. | `extends` one class and `implements` multiple interfaces. |
| You only need to reuse a piece of functionality without a genuine is-a relationship. | Consider **composition/delegation** instead of forcing inheritance. |
| Calling code only needs a few guaranteed operations and does not care about the implementing class. | Use interface-typed parameters or variables where appropriate. |

There is no absolute rule that "abstract classes are always better" or "interfaces are always better." Answer these questions instead: **what is the shared essence of the object family, what is merely a capability, and what truly needs shared implementation or state?** Supporting `default` methods in interfaces does not turn interface fields into per-instance state.

## 5. Progressive Exercises and Completion Criteria

**Exercise 1 — Polymorphism review:** Write `Animal` with `sound()`, and two classes `Cat` and `Dog` overriding it. Have an `Animal` variable reference each object in turn, then predict and verify the output. Completed when you can explain runtime dispatch.

**Exercise 2 — Abstract class:** Write `Shape`, `Rectangle`, and `Circle` as above. Add a parent class constructor and a shared method with a body. Completed when you can explain which part is shared and which part each subclass must implement.

**Exercise 3 — Interface:** Write `Printable`, `Invoice`, `Report`, and the `runPrint(Printable item)` method. Completed when you can add a new document type without modifying the code that calls `runPrint`.

**Exercise 4 — Combination:** Add `Car extends Vehicle implements Identifiable` to the `LearningPathDemo` example. If you need to represent charging capability, create `Rechargeable` only for the appropriate class(es). Completed when you can explain why not every `Vehicle` is `Rechargeable`.

**Exercise 5 — Design problem:** For (a) vehicles sharing common speed-check rules, (b) invoices and reports both having PDF export capability, and (c) an object needing logging functionality, choose between an abstract class, an interface, or composition and state your reasoning based on the business domain.

## 6. Misconceptions to Catch Early

- Calling an interface merely a "class with no methods that have bodies": modern interfaces have `default`, `static`, and `private` methods; their core value remains the type contract.
- Using `extends` when a class implements an interface: a class **`implements` an interface**; an interface `extends` an interface.
- Assuming an abstract class is useless because you cannot call `new` on it: subclasses still use its constructors, state, and concrete methods.
- Writing an interface implementation with default access: public interface methods must be implemented as `public` methods.
- Confusing the reference type with the actual object type: the reference type restricts the API at compile time; overridden instance method calls depend on the actual object.
- Trying to turn constants in an interface into per-object fields: interface fields are always `public static final`.
- Using inheritance just to save a few lines of code: this easily creates a false is-a relationship; consider composition.
- Jumping straight into default conflicts, lambdas, or sealed types before understanding `implements` and polymorphism: advanced details can easily obscure the fundamentals.

## 7. Self-Assessment Before Moving to the Next Lesson

Answer the following questions on your own (and prove them with code if needed):

1. Why does an abstract class have constructors even though it cannot be instantiated directly?
2. What must a concrete class do when it inherits an abstract method that has not yet been implemented?
3. Why can a `Bicycle` object be assigned to both `Vehicle` and `Identifiable` variables?
4. How does `extends` on a class differ in meaning from `implements` on an interface?
5. When do you need an independent contract, and when do you genuinely need to share parent class state?
6. Do `default` methods change the rule for interface fields?
7. Can you accurately predict the output, compile, and explain the `LearningPathDemo` example?

If you cannot answer these yet, go back to the nearest link in the chain **classes/objects → inheritance/polymorphism → abstract classes → interfaces → combination**. If you can answer them, you are ready to dive deeper into syntax, inheritance limits, method conflicts, and designing APIs with abstraction.
