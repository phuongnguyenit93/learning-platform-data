# Flow Scope Checklist in Java Pattern Matching

**Flow scoping** is the mechanism by which Java determines **where a variable declared by a pattern can be referenced**, based on the control-flow paths where the compiler proves the pattern has matched. With `instanceof`, record patterns, and pattern matching for `switch`, seeing a variable name within the same method is **not enough** to conclude that the variable can be used in every branch.

The goal of this checklist is to help Java learners and reviewers accurately answer:

- Is the pattern variable **definitely bound** before it is accessed?
- Which control-flow path brings execution to the point of use: true branch, false branch, guard return, `&&`/`||` operator, `?:` operator, loop, or `switch` `case`?
- Is the variable in a **valid scope** while its value could still be `null`?
- Can the compiler catch a scope mistake at build time, or is the issue a runtime behavior that needs tests?
- Does refactoring `if` to `switch` preserve guard evaluation order, null handling, and business semantics?

**Versions:** Type pattern `instanceof String s` has been final since **Java 16** (JEP 394), `record` final since Java 16, and `sealed` final since Java 17. Examples using **record patterns** and **pattern switch/when** are compiled on **Java 21+** (JEP 440, 441). The complete program uses `javac --release 21`, without needing `--enable-preview`.

## 1. Terms to Check

| Term | Meaning in this article | What must be verified |
| --- | --- | --- |
| **Pattern** | A type or structural check pattern, e.g., `String text` or `TextEvent(var text)` | Which inputs can the pattern match? |
| **Pattern variable** | A variable declared by a pattern: `text`, `number`, `left` | Is it in flow scope at the point of use? |
| **Matching succeeds** | The pattern matches and the pattern's variables are bound | Which condition guarantees a match? |
| **Definitely matched** | The compiler can conclude the pattern has matched on every path reaching the point of use | Is there an unmatched path that still reaches the variable usage? |
| **Flow scoping** | The effective scope of a pattern variable depends on control flow and expression structure | Do not infer scope solely from braces or variable names |
| **Short-circuit** | `&&` skips the right-hand side when the left-hand side is false; `||` skips the right-hand side when the left-hand side is true | Is the variable definitely assigned when the right-hand side runs? |
| **Guard `when`** | An additional condition checked after a case pattern matches | Is the variable bound inside the guard? Does the guard handle null in the right order? |
| **Dominance** | A preceding general case covers a more specific case following it | Will the case order be rejected by the compiler? |
| **Exhaustiveness** | A switch expression covers all required selector values according to language rules | Is a sealed variant or required branch missing? |

An important distinction: **flow scope is not synonymous with null safety**. When a type pattern `value instanceof String text` succeeds, `text` refers to a non-null `String`. However, with a **component pattern** `TextEvent(var text)`, the variable `text` can receive `null` because the record component declared with type `String` is nullable. The compiler may allow accessing the variable, while calling `text.isBlank()` still throws a `NullPointerException`.

## 2. Quick Checklist Before Reading or Editing Code

Use the table below as a **review checklist**. Any “unclear” answer is a sign to trace the control-flow paths, try compiling, or add tests.

| # | Check question | PASS criteria |
| --- | --- | --- |
| 1 | **Where** is the pattern variable declared? | Identify the exact `instanceof`, record pattern, or case label |
| 2 | At the point of use, has the pattern matched on **every** path? | No unmatched path reaches the variable usage |
| 3 | If in an `if` statement, is it in the **true** or **false** branch? | Variable `s` from `instanceof String s` is usable in the true branch, subject to special flow rules |
| 4 | If negation `!` is used, is the condition inverted correctly? | When `!(value instanceof String s)` is false, the original pattern has matched |
| 5 | If `&&` is used, does the left-hand side guarantee the variable is bound for the right-hand side? | With `value instanceof String s && s.length() > 0`, the answer is yes |
| 6 | If `||` is used, does left-hand side true or false cause the right-hand side to run? | With `!(value instanceof String s) || s.isBlank()`, the right-hand side runs only when the pattern matches |
| 7 | If `?:` is used, does the pattern variable appear only in the branch where matching is guaranteed? | With `value instanceof String s ? s.length() : 0`, the variable is used in the true branch |
| 8 | If early return is used, does the unmatched branch actually exit the method? | `if (!(value instanceof String s)) return ...;` allows using `s` in the remainder |
| 9 | If in a `while`/`for` loop, does the condition guarantee the pattern matches before the body/update? | A matching condition allows using the variable in the parts specified by the JLS |
| 10 | If in a `switch`, does the variable belong to that exact case pattern? | Variable is in that case's guard/body and does not leak into another case |
| 11 | With a record pattern, which components can be null? | Null-guard leaf components before dereferencing |
| 12 | Does case ordering suffer from dominance or a guard causing NPE? | Specific cases before broad cases; null guards before method-calling guards |
| 13 | Does the build use the right Java level? | Code using record patterns and `when` uses `--release 21` or a supporting version |
| 14 | Are unmatched, matched, null, and boundary-value paths all tested? | Tests have oracles and assertions, not just console logging |

