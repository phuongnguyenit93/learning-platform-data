# Testing Type Pattern Matches and Non-Matches in Java

## 1. Goal: Testing Both Outcomes of a Type Pattern

When using pattern matching for `instanceof`, an expression like `value instanceof String text` both asks **whether the value is of type `String`** and declares the variable `text` if the check succeeds. Therefore, when testing, we cannot just prove that a `String` object enters the right branch; we must also verify what happens if the object **does not match**.

Lesson objectives:

- Distinguish between a *type pattern match* and a *non-match*, including `null`, other types, subtypes, and interfaces.
- Design **positive tests**, **negative tests**, and **boundary tests** with concrete expected results.
- Check the flow after `instanceof`, including pattern variables, `&&`, `!`, and **flow scoping**.
- Test conditional chains when an input can match multiple types, such as `String`, `Integer`, or `CharSequence`.
- Know how to test generic structures via `List<?>` and check each element instead of expecting generic type arguments to be checked at runtime.
- Run a standalone Java program with **23 assertions**, then apply a similar structure in JUnit 5.

**Version:** Type patterns with `instanceof` were standardized in **Java 16** via [JEP 394](https://openjdk.org/jeps/394). The main program in this lesson runs with **JDK 17+** and does not require preview features. The extension on type patterns in `switch` applies to **Java 21+** (JEP 441).

## 2. What Do Match and Non-Match Actually Mean?

Consider a method that accepts `Object`:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "text:" + text;
    }
    return "not-a-string";
}
```

When `value` is a non-null `String` object, the type pattern **matches**. Java can use `text` as type `String` inside the `if` body without writing `(String) value`.

When `value` is an `Integer`, `StringBuilder`, `null`, or another type incompatible with `String`, the type pattern **does not match**. The `if` body is skipped and the method returns `not-a-string`.

There are several common points of confusion:

1. **It is not a class name comparison.** `instanceof Interface i` can also match implementations of the interface, even when the runtime class name differs from the interface name.
2. **It does not require the exact same class.** When a pattern checks a superclass or interface, objects of compatible subtypes can still match.
3. **`null` does not match a type pattern in `instanceof`.** The check returns `false`; by itself it does not throw a `NullPointerException`.
4. **A non-match is not an error by default.** Whether to return a fallback, throw an exception, or try another pattern is a decision of the surrounding code and must be tested.
5. **The pattern variable can only be used where the pattern is guaranteed to have matched.** The non-match branch has no valid `text` variable to access.

With `Object` variables:

```java
Object a = "hello";
Object b = 7;
Object c = null;

