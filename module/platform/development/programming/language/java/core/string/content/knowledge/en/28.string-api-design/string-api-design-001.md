# Choosing `String` or `CharSequence` for Java API Parameters

## 1. Principle: choose according to the contract the method needs

Java has two familiar ways to describe a text parameter: `String` is a concrete class whose content is **immutable**; `CharSequence` is an **interface** describing a readable sequence of characters. `String implements CharSequence`, so any `String` object can be passed to a `CharSequence` parameter.

**Use `CharSequence`** when the method only needs to iterate, count, or analyze characters and can work properly with multiple source types such as `String`, `StringBuilder`, `StringBuffer`, and `CharBuffer`. **Use `String`** when the method truly needs an immutable value, internal APIs require `String`, long-term state storage is needed, or many `String`-specific operations are used.

Example of the intent behind two APIs:

```java
// Read characters only during the call:
int countAsciiDigits(CharSequence text);

// Store the label as an immutable value:
void setPermanentLabel(String label);
```

These are illustrative signatures, not a standalone program. The decision lies in **usage semantics**, not simply picking the most general type. `CharSequence` does not promise immutability, does not automatically provide thread safety, and does not implicitly avoid copying data.

## 2. Comparison of key characteristics

| Criterion | `String` | `CharSequence` |
| --- | --- | --- |
| Kind | Concrete `final` class. | Interface for a character sequence. |
| Input data | `String` value (or `null` if the API allows). | `String`, `StringBuilder`, `StringBuffer`, `CharBuffer`, custom implementations. |
| Immutability | The content of a `String` object does not change. | **Not guaranteed**: the actual object may be mutable. |
| Common operations | `length()`, `charAt()`, `subSequence()`, `toString()`. | The same operations above, along with `chars()` and `codePoints()` in modern Java. |
| `String`-specific operations | `strip()`, `startsWith()`, `substring()`, `replace()`, `split()`, ... | Not part of the interface contract. |
| Value comparison | `String.equals`/`hashCode` are content-consistent with `String`. | The interface does not enforce that every implementation's `equals`/`hashCode` is content-based. |
| Storing the value for later | Suitable thanks to immutability. | Must consider source mutation; usually capture a `String` before storing. |
| Cost | Already a `String`; no conversion needed before calling APIs requiring `String`. | Can read multiple sources directly, though sometimes requires `toString()` and allocation. |

**Note:** A variable of type `String` can still be reassigned a reference to another `String`; it is the **content of each `String` object** that is immutable. Furthermore, a `CharSequence` parameter does not make a `StringBuilder` source read-only for other parts of code that still hold a reference to it.

## 3. Complete Java 17+ example

Create the file `CharSequenceApiDemo.java`:

```java
import java.nio.CharBuffer;
import java.util.Locale;
import java.util.Objects;

public class CharSequenceApiDemo {
    // Method only needs to read the character sequence via the interface.
    static int countAsciiDigits(CharSequence text) {
        Objects.requireNonNull(text, "text");
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch >= '0' && ch <= '9') {
                count++;
            }
        }
        return count;
    }

    // Convert to String when a stable value is needed for processing.
    static String normalizedCode(CharSequence text) {
        String stable = Objects.requireNonNull(text, "text").toString();
        return stable.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String fixed = "A7B";
        StringBuilder builder = new StringBuilder("x2");
        CharBuffer buffer = CharBuffer.wrap("p45");

        System.out.println("String: " + countAsciiDigits(fixed));
        System.out.println("StringBuilder: " + countAsciiDigits(builder));
        System.out.println("CharBuffer: " + countAsciiDigits(buffer));

        String captured = normalizedCode(builder);
        builder.append("9");
        System.out.println("Captured: " + captured);
        System.out.println("Current: " + normalizedCode(builder));

        System.out.println("Content equals: "
                + "key".contentEquals(new StringBuilder("key")));
        System.out.println("Object equals: "
                + Objects.equals("key", new StringBuilder("key")));
    }
}
```

Compile and run:

```bash
javac CharSequenceApiDemo.java
java CharSequenceApiDemo
```

Output:

```text
String: 1
StringBuilder: 1
CharBuffer: 2
Captured: X2
Current: X29
Content equals: true
Object equals: false
```

`countAsciiDigits` accepts three text types and only reads `length()` and `charAt()`. `normalizedCode` captures the data as a `String` before calling `strip()` and `toUpperCase(Locale.ROOT)`; the `captured` string remains `"X2"` even though the caller modifies `StringBuilder` to `"x29"` afterward. This illustrates the difference between **accepting a broad parameter** and **retaining an immutable value**.

