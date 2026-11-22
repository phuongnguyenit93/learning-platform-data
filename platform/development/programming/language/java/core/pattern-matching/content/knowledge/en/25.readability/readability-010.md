# Reviewing Pattern Matching Readability in Java 21+

## 1. Code Review Goal: Easy to Understand, Correct Behavior, Easy to Change

Pattern matching lets Java express type checks and data destructuring more concisely than chains of `instanceof` + manual casts. However, **fewer lines of code do not automatically mean better readability**. A `switch` containing many type patterns, nested record patterns, and `when` guards can compile cleanly and still be hard to understand: reviewers have to mentally deduce precedence, null cases, behavior when a new type appears, and side effects hidden inside expressions.

This lesson guides you through **reviewing the readability of pattern matching**: evaluating whether others can read, verify correctness, and maintain the code without having to simulate too many conditions in their heads.

Opening principle:

> A review should not only ask “is this pattern valid according to the compiler?” but also “does this pattern clearly express a business rule, preserve behavior, and support safe changes?”.

Three criteria must be met simultaneously:

1. **Correctness:** matches the right type/structure, right case ordering, right null/fallback handling, and exhaustive when needed.
2. **Clarity:** variable names reflect the domain, guards are short and meaningful, nested patterns are not too hard to follow, and each method has a clear responsibility.
3. **Maintainability:** reviewers can identify where to make edits when adding a new subtype or rule, boundary-value test points exist, and no side effects or runtime errors are hidden.

**Versions:** `instanceof` pattern matching became standard in Java 16 (JEP 394); record patterns and pattern matching for `switch` became standard in **Java 21** (JEP 440 and JEP 441). The main examples use **JDK 21+**, without needing `--enable-preview`.

## 2. Components to Identify When Reading Code

Consider this example:

```java
record Point(int x, int y) {}

String position = switch (value) {
    case Point(int x, int y) when x == 0 && y == 0 ->
            "origin";
    case Point(int x, int y) when x > 0 && y > 0 ->
            "quadrant I";
    case Point(int x, int y) ->
            "other point";
    case null -> "missing";
    default -> "not a point";
};
```

A reviewer should be able to distinguish:

- **Selector `value`:** the input expression of the `switch`. The static type of the selector determines which `case` labels can apply.
- **Record pattern `Point(int x, int y)`:** checks for a `Point` and extracts components `x` and `y`.
- **Pattern variables:** `x` and `y` may only be used within the scope where the compiler proves the pattern has matched.
- **Guard `when`:** filters further by value, evaluated after the pattern matches; `when` differs from a condition inside an `if`.
- **Arrow rule `->`:** only the body of the selected branch is executed, with no fall-through to other branches.
- **Unguarded branch:** acts as the catch-all for remaining `Point` values; it should not appear before guarded `Point` branches.
- **`case null`/`default`:** play different roles. In a pattern switch, `default` does not implicitly handle a null selector.

If a reader has to trace back through multiple methods just to know what condition a guard protects, or cannot determine which branch is responsible for a subtype, that is a signal to clarify the design before merging.

## 3. Six-Layer Review Framework

| Review Layer | Key Question | Signals to Check |
| --- | --- | --- |
| **Business intent** | What is the matching block classifying, and why? | Pattern names, case/handler names, a single method having too many responsibilities |
| **Matching order** | Are priority branches and fallbacks clear? | Parent/child types, overlapping guards, dominated cases |
| **Data structure** | Can the record pattern be read smoothly? | Nesting depth, too many components, nullable components |
| **Expressions and scope** | Are guards and pattern variables easy to reason about? | Overly long `when`, `&&`/`||`, ambiguous variable names, type checking |
| **Runtime safety** | Are nulls, exceptions, and side effects transparent? | Custom accessors, I/O calls in guards, altered fallbacks |
| **Evolvability** | Will adding a subtype or rule be missed? | Exhaustive sealed switch, overly broad `default`, boundary-value test suite |

There is no need to grade every line for “aesthetics.” The goal is **specific, verifiable feedback**: which condition is hard to understand, which input causes confusion, which name fails to show the domain, or which case lacks a test.

## 4. Full Example: Reviewing and Improving a Long Switch

### 4.1. Context

Suppose a system classifies four cases: `Login`, `Purchase`, `Heartbeat`, and a null selector. `Event` is a sealed interface; `Purchase` contains a nested record `Money`. Policy:

- Successful login with a non-null/non-blank username → `LOGIN_OK`; all other cases → `LOGIN_REVIEW`.
- Purchase with value of at least 10,000 cents and a valid buyer → `PURCHASE_LARGE`.
- Remaining purchases with positive cents → `PURCHASE`; a null buyer displays `unknown`.
- Purchase with null money or non-positive cents → `PURCHASE_REVIEW`.
- Heartbeat → `PING`; null selector → `MISSING`.

The `before` version uses multiple cases/guards to both identify the event type and enforce business policy. The `after` version reserves `switch` for **dispatching by type**, moving the specific rules for Login/Purchase into clearly named helpers.

Save the file **`PatternReadabilityReviewDemo.java`**:

```java
public class PatternReadabilityReviewDemo {
    sealed interface Event permits Login, Purchase, Heartbeat {}

    record Login(String user, boolean success) implements Event {}
    record Money(int cents) {}
    record Purchase(String buyer, Money money) implements Event {}
    record Heartbeat(long timestamp) implements Event {}

    // Before: valid, but multiple policies are mixed inside one switch.
    static String before(Event event) {
        return switch (event) {
            case Login(var user, boolean success)
                    when success && user != null && !user.isBlank() ->
                    "LOGIN_OK:" + user;
            case Login(var user, var success) -> "LOGIN_REVIEW";

            case Purchase(var buyer, Money(int cents))
                    when cents >= 10_000
                            && buyer != null && !buyer.isBlank() ->
                    "PURCHASE_LARGE:" + buyer;
            case Purchase(var buyer, Money(int cents)) when cents > 0 ->
                    "PURCHASE:" + (buyer == null ? "unknown" : buyer);
            case Purchase(var buyer, var money) -> "PURCHASE_REVIEW";

            case Heartbeat(var timestamp) -> "PING";
            case null -> "MISSING";
        };
    }

    // After: each case only decides which domain group to handle.
    static String after(Event event) {
        return switch (event) {
            case Login login -> describeLogin(login);
            case Purchase purchase -> describePurchase(purchase);
            case Heartbeat heartbeat -> "PING";
            case null -> "MISSING";
        };
    }

    static String describeLogin(Login login) {
        String user = login.user();
        if (login.success() && user != null && !user.isBlank()) {
            return "LOGIN_OK:" + user;
        }
        return "LOGIN_REVIEW";
    }

    static String describePurchase(Purchase purchase) {
        Money money = purchase.money();
        if (money == null) {
            return "PURCHASE_REVIEW";
        }

        int cents = money.cents();
        String buyer = purchase.buyer();

        if (cents >= 10_000 && buyer != null && !buyer.isBlank()) {
            return "PURCHASE_LARGE:" + buyer;
        }
        if (cents > 0) {
            return "PURCHASE:"
                    + (buyer == null ? "unknown" : buyer);
        }
        return "PURCHASE_REVIEW";
    }

    static void check(String name, Event event) {
        String oldValue = before(event);
        String newValue = after(event);

        if (!oldValue.equals(newValue)) {
            throw new AssertionError(
                    name + " mismatch: " + oldValue + " vs " + newValue);
        }
        System.out.println(name + " => " + newValue);
    }

    public static void main(String[] args) {
        check("login-ok", new Login("Ada", true));
        check("login-blank", new Login(" ", true));
        check("login-null-user", new Login(null, true));
        check("login-failed", new Login("Ada", false));
        check("large", new Purchase("Mai", new Money(10_000)));
        check("small", new Purchase("Mai", new Money(500)));
        check("buyer-null", new Purchase(null, new Money(50)));
        check("zero", new Purchase("Mai", new Money(0)));
        check("money-null", new Purchase("Mai", null));
        check("heartbeat", new Heartbeat(123L));
        check("selector-null", null);
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 PatternReadabilityReviewDemo.java
java PatternReadabilityReviewDemo
```

Stdout:

```text
login-ok => LOGIN_OK:Ada
login-blank => LOGIN_REVIEW
login-null-user => LOGIN_REVIEW
login-failed => LOGIN_REVIEW
large => PURCHASE_LARGE:Mai
small => PURCHASE:Mai
buyer-null => PURCHASE:unknown
zero => PURCHASE_REVIEW
money-null => PURCHASE_REVIEW
heartbeat => PING
selector-null => MISSING
```

### 4.2. Review Decisions You Can Draw

