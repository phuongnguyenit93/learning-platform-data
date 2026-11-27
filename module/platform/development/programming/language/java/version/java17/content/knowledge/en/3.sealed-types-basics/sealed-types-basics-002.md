# Comparing Open Hierarchies, `final`, and `sealed` in Java 17

**Topic:** Java 17 — Sealed Basics  
**Lesson:** Comparing open hierarchies, `final`, and `sealed`

When designing an object-oriented system, an important question is: **who is allowed to create a subclass or implement a type's interface?** In Java 17, there are three common ways to control the extensibility of a type hierarchy:

- **Open hierarchy:** A class or interface allows other valid types to inherit or implement it under standard accessibility rules.
- **`final`:** Prevents any other class from inheriting a **class** marked `final`.
- **`sealed`:** Restricts **which direct subtypes** are allowed to inherit a class or implement an interface, while still allowing multiple sub-branches to be designed with different extensibility levels.

`final` has existed in Java for a long time. `sealed` classes and interfaces were standardized in **Java 17** via JEP 409, following preview phases in Java 15 and 16. Java 17 has no `open` keyword for regular classes; "open hierarchy" simply describes a design that remains open to extension.

## 1. Visualizing the differences

Suppose an application needs to represent several types of request processing results:

```text
Open hierarchy:
Result
├── Success
├── Failure
├── Waiting
└── ... (additional implementations may appear)

Final class:
FinalResult
└── (cannot have subclasses)

Sealed hierarchy:
Result (sealed)
├── Success (final)
├── Failure (final)
└── Waiting (non-sealed)
    ├── WaitingForBank
    └── ... (this branch can be extended)
```

In an open hierarchy, the author of `Result` does not control all future subclasses. With `final`, the author completely closes subclassing. With `sealed`, the author selects a list of **direct subtypes**, then specifies whether each branch is closed, further restricted, or reopened.

Key point: **`sealed` restricts one direct inheritance level**. It does not automatically close every subtype at every depth.

## 2. Overview comparison table

| Criterion | Open hierarchy | `final` class | `sealed` hierarchy |
|---|---|---|---|
| Typical declaration | `class A`, `interface A` | `final class A` | `sealed class A permits ...` or `sealed interface A permits ...` |
| Direct subtypes allowed? | Yes, if inheritance and access rules are met | No | Only permitted subtypes |
| Fixed list of direct subtypes? | No | No subtypes | Yes |
| Can allow deeper extension? | Yes | Not through the `final` class itself | Yes, via a `non-sealed` branch or a nested `sealed` hierarchy |
| Usable on `interface`? | Yes | Cannot declare `final interface` | Yes |
| Suitable when | External parties should freely add behavior or plugins | A type must not be subclassed | You want explicit control over domain model variants |
| Common design risk | Hard to control all externally added subtypes | Hard to customize via inheritance | Can overly restrict API extensibility if `permits` is too tight |
| Status in Java 17 | Pre-existing mechanism | Pre-existing mechanism | Standard language feature as of Java 17 |

The inheritance capabilities compared above remain subject to Java's foundational rules: visibility of classes, constructors, packages, modules, and other language constraints. "Open" does **not** mean any code anywhere can subclass any class.

## 3. Open hierarchy: prioritizing extensibility

### 3.1. Simple declaration

```java
interface PaymentMethod {
    String code();
}

class CardPayment implements PaymentMethod {
    @Override
    public String code() {
        return "CARD";
    }
}

class BankTransfer implements PaymentMethod {
    @Override
    public String code() {
        return "BANK_TRANSFER";
    }
}
```

Here, `PaymentMethod` is a regular interface. Another implementation can be added later:

```java
class WalletPayment implements PaymentMethod {
    @Override
    public String code() {
        return "WALLET";
    }
}
```

There is no need to modify `PaymentMethod` to introduce another valid implementation into the system. An integration library or plugin module can use this mechanism if the interface is properly exposed.

Regular classes can also be extended:

```java
class Notification {
    public String message() {
        return "General notification";
    }
}

class EmailNotification extends Notification {
    @Override
    public String message() {
        return "Email notification";
    }
}
```

