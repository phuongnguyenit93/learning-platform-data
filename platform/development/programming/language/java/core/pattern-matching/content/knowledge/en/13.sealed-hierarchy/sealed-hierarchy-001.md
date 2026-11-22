# Sealed class and sealed interface in Java

## 1. What is a sealed hierarchy?

In Java, a regular class can be inherited by subclasses that the superclass author did not list in advance (as long as there are no other barriers such as `final` or access modifiers). A regular `interface` can also be implemented by many classes. This is good for systems that need free extensibility, but causes inconvenience when **the domain only allows a fixed set of variants**.

**Sealed classes** and **sealed interfaces** let you explicitly declare which types are permitted to **directly extend or implement** a parent type. Since Java 17, both are official language features (JEP 409). This is a way to model a controlled *type hierarchy*, commonly referred to as a *sealed hierarchy*.

For example, a business operation result that is only allowed to be a success or a failure:

```java
sealed interface Result permits Success, Failure {}

record Success(int value) implements Result {}

record Failure(String message) implements Result {}
```

This is an **illustrative code snippet**, placing the declarations in the same compilation unit and using Java 17+. Here, only `Success` and `Failure` are permitted to implement `Result` **directly**. Each `record` is itself a `final` type and cannot be extended by other classes.

Key benefits:

- **Model constraints:** The set of direct variants is declared in the source code.
- **Readable design:** Looking at `permits` immediately shows the direct child branches that the author allows.
- **Pattern matching support:** Starting in Java 21, `switch` can analyze the variant set of a sealed type to check **exhaustiveness** (whether all cases have been covered).
- **Fewer unintended extensions:** Types outside the permitted set cannot arbitrarily inherit directly.
- **Does not replace data validation:** Sealed restricts the type hierarchy structure; it **does not prove that an object or component cannot be `null`**, nor does it guarantee that the object's business properties are valid.

This lesson focuses on **syntax, inheritance rules, and the differences between sealed classes and sealed interfaces**; pattern matching is presented to show the practical purpose of the design.

## 2. Version requirements and background knowledge

| Component | First stable version | Notes |
| --- | --- | --- |
| `sealed`, `permits`, `non-sealed` | Java 17 | Official feature, no preview needed |
| `record` | Java 16 | Can `implements` a sealed interface and is `final` by default |
| `instanceof Type name` | Java 16 | Can be used with sealed classes/interfaces since Java 17 |
| Pattern matching in `switch` | Java 21 | Enables type cases, `when`, record patterns, and exhaustiveness checking |
| Record patterns like `case Success(int n)` | Java 21 | Deconstructs record data in patterns |

In the examples, JDK 17 is sufficient for defining a sealed hierarchy. Snippets with `switch` patterns use Java 21 or later and only use finalized features.

Check the JDK in use:

```bash
java -version
javac -version
```

The command `javac --release 17` helps verify the Java 17 parts; `javac --release 21` is used for Java 21 `switch` pattern examples. Having a newer JDK does not mean a project configured with `--release 17` will automatically support Java 21 syntax.

## 3. Declaring a sealed class

General syntax:

```java
public abstract sealed class Shape permits Circle, Rectangle {
    public abstract double area();
}
```

This is an **illustrative declaration**; the subclasses `Circle` and `Rectangle` need to be defined to directly extend `Shape` under valid module/package conditions. The components:

- `sealed`: the class restricts its **direct subclasses**.
- `permits Circle, Rectangle`: names the classes permitted to `extends Shape` directly.
- `abstract`: optional; a sealed class **can be abstract or concrete**, it does not have to be abstract.
- The `area()` method shows that a sealed class is still a regular Java class with respect to fields, constructors, and behavior.

A valid implementation:

```java
abstract sealed class Shape permits Circle, Rectangle {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle extends Shape {
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
```

This is a valid Java 17 code snippet **when the declarations are placed in the same appropriate source file**. `Circle` and `Rectangle` are the two permitted direct children; they choose `final` to prevent further inheritance.

**Important distinction:** If `Shape` is `abstract`, `Shape` itself cannot be instantiated. However, `sealed` on its own **does not mean abstract**. You can have a concrete sealed class with constructors that can be instantiated directly, as long as the remaining declaration constraints are satisfied.

A class can only `extends` **one** direct superclass; this remains Java's single-inheritance rule, unchanged by `sealed`.

## 4. Declaring a sealed interface