1. **Clearer intent:** `after` answers “which group does this event belong to?”, while `describePurchase` answers “which tier does this purchase qualify for?”.
2. **Reduced cognitive load:** previously, the reader had to track two Purchase guards and a fallback Purchase branch amid other event types; now Purchase policy is read continuously in one helper.
3. **Null rules are not hidden:** a null selector is handled in `case null`; a null `Money money` component is handled in `describePurchase`.
4. **Precedence is preserved:** the `>= 10_000` tier is still checked before `> 0`; the `large` test uses the exact 10,000 boundary.
5. **Exhaustiveness is preserved:** `Event` is a sealed interface permitting exactly three record subtypes. `after` covers all three types and `null`, without adding a `default` that would hide new variants.
6. **Testability is preserved:** the program compares `before`/`after` across 11 inputs and throws `AssertionError` if the outputs differ.

**Important note:** Passing all 11 tests **does not prove equivalence for all possible inputs**; in a real application, you should add boundary inputs, exceptions, and side effects according to the business contract. If accessors or helpers cause side effects, comparing returned strings alone may not be enough.

The `before` version is not “wrong” at the language level. In a very short snippet or when branches directly reflect a classification table, keeping the `switch` inline may be better. The `after` version is useful here because the Login/Purchase policies have clear names, scopes, and test points.

## 5. Reviewing Branch Ordering and Exhaustiveness

### 5.1. Specific Patterns Before General Patterns

Correct example when distinguishing subtypes:

```java
class Document {}
class ConfidentialDocument extends Document {}

// Part of a switch on an Object selector:
case ConfidentialDocument secret -> "restricted";
case Document ordinary -> "regular";
```

If `case Document` comes first, it covers `ConfidentialDocument` as well; the compiler may report the later label as **dominated**. Even so, the reviewer must understand the domain: you cannot “fix” it by deleting the Confidential branch if it has different security rules.

With guards:

```java
case Purchase(var buyer, Money(int cents))
        when cents >= 10_000 -> "large";
case Purchase(var buyer, Money(int cents))
        when cents > 0 -> "normal";
case Purchase(var buyer, var money) -> "review";
```

The unguarded branch should be placed after the two classification branches. When an earlier guard evaluates to false, Java can try the next branch; a guard does not mean “this branch must be chosen.”

### 5.2. Exhaustiveness of Switch Expressions

A `switch` expression must return a result or complete abruptly with an exception for every applicable value. With a sealed hierarchy, the compiler can use `permits` information to check exhaustiveness.

**Review warning:** Adding `default -> "unknown"` to every sealed switch can eliminate a useful signal when a new subtype is added: the compiler will no longer force the author to revisit each classification site. However, `default` still has a legitimate place if the domain is genuinely open, needs to accept unknown subtypes, or intentionally routes unsupported values to a fallback.

Avoid using `case Event e -> ...` or `default` prematurely just to silence missing-case compiler errors before the contract is defined.

### 5.3. Null Selector Does Not Mean Null Component

- `case null` checks whether **the entire selector** is null.
- `new Purchase("Mai", null)` is a non-null Purchase object with a null Money component. The pattern `Purchase(var buyer, Money(int cents))` **does not match** a null Money record; a broader `Purchase(var buyer, var money)` branch can accept it.
- In `after`, the Purchase case matches the object, and the helper checks `money == null`.
- `default` in a pattern switch does not implicitly handle a null selector. Do not treat it as identical to the `else` of an `if (value instanceof ...)` chain.

Reviewers should request separate null tests at each level whenever the schema allows nullable components.

## 6. Reviewing Record Pattern Readability

Record patterns are helpful because the structure is visible right at the branch:

```java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

// A case in a switch:
case Line(Point(int x1, int y1), Point(int x2, int y2))
        when x2 > x1 && y2 > y1 -> "increasing";
```

However, when there are many record levels, many short variable names like `a`, `b`, `c`, and complex combined conditions, readers have to hold too much context in mind.

Review questions:

- Does the nested structure genuinely express the **core rule**, or is it just a way to grab two fields to pass to a helper?
- Which components can be null? Could the nested pattern skip values?
- Are variable names meaningful? `startX`/`endX` are often clearer than `x1`/`x2` in domains with multiple coordinates.
- Are record accessors pure, stable, and free of unexpected exceptions?
- If extracted to a helper, does the helper have a domain name rather than `handle1` or `foo`?

An alternative is to use a shallow pattern and extract:

```java
case Line(var start, var end) ->
        describeDirection(start, end);
```

`describeDirection` is an illustrative method that must be defined in the application. This approach is easier to review if the logic comparing the two points is long, though unnecessary for a simple branch.

**Do not treat a hard limit like “at most two levels of nested patterns” as a Java rule.** You can use internal guidelines and ask for justification when nesting gets deep, but the decision should still rest on domain clarity.

