# Introducing StringBuilder for Repeated String Concatenation — Java 17+

## 1. When does concatenating Strings in a loop become a problem?

`String` in Java is **immutable**: once created, the content of a `String` object cannot be changed. The expression `text + value` produces a **new string value**. If a loop continuously accumulates data this way, the program may have to copy increasingly large intermediate contents:

~~~java
String result = "";
for (int i = 1; i <= 5; i++) {
    result += i; // A new String value is created and reassigned to result
}
System.out.println(result); // 12345
~~~

The snippet above is **functionally correct**, especially for small data. However, as the number of iterations and string length grow, repeated concatenation with `+=` can create many intermediate strings, increasing allocations and copying overhead. This is an important reason to use **`StringBuilder`**.

`StringBuilder` (in `java.lang`) is a **mutable sequence of characters**. It supports appending data into the same string builder via `append(...)`, rather than using immutable `String`s to store temporary results after every iteration.

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 5; i++) {
    builder.append(i);
}
String result = builder.toString();
System.out.println(result); // 12345
~~~

**Practical rule:** use `+` for a few simple parts because it is easy to read; consider `StringBuilder` when building content across many loop iterations, multiple branches, or a process with variable output size.

## 2. Workflow for using StringBuilder

Three basic steps:

1. **Create the builder**: `new StringBuilder()` or `new StringBuilder("prefix")`.
2. **Add content**: call `append(...)` inside the loop; each call updates the builder's content.
3. **Finalize the result**: call `toString()` to obtain a `String` value for an API, display, or return value.

~~~java
StringBuilder builder = new StringBuilder("Order:");
builder.append(' ').append(7);
builder.append(", paid=").append(true);

String message = builder.toString();
System.out.println(message); // Order: 7, paid=true
~~~

`append(...)` calls can be **chained** because `append` returns the same builder being used. Java provides overloads for `char`, `int`, `long`, `double`, `boolean`, `String`, `Object`, character arrays, and many other types.

What to distinguish:

~~~java
StringBuilder builder = new StringBuilder("A");
String text = builder.toString(); // "A"
builder.append("B");

System.out.println(builder); // AB
System.out.println(text);    // A
~~~

`text` is an **unchanging** `String` value. Editing the builder afterward does not change the string already extracted via `toString()`.

## 3. Joining a list in a loop: handling delimiters

A common scenario is building text from multiple elements separated by commas:

~~~java
static String joinNames(String[] names) {
    StringBuilder builder = new StringBuilder();
    for (int i = 0; i < names.length; i++) {
        if (i > 0) {
            builder.append(", ");
        }
        builder.append(names[i]);
    }
    return builder.toString();
}
~~~

If `names = {"Lan", "Minh", "An"}`, the result is `Lan, Minh, An`.

**Why check `i > 0`?** The delimiter only appears **before the second element onward**, so there is no leading or trailing comma. Using an index also handles empty-string elements consistently (if accepted).

| Input | Output |
|---|---|
| `{"Lan", "Minh", "An"}` | `Lan, Minh, An` |
| `{"Lan"}` | `Lan` |
| Empty array `{}` | Empty string `""` |
| `{"A", "", "B"}` | `A, , B` |

If you **only** need to join existing elements with a delimiter, Java also has a dedicated API:

~~~java
String value = String.join(", ", "Lan", "Minh", "An");
System.out.println(value); // Lan, Minh, An
~~~

There is no need to write a manual builder when `String.join` or `Collectors.joining` meets the requirements. A builder is more useful when adding content conditionally, per loop iteration, or mixing multiple data types.

## 4. StringBuilder is mutable, String is immutable: where do they differ?

~~~java
String first = "A";
String second = first + "B";

System.out.println(first);  // A
System.out.println(second); // AB
~~~

The expression `first + "B"` creates a result that is a different `String` in value; `first` still holds the text `A`.

~~~java
StringBuilder builder = new StringBuilder("A");
builder.append("B");

System.out.println(builder); // AB
~~~

The `append` call **mutates the builder's content**. If two variables reference the same builder, changes will be visible through both:

~~~java
StringBuilder a = new StringBuilder("Hi");
StringBuilder alias = a;
alias.append("!");

System.out.println(a); // Hi!
~~~

This code does not create a copy of the builder; `alias = a` only copies the **reference value**.

`final` does not make the builder's content immutable either:

