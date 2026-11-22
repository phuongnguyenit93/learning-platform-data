# Comparing the APIs of StringBuffer and StringBuilder in Java

`StringBuffer` and `StringBuilder` are both classes used to **build and edit mutable character sequences**. They share nearly the exact same API: `append`, `insert`, `delete`, `replace`, `reverse`, `charAt`, `setCharAt`, `length`, `capacity`, `substring`, and many Unicode helper methods. The most important design difference is: **`StringBuffer` synchronizes necessary operations on the object itself**, whereas **`StringBuilder` performs no internal synchronization**.

Therefore, in code where only a single thread operates on a string builder, `StringBuilder` is usually the appropriate choice and can avoid synchronization overhead. When a string-building object is genuinely **shared for multiple threads to modify concurrently**, `StringBuffer` may be more suitable because individual operations are synchronized. However, per-call synchronization **does not turn every sequence of multiple calls into an atomic transaction**.

This lesson focuses on comparing **APIs**, usage, return values, performance, and thread-safety limits — rather than treating either class as a replacement for immutable `String` in every case.

## 1. The Big Picture: What Is Similar, What Is Different?

| Criterion | `StringBuilder` | `StringBuffer` |
|---|---|---|
| Purpose | Building/editing mutable character sequences | Building/editing mutable character sequences |
| Modifies content in place? | Yes | Yes |
| Internal method synchronization | No | Yes, for necessary operations on the buffer |
| Use when | Local builder, owned by one thread, or self-managed synchronization | The same buffer is shared and accessed concurrently |
| `append`, `insert`, `delete`, `replace` | Yes | Yes |
| `reverse`, `setCharAt`, `setLength` | Yes | Yes |
| `length`, `capacity`, `ensureCapacity` | Yes | Yes |
| `charAt`, `codePointAt`, `appendCodePoint` | Yes | Yes |
| `substring`, `subSequence`, `indexOf` | Yes | Yes |
| `toString()` | Returns a `String` containing the current content | Returns a `String` containing the current content |
| Return type of `append(...)` | `StringBuilder` | `StringBuffer` |
| Usually preferred when synchronization is not needed | Yes | Less necessary |

Both implement useful interfaces such as `CharSequence` and `Appendable`; neither modifies the content of a previously created `String` object. They are **not subclasses of each other**: you cannot directly cast a `StringBuilder` to a `StringBuffer`, or vice versa.

Although their method names and signatures are similar, synchronization determines which class to choose in multi-threaded programs. `StringBuffer` is not inherently faster, nor is `StringBuilder` inherently wrong in multi-threaded applications: a builder **private to one thread or one call** remains safe without sharing.

## 2. Initialization and Managing length/capacity

Both classes have commonly used creation patterns:

```java
StringBuilder a = new StringBuilder();
StringBuilder b = new StringBuilder(64);
StringBuilder c = new StringBuilder("Java");

StringBuffer x = new StringBuffer();
StringBuffer y = new StringBuffer(64);
StringBuffer z = new StringBuffer("Java");
```

These are **illustrative code snippets**, not a standalone program file. No-argument constructors create an initially empty buffer; constructors taking an `int` set the initial capacity; constructors taking a `String` create a buffer pre-populated with content.

Two easily confused concepts:

- `length()` is **the number of UTF-16 code units currently in the content**.
- `capacity()` is **the code unit capacity the builder can currently hold before needing to expand**, and is always at least `length()`.
- `ensureCapacity(minimumCapacity)` requests a minimum capacity; it **does not add characters** and does not increase `length()`.
- `trimToSize()` requests an attempt to reclaim excess capacity. Do not rely on `capacity()` having to equal `length()` in every implementation after the call.

For example, `new StringBuilder(8)` and `new StringBuffer(8)` both initially have `length() == 0`, `capacity() == 8`. `append("Java")` turns `length()` into 4 without needing to change `capacity()`. Both operate in terms of **UTF-16 code units**, not the number of grapheme clusters or UTF-8 bytes.

### Runnable Example: Constructors, length, and capacity

