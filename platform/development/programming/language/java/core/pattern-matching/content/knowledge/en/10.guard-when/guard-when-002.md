# Pattern Syntax with `when` in Java 21

## 1. What Is the `when` Guard Used For?

When using pattern matching in `switch`, a pattern only verifies the **type or shape of the data**. Many scenarios also require an additional condition: a string must not be empty, a number must be positive, coordinates must belong to a certain region, or two record components must satisfy a relationship. In Java 21, you write a **guard** using the contextual keyword `when` right after the case pattern:

~~~java
case String text when !text.isBlank() -> "TEXT:" + text;
~~~

Such a `case` label has **two sequential conditions**:

1. The value in `switch (expression)` must match the **pattern** `String text`. If it does not match, Java does not evaluate the guard.
2. After matching and binding the variable `text`, Java evaluates the **guard** `!text.isBlank()`. Only when the guard returns `true` is this case selected.

If the guard returns `false`, Java continues looking for another `case` label that can match. This differs from a branch being selected and returning `false`; **the guard decides branch selection, not the return value of the branch**.

Lesson objectives:

- Write `case Pattern when booleanExpression -> ...` and the colon form `case Pattern when booleanExpression:` correctly.
- Know where to place `when` and the required result type of the guard.
- Use pattern variables safely in the guard and the case body.
- Combine guards with type patterns, record patterns, and nested patterns.
- Analyze label ordering, dominance, `default`, `null`, and the exhaustiveness requirement of switch expressions.
- Recognize compile errors when the guard is not boolean, when placing a guard on a non-pattern label, or when placing a covering label before a guarded label.

**Version:** this lesson uses the official syntax of **Java 21+** (JEP 441, Pattern Matching for switch). You can use JDK 21 or newer and the command `javac --release 21`, **without needing `--enable-preview`**. The syntax in preview releases of Java 17–20 changed during development, so do not copy Java 21's `when` syntax verbatim and expect it to compile with `--release 17`.

## 2. Syntax Formula: `case` Pattern First, Then `when`

The arrow form used in a switch expression or switch statement:

~~~java
switch (value) {
    case String s when s.isBlank() -> System.out.println("Blank");
    case String s -> System.out.println("String: " + s);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
~~~

This is an **illustrative snippet** inside a method that has an `Object value` variable. The basic formula:

~~~text
case <pattern> when <boolean-expression> -> <expression-or-statement>
case <pattern> when <boolean-expression> :  <statement-group>
~~~

Components:

| Component | Role |
| --- | --- |
| `case` | Starts a selection label |
| `String s` or `Point(int x, int y)` | Pattern that checks the object and introduces variables |
| `when` | Marks the additional *guard* condition |
| `s.isBlank()`, `x > 0 && y > 0` | Conditional expression, must be compatible with `boolean` |
| `->` | Starts a switch rule, with no fall-through |
| `:` | Starts a traditional statement group; fall-through must be controlled |

The syntax places `when` **after the pattern but before `->` or `:`**. Do not write the guard inside the pattern as if it were a component, and do not confuse the expression after `->` with the guard condition.

Valid examples:

~~~java
case Integer number when number > 0 -> "POSITIVE";
case Integer number -> "ZERO_OR_NEGATIVE";
~~~

Example using a record pattern (Java 21):

~~~java
case Point(int x, int y) when x == y -> "SAME_COORDINATES";
~~~

The snippets above are illustrative labels, not standalone programs; to run them, they must be placed inside a `switch` with a selector of an appropriate type and, for the record example, with the declaration `record Point(int x, int y) {}`.

**Syntax limitation:** `when` is a guard for a **case pattern**. You cannot attach a guard directly to a constant-only label or a `null` label:

~~~java
case "yes" when true -> 1;  // INVALID in Java 21
case null when true -> 1;   // INVALID in Java 21
~~~

The two lines above **intentionally do not compile**. If you want to apply an additional condition to a `String` value, you typically use `case String s when ...` and write the logic for the specific constant inside the guard if appropriate; whereas `case "yes"` on its own does not need a guard to match that exact constant.

## 3. How Java Selects a Guarded Case

Suppose we have:

~~~java
return switch (value) {
    case String s when s.isBlank() -> "BLANK";
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "SHORT";
    default -> "OTHER";
};
~~~

This is an excerpt inside a method with parameter `Object value` and return type `String`.

The process of evaluating labels in order:

1. Java evaluates the selector `value` and examines the cases in valid order within the switch block.
2. For the label `case String s when s.isBlank()`, if the value is not a `String`, the guard is skipped and evaluation moves on. If it is a `String`, `s` is bound and `isBlank()` is called.
3. If the guard is true, this case is selected, the rule body after `->` executes, and the switch expression completes.
4. If the guard is false, evaluation continues to try the next case. A value `"hello"` is not blank but has 5 characters, so it matches `case String s when s.length() >= 5`.
5. If both preceding guards are false while the value is still a `String`, the unguarded `case String s` label handles the remaining cases.
6. If it is not a `String`, the `default` label handles other applicable values; `null` must be considered separately.

**A guard is not used to check the type before the pattern.** The first question is always whether the pattern matches; the guard only runs after the pattern has bound its variables. For `null`, the type pattern `String s` does not match, so the guard `s.isBlank()` is not called.

Difference in outcomes:

| Selector value | Pattern and guard | Selected rule |
| --- | --- | --- |
| `"   "` | `String s` matches, `s.isBlank()` is true | `"BLANK"` |
| `"hello"` | First guard is false, `length() >= 5` guard is true | `"LONG"` |
| `"hi"` | Both guards are false, general `String s` pattern matches | `"SHORT"` |
| `12` | Does not match `String` patterns | `"OTHER"` |

A guard returning `false` does **not** mean the program runs the code after `->` and stops there. Java continues selecting an appropriate subsequent label.

## 4. Complete Program: Multiple Guards on `String` and `Integer`

Save the file `GuardWhenSyntaxDemo.java`:

~~~java
public class GuardWhenSyntaxDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG:" + s;
            case String s -> "SHORT:" + s;
            case Integer n when n > 0 -> "POS:" + n;
            case Integer n when n == 0 -> "ZERO";
            case Integer n -> "NEG:" + n;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("hello"));
        System.out.println(classify("hi"));
        System.out.println(classify(7));
        System.out.println(classify(0));
        System.out.println(classify(-3));
        System.out.println(classify(1.5));
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 GuardWhenSyntaxDemo.java
java GuardWhenSyntaxDemo
~~~

Exact output:

~~~text
NULL
BLANK
LONG:hello
SHORT:hi
POS:7
ZERO
NEG:-3
OTHER
~~~

Analysis:

- `case String s when s.isBlank()` handles whitespace-only strings; `"   "` produces `BLANK`.
- `case String s when s.length() >= 5` handles sufficiently long strings **after blank strings have been excluded** by the label above; `"hello"` produces `LONG:hello`.
- `case String s` is the fallback case for strings that do not pass the preceding guards; `"hi"` produces `SHORT:hi`.
- The three `Integer n` labels together classify positive, zero, and negative integers. `n` is bound separately in each case and has type `Integer`.
- `1.5` is a `Double` value when boxed into `Object`, so it does not match `Integer n` and falls into `default`.

Reusing the variable name `s` or `n` across separate cases does not mean a single variable exists across all branches. Each pattern variable is scoped to **its own label**.

## 5. Pattern Variable Scope in the Guard and Rule Body

A convenient feature of `when` is that you can immediately use the variable just introduced by the pattern:

~~~java
case String text when text.length() > 3 -> text.toUpperCase();
~~~

Java does not allow referencing `text` from the guard if the pattern does not bring that variable into scope. In this valid example:

- When the pattern `String text` matches, `text` is bound to the `String` object.
- `text.length()` is a valid call in the guard expression and has type `int`; the comparison `> 3` produces `boolean`.
- When the guard is true, the rule body `text.toUpperCase()` is allowed to read `text`.
- When the guard is false, the rule body does not execute; Java continues checking other cases.

### New Patterns Appearing Inside a Guard

A guard is a real Java expression, so you can also use `instanceof` with a pattern variable, as long as flow scoping rules are followed:

~~~java
case CharSequence cs
    when cs instanceof String text && text.length() >= 3 ->
    "LONG_TEXT:" + text.toUpperCase();
~~~

This is an **excerpt** in a switch selector of type `Object`. `cs` is introduced by the case pattern `CharSequence cs`. The guard tests whether `cs` itself is a `String` and binds `text`. Thanks to short-circuiting `&&`, `text.length()` is only called if `instanceof String text` succeeds. When the **entire guard is true**, `text` can also be used in the rule body.

To test this completely, save `GuardInnerPatternScopeDemo.java`:

~~~java
public class GuardInnerPatternScopeDemo {
    static String classify(Object value) {
        return switch (value) {
            case CharSequence cs
                    when cs instanceof String text && text.length() >= 3 ->
                "LONG_TEXT:" + text.toUpperCase();
            case CharSequence cs -> "OTHER_CHARSEQ:" + cs.length();
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("Hi"));
        System.out.println(classify(new StringBuilder("hello")));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardInnerPatternScopeDemo.java
java GuardInnerPatternScopeDemo
~~~

Output:

~~~text
LONG_TEXT:JAVA
OTHER_CHARSEQ:2
OTHER_CHARSEQ:5
NULL
~~~

Notice the three distinct cases:

1. `"Java"`: matches `CharSequence cs`; the guard confirms `cs instanceof String text` and at least 3 characters; the first rule is selected.
2. `"Hi"`: matches `CharSequence` and `String`, but `text.length() >= 3` is false; Java moves to the unguarded `case CharSequence cs`.
3. `new StringBuilder("hello")`: matches `CharSequence` but does **not** match `String text` in the guard; the right-hand side `text.length()` of `&&` does not run, and the general case handles it.

You cannot use `text` in another `case CharSequence cs` rule or outside the switch just because the same value may have been tested in an earlier guard.

## 6. `when` with Record Patterns: Checking Shape and Component Conditions

A **record pattern** lets you extract a record's components as soon as it matches. A `when` guard can then check relationships between those components.

Example:

~~~java
case Point(int x, int y) when x == y -> "EQUAL:" + x;
~~~

Here `Point(int x, int y)` is a record pattern; the variables `x` and `y` are bound if the record has the matching shape. The guard `x == y` is only evaluated after the record pattern has matched.

Save the complete program `GuardWhenRecordDemo.java`:

~~~java
record Point(int x, int y) {}

public class GuardWhenRecordDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case Point(int x, int y) when x == y -> "EQUAL:" + x;
            case Point(int x, int y) when x > 0 && y > 0 ->
                "POSITIVE:" + x + "," + y;
            case Point(int x, int y) -> "POINT:" + x + "," + y;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Point(3, 3)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(new Point(-2, 4)));
        System.out.println(classify("no"));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenRecordDemo.java
java GuardWhenRecordDemo
~~~

Output:

~~~text
EQUAL:3
POSITIVE:2,5
POINT:-2,4
OTHER
~~~

Explanation:

- `Point(3, 3)` matches the guard `x == y`; returns `EQUAL:3`.
- `Point(2, 5)` does not match the equality guard, but satisfies `x > 0 && y > 0`; returns `POSITIVE:2,5`.
- `Point(-2, 4)` does not satisfy either guard, but still matches the `Point` record structure; goes to the unguarded `case Point(int x, int y)` label.
- `"no"` is not a `Point`; goes to `default`.

**The pattern is responsible for deconstruction**, while `when` expresses additional business conditions. There is no need to manually cast the record or call accessors `x()`, `y()` to retrieve data in matched pattern branches. With nested record patterns, the guard can reference component variables bound in that pattern as long as they are in scope.

## 7. `when` Also Works with Methods Returning Boolean

A guard does not have to be a simple comparison. You can call a business validation method, as long as the call produces a valid Boolean condition.

Save `GuardWhenMethodDemo.java`:

~~~java
public class GuardWhenMethodDemo {
    static boolean accepted(String s) {
        return s.length() >= 4 &&
               s.chars().allMatch(Character::isLetter);
    }

