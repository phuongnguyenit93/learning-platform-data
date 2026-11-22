# Why Can't a Variable Be Used When a Match Fails? — Flow Scoping in Java

In Java Pattern Matching, the expression `value instanceof String text` both checks the type of a value and potentially introduces a **pattern variable** named `text`. However, this variable name may only be used in locations where the compiler can prove that **the pattern has matched successfully**.

Therefore, when a match fails, you cannot write `text.length()` in the `else` branch or on an arbitrary line after the condition. This is the **flow scoping** rule, which prevents the program from using a variable that has not been bound to a value of the appropriate type. Java checks this rule **at compile time**, before the program runs.

> Core idea: **Pattern matches → variable is bound → can be used where a match is guaranteed. Pattern does not match → no valid binding → the pattern variable cannot be used on that path.**

The main examples use **Java 17+**, with type patterns for `instanceof` having become a standard feature since Java 16.

## 1. First example: why can't `else` read `text`?

Valid code:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // 4
} else {
    System.out.println("Not a String");
}
```

We can read this test in two parts:

- **Target expression:** `value`, which is evaluated to obtain a reference.
- **Type pattern:** `String text`, which requires the value to be non-`null` and compatible with `String`. If true, the variable `text` is bound to that reference and has static type `String`.

The `if` branch is only executed if the pattern matches, so `text.length()` is valid. However, try writing:

```java
Object value = 42;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // System.out.println(text.length()); // COMPILE ERROR if uncommented
}
```

In the `else` branch, the condition `value instanceof String text` evaluates to `false`. Here, `42` is an `Integer`, which does not match `String`. Java **does not bind the variable `text`**, and the name `text` has no valid scope in that branch. The compiler rejects the statement accessing `text`.

This error is **not** a `NullPointerException` thrown at runtime. The program cannot pass the compilation step if you place a statement using the variable in a location outside the pattern variable's scope.

## 2. What happens during a pattern test?

Consider:

```java
if (value instanceof String text) {
    // ...
}
```

You can visualize the process as follows:

```text
Evaluate value
      |
      v
Get runtime value
      |
      v
Test type pattern String text
      |
      +-- Match (String, non-null)
      |      |
      |      +--> instanceof result = true
      |      +--> Bind text to the String object
      |      +--> True branch is allowed to use text
      |
      +-- No match (not String or null)
             |
             +--> instanceof result = false
             +--> No binding for text
             +--> Cannot use text on this path
```

**Binding** here means attaching a matching value to the pattern variable. It does not create a copy of the object. With `Object value = "Java"`, inside the matching branch, `value` and `text` both reference the string `"Java"`; the difference is that `value` has static type `Object` while `text` has static type `String`.

From this follow two important properties:

1. **The runtime value determines whether the match succeeds or fails.** A variable with static type `Object` can still hold a `String` object and match successfully.
2. **Control flow determines where the pattern variable can be used.** Having an `instanceof` test above does not mean every line below it can use the variable.

Java does not automatically assign `null`, an empty string, or a default value to `text` when the test fails. Without a binding, there is no valid `text` value to use.

## 3. Three scenarios to distinguish

| Value of `value` | Result of `value instanceof String text` | Is `text` bound? | Which branch runs? |
| --- | --- | --- | --- |
| `"Java"` | `true` | Yes, `text` points to `"Java"` | `if` branch |
| `42` | `false` | No | `else` branch |
| `null` | `false` | No | `else` branch |

Note: a type check with `instanceof` on `null` returns `false`; by itself it **does not throw `NullPointerException`**. However, that does not mean the pattern variable is bound to `null`.

A common misconception is: "`text` already has type `String`, so it can be used as a `String` in every branch." The type declared in the pattern is only useful **when the pattern succeeds and where the variable is in scope**. The compiler does not allow a failing path to use a binding that was never established.

## 4. Runnable Java 17+ example: the same test with three inputs

Save the file **`FailedMatchScopeDemo.java`**:

```java
public class FailedMatchScopeDemo {
    static void explain(Object input) {
        if (input instanceof String text) {
            System.out.println("matched: " + text + " (" + text.length() + ")");
        } else {
            System.out.println("no String match: " + input);
        }
    }

