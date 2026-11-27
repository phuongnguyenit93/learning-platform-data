# Roles of `final`, `sealed`, and `non-sealed` on Subclasses in Java 17

When a class or interface is declared `sealed`, Java allows only specified types to inherit or implement it directly. Yet control **does not stop at the `permits` list**: each direct subclass must also explicitly state whether its branch **terminates**, **remains restricted**, or **opens up for free extension**. That is the role of the three modifiers `final`, `sealed`, and `non-sealed`.

*Sealed classes and interfaces* have been **standard since Java 17** ([JEP 409](https://openjdk.org/jeps/409)). Examples in this lesson use standard Java 17 syntax with no `--enable-preview` flag needed.

## 1. The big picture: three ways to decide a branch's fate

Suppose the system defines:

```java
sealed interface Payment
        permits CashPayment, BankTransfer, GatewayPayment {
}
```

`Payment` permits strictly **three direct types**: `CashPayment`, `BankTransfer`, and `GatewayPayment`. At each permitted type, the developer must decide what happens next along that branch:

| Subtype modifier | Meaning | Consequence for further inheritance |
|---|---|---|
| `final` | **Close the branch** | No class may `extends` that class. |
| `sealed` | **Keep the branch controlled** | Only classes/interfaces permitted at the next level may directly inherit or implement it. |
| `non-sealed` | **Reopen the branch** | Other types may inherit or implement this branch under standard Java rules; they do not need to appear in the ancestor's `permits`. |

Diagram:

```text
Payment (sealed interface)
│
├── CashPayment (final class)
│   └── [Cannot be subclassed]
│
├── BankTransfer (sealed abstract class)
│   ├── DomesticTransfer (final class)
│   │   └── [Cannot be subclassed]
│   └── ForeignTransfer (non-sealed class)
│       ├── PriorityForeignTransfer (regular class)
│       └── ... (other valid subclasses)
│
└── GatewayPayment (non-sealed class)
    ├── CustomGatewayPayment (regular class)
    └── ... (other valid subclasses)
```

Key point: **`sealed` restricts direct subtypes; it does not automatically lock subtypes at every depth.** Once a direct branch is declared `non-sealed`, grandchild classes in that branch no longer need to be listed by the `sealed` ancestor.

## 2. Complete example running on JDK 17

Create the file **`SealedChildRoles.java`**:

```java
sealed interface Payment
        permits CashPayment, BankTransfer, GatewayPayment {

    String description();
}

// Branch 1: terminates here.
final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash payment";
    }
}

// Branch 2: continues restricting direct subclasses.
abstract sealed class BankTransfer implements Payment
        permits DomesticTransfer, ForeignTransfer {
}

final class DomesticTransfer extends BankTransfer {
    @Override
    public String description() {
        return "Domestic bank transfer";
    }
}

non-sealed class ForeignTransfer extends BankTransfer {
    @Override
    public String description() {
        return "International bank transfer";
    }
}

// Valid: ForeignTransfer opened the branch.
class PriorityForeignTransfer extends ForeignTransfer {
}

// Branch 3: allows other classes to extend freely.
non-sealed class GatewayPayment implements Payment {
    @Override
    public String description() {
        return "Partner gateway payment";
    }
}

// Valid even though the class name does not appear in Payment.permits.
class CustomGatewayPayment extends GatewayPayment {
}

public class SealedChildRoles {
    public static void main(String[] args) {
        Payment[] payments = {
            new CashPayment(),
            new DomesticTransfer(),
            new ForeignTransfer(),
            new PriorityForeignTransfer(),
            new CustomGatewayPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.description());
        }
    }
}
```

Compile and run with **JDK 17**:

```bash
javac --release 17 SealedChildRoles.java
java SealedChildRoles
```

Output:

```text
Cash payment
Domestic bank transfer
International bank transfer
International bank transfer
Partner gateway payment
```

Reading level by level:

1. `Payment` is a `sealed interface`, granting direct permission only to `CashPayment`, `BankTransfer`, and `GatewayPayment`.
2. `CashPayment` uses `final`, so `class SpecialCashPayment extends CashPayment` is disallowed.
3. `BankTransfer` uses `sealed` to permit only `DomesticTransfer` and `ForeignTransfer` as direct subclasses.
4. `DomesticTransfer` uses `final`, blocking further inheritance.
5. `ForeignTransfer` uses `non-sealed`, allowing `PriorityForeignTransfer` to extend it without appearing in `BankTransfer`'s `permits`.
6. `GatewayPayment` uses `non-sealed`, allowing `CustomGatewayPayment` to extend it while **still being a `Payment`** through indirect inheritance.

Even though `PriorityForeignTransfer` and `CustomGatewayPayment` do not appear in `Payment`'s `permits` list, both are valid because neither is a **direct** subtype of `Payment`.

## 3. `final`: deliberately terminating a branch

### 3.1. When to use `final`?

A direct subclass of a `sealed` type uses `final` when the author wants to declare that type as an endpoint of the inheritance tree.

```java
sealed interface Payment permits CashPayment {
}

final class CashPayment implements Payment {
}
```

No new subclass can be created from `CashPayment`:

```java
// Invalid: CashPayment is already final.
class SpecialCashPayment extends CashPayment {
}
```

`final` does not forbid instantiating the class itself. If the class has an accessible constructor, you can still call `new CashPayment()`.

### 3.2. `final` does not mean data immutability

`final class` only prevents **inheritance**. An object's internal state can still change if the class exposes fields or methods that allow it:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

A `Counter` can still increment `value`, even though no class can inherit from it. Likewise, `final` on variables and `final` on methods have distinct meanings; this lesson focuses on **`final` on classes**.

### 3.3. Notes on `record` and `enum`

A `record` is **implicitly `final`**, so a `record` can directly implement a `sealed interface` without writing the `final` modifier:

```java
sealed interface Result permits Success, Failure {
}

record Success(String data) implements Result {
}

record Failure(String reason) implements Result {
}
```

This is valid Java 17 code. You do not need to write `final` before `record` because the language implies it, though Java allows writing `final` explicitly (redundantly). Conversely, a `record` cannot be declared `sealed` or `non-sealed`. A `record` can implement a `sealed interface`, but cannot `extends` any `sealed` class because records have their own language-defined class inheritance structure.

`enum` also has implicit language rules: depending on its structure, an enum is treated as `final` or `sealed`, so it can be permitted to directly implement a `sealed interface` without explicitly writing one of the three modifiers. For **regular classes**, declare the desired modifier explicitly.

## 4. `sealed`: continuing control over subsequent inheritance tiers

If a branch needs to split into known subtypes and you still want to control that list, declare the subclass as `sealed`:

```java
sealed interface Message permits SystemMessage {
}

abstract sealed class SystemMessage implements Message
        permits WarningMessage, InformationMessage {
}

final class WarningMessage extends SystemMessage {
}

final class InformationMessage extends SystemMessage {
}
```

Here there are **two separate checkpoints**:

- `Message` decides which types directly implement `Message`: only `SystemMessage`.
- `SystemMessage` decides which classes directly extend it: `WarningMessage` and `InformationMessage`.

Another class cannot arbitrarily `extends SystemMessage` if it is not in `SystemMessage`'s `permits`. Each direct subclass must in turn choose `final`, `sealed`, or `non-sealed` (except where the language defines an implicit modifier).

### Does `sealed` have to be paired with `abstract`?

**No.** A `sealed class` can be concrete or abstract, depending on the data model.

- `abstract sealed class` fits when the superclass represents only a general concept and should not be instantiated directly.
- A non-`abstract` `sealed class` can still be instantiated if its constructor allows it; `sealed` only restricts subclasses.

Conversely, **`final` and `abstract` cannot be applied together to the same class** because an abstract class needs to be completable via subclasses, whereas `final` forbids all subclasses.

### `sealed` interfaces work similarly

A direct subinterface of a `sealed interface` can itself remain `sealed`:

```java
sealed interface Device permits NetworkDevice {
}

sealed interface NetworkDevice extends Device
        permits Router, Switch {
}

final class Router implements NetworkDevice {
}

final class Switch implements NetworkDevice {
}
```

An interface cannot be declared `final`. If an interface is a direct subtype of a `sealed interface`, it chooses **`sealed` or `non-sealed`** to determine how other interfaces or classes may continue implementing it.

## 5. `non-sealed`: reopening extensibility

When you want library users or other application modules to create additional subtypes along a branch, a directly permitted class or interface can use `non-sealed`.

```java
sealed interface Notification
        permits SystemNotification, ExtensionNotification {
}

final class SystemNotification implements Notification {
}

// Reopen the branch for application-defined notification types.
non-sealed class ExtensionNotification implements Notification {
}

class EmailExtension extends ExtensionNotification {
}

class SmsExtension extends ExtensionNotification {
}
```

`SystemNotification` is closed to further inheritance. `ExtensionNotification` allows adding types like `EmailExtension` and `SmsExtension` without modifying `Notification`.

### Opening a branch does not mean every class anywhere can extend it

`non-sealed` **lifts the restriction imposed by the `sealed` ancestor on that branch**, yet other Java rules still apply: `public`/package-private visibility, constructor accessibility, implementing abstract methods, module limits, and so on.

Moreover, **subclasses of a `non-sealed class` must not keep writing `non-sealed`** unless they also have another direct superclass or superinterface that is `sealed`. For example:

```java
class EmailExtension extends ExtensionNotification {
}

// Invalid if only extending ExtensionNotification:
// non-sealed class SmsExtension extends ExtensionNotification { }
```

`non-sealed` does not mean "a regular class allowed to have subclasses." It is a modifier used **specifically where you declare reopening a branch directly constrained by a `sealed` type**.

A deeper subclass can still declare `final` to stop inheritance there, or `sealed` with `permits` to control **its own direct subclasses**. However, doing so does not close any other branches already opened from `ExtensionNotification`.

### `non-sealed` on interfaces

`non-sealed` is not limited to classes:

```java
sealed interface Event permits InternalEvent, PublicEvent {
}

record InternalEvent(String id) implements Event {
}

non-sealed interface PublicEvent extends Event {
}

// No modifier needed because PublicEvent is already non-sealed.
interface PartnerEvent extends PublicEvent {
}

class PartnerCreatedEvent implements PartnerEvent {
}
```

`PartnerCreatedEvent` is still an `Event`, arriving via the reopened `PublicEvent` branch.

## 6. Why does Java force direct subclasses to choose a state?

Suppose Java allowed this code:

```java
// INVALID EXAMPLE — does not compile in Java 17.
sealed interface Task permits BackgroundTask {
}

class BackgroundTask implements Task {
}
```

If `BackgroundTask` were implicitly extensible like a normal class, the author of `Task` might unintentionally allow grandchild classes to grow without deliberate design. Java 17 requires the direct subclass to state its intent clearly, for example:

```java
final class BackgroundTask implements Task {
}
```

or:

```java
non-sealed class BackgroundTask implements Task {
}
```

To continue controlling it, use `sealed` and define the subclasses of `BackgroundTask`.

This rule makes the design decision readable directly in the type declaration: readers know whether a branch is closed, controlled, or reopened.

## 7. Key rules accompanying `permits`

### 7.1. List only direct subtypes

```java
sealed class Parent permits Child {
}

non-sealed class Child extends Parent {
}

class Grandchild extends Child {
}
```

`Parent` must permit `Child`; **there is no need to list `Grandchild`**. `Grandchild` does not directly `extends Parent`.

Conversely, naming a type that **does not inherit directly** in `permits` does not make it a valid direct subtype.

### 7.2. Module/package location of permitted types

Permitted direct subtypes must adhere to Java's location rules:

- If the `sealed` type is in a **named module**, permitted types must belong to the **same module**. They may reside in different packages within that module as long as access rules are met.
- If the `sealed` type is in an **unnamed module**, permitted types must be in the **same package**.

Thus, `permits` is not a mechanism to directly open a `sealed class` to arbitrary classes in external modules. To let other applications extend it, design a `non-sealed` branch as an extension point.

### 7.3. When can `permits` be omitted?

If direct subtypes are declared in the **same compilation unit (same source file)** as the `sealed` type, Java can infer the permitted list when you omit `permits`:

```java
sealed interface EventType {
}

final class Created implements EventType {
}

non-sealed class Updated implements EventType {
}
```

In this example, the compiler infers `Created` and `Updated` as the permitted types. When code spans multiple files, declare `permits` explicitly to specify the inheritance contract. Explicit declarations are often easier to read when the hierarchy has multiple branches.

### 7.4. Do not combine mutually exclusive modifiers

For a class, `final`, `sealed`, and `non-sealed` are three mutually exclusive choices for inheritance policy. You cannot combine them as `final sealed class ...` or `sealed non-sealed class ...`.

A regular class **with no `sealed` direct parent or interface** also cannot arbitrarily declare `non-sealed`. If no control is involved, use a regular `class`.

## 8. Common errors and how to fix them

Snippets in the "invalid" column are isolated error illustrations, not a single file meant to compile together.

| Situation | Why invalid or misleading | How to handle |
|---|---|---|
| `class Child extends SealedParent` even though in `permits` | `Child` is a direct subclass that has not chosen an inheritance status | Add **one** of `final`, `sealed`, `non-sealed` |
| `class Stranger extends SealedParent` not in `permits` | `sealed` forbids unauthorized direct subtypes | Update the design/valid `permits` list, or go through an appropriate `non-sealed` branch |
| `class Child extends FinalChild` | `final` forbids all subclasses | Use another appropriate relationship; do not extend a `final` class |
| `non-sealed class Ordinary { }` | No `sealed` direct supertype | Use `class Ordinary { }` |
| `final interface Sub extends SealedInterface` | Interfaces do not support `final` | Use `sealed interface` or `non-sealed interface` |
| `sealed class Child extends Parent { }` with no permitted subtypes | `sealed` requires a valid set of direct subtypes | Declare `permits` and subtypes, or change `Child` to `final`/`non-sealed` as intended |
| Placing a permitted direct type in another module | Same-named-module or same-package (unnamed module) rule not met | Move the type into valid scope or extend via an accessible `non-sealed` branch |
| Using `--enable-preview` to run Java 17 `sealed` examples | Causes confusion about feature status | Remove the preview flag; `sealed` is standard in Java 17 |

**Tip for reading errors:** When encountering a compiler message about `sealed`, check in order: does the parent's `permits` include the child, is the inheritance relationship **direct**, has the subtype chosen a status modifier, and are module/package boundaries respected?

## 9. Designing an appropriate inheritance tree

Never assume an entire tree must be closed or entirely open. A `sealed` tree can combine multiple policies simultaneously:

| Business need | Choice at subtype class/interface | Reason |
|---|---|---|
| Domain type is complete and needs no inheritance variants | `final class`, or `record` where suitable | Keeps a clear terminal branch |
| Still has a tightly controlled set of subtypes | `sealed class/interface` | Opens a new inheritance tier with a permitted list |
| Must support extensions/plugins or integrator-defined data types | `non-sealed class/interface` | Deliberately opens extension for a branch |
| Subclass is an abstract concept not meant for direct instantiation | `abstract sealed class` or `abstract non-sealed class` | Expresses abstraction while controlling or opening inheritance |
| Only need normal inheritance without a closed set of types | Regular `class`/`interface` | Avoids unnecessary `sealed` constraints |

### Impact when changing the inheritance tree

The `permits` list and subtype modifiers are part of the **public API design**. Changing `non-sealed` to `final` or `sealed` can break user code that relied on extensibility. Adding a new type to a `sealed` tree can also affect places that handle all cases exhaustively.

In modern Java releases, `sealed` trees are especially valuable for exhaustiveness checking in `switch` pattern matching. Still, keep versions distinct: **pattern matching for `switch` in Java 17 is still preview**, whereas sealed classes are standard; pattern matching for `switch` became standard in Java 21 ([JEP 441](https://openjdk.org/jeps/441)). Examples in this lesson rely on no preview features.

## 10. Practice exercises

### Exercise 1 — Choose modifiers

Given `sealed interface Command permits Start, Stop, PluginCommand`:

1. `Start` must not allow new subtypes.
2. `Stop` must have only two sub-variants: `GracefulStop` and `ForceStop`.
3. `PluginCommand` must let plugins define additional commands.

**Hint:** Choose `final`, `sealed`, and `non-sealed` respectively. For `Stop`, declare `permits GracefulStop, ForceStop`, and give both subclasses appropriate modifiers as well.

### Exercise 2 — Find the errors

```java
sealed interface ApiResult permits OkResult, ErrorResult {
}

class OkResult implements ApiResult {
}

non-sealed class ErrorResult implements ApiResult {
}

non-sealed class CustomError extends ErrorResult {
}
```

There are two errors to spot:

1. `OkResult` is a direct subtype of `ApiResult` but does not declare `final`, `sealed`, or `non-sealed`.
2. `CustomError` cannot be declared `non-sealed` just because it extends `ErrorResult`; its direct superclass `ErrorResult` is `non-sealed` and it has no `sealed` direct superinterface in this declaration.

One fix is declaring `final class OkResult` and `class CustomError extends ErrorResult`.

### Exercise 3 — Explain indirect inheritance

Why is `CustomGatewayPayment` in the main example still a `Payment` even though it is not in `Payment.permits`?

**Answer:** `CustomGatewayPayment extends GatewayPayment`, while `GatewayPayment implements Payment` and is directly permitted by `Payment`. Because `GatewayPayment` is `non-sealed`, the indirect subclass is validly created.

## 11. Remember via three questions

For **each direct subtype** of a `sealed class/interface`, ask yourself:

1. **Do you want to block further inheritance?** Use `final` for classes (or `record`, which is implicitly `final`, when suitable).
2. **Do you want to allow inheritance, but only from a controlled list?** Use `sealed` with an appropriate `permits` list.
3. **Do you want others to add further subtypes?** Use `non-sealed`, keeping in mind that Java accessibility rules still apply.

These three decisions keep the inheritance contract clear at every level while staying flexible on the exact branches designed for extension.

## 12. References

- [Oracle Java 17 — Sealed Classes](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): rules for `permits`, `final`, `sealed`, `non-sealed`, `record`, and module/package boundaries.
- [Oracle Java 17 — Java Language Changes](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): confirms sealed classes as a standard feature in Java 17.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design goals and language rules.
- [Java Language Specification 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): specification of classes, inheritance, and modifiers.
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441): reference when exploring sealed hierarchies in Java versions where pattern matching for `switch` is standard.
