# StringBuilder.setLength(): Extending Length with the NUL Character (`\\u0000`)

## 1. The Core Issue

`StringBuilder` is a **mutable** character sequence in Java. The `setLength(int newLength)` method sets the **logical length** of that sequence. When `newLength` is greater than the current length, the newly added positions are **not spaces and not empty strings**: they are filled with the **NUL** character, i.e. the UTF-16 code unit with value `U+0000`, written in Java as `'\0'` or `'\u0000'`.

This is API contract behavior, not just a JVM implementation detail. Because NUL often does not show up when printed to a terminal, developers easily assume `setLength()` only "reserves extra space" or that the new positions do not exist yet. In fact, **they are already part of the StringBuilder's content** and are counted in `length()`, `charAt()`, `toString()`, `append()`, searching, and comparisons.

Example:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);

System.out.println(sb.length());       // 5
System.out.println(sb.charAt(2) == '\0'); // true
System.out.println(sb.charAt(4) == '\u0000'); // true
System.out.println(sb.toString().equals("Hi")); // false
~~~

After `setLength(5)`, the code unit sequence is:

| Index | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Value | `'H'` | `'i'` | `U+0000` | `U+0000` | `U+0000` |

The data is equivalent to a Java string with content `"Hi\u0000\u0000\u0000"` — 5 UTF-16 code units long. It is **not** equivalent to `"Hi"`, nor is it equivalent to `"Hi   "` (three spaces).

## 2. Length (`length`) Differs from Capacity (`capacity`)

Two properties of `StringBuilder` must be clearly distinguished:

- **`length()`**: the number of UTF-16 code units currently constituting the logical content. Valid positions for `charAt(i)` run from 0 to `length() - 1`. NUL is counted as part of the length.
- **`capacity()`**: the number of code units the structure can hold **before needing to expand its internal storage**. Capacity can exceed length, but the portion beyond length is **not** considered content and cannot be read with `charAt()`.
- **`ensureCapacity(minimumCapacity)`**: requests reserving at least a minimum capacity to reduce the likelihood of reallocations during future appends. It **does not** increase `length()` and **does not** create NUL characters in the content.
- **`setLength(newLength)`**: changes the number of code units in the content. If extended, the new positions are initialized to NUL; capacity is expanded if needed.

Comparison example:

~~~java
StringBuilder a = new StringBuilder("AB");
a.ensureCapacity(100);
System.out.println(a.length());   // 2
System.out.println(a.toString()); // AB

StringBuilder b = new StringBuilder("AB");
b.setLength(5);
System.out.println(b.length());   // 5
System.out.println(b.charAt(2) == '\0'); // true
~~~

Do not use `setLength(1000)` just to optimize allocations before `append()`: doing so creates **1,000 logical content positions** (or more than the old length) with NULs in the added portion. When you only want to reserve space, use `new StringBuilder(expectedCapacity)` or `ensureCapacity(expectedCapacity)`.

| Goal | Appropriate Choice |
|---|---|
| Reserve space for 1,000 characters to be `append()`ed later | `new StringBuilder(1000)` or `ensureCapacity(1000)` |
| Change the logical length to 1,000 code units | `setLength(1000)` |
| Append content right after existing text | `append(...)` |
| Truncate content from position `n` onward | `setLength(n)` with `n` smaller than current length |
| Pad with spaces up to a required length | `append(" ".repeat(...))` or an intentional character-writing operation, **not** relying on `setLength()`'s default |

## 3. Three Cases of `setLength(newLength)`

### 3.1. `newLength` Equals Current Length

Content-wise, nothing changes:

~~~java
StringBuilder sb = new StringBuilder("ABC");
sb.setLength(3);
System.out.println(sb.toString().equals("ABC")); // true
~~~

### 3.2. `newLength` Less Than Current Length: Truncating the Tail

When reducing length, code units from index `newLength` onward no longer belong to the logical content:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(3);
System.out.println(sb.toString()); // ABC
System.out.println(sb.length());   // 3
~~~

Capacity does not usually shrink automatically to match length; that is a separate property. If you want to consider reducing memory after content stabilizes, `trimToSize()` exists, though it should not be called by habit since effectiveness and cost depend on the situation.

### 3.3. `newLength` Greater Than Current Length: Padding with NUL

~~~java
StringBuilder sb = new StringBuilder("ABC");
sb.setLength(6);

System.out.println(sb.length()); // 6
System.out.println(sb.charAt(3) == '\0'); // true
System.out.println(sb.charAt(4) == '\0'); // true
System.out.println(sb.charAt(5) == '\0'); // true
~~~

The new logical content consists of `A`, `B`, `C`, followed by three `U+0000` code units. The new positions are not "blank slots" for `append()` to fill automatically.

