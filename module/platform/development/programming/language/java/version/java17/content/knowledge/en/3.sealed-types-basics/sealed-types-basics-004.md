# Direct Subtype Rules and `extends`, `implements` Relationships in Sealed Types — Java 17

Starting in **Java 17**, `sealed class` and `sealed interface` are official features for restricting **which direct subtypes are permitted** in a hierarchy. At the heart of this mechanism is how Java interprets `extends`, `implements`, and the `permits` list.

A sealed type **does not necessarily restrict every descendant at every depth**. It restricts **declarations connected directly to it**. A child branch can then remain closed via `final`, stay controlled via `sealed`, or open up via `non-sealed`.

## 1. What is a direct subtype?

Observe:

```java
sealed class Vehicle permits Car {}

non-sealed class Car extends Vehicle {}

class ElectricCar extends Car {}
```

Diagram:

```text
Vehicle (sealed)
└── Car (non-sealed)      [directly extends Vehicle]
    └── ElectricCar      [directly extends Car]
```

Here:

- `Car` is a **direct subclass** of `Vehicle` because `Car`'s declaration states `extends Vehicle`.
- `ElectricCar` is an **indirect** subclass of `Vehicle` because it goes through `Car`.
- `Vehicle permits Car` is complete. `ElectricCar` must not and need not be placed in `Vehicle`'s `permits`.
- `Car` is `non-sealed`, so `ElectricCar` can be a regular class without any sealed-related modifier.

You can still write:

```java
Vehicle vehicle = new ElectricCar(); // Valid
```

That is **type assignment** via transitivity; it does not make `ElectricCar` a direct subclass of `Vehicle`.

**Rule:** to know whether a type is a *direct* subtype of a sealed type, check the superclass and superinterfaces named directly in its declaration—do not infer it from whether a variable can hold an instance of that type.

## 2. The `extends` and `implements` matrix

| Subtype declaration | Syntax | Direct supertype | Can be a direct subtype of |
|---|---|---|---|
| `class` | `class Child extends Parent` | One `class` | `sealed class Parent` |
| `class` or `record` | `class Child implements Role` | One or more `interface`s | `sealed interface Role` |
| `interface` | `interface Child extends Role` | One or more `interface`s | `sealed interface Role` |
| `interface` | `interface Child implements Role` | Invalid | None |
| `interface` | `interface Child extends ParentClass` | Invalid | None |
| `class` | `class Child extends SomeInterface` | Invalid | None |

Java 17 example:

```java
sealed class Base permits Derived {}
final class Derived extends Base {}

sealed interface Task permits DirectTask, SpecializedTask {}
final class DirectTask implements Task {}
non-sealed interface SpecializedTask extends Task {}
```

In `final class Derived extends Base`, `extends` connects **class to class**. In `final class DirectTask implements Task`, `implements` connects **class to interface**. In `non-sealed interface SpecializedTask extends Task`, `extends` connects **interface to interface**.

A class has only **one direct superclass** but can have **multiple direct superinterfaces**. An interface can `extends` multiple interfaces.

**`permits` does not create an inheritance relationship on its own.** It lists types that have declared (or will declare) direct `extends`/`implements` on the sealed type. Both sides must match **bidirectionally**: the child must name the parent, and the parent must permit the child.

## 3. Sealed class: direct access goes through `extends`

Example of an abstract type for geometry:

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

`Circle` and `Rectangle` are classes that directly `extends Shape`, so `Shape` must permit them. `final` closes each branch, preventing other classes from `extends Circle` or `extends Rectangle`.

`abstract sealed` is a valid combination:

- `abstract`: cannot directly instantiate `new Shape()` and allows declaring abstract methods.
- `sealed`: controls which classes are permitted to `extends Shape`.

An interface **cannot** become a direct subtype of `Shape`, because Java does not allow an interface to `extends` a class. If both classes and interfaces need to be direct subtypes, the parent type must be a **sealed interface**.

## 4. Sealed interface: classes use `implements`, interfaces use `extends`

A `sealed interface` can permit both classes and interfaces as direct subtypes. Example containing both forms:

