# When to Use `enum`, `sealed`, or Composition in Java 17

In Java 17 design, both `enum` and `sealed` help model **a constrained set of possibilities**, yet the two tools constrain **two different things**:

- **`enum`** describes a set of **named constant values**, where each constant is a pre-declared instance.
- **`sealed class` / `sealed interface`** restricts **which direct subtypes** may extend or implement a parent type. Each subtype can have its own data and behavior; a program can instantiate many objects of the same subtype.
- **Composition** means assigning enums, sealed types, records, and regular objects to distinct roles rather than forcing all information in a business domain into a single inheritance hierarchy.

Neither tool is universally superior to the other. The key design question is: **"Are these fixed values, distinct data shapes, or multiple independent dimensions of information?"**

This lesson uses syntax available and stable in **Java 17**. `sealed` was standardized in Java 17; `record`, `switch` expressions, and pattern matching for `instanceof` are also official in Java 17. **Pattern matching in `switch` is still a preview feature in Java 17**, so the examples use `switch` with enums or `instanceof` without `--enable-preview`.

## 1. Comparison Table for Choosing a Design Direction

| Criterion | `enum` | `sealed interface/class` | Composition |
| --- | --- | --- | --- |
| Represents | A set of **constant values** such as `NEW`, `PAID`, `CANCELLED`. | A set of **type families** such as `Success`, `Failure` with different structures. | Multiple data dimensions or multiple responsibilities within one model. |
| Number of objects | Each enum constant is a pre-defined object; no new constants can be created at runtime. | As many instances of permitted subclasses as needed can be created. | Depends on components: finite enums alongside records/objects with many instances. |
| Per-case data | Can hold fields and methods per constant, yet constants carry fixed data and cannot take new data per event. | Each subtype has its own fields, constructors, invariants, and behavior; records often fit data well. | Put independent attributes in fields; use `sealed` only where structural variants truly exist. |
| Extension policy | Enum constants cannot be added outside the enum declaration. | Only permitted direct subclasses; a `non-sealed` branch can be extended further. | Restrictions or openness can be chosen independently per component. |
| Branching in Java 17 | `switch` on enum works stably, including `switch` expressions. | `instanceof` with pattern variables, polymorphic methods, or Visitor; type-pattern `switch` is still preview in Java 17. | Often uses `switch` for enums and polymorphism/`instanceof` for sealed variants. |
| Typical cases | Permissions, statuses, priority levels, fixed notification kinds. | Success/failure results, commands with distinct payloads, AST nodes, message variants. | Payment method + order status; sealed result group + enum error code; event with type and metadata. |

Prefer the model with **the fewest types and constraints that accurately expresses the domain**. Do not use `sealed` merely because a project is on Java 17.

## 2. When `enum` Is the Right Choice

Choose `enum` when you have **a finite, clearly named group of values** that does not need new per-instance values created at runtime:

- Workflow states: `CREATED`, `PROCESSING`, `DONE`, `FAILED`.
- Priority levels: `LOW`, `NORMAL`, `HIGH`.
- Channel types: `EMAIL`, `SMS`, `PUSH`.
- A fixed taxonomy or reason codes defined by the system.

### 2.1. Example: Enum with Fields and `switch` Expression

Create the file **`PriorityDemo.java`**:

```java
enum Priority {
    LOW(1),
    NORMAL(5),
    URGENT(10);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }
}

public class PriorityDemo {
    static String label(Priority priority) {
        return switch (priority) {
            case LOW -> "Low";
            case NORMAL -> "Normal";
            case URGENT -> "Urgent";
        };
    }

    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(
                    label(priority) + " (weight=" + priority.weight() + ")"
            );
        }
    }
}
```

```bash
javac --release 17 PriorityDemo.java
java PriorityDemo
```

This example shows that an enum can contain **fields, constructors, and methods**, not just constant names. Still, there are only three values—`Priority.LOW`, `Priority.NORMAL`, and `Priority.URGENT`: the program cannot call `new Priority(...)`.

A `switch` expression in Java 17 must cover all appropriate cases. With enums, listing every constant enables the compiler to detect changes to the value set upon recompilation. A pre-written `default` can hide an important design warning when the enum grows; use `default` only when a catch-all fallback is genuinely intended.

### 2.2. Enum with Per-Constant Behavior

If each value has a small, stable behavioral rule, behavior can live right inside the enum:

```java
enum PricePolicy {
    STANDARD {
        @Override
        int apply(int basePrice) {
            return basePrice;
        }
    },
    PROMOTION {
        @Override
        int apply(int basePrice) {
            return basePrice * 90 / 100;
        }
    };

    abstract int apply(int basePrice);
}
```

