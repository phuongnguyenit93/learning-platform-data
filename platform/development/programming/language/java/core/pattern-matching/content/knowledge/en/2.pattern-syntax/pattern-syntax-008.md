# How pattern matching differs from expression evaluation in Java

In Java, **expression evaluation** is the process of computing the value of an expression; **pattern matching** is the process of testing whether a value conforms to a pattern and, when variables are declared in the pattern, **binding the corresponding values to those pattern variables**. The two mechanisms can work together in the same statement, but they answer two different questions:

- **Expression evaluation:** "What value does this expression produce, and under what evaluation rules?"
- **Pattern matching:** "Does an existing value match the structure/type described by the pattern, and if it matches, which variables become available?"

The most common point of confusion: **`instanceof` is an expression with a `boolean` result, whereas `String text` after `instanceof` is a *pattern*, not an ordinary expression.** When evaluating the entire `instanceof` expression, Java performs pattern matching inside it. Therefore, "expression evaluation" and "pattern matching" are two layers of mechanisms that can be nested, not mutually exclusive features.

## 1. Expression evaluation: computing a value

Examples of ordinary Java expressions:

```java
int sum = 2 + 3;                     // 2 + 3 evaluates to 5
int size = "Java".length();          // the call evaluates to 4
boolean same = "Java".equals("Go");  // evaluates to false
```

An expression has a type checked by Java at compile time; at runtime, the program evaluates the involved operands/calls and produces a **value** or completes abruptly (for example, throwing an exception). Java defines the evaluation order, short-circuit evaluation with `&&`/`||`, and side effects such as method calls and state mutation.

For example:

```java
boolean ok = ready && checkExpensiveCondition();
```

`checkExpensiveCondition()` is only called when `ready` is `true`. The result of the **entire** expression is a `boolean` value. No pattern variable is declared or bound solely by this expression.

**Evaluating to `true` does not automatically mean pattern matching is being used.** Comparisons like `a > b`, `equals(...)`, and many other checking methods also produce a `boolean` without containing a pattern.

## 2. Pattern matching: testing a pattern and binding variables on match

Consider an example for Java 17+:

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length());
}
```

Breakdown of roles:

| Syntax | Role | What happens |
| --- | --- | --- |
| `input` | **Target expression** | Evaluated to obtain the value to be tested—here, a reference to the string `"Java"`. |
| `String text` | **Type pattern** | Tests whether the runtime value is non-`null` and compatible with `String`. |
| `text` | **Pattern variable** | When the pattern matches, bound to the same object, with static type `String`. |
| `input instanceof String text` | **`instanceof` expression** | Evaluates to `true` or `false` depending on whether the pattern matches. |
| `text.length()` | **Method invocation expression** | Only allowed where Java proves `text` is bound; here, the result is `4`. |

Execution flow:

```text
Evaluate target expression: input
                 |
                 v
           runtime value
                 |
                 v
     test type pattern String text
          /                 \
       match              no match
        |                    |
   bind text              no binding
        |                    |
 instanceof = true     instanceof = false
        |
 use text where flow scoping is valid
```

A type pattern **does not create a new `String`**, does not cast the object into a different class, and does not mutate data on its own. It checks compatibility and lets a variable name with a useful static type refer to the matched object. With `input` declared as `Object`, the compiler does not allow calling `input.length()`, but inside the matching branch, `text.length()` is valid because `text` has type `String`.

With `input = 42` or `input = null`, the pattern `String text` does not match. The `instanceof` expression returns `false`; there is no successful binding for `text`.

## 3. Distinguishing syntax: which part is an expression, and which part is a pattern?

The same tokens `String` and `text` can appear in different contexts:

```java
String text = "Java";                 // local variable declaration with initializer
Object value = "Java";

