# Mutable Source Objects During `StringBuffer.append()` or `insert()`

## 1. The Problem: Source Data Can Change

`StringBuffer` stores a **mutable** character sequence and supports building strings with `append()`, `insert()`, `delete()`, `replace()`, `setCharAt()`, and other methods. Many overloads of `append()` and `insert()` accept data from a `CharSequence` or another `StringBuffer`. Those source types can change over time.

There are two situations to distinguish:

1. **The source changes before or after each call:** the result copied into the destination is based on the source's content at the time it is read. The characters copied to the destination are **its own data**, not a "live link" that automatically updates with the source.
2. **The source is modified concurrently at the exact moment it is being copied:** especially when the source is a `StringBuilder` or a custom `CharSequence`, do not assume that reading `length()` and then reading various `charAt()` positions forms an atomic snapshot. Thread coordination or capturing a stable snapshot is required.

Sequential example with deterministic output:

~~~java
StringBuffer source = new StringBuffer("A");
StringBuffer target = new StringBuffer("Result:");

target.append(source);
source.append("B");
target.append(source);

System.out.println(target); // Result:AAB
System.out.println(source); // AB
~~~

The first append adds `"A"`; afterward the source becomes `"AB"`, so the next append adds `"AB"`. The first part **does not turn into** `"AB"` just because the source changed. This is a character-copying mechanism, **not a shared view**.

## 2. Related Data Types and Overloads

`StringBuffer` implements `CharSequence`, so it accepts content from many source types:

| Call form | Meaning |
|---|---|
| `dest.append(String)` | Appends characters of an immutable String to the end |
| `dest.append(StringBuffer)` | Appends characters from a source StringBuffer |
| `dest.append(CharSequence)` | Appends the entire character sequence provided by CharSequence |
| `dest.append(CharSequence, start, end)` | Appends the portion within `[start, end)` of the source |
| `dest.insert(offset, String)` | Inserts a String at `offset` in the destination |
| `dest.insert(offset, CharSequence)` | Inserts CharSequence content into the destination |
| `dest.insert(offset, CharSequence, start, end)` | Inserts a segment `[start, end)` of the source |
| `dest.append(Object)` | Converts the object to a string via `String.valueOf`/`toString()`, then appends |

These are representative call forms, **not a list of all overloads** (there are also integers, characters, booleans, char arrays, etc.).

`String` is **immutable**; its content does not change after creation. `StringBuilder` and `StringBuffer` are **mutable**. `CharSequence` is only an interface representing a character sequence; it **promises neither immutability nor thread-safety**.

Example of passing a `StringBuilder` to `StringBuffer` under the `CharSequence` type:

~~~java
StringBuilder source = new StringBuilder("cat");
StringBuffer target = new StringBuffer();

target.append((CharSequence) source); // copies "cat"
source.setCharAt(0, 'b');             // source is now "bat"
target.insert(0, (CharSequence) source);

System.out.println(source); // bat
System.out.println(target); // batcat
~~~

The result `"batcat"` consists of `"bat"` inserted afterward and `"cat"` copied earlier. There is no automatic value synchronization between the two builders.

## 3. `append()`: Appending Content Read from Source to the End of Destination

### 3.1. Appending the Entire Source Content

When using `append(source)`, the destination gains the source's content. Once the call completes without concurrent race activity, modifying the source does not alter the already appended segment.

~~~java
StringBuffer source = new StringBuffer("red");
StringBuffer target = new StringBuffer("color=");
target.append(source);
source.replace(0, 3, "blue");

System.out.println(source); // blue
System.out.println(target); // color=red
~~~

Similarly, modifying `target` afterward does not modify `source` in return. Both objects maintain independent state.

**Point to avoid:** do not infer that `append(source)` always creates a specific intermediate `String` object in every JDK version. The API specifies the **content result**, while storage/copying optimizations may vary by implementation.

### 3.2. Appending Part of the Source: `start` Is Measured on the Source

With `append(CharSequence s, int start, int end)`, the range `[start, end)` is taken by **UTF-16 code unit indices of the source**, inclusive at start and exclusive at end.

~~~java
StringBuilder source = new StringBuilder("ABCDEFG");
StringBuffer target = new StringBuffer("part=");
target.append(source, 2, 5);

System.out.println(target); // part=CDE
source.setCharAt(2, 'X');
System.out.println(source); // ABXDEFG
System.out.println(target); // part=CDE
~~~

