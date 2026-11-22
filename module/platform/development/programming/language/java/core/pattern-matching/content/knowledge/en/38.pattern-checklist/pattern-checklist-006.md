# Record Pattern Checklist in Java 21+: Checking Syntax, Types, Nulls, and Behavior

## 1. When to use this checklist?

A **record pattern** is syntax for checking the structure of a Java `record` and extracting its components. Unlike merely determining "is this object a `Receipt`?", a record pattern also lets you retrieve the inner data right at the match site:

```java
// Illustrative snippet placed in a method with Object input.
if (input instanceof Receipt(var number, Amount(var cents, var currency))) {
    System.out.println(number + ":" + cents + ":" + currency);
}
```

The snippet above requires an actual `Receipt` whose `amount` component is a non-`null` `Amount`, and then binds the components `number`, `cents`, and `currency`. **A successful match does not prove the data is valid according to business rules:** `number` or `currency` can still be `null` because `var` variables can hold `null` if the corresponding component is a reference type.

This lesson belongs to the **Pattern Checklist** group. The goal is to have a review procedure you can use **before writing, during compilation, during testing, and before merging** an `instanceof` or `switch` statement containing record patterns. The checklist focuses on easily overlooked mistakes: wrong component order/arity, type inference, null levels, guards, case ordering, exhaustiveness, generic erasure, invariants, and testing.

**Versions:** record declarations have been standard since Java 16 (JEP 395); record patterns have been standard since **Java 21** (JEP 440); pattern matching for `switch` has also been standard since Java 21 (JEP 441). **JDK 21 or later** is required to run the complete program in this lesson, without needing `--enable-preview`. `instanceof` type patterns have existed since Java 16, but `Receipt(var number, ...)` is a **record pattern** and is not final syntax in Java 16/17.

## 2. Quick checklist: 24 questions before accepting a record pattern

You can check off each box after verifying it via source code, the compiler, or tests.

### A. Record types and structure

- [ ] **A1.** The expression to match is an actual **record type**, not a regular class mistaken for a deconstructible record.
- [ ] **A2.** Each `RecordType(...)` has the **exact number of subpatterns** matching the number of record components.
- [ ] **A3.** The order of subpatterns matches the **declaration order of components**, rather than being inferred from variable names.
- [ ] **A4.** The type of each subpattern is compatible with the component type; `var` has its static type accurately inferred by the compiler.
- [ ] **A5.** Nest only as deep as actually needed; avoid deep coupling to the schema when only a value object or a named accessor is needed.

### B. Nulls and value checks

- [ ] **B1.** Policy is defined for when the **root selector is `null`**: `instanceof` does not match; `switch` handles `null` appropriately.
- [ ] **B2.** The case where a **nested record is `null`** has been checked: a nested record pattern at that level does not match.
- [ ] **B3.** The case where a **reference component is `null`** but bound with `var` has been checked: the record pattern can still match.
- [ ] **B4.** Business data (IDs, amounts, units, value ranges) has explicit validators/guards; "match" is not treated as "valid".
- [ ] **B5.** Guards call methods on reference components **after checking for null** and do not unintentionally alter the branch policy.

### C. Flow, switch, and generics

- [ ] **C1.** Pattern variables are only used in locations valid under **flow scoping**; not used after a branch that might not match.
- [ ] **C2.** In `instanceof`, subsequent conditions are placed on the right-hand side of `&&` when the matched variables are needed; `||` is not used carelessly.
- [ ] **C3.** In `switch`, **specific/guarded cases come before general cases**, avoiding dominance errors.
- [ ] **C4.** If the selector is a sealed hierarchy, the `switch expression` handles all variants; `default` is not added just to mask missing-case errors.
- [ ] **C5.** Guards on Java 21 pattern cases use **`when`**, unlike `&&` in Boolean expressions with `instanceof`.
- [ ] **C6.** Generic record patterns are used in the right static type context; `instanceof Packet<Receipt>` is not used on `Object` as if generic arguments could be checked at runtime.

### D. Testing and maintainability