```java
sealed interface Payment permits CardPayment, CashPayment, VoucherPayment {
    long amount();
}

final class CardPayment implements Payment {
    private final long cents;

    CardPayment(long cents) {
        this.cents = cents;
    }

    @Override
    public long amount() {
        return cents;
    }
}

record CashPayment(long amount) implements Payment {}

non-sealed interface VoucherPayment extends Payment {
    String code();
}
```

Diagram:

```text
Payment (sealed interface)
├── CardPayment    (final class)               -- implements Payment
├── CashPayment    (record, implicitly final)  -- implements Payment
└── VoucherPayment (non-sealed interface)      -- extends Payment
```

`Payment permits` contains strictly **three direct subtypes** even though their declaration forms differ.

### Why don't indirect subtypes need `permits` from a grandparent?

`VoucherPayment` is permitted to `extends Payment` and is `non-sealed`. Therefore we can write:

```java
final class GiftVoucher implements VoucherPayment {
    @Override
    public long amount() {
        return 50_000;
    }

    @Override
    public String code() {
        return "WELCOME";
    }
}

Payment payment = new GiftVoucher(); // Valid
```

`GiftVoucher` directly `implements VoucherPayment`. It is a subtype of `Payment` **through** `VoucherPayment`, so `Payment permits GiftVoucher` is **not needed**.

However, if the declaration is changed to:

```java
// Invalid if GiftVoucher is not in Payment permits:
// final class GiftVoucher implements VoucherPayment, Payment { ... }
```

then `GiftVoucher` explicitly names `Payment` in `implements`, creating an additional **direct relationship**. It must then appear in `Payment`'s `permits` list, even though it already implements `Payment` indirectly via `VoucherPayment`.

Practical takeaway: `permits` is checked only against **direct relationships actually present in the declaration**; a type can have both direct and indirect relationships to the same interface if the author explicitly names that interface.

## 5. A class can have multiple direct sealed supertypes

### Two sealed interfaces

```java
sealed interface Auditable permits Receipt {}
sealed interface Printable permits Receipt {}

final class Receipt implements Auditable, Printable {}
```

`Receipt` directly `implements` **both interfaces**. Both `permits` lists must include `Receipt`. Missing it on either side makes the subtype declaration invalid.

### One sealed class and one sealed interface

```java
sealed class Entity permits User {}
sealed interface Identifiable permits User {}

final class User extends Entity implements Identifiable {}
```

`User` directly `extends Entity` and directly `implements Identifiable`. Therefore it must appear in **both `permits` lists**.

Do not check assignment compatibility and guess `permits`. Inspect **each subtype's own `extends`/`implements` list**, and verify permission for every sealed supertype named.

## 6. Three mandatory states for a direct subclass

When a class directly `extends` a sealed class **or** directly `implements` a sealed interface, it must choose one of three paths:

| Modifier | Meaning | Can subclasses be declared beneath it? |
|---|---|---|
| `final` | Terminates the branch | No |
| `sealed` | Further restricts direct subtypes of this branch | Yes, but only those permitted by this branch |
| `non-sealed` | Reopens the branch | Yes, under standard Java inheritance rules |

Multi-level example:

```java
sealed class Message permits TextMessage, AttachmentMessage, CustomMessage {}

final class TextMessage extends Message {}

sealed class AttachmentMessage extends Message
        permits ImageMessage, VideoMessage {}

final class ImageMessage extends AttachmentMessage {}

final class VideoMessage extends AttachmentMessage {}

non-sealed class CustomMessage extends Message {}

class BusinessMessage extends CustomMessage {}
```

Diagram:

```text
Message (sealed)
├── TextMessage (final)                  [terminated]
├── AttachmentMessage (sealed)           [controls next level]
│   ├── ImageMessage (final)
│   └── VideoMessage (final)
└── CustomMessage (non-sealed)           [reopened branch]
    └── BusinessMessage (regular class)
```

Three core observations:

1. `Message` permits only three **direct classes**: `TextMessage`, `AttachmentMessage`, and `CustomMessage`.
2. `AttachmentMessage` must **itself** specify `permits ImageMessage, VideoMessage` because it is `sealed` and is the direct superclass of those two classes.
3. `BusinessMessage` does not need to appear in `Message permits`, nor does it need the `non-sealed` modifier.

