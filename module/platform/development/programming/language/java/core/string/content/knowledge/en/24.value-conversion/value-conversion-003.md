# String.copyValueOf and Creating Strings from Character Arrays in Java

## 1. The Problem: Converting `char[]` to `String`

In Java, `char[]` is a **mutable array of `char` elements**, whereas `String` represents an **immutable** text string. When processing text with a character array, you often need to create a `String` to return from a method, compare, store, or pass to an API that accepts strings.

For example:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = String.copyValueOf(letters);

System.out.println(text); // Java
```

`String.copyValueOf` is a **static** method of `java.lang.String` that converts a character array or a portion of an array into a string. It is especially useful when you already have data in `char[]` form and want the actual character content, rather than the representation of the array object itself.

This lesson focuses on the two overloads of `copyValueOf`, creating strings from arrays, copying semantics, selecting a subrange, and Unicode/UTF-16 considerations.

## 2. The Two Overloads of String.copyValueOf

The API provides two signatures:

```java
public static String copyValueOf(char[] data)
public static String copyValueOf(char[] data, int offset, int count)
```

| Parameter | Meaning |
| --- | --- |
| `data` | The `char[]` array containing the source data |
| `offset` | Starting index in the array (**0**-based) |
| `count` | **Number** of `char` elements to take; not the ending index |

**The single-parameter overload** takes the entire array:

```java
char[] data = {'H', 'e', 'l', 'l', 'o'};
String result = String.copyValueOf(data);

System.out.println(result); // Hello
```

**The three-parameter overload** takes a contiguous slice starting at `offset`, consisting of `count` elements:

```java
char[] data = {'H', 'e', 'l', 'l', 'o', '-', 'J', 'a', 'v', 'a'};

String left = String.copyValueOf(data, 0, 5);
String right = String.copyValueOf(data, 6, 4);

System.out.println(left);  // Hello
System.out.println(right); // Java
```

With `String.copyValueOf(data, 6, 4)`, the elements taken have indices **6, 7, 8, 9**, i.e., the half-open interval `[6, 10)`. The third argument is **not `endIndex`**. Confusing `count` with the ending position will cause you to extract the wrong slice or trigger an out-of-bounds exception.

A clear mental model is:

```text
data = ['H', 'e', 'l', 'l', 'o', '-', 'J', 'a', 'v', 'a']
index    0    1    2    3    4    5    6    7    8    9

copyValueOf(data, 6, 4)
                 |  +---- take 4 char units
                 +------- start at index 6

Result: "Java"
```

## 3. Copying Values, Not Keeping a View into the Array

A `char[]` array can be modified after creating a `String`. The string returned from `copyValueOf` must **not be affected** by subsequent modifications to the array.

```java
char[] source = {'c', 'o', 'd', 'e'};
String frozen = String.copyValueOf(source);

source[0] = 'm';

System.out.println(new String(source)); // mode
System.out.println(frozen);             // code
```

This holds because `String` is immutable and the API guarantees the result does not change if the source character array changes. Do not treat `String.copyValueOf(data)` as a **live-linked view** into the array.

When using the slice-selecting overload, the semantics are the same:

```java
char[] buffer = {'<', 'O', 'K', '>'};
String token = String.copyValueOf(buffer, 1, 2);

buffer[1] = 'N';

System.out.println(token);              // OK
System.out.println(new String(buffer)); // <NK>
```

The reverse direction is also independent in value: `String.toCharArray()` creates a new character array from the string. Modifying that array does not modify the `String`:

```java
String word = "Java";
char[] copy = word.toCharArray();

copy[0] = 'L';

System.out.println(word);             // Java
System.out.println(new String(copy)); // Lava
```

**Why is this useful?** When a character buffer is reused to read subsequent data, `copyValueOf` helps save the content of the current read as a stable `String`.

Note: the API guarantees **independence of the result's semantics**, rather than requiring you to infer internal `String` storage details across JDK versions.

## 4. copyValueOf, valueOf, and new String(char[])

There are several valid ways to create a string from a character array:

```java
char[] letters = {'J', 'a', 'v', 'a'};

String a = String.copyValueOf(letters);
String b = String.valueOf(letters);
String c = new String(letters);

