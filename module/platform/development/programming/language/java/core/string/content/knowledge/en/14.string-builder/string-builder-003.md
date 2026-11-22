# `StringBuilder.append` with `String`, primitives, `Object`, `char[]`, and `CharSequence`

In Java, `StringBuilder` builds text by **appending data to the current object itself**. The `append(...)` method family has multiple overloads to directly accept `String`, primitive types, `Object`, `char[]` arrays, and `CharSequence`. On the surface, every call "appends", but **the argument type determines which overload is selected**, and that overload determines how the data is converted into characters.

Quick example:

```java
StringBuilder out = new StringBuilder();
out.append("id=").append(42).append(", active=").append(true);
System.out.println(out); // id=42, active=true
```

There is no need to repeatedly create intermediate `String` objects for each concatenation step. However, to use `append` correctly, you must understand the difference between **adding text content**, **converting a value to text**, and **adding the elements of a character array**.

## 1. `append` Modifies the Builder Itself and Returns `this`

With `String`, a concatenation such as `text = text + suffix` produces a new `String` value and reassigns the variable `text`, because `String` is immutable. By contrast, `StringBuilder.append(...)` appends to the content of the existing builder.

```java
StringBuilder builder = new StringBuilder("A");
StringBuilder sameReference = builder;

StringBuilder returned = builder.append("B");

System.out.println(builder);                  // AB
System.out.println(sameReference);            // AB
System.out.println(returned == builder);      // true
```

`append` returns **the builder itself**, so multiple calls can be chained:

```java
new StringBuilder().append("x=").append(10).append(", y=").append(20)
```

This is an illustrative expression: if you want the resulting `String`, call `toString()` at the end. There is no need to reassign `builder = builder.append(...)` because the builder is modified in place, though that assignment is still valid.

**Distinguishing `length` and `capacity`:** `length()` is the current number of UTF-16 code units; `capacity()` is the buffer capacity reserved for code units before expansion is needed. Repeated `append` calls can increase `length` and grow `capacity` when necessary. `capacity` is not a fixed character limit on the builder.

### Example 1: Appending multiple types in one program

Create the file `AppendOverviewDemo.java`:

```java
public class AppendOverviewDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("User ");
        StringBuilder alias = builder;

        builder.append("An")
               .append(" | age=")
               .append(21)
               .append(" | active=")
               .append(true)
               .append(" | grade=")
               .append('A');

        System.out.println(builder);
        System.out.println(alias);
        System.out.println(builder == alias);
        System.out.println(builder.length());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 AppendOverviewDemo.java
java AppendOverviewDemo
```

Output:

```text
User An | age=21 | active=true | grade=A
User An | age=21 | active=true | grade=A
true
40
```

Both variables still point to **one mutable object** after `append`. Data is added in the exact order of calls, with no automatic spaces or delimiters inserted unless you provide them yourself.

## 2. `append(String)`: Appending the Characters of a String

The `append(String str)` overload appends the characters of `str` to the end of the builder. If the argument is a `String`, this overload is usually the most direct choice.

```java
String prefix = "Hello";
StringBuilder sb = new StringBuilder();
sb.append(prefix);
sb.append(", Java");
```

The result is `"Hello, Java"`. Neither source `String` object is modified; the builder copies the content to be added into its own storage area.

### `null` in the `String` Overload

According to the `StringBuilder.append(String)` contract, a `null` `String` reference is appended as the four characters `"null"`. It **does not skip** the value and does not automatically throw an error:

```java
String missing = null;
StringBuilder sb = new StringBuilder("value=");
sb.append(missing);
// Content: "value=null"
```

If business requirements treat `null` as an empty string or want nothing added, you must **handle it explicitly before calling**. For example:

```java
if (missing != null) {
    sb.append(missing);
}
```

The two snippets above are illustrative code that can be placed inside a method. Do not rely on the `"null"` behavior to build a data protocol unless it is an explicitly defined convention.

## 3. `append` with Primitives: Values Represented as Text

`StringBuilder` provides overloads for common primitive types:

