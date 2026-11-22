# Controlled Extension of Type Hierarchies in Java Domain Model Design

## 1. The problem: adding domain types without losing consistency

A domain model often contains **multiple variants of the same concept**: an order can emit `Placed`, `Paid`, or `Cancelled` events; a payment result can be `Approved` or `Rejected`; an expression can be a constant or an addition.

If you only use a regular interface:

```java
interface OrderEvent {}
```

any class with access to that interface can `implements OrderEvent`. This is useful for plugin systems, but it raises a question for a finite domain: **which variants are valid, and does the handling code cover all of them?**

Since Java 17, **sealed classes/interfaces** (JEP 409) allow the owner to declare **the set of direct subtypes permitted to exist**. Since Java 21, **pattern matching for `switch`** (JEP 441) and **record patterns** (JEP 440) work together with sealed hierarchies so the compiler detects missing handling branches when extending the domain.

**Controlled extension** does not mean the hierarchy never changes. It means every new subtype must be considered at a clearly owned location; data consumers have the opportunity to be prompted by the compiler to update; and business constraints are preserved.

## 2. `sealed`, `permits`, `final`, and `non-sealed`

Example of a type hierarchy:

```java
sealed interface OrderEvent
        permits Placed, Paid, Cancelled {}

record Placed(String orderId) implements OrderEvent {}
record Paid(String orderId, long amountCents) implements OrderEvent {}
record Cancelled(String orderId, String reason) implements OrderEvent {}
```

- `sealed interface OrderEvent` states that **not just any arbitrary class/interface** is allowed to directly `implements`/`extends` it.
- `permits Placed, Paid, Cancelled` is **the list of direct subtypes** that are recognized.
- The three `record` types are direct subtypes; because records are implicitly **`final`**, they cannot be subclassed further.
- No fourth subtype may directly `implements OrderEvent` unless it is permitted in `permits`.

When a class **directly** extends a sealed class or implements a sealed interface, Java requires it to explicitly choose one of the modifiers: `final`, `sealed`, or `non-sealed` (records and enums have corresponding implicit rules). For a direct **subinterface**, the two appropriate choices are `sealed` or `non-sealed` because an interface cannot be `final`.

| Mechanism | Extension scope | When to use |
| --- | --- | --- |
| `final class` / `record` | Disallows further subclassing beneath it | The domain variant is complete |
| `sealed class/interface` | Only allows permitted direct subtypes; can further control deeper levels | Stable set of variants with a clear owner |
| `non-sealed class/interface` | Re-opens extension from that branch | An intentional extension branch is needed |
| Regular class/interface | Normal extension governed by Java access rules | Plugin design or open system with no fixed set of subtypes |

**`permits` applies to direct subtypes, not every descendant in the entire tree.** For example, a direct subtype that is `sealed` can have its own `permits` at the next level; a `non-sealed` subtype allows further extension beneath that branch.

## 3. Complete example: sealed hierarchy combined with pattern `switch`

Save the code in `SealedOrderDemo.java`:

```java
public class SealedOrderDemo {
    sealed interface OrderEvent
            permits Placed, Paid, Cancelled {}

    record Placed(String orderId) implements OrderEvent {}
    record Paid(String orderId, long amountCents) implements OrderEvent {}
    record Cancelled(String orderId, String reason)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var id) ->
                    "placed:" + id;

            case Paid(var id, var cents) ->
                    "paid:" + id + ":" + cents;

            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Placed("O-17")));
        System.out.println(describe(new Paid("O-17", 250)));
        System.out.println(describe(
                new Cancelled("O-17", "customer")));
    }
}
```

Run with **JDK 21 or later**:

```bash
javac --release 21 SealedOrderDemo.java
java SealedOrderDemo
```

Output:

```text
placed:O-17
paid:O-17:250
cancelled:O-17:customer
```

The key point in `describe` is that the `switch` **has no `default`**. The compiler can prove that the `switch` expression is *exhaustive*: every possible subtype of `OrderEvent` belongs to one of the three listed record types. `case Placed(var id)` and `case Paid(var id, var cents)` both select the event type and deconstruct its components via record patterns.

For an input with static type `OrderEvent`, this is a major design benefit: when the catalog of events changes, missing handling branches can be surfaced at **compile time**, instead of lying dormant until the system receives new data.

**Note on `null`:** exhaustiveness over the set of subtypes does not mean a `null` selector will automatically match. If `describe(null)` is called, the `switch` in the example will throw a `NullPointerException`. You can add `case null -> ...` if the business logic allows `null`, or perform non-null validation at the API boundary.

