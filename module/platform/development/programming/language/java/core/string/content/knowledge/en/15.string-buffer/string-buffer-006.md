# Converting from StringBuffer to String in Java

## 1. Learning Objectives

`StringBuffer` is a class used to **build and edit** character sequences through operations like `append()`, `insert()`, `delete()`, and `replace()`. The content inside a `StringBuffer` can change (*mutable*). Conversely, `String` is an **immutable** string type: once a `String` object is created, its content cannot be modified.

When finished building text, we often need to obtain the result as a `String`, for example to pass to an API requiring `String`, store a stable result, or compare and process using `String` methods.

The most direct way is:

~~~java
StringBuffer buffer = new StringBuffer("Java");
buffer.append(" Core");

String result = buffer.toString();
System.out.println(result); // Java Core
~~~

After this lesson, you should be able to:

1. Distinguish mutable `StringBuffer` from immutable `String`.
2. Convert `StringBuffer` to `String` via `toString()`, the `new String(buffer)` constructor, and understand when to use `String.valueOf(buffer)`.
3. Explain why the resulting `String` is a **content snapshot** that does not change when the buffer continues to be modified.
4. Recognize that conversion does not clear, reset length, invalidate the buffer, or automatically convert all other references to `String`.
5. Handle `null`, empty buffers, Unicode, output formatting, and APIs accepting `CharSequence`.
6. Know the limits of `StringBuffer`'s synchronized methods under multi-threading.
7. Verify with standalone compilable and runnable Java 17+ examples.

Prerequisites: objects/references, methods, `String`, `StringBuffer`, immutability, and assignment.

## 2. Primary Way: Calling StringBuffer.toString()

Syntax:

~~~java
StringBuffer buffer = new StringBuffer();
buffer.append("Hello");
buffer.append(" ");
buffer.append("World");

String text = buffer.toString();
~~~

`buffer.toString()` returns a `String` object representing the buffer's **current character content**. This is the most idiomatic, clear, and readable approach.

| Property | `StringBuffer` | Resulting `String` |
| --- | --- | --- |
| Can content be modified via API? | Yes: `append`, `delete`, `setCharAt`… | No |
| Can characters continue to be added? | Yes | Must create another `String` result or use a builder/buffer |
| Current length | `buffer.length()` | `text.length()` |
| Convert to the other type | `buffer.toString()` | `new StringBuffer(text)` |
| Value if buffer is modified afterward | Changes with each edit | **Retains the captured content** |

Key point: `toString()` **does not modify the buffer** and does not change the type of the `buffer` variable. The `buffer` variable still references the same mutable `StringBuffer` object after the call.

### Data Flow Illustration

~~~text
StringBuffer buffer: "Java"
        │
        ├─ append(" Core")
        ▼
StringBuffer buffer: "Java Core"
        │
        ├─ toString()
        ▼
String text: "Java Core"   (immutable)

Afterward buffer.append(" 17"):

buffer = "Java Core 17"
text   = "Java Core"      (unchanged)
~~~

Do not picture `toString()` as an "in-place type conversion." Both variables have **different static types** and hold independent references in terms of data semantics.

## 3. Snapshot: String Does Not Change When the Buffer Is Edited Further

~~~java
StringBuffer buffer = new StringBuffer("AB");
String snapshot = buffer.toString();

buffer.append("C");
buffer.setCharAt(0, 'X');

System.out.println(buffer);   // XBC
System.out.println(snapshot); // AB
~~~

`snapshot` holds the value `"AB"` at the time of conversion. Operations like `append("C")` or `setCharAt(0, 'X')` mutate the buffer; they **do not mutate** an existing `String` object.

If you want to update the `snapshot` variable to reflect new buffer content, you must **call `toString()` again and reassign**:

~~~java
StringBuffer buffer = new StringBuffer("A");
String snapshot = buffer.toString(); // A

buffer.append("B");
snapshot = buffer.toString();        // AB

System.out.println(snapshot);       // AB
~~~

The assignment `snapshot = ...` only reassigns the **variable reference**; it does not make `String` mutable.

### No Live Link Between the Two Objects

~~~java
StringBuffer buffer = new StringBuffer("first");
String first = buffer.toString();

buffer.setLength(0);
buffer.append("second");
String second = buffer.toString();

System.out.println(first);  // first
System.out.println(second); // second
System.out.println(buffer); // second
~~~

`setLength(0)` clears the content **stored inside the buffer** by shrinking its logical length to 0; it does not erase or modify `first`. The buffer remains reusable.

