# Extracting Long Guards into Predicates for Readable Pattern Matching (Java 21)

## 1. Problem: long guards obscure business intent

In pattern matching for `switch`, a **guard** is a boolean condition following the `when` keyword. The guard is evaluated only after the preceding pattern matches, allowing you to split a data type into more specific cases.

Consider a customer record:

```java
record Customer(String name, int age, List<String> tags) {}
```

A branch might be written as:

```java
case Customer(var name, var age, var tags)
        when name != null && !name.isBlank()
                && age >= 18 && tags != null
                && tags.contains("ACTIVE") ->
        "approved:" + name.trim();
```

Syntactically, this snippet is valid in a Java 21 `switch` when `List` is imported. However, the reader has to mentally interpret each `null` check, `isBlank`, age, and tag to understand the **approval condition**. As more conditions are added, the `case` clause can become longer than the action to be performed.

The solution is to **extract the long guard expression into one or more predicates with names that convey business meaning**:

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

In this lesson, *predicate* primarily means **a check that returns `boolean`**. It can be implemented as a `static boolean eligibleCustomer(...)` method; using the `java.util.function.Predicate<T>` interface is not required.

### Objectives

After this lesson, you will be able to:

1. Extract a long `when` clause into a clearly named boolean method without losing meaning or changing the result.
2. Know when to use a predicate that takes **individual components** versus **the entire record**.
3. Use bound pattern variables within their valid scope in `when` and in `instanceof && ...` expressions.
4. Preserve evaluation order, short-circuiting, `null` handling, and exceptions.
5. Avoid mixing business-rule changes into a refactor meant purely to improve code readability.
6. Verify before/after equivalence using a Java program and a test matrix.

**Versions:** `instanceof` pattern matching has been standard since Java 16 (JEP 394). Record patterns and pattern matching for `switch` became standard features in **Java 21** (JEP 440, JEP 441). The practice code uses JDK 21+ and does not require `--enable-preview`.

## 2. How `case Pattern when guard` works

General example:

```java
return switch (value) {
    case Customer(var name, var age, var tags)
            when eligibleCustomer(name, age, tags) ->
            "approved";
    case Customer c -> "pending";
    case null -> "null";
    default -> "other";
};
```

Execution flow:

1. Java checks whether `value` matches the record pattern `Customer(...)`.
2. If it matches, the variables `name`, `age`, and `tags` are bound from the record's components.
3. Java evaluates `eligibleCustomer(name, age, tags)`; the call must return `boolean`.
4. If it returns `true`, this branch is selected. If it returns `false`, `switch` continues checking subsequent matching `case` labels; here, `case Customer c` handles customers who are not yet eligible.
5. If the selector itself is `null`, `case null` handles it. `default` is for other object types.

The guard **does not run** when the preceding pattern does not match. Pattern variables are in scope only within the `when` condition and the selected branch; they cannot be used arbitrarily in other branches.

Key details to remember:

- `when` belongs to a **pattern `case` label** in `switch`. Do not write `value instanceof Customer c when predicate(c)`; with `instanceof`, use the boolean operator `&&`.
- `when` does not create a new pattern. It filters values that **have already matched the pattern** using an additional condition.
- A guard only accepts a `boolean`/`Boolean` result usable in a boolean context; the safest and most readable design is to return primitive `boolean`.
- Branches are evaluated in order. A broader, unguarded branch must generally be placed **after** guarded branches of the same type to avoid dominance errors.

## 3. Step-by-step safe guard extraction process

### Step 1: Choose a name based on the rule, not the syntax

A good name states **why** the condition holds:

- `eligibleCustomer(...)`, `hasAccess(...)`, `canIssueInvoice(...)`, `isWithinLimit(...)`.
- Avoid `check(...)`, `validateStuff(...)`, `condition1(...)` because they carry no information.
- If a method returns `boolean`, its name typically starts with `is`, `has`, `can`, or a state description such as `eligibleCustomer`.

