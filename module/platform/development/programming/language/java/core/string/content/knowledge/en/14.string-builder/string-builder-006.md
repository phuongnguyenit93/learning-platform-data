# `StringBuilder.setCharAt()` and `setLength()` in Java

## 1. Lesson Objectives

`StringBuilder` is an object holding a **mutable** sequence of UTF-16 character units. Unlike immutable `String`, `StringBuilder` lets you directly modify accumulated content without reassigning the object on every transformation.

The two methods in this lesson serve two different tasks:

- `setCharAt(int index, char ch)`: **replaces exactly one `char` unit** at an existing position. The method neither adds nor removes characters, so **`length()` does not change**.
- `setLength(int newLength)`: changes the **logical length** of the sequence. If decreased, trailing characters are dropped from the logical content; if increased, new positions are filled with the **NUL character `'\u0000'`**. The method does not fill with spaces and does not restore previously truncated characters.

Both mutate the `StringBuilder` object itself and have return type `void`, unlike methods such as `append`/`insert` that return the builder for chaining.

Quick look example:

```java
StringBuilder sb = new StringBuilder("Java");

sb.setCharAt(1, 'O'); // Content: "JOva", length = 4.
sb.setLength(2);      // Content: "JO", length = 2.
sb.setLength(5);      // Content: "JO\0\0\0", length = 5.
```

This is an illustrative snippet inside a method body. `\0` in comments and examples denotes **a single UTF-16 unit with value 0**, not the two characters `\` and `0`.

## 2. Distinguishing `length` from `capacity` and Valid Index Ranges

A `StringBuilder` has two distinct quantities:

| Concept | API | Meaning |
| --- | --- | --- |
| **Logical length** | `sb.length()` | Number of `char` units currently belonging to the builder's content |
| **Storage capacity** | `sb.capacity()` | Number of `char` units the builder can hold without necessarily needing to grow storage |
| **Access/modify content** | `sb.charAt(i)`, `sb.setCharAt(i,ch)` | Index must satisfy **`0 <= i < length()`** |
| **Change logical length** | `sb.setLength(n)` | `n >= 0`; can be shorter or longer than the current length |

Do not use `capacity()` as the valid bound for `setCharAt`. For example, if a builder has `length() == 2` yet `capacity() == 18`, index `2` is **still invalid** for `setCharAt`, because it is *past* the existing content. To write at index 2 with `setCharAt`, you must first increase `length` to at least 3, or use `append` to add data as intended.

`capacity()` is a storage capability detail exposed by the API, whereas valid content is always determined by `length()`. When increasing `length` beyond `capacity`, the builder may need to allocate additional capacity. Decreasing `length` does not mean capacity shrinks correspondingly; if you want to proactively request shrinking, see `trimToSize()`, though that is a performance/memory decision separate from the semantics of these two methods.

## 3. `setCharAt(index, ch)`: Modifying One Element Without Changing Length

Signature:

```java
public void setCharAt(int index, char ch)
```

- `index`: position of an existing **UTF-16 code unit** in the sequence, 0-based.
- `ch`: the new `char` value overwriting that unit.
- Return value: **`void`**.
- Index condition: `0 <= index < length()`. Violations throw `IndexOutOfBoundsException` (some implementations use the subclass `StringIndexOutOfBoundsException`).

Example:

```java
StringBuilder name = new StringBuilder("Jovo");
name.setCharAt(1, 'a');
name.setCharAt(3, 'a');
System.out.println(name);          // Java
System.out.println(name.length()); // 4
```

This is a snippet placed inside `main`. Only positions 1 and 3 are modified; length remains 4. The method **does not find all matching characters**; it modifies the exact specified index. If you want to replace all `'o'` letters, you can loop through positions and call `setCharAt` when `charAt(i) == 'o'`, or use an alternative API suited to your needs.

Save as `SetCharAtDemo.java`:

```java
public class SetCharAtDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        String original = builder.toString();

        builder.setCharAt(1, 'O');
        builder.setCharAt(3, '!');
        System.out.println(builder);
        System.out.println(builder.length());
        System.out.println(original);

        builder.setCharAt(1, builder.charAt(1));
        System.out.println(builder);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 SetCharAtDemo.java