This is a **constant-specific class body**, a longstanding capability still valid in Java 17. There is no need to create a sealed hierarchy just to express two simple constant strategies. If rules grow lengthy or depend on databases or dynamic configuration, move processing to a service/strategy instead of crowding logic into the enum.

### 2.3. When Not to Force Data into an Enum

Suppose every support ticket has an `id`, creator, open timestamp, message, and priority. The `Priority` enum expresses only the **priority level**; it cannot safely store per-ticket data by mutating a field on `URGENT`, because `URGENT` is **a single shared object**.

A suitable model is:

```java
import java.time.Instant;

record SupportTicket(
        long id,
        String requester,
        Priority priority,
        Instant createdAt
) {}
```

`Priority` here is **an attribute of `SupportTicket`**, not the ticket itself. Avoid mutable fields on enums to store per-user, per-request, or per-transaction state; mutating them affects every site using that enum constant.

## 3. When `sealed` Fits Better Than `enum`

Choose `sealed interface` or `sealed class` when the managed set of variants has **different data structures**, each variant can have **multiple instances**, or each needs its own behavior and invariants.

Examples:

- `Success<T>` holds a value `T`; `Failure<T>` holds an error code and message.
- `EmailNotification` holds a recipient address and subject; `SmsNotification` holds a phone number and body.
- `TransferCommand` holds source/destination accounts; `RefundCommand` holds the transaction ID to refund.

### 3.1. Example: `sealed` + `record` for Variants with Different Payloads

Create the file **`LookupDemo.java`**:

```java
import java.util.Objects;

sealed interface LookupResult
        permits Found, NotFound, LookupFailed {}

record Found(String value) implements LookupResult {
    Found {
        Objects.requireNonNull(value, "value");
    }
}

record NotFound(long requestedId) implements LookupResult {}

record LookupFailed(String reason) implements LookupResult {
    LookupFailed {
        Objects.requireNonNull(reason, "reason");
    }
}

public class LookupDemo {
    static String describe(LookupResult result) {
        if (result instanceof Found found) {
            return "Found: " + found.value();
        }
        if (result instanceof NotFound notFound) {
            return "Missing id=" + notFound.requestedId();
        }
        if (result instanceof LookupFailed failed) {
            return "Lookup error: " + failed.reason();
        }
        throw new IllegalStateException("Unhandled result: " + result);
    }

    public static void main(String[] args) {
        LookupResult a = new Found("Alice");
        LookupResult b = new NotFound(404);
        LookupResult c = new LookupFailed("Service unavailable");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println(describe(c));
    }
}
```

```bash
javac --release 17 LookupDemo.java
java LookupDemo
```

Key design points:

1. `LookupResult` permits only three **direct subtypes**. You cannot arbitrarily create `class UnexpectedResult implements LookupResult` elsewhere outside the permitted set.
2. `Found`, `NotFound`, and `LookupFailed` are `record` types; records are implicitly `final`, so they can directly implement a sealed interface. Each record holds **per-instance data**, unlike enum singletons.
3. A `LookupResult` variable can point to any instance of those three variants. There is no limit to a single `Found` or `LookupFailed` object.
4. `instanceof` with a pattern variable is a standard feature in Java 17. This example avoids `switch (result) { case Found f -> ... }` because type-pattern `switch` was still preview then.

**Note on exhaustiveness:** the `if/instanceof` code above is not verified for exhaustiveness against the sealed hierarchy by Java 17. If a new type is added to `permits`, the Java 17 compiler does not force you to add a matching `if`; the trailing throw catches unsupported cases at runtime. When you want per-variant behavior without scattering branching everywhere, consider polymorphic methods or Visitor.

### 3.2. `sealed` Does Not Mean the Entire Tree Is Always Closed

A direct subtype of a sealed interface must declare how inheritance continues:

```java
sealed interface Command permits BuiltInCommand, ExtensionCommand {}

sealed interface BuiltInCommand extends Command
        permits StartCommand, StopCommand {}

non-sealed interface ExtensionCommand extends Command {}

record StartCommand() implements BuiltInCommand {}
record StopCommand() implements BuiltInCommand {}

record CustomCommand(String pluginName) implements ExtensionCommand {}
```

`BuiltInCommand` keeps a restricted variant list. `ExtensionCommand` opens a branch for new types. This helps when only **part** of a hierarchy needs extensibility. Still, in plugin architectures where third parties must directly implement the root interface, a **regular interface** may be simpler and more appropriate than a sealed interface.