For interfaces, the corresponding form is:

```java
sealed interface Event permits Login, Logout {}

record Login(String username) implements Event {}

record Logout() implements Event {}
```

Here:

- `Event` defines the contract and restricts **direct implementing types**.
- `Login` and `Logout` are two records implementing `Event`.
- The two records can have their own components and accessors.
- Unlike a sealed class, a class can implement **multiple interfaces** (per Java rules), though each sealed interface must grant permission appropriately to the direct implementing type.

A sealed interface can have **direct subinterfaces** via `extends`, not just classes/records via `implements`:

```java
sealed interface Command permits Read, Write {}

record Read(String key) implements Command {}

non-sealed interface Write extends Command {}

final class Save implements Write {}
```

This is an illustrative Java 17 declaration in the same compilation unit. `Read` is a closed direct variant because a record is `final`. `Write` is a **`non-sealed`** direct subinterface, so `Save` can implement `Write` without appearing in `Command`'s `permits` clause. `Save` does not implement `Command` directly in terms of declaration syntax, but inherits the relationship with `Command` through `Write`.

**Important:** A `sealed interface` cannot be `final` like a class. An interface can be permitted to be extended by another interface with `sealed` or `non-sealed`; a directly implementing class must follow the required choice for subtypes. A record is implicitly `final`, so you do not need and are not allowed to add the `final` keyword to a record.

## 5. How do sealed class and sealed interface differ?

| Criterion | Sealed class | Sealed interface |
| --- | --- | --- |
| Goal | Controls **direct subclasses** | Controls **direct implementing classes/records/enums and direct subinterfaces** |
| How direct relationship is formed | `extends` | Classes/records use `implements`; subinterfaces use `extends` |
| Inheritance | A class has only one superclass | A class can implement multiple interfaces |
| State | Can have instance fields, constructors, shared implementations | Has constants, abstract/default/static/private methods per interface rules, no instance fields |
| Can be abstract? | Yes, but not required | Interfaces inherently represent an abstract contract |
| Can be `final` at the root? | Cannot be both `final` and `sealed` | Interfaces do not have the `final` modifier |
| Design fit | Want to share common state/logic, constructors, or template behavior | Want to model a group of variants with a shared contract, including `record`, without imposing a superclass |
| Interaction with pattern matching | `switch`/`instanceof` can check subtypes | Similar; especially well-suited with records as variants |

Examples of choosing between them:

- Use `sealed abstract class Document` if every document type needs to share a state field, a validating constructor, and shared method implementations.
- Use `sealed interface Message` if the variants `TextMessage`, `ImageMessage`, and `SystemMessage` have different structures, are well-suited as records, and only share a contract.
- If you want third-party projects to freely create new implementations, **sealed may not be appropriate**; consider a regular interface or an intentionally open `non-sealed` branch.

Sealed does not decide between a class and an interface on its own. Choose based on the **"is-a" relationship**, the need for shared state/code, and the desired extensibility.

## 6. Three mandatory choices for direct subtypes

The **direct subtypes listed or inferred as permitted** must explicitly state how they handle further extensibility. For a permitted class, the three choices are:

### 6.1. final — closed at the child branch

```java
sealed class Root permits Terminal {}

final class Terminal extends Root {}
```

`Terminal` is a permitted direct child and **does not allow further inheritance**.

### 6.2. sealed — further sealed at the next level

```java
sealed class Root permits Middle {}

sealed class Middle extends Root permits Leaf {}

final class Leaf extends Middle {}
```

`Middle` is both permitted by `Root` and **restricts** its own direct subtypes at the next level. `Leaf` is the leaf class of the branch.

### 6.3. non-sealed — reopening the child branch

```java
sealed class Root permits ExtensionPoint {}

non-sealed class ExtensionPoint extends Root {}

class CustomExtension extends ExtensionPoint {}
```

`ExtensionPoint` is permitted as a direct child, and then explicitly **reopens** the branch so other classes can inherit from it under normal Java rules. `CustomExtension` is **not** a direct child of `Root`, so it does not need to be named in `Root permits`.

Model:

```text
Root (sealed)
  |
  +-- Terminal (final)       -> stops
  |
  +-- Middle (sealed)        -> continues listing direct subtypes
  |      |
  |      +-- Leaf (final)
  |
  +-- ExtensionPoint (non-sealed) -> other classes can extend this branch
           |
           +-- CustomExtension
```

