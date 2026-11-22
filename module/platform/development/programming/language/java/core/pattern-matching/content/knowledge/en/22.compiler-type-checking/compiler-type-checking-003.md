# Definite Matching and Flow Analysis in Java Pattern Matching

In Java, a **pattern variable** can only be used at locations where the compiler can prove that pattern matching succeeded. This rule is called **definite matching**; reasoning from conditions and control flow to determine a variable's scope is called **flow analysis** or **flow scoping**.

The simplest example:

```java
Object input = "Java";

if (input instanceof String s) {
    System.out.println(s.length()); // 4: s is definitely bound.
}
// Cannot arbitrarily use s here because the if branch may not execute.
```

When `input` is not a `String`, the pattern `String s` does not match, so `s` is not initialized for that branch. Java prevents developers from using a pattern variable at a point where there is no guarantee that it has been bound. This mechanism is checked at **compile time**, helping avoid unsafe casts and references to uninitialized variables.

This article is based on the rules in the **Java Language Specification (JLS) 21**, especially sections **`6.3 Scope of a Declaration**, **`14.30 Patterns**, and **`16 Definite Assignment**. Type patterns in `instanceof` have been a standard feature since Java 16 (JEP 394); record patterns have been a standard feature since Java 21 (JEP 440). The full example uses **Java 21+** and does not require `--enable-preview`.

## 1. Three Concepts to Distinguish

### Pattern matching

**Pattern matching** is checking whether a value matches a pattern. If it succeeds, the variables declared by the pattern are initialized.

```java
Object value = "hello";
boolean isText = value instanceof String s;
```

Here `isText` is `true`, but the variable `s` cannot therefore be used at every position after the statement. The compiler only allows using `s` when control flow clearly confirms the match result. Therefore, an `instanceof` expression is usually placed directly inside an `if`, `while`, or conditional operator.

### Definite matching

A pattern variable is considered **definitely matched** at a point in a program if **every possible path reaching that point** guarantees that the match succeeded and the variable received a value.

```java
if (value instanceof String s) {
    System.out.println(s.toUpperCase()); // Valid.
} else {
    System.out.println("Not a String");
    // No guarantee for s in else.
}
```

The compiler analyzes expression structure, `if` branches, negation, branch-terminating statements, and certain other constructs. It does not need to run the program to confirm that `s` exists in a specific branch.

### Flow scoping and definite assignment

- **Flow scoping**: the scope of the name `s` depends on the program locations where the match is guaranteed to have succeeded; it is not simply the entire block enclosing the declaration.
- **Definite matching**: the property proving that a pattern has matched at a point in control flow, which determines where the pattern variable can be referenced.
- **Definite assignment (DA)**: Java's general rule requiring a local variable to be definitely assigned a value before being read. Pattern variables have specific rules for *matching* and scope, designed in a similar spirit to DA.

A typical DA example:

```java
int count;
if (Math.random() > 0.5) {
    count = 1;
}
// System.out.println(count); // Error: count might not have been initialized.
```

This is a **definite assignment** issue because `count` is declared normally. By contrast, reading `s` after a standalone `if (value instanceof String s)` is typically an error of **no pattern variable in scope at that point**. The two rules are related in terms of flow analysis, but they are not completely synonymous.

## 2. Basic Rules When instanceof Succeeds or Fails

With:

```java
Object obj = "abc";
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

The expression `obj instanceof String s` **introduces** the variable `s` on the path where the result is `true`. The JLS distinguishes:

- **Introduced when true:** when the entire expression is true, the pattern has definitely matched, so `s` can be used in locations permitted by the true branch.
- **Introduced when false:** can occur with expressions containing negation `!`; only when the entire expression is false has the inner pattern definitely matched.

A standalone `instanceof` introduces a pattern variable **when true**, not when false. This is the foundation for the combination rules below.

**Do not infer from the variable name alone:** the compiler checks actual branches; it does not assume that just because you wrote `String s` in one place, all subsequent statements have `s`.

## 3. The && Operator: Using a Variable on the Right-Hand Side When the Left-Hand Side Matches

`&&` evaluates using *short-circuit* semantics: it only evaluates the right-hand side when the left-hand side is `true`. If the left-hand side introduces a pattern variable when true, that variable is **definitely matched on the right-hand side**.

