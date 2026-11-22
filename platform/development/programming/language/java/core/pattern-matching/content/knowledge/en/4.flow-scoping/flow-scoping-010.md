# Error When Using a Pattern Variable Outside Flow Scope in Java 21

## 1. The problem: a variable appears in a pattern but is not necessarily allowed to be used

Consider the following code:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // Valid: text has matched
}

System.out.println(text); // COMPILE ERROR
```

`String text` is a **type pattern**. The variable `text` can only be used at points where the compiler can prove that the pattern **matched successfully**. After an `if` without an `else`, the condition may have been false, so `text` cannot be used by default.

This rule is called **flow scoping**: the scope of a *pattern variable* depends on **control flow and condition outcomes**, rather than just curly braces. The error typically manifests at compile time, such as `cannot find symbol` for a pattern variable that is not in scope; exact diagnostics may vary by JDK and code location.

This article focuses on how to determine scope, detect errors, fix them, and avoid breaking correctness when refactoring. It applies to Java 21 with finalized **type patterns**, **record patterns**, and **pattern matching for switch**; the examples run without needing preview enabled.

## 2. Basis for determining flow scope

According to the [Java Language Specification 21, §6.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3), a pattern variable can be **introduced when true**, **introduced when false**, or brought into scope by a statement, depending on the condition and statement form.

Read a conditional expression like this:

```java
obj instanceof String s
```

- When the expression is `true`, `obj` has matched `String` and the variable `s` has a value ready for use.
- When the expression is `false`, there is no basis to say `s` has matched; `s` cannot be used on that branch.
- `null instanceof String s` evaluates to `false`, so the pattern does not introduce the variable `s` on the `false` branch.

If negated:

```java
!(obj instanceof String s)
```

the meaning is inverted:

- The negated expression is **true** when the pattern **does not match**: `s` cannot be used in the `true` branch.
- The negated expression is **false** when the pattern **has matched**: `s` can be used in the `false` branch.

It is necessary to distinguish three things: **the variable is declared in syntax**, **the variable has a value when the match succeeds**, and **the locations where Java allows referencing the variable**. Seeing the identifier `s` in the same method or the same braced block is not enough to conclude it is in scope.

### Quick reference table

| Context | Can `s` be used? | Reason |
| --- | --- | --- |
| Right-hand side of `&&` in `obj instanceof String s && s.length() > 2` | **Yes** | The right-hand side only runs if the left-hand side is true |
| `then` branch of `if (obj instanceof String s)` | **Yes** | The branch runs when the pattern matches |
| `else` branch of `if (obj instanceof String s)` | **No** | This is the non-matching path |
| Right-hand side of `||` in `obj instanceof String s || s.isEmpty()` | **No** | The right-hand side only runs when the left-hand side is false |
| Right-hand side of `||` in `!(obj instanceof String s) || s.isBlank()` | **Yes** | The left-hand side being false means the pattern matched |
| `else` branch of `if (!(obj instanceof String s))` | **Yes** | The negation being false means the pattern matched |
| `then` branch of `if (!(obj instanceof String s))` | **No** | The negation being true means the pattern did not match |
| After a plain `if (obj instanceof String s)` | **No** | A path reaching after the `if` might not match |
| After the guard `if (!(obj instanceof String s)) return;` | **Yes** | The non-matching path has terminated |
| Inside `case String s when s.isBlank() ->` | **Yes** | The guard and case body are within the scope of `s` |

The table applies to the illustrated forms, where each variable `s` is only declared in the corresponding expression. Cases involving `return`, `throw`, `break`, or other compound conditions require analyzing the specific execution paths.

## 3. Error 1 — Using the variable in the `else` branch when the pattern is in the `if` condition

Incorrect code:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (obj instanceof String s) {
    System.out.println("Length: " + s.length());
} else {
    System.out.println("Failed match: " + s); // ERROR
}
```

The `else` branch runs when `obj` is not a `String` (or is `null`), so no matched value for `s` exists. You cannot "reuse" the name `s` to represent `obj` in the failed branch.

Fix:

```java
if (obj instanceof String s) {
    System.out.println("Length: " + s.length());
} else {
    System.out.println("Not a String: " + obj);
}
```

If you want to use `s` in the second branch, you must **invert the condition**:

```java
if (!(obj instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println("Length: " + s.length());
}
```

In the inverted condition, `s` in `else` is valid because only this branch guarantees that the pattern matched.

## 4. Error 2 — Using `s` after `if` without eliminating the failed path

Incorrect code:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (obj instanceof String s) {
    System.out.println("Found a string");
}
System.out.println(s.length()); // ERROR: obj might not be a String
```

Because the failed branch still reaches the last line, the compiler does not allow using `s`.

### Fix A: Keep processing inside the valid branch

```java
if (obj instanceof String s) {
    System.out.println("Found a string");
    System.out.println(s.length());
}
```

### Fix B: Guard clause with `return`

```java
static int lengthOrMinusOne(Object obj) {
    if (!(obj instanceof String s)) {
        return -1;
    }
    return s.length(); // Valid
}
```

At the line `return s.length()`, the **non-matching** branch has already exited the method. Java can prove that every remaining path has `s`.

### Fix C: Guard clause with `throw`

```java
static int requireLength(Object obj) {
    if (!(obj instanceof String s)) {
        throw new IllegalArgumentException("Expected String");
    }
    return s.length();
}
```

`throw` also blocks the failed flow. In contrast, a branch that only calls `System.out.println(...)` still completes normally, so it does not bring `s` into scope for subsequent statements.

### Also understand `if/else` with a terminating path

```java
static int requireTextLength(Object obj) {
    if (obj instanceof String s) {
        System.out.println("String found");
    } else {
        throw new IllegalArgumentException("Not a String");
    }
    return s.length(); // Valid: the else branch cannot complete normally
}
```

This is not an arbitrary compiler exception: according to the JLS, an `if/else` can bring a pattern variable into scope for subsequent statements when the other branch **cannot complete normally**. Rely on the paths that can reach the next statement, not just the position of curly braces.

## 5. Error 3 — Reading a pattern variable on the right-hand side of `||` when the left-hand side can fail

Incorrect code:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (obj instanceof String s || s.isBlank()) {
    System.out.println("Matched");
}
```

The `||` operator **short-circuits**: the right-hand side is only evaluated when the left-hand side is **false**. However, `obj instanceof String s` is false when `obj` does not match `String`; at that exact moment `s` is not bound. This is a case of using a variable outside flow scope.

Fix if you need to check "is a string and not blank":

```java
if (obj instanceof String s && !s.isBlank()) {
    System.out.println(s);
}
```

Fix if you need to classify strings and other objects separately:

```java
if (obj instanceof String s) {
    if (s.isBlank()) {
        System.out.println("Blank string");
    } else {
        System.out.println("Text: " + s);
    }
} else {
    System.out.println("Not a String");
}
```

### `||` is not always wrong

A **valid** case that is often misunderstood:

```java
static String nonBlankOrDefault(Object obj) {
    if (!(obj instanceof String s) || s.isBlank()) {
        return "missing";
    }
    return s.trim();
}
```

In the expression `!(obj instanceof String s) || s.isBlank()`, the right-hand side only runs when the negation is **false**, meaning `obj instanceof String s` was **true**. Therefore, `s.isBlank()` is valid.

After the `if`, only the path that makes **both sides** false continues, so `s` remains in scope and is guaranteed to be a non-blank `String`. This analysis is more accurate than the rule of thumb "`&&` is always allowed, `||` is always wrong".

## 6. Error 4 — Reversing the order of `&&` operands or using `&` instead of `&&`

Code that fails because it uses the variable **before** proving the match:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (s.length() > 2 && obj instanceof String s) {
    System.out.println("OK");
}
```

Even though a later part of the condition has `String s`, at the first `s.length()` nothing has declared or bound `s` yet.

Fix: check the pattern first, use the variable after.

```java
if (obj instanceof String s && s.length() > 2) {
    System.out.println("Long String: " + s);
}
```

Another mistake is accidentally changing `&&` to `&`:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (obj instanceof String s & s.length() > 2) {
    System.out.println(s);
}
```

`&` on booleans evaluates both sides; it does not carry the **flow scope on the right-hand side** rule like the conditional-and operator `&&` in the valid example. Even though the logical result may look similar in some cases, you cannot replace `&&` with `&` to use a pattern variable as above.