## 4. When `CharSequence` is more appropriate

A method that **processes synchronously during the call**, using only `length()`, `charAt()`, and `subSequence()` for reading, can often accept `CharSequence`. The API is more flexible for callers holding data in a `StringBuilder` or `CharBuffer`.

For example:

```java
static boolean containsAtSign(CharSequence input) {
    Objects.requireNonNull(input, "input");
    for (int i = 0; i < input.length(); i++) {
        if (input.charAt(i) == '@') {
            return true;
        }
    }
    return false;
}
```

This is an **illustrative** function, not a standalone runnable file, and checking for an `@` sign is not equivalent to email validation. The `CharSequence` type expresses exactly what the algorithm needs: reading each character unit.

Built-in Java APIs also reflect this design approach: `Pattern.matcher(CharSequence)` accepts an abstract input source for regex matching; `Appendable.append(CharSequence)` accepts general text data. Not every text operation needs to require `String`.

**Limitation to state clearly:** If a `StringBuilder` is modified concurrently by another thread while the function calls `length()` or `charAt()`, the result may be inconsistent; an index error may even occur if the length changes. This interface **does not provide** a synchronization mechanism. The API contract must require the caller not to modify during reading, synchronize appropriately, or snapshot to a `String`.

Accepting `CharSequence` also does not automatically make code more efficient. A `CharBuffer` has `position`/`limit` changing the observed region, different implementations have different read costs, and algorithms that depend on `String` may have to call `toString()` later.

## 5. When `String` is more appropriate

Choose `String` if:

- **Long-term storage:** storing in member fields, caches, queues, asynchronous jobs, or results that the caller may hold after the call finishes.
- **Value must remain stable:** validation, hashing, and subsequent business processing must rely on the exact same content received.
- **Using `String`-specific methods:** `strip()`, `replace()`, `split()`, `startsWith()`, or forwarding to a library that requires `String`.
- **Comparing or storing content-based keys:** `String.equals`, `hashCode`, and `String` immutability give key values stable behavior.
- **Intentionally narrow public contract:** the API only supports a text value normalized to `String`, or needs to preserve backward compatibility with older versions.

You can even accept `CharSequence` at the public boundary and capture it as a `String` immediately when storage is needed:

```java
import java.util.Objects;

final class Label {
    private final String value;

    Label(CharSequence input) {
        this.value = Objects.requireNonNull(input, "input").toString();
    }

    String value() {
        return value;
    }
}
```

This is a **single-class illustration**, not a standalone `main` program. After the constructor receives a `StringBuilder`, the `Label` object holds a stable `String` value that does not change with the source `StringBuilder`. If you only want to allow `String` from the start, declaring a `String` parameter is also a valid design.

If you both **validate data and store it**, capture a `String` first, validate **that exact captured copy**, and store that same copy. Validating a mutable `CharSequence` directly and capturing/storing later can cause the validated value to differ from the value actually used.

## 6. Ownership rules when using \`CharSequence\`

\`CharSequence\` allows an API to read multiple source types, but it does not make \`StringBuilder\` immutable. If reading only immediately within the call, document the requirement that the source is not modified concurrently. If you need to keep the value for a cache, queue, or asynchronous processing, **snapshot it once** upon receipt:

~~~java
final class Label {
    private final String value;

    Label(CharSequence source) {
        this.value = java.util.Objects.requireNonNull(source, "source")
                .toString();
    }

    String value() { return value; }
}
~~~

The captured \`String\` copy does not change after the caller modifies the source. However, calling \`toString()\` while a mutable source **is being modified concurrently** is not implicitly an atomic snapshot; an ownership handoff agreement or synchronization is required. \`subSequence()\` may also be a data-sharing view depending on the implementation. When an API returns a view, it must publish its lifecycle and update mechanism.

## 7. Content comparison requires specified semantics

\`String.equals(Object)\` compares content against a \`String\`, but \`CharSequence\` implementations do not have a unified \`equals/hashCode\` rule. When you only want to compare the current text:

~~~java
CharSequence candidate = new StringBuilder("key");
System.out.println("key".contentEquals(candidate)); // true
System.out.println("key".equals(candidate));        // false
~~~

For long-term stored keys, use a \`String\` snapshot and \`Map<String, ...>\` when business logic requires text-based equality. Do not assume \`HashMap<CharSequence, ...>\` will merge source types with the same characters or guarantee stable keys. Detailed analysis of \`StringBuilder\`, \`StringBuffer\`, \`CharBuffer\`, and \`subSequence\` belongs to the deep-dive article immediately following this parameter-type selection article.

## 8. Unicode and character counting units

`String` and `CharSequence` in Java primarily represent sequences of **UTF-16 code units**:

- `length()` counts the number of UTF-16 code units, not necessarily the number of Unicode code points.
- `charAt(i)` returns a 16-bit `char`; code points outside the BMP may require a **surrogate pair** and occupy two positions.
- `codePoints()` can iterate over code points, but a user-perceived "character" (*grapheme cluster*) may consist of multiple combining code points.

Java example inside a method:

```java
String emoji = "😀";
System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
```

If an API needs to count "10 user-perceived characters", neither `String.length()` nor `CharSequence.length()` is sufficient for all Unicode; an appropriate grapheme segmentation algorithm or library is needed. Choosing `String` or `CharSequence` does not by itself determine the counting unit for business logic.

## 9. Compatibility when changing a published API signature

Suppose an existing library has:

```java
public void submit(String text) {
    // Existing logic.
}
```

Changing it directly to `submit(CharSequence text)` may still allow **source code calling with `String`** to recompile because `String implements CharSequence`. However, the signature at the **JVM bytecode descriptor** level changes: a previously compiled program looking for `submit(String)` may fail to run against a library version that only has `submit(CharSequence)` and encounter `NoSuchMethodError`.

To consider binary compatibility, you can keep the old method and **add an overload**:

```java
public void submit(String text) {
    // Preserve existing behavior.
}