In the example above, `Notification` has neither `final` nor `sealed`, so it can be inherited when standard rules are satisfied.

### 3.2. When should you keep a hierarchy open?

An open hierarchy fits when **allowing additional subtypes is an intentional design requirement**:

- Library APIs where client applications supply their own implementations.
- Plugins, drivers, adapters, or user-extensible processing strategies.
- Abstractions designed as stable, well-documented extension points.

For instance, a payment system supporting external providers may let partners implement `PaymentMethod` as needed. Leaving a type unsealed does not by itself guarantee a good extension point: if the API contract is vague, has too many mandatory methods, or the class relies on fragile internal details, subclasses can still easily break assumptions.

### 3.3. Limitations of an open hierarchy

Suppose you have this handling logic:

```java
static String describe(PaymentMethod method) {
    if (method instanceof CardPayment) {
        return "Card payment";
    }
    if (method instanceof BankTransfer) {
        return "Bank transfer";
    }
    return "Other method";
}
```

`PaymentMethod` could have `WalletPayment` or classes not yet defined when the method was written. If the development team **assumes there are only two kinds**, the type system does not protect that assumption.

When publishing an extensible class, you must specify which methods may be overridden, which invariants must hold, and how to evolve the API without breaking third-party subclasses. Leaving a class unintentionally open without actually needing inheritance can introduce unnecessary complexity.

## 4. `final`: closing inheritance for a class

### 4.1. Declaration

```java
final class ReceiptNumber {
    private final String value;

    ReceiptNumber(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    String value() {
        return value;
    }
}
```

The `ReceiptNumber` class cannot be extended with `extends`:

```java
// INVALID: cannot inherit from a final class.
class SpecialReceiptNumber extends ReceiptNumber {
    SpecialReceiptNumber() {
        super("SP-001");
    }
}
```

The Java compiler rejects this subclass because `ReceiptNumber` is marked `final`. This is a decision about **type structure**, not a user access-permission mechanism.

### 4.2. What does `final` protect?

A `final` class is often chosen when:

- The type has standalone meaning and has no need for subclasses.
- The author wants to prevent subclasses from altering behavior or breaking class invariants.
- The object is designed as a value object using composition rather than inheritance.
- A public API does not want to commit to supporting override behavior across future releases.

For example, many value-representing classes like `String` and `Integer` are `final`. A `record` is also implicitly `final`, so a record class cannot be subclassed.

Distinguish three uses of the `final` keyword:

| Declaration | What is restricted |
|---|---|
| `final class X` | No class may `extends X` |
| `final void process()` | Subclasses may not override the `process` method |
| `final int n = 10` | The variable may only be assigned once under Java rules |

**`final class` does not automatically guarantee object immutability.** A `final` class can still contain mutable fields, setters, or references to mutable collections:

```java
final class Counter {
    private int count;

    void increment() {
        count++;
    }

    int getCount() {
        return count;
    }
}
```

`Counter` is `final` yet still has mutable state. If immutability is needed, it must be designed through fields, referenced objects, constructors, and methods.

### 4.3. What `final` does not forbid

`final` does **not** mean a class cannot implement interfaces:

```java
interface Exporter {
    void exportData();
}

final class CsvExporter implements Exporter {
    @Override
    public void exportData() {
        System.out.println("Export CSV");
    }
}
```

`CsvExporter` validly implements `Exporter`; only another class attempting `extends CsvExporter` is disallowed.

Java does not support `final interface` because an interface inherently represents a contract for implementing types. If you want to **restrict which types may implement it**, consider `sealed interface`.

A class cannot be declared both `final` and `abstract`: `abstract` requires subclassing to complete behavior, whereas `final` forbids subclassing that class.

## 5. `sealed`: closing the list of direct subtypes

### 5.1. Example with `sealed interface`

```java
sealed interface PaymentResult permits Paid, Rejected, Pending {}

record Paid(String transactionId) implements PaymentResult {}

record Rejected(String reason) implements PaymentResult {}

final class Pending implements PaymentResult {}
```

