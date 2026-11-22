# StringBuilder: Constructors, length, and capacity in Java

`StringBuilder` is a Java class used to **build and modify character strings** through operations such as `append()`, `insert()`, and `delete()`. Unlike an immutable `String`, a `StringBuilder` modifies the content of the object itself directly. To use it properly, you must distinguish between **content length** and **reserved capacity**:

- **`length()`:** the number of UTF-16 code units currently in the content.
- **`capacity()`:** the number of UTF-16 code units the builder can hold before having to expand its backing storage.

A builder can be completely empty (`length() == 0`) yet still have `capacity() == 100`. This **does not mean** it contains 100 spaces, nor does it mean you can access `charAt(99)`. Only positions from `0` to `length() - 1` belong to the current content.

## 1. Why Use StringBuilder?

When repeatedly creating new strings with `String` concatenation inside a loop, a program may have to create many intermediate objects. `StringBuilder` lets you accumulate text through a single mutable object:

~~~java
StringBuilder builder = new StringBuilder();
builder.append("Java");
builder.append(' ');
builder.append(17);

String result = builder.toString();
System.out.println(result); // Java 17
~~~

This is an **illustrative code snippet**, placed inside a Java method. `append(17)` appends the digit representation of the integer. `toString()` creates a `String` representing the current content. Even if you continue modifying `builder`, the existing `result` value does not change along with it.

The `StringBuilder` class does not automatically synchronize when multiple threads operate on the same object concurrently. In cases where content is built locally on a single thread, it is a convenient and usually efficient tool.

## 2. Four Commonly Used Constructors

| Constructor | Initial Content | Initial Length | Initial Capacity |
| --- | --- | ---: | ---: |
| `new StringBuilder()` | Empty string | 0 | **16** |
| `new StringBuilder(int capacity)` | Empty string | 0 | **capacity** |
| `new StringBuilder(String str)` | Content of `str` | `str.length()` | **`str.length() + 16`** |
| `new StringBuilder(CharSequence seq)` | Content of `seq` | `seq.length()` | **`seq.length() + 16`** |

All lengths and capacities in this table are measured in **UTF-16 code units**, not UTF-8 bytes or Unicode code points.

### 2.1. new StringBuilder(): Default Capacity of 16

~~~java
StringBuilder a = new StringBuilder();
System.out.println(a.length());   // 0
System.out.println(a.capacity()); // 16
System.out.println(a.toString().isEmpty()); // true
~~~

Sixteen units are reserved space, not existing characters. `a.charAt(0)` still throws `StringIndexOutOfBoundsException` because the length is 0.

### 2.2. new StringBuilder(int): Proactively Reserving Space

~~~java
StringBuilder b = new StringBuilder(5);
System.out.println(b.length());   // 0
System.out.println(b.capacity()); // 5

b.append("Hi");
System.out.println(b.length());   // 2
System.out.println(b.capacity()); // 5
~~~

Reserving 5 units lets you append "Hi" (two UTF-16 code units) without expanding. Using `new StringBuilder(0)` is completely valid: both initial length and capacity are 0; when you append a character, the builder grows capacity as needed.

If capacity is negative, the constructor throws `NegativeArraySizeException`:

~~~java
new StringBuilder(-1); // throws NegativeArraySizeException
~~~

This is an **illustrative exception line**, not a standalone program. Passing an excessively large capacity can fail due to memory limits; do not reserve unbounded capacity just to be "safe".

### 2.3. new StringBuilder(String): Initializing with Content

~~~java
StringBuilder c = new StringBuilder("Java");
System.out.println(c.length());   // 4
System.out.println(c.capacity()); // 20
System.out.println(c.toString()); // Java
~~~

Here the content already has four UTF-16 code units, so length = 4 and capacity = 4 + 16 = 20. Compare:

~~~java
StringBuilder fromNumber = new StringBuilder(20);
StringBuilder fromText = new StringBuilder("20");

System.out.println(fromNumber.length());   // 0
System.out.println(fromNumber.capacity()); // 20
System.out.println(fromText.length());     // 2
System.out.println(fromText.capacity());   // 18
~~~