| Argument Type | Typical Overload | Example Added to Builder |
| --- | --- | --- |
| `boolean` | `append(boolean)` | `true` → `"true"`; `false` → `"false"` |
| `char` | `append(char)` | `'A'` → `"A"` |
| `int` | `append(int)` | `42` → `"42"` |
| `long` | `append(long)` | `42L` → `"42"` |
| `float` | `append(float)` | `1.5f` → `"1.5"` |
| `double` | `append(double)` | `2.25` → `"2.25"` |

`byte` and `short` do not have dedicated overloads; they undergo **numeric promotion** to `int`, so their values are typically appended in decimal numeric representation.

A key detail to remember: `char` represents a **character unit**, whereas `int` represents an **integer**. `append('A')` differs from `append(65)`:

```java
new StringBuilder().append('A') // "A"
new StringBuilder().append(65)  // "65"
```

Even though `'A'` has Unicode numeric value 65, the overload is chosen by **compile-time type**, not by the author's implicit intent.

### Example 2: Primitives, types, and expressions

Create the file `PrimitiveAppendDemo.java`:

```java
public class PrimitiveAppendDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder();
        first.append(65).append('|')
             .append('A').append('|')
             .append(true).append('|')
             .append(12L).append('|')
             .append(1.5f).append('|')
             .append(2.25d);

        System.out.println(first);

        StringBuilder second = new StringBuilder();
        second.append(1 + 2).append('|');
        second.append(1).append(2);

        System.out.println(second);

        byte small = 7;
        short another = 8;
        System.out.println(new StringBuilder().append(small).append(',').append(another));
    }
}
```

```bash
javac -encoding UTF-8 PrimitiveAppendDemo.java
java PrimitiveAppendDemo
```

Output:

```text
65|A|true|12|1.5|2.25
3|12
7,8
```

In `append(1 + 2)`, the arithmetic `1 + 2` is evaluated **before the call**, and then `append(int)` appends `3`. Conversely, `append(1).append(2)` is two consecutive calls that append `"1"` and `"2"`, producing `"12"`. Overloads do not guess whether you want to add numbers or concatenate text.

Default number formatting is suitable for representing values, though it does not always satisfy reporting requirements: for example, displaying exactly two decimal places or locale-specific separators requires dedicated formatting such as `Formatter` or `String.format(Locale, ...)`. When appending directly, do not assume `append(double)` produces currency formatting or localized number formatting.

## 4. `append(Object)`: Converting an Object to a String via `String.valueOf`

The `append(Object obj)` overload obtains the string representation corresponding to `String.valueOf(obj)`:

- If `obj == null`, `"null"` is appended.
- If `obj != null`, `String.valueOf(obj)` relies on `obj.toString()`.
- If the object's class overrides `toString()`, the text appended to the builder is the representation provided by the class.
- If not overridden, `Object.toString()` typically produces a class name with identity information; that is **not** a structured representation suitable for all business needs.

When you want to include a custom object in a log line or descriptive string, provide a clear `toString()` if that is truly its intended use. However, `toString()` is not a standard serialization API for data that needs round-tripping.

### Example 3: An object with its own `toString()`

Create the file `ObjectAppendDemo.java`:

```java
public class ObjectAppendDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public String toString() {
            return "(" + x + "," + y + ")";
        }
    }

    public static void main(String[] args) {
        Point point = new Point(3, 4);
        Object asObject = point;

        StringBuilder builder = new StringBuilder("position=");
        builder.append(asObject).append("; missing=");
        builder.append((Object) null);

        System.out.println(builder);
        System.out.println(new StringBuilder().append((Object) "hello"));
    }
}
```

```bash
javac -encoding UTF-8 ObjectAppendDemo.java
java ObjectAppendDemo
```

Output:

```text
position=(3,4); missing=null
hello
```

The variable `asObject` is declared as `Object`, so the `append(Object)` overload is selected; `Point.toString()` is actually invoked at runtime via polymorphism. The last line casts `String` to `Object`, yet the output is still `hello` because `String.toString()` returns the exact content of the string.

**Note:** `append(Object)` **does not automatically iterate and append the elements of arbitrary arrays**. Specifically, character arrays have their own overload (`append(char[])`), while a variable cast to `Object` goes through the `Object` path. This is why you must understand the difference between **declared type** and **runtime value**.

## 5. `append(char[])`: Appending Character Array Content, Not the Array Name

`char[]` is an important argument type because `StringBuilder` has dedicated overloads:

```java
append(char[] str)
append(char[] str, int offset, int len)
```

- `append(char[])` appends **each code unit** in the array into the builder in order.
- `append(char[], offset, len)` appends **`len` elements** starting from `offset`.
- `offset` is the starting position **included in the slice**; `len` is the **number of elements**, **not the end index**.
- If the array is `null`, the `char[]` overloads throw `NullPointerException`.
- If the array range is invalid, the range overload throws `IndexOutOfBoundsException` or an appropriate subclass.

This differs from `append(String)` or `append(Object)`, which accept null and append `"null"`. Therefore, `append(null)` **does not have a single behavior**: the null literal has no specific type and causes **overload ambiguity** at compile time. To select one overload, use a typed variable or an explicit cast.

### Example 4: Entire array and a slice

Create `CharArrayAppendDemo.java`:

```java
public class CharArrayAppendDemo {
    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a', '!'};
        StringBuilder builder = new StringBuilder();

        builder.append(letters);
        builder.append(" | ");
        builder.append(letters, 1, 3);

        System.out.println(builder);

        letters[0] = 'X';
        System.out.println(builder);

        StringBuilder nullText = new StringBuilder();
        nullText.append((String) null).append('|')
                .append((Object) null).append('|')
                .append((CharSequence) null);
        System.out.println(nullText);

        try {
            new StringBuilder().append((char[]) null);
        } catch (NullPointerException exception) {
            System.out.println("char[] is null");
        }
    }
}
```

```bash
javac -encoding UTF-8 CharArrayAppendDemo.java
java CharArrayAppendDemo
```

Output:

```text
Java! | ava
Java! | ava
null|null|null
char[] is null
```

`append(letters, 1, 3)` takes the elements at indices 1, 2, 3, producing `"ava"`. Afterwards, changing `letters[0]` to `'X'` **does not change the text already appended** to the builder: the appended code units were copied into the builder's content.

If you want to append only part of an array, do not confuse the `(offset, len)` signature with `substring(start, end)` or `CharSequence.subSequence(start, end)`: the latter APIs use an **exclusive** end position, whereas for `char[]` the last parameter is the **slice length**.

### What happens if a character array goes through the `Object` overload?

Consider:

```java
char[] letters = {'O', 'K'};
StringBuilder first = new StringBuilder().append(letters);
StringBuilder second = new StringBuilder().append((Object) letters);
```

`first` has content `"OK"`. `second` **does not** have content `"OK"`; it uses the character array's `Object.toString()`, which typically looks like `[C@...` with a non-fixed identity suffix. Do not hardcode the specific output of `second` because the identifier part depends on the object/runtime.

This is an overload case demonstrating that the same **runtime `char[]` object** with different argument types at the call site leads to different behavior. `int[]` or `Object[]` arrays are also not automatically traversed by `append(Object)`; if you need to join array elements, choose an explicit formatting approach, such as `Arrays.toString(...)` when appropriate.

## 6. `append(CharSequence)`: Programming Against the Character-Sequence Interface

`CharSequence` represents a readable sequence of characters with `length()` and `charAt(...)`. `String`, `StringBuilder`, `StringBuffer`, and `CharBuffer` are common implementations.

`StringBuilder` provides the overloads:

```java
append(CharSequence s)
append(CharSequence s, int start, int end)
```

Meaning:

- `append(CharSequence s)` appends all current characters of sequence `s`.
- `append(s, start, end)` appends a slice over the **half-open index range `[start, end)`**. The `end` parameter is an **exclusive** position, unlike the `len` parameter of `append(char[], offset, len)`.
- The valid range is `0 <= start <= end <= s.length()` for non-null `s`.
- When `s == null`, the `CharSequence` overload contract specifies treating the source as the character sequence `"null"`. To avoid ambiguity, define your application's null policy instead of relying on the default behavior.
- `CharSequence` does not guarantee that the source object is immutable; mutable implementations can change content between different reads.

The interface contract allows you to write code that accepts many input types. However, **once `append` completes**, the appended content becomes part of the target builder's data; the target builder **does not become a live view** where later changes to the source automatically update previously appended text.

### Example 5: `String`, `StringBuilder`, and `CharBuffer`

Create `CharSequenceAppendDemo.java`:

```java
import java.nio.CharBuffer;

public class CharSequenceAppendDemo {
    public static void main(String[] args) {
        CharSequence word = "abcdef";
        CharSequence mutable = new StringBuilder("XYZ123");
        CharSequence buffer = CharBuffer.wrap("hello");

        StringBuilder result = new StringBuilder();
        result.append(word, 1, 4).append('|')
              .append(mutable, 0, 3).append('|')
              .append(buffer, 1, 4);

        System.out.println(result);

        StringBuilder source = new StringBuilder("cat");
        StringBuilder target = new StringBuilder().append((CharSequence) source);
        source.setCharAt(0, 'B');

        System.out.println(source);
        System.out.println(target);

        CharSequence missing = null;
        System.out.println(new StringBuilder().append(missing));
    }
}
```

```bash
javac -encoding UTF-8 CharSequenceAppendDemo.java
java CharSequenceAppendDemo
```

Output:

```text
bcd|XYZ|ell
Bat
cat
null
```

The call `result.append(word, 1, 4)` takes indices 1, 2, 3, producing `"bcd"`. For `mutable`, `[0,3)` produces `"XYZ"`; for `buffer`, `[1,4)` produces `"ell"`.

`target` retains `"cat"` even though `source` became `"Bat"` because `append` wrote the content into the target builder. If the source can be modified **concurrently** by another thread, appropriate synchronization must be used to ensure a consistent snapshot: `StringBuilder` does not guarantee thread-safety on its own.

### The null case with a `CharSequence` slice

By the `append(CharSequence, int, int)` contract, a `null` source is treated as the sequence `"null"` before taking the slice. Thus `append((CharSequence) null, 1, 3)` can append `"ul"`. Although valid, writing code that relies on this implicit null handling is usually less clear than choosing a default value or checking `null` beforehand.

## 7. Overload Resolution: The **Expression Type** Chooses the Method

Java selects the most specific applicable overload at **compile time**, based on the expression type at the call site. Just because a runtime value is a `String` does not mean `append(String)` is always called.

```java
String text = "hello";
Object object = text;
CharSequence sequence = text;

new StringBuilder().append(text);      // append(String)
new StringBuilder().append(object);    // append(Object)
new StringBuilder().append(sequence);  // append(CharSequence)
```

All three produce `hello` in this example, but the **conversion path** and overload selection differ. The difference becomes much clearer with `char[]`, with `null`, and with classes that have custom `toString()`.

| Argument Expression | Relevant Overload | Result or Note |
| --- | --- | --- |
| `"abc"` | `String` | Appends `abc` |
| `(String) null` | `String` | Appends `null` |
| `42` | `int` | Appends `42` |
| `'A'` | `char` | Appends `A` |
| `(Object) null` | `Object` | Appends `null` |
| `new char[] {'O', 'K'}` | `char[]` | Appends `OK` |
| `(Object) new char[] {'O', 'K'}` | `Object` | Does not append `OK`; uses the array's `toString()` |
| `(CharSequence) "abc"` | `CharSequence` | Appends `abc` |
| `(CharSequence) null` | `CharSequence` | Appends `null` |
| `null` (uncast) | Ambiguous among multiple reference overloads | **Compile error** |

The reason `append(null)` is ambiguous is that overloads such as `append(String)` and `append(char[])` have no subtype–supertype relationship that lets the compiler choose a single most specific overload. Do not put this in a Java file meant to compile; treat it as an **intentionally invalid** line for illustration:

```java
// new StringBuilder().append(null); // Compile error: reference to append is ambiguous
```

Simply adding a cast changes the meaning of the call:

```java
new StringBuilder().append((String) null); // Valid, "null"
new StringBuilder().append((char[]) null); // Throws NullPointerException
```

Therefore, during code review, pay attention to the **declared types** and casts of variables used as arguments. Do not look only at the runtime value.

## 8. Interaction with `char`, Unicode, and Code Points

`append(char)` appends **one UTF-16 code unit**. A Unicode code point outside the Basic Multilingual Plane (BMP), such as U+1F600, requires **two code units** (a surrogate pair). If you append only a single surrogate `char`, you have not appended the full code point.

When you need to append a Unicode code point stored in an `int` variable, `StringBuilder.appendCodePoint(int)` is the right API rather than `append(int)`:

