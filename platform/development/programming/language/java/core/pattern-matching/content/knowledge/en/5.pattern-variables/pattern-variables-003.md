# Pattern Variable Naming and Valid Scope in Java

## 1. What is a Pattern Variable and What Does Its Name Mean?

When using **pattern matching**, Java can both test whether a value matches a pattern and bind a variable of the matching type for use in safe locations. A variable declared by a pattern is called a **pattern variable**.

In Java 17, the basic scenario is the *type pattern* of `instanceof`:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Here:

- `value` is the expression being tested, with static type `Object`.
- `String` is the type to match.
- `text` is the **pattern variable name**. It has type `String` and is initialized from `value` when the type pattern matches.
- The `if` branch runs only when `value` actually matches the pattern, so `text` can be used inside that branch without an explicit cast.

The name `text` can be replaced with `s`, `message`, `candidate`, or any other valid identifier; **the variable name does not affect the matching condition**. However, the name directly affects code readability, potential name collisions, and reference scope. Two questions must be clearly distinguished:

1. **Is the name valid at declaration?** Java checks identifier rules and name collisions with declarations already in scope.
2. **Is the variable in valid scope at the point of use?** Java analyzes control flow to ensure the pattern has definitely matched before allowing references to the variable.

This second point is called **flow scoping**. It differs from the purely brace-based lexical scope of many ordinary local variables.

## 2. Pattern Variable Naming Rules

Pattern variables follow Java's identifier rules for local variables. Therefore, you should name them according to the same conventions as normal Java variables:

- It must be a valid **Java identifier**; keywords such as `class`, `if`, or `return` cannot be used. A single underscore `_` is not a valid ordinary variable name in Java 17.
- Names are **case-sensitive**: `text` and `Text` are two different identifiers.
- Letters, digits in valid positions, `_`, or `$` may be used according to Java rules; a name cannot start with a digit. Readable `camelCase` should be preferred.
- Choose names that describe the role after checking, such as `customer`, `exception`, or `response`. Very short names like `s` are acceptable in small checks, but should not be used mechanically in complex processing blocks.
- Avoid colliding with local variables or parameters that are still in scope. A name matching a **field** may be allowed due to shadowing, but can easily cause confusion.

Valid examples:

```java
if (value instanceof String userName) {
    System.out.println(userName);
}

if (value instanceof CharSequence charSequence) {
    System.out.println(charSequence.length());
}
```

The two checks above are independent. If `value` is a `String`, both patterns can match because `String` implements `CharSequence`. The type declared in the pattern determines which methods can be called through the pattern variable.

Invalid naming examples:

```java
// Invalid: starts with a digit
// if (value instanceof String 1name) { }

// Invalid: Java keyword
// if (value instanceof String class) { }

// In Java 17, a standalone _ cannot be used as an ordinary variable name
// if (value instanceof String _) { }
```

In newer Java versions with *unnamed patterns*, `_` serves a dedicated purpose and does not create a variable named `_` to reference; do not equate it with a named pattern variable in Java 17.

## 3. Flow Scoping: You Can Only Use the Variable When It Has "Definitely Matched"

With traditional local variables, `{...}` braces typically determine lexical scope. With pattern variables, the compiler also evaluates **the logical paths of expressions and control flow**. A pattern variable is only allowed to be used in places where Java can prove that the corresponding pattern has matched and the variable has been initialized.

```java
Object input = "Hello";

if (input instanceof String text) {
    System.out.println(text.length()); // Valid, text has matched
} else {
    // Cannot use text here: the pattern might have failed
}

// Cannot use text here: the if branch might not have executed.
```

At runtime, if `input` is `null` or an `Integer`, the pattern `String text` does not match, so there is no safe `text` value for those branches.

**Scope reference table for Java 17:**