System.out.println(a);                   // Java
System.out.println(a.equals(b));         // true
System.out.println(a.equals(c));         // true
```

In the `String` API, `copyValueOf(char[])` is functionally equivalent to `valueOf(char[])`. Similarly, the overload `copyValueOf(char[], offset, count)` is equivalent to `valueOf(char[], offset, count)` in terms of the resulting string.

| Form | Result with `char[]` | When to use |
| --- | --- | --- |
| `String.copyValueOf(data)` | String containing the whole array | Emphasize converting and preserving the array's content |
| `String.copyValueOf(data, offset, count)` | String containing the array slice | Already have offset and number of `char`s to take |
| `String.valueOf(data)` when `data` has static type `char[]` | String containing the whole array | Concise, common style |
| `String.valueOf(data, offset, count)` | String containing the array slice | Equivalent to `copyValueOf`'s slice overload |
| `new String(data)` | String containing the whole array | Constructor style |
| `new String(data, offset, count)` | String containing the array slice | Constructor style for an array slice |

The forms above produce the same **content** when given the same characters and slice. Do not use the `==` operator to infer that they are the same object. For `String`, compare contents using `equals`.

### `valueOf(char[])` and `valueOf(Object)` differ

`String.valueOf(data)` with a variable of static type `char[]` takes **the character contents**; casting to `Object` switches to the array object representation:

```java
char[] data = {'H', 'i'};
System.out.println(String.valueOf(data));                // Hi
System.out.println(String.valueOf((Object) data)
        .startsWith("[C@"));                              // true
```

If data arrives as type `Object`, you must check `instanceof char[]` before choosing the conversion approach; do not cast unconditionally. Details on overload resolution and `null` are covered in the lesson on `String.valueOf(Object)` versus `String.valueOf(char[])`.

### Distinction from Arrays.toString

`Arrays.toString(char[])` produces a display representation of **array elements**, with square brackets, commas, and spaces; it does not join characters into a continuous string:

```java
char[] data = {'H', 'i'};

System.out.println(String.copyValueOf(data)); // Hi
System.out.println(java.util.Arrays.toString(data)); // [H, i]
```

Both are useful but serve different purposes: the first creates text, while the second prints the array structure for debugging.

## 5. offset and count: Choosing the Right Range

Suppose `data.length == n`. A valid range must satisfy all conditions:

- `offset >= 0`.
- `count >= 0`.
- `offset <= n`.
- `count <= n - offset`.

In other words, the interval `[offset, offset + count)` must lie within the array. Writing the condition `count <= n - offset` helps avoid integer overflow when computing `offset + count` in extreme cases.

```java
char[] data = {'a', 'b', 'c', 'd'};

System.out.println(String.copyValueOf(data, 1, 2)); // bc
System.out.println(String.copyValueOf(data, 4, 0).isEmpty()); // true
```

Taking `count == 0` within a valid range produces the empty string `""`; `offset == data.length` is allowed **if `count` is 0**. Otherwise, negative indices or out-of-bounds requests will throw an exception.

If you need to take from `from` (inclusive) to `toExclusive` (exclusive), compute `count = toExclusive - from`:

```java
char[] data = {'a', 'b', 'c', 'd', 'e'};
int from = 1;
int toExclusive = 4;

String result = String.copyValueOf(data, from, toExclusive - from);
System.out.println(result); // bcd
```

This is consistent with the half-open range convention across many Java APIs. Avoid passing `toExclusive` directly as `count` if the slice does not start at 0.

## 6. null, Invalid Ranges, and Exceptions

No valid string is returned when passing a `null` array to `copyValueOf`.

```java
char[] missing = null;

try {
    String.copyValueOf(missing);
} catch (NullPointerException e) {
    System.out.println("Source array is null");
}
```

A call with invalid `offset` or `count` throws `IndexOutOfBoundsException` (JDK versions may throw a specific subclass):

```java
char[] data = {'J', 'a', 'v', 'a'};

try {
    String.copyValueOf(data, 3, 2); // needs 2 chars starting from index 3
} catch (IndexOutOfBoundsException e) {
    System.out.println("Array slice out of bounds");
}
```

Do not confuse this with the `Object` overload of `String.valueOf`. Calling `String.valueOf((Object) null)` produces the text string `"null"`, whereas `String.copyValueOf((char[]) null)` throws `NullPointerException`. These are different contracts.

When data comes from user input or a buffer with computed `offset`/`count`, validate range invariants at system boundaries. If an array is required, letting an exception be thrown may be appropriate; if `null` has domain meaning, handle it explicitly before calling:

```java
static String safelyCopy(char[] data) {
    return data == null ? "" : String.copyValueOf(data);
}
```

This pattern chooses the empty string when the source is `null` **by application decision**, not as default API behavior.

## 7. char[] Consists of UTF-16 Units, Not Always "Visible Characters"

A `char` in Java is a 16-bit UTF-16 code unit. Many common Unicode characters, such as `'A'`, occupy one `char`. However, characters outside the Basic Multilingual Plane (BMP), such as the emoji `🚀` (U+1F680), are represented by a **surrogate pair of two `char`s**.

`copyValueOf(data, offset, count)` counts by **`char` elements**, not by Unicode code points and not by user-perceived characters (grapheme clusters).

```java
char[] symbols = {'A', '\uD83D', '\uDE80', 'B'};
String text = String.copyValueOf(symbols);