java SetCharAtDemo
```

```text
JOv!
4
Java
JOv!
```

`original` is an immutable `String` capturing the builder's content before modification; it remains `Java`. `setCharAt` mutates the builder in place; reassigning the character already present produces no content difference.

### `setCharAt` Cannot Be Chained

`append` typically returns the builder, whereas `setCharAt` returns `void`:

```java
StringBuilder sb = new StringBuilder("abc");
sb.setCharAt(0, 'A');
sb.append('!'); // Valid.

// sb.setCharAt(0, 'Z').append('!'); // Does NOT compile: setCharAt returns void.
```

This is an illustrative snippet and the last line is commented out so the program stays valid. Do not build API chains assuming every `StringBuilder` method returns the builder itself.

## 4. `setLength(newLength)`: Three Cases

Signature:

```java
public void setLength(int newLength)
```

`newLength` must be **non-negative**. When called, one of three situations occurs:

| Compared to Old Length | Behavior |
| --- | --- |
| `newLength < oldLength` | Drops the logical content from index `newLength` to the end |
| `newLength == oldLength` | Content does not change |
| `newLength > oldLength` | Increases length; every new position receives `'\u0000'` (NUL), not `' '` or `'0'` |

Example:

```java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(3); // "ABC"
sb.setLength(5); // "ABC\0\0", NOT "ABCDE"
```

Reducing to 3 removes `D` and `E` from the logical content. Increasing to 5 afterward fills in **two new NUL values**, rather than restoring the two old letters. This can be hard to spot if you only print with `System.out.println`, because NUL characters do not render like normal letters.

### Why Pay Special Attention to the NUL Character?

`'\u0000'` is the character with code 0; it is **different from**:
- `'0'`: the digit zero, code `U+0030`.
- `' '`: a space, code `U+0020`.
- `'\n'`: a newline, code `U+000A`.
- The empty string `""`: contains zero `char` units.

When `StringBuilder` is extended by `setLength`, the logical content contains NUL characters. Different printing tools, storage systems, protocols, or non-JVM applications may handle NUL differently; do not assume those positions are spaces or nonexistent.

## 5. Standalone Example: Observing NUL Without Printing Raw Control Characters to the Screen

For clear and reproducible output, we create a helper `visible` that prints NUL as the two visible characters `\` and `0`, instead of writing code 0 directly to the terminal.

Save as `SetLengthDemo.java`:

```java
public class SetLengthDemo {
    static String visible(CharSequence text) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '\0') {
                out.append("\\0");
            } else {
                out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("ABCDE");
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(3);
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(5);
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setCharAt(3, 'X');
        System.out.println(visible(sb) + " / " + sb.length());

        sb.setLength(0);
        System.out.println("empty=" + (sb.length() == 0));

        sb.append("Hi");
        System.out.println(visible(sb) + " / " + sb.length());
    }
}
```

```bash
javac -encoding UTF-8 SetLengthDemo.java
java SetLengthDemo
```

```text
ABCDE / 5
ABC / 3
ABC\0\0 / 5
ABCX\0 / 5
empty=true
Hi / 2
```

Explanation:
1. Starts at length 5.
2. `setLength(3)` drops `DE` from the logical sequence.
3. `setLength(5)` adds two NUL positions.
4. `setCharAt(3, 'X')` writes to **one** of the new positions (index 3 is now valid), while position 4 remains NUL.
5. `setLength(0)` sets the logical sequence to empty.
6. `append("Hi")` starts appending from the beginning of the current logical sequence, so the builder displays `Hi` with length 2.

**Security note:** `setLength(0)` changes the logical length; it is **not an API that guarantees securely wiping all copies of sensitive data in memory**. If handling secrets, do not rely on `StringBuilder.setLength(0)` to conclude that data has been erased.

## 6. Exceptions and Boundary Conditions

### `setCharAt` Uses an Existing Element Index, Not an Insertion Position

If a builder has length `n`:
- `setCharAt(0, ch)` is valid when `n > 0`.
- `setCharAt(n - 1, ch)` is valid when `n > 0`.
- `setCharAt(n, ch)` is **invalid**: this is the position after the last element.
- `setCharAt(-1, ch)` is invalid.
- For an empty builder, **no index at all** is valid for `setCharAt`.

To add at the end, use `append(ch)` instead of `setCharAt(length(), ch)`.

### `setLength` Allows 0, but Not Negative Numbers

- `sb.setLength(0)` is valid and makes the logical content empty.
- `sb.setLength(sb.length())` keeps the content unchanged.
- `sb.setLength(sb.length() + 1)` extends by one `'\u0000'`, rather than automatically adding a useful character.
- `sb.setLength(-1)` throws `IndexOutOfBoundsException` (specifically `StringIndexOutOfBoundsException` in some implementations).
- Attempting to grow to an unsatisfiable size can trigger memory or array size limit failures; never pass unbounded lengths directly from untrusted input.

Standalone example, save as `BuilderBoundsDemo.java`:

```java
public class BuilderBoundsDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("AB");

        try {
            sb.setCharAt(2, 'X');
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("Invalid character index");
        }

        try {
            sb.setLength(-1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("Invalid length");
        }

        sb.setLength(3);
        sb.setCharAt(2, 'C');

        System.out.println(sb);
        System.out.println(sb.length());
    }
}
```

```bash
javac -encoding UTF-8 BuilderBoundsDemo.java
java BuilderBoundsDemo
```

```text
Invalid character index
Invalid length
ABC
3
```

This example demonstrates proper index usage, **not a recommendation to use exceptions for normal control flow**. If an index or length comes from external data, validate bounds explicitly before calling.

## 7. `setCharAt` and `setLength` Do Not Replace `append`, `insert`, `delete`, or `replace`

Each API has its own semantics:

| API | What Does It Modify? | Effect on `length()` |
| --- | --- | --- |
| `setCharAt(index,ch)` | Overwrites exactly one `char` at an existing index | Unchanged |
| `setLength(n)` | Truncates the end or extends content with NUL | Reset to `n` |
| `append(value)` | Appends the value's representation at the end | Typically increases by appended content length |
| `insert(index,value)` | Inserts data, shifting trailing content right | Increases by inserted length |
| `delete(start,end)` | Deletes range `[start,end)` | Decreases by number of deleted units |
| `replace(start,end,str)` | Replaces a **range** with a `String` | May increase, decrease, or stay the same |
| `charAt(index)` | Only reads one `char` | Unchanged |

For instance, if you want to turn `abc` into `abXc`, **`setCharAt(2,'X')` is wrong** because it yields `abX`, losing `c`. The right method is `insert(2,'X')`. Conversely, if you want `abc` to become `abX` while keeping length 3, `setCharAt(2,'X')` is right.

`setLength` is typically useful when:
- You want to truncate the end of a buffer after determining a valid length.
- Reusing a builder with `setLength(0)` and continuing to `append`.
- You need a fixed length and **actively** fill/overwrite every slot before treating the content as finished text.

If the goal is "adding content", `append` expresses intent more clearly than `setLength(oldLength + k)` followed by filling each slot, because increasing length automatically creates NULs before they are overwritten.

## 8. Creating a Fixed Character Region and Writing into New Positions

When you want to build a sequence of a known length and assign each `char`, you can call `setLength` first so every target index is in bounds:

```java
StringBuilder slots = new StringBuilder();
slots.setLength(3); // Three NUL positions.