| Location | Can pattern variable `s` be used? | Reason |
| --- | --- | --- |
| Inside the true branch of `if (x instanceof String s)` | Yes | The pattern matches upon entering the branch |
| Inside the `else` branch of the condition above | No | The pattern might have failed |
| After a normal `if` statement like the one above | No | Execution might have taken the non-matching path |
| Right-hand side of `x instanceof String s && s.length() > 0` | Yes | `&&` evaluates the right-hand side only when the left-hand side is true |
| Right-hand side of `x instanceof String s \|\| s.length() > 0` | No | `\|\|` evaluates the right-hand side only when the left-hand side is false |
| After `if (!(x instanceof String s)) return;` | Yes | The non-matching path has terminated |
| True branch of `x instanceof String s ? s.length() : 0` | Yes | That branch executes only when the pattern matches |
| Inside the body of `while (x instanceof String s)` | Yes | Each entry into the loop body must match the condition |

The table describes straightforward cases. For more complex expressions, you must analyze the exact control flow rather than simply memorizing that the variable "only lives inside the `if` braces."

## 4. `&&` and `||` Determine Scope on the Right-Hand Side

### Valid `&&` operation

```java
Object value = "Java";

if (value instanceof String s && s.length() >= 3) {
    System.out.println(s.toUpperCase()); // JAVA
}
```

Java evaluates the left-hand side first. Only when `value instanceof String s` is `true` is the right-hand side `s.length() >= 3` evaluated. Therefore, `s` is already initialized when used on the right-hand side. The additional condition may evaluate to false, but that does not negate the fact that the pattern matched beforehand.

This enables a safe, concise way to combine a type check with a content check:

```java
if (value instanceof String name && !name.isBlank()) {
    System.out.println("Valid: " + name.trim());
}
```

### Potentially invalid `||` operation

```java
// INVALID: the right-hand side runs when instanceof on the left-hand side returns false.
// if (value instanceof String s || s.isEmpty()) {
//     System.out.println("...");
// }
```

If `value` is not a `String`, the left-hand check is false, so Java must evaluate `s.isEmpty()`. However, the pattern **did not match**, so `s` is not in valid scope. This is a **compile-time error**, not a runtime `NullPointerException`.

Negation can change which flow is valid:

```java
if (!(value instanceof String s) || s.isEmpty()) {
    System.out.println("Not a non-empty String");
}
```

In this expression, the right-hand side `s.isEmpty()` runs only when `!(value instanceof String s)` is `false`, meaning the inner pattern matched. Therefore, using `s` on the right-hand side is valid. However, the `if` branch can also run when `value` is not a `String`, so do **not** assume that `s` can be used arbitrarily inside the body of that branch.

## 5. The Negation Operator `!`, the `else` Branch, and Guard Clauses

Negation reverses which branch is guaranteed to succeed:

```java
static void printLength(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not a String");
    } else {
        System.out.println(text.length()); // Valid
    }
}
```

Upon entering `else`, the negated condition was false; thus `input instanceof String text` is true, and `text` has been assigned a value.

A common pattern when further processing is needed below is a **guard clause**:

```java
static void process(Object input) {
    if (!(input instanceof String text)) {
        return;
    }

    // By this point, all remaining paths have matched String.
    System.out.println(text.toUpperCase());
}
```

Here, `text` can be used **after the `if` block**. Because the non-matching branch returned, no path can reach `System.out.println` without the pattern having matched.

Replacing `return` with `throw new IllegalArgumentException("Expected String");` also creates an exit path. However, if you omit the terminating statement and let execution continue, the compiler can no longer guarantee that the variable has matched after the `if`.

**Note:** The fact that the variable can be used after a guard does not mean it was declared and given a default value at the start of the method. A pattern variable is initialized as soon as the pattern matches during `instanceof` evaluation; Java simply allows using it at points that are safe according to control flow.

## 6. Name Collisions: When Is It an Error, and When Can a Name Be Reused?

### Cannot collide with a local variable currently in scope

The example below is invalid in Java 17:

```java
static void invalid(Object input) {
    String text = "Existing";

    // INVALID: a local variable named text already exists in the outer scope.
    // if (input instanceof String text) {
    //     System.out.println(text);
    // }
}
```

Similarly, you cannot declare a pattern variable with the same name as a method parameter that is in the same scope:

```java
// INVALID (illustration; will not compile if uncommented):
// static void invalid(Object input, String text) {
//     if (input instanceof String text) {
//         System.out.println(text);
//     }
// }
```

