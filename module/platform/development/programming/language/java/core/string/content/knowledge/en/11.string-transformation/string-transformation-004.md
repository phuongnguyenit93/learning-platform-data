# `String.repeat(int)`: Repetition Count, Empty Strings, and Negative Values in Java

## 1. What Is `repeat()` Used For?

When you need to repeat **an entire string intact** multiple times and concatenate the copies consecutively, the `java.lang.String` class provides the method:

```java
public String repeat(int count)
```

`String.repeat(int)` has been available since **Java 11** and works on Java 17 and later. It produces a **resulting string value** by repeating the entire content of the receiver string exactly `count` times. No separator is automatically inserted between repetitions.

For example, inside the body of a Java method:

```java
String word = "ha";
String result = word.repeat(3);

System.out.println(result); // hahaha
```

Intuitive view:

```text
"ha".repeat(3)
    = "ha" + "ha" + "ha"
    = "hahaha"
```

`repeat` is especially convenient for generating separators, padding characters, divider lines, or pattern strings with a known repetition count. It **does not modify the original string content** because `String` is *immutable*.

**Most important rule:** the `count` parameter must be **non-negative**. The value `0` is valid and produces an empty string; a negative number causes the method to throw `IllegalArgumentException`.

## 2. Behavior Table by Repetition Count

Suppose the receiver string is `"ab"`:

| Expression | Result or behavior | Meaning |
|---|---|---|
| `"ab".repeat(0)` | `""` | Repeat zero times |
| `"ab".repeat(1)` | `"ab"` | Keep same content, once |
| `"ab".repeat(2)` | `"abab"` | Concatenate two copies |
| `"ab".repeat(3)` | `"ababab"` | Concatenate three copies |
| `"ab".repeat(-1)` | `IllegalArgumentException` | Negative repetition count is invalid |

This differs from what some beginners might guess:

- `repeat(0)` **does not** return the original string and **does not** return `null`. It returns the empty string `""`.
- `repeat(1)` produces **content identical to the original string**. You should not rely on reference comparison `==` to verify the result, even though a JDK implementation may reuse the object in this case.
- `repeat(2)` and higher concatenate copies **without inserting spaces, commas, or newlines** between them.
- `repeat(-1)` does not mean "drop one element" or "repeat in reverse." It is an invalid argument, so Java throws an exception.

A multi-character string is always repeated **as a whole**:

```java
System.out.println("Java ".repeat(3)); // Java Java Java 
System.out.println("ab".repeat(3));    // ababab
System.out.println("-=".repeat(3));    // -=-=-=
```

In the first example, the space is **already inside** `"Java "`. Therefore, the result also has the trailing space. If you call `"Java".repeat(3)`, the result will be `"JavaJavaJava"`.

## 3. Empty Receiver String Case

An **empty string** is represented by `""` and has length `0`. When the original content is empty, repeating it any **non-negative** number of times still produces an empty string:

```java
"".repeat(0) // ""
"".repeat(1) // ""
"".repeat(5) // ""
```

Because concatenating empty strings produces no additional characters:

```text
"" + "" + "" = ""
```

Whether the receiver string has content or not, the rule for **negative numbers** remains the same:

```java
"".repeat(-2); // Throws IllegalArgumentException
```

This is a key point to remember: **an empty string does not make a negative repetition count valid**.

### Empty String Differs from `null`

```java
String empty = "";
System.out.println(empty.repeat(3).isEmpty()); // true

String missing = null;
// missing.repeat(3); // NullPointerException
```

`empty` references a valid `String` object with `length() == 0`; therefore, `repeat` can be called. `missing` is a `null` reference, so there is no object to receive the method call. This error differs from `IllegalArgumentException` when passing a negative `count` to a valid string.

## 4. Negative Numbers and `IllegalArgumentException`

`repeat(int count)` requires `count >= 0`. When `count < 0`, Java throws an exception of type `IllegalArgumentException`.

```java
String line = "-";
line.repeat(-1); // IllegalArgumentException
```

To catch the exception in a test scenario:

```java
try {
    String result = "ab".repeat(-3);
    System.out.println(result);
} catch (IllegalArgumentException ex) {
    System.out.println("count must be non-negative");
}
```

**Stdout:**

```text
count must be non-negative
```

You should not use `catch (Exception ignored) {}` to silently swallow errors if `count` comes from a formula or user input. It is usually better to make the business rule explicit before calling:

```java
static String repeatSafely(String text, int count) {
    if (count < 0) {
        throw new IllegalArgumentException("count must be >= 0");
    }
    return text.repeat(count);
}
```

