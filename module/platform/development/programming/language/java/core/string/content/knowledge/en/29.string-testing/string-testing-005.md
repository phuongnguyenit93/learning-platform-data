# Testing `==`, `equals`, `intern`, and Constant Expressions in Java String

Two `String` variables can **hold the exact same text** yet **point to two different objects**. Conversely, multiple variables can point to the same object thanks to string literal sharing and `intern()`. When testing, you must properly distinguish **string content**, **object identity**, **compile-time constant expressions**, and **results created at runtime**.

Core example:

```java
String literal = "java";
String anotherLiteral = "java";
String fresh = new String("java");

System.out.println(literal == anotherLiteral); // true
System.out.println(literal == fresh);          // false
System.out.println(literal.equals(fresh));     // true
System.out.println(literal == fresh.intern());  // true
```

All four outcomes have specific reasons. A good test suite must verify **precisely what the API promises**, rather than guessing `==` results merely because text looks the same.

## 1. Four Concepts to Distinguish

| Check | What it actually checks | When to use |
| --- | --- | --- |
| `a == b` | Whether two reference variables point to the **same object** (or both are `null`) | Intentionally testing object identity or pooling rules |
| `a.equals(b)` | Whether `a` and `b` have the **same content** per `String.equals` | Nearly all text-value comparisons |
| `a.intern()` | Returns the **canonical** string representing `a`'s content | When canonicalizing string references is genuinely needed |
| Constant expression `"ab" + "cd"` | Evaluated at **compile time**; resulting string is interned like a literal | Testing Java language constant-folding rules |

For `String`:

- `equals` compares character sequences in exact order and value (case-sensitive); it does not rely on reference identity.
- `==` on two `String` variables compares references; it does not inspect characters.
- `intern()` does not mutate content or “transform” the original object; it returns a **reference** to the canonical representative with the same content.
- Not every string matching a literal's content is **automatically** interned when created at runtime.

`String` is immutable, yet **immutable does not mean every equal-content instance is the same instance**.

## 2. Why Do Two String Literals Usually Have `==` Evaluate to `true`?

Per the Java Language Specification, string literals with identical content represent the same `String` instance. Therefore:

```java
String first = "coffee";
String second = "coffee";
System.out.println(first == second); // true
```

This is **specified behavior**, suitable for writing a test that demonstrates how literals work.

An expression composed of `String` constants, the `+` operator, and operands that are *constant expressions* is also evaluated at **compile time**. The string result of a constant expression is interned:

```java
String word = "coffee";
String folded = "co" + "ffee";
System.out.println(word == folded); // true
```

The compiler can store the shared `"coffee"` literal in the class file; no new object needs to be allocated at runtime just to join `"co"` and `"ffee"`.

**Key point:** `==` returning `true` here does not prove that **all** string concatenations share objects. You must verify whether an expression is genuinely a **constant expression in the Java language**.

## 3. Constant Expressions, `final` Variables, and Runtime Concatenation

### Case A — all parts of the concatenation are constants

```java
String a = "coffee";
String b = "co" + "ffee";

System.out.println(a == b); // true
```

`"co" + "ffee"` is a `String` constant expression. The compiler folds the content into `"coffee"`; `b` uses the canonical reference.

### Case B — `final String` constant variable

```java
final String PREFIX = "co";
String a = "coffee";
String b = PREFIX + "ffee";

System.out.println(a == b); // true
```

A `final` variable of primitive or `String` type initialized with a **constant expression** is a *constant variable*. `PREFIX` in this example is a constant variable, so `PREFIX + "ffee"` remains a constant expression and can be folded at compile time.

### Case C — non-constant variable

```java
String prefix = "co";
String a = "coffee";
String b = prefix + "ffee";

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

`prefix` is not a constant variable because it is not declared `final`. Concatenation is a runtime operation, producing a result with the same content but a different reference from the literal. Compilers and JVMs may choose different concatenation mechanisms, yet **you should never rely on `==` to test the content of runtime concatenation**.

### Case D — `final`, but initializer is not a constant expression

```java
final String prefix = new String("co");
String a = "coffee";
String b = prefix + "ffee";

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

The `final` keyword only forbids reassigning `prefix`. It **does not make `new String("co")` a compile-time constant**. Hence `prefix + "ffee"` is still evaluated at runtime.

