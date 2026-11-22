# Reading a pattern variable in the true branch of `instanceof` (Java 21)

In Java, an `if` statement often begins with a type check. With **pattern matching for `instanceof`**, we can both check the type and declare a variable of the exact type directly in the condition. This lesson focuses on **reading and using the pattern variable when the condition matches and the `true` branch is executed**.

After this lesson, you should understand why the variable can be used inside the `if` body, how the compiler knows the variable's type, when the variable is no longer in scope, and how to write combined conditions without running into variable scope errors.

## 1. From traditional `instanceof` to pattern variables

Before pattern matching, developers typically checked the type and then cast manually:

```java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

Since Java 16, type patterns for `instanceof` have been a standard feature. On Java 21, you can write the equivalent:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

In `value instanceof String text`:

- `value` is the expression being tested.
- `String` is the type to match.
- `text` is the **pattern variable**, with static type `String`.
- The `instanceof` operation returns `true` when the value is an object compatible with the `String` type (including when checking a compatible supertype in other examples), and `false` if it does not match or the value is `null`.

When the check succeeds, Java binds the same object in `value` to the variable `text`. **No new string is created and there is no need to write a `(String) value` cast**. The compiler already knows `text` is a `String`, so calling `length()`, `strip()`, `isBlank()`, or other `String` methods is valid.

> Key point: a pattern variable can only be used at locations where the compiler proves the pattern has matched. This rule is called *flow scoping* — variable scope depends on the program's control flow.

## 2. Why can the variable be read in the `true` branch?

Consider the statement:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

The execution flow is understood as follows:

1. Java evaluates `value` and checks `instanceof String`.
2. If the check is **true**, the `String text` pattern matches: `text` is assigned a reference to the tested object.
3. Only then does the `if` body run; reading `text.length()` is type-safe.
4. If the check is **false**, the `if` body is skipped, so the program does not attempt to read `text` when it has not been assigned.

For example, with `value = "abc"`, the program prints `3`; with `value = 123` or `value = null`, the `if` body does not run and the method prints nothing.

The pattern variable here is a variable with an explicit name and type, not a boolean value or an anonymous "cast result". You use `text` directly in the `true` branch just like an ordinary local `String` variable:

```java
if (value instanceof String text) {
    String normalized = text.strip();
    int length = text.length();
    System.out.println("normalized=" + normalized);
    System.out.println("length=" + length);
}
```

This snippet assumes `value` has already been declared in the enclosing method or scope; it is an illustrative example, not a standalone program.

## 3. The `else` branch and code after `if` do not automatically have the variable

With the non-negated condition `value instanceof String text`, the `true` branch is the matched path, while the `else` branch is the **unmatched** path:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip()); // VALID
    } else {
        System.out.println("Not a String");
        // System.out.println(text); // COMPILE ERROR
    }

    // System.out.println(text); // ERROR in this if/else structure
}
```

Do not interpret declaring `text` in the condition as declaring it for the entire method. The compiler only allows using it in code where there is proof that the condition matched. If the variable is needed in multiple paths, redesign the control flow or declare an appropriate variable in a shared scope.

There is an important exception to avoid misunderstanding: **flow scoping is not based solely on curly braces**. If the non-matching branch terminates the method, the compiler may allow using the variable after the `if`:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // VALID: every path reaching here has matched
}
```

In this example, `return 0` blocks every non-matching path; therefore, `text` is definitely assigned at the final statement. This still follows the same principle: **only read the variable when the compiler proves the pattern succeeded**.

## 4. Combining with `&&`: reading the variable in the condition and in the `true` branch

The `&&` operator in Java is **short-circuiting**: the right-hand side is only evaluated when the left-hand side is `true`. Because of this, we can check the type and then use the pattern variable to inspect its contents:

```java
static void printNonBlank(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.strip());
    }
}
```

This order is safe:

1. `value instanceof String text` is evaluated first.
2. Only when `String` matches does Java evaluate `!text.isBlank()` on the right-hand side.
3. If **both** conditions are true, the `if` body runs and `text` is available to read.

For `null` or a non-`String` object, Java skips the `text.isBlank()` call because the left-hand side of `&&` is already false. For a whitespace-only string, the type match succeeds but the `!text.isBlank()` check fails, so the `if` body does not run either.

Conversely, do not treat `||` as equivalent to `&&`. With `||`, the right-hand side can make the entire condition true even if the type pattern on the left-hand side did not match:

```java
// DOES NOT COMPILE: text is not guaranteed to be assigned in the true branch.
if (value instanceof String text || value == null) {
    System.out.println(text.length());
}
```

If you need to handle both `null` and strings, separate the branches and only use `text` in the matched branch. For example:

```java
if (value == null) {
    System.out.println("missing");
} else if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("other type");
}
```

The snippets in this section are illustrative code placed inside a method that has a variable `value` of type `Object`.

## 5. Negating the condition changes which branch can use the variable

Consider a condition with `!`:

```java
if (!(value instanceof String text)) {
    System.out.println("Not a String");
} else {
    System.out.println(text.length()); // VALID
}
```

The `true` branch of the **entire negated expression** now means the type match **failed**, so `text` cannot be read in that branch. The `else` branch is where the compiler knows the pattern matched. What you need to track is whether the match succeeded, not just which branch is labeled `true`.

To learn basic `instanceof` most easily, start with the non-negated form `if (value instanceof String text)`: reading the variable inside the `if` body is very intuitive.

## 6. Standalone Java 21 example and exact stdout

Create the file **`PatternVariableTrueBranchDemo.java`** with the following full contents:

```java
public class PatternVariableTrueBranchDemo {