~~~java
final StringBuilder b = new StringBuilder("A");
b.append("B"); // Valid
// b = new StringBuilder("C"); // Error: cannot reassign a final variable
~~~

**Conclusion:** `StringBuilder` can modify its content; `String` cannot modify its content. Do not pass a builder to code that might mutate it if you want to preserve your data unchanged.

## 5. Methods to learn first

| Method | Purpose | Example |
|---|---|---|
| `append(value)` | Append text/value to the end of the builder | `b.append(42)` |
| `toString()` | Get the result as a `String` | `String s = b.toString();` |
| `length()` | Number of UTF-16 code units currently held | `b.length()` |
| `charAt(index)` | Read one code unit at index | `b.charAt(0)` |
| `setCharAt(index, ch)` | Replace code unit at index | `b.setCharAt(0, 'J')` |
| `insert(index, value)` | Insert before position `index` | `b.insert(0, "Hi ")` |
| `delete(start, end)` | Delete range `[start, end)` | `b.delete(0, 3)` |
| `setLength(newLength)` | Change logical length; can truncate or expand | `b.setLength(0)` |
| `capacity()` | Current capacity in UTF-16 code units | `b.capacity()` |
| `ensureCapacity(n)` | Request minimum capacity | `b.ensureCapacity(100)` |

Editing example:

~~~java
StringBuilder b = new StringBuilder("Java");
b.append(" 17");
b.insert(5, "Core "); // Java Core 17
b.delete(5, 10);       // Java 17
b.setCharAt(0, 'j');   // java 17

System.out.println(b); // java 17
~~~

**Note on indices:** `charAt`, `setCharAt`, `insert`, and `delete` use **UTF-16 code unit** indices, not “one visible character = 1 position”. If the content includes emoji or supplementary Unicode characters outside the BMP, one code point can occupy two code units. Editing in the middle of a surrogate pair can make the text malformed.

`StringBuilder` has additional APIs such as `replace`, `reverse`, `indexOf`, and `substring`. Beginners only need to master `append`, `toString`, `length`, and delimiter management before branching out to more operations.

## 6. Length and capacity are not the same

- `length()`: **number of UTF-16 code units in the current content**.
- `capacity()`: **current capacity** of the buffer, always greater than or equal to `length()`.

~~~java
StringBuilder b = new StringBuilder(32);
System.out.println(b.length());   // 0
System.out.println(b.capacity()); // 32

b.append("Hi");
System.out.println(b.length());   // 2
System.out.println(b.capacity()); // 32
~~~

`new StringBuilder(32)` **does not create a 32-character string**; it creates an empty builder with an initial capacity of 32 UTF-16 code units.

If you roughly know the result size, specifying an initial capacity avoids several buffer expansions:

~~~java
StringBuilder report = new StringBuilder(128);
~~~

However, do not arbitrarily guess a huge size; base it on actual data. Internal reallocation/copying when exceeding capacity is an implementation detail and is normally managed automatically.

Calling `setLength(0)` clears the logical content, but **should not be treated as a secure wipe of secret data from all memory**. `StringBuilder` is not a dedicated secret-storage mechanism.

## 7. The repeated String concatenation pitfall: see via example, don't guess benchmarks

Look at two ways to produce the same result:

~~~java
static String withPlus(int count) {
    String text = "";
    for (int i = 1; i <= count; i++) {
        text += i;
    }
    return text;
}

static String withBuilder(int count) {
    StringBuilder b = new StringBuilder();
    for (int i = 1; i <= count; i++) {
        b.append(i);
    }
    return b.toString();
}
~~~

With `count = 5`, both return `"12345"`.

The difference is **how they build it**:

- `withPlus`: the `text` variable repeatedly receives new `String` results from concatenation across iterations; with long accumulated strings, this can incur heavy intermediate allocation/copying costs.
- `withBuilder`: the builder object is created once; `append` calls modify the content in the existing buffer.

You should not claim “`StringBuilder` is always faster in every expression”: the Java 17 compiler/JVM optimizes simple concatenations. You must **benchmark properly** if performance is a real concern; this section mainly guides **choosing an appropriate code structure**.

In repeated concatenation where the number of items grows with `n`, total copying work can grow substantially if each iteration has to process the entire accumulated string so far. A builder avoids that cost growth using a mutable buffer.

## 8. When is StringBuilder unnecessary?

**A short, clear concatenation expression:**

~~~java
String userName = "Lan";
int count = 3;
String message = "Hello " + userName + ", count=" + count;
System.out.println(message); // Hello Lan, count=3
~~~