Three **direct** implementations of `PaymentResult` are permitted:

- `Paid` is a record, implicitly `final`.
- `Rejected` is a record, implicitly `final`.
- `Pending` is explicitly declared `final`.

A fourth type not in `permits` is rejected at compile time:

```java
// INVALID: OutsideResult is not permitted by PaymentResult.
class OutsideResult implements PaymentResult {}
```

With a `sealed interface`, the `implements` keyword in implementing classes creates the direct subtype relationship. With a `sealed class`, direct subclasses use `extends`.

### 5.2. Example with `sealed class`

```java
abstract sealed class Document permits PdfDocument, TextDocument {
    abstract String format();
}

final class PdfDocument extends Document {
    @Override
    String format() {
        return "PDF";
    }
}

final class TextDocument extends Document {
    @Override
    String format() {
        return "TEXT";
    }
}
```

In this example, `Document` is both `abstract` and `sealed`. This is valid: `abstract` prevents creating an instance of `Document` directly, while `sealed` restricts **which classes may `extends Document`**.

`sealed` **does not automatically make a type `abstract`**. A non-`abstract` `sealed` class can still be instantiated directly if its constructor is accessible and other Java rules permit it.

### 5.3. Rules of `permits`

In Java 17, the key rules to grasp are:

1. The `permits` list refers to **direct subtypes**, not every descendant at all depths.
2. Each named type must actually `extends` or `implements` the corresponding `sealed` type directly.
3. In a **named module**, the `sealed` type and its permitted direct subtypes must be in the same module; they may be in different packages within that module.
4. In an **unnamed module** (e.g., ordinary Java files without a module declaration), permitted direct subtypes must be in the same package as the `sealed` type.
5. Each direct subtype must choose how the hierarchy continues using `final`, `sealed`, or `non-sealed`. Records are permitted as direct subtypes and are implicitly `final`.
6. The `permits` clause may be omitted when valid direct subtypes are declared in the same compilation unit as the `sealed` type; the compiler infers the list. Writing `permits` explicitly still helps readers see the model boundaries right at the declaration.

Example valid structure in an unnamed module:

```text
src/com/example/payments/
├── PaymentResult.java       (sealed interface PaymentResult)
├── Paid.java                (record Paid implements PaymentResult)
└── Rejected.java            (record Rejected implements PaymentResult)
```

If `Rejected` is moved to another package, simply keeping the three files under the same source folder is not enough. The corresponding module/package rule must be considered.

## 6. Three choices for each subtype of `sealed`

Java 17 requires a direct subtype to explicitly decide its further extensibility.

### 6.1. `final`: terminating the branch

```java
sealed interface TaskState permits Completed, Running {}

final class Completed implements TaskState {}

final class Running implements TaskState {}
```

`Completed` and `Running` are both terminal branches with no subclasses beneath them.

### 6.2. `sealed`: continuing restriction at the next level

```java
sealed interface Message permits UserMessage, SystemMessage {}

sealed interface UserMessage extends Message
        permits TextMessage, ImageMessage {}

final class TextMessage implements UserMessage {}

final class ImageMessage implements UserMessage {}

final class SystemMessage implements Message {}
```

The hierarchy has two restricted levels:

```text
Message (sealed)
├── UserMessage (sealed)
│   ├── TextMessage (final)
│   └── ImageMessage (final)
└── SystemMessage (final)
```

Each `sealed` type manages **its own list of direct subtypes**. This allows the hierarchy to grow with clear structure without cramming every variant into a single list at the root.

### 6.3. `non-sealed`: reopening a branch

```java
sealed interface Delivery permits InHouseDelivery, PartnerDelivery {}

final class InHouseDelivery implements Delivery {}

non-sealed class PartnerDelivery implements Delivery {}

class ExpressPartnerDelivery extends PartnerDelivery {}

class EconomyPartnerDelivery extends PartnerDelivery {}
```

Although `Delivery` allows only two direct subtypes, `PartnerDelivery` allows other classes to continue inheriting from it. Thus, the set of **all objects of type `Delivery`** is not limited to just two concrete classes.