## 4. Extending the hierarchy: adding the `Refunded` variant

Suppose the domain adds a **refund** event. The change is not just creating a new file/class:

```java
// Conceptual change:
sealed interface OrderEvent
        permits Placed, Paid, Cancelled, Refunded {}

record Refunded(String orderId, long amountCents)
        implements OrderEvent {}
```

After adding `Refunded` to `permits`, the old `switch` with only three `case` branches **is no longer exhaustive** when recompiled against the updated hierarchy. For a `switch` expression without `default`, `javac` reports an error like:

```text
the switch expression does not cover all possible input values
```

This error is a **change-control guardrail**: the domain owner has expanded the set of subtypes, while the `switch` site is still assuming the old set. Adding a handling branch with meaningful business logic resolves the issue:

```java
case Refunded(var id, var cents) ->
        "refunded:" + id + ":" + cents;
```

This is a deliberate update to review, because a refund may require additional accounting, sending notifications, or recording state; Java only knows that the new subtype needs to be handled, and **cannot decide business logic on its own**.

### Runnable example after extension

Save to `EvolvedOrderDemo.java`:

```java
public class EvolvedOrderDemo {
    sealed interface OrderEvent
            permits Placed, Paid, Cancelled, Refunded {}

    record Placed(String orderId) implements OrderEvent {}
    record Paid(String orderId, long amountCents) implements OrderEvent {}
    record Cancelled(String orderId, String reason)
            implements OrderEvent {}
    record Refunded(String orderId, long amountCents)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var id) ->
                    "placed:" + id;
            case Paid(var id, var cents) ->
                    "paid:" + id + ":" + cents;
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
            case Refunded(var id, var cents) ->
                    "refunded:" + id + ":" + cents;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Refunded("O-17", 100)));
    }
}
```

```bash
javac --release 21 EvolvedOrderDemo.java
java EvolvedOrderDemo
```

Output:

```text
refunded:O-17:100
```

So the upgrade workflow is not just editing `permits`: **declare the new subtype → add business rules → find/update consumers → recompile → test each variant**.

## 5. Why shouldn't you rush to add `default`?

When a missing-branch error appears after adding a subtype, a quick fix is:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case Placed(var id) -> "placed:" + id;
        case Paid(var id, var cents) -> "paid:" + id;
        default -> "other";
    };
}
```

This is an **illustrative snippet in a context where `OrderEvent`, `Placed`, and `Paid` are already declared**.

`default` gives `switch` a fallback branch for unlisted cases, but **at the same time hides the warning about missing handling for new subtypes**. If the business logic truly needs dedicated logic for `Refunded`, `default -> "other"` will cause refund events to be treated as "other".

For a hierarchy where each subtype has distinct business meaning, it is usually better to **list each case explicitly and omit `default`** so that adding a subtype forces consumers to review it. For an API that needs to handle all variants under a single general rule, `default` may make sense, but that decision should be intentional.

A useful review rule: ask **"does this consumer need to distinguish the new variant?"** before using `default` just to silence compile errors.

## 6. `non-sealed`: opening only the branch that needs extension

Sometimes a domain needs to allow plugin extensions while still protecting its core parts. In that case, creating an **intentional `non-sealed` branch** is usually clearer than removing `sealed` from the root.

Save to `ControlledExtensionDemo.java`:

```java
public class ControlledExtensionDemo {
    sealed interface DomainAction
            permits Create, Remove, ExtensionAction {}

    record Create(String id) implements DomainAction {}
    record Remove(String id) implements DomainAction {}

    non-sealed interface ExtensionAction extends DomainAction {}

    record PluginAction(String key) implements ExtensionAction {}

