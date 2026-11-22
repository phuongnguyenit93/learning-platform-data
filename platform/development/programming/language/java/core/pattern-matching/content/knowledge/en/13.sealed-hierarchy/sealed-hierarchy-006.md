# Pattern switch on a sealed interface in Java 21

## 1. Why combine a `sealed interface` with pattern `switch`?

When a system has a predefined set of business variants, a `sealed interface` lets you describe **which types are permitted to implement the interface**. Pattern matching for `switch` in Java 21 lets you branch directly on those types, bind a variable in each branch, and — when all cases are covered — rely on the compiler to check **exhaustiveness**.

For example, a payment flow with three outcomes:

```java
sealed interface PaymentState permits Pending, Captured, Rejected {}

record Pending(String paymentId) implements PaymentState {}
record Captured(String paymentId, long amountVnd) implements PaymentState {}
record Rejected(String paymentId, String reason) implements PaymentState {}
```

`PaymentState` is the parent type. `Pending`, `Captured`, and `Rejected` are the three permitted direct subtypes. Using `switch`:

```java
static String status(PaymentState state) {
    return switch (state) {
        case Pending pending -> "PENDING";
        case Captured captured -> "CAPTURED";
        case Rejected rejected -> "REJECTED";
    };
}
```

These are **shared code snippets** that can be placed into a valid Java class or file. The complete program in Section 13 provides full definitions and instructions for running it.

The main benefits go beyond having fewer `if/else` statements:

- **The domain type explicitly states the set of variants**: which subtypes are valid payment outcomes.
- **Switch branches align with business terminology**: each `case` represents a state.
- **The compiler helps detect missing branches** when a new subtype is added to the closed hierarchy and dependent code is recompiled.
- **No manual casting required**: type/record patterns bind properly typed variables inside the branch body.
- **Easy to add per-subtype policies** using guards, base branches, and dedicated handler methods.

**Important boundary:** `sealed` controls direct inheritance relationships; it does not automatically validate component data or all business invariants. A `Captured` instance can still have a negative amount or a `null` component if the constructor does not validate it.

## 2. Syntax and requirements for creating a sealed hierarchy

A `sealed interface` declares its set of direct subtypes using `permits`:

```java
sealed interface Message permits TextMessage, ImageMessage {}

record TextMessage(String text) implements Message {}
record ImageMessage(String imageUrl) implements Message {}
```

Distinctions:

| Element | Purpose |
| --- | --- |
| `sealed interface Message` | Interface restricting which classes/interfaces may directly extend/implement it |
| `permits TextMessage, ImageMessage` | List of direct permitted subtypes |
| `implements Message` | The subtype itself participates in the hierarchy |
| `record TextMessage(...)` | An implementation that is a record; records are implicitly `final` |
| `case TextMessage text ->` | Type pattern matching a variant |
| `case TextMessage(var content) ->` | Record pattern, both matching the type and extracting components |

A direct subtype of a sealed class/interface must explicitly declare one of the appropriate modifiers: **`final`, `sealed`, or `non-sealed`**, except for types that inherently satisfy the corresponding language requirement, such as `record` (which is implicitly `final`).

Example using regular classes:

```java
sealed interface Command permits CreateCommand, PluginCommand {}

final class CreateCommand implements Command {}

non-sealed class PluginCommand implements Command {}
```

`CreateCommand` is closed and disallows subclasses. `PluginCommand` is open again so it can have further subclasses. This affects how you reason about the number of runtime variants, but a `case PluginCommand plugin ->` still covers **every object** of type `PluginCommand` or any of its subtypes.

### 2.1. Module/package rules to remember

Permitted subtypes of a sealed type must reside in the **same module** if the hierarchy belongs to a named module; when the code is in the unnamed module, they must be in the **same package**. `permits` is not a mechanism for granting permission to an arbitrary subtype in any other module.

In small exercises, placing the interface and records as nested types inside the same `public class` is a simple way to create a self-contained program that compiles directly with `javac`.

### 2.2. `permits` only lists direct subtypes

Suppose:

```java
sealed interface Event permits OrderEvent, AuditEvent {}
sealed interface OrderEvent extends Event permits OrderPlaced {}
record OrderPlaced(String id) implements OrderEvent {}
final class AuditEvent implements Event {}
```

`OrderPlaced` is a direct permitted subtype of **`OrderEvent`**, not necessarily a direct element in the `permits` list of **`Event`**. When reading a switch on `Event`, you must look at the entire type tree, not just a single list of names.

## 3. Type pattern: branching by interface subtype

When the selector has a static type of a sealed interface, Java 21 supports **type patterns** directly in cases:

```java
static String shortLabel(PaymentState state) {
    return switch (state) {
        case Pending pending -> "waiting";
        case Captured captured -> "paid";
        case Rejected rejected -> "failed";
    };
}
```

Read `case Captured captured` as follows:

1. Check whether the runtime value belongs to type `Captured`.
2. If true, bind the pattern variable `captured` of type `Captured`.
3. Only within the matching branch can you use `captured.paymentId()`, `captured.amountVnd()`, etc.

The code does not need:

```java
if (state instanceof Captured) {
    Captured captured = (Captured) state;
}
```

because the pattern combines the type check and the typed variable binding.

**Name pattern variables clearly:** `captured`, `pending`, and `rejected` are more helpful than `x` or `obj` when a branch body is long. The name `captured` is just a variable, not a different pattern or a way to alter coverage rules.

## 4. Exhaustiveness: when does the compiler know all variants are covered?

A **switch expression** must exhaustively cover all applicable values. With the sealed `PaymentState` selector above, the three record subtypes `Pending`, `Captured`, and `Rejected` form a closed set; one unguarded case for **each** subtype is enough for the switch to be considered exhaustive:

```java
static int categoryCode(PaymentState state) {
    return switch (state) {
        case Pending pending -> 1;
        case Captured captured -> 2;
        case Rejected rejected -> 3;
    };
}
```

No `default` is needed. This is the strength of the sealed + switch design: if `Refunded` is later added to `permits` and places using `PaymentState` are recompiled, the compiler can report that the switch is no longer exhaustive, forcing the maintainer to review the handling rules for `Refunded`.

### 4.1. Why shouldn't you add `default` mechanically?

```java
static String category(PaymentState state) {
    return switch (state) {
        case Pending pending -> "PENDING";
        default -> "OTHER";
    };
}
```

This snippet compiles, but `Captured` and `Rejected` are lumped into `OTHER`. After adding a new subtype, the code continues returning `OTHER` without forcing the maintainer to update it. If every payment variant needs distinct handling, `default` is **hiding business-logic omissions**.

**Design choices:**

- A **closed** set of variants, each with its own semantics: prefer **no `default`**, listing the required patterns explicitly.
- An **open** source such as `Object`, external data, or a protocol with unsupported types: `default -> "UNSUPPORTED"` is a useful fallback policy.
- A `non-sealed` subtype with unbounded extensibility: you can use a type pattern covering that subtype itself and all its subclasses, rather than listing only a few subclasses and hoping it is exhaustive.

### 4.2. Not every `switch` has the same requirements

A `switch` **expression** must always be exhaustive. In Java 21, a `switch` **statement with pattern labels** belongs to *enhanced switch statements* and is also subject to exhaustiveness rules. For classic switch statements using only constants, the rules can differ. Do not use old `switch(int)` habits to assume a pattern switch is allowed to omit subtypes arbitrarily.

Example of the two forms:

```java
// Returning a value (switch expression):
String result = switch (state) {
    case Pending p -> "P";
    case Captured c -> "C";
    case Rejected r -> "R";
};

// Dispatching side effects (switch statement; hypothetical handlers):
switch (state) {
    case Pending p -> onPending(p);
    case Captured c -> onCaptured(c);
    case Rejected r -> onRejected(r);
}
```

The second snippet is only an **illustrative code fragment**; the handlers `onPending`, `onCaptured`, and `onRejected` must be defined in the application.

## 5. `null` still requires its own policy

A normal type pattern such as `case Captured captured` **does not match a `null` selector**. Java 21 allows adding `case null`:

```java
static String statusOrMissing(PaymentState state) {
    return switch (state) {
        case null -> "MISSING";
        case Pending pending -> "PENDING";
        case Captured captured -> "CAPTURED";
        case Rejected rejected -> "REJECTED";
    };
}
```

`sealed` tells you the full set of valid subtypes, but it does not automatically define `null` as a business state.

If `null` is a caller error, you can also reject it early:

```java
java.util.Objects.requireNonNull(state, "state");

String label = switch (state) {
    case Pending p -> "PENDING";
    case Captured c -> "CAPTURED";
    case Rejected r -> "REJECTED";
};
```

In a Java 21 pattern switch, if the selector is `null` and there is no matching null label, a `NullPointerException` can occur; `default` should not be treated as an automatic `null` catcher.

**Distinguish clearly:** "covering all subtypes" (exhaustiveness) and "having a policy for null" are two separate concerns. A method can be exhaustive while still intentionally throwing an exception when given `null`.

## 6. Record pattern: selecting the subtype and destructuring data together

For subtypes declared as records, Java 21 can extract components directly in the case:

```java
static String detail(PaymentState state) {
    return switch (state) {
        case null -> "missing";
        case Pending(var paymentId) ->
            "pending " + paymentId;
        case Captured(var paymentId, var amountVnd) ->
            "captured " + paymentId + ": " + amountVnd + " VND";
        case Rejected(var paymentId, var reason) ->
            "rejected " + paymentId + ": " + reason;
    };
}
```

`Captured(var paymentId, var amountVnd)` is a **record pattern**. Java matches the type `Captured`, then binds the two components **in the order of the record declaration**.

If the record is declared as `Captured(String paymentId, long amountVnd)`, the first variable has inferred type `String` and the second has inferred type `long`. No cast is needed. Accidentally swapping names or order can cause semantic bugs when multiple components share the same type: the compiler checks types, but it does not know that putting `senderId` in `receiverId`'s position is a business error.

### 6.1. When to use a type pattern instead of a record pattern?

Choose based on what the branch needs:

| Goal | Syntax to consider |
| --- | --- |
| Only need to classify the variant | `case Captured captured ->` |
| Need a few accessor properties without destructuring everything | `case Captured captured -> captured.amountVnd()` |
| Need all components directly | `case Captured(var paymentId, var amountVnd) ->` |
| Need to match a nested structure | `case Captured(var id, Money(var amount)) ->` |

A record pattern destructures **the entire component list** of a record positionally. If you only need one field from a record with many components, using a type pattern and an accessor can be cleaner and less coupled to the record declaration's component order.

## 7. Nested record patterns: watch out for null components

Suppose a payment state holds a money record:

```java
record Money(long amountVnd) {}
record Captured(String paymentId, Money money) implements PaymentState {}
```

This snippet is an **alternative model** for the two-component `Captured` record in earlier examples; do not place two different `Captured` declarations in the same file. Section 13 uses the `Captured(String paymentId, Money money)` model.

A nested record pattern:

```java
case Captured(String paymentId, Money(long amountVnd)) ->
    "captured " + paymentId + " for " + amountVnd + " VND";
```

must match both `Captured` and the `Money` component. If `money` is `null`, the nested `Money(...)` **does not match**. Therefore, if you want to handle every `Captured`, you should include a fallback type pattern branch:

```java
case Captured(String id, Money(long amount))
        when amount > 0 -> "valid captured payment";
case Captured captured -> "captured with missing or invalid money";
```

The trailing `Captured captured` branch covers all remaining `Captured` values, including `money = null`. This pattern illustrates an important point: **a sealed hierarchy does not guarantee that a nested record pattern will match every value of a subtype**, because component matching and guards can fail.

Do not place `case Captured captured` before the nested record pattern; the general branch would shadow the specific one (dominance).

## 8. `when` guards on sealed subtypes

In Java 21, guards let you split a subtype into distinct business cases:

```java
case Captured(var paymentId, var amountVnd)
        when amountVnd >= 1_000_000L ->
    "large captured payment";
case Captured(var paymentId, var amountVnd) ->
    "normal captured payment";
```