`non-sealed` makes sense when you want the **model root controlled** while dedicating one branch as an extension point. In partner-integration systems, this can balance domain governance with plugin extensibility.

Do not use `non-sealed` as a decorative keyword on arbitrary classes. It is only appropriate on a direct subtype of a `sealed` type (via direct `extends` or `implements`) to lift the inheritance restriction on that branch.

### 6.4. Comparing two sealed models

**Closing the entire tree:**

```text
Result (sealed)
├── Success (final)
├── Failure (final)
└── Timeout (final)
```

When every branch ends in `final`, the application can treat the set of concrete types as a controlled finite list.

**Closing the root, opening one branch:**

```text
Result (sealed)
├── Success (final)
├── Failure (final)
└── ExtensionResult (non-sealed)
    ├── PluginResultA
    └── PluginResultB
```

In the second approach, API users can still create new result types via `ExtensionResult`. Therefore, the statement "`sealed` always closes the entire hierarchy tree" is **inaccurate**.

## 7. Complete example running on Java 17

The following example brings all three options together in one program. Create **`HierarchyComparisonDemo.java`**:

```java
public class HierarchyComparisonDemo {

    // 1. OPEN HIERARCHY: a regular class allows extends.
    static class OpenNotification {
        String text() {
            return "General notification";
        }
    }

    static class EmailNotification extends OpenNotification {
        @Override
        String text() {
            return "Email notification";
        }
    }

    // 2. FINAL: cannot extend this class.
    static final class NotificationId {
        private final String value;

        NotificationId(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    // 3. SEALED: only three direct subtypes are permitted.
    sealed interface ProcessResult
            permits Success, Failure, Pending {}

    // Records are implicitly final (standard feature since Java 16).
    record Success(String receipt) implements ProcessResult {}
    record Failure(String reason) implements ProcessResult {}

    // Reopen the Pending branch for specific pending kinds.
    static non-sealed class Pending implements ProcessResult {
        String description() {
            return "Processing";
        }
    }

    static final class PendingAtBank extends Pending {
        @Override
        String description() {
            return "Waiting for bank";
        }
    }

    static String describe(ProcessResult result) {
        // Pattern matching for instanceof has been standard since Java 16.
        if (result instanceof Success success) {
            return "Success: " + success.receipt();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.reason();
        }
        if (result instanceof Pending pending) {
            return pending.description();
        }
        throw new IllegalStateException("Unsupported result type");
    }

    public static void main(String[] args) {
        OpenNotification notification = new EmailNotification();
        NotificationId id = new NotificationId("NTF-17");

        System.out.println(id.value() + ": " + notification.text());
        System.out.println(describe(new Success("PAY-001")));
        System.out.println(describe(new Failure("Invalid data")));
        System.out.println(describe(new PendingAtBank()));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 HierarchyComparisonDemo.java
java HierarchyComparisonDemo
```

Output:

```text
NTF-17: Email notification
Success: PAY-001
Failure: Invalid data
Waiting for bank
```

The example uses `sealed` (standard in Java 17), `record`, and pattern matching for `instanceof` (standard since Java 16). **No preview flags needed**.

**Note on `switch`:** Java 17 already has standard `switch` expressions (since Java 14), but **pattern matching for `switch`** in Java 17 is still *preview* (JEP 406). Therefore, the example uses `instanceof` to distinguish variants instead of writing `switch (result) { case Success s -> ... }` as default Java 17 syntax.

## 8. When to choose which?

The design problem dictates the choice, rather than defaulting every class to `sealed` or `final`.