This is an illustrative method placed inside a class. The check provides a clearer error message in application code, though `repeat` itself already checks for negative repetition counts.

### When `count` Is Computed by an Expression

A practical scenario is computing the number of spaces needed to reach a desired width:

```java
String label = "Java";
int width = 3;
int padding = width - label.length(); // -1
// String result = label + " ".repeat(padding); // Error because count = -1
```

If the intent is **to add no padding when the content is already long enough**, you can clamp to `0`:

```java
int padding = Math.max(0, width - label.length());
String result = label + " ".repeat(padding);
```

Here `Math.max(0, ...)` reflects the **business rule for string padding**. You should not automatically turn every negative `count` into `0` in all situations: sometimes a negative number is a data error that must be reported clearly.

## 5. Complete Java 17+ Example

Save the following content into **`StringRepeatDemo.java`**:

```java
public class StringRepeatDemo {

    static void show(String label, String value) {
        System.out.println(label + "=[" + value + "], length=" + value.length());
    }

    public static void main(String[] args) {
        String unit = "ab";

        show("zero", unit.repeat(0));
        show("once", unit.repeat(1));
        show("twice", unit.repeat(2));
        show("three", unit.repeat(3));

        show("emptyFive", "".repeat(5));
        show("emptyZero", "".repeat(0));
        show("emojiTwice", "😀".repeat(2));

        System.out.println("original=" + unit);
        unit.repeat(3); // Return value is discarded
        System.out.println("discarded=" + unit);

        String saved = unit.repeat(3);
        System.out.println("saved=" + saved);

        try {
            "".repeat(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative=" + ex.getClass().getSimpleName());
        }

        show("dashes", "-".repeat(6));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 StringRepeatDemo.java
java StringRepeatDemo
```

**Stdout:**

```text
zero=[], length=0
once=[ab], length=2
twice=[abab], length=4
three=[ababab], length=6
emptyFive=[], length=0
emptyZero=[], length=0
emojiTwice=[😀😀], length=4
original=ab
discarded=ab
saved=ababab
negative=IllegalArgumentException
dashes=[------], length=6
```

### Output Analysis

1. `repeat(0)` returns `""`, so the content inside `[]` is empty and `length()` is `0`.
2. `repeat(1)`, `repeat(2)`, and `repeat(3)` produce `"ab"`, `"abab"`, and `"ababab"`, respectively.
3. `""` repeated `5` times or `0` times remains an empty string.
4. `"😀"` is **one Unicode code point** represented by **two UTF-16 code units**; two emojis have `String.length() == 4`.
5. `unit.repeat(3);` computes the result and discards it, so `unit` still holds `"ab"`. When the result is stored in `saved`, `"ababab"` is retained.
6. `"" .repeat(-1)` (written without a space between `""` and `.repeat` in code) still throws `IllegalArgumentException`, showing that negative arguments are rejected even on an empty string.
7. `"-".repeat(6)` produces exactly six hyphens, with no extra separators.

The example uses `show` to wrap content in `[]`: this makes empty strings easier to spot when printed on screen.

## 6. `repeat()` and `String` Immutability

Like `trim()`, `replace()`, `substring()`, or `toUpperCase()`, `repeat()` is a method that produces a **return value** and does not modify the content of the receiving `String` object.

**Wrong if the goal is to update the variable:**

```java
String marker = "*";
marker.repeat(4);
System.out.println(marker); // *
```

The call `marker.repeat(4)` returned `"****"`, but the result was discarded. To keep the result, you can:

**Reassign the variable:**

```java
marker = marker.repeat(4);
System.out.println(marker); // ****
```

**Or store it in another variable:**

```java
String original = "*";
String repeated = original.repeat(4);

System.out.println(original); // *
System.out.println(repeated); // ****
```

**Or use it directly as an argument:**

```java
System.out.println("*".repeat(4)); // ****
```

There is no reason to assume `repeat()` increases the length of the old `String` object itself. Java only allows changing the **value of a reference variable** via reassignment; `String` objects themselves are immutable.

### Do Not Rely on `==` to Identify Results

When `count == 1`, the resulting content equals the original content. A JDK implementation may return the same `String` object, but this is not a requirement to rely on when using the method.

```java
String source = new String("xy");
String once = source.repeat(1);

System.out.println(source.equals(once)); // true
```

Use `.equals(...)` to check content; using `==` on two `String`s compares **object references**, not text.

## 7. Result Length and Memory Considerations

If the initial string has `m = source.length()` (measured in **UTF-16 code units**) and `count = n` is a non-negative integer, the length of the resulting string mathematically is:

\[
L = m \times n
\]

Example:

```java
String a = "abc";
String b = a.repeat(4);

System.out.println(b);          // abcabcabcabc
System.out.println(b.length()); // 12 = 3 * 4
```

For an empty string, `m == 0`, so the result always has length `0` for any `n >= 0`. For `n == 0`, the result also has length `0` regardless of the source string.

### Avoid Creating Huge Strings

`repeat` may require allocating memory proportional to the result size. A very large positive `count` combined with a long string can cause memory issues or slow down the program. If the requested size exceeds what the JVM can represent or allocate, the operation may fail, for instance with **`OutOfMemoryError`**.

Do not run dangerous examples like the following in a normal application:

```java
// Illustration not meant to be executed: risks consuming huge memory.
String huge = "abcdefghij".repeat(Integer.MAX_VALUE);
```

This is a **size/memory** issue, distinct from the `IllegalArgumentException` caused by negative `count`. Do not rely on a specific error message or assume the JVM can always allocate the string just because `count >= 0`.

When user-supplied data determines the repetition count, set appropriate limits. For example, the method below limits the total result length to an application-defined threshold:

```java
static String boundedRepeat(String text, int count, int maxUnits) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    if (count < 0 || maxUnits < 0) {
        throw new IllegalArgumentException("count and maxUnits must be non-negative");
    }

    long expectedUnits = (long) text.length() * count;
    if (expectedUnits > maxUnits) {
        throw new IllegalArgumentException("Result exceeds limit");
    }

    return text.repeat(count);
}
```

Casting to `(long)` before multiplication prevents **`int` integer overflow** during the size check. This check limits the number of UTF-16 code units per application policy, rather than guaranteeing that every memory allocation will always succeed.

## 8. Unicode and Multi-Unit UTF-16 Characters

`repeat` does not operate on individual characters to select or slice them. It repeats the **entire source string**, so valid surrogate pairs inside a copy are still copied together.

Example:

```java
String emoji = "😀";
String repeated = emoji.repeat(3);

System.out.println(repeated); // 😀😀😀
System.out.println(repeated.length()); // 6
System.out.println(
        repeated.codePointCount(0, repeated.length())
); // 3
```

`String.length()` counts UTF-16 code units; each emoji here consists of two code units, so three emojis have length `6` yet only `3` Unicode code points.

Similarly, for Vietnamese characters represented by multiple code points (such as a base letter plus a combining mark), `repeat` still copies the **exact input code sequence**. The method **does not normalize Unicode**, does not change case, and does not automatically compose combining characters.

If the source string already contains an unpaired surrogate, `repeat` also does not automatically fix or validate that Unicode data. It simply repeats the string with its existing content.

## 9. When Should You Use and Not Use `repeat()`?

### Creating Divider Lines or Text Accents

```java
String line = "-".repeat(12);
System.out.println(line); // ------------
```

Simpler and easier to read than manually writing a loop to append a fixed character.

### Creating Padding of a Known Length

```java
String label = "OK";
int width = 6;

String padded = label + " ".repeat(Math.max(0, width - label.length()));
System.out.println("[" + padded + "]"); // [OK    ]
```

This example computes width using `String.length()` (UTF-16 code units). If you need exact column alignment by **terminal display width**, `length()` is insufficient for emojis, combining characters, or characters of varying display widths.

### Creating Multiple Blank Lines or Newline Characters

```java
String twoNewlines = "\n".repeat(2);
```

The result contains two newline characters. When printed directly, blank lines can be hard to spot visually; this is why QA examples often print additional labels or lengths.

### Distinguishing from Joining with Separators

```java
String result = "Java".repeat(3);
// "JavaJavaJava"
```

If you want `"Java,Java,Java"`, you need to build **separator** logic yourself. A simple approach is using `String.join` with a list of elements:

```java
String joined = String.join(",", java.util.Collections.nCopies(3, "Java"));
System.out.println(joined); // Java,Java,Java
```

`repeat` itself has **no** parameter for a separator; `String.join` solves a different problem of joining elements with a delimiter.

### Cases Where a Loop or `StringBuilder` Is Better

`repeat` fits when you want to repeat the **same pattern** an exact number of times. If the content differs at each step, such as `"1, 2, 3"` or each line containing a new index, use a loop with `StringBuilder` or appropriate collection APIs.

```java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append(", ");
    }
    builder.append(i);
}
System.out.println(builder); // 1, 2, 3
```

`String.repeat` does not take a callback to generate new content on each iteration. It always repeats the receiver string itself.