- [ ] **D1.** There is a valid case for every pattern/case that needs to be handled.
- [ ] **D2.** There are `null` cases for the selector, each important nested record, and nullable components.
- [ ] **D3.** There is a case where the guard fails while the record structure still matches, to distinguish a **structural non-match** from an **invalid value**.
- [ ] **D4.** There are negative cases for wrong arity, dominated cases, non-exhaustive switches, or invalid generic runtime checks.
- [ ] **D5.** Examples have expected outputs and assertions; values are not just printed and assumed to be correct.
- [ ] **D6.** Coupling to component count/order when the record schema changes has been reviewed; for components of the same type, swapped names can still compile.
- [ ] **D7.** The place to enforce invariants is identified: constructor/factory/boundary validation, rather than inconsistently repeating guards everywhere.
- [ ] **D8.** If a nested pattern is hard to debug or has many cases, splitting into steps/named helpers with equivalent tests has been considered.

The checklist above consists of **deliberate review criteria**, not a list of conditions that the Java compiler checks automatically in full. The compiler handles A2–A4 and many C1/C3/C4 errors very well; items concerning domain logic, null policy, tests, and readability remain the developer's responsibility.

## 3. Practice model for using the checklist

To clearly see the difference between **structural matching** and **validation**, the example intentionally uses records that can produce invalid data:

```java
sealed interface Event permits Paid, Rejected, Pending {}

record Amount(long cents, String currency) {}
record Receipt(String number, Amount amount) {}

record Paid(String orderId, Receipt receipt) implements Event {}
record Rejected(String orderId, String reason) implements Event {}
record Pending(String orderId) implements Event {}

record Packet<T>(T data) {}
```

This is an **illustrative declaration snippet**, not a standalone file. The complete program is in section 9.

In this model:

- `Paid` has an order ID and a `Receipt`.
- `Receipt` has a reference number and an `Amount`.
- `Amount` has an amount in the smallest currency unit (`cents`) and a currency code as a string.
- `Rejected` has a rejection reason.
- `Pending` only has an order ID.
- `Packet<T>` helps test record patterns in a **generic** context.

**No compact constructors in the learning example**: `new Receipt("R-1", null)`, `new Rejected("O-2", " ")`, and `new Amount(0, "USD")` are all created to test guard/fallback branches. In a production domain model, invalid states should usually be prevented early at the constructor/factory or data-transfer boundary. Do not copy this model—which intentionally permits invalid states—directly into a real payment system.

## 4. A1–A5: checking structure, component count, and types

### 4.1. Record patterns rely on the record declaration, not variable names

`Receipt` declares:

```java
record Receipt(String number, Amount amount) {}
```

Valid pattern:

```java
// Valid: two subpatterns corresponding to number and amount.
if (input instanceof Receipt(var number, var amount)) {
    // number has type String, amount has type Amount.
}
```

And a nested pattern:

```java
if (input instanceof Receipt(var number,
        Amount(var cents, var currency))) {
    // cents has type long, currency has type String.
}
```

**Checklist A2:** `Receipt` has **two** components, and `Amount` has **two** components. Therefore, `Receipt(var number)` or `Amount(var cents)` is missing a subpattern and is rejected by the compiler.

**Checklist A3:** Java matches components **positionally**. Writing `Receipt(var amount, var number)` can still compile because `var` accepts the inferred type for each position, but the variable named `amount` will actually receive `String number` and the variable named `number` will receive `Amount amount`. This is a readability/naming bug that the compiler might **not** catch. Name variables to accurately reflect the component at that position.

**Checklist A4:** with `Amount(var cents, var currency)`, `cents` has type `long`, and `currency` has type `String`. Do not assume `var` is a dynamic variable on which any method can be called. `cents.toUpperCase()` is a compile error because primitive `long` has no methods.

### 4.2. Do you really need deep nesting?

If you only need `Receipt.number`, consider:

```java
// In a context where Paid paid already has a known type.
String number = paid.receipt() == null
        ? null : paid.receipt().number();
```

Or a pattern that only nests down to `Receipt`:

```java
if (input instanceof Paid(var id, Receipt(var number, var amount))) {
    System.out.println(number);
}
```

There is no need to further nest `Amount(var cents, var currency)` if the currency data is not used. Each added record pattern both provides data, requires the nested record at that position to be **non-null**, and increases coupling to the schema's component count. Nesting depth should be decided by the **goal of the branch**, not by a desire to use the syntax to its maximum.

## 5. B1–B5: level-by-level null check table

Compare four inputs:

```java
Paid full = new Paid("O-1",
        new Receipt("R-1", new Amount(450, "USD")));

Paid emptyAmount = new Paid("O-4",
        new Receipt("R-4", null));

Paid emptyReceipt = new Paid("O-5", null);

Paid nullableCurrency = new Paid("O-6",
        new Receipt("R-6", new Amount(450, null)));
```

And the pattern:

```java
Paid(var id, Receipt(var no, Amount(var cents, var currency)))
```

| Input | Does the deep pattern match? | Explanation |
| --- | --- | --- |
| `full` | Yes | `Paid`, `Receipt`, and `Amount` are all non-null and of the right types |
| `emptyAmount` | No | The nested record pattern `Amount(...)` requires an `Amount` object; it cannot match null |
| `emptyReceipt` | No | The nested record pattern `Receipt(...)` requires a `Receipt` object; it cannot match null |
| `nullableCurrency` | **Yes** | `Amount` exists; `var currency` can receive null |
| `null` selector in `instanceof` | No | `null instanceof Pattern` returns `false` |
| `null` selector in `switch` with `case null` | Enters `case null` | The null-handling policy is explicitly declared |

**Most common mistake:** `Record(var component)` does not automatically reject a null component; only a nested record pattern `NestedRecord(...)` requires a non-null nested record to match. Test both cases separately to avoid missing-data handling bugs.

With a **guard**:

```java
case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
        when cents > 0 && currency != null
                && currency.matches("[A-Z]{3}") -> ...
```

This is a **single case in a Java 21 switch**, not a standalone Java file. The check `currency != null` comes before `currency.matches(...)` to avoid calling a method on null. `cents > 0` is a rule of this example; it does not apply to all monetary amounts in every business domain (for instance, refunds and adjustments may use a different model).

The regex `[A-Z]{3}` only checks a three-uppercase-letter format; **it does not verify that it is an existing ISO 4217 code**. If the domain requires real currency codes, separate catalog validation is needed.

## 6. C1–C5: distinguishing `instanceof`, `switch`, `when`, and case ordering

### 6.1. Flow scoping with instanceof

```java
if (value instanceof Paid(var id,
        Receipt(var no, Amount(var cents, var currency)))
        && id != null && !id.isBlank() && cents > 0) {
    System.out.println(id + ":" + cents);
}
```

The variables `id`, `no`, `cents`, and `currency` are only valid in locations where the compiler knows the record pattern has matched. Short-circuiting `&&` ensures the guard is evaluated **after** the pattern matches. Do not use `id` after the `if` block if the compiler cannot prove the pattern succeeded on every path.

Do not confuse the syntax:

- In `instanceof`: `value instanceof Paid(...) && validCondition` — `&&` is a **Boolean operator outside the pattern**.
- In a Java 21 `switch` case: `case Paid(...) when validCondition -> ...` — `when` is a **guard on the case label**.

Older syntax like `case String s && ... ->` appeared in previews in earlier JDKs; **it is not final Java 21 syntax**.

### 6.2. Case ordering from specific to general

Consider a `switch` on `Event`:

```java
return switch (event) {
    case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
            when cents > 0 && currency != null
                    && currency.matches("[A-Z]{3}") ->
            "paid:" + id + ":" + no + ":" + cents + ":" + currency;

    case Paid(var id, Receipt(var no, var amount)) ->
            "paid:invalid-amount";

    case Paid(var id, var receipt) ->
            "paid:missing-receipt";

    case Rejected(var id, var reason)
            when reason != null && !reason.isBlank() ->
            "rejected:" + id + ":" + reason;

    case Rejected(var id, var reason) ->
            "rejected:invalid-reason";

    case Pending(var id) -> "pending:" + id;
    case null -> "missing";
};
```

The snippet above is inside the `String summarize(Event event)` method of the program in section 9.

The three cases for `Paid` classify intentionally:

1. `Paid` with both `Receipt` and `Amount`, **satisfying the guard**: returns the payment details.
2. `Paid` with `Receipt` but **failing the previous case**: returns `paid:invalid-amount`. In the demo, this covers a null `Amount` or an amount/currency code that fails the guard.
3. Remaining `Paid`: since `Receipt(...)` in the two cases above did not match, the remaining case in this model is `receipt == null`, returning `paid:missing-receipt`.