Do not assert that every call to `toString()` **always allocates a new String object**. A Java implementation may use internal caching or optimizations. What the API guarantees for this lesson is that **the returned `String` value is not altered by subsequent operations on the buffer**.

## 4. Conversion Approaches and Which One to Choose?

### 4.1. Recommended Way: buffer.toString()

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = buffer.toString();
~~~

Advantage: expresses exact intent, needs no extra utilities, and immediately signals retrieving the string value from the buffer. **This is the default approach to use** when `buffer` is non-null.

### 4.2. Constructor: new String(buffer)

Java also supports a constructor taking `StringBuffer`:

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = new String(buffer);
~~~

The result is a `String` with the same content as the buffer at creation time. For normal needs, it offers no expressive benefit over `buffer.toString()`. When retrieving the result from a buffer, most code should use `toString()`.

Note this is **`new String(StringBuffer)`**, not a constructor taking an arbitrary byte/char type. To build a string from `char[]`, using `new String(chars)` is a different contract.

### 4.3. String.valueOf(buffer)

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = String.valueOf(buffer);
~~~

`String.valueOf(Object)` uses the `toString()` representation of a non-null object; when the argument is `null`, it returns **the four-character string `"null"`**. Because `StringBuffer` has no special `valueOf` overload, calling it with a `StringBuffer` variable invokes the `Object` overload.

~~~java
StringBuffer missing = null;

System.out.println(String.valueOf(missing)); // null
// missing.toString();       // NullPointerException
// new String(missing);      // NullPointerException
~~~

Distinguish a string object containing the four characters `"null"` from an actual missing-data state. **Do not use `String.valueOf(buffer)` as a default `null`-handling policy** if business logic expects to reject it, return `null`, or use an empty string.

### 4.4. Returning null Instead of the String "null"

~~~java
static String snapshotOrNull(StringBuffer buffer) {
    return buffer == null ? null : buffer.toString();
}
~~~

Or if `null` is a programming error that should be caught:

~~~java
static String snapshotRequired(StringBuffer buffer) {
    java.util.Objects.requireNonNull(buffer, "buffer");
    return buffer.toString();
}
~~~

Both are **illustrative method snippets**, not standalone programs by themselves. The rule for returning `null` vs. throwing an exception must be agreed upon with API consumers.

## 5. Using String After Conversion

A common reason is that a library or business method requires the exact `String` type:

~~~java
static void saveMessage(String message) {
    System.out.println("Saved: " + message);
}

// Called inside a method:
StringBuffer buffer = new StringBuffer();
buffer.append("Order ");
buffer.append(42);

saveMessage(buffer.toString());
~~~

This is an **illustrative fragment**: place the statements inside a method such as `main`, and `saveMessage` inside a class body to compile. `StringBuffer` is not implicitly compatible with every parameter of type `String`.

### Check the Parameter Type Before Converting

Some APIs accept `CharSequence`, an interface implemented by both `String` and `StringBuffer`:

~~~java
static int textLength(CharSequence text) {
    return text.length();
}
~~~

If you only need to read length or access via `CharSequence`, you can pass the buffer **without creating an intermediate String**:

~~~java
StringBuffer buffer = new StringBuffer("ABC");
System.out.println(textLength(buffer));            // 3
System.out.println(textLength(buffer.toString())); // 3
~~~

However, `CharSequence` does not guarantee immutable content; if the API retains the reference for later use, converting to `String` may be necessary to keep a **stable** copy.

### When You Only Need to Print Buffer Content

~~~java
StringBuffer buffer = new StringBuffer("Hello");

System.out.println(buffer);            // Hello
System.out.println(buffer.toString()); // Hello
~~~

`println(Object)` uses the object's text representation. You do not necessarily need to create a separate `String` variable just to print; however, if you actually need to retain the result or pass it to something that only accepts `String`, call `toString()`.

## 6. When Should You Create the String?

In a text-building pipeline, obtain the `String` **once the desired content is complete**:

~~~java
StringBuffer buffer = new StringBuffer();
buffer.append("Name: ");
buffer.append("Lan");
buffer.append("\n");
buffer.append("City: ");
buffer.append("Hanoi");

String report = buffer.toString();
~~~

If you convert to `String` too early and then continue editing the buffer, the early `String` will **not automatically stay synchronized** with the final content.

Example:

~~~java
StringBuffer buffer = new StringBuffer("Hello");

String tooEarly = buffer.toString();
buffer.append(" World");

System.out.println(tooEarly);          // Hello
System.out.println(buffer.toString()); // Hello World
~~~

Therefore, call `toString()` at **the boundary between the mutable building phase and the immutable result**. For example, that boundary may be at the end of a message-building method, right before sending the result to an API, or when saving the current state.