**Rule of thumb:** Do not ask “is variable `s` declared in this method?”. Ask: “**If execution actually reaches the line using `s`, does the compiler know for certain that `instanceof String s` succeeded beforehand?**”

## 3. if/else: Distinguishing Matched and Unmatched Pattern Branches

Java 16+ example:

```java
static String positiveIf(Object value) {
    if (value instanceof String text) {
        return "IF=" + text.length();
    }
    return "NO_STRING";
}
```

**Flow analysis:**

1. Java evaluates `value instanceof String text`.
2. If it returns `true`, `text` is bound as a non-null `String`; inside the `if` body, `text.length()` is valid.
3. If it returns `false`, `text` is not bound on that path. The outer branch returns `NO_STRING` without referencing `text`.

Test values:

| Input | Result |
| --- | --- |
| `"Java"` | `IF=4` |
| `Integer.valueOf(4)` | `NO_STRING` |
| `null` | `NO_STRING` |

**Common mistake:**

```java
// INTENTIONALLY WRONG: outside the if, the pattern is not guaranteed to have matched.
static int wrongPostIf(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
    return text.length(); // error: cannot find symbol
}
```

One possible path is `value == null`; execution still reaches `return text.length()` even though the pattern did not match. The compiler rejects it instead of waiting for a runtime NPE.

**If you want to use the variable after the if**, use a negated early-return branch as in Section 4, or place the logic inside the matched `if` branch.

### Can else automatically see the variable from the if branch?

No. In this structure:

```java
// INTENTIONALLY WRONG:
if (value instanceof String text) {
    System.out.println(text);
} else {
    System.out.println(text.length()); // Not matched yet; the variable is not in this scope.
}
```

`else` is specifically the branch when `instanceof` is false. Therefore, `text` has no meaning in this branch. This is analogous to a local variable declared inside an `if` body not being usable arbitrarily outside that body.

## 4. Negation and Early Return: Variable Alive After a Guard

A common Java technique is the **guard clause**:

```java
static String negativeGuard(Object value) {
    if (!(value instanceof String text)) {
        return "NO_STRING";
    }
    return "GUARD=" + text.toUpperCase(java.util.Locale.ROOT);
}
```

We can analyze this with a truth table:

| `value instanceof String text` | `!(...)` | What happens? | Can `text` be used after `if`? |
| --- | --- | --- | --- |
| `false` | `true` | Returns `NO_STRING` immediately | Does not reach the rest |
| `true` | `false` | Skips the `if` branch | **Yes**, the pattern definitely matched |

Because the unmatched branch always ends with `return`, every path reaching `return "GUARD=" + text...` has matched the pattern.

Results: `negativeGuard("java")` returns `GUARD=JAVA`, `negativeGuard(null)` returns `NO_STRING`.

### Dedicated checklist for early return

- [ ] Is the negation `!` placed in the right position?
- [ ] Does the unmatched branch actually **exit** via `return` or `throw`?
- [ ] Can any branch fall through to the line using the variable without matching?
- [ ] After the guard, have you distinguished “variable is definitely bound” from “nested component inside the variable may be null”?

**Opposite wrong example:**

```java
// INTENTIONALLY WRONG:
static int wrongNegationBranch(Object value) {
    if (!(value instanceof String text)) {
        return text.length(); // Here the original pattern did NOT match.
    }
    return 0;
}
```

The compiler reports `cannot find symbol` where `text` is used inside the true branch of the negation.

## 5. The && Operator: Right-Hand Side Runs Only When the Pattern Matched

Standard pattern:

```java
static String andGate(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "AND=" + text.strip();
    }
    return "AND_SKIP";
}
```

This is **flow-scope safe**:

- The left-hand side `value instanceof String text` is evaluated first.
- If false, Java does not evaluate `!text.isBlank()`; the compiler does not need to access `text` on this path.
- If true, `text` is bound and is a non-null `String`; the right-hand side is allowed to call `isBlank()`.
- If both sides are true, the `if` body can use `text.strip()`.

Test table:

| Input | Pattern | Guard | Result |
| --- | --- | --- | --- |
| `" Hi "` | true | true | `AND=Hi` |
| `"  "` | true | false | `AND_SKIP` |
| `12` | false | not evaluated | `AND_SKIP` |
| `null` | false | not evaluated | `AND_SKIP` |

### Combining multiple patterns in one condition

