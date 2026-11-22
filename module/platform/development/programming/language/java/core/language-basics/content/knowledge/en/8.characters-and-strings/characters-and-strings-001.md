# Distinguishing `char`, `String`, and `char` Arrays in Java 17+

## 1. Three ways to represent characters: not interchangeable at will

Java has three common forms when working with text:

- **`char`**: a 16-bit primitive value representing **one UTF-16 code unit**. Written as a literal with single quotes, for example `'A'`.
- **`String`**: an **immutable** character sequence object representing a sequence of UTF-16 code units. Written as a literal with double quotes, for example `"Java"`.
- **`char[]`**: a **fixed-length array** consisting of `char` elements, whose elements can be modified via assignment.

~~~java
char initial = 'J';
String word = "Java";
char[] letters = {'J', 'a', 'v', 'a'};
~~~

These three variables differ in **type**, **access syntax**, **mutability**, and **copy semantics**.

| Property | `char` | `String` | `char[]` |
|---|---|---|---|
| Category | Primitive | Class `java.lang.String` | Array object |
| Content | One UTF-16 code unit | Sequence of UTF-16 code units | `char` elements |
| Example initialization | `'J'` | `"Java"` | `{'J','a','v','a'}` |
| Getting length | No length property | `word.length()` | `letters.length` |
| Accessing by position | No index | `word.charAt(i)` | `letters[i]` |
| Modifying content at index | Not applicable | **Cannot** modify in place | `letters[i] = 'K'` |
| `null` value | Cannot hold `null` | Can be `null` | Can be `null` |

**Remember:** `String` is **not** just another syntax for `char[]`; they are two different object types with different APIs and mutability.

## 2. `char`: one UTF-16 code unit, not necessarily a visible character

`char` uses single quotes:

~~~java
char letter = 'A';
char digit = '5';
char newline = '\n';
char backslash = '\\';

System.out.println(letter);           // A
System.out.println((int) digit);      // 53: UTF-16 code of '5'
System.out.println((int) newline);    // 10: LF
~~~

`'5'` is the **digit character**, not the integer `5`. Casting `char` to `int` gives the numeric value of that code unit:

~~~java
char value = 'A';
int codeUnit = value;
System.out.println(codeUnit); // 65
~~~

Java `char` has a value range from 0 to 65535 (`Character.MIN_VALUE` to `Character.MAX_VALUE`). That is the **UTF-16 code unit value**, not the entire Unicode code point range.

Unicode characters outside the **Basic Multilingual Plane** (BMP), such as emoji, are typically represented by a **surrogate pair** consisting of two `char`s. Therefore:

- One Unicode code point may require **two `char`s**.
- A visible character such as an accented character sequence or emoji may consist of **multiple code points**.
- You should not assume `char` = one user-visible character.

### Common syntax mistakes

~~~java
// char empty = '';    // Invalid: empty char literal
// char two = 'AB';    // Invalid: two regular characters
// char text = "A";    // Type mismatch: String does not automatically become char
// char missing = null; // Invalid: null cannot be assigned to primitive char
~~~

When you need a single letter from a string, use `charAt(index)` and check that the string is non-empty and the index is valid.

## 3. `String`: immutable sequence with a text-processing API

`String` is a **reference type** in `java.lang`:

~~~java
String label = "Java";
System.out.println(label.length());  // 4
System.out.println(label.charAt(0)); // J
System.out.println(label.substring(1, 3)); // av
~~~

Methods such as `replace`, `toUpperCase`, `concat`, or `substring` **do not modify the content of the old String object**. They return the appropriate string result, which may be the same instance or a different instance according to the API contract; the key point is that **the original string value remains unchanged**.

~~~java
String title = "Java";
String modified = title.replace('J', 'L');

System.out.println(title);    // Java
System.out.println(modified); // Lava
~~~

If you want the variable `title` to hold the new result, you **reassign the variable**:

~~~java
title = title.replace('J', 'L');
System.out.println(title); // Lava
~~~

Here the reference variable is assigned a different reference value; the original `String` object is not modified.

A `String` can hold `null` if there is no data yet (when you assign `null` to the variable); however, `null` is not the empty string `""`. Be sure to distinguish them:

~~~java
String missing = null;
String empty = "";
System.out.println(empty.length()); // 0
// missing.length(); // If executed: NullPointerException
~~~

## 4. `char[]`: array with mutable individual elements

A `char` array has its size fixed at creation time and **cannot change length on the same array object**. However, its elements can be modified:

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
letters[0] = 'K';

System.out.println(new String(letters)); // Kava
System.out.println(letters.length);      // 4
~~~

