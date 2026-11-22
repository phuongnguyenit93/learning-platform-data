# Documenting Invariants to Support Exhaustive Switch (Java 21+)

## 1. Understanding the Relationship Between Invariants and Exhaustive Switch

When using **pattern matching in `switch`**, a good API design does not only have complete `case` branches; readers must also understand **why the branch list is exhaustive** and **why the data inside each branch can be used safely**.

Two kinds of guarantees must be distinguished:

1. **Type-set guarantee:** a `sealed interface` or `sealed class` defines the set of permitted subtypes. Java 21 can use this type structure to check whether a `switch expression` is **exhaustive**: every non-`null` selector value belonging to those permitted subtypes has a handling path.
2. **Domain data invariant:** constructors/factories/validation guarantee the internal state of a valid object. For example, “a `Shipped` object always has a non-null, non-blank `trackingCode`”. This invariant allows the matched branch to call `trackingCode.toUpperCase(...)` without throwing `NullPointerException` along valid object-creation paths.

**Key takeaway:** a business invariant does not automatically make the compiler treat a `case ... when ...` as exhaustive. The compiler relies on **the type system and pattern dominance/coverage rules**; it does not prove arbitrary business conditions checked by a constructor.

Therefore, “documenting invariants to support exhaustive switch” should be understood accurately as:

- **Documenting the closed set of variants** so readers see the basis for the exhaustiveness check.
- **Documenting the invariant of each variant** so branches can use data safely.
- **Documenting the `null` and guard policy** so compiler guarantees are not mistakenly attributed to a domain rule.
- **Documenting the API evolution commitment** because adding a new subtype can make callers' `switch` statements non-exhaustive.

This article presents how to design, write Javadoc, place comments appropriately, write positive/negative tests, and maintain the contract on **Java 21+**.

## 2. An Example Model: Order State as a Closed Set of Variants

Suppose the domain has four order states:

| Variant | Specific payload | Invariant to protect |
| --- | --- | --- |
| `Draft` | `orderId` | Order ID is non-null and non-blank |
| `Paid` | `orderId`, `amountCents` | Valid ID; payment amount is positive |
| `Shipped` | `orderId`, `trackingCode` | Order ID and tracking code are non-null/non-blank |
| `Cancelled` | `orderId`, `reason` | Order ID and cancellation reason are non-null/non-blank |

An older design might put all information into a single record:

~~~java
enum Status { DRAFT, PAID, SHIPPED, CANCELLED }

record OrderData(
        Status status,
        String orderId,
        long amountCents,
        String trackingCode,
        String cancelReason) {}
~~~

This is a **problem-illustration model** without validation. It allows creating `OrderData(SHIPPED, "O1", 0, null, null)`, meaning a shipped state missing a tracking code; or a `DRAFT` state that has a cancellation reason. Many field combinations have no domain meaning.

Instead, model four separate variants:

~~~java
sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}

record Draft(String orderId) implements OrderState {}
record Paid(String orderId, long amountCents) implements OrderState {}
record Shipped(String orderId, String trackingCode) implements OrderState {}
record Cancelled(String orderId, String reason) implements OrderState {}
~~~

These four records are only **illustrative type declarations**; the next section adds compact constructors to prevent invalid data.

`sealed` describes **the set of permitted direct subtypes**. `record` is `final` by default, so in this example each branch is a terminal type; no new subclasses can be added arbitrarily beneath those records.

This helps the compiler evaluate whether a `switch` handles all four `OrderState` types. However, **`sealed` does not check component values by itself**. It does not prove that `amountCents > 0` or `trackingCode != null`. The two layers of guarantees must be expressed separately in API documentation.

## 3. Documenting the Contract Where Invariants Are Declared

If pattern branches are going to rely on an invariant, you must **enforce the invariant first**, rather than merely writing a comment asserting it always holds.

~~~java
static String requireText(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(field);
    }
    return text;
}

