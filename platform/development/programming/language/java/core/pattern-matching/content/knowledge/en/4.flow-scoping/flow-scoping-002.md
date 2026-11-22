# Variable Scope in `if` Branches: Java Pattern Matching Flow Scoping

## 1. Where can a pattern variable be used?

In Java, **flow scoping** is the mechanism by which the compiler determines **where a variable declared by a pattern can be referenced**, based on control flow and the definite outcome of the pattern test.

Example with an `instanceof` type pattern:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

The snippet above is **illustrative code inside a method that has a `value` variable**. When `value` is a `String` object, the `instanceof String text` check returns `true` and the pattern variable `text` is bound to a reference to that same object. Inside the **`if` branch where the condition is definitely true**, the compiler allows calling `text.length()` without a manual cast.

When `value` does not match `String`, including the `null` case, the condition evaluates to `false`; the variable `text` is not bound for that path. Therefore, the code cannot use `text` at a location where pattern matching is not guaranteed.

The core rule is:

> A pattern variable is only in scope on paths where the compiler can definitely deduce that the pattern has matched.

This is **control-flow-based scoping**; it is not quite the same as the "declared inside braces, usable throughout those braces" rule of ordinary local variables.

## 2. Scope in `if`, `else`, and after `if`

Suppose `value` has a declared type of `Object`.

### The `if` branch on a positive check

```java
if (value instanceof String text) {
    // Valid: entering here means the String text pattern has matched.
    System.out.println(text.toUpperCase());
} else {
    // Invalid if referencing text here:
    // System.out.println(text);
}
// Also invalid if using text here:
// System.out.println(text.length());
```

With this basic structure:

- **Inside the `if` body:** `text` is allowed to be used because the pattern check condition succeeded.
- **Inside the `else` body:** `text` is not allowed to be used because this branch executes when the condition is false and the pattern is not guaranteed to have matched.
- **After the entire `if/else`:** `text` cannot be used by default because control flow may have taken the non-matching branch.

The word "invalid" here means a **compile-time error**, not a `NullPointerException` that only appears at runtime. The compiler does not allow referencing a pattern variable outside its valid scope.

### Compared with a variable declared inside the block body

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
// text is also no longer in scope here.
```

This is the approach of checking the type and then casting manually. The variable `text` is a local variable declared inside the `if` block body. With pattern matching, the variable `text` is declared **directly inside the conditional expression**, so it can also be used in other parts of the Boolean expression if control flow proves it has matched. This is an important difference.

**Do not interpret "bound" as converting the object:** `String text` does not create a new string. The pattern variable simply has the static type `String` and references the existing matching `String` object.

## 3. `&&`: the pattern variable is usable on the right-hand side

The `&&` operator in Java evaluates **from left to right** and **short-circuits**: if the left-hand side is false, the right-hand side is not evaluated.

```java
if (value instanceof String text && text.length() > 3) {
    System.out.println("Chuỗi dài: " + text);
}
```

When Java needs to evaluate `text.length() > 3`, the `value instanceof String text` expression on the left has definitely returned `true`. Therefore:

1. `text` has been bound to a non-`null` `String`.
2. `text` **is in scope on the right-hand side of `&&`**.
3. If both sides are true, `text` is also usable inside the `if` branch body.

**Note:** the pattern may match while the overall `if` condition is still false. With `value = "hi"`, `String text` matches, but `text.length() > 3` is `false`. In that case, Java does not execute the `if` body. If there is an `else`, the `else` branch can run, but `text` cannot be used in that branch because the overall condition being false can come from multiple causes.

Multiple conditions can be chained when each step preserves the guarantee:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 5) {
    System.out.println(text.substring(0, 5));
}
```

This code is valid: the next condition only runs when the previous two conditions are true. Because `text.length() >= 5` is already established, `substring(0, 5)` in the selected branch will not go out of bounds.

## 4. `||`: you cannot arbitrarily use the pattern variable

The `||` operator also short-circuits: **the right-hand side is evaluated when the left-hand side is false**. Therefore, the following code **does not compile**:

```java
if (value instanceof String text || text.isEmpty()) {
    System.out.println("Không hợp lệ");
}
```