    static String route(DomainAction action) {
        return switch (action) {
            case Create(var id) ->
                    "create:" + id;
            case Remove(var id) ->
                    "remove:" + id;
            case ExtensionAction other ->
                    "extension:" + other.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Create("a")));
        System.out.println(route(new Remove("b")));
        System.out.println(route(new PluginAction("x")));
    }
}
```

```bash
javac --release 21 ControlledExtensionDemo.java
java ControlledExtensionDemo
```

Output:

```text
create:a
remove:b
extension:PluginAction
```

Explanation:

- The root `DomainAction` only permits three direct subtypes: `Create`, `Remove`, and `ExtensionAction`.
- `Create` and `Remove` are records (`final`), so the core variants are closed.
- `ExtensionAction` is a `non-sealed` interface: other classes/records can `implements ExtensionAction` without changing `DomainAction`'s `permits` list.
- `case ExtensionAction other` covers **all subtypes** in the open branch, so the `switch` remains exhaustive at the `DomainAction` level.

Trade-off: the compiler **does not force writing a separate `case`** for each plugin under `ExtensionAction`. If a new plugin needs custom handling, routing, contract validation, and versioning become the responsibility of the extension architecture. A `non-sealed` branch should only appear when there is a genuine requirement for independent extension.

Do not use `non-sealed` as a default workaround to bypass the `permits` list, because doing so gives up control over the set of subtypes in that branch.

## 7. Controlling intermediate levels of the hierarchy

A multi-level model can be useful when domain variants have both broad groups and smaller subgroups:

```java
sealed interface PaymentEvent
        permits Settled, Adjustment {}

record Settled(String paymentId) implements PaymentEvent {}

sealed interface Adjustment extends PaymentEvent
        permits Refund, Chargeback {}

record Refund(String paymentId) implements Adjustment {}
record Chargeback(String paymentId) implements Adjustment {}
```

This is a **type-declaration example** that can be placed in a single compilation unit (a file without a public type). Every direct subtype of `PaymentEvent` must be `Settled` or `Adjustment`. The `Adjustment` branch in turn has a fixed list of children: `Refund` and `Chargeback`.

When the compiler analyzes an exhaustive `switch` on `PaymentEvent`, it can use the closedness information of the `sealed` branches. However, if `Adjustment` is changed to `non-sealed`, the set of descendants in that branch becomes open, so a `switch` that handles `Refund` and `Chargeback` individually **is no longer exhaustive** for `PaymentEvent`. When you need to cover an open branch, a `case Adjustment adjustment -> ...` may be the right choice.

Distinguish between **direct subtypes** (listed in `permits` at the parent level) and **indirect subtypes** (passing through an already-permitted branch). Do not put every subclass of `Adjustment` into `PaymentEvent`'s `permits` if they do not directly `implements PaymentEvent`.

## 8. Encapsulation rules: modules and packages

The `permits` list does not allow creating subtypes anywhere. Java imposes important restrictions:

- If the sealed type belongs to a **named module**, all permitted direct subtypes must belong to **the same module**. They can reside in different packages within that module as long as access rules are respected.
- If the sealed type belongs to the **unnamed module**, all permitted direct subtypes must be in **the same package** as the sealed type.
- Every subtype in `permits` must actually be a **direct subtype** of the sealed type.
- If `permits` is omitted, Java can infer the list when the direct subtypes have canonical names and are declared **in the same compilation unit**. For large systems, an explicit `permits` clause is often easier to review when the goal is controlled extension.

For example, adding `com.partner.ExternalEvent implements OrderEvent` from a completely different module to a `sealed` hierarchy defined in the current module **is not a valid way to create a plugin** simply by updating `permits`. If cross-module extension is needed, design the boundary using an open API, SPI, adapter, or an appropriate `non-sealed` branch.

Therefore, the `sealed` decision is directly tied to **domain model ownership**: who is allowed to modify the set of variants, which teams need to stay synchronized, and which module/package the subtypes live in.

## 9. Sealed hierarchies do not replace business invariants

`sealed` controls **which types of objects** are accepted at the type-hierarchy level. It **does not guarantee that the data inside a subtype is valid**. For example, `Paid` is a valid subtype, yet it could still carry an empty `orderId` or a negative amount if not checked.

Use validation at data construction time, such as a record's compact constructor:

```java
record Approved(String paymentId, long cents) {
    Approved {
        if (paymentId == null || paymentId.isBlank()
                || cents <= 0) {
            throw new IllegalArgumentException(
                    "invalid approved payment");
        }
    }
}
```

This is an **illustrative record declaration**. In a real domain, you can use `Objects.requireNonNull`, dedicated value objects (`PaymentId`, `Money`), and explicit rules.

Standalone example `CheckedResultDemo.java`:

```java
public class CheckedResultDemo {
    sealed interface PaymentResult
            permits Approved, Rejected {}

    record Approved(String paymentId, long cents)
            implements PaymentResult {
        Approved {
            if (paymentId == null || paymentId.isBlank()
                    || cents <= 0) {
                throw new IllegalArgumentException(
                        "invalid approved payment");
            }
        }
    }