System.out.println(a instanceof String text); // true
System.out.println(b instanceof String text); // false
System.out.println(c instanceof String text); // false
```

The snippet above illustrates three separate checks. In real code, we usually use the bound variable immediately inside the `if` body to avoid unused-variable warnings and to prove that the matched branch actually processes the data.

## 3. Designing a Test Matrix: Do Not Just Pass One Valid String

Suppose a method classifies input in order:

```java
static String classify(Object input) {
    if (input instanceof String text) {
        if (text.isBlank()) return "blank-text";
        return "text:" + text.strip();
    }
    if (input instanceof Integer number) {
        return number >= 0 ? "nonnegative:" + number : "negative:" + number;
    }
    return input == null ? "null" : "unsupported:"
            + input.getClass().getSimpleName();
}
```

The test matrix should cover **each matching type, each non-matching type, and conditions inside the branches**:

| Input `input` | `String` Pattern | `Integer` Pattern | Expected Result |
| --- | --- | --- | --- |
| `" Java "` | Match | Not evaluated due to `return` | `text:Java` |
| `""` | Match | Not evaluated | `blank-text` |
| `"   "` | Match | Not evaluated | `blank-text` |
| `0` | Non-match | Match | `nonnegative:0` |
| `7` | Non-match | Match | `nonnegative:7` |
| `-3` | Non-match | Match | `negative:-3` |
| `3.5` | Non-match | Non-match | `unsupported:Double` |
| `true` | Non-match | Non-match | `unsupported:Boolean` |
| `new StringBuilder("ab")` | Non-match | Non-match | `unsupported:StringBuilder` |
| `null` | Non-match | Non-match | `null` |

**Why is each group needed?**

- Testing only `"Java"` does not prove the code handles empty or whitespace-only strings properly.
- Testing only `7` does not prove the `number >= 0` condition handles `0` or negative numbers properly.
- Testing only an `Integer` object does not prove a `Double` value is not mistakenly routed into the Integer branch.
- Testing only supported types does not prove the fallback branch or `null` handling works.
- A test using `new StringBuilder("ab")` distinguishes `String` from a class that **also holds characters but is not a String**.

Key takeaway: instead of just writing `assertFalse(input instanceof String)`, **call the method under test** and verify the expected result of the non-match path.

## 4. Supertypes, Interfaces, and Subtypes: Choosing the Right Data

Type patterns rely on runtime type compatibility. Therefore, you should also test **matching via an interface**, not only exact class name matches.

```java
static String textLength(Object input) {
    if (!(input instanceof CharSequence sequence)) {
        return "not-textual";
    }
    return "length:" + sequence.length();
}
```

For this example:

- `"Java"` matches `CharSequence` because `String implements CharSequence` → `length:4`.
- `new StringBuilder("abc")` also matches `CharSequence` → `length:3`.
- `new Object()` does not match → `not-textual`.
- `null` does not match → `not-textual`.

A flawed way to write tests is assuming only `String` matches `CharSequence`. The right way is to rely on the type hierarchy, not guess from a specific object's class name.

**Note on static types:** Not every `instanceof Pattern` expression is syntactically valid when the compiler already knows a static type that is too specific. For example, checking `String s; if (s instanceof String text)` is a redundant check that Java may reject because the expression is already a subtype of the pattern type. Use `Object` or an appropriate interface/supertype in examples if a runtime type check is genuinely needed.

Do not use `getClass() == String.class` instead of `instanceof` if the contract requires accepting subtypes/implementations. Those two checks behave differently.

## 5. Guards and Boundary Values: Matching the Type Is Not Enough to Succeed

A type pattern can match while the subsequent **business condition** fails. For example:

```java
static String longText(Object input) {
    if (input instanceof String text && text.length() >= 3) {
        return "long:" + text;
    }
    return "short-or-not-string";
}
```

Minimum cases:

- `"abc"`: type pattern matches, guard is true at the boundary length of 3 → `long:abc`.
- `"ab"`: type pattern matches, but guard is false → `short-or-not-string`.
- `123`: type pattern does not match; `text.length()` is not evaluated due to `&&` short-circuiting → `short-or-not-string`.
- `null`: type pattern does not match, `length()` is not called → `short-or-not-string`.

Thus, you need to distinguish three test states: **pattern match + guard true**, **pattern match + guard false**, and **pattern non-match**. If all of them return the same fallback, a test can add a helper to count condition evaluations when business logic requires verifying the flow; normally, however, testing the **public result** and intended side effects is enough.

Do not change the expression to:

```java
// DOES NOT COMPILE: variable text is not guaranteed to exist when the pattern is false.
if (input instanceof String text || text.length() >= 3) {
    System.out.println(text);
}
```

With `||`, when the left operand is false, there is no bound `text` variable available for the right operand. With `&&`, when the left operand is true, the pattern has matched, so the right-hand side can use `text`. This is an example of **flow scoping** that you must understand to write both code and tests correctly.

## 6. Complete Java 17 Program: 23 Checks with Assertions

Create a file named **`TypePatternMatchTestDemo.java`** with the following content:

```java
public class TypePatternMatchTestDemo {
    static String classify(Object input) {
        if (input instanceof String text) {
            if (text.isBlank()) return "blank-text";
            return "text:" + text.strip();
        }
        if (input instanceof Integer number) {
            return number >= 0 ? "nonnegative:" + number : "negative:" + number;
        }
        return input == null ? "null" : "unsupported:" + input.getClass().getSimpleName();
    }

    static String textLength(Object input) {
        if (!(input instanceof CharSequence sequence)) return "not-textual";
        return "length:" + sequence.length();
    }