When the left-hand side `value instanceof String text` is false, Java tries `text.isEmpty()`. However, in that case `text` is not bound. The compiler detects this and reports an out-of-scope variable reference error.

Even if the right-hand side is a valid independent condition:

```java
if (value instanceof String text || value == null) {
    // Cannot assume text is usable here:
    // System.out.println(text.length());
}
```

The entire condition can be true **solely because `value == null`**, while the `String text` pattern did not match. Therefore, inside the `if` body, the binding of `text` is not guaranteed.

A comparison to remember:

| Conditional expression | Can `text` be used on the right-hand side? | Can `text` be used in the `if` branch if the condition is true? |
| --- | --- | --- |
| `value instanceof String text` | No right-hand side | Yes |
| `value instanceof String text && !text.isBlank()` | Yes | Yes |
| `value instanceof String text || value == null` | No reference to `text` on the right-hand side; adding one would not be guaranteed | No |
| `!(value instanceof String text)` | No right-hand side | No, because the `if` branch is the non-matching path |

This table examines specific expressions; it does not claim that **every** combination of `||` with a pattern is invalid. You must consider the control-flow logic and the position where the variable is used.

## 5. Negation `!` flips the branch where the variable can be used

If you write `if (!(value instanceof String text))`, the `if` branch only runs when **the pattern does not match**:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải chuỗi");
    // Cannot use text here.
} else {
    // Valid: entering else means the pattern has matched.
    System.out.println("Độ dài: " + text.length());
}
```

Here `text` is usable in the `else` branch of the negated check, because `!(...)` is `false` only when the inner pattern has matched.

### Guard clause with `return`

The most common writing pattern is to exit the non-matching path early:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

The `return text.length();` part appears **after** the `if` block yet is still valid. Because the non-matching path already executed `return`, only the matching path can continue to this line.

Therefore, the statement "a pattern variable can never be used after an `if`" is **too absolute**. Scope depends on the proven path, and the guard clause form above is an important example.

### Guard clause with `throw`

```java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text.trim();
}
```

The line `return text.trim();` is also valid because if it does not match, the first branch throws an exception and cannot complete normally. This pattern fits when an API wants to reject invalid-type input rather than return a default value.

**Note:** simply having a `return` somewhere inside an `if` does not automatically make the pattern variable valid everywhere. The compiler relies on paths that **can continue execution** to the specific reference site.

## 6. Standalone runnable example with Java 17

Create the file `IfPatternScopeDemo.java`:

```java
public class IfPatternScopeDemo {

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text(" + text.length() + "): " + text;
        } else if (value instanceof Integer number) {
            return "Number: " + (number + 1);
        }
        return "Other";
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    public static void main(String[] args) {
        Object[] values = {"java", "", 41, null};

        for (Object value : values) {
            System.out.println(
                    describe(value) + " | length=" + lengthOrMinusOne(value));
        }
    }
}
```

Compile and run:

```bash
javac IfPatternScopeDemo.java
java IfPatternScopeDemo
```

Stdout:

```text
Text(4): java | length=4
Other | length=0
Number: 42 | length=-1
Other | length=-1
```

Breakdown of each input:

- `"java"`: the `String text` pattern matches, and `!text.isBlank()` is true, so `describe` uses `text` in the first branch body; `lengthOrMinusOne` uses `text` after the guard clause. The length result is `4`.
- `""`: still a `String`, so **the pattern matches**. However, `isBlank()` returns `true`, making the overall condition of the first branch false; `describe` returns `Other`. In `lengthOrMinusOne`, the negated check is false so `return -1` is skipped; `text.length()` returns `0`.
- `41`: the element is an `Integer` autoboxed when placed into `Object[]`; the second branch of `describe` can use `number` and returns `Number: 42`. `lengthOrMinusOne` returns `-1`.
- `null`: both `null instanceof String` and `null instanceof Integer` are false; both methods follow the non-matching path and never invoke a method on an unbound `String` variable.

This code **runs directly on Java 17**, without needing `--enable-preview`. Pattern matching for `instanceof` was standardized in Java 16; this lesson does not depend on `switch` pattern syntax standardized later in Java 21.

## 7. Common compile errors and misconceptions

### Error 1: Using the variable in the `else` branch of a positive check

```java
if (value instanceof String text) {
    System.out.println(text);
} else {
    // Error if uncommented:
    // System.out.println(text.length());
}
```

The `else` branch is precisely where the `instanceof` condition is false, so having a `text` variable of type `String` is not guaranteed.

### Error 2: Using the variable on the right-hand side of `||`

```java
// Does not compile if uncommented:
// if (value instanceof String text || text.isEmpty()) {
//     System.out.println(text);
// }
```

The execution path to `text.isEmpty()` occurs when the check on the left did not match. This is a **flow-scoping** error.

### Error 3: Treating a pattern variable as a method-wide variable

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }

    // Invalid if uncommented:
    // System.out.println(text.length());
}
```