## 10. Common Mistakes

| Misconception or code | Issue | Fix / principle |
|---|---|---|
| `"ab".repeat(0)` will return `"ab"` | Wrong: repetition count `0` creates an empty string | Expect `""` |
| `"".repeat(5)` will throw an error | Wrong: empty string is valid input | Result stays `""` |
| `"".repeat(-1)` will return `""` | Wrong: `count < 0` is rejected | Handle or report `IllegalArgumentException` |
| `text.repeat(3);` mutates `text` | `String` is immutable | Reassign or use the return value |
| `"ha".repeat(3)` adds spaces automatically | No default separator | Include the space in the pattern if needed |
| `String value = null; value.repeat(2);` | Calling a method on `null` | Validate input, avoid `NullPointerException` |
| `repeat` accepts floating-point `2.5` | Parameter must be `int` | Choose an integer according to business rules |
| `repeat` is always safe with `Integer.MAX_VALUE` | Output string can be too large | Limit `count` and expected size |
| `"😀".repeat(2).length()` equals `2` | `length()` counts UTF-16 code units | Example result is `4`, corresponding to 2 code points |

### Note When Testing Exceptions

Do not check the exception message (`ex.getMessage()`) as a fixed string. The message can vary by JDK or execution path. When teaching the concept, what to verify for negative numbers is the **exception type `IllegalArgumentException`** and the cause `count < 0`.

## 11. Testing Edge Cases

You can create a self-test method placed inside a Java class:

```java
static void testRepeat() {
    if (!"".equals("abc".repeat(0))) {
        throw new AssertionError("repeat(0) must return empty string");
    }
    if (!"abc".equals("abc".repeat(1))) {
        throw new AssertionError("repeat(1) must preserve content");
    }
    if (!"abcabc".equals("abc".repeat(2))) {
        throw new AssertionError("repeat(2) must concatenate two copies");
    }
    if (!"".equals("".repeat(100))) {
        throw new AssertionError("Repeating empty string must stay empty");
    }

    boolean negativeRejected = false;
    try {
        "".repeat(-1);
    } catch (IllegalArgumentException ex) {
        negativeRejected = true;
    }
    if (!negativeRejected) {
        throw new AssertionError("Negative count must be rejected");
    }
}
```

You can call `testRepeat();` from `main`. If all checks pass, the method finishes normally without printing anything. These assertions throw `AssertionError` directly, so they do not depend on the `-ea` runtime flag.

The test suite focuses on the **method specification**: `0`, `1`, positive numbers, empty strings, and negative numbers. These are the essential cases to include when writing utility methods based on `repeat()`.

## 12. Self-Check Questions

**Question 1.** What string does `"xy".repeat(3)` produce and what is its length?

**Answer:** `"xyxyxy"`, length `6` UTF-16 code units.

**Question 2.** Do `"-".repeat(0)` and `"".repeat(10)` return the same content?

**Answer:** Yes. Both return the empty string `""`.

**Question 3.** Why does `String x = "a"; x.repeat(4);` followed by printing `x` still output `"a"`?

**Answer:** `String` is immutable; the `"aaaa"` result was discarded. To keep the result, you need `x = x.repeat(4);` or store it in another variable.

**Question 4.** Do `String.repeat(-5)` and `null.repeat(5)` cause the same error?

**Answer:** No. Calling on a valid `String` with `count = -5` causes `IllegalArgumentException`; attempting to call the method on a `null` reference causes `NullPointerException`.

**Question 5.** Why should you avoid executing `"abc".repeat(count)` when `count` is user-supplied without limits?

**Answer:** An overly large `count` can request a huge amount of memory. Validate inputs and limit the repetition count or expected total length per application requirements.

**Question 6.** How do `"ab".repeat(3)` and `String.join("-", Collections.nCopies(3, "ab"))` differ?

**Answer:** `repeat` produces `"ababab"`; `String.join` with a three-element list and delimiter `"-"` produces `"ab-ab-ab"`. `repeat` does not automatically insert separators.

## 13. Key Takeaways

`String.repeat(int count)` repeats the **entire string content** exactly `count` times, consecutively and without adding separators. For `count = 0`, the result is `""`; for `count = 1`, the content is unchanged; for `count > 1`, copies are concatenated back-to-back. An empty string repeated any **non-negative** number of times stays empty, whereas **any negative `count` throws `IllegalArgumentException`**, even on an empty string.

Because `String` is immutable, you must **use the return value** of `repeat` if you want to keep the result. When the repetition count comes from external data or calculations, validate against negative numbers and bound the total length before allocating large strings.
