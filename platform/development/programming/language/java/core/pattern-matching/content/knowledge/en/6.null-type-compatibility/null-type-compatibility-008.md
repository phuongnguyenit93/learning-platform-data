# Unapplicable Patterns Due to Subtype Relationships in Java

## 1. Why Can a Type Pattern Be Rejected?

With `instanceof`, Java has two easily confused forms:

```java
value instanceof String       // Type check, no variable declared
value instanceof String text  // Type pattern, with pattern variable text
```

The lines above are only **expression illustrations**; they must appear in a valid position such as an `if` condition or a Boolean assignment. For a type pattern, the compiler examines the **static type** of the expression on the left and the **pattern type** on the right to decide whether the pattern is applicable.

Let:

- **S** be the static type of the expression being tested, determined at compile time.
- **T** be the type declared in the type pattern `T name`.
- **S <: T** mean that `S` is a subtype of `T`, including the case where `S` and `T` are the same type. For example: `String <: CharSequence`, `String <: Object`, and `String <: String`.

**Important version-specific point:** in **Java 16–20 (including Java 17)**, the expression `e instanceof T name` causes a **compile-time error if S <: T**. The reason is that this type check is already guaranteed to be true for any **non-`null`** value of type `S`, so it is not a necessary type-narrowing check. Starting in **Java 21**, Java allows such type patterns (often called *unconditional type patterns*); when used with `instanceof`, a `null` value still evaluates to `false`.

Therefore, **you must not generalize that testing a subtype with a pattern is forbidden in all Java versions**. When learning or compiling a Java 17 project, you must apply the Java 17 rule; when using Java 21+, you need to understand that the rule has changed.

## 2. Java 17: If the Static Type Is Already a Subtype, the Pattern Fails

An illustrative example inside a Java 17 method:

```java
String text = "java";

// COMPILE-TIME ERROR on Java 17:
if (text instanceof String sameText) {
    System.out.println(sameText);
}

// ALSO A COMPILE-TIME ERROR on Java 17:
if (text instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

**Why do both fail?**

1. In the first snippet, the static type of `text` is `String` and the pattern type is also `String`: `String <: String`.
2. In the second snippet, the static type is still `String`; `String` implements `CharSequence`, so `String <: CharSequence`.
3. If `text` is non-`null`, both type checks would be true. Java 17 rejects using a **type pattern with a variable** for these checks right at compile time.

Diagnostic messages may vary by compiler version, such as stating that the expression type is a subtype of the pattern type or that *unconditional patterns in instanceof* are not supported in Java 17 source level. This is a **compile-time error**, not a runtime `ClassCastException` or `NullPointerException`.

### Same Intent, Correct Way to Write It on Java 17

If you already have a `String` variable and only want to process it when it is non-`null`:

```java
String text = "java";

if (text != null) {
    System.out.println(text.length());
}
```

If you need a different local name in the branch:

```java
String text = "java";

if (text != null) {
    CharSequence chars = text;
    System.out.println(chars.length());
}
```

The `String` type is already known from the start, so there is no need to rebind it with a type pattern. The assignment from `String` to `CharSequence` is a **widening reference conversion**, which is valid because `String` is a subtype of `CharSequence`.

### Regular `instanceof` Still Differs from a Type Pattern

```java
String text = "java";

// VALID on Java 17:
if (text instanceof CharSequence) {
    System.out.println(text.length());
}
```

The `instanceof CharSequence` form only performs a **type check** and does not declare a pattern variable. Java 17's rule forbidding a type pattern when `S <: T` **must not be conflated** with the rule for the regular `instanceof T` type check.

Although this syntax is valid, it is still a redundant check if you only want to verify that `text` is a `CharSequence`: whenever `text` is non-`null`, the subtype relationship already guarantees that.

## 3. Reversing the Relationship: Checking from Supertype to Subtype Is Valid

Compare this with the following snippet on Java 17:

```java
Object value = "java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

The line above is **valid** because the **static type** of `value` is `Object`, while the pattern requires `String`. At runtime, `value` could be a `String`, an `Integer`, another object, or `null`. The check is genuinely meaningful to **narrow from a supertype to a subtype** and only binds the variable `text` when it succeeds.

