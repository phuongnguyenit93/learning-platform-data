# Writing Short and Readable Guards with `when` in Java 21

## 1. Goal: Guards Should State Rules Clearly, Not Hide Them

In Java 21's **pattern matching for switch**, a `case` branch can add a `when` condition after the pattern:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "text: " + text;
    case null -> "missing";
    default -> "unsupported";
};
```

The `String text` part is the **type pattern**; `text.isBlank()` is the **guard expression**. Java evaluates the guard only after `String text` has matched, so the pattern variable `text` can be used safely inside the guard.

A good guard helps the reader quickly answer two questions:

- **Which variant is being examined?** For example: `PaymentCaptured`, `String`, `LoginAttempt`.
- **What additional condition causes this variant to be selected?** For example: an amount exceeding a threshold, an empty string, or an eligible account.

A **short and readable guard** is not merely about having fewer characters. It must accurately describe business intent, have predictable conditions, maintain clear case ordering, and be testable without needing to parse dozens of operations on a single line.

This article uses standard Java 21: `when`, type patterns, record patterns, and pattern `switch` are finalized features—**no `--enable-preview` required**.

## 2. How `when` Works: Pattern Matches First, Then the Guard Is Evaluated

Common form:

```java
case Type variable when booleanExpression -> result
```

or with a record pattern:

```java
case PaymentCaptured(var paymentId, var amountVnd)
        when amountVnd >= 1_000_000L -> result
```

Step-by-step evaluation:

1. The `switch` selector is evaluated.
2. Java checks the pattern on a `case` label.
3. If the pattern **does not match**, that label's guard is **not evaluated**.
4. If the pattern matches, the pattern variables are bound, and then the guard is evaluated to a `boolean`.
5. Guard is **true**: the branch is selected. Guard is **false**: this label does not apply, and evaluation continues to the remaining labels.

The condition after `when` must be an expression of type `boolean` or `Boolean` that can be unboxed to `boolean`. For predictability, prefer returning a **primitive `boolean`** from guard methods; avoid `Boolean` results that could be `null` and throw a `NullPointerException` upon unboxing.

**Distinction from other syntax:**

- `when` is the **guard part of a pattern case label**, not an operator you can arbitrarily attach after `case null`, `default`, or constant labels.
- In an `if` statement, write `if (obj instanceof String text && !text.isBlank())`, **not** `if (obj instanceof String text when ...)`.
- Legacy preview syntax such as `case String text && text.length() > 3` was replaced by `case String text when text.length() > 3` in Java 21.
- Java 21 treats `when` as a contextual keyword in the appropriate context; it does not turn every occurrence of the identifier `when` in code into a guard.

## 3. Six Principles for Writing Readable Guards

| Principle | Do | Avoid |
| --- | --- | --- |
| **One primary meaning** | `when amountVnd >= LARGE_PAYMENT_VND` | Mixing authorization, state, and amount calculations in one guard |
| **Meaningful names** | `when isEligibleForRefund(refund)` | `when check(x) && p(y)` |
| **Shallow logic** | `when isHighRiskAttempt(userId, attempts)` | A long, hard-to-read chain of `&&` and `||` |
| **No side effects** | Methods that only compute a `boolean` result | Writing to a DB, sending notifications, or mutating state inside a guard |
| **Clear precedence order** | Specific guards before general cases | General cases placed first, shadowing the guarded ones |
| **Provide a base branch** | `case Paid payment -> ...` after guarded branches | Having only guarded branches, leaving some values unhandled |

A helpful rule of thumb: **a reviewer should understand the guard without having to mentally simulate the entire business workflow**. If they cannot, it is time to name a dedicated predicate or clarify the domain data.

## 4. Writing Simple Conditions Directly After `when`

Short, self-explanatory guards can be written directly in the `case`:

```java
case String text when text.isBlank() -> "blank input";
case Integer quantity when quantity < 0 -> "invalid quantity";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "large payment";
```

The three examples above are **case label snippets** inside a suitable `switch`, not standalone programs. They work well because the condition is immediately recognizable without hidden knowledge:

- `isBlank()`: the string is empty or consists only of whitespace.
- `quantity < 0`: a negative quantity.
- `amountVnd >= 1_000_000L`: an amount of at least one million VND, inclusive of the threshold.

When a threshold represents a business policy, replace the literal number with a named constant:

```java
static final long LARGE_PAYMENT_VND = 1_000_000L;