record Draft(String orderId) implements OrderState {
    Draft {
        requireText(orderId, "orderId");
    }
}

record Paid(String orderId, long amountCents) implements OrderState {
    Paid {
        requireText(orderId, "orderId");
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amountCents");
        }
    }
}

record Shipped(String orderId, String trackingCode) implements OrderState {
    Shipped {
        requireText(orderId, "orderId");
        requireText(trackingCode, "trackingCode");
    }
}

record Cancelled(String orderId, String reason) implements OrderState {
    Cancelled {
        requireText(orderId, "orderId");
        requireText(reason, "reason");
    }
}
~~~

These are **illustrative components in the same declaration scope**, not yet a standalone file: they need `OrderState` and `requireText` placed together in the right scope. Section 9 has the complete runnable program.

Compact constructors validate parameters before components are assigned. If an input violates a rule, the constructor throws `IllegalArgumentException` right at object creation.

For example:

~~~java
new Paid("O1", 1500);             // Valid
new Shipped("O1", "trk-9");       // Valid

new Paid("O1", 0);                // IllegalArgumentException
new Shipped("O1", null);         // IllegalArgumentException
new Cancelled("O1", "  ");        // IllegalArgumentException
~~~

**Java records themselves do not have non-null types by default.** `String trackingCode` still allows `null` without validation. Therefore, comments or Javadoc about an invariant must point to **the enforcing code that guarantees it**.

If a record holds a `List`, an array, or a mutable object, the record only has **shallow immutability**. An invariant on collection contents requires defensive copying or an appropriate immutable design. The lesson's example uses `String` and primitive types, with no mutable components.

## 4. Exhaustive Switch: Completeness Comes from the Subtype Set

With `OrderState` declared as sealed and four terminal subtypes, a `switch expression` can handle all of them:

~~~java
static String summary(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");

    return switch (state) {
        case Draft(var id) -> "draft:" + id;
        case Paid(var id, var cents) -> "paid:" + id + ":" + cents;

        // Invariant: trackingCode in Shipped is non-null and non-blank.
        // Checked by Shipped's compact constructor.
        case Shipped(var id, var tracking) ->
                "shipped:" + id + ":"
                + tracking.toUpperCase(java.util.Locale.ROOT);

        case Cancelled(var id, var reason) ->
                "cancelled:" + id + ":" + reason;
    };
}
~~~

This is an **illustrative method**, located in the class containing the records from section 3. A complete version is in section 9.

There is no `default`, yet the compiler accepts it because the branches cover all permitted subtypes of `OrderState` in the example structure.

Note the two layers of guarantees in the code:

- **Exhaustiveness:** the compiler infers this from `OrderState permits Draft, Paid, Shipped, Cancelled`, the subtypes, and the corresponding patterns.
- **Data safety:** the call `tracking.toUpperCase(...)` relies on the contract “`Shipped.trackingCode` is non-null” enforced by the constructor. The compiler **does not know on its own** that every `tracking` string in this branch has been validated.

Because `case Shipped(var id, var tracking)` uses unguarded component patterns, it covers `Shipped` instances according to record pattern coverage rules. Omitting `default` helps detect when the subtype set changes upon recompilation.

**Avoid writing a comment like “exhaustive because trackingCode is always valid”.** That statement conflates two reasons. A better comment is:

> The `switch` is exhaustive because `OrderState` is sealed with four permitted subtypes; the `Shipped` branch is safe to use `trackingCode` thanks to constructor validation.

## 5. A Guard Does Not Become Exhaustive Because of an Invariant

This is the most important point when documentation discusses invariants and `switch`.

Suppose `Shipped`'s constructor guarantees that the tracking code **always starts with `"X"`**. Someone might think the following branch covers all of `Shipped`:

~~~java
// INTENTIONALLY DOES NOT COMPILE without another Shipped case or default.
return switch (state) {
    case Shipped(var tracking) when tracking.startsWith("X") -> "shipping";
    case Closed c -> "closed";
};
~~~