```java
Object input = "  Java  ";

if (input instanceof String s && !s.isBlank()) {
    System.out.println(s.trim()); // Java
}
```

The compiler's reasoning path:

1. Check `input instanceof String s`.
2. If false, skip `!s.isBlank()` and the `if` branch; nowhere is `s` read when unmatched.
3. If true, `s` has received a non-`null` `String`, so it is allowed to be used in `!s.isBlank()`.
4. If both sides are true, the `if` branch runs and `s` remains valid to use.

Multiple checks can be chained:

```java
if (input instanceof String s
        && s.length() >= 4
        && s.startsWith("J")) {
    System.out.println(s);
}
```

Note: `&&` has its own *definite matching* rules. Do not assume that a non-short-circuiting Boolean operator like `&` always allows reading the same pattern variable on the right-hand side.

## 4. The || Operator and the Difference Between True and False

Unlike `&&`, `||` only evaluates the right-hand side when **the left-hand side is false**. Therefore, according to the JLS, only a pattern variable introduced by the left-hand side **when false** is definitely matched on the right-hand side.

### Invalid example

```java
// INVALID SNIPPET — for recognizing the compiler error only.
//
// if (input instanceof String s || s.isBlank()) {
//     System.out.println(s);
// }
```

The left-hand side `input instanceof String s` can be false. In that case `||` proceeds to evaluate `s.isBlank()`, but `s` has not been bound. This is a compile-time error. Even if the overall condition is true, it could be true from a branch that does not bind `s`, so `s` cannot be arbitrarily used in the `if` branch.

### Valid usage of || with negation

```java
static String requireText(Object input) {
    if (!(input instanceof String s) || s.isBlank()) {
        return "missing text";
    }
    return "trimmed=" + s.trim();
}
```

This is an important pattern:

1. `!(input instanceof String s)` is true when the value does **not** match `String`.
2. If the left-hand side is true, `||` skips `s.isBlank()` and the `if` branch returns immediately.
3. If the left-hand side is false, `input instanceof String s` was true, so `s` can be used safely on the right-hand side.
4. If the entire `if` condition is false, it means `s` is a valid `String` **and is not blank**. Because the `if` branch has a `return`, when execution continues to the final statement, `s` has definitely matched.

Result: `requireText("  hello  ")` returns `trimmed=hello`, while `requireText("  ")` and `requireText(null)` both return `missing text`.

**Rule of thumb:** with `a && b`, the compiler allows using variables introduced by `a` *when true* inside `b`; with `a || b`, the compiler allows using variables introduced by `a` *when false* inside `b`.

## 5. The ! Operator Reverses the Definite Matching Branch

Boolean negation `!` flips the "true" and "false" conditions:

```java
Object input = "Java";

if (!(input instanceof String s)) {
    System.out.println("Not text");
} else {
    System.out.println(s.length()); // 4
}
```

The expression `input instanceof String s` introduces `s` when **true**. After negating with `!`, the entire negated expression introduces `s` when **false**, because only then is the inner match guaranteed to have succeeded.

Therefore:

- The true `if` branch of `!(...)`: **cannot** assume `s` exists.
- The `else` branch of `!(...)`: `s` is guaranteed to have matched.
- Double negation `!!(input instanceof String s)` preserves the matching direction of the original condition; however, clearer syntax should be preferred.

This rule is inferred from the expression, not a special property of a variable named `s`.

## 6. Early Return and Scope After if

One of the strongest applications is a **guard clause**: eliminate invalid cases up front, then use the pattern variable for the rest of the method.

```java
static String describeString(Object input) {
    if (!(input instanceof String s)) {
        return "not a string";
    }
    return "length=" + s.length();
}
```

At the statement `return "length=" + s.length();`, every remaining path that continues must have gone through the `!(...) == false` case. Therefore `s` has definitely matched. The JLS allows an `if` to introduce a pattern variable into subsequent statements when the opposite branch **cannot complete normally**, such as when that branch ends with `return` or `throw`.

`throw` can be used instead of `return`:

```java
static int lengthOrThrow(Object input) {
    if (!(input instanceof String s)) {
        throw new IllegalArgumentException("String required");
    }
    return s.length();
}
```

**Comparison with an invalid pattern:**

```java
static void wrongIdea(Object input) {
    if (input instanceof String s) {
        System.out.println(s);
    }
    // System.out.println(s); // INVALID: input might not be a String.
}
```