This **code snippet** uses the `Captured(String paymentId, long amountVnd)` type from Section 1, not the `Captured(..., Money)` version from Section 7. The guard only runs after the record pattern matches, so `amountVnd` holds a valid value inside the `when` condition.

Key characteristics to remember:

- `when` is a guard, not a new subtype.
- Pattern variables are brought into scope for both the guard and the corresponding case body.
- A guarded case **must precede** an unguarded general case.
- When a guard evaluates to false, Java continues searching for a matching label; the general case handles the remaining values of the subtype.
- Guards using arbitrary arithmetic conditions are not fully analyzed by the compiler for coverage; test the logic and precedence separately.

### 8.1. Guards do not replace subtype coverage

The following snippet is **not exhaustive** for `Captured` if only a guarded case is present:

```java
// INTENTIONALLY NON-COMPILING SNIPPET: missing Captured when guard is false
return switch (state) {
    case Pending pending -> "pending";
    case Captured captured when captured.amountVnd() > 0 -> "captured";
    case Rejected rejected -> "rejected";
};
```

If `Captured.amountVnd() <= 0`, the guarded branch is not selected. Fix this by adding an unguarded `Captured` case afterward or an explicitly designed complementary policy.

### 8.2. Dominance: case order matters

```java
// INTENTIONALLY NON-COMPILING SNIPPET: dominated
return switch (state) {
    case Captured captured -> "any captured";
    case Captured captured when captured.amountVnd() > 0 ->
        "positive captured";
    default -> "other";
};
```

The first `Captured` branch already covers every value of that subtype. Swap the two branches so the guarded branch is evaluated first.

If you have multiple guards (for example, prioritizing `>= 5_000_000` then `>= 1_000_000`), order them from most specific to most general and test at the threshold boundaries. Do not treat "the compiler did not report dominance" as proof that every `when` ordering is logically correct.

## 9. Don't use `default` to hide errors when adding a new subtype

A common business change is adding a **`Refunded`** state:

```java
// SNIPPET for a domain change; permits must be updated accordingly:
record Refunded(String paymentId, long refundedAmountVnd)
        implements PaymentState {}
```

You must update:

```java
sealed interface PaymentState
        permits Pending, Captured, Rejected, Refunded {}
```

Upon recompiling, switch expressions without `default` that only handled the three previous subtypes will require reviewing `Refunded`.

If you merely silence the compiler error with:

```java
default -> "unknown";
```

the system might return `unknown` for refunds without auditing or notifying as required. Add a dedicated case instead:

```java
case Refunded refund -> "REFUNDED";
```

**Note when editing:** this `Refunded` snippet and `permits` list are extension examples. They are not in `SealedPatternSwitchDemo.java` in Section 13, because that program intentionally uses only three subtypes to illustrate the current state.

## 10. The `non-sealed` case: an open subclass set with a clear switch

A permitted subtype can be `non-sealed`:

```java
sealed interface Job permits InternalJob, ExternalJob {}
record InternalJob(String id) implements Job {}
non-sealed interface ExternalJob extends Job {}

final class PartnerJob implements ExternalJob {}
final class VendorJob implements ExternalJob {}
```

These are **Java declaration snippets**. `PartnerJob` and `VendorJob` are just two possible implementations of `ExternalJob`; the application may add others.

A switch on `Job` can still be exhaustive thanks to a type pattern covering **the entire open branch**:

```java
static String route(Job job) {
    return switch (job) {
        case InternalJob internal -> "internal";
        case ExternalJob external -> "external";
    };
}
```

`case ExternalJob external` matches not only `PartnerJob` and `VendorJob`, but also any future subtypes of `ExternalJob`.

**Do not** list `PartnerJob` and `VendorJob` and conclude you have handled the entire `ExternalJob` branch; because `ExternalJob` is `non-sealed`, other implementations can exist.

When you want to handle Partner/Vendor specifically:

```java
return switch (job) {
    case InternalJob internal -> "internal";
    case PartnerJob partner -> "partner";
    case VendorJob vendor -> "vendor";
    case ExternalJob external -> "other external";
};
```

This ordering places the specific subclasses before the parent `ExternalJob` pattern. If `ExternalJob external` is placed first, the `PartnerJob` and `VendorJob` cases below it will be dominated.

