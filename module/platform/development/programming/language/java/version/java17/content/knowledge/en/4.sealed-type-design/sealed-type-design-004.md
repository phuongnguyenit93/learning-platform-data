# How `non-sealed` Affects Extension Boundaries in Java 17

In Java 17, `sealed` lets designers **restrict which types may directly extend a class or extend/implement an interface**. However, a system sometimes needs to keep its core domain controlled while still allowing applications or partners to add new types. The `non-sealed` keyword addresses that need by **reopening extension rights at a specific branch of the type hierarchy**.

This lesson analyzes how `non-sealed` changes extension boundaries, why a parent type can still remain `sealed` when one of its child branches is `non-sealed`, and how to design APIs to preserve behavioral contracts when unknown subtypes may exist.

> **Version context:** Sealed classes/interfaces and `non-sealed` are standard features of **Java 17** (JEP 409). The examples below use standard Java 17 syntax without requiring preview flags.

## 1. What Is an Extension Boundary?

Suppose a system has an interface `PaymentMethod`. If declared as a regular interface:

```java
interface PaymentMethod {
    void pay();
}
```

Any class with access to this interface can `implements PaymentMethod`. That is an **open boundary**: the designer does not control the set of types directly implementing `PaymentMethod`.

If replaced with a `sealed interface`:

```java
sealed interface PaymentMethod permits CashPayment, OnlinePayment {
    void pay();
}
```

then only the types **directly listed in `permits`** may directly implement or extend `PaymentMethod`:

- `CashPayment`
- `OnlinePayment`

Another type declaring `implements PaymentMethod` directly will be rejected if it is not in that list. This boundary is enforced at the language and JVM level, not merely by naming convention.

An important distinction: `sealed` controls the **direct subtype set**, not necessarily fixing every type at deeper levels of the entire inheritance tree. Each branch's extensibility depends on how that branch is declared.

## 2. Three Choices for a Direct Subtype

A type that directly extends or implements a `sealed` type must specify how it handles further extension rights:

| Sub-branch declaration | Meaning | Further subtyping capability |
| --- | --- | --- |
| `final class` | Completely closes the class branch here. | No class may `extends` this class. |
| `sealed class` / `sealed interface` | Continues restricting direct subtypes. | Only types listed in that branch's own `permits`. |
| `non-sealed class` / `non-sealed interface` | Removes the sealed restriction on extending this branch. | Accessible types may `extends`/`implements` under standard Java rules. |

With `final`, you cannot declare a `final interface`; a subinterface of a `sealed interface` typically chooses `sealed` or `non-sealed`. A `record` directly implementing a `sealed interface` is also valid because a record is inherently `final` under Java semantics.

Example:

```java
sealed interface Notification
        permits EmailNotification, SmsNotification, CustomNotification {
}

final class EmailNotification implements Notification {
}

sealed class SmsNotification implements Notification
        permits TransactionalSms {
}

final class TransactionalSms extends SmsNotification {
}

non-sealed interface CustomNotification extends Notification {
}
```

In this hierarchy:

- The `EmailNotification` branch stops immediately at a `final` class.
- The `SmsNotification` branch permits only `TransactionalSms` to extend it directly.
- The `CustomNotification` branch can accept additional implementations without adding them to `Notification.permits`.

This combination keeps the core domain constrained while reserving an intentionally designed extension point.

## 3. Which Branch Does `non-sealed` Open—and Which Does It Keep Closed?

Consider the following type tree:

```text
Notification  (sealed)
│
├── EmailNotification  (final)
│
├── SmsNotification  (sealed)
│   └── TransactionalSms  (final)
│
└── CustomNotification  (non-sealed interface)
    ├── AppPushNotification
    ├── PartnerNotification
    └── ... types added later
```

When `CustomNotification` is `non-sealed`, **only the branch beneath `CustomNotification` opens up for extension under standard rules**. That keyword does not automatically turn `Notification` into an open interface.

For example, the following declaration is valid:

```java
class AppPushNotification implements CustomNotification {
}
```

Whereas the declaration below is invalid because `Notification` is still `sealed` and `UnknownNotification` is not permitted as a direct child:

```java
// Intentionally NON-compilable example
class UnknownNotification implements Notification {
}
```