```java
StringBuilder a = new StringBuilder().append(0x1F600);         // "128522"
StringBuilder b = new StringBuilder().appendCodePoint(0x1F600); // U+1F600
```

`append(int)` converts a **numeric value** to decimal digits; `appendCodePoint(int)` converts a **Unicode code point** into the corresponding UTF-16 units. The two methods serve different purposes and must not be swapped.

### Example 6: Code point count differs from code unit count

Create `UnicodeAppendDemo.java`:

```java
public class UnicodeAppendDemo {
    public static void main(String[] args) {
        int smile = 0x1F600;
        StringBuilder numeric = new StringBuilder().append(smile);
        StringBuilder actual = new StringBuilder().appendCodePoint(smile);

        System.out.println(numeric);
        System.out.println(numeric.length());
        System.out.println(actual.length());
        System.out.println(actual.codePointCount(0, actual.length()));
        System.out.println(actual.toString().codePointAt(0) == smile);
    }
}
```

```bash
javac -encoding UTF-8 UnicodeAppendDemo.java
java UnicodeAppendDemo
```

Output:

```text
128522
6
2
1
true
```

If you have a `String` containing an emoji and call `append(String)` or `append(CharSequence)`, the API appends the code units of that string. With `char[]`, you must also ensure the array contains the complete surrogate pair if representing a non-BMP code point. `StringBuilder` does not automatically turn every lone `char` unit into a complete Unicode character.

## 9. Choosing the Right Overload in API Design

A useful rule of thumb:

- **Already have a `String`:** use `append(String)` directly.
- **Appending numeric or boolean data:** use the primitive overloads to clearly express the value and avoid unnecessary conversions.
- **Already have a `char[]` array:** use the `char[]` overload if you want to append **the character content of the array**; use `offset` and `len` when you only need a slice.
- **Data described by `CharSequence`:** use the `CharSequence` overload; the `[start,end)` range is convenient for slicing general character sequences.
- **Have a domain object:** use `append(Object)` when you truly want its `toString()` representation. If it is interchange data or a format that must remain stable, create a dedicated formatter.
- **Appending one code point at a time from an `int` variable:** consider `appendCodePoint`, because `append(int)` writes digits.
- **Possible `null`:** define a clear policy so you do not accidentally produce `"null"` text or throw an array exception.

When building a string across multiple steps, the `append` syntax helps readers see the assembly order and avoids writing many intermediate `String` expressions. However, not every concatenation needs a builder: for short concatenations, `+` is often easier to read and modern compilers/JVMs can optimize it. Choose based on clarity and actual need, not an absolute rule.

### Example 7: Building a complete record line

Create the file `AppendRecordDemo.java`:

```java
public class AppendRecordDemo {
    static String render(String id, int quantity, boolean active, char[] token) {
        StringBuilder builder = new StringBuilder();
        builder.append("id=").append(id)
               .append("; qty=").append(quantity)
               .append("; active=").append(active)
               .append("; token=").append(token, 0, token.length);
        return builder.toString();
    }

    public static void main(String[] args) {
        char[] token = {'A', 'B', 'C'};
        String rendered = render("p-1", 3, true, token);

        System.out.println(rendered);
        token[0] = 'Z';
        System.out.println(rendered);
    }
}
```

```bash
javac -encoding UTF-8 AppendRecordDemo.java
java AppendRecordDemo
```

Output:

```text
id=p-1; qty=3; active=true; token=ABC
id=p-1; qty=3; active=true; token=ABC
```

The `char[]` data is appended to the builder and then `toString()` returns an immutable `String`. Modifying the original array afterward does not change the `rendered` string.

**Example limitation:** the method assumes `token` is non-null. In a real application, if null is possible, you must add a null check or define a fallback value before accessing `token.length`.

## 10. Common Pitfalls

**Pitfall 1 — thinking all overloads behave identically.** For `String`, `Object`, `char[]`, and `CharSequence`, results may look identical in normal cases yet differ sharply when encountering arrays, null, or general argument types.

**Pitfall 2 — thinking `append(Object)` appends the elements of every array.** It uses `String.valueOf(Object)` and may call the array's `Object.toString()`. For `char[]`, only the dedicated overload appends the element contents as expected.