## 11. Generic sealed interfaces: preserve the selector's static type

Sealed hierarchies can also have type parameters:

```java
sealed interface ApiResult<T> permits Ok, ErrorResult {}

record Ok<T>(T value) implements ApiResult<T> {}
record ErrorResult<T>(String reason) implements ApiResult<T> {}
```

When handling `ApiResult<String>`, the selector's static type remains important. Java uses the generic information available at compile time and pattern applicability rules to determine which patterns are valid; type erasure **does not turn every `ApiResult<T>` into a type that can be arbitrarily checked by `T` at runtime**.

Safe design example:

```java
// SNIPPET: r is ApiResult<String>
return switch (r) {
    case Ok<?> ok -> "ok: " + ok.value();
    case ErrorResult<?> error -> "error: " + error.reason();
};
```

Use `<?>` to match a generic variant without claiming the JVM checked a specific type argument at runtime. If you need `String`-specific behavior, rely on the static type at the API boundary or check the extracted value separately when data comes from a generic source.

In generic sealed hierarchies, type arguments can sometimes make a subtype impossible for a specific selector, so exhaustiveness can be more nuanced than "every name in `permits` must have a case." Let the compiler check against the **actual selector type** and avoid unchecked casts.

## 12. Architecture: short switches at the orchestration layer, long logic in handlers

Pattern switches on sealed interfaces are especially useful at the **application boundary**, where an event/result needs to be mapped to a response, audit label, or handler:

```java
// SNIPPET: handlers must be defined in the application
switch (paymentState) {
    case Pending pending -> onPending(pending);
    case Captured captured -> onCaptured(captured);
    case Rejected rejected -> onRejected(rejected);
}
```

Looking at the switch immediately reveals every outcome type. However, the `onCaptured` branch might need to query a transaction, send a receipt, update a ledger, and handle errors. Those steps should not be crammed into a long `case` block.

### 12.1. Three responsibilities to separate

| Responsibility | Suggested location |
| --- | --- |
| Declaring variants, data, and invariants | `sealed interface` and domain records/classes |
| Selecting behavior by subtype | Pattern `switch`, keeping branches short |
| Executing side effects / complex rules | Independent handlers, policies, or services |

Not every switch needs to be replaced by the visitor pattern or polymorphism. If the frequent change is **adding a new transformation** over a stable set of subtypes, a new switch expression is often simpler and compiler-checked. If all behavior is tightly coupled to each subtype and changes alongside subtypes, polymorphism may be a better fit. Choose based on **responsibilities and direction of change**, not on a blanket "switch is a code smell" rule.

### 12.2. Avoid turning `sealed` into a misguided "domain freeze"

`sealed` restricts inheritance, but it does not mean component data is immutable, business state is always valid, or the system will never evolve. When adding a valid subtype, you must update the model and re-analyze dependent switches — that is the **intended purpose** of this mechanism.

If a plugin system must allow third parties to freely extend many implementations outside your control, a top-level sealed hierarchy covering all plugins may not fit. You can use a `non-sealed` branch or an open registration/interface design at a separate boundary.

## 13. Complete Java 21 program

The following **`SealedPatternSwitchDemo.java`** file demonstrates **type patterns**, **nested record patterns**, **`when` guards**, **fallback cases**, **null policy**, and **exhaustiveness without `default`**. All syntax used is standard in Java 21.

