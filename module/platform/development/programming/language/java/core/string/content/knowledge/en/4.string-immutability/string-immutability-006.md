# Copying `char[]` Input and the Independence of `String.toCharArray()` in Java

## 1. Two Conversion Directions, One Principle: Protecting `String` Immutability

In Java, `char[]` is a **mutable** array: element `array[i]` can be reassigned. In contrast, `String` represents an **immutable text value**. For these two types to interoperate safely, the Java API maintains a data-copying boundary in both directions:

1. **`char[]` → `String`:** `new String(charArray)` captures the contents of the array elements at the moment the string is created. Modifying the source array **after the constructor finishes** does not change the created string.
2. **`String` → `char[]`:** `string.toCharArray()` returns a **new array** containing the string's character units. Modifying the returned array does not change the source `String`.
3. APIs such as `String.valueOf(char[])`, `String.copyValueOf(char[])`, `new String(char[], offset, count)`, and `String.getChars(...)` also have corresponding transfer/copy contracts; you should clearly distinguish where a copy lives and where an array is still shared.

Visualized by content ownership, once the `String` has been created:

```text
char[] input = {'J','a','v','a'}  [MUTABLE ARRAY]
        │
        │ new String(input): snapshots element values
        ▼
String text = "Java"             [IMMUTABLE VALUE]
        │
        │ text.toCharArray(): creates a new array
        ▼
char[] output = {'J','a','v','a'} [MUTABLE, INDEPENDENT ARRAY]

input[0] = 'K'  → text is still "Java", output is still "Java"
output[0] = 'X' → text is still "Java", input is still "Kava"
```

The diagram only describes the **data contract**. It does not assert that `String` must use `char[]` as its internal storage structure. Memory representation details of `String` may vary across JDK versions or implementations; what you can rely on is immutability and the independence observable through the API.

## 2. `char[]` Is Mutable; Plain Array Assignment Does Not Make a Copy

A variable of type `char[]` holds a **reference to an array object**. Assigning that reference to another variable does not duplicate the elements:

```java
char[] input = {'J', 'a', 'v', 'a'};
char[] alias = input; // Two variables point to the same array.
alias[0] = 'K';

System.out.println(new String(input)); // Kava
System.out.println(input == alias);     // true
```

This is an **illustrative snippet**; the `System.out.println` lines belong inside a method such as `main`. `alias[0] = 'K'` modifies the exact array that `input` references. The core difference is:

| Expression | Creates a data copy? | After modifying the source array |
| --- | --- | --- |
| `char[] b = a;` | No, only copies the reference | `b` observes changes in `a` |
| `char[] b = a.clone();` | Yes, creates a new array with copied elements | `b` keeps its own content |
| `char[] b = Arrays.copyOf(a, a.length);` | Yes, creates a new array | `b` keeps its own content |
| `String s = new String(a);` | Yes, creates a string value from array content | `s` does not change |
| `char[] b = s.toCharArray();` | Yes, returns a new array from the string | Modifying `b` does not change `s` |

For `char[]`, `clone` is a deep enough copy to be independent in terms of **elements**, because each `char` element is a primitive value, not a reference to an internally mutable object.

## 3. Constructor `new String(char[])` Copies the Input Content

The direct way to create an immutable string from a character array is:

```java
char[] source = {'H', 'e', 'l', 'l', 'o'};
String text = new String(source);
source[0] = 'Y';

System.out.println(new String(source)); // Yello
System.out.println(text);               // Hello
```

How to read this properly:
- Once `new String(source)` completes, `text` has content `"Hello"` and that content is protected from subsequent modifications to the source array.
- `source[0] = 'Y'` changes the first element of the source array; `text` does not hold a mutable view pointing back to the array.
- You do not need `source.clone()` before `new String(source)` solely to protect the `String` from *later* changes: the constructor already satisfies the required independence contract. Explicitly cloning only makes sense when the application also needs to own **another separate array**.

Overloads with equivalent semantics:

```java
char[] chars = {'J', 'a', 'v', 'a'};

String a = new String(chars);
String b = String.valueOf(chars);
String c = String.copyValueOf(chars);
```

All three produce `"Java"` content independent of subsequent changes to `chars`. `String.copyValueOf(char[])` has behavior equivalent to `String.valueOf(char[])`; the name `copyValueOf` does not imply that `valueOf(char[])` keeps the array by reference.

**Common overload pitfall:** `String.valueOf(char[])` and `String.valueOf(Object)` are two different overloads. Casting the array to `Object` makes Java choose the `Object` overload, which uses the array's object representation:

```java
char[] chars = {'O', 'K'};
System.out.println(String.valueOf(chars));          // OK
System.out.println(String.valueOf((Object) chars)); // Form [C@..., not "OK"
```

This is an illustrative snippet, not a standalone class file. The `[C@...` form consists of the `char[]` array type tag and an unstable identifier portion; you must not rely on its full contents.

## 4. `toCharArray()` Always Hands Over a Character Array for the Caller to Own and Mutate

`String.toCharArray()` returns a **new** `char[]` containing the content at the time of the call. The caller can edit, sort, refill, or pass the array around without being able to mutate the source `String` through that array.

```java
String text = "Java";
char[] first = text.toCharArray();
char[] second = text.toCharArray();

first[0] = 'K';
second[1] = 'O';

System.out.println(text);               // Java
System.out.println(new String(first));  // Kava
System.out.println(new String(second)); // JOva
System.out.println(first == second);    // false
```

Two calls to `toCharArray()` return two distinct arrays. Neither is a "backdoor" to alter the original string. When you need the content of a `String` as a `char[]`, this is the standard way to **explicitly create mutable data**.

Do not mistakenly assume `String` always contains a pre-existing `char[]` that `toCharArray()` simply hands back; that assumption leads learners to write code that depends on internal structure and goes against the API contract.

### Complete Runnable Program: Two-Way Copying

Save as `CharArrayCopyDemo.java`:

```java
public class CharArrayCopyDemo {
    public static void main(String[] args) {
        char[] input = {'J', 'a', 'v', 'a'};
        char[] alias = input;

        String byConstructor = new String(input);
        String byValueOf = String.valueOf(input);
        String byCopyValueOf = String.copyValueOf(input);

        alias[0] = 'K'; // input also changes: alias and input are one array.
        System.out.println(new String(input));
        System.out.println(byConstructor);
        System.out.println(byValueOf);
        System.out.println(byCopyValueOf);

        char[] extracted = byConstructor.toCharArray();
        extracted[0] = 'X';
        System.out.println(new String(extracted));
        System.out.println(byConstructor);

        char[] extractedAgain = byConstructor.toCharArray();
        System.out.println(extracted == extractedAgain);
        System.out.println(new String(extractedAgain));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CharArrayCopyDemo.java
java CharArrayCopyDemo
```

Expected output:

```text
Kava
Java
Java
Java
Xava
Java
false
Java
```

Explanation from the output:
- `alias[0]` modifies the original array; all three strings created from the array remain `Java`.
- `extracted[0]` only modifies the first array returned by `toCharArray()`.
- `byConstructor` does not change, and the next call to `toCharArray()` yields the original content again.
- `extracted == extractedAgain` is `false` because these are **two arrays** created by two separate calls.

## 5. Copying Only a Slice of an Array: `new String(char[], offset, count)`

Not always does the entire source array belong to the text to be stored. The constructor `new String(char[] value, int offset, int count)` uses a **contiguous slice** starting at index `offset` and consisting of `count` `char` elements:

```java
char[] frame = {'[', 'J', 'a', 'v', 'a', ']'};
String inner = new String(frame, 1, 4);
frame[1] = 'X';

System.out.println(inner);              // Java
System.out.println(new String(frame));  // [Xava]
```

The copied range is `[offset, offset + count)`: start inclusive, end exclusive. For the example array, elements at indices 1, 2, 3, 4 form the content `Java`, excluding the two brackets. The data inside `inner` is independent of the entire `frame` array, including the positions inside the copied slice.

Validity conditions: `offset >= 0`, `count >= 0`, and `offset + count <= value.length` (expressed as index bound conditions; implementations check in a way that avoids integer overflow). `count == 0` is valid if `offset` is within the valid range, including `offset == value.length`. Invalid offset/count throws `IndexOutOfBoundsException`; passing a `null` array throws `NullPointerException`.

Distinguish from `Arrays.copyOfRange(array, from, to)`:
- `new String(array, offset, count)` returns **`String`**, and the third parameter is the **count** of elements.
- `Arrays.copyOfRange(array, from, to)` returns **`char[]`**, and the third parameter is the **exclusive end index**; for some inputs where `to` exceeds array length, the method also has default-padding element rules. Do not swap the two rules.

## 6. Copying from `String` into an Existing Array: `getChars`

If you already have a destination array, `String.getChars(srcBegin, srcEnd, dst, dstBegin)` copies characters from the string into **that array**. The method does not return a new array; `dst` is an object supplied by the caller. It still provides no path to mutate back into the `String`.

Parameter definitions:
- `srcBegin`: starting index in the string, inclusive.
- `srcEnd`: ending index in the string, exclusive.
- `dst`: destination array receiving the data.
- `dstBegin`: starting index to write into the destination array.

