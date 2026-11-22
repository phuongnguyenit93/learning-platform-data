# Choosing Between if and switch: Prioritizing Readability When Using Pattern Matching in Java

## 1. Lesson Objectives

In Java, both `if / else if / else` and `switch` can control program flow. With **pattern matching**, these two approaches overlap even more: both can check types, extract values from a `record`, and use bound variables to process logic. Therefore, the practical question is not just "which syntax is shorter?" but:

> **Which structure helps the reader quickly understand the selection condition, the result of each branch, the normal path, and any unhandled cases?**

This lesson focuses on **choosing between `if` and `switch` based on readability and maintainability**. After this lesson, you will be able to:

- Identify cases where `if` / guard clauses are clearer, especially for independent conditions and early checks.
- Use `switch` when a single input value has multiple forms or mutually exclusive choices.
- Compare styles using **type patterns**, **record patterns**, `when` guards, `switch expression`, `yield`, and `sealed interface`.
- Understand limitations regarding `null`, branch ordering, **domination**, **exhaustiveness**, and pattern variable scoping.
- Refactor with tests instead of changing syntax just to reduce line count.

**Version:** Pattern matching for `instanceof` has been a standard feature since Java 16 (JEP 394); record patterns and pattern matching for `switch` are standard features in **Java 21** (JEP 440, JEP 441). The complete examples in this lesson run on **JDK 21 or later**, without preview flags.

## 2. Quick Selection Rule: Ask "What Am I Deciding Based On?"

A helpful perspective:

- **`if`** expresses: "If this condition is true, do this; otherwise, check the next condition." Conditions can use multiple variables, comparisons, predicate functions, or independent states.
- **`switch`** expresses: "Based on **one selector** (the input value under consideration), choose one of the cases." The selector can be matched against constants, types, or record structures. Branches can have `when` for further filtering.
- **`switch expression`** further emphasizes: "From this selector, **compute a value**." It requires cases to be exhaustively covered.
- **A guard clause with `if`** emphasizes: "If the input or precondition is invalid, exit early; the main business logic follows."

Practical comparison table:

| Situation | Usually Preferred | Readability Reason |
| --- | --- | --- |
| One or two simple conditions | `if` | Avoids heavy syntax for a small problem. |
| Checking invalid input and then `return`/`throw` | `if` with guard clause | The success path is not deeply nested. |
| Conditions based on **multiple independent values** like age, role, quota, status | `if / else if` | Each predicate reads naturally without forcing a fake selector. |
| Multiple forms of **the same input**: `Created`, `Changed`, `Deleted` | `switch` with type/record patterns | The choices sit on the same level, easy to scan and compare. |
| Mapping an input to a single result | `switch expression` | Each branch produces a value; the compiler helps verify completeness. |
| `sealed interface` with known subtypes | `switch` | Can list all subtypes without `default`, letting the compiler remind you to handle new branches when the type hierarchy changes. |
| Long branches, many side effects, or complex state dependencies | Consider `if` and helper methods | A large `switch` with many blocks is still hard to read; separating business logic matters more than syntax. |
| Only needing one component of a record whose type is already known | Direct accessor or simple `if` | No need to deconstruct the entire record just to get one value. |

This table is only a **guideline**, not a compiler rule. Prioritize the structure that makes the business logic and error cases clearest for your development team.

## 3. When if Is Better: Sequential, Independent Conditions and Guard Clauses

### 3.1. A Single Clear Condition Does Not Need switch

Input validation example:

```java
static String title(Object raw) {
    if (raw instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    return "Untitled";
}
```

This condition answers directly: "If it is a string and not blank, use it; otherwise use the default." Writing a `switch` with `case String s when ...` and `default` is also valid in Java 21, but not necessarily more readable for just a single check.

### 3.2. Conditions Based on Multiple Independent Variables

```java
static int priority(int age, boolean vip) {
    if (age < 0) return -1;
    if (vip && age >= 65) return 3;
    if (vip || age >= 65) return 2;
    return 1;
}
```

Here the decision depends on **both age and VIP status**, and the priority order of the conditions matters. `if` describes the predicates directly; there is no need to create an intermediate enum or string just to force it into a `switch`. In particular, avoid simulating `switch (true)`: in Java 21, you should not use a boolean selector as a trick to replace `if`.

### 3.3. Guard Clauses Help Reduce Nesting