```java
static String twoPatterns(Object first, Object second) {
    return first instanceof String left
            && second instanceof String right
            && left.length() == right.length()
            ? "EQUAL_LEN=" + left + ":" + right
            : "DIFFERENT";
}
```

In the third operand, **both `left` and `right` are bound** because Java reaches it only if both preceding `instanceof` checks are true.

This lets you inspect two objects without manual casting:

```text
twoPatterns("ab", "xy")   -> EQUAL_LEN=ab:xy
twoPatterns(null, "xy")   -> DIFFERENT
twoPatterns("a", "xy")    -> DIFFERENT
```

**Note:** Control flow matters more than declaration position. Reordering the operands can cause a variable to be used before the compiler proves it has matched.

## 6. The || Operator: Negation Must Be Understood Correctly

`||` evaluates its right-hand side only when the left-hand side is **false**, so using a pattern variable requires reasoning opposite to `&&`.

### Wrong pattern: using a variable after a positive instanceof joined by ||

```java
// INTENTIONALLY WRONG:
static boolean wrongOr(Object value) {
    return value instanceof String text || text.length() > 0;
}
```

When `value instanceof String text` returns false, Java must evaluate `text.length() > 0`, but **text is not bound**. The compiler reports `cannot find symbol`. You cannot “fix” this by assuming the variable is declared as soon as the parser reads past the pattern.

### Correct pattern: negating the match

```java
static String orGate(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "OR_SKIP";
    }
    return "OR=" + text;
}
```

Order of evaluation:

1. If not a String or if `null`, `!(...)` is true; `||` does not evaluate the right-hand side. Returns `OR_SKIP`.
2. If it is a String, `!(...)` is false; at this point `text` is bound and the right-hand side is allowed to call `text.isBlank()`.
3. If the String is blank, returns `OR_SKIP`.
4. If the String is not blank, the entire `if` condition is false; the path after `if` allows using `text` and returns `OR=...`.

Results: `orGate("Hi")` → `OR=Hi`; `orGate("  ")` → `OR_SKIP`; `orGate(null)` → `OR_SKIP`.

**Checklist for `||`:** For the right-hand side to use a pattern variable from the left-hand side, prove that **the left-hand side being false** implies the pattern has matched. This holds for the negated pattern above, and fails for the positive pattern `value instanceof String text || ...`.

## 7. The Ternary Operator ?: and Valid Branches

The conditional operator `?:` also has two paths:

```java
static String ternary(Object value) {
    return value instanceof Integer number
            ? "TERNARY=" + (number + 1)
            : "NO_INTEGER";
}
```

- The branch after `?` runs only when `instanceof Integer number` is true, so using `number` is valid.
- The branch after `:` runs when the pattern is false. It cannot arbitrarily use `number`.

Intentionally wrong example:

```java
// INTENTIONALLY WRONG:
static boolean wrongTernary(Object value) {
    return value instanceof String text ? true : text.isBlank();
}
```

The compiler rejects it because the false branch does not guarantee that the pattern variable `text` is bound.

**Additional note:** Choosing branches with `?:` is useful for short expressions. For logic with multiple guards or different error messages, `if/else` or `switch` is usually easier to review.

## 8. while and for: Pattern Variables in Body and Update

Flow scoping also applies in loops. The compiler can infer that a variable is bound on the path entering the loop body when the `instanceof` condition is true.

### while with a pattern condition

```java
static String whileLoop(Object input) {
    int sum = 0;
    while (input instanceof String text && !text.isEmpty()) {
        sum += text.length();
        input = text.substring(1);
    }
    return "WHILE=" + sum;
}
```

Trace with `input="abc"`:

| Iteration check | `text` | `text.length()` added | `input` after iteration |
| --- | --- | ---: | --- |
| 1 | `"abc"` | 3 | `"bc"` |
| 2 | `"bc"` | 2 | `"c"` |
| 3 | `"c"` | 1 | `""` |
| 4 | `""` | Condition `!text.isEmpty()` is false | Exit |

The total is `3 + 2 + 1 = 6`. With `input == null`, the loop never enters its body and returns `WHILE=0`.

### Traditional for loop

```java
static String forLoop(Object input) {
    int sum = 0;
    for (; input instanceof String text && !text.isEmpty();
            input = text.substring(1)) {
        sum += text.length();
    }
    return "FOR=" + sum;
}
```

In this `for (init; condition; update)` construct, the pattern variable `text` is allowed in the **body** and the **update** section because the condition has matched before those parts execute. This example was actually compiled with Java 21 and produces `FOR=6` for `"abc"`, `FOR=0` for `null`.

**Loop checklist:**