System.out.println(text.length()); // 4 UTF-16 units
System.out.println(text.codePointCount(0, text.length())); // 3 code points

String rocket = String.copyValueOf(symbols, 1, 2);
System.out.println(rocket); // 🚀
System.out.println(rocket.length()); // 2
```

If you slice a single element in the middle of a surrogate pair, the result may contain an unpaired surrogate; a Java string can still store that code unit, but subsequent Unicode processing/rendering may encounter issues.

When `offset`/`count` originate from code point positions, convert them properly to UTF-16 indices before using `copyValueOf`. You can start from a `String` and use `offsetByCodePoints` to determine boundaries:

```java
String source = "A🚀B";
int begin = source.offsetByCodePoints(0, 1);
int end = source.offsetByCodePoints(begin, 1);
char[] units = source.toCharArray();

String rocket = String.copyValueOf(units, begin, end - begin);
System.out.println(rocket); // 🚀
```

Here `begin == 1`, `end == 3`, so `count == 2`. These are the two `char` units representing one code point, fully matching the contract of `copyValueOf`.

**Do not confuse with encoding:** `copyValueOf` does not read bytes and does not apply `UTF-8` or any `Charset`; its input is already `char` units. When input is `byte[]`, you must decode with an appropriate charset (for example `new String(bytes, StandardCharsets.UTF_8)`), rather than `copyValueOf`.

## 8. Complete Java 17+ Example

Save the following code to **`CopyValueOfDemo.java`**:

```java
public class CopyValueOfDemo {

    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a', ' ', '1', '7'};

        String whole = String.copyValueOf(letters);
        String word = String.copyValueOf(letters, 0, 4);
        String tail = String.copyValueOf(letters, 5, 2);
        String byValueOf = String.valueOf(letters);
        String byConstructor = new String(letters);

        System.out.println("whole = " + whole);
        System.out.println("word = " + word);
        System.out.println("tail = " + tail);
        System.out.println("same text = "
                + (whole.equals(byValueOf) && whole.equals(byConstructor)));

        letters[0] = 'X';
        letters[5] = '2';

        System.out.println("array now = " + new String(letters));
        System.out.println("old string = " + whole);

        char[] roundTrip = word.toCharArray();
        roundTrip[0] = 'L';
        System.out.println("word remains = " + word);

        System.out.println("empty tail = "
                + String.copyValueOf(letters, letters.length, 0).isEmpty());

        System.out.println("object overload uses contents = "
                + String.valueOf((Object) letters).equals(new String(letters)));

        char[] symbols = {'A', '\uD83D', '\uDE80', 'B'};
        String line = String.copyValueOf(symbols);
        String rocket = String.copyValueOf(symbols, 1, 2);

        System.out.println("UTF16 units = " + line.length());
        System.out.println("code points = "
                + line.codePointCount(0, line.length()));
        System.out.println("rocket units = " + rocket.length());

        try {
            String.copyValueOf((char[]) null);
        } catch (NullPointerException e) {
            System.out.println("null -> NullPointerException");
        }

        try {
            String.copyValueOf(letters, 6, 2);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("bad range -> IndexOutOfBoundsException");
        }
    }
}
```

Run with JDK 17 or newer:

```bash
javac -encoding UTF-8 CopyValueOfDemo.java
java CopyValueOfDemo
```

Expected output:

```text
whole = Java 17
word = Java
tail = 17
same text = true
array now = Xava 27
old string = Java 17
word remains = Java
empty tail = true
object overload uses contents = false
UTF16 units = 4
code points = 3
rocket units = 2
null -> NullPointerException
bad range -> IndexOutOfBoundsException
```

Meaning of key lines:

- `whole` remains `"Java 17"` after `letters` became `"Xava 27"`: the created string is not live-linked to the array.
- `same text = true` confirms the three ways of creating a string have the same **content**, without concluding they are the same object.
- `empty tail = true` shows that `count = 0` is valid at the end of the array.
- `object overload uses contents = false` shows that casting `char[]` to `Object` changes the overload chosen when calling `String.valueOf`.
- `UTF16 units = 4` while `code points = 3` illustrates a surrogate pair; `rocket units = 2` is the `char` length of an emoji.
- The last two exceptions test `null` errors and invalid range errors separately.

## 9. When Should You Choose copyValueOf?

Use `String.copyValueOf(char[])` when you already have a character array containing data to convert into a string, and `String.copyValueOf(char[], offset, count)` when you only want to keep a slice without first creating a subarray manually.

Example with a buffer used during reading:

```java
char[] buffer = new char[8];
// Suppose a read API filled the first 3 characters: 'c', 'a', 't'
buffer[0] = 'c';
buffer[1] = 'a';
buffer[2] = 't';
int length = 3;

