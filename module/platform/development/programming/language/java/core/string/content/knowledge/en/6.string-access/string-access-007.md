# toCharArray() and Character Data Copies in Java

## 1. Learning objectives

The `String.toCharArray()` method converts the content of a `String` object into a **new `char[]` array**, containing the **UTF-16 code units** in the exact order they appear in the string. Each call provides a newly allocated array; modifying elements in this array **does not alter the source string**.

After this lesson, you will be able to:

1. Use `toCharArray()` with correct syntax and identify its exact return type.
2. Prove that the returned array is an **independent copy** from the original `String` and from arrays returned by other calls.
3. Read, iterate over, and modify individual `char[]` elements; create a new `String` from the modified data.
4. Understand the difference between **`char` (UTF-16 code unit)**, **Unicode code point**, and **visible character**.
5. Choose appropriately among `toCharArray()`, `charAt()`, `getChars()`, and code point processing APIs.
6. Avoid mistakes related to indices, `null` values, surrogate pairs, data copying, memory, and printing arrays.

This lesson belongs to the **Length and Access** group of Java Core String. Prerequisites: `String`, one-dimensional arrays, the `char` type, loops, assignment, references, and `String` immutability. Complete examples use Java 17+.

## 2. What does toCharArray() do?

Method signature in the Java API:

~~~java
public char[] toCharArray()
~~~

Basic usage:

~~~java
String word = "Java";
char[] letters = word.toCharArray();

System.out.println(letters.length);  // 4
System.out.println(letters[0]);      // J
System.out.println(letters[3]);      // a
~~~

`word` has type `String`, whereas `letters` has type **`char[]`**. Each element of the array holds one UTF-16 code unit of the string. The array has length equal to `word.length()`, because both count **UTF-16 code units** rather than necessarily counting user-visible characters.

Distinguish the syntax:

| Task | With String | With char[] |
| --- | --- | --- |
| Length | `word.length()` (method) | `letters.length` (array field) |
| Get element at position `i` | `word.charAt(i)` | `letters[i]` |
| Replace element `i` | No in-place mutation operation | `letters[i] = 'K'` |
| Convert to the other representation | `word.toCharArray()` | `new String(letters)` |
| Value type | Immutable `String` | Mutable `char[]`, fixed length |

Example iterating over the array after conversion:

~~~java
String word = "Code";
char[] units = word.toCharArray();

for (int i = 0; i < units.length; i++) {
    System.out.println(i + ": " + units[i]);
}
~~~

Output:

~~~text
0: C
1: o
2: d
3: e
~~~

Indices start at `0` and end at `length - 1`. Accessing `units[-1]` or `units[units.length]` throws `ArrayIndexOutOfBoundsException`.

## 3. Independent copy: modifying the array does not change the source string

This is the most important mechanism.

~~~java
String source = "Java";
char[] chars = source.toCharArray();

chars[0] = 'K';

System.out.println(source);           // Java
System.out.println(new String(chars)); // Kava
~~~

After `chars[0] = 'K'`, the `String` object still holds `"Java"`. Modifying the array only affects the **copy**. Illustration:

~~~text
source ───────────────► String "Java"  (immutable)
                            │
                            │ toCharArray()
                            ▼ copies values
chars  ───────────────► char[] ['J', 'a', 'v', 'a']
                                   │
                                   │ chars[0] = 'K'
                                   ▼
                        char[] ['K', 'a', 'v', 'a']

source is still "Java"
~~~

**Do not confuse "copy" with "view":** `toCharArray()` does not return a direct window into the memory that `String` uses to store its content. You are free to modify the array you receive, but you cannot use that to modify the string. The internal representation of `String` is a JDK implementation detail; since Java 9 many JDKs use *Compact Strings*, so you should not assume `String` objects internally store a `char[]`.

### Each call yields its own array

~~~java
String text = "ABC";
char[] first = text.toCharArray();
char[] second = text.toCharArray();

