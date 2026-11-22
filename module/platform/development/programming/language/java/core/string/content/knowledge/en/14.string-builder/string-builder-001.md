# `StringBuilder`: Mutable Character Buffer and String-Building Model

## 1. Why Do We Need `StringBuilder`?

In Java, `String` is **immutable**: once a `String` object is created, its content cannot be modified through the public API. Expressions such as concatenation, replacement, or slicing produce a new resulting string value; a variable can be assigned another reference, but the content of the old `String` object does not change.

`StringBuilder` solves a different need: **incrementally building and modifying a character sequence on the same mutable object**. It is especially useful when appending many parts to a result, assembling data in a loop, replacing a segment of text, inserting in the middle, or deleting characters.

~~~java
String text = "Hello";
text += " Java"; // text points to a new String value

StringBuilder builder = new StringBuilder("Hello");
builder.append(" Java"); // the same builder object is modified
~~~

Both can produce the text value `"Hello Java"`. The key difference is the **object model**: `String` remains immutable; `StringBuilder` has mutable state consisting of the current character sequence and the allocated buffer capacity.

**Goal:** understand when to use a builder, how `append` works, the difference between `length` and `capacity`, in-place modification operations, converting to `String`, UTF-16 handling, and thread-safety limitations.

## 2. Mutable Character Buffer Model

Think of a `StringBuilder` as a container holding a sequence of **UTF-16 code units** with two primary quantities:

- **`length()`**: the number of code units currently belonging to the builder's **valid content**.
- **`capacity()`**: the number of code units the buffer can hold **before needing to grow its capacity**. Always `0 <= length() <= capacity()`.

An intuitive model:

~~~text
builder = new StringBuilder(8)
length = 0; capacity = 8

After append("Java"):
content:  [J][a][v][a][ ][ ][ ][ ]
          ^-----------^ ^---------^
             length=4    available
capacity=8

After append(" 21"):
content:  [J][a][v][a][ ][2][1][ ]
length=7; capacity>=8

After appending more beyond capacity:
the builder automatically expands the buffer when needed;
existing content is preserved.
~~~

That is a **logical model**, not a guarantee that `StringBuilder` is always stored in a physical `char[]` or always increases capacity by a fixed ratio. The specific byte/array layout, allocation, optimizations, and growth policy may vary by JDK.

**Why is buffer reuse helpful?** If many parts must be appended sequentially, a builder can reuse already-allocated space instead of forcing the program to represent every intermediate state as a new `String` value. This is often helpful for continuous concatenation workflows, though modern Java's `+` also has its own optimizations.

## 3. API Selection Map When Building Strings

Instead of memorizing a list of commands, start from the **type of change you need to make**. The following lessons go deeper into the parameters, boundary conditions, and exceptions of each group.

| Goal | Common APIs | Decision Notes |
| --- | --- | --- |
| Create an empty builder or one with initial text | `new StringBuilder()`, `new StringBuilder(n)`, `new StringBuilder(text)` | `int` argument reserves capacity; `String` provides content |
| Append data incrementally | `append(value)` | Overload is chosen by expression type; returns the builder itself |
| Append a Unicode code point from `int` | `appendCodePoint(cp)` | Code points outside the BMP take two code units; `append(cp)` appends digits instead |
| Edit content by position | `insert`, `delete`, `deleteCharAt`, `replace` | Indices are in UTF-16 code units; `[start,end)` usually excludes the end bound |
| Change a character unit or logical length | `setCharAt(i,ch)`, `setLength(n)` | Both methods return `void`; increasing length pads with NUL |
| Reserve or attempt to shrink the buffer | `ensureCapacity(n)`, `trimToSize()` | Does not modify content; `trimToSize` is a best-effort request |
| Reverse or repeat data | `reverse()`, `repeat(...)` | Reversing does not preserve every grapheme cluster; builder `repeat` requires Java 21+ |
| Obtain a stable result | `toString()` | Returns a `String` whose content does not change when the builder is modified further |

A short example showing **API selection based on goal**:

~~~java
StringBuilder line = new StringBuilder("id=");
line.append(42);            // append number as text: "id=42"
line.insert(0, "[");        // insert opening bracket
line.append(']');           // append closing bracket
String finished = line.toString(); // "[id=42]"
~~~

Each statement sees the state after the previous statement. If you keep `finished` and continue modifying `line`, `finished` still holds the original content. Therefore, a builder is suitable for **assembling**, while `String` is suitable as a **finalized result**.

## 4. Complete Java 17+ Program: Observing the String-Building Model

Create the file **`StringBuilderModelDemo.java`**:

~~~java
public class StringBuilderModelDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder(4);
        System.out.println("initial=" + sb.length() + "/" + sb.capacity());

        sb.append("Java").append(' ').append(21);
        System.out.println("built=" + sb);
        System.out.println("length=" + sb.length());
        System.out.println("capacityEnough=" + (sb.capacity() >= sb.length()));

        String snapshot = sb.toString();
        sb.insert(5, "SE ");
        System.out.println("insert=" + sb);

        sb.replace(5, 7, "Core");
        System.out.println("replace=" + sb);

        sb.delete(9, 12);
        sb.setCharAt(0, 'j');
        System.out.println("edited=" + sb);
        System.out.println("snapshot=" + snapshot);

        sb.setLength(4);
        System.out.println("shortened=" + sb);
        sb.setLength(6);
        System.out.println("paddedCodeUnits="
                + (int) sb.charAt(4) + "," + (int) sb.charAt(5));

        StringBuilder unicode = new StringBuilder()
                .append('A')
                .appendCodePoint(0x1F600)
                .append('B');
        System.out.println("unicodeLength=" + unicode.length());
        System.out.println("unicodeCodePoints="
                + unicode.codePointCount(0, unicode.length()));

        StringBuilder comparison = new StringBuilder("java");
        System.out.println("sameText=" + sb.substring(0, 4)
                .contentEquals(comparison));
        System.out.println("sameBuilderContent="
                + new StringBuilder("java").toString()
                        .equals(comparison.toString()));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 StringBuilderModelDemo.java
