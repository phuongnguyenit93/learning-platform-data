# Why Observing `==` on Literals Does Not Replace `String` Content Comparison

When trying Java, many people see:

```java
String a = "Java";
String b = "Java";
System.out.println(a == b); // true
```

And then conclude that `==` can be used to check whether two strings have the same text. **That is the wrong conclusion.** The `true` result here comes from the *string pool* mechanism: two literals with the same content reference the same `String` object. The `==` operator still compares only **object identity**, not each character individually.

When you need to check whether two text values are the same, use `String.equals(...)` (or a value comparison matching the business requirement). This lesson explains why small experiments on literals easily mislead and how to write correct code for strings coming from real inputs.

## 1. Three Different Things: Variable, Object, and Content

Consider the code:

```java
String first = "core";
String second = first;
String third = new String("core");
```

- **Reference variables** `first`, `second`, and `third` store reference values pointing to `String` objects.
- **A `String` object** has its own identity in memory; two variables can point to the same object.
- **String content** is the sequence of characters, which is `"core"` in all three here.

Reference model:

```text
first  ──┐
         ├──────────> String "core" (object from pool)
second ──┘

third ──────────────> String "core" (object created by new)
```

When comparing two reference-type variables:

- `first == second` asks: "Do both variables point to **the same object**?" → `true`.
- `first == third` asks the same question → `false`.
- `first.equals(third)` asks: "Do both `String` objects have **the same content**?" → `true`.

Even when strings have the same characters, identity and value are not the same concept. Using `==` to check content only happens to yield the expected result when both sides already reference the same object.

## 2. Why Can Two Identical Literals Give `== true`?

Java stores string literals in an *interned* form in the **string pool**. According to Java semantics, literals with the same content (and constant string expressions with the same content) reference the canonical `String` object in the pool.

```java
String a = "Java";
String b = "Java";
System.out.println(a == b); // true
```

This is an intentional feature of the language and how literals are organized. It enables object reuse for identical constant values. However, this **does not turn `==` into a content comparison operator**. When two references point to different objects, `==` still returns `false` even if their characters match.

You can picture the common flawed reasoning like this:

> "Two literals with the same text return `true` with `==`, so all strings with the same text will also return `true`."

The faulty step is equating "same content" with "always the same reference." The pool explains **why the special case of literals can share identity**; it makes no guarantee for arbitrary strings produced at runtime.

### Example 1: literal and a copy with the same content

Create the file `LiteralIdentityDemo.java`:

```java
public class LiteralIdentityDemo {
    public static void main(String[] args) {
        String a = "Java";
        String b = "Java";
        String copied = new String("Java");

        System.out.println(a == b);
        System.out.println(a == copied);
        System.out.println(a.equals(copied));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LiteralIdentityDemo.java
java LiteralIdentityDemo
```

Exact output:

```text
true
false
true
```

The first line is true because the literal `"Java"` is shared through the pool. The second line is false because `new String("Java")` creates a **new object** with a different identity. The last line is true because `equals` compares the content of the two `String` objects.

All three comparisons are doing their exact job. The mistake is choosing `==` when the problem actually calls for text comparison.

## 3. Compile-Time Constant Strings Can Also Share Pooled Objects

It is not only literals written as a single token that can receive the same reference. **String constant expressions** evaluated at compile time can also become the same literal/interned value.

Example:

```java
String a = "Java";
String b = "Ja" + "va";
System.out.println(a == b); // true
```

`"Ja" + "va"` is a constant expression, evaluated at compile time to `"Java"`. Therefore `b` receives a reference to the same interned string.

Similarly, a `final String` **constant variable** initialized with a constant expression can participate in a constant expression:

```java
final String prefix = "Ja";
String c = prefix + "va";
System.out.println(c == "Java"); // true
```

Point to remember: **`final` does not automatically make every concatenation a constant expression**. The initializer and expression form must satisfy the language's *constant expression* definition. For example, if a `final` variable receives its value from a method at runtime, concatenating with it is not a constant expression merely because it has `final`.

### Example 2: checking literals and constant concatenation

Create the file `ConstantExpressionDemo.java`:

```java
public class ConstantExpressionDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        final String compileTimePrefix = "Ja";
        String foldedWithFinal = compileTimePrefix + "va";

        String runtimePrefix = new String("Ja");
        String constructedAtRuntime = runtimePrefix + "va";

        System.out.println(literal == folded);
        System.out.println(literal == foldedWithFinal);
        System.out.println(literal.equals(constructedAtRuntime));
        System.out.println(literal == constructedAtRuntime);
    }
}
```

```bash
javac ConstantExpressionDemo.java
java ConstantExpressionDemo
```

Output with Java 17+:

```text
true
true
true
false
```

The first two `true` outputs do not prove that `==` compares text: they only reflect **constant** concatenations receiving the pooled object. Because `runtimePrefix` is an object created at runtime, the concatenation produces a new `"Java"` value; `equals` confirms the content matches, while `==` shows it does not share identity with the literal in this example.