The next snippet is also valid:

```java
CharSequence sequence = "java";

if (sequence instanceof String text) {
    System.out.println(text.length());
}
```

Even though the current runtime object is the string `"java"`, the **static type** of `sequence` is still `CharSequence`. Another `CharSequence`, such as `StringBuilder`, might not be a `String`. Therefore, Java 17 accepts `sequence instanceof String text`.

This is an important distinction between **the declared type of a variable** and **the actual class of an object**. The compiler decides syntactic validity based on the static type; only later, at runtime, does `instanceof` check the specific value.

### Do Not Force-Widen a Type Just to "Bypass" the Error

You could write:

```java
String text = "java";
Object value = text;

if (value instanceof String matched) {
    System.out.println(matched.length());
}
```

This compiles on Java 17 because `value` has static type `Object`. However, if the data is already known to be a `String`, adding an `Object` variable just to use a pattern is **unnecessary**. Keeping the `String` type and checking for `null` when needed is clearer.

## 4. Distinguishing Two Kinds of Type-Compatibility Errors

Do not lump every `instanceof` pattern error into a single cause. There are at least two different situations.

### Case A: S Is Already a Subtype of T — Redundant Check on Java 17

```java
String text = "hello";

// Java 17 error: String is a subtype of CharSequence.
// if (text instanceof CharSequence chars) { ... }
```

The pattern imposes a type condition that needs no narrowing. Java 17 rejects this type pattern with a variable. Java 21+ allows it.

### Case B: Incompatible Types for Conversion — The Pattern Can Never Match

```java
String text = "hello";

// Compile-time error in both Java 17 and Java 21:
// if (text instanceof Integer number) { ... }
```

Here, `String` and `Integer` are classes that cannot be cast between each other for this kind of check. The check can never succeed, and the compiler rejects it.

**The difference:** Case A is a known type that is *already guaranteed to satisfy the pattern* for any non-`null` value. Case B is a known type that *can never satisfy the pattern*. Both reasons involve types, but they are not the same.

Saying two types "have no subtype relationship" is **not enough to conclude there is always an error**: interface relationships and Java's cast compatibility rules must also be considered. For example, an interface type may have different implementing classes, so a runtime check can be valid. You should not apply a simplistic rule like "no direct `extends` means always invalid."

## 5. Subtype Relationship Comparison Table

Suppose we test with the type pattern `instanceof T name`:

| Static Type S | Pattern Type T | Java 17 | Java 21+ | Explanation |
| --- | --- | --- | --- | --- |
| `String` | `String` | Compile-time error | Valid | Both types are the same; non-`null` values match |
| `String` | `CharSequence` | Compile-time error | Valid | `String` is a subtype of `CharSequence` |
| `String` | `Object` | Compile-time error | Valid | `String` is a subtype of `Object` |
| `Object` | `String` | Valid | Valid | Narrowing type check can succeed or fail |
| `CharSequence` | `String` | Valid | Valid | Not every `CharSequence` is a `String` |
| `Number` | `Integer` | Valid | Valid | Runtime subtype check is meaningful |
| `Integer` | `Number` | Compile-time error | Valid | `Integer` is a subtype of `Number` |
| `String` | `Integer` | Compile-time error | Compile-time error | Two classes are incompatible for pattern type checking |

In this table, we consider ordinary reference type patterns, without complex generics, nested patterns, or preview features for primitives. A pattern must also satisfy other syntax and variable-scoping rules.

**Note:** using `var text = "java";` causes `text` to be inferred as `String`. Therefore, on Java 17, `text instanceof CharSequence chars` still fails just like an explicit `String text` declaration. The `var` keyword does not turn the static type into `Object`.

## 6. The Role of `null` in Type Checks

Subtype relationships are about types, but a **reference variable** can hold the value `null`:

```java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không khớp");
}
```

This snippet is valid in Java 17 and prints:

```text
Không khớp
```

When the operand of `instanceof` is `null`, testing against a reference type pattern such as `String text` returns **`false`** and does not bind the variable `text`.