Here the `if` can complete normally even when the condition is false; the compiler cannot guarantee `s` at the next statement.

## 7. The Conditional Operator ? : and Variable Scope

In the expression `condition ? whenTrue : whenFalse`, the compiler allows reading the pattern variable in the branch corresponding to the condition's value:

```java
Object value = "JDK";
int length = value instanceof String s ? s.length() : 0;
System.out.println(length); // 3
```

The `s.length()` branch is only evaluated when the pattern `String s` matches. Conversely, the `0` branch runs when it does not match.

Negation still applies:

```java
String result = !(value instanceof String s)
        ? "not text"
        : "length=" + s.length();
```

The part after `:` in the second example runs when the negation is false, meaning the pattern has matched. You cannot arbitrarily use `s` in both branches or after the entire expression because execution reaching those places may not have matched.

## 8. Record Patterns Also Follow Definite Matching

Since Java 21, `instanceof` can contain a **record pattern**, in which multiple variables are declared at once.

```java
record Point(int x, int y) {}
Object value = new Point(2, 4);

if (value instanceof Point(var x, var y)
        && x >= 0 && y >= 0) {
    System.out.println(x + y); // 6
}
```

- `Point(var x, var y)` checks that `value` is a non-`null` `Point`, then extracts the two `int` components into `x` and `y`.
- If the record pattern matches, **both `x` and `y`** are bound and are in valid scope on the right-hand side of `&&` and in the true `if` branch.
- If `value` is another type or `null`, the pattern fails; no execution path reads `x` or `y`.
- If the pattern matches but `x < 0`, the overall `if` condition is still false due to the Boolean guard; this does not mean the record pattern itself failed to match.

The `var` type is inferred at compile time from the record definition; `x` and `y` have type `int`. This is not dynamic typing.

### Nested record patterns

```java
record Wrapper(Point point, String label) {}

Object value = new Wrapper(new Point(3, 3), "ok");
if (value instanceof Wrapper(Point(var x, var y), var label)
        && x == y) {
    System.out.println("diagonal=" + x + ", label=" + label);
}
```

Here a successful match binds `x`, `y`, and `label`. The right-hand side `x == y` is only evaluated after both the outer record pattern `Wrapper(...)` and the nested record pattern `Point(...)` match.

If `Wrapper.point() == null`, the `Point(var x, var y)` part does not match, and the entire `instanceof` evaluates to `false`. This avoids calling the `x()` accessor on a nonexistent `Point` object.

**However, `label` can be `null`**, because `var label` in a component position is an unconditional pattern for the component's `String` type. Definite matching guarantees that the variable `label` **has been bound**, not that every extracted reference value is non-`null`. Check `label != null` before calling `label.length()`.

## 9. Definite Matching in while and Loops

Flow analysis also applies to `while` conditions. Inside the loop body, if the condition matches, the pattern variable is valid to use.

```java
Object value = "abcd";

while (value instanceof String s && s.length() > 3) {
    System.out.println(s.length()); // 4
    break;
}
```

`s` is a `String` in the loop body and on the right-hand side of `&&`. The loop has `break` so it does not loop forever when `value` stays unchanged; real programs may update the input on each iteration. You must not assume `s` always exists outside the loop because the loop may never have executed even once.

JLS rules also analyze certain forms of `for` and `do`, though scoping details depend on how the condition is evaluated and how the loop is exited. For learners, it is best to master the `while` pattern first and let the compiler confirm which pattern variables can be used after a loop finishes.

## 10. In switch, Guards, and Case Bodies