public void submit(CharSequence text) {
    submit(Objects.requireNonNull(text, "text").toString());
}
```

This is an illustrative snippet inside a class with `import java.util.Objects;`. When both overloads exist, a call with a variable of compile-time type `String` selects the `String` overload because it is more specific. Other overloads can cause ambiguity or change call resolution; test the API from the caller's perspective. Adding overloads also increases the burden of maintaining consistent behavior. If the old API already meets requirements, keeping `String` may be simpler.

## 10. Handling `null`, performance, and API contracts

**`null` policy:** both `String` and `CharSequence` are reference types, so both can receive `null`. Clearly choose valid/invalid cases and express them through documentation, appropriate annotations, or `Objects.requireNonNull(text, "text")` if required.

**Do not assume `toString()` is free:** For `String`, `toString()` returns the object itself; for `StringBuilder` and other sources, it may create/copy a new string. If only iterating characters short-term and the source does not change during the call, reading `CharSequence` directly can avoid unnecessary conversion. If stability matters, creating a snapshot is an intentional cost.

**Do not store mutable references as-is in asynchronous processing:** Before passing data to a thread/task/queue, determine who owns the source and when the source can be modified. Capture a `String` at the boundary if you need to preserve the exact received content. Do not rely on the `CharSequence` parameter type appearing read-only to infer thread safety.

**Do not force every API onto an interface at all costs:** A library should choose parameter types that accurately reflect its data model. If every step of the method needs `String` and the caller already has `String`, a `String` parameter is the clear choice; if the algorithm only needs to traverse characters from multiple sources, `CharSequence` is the natural choice.

A decision checklist:

| Question | Suggestion |
| --- | --- |
| Only reading characters immediately inside the method, without retaining the source? | Consider `CharSequence`. |
| Need to accept `StringBuilder`, `CharBuffer` directly? | `CharSequence` provides flexibility. |
| Need to store and use later? | Use `String` or accept `CharSequence` and snapshot it. |
| Need methods exclusive to `String`? | Choose `String` or convert at a clear boundary. |
| Need content-based keys? | `String` has suitable equality/hash and immutability. |
| Changing a library's public signature? | Check source/binary compatibility first. |

## 11. Practice questions

1. Why can `countAsciiDigits(CharSequence)` accept a `StringBuilder` without requiring the caller to convert it to `String`? In what situation must concurrent source modification still be watched out for?
2. After `normalizedCode(builder)` returns `"X2"`, why does `builder.append("9")` not modify `captured`?
3. Why can `String.contentEquals(CharSequence)` yield a different result from `String.equals(Object)` with a `StringBuilder`?
4. When creating an asynchronous job that accepts `CharSequence`, when should you capture a `String` so the job processes the exact data at enqueue time?
5. If `submit(String)` is changed to `submit(CharSequence)`, why might an application compiled against the old version fail even though the call in source code remains valid?
6. Why is `length()` not always equal to the number of Unicode code points or user-perceived characters?

**Conclusion:** Use `CharSequence` when the contract only needs to **read a character sequence** and supporting multiple text sources is beneficial. Use `String` when you need **immutable values, stable comparison/storage, or specialized APIs**. When accepting `CharSequence` and needing to retain it long-term, capture a `String` at an appropriate boundary and handle source ownership and synchronization properly.