You should not bring `text` outside as if it were declared and initialized for all paths. If you need to handle both cases, use an explicit `if/else`, a guard clause, or redesign the parameter type.

### Error 4: Redeclaring the same name in an existing scope

```java
static void nameCollision(Object value) {
    String text = "existing";

    // Invalid: the name text already exists in scope:
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }

    if (value instanceof String matchedText) {
        System.out.println(matchedText);
    }
}
```

Pattern variable naming must not conflict with an existing local variable in a scope where Java forbids redeclaration. Choosing a role-descriptive name such as `matchedText` helps avoid errors and makes the code clearer.

### Error 5: Confusing "pattern matched" with "overall condition is true"

```java
Object value = "hi";
if (value instanceof String text && text.length() >= 5) {
    System.out.println("Long");
} else {
    System.out.println("Short or not a string");
}
```

The stdout of the snippet above (when placed inside a runnable method) is:

```text
Short or not a string
```

The `String text` pattern **did match** `"hi"`, but the length condition was false. The `else` branch cannot use `text` because logically the overall condition can also be false when the object is not a string.

### Error 6: Confusing compile-time scope with data lifetime

Flow scoping determines **where a pattern variable name can be accepted by the compiler**. It does not mean Java creates, destroys, or copies the `String` object each time execution enters or leaves a branch. The object still follows normal JVM reference and garbage-collection rules; variable name scope is a separate matter.

## 8. Quick comparison of `if` forms

| Code form | Path definitely matched | Where the pattern variable can be used |
| --- | --- | --- |
| `if (v instanceof String s) { ... }` | The `if` branch | Inside the `if` body |
| `if (v instanceof String s && s.length() > 0) { ... }` | Right-hand side of `&&` when evaluated; `if` body when the entire condition is true | On the right-hand side of `&&` and in the `if` body |
| `if (v instanceof String s) { ... } else { ... }` | The `if` branch | Cannot use `s` in the normal `else` |
| `if (!(v instanceof String s)) { ... } else { ... }` | The `else` branch | Can use `s` in the `else` branch |
| `if (!(v instanceof String s)) return;` then use `s` | Continuation path after `if` | Can use `s` after the guard clause |
| `if (v instanceof String s || v == null) { ... }` | No guarantee when the entire condition is true | Cannot assume `s` is usable in the `if` body |

All examples in the table assume `v` is a variable of a suitable broad reference type, such as `Object`, and there is no conflicting declaration with the same name.

## 9. How to apply and self-check

When you need to check a type for concise handling right inside a branch, use it directly:

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.charAt(0));
}
```

When you want to filter out wrong-type input early and continue processing below, prefer a guard clause:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length());
```

The second snippet is an **illustration placed inside a method returning `void`**. Flow-scoping rules make `text` valid after the `if` statement because the wrong-type path has terminated.

**Self-check:** given `Object v = "abc";`, in the expression `v instanceof String s && s.length() == 3`, is the right-hand side of `&&` allowed to use `s`? **Yes**, because it is only evaluated after the pattern has matched. If you replace `&&` with `||` and reference `s` on the right-hand side, is it valid? **No**, because the right-hand side runs when the pattern may not have matched.

**Remember:** the scope of a pattern variable is determined by **paths where the pattern is definitely matched**, not simply by the number of curly braces around an `if` branch. Understanding this principle helps you read Java 17+ code accurately, eliminate repetitive manual casts, and avoid compile-time errors when writing combined conditions.