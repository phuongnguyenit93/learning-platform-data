# `subSequence` and the `CharSequence` Contract in Java

When you need to extract a portion of text, Java has both `String.substring(start, end)` and `subSequence(start, end)`. What makes `subSequence` worth learning is not just the two slicing indices: it is a **method on the `CharSequence` interface**, so the same call can apply to `String`, `StringBuilder`, `StringBuffer`, `CharBuffer`, or any other class implementing this interface.

It is important to distinguish the **general `CharSequence` contract** from the **specific behavior of each implementation**. The interface specifies which characters the subsequence must represent and what the indices mean; it **does not promise** that the result is always a `String`, always an independent copy, always a view, or always immutable.

## 1. What Is `CharSequence`?

`java.lang.CharSequence` is an abstraction for a readable sequence of **`char` units (UTF-16 code units)**. The core operations are:

| Method | Meaning |
| --- | --- |
| `int length()` | Number of `char` units (UTF-16 code units), not necessarily equal to the number of Unicode characters perceived by a reader |
| `char charAt(int index)` | Reads the `char` unit at `index`, numbered from 0 |
| `CharSequence subSequence(int start, int end)` | Extracts a subsequence over the index range `[start, end)` |
| `String toString()` | Produces a `String` representation containing the character units in the sequence's exact order |
| `boolean isEmpty()` | In Java 17+, checks `length() == 0`; this is a default method on the interface |
| `IntStream chars()` / `IntStream codePoints()` | Streams UTF-16 code units or Unicode code points; their meanings differ for non-BMP characters |

Common implementing classes:

- `String`: immutable content; suitable for stable text values.
- `StringBuilder`: mutable content, not guaranteed to be thread-safe.
- `StringBuffer`: mutable content, with many operations synchronized; this does not mean every multi-step workflow is automatically atomic.
- `CharBuffer` in `java.nio`: character buffer with `position`/`limit`, capable of creating slices that view shared backing data.
- An application-defined class can also implement `CharSequence`.

Example of a method accepting `CharSequence`:

```java
static void show(CharSequence text) {
    System.out.println("Length: " + text.length());
    System.out.println(text.subSequence(0, Math.min(3, text.length())));
}
```

This is an **illustrative method snippet** that must be placed inside a class to compile. Calls like `show("Java")` or `show(new StringBuilder("Java"))` are both valid. When you only need to read characters, declaring the parameter as `CharSequence` lets an API accept many input types. If you need `String`-specific features, declare `String` or convert intentionally.

## 2. The Contract of `subSequence(start, end)`

In the interface, the method signature is:

```java
CharSequence subSequence(int start, int end);
```

The range is defined as a **half-open interval**:

- `start` is the index of the first character **included**, starting from 0.
- `end` is the **stopping position; the character there is excluded**.
- The length of the subsequence equals `end - start`.
- The `i`-th character of the subsequence corresponds to the `(start + i)`-th character of the original sequence, assuming no conflicting mutations occur at that time.
- A valid range requires `0 <= start <= end <= length()`.
- If the indices are invalid, the call throws `IndexOutOfBoundsException` or a subclass of it.
- `start == end` is valid and produces an empty subsequence, even when both equal `length()`.

Example with `"ABCDE"`, numbered:

```text
Chars:    A   B   C   D   E
Index:    0   1   2   3   4
Boundary: 0   1   2   3   4   5

subSequence(1, 4) --> "BCD"
subSequence(0, 5) --> "ABCDE"
subSequence(2, 2) --> ""
subSequence(5, 5) --> ""
subSequence(4, 2) --> error
```

The consistency of the `[start, end)` range makes length calculation and contiguous splitting easy: `text.subSequence(0, cut)` and `text.subSequence(cut, text.length())` cover the entire sequence for a valid `cut`, without duplication and without skipping any position.

### Example 1: Checking Boundaries

Create the file `SubSequenceBoundsDemo.java`:

```java
public class SubSequenceBoundsDemo {
    public static void main(String[] args) {
        CharSequence text = "ABCDE";

        CharSequence middle = text.subSequence(1, 4);
        CharSequence empty = text.subSequence(5, 5);

        System.out.println(middle);
        System.out.println(middle.length());
        System.out.println(empty.isEmpty());
        System.out.println("[" + empty + "]");

        try {
            text.subSequence(4, 2);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("Invalid range");
        }
    }
}
```

Run on JDK 17 or later:

```bash
javac SubSequenceBoundsDemo.java
java SubSequenceBoundsDemo
```

Output:

```text
BCD
3
true
[]
Invalid range
```

Do not rely on the exact exception subclass name or error message produced by `String`, `CharBuffer`, or another implementation. If you need to validate input yourself to report a custom error, `0 <= start && start <= end && end <= text.length()` is the core condition.