| Expression creating `b` | Compile-time constant expression? | `"coffee" == b` |
| --- | --- | --- |
| `"co" + "ffee"` | Yes | `true` |
| `final String p = "co"; b = p + "ffee";` | Yes | `true` |
| `String p = "co"; b = p + "ffee";` | No | `false` |
| `final String p = new String("co"); b = p + "ffee";` | No | `false` |
| `new String("coffee")` | No | `false` |
| `new StringBuilder().append("co").append("ffee").toString()` | No | `false` |

This table describes **specific code expressions** evaluating to `"coffee"` and the described object creation. For real-world data, always verify content using `equals`.

## 4. `new String(...)` and `StringBuilder.toString()`: Same Content, Different Object

`new String("coffee")` explicitly requests creating a new `String` object; even though it takes its value from an interned literal, the result is still a distinct instance:

```java
String literal = "coffee";
String fresh = new String("coffee");

System.out.println(literal == fresh);      // false
System.out.println(literal.equals(fresh)); // true
```

Likewise, converting a `StringBuilder`'s contents to a `String` yields valid text; do not assume this string is interned:

```java
String literal = "coffee";
String built = new StringBuilder()
        .append("co")
        .append("ffee")
        .toString();

System.out.println(literal == built);      // false
System.out.println(literal.equals(built)); // true
```

**Testing rule:** if system functionality only requires matching text, a test like `assertEquals("coffee", actual)` is meaningful; a test like `assertSame("coffee", actual)` may impose an **object-identity constraint** that the functionality never promised.

## 5. What Does `intern()` Guarantee?

`String.intern()` returns a reference to the **canonical string object** whose content equals the receiver string. If an equal-content string already resides in the intern table, that reference is returned; otherwise, interning establishes a canonical representative per the API contract.

The most useful guarantee:

```java
String x = new String("coffee");
String y = new StringBuilder()
        .append("co")
        .append("ffee")
        .toString();

System.out.println(x == y);                 // false
System.out.println(x.equals(y));            // true
System.out.println(x.intern() == y.intern()); // true
```

Because `x` and `y` have the same content, their `intern()` results are the **same reference**. With a known literal:

```java
String literal = "coffee";
String fresh = new String("coffee");

System.out.println(fresh == literal);          // false
System.out.println(fresh.intern() == literal); // true
System.out.println(fresh == literal);          // false
```

Calling `fresh.intern()` **does not change `fresh` itself to point to the canonical reference**. To use the interned result later, you must assign or directly use the returned reference:

```java
String canonical = fresh.intern();
```

### Do Not Test Implementation Details with `==`

Some examples in the wild rely on an assumption like “the first `intern()` call on a runtime string always returns that exact instance.” The guarantee application code should rely on is that **strings with equal content produce identical `intern()` references**; do not build logic around which object was stored first or when the JVM initializes its pool.

Interning also carries resource-management overhead. There is no need to call `intern()` just to compare content: `equals` is usually more direct, clearer, and purpose-built.

## 6. Standalone Java 17+ Test Program

Create `StringComparisonDemo.java`. The program self-checks 16 conditions and **throws `AssertionError` if any fails**; thus it runs as a standalone test without JUnit or enabling JVM assertions.

