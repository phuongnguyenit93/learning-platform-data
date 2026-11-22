# Integrated Practice: Writing a Switch Expression on a Sealed Type (Java 21)

## 1. Learning Objectives and Problem Statement

In Java 21, a `switch expression` can use **type patterns**, **record patterns**, **`when` guards**, and the list of subtypes of a **`sealed`** type. When the branches cover the entire hierarchy, the compiler can verify that the switch expression is **exhaustive** without needing to add a `default` branch just to make the code compile.

This integrated practice exercise does not stop at a single `switch` example that returns a string. Learners will:

1. Design a **multi-level sealed hierarchy** modeled after a business domain.
2. Write a `switch expression` that returns a string, covering every concrete subtype.
3. Deconstruct a record using a record pattern and handle a nested record that may be `null`.
4. Write two cases for the same type with `when`, where the guarded case comes **before** the unguarded case.
5. Compare this with writing a switch over an **intermediate** subtype for grouping.
6. Return a **structured result type** from a switch expression using `yield` when a case requires multiple statements.
7. Test `null`, thresholds, fallback branches, exhaustiveness, and dominance with deterministic data.
8. Understand the behavior when the hierarchy changes and how to turn compiler errors into an API control advantage.

**Prerequisites:** JDK 21 or later for finalized record patterns and pattern matching for switch (JEP 440, JEP 441). Sealed classes/interfaces have been finalized since Java 17 (JEP 409). The examples can be compiled with `javac --release 21` and do not use preview features.

### Business Context

A payment application receives **payment event results**:

- `Authorized`: the payment has been approved, with a payment ID and total amount.
- `Declined`: rejected, with a payment ID and reason code.
- `AnalystReview`: requires a human analyst to review.
- `FraudAlert`: has fraud risk signals that need investigation.

The last two belong to the `ReviewEvent` group. We want to render an event summary, classify events into business groups, and produce an action for the UI or review queue.

This is an exercise in **branching over a closed set of types**, not a real payment system implementation. Strings like `"approved"` and `"fraud"` in the example are purely simulated labels; they must not be interpreted as real bank transaction confirmations or anti-fraud decisions.

## 2. Reading the Sealed Tree Before Writing the Switch

Type model:

```text
PaymentEvent (sealed interface)
├── Authorized      (record, final)
├── Declined        (record, final)
└── ReviewEvent     (sealed interface)
    ├── AnalystReview  (record, final)
    └── FraudAlert     (record, final)

Money (record value object; not a PaymentEvent)

Decision (action result sealed interface)
├── Screen       (record, final)
└── ReviewTicket (record, final)
```

Declarations:

```java
sealed interface PaymentEvent
        permits Authorized, Declined, ReviewEvent {
    String paymentId();
}

sealed interface ReviewEvent extends PaymentEvent
        permits AnalystReview, FraudAlert {}

record Money(long cents, String currencyCode) {}

record Authorized(String paymentId, Money total)
        implements PaymentEvent {}

record Declined(String paymentId, String reasonCode)
        implements PaymentEvent {}

record AnalystReview(String paymentId, String reviewQueue)
        implements ReviewEvent {}

record FraudAlert(String paymentId, int riskScore)
        implements ReviewEvent {}
```

This is a **structural illustration snippet**, which can be used inside an enclosing class like the complete program in Section 9.

**Relationships to keep in mind:**

- `PaymentEvent` has three **direct permitted subtypes**: `Authorized`, `Declined`, `ReviewEvent`.
- `AnalystReview` and `FraudAlert` do **not** appear directly in `PaymentEvent permits`; they are indirect subtypes through `ReviewEvent`.
- `ReviewEvent` is itself `sealed`, so its direct subtypes are restricted to the two records.
- Record classes are implicitly `final`; therefore, there are no deeper subtypes of `Authorized`, `Declined`, `AnalystReview`, or `FraudAlert` via normal inheritance.
- Each record has a `paymentId` component of type `String` and a record-generated `paymentId()` accessor, satisfying the interface contract.
- `Money` does not belong to the hierarchy; it is a component value of `Authorized`.

**An academic yet very practical conclusion:** if the selector has static type `PaymentEvent`, every valid **non-`null` instance** must belong to one of the four leaf records in the current model. Therefore, the switch can list the four leaves, or use a single `ReviewEvent` case to cover the last two leaves.

## 3. First, Write a Simple Switch Version by Subtype

An initial goal is to classify each event:

```java
static String group(PaymentEvent event) {
    return switch (event) {
        case Authorized authorized -> "completed";
        case Declined declined -> "failed";
        case ReviewEvent review -> "manual";
    };
}
```

This method is part of the sample program in Section 9, where the types are declared. It illustrates a **type pattern**: `case Authorized authorized` checks the type and binds a reference `authorized`, without deconstructing the record.

Why are there only three cases when the hierarchy has four leaf records?

- `Authorized` is handled separately.
- `Declined` is handled separately.
- Every `AnalystReview` and `FraudAlert` is a `ReviewEvent`, so `case ReviewEvent review` covers both.

The compiler knows this relationship from `sealed` and `permits`. With a selector of type `PaymentEvent`, this is an **exhaustive switch expression** for non-`null` values.

If the business logic only needs to know whether an event belongs to the completed/failed/manual-review group, this grouping approach is often **easier to read** than listing every leaf record. However, if each subtype requires different handling, specific cases must be added instead of grouping everything under `ReviewEvent`.

### Comparison with if/else

```java
static String groupIfElse(PaymentEvent event) {
    if (event instanceof Authorized) {
        return "completed";
    }
    if (event instanceof Declined) {
        return "failed";
    }
    if (event instanceof ReviewEvent) {
        return "manual";
    }
    throw new IllegalArgumentException("unhandled event");
}
```