## 7. Reviewing `when` Guards and Purity

A guard should express **one clearly meaningful condition**:

```java
case Purchase(var buyer, Money(int cents))
        when cents >= 10_000 -> "large purchase";
```

If a guard is long, you can extract a named predicate:

```java
static boolean highValue(int cents) {
    return cents >= 10_000;
}

// An illustrative branch:
case Purchase(var buyer, Money(int cents))
        when highValue(cents) -> "large purchase";
```

However, a helper that only renames things meaninglessly like `check(int x)` does not help reviewers understand the rule.

**Avoid side effects in guards:** A guard can run and return `false`, after which Java continues checking other cases. Effects inside a guard—such as writing to a database, sending notifications, or incrementing a counter—**are not rolled back** just because that branch was not selected.

Example to reconsider:

```java
// Illustrative: auditAndCheck is a hypothetical method with side effects.
// case Purchase p when auditAndCheck(p) -> processPurchase(p);
```

Separate **pure checks** from **actions performed after branch selection**, or structure the business transaction transparently. A guard that throws an exception will propagate that exception outward; it is not treated as `false`.

**Boolean short-circuiting:** use `&&` to guard nullable accesses:

```java
case Login(var user, boolean success)
        when success && user != null && !user.isBlank() ->
        "valid login";
```

When `user == null`, `isBlank()` is not called. Using `||` or reordering conditions without understanding them can cause a `NullPointerException` or change the meaning.

## 8. Reviewing Flow Scoping, Variable Naming, and Formatting

### 8.1. Flow Scoping

In `if`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

`text` is in scope on the right-hand side of `&&` and inside the `if` body because the compiler knows the pattern matched.

Incorrect:

```java
// DOES NOT COMPILE:
// if (value instanceof String text || !text.isBlank()) {
//     System.out.println(text);
// }
```

If the left side of `||` is false, the right side can run while `text` is unbound. Reviewers should not suggest “combining conditions onto one line” if doing so breaks flow scoping.

In `switch`, pattern variables are scoped to their corresponding guard and branch body; do not assume the name holds a value across other branches.

### 8.2. Variable Naming and Visual Layout

Prefer names that reflect the domain:

```java
// Hard to read:
case Purchase(var x, Money(int n)) when n > 0 -> ...;

// More self-descriptive:
case Purchase(var buyer, Money(int cents)) when cents > 0 -> ...;
```

Here `...` simply indicates an omitted branch body for illustration, **not standalone compilable code**.

Keep formatting consistent: long `case` labels can wrap at the break between the pattern and the guard; complex expressions belong in a block or helper. For reviews, prefer diffs that highlight **rule changes** rather than unrelated reformatting.

## 9. Reviewing Switch Expressions vs. Switch Statements

Use a **switch expression** when the goal is to return a value:

```java
String label = switch (value) {
    case String text -> "TEXT:" + text;
    case Integer n -> "INT:" + n;
    case null -> "NULL";
    default -> "OTHER";
};
```

For multi-statement branches, use `yield` to provide the value:

```java
String label = switch (value) {
    case String text -> {
        String normalized = text.strip();
        yield normalized.isEmpty() ? "EMPTY" : normalized;
    }
    case null -> "NULL";
    default -> "OTHER";
};
```

Use a **switch statement** when the goal is an action, such as invoking a handler or logging:

```java
switch (value) {
    case String text -> processText(text);
    case Integer n -> processNumber(n);
    case null -> handleNull();
    default -> handleUnknown(value);
}
```

This statement snippet is **illustrative**: `processText`, `processNumber`, `handleNull`, and `handleUnknown` must be defined when used in a real program.

Reviewers should ask: is an expression hiding multiple side effects just to return a dummy value, or is a statement discarding a needed value? Neither `->` form falls through to the next branch, but only a switch expression requires producing an appropriate result on normal completion paths.

## 10. Reviewing Runtime Safety and Exception Behavior

### 10.1. Record Accessors and Side Effects

Record patterns extract components via accessors. If a record defines a custom accessor with side effects, attempting to match the pattern can trigger effects **before** the guard or case body runs.

```java
record Token(String text) {
    @Override
    public String text() {
        System.out.println("accessed");
        return text;
    }
}
```

When using `case Token(var body) -> ...`, the accessor may be invoked to bind `body`. With multiple patterns, do not rely on how many times an accessor is called. Reviewers should prefer simple, deterministic accessors, and pay special attention if a refactor changes where deconstruction happens.