For Java 21+, even when the static type of the operand is already a subtype of the pattern type (so the pattern is permitted), **`null` still does not make `instanceof` evaluate to `true`**. For example, a `String` holding `null` still does not match `instanceof String text`.

Do not confuse an "unconditional type pattern" in type-compatibility analysis with `instanceof` accepting `null`. In the context of `instanceof`, checking for `null` still affects the result. If the goal is simply to distinguish a `String` reference of known type from `null` on Java 17, write `text != null`.

## 7. Complete, Runnable Java 17 Program

Create the file **`SubtypeRelationDemo.java`**:

```java
public class SubtypeRelationDemo {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(" + text.length() + "): " + text;
        }
        if (value instanceof Integer number) {
            return "Integer next: " + (number + 1);
        }
        return "Other";
    }

    static String describeSequence(CharSequence sequence) {
        if (sequence instanceof String text) {
            return "String chars: " + text.length();
        }
        return sequence == null ? "Sequence null" : "Sequence not String";
    }

    static String handleKnownString(String text) {
        if (text == null) {
            return "Missing";
        }
        return "Upper: " + text.toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(12));
        System.out.println(describe(null));
        System.out.println(describeSequence("hi"));
        System.out.println(describeSequence(new StringBuilder("ab")));
        System.out.println(handleKnownString("ok"));
        System.out.println(handleKnownString(null));
    }
}
```

Compile with Java 17 source level (you can use a newer JDK that supports `--release 17`):

```bash
javac --release 17 SubtypeRelationDemo.java
java SubtypeRelationDemo
```

Exact stdout:

```text
String(4): java
Integer next: 13
Other
String chars: 2
Sequence not String
Upper: OK
Missing
```

**Group-by-group explanation:**

1. `describe(Object)` receives static type `Object`; checking `String` and `Integer` are both valid narrowing checks on Java 17. `12` is autoboxed to `Integer` when passed to the `Object` parameter.
2. `describe(null)` returns `Other` because `null` does not match either reference type pattern in the two conditions.
3. `describeSequence(CharSequence)` receives static type `CharSequence`. A `String` object like `"hi"` matches; a `StringBuilder` does not match `String` even though it also implements `CharSequence`.
4. `handleKnownString(String)` already receives a `String` parameter. Instead of a redundant type pattern that is invalid in Java 17, the method checks `text == null` and then calls `String.toUpperCase()` directly.

The key takeaway is that **the same string object can appear in a valid or invalid pattern expression depending on the static type of the operand and the Java version**. For example, `Object value = "java"` allows pattern narrowing in Java 17, whereas `String value = "java"` does not allow the type pattern `String text` at Java 17 source level.

## 8. Java 21+: Subtype Type Patterns Are Accepted

In Java 21, the pattern applicability rules were adjusted. The following snippet **compiles directly with Java 21**, without enabling preview features:

Create the file **`UnconditionalPatternJava21.java`**:

```java
public class UnconditionalPatternJava21 {
    static String describe(String input) {
        if (input instanceof CharSequence chars) {
            return "Length: " + chars.length();
        }
        return "Null";
    }

    static String sameType(String input) {
        if (input instanceof String text) {
            return "Text: " + text;
        }
        return "Null";
    }

    public static void main(String[] args) {
        System.out.println(describe("abc"));
        System.out.println(describe(null));
        System.out.println(sameType("ok"));
    }
}
```

Run commands:

```bash
javac --release 21 UnconditionalPatternJava21.java
java UnconditionalPatternJava21
```

Exact stdout:

```text
Length: 3
Null
Text: ok
```

In `describe("abc")`, the static type of `input` is `String` and the pattern is `CharSequence chars`: Java 21 allows using a wider-type pattern. With `describe(null)`, `instanceof` returns `false` and the method returns `"Null"`. In `sameType("ok")`, both the pattern and the static type are `String`, yet it is valid in Java 21.

