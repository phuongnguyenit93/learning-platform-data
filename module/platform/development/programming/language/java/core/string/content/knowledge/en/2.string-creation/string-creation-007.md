# Creating a `String` from `StringBuilder` or `StringBuffer` in Java

`StringBuilder` and `StringBuffer` are used to build, concatenate, or modify strings repeatedly. Once finished, the program usually needs a `String` value to return from a method, pass to an API expecting `String`, store in a data object, or display. The most common and clearest way to convert is to call `toString()`.

## 1. How Are the Three Types Related?

- `String` is an **immutable** string type: once created, a `String`'s content cannot be modified in place. Operations like `concat()` or `replace()` produce another `String` result when needed.
- `StringBuilder` is a **mutable** character buffer. Operations such as `append()`, `insert()`, `delete()`, `replace()`, and `reverse()` modify the buffer. This type is not designed for concurrent modification by multiple threads without external synchronization.
- `StringBuffer` can also modify its content, but many of its public methods are synchronized (`synchronized`). It is useful when that synchronization behavior is needed; however, a sequence of multiple method calls still requires proper protection if it must execute as an atomic operation.

Both buffer classes implement `CharSequence`, yet `CharSequence` is not `String`. A variable or API requiring the exact `String` type must be given a converted value.

## 2. Converting with `toString()`

Standard syntax:

```java
StringBuilder builder = new StringBuilder("Hello");
builder.append(" Java");
String text = builder.toString();

StringBuffer buffer = new StringBuffer("Hello");
buffer.append(" Java");
String otherText = buffer.toString();
```

`toString()` returns the current content as a `String`. This call **does not clear, close, or modify** the source buffer; you can continue using `builder` or `buffer` afterward.

### Runnable Example: Capturing `StringBuilder` Content

Save to `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Hello");
        builder.append(" Java");

        String before = builder.toString();
        builder.append("!");

        String after = builder.toString();

        System.out.println("before = " + before);
        System.out.println("after = " + after);
        System.out.println("builder = " + builder);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac Main.java
java Main
```

Output:

```text
before = Hello Java
after = Hello Java!
builder = Hello Java!
```

`before` is a **snapshot of the content at the time of conversion**. When `!` is appended to `builder`, `before` retains its old value; a subsequent `toString()` call retrieves the new content. This is an important distinction between a `String` value and a mutable buffer.

### Runnable Example: `StringBuffer`

Save to `BufferExample.java`:

```java
public class BufferExample {
    public static void main(String[] args) {
        StringBuffer buffer = new StringBuffer("A");
        buffer.append("B");

        String snapshot = buffer.toString();
        buffer.replace(0, 1, "X");

        System.out.println("snapshot = " + snapshot);
        System.out.println("buffer = " + buffer);
    }
}
```

Run with `javac BufferExample.java` then `java BufferExample`. Output:

```text
snapshot = AB
buffer = XB
```

Even though `StringBuffer` has synchronized methods, the returned result is still an immutable `String`, not live-linked to `buffer`'s content.

## 3. Other Ways to Convert

Java also provides constructors that directly accept buffer objects:

```java
StringBuilder builder = new StringBuilder("Java");
String fromBuilder = new String(builder);

StringBuffer buffer = new StringBuffer("Core");
String fromBuffer = new String(buffer);
```

The two constructors `String(StringBuilder)` and `String(StringBuffer)` create a `String` from the current content of the source object. For general conversion purposes, `toString()` is easier to read and is the default choice.

You can also use `String.valueOf(Object)`:

```java
StringBuilder builder = new StringBuilder("Java");
String text = String.valueOf(builder); // "Java"
```

For a **non-null** reference, this call uses the object's `toString()` representation. The difference is that `String.valueOf(Object)` with a `null` reference returns the character string `"null"`, whereas calling `toString()` on a `null` reference throws `NullPointerException`:

```java
StringBuilder builder = null;
String safeRepresentation = String.valueOf(builder); // "null"
// String text = builder.toString();                 // NullPointerException
```

Do not confuse the string literal `"null"` with the reference value `null`. If business rules want an empty string, handle it explicitly:

```java
StringBuilder builder = null;
String text = builder == null ? "" : builder.toString();
```

| Syntax | Result | When to use |
| --- | --- | --- |
| `builder.toString()` / `buffer.toString()` | `String` containing current content | General conversion when the source is guaranteed non-`null` |
| `new String(builder)` / `new String(buffer)` | `String` from buffer content | When you want to explicitly express creation via constructor |
| `String.valueOf(builder)` | String from `toString()`; `null` source becomes `"null"` | When converting an object to a string representation and accepting this `null` rule |

Avoid `new String(builder.toString())`: the constructor wrapper generally adds no meaning beyond `builder.toString()` and can create unnecessary extra work.

## 4. Conversion Timing and Immutability

Typical workflow:

1. Initialize a `StringBuilder` or `StringBuffer`.
2. Append, insert, or modify content using buffer operations.
3. Call `toString()` **after finishing** the content you need.
4. Store, pass, or return the resulting `String`.

If you keep modifying the buffer after step 3, the already-created result does not update automatically. To get the new version, call `toString()` again.

Do not compare the content of two results with `==`. That operator compares the references of the two objects; use `equals()` to compare contents:

```java
StringBuilder builder = new StringBuilder("abc");
String a = builder.toString();
String b = new String(builder);

System.out.println(a.equals(b)); // true
```

The example above intentionally checks content only. You should not rely on whether two conversions return the same or different objects under `==`; what matters in an application is the string value.

Conversion typically produces a `String` value corresponding to the buffer's content, so there is no need to call `toString()` repeatedly after **every** `append()` if only the final result is used. You can reuse a single `String` variable when multiple places need the same snapshot.

## 5. Practical Example: Building a Report Line

We join multiple parts with `StringBuilder`, then return a `String` to the caller:

```java
public class ReportExample {
    static String buildSummary(String[] names) {
        StringBuilder result = new StringBuilder();

        for (int i = 0; i < names.length; i++) {
            if (i > 0) {
                result.append(", ");
            }
            result.append(names[i]);
        }

        return result.toString();
    }

    public static void main(String[] args) {
        String summary = buildSummary(new String[] {"Lan", "Minh", "An"});
        System.out.println(summary);
    }
}
```

Save to `ReportExample.java`, run `javac ReportExample.java` and `java ReportExample`. Output:

```text
Lan, Minh, An
```

In `buildSummary()`, the buffer is an internal implementation detail; the method returns an immutable `String` type according to its declared contract. Calling `toString()` at the end of the method avoids capturing intermediate snapshots before the loop completes. For simple list joining like this example, `String.join(", ", names)` is also a clean option; you do not need to manually use `StringBuilder` in every case.

If you need to build content in code using `StringBuffer`, the return step is similar:

```java
static String finish(StringBuffer buffer) {
    return buffer.toString();
}
```

The `finish` snippet is an **illustrative method** that must be placed inside an appropriate Java class; it is not a standalone runnable program.

## 6. Multi-Threading Considerations

With `StringBuilder`, do not read/modify the same instance from multiple threads without proper synchronization. Calling `toString()` while another thread is mutating the `StringBuilder` does not automatically produce a safe, consistent snapshot.

With `StringBuffer`, methods like `append()` and `toString()` are synchronized on the object. A single `toString()` call can capture consistent content under that synchronization, yet **a multi-step sequence of actions** (for example: checking length, then appending data, then retrieving the string) does not automatically become an atomic transaction across threads. If steps must stay together, design synchronization around the entire operation.

Do not choose `StringBuffer` solely because the result must be a `String`: both classes convert to `String`. In single-threaded code, `StringBuilder` is usually the appropriate choice.

## 7. Common Mistakes and How to Fix Them

**1. Confusing the result with the mutable buffer.** After `String snapshot = builder.toString();`, modifying `builder` does not modify `snapshot`. Call `toString()` again if you want updated content.

**2. Calling `toString()` on a `null` object.** A `NullPointerException` occurs before creating the `String`. Check for `null` or use `String.valueOf()`'s convention when you genuinely want `"null"`.

**3. Converting too early or too often.** If an API needs the finished text, wait until all appends/edits are done before calling it. When intentional snapshots at multiple checkpoints are needed, each call makes sense.

**4. Using `==` to verify the result.** Use `equals()` for content comparison, and `equalsIgnoreCase()` only when case-insensitive comparison is desired.

**5. Assuming `StringBuffer` makes every multi-step sequence automatically thread-safe.** Per-method synchronization is no substitute for synchronizing the entire workflow.

**6. Creating `new String(builder.toString())` as a required step.** There is no need to wrap with `new String(...)` to obtain a `String`; `toString()` already returns the exact type.

## 8. Self-Check

**Question 1.** If `StringBuilder b = new StringBuilder("A"); String s = b.toString(); b.append("B");`, what are the values of `s` and `b.toString()`?

**Answer:** `s` is still `"A"`, while `b.toString()` is `"AB"`, because `s` is an immutable value created before appending.

**Question 2.** Do you have to use `new String(buffer)` to convert a `StringBuffer` to a `String`?

**Answer:** No. `buffer.toString()` is the direct and usually preferred way; the `new String(buffer)` constructor is also valid.

**Question 3.** Why might you choose `StringBuffer` in multi-threaded code, and what should you watch out for?

**Answer:** `StringBuffer`'s methods are synchronized, including `toString()`. However, the atomicity of a multi-call workflow still needs to be controlled separately.

**Remember:** Use `toString()` to obtain a `String` from `StringBuilder` or `StringBuffer`. The created value reflects the content at conversion time and does not change with subsequent buffer modifications.
