# Ordering Specific Guards Before General Guards in Java

## 1. The problem: multiple `case ... when` labels can be true at the same time

**Pattern matching for `switch`**, finalized in **Java 21** (JEP 441), allows a `case` label to consist of a **pattern** and a *guard* condition:

```java
case String s when s.isBlank() -> System.out.println("Blank");
```

Java first tests whether the selector value matches `String s`; if it matches, it initializes the pattern variable `s` and evaluates `s.isBlank()`. The rule is selected only when **both the pattern and the guard match**.

Important point: **`case` labels are evaluated in the order they appear in the switch block.** When multiple labels can accept the same value, the first matching label is the one selected. There is no automatic mechanism to guess which label is "more specific" in terms of business logic.

Example:

```java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() <= 4 -> "short";
        case String s -> "other text";
        case null -> "null";
        default -> "other";
    };
}
```

For the value `"  "` (two spaces), **both of the first two guards are true**: the string is blank and has length 2. Java selects the `isBlank()` rule because it **comes first**. If you swap the positions of the two rules, the program may still compile, but `"  "` will be labeled `"short"` instead of `"blank"`.

That is the reason for the design rule:

> **Place special, high-priority, or easily shadowed cases first; place broader cases later; end with an unguarded branch or `default` when needed.**

"Specific" here refers to **business priority and the set of accepted values**, not just class inheritance relationships.

## 2. How Java selects a guarded rule

For a `switch` using type patterns in Java 21, the label evaluation flow in source order can be described as follows:

1. Evaluate the selector `switch (input)` once.
2. Check whether the first `case` label applies to that value.
3. If the label contains a pattern, test the pattern. **Only when the pattern matches** do the pattern variables exist to evaluate `when`.
4. If the guard is false, continue searching for the next matching label. If the guard is true, select the rule and execute the right-hand side of `->`.
5. With arrow rules, execution does not continue into the rule below (*no fall-through*).
6. If no label matches, handling depends on the exhaustiveness of the switch; for an enhanced switch, the compiler requires enough labels to cover all allowed values.

The label selection rule does not call all guards and pick the "most specific" result. As soon as a rule is selected, guards **after that rule are no longer evaluated for this switch execution**.

### A false guard vs. a guard that throws an exception

```java
case String s when s.length() > 10 -> System.out.println("long");
```

If `s.length() > 10` is `false`, Java tries the next label. However, if **the guard expression throws an exception**, the switch terminates abruptly with that exception rather than treating the exception as `false`. Therefore, guards should be short, safe, and free of side effects.

### Guards are only evaluated after the pattern matches

```java
case String s when s.startsWith("ERR:") -> System.out.println(s);
```

`String s` does not match `Integer`, `null`, or other types. When it does not match, Java cannot use `s` to run the guard. Accessing `s.startsWith(...)` is valid because the guard is only evaluated after `s` has been bound to a non-null `String` object.

## 3. Clear example: guards for blank strings and short strings

Suppose a program needs to classify strings into three groups:

- **Blank**: `s.isBlank()`.
- **Short, but not prioritized as blank**: `s.length() <= 4`.
- **Remaining strings**: unguarded `case String s` branch.