    static String label(Object value) {
        return switch (value) {
            case String s when accepted(s) -> "ACCEPT:" + s;
            case String s -> "REJECT:" + s;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label("a2b4"));
        System.out.println(label("abc"));
        System.out.println(label(23));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenMethodDemo.java
java GuardWhenMethodDemo
~~~

Output:

~~~text
ACCEPT:Java
REJECT:a2b4
REJECT:abc
OTHER
~~~

Here `accepted(s)` only runs **after** `case String s` matches. It returns `true` when the string is at least 4 characters long and all characters are letters. Strings that do not satisfy the condition go to the second `case String s` label.

In practice:

- Use pure, easy-to-understand guard functions without unnecessary side effects; guards may be evaluated while Java is searching for a matching label.
- A guard can call methods and use `&&`, `||`, `!`, and parentheses to express logic, but it must return `boolean` or a value usable as `boolean` according to Java's unboxing rules.
- If a guard throws an exception, the switch does **not** treat it as `false` and move to the next case; the exception propagates through normal execution flow.
- Avoid code that both mutates an object and inspects it in a guard, because that makes branch ordering hard to predict and error-prone.

## 8. The `when` Guard Also Works with Colons

Guard syntax is not limited to `->`. With traditional **switch statement groups**, you can write:

~~~java
case String s when s.isBlank():
    return "BLANK";
~~~

Save the complete program `GuardWhenColonDemo.java`:

~~~java
public class GuardWhenColonDemo {
    static String classify(Object value) {
        switch (value) {
            case null:
                return "NULL";
            case String s when s.isBlank():
                return "BLANK";
            case String s when s.length() > 3:
                return "LONG";
            case String s:
                return "SHORT";
            default:
                return "OTHER";
        }
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("Hi"));
        System.out.println(classify(null));
        System.out.println(classify(1));
    }
}
~~~

~~~bash
javac --release 21 GuardWhenColonDemo.java
java GuardWhenColonDemo
~~~

Output:

~~~text
BLANK
LONG
SHORT
NULL
OTHER
~~~

The difference lies in **the syntax and control flow of the switch body**, not in the meaning of the guard:

- A guard in `case Pattern when condition:` form is still evaluated after the pattern matches.
- The statements after `:` form a statement group; the pattern variable is usable within the corresponding group.
- The colon form allows *fall-through* when the code before the next label completes normally. The example above uses `return` in every branch so it does not fall through to another branch.
- Java also restricts falling through **into** a label that declares a pattern variable, because that variable might not be initialized if the pattern did not actually match.
- The `case ... ->` form is usually easier to reason about because there is no fall-through, especially when handling multiple guarded labels.

**Do not convert `case ... when ... ->` to `case ... :` and remove all `return`/`break` statements** if doing so causes execution to fall through into the next label.

## 9. Label Ordering, Dominance, and Fallback Branches

These two cases are in a valid order:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "STRING";
~~~

The first label is for a special case, and the second covers all remaining `String` values.

Reversing them causes a compile error:

~~~java
case String s -> "STRING";
case String s when s.isBlank() -> "BLANK"; // COMPILE ERROR: dominated
~~~

The unguarded `String s` branch placed first already matches every `String` value. The second branch has no chance of being selected; the compiler reports `this case label is dominated by a preceding case label`. This is an **intentionally invalid snippet**, not runnable code.

Design principles:

- Place specific guarded patterns **before** general patterns of the same type.
- Place subtypes before supertypes when they need to be distinguished, for example `case Integer n when n > 0` before `case Number n`.
- Add an **unguarded** case of the same type or a `default` for values that do not satisfy the condition if needed.
- Do not assume Java will automatically pick the "most specific" branch regardless of case order.
- If two guards have overlapping condition domains, the earlier case takes precedence when both could be true.

### Guards Do Not Replace Exhaustive Coverage

A switch expression must cover all possible values that need to be handled. Even if the static selector type is `String`, the single label:

~~~java
case String s when s.length() > 3 -> 1;
~~~

does **not** cover shorter strings. For a switch expression missing other labels, Java will report a non-exhaustive error. You must add `case String s -> ...`, `default`, or a valid exhaustive design.

For a selector of type `Object`, a `default` is usually required to handle types that do not match any pattern. A switch can be considered exhaustive by the compiler thanks to an unguarded pattern covering the selector type or by covering all sealed subtypes, depending on Java 21 rules.

## 10. `when` Is Not a Way to Handle `null`

The type pattern `String s` does not match `null`; therefore `when s.isBlank()` is not evaluated when the selector is `null`. However, for a switch on a null reference, you must decide separately whether to handle `null` or let an exception occur.

Example:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

This illustrative snippet is inside a method with `Object value` and return type `String`.

- `case null` matches `null`.
- `case String s when ...` does not match `null`; the guard is not called.
- `default` on its own is **not automatically treated as a null-catching branch** in a pattern switch.

Therefore, `case null when ...` is not valid syntax. If you want all nulls to be rejected, you can write `case null -> throw new IllegalArgumentException("null");` or check for null before the switch.

### Boolean Guards and Exceptions

If a guard relies on a method that can throw an error, that error is not converted into a `false` result. Similarly, if a `Boolean` value is used where a `boolean` is required, unboxing from `null` can cause a `NullPointerException`. When designing guards, prefer simple, clear check expressions and avoid introducing unchecked nullable `Boolean` values.

## 11. Common Compile Errors with `when`

The following snippets are **intentionally non-compiling code** tested with `javac --release 21`. They illustrate errors for syntax self-checking, not runnable programs.

### Error 1 — Non-boolean guard

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s when s.length() -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

`s.length()` returns `int`, not a `boolean` condition. The compiler reports:

~~~text
error: incompatible types: int cannot be converted to boolean
~~~

Fix it with a comparison or a method returning boolean, such as `s.length() > 3`.

### Error 2 — Guard on a constant label

~~~java
static int invalid(String value) {
    return switch (value) {
        case "yes" when true -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

The compiler reports:

~~~text
error: guards are only allowed for case with a pattern
~~~

The label `case "yes"` is a constant label, not a type pattern or record pattern. Use `case "yes" -> 1` directly, or use a pattern `case String s when ...` if the condition needs to depend on a pattern variable.

### Error 3 — Guard on `case null`

~~~java
static int invalid(Object value) {
    return switch (value) {
        case null when true -> 1; // COMPILE ERROR
        default -> 0;
    };
}
~~~

The compiler also reports `guards are only allowed for case with a pattern`. Use `case null -> 1` on its own.

### Error 4 — Guarded branch dominated by a preceding branch

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> 1;
        case String s when s.isEmpty() -> 2; // COMPILE ERROR
        default -> 0;
    };
}
~~~

The compiler reports that the label is `dominated`. Swap the order so `isEmpty()` is checked before the general pattern.

### Error 5 — Using a guarded branch's variable in another branch

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> 1;
        case Integer n -> s.length(); // COMPILE ERROR
        default -> 0;
    };
}
~~~