| Real-world scenario | Choice to consider | Reason |
|---|---|---|
| Public library letting external developers write custom adapters | Regular interface | Allows adding implementations without modifying the library |
| Class representing an identifier, needing to prevent subclasses with altered semantics | `final class`, or `record` if suitable | Disallows inheriting value-representing classes |
| Processing result with only a few business cases defined by the owning module | `sealed interface` with `final` branches | Turns the direct subtype set into an explicit contract |
| Event model with system-controlled groups and a plugin-reserved group | `sealed` at root, one `non-sealed` branch | Limits top-level groups while still supporting extensions |
| Multi-level expression tree where each level accepts only defined variants | Nested `sealed` across levels | Manages extension boundaries at every tier |
| Simple fixed set of choices without per-choice data types | `enum` | Easily represents constant sets and dispatches by value |
| Varying behavior without tying into an inheritance tree | Composition via fields/interfaces | Reuses behavior without extending classes |

### 8.1. Comparing `sealed` with `enum`

An `enum` fits a finite set of choices where every case shares the same data shape:

```java
enum RequestStatus {
    NEW, PROCESSING, DONE, FAILED
}
```

`sealed` fits when variants **carry different data or behavior**:

```java
sealed interface ApiResponse permits OkResponse, ErrorResponse {}

record OkResponse(String data) implements ApiResponse {}

record ErrorResponse(int statusCode, String detail)
        implements ApiResponse {}
```

Instead of creating an enum with many fields that are nullable depending on the case, distinct records describe the required data for each variant. However, `sealed` is not always better than `enum`; choose the simplest structure that accurately reflects the domain.

### 8.2. Comparing `final` with composition

Extending behavior does not necessarily require `extends`. For example:

```java
interface PricingRule {
    long calculate(long basePrice);
}

final class OrderPricing {
    private final PricingRule rule;

    OrderPricing(PricingRule rule) {
        this.rule = rule;
    }

    long total(long basePrice) {
        return rule.calculate(basePrice);
    }
}
```

`OrderPricing` is `final`, yet its behavior can be customized through `PricingRule`. Thus, **closing a class's inheritance does not mean closing configurability or replaceable behavior**.

## 9. Impact on APIs and codebase maintenance

### 9.1. An open hierarchy is an extensibility commitment

If you release `public class BaseService` allowing inheritance, external code may already have created subclasses and overridden methods. Changing that class to `final` or `sealed` in a later library version can cause user code **not to compile** or lose binary/runtime compatibility.

Before tightening a hierarchy, identify which valid subclasses depend on the API, which modules/packages they reside in, and what migration path exists. This is an inheritance contract change, not just a keyword tweak.

### 9.2. `sealed` clarifies the model but does not handle every case automatically

A `sealed` hierarchy helps control data shapes and audit branch-handling code. However:

- Business correctness still depends on validation and per-class logic.
- If a `non-sealed` branch exists, deeper subclasses can still be added.
- Java 17 **does not yet have standard pattern matching for `switch`** to exhaustively switch over all variants by pattern. Do not assume newer Java versions' exhaustiveness features apply by default to Java 17.
- `sealed` does not replace authentication, authorization, input validation, or deserialization security.

### 9.3. Module/package limits affect library packaging

A `sealed` API can be consumed across many projects, but **listed direct subtypes cannot arbitrarily reside in another module**. If you want plugins in external modules to create new types, design an appropriate public `non-sealed` branch or choose an open interface at the extension point.

### 9.4. Adding or removing permitted types is a design change

Whenever changing the `permits` list, evaluate dependent code, serialization systems, variant-handling logic, and compatibility. Adding a direct subtype may require updating code that previously relied on the old set of variants, even when Java 17 code does not yet use pattern `switch`.

## 10. Common mistakes when learning `sealed`

### Mistake 1: Thinking `sealed` is the same as `final`

`final` forbids subclassing the class. `sealed` permits **specified direct subtypes**. A `sealed class` can still have multiple subtypes, and a `non-sealed` branch can be extended further.

### Mistake 2: Forgetting to specify the subclass's continuation modifier

```java
sealed class Vehicle permits Car {}

// INVALID: Car must choose final, sealed, or non-sealed.
class Car extends Vehicle {}
```

Fix, for example:

```java
sealed class Vehicle permits Car {}

final class Car extends Vehicle {}
```

If `Car` also needs subclasses from a restricted list, use `sealed class Car ...`; if it needs to be open freely, consider `non-sealed class Car`.

