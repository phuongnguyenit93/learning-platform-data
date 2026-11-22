# Limits of Patterns in `case` (Java 21)

## 1. Why Understand the Limits of Case Patterns?

Pattern matching for `switch` lets Java handle many object shapes concisely: `case String text` can check the type and bind the variable `text`; `case Point(int x, int y)` can deconstruct the components of a `record`. However, **not just any expression, type, or condition can be placed after `case`**. The compiler checks syntax, type compatibility, branch distinguishability, and the exhaustiveness of the `switch`.

Without understanding these limits, seemingly reasonable snippets like `case List<String> items`, `case String s, Integer n`, `case String s when s.length()`, or placing `case Object o` before `case String s` may fail to compile. A guarded branch may also never be selected even when the type matches; `null` and `default` have their own rules as well.

**Lesson objectives:** Recognize the `case` label forms supported by Java 21, the limits of type patterns/record patterns, guards, and pattern variables; understand dominance errors, duplicate labels, `null`, fall-through, and exhaustiveness; and write a readable, testable `switch`.

The scope is **Java 21 with finalized features**, without assuming preview syntax or extensions from newer JDK versions. `switch` expressions have been standard since Java 14, `instanceof` patterns since Java 16, and pattern matching for `switch` and record patterns since Java 21.

## 2. Distinguishing Case Constants, Case Patterns, `null`, and `default`

In Java 21, a `case` label can be a list of constants, a `null` literal, or a pattern. `default` is a fallback label, **not a pattern**.

| Label Type | Example | Meaning |
| --- | --- | --- |
| Constant | `case 0, 1 -> ...` (appropriate `Integer` or `int` selector) | Selects the branch when the value equals one of the valid constants |
| Type pattern | `case String text -> ...` | Checks whether the object is an instance of `String` and binds the variable `text` |
| Guarded type pattern | `case String text when text.isBlank() -> ...` | After the type matches, checks an additional boolean condition |
| Record pattern | `case Point(int x, int y) -> ...` | Matches `record Point` and extracts its two components |
| Null label | `case null -> ...` | Matches when the selector is `null` |
| Default label | `default -> ...` | Matches remaining non-null inputs in normal contexts |
| Combined null and default | `case null, default -> ...` | Combines the null branch with the fallback branch; used at most once and at the end of the switch |

You cannot write an arbitrary condition directly in the pattern position:

```java
// NOT valid case patterns in Java 21:
case value > 0 -> "positive";
case text.startsWith("A") -> "starts A";
```

These are **intentionally invalid syntax fragments**. When you want to check a property of an object whose type has already matched, write **pattern + `when`**:

```java
// Two illustrative cases, assuming the selector has type Object:
case Integer n when n > 0 -> "positive";
case String text when text.startsWith("A") -> "starts A";
```

`when` is only valid when attached to a **case pattern**. It is not a way to add a condition to every case constant; for example, `case 1 when condition` is not a valid Java 21 label form.

### A `switch` with Constants and Patterns

The example below is a **Java 21 method** using an `Integer` selector:

```java
static String classify(Integer value) {
    return switch (value) {
        case 0, 1 -> "small";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other:" + n;
    };
}
```

For `0`, `-3`, and `8`, the results are `small`, `negative`, and `other:8`, respectively. If `value` is `null`, this expression does not automatically enter the `Integer` pattern; it throws a `NullPointerException` because there is no `case null`. In real programs, explicitly decide whether to allow or reject `null`.

Constants and patterns are **not completely interchangeable**: for example, with a selector whose static type is `Object`, you cannot arbitrarily write `case 42` as an integer constant; matching that integer value can be expressed as `case Integer n when n == 42`.

## 3. Limits on Java Version and Selector Type

### Case Pattern Syntax Is a Java 21 Feature

In Java 17, the following snippet is **not finalized switch pattern syntax**:

```java
return switch (value) {
    case String s -> s;
    default -> "other";
};
```

This example is an expression fragment inside a method and requires **Java 21+** to use as a standard feature. Java 17 already has `switch` expressions on constants/enums and `instanceof String s`, but it cannot compile Java 21 pattern switches with `javac --release 17`.

### The Selector Also Has Limits