System.out.println(first == second); // false

first[0] = 'X';
System.out.println(new String(first));  // XBC
System.out.println(new String(second)); // ABC
System.out.println(text);               // ABC
~~~

Two independent calls return **two different arrays**. The `==` operator on two arrays compares **references**, not content.

If you need to compare array contents:

~~~java
char[] a = "java".toCharArray();
char[] b = "java".toCharArray();

System.out.println(a == b);                         // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

This difference matters because `String.equals()` compares the **contents** of two strings, whereas `char[]` arrays do not override `Object.equals()` to compare element by element.

## 4. Going from char[] back to String also creates an independent value

If you have edited the characters and want the corresponding string, construct a `String` object from the array:

~~~java
char[] chars = {'J', 'a', 'v', 'a'};
String snapshot = new String(chars);

chars[0] = 'K';

System.out.println(snapshot);        // Java
System.out.println(new String(chars)); // Kava
~~~

`new String(chars)` **copies the array content** at the time the string is created. Modifying the array afterward does not alter `snapshot`.

Thus both directions have the **independent snapshot** property for the data in question:

~~~text
Source String --toCharArray()--> mutable copy char[]
Data char[] --new String(...)--> new immutable String
~~~

From `char[]`, you can also create a `String` using `String.valueOf(chars)`. To construct from a **slice** of the array, use the constructor `new String(chars, offset, count)`; note that `count` is the **number of elements**, not the end index:

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
String part = new String(letters, 1, 2);
System.out.println(part); // av
~~~

Invalid indices or slice length throw `IndexOutOfBoundsException`. Even when selecting only a slice, the created `String` remains independent of subsequent changes to the array.

### Note: char[].toString() does not convert array content into a String

An array is an object. Calling `chars.toString()` uses the default object representation and **does not produce** the desired character content. Use:

~~~java
char[] chars = {'O', 'K'};

System.out.println(new String(chars));          // OK
System.out.println(String.valueOf(chars));       // OK
System.out.println(java.util.Arrays.toString(chars)); // [O, K]
~~~

`System.out.println(chars)` also displays the array content because `PrintStream` has a dedicated overload accepting `char[]`. Do not generalize this behavior to `chars.toString()` or to every API accepting `Object`.

## 5. char[] is a mutable array, but has a fixed length

An array allows **replacing elements**; its size does not automatically grow or shrink:

~~~java
char[] data = "cats".toCharArray();
data[0] = 'b';

System.out.println(new String(data)); // bats
System.out.println(data.length);      // 4
~~~

If you need to **insert or delete** in ways that change length, `StringBuilder` is usually more convenient. If your goal is only to read a few characters without needing an independent array, `String.charAt()` avoids allocating a full `char[]` array.

Remember three layers of state:

1. **Source string:** immutable.
2. **Copy array:** mutable per element, fixed size.
3. **String recreated from the array:** immutable snapshot, does not track later changes to the array.

### Copying an array to another array

An array assignment **does not copy elements**:

~~~java
char[] first = "Hi".toCharArray();
char[] alias = first;

alias[0] = 'B';
System.out.println(new String(first)); // Bi
~~~

`alias` and `first` are two references to the **same array**. If you want an independent copy of `char[]`:

~~~java
char[] first = "Hi".toCharArray();
char[] copy = first.clone();

copy[0] = 'B';
System.out.println(new String(first)); // Hi
System.out.println(new String(copy));  // Bi
~~~

You can use `Arrays.copyOf(first, first.length)` or `System.arraycopy(...)` when appropriate. Do not confuse **copying from a String with toCharArray()** with **assigning a reference between two char[] variables**.

## 6. Relationship with length() and charAt()

For every valid index `i`, the value `source.toCharArray()[i]` corresponds to `source.charAt(i)` at the time of conversion. Both APIs operate on **UTF-16 code units**.