In real applications, strings received from the network, keyboard, files, databases, and runtime processing must not be assumed to share identity with a literal even when their content matches.

## 4. External Strings Can Equal a Literal While `==` Is Still `false`

An example very close to reading external data is constructing a string from a character array:

```java
char[] incoming = {'o', 'k'};
String fromInput = new String(incoming);

System.out.println(fromInput == "ok");       // false
System.out.println(fromInput.equals("ok"));   // true
```

`fromInput` and the literal `"ok"` have the same content. However, the `String(char[])` constructor creates a `String` object from the input data, so its reference differs from the pooled literal reference. If code branches on `if (fromInput == "ok")`, that branch will **not execute** even though the user entered the exact expected text.

### Example 3: one buggy branch and one correct branch

Create the file `StringDecisionDemo.java`:

```java
public class StringDecisionDemo {
    public static void main(String[] args) {
        String expected = "READY";
        String received = new String(
                new char[] {'R', 'E', 'A', 'D', 'Y'}
        );

        if (received == expected) {
            System.out.println("Identity matched");
        } else {
            System.out.println("Identity did not match");
        }

        if (expected.equals(received)) {
            System.out.println("Content matched");
        } else {
            System.out.println("Content did not match");
        }
    }
}
```

```bash
javac StringDecisionDemo.java
java StringDecisionDemo
```

Output:

```text
Identity did not match
Content matched
```

Merely changing **how the object was created** while keeping the exact same content caused `==` to flip from `true` to `false`. That is precisely why you should not use a test on two literals to validate a program's content-comparison logic.

## 5. What Does `String.intern()` Change, and What Does It Not Change?

`String.intern()` returns a **canonical reference** to a string with the same content in the string pool. If the corresponding string is already in the pool, it returns the pooled reference. If not, the pool ensures a corresponding canonical object exists and returns that reference.

Example:

```java
String literal = "topic";
String dynamic = new String("topic");
String canonical = dynamic.intern();

System.out.println(literal == dynamic);   // false
System.out.println(literal == canonical); // true
System.out.println(dynamic == canonical); // false
```

Key points:

1. `dynamic` was created separately via `new`, so it has a different identity from `literal`.
2. `dynamic.intern()` returns the canonical reference for the content `"topic"`; the literal `"topic"` is already present in the example.
3. Calling `intern()` **does not reassign the `dynamic` variable** and does not transform the object `dynamic` references into the literal object.

### Example 4: clearly checking before and after `intern()`

Create the file `InternDemo.java`:

```java
public class InternDemo {
    public static void main(String[] args) {
        String literal = "topic";
        String dynamic = new String("topic");
        String canonical = dynamic.intern();

        System.out.println(literal == dynamic);
        System.out.println(literal == canonical);
        System.out.println(dynamic == canonical);
        System.out.println(literal.equals(dynamic));
    }
}
```

```bash
javac InternDemo.java
java InternDemo
```

Output:

```text
false
true
false
true
```

`intern()` can serve designs that intentionally require reference canonicalization. However, there is no need (and usually it is counterproductive) to call `intern()` just so you can use `==` instead of `equals`. Manually managing canonicalization couples code to an object-sharing strategy and can consume resources that content comparison does not need.

A good rule of thumb: **pool/intern explains where references come from; `equals` solves the need for content comparison.**

## 6. How Should Content Comparisons Be Written?

For two non-`null` `String` values:

```java
String expected = "Java";
String actual = new String("Java");

boolean sameContent = expected.equals(actual); // true
```

`String.equals(Object other)` returns `true` when the argument is a `String` with the same character sequence. It does not require the same object or the same creation source.

Regarding call direction and `null`:

- If you know for sure `a != null`, use `a.equals(b)`.
- If there is an expected constant, use `"READY".equals(received)`: it safely returns `false` when `received == null`.
- If **both sides can be null**, use `Objects.equals(a, b)` (import `java.util.Objects`); two `null` values return `true`.
- To check whether a reference **is null or not**, use `value == null` or `value != null`. That is reference comparison used for its intended purpose.
- Use `equalsIgnoreCase` only when business requirements genuinely call for ignoring case differences; it is not the default choice for all text.

### Example 5: safe comparison when `null` is possible

Create the file `NullSafeComparisonDemo.java`:

```java
import java.util.Objects;

public class NullSafeComparisonDemo {
    public static void main(String[] args) {
        String received = null;

        System.out.println("READY".equals(received));
        System.out.println(Objects.equals("READY", received));
        System.out.println(Objects.equals(null, received));

        received = new String("READY");
        System.out.println("READY".equals(received));
        System.out.println("READY" == received);
    }
}
```

```bash
javac NullSafeComparisonDemo.java
java NullSafeComparisonDemo
```

Output:

```text
false
false
true
true
false
```

