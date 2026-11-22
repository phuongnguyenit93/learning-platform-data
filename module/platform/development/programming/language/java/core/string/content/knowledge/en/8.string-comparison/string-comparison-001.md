# `==` Compares References, Whereas `equals()` Compares `String` Content

In Java, two `String` variables can hold **identical** character sequences while still referencing **two different objects**. Therefore, the expressions `a == b` and `a.equals(b)` answer two different questions:

- **`a == b`**: do the two reference variables point to the **same object**?
- **`a.equals(b)`**: according to the `String` class contract, do the two objects contain the **same sequence of UTF-16 characters**?

When checking names, codes, statuses, user input, or strings read from an API, **almost always use `equals()` for content comparison**. Use `==` when you truly want to know whether two references share the same object, or when comparing a reference to `null`.

## 1. Distinguishing "Same Object" from "Same Value"

The following code demonstrates this directly:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

The two `new String("Java")` calls create two separate `String` objects, even though both objects contain `"Java"`.

Visualize it like this:

```text
Variable a ───────► String object #1: "Java"
Variable b ───────► String object #2: "Java"

a == b       → false  (two different objects)
a.equals(b)  → true   (same content)
```

Conversely, if you assign the reference:

```java
String a = new String("Java");
String b = a;

System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Here `a` and `b` point to the same object. Therefore `==` returns `true`, and naturally the content is also equal.

| Scenario | `a == b` | `a.equals(b)` when `a != null` |
| --- | --- | --- |
| Both variables point to the same `String` | `true` | `true` |
| Two different `String` objects with the same content | `false` | `true` |
| Two `String` objects with different content | `false` | `false` |
| `a` is non-`null`, `b == null` | `false` | `false` |
| Both `a` and `b` are `null` | `true` | **Throws `NullPointerException`** if calling `a.equals(b)` |

Note: for primitive types such as `int` or `boolean`, `==` compares **primitive values**. This article covers two operands of **`String` reference** type: in that case, `==` compares object identity, not character-by-character content.

## 2. How Does Java Define `String.equals()`?

`String` overrides the `equals(Object)` method inherited from `Object`. It returns `true` only when the argument is a `String` that contains the **exact same sequence of UTF-16 code units** as the receiving object. This has several consequences:

1. **Case-sensitive**: `"Java".equals("java")` is `false`.
2. **Includes whitespace**: `"Java".equals("Java ")` is `false`.
3. **Includes newlines and control characters**: `"A\n".equals("A")` is `false`.
4. **Distinguishes Unicode characters represented by different code sequences**: for example, `"\u00E9"` (precomposed é) and `"e\u0301"` (e with a combining acute accent) may render identically, yet `equals()` returns `false`.
5. **Does not auto-normalize, auto-`trim()`, or ignore case**. If your problem requires different rules, the program must define and apply those rules before comparing.

For two `String` instances with genuinely identical content, `equals()` always returns `true`, regardless of whether they reside in different objects or were created in different ways. This is the right comparison for **text value**.

`String.equals()` accepts a parameter of type `Object`. When the argument is not a `String` object (including `null`), the result is `false`:

```java
"Java".equals(null)               // false
"Java".equals(new Object())       // false
"Java".equals(new String("Java")) // true
```

The expressions above are illustrative examples inside a method, not a complete program.

**Do not mechanically apply this rule to every Java class.** The default `Object.equals()` method uses identity comparison; many other classes define `equals()` with their own contracts. `StringBuilder`, for example, does not override `Object.equals()` to compare content like `String`. The topic here is the **specific contract of `String.equals()`**.

## 3. Why Does Comparing Two String Literals with `==` Sometimes Return `true`?

Java has a **String Pool** mechanism: string literals with the same content share a single interned `String` reference. Therefore:

```java
String a = "Java";
String b = "Java";

System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

The `true` result from `==` here is a consequence of **two variables referencing the same object in the pool**. It does **not** mean `==` has turned into a content comparison.

Meanwhile:

```java
String a = "Java";
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

Calling `new String("Java")` creates a separate object, despite having the same value. Thus, relying on `==` to evaluate text data can introduce bugs that only surface when the source or construction of the string changes.

### Compile-Time Constant Concatenation vs. Runtime Concatenation

A concatenation expression where **all components are compile-time constants** can be precomputed and become an interned string literal:

```java
String a = "Java";
String folded = "Ja" + "va";

System.out.println(a == folded); // true
```

In other cases, the value is built at runtime:

```java
String prefix = "Ja";
String runtime = prefix + "va";

