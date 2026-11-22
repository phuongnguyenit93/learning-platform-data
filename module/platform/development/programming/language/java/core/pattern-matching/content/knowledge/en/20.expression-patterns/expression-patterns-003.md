# Computing Values from Pattern Switch in Java 21

## 1. Goal: Using Pattern Matching to Produce a Value

When an input expression can belong to multiple data types, we often want to **compute a single value** based on the type and contents of the input: a result description string, a score, a processing fee, a display status, or output data for an API. Since Java 21, **pattern matching for `switch`** is a standard feature (JEP 441), allowing **type patterns**, **record patterns**, and `when` guards in each `case` branch. When written as a **`switch expression`**, the entire `switch` evaluates to a value.

A short example with `Object input`:

```java
String message = switch (input) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Unsupported";
};
```

Reading the example: if `input` is a string, the variable `text` is bound to that string and the branch returns `"Text: " + text`; if it is an `Integer`, the second branch produces a different string. The `switch` expression has type `String`, so it can be assigned to `message`.

Goals of this lesson:

- Distinguish between a `switch expression` (computing a value) and a `switch statement` (executing statements).
- Use `case Type variable`, `case Record(...)`, and `when` to choose how to compute a value.
- Understand `->`, blocks with `yield`, result types, **exhaustiveness** requirements, and how `null` is handled.
- Avoid common compiler errors: branches that do not produce a value, missing cases, dominated branches, and misplaced `return`/`break`.
- Build standalone, runnable Java 21+ functions and accurately predict their output.

The main examples use **JDK 21+**, because record patterns were also standardized in Java 21 (JEP 440). There is no need to enable `--enable-preview`.

## 2. Value-Computing Syntax: `case ... -> value`

Common pattern:

```java
ResultType result = switch (selector) {
    case PatternA -> expressionA;
    case PatternB when condition -> expressionB;
    case null -> expressionForNull;
    default -> fallbackExpression;
};
```

Where:

1. `selector` is the input expression, such as a variable of type `Object` or an interface.
2. `PatternA` and `PatternB` attempt to match the input type/structure and can declare pattern variables.
3. `when condition` is an additional condition checked **after the pattern matches**; the condition can use the newly bound variables.
4. The part after `->` computes the branch's value. For a single-expression branch, Java takes that value directly as the result of the `switch expression`.
5. The `;` after `}` terminates the assignment or `return` statement containing the `switch` expression.

Example computing an integer value:

```java
// Placed inside a method with an Object value variable.
int score = switch (value) {
    case Integer n when n > 10 -> n * 2;
    case Integer n -> n;
    case String s -> s.trim().length();
    case null -> 0;
    default -> -1;
};
```

At any given time, only **one branch is selected**. If `value == 12`, the branch with `when n > 10` returns `24`; if `value == 8`, the next `Integer` branch returns `8`; if it is `"  Java  "`, the `String` branch returns `4`. Arrow (`->`) branches do not fall through to subsequent branches.

Unlike a `switch` statement used to execute actions, a `switch expression` **must produce a result for every normal execution path**. A `throw` branch that terminates with an exception is also valid because no normal control flow exits that branch.

## 3. Returning Results with `return switch (...)`