    public static void main(String[] args) {
        explain("Java");
        explain(42);
        explain(null);
    }
}
```

Compile and run:

```bash
javac FailedMatchScopeDemo.java
java FailedMatchScopeDemo
```

Expected output:

```text
matched: Java (4)
no String match: 42
no String match: null
```

- Call 1: `"Java"` matches the type pattern `String text`; `text.length()` is called in the matched branch, producing `4`.
- Call 2: `42` does not match, because the runtime object is an `Integer`; the `else` branch only uses the original variable `input`.
- Call 3: `null` also does not match; the `else` branch can still print `input` thanks to Java's string concatenation.

In both failing calls, the program **does not access `text`**. The `instanceof` condition normally returns `false`, so the program still runs; only if you try to reference `text` in an invalid region does a **compile-time** error occur.

## 5. Flow scoping: "where is a match guaranteed?" matters more than "where was the condition written?"

**Flow scoping** is how Java determines the scope of a pattern variable based on control-flow paths. For a type pattern with `instanceof`, we usually ask:

- To reach this point, must the preceding pattern test have evaluated to true?
- Is there any path reaching here where the pattern failed?
- Does negation `!`, `&&` chaining, `||` chaining, or an early-exit statement change the answer?

### 5.1. Safe region: the true branch of `if`

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // Valid
}
```

Every execution entering the body goes through a successful match. The variable `text` is bound.

### 5.2. Unsafe region: the `else` branch

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    // System.out.println(text.length()); // Invalid if uncommented
}
```

Reaching the `else` branch means the pattern test **did not match**. You cannot use `text` here; use the `value` variable directly if you only need to report an error, or handle another type with a separate test.

### 5.3. Unsafe region: after a plain `if`

```java
if (value instanceof String text) {
    System.out.println(text);
}

// System.out.println(text.length()); // Invalid if uncommented
```

The line after the `if` can be executed even when the pattern just failed, because the `if` branch may be skipped. Having an `if` statement above is not enough to prove that `text` has been bound.

### 5.4. Safe region: the right-hand side of `&&`

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase());
}
```

`&&` is **short-circuiting**: the right-hand side is only evaluated when the left-hand side is `true`. If Java reaches `text.length()`, `value instanceof String text` is guaranteed to have matched. Therefore, `text` is valid on the right-hand side and inside the body of the true branch.

If `value = "Go"`, the pattern `String text` actually **matched**, but `text.length() >= 4` is `false`. Thus the entire `if` condition is false. This leads to a subtle rule: an `else` branch after an `&&` condition can run either because **the pattern failed** or because **the additional check failed**.

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println(text);
} else {
    // Cannot use text here:
    // it could be 42 (pattern failed) or "Go" (pattern matched, length condition failed).
}
```

### 5.5. Unsafe region: the right-hand side of `||`

```java
// Invalid if uncommented: the right-hand side only runs when the left-hand side does not match.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("...");
// }
```

`||` only evaluates the right-hand side when the left-hand side is `false`. In that case there is no guarantee that `text` has been bound; Java rejects using it.

Note the distinction: Java can still use **a normal boolean expression** on the right-hand side of `||`, but cannot use a pattern variable whose binding is not guaranteed:

```java
if (value instanceof String text || value == null) {
    // value can be used because it was already declared.
    // text is not guaranteed to exist here.
}
```

In this example, the condition can be true because `value == null` even though the pattern did not match, so the `if` body is also not a safe place to use `text`.

## 6. Why can negation `!` and `return` allow using the variable afterward?

Negation reverses the meaning of the conditional branches:

```java
if (!(value instanceof String text)) {
    System.out.println("Not a String");
} else {
    System.out.println(text.length()); // Valid: entering else means it matched
}
```

Because the outer expression is `!(...)`, the `else` branch of the negated `if` only runs when the original test `value instanceof String text` returned `true`. Flow scoping inspects the **underlying** condition and the negation, so `text` is valid in this `else` branch.

A very common technique is a **guard clause** (early-exit branch):

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    return text.length(); // Valid
}
```