Here `+` reads simply and fits well. Rewriting it with a builder does not necessarily improve clarity.

**Joining an existing list with a delimiter:**

~~~java
String csv = String.join(",", "A", "B", "C");
System.out.println(csv); // A,B,C
~~~

**Formatting from a template:**

~~~java
String summary = String.format(
        java.util.Locale.ROOT, "count=%d, ratio=%.2f", 3, 0.5);
System.out.println(summary); // count=3, ratio=0.50
~~~

When you need number formatting, alignment, locale, or decimal precision, `String.format` can be a better fit than a series of `append` calls.

**Choosing by intent:**

| Situation | Usually prefer |
|---|---|
| Combining 2–5 parts in a single statement | `+` |
| Joining existing strings with a delimiter | `String.join` |
| Building content across loops/branches, appending many times | `StringBuilder` |
| Formatting by a template with presentation rules | `String.format` or an appropriate formatter |

## 9. Complete, runnable Java 17 example

Save into a file named **`StringBuilderLoopDemo.java`**:

~~~java
public final class StringBuilderLoopDemo {
    private StringBuilderLoopDemo() {}

    static String joinNames(String[] names) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < names.length; i++) {
            if (i > 0) {
                builder.append(", ");
            }
            builder.append(names[i]);
        }
        return builder.toString();
    }

    static String withPlus(int count) {
        String result = "";
        for (int i = 1; i <= count; i++) {
            result += i;
        }
        return result;
    }

    static String withBuilder(int count) {
        StringBuilder builder = new StringBuilder();
        for (int i = 1; i <= count; i++) {
            builder.append(i);
        }
        return builder.toString();
    }

    public static void main(String[] args) {
        String[] names = {"Lan", "Minh", "An"};
        System.out.println("joined=" + joinNames(names));
        System.out.println("empty=<" + joinNames(new String[0]) + ">");
        System.out.println("plus=" + withPlus(5));
        System.out.println("builder loop=" + withBuilder(5));

        StringBuilder document = new StringBuilder("Java");
        document.append(' ').append(17).append('!');
        System.out.println("initial=" + document);
        document.setCharAt(0, 'j');
        document.insert(5, "Core ");
        System.out.println("inserted=" + document);
        document.delete(5, 10);
        System.out.println("deleted=" + document);

        String snapshot = document.toString();
        document.append(" again");
        System.out.println("snapshot=" + snapshot);
        System.out.println("changed=" + document);

        StringBuilder reserved = new StringBuilder(32);
        System.out.println("reserved length=" + reserved.length());
        System.out.println("reserved capacity=" + reserved.capacity());
        reserved.append("Hi");
        System.out.println("after append length=" + reserved.length());

        StringBuilder typed = new StringBuilder();
        typed.append("ok=").append(true)
                .append(", count=").append(3);
        System.out.println("typed=" + typed);
    }
}
~~~

**Requirements:** JDK 17 or newer, terminal opened in the directory containing `StringBuilderLoopDemo.java`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StringBuilderLoopDemo.java
java -cp . StringBuilderLoopDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StringBuilderLoopDemo.java
java -cp . StringBuilderLoopDemo
~~~

**Exact expected output:**

~~~text
joined=Lan, Minh, An
empty=<>
plus=12345
builder loop=12345
initial=Java 17!
inserted=java Core 17!
deleted=java 17!
snapshot=java 17!
changed=java 17! again
reserved length=0
reserved capacity=32
after append length=2
typed=ok=true, count=3
~~~

**Explanation of easily confused lines:**

- `insert(5, "Core ")` inserts before index 5 of `"java 17!"`, becoming `"java Core 17!"`.
- `delete(5, 10)` deletes the range `[5, 10)`, returning the content to `"java 17!"`.
- `snapshot` preserves the text at the time of `toString()`, remaining unchanged when `" again"` is appended to the builder.
- `new StringBuilder(32)` has `capacity() == 32`, yet `length() == 0` before `append`.
- Both `withPlus(5)` and `withBuilder(5)` produce the same text; the illustration demonstrates **string-building structure**, not speed measurement.

The program is standalone, requiring no Maven, Gradle, or libraries outside the JDK.

## 10. Common mistakes

