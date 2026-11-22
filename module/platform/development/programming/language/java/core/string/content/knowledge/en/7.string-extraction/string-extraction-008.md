# Do Not Depend on Whether String Extraction Results Share Objects or Internal Memory

## 1. Goal and Problem to Understand

When calling `String.substring(...)`, what an application is **allowed to rely on** is the **resulting character sequence**, the extracted range, and the immutability of `String`. An application **must not infer** that the result is always a new `String` object, always shares the same object with the source string, always shares the underlying internal array, or always owns a separate memory copy.

This relates directly to **string extraction**. Example:

~~~java
String source = "order:12345";
String id = source.substring(6); // "12345"
~~~

The business logic can assert:

- `id` contains the exact five characters `"12345"`.
- `id.length() == 5`.
- `id.equals("12345")` is `true`.
- Neither `source` nor `id` can have its content altered by “modifying characters inside the String”.

However, you **do not need** and **should not** assert whether `source` and `id` share a `char[]`/`byte[]` array or have specific storage addresses. Those factors belong to JVM/JDK implementation details and optimizations.

After this lesson, you will know how to read the `substring` contract accurately, avoid using `==` for content comparison, distinguish copying/aliasing/immutability, understand memory implications across Java versions, and structure code that stays stable when changing JDKs.

## 2. What Does the `substring` Contract Specify?

Both overloads have a clear **content** contract: `s.substring(begin)` takes from `begin` to the end, and `s.substring(begin, end)` takes `[begin, end)`. With `n = s.length()`, the conditions are `0 <= begin <= n` and `0 <= begin <= end <= n`, respectively; the two-parameter result length is `end - begin` UTF-16 code units. Valid equal bounds return an empty string; invalid ranges throw `IndexOutOfBoundsException`.

```java
String s = "programming";
String prefix = s.substring(0, 7);  // "program"
String suffix = s.substring(7);     // "ming"
String empty = s.substring(7, 7);   // ""
```

These are the **character values** you can rely on. The contract does not require the result to use the same instance, a different instance, a copied array, or a shared array. `String.subSequence(begin, end)` has equivalent content on a `String` object, though its declared return type is `CharSequence`.

## 3. Three Distinct Concepts: Value, Identity, and Backing Storage

**Value:** the sequence of UTF-16 code units of the string. This is what `equals`, `length`, `charAt`, `substring`, and many public APIs work with.

**Identity (object identity):** whether two variables point to the same `String` instance; checked using `==` between two references. This is an object relationship, **not a content relationship**.

**Backing storage:** the internal mechanism the JDK uses to represent characters, such as a byte array paired with an internal encoding coder in some implementations. Two different objects may share internal resources; the same object obviously uses its own internal state. `==` does not tell you whether two different instances share a backing array.

| Question | Appropriate Tool | Program Conclusion |
| --- | --- | --- |
| Do two strings have the **same content**? | `a.equals(b)` | Appropriate for comparing values |
| Do two references point to the same **object**? | `a == b` | Meaningful only when object identity is actually needed |
| Do two objects share a backing array? | No public `String` contract guarantees this | Cannot be inferred from `equals` or `==` |
| Does `substring` retain a large backing buffer? | JDK version analysis, heap profiler, and testing | Base optimization decisions on environment-specific evidence |

Example:

~~~java
String a = new String(new char[] {'a', 'b', 'c'});
String b = new String(new char[] {'a', 'b', 'c'});

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false: two separate new String creations
~~~

The two strings have the same content even though they are distinct objects. Conversely, if an implementation returns `this` when calling `substring(0, length())`, that does not change the **value semantics** of the result. You do not need a separate branch to handle that situation.

### Do Not Treat `==` Results as Proof of Storage Layout

~~~java
String source = "ABCD";
String whole = source.substring(0, source.length());
String half = source.substring(0, 2);

// Do not write business conditions depending on these identity comparisons.
boolean wholeSameObject = (whole == source);
boolean halfSameObject = (half == source);

// Content is defined by the API.
boolean wholeCorrect = whole.equals("ABCD"); // true
boolean halfCorrect = half.equals("AB");     // true
~~~

`wholeSameObject` and `halfSameObject` do not verify whether the extracted data is correct. Nor do they prove whether a buffer was copied or whether a reference to a large buffer is retained.

## 4. Benefit of Immutability: Results Cannot Be Mutated Behind Your Back