Save as **`BuilderBufferCapacityDemo.java`**:

```java
public class BuilderBufferCapacityDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(8);
        StringBuffer buffer = new StringBuffer(8);

        builder.append("Java");
        buffer.append("Java");

        System.out.println("builder text: " + builder);
        System.out.println("buffer text: " + buffer);
        System.out.println("builder length: " + builder.length());
        System.out.println("buffer length: " + buffer.length());
        System.out.println("builder capacity: " + builder.capacity());
        System.out.println("buffer capacity: " + buffer.capacity());

        builder.ensureCapacity(8);
        buffer.ensureCapacity(8);
        System.out.println("builder still length 4: "
                + (builder.length() == 4));
        System.out.println("buffer still length 4: "
                + (buffer.length() == 4));
    }
}
```

Run with JDK 17+:

```bash
javac BuilderBufferCapacityDemo.java
java BuilderBufferCapacityDemo
```

**Stdout:**

```text
builder text: Java
buffer text: Java
builder length: 4
buffer length: 4
builder capacity: 8
buffer capacity: 8
builder still length 4: true
buffer still length 4: true
```

In the example, the initial capacity is enough for four characters so `capacity()` remains 8. Do not infer a specific doubling rule for every expansion or every JVM version: the API contract guarantees the required capacity condition, while the allocation strategy is an implementation detail.

## 3. Comparing Common API Groups

### 3.1. Appending Content: `append`

Both have overloads for appending `String`, `char`, integers, floating-point numbers, booleans, `char[]` arrays, `CharSequence`, a portion of a `CharSequence`, and code points. Key point to remember: the overload is selected by the **argument type**, not the author's display intent.

```java
new StringBuilder().append(65);            // "65", not "A"
new StringBuffer().append(65);             // "65", not "A"
new StringBuilder().append('A');           // "A"
new StringBuffer().append('A');            // "A"
new StringBuilder().appendCodePoint(65);   // "A"
new StringBuffer().appendCodePoint(65);    // "A"
```

These are **illustrative expressions**. The `int` value in `append(65)` is converted to decimal digits; to append code point `U+0041`, call `appendCodePoint(65)` or use `char` `'A'` if only an appropriate BMP code unit is needed.

The `append(...)` methods of each class return **the receiver object itself**, allowing a fluent style:

```java
StringBuilder builder = new StringBuilder()
        .append("Hello")
        .append(' ')
        .append("Java");

StringBuffer buffer = new StringBuffer()
        .append("Hello")
        .append(' ')
        .append("Java");
```

### 3.2. Inserting, Deleting, Replacing, and Reversing Content

| Operation | API in Both Classes | How to Understand |
|---|---|---|
| Insert before position | `insert(offset, value)` | Insert at UTF-16 offset |
| Delete range | `delete(start, end)` | Delete range `[start, end)` |
| Delete one code unit | `deleteCharAt(index)` | Delete a single UTF-16 `char` |
| Replace range | `replace(start, end, str)` | Replace range with a new string |
| Reverse content | `reverse()` | Reverse content sequence, with special handling for surrogate pairs |
| Replace one code unit | `setCharAt(index, ch)` | Modify a `char` at an existing position |
| Adjust length | `setLength(newLength)` | Truncate or pad with `'\u0000'` code units |

All offsets in the table above are specified in **UTF-16 code units**. Because of this, `deleteCharAt(i)` or `setCharAt(i, ch)` can break a surrogate pair if the wrong position is chosen with emojis. `reverse()` attempts to keep valid surrogate pairs intact, but does not mean every displayable character cluster containing multiple code points (such as base letters with combining marks) will reverse properly.

### 3.3. Reading Content, Searching, and Slicing Strings

