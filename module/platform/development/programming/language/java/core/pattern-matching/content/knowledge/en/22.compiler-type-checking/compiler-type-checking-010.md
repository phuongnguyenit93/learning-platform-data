# Reading javac Pattern Warnings and Errors (Java 21)

## 1. Goal: understand compiler messages, fix the right root cause

When learning **pattern matching** in Java, many mistakes are caught at compile time, before the program runs. For example, a `case` may be shadowed by a more general branch, a `switch` may fail to cover all types, a pattern variable may be used out of scope, or a record pattern may have the wrong number of components. These errors are directly tied to how the Java compiler checks **types**, **control flow**, and **pattern matchability**.

This lesson guides you through reading **`javac`** diagnostics, distinguishing `error`, `warning`, and `note`, understanding common root causes, and modifying code with verification. The focus is on **type patterns**, **record patterns**, **pattern matching for `switch`**, and `when` guards.

After this lesson, you will be able to:
- Read the file location, line number, `^` marker, and message from `javac`.
- Use `--release 21`, `-Xlint:all`, `-Xlint:unchecked`, and `-Xdiags:verbose` for their intended purposes.
- Distinguish **errors that must be fixed** from **warnings whose risk should be evaluated**.
- Fix common pattern errors: *dominated case*, *non-exhaustive switch*, *cannot find symbol*, wrong record arity, non-reifiable generic types, and non-boolean guards.
- Test after every fix instead of merely silencing the message.

**Version scope:** `instanceof` with type patterns has been a standard feature since Java 16. **Record patterns (JEP 440)** and **pattern matching for `switch` (JEP 441)** are standard features starting in **Java 21**. To run the official examples in this lesson, use **JDK 21 or later** with `javac --release 21`. `--enable-preview` is not needed for features that are already finalized in Java 21.

## 2. How to read a javac diagnostic

For example, a diagnostic looks like this:

```text
BadOrder.java:8: error: this case label is dominated by a preceding case label
            case String s -> "string";
                 ^
1 error
```

This is an **illustrative format** (the filename, line number, spacing, and `^` position depend on the specific code and compiler version). Each part means:

| Part | Meaning | What to do |
| --- | --- | --- |
| `BadOrder.java` | The source file where `javac` reports the error | Open that exact file; do not guess from another file |
| `:8:` | The line in the file referenced by the compiler | Read a few preceding lines as well, especially earlier cases |
| `error: ...` | The error causing compilation to fail | Identify which language rule was violated |
| Reprinted line of code | Where the compiler detected the issue | Compare with case ordering / selector type |
| `^` | Position highlighted by the compiler | This is the detection point, not necessarily the root cause |
| `1 error` | Number of errors in this compilation pass | Fix and recompile to see the updated status |

**Key point:** Where `javac` points is sometimes only a *symptom*. For a `dominated` error, the compiler points to `case String`, but the **root cause** is the general case placed before it. For a `cannot find symbol` error, the location where the variable is not found may be due to the pattern being declared in a conditional branch not guaranteed to have matched.

### How error, warning, and note differ

- **`error`:** Violates a compilation rule, such as a `switch` missing coverage or an invalid type pattern. `javac` does not produce a successful build from source containing such an error. Do not address it by disabling lint flags.
- **`warning`:** The compiler detects a risk or situation worth reviewing, such as a generic cast that cannot be fully checked at runtime. Typically, the build can still succeed if `-Werror` is not used.
- **`note`:** Additional information, sometimes suggesting `-Xlint:...` flags to see detailed warnings. A note is not automatically equivalent to an error.
- **`-Werror`:** When enabled, any warning causes compilation to fail; therefore, you must distinguish the *cause of the warning* from the build policy that treats warnings as errors.

Do not conclude that "pattern matching is broken" just because a warning appears in the same file. Read the exact diagnostic type and the expression that caused it.

## 3. Useful javac commands when investigating

Compile a Java 21 file:

```bash
javac --release 21 JavacPatternDiagnosticsDemo.java
```

Enable warnings and detailed diagnostics:

```bash
javac --release 21 -Xlint:all -Xdiags:verbose JavacPatternDiagnosticsDemo.java
```