Here indices 2, 3, 4 are `CDE`. The `setCharAt(2, 'X')` statement on the source occurs **after the append** and does not alter the copied part.

Index constraints:

- `start` must not be negative.
- `end` must not be less than `start`.
- `end` must not exceed the valid source length at the time of application.
- If the range is invalid, the method throws an exception per the API contract (e.g., `IndexOutOfBoundsException`); it must not be assumed to "auto-clamp to the end."

**Warning:** if the source's size changes between when the program determines `start/end` and the copy call, indices that used to be valid can become invalid. With a source modified concurrently, never separately call `length()`, calculate indices, and then `append(...)` without a synchronization protocol.

### 3.3. Overload Selection and Semantics

In Java, the compiler selects an overload based on the **declared type at the call site**. Example:

~~~java
StringBuffer source = new StringBuffer("X");
CharSequence chars = source;

StringBuffer a = new StringBuffer();
a.append(source); // overload matching StringBuffer
a.append(chars);  // CharSequence overload

System.out.println(a); // XX
~~~

In terms of intent, both append text content. However, do not rely on a specific optimization or internal locking level across all overloads, all JDK versions, or all `CharSequence` source types. When correctness requires a clearly explainable snapshot, **proactively capture an immutable `String`** at a synchronized point.

## 4. `insert()`: Source and Insertion Position Use Two Coordinate Systems

`insert()` is similar to `append()` in taking characters from a source, but places that segment at **a position inside the destination**, shifting the destination's tail to the right.

~~~java
StringBuilder source = new StringBuilder("ABCDE");
StringBuffer target = new StringBuffer("[]");

target.insert(1, source, 1, 4);
System.out.println(target); // [BCD]

source.replace(1, 4, "xyz");
System.out.println(source); // AxyzE
System.out.println(target); // [BCD]
~~~

Explaining the indices:

- `offset=1`: insertion position in the **destination** `"[]"`, located between `[` and `]`.
- `start=1`, `end=4`: source character slice at indices 1, 2, 3, which is `"BCD"`.
- The destination's result is `"[BCD]"`. Modifying the source to `"AxyzE"` after the call does not change the destination's data.

Another example with `insert(offset, source)`:

~~~java
StringBuffer source = new StringBuffer("123");
StringBuffer target = new StringBuffer("AB");
target.insert(1, source);
System.out.println(target); // A123B
source.append("4");
System.out.println(target); // A123B
~~~

Like `append()`, the source `CharSequence` can be mutable, and when multiple threads act concurrently it must have its own synchronization rules.

Do not confuse:

- `offset` is the insertion position in the **destination**.
- `start/end` are the slice boundaries read from the **source**.
- The `offset` position must be valid in the destination when the operation executes; an offset computed too early can also become invalid if another thread modifies the destination.

## 5. Mutable Sources: What Is a Point-in-Time Snapshot?

A *snapshot* is a stable representation of data at a chosen point in time. In Java, an immutable `String` is the natural choice for a snapshot.

~~~java
StringBuffer source = new StringBuffer("BEFORE");
String snapshot = source.toString(); // immutable String

source.replace(0, source.length(), "AFTER");

StringBuffer target = new StringBuffer("value=");
target.append(snapshot);

System.out.println(source);   // AFTER
System.out.println(snapshot); // BEFORE
System.out.println(target);   // value=BEFORE
~~~

When a program wants to **lock in source content first** and then perform multiple operations, a snapshot ensures all operations use the same version:

~~~java
StringBuffer source = new StringBuffer("CODE");
String stable = source.toString();

StringBuffer a = new StringBuffer("a:");
StringBuffer b = new StringBuffer("b:");
a.append(stable);
b.insert(2, stable);

source.append("-UPDATED");
System.out.println(a); // a:CODE
System.out.println(b); // b:CODE
~~~

If `stable` were replaced with `source` in both calls, the copied content could differ if the source were modified **between the two calls**. A snapshot solves consistency across a sequence of steps, not just a single copy operation.

### Why Not Use `CharSequence` as a "Snapshot"?

A variable of type `CharSequence` can point to a `StringBuilder`, `StringBuffer`, `CharBuffer`, or any custom implementation. Example:

~~~java
StringBuilder source = new StringBuilder("old");
CharSequence view = source; // Same object, no copy made.