This is an illustrative Java snippet that can be placed in a class containing the corresponding types. The `if` chain here must use a final branch to represent the unrecognized path; the compiler does not enforce the same hierarchy-based exhaustiveness requirement as with a switch expression. Switching to `switch` makes **the intent to cover all event types** clearer.

## 4. Moving from Type Patterns to Record Patterns

To display detailed content, we not only need to know that `Authorized` exists, but also need to read `paymentId` and `Money`.

### 4.1. Type pattern capturing the whole record

```java
case Authorized authorized ->
        "approved:" + authorized.paymentId();
```

This is an illustrative `case` label inside a switch. It keeps the `authorized` object intact and calls the accessor explicitly.

### 4.2. Record pattern extracting components

```java
case Authorized(var paymentId, var total) ->
        "approved:" + paymentId;
```

`var paymentId` is inferred as `String`, and `var total` is inferred as `Money`. A record pattern matches components by **their declaration order in the record**, not by variable name.

### 4.3. Nested record pattern

```java
case Authorized(
        var paymentId,
        Money(var cents, var currencyCode)) ->
        "approved:" + paymentId + ":" + cents + " " + currencyCode;
```

The `Money(...)` pattern only matches when the `total` component of `Authorized` is a non-`null` `Money` record. This is a **narrower pattern** than `Authorized(var paymentId, var total)`.

Something to check: if `Authorized` is constructed with `total == null`, the nested `Money(...)` pattern does not match. The selector itself is still `Authorized`, not a `null` selector. Therefore, if you want to handle this case instead of missing it, you need a more general `Authorized` case after the narrower cases.

## 5. Adding `when` Guards and Ordering Cases Properly

We want to display `Authorized` with an amount of 100,000 cents or more as `large`:

```java
case Authorized(
        var paymentId, Money(var cents, var currencyCode))
        when cents >= 100_000 ->
        "approved:large:" + paymentId + ":" + cents
                + " " + currencyCode;

case Authorized(
        var paymentId, Money(var cents, var currencyCode)) ->
        "approved:" + paymentId + ":" + cents
                + " " + currencyCode;

case Authorized(var paymentId, var total) ->
        "approved:missing-total:" + paymentId;
```

These three labels are **part of a complete switch**, not a standalone file. Their order is meaningful:

1. **Narrowest pattern + guard:** `Money` is present and `cents >= 100_000`.
2. **Unguarded nested pattern:** `Money` is present but does not meet the threshold.
3. **General Authorized pattern:** covers the remaining situation, such as `total == null`.

If you place `case Authorized(var paymentId, var total)` first, it covers every non-`null` `Authorized` and the narrower `Authorized` cases after it will be rejected by the compiler due to **dominance**. If you place the unguarded `Money(...)` pattern before the guarded pattern, the guarded pattern will also be shadowed.

**A guard is not full domain validation.** In the example model, `Money` does not validate the amount or currency code. Patterns and guards only classify based on the numbers already present. In a real product, there should be constructors/factories validating amounts, currency codes, and business constraints.

### Why not just write one `Authorized` case with multiple ifs?

You could do that, but two guarded cases make the classification strategy explicit right in the `switch` structure. If the conditional logic has many steps, involves I/O, or has side effects, a general case with a pure helper function or in-body handling is often **easier to maintain** than a long guard.

## 6. Writing a Complete Switch Expression Without `default`

This is the core of the exercise:

```java
static String render(PaymentEvent event) {
    return switch (event) {
        case null -> "event:null";

        case Authorized(var paymentId, Money(var cents, var currencyCode))
                when cents >= 100_000 ->
                "approved:large:" + paymentId + ":" + cents
                        + " " + currencyCode;

        case Authorized(var paymentId, Money(var cents, var currencyCode)) ->
                "approved:" + paymentId + ":" + cents
                        + " " + currencyCode;

        case Authorized(var paymentId, var total) ->
                "approved:missing-total:" + paymentId;

        case Declined(var paymentId, var reasonCode) ->
                "declined:" + paymentId + ":" + reasonCode;

        case AnalystReview(var paymentId, var reviewQueue) ->
                "review:" + paymentId + ":" + reviewQueue;

        case FraudAlert(var paymentId, var riskScore)
                when riskScore >= 90 ->
                "fraud:critical:" + paymentId + ":" + riskScore;

        case FraudAlert(var paymentId, var riskScore) ->
                "fraud:hold:" + paymentId + ":" + riskScore;
    };
}
```

Why does the compiler accept this switch expression **without needing `default`**?

- `Authorized`: the `Authorized` cases end with a general case covering the entire type.
- `Declined`: has a case covering the entire subtype.
- `ReviewEvent` is split into `AnalystReview` and `FraudAlert`, and each has covering cases.
- `FraudAlert` has a guarded high-risk case and an unguarded remaining case.
- `case null` handles a null selector explicitly. Even though exhaustiveness for a sealed hierarchy only concerns non-null instances, this function's null policy is also explicit.

You should not replace all the trailing cases with `default -> "unknown"` just to avoid compiler errors for a missing new subtype. With an intentionally closed sealed hierarchy, **the absence of `default` is a design choice**: if a new direct subtype is added later, the compiler will require maintainers to review the behavior.

### Why distinguish `null` in two different places?

- `render(null)`: the selector is `null`, running `case null` → `"event:null"`.
- `render(new Authorized("P-102", null))`: the selector is a valid `Authorized`, but the `total` component is `null`. The `Money(...)` pattern does not match; `case Authorized(var paymentId, var total)` handles it → `"approved:missing-total:P-102"`.

You cannot use `case null` to automatically handle every null record component.

## 7. Writing a Switch Expression That Returns a Result Type, Not Just String