Focus only on unchecked operations:

```bash
javac --release 21 -Xlint:unchecked JavacPatternDiagnosticsDemo.java
```

In a test/CI environment where warnings should be treated as errors:

```bash
javac --release 21 -Xlint:all -Werror JavacPatternDiagnosticsDemo.java
```

The commands above are **separate ways to run**, not meant to be executed simultaneously. For the intentionally broken code snippets below, place them in an appropriate demo file and run the compiler to observe the error; do not paste intentionally broken snippets into a complete program.

**Option explanations:**
- `--release 21`: compiles against the Java SE 21 language and APIs on a JDK that supports this target; it does not by itself guarantee the runtime machine has Java 21.
- `-Xlint:all`: tells `javac` to emit all supported warning categories, not only pattern-related warnings.
- `-Xlint:unchecked`: highlights generic casts/operations that cannot be verified as safe at compile time.
- `-Xdiags:verbose`: requests a more detailed diagnostic format; it does not change Java semantics or automatically fix errors.
- `-Werror`: makes the build fail if any warning occurs; it does not turn an unsafe cast into a safe one.

Check the compiler version with `javac -version`. With Java 21, use `case T x when ...`; examples of `switch` and record patterns from earlier *preview* releases may use different syntax. Do not enable `--enable-preview` out of habit to "fix" errors in Java 21 code whose features are already finalized.

## 4. Working example: a program without pattern errors

Create the file **`JavacPatternDiagnosticsDemo.java`**:

```java
public class JavacPatternDiagnosticsDemo {

    sealed interface Result permits Message, Count {}

    record Message(String content) implements Result {}

    record Count(int value) implements Result {}

    static String describe(Result value) {
        return switch (value) {
            case Message(String s) when s == null ->
                "message=null";

            case Message(String s) when s.isBlank() ->
                "message=blank";

            case Message(String s) ->
                "message=" + s;

            case Count(int n) when n < 0 ->
                "count=negative";

            case Count(int n) ->
                "count=" + n;

            case null ->
                "null input";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Message("ok")));
        System.out.println(describe(new Message(" ")));
        System.out.println(describe(new Message(null)));
        System.out.println(describe(new Count(-2)));
        System.out.println(describe(new Count(3)));
        System.out.println(describe(null));
    }
}
```

Compile and run:

```bash
javac --release 21 -Xlint:all -Xdiags:verbose JavacPatternDiagnosticsDemo.java
java JavacPatternDiagnosticsDemo
```

**Expected stdout:**

```text
message=ok
message=blank
message=null
count=negative
count=3
null input
```

Why this code compiles:

1. `Result` is a `sealed interface`, permitting only the two child records `Message` and `Count`.
2. Case `Message(String s) when s == null` handles a `null` string component.
3. Case `Message(String s) when s.isBlank()` handles empty/whitespace strings, after null has already been handled.
4. The unguarded case `Message(String s)` handles all remaining `Message` values.
5. Case `Count(int n) when n < 0` handles negative values; the unguarded case `Count(int n)` handles all remaining `Count` values.
6. `case null` handles a `value == null` selector.
7. The unguarded cases cover every subtype of `Result`, so this switch expression is **exhaustive** even without `default`.

**Distinguishing two kinds of null:** `case null` catches a null selector itself. However, the component `String s` inside `Message(String s)` can still be null: at the component position declared as type `String`, this pattern is unconditional. Do not confuse this with `null instanceof String`, which evaluates to `false`.

This program is a complete runnable example; the error snippets below are examples that **intentionally do not compile** for practicing diagnostic reading.

## 5. Error: case label is dominated by a preceding case label

### Erroneous code

```java
// Intentionally incorrect example, placed inside a method receiving Object value:
return switch (value) {
    case CharSequence seq -> "char sequence";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
```

`String` implements `CharSequence`, so every `String` value already matches `case CharSequence seq`. The subsequent `case String text` can never be selected.

An actual `javac` diagnostic is:

```text
error: this case label is dominated by a preceding case label
```

This is an **error**, not a warning. It stems from the subsumption/dominance relationship between patterns.