Order **matching the business requirement**:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s when s.length() <= 4 -> "short";
        case String s -> "text";
        default -> "other";
    };
}
```

**Unsuitable** order when you want to identify blank strings first:

```java
static String classifyPoorly(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.length() <= 4 -> "short";
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

Both methods **compile validly on Java 21**, because Java does not prove in general that `isBlank()` has a value set completely contained within `length() <= 4`. However, the results differ:

| Input | `isBlank()` guard first | `length() <= 4` guard first |
| --- | --- | --- |
| `"  "` | `"blank"` | `"short"` |
| `""` | `"blank"` | `"short"` |
| `"Hi"` | `"short"` | `"short"` |
| `"Java"` | `"short"` | `"short"` |
| `"Pattern"` | `"text"` | `"text"` |

For the input `""`, both guards are true: `isBlank()` is true and `length()` is 0. If you want empty/blank strings to receive special handling, that branch must come before the short-string branch.

**Stricter approach:** if two rules easily overlap, in addition to ordering by priority, you can also make the exclusion explicit:

```java
case String s when s.isBlank() -> "blank";
case String s when !s.isBlank() && s.length() <= 4 -> "short";
case String s -> "text";
```

The second guard explicitly excludes blank strings. That makes the design intent easier to explain; you should still place the branches in the desired priority order.

## 4. Prioritizing error codes before length classification

Another practical example is strings with the `"ERR:"` prefix:

```java
static String route(Object input) {
    return switch (input) {
        case String s when s.startsWith("ERR:") -> "error";
        case String s when s.length() <= 4 -> "short";
        case String s -> "other text";
        case null -> "null";
        default -> "other";
    };
}
```

The value `"ERR:"` satisfies both the prefix condition and the length-4 condition. If the business rule requires **identifying error messages first**, the `startsWith("ERR:")` label must come above the `length() <= 4` label.

Placing the short-length branch first can cause error codes to be misclassified without the compiler **necessarily reporting a dominance error**. This is a **runtime logic conflict**, unlike the case where a pattern is completely shadowed, which the JLS can detect at compile time.

You should design the order by asking:

1. Which case is more important when **multiple conditions are true at the same time**?
2. Is any condition a **subset** of another condition according to the business logic?
3. Is there a final **unguarded** rule to cover the remaining values of the same type?
4. Are `case null` and `default` present if the selector can receive values outside the listed types?

## 5. Specific guards, general guards, and general type patterns

"General guard" is not synonymous with "general pattern." Three layers should be distinguished:

| `case` form | Example | Match scope |
| --- | --- | --- |
| Pattern + specific guard | `case String s when s.isBlank()` | Blank strings only |
| Pattern + broad guard | `case String s when s.length() <= 4` | Any string up to length 4, including short blank strings |
| Unguarded pattern | `case String s` | Any non-null string |
| Supertype pattern | `case CharSequence cs` | `String` as well as other classes implementing `CharSequence` |
| `default` | `default` | Non-null values not yet selected |

An unguarded pattern `case String s` placed **before** `case String s when s.isBlank()` will shadow the guarded branch after it: it matches all `String` values, leaving none for the other branch. This is a **dominance** situation detected by the Java 21 compiler.

Example that **does not compile** (illustrative snippet within the same switch):

```java
// INVALID:
case String s -> System.out.println("any String");
case String s when s.isBlank() -> System.out.println("blank"); // Dominated.
```

Fix by reversing the order:

```java
// VALID when placed in a switch with a compatible selector:
case String s when s.isBlank() -> System.out.println("blank");
case String s -> System.out.println("any other String");
```

Similarly, when mixing a supertype and a subtype, an unguarded supertype label can dominate the subtype label:

```java
// INVALID if in the same switch:
case CharSequence cs -> System.out.println("char sequence");
case String s -> System.out.println("string"); // String is dominated.
```

**Fix:** place `case String s` or guarded `String` labels first, then `case CharSequence cs` if you want to handle `String` separately.

### Dominance errors vs. business priority errors

- **Compile-time dominance**: an earlier label under JLS rules already covers a later label, for example `case String s` before a `case String s when ...`. Java 21 refuses to compile.
- **Runtime overlap**: two arbitrary guards have overlapping match domains, for example `s.isBlank()` and `s.length() <= 4`. Java does not infer general logical relationships between arbitrary guard expressions; the program can compile, but **changing the order changes the result**.

Even a guard that is mathematically always true should not be used to "replace" an unguarded pattern: a clearer and more readable design is to use `case String s` as the final branch of the `String` group.

## 6. Pattern variables and the scope of `when`

In a rule:

```java
case String s when s.length() > 4 -> System.out.println(s.toUpperCase());
```

The variable `s` is created when the pattern `String s` matches. It can be used:

1. In the guard **`when s.length() > 4`** of that same label;
2. In the expression, statement, or block on the right-hand side of `->` belonging to that same rule.

You cannot take a pattern variable from an earlier rule and use it in `when` or the RHS of a later rule. Two different rules can use the **same name** `s` because each label is an independent pattern variable declaration:

```java
switch (input) {
    case String s when s.isBlank() -> System.out.println("blank " + s.length());
    case String s when s.length() <= 4 -> System.out.println("short " + s);
    case String s -> System.out.println("text " + s);
    default -> System.out.println("other");
}
```

This snippet is an illustrative switch statement with a suitably declared `input` variable and **assumes `null` is not passed**; if null needs to be supported, add `case null`. The `s` variable in the first branch and the `s` variable in the second branch **are not the same variable**.

Guards commonly use methods of the matched type, such as `String.isBlank`, `String.length`, `Integer.signum`, or combined conditions with `&&`, `||`. Any additional conditions should avoid unnecessary side effects because reordering rules also changes the order in which guards are called.

## 7. Complete Java 21+ program

Save to the file **`GuardOrderingDemo.java`**:

```java
public class GuardOrderingDemo {
    static String route(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";

            case String s when s.startsWith("ERR:") ->
                    "error-code=" + s.substring(4);

            case String s when s.length() <= 4 -> "short: " + s;

            case String s -> "text: " + s;

            case Integer n when n == 0 -> "zero";

            case Integer n when n < 0 -> "negative: " + n;

            case Integer n when n <= 10 -> "small positive: " + n;

            case Integer n -> "large positive: " + n;

            default -> "other";
        };
    }

    static String badOrder(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.length() <= 4 -> "short";
            case String s when s.isBlank() -> "blank";
            case String s when s.startsWith("ERR:") -> "error";
            case String s -> "text";
            default -> "other";
        };
    }

    static void announce(Object value) {
        switch (value) {
            case null -> System.out.println("ANNOUNCE null");
            case String s when s.isBlank() ->
                    System.out.println("ANNOUNCE blank");
            case String s when s.length() <= 4 ->
                    System.out.println("ANNOUNCE short");
            case String s -> System.out.println("ANNOUNCE text");
            default -> System.out.println("ANNOUNCE other");
        }
    }

    public static void main(String[] args) {
        System.out.println(route("  "));
        System.out.println(route("ERR:42"));
        System.out.println(route("ok"));
        System.out.println(route("Java 21"));
        System.out.println(route(0));
        System.out.println(route(-4));
        System.out.println(route(7));
        System.out.println(route(21));
        System.out.println(route(null));
        System.out.println(route(2.5));

        System.out.println("wrong blank: " + badOrder("  "));
        System.out.println("right blank: " + route("  "));
        System.out.println("wrong error: " + badOrder("ERR:"));
        System.out.println("right error: " + route("ERR:"));

        announce(" ");
        announce("Hi");
    }
}
```

Compile and run with **JDK 21 or later**, without `--enable-preview`:

```bash
javac GuardOrderingDemo.java
java GuardOrderingDemo
```

**Exact standard output:**

```text
blank
error-code=42
short: ok
text: Java 21
zero
negative: -4
small positive: 7
large positive: 21
null
other
wrong blank: short
right blank: blank
wrong error: short
right error: error-code=
ANNOUNCE blank
ANNOUNCE short
```

**Explanation by order:**

1. `"  "` is both blank and short. `route` prioritizes `isBlank()`, so it returns `blank`.
2. `"ERR:42"` has the `"ERR:"` prefix and is not blank, so it returns `error-code=42` before checking length.
3. `"ok"` is short (2 characters), so it returns `short: ok`; `"Java 21"` is longer than 4, so it reaches the unguarded `case String s` rule.
4. `Integer` values 0, -4, 7, 21 match the zero guard, negative guard, small positive guard, and then the general `Integer` branch, respectively.
5. `null` is handled separately by `case null`; `2.5` is boxed into `Double`, which does not belong to `String`/`Integer`, so it goes to `default`.
6. In `badOrder`, the length guard comes first. As a result, `"  "` becomes `"short"` instead of `"blank"`, and `"ERR:"` becomes `"short"` instead of `"error"`.
7. `route("ERR:")` matches the prefix first, `substring(4)` is an empty string, so it prints `right error: error-code=` (with no characters after `=`).
8. `announce` is a **switch statement** with arrow rules. Guards are still evaluated in order; the selected branch prints its message and stops, without falling through.

The program demonstrates the difference between **an intended rule order** and **an order that still compiles but misclassifies**, while also showing that the same rules apply to both `switch expression` and `switch statement`.

## 8. How to organize guards across priority tiers

For rules with many conditions, a stable approach is to prioritize by tier:

1. **Special values** requiring dedicated policy: for example `case null`, blank strings, critical error codes, 0.
2. **Specialized guards**: for example `startsWith("ERR:")`, `n < 0`, or `n > 1000`.
3. **Broader guards**: for example `s.length() <= 4`, `n <= 10`.
4. **Unguarded pattern of the same type**: for example `case String s`, `case Integer n`.
5. **Supertype pattern or `default`**: for remaining types.

This ordering is only a suggested framework; **business intent determines what is considered specific**. For example, in a logging system, an empty string might be treated as a format error and checked before any prefix. In another program, a special prefix might take higher priority than length classification.

### What about mutually exclusive guards?

If guards **cannot be true at the same time**, changing their order usually does not change the result. For example, with `Integer n`:

```java
case Integer n when n < 0 -> "negative";
case Integer n when n == 0 -> "zero";
case Integer n when n > 0 -> "positive";
```

These three conditions are numerically mutually exclusive, so each `Integer` matches at most one guard. Even so, you must still ensure the remaining cases of the selector are covered. You can use `case Integer n -> ...` as an explicit fallback branch; if the final branch is missing in a switch whose selector is `Integer`, the compiler does not necessarily deduce that three arbitrary guards cover all integers.

**Do not rely on the compiler proving inequalities in guards to establish exhaustiveness.** The compiler applies language-level pattern/label rules rather than running a general solver for arbitrary business predicates.

### Keep guards lean and side-effect free

Avoid guards that write logs, mutate counters, or call APIs with side effects just to determine a branch:

```java
// Not recommended:
// case String s when externalService.recordAndCheck(s) -> ...
```

Reordering labels, adding a new branch, or a guard failing can cause side effects to run at different times. Compute needed facts before the switch, or separate the pure check (*pure predicate*) from the action to run after selecting a rule.

## 9. Dominance, `when`, and compile errors to distinguish

### 9.1. Unguarded pattern before a guarded one

**Invalid due to dominance**:

```java
// Illustration within the same switch(Object value):
// case String s -> "all strings";
// case String s when s.isBlank() -> "blank"; // Rejected by the compiler.
```

**Valid**:

```java
// In a switch expression with a selector and other covering branches:
case String s when s.isBlank() -> "blank";
case String s -> "other strings";
```

The unguarded `String` branch must be placed **last** among the `String` branches if you want guarded cases handled first.

### 9.2. Unguarded supertype before a subtype

**Invalid due to dominance**:

```java
// In the same switch(Object value):
// case CharSequence cs -> "any char sequence";
// case String s -> "string"; // String is dominated.
```

**Valid**:

```java
// In a compatible switch expression:
case String s -> "string";
case CharSequence cs -> "another char sequence";
```

Even though both `String` and `CharSequence` can match `"abc"`, the specialized branch is placed first; `CharSequence` handles other objects implementing this interface.

### 9.3. Two arbitrary overlapping guards that still compile

```java
// Valid, but the order may violate the intended logic:
case String s when s.length() <= 4 -> "short";
case String s when s.isBlank() -> "blank";
case String s -> "other";
```

For `" "`, the first rule matches and the second rule never runs. This is a **logic classification bug**, not a dominance error that the compiler is required to detect.

### 9.4. `when` only applies to labels with patterns

```java
// Not valid syntax in Java 21:
// case "ERR:" when flag -> "error";
```

If the selector is `String`, you can use `case "ERR:" -> ...` as a dedicated constant label, then add other rules. If you need a guard based on the string data, use `case String s when s.equals("ERR:") && flag -> ...` in the appropriate context.

### 9.5. `default` and `null`

In a Java 21 switch, **`case String s` does not match `null`**, and a regular `default` does not handle a `null` selector automatically. If the selector can be null, add `case null -> ...` (or use the special label `case null, default` when appropriate). Omitting a null label can cause `switch(null)` to throw `NullPointerException`.

### 9.6. Enhanced switch and exhaustiveness

A `switch expression` must cover all possible values; a `switch statement` that uses patterns is also an enhanced switch statement and must be **exhaustive**. With an `Object` selector, include `default` if the patterns do not cover all non-null values.

A `case Object o` branch is a very broad pattern. When the selector is already `Object`, avoid placing it alongside `default` as two competing general branches; choose a clear coverage strategy and handle null explicitly.

### 9.7. Switch rules vs. statement groups

In a switch rule `case ... -> ...`, there is no fall-through. In a switch statement using `case ...:` statement groups, Java restricts fall-through via rules that ensure pattern variables are initialized. **Reordering labels affects not only rule selection, but can also affect control flow** when using `:` syntax. For multi-guard classification, `->` is usually easier to control.

## 10. Practice exercises

1. **Blank strings and short strings.** Create a switch expression with `case String s when s.isBlank()`, `case String s when s.length() <= 5`, and `case String s`. Test inputs `""`, `" "`, `"Hi"`, `"Java 21"`. Swap the order of the first two guards and record the differing results.
2. **Error messages.** Write a `case String s when s.startsWith("ERR:")` rule followed by `case String s when s.length() <= 4`. Test `"ERR:"`, `"ERR:404"`, `"OK"`. Explain why the prefix must take priority over length.
3. **Overlapping numeric ranges.** With `Integer n`, write guards `n == 0`, `n < 0`, `n <= 10`, and then `case Integer n`. Test `0`, `-4`, `5`, `20`. Move `n <= 10` before `n == 0` and explain why the zero branch is shadowed.
4. **Dominance error.** Place `case String s` before `case String s when s.isBlank()` and observe the compiler error. Fix the order. Compare this with placing `when s.length() <= 5` before `when s.isBlank()`, which compiles but has a logic bug.
5. **Mutually exclusive guards.** Write branches `n < 0`, `n == 0`, `n > 0` and try reordering them. Explain why the result does not change for `Integer` when the conditions are truly mutually exclusive; add a fallback branch to ensure exhaustiveness.
6. **Pattern variable scope.** Write two different `case String s when ...` rules using the same name `s`; explain why this is valid. Try using `s` outside the switch to observe the error.
7. **Null and other types.** Use an `Object` selector, add `case null` and `default`. Test `null`, `Double`, `String`, and `Integer` to ensure every path is intentional.
8. **Business scenario.** Design a request classifier with priorities: locked account, overdue transaction, high-amount transaction, then normal request. Identify which guards can be true simultaneously; write the order, then write a test table for the overlapping cases.
9. **Record patterns (Java 21+).** Create `record Request(String path, int priority) {}`. Use two branches: `case Request(String path, int priority) when path.startsWith("/admin") && priority >= 10`, then `case Request(String path, int priority) when priority >= 10`, and a general `Request` branch. Explain why "urgent admin request" must come before "any urgent request."

**Remember:** Java selects **the first matching `case` label**, not automatically the "most specific" guard. With overlapping guards, order is part of the business logic. Place specialized guards before broad guards, unguarded patterns last within the same-type group, and check for both **compile-time dominance** and **runtime overlap**.

## References

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS 21, §14.11 — Switch Statements, switch labels, and dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [JLS 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [JLS 21, §6.3.3 — Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