In other words, extenders must go through the **defined open gate** (`CustomNotification`) rather than adding arbitrary direct subtypes to the root type.

### `non-sealed` Does Not Restrict Deeper Levels Below It

Not only are direct implementations of `CustomNotification` allowed; deeper inheritance levels follow normal rules as well:

```java
class PartnerNotification implements CustomNotification {
}

class PriorityPartnerNotification extends PartnerNotification {
}
```

`PriorityPartnerNotification` is an **indirect** `Notification`; it does not need to appear in `Notification.permits`. If `PartnerNotification` is declared `final`, further extension of that class will be blocked by `final`, which is the subclass's own choice rather than a restriction coming back from `Notification`.

A type beneath an open branch can still explicitly declare itself `final` or `sealed` to govern its own subtree. Therefore, "open" does not mean every descendant class is forced to stay open.

## 4. Runnable Java 17 Example: Opening an Integration Point for Partners

Suppose a delivery system has a fixed in-store pickup option and partner-provided integration channels. Design requirements:

1. No one may add delivery types directly to `DeliveryMethod` outside the branches published by the core.
2. Partners can create new integration classes without editing `DeliveryMethod`'s `permits`.
3. Core code can handle all delivery methods in the integration branch through a shared contract.

Create the file `NonSealedDemo.java`:

```java
public class NonSealedDemo {
    public static void main(String[] args) {
        printMethod(new CounterDelivery());
        printMethod(new PartnerDelivery());
        printMethod(new AnotherPartnerDelivery());
    }

    static void printMethod(DeliveryMethod method) {
        if (method instanceof CounterDelivery) {
            System.out.println("In-store pickup");
        } else if (method instanceof ExtensionDelivery extension) {
            System.out.println("Integration: " + extension.providerName());
        }
    }
}

sealed interface DeliveryMethod
        permits CounterDelivery, ExtensionDelivery {
}

final class CounterDelivery implements DeliveryMethod {
}

non-sealed interface ExtensionDelivery extends DeliveryMethod {
    String providerName();
}

final class PartnerDelivery implements ExtensionDelivery {
    @Override
    public String providerName() {
        return "Partner A";
    }
}

final class AnotherPartnerDelivery implements ExtensionDelivery {
    @Override
    public String providerName() {
        return "Partner B";
    }
}
```

Compile and run:

```bash
javac NonSealedDemo.java
java NonSealedDemo
```

Output:

```text
In-store pickup
Integration: Partner A
Integration: Partner B
```

**Important point:** `PartnerDelivery` and `AnotherPartnerDelivery` do not appear in `DeliveryMethod.permits`. They implement `ExtensionDelivery`, meaning they participate in the **open branch** permitted by the API.

`instanceof ExtensionDelivery extension` is **pattern matching for `instanceof`**, already a standard feature before Java 17. It both checks the type and provides the variable `extension` to call `providerName()`. As a result, the handler code does not need to name each partner individually.

### Why Is This Useful for APIs?

With the method:

```java
static void printMethod(DeliveryMethod method)
```

the API can keep using the common `DeliveryMethod` parameter type. New partners only need to comply with `ExtensionDelivery`. The application core does not need an extra `if` branch for every partner class, provided the desired behavior is expressed through the methods of the `ExtensionDelivery` contract.

Conversely, if code hardcodes specific implementation classes—such as checking only `PartnerDelivery`—it will miss `AnotherPartnerDelivery` and types added later. `non-sealed` enables structural extension of types, yet **does not automatically guarantee that handler code supports every variant**.

## 5. `non-sealed class` vs. `non-sealed interface`: Similarities and Differences

An open branch can be a class or an interface, though the actual extension capabilities depend on which kind is chosen:

### Open Branch as a Class

```java
sealed abstract class AuditEvent
        permits SystemAuditEvent, UserAuditEvent {
}

final class SystemAuditEvent extends AuditEvent {
}

non-sealed class UserAuditEvent extends AuditEvent {
}

class LoginAuditEvent extends UserAuditEvent {
}

class FailedLoginAuditEvent extends LoginAuditEvent {
}
```

`UserAuditEvent` is a `non-sealed class`: other classes can `extends UserAuditEvent` if they satisfy normal access and constructor rules. `LoginAuditEvent` and `FailedLoginAuditEvent` do not need to appear in `AuditEvent.permits`.