~~~java
String word = "Java";
char[] copy = word.toCharArray();

for (int i = 0; i < word.length(); i++) {
    System.out.println(word.charAt(i) == copy[i]);
}
~~~

All four lines print `true`. However, their usage differs:

- `charAt(i)`: reads a single character unit at position `i` from `String` without creating a full `char[]`.
- `toCharArray()`: obtains the entire content as a new array so you can traverse it repeatedly, pass it to an API requiring `char[]`, or mutate data in the **copy**.
- After editing the array, `word.charAt(i)` still reads from the original string, so it does not reflect changes made to the array.

Both `length()` and `toCharArray().length` use UTF-16 units; this result must not always be treated as the number of letters, code points, or graphemes.

### Empty strings and null

~~~java
String empty = "";
char[] emptyArray = empty.toCharArray();

System.out.println(emptyArray.length); // 0
~~~

The returned array is valid and has length `0`. Conversely:

~~~java
String missing = null;
// missing.toCharArray(); // NullPointerException
~~~

`null` is not an empty string. When an API receives uncertain input, define the function's contract clearly:

~~~java
static char[] orEmpty(String input) {
    return input == null ? new char[0] : input.toCharArray();
}
~~~

The illustrative function above **chooses** to convert `null` into an empty array. In other situations, returning `null` or throwing an exception with a specific message may be more appropriate; do not assume every application should behave like this example.

## 7. Unicode: char[] holds UTF-16 code units, not "visible characters"

This is the most important point when using `toCharArray()` for Vietnamese, emoji, and international text.

A Java `char` is a **16-bit unit**. A Unicode code point outside the **Basic Multilingual Plane (BMP)** requires **two** UTF-16 units called a *surrogate pair*. For example, the emoji `😀` is one code point yet occupies two `char[]` elements.

~~~java
String text = "A😀B";
char[] units = text.toCharArray();

System.out.println(text.length());                       // 4
System.out.println(units.length);                        // 4
System.out.println(text.codePointCount(0, text.length())); // 3
System.out.println(Character.isHighSurrogate(units[1])); // true
System.out.println(Character.isLowSurrogate(units[2]));  // true
~~~

Diagram:

~~~text
Displayed text:     A     😀       B
Code points:        A   U+1F600    B       (3 code points)
UTF-16 code units: [A] [high] [low] [B]   (4 chars)
Array indices:      0     1     2    3
~~~

**Important consequences:**

- `units[1]` is the **high surrogate**, and `units[2]` is the **low surrogate**. Printing each unit individually may not render as the expected emoji.
- If you modify one half of a surrogate pair without handling the other half, the array (and any `String` built from it) can end up containing an **unpaired surrogate** and invalid Unicode data with respect to surrogate pairing.
- `toCharArray()` only copies code units. It **does not** automatically split text into Unicode code points or user-perceived characters.

### When you need to iterate over code points

Use `String.codePoints()`, which returns an `IntStream` of code points, then convert it to `int[]` when you need an independent array:

~~~java
String text = "A😀B";
int[] points = text.codePoints().toArray();

System.out.println(points.length);       // 3
System.out.println(points[1] == 0x1F600); // true
~~~

You can process a code point with `Character.toChars(codePoint)` or reconstruct a string with the constructor `new String(int[] codePoints, int offset, int count)`. An `int[]` array is appropriate when an algorithm works on code points rather than code units.

**A code point is not necessarily a "visible character".** For instance, `"e\u0301"` has two code points (the letter e and a combining acute accent) yet can display as one character. Some emoji are sequences of multiple combined code points. If an algorithm requires segmentation by *grapheme cluster*, an appropriate Unicode segmentation tool is needed rather than just `toCharArray()` or `codePoints()`.

### Do not confuse with bytes and character encodings