For a more realistic exercise, a switch expression can return a **structured domain value**:

```java
sealed interface Decision permits Screen, ReviewTicket {}

record Screen(String text) implements Decision {}

record ReviewTicket(String paymentId, int priority)
        implements Decision {}
```

Here:

- `Screen`: message to display.
- `ReviewTicket`: request to enqueue for review, with a payment ID and priority level.
- `Decision` is also a sealed type, allowing downstream code to handle the result exhaustively.

A decision-making method:

```java
static Decision decide(PaymentEvent event) {
    Objects.requireNonNull(event, "event");

    return switch (event) {
        case Authorized(var paymentId, var total) -> {
            if (total == null) {
                yield new Screen(
                        "payment-data-missing:" + paymentId);
            }
            yield new Screen("receipt:" + paymentId);
        }

        case Declined(var paymentId, var reasonCode) ->
                new Screen("retry:" + paymentId + ":" + reasonCode);

        case AnalystReview(var paymentId, var reviewQueue) ->
                new ReviewTicket(paymentId, 50);

        case FraudAlert(var paymentId, var riskScore)
                when riskScore >= 90 -> {
            int priority = Math.min(100, riskScore);
            yield new ReviewTicket(paymentId, priority);
        }

        case FraudAlert(var paymentId, var riskScore) ->
                new ReviewTicket(paymentId, 60);
    };
}
```

This is a method belonging to a class with `import java.util.Objects;` and the declared types; the full program in Section 9 contains all of these parts.

### When is `yield` used?

In `case ... -> new Screen(...)`, the expression on the right of the arrow directly provides the value of the switch expression. When a branch has **multiple statements**, use a block `{ ... }`; a `yield expression;` statement supplies the value for that branch.

```java
case FraudAlert(var paymentId, var riskScore)
        when riskScore >= 90 -> {
    int priority = Math.min(100, riskScore);
    yield new ReviewTicket(paymentId, priority);
}
```

- `yield` returns a **value from the switch expression**.
- `return` in this context returns a value from the **method**, outside or enclosing the entire expression.
- `break` is not used to "return a value" from a switch expression. Traditional `break` serves a different purpose in switch statements.
- All cases in the same switch must produce values of compatible types for result type inference (here, all records implement `Decision`).

### Two null policies in the same exercise

`render(null)` returns the string `"event:null"`. Meanwhile, `decide(null)` **intentionally throws `NullPointerException`** via `Objects.requireNonNull(event, "event")`. The difference is the **API contract**: `render` displays a missing-input state; `decide` only accepts an actual event.

Both are valid if clearly documented and tested. Do not mechanically add `case null` or `Objects.requireNonNull` without knowing the desired policy.

## 8. Chaining a Second Switch on the Sealed Result

After `decide`, the caller can render the `Decision` type:

```java
static String decisionLabel(Decision decision) {
    return switch (decision) {
        case Screen(var text) ->
                "screen:" + text;
        case ReviewTicket(var paymentId, var priority) ->
                "ticket:" + paymentId + ":priority=" + priority;
    };
}
```

The two cases correspond to the two leaf records in the sealed interface `Decision`, so the switch expression is checked for exhaustiveness by the compiler. This is a benefit of **bounded type sets on both input and output**, though do not confuse "right type" with "right business outcome": priorities 60 or 97 in the example are still rules defined by the author.

This model fits "read event → UI/action decision" scenarios:

```text
PaymentEvent (sealed)
          │
          ▼ switch expression + guard
Decision (sealed)
          │
          ▼ switch expression
UI string / data sent to downstream system
```

In a real application, if creating a `ReviewTicket` has side effects such as sending a message or writing to a database, separate the **pure decision** from **executing the side effect**, and consider transactions/outbox patterns. This demonstration only creates a result record without actually persisting a ticket.

## 9. Complete, Standalone Java 21 Program

Save the entire program as **`SealedSwitchPractice.java`**. This example uses only the JDK and does not require Maven/JUnit to run. The `check` and `expectNpe` methods provide assertions to report errors if the output or null policy is incorrect.