```java
public class SealedPatternSwitchDemo {
    private static final long LARGE_PAYMENT_VND = 1_000_000L;

    sealed interface PaymentState
            permits Pending, Captured, Rejected {}

    record Money(long amountVnd) {}

    record Pending(String paymentId) implements PaymentState {}

    record Captured(String paymentId, Money money)
            implements PaymentState {}

    record Rejected(String paymentId, String reason)
            implements PaymentState {}

    static String describe(PaymentState state) {
        return switch (state) {
            case null -> "missing";

            case Captured(String paymentId, Money(long amountVnd))
                    when amountVnd >= LARGE_PAYMENT_VND ->
                "large captured " + paymentId
                    + ": " + amountVnd + " VND";

            case Captured(String paymentId, Money(long amountVnd)) ->
                "captured " + paymentId
                    + ": " + amountVnd + " VND";

            case Captured captured ->
                "captured " + captured.paymentId() + ": missing money";

            case Pending(String paymentId) ->
                "pending " + paymentId;

            case Rejected(String paymentId, String reason) ->
                "rejected " + paymentId + ": " + reason;
        };
    }

    static String status(PaymentState state) {
        return switch (state) {
            case null -> "NULL";
            case Pending pending -> "PENDING";
            case Captured captured -> "CAPTURED";
            case Rejected rejected -> "REJECTED";
        };
    }

    static long settledAmountVnd(PaymentState state) {
        return switch (state) {
            case null -> 0L;

            case Captured captured when captured.money() != null ->
                captured.money().amountVnd();

            case Captured captured -> 0L;
            case Pending pending -> 0L;
            case Rejected rejected -> 0L;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                "Expected [" + expected + "] but got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        PaymentState[] states = {
            new Pending("PAY-1"),
            new Captured("PAY-2", new Money(750_000L)),
            new Captured("PAY-3", new Money(1_500_000L)),
            new Captured("PAY-4", null),
            new Rejected("PAY-5", "insufficient funds"),
            null
        };

        for (PaymentState state : states) {
            System.out.println(describe(state)
                + " | " + status(state)
                + " | settled=" + settledAmountVnd(state));
        }

        check("large captured PAY-X: 1000000 VND",
            describe(new Captured("PAY-X", new Money(1_000_000L))));

        check("captured PAY-Y: 999999 VND",
            describe(new Captured("PAY-Y", new Money(999_999L))));

        check("captured PAY-4: missing money",
            describe(new Captured("PAY-4", null)));

        check("REJECTED",
            status(new Rejected("PAY-5", "insufficient funds")));

        if (settledAmountVnd(
                new Captured("PAY-6", new Money(42L))) != 42L) {
            throw new AssertionError("Incorrect settled amount");
        }

        System.out.println("checks passed");
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 SealedPatternSwitchDemo.java
java SealedPatternSwitchDemo
```

Stdout output:

```text
pending PAY-1 | PENDING | settled=0
captured PAY-2: 750000 VND | CAPTURED | settled=750000
large captured PAY-3: 1500000 VND | CAPTURED | settled=1500000
captured PAY-4: missing money | CAPTURED | settled=0
rejected PAY-5: insufficient funds | REJECTED | settled=0
missing | NULL | settled=0
checks passed
```

**Why is the program structured this way?**

1. `PaymentState` is a sealed interface and all three permitted subtypes are records, so the direct variant set is closed.
2. `describe` prioritizes the guarded nested record pattern for large amounts, followed by the general nested record pattern, and then the `Captured captured` type pattern to handle `money == null`.
3. `status` only needs to classify subtypes, so type patterns are shorter than record patterns.
4. `settledAmountVnd` expresses a dedicated rule for the settled amount, checking `money != null` before reading `amountVnd`.
5. All three switch expressions are exhaustive without `default`. `case null` expresses a "missing input" policy instead of allowing an NPE.
6. `check` is a runnable assertion helper that does not require `-ea` or a test library.
7. The program intentionally allows `Captured(..., null)` to illustrate that a sealed subtype **does not automatically guarantee valid components**. A real payment application should consider validating this invariant in the constructor and representing data errors explicitly.

## 14. Common compilation and logic errors

### Error 1 — Forgetting a subtype of the sealed hierarchy

```java
// INTENTIONALLY NON-COMPILING SNIPPET: missing Rejected
return switch (state) {
    case Pending p -> "pending";
    case Captured c -> "captured";
};
```

If `state` has type `PaymentState` with three permitted records, this switch expression is not exhaustive. **Fix:** add `case Rejected rejected -> ...` according to business requirements.

### Error 2 — Only having a guarded case for a subtype

```java
// INTENTIONALLY NON-COMPILING SNIPPET: missing Captured when guard is false
return switch (state) {
    case Pending p -> "pending";
    case Captured c when c.money() != null -> "captured";
    case Rejected r -> "rejected";
};
```