This **differs from the rule in Java 16 through Java 20**, where a static type that is a subtype of the pattern causes an error. If you run `javac --release 17 UnconditionalPatternJava21.java`, the compiler will reject these pattern expressions because of the 17 source level. For the same reason, looking only at **the installed JDK version** while ignoring the `--release` flag or the project's language level can lead to wrong conclusions.

Even though Java 21+ allows it, checking from `String` to `CharSequence` usually adds no new type information. If you are only handling a `String` of known type, an `input != null` condition can still be clearer.

## 9. How to Read Errors and Fix the Root Cause

When you see an error around `instanceof T name`, check in this order:

1. **Identify the language version:** does the project use `--release 17`, `--source 17`, Java 21, or another configuration? For subtype relationships, this is the decisive factor.
2. **Identify the static type S of the operand:** check the variable declaration, method return type, or inferred type from `var`. Do not infer it solely from the object held at runtime.
3. **Identify the pattern type T:** for example `String`, `CharSequence`, `Integer`.
4. **Compare the subtype direction:** if `S <: T`, Java 17 forbids that type pattern, whereas Java 21+ allows it. If `T <: S` and the cast is compatible, this is usually a valid narrowing check.
5. **If the two types cannot be cast compatibly:** the expression may be rejected in every version due to type incompatibility. You need to fix the data type or the condition rather than forcing the compiler to accept a check that can never be true.
6. **Clarify the business requirement:** do you want to check for `null`, check a runtime subtype, or simply access members of an already-known type? Write a condition that accurately reflects the goal.

### Example of Fixing a Subtype Error in Java 17

**Before — compile-time error under Java 17:**

```java
static int lengthOrZero(String text) {
    // Invalid on Java 17:
    // if (text instanceof CharSequence chars) {
    //     return chars.length();
    // }
    return 0;
}
```

This is a commented-out error illustration, not a function that implements the correct logic for all inputs.

**After — matches the intent and is valid on Java 17:**

```java
static int lengthOrZero(String text) {
    return text == null ? 0 : text.length();
}
```

The fixed method returns `0` if the reference is `null`; if non-`null`, it calls `String.length()` directly. There is no redundant type check and no need to create a pattern variable.

### Generic-Related Errors Are a Different Story

For example, `value instanceof java.util.List<String> list` with `value` of type `Object` is invalid on Java 17 because the parameterized type `List<String>` cannot be fully checked at runtime due to **type erasure**. The way to check the list shape is `value instanceof java.util.List<?> list`, and then inspect the elements as required.

A **type erasure** error is different from the **`S <: T`** error discussed in this article. When you see a compile-time error, identify the exact rule being violated instead of assuming every pattern error is caused by a subtype relationship.

## 10. Self-Check

**Question 1:** The project runs on Java 17. Does the following code compile?

```java
CharSequence data = "abc";
if (data instanceof String text) {
    System.out.println(text.length());
}
```

**Answer:** Yes. The static type of `data` is `CharSequence` and the pattern is `String`, so this is a meaningful narrowing check. The output printed is `3`.

**Question 2:** What if we change the declaration to `String data = "abc";` and keep `data instanceof String text`?

**Answer:** On **Java 17**, it does not compile because `String <: String`. Starting in **Java 21**, this type pattern is accepted; when the value is non-`null`, the condition is true.

**Question 3:** Does `Object value = null;` with `value instanceof String text` throw a `NullPointerException`?

**Answer:** No. The expression evaluates to `false`. The branch that uses `text` will not execute, so there is no unbound `text` reference.

**Key takeaway:** subtype relationships are **directional**. In Java 17, when the static type is already a subtype of the pattern type, an `instanceof` type pattern with a variable is rejected; whereas when the operand has a wider type and the pattern checks for a narrower type, that is usually the intended use case. Starting in Java 21, the rule for "already-guaranteed type" patterns is relaxed, but the meaning of `null` and cases where two types are incompatible must still be evaluated separately.

### Language Specification References

- [Java Language Specification 17, §15.20.2 — The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): states the compile-time error rule if the operand type is a subtype of the pattern type.
- [Java Language Specification 21, §15.20.2 — The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): applies pattern compatibility according to the updated rules.
- [Java Language Specification 21, §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): describes pattern applicability for a type.