This is a diagram, not Java syntax. **A closed set of direct subtypes** does not necessarily mean **a closed set of all runtime descendants**, because `non-sealed` can open a branch.

### For subinterfaces

An interface that directly `extends` a sealed interface can be `sealed` or `non-sealed`; **an interface cannot be `final`**. A class that directly `implements` a sealed interface can be `final`, `sealed`, or `non-sealed`. A record is inherently `final`, making it an especially concise choice for data variants.

In real code, choose `non-sealed` intentionally: it gives up the ability to enumerate all types in that branch in advance, even though the set of direct branches of the sealed root remains controlled.

## 7. The permits rule: directly permitted, not all descendants

### 7.1. A permitted subclass must directly extend/implement

If `Parent` is sealed:

```java
sealed class Parent permits DirectChild {}

non-sealed class DirectChild extends Parent {}

final class Grandchild extends DirectChild {}
```

`DirectChild` is a **direct subclass**. `Grandchild` is only an **indirect descendant**; it does not need to be and must not be listed as a permitted direct subclass of `Parent` when it does not directly `extends Parent`.

Intentionally invalid example:

```java
// INVALID: Other does not directly extend Parent.
sealed class Parent permits DirectChild, Other {}

final class DirectChild extends Parent {}

final class Other {}
```

Adding a name to `permits` **does not automatically create an inheritance relationship**. Each listed type must validly declare `extends`/`implements` on the parent.

### 7.2. Omitting permits in the same compilation unit

Java allows **inferring** the list of permitted direct subclasses when the direct child classes/interfaces are declared in the **same compilation unit (same source file)** as the sealed type:

```java
sealed interface Job {}

record PrintJob(String text) implements Job {}

record SaveJob(int id) implements Job {}
```

This is a Java 17 code snippet with all three declarations in one file; `permits` can be omitted because the compiler identifies `PrintJob` and `SaveJob` as the direct implementors within the compilation unit.

In projects using **multiple files**, you should write `permits` explicitly so the contract is clearly visible and does not depend on single-file inference.

### 7.3. Module and package rules

You cannot use `permits` to arbitrarily grant permission to a type in just any module/package:

- In a **named module**, the permitted direct subclasses/interfaces must belong to the **same module** as the sealed type. They can be in different packages as long as they are in the same module, with valid accessibility and declarations.
- In an **unnamed module** (common when running projects on the classpath without a module descriptor), the permitted direct subclasses must be in the **same package** as the sealed type.
- Inheritance control rules are still governed by normal access rules (public/package-private, etc.), compilability, and type relationship validity.

For example, in a project not using Java modules with `package app.model; sealed interface Result ...`, a type `app.external.ResultImpl` in another package **cannot** be permitted as a direct child simply by listing its name in `permits`.

This is a **limitation of sealed definitions**, not a data security access-control mechanism or a replacement for the Java module system.

### 7.4. The non-sealed keyword cannot be used standalone

`non-sealed` is only valid for a class/interface that has a **direct sealed superclass or superinterface**. You cannot arbitrarily add `non-sealed` to a regular root class just to express "I want it open":

```java
// INVALID: no direct sealed superclass or superinterface.
non-sealed class ArbitraryRoot {}
```

A regular non-`final` class already allows inheritance under Java rules; `non-sealed` exists to **reopen a branch beneath a sealed parent**.

## 8. Complete Java 17 example: both sealed class and sealed interface

Create the file **`SealedClassAndInterface17.java`** with the following content:

```java
public class SealedClassAndInterface17 {

    static abstract sealed class Vehicle
            permits Car, Bike, OtherVehicle {}

    static final class Car extends Vehicle {
        final String plate;

        Car(String plate) {
            this.plate = plate;
        }
    }

    static abstract sealed class Bike extends Vehicle
            permits RoadBike, MountainBike {}

    static final class RoadBike extends Bike {}

    static final class MountainBike extends Bike {}

    static non-sealed class OtherVehicle extends Vehicle {}

    static final class Boat extends OtherVehicle {}

    static String vehicleName(Vehicle value) {
        if (value == null) {
            return "missing";
        }
        if (value instanceof Car car) {
            return "car:" + car.plate;
        }
        if (value instanceof RoadBike) {
            return "road-bike";
        }
        if (value instanceof MountainBike) {
            return "mountain-bike";
        }
        if (value instanceof Boat) {
            return "boat";
        }
        return "other-vehicle";
    }

    sealed interface Event permits LoginEvent, LogoutEvent {}

    record LoginEvent(String user) implements Event {}

    record LogoutEvent() implements Event {}

    static String eventName(Event event) {
        if (event instanceof LoginEvent login) {
            return "login:" + login.user();
        }
        if (event instanceof LogoutEvent) {
            return "logout";
        }
        return "missing";
    }

    public static void main(String[] args) {
        System.out.println(vehicleName(new Car("ABC")));
        System.out.println(vehicleName(new RoadBike()));
        System.out.println(vehicleName(new MountainBike()));
        System.out.println(vehicleName(new Boat()));
        System.out.println(vehicleName(new OtherVehicle()));
        System.out.println(vehicleName(null));
        System.out.println(eventName(new LoginEvent("Lan")));
        System.out.println(eventName(new LogoutEvent()));
        System.out.println(eventName(null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 SealedClassAndInterface17.java
java SealedClassAndInterface17
```

**Exact output:**

```text
car:ABC
road-bike
mountain-bike
boat
other-vehicle
missing
login:Lan
logout
missing
```

**Structure analysis:**

1. `Vehicle` is an **abstract sealed class** with three direct children: `Car`, `Bike`, `OtherVehicle`.
2. `Car` is `final`, so no class can extend it.
3. `Bike` is further `sealed` at the second level, permitting two classes `RoadBike` and `MountainBike`. Both are `final`.
4. `OtherVehicle` is `non-sealed`, so `Boat` can extend it even though it is not named in `Vehicle permits`.
5. `Event` is a **sealed interface**, directly implemented by the two records `LoginEvent` and `LogoutEvent`.
6. In Java 17, `instanceof` type patterns are used to identify variants. For example, `event instanceof LoginEvent login` both checks the type and binds the variable `login`.
7. `null` does not match any `instanceof` type pattern, so the example checks for null separately or returns a fallback result.

The snippet does not use `switch` patterns because Java 17 did not yet have that feature in finalized form. This demonstrates that **a sealed hierarchy can be used independently of pattern matching in switch**.

## 9. Sealed hierarchies support exhaustive switch in Java 21

One of the most practical benefits of a sealed interface is that the compiler knows the **permitted subtype set** of the selector and can verify whether the `switch` branches are exhaustive.

Create the file **`SealedSwitch21.java`**:

```java
public class SealedSwitch21 {

    sealed interface Result permits Success, Failure {}

    record Success(int value) implements Result {}

    record Failure(String message) implements Result {}

    static String render(Result result) {
        return switch (result) {
            case null -> "missing";

            case Success(int value) when value >= 0 ->
                    "ok=" + value;

            case Success(int value) ->
                    "invalid=" + value;

            case Failure(String message) ->
                    "error=" + message;
        };
    }

    public static void main(String[] args) {
        System.out.println(render(new Success(5)));
        System.out.println(render(new Success(-2)));
        System.out.println(render(new Failure("timeout")));
        System.out.println(render(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 SealedSwitch21.java
java SealedSwitch21
```

Output:

```text
ok=5
invalid=-2
error=timeout
missing
```

**Why doesn't the switch expression need `default`?**

- `Result` has only two direct implementing types: `Success` and `Failure`. Both records are `final`, so there are no new subclasses beneath them.
- The unguarded `case Success(int value)` covers all remaining `Success` instances, even when the preceding guarded branch `value >= 0` is not selected.
- `case Failure(String message)` covers the remaining branch of the hierarchy per the declared contract.
- `case null` explicitly states the choice for handling a `null` selector, rather than mistakenly assuming `default` catches null.
- With the selector type `Result`, the compiler can prove that all valid variants of the hierarchy are handled and accepts the `switch expression` without `default`.

If you add `Pending` as a new direct variant and update `permits`:

```java
// Illustrates an intentional change; this is not a snippet
// to insert verbatim into the runnable example above.
sealed interface Result permits Success, Failure, Pending {}

record Pending() implements Result {}
```

without adding a `Pending` case to `render`, the compiler will require handling the missing variant because the `switch expression` is no longer exhaustive.

**Note:** `when` restricts the value set of a case. Having only `case Success(int value) when value >= 0` will **not** cover `Success(-2)`. That is why the example has an unguarded `Success` branch afterward. Placing a general case before a guarded case of the same type can cause a **dominance** error.