**Fix:** add `case Captured c -> "captured without money";` after the guarded case.

### Error 3 — A general branch dominates a specific branch

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (state) {
    case Captured c -> "captured";
    case Captured(String id, Money(long amount)) ->
        "captured with amount"; // Dominated!
    default -> "other";
};
```

**Fix:** move the nested record pattern before `case Captured c`, placing `case Captured c` afterward to handle the rest.

### Error 4 — Adding `default` causes new subtypes to be swallowed

```java
return switch (state) {
    case Pending p -> "pending";
    default -> "other";
};
```

This may not be a syntax error, but it is very dangerous for a sealed domain where each subtype needs distinct handling. **Fix:** list all subtypes explicitly instead of using an unconditional `default`.

### Error 5 — Assuming `sealed` means every component is non-null

```java
// SNIPPET: only safe when invariant money != null holds
case Captured captured ->
    captured.money().amountVnd();
```

If the `money` component is `null`, calling `amountVnd()` throws a `NullPointerException`. **Fix:** validate the data, or provide a separate branch for missing money as in the complete program.

### Error 6 — Using an overly broad type pattern before a subtype

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (state) {
    case PaymentState any -> "any";
    case Captured captured -> "captured"; // Dominated
};
```

`PaymentState any` matches every subtype of a selector of type `PaymentState`. This is no longer subtype-based branching. Only use a general pattern when you truly want to group all remaining variants and have no narrower branches after it.

### Error 7 — Treating a `non-sealed` subtype as a fixed subset

If `ExternalJob` is `non-sealed`, do not assume `PartnerJob` and `VendorJob` are the only implementations. **Fix:** include a broad `ExternalJob external` type pattern to cover other implementations if exhaustiveness is required.

### Error 8 — Overusing casts and `instanceof` instead of pattern switch

```java
if (state instanceof Pending) {
    Pending p = (Pending) state;
    // ...
} else if (state instanceof Captured) {
    Captured c = (Captured) state;
    // ...
}
```

This approach works, but when a new subtype is added it does not give you the same exhaustiveness checking as a switch expression on a sealed hierarchy. **Fix:** when the goal is mapping every variant to a result, prefer a pattern switch.

### Error 9 — Assuming `null` is a permitted subtype

There is no `NullPayment` unless you create such a domain type yourself. The `null` value does not automatically become a subtype in `permits`. **Fix:** decide whether to use `case null`, validate beforehand, or reject with an exception.

## 15. How to test and maintain when adding subtypes

The compiler checks the shape of the type hierarchy, but **it does not verify the business correctness** of each branch.

An appropriate test plan:

| Scenario | What to verify |
| --- | --- |
| Each subtype | `Pending`, `Captured`, and `Rejected` produce the right distinct results |
| Guard thresholds | 999,999; 1,000,000; 1,000,001 VND |
| `null` nested component | `Captured(..., null)` is handled intentionally |
| `null` selector | "Missing" policy or contract-defined error |
| Adding `Refunded` | All exhaustive switches requiring updates are reviewed |
| `non-sealed` case | Future implementations still route to the general branch |
| Multi-module integration | Binaries are compiled and deployed compatibly |

In particular, **do not add `default` just to make a compilation test pass** when the compiler reports a missing new subtype. In versioned environments, changing permitted subtypes and compiling modules separately can cause previously compiled code to run against a newer hierarchy; if an old exhaustive switch finds no matching branch, Java 21 can throw a `MatchException`. Recompile and run compatibility tests rather than trusting an old build.

### 15.1. Steps when adding a new state

1. Define the new subtype as a record or class with clear data invariants.
2. Update `permits` on the sealed interface, or the corresponding child sealed branch.
3. Recompile modules that depend on the hierarchy.
4. Review whether every switch expression/statement on that type needs a new case.
5. Determine how the new state affects formatting, auditing, transaction processing, and error policies.
6. Write unit tests for the new case and integration tests.
7. Check for any `default` that might accidentally mask missing handling; consider deployment versioning strategies.

**Do not assume** "adding a subtype" simply means adding an identical case to every switch. Switches in presentation, auditing, and business workflows may require different behaviors.