| Task | Corresponding API |
|---|---|
| Read one code unit | `charAt(index)` |
| Read code point at UTF-16 offset | `codePointAt(index)` |
| Read code point before offset | `codePointBefore(index)` |
| Count code points in UTF-16 range | `codePointCount(begin, end)` |
| Move offset by number of code points | `offsetByCodePoints(index, offset)` |
| Copy characters into an array | `getChars(srcBegin, srcEnd, dst, dstBegin)` |
| Find first occurrence | `indexOf(str)`, `indexOf(str, fromIndex)` |
| Find last occurrence | `lastIndexOf(str)`, `lastIndexOf(str, fromIndex)` |
| Extract substring | `substring(start)`, `substring(start, end)` |
| Extract as `CharSequence` | `subSequence(start, end)` |
| Create `String` with current content | `toString()` |

`indexOf` and `lastIndexOf` return `-1` if not found. `substring(start, end)` is valid when `0 <= start <= end <= length()`; the end parameter is **exclusive**. Bounds are not relaxed just because a builder/buffer is mutable.

### 3.4. Operations Returning the Builder/Buffer vs. Another Value?

- `append`, `insert`, `delete`, `deleteCharAt`, `replace`, `reverse`, and `appendCodePoint` generally return **the exact builder type being used**, enabling method chaining.
- `setCharAt`, `setLength`, `ensureCapacity`, and `trimToSize` return `void`; you cannot chain further calls after them.
- `charAt` returns `char`; `codePointAt` returns `int`; `length` and `capacity` return `int`.
- `substring` returns `String`, not `StringBuilder` or `StringBuffer`.
- `toString()` returns `String`, an object with immutable content; modifying the builder afterward does not alter the received content.

These are the return-type differences to know when migrating code from one class to the other: method names stay the same, but receiver types and builder/buffer result types differ.

## 4. Parallel Example Using the Same Sequence of API Calls

Save as **`BuilderBufferApiDemo.java`**:

```java
public class BuilderBufferApiDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        StringBuffer buffer = new StringBuffer("Java");

        builder.append(" Core").insert(4, " 17").delete(4, 7);
        buffer.append(" Core").insert(4, " 17").delete(4, 7);

        builder.replace(5, 9, "SE");
        buffer.replace(5, 9, "SE");

        System.out.println("builder: " + builder);
        System.out.println("buffer: " + buffer);
        System.out.println("same content: "
                + builder.toString().contentEquals(buffer));

        System.out.println("builder first char: " + builder.charAt(0));
        System.out.println("buffer first char: " + buffer.charAt(0));
        System.out.println("builder substring: " + builder.substring(5));
        System.out.println("buffer substring: " + buffer.substring(5));

        builder.setCharAt(0, 'j');
        buffer.setCharAt(0, 'j');
        System.out.println("after setCharAt: "
                + builder + " | " + buffer);
    }
}
```

```bash
javac BuilderBufferApiDemo.java
java BuilderBufferApiDemo
```

**Stdout:**

```text
builder: Java SE
buffer: Java SE
same content: true
builder first char: J
buffer first char: J
builder substring: SE
buffer substring: SE
after setCharAt: java SE | java SE
```

Step-by-step explanation:

1. `append(" Core")` produces `"Java Core"`.
2. `insert(4, " 17")` produces `"Java 17 Core"`, then `delete(4, 7)` removes `" 17"` to return to `"Java Core"`.
3. `replace(5, 9, "SE")` replaces `"Core"` with `"SE"` to yield `"Java SE"`.
4. The methods in both classes interpret positions and content identically.
5. `setCharAt(0, 'j')` modifies one code unit at the beginning, giving `"java SE"`.
6. `contentEquals(buffer)` compares the **`String` content** on the left with the `CharSequence` on the right; the two builders/buffers having different types does not prevent comparing their content via the proper API.

This example is single-threaded sequential execution; it demonstrates **API similarity**, not speed or safety when multiple threads operate concurrently.

## 5. Differences in the Synchronization Contract

Both classes have nearly the same character-building API, but `StringBuffer` synchronizes necessary operations on **the target object's monitor**, while `StringBuilder` provides no built-in locking. When sharing a `StringBuffer`, each `append` or `insert` is individually protected; the ordering between calls from different threads depends on scheduling.

A mutable `CharSequence` argument is **source** state and is not automatically protected by the destination buffer's monitor. If stable source content is needed, control its writers or convert it to an immutable `String` before calling.