### Mistake 3: Naming an indirect subtype in `permits`

```java
// INVALID: Sedan does not directly extend Vehicle.
sealed class Vehicle permits Car, Sedan {}

non-sealed class Car extends Vehicle {}

class Sedan extends Car {}
```

In this model, `Sedan` is an **indirect** subclass of `Vehicle`. `Vehicle`'s `permits` clause only needs to list `Car`; `Sedan` is allowed because `Car` is `non-sealed`.

### Mistake 4: Using `non-sealed` without a direct `sealed` parent

```java
class Base {}

// INVALID: Base is not a sealed type.
non-sealed class Child extends Base {}
```

`non-sealed` only makes sense when lifting an inheritance restriction placed on a direct `sealed` parent type.

### Mistake 5: Writing `final interface`

Java has no `final interface` syntax. To restrict valid implementing types, use `sealed interface`; to allow extension, use a regular interface.

### Mistake 6: Using `sealed` in Java 17 while compiling for Java 11

Even with JDK 17 installed, a build configured with `--release 11` does not allow `sealed` syntax. Ensure the release target matches the intended language/API level and that the deployment runtime can run Java 17 class files.

## 11. Design choice self-practice

**Exercise 1.** A logger library needs to let applications write `FileAppender`, `DatabaseAppender`, or `CloudAppender` in independent modules. Which hierarchy should be used for the extension point interface?

**Hint:** A regular interface works best when external implementations are a primary requirement. Putting `sealed` at the root would block implementations outside the module.

**Exercise 2.** A system returns `Approved`, `Rejected`, or `Pending`. Each variant has its own data fields, and a fourth variant is disallowed. What should be used?

**Hint:** Use `sealed interface Decision permits Approved, Rejected, Pending` and corresponding `record` types. Records are implicitly `final`.

**Exercise 3.** You need to lock an algorithm class so outsiders cannot override critical invariants, while still allowing different processing strategies to be passed in.

**Hint:** Use a `final class` combined with a strategy interface and composition. Locking the class does not prevent using different dependencies.

**Exercise 4.** A `sealed interface Notification` only permits `InternalNotification` and `ThirdPartyNotification`. The system wants full control over all internal notifications while letting plugins create notifications under the partner branch.

**Hint:** Make `InternalNotification` `final` or further `sealed` depending on internal variants; make `ThirdPartyNotification` `non-sealed`, with appropriate type/constructor accessibility for plugins to extend.

**Exercise 5.** Can we say that `sealed interface Event permits A, B` guarantees there are only two concrete classes implementing `Event` in the entire program?

**Answer:** Not necessarily. It only specifies two **direct subtypes**. If `A` or `B` is `non-sealed`, other classes can extend through that branch. If the entire tree must be finite, subsequent levels must be controlled too.

## 12. Takeaways to apply

- **Open hierarchy:** For types designed for others to extend; Java needs no `open` keyword.
- **`final class`:** Locks inheritance of that exact class. The class can still implement interfaces and hold mutable state.
- **`sealed class/interface`:** Controls the list of **direct subtypes**. Standardized as a language feature in Java 17.
- **`final` / `sealed` / `non-sealed` on subtypes:** Respectively closes the branch, restricts the next level, or reopens the branch.
- **Module/package rules:** Permitted direct subtypes must be in the same named module; in an unnamed module, they must be in the same package.
- **Java 17:** `sealed` can be used stably without preview flags. Pattern matching for `switch` remains preview in Java 17.

### Official references

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) — proposal finalized in Java 17, design motivation, and `permits` semantics.
- [Oracle Java 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html) — syntax and examples for `sealed`, `final`, and `non-sealed`.
- [Java Language Specification, Java SE 17 — Class Modifiers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1) — language rules for classes, `final`, and `sealed`.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html) — corresponding constraints for interfaces.

**Rule of thumb:** Start from the extensibility contract the system actually needs. **Leave open** when the system must accept new implementations; **use `final`** when a class needs no subclasses; **use `sealed`** when modeling a controlled set of subtype groups while preserving the ability to design multiple inheritance branches.