**Limits:** `setLength(-1)` throws `StringIndexOutOfBoundsException`. A huge increase may require a large memory allocation and cause resource errors such as `OutOfMemoryError`; validate allowed data sizes before calling, especially when `newLength` comes from external input.

## 4. NUL Is a Real Character, Not a Java String Terminator

**NUL** here is Unicode code point `U+0000`, encoded in `StringBuilder` as a code unit with value 0. It can be written:

~~~java
char nul1 = '\0';
char nul2 = '\u0000';
System.out.println(nul1 == nul2); // true
System.out.println((int) nul1);    // 0
~~~

Distinctions to keep in mind:

- `'\0'` is not the same as `null` (a reference value pointing to no object). `null` is not a character.
- `'\0'` is not the same as `'0'` (digit zero, code point U+0030).
- `'\0'` is not the same as `' '` (space, U+0020).
- Java `StringBuilder` and `String` **do not use NUL to mark the end of text** like the *null-terminated string* convention commonly seen in C. NUL in the middle or at the end of a string is still counted in the length.
- When sending data to a native library, network protocol, database, or format with its own rules, **never assume** NUL is always displayed, preserved, or allowed like ordinary text. Behavior depends on the receiving system; check conversion boundaries.

Example:

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.setLength(4);              // 'A','B','\0','\0'
sb.append('C');               // 'A','B','\0','\0','C'
System.out.println(sb.length()); // 5
System.out.println(sb.charAt(4)); // C
~~~

`append('C')` appends **after the current length** rather than scanning for NUL positions to overwrite. The result is not `"ABC"`, but a sequence containing `"AB"`, two NULs, and `"C"`.

## 5. How to Inspect NUL Positions Without Being Misled by the Terminal

A `System.out.println(sb)` statement may not visibly show NUL code units in the displayed text area. Do not rely on visual output to judge length.

You can inspect directly:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);
System.out.println("length=" + sb.length());       // length=5
System.out.println("nul-count=" + sb.chars()
        .filter(value -> value == 0)
        .count());                                  // nul-count=3
~~~

`StringBuilder.chars()` is an `int` stream corresponding to each UTF-16 code unit; NULs have value 0, making them easy to count. If the data contains non-BMP Unicode characters, `chars()` and `codePoints()` can give different counts; in the case of lone NULs, both still identify `U+0000`.

Another approach is printing a representation or hex code instead of printing NUL directly:

~~~java
for (int i = 0; i < sb.length(); i++) {
    System.out.printf("index=%d, unit=U+%04X%n",
            i, (int) sb.charAt(i));
}
~~~

Output for `"Hi"` after `setLength(5)`:

~~~text
index=0, unit=U+0048
index=1, unit=U+0069
index=2, unit=U+0000
index=3, unit=U+0000
index=4, unit=U+0000
~~~

When data goes into logs or JSON, a tool might escape NUL as `\u0000`, render a special glyph, or reject control characters. **How it renders does not turn NUL into empty data**; check actual bytes/code units, length, and encoding rules.

## 6. Shortening Then Re-Extending: Does Not Restore Old Characters

Suppose a builder holds `"ABCDE"`, then is truncated to length 2 and extended back to 4:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(2);
System.out.println(sb.toString()); // AB

sb.setLength(4);
System.out.println(sb.length());         // 4
System.out.println(sb.charAt(2) == '\0'); // true
System.out.println(sb.charAt(3) == '\0'); // true
~~~

The values at indices 2 and 3 are **not** `'C'` and `'D'`. Increasing the length again does not resurrect the truncated text. The new positions must be filled with NUL, even when the internal structure still retains capacity from before the truncation.

If you want to temporarily change the length and later restore the old content, save **a copy of the original data** before truncating, not just the length number:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
String original = sb.toString();
sb.setLength(2);
// ... work needing the shortened string ...
sb.setLength(0);
sb.append(original);
System.out.println(sb); // ABCDE
~~~

## 7. When Should You Use `setLength()` to Increase Length?

Proactively increasing length can be useful in **index-based** writing algorithms, provided the program clearly accounts for the temporary NUL positions and guarantees overwriting them before exposing the text externally.

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.setLength(5);       // Can call setCharAt at indices 2, 3, 4.
sb.setCharAt(2, '-');
sb.setCharAt(3, '-');
sb.setCharAt(4, 'Z');
System.out.println(sb); // AB--Z
~~~

Because `setCharAt(i, ch)` is only valid when `0 <= i < length()`, increasing length beforehand allows writing to the new indices. However, if the workflow is interrupted before finishing the fills, the data may contain NULs. That is why such update blocks should have clear bounds, validation, and never publish results while any position remains uninitialized with business data.

In most sequential string-building cases, `append()` is a clearer and safer API:

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.append("---");
System.out.println(sb); // AB---
~~~

When you need to **pad with spaces** up to `targetLength`, you can write:

~~~java
StringBuilder sb = new StringBuilder("AB");
int targetLength = 5;
if (targetLength > sb.length()) {
    sb.append(" ".repeat(targetLength - sb.length()));
}
System.out.println(sb.equals("AB   ")); // false: StringBuilder's equals does not compare content
System.out.println(sb.toString().equals("AB   ")); // true
~~~

A noteworthy detail in the last two `println` calls: `StringBuilder` does not override `equals()` to compare content, so you must compare `String`s or use an appropriate content comparison. `"AB   ".contentEquals(sb)` can also return `true`. When the goal is spaces, **you must explicitly add actual spaces**, not expect `setLength()` to do it.

## 8. Impact on String Operations and Validation

When `toString()` is called on a builder containing NULs, the resulting `String` keeps the NULs. Many content-inspection APIs will behave differently from how they behave on space-only text.

Example:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);
String text = sb.toString();

System.out.println(text.length());            // 5
System.out.println(text.equals("Hi"));        // false
System.out.println(text.indexOf('\0'));       // 2
System.out.println(text.isEmpty());           // false
System.out.println(text.isBlank());           // false
System.out.println(text.strip().length());    // 5
System.out.println(text.trim().length());     // 2
~~~

Explanation:

- `isEmpty()` checks whether length equals 0; `"Hi\0\0\0"` has length 5, so false.
- `isBlank()` (Java 11+) asks whether all characters belong to the whitespace set per `Character.isWhitespace`. NUL is **not** whitespace. Even a string consisting solely of NULs is **not blank**.
- `strip()` removes leading/trailing whitespace per `Character.isWhitespace`; NUL is not in that set, so it is not removed.
- `trim()` is the legacy API that removes code units with value at most U+0020 from both ends; thus it happens to remove trailing NULs in this example, though **this is not a reliable way to handle NULs in arbitrary positions**. A NUL in the middle of a string is not removed by `trim()`.

If data from `StringBuilder` is used as an identifier, filename, map key, or protocol value, invisible NUL characters can cause hard-to-spot bugs. Depending on domain requirements, **avoid creating unnecessary NULs**, or validate and reject control characters before use.

### Warning About Cutting Inside a Surrogate Pair

`length()` counts **UTF-16 code units**, not display characters or Unicode code points. For example, the emoji 🚀 consists of two code units in Java:

~~~java
StringBuilder sb = new StringBuilder("🚀");
System.out.println(sb.length()); // 2
sb.setLength(1);
System.out.println(Character.isHighSurrogate(sb.charAt(0))); // true
~~~

Calling `setLength(1)` can slice a surrogate pair in half and leave an **unpaired high surrogate**. `StringBuilder` allows such UTF-16 code unit sequences to exist; when converting to another encoding or sending over a protocol, the data may be replaced or rejected. Do not truncate arbitrarily by code units when you want to keep code points intact; determine valid boundaries, using `offsetByCodePoints()` with `String` when needed, and handle Unicode carefully.

## 9. Standalone Runnable Java 17 Program

The combined example below intentionally **avoids printing NUL directly** to stdout. Instead, `inspect()` renders each `char` using a readable notation. The program tests: extending with NUL, `append()` not replacing NUL, filling with `setCharAt()`, shortening/re-growing, `ensureCapacity()`, Unicode, and negative length.

Save the UTF-8 file as **`SetLengthNulDemo.java`**:

~~~java
public class SetLengthNulDemo {
    private static String inspect(StringBuilder sb) {
        StringBuilder view = new StringBuilder("[");
        for (int i = 0; i < sb.length(); i++) {
            if (i > 0) {
                view.append(", ");
            }
            char ch = sb.charAt(i);
            if (ch == '\0') {
                view.append("U+0000");
            } else {
                view.append('\'').append(ch).append('\'');
            }
        }
        return view.append(']').toString();
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("Hi");
        sb.setLength(5);

        System.out.println("expanded.length=" + sb.length());
        System.out.println("expanded.units=" + inspect(sb));
        System.out.println("nulAt2=" + (sb.charAt(2) == '\0'));
        System.out.println("stringLength=" + sb.toString().length());
        System.out.println("equalsHi=" + sb.toString().equals("Hi"));
        System.out.println("indexOfNul=" + sb.indexOf("\0"));
        System.out.println("isBlank=" + sb.toString().isBlank());
        System.out.println("trimLength=" + sb.toString().trim().length());
        System.out.println("stripLength=" + sb.toString().strip().length());

        sb.setCharAt(2, '!');
        sb.setCharAt(3, '?');
        sb.setCharAt(4, '.');
        System.out.println("filled=" + sb);

        sb.setLength(2);
        System.out.println("shortened=" + sb);
        sb.setLength(4);
        System.out.println("regrown.units=" + inspect(sb));
        sb.append('Z');
        System.out.println("afterAppend.units=" + inspect(sb));

        StringBuilder reserved = new StringBuilder("OK");
        reserved.ensureCapacity(100);
        System.out.println("reserved.length=" + reserved.length());
        System.out.println("reserved.content=" + reserved);

        try {
            sb.setLength(-1);
        } catch (StringIndexOutOfBoundsException expected) {
            System.out.println("negativeLength=REJECTED");
        }

        StringBuilder rocket = new StringBuilder("🚀");
        System.out.println("rocket.length=" + rocket.length());
        rocket.setLength(1);
        System.out.println("halfSurrogate=" +
                Character.isHighSurrogate(rocket.charAt(0)));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 SetLengthNulDemo.java
java SetLengthNulDemo
~~~

Expected stdout:

~~~text
expanded.length=5
expanded.units=['H', 'i', U+0000, U+0000, U+0000]
nulAt2=true
stringLength=5
equalsHi=false
indexOfNul=2
isBlank=false
trimLength=2
stripLength=5
filled=Hi!?.
shortened=Hi
regrown.units=['H', 'i', U+0000, U+0000]
afterAppend.units=['H', 'i', U+0000, U+0000, 'Z']
reserved.length=2
reserved.content=OK
negativeLength=REJECTED
rocket.length=2
halfSurrogate=true
~~~

Output analysis:

1. `expanded.units` proves the three added positions are `U+0000`, not spaces.
2. `stringLength=5` and `equalsHi=false` prove `toString()` preserves full content, including trailing NULs.
3. `trimLength=2` and `stripLength=5` illustrate two different leading/trailing handling criteria; do not use `trim()` to mask NUL bugs.
4. After calling `setCharAt()`, the data `Hi!?.` no longer contains NULs in the extended portion.
5. After truncating to `Hi` and extending again, the two new positions are **once again** NUL. `append('Z')` simply appends `Z` after them.
6. `ensureCapacity(100)` can increase reserved capacity without increasing length or changing `OK`.
7. `setLength(-1)` is rejected; truncating the emoji down to one code unit leaves an unpaired surrogate.

## 10. Common Mistakes

| Misconception | Reality | How to Handle |
|---|---|---|
| Increasing `setLength()` means reserving space | It **increases logical length** and fills the new portion with NUL | Use `ensureCapacity()` if you only want to reserve space |
| NUL positions are empty slots that `append()` will fill | `append()` always adds after current length | Use `setCharAt()` to overwrite in range, or `append()` from the start |
| NUL is the same as a space | NUL is U+0000; space is U+0020 | Explicitly fill real spaces if business logic requires them |
| NUL terminates Java Strings early | Java uses logical length, not a NUL terminator | Inspect `length()` and `charAt()` instead of eyeballing output |
| Decreasing then increasing `setLength()` restores old data | The newly extended portion is filled with NUL | Save the old data if restoration is needed |
| `toString()` strips NUL | The resulting `String` keeps NUL | Use hex/escape representations when debugging |
| `strip()` removes NUL | NUL is not whitespace per `Character.isWhitespace()` | Do not rely on `strip()` to handle control characters |
| `trim()` always removes NUL | It only handles code units <= U+0020 **at the ends**, not arbitrary positions | Construct data properly from the start or validate explicitly |
| `StringBuilder.equals()` compares content | By default it compares object identity | Use `toString().equals(...)` or `String.contentEquals(builder)` |
| `length()` equals visible character count | Length counts UTF-16 code units | Account for surrogate pairs / code points |
| Negative `setLength()` becomes empty | Negative values are invalid | Enforce `newLength >= 0` |
| Extending to huge lengths is always safe | Can consume memory and time, causing resource errors | Validate size and bound inputs |

## 11. Checklist for Using `setLength()` Properly

- [ ] Clearly distinguish **length** from **capacity**.
- [ ] Increase length only when you truly want the new positions to exist; know they are filled with **NUL**.
- [ ] If appending sequentially, prefer `append()`; if only reserving space, prefer `ensureCapacity()`.
- [ ] If you must increase length for index-based writes, ensure every temporary NUL slot is overwritten before outputting data.
- [ ] Do not rely on the terminal to spot NUL; use `charAt()`, hex codes, or length checks.
- [ ] Note that `toString()` preserves NUL, and `trim()`/`strip()` have different criteria.
- [ ] Put limits on the new size and handle `newLength < 0`.
- [ ] When truncating Unicode, avoid splitting a surrogate pair if the domain operates on code points.

**Key takeaway:** `setLength(newLength)` changes the **logical content** of `StringBuilder`: decreasing it truncates the tail, while increasing it **appends `U+0000` characters at the end**. It is **completely different** from only increasing capacity. NUL is a real character in a Java string, even though it is usually invisible when printed.