### Null is not automatically prevented by sealed

A variable of type `Result` can still be `null` if there is no other check. Just because the variants are sealed/records does not mean a reference variable always exists. In Java 21, a pattern `switch` with a `null` selector will throw `NullPointerException` if there is no appropriate null handling. This example uses `case null` to express the desired behavior.

If the domain **forbids** null, you can place `Objects.requireNonNull(result)` at the API boundary, or use `case null -> throw new IllegalArgumentException(...)` instead of returning `"missing"`.

## 10. Sealed class/interface and instanceof do not automatically check exhaustiveness

On Java 17, `instanceof` identifies objects at runtime:

```java
static String status(Object value) {
    if (value instanceof String text) {
        return "text=" + text;
    }
    if (value instanceof Integer number) {
        return "integer=" + number;
    }
    return "other";
}
```

This is an illustrative Java 17 method, not inherently tied to a sealed hierarchy. If the selector is a sealed interface, you can also write an `instanceof` chain for each subtype. However, the compiler **does not automatically check the exhaustiveness of the entire `if/else` chain** the way it analyzes pattern `switch` with a sealed selector in Java 21.

The benefit of sealed is not that `instanceof` "recognizes every type faster," but rather an **explicitly closed** type design so Java and maintainers understand the possible variants.

With a multi-branch `instanceof` block, you still need to decide how to handle unmatched cases and `null`. If the logic is repeated in many places, consider an exhaustive `switch` (Java 21) or polymorphic methods instead of duplicating `if` chains.

## 11. Sealed does not mean every inheritance path is locked

Consider the following diagram:

```text
Vehicle (sealed)
 ├── Car (final)
 ├── Bike (sealed)
 │    ├── RoadBike (final)
 │    └── MountainBike (final)
 └── OtherVehicle (non-sealed)
      ├── Boat (final)
      └── ... other subclasses
```

- The **direct** children of `Vehicle` remain restricted to `Car`, `Bike`, and `OtherVehicle`.
- In the `Car` branch, no subclasses can be added.
- In the `Bike` branch, inheritance is only allowed according to the declared subset.
- In the `OtherVehicle` branch, there can be new descendants that `Vehicle` does not list.

This has two consequences for pattern matching:

1. If handling `Vehicle` in Java 21, a `case OtherVehicle v` branch can cover both `Boat` and unknown descendants beneath `OtherVehicle`.
2. You **cannot** use a sealed root to conclude that all runtime descendants form a fixed list if there is a `non-sealed` branch.

For example, if the business logic wants to handle all vehicles in the open branch with the same logic, that is fine. But if only an absolutely fixed set of vehicle types is allowed, do not open `non-sealed` on a core branch.

## 12. Common limitations and compilation errors

### Error 1 — Direct child does not choose final/sealed/non-sealed

```java
// INTENTIONALLY INVALID: Child is a direct subclass of sealed Parent
// but does not declare an appropriate modifier.
sealed class Parent permits Child {}

class Child extends Parent {}
```

Fix by changing to `final class Child extends Parent {}`, or `sealed`/`non-sealed` with valid relationships and permitted descendants.

### Error 2 — Not named in permits

```java
sealed class Parent permits Allowed {}

final class Allowed extends Parent {}

// INTENTIONALLY INVALID: Forbidden is not permitted by Parent.
final class Forbidden extends Parent {}
```

With an explicit `permits`, only the permitted names can be direct subclasses. Being in the same package is not enough to be automatically included when the list is explicitly written.

### Error 3 — Permitted type is not actually a direct child

```java
// INTENTIONALLY INVALID: NotChild does not extend Parent.
sealed class Parent permits Allowed, NotChild {}

final class Allowed extends Parent {}

final class NotChild {}
```

Changing a line in `permits` does not create a type relationship. Check for the proper `extends` or `implements`.

### Error 4 — Combining final and sealed on the same class

```java
// INTENTIONALLY INVALID: final forbids inheritance, sealed defines permitted children.
final sealed class Contradiction {}
```

These two choices have opposing roles. Choose `final` if you want **no subclasses**; choose `sealed` if you want a **specific set of subclasses**.

### Error 5 — Using non-sealed without a direct sealed parent

```java
// INTENTIONALLY INVALID:
non-sealed class FreeClass {}
```

`non-sealed` is only a modifier to reopen a branch beneath a direct sealed type. A normal non-`final` class can already be inherited under normal rules.