// Inside switch:
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= LARGE_PAYMENT_VND -> "large payment";
```

This separates the meaning *"large payment"* from the specific configured number. Avoid naming a constant simply `LIMIT`, as it does not state what is being limited or in what unit.

### 4.1. Do Not Put Every Check Into the Guard

Example:

```java
// CODE SNIPPET illustrating a hard-to-maintain structure:
case PaymentCaptured(var id, var amount)
        when amount > 0
             && id != null
             && !id.isBlank()
             && amount >= 1_000_000L
             && policyAllows(id)
             && riskScore(id) < 40 -> "approved";
```

`policyAllows` and `riskScore` are hypothetical methods. This block simultaneously validates data, classifies the amount, checks policy, and evaluates risk. A reader cannot tell which condition is the essence of the branch.

Consider **validating data at the entry boundary**, **separating classification**, and **extracting complex business decisions into a named predicate**. You do not need to extract every condition into a helper; simple conditions should stay inline.

## 5. Use Named Predicates When a Condition Expresses a Domain Rule

Suppose we need to determine whether a login attempt requires an alert:

```java
static final int ALERT_THRESHOLD = 3;

static boolean requiresLoginAlert(String userId, int failedAttempts) {
    return userId != null
            && !userId.isBlank()
            && failedAttempts >= ALERT_THRESHOLD;
}
```

Inside `switch`:

```java
case LoginAttempt(var userId, var failedAttempts)
        when requiresLoginAlert(userId, failedAttempts) ->
    "security alert for " + userId;
```

The name `requiresLoginAlert` clarifies the **domain meaning**. The implementation is separated so it can be tested independently:

- The user ID must not be `null`.
- The user ID must not be blank.
- The number of failed attempts must be at least the threshold.

The snippet above is an **illustrative fragment**; the `LoginAttempt` type is declared in the complete program in Section 12.

**When should you extract a helper?** When any of these signs appear: the condition has multiple logical groups, it is reused in multiple places, it needs independent boundary testing, or a helper name explains the intent better than the raw boolean expression.

**When should you not extract?** A check like `text.isBlank()` or `amountVnd >= LARGE_PAYMENT_VND` is already clear inline and is usually better than forcing a jump to a helper like `isBlankString(text)` that adds no value.

### 5.1. Method Names Should Describe a Predicate, Not an Action

Choose question-like names that return `boolean`:

- `isLargePayment(amountVnd)`
- `requiresLoginAlert(userId, attempts)`
- `isRefundEligible(refund)`
- `hasActiveSubscription(customer)`

Avoid vague names like `process`, `check`, `validate`, or `doWork`. In particular, `validatePayment` can imply throwing an exception or mutating state; if it only returns `boolean`, `isPaymentEligible` is much clearer.

Do not use a helper merely to **hide unsafe logic**. A method named `isEligible` that has significant side effects still makes the guard unpredictable.

## 6. Keep Guards Pure and Cheap

A guard can be evaluated whenever a pattern matches, before a branch is chosen. If a guard mutates external state, reordering or adding a `case` can change how many times or when that side effect occurs.

**Avoid:**

```java
// SYNTAX SNIPPET to avoid if reserveBalance() mutates the balance:
case PaymentRequested request
        when reserveBalance(request) -> "reserved";