Note: extending a class is still subject to the rule that **Java allows only one direct superclass**, and a superclass constructor must be accessible for subclass invocation.

### Open Branch as an Interface

```java
sealed interface ExportFormat permits BuiltInFormat, CustomFormat {
}

final class BuiltInFormat implements ExportFormat {
}

non-sealed interface CustomFormat extends ExportFormat {
    String fileExtension();
}

class CsvLikeFormat implements CustomFormat {
    @Override
    public String fileExtension() {
        return ".csv";
    }
}

interface ExtendedCustomFormat extends CustomFormat {
    String displayName();
}
```

`CustomFormat` is a `non-sealed interface`, so classes can `implements` it and other interfaces can `extends` it. A class can also implement multiple interfaces under standard rules. Depending on the problem, an interface is often well suited for publishing an extension point without forcing users to inherit from a base class.

## 6. Language Constraints That Still Apply

### 6.1. `non-sealed` Only Applies to Direct Subtypes of a `sealed` Type

You cannot arbitrarily attach `non-sealed` to an ordinary class or interface:

```java
// Invalid: Object is not a sealed class
non-sealed class FreeClass {
}
```

A type declared `non-sealed` must be a **direct subtype of at least one `sealed` type**. The following example is valid:

```java
sealed interface Command permits ExtendableCommand {
}

non-sealed interface ExtendableCommand extends Command {
}
```

However, a subsequent subtype must not arbitrarily write `non-sealed` merely because a distant ancestor is `sealed`:

```java
// Invalid: only directly extends a non-sealed interface
non-sealed interface ChildCommand extends ExtendableCommand {
}
```

In this case, simply declare `interface ChildCommand extends ExtendableCommand`, or explicitly use `sealed interface` with a `permits` list if you want to seal the sub-branch.

### 6.2. `permits` Rules Apply to Direct Children

Types listed in a `sealed` type's `permits` clause must actually be **direct subclasses/subinterfaces** of that type. In Java 17, direct subtypes must reside in the **same named module** as the `sealed` type; if the root type belongs to an **unnamed module**, they must reside in the **same package**. Declaring `non-sealed` does not bypass these rules at the direct connection point to the `sealed` parent.

Beyond that connection point, subtypes of a **`non-sealed` branch** no longer have to be listed in the ancestor's `permits`. For public APIs, the open branch can be implemented from another module or package if visibility, module dependencies, and type accessibility allow it.

### 6.3. `non-sealed` Does Not Override Access Control Rules

`non-sealed` does not turn a `package-private` type into `public`, does not make a `private` constructor accessible, does not expose a package hidden by JPMS, and does not allow extending a `final` class.

If a library wants code outside its module to extend an open branch, it must design appropriate accessibility: for example, a `public non-sealed interface` in a package `exports`-ed via `module-info.java`. When using a `non-sealed class`, accessible constructors must also meet subclassing needs.

## 7. An Important Shift in Type-Set Design Thinking

Distinguish between two assumptions:

**Assumption A — The root's direct subtype set is controlled:**

```text
DeliveryMethod = CounterDelivery | ExtensionDelivery
```

This holds true for the `sealed DeliveryMethod` declaration in the example. Others cannot directly add `NewDelivery implements DeliveryMethod` unless `NewDelivery` is permitted.

**Assumption B — All runtime types of `DeliveryMethod` consist only of two concrete classes:**

```text
DeliveryMethod = CounterDelivery | PartnerDelivery
```

This is **false** when the `ExtensionDelivery` branch is `non-sealed`: `AnotherPartnerDelivery` or countless new types can still be valid `DeliveryMethod` instances through the open branch.

| Design dimension | Branch closed with `final` or restricted further with `sealed` | Branch opened with `non-sealed` |
| --- | --- | --- |
| Set of types that may appear | Can be narrowed step by step via `permits` layers and `final`. | Number of implementations/descendants is unbounded. |
| External extension | Restricted to permitted direct types and any still-open branches. | Allows adding subtypes without editing the ancestor's `permits` list. |
| Handling logic | Can be designed around known variants. | Should program against the interface/contract and include fallback behavior for new types. |
| Library maintenance | Maintainers control the list of direct subtypes. | Branch extensibility must be treated as part of the public API. |
| Evolution risk | Changing the list or branch kind can affect dependent code. | New subclasses can appear that core code did not anticipate if it only checks familiar classes. |