```java
import java.util.Objects;
import java.util.function.Supplier;

public class SealedSwitchPractice {
    sealed interface PaymentEvent
            permits Authorized, Declined, ReviewEvent {
        String paymentId();
    }

    sealed interface ReviewEvent extends PaymentEvent
            permits AnalystReview, FraudAlert {}

    record Money(long cents, String currencyCode) {}
    record Authorized(String paymentId, Money total)
            implements PaymentEvent {}
    record Declined(String paymentId, String reasonCode)
            implements PaymentEvent {}
    record AnalystReview(String paymentId, String reviewQueue)
            implements ReviewEvent {}
    record FraudAlert(String paymentId, int riskScore)
            implements ReviewEvent {}

    sealed interface Decision permits Screen, ReviewTicket {}
    record Screen(String text) implements Decision {}
    record ReviewTicket(String paymentId, int priority)
            implements Decision {}

    static String render(PaymentEvent event) {
        return switch (event) {
            case null -> "event:null";

            case Authorized(var paymentId, Money(var cents, var currencyCode))
                    when cents >= 100_000 ->
                    "approved:large:" + paymentId + ":"
                            + cents + " " + currencyCode;

            case Authorized(var paymentId, Money(var cents, var currencyCode)) ->
                    "approved:" + paymentId + ":"
                            + cents + " " + currencyCode;

            case Authorized(var paymentId, var total) ->
                    "approved:missing-total:" + paymentId;

            case Declined(var paymentId, var reasonCode) ->
                    "declined:" + paymentId + ":" + reasonCode;

            case AnalystReview(var paymentId, var reviewQueue) ->
                    "review:" + paymentId + ":" + reviewQueue;

            case FraudAlert(var paymentId, var riskScore)
                    when riskScore >= 90 ->
                    "fraud:critical:" + paymentId + ":" + riskScore;

            case FraudAlert(var paymentId, var riskScore) ->
                    "fraud:hold:" + paymentId + ":" + riskScore;
        };
    }

    static String group(PaymentEvent event) {
        return switch (event) {
            case Authorized authorized -> "completed";
            case Declined declined -> "failed";
            case ReviewEvent review -> "manual";
        };
    }

    static Decision decide(PaymentEvent event) {
        Objects.requireNonNull(event, "event");

        return switch (event) {
            case Authorized(var paymentId, var total) -> {
                if (total == null) {
                    yield new Screen("payment-data-missing:" + paymentId);
                }
                yield new Screen("receipt:" + paymentId);
            }

            case Declined(var paymentId, var reasonCode) ->
                    new Screen("retry:" + paymentId + ":" + reasonCode);

            case AnalystReview(var paymentId, var reviewQueue) ->
                    new ReviewTicket(paymentId, 50);

            case FraudAlert(var paymentId, var riskScore)
                    when riskScore >= 90 -> {
                int priority = Math.min(100, riskScore);
                yield new ReviewTicket(paymentId, priority);
            }

            case FraudAlert(var paymentId, var riskScore) ->
                    new ReviewTicket(paymentId, 60);
        };
    }

    static String decisionLabel(Decision decision) {
        return switch (decision) {
            case Screen(var text) -> "screen:" + text;
            case ReviewTicket(var paymentId, var priority) ->
                    "ticket:" + paymentId + ":priority=" + priority;
        };
    }

    static int passed = 0;

    static void check(String name, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + name + "=" + actual);
    }

    static void expectNpe(String name, Supplier<String> call) {
        try {
            call.get();
            throw new AssertionError(name
                    + " should throw NullPointerException");
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        var high = new Authorized(
                "P-100", new Money(125_000, "USD"));
        var standard = new Authorized(
                "P-101", new Money(2_500, "USD"));
        var withoutTotal = new Authorized("P-102", null);
        var declined = new Declined("P-103", "expired");
        var analyst = new AnalystReview("P-104", "risk");
        var critical = new FraudAlert("P-105", 97);
        var lowRisk = new FraudAlert("P-106", 45);

        check("null-selector", "event:null", render(null));
        check("high-amount",
                "approved:large:P-100:125000 USD", render(high));
        check("standard-amount",
                "approved:P-101:2500 USD", render(standard));
        check("missing-record",
                "approved:missing-total:P-102", render(withoutTotal));
        check("declined",
                "declined:P-103:expired", render(declined));
        check("analyst",
                "review:P-104:risk", render(analyst));
        check("critical",
                "fraud:critical:P-105:97", render(critical));
        check("hold",
                "fraud:hold:P-106:45", render(lowRisk));

        check("group-authorized", "completed", group(high));
        check("group-declined", "failed", group(declined));
        check("group-review", "manual", group(analyst));
        check("group-fraud", "manual", group(critical));
        expectNpe("group-null", () -> group(null));

        check("decision-authorized", "screen:receipt:P-100",
                decisionLabel(decide(high)));
        check("decision-missing", "screen:payment-data-missing:P-102",
                decisionLabel(decide(withoutTotal)));
        check("decision-declined", "screen:retry:P-103:expired",
                decisionLabel(decide(declined)));
        check("decision-review", "ticket:P-104:priority=50",
                decisionLabel(decide(analyst)));
        check("decision-critical", "ticket:P-105:priority=97",
                decisionLabel(decide(critical)));
        check("decision-hold", "ticket:P-106:priority=60",
                decisionLabel(decide(lowRisk)));
        expectNpe("decision-null",
                () -> decisionLabel(decide(null)));

        System.out.println("TOTAL=" + passed);
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 SealedSwitchPractice.java
java SealedSwitchPractice
```

**Exact output when all 20 assertions pass:**

```text
PASS null-selector=event:null
PASS high-amount=approved:large:P-100:125000 USD
PASS standard-amount=approved:P-101:2500 USD
PASS missing-record=approved:missing-total:P-102
PASS declined=declined:P-103:expired
PASS analyst=review:P-104:risk
PASS critical=fraud:critical:P-105:97
PASS hold=fraud:hold:P-106:45
PASS group-authorized=completed
PASS group-declined=failed
PASS group-review=manual
PASS group-fraud=manual
PASS group-null=NullPointerException
PASS decision-authorized=screen:receipt:P-100
PASS decision-missing=screen:payment-data-missing:P-102
PASS decision-declined=screen:retry:P-103:expired
PASS decision-review=ticket:P-104:priority=50
PASS decision-critical=ticket:P-105:priority=97
PASS decision-hold=ticket:P-106:priority=60
PASS decision-null=NullPointerException
TOTAL=20
```

The sample was run and verified in compiler mode `--release=21`. The program prints `TOTAL=20` only after every `check(...)` and `expectNpe(...)` succeeds. If an expected value is wrong, `AssertionError` halts the program, so you cannot just see a few `PASS` lines and assume the entire test suite succeeded.

**Runtime environment:** `--release 21` checks language/API compatibility and class file version at compile time; it does not by itself mean the JVM executing it is actually version 21. When a project deploys on Java 21, run the tests on a real Java 21 runtime in CI.

## 10. Explaining Each Group of Tests Run

### 10.1. `render`: exhaustive + null + record pattern