```

Here, `reserveBalance` is a hypothetical operation with a side effect. When the guard returns `false`, subsequent branches may still be evaluated even though the balance has already changed. When a new earlier `case` is added, the guard might no longer run and the side effect disappears.

**Separate concerns instead:**

1. Use the guard to **classify using already-available data**, ideally a pure predicate.
2. After `switch` selects a branch, perform the action in a handler or separate processing step.
3. Handle I/O errors, timeouts, transactions, and retries outside the short guard expression.

Conceptual example:

```java
// CODE SNIPPET: business methods must be defined separately
switch (event) {
    case PaymentRequested request
            when isEligibleForReservation(request) ->
        reserveBalance(request);
    case PaymentRequested request ->
        rejectReservation(request);
    default -> handleOther(event);
}
```

The guard only decides **eligibility**; `reserveBalance` runs only inside the body of the selected branch. If eligibility depends on mutable state, the handler still needs appropriate transaction or concurrency controls; a pure guard cannot replace atomic checks at execution time.

### 6.1. Exceptions in Guards Do Not Automatically Become "Guard False"

If a predicate throws an exception, `switch` does not treat that exception as `false` and fall through to other branches. The error propagates according to normal Java rules. Therefore, predicates should have clear contracts regarding `null` and errors; handle exceptions at the appropriate layer rather than masking all errors with `catch (Exception e) { return false; }`.

## 7. Ordering Cases: Specific Guards Before Base Cases

For the same variant, a common pattern is:

```java
return switch (payment) {
    case null -> "missing";
    case PaymentCaptured(var id, var amountVnd)
            when amountVnd >= 1_000_000L ->
        "large payment";
    case PaymentCaptured(var id, var amountVnd) ->
        "payment";
    default -> "other event";
};
```

This is an **example snippet** assuming the selector's type permits these cases. There are three distinct decisions:

- The `PaymentCaptured(...)` pattern narrows the subtype.
- The guard selects the special-policy branch.
- The **unguarded** branch of the same subtype handles the remainder of that subtype.

If you reverse the two branches:

```java
// INTENTIONALLY INVALID SNIPPET: compiler reports dominated case
case PaymentCaptured(var id, var amountVnd) -> "payment";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "large payment";
```

The first branch covers all `PaymentCaptured` instances, so the guarded branch after it can never be selected; this is a **dominance** error. Writing a readable guard is not enough if the ordering is wrong.

### 7.1. Multiple Priority Tiers

Suppose a business has three payment tiers:

```java
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 5_000_000L -> "VIP";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "LARGE";
case PaymentCaptured(var id, var amountVnd) -> "STANDARD";
```

Reading top-down: amounts from 5 million get `VIP`; from 1 million up to under 5 million get `LARGE`; the rest get `STANDARD`. If you swap the two guards, amounts of 5 million or more would fall into the `LARGE` branch first.

Java does not prove arbitrary mathematical relationships between guards; **test 999,999, 1,000,000, 4,999,999, 5,000,000, and 5,000,001**. Case order expresses priority policy, not just formatting preference.

## 8. Keep Boolean Expressions Well-Structured

When a guard requires multiple checks, prefer one of two approaches:

**Approach A — A short `&&` chain in a natural order:**

```java
case LoginAttempt(var userId, var attempts)
        when userId != null
             && !userId.isBlank()
             && attempts >= 3 -> "alert";
```

`&&` short-circuits from left to right. Check `userId != null` before `userId.isBlank()` to avoid dereferencing `null`.

**Approach B — A named predicate:**

```java
case LoginAttempt(var userId, var attempts)
        when requiresLoginAlert(userId, attempts) -> "alert";
```

If a guard combines `&&` and `||`, group them clearly with parentheses or extract a helper. For example:

```java
// METHOD SNIPPET: flags are primitive booleans
static boolean requiresReview(
        boolean manualFlag,
        boolean fraudFlag,
        boolean isHighAmount) {
    return manualFlag || (fraudFlag && isHighAmount);
}
```

Whenever a reader would have to recall operator precedence rules to understand the intent, add parentheses to communicate the business structure.

### 8.1. Avoid Redundant Comparisons

Since `isBlank()` already returns a boolean:

```java
// Longer without adding meaning:
case String text when text.isBlank() == true -> "blank";