In Java 21, the type of the selector expression passed to `switch` must be `char`, `byte`, `short`, `int`, or **a valid reference type**. Selectors with the **primitive types** `boolean`, `long`, `float`, or `double` are not supported in Java 21 `switch`:

```java
long quantity = 5L;
// INVALID in Java 21: selector is primitive long.
switch (quantity) {
    case 5L -> System.out.println("five");
    default -> System.out.println("other");
}
```

The code above intentionally fails to compile in Java 21. Do not confuse this with a `Long` object stored in an `Object`: a switch on a reference type can handle it with an appropriate type pattern.

A pattern must also be **applicable to the static type of the selector**. For example, you cannot place `case Integer n` in a `switch` whose selector has static type `String` and expect an impossible-to-match branch to execute. Change the selector to a more general type only if the input contract can genuinely hold multiple object types; do not widen the type just to silence a compiler error.

## 4. Limits of Type Patterns in `case` Position

A basic type pattern has the form `Type variableName`, for example:

```java
case String text -> "length=" + text.length();
case Number number -> "number=" + number;
```

These are two **illustrative case labels**, not a complete switch. In Java 21:

- **Top-level type patterns use reference types:** `case Integer n` is valid in an appropriate context; `case int n` at the top level is not a valid type pattern in Java 21. Later Java versions may evolve primitive patterns separately, so always verify against your `--release` target.
- **`var` cannot be used as a top-level type pattern:** `case var x -> ...` is not Java 21 syntax equivalent to `case Object x`. `var` can be used in a **component pattern** of a record, such as `case Point(var x, var y)`.
- **Pattern variables require valid Java identifiers:** `case String 123abc` is invalid; names that clash with a local variable already in scope at a conflicting position are also invalid.
- **No assignment expression in the declaration:** `case String s = "x"` is invalid; the variable `s` is bound when the pattern matches.
- **The pattern must be compatible with the selector:** the compiler checks whether the type combination is testable and rejects a branch that is completely meaningless due to incompatible static types.

### Generic Limits: Type Erasure

Suppose the selector has type `Object`:

```java
// Valid in Java 21:
case java.util.List<?> elements -> "size=" + elements.size();
```

However:

```java
// INTENTIONALLY INVALID with Object selector:
case java.util.List<String> elements -> "size=" + elements.size();
```

`List<String>` is not a type that can be fully verified by a runtime type test in this context; Java erases type arguments (`type erasure`) at runtime. `List<?>` checks whether the object is a `List`, **not whether every element is a `String`**.

If you need to process elements, check each element with `instanceof String text` or enforce a strongly typed data contract on the input. Do not use unchecked casts to hide warnings and treat the result as safe pattern matching.

## 5. Record Patterns Only Deconstruct Components of a Matching Record

In Java 21, a record pattern lets you match a record object and extract its components according to its declaration:

```java
record Point(int x, int y) {}

// A case inside switch(Object value):
case Point(int x, int y) -> "(" + x + "," + y + ")";
```

`Point` has exactly two components, `int x` and `int y`, so the pattern must have **exactly two component patterns, in the exact order**. Java checks that each component's type is compatible.

Examples of invalid syntax:

```java
// INTENTIONALLY INVALID: Point has two components, one component is missing.
case Point(int x) -> "x=" + x;

// INTENTIONALLY INVALID: String is not a record declared with components x, y.
case String(int x, int y) -> "wrong";
```

Inside a record pattern's components, `var` can be used for type inference:

```java
case Point(var x, var y) -> x + y;
```

The two variables `x` and `y` are inferred as `int`. This is **component pattern syntax**, not proof that `case var value` is valid at the top level.

A record pattern can nest another record pattern if the components actually have the corresponding types:

```java
record Segment(Point start, Point end) {}

// Illustrative snippet inside switch(Object value):
case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
        "from " + x1 + "," + y1 + " to " + x2 + "," + y2;
```

This is illustrative code requiring `Point` and `Segment` to be declared in a valid scope, not a standalone runnable file. Record patterns **do not automatically deconstruct private fields of a regular class**, are not regular expressions, and do not bypass nullability rules for nested data.

