# Relationships Between `String`, `char[]`, `CharSequence`, and `Object` in Java

## 1. Goals and the Big Picture

In Java, the same text content can appear under several types: a `String` object, a `char[]` array, an object implementing `CharSequence`, or an `Object` reference. These types are **not synonymous**, even when they sometimes represent the exact same characters. To use them properly, you need to distinguish three questions:

1. **Types and inheritance relationships:** assigning a value to which variable type is valid?
2. **Mutability and data ownership:** does modifying the original object/array change the content being observed?
3. **Operation semantics:** how will `equals`, `toString`, `charAt`, `length`, and conversions process the data?

Type diagram (Java 17+):

```text
java.lang.Object
  ├── java.lang.String (final)
  │      └── implements CharSequence, Comparable<String>, Serializable, ...
  ├── java.lang.StringBuilder (mutable, implements CharSequence)
  ├── java.lang.StringBuffer  (mutable, implements CharSequence)
  ├── java.nio.CharBuffer     (implements CharSequence)
  └── char[]                  (array type; is an Object, does NOT implement CharSequence)

java.lang.CharSequence is an interface (a contract for reading a char sequence),
not a superclass of Object and not an array type.
```

Every `String` and every `char[]` array is a Java object, so both can be held in an `Object` variable. However, `char[]` is **not** a `String` or a `CharSequence`; there is no direct type-assignment relationship between them. `String` is both an `Object` and a `CharSequence` because the class implements that interface.

| Type | Nature | Modify content through that value itself? | Key relationships |
| --- | --- | --- | --- |
| `String` | `final` class holding an immutable character sequence | No | `extends Object`; `implements CharSequence` |
| `char[]` | Array of primitive `char` elements | Yes, by assigning `array[i]` | Is an `Object`; does not implement `CharSequence` |
| `CharSequence` | Interface for reading a `char` sequence | Interface has no mutation operations; the actual object *may* be mutable | Implemented by `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` |
| `Object` | Root class of Java objects | Does not define text content | Only provides the general object contract |

**Distinguishing variable from object:** `String name = "A"; name = "B";` is **reassigning the reference** of the variable `name`, not modifying the content of the `String("A")` object.

## 2. `String` is an `Object` and implements `CharSequence`

The abbreviated declaration in Java 17 is:

```java
public final class String
        implements java.io.Serializable,
                   Comparable<String>,
                   CharSequence,
                   java.lang.constant.Constable,
                   java.lang.constant.ConstantDesc {
    // Method bodies omitted.
}
```

This is only an **illustrative signature**, not a self-compiling class: implementation methods and fields have been omitted. `String` inherits from `Object` under Java rules even though the declaration does not explicitly write `extends Object`.

A `String` object can be viewed through multiple reference types:

```java
String text = "Hello";
CharSequence sequence = text; // upcast: valid
Object object = text;         // upcast: valid

System.out.println(sequence.length());     // 5
System.out.println(object instanceof String); // true
```

When the static type is `CharSequence`, the program can only call methods declared in the `CharSequence` contract (plus `Object` methods), even though the actual object is a `String`. When the static type is `Object`, `object.length()` does not compile because `Object` does not declare `length()`. You must check and cast first:

```java
if (object instanceof String actual) {
    System.out.println(actual.length()); // 5
}
```

A cast `(String) object` is valid only when the actual object is a `String` (or `null`). If `object` currently holds a `char[]` or `StringBuilder`, casting to `String` throws `ClassCastException`. Casting does not perform content conversion.

## 3. `char[]`: a mutable array that does not automatically become a string

`char` is a 16-bit primitive type representing a **UTF-16 code unit**. `char[]` is an **array object** holding multiple `char` values, has a `length` field (not a `length()` method), and allows modifying elements.

```java
char[] letters = {'J', 'a', 'v', 'a'};
letters[0] = 'K';
System.out.println(letters.length); // 4
```