    record Rejected(String paymentId, String reason)
            implements PaymentResult {}

    static String display(PaymentResult result) {
        return switch (result) {
            case Approved(var id, var cents) ->
                    "ok:" + id + ":" + cents;
            case Rejected(var id, var reason) ->
                    "rejected:" + id + ":" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Approved("P-1", 350)));

        try {
            new Approved("", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac --release 21 CheckedResultDemo.java
java CheckedResultDemo
```

Output:

```text
ok:P-1:350
invalid approved payment
```

Here:

- `sealed` protects the result set as `Approved`/`Rejected`.
- `record` provides a data carrier that is immutable at the component-reference and accessor level.
- The compact constructor ensures valid values for `Approved`.
- The exhaustive `switch` ensures the display branch distinguishes each result.

However, **lifecycle/process state** such as "refunded only after payment" still requires separate state-transition or business rules; `sealed` alone cannot verify event history.

## 10. When extending a public API: source compatibility and runtime

Adding a permitted subtype has two distinct effects that must be separated:

**When recompiling source consumers:** a previously exhaustive `switch` may report a **compile-time error** due to a missing `case` for the new subtype. This is helpful for forcing logic updates. Code with `default` may continue to compile, but it can also easily miss the new business behavior.

**For binary consumers compiled against an older version:** according to the JLS, **adding a permitted direct subtype** is generally **binary compatible**, meaning it does not necessarily cause linkage errors just because the subtype list expanded. However, if an old binary contains a `switch` that was previously exhaustive and, after an upgrade, receives an object of the new subtype it does not know about, execution can throw **`MatchException`**. That is a compatibility risk during deployment/migration, even though the old class files still link.

Operational scenario example:

1. Domain library **v1** declares `OrderEvent permits Placed, Paid, Cancelled`; a client service compiles a `switch` covering all three types.
2. Library **v2** adds `Refunded`.
3. If the client is **recompiled**, the compiler requires updating the exhaustive `switch`.
4. If only the library is updated at runtime while still running the **old client**, the client can handle the three old types normally, but upon receiving `Refunded`, the old `switch` may fail with `MatchException`.

Therefore, controlling a hierarchy also includes **versioning, updating consumers, integration testing, and deployment planning**. Do not equate "binary compatible" with "all runtime behavior remains compatible".

## 11. Distinguishing internal domain extension from external system data

A domain hierarchy may be closed, but input data from JSON/APIs/message queues is usually not closed: there may be an unknown `eventType`, a malformed payload, or a newer unsupported version. `sealed` does not automatically map or validate JSON.

Separate layers of responsibility:

1. **Adapter/decoder** reads external data, validates schema, version, and access permissions.
2. **Validation/domain factory** creates a valid subtype or returns a clear input error.
3. **Sealed domain model** holds the set of variants accepted by the system.
4. **Pattern `switch` in application logic** handles all permitted domain subtypes.

If a system must retain future events it does not yet understand, you can consider a dedicated model such as `UnknownEvent(type, rawPayload)`, but that is a **business decision and data-compatibility policy**, not a default fix for every missing `case`. Set limits on size, format, and usage of unknown data if the model carries external payloads.

A `default` in `switch` or an `UnknownEvent` subtype does not automatically make the system understand future transactions; they only provide an explicit place to handle or reject them.

## 12. Choosing `enum`, `sealed interface`, or open interface?

| Characteristic | `enum` | `sealed interface` + records | Open interface |
| --- | --- | --- | --- |
| Variant set | Finite by constants | Controlled direct subtypes | Can be extended externally |
| Different data per variant | Possible, but becomes unwieldy when payloads have different structures | Each record carries its own meaningful components | Depends on implementation |
| Exhaustive `switch` | Compiler can rely on enum constants | Compiler can rely on the sealed hierarchy | Usually needs a catch-all branch |
| Extension point | Add an enum constant | Add a `permits` subtype or `non-sealed` branch | Implement another type |
| Best suited for | Simple states/values with little payload | Algebraic data types, events/results with different payloads | SPI, plugins, open polymorphism |

For example, if an order only has `NEW`, `PAID`, and `CANCELLED` and carries no differing data, `enum` may be enough. When each variant carries its own payload (`Paid.amountCents`, `Cancelled.reason`), a `sealed interface` combined with `record`s usually lets the model express what is valid much more clearly.

Do not choose a sealed hierarchy just because pattern matching syntax looks nice. Choose it when **the set of variants has an owner and needs control**, especially when multiple consumers must be updated whenever a new subtype is added.

## 13. Workflow for adding a subtype in a real project

A controlled change typically follows this order:

1. **Determine whether the new variant truly belongs as a subtype of the current domain.** For example, is `Refunded` an `OrderEvent`, or is it a result in the `Payment` bounded context?
2. **Identify who owns the sealed root and the package/module.** The new type must satisfy `permits` rules and module boundaries.
3. **Define the subtype and its invariants.** If using a record, consider components, nullability, value objects, and validation.
4. **Update `permits` on the sealed root** or extend the branch designed for that purpose; avoid opening the entire hierarchy with `non-sealed` if only one specific variant is needed.
5. **Recompile consumers.** Fix exhaustive `switch` errors; also review consumers using `default`, because they may still compile while violating business expectations.
6. **Verify integration and serialization.** APIs, JSON mapping, persistence, message schemas, telemetry, and old/new data must adhere to the contract.
7. **Plan synchronized deployment when needed.** Especially when multiple services share a domain JAR or event schema.
8. **Update domain documentation and examples.** Describe the purpose, data, processing flow, and how to extend further.

These steps do not replace code review; they help focus the review on places where the compiler or domain model cannot decide automatically.

## 14. Negative test example: unpermitted subtype

Given:

```java
sealed interface Action permits Start, Stop {}

record Start() implements Action {}
record Stop() implements Action {}
```

If you add:

```java
// Invalid without updating permits:
record Pause() implements Action {}
```

`Pause` attempts to directly implement `Action` without being listed. The compiler will reject it. Only when the owner of `Action` adds `Pause` to `permits` and the related rules are satisfied does it become a valid direct subtype.

Similarly, if `permits` is updated to add `Pause` while an existing `switch` only checks `Start` and `Stop`, the exhaustive `switch` expression is no longer complete and will be caught by the compiler on recompilation.

These are **two separate layers of control**: (1) who is allowed to become a variant of the root; (2) which consumers need to be updated when the variant catalog changes.

## 15. Common misconceptions

1. **"`sealed` forbids any future changes."** False. The owner can modify the `permits` list, but that change carries the obligation to upgrade consumers.
2. **"Any class can implement a sealed interface from any module as long as it is listed in `permits`."** False. Types must obey the same-named-module or same-package-in-unnamed-module restriction.
3. **"`permits` includes all subtypes at every level."** False. It only governs **direct** subtypes; each `sealed` branch governs its own children.
4. **"A `record` needs `final` explicitly to be valid with a sealed interface."** Unnecessary. Records are implicitly `final`.
5. **"`non-sealed` still keeps a fixed list of child subtypes."** False. It re-opens extension beneath that branch.
6. **"Having `default` is always a safe design."** Not necessarily. `default` can hide missing logic for new domain variants.
7. **"Once exhaustive, `switch` automatically handles `null`."** False. Define an explicit `null` policy.
8. **"Adding a subtype is binary incompatible in all cases."** False under Java's binary compatibility rules; the risk lies in **un-upgraded consumer code** and `MatchException` when encountering the new subtype.
9. **"Sealed guarantees every record instance is valid."** False. Nullability, positive amounts, string lengths, and business state require separate validation.
10. **"Every hierarchy should be `sealed`."** False. Truly open extension points can use regular interfaces or an intentionally designed `non-sealed` branch.

## 16. Design checklist

When creating or changing a domain type hierarchy, ask yourself:

- Is the set of variants **closed** or **open** according to product needs?
- Who owns the root type and who has authority to add subtypes?
- Which branches should be `final`/record, further `sealed`, or `non-sealed`?
- Does `permits` list the exact **direct subtypes** and respect module/package boundaries?
- Do `switch` statements/expressions relying on exhaustiveness need new `case`s? Is any `default` hiding missing handling?
- Are **data invariants** protected via constructors/factories/validation?
- Where are `null`, unknown data, and new schema versions handled?
- When upgrading the library/domain JAR, are consumers recompiled and deployed in sync?

**Remember:** use `sealed` to control **which kinds of domain values can exist**; use pattern matching with `switch` to control **which handling branches must exist**; use constructors, validation, and deployment processes to keep **values and business behavior** correct as the type hierarchy evolves.

## Official references

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java SE 21 JLS §8.1.1.2 — sealed and final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [Java SE 21 JLS §9.1.1.4 — sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4)
- [Java SE 21 JLS §14.11 — switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §13.4 and §13.5 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html)