java StringBuilderModelDemo
~~~

`stdout` verified via compilation/execution:

~~~text
initial=0/4
built=Java 21
length=7
capacityEnough=true
insert=Java SE 21
replace=Java Core 21
edited=java Core
snapshot=Java 21
shortened=java
paddedCodeUnits=0,0
unicodeLength=4
unicodeCodePoints=3
sameText=true
sameBuilderContent=true
~~~

Output explanation:

1. The constructor requests a capacity of `4`, but the initial content is empty, so `initial=0/4`.
2. `append` appends `"Java"`, a space, and the number `21` in sequence, producing the text `"Java 21"` of 7 code units. The builder expands if needed; the example only checks the invariant `capacity >= length`.
3. `insert` inserts `"SE "` before `21`. `replace` replaces `"SE"` with `"Core"`. `delete` removes `" 21"` and `setCharAt` changes `J` to `j`.
4. The `snapshot` variable is a `String` captured **before** those edits, so it remains `"Java 21"` while the builder becomes `"java Core"`.
5. `setLength(4)` truncates the sequence to `"java"`; `setLength(6)` appends two `U+0000` code units with numeric value `0`.
6. `appendCodePoint(0x1F600)` adds an emoji using **two UTF-16 code units**. Together with `A` and `B`, `unicode.length() == 4` while having 3 code points.
7. `substring(0, 4)` extracts `"java"`, and `String.contentEquals(CharSequence)` allows comparing against the builder's content. Comparing two `String` objects created from builders also yields `true`.

## 5. Reasoning Correctly from the Mutable Model

**A builder is a stateful object.** For example, `StringBuilder alias = builder;` only creates a second reference to the same object; `alias.append(...)` changes the text seen through `builder`. When you need a stable result to pass between components, obtain a `String` via `toString()` instead of handing a mutable builder to another party to edit.

**Index bounds come from `length()`, not `capacity()`.** Extra space in the buffer does not make `charAt(length())` valid. For a supplementary emoji like 😀, `length()` increases by two UTF-16 units while the code point count increases by one. Positional edit operations can split a surrogate pair in half; if you need to process by visible characters, you must also consider grapheme clusters.

**Choose the tool based on the data lifecycle.** A short `String` concatenation with `+` is often clear and can be optimized by Java. When collecting many pieces in a loop, a local builder is usually appropriate; only reserve capacity when you have a reliable estimate and a real performance need. `StringBuilder` has no built-in synchronization for safe shared mutation across multiple threads; prefer single-owner builders or coordinate access using explicit synchronization.

## 6. Self-Check Questions

**Question 1.** What are `new StringBuilder(32).length()` and `capacity()`?

**Answer:** length is `0`, capacity is `32`. No characters are added just because space was reserved.

**Question 2.** Do the two statements `builder.append("a"); builder.append("b");` create two new builders?

**Answer:** no. Both modify the same builder object, and the accumulated content becomes `"ab"`.

**Question 3.** After `String saved = builder.toString(); builder.append("!");`, does the content of `saved` change?

**Answer:** no. `saved` is an immutable `String` holding the state when `toString` was called.

**Question 4.** How do `ensureCapacity(200)` and `setLength(200)` differ?

**Answer:** `ensureCapacity` reserves at least 200 code units without changing the content; `setLength` sets the content length to 200, truncating or padding with `\u0000` depending on the current state.

**Question 5.** Why does `new StringBuilder("😀").length()` equal `2`?

**Answer:** the emoji `U+1F600` requires a surrogate pair consisting of two UTF-16 code units; `length` counts code units.

**Question 6.** Is it safe for two threads to concurrently call `append` on a shared `StringBuilder`?

**Answer:** there is no thread-safety guarantee without synchronization; prefer a local builder or an appropriate coordination mechanism.

**Question 7.** Does `new StringBuilder("x").equals(new StringBuilder("x"))` return true because both contain `x`?

**Answer:** no. `StringBuilder` does not compare content with `equals`; two distinct instances are not equal by identity. Use `toString().equals(...)` to compare text.

**Question 8.** Why should you avoid calling `trimToSize()` after every append in a loop?

**Answer:** the builder may have to expand again right afterward; doing so can increase allocation and copying overhead instead of taking advantage of spare capacity.

## 7. Official References

- [Java SE 17 — `StringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): constructors, `append`, `insert`, `delete`, `replace`, `toString`, and thread-safety contract.
- [Java SE 17 — `AbstractStringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractStringBuilder.html): `length`, `capacity`, `ensureCapacity`, `setLength`, and code unit operations.
- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutability, string values, and `equals` comparison.
- [Java SE 17 — `StringBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html): synchronized buffer and multi-step concatenation limitations.

**Key takeaway:** `StringBuilder` is a **mutable object that accumulates text in an expandable buffer**. `length` is the current number of code units; `capacity` is the reserved capacity. Operations `append/insert/delete/replace` modify the same builder; `toString` returns an immutable `String` value; a builder does not automatically synchronize across multiple threads.
