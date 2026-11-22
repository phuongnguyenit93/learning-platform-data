# `StringBuilder`: `insert`, `delete`, `deleteCharAt`, and `replace` in Java

`StringBuilder` is a **mutable sequence of characters**. Unlike `String` (immutable), `StringBuilder` lets you **insert, delete, and replace directly on the existing object**. Four important methods for editing content by position are:

- **`insert(index, value)`:** inserts data **before position** `index`.
- **`delete(start, end)`:** deletes character units in the range **`[start, end)`**.
- **`deleteCharAt(index)`:** deletes exactly **one `char` unit** at `index`.
- **`replace(start, end, str)`:** replaces the range **`[start, end)`** with the string `str`.

These operations **mutate the `StringBuilder` being called** and return a reference to that builder so calls can be chained. Indices used in `StringBuilder` APIs are **UTF-16 code unit offsets**, not necessarily the number of user-perceived characters.

## 1. Difference Between `String` and `StringBuilder`

```java
String text = "Java";
text.replace("Java", "Kotlin");
// text is still "Java": String is immutable.

StringBuilder builder = new StringBuilder("Java");
builder.replace(0, 4, "Kotlin");
// builder now has content "Kotlin".
```

In this example, `String.replace(CharSequence, CharSequence)` searches and replaces **literal content**, returning a `String`; whereas **`StringBuilder.replace(int, int, String)` replaces a range by index** and mutates the builder in place. The two methods share the same name but **do not share the same signature or how the target segment is selected**.

| Method | Position Input | Effect | Returns |
| --- | --- | --- | --- |
| `insert(offset, value)` | One insertion position, 0-based | Inserts before the code unit at offset | The `StringBuilder` itself |
| `delete(start, end)` | Half-open range `[start, end)` | Deletes the range | The `StringBuilder` itself |
| `deleteCharAt(index)` | Position of one code unit | Deletes one code unit | The `StringBuilder` itself |
| `replace(start, end, str)` | Half-open range `[start, end)` | Removes the range, puts `str` in its place | The `StringBuilder` itself |
| `toString()` | None | Creates a `String` value with current content | A `String` |

`StringBuilder.length()` returns the number of **current UTF-16 code units**, which changes on insert/delete/replace. `capacity()` is the reserved buffer capacity: it is **not** the text length and **not** a valid index bound for these operations.

## 2. Index Rules: Positions and the `[start, end)` Range

Suppose the builder contains `"ABCDE"`:

```text
Content:     A   B   C   D   E
Code unit:   0   1   2   3   4
Position:    0   1   2   3   4   5
             |---|---|---|---|---|

insert(2, "X")     -> ABXCDE
delete(1, 4)       -> AE
deleteCharAt(2)    -> ABDE
replace(1, 4, "X") -> AXE
```

The lines above are **four independent operations**, each starting from `"ABCDE"`, **not** sequential steps.

- `insert(2, "X")` inserts before `C` (the code unit at index 2), shifting everything from `C` onward to the right.
- `delete(1, 4)` deletes `B`, `C`, `D` (indices 1, 2, 3), keeping `A` and `E`.
- `deleteCharAt(2)` deletes only `C` at index 2.
- `replace(1, 4, "X")` replaces all of `BCD` with `X`.

**The start bound is inclusive and the end bound is exclusive** for `delete` and `replace`. Therefore, when `end - start == 3`, the operation affects three code units of the original sequence (assuming `end` does not exceed the length).

### Valid Indices

With `n = builder.length()`:

- `insert(offset, value)` allows `0 <= offset <= n`. `offset == 0` inserts at the start; `offset == n` inserts at the end (positionally like append).
- `delete(start, end)` requires `0 <= start <= n`, `start <= end`. If `end > n`, Java **clamps the end bound to `n`**; it is not an error merely because `end` exceeds `n`.
- `replace(start, end, str)` has the same range rule: `0 <= start <= n`, `start <= end`; `end > n` is **clamped to `n`**.
- `deleteCharAt(index)` requires `0 <= index < n`; `index == n` is **invalid**, because that is the position after the last character.
- Negative indices, `start > n`, or `start > end` are range errors for `delete` and `replace`.