`char[]` contains **UTF-16 units**. `byte[]` from `getBytes(StandardCharsets.UTF_8)` contains **UTF-8 encoded bytes**. The two structures differ in element type, length, and meaning. For many emoji, the UTF-8 byte count is 4, the UTF-16 `char` count is 2, and the code point count is 1.

~~~java
String emoji = "😀";
char[] chars = emoji.toCharArray();
byte[] bytes = emoji.getBytes(java.nio.charset.StandardCharsets.UTF_8);

System.out.println(chars.length); // 2
System.out.println(bytes.length); // 4
~~~

`toCharArray()` does not perform UTF-8 encoding or decoding, so do not use it instead of `getBytes()` when writing data to a file or network.

## 8. Compared with getChars(), charAt(), and StringBuilder

| Need | Typically suitable choice | Why |
| --- | --- | --- |
| Read 1–a few positions in a string | `charAt(i)` | Avoids creating an array holding the whole string |
| Need an **independent** character array of the whole string | `toCharArray()` | Allocates and returns a new `char[]` |
| Copy **a slice** into an existing array | `getChars(srcBegin, srcEnd, dst, dstBegin)` | Controls source range and destination start offset |
| Need multi-step edits where length may change | `StringBuilder` | Supports appending, deleting, inserting, replacing without fixed length |
| Need to iterate over Unicode code points | `codePoints()` | Avoids splitting a surrogate pair into two separate units |
| Need UTF-8 for data transmission | `getBytes(StandardCharsets.UTF_8)` | Encodes to byte[] according to the specified charset |

### getChars(): copy a slice into an existing destination array

~~~java
String text = "Hello";
char[] destination = {'_', '_', '_', '_', '_', '_'};

text.getChars(1, 4, destination, 2);

System.out.println(new String(destination)); // __ell_
~~~

The `srcEnd` bound is **exclusive**: `getChars(1, 4, ...)` copies `'e'`, `'l'`, `'l'` (three characters), starting at `destination[2]`. The method **returns `void`**, copying into the destination array provided by the caller; it does not change `text`.

Unlike `toCharArray()`, `getChars()` does not create the destination array for you. You must allocate enough elements. An invalid index range can throw `IndexOutOfBoundsException`.

### StringBuilder when length needs to change

~~~java
StringBuilder builder = new StringBuilder("Java");
builder.insert(0, "Core ");
builder.append(" 17");

System.out.println(builder.toString()); // Core Java 17
~~~

A `char[]` array cannot grow its size automatically to append a longer segment. `StringBuilder` can expand its capacity and is more convenient for repeated modifications. However, it is a **mutable** object, unlike `String`.

## 9. Memory, performance, and data safety

**Cost of toCharArray():** to copy a string with `n` UTF-16 units, the method must allocate an array of `n` elements and copy the content. Thus, both time and extra memory are **O(n)** in the length of the string. When you need a copy to mutate or pass to an API requiring an array, this cost serves a clear purpose. When you only want to read a few positions, `charAt()` can be more efficient because it does not allocate an entire array.

**Do not keep copies longer than needed:** every `char[]` is an object with its own data; calling `toCharArray()` thousands of times in a loop on large strings can increase unnecessary memory allocations. If you need to use the array within a processing block, convert once and reuse that array when logically sound.

**A copy alone does not guarantee absolute safety:** an independent copy lets code modify the array without affecting the source `String`, yet `char[]` is still mutable. If you share the **same array** across multiple parts of code, one part can overwrite another's data. Consider `clone()` or `Arrays.copyOf()` at API boundaries when data protection is needed.

**Sensitive data:** a `char[]` can be overwritten when no longer needed:

~~~java
char[] sensitive = {'1', '2', '3'};
java.util.Arrays.fill(sensitive, '\0');
~~~

However, if the array was created via `existingString.toCharArray()`, clearing the array **does not erase the source string** or other copies that previously existed in memory. Do not treat `toCharArray()` + `Arrays.fill()` as a guarantee that every trace of the data has been wiped. For APIs receiving secrets, prefer an appropriate secret-handling mechanism right at input time, rather than proactively creating a `String` containing the secret.