Analysis:

1. If the pattern does not match, the negated condition is `true` and the method **terminates immediately** with `return -1`.
2. If execution reaches the `return text.length()` statement at the end, the non-matching path **can no longer reach here**.
3. Therefore Java knows for certain that `text` has been bound to a valid `String`.

Here, the variable is not "revived" after a failure; rather, the failing branch **has already exited the method**, and the remaining code below is exclusively for the succeeding path.

Similarly, a negated branch ending with `throw` can guarantee that normal statements afterward only run when the match succeeds. Whether using `return` or `throw`, you must consider **every path that can continue** to the point where the variable is used.

## 7. Runnable Java 17+ example: safe handling with a guard clause and `&&`

Save the file **`SafeFlowScopeDemo.java`**:

```java
public class SafeFlowScopeDemo {
    static String categorize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isEmpty()) {
            return "empty";
        }
        return "string length=" + text.length();
    }

    static String withConjunction(Object value) {
        if (value instanceof String text && text.length() >= 4) {
            return "long=" + text.toUpperCase();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(categorize("Java"));
        System.out.println(categorize(""));
        System.out.println(categorize(17));
        System.out.println(categorize(null));
        System.out.println(withConjunction("Java"));
        System.out.println(withConjunction("Go"));
        System.out.println(withConjunction(null));
    }
}
```

Compile and run:

```bash
javac SafeFlowScopeDemo.java
java SafeFlowScopeDemo
```

Expected output:

```text
string length=4
empty
not a string
not a string
long=JAVA
other
other
```

In `categorize`, every non-`String` value (including `null`) exits the method before `text` is used. The statements after the guard clause are therefore safe. The empty string `""` is still a `String` and still matches the pattern; it is simply separated out at the `text.isEmpty()` step.

In `withConjunction`, the `text.length()` call is guarded by the left-hand `instanceof`. For `"Go"`, the pattern matches, but the length condition is false. For `null`, the pattern fails and Java never evaluates `text.length()`.

## 8. Why can't you "recover" a pattern variable through a `boolean` variable?

The following snippet intentionally **does not compile** if uncommented:

```java
Object value = "Java";
boolean matched = value instanceof String text;

if (matched) {
    // System.out.println(text.length()); // Invalid
}
```

Even though `matched` holds `true` in this concrete example, flow scoping rules **do not infer a pattern variable's scope from a separately declared boolean variable**. `text` has no valid scope inside the body of `if (matched)`. Java evaluates the syntactic and control-flow rules of the pattern expression where the variable is declared; it does not treat an arbitrary `boolean` value as proof to carry the binding into a new scope.

The right approach is to use the variable directly in the branch where the pattern guarantees success:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Or use a guard clause so only the matching flow continues:

```java
if (!(value instanceof String text)) {
    return; // valid in a void method
}
System.out.println(text.length());
```

*The second snippet is an illustrative body of a `void` method; it is not a standalone Java class meant to be compiled directly.*

## 9. When a match fails, how should you handle the value?

Depending on your program's requirements, there are three clear ways to handle it.

**Approach A — Use the original target in the false branch.** Useful for logging, error reporting, or default handling:

```java
if (value instanceof String text) {
    System.out.println("length=" + text.length());
} else {
    System.out.println("Unsupported value: " + value);
}
```

`value` is a variable already declared outside the condition, so it can be used in both branches.

**Approach B — Match another pattern.** If the input has multiple supported types, each type pattern introduces **its own variable** in its succeeding branch:

```java
if (value instanceof String text) {
    System.out.println("String length=" + text.length());
} else if (value instanceof Integer number) {
    System.out.println("Integer value=" + number);
} else {
    System.out.println("Unsupported or null");
}
```

`number` is not a fallback value for `text`. It is bound when **the separate `Integer number` pattern** matches.