source.replace(0, 3, "new");
System.out.println(view); // new
~~~

Assigning `CharSequence view = source` **only assigns a reference**; it does not freeze the content. For an immutable snapshot, create `String stable = source.toString()` at a safe reading point, then pass `stable` into `append()`/`insert()`.

### `CharBuffer` Also Has Read-Region State

A `java.nio.CharBuffer` is a `CharSequence`, yet the observable content can be affected by `position` and `limit`:

~~~java
import java.nio.CharBuffer;

CharBuffer source = CharBuffer.wrap("ABCDE");
StringBuffer target = new StringBuffer();
target.append(source);
source.position(2);
target.append(source);

System.out.println(target); // ABCDECDE
~~~

The first call appends `"ABCDE"`; the second appends the remaining `"CDE"`. Not only modifying characters changes a `CharSequence`: the **positional state** of certain source types also affects the content exposed by the interface.

## 6. Multi-Threaded Concurrency: What Is Guaranteed?

`StringBuffer` has synchronized operations, unlike `StringBuilder` which has no internal synchronization. However, this **does not mean every multi-operation workflow on source and destination is an atomic transaction**.

Consider a two-step process:

~~~java
// Illustrates operation order, not standalone race demonstration code.
StringBuffer source = new StringBuffer("A");
StringBuffer target = new StringBuffer();

target.append(source);
source.append("B");
target.append(source);
~~~

If another thread can modify `source` **between** the two `append` calls, the destination can end up containing two different versions of the source. Even when individual methods are synchronized, there is no promise that an entire read–copy–read sequence naturally becomes one transaction.

For `StringBuilder` or an unsynchronized mutable `CharSequence`, **modifying while** another call is reading multiple characters can lead to inconsistent observations or exceptions, depending on implementation. Never rely on lucky scheduler timing.

### Approach 1: Snapshot the StringBuffer Then Copy

~~~java
StringBuffer source = new StringBuffer("READY");
String snapshot = source.toString();
StringBuffer target = new StringBuffer("state:");
target.append(snapshot);
~~~

In the `StringBuffer` API, creating a `String` from the source's content uses the source object's synchronization. When all source modifications go through valid `StringBuffer` methods, `snapshot` becomes immutable and unaffected by subsequent changes. Once the snapshot is obtained, there is no need to hold the source lock while copying to the destination.

### Approach 2: Synchronize the Entire Multi-Step Operation

If you need to **check and use content consistently with another condition**, use a clear, shared locking protocol for both reader and writer:

~~~java
StringBuffer source = new StringBuffer("READY");
String snapshot;
synchronized (source) {
    if (source.length() > 0) {
        snapshot = source.toString();
    } else {
        snapshot = "<empty>";
    }
}
StringBuffer target = new StringBuffer();
target.append(snapshot);
~~~

The example above synchronizes checking length with taking the snapshot on **the same source lock**. Still, do not infer that a writer bypassing that locking protocol will safely coordinate with readers on arbitrary `CharSequence` implementations.

If you must lock **two different buffers** simultaneously, a consistent lock-acquisition order across the entire application is needed to avoid deadlock. Many tasks only need to snapshot each source before modifying the destination and avoid holding two locks at once.

### Approach 3: StringBuilder Should Only Be Modified by One Thread, or Properly Protected

If only a single thread creates and modifies a `StringBuilder`, it can be copied sequentially without synchronization. If multiple threads access it, you must use external synchronization, pass it through a queue/message to a single owning thread, or freeze a `String` before handing it to other threads. `StringBuilder.toString()` by itself cannot fix a race against a writer modifying the builder without synchronization.

### General Rules

| Situation | What to do |
|---|---|
| Immutable `String` source | Use directly |
| Source `StringBuffer` modified only sequentially | Use directly if content at call time is desired |
| Two copies must reflect the exact same version | Take one `String` snapshot and reuse it |
| Source `StringBuffer` has multiple writers | Take snapshot under proper locking; synchronize entire workflow if multi-step invariants exist |
| Source `StringBuilder` modified concurrently | Do not read/copy uncoordinated; use a shared lock or ensure single-thread ownership |
| Custom `CharSequence` or view | Check thread-safety contract, stability, and character region |
| Copying a changing source into a shared destination | Freeze the source first, then call destination APIs under a clear synchronization strategy |