## 3. On `String`, How Are `subSequence` and `substring` Related?

`String` implements `CharSequence`. On a `String`, the two methods:

```java
text.substring(start, end)
text.subSequence(start, end)
```

return the same substring **content**. The `String.subSequence` API is specified to behave like `String.substring`; in Java 17, the actual runtime result of `subSequence` on a `String` is a `String` object, even though its declared return type is `CharSequence`.

The most visible difference at the call site is the **compile-time return type**:

- `String.substring(int, int)` is declared to return `String`; you can chain `String` APIs directly.
- `String.subSequence(int, int)` is declared to return `CharSequence`; only members of `CharSequence` and `Object` are visible through that type, unless converted appropriately.

### Example 2: Equal Content but Different Declared Types

Create `StringSubSequenceDemo.java`:

```java
public class StringSubSequenceDemo {
    public static void main(String[] args) {
        String source = "Programming";

        String bySubstring = source.substring(3, 7);
        CharSequence bySubSequence = source.subSequence(3, 7);

        System.out.println(bySubstring);
        System.out.println(bySubSequence);
        System.out.println(bySubstring.equals(bySubSequence));
        System.out.println(bySubSequence instanceof String);

        String converted = bySubSequence.toString();
        System.out.println(converted.toUpperCase());
    }
}
```

```bash
javac StringSubSequenceDemo.java
java StringSubSequenceDemo
```

Output:

```text
gram
gram
true
true
GRAM
```

Step by step:

1. `substring(3, 7)` reads indices `3, 4, 5, 6` of `Programming`, producing `"gram"`.
2. `subSequence(3, 7)` on the same `String` produces an equivalent sequence.
3. `bySubstring.equals(bySubSequence)` returns `true` because the actual object behind `bySubSequence` is a `String` with the same content in this example.
4. `instanceof String` is true **for this `String` implementation**. It is not a guarantee for every `CharSequence.subSequence` result.
5. `toString()` provides a `String` value when the caller needs APIs like `toUpperCase`.

Using `substring` is usually more direct when you know you are working with a `String` and want a `String`. Use `subSequence` when designing a general API that makes sense across classes implementing `CharSequence`.

## 4. Is the Result a Copy, a View, or Immutable?

**There is no single answer for every `CharSequence`.** This is a key point of the interface contract.

Some implementations create a new string, while others may return an object representing a **view** over mutable data. Therefore, you must never deduce “calling `subSequence` guarantees the data is detached from the source” or “the subsequence always reflects all changes to the source”.

Examples of concrete behavior:

| Source Object | Notable Behavior in Java 17 | Can the Result Be Treated as an Independent `String` Copy? |
| --- | --- | --- |
| `String` | `subSequence` is equivalent to `substring` in content, returning an immutable `String` | You can rely on immutable content; do not rely on object identity or internal memory layout |
| `StringBuilder` | Standard implementation returns a `String` result like `substring` | Yes for this implementation; do not generalize that rule to all `CharSequence`s |
| `StringBuffer` | Standard implementation returns a `String` from the specified range | Yes for this implementation |
| `CharBuffer` | `subSequence` creates a new buffer sharing content with the source buffer (a view over the corresponding region) | **No**; the shared source/buffer can be modified |
| Custom `CharSequence` | Determined by the implementation within contract limits | Do not assume without knowing the specific contract |

**Be careful about immutability:** even though the interface is named `CharSequence`, it is **not synonymous with `String`**. A reference of type `CharSequence` can point to a mutable object.

### Example 3: `StringBuilder` and `CharBuffer` Can Behave Differently

Create `SubSequenceImplementationsDemo.java`:

```java
import java.nio.CharBuffer;

public class SubSequenceImplementationsDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("ABCDE");
        CharSequence builderSlice = builder.subSequence(1, 4);

        builder.setCharAt(2, 'x');
        System.out.println(builder);
        System.out.println(builderSlice);

        char[] chars = {'A', 'B', 'C', 'D', 'E'};
        CharBuffer buffer = CharBuffer.wrap(chars);
        CharSequence bufferSlice = buffer.subSequence(1, 4);

        chars[2] = 'x';
        System.out.println(buffer);
        System.out.println(bufferSlice);
    }
}
```

```bash
javac SubSequenceImplementationsDemo.java
java SubSequenceImplementationsDemo
```

Output on JDK 17:

```text
ABxDE
BCD
ABxDE
BxD
```

With `StringBuilder`, `builderSlice` is the `String` result of calling `subSequence` before the builder was mutated, so it still displays `BCD`. With `CharBuffer.wrap(chars)`, the buffer shares its backing storage with `chars`; `bufferSlice` is another buffer viewing a portion of that storage. When `chars[2]` changes from `'C'` to `'x'`, the view also sees `BxD`.

