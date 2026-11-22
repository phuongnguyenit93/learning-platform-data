# Creating a `String` from `char[]` or a Slice of an Array in Java

In Java, `char[]` is a mutable array containing `char` values; `String` is an **immutable** sequence of characters. When you already have data in `char[]` form and need a string to display, compare, pass to an API, or store as a processing result, you can create a `String` from **the entire array** or from **a contiguous slice** of the array. The two constructors to master are `new String(char[])` and `new String(char[], int offset, int count)`.

## 1. Two Ways to Create the String

| Syntax | Which characters are taken? | Result |
| --- | --- | --- |
| `new String(char[] value)` | All elements from index `0` to `value.length - 1` | A `String` whose content matches the entire array at creation time |
| `new String(char[] value, int offset, int count)` | `count` consecutive elements starting at `offset` | A `String` containing the exact selected slice |

For the second constructor:

- `value`: the source `char[]` array.
- `offset`: the **starting index**, zero-based, inclusive of the element at that index.
- `count`: the **number of elements to take**, not the ending index.
- The copied range has the form **[offset, offset + count)**: taking from `offset` through `offset + count - 1`. The `)` means the element at index `offset + count` is excluded.

Example with the array `{'J', 'a', 'v', 'a', ' ', '1', '7'}`:

| Index | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Value | J | a | v | a | space | 1 | 7 |

`new String(chars, 0, 4)` takes four characters at indices 0, 1, 2, 3, yielding `"Java"`. `new String(chars, 5, 2)` takes two characters at indices 5, 6, yielding `"17"`.

## 2. Standalone Runnable Java 17+ Example

Save the following program to **`CharArrayToStringDemo.java`**:

~~~java
public class CharArrayToStringDemo {
    public static void main(String[] args) {
        char[] chars = {'J', 'a', 'v', 'a', ' ', '1', '7'};

        String whole = new String(chars);
        String word = new String(chars, 0, 4);
        String version = new String(chars, 5, 2);
        String empty = new String(chars, chars.length, 0);

        System.out.println("whole = " + whole);
        System.out.println("word = " + word);
        System.out.println("version = " + version);
        System.out.println("empty length = " + empty.length());

        chars[0] = 'X'; // Modify the array after creating the String
        System.out.println("chars[0] = " + chars[0]);
        System.out.println("whole after array change = " + whole);
        System.out.println("word after array change = " + word);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CharArrayToStringDemo.java
java CharArrayToStringDemo
~~~

Expected output:

~~~text
whole = Java 17
word = Java
version = 17
empty length = 0
chars[0] = X
whole after array change = Java 17
word after array change = Java
~~~

Key takeaway: the constructors **copy the character contents** at the time of invocation. Changing `chars[0]` from `'J'` to `'X'` only modifies the array; `whole` and `word` retain their old contents. You also cannot modify a character in a `String` via assignment like `whole.charAt(0) = 'X'` because `charAt()` returns a value, not an assignable location. When you need a new string from a modified array, call the constructor again.

## 3. Validating Start Position and Length

Let `n = value.length`. A valid range must simultaneously satisfy:

- `offset >= 0`;
- `count >= 0`;
- `offset <= n - count` (equivalent to choosing a range that does not exceed the end of the array; the subtraction form also avoids integer overflow when checking `int` values yourself).

If `offset` is negative, `count` is negative, or the range exceeds the array, `new String(value, offset, count)` throws **`IndexOutOfBoundsException`**. When `value` is `null`, the operation cannot read characters and throws **`NullPointerException`**. These are runtime errors; the constructor does not silently clamp the range to valid bounds.

Several boundary cases to distinguish:

| `value.length` | `offset` | `count` | Valid? | Meaning |
| ---: | ---: | ---: | --- | --- |
| 3 | 0 | 3 | Yes | Takes the entire array |
| 3 | 1 | 2 | Yes | Takes the last two characters |
| 3 | 0 | 0 | Yes | Empty string |
| 3 | 3 | 0 | Yes | Empty string starting right after the last character |
| 3 | 4 | 0 | No | `offset` exceeds `length` |
| 3 | 2 | 2 | No | Tries to read through index 3, exceeding the array |
| 3 | -1 | 1 | No | Negative `offset` |
| 3 | 1 | -1 | No | Negative `count` |

You can verify this behavior with the standalone program **RangeValidationDemo.java**:

~~~java
public class RangeValidationDemo {
    public static void main(String[] args) {
        char[] data = {'a', 'b', 'c'};

        System.out.println("valid = " + new String(data, 1, 2));
        System.out.println("empty = " + new String(data, 3, 0).length());

        try {
            new String(data, 2, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("out of range");
        }

        try {
            new String((char[]) null);
        } catch (NullPointerException ex) {
            System.out.println("null array");
        }
    }
}
~~~

Run `javac -encoding UTF-8 RangeValidationDemo.java` then `java RangeValidationDemo`:

~~~text
valid = bc
empty = 0
out of range
null array
~~~

The cast syntax `(char[]) null` in the example helps Java choose the exact constructor taking `char[]`; calling `new String(null)` without a specific type is **ambiguous** because `String` has multiple constructors taking reference types.

When indices come from external input or calculations, validate the bounds before creating the string. For instance, the helper method below returns a result only when the range is valid:

~~~java
static String take(char[] source, int offset, int count) {
    if (source == null) {
        throw new IllegalArgumentException("source must not be null");
    }
    if (offset < 0 || count < 0 || offset > source.length - count) {
        throw new IllegalArgumentException("invalid slice");
    }
    return new String(source, offset, count);
}
~~~

This is an **illustrative method snippet** that must be placed inside a Java class to compile. The exception type in the example is the `take` method's choice for reporting invalid input; `String`'s constructors throw the exceptions described above.

## 4. Copying, Immutability, and Data Lifecycle

`char[]` is an in-place mutable structure: `chars[i] = 'x'` modifies the array. The created `String` does not change its value afterward. The two `char[]` constructors copy the selected characters; they do not provide a "live window" linked to the original array. Therefore:

1. Modifying the array **before** creating the string affects the contents of the string created afterward.
2. Modifying the array **after** creating the string does **not** affect the existing string.
3. Calling `new String(chars)` twice creates two separate `String` objects even though their contents are equal; compare string values using `equals()`, not `==`.
4. Do not infer internal representation details of `String` (such as internal array size) from the constructor; the API only guarantees content and immutability.

For passwords or sensitive data, converting `char[]` to `String` creates another immutable copy of the content that the program cannot clear character-by-character on demand; consider security requirements and the input-receiving API before creating a string.

## 5. Unicode Note: A `char` Is Not Always One Visible Character

Each Java `char` represents **one UTF-16 code unit (16-bit)**. A Unicode character outside the Basic Multilingual Plane (such as many emojis) requires **two `char`s**, called a *surrogate pair*. Thus `offset` and `count` count `char[]` elements, **not visible characters or code points**.

The example below is a **code snippet placed inside a Java method**:

~~~java
char[] units = "A😀B".toCharArray();
System.out.println(units.length); // 4: A, high surrogate, low surrogate, B

String emoji = new String(units, 1, 2);
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1

String broken = new String(units, 1, 1); // Only takes the high surrogate
System.out.println(broken.length()); // 1, but not a complete emoji
~~~

The printed numbers are `4`, `2`, `1`, and `1` respectively. The range `[1, 3)` keeps the emoji's surrogate pair intact; the range `[1, 2)` splits the pair in half, producing a string with an unpaired surrogate. When processing multilingual text, determine indices in UTF-16 code units and avoid slicing in the middle of a surrogate pair. If your application needs to slice by **code point**, use APIs such as `codePointCount()`, `offsetByCodePoints()`, or operate on `codePoints()` before determining the slice to take. Even slicing on code point boundaries does not guarantee keeping every visual character cluster intact, such as characters with combining marks.

**Distinguishing `char[]` from `byte[]`:** constructors taking `char[]` do not decode an encoding. For byte data, you must use a decoding mechanism and specify the appropriate charset, such as `new String(bytes, StandardCharsets.UTF_8)`. Never cast bytes to chars arbitrarily as a substitute for decoding.

## 6. Equivalent Forms and Usage Choices

The following calls create strings with the same **content value** when inputs are valid:

~~~java
char[] data = {'H', 'e', 'l', 'l', 'o'};
String a = new String(data);
String b = String.valueOf(data);
String c = String.copyValueOf(data);

String partA = new String(data, 1, 3);
String partB = String.valueOf(data, 1, 3);
String partC = String.copyValueOf(data, 1, 3);
~~~

Result: `a`, `b`, `c` all have the value `"Hello"`; `partA`, `partB`, `partC` all have the value `"ell"`. All calls in the group creating a string from `char[]` capture the content at invocation time. You can use `new String(chars, offset, count)` when you want to clearly express creating from a slice of an array; `String.valueOf(...)` is also a familiar choice.

Do not confuse with:

- `Arrays.toString(data)`: produces an array-element display format such as `"[H, e, l, l, o]"`, **different** from `"Hello"`.
- `new String(data, 1, 4)`: takes **four** characters starting at index 1, i.e., `"ello"`; it does not take from index 1 **to** index 4 as an end index.
- `new String(data, 0, data.length + 1)`: exceeds the valid range and throws an exception.
- `StringBuilder`: useful when continuously appending/modifying characters before producing a `String` result; it is unnecessary for copying an existing `char[]` slice.

## 7. Real-World Scenario: Taking Only the Data Actually Read

When reading into a `char[]` buffer from a `Reader`, the number of characters actually read is often smaller than the total buffer size. In a snippet **placed inside a method allowed to throw `IOException`** where `reader` is an open `java.io.Reader`:

~~~java
char[] buffer = new char[1024];
int count = reader.read(buffer);
if (count != -1) {
    String chunk = new String(buffer, 0, count);
    System.out.println("Read " + chunk.length() + " UTF-16 code units");
}
~~~

`reader.read(buffer)` returns the number of `char` units written into the buffer, or `-1` on end-of-stream; use `count` to take only the populated portion. If you use `new String(buffer)`, the result may contain unread elements or leftovers from a previous read. If you want to assemble the entire content across multiple reads, accumulate using `StringBuilder` or an appropriate line/stream processing mechanism. With Unicode data, watch out for surrogate boundaries when processing each chunk independently.

## 8. Self-Check

**Question 1.** Given `char[] a = {'0', '1', '2', '3', '4'};`, what does `new String(a, 2, 2)` return?

Answer: `"23"`, because it takes the elements at indices 2 and 3.

**Question 2.** An array has length 5. How do `new String(a, 5, 0)` and `new String(a, 5, 1)` differ?

Answer: the first call is valid and creates an empty string; the second requests an element at index 5 (which does not exist), so it throws `IndexOutOfBoundsException`.

**Question 3.** Why does modifying `char[]` after creating a `String` not change the `String`'s value?

Answer: the constructor copied the array's contents, and `String` is an immutable type.

**Question 4.** Does `count = 1` always mean one complete Unicode character?

Answer: no. `count` counts UTF-16 code units; a supplementary code point can require two `char`s, and a visible character cluster can consist of multiple code points.

## References

- [Java SE 17 — String constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): official description of array copying, `offset`, `count`, and exceptions.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): how Java represents Unicode code points and surrogate pairs.