| Test | Representative Input | Expected | Branch to Verify |
| --- | --- | --- | --- |
| `null-selector` | `null` | `event:null` | `case null` |
| `high-amount` | `Authorized(..., Money(125000, USD))` | `approved:large:...` | Authorized + Money + `when` satisfied |
| `standard-amount` | `Authorized(..., Money(2500, USD))` | `approved:...` | Authorized + Money, guard not satisfied |
| `missing-record` | `Authorized(..., null)` | `approved:missing-total:...` | Authorized fallback |
| `declined` | `Declined` | `declined:...` | Direct subtype |
| `analyst` | `AnalystReview` | `review:...` | Indirect subtype via ReviewEvent |
| `critical` | `FraudAlert(score=97)` | `fraud:critical:...` | Guard `score >= 90` |
| `hold` | `FraudAlert(score=45)` | `fraud:hold:...` | Unguarded FraudAlert |

Even though `PaymentEvent` only directly permits three branches, the detailed switch has **four leaf records**, and thanks to guarded/fallback cases it has more labels than subtypes.

This is completely normal: a subtype can have **multiple cases** as long as no case is dominated and the entire pattern set covers all possible values.

### 10.2. `group`: generalizing an intermediate branch

`group(analyst)` and `group(critical)` both return `manual`. They demonstrate that a single case of type `ReviewEvent` covers the subtypes of that branch. `group(null)` **throws `NullPointerException`** because there is no `case null`.

### 10.3. `decide`: returning a typed result, using `yield`

- Authorized with `Money` → `Screen("receipt:P-100")`.
- Authorized with `total == null` → `Screen("payment-data-missing:P-102")`.
- Declined → `Screen("retry:P-103:expired")`.
- AnalystReview → `ReviewTicket("P-104", 50)`.
- FraudAlert score 97 → `ReviewTicket("P-105", 97)`, created inside a block with `yield`.
- FraudAlert score 45 → `ReviewTicket("P-106", 60)`.
- `decide(null)` → NPE at `Objects.requireNonNull` before the switch is evaluated.

The `decisionLabel` function continues using a switch expression on the sealed type `Decision`, distinguishing display screens from tickets in a typed manner.

**Business boundaries:** `riskScore` and priority levels are illustrative rules. The score is not validated to be within `[0,100]` in the record; production code must define and enforce boundaries, and not infer that every `FraudAlert` carries a valid score just because the record declares `int`.

## 11. Compile-Error Test: Missing Exhaustive Branch

To understand why a sealed hierarchy is useful, **intentionally** write a switch expression that omits a subtype.

Java 21 example that **intentionally does not compile**:

```java
sealed interface Pay permits AcceptedPayment, ReviewPayment {}

record AcceptedPayment() implements Pay {}

sealed interface ReviewPayment extends Pay
        permits NeedsAnalyst, NeedsFraud {}

record NeedsAnalyst() implements ReviewPayment {}
record NeedsFraud() implements ReviewPayment {}

class MissingCase {
    static String check(Pay x) {
        return switch (x) {
            case AcceptedPayment p -> "ok";
            case NeedsAnalyst p -> "analyst";
        };
    }
}
```

Because `NeedsFraud` is still a valid subtype of `Pay` via `ReviewPayment`, the switch is not exhaustive. The Java 21 compiler reports a diagnostic similar to:

```text
the switch expression does not cover all possible input values
```

**Purpose of the experiment:** to see that the compiler does not ignore indirect subtypes. If a sealed node opens another sealed branch, the compiler can still check coverage across that branch.

There are two valid fixes depending on requirements:
- Add `case NeedsFraud p -> "fraud";` to handle it separately.
- Or replace the specific review type cases with `case ReviewPayment p -> "review";` if all reviews can share the same behavior.

You should not add `default -> "other"` just to ignore an undecided subtype that the domain already explicitly defines. `default` can be useful for open APIs or inputs that genuinely need a fallback, but with a closed sealed hierarchy, it weakens the review signal when a new type appears.

## 12. Compile-Error Test: Dominated Case

Pattern switches also have rules for **dominance**. The following example **intentionally does not compile** on Java 21:

```java
sealed interface Pay permits AcceptedPayment, ReviewPayment {}

record AcceptedPayment() implements Pay {}

sealed interface ReviewPayment extends Pay
        permits NeedsAnalyst, NeedsFraud {}

record NeedsAnalyst() implements ReviewPayment {}
record NeedsFraud() implements ReviewPayment {}

class DominatedCase {
    static String check(Pay x) {
        return switch (x) {
            case AcceptedPayment p -> "ok";
            case ReviewPayment p -> "all-reviews";
            case NeedsFraud p -> "fraud";
        };
    }
}
```

The preceding `case ReviewPayment p` already matches every `NeedsFraud`. Therefore, the subsequent `case NeedsFraud p` is **unreachable by pattern relationship** and the compiler reports something like:

```text
this case label is dominated by a preceding case label
```

**Fix according to business goal:**

```java
return switch (x) {
    case AcceptedPayment p -> "ok";
    case NeedsFraud p -> "fraud";
    case ReviewPayment p -> "other-review";
};
```

This is an illustrative snippet inside a method taking `Pay x`. The **specific** pattern comes before the **broad** pattern. When `ReviewPayment` is sealed with exactly `NeedsAnalyst` and `NeedsFraud`, the broad case covers the remaining review values.

Remember that dominance is a **compile-time** error: there is no runtime stdout to test for a snippet that cannot compile. Use a minimal example and read the compiler message, rather than running the whole system and guessing.

## 13. How Does a Switch Expression Differ from a Switch Statement?

### 13.1. A switch expression produces a value

```java
String message = switch (event) {
    case Authorized approved -> "approved";
    case Declined declined -> "declined";
    case ReviewEvent review -> "review";
};
```

This is an illustrative snippet using a `PaymentEvent event` variable and the model's types, which must be placed in a valid scope. All branches provide a result, and the switch expression must be exhaustive.

### 13.2. A switch statement executes statements