```java
StringBuffer shared = new StringBuffer();
shared.append("A"); // First call finishes and releases the monitor.
shared.append("B"); // Another thread can append in between.
```

In multi-threaded code, a local `StringBuilder` remains safe when unshared; there is no rule requiring every multi-threaded program to use `StringBuffer`. The introductory lesson **"The Role of StringBuffer in Code Requiring Synchronization"** has an example observing character counts across multiple threads.

## 6. API Boundaries for Multi-Step Operations

If you want to "append only while under `maxLength`" or "keep three parts of a record contiguous," this is a **multi-step logical operation** that goes beyond the single-method contract. You can lock the entire check–modify region with `synchronized (buffer)`, or build a complete `String record` first and call `buffer.append(record)` once if no other state checks are needed.

Two separate lessons **"Per-Method Synchronization Does Not Guarantee Atomicity for a Sequence of Operations"** and **"Choosing a Shared Lock When Coordinating Multiple Operations"** guide how to reproduce races, identify invariants, and choose a monitor. Here, when comparing APIs, the key takeaway is that **equivalent method names do not mean the synchronization scope across multiple calls is equivalent**.


## 7. Notes on References, `toString`, and `equals`

Both classes are mutable objects, unlike immutable `String`. After calling `toString()`, you have an independent `String` value in terms of content: subsequent edits to the buffer/builder do not change the obtained `String` object.

### Example: Capturing Content into a String

**`BufferSnapshotDemo.java`**

```java
public class BufferSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        StringBuffer buffer = new StringBuffer("A");

        String builderSnapshot = builder.toString();
        String bufferSnapshot = buffer.toString();

        builder.append("B");
        buffer.append("B");

        System.out.println("builder now: " + builder);
        System.out.println("builder snapshot: " + builderSnapshot);
        System.out.println("buffer now: " + buffer);
        System.out.println("buffer snapshot: " + bufferSnapshot);

        System.out.println("builder.equals(new builder): "
                + builder.equals(new StringBuilder("AB")));
        System.out.println("buffer.equals(new buffer): "
                + buffer.equals(new StringBuffer("AB")));
        System.out.println("snapshots equal: "
                + builderSnapshot.equals(bufferSnapshot));
    }
}
```

```bash
javac BufferSnapshotDemo.java
java BufferSnapshotDemo
```

**Stdout:**

```text
builder now: AB
builder snapshot: A
buffer now: AB
buffer snapshot: A
builder.equals(new builder): false
buffer.equals(new buffer): false
snapshots equal: true
```

`StringBuilder` and `StringBuffer` **do not override `Object.equals()` for content comparison**. Two distinct instances, even containing the exact same text, typically evaluate `equals(...) == false`. To compare content:

- Use `builder.toString().equals(buffer.toString())` if you want to snapshot both into two immutable strings and compare them.
- Use `String.contentEquals(CharSequence)` to compare `String` content against a `StringBuilder`/`StringBuffer` via the API.
- If the source is being modified concurrently, you must define an appropriate snapshot and synchronization policy; calling `toString()` twice on two different objects **does not automatically form an atomic snapshot across both**.

Do not use `==` to compare string content: `==` between reference objects asks whether they are the exact same instance.

## 8. Return-Type Differences When Refactoring Code

Both classes have nearly identical method names, but each returns its own specific type in fluent APIs:

```java
StringBuilder sb = new StringBuilder().append("A").reverse();
StringBuffer bf = new StringBuffer().append("A").reverse();
```

If a method is currently written as:

```java
static StringBuilder appendTag(StringBuilder target, String tag) {
    return target.append(tag);
}
```

then you cannot pass a `StringBuffer` in without changing the signature. This is an **illustrative signature snippet**, not a standalone program. You can design the function generically in terms of `Appendable` when only appending is needed without class-specific APIs:

```java
static void appendTag(Appendable target, String tag)
        throws java.io.IOException {
    target.append(tag);
}
```