- [ ] Is the pattern variable declared in the condition guaranteed to match before entering the body?
- [ ] If the variable is used in the `for` update, is it actually declared by the condition on the true path?
- [ ] Is the variable used after the loop has finished, when the final condition check may have been false?
- [ ] If `input` changes inside the loop, is there a risk of non-termination or repeatedly evaluating an accessor with side effects?

**Do not make arbitrary assumptions for `do/while`:** the `do` body runs **before** the condition is evaluated, so a pattern variable declared in the trailing condition cannot be used in the body before it is bound. If you need a variable across iterations, split the condition or switch to a verifiable structure.

## 9. Switch Patterns: Scope Lives Inside the Case and Its Guard

Java 21 allows classifying a closed hierarchy:

```java
sealed interface Event permits TextEvent, CountEvent, PairEvent {}
record TextEvent(String text) implements Event {}
record CountEvent(int count) implements Event {}
record PairEvent(TextEvent left, TextEvent right) implements Event {}
```

When `switch` selects a case:

```java
static String switchEvent(Event event) {
    return switch (event) {
        case null -> "MISSING_EVENT";
        case TextEvent(var text) when text == null -> "MISSING_TEXT";
        case TextEvent(var text) when text.isBlank() -> "BLANK";
        case TextEvent(var text) -> "TEXT=" + text.strip();
        case CountEvent(int count) when count < 0 -> "NEG_COUNT=" + count;
        case CountEvent(int count) -> "COUNT=" + count;
        case PairEvent(TextEvent(var left), TextEvent(var right))
                when left != null && right != null && left.equals(right) ->
                "SAME_PAIR=" + left;
        case PairEvent(TextEvent(var left), TextEvent(var right)) ->
                "PAIR=" + left + "|" + right;
        case PairEvent(var left, var right) -> "MISSING_PAIR_ITEM";
    };
}
```

The `record` declarations and method above are placed in the same class in the complete program in Section 11. Cases with record patterns require Java 21+.

### Scope across case labels

With `case CountEvent(int count) when count < 0 -> ...`:

- Java evaluates the guard `count < 0` only after `CountEvent(int count)` matches.
- The variable `count` is valid in the guard and body of **that case**.
- The `count` variable of this case **does not leak** into the `PairEvent` or `TextEvent` cases.
- Another `CountEvent(int count)` case can reuse the name `count` in its own separate case scope, according to switch pattern label rules.

Each `->` branch creates an independent handling path; do not try to use one case's pattern variable in another case branch.

### Scope and null are two different issues

`case TextEvent(var text) when text == null -> ...` is still necessary because the `TextEvent.text` component can be null, even though the record pattern matched. Only after this branch catches a null component is the subsequent `text.isBlank()` guard safe on the remaining values in this design.

`case null` only handles a **null selector event**; it does not handle `new TextEvent(null)`. A nested record pattern also does not match a **null child record**:

```java
new PairEvent(null, new TextEvent("B"))
```

That value does not match `PairEvent(TextEvent(...), TextEvent(...))` because `left == null`, but it matches `PairEvent(var left, var right)` and is handled by `MISSING_PAIR_ITEM` in the example.

Conversely:

```java
new PairEvent(new TextEvent(null), new TextEvent("B"))
```

Both child records exist, so `case PairEvent(TextEvent(var left), TextEvent(var right))` matches; `left` is bound, but **its value can be null**. The guard `left != null && right != null && left.equals(right)` does not dereference null; the unguarded case below it returns `PAIR=null|B`.

### Dominance must also be reviewed

If an unguarded `case TextEvent(var text)` is placed **before** branches of the same type with `when`, it covers all `TextEvent` instances, causing the specialized cases behind it to be dominated. The compiler may report:

```text
error: this case label is dominated by a preceding case label
```

Order branches from **special case / when → general type case**, and keep the branch handling a null component before guards that call methods on the component.

### Is exhaustiveness the same as flow scoping?

No. A switch expression on `sealed Event` is checked for exhaustiveness based on its permitted subtypes. Scope controls **variables within each case**. A switch can be exhaustive while a case body still references the wrong variable (compile error), or still hits a runtime NPE due to a null component.

## 10. Wrong Flow Scope in switch: Variables Do Not Cross Between Cases

An example that **intentionally does not compile**:

```java
static String wrongSwitchBranch(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> text; // Not a variable of the Integer case.
        default -> "other";
    };
}
```

`text` belongs only to `case String text`. When the selector is an `Integer`, `text` has not been bound, and the compiler reports `cannot find symbol`.

**How to fix:** each case must use only the pattern variables bound in that branch. If a shared result is needed across multiple cases, compute it from variables present in a common scope or extract a helper method.

Other errors that are not flow scope but are often confused with it:

- **Dominated case:** the compiler rejects a specific branch placed after a general branch that already covers it.
- **Non-exhaustive switch expression:** the compiler rejects a switch missing required cases.
- **Null selector:** a pattern switch without `case null` can throw a runtime NPE.
- **Nullable record component:** the variable is in scope, but calling a method on a null value can throw an NPE.

Therefore, do not blindly fix every pattern-related error by adding `default` or sprinkling `instanceof`.

## 11. Complete Java 21 Program Compiled and Run

Save the exact contents as **`FlowScopeChecklistDemo.java`**:

```java
import java.util.Locale;

public class FlowScopeChecklistDemo {
    sealed interface Event permits TextEvent, CountEvent, PairEvent {}
    record TextEvent(String text) implements Event {}
    record CountEvent(int count) implements Event {}
    record PairEvent(TextEvent left, TextEvent right) implements Event {}

    private static int checks;

    static String positiveIf(Object value) {
        if (value instanceof String text) {
            return "IF=" + text.length();
        }
        return "NO_STRING";
    }

    static String negativeGuard(Object value) {
        if (!(value instanceof String text)) {
            return "NO_STRING";
        }
        return "GUARD=" + text.toUpperCase(Locale.ROOT);
    }

    static String andGate(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "AND=" + text.strip();
        }
        return "AND_SKIP";
    }

    static String orGate(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "OR_SKIP";
        }
        return "OR=" + text;
    }

    static String numericIf(Object value) {
        if (value instanceof Integer number && number >= 0) {
            return "NONNEG=" + number;
        } else {
            return "NEG_OR_OTHER";
        }
    }

    static String ternary(Object value) {
        return value instanceof Integer number
                ? "TERNARY=" + (number + 1)
                : "NO_INTEGER";
    }

    static String twoPatterns(Object first, Object second) {
        return first instanceof String left
                && second instanceof String right
                && left.length() == right.length()
                ? "EQUAL_LEN=" + left + ":" + right
                : "DIFFERENT";
    }

    static String switchEvent(Event event) {
        return switch (event) {
            case null -> "MISSING_EVENT";
            case TextEvent(var text) when text == null -> "MISSING_TEXT";
            case TextEvent(var text) when text.isBlank() -> "BLANK";
            case TextEvent(var text) -> "TEXT=" + text.strip();
            case CountEvent(int count) when count < 0 -> "NEG_COUNT=" + count;
            case CountEvent(int count) -> "COUNT=" + count;
            case PairEvent(TextEvent(var left), TextEvent(var right))
                    when left != null && right != null && left.equals(right) ->
                    "SAME_PAIR=" + left;
            case PairEvent(TextEvent(var left), TextEvent(var right)) ->
                    "PAIR=" + left + "|" + right;
            case PairEvent(var left, var right) -> "MISSING_PAIR_ITEM";
        };
    }

    static String whileLoop(Object input) {
        int sum = 0;
        while (input instanceof String text && !text.isEmpty()) {
            sum += text.length();
            input = text.substring(1);
        }
        return "WHILE=" + sum;
    }

    static String forLoop(Object input) {
        int sum = 0;
        for (; input instanceof String text && !text.isEmpty();
                input = text.substring(1)) {
            sum += text.length();
        }
        return "FOR=" + sum;
    }

    private static void expect(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        expect("positive", "IF=4", positiveIf("Java"));
        expect("positive-int", "NO_STRING", positiveIf(4));
        expect("positive-null", "NO_STRING", positiveIf(null));
        expect("negative-guard", "GUARD=JAVA", negativeGuard("java"));
        expect("negative-guard-null", "NO_STRING", negativeGuard(null));
        expect("and-trim", "AND=Hi", andGate(" Hi "));
        expect("and-blank", "AND_SKIP", andGate("  "));
        expect("and-other", "AND_SKIP", andGate(12));
        expect("or-text", "OR=Hi", orGate("Hi"));
        expect("or-blank", "OR_SKIP", orGate("   "));
        expect("or-null", "OR_SKIP", orGate(null));
        expect("numeric", "NONNEG=2", numericIf(2));
        expect("numeric-negative", "NEG_OR_OTHER", numericIf(-1));
        expect("ternary", "TERNARY=6", ternary(5));
        expect("ternary-other", "NO_INTEGER", ternary("5"));
        expect("two-patterns", "EQUAL_LEN=ab:xy", twoPatterns("ab", "xy"));
        expect("two-patterns-null", "DIFFERENT", twoPatterns(null, "xy"));
        expect("switch-null", "MISSING_EVENT", switchEvent(null));
        expect("switch-empty", "BLANK", switchEvent(new TextEvent("  ")));
        expect("switch-null-text", "MISSING_TEXT", switchEvent(new TextEvent(null)));
        expect("switch-text", "TEXT=Hi", switchEvent(new TextEvent(" Hi ")));
        expect("switch-negative", "NEG_COUNT=-1", switchEvent(new CountEvent(-1)));
        expect("switch-zero", "COUNT=0", switchEvent(new CountEvent(0)));
        expect("switch-pair-same", "SAME_PAIR=A",
                switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("A"))));
        expect("switch-pair-other", "PAIR=A|B",
                switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("B"))));
        expect("switch-pair-null-component", "PAIR=null|B",
                switchEvent(new PairEvent(new TextEvent(null), new TextEvent("B"))));
        expect("switch-pair-null-record", "MISSING_PAIR_ITEM",
                switchEvent(new PairEvent(null, new TextEvent("B"))));
        expect("while-loop", "WHILE=6", whileLoop("abc"));
        expect("while-loop-null", "WHILE=0", whileLoop(null));
        expect("for-loop", "FOR=6", forLoop("abc"));
        expect("for-loop-null", "FOR=0", forLoop(null));

        System.out.println("PASS assertions=" + checks);
        System.out.println("PASS if=" + positiveIf("Java"));
        System.out.println("PASS guard=" + negativeGuard("java"));
        System.out.println("PASS and=" + andGate(" Hi "));
        System.out.println("PASS or=" + orGate("Hi"));
        System.out.println("PASS switch=" + switchEvent(new PairEvent(new TextEvent("A"), new TextEvent("A"))));
        System.out.println("PASS loops=" + whileLoop("abc") + "," + forLoop("abc"));
    }
}
```