**Dominance:** if you put `case Paid(var id, var receipt)` first, it covers every `Paid`, so the more specific cases below may be rejected by the compiler as dominated. Therefore, checklist C3 requires reviewing the **ordering of all pattern labels**, not just a single case in isolation.

**Do not equate a fallback with full validation:** the `paid:invalid-amount` case groups multiple causes together. If an API needs to return detailed errors (zero, currency format, null amount), you need more specific validation or a different result type. On the other hand, there is no need to create a separate case for every condition if the business logic only needs to know "unusable".

### 6.3. Exhaustiveness of a sealed hierarchy

`Event` is a sealed interface with three final record subtypes: `Paid`, `Rejected`, and `Pending`. The cases of `summarize` handle all three variants plus `case null`; this is an exhaustive **switch expression** without needing `default`.

If a new subtype `Canceled` is added to `permits`, the compiler can require updating `switch` expressions that do not yet cover that subtype. That is the benefit of an intentionally closed hierarchy.

A `default -> "other"` added just to make compilation easy can hide the need to update logic when the model changes. However, for intentionally extensible APIs or when a genuine fallback is needed, `default` can be appropriate; review the policy explicitly.

`case null` handles a **null selector**, not all null components inside the records.

## 7. C6: checklist for generic record patterns

Generic record:

```java
record Packet<T>(T data) {}
```

When the method parameter is `Packet<Receipt> packet`, the compiler has static type information to infer a record pattern:

```java
// In a method receiving Packet<Receipt> packet.
return switch (packet) {
    case Packet(Receipt(var no, Amount(var cents, var currency))) ->
            "packet:" + no + ":" + cents;
    case Packet(var receipt) -> "packet:unavailable";
    case null -> "packet:missing";
};
```

This example will appear in the runnable program in section 9. The deep case requires `Packet`, `Receipt`, and `Amount` to exist, while the `Packet(var receipt)` case can match even when the `data` component is `null`. The two cases must be in the right order.

**What the compiler infers does not mean the JVM verifies all generic type arguments at runtime.** From an `Object input` variable, you cannot validate the `Packet<Receipt>` type using `input instanceof Packet<Receipt> p` as if the generic argument `Receipt` were fully preserved at runtime.

If receiving untrusted data via `Object`, you can use:

```java
// Illustrative snippet in a method with Object input.
if (input instanceof Packet<?> packet) {
    Object data = packet.data();
    if (data instanceof Receipt(var no, var amount)) {
        System.out.println(no);
    }
}
```

`Packet<?>` checks the raw record type with an unknown type argument; `Receipt(...)` checks the component separately. If there is a deeper collection of elements such as `List<Receipt>`, you must also account for **erasure and validate each element**, rather than safely inferring from an external type tag.

## 8. Designing a test matrix from the checklist

Before writing the complete source, define inputs and expected outputs:

| Case | Input | Expected result | Checklist |
| --- | --- | --- | --- |
| Valid payment | `Paid("O-1", Receipt("R-1", Amount(450,"USD")))` | `paid:O-1:R-1:450:USD` | A/B/C/D |
| Zero amount | `Paid(...Amount(0,"USD"))` | `paid:invalid-amount` | B4, D3 |
| Missing Amount | `Paid(...Receipt("R-4", null))` | `paid:invalid-amount` | B2, D2 |
| Missing Receipt | `Paid("O-5", null)` | `paid:missing-receipt` | B2, D2 |
| Valid Rejected | `Rejected("O-2","out-of-stock")` | `rejected:O-2:out-of-stock` | C3, D1 |
| Blank reason | `Rejected("O-2"," ")` | `rejected:invalid-reason` | B4, D3 |
| Pending | `Pending("O-3")` | `pending:O-3` | C4, D1 |
| Root null Event | `summarize(null)` | `missing` | B1 |
| Valid instanceof | Valid Paid | `inspected:O-1:450` | C1/C2 |
| Instanceof null Amount | Paid with null Amount | `no-match` | B2 |
| Instanceof null Receipt | Paid with null Receipt | `no-match` | B2 |
| Instanceof wrong type | `"unexpected"` | `no-match` | A1 |
| Valid Packet | `Packet<Receipt>` with Amount | `packet:R-1:450` | C6 |
| Packet with null Amount | `Packet<Receipt>` containing Receipt with null amount | `packet:unavailable` | B2/C6 |
| Root null Packet | `packetInfo(null)` | `packet:missing` | B1/C6 |