Complete example, saved as `SliceCopyDemo.java`:

```java
public class SliceCopyDemo {
    public static void main(String[] args) {
        char[] frame = {'[', 'J', 'a', 'v', 'a', ']'};
        String inner = new String(frame, 1, 4);

        char[] destination = {'_', '_', '_', '_', '_', '_'};
        inner.getChars(1, 3, destination, 2); // Copy "av" into positions 2, 3.

        frame[1] = 'X';
        destination[2] = 'Z';

        System.out.println(inner);
        System.out.println(new String(frame));
        System.out.println(new String(destination));
        System.out.println(new String(inner.toCharArray()));
    }
}
```

```bash
javac -encoding UTF-8 SliceCopyDemo.java
java SliceCopyDemo
```

```text
Java
[Xava]
__Zv__
Java
```

Because `srcEnd` is an **exclusive** index, `getChars(1,3,...)` copies the two characters `a` and `v`, placing them into `destination[2]` and `destination[3]`. After changing the destination character to `Z`, `destination` prints `__Zv__`; the string `inner` remains `Java`. You must allocate a large enough destination array and use valid indices, otherwise bounds exceptions occur; `dst == null` is also invalid.

Use `getChars` when you need to fill part of an array managed by the caller; use `toCharArray()` when you want a new array containing the **entire** string.

## 7. Immutability, Snapshots, and Defensive API Design

Suppose a class accepts a caller's `char[]` data to store as a text value. If the class stores the array reference directly in a `char[]` field, the caller can still modify the data from outside. If the class only needs string data, converting to `String` in the constructor creates an immutable text value; when needing to return a mutable array, create the array via `toCharArray()`.

Save `ImmutableLabel.java`:

```java
import java.util.Objects;

public final class ImmutableLabel {
    private final String value;

    public ImmutableLabel(char[] input) {
        Objects.requireNonNull(input, "input");
        this.value = new String(input);
    }

    public String text() {
        return value;
    }

    public char[] characters() {
        return value.toCharArray();
    }

    public static void main(String[] args) {
        char[] source = {'H', 'e', 'l', 'l', 'o'};
        ImmutableLabel label = new ImmutableLabel(source);

        source[0] = 'Y';
        char[] exported = label.characters();
        exported[1] = 'X';

        System.out.println(new String(source));
        System.out.println(new String(exported));
        System.out.println(label.text());
    }
}
```

```bash
javac -encoding UTF-8 ImmutableLabel.java
java ImmutableLabel
```

```text
Yello
HXllo
Hello
```

The `value` field is `final`, meaning the reference cannot be reassigned after the constructor, while the `String` value it references is immutable. Even though the caller modifies `source` or the `exported` array, `label.text()` remains `Hello`. This is a form of **defensive copy** at the input/output boundary; in the example, both copy operations are guaranteed by the `String` API itself.

If a class needs to keep a mutable array internally (for example, because an algorithm requires in-place character edits), it can accept `input.clone()` and return a copy when returning the array. However, a `private final char[]` field **does not automatically make array contents immutable**: `final` only locks the field's reference, not `array[i]`.

### Why Does Copy Timing Matter?

A `String` created from an array is a **snapshot of values at the moment the constructor reads the array**, not a live link. After that point, modifying the array does not affect the string. Conversely, if another thread is **concurrently modifying the array while the program is copying it**, you must not assume the copy produces a consistent point-in-time snapshot: you need synchronization control, data ownership, or avoidance of overlapping updates. Immutability of the string after creation **does not replace** synchronization mechanisms when the input data is actively being mutated.

## 8. UTF-16: Copying `char[]` Does Not Mean Copying "Visible Characters"

`char` is a **UTF-16 code unit** (16 bits). Both `String.length()` and `string.toCharArray().length` measure the number of UTF-16 code units, not necessarily the number of Unicode code points or user-perceived characters (*grapheme clusters*).

For example, the emoji `🙂` lies outside the BMP and is represented by **two** `char` elements (a surrogate pair). `toCharArray()` preserves those two code units in order; `new String(array)` reconstructs the corresponding string content.

Save `UnicodeCopyDemo.java` in UTF-8 encoding:

```java
public class UnicodeCopyDemo {
    public static void main(String[] args) {
        String original = "A🙂B";
        char[] units = original.toCharArray();
        String roundTrip = new String(units);

        System.out.println(original.length());
        System.out.println(units.length);
        System.out.println(original.codePointCount(0, original.length()));
        System.out.println(roundTrip.equals(original));

        units[0] = 'X';
        System.out.println(original);
        System.out.println(new String(units));
    }
}
```