`abstract` does not replace `final`/`sealed`/`non-sealed`: a class can be `abstract sealed` or `abstract non-sealed`, but cannot be `abstract final`.

## 7. What if the direct subtype is an interface?

An interface that directly `extends` a sealed interface must choose **`sealed` or `non-sealed`**:

```java
sealed interface Notification
        permits EmailNotification, ExtensionNotification {}

sealed interface EmailNotification extends Notification
        permits TransactionEmail {}

non-sealed interface ExtensionNotification extends Notification {}

final class TransactionEmail implements EmailNotification {}
```

- `EmailNotification` retains control and lists **its own** direct subtypes.
- `ExtensionNotification` opens the branch, allowing other classes/interfaces to implement or extend it.
- **An interface cannot be `final`**. To terminate an interface branch, you typically use a `final class` or `record` implementing that interface.

### Does a `record` need `final` written explicitly?

No. A record in Java 17 is **implicitly `final`**, so it can be a direct subtype of a sealed interface without writing the modifier:

```java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

An `enum` can also directly implement a sealed interface; Java treats an enum as implicitly `final` or `sealed` depending on whether any enum constant has a class body. In introductory lessons, a `record` is a concise example of a class that is implicitly `final`.

### `non-sealed` is not an arbitrary modifier

A class/interface may only be declared `non-sealed` if it has **at least one direct sealed supertype**. For example:

```java
class OpenBase {}

// Invalid: OpenBase is not sealed.
// non-sealed class Extra extends OpenBase {}

// Valid:
class Extra extends OpenBase {}
```

In other words, `non-sealed` is a decision to **reopen a sealed boundary at the direct level**, not the standard way to write every extensible class.

## 8. What conditions must `permits` satisfy?

### 8.1. Every name must point to an actual direct subtype

This is invalid:

```java
// Invalid: Other does not extend Base.
// sealed class Base permits Other {}
// final class Other {}
```

Writing `permits Other` does not turn `Other` into a subclass. To be valid, `Other` must actually declare `extends Base` and satisfy the other rules.

Similarly:

```java
// Invalid: LogEntry does not implement Event.
// sealed interface Event permits LogEntry {}
// final class LogEntry {}
```

### 8.2. Direct subtypes outside the list are rejected

```java
sealed class Account permits PersonalAccount {}

final class PersonalAccount extends Account {}

// Invalid: not permitted by Account.
// final class BusinessAccount extends Account {}
```

This is a **compile-time error**; you do not have to wait until runtime.

### 8.3. `permits` does not allow duplicate types

```java
// Invalid: duplicate One.
// sealed class Base permits One, One {}
// final class One extends Base {}
```

`One` and the package-qualified name of `One` still refer to **one type**: it cannot be listed twice. Additionally, a class/interface with `permits` that is **not** declared `sealed` is also an error.

### 8.4. Do not list indirect descendants

Invalid:

```java
// Invalid: Leaf only directly extends Middle.
// sealed class Root permits Middle, Leaf {}
// non-sealed class Middle extends Root {}
// final class Leaf extends Middle {}
```

Valid:

```java
sealed class Root permits Middle {}

non-sealed class Middle extends Root {}

final class Leaf extends Middle {}
```

If `Middle` is also `sealed`, the `permits Leaf` list belongs to **Middle**, not `Root`.

### 8.5. Location constraints: named module vs. unnamed module

Subtypes permitted by `permits` must reside in the appropriate scope:

| Sealed type's context | Scope for permitted direct subtypes |
|---|---|
| **Named module** (using JPMS with `module-info.java`) | Types must belong to the **same named module**; they may be in different packages if accessible |
| **Unnamed module** (standard classpath) | Types must be in the **same package** as the sealed type |

Classpath example:

```java
// File: com/example/model/Action.java
package com.example.model;

public sealed interface Action permits SaveAction {}
```

```java
// File: com/example/model/SaveAction.java
package com.example.model;

public final class SaveAction implements Action {}
```

The two files are in the same package, so they satisfy the unnamed module constraint. If `SaveAction` is moved to another package, **merely changing `permits` to a fully qualified package name is not enough** to bypass the same-package constraint in an unnamed module.

In a named module, the sealed type and a permitted direct subtype can live in two different packages **within the same module**, provided the subtype can access the supertype and the declaration is valid.

## 9. `permits` can be omitted when the compiler can infer it

Java 17 can infer permitted direct subtypes if the sealed type **does not declare `permits`** and its direct subtypes are **in the same compilation unit** (the same `.java` source file).

Example single file `Operation.java`:

```java
sealed interface Operation {}