**Approach C — Check early and exit in the failing branch.** Useful when the rest of the method only serves the supported type:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.strip();
}
```

No failing path reaches the `text.strip()` call. Note that `strip()` operates on the already-matched string; it has nothing to do with re-evaluating the pattern.

If you want a genuine fallback value, **declare a separate fallback variable with explicit assignment rules**. Do not assume Java creates `text = null` when a match fails.

## 10. Connection to `switch` pattern matching (Java 21+)

The bind-only-on-match mechanism also appears in pattern matching for `switch`, standardized in **Java 21**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "text=" + text;
        case String text -> "blank String";
        case Integer number -> "number=" + number;
        case null -> "null";
        default -> "other";
    };
}
```

This is an illustrative method usable inside a Java 21+ class. With `case String text`, `text` is bound inside the `when` guard and the branch body once the pattern has matched. If that branch is not selected, you cannot arbitrarily use the name `text` in the `Integer`, `null`, or `default` branch. Each branch has the bindings of its own pattern.

For `"   "`, the type pattern `String text` in the first branch can match, but the guard `!text.isBlank()` is false; the next `case String text` branch is selected instead. This is another example showing that **the type match succeeding** and **an additional condition succeeding** are two separate things.

Keep the two version milestones distinct: type patterns for `instanceof` work in Java 17; `when` in `switch` as shown above requires Java 21+. The Java 17 examples in earlier sections do not require this `switch` syntax.

## 11. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "When a pattern fails, `text` is assigned `null`." | There is no binding when a type pattern fails; Java does not provide a default `text` value. |
| "Since `String text` was declared, `text` can be used in `else`." | A pattern variable's name is only in flow scope where a match is guaranteed. |
| "`instanceof` returning `false` is a runtime error." | With a type pattern, `false` is normal; trying to use the pattern variable out of scope is what causes a compile error. |
| "You can always use the pattern variable after an `if`." | Only when every path reaching that point guarantees a match, such as when the non-matching branch does `return`. |
| "Entering `else` from `instanceof String text && ...` means `String` did not match." | The pattern may have matched while the condition after `&&` was false. |
| "The right-hand side of `||` has `text` from the left-hand side." | The right-hand side of `||` only runs when the left-hand side is false, so binding is not guaranteed. |
| "Saving the result into `boolean matched` carries `text`'s scope along." | Flow scoping does not propagate bindings by inferring from an independent boolean variable. |
| "`null` is a `String` with an empty value." | `null` does not match the type pattern `String text`. The string `""` does match and has length 0. |

Another mistake is using a manual cast in the failing branch:

```java
if (!(value instanceof String text)) {
    // String wrong = (String) value; // May throw ClassCastException
}
```

Pattern matching does not make invalid casts safe. When a value is not a `String`, you need to handle that case or reject the input.

## 12. Self-checking flow scoping before running

For each use of a pattern variable, walk through these steps in order:

1. **Identify where the pattern is declared.** For example, `value instanceof String text`.
2. **Identify the pattern's match condition.** For the `String` type pattern: the value is non-`null` and compatible with type `String`.
3. **List all paths that can reach the line using the variable.** From the true branch? The false branch? After `&&` or `||`? Is there a `!`?
4. **Look for an unmatched path.** If there exists a path to that line where the pattern is not guaranteed to have succeeded, do not write code that depends on the variable's binding.
5. **Fix the control structure.** Move the code into the matching branch; use `&&` to guard an additional condition; use `return`/`throw` in the failing branch; or test a new pattern for another type.

Quick self-check example:

```java
// VALID: used when a match is guaranteed.
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}

// INVALID if the print statement is uncommented:
// if (value instanceof String text || value == null) {
//     System.out.println(text);
// }
```

In the second example, the condition can be true solely because `value == null`, so there is no guarantee that `text` has been bound.

## Conclusion

A pattern variable cannot be used when a match fails because **no valid binding exists for the variable**, and Java checks before runtime to ensure every use of the variable has a guaranteed matching path. **Flow scoping** ties pattern matching to control flow: the true branch, the right-hand side of `&&`, and code after a guard clause can be guaranteed; the false branch, the right-hand side of `||`, or a line after a plain `if` usually lack that guarantee.

To write safe code, always ask: **"Is there any path to this point where the pattern has not matched?"** If so, you must change where the variable is used or reorganize the control-flow branches.