```java
record Point(int x, int y) {}

static String pointLabel(Object value) {
    if (!(value instanceof Point(var x, var y))) {
        return "not a point";
    }
    if (x < 0 || y < 0) {
        return "invalid point";
    }
    return "sum=" + (x + y);
}
```

The first guard checks whether the data matches `Point`. If it does not match, the method returns immediately. When execution continues, Java guarantees that the two pattern variables `x` and `y` are bound (**flow scoping** rules). The second guard handles the business condition; the success path sits straight at the end. Writing this as a `switch` for three dependent steps does not necessarily make the logic easier to read.

**Note:** A pattern variable is only valid on control-flow paths where the compiler knows the pattern is definitely matched. For example, if `if (!(value instanceof Point(var x, var y)))` only logs and continues, you cannot use `x, y` afterward as if they were definitely assigned.

## 4. When switch Is Better: One Input, Multiple Case Types

Suppose a system receives different types of events:

```java
sealed interface Event permits Created, Changed, Deleted {}
record Created(String id, int count) implements Event {}
record Changed(String id, int before, int after) implements Event {}
record Deleted(String id) implements Event {}
```

Requirement: given an `Object value`, produce a label:

- `Created`: `"created <id>/<count>"`.
- `Changed`: if `after > before`, produce a growth label; otherwise, a generic changed label.
- `Deleted`: a deleted label.
- `null`: `"missing"`; any other type: `"unsupported"`.

Implementation using `if`:

```java
static String withIf(Object value) {
    if (value == null) return "missing";

    if (value instanceof Created(var id, var count)) {
        return "created " + id + "/" + count;
    }
    if (value instanceof Changed(var id, var before, var after)) {
        if (after > before) {
            return "growth " + id + "/" + (after - before);
        }
        return "changed " + id;
    }
    if (value instanceof Deleted(var id)) {
        return "deleted " + id;
    }
    return "unsupported";
}
```

This style is reasonable and easy to understand. However, the reader has to track that each `if` has a `return` to know which branch excludes which, and a chain of handling `value` is spread from top to bottom.

The same logic using a `switch expression`:

```java
static String withSwitch(Object value) {
    return switch (value) {
        case null -> "missing";
        case Created(var id, var count) -> "created " + id + "/" + count;
        case Changed(var id, var before, var after) when after > before -> {
            int delta = after - before;
            yield "growth " + id + "/" + delta;
        }
        case Changed(var id, var before, var after) -> "changed " + id;
        case Deleted(var id) -> "deleted " + id;
        default -> "unsupported";
    };
}
```

In this case, `switch` has clear advantages:

1. **A single selector:** every branch answers "which type/case does `value` belong to?".
2. **Branches at the same level:** easy to see the list of `Created`, `Changed`, `Deleted`.
3. **No fall-through:** the arrow syntax `->` separates branches automatically.
4. **Clearly indicates the result value:** `return switch (...)` returns a `String`, without repeating `return` in every branch.
5. **Supports `when`:** the growth `Changed` branch comes before the general `Changed` branch.

The `Changed ... when after > before` branch uses a block with two statements and `yield` to produce the result from the **switch expression**. If a branch has only a single expression, `yield` is not needed. If converted to a **switch statement** for the purpose of directly executing `return` from the method, the block can contain `return` instead of `yield`. Do not confuse `yield` (returning a value for the switch expression) with `return` (returning a value from the method).

Here, record patterns extract the `id`, `before`, and `after` components right at the `case` branch; each record pattern must list all components in their exact declaration order.

## 5. When switch expression Is Especially Useful: Exhaustiveness via Sealed Types

Suppose the method accepts `Event` rather than `Object`. Because `Event` is a `sealed interface`, the compiler knows the three permitted direct subtypes: `Created`, `Changed`, and `Deleted`. We can compute the label using a `switch expression` **without a `default` branch**:

```java
static String sealedSwitch(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created(var id, var count) -> "created " + id + "/" + count;
        case Changed(var id, var before, var after) when after > before
                -> "growth " + id + "/" + (after - before);
        case Changed(var id, var before, var after) -> "changed " + id;
        case Deleted(var id) -> "deleted " + id;
    };
}
```

This is a beneficial choice for maintainability:

- The `switch` expression must be **exhaustive**: it must have a branch for every case permitted by the selector type.
- A `Changed` branch with `when` is **not sufficient** to cover all `Changed` instances because the condition can be false. The unguarded `Changed` branch after it handles the remainder.
- If the source code changes the hierarchy by adding a permitted subtype to `permits`, the compiler can require updating the `switch` upon recompilation.
- Avoid adding `default` unconditionally "just to be safe" in a sealed hierarchy: `default` can hide forgetting to handle a new subtype. However, design appropriate fallback handling if the API requires broad compatibility.