The name must match the actual logic. For example, `eligibleCustomer` should not check only age if the real condition also requires an active tag.

### Step 2: Move **the entire expression** into a helper

From the original guard:

```java
when name != null && !name.isBlank()
        && age >= 18 && tags != null
        && tags.contains("ACTIVE")
```

Create:

```java
static boolean eligibleCustomer(String name, int age, List<String> tags) {
    return name != null && !name.isBlank()
            && age >= 18 && tags != null
            && tags.contains("ACTIVE");
}
```

During the refactor, **keep the exact order of operands and operators** to preserve short-circuiting. Only extract the expression; do not "while you're at it" change the age threshold, call `trim()` before comparing, add `equalsIgnoreCase`, or replace `contains` with a different rule.

### Step 3: Split into smaller predicates when there are two distinct concepts

```java
static boolean validIdentity(String name, int age) {
    return name != null && !name.isBlank() && age >= 18;
}

static boolean hasActiveTag(List<String> tags) {
    return tags != null && tags.contains("ACTIVE");
}

static boolean eligibleCustomer(String name, int age, List<String> tags) {
    return validIdentity(name, age) && hasActiveTag(tags);
}
```

This is a reasonable level of decomposition: **identity/age** and **tag status** are two concepts that can be explained, tested, and reused separately. The combination remains `&&`, in the original order.

There is no need to create a separate method for every `name != null` or `age >= 18` check if those tiny methods force the reader to jump between too many places to understand a simple rule.

### Step 4: Replace the guard without changing the pattern or branch result

Before:

```java
case Customer(var name, var age, var tags)
        when name != null && !name.isBlank()
                && age >= 18 && tags != null
                && tags.contains("ACTIVE") ->
        "approved:" + name.trim();
```

After:

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

Keep the record pattern, variables, result string, and branch order unchanged. This keeps the diff small, easy to review, and reduces the risk of changing how many times accessors are invoked. You can consider switching from a record pattern to a type pattern afterward, but that is a separate change that needs its own evaluation.

### Step 5: Prove equivalence

Run the same set of inputs through both the inline guard version and the extracted version; compare **return values**, relevant exceptions, and—if the application has side effects—the order and number of dependency calls. Do not run just one "happy path" case and conclude the refactor succeeded.

## 4. Choosing the predicate signature: components or object?

There are two particularly useful styles in Java 21.

### 4.1. Taking the bound components

```java
case Customer(var name, var age, var tags)
        when eligibleCustomer(name, age, tags) ->
        "approved:" + name.trim();
```

With this approach, the signature reflects the exact data being checked:

```java
static boolean eligibleCustomer(String name, int age, List<String> tags)
```

**Pros:** easy to unit test individual values; no need to construct a `Customer` when testing the predicate; does not force the predicate to depend on the entire record. Suitable when the logic is primarily a rule over a group of components and multiple places may supply equivalent components.

**Caveats:** when there are too many parameters, it becomes hard to tell where each parameter comes from, and easy to pass them in the wrong order if several parameters share the same type. In that case, accepting the record or a value object can be more readable.

### 4.2. Taking the record object itself

If the predicate is a rule belonging to `Customer`, you can write:

```java
static boolean eligibleCustomer(Customer c) {
    return c.name() != null && !c.name().isBlank()
            && c.age() >= 18
            && c.tags() != null
            && c.tags().contains("ACTIVE");
}
```

In `switch`:

```java
case Customer c when eligibleCustomer(c) -> "approved";
case Customer c -> "pending";
```

**Pros:** short signature, the type name helps express the business domain, easy to extend when the condition uses additional fields. Well suited for rules that primarily operate on the object as a whole.