The following program has **15 `check` calls**. Each `check` compares expected and actual; if they differ, it throws `AssertionError`. Thus, it only prints `15/15 checks passed` when all preceding tests succeed.

## 9. Standalone program: testing the full checklist on Java 21+

Create the file **`RecordPatternChecklistDemo.java`**:

```java
public class RecordPatternChecklistDemo {
    sealed interface Event permits Paid, Rejected, Pending {}

    record Amount(long cents, String currency) {}
    record Receipt(String number, Amount amount) {}
    record Paid(String orderId, Receipt receipt) implements Event {}
    record Rejected(String orderId, String reason) implements Event {}
    record Pending(String orderId) implements Event {}
    record Packet<T>(T data) {}

    static String summarize(Event event) {
        return switch (event) {
            case Paid(var id, Receipt(var no, Amount(var cents, var currency)))
                    when cents > 0 && currency != null
                            && currency.matches("[A-Z]{3}") ->
                    "paid:" + id + ":" + no + ":" + cents + ":" + currency;

            case Paid(var id, Receipt(var no, var amount)) ->
                    "paid:invalid-amount";

            case Paid(var id, var receipt) ->
                    "paid:missing-receipt";

            case Rejected(var id, var reason)
                    when reason != null && !reason.isBlank() ->
                    "rejected:" + id + ":" + reason;

            case Rejected(var id, var reason) ->
                    "rejected:invalid-reason";

            case Pending(var id) -> "pending:" + id;
            case null -> "missing";
        };
    }

    static String inspect(Object value) {
        if (value instanceof Paid(var id,
                Receipt(var no, Amount(var cents, var currency)))
                && id != null && !id.isBlank() && cents > 0) {
            return "inspected:" + id + ":" + cents;
        }
        return "no-match";
    }

    static String packetInfo(Packet<Receipt> packet) {
        return switch (packet) {
            case Packet(Receipt(var no, Amount(var cents, var currency))) ->
                    "packet:" + no + ":" + cents;
            case Packet(var receipt) -> "packet:unavailable";
            case null -> "packet:missing";
        };
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    public static void main(String[] args) {
        Paid paid = new Paid("O-1",
                new Receipt("R-1", new Amount(450, "USD")));
        Paid zero = new Paid("O-0",
                new Receipt("R-0", new Amount(0, "USD")));
        Paid nullAmount = new Paid("O-4",
                new Receipt("R-4", null));
        Paid nullReceipt = new Paid("O-5", null);

        check("paid", "paid:O-1:R-1:450:USD", summarize(paid));
        check("zero", "paid:invalid-amount", summarize(zero));
        check("null-amount", "paid:invalid-amount",
                summarize(nullAmount));
        check("null-receipt", "paid:missing-receipt",
                summarize(nullReceipt));
        check("rejected", "rejected:O-2:out-of-stock",
                summarize(new Rejected("O-2", "out-of-stock")));
        check("bad-reason", "rejected:invalid-reason",
                summarize(new Rejected("O-2", " ")));
        check("pending", "pending:O-3",
                summarize(new Pending("O-3")));
        check("root-null", "missing", summarize(null));

        check("inspect-paid", "inspected:O-1:450", inspect(paid));
        check("inspect-no-amount", "no-match",
                inspect(nullAmount));
        check("inspect-no-receipt", "no-match",
                inspect(nullReceipt));
        check("inspect-not-paid", "no-match",
                inspect("unexpected"));

        check("packet-paid", "packet:R-1:450",
                packetInfo(new Packet<>(paid.receipt())));
        check("packet-null-amount", "packet:unavailable",
                packetInfo(new Packet<>(nullAmount.receipt())));
        check("packet-null", "packet:missing", packetInfo(null));

        System.out.println("15/15 checks passed");
    }
}
```

**Compile/run with JDK 21+:**

```bash
javac --release 21 RecordPatternChecklistDemo.java
java RecordPatternChecklistDemo
```

**Exact stdout, verified on JDK 24:**