Rename the pattern variable to make its role clear:

```java
static void valid(Object input, String text) {
    if (input instanceof String candidate) {
        System.out.println(text + ": " + candidate);
    }
}
```

You must also check declarations in branches with **overlapping scopes**. The curly braces of an `if` body do not make every pattern variable name declared in the condition independent of outer local variables.

### A name can be reused when scopes do not overlap

```java
static void printBoth(Object first, Object second) {
    if (first instanceof String s) {
        System.out.println("first=" + s);
    }

    if (second instanceof String s) {
        System.out.println("second=" + s);
    }
}
```

Both pattern variables are named `s`, but they belong to **two independent checks**; the scope of `s` in the first `if` does not extend to the second `if`. Therefore, this snippet is valid and prints the values of the two objects in turn if they are `String`s.

Reusing a name does not mean the two variables are the same variable or share a value. In longer code, consider naming them `firstText` and `secondText` for easier tracking.

### Shadowing a field can be valid

Unlike local variables, a pattern variable can *shadow* a field with the same name:

```java
class Example {
    static String label = "FIELD";

    static void print(Object input) {
        if (input instanceof String label) {
            System.out.println(label.toUpperCase());
        }

        System.out.println(Example.label);
    }
}
```

Inside the `if` branch, the simple name `label` refers to the pattern variable of type `String`. To access the shadowed field, use `Example.label`. After the branch, where the pattern variable is no longer in scope, `label` can refer to the field again.

Although valid, shadowing easily causes confusion; it is usually better to choose a different name such as `matchedLabel`.

## 7. Pattern Variables in Ternary Expressions and Loops

### Conditional expression `? :`

```java
static int lengthOrZero(Object value) {
    return value instanceof String s ? s.length() : 0;
}
```

The branch to the right of `?` is evaluated only if the pattern matches, so `s.length()` is valid. The branch after `:` runs when the pattern does not match and **cannot use `s`**.

### `while` loop

```java
static void loop(Object value) {
    while (value instanceof String s) {
        System.out.println(s);
        value = null; // The next check will not match.
    }
}
```

The variable `s` is validly used inside the loop body, because entering the loop body requires matching during that evaluation of the condition. After the loop, you cannot assume `s` is usable: the loop might not have run at all, or it ended when the pattern failed.

**Do not infer memory behavior:** pattern variable initialization rules do not guarantee that the JVM creates a new object on each iteration; the variable references the matched object. The JVM may apply internal optimizations depending on context.

### When do two identical names conflict?

Consider **the declaration site together with all points where the variable is reachable via control flow**, not just by counting brace pairs. Declaring `s` in two short, separate branches is usually valid; declaring another `s` right where `s` is still in scope will cause a duplicate name error. When unsure, pick a different name and compile with the intended Java version.

## 8. Runnable Java 17 Program: Naming, Scope, Name Reuse

Save the complete code below as **`PatternScopeDemo.java`**:

```java
public class PatternScopeDemo {
    static String label = "FIELD";

    static void inspect(Object input) {
        if (input instanceof String label && !label.isBlank()) {
            System.out.println("if: " + label.toUpperCase());
        } else {
            System.out.println("not nonblank text");
        }

        if (input instanceof Integer number) {
            System.out.println("integer=" + number);
        }
    }

    static void afterGuard(Object input) {
        if (!(input instanceof String text)) {
            System.out.println("skip");
            return;
        }

        System.out.println("length=" + text.length());
    }

    static void reuse(Object left, Object right) {
        if (left instanceof String s) {
            System.out.println("first=" + s);
        }

        if (right instanceof String s) {
            System.out.println("second=" + s);
        }
    }

    public static void main(String[] args) {
        inspect("Java");
        inspect("   ");
        inspect(42);
        afterGuard("abc");
        afterGuard(null);
        reuse("left", "right");
        System.out.println("field=" + label);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
```

Standard output:

```text
if: JAVA
not nonblank text
not nonblank text
integer=42
length=3
skip
first=left
second=right
field=FIELD
```

Output breakdown:

1. `inspect("Java")`: `input` matches `String label`, and the string is not blank. Inside the branch, `label` is the **pattern variable**, so it prints `JAVA`.
2. `inspect("   ")`: the pattern still matches `String`, but `isBlank()` returns `true`, making the whole `&&` expression false and executing `else`. `label` is not used in that branch.
3. `inspect(42)`: the `String` pattern fails, then the `Integer number` pattern succeeds, printing `integer=42`.
4. `afterGuard("abc")`: the negated condition is false, execution passes the guard, and `text` can be used to print length `3`.
5. `afterGuard(null)`: the `String` pattern does not match; the guard branch prints `skip` and `return`s.
6. `reuse(...)`: both `if` statements can use their own `s` without conflict; prints `first=left` and `second=right`.
7. `field=FIELD`: the static field `label` remains untouched; the pattern variable with the same name inside `inspect` does not overwrite the field.

This example uses the **`instanceof` type pattern**, finalized in Java 16 and fully supported in Java 17. `--enable-preview` is not required.

## 9. Variable Name Scope in `switch` Pattern Matching (Java 21+)

Since Java 21, `switch` officially supports pattern matching. Each pattern `case` arm can declare a variable; that variable can be used in the **`when` guard** and the **body of the corresponding arm** when the pattern matches:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank";
        case null -> "null";
        default -> "other";
    };
}
```

Meaning:

- For `"Java"`, the pattern `String s` matches; `s` has a value when `when` checks `!s.isBlank()`. Result: `"text:Java"`.
- For `"   "`, the first type pattern matches, but the guard is false; `switch` continues searching for a matching arm and selects `case String s ->`, yielding `"blank"`.
- For `null`, the `case null` arm handles the value; it does not declare a pattern variable.
- For `42`, the `String` arms do not match; execution reaches `default` and yields `"other"`.

The two `case String s` arms here are valid because each arm's `s` variable is used within its own scope. The scope of a pattern variable in `switch` must follow the specific rules of the `switch` construct; especially with `:` labels and potential fall-through, do not assume every arm has the same scope rules as `if`. Using `->` arms as shown above makes the scope clearer.

Standalone runnable program for Java 21+ (file **`SwitchScopeDemo.java`**):

```java
public class SwitchScopeDemo {
    static String classify(Object value) {
        return switch (value) {
            case String s when !s.isBlank() -> "text:" + s;
            case String s -> "blank";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("   "));
        System.out.println(classify(null));
        System.out.println(classify(42));
    }
}
```

Compile/run with JDK 21 or later:

```bash
javac --release 21 SwitchScopeDemo.java
java SwitchScopeDemo
```

Output:

```text
text:Java
blank
null
other
```

A notable version difference: the full example in Section 8 runs with `--release 17`, whereas the `switch` example with `case String s when ...` requires Java 21+.

## 10. Common Mistakes and How to Fix Them

### Mistake 1: Referencing the variable in an `else` branch where matching is not guaranteed

```java
if (input instanceof String text) {
    System.out.println(text);
} else {
    // Invalid if uncommented: text may not have been initialized.
    // System.out.println(text.length());
}
```

**Fix:** write logic using `input` in the failure branch, or invert the condition and place the code that needs `text` in the branch guaranteed to match.

### Mistake 2: Using the variable on the right-hand side of `||` in the wrong direction

```java
// if (input instanceof String text || text.isBlank()) { ... } // Invalid
if (input instanceof String text && text.isBlank()) {
    System.out.println("Blank string");
}
```

**Fix:** choose an operator whose right-hand evaluation path guarantees the pattern result is already true; if the goal is "not a String or a blank String," use `!(input instanceof String text) || text.isBlank()`.

### Mistake 3: Accessing the pattern variable after an `if` when a failure path still exists

```java
if (!(input instanceof String text)) {
    System.out.println("Not String");
}

// Invalid if uncommented: the non-matching path can still reach here.
// System.out.println(text.length());
```

**Fix:** add `return` or `throw` in the failure branch when you truly want to continue processing only with a `String`, or move the processing into the matched branch.

### Mistake 4: Colliding with a local variable or parameter name

```java
String text = "A";
// if (input instanceof String text) { ... } // Invalid: name collision

