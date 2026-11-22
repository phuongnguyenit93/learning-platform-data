# `String.contentEquals()`: Comparing Content with `StringBuilder` and `CharSequence`

## 1. The Problem and Core Idea

In Java, `String` stores an *immutable* character sequence. Meanwhile, `StringBuilder`, `StringBuffer`, and many other types implementing `CharSequence` can supply a character sequence without being `String` objects. Sometimes you need to ask: **"Is this object's current character sequence identical to the content of a `String`?"** That is the use case for `String.contentEquals(...)`.

For instance, a data parser has assembled a field name in a `StringBuilder` and needs to compare it against the keyword `"status"`. Calling `"status".equals(builder)` returns `false`, even when the characters match, because `String.equals(Object)` only considers another object equal if it is also a `String` with the same content. `"status".contentEquals(builder)` directly inspects the character sequence inside the builder.

~~~java
String expected = "status";
StringBuilder actual = new StringBuilder("status");

System.out.println(expected.equals(actual));        // false
System.out.println(expected.contentEquals(actual)); // true
System.out.println(expected.equals(actual.toString())); // true
~~~

Both of the last two approaches are accurate for content. `contentEquals(builder)` avoids having the caller create an intermediate `String` via `builder.toString()`; actual efficiency depends on the object type, JDK version, JVM optimizations, and usage context.

## 2. The Two Overloads of `String.contentEquals()`

The `java.lang.String` class provides:

~~~java
public boolean contentEquals(StringBuffer sb)
public boolean contentEquals(CharSequence cs)
~~~

These are **API signatures**, not a complete Java program.

- **`contentEquals(StringBuffer)`:** compares `String` content against a `StringBuffer`. `StringBuffer` is a mutable class with synchronized operations; the dedicated `StringBuffer` overload synchronizes observation of the buffer while comparing.
- **`contentEquals(CharSequence)`:** compares `String` content against any object implementing `CharSequence`, such as `StringBuilder`, `StringBuffer`, `String`, `CharBuffer`, or a custom implementation.

`StringBuilder` does **not** have a dedicated overload; it is accepted because `StringBuilder implements CharSequence`. Both overloads share the same result semantics: `true` when the respective character sequences match exactly; `false` otherwise.

`CharSequence` is a read-only interface over a `char` sequence, with operations like `length()`, `charAt(int)`, and `subSequence(...)`. The interface **does not require immutability**. Thus, the result of `contentEquals()` reflects the content observed at the time of the call, not a guarantee that the object will remain unchanged later.

~~~java
CharSequence text = new StringBuilder("Java");
StringBuffer buffer = new StringBuffer("Java");

System.out.println("Java".contentEquals(text));   // true: CharSequence overload
System.out.println("Java".contentEquals(buffer)); // true: StringBuffer overload
System.out.println("Java".contentEquals("Java")); // true: String is also a CharSequence
~~~

When a variable's declared type is `CharSequence`, the compiler selects the `contentEquals(CharSequence)` overload, even if the runtime object is a `StringBuffer`. What matters is **content-comparison semantics**, not forcing callers to cast to another overload.

## 3. How Do `equals()`, `contentEquals()`, and `==` Differ?

| Expression | Condition Returning `true` | When to Use |
|---|---|---|
| `a == b` | Same object reference (for reference types) | Identity check; do not use by default for comparing text |
| `a.equals(b)` when `a` is a `String` | `b` is also a `String` with the same UTF-16 character sequence | Comparing two Strings |
| `a.contentEquals(cs)` | `cs` currently provides the same character sequence, even if it is a StringBuilder | Comparing a String with a CharSequence |
| `a.equals(cs.toString())` | `toString()` produces a String with content equal to `a` | Reasonable when a String copy is already needed for another purpose |
| `a.equalsIgnoreCase(b)` | Two Strings match under Java's case-insensitive rules | Case-insensitive text comparison; no direct CharSequence version exists |

Example with two distinct `String` objects:

~~~java
String a = new String("abc");
String b = new String("abc");
System.out.println(a == b);              // false
System.out.println(a.equals(b));         // true
System.out.println(a.contentEquals(b));  // true
~~~

When both sides are `String`, `equals()` is usually the clearest choice. When the other side is a `StringBuilder` or a `CharSequence` built during processing, `contentEquals()` expresses the intent directly without eagerly converting to a String.

**Important note:** `StringBuilder` does not override `Object.equals()` for content comparison; `new StringBuilder("abc").equals(new StringBuilder("abc"))` is `false` because they are two separate objects. To compare **two** `StringBuilder`s, in Java 17 you can use `builder1.compareTo(builder2) == 0` because `StringBuilder` implements `Comparable<StringBuilder>`, or compare via a `String` using `contentEquals()`. Do not assume every `CharSequence` has content-based `equals()`: the interface does not mandate that.