`switch` cannot always replace `if`: when you need to sequentially check multiple invariants of an object and return **exact errors per level**, guard clauses usually express intent better.

**Note on `null`:** `case null` handles a `null` selector intentionally. Do not treat `default` as a substitute for `case null`; a `switch` that does not handle null can throw `NullPointerException` with a null selector. This example chooses to return `"missing"`, though another API might want to throw an exception.

## 6. Complete Java 21 Example: Same Result, Two Structures

Create the file **`IfOrSwitchDemo.java`**:

```java
public class IfOrSwitchDemo {
    record Point(int x, int y) {}
    sealed interface Event permits Created, Changed, Deleted {}
    record Created(String id, int count) implements Event {}
    record Changed(String id, int before, int after) implements Event {}
    record Deleted(String id) implements Event {}

    static String withIf(Object value) {
        if (value == null) return "missing";
        if (value instanceof Created(var id, var count)) {
            return "created " + id + "/" + count;
        }
        if (value instanceof Changed(var id, var before, var after)) {
            if (after > before) return "growth " + id + "/" + (after - before);
            return "changed " + id;
        }
        if (value instanceof Deleted(var id)) return "deleted " + id;
        return "unsupported";
    }

    static String withSwitch(Object value) {
        return switch (value) {
            case null -> "missing";
            case Created(var id, var count) -> "created " + id + "/" + count;
            case Changed(var id, var before, var after) when after > before -> {
                int delta = after - before;
                yield "growth " + id + "/" + delta;
            }
            case Changed(var id, var before, var after) -> "changed " + id;
            case Deleted(var id) -> "deleted " + id;
            default -> "unsupported";
        };
    }

    static String sealedSwitch(Event event) {
        return switch (event) {
            case null -> "missing";
            case Created(var id, var count) -> "created " + id + "/" + count;
            case Changed(var id, var before, var after) when after > before
                -> "growth " + id + "/" + (after - before);
            case Changed(var id, var before, var after) -> "changed " + id;
            case Deleted(var id) -> "deleted " + id;
        };
    }

    static int priority(int age, boolean vip) {
        if (age < 0) return -1;
        if (vip && age >= 65) return 3;
        if (vip || age >= 65) return 2;
        return 1;
    }

    static String pointLabel(Object value) {
        if (!(value instanceof Point(var x, var y))) return "not a point";
        if (x < 0 || y < 0) return "invalid point";
        return "sum=" + (x + y);
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Created("A", 2),
            new Changed("B", 3, 8),
            new Changed("C", 9, 6),
            new Deleted("D"),
            "random"
        };
        for (Object value : values) {
            String expected = withIf(value);
            System.out.println(expected + " | equal=" + expected.equals(withSwitch(value)));
        }
        System.out.println("sealed=" + sealedSwitch(new Deleted("X")));
        System.out.println("priority=" + priority(70, false));
        System.out.println("point=" + pointLabel(new Point(2, 3)));
        System.out.println("invalid=" + pointLabel(new Point(-1, 2)));
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 IfOrSwitchDemo.java
java IfOrSwitchDemo
```

**Exact output:**

```text
missing | equal=true
created A/2 | equal=true
growth B/5 | equal=true
changed C | equal=true
deleted D | equal=true
unsupported | equal=true
sealed=deleted X
priority=2
point=sum=5
invalid=invalid point
```

Analysis:

- The first six lines compare the output of `withIf` with `withSwitch` on the same value. `equal=true` confirms both approaches produce the same string in six cases: null, created, growth, non-growth change, deleted, and unsupported type.
- `Changed("B", 3, 8)` satisfies `after > before`, so it computes the difference `5`; `Changed("C", 9, 6)` enters the unguarded `Changed` branch and gets the generic label.
- `sealed=deleted X` shows that `switch` on `Event` covers the hierarchy without `default`.
- `priority=2` illustrates that `if` fits independent age and VIP conditions (age 70, not VIP).
- `point=sum=5` and `invalid=invalid point` illustrate guard clauses with a matched `Point` structure; checking negative coordinates is clearer when kept as a separate `if`.

The `equal=true` values in the example are **regression tests for six cases**, not a proof that all data variants are equivalent. In a real project, add boundary data, nulls in components, negative values, and exception behavior before replacing all legacy code.