## 7. Inserting/Appending the Destination Into Itself: Self-Reference Cases

When **both source and destination are the same builder**, modifying the destination simultaneously changes the source data being read. This case is especially sensitive to copying order and overloads. Do not assume that every self-insert call with overlapping source regions always produces the expected result or behaves identically across every API/version.

If you want to duplicate the current content, the clearest expression is to **capture a String snapshot first**:

~~~java
StringBuffer buffer = new StringBuffer("AB");
String original = buffer.toString();
buffer.append(original);
System.out.println(buffer); // ABAB
~~~

If you want to insert the beginning of the buffer into its own middle:

~~~java
StringBuffer buffer = new StringBuffer("WXYZ");
String snapshot = buffer.toString();
buffer.insert(2, snapshot.substring(0, 2));
System.out.println(buffer); // WXWXYZ
~~~

This prevents a change to the destination from simultaneously altering the content exposed by the source parameter. Self-referential cases, especially with `insert(..., CharSequence, start, end)`, require attention to the JDK version's contract and avoiding self-inferred overlap rules in critical code.

## 8. `append(Object)` and When `toString()` Is Called

`CharSequence` is not the only thing containing mutable content. Any object can have a `toString()` that depends on state:

~~~java
class Counter {
    int value;
    @Override public String toString() {
        return "v=" + value;
    }
}

Counter counter = new Counter();
StringBuffer target = new StringBuffer();
target.append((Object) counter);
counter.value = 7;
target.append((Object) counter);
System.out.println(target); // v=0v=7
~~~

This is an illustrative snippet: place `Counter` and the calling statements inside a valid program. The two conversions of the object to String happen at two different points in time. The destination object **does not store a live reference** to `counter` inside the `StringBuffer`'s content.

If a mutable object's `toString()` reads multiple fields while those fields are being modified concurrently, constructing the snapshot itself can also be inconsistent. Synchronized state reading requires its own mechanism; do not treat `append(Object)` as automatically solving concurrency for arbitrary classes.

## 9. Other Common Mistakes

### 9.1. Confusing append with a Reference Link

~~~java
StringBuilder source = new StringBuilder("A");
StringBuffer target = new StringBuffer();
target.append(source);
source.append("B");
System.out.println(target); // A
~~~

The destination keeps the copied characters; it does not automatically update to `"AB"`.

### 9.2. Assuming Thread-Safe `StringBuffer` Means the Whole Workflow Is Atomic

One `append()` call does not automatically synchronize with subsequent checking, deciding, inserting, and updating steps as a single transaction. Use a snapshot or properly scoped locks.

### 9.3. Computing Indices from One State While the Source Changes

~~~java
StringBuilder source = new StringBuilder("ABCDE");
int end = source.length();
source.setLength(2);
// source now has "AB", end=5 is stale.
// target.append(source, 0, end) will have an invalid range.
~~~

If the source can change, compute `start/end` from a stable snapshot or synchronize the entire check-and-copy process. Do not use stale indices.

### 9.4. Confusing `CharSequence` with Immutable String

A `CharSequence` variable can point to a `StringBuilder`; reassigning a reference does not create a copy. Use `String snapshot = source.toString()` when stable data and safe reads are needed.

### 9.5. Splitting a Unicode Surrogate Pair

The range `[start,end)` uses UTF-16 code unit indices; an emoji outside the BMP typically requires two `char`s. Splitting between two surrogates can yield an unpaired surrogate. If the goal is slicing by Unicode code points or grapheme clusters, determine proper boundaries before copying.

### 9.6. Treating Content Copying as Identity Equality

`StringBuffer` does not override `equals()` for content comparison. Use `toString().equals(...)` or `String.contentEquals(CharSequence)` when comparing by characters. Do not use `==` or `StringBuffer.equals()` to check if two contents are equal.

## 10. Complete Java 17 Program

The following verified **`MutableSourceBufferDemo.java`** file demonstrates: appending at two points in time; inserting a slice then modifying the source; creating and reusing a snapshot; inserting destination's own content via snapshot; and a `CharBuffer` source changing its visible region.

~~~java
import java.nio.CharBuffer;