You do not always convert only once. If a system intentionally stores multiple history checkpoints:

~~~java
StringBuffer timeline = new StringBuffer("start");
String stage1 = timeline.toString();

timeline.append(" -> process");
String stage2 = timeline.toString();

System.out.println(stage1); // start
System.out.println(stage2); // start -> process
~~~

Those are two meaningful snapshots, not redundant calls.

## 7. Comparing StringBuffer, StringBuilder, and String

| Characteristic | `String` | `StringBuffer` | `StringBuilder` |
| --- | --- | --- | --- |
| Can content be edited? | No | Yes | Yes |
| Incremental concatenation with `append()`? | No | Yes | Yes |
| Use `toString()` to get String? | Value is already a String | Yes | Yes |
| Key mutating methods synchronized? | No in-place mutation | Synchronized | Unsynchronized |
| Common use | Stable text values | Text building with synchronization needs | Text building within single-thread scope |
| Editing buffer/builder after snapshot changes String? | Not applicable | No | No |

Example showing both builders can produce a `String` result:

~~~java
StringBuffer synchronizedBuilder = new StringBuffer("A");
String fromBuffer = synchronizedBuilder.toString();

StringBuilder unsynchronizedBuilder = new StringBuilder("A");
String fromBuilder = unsynchronizedBuilder.toString();

System.out.println(fromBuffer.equals(fromBuilder)); // true
~~~

However, a `StringBuffer` object used by multiple threads can receive edits between calls; `toString()` taking a snapshot **does not automatically turn a multi-step workflow into an atomic transaction** (see section 9).

## 8. Common Conversion Mistakes

### 8.1. Forgetting to Call toString() When the Receiver Needs String

~~~java
StringBuffer buffer = new StringBuffer("Hello");
// String text = buffer; // Compile error: StringBuffer is not String
String text = buffer.toString();
~~~

`StringBuffer` and `String` are two distinct classes, even though both hold character sequences. Java performs no implicit cast from `StringBuffer` to `String`.

### 8.2. Invalid Type Casting

~~~java
StringBuffer buffer = new StringBuffer("Hello");
// String text = (String) buffer; // No valid cast relationship
String text = buffer.toString();
~~~

You cannot replace `toString()` with a cast. They are neither the same object nor related by inheritance to allow such a cast.

### 8.3. Saving a String and Expecting It to Update Automatically

~~~java
StringBuffer buffer = new StringBuffer("A");
String snapshot = buffer.toString();

buffer.append("B");
System.out.println(snapshot); // A
~~~

To get the new value, take a fresh snapshot: `snapshot = buffer.toString();`.

### 8.4. Thinking Conversion Empties or Locks the Buffer

~~~java
StringBuffer buffer = new StringBuffer("ABC");
String text = buffer.toString();

System.out.println(buffer.length()); // 3
buffer.append("D");                 // Still valid
System.out.println(buffer);          // ABCD
System.out.println(text);            // ABC
~~~

`toString()` does **not** reset the length, does not free programmer-managed memory, and does not prevent subsequent `append()` calls.

### 8.5. Using equals on StringBuffer to Compare Content

`StringBuffer` does not define `equals()` by content like `String`. To compare text, convert to `String` (or use an appropriate string-comparison method):

~~~java
StringBuffer a = new StringBuffer("Java");
StringBuffer b = new StringBuffer("Java");

System.out.println(a.equals(b));                     // false
System.out.println(a.toString().equals(b.toString())); // true
~~~

Do not mix up **reference equality** with **equal text data**.

### 8.6. Returning a String and Then Modifying the Buffer Inside a Method

This can be completely valid, provided you know the method is returning a **snapshot**:

~~~java
static String makeText() {
    StringBuffer b = new StringBuffer("A");
    String s = b.toString();
    b.append("B");
    return s; // "A", not "AB"
}
~~~

If you want to return `"AB"`, convert at the end after `append()` finishes.

## 9. Synchronization and Multi-Threading: How Far Do Guarantees Go?

`StringBuffer` is designed with **synchronized** key methods, unlike `StringBuilder`. Calling `toString()` produces a stable `String` value once the result is obtained, yet you must distinguish:

- A single synchronized operation on `StringBuffer` provides protection within the scope of **that operation**.
- Multiple operations like `append()` → `delete()` → `toString()` do not become **one atomic operation** just because each individual call is synchronized.
- Another thread can alter buffer content between two calls; the snapshot may contain content at an unexpected moment without proper coordination.
- The returned `String` is immutable, so its own content will not continue changing while threads modify the buffer.