**Caution:** the example above reads the accessors `c.name()` and `c.tags()` multiple times. For a standard record, default accessors simply return the component, but Java allows explicit accessor declarations, which can have side effects, cost, or exceptions. If the contract requires **exactly one read**, store the value in a local variable and preserve evaluation order, or keep the bound components from the record pattern. Switching from record deconstruction to a type pattern can also change when and how many times accessors are called. Evaluate that change independently from extracting the guard.

### Which one to choose?

| Criterion | Take components | Take record |
| --- | --- | --- |
| Logic uses few fields, easy to reuse elsewhere | Often suitable | May depend on the record more than necessary |
| Logic genuinely describes the object's state | Requires passing many arguments | Easy to name, preserves business meaning |
| Need to control accessor calls | Bound components can be reused | Must control accessor call count inside the helper |
| Unit testing the predicate in isolation | Pass values directly | Construct a record |
| Signature has too many arguments of the same type | Easy to mix up | Usually more concise |

There is no single right choice for every situation. Prefer **the option that clarifies behavior with the fewest changes outside the refactoring goal**.

## 5. How do a `boolean` method and `Predicate<T>` differ?

The term "predicate" has two common meanings:

1. A method returning boolean, such as `static boolean eligibleCustomer(Customer c)`.
2. An object implementing the `java.util.function.Predicate<T>` interface with a `boolean test(T value)` method, which can be passed around as a value and composed with `and`, `or`, and `negate`.

In `when`, **either works**, as long as the expression after `when` evaluates to boolean.

Method form:

```java
case Customer c when eligibleCustomer(c) -> "approved";
```

`Predicate<Customer>` object form:

```java
import java.util.function.Predicate;

private static final Predicate<Customer> ELIGIBLE =
        c -> c.name() != null && !c.name().isBlank() && c.age() >= 18;

static String status(Object input) {
    return switch (input) {
        case Customer c when ELIGIBLE.test(c) -> "approved";
        case Customer c -> "pending";
        case null -> "null";
        default -> "other";
    };
}
```

This snippet is an example placed inside a class that has `record Customer(String name, int age, ...)`, not a standalone program. `ELIGIBLE.test(c)` returns a `boolean`, whereas `ELIGIBLE` itself is just a **function object**, not a boolean.

The following **intentionally fails to compile**:

```java
case Customer c when ELIGIBLE -> "approved"; // Predicate<Customer> is not a boolean
```

If the rules need to be used in `Stream.filter(...)` or passed between classes, `Predicate<T>` is useful. If you only need to name a `switch` guard, **a `boolean` method is usually simpler and more direct**, avoiding the extra `.test(...)` syntax.

### Composing predicates with `and`/`or`

Example when you genuinely have two predicates used in multiple places:

```java
Predicate<Customer> namedAdult =
        c -> c.name() != null && !c.name().isBlank() && c.age() >= 18;
Predicate<Customer> active =
        c -> c.tags() != null && c.tags().contains("ACTIVE");
Predicate<Customer> eligible = namedAdult.and(active);
```

`eligible.test(c)` applies `namedAdult` first and evaluates `active` only if the first predicate returns `true`. `or` also short-circuits in order; `negate` inverts the boolean. Creating and composing `Predicate` instances should have a clear design reason, avoiding turning a simple guard into a hard-to-read chain of lambdas.

## 6. Short-circuiting, null, and argument evaluation: invariants you must preserve

### 6.1. Preserve null-check ordering

In the guard:

```java
when name != null && !name.isBlank()
        && tags != null && tags.contains("ACTIVE")
```

`!name.isBlank()` does not run if `name == null`. Similarly, `tags.contains(...)` does not run if `tags == null`. The extracted predicate must preserve this relationship:

```java
static boolean valid(String name, List<String> tags) {
    return name != null && !name.isBlank()
            && tags != null && tags.contains("ACTIVE");
}
```

With `Customer(var name, var age, var tags)`, reference components **can be `null`**. A record pattern using `var` can bind `null`; do not assume that matching the record guarantees all components are non-null.

Distinguish between:

- `value == null`: the selector does not match `Customer(...)`; handle with `case null` if desired.
- `new Customer(null, 20, ...)`: the outer record still matches; the `name` component binds `null` to `var`, and the predicate must handle it explicitly.
- `new Customer("", 20, ...)`: `name` is non-null but blank; the method decides whether this qualifies.

### 6.2. Java evaluates arguments before calling a method

A dangerous refactor is moving an expression with side effects into a **method argument**, causing it to run earlier. Compare:

```java
// Before: expensiveCheck() is called only if name is not null.
boolean before = name != null && expensiveCheck();

// After: NOT equivalent if expensiveCheck() has side effects,
// because Java evaluates arguments before calling isValid(...).
boolean after = isValid(name, expensiveCheck());
```

Assume `expensiveCheck()` is a method returning `boolean` and `isValid(String, boolean)` also returns boolean; this snippet illustrates **evaluation order**, not standalone runnable code. Java will call `expensiveCheck()` to obtain the second argument even when `name == null`.

**The safe approach** is to pass already-bound/already-computed variables into the helper, and keep the short-circuit logic inside:

```java
static boolean isValid(String name) {
    return name != null && expensiveCheck();
}
```

In this second illustrative example, `expensiveCheck()` is a hypothetical dependency. When refactoring real code, preserve the original context/method rather than copying this snippet as a standalone program.

### 6.3. Do not reorder conditions "for looks" without proving equivalence

In an expression consisting solely of primitive values and pure functions, reordering `&&` may preserve the boolean result. However, with getters that have side effects, mutable `List`s, `Clock`, I/O, logging, or methods that throw exceptions, **evaluation order is part of the behavior**.

For example:

```java
tags != null && tags.contains("ACTIVE") && auditAllowed()
```

is not automatically equivalent to:

```java
auditAllowed() && tags != null && tags.contains("ACTIVE")
```

If `auditAllowed()` writes logs, recomputes a cache, or can throw an error, the two versions can behave differently. Even when the boolean result is the same, differences in side effects still matter.

## 7. Predicates should be pure and unsurprising

An ideal **pure predicate** only reads its inputs and returns a `boolean`, without mutating state, calling external systems, emitting business logs, or reading/altering time. For `switch` guards, purity ensures:

- Predictable results that are easy to test.
- Multiple evaluations are far less risky.
- The method name genuinely describes a question about data, without hiding actions.
- No unexpected exceptions or latency when a value matches a pattern.

Good example:

```java
static boolean canIssueInvoice(
        String currency, BigDecimal total, boolean paid) {
    return currency != null && !currency.isBlank()
            && total != null && total.signum() > 0 && paid;
}
```

The method checks a property of the invoice; it does not actually issue the invoice, charge money, or write data. **The `can` prefix**, rather than `issueInvoice`, reflects that the result is only a condition for performing another operation.

**Avoid:**

```java
// Should not be used directly as a guard if the method performs external operations.
case Invoice invoice when chargeCardAndUpdateDatabase(invoice) -> "ready";
```

The snippet above illustrates syntax in a `switch` with a hypothetical helper. If a guard has side effects, failures or thrown exceptions can alter branch selection flow and create behavior that is hard to trace. When an external service call is needed, it is usually better to perform it in an explicit orchestration step and pass the controlled result to the classification logic.

**Important note:** `when` is invoked when the pattern matches that label; if the guard returns `false`, `switch` can evaluate subsequent branches. Do not rely on the compiler "automatically caching" results across guards that look similar. When the same predicate appears in multiple branches, consider its cost and side effects; if it must be evaluated exactly once, structure the control flow to store the result at an appropriate point.

## 8. Placing predicates in the right position in case order

Consider a classification with three customer branches:

```java
return switch (value) {
    case Customer(var name, var age, var tags)
            when eligibleCustomer(name, age, tags) -> "approved";
    case Customer(var name, var age, var tags)
            when age < 18 -> "underage";
    case Customer c -> "pending";
    case null -> "null";
    default -> "other";
};
```