public class MutableSourceBufferDemo {
    public static void main(String[] args) {
        StringBuffer source = new StringBuffer("A");
        StringBuffer target = new StringBuffer("Result:");
        target.append(source);
        source.append("B");
        target.append(source);
        System.out.println("appendResult=" + target);
        System.out.println("appendSource=" + source);

        StringBuilder partSource = new StringBuilder("ABCDE");
        StringBuffer inserted = new StringBuffer("[]");
        inserted.insert(1, partSource, 1, 4);
        partSource.replace(1, 4, "xyz");
        System.out.println("insertResult=" + inserted);
        System.out.println("insertSource=" + partSource);

        StringBuffer state = new StringBuffer("OLD");
        String snapshot = state.toString();
        StringBuffer left = new StringBuffer("left:");
        StringBuffer right = new StringBuffer("right:");
        left.append(snapshot);
        right.append(snapshot);
        state.replace(0, state.length(), "NEW");
        System.out.println("stateNow=" + state);
        System.out.println("snapshotLeft=" + left);
        System.out.println("snapshotRight=" + right);

        StringBuffer self = new StringBuffer("AB");
        String oldValue = self.toString();
        self.append(oldValue);
        System.out.println("selfAppend=" + self);

        StringBuffer same = new StringBuffer("WXYZ");
        String sameSnapshot = same.toString();
        same.insert(2, sameSnapshot.substring(0, 2));
        System.out.println("selfInsert=" + same);

        CharBuffer chars = CharBuffer.wrap("ABCDE");
        StringBuffer fromView = new StringBuffer();
        fromView.append(chars);
        chars.position(2);
        fromView.append(chars);
        System.out.println("charBufferView=" + fromView);

        StringBuilder word = new StringBuilder("cat");
        StringBuffer copied = new StringBuffer();
        copied.append((CharSequence) word);
        word.setCharAt(0, 'b');
        copied.insert(0, (CharSequence) word);
        System.out.println("mutableBuilder=" + word);
        System.out.println("copyResult=" + copied);
    }
}
~~~

Compile and run with JDK 17 or newer, saving the file in UTF-8 encoding:

~~~bash
javac -encoding UTF-8 MutableSourceBufferDemo.java
java MutableSourceBufferDemo
~~~

Expected output:

~~~text
appendResult=Result:AAB
appendSource=AB
insertResult=[BCD]
insertSource=AxyzE
stateNow=NEW
snapshotLeft=left:OLD
snapshotRight=right:OLD
selfAppend=ABAB
selfInsert=WXWXYZ
charBufferView=ABCDECDE
mutableBuilder=bat
copyResult=batcat
~~~

Points to observe:

- `appendResult` contains the source's content at **two different points in time**.
- `insertResult` remains `[BCD]` even after the source becomes `AxyzE`.
- Both destinations `snapshotLeft` and `snapshotRight` retain `OLD` even though the source's state is now `NEW`.
- Self-append/self-insert uses a **snapshot** to avoid copying from a structure being modified at the same time.
- `CharBuffer` with `position=2` provides the remaining slice `CDE` for the second append.
- `copyResult=batcat` shows that modifying `StringBuilder` after appending does not alter previously copied characters in the destination.

## 11. Practice Checklist

- [ ] Identify whether the actual source is an immutable `String`, `StringBuffer`, `StringBuilder`, `CharBuffer`, or another `CharSequence`.
- [ ] When wanting the "latest" content, accept that each call sees a separate source state at the time it is read.
- [ ] When wanting multiple copies to use the **exact same version**, create a `String` snapshot **once** and reuse it.
- [ ] Never allow a mutable source to be modified concurrently while being read without a guaranteed coordination mechanism.
- [ ] With `StringBuffer`, remember that per-operation synchronization does not automatically turn multiple steps into one transaction.
- [ ] With `StringBuilder`, avoid sharing mutable state without locks or clear ownership.
- [ ] With `insert()`, distinguish destination `offset` from source `start/end`; validate indices against a stable state.
- [ ] When the source itself is also the destination, prefer a `String` snapshot for clearer code and to avoid overlap issues.
- [ ] When copying by Unicode ranges, remember that indices are measured in UTF-16 code units.
- [ ] Test both sources changing **between** calls and cases involving multiple threads.

**Conclusion:** `StringBuffer.append()` and `insert()` **copy characters**, rather than maintaining a live link to the source. A mutable source can yield different content across copy calls. When a stable version or correctness in a concurrent environment is required, you must use **immutable snapshots and appropriate synchronization rules**; never deduce that an entire workflow is automatically safe simply because `StringBuffer` is used.