Architecturally, `non-sealed` creates a **named, contract-backed extension path**: the development team defines exactly where new types may be added instead of having to leave the entire root interface open.

## 8. Impact on Branching and Type Checking in Java 17

When a branch is `non-sealed`, source code cannot assume it "has seen every implementation class." For example:

```java
static String describe(DeliveryMethod method) {
    if (method instanceof CounterDelivery) {
        return "In-store pickup";
    }
    if (method instanceof ExtensionDelivery extension) {
        return "From provider " + extension.providerName();
    }
    throw new IllegalStateException("Unsupported delivery method");
}
```

Here, the `ExtensionDelivery` branch uniformly handles **all types implementing the open branch**, including types added after `describe` was written. The final path is still retained as an explicit safeguard against unexpected cases.

If written as below, the code cannot guarantee support for the whole open branch:

```java
// Fragile design that misses new implementations:
if (method instanceof PartnerDelivery) {
    // Handles only one specific partner class
}
```

For objects in an open branch, prefer **invoking behavior published by the interface/abstract class** rather than depending on a list of concrete classes.

> **Version note:** Pattern matching for `instanceof` is standard syntax usable in Java 17. Pattern matching for `switch` is still in **preview in Java 17**; do not rely on it as a mandatory foundation for standard Java 17 examples. Also, do not confuse `sealed` knowing its "direct children" with automatically having a finite list of all implementations beneath a `non-sealed` branch.

## 9. Impact on Library, Plugin, and API Versioning Design

### 9.1. When a Library Exposes a `non-sealed` Branch

Suppose a library declares:

```java
public sealed interface Formatter
        permits StandardFormatter, PluginFormatter {
}

public non-sealed interface PluginFormatter extends Formatter {
    String format(String input);
}
```

In a real project, each `public` top-level type should live in its own correspondingly named Java file; the compact snippet above only illustrates type relationships. Implementations of `StandardFormatter` and any remaining `permits` entries must be completed within the library.

Users can add `class CustomFormatter implements PluginFormatter` wherever the interface is accessible. In return, the library must uphold the `format` contract: inputs, outputs, errors, invariants, and data expectations must be documented clearly enough so new implementations do not break behavior.

Key points when designing extension points:

- **Define the minimum contract:** which methods are required and what behavior must be guaranteed?
- **Minimize implementation coupling:** prefer interface types over checking concrete class names.
- **Mind compatibility:** changing a `non-sealed` branch to `sealed` or `final` can break external code that extends it during recompilation or class loading.
- **Maintain business guardrails:** validate permissions, data, and invariants at appropriate handling points; `non-sealed` only governs type structure and does not validate extension code.
- **Design extension points intentionally:** open only the branches needed for feature growth rather than leaving the entire domain model open.

### 9.2. `non-sealed` Is Not a Plugin Loading Mechanism

`non-sealed` only governs **inheritance/implementation permissions in the type system**. It does not by itself:

- discover implementation classes on the classpath/module path;
- instantiate objects of those classes;
- register them into the system;
- guarantee that every implementation respects the interface's business semantics.

To discover and load plugins, an application still needs a dedicated mechanism such as configuration, dependency injection, or Java's `ServiceLoader` when appropriate. The `non-sealed` keyword determines **whether a subtype may be created**, while the plugin system determines **how that subtype is found and used**.

### 9.3. You Cannot Rely on `non-sealed` to Isolate Untrusted Code

A partner can implement an open branch yet produce unexpected behavior. `non-sealed` imposes no security boundary, validates no data, and guarantees no safety of executing code. If an extension point receives sensitive data or performs privileged operations, the system still needs appropriate authentication, authorization, input validation, and execution controls.

## 10. Should You Choose `final`, `sealed`, or `non-sealed`?

When building a type tree from a `sealed` root, you can choose a policy per branch:

| Practical need | Appropriate choice | Example |
| --- | --- | --- |
| Disallow subclassing of an implementation | `final class` | `CounterDelivery` has fixed semantics. |
| Allow only a defined set of subtypes | `sealed class` or `sealed interface` | Internal branch with explicit `permits`. |
| Publish an extension point for apps/partners to add types | `non-sealed interface` | `ExtensionDelivery` for multiple providers. |
| Let user code inherit and reuse base state/behavior | `non-sealed class` | `UserAuditEvent` as an open base class. |
| No need to manage subtypes from the root | Regular class/interface | Fully open model under standard Java rules. |

Several questions to ask before choosing `non-sealed`:

1. **Who will create new subclasses/implementations?** If only internal code uses them and the kinds are known, `final` or `sealed` branches may be easier to govern.
2. **Does handler code depend on knowing every concrete type?** If so, opening a branch makes that assumption unsafe.
3. **Is the contract for new implementations clear enough?** When handing an extension point to external code, behavior and invariants matter more than a list of class names.
4. **Does the API ensure visibility from where extension is needed?** A `non-sealed` type that is invisible from consuming modules provides no useful extensibility.
5. **Are you prepared to maintain that extension point long-term?** Narrowing a branch previously published as open can break library users.

## 11. Common Misconceptions

| Claim | Truth in Java 17 |
| --- | --- |
| "A `sealed` parent can never have new descendants." | The parent restricts only **direct children**; a `non-sealed` branch can gain new descendants. |
| "Making one child `non-sealed` opens all branches of the parent." | Only the branch passing through that child is opened; the parent's `permits` remains enforced. |
| "Adding a partner requires editing the root's `permits`." | Not needed if the partner implements an allowed `non-sealed` branch. |
| "You can put `non-sealed` in front of any class." | No; it requires a **direct child** relationship to at least one `sealed` type. |
| "`non-sealed` automatically makes a class `public`." | No; visibility modifiers and module rules still apply. |
| "`sealed` guarantees an `if` handles every implementation." | No; a `non-sealed` branch can hold new implementations not anticipated by handler code. |
| "`non-sealed` automatically registers plugins into the app." | No; discovering and instantiating plugins is a separate architectural responsibility. |

## 12. Self-Practice Exercises

**Exercise 1 – Predicting Inheritance Capability**

```java
sealed interface Media permits Photo, Video {
}

final class Photo implements Media {
}

non-sealed interface Video extends Media {
}

class OnlineVideo implements Video {
}
```

Consider:

- Can you add `class NewPhoto extends Photo`? **No**, because `Photo` is `final`.
- Can you add `class OfflineVideo implements Video`? **Yes**, if access rules are met.
- Can you add `class Audio implements Media` directly? **No**, because `Audio` is not in `Media.permits`.

**Exercise 2 – Designing an Extension Point**

An application needs to model `ReportSource` with two branches: `DatabaseSource` as a fixed internal source and `ExternalSource` allowing multiple third-party services. Do the following:

1. Declare `sealed interface ReportSource` with two direct child branches.
2. Choose `final` for the fixed source and `non-sealed interface` for the open source.
3. Define a common method in `ExternalSource` for every partner to implement.
4. Create two classes implementing `ExternalSource` and a handler method working against the open-branch contract without checking individual partner classes.

**Exercise 3 – Analyzing an API Change**

A library published `public non-sealed interface ExtensionPoint`, and users have classes that `implements ExtensionPoint`. If a new version changes `ExtensionPoint` to `sealed`, what problems might external classes encounter? Explain why this is not just a stylistic change, but potentially an **API extensibility breaking change**.

## Conclusion

`sealed` sets a boundary at **direct subtypes**, while `non-sealed` is a decision to **reopen extension rights at a specific branch**. Combining `sealed` + `final` + `non-sealed` helps build Java 17 models with a controlled core and integration points that can still evolve independently. When choosing `non-sealed`, design clear behavioral contracts, program against abstractions, and account for new implementations appearing in the future.

### References

- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — standard Java 17 feature, covering `sealed`, `permits`, and `non-sealed`.
- [Java Language Specification, Java SE 17 — Chapter 8: Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html) — modifier and class inheritance rules.
- [Java Language Specification, Java SE 17 — Chapter 9: Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html) — interface and sealed interface rules.
- [JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394) — `instanceof` syntax used in the examples.