The order here means:

1. If it is a `Customer` and eligible, select `approved`.
2. If the first guard is false and the person is under 18, select `underage`.
3. All remaining `Customer` instances select `pending`.
4. `null` and other types have their own fallbacks.

Do not place `case Customer c -> "pending"` earlier. An **unguarded** general pattern dominates subsequent customer branches, causing the compiler to report a dominance error.

Extracting a long guard into a boolean helper **is not a reason to change the order of cases**. If you need to reprioritize classification, that is a separate business behavior change that requires tests and review.

### Do not confuse a `false` guard with an `if`'s `else` branch

In `switch`, when `case Customer(...) when predicate(...)` matches the pattern but the predicate returns `false`, the runtime continues checking other labels. If you move the predicate logic **into the body of a general case** and return `pending` immediately, you may skip subsequent cases that use different guards, such as `underage`. The two structures are equivalent only if you have proven all remaining branches produce the same result.

### Normal guards and dominance

A branch with `when somePredicate(...)` before an unguarded branch of the same type is valid. The compiler **does not infer the semantics of a predicate helper** to prove it is always true. However, a guard that is a constant `true` in source code receives special dominance treatment, almost like an unguarded branch. Do not replace `when predicate(...)` with `when true` to "reduce complexity" when you still need classification branches below it.

## 9. Complete Java 21 example: refactoring and parity testing

Create the file **`GuardPredicateDemo.java`**. This example keeps two methods side by side:

- `before(...)`: long guards written directly inside `when`.
- `after(...)`: guards replaced with named predicates, keeping branch order and results unchanged.

The program also includes `compact(...)` to demonstrate switching to `case Customer c when ...` when you want to pass the entire record's data via accessors.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;

public class GuardPredicateDemo {
    record Customer(String name, int age, List<String> tags) {}
    record Invoice(String currency, BigDecimal total, boolean paid) {}

    static String before(Object value) {
        return switch (value) {
            case Customer(var name, var age, var tags)
                    when name != null && !name.isBlank()
                            && age >= 18 && tags != null
                            && tags.contains("ACTIVE") ->
                    "approved:" + name.trim();
            case Customer(var name, var age, var tags) when age < 18 ->
                    "underage";
            case Customer c -> "pending";
            case Invoice(var currency, var total, var paid)
                    when currency != null && !currency.isBlank()
                            && total != null && total.signum() > 0 && paid ->
                    "invoice:" + currency.toUpperCase(Locale.ROOT);
            case Invoice i -> "invoice-held";
            case null -> "null";
            default -> "other";
        };
    }

    static boolean validIdentity(String name, int age) {
        return name != null && !name.isBlank() && age >= 18;
    }

    static boolean hasActiveTag(List<String> tags) {
        return tags != null && tags.contains("ACTIVE");
    }

    static boolean eligibleCustomer(String name, int age, List<String> tags) {
        return validIdentity(name, age) && hasActiveTag(tags);
    }

    static boolean canIssueInvoice(
            String currency, BigDecimal total, boolean paid) {
        return currency != null && !currency.isBlank()
                && total != null && total.signum() > 0 && paid;
    }

    static String after(Object value) {
        return switch (value) {
            case Customer(var name, var age, var tags)
                    when eligibleCustomer(name, age, tags) ->
                    "approved:" + name.trim();
            case Customer(var name, var age, var tags) when age < 18 ->
                    "underage";
            case Customer c -> "pending";
            case Invoice(var currency, var total, var paid)
                    when canIssueInvoice(currency, total, paid) ->
                    "invoice:" + currency.toUpperCase(Locale.ROOT);
            case Invoice i -> "invoice-held";
            case null -> "null";
            default -> "other";
        };
    }