```java
switch (event) {
    case Authorized approved -> System.out.println("approved");
    case Declined declined -> System.out.println("declined");
    case ReviewEvent review -> System.out.println("review");
}
```

This is a switch **statement** with arrow cases. It is suitable when the goal is actions and side effects rather than producing a value. Enhanced switch statements using patterns in Java 21 must also satisfy Java's exhaustiveness requirements, unlike the simplistic assumption that "a statement missing a case is always valid."

### 13.3. How `yield` differs from `return` and `break`

| Keyword/Syntax | Primary Role | In This Exercise |
| --- | --- | --- |
| `case Type t -> expression` | Produces a branch value without a block | `case Declined(...) -> new Screen(...)` |
| `yield expression;` | Returns the value of the **switch expression** from a block | Creating `ReviewTicket` after computing `priority` |
| `return expression;` | Returns from the **method** | `return switch (event) { ... };` |
| `break;` | Control flow in switch statements/loops, not used as the return value of a switch expression | Does not replace `yield` |

A common mistake when migrating from an old switch statement to an expression is keeping `break` as a way to "exit the case" and expecting the switch to return a value. With an expression, you need an expression or `yield` on all normal completion paths of a block.

## 14. Null Policy, Record Components, and Guards: Three Distinct Things to Test

**Null selector:** `switch (event)` receives `event == null`. If `case null` is present as in `render`, that case is selected. Otherwise, as in `group`, switching on a null reference normally throws `NullPointerException`. `default` is not automatically a null handler.

**Null record component:** `new Authorized("P-102", null)` is an `Authorized` object, so it does not trigger `case null`. The `Money(...)` pattern does not match a null component; `case Authorized(var paymentId, var total)` still matches and `total` receives `null`. This is why the `missing-record` test case is important.

**False guard:** `FraudAlert("P-106", 45)` is still of type `FraudAlert`; the record pattern matches, but `when riskScore >= 90` is false. Java moves on to the unguarded `FraudAlert` case. Do not confuse a false guard with a null selector or a wrong subtype.

### When a guard itself throws an exception

If a guard calls an unsafe method on a potentially null component, an exception thrown while evaluating `when` propagates according to expression rules, rather than resulting in a false match. Use the short-circuit `&&` operator and order conditions properly:

```java
case Authorized(var id, Money(var cents, var currencyCode))
        when currencyCode != null && !currencyCode.isBlank() ->
        "valid-currency:" + id;
```

This is an illustrative `case` label. It only checks for a non-blank string; in production, checking whether a currency code is supported is a separate domain concern.

### When a record accessor throws an error

Record patterns retrieve components via accessors; a custom accessor can throw an exception. In Java 21, an error from an accessor during pattern matching is wrapped in `MatchException` with `getCause()` containing the original error. This is different from "no match due to a null component." Keeping records simple, validating data upon construction, and separating I/O from accessors makes switch behavior predictable.

## 15. Which Paths Should a Regression Test Suite Cover?

The complete program contains 20 assertions divided into three groups. When extending the exercise in a real system, you can use this matrix:

| Test Type | How to Construct Data | Expected Assertion |
| --- | --- | --- |
| A direct subtype | `Declined("P-103","expired")` | `render` returns the exact string |
| An indirect subtype | `AnalystReview("P-104","risk")` | `group` returns `manual` |
| Another indirect subtype | `FraudAlert("P-105",97)` | `render` and `group` are correct |
| Guard true | 100,000 cents or more | Large branch is selected |
| Guard false | Below 100,000 cents | Standard branch is selected |
| Guard boundary | 99,999 and 100,000 cents | Distinguishes before/at threshold accurately |
| Nested record present | `Authorized(..., Money(...))` | Components are deconstructed properly |
| Nested record null | `Authorized(..., null)` | Fallback branch, not confused with null selector |
| Null selector with case | `render(null)` | `event:null` |
| Null selector without case | `group(null)` | `NullPointerException` |
| Switch expression returning record | `decide(critical)` | `ReviewTicket` has expected priority |
| Block with `yield` | `FraudAlert(score=97)` | Priority 97, does not fall into fallback |
| Type-specific fallback | `FraudAlert(score=45)` | Priority 60 |
| Compiler completeness | Deliberately remove a subtype case | Missing exhaustiveness error |
| Compiler dominance | Place `ReviewEvent` case before `FraudAlert` | Dominated case error |
| API evolution | Add a new direct permitted subtype | Recompile and review all exhaustive switches |

The last two items are **compile tests**, not runtime tests; they can be verified with a small source snippet that intentionally fails to compile. Do not record them as "runtime unit test PASS" simply because `javac` fails as expected.

### Note on boundary testing

In the complete program, the high case uses 125,000 and the standard case uses 2,500, so both guard paths are tested. When moving to production, add **99,999 and 100,000** to catch bugs where `>=` is replaced with `>` or the threshold is changed. Using boundary data makes tests more meaningful than simply adding more values far from the threshold.

## 16. Using JUnit 5 for Isolated Tests