For invalid inputs, these APIs throw exceptions in the `IndexOutOfBoundsException` hierarchy (specifically `StringIndexOutOfBoundsException` depending on the method/implementation). `replace` also throws `NullPointerException` if the replacement string `str` is `null`.

## 3. `insert()`: Inserting at the Start, Middle, or End

`insert` has many overloads for accepting different types of data, for example:

```java
builder.insert(0, "Hi ");    // insert String at the beginning
builder.insert(2, 'X');      // insert char
builder.insert(3, 42);       // insert integer, in text form "42"
builder.insert(builder.length(), "!"); // insert at the end
```

This snippet **illustrates calls placed in a method body** on an already-created builder; if run sequentially, the index of each call is interpreted relative to the **content at the moment of that call**, not the initial content.

Some commonly used overloads:

| Overload | Meaning |
| --- | --- |
| `insert(int offset, String str)` | Inserts the content of `String` |
| `insert(int offset, CharSequence s)` | Inserts a character sequence (such as `String` or `StringBuilder`) |
| `insert(int offset, char c)` | Inserts a `char` |
| `insert(int offset, int i)` | Inserts the text representation of an integer |
| `insert(int offset, boolean b)` | Inserts `"true"` or `"false"` |
| `insert(int offset, char[] data)` | Inserts characters from an array |
| `insert(int dstOffset, CharSequence s, int start, int end)` | Inserts slice `[start, end)` of source `s` at destination offset |

With the last overload, distinguish **`dstOffset` in the target builder** from **`start` and `end` in the source `CharSequence`**. For instance, `new StringBuilder("XY").insert(1, "012345", 2, 5)` produces `"X234Y"`: it takes slice `234` from the source and inserts it between `X` and `Y`.

**The null case:** Several `insert` overloads are specified to insert the letters `"null"` when a `String`/`CharSequence` argument is null. For example, `new StringBuilder("abc").insert(1, (String) null)` becomes `"anullbc"`. Define your program's data policy; do not rely on automatically inserting `"null"` if null represents missing data.

## 4. `delete()` and `deleteCharAt()`: Deleting the Exact Range

### 4.1. Deleting a Range with `delete(start, end)`

`delete(start, end)` deletes from **`start` inclusive to `end` exclusive**. The actual deleted length is `min(end, length()) - start` when the start bounds are valid.

```java
StringBuilder sb = new StringBuilder("abcdef");
sb.delete(2, 5); // "abf" (deletes c, d, e)
```

In this example, `"abcdef"` has indices `0..5`; after deleting indices `2..4`, the result is **`"abf"`** because `a, b, f` remain.

Special cases:

- `delete(2, 2)`: empty range; content does not change.
- `delete(0, length())`: clears the entire builder.
- `delete(1, 99)` on builder `"abc"`: deletes from index 1 to the end because `end` is clamped to 3; result is `"a"`.
- `delete(length(), length())`: valid, no change.
- `delete(length() + 1, length() + 1)`: invalid because `start` exceeds the length.

Note: an end bound exceeding length **is clamped**, whereas a start bound exceeding length **is not** automatically clamped.

### 4.2. Deleting One Code Unit with `deleteCharAt(index)`

`deleteCharAt(index)` is equivalent to `delete(index, index + 1)` in deleting **one UTF-16 code unit**, when `index` is valid.

```java
StringBuilder sb = new StringBuilder("book");
sb.deleteCharAt(1);
// Result: "bok"
```

The last valid index for `deleteCharAt` is `length() - 1`. If the builder is empty, no index is valid for deleting a `char`.

**Unicode warning:** `deleteCharAt` operates on individual code units and can delete one half of an emoji's **surrogate pair**, leaving the string with a lone surrogate. To delete a full non-BMP Unicode code point, use `codePointAt` and `Character.charCount` as shown in the Unicode section below. To delete a full *grapheme cluster* (what a user considers one character), proper Unicode segmentation is required; deleting a single code point can still split combining marks or ZWJ emojis.

## 5. `replace(start, end, str)`: Replacing a Range with a New String

`StringBuilder.replace(int start, int end, String str)`:

1. Identifies the range `[start, end)` of the current builder.
2. Removes that range (if `end` exceeds `length()`, it only goes up to the end).
3. Inserts the content of `str` right at `start`.

Standalone example:

```java
StringBuilder sb = new StringBuilder("Hello world");
sb.replace(6, 11, "Java");
// Result: "Hello Java"
```

`replace` is **positional replacement**, and **does not automatically find all occurrences of `"world"`**. If you do not know the position, you can call `indexOf("world")` first, then use `replace(index, index + "world".length(), "Java")` after checking that index is not `-1`.

Useful edge cases:

- `replace(k, k, "X")`: removes zero code units, effectively **inserting `"X"` at k**.
- `replace(start, end, "")`: replaces with an empty string, effectively **deleting the range**.
- `replace(length(), length(), "!")`: inserts `!` at the end.
- `replace(1, 99, "XY")` on builder `"abc"`: replaces from `b` to the end with `XY`, resulting in `"aXY"`.
- `replace(3, 99, "!")` on builder `"abc"`: removes nothing because it starts at the end, then inserts `!`, resulting in `"abc!"`.

**`str` must not be null:** `replace(start, end, null)` throws `NullPointerException`. Unlike some `insert` overloads, `replace` does not turn null into `"null"`.

### Difference from `String.replace` and `replaceAll`

| API | Selects Part to Replace | Mutates Receiver? |
| --- | --- | --- |
| `StringBuilder.replace(start, end, str)` | **By indices** of one range | Yes, mutates `StringBuilder` |
| `String.replace(oldText, newText)` | **All non-overlapping literal matches** | No, returns `String` |
| `String.replaceAll(regex, replacement)` | **All regex matches** | No, returns `String` |

Do not pass a regex like `"\\d+"` to `StringBuilder.replace` expecting it to replace digits; `StringBuilder`'s overload takes neither a regex target nor a search string, only **start and end positions**.

## 6. Combined Runnable Example on Java 17+

Save the file `BuilderOpsDemo.java`:

```java
public class BuilderOpsDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("Java");

        sb.insert(4, " Core");
        System.out.println(sb);

        sb.insert(0, "Learn ");
        System.out.println(sb);

        sb.insert(sb.length(), "!");
        System.out.println(sb);

        sb.delete(0, 6);
        System.out.println(sb);

        sb.delete(4, 9);
        System.out.println(sb);

        sb.deleteCharAt(4);
        System.out.println(sb);

        sb.replace(0, 4, "Kotlin");
        System.out.println(sb);

        System.out.println(sb.length());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BuilderOpsDemo.java
java BuilderOpsDemo
```

Output:

```text
Java Core
Learn Java Core
Learn Java Core!
Java Core!
Java!
Java
Kotlin
6
```

Explanation of key milestones:

- After the third insertion, `"Learn Java Core!"` is 16 code units long.
- `delete(0, 6)` removes the prefix `"Learn "` (6 code units), yielding `"Java Core!"`.
- `delete(4, 9)` removes `" Core"`; exclusive bound 9 leaves `!`, leaving `"Java!"`.
- `deleteCharAt(4)` deletes `!`, leaving `"Java"`.
- `replace(0, 4, "Kotlin")` replaces all of `Java` with `Kotlin`, length 6.

**Important:** Indices at each operation are calculated from the **current content**, not the initial content `"Java"`. Any insertion or deletion before a position can shift subsequent indices.

## 7. Runnable Example Testing Boundary Cases

Save the file `BuilderBoundsDemo.java`:

```java
public class BuilderBoundsDemo {
    public static void main(String[] args) {
        StringBuilder a = new StringBuilder("abc");
        System.out.println(a.delete(1, 99));

        StringBuilder b = new StringBuilder("abc");
        System.out.println(b.replace(1, 99, "XY"));

        StringBuilder c = new StringBuilder("abc");
        System.out.println(c.replace(1, 1, "!"));

        StringBuilder d = new StringBuilder("abc");
        System.out.println(d.replace(3, 99, "!"));

        StringBuilder e = new StringBuilder("abc");
        System.out.println(e.insert(1, (String) null));

        StringBuilder f = new StringBuilder("abc");
        System.out.println(f.delete(1, 1));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderBoundsDemo.java
java BuilderBoundsDemo
```

Output:

```text
a
aXY
a!bc
abc!
anullbc
abc
```