**Code review rule:** any expression that uses the variable must lie on a path where the match has succeeded, and the operator must actually guarantee that path.

## 7. Error 5 — Misunderstanding `!` and the matching branch

Error:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (!(obj instanceof String s)) {
    System.out.println(s.length()); // ERROR: this branch means NOT matched
}
```

Do not assume that because `String s` appears inside the parentheses, `s` automatically exists in every branch.

First fix:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

Second fix: use negation to handle the error, then continue along the success path.

```java
static String normalized(Object obj) {
    if (!(obj instanceof String s)) {
        return "not a String";
    }
    return s.trim().toLowerCase();
}
```

The key is the **boolean value of the entire condition**. For `!(obj instanceof String s)`, `s` is guaranteed to have matched when the negated condition is **false**.

## 8. Error 6 — Using `s` in the wrong branch of the `? :` operator

The ternary operator also follows flow scope rules:

```java
static int length(Object obj) {
    return obj instanceof String s ? s.length() : 0;
}
```

In `? then : else`, when the pattern condition is true, the branch after `?` has `s`; the branch after `:` does not.

Incorrect code:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
int result = obj instanceof String s
        ? 1
        : s.length();  // ERROR
```

With negation, the variable can be brought into **the other branch**:

```java
static int lengthWithNegation(Object obj) {
    return !(obj instanceof String s) ? -1 : s.length();
}
```

Do not use the variable after the entire operator just because it appeared in one branch:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
int n = obj instanceof String s ? s.length() : 0;
System.out.println(s); // ERROR: after the operator, match is not guaranteed
```

According to the JLS, `? :` does not automatically bring a pattern variable into scope for the surrounding expression when execution can take either branch.

## 9. Error 7 — Carrying a variable from one `switch` branch to another or outside `switch`

Java 21 supports pattern matching for `switch`:

```java
static String describe(Object obj) {
    return switch (obj) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s -> "text: " + s;
        case Integer n -> "number: " + n;
        default -> "other";
    };
}
```

In the branch `case String s when s.isBlank()`, `s` is in scope for the `when` **guard** and the corresponding branch. In the branch `case String s ->`, `s` belongs to that branch. Two branches using the same name `s` does not make them a single shared variable; each pattern is a separate declaration in its respective scope.

Incorrect code:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
switch (obj) {
    case String s -> System.out.println(s);
    case Integer n -> System.out.println(s); // ERROR: s belongs to another branch
    default -> {}
}
System.out.println(s); // ERROR: s does not escape switch
```

Fix by handling it in the **right branch** or returning a **common value**:

```java
String result = switch (obj) {
    case null -> "null";
    case String s -> "string:" + s;
    case Integer n -> "integer:" + n;
    default -> "unknown";
};
System.out.println(result);
```

`result` is a local variable declared **outside** `switch`, so it can be used afterward. The pattern variables `s` and `n` are only in scope within their respective branches.

Do not confuse a **dominance** error (a `case` branch being shadowed by an earlier broader type branch) with a **flow scoping** error. Both can prevent code from compiling, but for different reasons.

## 10. Error 8 — Using record pattern component variables outside the matching branch

With record patterns in Java 21:

```java
record Point(int x, int y) {}
```

The following introduces two pattern variables `x` and `y` **only when the entire record pattern matches**:

```java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y); // Valid
}
```

They cannot be used on a path that might fail:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (obj instanceof Point(int x, int y)) {
    System.out.println("matched");
}
System.out.println(x + y); // ERROR: x, y outside flow scope
```

Nested record patterns follow the same principle:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

static int sumX(Object obj) {
    if (!(obj instanceof Segment(
            Point(var x1, var y1),
            Point(var x2, var y2)))) {
        return -1;
    }
    return x1 + x2; // Valid after guard clause
}
```

In this snippet, Java only allows using the component variables when the **entire** `Segment(...)` with nested `Point(...)` patterns matches. If the `start` or `end` component is `null`, the nested record pattern `Point(...)` does not match; the `return -1` branch is taken.

**Note on `record`:** the names `x` and `y` in `record Point(int x, int y)` are component names. When writing `Point(int x, int y)` in pattern position, you are declaring **new pattern variables**. Even though the names match, their scope is not like fields, `p.x()` accessors, or regular local variables.

## 11. Error 9 — Colliding with a local variable name or confusing reuse with shadowing