When you need to take a snapshot of **a logical sequence of changes** without interleaving, you must have a synchronization strategy covering the whole sequence of operations with all involved threads obeying the locking rule:

~~~java
StringBuffer shared = new StringBuffer();

String snapshot;
synchronized (shared) {
    shared.append("A");
    shared.append("B");
    snapshot = shared.toString();
}

System.out.println(snapshot); // AB
~~~

This is a single-threaded example of the locking syntax. In a multi-threaded application, the result is protected from edits **interleaving from operations that obey the same `shared` lock**. Do not rely solely on `StringBuffer` to solve all business-level concurrency issues.

Note: you can design each thread to use its own buffer and then emit a `String`; when synchronization is unnecessary, `StringBuilder` is usually the simpler choice.

## 10. Unicode, Length, and Encoding After Conversion

`StringBuffer` stores a sequence of **UTF-16 code units** in terms of its `char`/index API, just like `String`. Converting via `toString()` preserves the represented character order: it performs no case conversion, Unicode normalization, or UTF-8 encoding.

~~~java
StringBuffer buffer = new StringBuffer("A😀B");
String text = buffer.toString();

System.out.println(buffer.length()); // 4
System.out.println(text.length());   // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

The emoji `😀` occupies two UTF-16 units yet is one Unicode code point. Converting to `String` does not change this distinction.

To obtain **UTF-8 bytes** for file or network storage:

~~~java
StringBuffer buffer = new StringBuffer("A");
byte[] encoded = buffer.toString().getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(encoded.length); // 1
~~~

`toString()` is not an encoding method. In particular, do not confuse `StringBuffer` with `ByteBuffer`.

## 11. Complete Runnable Program on Java 17+

Create the file **`StringBufferToStringDemo.java`**:

~~~java
public class StringBufferToStringDemo {
    public static void main(String[] args) {
        StringBuffer buffer = new StringBuffer("Java");
        buffer.append(" Core");

        String first = buffer.toString();
        System.out.println("first=" + first);

        buffer.append(" 17");
        System.out.println("buffer=" + buffer);
        System.out.println("firstAgain=" + first);

        String second = new String(buffer);
        System.out.println("second=" + second);

        buffer.setCharAt(0, 'K');
        System.out.println("afterEdit=" + buffer);
        System.out.println("secondAgain=" + second);

        buffer.setLength(0);
        System.out.println("empty=[" + buffer.toString() + "]");
        System.out.println("firstAfterClear=" + first);

        StringBuffer missing = null;
        System.out.println("valueOfNull=" + String.valueOf(missing));

        StringBuffer other = new StringBuffer("Java Core");
        System.out.println("contentEquals="
                + first.equals(other.toString()));

        StringBuffer unicode = new StringBuffer("A😀B");
        String snapshot = unicode.toString();
        System.out.println("utf16=" + snapshot.length());
        System.out.println("codePoints="
                + snapshot.codePointCount(0, snapshot.length()));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 StringBufferToStringDemo.java
java StringBufferToStringDemo
~~~

**Exact Stdout:**

~~~text
first=Java Core
buffer=Java Core 17
firstAgain=Java Core
second=Java Core 17
afterEdit=Kava Core 17
secondAgain=Java Core 17
empty=[]
firstAfterClear=Java Core
valueOfNull=null
contentEquals=true
utf16=4
codePoints=3
~~~

**Group-by-group explanation:**

1. `first` captures the buffer content after `append(" Core")`. When `" 17"` is appended to the buffer, `first` stays `"Java Core"`.
2. `second = new String(buffer)` captures the new content `"Java Core 17"`. Changing `buffer.setCharAt(0, 'K')` to `"Kava Core 17"` does not alter `second`.
3. `setLength(0)` only empties the buffer; `first` still retains the first string.
4. `String.valueOf(missing)` with a null reference yields the four-character text `"null"`.
5. `first.equals(other.toString())` compares the content of two `String`s and returns `true`.
6. With an emoji, `length()` measures in UTF-16 code units; `codePointCount()` gives the number of code points.

Try adding `buffer.append("again")` after `setLength(0)`: you will see the buffer is reusable, while `first` and `second` keep their respective values.

## 12. Choosing the Right Method in Each Situation

| Situation | Approach | Reason |
| --- | --- | --- |
| Content is built, `String` result is needed | `buffer.toString()` | Direct, clear intent |
| Want to create a `String` from buffer at the current time | `new String(buffer)` | Valid, though usually unnecessary over `toString()` |
| Argument may be null and must display text "null" | `String.valueOf(buffer)` | Has rule converting null to text |
| Null must be preserved as null | `buffer == null ? null : buffer.toString()` | Clear null-handling contract |
| Method takes `CharSequence` and only reads immediately | Can pass `buffer` | No conversion needed if no snapshot is needed |
| Returning stable data for other components to hold long-term | `buffer.toString()` | Avoids sharing mutable state |
| Continuing to append/edit repeatedly | Keep `StringBuffer` or choose `StringBuilder` | Avoid converting prematurely |
| Converting to UTF-8 bytes | `buffer.toString().getBytes(UTF_8)` | Text-type conversion and encoding are two separate tasks |

**Performance note:** `toString()` may need to process/copy data and produce a result value, so calling it inside a large loop just to inspect intermediate content can add cost. Exact allocation details depend on the JDK and optimizations; do not assume a new object is or is not created on every call. Retain the result when a snapshot is genuinely needed, instead of converting back and forth between buffer and `String` out of habit.

## 13. Practice Exercises

### Exercise 1 — Create Two Snapshots

Initialize `StringBuffer b = new StringBuffer("A");`. Capture `String s1 = b.toString();`, then execute `b.append("B");` and capture `String s2 = b.toString();`. Print `s1`, `s2`, and `b`. Explain why only `b` and `s2` contain `B`.

### Exercise 2 — new String(buffer)

Convert `StringBuffer("Hello")` to `String` using the constructor `new String(buffer)`. Then call `buffer.delete(0, 1)`. Predict the created string and the current buffer. Why do they differ?

### Exercise 3 — Null Policies

Write a method `asTextOrNull(StringBuffer b)` returning null if the input is null, otherwise using `toString()`. Compare it with `String.valueOf((Object) b)` on null and explain the difference between the string `"null"` and a null reference.

### Exercise 4 — API Boundaries

Write two methods: `printText(String text)` and `readLength(CharSequence text)`. Try passing a `StringBuffer` directly to each method. Which method accepts it without conversion? If the method retains the reference for later processing, why might you want to convert to `String`?

### Exercise 5 — Reusing a Buffer

Create a buffer, append three parts, and convert to `String first`. Call `setLength(0)`, append new content, and capture `String second`. Prove that `first` does not change after clearing the buffer.

### Exercise 6 — Comparing Content

Create two `StringBuffer` objects with content `"same"`. Compare `a.equals(b)` with `a.toString().equals(b.toString())`. Which result checks **content**? Why should `==` not be used to compare strings?

### Exercise 7 — Business-Level Synchronization

Suppose two threads share a buffer. One thread performs `append("A")` then `append("B")`, while the other thread may append in between. Write a synchronized way to capture a snapshot of the two operations as one group, and explain why all accessing parties must obey the same locking rule.

### Exercise 8 — Unicode

Convert `StringBuffer("A😀B")` to `String`, measuring `length()` and `codePointCount()`. Why is an emoji not counted as one `char`? Does `toString()` perform UTF-8 encoding?

## 14. Awareness Checklist and Mistakes to Avoid

- `StringBuffer.toString()` **returns type `String`**, not `StringBuffer`.
- An extracted `String` **does not reflect** later edits made to the buffer.
- `toString()` **does not drain content out of the buffer** and does not automatically clear or lock the buffer.
- `new String(buffer)` is valid; `(String) buffer` is invalid.
- `String.valueOf(buffer)` on null can produce **the text `"null"`** unexpectedly.
- A method requiring `String` needs a `String`; a method accepting `CharSequence` can receive the buffer directly.
- `StringBuffer` is mutable, so sharing it is not like sharing an immutable `String`.
- A multi-step sequence of operations is not atomically safe just because each buffer method is synchronized.
- If you only need to build text within a single thread's scope, `StringBuilder` is usually simpler and more appropriate.
- `toString()` does not automatically convert Unicode, normalize, or convert to UTF-8 bytes.
- To compare content, use `equals()` on two `String` objects.
- When taking multiple snapshots, name their points in time clearly: `before`, `after`, `finalText`.

**Rule to remember:** use **`String text = buffer.toString();`** to obtain an **immutable** text value from the current state of `StringBuffer`. You can continue editing the buffer, while `text` remains unchanged. Choose when to take a snapshot according to business intent, and explicitly decide your policy for `null` and multi-threaded data.

## 15. Official References

- [Java SE 17 — StringBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html): `toString()`, `append()`, `setCharAt()`, `setLength()`, and mutable operations.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `String(StringBuffer)` constructor, `equals()`, `valueOf()`, UTF-16, and immutability.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): unsynchronized builder variant and conversion to String.
- [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html): contract for objects representing character sequences.