### Fix

Place the specific case before the general case:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence seq -> "char sequence";
    case null -> "null";
    default -> "other";
};
```

Similarly, with record patterns:

```java
// Wrong order if these cases are in the same switch:
case Message(String s) -> "any message";
case Message(String s) when s.isBlank() -> "blank";
```

The unguarded `Message` case already covers the guarded branch after it. **Fix:** guarded case first, unguarded case after. For two patterns of the same subtype with different guards, include a fallback case if the guards do not cover all values.

**Tip for reading the error:** When the compiler points to a dominated case, look **upward** to find the parent case or unguarded case that already accepts all of its values.

## 6. Error: the switch expression does not cover all possible input values

### Erroneous code

```java
// value has type Object:
return switch (value) {
    case String text -> text;
};
```

`Object` can also hold `Integer`, `Double`, custom records, etc. `case String` cannot cover the entire value domain. A diagnostic emitted by `javac` is:

```text
error: the switch expression does not cover all possible input values
```

### Fix

Add cases for the types to handle and a fallback for the rest:

```java
return switch (value) {
    case String text -> text;
    case Integer number -> "number=" + number;
    case null -> "null";
    default -> "other";
};
```

If the selector is a closed **sealed hierarchy**, write cases for all permitted subtypes. You do not necessarily need to add `default`: letting the compiler check exhaustiveness helps catch new subtypes that have not been handled yet when recompiling.

**Distinguishing statements:** Java 21 also requires **enhanced switch statements** (for example, a switch with pattern labels) to be exhaustive. For traditional switch statements with only constant labels, exhaustiveness rules may differ. Do not mechanically apply the "switch statement doesn't need default" habit to pattern switches.

**A branch with `when` generally does not cover an entire subtype:** `case Count(int n) when n < 0` does not handle `Count(3)`. To be exhaustive, add an unguarded `case Count(int n)` or an appropriate covering pattern.

## 7. Error: cannot find symbol — pattern variable out of scope

### Erroneous code

```java
// Intentionally incorrect example; value has type Object:
if (value instanceof String text) {
    System.out.println(text);
}

System.out.println(text.length());
```

The variable `text` is only bound at locations where Java proves the pattern has matched. After the `if`, that is no longer guaranteed. `javac` emits a diagnostic such as:

```text
error: cannot find symbol
  symbol:   variable text
```

### Fix 1: use the variable inside the matched branch

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a string");
}
```

### Fix 2: exit early when the pattern does not match

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

In Fix 2, after exiting the non-matching case via `return`, the compiler knows the remaining path has matched `String`; the variable `text` is allowed to be used.

**Tip for reading the error:** When encountering `cannot find symbol` for a pattern variable, do not rush to redeclare a variable with the same name. Inspect the **flow scoping** of `instanceof`, `&&`, `||`, `if`, and each `case` in `switch`.

## 8. Error: incorrect number of nested patterns — wrong component count in record pattern

Suppose the record is declared as:

```java
record Pair(int left, int right) {}
```

### Erroneous code

```java
// value has type Object:
if (value instanceof Pair(int left)) {
    System.out.println(left);
}
```

`Pair` declares **two** record components, but the pattern provides only **one** nested pattern. `javac` may report:

```text
error: incorrect number of nested patterns
  required: int,int
  found:    int
```

### Fix

Write one pattern for **each record component**, in the exact declaration order:

```java
if (value instanceof Pair(int left, int right)) {
    System.out.println(left + right);
}
```

Record patterns do not have a syntax to "skip a position" by omitting components. If you only need one component without structural deconstruction, calling the accessor `pair.left()` on a known `Pair` is also a simple option.

**Tip for reading the error:** Cross-check the number and types of components in the `record Name(T1 a, T2 b, ...)` header against the list in `Name(pattern1, pattern2, ...)`. For multi-level nested record patterns, check each record from the outside in.

## 9. Error: generic pattern cannot be safely checked

### Erroneous code

```java
// value has type Object:
if (value instanceof java.util.List<String> items) {
    System.out.println(items.size());
}
```