For an empty array or an array initialized with a size:

~~~java
char[] buffer = new char[3];
System.out.println(buffer.length); // 3
System.out.println((int) buffer[0]); // 0: default value '\u0000'
~~~

An array is a **reference object**; an array variable can be reassigned to another array:

~~~java
char[] data = {'A'};
data = new char[] {'B', 'C'};
System.out.println(data.length); // 2
~~~

The statement above **does not extend the old array**; it replaces the reference value in the `data` variable to point to a different array.

### `length()` vs `length`

~~~java
String word = "cat";
char[] chars = {'c', 'a', 't'};

System.out.println(word.length()); // 3
System.out.println(chars.length);  // 3
~~~

`String.length()` is a method call; `char[].length` is the array's **length field**. Writing `chars.length()` or `word.length` will not compile.

## 5. Converting back and forth: `String` and `char[]`

The two most practical APIs:

~~~java
String word = "Java";
char[] chars = word.toCharArray(); // String -> char[]
String restored = new String(chars); // char[] -> String
~~~

These conversions are useful because they create separate data to process:

~~~java
String original = "Java";
char[] copy = original.toCharArray();
copy[0] = 'K';

System.out.println(new String(copy)); // Kava
System.out.println(original);         // Java
~~~

`toCharArray()` provides **a new array** containing the string's code units; modifying that array does not mutate the source `String`.

In the opposite direction, `new String(chars)` takes a **copy of the array's content** at the time the string is created:

~~~java
char[] buffer = {'A', 'B'};
String snapshot = new String(buffer);
buffer[0] = 'Z';

System.out.println(snapshot);          // AB
System.out.println(new String(buffer)); // ZB
~~~

**There is no automatic synchronization link between the array and the String.** After conversion, each side keeps its content according to the rules of its object type.

Other options:

- `String.valueOf(chars)` creates a `String` from a character array.
- `String.valueOf(oneChar)` creates a single-element string from a `char`.
- `String.valueOf(chars, offset, count)` selects a slice of the array, though valid bounds must be checked.
- `Character.toString(ch)` converts a `char` into a `String`.

~~~java
char initial = 'J';
String oneLetter = String.valueOf(initial);
System.out.println(oneLetter); // J
~~~

## 6. Comparing: string content and array content

With `String`, you normally use **`equals`** to compare content:

~~~java
String first = new String(new char[] {'o', 'k'});
String second = new String(new char[] {'o', 'k'});

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

`==` in the example checks **whether two references point to the same object**, not whether two strings have the same characters.

With `char[]`, **arrays do not compare elements by `equals`**. Use `java.util.Arrays.equals`:

~~~java
char[] a = {'o', 'k'};
char[] b = {'o', 'k'};

System.out.println(a == b);                 // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

To compare an array with a string, you can convert and call `equals`, or design the API to accept the same representation from the start:

~~~java
String expected = "ok";
char[] actual = {'o', 'k'};
System.out.println(expected.equals(new String(actual))); // true
~~~

**Note on sensitive data:** converting a `char[]` containing confidential information into a `String` can leave behind an immutable copy that is hard to clear from memory. When security is a requirement, avoid creating unnecessary copies; clearing an array only zeroes out that array itself and **does not guarantee wiping every copy of the data**.

## 7. How `char[]` prints and the overload trap

`PrintStream` has a `println(char[])` overload, so for example:

~~~java
char[] data = {'J', 'a', 'v', 'a'};
System.out.println(data);
~~~

will print:

~~~text
Java
~~~

This does **not** mean the array itself automatically turns into a String. For an array reference viewed as `Object`, overload selection and default representation may differ; you should not rely on an array's `toString()` to obtain text content.

When clarity is the goal, write:

~~~java
System.out.println(new String(data));          // Java
System.out.println(java.util.Arrays.toString(data)); // [J, a, v, a]
~~~

`Arrays.toString(char[])` is a list-of-elements representation for **debugging**, whereas `new String(data)` is **text content**.

## 8. Unicode boundaries when converting between String and char[]

Both `String.length()` and `char[].length` count **UTF-16 code units**, so a Unicode code point outside the BMP can occupy two `char`s. Converting `String` to `char[]` **does not automatically split into Unicode code points**:

~~~java
int emoji = 0x1F600; // U+1F600.
char[] twoUnits = Character.toChars(emoji);
String symbol = new String(twoUnits);

System.out.println(twoUnits.length); // 2
System.out.println(symbol.length()); // 2
System.out.println(symbol.codePointCount(0, symbol.length())); // 1
~~~

