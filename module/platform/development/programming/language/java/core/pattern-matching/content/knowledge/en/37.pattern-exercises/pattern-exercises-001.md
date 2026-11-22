# Writing Type Patterns Instead of Manual Casts — Java Comprehensive Practice

## 1. Objective of the Practice

In older Java code, checking a type before casting was typically written as two separate operations:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.strip());
}
```

This snippet can be correct, but it repeats the type name `String` in both `instanceof` and the `(String) value` cast. If a large method has many branches or nested objects, repeated check/cast pairs make the code verbose and easy to edit inconsistently.

**Type patterns with `instanceof`** allow writing:

```java
if (value instanceof String text) {
    System.out.println(text.strip());
}
```

In a single expression, Java both **checks the runtime type** and **binds a pattern variable** of the determined type. If the pattern does not match, the `if` body does not execute; there is no direct cast failing on that line.

The article “**Writing Type Patterns Instead of Manual Casts**” belongs to the **Comprehensive Practice** group. You will:

1. Recognize the `instanceof T` → `(T) object` pattern in legacy code.
2. Refactor to `instanceof T variable` without changing the matching or non-matching branches.
3. Use **flow scoping** and guard clauses to eliminate nested casts.
4. Handle `String`, `Integer`, `CharSequence`, `record`, and `List<?>` types.
5. Preserve exact behavior for `null`, invalid data, mismatched runtime types, and branch ordering.
6. Understand where **not** to replace a cast with a pattern: when you intentionally want to throw `ClassCastException`, when performing numeric conversions, or when checking generic type arguments.
7. Run a standalone Java program comparing both approaches across **25 test cases**, then complete the refactoring exercises yourself.

**Version:** Pattern matching for `instanceof` was standardized in **Java 16** via JEP 394. All complete runnable programs in this article use only features stabilized in **Java 17**, without needing `--enable-preview`. Record patterns in `switch` are a Java 21 extension and are covered separately at the end of the article.

## 2. Basic Refactoring Rule: Checking the Type and Binding the Variable Together

### 2.1. Before: Manual Cast After instanceof

```java
static String oldText(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return "text:" + text.strip();
    }
    return "other";
}
```

Execution flow: `input instanceof String` returns true if `input` is a non-null `String` object. Then `(String) input` succeeds because the condition has already verified the type. The second cast can be removed while preserving the intent.

### 2.2. After: Type Pattern

```java
static String newText(Object input) {
    if (input instanceof String text) {
        return "text:" + text.strip();
    }
    return "other";
}
```

In `instanceof String text`:

- `String` is the **pattern type**.
- `text` is the **pattern variable** bound when the pattern matches.
- Inside the true branch, the compiler knows `text` has type `String`, so `strip()` can be called.
- When `input` is `Integer`, `StringBuilder`, or `null`, the pattern does not match and the program returns `"other"`.

If the old code already guarantees a safe cast via `instanceof` on **the exact same value**, refactoring is usually straightforward. However, preserving overall behavior also depends on other expressions, branch order, and null handling.

### 2.3. Not Every Cast Can Be Replaced with a Type Pattern

For example:

```java
String text = (String) raw;
```

This is a **direct** cast. If `raw` is an `Integer`, Java throws `ClassCastException`. If you replace it with:

```java
if (raw instanceof String text) {
    use(text);
}
```

you have changed **“wrong type throws an error”** to **“wrong type is silently skipped”**, which may not be equivalent. If the contract requires rejecting invalid types, write an explicit error branch:

```java
if (!(raw instanceof String text)) {
    throw new IllegalArgumentException("expected a String");
}
use(text);
```

These two snippets with `raw`/`use` are taken from a method context. They illustrate three different policies: direct cast, skipping non-matches, and rejecting with an error message. Choose the policy based on the contract, not just syntax brevity.

## 3. Understanding Match, Non-Match, and Null Before Refactoring

| Value of `Object raw` | `raw instanceof String text` | Branch entered |
| --- | --- | --- |
| `"Java"` | true | String branch, `text="Java"` |
| `""` | true | String branch, even though empty string |
| `7` | false | Non-matching branch |
| `3.5` | false | Non-matching branch |
| `new StringBuilder("abc")` | false | Non-matching branch |
| `null` | false | Non-matching branch |

Two cases are easily confused:

**An empty string is not a non-match.** It still has type `String`, so if business logic requires non-empty content, you must add a check such as `text.isBlank()`.

**`null` does not match a type pattern.** `null instanceof String text` evaluates to false and does not throw `NullPointerException` by itself. However, if the fallback branch calls `raw.getClass()` without handling null, the application can throw an NPE in the **fallback code**, not because of `instanceof`.

The practice code later clearly distinguishes `"missing"` from unsupported type values.

### 3.1. Static Type and Runtime Type

Given:

```java
Object input = 7;
```

The variable `input` has static type `Object`, while the runtime object is `Integer` (due to autoboxing). Therefore `input instanceof Integer number` matches. However, `input instanceof Long number` does not match, even though 7 is a whole number in everyday terms.

Patterns are based on Java's type relationships, not display names, data shapes, or numeric conversion possibilities. Do not treat `Integer` and `Long` as the same type pattern; if you need to accept multiple numeric types, consider `Number` with rules for handling specific values.

## 4. Refactoring a Multi-Type Classification Chain

A common use case is receiving an `Object` and classifying it. Old code:

```java
static String oldLabel(Object value) {
    if (value == null) return "missing";

    if (value instanceof String) {
        String text = (String) value;
        return text.isBlank() ? "blank-text" : "text:" + text.strip();
    }
    if (value instanceof Integer) {
        Integer n = (Integer) value;
        return "integer:" + n;
    }
    if (value instanceof CharSequence) {
        CharSequence chars = (CharSequence) value;
        return "chars:" + chars.length();
    }
    return "unsupported:" + value.getClass().getSimpleName();
}
```

Version using type patterns:

```java
static String newLabel(Object value) {
    if (value == null) return "missing";

    if (value instanceof String text) {
        return text.isBlank() ? "blank-text" : "text:" + text.strip();
    }
    if (value instanceof Integer n) {
        return "integer:" + n;
    }
    if (value instanceof CharSequence chars) {
        return "chars:" + chars.length();
    }
    return "unsupported:" + value.getClass().getSimpleName();
}
```

Improvements made:

- No repetition of `String text = (String) value`, `Integer n = (Integer) value`, and `CharSequence chars = (CharSequence) value`.
- Each branch immediately shows **which type the input matches** and **which variable is used in that branch**.
- No need to declare a broad variable and cast before every method call.
- Preserves branch order, null handling, and fallback so behavior is not accidentally altered.

**Why place `String` before `CharSequence`?** `String` implements `CharSequence`. If you swap the order and the `CharSequence` branch returns immediately, a `String` will enter the broader branch first and will no longer be handled by the `String`-specific rule. Removing casts does not allow reordering branches automatically.

In the full program in section 8, there is also a `Purchase` case to illustrate type patterns with a domain record.

## 5. Flow Scoping: Pattern Variables Live Where the Compiler Knows They Matched

A type pattern is not simply a regular local variable declaration. Java uses **flow scoping**: the variable is only in scope on control-flow paths where the compiler determines the pattern has definitely succeeded.

### 5.1. Inside the True Branch

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Here `text` is in scope inside the `if` branch. After the `if`, if execution can continue even when `input` is not a `String`, you cannot use `text` as if it always existed.

### 5.2. Combining with && to Check Additional Conditions

```java
static String longText(Object value) {
    if (value instanceof CharSequence text && text.length() >= 3) {
        return "long:" + text.length();
    }
    return "short-or-other";
}
```

The `&&` operator evaluates the right-hand side **only when** the left-hand side is true. Thus, when evaluating `text.length()`, the compiler knows the pattern `CharSequence text` has matched and `text` is bound.

Three essential test groups:

- `"Java"` → pattern matches, length condition is true → `long:4`.
- `"ab"` → pattern matches, but guard is false → `short-or-other`.
- `null` or `123` → pattern does not match, right-hand side is not evaluated → `short-or-other`.

Conversely:

```java
// DOES NOT COMPILE: when the left-hand side is false, text is not bound.
if (value instanceof CharSequence text || text.length() >= 3) {
    System.out.println(text);
}
```

With `||`, the right-hand side is evaluated when the left-hand side is false, which is precisely when the pattern variable does **not** have a value. Do not change `&&` to `||` while still using the pattern variable on the right-hand side.

### 5.3. Negated Guard Clauses Reduce Nesting

Old code:

```java
static int oldLength(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return -1;
}
```

New code:

```java
static int newLength(Object input) {
    if (!(input instanceof String text)) return -1;
    return text.length();
}
```

At `return text.length();`, the compiler knows every non-matching path has already exited at `return -1;`. Therefore `text` is in scope after the guard clause. This style keeps the **happy path at the end** without deep `if` nesting.

If you remove `return -1;` and let the negated branch fall through, the compiler no longer has proof that `text` is always bound. Flow scoping is a static check, not a variable-naming trick.

## 6. Refactoring Nested Casts: Envelope Containing Purchase

When data is nested inside a wrapper, manual casting code can be hard to follow. Consider:

```java
record Purchase(String orderId, java.math.BigDecimal amount) {}
record Envelope(Object payload) {}
```

Intent: the input must be an `Envelope`, its `payload` component must be a `Purchase`, and `amount` must be non-null and positive. If valid, return `accepted:<orderId>`. If invalid, return a clear error code.

### 6.1. Old Version

```java
static String oldPurchase(Object input) {
    if (!(input instanceof Envelope)) return "not-envelope";
    Envelope envelope = (Envelope) input;

    if (!(envelope.payload() instanceof Purchase)) return "not-purchase";
    Purchase purchase = (Purchase) envelope.payload();

    java.math.BigDecimal amount = purchase.amount();
    if (amount == null) return "missing-amount";
    if (amount.signum() <= 0) return "nonpositive";

    return "accepted:" + purchase.orderId();
}
```

First it checks `Envelope`, then casts; next it checks `Purchase` and casts again. In this example `Envelope` is a record with a default accessor, so calling `payload()` twice for the same component does not change the object.

### 6.2. Version Using Type Patterns

```java
static String newPurchase(Object input) {
    if (!(input instanceof Envelope envelope)) return "not-envelope";
    if (!(envelope.payload() instanceof Purchase purchase)) return "not-purchase";

    java.math.BigDecimal amount = purchase.amount();
    if (amount == null) return "missing-amount";
    if (amount.signum() <= 0) return "nonpositive";

    return "accepted:" + purchase.orderId();
}
```

With the pattern `Envelope envelope`, the compiler binds the variable after the check. When the guard fails to match, the method exits. Next, the pattern `Purchase purchase` binds the `payload` data; both casts are gone.

**The new code uses type patterns, not record deconstruction.** Java 17 already supports `instanceof Envelope envelope` and `instanceof Purchase purchase`. If upgrading to Java 21, you can use nested record patterns such as `Envelope(Purchase(var orderId, var amount))`, which is a different technique and will be distinguished in section 11.

### 6.3. Be Careful with Null at Multiple Levels

Cases to test:

| Input | `Envelope` match? | `Purchase` match? | Result |
| --- | --- | --- | --- |
| `null` | No | Not evaluated | `not-envelope` |
| `"other"` | No | Not evaluated | `not-envelope` |
| `new Envelope(null)` | Yes | No | `not-purchase` |
| `new Envelope("other")` | Yes | No | `not-purchase` |
| `new Envelope(new Purchase("P2", null))` | Yes | Yes | `missing-amount` |
| `new Envelope(new Purchase("P3", BigDecimal.ZERO))` | Yes | Yes | `nonpositive` |
| `new Envelope(new Purchase("P1", new BigDecimal("2.00")))` | Yes | Yes | `accepted:P1` |

The `Purchase` record can have `amount == null` because the record here has no constructor validation. **The type pattern `Purchase purchase` only proves the object's type, not that its components are valid**. Therefore checking `amount == null` is mandatory if the domain does not allow a missing amount.

### 6.4. Avoid Re-Evaluating Getters with Side Effects When Refactoring

The old code checks and reads `envelope.payload()` twice. With a default record accessor for component `Object payload`, the result is stable. However, if real-world code calls a custom accessor with side effects or data mutated externally, two calls could return different values.

In that case, assign the value to be checked **once**:

```java
Object payload = getPayload();
if (!(payload instanceof Purchase purchase)) {
    return "not-purchase";
}
// Use purchase here.
```

`getPayload()` is a hypothetical application method not present in the standalone file. The goal is not to inadvertently change **how many times** an expression is evaluated during refactoring. In particular, never cast a fresh result from `getPayload()` after checking an earlier result.

## 7. Interfaces/Subtypes and Generics: Where Type Patterns Require Deeper Understanding

### 7.1. StringBuilder Is Not a String, but It Is a CharSequence

`StringBuilder` and `String` both provide characters, but `StringBuilder` **does not extend** `String`. For example:

```java
Object input = new StringBuilder("abcd");