`String` is immutable: once created, **that instance's character sequence cannot be modified** through public APIs. Thus an application can pass an extracted `String` to another function without worrying that the function will directly mutate the string's content.

~~~java
String source = "hello-world";
String part = source.substring(6); // "world"

source = "changed";   // reassign variable to a different String
System.out.println(part); // "world"
~~~

The assignment `source = "changed"` only changes the **reference stored in variable `source`**. It does **not** edit the old source instance and does not change `part`. This outcome does not prove `part` has its own memory array: whether data is copied or safely shared, the **public value** stays stable because `String`s are immutable.

For a mutable `char[]` array, `String.toCharArray()` creates a **new array** containing the current characters:

~~~java
String part = "world";
char[] editable = part.toCharArray();
editable[0] = 'W';

System.out.println(new String(editable)); // "World"
System.out.println(part);                 // "world"
~~~

Modifying `editable` only affects the new array. This is an **explicit contract of `toCharArray`**, unlike vague assumptions about internal arrays that `substring` might use.

Even though `StringBuilder` is **mutable**, extracting a `String` result via `substring` captures the value at the time of extraction:

~~~java
StringBuilder builder = new StringBuilder("mutable");
String saved = builder.substring(0, 4); // "muta"

builder.setCharAt(0, 'M');
System.out.println(builder); // "Mutable"
System.out.println(saved);   // "muta"
~~~

Here `saved` is a `String`; subsequent modifications to `builder` do not alter the content of `saved`. That is what business logic needs. You do not need to know how either class manages its internal arrays.

## 5. Java Has Changed String Storage Before — Do Not Make It an API Contract

How `String` is organized has changed across JDK versions:

- **Some older JDKs prior to Java 7u6** implemented `substring` by keeping an offset/length view into the source's large character array. If an application retained a very small slice while dropping the large string, the large array **could** remain retained longer than expected.
- **Modern OpenJDK/JDK releases**, including Java 17, no longer use that offset/count `String` view mechanism. In OpenJDK 17 source code, the `substring(0, length())` branch may return `this` itself; other branches construct the substring representation via the corresponding helper.
- **Java 9 and later** feature *Compact Strings* in common OpenJDK implementations: internal representation may use `byte[]` and a coder flag. Hence modern Java `String`s should not be described as “a `char[]` array”.
- Java may continue changing optimizations, internal data sharing, or allocation strategies. The `java.lang.String` API **does not promise** exact memory footprint, object identity for every `substring` result, or when a specific array can be garbage-collected.

What to preserve when upgrading JDKs: **program logic based on characters and the API**. If the requirement is to reduce memory usage, inspect the implementation details of the **running JDK** and measure under realistic workloads.

### Why Could a Small Slice Involve Large Memory?

Imagine processing a large text record and keeping only a few characters:

~~~java
String largeRecord = loadRecord();
String key = largeRecord.substring(0, 8);
// Subsequent steps only retain key.
~~~

*`loadRecord()` is a hypothetical function; the snippet above illustrates data flow, not a standalone program.*

On an implementation that shares backing arrays, `key` could indirectly retain the large data. On an implementation that copies the subrange, memory retention and copy cost differ. Yet **there is no single allocation rule across all JVMs**, and `key.equals(...)` remains correct on both.

For systems handling large data volumes, inspect heap dumps, allocation profiles, object lifetimes, and representative benchmarks. Avoid adding extra copies simply because you heard `substring` “always shares arrays” or “always allocates its own array”.

## 6. A Runnable and Verifiable Java 17+ Example

File **`SubstringIndependenceDemo.java`**:

~~~java
public class SubstringIndependenceDemo {
    public static void main(String[] args) {
        String source = "prefix:alpha|suffix:omega";

        int start = source.indexOf(':') + 1;
        int end = source.indexOf('|', start);
        String part = source.substring(start, end);
        String other = new String(new char[] {'a', 'l', 'p', 'h', 'a'});

        System.out.println("part=" + part);
        System.out.println("equalContent=" + part.equals(other));
        System.out.println("length=" + part.length());
        System.out.println("prefix=" + source.substring(0, 6));
        System.out.println("empty=" + source.substring(6, 6).isEmpty());

        char[] editableCopy = part.toCharArray();
        editableCopy[0] = 'X';
        System.out.println("arrayFirst=" + editableCopy[0]);
        System.out.println("partAfterArrayEdit=" + part);

        source = "reassigned";
        System.out.println("partAfterSourceReassign=" + part);

        StringBuilder builder = new StringBuilder("mutable");
        String snapshot = builder.substring(0, 4);
        builder.setCharAt(0, 'M');
        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);