record Add(int a, int b) implements Operation {}

record Multiply(int a, int b) implements Operation {}
```

The compiler infers `Add` and `Multiply` as the two permitted direct subtypes of `Operation`.

The **same source file** requirement is crucial: being in the same package across **different `.java` files** is not inferred this way. When splitting files, write `permits` explicitly:

```java
// Operation.java
sealed interface Operation permits Add, Multiply {}
```

```java
// Add.java
record Add(int a, int b) implements Operation {}
```

```java
// Multiply.java
record Multiply(int a, int b) implements Operation {}
```

The three files above are assumed to belong to the same package. When `permits` is omitted, the compiler only infers direct subtypes with a **canonical name** in the same compilation unit (e.g., top-level/member types); **local** and **anonymous** classes are not inferred that way. A sealed type must not lack `permits` while also having no valid direct subtypes to infer.

Write `permits` explicitly when you want readers to see the hierarchy right away or when types are split across multiple files.

## 10. Distinguishing indirect relationships via classes and interfaces

### 10.1. Indirect via a `non-sealed` class

```java
sealed class Parent permits OpenChild {}

non-sealed class OpenChild extends Parent {}

class GrandChild extends OpenChild {}
```

`GrandChild` is an indirect subclass of `Parent`; it does not need `Parent permits GrandChild`.

### 10.2. Indirect via a `non-sealed` interface

```java
sealed interface BaseRole permits ExtendedRole {}

non-sealed interface ExtendedRole extends BaseRole {}

final class Person implements ExtendedRole {}
```

`Person` directly implements `ExtendedRole`, indirectly belonging to `BaseRole`. Only `ExtendedRole` needs to be in `BaseRole permits`.

### 10.3. Indirect via a superclass that implements the interface

```java
sealed interface Identified permits BaseEntity {}

non-sealed class BaseEntity implements Identified {}

class Customer extends BaseEntity {}
```

`Customer` inherits the implementation of `Identified` through its superclass `BaseEntity`; `Customer` does not directly `implements Identified`. Hence `Identified` only needs to permit `BaseEntity`.

**Special case:** If `Customer` both `extends BaseEntity` and also writes `implements Identified`, it creates a direct relationship to `Identified` itself. In that case, `Identified` must permit it separately, and `Customer` must have an appropriate modifier as a class with a sealed direct superinterface.

## 11. Common errors and how to diagnose their causes

Snippets marked "invalid" below are isolated error illustrations, not examples meant to be compiled together.

| Syntax/situation | What is wrong? | How to fix |
|---|---|---|
| `class Child extends SealedClass` where `Child` is not in `permits` | Blocked by direct superclass | Permit `Child` if it fits the design |
| `class Impl implements SealedInterface` where `Impl` is not in `permits` | Blocked by direct superinterface | Permit `Impl` |
| `interface Child extends SealedInterface` where not in `permits` | Blocked by direct superinterface | Permit `Child` |
| `permits GrandChild` when `GrandChild` only `extends Child` | Not a direct subtype | Remove `GrandChild` from grandparent's `permits` |
| `class Child extends SealedParent {}` | Missing `final`/`sealed`/`non-sealed` | Choose one modifier for the class |
| `interface Child extends SealedParent {}` | Missing `sealed`/`non-sealed` | Choose a modifier for the interface |
| `final interface Child` | Interfaces cannot be `final` | Use `sealed`/`non-sealed` as intended |
| `non-sealed class Child extends OpenBase` | Direct superclass is not sealed (and no sealed direct superinterface) | Use a regular `class` |
| `permits A, A` | Duplicate reference to the same type | List once |
| `permits` on a non-`sealed` class/interface | Missing `sealed` requirement for `permits` syntax | Declare `sealed` if restricting the tree |
| Two different packages in an unnamed module | Violates permitted direct subtype scope | Place direct subtype in the same package or design an appropriate named module |

### Error example: missing direct subtype modifier

```java
// Invalid: Leaf is not final/sealed/non-sealed.
// sealed class Node permits Leaf {}
// class Leaf extends Node {}
```

Fix:

```java
sealed class Node permits Leaf {}
final class Leaf extends Node {}
```

### Error example: confusing `extends` with `implements`

```java
// Invalid: a class cannot extend an interface.
// sealed interface Service permits HttpService {}
// final class HttpService extends Service {}
```

Fix:

```java
sealed interface Service permits HttpService {}
final class HttpService implements Service {}
```

### Error example: adding `non-sealed` on an already open tier

```java
// sealed class Root permits Branch {}
// non-sealed class Branch extends Root {}
// non-sealed class Next extends Branch {} // Invalid: Branch is not sealed
```

Fix to `class Next extends Branch {}` or `final class Next extends Branch {}`, depending on whether `Next` should allow further subclassing.

## 12. Practice exercise: identifying direct subtypes

Read the following Java 17 code:

```java
sealed interface Document permits PdfDocument, EditableDocument {}