Within a block, a pattern variable name cannot arbitrarily **shadow** a local variable name that is already in scope. Error example:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
String s = "existing";
if (obj instanceof String s) {  // ERROR: collides with variable already in scope
    System.out.println(s);
}
```

Fix with a clear name:

```java
String existing = "existing";
if (obj instanceof String matched) {
    System.out.println(matched);
}
```

However, you should not generalize that "once a pattern variable name is used, it can never be used again in the method". When a branch ends and the variable is **no longer in scope**, a new declaration at a valid location can reuse the same name. What you need to check is the **current scope** and Java's declaration rules, rather than just searching for duplicate identifier strings in the file.

## 12. Error 10 — Assuming `while` / `for` keeps the variable alive after the loop

A pattern variable matched by a loop condition can be used **in the loop body**, when the condition has been proven true:

```java
while (value instanceof String s) {
    System.out.println(s.length());
    break;
}
```

However, you cannot automatically use `s` after the loop, because the loop may terminate without a match, or via a `break` path.

```java
// INTENTIONALLY NON-COMPILING SNIPPET
while (value instanceof String s) {
    break;
}
System.out.println(s); // ERROR
```

For a basic `for` loop, a pattern variable introduced when true by the condition expression can be used in the **body** and **update** part of the loop, as long as the condition still proves the match. Example:

```java
for (; value instanceof String s; ) {
    System.out.println(s.length()); // Valid
    break;
}
```

In loops with negation, the rules for variables after the loop depend on both the condition and the possibility of **`break`**. JLS §6.3.2 has specific rules; avoid drawing conclusions based solely on the presence or absence of `while`.

## 13. Complete Java 21 program for verification

Save the code below to **`FlowScopeDemo.java`**. All techniques use **finalized** Java 21 features.

```java
public class FlowScopeDemo {
    record Point(int x, int y) {}

    static String classify(Object obj) {
        if (obj instanceof String s && !s.isBlank()) {
            return "text:" + s.length();
        }
        return "other";
    }

    static String label(Object obj) {
        if (!(obj instanceof String text)) {
            return "not-string";
        }
        return text.toUpperCase();
    }

    static String nonBlank(Object obj) {
        if (!(obj instanceof String s) || s.isBlank()) {
            return "missing";
        }
        return s.trim();
    }