```java
import java.util.Objects;

public class StringComparisonDemo {
    private static int checks;

    private static void check(
            String name, boolean actual, boolean expected) {
        if (actual != expected) {
            throw new AssertionError(name + " expected "
                    + expected + " but got " + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        String literal = "coffee";
        String repeated = "coffee";
        String folded = "co" + "ffee";

        final String constantPrefix = "co";
        String viaConstant = constantPrefix + "ffee";

        String variablePrefix = "co";
        String viaVariable = variablePrefix + "ffee";

        final String nonconstantPrefix = new String("co");
        String viaFinalObject = nonconstantPrefix + "ffee";

        String fresh = new String("coffee");
        String built = new StringBuilder()
                .append("co")
                .append("ffee")
                .toString();

        String nullable = null;

        check("repeated literals", literal == repeated, true);
        check("literal folding", literal == folded, true);
        check("constant variable folding", literal == viaConstant, true);
        check("runtime variable concatenation",
                literal == viaVariable, false);
        check("final reference is not always constant",
                literal == viaFinalObject, false);
        check("new String identity", literal == fresh, false);
        check("new String content", literal.equals(fresh), true);
        check("Objects.equals content",
                Objects.equals(literal, fresh), true);
        check("StringBuilder identity", literal == built, false);
        check("StringBuilder content", literal.equals(built), true);
        check("intern canonical result", literal == fresh.intern(), true);
        check("intern both strings",
                fresh.intern() == built.intern(), true);
        check("intern does not change fresh identity",
                literal == fresh, false);
        check("null-safe one null",
                Objects.equals(nullable, literal), false);
        check("null-safe two nulls",
                Objects.equals(nullable, null), true);
        check("non-null equals(null)",
                literal.equals(nullable), false);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

Compile and run:

```bash
javac StringComparisonDemo.java
java StringComparisonDemo
```

Exact output:

```text
PASS: 16 checks
```

This is a self-verifying test of actual behavior, rather than just printing values and asking the reader to compare by eye. Each `check` call states an explicit expectation; failures report which test case failed. The program **does not use Java's `assert` statement**, because `assert` is disabled by default unless `-ea` is enabled.

To quickly inspect a single expression, you can print it as in earlier sections; for automation, use test conditions that genuinely fail when output differs from expectations.

## 7. Writing Tests with JUnit 5

In a project that already has JUnit Jupiter, you can use assertions that clearly express intent:

- `assertEquals(expected, actual)`: checks **value/content** via `equals` logic.
- `assertSame(expected, actual)`: checks **same reference**.
- `assertNotSame(unexpected, actual)`: checks **different reference**.
- `assertTrue`, `assertFalse`: check a condition with clear intent.
- `assertNull` and `assertNotNull`: check null references.

Example test file in a JUnit 5 project (this snippet **will not run standalone without the JUnit Jupiter dependency**):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Objects;

class StringComparisonTest {

    @Test
    void literalAndConstantExpressionShareReference() {
        String literal = "coffee";
        final String constantPrefix = "co";

        assertSame(literal, "co" + "ffee");
        assertSame(literal, constantPrefix + "ffee");
    }

    @Test
    void runtimeStringHasSameContentButDifferentReference() {
        String literal = "coffee";
        String generated = new String("coffee");

        assertNotSame(literal, generated);
        assertEquals(literal, generated);
    }

    @Test
    void internReturnsCanonicalReference() {
        String literal = "coffee";
        String generated = new String("coffee");

        assertSame(literal, generated.intern());
        assertNotSame(literal, generated);
    }

    @Test
    void nullComparisonIsSafeWhenRequested() {
        String absent = null;
        String present = "coffee";

        assertFalse(Objects.equals(absent, present));
        assertTrue(Objects.equals(absent, null));
        assertFalse(present.equals(absent));
    }
}
```

Assertions using `assertSame` in this example only test **specified behavior**: literals/constant expressions are interned and `intern()` results share the canonical reference. When testing a function whose contract is solely “return the right text,” use `assertEquals`.

**Avoid:** using `assertSame("OK", service.getStatus())` if the service does not promise an interned instance; even with the right value, the test can fail on a completely valid new instance.

## 8. Testing with `null`: `equals` Does Not Protect the Receiver

`==` compares references and does not throw `NullPointerException` merely because one or both operands are `null`:

```java
String a = null;
String b = null;

System.out.println(a == b); // true
```

However, calling an instance method on a `null` reference causes an error:

```java
String value = null;

// value.equals("ready") will throw NullPointerException.
boolean safe1 = "ready".equals(value);  // false
boolean safe2 = Objects.equals(value, "ready"); // false
```

`"ready".equals(value)` works well when the left-hand side is a literal guaranteed non-null. `Objects.equals(a, b)` fits when **both variables can be null**: two nulls are treated as equal, one null and one non-null as not equal.

### `equals` and `equalsIgnoreCase` Have Different Criteria

`String.equals` is case-sensitive:

```java
System.out.println("Java".equals("java"));           // false
System.out.println("Java".equalsIgnoreCase("java")); // true
```

If the requirement is case-insensitive comparison, write tests directly for that behavior. Never use `==` as an “optimization” in place of any content comparison.

## 9. Common Testing Mistakes