## 4. Comparing `StringBuilder` When Its Content Changes

`StringBuilder` is mutable: `append()`, `insert()`, `delete()`, `replace()`, `setCharAt()`, and `setLength()` can alter the character sequence. A later comparison can return a different result from an earlier one:

~~~java
String expected = "abc";
StringBuilder builder = new StringBuilder("abc");

System.out.println(expected.contentEquals(builder)); // true
builder.append('d');
System.out.println(expected.contentEquals(builder)); // false
builder.deleteCharAt(3);
System.out.println(expected.contentEquals(builder)); // true
~~~

While parsing or building messages, compare after the target content has been constructed. If you need a **stable snapshot** to store, pass to another thread, or reuse over time, take `String snapshot = builder.toString();` at an appropriate checkpoint and compare with `equals()`; never assume a mutable `CharSequence` will keep its content fixed.

### Whole-Sequence Comparison, Not Prefix or Substring

`contentEquals()` checks the **entire character sequence**. It is not like `contains()`, `startsWith()`, or partial matching:

~~~java
StringBuilder full = new StringBuilder("status=OK");
System.out.println("status".contentEquals(full)); // false
System.out.println("status=OK".contentEquals(full)); // true
System.out.println("status=OK".startsWith("status")); // true
~~~

If the goal is merely finding a keyword inside a longer string, use `contains()`, `indexOf()`, or a parser rather than `contentEquals()`.

## 5. Comparing Against a Parameter Declared as `CharSequence`

An API accepting `CharSequence` lets you support multiple data sources without forcing callers to convert everything to `String`:

~~~java
static boolean isReady(CharSequence candidate) {
    return "READY".contentEquals(candidate);
}
~~~

You can call:

~~~java
System.out.println(isReady("READY"));                     // true
System.out.println(isReady(new StringBuilder("READY")));  // true
System.out.println(isReady(new StringBuffer("READY")));   // true
System.out.println(isReady(new StringBuilder("ready")));  // false
~~~

The two blocks above are **illustrative snippets**: place `isReady` inside a class, and the `System.out.println` calls inside a runnable method, as shown in the complete program below.

The `CharSequence` interface has various implementations:

- `String`: immutable content.
- `StringBuilder`: mutable, optimized for building strings on a single thread.
- `StringBuffer`: mutable, with synchronized buffer methods.
- `java.nio.CharBuffer`: exposes a character region determined by `position` and `limit`; content can depend on its current state and visible window.
- Custom implementations: may have their own mechanisms for generating or reading content; do not assume `toString()`, `equals()`, and `charAt()` guarantee properties beyond what that API documents.

Example with a `CharBuffer` wrapped to view four characters:

~~~java
import java.nio.CharBuffer;

CharBuffer buffer = CharBuffer.wrap("Java");
System.out.println("Java".contentEquals(buffer));  // true
buffer.position(1);
System.out.println("Java".contentEquals(buffer));  // false: remaining content is "ava"
System.out.println("ava".contentEquals(buffer));   // true
~~~

`CharBuffer` treats the characters from `position` up to `limit` as the remaining elements of the buffer. Changing `position` changes the character sequence exposed by `CharSequence` methods; therefore, do not treat every `CharSequence` as a fixed String.

## 6. Null, Case Sensitivity, Unicode, and Whitespace

### 6.1. Null

`"abc".contentEquals((CharSequence) null)` throws `NullPointerException`. The receiving String also cannot be null; `String s = null; s.contentEquals(...)` throws `NullPointerException`.

If null is a valid value in your data model, check beforehand:

~~~java
static boolean sameText(String expected, CharSequence actual) {
    return expected != null && actual != null
            && expected.contentEquals(actual);
}
~~~

This follows a **null never matches** convention, even when both are null. If business rules require null to equal null, define that rule explicitly; for String/String only, you can use `Objects.equals()`. Do not assume `contentEquals(null)` returns `false`.

### 6.2. Case Sensitivity and Whitespace

`contentEquals()` compares the exact sequence of code units: it does not ignore spaces, does not `trim`/`strip`, and does not change case.

~~~java
System.out.println("Java".contentEquals(new StringBuilder("java")));   // false
System.out.println("Java".contentEquals(new StringBuilder(" Java")));  // false
System.out.println("Java".contentEquals(new StringBuilder("Java")));   // true
~~~

If you need case-insensitive comparison or whitespace trimming, make the input-normalization rules explicit:

~~~java
import java.util.Locale;

StringBuilder candidate = new StringBuilder(" java ");
String normalized = candidate.toString().strip().toUpperCase(Locale.ROOT);
System.out.println("JAVA".equals(normalized)); // true
~~~

`Locale.ROOT` fits many language-independent machine codes, yet **does not** replace natural-language word comparison rules for every locale. Normalization must be decided by actual requirements; do not expect it automatically inside `contentEquals()`.