If the project has JUnit 5, replace the `check` helper with `assertEquals` and `assertThrows`. The example below is an **illustrative test class** that requires JUnit 5 on the test classpath and resides in the same package as `SealedSwitchPractice` (the example's nested types/methods have package-private visibility):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SealedSwitchJUnitTest {
    @Test
    void sealedSwitchCoversReviewSubtypes() {
        var analyst =
                new SealedSwitchPractice.AnalystReview("P-1", "risk");
        var fraud = new SealedSwitchPractice.FraudAlert("P-2", 97);

        assertAll(
                () -> assertEquals("manual",
                        SealedSwitchPractice.group(analyst)),
                () -> assertEquals("manual",
                        SealedSwitchPractice.group(fraud)),
                () -> assertEquals("fraud:critical:P-2:97",
                        SealedSwitchPractice.render(fraud))
        );
    }

    @Test
    void nestedRecordNullAndNullSelectorAreDifferent() {
        var missing =
                new SealedSwitchPractice.Authorized("P-3", null);

        assertAll(
                () -> assertEquals("approved:missing-total:P-3",
                        SealedSwitchPractice.render(missing)),
                () -> assertEquals("event:null",
                        SealedSwitchPractice.render(null))
        );
    }

    @Test
    void guardBoundaryIsInclusive() {
        var below = new SealedSwitchPractice.Authorized(
                "P-4", new SealedSwitchPractice.Money(99_999, "USD"));
        var at = new SealedSwitchPractice.Authorized(
                "P-5", new SealedSwitchPractice.Money(100_000, "USD"));

        assertAll(
                () -> assertEquals("approved:P-4:99999 USD",
                        SealedSwitchPractice.render(below)),
                () -> assertEquals("approved:large:P-5:100000 USD",
                        SealedSwitchPractice.render(at))
        );
    }

    @Test
    void groupWithoutNullCaseRejectsNull() {
        assertThrows(NullPointerException.class,
                () -> SealedSwitchPractice.group(null));
    }

    @Test
    void decisionCanBeComparedStructurally() {
        var fraud = new SealedSwitchPractice.FraudAlert("P-6", 95);
        assertEquals(
                new SealedSwitchPractice.ReviewTicket("P-6", 95),
                SealedSwitchPractice.decide(fraud));
    }
}
```

This test class can only be run when JUnit is configured in the project. Otherwise, `SealedSwitchPractice.java` in Section 9 is a standalone example using only the Java standard library.

**Key takeaway:** using `assertEquals` directly on `ReviewTicket` records is appropriate because records generate component-based `equals`. There is no need to convert a record to a string just to verify that two values have the same contents.

## 17. When Adding a New Subtype, Do Not Use `default` to Hide Design Gaps

A sealed hierarchy can be extended by modifying the `permits` clause itself. Suppose we need to add a `Chargeback` type directly under `PaymentEvent`.

Example illustrating the declaration change (must not be combined verbatim with the old `permits` without updating the definition):

```java
sealed interface PaymentEvent
        permits Authorized, Declined, ReviewEvent, Chargeback {
    String paymentId();
}

record Chargeback(String paymentId, String disputeId)
        implements PaymentEvent {}