| Practice / mistake | Why pay attention? | How to handle |
|---|---|---|
| `String s = ""; for (...) s += value;` | Can repeatedly allocate/copy when accumulating large content | Create a `StringBuilder` outside the loop |
| `new StringBuilder()` inside every iteration | Loses the benefit of reusing one builder | Initialize once **before** the loop if the goal is one result |
| Forgetting `toString()` when an API expects `String` | `StringBuilder` and `String` are two different types | Return `builder.toString()` |
| `builder = builder.append(x)` in every iteration | Valid, but reassigning the variable is unnecessary | Call `builder.append(x)` directly |
| Writing a manual builder instead of `String.join` for simple lists | Adds unnecessary code | Use built-in APIs when intent is clear |
| Forgetting separators between elements | Results stick together and are hard to read | Add `", "` based on index or state |
| Using `capacity()` to get content length | Capacity is not length | Use `length()` |
| Thinking `final StringBuilder` cannot append | final locks the reference variable, not the object | Can append, cannot reassign the variable |
| Calling `charAt`/`delete` with invalid indices | Can throw `IndexOutOfBoundsException` | Check bounds against `length()` |
| Treating index as visible character count | UTF-16 code units may differ from Unicode code points | Choose APIs by the Unicode unit to process |
| Sharing a mutable builder across multiple threads | No internal synchronization | Keep builders thread-local or synchronize explicitly |
| Reusing a shared builder across tasks requiring isolation | Content may be altered unexpectedly | Create a separate builder per task |

### A subtle Java trap: appending `null`

~~~java
StringBuilder builder = new StringBuilder();
builder.append((Object) null);
System.out.println(builder); // null
~~~

`append((Object) null)` appends **four characters**: `n`, `u`, `l`, `l`. However, some overloads, especially with a null character array, behave differently; when data can be null, choose the overload and display policy explicitly rather than passing an ambiguous null value.

## 11. Exercises with answers

### Exercise A — joining numbers with a builder

Create the string `1-2-3-4` using a loop.

**Answer:**

~~~java
StringBuilder b = new StringBuilder();
for (int i = 1; i <= 4; i++) {
    if (i > 1) {
        b.append('-');
    }
    b.append(i);
}
System.out.println(b.toString()); // 1-2-3-4
~~~

### Exercise B — String snapshot

~~~java
StringBuilder b = new StringBuilder("A");
String snapshot = b.toString();
b.append('B');
System.out.println(snapshot);
System.out.println(b);
~~~

**Answer:**

~~~text
A
AB
~~~

Because `snapshot` is an immutable String obtained from the builder before appending `B`.

### Exercise C — length or capacity?

~~~java
StringBuilder b = new StringBuilder(50);
b.append("Hi");
System.out.println(b.length());
System.out.println(b.capacity());
~~~

**Answer:**

~~~text
2
50
~~~

### Exercise D — is a builder needed?

~~~java
String greeting = "Hello, " + name + "!";
~~~

**Answer:** usually **not needed** if only combining a few components once. This is a clear expression and modern Java compilers/JVMs can optimize it. Use a builder when there is a reason such as looping many times or multi-step construction.

### Exercise E — modifying an element of an already finalized string?

~~~java
StringBuilder builder = new StringBuilder("Java");
String s = builder.toString();
builder.setCharAt(0, 'K');
System.out.println(s);
System.out.println(builder);
~~~

**Answer:**

~~~text
Java
Kava
~~~

## 12. Self-assessment checklist

- [ ] Understand why repeated `String += value` can be costly.
- [ ] Know how to create `StringBuilder` **once before the loop**.
- [ ] Use `append` to add values and `toString()` to obtain the final String.
- [ ] Understand `StringBuilder` is mutable, `String` is immutable, and snapshots do not change along with the builder.
- [ ] Know how to add delimiters without extra leading/trailing separators.
- [ ] Distinguish `length()` from `capacity()`; understand the capacity constructor.
- [ ] Know the basic methods `append`, `insert`, `delete`, `setCharAt`.
- [ ] Choose `+` or `String.join` when simpler.
- [ ] Recognize that character indices operate on UTF-16 code units.
- [ ] Do not share a mutable builder unsynchronized across threads.
- [ ] Compile and run `StringBuilderLoopDemo.java` with JDK 17+, comparing with expected output.

**Conclusion:** `StringBuilder` is useful when you need to **concatenate strings repeatedly or build content across multiple steps**, because it updates a mutable buffer via `append` and then creates the final `String` via `toString()`. Using it in the right places keeps code clear and typically reduces intermediate string allocations; for a few short concatenations, `+` remains a readable and sensible choice.