If you modify a single element of `twoUnits` on its own, you can break the **surrogate pair**. When the goal is processing code points, use `codePoints()` or `codePointAt` at valid UTF-16 boundaries; if the goal is user-perceived characters, a **grapheme cluster** can sometimes even consist of multiple code points. This lesson focuses on choosing between `char`, `String`, `char[]` and copy/mutability rules; surrogate positions, combining formulas, and safe slicing are verified in detail in the lesson on UTF-16.


## 9. Standalone Java 17 runnable program and expected output

Create the file **`CharStringArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class CharStringArrayDemo {
    private CharStringArrayDemo() {}

    public static void main(String[] args) {
        char initial = 'J';
        String word = "Java";
        char[] letters = {'J', 'a', 'v', 'a'};

        System.out.println("char: " + initial);
        System.out.println("string: " + word);
        System.out.println("array: " + new String(letters));
        System.out.println("lengths: " + word.length()
                + " / " + letters.length);
        System.out.println("index 1: " + word.charAt(1)
                + " / " + letters[1]);

        String snapshot = new String(letters);
        letters[0] = 'K';
        System.out.println("edited array: " + new String(letters));
        System.out.println("snapshot: " + snapshot);
        System.out.println("original String: " + word);

        char[] copied = word.toCharArray();
        copied[1] = 'o';
        System.out.println("toCharArray copy: " + new String(copied));
        System.out.println("String remains: " + word);

        String updated = word.replace('J', 'L');
        System.out.println("replace result: " + updated);
        System.out.println("replace source: " + word);

        System.out.println("equal text: " + word.equals(
                new String(new char[] {'J', 'a', 'v', 'a'})));
        System.out.println("equal arrays: " + Arrays.equals(
                word.toCharArray(), new char[] {'J', 'a', 'v', 'a'}));

        System.out.println("char arithmetic: " + ('A' + 'B'));
        System.out.println("char appended: " + ("A" + 'B'));

        int codePoint = 0x1F600;
        char[] twoUnits = Character.toChars(codePoint);
        String symbol = new String(twoUnits);
        System.out.println("supplementary units: " + twoUnits.length);
        System.out.println("supplementary String.length: "
                + symbol.length());
        System.out.println("supplementary codepoints: "
                + symbol.codePointCount(0, symbol.length()));
        System.out.println("high surrogate: "
                + Character.isHighSurrogate(twoUnits[0]));
    }
}
~~~

Requires **JDK 17+**; open a terminal in the directory containing the source file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac --release 17 -encoding UTF-8 CharStringArrayDemo.java
java -cp . CharStringArrayDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac --release 17 -encoding UTF-8 .\CharStringArrayDemo.java
java -cp . CharStringArrayDemo
~~~

**Expected output:**

~~~text
char: J
string: Java
array: Java
lengths: 4 / 4
index 1: a / a
edited array: Kava
snapshot: Java
original String: Java
toCharArray copy: Jova
String remains: Java
replace result: Lava
replace source: Java
equal text: true
equal arrays: true
char arithmetic: 131
char appended: AB
supplementary units: 2
supplementary String.length: 2
supplementary codepoints: 1
high surrogate: true
~~~

**Key verifications:**

- Modifying `letters[0]` only changes the **array**, not `snapshot` or `word`.
- Modifying the array returned by `toCharArray()` also **does not affect** `word`.
- `replace` produces a new string value without modifying the original `word`.
- `'A' + 'B'` is numeric addition on `char` values, producing `int` **131**; the expression `"A" + 'B'` concatenates into the string **AB**.
- Code point U+1F600 has two UTF-16 code units but is only one Unicode code point.

## 10. Common mistakes and fixes

| Case | What is wrong? | Correct approach |
|---|---|---|
| `char ch = "A";` | Literal `"A"` is a `String` | `char ch = 'A';` |
| `String s = 'A';` | Cannot directly assign `char` to `String` | `String s = String.valueOf('A');` |
| `word[0]` | String does not have the indexing operator `[]` | `word.charAt(0)` |
| `letters.charAt(0)` | Array does not have a `charAt` method | `letters[0]` |
| `word.length` | String does not have a public `length` field | `word.length()` |
| `letters.length()` | Array uses the `length` field | `letters.length` |
| `word.charAt(0) = 'K';` | Cannot assign to a method result; String is immutable | Create a new String or edit an array then convert back |
| `a.equals(b)` with two different `char[]` | Arrays do not compare element-by-element | `Arrays.equals(a, b)` |
| `str1 == str2` to compare content | Reference comparison | `str1.equals(str2)` when non-null |
| An emoji has `length() == 2` | `length` counts UTF-16 units | Use code point APIs as appropriate |
| `chars.toString()` | Does not convert array to text as expected | `new String(chars)` |
| `String s = null; s.length()` | Calling a method on null | Check for null before accessing |

### Index out-of-bounds errors

Both access forms require a non-negative index **less than the length**:

~~~java
String text = "ABC";
char[] array = {'A', 'B', 'C'};

// text.charAt(3); // StringIndexOutOfBoundsException if executed
// char c = array[3]; // ArrayIndexOutOfBoundsException if executed
~~~

With the code above, valid indices are 0, 1, 2. Java does **not** automatically return `'\0'` when reading past the end.

## 11. Choosing the right representation for the job

| Task | What to consider |
|---|---|
| Storing labels, names, messages, ordinary text | `String` |
| Comparing/transforming/splitting text with standard APIs | `String` |
| Handling a single UTF-16 code unit | `char` |
| Needing a buffer to modify individual code units by index | `char[]` |
| Building a string through many appends/concatenations/edits | `StringBuilder` is usually more convenient than array manipulation |
| Iterating Unicode characters outside the BMP by true code point | `String.codePoints()` and `Character` APIs |
| Handling confidential data needing active buffer clearing after use | `char[]` may be used with a copy-limiting process; not an absolute guarantee |

A good choice does not depend only on memory size: consider **immutability**, the APIs required by libraries, mutability needs, and the exact Unicode unit your business logic cares about.

### About `StringBuilder` when many edits are needed

~~~java
StringBuilder builder = new StringBuilder();
builder.append('J').append("ava");
builder.setCharAt(0, 'K');
String result = builder.toString();

System.out.println(result); // Kava
~~~

`StringBuilder` is a mutable object specialized for building and editing strings efficiently; **it is neither a `String` type nor a `char[]`**. After calling `toString()`, the returned string value is immutable just like any other `String`.

## 12. Exercises with answers

### Exercise A — classify the types

~~~java
char a = 'X';
String b = "X";
char[] c = {'X'};
~~~

**Answer:** `a` is a primitive char; `b` is a String object; `c` is a one-element char array object. Although all represent the letter X, they are not the same type.

### Exercise B — does the string change with the array?

~~~java
char[] data = {'a', 'b'};
String s = new String(data);
data[0] = 'z';
System.out.println(s);
System.out.println(new String(data));
~~~

**Answer:**

~~~text
ab
zb
~~~

`new String(data)` takes a copy of the content at the time of creation.

### Exercise C — difference between `length()` and `length`

~~~java
String word = "cat";
char[] data = word.toCharArray();
System.out.println(word.length());
System.out.println(data.length);
~~~

**Answer:** `3` and `3` respectively. The syntax differs because String uses a method while array uses a field.

### Exercise D — comparing two arrays

~~~java
char[] first = {'o', 'k'};
char[] second = {'o', 'k'};
System.out.println(first == second);
System.out.println(java.util.Arrays.equals(first, second));
~~~

**Answer:**

~~~text
false
true
~~~

### Exercise E — how many chars does a supplementary code point occupy?

~~~java
String s = new String(Character.toChars(0x1F600));
System.out.println(s.length());
System.out.println(s.codePointCount(0, s.length()));
~~~

**Answer:**

~~~text
2
1
~~~

Java String is indexed by UTF-16 code units. A code point outside the BMP typically requires a surrogate pair of two `char`s.

## 13. Pre-application checklist

- [ ] Distinguish primitive `char`, immutable `String`, and mutable `char[]`.
- [ ] Use single quotes for `char` and double quotes for `String`.
- [ ] Remember that `String.length()` and `char[].length` have different syntax.
- [ ] Use `charAt(i)` for String and `[i]` for arrays.
- [ ] Know that `new String(chars)` and `toCharArray()` create data unaffected by edits to the other side.
- [ ] Use `String.equals` for strings and `Arrays.equals` for arrays.
- [ ] Understand `char` is a UTF-16 code unit, not every Unicode code point.
- [ ] Distinguish numeric addition `'A' + 'B'` from string concatenation `"A" + 'B'`.
- [ ] Check for null and valid indices before accessing elements.
- [ ] Compile and run `CharStringArrayDemo.java` on JDK 17+ and compare the output.

**Conclusion:** `char` holds one UTF-16 code unit; `String` holds an **immutable** character sequence; `char[]` holds a sequence of `char`s **modifiable at each index**. Choosing the right type and understanding copy/conversion rules helps avoid accidental data mutation, wrong comparisons, and inaccurate Unicode handling.