```text
paid -> paid:O-1:R-1:450:USD
zero -> paid:invalid-amount
null-amount -> paid:invalid-amount
null-receipt -> paid:missing-receipt
rejected -> rejected:O-2:out-of-stock
bad-reason -> rejected:invalid-reason
pending -> pending:O-3
root-null -> missing
inspect-paid -> inspected:O-1:450
inspect-no-amount -> no-match
inspect-no-receipt -> no-match
inspect-not-paid -> no-match
packet-paid -> packet:R-1:450
packet-null-amount -> packet:unavailable
packet-null -> packet:missing
15/15 checks passed
```

The program was **executed using JDK 24 JShell**, using syntax finalized in Java 21, and passed all 15/15 expected results. The `summarize`/`inspect` pair has **different criteria**: `summarize` requires a validly formatted currency code, whereas `inspect` only checks the ID and a positive amount. This **difference in contract** is intentional, serving as a reminder that **the same record pattern does not imply the same validation policy**.

**Checklist review of the program:**

- `Paid(var id, Receipt(...Amount(...)))` demonstrates a three-level nested record pattern.
- `Receipt(..., var amount)` allows a null amount component, enabling separate classification when `Receipt` exists but `Amount` does not match.
- `case Paid(var id, var receipt)` catches `Paid` instances that do not match the deeper patterns.
- `when` ensures data is checked before the display branch runs.
- `case Rejected` has a guarded branch and a fallback branch.
- `Packet<Receipt>` proves that a generic record pattern can use static type information for inference.
- `case null` is an explicit policy for a null selector.
- `switch` on sealed `Event` does not need `default`; the compiler checks variant coverage.
- Assertions help catch regressions immediately when schema, guards, or case order change.

## 10. Negative compile tests: checklist errors to catch before runtime

The following four snippets are **intentionally wrong** and must not be placed into the runnable file in section 9. They were tested in a **JDK 24** JShell environment with equivalent types declared in `RecordPatternChecklistDemo`.

### 10.1. Wrong component count (A2)

`Paid` has exactly **two** components: `orderId` and `receipt`. You cannot write:

```java
// INTENTIONALLY WRONG in a class containing Paid.
static boolean wrongArity(Object input) {
    return input instanceof Paid(var id);
}
```

The compiler reports **`incorrect number of nested patterns`**. Both components are required, such as `Paid(var id, var receipt)`.

### 10.2. General case dominating a deeper case (C3)

```java
// INTENTIONALLY WRONG in a switch on Event.
case Paid(var id, var receipt) -> "broad";
case Paid(var id, Receipt(var no, var amount)) -> "specific";
```

The first case covers every `Paid`, so the latter case is **dominated**. The JDK 24 compiler rejects it with an error stating that the case label is dominated by a preceding case label. Fix this by placing `Paid(...Receipt(...))` **before** the general case.

### 10.3. Non-exhaustive switch expression (C4)

```java
// INTENTIONALLY WRONG: Pending is omitted.
static String incomplete(Event event) {
    return switch (event) {
        case Paid p -> "paid";
        case Rejected r -> "rejected";
        case null -> "missing";
    };
}
```

Because `Event` is sealed and `Pending` remains, the compiler rejects the `switch expression` for **not covering all possible input values**. `case null` does not substitute for a `Pending` case. Add `case Pending p -> "pending";` to maintain an explicit contract.

### 10.4. Cannot check generic type arguments directly from Object (C6)

```java
// INTENTIONALLY WRONG: Packet<Receipt> cannot be checked from Object.
static boolean unsafe(Object input) {
    return input instanceof Packet<Receipt> p;
}
```

The compiler rejects this because `Object` cannot be safely checked/cast to a non-reifiable generic type like `Packet<Receipt>` in this situation. Use `Packet<?>` to check the container, then check the component appropriately.

**Do not overgeneralize:** the type `Packet<?>` is reifiable for checking the raw record type; Java also has valid `instanceof` checks in narrower type contexts. The negative example here is specifically **`Object` to `Packet<Receipt>`**.

## 11. Checklist for schema changes and maintainability

When adding or modifying a record's components, patterns can be affected even if the business logic itself has not changed.

For example, changing:

```java
record Receipt(String number, Amount amount) {}
```

to:

```java
record Receipt(String number, Amount amount, String issuedBy) {}
```

Old `Receipt(var number, var amount)` patterns are missing the third component, so they are **no longer valid**. In large codebases with many nested patterns, this is schema coupling. The compiler helps detect mismatched component counts, but does not guarantee which fix is business-correct.