```bash
javac -encoding UTF-8 UnicodeCopyDemo.java
java UnicodeCopyDemo
```

```text
4
4
3
true
A🙂B
X🙂B
```

Three Unicode code points (`A`, `🙂`, `B`) occupy four `char`s. Copying to an array and back preserves the string, yet modifying **one half** of a surrogate pair by itself can produce an invalid UTF-16 sequence. When you want to handle Unicode by code point, look at `codePoints()`, `codePointAt()`, `offsetByCodePoints()`, or appropriate APIs; using `char[]` does not resolve code point boundaries on its own.

## 9. Copy Cost, Performance, and Sensitive Data

Both conversion directions have cost proportional to data size in terms of copying operations. If a loop repeatedly converts `String` ↔ `char[]`, it can create extra objects, increase allocations, and add garbage-collector pressure. Before optimizing, choose the data model that fits the actual job:
- If you only need to read and store strings, keep using `String`; do not call `toCharArray()` just to iterate characters when `charAt`/`codePoints` may suffice.
- If you need bulk character transformations, create the array once, process it, and create the `String` once when finished (or consider `StringBuilder` depending on the operation).
- If an API takes `char[]` while the caller only has `String`, `toCharArray()` is the standard conversion; be aware it creates new data to manage.
- If an API takes `String` while the caller owns `char[]`, `new String(chars)` clearly expresses the intent to create an independent text value.

In some security contexts, passwords or secrets are kept in `char[]` to allow overwriting **the array the application owns** after use, such as `Arrays.fill(secret, '\0')`. Once converted to `String`, the application has no equivalent API mechanism to wipe the immutable string's content on demand; therefore do not create a `String` merely for convenience if you need lifecycle control over sensitive data. Even when overwriting an array, you cannot guarantee every copy across the JVM/system has been erased.

## 10. Common Mistakes and Self-Check

| Misconception | Consequence | Fix |
| --- | --- | --- |
| `char[] alias = source` copies content | Modifying through `alias` changes `source` | Use `clone`/`Arrays.copyOf` when you want a new array |
| `new String(source)` still shares source `char[]` | Unfounded worry about string mutation | Trust the constructor's copy contract |
| `toCharArray()` returns `String`'s internal backing array | Trying to use the array to mutate the original string | Understand it is a new array, edited independently |
| `String.valueOf(char[])` keeps the array | Mistaking it for a kind of view | It is a conversion to an independent string |
| `String.valueOf((Object) chars)` matches `String.valueOf(chars)` | Produces text like `[C@...` | Pass the proper `char[]` type |
| `new String(arr, from, to)` treats `to` as end index | Copies the wrong range | The third parameter is `count` |
| `getChars` creates a new array | Misunderstanding where data is written | Supply a `dst` with sufficient capacity |
| `final char[]` is an immutable array | Element changes leak through aliases | Copy the array on input/output or use `String` |
| `toCharArray().length` equals visible character count | Splits surrogate pairs or graphemes | Account for UTF-16 units/code points/graphemes |

### Self-Check by Predicting Output

Predict the output before reading the explanation:

```java
char[] data = {'a', 'b'};
String text = new String(data);
char[] out = text.toCharArray();
data[0] = 'x';
out[1] = 'y';

System.out.println(new String(data));
System.out.println(text);
System.out.println(new String(out));
```

This is a snippet placed in `main`, not a standalone class. The output is:

```text
xb
ab
ay
```

The three values differ because the source array, the `String` object, and the array returned by `toCharArray()` each hold separate contents. Modifying either array after creating the string does not propagate to the string or the other array.

## 11. Programming Takeaways

- `new String(char[])`, `String.valueOf(char[])`, and `String.copyValueOf(char[])` create a string whose content is **independent** of subsequent changes to the source array.
- `String.toCharArray()` creates a **new** array; callers can freely modify that array without modifying the source string.
- `char[] b = a` is only an **alias**, not a copy; `a.clone()` or `Arrays.copyOf` creates a separate array.
- `new String(chars, offset, count)` copies a slice by **offset and element count**; `getChars(begin, end, dst, dstBegin)` copies into an **existing destination array** with an exclusive end index.
- Copying preserves UTF-16 code units, but does not turn a `char` into a Unicode code point or visible character.
- Copy independence is especially useful when building immutable APIs, though copy cost, synchronization timing, and sensitive data must be weighed in context.

## Java SE 17 API References

- [`String(char[])`, `String(char[], int, int)`, `toCharArray()`, and `getChars()` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Arrays.copyOf` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)
- [`Character` and Unicode — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