```

When recompiling `render` or `decide` without a `Chargeback` case, the compiler will report missing exhaustiveness. That is **the exact goal of a closed type set**: requiring maintainers to define display and action logic for chargebacks rather than silently routing them into an `"unknown"` branch.

With **separate compilation** (a client built against an older version of the hierarchy loads a newer library at runtime), a switch compiled as exhaustive against the old set can throw `MatchException` when receiving an unknown subtype. This is a compatibility risk that must be tested; do not assume all old clients will run properly just because the new class implements the same root.

If a branch is opened with `non-sealed`, subtypes can be added externally without modifying the sealed root's `permits`. This is useful for plugins, but you must then design a corresponding general case, and **cannot assume the concrete subtype set is closed**.

### Not every exhaustive switch needs deep record patterns

If only grouping, `case ReviewEvent review` is preferable to two separate cases for `AnalystReview` and `FraudAlert`. If you need the exact components, `case FraudAlert(var id, var score)` provides the data at the case level. If dispatching to another handler/service, `case FraudAlert alert -> fraudHandler.handle(alert)` preserves the object and is sometimes easier to maintain.

The level of deconstruction should be driven by **processing needs**, not by the fact that record pattern syntax allows extracting all fields.

## 18. Common Mistakes When Doing the Exercise

### 18.1. Handling only the two direct records and forgetting the intermediate sealed subtype

`PaymentEvent` does not only have `Authorized` and `Declined`; it also has `ReviewEvent`. If a switch omits a case for `ReviewEvent` or all of its children, the compiler will report non-exhaustiveness.

### 18.2. Listing only one subtype of ReviewEvent

`AnalystReview` does not cover `FraudAlert`. You need a `FraudAlert` case or a `ReviewEvent` case that covers the business logic appropriately.

### 18.3. Using `default` to make code compile quickly

With a closed hierarchy, this can hide newly added subtypes. If a fallback is genuinely needed, document why clearly and test behavior with new subtypes.

### 18.4. Placing a broad case before a narrow case

`case ReviewEvent review` before `case FraudAlert alert` makes the later case dominated; similarly, `case Authorized(var id, var money)` before `Authorized(..., Money(...))`.

### 18.5. Forgetting the branch when the guard is false

`case FraudAlert(var id, var score) when score >= 90` does not cover a `FraudAlert` with a lower score; there must be another case for the remaining group unless a valid general path exists.

### 18.6. Using `case null` to handle null inside a record

`case null` only matches a null selector. A `total == null` component is handled by a record pattern and fallback on `Authorized`.

### 18.7. Assuming `record` automatically validates data

`Money(-1, null)` can still be created in the example because the record declares no validation. The parameter name `cents` and the sealed hierarchy do not automatically guarantee valid values.

### 18.8. Confusing the meaning of `yield`

`yield` inside a case block returns the value of the switch expression, not returning from the entire method like `return`.

### 18.9. Thinking a passing compile means correct behavior

The compiler ensures valid pattern types and type-based exhaustiveness; it does not verify that the 100,000 threshold, decline reason, or priority 60 are business-correct. Regression tests are required.

### 18.10. Testing only one subtype and skipping boundary data

Having a single test for `Authorized` is not enough. You must check guard true/false, null nested records, indirect subtypes, null selectors, and result branches.

### 18.11. Writing Java 21 code and compiling under `--release 17`

Sealed classes and record classes were already in Java 17, but record patterns and pattern matching for switch in this article's syntax were finalized in Java 21. Use a JDK supporting `--release 21`, and do not abuse historical preview flags.

### 18.12. Using pattern matching to replace authorization checks or I/O

A switch expression is only a branching mechanism by type/condition. Caller authentication, transaction persistence, writing review tickets, retries, and security must be designed at the appropriate layers. Returning a `Decision` record does not by itself prove that side effects have occurred.

## 19. Self-Practice Exercises (with Answers)

**Exercise 1 — Identifying direct subtypes.** How many direct permitted subtypes does `PaymentEvent permits Authorized, Declined, ReviewEvent` have? Is `FraudAlert` a direct subtype?

**Answer:** Three. `FraudAlert` is an indirect subtype via `ReviewEvent`.

**Exercise 2 — Exhaustiveness via an intermediate branch.** Can you write `case Authorized`, `case Declined`, `case ReviewEvent` without listing `FraudAlert`/`AnalystReview`?

**Answer:** Yes, if you want to handle the entire review group in the same branch. `case ReviewEvent` covers both of its child records.

**Exercise 3 — False guard.** Does `FraudAlert("P", 45)` enter `when riskScore >= 90`? What happens next?

**Answer:** No; the subsequent unguarded `FraudAlert` case is selected and returns `fraud:hold:P:45` in `render`.

**Exercise 4 — Boundary value.** With `cents == 100_000`, does `Authorized`'s string contain `large`? Why?

**Answer:** Yes, because the guard uses the `>=` operator rather than `>`.

**Exercise 5 — Null nested record.** Does `render(new Authorized("P", null))` execute `case null`?

**Answer:** No. The selector is a non-null `Authorized`. The nested `Money` pattern does not match, and the general `Authorized` case returns `approved:missing-total:P`.

**Exercise 6 — Null policy.** Why do `render(null)` and `group(null)` behave differently?

**Answer:** `render` has `case null` so it returns `event:null`; `group` does not, so switching on null throws `NullPointerException`.

**Exercise 7 — Missing case.** If you remove the unguarded `FraudAlert` branch and keep only `FraudAlert` with `score >= 90`, is the switch still exhaustive?

**Answer:** No, because a `FraudAlert` with a lower score can still occur. An unguarded branch or another covering pattern must be added.

**Exercise 8 — Dominance.** Is placing `case ReviewEvent review` before `case AnalystReview analyst` in the same switch valid?

**Answer:** No; `AnalystReview` is already matched by the broader `ReviewEvent` pattern first, so the specific case after it is dominated.

**Exercise 9 — `yield`.** Why does the critical `FraudAlert` case in `decide` use `yield` instead of `break`?

**Answer:** It is a block in a switch expression that needs to produce a value of type `Decision`. `yield new ReviewTicket(...)` supplies the value, whereas `break` does not supply a switch expression value.

**Exercise 10 — Typed result.** Why is `ReviewTicket("P", 95)` a good value to use with `assertEquals`?

**Answer:** It is a record, which has component-based `equals`, so it can be compared structurally without converting it to a `String`.

**Exercise 11 — API evolution.** If you add a direct subtype `Chargeback` to `PaymentEvent`, do existing switches need updating?

**Answer:** Exhaustive switches without a new case or valid fallback will fail on recompile. You must define the semantics for `Chargeback`, update tests/docs, and consider older binary clients.

**Exercise 12 — Choosing pattern granularity.** If a method only needs to know whether an event is in the review group, should you write `case ReviewEvent review` or the two child record patterns?

**Answer:** `case ReviewEvent` is sufficient and usually clearer. Only deconstruct child records if you actually need subtype-specific data.

**Exercise 13 — Validation.** Is `new Money(-100, null)` rejected by the compiler for invalid values?

**Answer:** No. The `long`/`String` types are syntactically valid; constructor/factory validation is required if the domain demands a non-negative amount and a valid `currencyCode`.

**Exercise 14 — Improvement.** Write two more assertions for `render` with `Money(99_999, "USD")` and `Money(100_000, "USD")`. What should they return?

**Answer:** With payment IDs `P-4` and `P-5` respectively: `approved:P-4:99999 USD` and `approved:large:P-5:100000 USD`. These assertions protect the boundary if someone accidentally changes `>=` to `>`.

## 20. Practice Completion Checklist

- [ ] Clearly identify the sealed root and **all direct permitted subtypes**.
- [ ] If there are intermediate sealed subtypes, consider their children or use a broad case for the whole branch.
- [ ] Keep data records separate from the hierarchy if they do not represent a variant of the sealed root.
- [ ] Every `switch expression` has a clear result type and every valid execution path provides a value.
- [ ] Narrow and guarded patterns must precede broad unguarded patterns to avoid dominance.
- [ ] If using nested record patterns, include a path to handle a null nested record if the domain allows it.
- [ ] The null selector policy is explicitly defined: `case null` or NPE per contract.
- [ ] For multi-statement blocks, use `yield` to produce a value from the switch expression.
- [ ] Do not add `default` merely to patch an unresolved domain exhaustiveness gap.
- [ ] Test at least every subtype, guard true/false, boundaries, null, and results.
- [ ] Distinguish runnable code from examples that intentionally produce compile errors.
- [ ] Compile with `javac --release 21` and test on the target runtime.
- [ ] If the hierarchy changes, update handlers, tests, documentation, and check compatibility.

**Conclusion:** Writing a switch expression on a sealed type is an exercise in **type-domain design + choosing pattern granularity + null/guard contracts + exhaustiveness verification**. The greatest value is not saving a few lines of `if`, but letting the compiler and regression tests help maintainers spot when a new variant lacks handling.

**Official References:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification 21 — Patterns (`14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