    static String longText(Object input) {
        if (input instanceof String text && text.length() >= 3) {
            return "long:" + text;
        }
        return "short-or-not-string";
    }

    static String countNonblankStrings(Object input) {
        if (!(input instanceof java.util.List<?> items)) return "not-a-list";
        int count = 0;
        for (Object element : items) {
            if (element instanceof String text && !text.isBlank()) {
                count++;
            }
        }
        return "nonblank-strings:" + count;
    }

    static int checked;
    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected + " actual=" + actual);
        }
        checked++;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        expect("string", "text:Java", classify(" Java "));
        expect("empty-string", "blank-text", classify(""));
        expect("whitespace-string", "blank-text", classify("   "));
        expect("int-zero", "nonnegative:0", classify(0));
        expect("int-positive", "nonnegative:7", classify(7));
        expect("int-negative", "negative:-3", classify(-3));
        expect("double-not-integer", "unsupported:Double", classify(3.5));
        expect("boolean-unsupported", "unsupported:Boolean", classify(true));
        expect("null", "null", classify(null));
        expect("string-builder-no-string", "unsupported:StringBuilder", classify(new StringBuilder("ab")));
        expect("charsequence-string", "length:4", textLength("Java"));
        expect("charsequence-builder", "length:3", textLength(new StringBuilder("abc")));
        expect("charsequence-object", "not-textual", textLength(new Object()));
        expect("charsequence-null", "not-textual", textLength(null));
        expect("long-boundary-below", "short-or-not-string", longText("ab"));
        expect("long-boundary", "long:abc", longText("abc"));
        expect("long-guard-false", "short-or-not-string", longText(123));
        expect("long-null", "short-or-not-string", longText(null));
        expect("list-match", "nonblank-strings:2", countNonblankStrings(java.util.Arrays.asList("a", "", 7, null, "xy")));
        expect("list-empty", "nonblank-strings:0", countNonblankStrings(java.util.List.of()));
        expect("list-mixed", "nonblank-strings:0", countNonblankStrings(java.util.Arrays.asList(1, 2, null)));
        expect("list-nonmatch", "not-a-list", countNonblankStrings("a"));
        expect("list-null", "not-a-list", countNonblankStrings(null));
        System.out.println("checks=" + checked);
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac --release 17 TypePatternMatchTestDemo.java
java TypePatternMatchTestDemo
```

**Exact output:**

```text
PASS string => text:Java
PASS empty-string => blank-text
PASS whitespace-string => blank-text
PASS int-zero => nonnegative:0
PASS int-positive => nonnegative:7
PASS int-negative => negative:-3
PASS double-not-integer => unsupported:Double
PASS boolean-unsupported => unsupported:Boolean
PASS null => null
PASS string-builder-no-string => unsupported:StringBuilder
PASS charsequence-string => length:4
PASS charsequence-builder => length:3
PASS charsequence-object => not-textual
PASS charsequence-null => not-textual
PASS long-boundary-below => short-or-not-string
PASS long-boundary => long:abc
PASS long-guard-false => short-or-not-string
PASS long-null => short-or-not-string
PASS list-match => nonblank-strings:2
PASS list-empty => nonblank-strings:0
PASS list-mixed => nonblank-strings:0
PASS list-nonmatch => not-a-list
PASS list-null => not-a-list
checks=23
```

**What the tests actually prove within the scope of this example:**

- Three `String` cases match the pattern but branch into non-empty strings and blank/empty strings.
- Three `Integer` cases match after the `String` pattern does not match, while also checking the `0` boundary.
- `Double`, `Boolean`, and `StringBuilder` do not match either the `String` or `Integer` patterns and take the fallback branch.
- `null` does not match the type patterns and is handled separately without dereferencing.
- Two different implementations of `CharSequence` both match the interface pattern; `Object` and `null` do not match.
- The `longText` cases distinguish match + guard true, match + guard false, non-match, and null.
- `List<?>` checks the **container type**; the loop checks **each element's type**. Mixed data containing `String`, numbers, and null must produce the exact count of non-blank Strings.

The `expect` helper throws `AssertionError` if `actual` differs from `expected`, so the program **fails immediately** when a test assumption is wrong. Printing `PASS` only happens after comparing for equality. The line `checks=23` confirms that the demo's 23 assertions passed; **it does not mean every possible state and input of every application has been tested**.

## 7. Rewriting in JUnit 5 for Project Use

In a Maven or Gradle project with the **JUnit Jupiter** dependency, separate production code from test code and use `@Test`/`assertEquals` so the test runner detects failures, counts tests, and generates reports.

Example test file **`TypePatternMatchJUnitTest.java`** placed in the same package as the `TypePatternMatchTestDemo` class:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class TypePatternMatchJUnitTest {
    @Test
    void stringMatchAndNonMatch() {
        assertAll(
            () -> assertEquals("text:Java",
                    TypePatternMatchTestDemo.classify(" Java ")),
            () -> assertEquals("blank-text",
                    TypePatternMatchTestDemo.classify("  ")),
            () -> assertEquals("unsupported:Double",
                    TypePatternMatchTestDemo.classify(3.5)),
            () -> assertEquals("null",
                    TypePatternMatchTestDemo.classify(null))
        );
    }

    @Test
    void interfacePatternAndGuardBoundary() {
        assertEquals("length:3",
                TypePatternMatchTestDemo.textLength(new StringBuilder("abc")));
        assertEquals("not-textual",
                TypePatternMatchTestDemo.textLength(new Object()));
        assertEquals("long:abc",
                TypePatternMatchTestDemo.longText("abc"));
        assertEquals("short-or-not-string",
                TypePatternMatchTestDemo.longText("ab"));
    }

    @Test
    void listContainerAndElementPatterns() {
        assertEquals("nonblank-strings:2",
                TypePatternMatchTestDemo.countNonblankStrings(
                        java.util.Arrays.asList("a", "", 7, null, "xy")));
        assertEquals("not-a-list",
                TypePatternMatchTestDemo.countNonblankStrings("not a list"));
    }
}
```