`s` does not exist in the scope of the `Integer` branch. The compiler reports `cannot find symbol: variable s`. Each branch must use variables declared by its own pattern or other variables in valid scope.

### Error 6 — Only one guarded case without other branches

~~~java
static int invalid(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> 1;
    };
}
~~~

The compiler reports:

~~~text
error: the switch expression does not cover all possible input values
~~~

A string of length 0, 1, 2, or 3 does not satisfy the guard. You must add a branch to handle them, such as `case String s -> 0`; for null, consider `case null` depending on the runtime contract.

## 12. Checklist for Using `when` Safely

When reading a guarded case pattern, ask yourself:

1. Is the project compiling with **Java 21+** or a preview release with different syntax?
2. Does the label actually contain a **pattern** right before `when`?
3. Does the guard have a valid `boolean` type?
4. Has every pattern variable used in the guard been bound by the pattern or a subexpression according to flow scoping rules?
5. Is the guard simple and free of side effects/exceptions?
6. Are specific branches placed **before** covering patterns to avoid dominance?
7. If the guard returns `false`, which branch will Java check next? Is there an unguarded fallback branch?
8. Is the switch expression exhaustive, and are `null` values handled as required?
9. If using `case ...:` syntax, have you avoided accidental fall-through into a case with a pattern variable?
10. Have you distinguished between **the guard that selects the branch** and **the branch's expression/statement**?