Do not generalize “`builderSlice` stayed unchanged” into an immutability rule for the whole interface. Nor should you generalize “`bufferSlice` changed” into a rule that every `subSequence` returns a view.

**If you need stable immutable text**, convert the slice you need to `String` at an appropriate boundary:

```java
static String stableSlice(CharSequence source, int start, int end) {
    return source.subSequence(start, end).toString();
}
```

This is an **illustrative method snippet**, not a standalone program. With standard `StringBuilder` or `CharBuffer`, `toString()` returns a `String` value representing the content at the time of conversion. If the source can be mutated concurrently by other threads, taking a consistent snapshot requires synchronization appropriate for the source; the `CharSequence` interface itself does not guarantee thread safety.

## 5. `CharSequence` Indices Are UTF-16 Code Units

The `CharSequence` contract describes a sequence of `char`s, i.e., UTF-16 code units. `subSequence(start, end)` can produce a slice containing an unpaired surrogate if a boundary cuts between the two halves of a non-BMP code point. For example, `"A😀B".subSequence(1, 2)` contains only the high surrogate, whereas `subSequence(1, 3)` contains the full pair.

Unlike `String`, the `CharSequence` interface **does not directly provide** `offsetByCodePoints`. If an algorithm needs code point boundaries on a general input, you can convert the content to `String` and use `String`'s code point APIs; for mutable sources, clarify when to take the snapshot and how to synchronize under concurrent access. Code point boundaries are still not guaranteed to be visible character cluster boundaries.

## 6. `CharSequence` Does Not Define a Content-Based `equals` Contract

Another mistake is calling `equals` on two arbitrary objects implementing `CharSequence` and assuming it compares character sequences. The `CharSequence` interface **does not impose a common content-based `equals` contract** across implementations.

For instance, `String` overrides `equals` to compare against **another `String`** with the same content. Meanwhile, `StringBuilder` uses identity-based `equals` (inherited from `Object`).

### Example 5: Same Content Does Not Mean `equals` Returns True

Create `CharSequenceEqualityDemo.java`:

```java
public class CharSequenceEqualityDemo {
    public static void main(String[] args) {
        CharSequence a = "abc";
        CharSequence b = new StringBuilder("abc");

        System.out.println(a.toString().equals(b.toString()));
        System.out.println(a.equals(b));
        System.out.println("abc".contentEquals(b));
        System.out.println(a.length() == b.length());
    }
}
```

```bash
javac CharSequenceEqualityDemo.java
java CharSequenceEqualityDemo
```

Output:

```text
true
false
true
true
```

Both `toString()` calls produce `String` values with the same content, so `equals` returns `true`. However, `a.equals(b)` calls `String.equals`, and `b` is a `StringBuilder`, so it receives `false`. `String.contentEquals(CharSequence)` compares content against a `CharSequence`, returning `true` in the example.

Checking only that `length()` is equal is **not enough**: two sequences of the same length can still contain different characters. To compare the content of two general `CharSequence`s, you can use `CharSequence.compare(a, b) == 0` in Java 17 (lexicographical comparison by UTF-16 code units), or convert to `String` and compare content when appropriate for performance and purpose. Handle `null` explicitly.

## 7. Designing APIs That Accept `CharSequence`

Suppose you need to extract a short code from a text input. If you only read length, access characters, and extract slices, this signature is sufficiently general:

```java
static String extractCode(CharSequence text, int start, int end) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    if (start < 0 || end < start || end > text.length()) {
        throw new IndexOutOfBoundsException("Invalid range");
    }
    return text.subSequence(start, end).toString();
}
```

This is an **illustrative method** you can place in a Java class. Design decisions:

1. Accept `CharSequence` to allow `String`, `StringBuilder`, and compatible implementations.
2. Intentionally validate the input and slice range; error messages can be tailored to the application's API.
3. Return `String` if the method's contract promises an **immutable text value** rather than a `CharSequence` slice that might reflect changes in the source data.
4. Never assume the parameter's runtime implementation is always `String`. Casting `(String) text.subSequence(...)` can throw `ClassCastException` on implementations that return a `CharBuffer` or another `CharSequence` type.

If an API intentionally returns a **view** to avoid copying, clearly document lifetime, data ownership responsibilities, mutation visibility, and thread safety for the specific implementation. Never promise O(1) performance, zero allocation, or memory isolation for `subSequence` when the source type is unspecified: the interface contract does not enforce those details.

### Example 6: One Method Working with Multiple Implementations

Create the file `GenericSubSequenceDemo.java`:

```java
import java.nio.CharBuffer;

public class GenericSubSequenceDemo {
    static String extractCode(CharSequence text, int start, int end) {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        if (start < 0 || end < start || end > text.length()) {
            throw new IndexOutOfBoundsException("Invalid range");
        }
        return text.subSequence(start, end).toString();
    }

    public static void main(String[] args) {
        String text = "ID-4567";
        StringBuilder builder = new StringBuilder("ID-4567");
        CharBuffer buffer = CharBuffer.wrap("ID-4567".toCharArray());

        System.out.println(extractCode(text, 3, 7));
        System.out.println(extractCode(builder, 3, 7));
        System.out.println(extractCode(buffer, 3, 7));
    }
}
```

```bash
javac GenericSubSequenceDemo.java
java GenericSubSequenceDemo
```

Output:

```text
4567
4567
4567
```

The same `CharSequence.subSequence` contract produces the right character sequence from different input types. **Converting the subsequence to `String`** when returning creates uniform usage, without forcing callers to care about the concrete class implementing `subSequence`.

## 8. Common Mistakes and How to Avoid Them

**Mistake 1 — assuming `end` is included:** `subSequence(1, 3)` takes indices `1` and `2`; it excludes `3`. Verify with length `end - start`.

**Mistake 2 — slicing past bounds:** `subSequence(0, text.length() + 1)` is invalid. If positions are computed from external data, validate boundary conditions and handle exceptions intentionally.

**Mistake 3 — assuming every result is a `String`:** the method's return type is `CharSequence`, and different implementations may return different classes. When a `String` is truly needed, use `toString()` per the contract; do not cast blindly.

**Mistake 4 — assuming every result is a view:** standard `StringBuilder` can return a `String` snapshot. Do not rely on source mutations appearing in the subsequence unless the implementation's contract explicitly states so.

**Mistake 5 — assuming every result is immutable:** `CharBuffer` can return a view sharing mutable data. If you need to keep immutable text, convert it to `String` and define an appropriate synchronization/ownership policy.

**Mistake 6 — confusing length with Unicode code points:** `length()` and `subSequence` indices count UTF-16 code units. When handling emojis or non-BMP characters, compute code point boundaries carefully; grapheme clusters can be even more complex.

**Mistake 7 — using `equals` across `CharSequence` types to conclude two sequences are equal:** there is no general equality contract. Use `String.contentEquals`, `CharSequence.compare`, or convert to `String` when appropriate.

**Mistake 8 — thinking `subSequence` is automatically thread-safe:** the interface provides no such guarantee. If mutable source data is modified by another thread, you must rely on synchronization mechanisms and implementation-specific properties.

**Mistake 9 — using `subSequence` instead of `substring` just because the name sounds “more general”:** when the source type is already `String` and you need a `String`, `substring` is usually more direct and clearer; `subSequence` is useful when programming against the interface.

## 9. Self-Check

### Exercise 1 — half-open bounds

Given `CharSequence s = "spring";`. Predict:

```java
System.out.println(s.subSequence(0, 3));
System.out.println(s.subSequence(3, 6));
System.out.println(s.subSequence(6, 6).isEmpty());
```

Output:

```text
spr
ing
true
```

Index `end` is excluded; the two slices `[0,3)` and `[3,6)` combine to form `spring`. Taking an empty slice at the end position is valid.

### Exercise 2 — is the content stable?

In Java 17:

```java
StringBuilder builder = new StringBuilder("hello");
CharSequence sub = builder.subSequence(1, 4);
builder.replace(1, 4, "XYZ");

System.out.println(builder);
System.out.println(sub);
```

Output:

```text
hXYZo
ell
```

In the standard `StringBuilder` implementation, `subSequence` produces a `String` result of `"ell"` at the time of the call. Do not apply this snapshot assumption to every `CharSequence` implementation.

### Exercise 3 — code points and code units

Given:

```java
String text = "A\uD83D\uDE00B";
System.out.println(text.length());
System.out.println(text.subSequence(1, 3).length());
```

Output:

```text
4
2
```

The slice `subSequence(1, 3)` contains one code point U+1F600 but two UTF-16 code units.

### Exercise 4 — designing a signature

A method needs to accept `String`, `StringBuilder`, and `CharBuffer`, and return an immutable text value. What should be declared?

**Hint:** parameter `CharSequence source`; return type `String`; use `source.subSequence(start, end).toString()` after validating indices. If the input can be mutated concurrently, also specify synchronization and snapshot timing.

## Conclusion

**`subSequence(start, end)` is a contract for reading a slice over a half-open UTF-16 index range `[start, end)` on the `CharSequence` interface.** The contract specifies which characters the subsequence must contain, but does not guarantee the result class, snapshot vs. view semantics, immutability, or execution cost. On `String`, it is equivalent in content to `substring`; on other implementations, rely on their specific characteristics. Proper API design must distinguish **subsequence content**, **return type**, **data ownership**, and **source mutability**.