### 6.3. Unicode: Compares UTF-16, Does Not Auto-Normalize

Both `String` and `CharSequence` expose a sequence of `char`s (UTF-16 code units). With `contentEquals()`, the two sequences must match identically. Visually identical Unicode representations can differ:

~~~java
import java.text.Normalizer;

String composed = "\u00E9";       // é: one code point
StringBuilder decomposed = new StringBuilder("e\u0301"); // e + combining acute accent

System.out.println(composed.contentEquals(decomposed)); // false
String normalized = Normalizer.normalize(
        decomposed.toString(), Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

Emojis outside the BMP can use **two `char`s**, yet if both code-unit sequences are completely identical, `contentEquals()` still returns true:

~~~java
System.out.println("🚀".length());                             // 2
System.out.println("🚀".contentEquals(new StringBuilder("🚀"))); // true
~~~

If natural-language comparison is needed (such as Vietnamese name sorting, diacritic stripping, or case folding), choose the right algorithm/locale; `contentEquals()` only compares exact content. It also is **not** a substitute for comparing passwords or secrets with constant-time requirements, because the API makes no timing side-channel resistance guarantees.

## 7. Synchronization and Thread Safety

`String` is immutable and safe for multiple threads to read concurrently. `StringBuilder` is mutable and has **no internal synchronization**, so it must not be modified concurrently with a `contentEquals()` call on another thread without coordination. Reading `length()` and each `charAt()` on an object undergoing modification can observe inconsistent state; the outcome is unpredictable, with no atomic snapshot guarantee.

`StringBuffer` uses synchronization for its operations. The `String.contentEquals(StringBuffer)` overload synchronizes on the buffer object while comparing, so it can observe a consistent character sequence relative to mutations that follow the same lock. Even so, the data **can still change before or after the call**. Do not confuse the safety of a single comparison with a multi-operation atomic transaction.

Example of a multi-step block:

~~~java
// Illustrative snippet, not an atomic transaction:
StringBuffer shared = new StringBuffer("READY");
if ("READY".contentEquals(shared)) {
    // Another thread can still modify shared right after the if condition is evaluated.
    // Do not assume shared is always "READY" inside this body.
}
~~~

If checking and using the content must happen as a single transaction, synchronize a block covering **both the check and the usage** under the same lock followed by all writers, or convert the data into an immutable snapshot at the right boundary.

~~~java
StringBuilder builder = new StringBuilder("READY");
// After all write operations on builder have finished:
String snapshot = builder.toString();
System.out.println("READY".equals(snapshot)); // true
~~~

If multiple threads access `StringBuilder`, the snapshot creation step must also be properly synchronized; `toString()` itself does not fix unsynchronized concurrent writes.

## 8. Performance: When to Avoid `toString()`?

When you already have a `StringBuilder` and only need **a single full-content comparison**, `expected.contentEquals(builder)` avoids an explicit String creation in code. Creating a `String` from a builder via `toString()` can incur allocation or copying depending on the JVM/JDK; however, you **cannot** conclude from this that `contentEquals()` never allocates or is always faster.

Comparison:

~~~java
String expected = "GET";

// Approach 1: compare character sequence directly.
boolean direct = expected.contentEquals(builder);

// Approach 2: create intermediate String then compare.
boolean converted = expected.equals(builder.toString());
~~~

In this example, `builder` is assumed to already exist and hold the text under check. These are **only two styles for discussion**, not a standalone Java file.

Practical selection rules:

- If you only need **one or a few comparisons** against an existing `StringBuilder`, prefer `contentEquals()` because it states the intent directly and does not require calling `toString()`.
- If you need to store/pass text to an API expecting `String` or reuse a snapshot multiple times, `String snapshot = builder.toString();` may be more appropriate and clearer.
- If comparing **two Strings**, use `equals()`; do not wrap them in a builder just to call `contentEquals()`.
- For performance-sensitive code, measure real workloads using a profiler or JMH; avoid naive loop microbenchmarks because JIT/escape analysis can eliminate or alter costs unexpectedly.

Do not use `contentEquals()` as a blanket replacement for `equals()`. Its purpose is **directly comparing a String against a non-String CharSequence**.

## 9. Complete Program Running on Java 17

Put the entire block below into a UTF-8 file named **`ContentEqualsDemo.java`**. The program demonstrates both overloads, mutating content, full-string checks, CharSequence, and a Unicode normalization example.

~~~java
import java.nio.CharBuffer;
import java.text.Normalizer;
import java.util.Locale;

public class ContentEqualsDemo {
    private static boolean isReady(CharSequence value) {
        return value != null && "READY".contentEquals(value);
    }

    public static void main(String[] args) {
        String expected = "Java";
        StringBuilder builder = new StringBuilder("Java");

        System.out.println("equalsBuilder=" + expected.equals(builder));
        System.out.println("contentBuilder=" + expected.contentEquals(builder));
        System.out.println("equalsString=" + expected.equals(builder.toString()));

        builder.append('!');
        System.out.println("afterAppend=" + expected.contentEquals(builder));
        builder.deleteCharAt(4);
        System.out.println("afterDelete=" + expected.contentEquals(builder));

        CharSequence sequence = new StringBuilder("Java");
        StringBuffer buffer = new StringBuffer("Java");
        System.out.println("asSequence=" + expected.contentEquals(sequence));
        System.out.println("asBuffer=" + expected.contentEquals(buffer));

        CharBuffer charBuffer = CharBuffer.wrap("Java");
        System.out.println("charBufferFull=" + expected.contentEquals(charBuffer));
        charBuffer.position(1);
        System.out.println("charBufferSuffix=" + "ava".contentEquals(charBuffer));

        System.out.println("ready=" + isReady(new StringBuilder("READY")));
        System.out.println("nullReady=" + isReady(null));
        System.out.println("caseSensitive=" +
                "Java".contentEquals(new StringBuilder("java")));

        String normalized = new StringBuilder(" java ").toString()
                .strip().toUpperCase(Locale.ROOT);
        System.out.println("normalized=" + "JAVA".equals(normalized));

        String composed = "\u00E9";
        StringBuilder decomposed = new StringBuilder("e\u0301");
        System.out.println("unicodeDirect=" +
                composed.contentEquals(decomposed));
        System.out.println("unicodeNFC=" +
                composed.equals(Normalizer.normalize(
                        decomposed.toString(), Normalizer.Form.NFC)));
    }
}
~~~

Compile with JDK 17+ using UTF-8 source encoding and run:

~~~bash
javac -encoding UTF-8 ContentEqualsDemo.java
java ContentEqualsDemo
~~~

Exact stdout output:

~~~text
equalsBuilder=false
contentBuilder=true
equalsString=true
afterAppend=false
afterDelete=true
asSequence=true
asBuffer=true
charBufferFull=true
charBufferSuffix=true
ready=true
nullReady=false
caseSensitive=false
normalized=true
unicodeDirect=false
unicodeNFC=true
~~~

Key explanation: `equalsBuilder=false` because `String.equals(Object)` does not treat `StringBuilder` as a String. `contentBuilder=true` because the character sequences match. Appending `!` changes the length, so comparison fails; deleting it makes them equal again. `CharBuffer` exposes the sequence from its current position to its limit; moving position to 1 leaves `"ava"`. Unicode NFC normalization converts `e + combining acute accent` to the representation equivalent to `é`.

## 10. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| `"abc".equals(new StringBuilder("abc"))` | Always false for StringBuilder | `"abc".contentEquals(builder)` |
| `a == b` to check text | Compares identity, not content | Use `equals()` or `contentEquals()` as appropriate |
| Calling `contentEquals(null)` | `NullPointerException` | Null-check beforehand |
| Treating a builder comparison result as permanent | Builder may be mutated later | Compare at point of use or take a snapshot |
| Mutating builder concurrently while comparing on another thread | Race condition, inconsistent state | Coordinate synchronization or take a safe snapshot |
| Expecting case/space insensitivity | `contentEquals()` compares exact code units | Normalize intentionally before comparing |
| Expecting visually similar Unicode to be equal | Code point/code unit sequences may differ | Normalize appropriately when business logic requires it |
| Expecting `contentEquals()` to find a substring | It checks the entire sequence | `contains()`/`indexOf()` or a parser |
| Calling `toString()` on every comparison just to use `equals()` | Can create unnecessary conversions | Use `contentEquals()` directly when only comparing |
| Believing `contentEquals()` is always faster | Optimization depends on the case and JVM | Benchmark/profile on real workloads |

## 11. Guidelines for Choosing an API

1. **Both objects are `String`:** `equals()` for exact content; `equalsIgnoreCase()` if case-insensitive comparison is required and locale/semantics have been considered.
2. **One `String`, one `StringBuilder`/`StringBuffer`/`CharSequence`:** `String.contentEquals()` for direct full-sequence comparison.
3. **Need an immutable snapshot from a builder:** convert via `toString()` at an appropriate checkpoint and compare with `equals()`; for multi-threaded shared data, ensure no unsynchronized concurrent writes.
4. **Need to find a substring:** use `contains()`, `indexOf()`, `startsWith()`, or regex depending on requirements.
5. **Dealing with null or complex Unicode data:** define explicit rules for null, case, whitespace, and normalization before calling the API.

`contentEquals()` is valuable specifically because it **directly compares the current content of a `CharSequence` against a `String`**, even when the two objects have different types. It does not auto-normalize text, does not substitute for thread-safety guarantees, and does not make `equals()` obsolete.