boolean matched = value instanceof String s; // instanceof expression + type pattern
```

- `String text = "Java"` is a **variable declaration** with the initializer expression `"Java"`, not a pattern used for matching.
- `String s` in `value instanceof String s` is a **type pattern**. Here, the pattern is placed in a syntactic position that permits a pattern (after `instanceof`).
- `value instanceof String s` is the **entire expression** that evaluates to `boolean`. The pattern `String s` by itself is not a standalone `boolean` expression.
- `matched` only stores `true`/`false`. Storing this result does not automatically keep the variable `s` in scope at the next statement.

Intentionally invalid examples:

```java
Object value = "Java";
boolean matched = value instanceof String s;
// System.out.println(s.length()); // Compile ERROR: s is not in scope here.

// boolean another = String s;      // ERROR: a type pattern is not an expression.
```

When you need to work with the matched value, place it in a context where Java can prove the match:

```java
Object value = "Java";

if (value instanceof String s) {
    System.out.println(s.length()); // Valid: result is 4
}
```

## 4. An `instanceof` expression consists of two distinct operations

Syntax:

```java
targetExpression instanceof Type patternVariable
```

To evaluate an `instanceof` **expression**, Java performs these main steps:

1. Evaluate `targetExpression` to obtain a reference value. If it is a method call, the method may have side effects or throw an exception. Pattern matching **does not skip** those effects.
2. Test the **type pattern** against the obtained value. A type pattern does not match `null`; for a non-`null` object, it must be compatible with the type required by the pattern.
3. If it matches, create a binding for the pattern variable; the `instanceof` expression evaluates to `true`. If it does not match, the result is `false` and there is no successful binding.
4. If the expression appears in `if`, `&&`, a conditional operator, or another context supporting flow scoping, Java analyzes control-flow paths to determine whether the pattern variable can be used at subsequent locations.

Therefore, **the target expression is evaluated to obtain the data to test**, while **the pattern describes how to test and bind that data**. Pattern matching is not evaluating the right-hand side of `instanceof` into a separate object or `boolean` value.

## 5. Runnable example: target is evaluated, pattern is matched, and another condition is evaluated

Save the file `PatternVsExpressionDemo.java`:

```java
public class PatternVsExpressionDemo {
    static Object load(String data) {
        System.out.println("evaluate target");
        return data;
    }

    static void inspect(String input) {
        if (load(input) instanceof String text && text.length() > 3) {
            System.out.println("matched: " + text.toUpperCase());
        } else {
            System.out.println("no match");
        }
    }