## 13. Exercises and Answers

### Exercise 1 — Identify the Branch

Given:

~~~java
static String label(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() > 4 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

What are the results of `label("   ")`, `label("hello")`, `label("hi")`, and `label(5)`?

**Answer:** `BLANK`, `LONG`, `SHORT`, and `OTHER` respectively. The two preceding guards are tried in order if the `String` pattern matches.

### Exercise 2 — `when` with a Record Pattern

Given `record Range(int start, int end) {}`, write a case label that recognizes a valid range where `start <= end` and returns `"VALID"`.

**Reference answer:**

~~~java
case Range(int start, int end) when start <= end -> "VALID";
~~~

This is a label snippet placed inside an appropriate switch, not a standalone program. You must add cases for `Range` that do not satisfy the guard and for other types if the switch expression requires exhaustiveness.

### Exercise 3 — Why Doesn't `null` Call `isBlank`?

Why does `switch (value)` with `case String s when s.isBlank()` not throw a `NullPointerException` in the guard when `value == null`?

**Answer:** Because the type pattern `String s` does not match `null`, so the guard is not evaluated. However, **the switch itself** on `null` still needs a `case null` label or appropriate handling; otherwise it may throw `NullPointerException`.

### Exercise 4 — Fix an Incorrectly Typed Guard

Fix:

~~~java
case String s when s.length() -> "LONG";
~~~

**Answer:** Add a Boolean condition, for example `case String s when s.length() >= 5 -> "LONG";`.

### Exercise 5 — Reversed Case Order

Explain why:

~~~java
case Number n -> "NUMBER";
case Integer i when i > 0 -> "POSITIVE_INTEGER";
~~~

is an invalid label ordering when the selector allows both `Number` and `Integer`.

**Answer:** `Integer` is a subtype of `Number`. The unguarded `case Number n` label already covers `Integer` objects, causing the subsequent `Integer i` label to be dominated. Place `Integer i when i > 0` before `Number n`.

### Exercise 6 — Guard with an Inner Pattern

Is the following snippet valid and why?

~~~java
case CharSequence cs
    when cs instanceof String text && text.length() >= 3 ->
    "LONG:" + text;
~~~

**Answer:** Valid in Java 21 when the selector allows applying `CharSequence`. The guard is only evaluated after `cs` is bound; `&&` ensures `text.length()` only runs after `cs instanceof String text` matches. When the guard is true, `text` is in scope in the rule body.

## 14. Takeaways and References

**Core formula:**

~~~text
case Pattern p when booleanConditionUsing(p) -> branch
~~~

Java checks **the pattern first, the guard second**. If the guard is true, the branch is selected and its code runs; if the guard is false, the next label is tried. Place specific cases before general ones, keep conditions returning `boolean`, understand variable scoping properly, handle `null`, and ensure switch expressions are exhaustive.

Official documentation for further reading:

- JLS Java SE 21 `14.11.1 — Switch Blocks, guarded case labels and dominance`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- JLS Java SE 21 `6.3.3 — Scope for Pattern Variables in case Labels`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