System.out.println(a.equals(runtime)); // true
```

You should not use `a == runtime` to check content, regardless of what a specific code version or JDK happens to print. For **concatenation that is not a compile-time constant**, language rules create the resulting string at runtime; and a small change in how it is initialized can break an earlier `==` check.

Note on the `final` keyword: a `final String` variable initialized with a **constant expression** can be a *constant variable*, so using it in a concatenation expression can also make the entire concatenation a compile-time constant. Do not assume that the mere presence of a variable name in a concatenation guarantees runtime evaluation.

## 4. Complete Java 17+ Example: `==`, `equals()`, Literals, and `intern()`

Save the following code to `StringEqualityDemo.java`:

```java
public class StringEqualityDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String sameLiteral = "Java";
        String allocated = new String("Java");
        String runtime = new StringBuilder("Ja")
                .append("va").toString();
        String folded = "Ja" + "va";
        String pooled = allocated.intern();

        System.out.println(
                "literal == sameLiteral: " + (literal == sameLiteral));
        System.out.println(
                "literal == allocated: " + (literal == allocated));
        System.out.println(
                "literal.equals(allocated): " + literal.equals(allocated));
        System.out.println(
                "literal == runtime: " + (literal == runtime));
        System.out.println(
                "literal.equals(runtime): " + literal.equals(runtime));
        System.out.println(
                "literal == folded: " + (literal == folded));
        System.out.println(
                "literal == pooled: " + (literal == pooled));
        System.out.println(
                "literal.equals(java): " + literal.equals("java"));
        System.out.println(
                "literal.equals(null): " + literal.equals(null));
    }
}
```

Compile and run:

```bash
javac StringEqualityDemo.java
java StringEqualityDemo
```

Output:

```text
literal == sameLiteral: true
literal == allocated: false
literal.equals(allocated): true
literal == runtime: false
literal.equals(runtime): true
literal == folded: true
literal == pooled: true
literal.equals(java): false
literal.equals(null): false
```

**Explanation of each group of results:**

- `literal` and `sameLiteral` are the same literal, so they reference the same interned object.
- `allocated` is a new `String`. Therefore `literal == allocated` returns `false`, while `literal.equals(allocated)` is still `true`.
- `runtime` is created via `StringBuilder.toString()`; it carries the same character sequence but is an independent string object in the example.
- `folded` is a compile-time concatenation of two literals, so it shares the pool reference with `"Java"`.
- `allocated.intern()` returns the canonical reference in the pool for the string with the same content, so `literal == pooled` is `true`.
- `equals()` compares the **exact** character sequence; `"Java"` and `"java"` differ in case, and a `null` argument is simply not a string with equal content.

`intern()` is a real API that exists, but it is **unnecessary** for checking content. Do not call `intern()` everywhere just to make `==` produce the desired result: using `equals()` is both simpler and clearly expresses the true intent of the condition.

## 5. Handling `null` in Content Comparisons

`equals()` is an instance method: if `input == null`, then `input.equals("OK")` throws `NullPointerException`. Conversely, `"OK".equals(input)` returns `false` when the input is missing, because the receiving literal is always non-`null`.

```java
String input = null;
System.out.println("OK".equals(input)); // false
System.out.println(input != null && input.equals("OK")); // false
System.out.println(java.util.Objects.equals(input, "OK")); // false
System.out.println(java.util.Objects.equals(null, null)); // true
```

Put the literal on the left when comparing against a constant, use `&&` to check the receiver before calling, or choose `Objects.equals(a, b)` when both can be `null` **and** requirements dictate treating two absent values as equal. These approaches handle nullable data; they do not turn `==` into a content comparison.

Dedicated articles on `String.equals(null)` and `Objects.equals` examine non-`String` arguments, null-safe contracts, and business cases in greater depth.



## 6. Why Can `==` Cause "Works on My Machine" Bugs?

Suppose an application checks a status:

```java
String status = new String("READY");

if (status == "READY") {
    System.out.println("Accepted");
} else {
    System.out.println("Rejected");
}
```

The output is `Rejected`, even though `status` contains the exact text `"READY"`. Reason: `new String("READY")` creates a different object from the literal `"READY"`, so `==` is `false`.

Change it to:

```java
if ("READY".equals(status)) {
    System.out.println("Accepted");
} else {
    System.out.println("Rejected");
}
```

The output is `Accepted`. The condition now checks **content**, matching the business goal.

Bugs of this kind easily slip past superficial tests if tested with hardcoded string literals, where two references happen to be shared from the String Pool. When data arrives from an API, file, user input, or runtime-concatenated strings, behavior based on object identity no longer holds. Therefore, avoid relying on the String Pool when writing content conditions.

## 7. Relationship to Immutability and `hashCode()`

`String` is **immutable**: the content of a `String` object cannot be changed after creation using standard APIs.

```java
String a = "Java";
String b = a;

a = a.concat(" 17");