You can return the value of a `switch expression` directly from a method:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "text(" + s.length() + ")";
        case Integer n -> "integer(" + n + ")";
        default -> "other";
    };
}
```

The `return` here belongs to the **`describe` method**. To the right of `return` is **a `switch` expression**, and the value of that expression is the return value of the method.

Do not confuse this with the following:

```java
// Demonstrates a switch STATEMENT, not a switch expression.
static String describeStatement(Object value) {
    switch (value) {
        case String s -> {
            return "text(" + s.length() + ")";
        }
        default -> {
            return "other";
        }
    }
}
```

In the second example, `switch` is a **statement** because it is used as a standalone statement; the `return` statements inside each branch exit the method directly. Both approaches work, but `return switch (...) { ... };` usually expresses the intent of mapping an input to a single value more clearly and avoids repeating `return`.

## 4. A Branch with Multiple Statements: Using `yield`

When computing a value requires multiple steps (validation, intermediate calculation, formatting), place the statements in a block `{ ... }` and use **`yield`**:

```java
// Snippet inside a method returning int.
return switch (value) {
    case String text -> {
        String normalized = text.trim();
        int length = normalized.length();
        yield length;
    }
    case Integer number -> number;
    default -> 0;
};
```

`yield length;` tells Java that **the value of this `switch expression` branch is `length`**. It ends evaluation of the branch and passes the value out of the `switch`. `yield` differs from `return`: `yield` returns a value to the `switch` expression, whereas `return` returns a value to the enclosing method.

For a `switch expression`:

- `case ... -> expression;` is suitable when the computation is simple.
- `case ... -> { ...; yield expression; }` is suitable when a multi-statement block is needed.
- `case ... -> throw new IllegalArgumentException(...);` is valid when that case must fail.
- Do not use `break 10;` to return a value; the syntax for producing a value is `yield 10;`.
- A branch block cannot complete normally without producing a value. If multiple execution paths are needed, each ending path must `yield` or `throw` accordingly.

With the older colon syntax, a `switch expression` also uses `yield` to produce a value:

```java
int length = switch (value) {
    case String s:
        yield s.length();
    default:
        yield 0;
};
```

However, the `->` syntax is usually easier to read when handling patterns and avoids confusion with fall-through in the older `switch statement` style.

## 5. Type Patterns and `when`: Computing Values by Type and Condition

The pattern `case Integer n` both checks whether the selector matches `Integer` and declares the variable `n` for the computation. A `when` guard adds an extra condition:

```java
static int adjust(Object input) {
    return switch (input) {
        case Integer n when n >= 100 -> n + 10;
        case Integer n when n >= 0 -> n;
        case Integer n -> 0;
        case null -> 0;
        default -> -1;
    };
}
```

The branch order is meaningful:

1. `Integer` 100 or greater: add 10.
2. Non-negative `Integer` less than 100: keep unchanged.
3. Negative `Integer`: return 0.
4. `null` selector: return 0.
5. Unsupported type: return -1.

`when` guards are evaluated after their corresponding pattern matches. If `n >= 100` is false, Java can try the next branch. The variable `n` in each branch is scoped only to that branch's guard and body, not as a single shared variable for the entire method.

**Narrower branches must be placed before broader ones.** If you put `case Integer n -> n;` first and then `case Integer n when n >= 100 -> ...;`, the guarded branch is shadowed by the broader branch; the compiler will report a **dominated case label** error.

Avoid performing complex side effects inside `when` conditions. The primary purpose of a guard is to clearly state which condition belongs to the branch computing the value.

## 6. Record Patterns: Extracting Components and Producing a Value

Java 21 allows the pattern `case RecordType(componentPatterns...)`. It checks the record and deconstructs its components right in the `case` branch:

```java
record Item(String sku, int quantity) {}

// Placed inside a method taking Object value and returning String.
return switch (value) {
    case Item(String sku, int quantity) when quantity > 0
            -> sku + " x " + quantity;
    case Item(var sku, var quantity) -> "empty item " + sku;
    case null -> "missing item";
    default -> "unsupported";
};
```

If the selector is `new Item("BK-1", 3)`, the result is `"BK-1 x 3"`. Record patterns let us compute a string from `sku` and `quantity` without needing to call `item.sku()`/`item.quantity()` after matching.

A record pattern must have the **exact number of components in the exact order** of the record declaration. For `record Item(String sku, int quantity)`, `Item(var sku)` is invalid because a component is missing. You can use `var` for type inference in the pattern, or write `String sku`/`int quantity` explicitly. A record pattern only matches when the record value at that position is non-`null` and the requested sub-structure matches; extracting components with `var` does not guarantee that every component is non-`null`.

Example with nested records:

```java
record Address(String city) {}
record User(String id, Address address) {}

static String destination(Object input) {
    return switch (input) {
        case User(var id, Address(var city)) when city != null -> id + "@" + city;
        case User(var id, var address) -> "No city for " + id;
        case null -> "Missing user";
        default -> "Unsupported";
    };
}
```

In the first branch, `Address(...)` is a record pattern nested inside `User(...)`, so both the user and the address must match. The guard `city != null` checks the string component. The second `User(...)` branch still catches users with `address == null` or a blank/null city depending on the contents, returning a different message.

## 7. Exhaustiveness of a `switch` Expression

Because a `switch expression` must produce a value on every normal execution path, the compiler requires the branches to **exhaustively cover all possible cases** according to the static type of the selector.

### `Object` Selector: Usually Requires `default`

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "S:" + s;
        case Integer n -> "I:" + n;
        case null -> "null";
        default -> "other";
    };
}
```

`Object` can hold countless types other than `String` and `Integer`, so a `default` branch is required. Without `default`, the compiler cannot prove that every value has a branch returning a result.

### Sealed Hierarchy Selector: May Not Need `default`

With a `sealed interface` whose direct subtypes are fully known to the compiler, pattern `case` branches can cover all subtypes:

```java
sealed interface Payment permits Approved, Declined {}
record Approved(String id, int cents) implements Payment {}
record Declined(int code, String reason) implements Payment {}

static String summarize(Payment payment) {
    return switch (payment) {
        case null -> "Missing payment";
        case Approved(var id, var cents) when cents >= 10000
                -> "large " + id;
        case Approved(var id, var cents) -> "regular " + id;
        case Declined(var code, var reason) -> "declined " + code;
    };
}
```