slots.setCharAt(0, 'A');
slots.setCharAt(1, 'B');
slots.setCharAt(2, 'C');

System.out.println(slots); // ABC
```

This is a valid snippet inside `main`. If you forget to fill a slot, the remaining empty position actually holds NUL, not "no element". A clearer data model in some cases is using `char[]`, `Arrays.fill`, or an appropriate buffer structure; the choice depends on the API and purpose.

Complete example, save as `FixedSlotsDemo.java`:

```java
public class FixedSlotsDemo {
    public static void main(String[] args) {
        StringBuilder slots = new StringBuilder();
        slots.setLength(4);

        for (int i = 0; i < slots.length(); i++) {
            slots.setCharAt(i, (char) ('A' + i));
        }

        System.out.println(slots);
        System.out.println(slots.length());

        slots.setLength(2);
        slots.append('!');
        System.out.println(slots);
    }
}
```

```bash
javac -encoding UTF-8 FixedSlotsDemo.java
java FixedSlotsDemo
```

```text
ABCD
4
AB!
```

In the loop, `(char) ('A' + i)` converts the integer expression into a `char` unit. With `i` from 0 to 3, we get `A`, `B`, `C`, `D`. When truncated to length 2 and `!` is appended, the content becomes `AB!`. The letters `CD` were removed from the logical sequence and do not come back when appending.

## 9. UTF-16: One `char` Is Not Always One Visible Unicode Character

An important point when editing text data: `StringBuilder` stores **UTF-16** units. A non-BMP Unicode code point like `🙂` (`U+1F642`) is represented by **two `char`s**: a *high surrogate* and a *low surrogate*. Therefore:
- `builder.length()` counts `char` units, which does not necessarily equal the number of Unicode code points or user-perceived characters.
- `setCharAt(i,ch)` replaces only **one UTF-16 unit**. It **does not automatically detect** surrogate pairs and does not guarantee preserving a non-BMP code point.
- `setLength(n)` can cut a string **between** a high surrogate and a low surrogate if `n` lands on an improper boundary.
- A `String` or `StringBuilder` can contain lone surrogates, though such data does not represent a valid Unicode scalar value sequence.

Save `SurrogateBuilderDemo.java`:

```java
public class SurrogateBuilderDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("A🙂B");

        System.out.println(text.length());
        System.out.println(
                text.codePointCount(0, text.length()));

        text.setCharAt(0, 'X');
        System.out.println(text);

        text.setLength(3); // Proper boundary after the emoji.
        System.out.println(text);
        System.out.println(
                text.codePointCount(0, text.length()));
    }
}
```

```bash
javac -encoding UTF-8 SurrogateBuilderDemo.java
java SurrogateBuilderDemo
```

```text
4
3
X🙂B
X🙂
2
```

The initial string has 4 UTF-16 units yet only 3 code points. After changing `A` to `X`, the emoji's surrogate structure remains intact. `setLength(3)` drops the trailing `B` without splitting the emoji, so `X🙂` has 3 UTF-16 units and 2 code points.

Conversely, calling `setLength(2)` on `"A🙂B"` keeps `A` and the emoji's **high surrogate** while cutting off the low surrogate. That is not a valid way to truncate Unicode text on a code point boundary. If you want to move by code points, use `offsetByCodePoints` or `codePointAt`/`Character.charCount` to compute the UTF-16 boundary before calling `setLength`. If you need to replace an entire emoji with another emoji, consider `replace(start,end,replacement)` with proper UTF-16 boundaries instead of `setCharAt` on a single slot.

### Truncating to an Exact Number of Code Points

Snippet:

```java
StringBuilder sb = new StringBuilder("A🙂B");
int endUtf16 = sb.offsetByCodePoints(0, 2);
sb.setLength(endUtf16);
System.out.println(sb); // A🙂
```

`offsetByCodePoints(0,2)` returns UTF-16 index `3`, because `A` occupies one `char` and `🙂` occupies two. Thus `setLength(3)` keeps the surrogate pair intact. These methods count by **code point**, which is still not enough to guarantee never splitting a *grapheme cluster* (such as combining marks or ZWJ-joined emojis); if requirements involve user cursors or visible character counts, corresponding grapheme segmentation logic is needed.

## 10. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Calling `setCharAt(sb.length(),ch)` to append at the end | Index out of bounds error | Use `append(ch)` |
| Using `capacity()` to validate an index for `setCharAt` | May touch a position beyond the **logical length** | Check `0 <= index < length()` |
| Thinking `setCharAt` replaces all identical characters | It edits only **one position** | Loop/replace each position if bulk replacement is needed |
| Writing `sb.setCharAt(...).append(...)` | Does not compile because `setCharAt` returns `void` | Write as two separate statements |
| Thinking `setLength` returns the builder for chaining | Does not compile because `setLength` returns `void` | Call separately |
| Increasing `setLength` and assuming spaces or `'0'` appear | New positions are **NUL U+0000** | Explicitly fill all data |
| Truncating and then re-extending hoping old characters return | Truncated characters are not in the logical result | Keep the original copy if recovery is needed |
| Thinking `setLength(0)` frees memory or erases secrets | It changes length; does not promise clearing/reallocating the buffer | Choose appropriate sensitive-data handling techniques |
| Using `setLength` to cut inside a surrogate pair | Can create lone high/low surrogates | Compute code point boundaries first |
| Using `setCharAt` to replace an entire non-BMP emoji | One `char` cannot represent that emoji | Replace the full two-code-unit range or use code point handling |
| Assuming a builder is immutable like `String` | Aliases all observe mutations to the same builder | Copy or avoid sharing a mutable builder |
| Sharing a builder across threads without synchronization | Race conditions and undefined results | Use exclusive ownership or proper synchronization |

## 11. Self-Check Exercises

### Exercise 1. Replacing at the Right Position

Given `StringBuilder sb = new StringBuilder("java");`, write calls to turn the content into `"Java!"`. Catch: initial length is 4, final length is 5. Can you use only `setCharAt` to create the `!` at position 4?

**Answer:** `sb.setCharAt(0,'J'); sb.append('!');`. `setCharAt` alone cannot increase the length from 4 to 5. Another way is `setLength(5)` then `setCharAt(4,'!')`, though `append` expresses intent more clearly.

### Exercise 2. Truncating Then Extending

Predict the integer values of the last two positions after these statements:

```java
StringBuilder sb = new StringBuilder("HELLO");
sb.setLength(3);
sb.setLength(5);
System.out.println((int) sb.charAt(3));
System.out.println((int) sb.charAt(4));
```

**Answer:**

```text
0
0
```

Both new positions contain `'\u0000'`, not `L`/`O`. Truncated letters do not come back automatically.

### Exercise 3. Valid Range

If a builder has `length() == 3` and `capacity() == 18`, which indices are valid when calling `setCharAt`?

**Answer:** Indices 0, 1, 2. Index 3 and above are invalid even though capacity is large enough.

### Exercise 4. Unicode Check

Given `StringBuilder sb = new StringBuilder("A🙂B");`:
- What is `sb.length()`?
- Does calling `sb.setLength(3)` keep the emoji intact?
- Does calling `sb.setLength(2)` still keep the full surrogate pair?

**Answer:** Length is 4 `char`s; truncating to 3 keeps `A🙂`, whereas truncating to 2 drops the emoji's low surrogate and leaves a lone high surrogate. To truncate cleanly by code points, compute the UTF-16 index with `offsetByCodePoints` first.

### Exercise 5. Return Type and Mutation

Is the following valid?

```java
StringBuilder sb = new StringBuilder("abc");
// sb = sb.setLength(2); // Does not compile.
sb.setLength(2);
System.out.println(sb);
```

**Answer:** `setLength` has return type `void`, so its result cannot be assigned to `sb`. Called on its own, the program prints `ab`.

## 12. Key Takeaways

- `setCharAt(index,ch)` **overwrites an existing `char`**; requires `0 <= index < length()`, length does not change, return type is `void`.
- `setLength(n)` changes the **logical length**. Decreasing length truncates the end; increasing length fills every new position with `'\u0000'`; negative `n` is invalid.
- **`length()` differs from `capacity()`.** Having storage capacity does not mean a valid element exists at that index.
- Truncating and then extending **does not restore** old data. `setLength(0)` makes it logically empty and does not promise wiping secrets from memory.
- `setCharAt` and `setLength` indices count **UTF-16 units**; be careful with surrogate pairs and graphemes.
- `StringBuilder` mutates in place, unlike immutable `String`; when sharing references or working across threads, manage mutation permissions and synchronization.

## Official Documentation (Java SE 17)

- [`StringBuilder`: `setCharAt`, `setLength`, `length`, `capacity`, `append`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`AbstractStringBuilder` and `CharSequence`: UTF-16 positions and character sequence operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
- [`Character`: Unicode code points, `charCount`, and surrogates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