The two constructors have **completely different** meanings: the integer is *capacity*, whereas the string is *content*. The `String` constructor requires a non-null argument; `new StringBuilder((String) null)` throws `NullPointerException`.

### 2.4. new StringBuilder(CharSequence): Initializing from a Text Interface

`CharSequence` is the common interface for `String`, `StringBuilder`, `StringBuffer`, and other types that provide character sequences.

~~~java
CharSequence source = "ABC";
StringBuilder d = new StringBuilder(source);
System.out.println(d.length());   // 3
System.out.println(d.capacity()); // 19
System.out.println(d.toString()); // ABC
~~~

The new object receives the content from the source with capacity = `seq.length() + 16`. The `CharSequence` constructor also requires a non-null argument. If you call `new StringBuilder("ABC")` directly with a `String` literal, the compiler selects the more specific `String` overload, though the resulting initial length/capacity in this case is still 3/19.

## 3. length() and capacity(): Understanding via Diagram

Example:

~~~java
StringBuilder sb = new StringBuilder(8);
sb.append("Cat");
~~~

~~~text
Content:              C  a  t
UTF-16 offset:        0  1  2
                  +--+--+--+--+--+--+--+--+
Capacity (8 unit) | C| a| t|  |  |  |  |  |
                  +--+--+--+--+--+--+--+--+

length()   = 3
capacity() = 8
~~~

The diagram illustrates **API capacity**, not actual RAM byte layout. The remaining five slots do not yet belong to the content. Therefore:

- `sb.charAt(0)`, `sb.charAt(1)`, and `sb.charAt(2)` are valid.
- `sb.charAt(3)` is **invalid**, even though capacity is 8.
- `sb.toString()` produces `"Cat"`, not `"Cat     "`.

The invariant that must always hold in a valid state:

~~~text
0 <= length() <= capacity()
~~~

`capacity() - length()` is the **unused capacity in UTF-16 code units**. It is not the number of visible characters you can still add, because many emojis occupy two UTF-16 code units.

## 4. append() and Capacity Expansion Rules

`append()` increases length according to the amount of text added; capacity increases only if the reserved buffer is insufficient.

~~~java
StringBuilder sb = new StringBuilder(3);
sb.append("AB");
System.out.println(sb.length());    // 2
System.out.println(sb.capacity());  // 3

sb.append("CDE");
System.out.println(sb.length());    // 5
System.out.println(sb.capacity() >= 5); // true
System.out.println(sb.toString());  // ABCDE
~~~

After the second append call, 5 UTF-16 units exceed the initial capacity of 3, so the builder must increase its capacity. The new capacity may be **larger than** the current length so that subsequent appends do not have to reallocate repeatedly.

In Java implementations, you may observe a growth strategy related to `2 * oldCapacity + 2`, but **you should not write business logic or tests that depend on the exact capacity number after automatic growth**. What matters is that capacity remains sufficient and the content is preserved.

### Pre-Reserving with a Reasonable Estimate

~~~java
int estimatedUnits = 1000;
StringBuilder out = new StringBuilder(estimatedUnits);
for (int i = 0; i < 100; i++) {
    out.append("item=").append(i).append(';');
}
String result = out.toString();
~~~

This is an **illustrative snippet placed inside a method**. When you can estimate the output size in UTF-16 units, reserving an appropriate capacity can reduce the number of buffer expansions. However, overestimating too much can also waste memory. Optimize only after understanding the data scale and measuring performance when necessary.

## 5. ensureCapacity(): Ensuring Storage Without Adding Content

`ensureCapacity(int minimumCapacity)` requests at least `minimumCapacity` units of capacity, expanding capacity if needed. This method **does not insert characters**, does not set a new length, and does not erase existing content.

~~~java
StringBuilder sb = new StringBuilder(3);
sb.ensureCapacity(20);

System.out.println(sb.length());          // 0
System.out.println(sb.capacity() >= 20);  // true

sb.append("Hello");
System.out.println(sb.length());          // 5
System.out.println(sb.capacity() >= 20);  // true
~~~