**Checklist when changing a record declaration:**

- List all uses of `Receipt(...)` in `instanceof` and `switch`.
- Verify the **count, order, and types** of components in each pattern.
- Compile against the target JDK/source level.
- Run level-by-level null tests, guard tests, and business outcome tests.
- Pay special attention to components of the same type if their order changes: `record Person(String first, String last)` with `Person(var last, var first)` can still **compile**, yet interpret the data backward.
- If many call sites only need the reference number, consider keeping `Receipt` as a value object and calling `receipt.number()`, or a domain helper, instead of deconstructing all components.

**There is no "standard maximum depth"** prescribed by Java for code quality. A moderately deep pattern packed with variables, guards, and fallback branches can be harder to read than a longer but crystal-clear pattern. Use practical review: can someone else explain the match/non-match paths and component names?

### 11.1. When to split into steps

If you need exact messages for "missing Receipt", "missing Amount", "invalid currency", and "non-positive cents", a single `instanceof` with a Boolean result does not provide enough cause information. You can inspect each level step by step:

```java
// Illustration in a class containing Paid and Receipt.
static String diagnosePaid(Object value) {
    if (!(value instanceof Paid paid)) return "not-paid";

    Receipt receipt = paid.receipt();
    if (receipt == null) return "receipt-null";

    Amount amount = receipt.amount();
    if (amount == null) return "amount-null";

    if (amount.cents() <= 0) return "nonpositive-cents";
    if (amount.currency() == null) return "currency-null";
    if (!amount.currency().matches("[A-Z]{3}"))
        return "invalid-currency-format";

    return "ok";
}
```

This is an **illustrative method**, not called in the main demo file. It intentionally returns the **first reason in check order**, rather than aggregating all errors. A cleaner method for validation/debugging can be more valuable than a very long nested pattern with many guards and fallbacks.

### 11.2. Constructor invariants matter more than repeating guards

In a real system, if policy always requires `Amount.cents > 0` and a valid currency format, you can enforce the invariant:

```java
// Illustrative snippet replacing the demo's Amount record.
record Amount(long cents, String currency) {
    public Amount {
        if (cents <= 0
                || currency == null
                || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("invalid amount");
        }
    }
}
```

Then objects created through a valid constructor cannot have an `Amount` that violates this rule, and tests shift to verifying that the constructor rejects invalid data. Clearly distinguish a model "intentionally relaxed for learning patterns" from a domain model that "must block invalid states at the boundary".

**Note:** `record` does not automatically make all components non-null or deeply immutable. A record with a mutable object component is still at risk of mutation via reference; consider defensive copies and corresponding boundaries.

## 12. Special risk review

### 12.1. Accessors should not have unexpected side effects

Record patterns deconstruct via record accessors. If a record defines a custom accessor and that accessor throws an exception during matching, the result can be a **`MatchException`**, not a normal Boolean non-match. For records used as data models, prefer clear accessors with minimal side effects; when an error occurs during matching, read the stack trace and its cause.

### 12.2. Case ordering is a behavioral contract, not just syntax

In a `switch`, a specific guarded case might fail to match due to a business condition, and a broader subsequent case then receives the data. That is processing policy. If you change case order or turn a broad branch into `default`, review expected outputs—do not just check that the code compiles.

### 12.3. Exhaustiveness does not prove business rules are right

The compiler can guarantee coverage of all sealed variants in a `switch expression`, but it does not prove that a monetary amount is valid, an order ID exists in the database, or a regex was chosen correctly for the business. Those require validation and tests.

### 12.4. Do not guess performance from the number of record patterns

Deep record patterns are **not inherently slower or faster** than multiple manual accessor calls across every workload. JIT compilation, data types, null frequencies, and accessor methods all have an impact. If performance is a requirement, use a controlled benchmark such as JMH with warmup and representative data; do not draw general conclusions from a few `System.nanoTime()` calls.

### 12.5. Boundaries and generic data

APIs receiving JSON, queue events, or `Object` should parse/validate before constructing typed models. Avoid letting a `String type` plus `Object payload` leak deep into business logic; when using generic records, validate elements in containers appropriately within type erasure limits. Pattern matching does not automatically guarantee the schema of untrusted data.