In Java 17, direct permitted subtypes of a sealed type must reside in the **same named module** as the parent; when using an **unnamed module**, they must reside in the **same package**. Designing sealed hierarchies across independent modules therefore requires careful consideration.

## 4. When to Combine `enum` and `sealed`

Combining them makes sense when a type models **message shapes**, while an enum models a **shared classification repeated across messages**.

For instance, a system returns payment outcomes consisting of:

- `Approved`: has an approved transaction ID and amount.
- `Rejected`: has a reason code and detailed message.
- `Pending`: has an expected confirmation timestamp.

These results have different payloads, so **sealed interface + record** fits well. Meanwhile, the list of rejection reasons—`INSUFFICIENT_FUNDS`, `INVALID_DETAILS`, `RISK_REVIEW`—are **classification values**, making **enum** a great fit.

### 4.1. Complete Example: `sealed` for Outcomes, `enum` for Reason Codes

Create the file **`PaymentResultDemo.java`**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

enum RejectReason {
    INSUFFICIENT_FUNDS,
    INVALID_DETAILS,
    RISK_REVIEW
}

sealed interface PaymentResult
        permits Approved, Rejected, Pending {}

record Approved(String transactionId, BigDecimal amount)
        implements PaymentResult {
    Approved {
        Objects.requireNonNull(transactionId, "transactionId");
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}

record Rejected(RejectReason reason, String message)
        implements PaymentResult {
    Rejected {
        Objects.requireNonNull(reason, "reason");
        Objects.requireNonNull(message, "message");
    }
}

record Pending(Instant nextCheckAt) implements PaymentResult {
    Pending {
        Objects.requireNonNull(nextCheckAt, "nextCheckAt");
    }
}

public class PaymentResultDemo {
    static String render(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "Approved #" + approved.transactionId()
                    + ": " + approved.amount();
        }
        if (result instanceof Rejected rejected) {
            return "Rejected [" + rejected.reason() + "]: "
                    + rejected.message();
        }
        if (result instanceof Pending pending) {
            return "Pending until " + pending.nextCheckAt();
        }
        throw new IllegalStateException("Unexpected result: " + result);
    }

    public static void main(String[] args) {
        PaymentResult a = new Approved(
                "TX-101", new BigDecimal("125.00")
        );
        PaymentResult b = new Rejected(
                RejectReason.INSUFFICIENT_FUNDS,
                "Account balance is too low"
        );
        PaymentResult c = new Pending(
                Instant.parse("2026-12-01T09:00:00Z")
        );

        System.out.println(render(a));
        System.out.println(render(b));
        System.out.println(render(c));
    }
}
```

```bash
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

Diagram:

```text
PaymentResult                (sealed interface)
├── Approved                 (record: transactionId, amount)
├── Rejected                 (record: reason, message)
│   └── reason               (enum RejectReason)
└── Pending                  (record: nextCheckAt)
```

`RejectReason` **is not a subtype** of `PaymentResult`; it is a **data component inside** `Rejected`. Adding a new reason code does not require creating a new payment-result class at the type level. Adding a new outcome kind with a different structure requires updating `PaymentResult`'s permitted subtypes.

This avoids bloated designs like `RejectedInsufficientFunds`, `RejectedInvalidDetails`, and `RejectedRiskReview` when rejection cases all share the `reason + message` structure. Only promote individual reasons to standalone sealed variants if they require completely different payloads or separate invariants.

### 4.2. An `enum` Can Also Directly Implement a `sealed interface`

There is no rule forcing subtypes of a sealed interface to be `record`s. If one branch genuinely consists of **constant values with no dynamic payload**, an enum can serve as a permitted subtype:

```java
sealed interface UserAction permits NavigationAction, SendMessage {}

enum NavigationAction implements UserAction {
    BACK,
    HOME,
    REFRESH
}

record SendMessage(String text) implements UserAction {}
```

`UserAction` has one branch of fixed navigation actions and one branch carrying a new payload per sent message. `NavigationAction` is **one direct subtype** of `UserAction`, not three subtypes `BACK`, `HOME`, `REFRESH`. Under Java 17 rules, enums are special types with closed-hierarchy semantics; you do not add `final` or `sealed` modifiers manually to an enum declaration.

Still, use this combination only when treating both groups as `UserAction` is genuinely meaningful in the domain. You do not need to create a sealed root for every enum in your project.

## 5. When Composition Is Simpler Than a Hierarchy

A model with multiple **independent axes of variation** should not spawn subclasses for every combination. For example, an order has two axes:

- **Status:** `CREATED`, `PAID`, `CANCELLED`.
- **Payment channel:** `CARD`, `BANK_TRANSFER`, `WALLET`.