String snapshot = String.copyValueOf(buffer, 0, length);
// snapshot is "cat"; the rest of the buffer is not appended to the string
```

When only part of the array holds meaningful data, the three-parameter overload avoids including unused elements (such as `'\0'`) in the `String`.

Notes on making the choice:

- In terms of **resulting content**, `String.valueOf(char[])` and `String.copyValueOf(char[])` are equivalent. You can choose whichever style is familiar in your codebase.
- Do not use `String.copyValueOf` to concatenate multiple arrays, convert arbitrary object types, or decode `byte[]`. If you need to join multiple slices, `StringBuilder` or an appropriate concatenation method usually expresses the intent more clearly.
- Creating a new `String` from an array has processing and memory costs proportional to length; when looping over large data, measure your actual case. Do not speculate about internal details of individual JDKs.
- If the array holds secrets that must be cleared from memory immediately after use, converting it into an immutable `String` can make data lifecycle control difficult; consider security requirements before creating a string.
- For Unicode text, check UTF-16 boundaries and normalize separately if the problem requires Unicode equivalence comparison; `copyValueOf` does not automatically normalize diacritics or code points.

## 10. Common Mistakes

1. **Using `charArray.toString()` expecting to get the content.** That method represents the array object, not the joined characters. Use `String.copyValueOf(charArray)`.
2. **Confusing `count` with `endIndex`.** `copyValueOf(data, 2, 5)` means taking **five characters starting at index 2**, not taking indices 2, 3, 4.
3. **Keeping a reference to the array and thinking modifying the array changes the string.** `String` is immutable; the created snapshot does not change.
4. **Failing to check `null` or bounds.** `copyValueOf(null)` causes `NullPointerException`; an out-of-bounds slice causes `IndexOutOfBoundsException`.
5. **Casting the array to `Object` when calling `String.valueOf`.** The `valueOf(Object)` overload does not join `char[]` elements into text.
6. **Using `Arrays.toString(char[])` when a continuous string is needed.** It is used to display the array structure, such as `[H, i]`.
7. **Assuming a `char` corresponds to one Unicode code point.** A character outside the BMP usually occupies two UTF-16 units; a range might split a surrogate pair by mistake.
8. **Confusing the valid character count of a buffer with `buffer.length`.** If a buffer only holds partial data, you must pass the exact `offset` and `count`.
9. **Comparing strings with `==` instead of `equals`.** Results created from different APIs may be distinct objects with the same text.

## 11. Self-Check Exercises

**Exercise 1.** With the following code, what is the output?

```java
char[] data = {'A', 'B', 'C', 'D', 'E'};
System.out.println(String.copyValueOf(data, 1, 3));
```

**Answer:** `BCD`. Starts at index 1 and takes three elements.

**Exercise 2.** Why does `String.copyValueOf(data, 2, 4)` throw an exception when `data.length == 5`?

**Answer:** The intended range is `[2, 6)`, which extends beyond the array's `[0, 5)`. `count` must be less than or equal to `5 - 2 = 3`.

**Exercise 3.** After running the following code, does `s` change to `"Xbc"`?

```java
char[] data = {'a', 'b', 'c'};
String s = String.copyValueOf(data);
data[0] = 'X';
```

**Answer:** No. `s` remains `"abc"` because modifying the source array afterward does not affect the created `String`.

**Exercise 4.** Is `String.copyValueOf(data, 0, 1)` guaranteed to extract an entire emoji at the beginning of the array?

**Answer:** Not guaranteed. Emojis outside the BMP usually consist of two UTF-16 `char`s. You must determine the exact code point boundary before slicing by `char`.

**Exercise 5.** Why shouldn't `String.valueOf((Object) data)` be used to convert `char[]` to text?

**Answer:** It selects the `valueOf(Object)` overload and returns the array object's representation. To join `char` elements, use `String.valueOf(data)` with static type `char[]`, `String.copyValueOf(data)`, or `new String(data)`.

## References

- [Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `copyValueOf` and `valueOf` overloads, `char[]` constructors, `toCharArray`, and immutability rules.
- [Java SE 17 — Character API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): UTF-16 code units, code points, and surrogate pairs.

**Key takeaway:** `copyValueOf` creates a `String` from an entire `char[]` array or a slice of it, `offset` is the starting position, `count` is the number of **UTF-16 `char` units** taken, and the string's content does not change when the source array is modified later.