    static int sum(Object obj) {
        if (obj instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    static String viaSwitch(Object obj) {
        return switch (obj) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "str:" + s.length();
            case Integer n -> "int:" + n;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("   "));
        System.out.println(label("flow"));
        System.out.println(label(42));
        System.out.println(nonBlank(" hi "));
        System.out.println(nonBlank("  "));
        System.out.println(sum(new Point(2, 5)));
        System.out.println(sum("x"));
        System.out.println(viaSwitch(null));
        System.out.println(viaSwitch("   "));
        System.out.println(viaSwitch(12));
    }
}
```

Compile and run with JDK 21:

```bash
javac --release 21 FlowScopeDemo.java
java FlowScopeDemo
```

Stdout output:

```text
text:4
other
FLOW
not-string
hi
missing
7
-1
null
blank
int:12
```

**Method-by-method breakdown:**

- `classify`: `s` is valid after `instanceof` on the left-hand side of `&&`, and in the `then` branch.
- `label`: `text` is valid **after** the negated `if` whose `return` eliminates the non-matching path.
- `nonBlank`: `s` is valid on the right-hand side of `||` because the negated left-hand side being **false** means it matched; `s` is also valid after the guard clause.
- `sum`: `x` and `y` belong to the record pattern `Point(...)` and are only used in the matching branch.
- `viaSwitch`: `s` and `n` are in scope for their respective case guard/body, not as variables for the entire `switch`.

## 14. Error-fixing strategy in real-world code

When the IDE or `javac` reports that a pattern variable name cannot be found, follow this sequence:

1. **Locate the pattern declaration:** for example `obj instanceof String s` or `case String s`.
2. **Determine which outcome guarantees a match:** `true` for a direct `instanceof`; `false` for `!(instanceof ...)`.
3. **Trace the exact control flow:** check `if/else` branches, `&&`/`||` order, `? :` branches, `return`/`throw`/`break` paths, and the scope of each `case`.
4. **Choose a minimal fix:** move the statement into the matching branch; change `||` to `&&` when that matches the logical intent; add a guard clause; or return a value from `switch`.
5. **Do not use a cast to hide a logic bug:** casting `(String) obj` outside the matching path can throw `ClassCastException`. Flow scoping lets the compiler catch the bug before runtime.
6. **Do not declare a separate variable with the same name to "patch the scope":** a variable outside the pattern can cause collisions or cause code to use the wrong variable; prefer clear naming and keeping data in the exact right scope.

### Before and after refactoring a chain of checks

Before, the code failed because it used the variable outside flow scope:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
if (request instanceof String payload && !payload.isBlank()) {
    System.out.println("accepted");
}
send(payload); // ERROR: pattern match is not guaranteed
```

After, keeping the call on the matching path:

```java
if (request instanceof String payload && !payload.isBlank()) {
    System.out.println("accepted");
    send(payload);
}
```

In this example, `send` and `request` are illustrative names provided by the application; this is a **snippet**, not a standalone program.

Or use a guard clause in a method:

```java
static String acceptedText(Object request) {
    if (!(request instanceof String payload) || payload.isBlank()) {
        return "rejected";
    }
    return "accepted:" + payload;
}
```

This approach is suitable when all subsequent processing steps require a `payload` already proven to be a non-blank `String`.

## 15. Error-spotting exercises and answers

### Exercise 1: Where can the variable be used?

```java
if (obj instanceof String s && s.length() >= 3) {
    System.out.println(s);
} else {
    System.out.println(s); // ?
}
```

**Answer:** `s` is valid on the right-hand side of `&&` and in the `then` branch. `s` is **not valid in `else`**, because execution can reach this branch when `obj` is not a `String` or when its length is less than 3.

### Exercise 2: Does inverting the condition lose `s`?

```java
static String f(Object obj) {
    if (!(obj instanceof String s)) {
        return "bad";
    }
    return s.toLowerCase();
}
```

**Answer:** No. `return s.toLowerCase()` is valid; by the time execution reaches here, the non-matching negated branch has already terminated.

### Exercise 3: How do these two `||` expressions differ?

```java
// A: Invalid
if (obj instanceof String s || s.isBlank()) { }

// B: Valid
if (!(obj instanceof String s) || s.isBlank()) { }
```

**Answer:** In A, the right-hand side runs when the match fails, so `s` is not available. In B, the right-hand side runs when the negated condition is false—meaning the pattern matched—so `s` is available. **B is valid with respect to scope**, while how to handle non-`String` objects is a separate business logic decision.

### Exercise 4: Does `switch` allow using `s` after it finishes?

```java
String result = switch (obj) {
    case String s -> s.toUpperCase();
    default -> "n/a";
};
System.out.println(result);
```

**Answer:** You can use `result`; you cannot use `s` directly after `switch`. These are two different declarations: `s` belongs to the pattern branch, while `result` belongs to the outer block.

### Exercise 5: Do record patterns change the rules?

```java
record Point(int x, int y) {}

if (!(obj instanceof Point(int x, int y))) {
    return;
}
System.out.println(x + y);
```

**Answer:** Inside a `void`-returning method, the code after the guard clause is valid: both `x` and `y` from the record pattern are bound on every path that continues.

## 16. Key takeaways

- **Flow scope depends on paths proven to have matched.** A pattern variable is not like a local variable declared directly in a block.
- **`&&` and `||` must be read in line with the condition's truth value.** With a direct `instanceof`, `&&` is usually convenient; with a negated `!(instanceof ...)`, `||` can be safe.
- **`return` and `throw` are useful tools for fixing scope** when you want to keep working with a matched variable in the rest of a method.
- **`case` and record patterns are also governed by flow scoping:** each pattern variable can only be used where the match is guaranteed.
- **The intentionally non-compiling snippets in this article are diagnostic examples** and must not be pasted into `FlowScopeDemo.java`.

## 17. References

- [Java Language Specification 21, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): official rules for flow scope, `&&`, `||`, `!`, `? :`, `if`, loops, and `switch`.
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): how patterns declare variables and nested record patterns.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): explanation of pattern variables and type checking with `instanceof`.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): finalized record patterns in Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): variable scope in pattern `case` labels, guards, and `switch` rules.