If you wrote `received.equals("READY")` when `received == null`, the program would throw `NullPointerException`. Do not "fix" this by writing `received == "READY"`: reference comparison merely hides the null bug in a small example and then causes logic errors when valid data arrives from elsewhere.

## 7. Quick Comparison: Which Results Are Guaranteed?

| Two compared expressions | `==` | `equals` | Explanation |
| --- | --- | --- | --- |
| `"x"` and `"x"` | `true` | `true` | Two literals with the same interned value |
| `"x"` and `"x" + ""` | `true` | `true` | All-constant concatenation evaluated at compile time |
| `a` and `b` after `String b = a` | `true` | `true` when `a` is a non-null `String` | Same reference; if null, do not call `a.equals(...)` |
| `"x"` and `new String("x")` | `false` | `true` | `new` creates a different `String` object |
| `"x"` and `new String("x").intern()` | `true` | `true` | `intern()` returns the pooled reference |
| `"x"` and `new String("y")` | `false` | `false` | Different objects and different content |

This table uses expressions with well-defined conditions. For an arbitrary `String` obtained from an external system, **you cannot predict the result of `==` merely from the displayed text**. Do not treat `== true` as meaning "equal content" under a value-comparison API contract, even though having the same reference naturally implies having the same content at that moment.

## 8. Two Bugs That Easily Slip Past Testing

### Bug A — testing only with literals

```java
static boolean isAdmin(String role) {
    return role == "ADMIN"; // Wrong intent if checking content.
}
```

If you test `isAdmin("ADMIN")`, the result is usually `true`, which can trick you into thinking the method is right. But when a data source creates a new object with the same content, such as `isAdmin(new String("ADMIN"))`, the result is `false`.

Fix to:

```java
static boolean isAdmin(String role) {
    return "ADMIN".equals(role);
}
```

This is an illustrative method snippet that can be placed inside a Java class; it is not a standalone program because it lacks `main`. The new comparison returns `true` for any `String` with exact content `"ADMIN"` regardless of how the object was created. When `role == null`, it returns `false`.

### Bug B — using `intern()` to justify `==`

An unnecessarily awkward fix is:

```java
String received = new String("READY");
if (received.intern() == "READY") {
    // ...
}
```

This works for the specific example, but makes the logic depend on the pool and forces readers to reason about canonicalization strategy. The more direct and meaningful approach is:

```java
String received = new String("READY");
if ("READY".equals(received)) {
    // ...
}
```

Value-comparison methods express intent far better than altering reference management just to make `==` work.

## 9. When Does `==` on `String` Still Make Sense?

`==` is not a "forbidden" operator on `String`. It is right when what you want to check **is genuinely identity**, such as:

- `value == null` to check for the absence of a reference.
- `a == b` in internal code intentionally determining whether two variables hold the same object, for instance when studying the pool or verifying an optimization; this result tells you about *object identity*, and does not replace content checks.
- Logic with a genuine custom contract based on identity (a rare case that must be documented clearly).

If the business question is "is the status code equal to `READY`?", "are the usernames the same?", or "are the text values from two sources equal?", then the answer requires **content** comparison. Do not replace a business contract with assumptions about pooling.

Also remember: because `String` is immutable, two variables sharing a pooled object does not mean modifying one variable's string affects the other. Reassigning a variable or creating a new string value does not alter the old `String` object's content.

## 10. Self-Check

### Question 1 — true or false values?

```java
String x = "cat";
String y = "cat";
String z = new String("cat");

System.out.println(x == y);
System.out.println(y == z);
System.out.println(x.equals(z));
```

Answer:

```text
true
false
true
```

`x` and `y` share the literal reference. `z` is a separate object with the same content.

### Question 2 — the real reason for `true`?

```java
String text = "abcdef";
String built = "abc" + "def";
System.out.println(text == built);
```

The answer is `true` because concatenating all literals is a constant expression evaluated at compile time. This does **not** mean the `==` operator compares character by character.

### Question 3 — testing data arriving at runtime

```java
String expected = "abc";
String actual = new String(new char[] {'a', 'b', 'c'});

System.out.println(expected == actual);
System.out.println(expected.equals(actual));
```

Answer:

```text
false
true
```

A runtime string does not share identity with a literal even when the content is equal.

### Question 4 — choosing the comparison

Suppose `String token` may be `null` and you want to know whether the token is exactly `"OK"`. Should you choose `token == "OK"`, `token.equals("OK")`, or `"OK".equals(token)`?

**Answer:** `"OK".equals(token)`. It returns `true` when the content matches, and `false` if `token` differs or is `null`. `token.equals("OK")` risks throwing `NullPointerException`; `token == "OK"` checks identity with the wrong intent.

## Conclusion

**`==` on `String` compares references; `equals` compares content.** Two identical literals, or two constant expressions with the same result, can share a reference via the string pool so `==` returns `true`. That is an accurate observation about **literal identity**, but **not** a guarantee that all strings with the same text created at runtime will share a reference. For real text data, write comparisons according to value semantics from the start, using `equals` and handling `null` explicitly.