To make the example clear and avoid confusion over the number of components, here is a **hypothetical model different from `OrderState`**:

~~~java
sealed interface State permits Shipped, Closed {}

record Shipped(String tracking) implements State {
    Shipped {
        if (tracking == null || !tracking.startsWith("X")) {
            throw new IllegalArgumentException("tracking");
        }
    }
}

record Closed() implements State {}
~~~

When placing `return switch (state) {...}` in a method taking `State state` of the same model, Java 21 **reports that the switch is not exhaustive**. The reason: the compiler does not treat the `when tracking.startsWith("X")` condition as unconditional coverage, even though the constructor checked the `"X"` prefix.

**How to fix it so the compiler can verify completeness:**

~~~java
static String label(State state) {
    return switch (state) {
        case Shipped(var tracking) when tracking.startsWith("X") ->
                "shipping-priority";
        case Shipped(var tracking) -> "shipping-other";
        case Closed c -> "closed";
    };
}
~~~

This is an illustrative snippet for the `State` model above; it is **not** part of the main program in section 9. The second `Shipped` branch has no guard, so it covers the remainder of the subtype, including cases where the earlier guard does not match. If the invariant holds along valid object-creation paths, that fallback branch may rarely execute, but it **is still required for the exhaustiveness guarantee in source code**.

Do not fix this by mechanically adding `default` just to silence the error. `default` can prevent the compiler from reminding you to update handling when a new subtype is added.

### Why Is This Useful for API Documentation?

Javadoc should describe both:

1. **The invariant of `Shipped`:** the constructor only accepts valid codes.
2. **The limit of compiler checking:** runtime conditions in `when` are not inferred from Javadoc or the constructor implementation.

Documentation helps developers **avoid false inferences** about exhaustiveness and know when to use an unguarded branch or reorganize the type model.

## 6. Designing Guards with Fallback Branches on the Real Model

A guarded handling approach is classifying the shipping method by tracking code prefix:

~~~java
static String carrier(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");

    return switch (state) {
        case Shipped(var id, var tracking)
                when tracking.startsWith("X") -> "priority-shipping";

        case Shipped(var id, var tracking) -> "standard-shipping";

        case Draft d -> "not-shipped";
        case Paid p -> "not-shipped";
        case Cancelled c -> "not-shipped";
    };
}
~~~

This is an illustrative method on the `OrderState` model, included verbatim in the class in section 9.

The guarded branch `Shipped ... when tracking.startsWith("X")` applies only to a **subset** of `Shipped`. The unguarded `Shipped(...)` branch afterward ensures the remaining `Shipped` values have a handling path.

Order matters: if you move the broader `Shipped(...)` branch earlier, the `when` branch afterward may be rejected by the compiler as **dominated**. When writing maintenance documentation, explicitly state why the specific branch must come before the general one.

In the example, `trackingCode` is only required to be non-blank, **not** forced to have a specific prefix. Thus both `Shipped` branches can genuinely occur:

- `Shipped("O1", "X-7")` → `"priority-shipping"`.
- `Shipped("O2", "trk-9")` → `"standard-shipping"`.

This differs from the `State` model in section 5, where the constructor hypothetically allowed only codes starting with `"X"`. The two models intentionally have different invariants; do not mix their conclusions.

## 7. Documenting the Null Policy: Exhaustive Does Not Mean Catching Every Null

An exhaustive `switch` on a `sealed interface` can cover **all valid non-null subtypes** and still not handle a `null` selector in a business-meaningful way.

The `summary` method in section 4 uses:

~~~java
java.util.Objects.requireNonNull(state, "state");
~~~

This means the API **explicitly rejects null**, throwing `NullPointerException` at the method boundary. This is an intentional contract.

If an API must accept `null` as a “no state yet” value, it can be written as:

~~~java
static String nullableSummary(OrderState state) {
    return switch (state) {
        case null -> "missing-state";
        case Draft d -> summary(d);
        case Paid p -> summary(p);
        case Shipped s -> summary(s);
        case Cancelled c -> summary(c);
    };
}
~~~