### 10.2. Selector Static Type and Generic Type Erasure

Java 21 allows reference types as `switch` selectors, but not every arbitrary pattern can be applied:

```java
Number number = 5;

// DOES NOT COMPILE: Number cannot match String.
// switch (number) {
//     case String s -> System.out.println(s);
//     default -> {}
// }
```

With generics, do not use a pattern like `List<String>` to “prove” the element type from `Object`. Type argument information is typically erased at runtime; a `List<?>` pattern only confirms the object is a `List`, not that its elements are all `String`.

### 10.3. Do Not Arbitrarily Change Exceptions or Fallbacks

Replacing an unconditional cast with `instanceof` plus a fallback can turn a `ClassCastException`/`NullPointerException` into `"unknown"`. That is a **behavior change**, not a pure readability refactor. Clarify the caller's contract, expected errors, and legacy data behavior before recommending it.

If logic handles multiple subtypes through an open interface, a `default` may be necessary. If the domain is sealed, do not use `default` just to mask an unexamined case.

## 11. How to Write Helpful Code Review Comments

Instead of commenting “too many patterns, split it” or “pattern is hard to read,” state **context, risk, and a verification suggestion**.

**Example 1 — Branch ordering:**

> The `case Text` branch also covers `UrgentText`, but `UrgentText` has its own priority rule. Could we place the specific branch first and add an `UrgentText` input test to prevent regression?

**Example 2 — Guard with side effects:**

> `auditAndCheck` writes data even when it returns `false`. If this case is not selected, the audit record still remains. Can we separate the check predicate from the action executed inside the chosen branch?

**Example 3 — Null in nested record:**

> `Purchase(var buyer, Money(int cents))` does not match when `money == null`. Does the domain allow this case? Which fallback branch will receive it, and is there a test for it?

**Example 4 — Sealed exhaustive switch:**

> `Event` is sealed and we have listed all current variants. Is `default` required by the contract, or should we remove it so the compiler reminds us to update this when a new subtype is added?

**Example 5 — Method purpose:**

> This `switch` both classifies events and processes payments. Could we keep the switch dispatching by event and move payment rules into separately named and tested `describePurchase`/`processPurchase` methods?

A good comment helps the author understand *why* an adjustment is needed, rather than forcing everyone to follow personal formatting preferences.

## 12. Checklist Before Approving Pattern Matching

### A. Clarity of Intent
- [ ] Does the method have a single clear purpose and an appropriate name?
- [ ] Looking at each `case`, is it clear which data type and action are selected?
- [ ] Do pattern variable names carry domain meaning, avoiding `x`/`v`/`tmp` in complex branches?

### B. Ordering and Completeness
- [ ] Do subtypes appear before parent types when policies differ?
- [ ] Do overlapping guards have clear precedence and boundary tests?
- [ ] Do unguarded/fallback branches handle remaining values without hiding errors?
- [ ] Does a sealed switch preserve exhaustiveness checking without an unnecessary `default`?

### C. Structure and Scope
- [ ] Do nested record patterns improve readability compared to extracting to a helper?
- [ ] Are nullable components handled at the right level?
- [ ] Are pattern variables used only where the compiler guarantees binding, and are `&&`/`||` aligned with intent?

### D. Runtime and Testing
- [ ] Are guards and accessors free of unexpected side effects, I/O, or exceptions?
- [ ] Does `case null` match the existing contract?
- [ ] Are there tests for subtypes, boundary values, null, unknown, exceptions, and important side effects?
- [ ] Does the refactor only change structure, or does it also change semantics? If behavior changed, has it been confirmed?
- [ ] Is the diff easy to review, avoiding mixing reformatting with large domain changes?

### E. Final Decision

- **Keep as-is** when a multi-branch `switch` still describes a transparent classification table and is well tested.
- **Extract helpers/predicates** when each group has its own policy, or when long guards or nested patterns force reviewers to hold too much context.
- **Consider polymorphism** when the behavior truly belongs to the types and those types are owned by the module; avoid stuffing unrelated logic into domain models.
- **Pause large refactors** if you do not yet understand the hierarchy, null contract, side effects, or fallback behavior. Write characterization tests before changing code.

**Conclusion:** Reviewing pattern matching readability is reviewing **how decisions are presented**. A clean `case` block should show **what data matches, which conditions matter, which branch takes priority, and what happens when nothing matches**. Do not use line count or pattern count as the sole metric; prioritize domain expression, traceable logic, and a test suite that protects behavior.

### References

- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 440 — Record Patterns (Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