if (input instanceof String candidate) {
    System.out.println(candidate);
}
```

**Fix:** choose a non-colliding name, preferably reflecting its role such as `candidate` or `parsedText`.

### Mistake 5: Assuming a pattern variable always has a default value

There is no rule that automatically initializes a pattern variable to `null` when the pattern fails. A pattern variable **cannot be used** on paths where the compiler cannot prove a match; this issue normally surfaces as a compile-time error before execution.

### Mistake 6: Confusing a pattern variable name with renaming an object

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text); // Java
}
```

`text` is a `String`-typed reference to the matched value; it does not create a new `String` object and does not change the declared type of `input` from `Object` to `String`.

### Mistake 7: Assuming a pattern variable is `final` by default

In pattern matching for `instanceof` since Java 16, pattern variables are **not `final` by default**. You can reassign the variable within its valid scope when not restricted by other rules; reassigning the pattern variable does not automatically modify the source variable. Even though allowed, avoid reusing the same name for multiple meanings that make data flow hard to read.

### Mistake 8: Reusing a name within the same active scope

You can use the same `s` in two independent `if` statements if their scopes do not overlap; however, you cannot declare a second pattern variable with the same name at a point where an earlier local variable or pattern variable is still in scope. When in doubt, rename the variable or narrow the block, then verify with `javac` for your target version.

## 11. Self-Check Questions

**Question 1.** Given `Object x = "abc";`, why is `if (x instanceof String s && s.length() > 2)` valid, whereas replacing `&&` with `||` fails?

**Answer:** `&&` allows the right-hand side to run only after the pattern matches; `||` runs the right-hand side only when the left-hand side is false, so `s` is not guaranteed to be initialized.

**Question 2.** Does the following snippet compile?

```java
static void verify(Object x) {
    if (!(x instanceof String s)) {
        return;
    }
    System.out.println(s.length());
}
```

**Answer:** Yes (Java 17+). Every path reaching `println` has eliminated the non-matching case.

**Question 3.** Is using the name `s` twice in two consecutive, non-nested `if` statements always a duplicate declaration error?

**Answer:** No. If the scope of the first pattern variable has ended before the second variable is declared, the name can be reused. The example in Section 8 illustrates this valid case.

**Question 4.** Given a class with a field `String label`, can `label.toUpperCase()` be called inside `if (obj instanceof String label)`?

**Answer:** Yes, if the static type of `obj` permits the type pattern and the pattern matches. A pattern variable can shadow a field; use `ClassName.label` to access the field when needed. However, using the same name should be avoided as it is error-prone.

**Question 5.** In a `switch` with `case String s when s.length() > 2 ->`, can `s` be used inside `when`?

**Answer:** Yes in Java 21+, because the guard is evaluated only after that arm's pattern matches. In Java 17, this pattern `switch` syntax is not yet a finalized feature.

## 12. Checklist When Writing Pattern Variables

Before using a pattern variable name, ask yourself in order:

1. **Is the name valid and meaningful?** Avoid keywords, names colliding with in-scope locals/parameters, and unnecessary field shadowing.
2. **Is the pattern type compatible with the static type of the tested expression?** Not every `instanceof` check can be written as a valid pattern if it is redundant or involves incompatible types in your target Java version.
3. **At the line where it is used, has the pattern definitely matched?** Check `&&`, `||`, `!`, `if/else`, `return`, loops, or `switch`.
4. **Could the variable be used in a failure branch or after its scope ends?** If so, restructure the control flow or use a different variable.
5. **Have you compiled with the right Java version?** For example, `instanceof` type patterns use Java 17; `case String s when ...` in `switch` requires Java 21+.

**Core rule:** *Name a pattern variable like a Java local variable, but determine its usable scope according to the paths along which Java can prove matching has succeeded.* That is why the same name can be valid in two independent blocks, and a variable declared inside a condition can still be used after an `if` when a guard eliminates all non-matching paths.

### Official Documentation

- [JLS Java SE 17, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [JLS Java SE 17, §6.3.1 — Scope for Pattern Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1)
- [JLS Java SE 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
