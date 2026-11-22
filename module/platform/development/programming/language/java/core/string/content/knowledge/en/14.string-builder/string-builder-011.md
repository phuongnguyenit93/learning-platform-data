# StringBuilder.toString(): Result Independent of Subsequent Changes

## 1. What "Independent" Means

`StringBuilder` is a **mutable** object: after creation, you can call `append`, `insert`, `delete`, `replace`, `setCharAt`, `reverse`, or `setLength` to modify the character sequence it holds. By contrast, `String` is **immutable**: the content of a created `String` cannot be modified in place.

When you call `String snapshot = builder.toString();`, the method captures **the content of `builder` at the moment of the call** and returns a `String` with that content. Under the `StringBuilder.toString()` API contract, subsequent changes to the `StringBuilder` **do not affect** the content of the returned `String`.

- `snapshot` is a text value finalized at call time, not a "window" tracking `builder`.
- `builder` still exists and remains editable; `toString()` does not lock, clear, or reset it.
- To get a newer state, call `builder.toString()` again and keep the new result.

## 2. Standalone Runnable Java 17+ Example

Save the following program as `StringBuilderSnapshotDemo.java`:

```java
public class StringBuilderSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");

        String first = builder.toString();      // Captures "Java"
        builder.append(" 17");

        String second = builder.toString();     // Captures "Java 17"
        builder.replace(0, 4, "OpenJDK");       // Mutates the builder itself

        System.out.println("first   = " + first);
        System.out.println("second  = " + second);
        System.out.println("builder = " + builder);
        System.out.println("second still matches builder? "
                + second.contentEquals(builder));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac StringBuilderSnapshotDemo.java
java StringBuilderSnapshotDemo
```

Expected output:

```text
first   = Java
second  = Java 17
builder = OpenJDK 17
second still matches builder? false
```

Progression of the three values:

| Time | `builder` Content | `first` | `second` |
| --- | --- | --- | --- |
| Right after `first = builder.toString()` | `Java` | `Java` | Not yet created |
| After `append(" 17")` and the second `toString()` call | `Java 17` | `Java` | `Java 17` |
| After `replace(0, 4, "OpenJDK")` | `OpenJDK 17` | `Java` | `Java 17` |

`replace(0, 4, ...)` replaces the characters from index `0` up to before `4` in the **current builder**. Both `String` variables still keep the exact content from when they were created. The final `contentEquals` check returns `false` because `Java 17` differs from `OpenJDK 17`.

## 3. Distinguishing a Snapshot from a Reference to StringBuilder

Another variable pointing to the same `StringBuilder` will observe subsequent edits to that object. For example, place the following snippet **inside `main`**:

```java
StringBuilder builder = new StringBuilder("A");
StringBuilder alias = builder;
CharSequence sequence = builder;
String snapshot = builder.toString();

builder.append("B");

System.out.println(alias);     // AB
System.out.println(sequence);  // AB
System.out.println(snapshot);  // A
```

- `alias` and `sequence` both reference `builder`, so when printed after `append`, they show the new content `AB`.
- `snapshot` is a `String` created **before** `append`, so it stays `A`.
- The declared type `CharSequence` by itself **does not guarantee immutability**: the actual object may be a mutable `StringBuilder` or an immutable `String`.

This also explains why `System.out.println(builder)` prints the builder's state at the time the statement runs; it does not store a snapshot for future print statements to reuse.

## 4. Why Does Java Guarantee This?

`StringBuilder` manages a mutable sequence of characters. `toString()` creates a `String` result representing the character sequence **at that call**. From the outside, the result obeys `String`'s immutability and does not share *directly mutable* state with `StringBuilder` in a way that could cause the old string's content to change.

This is an **API behavioral guarantee**, independent of how a JVM version stores characters in byte arrays, what internal encoding it uses, or how it optimizes memory. You do not need to rely on implementation details to trust the **content** independence between a snapshot and later edits.

Keep both directions clear: modifying `builder` does not change `snapshot`; conversely, `snapshot` does not provide a way to modify `builder`. `String` has no in-place character-editing methods such as `setCharAt`.

## 5. When to Call toString(), and Common Mistakes

**When you need a stable value:** call `toString()` once the desired content is assembled, for example before returning a result from a method, saving a message for later processing, or passing data to an API expecting `String`.

**While still building content:** continue using `StringBuilder` to append/edit. Calling `toString()` on every loop iteration just to inspect intermediate values can create many strings and incur time/memory costs proportional to text length. Create snapshots only at milestones where they are actually needed.

Pitfalls to avoid:

1. **Thinking a snapshot updates itself.** `String old = builder.toString(); builder.append("!");` does not modify `old`. Call `toString()` again if you want the new string.
2. **Thinking `toString()` makes the builder immutable or empty.** This method only returns a `String`; it does not alter the builder's content.
3. **Keeping an alias and thinking it is a snapshot.** `StringBuilder other = builder;` only creates another reference to the same object. Use `String other = builder.toString();` to obtain a stable value.
4. **Using `==` to compare the content of two `String`s.** `==` checks reference equality; use `equals` or `contentEquals` when checking content.
5. **Concluding `StringBuilder` is safe under concurrent multi-threaded mutation.** `StringBuilder` is not synchronized; if concurrent access exists, coordinate access so snapshots are taken in a consistent state. The immutability of the returned `String` does not resolve races while reading the builder.

## 6. Self-Check

Predict the output of the following snippet, then optionally place it inside `main` to run:

```java
StringBuilder b = new StringBuilder("AB");
String x = b.toString();

b.setCharAt(0, 'Z');
String y = b.toString();

b.deleteCharAt(1);
System.out.println(x + " | " + y + " | " + b);
```

Output:

```text
AB | ZB | Z
```

`x` keeps `AB`; `y` keeps `ZB`; `b` has `Z` left after deleting the character at position `1`. Each `toString()` call marks **a separate content snapshot at that point in time**.