## 7. Distinguish switch statement and switch expression Before Choosing

Both use the `switch` keyword, but their purposes are different.

**Switch expression** produces a value:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "none";
        case String s -> "text";
        case Integer n when n >= 0 -> "nonnegative number";
        case Integer n -> "negative number";
        default -> "other";
    };
}
```

**Switch statement** performs actions/statements. For example, when logging by data type:

```java
static void logType(Object input) {
    switch (input) {
        case null -> System.out.println("none");
        case String s -> System.out.println("text: " + s);
        default -> System.out.println("other");
    }
}
```

If the main goal is to **compute a value** such as a label, classification, or DTO, `switch expression` is usually concise and lets the compiler check that all branches produce a result. If the branches only execute statements such as logging or calling services, a `switch statement` or small methods may be more appropriate.

With a `switch expression`, a multi-statement branch needs `yield`:

```java
// Illustrative example inside a method returning int.
return switch (input) {
    case String s -> {
        String normalized = s.strip();
        yield normalized.length();
    }
    case Integer n -> n;
    default -> 0;
};
```

`yield` supplies a value for the **switch expression**; `return` returns a value for the **method**. Do not use `break 5;` instead of `yield 5;`. Also do not write a block for an expression branch where any normal execution path completes without yielding a value.

## 8. Important Rules to Keep switch Readable

### 8.1. Specific Branches Before General Branches

The following syntax intends to compute growth, but the order is invalid:

```java
// Wrong: the unguarded Changed branch first dominates the branch when after > before.
return switch (value) {
    case Changed(var id, var before, var after) -> "changed " + id;
    case Changed(var id, var before, var after) when after > before
            -> "growth " + id;
    default -> "other";
};
```

The unguarded `Changed` branch matches every `Changed`, so the `when` branch after it is **dominated**. Put the branch with `when` first. This is similar to ordering an `if / else if` chain: if a general condition comes first, a specific condition may never get a chance to run. The difference is that the pattern `switch` compiler can detect some of these shadowed branches.

### 8.2. `when` Guards Should Be Short and Express Business Conditions

`case Changed(var id, var before, var after) when after > before -> ...` clearly states the branch selection condition. If the guard needs heavy I/O access, side effects, or hard-to-read logic, move the computation into a pure method with a meaningful name. `when` is not an early `return`: when the guard is false, Java continues checking other matching cases.

### 8.3. Avoid Overly Deep Record Patterns When You Only Need One Piece of Data

For example, `case Order(Customer(Address(var city, ...), ...), ...)` can be useful when you need to **both check the structure and extract the city**. But if you only need to determine that an object is an `Order` and pass the whole record to a method, `case Order order -> handle(order)` or an `if (input instanceof Order order)` may be clearer. Do not deconstruct every component just to create a long tree of parentheses.

### 8.4. Use default Intentionally

With an open selector like `Object`, `default` is usually needed because there are many types beyond the written cases. With a fully known `sealed` hierarchy, listing all subtypes without `default` can help the compiler detect missing branches after the hierarchy source code changes.

However, `default` does not automatically replace `case null`. `null` input must be handled explicitly according to the application contract, via `case null` or an earlier check.

### 8.5. Name Pattern Variables Meaningfully

`case Changed(var id, var before, var after)` reads better than variable names `a, b, c`. For a record with many fields where only one component is used, Java 21 still requires declaring all positions; use a name like `var ignoredField` for unused components. Unnamed patterns `_` are a standard feature starting in Java 22; do not include them in code targeting `--release 21`.

## 9. When You Should Not Refactor if into switch

Do not convert every `if / else` into `switch` just because the new syntax exists. There are signs that `if` is more readable:

1. **Conditions do not share the same selector**: for example, `age >= 18`, `account.active()`, `quota > 0` have independent meanings.
2. **A series of preconditions must all be true**, requiring separate error messages: sequential guard clauses preserve the error contract.
3. **The success path needs to continue processing after the checks**: guard clauses with early `return`/`throw` keep the business logic straight at the end.
4. **Only one special-case branch**: `if (value instanceof Foo f)` can be shorter and more natural than a switch with two cases.
5. **Complex branch logic**, rather than a classification: extracting methods like `processCreated`, `processChanged` may yield a bigger improvement than turning `if` into `switch`.

Similarly, do not force data into a fake enum just to use switch if the original logic is naturally a combination of independent conditions. The goal is **business-rule transparency**, not eliminating the `if` keyword.

### Readability Does Not Always Mean Better Performance

There is no universal rule that "`switch` is faster than `if`" for all pattern matching. Both are optimized by the compiler and JVM depending on data types, branch order, and runtime behavior. For ordinary logic, prioritize the choice that is easy to read, review, and test; only optimize performance after measuring on a critical path.

## 10. Checklist for Reviewing and Refactoring

When deciding whether to keep `if` or switch to `switch`, ask yourself:

1. **One or multiple selectors?** If multiple independent conditions, `if` is usually natural. If one selector with multiple forms, `switch` is a good candidate.
2. **Is the goal to return a value?** If yes, consider `switch expression`; if it is checking conditions and continuing, a guard clause may be clearer.
3. **Are the branches mutually exclusive?** `switch` with `->` makes case boundaries clear; `if` needs proper ordering and `return`/`else` handling.
4. **Are there known subtypes?** With `sealed`, switch has the advantage of exhaustive checking.
5. **Are there nulls and errors to distinguish?** Must preserve `null` behavior, exceptions, error order, and default results.
6. **Is pattern variable scoping clear?** Case variables are only used within valid guards/branches; with `if`, pay attention to flow scoping after `return`.
7. **Are any branches shadowed?** Place specific `when` cases before general type/record cases.
8. **Is there minimal duplication and easy extensibility?** If each case is dozens of lines long, extract methods so the selection part is just action/business names.
9. **Have you tested before and after?** Compare happy paths, invalid data, null, new subtypes, and boundary values.

When reviewing a PR, a comment like "switch to switch to be modern" is not as strong as "these branches all classify the same Event; switch expresses all subtypes exhaustively, making missing new branches obvious." Similarly, keep `if` when it helps identify invariants and errors in sequence.

## 11. Practice Exercises: Choose a Structure and Explain Why

### Exercise A — Independent Result Types

Given the records:

```java
sealed interface OperationResult permits Success, Invalid, Retry {}
record Success(String id) implements OperationResult {}
record Invalid(String reason) implements OperationResult {}
record Retry(int seconds) implements OperationResult {}
```

Write `static String message(OperationResult result)` returning:

- `Success("A1")` → `"ok:A1"`
- `Invalid("bad input")` → `"invalid:bad input"`
- `Retry(5)` → `"retry:5"`
- null → `"no result"`

**Solution:** Choose `switch expression` because the input is **a sealed hierarchy**, branches are determined by type, and the goal is to return a string.

```java
static String message(OperationResult result) {
    return switch (result) {
        case null -> "no result";
        case Success(var id) -> "ok:" + id;
        case Invalid(var reason) -> "invalid:" + reason;
        case Retry(var seconds) -> "retry:" + seconds;
    };
}
```

All direct subtypes are covered, without needing `default`. If requirements add a new result type, a switch without default helps the compiler catch the need to update handling on rebuild.

### Exercise B — Multiple Sequential Preconditions

Write a method accepting `Object value`, only accepting a non-empty `String` with maximum length 8. Require distinct error messages for wrong type, blank string, and too long; if valid, return the normalized string itself.

**Solution:** Choose `if` with guard clauses so the sequential conditions are easy to read:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) return "wrong type";
    String normalized = text.strip();
    if (normalized.isEmpty()) return "blank";
    if (normalized.length() > 8) return "too long";
    return normalized;
}
```

The conditions are not four different "object types"; they are sequential validation steps on a type-verified value. Guard clauses preserve error priority without deeply nesting the success result.

### Exercise C — When Do You Need Both?

Suppose an `Event` has three subtypes, but `Changed` specifically must check multiple business conditions and call a service. You can use `switch` to **dispatch by subtype**, and then call `handleChanged(Changed c)`. Inside that method, use **`if`/guard clauses** to check business invariants. Do not force all the work to happen inside one long case.

This combination is usually easier to review than a giant `if` chain or a `switch` containing too many nested blocks.

## 12. Conclusion

**Choose `if` when you are checking conditions; choose `switch` when you are selecting among cases of a single value.** If the goal is also to produce a result, `switch expression` makes mapping input to output clear and compiler-checked for exhaustiveness. When business conditions are independent, prioritized, or require guard clauses, `if` usually keeps control flow easier to follow.

No structure wins in every situation. Evaluate readability by asking: can a maintainer immediately see **which inputs are handled, which branch produces which result, which branches might be missed, and how the code will react to null or new data**?

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