## 16. Exercises with answers

### Exercise 1. Why is `default` not needed?

```java
sealed interface Document permits PdfDocument, TextDocument {}
record PdfDocument(byte[] bytes) implements Document {}
record TextDocument(String text) implements Document {}
```

**Question:** Can a switch expression on `Document` with two cases, `PdfDocument` and `TextDocument`, be exhaustive?

**Answer:** Yes. Both direct subtypes are `final` records; if each case is unguarded and covers its corresponding subtype, the switch expression is exhaustive without needing `default`. Handling a `null` selector is a separate decision.

### Exercise 2. Does a guard cover the entire variant?

```java
case PdfDocument pdf when pdf.bytes().length > 0 -> "nonempty";
```

**Question:** Does the case above cover every `PdfDocument`?

**Answer:** No. If `bytes()` has length 0, the guard is false; if `bytes()` is `null`, the guard can even throw an exception. Add a `PdfDocument pdf -> ...` case afterward or establish clear data invariants and policies.

### Exercise 3. What happens when adding subtype `HtmlDocument`?

**Answer:** Update the permitted subtypes of the sealed interface, then recompile all dependent exhaustive switches. Any switch missing the new case will need to be updated. Do not add `default -> ""` to mask missing business requirements.

### Exercise 4. What does `non-sealed` mean for a switch?

```java
sealed interface Job permits ExternalJob {}
non-sealed interface ExternalJob extends Job {}
```

**Answer:** `ExternalJob` can have many future implementations; a `case ExternalJob external -> ...` covers that entire branch. Listing only two existing implementations does not guarantee exhaustiveness.

### Exercise 5. When to use a type pattern vs. a record pattern?

**Answer:** Use `case Captured captured` when you only need the subtype or a few component accessors. Use `case Captured(var id, Money(var amount))` when you need to match structure and extract components directly. With nested patterns, you must have a fallback for `null` or non-matching components.

### Exercise 6. Does `default` catch `null` automatically?

**Answer:** Do not assume so. Java 21 pattern switches have dedicated null rules; add `case null` if you want to map null to a normal state, or reject it with `Objects.requireNonNull`.

### Exercise 7. Should `case PaymentState state` be placed first as a "catch-all"?

**Answer:** Not if you need to distinguish subtypes. That general pattern covers all subtypes and causes narrower branches below it to be dominated. If you need a general fallback, place it last and consider the impact of losing fine-grained exhaustiveness checking.

## 17. Code review checklist

- [ ] Does the `sealed interface` reflect a **domain variant set** that truly needs to be closed?
- [ ] Are the direct permitted subtypes valid and marked appropriately as `final`/`sealed`/`non-sealed`?
- [ ] Does the switch selector keep the sealed interface's static type rather than being widened to `Object`?
- [ ] Do unguarded `case` branches cover all subtypes without a `default` swallowing new variants?
- [ ] Is the `null` policy decided explicitly?
- [ ] Is a type pattern or record pattern chosen based on the data the branch actually needs?
- [ ] Do nested record patterns handle `null` or non-matching components?
- [ ] Are `when` guards placed before general branches and tested at boundaries?
- [ ] Is there any dominance caused by a supertype or overly general type pattern appearing first?
- [ ] Is any `non-sealed` branch covered by a sufficiently broad type pattern?
- [ ] Is lengthy business logic extracted into handlers/policies rather than piled into each case?
- [ ] When a new subtype is added, are dependent switches and modules recompiled, tested, and deployed compatibly?
- [ ] Do pattern variable names accurately reflect the domain, state, and units?

## 18. Official documentation

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): purpose, `sealed` declarations, `permits`, and subtype rules.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `case` patterns, `when` guards, exhaustiveness, dominance, and `null` in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record destructuring and nested record patterns in Java 21.
- [JLS Java SE 21 §9.1.1.4 — sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): declaration requirements for sealed interfaces and permitted subtypes.
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch blocks, case labels, dominance, and exhaustiveness.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): results and exhaustiveness of switch expressions.
- [JLS Java SE 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, and pattern applicability.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): Java 21 examples with sealed hierarchies and case patterns.