**How to run with JDK 21+:**

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 FlowScopeChecklistDemo.java
java FlowScopeChecklistDemo
```

**Verified exact stdout:**

```text
PASS assertions=31
PASS if=IF=4
PASS guard=GUARD=JAVA
PASS and=AND=Hi
PASS or=OR=Hi
PASS switch=SAME_PAIR=A
PASS loops=WHILE=6,FOR=6
```

The program uses an `expect` helper that compares the **actual value against an independent oracle**; on any mismatch, it throws `AssertionError` and cannot print `PASS assertions=31` as shown above. In actual verification, it compiled cleanly with `javac --release 21 -Xlint:all -Werror` and produced the exact **7 lines of stdout**. No external libraries are used.

### How to read the 31 checks

The test cases are distributed across:

- `if` with String, integer, and null selector;
- negated guard with String and null;
- `&&` with non-blank string, blank string, and other object;
- negated `||` with non-blank string, blank string, and null;
- numeric `if/else`, `?:` with Integer/wrong type;
- two patterns in a single `&&` expression;
- switch with null selector, null record component, blank guard, negative/zero counts, equal/different nested records, and null child record;
- two loop styles with String and null.

This does not automatically equate to **100% branch coverage in JaCoCo**. The test suite is designed to verify flow scope and the observable semantics of the selected branches; coverage tools apply their own bytecode-level criteria.

## 12. Intentionally Wrong Program: Five Compile-Time Scope Errors

Save separately as **`FlowScopeCompileErrors.java`** to observe the errors. **Do not include this file in the same compile command as the runnable program in Section 11**, as it is written to fail.

```java
public class FlowScopeCompileErrors {
    static boolean wrongOr(Object value) {
        return value instanceof String text || text.length() > 0;
    }

    static int wrongNegationBranch(Object value) {
        if (!(value instanceof String text)) {
            return text.length();
        }
        return 0;
    }

    static int wrongPostIf(Object value) {
        if (value instanceof String text) {
            System.out.println(text);
        }
        return text.length();
    }

    static boolean wrongTernary(Object value) {
        return value instanceof String text ? true : text.isBlank();
    }

    static String wrongSwitchBranch(Object value) {
        return switch (value) {
            case String text -> text;
            case Integer number -> text;
            default -> "other";
        };
    }
}
```

Compile:

```bash
javac --release 21 -encoding UTF-8 FlowScopeCompileErrors.java
```

Verified output from `javac` shows **5 errors**, all in this category:

```text
error: cannot find symbol
  symbol:   variable text