### Error 6 — Thinking a record can extend a class

```java
// INTENTIONALLY INVALID: a record cannot extend a user-defined class.
sealed class Message permits TextMessage {}

record TextMessage(String text) extends Message {}
```

A record implicitly extends `java.lang.Record` and cannot `extends Message`. If you want to use records as variants, typically choose a **sealed interface**:

```java
sealed interface Message permits TextMessage {}

record TextMessage(String text) implements Message {}
```

### Error 7 — Placing a permitted subtype in the wrong module/package

If using the classpath/unnamed module, a permitted direct subclass must be in the **same package** as the sealed type. With a named module, it must be in the **same module**. Do not expect `permits` to bypass those boundaries.

### Error 8 — Forgetting to add a case when extending the hierarchy

With Java 21, a `switch expression` that used to be exhaustive may no longer be exhaustive when a new permitted direct subclass is added. You will then need to review the logic at each place using a pattern switch. This is intentional: **changes to the data domain structure force a review of the handling logic**.

### Error 9 — Mistaking sealed for a mechanism that prevents all runtime subclasses

`non-sealed` can allow descendants to extend. Furthermore, a sealed class/interface is a **language modeling and inheritance constraint**, not a replacement for object access checks, validation, API security, or external data control.

## 13. Sealed hierarchies, polymorphism, and code organization

A sealed hierarchy can be processed using several strategies:

**Strategy 1 — Polymorphism:** Define a common behavioral method that each variant implements itself. For example, `Shape.area()` on `Circle` and `Rectangle`. This works well when the behavior is a stable characteristic of each type and will be called in many places. It still works with sealed types.

**Strategy 2 — Pattern switch (Java 21):** Use `switch (shape)` in one place where you want to transform/display/render data by variant. This works well when you need **an external transformation** over each type and want the compiler to verify branch exhaustiveness.

**Strategy 3 — Visitor or dedicated handlers:** Can suit code with many operations, needing to separate domain classes from processing, or having to support older Java versions. Sealed helps constrain the model, but does not automatically replace visitors.

No single strategy is best in every situation. If every operation is a huge `switch` placed in dozens of methods, consider polymorphism. Conversely, if you have a few independent data converters, an exhaustive `switch` is often clearer and has less boilerplate.

### Distinguishing closed data from closed behavior

`sealed` "closes" **the set of direct subtypes**, not the values of fields. For example, `record Success(int value)` allows many values of `value`; `record Failure(String message)` can hold any string or `null` if there is no separate validation. To ensure valid data, use constructors/compact constructors, invariant checks, and unit tests.

The permitted subtype set also does not limit the number of objects instantiated. You can create many `Success` instances with different values; sealed does not turn objects into singletons.

## 14. Step-by-step design of a sealed hierarchy

A process to avoid arbitrary modifier choices:

1. **List the actual variants of the business domain.** For example, `Success`, `Failure`, `Pending`. Check whether that set is expected to be extended by plugins or partners.
2. **Choose between sealed class and sealed interface.** Need constructors, state, shared code, and a meaningful superclass? Consider a sealed class. Need multiple records/independent implementations and multiple contracts? Consider a sealed interface.
3. **Draw the tree of direct and indirect subtypes.** Do not list descendants in a grandparent's `permits` if they do not directly inherit from it.
4. **Set the policy for each direct child.** `final` to close, `sealed` for controlled hierarchy at the next level, `non-sealed` to intentionally open the branch.
5. **Check module/package placement.** On the classpath, permitted direct subclasses must be in the same package; in a named module, they must be in the same module.
6. **If you want to omit permits, check the compilation unit.** When direct subclasses are declared in the same file, Java can infer them; in multi-file setups, write it explicitly.
7. **Define null and validation conventions.** Choose errors or states for null input, record component validation, and required invariants.
8. **Choose the logic that consumes variants.** Polymorphism, `instanceof` (Java 17), exhaustive pattern `switch` (Java 21), or a dedicated API.
9. **Test adding subtypes.** Try adding an unpermitted direct subclass to confirm a compile error, add a permitted subtype to see exhaustive `switch`es require updates, and test any `non-sealed` branch if present.

Do not use `sealed` just to use new syntax. Choose `sealed` when **the permitted variants are an explicit part of the data domain's public design**.

## 15. Practice exercises

### Exercise 1 — Two-level sealed class