Pattern matching in Java 21 `switch` also relies on definite matching. When a `case` label matches, the pattern variables in the label are guaranteed to have values in the **`when` guard** and that branch's body.

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "switch=null";
        case Point(var x, var y) when x == y -> "same=" + x;
        case Point(var x, var y) -> "different=" + (x - y);
        default -> "switch=other";
    };
}
```

The first branch matches `Point(var x, var y)` and only then checks `x == y`. The next branch has **a new declaration of pattern variables** with the same names, scoped to its own branch. Each case uses its own variables; you cannot arbitrarily access `x` or `y` after the entire `switch`.

Placing the branch with `when` before the general `Point(...)` branch also prevents the broader branch from shadowing the more specific one (*dominance*). `case null` handles a `null` selector; `default` is not treated as a general `null`-catching branch in this example.

Although the focus here is *definite matching*, remember that the compiler also independently checks other `switch` rules, such as **exhaustiveness**, **dominance**, and the types of the branches.

## 11. Flow Analysis Summary Table

| Expression or Construct | When is variable `s` definitely matched? | Where can `s` be used? |
| --- | --- | --- |
| `obj instanceof String s` | When the expression is `true` | True branch of `if` |
| `obj instanceof String s && s.length() > 0` | Left-hand side is true | Right-hand side of `&&`, true `if` branch |
| `obj instanceof String s \|\| other` | Not guaranteed when the overall expression is true | Do not use `s` in the true branch based on this expression alone |
| `!(obj instanceof String s)` | When the negated expression is `false` | Corresponding `else` branch |
| `!(obj instanceof String s) \|\| s.isBlank()` | When the negated left-hand side is false | Right-hand side of `\|\|`; after a guard with `return` if flow guarantees it |
| `if (!(obj instanceof String s)) return;` | When execution continues past the `if` | Subsequent statements within the scope defined by the JLS |
| `obj instanceof String s ? s.length() : 0` | When the ternary condition is true | The `?` branch following the condition |
| `while (obj instanceof String s && ...)` | When the loop condition is true | Right-hand side of `&&` and the loop body |
| `case Point(var x, var y) when x == y -> ...` | When the case's record pattern matches | The corresponding guard and case body |

This table describes **where referencing a pattern variable is permitted**. It does not itself guarantee that a reference value inside a record is non-`null`, nor does it replace Java's other type or syntax checks.

## 12. Complete Java 21 Program and Verified Stdout

Save the following code to **`DefiniteMatchingDemo.java`**:

```java
public class DefiniteMatchingDemo {
    record Point(int x, int y) {}
    record Wrapper(Point point, String label) {}