`case null` handles the `null` selector. The remaining branches cover the four closed subtypes. `default` in a Java 21 pattern switch **does not automatically match `null`**, so it must be designed explicitly.

API documentation should answer:

- Is `null` an **API caller bug** or a valid business state?
- If rejected, which exception is thrown and where?
- If accepted, what does `case null` mean to the caller?

Do not write “all cases are covered” while omitting the null contract. **Type exhaustiveness** and **null handling** are two separate questions.

### Warning About Null in Record Components

A record component variable such as `var tracking` can receive `null` if the constructor does not guard against it. Even a typed subpattern like `String tracking`, when **unconditional** for a static `String` component, can still match a `null` value in Java 21.

Therefore, record patterns **do not replace validation**. To call `tracking.toUpperCase(...)` safely, the code needs an enforced invariant or an inline null-check guard.

## 8. Javadoc and Comments: What to Write Where?

### 8.1. Javadoc on the Sealed Interface: Publish the Variant List

A helpful description:

~~~java
/**
 * Valid order states modeled as a closed set of subtypes:
 * Draft, Paid, Shipped, and Cancelled.
 *
 * Methods processing OrderState should use an exhaustive switch
 * without default when they need the compiler to prompt for updates when adding a variant.
 *
 * A null selector is not a valid OrderState;
 * each API explicitly decides whether to reject or handle null.
 */
sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}
~~~

This is an **illustration of API documentation style**. The real declaration must be combined with the records in the same package/module according to `sealed` rules.

Listing the variants in Javadoc helps API users understand **the set of states**. However, Javadoc is documentation; the type list checked by the compiler lives in **`permits` and the subtype definitions**. Updating only Javadoc without updating `permits` does not change the type set.

### 8.2. Javadoc on the Record: State Invariants as a Contract

Example:

~~~java
/**
 * Order has been handed over to the carrier.
 *
 * @param orderId order ID, non-null and non-blank
 * @param trackingCode tracking code, non-null and non-blank
 * @throws IllegalArgumentException if any component is invalid
 */
record Shipped(String orderId, String trackingCode) implements OrderState {
    Shipped {
        requireText(orderId, "orderId");
        requireText(trackingCode, "trackingCode");
    }
}
~~~

This is an illustrative snippet; `requireText` must be declared in the enclosing scope of the record. When designing a public API, descriptions of allowed value types and exceptions should be attached to the appropriate constructor/component API according to the project's Javadoc conventions.

A short note at the handling site:

~~~java
// Shipped constructor guarantees trackingCode != null and !isBlank().
case Shipped(var id, var tracking) ->
        tracking.toUpperCase(java.util.Locale.ROOT);
~~~

It explains a **non-obvious assumption**: why dereferencing `tracking` needs no extra guard.

### 8.3. Avoiding Misleading Comments

**Weak comment:**

~~~java
// This switch is exhaustive because the data is always valid.
~~~

Wrong about the cause: valid data does not make a `when` branch exhaustive.

**More accurate comment:**

~~~java
// Exhaustive: OrderState is sealed, and all four final records have a case.
// Safe dereference: Shipped constructor rejects null/blank trackingCode.
// If permits or the constructor changes, re-verify the switch and tests.
~~~

Where readers can easily see it, a comment should explain **the dependency between the model and the handling path**, rather than repeating syntax the compiler already makes clear.

### 8.4. When Is No Comment Needed?

If a small function already uses `Objects.requireNonNull` and all branches are straightforward with no hidden business assumptions, adding a comment on every `case` can create clutter. Prefer:

- A complete contract in **API declarations/Javadoc**.
- A short comment at **points that depend on cross-field invariants or implicit conditions**.
- Tests verifying that the conditions are enforced; never treat comments as a protection mechanism.

## 9. Complete Java 21 Program with 21 Test Cases

Create the file **`ExhaustiveInvariantDemo.java`** and copy the entire program exactly:

~~~java
public class ExhaustiveInvariantDemo {
    sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}

    record Draft(String orderId) implements OrderState {
        Draft { requireText(orderId, "orderId"); }
    }

    record Paid(String orderId, long amountCents) implements OrderState {
        Paid {
            requireText(orderId, "orderId");
            if (amountCents <= 0) {
                throw new IllegalArgumentException("amountCents");
            }
        }
    }

    record Shipped(String orderId, String trackingCode) implements OrderState {
        Shipped {
            requireText(orderId, "orderId");
            requireText(trackingCode, "trackingCode");
        }
    }

    record Cancelled(String orderId, String reason) implements OrderState {
        Cancelled {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field);
        }
        return text;
    }

    static String summary(OrderState state) {
        java.util.Objects.requireNonNull(state, "state");
        return switch (state) {
            case Draft(var id) -> "draft:" + id;
            case Paid(var id, var cents) -> "paid:" + id + ":" + cents;
            // Invariant: Shipped.trackingCode is non-null and non-blank.
            // Enforced in Shipped's compact constructor.
            case Shipped(var id, var tracking) ->
                    "shipped:" + id + ":"
                    + tracking.toUpperCase(java.util.Locale.ROOT);
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
        };
    }

    static String carrier(OrderState state) {
        java.util.Objects.requireNonNull(state, "state");
        return switch (state) {
            case Shipped(var id, var tracking)
                    when tracking.startsWith("X") -> "priority-shipping";
            case Shipped(var id, var tracking) -> "standard-shipping";
            case Draft d -> "not-shipped";
            case Paid p -> "not-shipped";
            case Cancelled c -> "not-shipped";
        };
    }

    static String nullableSummary(OrderState state) {
        return switch (state) {
            case null -> "missing-state";
            case Draft d -> summary(d);
            case Paid p -> summary(p);
            case Shipped s -> summary(s);
            case Cancelled c -> summary(c);
        };
    }

    private static int passed = 0;

    static void check(String name, String got, String expected) {
        if (!java.util.Objects.equals(got, expected)) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + got);
        }
        ++passed;
        System.out.println("PASS " + name + " -> " + got);
    }

    static void expectInvalid(String name, Runnable attempt) {
        try {
            attempt.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + name);
        } catch (IllegalArgumentException expected) {
            ++passed;
            System.out.println("PASS " + name);
        }
    }

    static void expectNull(String name, Runnable attempt) {
        try {
            attempt.run();
            throw new AssertionError(
                    "Expected NullPointerException: " + name);
        } catch (NullPointerException expected) {
            ++passed;
            System.out.println("PASS " + name);
        }
    }

    public static void main(String[] args) {
        OrderState draft = new Draft("O1");
        OrderState paid = new Paid("O1", 1500);
        OrderState shippedX = new Shipped("O1", "X-7");
        OrderState shippedStd = new Shipped("O2", "trk-9");
        OrderState cancelled = new Cancelled("O3", "customer");

        check("draft", summary(draft), "draft:O1");
        check("paid", summary(paid), "paid:O1:1500");
        check("shipped", summary(shippedStd), "shipped:O2:TRK-9");
        check("cancelled", summary(cancelled), "cancelled:O3:customer");
        check("priority", carrier(shippedX), "priority-shipping");
        check("standard", carrier(shippedStd), "standard-shipping");
        check("carrier-draft", carrier(draft), "not-shipped");
        check("carrier-paid", carrier(paid), "not-shipped");
        check("carrier-cancelled", carrier(cancelled), "not-shipped");
        check("nullable-null", nullableSummary(null), "missing-state");
        check("nullable-shipped",
                nullableSummary(shippedX), "shipped:O1:X-7");

        expectInvalid("draft-blank-id", () -> new Draft("  "));
        expectInvalid("paid-null-id", () -> new Paid(null, 100));
        expectInvalid("paid-zero", () -> new Paid("O1", 0));
        expectInvalid("paid-negative", () -> new Paid("O1", -5));
        expectInvalid("shipped-null-id",
                () -> new Shipped(null, "T-1"));
        expectInvalid("shipped-null-tracking",
                () -> new Shipped("O1", null));
        expectInvalid("shipped-blank-tracking",
                () -> new Shipped("O1", " "));
        expectInvalid("cancelled-blank-reason",
                () -> new Cancelled("O1", ""));
        expectInvalid("cancelled-null-reason",
                () -> new Cancelled("O1", null));
        expectNull("summary-null", () -> summary(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile with **JDK 21 or later** and run:

~~~bash
javac --release 21 ExhaustiveInvariantDemo.java
java ExhaustiveInvariantDemo
~~~

**Deterministic output:**

~~~text
PASS draft -> draft:O1
PASS paid -> paid:O1:1500
PASS shipped -> shipped:O2:TRK-9
PASS cancelled -> cancelled:O3:customer
PASS priority -> priority-shipping
PASS standard -> standard-shipping
PASS carrier-draft -> not-shipped
PASS carrier-paid -> not-shipped
PASS carrier-cancelled -> not-shipped
PASS nullable-null -> missing-state
PASS nullable-shipped -> shipped:O1:X-7
PASS draft-blank-id
PASS paid-null-id
PASS paid-zero
PASS paid-negative
PASS shipped-null-id
PASS shipped-null-tracking
PASS shipped-blank-tracking
PASS cancelled-blank-reason
PASS cancelled-null-reason
PASS summary-null
ALL PASSED: 21
~~~

### What the Tests Confirm

- The four cases `draft`, `paid`, `shipped`, `cancelled` confirm that `summary` handles all four subtypes.
- The two cases `priority` and `standard` prove that both the `when` branch and the fallback branch for `Shipped` can execute in the article's model.
- The three `carrier-*` cases prove that all remaining subtypes have a handling path in `carrier`.
- `nullable-null` shows that `case null` can encode a policy for handling a null selector; `summary-null` confirms that another API chooses to reject `null` explicitly.
- Nine `expectInvalid` calls? Yes: the program has **nine** `expectInvalid` calls, from a blank order ID to a null cancellation reason. They prove that constructors protect invariants before the switch uses the data.
- Each `check` or exception test that does not match expectations throws `AssertionError`; the line `ALL PASSED: 21` is printed only after all checks pass.

**Important distinction:** the 21 cases here verify runtime behavior, including invalid data rejected by constructors. **Exhaustiveness** of `summary` and `carrier` is verified by the compiler at compile time, not by running all 21 cases. The two kinds of checks complement each other.

## 10. Negative Compile Test: Proving Compiler Limits

A runtime test cannot prove that the compiler will reject a `switch` missing a branch. For that purpose, create a **separate file** `GuardOnlyCompileError.java` as follows:

~~~java
public class GuardOnlyCompileError {
    sealed interface State permits Shipped, Closed {}

    record Shipped(String tracking) implements State {
        Shipped {
            if (tracking == null || !tracking.startsWith("X")) {
                throw new IllegalArgumentException("tracking");
            }
        }
    }

    record Closed() implements State {}

    static String label(State state) {
        return switch (state) {
            case Shipped(var tracking)
                    when tracking.startsWith("X") -> "shipping";
            case Closed c -> "closed";
        };
    }
}
~~~

Run the command:

~~~bash
javac --release 21 GuardOnlyCompileError.java
~~~

**Expected:** the compiler rejects it because the `switch expression` **does not cover all possible input values**. Even though `Shipped`'s constructor requires the tracking code to start with `"X"`, the `case Shipped(...) when ...` branch is still a guarded branch, so **the compiler does not consider it to cover all of `Shipped`**.

This is a file that **intentionally fails to compile**, and must not be copied into the main program in section 9. A *negative compile test* should verify that `javac` fails **due to lack of exhaustiveness**, rather than treating any syntax error or missing class as a PASS.

The fix while keeping the business condition is to add an unguarded `Shipped` branch after the guarded branch. When testing similar scenarios, inspect the compiler diagnostics of your actual JDK version because message wording may vary.

## 11. When Adding a Subtype: The Type-Set Invariant Is Also an API Contract

Suppose the project needs to add a `Returned` state. To do so, a developer must:

1. Define the `Returned` subtype with its own payload/invariant.
2. Add `Returned` to `OrderState`'s `permits` list.
3. Recompile consumers that have exhaustive `switch expression`s. `switch`es lacking a `Returned` branch and without an appropriate fallback may be rejected at compile time.
4. Add handling logic and tests for the new variant.
5. Update **Javadoc regarding the state list, constraints, and state transition rules**.

An illustrative subtype, **not included in the program in section 9**:

~~~java
record Returned(String orderId, String returnReason)
        implements OrderState {
    Returned {
        requireText(orderId, "orderId");
        requireText(returnReason, "returnReason");
    }
}
~~~

The snippet above also requires updating `permits` and the `switch`es; it cannot simply be pasted into the main program and expected to run on its own. This is the value of exhaustive switch: when the variant set changes, the compiler can point out code locations that have not been updated.

### Notes for Public Libraries

The subtype set of a `sealed` type is **part of the API extension contract**:

- Consumers can write a `switch` without `default` and rely on the closed subtype list at compile time.
- Adding a subtype in a new release can cause **source compatibility** errors in consumers' exhaustive switches when they recompile.
- Upgrading a library while keeping old consumer binaries also requires compatibility testing and runtime update handling; you cannot automatically assume all previously compiled code is safe with a new subtype.
- If the API is designed for external plugins to create many subtypes on their own, an open interface or handler registration model may be more suitable. Use `sealed` when **a closed set of variants** is genuinely a domain characteristic you want to publish.

**Do not mindlessly add `default` just to avoid compiler reminders to update.** For a closed domain, having to handle new variants is usually desirable. Conversely, an API with an explicit “unknown future variant” strategy can intentionally use a fallback, but should document that contract and test its consequences.

## 12. Documentation Rules for Different Invariants

| Kind of guarantee | Who enforces it? | Where to document? | What not to misconceive |
| --- | --- | --- | --- |
| Closed subtype list | Compiler based on `sealed`/`permits` and subtypes | Javadoc on interface + type declaration | Comments alone do not make it exhaustive |
| Non-null/non-blank payload | Constructor, factory, validation | Javadoc on record/constructor and negative tests | `record`/`String` does not imply non-null |
| Cross-field relationships | Business validation code | Model contract and tests | Compiler does not prove arbitrary cross-field invariants |
| `when` conditions | Runtime logic in guard | Document the rule when non-obvious | Guarded case does not cover the whole subtype |
| `null` selector | API contract, `requireNonNull`, or `case null` | Method Javadoc | Exhaustiveness over sealed subtypes does not replace null policy |
| Future subtype additions | API change process + compiler on recompilation | Versioning/changelog/Javadoc | Do not assume all subtype-set changes are compatible |
| Unvalidated input data | Boundary parser/validator | Contract on DTO/domain mapper | Pattern matching does not replace validation |

When writing API documentation, prefer **specific and testable** statements: “`trackingCode` must be non-`null` and non-blank; the constructor throws `IllegalArgumentException` if invalid” is more valuable than “the state is always valid”.

If a contract is not yet enforced, do not write comments claiming it is already true. Add validation code, tests, or redesign the types first.

## 13. Common Misconceptions

**Misconception 1 — “Constructor invariants make a `when` branch exhaustive.”** No. The compiler does not prove business conditional expressions in guards from constructors. You need an unguarded covering branch or an appropriate type organization.

**Misconception 2 — “`sealed` protects all data inside a record.”** `sealed` restricts direct subtypes. It does not guarantee non-null strings, positive amounts, or relationships across multiple fields.

**Misconception 3 — “There are four case branches, so it must be exhaustive.”** You must look at the selector type, pattern types, and guards. Four branches might not cover the entire type set or might contain patterns rejected by the compiler.

**Misconception 4 — “`default` handles every case.”** In Java 21 pattern switches, `default` does not automatically handle a `null` selector. At the same time, an overly broad `default` can hide forgetting to update for a new subtype.

**Misconception 5 — “The variable `var tracking` is always non-null because Java knows it is a String.”** The static type `String` is not equivalent to a non-null constraint. A component pattern can receive `null`; a reliable constructor or guard is required.

**Misconception 6 — “If the comment is accurate, tests are unnecessary.”** Comments can become outdated when constructors change. Testing valid and invalid data protects the invariants that branches depend on.

**Misconception 7 — “Exhaustiveness guarantees every business operation will succeed.”** It only checks structural type/branch coverage. Handling paths can still throw exceptions, fail infrastructure calls, or violate other domain rules.

**Misconception 8 — “Adding a subtype is an internal change.”** With a public `sealed API`, consumers may rely on the variant list. Adding a subtype requires versioning plans and compatibility checks.

**Misconception 9 — “Records are deeply immutable.”** Records are shallowly immutable with `final` components. If they hold mutable objects, content invariants can be broken after the constructor checks them.

**Misconception 10 — “Runtime tests can replace compiler checks.”** Tests only verify the inputs that were run; exhaustiveness requires the compiler's guarantee. Conversely, the compiler does not replace content validation tests.

## 14. Review Checklist and Exercises

### Checklist

1. Is the interface/class marked `sealed` appropriately for the domain's purpose? Do the direct subtypes match the `permits` list?
2. Is there any `non-sealed` subtype that widens the value set to be handled? If so, clearly describe its impact on classification.
3. Does each subtype have a payload contract and constructor/factory validation?
4. For a `switch expression`, do the **unguarded** branches cover all required subtypes?
5. Are `when` branches placed before the general branch of the same subtype?
6. Is a `null` selector explicitly rejected or handled with `case null`?
7. Where pattern variables are dereferenced, is there a reliable invariant or protective guard?
8. Does Javadoc distinguish exhaustiveness due to **types** from data safety due to **invariants**?
9. Are there runtime tests for each subtype and for invalid data cases?
10. When adding a new subtype, are consumers recompiled and API documentation updated?
11. Is a broad `default` avoided when the subtype set is designed to be closed?
12. Is there a negative compile test proving that guard-only branches do not provide an exhaustiveness guarantee?

### Exercises

- Add a `Returned` subtype to `OrderState`, update `permits`, and try compiling `summary`. Observe the locations that need updating and add tests.
- In the `State` model from section 5, remove the unguarded `case Shipped(...)` branch. Observe the compiler rejecting the `switch` even though the constructor only allows tracking codes starting with `"X"`.
- Temporarily remove the null check for `Shipped.trackingCode` in the constructor and construct `new Shipped("O1", null)`. Find where `summary` relies on the old invariant and explain why comments can be misleading.
- Change `summary` from `Objects.requireNonNull` to `case null`; update the contract and the `summary-null` test accordingly.
- Write Javadoc for `Paid`: non-blank order ID, `amountCents > 0`, and document the exception on violation. Cross-check with the `paid-zero` and `paid-negative` tests.
- Discuss a plugin API with open subtypes: should you use `sealed`, `non-sealed`, or a regular interface? State the trade-offs between extensibility and compiler exhaustiveness.

**Remember:** **`sealed` and subtype types** provide the basis for the compiler to check exhaustive `switch`; **constructor/factory invariants** provide the basis for using data safely inside each branch; **`when`** is a runtime condition and is not treated as covering an entire subtype just because Javadoc claims the condition always holds. Documenting each guarantee clearly, handling `null` intentionally, and protecting them with tests makes pattern matching APIs easier to understand, safer, and more evolvable.