If a reference component can be `null`, check the matching rules of the **specific component pattern** and the data contract; do not assume every nested pattern automatically filters out `null`. A readable design is to use a record type branch (`case Segment segment`) and then check accessors when you need to distinguish internal `null` values.

## 6. Limits of Multi-Element `case` Labels

### Multiple Constants Can Be Grouped in One Branch

With a valid `Integer` or `int` selector:

```java
case 0, 1 -> "small";
```

A label can carry a **list of constants**; the constants must be compatible with the selector and must not duplicate values from another label in the same switch.

### Do Not Combine Multiple Patterns with Bound Variables in One Label

The following syntax is **invalid in Java 21**:

```java
// INTENTIONALLY INVALID (Java 21):
case String s, Integer n -> "text or integer";
```

If the selector is a string, `s` is bound while `n` is not; if the selector is an integer, the reverse happens. There is no safe way for a single branch body to reference those two variables without knowing which pattern matched. In Java 21, a `case` label with patterns structured like this must be written as **separate labels**:

```java
case String s -> "text: " + s;
case Integer n -> "integer: " + n;
```

These snippets are illustrative labels. If you only want a shared result and do not need the variables, extract the common logic into a helper method called from each branch.

Also avoid stacking multiple colon-style (`:`) labels before a branch body that uses a pattern variable: control flow could reach that body from another label where the variable has not been bound. Java 21 rules forbid these ambiguous cases.

Example intentionally invalid due to fall-through in a `switch` statement:

```java
// INTENTIONALLY INVALID: can fall through from the String branch into the Integer branch.
switch (value) {
    case String s:
        System.out.println(s); // No break.
    case Integer n:
        System.out.println(n);
        break;
    default:
        break;
}
```

Use independent `->` branches to avoid fall-through, or structure statement groups so that no execution path leaves a pattern variable uninitialized. In introductory code, prefer `->`.

## 7. Limits of `when` Guards

`when` adds a boolean condition **after the pattern has matched**:

```java
case String text when text.isBlank() -> "blank";
case String text -> "text: " + text;
```

In the first case, Java verifies that the selector is a `String` and binds `text` before evaluating `text.isBlank()`. If the guard evaluates to false, that branch does not apply and Java continues checking subsequent cases in order.

A guard must have type `boolean` or `Boolean` (if `Boolean` is null and gets unboxed, it can throw a `NullPointerException`). Conditions that do not return a boolean are syntactically/semantically invalid:

```java
// INTENTIONALLY INVALID: length() returns int, not boolean.
case String text when text.length() -> "wrong";
```

Fix it to `text.length() > 0` or another explicit boolean condition. In Java 21, the guard keyword is `when`, not `if`. Constant `false` guards are rejected; constant `true` guards can cause the branch to be treated as unguarded for dominance purposes and are rarely useful.

Guards also have restrictions on external local variables or parameters: referenced variables (not declared by the pattern itself) must satisfy the `final` or effectively final requirement per the JLS. Do not write guards that assign to outer variables or rely on side effects; doing so easily violates language rules and makes case selection unpredictable.

### A Guard Does Not Replace a Catch-All Branch

```java
// Assuming the selector can be any Integer.
case Integer n when n > 0 -> "positive";
```

This branch only matches positive integers; `0`, negative values, or other types need an appropriate handling branch. Add `case Integer n -> ...` afterward when you want to cover the remainder of the `Integer` type itself.

**Do not let a guard dereference nullable data without checking first.** `case Box b when b.value().isBlank()` is unsafe if `Box.value()` can be `null`, even though `b` itself matched the type.

## 8. Dominance: Limits on Branch Ordering

An earlier case **dominates** a later case when the compiler determines that the earlier case can match every value that the later case matches. That causes a **compile-time error** because the later branch can never be selected by pattern-matching logic.

### General Pattern Placed Before a Specific Pattern

```java
// INTENTIONALLY INVALID:
return switch (value) {
    case CharSequence sequence -> "sequence";
    case String text -> "string"; // Unreachable.
    default -> "other";
};
```