// Clearer:
case String text when text.isBlank() -> "blank";
```

And instead of `when !(!text.isBlank())`, write `when text.isBlank()`. Guards with fewer nested negations are easier to verify.

### 8.2. Name Variables So Conditions Read Like Business Statements

Compare:

```java
case PaymentCaptured(var x, var y) when y >= 1_000_000L -> "large";
case PaymentCaptured(var paymentId, var paidAmountVnd)
        when paidAmountVnd >= LARGE_PAYMENT_VND -> "large";
```

The second version makes clear which quantity is checked, what unit it uses, and what the threshold means. With record patterns, variables are bound **by component position**, so verify that `paidAmountVnd` actually corresponds to the amount component and not another `long` value.

## 9. `null` and the Difference Between Pattern Failure and Guard False

A pattern `case String text` matches only non-`null` `String` values. If the selector is `null`, the guard `text.isBlank()` **is not executed**.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text";
        default -> "unsupported";
    };
}
```

Different inputs take different paths:

| Value | Result | Explanation |
| --- | --- | --- |
| `null` | `missing` | Matches `case null` |
| `" "` | `blank` | Matches `String`, guard `isBlank()` is true |
| `"abc"` | `text` | Matches `String`, guard is false, handled by base `String` branch |
| `42` | `unsupported` | Does not match `String`, guard is not executed |

If a selector can be `null` without a matching `case null` label, a Java 21 `switch` normally throws `NullPointerException`; **`default` does not match `null`**. Writing a guard just to handle a `null` selector is the wrong place; decide the `null` policy explicitly.

**Unlike the selector**, components inside a record can still be `null` depending on the model. If a guard calls methods on a component, handle `null` safely:

```java
// SYNTAX SNIPPET: CustomerEvent has an email component that may be null
case CustomerEvent(var email)
        when email != null && !email.isBlank() ->
    "email present";
```

The record pattern `CustomerEvent(var email)` does not guarantee that `email` is non-`null` just because the selector is a record; the guard must check data constraints when needed.

## 10. Exhaustiveness: Guarded Branches Alone May Not Cover a Subtype

With a sealed domain:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

A `switch` expression with only a **guarded** `Success` branch and an unguarded `Failure` branch fails to cover `Success` instances that do not satisfy the guard:

```java
// INTENTIONALLY NON-COMPILING SNIPPET:
return switch (result) {
    case Success(var value) when value != null -> "ok";
    case Failure(var reason) -> "failed";
};
```

If `Success.value()` is `null`, the guarded `Success` branch is not selected, and `Failure` does not match. The compiler cannot treat `when value != null` as covering all `Success` cases.

**Fix** by adding an unguarded base branch for `Success`:

```java
return switch (result) {
    case Success(var value) when value != null -> "ok: " + value;
    case Success(var value) -> "success without value";
    case Failure(var reason) -> "failed: " + reason;
};
```

When all subtypes of a sealed hierarchy are fully covered, there is no need to add `default` just to satisfy the compiler. An unconditional `default` can hide missing branches when the domain is extended later.

**Notable exception:** `when true` is a special case that Java may treat as an unrestricted guard for coverage. However, when the goal is to express a general fallback branch, writing it **without a guard** is usually clearer than `when true`.

## 11. Using `when` in the Right Place in Your Architecture

There is a practical boundary between "data classification" and "business execution":

```text
Input
  |
  v
Validate / normalize required data
  |
  v
switch: match subtype + short guard
  |
  +--> case A -> handler A
  +--> case B -> handler B
  +--> case C -> handler C
  |
  v
Controlled result or side effect
```

If a guard contains multiple independently changing rules, consider:

- **Named predicate:** a pure, reusable, unit-testable condition.
- **Policy object:** when rules depend on configuration or system-managed strategies.
- **Validation before `switch`:** when data must be normalized or rejected before classification.
- **Handler after `switch`:** when actions involve side effects or complex exception handling.

For example, instead of stuffing limit checks, fraud checks, customer eligibility, and database queries into a single guard for `PaymentCaptured`, move them into an **eligibility evaluation** step with a clear contract. The `switch` then classifies the evaluation result rather than commanding transactions inside a guard.

Do not "overuse clean code" by creating 10 helpers just to wrap a simple `>` comparison. Optimize for **the person reading the code at the call site**.

## 12. Complete Java 21 Program: Short Guards, Helpers, and Base Branches

Save to **`ReadableGuardDemo.java`**:

```java
public class ReadableGuardDemo {
    private static final long LARGE_PAYMENT_VND = 1_000_000L;
    private static final int LOGIN_ALERT_THRESHOLD = 3;

    sealed interface Event
            permits PaymentCaptured, LoginAttempt, RefundRequested {}

    record PaymentCaptured(String paymentId, long amountVnd)
            implements Event {}

    record LoginAttempt(String userId, int failedAttempts)
            implements Event {}

    record RefundRequested(String refundId, long amountVnd,
                           boolean approved)
            implements Event {}

    static boolean isLargePayment(long amountVnd) {
        return amountVnd >= LARGE_PAYMENT_VND;
    }

    static boolean requiresLoginAlert(String userId, int failedAttempts) {
        return userId != null
                && !userId.isBlank()
                && failedAttempts >= LOGIN_ALERT_THRESHOLD;
    }

    static boolean isRefundReady(long amountVnd, boolean approved) {
        return approved && amountVnd > 0;
    }

    static String describe(Event event) {
        return switch (event) {
            case null -> "missing event";

            case PaymentCaptured(var paymentId, var amountVnd)
                    when isLargePayment(amountVnd) ->
                "large payment " + paymentId + ": " + amountVnd + " VND";

            case PaymentCaptured(var paymentId, var amountVnd) ->
                "payment " + paymentId + ": " + amountVnd + " VND";

            case LoginAttempt(var userId, var failedAttempts)
                    when requiresLoginAlert(userId, failedAttempts) ->
                "login alert " + userId + ": " + failedAttempts + " failures";

            case LoginAttempt(var userId, var failedAttempts) ->
                "login " + userId + ": " + failedAttempts + " failures";

            case RefundRequested(var refundId, var amountVnd, var approved)
                    when isRefundReady(amountVnd, approved) ->
                "refund ready " + refundId + ": " + amountVnd + " VND";

            case RefundRequested(var refundId, var amountVnd, var approved) ->
                "refund pending " + refundId;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new PaymentCaptured("PAY-1", 1_500_000L),
            new PaymentCaptured("PAY-2", 200_000L),
            new LoginAttempt("lan", 3),
            new LoginAttempt("minh", 1),
            new RefundRequested("REF-1", 100_000L, true),
            new RefundRequested("REF-2", 0L, true),
            new RefundRequested("REF-3", 90_000L, false),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        check("large payment PAY-1: 1500000 VND",
                describe(new PaymentCaptured("PAY-1", 1_500_000L)));
        check("payment PAY-3: 999999 VND",
                describe(new PaymentCaptured("PAY-3", 999_999L)));
        check("large payment PAY-4: 1000000 VND",
                describe(new PaymentCaptured("PAY-4", 1_000_000L)));
        check("login alert lan: 3 failures",
                describe(new LoginAttempt("lan", 3)));
        check("login : 7 failures",
                describe(new LoginAttempt("", 7)));
        check("refund pending REF-2",
                describe(new RefundRequested("REF-2", 0L, true)));
        check("missing event", describe(null));

        System.out.println("checks passed");
    }
}
```

Compile and run with **JDK 21**, without enabling preview features:

```bash
javac --release 21 ReadableGuardDemo.java
java ReadableGuardDemo
```

**Stdout:**

```text
large payment PAY-1: 1500000 VND
payment PAY-2: 200000 VND
login alert lan: 3 failures
login minh: 1 failures
refund ready REF-1: 100000 VND
refund pending REF-2
refund pending REF-3
missing event
checks passed
```

Key details to note:

- `PaymentCaptured(...)`, `LoginAttempt(...)`, and `RefundRequested(...)` are **record patterns**.
- The `var` declarations inside them are pattern component variables whose types are inferred from the records.
- `isLargePayment`, `requiresLoginAlert`, and `isRefundReady` are **pure predicates** named after business rules.
- Every guarded branch is followed by an **unguarded branch of the same subtype**, ensuring values that do not meet the special condition are still handled.
- `case null` defines an explicit policy; no `default` is needed because `Event` is a closed sealed hierarchy of three records.
- `check` tests just below and exactly at the payment threshold, login attempt count, and refund status—without requiring `-ea` assertions to be enabled.
- The input `LoginAttempt("", 7)` shows that the guard suppresses the alert when `userId` is blank, while the general branch still returns a description: **rejecting invalid data must be decided by separate validation**, rather than assuming every fallback branch represents valid data.

Some business rules in this example are simplified to illustrate guard style; in a real application, `isRefundReady` might depend on transaction state, remaining refundable amount, permissions, and deadlines. Such checks belong in a policy or service with a clear contract, rather than being crammed into a long guard.

## 13. Common Mistakes When Writing Guards

### Mistake 1 — Unguarded Branch Placed Before Guarded Branch

```java
// INTENTIONALLY INVALID SNIPPET, dominated
case String text -> "any text";
case String text when text.isBlank() -> "blank";
```

**Fix:** move `when text.isBlank()` above the unguarded `String text` branch.

### Mistake 2 — Using `when` in the Wrong Context

```java
// INTENTIONALLY INVALID SNIPPET
if (obj instanceof String text when !text.isBlank()) {
    System.out.println(text);
}
```

**Fix:** in `if`, use `&&`:

```java
if (obj instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

### Mistake 3 — Using a Pattern Variable Out of Scope

```java
// INTENTIONALLY INVALID SNIPPET
switch (obj) {
    case String text when text.isBlank() -> System.out.println(text);
    default -> {}
}
System.out.println(text); // text is not in scope here
```

**Fix:** use the variable within the guard or branch body, or return a common result from a `switch` expression and use that result outside.

### Mistake 4 — Missing Base Branch for a Subtype When the Guard Is False

```java
// INTENTIONALLY NON-COMPILING SNIPPET in a switch expression on sealed Result
return switch (result) {
    case Success(var value) when value != null -> "ok";
    case Failure(var reason) -> "failed";
};
```

**Fix:** add an unguarded `case Success(var value) -> ...` to cover the remaining cases.

### Mistake 5 — Guard Using `||` Without Clear Grouping

```java
// Hard to read: requires verifying operator precedence
when isPriorityCustomer(customer) || isUrgent(order) && hasStock(order)
```

**Fix:** add parentheses `isPriorityCustomer(customer) || (isUrgent(order) && hasStock(order))` if that matches the business rule, or extract a tested `requiresFastLane(customer, order)` method.

### Mistake 6 — Guard With Side Effects

```java
// SYNTAX SNIPPET to avoid
case Order order when chargeCreditCard(order) -> "paid";
```

**Fix:** the guard should only identify the case; perform payment capture in a handler with proper transaction/idempotency handling. Do not turn a false guard into a business failure that already produced side effects.

### Mistake 7 — Hard-Coding Magic Numbers

```java
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1000000 -> "large";
```

**Fix:** use `LARGE_PAYMENT_VND` or a named policy; confirm the threshold and unit with the domain before implementing.

### Mistake 8 — Swallowing All Errors by Returning False

```java
// ANTI-PATTERN METHOD SNIPPET, do not write like this:
static boolean isEligible(Payment payment) {
    try {
        return externalService.check(payment);
    } catch (Exception ignored) {
        return false;
    }
}
```

**Problem:** `false` may mean "not eligible," but here it also hides connection failures, timeouts, or programming bugs. In a real system, separate technical errors from business classification results with proper observability and handling. `Payment` and `externalService` in this snippet are hypothetical.

## 14. Code-Reading Exercises and Answers

**Exercise 1.** Why should these two branches be written in this order?

```java
case String text when text.isBlank() -> "blank";
case String text -> "non-blank";
```

**Answer:** The guarded branch selects the special case first. The unguarded `String` branch after it catches all remaining `String` values. If reversed, the later `when` branch would be dominated by the general branch.

**Exercise 2.** Is the following valid Java 21 syntax?

```java
case Integer value && value > 10 -> "large";
```

**Answer:** No. This resembles legacy preview syntax. Standard Java 21 writes `case Integer value when value > 10 -> "large";`.

**Exercise 3.** Where should a long guard that calls `queryDatabase()`, `sendEmail()`, and `isEligible()` be refactored?

**Answer:** Move I/O operations and email sending out of the guard into a handler or business step with error management. The classification condition can be extracted into a named pure predicate and tested separately. Wrapping side effects inside a helper does not solve the design issue.

**Exercise 4.** Given `case String s when s.length() > 3`, does the guard run when the selector is an `Integer`?

**Answer:** No. The `String s` pattern fails, so the guard is not evaluated. Only when the selector is a `String` is `s` bound and the guard evaluated.

**Exercise 5.** Should you use `default` to fix a sealed-domain `switch` that is non-exhaustive because a guard can be false?

**Answer:** Usually no. If every subtype needs dedicated handling, add the corresponding unguarded branch instead of `default` so the compiler can still detect new subtypes in the future. For genuinely open sources like `Object`, `default` is an appropriate fallback policy.

**Exercise 6.** When should `when amount >= LIMIT` stay inline in the `case` instead of being extracted to a helper?

**Answer:** When the condition is simple, used in one place, and the variable name plus `LIMIT` already convey the full meaning. Extract a helper when it is a multi-step domain rule, reused, or needs independent testing.

**Exercise 7.** What does `when userId != null && !userId.isBlank()` do?

**Answer:** `&&` short-circuits: if `userId` is `null`, Java does not call `isBlank()`; the guard returns `false` and the `switch` continues trying the next matching branch. This checks the component, not whether the selector itself is `null`.

## 15. Review Checklist for a `when` Guard

- [ ] The guard adds **one clear condition** after the pattern matches.
- [ ] Pattern variable, predicate, and constant names accurately convey the domain and units.
- [ ] Short conditions are written inline; multi-part conditions are extracted into named predicates.
- [ ] Predicates perform no I/O, state mutation, or uncontrolled transactional side effects.
- [ ] Contracts for `null`, exceptions, data types, and boundary values are clear.
- [ ] `&&`, `||`, and `!` operators have parentheses and ordering that match intent.
- [ ] Priority guarded branches precede general branches; no unexpected dominance occurs.
- [ ] Each subtype is handled when the guard is both true **and** false, if the domain requires exhaustiveness.
- [ ] `default` is not used to mask missing branches in a sealed hierarchy that requires full handling.
- [ ] `case null` or a `null`-rejection policy is defined explicitly.
- [ ] Thresholds are tested just below, exactly at, and just above the boundary.
- [ ] Technical errors are distinguished from a false guard; exceptions are not silently swallowed.

## 16. Official References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `when` guard syntax, type patterns, dominance, and exhaustiveness in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns and component variables used in guards.
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case labels, guards, selection, and dominance.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): `switch` expressions and exhaustiveness.
- [JLS Java SE 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): scope of pattern variables in guard expressions and branches.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): syntax guide and guard examples.