Points to remember: `end > length()` with `delete` or `replace` does not automatically throw an error; `start == end` creates an empty range (deleting is a no-op; replacing with a non-empty string inserts). Also, `insert(..., (String) null)` inserts `"null"` per that overload's rule, which does not mean `replace(..., null)` is valid.

## 8. Working Safely with Unicode / UTF-16

`StringBuilder` also stores and indexes by UTF-16 code units. The emoji `😀` is one Unicode code point yet is represented by **two `char`s**. Inserting or deleting in the middle of a surrogate pair can make the string lose Unicode validity.

Save `BuilderUnicodeDemo.java`:

```java
public class BuilderUnicodeDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder(
                "A\uD83D\uDE00B"); // A😀B

        System.out.println(text.length());
        System.out.println(
                Character.codePointCount(text, 0, text.length()));

        StringBuilder whole = new StringBuilder(text);
        whole.delete(1, 3);
        System.out.println(whole);

        StringBuilder broken = new StringBuilder(text);
        broken.deleteCharAt(1);
        System.out.println(
                Character.isLowSurrogate(broken.charAt(1)));
        System.out.println(broken.length());
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderUnicodeDemo.java
java BuilderUnicodeDemo
```

Output:

```text
4
3
AB
true
3
```

- `length() == 4` because `A` and `B` each take 1 code unit, while the emoji needs 2 code units.
- There are 3 Unicode code points: `A`, `😀`, `B`.
- `delete(1, 3)` deletes the entire surrogate pair representing the emoji, leaving `AB`.
- `deleteCharAt(1)` deletes only the high surrogate at index 1, leaving a lone low surrogate. Thus `Character.isLowSurrogate(broken.charAt(1))` returns `true`. The remaining string should not be treated as valid Unicode.

When standing at the **starting offset of a code point**, you can delete that whole code point with:

```java
int index = 1;
int point = text.codePointAt(index);
text.delete(index, index + Character.charCount(point));
```

This is an illustrative snippet inside a method after `text` holds `"A😀B"`; the result will be `"AB"`. `Character.charCount(point)` returns `2` for `😀`. If the starting offset falls **in the middle** of a surrogate pair, the algorithm must locate the exact boundary first before processing. And if the domain needs operations by **visible character** (grapheme cluster), relying on code points alone is still insufficient for combining marks, modifiers, or zero-width joiner emojis.

## 9. Searching by Content Before Positional Editing

`StringBuilder.replace` requires **indices**, not a search target. If you want to replace a single literal occurrence of a word:

```java
StringBuilder sb = new StringBuilder("Hello world");
String target = "world";
int index = sb.indexOf(target);

if (index >= 0) {
    sb.replace(index, index + target.length(), "Java");
}

System.out.println(sb); // Hello Java
```

This snippet is illustrative code placed inside a method. `indexOf` returns `-1` when not found; always check before passing to `replace`.

If you need to replace **all** literal occurrences by editing the builder directly, you can loop over found positions. Standalone example in `BuilderReplaceAllDemo.java`:

```java
public class BuilderReplaceAllDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("red blue red");
        String target = "red";
        String replacement = "green";

        if (target.isEmpty()) {
            throw new IllegalArgumentException("target is empty");
        }

        int from = 0;
        while ((from = sb.indexOf(target, from)) >= 0) {
            sb.replace(from, from + target.length(), replacement);
            from += replacement.length();
        }

        System.out.println(sb);
    }
}
```

Run:

```bash
javac -encoding UTF-8 BuilderReplaceAllDemo.java
java BuilderReplaceAllDemo
```

Output:

```text
green blue green
```

After each replacement, `from` advances past **the newly inserted replacement segment**, avoiding re-matching the newly inserted characters in the current replacement. Checking `target.isEmpty()` prevents empty-target search cases that require a separate policy.

For simple problems that only need to replace a text snippet everywhere, **`String.replace(target, replacement)` is usually easier to read**: `String result = sb.toString().replace("red", "green");`. Use an in-place builder loop only when there is a reason to edit in place or integrate multiple stateful transformations.

## 10. Method Chaining, Length, and Performance

All four content-editing methods return the builder, so they can be **chained**:

```java
StringBuilder sb = new StringBuilder("abc");
StringBuilder same = sb.insert(1, "-");

System.out.println(sb == same); // true
System.out.println(sb);         // a-bc

sb.delete(1, 2).replace(1, 2, "B");
System.out.println(sb);         // aBc
```