1. **Using `==` to verify business output of a string-processing function.** The result may have identical content yet be a different instance; use `equals` or `assertEquals` if the contract only specifies text.
2. **Assuming `final` always creates a constant expression.** `final String p = new String("co")` is not a constant variable; `p + "ffee"` is still computed at runtime.
3. **Failing to distinguish constant concatenation from runtime concatenation.** `"co" + "ffee"` is a constant expression; `String prefix = "co"; prefix + "ffee"` is not.
4. **Assuming `new String(literal)` is automatically interned.** The constructor creates a new object; its content equals the literal, but its reference differs.
5. **Assuming calling `intern()` mutates the original variable.** It returns a reference; `fresh` still points to the original instance unless reassigned.
6. **Depending on “the first `intern()` returns this exact object.”** Do not write tests forcing the JVM to use a specific intern strategy beyond the canonicalization contract.
7. **Forgetting `null` when calling `equals`.** `nullable.equals(...)` can throw an exception; put a literal on the left or use `Objects.equals` where appropriate.
8. **Confusing JUnit's `assertEquals` and `assertSame`.** The former checks content; the latter checks reference identity.
9. **Using `assert` and running Java without `-ea`.** A program printing “test passed” while `assert` is disabled is misleading; JUnit or checks explicitly throwing `AssertionError` are better.
10. **Testing identity everywhere thinking pooling saves memory.** Memory-optimization rules do not automatically become functional system contracts. Only test identity when specifically verifying literals, constant expressions, or `intern()`.

## 10. Practice Exercises

**Question 1.** Predict both outputs:

```java
String a = "cat";
String b = "c" + "at";
System.out.println(a == b);
System.out.println(a.equals(b));
```

Answer: `true`, `true`. The expression joining two literals is evaluated at compile time.

**Question 2.** Predict with a non-`final` variable:

```java
String prefix = "c";
String a = "cat";
String b = prefix + "at";
System.out.println(a == b);
System.out.println(a.equals(b));
```

Answer: `false`, `true`. This is runtime concatenation, yet content still equals `cat`.

**Question 3.** Is `final` alone enough for concatenation to become a constant expression?

No. You need a `final` variable of primitive or `String` type **initialized with a constant expression**. For example, `final String p = "c";` can be folded; `final String p = new String("c");` cannot.

**Question 4.** Contrast the two checks:

```java
String x = new String("cat");
String y = new String("cat");
System.out.println(x == y);
System.out.println(x.intern() == y.intern());
```

Answer: `false` then `true`. Two separate objects are created, yet interning equal content returns one canonical reference.

**Question 5.** A function returns `new String("OK")` on success. Should you assert `assertEquals("OK", actual)` or `assertSame("OK", actual)`?

If the contract only requires the value `OK`, use `assertEquals`. `assertSame` would demand the exact same reference and misrepresent the requirement.

**Question 6.** When both `String` variables may be `null`, what is the safe way to compare content?

`Objects.equals(a, b)`. It yields `true` if both are `null`, `false` if only one is `null`, and delegates to `equals` if both are non-null.

## 11. Pre-Conclusion Test Checklist

- **Are you testing text or identity?** Use `equals`/`assertEquals` for text; `==`/`assertSame` for identity.
- **Is the expression truly a compile-time constant?** Check whether every participating variable is a constant variable.
- **Is there `new String`, `StringBuilder`, or runtime concatenation?** If so, never assume the result is interned.
- **Are you using `intern()`?** Compare the **returned reference** and do not confuse it with the original variable.
- **Is `null` possible?** Use `Objects.equals` or place a literal on the left side of `equals`.
- **Does the test genuinely fail when wrong?** Use JUnit, checks throwing `AssertionError`, or run Java assertions properly with `-ea`.

**Takeaway:** `==` and `assertSame` are about **objects**; `equals` and `assertEquals` are about **content**; `intern()` canonicalizes references; *constant expressions* determine when strings are evaluated and interned at compile time. Write tests against behavioral contracts first, and test pooling mechanics only when that is actually your target.

## Official Documentation

- [`String.equals`, `String.intern` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java Language Specification, 3.10.5 — String Literals](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5)
- [Java Language Specification, 15.29 — Constant Expressions](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-15.html#jls-15.29)
- [Java Language Specification, 4.12.4 — final Variables](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4)