final class PdfDocument implements Document {}

non-sealed interface EditableDocument extends Document {}

class TextDocument implements EditableDocument {}

final class RichTextDocument extends TextDocument {}
```

**Question 1.** Which types are direct subtypes of `Document`?

**Answer:** `PdfDocument` because it `implements Document`; `EditableDocument` because it `extends Document`. These are the exact two names in `permits`.

**Question 2.** Are `TextDocument` and `RichTextDocument` subtypes of `Document`?

**Answer:** Yes, transitively, but they are **indirect** subtypes: `TextDocument` goes through `EditableDocument`, and `RichTextDocument` goes through `TextDocument` and `EditableDocument`.

**Question 3.** Do `TextDocument` and `RichTextDocument` need to be added to `Document permits`?

**Answer:** No. They do not directly declare `extends`/`implements Document`, so adding them would violate the direct subtype requirement.

**Question 4.** What happens if `TextDocument` is changed to `class TextDocument implements EditableDocument, Document`?

**Answer:** Then `TextDocument` directly `implements Document`; it must be added to `Document permits` and must declare one of `final`, `sealed`, or `non-sealed`. If you still want `RichTextDocument extends TextDocument`, you can choose `non-sealed class TextDocument implements EditableDocument, Document {}`.

**Question 5.** If `EditableDocument` should remain `sealed` and only allow `TextDocument` to directly implement it, how should it be written?

```java
sealed interface Document permits PdfDocument, EditableDocument {}

final class PdfDocument implements Document {}

sealed interface EditableDocument extends Document
        permits TextDocument {}

non-sealed class TextDocument implements EditableDocument {}

final class RichTextDocument extends TextDocument {}
```

Now `EditableDocument` restricts its own direct subtypes; `TextDocument` chooses `non-sealed` so `RichTextDocument` can extend it afterward.

## 13. How to analyze a sealed tree without confusion

For each sealed class/interface, answer three questions in order:

1. **Who directly names this type in `extends` or `implements`?** Examine only one inheritance step.
2. **Are those types permitted?** Check explicit `permits`, or the inferred list in the same compilation unit.
3. **Does the direct subtype block, keep controlling, or open up?** Classes choose `final`, `sealed`, or `non-sealed`; interfaces choose `sealed` or `non-sealed`; records are implicitly `final`.

If you encounter a `sealed` branch, continue analyzing in the same way **starting from that branch**. If you encounter a `non-sealed` branch, descendants beneath it do not need to be listed by the sealed ancestor, as long as they do not introduce a restricted direct relationship themselves.

## Java 17 references

- [JLS 17 — `8.1.1.2`: `sealed`, `non-sealed`, `final` for classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2)
- [JLS 17 — `8.1.4`: Superclasses and Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.4)
- [JLS 17 — `8.1.5`: Superinterfaces of a class](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.5)
- [JLS 17 — `8.1.6`: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [JLS 17 — `9.1.1.4`: Sealed and Non-Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4)
- [JLS 17 — `9.1.3` and `9.1.4`: Direct Subinterfaces and Permits](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
- [JEP 409 — Sealed Classes: standard feature in Java 17](https://openjdk.org/jeps/409)