`String` is a subtype of `CharSequence`, so every `String` already matches the first branch. Fix:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence sequence -> "sequence";
    default -> "other";
};
```

These are expression fragments inside a method with an appropriate selector type (such as `Object value`). Add `case null` when the contract accepts `null`.

### Guarded Branch Placed After an Unguarded Branch of the Same Type

```java
// INTENTIONALLY INVALID:
return switch (value) {
    case String text -> "any";
    case String text when text.isBlank() -> "blank"; // Dominated.
    default -> "other";
};
```

Fix by placing the special case first:

```java
case String text when text.isBlank() -> "blank";
case String text -> "any";
```

### A Pattern Can Dominate a Constant Too

In a `switch` with an `Integer` selector, if an unguarded `case Integer n` appears before `case 42`, then `case 42` is dominated. Order them as **specific constants → guarded patterns → unguarded patterns** when all three apply.

The compiler does not solve arbitrary logical inference over guard conditions. Therefore, even if two guards can overlap mathematically, you must design the order according to business intent and write tests.

### Unconditional Branches and `default`

If the selector has type `Object`, an unguarded `case Object o` branch is an **unconditional pattern** for the selector type; it acts as a catch-all and cannot be paired with a trailing `default` acting as an equivalent fallback. Keep exactly one way to handle the remaining values, along with a dedicated policy for `null` when needed.

## 9. `null`, `default`, and Duplicate Labels

`case null` **is not a pattern**; it is an explicit way to represent a `null` input for a reference-type switch. In Java 21, in a typical pattern switch, `default` does not automatically accept `null`: if there is no appropriate null-handling case, a `null` selector results in a `NullPointerException`.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text";
        default -> "other";
    };
}
```

In some problems, `null` and the remaining values share the same meaning; Java 21 allows a combined label:

```java
static String describeCombined(Object value) {
    return switch (value) {
        case String text -> "text";
        case null, default -> "other-or-missing";
    };
}
```

The `case null, default` label must be the **last label**; no other labels may follow it. It should only be used when you intentionally want to combine those two situations.

Limits to remember:

- A switch cannot have two `null` labels or two `default` labels.
- You cannot repeat a `case` constant with the same value.
- Placing `default` before a case pattern or `case null` is a compile-time error in Java 21.
- `case null, default` must be at the end and cannot coexist with another `default`.
- A pattern determined by the compiler to be unconditional for the selector acts as a catch-all branch, so adding `default` can be treated as duplicate coverage.

Do not use `default` to hide structural gaps: with a `sealed` hierarchy where you want to be notified when a new subtype is added, listing all specific patterns lets you benefit from exhaustiveness checking.

## 10. A Complete Example: Valid Cases and Proper Ordering

Create the file `CasePatternLimits21.java`:

```java
import java.util.List;

public class CasePatternLimits21 {

    record Point(int x, int y) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text=" + text.strip();

            case Point(int x, int y) when x == 0 && y == 0 ->
                    "origin";

            case Point(int x, int y) ->
                    "point=" + x + "," + y;

            case List<?> list ->
                    "list=" + list.size();

            case Integer n ->
                    "int=" + n;

            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe(" Java "));
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(List.of("a", "b")));
        System.out.println(describe(7));
        System.out.println(describe(1.5));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 CasePatternLimits21.java
java CasePatternLimits21
```

Output:

```text
null
blank
text=Java
origin
point=2,3
list=2
int=7
other
```

**Reading this through the limits we learned:**

- `case null` is an explicit branch for `null`, independent of `default`.
- The guarded `String` case comes before the general `String` case; the variable `text` is only used in the matching branch.
- The record pattern `Point(int x, int y)` has exactly two components; the origin `(0,0)` case comes before the catch-all `Point` case.
- `List<?>` is a testable type when the selector is `Object`; it makes no assumptions about the specific element type.
- `Integer` is distinct from `Double`, so `7` enters `int=7` while `1.5` goes to `default`.
- The `switch` expression has `default` to cover other object types when the selector has type `Object`.

The dominance and type-mismatch errors illustrated earlier are **separate error-testing exercises**; they are not included in this complete runnable program.

## 11. Exhaustiveness and Case Limits on a Sealed Hierarchy