**Pitfall 3 — writing `append(null)` and assuming it appends `"null"`.** The call has overload ambiguity; a cast or typed reference is required. Once a type is chosen, null `String`/`Object`/`CharSequence` appends `"null"`, whereas null `char[]` throws `NullPointerException`.

**Pitfall 4 — using `append(65)` to append `'A'`.** The integer 65 is formatted as `"65"`. To get `A`, use `append('A')` or an appropriate Unicode API.

**Pitfall 5 — thinking `append(char[], offset, len)` takes an end index.** `len` is the element count; for example, `offset=1, len=3` takes positions 1, 2, 3.

**Pitfall 6 — applying array rules to `CharSequence`.** `append(sequence, start, end)` uses the range **[start, end)**, meaning `end` is an exclusive position, not an element count.

**Pitfall 7 — thinking a builder creates a new string without mutating the old object.** `append` mutates the `StringBuilder` itself and returns that same builder. Every reference holding the builder sees the new content.

**Pitfall 8 — thinking the builder remains linked to the array or `CharSequence` source.** Once `append` completes, the text is written into the target builder; modifying the source later does not automatically update the appended characters.

**Pitfall 9 — using `append(Object)` as a serialization standard.** `toString()` can change across implementations and provides neither a schema nor escaping. Storage/interchange formats require an explicit contract.

**Pitfall 10 — ignoring Unicode.** `char` is a UTF-16 code unit, not every Unicode code point; `append(int)` appends a number, unlike `appendCodePoint(int)`.

**Pitfall 11 — assuming a builder is thread-safe by default.** `StringBuilder` does not synchronize all operations for safe concurrent sharing across threads; if shared concurrent mutation is needed, design an appropriate synchronization mechanism. Using `StringBuffer` synchronizes individual operations, though multi-step workflows still need review.

## 11. Practice Exercises

### Question 1: Primitive types

```java
StringBuilder b = new StringBuilder();
b.append(7).append('7').append(true);
System.out.println(b);
```

Output:

```text
77true
```

First it appends the digit `7` from `int`, second it appends the character `'7'`, and third it appends `true`. There is no automatic delimiter.

### Question 2: Difference between `char[]` and `Object`

Given `char[] data = {'H', 'i'};`, what is the content after `append(data)`? **`Hi`**, because the `char[]` overload is selected.

What about `append((Object) data)`? **Not guaranteed to be `Hi`**, because it uses the array object's `toString()` representation; the identity suffix should not be guessed in tests.

### Question 3: `offset, len` vs. `start, end`

```java
char[] a = {'a', 'b', 'c', 'd', 'e'};
CharSequence s = "abcde";

System.out.println(new StringBuilder().append(a, 1, 3));
System.out.println(new StringBuilder().append(s, 1, 3));
```

Output:

```text
bcd
bc
```

For the array: takes **3 elements** starting at position 1. For `CharSequence`: takes positions from 1 up to before 3, so only **2 characters**.

### Question 4: null

Predict:

```java
System.out.println(new StringBuilder().append((String) null));
System.out.println(new StringBuilder().append((CharSequence) null));
```

Output:

```text
null
null
```

However, if changed to `append((char[]) null)`, the program throws `NullPointerException`; if you remove the cast and write `append(null)`, the error occurs at **compile time** due to overload ambiguity.

### Question 5: Another mutable object vs. already-appended content

```java
StringBuilder source = new StringBuilder("one");
StringBuilder target = new StringBuilder();
target.append((CharSequence) source);
source.append(" two");
System.out.println(target);
System.out.println(source);
```

Output:

```text
one
one two
```

The `source` object is mutable, yet `target` is not a view of `source`. It retains the characters that had been appended at the time the call completed.

## Conclusion

**`StringBuilder.append(...)` has one general goal — adding data to the end of a builder — but overload selection determines what the argument means.** `String` and `CharSequence` provide text content; primitives are represented as characters; `Object` relies on `String.valueOf`/`toString()`; `char[]` is appended code unit by code unit and has a slice overload using `offset, len`. Pay attention to compile-time expression types, handle `null` explicitly, distinguish the `[start,end)` range from `offset,len`, and remember that `append` **mutates the `StringBuilder` itself, not the source that was appended**.