    static String compact(Object value) {
        return switch (value) {
            case Customer c when eligibleCustomer(c.name(), c.age(), c.tags()) ->
                    "approved";
            case Customer c -> "pending";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
            new Customer(" Linh ", 20, List.of("ACTIVE")),
            new Customer("Mai", 17, List.of("ACTIVE")),
            new Customer("", 22, List.of("ACTIVE")),
            new Customer("Ha", 22, List.of("GUEST")),
            new Customer(null, 22, List.of("ACTIVE")),
            new Customer("Long", 22, null),
            new Invoice("usd", new BigDecimal("120.00"), true),
            new Invoice("eur", BigDecimal.ZERO, true),
            new Invoice(null, BigDecimal.ONE, true),
            new Invoice("vnd", new BigDecimal("30"), false),
            null,
            123
        };
        for (Object value : samples) {
            String expected = before(value);
            String actual = after(value);
            if (!expected.equals(actual)) {
                throw new AssertionError("mismatch: " + value);
            }
            System.out.println(actual);
        }
        System.out.println("PARITY PASS: " + samples.length);
        System.out.println("compact: " +
                compact(new Customer(" Hoa ", 30, List.of("ACTIVE"))));
    }
}
```

Use JDK 21 or later:

```bash
javac --release 21 GuardPredicateDemo.java
java GuardPredicateDemo
```

**Exact output:**

```text
approved:Linh
underage
pending
pending
pending
pending
invoice:USD
invoice-held
invoice-held
invoice-held
null
other
PARITY PASS: 12
compact: approved
```

### Result analysis

- `approved:Linh`: name has leading/trailing whitespace but is not blank, customer is of age, and has the `ACTIVE` tag; both the inline and predicate versions agree.
- `underage`: the eligibility branch returns `false` because age is under 18; `switch` tries the next `when age < 18` branch.
- The four `pending` cases show that a blank name, missing `ACTIVE` tag, `null` name, and `null` tag list are all handled without throwing `NullPointerException`.
- `invoice:USD`: the invoice has a currency, positive amount, and is paid; the invoice predicate has no side effects. `toUpperCase(Locale.ROOT)` runs only in the branch that matched and whose guard returned `true`.
- The three `invoice-held` cases: total is zero, currency is `null`, or `paid == false`.
- `null` and `other`: a `null` selector is handled explicitly, while types other than `Customer` or `Invoice` fall into `default`.
- The `PARITY PASS: 12` line appears after comparing results across **12 inputs** between the two implementations; if any differed, the program would throw `AssertionError` instead of reporting a pass.
- `compact: approved` illustrates using the type pattern `Customer c` and calling the helper with components retrieved via accessors.

**Limitations of the example:** 12 samples prove equivalence for those exact tested cases, not for every possible production state. If a record has custom accessors, mutable objects, or I/O-related logic, add tests based on risk.

## 10. Extracting guards in `instanceof` and other expressions

Beyond pattern `switch`, naming predicates is also useful with `instanceof`:

```java
if (value instanceof Customer(var name, var age, var tags)
        && eligibleCustomer(name, age, tags)) {
    System.out.println("approved");
}
```

This illustrates code inside a method that already has `value` and a `Customer` declaration. The right-hand side of `&&` is evaluated only when the pattern matches and `name`, `age`, and `tags` are bound.

Do not write:

```java
// INTENTIONALLY WRONG: when is not valid syntax for instanceof.
if (value instanceof Customer c when eligibleCustomer(c)) {
    // ...
}
```

Predicates can also be reused in the ternary operator:

```java
return value instanceof Customer(var name, var age, var tags)
        && eligibleCustomer(name, age, tags)
        ? "approved" : "pending";