Create `abstract sealed class Payment permits Cash, Card, Gift`. Define `Cash` as `final`, `Card` as `sealed` with two subtypes `DebitCard` and `CreditCard` (both `final`), and `Gift` as `non-sealed`. Draw the inheritance tree, add `PartnerGift extends Gift`, and explain why it does not appear in `Payment permits`.

### Exercise 2 — Switching from class to sealed interface

Create `sealed interface Notification permits Email, Sms` with two `record`s. Write a method that accepts `Notification` and uses Java 17 `instanceof` to return a description. Then compare the convenience of records/constructors when using a sealed interface instead of a sealed class.

### Exercise 3 — Direct child relationship

Given the hierarchy:

```text
Root
  -> Branch
       -> Leaf
```

If `Root` is sealed and `Branch` is sealed, determine the exact `permits` list for both types. Why is `Leaf` not listed in `Root permits` unless it is truly a direct child?

### Exercise 4 — Omitting permits and compilation units

Put `sealed interface Job`, `record Upload`, and `record Download` in the same file; try omitting `permits`. Then split them into multiple files in the same package and add `permits` explicitly. Note the difference between **same package** and **same compilation unit**.

### Exercise 5 — Exhaustive switch in Java 21

Run `SealedSwitch21`. Add `record Pending() implements Result` and include it in `Result permits`. Observe the compilation error in `render`; add `case Pending p -> "pending"`, then verify the output again.

### Exercise 6 — Guard does not cover all variants

In `render`, try removing the unguarded `Success(int value)` case, keeping only the `when value >= 0` case. Why is `Success(-2)` unhandled? Explain why `sealed` does not make a guard automatically cover the remaining values.

### Exercise 7 — Intentional non-sealed decision

You are designing a notification system where third-party libraries can add new types, while keeping the `SystemNotification` group restricted. Propose a root `sealed` interface, a `sealed` branch for system notifications, and a `non-sealed` branch for extensions. Point out the consequences for exhaustive `switch`.

### Exercise 8 — Fixing compilation errors

Explain and fix four errors: a permitted class not directly inheriting, a direct subclass missing `final`/`sealed`/`non-sealed`, a record using `extends` on a user-defined class, and `non-sealed` on a class with no direct sealed parent.

## 16. Self-assessment questions

1. Which subtypes does `sealed` close: direct ones or all descendants? How does a `non-sealed` branch change the answer?
2. What is the most important difference between `sealed class` and `sealed interface` when you want to use `record`?
3. Why must a permitted direct class choose `final`, `sealed`, or `non-sealed`? Can a subinterface be `final`?
4. Under what conditions can the `permits` keyword be omitted? Is "same package" alone enough to omit `permits`?
5. Can you permit a direct subclass in another module? How do the rules differ between a named module and an unnamed module?
6. Must a sealed class be `abstract`? Is `final sealed class` valid?
7. How does adding a subtype to a sealed hierarchy affect an exhaustive Java 21 `switch` expression without `default`?
8. Why can't a `when` guard that only covers a subset implicitly replace an unguarded covering case?
9. Why are `null` checks and record component validation still necessary when using `sealed`?
10. In your problem domain, should the logic live in polymorphic methods or a pattern `switch`? Why?

You have completed this lesson when you can **write both forms of sealed declarations, correctly identify permitted direct subclasses, explain the three modifier choices for each branch, and build an exhaustive `switch`** on a sealed interface in Java 21.

## 17. Official sources

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): goals, syntax, and subtype restriction rules, official since Java 17.
- [Java Language Specification, Java SE 17 — `8.1.1.2 sealed, non-sealed and final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): class declaration rules, permitted subclasses, and modifiers.
- [Java Language Specification, Java SE 17 — `9.1.1.4 sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): conditions for sealed interfaces and subinterfaces.
- [JEP 395 — Records](https://openjdk.org/jeps/395): records as fixed-structure class types, useful when implementing sealed interfaces.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): `instanceof` type patterns available since Java 16.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern `switch`, exhaustiveness, and guards finalized in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): using record patterns to deconstruct components in `switch` since Java 21.

**Remember:** Sealed is a tool for **controlling inheritance architecture and data domain modeling**, not an automatic validation mechanism. `sealed class` fits when you need a superclass sharing state/behavior, while `sealed interface` is flexible for sets of data variants and `record`s. The benefit of branch exhaustiveness checking via pattern `switch` is clearest starting in Java 21.