System.out.println(a);           // Java 17
System.out.println(b);           // Java
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false
```

Reassigning `a` does not modify the old `String` object that `b` still holds. Thus, both comparisons after the concatenation in the example return `false`, but **for two different reasons**: different references and different content.

If two `String` objects are equal according to `equals()`, their `hashCode()` values must be equal. The converse is false when two strings with different content happen to have colliding hash codes. A separate article on `equals` and `hashCode` explains how `HashMap`/`HashSet` handle these cases.

## 8. Comparing Common String Comparison Approaches

| Method / Operator | Checks | When to Use |
| --- | --- | --- |
| `a == b` | Whether two references point to the same object (or are both `null`) | When object identity is genuinely the goal; checking for `null`. |
| `a.equals(b)` | Whether two strings have the same sequence of UTF-16 code units | Exact content comparison when `a` is guaranteed non-`null`. |
| `"X".equals(a)` | Whether the content of `a` equals `"X"` | Comparing against a literal constant, safe when `a` is `null`. |
| `Objects.equals(a, b)` | Equality via `equals`, handling `null` | When one or both references may be `null`. |
| `a.equalsIgnoreCase(b)` | Comparison ignoring certain case differences per the `String` contract | Only when requirements allow ignoring case differences. |
| `a.compareTo(b)` | Lexicographical ordering based on UTF-16 code units | When sorting/ordering is needed; returns negative, 0, or positive. |
| `a.contentEquals(charSequence)` | Content comparison against a `CharSequence` | When the other object is a type like `StringBuilder` and character comparison is required. |

`compareTo() == 0` for two `String` objects is equivalent to `equals()` for content; `compareTo()` is not meant to answer whether two variables share the same reference. Note also that Unicode/locale-based sorting may require `Collator` or custom algorithms if the application wants natural language ordering rather than UTF-16 order.

## 9. Common Mistakes and How to Avoid Them

1. **Using `==` to check text data**: `if (input == "yes")` can fail due to different object identities. Use `"yes".equals(input)` to check content.
2. **Believing `==` is always false for two strings**: also untrue; two literals with the same content may reference the same pooled object, or two variables may point to the same object. The issue lies in the meaning of the check.
3. **Assuming `equals()` never throws an exception**: calling it on a `null` reference causes `NullPointerException`. Put the literal on the left or use `Objects.equals()` when needed.
4. **Assuming `Objects.equals(null, null)` returns `false`**: the result is `true`; two `null` references are considered equal by this helper.
5. **Abusing `intern()` to "fix" comparisons**: interning is unnecessary for accurate content comparison. Use `equals()`, and consider interning only for a specific purpose after weighing trade-offs.
6. **Thinking `equals()` automatically strips whitespace**: `"Java"` differs from `"Java "`. If input normalization is desired, use explicit rules, such as `strip()` when trimming boundary whitespace is genuinely allowed.
7. **Thinking `equals()` automatically ignores case**: `"Java"` differs from `"java"`. Only use `equalsIgnoreCase()` if the comparison requirements specify it.
8. **Thinking any two strings that render the same have `equals() == true`**: Unicode can represent text with different code sequences. Consider normalization if the system needs it.
9. **Using `hashCode()` to decide whether two strings are equal**: hash collisions do not prove identical content; `equals()` expresses the exact equality condition.
10. **Using `==` to compare strings just because it is "faster"**: answering the wrong question is not an optimization. Prioritize correctness; optimize only after measuring and identifying a real issue.

## 10. Self-Check Questions

**Question 1.** Predict the output:

```java
String first = "hi";
String second = "hi";
String third = new String("hi");

System.out.println(first == second);
System.out.println(first == third);
System.out.println(first.equals(third));
```

Answer:

```text
true
false
true
```

The two interned literals share the same reference; `new String` creates a different object with the same character sequence.

**Question 2.** When both variables are `null`, which condition returns `true` and which throws an exception?

```java
String a = null;
String b = null;

System.out.println(a == b);
System.out.println(java.util.Objects.equals(a, b));
// System.out.println(a.equals(b));
```

Both of the first two print statements output `true`. If the last line is uncommented, calling `a.equals(b)` throws `NullPointerException` because `a` is `null`.

**Question 3.** If two strings have both different references and different content, what do `a == b` and `a.equals(b)` evaluate to?

Both evaluate to `false`, yet their meanings still differ: `==` checks same object, while `equals()` checks same text. **You cannot infer backwards** from matching results that the two mechanisms are equivalent.

**Question 4.** A program reads `String command` from the user and needs to recognize the exact uppercase command `"START"`. How should the condition be written?

```java
if ("START".equals(command)) {
    // Perform the task.
}
```

This condition checks exact content, is case-sensitive, and avoids NPE when `command == null`. Only if the business logic accepts `"start"` should you consider `equalsIgnoreCase()` along with appropriate normalization rules.

## Summary

Given two `String` references `a` and `b`, ask yourself:

- **Do you need to know whether both variables point to the same object?** → `a == b`.
- **Do you need to know whether the two text values are the same?** → `a.equals(b)` if `a` is non-`null`; `Objects.equals(a, b)` when null-safety is needed.
- **Is one side a fixed string literal?** → usually use `"expected".equals(actual)` for content checks.
- **Do requirements care about case sensitivity, whitespace, or Unicode?** → define explicit rules before comparing; `equals()` checks exact content by default.

The String Pool can cause some `==` comparisons between literals to return `true`, but **that is a reference-sharing property**, not a change in comparison contract. Correct text-processing code must reflect **content** equality without depending on how the JVM arranges `String` objects.

## References

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `equals`, `equalsIgnoreCase`, `compareTo`, `contentEquals`, `intern`.
- [Java Language Specification §15.21.3 — Reference Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21.3): meaning of `==` and `!=` for reference types.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5): specification for interning string literals.
- [Java SE 21 API — `java.util.Objects.equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): null-safe equality check.