5 errors
```

| Error location | Why does the compiler reject it? | How to fix |
| --- | --- | --- |
| `wrongOr` | Right-hand side of `||` runs when `instanceof` is false | Use `!(value instanceof String text) || ...` when semantically appropriate, or redesign the logic |
| `wrongNegationBranch` | The `if` branch is true because the pattern did **not** match | Use `text` after an early-return guard, not inside the unmatched branch |
| `wrongPostIf` | After `if`, an unmatched path still exists | Move the logic into the true branch or ensure the false branch exits |
| `wrongTernary` | The false branch of `?:` does not have `text` bound | Use `text` in the true branch, or choose another value for the false branch |
| `wrongSwitchBranch` | Variable `text` belongs to the String case, not the Integer case | Use `number` or a variable from a common scope |

**The diagnostic is a compile error, not a runtime NPE.** Enabling/disabling `-Xlint` does not make out-of-scope expressions valid. Conversely, an expression in valid scope can still encounter runtime errors from nullable components or side effects; therefore, compile-time review must be combined with tests.

## 13. Null-Safety Checklist When Using Record Patterns

A common logical bug in code that compiles successfully is **equating a bound variable with a non-null variable**.

Suppose:

```java
record TextEvent(String text) {}
Object input = new TextEvent(null);
```

With a component pattern:

```java
// The pattern can match while text is null:
if (input instanceof TextEvent(var text)) {
    // text.isBlank(); // NOT safe if text == null.
    System.out.println(text == null ? "missing" : text);
}
```

**Why?** The `TextEvent` record exists so the record pattern matches; `var text` binds a reference component that is allowed to be null. An outer type pattern and an inner component pattern do not have the same null guarantees for every value.

How to handle it:

```java
if (input instanceof TextEvent(var text)
        && text != null
        && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Check in order: record pattern matches → component is non-null → content condition. Do not call `text.strip()` or `text.isBlank()` before establishing the component's nullability.

**Additional checklist:**

- [ ] Can the outer selector be null? `instanceof` with a null selector simply evaluates to false; `switch` needs a `case null` policy or dedicated guard.
- [ ] Can nested child records be null? A nested record pattern requires the child record to exist in order to match.
- [ ] Can an unguarded `var`/type pattern component receive null? Do not assume non-null by default for component variables.
- [ ] Does any guard call a method on a component? Does a null guard run **before** it?
- [ ] Should null be rejected in the record constructor instead of repeating guards everywhere? Apply this only when the business contract genuinely forbids null.
- [ ] Have null/blank inputs and null child records been tested with unit tests?

## 14. Checklist for Reviewing a Pattern Refactoring Pull Request

Before approving a change that uses pattern matching, you can follow this process:

### A. Flow and scope checks

- [ ] Locate all pattern variable declaration sites (`instanceof`, record pattern, `case`).
- [ ] Mark the **pattern true** and **pattern false** paths.
- [ ] With `&&`: use the variable on the right-hand side only when the path reaching it guarantees a match.
- [ ] With `||`: pay special attention to negation; the right-hand side runs when the left-hand side is false.
- [ ] With `?:`: identify the exact branch where the pattern variable is available.
- [ ] With an early-return guard: the unmatched branch must terminate control flow before the variable is used.
- [ ] With loops: use the variable only when the loop condition guarantees the pattern has matched.
- [ ] With switch: a case's guard/body uses only its own case variables; do not use names from another case.

### B. Type, null, and ordering checks

- [ ] Distinguish `null` on the selector from `null` on a record component.
- [ ] Cases with `when` are placed before general cases of the same type to avoid dominance.
- [ ] Guards handling null components come before guards dereferencing components.
- [ ] A switch expression on a sealed hierarchy handles all variants; do not blindly add `default` to hide missing cases.
- [ ] Pattern variables may be declared with the same name in independent scopes, but must not violate declaration/shadowing rules in the active scope.
- [ ] If a variable is needed in multiple places, extract a method or declare a valid shared variable rather than trying to “pull” a pattern variable out of flow scope.

### C. Runnability and test checks

- [ ] `javac --release` level matches the syntax: Java 16+ for `instanceof` type patterns, Java 21+ for final record patterns/pattern switch.
- [ ] Build has no `cannot find symbol` compiler errors related to pattern variables.
- [ ] Tests cover pattern true and false inputs, wrong types, null selector, and nullable components.
- [ ] Tests cover guard true/false, blank cases, numeric boundary values, and null nested child records if the domain allows them.
- [ ] Expected results are defined **independently of actual results**; tests do not just print to the console.
- [ ] After refactoring, business behavior remains unchanged per contract, including error precedence and special branches.

## 15. Common Pitfalls

1. **Using a pattern variable after an `if` that can fall through the false branch.** The compiler does not see the variable as definitely matched.
2. **Using the variable in the true branch of a negation.** `!(value instanceof String s)` being true means `s` is not bound.
3. **Writing `value instanceof String s || s.isEmpty()`.** The right-hand side runs when the pattern is false; the compiler rejects it.
4. **Confusing `&&` with `||`.** The two operators have different short-circuit paths; they cannot be swapped arbitrarily.
5. **Using a pattern variable in the false branch of `?:`.** With a positive pattern in the condition, the false branch does not guarantee binding.
6. **Using one case's pattern variable in another case.** Switch does not automatically share a variable across cases.
7. **Assuming a pattern variable works across the entire lexical block.** Flow scoping depends on control-flow paths, not just braces.
8. **Confusing scope with null safety of a record component.** `var text` can bind a null component inside a matched record.
9. **Forgetting `case null` in a pattern switch.** Even when sealed subtypes are exhaustively handled, a null selector can still throw NPE without an explicit policy.
10. **Placing a general case before a guarded case.** The compiler may report a dominated case; place specific cases first.
11. **Treating every missing branch in a switch as a flow scope error.** A missing subtype is an exhaustiveness error; its cause and fix are different.
12. **Believing the compiler proves every business condition.** The compiler checks static scope rules; it does not guarantee that a guard with side effects or access to a nullable component is always safe.
13. **Using a pattern variable name that collides with a variable already in scope.** This can cause duplicate declaration/shadowing errors or hurt readability despite nearby structure.
14. **Assuming Java 17 already supports final record patterns.** `record` already existed, but deconstruction with record patterns and `when` requires Java 21 as a final feature.
15. **Testing only the success path.** Tests must include false paths, null, false guards, early exits, and loops that never enter their body.
16. **Relying on new syntax to refactor without preserving behavior.** Reordering conditions can change short-circuiting, accessor call order, exceptions, and the chosen branch.

## 16. Self-Check Exercises with Answers

**Exercise 1.** Is variable `s` valid at the end of the method below?

```java
static int length(Object value) {
    if (!(value instanceof String s)) {
        throw new IllegalArgumentException("not a String");
    }
    return s.length();
}
```

*Answer:* **Yes.** The unmatched branch throws an exception, so no path continues to `return s.length()`. All remaining paths have matched `String s`.

**Exercise 2.** Is the following snippet valid?

```java
return value instanceof String s && s.length() > 1;
```

*Answer:* **Yes**, when placed in a valid Java context, because the right-hand side of `&&` runs only when `instanceof` on the left-hand side is true.

**Exercise 3.** Why does the following snippet fail?

```java
return value instanceof String s || s.length() > 1;
```

*Answer:* The right-hand side of `||` runs only if `instanceof` is false; at that point `s` is not bound. The compiler does not allow using `s` there.

**Exercise 4.** In `if (!(value instanceof String s) || s.isBlank()) return;`, can `s` be used on the right-hand side?

*Answer:* **Yes**, because the right-hand side runs only when the negation is false, meaning the original pattern has matched. Since the `if` true branch has `return`, any remaining paths after the `if` have also matched a non-blank `String`.

**Exercise 5.** Does `case TextEvent(var text) when text.isBlank()` guarantee no NPE?

*Answer:* **No.** The pattern variable is in the right scope, but the `TextEvent.text` component can be null. You must handle `text == null` first or enforce non-null via an invariant in the constructor.

**Exercise 6.** In a switch, can `text` from `case String text` be used in `case Integer number`?

*Answer:* **No.** Each case pattern binds variables on its own match path; the Integer case does not bind `text`.

**Exercise 7.** Why can `for (; input instanceof String s && !s.isEmpty(); input=s.substring(1))` use `s` in the update clause?

*Answer:* The update clause runs only after the loop condition is true and the body has executed; the pattern is bound on that path. The Java 21 example in Section 11 is accepted by the compiler.

**Exercise 8.** After a `while (value instanceof String s)` loop, can `s` be used in the next statement simply because it was declared in the condition?

*Answer:* **Not by default.** The loop might not execute at all or might exit when the condition no longer matches; you must re-verify binding along the specific path rather than relying on the variable name appearing in the condition.

**Exercise 9.** Can a nested record pattern be replaced with a type pattern for easier debugging?

*Answer:* **Yes.** You can inspect child objects via accessors and `instanceof`, then split into steps. If logic has many levels and needs to distinguish nulls at each level, snapshot variables can be easier to read than overly deep deconstruction. Behavior and tests must be preserved.

**Exercise 10.** During review, how do you tell whether an error is scope, dominance, or null safety?

*Answer:* Start from the diagnostic: `cannot find symbol` on a pattern variable name is usually scope; `dominated by a preceding case label` is case ordering; `NullPointerException` when calling a method on a component is runtime null safety. For a switch expression missing a variant, the compiler reports that it does not cover all possible input values. Do not use a single fix for all of them.

## 17. Official References

- [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394): type patterns and flow scoping, final since Java 16.
- [JEP 440 – Record Patterns](https://openjdk.org/jeps/440): nested record deconstruction, final since Java 21.
- [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441): case patterns, guards, dominance, and exhaustive switch.
- [JLS Java 21 `6.3 – Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): scope of pattern variables.
- [JLS Java 21 `14.30 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): pattern semantic rules, including record patterns.
- [JLS Java 21 `14.11 – switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch rules and case branches.
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