The `Approved` cases are covered by two branches (the guarded branch and the remaining branch), `Declined` has one branch, and `null` has its own branch. Therefore, the `switch expression` is exhaustive even without `default`. As a result, if the hierarchy is modified in the source code to add another permitted subtype, the compiler can require updating the switch to maintain exhaustiveness.

**Note:** `when` makes a branch conditional. Having only `case Approved(var id, var cents) when cents >= 10000` does not cover all `Approved` instances. You must add an unguarded `Approved` branch (or an appropriate catch-all branch).

### `null` and Exhaustiveness Are Two Separate Concerns

A `case null` catches a `null` selector. Do not assume `default` always handles `null`: when a reference-typed `switch` selector is `null` and there is no matching `null` case, Java throws a `NullPointerException`. If `null` is a valid input in your application, write `case null -> ...` explicitly or check for it before switching.

If you do not want to return a value when the input is `null`, a branch like `case null -> throw new IllegalArgumentException("Missing input");` is also valid.

## 8. Complete Java 21 Example: Returning Strings and Numbers from Pattern Switch

Create a file named **`PatternSwitchValueDemo.java`** as follows:

```java
public class PatternSwitchValueDemo {
    sealed interface Payment permits Approved, Declined {}
    record Approved(String id, int cents) implements Payment {}
    record Declined(int code, String reason) implements Payment {}

    static String summarize(Payment payment) {
        return switch (payment) {
            case null -> "Missing payment";
            case Approved(String id, int cents) when cents >= 10000 -> {
                String tier = "large";
                yield id + ":" + tier + ":" + cents;
            }
            case Approved(String id, int cents) -> id + ":regular:" + cents;
            case Declined(int code, String reason) -> "declined:" + code + ":" + reason;
        };
    }

    static int score(Object value) {
        return switch (value) {
            case null -> 0;
            case Integer n when n > 10 -> n * 2;
            case Integer n -> n;
            case String s -> {
                int trimmedLength = s.trim().length();
                yield trimmedLength;
            }
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(summarize(new Approved("A1", 12000)));
        System.out.println(summarize(new Approved("A2", 5000)));
        System.out.println(summarize(new Declined(403, "blocked")));
        System.out.println(summarize(null));
        System.out.println(score(12));
        System.out.println(score(8));
        System.out.println(score("  Java  "));
        System.out.println(score(new Object()));
        System.out.println(score(null));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 PatternSwitchValueDemo.java
java PatternSwitchValueDemo
```

Exact output:

```text
A1:large:12000
A2:regular:5000
declined:403:blocked
Missing payment
24
8
4
-1
0
```

**Why does it produce this output?**

- `Approved("A1", 12000)` matches the `Approved` record and exceeds the `10000` threshold, so it enters the `when` branch. The block declares `tier` and yields `"A1:large:12000"`.
- `Approved("A2", 5000)` still matches `Approved` but fails the guard, so it enters the second `Approved` branch and returns `"A2:regular:5000"`.
- `Declined(403, "blocked")` matches `Declined` and returns `"declined:403:blocked"`.
- `null` in `summarize` is handled by `case null` and returns `"Missing payment"`.
- `score(12)`: the `Integer n` pattern matches, the guard `n > 10` is true, and it returns `24`. For `score(8)`, the guard is false and the unguarded `Integer` branch returns `8`.
- `score("  Java  ")`: the `String` branch computes `trimmedLength` and yields `4`.
- `new Object()`: matches neither `Integer` nor `String`, so `default` returns `-1`.
- `score(null)`: `case null` returns `0`.

The example uses **two `switch` expressions that genuinely return values**: `summarize` returns `String` and `score` returns `int`. Both are placed directly after `return`, and each branch completes with an expression, `yield`, or (in other variants) could throw an exception.

## 9. Result Type of a `switch` Expression

When assigning the result to a variable or returning it from a method, the branches must produce values **compatible with the target type context**:

```java
// Snippet assuming an Object value variable exists.
String label = switch (value) {
    case Integer n -> "count=" + n;
    case String s -> s;
    default -> "unknown";
};
```

All branches produce `String`, so `label` has type `String`. Another example where branches produce `int`:

```java
int total = switch (value) {
    case Integer n -> n;
    case String s -> s.length();
    default -> 0;
};
```

If you want to return `double`, you can use numeric values convertible to the target type. If you mix values that are completely incompatible with the required type, the compiler reports an error. For example, you cannot assign one branch returning `String` and another returning `int` to a primitive `int` variable.

The **target type** can be determined from an assignment, a method's return type, or a method call argument. When using `var result = switch (...) { ... };`, the compiler must infer the result type from the branches; if branches have different types, the common type is determined by language rules. For readable APIs, it is usually better to use an explicit return type such as `String`, `int`, or a purposeful result interface/record rather than relying on an overly broad common type.