`Appendable` declares that `append` may throw `IOException`; therefore a generic signature must handle the checked exception on the interface, even though the concrete implementations `StringBuilder` and `StringBuffer` do not throw `IOException` in their corresponding overloads. Switching to `Appendable` also loses direct access to `delete`, `capacity`, `reverse`, or `setCharAt` because those methods do not belong to the interface.

If you only need to **read** a character sequence, `CharSequence` is a better interface; however, a mutable `CharSequence` can still change after being passed into a method, so do not treat it as implicitly immutable.

### Generic Example via `Appendable`

**`AppendableCompatibilityDemo.java`**

```java
import java.io.IOException;

public class AppendableCompatibilityDemo {
    private static void addLabel(Appendable out, String value)
            throws IOException {
        out.append('[').append(value).append(']');
    }

    public static void main(String[] args) throws IOException {
        StringBuilder builder = new StringBuilder();
        StringBuffer buffer = new StringBuffer();

        addLabel(builder, "A");
        addLabel(buffer, "A");

        System.out.println(builder.toString());
        System.out.println(buffer.toString());
    }
}
```

```bash
javac AppendableCompatibilityDemo.java
java AppendableCompatibilityDemo
```

**Stdout:**

```text
[A]
[A]
```

Using an interface keeps source code independent of a concrete class when only shared functionality is needed. However, **it does not determine thread-safety**: if the input is a `StringBuilder` shared across threads, calling through `Appendable` does not make that builder automatically synchronized.

## 9. Unicode and Indexing: Both Classes Share the Same Risks

Because both store content with UTF-16 semantics:

- `length()` and the indices in `charAt`, `insert`, `delete`, `replace`, and `substring` all operate in **UTF-16 code units**.
- `appendCodePoint(int)` is the API for adding a code point, which may produce **one** code unit in the BMP or **two** code units outside the BMP.
- `codePointAt` and `codePointCount` help process data by Unicode code points, but do not count **grapheme clusters**.
- `deleteCharAt` can split a surrogate pair in half; boundaries must be chosen using `offsetByCodePoints` or a grapheme segmentation tool if the goal is user-perceived characters.
- `reverse()` handles surrogate pairs, but does not guarantee properly reversing character clusters containing multiple code points.

**`BuilderBufferUnicodeDemo.java`**

```java
public class BuilderBufferUnicodeDemo {
    public static void main(String[] args) {
        int smile = 0x1F60A;

        StringBuilder builder = new StringBuilder()
                .appendCodePoint(smile).append('A');
        StringBuffer buffer = new StringBuffer()
                .appendCodePoint(smile).append('A');

        System.out.println("builder units: " + builder.length());
        System.out.println("buffer units: " + buffer.length());
        System.out.println("builder points: "
                + builder.codePointCount(0, builder.length()));
        System.out.println("buffer points: "
                + buffer.codePointCount(0, buffer.length()));

        System.out.println("same Unicode content: "
                + builder.toString().contentEquals(buffer));

        System.out.printf("builder first code point: U+%X%n",
                builder.codePointAt(0));
        System.out.printf("buffer first code point: U+%X%n",
                buffer.codePointAt(0));
    }
}
```

```bash
javac BuilderBufferUnicodeDemo.java
java BuilderBufferUnicodeDemo
```

**Stdout:**

```text
builder units: 3
buffer units: 3
builder points: 2
buffer points: 2
same Unicode content: true
builder first code point: U+1F60A
buffer first code point: U+1F60A
```

When adding the emoji 😊 (a supplementary code point) and the letter `A` (a BMP code point), each builder contains **3 UTF-16 code units** yet only **2 code points**. Both classes produce identical results. `StringBuffer` synchronizing its methods does not automatically fix Unicode logic bugs if the program picks wrong cut points.

## 10. Performance Follows How the API Is Used

`StringBuilder` avoids internal synchronization when only one thread owns the builder; `StringBuffer` adds monitor coordination when protecting a shared buffer. Still, a simple measurement is not enough to assert a fixed ratio of difference, because results depend on the JDK/JIT, allocation, capacity, and lock contention.