This is a **JUnit template** that requires JUnit 5 on the test classpath; the test snippet alone cannot be run standalone with the two `javac/java` commands from section 6 if the dependency is missing. In a Maven/Gradle project, run it through the actual test runner configuration. The test uses package-private `static` methods of the demo class in the same package so no production code changes are needed.

Test organization tips:

1. Name tests to describe **both the condition and the outcome**: `whenDouble_thenFallback` or `whenNull_thenDefault`.
2. Keep each test focused on a meaningful group of behaviors; parameterized tests can be a good fit for matrices with dozens of inputs.
3. Ensure non-match tests do not accidentally repeat the same fallback branch while skipping `null` and subtypes.
4. When business rules require failing fast, add `assertThrows` to verify the expected exception type and message.
5. Monitor coverage to find unexecuted branches, but do not use coverage as a substitute for defining expected results.

## 8. Testing Generic Type Patterns: Container vs. Element Difference

A common mistake is thinking that checking:

```java
// DOES NOT COMPILE if raw is Object:
if (raw instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

will verify `String` elements. In Java, type arguments of most generic types undergo **type erasure**, so `List<String>` is not a valid reifiable type pattern when `raw` is `Object`. Check the container with `List<?>`, then verify each element's type:

```java
static int countStrings(Object raw) {
    if (!(raw instanceof java.util.List<?> values)) return 0;
    int count = 0;
    for (Object value : values) {
        if (value instanceof String text) {
            count++;
        }
    }
    return count;
}
```

This is a snippet that can be placed in a suitable class and compiled with Java 17+. You should distinguish:

- **Container match:** `new ArrayList<Integer>()` still matches `List<?>`.
- **Element match:** an `Integer` element does not match `String text`, whereas a `String` element does.
- **Null element:** `null instanceof String text` is false and does not throw an error just from the `instanceof` check.
- **Empty list:** the container matches, but the valid element count is 0.
- **Non-list input:** the container does not match and the method returns the fallback value.

If tests only use `List<String>`, you will not catch bugs when runtime receives a mixed list from legacy data. The full example in section 6 already includes `List<?>`, mixed data, and `null` in the same matrix.

## 9. Pattern Variable Scope: Cases That Fail at Compile Time

Some errors cannot be tested at runtime because the compiler rejects the code. For example:

```java
// DOES NOT COMPILE: text is not guaranteed to exist after if.
static int wrongScope(Object raw) {
    if (raw instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

After the `if`, `raw` might not be a `String`; `text` is not guaranteed to be bound. Fix it with a negated guard clause:

```java
static int safeLength(Object raw) {
    if (!(raw instanceof String text)) return -1;
    return text.length();
}
```

For the corrected version, the minimum test suite should include:
- `safeLength("hi") == 2`: pattern matches, pattern variable is used.
- `safeLength(10) == -1`: non-match, early return.
- `safeLength(null) == -1`: `null` also does not match.

**Distinction:** the compiler guarantees the pattern variable is not used on the non-matching path, but the compiler **does not prove the business rule is right**. If the length must be greater than 0, you still have to add a separate condition and test.

When reviewing code, treat a compiler error caused by scope or an invalid type pattern as a **syntax/type-level error**, not a runtime branch that tests need to trigger.

## 10. Extension: Testing Type Patterns in `switch` (Java 21+)

Starting in Java 21, type patterns can also appear in `switch` `case` labels:

```java
// Java 21+, snippet placed inside a method receiving Object input.
String label = switch (input) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    case Integer n -> "integer:" + n;
    default -> "unsupported";
};
```

Corresponding test matrix:

| Input | Branch That Must Match | Result |
| --- | --- | --- |
| `" "` | `case String s when s.isBlank()` | `blank` |
| `"Java"` | `case String s` | `text:Java` |
| `7` | `case Integer n` | `integer:7` |
| `3.5` | `default` | `unsupported` |
| `null` | `case null` | `missing` |

Differences from `instanceof`:

- An unguarded `case String s` placed **before** `case String s when ...` will shadow the guarded branch. The compiler may report a *dominated case label*.
- A `switch expression` over an open type like `Object` needs an exhaustive branch such as `default` to handle all other types.
- `case null` handles a null selector. **`default` should not be treated as a substitute for `case null`**.
- When using a `when` guard, tests must exercise both **guard true** and **guard false**. A test that only confirms the input is a `String` is not enough.

The Java 21 snippet in this section is an extension guide; the standalone runnable program in section 6 intentionally uses only stable Java 17 features.

## 11. Avoiding Test Patterns That Create a False Sense of Security

| Poor Testing Practice | Problem | Better Approach |
| --- | --- | --- |
| Using only one valid `String` | No evidence for non-match, `null`, or guard false. | Build a matrix with multiple types, `null`, and boundary values. |
| Only calling `System.out.println(actual)` | Code could print the wrong value and the test still looks "finished". | Use `assertEquals`/`AssertionError` with concrete expected values. |
| Testing `obj instanceof String` without calling the production method | Does not prove the method handles the non-match branch properly. | Test the return value or exception of the actual method under test. |
| Assuming `StringBuilder` matches `String` | Confuses a character-holding class with a subtype of `String`. | Test `StringBuilder` as a non-match for `String` and a match for `CharSequence`. |
| Skipping `null` tests | `null` does not match any type pattern in `instanceof`. | Verify the fallback path or exception for `null` according to the contract. |
| Not testing interfaces/subtypes | Could accidentally write an exact class check instead of `instanceof`. | Use different implementations of the same interface. |
| Not testing `&&` guard false | The pattern may match while the extra condition is still false. | Test at the threshold, below the threshold, and with the wrong type. |
| Checking `List<String>` as a runtime type | Generic element types are not preserved across erasure. | Use `List<?>` and match each element. |
| Testing the fallback branch with only one other type | Fails to catch differences between wrong type and `null`. | Separate `null`, other types, container, and element cases. |
| Looking only at 100% branch coverage | Does not verify boundary values or expected business results. | Combine coverage with assertions and data partitions. |
| `catch (Exception e) {}` in negative tests | Can hide the wrong exception type, causing a false pass. | Use `assertThrows` or a helper that checks the exact exception. |
| Testing only `case String s` in `switch` | Can miss `when`, `case null`, and `default`. | Test each branch and routing condition. |

### Test Data Must Trigger the Right Branch

Especially in an `if / else if` chain, if the first branch matches and returns (`return`), subsequent branches are never evaluated. To test the `Integer` branch of `classify`, the input must **not match `String`** and **match `Integer`**. To test the fallback, the input must **match neither `String` nor `Integer`**.

Do not mark a non-match test as PASS just because the method returns any non-null value; compare against the exact expected business result. If the code throws an exception on invalid input, a negative test must prove it throws the right exception rather than receiving a successful fallback.

## 12. Hands-On Exercise: Design Your Own Type Pattern Tests

Given the method:

```java
static String formatCode(Object value) {
    if (value instanceof String code && code.length() == 4) {
        return "code:" + code;
    }
    if (value instanceof Number number) {
        return "number:" + number.intValue();
    }
    return value == null ? "missing" : "invalid";
}
```

**Question:** Build a test suite checking `String` pattern match/non-match, guard true/false, `Number` pattern match, unsupported types, and `null`. Specifically, do `Integer`, `Long`, and `Double` all match the `Number number` pattern?

**Answer and suggested test cases:**

1. `formatCode("AB12")` → `code:AB12`: `String` match, length is exactly 4.
2. `formatCode("ABC")` → `invalid`: `String` match but guard is false; `Number` non-match.
3. `formatCode("")` → `invalid`: `String` match but insufficient length.
4. `formatCode(7)` → `number:7`: `Integer` is a subtype of `Number`.
5. `formatCode(7L)` → `number:7`: `Long` also matches `Number`.
6. `formatCode(3.9)` → `number:3`: `Double` matches `Number` and `intValue()` converts the value according to Java numeric rules; here it takes the integer part `3`.
7. `formatCode(true)` → `invalid`: `Boolean` is neither `Number` nor `String`.
8. `formatCode(null)` → `missing`: neither pattern matches.
9. `formatCode(new StringBuilder("AB12"))` → `invalid`: neither `String` nor `Number`.

These cases both verify **the selected branch** and confirm that **the broader type** `Number` accepts its subclasses. This helps catch mistakes if someone refactors to `value instanceof Integer` and forgets `Long`/`Double`. If you want to avoid precision loss when converting `Double` to `int`, the business requirements and code need to change; the current tests accurately reflect the written behavior rather than inferring financial semantics.

The snippets in this exercise are meant to be placed in an appropriate class; the standalone program with `main`, assertions, and verified output is in section 6.

## 13. Project Application Checklist

Before considering type pattern testing complete:

1. **List the patterns and branches to test**: `String`, `Integer`, `CharSequence`, `Number`, `List<?>`, or your application's actual data types.
2. **At least one positive test** for each required match branch, with a verifiable value.
3. **At least one negative test** to trigger the non-match path; if there are multiple distinct invalid data types, pick meaningful groups.
4. **Test `null` separately** because `null` does not match `instanceof` and may be handled differently from wrong types.
5. **Test subtypes/interfaces** when the pattern uses a superclass or interface.
6. **Test guard true/false and boundary values** when the match branch has extra conditions, such as `length >= 3` or `number >= 0`.
7. **Test fallback/exception** according to the contract, not just checking that "the method does not crash".
8. **Use automated assertions** and review failure reports; consider moving matrices into JUnit parameterized tests when there are many data sets.
9. **Remember type erasure**: checking `List<?>` does not prove every element has type `String`.
10. **Do not confuse compile-time errors with runtime non-matches**: scope errors or invalid patterns must be fixed in code, while valid non-matches need runtime behavior tests.

**Remember:** Proper type pattern testing must prove that **when matched, the variable is used and the result is accurate; when not matched, the program transitions to the right branch, right result, or right exception**. Test `null`, unexpected types, interfaces/subtypes, and guard boundary values instead of writing only a single happy-path assertion.

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html), [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441), [Java SE 17 Language Specification — instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