`String` does not provide assignment syntax like `text[0] = 'K'` and has no methods to mutate character positions in place. Operations such as `replace`, `substring`, or `concat` produce a `String` result without modifying the existing string value; the fact that the JVM may reuse objects in certain cases does not change its immutability.

Converting `char[]` to `String` creates text content from the **element values at the time of conversion**:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = new String(letters);
letters[0] = 'K';
System.out.println(text);                // Java
System.out.println(new String(letters)); // Kava
```

The `new String(char[])` constructor **copies the content**. `String.valueOf(char[])` and `String.copyValueOf(char[])` also create a string from the array's characters. Modifying the source array afterward does not change the created `String`. Conversely, `text.toCharArray()` returns a new mutable array without mutating the original string:

```java
String text = "Java";
char[] copy = text.toCharArray();
copy[0] = 'K';
System.out.println(text);        // Java
System.out.println(new String(copy)); // Kava
```

To copy a range of characters into an existing array, use `text.getChars(srcBegin, srcEnd, destination, dstBegin)` and ensure the destination has enough space. When processing repeatedly in array form, weigh the cost of creating copies against data-ownership requirements.

**Memory note:** `String`'s API model expresses a sequence of UTF-16 code units; do not infer that Java is required to store `String` internally as a `char[]`. Modern JDKs may use other optimized storage representations, and that is an implementation detail, not a Java type relationship.

## 4. `CharSequence`: a read contract for character sequences, with no immutability guarantee

`CharSequence` provides a common interface so libraries can accept text without forcing callers to create a `String` upfront. Core operations:

| API | Meaning |
| --- | --- |
| `length()` | Number of `char` (UTF-16) units in the sequence |
| `charAt(index)` | Reads one `char` unit at a 0-based index |
| `subSequence(start, end)` | Extracts the range `[start, end)`; return type is declared as `CharSequence` |
| `toString()` | Represents the sequence at call time as a `String` |
| `isEmpty()` | Checks `length() == 0` |
| `chars()` | `IntStream` of UTF-16 units |
| `codePoints()` | `IntStream` of Unicode code points, pairing valid surrogate pairs |

These methods support **reading**, but the interface does not guarantee that the underlying object is immutable. `String` is immutable; `StringBuilder` and `StringBuffer` are mutable; `CharBuffer` can reflect an underlying data array and position/limit state. `StringBuffer` synchronizes many individual methods, but that does not make the general `CharSequence` contract immutable or guarantee safety for all multi-threaded operation sequences.

For example:

```java
StringBuilder builder = new StringBuilder("Java");
CharSequence sequence = builder;
builder.append(" 17");
System.out.println(sequence); // Java 17
```

The `sequence` reference sees the change because both references point to the **same `StringBuilder` object**. Conversely, if you need to store an immutable snapshot of the content, you can convert it to a `String`, such as `String snapshot = builder.toString();`. You must define clearly when the snapshot is taken and avoid concurrent mutation while reading from a mutable source.

`char[]` does not implement `CharSequence`, so the snippet below is an **intentionally invalid type** example:

```java
char[] raw = {'H', 'i'};
// CharSequence cs = raw; // COMPILE ERROR: char[] does not implement CharSequence
CharSequence copied = new String(raw); // Immutable copy
```

If you need a view that reflects changes to the array, use `java.nio.CharBuffer.wrap(raw)`. This view is backed by the source array itself: modifying the array can be observed through the buffer, and the buffer's position/limit also affect `CharSequence.length()`, `charAt()`, and `subSequence()` when working with `CharBuffer`.

## 5. Complete example: copying, upcasting, and observing values

Save as `StringRelationsDemo.java`:

```java
public class StringRelationsDemo {
    public static void main(String[] args) {
        char[] source = {'J', 'a', 'v', 'a'};
        String text = new String(source);
        CharSequence sequence = text;
        Object asObject = text;

        source[0] = 'K';
        System.out.println(text);
        System.out.println(new String(source));
        System.out.println(sequence.length());
        System.out.println(sequence.charAt(1));
        System.out.println(sequence.subSequence(1, 3));
        System.out.println(asObject instanceof String);

        char[] snapshot = text.toCharArray();
        snapshot[0] = 'X';
        System.out.println(text);

        Object arrayAsObject = source;
        System.out.println(arrayAsObject instanceof String);
        System.out.println(String.valueOf(source));
        System.out.println(
                String.valueOf((Object) source).startsWith("[C@"));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 StringRelationsDemo.java
java StringRelationsDemo
```

Expected output:

```text
Java
Kava
4
a
av
true
Java
false
Kava
true
```

Explanation:
- The first two lines show that `new String(source)` captured the initial content: changing the source array to `Kava` does not affect `text`.
- `sequence` still points to `String("Java")`, so `length()` is 4, `charAt(1)` is `a`, and `subSequence(1, 3)` is `av`.
- `asObject` holds an actual `String`, whereas `arrayAsObject` holds a `char[]` object; both are `Object`, yet the `instanceof String` results differ.
- `String.valueOf(source)` selects the overload taking `char[]`, so it returns the text `Kava`. Casting `source` to `Object` selects the `valueOf(Object)` overload: arrays use `Object.toString()`, whose format starts with `[C@` followed by an unstable identifier. Only check the prefix to avoid depending on the hash code.

## 6. Writing general APIs that accept `CharSequence`

A method that only needs to read characters can accept `CharSequence` to work with `String`, `StringBuilder`, or `CharBuffer`. The following example is a **standalone program**; save as `SequenceApiDemo.java`:

```java
import java.nio.CharBuffer;

public class SequenceApiDemo {
    static String prefix(CharSequence input, int count) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        int end = Math.min(count, input.length());
        return input.subSequence(0, end).toString();
    }

    public static void main(String[] args) {
        CharSequence immutable = "Hello";
        StringBuilder builder = new StringBuilder("Builder");
        char[] raw = {'C', 'h', 'a', 'r'};
        CharSequence view = CharBuffer.wrap(raw);

        System.out.println(prefix(immutable, 2));
        System.out.println(prefix(builder, 3));
        System.out.println(prefix(view, 2));

        builder.append("!");
        raw[0] = 'X';
        System.out.println(builder);
        System.out.println(view);
    }
}
```

```bash
javac -encoding UTF-8 SequenceApiDemo.java
java SequenceApiDemo
```

```text
He
Bui
Ch
Builder!
Xhar
```

Here `prefix` uses the common `CharSequence` contract; the returned result is a `String`. `CharBuffer.wrap(raw)` **does not create a copy**, so the last line sees the newly modified `X` character. If you need to freeze the input at a point in time, create a `String` from the content before storing it; if consistency is required while multiple threads concurrently modify the source, external synchronization must be coordinated.

### When should you accept `String`, and when should you accept `CharSequence`?

- Use `String` when an API needs an immutable string for long-term storage, as a map key, for comparison by `String` rules, or needs methods only available on `String` such as `replace`, `split`, or `matches`.
- Use `CharSequence` when an algorithm only needs to read `length`, `charAt`, `subSequence`, or character streams and wants to accept multiple representations. API documentation should clearly state whether the function retains the input reference after returning.
- Use `char[]` when you genuinely need in-place manipulation of `char` elements, interoperate with an API that accepts arrays, or actively manage copies. Do not assume arrays are faster by default: performance depends on the operations and allocation patterns.
- Use `StringBuilder` to build text that changes repeatedly within the same context; call `toString()` when an immutable result is needed.

## 7. `Object`, `toString()`, overloads, and comparison types

Because `String` is an `Object`, `Object ref = "Java";` is valid; however, the **static type** of the reference determines which methods can be called directly. `Object.toString()` is a polymorphic method: `String.toString()` returns the string's content; `StringBuilder.toString()` returns a string representing the content at call time. A `char[]` array does not override `Object.toString()` to print the characters a reader expects.

Overloads that are easy to confuse:

```java
char[] data = {'O', 'K'};
System.out.println(String.valueOf(data));          // OK
System.out.println(String.valueOf((Object) data)); // format [C@..., not "OK"
System.out.println(data);                          // OK, due to println(char[])
System.out.println((Object) data);                 // format [C@..., due to println(Object)
```

The snippet above is an **overload explanation snippet**, not a separate class with `main`. Do not compare the entire `[C@...` format against a fixed string: the part after `@` depends on the object/program run.

Type relationships do not determine how content is compared:

| Expression | Checks | Recommendation |
| --- | --- | --- |
| `a == b` with two references | Whether they are the same object | Use when identity matters |
| `stringA.equals(stringB)` | Content of two `String`s | Use for string equality |
| `Arrays.equals(charArrayA, charArrayB)` | Each element of two arrays | Use for array equality |
| `charArrayA.equals(charArrayB)` | Array identity (inherited from `Object`) | Do not use to compare content |
| `string.contentEquals(sequence)` | `String` content against a `CharSequence` | Use when comparing across different implementation classes |

`CharSequence` **does not redefine `Object`'s `equals`/`hashCode` contract**. Therefore, do not assume two `CharSequence` instances with identical content will be `equals` to each other, especially when they belong to different classes. A `HashSet<CharSequence>` or `Map<CharSequence, ...>` is only appropriate when you have deliberately chosen and controlled key equality and immutability rules. For text keys, `String` is usually safer and more predictable.

Standalone example, save as `EqualityDemo.java`:

```java
import java.util.Arrays;

public class EqualityDemo {
    public static void main(String[] args) {
        String a = new String(new char[] {'h', 'i'});
        String b = new String(new char[] {'h', 'i'});
        char[] x = {'h', 'i'};
        char[] y = {'h', 'i'};
        CharSequence builder = new StringBuilder("hi");

        System.out.println(a.equals(b));
        System.out.println(a == b);
        System.out.println(Arrays.equals(x, y));
        System.out.println(x.equals(y));
        System.out.println(a.equals(builder));
        System.out.println(a.contentEquals(builder));
    }
}
```

```bash
javac -encoding UTF-8 EqualityDemo.java
java EqualityDemo
```

```text
true
false
true
false
false
true
```

`a` and `b` have equal content but are two separately created `String` objects. The two arrays `x` and `y` are equal in elements but do not point to the same array. `a.equals(builder)` is `false` because the argument is not a `String`, whereas `contentEquals` compares the characters and returns `true`. For `String` literals, the JVM may use the string pool; thus, do not use `"hi" == "hi"` to infer general content-comparison rules.

## 8. Unicode: `char`, Unicode characters, and string length do not always match

Java's `char` is 16 bits wide, representing one **UTF-16 code unit**. A Unicode code point outside the Basic Multilingual Plane (BMP) requires **two** `char` values (a surrogate pair). Consequently:
- `String.length()`, `CharSequence.length()`, and `char[]` array length all count **UTF-16 units** in their respective sequences, not necessarily the number of Unicode code points or characters perceived by a reader.
- `charAt(i)` returns one UTF-16 unit; it may be half of a surrogate pair.
- `codePointCount`, `codePointAt`, `offsetByCodePoints`, and `codePoints()` are useful when processing by code point. A *grapheme cluster* (visible character) can still consist of multiple code points, so counting code points is not synonymous with counting user-perceived characters.

Standalone example, save as `UnicodeDemo.java` (UTF-8 encoded file):

```java
public class UnicodeDemo {
    public static void main(String[] args) {
        String value = "A🙂B";
        System.out.println(value.length());
        System.out.println(value.toCharArray().length);
        System.out.println(value.codePointCount(0, value.length()));
        System.out.println(value.codePoints().count());
        System.out.println(value.offsetByCodePoints(0, 2));
    }
}
```

```bash
javac -encoding UTF-8 UnicodeDemo.java
java UnicodeDemo
```

```text
4
4
3
3
3
```

The string consists of `A` (one `char`), the emoji `🙂` (two `char`s), and `B` (one `char`): four UTF-16 units in total, but three code points. The UTF-16 index immediately after the first two code points is 3. If you slice with `substring`/`subSequence` between the two halves of a surrogate pair, you can produce an invalid UTF-16 sequence; when processing code points, compute boundaries using `offsetByCodePoints` or an appropriate Unicode API.

## 9. Common mistakes and how to handle them

1. **Assuming `char[]` is a `CharSequence`:** direct casting does not create an adapter; use `new String(array)` to copy or `CharBuffer.wrap(array)` when intentionally sharing the array.
2. **Using `==` or `char[].equals` to compare content:** choose `String.equals`, `Arrays.equals`, or `String.contentEquals` depending on the data types and desired rules.
3. **Believing every `CharSequence` is immutable:** check the implementing class and reference retention. `StringBuilder`/`CharBuffer` can change content while being read.
4. **Printing an array via `Object.toString()` and thinking it is text:** `String.valueOf((Object) array)` does not select the `char[]` overload; use `new String(array)` or `String.valueOf(array)`.
5. **Confusing `array.length` with `string.length()`:** arrays use a field, while `String`/`CharSequence` use a method.
6. **Casting `Object` to `String` when it actually holds an array:** check with `instanceof` and handle by type; casting is different from converting.
7. **Treating `charAt` as a complete Unicode character:** for characters outside the BMP, work with code points or grapheme clusters as required.
8. **Using `String` to assemble many pieces in a large loop:** `String` is immutable, so repeated concatenation can create many intermediate objects; `StringBuilder` is usually appropriate when accumulating text.
9. **Using a mutable `CharSequence` as a map/set key:** mutating content or differing `equals`/`hashCode` across implementing classes can cause unpredictable results; typically normalize to `String` when choosing text keys.
10. **Assuming a `char[]` holding secrets can wipe every copy:** you can overwrite an array you own, but Java/JVM/APIs may create copies elsewhere. Do not promise guaranteed erasure from all of memory with a single `Arrays.fill`.

## 10. Quick selection rules and self-check

Define your requirements before choosing a type:

- **Need a stable text value:** use `String`.
- **Need a read-only parameter accepting multiple text sources:** use `CharSequence`; clearly decide whether the data is snapshotted into a `String` when stored.
- **Need to modify individual UTF-16 elements:** use `char[]` or an appropriate buffer.
- **Need continuous building/appending:** use `StringBuilder`, then obtain a `String` when finished.
- **Only have an `Object` reference:** check the actual type and convert intentionally; do not expect every type's `Object.toString()` to return text content.

Review questions:
1. Why does changing `charArray[0]` after `new String(charArray)` not change the `String`, whereas with `CharBuffer.wrap(charArray)` the change can be observed?
2. Why is `CharSequence s = new StringBuilder("x");` valid, while `CharSequence s = new char[] {'x'};` is invalid?
3. At which overload-resolution step does `String.valueOf(array)` differ from `String.valueOf((Object) array)`?
4. Why can `string.equals(builder)` and `string.contentEquals(builder)` return different results?
5. When `text.length() == 4`, can you conclude the string has exactly four Unicode code points or four visible characters? Why?

Mastering **type relationships**, **immutability/copying**, the **`CharSequence` contract**, and **UTF-16 units** will help you design proper APIs, avoid casting/comparison bugs, and choose the right data structures.

## Official API Documentation (Java SE 17)

- [`String` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`CharSequence` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
- [`CharBuffer` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/CharBuffer.html)
- [`Arrays` — Oracle Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)