`==` is used here **intentionally to check `StringBuilder` object identity**, not to compare the content of two `String`s. The builder remains a single object; chained calls modify its content sequentially.

Regarding cost:

- `insert` in the middle of a string typically shifts the tail to the right; `delete` typically shifts the remaining data to the left.
- `replace` can cause length to grow or shrink, depending on the length of the removed range and the inserted `str`.
- `append` is generally a better fit than middle `insert` if the goal is simply building a string left to right.
- `StringBuilder` has an expandable buffer; `capacity()` and `ensureCapacity(...)` relate to performance/capacity and **do not change positional rules**.
- `StringBuilder` **does not synchronize its methods** for shared mutation from multiple threads; for concurrent access, manage synchronization externally or design without sharing a mutable builder.

You should not make absolute claims about allocation counts or whole-program complexity from a single concatenation; performance should be evaluated with real data and the actual JVM.

## 11. Common Mistakes and How to Avoid Them

1. **Mistaking the end bound as inclusive:** `delete(1, 4)` deletes indices 1, 2, 3, not index 4.
2. **Using stale indices after insert/delete:** subsequent code units may have shifted; recompute positions on the current builder.
3. **Thinking `end > length()` always throws:** for `delete` and `replace`, an `end` greater than length is **clamped to length**; however, `start > length()` is still an error.
4. **Calling `deleteCharAt(length())`:** invalid; the last character is at index `length() - 1`, if the builder is non-empty.
5. **Confusing `replace(start, end, str)` with `String.replace(old, new)`:** the builder method replaces **one index range**, not all occurrences automatically.
6. **Calling `replace(start, end, null)`:** a null `str` causes `NullPointerException`; if you want to delete the range, use `delete` or `replace(start, end, "")`.
7. **Assuming every operation works on "visible characters":** the API uses UTF-16 code units; deleting a single `char` can break a surrogate pair.
8. **Assuming builder methods do not mutate the receiver:** these methods *mutate* the builder itself; references held elsewhere to that `StringBuilder` will observe the changed content.
9. **Comparing two builders' contents with `==`:** `==` checks reference identity. Use `toString().equals(...)` or an appropriate content comparison when needed.
10. **Not checking the result of `indexOf` before `replace`:** if not found, index `-1` is invalid.
11. **Sharing one `StringBuilder` across multiple mutating threads without synchronization:** can cause inconsistent state and results.

## 12. Self-Check

For each scenario below, **start with a fresh builder**, without carrying over the result of the previous row:

| Initial Builder | Operation | Result |
| --- | --- | --- |
| `"ABCDE"` | `insert(0, ">")` | `">ABCDE"` |
| `"ABCDE"` | `insert(5, "!")` | `"ABCDE!"` |
| `"ABCDE"` | `delete(1, 4)` | `"AE"` |
| `"ABCDE"` | `delete(2, 2)` | `"ABCDE"` |
| `"ABCDE"` | `deleteCharAt(4)` | `"ABCD"` |
| `"ABCDE"` | `replace(1, 4, "x")` | `"AxE"` |
| `"ABCDE"` | `replace(2, 2, "x")` | `"ABxCDE"` |
| `"ABCDE"` | `replace(0, 5, "")` | `""` |
| `"ABCDE"` | `delete(2, 99)` | `"AB"` |

Check questions:

- On `"abc"`, what does `delete(1, 99)` produce? **`"a"`** because `end` beyond length is clamped.
- On `"abc"`, what does `replace(3, 99, "!")` produce? **`"abc!"`** because `start` is at the end and the replaced slice is empty.
- Why can `deleteCharAt(1)` corrupt Unicode content on `"A😀B"`? Because it deletes a single `char`, which can delete only **half of the surrogate pair**.
- If you want to replace every `red` with `green`, does `StringBuilder.replace` do all of them automatically? **No**; you must locate each range to replace, or use `String.replace`.

**Key takeaway:** `insert` inserts at a position; `delete` deletes `[start, end)`; `deleteCharAt` deletes one code unit; `replace` replaces `[start, end)`. All four **mutate the `StringBuilder` itself**, return the builder for chaining, and use **UTF-16 offsets** — so verify bounds and Unicode boundaries before editing.