    static void inspect(Object value) {
        if (value instanceof String text) {
            System.out.println("Raw length: " + text.length());
            System.out.println("Trimmed: " + text.strip());
        } else {
            System.out.println("Not String");
        }
    }

    static void inspectNonBlank(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("Nonblank: " + text.strip());
        } else {
            System.out.println("Not nonblank String");
        }
    }

    public static void main(String[] args) {
        inspect("  Java 21  ");
        inspect(42);
        inspect(null);
        inspectNonBlank("  Hello  ");
        inspectNonBlank("   ");
    }
}
```

Use **JDK 21** to compile and run (no preview features needed):

```bash
javac --release 21 PatternVariableTrueBranchDemo.java
java PatternVariableTrueBranchDemo
```

Expected output on stdout:

```text
Raw length: 11
Trimmed: Java 21
Not String
Not String
Nonblank: Hello
Not nonblank String
```

Step-by-step explanation:

- `inspect("  Java 21  ")`: the object is a `String`, so it enters the `true` branch; `text.length()` counts 11 characters, including the two leading and trailing spaces; `text.strip()` returns `Java 21`.
- `inspect(42)`: the actual object is an `Integer`, which does not match `String`, so it prints `Not String`.
- `inspect(null)`: `null instanceof String` is `false`; no `NullPointerException` occurs simply from the `instanceof` check.
- `inspectNonBlank("  Hello  ")`: both matches the type and is not a blank string, so it prints `Nonblank: Hello`.
- `inspectNonBlank("   ")`: still matches `String`, but fails the `!text.isBlank()` condition, so it enters the `else` branch.

This example demonstrates two distinct roles: `instanceof` guarantees the **correct type**, while `!text.isBlank()` checks an additional **data condition**. Pattern matching does not automatically validate whether a string meets business rules.

## 7. Common mistakes when reading a pattern variable

**Mistake 1 — using the variable in the non-matching branch.** In the `else` branch of `if (value instanceof String text)`, `text` is not guaranteed to exist. Move the code that uses `text` into the matching branch, or rewrite the control flow.

**Mistake 2 — using the variable after `if` while ignoring the false path.** With an ordinary `if` that can continue even if the match fails, you cannot read `text` after the block. Only certain flow-scoping structures whose non-matching branch clearly terminates (such as the early return in section 3) allow this.

**Mistake 3 — using `||` as if the `true` branch always matches the pattern.** Another operand of `||` can make the condition true. Use `&&` when you want to check additional properties of the pattern variable after the type check.

**Mistake 4 — casting again unnecessarily.** Inside the `true` branch, `text` already has type `String`. Writing `((String) value).length()` is redundant, reduces clarity, and fails to take advantage of the newly declared variable.

**Mistake 5 — assuming matching `String` means the data is non-empty.** Strings like `""` or `"   "` still make `instanceof String` true. If non-empty or non-blank data is required, add `!text.isEmpty()` or `!text.isBlank()`, depending on the requirement.

**Mistake 6 — confusing a pattern variable with a cast for any kind of data.** `instanceof String text` only succeeds for objects compatible with `String`. It does not convert an `Integer` into a string or automatically parse data.

## 8. Self-check

Given `Object value = "abc";` and the expression:

```java
if (value instanceof String text && text.length() == 3) {
    System.out.println(text.toUpperCase());
}
```

This is valid code inside a method; the statement prints `ABC`. Because the type pattern matched, `text` has type `String` both on the right-hand side of `&&` and inside the `true` branch.

Replace `value` with `null`: the `if` branch does not run and `text.length()` on the right-hand side is not evaluated. Replace `value` with `"ab"`: the type match succeeds but the length condition is false, so the branch does not run either. If you change `&&` to `||`, the program no longer guarantees that `text` has matched for reading inside the `if` body.

Whenever reading any pattern variable, ask yourself: **"At this point, have all possible paths reaching here matched the pattern?"** If the answer is yes, the compiler allows using the variable; if not, adjust the condition structure or handle the data in the appropriate branch.