A `switch` expression must produce a result or throw an exception in every valid case. With an `Object` selector, `default` usually covers all other types. With a `sealed interface`, the compiler knows which direct subtypes are permitted, so it can check exhaustiveness of the case patterns **without needing `default`**.

Create the file `SealedCaseCoverage21.java`:

```java
public class SealedCaseCoverage21 {

    sealed interface Result permits Success, Failure {}

    record Success(int value) implements Result {}

    record Failure(String reason) implements Result {}

    static String status(Result result) {
        return switch (result) {
            case null -> "missing";

            case Success(int value) when value < 0 ->
                    "invalid-success";

            case Success(int value) ->
                    "success:" + value;

            case Failure(String reason) ->
                    "failure:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(status(null));
        System.out.println(status(new Success(-1)));
        System.out.println(status(new Success(5)));
        System.out.println(status(new Failure("timeout")));
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 --release 21 SealedCaseCoverage21.java
java SealedCaseCoverage21
```

Output:

```text
missing
invalid-success
success:5
failure:timeout
```

**Why is `default` not needed?** `Result` is a `sealed` type with two variants, `Success` and `Failure`. There is an unguarded case for each variant; the guard on `Success` simply prioritizes the negative-value case, while the unguarded `Success` case handles the rest. `case null` explicitly handles a `null` reference. If you kept only `case Success(int value) when value < 0` and removed the unguarded `case Success(int value)`, the switch would fail to cover non-negative `Success` values.

Try adding `record Pending() implements Result {}` and listing it in `permits` without adding a case: the compiler will report that the `switch` expression is not exhaustive. That is your signal to handle the new variant. When a hierarchy is genuinely open, `default` or another catch-all branch is required.

For a `switch` statement using patterns in Java 21, many forms are treated as an **enhanced switch** and must also be exhaustive; do not assume that only `switch` expressions require exhaustiveness.

## 12. Common Errors and Fixes

| Code or Idea | Problem | How to Fix |
| --- | --- | --- |
| `case int n` at top level (Java 21) | Top-level primitive type patterns are not supported | Use `case Integer n` when the selector is appropriate |
| `case var x` | `var` is not a top-level type pattern in Java 21 | Specify a reference type, e.g., `case String x` |
| `case List<String> xs` with `Object` selector | Generic type arguments cannot be checked at runtime | Use `case List<?> xs` and check elements if needed |
| `case Point(int x)` for `record Point(int x, int y)` | Wrong number of components | Provide exactly two component patterns |
| `case String s, Integer n` | Multiple patterns with bound variables in one label | Split into two separate cases |
| `case 1 when condition` | Guards must be attached to a case pattern | Use a plain constant or `Integer n when ...` |
| `case String s when s.length()` | Guard returns `int` | Use `s.length() > 0` |
| `case String s when false` | Constant `false` guard is rejected | Remove the unreachable branch and write a real condition |
| `case CharSequence cs` before `case String s` | Later case is dominated | Place the `String` case first |
| `case String s` before `case String s when ...` | Later guarded case is dominated | Place the guarded case before the general case |
| `case Integer n` before `case 42` with `Integer` selector | Unguarded pattern already covers constant `42` | Place specific constants before the pattern |
| Repeated `case null` | Duplicate null label | Keep only one null label |
| `default` followed by `case String s` | `default` appears before a pattern | Move `default` to the end |
| `case null, default` followed by another case | Combined label must be last | Move it to the end or split intentionally |
| Primitive `long` or `double` selector | Java 21 does not support those selector types | Review the input type; for an appropriate reference type, use a type pattern |
| Using a pattern variable in another case | Variable is only in scope for its matching case/guard | Use the variable name bound by the matching pattern itself |
| Guard allows a null component and calls a method on it | May throw `NullPointerException` | Check the component first or enforce a non-null invariant |

Most errors are caught **at compile time**, but a guard that throws an exception or an unclear null contract may only surface at runtime. Therefore, verify both compilation and runtime execution paths.

## 13. Safe Case Pattern Design Workflow

A short checklist before writing a `switch` in Java 21:

1. **Determine the selector type** and the values that can actually arrive, including `null`. Do not change the static type to `Object` if the data domain can be modeled more accurately.
2. **List the label types needed:** case constants for valid fixed values, type patterns for type branching, record patterns when the data is a record, and `case null` for `null` per the contract.
3. **Check applicability:** pattern types are compatible with the selector, generics are testable, and records have the exact component count and types.
4. **Separate branches with bound variables:** do not combine multiple patterns with variables into one Java 21 case. For colon-grouped `switch` statements, avoid fall-through across branches that require pattern variables.
5. **Order from specific to general:** specific constants and guarded patterns before broad type patterns; avoid dominance.
6. **Decide on `null` and `default`:** give them clear semantics, and do not add `default` arbitrarily when an unconditional case already exists or when you want the compiler to check exhaustiveness on a sealed hierarchy.
7. **Check exhaustiveness:** every `switch` expression and enhanced `switch` statement must cover all valid cases.
8. **Run test cases:** `null` values, constant cases, true/false guards, subtypes, unsupported inputs, and intentional syntax-error checks.

When refactoring, keep each branch short and readable; move long computations or side effects into clearly named methods. Do not turn every problem into a giant `switch` just because Java supports patterns.

## 14. Practice Exercises

**Exercise 1 — Distinguish labels:** Given `case 0, 1`, `case Integer n`, `case Point(int x, int y)`, `case null`, and `default`, identify which are constants, which are patterns, and which are special labels; describe the required selector type.

**Exercise 2 — Fix invalid patterns:** Rewrite `case var x`, `case List<String> xs` (with `Object` selector), and `case Point(int x)` (`Point` has two components) into valid syntax. State the language limit behind each error.

**Exercise 3 — Ordering and dominance:** Create a `switch` with `case CharSequence cs` before `case String text` and observe the error. Then try placing `case String s` before `case String s when s.isBlank()`, and fix it. Explain not only the order, but also the subsumption relationship between the patterns.

**Exercise 4 — Null and default:** Using Java 21, write two versions: one with a separate `case null` and `default`, and one with `case null, default` at the end. Test with `null`, `String`, and `Integer`, and compare the semantics of both approaches.

**Exercise 5 — Grouped labels:** With an `Integer` selector, write `case 0, 1`, `case Integer n when n < 0`, and `case Integer n`. Then try grouping `case String s, Integer n` with an `Object` selector to observe the syntax/variable-initialization error, and split them into two cases.

**Exercise 6 — Exhaustiveness:** Run `SealedCaseCoverage21`, remove the unguarded `Success` case, and try to compile. Add a `Pending` subtype to `Result` and identify the missing case.

**Exercise 7 — Selector limits:** Write a `switch` with a primitive `long` selector under `--release 21` to observe the error, then use `Object value = 5L` and `case Long n` to branch on a reference type. Explain the difference between a primitive selector and a boxed value inside `Object`.

### Self-Check Questions

- Why is `case 1, 2` valid while `case String s, Integer n` is disallowed in Java 21?
- Which part of `case String s when s.isBlank()` binds the variable `s`? When is the guard evaluated?
- Why does `case List<?> xs` not prove that every element is a `String`?
- When does a case pattern dominate a case constant or another pattern?
- How do `case null`, `default`, and `case null, default` differ?
- Why is a set of cases consisting only of guarded branches usually insufficient to prove exhaustiveness?
- When does `sealed` allow you to omit `default` in a principled way?
- Why do pattern variables in colon-style `switch` statements restrict fall-through?

Once you can answer these and explain why the non-compiling examples fail, you have mastered the key limits for designing **case labels** accurately in Java 21.

## 15. Official References

- [Java Language Specification 21 — `14.11 Switch Statement, Switch Blocks`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case label forms, ordering, compatibility, dominance, and exhaustiveness.
- [Java Language Specification 21 — `14.30 Patterns`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, applicability, and matching rules.
- [Java Language Specification 21 — `15.28 Switch Expressions`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): how `switch` acts as a value-producing expression.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): practical examples of dominance, guards, and `null`.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): design of the finalized Java 21 feature.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns and components.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `switch` expressions, arrows, and `yield`.

Always use syntax matching your project's Java version—for example, `javac --release 21` when using finalized pattern switches—and treat every compile error in the "intentionally invalid" examples as a lesson in the language's constraints.