**Note:** `String.toCharArray()` does not transfer ownership of the `String`; it only creates a copy. `String` immutability prevents the original content from being altered through the returned array, but publishing or sharing a mutable array requires clear design.

## 10. Comprehensive standalone runnable example (Java 17+)

Create a file named **`CharArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class CharArrayCopyDemo {
    public static void main(String[] args) {
        String source = "Java";
        char[] first = source.toCharArray();
        char[] second = source.toCharArray();

        System.out.println(first == second);
        first[0] = 'K';
        System.out.println(source);
        System.out.println(new String(first));
        System.out.println(new String(second));

        String snapshot = new String(first);
        first[1] = 'o';
        System.out.println(new String(first));
        System.out.println(snapshot);

        char[] destination = {'_', '_', '_', '_', '_', '_'};
        "Hello".getChars(1, 4, destination, 2);
        System.out.println(new String(destination));

        String unicode = "A😀B";
        char[] units = unicode.toCharArray();
        System.out.println(unicode.length());
        System.out.println(units.length);
        System.out.println(unicode.codePointCount(0, unicode.length()));
        System.out.println(Character.isHighSurrogate(units[1]));
        System.out.println(Character.isLowSurrogate(units[2]));

        System.out.println(Arrays.toString("OK".toCharArray()));
    }
}
~~~

Compile and run in the same directory as the file:

~~~bash
javac CharArrayCopyDemo.java
java CharArrayCopyDemo
~~~

**Exact** stdout:

~~~text
false
Java
Kava
Java
Kova
Kava
__ell_
4
4
3
true
true
[O, K]
~~~

Reading the output by group:

1. `first == second` is `false` because two calls to `toCharArray()` return two independent arrays.
2. Changing `first[0]` to `'K'` makes the first array display `"Kava"`, while `source` and `second` remain `"Java"`.
3. `snapshot` captures `"Kava"`; subsequently modifying `first[1]` to `'o'` to produce `"Kova"` does not change `snapshot`.
4. `getChars(1, 4, ...)` copies the three characters `"ell"` into the existing array at position `2`, resulting in `"__ell_"`.
5. `"A😀B"` contains **4 code units** but **3 Unicode code points**, with positions `1` and `2` being the high/low surrogates.
6. `Arrays.toString()` displays the list of elements as `[O, K]` instead of joining them directly into `"OK"`.

To verify further, try changing `source` to `"Hi"` and adjusting the accessed indices accordingly. Do not change only the input while leaving the indices untouched, as that will cause an out-of-bounds exception.

## 11. Practice exercises by difficulty

### Exercise 1 — Convert and iterate

Write `printIndexedChars(String text)` using `toCharArray()` and a `for` loop to print UTF-16 units along with their indices. Test with `"Java"`, `""`, and `"A😀B"`. Explain why emoji inputs require caution when printing individual `char`s.

### Exercise 2 — Proving an independent copy

Create two arrays by calling `"Code".toCharArray()` twice. Change the first element of the first array to `'N'`; print the source string and both arrays using `new String(...)`. Predict the result beforehand and explain why the second array remains unchanged.

### Exercise 3 — Snapshot when converting back

Create `char[] chars = {'C', 'a', 't'};` and then `String animal = new String(chars);`. Afterward modify `chars[0] = 'B';`. Print both `animal` and `new String(chars)`, and describe the independence mechanism between the two values.

### Exercise 4 — Comparing arrays properly

Create `char[] a = "abc".toCharArray();`, `char[] b = "abc".toCharArray();`. Compare using `==` and `Arrays.equals()`. Why does one yield `false` and the other yield `true`?

### Exercise 5 — Copying a slice

Given the string `"012345"` and a destination array of six `'_'` characters, use `getChars(2, 5, dst, 1)`. The expected result is `"_234__"`. Explain how the end bound and the number of copied elements are calculated.

### Exercise 6 — Unicode

Measure `length()`, `toCharArray().length`, `codePointCount()`, and `codePoints().toArray().length` for `"😀😀"`. Expect `4`, `4`, `2`, `2`, respectively. Explain why `char[]` array indices do not map directly to the number of emoji.

### Exercise 7 — Choosing a solution

Write two versions that count the ASCII character `'a'` in a string: one reading via `charAt()` and one using `toCharArray()`. Both must produce the same result. Analyze the trade-off: `charAt()` does not allocate an array; `toCharArray()` creates a snapshot you can manipulate independently.

### Exercise 8 — Sensitive operations

Given a `char[]` array received from an API, use `Arrays.fill(chars, '\0')` after use. Explain the difference between wiping **that array** and claiming the data has been erased from **all of JVM memory** (the latter claim is not guaranteed). Discuss why converting secrets into `String` can increase the number of copies retained in memory.

## 12. Common mistakes and completion criteria

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Thinking `toCharArray()` mutates the String | String is immutable; the method only returns a copy | Receive `char[]`, mutate the copy, and build a new String if needed |
| Calling `text.toCharArray()` and discarding the result | The returned array is neither stored nor used | `char[] units = text.toCharArray();` |
| Using `chars.length()` | Arrays have a `length` field, not this method | `chars.length` |
| Using `chars.toString()` to get text | Returns the array object's default representation | `new String(chars)` or `String.valueOf(chars)` |
| Comparing `char[]` with `==` when checking content | `==` compares references | `Arrays.equals(a, b)` |
| Believing `char[] alias = chars` makes a copy | Only copies the reference | `chars.clone()` or `Arrays.copyOf(...)` |
| Thinking one `char` is always one Unicode code point | Surrogate pairs need two `char`s | Use `codePoints()` when processing code points |
| Splitting or editing one half of a surrogate pair alone | Can create lone surrogates | Keep pairs intact or process by code point |
| Not handling `null` | Calling methods on `null` throws NPE | Define a contract and check beforehand |
| Confusing `char[]` with `byte[]` | UTF-16 code units differ from encoded bytes | `getBytes(UTF_8)` when encoding is needed |
| Calling `toCharArray()` repeatedly without need | Creates a copy and incurs O(n) cost each time | Reuse the array or use `charAt()` |
| Thinking wiping the array wipes all String copies | Snapshots are independent | Manage secrets at input time, avoid creating unnecessary Strings |

**Self-check before completing the lesson:**

1. What type does `toCharArray()` return, and does it modify the source string?
2. Why do two calls to `toCharArray()` return two arrays that may have identical contents yet `==` is `false`?
3. When `chars[0]` changes, what happens to the source `String` and to a `String` previously created with `new String(chars)`?
4. When should you use `charAt()` instead of `toCharArray()`? When should you use `getChars()`?
5. Why is `"😀".toCharArray().length` equal to `2` while `"😀".codePointCount(0, 2)` is equal to `1`?
6. Can a `char[]` array change size? If you need to append, insert, or delete repeatedly, which tool is more suitable?
7. Why does `Arrays.fill(chars, '\0')` not mean all traces of sensitive data have disappeared?

**Rule to remember:** `String.toCharArray()` creates a **new `char[]` array containing a copy of the UTF-16 units**. You can modify **that array**, but you **cannot modify the source String through the array**. To transform data and obtain a string, create a new `String` from the modified array.

### References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toCharArray()`, `length()`, `charAt()`, `getChars()`, constructors, and `codePoints()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs, code points, and `Character.toChars()`.
- [Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `Arrays.equals()`, `Arrays.copyOf()`, `Arrays.fill()`, and `Arrays.toString()`.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): mutating content operations and converting to `String`.