In practice, design a `switch expression` to return **one kind of meaning**: all statuses, all scores, or all result DTOs. If each branch logs, mutates data, and returns different types, splitting responsibilities into smaller methods is easier to understand.

## 10. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `case String s -> { s.length(); }` in a switch expression | The block contains statements but **does not return a value** to the switch expression. | Use `yield s.length();` or write `case String s -> s.length();`. |
| Writing `break n;` to return a value | `break` is not the mechanism for returning a result from a switch expression. | Use `yield n;` inside the block. |
| Omitting `default` in `switch (Object value)` when only handling `String` and `Integer` | Not exhaustive for all other types. | Add `default -> ...` or model the input type with an exhaustive sealed hierarchy. |
| Assuming `default` always catches `null` | A `null` selector requires explicit handling in a pattern switch; without a matching case, an exception is thrown. | Add `case null -> ...` when `null` should be handled as valid data. |
| Placing `case Integer n -> ...` before `case Integer n when n > 10 -> ...` | The unguarded branch covers the guarded case too, making the later branch dominated. | Place the guarded branch first. |
| Having `case A(...) when condition` as the only branch handling subtype `A` | The guard can be false, so the branch does not cover all of `A`. | Add a remaining `case A(...) -> ...` branch or another appropriate catch-all branch. |
| Referencing variable `s` from `case String s` in an `Integer` branch | A pattern variable is only in scope in its own branch's guard and body. | Compute the result inside its corresponding branch; pass values to other methods via arguments. |
| Using `return` inside a `case ... -> { ... }` block of a switch expression intending to return a value to the switch | `return` exits the method, not the switch expression branch; depending on context, the compiler may also reject it. | Use `yield` to supply a value to the switch expression. |
| Using Java 21 syntax on Java 17 as standard syntax | Pattern matching for switch and record patterns were not finalized in Java 17. | Use JDK 21+ for the examples in this lesson. |
| Converting a switch statement with fall-through directly into a switch expression without checking | Expressions require producing a value and exhaustive matching. | Redesign branches using `->`/`yield` and verify all cases are covered. |

## 11. Exercise: Pricing by Transaction Type

Given two records used as input data:

```java
record DigitalPurchase(String sku, int price) {}
record PhysicalPurchase(String sku, int price, int shippingFee) {}
```

Write a method `static int total(Object purchase)` that computes the result according to these rules:

- `DigitalPurchase`: return `price` if non-negative.
- `PhysicalPurchase`: return `price + shippingFee` if both numbers are non-negative.
- `null`: return 0.
- All other cases (including invalid data): throw `IllegalArgumentException`.

**Java 21 solution** (placed in the same class as the two records above):

```java
static int total(Object purchase) {
    return switch (purchase) {
        case null -> 0;
        case DigitalPurchase(var sku, var price) when price >= 0 -> price;
        case PhysicalPurchase(var sku, var price, var shippingFee)
                when price >= 0 && shippingFee >= 0 -> price + shippingFee;
        default -> throw new IllegalArgumentException("Unsupported purchase");
    };
}
```

This is a `switch expression` of type `int`. The two record pattern branches return a number only when the guard confirms non-negative amounts. The `default` branch **throws an exception** instead of producing a number; this is still valid because that execution path terminates abnormally. For instance, `total(new DigitalPurchase("EBOOK", 150))` returns 150; `total(new PhysicalPurchase("BOOK", 200, 30))` returns 230; `total(null)` returns 0; `total(new DigitalPurchase("BAD", -1))` throws `IllegalArgumentException`.

Self-check point: if a `PhysicalPurchase` has a negative shipping fee, the `when` branch does not match; it falls through to `default` and throws an exception. If business requirements call for distinct error messages per record, you can add unguarded branches afterward to differentiate them rather than lumping all errors into a single `default`.

## 12. Guidelines for Choosing How to Write It

- If the goal is to **map an input to a value**, prefer a `switch expression` and write `return switch (...) { ... };` or assign the result to a variable.
- For a single-line calculation, use `case Pattern -> expression;`. For multiple steps, use `case Pattern -> { ...; yield result; }`.
- Use patterns to check type/structure and extract variables at the same time; use `when` for secondary conditions on those variables. Place specific branches before general ones.
- Always ensure exhaustiveness: `default` for open types like `Object` when needed; list all subtypes in a sealed hierarchy if you want the compiler to verify coverage.
- Handle `null` according to the function's contract using `case null` or a pre-check, rather than implicitly assuming `default` catches it.
- Keep the result type and meaning consistent; reserve exceptions for genuine error states rather than replacing valid branch design.

**References:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