Creating a separate class per combination produces `3 × 3 = 9` types, and multiplies further when adding a status or channel. Meanwhile, these two axes can be represented as two enum fields on a record:

```java
import java.util.Objects;

enum OrderStatus {
    CREATED, PAID, CANCELLED
}

enum PaymentChannel {
    CARD, BANK_TRANSFER, WALLET
}

record Order(
        long id,
        OrderStatus status,
        PaymentChannel channel
) {
    Order {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(channel, "channel");
    }
}
```

Example object: `new Order(42, OrderStatus.PAID, PaymentChannel.CARD)`. When adding a payment channel, you do not have to add a subtype for every status. **Composition expresses what an object has** (`status`, `channel`) instead of turning every combination into an **is-a** relationship.

Not every combination is valid in business terms. If certain statuses are allowed only with specific channels, place **validation rules** at creation or state-transition points rather than assuming a transaction is valid simply because Java lets two enum values coexist.

### 5.1. Combining Data and Behavior at the Right Level

For larger business domains, responsibilities can be split cleanly:

| Component | Purpose |
| --- | --- |
| `enum OrderStatus` | Names of finite business states. |
| `enum PaymentChannel` | Payment channel classification. |
| `record Order` | Per-order data and local invariants. |
| `sealed interface PaymentResult` | Processing outcome shapes with distinct payloads. |
| `PaymentService` | Business orchestration, external integrations, state-transition rules. |

Avoid stuffing all business logic into enums or building a massive sealed tree just to group unrelated functions under one type hierarchy. `sealed` excels when variants truly have **different shapes/meanings**; `enum` excels when options share the same shape; composition excels when there are **multiple distinct attributes**.

## 6. Decision-Making Flow

You can follow this decision sequence when designing:

```text
What is the problem modeling?
│
├─ A fixed list of named values?
│  └─ enum
│
├─ Kinds of objects with different payloads/invariants?
│  ├─ Direct subtype set clearly managed by you?
│  │  └─ sealed interface/class + appropriate records/classes/enums
│  └─ Must third parties implement directly?
│     └─ regular interface (or an explicit non-sealed branch)
│
└─ Multiple independent classification axes/attributes?
   └─ composition: record/class holding enums, sealed types, or other objects
```

After choosing a primary direction, ask further:

1. **Does each case carry new per-instance data?** If each call needs a distinct `transactionId`, do not try to store it on an enum constant.
2. **How many variant kinds exist, and who may add them?** `sealed` fits when someone controls the direct subtype set; open interfaces fit public extension points.
3. **Do all cases share the same shape?** If every case simply has `code + description`, one record with an enum field may be enough.
4. **Are two dimensions independent?** If adding a value in dimension A should not force adding multiple types in dimension B, composition is usually much more natural.
5. **How will API callers handle the cases?** Enums work well with Java 17 `switch`; `sealed` can use polymorphic methods or `instanceof`, remembering that type-pattern `switch` in Java 17 is preview.

## 7. Common Modeling Mistakes

### 7.1. Using an Enum to Hold Per-Request State

```java
enum ConnectionState {
    CONNECTED, DISCONNECTED;

    // Avoid adding mutable fields like:
    // String currentUserId;
}
```

Every constant is shared. `ConnectionState.CONNECTED` does not represent **a specific connection session**; use `record Session(String userId, ConnectionState state)` or an appropriate session class instead.

### 7.2. Creating Dozens of Subclasses for Simple Classifications

If the only difference between cases is `severity` (`INFO`, `WARN`, `ERROR`), an `enum Severity` and `record LogEntry(Severity severity, String message)` can be far easier to understand than `InfoLog`, `WarnLog`, `ErrorLog`.

Only promote a model to a sealed hierarchy when individual cases have **meaningful distinct payloads or invariants**, or when that distinction genuinely needs to be represented in static types.

### 7.3. Using `sealed` for a Public Extension Point

A library shipping `sealed interface Plugin` blocks user modules from directly creating classes implementing `Plugin` unless they are in the valid `permits` set. If the goal is letting any user write plugins, a regular interface is usually the natural choice.

You can use a **sealed root + `non-sealed` branch** when wanting to designate a specific extension point, yet carefully evaluate module/package requirements and library-user ergonomics.

### 7.4. Assuming `sealed` Enables Type-Pattern `switch` by Default in Java 17

```java
// This is pattern-matching switch syntax that was in preview in Java 17:
// return switch (result) {
//     case Found f -> f.value();
//     case NotFound n -> "...";
//     case LookupFailed e -> "...";
// };
```