**Things to remember:**

1. If the current capacity is already sufficient, the call does not need to expand storage.
2. For `minimumCapacity <= 0`, the call does not increase capacity.
3. For larger requests, the builder expands capacity enough to hold it, within JVM allocation limits.
4. `ensureCapacity(20)` **does not guarantee capacity equals exactly 20**, only **at least 20** when successful.
5. `ensureCapacity(20)` is completely **different from** `setLength(20)`.

## 6. setLength(): Changing Content Length

`setLength(int newLength)` sets a **new length** for the builder, unlike `ensureCapacity()`:

- If `newLength < length()`, the content is **truncated from the end**.
- If `newLength == length()`, the length remains unchanged.
- If `newLength > length()`, the new positions are added to the content with the **NUL character, `'\u0000'`**, not spaces.
- If the new length exceeds capacity, the builder can automatically expand capacity.
- If `newLength < 0`, the method throws `IndexOutOfBoundsException`.

Example:

~~~java
StringBuilder sb = new StringBuilder(8);
sb.append("Cat");
sb.setLength(5);

System.out.println(sb.length());        // 5
System.out.println(sb.capacity());      // 8
System.out.println((int) sb.charAt(3)); // 0
System.out.println((int) sb.charAt(4)); // 0

sb.setLength(2);
System.out.println(sb.toString());      // Ca
System.out.println(sb.length());        // 2
System.out.println(sb.capacity());      // 8
~~~

This is an **illustrative code snippet placed inside a method**. The two new elements already belong to the content after `setLength(5)`, but they are NUL and may not be visible when printed directly. Do not use `setLength()` just to "reserve blank space" if you do not want to add actual characters to the string.

### Clearing Content with setLength(0)

~~~java
StringBuilder sb = new StringBuilder(32);
sb.append("first");
sb.setLength(0);
sb.append("second");
System.out.println(sb.toString()); // second
~~~

`setLength(0)` makes the builder empty in terms of **logical content**, allowing the already-allocated capacity to be reused in sequential loops. This statement is not a secure way to wipe sensitive data from JVM memory; you cannot infer from length that old data has been overwritten at the storage layer.

**Unicode warning:** because length counts UTF-16 code units, truncating with `setLength()` in the middle of a surrogate pair can leave an unpaired surrogate; when you need to truncate by Unicode code point or visible character, find the appropriate boundary first.

## 7. trimToSize(): Requesting to Trim Excess Capacity

`trimToSize()` asks the builder to try reducing its reserved buffer if possible. It **does not** change the content or length.

~~~java
StringBuilder sb = new StringBuilder(100);
sb.append("Java");

System.out.println(sb.length());   // 4
System.out.println(sb.capacity()); // 100

sb.trimToSize();

System.out.println(sb.length());   // 4
System.out.println(sb.capacity() >= sb.length()); // true
System.out.println(sb.toString()); // Java
~~~

**Never assume** `sb.capacity() == 4` after `trimToSize()`. The API allows an implementation not to reduce capacity, or to reduce it without matching the exact length. Therefore, `trimToSize()` is not suitable for writing tests based on exact memory savings. Trimming and then appending a lot again can trigger new allocations, so use it only when you have a clear reason based on the builder's lifecycle.

| Method | Changes length? | Can change capacity? | Effect on content |
| --- | --- | --- | --- |
| `append(...)` | Can increase | Can increase | Appends new part |
| `insert(...)` | Can increase | Can increase | Inserts new part |
| `delete(...)` | Decreases if deleted range is non-empty | Does not need to decrease | Removes part |
| `ensureCapacity(n)` | **No** | Can increase | Preserves content |
| `setLength(n)` | **Yes** if different from old length | Can increase | Truncates or pads with NUL |
| `trimToSize()` | **No** | Can decrease | Preserves content |
| `toString()` | **No** | Does not change builder | Returns resulting `String` |

## 8. UTF-16: length and capacity Are Not Code Point Counts

In Unicode, a code point outside the BMP such as the emoji `😀` takes two UTF-16 units:

~~~java
StringBuilder emoji = new StringBuilder("A😀");
System.out.println(emoji.length()); // 3
System.out.println(emoji.codePointCount(0, emoji.length())); // 2
System.out.println(emoji.capacity()); // 19
~~~

The string `"A😀"` has **2 Unicode code points** but is **3 UTF-16 code units** long: one for A and two for the emoji. The `String` constructor initializes capacity = `3 + 16 = 19`. Therefore:

- Do not treat `length()` as the number of "letters" the user sees.
- Do not calculate capacity in UTF-8 file bytes.
- Do not treat capacity as RAM bytes; internal storage layout and object overhead depend on the JVM.
- If you need to count code points, use `codePointCount(0, length())`; if you want to append a whole code point, use `appendCodePoint(int)`.

A displayed grapheme cluster can even consist of **multiple code points** (base letter + combining marks, composite emojis). If an application limits length in the UI, choose the measurement unit according to the requirements rather than defaulting to length or capacity.

## 9. Complete Java 17+ Program

Save this code to the file **StringBuilderCapacityDemo.java**:

~~~java
public class StringBuilderCapacityDemo {
    public static void main(String[] args) {
        StringBuilder empty = new StringBuilder();
        StringBuilder reserved = new StringBuilder(5);
        StringBuilder fromString = new StringBuilder("Java");
        StringBuilder fromSequence = new StringBuilder(
                (CharSequence) "ABC");

        System.out.println("empty length/capacity = "
                + empty.length() + "/" + empty.capacity());
        System.out.println("reserved length/capacity = "
                + reserved.length() + "/" + reserved.capacity());
        System.out.println("String length/capacity = "
                + fromString.length() + "/" + fromString.capacity());
        System.out.println("CharSequence length/capacity = "
                + fromSequence.length() + "/" + fromSequence.capacity());

        reserved.append("Hi");
        System.out.println("after append length/capacity = "
                + reserved.length() + "/" + reserved.capacity());

        StringBuilder grown = new StringBuilder(3);
        grown.ensureCapacity(20);
        System.out.println("ensure length = " + grown.length());
        System.out.println("ensure capacity >= 20 = "
                + (grown.capacity() >= 20));

        grown.append("ABCDE");
        System.out.println("append length = " + grown.length());
        grown.setLength(7);
        System.out.println("extended length = " + grown.length());
        System.out.println("added char code = " + (int) grown.charAt(5));

        grown.setLength(2);
        System.out.println("shrunk content = " + grown);
        System.out.println("shrunk capacity >= 20 = "
                + (grown.capacity() >= 20));

        StringBuilder emoji = new StringBuilder("A😀");
        System.out.println("emoji UTF-16 length = " + emoji.length());
        System.out.println("emoji code points = "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("emoji initial capacity = "
                + emoji.capacity());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 StringBuilderCapacityDemo.java
java StringBuilderCapacityDemo
~~~

**Stdout output:**

~~~text
empty length/capacity = 0/16
reserved length/capacity = 0/5
String length/capacity = 4/20
CharSequence length/capacity = 3/19
after append length/capacity = 2/5
ensure length = 0
ensure capacity >= 20 = true
append length = 5
extended length = 7
added char code = 0
shrunk content = AB
shrunk capacity >= 20 = true
emoji UTF-16 length = 3
emoji code points = 2
emoji initial capacity = 19
~~~

**Analysis:** Both empty constructors give length 0 but different capacities. The text constructors give length equal to the text length and capacity plus 16. `ensureCapacity(20)` adds no characters; `append()` increases length; `setLength(7)` pads with NUL; `setLength(2)` truncates content to `AB`. The emoji shows that the API measures in UTF-16. The program uses `>=` checks where an exact capacity after auto-growth should not be assumed.

## 10. Common Mistakes to Avoid

| Wrong Understanding / Practice | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| `new StringBuilder(100)` creates 100 spaces | The argument is capacity; the builder is still empty | Use `append` if you want to create content |
| `capacity()` is the number of written characters | Capacity is reserved space, not length | Call `length()` for content |
| If spare capacity exists, `charAt(length())` is valid | Indices are bounded by length | `0 <= index < length()` |
| `ensureCapacity(n)` sets length to n | It only reserves space | Use `setLength(n)` when you truly want to change content length |
| `setLength(n)` only allocates without adding characters | If n increases, NUL characters are added | Use `ensureCapacity(n)` to reserve space |
| `setLength(0)` definitely frees memory | Length becomes 0, but capacity may remain unchanged | Do not use length to infer RAM usage |
| `trimToSize()` always sets capacity equal to length | The API does not promise shrinking to an exact size | Do not assert exact capacity values after trimming |
| Guessing the capacity growth formula for logic | Growth/implementation details may change | Rely on the minimum guarantees of the API |
| `new StringBuilder(-1)` is valid | Negative capacity is invalid | Validate parameters |
| `new StringBuilder(10)` and `new StringBuilder("10")` are the same | One sets reserved space, the other sets content | Choose the right overload |
| `length()` equals the number of emojis | Non-BMP emojis take two code units | Use code point APIs as required |
| Capacity 100 means 200 bytes of RAM | JVM internal structure is not described by capacity | Do not use capacity as a RAM meter |
| Sharing a builder across threads without locking | `StringBuilder` is not synchronized by default | Restrict access / synchronize appropriately |

## 11. Practice Checklist

1. **Is the input content or an estimated capacity?** If it is content, use the constructor taking `String`/`CharSequence`; if only reserving space, use the constructor taking `int`.
2. **Which unit is being counted?** Both capacity and length are counted in UTF-16 code units, not UTF-8 bytes or code points.
3. **Do you need to optimize the number of capacity expansions?** Choose an initial value or `ensureCapacity()` based on a reasonable estimate, without exceeding actual needs by too much.
4. **Did you distinguish ensureCapacity and setLength?** One only reserves space; the other changes the content itself and may add NULs.
5. **Did you check for exceptions?** Avoid negative capacity, huge allocations, and indices outside `length()`.
6. **Are you depending on exact capacity after append/trim?** If so, reconsider; it is better to check only actual API guarantees.
7. **Is there Unicode data?** Avoid interpreting length/capacity as the number of user-perceived characters.
8. **Is it shared across threads?** Ensure an appropriate synchronization policy or use a local builder.

## 12. Self-Check Questions

**Question 1.** For `StringBuilder b = new StringBuilder(4); b.append("ab");`, what are `length()` and `capacity()`?

**Answer:** length = 2, capacity = 4.

**Question 2.** What are the initial length and capacity of `new StringBuilder("abc")`?

**Answer:** length = 3 and capacity = 19, because the `String` constructor uses `str.length() + 16`.

**Question 3.** After `StringBuilder b = new StringBuilder(8); b.ensureCapacity(50);`, which conditions must hold when the call succeeds?

**Answer:** `b.length() == 0` and `b.capacity() >= 50`. `capacity() == 50` is not required.

**Question 4.** Given `b = new StringBuilder("AB"); b.setLength(4);`, what is in the two added positions?

**Answer:** two NUL characters `'\u0000'`, not spaces. They are part of the logical content.

**Question 5.** What are the length and initial capacity of `new StringBuilder("😀")`?

**Answer:** length = 2 UTF-16 code units; capacity = 18.

**Question 6.** Why shouldn't you assert `b.capacity() == b.length()` after `trimToSize()`?

**Answer:** the API allows trimming not to reduce capacity or not to shrink it down to the exact length. Content is unaffected whether capacity decreases or not.

**Question 7.** In a loop that builds strings many times, when should you use `new StringBuilder(estimated)`?

**Answer:** when you have a reasonably reliable estimate of the UTF-16 code unit count and pre-reserving brings practical benefit. Avoid overly large estimates that waste memory.

## References

- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): constructors, `length()`, `capacity()`, `ensureCapacity()`, `setLength()`, `trimToSize()`, and mutation methods.
- [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html): input source interface for the `CharSequence` constructor.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutable string type, UTF-16 length, and code point operations.