Choose based on **instance ownership and program correctness** first. When optimization is needed, compare two alternatives with identical semantics; consider building parts locally and appending in batches to reduce how often threads enter the monitor. The lesson **"Synchronization Cost and When StringBuffer Is Truly Needed"** guides JMH benchmark design and contention analysis.


## 11. Common Mistakes When Comparing APIs

| Misconception | Actual Issue | Correct Understanding |
|---|---|---|
| "StringBuffer and StringBuilder have the same content so `equals` returns true" | Neither class overrides `equals` to compare content | Use `toString().equals(...)` or `String.contentEquals(...)` |
| "StringBuffer guarantees a check-then-append block is atomic" | Separate calls do not form a multi-step transaction | Use a shared lock protecting the entire invariant |
| "Only single-threaded applications may use StringBuilder" | Local unshared builders remain safe in multi-threaded applications | Consider **instance ownership**, not just thread count of the application |
| "`append(int)` appends a Unicode code point" | `append(int)` appends the decimal representation of the number | Use `appendCodePoint(int)` |
| "`length()` counts visible characters" | UTF-16 has surrogate pairs; a grapheme may contain multiple code points | Distinguish units, points, and clusters |
| "`capacity()` is the number of added elements" | Capacity is storage room, not length | Use `length()` to find the current number of code units |
| "`substring` returns a new builder" | It returns a `String` | Create a new `StringBuilder`/`StringBuffer` if further edits are needed |
| "You can cast StringBuilder ↔ StringBuffer" | There is no inheritance relationship between the two classes | Create a new object from the content, or design around interfaces |
| "`toString()` will reflect all future changes" | The resulting `String` is immutable | Capture `toString()` again if a fresh snapshot is needed |
| "Declaring an `Appendable` parameter makes everything thread-safe" | Thread-safety still depends on the instance and synchronization policy | Control sharing and ownership |
| "All methods with the same name behave 100% identically in parameters and results" | Fluent return types are the specific builder type; JDK APIs can evolve | Check signatures and the application's JDK version |

## 12. Self-Check Knowledge Test

Before running, predict the stdout:

**`BuilderBufferSelfCheck.java`**

```java
public class BuilderBufferSelfCheck {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("ab");
        StringBuffer buffer = new StringBuffer("ab");

        builder.append('c').reverse();
        buffer.append('c').reverse();

        System.out.println(builder);
        System.out.println(buffer);
        System.out.println(builder.length() == buffer.length());
        System.out.println(builder.toString().equals(buffer.toString()));

        String snapshot = buffer.toString();
        buffer.append('!');
        System.out.println(snapshot);
        System.out.println(buffer);

        System.out.println(new StringBuffer("ab")
                .equals(new StringBuffer("ab")));
    }
}
```

```bash
javac BuilderBufferSelfCheck.java
java BuilderBufferSelfCheck
```

**Stdout:**

```text
cba
cba
true
true
cba
cba!
false
```

- `append('c')` appends `c` to `"ab"`, then `reverse()` produces `"cba"` in each object.
- Both objects contain the same content and length, but comparing via `toString().equals(...)` is what compares **text value**.
- `snapshot` stays `"cba"` after the buffer changes to `"cba!"`, because it is an immutable `String`.
- The two `new StringBuffer("ab")` objects are distinct instances; `equals` has no custom content comparison, so it returns `false`.

**Three deciding questions when writing code:**

1. Is the string-building object **shared** across threads, or owned individually by each thread?
2. Is the requirement only independent calls (`append`, `insert`, `delete`), or is there a **multi-step invariant** needing atomic protection?
3. Is the goal handling **character content**, **UTF-16 offsets**, or **object references**? Have `equals`/`contentEquals`/`substring` been chosen appropriately?

**Conclusion:** `StringBuilder` and `StringBuffer` are nearly equivalent in string-building operations, but differ in synchronization mechanisms. Choose `StringBuilder` for builders not shared concurrently; choose `StringBuffer` or another synchronization mechanism when genuine shared access exists, and additionally protect multi-step operations if business rules require it. Whichever class you use, always distinguish content from reference, length from capacity, and code units from code points to get correct results.