`List<String>` is a parameterized type that is not reifiable in a way that lets the runtime distinguish `List<String>` from `List<Integer>`. `javac` reports an error like:

```text
error: java.lang.Object cannot be safely cast to java.util.List<java.lang.String>
```

This is an **error** on the `instanceof` pattern in this situation, **not an unchecked warning** that you could just suppress with lint flags.

### Fix

Use a type that can be checked at runtime such as `List<?>`, and check elements when needed:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println("string=" + text);
        } else {
            System.out.println("not a string");
        }
    }
}
```

Here `List<?>` confirms the object is a list, but **does not prove every element is a String**. Checking each element avoids unsafe assumptions about generic types.

**Important distinction:** `instanceof List<String>` on `Object` can be an **error**. Meanwhile, a cast `(List<String>) value` can compile with an **unchecked warning**. The two situations are different and must be fixed according to their actual root cause.

## 10. Error: incompatible types — when guard must return boolean

### Erroneous code

```java
// value has type Object; snippet inside a switch expression:
case String text when text.length() -> text;
```

`text.length()` has type `int`, whereas `when` requires a conditional expression of type `boolean`. `javac` may report:

```text
error: incompatible types: int cannot be converted to boolean
```

### Fix

Write an explicit boolean comparison:

```java
case String text when text.length() > 0 -> text;
```

You also need appropriate cases to handle empty strings, null, and other object types. If a guard calls a method that can throw an exception, such as `text.isBlank()` or `text.length()` on a possibly null variable, check for null first or use a safe condition.

In Java 21, the guard syntax is **`when`**. Some tutorials from earlier Java preview versions may use different syntax; always verify which Java version you are compiling against before copying.

## 11. Warning: unchecked cast — different from a pattern error

Consider the method:

```java
// Illustrative snippet, not a pattern:
static java.util.List<String> asStrings(Object value) {
    return (java.util.List<String>) value;
}
```

When compiled with `-Xlint:unchecked`, `javac` may emit:

```text
warning: [unchecked] unchecked cast
  required: java.util.List<java.lang.String>
  found:    java.lang.Object