        String withEmoji = "A" + Character.toString(0x1F600) + "B";
        int afterTwoCodePoints = withEmoji.offsetByCodePoints(0, 2);
        String prefix = withEmoji.substring(0, afterTwoCodePoints);
        System.out.println("utf16End=" + afterTwoCodePoints);
        System.out.println("prefixCodePoints="
                + prefix.codePointCount(0, prefix.length()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SubstringIndependenceDemo.java
java SubstringIndependenceDemo
~~~

Verified `stdout` output with an actual compiler and JVM:

~~~text
part=alpha
equalContent=true
length=5
prefix=prefix
empty=true
arrayFirst=X
partAfterArrayEdit=alpha
partAfterSourceReassign=alpha
builder=Mutable
snapshot=muta
utf16End=3
prefixCodePoints=2
~~~

Explanation:

1. `substring(start, end)` extracts the characters between `:` and `|`, so `part` is `"alpha"`. `part.equals(other)` is true even though `other` was created via a different constructor.
2. `source.substring(6, 6)` is an empty string because both boundaries are equal. This is a valid result; there is no need to guess whether the `""` instance is reused.
3. Changing `editableCopy[0]` to `'X'` cannot change `part`'s content because `toCharArray` returns a new array.
4. Reassigning `source` to `"reassigned"` does not alter `part`.
5. Changing `StringBuilder`'s content to `"Mutable"` does not alter the snapshot string `"muta"`.
6. `offsetByCodePoints(0, 2)` returns UTF-16 index `3` for the first two code points of `"A😀B"`. `substring(0, 3)` produces a slice with two code points, avoiding cutting mid-surrogate-pair.

Note: the program **does not print the object identity of `substring`**, because identity is not needed to prove any of the desired results above.

## 7. Choosing the Right Comparison in Business Logic

Wrong when the goal is comparing content:

~~~java
String input = getInput();
String token = input.substring(0, 3);

if (token == "ABC") {
    // Wrong: depends on identity of token and literal.
}
~~~

*`getInput()` is an illustrative function, not defined in the snippet; this is not a standalone runnable program.*

Right:

~~~java
String input = "ABC-123";
String token = input.substring(0, 3);

if ("ABC".equals(token)) {
    System.out.println("Matched ABC");
}
~~~

`"ABC".equals(token)` does not depend on whether `token` is interned or shares the same object as the literal. Putting the literal on the left also avoids `NullPointerException` if `token` could be null, although `substring` on a non-null `String` always returns a `String`.

If the problem requires case-insensitive comparison, consider `equalsIgnoreCase` per application semantics; that is a **value comparison** decision, unrelated to object identity. If you need to recognize a specific shared sentinel object owned by the application, `==` may make sense, but that is a completely different contract from “two strings have the same text”.

### Does `intern()` Change the Rules Above?

`String.intern()` returns a canonical representation in the string pool with identity semantics defined by the `intern` API itself. However, **you do not need `intern()` to compare text**; `equals` operates directly on content.

`intern` is also not a universal memory-saving trick for extraction: it affects string pool lifetimes/resources and must be evaluated against data types, cardinality, and actual workload. Do not introduce a dependency on `intern` merely to make `==` happen to evaluate to true.

## 8. Be Careful About Memory and Performance

Several trade-offs cannot be deduced from `substring` syntax alone:

| Practical Question | What Can Be Stated with Certainty | What to Do If It Matters? |
| --- | --- | --- |
| Does extracting 100 characters allocate a 100-character array? | The API does not commit to an allocation strategy | Inspect the JDK and allocation profiler |
| Does retaining a 10-character slice extend the lifetime of a 1 MB buffer? | Depends on storage layout and references | Heap dump, inspect retained size |
| Does `substring(0, length())` return `this`? | Its value equals the source; identity should not be a business condition | Do not branch on `==` |
| Does `new String(existing)` force copying the backing array? | The constructor creates a new `String` object representing the same content, but does not promise a **deep copy** of backing storage | Do not use it to blindly “force buffer release” |
| Does `toCharArray()` create a new array? | **Yes**, per API documentation, containing the string's UTF-16 code units | Use only when you genuinely need an independent, mutable `char[]` |
| Is slicing multiple times faster than keeping offsets? | Depends on usage, memory, and JVM optimizations | Benchmark with the target JDK, data, and real workload |

Do not confuse “not depending on internals” with “not caring about performance”. Business logic should be designed around values; performance optimization is driven by **empirical measurement**. If you must interact with an API requiring a mutable `char[]`, `toCharArray()` has a clear contract. If you only need string content, creating extra copies is usually unnecessary.

## 9. Note Unicode Boundaries When Extracting

Memory layout and immutability do not fix **mis-targeted UTF-16 indices**. For example, `substring(0, 2)` on `"A😀B"` cuts after the high surrogate, whereas getting the first two code points requires converting the boundary with `s.offsetByCodePoints(0, 2)` (returning offset `3`) before calling `substring(0, 3)`.

With combining marks or multi-code-point emojis, consider grapheme cluster boundaries when the product requires “user-visible characters”. That is a matter of **selecting the right character sequence**, independent of the result's identity and backing storage.

## 10. Mental Traps to Avoid

1. **“A `substring` result is definitely a new object.”** Wrong as an assumption portable across all JDKs/calls. A newly extracted value is what the API specifies; identity is another matter.
2. **“`==` between two strings is the only way to tell content is equal.”** Wrong. `==` compares references; `equals` compares content.
3. **“Two strings that are different objects definitely cannot share an array.”** Backing storage cannot be inferred from the identity of two `String`s.
4. **“Because `String` is immutable, the JVM definitely copied the whole buffer.”** Immutability enables many optimization strategies, including safely sharing internal data.
5. **“`new String(s)` always forces a deep copy of the backing array.”** There is no such guarantee from the `String`-copy constructor; for example, OpenJDK 17 can reuse the internal representation.
6. **“Seeing one JDK copy means every JDK copies with identical cost.”** Allocation and representation strategies can change across versions and runtimes.
7. **“Slicing from index 0 to 2 is always two Unicode characters.”** False for supplementary code points; `substring` indices are measured in UTF-16 code units.
8. **“Reassigning the source variable changes the extracted slice.”** Reassigning the source variable does not change the old `String` content or the extracted result.
9. **“Running once and seeing fast/slow timing is enough to conclude.”** No. Benchmarks need warmup, representative loads, multiple samples, and memory observation when results are long-lived.

## 11. Self-Check

**Question 1:** Given `String s = "Java"; String t = s.substring(0, 4);`, should you check `t.equals(s)` or `t == s` if you only care whether the result has the right content?

**Answer:** `t.equals(s)`. Whether `t` is the same instance as `s` is irrelevant to content correctness.

**Question 2:** Why does `char[] copy = extracted.toCharArray(); copy[0] = 'X';` not modify `extracted`?

**Answer:** `toCharArray()` creates a new array; `String` remains immutable.

**Question 3:** If an older JVM shares a backing array between a long source string and a short slice, does business logic need identity checks to protect the content?

**Answer:** No. Whether backing arrays are shared or separate, the `String`'s content remains intact. What may need separate evaluation is **retained heap memory** on that older JVM.

**Question 4:** Is `new String(existing)` a guaranteed way to obtain a completely independent physical copy of the internal array?

**Answer:** No. The constructor may create a new object with the same value, yet backing storage strategy is an implementation detail.

**Question 5:** How do you extract the first two code points from `"A😀B"`?

**Answer:** `int end = s.offsetByCodePoints(0, 2); String first = s.substring(0, end);`. `end` equals `3` in UTF-16 units.

**Question 6:** When extraction performance is abnormal on a specific JDK version, should you change the logic to `==` comparisons, or what should you do?

**Answer:** Keep value-based logic correct; measure allocations, retained size, and profile/benchmark on the specific workload and JDK to identify optimizations.

## 12. References

- [Java SE 17 — `String.substring`, `String.equals`, `String.toCharArray`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): content contract, index bounds, immutability, and `char[]` array copying.
- [Java SE 17 — `StringBuilder.substring`, `setCharAt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `String` results from a mutable source sequence.
- [OpenJDK 17 — `String.java` source](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java): example implementation details that may return `this` for the whole string or construct a result representation for a slice; use only to understand implementation, not as a replacement for the API contract.
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): rationale and techniques for changing `String` memory representation in OpenJDK.

**Key takeaway:** `substring` must produce the **exact requested character sequence**, while object identity and internal memory sharing/copying are not bases for business design. Compare with `equals`, rely on `String` immutability, use appropriate Unicode indices, and draw performance conclusions only after measuring on the actual JDK.