System.out.println(input instanceof String);       // false
System.out.println(input instanceof CharSequence); // true
```

A `input instanceof String text` case will not match. If you want to handle `StringBuilder` as well, you need a broader pattern like `CharSequence chars` or separate cases. In the full program, `String` is handled first, while `CharSequence` comes after to catch `StringBuilder`.

Do not replace a type pattern with `input.getClass() == CharSequence.class`: that compares **exact Class objects**, not implementations/subtypes, so it evaluates to false for `StringBuilder` even though `instanceof CharSequence` is true.

### 7.2. Checking Generic Containers with List<?>

A common pitfall:

```java
// DOES NOT COMPILE in a regular Object raw context:
if (raw instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Type arguments of most generic types are not fully preserved at runtime due to **type erasure**. With `Object raw`, the `List<String>` pattern above is not a valid reifiable type check. A safe refactor uses a wildcard for the container, then checks each element:

```java
static int countNonblankStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) return 0;

    int count = 0;
    for (Object element : items) {
        if (element instanceof String text && !text.isBlank()) {
            count++;
        }
    }
    return count;
}
```

Examples:

- `["a", 5, " ", null, "xyz"]` → two non-blank Strings: `"a"` and `"xyz"`.
- `"abc"` is not a List → 0.
- A List containing only integers still matches `List<?>`, but no element matches `String text`.
- An empty List still matches the container pattern and returns 0.

**Note:** `List<?>` only guarantees the object is an implementation of `List`. It does not guarantee that every element is a `String`. If logic requires the entire list to have a uniform type, validate every element or use data with a trusted schema.

### 7.3. Do Not Confuse Type Patterns with Numeric Conversions

If the input is `Long 7L`, `instanceof Integer i` is false. Pattern matching does not automatically convert a `Long` into an `Integer`. If business logic accepts different numeric types, you can use `Number number` and convert according to policy, but you must check range, overflow, and precision.

For example, `Number.intValue()` can lose information for large numbers or floating-point numbers. Switching from casts to type patterns **does not eliminate** those risks.

## 8. Complete Java 17 Program — Before/After Comparison with 25 Checks

Create a single file **`ManualCastRefactorDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

public class ManualCastRefactorDemo {
    record Purchase(String orderId, BigDecimal amount) {}
    record Envelope(Object payload) {}

    static String oldLabel(Object value) {
        if (value == null) return "missing";
        if (value instanceof String) {
            String text = (String) value;
            return text.isBlank() ? "blank-text" : "text:" + text.strip();
        }
        if (value instanceof Integer) {
            Integer n = (Integer) value;
            return "integer:" + n;
        }
        if (value instanceof Purchase) {
            Purchase purchase = (Purchase) value;
            return "purchase:" + purchase.orderId() + "/" + purchase.amount();
        }
        if (value instanceof CharSequence) {
            CharSequence chars = (CharSequence) value;
            return "chars:" + chars.length();
        }
        return "unsupported:" + value.getClass().getSimpleName();
    }

    static String newLabel(Object value) {
        if (value == null) return "missing";
        if (value instanceof String text) {
            return text.isBlank() ? "blank-text" : "text:" + text.strip();
        }
        if (value instanceof Integer n) return "integer:" + n;
        if (value instanceof Purchase purchase) {
            return "purchase:" + purchase.orderId() + "/" + purchase.amount();
        }
        if (value instanceof CharSequence chars) {
            return "chars:" + chars.length();
        }
        return "unsupported:" + value.getClass().getSimpleName();
    }

    static String oldPurchase(Object input) {
        if (!(input instanceof Envelope)) return "not-envelope";
        Envelope envelope = (Envelope) input;
        if (!(envelope.payload() instanceof Purchase)) return "not-purchase";
        Purchase purchase = (Purchase) envelope.payload();
        BigDecimal amount = purchase.amount();
        if (amount == null) return "missing-amount";
        if (amount.signum() <= 0) return "nonpositive";
        return "accepted:" + purchase.orderId();
    }

    static String newPurchase(Object input) {
        if (!(input instanceof Envelope envelope)) return "not-envelope";
        if (!(envelope.payload() instanceof Purchase purchase)) return "not-purchase";
        BigDecimal amount = purchase.amount();
        if (amount == null) return "missing-amount";
        if (amount.signum() <= 0) return "nonpositive";
        return "accepted:" + purchase.orderId();
    }

    static String oldLength(Object value) {
        if (value instanceof CharSequence) {
            CharSequence text = (CharSequence) value;
            if (text.length() >= 3) return "long:" + text.length();
        }
        return "short-or-other";
    }

    static String newLength(Object value) {
        if (value instanceof CharSequence text && text.length() >= 3) {
            return "long:" + text.length();
        }
        return "short-or-other";
    }

    static int countNonblankStrings(Object value) {
        if (!(value instanceof List<?> items)) return 0;
        int count = 0;
        for (Object element : items) {
            if (element instanceof String text && !text.isBlank()) {
                count++;
            }
        }
        return count;
    }

    static String unsafeCast(Object value) {
        Purchase purchase = (Purchase) value;
        return purchase.orderId();
    }

    static int passed;

    static void compare(String label, String expected, String oldResult, String newResult) {
        if (!expected.equals(oldResult) || !expected.equals(newResult)) {
            throw new AssertionError(
                label + ": expected " + expected
                + ", old=" + oldResult + ", new=" + newResult
            );
        }
        passed++;
        System.out.println("PASS " + label + " => " + newResult);
    }

    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + ": expected " + expected + ", got " + actual
            );
        }
        passed++;
        System.out.println("PASS " + label + " => " + actual);
    }

    static void expectBadCast() {
        try {
            unsafeCast("not-a-purchase");
            throw new AssertionError("unsafe-cast: expected ClassCastException");
        } catch (ClassCastException ex) {
            passed++;
            System.out.println("PASS unsafe-cast => ClassCastException");
        }
    }

    static void labelCase(String name, String expected, Object value) {
        compare(name, expected, oldLabel(value), newLabel(value));
    }

    static void purchaseCase(String name, String expected, Object value) {
        compare(name, expected, oldPurchase(value), newPurchase(value));
    }

    static void lengthCase(String name, String expected, Object value) {
        compare(name, expected, oldLength(value), newLength(value));
    }

    public static void main(String[] args) {
        labelCase("text", "text:java", " java ");
        labelCase("blank", "blank-text", "   ");
        labelCase("integer", "integer:7", 7);
        labelCase("negative", "integer:-3", -3);
        labelCase("purchase", "purchase:P1/12.50",
                new Purchase("P1", new BigDecimal("12.50")));
        labelCase("builder", "chars:4", new StringBuilder("abcd"));
        labelCase("double", "unsupported:Double", 3.5);
        labelCase("boolean", "unsupported:Boolean", true);
        labelCase("object", "unsupported:Object", new Object());
        labelCase("null", "missing", null);

        purchaseCase("nested-valid", "accepted:P1",
                new Envelope(new Purchase("P1", new BigDecimal("2.00"))));
        purchaseCase("nested-null-amount", "missing-amount",
                new Envelope(new Purchase("P2", null)));
        purchaseCase("nested-zero", "nonpositive",
                new Envelope(new Purchase("P3", BigDecimal.ZERO)));
        purchaseCase("nested-negative", "nonpositive",
                new Envelope(new Purchase("P4", new BigDecimal("-1"))));
        purchaseCase("nested-other", "not-purchase", new Envelope("other"));
        purchaseCase("nested-null-payload", "not-purchase", new Envelope(null));
        purchaseCase("nested-null", "not-envelope", null);
        purchaseCase("nested-wrong-type", "not-envelope", "other");

        lengthCase("length-string", "long:4", "Java");
        lengthCase("length-short", "short-or-other", "ab");
        lengthCase("length-builder", "long:3", new StringBuilder("abc"));
        lengthCase("length-null", "short-or-other", null);

        expect("mixed-list", "2",
                Integer.toString(countNonblankStrings(
                        Arrays.asList("a", 5, " ", null, "xyz"))));
        expect("not-list", "0",
                Integer.toString(countNonblankStrings("abc")));
        expectBadCast();

        System.out.println("checks=" + passed);
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac --release 17 ManualCastRefactorDemo.java
java ManualCastRefactorDemo
```

**Exact stdout output:**

```text
PASS text => text:java
PASS blank => blank-text
PASS integer => integer:7
PASS negative => integer:-3
PASS purchase => purchase:P1/12.50
PASS builder => chars:4
PASS double => unsupported:Double
PASS boolean => unsupported:Boolean
PASS object => unsupported:Object
PASS null => missing
PASS nested-valid => accepted:P1
PASS nested-null-amount => missing-amount
PASS nested-zero => nonpositive
PASS nested-negative => nonpositive
PASS nested-other => not-purchase
PASS nested-null-payload => not-purchase
PASS nested-null => not-envelope
PASS nested-wrong-type => not-envelope
PASS length-string => long:4
PASS length-short => short-or-other
PASS length-builder => long:3
PASS length-null => short-or-other
PASS mixed-list => 2
PASS not-list => 0
PASS unsafe-cast => ClassCastException
checks=25
```

**Explanation of test results:**

- Ten `labelCase` checks call **both the old and new versions**, then compare against expected. They test `String`, `Integer`, the `Purchase` record, `CharSequence`, unsupported types, and null.
- Eight `purchaseCase` checks verify that refactoring nested casts does not change error codes for missing `Envelope`, wrong payload type, missing amount, or non-positive amount.
- Four `lengthCase` checks test `&&` for pattern match + true guard, match + false guard, interface subtype, and null.
- Two `countNonblankStrings` checks test container/element patterns when input is a mixed-type list or not a list.
- One `expectBadCast` check verifies that a direct cast on the wrong type throws **ClassCastException**, highlighting the difference between an “unguarded cast” and a “non-matching pattern”.

The `compare` helper throws `AssertionError` if **either `oldResult` or `newResult`** differs from expected. This is stronger than only comparing old against new: if both are wrong in the same way, an `old == new` check is insufficient. The `expect` helper also compares against expected before printing PASS.

The line `checks=25` indicates that **25 specific checks passed**; it does not mean the program covers every possible input or proves the refactor is always right in a real system.

### Why Use BigDecimal for amount?

In this article, `Purchase.amount` is `BigDecimal` to illustrate monetary data and check positivity via `amount.signum()`. This avoids unnecessary `double` comparisons for money. We do not convert currencies, calculate taxes, or round here; the goal is to check **type and condition**.

`BigDecimal.ZERO` has `signum()==0`; `new BigDecimal("-1")` has `signum()==-1`. Both are rejected by `signum() <= 0`. You must check for null before calling `signum()`, otherwise an NPE can occur.

## 9. Hands-On Exercises: Refactor Yourself and Compare Results

### Exercise A — One Type and One Fallback Branch

Old code:

```java
static String greet(Object person) {
    if (person instanceof String) {
        String name = (String) person;
        return "Hello, " + name.strip();
    }
    return "Unknown";
}
```

**Requirement:** Remove the cast while preserving results for `" Lan "`, `7`, and `null`.

**Solution:**

```java
static String greet(Object person) {
    if (person instanceof String name) {
        return "Hello, " + name.strip();
    }
    return "Unknown";
}
```

Results:

- `greet(" Lan ")` → `Hello, Lan`.
- `greet(7)` → `Unknown`.
- `greet(null)` → `Unknown`.

Do not turn the null branch into an exception or drop the fallback when the prompt only asks to refactor the cast.

### Exercise B — Multiple Types with Subtype/Interface Relationships

Old code:

```java
static String format(Object input) {
    if (input instanceof CharSequence) {
        CharSequence value = (CharSequence) input;
        return "chars:" + value.length();
    }
    if (input instanceof Number) {
        Number value = (Number) input;
        return "number:" + value;
    }
    return "unknown";
}
```

**Solution:**

```java
static String format(Object input) {
    if (input instanceof CharSequence value) {
        return "chars:" + value.length();
    }
    if (input instanceof Number number) {
        return "number:" + number;
    }
    return "unknown";
}
```

Test cases:

- `new StringBuilder("abc")` → `chars:3`.
- `"hello"` → `chars:5`.
- `7L` → `number:7`.
- `3.5` → `number:3.5`.
- `null` → `unknown`.

A common refactoring mistake is changing `CharSequence` to `String` because the code appears to work with text. That causes `StringBuilder` to stop matching and changes behavior.

### Exercise C — Nested Casts Through a Wrapper

Old code:

```java
record Container(Object item) {}
record Customer(String name) {}

static String customerName(Object input) {
    if (!(input instanceof Container)) return "bad-container";
    Container container = (Container) input;
    if (!(container.item() instanceof Customer)) return "bad-customer";
    Customer customer = (Customer) container.item();
    return customer.name();
}
```

**Java 17–compatible solution:**

```java
static String customerName(Object input) {
    if (!(input instanceof Container container)) return "bad-container";
    if (!(container.item() instanceof Customer customer)) return "bad-customer";
    return customer.name();
}
```

Tests should include a valid `Container`, `Container(null)`, `Container(String)`, and `null` input. If `Customer` has `name == null`, the method still returns `null`; if business logic does not allow that, add separate validation—**do not assume the type pattern checked the name**.

### Exercise D — Guard with a Threshold Condition

Given `Object value`, return a processed code only when `value` is a `String` of at least 4 characters; otherwise return `"skip"`. Write this using a single `if` with `&&`:

```java
static String process(Object value) {
    if (value instanceof String text && text.length() >= 4) {
        return "use:" + text;
    }
    return "skip";
}
```

Minimum tests:

- `"abcd"` → `use:abcd` (at threshold).
- `"abc"` → `skip` (below threshold).
- `1234` → `skip` (wrong type).
- `null` → `skip` (pattern is false).

Do not omit the wrong-type case: it proves the right-hand side using `text.length()` is not evaluated when the pattern does not match.

## 10. Common Type Pattern Refactoring Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Removing `instanceof` and keeping a direct cast | Wrong-type input can throw `ClassCastException`. | Only use a direct cast when the contract requires failing fast; if there is a non-match path, use a type pattern and handle it explicitly. |
| Reordering cases during refactoring | A narrower type may be intercepted by a broader type first. | Keep the original order or change it intentionally with tests. |
| Replacing `CharSequence` with `String` | `StringBuilder` will no longer match. | Preserve the pattern type; test different implementations of the interface. |
| Not testing `null` | Fallback branches can dereference `null`. | Keep null handling aligned with the contract and test it separately. |
| Using a pattern variable outside flow scope | The compiler does not guarantee the variable is bound. | Use it inside the true branch or after a negated guard clause with an early return. |
| Using `||` when the right side needs the pattern variable | The variable is not definitely bound when the left side is false. | Use `&&` or split the condition with correct logic. |
| Assuming `instanceof Purchase p` checks `amount > 0` | A type pattern only checks the object's type. | Check null, components, and invariants separately. |
| Changing a non-match branch to throw without thinking | Can change the API from a fallback to an exception. | Compare before/after behavior with expected assertions. |
| Re-casting a value from a second getter call | The getter might mutate or have side effects. | Read the value once and match against that same value. |
| Using `List<String>` for a runtime `Object` | Generic type arguments are erased; the pattern is invalid in normal cases. | Use `List<?>`, then check individual elements. |
| Trying to write `String s instanceof String text` | Java may reject a pattern type that makes no sense when the static type is already a subtype. | Only use patterns when a runtime check is needed; use `String` directly if the type is already known. |
| Confusing type patterns with record patterns | `instanceof Purchase(var id, var amount)` is not standard in Java 17. | In Java 17 use `Purchase p` + accessors; record deconstruction arrives in Java 21. |
| Only checking `old.equals(new)` | Both old and new could be wrong in the same way. | Compare against independent expected values and add error/boundary cases. |
| Cramming everything into one complex `if` | Hard to read even with fewer casts. | Use guard clauses, small methods, and meaningful variable names. |

## 11. Java 21: When to Move from Type Patterns to Record Patterns or Switch?

The main article uses **Java 17** because the goal is removing manual casts without requiring Java 21 syntax. However, if your project has upgraded to Java 21, you have additional options.

### 11.1. Type Patterns and Record Patterns Are Not the Same

Given `record Purchase(String orderId, BigDecimal amount)`:

```java
// Type pattern: stable since Java 16.
if (raw instanceof Purchase purchase) {
    return purchase.orderId();
}
```

```java
// Record pattern: finalized in Java 21.
if (raw instanceof Purchase(var orderId, var amount)) {
    return orderId;
}
```

A type pattern binds **the whole object**; a record pattern binds **the components**. Choose a record pattern when you need to deconstruct a structure clearly, especially with nested records; do not switch to the new pattern just to save a single accessor call if it makes the code harder to read.

### 11.2. Switch Expressions for Multiple Branches on the Same Selector

From Java 21 onward:

```java
// Java 21 snippet; place inside a method taking Object value.
return switch (value) {
    case null -> "missing";
    case String text when text.isBlank() -> "blank-text";
    case String text -> "text:" + text.strip();
    case Integer number -> "integer:" + number;
    default -> "unsupported";
};
```

`switch` can be clearer than an `if` chain when multiple cases classify **a single selector**, though it is not always better. For a single early check followed by business logic, `if (value instanceof T t)` or a guard clause is often simpler.

**Note:** `case String text when text.isBlank()` must come before the unguarded `case String text`, otherwise the specific case is shadowed by the broader branch (*domination*). `case null` expresses an explicit null policy; do not assume `default` handles `null` automatically.

### 11.3. Preserving Source Level Compatibility

If a project sets `javac --release 17`, you cannot use finalized Java 21 record patterns or pattern matching for `switch` in Java 17 source code. The `instanceof T variable` type pattern code in this article remains valid and improves readability without forcing a version upgrade.

## 12. Refactoring Workflow on Real Projects

A reliable workflow:

1. **Find check/cast pairs**: `if (x instanceof T) { T t = (T)x; ... }` and negated variants.
2. **Verify the same expression**: if old code checks one getter call and casts the result of another call, inspect whether repeated evaluation matters. You may need to store it in a variable first.
3. **Document the current contract**: what does the matching branch do? Does a non-match return a value, fall through to another branch, or throw an exception? How is `null` handled?
4. **Replace with a type pattern**: `x instanceof T t`, remove the redundant cast, and use `t` within its valid scope.
5. **Preserve type order and specificity**: keep `String` before `CharSequence` if you want a dedicated branch; `Integer` does not automatically substitute for `Number`.
6. **Place other validations explicitly**: checking null components, blank strings, negative numbers, state, or permissions is not the job of a type pattern.
7. **Keep error messages and exceptions per contract**: avoid silently turning `ClassCastException` into a no-op, or a fallback into a throw.
8. **Run unit tests before/after** with independent expected values for match, non-match, null, subtypes, boundary values, and nested cases.
9. **Compile at the right version**: type patterns for `instanceof` are finalized from Java 16; check your JDK and `--release` in IDE/CI.
10. **Review readability**: if many type patterns create a giant method, extract helper methods instead of assuming removing casts is enough.

### When Is a Type Pattern Unnecessary?

If a variable already has the exact type at compile time, just use it directly:

```java
static int size(String value) {
    return value.length();
}
```

There is no need to ask `value instanceof String text`. If the object can be null, handle null according to the contract: a type pattern is not a mandatory way to null-check. For Java types that do not need a cast or pattern, do not add extra syntax just to “modernize”.

## 13. Summary

**Type patterns for `instanceof` effectively replace the “check type then manually cast” idiom.** The syntax `if (value instanceof T variable)` combines both operations, reducing type repetition, eliminating redundant casts, and clarifying the scope of the checked variable.

Real value comes from **preserving behavior** during the conversion:

- `null` and non-matching types must still take the right branches.
- Subtypes/interfaces and check ordering must be preserved.
- Business conditions after matching a type still require separate checks.
- Flow scoping with `&&` and guard clauses must be provably valid to the compiler.
- Direct casts may intentionally throw errors; patterns only check types and do not automatically alter exception contracts.
- Java 17 code can use type patterns without needing Java 21 record deconstruction or pattern `switch`.

Treat the 25-check program in section 8 as a **regression exercise**: run it to see both styles produce the same expected results on the selected cases, then apply the same technique to real code and expand your test matrix to match your domain.

**References:**

- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [Java SE 17 Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