```

Some versions display the category, alignment, or annotations differently. The essence remains that the compiler **cannot prove** the cast from `Object` to `List<String>` is safe with respect to element types. The runtime only checks the raw type such as `List`, without guaranteeing the list contains only `String` elements.

### Safer handling

If the goal is to accept only `String` elements and reject others:

```java
static java.util.List<String> copyStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        throw new IllegalArgumentException("Not a list");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : items) {
        if (item instanceof String text) {
            result.add(text);
        } else {
            throw new IllegalArgumentException("Non-string element");
        }
    }
    return result;
}
```

This approach returns a new list after checking each element. If the input is empty, it still creates a valid empty list; if `null` is present, this example intentionally rejects it because `null instanceof String` is `false`. Whether to accept or reject null is an application design decision.

**Do not just add `@SuppressWarnings("unchecked")` to hide the risk.** This annotation only makes sense if an external invariant/verification already exists and the risk is accepted; it does not make the cast safe. In CI with `-Werror`, such warnings can fail the build.

## 12. Grouping diagnostics for quick fixes

| Diagnostic or symptom | Common kind | Pattern cause | How to fix |
| --- | --- | --- | --- |
| `this case label is dominated ...` | **error** | Broader case placed before narrower case | Put specific/guarded case first or remove shadowed case |
| `switch expression does not cover ...` | **error** | Not exhaustive | Add missing subtypes, fallback, or appropriate default |
| `cannot find symbol: variable x` | **error** | Pattern variable outside flow scope | Use inside a definitely matched branch; refactor condition |
| `incorrect number of nested patterns` | **error** | Record pattern has too few/many components | Align with record header |
| `cannot be safely cast to List<String>` | **error** | Generic type cannot verify element types at runtime | Use `List<?>` and check elements |
| `int cannot be converted to boolean` | **error** | `when` guard does not produce a boolean | Use a boolean comparison/expression |
| `unchecked cast` | **warning** | Generic cast cannot be verified as safe | Validate data, copy/validate, or improve type design |
| `warnings found and -Werror specified` | **error due to build policy** | Warnings exist while `-Werror` is enabled | Address the underlying warning first |
| Message requiring `--enable-preview` | Depends on JDK and feature | Code uses preview/different version syntax | Check JDK and feature status; finalized Java 21 patterns need no preview |

A cascade of errors can originate from **a single initial syntax or type error**. Fix the earliest cause, recompile, and then inspect any remaining errors. Do not mistake dozens of secondary diagnostics for dozens of independent problems.

## 13. Practical workflow when javac reports a pattern error

**Step 1 — Record the command and version:** Run `javac -version`. Identify the `--release`/`--source`, preview flags, and lint flags in use. For example, Java 21 code will not run by default on a Java 17 compiler that lacks finalized Java 21 features.

**Step 2 — Read the first error and related source:** Note the file, line, diagnostic text, and nearby cases/expressions. If the message says `dominated`, inspect preceding branches; if `not exhaustive`, inspect the entire hierarchy and fallback.

**Step 3 — Identify the check category:** Is the error syntax, static typing, flow scoping, record deconstruction, dominance, or exhaustiveness? Each category has a different fix; do not fix by blindly casting.

**Step 4 — Make minimal, semantically sound fixes:** Reorder cases, add fallback cases, adjust record arity, write a boolean guard, or move variables into valid scope. Do not add `default` indiscriminately if you want the compiler to keep reminding you about new subtypes of a sealed hierarchy.

**Step 5 — Recompile with useful flags:** Re-run `javac --release 21 -Xlint:all -Xdiags:verbose` and separate remaining warnings from errors. If your team uses `-Werror`, identify the root warning and address it at the source.

**Step 6 — Test at runtime:** Once the build passes, run tests for specific branches, fallback branches, null selector, null record components, guard boundary values, and invalid generic data. The compiler checks that patterns obey language rules, but it does not guarantee all business rules are correct.

### A short checklist when reading a case pattern

- What is the static type of the selector? Can it be `null`?
- Is the pattern checking the outer type or record components?
- Has a preceding case already covered the current case?
- Do guarded cases have a corresponding unguarded/fallback case?
- Is any subtype of the sealed hierarchy still unhandled?
- Is the pattern variable used at a point where the compiler knows it has matched?
- Can that generic type be safely checked at runtime?
- Is the diagnostic actually an `error`, `warning`, or `note`?

## 14. Exercises: intentionally trigger errors and re-read javac

**Exercise 1 — Dominance.** In `JavacPatternDiagnosticsDemo`, move `case Message(String s) -> ...` before `case Message(String s) when s == null`. Recompile to observe the dominated error. Then restore the order from specific to general.

**Exercise 2 — Exhaustiveness.** Add `record Failure(String reason) implements Result {}` and update `Result`'s `permits` clause without adding a `Failure` case to `describe`. Recompile to observe the requirement to cover the new subtype. Then add `case Failure(String reason) -> "failure=" + reason;`.

**Exercise 3 — Scope.** Write a method `int length(Object value)` that intentionally uses `text` after an `if (value instanceof String text)` where the non-matching path still reaches the usage. Observe `cannot find symbol`; fix it using an `else` branch or an early `return`.

**Exercise 4 — Record arity.** Change `case Count(int n)` to `case Count(int n, int other)`. `Count` has only one component; read the diagnostic about the number of nested patterns, then fix it back to one component.

**Exercise 5 — Warning vs. error.** Create two methods: one checking `Object` with `instanceof List<String>` and one casting `(List<String>) value`. Run with `-Xlint:unchecked`. Explain why the first causes an error in this case, while the second can produce an unchecked warning. Finally, replace both with `List<?>` and element-by-element checks.

**Remember:** `javac` reports where the error appears, but the programmer needs to read the **type checking/flow checking rules** behind the message. With Java 21 pattern matching, the four most important questions are **can the pattern match, is the branch shadowed, is the variable in scope, and is the switch exhaustive**. Unchecked warnings differ fundamentally from invalid pattern errors; fix the root cause rather than just trying to silence the diagnostic.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java Language Specification SE 21 — Pattern Matching for `instanceof`, `switch` and pattern scopes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