    public static void main(String[] args) {
        inspect("Java");
        inspect("Go");
        inspect(null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PatternVsExpressionDemo.java
java PatternVsExpressionDemo
```

Output:

```text
evaluate target
matched: JAVA
evaluate target
no match
evaluate target
no match
```

Explanation of the three runs:

1. For `"Java"`: the expression `load(input)` is evaluated **once**, prints `evaluate target`, and returns the string. The pattern `String text` matches and binds `text`. Only then is the expression `text.length() > 3` on the right-hand side of `&&` evaluated to `true`; the first branch prints `matched: JAVA`.
2. For `"Go"`: the type pattern **still matches** because `"Go"` is a `String`. However, the expression `text.length() > 3` is `false`, so execution enters `else`. The line `no match` is the program's general message: **do not infer that the pattern failed** just because the overall `if` condition was false.
3. For `null`: the target expression is still evaluated and still prints `evaluate target`; the type pattern does not match. The right-hand side of `&&` **is not executed**, preventing any call to `text.length()` on an unbound variable.

This example demonstrates three separate mechanisms: evaluating the target; testing the pattern and binding; and continuing to evaluate another `boolean` expression via `&&`. With a single evaluation in the `if` above, `load` is called only once; if you write two separate checks containing `load(...)`, those are two distinct evaluations.

## 6. Flow scoping: variables introduced by a pattern, used via control flow

Normally, local variables have scope determined by declaration structure and blocks. Pattern variables add the **flow scoping** rule: a variable can be used only where the compiler is certain that every control-flow path reaching that point has matched the pattern.

**True branch:**

```java
if (input instanceof String text) {
    System.out.println(text.toUpperCase()); // Valid
} else {
    // Cannot use text: this branch does not guarantee a match.
}
```

**Right-hand side of `&&`:**

```java
if (input instanceof String text && text.length() >= 4) {
    System.out.println(text);
}
```

The right-hand side executes only when the pattern test on the left-hand side returned `true`. In this example, both `text.length()` and `System.out.println(text)` are in positions where `text` can be used.

**Right-hand side of `||`:**

```java
// Invalid, does not compile:
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

The right-hand side of `||` executes when the left-hand side is `false`, which does not guarantee that `String text` matched. You cannot use `text` there.

**After an early-return branch:**

```java
static int lengthOrMinusOne(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid: any path reaching here is guaranteed to match.
}
```

The `!` operator negates the condition; the `return` statement eliminates the non-matching path. At the end of the method, Java knows `text` is bound. This is not the result of an arbitrary expression returning `true`; it is a scoping rule tied to patterns and control flow.

## 7. `switch`: patterns select the branch, expressions produce the result

Since **Java 21**, pattern matching in `switch` and `when` guards have been standardized. Consider a `switch expression` returning `String`:

```java
return switch (input) {
    case String text when text.isBlank() -> "blank String";
    case String text -> "String length=" + text.length();
    case Integer number -> "Integer+1=" + (number + 1);
    case null -> "null";
    default -> "other";
};
```

Three roles to distinguish:

- `input` is the **selector expression**: evaluated to obtain a value for branch selection.
- `case String text` and `case Integer number` contain **patterns**: they test the type and bind a variable in the matching branch. `case null` is a label for handling `null`, not a type pattern.
- `when text.isBlank()` is a `boolean` **guard expression**, evaluated only after the pattern `String text` has matched and `text` is usable. The value after `->` in the selected branch is the expression that produces the **final result of the `switch expression`**.

Thus, a `switch expression` uses **pattern matching to select a branch** and **expression evaluation to compute the return value**. The pattern in a `case` does not itself carry the return value of the entire `switch`.

### Runnable Java 21+ example

Save the file `SwitchPatternDemo.java`:

```java
public class SwitchPatternDemo {
    static String describe(Object input) {
        return switch (input) {
            case String text when text.isBlank() -> "blank String";
            case String text -> "String length=" + text.length();
            case Integer number -> "Integer+1=" + (number + 1);
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(" "));
        System.out.println(describe(41));
        System.out.println(describe(null));
        System.out.println(describe(2.5));
    }
}
```

```bash
javac SwitchPatternDemo.java
java SwitchPatternDemo
```

Output:

```text
String length=4
blank String
Integer+1=42
null
other
```

For `"Java"`, the pattern `String text` in the first branch matches, but the guard `text.isBlank()` is false; the next `case String text` branch is selected and evaluates the expression producing `"String length=4"`. For `" "`, the guard is true, so the first branch returns `"blank String"`. For `41`, the pattern `Integer number` matches, and then the expression `number + 1` produces `42`. `null` is handled by `case null`. For `2.5`, `default` returns `"other"`.

When using `switch` with patterns, pay attention to **branch ordering and dominance**: placing a broader pattern earlier can shadow a narrower pattern later, causing the compiler to report a dominated case label. A `switch expression` must also be exhaustive according to Java's rules. In particular, a `switch` without `case null` generally does not treat `null` the way `instanceof` returns `false`; do not infer `switch` behavior from `instanceof` checks.

## 8. Record patterns: a clearer example of "matching" vs. "evaluating" (Java 21+)

A **record pattern** can test a record type and recursively match its components to create multiple bindings. The following example assumes the record is declared in the same compilation scope:

```java
record Pair(Object left, Object right) {}

Object input = new Pair("A", 42);
if (input instanceof Pair(String left, Integer right)) {
    System.out.println(left + ":" + right); // A:42
}
```

Here:

- `input` is evaluated to a `Pair` object.
- `Pair(String left, Integer right)` is a **record pattern** (not a constructor call and not a method call).
- The pattern checks that the object is of type `Pair`, then matches each component against the type patterns `String left` and `Integer right`.
- Only when the entire pattern matches are `left` and `right` bound for use in the `if` block.
- The expression `left + ":" + right` then performs string concatenation and produces the value to print.

Writing `new Pair("A", 42)` is an **object creation expression**; writing `Pair(String left, Integer right)` in a pattern position is **syntax for matching and deconstructing data**. They look similar in form but have different semantic roles. Record patterns were introduced in Java 21; do not compile this example with `--release 17`.

## 9. Summary comparison

| Criterion | Expression evaluation | Pattern matching |
| --- | --- | --- |
| Main question | What value does the expression return? | Does the tested value conform to the pattern? |
| Input | Operands, variables, calls, intermediate values, etc. | A value to test and a pattern describing type/structure |
| Result | A value of the expression's type, or abrupt completion | Match success/failure, along with bindings on success |
| Examples | `a + b`, `s.length()`, `a > 0`, the entire `x instanceof String s` | `String s` in `instanceof`; `case String s`; `Pair(String x, Integer y)` |
| New variables | Does not necessarily declare variables | A pattern can introduce pattern variables |
| Control flow | Has evaluation order and short-circuiting | Whether a pattern variable can be used depends on flow scoping |
| Failure | May throw an exception or return a value indicating failure depending on the expression | No match means no binding; exceptions during target evaluation or related processing can still occur |

The two columns are **not absolute opposites**. Evaluating an `instanceof expression` includes testing a pattern; evaluating a `switch expression` can include selecting a branch using patterns.

## 10. Common conceptual and coding mistakes

1. **Thinking `String text` is an expression that returns `boolean`.** The `boolean` result comes from the *entire* `input instanceof String text`; `String text` is the pattern.
2. **Thinking every `boolean` condition uses a pattern.** `input != null` or `"Java".equals(input)` only evaluates a condition and does not bind a new `String text`.
3. **Thinking the `else` branch proves the pattern did not match.** With `instanceof String text && text.length() > 3`, `else` is also reached when the pattern matches but the length comparison fails.
4. **Using a pattern variable outside its flow scope.** Assigning the result of `instanceof` to a `boolean` variable does not allow using the pattern variable name in subsequent statements.
5. **Thinking the target is not evaluated when a pattern fails.** The target must always be evaluated to test the pattern, unless the entire expression containing the test is skipped by an outer control-flow construct. If evaluating the target throws an exception, the test cannot produce a normal result.
6. **Equating `null` handling in `instanceof` and `switch`.** `null instanceof String text` is always `false` for a type pattern; `switch` must handle `null` according to its own rules, such as using `case null`.
7. **Confusing a record pattern with a constructor call.** `new Pair(...)` creates an object; `Pair(...)` in a record pattern position matches an existing object and binds its components.
8. **Confusing language patterns with `java.util.regex.Pattern`.** `java.util.regex.Pattern` is a library class for regular expressions; `String text` or `Pair(...)` here is Java's language-level pattern matching syntax.
9. **Ignoring the Java version.** Type patterns for `instanceof` have been standard since Java 16 (and work well in Java 17); pattern matching for `switch`, `when`, and record patterns were standardized in Java 21. The two main examples above include the appropriate JDK requirements.

## 11. How to quickly read code that uses patterns

When encountering pattern matching, separate four questions in order:

1. **What is the target/selector expression?** When is it evaluated, and can it have side effects or throw an exception?
2. **Where is the pattern, and what does it test?** Which type or record components are being tested?
3. **If it matches, which pattern variables are bound?** What is each variable's static type and where is it in scope?
4. **Which expression is evaluated next?** This could be a `&&` condition, a `when` guard, an expression inside a branch, or the result expression of a `switch expression`.

Keeping **"expressions produce values" → "patterns test values and bind variables" → "subsequent expressions use results/bindings within valid scopes"** clearly separated helps you read and write pattern syntax accurately without confusing type/structure testing with ordinary computation.