Without preview enabled on Java 17, use `instanceof` patterns or polymorphism. Do not take Java 21+ examples and treat them as stable Java 17 syntax.

### 7.5. Treating `permits` as a List of Every Instance

`sealed interface Result permits Success, Failure` restricts only **two direct subtypes**. A program can still create a million `Success` objects with a million different payloads. That is the fundamental difference from an enum's fixed set of constants.

### 7.6. Persisting Enums by `ordinal()` or Assuming Enum Names Never Change

Do not persist `ordinal()` as a durable business code, because merely inserting or reordering constants shifts ordinal numbers. When communicating over APIs or storing in databases, use explicit codes:

```java
enum DeliveryStatus {
    CREATED("created"),
    IN_TRANSIT("in_transit"),
    DELIVERED("delivered");

    private final String code;

    DeliveryStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

Establish compatibility policies when adding, renaming, or removing enum constants. Adding a constant or a sealed subtype may require consumer code to update handling branches; in Java 17, pay special attention to `switch` branches on enums and `instanceof` logic on sealed types.

## 8. Design Differences Between `sealed class` and `sealed interface`

Even after choosing `sealed`, you still decide between a class and an interface:

| `sealed interface` | `sealed class` |
| --- | --- |
| Fits when variants only need to share a **type contract**, without shared base state. | Fits when subclasses share significant **state/constructors/implementation**. |
| A class can implement multiple interfaces, provided `permits` rules are satisfied. | Java allows a class to directly extend only one superclass. |
| Records and enums can directly implement an interface (when listed as permitted). | Records and enums cannot `extends` a regular sealed class because they already have special superclasses. |
| Usually natural for `sealed interface Result permits Success, Failure`. | Useful for a class family with shared constructors or protected members. |

Simple example with a sealed class:

```java
sealed abstract class ReportItem permits TextItem, ImageItem {
    private final String id;

    protected ReportItem(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public String id() {
        return id;
    }
}

final class TextItem extends ReportItem {
    private final String text;

    TextItem(String id, String text) {
        super(id);
        this.text = text;
    }

    String text() {
        return text;
    }
}

final class ImageItem extends ReportItem {
    ImageItem(String id) {
        super(id);
    }
}
```

In this example, the sealed class holds the shared `id` and constructor to guarantee every element has an identifier. When variants do not need shared base state, `sealed interface` + `record` is usually more concise.

## 9. Design Exercises

**Exercise 1 — Design Classification.** For each model below, choose `enum`, `sealed`, or composition, and explain why:

1. Priority levels `LOW/MEDIUM/HIGH`.
2. File loading outcome: `Success(bytes)`, `NotFound(path)`, `Failure(cause)`.
3. An order record holding status, order channel, order ID, and creation timestamp.
4. Notification kinds `Email(to, subject)` and `Sms(phoneNumber)`.

**Exercise 2 — Refactoring a Model.** A system has nine classes: `CardPending`, `CardApproved`, `CardRejected`, `WalletPending`, `WalletApproved`, etc. If status and payment channel are independent, redesign them into a single record containing two enums. If `Rejected` must carry a specific reason, consider separating the **processing outcome** into a sealed type with payloads rather than creating the original nine classes.

**Exercise 3 — Combining Enum and Sealed.** Design `sealed interface Notification` containing `EmailNotification` and `SmsNotification`. Include `enum Urgency { NORMAL, HIGH }` in the shared data required by each notification. Identify which type defines payload shape and which classifies urgency.

**Exercise 4 — Choosing Sealed vs. Regular Interface.** You are building an SDK allowing customers to implement custom `StorageProvider`s across different modules. Analyze why `sealed interface StorageProvider` would impede extensibility needs and when a `non-sealed` branch might help.

## 10. Official Java 17 Reference Documentation

- [JLS Java SE 17, §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): enum constants, constructors, members, and enum semantics.
- [JLS Java SE 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, constructors, and record `final` behavior.
- [JLS Java SE 17, §9.1.1.4 — Sealed and Non-Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): extension rules for sealed interfaces.
- [JLS Java SE 17, §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): `permits`, module, and package rules.
- [JLS Java SE 17, §8.1.1.2 — Sealed, Non-Sealed, and Final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): subclass restrictions.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design context and standard status in JDK 17.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `switch` expressions standard since Java 14 and stable in Java 17.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern matching for `instanceof`, standardized prior to Java 17.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): preview status of type-pattern `switch` in Java 17.

**Rule of thumb for design:** use **enums** for *fixed values*, use **sealed** for *distinct object kinds with their own structures and rules*, and use **composition** when data varies along *independent dimensions*. You can combine all three in the same model as long as each tool is responsible for what it expresses best.