    static String describe(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "text=" + s.trim();
        }
        if (value instanceof Point(var x, var y) && x >= 0 && y >= 0) {
            return "point=(" + x + "," + y + ")";
        }
        if (value instanceof Wrapper(Point(var x, var y), var label)
                && x == y) {
            return "diagonal=" + x + ", label=" + label;
        }
        return "other";
    }

    static String afterEarlyReturn(Object value) {
        if (!(value instanceof String s)) {
            return "not a string";
        }
        return "length=" + s.length();
    }

    static String orGuard(Object value) {
        if (!(value instanceof String s) || s.isBlank()) {
            return "missing text";
        }
        return "trimmed=" + s.trim();
    }

    static String ternary(Object value) {
        int length = value instanceof String s ? s.length() : 0;
        return "ternary length=" + length;
    }

    static String whileCheck(Object value) {
        while (value instanceof String s && s.length() > 3) {
            return "long text=" + s.length();
        }
        return "not long text";
    }

    static String caseCheck(Object value) {
        return switch (value) {
            case null -> "switch=null";
            case Point(var x, var y) when x == y -> "same=" + x;
            case Point(var x, var y) -> "different=" + (x - y);
            default -> "switch=other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe(new Point(2, 4)));
        System.out.println(describe(new Point(-2, 4)));
        System.out.println(describe(new Wrapper(new Point(3, 3), "ok")));
        System.out.println(describe(new Wrapper(null, "missing")));
        System.out.println(afterEarlyReturn("abc"));
        System.out.println(afterEarlyReturn(123));
        System.out.println(orGuard("  "));
        System.out.println(orGuard("  hello  "));
        System.out.println(orGuard(null));
        System.out.println(ternary("JDK"));
        System.out.println(ternary(null));
        System.out.println(whileCheck("abcd"));
        System.out.println(whileCheck("abc"));
        System.out.println(caseCheck(new Point(4, 4)));
        System.out.println(caseCheck(new Point(4, 2)));
        System.out.println(caseCheck(null));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 DefiniteMatchingDemo.java
java DefiniteMatchingDemo
```

**Exact output:**

```text
text=Java
point=(2,4)
other
diagonal=3, label=ok
other
length=3
not a string
missing text
trimmed=hello
missing text
ternary length=3
ternary length=0
long text=4
not long text
same=4
different=2
switch=null
```

Key takeaways:

1. `describe("  Java  ")` uses `String s` and the condition `!s.isBlank()`, then trims whitespace to produce `text=Java`.
2. `Point(2,4)` matches the record pattern and the non-negative coordinate condition. `Point(-2,4)` matches the record pattern but is filtered out by `x >= 0`, so it returns `other`.
3. `Wrapper(Point(3,3),"ok")` matches both the outer record and the nested record, yielding `x=3`, `y=3`, and `label="ok"`. `Wrapper(null,"missing")` does not match the `Point(...)` record pattern.
4. `afterEarlyReturn` demonstrates `s` remaining in scope after a negated guard that ends with `return`.
5. `orGuard` demonstrates `||` with negation: `s` is only used at points where it is definitely matched.
6. `ternary` demonstrates `s` being used in the `?` branch when the condition is true.
7. `whileCheck` uses `s` inside the `while` body without casting.
8. `caseCheck` demonstrates record pattern variables used in a `when` guard and a `switch` branch; a `null` selector enters `case null`.

The code was verified with `javac --release 21` and `java`, producing the exact 17 lines of output shown above.

## 13. Common Mistakes When Learning Definite Matching

1. **Confusing "declared" with "allowed to use."** Seeing `String s` appear does not mean `s` can be used everywhere below it. Trace every flow that can reach the point where the variable is read.
2. **Reading `s` on the right-hand side of `||` right after `obj instanceof String s`.** The right-hand side runs when the preceding pattern is false; the compiler must reject it.
3. **Reading `s` on the right-hand side of `&&` after a negation `!(obj instanceof String s)`.** When the negation is true, the original pattern did not match; there is no `s` to use.
4. **Assuming the true branch of a negated expression has the variable.** For `if (!(obj instanceof String s))`, the `else` branch is where the pattern has definitely succeeded.
5. **Using the variable outside an `if` without an early-exit guard.** If the non-matching case can still fall through, the compiler cannot guarantee the variable is bound.
6. **Assuming record components are always non-null on a match.** `Wrapper(Point(var x,var y),var label)` guarantees the nested `Point` exists, but `label` can still be `null`.
7. **Confusing a record pattern with a type pattern.** `Point p` binds the entire record; `Point(var x,var y)` binds its components. Both follow flow scoping.
8. **Declaring two pattern variables with the same name in a combined expression.** For example, `(a instanceof String s) && (b instanceof String s)` violates the JLS duplicate-name rules; give the two variables distinct names.
9. **Thinking a runtime condition is "obvious" so the compiler should accept it.** The compiler reasons according to static language rules; it does not run the whole program to guess arbitrary outcomes.
10. **Confusing definite matching with `null` checking.** A bound pattern variable can still hold a `null` reference component value; check it before dereferencing.
11. **Using the wrong Java version.** Type patterns for `instanceof` have been standard since Java 16, but record patterns in the sample program require Java 21+.

## 14. Self-Check Questions

**Question 1.** Why does this code compile?

```java
if (obj instanceof String s && s.length() > 3) {
    System.out.println(s);
}
```

*Answer:* The right-hand side of `&&` only runs when the left-hand side is true. Therefore `s` is definitely matched in `s.length()` and in the true `if` branch.

**Question 2.** Why is the following code invalid?

```java
// if (obj instanceof String s || s.isEmpty()) {
//     System.out.println(s);
// }
```

*Answer:* The right-hand side of `||` is only evaluated when `obj instanceof String s` is `false`. In that case `s` is not bound, so the compiler rejects it.

**Question 3.** Can variable `s` be used after the following statement?

```java
if (!(obj instanceof String s)) {
    throw new IllegalArgumentException();
}
System.out.println(s.length());
```

*Answer:* Yes. The non-matching branch throws an exception and cannot complete normally; all remaining execution paths that continue have `s` matched.

**Question 4.** If a `Wrapper` record contains a `null` `Point`, can `value instanceof Wrapper(Point(var x, var y), var label)` match?

*Answer:* No. The nested record pattern `Point(...)` does not match `null`; therefore `x`, `y`, and `label` from the full pattern are not in scope in the success branch.

**Question 5.** In `case Point(var x,var y) when x == y -> ...`, why can `x` be used in `when`?

*Answer:* The `when` guard is evaluated after the case's pattern has matched, so the compiler confirms that `x` and `y` are bound.

**Official references:** [JLS 21, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3), [JLS 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [JLS 21, `16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se21/html/jls-16.html), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