## 13. Pre-merge testing checklist

To bring this lesson into a code review workflow, you can use the following short template:

| Review question | Minimum evidence |
| --- | --- |
| Does the source level support record patterns? | JDK/toolchain, `javac --release 21` or equivalent configuration |
| Does the record declaration have the right components? | Cross-check declaration and pattern; compiles cleanly |
| Are `var` types and component order correct? | Method/variable calls, code review; negative compile tests when helpful |
| Is root null handled? | Test `instanceof null` and `case null` branch if switch allows it |
| Are null nested records handled? | Test missing Receipt and missing Amount separately |
| Are nullable components handled? | Test `Amount(450, null)`/`Rejected(...,null)` per policy |
| Are guards null-safe? | Use `&&`/`when` in the right order; test blank/null |
| Are there dominated cases or missing subtypes? | Negative compile tests for dominance/exhaustiveness |
| Can generic arguments be verified at runtime? | Use wildcards and runtime type checks instead of `Packet<Receipt>` from Object |
| Are invariants at the right layer? | Constructor/factory/validator and negative tests |
| Are test results verified with assertions? | Clear expected/actual; a failing case must fail the test |
| Do schema changes have side effects? | Review deconstruction patterns, run regression tests |

**Suggested workflow:** check A (structure) first → B (nulls/validation) → C (guards/switch/generics) → D (tests/schema/maintainability). When a bug is found, fix only the appropriate layer and rerun all tests; do not add `default` or broad casts to hide errors.

## 14. Practice exercises

### Exercise 1 — find the component-count mismatch in a record pattern

Given:

```java
record Coordinate(double latitude, double longitude) {}
record Destination(String name, Coordinate point) {}
```

Identify the error in:

```java
// INTENTIONALLY WRONG.
if (value instanceof Destination(var name, Coordinate(var latitude))) {
    System.out.println(name);
}
```

**Hint:** `Coordinate` has two components, but `Coordinate(var latitude)` only has one. Fix it to `Coordinate(var latitude, var longitude)` and test `point == null`.

### Exercise 2 — distinguish nested null from component null

With `Destination` and `Coordinate`, test:

- `new Destination("A", null)`: does nested `Coordinate(...)` match?
- `new Destination(null, new Coordinate(10, 20))`: does `var name` receive null?
- `value == null`: how do `instanceof` and `switch` handle it?

**Requirement:** explain each result before running the test.

### Exercise 3 — add a valid guard

Write an `instanceof` pattern that extracts `latitude` and `longitude`, accepting values only if both are finite and within `[-90,90]` and `[-180,180]` respectively. Use `Double.isFinite` to exclude `NaN`/infinity; remember that primitive `double` cannot be null.

### Exercise 4 — extend the sealed hierarchy

Add `Canceled(String orderId) implements Event` to the demo model and `permits`. Before updating `summarize`, run the compiler; explain why an exhaustive `switch expression` requires the new case. Then add a test case for `Canceled`.

### Exercise 5 — review an overly deep pattern

Create a four-level nested record. If a method only needs a reference code at the second level, try two solutions: (1) a four-level deep pattern, (2) a two-level pattern followed by named accessors. Measure the number of bound variables, the number of nested records required to be non-null, the ability to report failure reasons, and the degree of schema coupling. Choose the option that best serves the domain; do not use line count alone as the criterion.

## 15. Summary

A good record pattern passes **four layers of checks**:

1. **Correct structure:** record type, component count and order, `var`/subpattern types.
2. **Correct semantics:** level-by-level nulls, guards, pattern variables in flow scope, generic inference, and data policy.
3. **Correct branching:** specific cases before broad cases, exhaustive switch on sealed types, explicit handling of null selectors.
4. **Correct maintainability:** tests with assertions, negative compile tests, invariants at boundaries/constructors, reviews on schema changes, and sensible nesting depth.

With the `Paid → Receipt → Amount` model, the program verified **15/15 runtime cases**, covering nulls at multiple levels, guards, sealed variants, and generic `Packet`. Four intentionally wrong scenarios—arity, dominance, exhaustiveness, and generic type erasure—were rejected by the JDK 24 compiler. These are reusable criteria for code reviews, though **they do not replace domain validation or product requirement reviews**.

### Official Java documentation

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS 21 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