```

The `return` example above is in the context of a method returning `String`. If there are many branches for different types, a `switch` expression with `when` is usually clearer than multiple nested ternary operators.

**Semantic difference:** `instanceof` returns `false` for `null` input; in a pattern `switch`, a `null` selector typically needs `case null` to return a result rather than throwing `NullPointerException`. When converting between `if` and `switch` to improve readability, always re-verify `null` behavior.

## 11. Unit testing predicates and checking before/after behavior

Small predicates have the advantage of being testable in isolation, but isolated tests **do not replace** tests on the full `switch`. You should test both:

| Category | Representative input | Expectation |
| --- | --- | --- |
| Valid customer match | Non-blank name, age 18+, `ACTIVE` tag | Predicate `true`; `approved` branch |
| `null` or blank name | `null`, `""`, `"  "` | Predicate `false`; no NPE thrown |
| Boundary age | 17, 18, 19 | 17 fails; 18 and above depend on other criteria |
| Missing tags | `null`, empty list, list without `ACTIVE` | Predicate `false` |
| Invoice missing data | `currency == null` or `total == null` | `false`, no method calls on `null` |
| Invoice amount | negative, 0, positive | Only positive can pass the guard |
| Unpaid invoice | `paid == false` | `false` |
| Other input types | `Integer`, `String` | Customer/Invoice predicates not called; `default` branch |
| `null` selector | `null` | `case null` branch per contract |
| Overlapping guards | Ineligible customer under 18 | `underage` branch must be selected after earlier guard returns `false` |
| Custom accessor/side effect | Record with accessor counting calls | No change in read count or order if required by contract |

### Parity testing

A practical approach is to keep the inline logic as a temporary baseline in tests, run the same list of inputs through both versions, and compare:

1. **Return values** and selected branches.
2. **Exception types and conditions** for invalid/missing inputs.
3. **Order and count of calls** to dependencies or accessors with side effects.
4. **Mutable data** to ensure it is not modified differently.

When results differ, do not adjust the expected output just to make the test pass. Identify the cause: did condition order, argument passing, `null` checks, or branch priority change?

Tests should include cases where **the guard returns `true`**, **the guard returns `false`**, **the pattern does not match**, **the selector is `null`**, as well as boundary values. If the application uses Maven/Gradle, include the test suite in CI with the project's actual Java configuration.

## 12. Review guide and refactoring completion criteria

A pull request that extracts long guards should be easy to evaluate using these questions:

- [ ] Does the predicate name describe **the business rule**, rather than vague details like `condition1`?
- [ ] Does the condition moved into the helper **preserve the exact meaning**, without changing thresholds, formatting, or broadening permissions?
- [ ] Are the pattern, case order, branch results, and `null` handling preserved?
- [ ] Are short-circuiting and evaluation order preserved? Was any expression with side effects turned into an **eagerly evaluated argument**?
- [ ] Are pattern variables in `when`/`&&` always within valid scope?
- [ ] Do null checks appear before any dereference that could cause an NPE?
- [ ] Does the predicate avoid hiding data writes, I/O, or unexpected exceptions?
- [ ] Is the helper signature appropriate (components or record), avoiding too many parameters of the same type and avoiding redundant accessor reads?
- [ ] Are there no dominated branches, and are false-guard cases still handled by subsequent cases as before?
- [ ] Is the predicate unit-tested at key boundaries, and does the entire switch have regression/differential tests?
- [ ] Does it build on the target Java version, with formatter, static checks, and relevant CI passing?
- [ ] Is the diff clean, without mixing in new logic outside the "improve readability" scope?

**Definition of DONE:** A reviewer can look at `case ... when eligibleCustomer(...)` and immediately understand the intent, open the helper to see a well-named/well-split rule, and have evidence that the refactored code returns the same results for all cases in the contract.

### When is it *not* necessary to extract a guard?

A short, self-explanatory guard such as `when x == y` in `case Point(var x, var y)` is usually already clear. Creating `isSameCoordinate(x, y)` just to hide a simple comparison can make code **harder to read**. Extract when the logic is sufficiently long, repeated in multiple places, has a natural domain name, or needs independent unit testing.

Do not use a fixed line count as a mechanical rule. More important criteria are **readability, consistency, and testability**.

## 13. Common mistakes

### Mistake 1: Extracting but only renaming superficially

`checkAllConditions(name, age, tags)` adds very little information. If the domain calls this state an "eligible customer", `eligibleCustomer(...)` lets the reader immediately see the intended meaning.

### Mistake 2: Helper returns `void` or an object instead of boolean

`when` requires a boolean expression; you cannot call a `void` helper or place a raw `Predicate<Customer>` after `when`. When using `Predicate<T>`, you must call `.test(value)`.

### Mistake 3: Changing evaluation timing via argument passing

Turning `name != null && expensiveCheck()` into `isValid(name, expensiveCheck())` causes `expensiveCheck()` to run before the helper performs the null check. This is not a behavior-preserving refactor.

### Mistake 4: Moving a helper with side effects out of the guard

If you change `when expensivePredicate(value)` into precomputing `boolean ok = expensivePredicate(value)` before the `switch`, the helper may be called **even when the pattern does not match**. This changes cost, exceptions, or logs. Evaluate carefully rather than assuming equivalence.

### Mistake 5: Mixing record type patterns and deconstruction without checking

`case Customer c` and `case Customer(var name, var age, var tags)` differ in how they retrieve components. If accessors are overridden, switching between the two forms can affect call counts and exceptions. For a pure guard refactor, keeping the original pattern is the safer choice.

### Mistake 6: Placing a general branch before a guarded branch

`case Customer c -> ...` before `case Customer c when eligibleCustomer(c) -> ...` shadows the second branch and causes a compiler dominance error. More specific branches must come before more general ones.

### Mistake 7: Having a predicate method perform business actions

A method named `canIssueInvoice` should return boolean, not process payments, write to a database, or send emails. Guards are meant for **classification/decision-making**, not for hiding hard-to-reverse actions.

### Mistake 8: Testing only the predicate and ignoring the full switch behavior

A predicate may be correct in isolation, while the switch result also depends on **pattern matching, case order, other guards, and null/default**. You must test the method containing the switch as a whole.

## 14. Self-check questions

**1. Why is `when eligibleCustomer(name, age, tags)` usually more readable than a long `&&` chain?**  
Because the method name reveals the business intent; readers can inspect the details in the helper when needed.

**2. Is it required to declare a `Predicate<Customer>` to extract a guard?**  
No. A `static boolean eligibleCustomer(...)` method is sufficient and usually simpler.

**3. With `case Customer(var name, var age, var tags) when ...`, when is the guard called?**  
Only after the record pattern matches and the variables have been bound.

**4. Why does `case Customer c when ELIGIBLE` fail to compile if `ELIGIBLE` has type `Predicate<Customer>`?**  
Because a `Predicate` object is not a boolean; you must use `ELIGIBLE.test(c)`.

**5. When `name == null`, is it safe if a predicate writes `name != null && !name.isBlank()`?**  
Yes; `&&` short-circuits and skips the right-hand side when the left-hand side is false.

**6. Why can passing `expensiveCheck()` as a helper argument change behavior?**  
Java evaluates arguments before invoking the method; the expensive call may run even though the null check inside the helper would return `false`.

**7. If the first guard returns `false`, can `switch` enter a later unguarded `case` for the same record?**  
Yes. That is how you build specific classification branches followed by a general fallback.

**8. For a guard that is just `when x == y`, should you always extract it into `same(x, y)`?**  
No. Short and clear guards can stay inline; extract only when it improves readability or testability.

**9. Does getting identical results from the refactored version on 12 test cases prove complete equivalence?**  
No. Other paths, boundary data, exceptions, and side effects may still remain untested.

**10. Why should predicates be pure and avoid mutating state?**  
It makes guards predictable, reusable, and easy to test, while avoiding side effects that depend on case evaluation order.

## References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 API — java.util.function.Predicate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Predicate.html)
- [JLS SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
